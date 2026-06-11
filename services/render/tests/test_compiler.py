"""Compiler unit tests: golden byte-compare, determinism, structured errors.

Run from the repo root or services/render:
    python3 -m unittest discover services/render/tests
"""

import copy
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RENDER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RENDER_ROOT))

import sla_compiler as C

TEMPLATE = str(RENDER_ROOT / "template.sla")
EXAMPLE = RENDER_ROOT / "examples" / "example.json"
GOLDEN_SLA = RENDER_ROOT / "tests" / "golden" / "out.sla"


def example_doc():
    return json.loads(EXAMPLE.read_text())


def minimal_doc():
    return {
        "version": "0.1",
        "page": {"size": "A4"},
        "swatches": [{"name": "Ink", "space": "cmyk", "values": [0, 0, 0, 100]}],
        "charStyles": [{"name": "C", "font": "Liberation Sans Regular",
                        "size": 12, "color": "Ink"}],
        "paraStyles": [{"name": "P", "charStyle": "C", "align": "left"}],
        "pages": [{"items": [
            {"type": "text", "name": "t", "frame": [10, 10, 100, 50],
             "paragraphs": [{"style": "P", "text": "hi"}]},
        ]}],
    }


def error_codes(exc):
    return {e["code"] for e in exc.errors}


class TestByteStability(unittest.TestCase):

    def test_golden_byte_identical(self):
        """RND-2 / M0 exit criterion: recompiling example.json is byte-identical."""
        got = C.compile_to_bytes(example_doc(), TEMPLATE)
        self.assertEqual(got, GOLDEN_SLA.read_bytes(),
                         "compiled SLA differs from golden fixture — if the "
                         "change is intentional, regenerate tests/golden/out.sla")

    def test_compile_twice_identical(self):
        doc = example_doc()
        self.assertEqual(C.compile_to_bytes(doc, TEMPLATE),
                         C.compile_to_bytes(copy.deepcopy(doc), TEMPLATE))

    def test_item_ids_sequential(self):
        root = ET.fromstring(C.compile_to_bytes(example_doc(), TEMPLATE))
        ids = [int(po.get("ItemID"))
               for po in root.find("DOCUMENT").findall("PAGEOBJECT")]
        self.assertEqual(ids, list(range(C.ITEM_ID_BASE,
                                         C.ITEM_ID_BASE + len(ids))))


class TestValidation(unittest.TestCase):

    def compile_expecting_errors(self, doc):
        with self.assertRaises(C.CompileError) as ctx:
            C.compile_to_bytes(doc, TEMPLATE)
        return ctx.exception

    def test_example_is_valid(self):
        C.compile_to_bytes(example_doc(), TEMPLATE)  # must not raise

    def test_missing_version(self):
        doc = minimal_doc()
        del doc["version"]
        exc = self.compile_expecting_errors(doc)
        self.assertIn("missing-field", error_codes(exc))
        self.assertEqual(exc.errors[0]["path"], "version")

    def test_unsupported_version(self):
        doc = minimal_doc()
        doc["version"] = "9.9"
        exc = self.compile_expecting_errors(doc)
        self.assertIn("unsupported-version", error_codes(exc))

    def test_unknown_item_type(self):
        doc = minimal_doc()
        doc["pages"][0]["items"].append({"type": "blob", "frame": [0, 0, 10, 10]})
        exc = self.compile_expecting_errors(doc)
        self.assertIn("unknown-item-type", error_codes(exc))

    def test_unknown_swatch_in_fill(self):
        doc = minimal_doc()
        doc["pages"][0]["items"].append(
            {"type": "shape", "frame": [0, 0, 10, 10], "fill": "NoSuchColour"})
        exc = self.compile_expecting_errors(doc)
        self.assertIn("unknown-swatch", error_codes(exc))
        self.assertEqual(exc.errors[0]["path"], "pages[0].items[1].fill")

    def test_fill_on_path_invalid(self):
        doc = minimal_doc()
        doc["pages"][0]["items"].append(
            {"type": "path", "frame": [0, 0, 10, 10], "d": "M0 0 L10 10",
             "fill": "Ink", "stroke": {"color": "Ink", "width": 0.5}})
        exc = self.compile_expecting_errors(doc)
        self.assertIn("invalid-fill", error_codes(exc))

    def test_unknown_paragraph_style(self):
        doc = minimal_doc()
        doc["pages"][0]["items"][0]["paragraphs"][0]["style"] = "Ghost"
        exc = self.compile_expecting_errors(doc)
        self.assertIn("unknown-style", error_codes(exc))

    def test_all_errors_collected_in_one_pass(self):
        """GEN-3 repair loops need the whole picture in one round trip."""
        doc = minimal_doc()
        del doc["version"]
        doc["pages"][0]["items"][0]["paragraphs"][0]["style"] = "Ghost"
        doc["pages"][0]["items"].append({"type": "blob", "frame": [0, 0, 1, 1]})
        exc = self.compile_expecting_errors(doc)
        self.assertGreaterEqual(len(exc.errors), 3)
        self.assertEqual(
            {"missing-field", "unknown-style", "unknown-item-type"},
            error_codes(exc) & {"missing-field", "unknown-style", "unknown-item-type"})

    def test_empty_paragraphs(self):
        doc = minimal_doc()
        doc["pages"][0]["items"][0]["paragraphs"] = []
        exc = self.compile_expecting_errors(doc)
        self.assertIn("empty-paragraphs", error_codes(exc))


class TestDonor(unittest.TestCase):

    def test_missing_anchor_is_clear_error(self):
        tree = ET.parse(TEMPLATE)
        doc = tree.getroot().find("DOCUMENT")
        for c in doc.findall("COLOR"):
            doc.remove(c)
        with tempfile.NamedTemporaryFile(suffix=".sla", delete=False) as fh:
            tree.write(fh, encoding="UTF-8", xml_declaration=True)
            crippled = fh.name
        try:
            with self.assertRaises(C.DonorError) as ctx:
                C.compile_to_bytes(minimal_doc(), crippled)
            self.assertIn("COLOR", str(ctx.exception))
            self.assertIn("regenerate", str(ctx.exception))
        finally:
            Path(crippled).unlink()

    def test_unreadable_donor(self):
        with self.assertRaises(C.DonorError):
            C.compile_to_bytes(minimal_doc(), "/nonexistent/template.sla")


if __name__ == "__main__":
    unittest.main()
