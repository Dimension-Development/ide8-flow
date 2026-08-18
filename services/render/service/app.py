"""ide8.flow render service (PRD RND-1).

Endpoints:
    POST /compile   document JSON → SLA (or 422 {ok, errors} for repair loops)
    POST /proof     SLA bytes → PNG raster (query: dpi, page)
    POST /package   SLA bytes → print PDF (PDF/X target — see RND-3 status)
    GET  /fonts     fonts visible to the render host
    GET  /healthz   liveness + scribus presence

Per-request temp dirs, no shared state (RND-8). Scribus runs headless under
xvfb; warm-process pooling (RND-4) is a follow-up — the skeleton spawns per
request, which is correct first and fast second.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

RENDER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RENDER_ROOT))

from sla_compiler import CompileError, DonorError, compile_to_bytes  # noqa: E402

TEMPLATE = os.environ.get("SLA_TEMPLATE", str(RENDER_ROOT / "template.sla"))
SCRIBUS = os.environ.get("SCRIBUS_BIN", "scribus")
EXPORT_SCRIPT = Path(__file__).parent / "scribus_scripts" / "export_pdf.py"
SCRIBUS_TIMEOUT = int(os.environ.get("SCRIBUS_TIMEOUT", "180"))

app = FastAPI(title="ide8.flow render service", version="0.1.0")


@app.get("/healthz")
def healthz():
    return {"ok": True, "scribus": shutil.which(SCRIBUS) is not None}


@app.get("/fonts")
def fonts():
    res = subprocess.run(
        ["fc-list", "--format", "%{family[0]} %{style[0]}\n"],
        capture_output=True, text=True)
    return {"fonts": sorted(set(filter(None, res.stdout.splitlines())))}


@app.post("/compile")
def compile_document(payload: dict = Body(...)):
    # Plain document bodies remain the original API.  The worker supplies an
    # envelope only when it has trusted asset dimensions for deterministic
    # 0.2 contain/cover placement.
    if "document" in payload:
        document = payload["document"]
        image_meta = payload.get("image_meta")
    else:
        document = payload
        image_meta = None
    if not isinstance(document, dict):
        raise HTTPException(status_code=400, detail="document must be an object")
    try:
        data = compile_to_bytes(document, TEMPLATE, image_meta=image_meta)
    except CompileError as e:
        return JSONResponse(status_code=422, content={"ok": False, "errors": e.errors})
    except DonorError as e:
        raise HTTPException(status_code=500, detail=f"donor template: {e}")
    return Response(content=data, media_type="application/vnd.scribus.sla+xml")


def _export_pdf(sla_bytes: bytes, kind: str, workdir: Path) -> Path:
    """Run headless Scribus on the SLA, return the exported PDF path."""
    sla = workdir / "doc.sla"
    pdf = workdir / "out.pdf"
    sla.write_bytes(sla_bytes)
    cmd = [SCRIBUS, "-g", "-ns", "-py", str(EXPORT_SCRIPT),
           str(sla), str(pdf), kind]
    if shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    res = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=SCRIBUS_TIMEOUT, cwd=workdir)
    if not pdf.exists():
        raise HTTPException(status_code=500, detail={
            "stage": "scribus-export",
            "returncode": res.returncode,
            "stdout": res.stdout[-2000:],
            "stderr": res.stderr[-2000:],
        })
    return pdf


def _overflows(pdf: Path):
    """VAL-6 report written by export_pdf.py next to the PDF."""
    report = Path(str(pdf) + ".report.json")
    if not report.exists():
        return []
    return json.loads(report.read_text()).get("overflows", [])


async def _read_render_request(request: Request):
    """Raw SLA bytes, or the RND-5 JSON envelope {sla_b64, assets} — assets
    are staged into the per-request workdir so relative PFILE paths in the
    SLA resolve against the document location."""
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        if "sla_b64" not in body:
            raise HTTPException(status_code=400, detail="missing sla_b64")
        sla = base64.b64decode(body["sla_b64"])
        assets = {rel: base64.b64decode(b64)
                  for rel, b64 in (body.get("assets") or {}).items()}
        return sla, assets
    return await request.body(), {}


def _stage_assets(workdir: Path, assets):
    root = workdir.resolve()
    for rel, data in assets.items():
        target = (workdir / rel).resolve()
        if root != target and root not in target.parents:
            raise HTTPException(status_code=400,
                                detail=f"bad asset path {rel!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


@app.post("/proof")
async def proof(request: Request,
                dpi: int = Query(150, ge=36, le=600),
                page: int = Query(1, ge=1),
                meta: bool = Query(False)):
    sla_bytes, assets = await _read_render_request(request)
    if not sla_bytes:
        raise HTTPException(status_code=400, detail="body must be SLA bytes")
    with tempfile.TemporaryDirectory(prefix="rnd-proof-") as td:
        workdir = Path(td)
        _stage_assets(workdir, assets)
        pdf = _export_pdf(sla_bytes, "proof", workdir)
        png = workdir / "proof.png"
        res = subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page),
             "-l", str(page), "-singlefile", str(pdf),
             str(workdir / "proof")],
            capture_output=True, text=True)
        if not png.exists():
            raise HTTPException(status_code=500, detail={
                "stage": "pdftoppm", "stderr": res.stderr[-2000:]})
        overflows = _overflows(pdf)
        if meta:
            return JSONResponse(content={
                "png_b64": base64.b64encode(png.read_bytes()).decode(),
                "overflows": overflows,
                "dpi": dpi,
                "page": page,
            })
        return Response(content=png.read_bytes(), media_type="image/png",
                        headers={"X-Overflow-Count": str(len(overflows))})


@app.post("/package")
async def package(request: Request):
    sla_bytes, assets = await _read_render_request(request)
    if not sla_bytes:
        raise HTTPException(status_code=400, detail="body must be SLA bytes")
    with tempfile.TemporaryDirectory(prefix="rnd-pkg-") as td:
        workdir = Path(td)
        _stage_assets(workdir, assets)
        pdf = _export_pdf(sla_bytes, "package", workdir)
        return Response(content=pdf.read_bytes(), media_type="application/pdf")
