"""Brand versioning (BRAND-4), the project/campaign layer, and project
brand overrides (BRAND-6).

    python3 -m unittest discover services/worker/tests
"""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

from brand import apply_overrides, validate_overrides  # noqa: E402
from store import DocStore  # noqa: E402
from validation import brand_rules  # noqa: E402

PROFILE = WORKER_ROOT / "examples" / "harvest-edit" / "brand_profile.json"


def load_profile():
    return json.loads(PROFILE.read_text())


OVERRIDES = {
    "add": {"swatches": [{"name": "XmasFoilGold", "space": "cmyk",
                          "values": [0, 20, 60, 20], "spot": True}],
            "fonts": ["Festive Display"]},
    "rules": {"minTypeSize": {"value": 5,
                              "reason": "promo legal line at 5pt approved"
                                        " by brand owner 2026-08"}},
    "designPrinciples": ["Lean festive: gold accents, never gold fields."],
}


class TestBrandVersioning(unittest.TestCase):

    def setUp(self):
        self.db = DocStore(tempfile.mktemp(suffix=".db"))
        self.profile = load_profile()

    def test_saves_append_versions(self):
        first = self.db.save_brand_profile("Meridian Market", self.profile)
        self.assertEqual(first["version"], 1)
        second = self.db.save_brand_profile(
            "Meridian Market", {**self.profile, "version": "2026.2"})
        self.assertEqual(second["version"], 2)
        # both remain retrievable; head is the default
        self.assertEqual(
            self.db.get_brand_profile("Meridian Market")["version"], 2)
        v1 = self.db.get_brand_profile("Meridian Market", version=1)
        self.assertEqual(v1["profile"]["version"], "2026.1")
        self.assertEqual(
            [v["version"] for v in
             self.db.list_brand_versions("Meridian Market")], [1, 2])

    def test_identical_save_is_a_noop(self):
        self.db.save_brand_profile("Meridian Market", self.profile)
        again = self.db.save_brand_profile("Meridian Market", self.profile)
        self.assertEqual(again["version"], 1)
        self.assertEqual(
            len(self.db.list_brand_versions("Meridian Market")), 1)

    def test_versions_are_immutable(self):
        rec = self.db.save_brand_profile("Meridian Market", self.profile)
        db = sqlite3.connect(self.db._path)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE brand_version SET profile_json = '{}'"
                       " WHERE id = ?", (rec["id"],))
        db.close()

    def test_legacy_table_migrates_to_version_1(self):
        path = tempfile.mktemp(suffix=".db")
        db = sqlite3.connect(path)
        db.execute("""CREATE TABLE brand_profile (
            name TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')))""")
        db.execute("INSERT INTO brand_profile (name, profile_json)"
                   " VALUES (?,?)",
                   ("Meridian Market", json.dumps(self.profile)))
        db.commit()
        db.close()
        store = DocStore(path)
        rec = store.get_brand_profile("Meridian Market")
        self.assertEqual(rec["version"], 1)
        self.assertEqual(rec["profile"]["rules"]["contrastFloor"], 4.0)
        db = sqlite3.connect(path)
        self.assertIsNone(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table'"
            " AND name = 'brand_profile'").fetchone())
        db.close()

    def test_delete_blocked_while_pinned(self):
        rec = self.db.save_brand_profile("Meridian Market", self.profile)
        pid = self.db.create_project("Xmas 2026",
                                     brand_version_id=rec["id"])
        with self.assertRaises(ValueError):
            self.db.delete_brand_profile("Meridian Market")
        self.db.update_project(pid, brand_version_id=None)  # unpin
        self.assertTrue(self.db.delete_brand_profile("Meridian Market"))


