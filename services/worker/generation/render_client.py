"""HTTP client for the render service (PRD RND-1 endpoints)."""

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

    def compile(self, document):
        """document JSON -> SLA bytes. Raises CompileRejected on 422."""
        resp = self._http.post("/compile", json=document)
        if resp.status_code == 422:
            raise CompileRejected(resp.json().get("errors", []))
        resp.raise_for_status()
        return resp.content

    def proof_meta(self, sla_bytes, dpi=150, page=1):
        """SLA bytes -> (png_b64, overflows) via /proof?meta=1 (VAL-6)."""
        resp = self._http.post(
            "/proof", params={"dpi": dpi, "page": page, "meta": "1"},
            content=sla_bytes)
        resp.raise_for_status()
        body = resp.json()
        return body["png_b64"], body.get("overflows", [])

    def package(self, sla_bytes):
        """SLA bytes -> PDF/X bytes."""
        resp = self._http.post("/package", content=sla_bytes)
        resp.raise_for_status()
        return resp.content
