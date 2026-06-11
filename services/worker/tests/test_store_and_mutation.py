"""Store immutability/provenance (GEN-6, VAL-7) + mutation loop (GEN-7)."""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from brand import load_profile  # noqa: E402
from generation import prompts  # noqa: E402
from generation.mutation import doc_diff, mutate_document  # noqa: E402
from store import DocStore, content_hash  # noqa: E402

from test_generation_loop import (  # noqa: E402
    FakeRender, ScriptedClient, emit_resp, valid_doc, invalid_doc)

SCHEMA_PATH = str(REPO_ROOT / "schema" / "document-0.1.schema.json")
SCHEMA_JSON = json.loads(Path(SCHEMA_PATH).read_text())
PROFILE = load_profile(WORKER_ROOT / "examples" / "brand_profile.json")
PACK = prompts.load_pack("0.1")
PACK["exemplar"] = {}


def temp_store():
    return DocStore(Path(tempfile.mkdtemp()) / "test.db")


class TestStore(unittest.TestCase):

    def test_roundtrip_with_provenance(self):
        s = temp_store()
        cid = s.create_concept({"title": "t"}, "Hero split")
        vid = s.add_version(
            cid, valid_doc(), schema_version="0.1", prompt_pack="0.1",
            validation={"ok": True, "errors": [], "warnings": []},
            model_history=["claude-sonnet-4-6"], approved=True,
            proof_png=b"PNGBYTES")
        v = s.get_version(vid)
        self.assertEqual(v["concept_id"], cid)
        self.assertEqual(v["schema_version"], "0.1")
        self.assertTrue(v["approved"])
        self.assertTrue(v["has_proof"])
        self.assertEqual(v["content_hash"], content_hash(valid_doc()))
        self.assertEqual(s.get_proof(vid), b"PNGBYTES")
        self.assertEqual(v["document"]["version"], "0.1")

    def test_versions_are_immutable_in_the_database(self):
        s = temp_store()
        cid = s.create_concept({}, "")
        vid = s.add_version(
            cid, valid_doc(), schema_version="0.1", prompt_pack="0.1",
            validation={"ok": True})
        db = s._connect()
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute(
                "UPDATE doc_version SET approved = 1 WHERE id = ?", (vid,))
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("DELETE FROM doc_version WHERE id = ?", (vid,))
        db.close()

    def test_concurrent_readers_and_writers_do_not_lock(self):
        # Regression for the live 11 Jun 2026 failure: a mutation commit
        # raised "database is locked" while the UI streamed proofs.
        import threading

        s = temp_store()
        cid = s.create_concept({}, "")
        first = s.add_version(cid, valid_doc(), schema_version="0.1",
                              prompt_pack="0.1", validation={"ok": True},
                              proof_png=b"P" * 50_000)
        errors = []

        def writer():
            try:
                for _ in range(10):
                    s.add_version(cid, valid_doc(), schema_version="0.1",
                                  prompt_pack="0.1", validation={"ok": True},
                                  proof_png=b"P" * 50_000)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    s.get_proof(first)
                    s.list_versions(cid)
                    s.list_concepts()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = ([threading.Thread(target=writer) for _ in range(4)]
                   + [threading.Thread(target=reader) for _ in range(4)])
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(s.list_versions(cid)), 41)

    def test_version_chain(self):
        s = temp_store()
        cid = s.create_concept({}, "")
        v1 = s.add_version(cid, valid_doc(), schema_version="0.1",
                           prompt_pack="0.1", validation={"ok": True})
        doc2 = valid_doc()
        doc2["meta"] = {"title": "v2"}
        v2 = s.add_version(cid, doc2, schema_version="0.1",
                           prompt_pack="0.1", validation={"ok": True},
                           origin="mutation", parent_version_id=v1,
                           mutation_instruction="add a title")
        chain = s.list_versions(cid)
        self.assertEqual([c["id"] for c in chain], [v1, v2])
        self.assertEqual(chain[1]["parent_version_id"], v1)
        self.assertEqual(chain[1]["origin"], "mutation")
        self.assertEqual(s.latest_version(cid)["id"], v2)

    def test_content_hash_is_canonical(self):
        a = {"b": 1, "a": [1, 2]}
        b = {"a": [1, 2], "b": 1}
        self.assertEqual(content_hash(a), content_hash(b))


