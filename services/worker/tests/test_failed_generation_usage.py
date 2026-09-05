"""Paid work must remain accounted for when a later model/render call fails."""

import copy
import tempfile
import unittest
from pathlib import Path

from test_generation_loop import (
    BRIEF, PACK, PROFILE, SCHEMA_JSON, SCHEMA_PATH, FakeRender,
    ScriptedClient, critique_resp, emit_resp, invalid_doc, run, valid_doc,
)
from test_stats_and_comments import usage
from generation.loop import GenConfig
from generation.service import generate_and_store
from store import DocStore


class RaisingClient(ScriptedClient):
    def create(self, **kwargs):
        response = super().create(**kwargs)
        if isinstance(response, Exception):
            raise response
        return response


class RaisingRender(FakeRender):
    def __init__(self, stage, on_call=1):
        super().__init__()
        self.stage = stage
        self.on_call = on_call
        self.compiles = self.proofs = 0

    def compile(self, document, image_meta=None):
        self.compiles += 1
        if self.stage == "compile" and self.compiles == self.on_call:
            raise RuntimeError("compile unavailable")
        return super().compile(document, image_meta)

    def proof_meta(self, sla_bytes, dpi=120, assets=None):
        self.proofs += 1
        if self.stage == "proof" and self.proofs == self.on_call:
            raise RuntimeError("proof unavailable")
        return super().proof_meta(sla_bytes, dpi=dpi, assets=assets)


