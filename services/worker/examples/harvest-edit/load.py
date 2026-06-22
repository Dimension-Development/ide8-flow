#!/usr/bin/env python3
"""Load the Harvest Edit fixture into a running worker and (optionally) fire a
fan-out. Exercises the full brief path: brand profile -> assets -> generate.

    # worker on :8200, render on :8127
    python3 load.py                 # brand + clean assets + 2-concept draft run
    python3 load.py --n 4 --engine standard
    python3 load.py --edge          # also try the edge-case uploads (some 415)
    python3 load.py --no-generate   # just load brand + assets

Stdlib only (urllib) so it runs anywhere the fixture does.
"""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def post(base, path, payload):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode()[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", default="http://localhost:8200")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--engine", default="draft",
                    choices=["draft", "standard", "premium"])
    ap.add_argument("--edge", action="store_true",
                    help="also attempt the edge-case uploads")
    ap.add_argument("--no-generate", action="store_true")
    args = ap.parse_args()
    base = args.worker.rstrip("/")

    brand = json.loads((HERE / "brand_profile.json").read_text())
    brief = json.loads((HERE / "brief.json").read_text())
    manifest = json.loads((HERE / "manifest.json").read_text())

    # 1) brand profile (BRAND-3) ------------------------------------------
    st, body = post(base, "/brands", brand)
    print(f"[brand]  {st}  {brand['name']}")
    if st >= 400:
        print(f"         -> {body}")

    # 2) assets (RND-5) ---------------------------------------------------
    print("\n[assets]")
    for m in manifest:
        edge = "edge-cases" in m["file"]
        if edge and not args.edge:
            continue
        path = HERE / m["file"]
        if not path.exists():  # e.g. the gitignored TIFF — run gen_assets.py
            print(f"  skip {m['name']} — missing {m['file']} "
                  f"(run gen_assets.py)")
            continue
        data = path.read_bytes()
        ext = m["file"].rsplit(".", 1)[-1]
        name = m["name"] if not edge else f"{Path(m['file']).stem}-{ext}"
        st, body = post(base, "/assets", {
            "name": name, "filename": Path(m["file"]).name,
            "data_b64": base64.b64encode(data).decode()})
        flag = "" if not edge else f"  (expected: {m['expect']})"
        note = "" if st < 400 else f"  -> {body}"
        print(f"  {st}  {name:24} {m['format']:5} {m['mode']:7}{flag}{note}")

    if args.no_generate:
        return

    # 3) generate (BRF-1 + the new gates) ---------------------------------
    st, body = post(base, "/generate",
                    {"brief": brief, "n": args.n, "engine": args.engine})
    print(f"\n[generate]  {st}")
    if st >= 400:
        print(f"  -> {body}")
        sys.exit(1)
    print(f"  job_id : {body.get('job_id')}")
    print(f"  brand  : {body.get('brand')}")
    print(f"  models : {body.get('models')}")
    print(f"\n  watch:  curl -s {base}/jobs/{body.get('job_id')} | python3 -m json.tool")


if __name__ == "__main__":
    main()
