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

from fastapi import Body, FastAPI, HTTPException, Response

WORKER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKER_ROOT))

import base64  # noqa: E402

from assets import SAFE_NAME, sniff  # noqa: E402
from brand import load_profile, merge_profile  # noqa: E402
from generation import prompts  # noqa: E402
from generation.loop import GenConfig  # noqa: E402
from generation.metering import assert_all_priced  # noqa: E402
from generation.render_client import RenderClient  # noqa: E402
from generation.service import generate_and_store, mutate_and_store  # noqa: E402
from store import DocStore  # noqa: E402

REPO_ROOT = WORKER_ROOT.parents[1]
SCHEMA_PATH = str(REPO_ROOT / "schema" / "document-0.1.schema.json")

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
        pack = prompts.load_pack(os.environ.get("PROMPT_PACK", "0.1"))
        pack["exemplar"] = json.loads(
            (REPO_ROOT / "services" / "render" / "examples"
             / "example.json").read_text())
        _state.update({
            "pack": pack,
            "schema_json": json.loads(Path(SCHEMA_PATH).read_text()),
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


def _run_job(job_id, brief, n, config, profile):
    store, s = _gen_deps()
    store.set_job_status(job_id, "running")
    try:
        generate_and_store(
            brief, n=n, store=store, client=s["client"], render=s["render"],
            pack=s["pack"], schema_json=s["schema_json"],
            schema_path=SCHEMA_PATH, profile=profile,
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
    profile = _resolve_profile(brief.get("brand"))
    job_id = store.create_job(brief, n)
    threading.Thread(target=_run_job, args=(job_id, brief, n, config, profile),
                     daemon=True).start()
    return {"job_id": job_id, "status": "queued", "n": n,
            "brand": profile.get("name"),
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
    sla = s["render"].compile(merge_profile(v["document"], profile))
    return Response(
        content=sla, media_type="application/vnd.scribus.sla+xml",
        headers={"Content-Disposition":
                 f'attachment; filename="ide8-{version_id[:8]}.sla"'})


@app.post("/versions/{version_id}/mutate")
def mutate(version_id: str, payload: dict = Body(...)):
    instruction = (payload.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(400, "payload needs an 'instruction' string")
    store, s = _gen_deps()
    parent = store.get_version(version_id, include_document=False)
    profile = _resolve_profile(_brand_for_version(store, parent))
    try:
        new_id, r = mutate_and_store(
            version_id, instruction, store=store, client=s["client"],
            render=s["render"], pack=s["pack"],
            schema_json=s["schema_json"], schema_path=SCHEMA_PATH,
            profile=profile)
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
