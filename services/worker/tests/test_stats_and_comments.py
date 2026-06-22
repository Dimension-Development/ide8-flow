"""ADM-1 usage_stats aggregation + REV-3 comment thread store methods."""

import sys
import tempfile
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from store import DocStore  # noqa: E402


def temp_store():
    return DocStore(Path(tempfile.mkdtemp()) / "test.db")


def usage(model, inp, outp, cost):
    """A minimal Meter.report()-shaped usage blob with one event."""
    return {
        "calls": 1, "input_tokens": inp, "output_tokens": outp,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        "cost_usd": cost,
        "events": [{
            "model": model, "purpose": "emit",
            "input_tokens": inp, "output_tokens": outp,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        }],
    }


def report(errors=(), warnings=()):
    return {"ok": not errors,
            "errors": [{"code": c, "path": "/", "message": c} for c in errors],
            "warnings": [{"code": c, "path": "/", "message": c}
                         for c in warnings]}


class TestUsageStats(unittest.TestCase):

    def _seed(self):
        s = temp_store()
        a = s.create_concept({"t": "a"}, "Hero split", job_id="J1")
        b = s.create_concept({"t": "b"}, "Framed", job_id="J1")
        c = s.create_concept({"t": "c"}, "Stacked")  # no job
        v1 = s.add_version(a, {"x": 1}, schema_version="0.1",
                           prompt_pack="0.1", validation=report(),
                           usage=usage("claude-sonnet-4-6", 1000, 500, 0.50))
        s.add_version(a, {"x": 2}, schema_version="0.1", prompt_pack="0.1",
                      validation=report(errors=["low-contrast"],
                                        warnings=["safe-zone"]),
                      usage=usage("claude-opus-4-8", 2000, 1000, 1.00),
                      approved=True, origin="mutation", parent_version_id=v1)
        s.add_version(b, {"x": 3}, schema_version="0.1", prompt_pack="0.1",
                      validation=report(errors=["out-of-bounds",
                                                "low-contrast"]),
                      usage=usage("claude-sonnet-4-6", 500, 200, 0.25))
        s.add_version(c, {"x": 4}, schema_version="0.1", prompt_pack="0.1",
                      validation=report(),
                      usage=usage("claude-opus-4-8", 300, 100, 0.30))
        return s

    def test_global_rollup(self):
        st = self._seed().usage_stats()
        self.assertEqual(st["scope"], "global")
        self.assertEqual(st["concepts"], 3)
        self.assertEqual(st["versions"], 4)
        self.assertEqual(st["versions_by_origin"],
                         {"generation": 3, "mutation": 1})
        self.assertEqual(st["approved_versions"], 1)
        self.assertEqual(st["llm_calls"], 4)
        self.assertAlmostEqual(st["cost_usd_total"], 2.05, places=4)
        self.assertEqual(st["tokens"]["input"], 3800)
        self.assertEqual(st["tokens"]["output"], 1800)

    def test_cost_by_model(self):
        st = self._seed().usage_stats()
        by = {m["model"]: m for m in st["cost_by_model"]}
        self.assertEqual(set(by), {"claude-sonnet-4-6", "claude-opus-4-8"})
        self.assertEqual(by["claude-sonnet-4-6"]["calls"], 2)
        self.assertEqual(by["claude-opus-4-8"]["calls"], 2)
        self.assertTrue(all(m["priced"] for m in st["cost_by_model"]))
        # sonnet (3/15 $/MTok): (1500*3 + 700*15)/1e6 = 0.015
        self.assertAlmostEqual(by["claude-sonnet-4-6"]["cost_usd"], 0.015,
                               places=4)

    def test_validation_by_rule(self):
        v = self._seed().usage_stats()["validation"]
        self.assertEqual(v["versions_with_errors"], 2)
        self.assertEqual(v["errors_by_code"],
                         {"low-contrast": 2, "out-of-bounds": 1})
        self.assertEqual(v["warnings_by_code"], {"safe-zone": 1})

    def test_per_job_scope(self):
        st = self._seed().usage_stats(job_id="J1")
        self.assertEqual(st["scope"], "job")
        self.assertEqual(st["concepts"], 2)
        self.assertEqual(st["versions"], 3)
        self.assertAlmostEqual(st["cost_usd_total"], 1.75, places=4)
        self.assertEqual(st["validation"]["errors_by_code"],
                         {"low-contrast": 2, "out-of-bounds": 1})

    def test_unpriced_model_flagged_not_crashing(self):
        s = temp_store()
        cid = s.create_concept({"t": "x"}, "")
        s.add_version(cid, {"x": 1}, schema_version="0.1", prompt_pack="0.1",
                      validation=report(),
                      usage=usage("claude-retired-9", 100, 100, 0.0))
        m = s.usage_stats()["cost_by_model"][0]
        self.assertEqual(m["model"], "claude-retired-9")
        self.assertFalse(m["priced"])      # no price entry
        self.assertEqual(m["cost_usd"], 0.0)  # tokens counted, cost excluded
        self.assertEqual(m["input_tokens"], 100)


class TestComments(unittest.TestCase):

    def test_thread_lifecycle(self):
        s = temp_store()
        cid = s.create_concept({"t": "a"}, "")
        vid = s.add_version(cid, {"x": 1}, schema_version="0.1",
                            prompt_pack="0.1", validation=report())
        c = s.add_comment(cid, "tighten the legal line", author="designer",
                          version_id=vid)
        self.assertEqual(c["author"], "designer")
        self.assertEqual(c["version_id"], vid)
        self.assertFalse(c["resolved"])
        self.assertEqual(c["anchor_name"], None)

        self.assertEqual(len(s.list_comments(cid)), 1)
        self.assertTrue(s.set_comment_resolved(c["id"], True))
        self.assertTrue(s.get_comment(c["id"])["resolved"])
        self.assertTrue(s.set_comment_resolved(c["id"], False))
        self.assertFalse(s.get_comment(c["id"])["resolved"])

    def test_unscoped_helpers(self):
        s = temp_store()
        self.assertEqual(s.list_comments("nope"), [])
        self.assertIsNone(s.get_comment("nope"))
        self.assertFalse(s.set_comment_resolved("nope", True))

    def test_comment_without_version(self):
        s = temp_store()
        cid = s.create_concept({"t": "a"}, "")
        c = s.add_comment(cid, "love it", author="designer")
        self.assertIsNone(c["version_id"])


if __name__ == "__main__":
    unittest.main()
