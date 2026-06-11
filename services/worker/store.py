"""Immutable document version store (PRD GEN-6, VAL-7, §10 data model).

M1 interim on SQLite: zero infra, transactional, and the schema mirrors the
PRD's `concept` / `doc_version` entities one-to-one so the M2 move to
Supabase Postgres is a driver/DSN swap, not a redesign. Immutability is
enforced in the database itself — UPDATE/DELETE on doc_version raise.

Provenance per version: parent, document-schema version, prompt pack,
model history, validation report (VAL-7), critique, usage/cost, origin
(generation | mutation | hand_finished), proof raster, content hash
(sha256 of the canonical document JSON — what approvals will lock, REV-6).
"""

import hashlib
import json
import sqlite3
import threading
import uuid

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
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA_SQL)
        self._lock = threading.Lock()  # one connection, many fan-out threads

    # ---------------------------------------------------------- concepts

    def create_concept(self, brief, archetype=""):
        cid = uuid.uuid4().hex
        with self._lock:
            self._db.execute(
                "INSERT INTO concept (id, brief_json, archetype) VALUES (?,?,?)",
                (cid, json.dumps(brief, sort_keys=True), archetype))
            self._db.commit()
        return cid

    def list_concepts(self, include_discarded=False):
        sql = "SELECT * FROM concept"
        if not include_discarded:
            sql += " WHERE discarded = 0"
        rows = self._db.execute(sql + " ORDER BY created_at").fetchall()
        return [self._concept_row(r) for r in rows]

    def get_concept(self, concept_id):
        row = self._db.execute(
            "SELECT * FROM concept WHERE id = ?", (concept_id,)).fetchone()
        return self._concept_row(row) if row else None

    def set_discarded(self, concept_id, discarded):
        """REV-1 discard/restore — concept curation state is mutable;
        doc_versions never are."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE concept SET discarded = ? WHERE id = ?",
                (1 if discarded else 0, concept_id))
            self._db.commit()
            return cur.rowcount > 0

    @staticmethod
    def _concept_row(row):
        return {"id": row["id"], "brief": json.loads(row["brief_json"]),
                "archetype": row["archetype"],
                "discarded": bool(row["discarded"]),
                "created_at": row["created_at"]}

    # ---------------------------------------------------------- versions

    def add_version(self, concept_id, document, *, schema_version,
                    prompt_pack, validation, model_history=None,
                    critique=None, usage=None, approved=False,
                    origin="generation", mutation_instruction=None,
                    proof_png=None, parent_version_id=None):
        vid = uuid.uuid4().hex
        with self._lock:
            self._db.execute(
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
            self._db.commit()
        return vid

    def get_version(self, version_id, include_document=True):
        row = self._db.execute(
            "SELECT * FROM doc_version WHERE id = ?", (version_id,)).fetchone()
        if row is None:
            return None
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
        row = self._db.execute(
            "SELECT proof_png FROM doc_version WHERE id = ?",
            (version_id,)).fetchone()
        return row["proof_png"] if row else None

    def list_versions(self, concept_id):
        rows = self._db.execute(
            "SELECT id FROM doc_version WHERE concept_id = ?"
            " ORDER BY created_at", (concept_id,)).fetchall()
        return [self.get_version(r["id"], include_document=False)
                for r in rows]

    def latest_version(self, concept_id):
        row = self._db.execute(
            "SELECT id FROM doc_version WHERE concept_id = ?"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (concept_id,)).fetchone()
        return self.get_version(row["id"]) if row else None
