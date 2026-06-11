# ide8.flow — Product Requirements Document

**AI-assisted creative-to-production platform for retail POS artwork**

| | |
|---|---|
| Version | 0.2 |
| Date | 11 June 2026 |
| Owner | Luke — Print Services Director, Dimension Development Ltd |
| Status | Pre-development. Greenfield build; render-engine architecture proven in spike (see §13.1) |

**Changes in v0.2** — terminology fixed: generated instances are *documents*, the spec they conform to is the *document schema* · RND-3 sharpened to require *named* separations after verification of the spike PDF (`/Separation /All` false-pass trap) · byte-stable compilation added to RND-2 and the M0 exit criteria · RND-4 acknowledges the warm-renderer process model · VAL-6 promoted P1 → P0 and added to M1 · document-schema versioning / no-migration policy added to §8 and §10 · normative schema spec extracted to `docs/SCHEMA.md` (§13.2).

---

## 1. Vision

ide8.flow collapses the POS creative cycle from days to minutes. A brief goes in; an AI ideation engine generates genuinely distinct layout concepts as structured vector documents; humans review, comment, and steer in a live canvas; approved concepts emit production-ready PDF/X — with spot cut paths, bleed, and crop marks — directly into Dimension's Phoenix/PitStop production pipeline.

The core architectural bet: **the document is data, not pixels.** Every concept is a small, declarative JSON document — an instance of the formal document schema — that compiles deterministically to a Scribus SLA and renders headlessly to proof rasters and print PDFs. The LLM authors and mutates the document; it never touches the renderer. This makes generation auditable, variants free, brand rules enforceable in code, and the entire iteration history replayable.

> **Terminology.** A generated concept artefact is a **document** (document JSON); the specification it conforms to is the **document schema** (`docs/SCHEMA.md`). "Schema" alone always means the latter.

The product is *AI for the first 80% of iteration, designers for the finishing pass, production pipeline untouched.* A human designer can open any generated document in Scribus (or via IDML export, InDesign) at any point. ide8.flow augments the studio; it does not replace it.

## 2. Problem

A concept round for POS artwork currently costs designer-hours per variation. Client reviews happen against static PDFs over email, feedback is lossy, format adaptations (A4 → A3 → shelf strip) are manual rework, and approval audit trails live in inboxes. The studio's capacity, not its creativity, caps how many directions a client ever sees.

## 3. Users & personas

| Persona | Role in flow | Primary needs |
|---|---|---|
| **Concept designer** (internal) | Initiates briefs, curates AI output, performs craft pass | Fast fan-out, real .sla/IDML escape hatch, never blocked by the tool |
| **Account manager** (internal) | Runs client reviews, manages timeline | Shareable review links, status visibility, Monday.com sync |
| **Client reviewer** (external) | Comments, votes, approves | Zero-friction access, simple proof grid, comment + approve |
| **Pre-press / production** (internal) | Consumes approved artwork | Compliant PDF/X, correct spot separations, no surprises |
| **Admin** (Luke / IT) | Brand profiles, users, system health | Profile management, audit, cost visibility |

## 4. Goals & success metrics

| Goal | Metric | Target (6 mo post-launch) |
|---|---|---|
| Compress ideation cycle | Brief → first 6-concept proof grid | < 5 minutes |
| Increase creative breadth | Distinct concepts shown per brief | ≥ 6 (vs typically 2–3 today) |
| Fast refinement | Comment → regenerated proof | < 60 seconds |
| Free format variants | Time to produce size adaptation of approved concept | < 2 minutes, zero designer time |
| Production-safe output | Approved exports passing PitStop preflight first time | ≥ 95% |
| Adoption | Briefs run through platform by internal studio | ≥ 50% of eligible POS briefs |
| Auditability | Approvals with full version + commenter trail | 100% |

## 5. Scope & phasing

### Phase 0 — Render engine service (foundation, internal only)
The proven spike, productionised. No UI.

