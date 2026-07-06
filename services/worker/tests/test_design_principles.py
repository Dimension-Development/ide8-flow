"""DESIGN.md-style brand design principles: a markdown string stored as
profile.designPrinciples becomes its own system-prompt block (split out of
the machine-rules JSON) and the critique rubric references it. Division of
labour: interpretive direction only — machine-checkable rules stay in
profile.rules where validation enforces them."""

import json
import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from generation import prompts  # noqa: E402
from store import DocStore  # noqa: E402

from test_generation_loop import (  # noqa: E402
    FakeRender, ScriptedClient, critique_resp, emit_resp, valid_doc)

PRINCIPLES = "# X — design principles\n\nAsymmetry over centring."
PACK = {"system_text": "You are a designer."}
SCHEMA = {"type": "object"}


def profile(with_principles=True):
    p = {"name": "X", "swatches": [], "fonts": [],
         "rules": {"contrastFloor": 4.0}}
    if with_principles:
        p["designPrinciples"] = PRINCIPLES
    return p


class TestSystemAssembly(unittest.TestCase):

    def test_principles_get_their_own_block(self):
        blocks = prompts.build_system(PACK, SCHEMA, profile(), exemplar={})
        principle_blocks = [b for b in blocks if
                            "## Brand design principles" in b["text"]]
        self.assertEqual(len(principle_blocks), 1)
        self.assertIn("Asymmetry over centring", principle_blocks[0]["text"])

    def test_principles_are_split_out_of_the_machine_profile(self):
        blocks = prompts.build_system(PACK, SCHEMA, profile(), exemplar={})
        profile_block = next(b for b in blocks
                             if "## Brand profile" in b["text"])
        self.assertNotIn("designPrinciples", profile_block["text"])
        self.assertIn("contrastFloor", profile_block["text"])

    def test_no_principles_no_block(self):
        blocks = prompts.build_system(PACK, SCHEMA, profile(False),
                                      exemplar={})
        self.assertFalse(any("## Brand design principles" in b["text"]
                             for b in blocks))

    def test_cache_control_stays_on_the_final_block(self):
        # the cacheable-prefix contract: exactly one cache breakpoint, on
        # the last block, with or without principles
        for with_p in (True, False):
            blocks = prompts.build_system(PACK, SCHEMA, profile(with_p),
                                          exemplar={})
            flagged = [i for i, b in enumerate(blocks) if "cache_control" in b]
            self.assertEqual(flagged, [len(blocks) - 1])

    def test_critique_rubric_mentions_principles_only_when_present(self):
        brief = {"title": "t"}
        self.assertIn("design principles",
                      prompts.build_critique_message(brief, profile()))
        self.assertNotIn("design principles",
                         prompts.build_critique_message(brief, profile(False)))
        self.assertNotIn("design principles",
                         prompts.build_critique_message(brief))


class TestLoopCarriesPrinciples(unittest.TestCase):

    def test_generation_call_includes_principles_block(self):
        from brand import load_profile
        from generation.loop import generate_concept

        base = load_profile(WORKER_ROOT / "examples" / "brand_profile.json")
        prof = {**base, "designPrinciples": PRINCIPLES}
        schema = json.loads(
            (WORKER_ROOT.parents[1] / "schema"
             / "document-0.1.schema.json").read_text())
        pack = {**PACK, "exemplar": {}}
        client = ScriptedClient([emit_resp(valid_doc()),
                                 critique_resp(True)])
        r = generate_concept(
            {"title": "t"}, prof, "Type-led", client=client,
            render=FakeRender(), pack=pack, schema_json=schema,
            schema_path=str(WORKER_ROOT.parents[1] / "schema"
                            / "document-0.1.schema.json"))
        self.assertTrue(r.approved)
        system = client.calls[0]["system"]
        self.assertTrue(any("Asymmetry over centring" in b["text"]
                            for b in system))
        # critique turn cites the rubric
        critique_call = client.calls[1]
        texts = [c.get("text", "") for m in critique_call["messages"]
                 if isinstance(m.get("content"), list)
                 for c in m["content"] if isinstance(c, dict)]
        self.assertTrue(any("design principles" in t for t in texts))


class TestStoreSummary(unittest.TestCase):

    def test_summary_carries_principles(self):
        import tempfile
        s = DocStore(Path(tempfile.mkdtemp()) / "test.db")
        s.save_brand_profile("X", profile())
        self.assertEqual(s.list_brand_profiles()[0]["designPrinciples"],
                         PRINCIPLES)
        s.save_brand_profile("Y", profile(False))
        y = next(b for b in s.list_brand_profiles() if b["name"] == "Y")
        self.assertIsNone(y["designPrinciples"])


if __name__ == "__main__":
    unittest.main()
