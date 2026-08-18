# BYOMA vertical slice — Terra execution tasks

| | |
|---|---|
| **Status** | Ready for technical execution; real brand work remains blocked on design inputs |
| **Execution target** | Terra, optimised for elapsed delivery time |
| **Parent plan** | [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md) |
| **Prepared** | 18 August 2026 |

## 1. Instruction to Terra

Work from the first unchecked task whose dependencies are complete. Treat the
contracts in section 3 as fixed for this slice; do not reopen product scope
unless a renderer harvest proves that Scribus 1.6.1 cannot express it.

This handoff is designed for **wall-clock speed, not token minimisation**:

- use the parallel waves in section 2 when more than one worktree/task is
  available;
- otherwise follow the task numbers in order;
- open the files listed on each task first and widen the search only if blocked;
- run the targeted checks on each task, then run the full gates once in T09;
- mark completed checkboxes and add the command/result beneath the task;
- if a stop condition is reached, record evidence and continue with another
  unblocked task rather than inventing a Scribus mapping;
- do not call a live generation model and do not use real BYOMA material during
  Stage A.

Use normal/medium reasoning for the bounded implementation tasks. T01 and T04
contain the only expected renderer uncertainty; increase effort there only if
the harvested SLA evidence is ambiguous.

## 2. Fastest safe execution order

```text
Wave 1 (parallel)       T01 Scribus harvest   T02 schema 0.2   T08 brand scaffold
                                |                    |
Renderer lane           T03 gradient/opacity -> T04 image placement
Worker lanes                                  T05 version routing
                                              T06 validation changes
                                \                |                /
Wave 3                                  T07 conformance fixture
                                                   |
Final gate                                         T09
```

T03 and T04 deliberately share one renderer lane because both edit
`sla_compiler.py`. T05, T06 and T08 use separate files and are safe to run
alongside that lane after T02.

## 3. Locked document `0.2` contract

These semantics are renderer-neutral. Scribus attribute names must not escape
into document JSON.

### 3.1 Fill and gradients

`fill` remains a swatch-name string for a solid fill, or is one of:

```json
{
  "type": "linear-gradient",
  "start": [0, 0.5],
  "end": [1, 0.5],
  "stops": [
    {"at": 0, "color": "BrandPink"},
    {"at": 1, "color": "BrandYellow"}
  ]
}
```

```json
{
  "type": "radial-gradient",
  "center": [0.5, 0.5],
  "focal": [0.5, 0.5],
  "radius": 0.5,
  "stops": [
    {"at": 0, "color": "BrandYellow"},
    {"at": 1, "color": "BrandPink"}
  ]
}
```

Rules:

- points are `[x, y]` coordinates normalised to the item's frame;
- radial radius is relative to the frame's shorter edge;
- `focal` is optional and defaults to `center`;
- the radial focal point must lie strictly inside the radial circle; this is a
  semantic compiler check because JSON Schema cannot express the distance rule;
- a gradient has 2–16 stops, each `at` is in `0..1`;
- stops are non-decreasing, the first is exactly `0`, and the last exactly `1`;
- every stop references a named document/profile swatch;
- stop-level opacity, blend modes, masks and gradient transforms are out of
  scope for `0.2`;
- gradient fills are allowed on `shape`, `text` frame backgrounds and `image`
  frame backgrounds, but never on production `path` items.

### 3.2 Opacity

`opacity` is a number from `0` (invisible) to `1` (opaque), defaulting to `1`.
It is allowed on `shape` and `image` only in this slice. It applies to the
whole object. Text transparency and path/spot transparency are deferred so the
pilot cannot accidentally weaken copy or production separations.

### 3.3 Image placement

The `0.2` image contract replaces the ambiguous `0.1` `frame/free/stretch`
combination with:

```json
{
  "type": "image",
  "frame": [0, 0, 200, 425.19685],
  "src": "model-cutout",
  "fit": "cover",
  "focus": [0.42, 0.35],
  "zoom": 1.1
}
```

Rules:

- `fit` is `contain`, `cover` or `stretch`; default is `contain`;
- `focus` is an intrinsic-image coordinate normalised to `0..1`, defaults to
  `[0.5, 0.5]`, and is valid only with `cover`;
