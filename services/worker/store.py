"""Immutable document version store (PRD GEN-6, VAL-7, §10 data model).

M1 interim on SQLite: zero infra, transactional, and the schema mirrors the
PRD's `concept` / `doc_version` entities one-to-one so the M2 move to
Supabase Postgres is a driver/DSN swap, not a redesign. Immutability is
enforced in the database itself — UPDATE/DELETE on doc_version raise.

Concurrency: connection-per-operation + WAL journal. A single shared
connection across FastAPI's threadpool races its own commits ("database is
locked" mid-mutation while the UI streams proofs — found live, 11 Jun 2026).
WAL lets readers and the writer coexist; busy_timeout absorbs the rare
writer-writer overlap.

Provenance per version: parent, document-schema version, prompt pack,
model history, validation report (VAL-7), critique, usage/cost, origin
(generation | mutation | hand_finished), proof raster, content hash
(sha256 of the canonical document JSON — what approvals will lock, REV-6).
"""

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from workspace import (WorkspaceConflict, campaign_fields, identity_profile,
                       revision_number, string_list)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concept (
    id TEXT PRIMARY KEY,
    brief_json TEXT NOT NULL,
    archetype TEXT NOT NULL DEFAULT '',
    discarded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS doc_version (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concept(id),
    parent_version_id TEXT REFERENCES doc_version(id),
    document_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    prompt_pack TEXT NOT NULL,
    model_history_json TEXT NOT NULL DEFAULT '[]',
    validation_json TEXT NOT NULL,
    critique_json TEXT,
    usage_json TEXT,
    approved INTEGER NOT NULL DEFAULT 0,
    origin TEXT NOT NULL DEFAULT 'generation'
        CHECK (origin IN ('generation', 'mutation', 'hand_finished')),
    mutation_instruction TEXT,
    proof_png BLOB,
    effective_profile_json TEXT,
    text_changes_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_version_concept
    ON doc_version (concept_id, created_at);
CREATE TABLE IF NOT EXISTS asset (
    name TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    mime TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    data BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS brand_version (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    profile_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, version)
);
CREATE TRIGGER IF NOT EXISTS brand_version_immutable
    BEFORE UPDATE ON brand_version
    BEGIN SELECT RAISE(ABORT, 'brand_version rows are immutable (BRAND-4)'); END;
CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand_version_id TEXT REFERENCES brand_version(id),
    brief_json TEXT NOT NULL DEFAULT '{}',
    overrides_json TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    brief_json TEXT NOT NULL,
    n INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS campaign (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand_name TEXT NOT NULL,
    ranges_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (brand_name, name)
);
CREATE TABLE IF NOT EXISTS identity_draft (
    brand_name TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    revision INTEGER NOT NULL,
    base_version_id TEXT NOT NULL REFERENCES brand_version(id),
    published_version_id TEXT REFERENCES brand_version(id),
    published_revision INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS brand_asset_set (
    brand_name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS brand_asset (
    brand_name TEXT NOT NULL REFERENCES brand_asset_set(brand_name) ON DELETE CASCADE,
    asset_name TEXT NOT NULL REFERENCES asset(name),
    PRIMARY KEY (brand_name, asset_name)
);
CREATE TABLE IF NOT EXISTS comment (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concept(id),
    version_id TEXT REFERENCES doc_version(id),
    anchor_name TEXT,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_comment_concept
    ON comment (concept_id, created_at);
CREATE TRIGGER IF NOT EXISTS doc_version_immutable
    BEFORE UPDATE ON doc_version
    BEGIN SELECT RAISE(ABORT, 'doc_version rows are immutable (GEN-6)'); END;
CREATE TRIGGER IF NOT EXISTS doc_version_no_delete
    BEFORE DELETE ON doc_version
    BEGIN SELECT RAISE(ABORT, 'doc_version rows are immutable (GEN-6)'); END;
CREATE TABLE IF NOT EXISTS template (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    source_version_id TEXT NOT NULL REFERENCES doc_version(id),
    document_json TEXT NOT NULL,
    bindings_json TEXT NOT NULL,
    brand TEXT,
    schema_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TRIGGER IF NOT EXISTS template_immutable
    BEFORE UPDATE ON template
    BEGIN SELECT RAISE(ABORT, 'template rows are immutable (TPL-1)'); END;
CREATE TABLE IF NOT EXISTS template_run (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES template(id),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    error TEXT,
    rows_json TEXT NOT NULL,
    results_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS template_output (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES template_run(id),
    row_index INTEGER NOT NULL,
    document_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    proof_png BLOB,
    pdf BLOB,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_output_run
    ON template_output (run_id, row_index);
"""


def content_hash(document):
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocStore:

    def __init__(self, path):
        self._path = str(path)
        with closing(self._connect()) as db:
            db.executescript(SCHEMA_SQL)
            db.execute("PRAGMA journal_mode=WAL")  # persistent, set once
            # lightweight migrations: concept.job_id arrived with async jobs,
            # concept.failure_json with failed-generation surfacing (ADM-2),
            # project_id columns + job.brand_json with the project layer
            cols = {r[1] for r in db.execute("PRAGMA table_info(concept)")}
            if "job_id" not in cols:
                db.execute("ALTER TABLE concept ADD COLUMN job_id TEXT")
            if "failure_json" not in cols:
                db.execute("ALTER TABLE concept ADD COLUMN failure_json TEXT")
            if "project_id" not in cols:
                db.execute("ALTER TABLE concept ADD COLUMN project_id TEXT")
            jcols = {r[1] for r in db.execute("PRAGMA table_info(job)")}
            if "project_id" not in jcols:
                db.execute("ALTER TABLE job ADD COLUMN project_id TEXT")
            if "brand_json" not in jcols:
                db.execute("ALTER TABLE job ADD COLUMN brand_json TEXT")
            pcols = {r[1] for r in db.execute("PRAGMA table_info(project)")}
            if "campaign_id" not in pcols:
                db.execute("ALTER TABLE project ADD COLUMN campaign_id TEXT REFERENCES campaign(id)")
            self._migrate_project_name_scope(db)
            vcols = {r[1] for r in db.execute("PRAGMA table_info(doc_version)")}
            if "effective_profile_json" not in vcols:
                # Additive only: old documents are never rewritten or assigned
                # the current profile as guessed historical provenance.
                db.execute("ALTER TABLE doc_version ADD COLUMN effective_profile_json TEXT")
            if "text_changes_json" not in vcols:
                db.execute("ALTER TABLE doc_version ADD COLUMN text_changes_json TEXT")
            # legacy mutable brand_profile table -> versioned brand_version
            # (BRAND-4): each stored profile becomes version 1 of its brand
            if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table'"
                          " AND name = 'brand_profile'").fetchone():
                for r in db.execute("SELECT * FROM brand_profile").fetchall():
                    db.execute(
                        "INSERT OR IGNORE INTO brand_version (id, name,"
                        " version, profile_json, content_hash, created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (uuid.uuid4().hex, r["name"], 1, r["profile_json"],
                         content_hash(json.loads(r["profile_json"])),
                         r["created_at"]))
                db.execute("DROP TABLE brand_profile")
            db.commit()

    @staticmethod
    def _migrate_project_name_scope(db):
        """Remove the legacy global name uniqueness without replacing IDs.

        SQLite cannot drop a UNIQUE auto-index. Rebuild only the project table
        inside a transaction; preserve pins, briefs, campaign links, indexes,
        triggers and referencing rows. Foreign-key checks run before commit.
        """
        def quoted(name):
            return '"' + name.replace('"', '""') + '"'

        unique_name_indexes = {index['name'] for index in db.execute('PRAGMA index_list(project)').fetchall()
                               if index['unique'] and [row['name'] for row in db.execute('PRAGMA index_info(' + quoted(index['name']) + ')')] == ['name']}
        if not unique_name_indexes:
            return
        columns = ['id', 'name', 'brand_version_id', 'brief_json', 'overrides_json',
                   'status', 'created_at', 'updated_at', 'campaign_id']
        actual = {row['name'] for row in db.execute('PRAGMA table_info(project)')}
        if actual != set(columns):
            raise ValueError('cannot migrate project names with unknown project columns')
        saved_schema = [row['sql'] for row in db.execute(
            "SELECT name,sql FROM sqlite_master WHERE tbl_name='project' AND type IN ('index','trigger') AND sql IS NOT NULL")
            if row['name'] not in unique_name_indexes]
        db.commit()
        db.execute('PRAGMA foreign_keys=OFF')
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute("""CREATE TABLE project_scoped_migration (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                brand_version_id TEXT REFERENCES brand_version(id),
                brief_json TEXT NOT NULL DEFAULT '{}', overrides_json TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                campaign_id TEXT REFERENCES campaign(id))""")
            names = ','.join(columns)
            db.execute('INSERT INTO project_scoped_migration (' + names + ') SELECT ' + names + ' FROM project')
            db.execute('DROP TABLE project')
            db.execute('ALTER TABLE project_scoped_migration RENAME TO project')
            for sql in saved_schema:
                db.execute(sql)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('project-name migration would violate foreign-key integrity')
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute('PRAGMA foreign_keys=ON')

    def _connect(self):
        db = sqlite3.connect(self._path, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    # ---------------------------------------------------------- concepts

    def create_concept(self, brief, archetype="", job_id=None,
                       project_id=None):
        cid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO concept (id, brief_json, archetype, job_id,"
                " project_id) VALUES (?,?,?,?,?)",
                (cid, json.dumps(brief, sort_keys=True), archetype, job_id,
                 project_id))
            db.commit()
        return cid

    def concepts_for_job(self, job_id):
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT * FROM concept WHERE job_id = ? ORDER BY created_at",
                (job_id,)).fetchall()
        return [self._concept_row(r) for r in rows]

    # ---------------------------------------------------------- assets

    def add_asset(self, name, filename, mime, width, height, data):
        """Assets are write-once: versions reference them by name, so
        overwriting would silently rewrite history. Returns False if the
        name is taken."""
        with closing(self._connect()) as db:
            try:
                db.execute(
                    "INSERT INTO asset (name, filename, mime, width, height,"
                    " data) VALUES (?,?,?,?,?,?)",
                    (name, filename, mime, width, height, data))
                db.commit()
            except Exception:  # sqlite3.IntegrityError — name taken
                return False
        return True

    def list_assets(self):
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT name, filename, mime, width, height,"
                " length(data) AS size, created_at FROM asset"
                " ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def get_asset(self, name):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM asset WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return {"name": row["name"], "filename": row["filename"],
                "mime": row["mime"], "width": row["width"],
                "height": row["height"], "data": row["data"],
                "created_at": row["created_at"]}

    # ---------------------------------------------------------- brand profiles

    def save_brand_profile(self, name, profile):
        """Append-only versioning (BRAND-4): saving creates the next
        immutable brand version; a content-identical save is a no-op that
        returns the current head. Projects pin a version id, so edits never
        reach past work."""
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._append_brand_profile(db, name, profile)
            db.commit()
            return self._brand_row(row)

    @staticmethod
    def _append_brand_profile(db, name, profile):
        """The one immutable publication path; caller owns the transaction."""
        h = content_hash(profile)
        head = db.execute('SELECT * FROM brand_version WHERE name=? ORDER BY version DESC LIMIT 1', (name,)).fetchone()
        if head is not None and head['content_hash'] == h:
            return head
        vid = uuid.uuid4().hex
        db.execute('INSERT INTO brand_version (id,name,version,profile_json,content_hash) VALUES (?,?,?,?,?)',
                   (vid, name, head['version'] + 1 if head else 1, json.dumps(profile, sort_keys=True), h))
        if head is None:
            # New brands start with an explicitly empty library. Existing
            # migrated brands retain their legacy unassigned behaviour.
            db.execute('INSERT OR IGNORE INTO brand_asset_set (brand_name) VALUES (?)', (name,))
        return db.execute('SELECT * FROM brand_version WHERE id=?', (vid,)).fetchone()

    def list_brand_profiles(self):
        """Summaries only — head version per brand for the admin grid."""
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT b.*, (SELECT COUNT(*) FROM brand_version v"
                "  WHERE v.name = b.name) AS versions,"
                " (SELECT MIN(created_at) FROM brand_version v"
                "  WHERE v.name = b.name) AS first_created"
                " FROM brand_version b"
                " WHERE b.version = (SELECT MAX(version) FROM brand_version v"
                "  WHERE v.name = b.name)"
                " ORDER BY b.name").fetchall()
        out = []
        for r in rows:
            p = json.loads(r["profile_json"])
            out.append({
                "name": r["name"],
                "version": r["version"],
                "versions": r["versions"],
                "swatches": p.get("swatches", []),
                "fonts": p.get("fonts", []),
                "rules": p.get("rules", {}),
                "designPrinciples": p.get("designPrinciples"),
                "identity": ({"brandName": p['identity'].get('brandName')}
                             if isinstance(p.get('identity'), dict) else None),
                "created_at": r["first_created"],
                "updated_at": r["created_at"]})
        return out

    def get_brand_profile(self, name, version=None):
        """Head version by default; a specific immutable version on request."""
        sql = "SELECT * FROM brand_version WHERE name = ?"
        params = [name]
        if version is None:
            sql += " ORDER BY version DESC LIMIT 1"
        else:
            sql += " AND version = ?"
            params.append(version)
        with closing(self._connect()) as db:
            row = db.execute(sql, params).fetchone()
        return self._brand_row(row) if row else None

    def get_brand_version(self, brand_version_id):
        """The exact immutable version a project pinned (BRAND-4)."""
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM brand_version WHERE id = ?",
                             (brand_version_id,)).fetchone()
        return self._brand_row(row) if row else None

    def list_brand_versions(self, name):
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id, name, version, content_hash, created_at"
                " FROM brand_version WHERE name = ? ORDER BY version",
                (name,)).fetchall()
        return [dict(r) for r in rows]

    def delete_brand_profile(self, name):
        """Remove every version of a brand. Raises ValueError while any
        project pins one of them (FK RESTRICT) — archive or repin first."""
        with closing(self._connect()) as db:
            try:
                if db.execute('SELECT 1 FROM campaign WHERE brand_name=?', (name,)).fetchone():
                    raise ValueError('brand is associated with a campaign and cannot be deleted')
                db.execute('DELETE FROM identity_draft WHERE brand_name=?', (name,))
                cur = db.execute(
                    "DELETE FROM brand_version WHERE name = ?", (name,))
                db.execute('DELETE FROM brand_asset_set WHERE brand_name=?', (name,))
                db.commit()
            except sqlite3.IntegrityError:
                raise ValueError(
                    f'brand "{name}" is pinned by a project — it cannot be'
                    f" deleted while in use (BRAND-4)")
            return cur.rowcount > 0

    @staticmethod
    def _brand_row(row):
        return {"id": row["id"], "name": row["name"],
                "version": row["version"],
                "profile": json.loads(row["profile_json"]),
                "content_hash": row["content_hash"],
                "created_at": row["created_at"]}

    # ---------------------------------------------------------- studio workspace

    def create_campaign(self, **payload):
        fields = campaign_fields(payload)
        cid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM brand_version WHERE name=?', (fields['brand'],)).fetchone():
                raise ValueError('unknown campaign brand')
            try:
                db.execute('INSERT INTO campaign (id,name,brand_name,ranges_json,status) VALUES (?,?,?,?,?)',
                           (cid, fields['name'], fields['brand'], json.dumps(fields['ranges']), fields['status']))
                db.commit()
            except sqlite3.IntegrityError:
                raise WorkspaceConflict('campaign name already exists for this brand') from None
        return self.get_campaign(cid)

    def get_campaign(self, campaign_id):
        with closing(self._connect()) as db:
            row = db.execute('SELECT c.*, (SELECT COUNT(*) FROM project p WHERE p.campaign_id=c.id) AS project_count FROM campaign c WHERE id=?', (campaign_id,)).fetchone()
        return self._campaign_row(row) if row else None

    def list_campaigns(self, include_archived=False):
        with closing(self._connect()) as db:
            rows = db.execute('SELECT c.*, (SELECT COUNT(*) FROM project p WHERE p.campaign_id=c.id) AS project_count FROM campaign c'
                              + ('' if include_archived else " WHERE c.status='active'") + ' ORDER BY c.created_at,c.name').fetchall()
        return [self._campaign_row(r) for r in rows]

    @staticmethod
    def _campaign_row(row):
        return {'id': row['id'], 'name': row['name'], 'brand': row['brand_name'],
                'ranges': json.loads(row['ranges_json']), 'status': row['status'],
                'created_at': row['created_at'], 'updated_at': row['updated_at'],
                'project_count': row['project_count']}

    def update_campaign(self, campaign_id, **payload):
        fields = campaign_fields(payload, partial=True)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM campaign WHERE id=?', (campaign_id,)).fetchone()
            if current is None:
                return None
            if fields.get('brand', current['brand_name']) != current['brand_name']:
                raise WorkspaceConflict('campaign brand cannot change; create a campaign for the other brand')
            fields.pop('brand', None)
            if 'ranges' in fields:
                fields['ranges_json'] = json.dumps(fields.pop('ranges'))
            if fields:
                try:
                    db.execute('UPDATE campaign SET ' + ','.join(k + '=?' for k in fields)
                               + ",updated_at=datetime('now') WHERE id=?", (*fields.values(), campaign_id))
                except sqlite3.IntegrityError:
                    raise WorkspaceConflict('campaign name already exists for this brand') from None
            db.commit()
        return self.get_campaign(campaign_id)

    @staticmethod
    def _validate_project_campaign(db, campaign_id, brand_version_id):
        if campaign_id is None:
            return
        if not isinstance(campaign_id, str):
            raise ValueError('campaign_id must be a campaign ID or null')
        campaign = db.execute('SELECT * FROM campaign WHERE id=?', (campaign_id,)).fetchone()
        if campaign is None:
            raise ValueError('unknown campaign')
        brand = db.execute('SELECT name FROM brand_version WHERE id=?', (brand_version_id,)).fetchone()
        if brand is None or brand['name'] != campaign['brand_name']:
            raise WorkspaceConflict('project must pin a version of its campaign brand')

    def get_brand_assets(self, name):
        with closing(self._connect()) as db:
            assigned = db.execute('SELECT 1 FROM brand_asset_set WHERE brand_name=?', (name,)).fetchone() is not None
            names = [r[0] for r in db.execute('SELECT asset_name FROM brand_asset WHERE brand_name=? ORDER BY asset_name', (name,))]
        return {'brand': name, 'assigned': assigned, 'names': names}

    def set_brand_assets(self, name, names):
        names = string_list(names, 'names', limit=10000)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM brand_version WHERE name=?', (name,)).fetchone():
                raise ValueError('unknown brand')
            missing = [n for n in names if not db.execute('SELECT 1 FROM asset WHERE name=?', (n,)).fetchone()]
            if missing:
                raise ValueError('unknown assets: ' + ', '.join(missing))
            db.execute('INSERT OR IGNORE INTO brand_asset_set (brand_name) VALUES (?)', (name,))
            db.execute('DELETE FROM brand_asset WHERE brand_name=?', (name,))
            db.executemany('INSERT INTO brand_asset (brand_name,asset_name) VALUES (?,?)', [(name, n) for n in names])
            db.commit()
        return self.get_brand_assets(name)

    @staticmethod
    def _identity_row(row):
        return {'brand': row['brand_name'], 'profile': json.loads(row['profile_json']),
                'revision': row['revision'], 'base_version_id': row['base_version_id'],
                'published_version_id': row['published_version_id'],
                'published_revision': row['published_revision'], 'updated_at': row['updated_at'], 'is_saved': True}

    def get_identity_draft(self, name):
        with closing(self._connect()) as db:
            row = db.execute('SELECT * FROM identity_draft WHERE brand_name=?', (name,)).fetchone()
        if row:
            return self._identity_row(row)
        head = self.get_brand_profile(name)
        if head is None:
            return None
        return {'brand': name, 'profile': head['profile'], 'revision': 0,
                'base_version_id': head['id'], 'published_version_id': head['id'],
                'published_revision': None, 'updated_at': head['created_at'], 'is_saved': False}

    def save_identity_draft(self, name, profile, *, expected_revision, base_version_id=None):
        profile = identity_profile(name, profile)
        revision_number(expected_revision)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            head = db.execute('SELECT * FROM brand_version WHERE name=? ORDER BY version DESC LIMIT 1', (name,)).fetchone()
            if head is None:
                raise ValueError('unknown brand')
            current = db.execute('SELECT * FROM identity_draft WHERE brand_name=?', (name,)).fetchone()
            if expected_revision != (current['revision'] if current else 0):
                raise WorkspaceConflict('identity draft changed; reload before saving')
            base = base_version_id or (current['base_version_id'] if current else head['id'])
            if base_version_id is not None and base_version_id != head['id']:
                raise WorkspaceConflict('explicit draft base must be the current published version')
            db.execute('INSERT INTO identity_draft (brand_name,profile_json,revision,base_version_id) VALUES (?,?,?,?) '
                       'ON CONFLICT(brand_name) DO UPDATE SET profile_json=excluded.profile_json,revision=excluded.revision,base_version_id=excluded.base_version_id,updated_at=datetime(\'now\')',
                       (name, json.dumps(profile, sort_keys=True), expected_revision + 1, base))
            saved = db.execute('SELECT * FROM identity_draft WHERE brand_name=?', (name,)).fetchone()
            db.commit()
        return self._identity_row(saved)

    def publish_identity_draft(self, name, *, revision):
        revision_number(revision, 'revision')
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            draft = db.execute('SELECT * FROM identity_draft WHERE brand_name=?', (name,)).fetchone()
            if draft is None:
                raise ValueError('no saved identity draft to publish')
            if draft['revision'] != revision:
                raise WorkspaceConflict('identity draft changed; review the saved revision before publishing')
            head = db.execute('SELECT * FROM brand_version WHERE name=? ORDER BY version DESC LIMIT 1', (name,)).fetchone()
            if head is None or head['id'] != draft['base_version_id']:
                raise WorkspaceConflict('published brand changed; merge and save the draft against its new base before publishing')
            profile = identity_profile(name, json.loads(draft['profile_json']))
            if any(card.get('status') == 'draft' for card in profile.get('identity', {}).get('cards', [])):
                raise WorkspaceConflict('Review or reject all awaiting-review guidance cards before publishing')
            published = self._append_brand_profile(db, name, profile)
            db.execute('UPDATE identity_draft SET base_version_id=?,published_version_id=?,published_revision=?,updated_at=datetime(\'now\') WHERE brand_name=?',
                       (published['id'], published['id'], revision, name))
            saved = db.execute('SELECT * FROM identity_draft WHERE brand_name=?', (name,)).fetchone()
            db.commit()
            result = self._brand_row(published)
        return {'brand': result, 'draft': self._identity_row(saved)}

    # ---------------------------------------------------------- projects

    def create_project(self, name, *, brand_version_id=None, brief=None,
                       overrides=None, campaign_id=None):
        """The campaign layer: directional state riding on a pinned brand
        version. Mutable (unlike doc_versions) — the per-generation brand
        provenance snapshot lives on the job. Returns None if the name is
        taken within the same canonical brand and campaign."""
        pid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            self._validate_project_campaign(db, campaign_id, brand_version_id)
            if self._project_name_taken(db, name, brand_version_id, campaign_id):
                return None
            try:
                db.execute(
                    "INSERT INTO project (id, name, brand_version_id,"
                    " brief_json, overrides_json, campaign_id) VALUES (?,?,?,?,?,?)",
                    (pid, name, brand_version_id,
                     json.dumps(brief or {}, sort_keys=True),
                     json.dumps(overrides, sort_keys=True)
                     if overrides is not None else None, campaign_id))
                db.commit()
            except sqlite3.IntegrityError:
                return None
        return pid

    @staticmethod
    def _project_name_taken(db, name, brand_version_id, campaign_id, excluding=None):
        brand = db.execute('SELECT name FROM brand_version WHERE id=?', (brand_version_id,)).fetchone()
        brand_name = brand['name'] if brand else None
        return db.execute('SELECT 1 FROM project p LEFT JOIN brand_version b ON b.id=p.brand_version_id '
                          'WHERE p.name=? AND b.name IS ? AND p.campaign_id IS ? AND p.id IS NOT ? LIMIT 1',
                          (name, brand_name, campaign_id, excluding)).fetchone() is not None

    def get_project(self, project_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT p.*, b.name AS brand_name, b.version AS brand_version, c.name AS campaign_name"
                " FROM project p LEFT JOIN brand_version b"
                "  ON b.id = p.brand_version_id"
                " LEFT JOIN campaign c ON c.id = p.campaign_id"
                " WHERE p.id = ?", (project_id,)).fetchone()
        return self._project_row(row) if row else None

    def list_projects(self, include_archived=False):
        sql = ("SELECT p.*, b.name AS brand_name,"
               " b.version AS brand_version, campaign.name AS campaign_name,"
               " (SELECT COUNT(*) FROM concept c"
               "  WHERE c.project_id = p.id AND c.discarded = 0) AS concepts"
               " FROM project p LEFT JOIN brand_version b"
               "  ON b.id = p.brand_version_id"
               " LEFT JOIN campaign ON campaign.id = p.campaign_id")
        if not include_archived:
            sql += " WHERE p.status = 'active'"
        with closing(self._connect()) as db:
            rows = db.execute(sql + " ORDER BY p.created_at").fetchall()
        return [{**self._project_row(r), "concepts": r["concepts"]}
                for r in rows]

    def update_project(self, project_id, **fields):
        """Partial update of the mutable campaign layer. Accepts any of
        brief, overrides, status, brand_version_id (None unpins)."""
        allowed = {"brief": "brief_json", "overrides": "overrides_json",
                   "status": "status", "brand_version_id": "brand_version_id",
                   "campaign_id": "campaign_id"}
        unknown = set(fields) - set(allowed)
        if unknown:
            raise ValueError(f"unknown project fields: {sorted(unknown)}")
        if not fields:
            return self.get_project(project_id)
        sets, params = [], []
        for key, value in fields.items():
            if key == "brief":
                value = json.dumps(value or {}, sort_keys=True)
            elif key == "overrides":
                value = (json.dumps(value, sort_keys=True)
                         if value is not None else None)
            sets.append(f"{allowed[key]} = ?")
            params.append(value)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM project WHERE id=?', (project_id,)).fetchone()
            if current is None:
                return None
            self._validate_project_campaign(db, fields.get('campaign_id', current['campaign_id']),
                                            fields.get('brand_version_id', current['brand_version_id']))
            if self._project_name_taken(db, current['name'], fields.get('brand_version_id', current['brand_version_id']),
                                        fields.get('campaign_id', current['campaign_id']), excluding=project_id):
                raise WorkspaceConflict('project name already exists within this brand and campaign')
            cur = db.execute(
                "UPDATE project SET " + ", ".join(sets)
                + ", updated_at = datetime('now') WHERE id = ?",
                (*params, project_id))
            db.commit()
            if cur.rowcount == 0:
                return None
        return self.get_project(project_id)

    def concepts_for_project(self, project_id, include_discarded=False):
        sql = "SELECT * FROM concept WHERE project_id = ?"
        if not include_discarded:
            sql += " AND discarded = 0"
        with closing(self._connect()) as db:
            rows = db.execute(sql + " ORDER BY created_at",
                              (project_id,)).fetchall()
        return [self._concept_row(r) for r in rows]

    @staticmethod
    def _project_row(row):
        return {"id": row["id"], "name": row["name"],
                "campaign_id": row["campaign_id"],
                "campaign_name": row["campaign_name"],
                "brand_version_id": row["brand_version_id"],
                "brand": row["brand_name"],
                "brand_version": row["brand_version"],
                "brief": json.loads(row["brief_json"]),
                "overrides": (json.loads(row["overrides_json"])
                              if row["overrides_json"] else None),
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]}

    # ---------------------------------------------------------- jobs

    def create_job(self, brief, n, project_id=None, brand=None):
        """brand is the BRAND-6 provenance snapshot for project jobs:
        {brand, version, brand_version_id, overrides, effective_sha256} at
        the moment of generation — the project rows stay mutable, this
        doesn't."""
        jid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO job (id, brief_json, n, project_id, brand_json)"
                " VALUES (?,?,?,?,?)",
                (jid, json.dumps(brief, sort_keys=True), n, project_id,
                 json.dumps(brand, sort_keys=True)
                 if brand is not None else None))
            db.commit()
        return jid

    def set_job_status(self, job_id, status, error=None, finished=False):
        with closing(self._connect()) as db:
            db.execute(
                "UPDATE job SET status = ?, error = ?,"
                " finished_at = CASE WHEN ? THEN datetime('now')"
                " ELSE finished_at END WHERE id = ?",
                (status, error, 1 if finished else 0, job_id))
            db.commit()

    def get_job(self, job_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        keys = row.keys()
        return {"id": row["id"], "brief": json.loads(row["brief_json"]),
                "n": row["n"], "status": row["status"],
                "error": row["error"],
                "project_id": (row["project_id"]
                               if "project_id" in keys else None),
                "brand": (json.loads(row["brand_json"])
                          if "brand_json" in keys and row["brand_json"]
                          else None),
                "created_at": row["created_at"],
                "finished_at": row["finished_at"]}

    def list_concepts(self, include_discarded=False):
        sql = "SELECT * FROM concept"
        if not include_discarded:
            sql += " WHERE discarded = 0"
        with closing(self._connect()) as db:
            rows = db.execute(sql + " ORDER BY created_at").fetchall()
        return [self._concept_row(r) for r in rows]

    def get_concept(self, concept_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM concept WHERE id = ?", (concept_id,)).fetchone()
        return self._concept_row(row) if row else None

    def set_concept_failure(self, concept_id, failure):
        """ADM-2 (first slice): record why a generation run stored no
        doc_version for this concept, so the grid can say more than
        "no proof". Failure is concept curation state, not provenance —
        mutable, unlike doc_versions."""
        with closing(self._connect()) as db:
            cur = db.execute(
                "UPDATE concept SET failure_json = ? WHERE id = ?",
                (json.dumps(failure), concept_id))
            db.commit()
            return cur.rowcount > 0

    def set_discarded(self, concept_id, discarded):
        """REV-1 discard/restore — concept curation state is mutable;
        doc_versions never are."""
        with closing(self._connect()) as db:
            cur = db.execute(
                "UPDATE concept SET discarded = ? WHERE id = ?",
                (1 if discarded else 0, concept_id))
            db.commit()
            return cur.rowcount > 0

    # ---------------------------------------------------------- templates

    def create_template(self, name, source_version_id, document, bindings,
                        brand, schema_version):
        """TPL-1: templates are immutable at creation (DB-trigger enforced,
        like doc_version). Returns None if the name is taken."""
        tid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            try:
                db.execute(
                    "INSERT INTO template (id, name, source_version_id,"
                    " document_json, bindings_json, brand, schema_version)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (tid, name, source_version_id,
                     json.dumps(document, sort_keys=True),
                     json.dumps(bindings, sort_keys=True),
                     brand, schema_version))
                db.commit()
            except sqlite3.IntegrityError:
                return None
        return tid

    def get_template(self, template_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM template WHERE id = ?",
                             (template_id,)).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "name": row["name"],
                "source_version_id": row["source_version_id"],
                "document": json.loads(row["document_json"]),
                "bindings": json.loads(row["bindings_json"]),
                "brand": row["brand"],
                "schema_version": row["schema_version"],
                "created_at": row["created_at"]}

    def list_templates(self):
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id, name, source_version_id, bindings_json, brand,"
                " schema_version, created_at FROM template"
                " ORDER BY created_at").fetchall()
        return [{"id": r["id"], "name": r["name"],
                 "source_version_id": r["source_version_id"],
                 "slots": sorted(
                     json.loads(r["bindings_json"]).get("slots", {})),
                 "brand": r["brand"],
                 "schema_version": r["schema_version"],
                 "created_at": r["created_at"]} for r in rows]

    def create_template_run(self, template_id, rows):
        rid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO template_run (id, template_id, rows_json)"
                " VALUES (?,?,?)",
                (rid, template_id, json.dumps(rows)))
            db.commit()
        return rid

    def set_template_run(self, run_id, status, results=None, error=None,
                         finished=False):
        with closing(self._connect()) as db:
            db.execute(
                "UPDATE template_run SET status = ?, error = ?,"
                " results_json = COALESCE(?, results_json),"
                " finished_at = CASE WHEN ? THEN datetime('now')"
                " ELSE finished_at END WHERE id = ?",
                (status, error,
                 json.dumps(results) if results is not None else None,
                 1 if finished else 0, run_id))
            db.commit()

    def get_template_run(self, run_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM template_run WHERE id = ?",
                             (run_id,)).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "template_id": row["template_id"],
                "status": row["status"], "error": row["error"],
                "rows": json.loads(row["rows_json"]),
                "results": json.loads(row["results_json"]),
                "created_at": row["created_at"],
                "finished_at": row["finished_at"]}

    def add_template_output(self, run_id, row_index, document, proof_png,
                            pdf):
        oid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO template_output (id, run_id, row_index,"
                " document_json, content_hash, proof_png, pdf)"
                " VALUES (?,?,?,?,?,?,?)",
                (oid, run_id, row_index,
                 json.dumps(document, sort_keys=True),
                 content_hash(document), proof_png, pdf))
            db.commit()
        return oid

    def get_template_output(self, output_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM template_output WHERE id = ?",
                             (output_id,)).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "run_id": row["run_id"],
                "row_index": row["row_index"],
                "document": json.loads(row["document_json"]),
                "content_hash": row["content_hash"],
                "proof_png": row["proof_png"], "pdf": row["pdf"],
                "created_at": row["created_at"]}

    @staticmethod
    def _concept_row(row):
        keys = row.keys()
        return {"id": row["id"], "brief": json.loads(row["brief_json"]),
                "archetype": row["archetype"],
                "discarded": bool(row["discarded"]),
                "job_id": row["job_id"] if "job_id" in keys else None,
                "project_id": (row["project_id"]
                               if "project_id" in keys else None),
                "failure": (json.loads(row["failure_json"])
                            if "failure_json" in keys and row["failure_json"]
                            else None),
                "created_at": row["created_at"]}

    # ---------------------------------------------------------- versions

    def add_version(self, concept_id, document, *, schema_version,
                    prompt_pack, validation, model_history=None,
                    critique=None, usage=None, approved=False,
                    origin="generation", mutation_instruction=None,
                    proof_png=None, parent_version_id=None, effective_profile=None,
                    text_changes=None):
        vid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO doc_version (id, concept_id, parent_version_id,"
                " document_json, content_hash, schema_version, prompt_pack,"
                " model_history_json, validation_json, critique_json,"
                " usage_json, approved, origin, mutation_instruction,"
                " proof_png, effective_profile_json, text_changes_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (vid, concept_id, parent_version_id,
                 json.dumps(document, sort_keys=True),
                 content_hash(document), schema_version, prompt_pack,
                 json.dumps(model_history or []),
                 json.dumps(validation),
                 json.dumps(critique) if critique is not None else None,
                 json.dumps(usage) if usage is not None else None,
                 1 if approved else 0, origin, mutation_instruction,
                 proof_png, json.dumps(effective_profile, sort_keys=True)
                 if effective_profile is not None else None,
                 json.dumps(text_changes, sort_keys=True) if text_changes is not None else None))
            db.commit()
        return vid

    def get_version(self, version_id, include_document=True):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM doc_version WHERE id = ?",
                (version_id,)).fetchone()
        if row is None:
            return None
        return self._version_row(row, include_document)

    @staticmethod
    def _version_row(row, include_document):
        out = {
            "id": row["id"],
            "concept_id": row["concept_id"],
            "parent_version_id": row["parent_version_id"],
            "content_hash": row["content_hash"],
            "schema_version": row["schema_version"],
            "prompt_pack": row["prompt_pack"],
            "model_history": json.loads(row["model_history_json"]),
            "validation": json.loads(row["validation_json"]),
            "critique": (json.loads(row["critique_json"])
                         if row["critique_json"] else None),
            "usage": (json.loads(row["usage_json"])
                      if row["usage_json"] else None),
            "approved": bool(row["approved"]),
            "origin": row["origin"],
            "mutation_instruction": row["mutation_instruction"],
            "text_changes": (json.loads(row["text_changes_json"])
                             if row["text_changes_json"] else None),
            "has_proof": row["proof_png"] is not None,
            "effective_profile": (json.loads(row["effective_profile_json"])
                                  if row["effective_profile_json"] else None),
            "created_at": row["created_at"],
        }
        if include_document:
            out["document"] = json.loads(row["document_json"])
        return out

    def get_proof(self, version_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT proof_png FROM doc_version WHERE id = ?",
                (version_id,)).fetchone()
        return row["proof_png"] if row else None

    def list_versions(self, concept_id):
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT * FROM doc_version WHERE concept_id = ?"
                " ORDER BY created_at, rowid", (concept_id,)).fetchall()
        return [self._version_row(r, include_document=False) for r in rows]

    def latest_version(self, concept_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM doc_version WHERE concept_id = ?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (concept_id,)).fetchone()
        return self._version_row(row, True) if row else None

    # ---------------------------------------------------------- comments

    def add_comment(self, concept_id, body, *, author,
                    version_id=None, anchor_name=None):
        """REV-3 per-concept comment thread (Phase 1). version_id pins the
        comment to the version under review; anchor_name reserves the
        per-region pin (item ANNAME) for the P1 follow-up. Comments are
        mutable (resolve/reopen) — unlike doc_versions — but persisted so a
        future realtime layer (Liveblocks) is replaceable (PRD §12)."""
        cid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO comment (id, concept_id, version_id,"
                " anchor_name, author, body) VALUES (?,?,?,?,?,?)",
                (cid, concept_id, version_id, anchor_name, author, body))
            db.commit()
        return self.get_comment(cid)

    def get_comment(self, comment_id):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM comment WHERE id = ?",
                (comment_id,)).fetchone()
        return self._comment_row(row) if row else None

    def list_comments(self, concept_id):
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT * FROM comment WHERE concept_id = ?"
                " ORDER BY created_at, rowid", (concept_id,)).fetchall()
        return [self._comment_row(r) for r in rows]

    def set_comment_resolved(self, comment_id, resolved):
        with closing(self._connect()) as db:
            cur = db.execute(
                "UPDATE comment SET resolved = ? WHERE id = ?",
                (1 if resolved else 0, comment_id))
            db.commit()
            return cur.rowcount > 0

    @staticmethod
    def _comment_row(row):
        return {"id": row["id"], "concept_id": row["concept_id"],
                "version_id": row["version_id"],
                "anchor_name": row["anchor_name"],
                "author": row["author"], "body": row["body"],
                "resolved": bool(row["resolved"]),
                "created_at": row["created_at"]}

    # ---------------------------------------------------------- stats (ADM-1)

    def usage_stats(self, job_id=None, project_id=None):
        """ADM-1 v1: aggregate generation counts, token/cost spend, and
        validation outcomes from stored versions and no-version failures.

        Scope is global, per-job (one brief fan-out), or per-project (GEN-5
        per-project metering). Render latency is omitted: it isn't
        instrumented anywhere. Validation rates count FINAL stored versions
        only; saved in-loop repair diagnostics are not counted as versions.
        Failed concepts contribute known spend, not synthetic version counts.
        """
        from generation.metering import PRICES_PER_MTOK

        sql = ("SELECT dv.origin, dv.approved, dv.usage_json,"
               " dv.validation_json FROM doc_version dv")
        params = ()
        if job_id is not None:
            sql += " JOIN concept c ON c.id = dv.concept_id WHERE c.job_id = ?"
            params = (job_id,)
        elif project_id is not None:
            sql += (" JOIN concept c ON c.id = dv.concept_id"
                    " WHERE c.project_id = ?")
            params = (project_id,)
        with closing(self._connect()) as db:
            rows = db.execute(sql, params).fetchall()
            concept_sql = "SELECT COUNT(*) FROM concept"
            if job_id is not None:
                concept_sql += " WHERE job_id = ?"
            elif project_id is not None:
                concept_sql += " WHERE project_id = ?"
            concepts = db.execute(concept_sql, params).fetchone()[0]
            failure_sql = (
                "SELECT c.failure_json FROM concept c WHERE c.failure_json IS NOT NULL"
                " AND NOT EXISTS (SELECT 1 FROM doc_version dv WHERE dv.concept_id = c.id)")
            if job_id is not None:
                failure_sql += " AND c.job_id = ?"
            elif project_id is not None:
                failure_sql += " AND c.project_id = ?"
            failures = db.execute(failure_sql, params).fetchall()

        tokens = {"input": 0, "output": 0,
                  "cache_read": 0, "cache_creation": 0}
        by_origin, by_model = {}, {}
        errors_by_code, warnings_by_code = {}, {}
        cost_total = 0.0
        calls = approved = versions_with_errors = 0

        def _event_cost(e):
            price = PRICES_PER_MTOK.get(e["model"])
            if not price:
                return None  # unpriced (drift / retired model) — tokens only
            inp, outp = price
            return (e.get("input_tokens", 0) * inp
                    + e.get("output_tokens", 0) * outp
                    + e.get("cache_read_input_tokens", 0) * inp * 0.1
                    + e.get("cache_creation_input_tokens", 0) * inp * 1.25
                    ) / 1e6

        def _accumulate_usage(usage):
            nonlocal cost_total, calls
            if usage:
                cost_total += usage.get("cost_usd") or 0
                tokens["input"] += usage.get("input_tokens", 0)
                tokens["output"] += usage.get("output_tokens", 0)
                tokens["cache_read"] += usage.get(
                    "cache_read_input_tokens", 0)
                tokens["cache_creation"] += usage.get(
                    "cache_creation_input_tokens", 0)
                for e in usage.get("events", []):
                    calls += 1
                    m = by_model.setdefault(
                        e["model"], {"calls": 0, "input_tokens": 0,
                                     "output_tokens": 0, "cost_usd": 0.0,
                                     "priced": True})
                    m["calls"] += 1
                    m["input_tokens"] += e.get("input_tokens", 0)
                    m["output_tokens"] += e.get("output_tokens", 0)
                    c = _event_cost(e)
                    if c is None:
                        m["priced"] = False
                    else:
                        m["cost_usd"] += c

        for r in rows:
            by_origin[r["origin"]] = by_origin.get(r["origin"], 0) + 1
            if r["approved"]:
                approved += 1
            usage = json.loads(r["usage_json"]) if r["usage_json"] else None
            _accumulate_usage(usage)
            report = json.loads(r["validation_json"])
            errs = report.get("errors", [])
            if errs:
                versions_with_errors += 1
            for it in errs:
                code = it.get("code", "unknown")
                errors_by_code[code] = errors_by_code.get(code, 0) + 1
            for it in report.get("warnings", []):
                code = it.get("code", "unknown")
                warnings_by_code[code] = warnings_by_code.get(code, 0) + 1

        for row in failures:
            failure = json.loads(row["failure_json"])
            usage = failure.get("usage")
            _accumulate_usage(usage)
            # Older failures saved only an aggregate. Retain that known cost
            # without inventing tokens, calls, model splits or versions.
            if not usage or usage.get("cost_usd") is None:
                cost_total += failure.get("cost_usd") or 0

        return {
            "scope": ("job" if job_id is not None
                      else "project" if project_id is not None else "global"),
            "job_id": job_id,
            "project_id": project_id,
            "concepts": concepts,
            "versions": len(rows),
            "versions_by_origin": by_origin,
            "approved_versions": approved,
            "llm_calls": calls,
            "cost_usd_total": round(cost_total, 4),
            "tokens": tokens,
            "cost_by_model": [
                {"model": name, "calls": d["calls"],
                 "input_tokens": d["input_tokens"],
                 "output_tokens": d["output_tokens"],
                 "cost_usd": round(d["cost_usd"], 4),
                 "priced": d["priced"]}
                for name, d in sorted(by_model.items())],
            "validation": {
                "versions_with_errors": versions_with_errors,
                "errors_by_code": errors_by_code,
                "warnings_by_code": warnings_by_code,
            },
        }
