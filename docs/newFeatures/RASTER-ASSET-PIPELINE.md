# RASTER-ASSET-PIPELINE.md

## Purpose

This document proposes the next major capability for **ide8.flow**: a **raster asset transformation pipeline** that sits alongside the existing structured document and render flow.

The goal is simple:

> ide8.flow should not only generate and place vector and text-based layout elements — it should also be able to **prepare, transform, and version raster assets** as part of the same end-to-end creative-to-production workflow.

This completes the “flow” in ide8.flow.

---

## Repository review resolution — 27 August 2026

This subsystem is governed by the unified asset/version/operation model in
`IDE8-FLOW-CREATIVE-ORCHESTRATION-PLAN.md`. The following constraints are
binding:

- New assets are project-scoped or explicitly promoted to a shared library.
- Documents reference immutable asset versions; logical names remain a legacy
  schema `0.1`/`0.2` compatibility surface.
- Every transform creates a candidate version. Validation and policy approval
  happen before that version can replace an asset in a document.
- Asset-only replacement is a deterministic document operation that changes
  only the targeted `src` field and rejects unrelated structural changes.
- Durable job state, idempotency and atomic publication are part of Phase 1.
- Ordinary `fit`/`focus`/`zoom` changes use existing document placement
  semantics and do not create duplicate pixel assets.
- The operation vocabulary covers ordinary graphic-design manipulation of
  supplied pixels: background removal, alpha work, monotone/duotone treatments,
  fade overlays, recolouring, crops and similar bounded edits. Duotone is one
  example, not the defining feature.
- The subsystem does not generate a totally new subject, replacement product or
  scene. Any future generative replacement capability is a separate product and
  policy decision.

Assets are project-private by default and generated vectors remain one semantic
asset with their source SVG in the craft bundle, as recorded in the master
plan's **Resolved product decisions** section.

---

## Why this matters

At present, ide8.flow already has the correct core architectural bet:

- the **document is data, not pixels**
- the layout/generation agent creates a structured artwork document
- the renderer (Scribus) assembles the final production output
- raster assets can be placed into the document as referenced assets

That is strong.

However, in real retail POS and artwork production, supplied raster assets are rarely perfect as-is. They often need work before they should be placed into the final design:

- background removal
- transparent output
- duotone treatment
- recolouring to match brand direction
- monotone and gradient/fade treatments
- framing/cropping refinement
- simple cleanup or retouching
- background extension
- shadow extraction or replacement

If ide8.flow cannot handle these operations internally, the workflow breaks and the user has to leave the system.

This proposed pipeline closes that gap.

---

## Core principle

Raster editing should be treated the same way as vector generation:

- **the layout agent decides what is needed**
- **a specialist component performs the asset transformation**
- **the output becomes a versioned asset**
- **the structured ide8 document references that asset**
- **the artwork is re-rendered without regenerating the whole design**

This preserves structure and avoids the weaknesses of “generate the whole page again”.

---

## Desired outcome

A user or internal designer should be able to say things like:

- “Remove the background from the hero product shot”
- “Make this image transparent”
- “Create a visual duotone using the approved BrandRed and BrandYellow swatches”
- “Tighten the crop and centre focus on the product”
- “Create a cleaner cutout version”
- “Apply a branded monochrome treatment”
- “Use the transparent cutout in concepts 2, 4 and 5”

And ide8.flow should be able to:

1. create a derived raster asset
2. store provenance and transformation metadata
3. place the derived asset into the document
4. preserve all existing layout/text/production structure
5. re-render the proof and package output

---

## Architectural position

The raster asset pipeline should become a distinct subsystem in the ide8.flow architecture.

```text
Brief / mutation instruction
          ↓
   Layout / orchestration agent
          ↓
   decides required asset operations
          ↓
┌─────────────────────────────────────┐
│     Raster Asset Transformation     │
│   - background removal              │
│   - transparency                    │
│   - visual duotone                  │
│   - recolour                        │
│   - fade overlay                    │
│   - baked crop when required        │
│   - cleanup / retouch               │
└─────────────────────────────────────┘
          ↓
   Derived raster asset(s)
          ↓
   Asset store + provenance
          ↓
   ide8 structured document
          ↓
   Scribus render / proof / PDF/X
```

This keeps responsibilities clean:

- **LLM / orchestration layer** = decides what should happen
- **image editing service/model** = transforms the raster asset
- **document system** = places the result into the layout
- **renderer** = produces proofs and production files