- `zoom` is `1..8`, defaults to `1`, and is valid only with `cover`;
- `cover` scale is `max(frameWidth/sourceWidth,
  frameHeight/sourceHeight) * zoom`;
- the focal point is placed at frame centre and then clamped so no empty area
  appears inside the frame;
- source dimensions come from the asset record, not model-authored JSON;
- `cover` without known source dimensions fails with
  `image-dimensions-required` rather than degrading to another fit mode.

The `fit + focus + zoom` combination is the deterministic crop/scale control
for this slice. Do not add a second raw Scribus offset/scale vocabulary.

### 3.4 Stacking and compatibility

- `pages[].items` is canonical back-to-front paint order. Do not add `zIndex`
  unless the conformance fixture proves array order is not preserved.
- `shape.d` remains the way to create filled vector motifs such as rounded
  stars; do not add a star-specific item type.
- A `0.1` document must still compile to the existing golden SLA byte-for-byte.
- Stored `0.1` documents are never silently migrated or mutated as `0.2`.
- Unsupported renderer features fail explicitly; they are never flattened or
  silently approximated.

## 4. Task cards

### T00 — baseline recorded

**Status:** complete on 18 August 2026.

The clean starting point is:

```text
python3 -m unittest discover services/render/tests  -> 14 passed
python3 -m unittest discover services/worker/tests  -> 107 passed
```

The BYOMA planning directory is currently untracked. Preserve unrelated user
changes and do not regenerate `services/render/tests/golden/out.sla`.

---

### T01 — harvest Scribus 1.6.1 feature mappings

**Status:** complete on 18 August 2026.

**Dependencies:** T00.

**Parallel:** safe with T02 and T08.

**Purpose:** replace guesses about SLA transparency, gradients and image
placement with evidence from the pinned renderer.

Read first:

- `services/render/template.sla`
- `services/render/sla_compiler.py`
- `services/render/service/scribus_scripts/gen_donor.py`
- `services/render/Dockerfile`
- `services/render/README.md`

Deliver:

- [x] Add `docs/briefs/byoma-pilot/SCRIBUS-MAPPING.md`.
- [x] Add minimal Scribus-saved SLA samples under
  `services/render/tests/fixtures/scribus-1.6.1-features/` for:
  linear gradient, radial gradient, 50% object opacity, transparent PNG,
  contain image, cover image with an off-centre focal crop, and a filled
  custom vector path.
- [x] Record the exact object attributes/children that change from a plain
  object and which values are frame-local versus image-local.
- [x] Record whether reopening and resaving preserves those values.
- [x] Prove that page-object order is preserved in exported PDF paint order.
- [x] Record a repeatable harvest command or script in the mapping document.

Acceptance:

- every compiler mapping used by T03/T04 is supported by a Scribus-saved
  sample from the pinned 1.6.1 container;
- the samples are minimal enough to diff meaningfully;
- no production compiler behaviour changes in this task.

Stop condition: if headless scripting cannot create one of the samples, save a
single minimal document through Scribus UI or record the precise blocker. Do
not hand-author an SLA mapping based solely on memory or an older Scribus
version.

Evidence: pinned package `1.6.1-0ubuntu7`; all mappings survived a second
reopen/save; paint-order and PNG-alpha proof pixels passed
`verify_harvest.py`. The harvest found stable gradient types `6/7` and proved
that SLA `TransValue` stores opacity rather than the scripting API's
transparency input.

---

### T02 — add the formal document `0.2` contract

**Status:** complete on 18 August 2026.

**Dependencies:** T00 and section 3 of this document.

**Parallel:** safe with T01 and T08.

**Purpose:** give all later work one machine-readable vocabulary.

Read first:

- `schema/document-0.1.schema.json`
- `docs/SCHEMA.md`
- `services/worker/validation/schema_check.py`
- `services/worker/tests/test_validation.py`

Deliver:

- [x] Add `schema/document-0.2.schema.json`; copy stable `0.1` definitions and
  apply only the contract in section 3.
- [x] Keep `additionalProperties: false` throughout.
- [x] Add reusable definitions for `point`, `gradientStop`, `linearGradient`,
  `radialGradient` and `fill`.
