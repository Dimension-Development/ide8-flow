# ide8.flow — Creative Orchestration Evolution Plan

## Purpose

This document defines the next architectural evolution of **ide8.flow** following the recent review of the current repository, the emergence of genuine native-vector generation, and the decision to add first-class raster asset transformation.

It is intentionally broader than `RASTER-ASSET-PIPELINE.md`.

The raster plan remains the detailed specification for one subsystem. This document is the **master implementation plan** that coordinates the wider changes required across ide8.flow:

- provider-independent model orchestration
- newer generation and critique models
- independent creator/judge routing
- specialist vector generation via Recraft
- first-class vector assets
- raster asset transformation
- asset provenance and lineage
- brand-aware asset treatments
- schema evolution
- validation and production safety
- UI changes
- evaluation and benchmarking
- staged rollout without destabilising the proven Scribus/PDF-X pipeline

The objective is not to turn ide8.flow into a generic image generator.

The objective is to evolve it into a **production-aware creative orchestration system**.

---

## Repository review resolution — 27 August 2026

The architecture pass against the current repository has been completed. The
following findings are now binding implementation constraints for this plan:

1. Existing assets are global, write-once BLOBs keyed by logical name. New asset
   work must introduce project-scoped immutable identities without changing how
   stored schema `0.1` and `0.2` documents replay.
2. The repository proves inline single-path vector geometry, not arbitrary SVG
   placement. Native SVG must pass a pinned-Scribus feature harvest before
   schema `0.3` is frozen.
3. Provider independence requires normalised model turns, tool calls, usage and
   errors. Product operations such as generation, mutation and judging remain
   above the provider boundary.
4. Independent judge results need first-class attempt/evaluation records. One
   `critique_json` field on the final document version is insufficient.
5. Asset-only mutation must be deterministic and enforced by structural diff;
   prompt wording alone is not a minimal-change guarantee.
6. Durable job state, idempotency, project policy and atomic candidate
   publication are prerequisites of the first external vector/raster call, not
   a final hardening exercise.
7. Raster work is controlled manipulation of supplied assets, not generation of
   replacement imagery. Monotone/duotone treatments, background removal, fades,
   crops and similar designer operations are examples of the extensible
   operation vocabulary, not separate product pillars.

The product choices raised by the review are recorded as resolved decisions near
the end of this document. Everything else in this plan should be read
consistently with the constraints above.

---

# 1. Executive decision

The current core architecture should **not** be replaced.

The following decisions remain sound and should be preserved:

1. **The document is data, not pixels.**
2. The canonical creative artefact remains ide8.flow's renderer-neutral structured document.
3. The layout/generation model never authors Scribus SLA directly.
4. Validation remains deterministic wherever a rule can be expressed deterministically.
5. Scribus remains the production renderer until a real creative or production limitation justifies a replacement.
6. Raster imagery, generated vectors, typography and production geometry remain separate semantic objects.
7. PDF/X, named spot separations, PitStop and Phoenix remain downstream production authorities.
8. Human review remains part of the creative and release process.

The architectural change is therefore **additive and modular**, not a rewrite.

---

# 2. Strategic shift

ide8.flow originally centred around a capable general-purpose model authoring structured layouts.

The next version should become an orchestrator that can choose the right specialist for each creative task.

The conceptual shift is:

```text
OLD

Brief
  ↓
General-purpose LLM
  ↓
ide8 document
  ↓
Scribus
  ↓
PDF/X
```

to:

```text
TARGET

Brief / mutation / art direction
              ↓
     Creative orchestration agent
              ↓
   ┌──────────┼───────────┬─────────────┐
   │          │           │             │
   ▼          ▼           ▼             ▼
Layout     Vector       Raster       Independent
model      generator    editor       visual judge
   │          │           │             │
   └──────────┴───────────┴─────────────┘
              ↓
      Versioned asset/document graph
              ↓
          ide8 document
              ↓
      deterministic validation
              ↓
            Scribus
              ↓
        Proof / PDF-X-4
              ↓
       PitStop / Phoenix
```

The key principle is:

> **Specialist models create or transform components. ide8.flow remains responsible for the artwork.**

---

# 3. Product outcome

A designer should eventually be able to give ide8.flow a brief containing copy, brand rules, product photography, logos and reference material, then ask for six creative directions.

ide8.flow should be able to decide that a particular concept needs:

- a supplied hero photograph
- the background removed from that photograph
- a two-colour brand duotone treatment
- a newly generated vector flourish
- live headline and body typography
- a branded price flash
- a supplied vector logo
- a spot-colour cutter path
- a specific image crop
- a specific hierarchy and composition

Each component should remain independently editable, traceable and replaceable.

A later mutation such as:

> “Keep everything, but make the hero image duotone and replace the botanical flourish with something looser and more hand-drawn.”

should result in:

1. one raster derivative being created or selected
2. one vector asset being regenerated
3. the document updating only those asset references
4. all text, geometry and production structure remaining untouched
5. a new proof being rendered
6. the new version being added to the immutable history

That is the target behaviour.

---

# 4. Non-goals

This work should **not** introduce:

- a Photoshop clone
- a full Illustrator clone
- a general drawing canvas
- whole-page raster generation as the canonical artwork
- destructive modification of uploaded source assets
- uncontrolled autonomous production release
- model-specific document formats
- renderer-specific fields leaking into the canonical document
- vendor lock-in to Recraft, Anthropic, OpenAI, Google or Adobe
- replacement of Scribus without demonstrated need