---

## Scope boundaries

This capability should focus first on **controlled asset transformation**, not unrestricted image generation.

### In scope
- background removal
- transparency / cutout creation
- reusable baked crops when document placement is insufficient
- visual duotone / tritone
- monotone and gradient/fade treatments
- monochrome branded recolouring
- background extension for fitting
- cleanup / minor retouching
- shadow extraction / simple shadow creation
- derived raster asset versioning and provenance
- document references to derived assets

### Out of scope initially
- “make me a totally new hero image from scratch”
- full replacement of supplied product photography
- freeform hallucinated product generation
- unrestricted photo compositing
- replacing brand packshots with invented imagery
- destructive modification of the original asset
- general-purpose Photoshop clone editing UI

The first implementation should be **safe, constrained, and production-oriented**.

---

## Why constrained transformation first

For ide8.flow, the most commercially useful and lowest-risk raster operations are not open-ended generation. They are **production-safe transformations**.

This matters because “regenerate this image” creates serious risk:

- wrong packaging
- altered brand details
- missing or changed labels
- incorrect product proportions
- hallucinated visual content
- brand non-compliance

By contrast, these are much safer:

- remove background
- isolate subject
- make transparent
- apply a defined duotone
- apply a monotone treatment or fade overlay
- adjust crop/focus
- create consistent branded treatments

These operations are exactly the kind of things a designer or studio would repeatedly do.

---

## Proposed asset model

The system should distinguish between **source assets** and **derived assets**.

### Asset classes
- `originalRaster`
- `derivedRaster`
- vector classes share the same asset model but are outside this subsystem
- `brandAsset` is a role/classification, not a competing storage entity

### Required entities

```text
asset
  id, project_id, logical_name, kind, role, fidelity_class, root_asset_id

asset_version
  id, asset_id, parent_version_id, content_hash, mime_type
  width, height, has_alpha, colour_space, ICC profile identity
  validation_status, approval_status, immutable payload/object key

asset_operation
  id, input_version_id, operation_type, normalised_parameters
  operation_fingerprint, provider/model/tool version
  status, cost, error, output_version_id

document_asset_reference
  document_version_id, item_name, asset_version_id
```

An `asset` is the stable logical lineage. An `asset_version` is one immutable
piece of content. A transformation links an input version to a new output
version; it does not create a mutable `derived_asset` row or overwrite a source.

### Asset provenance chain
Every derived asset should preserve lineage back to its source asset.

Example:

```text
hero-product-01.jpg
  ↓ remove_background
hero-product-01.cutout.v1.png
  ↓ visual_duotone(BrandRed, BrandYellow)
hero-product-01.cutout.duotone.v1.png
```

This is important for:
- auditability
- repeatability
- re-rendering
- designer trust
- future replacement or reprocessing
- model/tool benchmarking

---

## Proposed raster operations

Represent transformations explicitly and semantically.

### Initial operations
- `remove_background`
- `apply_alpha_mask` when an explicit mask already exists
- `bake_crop` only when a new pixel asset is genuinely required
- `visual_duotone`
- `visual_tritone`
- `monotone`
- `apply_fade_overlay`
- `recolor_brand`
- `extend_background`
- `retouch_basic`
- `extract_shadow`
- `add_shadow_simple`

`make_transparent` is not a sufficiently defined operation: transparency needs
either background/subject segmentation or an explicit alpha mask. Use
`remove_background` or `apply_alpha_mask` so provenance records what happened.

Likewise, changing how an image is framed in one concept is a document mutation,
not an asset transformation. Use the existing image `fit`, `focus` and `zoom`
fields. `bake_crop` is reserved for a reusable pixel derivative or a provider
that requires pre-cropped input.

When a fade can be expressed as a document-level gradient shape, prefer that
editable composition. Use `apply_fade_overlay` when the fade is intentionally a
reusable part of the derived raster treatment.

### Example operation objects

#### Background removal
```json
{
  "operation": "remove_background",
  "sourceAssetVersion": "av_hero_product_01"
}
```

#### Apply an existing alpha mask
```json
{
  "operation": "apply_alpha_mask",
  "sourceAssetVersion": "av_hero_product_01",
  "maskAssetVersion": "av_hero_product_mask_01"
}
```

