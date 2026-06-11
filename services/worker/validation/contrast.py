"""VAL-4: contrast — computed text colour vs underlying fill must meet the
profile floor. Catches the invisible-text class of failure without spending
a vision call. Runs on the MERGED document (needs profile styles/swatches).

Background resolution, in order: the text frame's own fill, else the topmost
earlier-drawn filled item on the same page whose frame contains the text
frame's centre, else paper white.
"""

DEFAULT_FLOOR = 3.0


def _swatch_rgb(sw):
    vals = sw.get("values", [])
    if sw.get("space", "cmyk") == "rgb":
        return tuple(float(v) for v in vals)
    c, m, y, k = (float(v) / 100 for v in vals)
    return (255 * (1 - c) * (1 - k),
            255 * (1 - m) * (1 - k),
            255 * (1 - y) * (1 - k))


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(rgb):
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(rgb_a, rgb_b):
    la, lb = _luminance(rgb_a), _luminance(rgb_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


WHITE = (255.0, 255.0, 255.0)
BLACK = (0.0, 0.0, 0.0)


def check(document, profile):
    errors = []
    floor = profile.get("rules", {}).get("contrastFloor", DEFAULT_FLOOR)

    swatches = {sw["name"]: _swatch_rgb(sw)
                for sw in document.get("swatches", [])}
    swatches.setdefault("Black", BLACK)
    swatches.setdefault("White", WHITE)
    char_styles = {st["name"]: st for st in document.get("charStyles", [])}
    para_styles = {st["name"]: st for st in document.get("paraStyles", [])}

    def text_rgb(char_style_name):
        st = char_styles.get(char_style_name, {})
        return swatches.get(st.get("color", "Black"), BLACK)

    for n, pg in enumerate(document.get("pages", [])):
        items = pg.get("items", [])
        for j, item in enumerate(items):
            if item.get("type") != "text":
                continue
            p = f"pages[{n}].items[{j}]"
            x, y, fw, fh = item["frame"]
            cx, cy = x + fw / 2, y + fh / 2

            bg = WHITE
            if item.get("fill"):
                bg = swatches.get(item["fill"], WHITE)
            else:
                for prev in items[:j]:
                    fill = prev.get("fill")
                    if not fill:
                        continue
                    px, py, pw, ph = prev["frame"]
                    if px <= cx <= px + pw and py <= cy <= py + ph:
                        bg = swatches.get(fill, WHITE)  # later = topmost

            for k, para in enumerate(item.get("paragraphs", [])):
                checks = []
                style = para_styles.get(para.get("style", ""), {})
                if "text" in para:
                    checks.append((f"{p}.paragraphs[{k}]",
                                   style.get("charStyle", "")))
                for r, run in enumerate(para.get("runs", []) or []):
                    checks.append((f"{p}.paragraphs[{k}].runs[{r}]",
                                   run.get("charStyle",
                                           style.get("charStyle", ""))))
                for path, cs_name in checks:
                    fg = text_rgb(cs_name)
                    ratio = _ratio(fg, bg)
                    if ratio < floor:
                        errors.append({
                            "code": "low-contrast", "path": path,
                            "message": (
                                f"contrast {ratio:.2f} is below the profile "
                                f"floor {floor} (text colour vs underlying "
                                f"fill) — choose a darker/lighter pairing")})

    return errors
