#!/usr/bin/env python3
"""Brief -> N validated concepts via the generation loop (PRD GEN-1/2/5).

    python3 generate.py examples/brief.json --outdir out/ --n 6 \
        --render-url http://localhost:8127

Requires ANTHROPIC_API_KEY in the environment and a running render service.
Writes per concept: document.json, proof.png, validation.json, meta.json
(provenance: models, prompt pack, tokens, cost) — the file-based interim for
GEN-6 until the Postgres doc_version store lands.
"""

import argparse
import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKER_ROOT))

from brand import load_profile  # noqa: E402
from generation import prompts  # noqa: E402
from generation.loop import GenConfig, generate_concept  # noqa: E402
from generation.render_client import RenderClient  # noqa: E402

REPO_ROOT = WORKER_ROOT.parents[1]
DEFAULT_SCHEMA = REPO_ROOT / "schema" / "document-0.1.schema.json"
DEFAULT_PROFILE = WORKER_ROOT / "examples" / "brand_profile.json"
DEFAULT_EXEMPLAR = (REPO_ROOT / "services" / "render" / "examples"
                    / "example.json")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("brief")
    p.add_argument("--outdir", default="out")
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--pack", default="0.1")
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    p.add_argument("--render-url", default="http://localhost:8127")
    p.add_argument("--fast-model", default=None)
    p.add_argument("--strong-model", default=None)
    p.add_argument("--max-iterations", type=int, default=4)
    args = p.parse_args(argv)

    import anthropic  # late import: only the live path needs it

    brief = json.loads(Path(args.brief).read_text())
    profile = load_profile(args.profile)
    schema_json = json.loads(Path(args.schema).read_text())
    pack = prompts.load_pack(args.pack)
    pack["exemplar"] = json.loads(DEFAULT_EXEMPLAR.read_text())

    cfg = GenConfig(max_iterations=args.max_iterations)
    if args.fast_model:
        cfg.fast_model = args.fast_model
    if args.strong_model:
        cfg.strong_model = args.strong_model

    client = anthropic.Anthropic()
    render = RenderClient(args.render_url)
    render.healthz()  # fail fast if the render service is down

    archetypes = pack["archetypes"]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    def run_one(i):
        archetype = archetypes[i % len(archetypes)]
        return i, archetype, generate_concept(
            brief, profile, archetype, client=client, render=render,
            pack=pack, schema_json=schema_json, schema_path=args.schema,
            config=cfg)

    print(f"fan-out: {args.n} concepts, pack {pack['version']}, "
          f"fast={cfg.fast_model}, strong={cfg.strong_model}")
    with ThreadPoolExecutor(max_workers=args.n) as pool:
        results = list(pool.map(run_one, range(args.n)))

    total_cost = 0.0
    approved = 0
    for i, archetype, r in results:
        cdir = outdir / f"concept-{i + 1}"
        cdir.mkdir(parents=True, exist_ok=True)
        if r.document:
            (cdir / "document.json").write_text(
                json.dumps(r.document, indent=2))
        if r.proof_png_b64:
            (cdir / "proof.png").write_bytes(
                base64.b64decode(r.proof_png_b64))
        if r.validation:
            (cdir / "validation.json").write_text(
                json.dumps(r.validation, indent=2))
        meta = {
            "archetype": archetype,
            "approved": r.approved,
            "iterations": r.iterations,
            "model_history": r.model_history,
            "critique": r.critique,
            "prompt_pack": pack["version"],
            "usage": r.usage,
            "error": r.error,
        }
        (cdir / "meta.json").write_text(json.dumps(meta, indent=2))

        cost = (r.usage or {}).get("cost_usd", 0.0)
        total_cost += cost
        approved += 1 if r.approved else 0
        status = "approved" if r.approved else (
            "ERROR: " + r.error if r.error else "unapproved (cap reached)")
        print(f"  concept-{i + 1}: {status} | {r.iterations} iteration(s) | "
              f"${cost:.4f} | {archetype}")

    print(f"\n{approved}/{args.n} approved, total LLM spend ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