#### Visual brand-colour duotone
```json
{
  "operation": "visual_duotone",
  "sourceAssetVersion": "av_hero_product_cutout_01",
  "parameters": {
    "shadowColor": "BrandRed",
    "highlightColor": "BrandYellow",
    "toneMapping": "luminance-linear-v1",
    "preserveTransparency": true,
    "outputProfile": "sRGB IEC61966-2.1"
  }
}
```

#### Concept-local crop/focus — document change, not an asset operation
```json
{
  "type": "image",
  "src": "av_hero_product_01",
  "fit": "cover",
  "focus": [0.54, 0.42],
  "zoom": 1.15
}
```

#### Branded recolour
```json
{
  "operation": "recolor_brand",
  "sourceAssetVersion": "av_hero_product_cutout_01",
  "parameters": {
    "palette": ["BrandPink", "BrandCream"],
    "mode": "monochrome",
    "outputProfile": "sRGB IEC61966-2.1"
  }
}
```

#### Reusable fade overlay
```json
{
  "operation": "apply_fade_overlay",
  "sourceAssetVersion": "av_hero_product_01",
  "parameters": {
    "direction": "bottom-to-top",
    "start": 0.55,
    "end": 1.0,
    "color": "BrandInk",
    "startOpacity": 0.0,
    "endOpacity": 0.7,
    "preserveTransparency": true
  }
}
```

---

## Colour semantics

Two different deliverables must not share the same operation name:

### Visual brand-colour treatment

- Maps source luminance/tones to approved brand colours.
- Produces an ordinary colour-managed raster such as an sRGB PNG with alpha.
- Enters the existing Scribus/PDF/X colour-management path.
- Does not create named Pantone/spot raster channels, even when the selected
  brand swatches originated from Pantone references.
- Must record the tone-mapping algorithm/version and output profile so the
  result is reproducible.

### True spot-channel raster treatment

- Requires a format and renderer/preflight workflow that preserves named raster
  channels and separations.
- Needs a dedicated pinned-Scribus/PitStop/Phoenix technical slice.
- Is not required by the agreed Phase 1 manipulation scope and remains a
  separate future production capability.

Using a Pantone label as a colour instruction does not by itself make a PNG a
spot-colour production asset.

---

## Proposed derived asset metadata

Each derived asset should store enough information to be trustworthy and reusable.

### Suggested fields

```json
{
  "id": "av_hero_product_cutout_duotone_01",
  "assetId": "asset_hero_product",
  "kind": "derivedRaster",
  "parentAssetVersionId": "av_hero_product_cutout_01",
  "rootAssetId": "asset_hero_product",
  "mimeType": "image/png",
  "width": 2400,
  "height": 2400,
  "hasAlpha": true,
  "colourSpace": "RGB",
  "iccProfile": "sRGB IEC61966-2.1",
  "contentSha256": "…",
  "operation": {
    "type": "visual_duotone",
    "parameters": {
      "shadowColor": "BrandRed",
      "highlightColor": "BrandYellow",
      "toneMapping": "luminance-linear-v1",
      "preserveTransparency": true,
      "outputProfile": "sRGB IEC61966-2.1"
    },
    "fingerprint": "sha256(input-hash + canonical-parameters + tool-version)"
  },
  "generator": {
    "service": "raster-transformer",
    "model": "TBD",
    "version": "TBD"
  },
  "instruction": "Create an approved visual brand-colour duotone while preserving transparency.",
  "createdAt": "2026-08-27T00:00:00Z",
  "validationStatus": "passed",
  "approvalStatus": "candidate"
}
```

---

## Document integration

The document model should continue to reference raster assets by asset identity, not by arbitrary file paths.

That means the document remains clean and stable.

### Example document usage
```json
{
  "type": "image",
  "name": "hero-product",
  "frame": [24, 36, 220, 260],
  "src": "av_hero_product_cutout_duotone_01",
  "fit": "cover",
  "focus": [0.5, 0.45],
  "zoom": 1.0
}
```

The important point is:

> the **document does not need to know how the image was produced** — only which approved asset it references.

That separation is ideal.

Schema `0.1` and `0.2` continue to resolve legacy logical names. New immutable
asset-version IDs are the schema `0.3` contract; they must not be silently
backported into stored older documents.

### Deterministic replacement

Replacing an asset in a concept is not a freeform LLM mutation. The service
accepts a parent document version, expected content hash, target item name/role
and approved replacement asset-version ID. It changes only the targeted `src`,
runs validation/proofing, verifies the structural diff, then commits a child
document version. Any failure leaves the parent untouched.