- [x] Express conditional image rules so `focus`/`zoom` are rejected unless
  `fit` is `cover`.
- [x] Add `docs/SCHEMA-0.2.md` with examples and defaults.
- [x] Add a short version index to `docs/SCHEMA.md`; do not rewrite the `0.1`
  reference as though its rules had changed.
- [x] Add `services/render/examples/example-0.2.json`, using synthetic swatch
  names and no real brand content.
- [x] Add isolated tests in
  `services/worker/tests/test_schema_0_2.py` for every valid and invalid
  contract edge.

Required negative tests:

- opacity below 0/above 1, opacity on text/path;
- fewer than two or more than sixteen stops;
- stop outside `0..1`;
- gradient on a path;
- invalid normalised points/radius;
- focus or zoom used with contain/stretch;
- unknown `fit` and hallucinated properties;
- a `0.1` document with any `0.2` property still fails its original schema.

Note: JSON Schema cannot enforce sorted stops or exact first/last positions
cleanly. T03 must enforce those checks and return stable compiler errors.

Acceptance command:

```bash
python3 -m unittest discover services/worker/tests -p 'test_schema_0_2.py'
```

Evidence: 17 schema `0.2` tests passed, including Draft 2020-12 schema
self-validation, the complete example, every listed negative edge and `0.1`
version isolation.

---

### T03 — compile gradients and opacity

**Status:** complete on 18 August 2026.

**Dependencies:** T01 and T02.

**Parallel:** do not overlap T04 in the same worktree.

**Purpose:** make the new visual vocabulary deterministic and renderer-backed.

Read first:

- `docs/briefs/byoma-pilot/SCRIBUS-MAPPING.md`
- `services/render/sla_compiler.py`
- `services/render/tests/test_compiler.py`
- `services/render/tests/fixtures/scribus-1.6.1-features/`

Deliver:

- [x] Add `0.2` to compiler dispatch without changing the `0.1` output path.
- [x] Validate gradient shape, swatch references, stop ordering and endpoints
  before emission; never use a dict as a hash key.
- [x] Emit linear and radial gradients exactly as harvested in T01.
- [x] Emit object opacity exactly as harvested; handle `opacity: 0` explicitly
  rather than through truthiness.
- [x] Preserve `shape.d` as vector geometry.
- [x] Add `services/render/tests/test_compiler_0_2.py` with attribute-level
  assertions and byte-determinism tests.
- [x] Add stable compiler errors:
  `bad-gradient`, `gradient-stop-order`, `gradient-stop-endpoints`,
  `unknown-swatch`, `bad-opacity`, and `unsupported-feature`.

Protected invariant:

```bash
python3 -m unittest discover services/render/tests -p 'test_compiler.py'
```

The existing `0.1` golden must pass unchanged. Do not regenerate it to make a
failure disappear.

Evidence: 18 focused compiler tests pass. A compiler-produced `0.2` SLA was
exported successfully by pinned Scribus 1.6.1 and reopened/resaved with
`GRTYP="6"`, its gradient coordinates/stops and `TransValue="0.5"`
preserved. The full `0.1` golden remains byte-identical. Metadata-dependent
contain/cover placement fails explicitly until T04; stretch image opacity is
already supported.

---

### T04 — deterministic image contain/cover/stretch and focal crop

**Dependencies:** T01, T02 and T03.

**Purpose:** place real supplied imagery predictably without exposing renderer
internals to the document model.

Read first:

- `services/worker/assets.py`
- `services/worker/generation/render_client.py`
- `services/render/service/app.py`
- `services/render/sla_compiler.py`
- every `resolve_srcs` call reported by `rg -n 'resolve_srcs' services/worker`

Implement this boundary:

1. `resolve_srcs` continues to rewrite asset names and collect bytes, and also
   returns metadata keyed by staged relative path: `{width, height}`.
2. `RenderClient.compile(document, image_meta=None)` keeps plain-document
   requests backward compatible and uses an envelope only when metadata is
   present: `{document, image_meta}`.
3. `/compile` accepts either the existing plain document or that envelope.
4. `compile_to_bytes(..., image_meta=None)` performs the deterministic
   fit/focus/zoom calculation from section 3 and emits the T01 mapping.