---

# 5. Current architecture to preserve

The existing repo already contains several foundations that should be reused rather than rebuilt:

- renderer-neutral JSON document schema
- JSON → Scribus SLA compiler
- deterministic/byte-stable compilation
- PDF/X-4 packaging
- named spot separations
- image assets referenced by logical name
- brand-profile merge
- immutable document versions
- validation and repair loop
- raster proof generation
- multimodal proof critique
- mutation API
- cost metering
- templates / deterministic bind-and-render
- craft-pass bundle
- schema versioning
- schema `0.2` gradients, opacity and deterministic image placement
- BYOMA technical vertical slice proving the current renderer is still viable

The work in this plan should build **around those seams**.

---

# 6. Target subsystem boundaries

The target architecture should separate six concerns.

## 6.1 Creative orchestration

Responsible for:

- interpreting the brief
- selecting a creative direction
- deciding which assets are needed
- deciding whether an existing asset can be used
- requesting vector generation
- requesting raster transformation
- authoring layout/document structure
- deciding when to ask for another creative iteration

It should **not** render files or perform production transformations itself.

---

## 6.2 Layout/document generation

Responsible for:

- page composition
- hierarchy
- typography
- frame geometry
- asset placement
- brand-compliant swatch/style references
- document mutations
- outputting valid ide8 document JSON

This remains the job of a strong general-purpose multimodal/tool-using model.

---

## 6.3 Vector asset generation

Responsible for creating self-contained vector illustrations or design components.

Initial specialist:

- **Recraft native vector generation**

Examples:

- botanical motifs
- decorative flourishes
- abstract shapes
- iconography
- bursts
- badges
- geometric compositions
- patterns
- illustrated accents
- large hero illustrations where appropriate

Recraft should **not** own:

- page layout
- legal copy
- live typography
- logos
- production paths
- document dimensions
- PDF/X production

---

## 6.4 Raster asset transformation

Responsible for transforming supplied raster assets while preserving lineage.

Detailed in:

`RASTER-ASSET-PIPELINE.md`

Initial capabilities:

- background removal
- alpha/transparency manipulation
- document-level crop/focus and reusable baked crops where required
- monotone, duotone and tritone tonal treatments
- monochrome/brand recolour
- gradient/fade overlays
- background extension
- simple retouching
- basic shadow operations

This subsystem should return **derived assets**, never silently overwrite originals.

---

## 6.5 Independent visual evaluation

Responsible for evaluating rendered proofs independently of the model that created them.

It should judge:

- composition
- hierarchy
- balance
- typography
- brand authenticity
- imagery treatment
- legibility
- craft
- brief fulfilment
- whether a concept is worthy of human review

The creator should no longer be the only judge of its own output.

---

## 6.6 Production rendering and validation

Responsible for:

- schema validation
- brand rules
- geometry
- copy integrity
- image resolution
- asset availability
- spot-colour rules
- overflow detection
- rendering
- PDF/X packaging
- production handoff

This remains deterministic wherever possible.

---

# 7. Workstream A — Model provider abstraction

## Goal

Remove Anthropic-specific assumptions from the generation engine so ide8.flow can benchmark and route models from multiple providers without changing the canonical document contract.

## Current limitation

The generation loop is currently tightly aligned to Anthropic's tool-use and message API.

That was appropriate for M1, but the document schema now gives ide8.flow a strong vendor-neutral output contract.

## Required change

Introduce an internal provider interface.

Conceptually:

```text
ModelProvider
│
├── AnthropicProvider
├── OpenAIProvider
└── GoogleProvider
```

Each provider should expose a common transport-level contract for:

- system and user messages
- structured tool definitions and forced tool choice
- text and image inputs
- normalised text/tool-call outputs
- normalised token/cost usage
- model identity/version
- error normalisation
- retries/timeouts
- capability declaration

## Suggested interface

```python
@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

@dataclass
class ModelRequest:
    model: ModelRef
    system: list[ContentBlock]
    messages: list[Message]
    tools: list[ToolDefinition]
    forced_tool: str | None = None
    max_output_tokens: int | None = None

@dataclass
class ModelResponse:
    content: list[ContentBlock]
    tool_calls: list[ToolCall]
    usage: NormalizedUsage
    finish_reason: str | None
    provider_request_id: str | None

class ModelProvider:
    def invoke(self, request: ModelRequest) -> ModelResponse:
        ...

    def capabilities(self, model: ModelRef) -> ModelCapabilities:
        ...
```

`emit_document`, `mutate_document` and `critique_proof` are ide8 workflows, not
provider methods. They should continue to live in the generation/orchestration
layer and consume the normalised request/response contract.

Provider-specific features such as Anthropic cache-control blocks or provider
response IDs may be used inside adapters, but must not be required by the
canonical loop.

The exact implementation is open, but provider-specific request/response structures must not leak into the wider worker.

## Initial model candidates

### Anthropic
- current Sonnet-class model as baseline
- current Opus-class model for escalation

### OpenAI
- current GPT-5.6 family candidates for layout and/or visual critique

### Google
- current Gemini high-throughput multimodal candidate

Model names should be configuration, not hard-coded architectural assumptions.

## Acceptance criteria

