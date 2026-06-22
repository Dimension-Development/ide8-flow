#!/usr/bin/env python3
"""Generate the Harvest Edit image asset pack (real pixels, via Pillow).

Produces a "clean" usable set the engine can place, plus an edge-case set that
deliberately probes the asset pipeline (CMYK colour, missing TIFF dimensions,
oversized/tiny/extreme-aspect rasters, and unsupported vector/animation
formats). Writes assets/ + assets/edge-cases/ and a manifest.json.

    python3 gen_assets.py

Pure Pillow — no numpy. Gradients are drawn per-row / as concentric ellipses
to stay fast without a vector backend.
"""

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets"
EDGE = OUT / "edge-cases"

# --- brand palette (sRGB approximations of the CMYK profile swatches) --------
PLUM = (63, 28, 91)
RUST = (206, 70, 35)
OCHRE = (218, 157, 24)
SAGE = (170, 196, 165)
BONE = (250, 247, 235)
INK = (18, 16, 16)
COPPER = (172, 103, 57)
BERRY = (138, 32, 90)


def font(size, bold=False):
    """Best-effort system TTF; falls back to Pillow's bitmap font."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-"
        + ("Bold" if bold else "Regular") + ".ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def vgrad(w, h, top, bottom):
    """Vertical linear gradient image (RGB)."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def radial(w, h, inner, outer, cx=None, cy=None):
    """Cheap radial gradient via concentric ellipses."""
    img = Image.new("RGB", (w, h), outer)
    d = ImageDraw.Draw(img)
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    rmax = math.hypot(max(cx, w - cx), max(cy, h - cy))
    steps = 140
    for i in range(steps, 0, -1):
        t = i / steps
        r = rmax * t
        col = tuple(round(outer[k] + (inner[k] - outer[k]) * (1 - t))
                    for k in range(3))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    return img


def centre_text(d, box, text, fnt, fill):
    x0, y0, x1, y1 = box
    l, t, r, b = d.textbbox((0, 0), text, font=fnt)
    d.text(((x0 + x1 - (r - l)) / 2 - l, (y0 + y1 - (b - t)) / 2 - t),
           text, font=fnt, fill=fill)


def draw_mark(d, cx, cy, R, sun, line, hill):
    """Meridian motif: a sun/disc crossing a horizon meridian, hill below."""
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=sun)
    # horizon meridian line, slightly wider than the disc
    d.line([cx - R * 1.5, cy, cx + R * 1.5, cy], fill=line,
           width=max(2, R // 9))
    # hill arc (lower third)
    d.pieslice([cx - R * 0.9, cy - R * 0.1, cx + R * 0.9, cy + R * 1.7],
               20, 160, fill=hill)


def logo(reversed_=False, mark_only=False):
    """Primary lockup / reversed / mark-only, transparent background."""
    if mark_only:
        s = 512
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        draw_mark(d, s / 2, s / 2 - 20, 150, COPPER, PLUM if not reversed_
                  else BONE, RUST)
        return img
    w, h = 1100, 460
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = BONE if reversed_ else PLUM
    draw_mark(d, w / 2, 150, 110, COPPER, ink, RUST)
    centre_text(d, (0, 250, w, 360), "MERIDIAN", font(150, bold=True), ink)
    centre_text(d, (0, 372, w, 430), "·  M A R K E T  ·",
                font(46, bold=False), COPPER if reversed_ else COPPER)
    return img


def hero():
    """Editorial food-hero placeholder (RGB)."""
    w, h = 1600, 1200
    img = radial(w, h, PLUM, (28, 12, 42), cx=w * 0.62, cy=h * 0.42)
    d = ImageDraw.Draw(img, "RGBA")
    # a stylised squash: stacked warm ellipses
    cx, cy = w * 0.60, h * 0.60
    for i, col in enumerate([(150, 70, 20), RUST, OCHRE]):
        rx, ry = 360 - i * 70, 300 - i * 55
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col + (255,))
    d.ellipse([cx - 28, cy - 320, cx + 28, cy - 250], fill=(70, 110, 50))  # stem
    # plums, scattered
    rnd = random.Random(7)
    for _ in range(7):
        px, py = rnd.randint(120, 520), rnd.randint(760, 1080)
        rr = rnd.randint(48, 86)
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=PLUM + (255,))
        d.ellipse([px - rr * .5, py - rr * .7, px - rr * .1, py - rr * .3],
                  fill=(150, 110, 170, 150))
    centre_text(d, (40, h - 70, 560, h - 30),
                "PLACEHOLDER · harvest-hero", font(28, bold=True),
                (255, 255, 255, 140))
    return img


