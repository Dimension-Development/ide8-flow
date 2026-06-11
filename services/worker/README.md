# generation worker — brief → validated, persisted concepts

ide8.flow's M1 generation engine (PRD GEN-1..7, VAL-1..4/6/7, BRAND-1/2).

```
brief ──▶ Claude (emit_document) ──▶ VAL-1..4 ──▶ render /compile ──▶ proof + VAL-6
              ▲                        │ errors {code, path, message}      │
              └────── repair ◀─────────┴───────── overflow ◀───────────────┤
              └────── revise ◀── vision self-critique (submit_critique) ◀──┘
                                        │ approve
                                        ▼
                       immutable doc_version (provenance + proof + hash)
```

## Layout

- `validation/` — deterministic gates: formal-schema check (VAL-1), brand
  conformance (VAL-2), geometry (VAL-3), contrast (VAL-4). All errors share
  the compiler's `{code, path, message}` shape (GEN-3).
- `brand.py` — brand profile load + authoritative merge (BRAND-1/2).
- `generation/loop.py` — the GEN-1 tool-use loop; `mutation.py` — GEN-7
  (no vision pass: the designer judges the before/after proofs);
  `service.py` — fan-out + persistence, the single brief→store path;
  `prompts.py` — GEN-4 pack assembly (stable, cacheable system prefix);
  `metering.py` — token/cost accounting; `render_client.py` — RND-1 HTTP.
- `prompt_packs/<version>/` — versioned system prompt + fan-out archetypes.
- `store.py` — GEN-6/VAL-7: immutable `concept`/`doc_version` store with
  provenance, proof rasters and content hashes. SQLite for M1; the schema
  mirrors PRD §10 so the M2 move to Supabase Postgres is a driver swap.
  Immutability is enforced by DB triggers, not convention.
- `app.py` — worker API: `POST /generate`, `GET /concepts[/{id}]`,
  `GET /versions/{id}[/proof.png]`, `POST /versions/{id}/mutate`.
- `generate.py` — CLI over the same service path.

## Model routing (GEN-5)

`claude-sonnet-4-6` for fan-out and mutations; escalation to
`claude-opus-4-8` after repeated validation failures or rejected
self-critiques (mutations escalate on first failure). Per-call token and
cost metering persists with each version. Measured live (11 Jun 2026):
~£0.20–0.35 per concept at iteration cap 4 — comfortably inside the
£2/brief NFR.

## Run

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...                # never commit this

# render service must be up (see services/render/README.md)
docker run -d --rm -p 8127:8000 ide8-render

# CLI
python3 generate.py examples/brief.json --n 6 --outdir out/

# API
uvicorn app:app --port 8200
curl -X POST localhost:8200/generate -H 'content-type: application/json' \
     -d "{\"brief\": $(cat examples/brief.json), \"n\": 6}"
curl -X POST localhost:8200/versions/<id>/mutate \
     -H 'content-type: application/json' \
     -d '{"instruction": "Make the headline band DeepInk with Cream type"}'

# tests (no API key needed — scripted fakes)
python3 -m unittest discover tests
```

## Known M1 boundaries

- `POST /generate` is synchronous (minutes). The Postgres job queue +
  gateway arrive in M2 (PRD §9).
- Store is SQLite (`data/ide8.db`, gitignored); Supabase Postgres + RLS in
  M2. The DAO surface is the migration boundary.
- Mutation instructions are interpreted by the model — ambiguous wording
  yields defensible-but-unexpected readings. The before/after proof pair
  plus the structural diff is the designer's safety net; instruction
  authoring guidance belongs in the M2 review UI.
