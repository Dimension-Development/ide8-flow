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
CREATE TRIGGER IF NOT EXISTS doc_version_immutable
    BEFORE UPDATE ON doc_version
    BEGIN SELECT RAISE(ABORT, 'doc_version rows are immutable (GEN-6)'); END;
CREATE TRIGGER IF NOT EXISTS doc_version_no_delete
    BEFORE DELETE ON doc_version
    BEGIN SELECT RAISE(ABORT, 'doc_version rows are immutable (GEN-6)'); END;
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
            # lightweight migration: concept.job_id arrived with async jobs
            cols = {r[1] for r in db.execute("PRAGMA table_info(concept)")}
            if "job_id" not in cols:
                db.execute("ALTER TABLE concept ADD COLUMN job_id TEXT")
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

    def set_discarded(self, concept_id, discarded):
        """REV-1 discard/restore — concept curation state is mutable;
        doc_versions never are."""
        with closing(self._connect()) as db:
            cur = db.execute(
                "UPDATE concept SET discarded = ? WHERE id = ?",
                (1 if discarded else 0, concept_id))
            db.commit()
            return cur.rowcount > 0

    @staticmethod
    def _concept_row(row):
        return {"id": row["id"], "brief": json.loads(row["brief_json"]),
                "archetype": row["archetype"],
                "discarded": bool(row["discarded"]),
                "job_id": row["job_id"] if "job_id" in row.keys() else None,
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
