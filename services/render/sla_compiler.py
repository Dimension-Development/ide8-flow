#!/usr/bin/env python3
"""
sla_compiler.py — compile an ide8.flow document (JSON) to a Scribus .sla file.

Pipeline:  document.json  →  sla_compiler  →  doc.sla  →  headless Scribus  →  PDF proof / PDF/X

Design notes
------------
- All document coordinates are PAGE-RELATIVE points (1pt = 1/72"). The compiler
  translates to Scribus "scratch space": page n sits at
  (SCRATCH_X, SCRATCH_Y + n * (pageH + V_GAP)).
- Byte-stable (PRD RND-2): identical document + compiler + donor template
  produces a byte-identical SLA. Item IDs are allocated sequentially in
  document order — never random. All serialization goes through
  compile_to_bytes() so CLI, tests, and the render service emit identically.
- Validation is structural and collects ALL errors before failing
  (CompileError.errors: [{code, path, message}]), so generation repair loops
  (PRD GEN-3) see the whole picture in one round trip. The full VAL layer
  (brand conformance, geometry, contrast) is M1 and lives above this.
- A donor template.sla (empty doc saved by the target Scribus version) supplies
  the ~170 DOCUMENT preference attributes and required boilerplate children
  (CheckProfile, Printer, PDF, LAYERS, PageSets, ...). We never hand-author
  those. Missing anchors raise DonorError → regenerate the donor.
- Per-PTYPE attribute defaults were harvested from real Scribus-saved objects,
  so every required attribute is present; the compiler only overrides the
  meaningful ones.
- Geometry uses the modern SVG path syntax ("M 0 0 L w 0 ... Z") that
  Scribus 1.5+ stores natively.

Usage:
    python3 sla_compiler.py document.json out.sla [--template template.sla] [--errors-json]
"""

import argparse
import io
import itertools
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------- constants

SUPPORTED_VERSIONS = {"0.1", "0.2"}

SCRATCH_X = 100.0   # where Scribus places page x in scratch space
SCRATCH_Y = 20.0    # first page y
V_GAP = 40.0        # vertical gap between stacked pages

ITEM_ID_BASE = 100_000_001   # sequential, document order — byte-stable output

PAGE_SIZES = {      # points, portrait
    "A0": (2384, 3370), "A1": (1684, 2384), "A2": (1191, 1684),
    "A3": (842, 1191), "A4": (595, 842), "A5": (420, 595),
    "SRA3": (907, 1276), "LETTER": (612, 792), "TABLOID": (792, 1224),
}

ALIGN = {"left": "0", "center": "1", "right": "2", "justify": "3", "force": "4"}

ITEM_TYPES = {"text": "4", "shape": "6", "path": "7", "image": "2"}

