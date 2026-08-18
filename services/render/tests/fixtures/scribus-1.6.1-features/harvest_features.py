"""Create minimal SLA samples using Scribus' own 1.6.1 scripting API.

Run inside the pinned render container. This file is deliberately Python 3.6
compatible because it executes inside Scribus rather than the host runtime.

    scribus -g -ns -py harvest_features.py OUTDIR PNG_PATH
"""

import math
import os
import sys
import xml.etree.ElementTree as ET

import scribus


OUTDIR = os.path.abspath(sys.argv[1])
PNG_PATH = os.path.abspath(sys.argv[2])


def new_document(width=220, height=180):
    scribus.newDocument(
        (width, height),
        (0, 0, 0, 0),
        scribus.PORTRAIT,
        1,
        scribus.UNIT_POINTS,
        scribus.PAGE_1,
        0,
        1,
    )
    scribus.defineColorCMYKFloat("HarvestPink", 0, 90, 10, 0)
    scribus.defineColorCMYKFloat("HarvestYellow", 0, 5, 95, 0)
    scribus.defineColorCMYKFloat("HarvestCyan", 90, 0, 10, 0)
    scribus.defineColorCMYKFloat("HarvestBlue", 90, 55, 0, 0)


def save(name):
    scribus.saveDocAs(os.path.join(OUTDIR, name + ".sla"))
    scribus.closeDoc()


def plain_shape(name="plain-shape"):
    obj = scribus.createRect(20, 20, 180, 120, name)
    scribus.setFillColor("HarvestPink", obj)
    scribus.setLineColor("None", obj)
    return obj


def linear_gradient():
    new_document()
    obj = plain_shape("linear-gradient")
    scribus.setGradientFill(
        scribus.FILL_HORIZONTALG,
        "HarvestPink", 100,
        "HarvestYellow", 100,
        obj,
    )
    scribus.setGradientStop("HarvestCyan", 100, 1.0, 0.5, obj)
    save("linear-gradient")


def radial_gradient():
    new_document()
    obj = plain_shape("radial-gradient")
    scribus.setGradientFill(
        scribus.FILL_RADIALG,
        "HarvestYellow", 100,
        "HarvestPink", 100,
        obj,
    )
    scribus.setGradientStop("HarvestCyan", 100, 1.0, 0.65, obj)
    save("radial-gradient")


def radial_focal_gradient():
    """Create a non-centred focal sample despite the 1.6 Scripter gap.

    Scribus 1.6 exposes no setGradientVector function. Seed the two focal
    coordinates in its own saved XML, then reopen and save through Scribus so
    the committed sample is renderer-validated and round-trip stable.
    """
    new_document()
    obj = plain_shape("radial-gradient-focal")
    scribus.setGradientFill(
        scribus.FILL_RADIALG,
        "HarvestYellow", 100,
        "HarvestPink", 100,
        obj,
    )
    path = os.path.join(OUTDIR, "radial-gradient-focal.sla")
    scribus.saveDocAs(path)
    scribus.closeDoc()

    tree = ET.parse(path)
    item = next(node for node in tree.getroot().find("DOCUMENT")
                if node.tag == "PAGEOBJECT"
                and node.get("ANNAME") == "radial-gradient-focal")
    item.set("GRFOCALX", "60")
    item.set("GRFOCALY", "60")
    tree.write(path, encoding="UTF-8", xml_declaration=True)

    scribus.openDoc(path)
    scribus.saveDoc()
    scribus.closeDoc()


def object_opacity():
    new_document()
    obj = plain_shape("fifty-percent-opacity")
    # The API expects transparency in 0..1; 0.5 is also opacity 0.5.
    scribus.setFillTransparency(0.5, obj)
    save("object-opacity")


def opacity_calibration():
    new_document()
    obj = plain_shape("seventy-five-percent-opacity")
    scribus.setLineColor("HarvestBlue", obj)
    scribus.setLineWidth(4, obj)
    # This non-symmetric calibration proves the conversion: the API receives
    # 0.25 transparency, while SLA stores 0.75 opacity in both attributes.
    scribus.setFillTransparency(0.25, obj)
    scribus.setLineTransparency(0.25, obj)
    save("opacity-calibration")