---

## Designer/user workflow

### Example 1 — background removal
1. User uploads `product.jpg`
2. User asks: “Remove the background and make it transparent”
3. ide8.flow creates `product.cutout.v1.png`
4. Derived asset is stored with provenance
5. Layout concept references the cutout version
6. Proof is re-rendered

### Example 2 — duotone transformation
1. User selects existing cutout asset
2. User asks: “Create a visual duotone using approved BrandRed and BrandYellow”
3. ide8.flow creates `product.cutout.duotone.v1.png`
4. New asset appears in the asset/version history
5. Designer swaps it into selected concepts
6. Proofs re-render without touching other layout content

### Example 3 — concept mutation using asset ops
1. Designer opens concept 3
2. Designer says: “Keep the layout, but make the hero image transparent and use the duotone version”
3. ide8.flow transforms or swaps the asset
4. Document remains otherwise unchanged
5. Only the image reference updates
6. Resulting proof preserves text, legal copy, prices, spot paths, bleed, etc.

---

## Benefits to the overall product

This feature materially improves ide8.flow in several ways.

### 1. Completes the workflow
Users stay within ide8.flow instead of needing Photoshop or external editing tools for basic asset prep.

### 2. Preserves structure
The page is not regenerated. The asset is transformed and swapped in.

### 3. Improves mutation quality
Asset-only changes are more controlled and predictable than whole-document regeneration.

### 4. Strengthens provenance
Every asset version becomes inspectable, replayable, and attributable.

### 5. Opens brand-aware treatments
Duotone, monochrome, and approved treatment styles can become part of the brand profile.

### 6. Supports scalable production
Once asset transformations are codified, they can be reused in templates, variants, and VDP workflows.

---

## Brand-aware future

The eventual direction should allow brand profiles to define not just layout constraints, but also **approved raster treatments**.

For example, a brand profile might define:

- approved duotone pairings
- approved monochrome treatments
- preferred shadow style
- preferred cutout handling
- preferred background style
- no-go treatments
- minimum quality/DPI rules
- whether backgrounds may be removed automatically
- whether product photography may be recoloured

### Example future brand profile concept
```json
{
  "rasterTreatments": {
    "approvedDuotones": [
      ["BrandRed", "BrandYellow"],
      ["BrandPurple", "BrandCream"]
    ],
    "allowBackgroundRemoval": true,
    "allowMonochromeRecolour": true,
    "allowFreeformRegeneration": false
  }
}
```

This would make the asset pipeline more deterministic and safer.

---

## Suggested implementation phases

## Phase 1 — production-safe baseline
Build the smallest useful version first.

### Deliver
- asset lineage model
- derived raster asset records
- project scoping and fidelity policy
- durable/idempotent operation jobs
- background removal
- alpha-preserving output
- document-level crop/focus using existing placement controls
- visual brand-colour duotone transformation
- monotone and reusable fade-overlay transformations
- basic API surface
- document reference compatibility
- deterministic asset replacement
- dimensions, alpha, effective-DPI, colour-space and ICC-profile validation
- proof re-render path

### Success condition
A designer can upload an image, remove its background, create a transparent
visual brand-colour duotone derivative, approve it, and place it into a concept
without changing unrelated document structure.

---

## Phase 2 — richer controlled transformations
Expand the supported operations.

### Deliver
- branded recolour / monochrome treatments
- background extension
- cleanup / simple retouch
- shadow extraction or simple shadow generation
- UI affordances for browsing asset variants
- compare original vs derived
- asset swap inside concept detail view

### Success condition
A designer can prepare multiple polished, brand-aligned image variants and quickly test them across concepts.

---

## Phase 3 — intelligent orchestration
Allow the agent to request asset operations automatically as part of generation/mutation.

### Deliver
- orchestration layer can decide to call raster transformations
- creative prompts can describe required treatment
- transformed assets become reusable library objects
- model/tool routing for asset transformation
- brand-aware defaults for transformation selection

### Success condition
The agent can intelligently propose or execute asset treatments as part of the creative flow while preserving operator control and auditability.

---

## Data model contract

The required entities are `asset`, immutable `asset_version`, `asset_operation`
and `document_asset_reference`, as defined above. Do not introduce a separate
mutable `derived_asset` entity: derivation is expressed by version parentage and
the operation record.

Existing name-keyed asset rows migrate to one logical asset plus one immutable
version. The old name remains an alias so schema `0.1`/`0.2` documents replay
unchanged.

