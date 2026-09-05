"""EXP-5 craft-pass bundle: /versions/{id}/bundle.zip ships the compiled
.sla, every referenced asset at its staged relpath, a manifest with identity
+ hashes, and the profile the .sla was compiled against."""

import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049"
    "454e44ae426082")


class FakeRender:
    def compile(self, document, image_meta=None):
        # echo the staged srcs so the test can assert resolution happened
        srcs = [item.get("src") for pg in document.get("pages", [])
                for item in pg.get("items", [])
                if item.get("type") == "image"]
        return json.dumps({"fake-sla": srcs}).encode()


class TestBundle(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        import app as appmod
        os.environ["WORKER_DB"] = tempfile.mktemp(suffix=".db")
        appmod._state.clear()
        # pre-seed generation deps so _gen_deps never builds the real
        # anthropic client or render client
        appmod._state.update({
            "pack": {}, "schema_json": {}, "client": None,
            "render": FakeRender(),
        })
        self.appmod = appmod
        self.client = TestClient(appmod.app)
        self.store = appmod._deps()

    def _seed(self, with_asset=True, src="hero-shot"):
        if with_asset:
            self.store.add_asset("hero-shot", "hero.png", "image/png",
                                 1, 1, PNG_1PX)
        doc = {"version": "0.1", "pages": [{"items": [
            {"type": "image", "src": src,
             "frame": {"x": 0, "y": 0, "w": 50, "h": 50}}]}]}
        cid = self.store.create_concept({"brand": None}, "")
        vid = self.store.add_version(
            cid, doc, schema_version="0.1", prompt_pack="0.1",
            validation={"ok": True}, effective_profile=self.appmod._default_profile())
        return cid, vid

    def _zip(self, resp):
        return zipfile.ZipFile(io.BytesIO(resp.content))

    def test_bundle_contains_sla_assets_manifest_profile(self):
        cid, vid = self._seed()
        r = self.client.get(f"/versions/{vid}/bundle.zip")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/zip")
        z = self._zip(r)
        root = f"ide8-{vid[:8]}"
        names = set(z.namelist())
        self.assertIn(f"{root}/document.sla", names)
        self.assertIn(f"{root}/assets/hero-shot.png", names)
        self.assertIn(f"{root}/manifest.json", names)
        self.assertIn(f"{root}/profile.json", names)
        self.assertEqual(z.read(f"{root}/assets/hero-shot.png"), PNG_1PX)

    def test_sla_srcs_are_resolved_to_staged_relpaths(self):
        cid, vid = self._seed()
        z = self._zip(self.client.get(f"/versions/{vid}/bundle.zip"))
        sla = json.loads(z.read(f"ide8-{vid[:8]}/document.sla"))
        self.assertEqual(sla["fake-sla"], ["assets/hero-shot.png"])

    def test_manifest_identity_and_hashes(self):
        import hashlib
        cid, vid = self._seed()
        z = self._zip(self.client.get(f"/versions/{vid}/bundle.zip"))
        root = f"ide8-{vid[:8]}"
        m = json.loads(z.read(f"{root}/manifest.json"))
        self.assertEqual(m["concept_id"], cid)
        self.assertEqual(m["version_id"], vid)
        self.assertEqual(m["assets"], ["assets/hero-shot.png"])
        self.assertEqual(m["missing_assets"], [])
        self.assertEqual(
            m["sla_sha256"],
            hashlib.sha256(z.read(f"{root}/document.sla")).hexdigest())
        self.assertEqual(
            m["profile_sha256"],
            hashlib.sha256(z.read(f"{root}/profile.json")).hexdigest())

    def test_missing_asset_is_reported_not_fatal(self):
        cid, vid = self._seed(with_asset=False, src="ghost")
        r = self.client.get(f"/versions/{vid}/bundle.zip")
        self.assertEqual(r.status_code, 200)
        m = json.loads(self._zip(r).read(
            f"ide8-{vid[:8]}/manifest.json"))
        self.assertEqual(m["missing_assets"], ["ghost"])
        self.assertEqual(m["assets"], [])

    def test_unknown_version_is_404(self):
        self.assertEqual(
            self.client.get("/versions/nope/bundle.zip").status_code, 404)


if __name__ == "__main__":
    unittest.main()
