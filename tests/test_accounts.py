"""계정(spec_계정) — 가입 · 승인 · 로그인 문 · 계정마다 따로인 작업."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import accounts, accounts_api, works
from app.server import DOCS, app

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "기술수요조사서.docx"


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_AUTH", "1")
    monkeypatch.setenv("NFM_ACCOUNTS", str(tmp_path / "accounts.json"))
    yield
    DOCS.clear()
    accounts_api._fails.clear()


def _login(name, password, expect=200):
    c = TestClient(app)   # 클라이언트마다 쿠키가 따로 — 계정 하나
    r = c.post("/api/account/login", json={"name": name, "password": password})
    assert r.status_code == expect, r.text
    return c


def _member(name):
    assert TestClient(app).post("/api/account/join", json={"name": name, "password": "pw-" + name}).status_code == 201
    accounts.change(name, state="approved")
    return _login(name, "pw-" + name)


def _upload(c):
    r = c.post("/api/docs", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_gate_off_is_as_before():
    c = TestClient(app)
    assert c.get("/api/works").status_code == 200
    assert c.get("/api/account/me").json() == {"on": False, "name": None}


def test_no_login_is_turned_away(gate):
    c = TestClient(app)
    assert c.get("/api/works").status_code == 401 and c.get("/api/works").headers["X-Login"] == "required"
    r = c.get("/workflow?x=1", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login?next=%2Fworkflow%3Fx%3D1"
    assert c.get("/login").status_code == 200 and c.get("/static/account/login.js").status_code == 200
    assert c.get("/api/account/me").json() == {"on": True, "name": None}
    with pytest.raises(Exception):   # 웹소켓도 닫는다
        with c.websocket_connect("/api/docs/000000000000/pointer"):
            pass


def test_join_waits_for_approval(gate):
    anon = TestClient(app)
    assert anon.post("/api/account/join", json={"name": "Kim_1", "password": "abcd"}).json()["state"] == "pending"   # 이름은 소문자로
    assert anon.post("/api/account/join", json={"name": "kim_1", "password": "abcd"}).status_code == 409
    assert anon.post("/api/account/join", json={"name": "../x", "password": "abcd"}).status_code == 400
    assert anon.post("/api/account/join", json={"name": "lee", "password": "abc"}).status_code == 400
    _login("kim_1", "abcd", 403)   # 승인 전
    admin = _login("sscb", "sscb")   # 관리자는 처음부터 있다
    assert admin.get("/api/account/me").json()["pending"] == 1
    assert admin.put("/api/account/users/kim_1", json={"state": "approved"}).json()["state"] == "approved"
    kim = _login("kim_1", "abcd")
    assert kim.get("/api/account/me").json() == {"on": True, "name": "kim_1", "admin": False, "local": False}
    assert kim.get("/api/account/users").status_code == 403 and kim.get("/api/flow/active").status_code == 403
    assert admin.get("/api/flow/active").status_code == 200
    admin.put("/api/account/users/kim_1", json={"state": "blocked"})
    assert kim.get("/api/works").status_code == 401   # 막으면 바로 풀린다
    assert admin.put("/api/account/users/sscb", json={"state": "blocked"}).status_code == 400
    assert admin.delete("/api/account/users/kim_1").status_code == 200 and admin.delete("/api/account/users/kim_1").status_code == 404


def test_wrong_password_is_throttled(gate):
    for _ in range(5):
        _login("sscb", "nope", 401)
    _login("sscb", "sscb", 429)


def test_password_change_drops_other_logins(gate):
    a, b = _login("sscb", "sscb"), _login("sscb", "sscb")
    assert a.post("/api/account/password", json={"old": "bad", "new": "longer-pw"}).status_code == 403
    assert a.post("/api/account/password", json={"old": "sscb", "new": "longer-pw"}).status_code == 200
    assert a.get("/api/works").status_code == 200 and b.get("/api/works").status_code == 401
    _login("sscb", "longer-pw")


def test_works_and_projects_are_per_account(gate):
    kim, lee, admin = _member("kim"), _member("lee"), _login("sscb", "sscb")
    wid = _upload(kim)
    assert (works._base() / works.ACCOUNTS_DIR / "kim" / wid).is_dir()
    assert [w["id"] for w in kim.get("/api/works").json()] == [wid]
    assert lee.get("/api/works").json() == [] and admin.get("/api/works").json() == []
    assert kim.get(f"/api/docs/{wid}").status_code == 200
    assert lee.get(f"/api/docs/{wid}").status_code == 404   # 메모리에 열려 있어도 남의 작업은 없는 작업
    assert lee.put(f"/api/works/{wid}/alias", json={"alias": "x"}).status_code == 404
    assert admin.get(f"/api/docs/{wid}").status_code == 200   # 관리자는 id 로 연다
    assert kim.post("/api/projects", json={"name": "과제"}).status_code == 200
    assert lee.post("/api/projects", json={"name": "과제"}).status_code == 200   # 계정이 다르면 같은 이름도 따로
    assert [p["name"] for p in admin.get("/api/projects").json()["projects"]] == []
    mine = _upload(lee)
    assert _upload(lee) == mine and mine != wid   # 같은 파일 찾기도 제 뿌리만


def test_background_thread_finds_any_account_work(gate):
    wid = _upload(_member("kim"))
    assert works.ACCOUNT.get() is None and works.work(wid)["id"] == wid   # 맥락 없는 곳(작업 저장 스레드)은 id 로 찾는다
    token = works.ACCOUNT.set("lee")
    try:
        assert works.work(wid) is None
    finally:
        works.ACCOUNT.reset(token)
