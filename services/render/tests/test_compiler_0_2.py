"""Compiler tests for document 0.2 gradients and item opacity (T03)."""

import copy
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


RENDER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RENDER_ROOT))

import sla_compiler as C  # noqa: E402


TEMPLATE = str(RENDER_ROOT / "template.sla")


SWATCHES = [
    {"name": "Pink", "space": "cmyk", "values": [0, 90, 10, 0]},
    {"name": "Yellow", "space": "cmyk", "values": [0, 5, 95, 0]},
    {"name": "Cyan", "space": "cmyk", "values": [90, 0, 10, 0]},
]


def document(*items, version="0.2"):
    return {
        "version": version,
        "page": {"size": [300, 200]},
        "swatches": copy.deepcopy(SWATCHES),
        "pages": [{"items": list(items)}],
    }


def shape(fill="Pink", **extra):
    return {
        "type": "shape", "name": "feature", "frame": [10, 10, 200, 100],
        "fill": fill, **extra,
    }


def linear(stops=None):
    return {
        "type": "linear-gradient",
        "start": [0, 0.5],
        "end": [1, 0.25],
        "stops": stops or [
            {"at": 0, "color": "Pink"},
            {"at": 0.4, "color": "Cyan"},
            {"at": 1, "color": "Yellow"},
        ],
    }


def radial(**changes):
    value = {
        "type": "radial-gradient",
        "center": [0.5, 0.5],
        "focal": [0.4, 0.5],
        "radius": 0.4,
        "stops": [
            {"at": 0, "color": "Yellow"},
            {"at": 1, "color": "Pink"},
        ],
    }
    value.update(changes)
    return value


SOURCE_META = {"assets/source.png": {"width": 400, "height": 200}}


def compile_root(doc, image_meta=None):
    return ET.fromstring(C.compile_to_bytes(
        doc, TEMPLATE, image_meta=image_meta)).find("DOCUMENT")


def page_object(doc, name="feature", image_meta=None):
    return next(item for item in compile_root(
        doc, image_meta=image_meta).findall("PAGEOBJECT")
                if item.get("ANNAME") == name)


def errors(doc, image_meta=None):
    with unittest.TestCase().assertRaises(C.CompileError) as caught:
        C.compile_to_bytes(doc, TEMPLATE, image_meta=image_meta)
    return caught.exception.errors


def codes(items):
    return {item["code"] for item in items}


class TestGradientEmission(unittest.TestCase):

    def test_linear_gradient_uses_stable_scribus_mapping(self):
        item = page_object(document(shape(linear())))
        self.assertEqual(item.get("GRTYP"), "6")
        self.assertEqual(item.get("PCOLOR"), "Pink")
        self.assertEqual(
            [item.get(key) for key in
             ("GRSTARTX", "GRSTARTY", "GRENDX", "GRENDY")],
            ["0", "50", "200", "25"])
        self.assertEqual(item.get("GRFOCALX"), "0")
        self.assertEqual(item.get("GRFOCALY"), "0")
        self.assertEqual(item.get("GRSCALE"), "1")
        self.assertEqual(item.get("GRSKEW"), "0")
        self.assertEqual(item.get("GRExt"), "3")
        self.assertEqual(
            [(stop.get("RAMP"), stop.get("NAME"), stop.get("SHADE"),
              stop.get("TRANS")) for stop in item.findall("CSTOP")],
            [("0", "Pink", "100", "1"),
             ("0.4", "Cyan", "100", "1"),
             ("1", "Yellow", "100", "1")])

    def test_radial_gradient_uses_item_local_points(self):
        item = page_object(document(shape(radial())))
        self.assertEqual(item.get("GRTYP"), "7")
        self.assertEqual(
            [item.get(key) for key in
             ("GRSTARTX", "GRSTARTY", "GRENDX", "GRENDY",
              "GRFOCALX", "GRFOCALY")],
            ["100", "50", "140", "50", "80", "50"])

    def test_radial_focal_defaults_to_center(self):
        fill = radial()
        del fill["focal"]
        item = page_object(document(shape(fill)))
        self.assertEqual(item.get("GRFOCALX"), "100")
        self.assertEqual(item.get("GRFOCALY"), "50")

    def test_text_frame_can_have_gradient_background(self):
        text = {
            "type": "text", "name": "feature", "frame": [0, 0, 200, 100],
            "fill": linear(),
            "paragraphs": [{"style": "Default Paragraph Style", "text": "x"}],
        }
        item = page_object(document(text))
        self.assertEqual(item.get("PTYPE"), "4")
        self.assertEqual(item.get("GRTYP"), "6")
        self.assertEqual(len(item.findall("CSTOP")), 3)
        self.assertIsNotNone(item.find("StoryText"))

    def test_identical_0_2_inputs_are_byte_identical(self):
        doc = document(shape(linear()))
        self.assertEqual(C.compile_to_bytes(doc, TEMPLATE),
                         C.compile_to_bytes(copy.deepcopy(doc), TEMPLATE))


