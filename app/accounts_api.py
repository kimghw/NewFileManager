"""계정의 로그인 문 · 끝점 · 페이지(spec_계정 ② §2 · §4) — server.py 가 `include_router(router)` · `add_middleware(Gate)` 로 붙인다(server 를 가져오지 않는다).
저장 · 해시 · 쿠키 값은 app/accounts.py.

- `Gate` = 순수 ASGI 미들웨어(http · websocket). env `NFM_AUTH=1` 일 때만 문이 선다(안 걸면 그대로 지나간다 — 시험 · 화면 검사 · 임시 서버).
  요청의 계정 = 쿠키 `nfm_auth` → 없으면 **이 PC 안에서 바로 온 요청**(상대 127.0.0.1 · `X-Forwarded-For` 없음 — 바깥 요청은 Caddy 가 그 머리말을 늘 붙인다)은 관리자.
  계정이 없으면: 열린 길(`OPEN`)은 지나가고 · 페이지는 `/login?next=` · API 는 401(머리말 `X-Login: required` — 화면 chip.js 가 그것을 보고 로그인으로 보낸다) · 웹소켓은 닫음.
  계정이 있으면: 그 요청을 **그 계정의 작업 폴더 뿌리**에서 돌린다(`works.ACCOUNT` — 관리자는 None = 전의 뿌리: ② §3) · 주소의 작업 id 가 제 것이 아니면 404 · `ADMIN_ONLY` 는 관리자만.
- `GET /login` · `GET /account` = 페이지(app/static/account/).
- `GET /api/account/me` → {on, name|null, admin, local, pending?(관리자 — 승인 대기 수)}
- `POST /api/account/login` {name, password} → {name, admin} + 쿠키 · 401 = 틀림 · 403 = 승인 대기 · 막음 · 429 = 틀린 비밀번호가 잇따름
- `POST /api/account/join` {name, password} → 201 {name, state: pending} · 400 = 꼴 · 409 = 있는 이름 · 429 = 승인 대기가 너무 많음
- `POST /api/account/logout` · `POST /api/account/password` {old, new}
- 관리자: `GET /api/account/users` · `PUT /api/account/users/{name}` {state?, password?} · `DELETE /api/account/users/{name}`(계정만 — 작업 폴더는 그대로)."""
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app import accounts as A
from app import works

router = APIRouter()
COOKIE = "nfm_auth"
PAGES = Path(__file__).with_name("static") / "account"
OPEN = ("/login", "/api/account/login", "/api/account/join", "/api/account/me", "/static/")   # 로그인 없이 열리는 길(정적 파일 = 화면 코드 — 사용자 자료가 아니다)
ADMIN_ONLY = ("/api/flow/active",)   # 모든 계정의 도는 실행(8114 를 다시 켜기 전에 보는 것)
FAIL_MAX, FAIL_WINDOW, PENDING_MAX = 5, 300, 50
_WORK = re.compile(r"^/api/(?:docs|works)/([0-9a-f]{12})(?:/|$)")   # 작업 id 가 든 주소(works.ID 의 꼴)
_fails: dict[str, list[float]] = {}


def on() -> bool:
    return os.environ.get("NFM_AUTH", "").strip().lower() in ("1", "on", "true")


def _cookie(header) -> str | None:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE:
            return v
    return None


def _account(scope, headers) -> dict | None:
    u = A.who(_cookie(headers.get("cookie")))
    if u is None and (scope.get("client") or ("",))[0] in ("127.0.0.1", "::1") and "x-forwarded-for" not in headers:
        u = {"name": A.ADMIN, "admin": True, "local": True}   # 이 PC 안의 도구 · 확인 절차 — 프록시(Caddy)를 거친 요청에는 그 머리말이 늘 있다
    return u


class Gate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket") or not on():
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers") or ()}
        user = _account(scope, headers)
        if user is None and not path.startswith(OPEN):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            elif scope.get("method") == "GET" and not path.startswith("/api/"):
                qs = scope.get("query_string", b"").decode("latin-1")
                await RedirectResponse("/login?next=" + quote(path + ("?" + qs if qs else ""), safe=""), 302)(scope, receive, send)
            else:
                await JSONResponse({"detail": "로그인이 필요합니다"}, 401, headers={"X-Login": "required"})(scope, receive, send)
            return
        scope["account"] = user
        who = user["name"] if user and not user["admin"] else None
        token = works.ACCOUNT.set(who)
        try:
            deny = None
            if who and path.startswith(ADMIN_ONLY):
                deny = (403, "관리자만 볼 수 있습니다")
            m = _WORK.match(path) if who else None
            if m and not ((d := works.folder(m.group(1))) and d.is_dir()):
                deny = (404, "그런 작업이 없습니다")   # 남의 작업 id = 없는 작업(메모리에 열려 있어도)
            if deny is None:
                await self.app(scope, receive, send)
            elif scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": deny[1]}, deny[0])(scope, receive, send)
        finally:
            works.ACCOUNT.reset(token)


