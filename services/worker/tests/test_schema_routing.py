"""Schema/prompt/exemplar routing and immutable provenance (T05)."""

import sys
import tempfile
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from generation.loop import GenConfig  # noqa: E402
from generation.service import generate_and_store, mutate_and_store  # noqa: E402
from schema_registry import SchemaRoutingError, load, route  # noqa: E402
from store import DocStore  # noqa: E402
from test_generation_loop import (FakeRender, PROFILE, ScriptedClient,
                                  critique_resp, emit_resp, valid_doc)  # noqa: E402


def store():
    return DocStore(Path(tempfile.mkdtemp()) / "routing.db")


def valid_0_2():
    return {"version": "0.2", "page": {"size": [100, 100]},
            "pages": [{"items": []}]}


class TestSchemaRouting(unittest.TestCase):

    def test_registry_routes_every_supported_version_as_a_matched_set(self):
        for version in ("0.1", "0.2"):
            runtime = load(version)
            self.assertEqual(runtime["version"], version)
            self.assertEqual(runtime["pack"]["version"], version)
            self.assertTrue(Path(runtime["schema_path"]).is_file())
            self.assertTrue(Path(runtime["exemplar_path"]).is_file())

    def test_unknown_and_mismatched_routes_are_rejected(self):
        with self.assertRaises(SchemaRoutingError):
            route("9.9")
        with self.assertRaises(SchemaRoutingError):
            load("0.2", prompt_pack="0.1")

    def test_new_generation_stores_the_validated_document_version(self):
        runtime = load("0.2")
        db = store()
        client = ScriptedClient([emit_resp(valid_0_2()), critique_resp(True)])
        result = generate_and_store(
            {"title": "pilot"}, n=1, store=db, client=client,
            render=FakeRender(), pack=runtime["pack"],
            schema_json=runtime["schema_json"], schema_path=runtime["schema_path"],
            profile=PROFILE, expected_version="0.2")
        version = db.get_version(result["concepts"][0]["version_id"])
        self.assertEqual(version["schema_version"], "0.2")
        self.assertEqual(version["prompt_pack"], "0.2")

    def test_emitted_version_mismatch_is_not_stored_with_false_provenance(self):
        runtime = load("0.2")
        db = store()
        result = generate_and_store(
            {"title": "pilot"}, n=1, store=db,
            client=ScriptedClient([emit_resp(valid_doc())]), render=FakeRender(),
            pack=runtime["pack"], schema_json=runtime["schema_json"],
            schema_path=runtime["schema_path"], profile=PROFILE,
            expected_version="0.2", config=GenConfig(max_iterations=1))
        self.assertIsNone(result["concepts"][0]["version_id"])
        concept = db.get_concept(result["concepts"][0]["concept_id"])
        self.assertIn("document-version-mismatch", concept["failure"]["error"])

    def test_mutation_inherits_parent_route_for_both_versions(self):
        db = store()
        for version, doc in (("0.1", valid_doc()), ("0.2", valid_0_2())):
            with self.subTest(version=version):
                runtime = load(version)
                concept = db.create_concept({"title": version}, "")
                parent = db.add_version(
                    concept, doc, schema_version=version, prompt_pack=version,
                    validation={"ok": True}, effective_profile=PROFILE)
                new_id, result = mutate_and_store(
                    parent, "retain version", store=db,
                    client=ScriptedClient([emit_resp(doc)]), render=FakeRender(),
                    pack=runtime["pack"], schema_json=runtime["schema_json"],
                    schema_path=runtime["schema_path"], profile=PROFILE,
                    expected_version=version)
                self.assertIsNotNone(result.document)
                child = db.get_version(new_id)
                self.assertEqual(child["schema_version"], version)
                self.assertEqual(child["prompt_pack"], version)


if __name__ == "__main__":
    unittest.main()
