"""Brand-owned source documents and browser font specimens.

These immutable uploads are references, not generated artwork or renderer font
installation. No endpoint accepts a filesystem path or a remote fetch URL.
"""
import base64
import binascii
from contextlib import closing
import hashlib
from pathlib import PurePath

from fastapi import APIRouter, Body, HTTPException, Response

MAX_BYTES = 32 * 1024 * 1024


def make_router(get_store):
    router = APIRouter()

    def connection(name):
        store = get_store()
        if store.get_brand_profile(name) is None:
            raise HTTPException(404, 'unknown brand')
        db = store._connect()
        db.execute('''CREATE TABLE IF NOT EXISTS identity_source (
          brand TEXT NOT NULL, id TEXT NOT NULL, filename TEXT NOT NULL,
          mime TEXT NOT NULL, font_family TEXT, data BLOB NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          PRIMARY KEY (brand, id))''')
        db.commit()
        return db

    def summary(row):
        return {k: row[k] for k in ('id', 'filename', 'mime', 'font_family', 'created_at')} | {'size': len(row['data'])}

    @router.get('/brands/{name}/sources')
    def sources(name: str):
        with closing(connection(name)) as db:
            rows = db.execute('SELECT * FROM identity_source WHERE brand=? ORDER BY created_at,id', (name,)).fetchall()
            return {'sources': [summary(r) for r in rows]}

    @router.post('/brands/{name}/sources')
    def upload(name: str, payload: dict = Body(...)):
        encoded = payload.get('data_b64')
        if not isinstance(encoded, str) or len(encoded) > (MAX_BYTES * 4 // 3 + 8):
            raise HTTPException(413, 'source must be at most 32MB')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(400, 'invalid base64 source')
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(413, 'source must be nonempty and at most 32MB')
        if data.startswith(b'%PDF-'):
            mime = 'application/pdf'
        elif data[:4] in (b'\x00\x01\x00\x00', b'true'):
            mime = 'font/ttf'
        elif data.startswith(b'OTTO'):
            mime = 'font/otf'
        else:
            raise HTTPException(422, 'supported sources are PDF, TTF and OTF')
        filename = payload.get('filename')
        if not isinstance(filename, str) or not filename.strip() or len(filename) > 255 or any(ord(c) < 32 for c in filename):
            raise HTTPException(422, 'a valid source filename is required')
        filename = PurePath(filename.replace('\\', '/')).name
        if not filename.strip() or filename in ('.', '..'):
            raise HTTPException(422, 'a valid source basename is required')
        family = payload.get('font_family') if mime.startswith('font/') else None
        if family is not None and (not isinstance(family, str) or not family.strip() or len(family) > 160):
            raise HTTPException(422, 'invalid font family')
        digest = hashlib.sha256(data).hexdigest()
        with closing(connection(name)) as db:
            db.execute('INSERT OR IGNORE INTO identity_source (brand,id,filename,mime,font_family,data) VALUES (?,?,?,?,?,?)',
                       (name, digest, filename, mime, family, data))
            db.commit()
            return summary(db.execute('SELECT * FROM identity_source WHERE brand=? AND id=?', (name,digest)).fetchone())

    @router.get('/brands/{name}/sources/{source_id}')
    def source(name: str, source_id: str):
        with closing(connection(name)) as db:
            row = db.execute('SELECT * FROM identity_source WHERE brand=? AND id=?', (name,source_id)).fetchone()
            if row is None:
                raise HTTPException(404, 'source not found for this brand')
            return Response(content=row['data'], media_type=row['mime'], headers={
                'X-Content-Type-Options': 'nosniff',
                'Cache-Control': 'private, max-age=3600',
                'Content-Security-Policy': "sandbox; default-src 'none'",
            })
    return router
