"""Structural compiler checks for the permanent synthetic agency-card fixture."""

import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RENDER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RENDER_ROOT))

import sla_compiler as C  # noqa: E402

FIXTURE = RENDER_ROOT / "tests" / "fixtures" / "agency-card-0.2"
DOCUMENT = json.loads((FIXTURE / "document.json").read_text())
META = {"assets/synthetic-model-cutout.png": {"width": 400, "height": 600}}
TEMPLATE = RENDER_ROOT / "template.sla"


def compiled_root():
    return ET.fromstring(C.compile_to_bytes(DOCUMENT, TEMPLATE, image_meta=META)).find("DOCUMENT")


class TestAgencyCardFixture(unittest.TestCase):

    def test_compile_is_byte_stable(self):
        self.assertEqual(C.compile_to_bytes(DOCUMENT, TEMPLATE, image_meta=META),
                         C.compile_to_bytes(DOCUMENT, TEMPLATE, image_meta=META))

    def test_card_geometry_and_requested_constructions_are_present(self):
        self.assertEqual(DOCUMENT["page"]["size"], [425.19685, 425.19685])
        self.assertEqual(DOCUMENT["page"]["bleed"], 8.503937)
        self.assertEqual(DOCUMENT["page"]["margins"], [17.007874] * 4)
        items = DOCUMENT["pages"][0]["items"]
        names = {item["name"] for item in items}
        self.assertTrue({"gradient-background", "synthetic-model-cutout", "headline",
                         "body-copy", "logo-clear-space-placeholder", "cut-contour-test"}
                        <= names)
        stars = [item for item in items if item["name"].startswith("rounded-star-")]
        self.assertEqual(len(stars), 2)
        self.assertTrue(all(item["type"] == "shape" and item["opacity"] == 0.5
                            and " C" in item["d"] for item in stars))

    def test_compiled_sla_contains_gradient_opacity_image_crop_and_spot_path(self):
        objects = {item.get("ANNAME"): item for item in compiled_root().findall("PAGEOBJECT")}
        background = objects["gradient-background"]
        self.assertEqual(background.get("GRTYP"), "6")
        self.assertEqual([stop.get("NAME") for stop in background.findall("CSTOP")],
                         ["SyntheticCoral", "SyntheticLime"])
        self.assertEqual(objects["rounded-star-top"].get("TransValue"), "0.5")
        image = objects["synthetic-model-cutout"]
        self.assertEqual((image.get("SCALETYPE"), image.get("RATIO")), ("1", "1"))
        self.assertNotEqual(image.get("LOCALX"), "0")
        self.assertEqual(objects["cut-contour-test"].get("PCOLOR2"), "CutContour")
        self.assertFalse(objects["cut-contour-test"].get("path", "").endswith("Z"))


if __name__ == "__main__":
    unittest.main()
