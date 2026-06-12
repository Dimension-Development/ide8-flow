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

from fastapi import Body, FastAPI, HTTPException, Response

WORKER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKER_ROOT))

import base64  # noqa: E402

from assets import SAFE_NAME, sniff  # noqa: E402
from brand import load_profile, merge_profile  # noqa: E402
from generation import prompts  # noqa: E402
from generation.loop import GenConfig  # noqa: E402
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
            "profile": load_profile(
                os.environ.get("BRAND_PROFILE",
                               str(WORKER_ROOT / "examples"
                                   / "brand_profile.json"))),
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


def resolve_preset(name):
    if name not in MODEL_PRESETS:
        raise HTTPException(
            400, f"unknown engine preset {name!r} — one of "
                 f"{sorted(MODEL_PRESETS)}")
    fast, strong = MODEL_PRESETS[name]
    return GenConfig(fast_model=fast, strong_model=strong)


def _run_job(job_id, brief, n, config):
    store, s = _gen_deps()
    store.set_job_status(job_id, "running")
    try:
        generate_and_store(
            brief, n=n, store=store, client=s["client"], render=s["render"],
            pack=s["pack"], schema_json=s["schema_json"],
            schema_path=SCHEMA_PATH, profile=s["profile"],
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
    job_id = store.create_job(brief, n)
    threading.Thread(target=_run_job, args=(job_id, brief, n, config),
                     daemon=True).start()
    return {"job_id": job_id, "status": "queued", "n": n,
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


@app.get("/concepts")
def concepts(include_discarded: bool = False):
    store = _deps()
    return {"concepts": [
        {**c, "latest": _latest_summary(store, c["id"])}
        for c in store.list_concepts(include_discarded=include_discarded)]}


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
    sla = s["render"].compile(merge_profile(v["document"], s["profile"]))
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
    try:
        new_id, r = mutate_and_store(
            version_id, instruction, store=store, client=s["client"],
            render=s["render"], pack=s["pack"],
            schema_json=s["schema_json"], schema_path=SCHEMA_PATH,
            profile=s["profile"])
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