5. Metadata is transient compiler input. It is not stored in canonical
   document JSON and is not shown to the model.

Deliver:

- [x] Update all generation, mutation, download, bundle and test callers for
  the extended asset return value.
- [x] Preserve compilation for documents with no images and for `0.1` image
  semantics.
- [x] Centre `contain`; fill and clamp `cover`; fill non-proportionally for
  `stretch`.
- [x] Add errors `image-dimensions-required`, `bad-image-dimensions` and
  `bad-image-placement`.
- [x] Add focused compiler, render-client, asset and service tests.
- [x] Include a non-square source/non-square frame test whose expected scale
  and both offsets are calculated explicitly in the test.

**Status:** complete on 18 August 2026.

**Evidence:** `resolve_srcs` now returns staged-image dimensions separately
from canonical document JSON; the render client uses its envelope only when
that metadata exists.  Compiler tests cover the harvested 400×200 source in a
140×120 frame: contain emits `0.35` scale and `25pt / 71.428571px` vertical
offset; cover with focus `[0.625, 0.5]` emits `0.6` scale and `-80pt /
-133.333333px` horizontal offset after clamping; stretch emits independent
`0.35`/`0.6` scales. Focused tests and the full renderer/worker suites pass:
`37` and `126` tests respectively.

Stop condition: if T01 proves Scribus cannot reproduce the specified focal crop
through stable SLA values, do not fake it with a visually similar fit. Write a
short ADR beneath `docs/briefs/byoma-pilot/` comparing (a) a Scribus scripting
post-load step, (b) pre-cropping a derived asset, and (c) deferring `cover`,
then stop T04 for a product decision.

---

### T05 — route schema and prompt-pack versions correctly

**Dependencies:** T02.

**Parallel:** safe alongside the renderer lane and T06 when using the listed
new test file.

**Purpose:** generate new `0.2` documents without corrupting replay/mutation of
stored `0.1` work.

Read first:

- `services/worker/app.py`
- `services/worker/generate.py`
- `services/worker/generation/service.py`
- `services/worker/generation/prompts.py`
- `services/worker/prompt_packs/0.1/`
- `services/worker/tests/test_store_and_mutation.py`

Deliver:

- [x] Add one central worker registry mapping schema version to schema path,
  prompt pack and exemplar; reject unknown or mismatched combinations.
- [x] Add prompt pack `services/worker/prompt_packs/0.2/`, changing only rules
  required by `0.2` plus explicit gradient/opacity/image guidance.
- [x] Add `DOCUMENT_SCHEMA_VERSION`; default it to `0.1` for existing installs
  until T09 passes. The pilot can opt into `0.2` explicitly.
- [x] Make the CLI expose an explicit schema-version option while retaining
  existing explicit path/pack overrides for diagnostics.
- [x] Store `schema_version` from the validated document, never from the
  current hard-coded `SCHEMA_VERSION` constant.
- [x] Select schema, prompt pack and exemplar from the parent version during
  mutation. A `0.1` parent must remain `0.1`.
- [x] Fail a generation result whose emitted version does not match the active
  schema instead of storing false provenance.
- [x] Add isolated tests in
  `services/worker/tests/test_schema_routing.py` for new generation, `0.1`
  mutation, `0.2` mutation, unknown versions and stored provenance.

**Status:** complete on 18 August 2026.

**Evidence:** `schema_registry.py` is the single matched schema/prompt/exemplar
route source; `DOCUMENT_SCHEMA_VERSION` remains `0.1` by default. The API and
CLI can opt into `0.2`, while mutation/template runs select the stored parent
route. Five isolated routing tests pass, including prevention of false stored
provenance after an emitted-version mismatch.

Do not make a live Anthropic call; existing fakes are sufficient.

---

### T06 — make deterministic validation gradient-aware

**Dependencies:** T02.

**Parallel:** safe alongside T03/T04/T05.

**Purpose:** prevent the validation layer from crashing or approving illegible
copy when a background fill is no longer a single string.

Read first:

- `services/worker/validation/contrast.py`
- `services/worker/validation/brand_rules.py`
- `services/worker/validation/__init__.py`
- `services/worker/templates.py`
- `services/worker/tests/test_validation.py`

