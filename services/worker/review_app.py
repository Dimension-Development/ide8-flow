"""Restricted client-review delivery surface (no studio APIs or source files).

Run alongside the private worker with the SAME WORKER_DB and a UI_DIST path:
  uvicorn review_app:build_app --factory --host 127.0.0.1 --port 8134 --no-access-log
Put only this surface behind public HTTPS. Keep the studio worker private.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from client_reviews import make_router
from store import DocStore


def create_app(store, dist):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    router=make_router(lambda:store)
    router.routes[:]=[r for r in router.routes if r.path.startswith('/client-reviews/')]
    app.include_router(router,prefix='/api')
    dist=Path(dist)

    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get('/',response_class=HTMLResponse)
    def index():
        return (dist/'index.html').read_text().replace('<html lang="en">','<html lang="en" data-review-only="true">')

    if (dist/'assets').is_dir():
        app.mount('/assets',StaticFiles(directory=dist/'assets'))
    return app


def build_app():
    repo=Path(__file__).resolve().parents[2]
    return create_app(DocStore(os.environ.get('WORKER_DB','ide8.db')),
                      os.environ.get('UI_DIST',str(repo/'services/ui/dist')))


# Uvicorn factory avoids creating an unrelated database when imported by tests.
