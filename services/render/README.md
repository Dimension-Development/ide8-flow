# render service — document JSON → Scribus SLA → PDF / proof

ide8.flow's render engine (PRD RND-1..4, RND-8): a clean JSON document
compiles to Scribus `.sla`, and headless Scribus (1.6.x) acts as the
layout/render engine, producing print PDFs with bleed, crop marks and
spot-colour swatches, plus raster proofs via poppler.

```
document.json ──▶ sla_compiler.py ──▶ doc.sla ──▶ scribus -g -ns -py ──▶ PDF / raster proof
                                                        ▲
                                          the LLM never touches this part
```

**The document format is specified in [`docs/SCHEMA.md`](../../docs/SCHEMA.md)**
(normative, reference v0.1). This README covers the compiler, the FastAPI
service, the Docker image, and implementation notes.

## Why this shape

The LLM authors the **document**, never the SLA. The document is page-relative,
declarative, and small; the compiler absorbs every Scribus quirk. The render
loop (`compile → export PDF → rasterise → model inspects the image → mutate
document`) was validated end-to-end during the spike, including catching and
fixing a contrast bug purely from looking at the rendered proof.

## Files

- `sla_compiler.py` — the compiler. Stdlib only. Byte-stable output
  (deterministic item IDs); structural validation collects all errors as
  `{code, path, message}` for generation repair loops (PRD GEN-3).
- `template.sla` — donor boilerplate: an empty document saved by the target
  Scribus version (1.6.1 — this file *is* the version pin). Supplies ~170
  `DOCUMENT` preference attributes and required children. Regenerate with
  `service/scribus_scripts/gen_donor.py` when bumping Scribus.
- `service/app.py` — FastAPI service: `/compile`, `/proof`, `/package`,
  `/fonts`, `/healthz`. Per-request temp dirs, no shared state.
- `service/scribus_scripts/` — scripts that run *inside* headless Scribus:
  `export_pdf.py` (SLA → PDF, proof/package modes), `gen_donor.py`.
- `examples/example.json` — a 2-page POS header card exercising every feature.
- `tests/` — unittest suite (golden byte-compare, determinism, error codes)
  plus `check_separation.py`, the RND-3 acceptance check.
- `tests/golden/out.sla` — golden fixture; byte-identical recompile is a CI
  gate and an M0 exit criterion.
- `Dockerfile` — ubuntu:24.04 (Scribus 1.6.1) + xvfb + poppler + fonts.

## Usage

Compiler only (no Scribus needed):

```bash
python3 sla_compiler.py examples/example.json out.sla            # template.sla auto-found
python3 sla_compiler.py bad.json out.sla --errors-json           # {ok, errors} for repair loops
python3 -m unittest discover tests                               # test suite
```

Full service:

```bash
docker build -t ide8-render .
docker run --rm -p 8000:8000 ide8-render

curl localhost:8000/healthz
curl -X POST localhost:8000/compile -H 'content-type: application/json' \
     --data @examples/example.json -o doc.sla
curl -X POST 'localhost:8000/proof?dpi=150&page=1' --data-binary @doc.sla -o proof.png
curl -X POST localhost:8000/package --data-binary @doc.sla -o out.pdf
python3 tests/check_separation.py out.pdf CutContour             # RND-3 acceptance
```

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
7. **Deterministic item IDs** allocated sequentially in document order from
   `ITEM_ID_BASE` — identical input compiles to byte-identical output.

## Render-pipeline limits (current state)

- **Spot → PDF separation — RESOLVED (RND-3).** Root cause was never CMS
  prefs: `PDFfile.outdst` defaults to 0 (screen output), which converts all
  colour to RGB — spots cannot survive that path regardless of `usespot`.
  Package export sets `outdst = 1` (printer); the named
  `/Separation /CutContour` is now present and gated in CI. Note for tests:
  asserting "PDF contains a `/Separation`" is a **false pass** (crop marks
  always contribute `/Separation /All`) — use `tests/check_separation.py`.
- **PDF/X conformance — done.** `/package` emits PDF/X-4 by default:
  `GTS_PDFXVersion` marker, output intent (`ISO Coated v2 300% (basICColor)`,
  bundled with Scribus), named spots intact. Env overrides: `PDFX_VERSION`
  (10 = X-4, 11 = X-1a, 12 = X-3), `PDFX_PROFILE`, `PDFX_INFO`. All three X
  levels verified to preserve the named separation. PitStop preflight of a
  packaged PDF is the remaining M0 exit check (licensed production
  environment).
- **Per-request Scribus spawn (RND-4).** Measured in-container: ~0.5 s per
  headless export, ~0.6 s proof round trip over HTTP — already inside the
  2 s p95 budget, so the warm-process pool is an optimisation held in
  reserve, not a blocker.
- **Version pinning.** SLA changes across the 1.5/1.6/1.7 series. The donor
  template is the pin. Regenerate the donor (`gen_donor.py`) + re-harvest
  object defaults + regenerate golden fixtures when upgrading.

Roadmap beyond this service (formal JSON Schema, validation layer, IDML)
is tracked in the PRD by requirement ID — see `docs/PRD.md` §7.5–7.6 and the
M0/M1 milestones. This README intentionally carries no roadmap of its own.
