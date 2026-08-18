"""Formal document-schema 0.2 tests (T02 only; semantic checks are T03)."""

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema


WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from validation import schema_check  # noqa: E402


SCHEMA_0_1 = REPO_ROOT / "schema" / "document-0.1.schema.json"
SCHEMA_0_2 = REPO_ROOT / "schema" / "document-0.2.schema.json"
EXAMPLE_0_2 = REPO_ROOT / "services" / "render" / "examples" / "example-0.2.json"
EXAMPLE_0_1 = REPO_ROOT / "services" / "render" / "examples" / "example.json"


def load(path):
    return json.loads(Path(path).read_text())


def errors(document, schema=SCHEMA_0_2):
    return schema_check.check(document, schema)


def minimal_item(item):
    return {
        "version": "0.2",
        "page": {"size": [100, 100]},
        "pages": [{"items": [item]}],
    }


def linear(stops=None):
    return {
        "type": "linear-gradient",
        "start": [0, 0.5],
        "end": [1, 0.5],
        "stops": stops or [
            {"at": 0, "color": "A"},
            {"at": 1, "color": "B"},
        ],
    }


def radial():
    return {
        "type": "radial-gradient",
        "center": [0.5, 0.5],
        "focal": [0.4, 0.5],
        "radius": 0.5,
        "stops": [
            {"at": 0, "color": "A"},
            {"at": 1, "color": "B"},
        ],
    }


class TestSchemaDefinition(unittest.TestCase):

    def test_schema_is_valid_draft_2020_12(self):
        jsonschema.Draft202012Validator.check_schema(load(SCHEMA_0_2))

    def test_complete_example_is_valid(self):
        self.assertEqual(errors(load(EXAMPLE_0_2)), [])

    def test_version_is_string_0_2_only(self):
        doc = load(EXAMPLE_0_2)
        doc["version"] = 0.2
        self.assertTrue(errors(doc))
        doc["version"] = "0.1"
        self.assertTrue(errors(doc))


class TestFillAndOpacity(unittest.TestCase):

    def shape(self, fill="A", **extra):
        return minimal_item({
            "type": "shape", "frame": [0, 0, 10, 10], "fill": fill,
            **extra,
        })

    def test_solid_linear_radial_and_hard_stop_are_valid(self):
        self.assertEqual(errors(self.shape()), [])
        self.assertEqual(errors(self.shape(linear())), [])
        self.assertEqual(errors(self.shape(radial())), [])
        hard = linear([
            {"at": 0, "color": "A"},
            {"at": 0.5, "color": "A"},
            {"at": 0.5, "color": "B"},
            {"at": 1, "color": "B"},
        ])
        self.assertEqual(errors(self.shape(hard)), [])

    def test_gradient_is_valid_on_text_and_image_frame_backgrounds(self):
        text = minimal_item({
            "type": "text", "frame": [0, 0, 10, 10], "fill": linear(),
            "paragraphs": [{"style": "P", "text": "x"}],
        })
        fill = radial()
        del fill["focal"]  # optional; defaults to center semantically
        image = minimal_item({
            "type": "image", "frame": [0, 0, 10, 10], "src": "asset",
            "fill": fill,
        })
        self.assertEqual(errors(text), [])
        self.assertEqual(errors(image), [])

    def test_opacity_boundaries_are_valid(self):
        self.assertEqual(errors(self.shape(opacity=0)), [])
        self.assertEqual(errors(self.shape(opacity=1)), [])

    def test_opacity_outside_range_is_invalid(self):
        self.assertTrue(errors(self.shape(opacity=-0.001)))
        self.assertTrue(errors(self.shape(opacity=1.001)))

    def test_opacity_is_invalid_on_text_and_path(self):
        text = minimal_item({
            "type": "text", "frame": [0, 0, 10, 10], "opacity": 0.5,
            "paragraphs": [{"style": "P", "text": "x"}],
        })
        path = minimal_item({
            "type": "path", "frame": [0, 0, 10, 10], "opacity": 0.5,
            "d": "M0 0 L10 10", "stroke": {"color": "A", "width": 1},
        })
        self.assertTrue(errors(text))
        self.assertTrue(errors(path))

    def test_gradient_is_invalid_on_path(self):
        path = minimal_item({
            "type": "path", "frame": [0, 0, 10, 10],
            "fill": linear(), "d": "M0 0 L10 10",
            "stroke": {"color": "A", "width": 1},
        })
        self.assertTrue(errors(path))

    def test_stop_count_and_position_ranges(self):
        self.assertTrue(errors(self.shape(linear([
            {"at": 0, "color": "A"},
        ]))))
        too_many = [{"at": i / 16, "color": "A"} for i in range(17)]
        self.assertTrue(errors(self.shape(linear(too_many))))
        self.assertTrue(errors(self.shape(linear([
            {"at": -0.01, "color": "A"},
            {"at": 1, "color": "B"},
        ]))))
        self.assertTrue(errors(self.shape(linear([
            {"at": 0, "color": "A"},
            {"at": 1.01, "color": "B"},
        ]))))

    def test_points_and_radius_ranges(self):
        bad_point = linear()
        bad_point["start"] = [-0.01, 0.5]
        self.assertTrue(errors(self.shape(bad_point)))
        bad_radius = radial()
        bad_radius["radius"] = 0
        self.assertTrue(errors(self.shape(bad_radius)))
        bad_radius["radius"] = 2.01
        self.assertTrue(errors(self.shape(bad_radius)))

    def test_gradient_hallucinated_property_is_invalid(self):
        fill = linear()
        fill["angle"] = 45
        self.assertTrue(errors(self.shape(fill)))


