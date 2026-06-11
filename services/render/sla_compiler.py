#!/usr/bin/env python3
"""
sla_compiler.py — compile a clean JSON document schema to a Scribus .sla file.

Pipeline:  schema.json  →  sla_compiler  →  doc.sla  →  headless Scribus  →  PDF proof / PDF/X

Design notes
------------
- All schema coordinates are PAGE-RELATIVE points (1pt = 1/72"). The compiler
  translates to Scribus "scratch space": page n sits at
  (SCRATCH_X, SCRATCH_Y + n * (pageH + V_GAP)).
- A donor template.sla (empty doc saved by the target Scribus version) supplies
  the ~170 DOCUMENT preference attributes and required boilerplate children
  (CheckProfile, Printer, PDF, LAYERS, PageSets, ...). We never hand-author those.
- Per-PTYPE attribute defaults were harvested from real Scribus-saved objects,
  so every required attribute is present; the compiler only overrides the
  meaningful ones.
- Geometry uses the modern SVG path syntax ("M 0 0 L w 0 ... Z") that
  Scribus 1.5+ stores natively.

Usage:
    python3 sla_compiler.py schema.json out.sla [--template template.sla]
"""

import json
import random
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy

# ---------------------------------------------------------------- constants

SCRATCH_X = 100.0   # where Scribus places page x in scratch space
SCRATCH_Y = 20.0    # first page y
V_GAP = 40.0        # vertical gap between stacked pages

PAGE_SIZES = {      # points, portrait
    "A0": (2384, 3370), "A1": (1684, 2384), "A2": (1191, 1684),
    "A3": (842, 1191), "A4": (595, 842), "A5": (420, 595),
    "SRA3": (907, 1276), "LETTER": (612, 792), "TABLOID": (792, 1224),
}

ALIGN = {"left": "0", "center": "1", "right": "2", "justify": "3", "force": "4"}

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


# ---------------------------------------------------------------- helpers

def f(v):
    """Format a number for SLA attributes (trim trailing zeros)."""
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def rect_path(w, h):
    return f"M0 0 L{f(w)} 0 L{f(w)} {f(h)} L0 {f(h)} L0 0 Z"


def new_item_id():
    return str(random.randint(10_000_000, 999_999_999))


def page_size(page_spec):
    size = page_spec.get("size", "A4")
    if isinstance(size, (list, tuple)):
        w, h = float(size[0]), float(size[1])
    else:
        w, h = PAGE_SIZES[size.upper()]
    if page_spec.get("orientation", "portrait") == "landscape" and h > w:
        w, h = h, w
    return w, h


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


def emit_item(doc_el, item, page_no, page_pos):
    px, py = page_pos
    x, y, w, h = item["frame"]
    kind = item["type"]
    ptype = {"text": "4", "shape": "6", "path": "7", "image": "2"}[kind]
    attrs = dict(OBJ_DEFAULTS[ptype])
    attrs.update({
        "ItemID": new_item_id(),
        "OwnPage": str(page_no),
        "ANNAME": item.get("name", ""),
        "XPOS": f(px + x), "YPOS": f(py + y),
        "WIDTH": f(w), "HEIGHT": f(h),
    })

    stroke = item.get("stroke")
    if stroke:
        attrs["PCOLOR2"] = stroke.get("color", "Black")
        attrs["PWIDTH"] = f(stroke.get("width", 1))
    if item.get("fill"):
        attrs["PCOLOR"] = item["fill"]

    if kind == "path":
        attrs["path"] = item["d"]
    elif kind == "shape":
        attrs["path"] = item.get("d", rect_path(w, h))
    else:
        attrs["path"] = rect_path(w, h)

    if kind == "image":
        attrs["PFILE"] = item.get("src", "")
        fit = item.get("fit", "frame")
        attrs["SCALETYPE"] = "1" if fit == "frame" else "0"
        attrs["RATIO"] = "0" if item.get("stretch") else "1"

    if kind == "text":
        attrs["COLUMNS"] = str(item.get("columns", 1))
        attrs["COLGAP"] = f(item.get("columnGap", 0))
        pad = item.get("padding", 0)
        attrs["EXTRA"] = attrs["TEXTRA"] = attrs["BEXTRA"] = attrs["REXTRA"] = f(pad)

    po = ET.Element("PAGEOBJECT", attrs)
    if kind == "text":
        emit_story(po, item["paragraphs"])
    doc_el.append(po)


# ---------------------------------------------------------------- compile

def compile_sla(schema, template_path):
    tree = ET.parse(template_path)
    root = tree.getroot()
    doc = root.find("DOCUMENT")

    page = schema.get("page", {})
    w, h = page_size(page)
    m = page.get("margins", [10, 10, 10, 10])  # L R T B
    bleed = page.get("bleed", 0)
    pages = schema.get("pages", [])

    doc.set("ANZPAGES", str(len(pages)))
    doc.set("PAGEWIDTH", f(w))
    doc.set("PAGEHEIGHT", f(h))
    for side in ("Top", "Bottom", "Left", "Right"):
        doc.set("Bleed" + side, f(bleed))
    doc.set("BORDERLEFT", f(m[0]))
    doc.set("BORDERRIGHT", f(m[1]))
    doc.set("BORDERTOP", f(m[2]))
    doc.set("BORDERBOTTOM", f(m[3]))
    if "title" in schema.get("meta", {}):
        doc.set("TITLE", schema["meta"]["title"])

    emit_colors(doc, schema.get("swatches", []))
    emit_char_styles(doc, schema.get("charStyles", []))
    emit_para_styles(doc, schema.get("paraStyles", []))
    positions = emit_pages(doc, len(pages), w, h, m)

    # drop any donor page objects
    for po in doc.findall("PAGEOBJECT"):
        doc.remove(po)

    for n, pg in enumerate(pages):
        for item in pg.get("items", []):
            emit_item(doc, item, n, positions[n])

    return tree


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    schema_path, out_path = sys.argv[1], sys.argv[2]
    template = "template.sla"
    if "--template" in sys.argv:
        template = sys.argv[sys.argv.index("--template") + 1]
    schema = json.load(open(schema_path))
    tree = compile_sla(schema, template)
    ET.indent(tree, space=" ")
    tree.write(out_path, encoding="UTF-8", xml_declaration=True)
    print(f"compiled {schema_path} -> {out_path}")


if __name__ == "__main__":
    main()