- the same brief can run through at least two providers
- both produce the same ide8 document schema
- validation errors are provider-neutral
- provenance records provider + model
- cost/usage remains measurable
- switching providers requires configuration, not application rewrites

---

# 8. Workstream B — Creator / judge separation

## Goal

Stop relying entirely on the same model/conversation to create a design and approve its own proof.

## Why

Creative models can have correlated blind spots:

- a questionable layout choice may look reasonable to the model that invented it
- stylistic weaknesses may survive self-critique
- repeated self-revision may converge on the same local optimum

## Target pattern

```text
Creator model
     ↓
ide8 document
     ↓
validation
     ↓
rendered proof
     ↓
Independent judge model
     ↓
approve / critique
     ↓
Creator revises
```

## Routing should be configurable

Examples:

```text
Sonnet → GPT judge
GPT → Gemini judge
Gemini → Opus judge
```

A model should optionally be disallowed from judging its own generation during benchmark runs.

## Judge output schema

The judge should return a structured scorecard, not free prose only.

Suggested shape:

```json
{
  "rubricVersion": "creative-scorecard-1",
  "approve": false,
  "confidence": 0.82,
  "scores": {
    "briefFulfilment": 8,
    "brandAuthenticity": 6,
    "composition": 5,
    "typography": 7,
    "imagery": 8
  },
  "issues": [
    {
      "severity": "major",
      "region": "hero-image",
      "issue": "Image dominates headline hierarchy",
      "suggestedFix": "Reduce image width or increase headline scale"
    }
  ]
}
```

Production readiness must not be inferred from the visual judge. Schema,
overflow, effective DPI, separations, fonts and PDF/X remain deterministic
gates. The judge evaluates creative quality after those gates pass.

## Attempt and evaluation persistence

Every proof sent to a judge should have a durable `creative_attempt` identity.
Every judge response should be an immutable `judge_evaluation` linked to that
attempt, including rubric version, provider/model, usage and scorecard.

Rejected repair attempts do not need to clutter the designer-facing document
version timeline, but they must remain inspectable. A surfaced or approved
attempt is promoted to a `doc_version` and retains the link to its attempt and
evaluations.

## Acceptance criteria

- creator and judge can be independently configured
- scorecards persist with document versions
- critiques can feed the repair loop
- human reviewers can see why a concept was rejected or surfaced
- benchmark reports can compare judge agreement with human designers
- rejected attempts remain inspectable without becoming document versions

---

# 9. Workstream C — First-class vector asset system

## Goal

Allow ide8.flow to commission, store, version, validate and place native vector artwork generated by specialist models.

## Key decision

Do not treat complex generated vector artwork as a giant inline `shape.d` blob.

Add first-class vector asset semantics.

## Proposed document item

Schema `0.3` should consider a new item such as:

```json
{
  "type": "vectorAsset",
  "name": "hero-botanical-flourish",
  "src": "campaign-flourish-03",
  "frame": [24, 36, 310, 180],
  "fit": "contain",
  "opacity": 0.7
}
```

The document should reference an asset identity.

The asset record owns the generated SVG.

## Proposed vector asset metadata

```json
{
  "id": "campaign-flourish-03",
  "kind": "generatedVector",
  "mimeType": "image/svg+xml",
  "generator": {
    "provider": "recraft",
    "model": "configured-vector-model",
    "version": "recorded-at-generation"
  },
  "prompt": "...",
  "viewBox": [0, 0, 1000, 500],
  "sha256": "...",
  "status": "approved"
}
```

## Recraft adapter

Create a dedicated adapter/service boundary:

```text
VectorGenerator
└── RecraftVectorProvider
```

Do not call Recraft directly from random worker code.

The interface should make later providers possible.

## Generation request

The layout/orchestration agent should request an asset semantically.

Example:

```json
{
  "role": "decorative-flourish",
  "prompt": "Loose hand-drawn botanical flourish with rounded leaves",
  "aspectRatio": "2:1",
  "palette": ["BrandPink", "BrandYellow"],
  "constraints": {
    "noText": true,
    "simpleGeometryPreferred": true
  }
}
```

## SVG ingestion/sanitisation

Generated SVG must pass a deterministic ingestion gate.

Checks should include:

- no scripts
- no external network resources
- no embedded arbitrary HTML
- no unsupported filters
- no unexpected raster embedding unless explicitly allowed
- no generated text objects unless explicitly allowed
- finite viewBox
- finite path coordinates
- complexity/node-count ceiling
- supported gradients/transparency only
- colour extraction
- renderer compatibility
- successful proof render

## Initial renderer path

The current repository does not prove that an external SVG can be placed through
an image `PFILE` and remain vector in the packaged PDF. The first vector task is
therefore a pinned-Scribus feature harvest, not a schema change.

Unless that harvest demonstrates a simpler deterministic route, the initial
implementation should:

1. retain the original sanitised SVG as the immutable asset payload
2. parse an explicitly allowed SVG subset into a normalised vector scene
3. flatten supported transforms into finite path coordinates
4. reject text, scripts, external resources, filters, clipping, masks and
   unsupported paint features
5. map colours through the asset/brand palette policy
6. pass the normalised scene to the compiler as trusted asset metadata
7. emit deterministic native Scribus page objects with stable item IDs
8. verify that packaged PDF geometry remains vector

