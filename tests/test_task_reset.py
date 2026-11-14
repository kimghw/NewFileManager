"""이관 1·2단계 초기화(spec_작업 ② §14 「초기화」 — app/merge_api.py `POST /api/docs/{연차보고서}/merge-links/reset`).

실제 연차보고서 서식을 올려 구분 기준을 반영(1단계)하고 2단계 기록을 merge.json 에 적어 둔 뒤:
- frame = 올린 원본으로 + 2단계 기록 지움(입력 값은 그대로)
- map   = 원본으로 되돌린 뒤 같은 값으로 구조를 다시 반영 + 2단계 기록 지움(사람이 바꿔 둔 입력 값은 그대로)"""
import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import merge_api, server, works

pytestmark = pytest.mark.skipif(not M.REPORT_FORM.exists(), reason="KEIT 연차보고서 서식 hwpx 없음")
VALS = {"stages": [2, 1], "orgs": {"lead": "인텍", "joint": ["가나대"], "nonprofit": [False, True]}}


@pytest.fixture
def client():
    server.DOCS.clear()
    merge_api._CACHE.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _report(c):
    d = c.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    assert c.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "초기화 시험"}).status_code == 200
    return d


def _frame(c, d):
    p = c.post(f"/api/docs/{d}/divisions/plan", json={"values": VALS})
    assert p.status_code == 200, p.text
    a = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": p.json()["planId"]})
    assert a.status_code == 200, a.text
    return a.json()["applied"]


def _paras(c, d):
    return [b["text"] for b in c.get(f"/api/docs/{d}").json()["blocks"] if b["type"] == "paragraph"]


def _stage2(d):
    """2단계가 쌓는 기록(자리 연결에서 고른 것 · 표 짝 · 표 대응 · LLM 검토 · 넣은 기록) + 마지막 LLM 프롬프트 파일."""
    merge_api._store(d, {"from": "aaaaaaaaaaaa", "fixed": {"g1": {"from": "f1", "source": "user"}}, "tables": {"t1": {"from": "u1", "source": "llm"}},
                         "tableMaps": {"t2": {"from": "u2"}}, "llm": {"at": "2026-11-12T10:00:00"}, "applied": {"k1": {"hash": "h", "ids": []}}, "toRev": 1, "fromRev": 0})
    merge_api._last(d, {"at": "t", "units": []})


def test_frame_reset_restores_original_and_clears_stage2(client):
    d = _report(client)
    before = _paras(client, d)
    _frame(client, d)
    assert _paras(client, d) != before
    _stage2(d)
    kept = client.get(f"/api/docs/{d}/merge-links").json()["kept"]   # 화면의 「2단계 초기화」 가 켜질지
    assert kept == {"links": 1, "tables": 1, "maps": 1, "applied": 1, "llm": True}
    r = client.post(f"/api/docs/{d}/merge-links/reset", json={"stage": "frame"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["reset"]["restored"] is True and out["reset"]["reframe"] is None
    assert {"fixed", "tables", "tableMaps", "llm", "applied", "merge_llm_last.json"} <= set(out["reset"]["cleared"])
    assert out["base"] == 0 and out["edited"] == [] and _paras(client, d) == before   # 올린 원본 그대로
    dv = client.get(f"/api/docs/{d}/divisions").json()
    assert dv["applied"] is None and dv["settings"]["values"]["orgs"]["lead"] == "인텍"   # 반영 상태는 없음 · 입력 값은 남는다
    assert merge_api._store(d) == {"from": "aaaaaaaaaaaa"} and merge_api._last(d) is None   # 사람이 고른 원본(from)은 진행이 아니라 둔다
    assert client.get(f"/api/docs/{d}/merge-links").json()["kept"] == {"links": 0, "tables": 0, "maps": 0, "applied": 0, "llm": False}
    again = client.post(f"/api/docs/{d}/merge-links/reset", json={"stage": "frame"}).json()["reset"]
    assert (again["restored"], again["cleared"]) == (False, [])   # 이미 처음 — 바뀐 것 없음
    resets = [e for e in works.events(d) if e["kind"] == "taskReset"]   # 기록(log.jsonl) — 두 번 모두
    assert [(e["stage"], e["restored"]) for e in resets] == [("frame", True), ("frame", False)]


def test_map_reset_reframes_with_same_values_and_keeps_inputs(client):
    d = _report(client)
    applied = _frame(client, d)
    framed = _paras(client, d)
    pid = next(b["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["type"] == "paragraph" and b["text"].strip())
    assert client.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "2단계가 넣은 글"}).status_code == 200   # 반영 뒤 들어간 내용·사람 고침
    assert "2단계가 넣은 글" in _paras(client, d)
    assert client.put(f"/api/docs/{d}/divisions/settings", json={"values": {**VALS, "current": 2}}).status_code == 200   # 다른 해 보고서 — 입력에서만 바꿔 둔 당해 차년도
    _stage2(d)
    r = client.post(f"/api/docs/{d}/merge-links/reset", json={"stage": "map"})
    assert r.status_code == 200, r.text
    res = r.json()["reset"]
    assert res["restored"] is True and "error" not in (res["reframe"] or {}) and res["reframe"]["summary"]["applied"]
    assert _paras(client, d) == framed   # 1단계 구조만 — 넣은 글은 없다
    dv = client.get(f"/api/docs/{d}/divisions").json()
    assert dv["applied"]["values"] == applied["values"] and dv["settings"]["values"].get("current") == 2   # 같은 값으로 다시 반영 · 입력 값은 그대로
    assert merge_api._store(d) == {"from": "aaaaaaaaaaaa"}


def test_reset_guards(client):
    d = _report(client)
    assert client.post(f"/api/docs/{d}/merge-links/reset", json={"stage": "map"}).status_code == 409   # 구조 반영 전 — 2단계만 되돌릴 수 없다
    assert client.post(f"/api/docs/{d}/merge-links/reset", json={"stage": "all"}).status_code == 400
