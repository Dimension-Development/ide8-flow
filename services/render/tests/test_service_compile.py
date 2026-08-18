"""Service acceptance of the backwards-compatible /compile envelope (T04)."""

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RENDER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RENDER_ROOT))

from service.app import compile_document  # noqa: E402


class TestCompileEnvelope(unittest.TestCase):

    def test_envelope_forwards_dimensions_to_compiler(self):
        doc = {
            "version": "0.2", "page": {"size": [300, 200]},
            "pages": [{"items": [{
                "type": "image", "frame": [0, 0, 140, 120],
                "src": "assets/source.png", "fit": "cover",
                "focus": [0.625, 0.5],
            }]}],
        }
        response = compile_document({"document": doc, "image_meta": {
            "assets/source.png": {"width": 400, "height": 200}}})
        self.assertEqual(response.status_code, 200)
        item = ET.fromstring(response.body).find(".//PAGEOBJECT")
        self.assertEqual(item.get("LOCALSCX"), "0.6")
        self.assertEqual(item.get("LOCALX"), "-133.333333")


if __name__ == "__main__":
    unittest.main()