Runtime GUI import or opaque provider-generated SLA is not an acceptable
production path. The source SVG remains in the craft bundle even when the
compiler consumes its normalised representation.

## Colour policy

Support at least:

- `preserve`
- `brand-map`
- `strict-brand`

`strict-brand` should reject colours outside approved brand swatches.

`brand-map` may map generated colours onto the closest/assigned approved swatches.

## Acceptance criteria

- Recraft can generate an SVG asset
- ide8 stores it with provenance
- the SVG passes sanitisation
- the document references it as a vector asset
- Scribus/PDF output preserves vector geometry
- the asset can be replaced without regenerating the rest of the document
- an asset mutation creates a new vector version, not an overwrite

---

# 10. Workstream D — Raster asset transformation

## Goal

Complete the asset-preparation flow for supplied photography and raster artwork.

The detailed design is defined separately in:

`RASTER-ASSET-PIPELINE.md`

This master plan adds the integration requirements.

## Integration requirements

Raster transformations must:

- share the common asset/version model
- use the same provenance conventions as generated vectors
- never destroy original files
- be callable by the orchestration layer
- be callable explicitly by users
- support concept-local asset replacement
- work with document mutation/version history
- feed image dimensions/alpha metadata back into validation
- support brand treatment rules

## Phase 1 raster operations

- remove background
- preserve/create transparency
- document-level crop/focus and explicit baked crop when required
- monotone/duotone/tritone tonal treatments
- monochrome brand recolour
- gradient/fade overlay

These are an initial controlled-operation set, not an exhaustive list. New
operations are acceptable when they transform supplied pixels predictably,
preserve lineage and fidelity policy, and do not synthesize a replacement
subject or scene.

## Later model-driven operations

- background extension
- cleanup
- reflection cleanup
- shadow refinement
- light retouch
- creative but bounded background changes

## Acceptance criteria

The Phase 1 success case remains:

> Upload an image → remove background → create a transparent two-colour derivative → place it into an existing concept → re-render without changing any other artwork structure.

---

# 11. Workstream E — Unified asset graph and provenance

## Goal

Create one coherent model for all supplied, generated and derived assets.

## Asset classes

At minimum:

- `originalRaster`
- `derivedRaster`
- `originalVector`
- `generatedVector`
- `brandAsset`

Potential later classes:

- `generatedRaster`
- `mask`
- `shadow`
- `referenceOnly`

## Required lineage

Every derivative should be traceable to its parent and root source.

Example:

```text
product-original.tif
        │
        ├── remove background
        ▼
product-cutout-v1.png
        │
        ├── duotone
        ▼
product-duotone-v1.png
```

And separately:

```text
creative request
        │
        └── Recraft
             ▼
flourish-v1.svg
        │
        └── regenerate "looser"
             ▼
flourish-v2.svg
```

## Suggested data concepts

The current `asset.name` primary key is retained only as a legacy resolution
surface for schema `0.1` and `0.2`. New work should use these concepts:

```text
asset
  id
  project_id
  logical_name
  kind
  role
  fidelity_class
  root_asset_id

asset_version
  id
  asset_id
  parent_version_id
  content_hash
  mime_type
  width / height / view_box
  has_alpha
  colour_space / ICC profile identity
  validation_status
  approval_status
  immutable payload or object key

asset_operation
  id
  project_id
  input_version_id
  operation_type
  normalised_parameters
  operation_fingerprint
  provider / model / tool version
  status / cost / error
  output_version_id

document_asset_reference
  document_version_id
  item_name
  asset_version_id
```

`document_asset_reference` is an index/audit record derived transactionally
when a document version is created. The canonical reference remains in document
JSON.

### Project scoping and migration

- New assets must belong to a project or to an explicitly shared library.
- Generation receives only assets visible to its project; it must never receive
  the entire global library.
- Each legacy asset row migrates to one `asset` plus immutable
  `asset_version`, preserving its existing name as a legacy alias.
- Schema `0.1` and `0.2` continue resolving `image.src` by that alias.
- Schema `0.3` references immutable asset-version IDs.
- Content hashes and operation fingerprints make deterministic transformations
  idempotent and reusable.
- Asset payload and lineage are immutable. Approval, rejection and supersession
  are append-only audit events; a materialised current status may be updated
  without rewriting content or decision history.

## Required provenance

Store:

- provider/service
- model
- model version if exposed
- prompt/instruction
- parameters
- parent asset
- root asset
- creation time
- content hash
- MIME type
- dimensions/viewBox
- alpha/transparency status
- validation status
- approval status
- cost if applicable

## Acceptance criteria

Any asset visible in a concept should be answerable with:

- where did it come from?
- was it supplied or generated?
- what model/service touched it?
- what was changed?
- which version is this?
- where else is it used?
- can we revert it?

---

# 12. Workstream F — Document schema `0.3`

## Goal

Add the minimum renderer-neutral vocabulary needed for generated vectors and richer asset references without overloading schema `0.2`.

## Principles

- `0.1` remains immutable
- `0.2` remains immutable
- no silent migrations
- stored documents replay under their recorded version
- schema features describe creative intent, not Scribus internals

## Candidate additions

### `vectorAsset`
A first-class placed vector asset.

### richer asset references
Schema `0.3` item `src` values identify immutable `asset_version` records.
Logical names remain presentation metadata and the compatibility mechanism for
schema `0.1`/`0.2`; they are not new-version identity.

