"""Generation loop tests (GEN-1/3/5) with scripted fakes — no API calls.

    python3 -m unittest discover services/worker/tests
"""

import json
import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from brand import load_profile  # noqa: E402
from generation import prompts  # noqa: E402
from generation.loop import GenConfig, generate_concept  # noqa: E402

SCHEMA_PATH = str(REPO_ROOT / "schema" / "document-0.1.schema.json")
SCHEMA_JSON = json.loads(Path(SCHEMA_PATH).read_text())
PROFILE = load_profile(WORKER_ROOT / "examples" / "brand_profile.json")
PACK = prompts.load_pack("0.1")
PACK["exemplar"] = {}
BRIEF = json.loads(
    (WORKER_ROOT / "examples" / "brief.json").read_text())


# ---------------------------------------------------------------- fakes

class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


_ids = iter(range(1, 1000))


def usage(inp=1000, out=400):
    return Obj(input_tokens=inp, output_tokens=out,
               cache_read_input_tokens=0, cache_creation_input_tokens=0)


def emit_resp(document):
    return Obj(content=[Obj(type="tool_use", name="emit_document",
                            id="tu_%03d" % next(_ids), input=document)],
               usage=usage(), stop_reason="tool_use")


def critique_resp(approve, issues=None):
    return Obj(content=[Obj(type="tool_use", name="submit_critique",
                            id="tu_%03d" % next(_ids),
                            input={"approve": approve,
                                   "issues": issues or []})],
               usage=usage(), stop_reason="tool_use")


class ScriptedClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self  # client.messages.create -> self.create

    def create(self, **kwargs):
        snapshot = dict(kwargs)
        snapshot["messages"] = list(kwargs["messages"])  # loop mutates it
        self.calls.append(snapshot)
        return self._responses.pop(0)


class FakeRender:
    def __init__(self, overflow_rounds=None):
        self.overflow_rounds = list(overflow_rounds or [])

    def compile(self, document):
        return b"<SCRIBUSUTF8NEW/>"

    def proof_meta(self, sla_bytes, dpi=120):
        overflows = self.overflow_rounds.pop(0) if self.overflow_rounds else []
        return "UE5HZmFrZQ==", overflows


def valid_doc():
    return {
        "version": "0.1",
        "page": {"size": "A4", "margins": [12, 12, 12, 12], "bleed": 8.5},
        "charStyles": [{"name": "H", "font": "Liberation Sans Bold",
                        "size": 40, "color": "DeepInk"}],
        "paraStyles": [{"name": "HP", "charStyle": "H", "align": "left"}],
        "pages": [{"items": [
            {"type": "text", "name": "headline", "frame": [40, 40, 400, 200],
             "paragraphs": [{"style": "HP", "text": "SUMMER JUST LANDED"}]},
        ]}],
    }


def invalid_doc():
    doc = valid_doc()
    doc["version"] = "9.9"
    doc["pages"][0]["items"].append({"type": "blob", "frame": [0, 0, 1, 1]})
    return doc


def run(client, render, config=None):
    return generate_concept(
        BRIEF, PROFILE, "Type-led poster", client=client, render=render,
        pack=PACK, schema_json=SCHEMA_JSON, schema_path=SCHEMA_PATH,
        config=config)


# ---------------------------------------------------------------- tests

