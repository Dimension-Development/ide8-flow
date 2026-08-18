# BYOMA agency-quality vertical slice — implementation plan

| | |
|---|---|
| **Status** | Stage A complete — technical construction proven; approved brand pack pending for Stages B/C |
| **Owner** | Luke — Dimension Development Ltd |
| **Prepared** | 18 August 2026 |
| **Purpose** | Prove that ide8.flow can generate, refine and package an agency-credible branded design using the existing architecture |

> **Why this plan exists.** The capability is partially represented in the
> [PRD](../../PRD.md) and the current [document schema](../../SCHEMA.md), but it
> is scattered across future renderer, vector, brand and craft-pass requirements.
> This document turns those requirements into one deliberately narrow vertical
> slice with a visible creative result and measurable production acceptance.

## 1. Outcome we are proving

A user can ask ide8.flow to:

> Design a 150 × 150 mm information card for BYOMA. Use the approved BYOMA
> colours, fonts, typography and logo rules. Use the supplied model and product
> imagery. Create a brand-colour gradient background, place the model across
> approximately 50% of the left side, place the supplied copy on the right, and
> overlay rounded-corner star motifs at 50% opacity. Produce six genuinely
> distinct directions suitable for internal design review.

The system should translate that instruction into structured document data,
validate the hard brand and production rules, render proofs, critique and repair
the results, and package the selected direction as a production-safe PDF/X-4.

This is a test of the product's core proposition: **AI for the first 80% of
iteration, designers for selection, art direction and the finishing pass.** It
is not a claim that every first-generation design will be client-ready without
human judgement.

## 2. Decisions fixed for this slice

1. The canonical artefact remains renderer-neutral document JSON. Scribus SLA
   is an implementation detail, never model-authored input.
2. Scribus 1.6.1 remains the pilot renderer. Replacing it is not required unless
   the conformance fixture demonstrates a material rendering failure.
3. New document capabilities ship as schema version `0.2`; stored `0.1`
   documents remain immutable and replay through their original compiler.
4. Rounded-star motifs compile to ordinary vector `path`/`shape` geometry.
   They do not become a Scribus-specific or renderer-specific object type.
5. Start with object opacity and simple linear/radial gradients. Blend modes,
   nested transparency groups and general-purpose masks are deferred unless the
   pilot design cannot be expressed without them.
6. No general-purpose drawing UI is added. Natural-language mutation, structured
   controls and an external craft pass remain the editing model.

## 3. Scope

### 3.1 Document schema `0.2`

Add the smallest renderer-neutral vocabulary required by the pilot:

- `fill` accepts either a swatch name or a gradient definition;
- linear and radial gradients use named swatches and explicit stops;
- item-level `opacity` from `0` to `1`;
- image focal point and deterministic crop/scale controls;
- filled vector paths remain ordinary `shape` items;
- stable layer/order semantics where document order is insufficient;
- validation errors for invalid stops, opacity, crop and unsupported features.

The formal JSON Schema, human reference, compiler and prompt-pack description
must change together. Capability additions must not silently alter `0.1`.

### 3.2 Scribus compiler and renderer

- Compile linear/radial gradients to the pinned Scribus representation.
- Compile item opacity without flattening supported vector content.
- Produce deterministic image crop and focal-point placement.
- Preserve the existing byte-stable compilation guarantee per schema/compiler
  version.
- Continue to emit PDF/X-4 with output intent, embedded fonts and named spot
  separations.
- Expose unsupported renderer capabilities as explicit errors, not degraded
  output.

### 3.3 Synthetic agency-card fixture

Before real BYOMA material arrives, create a neutral 150 × 150 mm fixture that
contains:

- 3 mm bleed and a defined safe area;
- a two-colour gradient background;
- a transparent model cut-out occupying approximately half the card;
- a right-hand headline, supporting copy and legal-copy hierarchy;
- several filled rounded-star paths at 50% opacity;
- a logo clear-space region;
- CMYK swatches plus a named `CutContour` test separation;
- sufficient complexity to expose crop, overflow and layering faults.

The fixture is not intended to imitate BYOMA. It proves the construction and
production capabilities without pre-empting the design team's brand guidance.

### 3.4 Validation and conformance

Automated acceptance must cover:

- schema validation and structured repair errors;
- deterministic compilation for identical inputs;
- gradient and opacity surviving PDF/X-4 output;
- transparent image alpha rendering correctly;
- vector motifs remaining vector;
- embedded fonts and no unintended substitution;
- no text overflow;
- correct colour profile/output intent;
- named spot separation preservation;
- minimum effective image resolution;
- repeat-render visual stability;
- PitStop preflight against Dimension's production profile when available.

The synthetic card becomes the permanent renderer-conformance fixture. It can
later be run unchanged through Prince, PDFlib or Adobe to compare renderers.

### 3.5 Brand-pack ingestion

Prepare a standard location and manifest for the design team's material:

```text
brand/
  profile.json
  logos/
  fonts/
  swatches/
  imagery/
  motifs/
  references/
    approved/
    rejected/
  rules/
  production/
```

The resulting brand profile must separate:

- **hard constraints** — permitted fonts/colours, logo rules, minimum sizes,
  safe zones, mandatory copy and production requirements;
- **creative preferences** — hierarchy, composition, crop, whitespace, motif
  use and characteristic colour combinations;