### masks/clipping
Only if required by actual pilot work.

### asset role
Optional semantic role metadata:

```json
{
  "role": "hero-illustration"
}
```

This can help:

- comments
- mutation targeting
- validation
- orchestration

## Do not automatically add

- every SVG feature
- arbitrary blend modes
- every Illustrator effect
- arbitrary nested groups
- renderer-specific crop matrices

Only add features justified by real briefs.

### Initial `vectorAsset` scope

The first schema `0.3` slice supports `frame`, `name`, `role`, immutable `src`,
`fit: "contain"` and item `opacity`. It does not expose SVG internals, renderer
crop matrices, masks or clipping. Unsupported vector content fails during asset
ingestion before a document can reference it.

## Acceptance criteria

- old documents replay unchanged
- new vector assets compile deterministically
- schema validation clearly distinguishes unsupported features
- renderer limitations surface as explicit errors

---

# 13. Workstream G — Brand profile evolution

## Goal

Extend brand profiles from layout constraints into **creative asset policy**.

## Current strengths to preserve

- locked swatches
- font rules
- styles
- logos
- deterministic constraints
- interpretive design principles

## Proposed additions

### Vector generation policy

```json
{
  "vectorGeneration": {
    "allowed": true,
    "palettePolicy": "strict-brand",
    "allowGeneratedText": false,
    "preferredStyles": [
      "rounded",
      "playful",
      "minimal"
    ]
  }
}
```

### Raster treatment policy

```json
{
  "rasterTreatments": {
    "allowBackgroundRemoval": true,
    "allowDuotone": true,
    "approvedDuotones": [
      ["BrandPink", "BrandYellow"]
    ],
    "allowMonochromeRecolour": true,
    "allowFreeformRegeneration": false
  }
}
```

### Asset fidelity policy

Some brands/products may require:

- packshot must never be generatively altered
- logo cannot be recoloured
- product label must remain pixel-identical
- lifestyle imagery may be extended but not edited internally

These restrictions should be machine-readable.

They apply at two levels:

- the brand profile defines defaults and prohibitions
- the asset record defines the specific fidelity class and any narrower
  per-asset restrictions

The most restrictive applicable rule wins. Packshots and logos should default
to no generative alteration until explicitly classified otherwise.

The exact immutable brand-profile version used for generation, asset operations
and rendering must be pinned in provenance. Replaying a stored document against
the latest live profile is not sufficient.

## Acceptance criteria

The orchestration layer must know **what it is allowed to ask a specialist model to do** before it makes the request.

Policy enforcement must land before the first external vector/raster provider
call. It is not a later UI enhancement.

---

# 14. Workstream H — Creative orchestration layer

## Goal

Move from “one model writes a page” to “one agent plans and coordinates a creative document”.

## Responsibilities

The orchestration layer should decide:

1. what the concept is
2. what assets are already available
3. whether a supplied asset needs transformation
4. whether a vector component should be generated
5. whether a raster asset should be transformed
6. which layout model should author the document
7. when the result is ready for proof evaluation
8. which changes can be local instead of full-document regeneration

## Tool vocabulary

The orchestration model should eventually have tools conceptually like:

- `emit_document`
- `request_vector_asset`
- `transform_raster_asset`
- `select_existing_asset`
- `replace_document_asset`
- `submit_concept_for_review`

These are ide8-level tools.

The model should not know vendor API details.

## Example

User:

> Make concept 3 more expressive. Keep the layout, but make the product shot a pink/yellow duotone and replace the geometric motif with something hand-drawn.

Desired orchestration:

```text
1. Identify current hero raster asset
2. Create/reuse approved duotone derivative
3. Identify current motif vector asset
4. Request a new Recraft vector derivative
5. Create document version changing only two asset references
6. Validate
7. Render
8. Judge
9. Surface before/after
```

No full layout regeneration is required.

## Acceptance criteria

The orchestrator demonstrates **minimal-change behaviour**.

When the user asks to change one component, unrelated document structure should remain byte/structure-equivalent wherever possible.

For asset-only changes this is an enforced invariant:

- the request identifies the parent document version and expected content hash
- the replacement targets an item by stable `name` or unambiguous `role`
- the replacement service changes only the approved `src` field(s)
- structural diff rejects any unrelated change
- validation, proofing and version creation complete before the child version is
  published
- a failed operation leaves the parent version and current asset references
  untouched

---

# 15. Workstream I — Validation expansion

## Goal

Keep ide8.flow production-safe as model capabilities increase.

## Vector validation

Add checks for:

- SVG safety
- supported features
- vector complexity
- approved palette
- no unexpected text
- no external assets
- successful renderer round-trip
- output remains vector in packaged PDF where required

## Raster validation

Add checks for:

- dimensions
- effective DPI
- alpha state
- colour space and ICC-profile state
- valid colour/treatment policy
- source lineage
- correct output format
- no missing derivative
- render compatibility

## Document validation

Retain and expand:

- schema
- brand conformance
- geometry
- copy integrity
- overflow
- spot path rules
- safe zones
- contrast

## Production validation

Continue:

- PDF/X conformance
- named separations
- output intent
- embedded fonts
- PitStop preflight

## Important rule

If a specialist model produces something the renderer cannot represent safely, ide8.flow should fail explicitly.

Never silently flatten, approximate or discard production-critical semantics without an explicit policy.

---

