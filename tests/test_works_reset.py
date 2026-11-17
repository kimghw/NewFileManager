"""같은 파일은 묻고 연다(spec_작업 ② §1 「같은 파일은 묻고 연다」) · 작업 내용 초기화(② §3-1) — 2026-11-18 사용자
"파일이 같으면 그냥 새프로젝트로 할건지 기존 프로젝트 이어서 할건지 물어봐주고, 작업한 내용 초기화 하는 기능도 넣어줘."
작업 폴더는 conftest 의 NFM_WORKS(시험마다 임시)."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_forms, server, works

SAMPLES = Path(__file__).parents[1] / "samples"
HWPX = SAMPLES / "기술수요조사서.hwpx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _post(c, query="", name=None):
    return c.post("/api/docs" + query, files={"file": (name or HWPX.name, HWPX.read_bytes())})


def _upload(c, query=""):
    r = _post(c, query)
    assert r.status_code == 200, r.text
    return r.json()


def _imported(d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if any(r["kind"] == "import" for r in works.runs(d)):
            return
        time.sleep(0.05)
    raise AssertionError("가져오기 검증이 끝나지 않음")


def _first_para(c, d):
    stack = list(c.get(f"/api/docs/{d}").json()["blocks"])
    while stack:
        b = stack.pop(0)
        if b["type"] == "paragraph" and b["text"].strip():
            return b
        stack[:0] = [x for cell in b.get("cells", ()) for x in cell["blocks"]]
    raise AssertionError("글이 있는 문단이 없음")


def _edit(c, d, tail):
    p = _first_para(c, d)
    assert c.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + tail}).json()["edited"]
    return p


# ---- 같은 파일 고르기(② §1) ---------------------------------------------------------------------------------

def test_ask_without_same_file_makes_new_work(client):
    r = _upload(client, "?ask=1")
    assert r.get("ask") is None and r["reused"] is False
    assert [w["id"] for w in works.list_works()] == [r["docId"]]


def test_ask_lists_same_works_and_opens_nothing(client):
    a = _upload(client)["docId"]
    _imported(a)
    _edit(client, a, "★묻기")
    server._persist_all()
    r = _upload(client, "?ask=1")
    assert r["ask"] is True and r["name"] == HWPX.name and "docId" not in r
    assert [x["id"] for x in r["same"]] == [a]
    row = r["same"][0]
    assert set(row) >= {"id", "name", "task", "created", "updated", "rev", "edited", "commits", "open"} and row["edited"] >= 1
    assert len(works.list_works()) == 1  # 묻기만 — 새 작업을 만들지 않는다
    kinds = [e["kind"] for e in client.get(f"/api/works/{a}/log").json()["events"]]
    assert "reupload" not in kinds


def test_ask_orders_rows_by_job_then_empty(client):
    a = _upload(client)["docId"]
    b = _upload(client, "?new=1")["docId"]
    c = _upload(client, "?new=1")["docId"]
    assert client.put(f"/api/works/{a}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": ""}).status_code == 200
    assert client.put(f"/api/works/{c}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": ""}).status_code == 200
    rows = [x["id"] for x in _upload(client, "?ask=1&job=plan_fit")["same"]]
    assert rows[0] == a and rows[1] == b and rows[2] == c  # 그 TASK → TASK 빈 작업 → 그 밖


def test_use_opens_the_picked_work(client):
    a = _upload(client)["docId"]
    b = _upload(client, "?new=1")["docId"]
    r = _upload(client, f"?use={a}")
    assert r["reused"] is True and r["docId"] == a
    kinds = [e["kind"] for e in client.get(f"/api/works/{a}/log").json()["events"]]
    assert kinds.count("reupload") == 1
    assert _upload(client, f"?use={b}")["docId"] == b


def test_use_refuses_a_work_of_another_file(client):
    other = _post(client, name="다른 이름.hwpx").json()["docId"]  # 바이트가 같아도 이름이 다르면 다른 파일
    r = _post(client, f"?use={other}")
    assert r.status_code == 409
    assert len(works.list_works()) == 1


def test_ask_and_new_makes_new_work(client):
    a = _upload(client)["docId"]
    r = _upload(client, "?ask=1&new=1")
    assert r["reused"] is False and r["docId"] != a


# ---- 작업 내용 초기화(② §3-1) ---------------------------------------------------------------------------------

def test_reset_returns_to_original_and_moves_results(client):
    d = _upload(client)["docId"]
    _imported(d)
    p = _edit(client, d, "★초기화 전")
    heading_forms.set_choice(d, "")  # 양식 선택(「양식 없음으로 고정」) — 초기화 뒤에도 남는다
    server._persist_all()
    before = works.work(d)
    folder = works.folder(d)
    assert (folder / "state.json").is_file()

    r = client.post(f"/api/works/{d}/reset")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["reset"] == {"n": 1, "archive": "reset/1", "commit": None, "skipped": []}
    assert j["editedCount"] == 0 and j["edited"] == []
    assert _first_para(client, d)["text"] == p["text"]
    after = works.work(d)
    assert after["id"] == d and after["created"] == before["created"] and after["edited"] == 0
    assert after["rev"] > before["rev"]  # 편집 차례는 이어 센다
    assert (folder / "reset" / "1" / "state.json").is_file() and (folder / "reset" / "1" / "verify").is_dir()
    assert (folder / f"original.{after['format']}").is_file() and (folder / "log.jsonl").is_file()
    assert heading_forms.choice(d) == ""
    ev = [e for e in works.events(d) if e["kind"] == "reset"]
    assert len(ev) == 1 and ev[0]["archive"] == "reset/1" and "state.json" in ev[0]["moved"]
    assert any(e["kind"] == "create" for e in works.events(d))  # 작업 기록은 남는다
    _imported(d)  # 다시 연 작업에서 가져오기 검증이 다시 돈다


def test_reset_closed_work_and_second_reset(client):
    d = _upload(client)["docId"]
    _imported(d)
    _edit(client, d, "★닫힌 작업")
    server._persist_all()
    server.DOCS.clear()  # 서버를 다시 켠 것처럼
    assert client.post(f"/api/works/{d}/reset").json()["reset"]["n"] == 1
    _imported(d)
    _edit(client, d, "★두 번째")
    server._persist_all()
    j = client.post(f"/api/works/{d}/reset").json()
    assert j["reset"]["archive"] == "reset/2" and j["editedCount"] == 0
    _imported(d)


def test_reset_with_commits_adds_restore_commit(client):
    d = _upload(client)["docId"]
    _imported(d)
    p = _edit(client, d, "★확정")
    c = client.post(f"/api/docs/{d}/commits", json={"message": "하나"})
    assert c.status_code == 200, c.text
    _imported(d)
    _edit(client, d, "★확정 뒤")
    server._persist_all()
    j = client.post(f"/api/works/{d}/reset").json()
    assert j["reset"]["commit"] == 2 and j["base"] == 2 and j["editedCount"] == 0
    assert _first_para(client, d)["text"] == p["text"]  # 올린 원본의 글
    cs = client.get(f"/api/docs/{d}/commits").json()["commits"]
    assert [x["n"] for x in cs] == [2, 1, 0]  # 확정 기록은 남고 초기화가 하나 더함
    assert cs[0]["restoreOf"] == 0 and "초기화" in cs[0]["message"]
    server.DOCS.clear()
    assert client.get(f"/api/docs/{d}").json()["base"] == 2  # 다시 열어도 그 기준
    _imported(d)


def test_reset_keeps_project_settings(client):
    d = _upload(client)["docId"]
    _imported(d)
    s = server.DOCS[d]
    s.division["settings"] = {"values": {"stages": 1}}
    s.division["confirmed"] = {"at": 1, "hash": "x", "values": {"stages": 1}}
    s.division["applied"] = {"rev": 1}
    s.rev += 1
    server._persist_all()
    assert client.post(f"/api/works/{d}/reset").status_code == 200
    s2 = server.DOCS[d]
    assert s2 is not s
    assert s2.division["settings"] == {"values": {"stages": 1}} and s2.division["confirmed"]["hash"] == "x"
    assert s2.division["applied"] is None and s2.division["prior"] == []
    _imported(d)


def test_reset_refuses_while_heading_job_runs(client):
    d = _upload(client)["docId"]
    _imported(d)

    class Running:
        status = "running"

    server.DOCS[d].heads = {"job": Running()}
    r = client.post(f"/api/works/{d}/reset")
    assert r.status_code == 409 and "도는 중" in r.json()["detail"]
    assert not (works.folder(d) / "reset").exists()
    server.DOCS[d].heads = None


def test_reset_unknown_work_is_404(client):
    assert client.post("/api/works/0123456789ab/reset").status_code == 404