class TestOpacityEmission(unittest.TestCase):

    def test_zero_opacity_and_stroke_are_emitted_explicitly(self):
        item = page_object(document(shape(
            stroke={"color": "Cyan", "width": 2}, opacity=0)))
        self.assertEqual(item.get("TransValue"), "0")
        self.assertEqual(item.get("TransValueS"), "0")

    def test_non_symmetric_opacity_maps_directly(self):
        item = page_object(document(shape(opacity=0.75)))
        self.assertEqual(item.get("TransValue"), "0.75")
        self.assertIsNone(item.get("TransValueS"))

    def test_image_opacity_compiles_with_available_stretch_mapping(self):
        image = {
            "type": "image", "name": "feature", "frame": [0, 0, 100, 80],
            "src": "assets/source.png", "fit": "stretch", "opacity": 0.5,
        }
        item = page_object(document(image), image_meta=SOURCE_META)
        self.assertEqual(item.get("PTYPE"), "2")
        self.assertEqual(item.get("TransValue"), "0.5")
        self.assertEqual(item.get("SCALETYPE"), "0")
        self.assertEqual(item.get("RATIO"), "0")


class TestGradientValidation(unittest.TestCase):

    def test_unknown_stop_swatch_has_precise_path(self):
        report = errors(document(shape(linear([
            {"at": 0, "color": "Pink"},
            {"at": 1, "color": "Missing"},
        ]))))
        self.assertIn("unknown-swatch", codes(report))
        match = next(item for item in report if item["code"] == "unknown-swatch")
        self.assertEqual(match["path"], "pages[0].items[0].fill.stops[1].color")

    def test_stop_order_and_endpoints_have_stable_errors(self):
        report = errors(document(shape(linear([
            {"at": 0.1, "color": "Pink"},
            {"at": 0.8, "color": "Cyan"},
            {"at": 0.7, "color": "Yellow"},
        ]))))
        self.assertIn("gradient-stop-order", codes(report))
        self.assertIn("gradient-stop-endpoints", codes(report))

    def test_bad_gradient_shape_does_not_crash(self):
        report = errors(document(shape({"type": "mesh", "stops": []})))
        self.assertIn("bad-gradient", codes(report))

    def test_zero_length_linear_vector_is_rejected(self):
        fill = linear()
        fill["end"] = fill["start"]
        self.assertIn("bad-gradient", codes(errors(document(shape(fill)))))

    def test_radial_focal_must_be_strictly_inside_radius(self):
        fill = radial(focal=[1, 0.5], radius=0.4)
        report = errors(document(shape(fill)))
        self.assertIn("bad-gradient", codes(report))
        self.assertTrue(any(item["path"].endswith(".focal") for item in report))

    def test_path_gradient_is_invalid_even_when_well_formed(self):
        path = {
            "type": "path", "frame": [0, 0, 100, 100], "fill": linear(),
            "d": "M0 0 L100 100", "stroke": {"color": "Cyan", "width": 1},
        }
        self.assertIn("invalid-fill", codes(errors(document(path))))


