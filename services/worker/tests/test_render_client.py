"""Render-client wire contract for transient image metadata (T04)."""

import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from generation.render_client import RenderClient  # noqa: E402


class Response:
    status_code = 200
    content = b"sla"

    def raise_for_status(self):
        pass


class Http:
    def __init__(self):
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return Response()


class TestCompilePayload(unittest.TestCase):

    def setUp(self):
        self.http = Http()
        self.client = RenderClient.__new__(RenderClient)
        self.client._http = self.http

    def test_plain_document_stays_plain_for_backward_compatibility(self):
        doc = {"version": "0.1"}
        self.assertEqual(self.client.compile(doc), b"sla")
        self.assertEqual(self.http.calls[0], ("/compile", {"json": doc}))

    def test_metadata_uses_compile_envelope(self):
        doc = {"version": "0.2"}
        meta = {"assets/hero.png": {"width": 400, "height": 200}}
        self.client.compile(doc, image_meta=meta)
        self.assertEqual(self.http.calls[0], ("/compile", {"json": {
            "document": doc, "image_meta": meta}}))


if __name__ == "__main__":
    unittest.main()
