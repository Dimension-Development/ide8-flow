"""TPL-1..3: promote-to-template, deterministic bind-and-render, batch VDP.

No LLM anywhere on this path — the fake render service is the only
double needed."""

import base64
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from templates import apply_bindings, validate_bindings  # noqa: E402

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049"
    "454e44ae426082")

DOC = {
    "version": "0.1",
    "page": {"size": "A4", "orientation": "portrait", "bleed": 3,
             "margins": [12, 12, 12, 12]},
    "swatches": [
        {"name": "DeepInk", "space": "cmyk", "values": [80, 60, 0, 70]},
        {"name": "BrandRed", "space": "cmyk", "values": [0, 90, 78, 8]},
        {"name": "Cream", "space": "cmyk", "values": [0, 4, 12, 0]},
    ],
    "charStyles": [{"name": "HChar", "font": "Liberation Sans Bold",
                    "size": 24, "color": "DeepInk"}],
    "paraStyles": [{"name": "H", "charStyle": "HChar"}],
    "pages": [{"items": [
        {"type": "text", "name": "headline", "frame": [20, 20, 400, 80],
         "fill": "Cream",
         "paragraphs": [{"style": "H", "text": "TEMPLATE HEADLINE"}]},
        {"type": "image", "name": "hero", "frame": [20, 120, 200, 150],
         "src": "hero-shot", "fit": "frame"},
        {"type": "shape", "name": "accent-band", "frame": [20, 290, 400, 40],
         "fill": "BrandRed"},
        {"type": "shape", "name": "logo-lockup", "frame": [240, 120, 180, 150],
         "fill": "Cream"},
    ]}],
}

BINDINGS = {
    "slots": {
        "headline": {"kind": "text", "item": "headline"},
        "hero": {"kind": "image", "item": "hero"},
        "band": {"kind": "swatch", "item": "accent-band", "target": "fill"},
    },
    "locked": ["logo-lockup"],
}


class TestBindingLogic(unittest.TestCase):

    def test_valid_bindings_pass(self):
        self.assertEqual(validate_bindings(DOC, BINDINGS), [])

    def test_unknown_item_kind_mismatch_and_locked_slot(self):
        bad = {"slots": {
            "a": {"kind": "text", "item": "ghost"},
            "b": {"kind": "image", "item": "headline"},
            "c": {"kind": "text", "item": "logo-lockup"},
        }, "locked": ["logo-lockup", "nope"]}
        codes = {e["code"] for e in validate_bindings(DOC, bad)}
        self.assertEqual(codes, {"slot-unknown-item", "slot-kind-mismatch",
                                 "slot-locked", "locked-unknown-item"})

    def test_text_bind_preserves_style_and_multiline(self):
        doc, errors = apply_bindings(
            DOC, BINDINGS, {"headline": "NEW LINE ONE\nLINE TWO"},
            asset_names={"hero-shot"})
        self.assertEqual(errors, [])
        paras = doc["pages"][0]["items"][0]["paragraphs"]
        self.assertEqual([p["text"] for p in paras],
                         ["NEW LINE ONE", "LINE TWO"])
        self.assertEqual({p["style"] for p in paras}, {"H"})
        # template untouched (deep copy)
        self.assertEqual(DOC["pages"][0]["items"][0]["paragraphs"][0]["text"],
                         "TEMPLATE HEADLINE")

    def test_image_bind_checks_asset_library(self):
        doc, errors = apply_bindings(DOC, BINDINGS, {"hero": "other-shot"},
                                     asset_names={"other-shot"})
        self.assertEqual(errors, [])
        self.assertEqual(doc["pages"][0]["items"][1]["src"], "other-shot")
        _, errors = apply_bindings(DOC, BINDINGS, {"hero": "ghost"},
                                   asset_names={"other-shot"})
        self.assertEqual(errors[0]["code"], "bind-unknown-asset")

    def test_swatch_bind_rebinds_fill_and_unknown_slot(self):
        doc, errors = apply_bindings(DOC, BINDINGS, {"band": "DeepInk"},
                                     asset_names=set())
        self.assertEqual(errors, [])
        self.assertEqual(doc["pages"][0]["items"][2]["fill"], "DeepInk")
        _, errors = apply_bindings(DOC, BINDINGS, {"band": "NotASwatch"},
                                   asset_names=set())
        self.assertEqual(errors[0]["code"], "bind-unknown-swatch")
        _, errors = apply_bindings(DOC, BINDINGS, {"ghost": "x"},
                                   asset_names=set())
        self.assertEqual(errors[0]["code"], "unknown-slot")


class FakeRender:
    """Render double: flags documents whose headline contains OVERFLOW."""

    def compile(self, document):
        return json.dumps(document).encode()

    def proof_meta(self, sla_bytes, dpi=150, page=1, assets=None):
        overflows = ([{"item": "headline"}]
                     if b"OVERFLOW" in sla_bytes else [])
        return base64.b64encode(PNG_1PX).decode(), overflows

    def package(self, sla_bytes, assets=None):
        return b"%PDF-fake"


