"""Public review delivery must not expose the private studio or local sources."""
import base64
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from client_reviews import make_router
from review_app import create_app
from store import DocStore


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1sAAAAASUVORK5CYII=')


class ReviewDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dist = self.root / 'dist'
        (self.dist / 'assets').mkdir(parents=True)
        (self.dist / 'index.html').write_text('<!doctype html><html lang="en"><head><script src="/assets/app.js"></script></head><body><div id="root"></div></body></html>')
        (self.dist / 'assets' / 'app.js').write_text('window.reviewBundleLoaded=true;')
        (self.dist / 'private-source.pdf').write_bytes(b'PRIVATE_PDF_SOURCE_NOT_PUBLIC')
        (self.root / 'private-guidance.md').write_text('PRIVATE_GUIDANCE_NOT_PUBLIC')
        (self.dist / 'assets' / 'outside-source.pdf').symlink_to(self.dist / 'private-source.pdf')
        self.store = DocStore(self.root / 'review.db')
        self.project = self.store.create_project('Client campaign', brief={'title': 'INTERNAL_BRIEF'})
        self.concept = self.store.create_concept({'title': 'INTERNAL_BRIEF'}, 'Poster', project_id=self.project)
        self.version = self.store.add_version(self.concept,
            {'version': '0.2', 'page': {'size': 'A4'}, 'pages': [{'items': []}]},
            schema_version='0.2', prompt_pack='0.2', validation={'ok': True, 'errors': [], 'warnings': []},
            proof_png=PNG, approved=False, effective_profile={'name': 'INTERNAL_BRAND_PROFILE'})
        private_app = FastAPI()
        private_app.include_router(make_router(lambda: self.store))
        self.studio = TestClient(private_app)
        response = self.studio.post('/projects/' + self.project + '/reviews',
                                    json={'title': 'Review this poster', 'version_ids': [self.version]})
        self.assertEqual(response.status_code, 200)
        self.review = response.json()
        self.client = TestClient(create_app(self.store, self.dist))

    def tearDown(self):
        self.client.close()
        self.studio.close()
        self.temporary.cleanup()

    def assert_private_headers(self, response):
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        self.assertEqual(response.headers.get('referrer-policy'), 'no-referrer')
        self.assertEqual(response.headers.get('x-frame-options'), 'DENY')
        self.assertEqual(response.headers.get('x-content-type-options'), 'nosniff')
        self.assertIn("frame-ancestors 'none'", response.headers.get('content-security-policy', ''))

    def test_index_enters_review_only_mode_and_serves_only_ui_bundle(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-review-only="true"', response.text)
        self.assertIn('text/html', response.headers['content-type'])
        self.assert_private_headers(response)
        asset = self.client.get('/assets/app.js')
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.text, 'window.reviewBundleLoaded=true;')
        self.assert_private_headers(asset)

    def test_studio_apis_and_documentation_are_not_mounted(self):
        paths = ['/api/projects', '/api/projects/' + self.project, '/api/brands',
                 '/api/assets', '/api/versions/' + self.version + '/document.json',
                 '/api/versions/' + self.version + '/bundle.zip', '/api/stats',
                 '/api/projects/' + self.project + '/reviews', '/api/brands/Brand/sources',
                 '/docs', '/redoc', '/openapi.json', '/api/docs', '/api/openapi.json']
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assert_private_headers(response)
                self.assertNotIn('INTERNAL_BRIEF', response.text)
                self.assertNotIn('INTERNAL_BRAND_PROFILE', response.text)
        for path in ('/api/generate', '/api/projects', '/api/brands', '/api/assets',
                     '/api/projects/' + self.project + '/reviews',
                     '/api/projects/' + self.project + '/reviews/' + self.review['id'] + '/revoke'):
            with self.subTest(post_path=path):
                self.assertEqual(self.client.post(path, json={}).status_code, 404)

    def test_arbitrary_source_paths_traversal_and_asset_symlinks_are_not_served(self):
        paths = ['/private-source.pdf', '/private-guidance.md',
                 '/assets/%2e%2e/private-source.pdf', '/assets/%2e%2e/%2e%2e/private-guidance.md',
                 '/assets/outside-source.pdf', '/api/files?path=' + str(self.root / 'private-guidance.md'),
                 '/api/brands/Brand/sources/arbitrary-id', '/review.db']
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn('PRIVATE_PDF_SOURCE_NOT_PUBLIC', response.text)
                self.assertNotIn('PRIVATE_GUIDANCE_NOT_PUBLIC', response.text)
                self.assert_private_headers(response)

    def test_legitimate_capability_can_read_proof_and_submit_feedback(self):
        prefix = '/api/client-reviews/' + self.review['token']
        metadata = self.client.get(prefix)
        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(metadata.json()['items'][0]['version_id'], self.version)
        self.assert_private_headers(metadata)
        proof = self.client.get(metadata.json()['items'][0]['proof_url'])
        self.assertEqual(proof.status_code, 200)
        self.assertEqual(proof.content, PNG)
        self.assert_private_headers(proof)
        payload = {'version_id': self.version, 'author': 'Client reviewer',
                   'action': 'approved', 'body': None, 'idempotency_key': 'client-review-click'}
        decision = self.client.post(prefix + '/events', json=payload)
        self.assertEqual(decision.status_code, 200)
        self.assert_private_headers(decision)
        self.assertEqual(self.client.get(prefix).json()['items'][0]['decision'], 'approved')
        self.assertFalse(self.store.get_version(self.version)['approved'])

    def test_revoked_links_and_unknown_tokens_retain_private_headers(self):
        unknown = self.client.get('/api/client-reviews/' + 'x' * 43)
        self.assertEqual(unknown.status_code, 404)
        self.assert_private_headers(unknown)
        self.studio.post('/projects/' + self.project + '/reviews/' + self.review['id'] + '/revoke')
        revoked = self.client.get('/api/client-reviews/' + self.review['token'])
        self.assertEqual(revoked.status_code, 410)
        self.assert_private_headers(revoked)


if __name__ == '__main__':
    unittest.main()