- **reference evidence** — approved and rejected examples with designer notes;
- **licensing facts** — whether each font and asset may be used on the render
  host and embedded in output.

### 3.6 Generation and creative evaluation

- Create a versioned BYOMA pilot brief and prompt-pack addition.
- Generate six structural directions, not six colourway variations.
- Use named creative axes to force meaningful diversity in image dominance,
  hierarchy, density and motif treatment.
- Run the existing render/vision/repair loop within its recorded iteration cap.
- Allow conversational refinement of the selected direction.
- Preserve every prompt, document version, proof, validation report and cost.

Design review uses a scorecard agreed before generation:

| Dimension | Review question |
|---|---|
| Brand authenticity | Does this feel unmistakably BYOMA rather than merely using its colours? |
| Composition | Is the image/copy relationship intentional and balanced? |
| Typography | Is the hierarchy confident, legible and characteristic of the brand? |
| Imagery | Are selection, crop, focal point and scale appropriate? |
| Sophistication | Does the result avoid a generic or visibly templated feel? |
| Production | Is the artwork technically safe and correctly packaged? |
| Craft effort | How much designer time is required to make it client-ready? |

## 4. Work sequence

### Stage A — can begin before the brand pack

**Status: complete on 18 August 2026.** See [STAGE-A-RESULTS.md](./STAGE-A-RESULTS.md).

1. Specify schema `0.2` and its compatibility rules.
2. Add the formal schema and compiler dispatch for `0.1`/`0.2`.
3. Implement gradient, opacity and deterministic image crop support.
4. Build the synthetic agency-card fixture.
5. Add compiler, render and PDF conformance tests.
6. Prepare the brand-pack manifest and designer scorecard.

### Stage B — begins when design inputs arrive

**Status: pending approved design-team inputs.**

1. Inventory and validate the supplied files.
2. Resolve font licensing, missing masters and unsuitable image resolution.
3. Encode the versioned BYOMA brand profile.
4. Record approved/rejected references and designer rationale.
5. Finalise the real copy deck and pilot brief.

### Stage C — pilot execution

**Status: pending completion of Stage B and design approval.**

1. Generate six directions.
2. Run deterministic validation and visual self-critique.
3. Hold design-team review using the scorecard.
4. Refine the strongest direction through natural-language mutations.
5. Package PDF/X-4 and run production preflight.
6. Complete a craft-pass handoff and measure finishing effort.
7. Record which gaps belong to brand intelligence, model art direction,
   document vocabulary, rendering or workflow.

## 5. Acceptance criteria

### Technical

- A valid `0.2` document renders through the existing service without weakening
  `0.1` replay or deterministic output.
- The fixture visibly contains the requested gradient, transparent imagery,
  opaque/transparent vector shapes, correct crop and text hierarchy.
- The packaged PDF/X-4 passes automated checks for output intent, fonts and
  named spot separations, followed by PitStop in production.
- Invalid opacity, gradient, crop and unsupported features produce stable,
  machine-repairable error codes.

### Creative

- Six directions show meaningful structural diversity.
- At least one direction is judged by the nominated designers to be suitable
  for a normal first-round internal review.
- Reviewers can identify the brand rationale behind the selected composition.
- The selected direction improves predictably in response to art direction.

### Workflow

- The selected artwork can be handed to the agreed craft application with its
  assets, fonts/manifest and version provenance intact.
- Designer finishing effort is recorded rather than assessed anecdotally.
- The pilot produces a prioritised gap list and a go/adjust/stop decision for
  the next product milestone.

## 6. Explicit non-goals

- Autonomous release without designer and production approval.
- General raster retouching or layered PSD authoring.
- A browser-based general-purpose layout editor.
- Arbitrary reverse-compilation of Affinity, Illustrator or InDesign files.
- Renderer replacement before the current renderer fails an agreed fixture.
- Complete support for every PDF blend mode or transparency construct.

## 7. Principal risks and controls

| Risk | Control |
|---|---|
| Correctly rendered work is mistaken for creatively successful work | Separate technical acceptance from the designer scorecard |
| BYOMA inputs are incomplete or inconsistently documented | Inventory files, record assumptions and obtain one named design approver |
| Licensed fonts cannot run server-side | Confirm licence terms early; record approved fallbacks explicitly |
| Schema becomes a mirror of Scribus internals | Keep public concepts renderer-neutral and add capability tests |
| Advanced effects expand the slice indefinitely | Limit v0.2 to gradient, item opacity and deterministic crop |
| Six outputs are superficial variations | Condition generation with explicit creative axes and review structural diversity |
| PDF looks correct but fails production | Gate output intent, fonts, spots and PitStop separately from visual QA |

## 8. Definition of done

This slice is complete when Dimension's design and production representatives
can review one recorded pilot run and answer, with evidence:

1. Can ide8.flow construct the requested artwork using structured document data?
2. Can it produce several credible, genuinely different branded directions?
3. Can a designer improve a selected direction quickly through art direction?
4. Does the final artwork survive the expected craft and production workflow?
5. Where does the remaining gap to Dimension's quality bar actually reside?

The result is not required to prove that ide8.flow can replace a designer. It
must prove whether the platform can remove a meaningful portion of repetitive
first-round and production work without lowering Dimension's creative standard.
