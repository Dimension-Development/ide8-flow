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
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Response

WORKER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKER_ROOT))

from brand import load_profile  # noqa: E402
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
            "client": anthropic.Anthropic(),
            "render": RenderClient(
                os.environ.get("RENDER_URL", "http://localhost:8127")),
        })
    return store, _state


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/generate")
def generate(payload: dict = Body(...)):
    brief = payload.get("brief")
    if not brief:
        raise HTTPException(400, "payload needs a 'brief' object")
    n = int(payload.get("n", 6))
    store, s = _gen_deps()
    return generate_and_store(
        brief, n=n, store=store, client=s["client"], render=s["render"],
        pack=s["pack"], schema_json=s["schema_json"],
        schema_path=SCHEMA_PATH, profile=s["profile"],
        config=GenConfig())


@app.get("/concepts")
def concepts():
    return {"concepts": _deps().list_concepts()}


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