class TestLoop(unittest.TestCase):

    def test_first_try_approved(self):
        client = ScriptedClient([emit_resp(valid_doc()),
                                 critique_resp(True)])
        r = run(client, FakeRender())
        self.assertTrue(r.approved)
        self.assertEqual(r.iterations, 1)
        self.assertEqual(r.model_history, [GenConfig().fast_model])
        self.assertTrue(r.validation["ok"])
        self.assertIsNotNone(r.proof_png_b64)
        self.assertEqual(r.usage["calls"], 2)
        self.assertGreater(r.usage["cost_usd"], 0)

    def test_repair_loop_feeds_structured_errors_back(self):
        client = ScriptedClient([emit_resp(invalid_doc()),
                                 emit_resp(valid_doc()),
                                 critique_resp(True)])
        r = run(client, FakeRender())
        self.assertTrue(r.approved)
        self.assertEqual(r.iterations, 2)
        # the second emit call must have received the error report
        second_call_messages = client.calls[1]["messages"]
        repair = second_call_messages[-1]["content"][0]
        self.assertEqual(repair["type"], "tool_result")
        self.assertTrue(repair.get("is_error"))
        errors = json.loads(repair["content"])["errors"]
        self.assertTrue(all(e["code"] == "schema" for e in errors))
        self.assertIn("version", [e["path"] for e in errors])

    def test_overflow_is_hard_failure_before_vision(self):
        render = FakeRender(overflow_rounds=[
            [{"page": 1, "item": "headline"}], []])
        client = ScriptedClient([emit_resp(valid_doc()),
                                 emit_resp(valid_doc()),
                                 critique_resp(True)])
        r = run(client, render)
        self.assertTrue(r.approved)
        self.assertEqual(r.iterations, 2)
        repair = client.calls[1]["messages"][-1]["content"][0]
        self.assertIn("overflow", repair["content"])
        # no vision call was spent on the overflowing round: 3 calls total
        self.assertEqual(r.usage["calls"], 3)

    def test_escalates_to_strong_model_after_repeated_failures(self):
        cfg = GenConfig(escalate_after_failures=2)
        client = ScriptedClient([emit_resp(invalid_doc()),
                                 emit_resp(invalid_doc()),
                                 emit_resp(valid_doc()),
                                 critique_resp(True)])
        r = run(client, FakeRender(), cfg)
        self.assertTrue(r.approved)
        models = [c["model"] for c in client.calls]
        self.assertEqual(models[0], cfg.fast_model)
        self.assertEqual(models[1], cfg.fast_model)
        self.assertEqual(models[2], cfg.strong_model)
        self.assertIn(cfg.strong_model, r.model_history)

    def test_critique_revision_loop(self):
        client = ScriptedClient([
            emit_resp(valid_doc()),
            critique_resp(False, [{"issue": "headline too timid",
                                   "fix": "increase size, full-bleed panel"}]),
            emit_resp(valid_doc()),
            critique_resp(True)])
        r = run(client, FakeRender())
        self.assertTrue(r.approved)
        self.assertEqual(r.iterations, 2)
        # the revision request reached the model after the rejection
        revise = client.calls[2]["messages"][-1]["content"][0]
        self.assertEqual(revise["type"], "tool_result")
        self.assertIn("Revise", revise["content"])

    def test_cap_reached_returns_unapproved_with_artifacts(self):
        cfg = GenConfig(max_iterations=1)
        client = ScriptedClient([emit_resp(valid_doc()),
                                 critique_resp(False, [{"issue": "weak"}])])
        r = run(client, FakeRender(), cfg)
        self.assertFalse(r.approved)
        self.assertIsNotNone(r.document)
        self.assertIsNotNone(r.proof_png_b64)
        self.assertFalse(r.critique["approve"])

    def test_numeric_version_is_normalised_not_punished(self):
        # Live finding (11 Jun 2026): models emit version as the JSON
        # number 0.1; that must not cost a repair iteration.
        doc = valid_doc()
        doc["version"] = 0.1
        client = ScriptedClient([emit_resp(doc), critique_resp(True)])
        r = run(client, FakeRender())
        self.assertTrue(r.approved)
        self.assertEqual(r.iterations, 1)
        self.assertEqual(r.document["version"], "0.1")

    def test_forced_tool_choice_on_every_call(self):
        client = ScriptedClient([emit_resp(valid_doc()),
                                 critique_resp(True)])
        run(client, FakeRender())
        self.assertEqual(client.calls[0]["tool_choice"],
                         {"type": "tool", "name": "emit_document"})
        self.assertEqual(client.calls[1]["tool_choice"],
                         {"type": "tool", "name": "submit_critique"})


if __name__ == "__main__":
    unittest.main()
