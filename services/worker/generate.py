#!/usr/bin/env python3
"""Brief -> N validated, PERSISTED concepts (PRD GEN-1/2/5/6).

    python3 generate.py examples/brief.json --n 6 \
        --render-url http://localhost:8127 [--db data/ide8.db] [--outdir out]

Requires ANTHROPIC_API_KEY and a running render service. Concepts and
immutable doc_versions land in the store (GEN-6); --outdir additionally
dumps document/proof/validation/meta files per concept for eyeballing.
"""

import argparse
import json
import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKER_ROOT))

from brand import load_profile  # noqa: E402
from generation import prompts  # noqa: E402
from generation.loop import GenConfig  # noqa: E402
from generation.render_client import RenderClient  # noqa: E402
from generation.service import generate_and_store  # noqa: E402
from schema_registry import (DOCUMENT_SCHEMA_VERSION,
                             SchemaRoutingError, load as load_schema_route)  # noqa: E402
from store import DocStore  # noqa: E402

REPO_ROOT = WORKER_ROOT.parents[1]
DEFAULT_PROFILE = WORKER_ROOT / "examples" / "brand_profile.json"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("brief")
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--db", default=str(WORKER_ROOT / "data" / "ide8.db"))
    p.add_argument("--outdir", default=None,
                   help="optionally dump per-concept artifact files")
    p.add_argument("--schema-version", default=DOCUMENT_SCHEMA_VERSION,
                   help="document schema/prompt/exemplar route (default: %(default)s)")
    p.add_argument("--pack", default=None,
                   help="explicit prompt-pack override for diagnostics")
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--schema", default=None,
                   help="explicit schema-path override for diagnostics")
    p.add_argument("--exemplar", default=None,
                   help="explicit exemplar-path override for diagnostics")
    p.add_argument("--render-url", default="http://localhost:8127")
    p.add_argument("--fast-model", default=None)
    p.add_argument("--strong-model", default=None)
    p.add_argument("--max-iterations", type=int, default=4)
    args = p.parse_args(argv)

    import anthropic  # late import: only the live path needs it

    brief = json.loads(Path(args.brief).read_text())
    profile = load_profile(args.profile)
    try:
        runtime = load_schema_route(
            args.schema_version, schema_path=args.schema, prompt_pack=args.pack,
            exemplar_path=args.exemplar)
    except SchemaRoutingError as exc:
        p.error(str(exc))

    cfg = GenConfig(max_iterations=args.max_iterations)
    if args.fast_model:
        cfg.fast_model = args.fast_model
    if args.strong_model:
        cfg.strong_model = args.strong_model

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = DocStore(args.db)
    render = RenderClient(args.render_url)
    render.healthz()  # fail fast if the render service is down

    print(f"fan-out: {args.n} concepts, schema {runtime['version']}, "
          f"pack {runtime['pack']['version']}, "
          f"fast={cfg.fast_model}, strong={cfg.strong_model}, db={args.db}")
    summary = generate_and_store(
        brief, n=args.n, store=store,
        client=anthropic.Anthropic(max_retries=6),
        render=render, pack=runtime["pack"], schema_json=runtime["schema_json"],
        schema_path=runtime["schema_path"], profile=profile, config=cfg,
        expected_version=runtime["version"])

    for i, c in enumerate(summary["concepts"], 1):
        status = "approved" if c["approved"] else (
            "ERROR: " + c["error"] if c["error"]
            else "unapproved (cap reached)")
        print(f"  concept-{i}: {status} | {c['iterations']} iteration(s) | "
              f"${c['cost_usd']:.4f} | {c['archetype']}")
        print(f"             concept={c['concept_id']} "
              f"version={c['version_id']}")
        if args.outdir and c["version_id"]:
            v = store.get_version(c["version_id"])
            cdir = Path(args.outdir) / f"concept-{i}"
            cdir.mkdir(parents=True, exist_ok=True)
            (cdir / "document.json").write_text(
                json.dumps(v["document"], indent=2))
            (cdir / "validation.json").write_text(
                json.dumps(v["validation"], indent=2))
            (cdir / "meta.json").write_text(json.dumps(
                {k: v[k] for k in ("approved", "model_history", "critique",
                                   "usage", "prompt_pack", "content_hash")},
                indent=2))
            png = store.get_proof(c["version_id"])
            if png:
                (cdir / "proof.png").write_bytes(png)

    print(f"\n{summary['approved']}/{args.n} approved, "
          f"total LLM spend ${summary['total_cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
