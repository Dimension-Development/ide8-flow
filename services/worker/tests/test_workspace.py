"""Durable campaign, identity review/publication and brand-library boundaries."""
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app as worker
from generation.service import _asset_map
from store import DocStore
from workspace import WorkspaceConflict


def profile(name='Studio Brand'):
    return {'name': name, 'swatches': [], 'fonts': [], 'rules': {},
            'designPrinciples': 'Original published guidance.'}


def draft_profile(name='Studio Brand'):
    return {**profile(name), 'designPrinciples': 'Reviewed studio guidance.',
            'identity': {'schemaVersion': 1, 'brandName': name, 'campaignName': 'Summer',
                         'ranges': ['First', 'Second'], 'cards': [
                {'id': 'C01', 'category': 'guidance', 'title': 'Spacing',
                 'body': 'Give the product room.', 'status': 'reviewed',
                 'scope': 'Shared', 'source': {'label': 'Brand PDF', 'page': 2,
                                              'path': '/private/display-only.pdf'},
                 'review': {'by': 'Luke', 'action': 'reviewed', 'clientApproval': False}}],
                         'provenance': {'internalOnly': True}}}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = DocStore(Path(self.temporary.name) / 'workspace.db')
        self.brand = self.store.save_brand_profile('Studio Brand', profile())
        self.other = self.store.save_brand_profile('Other Brand', profile('Other Brand'))
        self.client = TestClient(worker.app)
        self.dependencies = patch.object(worker, '_deps', return_value=self.store)
        self.dependencies.start()

    def tearDown(self):
        self.dependencies.stop()
        self.client.close()
        self.temporary.cleanup()

    def campaign(self):
        return self.store.create_campaign(name='Summer', brand='Studio Brand', ranges=['First', 'Second'])

    def test_campaign_project_relationship_is_durable_and_optional(self):
        campaign = self.campaign()
        pid = self.store.create_project('Poster', brand_version_id=self.brand['id'], campaign_id=campaign['id'])
        legacy = self.store.create_project('Existing ungrouped project')
        reopened = DocStore(self.store._path)
        self.assertEqual(reopened.get_project(pid)['campaign_id'], campaign['id'])
        self.assertIsNone(reopened.get_project(legacy)['campaign_id'])
        self.assertEqual(reopened.get_campaign(campaign['id'])['project_count'], 1)
        reopened.update_campaign(campaign['id'], ranges=['First', 'Second', 'Third'], status='archived')
        self.assertEqual(reopened.list_campaigns(), [])
        self.assertEqual(len(reopened.list_campaigns(True)), 1)
        self.assertEqual(reopened.get_project(pid)['brand_version'], 1)

    def test_cross_brand_link_and_repin_are_rejected_atomically(self):
        campaign = self.campaign()
        with self.assertRaises(WorkspaceConflict):
            self.store.create_project('Wrong brand', brand_version_id=self.other['id'], campaign_id=campaign['id'])
        pid = self.store.create_project('Poster', brand_version_id=self.brand['id'], campaign_id=campaign['id'])
        with self.assertRaises(WorkspaceConflict):
            self.store.update_project(pid, brand_version_id=self.other['id'])
        self.assertEqual(self.store.get_project(pid)['brand_version_id'], self.brand['id'])
        with self.assertRaises(WorkspaceConflict):
            self.store.update_campaign(campaign['id'], brand='Other Brand')
        self.store.update_project(pid, campaign_id=None, brand_version_id=self.other['id'])
        self.assertEqual(self.store.get_project(pid)['brand'], 'Other Brand')

    def test_campaign_api_validation_and_duplicate_names(self):
        response = self.client.post('/campaigns', json={'name': 'Summer', 'brand': 'Studio Brand', 'ranges': ['First']})
        self.assertEqual(response.status_code, 200)
        campaign = response.json()
        self.assertEqual(self.client.post('/campaigns', json={'name': 'Summer', 'brand': 'Studio Brand'}).status_code, 409)
        self.assertEqual(self.client.patch('/campaigns/' + campaign['id'], json={'status': 'deleted'}).status_code, 400)
        self.assertEqual(self.client.get('/campaigns').json()['campaigns'][0]['id'], campaign['id'])
        self.assertEqual(self.client.post('/projects', json={'name': 'Wrong', 'brand': 'Other Brand', 'campaign_id': campaign['id']}).status_code, 409)
        project = self.client.post('/projects', json={'name': 'Correct', 'brand': 'Studio Brand', 'campaign_id': campaign['id']})
        self.assertEqual(project.status_code, 200)
        self.assertEqual(self.client.patch('/projects/' + project.json()['id'], json={'brand': None}).status_code, 409)

    def test_draft_save_is_isolated_until_explicit_publication(self):
        pid = self.store.create_project('Pinned work', brand_version_id=self.brand['id'])
        initial = self.client.get('/brands/Studio%20Brand/identity-draft').json()
        self.assertEqual(initial['revision'], 0)
        self.assertFalse(initial['is_saved'])
        saved = self.client.put('/brands/Studio%20Brand/identity-draft', json={'profile': draft_profile(), 'expected_revision': 0})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['revision'], 1)
        self.assertEqual(self.store.get_brand_profile('Studio Brand')['profile'], profile())
        self.assertEqual(len(self.store.list_brand_versions('Studio Brand')), 1)
        published = self.client.post('/brands/Studio%20Brand/identity-draft/publish', json={'revision': 1})
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()['brand']['version'], 2)
        self.assertEqual(published.json()['brand']['profile']['identity'], draft_profile()['identity'])
        self.assertIn('Give the product room.', published.json()['brand']['profile']['designPrinciples'])
        self.assertNotIn('Reviewed studio guidance.', published.json()['brand']['profile']['designPrinciples'])
        self.assertEqual(self.store.get_brand_profile('Studio Brand', 1)['profile'], profile())
        self.assertEqual(self.store.get_project(pid)['brand_version_id'], self.brand['id'])
        repeated = self.client.post('/brands/Studio%20Brand/identity-draft/publish', json={'revision': 1})
        self.assertEqual(repeated.json()['brand']['version'], 2)
        self.assertEqual(self.store.get_brand_profile('Other Brand')['version'], 1)

    def test_stale_draft_save_and_publish_do_not_overwrite(self):
        self.store.save_identity_draft('Studio Brand', draft_profile(), expected_revision=0)
        with self.assertRaises(WorkspaceConflict):
            self.store.save_identity_draft('Studio Brand', draft_profile(), expected_revision=0)
        changed = draft_profile()
        changed['identity']['cards'][0]['body'] = 'Changed draft'
        self.store.save_identity_draft('Studio Brand', changed, expected_revision=1)
        with self.assertRaises(WorkspaceConflict):
            self.store.publish_identity_draft('Studio Brand', revision=1)
        self.assertEqual(self.store.get_brand_profile('Studio Brand')['version'], 1)

    def test_published_head_conflict_requires_explicit_rebase(self):
        self.store.save_identity_draft('Studio Brand', draft_profile(), expected_revision=0)
        new_head = self.store.save_brand_profile('Studio Brand', {**profile(), 'designPrinciples': 'External edit'})
        with self.assertRaises(WorkspaceConflict):
            self.store.publish_identity_draft('Studio Brand', revision=1)
        self.store.save_identity_draft('Studio Brand', draft_profile(), expected_revision=1, base_version_id=new_head['id'])
        self.assertEqual(self.store.publish_identity_draft('Studio Brand', revision=2)['brand']['version'], 3)

    def test_concurrent_draft_edits_have_exactly_one_winner(self):
        def save(_):
            try:
                self.store.save_identity_draft('Studio Brand', draft_profile(), expected_revision=0)
                return 'saved'
            except WorkspaceConflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(save, range(2))), ['conflict', 'saved'])

    def test_bad_identity_status_and_active_source_urls_rejected(self):
        for field, value in [('status', 'client-approved'), ('source', {'url': 'javascript:alert(1)'}),
                             ('review', {'by': 'Luke', 'clientApproval': True})]:
            draft = draft_profile()
            draft['identity']['cards'][0][field] = value
            self.assertEqual(self.client.put('/brands/Studio%20Brand/identity-draft', json={'profile': draft, 'expected_revision': 0}).status_code, 400)
        draft = draft_profile()
        draft['identity']['brandName'] = 'Friendly display label'
        draft['identity']['cards'][0]['source']['url'] = '/api/brands/Studio%20Brand/sources/abc#page=2'
        self.assertEqual(self.client.put('/brands/Studio%20Brand/identity-draft', json={'profile': draft, 'expected_revision': 0}).status_code, 200)

    def test_asset_assignment_is_atomic_brand_specific_and_filters_model_input(self):
        for name in ('one', 'two'):
            self.store.add_asset(name, name + '.png', 'image/png', 1, 1, name.encode())
        self.assertEqual(_asset_map(self.store, profile()), {})
        assigned = self.client.put('/brands/Studio%20Brand/assets', json={'names': ['one']})
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(self.client.put('/brands/Studio%20Brand/assets', json={'names': ['two', 'missing']}).status_code, 400)
        self.assertEqual(self.store.get_brand_assets('Studio Brand')['names'], ['one'])
        self.assertEqual(set(_asset_map(self.store, profile())), {'one'})
        self.assertEqual(_asset_map(self.store, profile(), {'references': {'imageAssets': ['two']}}), {})
        self.assertEqual(self.store.get_brand_assets('Other Brand')['names'], [])

    def test_generation_rejects_other_brand_asset_before_model_initialization(self):
        self.store.add_asset('foreign', 'f.png', 'image/png', 1, 1, b'x')
        pid = self.store.create_project('Poster', brand_version_id=self.brand['id'])
        brief = {'title': 'Test', 'brand': 'Studio Brand', 'references': {'imageAssets': ['foreign']}}
        with patch.object(worker, '_gen_deps', side_effect=AssertionError('model dependencies must not initialize')):
            response = self.client.post('/projects/' + pid + '/generate', json={'brief': brief, 'n': 1})
            standalone = self.client.post('/generate', json={'brief': brief, 'n': 1})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(standalone.status_code, 422)

    def test_legacy_unassigned_assets_and_project_migration(self):
        self.store.add_asset('legacy', 'l.png', 'image/png', 1, 1, b'x')
        db = sqlite3.connect(self.store._path)
        db.execute('DELETE FROM brand_asset_set WHERE brand_name=?', ('Studio Brand',))
        db.commit()
        db.close()
        self.assertEqual(set(_asset_map(self.store, profile())), {'legacy'})
        path = Path(self.temporary.name) / 'legacy.db'
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE project (id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,brand_version_id TEXT,brief_json TEXT NOT NULL DEFAULT '{}',overrides_json TEXT,status TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL DEFAULT (datetime('now')),updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
        db.execute("INSERT INTO project(id,name) VALUES ('old','Legacy project')")
        db.commit()
        db.close()
        migrated = DocStore(path)
        self.assertEqual(migrated.get_project('old')['name'], 'Legacy project')
        self.assertIsNone(migrated.get_project('old')['campaign_id'])
        self.assertEqual(DocStore(path).get_project('old'), migrated.get_project('old'))

    def test_project_names_are_scoped_by_brand_and_campaign(self):
        first = self.store.create_project('Launch', brand_version_id=self.brand['id'])
        other = self.store.create_project('Launch', brand_version_id=self.other['id'])
        self.assertTrue(first and other)
        newer = self.store.save_brand_profile('Studio Brand', {**profile(), 'version': '2'})
        self.assertIsNone(self.store.create_project('Launch', brand_version_id=newer['id']))
        campaign = self.campaign()
        scoped = self.store.create_project('Launch', brand_version_id=self.brand['id'], campaign_id=campaign['id'])
        self.assertTrue(scoped)
        with self.assertRaises(WorkspaceConflict):
            self.store.update_project(scoped, campaign_id=None)
        with self.assertRaises(WorkspaceConflict):
            self.store.update_project(other, brand_version_id=self.brand['id'])
        self.assertEqual(self.store.get_project(other)['brand'], 'Other Brand')
        self.assertEqual(self.store.get_project(scoped)['campaign_id'], campaign['id'])

    def test_project_api_exposes_current_campaign_name_and_handles_ungrouped(self):
        campaign = self.campaign()
        pid = self.store.create_project('Poster', brand_version_id=self.brand['id'], campaign_id=campaign['id'])
        ungrouped = self.store.create_project('Ungrouped', brand_version_id=self.brand['id'])
        self.assertEqual(self.client.get('/projects/' + pid).json()['campaign_name'], 'Summer')
        projects = {p['id']: p for p in self.client.get('/projects').json()['projects']}
        self.assertEqual(projects[pid]['campaign_name'], 'Summer')
        self.assertIsNone(projects[ungrouped]['campaign_name'])
        self.store.update_campaign(campaign['id'], name='Summer launch')
        self.assertEqual(self.store.get_project(pid)['campaign_name'], 'Summer launch')
        self.assertEqual(self.store.get_project(pid)['campaign_id'], campaign['id'])

    def test_brand_summary_alias_comes_only_from_published_identity(self):
        draft = draft_profile()
        draft['identity']['brandName'] = 'Friendly label'
        self.store.save_identity_draft('Studio Brand', draft, expected_revision=0)
        summaries = {b['name']: b for b in self.client.get('/brands').json()['brands']}
        self.assertIsNone(summaries['Studio Brand']['identity'])
        self.store.publish_identity_draft('Studio Brand', revision=1)
        summaries = {b['name']: b for b in self.client.get('/brands').json()['brands']}
        self.assertEqual(summaries['Studio Brand']['identity'], {'brandName': 'Friendly label'})
        self.assertNotIn('cards', summaries['Studio Brand']['identity'])
        draft['identity']['brandName'] = 'Unpublished replacement'
        self.store.save_identity_draft('Studio Brand', draft, expected_revision=1)
        summaries = {b['name']: b for b in self.client.get('/brands').json()['brands']}
        self.assertEqual(summaries['Studio Brand']['identity']['brandName'], 'Friendly label')

    def test_concurrent_same_scope_project_names_have_one_winner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.store.create_project('Launch', brand_version_id=self.brand['id']), range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_global_unique_migration_preserves_project_and_references(self):
        campaign = self.campaign()
        pid = self.store.create_project('Launch', brand_version_id=self.brand['id'], campaign_id=campaign['id'], brief={'copy': 'unchanged'})
        before = self.store.get_project(pid)
        db = sqlite3.connect(self.store._path)
        # Reproduce the legacy UNIQUE(name) constraint using its equivalent
        # named index, plus a real referencing row that must not cascade away.
        db.execute('CREATE UNIQUE INDEX legacy_project_name ON project(name)')
        db.execute('CREATE INDEX keep_project_status ON project(status)')
        db.execute('CREATE TABLE project_attachment(id TEXT PRIMARY KEY,project_id TEXT REFERENCES project(id) ON DELETE CASCADE)')
        db.execute('INSERT INTO project_attachment VALUES (?,?)', ('attachment', pid))
        db.commit()
        db.close()
        reopened = DocStore(self.store._path)
        self.assertEqual(reopened.get_project(pid), before)
        db = sqlite3.connect(self.store._path)
        self.assertEqual(db.execute('SELECT project_id FROM project_attachment').fetchone()[0], pid)
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='keep_project_status'").fetchone())
        db.close()
        self.assertTrue(reopened.create_project('Launch', brand_version_id=self.other['id']))


if __name__ == '__main__':
    unittest.main()
