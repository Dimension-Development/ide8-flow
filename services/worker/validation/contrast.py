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


def _fill_colours(fill, swatches, path, errors):
    """Resolve a solid fill or every gradient stop without a white fallback."""
    names = ([fill] if isinstance(fill, str) else
             [stop.get("color") for stop in fill.get("stops", [])]
             if isinstance(fill, dict) else [])
    colours = []
    for i, name in enumerate(names):
        if name not in swatches:
            suffix = f".stops[{i}].color" if isinstance(fill, dict) else ""
            errors.append({"code": "unknown-swatch", "path": path + suffix,
                           "message": f'"{name}" is not a defined swatch'})
        else:
            colours.append(swatches[name])
    return colours


def _composite(foreground, opacity, background=WHITE):
    return tuple(opacity * fg + (1 - opacity) * bg
                 for fg, bg in zip(foreground, background))


def check(document, profile):
    errors = []
    floor = profile.get("rules", {}).get("contrastFloor", DEFAULT_FLOOR)

    swatches = {sw["name"]: _swatch_rgb(sw)
                for sw in document.get("swatches", [])}
    swatches.setdefault("Black", BLACK)
    swatches.setdefault("White", WHITE)
    char_styles = {st["name"]: st for st in document.get("charStyles", [])}
    para_styles = {st["name"]: st for st in document.get("paraStyles", [])}

    def text_rgb(char_style_name, path):
        st = char_styles.get(char_style_name, {})
        name = st.get("color", "Black")
        if name not in swatches:
            errors.append({"code": "unknown-swatch", "path": path,
                           "message": f'"{name}" is not a defined swatch'})
            return None
        return swatches[name]

    for n, pg in enumerate(document.get("pages", [])):
        items = pg.get("items", [])
        for j, item in enumerate(items):
            if item.get("type") != "text":
                continue
            p = f"pages[{n}].items[{j}]"
            x, y, fw, fh = item["frame"]
            cx, cy = x + fw / 2, y + fh / 2

            bg_colours = [WHITE]
            bg_opacity = 1
            if "fill" in item:
                bg_colours = _fill_colours(item["fill"], swatches,
                                           f"{p}.fill", errors)
            else:
                for prev_i, prev in enumerate(items[:j]):
                    if "fill" not in prev:
                        continue
                    px, py, pw, ph = prev["frame"]
                    if px <= cx <= px + pw and py <= cy <= py + ph:
                        bg_colours = _fill_colours(
                            prev["fill"], swatches,
                            f"pages[{n}].items[{prev_i}].fill", errors)
                        bg_opacity = prev.get("opacity", 1)  # later = topmost

            if bg_opacity < 1:
                # Conservative 0.2 rule: composite semi-transparent shapes
                # over paper white; general backdrop compositing is deferred.
                bg_colours = [_composite(rgb, bg_opacity) for rgb in bg_colours]

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
                    fg = text_rgb(cs_name, path)
                    if fg is None:
                        continue
                    ratio = min((_ratio(fg, bg) for bg in bg_colours), default=0)
                    if ratio < floor:
                        errors.append({
                            "code": "low-contrast", "path": path,
                            "message": (
                                f"contrast {ratio:.2f} is below the profile "
                                f"floor {floor} (text colour vs underlying "
                                f"fill) — choose a darker/lighter pairing")})

    return errors
