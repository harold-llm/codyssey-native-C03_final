"""Vercel Function 진입점 — FastAPI(ASGI) 껍질이 backend.dispatch()에 위임.

브라우저 요청이 전부 이 함수로 들어온다:
  - /api/...  → backend.dispatch() (JSON API)
  - 그 외     → 루트 정적 파일 (index.html, style.css, app.js) — SPA 폴백 포함
    (정적 파일도 dispatch가 서빙해서, 로컬 표준라이브러리 서버와 동작이 1:1 동일)

로컬 실행:  ./.venv/bin/python -m uvicorn api.index:app --port 8000
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi import FastAPI, Request, Response  # noqa: E402

import main as bloomy  # noqa: E402
import store  # noqa: E402


async def _parse_body(request: Request):
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


def _jsonable(o):
    """Postgres는 created_at 등에 datetime 객체를 돌려서 JSON 직렬화가 깨진다.
    모든 응답을 isoformat 문자열로 정규화한다 (SQLite 문자열은 그대로)."""
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (dt.datetime, dt.date, dt.time)):
        return o.isoformat()
    return o


def _respond(code, payload, ctype):
    if ctype == bloomy.JSON and isinstance(payload, (dict, list)):
        payload = json.dumps(_jsonable(payload), ensure_ascii=False).encode("utf-8")
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return Response(content=payload or b"", status_code=code, media_type=ctype)


def _run(request: Request, path_with_slash: str, body):
    full = path_with_slash
    if request.url.query:
        full += "?" + request.url.query
    code, payload, ctype = bloomy.dispatch(
        request.method, full, request.headers, body
    )
    return _respond(code, payload, ctype)


app = FastAPI(title="Bloomy", docs_url=None, redoc_url=None)
app.router.routes.clear()


@app.on_event("startup")
def _startup():
    store.init()
    import catalog

    catalog.load()


@app.api_route("/", methods=["GET", "POST"], include_in_schema=False)
async def _root(request: Request):
    body = await _parse_body(request) if request.method == "POST" else None
    return _run(request, "/", body)


@app.api_route("/{path:path}", methods=["GET", "POST"], include_in_schema=False)
async def _catch_all(request: Request, path: str):
    body = await _parse_body(request) if request.method == "POST" else None
    return _run(request, "/" + path, body)
