"""ide8.flow generation worker API (M1: GEN-1..7, VAL-7 — internal only).

    uvicorn app:app --port 8200    (from services/worker)

Env: ANTHROPIC_API_KEY (required for /generate and /mutate),
     RENDER_URL (default http://localhost:8127),
     WORKER_DB (default data/ide8.db).

POST /generate runs synchronously — minutes for a full fan-out. Acceptable
for the M1 internal API; the Postgres-backed job queue arrives with the
gateway in M2 (PRD §9).
"""

import json
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Request, Response

WORKER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKER_ROOT))

import base64  # noqa: E402

from assets import SAFE_NAME, resolve_srcs, sniff  # noqa: E402
from brand import load_profile, merge_profile  # noqa: E402
from generation.loop import GenConfig  # noqa: E402
from generation.metering import assert_all_priced  # noqa: E402
from generation.render_client import RenderClient  # noqa: E402
from generation.service import generate_and_store, mutate_and_store  # noqa: E402
from schema_registry import (DOCUMENT_SCHEMA_VERSION, load as load_schema_route,
                             route as schema_route)  # noqa: E402
from store import DocStore  # noqa: E402
from templates import apply_bindings, validate_bindings  # noqa: E402
from validation import run_validation  # noqa: E402

REPO_ROOT = WORKER_ROOT.parents[1]
# Compatibility import for internal diagnostics; live work always resolves a
# complete route through schema_registry below.
SCHEMA_PATH = str(schema_route(DOCUMENT_SCHEMA_VERSION)["schema_path"])

app = FastAPI(title="ide8.flow generation worker", version="0.1.0")

_state = {}


def _deps():
    """Lazy singletons so read-only endpoints work without an API key."""
    if "store" not in _state:
        db_path = Path(os.environ.get("WORKER_DB",
                                      str(WORKER_ROOT / "data" / "ide8.db")))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _state["store"] = DocStore(db_path)
    return _state["store"]


def _default_profile():
    """The env-configured fallback profile (no API key needed to load it).
    Used when a brief names no stored brand, or names one that doesn't exist."""
    if "profile" not in _state:
        _state["profile"] = load_profile(
            os.environ.get("BRAND_PROFILE",
                           str(WORKER_ROOT / "examples"
                               / "brand_profile.json")))
    return _state["profile"]


def _resolve_profile(brand_name):
    """BRAND-3: resolve the brand profile a brief should compile against.

    Prefers a profile stored under brief.brand; falls back to the env default.
    (Pinning the exact profile version a stored doc_version used is BRAND-4 —
    today mutate/.sla recompile against whatever the brand currently is.)
    """
    if brand_name:
        rec = _deps().get_brand_profile(brand_name)
        if rec is not None:
            return rec["profile"]
    return _default_profile()


def _brand_for_version(store, version):
    """The brand name recorded on a version's concept brief, if any. Used so
    mutate/.sla recompile against the same profile the concept was briefed
    with (best-effort; see BRAND-4)."""
    if not version:
        return None
    concept = store.get_concept(version["concept_id"])
    return ((concept or {}).get("brief") or {}).get("brand")


def _gen_deps():
    store = _deps()
    if "pack" not in _state:
        import anthropic
        runtime = load_schema_route(DOCUMENT_SCHEMA_VERSION)
        _state.update({
            "runtime": runtime,
            "pack": runtime["pack"],
            "schema_json": runtime["schema_json"],
            "profile": _default_profile(),
            # generous retries: 429s during fan-out bursts resolve within
            # the minute window; the SDK honours retry-after with backoff
            "client": anthropic.Anthropic(max_retries=6),
            "render": RenderClient(
                os.environ.get("RENDER_URL", "http://localhost:8127")),
        })
    return store, _state


@app.get("/healthz")
def healthz():
    return {"ok": True}


# Designer-facing presets (GEN-5: users pick quality/cost, the engine maps
# to a fast/strong routing pair). Whitelist — never feed request strings
# straight into the SDK.
MODEL_PRESETS = {
    "draft": ("claude-haiku-4-5", "claude-sonnet-4-6"),
    "standard": ("claude-sonnet-4-6", "claude-opus-4-8"),
    "premium": ("claude-opus-4-8", "claude-opus-4-8"),
}

