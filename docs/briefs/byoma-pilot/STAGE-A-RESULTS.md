# BYOMA pilot — Stage A technical results

| | |
|---|---|
| **Status** | Complete — technical readiness proven; real-brand work remains blocked on approved design inputs |
| **Completed** | 18 August 2026 |
| **Renderer** | Pinned `ide8-render` image, Scribus 1.6.1 |
| **Scope** | Synthetic/non-brand 150 × 150 mm agency-card construction fixture |

## Result

The current ide8.flow stack can deterministically construct the technical
components requested for the pilot: gradient background, alpha-preserving
focal-cropped image, right-side copy hierarchy, 50% opaque filled vector motifs,
logo clear-space placeholder and named production spot path. This is evidence
of construction capability, not a claim of BYOMA creative quality.

## Commands and evidence

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover services/render/tests
# 40 passed

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover services/worker/tests
# 136 passed

PYTHONDONTWRITEBYTECODE=1 python3 -c 'import sys; sys.path.insert(0, "services/worker"); import schema_registry as r; assert r.DOCUMENT_SCHEMA_VERSION == "0.1"; assert r.load("0.2")["pack"]["version"] == "0.2"; print("default=0.1 explicit=0.2")'
# default=0.1 explicit=0.2

docker compose up -d render
curl --fail --silent --show-error http://localhost:8127/healthz
# {"ok":true,"scribus":true}

PYTHONDONTWRITEBYTECODE=1 python3 services/render/tests/fixtures/agency-card-0.2/run_conformance.py
# run once: passed (two identical proof/package iterations)
# run twice: passed (two identical proof/package iterations)
```

The original `0.1` golden-byte assertion and stored `0.1` mutation cases are
part of the passing suites. The explicit routing check proves that the pilot can
select `0.2` while existing installations still default to `0.1`.

The repeated pinned-renderer checks confirmed all of the following for every
package: 443 × 443px bleed-inclusive proof at 72dpi; pixel-identical repeated
proof; no text overflow; named `CutContour` separation; PDF/X marker; output
intent; and embedded font data. The human-reviewable result is
[`proof-synthetic.png`](../../../services/render/tests/fixtures/agency-card-0.2/proof-synthetic.png),
labelled in `PROOF-SYNTHETIC.md` as synthetic/non-brand.

## Known limitations and deliberate deferrals

- No real BYOMA colours, fonts, logos, copy, imagery or design rules have been
  inferred or used. Stages B/C require the approved design-team pack.
- Gradient contrast uses the conservative worst stop. A semi-transparent
  background is composited over paper white only; general backdrop/layer
  compositing is deferred.
- Gradients are limited to simple linear/radial named-swatch fills. Blend modes,
  masks, stop opacity and gradient transforms remain unsupported.
- Image placement is deterministic from trusted asset dimensions but is not a
  general image editing UI or DPI-aware artwork-management system.
- The output is a technical construction fixture. Creative authenticity and
  client-ready quality remain design-review decisions, not Stage A criteria.

## Workspace hygiene

No API keys or real client assets were created. Reproducible PDFs remain only
inside the named fixture and are ignored. `services/worker/data/ide8.db` and
its WAL/SHM files predate Stage A (16 July 2026) and were left untouched rather
than deleting existing local data.

## Decision

Keep Scribus 1.6.1 as the Stage B pilot renderer. Stage A found no technical
failure requiring a move to another renderer. Revisit that decision after the
approved BYOMA pack has been exercised and the design scorecard records actual
craft effort.
