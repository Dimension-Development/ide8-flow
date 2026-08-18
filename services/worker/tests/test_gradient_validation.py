"""Gradient-aware deterministic validation and template binding (T06)."""

import copy
import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from brand import merge_profile  # noqa: E402
from templates import apply_bindings  # noqa: E402
from validation import brand_rules, contrast  # noqa: E402


PROFILE = {
    "swatches": [
        {"name": "Ink", "space": "rgb", "values": [0, 0, 0]},
        {"name": "Paper", "space": "rgb", "values": [255, 255, 255]},
        {"name": "Mid", "space": "rgb", "values": [128, 128, 128]},
    ],
    "rules": {"contrastFloor": 4.5},
}


def gradient(*colours):
    return {"type": "linear-gradient", "start": [0, 0], "end": [1, 0],
            "stops": [{"at": i / (len(colours) - 1), "color": colour}
                      for i, colour in enumerate(colours)]}


def document(background, opacity=None):
    bg = {"type": "shape", "name": "background", "frame": [0, 0, 100, 100],
          "fill": background}
    if opacity is not None:
        bg["opacity"] = opacity
    return {
        "version": "0.2",
        "charStyles": [{"name": "copy", "font": "Test", "size": 12,
                        "color": "Paper"}],
        "paraStyles": [{"name": "body", "charStyle": "copy"}],
        "pages": [{"items": [bg, {
            "type": "text", "name": "copy", "frame": [10, 10, 80, 40],
            "paragraphs": [{"style": "body", "text": "Readable"}],
        }]}],
    }


class TestGradientValidation(unittest.TestCase):

    def test_worst_gradient_stop_controls_text_contrast(self):
        # Paper text is fine on Ink but fails against the Paper stop.
        errors = contrast.check(merge_profile(document(gradient("Ink", "Paper")), PROFILE),
                                PROFILE)
        self.assertEqual([e["code"] for e in errors], ["low-contrast"])

    def test_transparent_shape_is_conservatively_composited_over_paper(self):
        opaque = contrast.check(merge_profile(document("Ink"), PROFILE), PROFILE)
        translucent = contrast.check(
            merge_profile(document("Ink", opacity=0.5), PROFILE), PROFILE)
        self.assertEqual(opaque, [])
        self.assertEqual([e["code"] for e in translucent], ["low-contrast"])

    def test_unknown_gradient_stop_is_structured_validation_error(self):
        raw = document(gradient("Ink", "Ghost"))
        errors = brand_rules.check(raw, PROFILE)
        self.assertTrue(any(e["code"] == "unknown-swatch" and
                            e["path"].endswith("stops[1].color")
                            for e in errors))

    def test_profile_merge_keeps_gradient_definition_intact(self):
        raw = document(gradient("Ink", "Paper"))
        before = copy.deepcopy(raw["pages"][0]["items"][0]["fill"])
        merged = merge_profile(raw, PROFILE)
        self.assertEqual(merged["pages"][0]["items"][0]["fill"], before)

    def test_swatch_slot_replaces_the_complete_gradient_fill(self):
        raw = document(gradient("Ink", "Paper"))
        raw["swatches"] = copy.deepcopy(PROFILE["swatches"])
        bindings = {"slots": {"background": {
            "kind": "swatch", "item": "background", "target": "fill"}}}
        bound, errors = apply_bindings(raw, bindings, {"background": "Mid"})
        self.assertEqual(errors, [])
        self.assertEqual(bound["pages"][0]["items"][0]["fill"], "Mid")


if __name__ == "__main__":
    unittest.main()
