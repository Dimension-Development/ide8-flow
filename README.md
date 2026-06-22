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

**M2 — internal MVP UI** is in progress. Shipped so far: brief intake with
async generation jobs, the proof grid and concept detail (version timeline +
NL mutation box), EXP-1 downloads, per-version cost metering, the RND-5 asset
pipeline, brand-profile admin + selection (BRAND-3), the fuller brief form
(BRAND/mandatory/format fields, BRF-1), copy-integrity + mandatory-element
validation (VAL-5), per-concept review comments (REV-3, Phase 1), and a usage
& validation dashboard (ADM-1). Still to land toward the exit criterion —
Alex's team running a real brief end-to-end internally — are auth (AUTH-1/3),
multi-format briefs (BRF-2), and the Supabase migration. See
[`docs/PRD.md`](docs/PRD.md) §11 for the milestone map.

## Layout

| Path | Contents |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements (v0.4) — the roadmap; requirement IDs map 1:1 to tasks |
| [`docs/SCHEMA.md`](docs/SCHEMA.md) | Document schema reference — the normative spec for what the LLM authors |
| [`services/render/`](services/render/) | Render engine: JSON→SLA compiler, headless-Scribus FastAPI service + Docker image, donor template (the Scribus version pin), examples, golden fixtures |
| [`services/worker/`](services/worker/) | Generation worker: validation layer, Claude tool-use loop, prompt packs, immutable version store, API |
| [`services/ui/`](services/ui/) | Review UI (M2): proof grid, concept detail with version timeline + mutation box (React/Vite/Tailwind) |

`services/render`, `services/worker`, and `services/ui` are all live; new
services get sibling slots under `services/` as later milestones (M3 — client
review + handoff) land.