# Per-PTYPE attribute defaults harvested from Scribus 1.6.1-saved objects.
# Only attributes NOT overridden per-item need to be correct here.
OBJ_DEFAULTS = {
    # text frame
    "4": {
        "OwnPage": "0", "ItemID": "0", "PTYPE": "4", "XPOS": "0", "YPOS": "0",
        "WIDTH": "100", "HEIGHT": "100", "ROT": "0", "PWIDTH": "1",
        "PCOLOR": "None", "PCOLOR2": "None", "COLUMNS": "1", "COLGAP": "0",
        "AUTOTEXT": "0", "EXTRA": "0", "TEXTRA": "0", "BEXTRA": "0", "REXTRA": "0",
        "VAlign": "0", "FLOP": "0", "PLINEART": "1", "PLINEEND": "0", "PLINEJOIN": "0",
        "LOCALSCX": "1", "LOCALSCY": "1", "LOCALX": "0", "LOCALY": "0", "LOCALROT": "0",
        "PICART": "1", "SCALETYPE": "1", "RATIO": "1", "PRINTABLE": "1",
        "ANNOTATION": "0", "BOOKMARK": "0", "FRTYPE": "0", "CLIPEDIT": "0",
        "NEXTITEM": "-1", "BACKITEM": "-1", "LAYER": "0", "ANNAME": "",
        "BASEOF": "0", "TEXTFLOWMODE": "0",
    },
    # shape / polygon
    "6": {
        "OwnPage": "0", "ItemID": "0", "PTYPE": "6", "XPOS": "0", "YPOS": "0",
        "WIDTH": "100", "HEIGHT": "100", "ROT": "0", "PWIDTH": "1",
        "PCOLOR": "None", "PCOLOR2": "None", "PLINEART": "1", "PLINEEND": "0",
        "PLINEJOIN": "0", "LOCALSCX": "1", "LOCALSCY": "1", "LOCALX": "0",
        "LOCALY": "0", "LOCALROT": "0", "PICART": "1", "SCALETYPE": "1",
        "RATIO": "1", "PRINTABLE": "1", "ANNOTATION": "0", "BOOKMARK": "0",
        "FRTYPE": "3", "CLIPEDIT": "1", "NEXTITEM": "-1", "BACKITEM": "-1",
        "LAYER": "0", "ANNAME": "", "TEXTFLOWMODE": "0",
    },
    # polyline (open path)
    "7": {
        "OwnPage": "0", "ItemID": "0", "PTYPE": "7", "XPOS": "0", "YPOS": "0",
        "WIDTH": "100", "HEIGHT": "100", "ROT": "0", "PWIDTH": "1",
        "PCOLOR": "None", "PCOLOR2": "None", "PLINEART": "1", "PLINEEND": "0",
        "PLINEJOIN": "0", "LOCALSCX": "1", "LOCALSCY": "1", "LOCALX": "0",
        "LOCALY": "0", "LOCALROT": "0", "PICART": "1", "SCALETYPE": "1",
        "RATIO": "1", "PRINTABLE": "1", "ANNOTATION": "0", "BOOKMARK": "0",
        "FRTYPE": "3", "CLIPEDIT": "1", "NEXTITEM": "-1", "BACKITEM": "-1",
        "LAYER": "0", "ANNAME": "", "TEXTFLOWMODE": "0",
    },
    # image frame
    "2": {
        "OwnPage": "0", "ItemID": "0", "PTYPE": "2", "XPOS": "0", "YPOS": "0",
        "WIDTH": "100", "HEIGHT": "100", "ROT": "0", "PWIDTH": "1",
        "PCOLOR": "None", "PCOLOR2": "None", "PFILE": "", "IRENDER": "0",
        "EMBEDDED": "0", "LOCALSCX": "1", "LOCALSCY": "1", "LOCALX": "0",
        "LOCALY": "0", "LOCALROT": "0", "PICART": "1", "SCALETYPE": "1",
        "RATIO": "1", "PRINTABLE": "1", "ANNOTATION": "0", "BOOKMARK": "0",
        "FRTYPE": "0", "CLIPEDIT": "0", "NEXTITEM": "-1", "BACKITEM": "-1",
        "LAYER": "0", "ANNAME": "", "TEXTFLOWMODE": "0",
    },
}


# ---------------------------------------------------------------- errors