# 16. Workstream J — Evaluation corpus and model bake-off

## Goal

Choose models by ide8.flow outcomes, not generic leaderboards.

## Build a fixed evaluation corpus

Create approximately 10–20 representative briefs covering:

- simple retail card
- product launch POS
- price-led promotional layout
- beauty/skincare brand
- premium/luxury treatment
- dense legal/copy layout
- image-dominant concept
- vector-illustration-led concept
- multiple formats
- difficult asset-treatment case

The BYOMA pilot should remain one of the harder real-brand cases.

## Measure

For each generation model:

- first-pass schema validity
- validation failures
- repair count
- latency
- cost
- visual score
- human designer score
- brand authenticity
- mutation fidelity
- craft minutes to client-ready state

For each judge:

- agreement with human reviewers
- false approvals
- false rejections
- usefulness of critique
- consistency

For Recraft/vector providers:

- creative usefulness
- editability
- geometry cleanliness
- brand adherence
- render compatibility
- time saved versus manual vector creation

For raster providers:

- subject fidelity
- transparency quality
- colour-treatment accuracy
- packaging/product fidelity
- deterministic/repeatable operation quality
- designer acceptance

## Primary product metric

The most important creative metric should be:

> **Designer minutes required to make a surfaced concept client-ready.**

That directly measures whether ide8.flow is doing useful work.

---

# 17. Workstream K — UI evolution

## Goal

Expose new power without turning the interface into Adobe Creative Suite.

## Asset library

Add:

- original/derived grouping
- raster/vector badges
- provenance
- version timeline
- preview
- approval state
- usage count

## Quick raster actions

- remove background
- duotone
- recolour
- crop/focus

## Vector actions

- generate vector element
- regenerate
- create variation
- replace in concept

## Concept detail

Allow:

- select an asset in the concept
- see its lineage
- swap asset version
- regenerate only that asset
- transform only that raster
- compare before/after

## Keep natural language central

The UI should support direct controls where precision helps, but ide8.flow should remain primarily:

- brief-driven
- conversational
- review-driven

Do not add arbitrary drawing tools unless later user evidence demands them.

---

# 18. Workstream L — Renderer strategy

## Decision

Keep Scribus 1.6.1 for this work unless a pilot exposes a genuine limitation.

This decision does not claim that arbitrary native SVG placement is already
supported. The current evidence covers inline path geometry only. External SVG
ingestion remains a mandatory feature harvest and explicit Stage 0 exit gate.

## Why

The current system has already proven:

- deterministic compilation
- vector paths
- gradients
- opacity
- raster placement
- live text
- spot colours
- PDF/X
- acceptable proof-render latency

The BYOMA technical slice did not produce evidence requiring a renderer change.

## Revisit only if real work repeatedly requires

- masks Scribus cannot express acceptably
- blend/transparency behaviour that cannot be represented safely
- significantly richer typography
- renderer bugs affecting client work
- poor vector-asset handling
- unacceptable Adobe handoff friction

## Preserve renderer neutrality

The canonical document should continue to make future targets possible:

```text
ide8 document
    │
    ├── Scribus
    ├── IDML / InDesign
    ├── Illustrator bridge
    └── future renderer
```

Scribus should remain an implementation target, not the product's data model.

---

# 19. Workstream M — Export and craft-pass implications

Generated/derived assets must participate in the existing craft-pass bundle.

A bundle should ultimately contain:

```text
concept/
├── document.json
├── artwork.sla
├── assets/
│   ├── supplied/
│   ├── derived-raster/
│   └── generated-vector/
├── manifest.json
├── profile.json
└── provenance/
```

The manifest should record every asset hash and lineage.

Later IDML/Adobe export should use the same asset graph.

---

# 20. Recommended delivery sequence

The work should be staged so each step produces value and avoids a large risky rewrite.

## Stage 0 — ADRs and renderer evidence

Before implementation:

1. record the architectural decision to keep document JSON canonical
2. record Scribus as current renderer
3. record the normalised provider-turn boundary
4. define asset/version/operation terminology and project scope
5. define provenance, approval and brand-profile pinning requirements
6. record the controlled raster-manipulation boundary and initial operation set
7. harvest external SVG behaviour in pinned Scribus and choose the deterministic
   native-vector route

**Exit:** architecture and raster boundaries are agreed; SVG → Scribus → PDF
vector preservation has evidence or a recorded compiler-normalisation route.

---

## Stage 1 — Unified asset lineage and policy foundation

Build:

- project-private asset scoping with explicit, configurable promotion to a
  shared brand/library scope
- `asset`, immutable `asset_version` and `asset_operation`
- content hashes and idempotent operation fingerprints
- candidate/validated/approved/rejected states
- per-brand and per-asset fidelity policy
- pinned brand-profile provenance
- document-asset reference indexing
- compatibility migration for existing named assets
- minimal durable job state, retries and atomic candidate publication

No specialist model call lands before this stage.

**Exit:** legacy documents replay unchanged; new projects see only permitted
assets; an operation can fail or retry without altering approved state.

---

## Stage 2 — Provider-independent generation

Build:

- normalised model request/response/tool/usage types
- Anthropic adapter preserving current behaviour
- provider-neutral model references, metering and errors
- adapter contract tests
- one experimental second-provider adapter
- model configuration/routing

Do not add OpenAI and Google simultaneously before the contract is proven.

