# Synthetic agency-card 0.2 conformance fixture

This fixture is deliberately non-brand: no BYOMA material, people, product,
logo, typeface or copy is present. It proves the construction requested for the
pilot, not its eventual art direction.

## What it proves

- 150 × 150 mm trim, 3 mm bleed and 6 mm safe-area margins;
- two-swatch linear gradient background;
- transparent synthetic cut-out image occupying the left half, using cover,
  focus and zoom from trusted `400 × 600px` metadata;
- right-side copy hierarchy and a logo clear-space placeholder;
- two filled rounded-star vector `shape.d` motifs at 50% opacity;
- an open, named `CutContour` spot path;
- byte-stable compile plus repeatable proof/package semantic checks.

## Reproduce

```bash
python3 make_asset.py
docker compose build render
docker compose up -d render
curl localhost:8127/healthz
python3 run_conformance.py
```

`run_conformance.py` runs compile/proof/package twice, checks pixel-identical
443 × 443px 72-dpi bleed-inclusive proofs, overflow report, PDF/X marker, output intent,
embedded font data and named `CutContour`. It writes the human-reviewable
`proof-synthetic.png` beside this README; it is intentionally ignored because
it is a reproducible renderer artefact.
