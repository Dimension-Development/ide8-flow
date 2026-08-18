#!/usr/bin/env python3
"""Verify the feature mappings harvested from Scribus 1.6.1.

Optionally pass a round-trip directory and 72dpi PPM paint/alpha proofs:

    verify_harvest.py FIXTURE_DIR [ROUNDTRIP_DIR] [PAINT_PPM] [ALPHA_PPM]
"""

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(sys.argv[1])


def objects(name, root=ROOT):
    tree = ET.parse(root / (name + ".sla"))
    return tree.getroot().find("DOCUMENT").findall("PAGEOBJECT")


def named(sample, item_name, root=ROOT):
    return next(item for item in objects(sample, root)
                if item.get("ANNAME") == item_name)


def close(actual, expected):
    assert math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-9), (
        actual, expected)


def stops(item):
    return [(float(stop.get("RAMP")), stop.get("NAME"),
             float(stop.get("TRANS")))
            for stop in item.findall("CSTOP")]


linear = named("linear-gradient", "linear-gradient")
assert linear.get("GRTYP") == "6"
assert [float(linear.get(key)) for key in
        ("GRSTARTX", "GRSTARTY", "GRENDX", "GRENDY")] == [0, 60, 180, 60]
assert stops(linear) == [
    (0.0, "HarvestPink", 1.0),
    (0.5, "HarvestCyan", 1.0),
    (1.0, "HarvestYellow", 1.0),
]

radial = named("radial-gradient", "radial-gradient")
assert radial.get("GRTYP") == "7"
assert [float(radial.get(key)) for key in
        ("GRSTARTX", "GRSTARTY", "GRENDX", "GRENDY")] == [90, 60, 180, 60]
assert stops(radial) == [
    (0.0, "HarvestYellow", 1.0),
    (0.65, "HarvestCyan", 1.0),
    (1.0, "HarvestPink", 1.0),
]

radial_focal = named("radial-gradient-focal", "radial-gradient-focal")
assert radial_focal.get("GRTYP") == "7"
close(radial_focal.get("GRFOCALX"), 60)
close(radial_focal.get("GRFOCALY"), 60)

opacity = named("object-opacity", "fifty-percent-opacity")
close(opacity.get("TransValue"), 0.5)

calibration = named("opacity-calibration", "seventy-five-percent-opacity")
close(calibration.get("TransValue"), 0.75)
close(calibration.get("TransValueS"), 0.75)

image_opacity = named("image-opacity", "image-fifty-opacity")
close(image_opacity.get("TransValue"), 0.5)

contain = named("contain-image", "contain-image")
assert contain.get("SCALETYPE") == "1" and contain.get("RATIO") == "1"
close(contain.get("LOCALSCX"), 0.35)
close(contain.get("LOCALSCY"), 0.35)
close(contain.get("LOCALX"), 0)
close(contain.get("LOCALY"), 25 / 0.35)

cover = named("cover-focus-image", "cover-focus-image")
assert cover.get("SCALETYPE") == "1" and cover.get("RATIO") == "1"
close(cover.get("LOCALSCX"), 0.6)
close(cover.get("LOCALSCY"), 0.6)
close(cover.get("LOCALX"), -80 / 0.6)
close(cover.get("LOCALY"), 0)

stretch = named("stretch-image", "stretch-image")
assert stretch.get("SCALETYPE") == "0" and stretch.get("RATIO") == "0"
close(stretch.get("LOCALSCX"), 0.35)
close(stretch.get("LOCALSCY"), 0.6)

vector = named("filled-vector", "filled-vector-star")
assert vector.get("PTYPE") == "6"
assert vector.get("PCOLOR") == "HarvestYellow"
assert vector.get("PCOLOR2") == "HarvestPink"
assert vector.get("path", "").startswith("M")

order = [item.get("ANNAME") for item in objects("paint-order")]
assert order == ["paint-1-pink", "paint-2-yellow", "paint-3-blue"]

png = (ROOT / "transparent-source.png").read_bytes()
assert png.startswith(b"\x89PNG\r\n\x1a\n") and png[25] == 6


def signature(root, sample, item_name):
    item = named(sample, item_name, root)
    keys = (
        "PTYPE", "WIDTH", "HEIGHT", "PCOLOR", "PCOLOR2", "GRTYP",
        "GRSTARTX", "GRSTARTY", "GRENDX", "GRENDY", "GRFOCALX",
        "GRFOCALY", "TransValue", "LOCALSCX", "LOCALSCY", "LOCALX",
        "LOCALY", "SCALETYPE", "RATIO", "path",
    )
    return tuple(item.get(key) for key in keys), stops(item)


if len(sys.argv) > 2:
    roundtrip = Path(sys.argv[2])
    samples = {
        "linear-gradient": "linear-gradient",
        "radial-gradient": "radial-gradient",
        "radial-gradient-focal": "radial-gradient-focal",
        "object-opacity": "fifty-percent-opacity",
        "opacity-calibration": "seventy-five-percent-opacity",
        "contain-image": "contain-image",
        "cover-focus-image": "cover-focus-image",
        "stretch-image": "stretch-image",
        "image-opacity": "image-fifty-opacity",
        "filled-vector": "filled-vector-star",
    }
    for sample, item_name in samples.items():
        assert signature(ROOT, sample, item_name) == signature(
            roundtrip, sample, item_name), sample


def ppm_pixel(path, x, y):
    data = Path(path).read_bytes()
    assert data.startswith(b"P6\n")
    header, pixels = data.split(b"\n255\n", 1)
    _, dimensions = header.split(b"\n", 1)
    width, height = map(int, dimensions.split())
    assert 0 <= x < width and 0 <= y < height
    start = (y * width + x) * 3
    return tuple(pixels[start:start + 3])


if len(sys.argv) > 3:
    # At 72dpi, (100, 80) lies in all three objects. The last PAGEOBJECT is
    # blue and must be the visible one, proving back-to-front paint order.
    pixel = ppm_pixel(sys.argv[3], 100, 80)
    assert pixel[2] > pixel[0] and pixel[2] > pixel[1], pixel

if len(sys.argv) > 4:
    # Both points are inside the image frame. The first is outside the RGBA
    # ellipse and must reveal the cyan backing; the second is opaque magenta.
    transparent = ppm_pixel(sys.argv[4], 45, 35)
    opaque = ppm_pixel(sys.argv[4], 110, 65)
    assert transparent[1] > transparent[0], transparent
    assert transparent[2] > transparent[0], transparent
    assert opaque[0] > opaque[1] * 2, opaque

print("ok: Scribus 1.6.1 feature harvest verified")
