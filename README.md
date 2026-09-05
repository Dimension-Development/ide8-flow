# ide8.flow

AI-assisted creative-to-production platform for retail POS artwork. A brief
goes in; an AI ideation engine generates distinct layout concepts as
structured vector documents; humans review, comment, and steer; approved
concepts emit production-ready PDF/X — spot cut paths, bleed, crop marks —
into the Phoenix/PitStop production pipeline.

The core architectural bet: **the document is data, not pixels.** Every
concept is a declarative JSON document that compiles deterministically to a
Scribus SLA and renders headlessly. The LLM authors the document; it never
touches the renderer.

## Status

In development. **M0 — render service** and **M1 — generation loop** are
complete (both exit criteria met 11 Jun 2026): byte-identical recompile is
CI-gated and the packaged PDF/X-4 with named `/Separation /CutContour` passed
PitStop preflight first time (M0); a brief fans out to 6 validated concepts
through the full self-critique loop, entirely via API, at ~$0.26/concept with
owner sign-off (M1).

**September 2026: local studio workflow and client-review foundation.** Brands
contain campaigns and projects; each project pins an immutable brand version.
The visual identity board combines guidance, working colours/fonts, source PDFs
and assigned assets, with separate draft review/publication and a generated
`DESIGN.md`. Opus-assisted PDF extraction reads page images and text, then returns
source-linked draft findings for human review. Project artwork supports versioned
refinement, reproducible craft bundles and explicit copy/format protection.

Client review links select exact proof versions for comments, change requests
and approval, with expiry, revocation and separate decision history. A restricted
delivery server exposes only client-review routes. These flows have been tested
locally with supplied No7 assets; this does **not** complete M2/M3 launch criteria.
Public hosting, verified authentication, release/PitStop integration, multi-format
orchestration and consistently strong artwork still need work. See
[`docs/PRD.md`](docs/PRD.md) for requirements and current implementation status.

The studio API is unauthenticated and must remain private. Do not expose the
worker or development UI as a client portal. Deployment boundaries and the
separate review-server command are documented in the
[extraction and client-review guide](docs/PDF-EXTRACTION-AND-CLIENT-REVIEW-2026-09-05.md).

## Layout

| Path | Contents |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements and September implementation status |
| [`docs/SCHEMA.md`](docs/SCHEMA.md) | Document schema reference — the normative spec for what the LLM authors |
| [`services/render/`](services/render/) | Render engine: JSON→SLA compiler, headless-Scribus FastAPI service + Docker image, donor template (the Scribus version pin), examples, golden fixtures |
| [`services/worker/`](services/worker/) | Generation worker: validation layer, Claude tool-use loop, prompt packs, immutable version store, API |
| [`services/ui/`](services/ui/) | Studio, identity/extraction and client review UI (React/Vite/Tailwind) |

## Delivery notes

- [Integrity fixes and historical provenance](docs/INTEGRITY-FIXES.md)
- [Brand workspace and identity board](docs/BRAND-WORKSPACE-2026-09-05.md)
- [Automatic PDF extraction and client review](docs/PDF-EXTRACTION-AND-CLIENT-REVIEW-2026-09-05.md)
- [No7 asset preparation findings](docs/NO7-ONBOARDING-PILOT-2026-09-05.md)
- [Original delivery review](docs/PRODUCT-DELIVERY-REVIEW-2026-09-05.md) and
  [future feature proposals](docs/newFeatures/README.md)

Client source files, generated proofs, SQLite databases and local trial runners
are intentionally excluded from Git under `out/`. The repository contains the
implementation, synthetic tests and written findings, not the No7 asset pack.

Validation at this checkpoint: 280 worker tests, 42 renderer tests, TypeScript
typecheck, Vite build and local browser trials. Live tests include saved-proof
versus exported-bundle comparisons and a four-page PDF extraction check; they do
not certify a complete production preflight or general extraction accuracy.

`services/render`, `services/worker`, and `services/ui` are all live. The restricted
client-review server is a separate entry point in `services/worker/review_app.py`.