# Fail fast on drift: every routed model must be priced in metering, else
# cost_usd would mis-bill the generation against the £2/brief NFR (GEN-5).
assert_all_priced(
    {m for pair in MODEL_PRESETS.values() for m in pair},
    context="MODEL_PRESETS")


def resolve_preset(name):
    if name not in MODEL_PRESETS:
        raise HTTPException(
            400, f"unknown engine preset {name!r} — one of "
                 f"{sorted(MODEL_PRESETS)}")
    fast, strong = MODEL_PRESETS[name]
    return GenConfig(fast_model=fast, strong_model=strong)


def _run_job(job_id, brief, n, config, profile, runtime):
    store, s = _gen_deps()
    store.set_job_status(job_id, "running")
    try:
        generate_and_store(
            brief, n=n, store=store, client=s["client"], render=s["render"],
            pack=runtime["pack"], schema_json=runtime["schema_json"],
            schema_path=runtime["schema_path"], profile=profile,
            expected_version=runtime["version"],
            config=config, job_id=job_id)
        store.set_job_status(job_id, "done", finished=True)
    except Exception as e:  # noqa: BLE001 — job must always reach a terminal state
        store.set_job_status(job_id, "failed", error=str(e)[:2000],
                             finished=True)


@app.post("/generate")
def generate(payload: dict = Body(...)):
    """Async (BRF-1 UX): returns a job id immediately; concepts and versions
    land in the store incrementally, so the grid fills as they finish."""
    brief = payload.get("brief")
    if not brief:
        raise HTTPException(400, "payload needs a 'brief' object")
    n = max(1, min(int(payload.get("n", 6)), 8))
    config = resolve_preset(payload.get("engine", "standard"))
    store, _ = _gen_deps()  # construct deps eagerly: fail in-request, not in-thread
    try:
        runtime = load_schema_route(payload.get(
            "schema_version", DOCUMENT_SCHEMA_VERSION))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    profile = _resolve_profile(brief.get("brand"))
    job_id = store.create_job(brief, n)
    threading.Thread(target=_run_job,
                     args=(job_id, brief, n, config, profile, runtime),
                     daemon=True).start()
    return {"job_id": job_id, "status": "queued", "n": n,
            "brand": profile.get("name"), "schema_version": runtime["version"],
            "models": {"fast": config.fast_model,
                       "strong": config.strong_model}}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    store = _deps()
    j = store.get_job(job_id)
    if j is None:
        raise HTTPException(404, "unknown job")
    j["concepts"] = [
        {**c, "latest": _latest_summary(store, c["id"])}
        for c in store.concepts_for_job(job_id)]
    return j


def _latest_summary(store, concept_id):
    latest = store.latest_version(concept_id)
    if latest is None:
        return None
    return {
        "id": latest["id"], "approved": latest["approved"],
        "origin": latest["origin"], "has_proof": latest["has_proof"],
        "created_at": latest["created_at"],
        "validation_ok": latest["validation"].get("ok"),
        "error_codes": sorted({e.get("code", "unknown") for e in
                               latest["validation"].get("errors", [])}),
        "warnings": len(latest["validation"].get("warnings", [])),
        "cost_usd": (latest["usage"] or {}).get("cost_usd"),
    }


# RND-5 upload guards (gap D4): keep the version-store BLOBs lean and render-
# host staging fast. Configurable; the dimension cap only applies to formats
# that expose dimensions (TIFF dims aren't sniffed — gap D2).
MAX_ASSET_BYTES = int(os.environ.get("ASSET_MAX_BYTES", 16 * 1024 * 1024))
MAX_ASSET_DIM = int(os.environ.get("ASSET_MAX_DIM", 4096))