class TestImagePlacement(unittest.TestCase):

    def image(self, **extra):
        return minimal_item({
            "type": "image", "frame": [0, 0, 10, 10], "src": "asset",
            **extra,
        })

    def test_fit_modes_and_image_opacity_are_valid(self):
        self.assertEqual(errors(self.image()), [])
        self.assertEqual(errors(self.image(fit="contain")), [])
        self.assertEqual(errors(self.image(fit="stretch", opacity=0.5)), [])
        self.assertEqual(errors(self.image(
            fit="cover", focus=[0, 1], zoom=8)), [])

    def test_focus_or_zoom_requires_explicit_cover(self):
        self.assertTrue(errors(self.image(focus=[0.5, 0.5])))
        self.assertTrue(errors(self.image(fit="contain", focus=[0.5, 0.5])))
        self.assertTrue(errors(self.image(fit="stretch", zoom=2)))

    def test_focus_and_zoom_ranges(self):
        self.assertTrue(errors(self.image(fit="cover", focus=[1.01, 0.5])))
        self.assertTrue(errors(self.image(fit="cover", zoom=0.99)))
        self.assertTrue(errors(self.image(fit="cover", zoom=8.01)))

    def test_old_and_unknown_fit_properties_are_invalid(self):
        self.assertTrue(errors(self.image(fit="frame")))
        self.assertTrue(errors(self.image(fit="free")))
        self.assertTrue(errors(self.image(fit="contain", stretch=True)))
        self.assertTrue(errors(self.image(fit="crop")))


class TestVersionIsolation(unittest.TestCase):

    def test_0_1_still_rejects_every_0_2_addition(self):
        base = load(EXAMPLE_0_1)
        changes = [
            (0, "opacity", 0.5),
            (0, "fill", linear()),
        ]
        for item_index, key, value in changes:
            with self.subTest(key=key):
                doc = copy.deepcopy(base)
                doc["pages"][0]["items"][item_index][key] = value
                self.assertTrue(errors(doc, SCHEMA_0_1))

        doc = copy.deepcopy(base)
        doc["pages"][0]["items"].append({
            "type": "image", "frame": [0, 0, 10, 10], "src": "asset",
            "fit": "cover", "focus": [0.5, 0.5],
        })
        self.assertTrue(errors(doc, SCHEMA_0_1))


if __name__ == "__main__":
    unittest.main()