Deliver:

- [x] Resolve a solid fill to one candidate colour and a gradient to all stop
  colours.
- [x] Evaluate text contrast against every candidate stop and use the worst
  ratio. This deliberately conservative rule is deterministic and safe.
- [x] When a background shape has opacity below `1`, composite each candidate
  against paper white for this slice and document the limitation; general
  backdrop compositing is deferred.
- [x] Ensure unknown gradient swatches produce structured validation/compiler
  errors, never `TypeError` or a white-background silent fallback.
- [x] Confirm brand profile merging leaves gradient definitions intact.
- [x] Confirm a template swatch binding aimed at `fill` replaces the complete
  fill (solid or gradient); changing an individual stop is not a `0.2` template
  feature.
- [x] Add isolated tests in
  `services/worker/tests/test_gradient_validation.py` for best/worst stops,
  translucent backgrounds, unknown stop swatches and template replacement.

**Status:** complete on 18 August 2026.

**Evidence:** contrast evaluates all gradient stops and takes the lowest ratio;
semi-transparent background candidates are composited over paper white only.
General backdrop/layer compositing remains intentionally deferred. Five focused
tests cover worst-stop contrast, opacity, unknown stops, merge preservation and
whole-fill template replacement.

No vision or heuristic scoring belongs in this task.

---

### T07 — build the permanent synthetic agency-card conformance fixture

**Dependencies:** T03, T04, T05 and T06.

**Purpose:** prove the requested construction before any BYOMA assets or taste
judgements enter the system.

Target geometry:

- trim: `150 × 150 mm` = `425.19685 × 425.19685 pt`;
- bleed: `3 mm` = `8.503937 pt`;
- safe area: at least `6 mm` = `17.007874 pt` inside trim.

Deliver under `services/render/tests/fixtures/agency-card-0.2/`:

- [x] `document.json` with a two-swatch gradient background, neutral
  transparent cut-out image on the left half, right-side type hierarchy,
  several filled rounded-star `shape.d` motifs at `opacity: 0.5`, logo
  clear-space placeholder, and an open `CutContour` production test path.
- [x] A deterministic asset generator plus its small transparent PNG output;
  do not use real people, products, logos or BYOMA styling.
- [x] `README.md` identifying every assertion and how to regenerate assets.
- [x] Compiler tests for determinism, vector motif geometry, gradient/opacity
  mapping and image placement.
- [x] A render-conformance script that produces two proofs/packages and checks
  pixel-identical proofs, proof dimensions, no text overflow, named
  `CutContour`, output intent, embedded fonts and the required PDF/X marker.
  Do not require PDF bytes to match because producer metadata can vary; require
  the same semantic package checks on both outputs.
- [x] A human-viewable proof artefact for review, generated by the pinned
  container and clearly labelled synthetic/non-brand.

Required service run:

```bash
docker compose build render
docker compose up -d render
curl localhost:8127/healthz
```

Use the existing endpoints and `services/render/tests/check_separation.py`.
Do not assert that any `/Separation` is sufficient; `/All` from crop marks is
not the named `CutContour` acceptance condition.

Acceptance: the fixture visibly demonstrates every requested construction
capability and the repeat proof/package checks pass twice in the same pinned
container. Creative quality is intentionally not an acceptance criterion yet.

**Status:** complete on 18 August 2026.

**Evidence:** the synthetic fixture compiles byte-stably and its three focused
compiler tests pass. Pinned `ide8-render` (Scribus 1.6.1) produced two
pixel-identical 443×443px, 72-dpi bleed-inclusive proofs; both packages passed
the overflow, named `CutContour`, PDF/X marker, output-intent and embedded-font
checks. See `proof-synthetic.png` and `PROOF-SYNTHETIC.md` in the fixture.

---

### T08 — prepare the brand-pack intake and design scorecard

**Dependencies:** T00.

**Parallel:** safe at any time.

**Purpose:** make the design team's eventual delivery immediately ingestible
without pretending we already know BYOMA's rules.

Deliver under `services/worker/examples/byoma-pilot/`:

- [x] `README.md` with the expected directory tree, naming conventions,
  licensing fields and intake checks.
