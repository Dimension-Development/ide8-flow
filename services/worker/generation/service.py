"""Fan-out orchestration + persistence (GEN-2 + GEN-6) — shared by the CLI
and the worker API so there is exactly one code path from brief to stored
versions."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from generation.loop import generate_concept  # noqa: E402
from generation.mutation import mutate_document  # noqa: E402
from provenance import profile_for_version  # noqa: E402

def _asset_map(store, profile=None, brief=None):
    """Only the brand's assigned and brief-selected assets reach the model.

    Legacy brands with no assignment retain their existing library. Historical
    export paths do not use this filter and still resolve immutable assets.
    """
    allowed = None
    if profile is not None:
        membership = store.get_brand_assets(profile.get('name'))
        if membership['assigned']:
            allowed = set(membership['names'])
    selected = ((brief or {}).get('references') or {}).get('imageAssets')
    if isinstance(selected, list):
        allowed = set(selected) if allowed is None else allowed & set(selected)
    return {meta["name"]: store.get_asset(meta["name"])
            for meta in store.list_assets()
            if allowed is None or meta['name'] in allowed}


def _failure_record(result):
    """Why a run produced no storable document (ADM-2 first slice) — from
    the loop's last-known state. Persisted on the concept so the grid can
    show a reason instead of a bare "no proof"."""
    reason = result.error
    if reason is None:
        codes = sorted({e.get("code", "unknown") for e in
                        (result.validation or {}).get("errors", [])})
        reason = ("no valid document after %d iteration(s) — last errors: %s"
                  % (result.iterations, ", ".join(codes) or "unknown"))
    return {
        "error": reason,
        "iterations": result.iterations,
        "model_history": result.model_history,
        "validation": result.validation,
        "cost_usd": (result.usage or {}).get("cost_usd", 0.0),
        "usage": result.usage,
    }


def generate_and_store(brief, *, n, store, client, render, pack,
                       schema_json, schema_path, profile, config=None,
                       job_id=None, project_id=None, expected_version=None):
    expected_version = expected_version or pack["version"]
    archetypes = pack["archetypes"]
    assets = _asset_map(store, profile, brief)

    def run_one(i):
        archetype = archetypes[i % len(archetypes)]
        concept_id = store.create_concept(brief, archetype, job_id=job_id,
                                          project_id=project_id)
        try:
            r = generate_concept(
                brief, profile, archetype, client=client, render=render,
                pack=pack, schema_json=schema_json, schema_path=schema_path,
                config=config, assets=assets, expected_version=expected_version)
        except Exception as e:  # noqa: BLE001 — one concept must not kill the job
            error = f"{type(e).__name__}: {e}"[:500]
            store.set_concept_failure(concept_id, {
                "error": error, "iterations": 0,
                "model_history": [], "validation": None, "cost_usd": 0.0})
            return {
                "concept_id": concept_id, "version_id": None,
                "archetype": archetype, "approved": False,
                "iterations": 0, "cost_usd": 0.0,
                "error": error,
            }
        version_id = None
        if r.document is None:
            store.set_concept_failure(concept_id, _failure_record(r))
        else:
            import base64
            version_id = store.add_version(
                concept_id, r.document,
                schema_version=r.document["version"],
                prompt_pack=pack["version"],
                validation=r.validation or {},
                model_history=r.model_history,
                critique=r.critique,
                usage=r.usage,
                approved=r.approved,
                origin="generation",
                effective_profile=profile,
                proof_png=(base64.b64decode(r.proof_png_b64)
                           if r.proof_png_b64 else None))
        return {
            "concept_id": concept_id,
            "version_id": version_id,
            "archetype": archetype,
            "approved": r.approved,
            "iterations": r.iterations,
            "cost_usd": (r.usage or {}).get("cost_usd", 0.0),
            "error": r.error,
        }

    # Throttled fan-out: low usage tiers (8k OTPM) can't absorb 6-8 parallel
    # generations. 3 concurrent stays under Tier-1 limits with 8k max_tokens;
    # raise FANOUT_CONCURRENCY as the org tier grows.
    workers = max(1, min(n, int(os.environ.get("FANOUT_CONCURRENCY", "3"))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        concepts = list(pool.map(run_one, range(n)))

    return {
        "concepts": concepts,
        "approved": sum(1 for c in concepts if c["approved"]),
        "total_cost_usd": round(sum(c["cost_usd"] for c in concepts), 6),
    }


def mutate_and_store(version_id, instruction, *, store, client, render,
                     pack, schema_json, schema_path, profile, config=None,
                     expected_version=None, text_changes=None):
    """GEN-7: load version -> mutate -> persist child version. Returns
    (new_version_id, MutationResult)."""
    parent = store.get_version(version_id)
    if parent is None:
        raise KeyError(f"unknown version {version_id}")
    expected_version = expected_version or pack["version"]
    profile = profile_for_version(store, parent)
    concept = store.get_concept(parent["concept_id"])

    r = mutate_document(
        parent["document"], instruction, profile, client=client,
        render=render, pack=pack, schema_json=schema_json,
        schema_path=schema_path, config=config,
        assets=_asset_map(store, profile, (concept or {}).get('brief')), expected_version=expected_version,
        brief=(concept or {}).get("brief"), text_changes=text_changes)

    new_id = None
    if r.document is not None:
        import base64
        new_id = store.add_version(
            parent["concept_id"], r.document,
            schema_version=r.document["version"],
            prompt_pack=pack["version"],
            validation=r.validation or {},
            usage=r.usage,
            origin="mutation",
            effective_profile=profile,
            text_changes=text_changes,
            mutation_instruction=instruction,
            parent_version_id=version_id,
            proof_png=(base64.b64decode(r.proof_png_b64)
                       if r.proof_png_b64 else None))
    return new_id, r
