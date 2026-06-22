# Harvest Edit — maximal brief fixture

A deliberately exhaustive creative brief for the fictional retailer **Meridian
Market**, built to push every part of ide8.flow and surface gaps. It carries
everything a real 2D design brief would: brand guidelines (colour incl. spot,
a full type system, logo lockups), photography, icons, a structured copy deck
with legal, a multi-format kit, die-cut shapes and production specs.

| File | What |
|---|---|
| `brand_profile.json` | Brand guidelines (BRAND-1): swatches incl. 2 spot + 1 RGB, font stack, char/para styles, logo assets, rules |
| `brief.json` | The machine brief (BRF-1/2): multi-format kit, copy deck, mandatory elements, references, production |
| `gen_assets.py` | Pillow generator → `assets/` (usable) + `assets/edge-cases/` (deliberately awkward) + `manifest.json` |
| `assets/` | 10 usable images (hero, lifestyle, texture, logos, QR, icons, badge) |
| `assets/edge-cases/` | CMYK TIFF/JPEG, oversized, tiny, extreme-aspect, SVG vector master, GIF |
| `load.py` | Loads the brand + assets into a running worker and fires a fan-out |

The human-readable brief and the gap analysis live under
[`docs/briefs/harvest-edit/`](../../../../docs/briefs/harvest-edit/) —
`BRIEF.md` and `GAPS.md`.

## Regenerate the images

```bash
python3 gen_assets.py        # needs Pillow; writes assets/ + manifest.json
```

## Run it through the local stack

```bash
# render on :8127 (docker), worker on :8200 (uvicorn) — see services/worker/README.md
python3 load.py                 # brand + clean assets + a 2-concept draft run
python3 load.py --edge          # also try the edge-case uploads (some return 415)
python3 load.py --n 4 --engine standard --no-generate
```

`load.py` prints each upload's status so the edge-case rejections (SVG/GIF →
415) and quirks (CMYK, oversized) are visible. What the brief exposes — and what
this change closes vs. defers — is tracked in
[`GAPS.md`](../../../../docs/briefs/harvest-edit/GAPS.md).
