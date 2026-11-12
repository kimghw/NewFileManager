"""같은 파일을 다시 열면 그 작업을 이어 연다(spec_작업 ② §1, 2026-11-10 사용자 확정).
같은 파일 = 이름·형식·바이트(sha256)가 모두 같음. `?new=1` 이면 늘 새 작업. 작업 폴더는 conftest 의 NFM_WORKS(시험마다 임시)."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import server, works

SAMPLES = Path(__file__).parents[1] / "samples"
HWPX, DOCX = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "기술수요조사서.docx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _upload(c, path=HWPX, name=None, new=False):
    r = c.post("/api/docs" + ("?new=1" if new else ""), files={"file": (name or path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()


def _imported(c, d, timeout=60):
    """가져오기 검증이 끝나 기록까지 남을 때까지 — 그 뒤라야 work.json 의 updated 가 더 바뀌지 않는다."""
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


def test_same_file_reopens_work(client):
    a = _upload(client)
    assert a["reused"] is False
    _imported(client, a["docId"])
    b = _upload(client)
    assert b["reused"] is True and b["docId"] == a["docId"] and b["name"] == HWPX.name
    assert set(b["work"]) >= {"created", "updated", "rev", "edited", "commits"}
    assert [w["id"] for w in works.list_works()] == [a["docId"]]
    kinds = [e["kind"] for e in client.get(f"/api/works/{a['docId']}/log").json()["events"]]
    assert kinds.count("create") == 1 and kinds.count("reupload") == 1


def test_new_flag_and_other_name_make_new_work(client):
    a = _upload(client)["docId"]
    b = _upload(client, new=True)
    assert b["reused"] is False and b["docId"] != a
    c = _upload(client, name="이름을 바꾼 조사서.hwpx")  # 바이트가 같아도 이름이 다르면 다른 파일
    assert c["reused"] is False and c["docId"] not in (a, b["docId"])
    assert len(works.list_works()) == 3


def test_reopened_work_keeps_edits_after_restart(client):
    d = _upload(client)["docId"]
    p = _first_para(client, d)
    assert client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★이어 열기"}).json()["edited"]
    server._persist_all()
    server.DOCS.clear()  # 서버를 다시 켠 것처럼 — 작업은 작업 폴더에만
    again = _upload(client)
    assert again["reused"] is True and again["docId"] == d and again["work"]["edited"] >= 1
    assert d in server.DOCS  # 열면서 작업 폴더에서 다시 올렸다
    assert _first_para(client, d)["text"].endswith("★이어 열기")


def test_reopened_work_moves_to_top(client):
    a = _upload(client)["docId"]
    _imported(client, a)
    b = client.post(f"/api/samples/{DOCX.name}").json()["docId"]
    _imported(client, b)
    assert works.list_works()[0]["id"] == b
    assert _upload(client)["docId"] == a
    assert works.list_works()[0]["id"] == a  # 최근 작업 맨 위로


def test_sample_and_upload_share_work(client):
    s = client.post(f"/api/samples/{HWPX.name}").json()
    assert s["reused"] is False
    assert client.post(f"/api/samples/{HWPX.name}").json()["docId"] == s["docId"]
    assert _upload(client)["docId"] == s["docId"]  # 예제와 같은 이름·바이트를 올려도 같은 파일
    assert client.post(f"/api/samples/{HWPX.name}?new=1").json()["docId"] != s["docId"]


def test_broken_work_falls_back_to_new(client, monkeypatch):
    a = _upload(client)["docId"]
    server.DOCS.clear()

    def boom(_):
        raise RuntimeError("못 엶")
    monkeypatch.setattr(server, "_reopen", boom)
    b = _upload(client)
    assert b["reused"] is False and b["docId"] != a


def test_works_off_always_new(client, monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    a = _upload(client)["docId"]
    b = _upload(client)
    assert b["reused"] is False and b["docId"] != a