class TestJobs(unittest.TestCase):

    def test_job_lifecycle_and_concept_linkage(self):
        from generation.service import generate_and_store
        from test_generation_loop import critique_resp

        s = temp_store()
        jid = s.create_job({"title": "t"}, 2)
        self.assertEqual(s.get_job(jid)["status"], "queued")

        s.set_job_status(jid, "running")
        client = ScriptedClient([emit_resp(valid_doc()), critique_resp(True),
                                 emit_resp(valid_doc()), critique_resp(True)])
        summary = generate_and_store(
            {"title": "t"}, n=2, store=s, client=client, render=FakeRender(),
            pack=PACK, schema_json=SCHEMA_JSON, schema_path=SCHEMA_PATH,
            profile=PROFILE, job_id=jid)
        s.set_job_status(jid, "done", finished=True)

        self.assertEqual(summary["approved"], 2)
        linked = s.concepts_for_job(jid)
        self.assertEqual(len(linked), 2)
        self.assertTrue(all(c["job_id"] == jid for c in linked))
        j = s.get_job(jid)
        self.assertEqual(j["status"], "done")
        self.assertIsNotNone(j["finished_at"])

    def test_failed_job_records_error(self):
        s = temp_store()
        jid = s.create_job({}, 1)
        s.set_job_status(jid, "failed", error="render service down",
                         finished=True)
        j = s.get_job(jid)
        self.assertEqual(j["status"], "failed")
        self.assertIn("render", j["error"])


class TestDiff(unittest.TestCase):

    def test_diff_paths(self):
        old = valid_doc()
        new = valid_doc()
        new["charStyles"][0]["size"] = 60
        new["pages"][0]["items"].append(
            {"type": "shape", "name": "band", "frame": [0, 700, 595, 100],
             "fill": "BrandRed"})
        changes = doc_diff(old, new)
        paths = {c["path"]: c["change"] for c in changes}
        self.assertEqual(paths.get("charStyles[0].size"), "changed")
        self.assertEqual(paths.get("pages[0].items[1]"), "added")

    def test_identical_documents_diff_empty(self):
        self.assertEqual(doc_diff(valid_doc(), valid_doc()), [])


class TestMutation(unittest.TestCase):

    def run_mutation(self, client, render=None, instruction="bigger headline"):
        return mutate_document(
            valid_doc(), instruction, PROFILE, client=client,
            render=render or FakeRender(), pack=PACK,
            schema_json=SCHEMA_JSON, schema_path=SCHEMA_PATH)

    def test_successful_mutation_produces_diff(self):
        revised = valid_doc()
        revised["charStyles"][0]["size"] = 64
        client = ScriptedClient([emit_resp(revised)])
        r = self.run_mutation(client)
        self.assertIsNotNone(r.document)
        self.assertEqual(r.iterations, 1)
        self.assertIn("charStyles[0].size",
                      [c["path"] for c in r.diff])
        self.assertIsNotNone(r.proof_png_b64)

    def test_mutation_repairs_and_escalates_immediately(self):
        revised = valid_doc()
        revised["charStyles"][0]["size"] = 64
        client = ScriptedClient([emit_resp(invalid_doc()),
                                 emit_resp(revised)])
        r = self.run_mutation(client)
        self.assertIsNotNone(r.document)
        self.assertEqual(r.iterations, 2)
        # mutations escalate to the strong model on first failure
        self.assertNotEqual(client.calls[0]["model"], client.calls[1]["model"])

    def test_mutation_failure_reports_error(self):
        client = ScriptedClient([emit_resp(invalid_doc())] * 3)
        r = self.run_mutation(client)
        self.assertIsNone(r.document)
        self.assertIsNotNone(r.error)


if __name__ == "__main__":
    unittest.main()