@app.post("/assets")
def upload_asset(payload: dict = Body(...)):
    """RND-5: upload an image asset. {name, filename, data_b64}. Names are
    write-once — versions reference assets by name."""
    name = (payload.get("name") or "").strip().lower()
    if not SAFE_NAME.match(name):
        raise HTTPException(400, "name must be kebab-case: a-z, 0-9, -, _")
    try:
        data = base64.b64decode(payload["data_b64"])
    except Exception:
        raise HTTPException(400, "data_b64 missing or not valid base64")
    mime, width, height = sniff(data)
    if mime is None:
        raise HTTPException(415, "unrecognised image format — PNG, JPEG or "
                                 "TIFF only")
    if len(data) > MAX_ASSET_BYTES:
        raise HTTPException(413, f"asset is {len(data) // 1024} KB — over the "
                                 f"{MAX_ASSET_BYTES // (1024 * 1024)} MB limit")
    if width and height and max(width, height) > MAX_ASSET_DIM:
        raise HTTPException(413, f"{width}x{height}px exceeds the "
                                 f"{MAX_ASSET_DIM}px max-dimension limit")
    if not _deps().add_asset(name, payload.get("filename", name), mime,
                             width, height, data):
        raise HTTPException(409, f'asset "{name}" already exists — assets '
                                 f"are write-once; pick a new name")
    return {"name": name, "mime": mime, "width": width, "height": height,
            "size": len(data)}


@app.get("/assets")
def assets_list():
    return {"assets": _deps().list_assets()}


@app.get("/assets/{name}")
def asset_bytes(name: str):
    a = _deps().get_asset(name)
    if a is None:
        raise HTTPException(404, "unknown asset")
    return Response(content=a["data"], media_type=a["mime"])


@app.get("/brands")
def brands_list():
    """BRAND-3: profiles for the admin grid + brief picker (summaries)."""
    return {"brands": _deps().list_brand_profiles(),
            "default": _default_profile().get("name")}


@app.post("/brands")
def brand_save(payload: dict = Body(...)):
    """Create or update a brand profile. Accepts either {name, profile} or a
    bare profile object. Mutable (BRAND-4 pinning is future work)."""
    profile = payload.get("profile") if isinstance(
        payload.get("profile"), dict) else payload
    name = (payload.get("name") or profile.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "brand profile needs a 'name'")
    if not isinstance(profile.get("swatches"), list):
        raise HTTPException(400, "profile needs a 'swatches' array")
    profile = {**profile, "name": name}  # keep name canonical for lookups
    return _deps().save_brand_profile(name, profile)


@app.get("/brands/{name}")
def brand_get(name: str):
    rec = _deps().get_brand_profile(name)
    if rec is None:
        raise HTTPException(404, "unknown brand profile")
    return rec


@app.delete("/brands/{name}")
def brand_delete(name: str):
    if not _deps().delete_brand_profile(name):
        raise HTTPException(404, "unknown brand profile")
    return {"ok": True}


@app.get("/concepts")
def concepts(include_discarded: bool = False):
    store = _deps()
    return {"concepts": [
        {**c, "latest": _latest_summary(store, c["id"])}
        for c in store.list_concepts(include_discarded=include_discarded)]}


@app.get("/stats")
def stats(job_id: Optional[str] = None):
    """ADM-1 v1: usage + validation rollups, global or per-job. Read-only
    aggregation over the persisted doc_version provenance."""
    return _deps().usage_stats(job_id=job_id)


@app.post("/concepts/{concept_id}/discard")
def discard(concept_id: str):
    if not _deps().set_discarded(concept_id, True):
        raise HTTPException(404, "unknown concept")
    return {"ok": True}


@app.post("/concepts/{concept_id}/restore")
def restore(concept_id: str):
    if not _deps().set_discarded(concept_id, False):
        raise HTTPException(404, "unknown concept")
    return {"ok": True}


@app.get("/concepts/{concept_id}")
def concept(concept_id: str):
    c = _deps().get_concept(concept_id)
    if c is None:
        raise HTTPException(404, "unknown concept")
    c["versions"] = _deps().list_versions(concept_id)
    return c


# REV-3: per-concept comment threads. No identity yet (AUTH-1/3 unbuilt), so
# comments are authored as a single internal stub user until SSO lands;
# override with INTERNAL_USER. Client-authored text is data, never an
# instruction — it is stored verbatim and never fed to the model. Promoting a
# comment to a mutation is a separate, explicit internal action (the GEN-9
# prompt-injection boundary, PRD §8).
INTERNAL_USER = os.environ.get("INTERNAL_USER", "designer")


@app.get("/concepts/{concept_id}/comments")
def list_comments(concept_id: str):
    store = _deps()
    if store.get_concept(concept_id) is None:
        raise HTTPException(404, "unknown concept")
    return {"comments": store.list_comments(concept_id)}