- [x] `brand/manifest.template.json` covering file role, version, owner,
  licence/embedding permission, colour space, dimensions/resolution and hash.
- [x] `brand/profile.template.json` separating hard rules from
  `designPrinciples`.
- [x] `brief.template.json` for the real 150 × 150 mm card and copy deck.
- [x] `DESIGN-REVIEW.md` containing the seven scorecard dimensions from the
  parent plan, a 1–5 anchored scale, reviewer, notes, craft-minutes and a
  go/adjust/stop decision.
- [x] `.gitkeep`/ignore handling so licensed fonts, unreleased imagery and
  client files are not accidentally committed.

**Status:** complete on 18 August 2026.

**Evidence:** neutral, non-brand templates and a seven-dimension review
scorecard now live in `services/worker/examples/byoma-pilot/`. The intake
directory ignores approved client artefacts and keeps only empty placeholder
directories under version control.

Do not download brand assets, scrape brand rules or infer official colours,
fonts, copy or logo clearance from public marketing material. This task is a
neutral intake scaffold only.

---

### T09 — integration gate and handoff evidence

**Dependencies:** T01–T08 complete, or an explicitly accepted T04 ADR.

**Purpose:** finish Stage A with evidence and one clear decision point.

Deliver:

- [x] Run both complete Python suites.
- [x] Run the T07 pinned-container conformance test twice.
- [x] Confirm the original `0.1` golden is byte-identical and stored `0.1`
  mutation tests pass.
- [x] Confirm the pilot can select `0.2` explicitly without changing the
  default for existing installs.
- [x] Add `docs/briefs/byoma-pilot/STAGE-A-RESULTS.md` with exact commands,
  pass/fail evidence, generated proof links, known limitations and the T04
  decision if applicable.
- [x] Update the parent plan's status; do not mark Stage B or C complete.
- [x] Leave the worktree free of generated databases, API keys, temporary
  proofs outside the named fixture, or real client assets.

**Status:** complete on 18 August 2026.

**Evidence:** renderer suite `40` passed; worker suite `136` passed; explicit
route check reported `default=0.1 explicit=0.2`; two independent invocations of
the pinned-container conformance script passed, each internally proving a pair
of pixel-identical proofs/packages. See `STAGE-A-RESULTS.md` for exact commands
and limitations. Existing ignored worker database files from 16 July 2026 were
verified untouched; no Stage A temporary files escaped their named fixture.

Full local gates:

```bash
python3 -m unittest discover services/render/tests
python3 -m unittest discover services/worker/tests
```

Stage A is complete only when the technical fixture is reproducible and the
results document lets a reviewer decide whether Scribus remains acceptable for
the BYOMA pilot.

## 5. Tasks deliberately blocked on the design department

Do not start these from public guesses. They become executable when the
requested material arrives.

- [ ] **B01 — intake audit:** hash, identify, preview and licence-check every
  supplied file; report gaps without converting originals.
- [ ] **B02 — BYOMA profile:** encode approved swatches, fonts, logo rules,
  minimum sizes, safe zones, required copy and production rules.
- [ ] **B03 — design evidence:** catalogue approved/rejected examples and the
  designers' reasons as `designPrinciples`, not machine rules unless measurable.
- [ ] **B04 — pilot brief:** freeze copy, image choices, dimensions, mandatories
  and named creative axes with one design approver.
- [ ] **C01 — six directions:** generate six structurally different concepts
  using the real pack and record every version/proof/validation report.
- [ ] **C02 — design review:** score all six before refinement; select one or
  stop with evidence.
- [ ] **C03 — refine/package:** art-direct the selected concept, export PDF/X-4,
  run Dimension's PitStop profile and record designer finishing time.
- [ ] **C04 — decision:** attribute remaining gaps to brand intelligence,
  model direction, document vocabulary, Scribus rendering or workflow and make
  the go/adjust/stop recommendation.

## 6. Scope guard

Stage A does **not** include a drawing UI, general PSD/IDML/Affinity import,
blend modes, masks, nested transparency groups, a renderer replacement, live
brand scraping, autonomous client release or a claim that the synthetic card
is creatively successful. If one of those becomes necessary, capture it as a
separate decision rather than quietly expanding this slice.
