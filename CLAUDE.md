# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ide8.flow — AI-assisted creative-to-production platform for retail POS artwork.
A brief goes in; Claude generates layout concepts as structured JSON documents;
humans review and steer; approved concepts emit production-ready PDF/X.

The core architectural bet: **the document is data, not pixels.** Every concept
is a declarative JSON document (spec: `docs/SCHEMA.md`, normative) that compiles
deterministically to a Scribus SLA and renders headlessly. The LLM authors the
document; it never touches the renderer.

Work is PRD-driven: `docs/PRD.md` requirement IDs (RND-*, GEN-*, VAL-*, REV-*,
BRF-*, BRAND-*, AUTH-*, EXP-*, ADM-*) map 1:1 to tasks; milestones are in
PRD §11. Reference these IDs in commits and discussion. Align docs first, then
build.

## Architecture

Three services under `services/`, communicating over HTTP:

- **`services/render/`** — JSON document → Scribus `.sla` (`sla_compiler.py`,
  stdlib-only, byte-stable output) → headless Scribus 1.6.1 in Docker →
  PDF/X-4 with named spot separations, or raster proof via poppler. FastAPI:
  `/compile`, `/proof`, `/package`, `/fonts`, `/healthz`. `/proof` and
  `/package` accept a JSON envelope `{sla_b64, assets: {relpath: b64}}` for
  staged image assets (RND-5).
- **`services/worker/`** — the generation engine. `generation/loop.py` runs the
  Claude tool-use loop (emit_document → deterministic validation VAL-1..5 →
  render proof → vision self-critique → repair/revise); `service.py` is the
  single brief→store fan-out path; `store.py` is the immutable
  concept/doc_version store (SQLite `data/ide8.db`, immutability enforced by
  DB triggers — Supabase Postgres is the M2 migration boundary). FastAPI in
  `app.py`; CLI in `generate.py`. Model routing (GEN-5): sonnet fan-out,
  opus escalation after repeated failures; per-call cost metering persists
  with each version.
- **`services/ui/`** — React 19 / Vite / Tailwind 4 review UI: brief form,
  proof grid, concept detail (version timeline + NL mutation box), brands
  admin, dashboard.

Validation errors everywhere share the compiler's `{code, path, message}`
shape (GEN-3) — the repair loop depends on it.

Documents reference image assets **by name** (`"logo-primary"`), not path;
`worker/assets.py` resolves names to staged relative paths at compile time.
Assets are write-once; PNG/JPEG/TIFF only (sniffed by byte signature).

## Commands

```bash
# Render compiler tests (no Scribus/Docker needed — stdlib only)
python3 -m unittest discover services/render/tests -v

# Worker tests (no API key needed — scripted fakes)
pip install -r services/worker/requirements.txt
python3 -m unittest discover services/worker/tests -v
# single test module
python3 -m unittest tests.test_assets -v   # run from services/worker/

# UI typecheck + build (what CI runs)
cd services/ui && npm ci && npx tsc --noEmit && npm run build

# Render service image + full in-container smoke (CI render-image job)
docker build -t ide8-render services/render
docker run --rm ide8-render python3 -m unittest discover tests -v
```

Local dev stack (three processes):

```bash
docker run -d --rm -p 8127:8000 --name ide8-rnd ide8-render   # render :8127
# worker :8200 and ui :5173 are in .claude/launch.json — use the preview
# tools (preview_start {name: "worker"} / {name: "ui"}), not Bash
```

The worker needs `ANTHROPIC_API_KEY` for live generation (tests don't). It
lives in `~/.zshrc`, but sourcing the full .zshrc fails non-interactively —
load it with `eval "$(grep '^export ANTHROPIC_API_KEY=' ~/.zshrc)"`.

Key worker env vars (defaults in `app.py`): `RENDER_URL`
(http://localhost:8127), `WORKER_DB`, `PROMPT_PACK` (0.1), `BRAND_PROFILE`
(env-default fallback when a brief names no stored brand),
`FANOUT_CONCURRENCY` (3 — throttled for API Tier 1 rate limits),
`ASSET_MAX_BYTES` / `ASSET_MAX_DIM`.

## Invariants and gotchas

- **`services/render/template.sla` is the Scribus version pin** (1.6.1). Never
  author `DOCUMENT` attributes by hand — they're cloned from this donor.
  Bumping Scribus means regenerating the donor (`gen_donor.py`), re-harvesting
  per-PTYPE object defaults, and regenerating golden fixtures.
- **`tests/golden/out.sla` byte-identical recompile is a CI gate** (M0 exit
  criterion). The compiler must stay deterministic — item IDs are allocated
  sequentially from `ITEM_ID_BASE`. PDF output is NOT byte-stable; only the
  SLA is golden.
- **Store immutability is DB-trigger enforced**, not convention. Don't UPDATE
  doc_version rows; new state = new version.
- Scribus headless: `print()` inside `scribus -g -py` scripts never reaches
  stdout — write to a file. `PDFfile.outdst = 1` (printer) is required or
  spot colours silently convert to RGB. PDF/X version enums: 10 = X-4,
  11 = X-1a, 12 = X-3. `PDFfile` settings are sticky within a Scribus
  session — test export variants in fresh sessions.
- Spot-separation tests: crop marks always add `/Separation /All`, so
  asserting "a separation exists" is a false pass — assert the *named* one
  via `tests/check_separation.py`.
- Brand profiles: machine-checkable rules live in `profile.rules` (enforced by
  VAL-2..5); `profile.designPrinciples` is interpretive only (prompt +
  critique rubric, never validation). Keep that division.
- Preview-tool quirk: screenshots after programmatic scroll capture blank —
  verify via DOM snapshot (read_page) instead.

## Fixtures

`services/worker/examples/harvest-edit/` is the maximal test fixture
("Meridian Market" brand + multi-format brief + generated image assets;
`load.py` seeds a dev DB). Its human-readable brief and known-gaps register
live in `docs/briefs/harvest-edit/` (BRIEF.md, GAPS.md) — check GAPS.md
before filing something as a new gap.