@app.post("/concepts/{concept_id}/comments")
def add_comment(concept_id: str, payload: dict = Body(...)):
    store = _deps()
    if store.get_concept(concept_id) is None:
        raise HTTPException(404, "unknown concept")
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(400, "payload needs a non-empty 'body' string")
    version_id = payload.get("version_id")
    if version_id is not None:
        v = store.get_version(version_id, include_document=False)
        if v is None or v["concept_id"] != concept_id:
            raise HTTPException(
                400, "version_id does not belong to this concept")
    return store.add_comment(
        concept_id, body[:4000], author=INTERNAL_USER,
        version_id=version_id, anchor_name=payload.get("anchor_name"))


@app.post("/comments/{comment_id}/resolve")
def resolve_comment(comment_id: str):
    if not _deps().set_comment_resolved(comment_id, True):
        raise HTTPException(404, "unknown comment")
    return {"ok": True}


@app.post("/comments/{comment_id}/reopen")
def reopen_comment(comment_id: str):
    if not _deps().set_comment_resolved(comment_id, False):
        raise HTTPException(404, "unknown comment")
    return {"ok": True}


@app.get("/versions/{version_id}")
def version(version_id: str):
    v = _deps().get_version(version_id)
    if v is None:
        raise HTTPException(404, "unknown version")
    return v


@app.get("/versions/{version_id}/proof.png")
def proof(version_id: str):
    png = _deps().get_proof(version_id)
    if png is None:
        raise HTTPException(404, "no proof for this version")
    return Response(content=png, media_type="image/png")


# Proof thumbnails (REV-2): the grid shows 6-8 cards at ~400px; full proofs
# are ~1MP PNGs. doc_versions are immutable, so a rendered thumb never goes
# stale — cache unboundedly-ish and clear wholesale if it ever grows.
THUMB_MAX_EDGE = 512
_thumb_cache = {}


@app.get("/versions/{version_id}/thumb.png")
def thumb(version_id: str):
    png = _thumb_cache.get(version_id)
    if png is None:
        full = _deps().get_proof(version_id)
        if full is None:
            raise HTTPException(404, "no proof for this version")
        import io

        from PIL import Image
        im = Image.open(io.BytesIO(full))
        im.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE))
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        if len(_thumb_cache) >= 512:
            _thumb_cache.clear()
        png = _thumb_cache[version_id] = buf.getvalue()
    return Response(content=png, media_type="image/png")