class CompileError(Exception):
    """Structural errors in the document. `errors` is machine-readable:
    [{code, path, message}] — the contract the GEN-3 repair loop consumes."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(
            f"[{e['code']}] {e['path']}: {e['message']}" for e in errors))


class DonorError(Exception):
    """The donor template is unusable. Regenerate it: save an empty document
    from the pinned Scribus version, replace template.sla (see README)."""


# ---------------------------------------------------------------- helpers

def f(v):
    """Format a number for SLA attributes (trim trailing zeros)."""
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def rect_path(w, h):
    return f"M0 0 L{f(w)} 0 L{f(w)} {f(h)} L0 {f(h)} L0 0 Z"


def page_size(page_spec):
    size = page_spec.get("size", "A4")
    if isinstance(size, (list, tuple)):
        w, h = float(size[0]), float(size[1])
    else:
        w, h = PAGE_SIZES[size.upper()]
    if page_spec.get("orientation", "portrait") == "landscape" and h > w:
        w, h = h, w
    return w, h


def _is_frame(v):
    return (isinstance(v, (list, tuple)) and len(v) == 4
            and all(isinstance(n, (int, float)) for n in v))


def _is_number(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def _is_point(v):
    return (isinstance(v, (list, tuple)) and len(v) == 2
            and all(_is_number(n) and 0 <= n <= 1 for n in v))


def _gradient_stops(fill):
    stops = fill.get("stops") if isinstance(fill, dict) else None
    return stops if isinstance(stops, list) else []


def _validate_gradient(fill, path, known_colors, frame, err):
    """Validate 0.2 gradient semantics that JSON Schema cannot express.

    The compiler endpoint can be called directly, so it also guards the basic
    shape rather than assuming the worker's formal-schema gate already ran.
    """
    if not isinstance(fill, dict):
        err("bad-gradient", path,
            "fill must be a swatch name or a linear/radial gradient object")
        return

    kind = fill.get("type")
    if kind not in ("linear-gradient", "radial-gradient"):
        err("bad-gradient", f"{path}.type",
            'must be "linear-gradient" or "radial-gradient"')

    stops = fill.get("stops")
    if not isinstance(stops, list) or not 2 <= len(stops) <= 16:
        err("bad-gradient", f"{path}.stops",
            "must contain between 2 and 16 gradient stops")
        stops = []

    positions = []
    for i, stop in enumerate(stops):
        sp = f"{path}.stops[{i}]"
        if not isinstance(stop, dict):
            err("bad-gradient", sp, "gradient stop must be an object")
            continue
        at = stop.get("at")
        color = stop.get("color")
        if not _is_number(at) or not 0 <= at <= 1:
            err("bad-gradient", f"{sp}.at", "must be a number from 0 to 1")
        else:
            positions.append((i, float(at)))
        if not isinstance(color, str) or not color:
            err("bad-gradient", f"{sp}.color",
                "must be a non-empty swatch name")
        elif color not in known_colors:
            err("unknown-swatch", f"{sp}.color",
                f'"{color}" is not a defined swatch')

    if positions:
        if positions[0][1] != 0 or positions[-1][1] != 1:
            err("gradient-stop-endpoints", f"{path}.stops",
                "first gradient stop must be 0 and last must be 1")
        for (previous_i, previous), (current_i, current) in zip(
                positions, positions[1:]):
            if current < previous:
                err("gradient-stop-order",
                    f"{path}.stops[{current_i}].at",
                    f"stop {current_i} ({current}) is before stop "
                    f"{previous_i} ({previous})")

    if kind == "linear-gradient":
        start, end = fill.get("start"), fill.get("end")
        if not _is_point(start):
            err("bad-gradient", f"{path}.start",
                "must be a normalised [x, y] point")
        if not _is_point(end):
            err("bad-gradient", f"{path}.end",
                "must be a normalised [x, y] point")
        if _is_point(start) and _is_point(end) and list(start) == list(end):
            err("bad-gradient", path,
                "linear gradient start and end must be different")

    elif kind == "radial-gradient":
        center = fill.get("center")
        focal = fill.get("focal", center)
        radius = fill.get("radius")
        if not _is_point(center):
            err("bad-gradient", f"{path}.center",
                "must be a normalised [x, y] point")
        if not _is_point(focal):
            err("bad-gradient", f"{path}.focal",
                "must be a normalised [x, y] point")
        if not _is_number(radius) or not 0 < radius <= 2:
            err("bad-gradient", f"{path}.radius",
                "must be greater than 0 and at most 2")
        if (_is_frame(frame) and _is_point(center) and _is_point(focal)
                and _is_number(radius) and radius > 0):
            _, _, width, height = frame
            dx = (focal[0] - center[0]) * width
            dy = (focal[1] - center[1]) * height
            if math.hypot(dx, dy) >= radius * min(width, height):
                err("bad-gradient", f"{path}.focal",
                    "radial focal point must lie strictly inside the radius")


# ---------------------------------------------------------------- validation

def _image_dimensions(image_meta, src):
    """Return trusted source dimensions, or a stable validation error code.

    Asset metadata is transient compiler input rather than part of the document
    vocabulary.  It is intentionally keyed by the worker-staged PFILE path.
    """
    if not isinstance(image_meta, dict) or src not in image_meta:
        return None, "image-dimensions-required"
    meta = image_meta[src]
    if not isinstance(meta, dict):
        return None, "bad-image-dimensions"
    width, height = meta.get("width"), meta.get("height")
    if (not _is_number(width) or not _is_number(height)
            or width <= 0 or height <= 0):
        return None, "bad-image-dimensions"
    return (float(width), float(height)), None


def _image_placement(item, image_meta):
    """Calculate the harvested Scribus image mapping for a 0.2 image item.

    Returns attribute overrides or `(None, error_code, message)`.  All offset
    calculations are in source pixels because that is Scribus' SLA unit for
    LOCALX/Y; LOCALSCX/Y are points per source pixel.
    """
    fit = item.get("fit", "contain")
    if fit not in ("contain", "cover", "stretch"):
        return None, "bad-image-placement", 'fit must be "contain", "cover" or "stretch"'

    focus = item.get("focus", [0.5, 0.5])
    zoom = item.get("zoom", 1)
    if fit != "cover" and ("focus" in item or "zoom" in item):
        return None, "bad-image-placement", "focus and zoom are valid only with cover"
    if fit == "cover":
        if not _is_point(focus):
            return None, "bad-image-placement", "focus must be a normalised [x, y] point"
        if not _is_number(zoom) or not 1 <= zoom <= 8:
            return None, "bad-image-placement", "zoom must be a finite number from 1 to 8"

    source, code = _image_dimensions(image_meta, item.get("src"))
    if code:
        message = ("image placement requires trusted source image dimensions"
                   if code == "image-dimensions-required" else
                   "source image dimensions must be finite positive numbers")
        return None, code, message

    sw, sh = source
    _, _, fw, fh = item["frame"]
    if not _is_number(fw) or not _is_number(fh) or fw <= 0 or fh <= 0:
        return None, "bad-image-placement", "image frame width and height must be positive"
    if fit == "stretch":
        return {
            "SCALETYPE": "0", "RATIO": "0",
            "LOCALSCX": f(fw / sw), "LOCALSCY": f(fh / sh),
            "LOCALX": "0", "LOCALY": "0",
        }, None, None
    if fit == "contain":
        scale = min(fw / sw, fh / sh)
        offset_x = (fw - sw * scale) / 2
        offset_y = (fh - sh * scale) / 2
    else:
        scale = max(fw / sw, fh / sh) * zoom
        wanted_x = fw / 2 - focus[0] * sw * scale
        wanted_y = fh / 2 - focus[1] * sh * scale
        offset_x = min(0, max(fw - sw * scale, wanted_x))
        offset_y = min(0, max(fh - sh * scale, wanted_y))
    return {
        "SCALETYPE": "1", "RATIO": "1",
        "LOCALSCX": f(scale), "LOCALSCY": f(scale),
        "LOCALX": f(offset_x / scale), "LOCALY": f(offset_y / scale),
    }, None, None


def validate_document(document, donor_colors, donor_charstyles, donor_parastyles,
                      image_meta=None):
    """Structural validation. Returns ALL errors, not just the first."""
    errors = []

    def err(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    version = document.get("version")
    if version is None:
        err("missing-field", "version",
            f"required; supported document-schema versions: {sorted(SUPPORTED_VERSIONS)}")
    elif version not in SUPPORTED_VERSIONS:
        err("unsupported-version", "version",
            f'"{version}" not in supported versions {sorted(SUPPORTED_VERSIONS)}')

    page = document.get("page", {})
    size = page.get("size", "A4")
    if isinstance(size, str):
        if size.upper() not in PAGE_SIZES:
            err("unknown-page-size", "page.size",
                f'"{size}" — named sizes: {sorted(PAGE_SIZES)} (or [w, h] in points)')
    elif not (isinstance(size, (list, tuple)) and len(size) == 2):
        err("bad-page-size", "page.size", "must be a named size or [w, h] in points")
    if page.get("orientation", "portrait") not in ("portrait", "landscape"):
        err("bad-orientation", "page.orientation", 'must be "portrait" or "landscape"')
    margins = page.get("margins", [10, 10, 10, 10])
    if not (isinstance(margins, (list, tuple)) and len(margins) == 4):
        err("bad-margins", "page.margins", "must be [left, right, top, bottom]")

    swatch_names = set()
    for i, sw in enumerate(document.get("swatches", [])):
        p = f"swatches[{i}]"
        name = sw.get("name")
        if not name:
            err("missing-field", f"{p}.name", "swatch needs a name")
            continue
        swatch_names.add(name)
        space = sw.get("space", "cmyk").lower()
        vals = sw.get("values", [])
        want = {"cmyk": 4, "rgb": 3}.get(space)
        if want is None:
            err("bad-swatch", f"{p}.space", f'"{space}" — must be "cmyk" or "rgb"')
        elif len(vals) != want:
            err("bad-swatch", f"{p}.values",
                f"{space} needs {want} values, got {len(vals)}")

    # "None" is the Scribus no-colour; the donor supplies Black/White/etc.
    known_colors = donor_colors | swatch_names | {"None"}

    char_names = set(donor_charstyles) | {"Default Character Style"}
    for i, st in enumerate(document.get("charStyles", [])):
        p = f"charStyles[{i}]"
        if not st.get("name"):
            err("missing-field", f"{p}.name", "char style needs a name")
        else:
            char_names.add(st["name"])
        if not st.get("font"):
            err("missing-field", f"{p}.font", "char style needs a font")
        color = st.get("color", "Black")
        if color not in known_colors:
            err("unknown-swatch", f"{p}.color", f'"{color}" is not a defined swatch')

    para_names = set(donor_parastyles) | {"Default Paragraph Style"}
    for i, st in enumerate(document.get("paraStyles", [])):
        p = f"paraStyles[{i}]"
        if not st.get("name"):
            err("missing-field", f"{p}.name", "paragraph style needs a name")
        else:
            para_names.add(st["name"])
        align = st.get("align", "left")
        if align not in ALIGN:
            err("bad-align", f"{p}.align", f'"{align}" — must be one of {sorted(ALIGN)}')
        cs = st.get("charStyle")
        if cs and cs not in char_names:
            err("unknown-style", f"{p}.charStyle", f'"{cs}" is not a defined char style')

    for n, pg in enumerate(document.get("pages", [])):
        for j, item in enumerate(pg.get("items", [])):
            p = f"pages[{n}].items[{j}]"
            kind = item.get("type")
            if kind not in ITEM_TYPES:
                err("unknown-item-type", f"{p}.type",
                    f'"{kind}" — must be one of {sorted(ITEM_TYPES)}')
                continue
            if not _is_frame(item.get("frame")):
                err("bad-frame", f"{p}.frame", "must be [x, y, w, h] in points")

            fill = item.get("fill")
            if "fill" in item:
                if isinstance(fill, str):
                    if fill not in known_colors:
                        err("unknown-swatch", f"{p}.fill",
                            f'"{fill}" is not a defined swatch')
                elif version == "0.2":
                    _validate_gradient(fill, f"{p}.fill", known_colors,
                                       item.get("frame"), err)
                else:
                    err("unsupported-feature", f"{p}.fill",
                        "gradient fills require document version 0.2")

            if "opacity" in item:
                opacity = item.get("opacity")
                if version != "0.2":
                    err("unsupported-feature", f"{p}.opacity",
                        "item opacity requires document version 0.2")
                elif kind not in ("shape", "image"):
                    err("bad-opacity", f"{p}.opacity",
                        "opacity is supported on shape and image items only")
                elif not _is_number(opacity) or not 0 <= opacity <= 1:
                    err("bad-opacity", f"{p}.opacity",
                        "must be a finite number from 0 to 1")
            stroke = item.get("stroke")
            if stroke:
                sc = stroke.get("color", "Black")
                if sc not in known_colors:
                    err("unknown-swatch", f"{p}.stroke.color",
                        f'"{sc}" is not a defined swatch')

            if kind == "path":
                if not item.get("d"):
                    err("missing-field", f"{p}.d", "path needs SVG path data")
                if not stroke:
                    err("missing-field", f"{p}.stroke", "path needs a stroke")
                if "fill" in item:
                    err("invalid-fill", f"{p}.fill",
                        "paths are stroke-only — no fill (cut/crease paths, VAL-3)")

            elif kind == "text":
                paragraphs = item.get("paragraphs")
                if not paragraphs:
                    err("empty-paragraphs", f"{p}.paragraphs",
                        "text frame needs at least one paragraph")
                    continue
                for k, para in enumerate(paragraphs):
                    pp = f"{p}.paragraphs[{k}]"
                    style = para.get("style")
                    if not style:
                        err("missing-field", f"{pp}.style", "paragraph needs a style")
                    elif style not in para_names:
                        err("unknown-style", f"{pp}.style",
                            f'"{style}" is not a defined paragraph style')
                    runs = para.get("runs")
                    if runs is None and "text" not in para:
                        err("missing-field", f"{pp}.text",
                            'paragraph needs "text" or "runs"')
                    for r, run in enumerate(runs or []):
                        if "text" not in run:
                            err("missing-field", f"{pp}.runs[{r}].text",
                                "run needs text")
                        rcs = run.get("charStyle")
                        if rcs and rcs not in char_names:
                            err("unknown-style", f"{pp}.runs[{r}].charStyle",
                                f'"{rcs}" is not a defined char style')

            elif kind == "image":
                if not item.get("src"):
                    err("missing-field", f"{p}.src", "image needs a source path")
                elif version == "0.2":
                    _, code, message = _image_placement(item, image_meta)
                    if code:
                        err(code, f"{p}.fit", message)

    return errors


# ---------------------------------------------------------------- emitters

def emit_colors(doc_el, swatches):
    existing = {c.get("NAME") for c in doc_el.findall("COLOR")}
    anchor = doc_el.findall("COLOR")[-1]
    idx = list(doc_el).index(anchor) + 1
    for sw in swatches:
        if sw["name"] in existing:
            continue
        attrs = {"NAME": sw["name"]}
        space = sw.get("space", "cmyk").lower()
        vals = sw["values"]
        if space == "cmyk":
            attrs["SPACE"] = "CMYK"
            for k, v in zip("CMYK", vals):
                attrs[k] = f(v)
        else:
            attrs["SPACE"] = "RGB"
            for k, v in zip(("R", "G", "B"), vals):
                attrs[k] = f(v)
        if sw.get("spot"):
            attrs["Spot"] = "1"
        el = ET.Element("COLOR", attrs)
        doc_el.insert(idx, el)
        idx += 1


def emit_char_styles(doc_el, styles):
    anchor = doc_el.findall("CHARSTYLE")[-1]
    idx = list(doc_el).index(anchor) + 1
    for st in styles:
        attrs = {
            "CNAME": st["name"],
            "FONT": st["font"],
            "FONTSIZE": f(st.get("size", 12)),
            "FCOLOR": st.get("color", "Black"),
        }
        if "tracking" in st:
            attrs["KERN"] = f(st["tracking"])
        doc_el.insert(idx, ET.Element("CHARSTYLE", attrs))
        idx += 1


def emit_para_styles(doc_el, styles):
    anchor = doc_el.findall("STYLE")[-1]
    idx = list(doc_el).index(anchor) + 1
    for st in styles:
        attrs = {
            "NAME": st["name"],
            "ALIGN": ALIGN[st.get("align", "left")],
            "INDENT": f(st.get("indent", 0)),
            "FIRST": f(st.get("firstIndent", 0)),
            "VOR": f(st.get("spaceBefore", 0)),     # legacy German: before
            "NACH": f(st.get("spaceAfter", 0)),     # legacy German: after
        }
        if "lineHeight" in st:
            attrs["LINESPMode"] = "0"
            attrs["LINESP"] = f(st["lineHeight"])
        else:
            attrs["LINESPMode"] = "1"               # automatic
        if "charStyle" in st:
            attrs["CPARENT"] = st["charStyle"]
        doc_el.insert(idx, ET.Element("STYLE", attrs))
        idx += 1


def emit_pages(doc_el, n_pages, w, h, margins):
    # remove donor pages
    for p in doc_el.findall("PAGE"):
        doc_el.remove(p)
    # insert after MASTERPAGE
    anchor = doc_el.findall("MASTERPAGE")[-1]
    idx = list(doc_el).index(anchor) + 1
    positions = []
    for n in range(n_pages):
        px, py = SCRATCH_X, SCRATCH_Y + n * (h + V_GAP)
        positions.append((px, py))
        attrs = {
            "PAGEXPOS": f(px), "PAGEYPOS": f(py),
            "PAGEWIDTH": f(w), "PAGEHEIGHT": f(h),
            "BORDERLEFT": f(margins[0]), "BORDERRIGHT": f(margins[1]),
            "BORDERTOP": f(margins[2]), "BORDERBOTTOM": f(margins[3]),
            "NUM": str(n), "NAM": "", "MNAM": "Normal",
            "Size": "Custom", "Orientation": "0", "LEFT": "0", "PRESET": "0",
            "VerticalGuides": "", "HorizontalGuides": "",
            "AGhorizontalAutoGap": "0", "AGverticalAutoGap": "0",
            "AGhorizontalAutoCount": "0", "AGverticalAutoCount": "0",
            "AGhorizontalAutoRefer": "0", "AGverticalAutoRefer": "0",
            "AGSelection": "0 0 0 0", "pageEffectDuration": "1",
            "pageViewDuration": "1", "effectType": "0", "Dm": "0",
            "M": "0", "Di": "0",
        }
        doc_el.insert(idx, ET.Element("PAGE", attrs))
        idx += 1
    return positions


def emit_story(po_el, paragraphs):
    story = ET.SubElement(po_el, "StoryText")
    first_style = paragraphs[0].get("style", "Default Paragraph Style")
    ET.SubElement(story, "DefaultStyle", {"PARENT": first_style})
    for i, para in enumerate(paragraphs):
        style = para.get("style", first_style)
        runs = para.get("runs") or [{"text": para.get("text", "")}]
        for run in runs:
            it = {"CH": run["text"]}
            if "charStyle" in run:
                it["CPARENT"] = run["charStyle"]
            ET.SubElement(story, "ITEXT", it)
        tag = "trail" if i == len(paragraphs) - 1 else "para"
        ET.SubElement(story, tag, {"PARENT": style})


def apply_fill(attrs, fill, width, height):
    """Apply a solid or validated 0.2 gradient fill to PAGEOBJECT attrs."""
    if isinstance(fill, str):
        attrs["PCOLOR"] = fill
        return
    if not isinstance(fill, dict):
        return

    stops = _gradient_stops(fill)
    if stops:
        # PCOLOR is a non-gradient fallback; Scribus renders the CSTOP list.
        attrs["PCOLOR"] = stops[0]["color"]
    attrs.update({"GRSCALE": "1", "GRSKEW": "0", "GRExt": "3"})

    if fill["type"] == "linear-gradient":
        start, end = fill["start"], fill["end"]
        attrs.update({
            "GRTYP": "6",
            "GRSTARTX": f(start[0] * width),
            "GRSTARTY": f(start[1] * height),
            "GRENDX": f(end[0] * width),
            "GRENDY": f(end[1] * height),
            # Ignored by Scribus for a linear gradient, but explicit and
            # stable across reopen/save.
            "GRFOCALX": "0",
            "GRFOCALY": "0",
        })
    else:
        center = fill["center"]
        focal = fill.get("focal", center)
        radius = fill["radius"] * min(width, height)
        cx, cy = center[0] * width, center[1] * height
        attrs.update({
            "GRTYP": "7",
            "GRSTARTX": f(cx),
            "GRSTARTY": f(cy),
            "GRENDX": f(cx + radius),
            "GRENDY": f(cy),
            "GRFOCALX": f(focal[0] * width),
            "GRFOCALY": f(focal[1] * height),
        })


def emit_gradient_stops(po_el, fill):
    if not isinstance(fill, dict):
        return
    for stop in _gradient_stops(fill):
        ET.SubElement(po_el, "CSTOP", {
            "RAMP": f(stop["at"]),
            "NAME": stop["color"],
            "SHADE": "100",
            "TRANS": "1",
        })


def emit_item(doc_el, item, item_id, page_no, page_pos, version, image_meta=None):
    px, py = page_pos
    x, y, w, h = item["frame"]
    kind = item["type"]
    attrs = dict(OBJ_DEFAULTS[ITEM_TYPES[kind]])
    attrs.update({
        "ItemID": str(item_id),
        "OwnPage": str(page_no),
        "ANNAME": item.get("name", ""),
        "XPOS": f(px + x), "YPOS": f(py + y),
        "WIDTH": f(w), "HEIGHT": f(h),
    })

    stroke = item.get("stroke")
    if stroke:
        attrs["PCOLOR2"] = stroke.get("color", "Black")
        attrs["PWIDTH"] = f(stroke.get("width", 1))
    if "fill" in item:
        apply_fill(attrs, item["fill"], w, h)

    if "opacity" in item:
        attrs["TransValue"] = f(item["opacity"])
        if stroke:
            attrs["TransValueS"] = f(item["opacity"])

    if kind == "path":
        attrs["path"] = item["d"]
    elif kind == "shape":
        attrs["path"] = item.get("d", rect_path(w, h))
    else:
        attrs["path"] = rect_path(w, h)

    if kind == "image":
        attrs["PFILE"] = item.get("src", "")
        if version == "0.2":
            placement, code, message = _image_placement(item, image_meta)
            # validate_document() has already checked this.  Keep the guard
            # here so direct future use of emit_item cannot silently emit a
            # different mapping.
            if code:
                raise CompileError([{"code": code, "path": "image.fit",
                                     "message": message}])
            attrs.update(placement)
        else:
            fit = item.get("fit", "frame")
            attrs["SCALETYPE"] = "1" if fit == "frame" else "0"
            attrs["RATIO"] = "0" if item.get("stretch") else "1"

    if kind == "text":
        attrs["COLUMNS"] = str(item.get("columns", 1))
        attrs["COLGAP"] = f(item.get("columnGap", 0))
        pad = item.get("padding", 0)
        attrs["EXTRA"] = attrs["TEXTRA"] = attrs["BEXTRA"] = attrs["REXTRA"] = f(pad)

    po = ET.Element("PAGEOBJECT", attrs)
    emit_gradient_stops(po, item.get("fill"))
    if kind == "text":
        emit_story(po, item["paragraphs"])
    doc_el.append(po)


# ---------------------------------------------------------------- compile

def _donor_doc(template_path):
    """Parse the donor and assert the anchors the emitters rely on."""
    try:
        tree = ET.parse(template_path)
    except (OSError, ET.ParseError) as e:
        raise DonorError(f"cannot read donor template {template_path}: {e}")
    doc = tree.getroot().find("DOCUMENT")
    if doc is None:
        raise DonorError(f"{template_path} has no DOCUMENT element")
    missing = [tag for tag in ("COLOR", "CHARSTYLE", "STYLE", "MASTERPAGE")
               if not doc.findall(tag)]
    if missing:
        raise DonorError(
            f"{template_path} is missing required anchors {missing} — "
            "regenerate the donor: save an empty document from the pinned "
            "Scribus version (see README)")
    return tree, doc


def compile_sla(document, template_path, image_meta=None):
    tree, doc = _donor_doc(template_path)

    errors = validate_document(
        document,
        donor_colors={c.get("NAME") for c in doc.findall("COLOR")},
        donor_charstyles={c.get("CNAME") for c in doc.findall("CHARSTYLE")},
        donor_parastyles={s.get("NAME") for s in doc.findall("STYLE")},
        image_meta=image_meta,
    )
    if errors:
        raise CompileError(errors)

    page = document.get("page", {})
    w, h = page_size(page)
    m = page.get("margins", [10, 10, 10, 10])  # L R T B
    bleed = page.get("bleed", 0)
    pages = document.get("pages", [])

    doc.set("ANZPAGES", str(len(pages)))
    doc.set("PAGEWIDTH", f(w))
    doc.set("PAGEHEIGHT", f(h))
    for side in ("Top", "Bottom", "Left", "Right"):
        doc.set("Bleed" + side, f(bleed))
    doc.set("BORDERLEFT", f(m[0]))
    doc.set("BORDERRIGHT", f(m[1]))
    doc.set("BORDERTOP", f(m[2]))
    doc.set("BORDERBOTTOM", f(m[3]))
    if "title" in document.get("meta", {}):
        doc.set("TITLE", document["meta"]["title"])

    emit_colors(doc, document.get("swatches", []))
    emit_char_styles(doc, document.get("charStyles", []))
    emit_para_styles(doc, document.get("paraStyles", []))
    positions = emit_pages(doc, len(pages), w, h, m)

    # drop any donor page objects
    for po in doc.findall("PAGEOBJECT"):
        doc.remove(po)

    ids = itertools.count(ITEM_ID_BASE)
    for n, pg in enumerate(pages):
        for item in pg.get("items", []):
            emit_item(doc, item, next(ids), n, positions[n],
                      document["version"], image_meta=image_meta)

    return tree


def compile_to_bytes(document, template_path, image_meta=None):
    """The single serialization path — CLI, tests, and the render service all
    emit through here, which is what makes byte-stability a testable claim."""
    tree = compile_sla(document, template_path, image_meta=image_meta)
    ET.indent(tree, space=" ")
    buf = io.BytesIO()
    tree.write(buf, encoding="UTF-8", xml_declaration=True)
    return buf.getvalue()


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compile an ide8.flow document (JSON) to a Scribus .sla")
    parser.add_argument("document", help="document JSON path")
    parser.add_argument("out", help="output .sla path")
    parser.add_argument("--template",
                        default=str(Path(__file__).with_name("template.sla")),
                        help="donor template (default: template.sla beside the compiler)")
    parser.add_argument("--errors-json", action="store_true",
                        help="on validation failure, print {ok, errors} JSON to stdout")
    args = parser.parse_args(argv)

    with open(args.document) as fh:
        document = json.load(fh)

    try:
        data = compile_to_bytes(document, args.template)
    except CompileError as e:
        if args.errors_json:
            json.dump({"ok": False, "errors": e.errors}, sys.stdout, indent=2)
            print()
        else:
            for err in e.errors:
                print(f"error[{err['code']}] {err['path']}: {err['message']}",
                      file=sys.stderr)
        return 2
    except DonorError as e:
        print(f"donor error: {e}", file=sys.stderr)
        return 3

    Path(args.out).write_bytes(data)
    print(f"compiled {args.document} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