class TestTemplateEndpoints(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        import app as appmod
        os.environ["WORKER_DB"] = tempfile.mktemp(suffix=".db")
        appmod._state.clear()
        appmod._state.update({
            "pack": {}, "schema_json": {}, "client": None,
            "render": FakeRender(),
        })
        self.client = TestClient(appmod.app)
        self.store = appmod._deps()
        self.store.add_asset("hero-shot", "hero.png", "image/png",
                             1, 1, PNG_1PX)
        self.store.add_asset("alt-shot", "alt.png", "image/png",
                             1, 1, PNG_1PX)
        cid = self.store.create_concept({"brand": None}, "")
        self.vid = self.store.add_version(
            cid, DOC, schema_version="0.1", prompt_pack="0.1",
            validation={"ok": True})

    def _promote(self, name="price-card"):
        r = self.client.post(f"/versions/{self.vid}/promote",
                             json={"name": name, "bindings": BINDINGS})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["template_id"]

    def _run(self, tid, rows, package=True):
        r = self.client.post(f"/templates/{tid}/run",
                             json={"rows": rows, "package": package})
        self.assertEqual(r.status_code, 200, r.text)
        run_id = r.json()["run_id"]
        for _ in range(100):
            j = self.client.get(f"/template-runs/{run_id}").json()
            if j["status"] in ("done", "failed"):
                return j
            time.sleep(0.05)
        self.fail("run never reached a terminal state")

    def test_promote_and_fetch(self):
        tid = self._promote()
        t = self.client.get(f"/templates/{tid}").json()
        self.assertEqual(t["name"], "price-card")
        self.assertEqual(sorted(t["bindings"]["slots"]),
                         ["band", "headline", "hero"])
        listed = self.client.get("/templates").json()["templates"]
        self.assertEqual(listed[0]["slots"], ["band", "headline", "hero"])

    def test_promote_rejects_bad_bindings_and_duplicate_names(self):
        r = self.client.post(
            f"/versions/{self.vid}/promote",
            json={"name": "x", "bindings":
                  {"slots": {"a": {"kind": "text", "item": "ghost"}}}})
        self.assertEqual(r.status_code, 422)
        self._promote("dupe")
        r = self.client.post(f"/versions/{self.vid}/promote",
                             json={"name": "dupe", "bindings": BINDINGS})
        self.assertEqual(r.status_code, 409)

    def test_single_bind_and_render(self):
        tid = self._promote()
        j = self._run(tid, [{"headline": "50% OFF ALL WEEK"}])
        self.assertEqual(j["status"], "done")
        (res,) = j["results"]
        self.assertEqual(res["status"], "ok", res)
        oid = res["output_id"]
        proof = self.client.get(f"/template-outputs/{oid}/proof.png")
        self.assertEqual(proof.status_code, 200)
        self.assertEqual(proof.content, PNG_1PX)
        pdf = self.client.get(f"/template-outputs/{oid}/artwork.pdf")
        self.assertEqual(pdf.content, b"%PDF-fake")
        # the bound document was stored, not the template
        doc = self.store.get_template_output(oid)["document"]
        self.assertEqual(doc["pages"][0]["items"][0]["paragraphs"][0]["text"],
                         "50% OFF ALL WEEK")

    def test_batch_rows_isolated_failures(self):
        tid = self._promote()
        j = self._run(tid, [
            {"headline": "ROW ONE", "hero": "alt-shot"},
            {"headline": "OVERFLOW THIS FRAME"},   # FakeRender flags it
            {"hero": "ghost-asset"},               # bind error
            {"headline": "ROW FOUR"},
        ])
        statuses = [r["status"] for r in j["results"]]
        self.assertEqual(statuses, ["ok", "failed", "failed", "ok"])
        self.assertEqual(j["results"][1]["errors"][0]["code"], "overflow")
        self.assertEqual(j["results"][2]["errors"][0]["code"],
                         "bind-unknown-asset")

    def test_no_package_skips_pdf(self):
        tid = self._promote()
        j = self._run(tid, [{"headline": "PROOF ONLY"}], package=False)
        oid = j["results"][0]["output_id"]
        r = self.client.get(f"/template-outputs/{oid}/artwork.pdf")
        self.assertEqual(r.status_code, 404)

    def test_run_input_guards(self):
        tid = self._promote()
        self.assertEqual(self.client.post(
            f"/templates/{tid}/run", json={"rows": []}).status_code, 400)
        self.assertEqual(self.client.post(
            f"/templates/{tid}/run", json={"rows": "nope"}).status_code, 400)
        self.assertEqual(self.client.post(
            "/templates/ghost/run",
            json={"rows": [{}]}).status_code, 404)

    def test_template_rows_are_immutable(self):
        import sqlite3
        tid = self._promote()
        with self.assertRaises(sqlite3.IntegrityError):
            import store as storemod
            from contextlib import closing
            with closing(self.store._connect()) as db:
                db.execute("UPDATE template SET name = 'x' WHERE id = ?",
                           (tid,))


if __name__ == "__main__":
    unittest.main()