@app.get("/versions/{version_id}/document.json")
def download_document(version_id: str):
    """EXP-1: the raw document JSON, pretty-printed for humans."""
    v = _deps().get_version(version_id)
    if v is None:
        raise HTTPException(404, "unknown version")
    return Response(
        content=json.dumps(v["document"], indent=2),
        media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename="ide8-{version_id[:8]}.json"'})


@app.get("/versions/{version_id}/document.sla")
def download_sla(version_id: str):
    """EXP-1: the escape hatch — compile this version (brand merged) to a
    Scribus .sla a designer can open and finish by hand."""
    store, s = _gen_deps()
    v = store.get_version(version_id)
    if v is None:
        raise HTTPException(404, "unknown version")
    profile = _resolve_profile(_brand_for_version(store, v))
    asset_map = {meta["name"]: store.get_asset(meta["name"])
                 for meta in store.list_assets()}
    staged, _, image_meta = resolve_srcs(
        merge_profile(v["document"], profile), asset_map)
    sla = s["render"].compile(staged, image_meta=image_meta or None)
    return Response(
        content=sla, media_type="application/vnd.scribus.sla+xml",
        headers={"Content-Disposition":
                 f'attachment; filename="ide8-{version_id[:8]}.sla"'})


@app.get("/versions/{version_id}/bundle.zip")
def download_bundle(version_id: str, request: Request):
    """EXP-5: the craft-pass bundle — everything a designer needs to open
    this version in Scribus with no missing images, plus a manifest carrying
    the identity EXP-7's return script will need.

    Layout:  ide8-<id8>/document.sla        image srcs resolved to assets/…
             ide8-<id8>/assets/<name>.<ext> every referenced asset
             ide8-<id8>/manifest.json       concept/version ids, brand, hashes
             ide8-<id8>/profile.json        the profile the .sla was compiled
                                            against (BRAND-4 note: best-effort
                                            live resolution until profile
                                            versions are pinned per version)
    """
    import hashlib
    import io as _io
    import zipfile

    store, s = _gen_deps()
    v = store.get_version(version_id)
    if v is None:
        raise HTTPException(404, "unknown version")
    profile = _resolve_profile(_brand_for_version(store, v))
    merged = merge_profile(v["document"], profile)
    asset_map = {meta["name"]: store.get_asset(meta["name"])
                 for meta in store.list_assets()}
    staged, files, image_meta = resolve_srcs(merged, asset_map)
    sla = s["render"].compile(staged, image_meta=image_meta or None)

    referenced = {item.get("src") for pg in v["document"].get("pages", [])
                  for item in pg.get("items", [])
                  if item.get("type") == "image"}
    missing = sorted(name for name in referenced
                     if name and name not in asset_map)

    profile_json = json.dumps(profile, indent=2, sort_keys=True)
    manifest = {
        "bundle": "ide8.flow craft-pass bundle (EXP-5)",
        "concept_id": v["concept_id"],
        "version_id": version_id,
        "schema_version": v.get("schema_version"),
        "created_at": v.get("created_at"),
        "brand": profile.get("name"),
        "profile_sha256": hashlib.sha256(
            profile_json.encode()).hexdigest(),
        "sla_sha256": hashlib.sha256(sla).hexdigest(),
        "assets": sorted(files),
        "missing_assets": missing,
        "worker_url": str(request.base_url).rstrip("/"),
        "return_path": f"/versions/{version_id}/handoff (EXP-3/EXP-7 — "
                       f"not yet implemented)",
    }

    root = f"ide8-{version_id[:8]}"
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{root}/document.sla", sla)
        for relpath, data in sorted(files.items()):
            z.writestr(f"{root}/{relpath}", data)
        z.writestr(f"{root}/manifest.json", json.dumps(manifest, indent=2))
        z.writestr(f"{root}/profile.json", profile_json)
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="{root}-bundle.zip"'})


@app.post("/versions/{version_id}/mutate")
def mutate(version_id: str, payload: dict = Body(...)):
    instruction = (payload.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(400, "payload needs an 'instruction' string")
    store, s = _gen_deps()
    parent = store.get_version(version_id, include_document=False)
    profile = _resolve_profile(_brand_for_version(store, parent))
    if parent is None:
        raise HTTPException(404, "unknown version")
    try:
        runtime = load_schema_route(parent["schema_version"])
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    try:
        new_id, r = mutate_and_store(
            version_id, instruction, store=store, client=s["client"],
            render=s["render"], pack=runtime["pack"],
            schema_json=runtime["schema_json"], schema_path=runtime["schema_path"],
            profile=profile, expected_version=runtime["version"])
    except KeyError:
        raise HTTPException(404, "unknown version")
    if new_id is None:
        raise HTTPException(422, detail={
            "error": r.error, "validation": r.validation})
    return {
        "version_id": new_id,
        "parent_version_id": version_id,
        "diff": r.diff,
        "iterations": r.iterations,
        "cost_usd": (r.usage or {}).get("cost_usd"),
        "before_proof": f"/versions/{version_id}/proof.png",
        "after_proof": f"/versions/{new_id}/proof.png",
    }


# ------------------------------------------------------------- templates
# TPL-1..3 (pulled forward from Phase 3): approved versions promote to
# slot-bound templates; binding + rendering is deterministic — no LLM call
# anywhere below this line.

TEMPLATE_RUN_MAX_ROWS = int(os.environ.get("TEMPLATE_RUN_MAX_ROWS", 500))


@app.post("/versions/{version_id}/promote")
def promote_to_template(version_id: str, payload: dict = Body(...)):
    """TPL-1: freeze this version's document + a bindings map as a named,
    immutable template."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "payload needs a 'name' string")
    bindings = payload.get("bindings")
    store = _deps()
    v = store.get_version(version_id)
    if v is None:
        raise HTTPException(404, "unknown version")
    errors = validate_bindings(v["document"], bindings or {})
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    brand = _brand_for_version(store, v)
    tid = store.create_template(
        name, version_id, v["document"], bindings, brand,
        v.get("schema_version") or "0.1")
    if tid is None:
        raise HTTPException(409, f'template "{name}" already exists — '
                                 f"templates are immutable; pick a new name")
    return {"template_id": tid, "name": name, "brand": brand,
            "slots": sorted((bindings or {}).get("slots", {}))}


@app.get("/templates")
def templates_list():
    return {"templates": _deps().list_templates()}


@app.get("/templates/{template_id}")
def template_detail(template_id: str):
    t = _deps().get_template(template_id)
    if t is None:
        raise HTTPException(404, "unknown template")
    return t


def _run_template_rows(run_id, template, rows, package):
    """TPL-2/3 worker: bind, validate, render each row. Row failures are
    recorded per-row and never batch-fatal."""
    store, s = _gen_deps()
    profile = _resolve_profile(template["brand"])
    try:
        runtime = load_schema_route(template["schema_version"])
    except ValueError as exc:
        store.set_template_run(run_id, "failed", error=str(exc))
        return
    asset_map = {meta["name"]: store.get_asset(meta["name"])
                 for meta in store.list_assets()}
    results = []
    store.set_template_run(run_id, "running")
    for i, values in enumerate(rows):
        try:
            doc, errors = apply_bindings(
                template["document"], template["bindings"], values,
                asset_names=set(asset_map))
            if not errors:
                report = run_validation(
                    doc, profile, runtime["schema_path"],
                    asset_names=set(asset_map))
                errors = report["errors"] if not report["ok"] else []
            if errors:
                results.append({"row": i, "status": "failed",
                                "errors": errors})
                continue
            merged = merge_profile(doc, profile)
            staged, files, image_meta = resolve_srcs(merged, asset_map)
            sla = s["render"].compile(staged, image_meta=image_meta or None)
            png_b64, overflows = s["render"].proof_meta(sla, assets=files)
            if overflows:
                results.append({"row": i, "status": "failed", "errors": [
                    {"code": "overflow", "path": o.get("item", ""),
                     "message": "bound text overflows its frame"}
                    for o in overflows]})
                continue
            pdf = s["render"].package(sla, assets=files) if package else None
            oid = store.add_template_output(
                run_id, i, doc, base64.b64decode(png_b64), pdf)
            results.append({"row": i, "status": "ok", "output_id": oid})
        except Exception as e:  # noqa: BLE001 — row isolation (TPL-3)
            results.append({"row": i, "status": "failed", "errors": [
                {"code": "render-error", "path": "", "message": str(e)[:500]}]})
        store.set_template_run(run_id, "running", results=results)
    store.set_template_run(run_id, "done", results=results, finished=True)


@app.post("/templates/{template_id}/run")
def template_run(template_id: str, payload: dict = Body(...)):
    """TPL-2/3: bind rows of values through the template and render each —
    async like /generate; poll /template-runs/{id}. One row = a single
    bind-and-render; many rows = VDP."""
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or \
            not all(isinstance(r, dict) for r in rows):
        raise HTTPException(400, "payload needs 'rows': a non-empty list "
                                 "of {slot: value} objects")
    if len(rows) > TEMPLATE_RUN_MAX_ROWS:
        raise HTTPException(413, f"{len(rows)} rows — cap is "
                                 f"{TEMPLATE_RUN_MAX_ROWS} per run")
    package = bool(payload.get("package", True))
    store, _ = _gen_deps()  # fail on missing deps in-request
    template = store.get_template(template_id)
    if template is None:
        raise HTTPException(404, "unknown template")
    run_id = store.create_template_run(template_id, rows)
    threading.Thread(
        target=_run_template_rows,
        args=(run_id, template, rows, package), daemon=True).start()
    return {"run_id": run_id, "status": "queued", "rows": len(rows),
            "package": package}


@app.get("/template-runs/{run_id}")
def template_run_status(run_id: str):
    r = _deps().get_template_run(run_id)
    if r is None:
        raise HTTPException(404, "unknown run")
    return r


@app.get("/template-outputs/{output_id}/proof.png")
def template_output_proof(output_id: str):
    o = _deps().get_template_output(output_id)
    if o is None or not o["proof_png"]:
        raise HTTPException(404, "no proof for that output")
    return Response(content=o["proof_png"], media_type="image/png")


@app.get("/template-outputs/{output_id}/artwork.pdf")
def template_output_pdf(output_id: str):
    o = _deps().get_template_output(output_id)
    if o is None or not o["pdf"]:
        raise HTTPException(404, "no PDF for that output — run with "
                                 "package: true")
    return Response(
        content=o["pdf"], media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="ide8-{output_id[:8]}.pdf"'})