def lifestyle():
    """Lifestyle scene placeholder (RGB) — table-top vibe."""
    w, h = 1800, 1200
    img = vgrad(w, h, (236, 224, 200), (205, 188, 156))
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, int(h * 0.72), w, h], fill=(120, 84, 52))  # table
    rnd = random.Random(11)
    palette = [RUST, OCHRE, PLUM, SAGE, COPPER]
    for _ in range(22):
        px = rnd.randint(80, w - 80)
        py = rnd.randint(int(h * 0.55), int(h * 0.9))
        rr = rnd.randint(34, 80)
        d.ellipse([px - rr, py - rr, px + rr, py + rr],
                  fill=rnd.choice(palette) + (255,))
    centre_text(d, (40, h - 70, 600, h - 30),
                "PLACEHOLDER · harvest-lifestyle", font(28, bold=True),
                (40, 30, 20, 130))
    return img


def kraft():
    """Subtle kraft-paper texture (RGB)."""
    w, h = 1200, 1200
    img = Image.new("RGB", (w, h), (196, 168, 126))
    d = ImageDraw.Draw(img)
    rnd = random.Random(3)
    for _ in range(60000):
        x, y = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        v = rnd.randint(-18, 18)
        base = (196, 168, 126)
        d.point((x, y), fill=tuple(max(0, min(255, c + v)) for c in base))
    return img


def qr():
    """QR-shaped fixture (not a real code) — finder patterns + random grid."""
    n, scale, quiet = 29, 18, 3
    s = (n + quiet * 2) * scale
    img = Image.new("RGB", (s, s), "white")
    d = ImageDraw.Draw(img)
    rnd = random.Random(42)

    def cell(cx, cy, on):
        if on:
            x = (cx + quiet) * scale
            y = (cy + quiet) * scale
            d.rectangle([x, y, x + scale - 1, y + scale - 1], fill=INK)

    def finder(ox, oy):
        for yy in range(7):
            for xx in range(7):
                edge = xx in (0, 6) or yy in (0, 6)
                core = 2 <= xx <= 4 and 2 <= yy <= 4
                cell(ox + xx, oy + yy, edge or core)

    for yy in range(n):
        for xx in range(n):
            if (xx < 8 and yy < 8) or (xx > n - 9 and yy < 8) \
                    or (xx < 8 and yy > n - 9):
                continue
            cell(xx, yy, rnd.random() < 0.46)
    finder(0, 0)
    finder(n - 7, 0)
    finder(0, n - 7)
    return img


def leaf_icon():
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.pieslice([40, 20, 230, 236], 90, 270, fill=SAGE + (255,))
    d.pieslice([26, 20, 216, 236], 270, 450, fill=(120, 150, 110, 255))
    d.line([128, 40, 128, 220], fill=(60, 80, 55), width=8)
    return img


