# ide8.flow document schema — reference v0.1

> **Version index:** this file is the immutable `0.1` reference. New documents
> may opt into [`0.2`](./SCHEMA-0.2.md), whose formal schema adds gradients,
> shape/image opacity and deterministic image placement. A stored document
> always replays under the schema version recorded in its own `version` field.

**Normative spec** for the document JSON that the generation engine authors and the compiler consumes (PRD §13.2). The formal JSON Schema is [`schema/document-0.1.schema.json`](../schema/document-0.1.schema.json) (VAL-1); this file remains the human-readable contract — the two must not drift. Compiler implementation notes (donor template, scratch-space translation, PTYPE defaults) live in the spike README alongside `sla_compiler.py`.

## Terminology

A generated concept artefact is a **document** (document JSON). The specification it conforms to — this file — is the **document schema**. "Schema" alone always means the latter.

## Top level

`version` · `meta` · `page` · `swatches` · `charStyles` · `paraStyles` · `pages`

- **version** (required) — the document-schema version this document conforms to (currently `"0.1"`). Stored documents are **never migrated**: each persisted `doc_version` replays through the compiler and render image pinned to its recorded schema version (PRD §8).
- **meta** — `{title}`. Compiles to the SLA document title.

## Coordinates

All coordinates are **page-relative points** (1 pt = 1/72″), origin top-left. Negative coordinates reach into the bleed.

## page

- `size` — a named size (`A0`–`A5`, `SRA3`, `LETTER`, `TABLOID`) or `[w, h]` in points.
- `orientation` — `portrait` | `landscape`.
- `margins` — `[left, right, top, bottom]`. **Not CSS order** — this deliberately matches Scribus `BORDERLEFT/RIGHT/TOP/BOTTOM`.
- `bleed` — a single value applied to all sides.

**One page size per document.** A multi-format brief produces one document per format (PRD BRF-2, VAR-1); formats are never mixed within a document. All pages in a document share the `page` spec.

## swatches

`{name, space: "cmyk"|"rgb", values: [..], spot: bool}`

CMYK values are 0–100, RGB 0–255. Objects and styles reference swatches by name, exactly like a swatch panel. `spot: true` survives the round trip into Scribus (verified via `isSpotColor`). PDF-export separation status is a render-pipeline concern — see the spike README and PRD RND-3.

## charStyles

`{name, font, size, color, tracking?}`

`font` must be a PostScript-resolvable family+style name available to Scribus on the render host. `color` is a swatch name (compiles to `FCOLOR` — Scribus uses `FCOLOR` for text fill and `SCOLOR` for stroke; getting this wrong renders black text).

## paraStyles

`{name, charStyle, align, lineHeight?, spaceBefore?, spaceAfter?, indent?, firstIndent?}`

- `align` — `left` | `center` | `right` | `justify` | `force`.
- `lineHeight` is **absolute points**, never a CSS-style multiplier: 48pt
  display type wants `lineHeight` ≈ 52, not 1.1. A multiplier-looking value
  compiles to ~1pt leading and stacks every line on the same baseline
  (validated as `lineheight-not-points`, VAL-3). Omitting `lineHeight`
  selects automatic leading.
- `spaceBefore`/`spaceAfter` compile to the legacy German attributes `VOR`/`NACH`.
- `charStyle` links via `CPARENT`.

## pages & items

`pages` is an array of `{items: [...]}`.

### Common to every item

- `frame` — `[x, y, w, h]`, page-relative points.
- `name` (optional but recommended) — stable identifier, compiles to `ANNAME`. This is the anchor for per-region comment pins (PRD REV-3) and audit references; generators should name every meaningful item.
- `fill` — swatch name. `stroke` — `{color, width}`.

Fill/stroke applicability by item type:

| type | `fill` | `stroke` |
|---|---|---|
| `text` | frame background | frame border |
| `shape` | ✓ | ✓ |
| `image` | frame background | frame border |
| `path` | **invalid** — cut/crease paths are stroke-only, no fill (PRD VAL-3) | required |

### text

`{frame, paragraphs: [...], columns?, columnGap?, padding?}`

Each paragraph is `{style, text}` or `{style, runs: [{text, charStyle?}]}` for mixed inline styling. `padding` applies to all four insets.

### shape

Closed filled/stroked shape. `{frame, fill?, stroke?, d?}`. `d` is an SVG path *relative to the frame*; omitted, you get a rectangle.

### path

Open vector path (cut paths, creases). `{frame, d, stroke}`. Stroke colour is typically a `spot: true` swatch (e.g. `CutContour`).

### image

`{frame, src, fit: "frame"|"free", stretch?}`. `src` is an **asset name** (kebab-case, e.g. `"brand-wordmark"`) from the asset library — never a file path. The pipeline validates the name (`missing-asset` is a hard failure, RND-5), rewrites it to a staged relative path at compile time, and ships the file to the render host with each render request. SLA references images by path and does not embed them.

## Schema-scope limits (not yet modelled)

Linked/chained text frames (`NEXTITEM`/`BACKITEM` — PRD RND-6), master-page content, text-on-path, gradients, transparency groups, ICC intent per image, tables.

## Roadmap

This spec is intentionally minimal; evolution is tracked in the PRD, not here:

- Formal JSON Schema + validation layer — VAL-1..4, VAL-6..7 (M1)
- Render service endpoints wrapping the compiler — RND-1 (M0)
- Byte-stable compilation (deterministic item IDs) — RND-2 (M0)
- Brand-profile merge at compile time — BRAND-2 (M1)
- IDML export — RND-7 (P2)