class TestInterruptedGeneration(unittest.TestCase):
    def test_emit_exception_retains_paid_invalid_attempt_and_usage(self):
        r = run(RaisingClient([
            emit_resp(invalid_doc()), RuntimeError("provider unavailable")]),
            FakeRender())
        self.assertIsNone(r.document)
        self.assertIn("provider unavailable", r.error)
        self.assertEqual(r.usage["calls"], 1)
        self.assertGreater(r.usage["cost_usd"], 0)
        self.assertEqual(r.model_history, [GenConfig().fast_model])
        attempts = r.validation["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["emitted_document"], invalid_doc())
        self.assertEqual(attempts[1]["stage"], "emit")
        self.assertEqual(attempts[1]["validation"]["errors"][0]["code"],
                         "generation-exception")

    def test_render_exceptions_retain_successful_emit_spend(self):
        for stage in ("compile", "proof"):
            with self.subTest(stage=stage):
                r = run(RaisingClient([emit_resp(valid_doc())]),
                        RaisingRender(stage))
                self.assertIsNone(r.document)
                self.assertIsNone(r.proof_png_b64)
                self.assertEqual(r.usage["calls"], 1)
                self.assertGreater(r.usage["cost_usd"], 0)
                self.assertFalse(r.validation["ok"])
                attempt = r.validation["attempts"][0]
                self.assertEqual(attempt["stage"], stage)
                self.assertTrue(attempt["preflight_validation"]["ok"])
                self.assertEqual(attempt["emitted_document"], valid_doc())

    def test_critique_exception_keeps_rendered_candidate_unapproved(self):
        r = run(RaisingClient([
            emit_resp(valid_doc()), RuntimeError("critique unavailable")]),
            FakeRender())
        self.assertEqual(r.document, valid_doc())
        self.assertEqual(r.proof_png_b64, "UE5HZmFrZQ==")
        self.assertTrue(r.validation["ok"])
        self.assertFalse(r.approved)
        self.assertIsNone(r.critique)
        self.assertEqual(r.usage["calls"], 1)
        self.assertEqual(r.validation["attempts"][0]["stage"], "critique")

    def test_later_proof_exception_does_not_replace_prior_candidate(self):
        changed = copy.deepcopy(valid_doc())
        changed["pages"][0]["items"][0]["frame"][0] = 50
        r = run(RaisingClient([
            emit_resp(valid_doc()), critique_resp(False), emit_resp(changed)]),
            RaisingRender("proof", on_call=2))
        self.assertEqual(r.document, valid_doc())
        self.assertEqual(r.proof_png_b64, "UE5HZmFrZQ==")
        self.assertTrue(r.validation["ok"])
        self.assertFalse(r.critique["approve"])
        self.assertEqual(r.usage["calls"], 3)
        self.assertEqual(r.validation["attempts"][1]["emitted_document"], changed)
        self.assertEqual(r.validation["attempts"][1]["stage"], "proof")

    def test_service_persists_full_failed_usage_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DocStore(Path(tmp) / "test.db")
            result = generate_and_store(
                BRIEF, n=1, store=store,
                client=RaisingClient([emit_resp(invalid_doc()),
                                      RuntimeError("provider unavailable")]),
                render=FakeRender(), pack=PACK, schema_json=SCHEMA_JSON,
                schema_path=SCHEMA_PATH, profile=PROFILE, job_id="failed-job")
            summary = result["concepts"][0]
            self.assertIsNone(summary["version_id"])
            failure = store.get_concept(summary["concept_id"])["failure"]
            self.assertEqual(failure["iterations"], 2)
            self.assertEqual(failure["usage"]["calls"], 1)
            self.assertEqual(failure["cost_usd"], result["total_cost_usd"])
            stats = store.usage_stats(job_id="failed-job")
            self.assertEqual(stats["versions"], 0)
            self.assertEqual(stats["llm_calls"], 1)
            self.assertAlmostEqual(stats["cost_usd_total"],
                                   result["total_cost_usd"], places=4)


class TestFailureStats(unittest.TestCase):
    def test_failure_spend_is_scoped_without_fake_versions_or_double_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DocStore(Path(tmp) / "test.db")
            project1 = store.create_project("one")
            project2 = store.create_project("two")
            metered = usage("claude-sonnet-4-6", 1000, 500, 0.0105)
            metered["cache_read_input_tokens"] = 100
            metered["cache_creation_input_tokens"] = 200
            metered["events"][0].update(cache_read_input_tokens=100,
                                         cache_creation_input_tokens=200)
            metered["cost_usd"] = 0.01128
            failed = store.create_concept({}, job_id="J1", project_id=project1)
            store.set_concept_failure(failed, {"error": "render failed",
                                               "usage": metered,
                                               "cost_usd": 0.01128})
            old = store.create_concept({}, job_id="J1", project_id=project1)
            store.set_concept_failure(old, {"error": "old failure",
                                            "model_history": ["unknown"],
                                            "cost_usd": 0.4})
            successful = store.create_concept({}, job_id="J1", project_id=project1)
            # Deliberately stale failure metadata must not duplicate a version's spend.
            store.set_concept_failure(successful, {"usage": metered,
                                                   "cost_usd": 0.01128})
            store.add_version(successful, valid_doc(), schema_version="0.1",
                              prompt_pack="0.1", validation={"ok": True,
                              "errors": [], "warnings": []}, usage=metered,
                              approved=True)
            other = store.create_concept({}, job_id="J2", project_id=project2)
            store.set_concept_failure(other, {"usage": usage(
                "claude-opus-4-8", 2000, 1000, 0.035), "cost_usd": 0.035})
            for scope in ({"job_id": "J1"}, {"project_id": project1}):
                with self.subTest(scope=scope):
                    stats = store.usage_stats(**scope)
                    self.assertEqual(stats["concepts"], 3)
                    self.assertEqual(stats["versions"], 1)
                    self.assertEqual(stats["versions_by_origin"], {"generation": 1})
                    self.assertEqual(stats["approved_versions"], 1)
                    self.assertEqual(stats["llm_calls"], 2)
                    self.assertAlmostEqual(stats["cost_usd_total"], 0.4226)
                    self.assertEqual(stats["tokens"], {"input": 2000,
                                     "output": 1000, "cache_read": 200,
                                     "cache_creation": 400})
                    self.assertEqual(len(stats["cost_by_model"]), 1)
                    self.assertEqual(stats["cost_by_model"][0]["calls"], 2)
                    self.assertEqual(stats["cost_by_model"][0]["cost_usd"], 0.0226)
                    self.assertEqual(stats["validation"]["versions_with_errors"], 0)
            global_stats = store.usage_stats()
            self.assertEqual(global_stats["llm_calls"], 3)
            self.assertAlmostEqual(global_stats["cost_usd_total"], 0.4576)
            self.assertEqual(len(global_stats["cost_by_model"]), 2)
            self.assertEqual(store.usage_stats(job_id="missing")["cost_usd_total"], 0)
            self.assertEqual(store.usage_stats(project_id=project2)["versions"], 0)


if __name__ == "__main__":
    unittest.main()
