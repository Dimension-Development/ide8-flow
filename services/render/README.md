# sla-compiler spike — document JSON → Scribus SLA

The proven spike behind ide8.flow's render engine (PRD §13.1): a clean JSON
document compiles to Scribus `.sla`, and headless Scribus (1.6.x) acts as the
layout/render engine, producing print PDFs with bleed, crop marks and
spot-colour swatches.

```
document.json ──▶ sla_compiler.py ──▶ doc.sla ──▶ scribus -g -ns -py ──▶ PDF / raster proof
                                                        ▲
                                          the LLM never touches this part
```

**The document format is specified in [`docs/SCHEMA.md`](../../docs/SCHEMA.md)**
(normative, reference v0.1). This README covers the spike artefacts, usage,
and compiler implementation notes only.

## Why this shape

The LLM authors the **document**, never the SLA. The document is page-relative,
declarative, and small; the compiler absorbs every Scribus quirk. The render
loop (`compile → export PDF → rasterise → model inspects the image → mutate
document`) was validated end-to-end during development, including catching and
fixing a contrast bug purely from looking at the rendered proof.

## Files

- `sla_compiler.py` — the compiler. Stdlib only, no dependencies.
- `template.sla` — donor boilerplate: an empty document saved by the target
  Scribus version (1.6.1 — this file *is* the version pin). Supplies ~170
  `DOCUMENT` preference attributes and required children (`CheckProfile`,
  `Printer`, `PDF`, `LAYERS`, `PageSets`, …). Regenerate it from any Scribus
  version you want to pin to.
- `examples/example.json` — a 2-page POS header card exercising every feature.
- `tests/golden/out.sla`, `tests/golden/out.pdf` — compiled output and headless
  PDF export, as proof. These become real golden-file CI fixtures in M0, once
  compilation is byte-stable (PRD RND-2).

## Usage

```bash
python3 sla_compiler.py examples/example.json out.sla
xvfb-run -a scribus -g -ns -py export.py
```

`export.py` is illustrative — any Scribus scripter export script works; it is
not part of the spike artefacts. The production export script ships with the
render service (PRD RND-1).

## Compile rules (what the compiler absorbs)

1. **Scratch-space translation.** Scribus positions everything in a global
   canvas: page *n* sits at `(100, 20 + n × (pageH + 40))`. Item `XPOS/YPOS`
   are page position + page-relative frame origin.
2. **Boilerplate via donor.** Never author `DOCUMENT` attributes by hand; clone
   them from a real save and override only `ANZPAGES`, dimensions, bleeds,
   margins.
3. **Per-PTYPE attribute defaults.** Page objects need their full attribute
   set; defaults were harvested from Scribus-saved objects per type
   (4 = text, 6 = shape, 7 = polyline, 2 = image) and only meaningful
   attributes are overridden.
4. **Geometry as SVG path syntax.** Scribus 1.5+ stores object geometry as
   `path="M0 0 L…Z"` — emitted directly, which is also the syntax LLMs write
   most fluently.
5. **Text as runs.** `StoryText` → `DefaultStyle PARENT=` + `ITEXT` runs
   (`CPARENT` for inline char-style overrides) + `<para>` separators +
   `<trail>` terminator.
6. **Page mapping** via `OwnPage` on every object.

## Render-pipeline limits (spike state)

- **Spot → PDF separation — verified open issue.** The spot flag round-trips
  into Scribus (`isSpotColor` confirms it), but the spike's exported PDF
  contains only `/Separation /All` (the registration colour from the crop
  marks); the string `CutContour` appears nowhere in the PDF — the spot was
  converted to process despite `usespot=True`. Consequence for testing:
  asserting "PDF contains a `/Separation`" is a **false pass**; the M0
  acceptance test must assert the *named* separation, `/Separation /CutContour`
  (PRD RND-3). Suspected cause: colour-management prefs in a bare container.
  Fallback: PitStop action-list spot recolouring (already licensed).
- **Non-deterministic item IDs.** The spike compiler generates `ItemID` via
  unseeded `random.randint`, so recompiling the same document produces a
  different SLA. This violates the byte-stable compilation requirement
  (PRD RND-2) and blocks golden-file CI; the fix is an M0 task.
- **Version pinning.** SLA changes across the 1.5/1.6/1.7 series. The donor
  template is the pin. Regenerate the donor + re-harvest object defaults when
  upgrading.

Roadmap beyond the spike (formal JSON Schema, render endpoints, validation
layer) is tracked in the PRD by requirement ID — see `docs/PRD.md` §7.5–7.6
and the M0/M1 milestones. This README intentionally carries no roadmap of its
own.
