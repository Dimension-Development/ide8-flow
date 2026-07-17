"""VAL-3: geometry — frames within page+bleed bounds, safe-zone intrusion
warnings for text, cut paths (spot stroke) must be open. Runs on the MERGED
document so profile swatches are visible for spot detection."""

EPS = 0.01

# Keep in sync with services/render/sla_compiler.py PAGE_SIZES.
PAGE_SIZES = {
    "A0": (2384, 3370), "A1": (1684, 2384), "A2": (1191, 1684),
    "A3": (842, 1191), "A4": (595, 842), "A5": (420, 595),
    "SRA3": (907, 1276), "LETTER": (612, 792), "TABLOID": (792, 1224),
}


def page_dims(page_spec):
    size = page_spec.get("size", "A4")
    if isinstance(size, (list, tuple)):
        w, h = float(size[0]), float(size[1])
    else:
        w, h = PAGE_SIZES[size.upper()]
    if page_spec.get("orientation", "portrait") == "landscape" and h > w:
        w, h = h, w
    return w, h


def check(document, profile):
    errors, warnings = [], []

    def err(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    def warn(code, path, message):
        warnings.append({"code": code, "path": path, "message": message})

    # lineHeight is ABSOLUTE POINTS (SCHEMA.md §paraStyles) — models trained
    # on CSS habitually emit multipliers (1.2), which compile to 1.2pt leading
    # and pile every line onto the same baseline. Found live 16 Jul 2026: it
    # garbled all 12 Harvest A/B concepts' multi-line text and zeroed the
    # critique pass rate. A ratio-looking value is an error so the GEN-3
    # repair loop fixes it, not a warning a human has to spot in the proof.
    char_sizes = {cs.get("name"): cs.get("size", 12)
                  for cs in document.get("charStyles", [])}
    for i, ps in enumerate(document.get("paraStyles", [])):
        lh = ps.get("lineHeight")
        if lh is None:
            continue  # automatic leading
        size = char_sizes.get(ps.get("charStyle"), 12)
        if lh < size * 0.5:
            err("lineheight-not-points", f"paraStyles[{i}].lineHeight",
                f"lineHeight {lh} looks like a multiplier — lineHeight is "
                f"absolute points; for {size}pt type write ≈{round(size * (lh if lh > 0.6 else 1.2), 1)} "
                f"or omit it for automatic leading")

    page = document.get("page", {})
    w, h = page_dims(page)
    bleed = page.get("bleed", 0)
    ml, mr, mt, mb = page.get("margins", [10, 10, 10, 10])
    safe_zone_on = profile.get("rules", {}).get("safeZone", True)

    spots = {sw["name"] for sw in document.get("swatches", []) if sw.get("spot")}

    for n, pg in enumerate(document.get("pages", [])):
        for j, item in enumerate(pg.get("items", [])):
            p = f"pages[{n}].items[{j}]"
            x, y, fw, fh = item["frame"]

            if fw <= 0 or fh <= 0:
                err("bad-frame", f"{p}.frame",
                    f"width/height must be positive (got {fw} x {fh})")
                continue

            if (x < -bleed - EPS or y < -bleed - EPS
                    or x + fw > w + bleed + EPS or y + fh > h + bleed + EPS):
                err("out-of-bounds", f"{p}.frame",
                    f"frame [{x}, {y}, {fw}, {fh}] exceeds page+bleed "
                    f"bounds [{-bleed}, {-bleed}, {w + bleed}, {h + bleed}]")

            if (safe_zone_on and item.get("type") == "text"
                    and (x < ml - EPS or y < mt - EPS
                         or x + fw > w - mr + EPS or y + fh > h - mb + EPS)):
                warn("safe-zone", f"{p}.frame",
                     f"text frame intrudes into the margin safe zone "
                     f"[{ml}, {mt}, {w - mr}, {h - mb}]")

            if item.get("type") == "path":
                stroke_col = item.get("stroke", {}).get("color")
                d = item.get("d", "")
                if stroke_col in spots and ("Z" in d or "z" in d):
                    err("closed-cut-path", f"{p}.d",
                        "cut/crease paths (spot stroke) must be OPEN — "
                        "remove the Z close command")

    return errors, warnings