class TestImagePlacement(unittest.TestCase):

    def _image(self, **changes):
        image = {
            "type": "image", "name": "feature", "frame": [0, 0, 140, 120],
            "src": "assets/source.png",
        }
        image.update(changes)
        return image

    def test_contain_centres_a_non_square_source_in_a_non_square_frame(self):
        item = page_object(document(self._image(fit="contain")),
                           image_meta=SOURCE_META)
        self.assertEqual(item.get("SCALETYPE"), "1")
        self.assertEqual(item.get("RATIO"), "1")
        self.assertEqual(item.get("LOCALSCX"), "0.35")
        self.assertEqual(item.get("LOCALSCY"), "0.35")
        self.assertEqual(item.get("LOCALX"), "0")
        # (120 - 200 * .35) / 2 = 25pt; SLA offsets are source pixels.
        self.assertEqual(item.get("LOCALY"), "71.428571")

    def test_cover_places_focal_point_then_clamps_both_axes(self):
        item = page_object(document(self._image(
            fit="cover", focus=[0.625, 0.5], zoom=1)), image_meta=SOURCE_META)
        self.assertEqual(item.get("SCALETYPE"), "1")
        self.assertEqual(item.get("RATIO"), "1")
        self.assertEqual(item.get("LOCALSCX"), "0.6")
        self.assertEqual(item.get("LOCALSCY"), "0.6")
        # wanted x = 70 - .625 * 400 * .6 = -80pt => -133.333px.
        self.assertEqual(item.get("LOCALX"), "-133.333333")
        self.assertEqual(item.get("LOCALY"), "0")

    def test_stretch_uses_independent_source_scales(self):
        item = page_object(document(self._image(fit="stretch")),
                           image_meta=SOURCE_META)
        self.assertEqual(item.get("SCALETYPE"), "0")
        self.assertEqual(item.get("RATIO"), "0")
        self.assertEqual(item.get("LOCALSCX"), "0.35")
        self.assertEqual(item.get("LOCALSCY"), "0.6")

    def test_missing_or_bad_dimensions_are_explicit(self):
        doc = document(self._image(fit="cover"))
        self.assertIn("image-dimensions-required", codes(errors(doc)))
        self.assertIn("bad-image-dimensions", codes(errors(
            doc, {"assets/source.png": {"width": 0, "height": 200}})))

    def test_bad_placement_has_a_stable_error(self):
        for changes in ({"fit": "nope"}, {"fit": "contain", "zoom": 2},
                        {"fit": "cover", "focus": [2, 0.5]},
                        {"fit": "cover", "zoom": 0.5}):
            with self.subTest(changes=changes):
                self.assertIn("bad-image-placement", codes(errors(
                    document(self._image(**changes)), SOURCE_META)))


class TestOpacityAndCapabilityValidation(unittest.TestCase):

    def test_bad_opacity_range_and_type(self):
        for value in (-0.01, 1.01, True, float("inf")):
            with self.subTest(value=value):
                self.assertIn("bad-opacity",
                              codes(errors(document(shape(opacity=value)))))

    def test_opacity_is_rejected_on_text_and_path(self):
        text = {
            "type": "text", "frame": [0, 0, 100, 40], "opacity": 0.5,
            "paragraphs": [{"style": "Default Paragraph Style", "text": "x"}],
        }
        path = {
            "type": "path", "frame": [0, 0, 100, 100], "opacity": 0.5,
            "d": "M0 0 L100 100", "stroke": {"color": "Cyan", "width": 1},
        }
        self.assertIn("bad-opacity", codes(errors(document(text))))
        self.assertIn("bad-opacity", codes(errors(document(path))))

    def test_0_1_new_features_fail_without_type_error(self):
        gradient_doc = document(shape(linear()), version="0.1")
        opacity_doc = document(shape(opacity=0.5), version="0.1")
        self.assertIn("unsupported-feature", codes(errors(gradient_doc)))
        self.assertIn("unsupported-feature", codes(errors(opacity_doc)))

if __name__ == "__main__":
    unittest.main()