---

## Initial API contract

Field naming may still be normalised to the existing API style, but these
resource boundaries and asynchronous operation semantics are required.

### Asset upload
- `POST /projects/{projectId}/assets`

### List/get assets
- `GET /projects/{projectId}/assets`
- `GET /assets/{assetId}`
- `GET /asset-versions/{assetVersionId}`

### Transform asset
- `POST /asset-versions/{assetVersionId}/operations`

Example:
```json
{
  "operation": "visual_duotone",
  "parameters": {
    "shadowColor": "BrandRed",
    "highlightColor": "BrandYellow",
    "toneMapping": "luminance-linear-v1",
    "preserveTransparency": true,
    "outputProfile": "sRGB IEC61966-2.1"
  },
  "idempotencyKey": "client-or-derived-key"
}
```

This returns `202 Accepted` with an operation ID. Poll or subscribe to the
durable operation record; do not hold an HTTP request open across a specialist
provider call.

### Get operation
- `GET /asset-operations/{operationId}`

### Get derived asset history
- `GET /assets/{assetId}/versions`

### Swap asset in a document/concept
- `POST /versions/{documentVersionId}/asset-replacements`

```json
{
  "expectedContentHash": "…",
  "targetItemName": "hero-product",
  "replacementAssetVersionId": "av_hero_product_cutout_duotone_01"
}
```

The endpoint returns a new child document-version ID after validation, proofing
and structural-diff enforcement.

---

## UI suggestions

The UI should remain consistent with ide8.flow’s philosophy: no bloated Photoshop clone.

### Useful UI components
- asset library panel
- original / derived asset timeline
- quick actions:
  - remove background
  - apply existing mask
  - duotone
  - recolour
- concept crop/focus controls that edit document placement without creating an
  asset derivative
- preview compare
- “use in concept” action
- “replace current asset in this concept” action
- derived asset metadata/provenance drawer

### Avoid
- full drawing UI
- layer-heavy bitmap editing UI
- unrestricted freeform editing panels in v1

---

## Validation and quality gates

Raster transformation should include deterministic checks where possible.

### Useful validation checks
- image dimensions present
- output file type valid
- alpha channel status known
- colour space and ICC-profile status known
- minimum effective resolution
- operation parameters valid
- approved colour/treatment rules respected
- asset exists and lineage is intact
- transformed output is renderable
- if used in document, proof round-trip succeeds

### Brand-specific or production-specific checks
- no transparent image accidentally flattened
- no DPI drop below threshold
- no missing linked asset in bundle/package
- no unintended colourspace issue for downstream workflow
- visual duotone is not reported as a named spot separation

---

## Important strategic note

This should **not** become “image generation bolted onto the side”.

The value of ide8.flow is not that it can make pictures.

The value is that it can:

- direct the creation or transformation of assets
- place them semantically into a real document
- preserve live text and production structure
- keep auditability and version history intact
- re-render deterministically into proofs and PDF/X

That is the differentiator.

---

## Recommendation

Proceed with a **raster asset transformation pipeline** as a first-class subsystem of ide8.flow.

Do **not** treat it as a generic image-generation feature.

Treat it as:

> a structured, provenance-aware, production-safe asset-preparation layer that completes the creative-to-production flow.

This is the correct architectural extension of ide8.flow’s existing document-first design.

---

## Immediate next steps for Codex

The architecture review and API/entity proposal are complete. Follow the master
plan delivery sequence:

1. implement project-private asset/version/operation foundations, sharing
   controls and migration
2. add durable/idempotent operation state and fidelity-policy enforcement
3. add deterministic asset replacement with structural-diff tests
4. implement background removal and alpha-preserving candidate output
5. implement versioned monotone/duotone and fade-overlay operations
6. wire approval, replacement, proof re-rendering and craft-bundle provenance
7. add effective-DPI, fidelity, render compatibility and failure-atomicity tests

Do not broaden this into replacement-image generation or true raster
spot-channel work without a separate production contract.

---

## Closing statement

Adding raster asset transformation is not scope creep. It is a natural and necessary completion of ide8.flow’s architecture.

Without it, the flow breaks at the asset-preparation stage.

With it, ide8.flow becomes a much more complete system:

- structured layout generation
- vector asset generation
- raster asset transformation
- deterministic composition
- proofing
- production-safe output

That is a far stronger product than a simple “AI poster generator”.