**Exit:** current briefs pass regression tests through the Anthropic adapter and
the same canonical loop can run through a second provider by configuration.

---

## Stage 3 — Attempts and independent judge

Build:

- `creative_attempt` and `judge_evaluation`
- versioned creative rubric and score thresholds
- independent creator/judge routing
- separate creator and judge conversations
- judge provenance and usage
- human/judge comparison hooks
- promotion of surfaced attempts to document versions

**Exit:** provider A can create a valid proof, provider B can judge it, and all
rejected/surfaced attempts remain inspectable without corrupting the document
version timeline.

---

## Stage 4 — Native vector vertical slice

Build:

- schema `0.3` `vectorAsset`
- Recraft adapter
- SVG sanitisation
- normalised allowed SVG subset
- palette policy
- asset storage/provenance
- deterministic native Scribus object emission
- PDF vector-preservation validation
- UI preview/replace

Use one narrowly defined pilot.

**Exit:** prompt → Recraft SVG → ide8 asset → document → Scribus → PDF/X works end-to-end.

---

## Stage 5 — Raster Phase 1

Implement the Phase 1 scope from `RASTER-ASSET-PIPELINE.md`:

- background removal
- transparency
- document-level crop/focus using existing `0.2` placement semantics
- monotone/duotone tonal treatments
- gradient/fade overlays
- brand recolour
- deterministic asset swap with structural-diff enforcement
- lineage
- UI controls
- effective-DPI, alpha, colour-space and ICC-profile validation

**Exit:** supplied product image can be transformed and swapped into a concept without regenerating the layout.

---

## Stage 6 — Orchestration tools and approvals

Give the creative agent ide8-level tools to:

- request vector asset
- transform raster asset
- select asset
- replace asset
- emit/mutate document

Add minimal-change rules.

Specialist results remain candidate asset versions until validated and approved
under the project policy. Automatic use is opt-in per operation/fidelity class.

**Exit:** a natural-language mutation can coordinate specialist asset changes and document updates.

---

## Stage 7 — UI and workflow completion

Build:

- original/derived asset timeline
- provenance and policy display
- candidate approval/rejection
- asset usage and replacement views
- before/after comparison
- vector regeneration/variation actions
- operation retry/fallback controls

**Exit:** a designer can understand, approve, replace and revert every asset
used by a concept without inspecting raw JSON.

---

## Stage 8 — Bake-off and routing

Run the fixed brief corpus across:

- generation models
- judge models
- vector providers
- raster providers

Collect:

- quality
- latency
- cost
- repair rate
- craft minutes

Define routing defaults from evidence.

**Exit:** model choices are driven by measured ide8.flow performance.

---

## Stage 9 — Production hardening

Add:

- rate limits
- queue scaling and recovery testing
- retry/fallback policy hardening
- provider failure fallback
- cost ceilings
- asset-size limits
- SVG complexity limits
- security review
- production preflight gates
- audit/reporting

**Exit:** the expanded pipeline is safe for internal studio use.

---

# 21. Suggested service structure

Do not treat this as prescriptive, but a possible direction is:

```text
services/
├── render/
├── worker/
├── ui/
│
├── model_gateway/
│   ├── providers/
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── google.py
│   └── routing.py
│
├── asset_pipeline/
│   ├── vector/
│   │   ├── providers/
│   │   │   └── recraft.py
│   │   ├── sanitize.py
│   │   └── validate.py
│   │
│   ├── raster/
│   │   ├── providers/
│   │   ├── operations.py
│   │   └── validate.py
│   │
│   └── provenance.py
│
└── evaluation/
    ├── briefs/
    ├── scorecards/
    └── runners/
```

This may remain inside the worker initially if separate services would create unnecessary deployment complexity.

Service boundaries should follow operational need, not aesthetic purity.

---

# 22. Failure handling and fallbacks

Model/vendor failures must not corrupt artwork state.

## Rules

- never overwrite the current approved asset
- generation jobs create candidate asset versions
- only successful validated results can be referenced
- every externally executed operation has an idempotency key derived from its
  input content hash, normalised parameters and tool/provider version where the
  operation is deterministic
- job state is durable; process restart cannot turn a completed provider call
  into an untracked orphan or duplicate charge
- provider timeout leaves existing concept untouched
- failed specialist call can be retried or routed elsewhere
- all errors become structured ide8 errors
- candidate creation, validation state and publication of a document reference
  are transactional boundaries; a document may never reference a partial asset

## Example

```text
Recraft unavailable
    ↓
vector job fails
    ↓
existing concept remains valid
    ↓
user sees retry/fallback option
```

No half-written document version should be committed.

---

# 23. Cost control

Specialist generation adds cost, so model/tool calls should be intentional.

## Principles

- reuse existing generated assets where suitable
- do not regenerate unchanged assets during layout repair
- cache/reuse derived raster treatments
- only call strong models after cheaper failure/escalation conditions
- meter vector/raster operations independently
- show per-concept cost
- retain per-brief ceilings

A failed text overflow should not trigger another Recraft call.

A layout mutation that moves a frame should not re-run background removal.

---

# 24. Security

New asset pipelines introduce additional attack surface.

## SVG

Treat generated/uploaded SVG as untrusted input.

Sanitise:

- scripts
- external references
- data URLs where disallowed
- embedded foreign objects
- unsupported filters
- pathological geometry