class TestProjectStore(unittest.TestCase):

    def setUp(self):
        self.db = DocStore(tempfile.mktemp(suffix=".db"))
        self.brand = self.db.save_brand_profile("Meridian Market",
                                                load_profile())

    def test_create_get_update_list(self):
        pid = self.db.create_project(
            "Xmas 2026", brand_version_id=self.brand["id"],
            brief={"title": "Xmas"}, overrides=OVERRIDES)
        p = self.db.get_project(pid)
        self.assertEqual((p["brand"], p["brand_version"]),
                         ("Meridian Market", 1))
        self.assertEqual(p["brief"]["title"], "Xmas")
        self.assertEqual(p["overrides"]["rules"]["minTypeSize"]["value"], 5)
        # duplicate name refused
        self.assertIsNone(self.db.create_project("Xmas 2026", brand_version_id=self.brand['id']))
        # partial update leaves the rest alone
        self.db.update_project(pid, status="archived")
        p = self.db.get_project(pid)
        self.assertEqual(p["status"], "archived")
        self.assertEqual(p["brief"]["title"], "Xmas")
        self.assertEqual([q["id"] for q in self.db.list_projects()], [])
        self.assertEqual(
            [q["id"] for q in self.db.list_projects(include_archived=True)],
            [pid])

    def test_pin_survives_brand_edits(self):
        pid = self.db.create_project("Spring",
                                     brand_version_id=self.brand["id"])
        self.db.save_brand_profile(
            "Meridian Market", {**load_profile(), "version": "2026.2"})
        p = self.db.get_project(pid)
        self.assertEqual(p["brand_version"], 1)  # still v1
        pinned = self.db.get_brand_version(p["brand_version_id"])
        self.assertEqual(pinned["profile"]["version"], "2026.1")

    def test_concepts_jobs_and_stats_scope_to_project(self):
        pid = self.db.create_project("Spring")
        jid = self.db.create_job({"title": "b"}, 2, project_id=pid,
                                 brand={"brand": "Meridian Market"})
        cid = self.db.create_concept({"title": "b"}, "hero", job_id=jid,
                                     project_id=pid)
        self.db.create_concept({"title": "other"}, "hero")  # projectless
        self.assertEqual(self.db.get_job(jid)["project_id"], pid)
        self.assertEqual(self.db.get_job(jid)["brand"]["brand"],
                         "Meridian Market")
        self.assertEqual(
            [c["id"] for c in self.db.concepts_for_project(pid)], [cid])
        self.db.add_version(
            cid, {"version": "0.1", "pages": []}, schema_version="0.1",
            prompt_pack="0.1", validation={"ok": True, "errors": [],
                                           "warnings": []})
        stats = self.db.usage_stats(project_id=pid)
        self.assertEqual((stats["scope"], stats["concepts"],
                          stats["versions"]), ("project", 1, 1))
        self.assertEqual(self.db.usage_stats()["concepts"], 2)


class TestOverrides(unittest.TestCase):

    def setUp(self):
        self.profile = load_profile()

    def test_clean_overrides_validate_and_apply(self):
        self.assertEqual(validate_overrides(OVERRIDES, self.profile), [])
        eff = apply_overrides(self.profile, OVERRIDES)
        names = [s["name"] for s in eff["swatches"]]
        self.assertIn("XmasFoilGold", names)
        self.assertIn("HarvestPlum", names)  # brand palette intact
        self.assertIn("Festive Display", eff["fonts"])
        self.assertEqual(eff["rules"]["minTypeSize"], 5)
        self.assertEqual(eff["rules"]["contrastFloor"], 4.0)  # untouched
        self.assertIn("gold accents", eff["designPrinciples"][0])
        # the brand profile itself is never mutated
        self.assertNotIn("Festive Display", self.profile["fonts"])

    def test_none_is_a_passthrough(self):
        self.assertEqual(validate_overrides(None, self.profile), [])
        self.assertEqual(apply_overrides(self.profile, None), self.profile)

    def test_brand_names_cannot_be_redefined(self):
        bad = {"add": {"swatches": [
            {"name": "HarvestPlum", "space": "cmyk", "values": [0, 0, 0, 0]}]}}
        errs = validate_overrides(bad, self.profile)
        self.assertEqual([e["code"] for e in errs],
                         ["override-name-conflict"])

    def test_rule_override_requires_a_reason(self):
        bad = {"rules": {"minTypeSize": {"value": 5}}}
        codes = [e["code"] for e in validate_overrides(bad, self.profile)]
        self.assertEqual(codes, ["override-missing-reason"])

    def test_restrict_must_name_brand_entries(self):
        ok = {"restrict": {"fonts": ["Canela Deck Medium"]}}
        self.assertEqual(validate_overrides(ok, self.profile), [])
        eff = apply_overrides(self.profile, ok)
        self.assertEqual(eff["fonts"], ["Canela Deck Medium"])
        bad = {"restrict": {"fonts": ["Comic Sans"]}}
        codes = [e["code"] for e in validate_overrides(bad, self.profile)]
        self.assertEqual(codes, ["override-unknown-name"])

    def test_unknown_sections_are_shape_errors(self):
        bad = {"replace": {}, "add": {"rules": []}}
        codes = sorted(e["code"] for e in validate_overrides(bad,
                                                             self.profile))
        self.assertEqual(codes, ["override-shape", "override-shape"])

    def test_effective_profile_admits_added_swatch_in_validation(self):
        """The end-to-end point of BRAND-6: a document using a campaign
        swatch fails VAL-2 against the raw brand but passes against the
        effective profile."""
        doc = {"swatches": [{"name": "XmasFoilGold", "space": "cmyk",
                             "values": [0, 20, 60, 20], "spot": True}],
               "pages": []}
        raw = [e["code"] for e in brand_rules.check(doc, self.profile)]
        self.assertIn("off-brand-swatch", raw)
        eff = apply_overrides(self.profile, OVERRIDES)
        errs = brand_rules.check(doc, eff)
        self.assertEqual([e for e in errs
                          if e["code"] == "off-brand-swatch"], [])


