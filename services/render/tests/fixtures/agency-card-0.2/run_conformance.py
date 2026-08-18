#!/usr/bin/env python3
"""Pinned-renderer repeatability gate for the synthetic agency card.

Requires the compose `render` service. It intentionally compares proofs, not
PDF bytes: PDF producer metadata may vary while its required semantics must not.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = ROOT.parents[1]
sys.path.insert(0, str(TESTS))
from check_separation import separations  # noqa: E402

URL = os.environ.get("RENDER_URL", "http://localhost:8127").rstrip("/")
DPI = 72
# PDF proof includes the 3mm document bleed: 425.19685 + 2*8.503937 points.
EXPECTED_PROOF_SIZE = (443, 443)


def request(path, *, body=None, content_type="application/json"):
    req = urllib.request.Request(URL + path, data=body, method="POST")
    if body is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} failed ({exc.code}): {exc.read().decode()}") from exc


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("proof is not a PNG")
    return tuple(int.from_bytes(data[i:i + 4], "big") for i in (16, 20))


def compile_document(document, image_meta):
    body = json.dumps({"document": document, "image_meta": image_meta}).encode()
    return request("/compile", body=body)


def render_payload(sla, assets):
    return json.dumps({
        "sla_b64": base64.b64encode(sla).decode(),
        "assets": {name: base64.b64encode(data).decode() for name, data in assets.items()},
    }).encode()


def check_pdf(data, label):
    path = ROOT / f"{label}.pdf"
    path.write_bytes(data)
    if "CutContour" not in separations(path):
        raise AssertionError(f"{label} lacks named CutContour separation")
    for marker in (b"/OutputIntent", b"GTS_PDFXVersion", b"/FontFile"):
        if marker not in data:
            raise AssertionError(f"{label} lacks required PDF semantic {marker!r}")


def main():
    document = json.loads((ROOT / "document.json").read_text())
    image = ROOT / "synthetic-model-cutout.png"
    if not image.exists():
        raise RuntimeError("missing synthetic-model-cutout.png; run make_asset.py")
    asset_path = "assets/synthetic-model-cutout.png"
    assets = {asset_path: image.read_bytes()}
    metadata = {asset_path: {"width": 400, "height": 600}}

    proofs, packages = [], []
    for run in (1, 2):
        sla = compile_document(document, metadata)
        payload = render_payload(sla, assets)
        proof = request("/proof?" + urllib.parse.urlencode(
            {"dpi": DPI, "page": 1, "meta": "true"}), body=payload)
        report = json.loads(proof)
        png = base64.b64decode(report["png_b64"])
        if report.get("overflows"):
            raise AssertionError(f"run {run} text overflow: {report['overflows']}")
        if png_size(png) != EXPECTED_PROOF_SIZE:
            raise AssertionError(
                f"run {run} proof size {png_size(png)} != {EXPECTED_PROOF_SIZE}")
        proofs.append(png)
        package = request("/package", body=payload)
        check_pdf(package, f"package-{run}")
        packages.append(package)

    if proofs[0] != proofs[1]:
        raise AssertionError("proof PNG bytes differ across identical runs")
    (ROOT / "proof-synthetic.png").write_bytes(proofs[0])
    print("ok: repeated synthetic proof/package conformance passed")
    print(f"proof: proof-synthetic.png ({EXPECTED_PROOF_SIZE[0]}x{EXPECTED_PROOF_SIZE[1]}px)")


if __name__ == "__main__":
    main()
