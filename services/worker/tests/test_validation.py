"""Validation layer tests (VAL-1..4) + brand merge (BRAND-2).

    python3 -m unittest discover services/worker/tests
Requires: pip install -r services/worker/requirements.txt (jsonschema)
"""

import copy
import json
import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from brand import merge_profile  # noqa: E402
from validation import run_validation  # noqa: E402

SCHEMA = REPO_ROOT / "schema" / "document-0.1.schema.json"
EXAMPLE = REPO_ROOT / "services" / "render" / "examples" / "example.json"
PROFILE = WORKER_ROOT / "examples" / "brand_profile.json"


def load(p):
    return json.loads(Path(p).read_text())


def codes(report):
    return {e["code"] for e in report["errors"]}


def warn_codes(report):
    return {w["code"] for w in report["warnings"]}


class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        self.doc = load(EXAMPLE)
        self.profile = load(PROFILE)

    def validate(self, doc=None):
        return run_validation(doc or self.doc, self.profile, SCHEMA)

    def test_example_document_is_clean(self):
        report = self.validate()
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["ok"])

    # ---- VAL-1 schema ----

    def test_hallucinated_key_fails_schema(self):
        self.doc["pages"][0]["items"][0]["opacity"] = 0.5
        report = self.validate()
        self.assertIn("schema", codes(report))
        self.assertFalse(report["ok"])

    def test_fill_on_path_fails_schema(self):
        self.doc["pages"][0]["items"].append({
            "type": "path", "frame": [0, 0, 50, 50], "d": "M0 0 L50 50",
            "fill": "BrandRed",
            "stroke": {"color": "CutContour", "width": 0.5}})
        report = self.validate()
        self.assertIn("schema", codes(report))

    def test_schema_failure_short_circuits(self):
        report = self.validate({"version": "9.9"})
        self.assertTrue(all(e["code"] == "schema" for e in report["errors"]))

    # ---- VAL-2 brand ----

    def test_off_brand_swatch(self):
        self.doc["swatches"].append(
            {"name": "RogueTeal", "space": "cmyk", "values": [60, 0, 30, 0]})
        self.assertIn("off-brand-swatch", codes(self.validate()))

    def test_swatch_redefinition(self):
        self.doc["swatches"][0]["values"] = [0, 0, 0, 100]  # BrandRed → black
        self.assertIn("off-brand-swatch", codes(self.validate()))

    def test_off_brand_font(self):
        self.doc["charStyles"][0]["font"] = "Comic Sans MS Regular"
        self.assertIn("off-brand-font", codes(self.validate()))

    def test_type_too_small(self):
        self.doc["charStyles"][2]["size"] = 5
        self.assertIn("type-too-small", codes(self.validate()))

    def test_missing_mandatory_element(self):
        self.profile["rules"]["mandatoryElements"] = ["legal-line"]
        self.assertIn("missing-mandatory", codes(self.validate()))

    # ---- VAL-3 geometry ----

    def test_out_of_bounds(self):
        self.doc["pages"][0]["items"][0]["frame"] = [-50, 0, 700, 100]
        self.assertIn("out-of-bounds", codes(self.validate()))

    def test_closed_cut_path(self):
        for pg in self.doc["pages"]:
            for item in pg["items"]:
                if item["type"] == "path":
                    item["d"] = item["d"] + " Z"
        self.assertIn("closed-cut-path", codes(self.validate()))

    def test_safe_zone_warning(self):
        self.doc["pages"][0]["items"][1]["frame"] = [2, 80, 515, 120]
        report = self.validate()
        self.assertIn("safe-zone", warn_codes(report))
        self.assertTrue(report["ok"])  # warnings don't fail validation

    # ---- VAL-4 contrast ----

    def test_low_contrast_text_on_white(self):
        # Cream text with no panel behind it — the invisible-text class.
        self.doc["pages"][1]["items"][1]["paragraphs"][0]["style"] = "Subhead"
        report = self.validate()
        self.assertIn("low-contrast", codes(report))

    def test_contrast_uses_topmost_underlying_fill(self):
        # Headline sits on the BrandRed panel: Cream-on-red passes the floor.
        report = self.validate()
        self.assertNotIn("low-contrast", codes(report))


class TestMerge(unittest.TestCase):

    def test_profile_is_authoritative_on_conflict(self):
        doc = {"swatches": [{"name": "BrandRed", "space": "cmyk",
                             "values": [0, 0, 0, 100]}]}
        profile = load(PROFILE)
        merged = merge_profile(doc, profile)
        red = next(s for s in merged["swatches"] if s["name"] == "BrandRed")
        self.assertEqual(red["values"], [0, 90, 78, 8])

    def test_document_extras_survive(self):
        doc = {"charStyles": [{"name": "Local", "font": "Liberation Sans Bold",
                               "size": 30}]}
        merged = merge_profile(doc, load(PROFILE))
        self.assertIn("Local", [s["name"] for s in merged["charStyles"]])


if __name__ == "__main__":
    unittest.main()
