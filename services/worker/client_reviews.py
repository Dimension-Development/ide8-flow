"""Capability-scoped client review of immutable artwork versions.

Studio routes rely on the private studio deployment boundary. Public delivery
must expose only /client-reviews, never the unauthenticated studio worker.
Tokens are returned once, stored as hashes, and confer review access only.
"""
import hashlib
import json
import os
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Response
from store import content_hash


def now():
    return datetime.now(timezone.utc).isoformat()


def checked_text(value, field, maximum=300, optional=False):
    if optional and value is None:
        return ''
    if not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip()):
        raise HTTPException(422, f'{field} must be text of at most {maximum} characters')
    return value.strip()


def make_router(get_store):
    router = APIRouter()

    def connection():
        db = get_store()._connect()
        db.executescript('''
          CREATE TABLE IF NOT EXISTS client_review (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
            token_hash TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
            project_name TEXT NOT NULL, created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL, revoked_at TEXT);
          CREATE TABLE IF NOT EXISTS client_review_item (
            review_id TEXT NOT NULL REFERENCES client_review(id),
            version_id TEXT NOT NULL REFERENCES doc_version(id),
            concept_id TEXT NOT NULL REFERENCES concept(id), label TEXT NOT NULL,
            version_label TEXT NOT NULL, content_hash TEXT NOT NULL,
            proof_hash TEXT NOT NULL, position INTEGER NOT NULL,
            PRIMARY KEY(review_id,version_id));
          CREATE TABLE IF NOT EXISTS client_review_event (
            id TEXT PRIMARY KEY, review_id TEXT NOT NULL,
            version_id TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('comment','approved','changes_requested')),
            created_at TEXT NOT NULL, idempotency_key TEXT NOT NULL,
            FOREIGN KEY(review_id,version_id) REFERENCES client_review_item(review_id,version_id),
            UNIQUE(review_id,idempotency_key));
          CREATE UNIQUE INDEX IF NOT EXISTS one_client_decision
            ON client_review_event(review_id,version_id) WHERE action != 'comment';
          CREATE TRIGGER IF NOT EXISTS client_review_event_immutable
            BEFORE UPDATE ON client_review_event BEGIN SELECT RAISE(ABORT,'review events are immutable'); END;
          CREATE TRIGGER IF NOT EXISTS client_review_event_no_delete
            BEFORE DELETE ON client_review_event BEGIN SELECT RAISE(ABORT,'review events are immutable'); END;
        ''')
        return db

    def project(db, pid):
        row = db.execute('SELECT * FROM project WHERE id=?', (pid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'project not found')
        return row

    def capability(db, token):
        if not isinstance(token, str) or not 30 <= len(token) <= 100:
            raise HTTPException(404, 'review link not found')
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = db.execute('SELECT * FROM client_review WHERE token_hash=?', (digest,)).fetchone()
        if row is None:
            raise HTTPException(404, 'review link not found')
        if row['revoked_at'] or row['expires_at'] <= now():
            raise HTTPException(410, 'This review link has expired or been revoked. Ask the studio for a new link.')
        return row

    def item_state(db, item):
        latest = db.execute('SELECT id FROM doc_version WHERE concept_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                            (item['concept_id'],)).fetchone()
        version = db.execute('SELECT content_hash,document_json,proof_png,validation_json FROM doc_version WHERE id=?', (item['version_id'],)).fetchone()
        if (version is None or version['content_hash'] != item['content_hash'] or
                content_hash(json.loads(version['document_json'])) != item['content_hash'] or
                hashlib.sha256(version['proof_png'] or b'').hexdigest() != item['proof_hash']):
            raise HTTPException(409, 'Shared proof integrity check failed. Ask the studio for a new review.')
        validation = json.loads(version['validation_json'])
        concept = db.execute('SELECT discarded FROM concept WHERE id=?', (item['concept_id'],)).fetchone()
        return latest['id'] != item['version_id'] or bool(concept['discarded']), len(validation.get('warnings', []))

    def serialize(db, row, token=None):
        result = {k: row[k] for k in ('id','title','project_name','created_at','expires_at','revoked_at')}
        result['items'] = []
        for item in db.execute('SELECT * FROM client_review_item WHERE review_id=? ORDER BY position', (row['id'],)).fetchall():
            superseded, warnings = item_state(db, item)
            out = {k: item[k] for k in ('version_id','concept_id','label','version_label','content_hash')}
            events = db.execute('SELECT id,author,body,action,created_at FROM client_review_event WHERE review_id=? AND version_id=? ORDER BY created_at,rowid', (row['id'],item['version_id'])).fetchall()
            out.update(events=[dict(e) for e in events], decision=next((e['action'] for e in events if e['action'] != 'comment'), None),
                       superseded=superseded, warning_count=warnings)
            if token:
                out['proof_url'] = f'/api/client-reviews/{token}/versions/{item["version_id"]}/proof.png'
            result['items'].append(out)
        return result

    @router.post('/projects/{pid}/reviews')
    def create(pid: str, payload: dict = Body(...)):
        title = checked_text(payload.get('title'), 'review title')
        vids = payload.get('version_ids')
        if not isinstance(vids, list) or not 1 <= len(vids) <= 20 or any(not isinstance(v,str) for v in vids) or len(set(vids)) != len(vids):
            raise HTTPException(422, 'select 1–20 distinct proof versions')
        days = payload.get('expires_days', 7)
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30:
            raise HTTPException(422, 'expiry must be 1–30 days')
        token = secrets.token_urlsafe(32)
        rid, timestamp = uuid4().hex, now()
        with closing(connection()) as db:
            db.execute('BEGIN IMMEDIATE')
            p = project(db, pid)
            if p['status'] != 'active':
                raise HTTPException(409, 'reactivate the project before sharing')
            items = []
            for position, vid in enumerate(vids):
                v = db.execute('SELECT v.*,c.project_id,c.archetype,c.discarded FROM doc_version v JOIN concept c ON c.id=v.concept_id WHERE v.id=?', (vid,)).fetchone()
                if v is None or v['project_id'] != pid:
                    raise HTTPException(422, 'every shared version must belong to this project')
                latest = db.execute('SELECT id FROM doc_version WHERE concept_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (v['concept_id'],)).fetchone()
                if v['discarded'] or latest['id'] != vid or not v['proof_png'] or not json.loads(v['validation_json']).get('ok'):
                    raise HTTPException(409, 'share only current, render-valid, undiscarded proofs')
                if content_hash(json.loads(v['document_json'])) != v['content_hash']:
                    raise HTTPException(409, 'document integrity check failed')
                number = db.execute('SELECT COUNT(*) FROM doc_version WHERE concept_id=?', (v['concept_id'],)).fetchone()[0]
                items.append((rid,vid,v['concept_id'],v['archetype'].split(':')[0],f'Version {number}',v['content_hash'],hashlib.sha256(v['proof_png']).hexdigest(),position))
            db.execute('INSERT INTO client_review VALUES (?,?,?,?,?,?,?,NULL)',
                       (rid,pid,hashlib.sha256(token.encode()).hexdigest(),title,p['name'],timestamp,(datetime.now(timezone.utc)+timedelta(days=days)).isoformat()))
            db.executemany('INSERT INTO client_review_item VALUES (?,?,?,?,?,?,?,?)', items)
            db.commit()
            return {**serialize(db, db.execute('SELECT * FROM client_review WHERE id=?',(rid,)).fetchone()),
                    'token':token, 'review_base_url':os.environ.get('CLIENT_REVIEW_BASE_URL')}

    @router.get('/projects/{pid}/reviews')
    def listing(pid: str):
        with closing(connection()) as db:
            project(db,pid)
            return {'reviews':[serialize(db,r) for r in db.execute('SELECT * FROM client_review WHERE project_id=? ORDER BY created_at DESC',(pid,)).fetchall()]}

    @router.post('/projects/{pid}/reviews/{rid}/revoke')
    def revoke(pid: str, rid: str):
        with closing(connection()) as db:
            project(db,pid)
            if db.execute('UPDATE client_review SET revoked_at=COALESCE(revoked_at,?) WHERE id=? AND project_id=?',(now(),rid,pid)).rowcount != 1:
                raise HTTPException(404,'review not found in this project')
            db.commit()
            return {'revoked':True}

    @router.get('/client-reviews/{token}')
    def public(token: str, response: Response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        with closing(connection()) as db:
            return serialize(db,capability(db,token),token)

    @router.get('/client-reviews/{token}/versions/{vid}/proof.png')
    def proof(token: str, vid: str):
        with closing(connection()) as db:
            review = capability(db,token)
            item = db.execute('SELECT * FROM client_review_item WHERE review_id=? AND version_id=?',(review['id'],vid)).fetchone()
            if item is None:
                raise HTTPException(404,'proof not included in this review')
            item_state(db,item)
            png = db.execute('SELECT proof_png FROM doc_version WHERE id=?',(vid,)).fetchone()[0]
            return Response(png, media_type='image/png',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})

    @router.post('/client-reviews/{token}/events')
    def event(token: str, payload: dict = Body(...)):
        author = checked_text(payload.get('author'),'your name',120)
        action = payload.get('action')
        if action not in ('comment','approved','changes_requested'):
            raise HTTPException(422,'choose comment, approved or changes_requested')
        body = checked_text(payload.get('body'),'feedback',5000,optional=action=='approved')
        key = checked_text(payload.get('idempotency_key'),'request key',100)
        vid = checked_text(payload.get('version_id'),'version ID',100)
        with closing(connection()) as db:
            db.execute('BEGIN IMMEDIATE')
            review = capability(db,token)
            item = db.execute('SELECT * FROM client_review_item WHERE review_id=? AND version_id=?',(review['id'],vid)).fetchone()
            if item is None:
                raise HTTPException(404,'version not included in this review')
            old = db.execute('SELECT * FROM client_review_event WHERE review_id=? AND idempotency_key=?',(review['id'],key)).fetchone()
            if old:
                if (old['version_id'],old['author'],old['body'],old['action']) != (vid,author,body,action):
                    raise HTTPException(409,'request key was already used for different feedback')
                return {k:old[k] for k in ('id','author','body','action','created_at')}
            superseded,_ = item_state(db,item)
            if superseded and action == 'approved':
                raise HTTPException(409,'A newer or withdrawn version exists. Ask the studio for a fresh review before approving.')
            if action != 'comment' and db.execute("SELECT 1 FROM client_review_event WHERE review_id=? AND version_id=? AND action!='comment'",(review['id'],vid)).fetchone():
                raise HTTPException(409,'A decision is already recorded for this version in this review. You can add a comment or request a new review.')
            result = dict(id=uuid4().hex,author=author,body=body,action=action,created_at=now())
            db.execute('INSERT INTO client_review_event VALUES (?,?,?,?,?,?,?,?)',(result['id'],review['id'],vid,author,body,action,result['created_at'],key))
            db.commit()
            return result

    return router
