**ide8.flow — repository review and proposed delivery plan**

Historical review: the findings below describe the repository before this day's
implementation. The integrity defects were addressed, and local brand/project,
PDF extraction and client-review workflows were subsequently added. Consult
[the PRD's implementation checkpoint](PRD.md) and the
[PDF/client-review guide](PDF-EXTRACTION-AND-CLIENT-REVIEW-2026-09-05.md) for current
status; the launch gaps and unimplemented proposals remain explicitly tracked.

Reviewed 5 September 2026. Release target confirmed by Luke: internal studio use plus client review and approval. Delivery team: Luke and Nova. No committed deadline was supplied. This is a proposed plan, not an instruction to implement every earlier feature proposal.

**Assessment**

ide8 has a substantial, reusable engine and an internal preview UI. It is not yet a dependable client-facing product. The largest gap is completing and securing the journey around the engine: project organisation, reliable jobs, reproducible artwork, human approval, finishing and export. Several concrete integrity defects need correcting before a client can approve anything authoritatively.

Keep the renderer-neutral document, deterministic compiler, validation pipeline, immutable version concept and Scribus renderer. Complete a narrow but whole studio-to-client workflow. Assess creative usefulness on real briefs from the start; technical completion alone will not establish product value.

The earlier orchestration/raster plans remain useful directions. They should become a prioritised capability backlog within this release programme rather than its entire definition.

**What this review covered and verified**

Reviewed the current checkout on `codex/byoma-stage-a`, HEAD `729c7e3`, including the existing uncommitted project/brand changes and their new tests. Those changes must be reviewed and integrated deliberately; a checkout containing them is not evidence they have shipped. Existing application changes and local project data were left untouched. Only this review document was added to the repository.

Read the PRD, schema routing and schema capabilities, historical pilot/gap reports, worker API/store, generation and mutation loops, asset/brand handling, validators, rendering/export code, UI flows, Dockerfiles and CI configuration. Tested with temporary databases and scripted model responses; made no paid model calls or changes to connected client systems.

| Verification | Result | Practical limit |
|---|---|---|
| Worker suite | 156 tests passed using installed system Python dependencies | The local `.venv` lacks Pillow: its first run produced six dependency errors, not six established application regressions |
| Renderer/compiler suite | 40 tests passed | Unit and service-compile coverage, not a complete production preflight |
| UI | TypeScript check and production build passed | No interactive browser usability or accessibility assessment performed |
| Real Scribus execution | Current renderer source mounted read-only into disposable existing `ide8-render` image `7cfbcfdab9c3`; two synthetic agency-card proof/package runs passed | Local synthetic fixture; not a real-brand acceptance test or a new deployment build |
| Repeatability/export semantics | Identical SLA and proof bytes; 443×443 proof; no overflow; named CutContour; output intent, PDF/X and embedded-font markers present | Markers are not full PDF/X certification; PitStop and Phoenix were not run in this review |
| Targeted negative cases | Legal-copy loss, stale proof/document pairing, historic brand drift and unchecked format mismatch reproduced | Scripted model outputs demonstrate reachable software defects, not their frequency with a live model |

The two local proof-plus-package checks took approximately 1.46s and 0.79s. These are smoke measurements, not p95 or concurrent-load evidence. The existing 40 renderer and 156 worker tests passing does not cover the additional defects reproduced below.

**Current product inventory**

| Product area | Current implementation | Release implication |
|---|---|---|
| Document and rendering | Schemas 0.1/0.2; deterministic JSON→SLA; geometry, gradients, opacity and controlled image placement; proofs and renderer-level PDF/X packaging | Strong foundation to preserve |
| Concept generation | Anthropic tool loop, archetype fan-out, deterministic repair, visual self-critique, model escalation, usage metering | Functional; reliability and real creative acceptance need work |
| Mutation/history | Natural-language mutations, structural diff, immutable document rows, proof history | Functional but protected-content and artifact integrity defects block trusted approvals |
| Brands/projects | Brand admin; new immutable brand versions, project APIs and campaign overrides in current working changes | Partial foundation; historical replay and UI integration incomplete |
| Studio UI | Brief form, global proof grid, detail view, comments, discard/restore, uploads, brand admin and usage dashboard | Internal preview; not a project-centred application yet |
| Assets | Global write-once names; PNG/JPEG/TIFF bytes in SQLite; staging into renderer and craft bundle | No scoped/versioned lineage; no SVG ingestion, transformations or robust production metadata |
| Client review | No login, invitation, client-specific API/view, human approval record or review state machine found | Essential new release work |
| Finishing/export | JSON, SLA, proof PNG and craft ZIP downloads | No normal concept PDF download/release route; craft return is explicitly unimplemented |
| Templates | Backend promotion, bindings and batch rendering exist | No UI; promotion does not enforce approval; defer exposure until corrected |
| Operations | Docker Compose, SQLite/WAL, in-process daemon jobs, unit CI and render-image smoke | No deployment configuration for the PRD's Azure/Supabase target, durable worker queue, restore procedure or cross-service tracing found |

**Confirmed integrity defects — fix first**

1. **An old version can export differently after a project change.** `_profile_for_version` uses the project's current brand pin and overrides. The job stores some original brand metadata, but export/mutation resolution does not use it. A temporary-store reproduction repinned a project to a changed brand: the document hash remained identical while compiled SLA changed. Templates also resolve the current brand by name. Persist an immutable effective-profile snapshot/reference with each version/render input, and use it consistently for proof, mutation, download and template binding. A mutable project chooses defaults for future work; it must not rewrite historical output. [Profile resolution](/Users/lukeatkins/dev/Ide8/services/worker/app.py:110), [template rendering](/Users/lukeatkins/dev/Ide8/services/worker/app.py:821).

2. **A layout-only mutation can remove legal copy and still pass.** The mutation loop runs validation without the brief; the omission is explicitly documented. A scripted mutation dropping the legal frame returned `validation.ok=true`, while the brief checker reported both missing mandatory content and missing copy. Preserve a versioned content contract; permit intentional copy changes through explicit, scoped edits. Check all remaining protected copy, mandatory assets and production geometry. A prompt asking for a surgical change is insufficient enforcement. [Mutation validation](/Users/lukeatkins/dev/Ide8/services/worker/generation/mutation.py:124), [brief validation contract](/Users/lukeatkins/dev/Ide8/services/worker/validation/__init__.py:33).

3. **A stored proof can belong to a different generation attempt.** After a valid proof is visually rejected, an overflowing last iteration replaces `result.document` without replacing/clearing the previous proof. Reproduced with document B saved alongside proof A and an overflow report. Keep document, proof, validation and critique together as one candidate result. Retain rejected attempts separately from the last complete candidate. Never publish a mixed artifact set. [Generation overflow handling](/Users/lukeatkins/dev/Ide8/services/worker/generation/loop.py:203).

4. **The requested output format is not a deterministic gate.** An A4 portrait document passed validation against a brief requesting A3 landscape. Current brief checks cover copy and item names, not page geometry. Validate or construct the requested dimensions, orientation, bleed and required production marks from a typed format specification. Extend the same contract to mutations and variants. [Brief checks](/Users/lukeatkins/dev/Ide8/services/worker/validation/brief_checks.py:50).

These should become regression cases before changing the surrounding architecture. The existing tests are useful assets; extend them around the failures rather than replacing them.

**Other release blockers and important gaps**

| Priority | Finding and evidence | Required outcome |
|---|---|---|
| Blocker | Worker routes have no authentication/authorisation dependencies. Comments all use a configured `designer` identity. Assets and concepts are globally listed. [API](/Users/lukeatkins/dev/Ide8/services/worker/app.py:46), [comment identity](/Users/lukeatkins/dev/Ide8/services/worker/app.py:551) | Named users, project membership, role checks and private files; clients can access only specifically shared material |
| Blocker | `approved` is the creator model's self-critique verdict; badges label it approved. No human approval entity/action exists. [Badge](/Users/lukeatkins/dev/Ide8/services/ui/src/components/Badges.tsx:1) | Separate technical validation, AI assessment, internal selection and client approval |
| Blocker | UI calls legacy `/generate` and global `/concepts`, not the new project endpoints. Grid takes the first concept's title for all concepts. Navigation/job identity lives only in React memory. [UI client](/Users/lukeatkins/dev/Ide8/services/ui/src/api.ts:180), [grid](/Users/lukeatkins/dev/Ide8/services/ui/src/components/ConceptGrid.tsx:19) | Project list/detail, saved briefs, scoped grids, shareable URLs and refresh-safe job status |
| Blocker | Generation and template jobs run in daemon threads. There is no restart recovery/lease consumer. Each submitted job has its own fan-out pool; the current limit is not a global concurrency ceiling. [Job launch](/Users/lukeatkins/dev/Ide8/services/worker/app.py:204) | Durable jobs, bounded global concurrency, retries, cancellation, restart reconciliation and explicit partial/failure outcomes |
| Blocker | Worker has no normal `/versions/{id}/artwork.pdf` endpoint or approved release manifest; PDF generation exists in the renderer and template path. Craft bundle advertises an unimplemented return route. [Bundle](/Users/lukeatkins/dev/Ide8/services/worker/app.py:671) | Exact-version PDF/proof packages, finishing return and recorded manual handoff |
| Blocker | `_asset_map` offers all uploaded assets to each generation; there is no project/brand eligibility boundary. Reference assets are names/dimensions in prompt text, not visual inputs to the initial layout call. [Asset collection](/Users/lukeatkins/dev/Ide8/services/worker/generation/service.py:17), [prompt](/Users/lukeatkins/dev/Ide8/services/worker/generation/prompts.py:60) | Explicit eligible assets, visual thumbnails/references where useful, semantic roles and protected logos/packshots |
| High | Fonts can be whitelisted without being installed. Raster ingestion trusts simple signatures, has unknown TIFF dimensions, and lacks effective-DPI/colour-profile checks. A header-only PNG was recognised by the sniffer in a negative check. [Assets](/Users/lukeatkins/dev/Ide8/services/worker/assets.py:21) | Decode/verify images, preserve originals, generate previews, inspect dimensions/alpha/profile, check placed resolution and installed brand fonts |
| High | Default generation remains 0.1. UI has no schema selection, and worker Dockerfile copies `example.json` but omits `example-0.2.json`, which the 0.2 route requires. [Routing](/Users/lukeatkins/dev/Ide8/services/worker/schema_registry.py:19), [Dockerfile](/Users/lukeatkins/dev/Ide8/services/worker/Dockerfile:12) | Package every supported route; deliberately enable 0.2 for new work after deployment checks; retain exact 0.1 replay |
| High | A missing overflow report returns an empty list; report collection errors can therefore look clean. Render endpoints call blocking subprocesses inside async handlers. [Report handling](/Users/lukeatkins/dev/Ide8/services/render/service/app.py:96) | Fail closed on missing/failed validation evidence; bounded rendering execution and queue/load tests |
| High | Failed attempts are not fully accounted for: stats aggregate stored versions, failed mutations are not persisted, and a later exception can discard already-incurred model usage. [Stats](/Users/lukeatkins/dev/Ide8/services/worker/store.py:800), [exception handling](/Users/lukeatkins/dev/Ide8/services/worker/generation/service.py:58) | Persist per-call/attempt usage independently; enforce project/job spend ceilings before dispatch |
| High | Templates can be promoted without approval and compile against a live brand; `hand_finished` is a stored origin value without an actual upload/locking workflow. | Keep template endpoints internal until their lifecycle rules match the release contract |

**Definition of the first working product**

A designer signs in, opens a project, selects an approved brand pack, supplies copy and assets, and creates useful concepts for supported POS formats. They can refine and finish a selected concept, send explicitly selected versions to an invited client, receive comments and an attributable approval, then download the exact approved production package. Refreshing a browser or restarting a worker does not lose the job or change the artwork. Another client cannot retrieve the project or its files.

Initial boundary: one studio organisation, a small number of pilot brands, one named client approver per review, supported flat POS formats with explicit dimensions and bleed, and manual PitStop/Phoenix handoff. Multi-approver quorum, arbitrary shaped-product construction and automated downstream integrations remain later work unless a pilot requires them. This is a proposed scope boundary for discussion, not a claim that these features are already agreed out of scope.

Format handling still needs to be real: a project can request a master and at least one supported additional size, with one document and approval/sign-off state per output. Begin with a constrained adaptation workflow and human review; do not promise arbitrary automatic reflow or consistent kit design without evidence.

**Architectural decisions to carry forward**

- Keep React/Vite and the Python application. Extract focused modules from the growing API/store as the relevant work lands; a frontend or framework rewrite is unnecessary.
- Keep Scribus and the canonical generated-document schema. Store exact render inputs and outputs as immutable artifacts, including effective brand profile, asset-version hashes, compiler/render-image identity, font manifest and output settings. A document JSON hash alone cannot identify the complete artwork.
- For client release candidates, build a fixed review package whose proof is derived from the recorded production PDF under a documented proof policy. Approval references that package's identity and hashes. Later changes create a new package and require a new approval; downloads of an approved package retrieve the stored bytes.
- Keep supplied and generated/derived assets under the same ownership and version conventions. Logical names can be convenient in authoring, but a stored version must resolve to exact bytes.
- Use the PRD's planned Supabase Postgres/Storage foundation for the shared application. This is a migration project, not the store module's claimed driver/DSN swap: SQLite SQL/triggers, BLOB storage, membership policies, transactional jobs and historical references all need explicit treatment.
- Prefer a single application identity mapped to staff and client memberships. Supabase documents Microsoft Entra/Azure login, so staff Microsoft sign-in can fit the planned foundation; configure and test staff identity separately from invitation-scoped client access. [Microsoft login documentation](https://supabase.com/docs/guides/auth/social-login/auth-azure).
- Enforce project and review-package permissions at the API and data/file access boundaries. A privileged worker connection can bypass row policies, so RLS alone does not authorise a gateway request. Test the actual credential path used by each operation. [RLS documentation](https://supabase.com/docs/guides/database/postgres/row-level-security), [storage permissions](https://supabase.com/docs/guides/storage/security/access-control).
- Use one application codebase with separate API and durable worker processes, plus the existing render container. Avoid a separate model gateway service, vector service and raster service until operation or scaling needs justify them. The renderer stays private.

**Proposed delivery sequence**

Each stage ends with a demonstrable user outcome. Technical IDs below refer to the existing PRD; the new integrity checks should get explicit delivery tickets rather than disappearing inside a broad refactor.

| Stage | Work | Exit evidence | Rough focused delivery days |
|---|---|---|---|
| 0 — Establish the release baseline | Integrate/review current project changes; resolve PRD/new-feature contradictions; fix the four integrity defects; package 0.2; add failure-path regressions; separate AI verdict labels from approval | Existing suites plus new integrity cases pass; supported schemas load inside built worker image; historic export survives changed project defaults | 3–5 |
| 1 — Shared data and access | Supabase migrations and object storage; staff/client identities; memberships and roles; private artifacts; narrow API projections; staging deployment; migration/backup/restore rehearsal | Two distinct client identities cannot access each other's records, proofs or downloads through UI, API or storage; existing versions migrate with intact identities/hashes | 5–9 |
| 2 — Usable studio workspace | Project UI and URLs; saved brief/format contract; eligible assets and brand readiness; durable jobs for generation, mutation and render; partial failures, retry/cancel, spend guardrails | Designer starts a project, refreshes/reopens it, generates and mutates; worker restart recovers safely; budget and failed-call costs remain visible | 5–8 |
| 3 — Finish and package real artwork | Font availability and image metadata/DPI; supported supplied-vector intake; exact asset replacement; constrained second-format adaptation; stable PDF export; craft return | Pilot artwork opens in the agreed studio editor, returns with a fresh proof, and produces a downloadable package with matching source/assets/output identities | 5–9 |
| 4 — Client review and approval | Curated immutable review packages; invitations with expiry/revocation; client-only views; version-specific comments; named approval/request-changes; audit/history; approved download | Client reviews v1; studio creates v2; old approval never approves v2; unshared drafts/costs/prompts remain inaccessible; repeated approval submits are safe | 5–8 |
| 5 — Pilot and release | Real briefs, designer timing, client acceptance run, independent PitStop checks, failure/restore/load tests, operational runbook, support and rollback path | Three agreed pilot briefs complete through studio, client decision and manual production handoff; all release blockers closed | 5–10 |

These are planning ranges, not commitments: approximately 28–49 focused delivery days before contingency. For the two of us, provisionally think 8–12 calendar weeks if this is the main priority and access/feedback are available. Re-estimate after Stage 0 and the first real-brand run. Part-time availability, missing brand/font permissions, identity setup or major craft interoperability gaps will extend this. No fixed launch date should be inferred.

Requirements covered: Stage 0 GEN-6/7, VAL-5/6/7, BRAND-4/6; Stage 1 AUTH-1..4 and the PRD data/security NFRs; Stage 2 BRF-1/2, REV-1..3, GEN-2/5, ADM-2/3; Stage 3 RND-5, EXP-2/3/5, constrained VAR-1/2; Stage 4 REV-5..7/9; Stage 5 measured quality/performance and manual production acceptance. ADM-1 remains but becomes complete attempt accounting rather than only successful-version totals.

**Creative usefulness must run alongside delivery**

Start with three actual supported briefs: a straightforward promotion, a dense copy/price case and an image-led brand case. Obtain the approved assets, fonts, copy and an existing designer outcome for comparison. During Stage 0, rerun these with the deployed schema/model configuration, record first-pass validity, usable distinct concepts, repair cost and actual designer craft minutes. Agree the acceptance bar with the studio before optimising.

The historical Harvest A/B test was confounded by a now-fixed line-height issue and did not establish current creative quality. The BYOMA Stage A result explicitly uses synthetic/non-brand inputs and leaves real-brand evaluation pending. Treat neither as a current product acceptance study. [Harvest results](/Users/lukeatkins/dev/Ide8/docs/briefs/harvest-edit/AB-PRINCIPLES-RUN-1.md), [BYOMA results](/Users/lukeatkins/dev/Ide8/docs/briefs/byoma-pilot/STAGE-A-RESULTS.md).

Suggested pilot bar to agree: at least two sufficiently distinct, usable directions from a six-concept run on each pilot brief; selected output can reach the studio's client-ready standard with at most about 15 minutes of finishing; no unintended changes to protected content; every released pilot package passes the agreed preflight. Measure failures and reruns too. These are proposed acceptance targets, not measured results.

Build a small provider interface while touching the generation loop, preserving the existing adapter. Add one challenger only if current models fail the pilot quality or cost bar. Separate critique inputs from the creator's conversation, record a structured scorecard and compare it with designer assessment. A different model can be useful, but human agreement is the test of independence's value. AI scoring never grants a human approval.

The likely first improvement to asset-aware generation is ensuring the model receives the correct project assets and can see useful thumbnails/reference images. Benchmark that alongside prompt/example improvements before assuming another generator will solve composition quality.

**How the raster/vector plans fit**

| Capability | Proposed release treatment | Reason |
|---|---|---|
| Scoped assets, exact versions, provenance, precise replacement | Foundation for release | Required for approved artwork identity and future transformations |
| Supplied SVG/vector logo handling | Required for pilot brands that supply vector masters; narrow supported subset first | Existing source artwork must make it through the real studio workflow |
| Crop/focus controls | Expose existing 0.2 placement where useful | Often a document-placement edit, not a reason to create another raster file |
| Background removal + deterministic duotone | First controlled enhancement once lineage is in place; pull forward if pilot asset preparation is the actual bottleneck | Valuable workflow completion, with visible originals and derivatives |
| Generated vector assets | Bounded pilot after vector ingestion and replacement work | Same contract supports Recraft and direct LLM SVG; no need to commit to a universal winner |
| SVG-specific semantic judge | Advisory benchmark component initially | Semantic similarity does not establish editability, colour-production semantics or renderer compatibility |
| Independent whole-artwork judge | Thin scoring boundary early; expand if designer comparison shows benefit | Supports measured creative improvement without making another model integration the release definition |
| Three layout providers, four vector providers, automatic specialist routing | Later unless a bounded quality experiment identifies a necessary route | Larger integration/testing surface for a two-person delivery effort |
| Retouch, background extension, richer brand treatments, broad schema 0.3 | Later, driven by actual briefs | Their value can be assessed against measured studio preparation/craft time |

For any raster colour treatment, specify whether the requested output is a process-colour appearance or actual named print separations. Do not equate a preview colour label with production colour semantics. Validate that distinction in the selected renderer/export workflow.

Native SVG intake and generated SVG evaluation share the same technical validation/renderer boundary. Keep XML/feature safety, geometry complexity and output preservation checks distinct from an AI semantic score. The SVG-Score paper motivates benchmarking routes but does not determine ide8's provider choice or validate vector editability. [Paper limitations](https://arxiv.org/html/2609.03806v1).

**Client approval and the craft pass need one explicit rule**

An approval always names a specific immutable review package. Staff may request creative direction approval on a concept, but production approval must cover the final finished artifact. If the designer changes artwork after approval, that creates another version and approval request.

Generated editable work remains canonical JSON. A hand-finished branch records its authoritative uploaded source/package as `hand_finished`; it does not pretend a stale JSON document describes manual changes. Store and render that branch independently and disallow LLM mutation of it. Start with manual download/upload. Choose SLA round-trip or a frozen PDF plus source package according to the studio's actual finishing tool and prove one real round-trip in Stage 0/3. An uploaded finished PDF must be preflighted and its own proof presented for approval.

Hosted Scribus, IDML conversion, protocol handlers and in-editor return scripts are not prerequisites for this first complete path. If the studio cannot finish the supplied artifacts efficiently in its actual tools, that finding changes the critical path; do not hide it behind an assumed Scribus adoption.

**Release gates and operational work**

- Identity: real staff login, invitation-only client access, author identities, expiry/revocation and cross-project denial tests covering every artifact and mutating endpoint. Clients see only curated versions; private cost, prompts, internal comments and unused assets are omitted server-side.
- Approval: atomic/idempotent actions against the reviewed package, audit events, stale-version checks and a new decision for any changed artifact. Approver quorum is deliberately one named person for the initial proposal.
- Correctness: protected copy/assets/geometry; requested format; exact version inputs; no stale proofs; invalid or missing overflow evidence blocks a release candidate; brand/fonts/assets pass readiness checks.
- Reliability: durable attempt records, bounded work admission, restart recovery, timeouts, retry/cancel behaviour, duplicate-submission protection and accurate cost accounting even after failures. An uncertain paid-provider timeout needs reconciliation/bounded retry, not blind repeated dispatch.
- Deployment: reproducible worker/UI/render images, supported-route smoke tests, pinned dependencies and image identifiers, migrations, secrets/configuration, private renderer networking, health/readiness checks, staging-to-production rollback and database plus object-storage restore tests.
- Usability: URL-addressable project/review pages, clear empty/error states, browser-refresh recovery, responsive client review, accessible comments/approval controls and a realistic onboarding pack. Validate with a designer and invited reviewer, not only a build.
- Production: download exactly the approved bytes, include per-file hashes and sign-off identities, record manual preflight/handoff and preserve failure reports. Production automation follows once this manual boundary works.
- Evidence: browser end-to-end checks using independent identities, HTTP pipeline integration, concurrent job/restart tests and actual studio/client pilot acceptance. Fresh API tests should load supported schema routes from the built worker image, which current CI does not verify.

**Work to keep off the initial critical path**

Monday.com/n8n/Phoenix automation, realtime cursors/presence, complex voting/quorum, template/VDP UI, arbitrary kit reflow, general image editing, broad specialist routing, IDML and hosted-editor infrastructure. Existing template endpoints should be protected or disabled externally until their approval/provenance rules are complete. Keep the implemented deterministic template engine for later use.

The PRD currently excludes raster editing while the new plan proposes it, calls the product a live canvas while later rejecting WYSIWYG editing, and mixes old milestone descriptions with newer features. Reconcile these into one release scope and delivery board. Historical milestone dates and previous cost/latency measurements remain historical evidence rather than launch estimates.

**How Luke and Nova can deliver this**

Nova owns implementation proposals, small reviewable changes, automated checks, migration tooling, staging verification and evidence. Luke owns the business scope, account/access setup that requires the company, approved brand/source inputs and scheduling short designer/client validation sessions. We still need real reviewers even if they are not developers; studio quality and client usability cannot be signed off by code alone.

Keep one active delivery slice with explicit exit evidence. Obtain identity/hosting access, the approved pilot pack and a representative finishing workflow at the start so they do not surface as week-six blockers. Spend the first focused block closing the reproduced integrity defects and proving the real-asset craft path while finalising the data/access contract. That produces a reliable base for the client-review work and tells us early whether creative quality or handoff needs more investment.
