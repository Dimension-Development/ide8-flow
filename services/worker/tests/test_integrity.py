"""Regressions for reproducible versions, protected refinements and format gates."""

import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brand import apply_overrides
from generation.loop import GenConfig, generate_concept
from generation.mutation import mutate_document
from generation.service import generate_and_store, mutate_and_store
from provenance import MissingProfileSnapshot, profile_for_version
from store import DocStore, SCHEMA_SQL, content_hash
from validation import brief_checks, contrast, format_check, mutation_checks
from test_generation_loop import (PROFILE, PACK, BRIEF, SCHEMA_JSON, SCHEMA_PATH,
                                  FakeRender, ScriptedClient, valid_doc,
                                  emit_resp, critique_resp)


def dependencies(responses, render=None):
    return dict(client=ScriptedClient(responses), render=render or FakeRender(),
                pack=PACK, schema_json=SCHEMA_JSON, schema_path=SCHEMA_PATH,
                config=GenConfig(max_iterations=1), expected_version="0.1")


class TestFormat(unittest.TestCase):
    def test_invalid_format_api_rejects_before_model_initialization(self):
        from fastapi.testclient import TestClient
        import app
        with patch("app._gen_deps", side_effect=AssertionError("must not initialize")):
            r = TestClient(app.app).post("/generate", json={"brief": {"format": {"size": "unknown"}}})
        self.assertEqual(r.status_code, 422)
    def test_wrong_but_internally_valid_format_is_rejected(self):
        spec = {"size": "A3", "orientation": "landscape", "bleed": 9,
                "margins": [20] * 4}
        errors = format_check.check(valid_doc(), spec)
        self.assertEqual({e["path"] for e in errors},
                         {"page.size", "page.orientation", "page.bleed", "page.margins"})
        doc = {"page": spec}
        self.assertEqual(format_check.check(doc, spec), [])

    def test_explicit_pilot_units_and_rounding(self):
        spec = {"trimMm": [100, 150], "bleedMm": 3, "safeAreaMm": 5}
        doc = {"page": {"size": [283.46, 425.20], "bleed": 8.504,
                        "margins": [14.173] * 4}}
        self.assertEqual(format_check.check(doc, spec), [])
        self.assertEqual(format_check.check(doc, {"trimPt": doc["page"]["size"]}), [])

    def test_invalid_or_conflicting_specs(self):
        for spec in (None, {"size": "A99"}, {"size": [0, 100]},
                     {"size": [True, 100]}, {"bleed": float("nan")},
                     {"orientation": "diagonal"}, {"margins": [1, 2]},
                     {"bleed": 3, "bleedMm": 3}, {"size": "A4", "trimPt": [1, 2]}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                format_check.normalize_format(spec)

    def test_generation_never_renders_wrong_requested_size(self):
        deps = dependencies([emit_resp(valid_doc())])
        r = generate_concept({**BRIEF, "format": {"size": "A3"}}, PROFILE, "", **deps)
        self.assertIsNone(r.document)
        self.assertEqual(deps["render"].compiled, [])
        self.assertIn("format-mismatch", {e["code"] for e in r.validation["errors"]})


class TestMutationProtection(unittest.TestCase):
    def setUp(self):
        self.doc = valid_doc()
        legal = deepcopy(self.doc["pages"][0]["items"][0])
        legal.update(name="legal", frame=[40, 280, 400, 100])
        legal["paragraphs"][0]["text"] = "Subject to availability."
        self.doc["pages"][0]["items"].append(legal)

    def test_dropped_or_rewritten_legal_never_renders(self):
        for remove in (False, True):
            revised = deepcopy(self.doc)
            if remove:
                revised["pages"][0]["items"].pop()
            else:
                revised["pages"][0]["items"][-1]["paragraphs"][0]["text"] = "Availability varies."
            deps = dependencies([emit_resp(revised)])
            r = mutate_document(self.doc, "Increase headline size", PROFILE, **deps)
            self.assertIsNone(r.document)
            self.assertEqual(deps["render"].compiled, [])
            self.assertIn("protected-copy", {e["code"] for e in r.validation["errors"]})

    def test_exact_replacement_passes_and_becomes_next_baseline(self):
        revised = deepcopy(self.doc)
        revised["pages"][0]["items"][0]["paragraphs"][0]["text"] = "NEW APPROVED HEADLINE"
        r = mutate_document(self.doc, "Use the new approved headline", PROFILE,
                            text_changes={"headline": "NEW APPROVED HEADLINE"},
                            **dependencies([emit_resp(revised)]))
        self.assertEqual(r.document, revised)
        self.assertEqual(mutation_checks.check(revised, deepcopy(revised), PROFILE), [])
        self.assertTrue(mutation_checks.check(revised, self.doc, PROFILE))

    def test_replacement_is_required_and_must_be_unambiguous(self):
        self.assertTrue(mutation_checks.check(self.doc, self.doc, PROFILE,
                                             text_changes={"headline": "NEW"}))
        for changes in ([], {"missing": "x"}, {"legal": ""}):
            deps = dependencies([])
            r = mutate_document(self.doc, "change copy", PROFILE, text_changes=changes, **deps)
            self.assertIsNone(r.document)
            self.assertEqual(deps["client"].calls, [])
        self.doc["pages"][0]["items"].append(deepcopy(self.doc["pages"][0]["items"][0]))
        self.assertTrue(mutation_checks.validate_text_changes(self.doc, {"headline": "NEW"}))

    def test_page_size_and_required_logo_identity_are_preserved(self):
        self.doc["pages"][0]["items"].append({"type": "image", "name": "logo", "src": "approved-logo"})
        changed = deepcopy(self.doc)
        changed["page"]["size"] = "A3"
        changed["pages"][0]["items"][-1]["src"] = "different-logo"
        codes = {e["code"] for e in mutation_checks.check(
            self.doc, changed, {"rules": {"mandatoryElements": ["logo"]}})}
        self.assertEqual(codes, {"format-mismatch", "protected-mandatory"})

    def test_spot_path_and_unnamed_duplicate_copy_cannot_disappear(self):
        spot = {"type": "path", "name": "cut", "stroke": {"color": "CutContour"},
                "frame": [0, 0, 100, 100], "points": [[0, 0], [100, 100]]}
        self.doc["pages"][0]["items"].append(spot)
        self.doc["swatches"] = [{"name": "CutContour", "spot": True}]
        changed = deepcopy(self.doc)
        changed["pages"][0]["items"][-1]["frame"][0] = 1
        self.assertIn("protected-production-path", {e["code"] for e in
                      mutation_checks.check(self.doc, changed, PROFILE)})
        duplicate = deepcopy(self.doc["pages"][0]["items"][0])
        duplicate.pop("name")
        self.doc["pages"][0]["items"].append(duplicate)
        self.assertIn("protected-copy", {e["code"] for e in
                      mutation_checks.check(self.doc, changed, PROFILE)})

    def test_custom_landscape_dimensions_without_orientation_are_supported(self):
        self.doc["page"]["size"] = [800, 400]
        self.assertEqual(mutation_checks.check(self.doc, self.doc, PROFILE), [])

    def test_copy_check_matches_rendered_runs_not_hidden_text(self):
        para = self.doc["pages"][0]["items"][0]["paragraphs"][0]
        para["runs"] = [{"text": "SUMMER JUST "}, {"text": "LANDED"}]
        self.assertEqual(brief_checks.check(self.doc, BRIEF)[0], [])
        para["runs"] = [{"text": "Different"}]
        self.assertIn("missing-copy", {e["code"] for e in brief_checks.check(self.doc, BRIEF)[0]})
        para["runs"] = [{"text": "SUMMER"}, {"text": "JUST LANDED"}]
        self.assertIn("missing-copy", {e["code"] for e in brief_checks.check(self.doc, BRIEF)[0]})


class TestCandidateIdentity(unittest.TestCase):
    def test_failed_final_attempt_cannot_replace_document_or_report(self):
        first, second = valid_doc(), valid_doc()
        second["charStyles"][0]["size"] = 42
        class DistinctProofs(FakeRender):
            def proof_meta(self, *args, **kwargs):
                return (("Zmlyc3Q=", []) if len(self.compiled) == 1 else
                        ("c2Vjb25k", [{"item": "headline", "page": 1}]))
        deps = dependencies([emit_resp(first), critique_resp(False, [{"issue": "spacing"}]),
                             emit_resp(second)], DistinctProofs())
        deps["config"].max_iterations = 2
        r = generate_concept(BRIEF, PROFILE, "", **deps)
        self.assertEqual(r.document, first)
        self.assertEqual(r.proof_png_b64, "Zmlyc3Q=")
        self.assertEqual(r.critique["issues"], [{"issue": "spacing"}])
        self.assertTrue(r.validation["ok"])
        self.assertFalse(r.validation["attempts"][1]["validation"]["ok"])
        self.assertFalse(r.approved)

    def test_only_overflowing_attempt_creates_no_version(self):
        with tempfile.TemporaryDirectory() as td:
            db = DocStore(Path(td) / "test.db")
            r = generate_and_store(BRIEF, n=1, store=db, profile=PROFILE,
                **dependencies([emit_resp(valid_doc())], FakeRender([[{"item": "headline"}]])))
            self.assertIsNone(r["concepts"][0]["version_id"])
            concept = db.get_concept(r["concepts"][0]["concept_id"])
            self.assertIn("overflow", concept["failure"]["error"])


class TestPhotographicContrast(unittest.TestCase):
    def test_image_backdrop_is_explicitly_unverified_then_opaque_fill_restores_gate(self):
        doc = valid_doc()
        doc["swatches"] = [{"name": "White", "space": "rgb", "values": [255, 255, 255]}]
        doc["charStyles"][0]["color"] = "White"
        doc["pages"][0]["items"].insert(0, {"type": "image", "frame": [0, 0, 595, 842]})
        warnings=[]
        self.assertEqual(contrast.check(doc, {}, warnings=warnings), [])
        self.assertEqual(warnings[0]["code"], "image-contrast-review")
        doc["pages"][0]["items"].insert(1, {"type": "shape", "frame": [0, 0, 595, 842], "fill": "White"})
        warnings=[]
        self.assertEqual(contrast.check(doc, {}, warnings=warnings)[0]["code"], "low-contrast")
        self.assertEqual(warnings, [])
        doc["pages"][0]["items"][1]["opacity"] = 0.5
        self.assertEqual(contrast.check(doc, {}, warnings=warnings), [])
        self.assertEqual(warnings[0]["code"], "image-contrast-review")


class TestProfileSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.db"
        self.db = DocStore(self.path)
        self.cid = self.db.create_concept(BRIEF)

    def version(self, **kw):
        return self.db.add_version(self.cid, valid_doc(), schema_version="0.1",
                                   prompt_pack="0.1", validation={"ok": True}, **kw)

    def test_generation_snapshots_profile_and_refinement_inherits_it(self):
        result = generate_and_store(BRIEF, n=1, store=self.db, profile=PROFILE,
                                    **dependencies([emit_resp(valid_doc()), critique_resp(True)]))
        vid = result["concepts"][0]["version_id"]
        self.assertEqual(self.db.get_version(vid)["effective_profile"], PROFILE)
        revised = valid_doc()
        revised["pages"][0]["items"][0]["paragraphs"][0]["text"] = "NEW HEADLINE"
        changes = {"headline": "NEW HEADLINE"}
        child, _ = mutate_and_store(vid, "Use new copy", store=self.db,
                                     profile={"name": "Wrong current brand"},
                                     text_changes=changes,
                                     **dependencies([emit_resp(revised)]))
        self.assertEqual(self.db.get_version(child)["effective_profile"], PROFILE)
        self.assertEqual(self.db.get_version(child)["text_changes"], changes)

    def test_snapshot_cannot_be_rewritten(self):
        vid = self.version(effective_profile=PROFILE)
        with sqlite3.connect(self.path) as db, self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE doc_version SET effective_profile_json='{}' WHERE id=?", (vid,))

    def test_legacy_generation_requires_matching_original_job_evidence(self):
        brand = self.db.save_brand_profile("Original", PROFILE)
        overrides = {"add": {"fonts": ["Extra Font"]}}
        effective = apply_overrides(PROFILE, overrides)
        for digest, origin, works in ((content_hash(effective), "generation", True),
                                       ("wrong-hash", "generation", False),
                                       (content_hash(effective), "mutation", False)):
            jid = self.db.create_job(BRIEF, 1, brand={"brand_version_id": brand["id"],
                     "overrides": overrides, "effective_sha256": digest})
            self.cid = self.db.create_concept(BRIEF, job_id=jid)
            version = self.db.get_version(self.version(origin=origin))
            if works:
                self.assertEqual(profile_for_version(self.db, version), effective)
            else:
                with self.assertRaises(MissingProfileSnapshot):
                    profile_for_version(self.db, version)

    def test_additive_migration_preserves_legacy_hash_and_proof(self):
        path = Path(self.tmp.name) / "legacy.db"
        with sqlite3.connect(path) as db:
            db.executescript(SCHEMA_SQL.replace("    effective_profile_json TEXT,\n", "")
                             .replace("    text_changes_json TEXT,\n", ""))
            db.execute("INSERT INTO concept (id, brief_json, archetype) VALUES ('c','{}','')")
            db.execute("INSERT INTO doc_version (id,concept_id,document_json,content_hash,"
                       "schema_version,prompt_pack,validation_json,proof_png) VALUES "
                       "('v','c','{}','original-hash','0.1','0.1','{}',?)", (b"original-proof",))
        migrated = DocStore(path)
        self.assertEqual(migrated.get_version("v")["content_hash"], "original-hash")
        self.assertEqual(migrated.get_proof("v"), b"original-proof")
        self.assertIsNone(migrated.get_version("v")["effective_profile"])

    def test_exports_stay_identical_after_project_and_brand_changes_without_model_key(self):
        from fastapi.testclient import TestClient
        import app
        class EchoRender:
            def compile(self, document, image_meta=None):
                return json.dumps(document, sort_keys=True).encode()
        brand = self.db.save_brand_profile("Brand", PROFILE)
        pid = self.db.create_project("Campaign", brand_version_id=brand["id"])
        self.cid = self.db.create_concept(BRIEF, project_id=pid)
        vid = self.version(effective_profile=PROFILE)
        with patch.dict(app._state, {"store": self.db, "render": EchoRender()}, clear=True), \
                patch.dict(os.environ, {}, clear=True):
            client = TestClient(app.app)
            before = client.get(f"/versions/{vid}/document.sla")
            self.assertEqual(before.status_code, 200)
            updated = deepcopy(PROFILE)
            updated["swatches"][0]["values"] = [1, 2, 3, 4]
            next_brand = self.db.save_brand_profile("Brand", updated)
            self.db.update_project(pid, brand_version_id=next_brand["id"], overrides={"add": {"fonts": ["New"]}})
            app._state["profile"] = updated
            after = client.get(f"/versions/{vid}/document.sla")
            self.assertEqual(before.content, after.content)
            bundle = client.get(f"/versions/{vid}/bundle.zip")
            self.assertEqual(bundle.status_code, 200)
            z = zipfile.ZipFile(io.BytesIO(bundle.content))
            self.assertEqual(json.loads(z.read(f"ide8-{vid[:8]}/profile.json")), PROFILE)

    def test_unverifiable_legacy_exports_refuse_but_proof_and_json_remain(self):
        from fastapi.testclient import TestClient
        import app
        vid = self.version(proof_png=b"original-proof")
        with patch.dict(app._state, {"store": self.db, "render": FakeRender()}, clear=True):
            client = TestClient(app.app)
            for path in ("document.sla", "bundle.zip"):
                r = client.get(f"/versions/{vid}/{path}")
                self.assertEqual(r.status_code, 409)
                self.assertEqual(r.json()["detail"]["code"], "missing-profile-snapshot")
            self.assertEqual(client.post(f"/versions/{vid}/mutate", json={"instruction": "refine"}).status_code, 409)
            self.assertEqual(client.get(f"/versions/{vid}/document.json").status_code, 200)
            self.assertEqual(client.get(f"/versions/{vid}/proof.png").content, b"original-proof")

    def test_template_render_uses_source_snapshot_after_brand_head_changes(self):
        import app
        vid = self.version(effective_profile=PROFILE)
        tid = self.db.create_template("locked-source", vid, valid_doc(),
                {"slots": {"headline": {"kind": "text", "item": "headline"}}},
                PROFILE["name"], "0.1")
        self.db.save_brand_profile(PROFILE["name"], {**PROFILE, "fonts": ["Wrong Font"]})
        rows = [{"headline": "NEW CAMPAIGN"}]
        run = self.db.create_template_run(tid, rows)
        render = FakeRender()
        with patch.dict(app._state, {"store": self.db, "render": render}, clear=True):
            app._run_template_rows(run, self.db.get_template(tid), rows, package=False)
        self.assertEqual(self.db.get_template_run(run)["results"][0]["status"], "ok")
        self.assertEqual(render.compiled[0][0]["swatches"], PROFILE["swatches"])


if __name__ == "__main__":
    unittest.main()
