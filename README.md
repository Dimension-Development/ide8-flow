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

Pre-development. The render-engine architecture is proven in a spike
(PRD §13.1); next milestone is **M0 — render service** (compiler hardening,
spot-colour fix, golden-file CI).

## Layout

| Path | Contents |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements (v0.2) — the roadmap; requirement IDs map 1:1 to tasks |
| [`docs/SCHEMA.md`](docs/SCHEMA.md) | Document schema reference — the normative spec for what the LLM authors |
| [`services/render/`](services/render/) | Render engine: spike compiler, donor template (the Scribus version pin), examples, golden fixtures |

Future services (`gateway/`, `worker/`, `ui/`) get sibling slots under
`services/` as milestones land.