## Raster

Validate:

- MIME type
- decoded dimensions
- file size
- decompression-bomb limits
- metadata
- storage path
- output format

## Prompts and assets

External/client content must not be allowed to override:

- system policy
- brand rules
- production rules
- tool permissions

Client assets also require outbound-data policy:

- provider allowlist by project and fidelity class
- recorded consent/authority to send the asset to that provider
- retention/training/data-residency requirements where applicable
- licence and usage-right metadata for supplied and generated assets
- audit record of exactly which asset version and prompt left ide8.flow

Project scoping is a security boundary. A model prompt, asset picker or
generation job must not enumerate assets from unrelated projects.

---

# 25. Observability

Every creative job should become inspectable.

Track:

- brief ID
- concept ID
- document version
- provider/model
- judge provider/model
- vector jobs
- raster jobs
- validation failures
- repair count
- latency
- cost
- human approval
- final craft effort

This data becomes extremely valuable for routing decisions later.

---

# 26. Testing strategy

## Unit

- provider adapters
- asset lineage
- SVG sanitisation
- raster operation schemas
- brand policy checks
- document schema `0.3`
- provenance

## Integration

- Recraft fixture → SVG → renderer
- raster derivative → document → proof
- creator A → judge B
- asset replacement without unrelated document mutation
- craft bundle includes generated/derived assets

## Golden/conformance

Add permanent fixtures for:

- generated vector
- transparent raster
- duotone raster
- mixed vector+raster artwork
- PDF vector preservation
- named spots
- PDF/X

## Human evaluation

Keep model quality evaluation separate from deterministic technical tests.

---

# 27. Risks

## Risk: specialist asset generation becomes visually attractive but structurally messy

Mitigation:
- sanitisation
- complexity limits
- palette policy
- human review
- alternate provider support

## Risk: raster editing alters product fidelity

Mitigation:
- operation allowlists
- brand fidelity rules
- supplied packshots protected by default
- original/derived comparison
- human approval

## Risk: orchestration becomes expensive

Mitigation:
- local/minimal-change operations
- caching
- provider routing
- cost ceilings
- do not regenerate untouched assets

## Risk: schema expands too quickly

Mitigation:
- `0.3` only contains features proven necessary by pilots
- explicit unsupported-feature errors
- no renderer leakage

## Risk: model bake-offs create endless experimentation

Mitigation:
- fixed evaluation corpus
- fixed success metrics
- periodic rather than constant rerouting
- designer craft minutes as the deciding metric

---

# 28. Immediate Codex task

The repository architecture pass requested by the original version of this plan
was completed on 27 August 2026. Its findings are incorporated above.

The next implementation slice is Stage 0 evidence and ADR work followed by the
Stage 1 asset foundation. Do not begin by integrating every external provider.

## Next concrete tasks

1. write the document/renderer, asset identity, provider boundary and approval
   ADRs
2. run the pinned-Scribus SVG feature harvest and record the supported path
3. specify the SQLite migration and rollback test for legacy named assets
4. implement project-private asset lookup and explicit sharing controls before
   adding derived assets
5. add immutable asset/version/operation records and operation idempotency tests
6. pin brand-profile provenance for new jobs/versions/operations
7. add the deterministic asset-replacement service and structural-diff tests
8. only then add the normalised provider adapter or specialist vertical slice

Codex should favour adaptation of the existing architecture over rewrites.

---

# 29. Resolved product decisions

The repository review questions were resolved on 27 August 2026:

1. **Raster manipulation boundary:** duotone is illustrative. The raster
   subsystem performs ordinary graphic-design manipulation of supplied assets —
   for example monotone/duotone treatments, background removal and fade overlays
   — without generating a totally new replacement asset or scene.
2. **Asset scope:** assets are project-private by default. An explicit,
   configurable action may promote or share an asset with a brand/library scope
   when required.
3. **Vector editability:** a generated vector is initially one semantic,
   vector-preserved and replaceable asset. Its source SVG is included in the
   craft bundle; individual SVG subpath editing in Scribus is not a first-slice
   requirement.

---

# 30. Definition of success

This programme is successful when ide8.flow can take:

- a brief
- approved brand rules
- supplied photography
- supplied logos
- copy

and autonomously coordinate:

- document layout
- native vector illustration generation
- controlled raster transformation
- live typography
- versioned asset placement
- independent visual critique
- deterministic validation
- production rendering

while still producing:

- structured editable artwork
- traceable asset provenance
- live text
- genuine vector content
- linked/derived raster assets
- PDF/X
- named production separations
- a clean designer craft-pass path

The final artwork must remain a **document**, not an image.

---

# 31. Closing direction

The recent arrival of genuine native-vector generation does not invalidate ide8.flow's architecture.

It validates the decision to keep the canonical document separate from any one model.

The correct next step is therefore not:

> replace ide8.flow with Recraft or another generative design tool.

It is:

> make ide8.flow capable of commissioning specialist creative tools while retaining ownership of structure, production rules, provenance and output.

The long-term model is straightforward:

- **general-purpose model** = creative director / layout designer
- **Recraft or future vector provider** = illustrator
- **raster transformation model/service** = image retoucher
- **independent multimodal model** = art director / critic
- **ide8 document** = canonical artwork
- **Scribus** = current production compositor
- **PitStop / Phoenix** = production authority

That is the evolution to build.
