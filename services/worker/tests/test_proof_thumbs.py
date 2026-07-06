"""REV-2 proof thumbnails: /versions/{id}/thumb.png serves a downscaled
proof so the grid doesn't pull ~1MP PNGs per card."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))


class TestProofThumb(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        import app as appmod
        os.environ["WORKER_DB"] = tempfile.mktemp(suffix=".db")
        appmod._state.pop("store", None)  # force the temp DB
        appmod._thumb_cache.clear()
        self.appmod = appmod
        self.client = TestClient(appmod.app)
        self.store = appmod._deps()

    def _version_with_proof(self, w, h):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (250, 250, 245)).save(buf, "PNG")
        cid = self.store.create_concept({}, "")
        return self.store.add_version(
            cid, {"version": "0.1"}, schema_version="0.1",
            prompt_pack="0.1", validation={"ok": True},
            proof_png=buf.getvalue())

    def test_thumb_is_downscaled_and_aspect_preserved(self):
        from PIL import Image
        vid = self._version_with_proof(992, 1403)  # A4 proof at 120 dpi
        r = self.client.get(f"/versions/{vid}/thumb.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        im = Image.open(io.BytesIO(r.content))
        self.assertEqual(max(im.size), self.appmod.THUMB_MAX_EDGE)
        self.assertAlmostEqual(im.size[0] / im.size[1], 992 / 1403, places=2)

    def test_small_proof_is_not_upscaled(self):
        from PIL import Image
        vid = self._version_with_proof(100, 80)
        r = self.client.get(f"/versions/{vid}/thumb.png")
        im = Image.open(io.BytesIO(r.content))
        self.assertEqual(im.size, (100, 80))

    def test_cached_second_hit_is_identical(self):
        vid = self._version_with_proof(992, 1403)
        first = self.client.get(f"/versions/{vid}/thumb.png").content
        self.assertIn(vid, self.appmod._thumb_cache)
        second = self.client.get(f"/versions/{vid}/thumb.png").content
        self.assertEqual(first, second)

    def test_missing_proof_is_404(self):
        cid = self.store.create_concept({}, "")
        vid = self.store.add_version(
            cid, {"version": "0.1"}, schema_version="0.1",
            prompt_pack="0.1", validation={"ok": False})
        self.assertEqual(
            self.client.get(f"/versions/{vid}/thumb.png").status_code, 404)
        self.assertEqual(
            self.client.get("/versions/nope/thumb.png").status_code, 404)


if __name__ == "__main__":
    unittest.main()
