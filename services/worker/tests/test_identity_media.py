"""Brand-owned reference uploads: isolation, exact bytes and immutable metadata.

The router identifies source types by their headers; font fixtures exercise
that contract, not full font parsing or renderer installation.
"""

import base64
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

import identity_media
from store import DocStore

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


class TestIdentityMedia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = DocStore(Path(self.tmp.name) / "identity-test.db")
        for name in ("Studio A", "Studio B"):
            self.store.save_brand_profile(name, {
                "name": name, "fonts": [], "swatches": [],
            })
        app = FastAPI()
        app.include_router(identity_media.make_router(lambda: self.store))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def upload(self, data=PDF, filename="Guidelines.pdf", brand="Studio A", **extra):
        return self.client.post(f"/brands/{brand}/sources", json={
            "filename": filename,
            "data_b64": base64.b64encode(data).decode("ascii"),
            **extra,
        })

    def test_pdf_roundtrip_hash_dedup_and_original_metadata(self):
        first = self.upload(font_family="Ignore this for a PDF", mime="text/html")
        self.assertEqual(first.status_code, 200)
        record = first.json()
        self.assertEqual(record["id"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(record["filename"], "Guidelines.pdf")
        self.assertEqual(record["mime"], "application/pdf")
        self.assertIsNone(record["font_family"])
        self.assertEqual(record["size"], len(PDF))
        self.assertTrue(record["created_at"])
        second = self.upload(filename="Replacement name.pdf")
        self.assertEqual(second.json(), record)
        listing = self.client.get("/brands/Studio A/sources").json()["sources"]
        self.assertEqual(listing, [record])
        self.assertNotIn("data", listing[0])
        self.assertNotIn("data_b64", listing[0])
        downloaded = self.client.get(f'/brands/Studio A/sources/{record["id"]}')
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PDF)
        self.assertEqual(downloaded.headers["content-type"], "application/pdf")

    def test_brand_isolation_and_same_hash_with_independent_metadata(self):
        a = self.upload().json()
        self.assertEqual(self.client.get("/brands/Studio B/sources").json(), {"sources": []})
        self.assertEqual(self.client.get(f'/brands/Studio B/sources/{a["id"]}').status_code, 404)
        b = self.upload(brand="Studio B", filename="B guidelines.pdf").json()
        self.assertEqual(a["id"], b["id"])
        self.assertNotEqual(a["filename"], b["filename"])
        self.assertEqual(self.client.get("/brands/Studio A/sources").json()["sources"], [a])
        self.assertEqual(self.client.get("/brands/Studio B/sources").json()["sources"], [b])
        self.assertEqual(self.client.get(f'/brands/Studio B/sources/{b["id"]}').content, PDF)

    def test_font_headers_family_and_response_type(self):
        for header, mime, extension in (
                (b"\x00\x01\x00\x00", "font/ttf", "ttf"),
                (b"true", "font/ttf", "ttf"),
                (b"OTTO", "font/otf", "otf")):
            with self.subTest(header=header):
                data = header + b"\x00" * 12
                response = self.upload(data, f"Studio font.{extension}", font_family="Studio Display")
                self.assertEqual(response.status_code, 200)
                record = response.json()
                self.assertEqual(record["font_family"], "Studio Display")
                self.assertEqual(record["mime"], mime)
                downloaded = self.client.get(f'/brands/Studio A/sources/{record["id"]}')
                self.assertEqual(downloaded.content, data)
                self.assertEqual(downloaded.headers["content-type"], mime)
                self.assertEqual(downloaded.headers["x-content-type-options"], "nosniff")

    def test_duplicate_font_cannot_rewrite_family_or_filename(self):
        data = b"OTTO" + b"\x00" * 12
        original = self.upload(data, "Original.otf", font_family="Original family").json()
        duplicate = self.upload(data, "Renamed.otf", font_family="Different family")
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json(), original)

    def test_font_family_optional_but_invalid_values_rejected(self):
        data = b"OTTO" + b"\x01" * 12
        response = self.upload(data, "No family.otf")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["font_family"])
        for family in ("", "   ", "x" * 161, 123, ["Family"]):
            with self.subTest(family=family):
                self.assertEqual(self.upload(data, "Font.otf", font_family=family).status_code, 422)

    def test_unsupported_content_is_not_admitted_by_filename_or_mime(self):
        for data in (b"<html><script>alert(1)</script></html>", b"wOFFdata", b"\x89PNG\r\n\x1a\n", b"random"):
            with self.subTest(data=data):
                self.assertEqual(self.upload(data, "Looks like a PDF.pdf", mime="application/pdf").status_code, 422)
        self.assertEqual(self.client.get("/brands/Studio A/sources").json(), {"sources": []})

    def test_invalid_base64_is_rejected_without_persisting(self):
        for encoded in ("%%%", "not-base64", "JVBERi0=\n", "JVBERi0=💡"):
            with self.subTest(encoded=encoded):
                response = self.client.post("/brands/Studio A/sources", json={
                    "filename": "bad.pdf", "data_b64": encoded})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/brands/Studio A/sources").json(), {"sources": []})

    def test_invalid_filenames_are_rejected(self):
        for filename in (None, 123, "", "   ", "a" * 256, "bad\nname.pdf", "bad\x00name.pdf"):
            with self.subTest(filename=filename):
                self.assertEqual(self.upload(filename=filename).status_code, 422)
        self.assertEqual(self.client.get("/brands/Studio A/sources").json(), {"sources": []})

    def test_filename_path_is_reduced_to_basename(self):
        for filename in ("/private/source/Guidelines.pdf", "C:\\source\\Guidelines.pdf"):
            with self.subTest(filename=filename):
                response = self.upload(filename=filename)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["filename"], "Guidelines.pdf")

    def test_filename_without_a_real_basename_is_rejected(self):
        for filename in (".", "..", "/", "\\", "folder/..", "folder/   "):
            with self.subTest(filename=filename):
                self.assertEqual(self.upload(filename=filename).status_code, 422)

    def test_payload_limit_and_empty_source(self):
        # Exercise both encoded and decoded guards without allocating 32MB.
        with patch.object(identity_media, "MAX_BYTES", len(PDF)):
            self.assertEqual(self.upload().status_code, 200)
            self.assertEqual(self.upload(PDF + b"x").status_code, 413)
            self.assertEqual(self.upload(PDF + b"x" * 30).status_code, 413)
            self.assertEqual(self.upload(b"").status_code, 413)
        for encoded in (None, 123, ["abc"]):
            with self.subTest(encoded=encoded):
                response = self.client.post("/brands/Studio A/sources", json={
                    "filename": "bad.pdf", "data_b64": encoded})
                self.assertEqual(response.status_code, 413)
        self.assertEqual(len(self.client.get("/brands/Studio A/sources").json()["sources"]), 1)

    def test_unknown_brand_and_missing_source_return_404(self):
        self.assertEqual(self.client.get("/brands/Unknown/sources").status_code, 404)
        self.assertEqual(self.upload(brand="Unknown").status_code, 404)
        digest = hashlib.sha256(PDF).hexdigest()
        self.assertEqual(self.client.get(f"/brands/Unknown/sources/{digest}").status_code, 404)
        self.assertEqual(self.client.get(f"/brands/Studio A/sources/{digest}").status_code, 404)

    def test_download_security_headers_and_unsupported_mutations(self):
        record = self.upload().json()
        url = f'/brands/Studio A/sources/{record["id"]}'
        response = self.client.get(url)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cache-control"], "private, max-age=3600")
        self.assertEqual(response.headers["content-security-policy"], "sandbox; default-src 'none'")
        for method in ("patch", "put", "delete"):
            self.assertEqual(getattr(self.client, method)(url).status_code, 405)
        self.assertEqual(self.client.get(url).content, PDF)


if __name__ == "__main__":
    unittest.main()