def image_sample(name, mode):
    new_document()
    # Checkerboard-like backing makes source alpha obvious in exported proofs.
    back = scribus.createRect(20, 20, 180, 140, "alpha-backing")
    scribus.setFillColor("HarvestCyan", back)
    scribus.setLineColor("None", back)
    image = scribus.createImage(40, 30, 140, 120, name)
    scribus.loadImage(PNG_PATH, image)
    if mode == "auto":
        scribus.setScaleImageToFrame(True, True, image)
    elif mode == "contain":
        scribus.setScaleImageToFrame(False, True, image)
        # Desired scale is min(140/400, 120/200) = 0.35pt/px. At 100ppi,
        # pass 0.35/0.72 to the properties-palette API. The 140x70pt image
        # is centred vertically with a 25pt offset.
        scribus.setImageScale(0.35 / 0.72, 0.35 / 0.72, image)
        scribus.setImageOffset(0, 25, image)
    elif mode == "cover":
        scribus.setScaleImageToFrame(False, True, image)
        # Source is 400x200 at 100ppi, whose native scale is 0.72pt/px.
        # Cover needs 0.6pt/px, so the properties-palette scale passed to the
        # API is 0.6 / 0.72 = 0.833333. The SLA saves LOCALSC*=0.6.
        # Focus (0.625, 0.5) centres at x=70pt:
        # 70 - (400 * 0.625 * 0.6) = -80pt; y offset is 0.
        scribus.setImageScale(0.833333333333, 0.833333333333, image)
        scribus.setImageOffset(-80, 0, image)
    save(name)


def transparent_png():
    image_sample("transparent-png", "auto")


def contain_image():
    image_sample("contain-image", "contain")


def cover_focus_image():
    image_sample("cover-focus-image", "cover")


def stretch_image():
    new_document()
    image = scribus.createImage(40, 30, 140, 120, "stretch-image")
    scribus.loadImage(PNG_PATH, image)
    scribus.setScaleImageToFrame(True, False, image)
    save("stretch-image")


def image_opacity():
    new_document()
    back = scribus.createRect(20, 20, 180, 140, "opacity-backing")
    scribus.setFillColor("HarvestCyan", back)
    scribus.setLineColor("None", back)
    image = scribus.createImage(40, 30, 140, 120, "image-fifty-opacity")
    scribus.loadImage(PNG_PATH, image)
    scribus.setScaleImageToFrame(True, True, image)
    scribus.setFillTransparency(0.5, image)
    save("image-opacity")


def filled_vector():
    new_document()
    cx, cy = 110, 90
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = 68 if i % 2 == 0 else 30
        points.extend([cx + math.cos(angle) * radius,
                       cy + math.sin(angle) * radius])
    obj = scribus.createPolygon(points, "filled-vector-star")
    scribus.setFillColor("HarvestYellow", obj)
    scribus.setLineColor("HarvestPink", obj)
    scribus.setLineWidth(3, obj)
    save("filled-vector")


def paint_order():
    new_document()
    specs = [
        (20, 20, "HarvestPink", "paint-1-pink"),
        (55, 45, "HarvestYellow", "paint-2-yellow"),
        (90, 70, "HarvestBlue", "paint-3-blue"),
    ]
    for x, y, color, name in specs:
        obj = scribus.createRect(x, y, 110, 90, name)
        scribus.setFillColor(color, obj)
        scribus.setLineColor("None", obj)
    save("paint-order")


if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

linear_gradient()
radial_gradient()
radial_focal_gradient()
object_opacity()
opacity_calibration()
transparent_png()
contain_image()
cover_focus_image()
stretch_image()
image_opacity()
filled_vector()
paint_order()

# The Scripter constants initially save legacy automatic-gradient codes 1/5.
# Scribus normalises them to its stable free linear/radial codes 6/7 when the
# document is reopened. Commit the round-trip-stable representation that a
# compiler should emit and that a designer can reopen without file churn.
for gradient_name in ("linear-gradient", "radial-gradient"):
    path = os.path.join(OUTDIR, gradient_name + ".sla")
    scribus.openDoc(path)
    scribus.saveDoc()
    scribus.closeDoc()
