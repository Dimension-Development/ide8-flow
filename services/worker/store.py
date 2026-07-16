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
CREATE TABLE IF NOT EXISTS brand_profile (
    name TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
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
            # concept.failure_json with failed-generation surfacing (ADM-2)
            cols = {r[1] for r in db.execute("PRAGMA table_info(concept)")}
            if "job_id" not in cols:
                db.execute("ALTER TABLE concept ADD COLUMN job_id TEXT")
            if "failure_json" not in cols:
                db.execute("ALTER TABLE concept ADD COLUMN failure_json TEXT")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self._path, timeout=10.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    # ---------------------------------------------------------- concepts

    def create_concept(self, brief, archetype="", job_id=None):
        cid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO concept (id, brief_json, archetype, job_id)"
                " VALUES (?,?,?,?)",
                (cid, json.dumps(brief, sort_keys=True), archetype, job_id))
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
        """Upsert a brand profile (BRAND-3 de-singleton). Mutable for now;
        profile-version pinning once a project uses it is BRAND-4."""
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO brand_profile (name, profile_json) VALUES (?,?)"
                " ON CONFLICT(name) DO UPDATE SET profile_json = excluded."
                "profile_json, updated_at = datetime('now')",
                (name, json.dumps(profile, sort_keys=True)))
            db.commit()
        return self.get_brand_profile(name)

    def list_brand_profiles(self):
        """Summaries only — swatch/font counts for the admin grid."""
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT name, profile_json, created_at, updated_at"
                " FROM brand_profile ORDER BY name").fetchall()
        out = []
        for r in rows:
            p = json.loads(r["profile_json"])
            out.append({
                "name": r["name"],
                "version": p.get("version"),
                "swatches": p.get("swatches", []),
                "fonts": p.get("fonts", []),
                "rules": p.get("rules", {}),
                "designPrinciples": p.get("designPrinciples"),
                "created_at": r["created_at"], "updated_at": r["updated_at"]})
        return out

    def get_brand_profile(self, name):
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM brand_profile WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return {"name": row["name"],
                "profile": json.loads(row["profile_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]}

    def delete_brand_profile(self, name):
        with closing(self._connect()) as db:
            cur = db.execute(
                "DELETE FROM brand_profile WHERE name = ?", (name,))
            db.commit()
            return cur.rowcount > 0

    # ---------------------------------------------------------- jobs

    def create_job(self, brief, n):
        jid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO job (id, brief_json, n) VALUES (?,?,?)",
                (jid, json.dumps(brief, sort_keys=True), n))
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
        return {"id": row["id"], "brief": json.loads(row["brief_json"]),
                "n": row["n"], "status": row["status"],
                "error": row["error"], "created_at": row["created_at"],
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
                "failure": (json.loads(row["failure_json"])
                            if "failure_json" in keys and row["failure_json"]
                            else None),
                "created_at": row["created_at"]}

    # ---------------------------------------------------------- versions

    def add_version(self, concept_id, document, *, schema_version,
                    prompt_pack, validation, model_history=None,
                    critique=None, usage=None, approved=False,
                    origin="generation", mutation_instruction=None,
                    proof_png=None, parent_version_id=None):
        vid = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO doc_version (id, concept_id, parent_version_id,"
                " document_json, content_hash, schema_version, prompt_pack,"
                " model_history_json, validation_json, critique_json,"
                " usage_json, approved, origin, mutation_instruction,"
                " proof_png) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (vid, concept_id, parent_version_id,
                 json.dumps(document, sort_keys=True),
                 content_hash(document), schema_version, prompt_pack,
                 json.dumps(model_history or []),
                 json.dumps(validation),
                 json.dumps(critique) if critique is not None else None,
                 json.dumps(usage) if usage is not None else None,
                 1 if approved else 0, origin, mutation_instruction,
                 proof_png))
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
            "has_proof": row["proof_png"] is not None,
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

    def usage_stats(self, job_id=None):
        """ADM-1 v1: aggregate generation counts, token/cost spend, and
        validation outcomes from the persisted doc_version provenance.

        Scope is global or per-job — a job is one brief fan-out. (Per-project
        rollups wait on a `project` entity, which the M2 store doesn't have
        yet.) Render latency is omitted: it isn't instrumented anywhere.
        Validation rates count FINAL stored versions only; in-loop repair
        attempts are fed back to the model and never persisted, so they're not
        reflected here.
        """
        from generation.metering import PRICES_PER_MTOK

        sql = ("SELECT dv.origin, dv.approved, dv.usage_json,"
               " dv.validation_json FROM doc_version dv")
        params = ()
        if job_id is not None:
            sql += " JOIN concept c ON c.id = dv.concept_id WHERE c.job_id = ?"
            params = (job_id,)
        with closing(self._connect()) as db:
            rows = db.execute(sql, params).fetchall()
            concept_sql = "SELECT COUNT(*) FROM concept"
            if job_id is not None:
                concept_sql += " WHERE job_id = ?"
            concepts = db.execute(concept_sql, params).fetchone()[0]

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

        for r in rows:
            by_origin[r["origin"]] = by_origin.get(r["origin"], 0) + 1
            if r["approved"]:
                approved += 1
            usage = json.loads(r["usage_json"]) if r["usage_json"] else None
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

        return {
            "scope": "job" if job_id is not None else "global",
            "job_id": job_id,
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
