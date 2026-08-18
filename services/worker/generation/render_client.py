"""HTTP client for the render service (PRD RND-1 endpoints).

Renders that involve image assets (RND-5) use the JSON envelope form of
/proof and /package: {sla_b64, assets: {relpath: b64}} — the render service
stages the files into the per-request workdir so relative PFILE paths in
the SLA resolve."""

import base64

import httpx


class CompileRejected(Exception):
    """The render service rejected the document (422). `errors` carries the
    structured {code, path, message} list for the repair loop."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"{len(errors)} compile error(s)")


class RenderClient:

    def __init__(self, base_url, timeout=120.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def healthz(self):
        return self._http.get("/healthz").json()

    def compile(self, document, image_meta=None):
        """document JSON -> SLA bytes. Raises CompileRejected on 422."""
        payload = (document if not image_meta else
                   {"document": document, "image_meta": image_meta})
        resp = self._http.post("/compile", json=payload)
        if resp.status_code == 422:
            raise CompileRejected(resp.json().get("errors", []))
        resp.raise_for_status()
        return resp.content

    @staticmethod
    def _payload(sla_bytes, assets):
        return {"sla_b64": base64.b64encode(sla_bytes).decode(),
                "assets": {p: base64.b64encode(d).decode()
                           for p, d in (assets or {}).items()}}

    def proof_meta(self, sla_bytes, dpi=150, page=1, assets=None):
        """SLA bytes -> (png_b64, overflows) via /proof?meta=1 (VAL-6)."""
        params = {"dpi": dpi, "page": page, "meta": "1"}
        if assets:
            resp = self._http.post("/proof", params=params,
                                   json=self._payload(sla_bytes, assets))
        else:
            resp = self._http.post("/proof", params=params,
                                   content=sla_bytes)
        resp.raise_for_status()
        body = resp.json()
        return body["png_b64"], body.get("overflows", [])

    def package(self, sla_bytes, assets=None):
        """SLA bytes -> PDF/X bytes."""
        if assets:
            resp = self._http.post("/package",
                                   json=self._payload(sla_bytes, assets))
        else:
            resp = self._http.post("/package", content=sla_bytes)
        resp.raise_for_status()
        return resp.content
