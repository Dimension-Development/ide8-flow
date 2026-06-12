"""Asset pipeline tests (RND-5): sniffing, store, validation, staging."""

import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from assets import resolve_srcs, sniff, staged_relpath  # noqa: E402
from brand import load_profile  # noqa: E402
from store import DocStore  # noqa: E402
from validation import run_validation  # noqa: E402

from test_generation_loop import valid_doc  # noqa: E402

SCHEMA_PATH = str(REPO_ROOT / "schema" / "document-0.1.schema.json")
PROFILE = load_profile(WORKER_ROOT / "examples" / "brand_profile.json")


def make_png(width=120, height=80, rgb=(216, 51, 46)):
    """Minimal valid PNG, no dependencies."""
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(
            ">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height,
                                         8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def doc_with_image(src="logo-primary"):
    doc = valid_doc()
    doc["pages"][0]["items"].append({
        "type": "image", "name": "logo", "frame": [400, 700, 120, 80],
        "src": src, "fit": "frame"})
    return doc


class TestSniff(unittest.TestCase):

    def test_png_dimensions(self):
        mime, w, h = sniff(make_png(300, 150))
        self.assertEqual((mime, w, h), ("image/png", 300, 150))

    def test_unknown_format_rejected(self):
        self.assertEqual(sniff(b"not an image at all"), (None, None, None))


class TestAssetStore(unittest.TestCase):

    def setUp(self):
        self.store = DocStore(Path(tempfile.mkdtemp()) / "t.db")

    def test_roundtrip_with_dimensions(self):
        png = make_png()
        self.assertTrue(self.store.add_asset(
            "logo-primary", "logo.png", "image/png", 120, 80, png))
        a = self.store.get_asset("logo-primary")
        self.assertEqual((a["width"], a["height"]), (120, 80))
        self.assertEqual(a["data"], png)
        listed = self.store.list_assets()
        self.assertEqual(listed[0]["name"], "logo-primary")
        self.assertEqual(listed[0]["size"], len(png))

    def test_assets_are_write_once(self):
        self.store.add_asset("logo", "a.png", "image/png", 1, 1, b"x")
        self.assertFalse(
            self.store.add_asset("logo", "b.png", "image/png", 2, 2, b"y"))


class TestValidationAndStaging(unittest.TestCase):

    def test_unknown_asset_is_hard_failure(self):
        report = run_validation(doc_with_image("no-such-asset"), PROFILE,
                                SCHEMA_PATH, asset_names={"logo-primary"})
        self.assertIn("missing-asset", {e["code"] for e in report["errors"]})

    def test_known_asset_passes(self):
        report = run_validation(doc_with_image(), PROFILE, SCHEMA_PATH,
                                asset_names={"logo-primary"})
        self.assertEqual(report["errors"], [])

    def test_resolve_rewrites_src_and_collects_files(self):
        png = make_png()
        asset_map = {"logo-primary": {
            "name": "logo-primary", "mime": "image/png",
            "width": 120, "height": 80, "data": png}}
        staged, files = resolve_srcs(doc_with_image(), asset_map)
        rel = staged_relpath("logo-primary", "image/png")
        self.assertEqual(rel, "assets/logo-primary.png")
        item = staged["pages"][0]["items"][-1]
        self.assertEqual(item["src"], rel)
        self.assertEqual(files, {rel: png})
        # original untouched
        self.assertEqual(
            doc_with_image()["pages"][0]["items"][-1]["src"], "logo-primary")


if __name__ == "__main__":
    unittest.main()