def _page(name):
    return Response((PAGES / name).read_text(encoding="utf-8"), media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@router.get("/login")
def login_page():
    return _page("login.html")


@router.get("/account")
def account_page():
    return _page("account.html")


def _me(request) -> dict:
    u = request.scope.get("account")
    if u is None:
        raise HTTPException(403, "로그인한 계정이 없습니다")
    return u


def _admin(request) -> dict:
    u = _me(request)
    if not u["admin"]:
        raise HTTPException(403, "관리자만 할 수 있습니다")
    return u


def _store(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except KeyError as exc:
        raise HTTPException(404, "그런 계정이 없습니다") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _signed(request, body, name):
    resp = JSONResponse(body)
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
    resp.set_cookie(COOKIE, A.token(name), max_age=A.TOKEN_DAYS * 86400, httponly=True, samesite="lax", secure=https, path="/")
    return resp


@router.get("/api/account/me")
def me(request: Request):
    u = request.scope.get("account")
    if not on() or u is None:
        return {"on": on(), "name": None}
    out = {"on": True, "name": u["name"], "admin": u["admin"], "local": bool(u.get("local"))}
    if u["admin"]:
        out["pending"] = sum(x["state"] == "pending" for x in A.users())
    return out


@router.post("/api/account/login")
def login(request: Request, body: dict = Body(...)):
    name, now = str(body.get("name") or "").strip().lower(), time.time()
    recent = [t for t in _fails.get(name, ()) if now - t < FAIL_WINDOW]
    if len(recent) >= FAIL_MAX:
        raise HTTPException(429, "비밀번호가 여러 번 틀렸습니다 — 5분 뒤에 다시 해 보세요")
    u = _store(A.verify, name, body.get("password"))
    if u is None:
        if len(_fails) > 1000:   # 없는 이름으로 두드리는 요청이 표를 불리지 않게
            _fails.clear()
        _fails[name] = [*recent, now]
        raise HTTPException(401, "이름이나 비밀번호가 맞지 않습니다")
    _fails.pop(name, None)
    if u["state"] != "approved":
        raise HTTPException(403, "관리자의 승인을 기다리는 중입니다" if u["state"] == "pending" else "막힌 계정입니다 — 관리자에게 문의하세요")
    return _signed(request, {"name": u["name"], "admin": u["admin"]}, name)


@router.post("/api/account/join", status_code=201)
def join(body: dict = Body(...)):
    if sum(x["state"] == "pending" for x in A.users()) >= PENDING_MAX:
        raise HTTPException(429, "승인을 기다리는 신청이 너무 많습니다 — 관리자에게 문의하세요")
    name = body.get("name").strip().lower() if isinstance(body.get("name"), str) else None
    try:
        return A.join(name, body.get("password"))
    except KeyError as exc:
        raise HTTPException(409, "이미 있는 이름입니다") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/account/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.post("/api/account/password")
def password(request: Request, body: dict = Body(...)):
    u = _me(request)
    if A.verify(u["name"], body.get("old")) is None:
        raise HTTPException(403, "지금 비밀번호가 맞지 않습니다")
    _store(A.change, u["name"], password=body.get("new"))
    return _signed(request, {"ok": True}, u["name"])   # 비밀번호가 바뀌면 앞의 쿠키는 풀린다 — 이 화면은 새 쿠키로 잇는다


@router.get("/api/account/users")
def users(request: Request):
    _admin(request)
    return {"users": _store(A.users)}


@router.put("/api/account/users/{name}")
def user_change(name: str, request: Request, body: dict = Body(...)):
    _admin(request)
    return _store(A.change, name, state=body.get("state"), password=body.get("password"))


@router.delete("/api/account/users/{name}")
def user_remove(name: str, request: Request):
    _admin(request)
    _store(A.remove, name)
    return {"ok": True}