### Phase 1 — Ideation engine + internal review (MVP)
Brief intake, generation loop, validation, proof grid with comments, manual export. Internal users only (Alex's design team as pilot).

### Phase 2 — Client review & production handoff
External reviewer access, approval gates, PDF/X packaging into Phoenix/PitStop via n8n, Monday.com sync.

### Phase 3 — Scale & craft
IDML export, chained text frames, image/asset library, house-style image generation hooks (ComfyUI/FLUX), template/kit system, analytics.

**Out of scope (all phases):** raster image editing, general-purpose page layout UI (no drawing tools — by design), video/motion, e-commerce artwork, fully autonomous (human-gate-free) production release.

## 6. End-to-end user flow (Phase 2 target)

1. **Brief.** Designer or AM creates a project: campaign name, formats required (e.g. A3 landscape header + 165 mm shelf strip), brand profile, copy deck, mandatory elements, references. (`BRF-*`)
2. **Fan-out.** Engine generates N (default 6) distinct concepts. Each passes deterministic validation, renders, self-critiques via vision, and auto-fixes before surfacing. (`GEN-*`)
3. **Curate.** Designer views the proof grid, discards weak options, optionally requests "6 more like #3." (`REV-*`)
4. **Refine.** Conversational mutations per concept ("more arch on the tab, two-column body"). Each round trip < 60 s. (`GEN-7`)
5. **Client review.** AM shares a review link. Clients comment per-concept, vote, request changes (comments can drive regeneration), and approve against the gate. (`REV-5..9`)
6. **Variants.** Approved master concept reflows to every format in the brief automatically; designer eyeballs each. (`VAR-*`)
7. **Craft pass (optional).** Designer downloads .sla / IDML, finishes by hand, re-uploads as a new locked version. (`EXP-3`)
8. **Release.** One click packages PDF/X per format → n8n → PitStop preflight → Phoenix hot folder; Monday.com item updated with proofs, files, approval record. (`PRD-*`)

## 7. Functional requirements

IDs are stable for task decomposition. Priority: **P0** = MVP-blocking, **P1** = Phase 2, **P2** = Phase 3.

### 7.1 Auth & tenancy (AUTH)

- **AUTH-1 (P0)** Internal staff authenticate via Microsoft Entra ID (SSO).
- **AUTH-2 (P1)** External client reviewers authenticate via Supabase magic-link auth, scoped to invited projects only.
- **AUTH-3 (P0)** Role model: `admin`, `designer`, `account_manager`, `client_reviewer`, `production` (mirrors LetsMakeIt's five-role pattern). Row-level security in Postgres enforces project access.
- **AUTH-4 (P1)** Review links are revocable and expiring.

### 7.2 Brand profiles (BRAND)

- **BRAND-1 (P0)** A brand profile is a versioned JSON fragment: locked swatches (CMYK + spot definitions), char styles, paragraph styles, logo assets, fonts, and rules (min type size, safe zones, contrast floor, mandatory elements).
- **BRAND-2 (P0)** Profiles merge into every generated document at compile time; the generator cannot emit colours or fonts outside the profile.
- **BRAND-3 (P0)** Admin CRUD UI for profiles, with visual swatch/style preview.
- **BRAND-4 (P1)** Profile versions are immutable once used by a project (reproducibility).
- **BRAND-5 (P2)** Import assist: extract candidate swatches/fonts from an uploaded brand guideline PDF for human confirmation.

### 7.3 Brief intake (BRF)

- **BRF-1 (P0)** Brief form: title, brand profile, formats (named sizes or custom mm/pt + orientation), copy deck (structured: headline, subhead, body, legal), mandatory elements, tone/direction free text, reference uploads.
- **BRF-2 (P0)** Formats support multiple outputs per brief; one is flagged `master`. Each format is a separate document — formats are never mixed within a document.
- **BRF-3 (P1)** Brief templates ("gondola end kit") pre-populate format sets.
- **BRF-4 (P1)** Briefs sync to Monday.com as items via n8n (create + status mirror).

### 7.4 Generation engine (GEN)

- **GEN-1 (P0)** A generation worker runs a Claude API tool-use loop: emit document JSON → validate → render proof → inspect raster (vision) → mutate → repeat until self-critique passes or iteration cap (default 4) reached.
- **GEN-2 (P0)** Fan-out: produce N concepts per brief with explicit diversity instruction (layout archetypes, not colourway tweaks). Concepts generate in parallel.
- **GEN-3 (P0)** All model output is validated against the document schema (formal JSON Schema) before compile; invalid output triggers structured repair, never silent acceptance.
- **GEN-4 (P0)** System prompt assembles from: document-schema spec, brand profile, brief, few-shot exemplars. Versioned as `prompt_pack` rows for reproducibility.
- **GEN-5 (P0)** Model routing: fast model (Sonnet-class) for fan-out and mutations; strong model escalation for failed self-critique or flagged-hard briefs. Per-project token/cost metering.
- **GEN-6 (P0)** Every accepted document is persisted as an immutable version with provenance: model, prompt pack version, parent version, document-schema version, validation report, proof raster.
- **GEN-7 (P0)** Mutation API: natural-language instruction + target concept → document diff → new version. Surface a before/after proof pair.
- **GEN-8 (P1)** "More like this": seed fan-out from an existing concept.
- **GEN-9 (P2)** Comment-driven regeneration: a client comment can be promoted to a mutation instruction by internal staff (never auto-executed from client input — prompt-injection boundary).

### 7.5 Validation layer (VAL)

Deterministic, ordered cheapest-first. VAL-1..5 run pre-render; VAL-6 reads back a renderer flag at proof time.

- **VAL-1 (P0)** Document-schema conformance (formal JSON Schema).
- **VAL-2 (P0)** Brand conformance: swatch whitelist, font whitelist, min type sizes.
- **VAL-3 (P0)** Geometry: frames within page+bleed bounds; safe-zone intrusion warnings; cut paths (`spot` stroke) must be open paths with stroke-only, no fill.
- **VAL-4 (P0)** Contrast: computed text colour vs underlying fill colour ≥ profile floor (catches invisible-text class of failure without a vision call).
- **VAL-5 (P1)** Copy integrity: all mandatory copy-deck strings present verbatim; legal text unaltered.
- **VAL-6 (P0)** Overflow detection post-render: the text-frame overflow flag is read back from Scribus during proof render and treated as a hard failure. *(Promoted from P1: overflow is the most common LLM layout failure, the flag is free at render time, and catching it deterministically saves vision-loop tokens — serving the §8 cost target.)*
- **VAL-7 (P0)** Validation reports persist against the document version (machine-readable, surfaced in UI).

### 7.6 Render service (RND)

- **RND-1 (P0)** Stateless Docker service: Scribus 1.6.x + xvfb + poppler + licensed fonts baked into the image. FastAPI endpoints: `POST /compile` (JSON→SLA), `POST /proof` (SLA→PNG at requested dpi), `POST /package` (SLA→PDF/X), `GET /fonts`, `GET /healthz`.
- **RND-2 (P0)** Compiler per the proven spike: donor-template boilerplate, per-PTYPE harvested defaults, page-relative→scratch translation, SVG path geometry, run-based text. Pinned to the Scribus version in the image; donor regenerated on image build. **Compilation is byte-stable:** identical document + compiler version + donor template produces a byte-identical SLA (deterministic item IDs, stable element order) — prerequisite for golden-file CI and the §8 reproducibility NFR. *(Known spike gap: the spike compiler generates random item IDs; fix lands in M0.)*
- **RND-3 (P0)** Spot-colour fidelity: packaged PDF/X must contain a `/Separation` colourspace **named for each spot swatch** (e.g. `/Separation /CutContour`). Acceptance test inspects the decompressed PDF for the *named* separation — presence of any `/Separation` alone is a false pass, because crop marks always contribute `/Separation /All` (registration). *(Verified on the spike output: the exported PDF's only separation is `/Separation /All`; CutContour was converted to process — see §12.)*
- **RND-4 (P0)** Proof render: < 2 s p95 at review resolution; deterministic output for identical input. Cold Scribus + xvfb startup alone exceeds this budget, so the service keeps **long-lived warm renderer processes**; "stateless" means no shared persistent state and per-request temp dirs, not process-per-request.
- **RND-5 (P1)** Image frames: assets fetched from Supabase Storage to local scratch pre-compile; missing-asset = hard validation failure.
- **RND-6 (P2)** Chained text frames (`NEXTITEM`/`BACKITEM`), text-on-path, gradients.
- **RND-7 (P2)** IDML export endpoint for InDesign handoff.
- **RND-8 (P0)** Horizontal scaling on Azure Container Apps; no shared state across replicas; per-request temp dirs.

### 7.7 Review canvas (REV)

- **REV-1 (P0)** Proof grid per brief: concept cards with raster proof, version badge, validation status, cost-to-date. Discard/restore.
- **REV-2 (P0)** Concept detail view: zoomable proof, version history timeline with visual diffs (proof thumbnails per version), mutation input box.
- **REV-3 (P0)** Comment threads anchored per concept (Phase 1) and per-region pin (P1; item `name`/`ANNAME` is the anchor). Liveblocks for realtime presence and comments.
- **REV-4 (P1)** Side-by-side compare of any two versions or concepts.
- **REV-5 (P1)** Client review mode: stripped-down grid, comment + vote per concept, no internal metadata (costs, prompts) visible.
- **REV-6 (P1)** Approval gate: named approver(s) per project; approving locks the version (immutable), records approver, timestamp, and exact document/proof hashes.
- **REV-7 (P1)** Status workflow: `draft → internal_review → client_review → approved → released` mirrored to Monday.com.
- **REV-8 (P2)** @mentions and notification digests (email via n8n).
- **REV-9 (P1)** Audit log view: every version, comment, approval, export per project.

### 7.8 Variant engine (VAR)

- **VAR-1 (P1)** On approval of master, auto-generate document variants for every other format in the brief: page-size parameter change + LLM reflow pass constrained to preserve approved content, styles, and hierarchy.
- **VAR-2 (P1)** Variants render to a variant grid for one-click designer sign-off each; sign-off required before release.
- **VAR-3 (P2)** Kit awareness: shared elements (logo lockup, key visual) maintain consistent scale relationships across formats per profile rules.

### 7.9 Export & escape hatch (EXP)

- **EXP-1 (P0)** Download any version as `.sla` and proof PNG.
- **EXP-2 (P1)** Download packaged PDF/X per format.
- **EXP-3 (P1)** Round-trip: upload a hand-finished `.sla` against a concept as a new locked version (flagged `hand_finished`; no further LLM mutation permitted on that branch).
- **EXP-4 (P2)** IDML download (via RND-7).

### 7.10 Production handoff (PRD)

- **PRD-1 (P1)** Release action packages PDF/X for all signed-off formats and posts to n8n webhook.
- **PRD-2 (P1)** n8n flow: PitStop Server preflight → on pass, drop to Phoenix hot folder + update Monday.com item (files, proofs, approval record) → on fail, return preflight report to ide8.flow as a blocking issue.
- **PRD-3 (P1)** Release manifest: formats, file hashes, approval references — stored and attached to Monday.com.
- **PRD-4 (P2)** BOM hook: structural components (plain CAD parts) referenced from the brief flow through to the production BOM (LetsMakeVM/Monday.com pattern).

### 7.11 Admin & observability (ADM)

- **ADM-1 (P0)** Per-project and global dashboards: generation counts, token spend, render latency, validation failure rates by rule.
- **ADM-2 (P0)** Structured logging with trace IDs across gateway → worker → render service.
- **ADM-3 (P1)** Cost guardrails: per-project token budget with soft warning and hard cap.
- **ADM-4 (P1)** Prompt pack management UI (versioned, diffable, promotable).

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Proof render < 2 s p95; brief → 6 validated concepts < 5 min p95; mutation round trip < 60 s p95 |
| Availability | 99.5% business hours (internal tool tier); render service stateless, ≥ 2 replicas |
| Security | RLS on all project data; client reviewers see only invited projects; secrets in Azure Key Vault; no client data in LLM training (API ZDR posture documented) |
| Prompt-injection | Client-authored text (comments, uploaded docs) is never executed as instructions; promotion to mutation requires internal user action (GEN-9) |
| Reproducibility | Any version re-renders byte-comparably from stored document + pinned compiler + pinned render image + brand profile version. **Stored documents are never migrated:** each `doc_version` records its document-schema version and replays through the matching pinned compiler and render image (same pattern as donor pinning) |
| Font licensing | Only fonts licensed for server use baked into render image; per-brand font manifest maintained |
| Data retention | Project data retained 7 years (approval audit); proofs/intermediates pruneable |
| Cost | Target < £2 LLM spend per brief at MVP defaults; metered per ADM-1/3 |

## 9. Architecture & stack

```
React (Vite, Tailwind) — ide8.flow UI ── Liveblocks (presence/comments)
        │  Vercel (P1) → Azure Static Web Apps + Entra (P2)
        ▼
FastAPI gateway (Docker) ───────── Supabase: Postgres (RLS) + Storage + Auth(clients)
        │ Postgres-backed job queue
        ▼
Generation worker (Python, Claude API, tool-use loop)
        │ validated document JSON
        ▼
Render service (Docker: Scribus 1.6 + xvfb + poppler + fonts; FastAPI)
        │ SLA / PNG / PDF-X → Supabase Storage
        ▼
n8n (self-hosted) ──▶ PitStop Server ──▶ Phoenix hot folder
        └──▶ Monday.com (briefs, status, release manifests)
```

Stack choices follow the established house pattern: FastAPI microservices in Docker, self-hosted n8n as integration glue, Supabase for data, Monday.com as the project backbone, Azure as the deployment target (Container Apps for services; Entra for internal auth). New third-party additions are limited to Liveblocks (review realtime) and the Claude API.

## 10. Data model (core entities)

`brand_profile` (versioned JSON, immutable-once-used) · `project` (brief metadata, brand_profile_version, status) · `format` (per-project output spec, master flag) · `concept` (project-scoped, discard flag) · `doc_version` (concept-scoped, immutable: document JSON, document-schema version, parent_version, provenance — model, prompt_pack, validation_report, proof_path, hand_finished flag) · `comment` (anchored to concept/version/region; author role) · `approval` (version hash, approver, timestamp) · `release` (manifest, preflight result, monday_item) · `prompt_pack` (versioned) · `usage_event` (tokens, renders, cost).

## 11. Milestones

| Milestone | Contents | Exit criteria |
|---|---|---|
| **M0 — Render service** (wks 1–2) | RND-1..4, RND-8; compiler hardening (incl. byte-stable compilation); spot-colour fix; golden-file CI | example.json → PDF/X with `/Separation /CutContour` (named, per RND-3), passing PitStop preflight; recompiling example.json is byte-identical (golden-file CI green) |
| **M1 — Generation loop** (wks 3–5) | GEN-1..7, VAL-1..4, VAL-6..7, BRAND-1..2, ADM-1..2 | Brief JSON → 6 validated concepts with self-critique loop, fully via API |
| **M2 — Internal MVP UI** (wks 6–9) | AUTH-1/3, BRF-1..2, REV-1..3, EXP-1, BRAND-3 | Alex's team runs a real brief end-to-end internally |
| **M3 — Client review + handoff** (wks 10–14) | AUTH-2/4, REV-5..7/9, VAR-1..2, EXP-2..3, PRD-1..3, BRF-4 | A live client review and a released job through PitStop/Phoenix |
| **M4 — Scale & craft** (ongoing) | Phase 3 items by demand | — |

Build sequence within each milestone follows atomic decomposition; requirement IDs above map 1:1 to task manifests.

## 12. Risks & open questions

| Risk | Mitigation |
|---|---|
| **Spot separation in PDF export** (verified spike issue: exported PDF contains only `/Separation /All` from crop marks; CutContour converted to process) | M0 blocking task; investigate Scribus CMS prefs (`prefs160.xml`) and export options; acceptance = `/Separation /CutContour` (named) in decompressed PDF — see RND-3 false-pass note. Fallback: post-process spot recolouring via PitStop action list (already licensed) |
| SLA format drift across Scribus versions | Version pinned via Docker image; donor template + PTYPE defaults regenerated in image build; golden-file CI |
| Render latency blows the 2 s proof budget | Warm long-lived Scribus renderer processes per container (RND-4); startup cost paid once per replica, not per request |
| LLM layout quality below studio bar | Few-shot exemplar library curated from real Dimension work; designer-in-the-loop positioning; fan-out volume compensates |
| Designer adoption / perceived threat | Frame as fan-out + grunt-work tool with explicit craft-pass escape hatch (EXP-3); pilot with Alex's team and iterate on their feedback |
| Font server-use licensing | Audit per brand before profile activation; manifest per render image |
| Client IP / AI-generated work provenance | Provenance recorded per version; client contracts reviewed for AI-assisted deliverable language (open question for commercial) |
| Token cost runaway | Iteration caps, model routing, ADM-3 budgets, deterministic pre-render validation (VAL-1..4, VAL-6) before vision calls |
| Prompt injection via client comments/uploads | GEN-9 human-promotion boundary; client text always data, never instruction |
| Liveblocks dependency for client-facing reviews | Acceptable for v1; comments persisted to Postgres so realtime layer is replaceable |

**Open questions:** approval gate semantics (single approver vs quorum per client?) · where the craft pass most often happens (Scribus vs IDML/InDesign — affects RND-7 priority) · whether LetsMakeVM 3D renders feed briefs as references (likely yes — convergence point) · commercial model if offered client-direct vs internal-only tooling.

## 13. Appendices

### 13.1 Proven spike (11 Jun 2026)
JSON document → Python compiler (stdlib-only, donor-template architecture) → valid Scribus 1.6 SLA → headless load (all objects on correct pages, styles cascading, spot flag round-tripping) → PDF export with bleed/crop marks → raster proof. Visual self-critique loop demonstrated live (FCOLOR/SCOLOR fix; contrast fix caught from rendered proof). Artefacts (spike folder): `sla_compiler.py`, `template.sla`, `example.json`, `README.md` (spike usage + compiler notes), `out.sla`, `out.pdf`. The schema reference formerly in the spike README now lives at `docs/SCHEMA.md`.

### 13.2 Document-schema spec
`docs/SCHEMA.md` (reference v0.1) is the normative spec for the document schema and authoring rules; it graduates to a formal JSON Schema file in M1 (VAL-1). Stored documents pin the schema version they were authored against (§8, §10).

### 13.3 Version history
| Version | Date | Changes |
|---|---|---|
| 0.1 | 11 Jun 2026 | Initial draft (archived at `docs/archive/ide8flow-PRD-v0.1.md`) |
| 0.2 | 11 Jun 2026 | See **Changes in v0.2** at top |