def allergen_icons():
    """A row of circular allergen badges (composite, wide)."""
    labels = ["GF", "VG", "V", "N", "MK"]
    cell, pad = 200, 24
    w = len(labels) * cell
    img = Image.new("RGBA", (w, cell), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, lab in enumerate(labels):
        cx = i * cell + cell / 2
        d.ellipse([i * cell + pad, pad, i * cell + cell - pad, cell - pad],
                  outline=PLUM, width=8, fill=BONE)
        centre_text(d, (i * cell, 0, i * cell + cell, cell), lab,
                    font(72, bold=True), PLUM)
    return img


def plus_badge():
    s = 420
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([10, 10, s - 10, s - 10], fill=COPPER)
    d.ellipse([30, 30, s - 30, s - 30], outline=BONE, width=6)
    centre_text(d, (0, 60, s, 250), "M+", font(180, bold=True), BONE)
    centre_text(d, (0, 250, s, 360), "MEMBER", font(54, bold=True), BONE)
    return img


SVG_LOGO = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 460" role="img"
     aria-label="Meridian Market">
  <g fill="none">
    <circle cx="550" cy="150" r="110" fill="#AC6739"/>
    <line x1="385" y1="150" x2="715" y2="150" stroke="#3F1C5B"
          stroke-width="12"/>
    <path d="M451 150 A110 110 0 0 0 649 150 Z" fill="#CE4623"/>
  </g>
  <text x="550" y="345" text-anchor="middle" font-family="Canela Deck, serif"
        font-weight="600" font-size="150" fill="#3F1C5B">MERIDIAN</text>
  <text x="550" y="410" text-anchor="middle" font-family="Söhne, sans-serif"
        letter-spacing="14" font-size="40" fill="#AC6739">· MARKET ·</text>
</svg>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    EDGE.mkdir(parents=True, exist_ok=True)
    manifest = []

    def save(img, name, fmt, sub=OUT, note="", expect="accepted", **kw):
        ext = {"PNG": "png", "JPEG": "jpg", "TIFF": "tif",
               "GIF": "gif", "WEBP": "webp"}[fmt]
        path = sub / f"{name}.{ext}"
        img.save(path, fmt, **kw)
        manifest.append({
            "name": name, "file": str(path.relative_to(HERE)),
            "format": fmt, "mode": img.mode, "size": list(img.size),
            "bytes": path.stat().st_size, "expect": expect, "note": note})

    # ---- clean, usable set ------------------------------------------------
    save(hero(), "harvest-hero", "JPEG", quality=88,
         note="Editorial food hero, RGB.")
    save(lifestyle(), "harvest-lifestyle", "PNG",
         note="Lifestyle scene, RGB PNG.")
    save(kraft(), "kraft-texture", "JPEG", quality=80,
         note="Background texture, RGB.")
    save(logo(), "meridian-logo", "PNG", note="Primary lockup, alpha.")
    save(logo(reversed_=True), "meridian-logo-reversed", "PNG",
         note="Reversed lockup for dark grounds, alpha.")
    save(logo(mark_only=True), "meridian-mark", "PNG",
         note="Symbol only, square, alpha.")
    save(qr(), "harvest-recipe-qr", "PNG", note="QR-shaped fixture.")
    save(leaf_icon(), "leaf-icon", "PNG", note="Single icon, alpha.")
    save(allergen_icons(), "allergen-icons", "PNG",
         note="Composite allergen row, wide, alpha.")
    save(plus_badge(), "meridian-plus-badge", "PNG",
         note="Member badge, alpha.")

    # ---- edge-case set ----------------------------------------------------
    save(hero().convert("CMYK"), "harvest-hero-cmyk", "TIFF", sub=EDGE,
         expect="accepted-but-no-dims",
         note="CMYK TIFF: sniff() returns mime but width/height None "
              "(no IFD walk). Print-correct colour, but UI shows no dims and "
              "browsers can't preview CMYK TIFF.")
    save(hero().convert("CMYK"), "harvest-hero-cmyk", "JPEG", sub=EDGE,
         quality=88, expect="accepted-but-may-preview-wrong",
         note="CMYK JPEG: accepted (mime+dims read), but many browsers "
              "render Adobe CMYK JPEGs with inverted colour in <img>.")
    save(Image.new("RGB", (5000, 3500), RUST).point(lambda v: v),
         "oversized-banner", "JPEG", sub=EDGE, quality=70,
         expect="accepted-no-size-guard",
         note="5000×3500 — no max-dimension or byte-size guard on upload.")
    save(radial(16, 16, OCHRE, PLUM), "tiny-icon", "PNG", sub=EDGE,
         expect="accepted-tiny",
         note="16×16 — will be scaled up into any real frame; no min-size "
              "or DPI check.")
    save(Image.new("RGB", (3000, 80), PLUM), "extreme-aspect", "PNG",
         sub=EDGE, expect="accepted-extreme-aspect",
         note="37.5:1 strip — aspect ratio is reported but never validated "
              "against the placing frame.")
    save(qr(), "animated-unsupported", "GIF", sub=EDGE,
         expect="rejected-415",
         note="GIF is not sniffed → upload returns 415 unrecognised format.")
    (EDGE / "meridian-logo.svg").write_text(SVG_LOGO)
    manifest.append({
        "name": "meridian-logo", "file": "assets/edge-cases/meridian-logo.svg",
        "format": "SVG", "mode": "vector", "size": [1100, 460],
        "bytes": (EDGE / "meridian-logo.svg").stat().st_size,
        "expect": "rejected-415",
        "note": "The authoritative VECTOR logo master. SVG/EPS/PDF vector "
                "uploads are not supported at all — the headline gap. Vector "
                "logos must currently be hand-rebuilt as native shape/path "
                "items or flattened to PNG, losing scalability."})

    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} assets")
    for m in manifest:
        dims = f"{m['size'][0]}x{m['size'][1]}"
        print(f"  {m['expect']:28} {m['format']:5} {m['mode']:7} "
              f"{dims:12} {m['name']}")


if __name__ == "__main__":
    main()