class TestProjectApi(unittest.TestCase):
    """Project endpoints + the generate hand-off, with _run_job stubbed —
    no API key, render host, or model call anywhere."""

    class _SyncThread:
        """Runs the job launch inline so tests see it deterministically."""

        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._call = (target, args, kwargs or {})

        def start(self):
            target, args, kwargs = self._call
            target(*args, **kwargs)

    def setUp(self):
        import os
        import types
        from fastapi.testclient import TestClient
        import app as appmod
        self.app = appmod
        os.environ["WORKER_DB"] = tempfile.mktemp(suffix=".db")
        os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
        appmod._state.clear()  # force the temp DB + default profile reload
        self.client = TestClient(appmod.app)
        self.launched = []
        self._real_run_job = appmod._run_job
        self._real_threading = appmod.threading
        appmod._run_job = lambda *a, **k: self.launched.append(a)
        appmod.threading = types.SimpleNamespace(Thread=self._SyncThread)
        r = self.client.post("/brands",
                             json={"profile": load_profile()})
        self.assertEqual(r.status_code, 200)

    def tearDown(self):
        self.app._run_job = self._real_run_job
        self.app.threading = self._real_threading

    def create_project(self, **extra):
        payload = {"name": "Xmas 2026", "brand": "Meridian Market",
                   "brief": {"title": "Xmas", "brand": "Meridian Market"},
                   "overrides": OVERRIDES, **extra}
        return self.client.post("/projects", json=payload)

    def test_create_pins_head_and_survives_brand_edit(self):
        r = self.create_project()
        self.assertEqual(r.status_code, 200)
        project = r.json()
        self.assertEqual(project["brand_version"], 1)
        self.assertTrue(project["effective"]["overridden"])
        self.assertEqual(project["effective"]["rules"]["minTypeSize"], 5)
        # brand moves to v2; the project stays pinned at v1
        self.client.post("/brands", json={
            "profile": {**load_profile(), "version": "2026.2"}})
        detail = self.client.get(f"/projects/{project['id']}").json()
        self.assertEqual(detail["brand_version"], 1)
        # ...and the brand can't be deleted while pinned
        self.assertEqual(
            self.client.delete("/brands/Meridian%20Market").status_code, 409)

    def test_unknown_brand_and_bad_overrides_are_rejected(self):
        r = self.create_project(brand="Nope Brand")
        self.assertEqual(r.status_code, 404)
        r = self.create_project(overrides={
            "rules": {"minTypeSize": {"value": 5}}})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(
            r.json()["detail"]["errors"][0]["code"],
            "override-missing-reason")

    def test_generate_snapshots_brand_provenance(self):
        pid = self.create_project().json()["id"]
        r = self.client.post(f"/projects/{pid}/generate",
                             json={"n": 2, "engine": "draft"})
        self.assertEqual(r.status_code, 200)
        out = r.json()
        self.assertEqual(out["project_id"], pid)
        self.assertEqual(out["brand"]["brand_version"], 1)
        self.assertEqual(out["brand"]["overrides"], OVERRIDES)
        # the job row carries the snapshot; the launched profile is effective
        job = self.client.get(f"/jobs/{out['job_id']}").json()
        self.assertEqual(job["project_id"], pid)
        self.assertEqual(job["brand"]["effective_sha256"],
                         out["brand"]["effective_sha256"])
        self.assertEqual(len(self.launched), 1)
        job_id, brief, n, config, profile, runtime, project_id = \
            self.launched[0]
        self.assertEqual((job_id, n, project_id), (out["job_id"], 2, pid))
        self.assertIn("XmasFoilGold",
                      [s["name"] for s in profile["swatches"]])
        self.assertEqual(profile["rules"]["minTypeSize"], 5)

    def test_archived_projects_do_not_generate(self):
        pid = self.create_project().json()["id"]
        r = self.client.patch(f"/projects/{pid}",
                              json={"status": "archived"})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(f"/projects/{pid}/generate", json={})
        self.assertEqual(r.status_code, 409)

    def test_patch_revalidates_overrides_against_pin(self):
        pid = self.create_project().json()["id"]
        r = self.client.patch(f"/projects/{pid}", json={
            "overrides": {"restrict": {"fonts": ["Comic Sans"]}}})
        self.assertEqual(r.status_code, 422)
        r = self.client.patch(f"/projects/{pid}", json={
            "overrides": {"restrict": {"fonts": ["Canela Deck Medium"]}}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["effective"]["fonts"], 1)


if __name__ == "__main__":
    unittest.main()
