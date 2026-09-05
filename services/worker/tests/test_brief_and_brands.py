"""Brief-derived validation (VAL-5 copy integrity + brief mandatory elements)
and the brand-profile store (BRAND-3 de-singleton).

    python3 -m unittest discover services/worker/tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from store import DocStore  # noqa: E402
from validation import brief_checks  # noqa: E402

BRIEF = WORKER_ROOT / "examples" / "harvest-edit" / "brief.json"
PROFILE = WORKER_ROOT / "examples" / "harvest-edit" / "brand_profile.json"


def load(p):
    return json.loads(Path(p).read_text())


def text_item(name, text):
    return {"type": "text", "name": name,
            "paragraphs": [{"style": "Body", "text": text}]}


def image_item(name):
    return {"type": "image", "name": name, "src": name}


class TestBriefChecks(unittest.TestCase):

    def setUp(self):
        self.brief = load(BRIEF)
        c = self.brief["copy"]
        # a document that satisfies every hard brief requirement
        self.doc = {"pages": [{"items": [
            text_item("headline", c["headline"]),
            text_item("subhead", c["subhead"]),
            text_item("body", " ".join(c["body"])),
            text_item("legal-line", c["legal"]),
            image_item("meridian-logo"),
            image_item("harvest-recipe-qr"),
        ]}]}
        self.doc["page"] = dict(self.brief["format"])

    def errs(self, doc):
        e, _ = brief_checks.check(doc, self.brief)
        return e

    def warns(self, doc):
        _, w = brief_checks.check(doc, self.brief)
        return w

    def test_clean_document_has_no_errors(self):
        self.assertEqual(self.errs(self.doc), [])

    def test_missing_mandatory_qr_fails(self):
        self.doc["pages"][0]["items"] = [
            it for it in self.doc["pages"][0]["items"]
            if it.get("name") != "harvest-recipe-qr"]
        e = self.errs(self.doc)
        self.assertTrue(any(x["code"] == "missing-mandatory"
                            and "harvest-recipe-qr" in x["message"] for x in e))

    def test_dropped_legal_is_a_hard_error(self):
        self.doc["pages"][0]["items"] = [
            it for it in self.doc["pages"][0]["items"]
            if it.get("name") != "legal-line"]
        e = self.errs(self.doc)
        self.assertTrue(any(x["code"] == "missing-copy"
                            and x["path"] == "copy.legal" for x in e))

    def test_paraphrased_headline_is_a_hard_error(self):
        self.doc["pages"][0]["items"][0] = text_item("headline",
                                                     "Harvest Edit")
        e = self.errs(self.doc)
        self.assertTrue(any(x["path"] == "copy.headline" for x in e))

    def test_smart_quote_substitution_still_matches(self):
        # body copy with curly apostrophes must NOT false-fail
        smart = self.brief["copy"]["legal"].replace("'", "’")
        self.doc["pages"][0]["items"][3] = text_item("legal-line", smart)
        self.assertEqual([x for x in self.errs(self.doc)
                          if x["path"] == "copy.legal"], [])

    def test_subhead_and_body_are_warnings_not_errors(self):
        self.doc["pages"][0]["items"] = [
            it for it in self.doc["pages"][0]["items"]
            if it.get("name") not in ("subhead", "body")]
        self.assertEqual(self.errs(self.doc), [])  # still no hard errors
        codes = {w["code"] for w in self.warns(self.doc)}
        self.assertIn("missing-copy", codes)

    def test_no_brief_means_no_checks(self):
        e, w = brief_checks.check({"pages": []}, None)
        self.assertEqual((e, w), ([], []))


class TestBrandStore(unittest.TestCase):

    def setUp(self):
        self.db = DocStore(tempfile.mktemp(suffix=".db"))
        self.profile = load(PROFILE)

    def test_save_list_get_delete(self):
        self.db.save_brand_profile(self.profile["name"], self.profile)
        names = [b["name"] for b in self.db.list_brand_profiles()]
        self.assertEqual(names, ["Meridian Market"])
        got = self.db.get_brand_profile("Meridian Market")
        self.assertEqual(got["profile"]["rules"]["contrastFloor"], 4.0)
        self.assertEqual(len(self.db.list_brand_profiles()[0]["swatches"]), 9)
        self.assertTrue(self.db.delete_brand_profile("Meridian Market"))
        self.assertEqual(self.db.list_brand_profiles(), [])

    def test_upsert_updates_in_place(self):
        self.db.save_brand_profile(self.profile["name"], self.profile)
        self.db.save_brand_profile(self.profile["name"],
                                   {**self.profile, "version": "2026.2"})
        self.assertEqual(len(self.db.list_brand_profiles()), 1)
        self.assertEqual(
            self.db.get_brand_profile("Meridian Market")["profile"]["version"],
            "2026.2")

    def test_unknown_returns_none(self):
        self.assertIsNone(self.db.get_brand_profile("nope"))
        self.assertFalse(self.db.delete_brand_profile("nope"))


class TestAssetUploadGuard(unittest.TestCase):
    """Gap D4: /assets must reject oversized images (dimension + byte size)."""

    def setUp(self):
        import io
        import os
        from fastapi.testclient import TestClient
        from PIL import Image
        import app as appmod
        self.app = appmod
        os.environ["WORKER_DB"] = tempfile.mktemp(suffix=".db")
        appmod._state.pop("store", None)  # force the temp DB
        appmod.MAX_ASSET_DIM = 4096
        appmod.MAX_ASSET_BYTES = 16 * 1024 * 1024
        self.client = TestClient(appmod.app)

        def png_b64(w, h):
            buf = io.BytesIO()
            Image.new("RGB", (w, h), (200, 80, 40)).save(buf, "PNG")
            import base64 as b
            return b.b64encode(buf.getvalue()).decode()

        self.big_dim = png_b64(5000, 2)
        self.small = png_b64(8, 8)

    def test_oversized_dimension_rejected(self):
        r = self.client.post("/assets",
                             json={"name": "too-wide", "data_b64": self.big_dim})
        self.assertEqual(r.status_code, 413)

    def test_oversized_bytes_rejected(self):
        self.app.MAX_ASSET_BYTES = 50  # any real PNG exceeds this
        r = self.client.post("/assets",
                             json={"name": "too-big", "data_b64": self.small})
        self.assertEqual(r.status_code, 413)

    def test_within_limits_accepted(self):
        r = self.client.post("/assets",
                             json={"name": "ok-img", "data_b64": self.small})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
