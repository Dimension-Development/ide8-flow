"""Client-review security and decision regressions; temporary stores only.

No renderer, model, live database, real review link or external delivery is
used. Public responses must contain only the selected immutable proofs and
their review history, independently of model self-approval.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import client_reviews
from store import DocStore, content_hash


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1sAAAAASUVORK5CYII=')


class ClientReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = DocStore(Path(self.temporary.name) / 'reviews.db')
        profile = {'name': 'Private Brand', 'swatches': [], 'fonts': [],
                   'designPrinciples': 'PRIVATE_PROFILE_SENTINEL'}
        self.brand = self.store.save_brand_profile(profile['name'], profile)
        self.project = self.store.create_project('Campaign one', brand_version_id=self.brand['id'],
                                                 brief={'title': 'PRIVATE_BRIEF_SENTINEL'})
        self.other_project = self.store.create_project('Campaign two', brand_version_id=self.brand['id'])
        self.concept = self.store.create_concept({'title': 'PRIVATE_BRIEF_SENTINEL'},
                                                 'Hero: PRIVATE_STRATEGY_SENTINEL', project_id=self.project)
        self.version = self.version_for(self.concept)
        other_concept = self.store.create_concept({'title': 'Other private brief'}, 'Other', project_id=self.other_project)
        self.other_version = self.version_for(other_concept)
        self.app = FastAPI()
        self.app.include_router(client_reviews.make_router(lambda: self.store))
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temporary.cleanup()

    def version_for(self, concept, *, proof=PNG, valid=True, parent=None, approved=False):
        document = {'version': '0.2', 'page': {'size': 'A4'}, 'pages': [{'items': []}],
                    'title': 'PRIVATE_DOCUMENT_SENTINEL'}
        return self.store.add_version(concept, document, schema_version='0.2', prompt_pack='0.2',
                                      validation={'ok': valid, 'errors': [], 'warnings': [{'code': 'contrast-unknown'}]},
                                      proof_png=proof, effective_profile=self.brand['profile'],
                                      model_history=['PRIVATE_MODEL_SENTINEL'],
                                      usage={'cost_usd': 9876.54321}, critique={'approve': approved},
                                      approved=approved, parent_version_id=parent)

    def share(self, versions=None, project=None, **extra):
        return self.client.post('/projects/' + (project or self.project) + '/reviews',
                                json={'title': 'Artwork for review', 'version_ids': versions or [self.version], **extra})

    def created(self, **kwargs):
        response = self.share(**kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def feedback(self, token, action='comment', *, version=None, key='request-1', **extra):
        payload = {'version_id': version or self.version, 'author': 'Client reviewer',
                   'action': action, 'body': 'Please adjust spacing.', 'idempotency_key': key, **extra}
        return self.client.post('/client-reviews/' + token + '/events', json=payload)

    def row_count(self, table):
        with closing(self.store._connect()) as db:
            return db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]

    def test_creation_rejects_cross_project_versions_without_partial_share(self):
        response = self.share(versions=[self.version, self.other_version])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.row_count('client_review'), 0)
        self.assertEqual(self.row_count('client_review_item'), 0)
        self.assertEqual(self.share(project='missing-project').status_code, 404)
        self.assertEqual(self.share(versions=['missing-version']).status_code, 422)

    def test_public_payload_is_proof_only_and_token_is_not_relisted(self):
        share = self.created()
        public = self.client.get('/client-reviews/' + share['token'])
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.headers['cache-control'], 'no-store')
        self.assertEqual(public.headers['referrer-policy'], 'no-referrer')
        text = public.text
        for secret in ('PRIVATE_PROFILE_SENTINEL', 'PRIVATE_BRIEF_SENTINEL', 'PRIVATE_DOCUMENT_SENTINEL',
                       'PRIVATE_STRATEGY_SENTINEL', 'PRIVATE_MODEL_SENTINEL', '9876.54321'):
            self.assertNotIn(secret, text)
        for internal in ('"brief"', '"profile"', '"document"', '"usage"', '"cost_usd"', '"token_hash"', '"token"'):
            self.assertNotIn(internal, text)
        item = public.json()['items'][0]
        self.assertEqual(item['version_id'], self.version)
        self.assertEqual(item['label'], 'Hero')
        self.assertEqual(item['warning_count'], 1)
        self.assertEqual(item['content_hash'], self.store.get_version(self.version)['content_hash'])
        self.assertIn('/versions/' + self.version + '/proof.png', item['proof_url'])
        listing = self.client.get('/projects/' + self.project + '/reviews')
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(share['token'], listing.text)
        self.assertNotIn('token_hash', listing.text)
        self.assertNotIn('proof_url', listing.text)
        with closing(self.store._connect()) as db:
            row = db.execute('SELECT * FROM client_review WHERE id=?', (share['id'],)).fetchone()
            self.assertEqual(row['token_hash'], hashlib.sha256(share['token'].encode()).hexdigest())
            self.assertNotIn(share['token'], tuple(row))

    def test_capability_only_serves_selected_exact_proof_bytes(self):
        share = self.created()
        prefix = '/client-reviews/' + share['token']
        proof = self.client.get(prefix + '/versions/' + self.version + '/proof.png')
        self.assertEqual(proof.status_code, 200)
        self.assertEqual(proof.content, PNG)
        self.assertEqual(proof.headers['content-type'], 'image/png')
        self.assertEqual(proof.headers['cache-control'], 'no-store')
        self.assertEqual(proof.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.client.get(prefix + '/versions/' + self.other_version + '/proof.png').status_code, 404)
        self.assertEqual(self.feedback(share['token'], version=self.other_version).status_code, 404)
        self.assertEqual(self.client.get('/client-reviews/not-a-token').status_code, 404)
        self.assertEqual(self.client.get('/client-reviews/' + 'x' * 43).status_code, 404)

    def test_expiry_blocks_public_read_proof_and_feedback(self):
        share = self.created(expires_days=1)
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with patch.object(client_reviews, 'now', return_value=future):
            self.assertEqual(self.client.get('/client-reviews/' + share['token']).status_code, 410)
            self.assertEqual(self.client.get('/client-reviews/' + share['token'] + '/versions/' + self.version + '/proof.png').status_code, 410)
            self.assertEqual(self.feedback(share['token']).status_code, 410)
        self.assertEqual(self.row_count('client_review_event'), 0)

    def test_revoke_is_project_scoped_and_idempotent(self):
        share = self.created()
        self.assertEqual(self.client.post('/projects/' + self.other_project + '/reviews/' + share['id'] + '/revoke').status_code, 404)
        self.assertEqual(self.client.get('/client-reviews/' + share['token']).status_code, 200)
        path = '/projects/' + self.project + '/reviews/' + share['id'] + '/revoke'
        self.assertEqual(self.client.post(path).status_code, 200)
        with closing(self.store._connect()) as db:
            timestamp = db.execute('SELECT revoked_at FROM client_review WHERE id=?', (share['id'],)).fetchone()[0]
        self.assertEqual(self.client.post(path).status_code, 200)
        with closing(self.store._connect()) as db:
            self.assertEqual(timestamp, db.execute('SELECT revoked_at FROM client_review WHERE id=?', (share['id'],)).fetchone()[0])
        self.assertEqual(self.client.get('/client-reviews/' + share['token']).status_code, 410)
        self.assertEqual(self.feedback(share['token'], 'approved').status_code, 410)

    def test_invalid_creation_and_feedback_never_write_events(self):
        bad_creates = [
            {'title': ''}, {'title': 'x' * 301}, {'version_ids': []},
            {'version_ids': [self.version] * 2}, {'version_ids': ['v' + str(i) for i in range(21)]},
            {'version_ids': [1]}, {'expires_days': True}, {'expires_days': 0},
            {'expires_days': 31}, {'expires_days': '7'},
        ]
        for extra in bad_creates:
            with self.subTest(extra=extra):
                response = self.client.post('/projects/' + self.project + '/reviews',
                                            json={'title': 'Review', 'version_ids': [self.version], **extra})
                self.assertEqual(response.status_code, 422)
        share = self.created()
        for extra in ({'author': ''}, {'author': 'x' * 121}, {'body': ''}, {'body': 'x' * 5001},
                      {'idempotency_key': ''}, {'idempotency_key': 'x' * 101},
                      {'version_id': ''}, {'action': 'publish'}, {'action': 'changes_requested', 'body': None}):
            with self.subTest(extra=extra):
                response = self.feedback(share['token'], **extra)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.row_count('client_review_event'), 0)

    def test_stale_discarded_unrendered_and_archived_work_cannot_be_shared(self):
        self.version_for(self.concept, parent=self.version)
        self.assertEqual(self.share().status_code, 409)
        for proof, valid in ((None, True), (PNG, False)):
            concept = self.store.create_concept({}, 'Test', project_id=self.project)
            version = self.version_for(concept, proof=proof, valid=valid)
            self.assertEqual(self.share(versions=[version]).status_code, 409)
        concept = self.store.create_concept({}, 'Discarded', project_id=self.project)
        version = self.version_for(concept)
        self.store.set_discarded(concept, True)
        self.assertEqual(self.share(versions=[version]).status_code, 409)
        self.store.update_project(self.other_project, status='archived')
        self.assertEqual(self.share(project=self.other_project, versions=[self.other_version]).status_code, 409)
        self.assertEqual(self.row_count('client_review'), 0)

    def test_superseded_or_withdrawn_proof_stays_viewable_but_not_approvable(self):
        share = self.created()
        self.version_for(self.concept, parent=self.version)
        public = self.client.get('/client-reviews/' + share['token'])
        self.assertTrue(public.json()['items'][0]['superseded'])
        self.assertEqual(self.feedback(share['token'], 'approved', key='approve').status_code, 409)
        self.assertEqual(self.feedback(share['token'], 'comment', key='comment').status_code, 200)
        self.assertEqual(self.client.get('/client-reviews/' + share['token'] + '/versions/' + self.version + '/proof.png').content, PNG)
        other_share = self.created(project=self.other_project, versions=[self.other_version])
        other_concept = self.store.get_version(self.other_version)['concept_id']
        self.store.set_discarded(other_concept, True)
        self.assertEqual(self.feedback(other_share['token'], 'approved', version=self.other_version).status_code, 409)
        self.assertEqual(self.feedback(other_share['token'], version=self.other_version).status_code, 200)

    def test_decision_is_terminal_but_comments_and_exact_retries_remain_allowed(self):
        share = self.created()
        original = self.feedback(share['token'], 'changes_requested')
        self.assertEqual(original.status_code, 200)
        retry = self.feedback(share['token'], 'changes_requested')
        self.assertEqual(retry.json(), original.json())
        self.assertEqual(self.feedback(share['token'], 'approved', key='different-decision').status_code, 409)
        self.assertEqual(self.feedback(share['token'], 'changes_requested', key='second-decision').status_code, 409)
        self.assertEqual(self.feedback(share['token'], key='additional-comment').status_code, 200)
        item = self.client.get('/client-reviews/' + share['token']).json()['items'][0]
        self.assertEqual(item['decision'], 'changes_requested')
        self.assertEqual([e['action'] for e in item['events']], ['changes_requested', 'comment'])
        self.assertEqual(self.row_count('client_review_event'), 2)

    def test_conflicting_retry_is_rejected_and_keys_are_scoped_to_review(self):
        share = self.created()
        first = self.feedback(share['token'])
        self.assertEqual(first.status_code, 200)
        for change in ({'body': 'different feedback'}, {'author': 'Different reviewer'}, {'action': 'approved'}):
            self.assertEqual(self.feedback(share['token'], **change).status_code, 409)
        second_share = self.created()
        second = self.feedback(second_share['token'], 'approved')
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(self.row_count('client_review_event'), 2)

    def test_exact_approval_retry_is_stable_after_version_is_superseded(self):
        share = self.created()
        original = self.feedback(share['token'], 'approved', body=None)
        self.assertEqual(original.status_code, 200)
        self.version_for(self.concept, parent=self.version)
        repeated = self.feedback(share['token'], 'approved', body=None)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json(), original.json())
        self.assertEqual(self.feedback(share['token'], 'approved', key='new-request').status_code, 409)
        self.assertEqual(self.row_count('client_review_event'), 1)

    def test_concurrent_conflicting_decisions_record_only_one_event(self):
        share = self.created()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda action: self.feedback(share['token'], action, key=action),
                                      ['approved', 'changes_requested']))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.row_count('client_review_event'), 1)

    def test_human_decisions_do_not_change_model_approval_or_immutable_versions(self):
        share = self.created()
        before = self.store.get_version(self.version)
        self.assertFalse(before['approved'])
        self.assertEqual(self.feedback(share['token'], 'approved').status_code, 200)
        self.assertEqual(self.store.get_version(self.version), before)
        self.assertEqual(self.client.get('/client-reviews/' + share['token']).json()['items'][0]['decision'], 'approved')

    def test_event_history_cannot_be_updated_or_deleted(self):
        share = self.created()
        original = self.feedback(share['token'], 'approved').json()
        with closing(self.store._connect()) as db:
            for statement in ('UPDATE client_review_event SET body=\'rewritten\' WHERE id=?',
                              'DELETE FROM client_review_event WHERE id=?'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(statement, (original['id'],))
                db.rollback()
        events = self.client.get('/client-reviews/' + share['token']).json()['items'][0]['events']
        self.assertEqual(events, [original])

    def test_changed_proof_or_document_hash_fails_shared_integrity_checks(self):
        for column, value in (('proof_png', b'changed proof bytes'), ('content_hash', '0' * 64)):
            with self.subTest(column=column):
                concept = self.store.create_concept({}, 'Integrity check', project_id=self.project)
                version = self.version_for(concept)
                share = self.created(versions=[version])
                # Corrupt only an isolated fixture to exercise read-side integrity
                # protection independently of the normal immutable-write trigger.
                with closing(self.store._connect()) as db:
                    db.execute('DROP TRIGGER IF EXISTS doc_version_immutable')
                    db.execute('UPDATE doc_version SET ' + column + '=? WHERE id=?', (value, version))
                    db.commit()
                self.assertEqual(self.client.get('/client-reviews/' + share['token']).status_code, 409)
                self.assertEqual(self.client.get('/client-reviews/' + share['token'] + '/versions/' + version + '/proof.png').status_code, 409)
                self.assertEqual(self.feedback(share['token'], 'approved', version=version).status_code, 409)

    def test_document_bytes_must_match_cached_hash_at_sharing_and_public_read(self):
        share = self.created()
        document = self.store.get_version(self.version)['document']
        document['title'] = 'Altered without regenerating the saved proof'
        self.assertNotEqual(content_hash(document), self.store.get_version(self.version)['content_hash'])
        with closing(self.store._connect()) as db:
            db.execute('DROP TRIGGER doc_version_immutable')
            db.execute('UPDATE doc_version SET document_json=? WHERE id=?', (json.dumps(document), self.version))
            db.commit()
        self.assertEqual(self.share().status_code, 409, 'A stale proof must not be newly shared after its document changed')
        self.assertEqual(self.client.get('/client-reviews/' + share['token']).status_code, 409)
        self.assertEqual(self.client.get('/client-reviews/' + share['token'] + '/versions/' + self.version + '/proof.png').status_code, 409)


if __name__ == '__main__':
    unittest.main()
