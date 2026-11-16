"""분석 상태(spec_작업 ② §20 — app/analysis.py · app/analysis_api.py): 문서마다 헤딩 · 표(스크립트) · LLM 판정 · 구분 기준 LLM 검토(옵션)가 어디까지 됐는지를 같은 꼴로.
읽기만 하는지(분석을 시작하지 않음) · 도는 작업의 차례(첫 분석 = 헤딩 → 표) · LLM 은 지금 결과 기준 · 문서를 고쳐도 done(뼈대 유지) · 해당 없는 항목은 없음(docx · 지원 양식 아님)."""
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import analysis, heading_runs, server

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, DOCX, FORM = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "기술수요조사서.docx", SAMPLES / "연구개발계획서_양식.hwpx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _upload(c, path=SMALL):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait_heads(c, d, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("헤딩 추출이 끝나지 않음")


def _items(v):
    return {i["key"]: i for i in v["items"]}


def _paras(blocks):
    """문단 블록을 문서 차례로(표 칸 안까지)."""
    out = []
    for b in blocks:
        if "text" in b:
            out.append(b)
        for c in b.get("cells", ()):
            out += _paras(c["blocks"])
    return out


# ---------------------------------------------------------------- 셈(가짜 세션 — 빠름)

def _sess(st, rev=3, fmt="hwpx", division=None):
    return SimpleNamespace(id="x", rev=rev, fmt=fmt, heads={"loaded": True, "runs": [], "job": None, "stage1": None, "stage2": None, "stage3": None, **st}, division=division or {})


def _job(stage=3, llm=False, first=False, status="running", error=None):
    j = heading_runs.Job(stage, llm, 3)
    j.first, j.status, j.error = first, status, error
    return j


def _res(run, rev=3, llm=None, **counts):
    return {"meta": {"run": run, "rev": rev, "at": 100.0 + run}, "counts": counts, "llm": {"requested": False, "fallback": True, "error": None, **(llm or {})}}


def test_states_are_the_documented_ones_and_nothing_means_none():
    v = analysis.status(_sess({}))
    assert v["base"] == "none" and v["job"] is None and [i["key"] for i in v["items"]] == ["heads", "tables"]
    for i in v["items"]:
        assert i["state"] == "none" and i["llm"]["state"] == "none" and i["run"] is None and i["moved"] is False and i["state"] in analysis.STATES
    assert _items(v)["heads"]["name"] == "헤딩" and _items(v)["tables"]["name"] == "표"
    assert _items(v)["heads"]["llm"]["text"] == "LLM 판정 안 함"   # 결과가 아예 없으면 「스크립트 결과」 라고 하지 않는다
    assert _items(analysis.status(_sess({"stage2": _res(2)})))["heads"]["llm"]["text"] == "LLM 판정 안 함 — 스크립트 결과"


def test_first_run_turns_heads_then_tables():
    """첫 분석 = 2단계 → 3단계를 한 작업으로: 헤딩이 도는 동안 표는 대기, 헤딩이 끝나면 표가 돈다. 이미 있는 단계는 건너뛰므로 그 항목은 done 그대로."""
    a = _items(analysis.status(_sess({"job": _job(first=True)})))
    assert (a["heads"]["state"], a["tables"]["state"]) == ("running", "wait")
    v = analysis.status(_sess({"job": _job(first=True), "stage2": _res(2, templates=4, nodes=30)}))
    b = _items(v)
    assert (b["heads"]["state"], b["tables"]["state"]) == ("done", "running") and v["base"] == "running" and v["job"]["what"] == "첫 분석" and v["job"]["first"] is True
    assert b["heads"]["text"] == "헤딩 그래프 — 실행 2 · 템플릿 4 · 헤딩 30"
    c = _items(analysis.status(_sess({"job": _job(first=True), "stage3": _res(3, tables=7, cells=90)})))   # 표만 있던 문서 — 헤딩만 뽑는다
    assert (c["heads"]["state"], c["tables"]["state"]) == ("running", "done") and c["tables"]["text"] == "표 구조 — 실행 3 · 표 7 · 칸 90"
    done = analysis.status(_sess({"job": _job(first=True, status="done"), "stage2": _res(2), "stage3": _res(3)}))
    assert done["base"] == "done" and done["job"] is None and [i["state"] for i in done["items"]] == ["done", "done"]


def test_llm_is_separate_and_follows_the_current_result():
    """LLM 판정은 기본 분석과 따로 — 결과가 있는 채 LLM 을 돌리면 헤딩은 done 그대로이고 LLM 만 도는 중. 지금 결과가 LLM 을 거쳤는지가 기준(스크립트로 다시 돌려 덮으면 none)."""
    both = {"stage2": _res(2), "stage3": _res(3)}
    a = _items(analysis.status(_sess({**both, "job": _job(stage=2, llm=True)})))
    assert a["heads"]["state"] == "done" and a["heads"]["llm"]["state"] == "running" and a["tables"]["state"] == "done" and a["tables"]["llm"]["state"] == "none"
    b = _items(analysis.status(_sess({"job": _job(stage=2, llm=True)})))   # 결과 없이 LLM 으로 — 기본도 도는 중
    assert b["heads"]["state"] == "running" and b["heads"]["llm"]["state"] == "running" and b["tables"]["state"] == "none"
    ok = _items(analysis.status(_sess({"stage2": _res(5, llm={"requested": True, "fallback": False, "applied": 80, "calls": 8, "failed": 0}), "stage3": _res(3)})))
    assert ok["heads"]["llm"] == {"state": "done", "text": "LLM 판정함 — 반영 80 · 호출 8", "error": None} and ok["tables"]["llm"]["state"] == "none"
    bad = _items(analysis.status(_sess({"stage2": _res(5, llm={"requested": True, "fallback": True, "error": "TimeoutError: x"}), "stage3": _res(3)})))
    assert bad["heads"]["state"] == "done" and bad["heads"]["llm"]["state"] == "failed" and bad["heads"]["llm"]["error"] == "TimeoutError: x"
    rerun = _items(analysis.status(_sess({**both, "job": _job(stage=3)})))   # 스크립트로 다시 — 그 항목만 도는 중
    assert (rerun["heads"]["state"], rerun["tables"]["state"], rerun["tables"]["llm"]["state"]) == ("done", "running", "none")
    stage1 = analysis.status(_sess({**both, "job": _job(stage=1)}))   # 1단계 작업(탭을 열 때 저절로)은 항목에 영향이 없다
    assert stage1["base"] == "done" and [i["state"] for i in stage1["items"]] == ["done", "done"]
    assert stage1["busy"] is True and analysis.status(_sess({"job": _job(stage=1)}))["busy"] is True   # 그래도 도는 중이라 새 분석은 못 건다 — 화면이 「분석」 단추를 감춘다
    assert analysis.status(_sess(both))["busy"] is False and analysis.status(_sess({**both, "job": _job(stage=1, status="done")}))["busy"] is False
    # LLM 실행이 예외로 끝남 — 앞 결과(스크립트)는 그대로 done, LLM 만 failed. 지금 결과가 이미 LLM 을 거친 것이면 그 판정은 유효(done)
    boom = _items(analysis.status(_sess({**both, "job": _job(stage=2, llm=True, status="failed", error="RuntimeError: api")})))
    assert boom["heads"]["state"] == "done" and boom["heads"]["llm"] == {"state": "failed", "text": "LLM 판정 실행이 실패함 — 앞 결과는 그대로", "error": "RuntimeError: api"}
    assert boom["tables"]["llm"]["state"] == "none"
    kept = _items(analysis.status(_sess({"stage2": _res(5, llm={"requested": True, "fallback": False}), "stage3": _res(3), "job": _job(stage=2, llm=True, status="failed", error="E")})))
    assert kept["heads"]["llm"]["state"] == "done"
    script_fail = _items(analysis.status(_sess({**both, "job": _job(stage=2, status="failed", error="E")})))   # 스크립트 다시 돌리기가 실패 — LLM 과 무관
    assert script_fail["heads"]["llm"]["state"] == "none"


def test_failed_only_where_the_job_stopped_and_moved_is_not_a_state():
    f = analysis.status(_sess({"job": _job(first=True, status="failed", error="ValueError: boom")}))
    a = _items(f)
    assert (a["heads"]["state"], a["heads"]["error"], a["tables"]["state"], a["tables"]["error"]) == ("failed", "ValueError: boom", "none", None)
    assert f["base"] == "failed" and f["job"]["status"] == "failed" and f["job"]["error"] == "ValueError: boom"
    b = _items(analysis.status(_sess({"job": _job(first=True, status="failed", error="E"), "stage2": _res(2)})))
    assert (b["heads"]["state"], b["tables"]["state"]) == ("done", "failed")
    c = _items(analysis.status(_sess({"job": _job(stage=3, status="failed", error="E"), "stage2": _res(2), "stage3": _res(3)})))   # 결과가 있으면 실패한 다시 돌리기는 done 그대로
    assert c["tables"]["state"] == "done" and c["tables"]["error"] is None
    moved = analysis.status(_sess({"stage2": _res(2, rev=1), "stage3": _res(3, rev=3)}, rev=3))   # 문서를 고친 뒤 — 뼈대로 남는다(done) · moved 는 도움말용
    assert moved["base"] == "done" and [(i["state"], i["moved"]) for i in moved["items"]] == [("done", True), ("done", False)]


def test_division_is_optional_and_only_when_it_applies():
    assert [i["key"] for i in analysis.status(_sess({}), division=False)["items"]] == ["heads", "tables"]
    none = _items(analysis.status(_sess({}), kind="rnd", division=True))["division"]
    assert none["optional"] is True and none["state"] == "none" and none["name"] == "구분 기준" and none["found"] == 0 and "옵션" in none["text"]
    run = _items(analysis.status(_sess({}, division={"reviewing": True}), division=True))["division"]
    assert run["state"] == "running"
    review = {"at": 9.0, "missing": {"missing": [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]}, "review": {"applied": [{"id": "h1"}]}}
    v = analysis.status(_sess({"stage2": _res(2), "stage3": _res(3)}, division={"review": review, "reviewing": False}), kind="rnd", division=True)
    d = _items(v)["division"]
    assert (d["state"], d["found"], d["applied"], d["at"]) == ("done", 3, 1, 9.0) and v["kind"] == "rnd"
    assert v["base"] == "done"   # 옵션 항목은 기본 분석 한마디에 안 든다(검토가 도는 중이어도)
    assert d["partial"] is False and d["error"] is None
    half = {"at": 9.0, "missing": None, "review": {"applied": []}, "errors": {"missing": "응답 없음"}}   # 빠진 자리 검토가 답이 없었다 — 결과는 남지만 다 본 것이 아니다
    h = _items(analysis.status(_sess({}, division={"review": half}), kind="rnd", division=True))["division"]
    assert (h["state"], h["found"], h["partial"], h["error"]) == ("done", 0, True, "빠진 자리 검토 — 응답 없음") and "답을 못 받은 검토" in h["text"]
    assert _items(analysis.status(_sess({}, division={"reviewing": True, "review": half}), division=True))["division"]["partial"] is False   # 다시 도는 중
    assert analysis.status(_sess({"stage2": _res(2), "stage3": _res(3)}, division={"reviewing": True}), division=True)["base"] == "done"
    docx = analysis.status(_sess({}, fmt="docx"), kind="general", division=True)   # 헤딩 추출은 hwpx 만 — 항목 없음
    assert docx == {"rev": 3, "format": "docx", "kind": "general", "base": "na", "busy": False, "job": None, "items": []}


# ---------------------------------------------------------------- API(실제 문서)

def test_api_reads_only_and_follows_the_first_run(client):
    """갓 올린 문서(API 로만 — 화면이 아니라 첫 분석이 안 돈다): 읽기만 해서 none 그대로. 첫 분석을 걸면 done, 문서를 고쳐도 done(moved 만 참)."""
    d = _upload(client)
    v = client.get(f"/api/docs/{d}/analysis").json()
    assert v["format"] == "hwpx" and v["base"] == "none" and v["job"] is None and v["rev"] == 0
    assert [(i["key"], i["state"], i["llm"]["state"]) for i in v["items"] if i["key"] != "division"] == [("heads", "none", "none"), ("tables", "none", "none")]
    assert client.get(f"/api/docs/{d}/headings").json()["job"] is None   # 상태를 읽어도 분석이 시작되지 않는다
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    _wait_heads(client, d)
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert v["base"] == "done" and v["job"] is None and (a["heads"]["state"], a["tables"]["state"]) == ("done", "done")
    assert (a["heads"]["run"], a["tables"]["run"]) == (2, 3) and a["heads"]["llm"]["state"] == a["tables"]["llm"]["state"] == "none" and not a["heads"]["moved"]
    assert a["heads"]["text"].startswith("헤딩 그래프 — 실행 2 · 템플릿 ") and a["tables"]["text"].startswith("표 구조 — 실행 3 · 표 ")
    doc = client.get(f"/api/docs/{d}").json()
    p = next(b for b in _paras(doc["blocks"]) if b["text"].strip())
    assert client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 고침"}).status_code == 200
    v2 = client.get(f"/api/docs/{d}/analysis").json()
    assert v2["rev"] > v["rev"] and v2["base"] == "done" and [(i["state"], i["moved"]) for i in v2["items"] if i["key"] != "division"] == [("done", True), ("done", True)]


def test_api_shows_a_running_job_then_failed_without_result(client, monkeypatch):
    d = _upload(client)
    gate, entered = threading.Event(), threading.Event()

    def slow(sess, job, use_llm=False):
        entered.set()
        gate.wait(10)
        raise RuntimeError("멈춤")
    monkeypatch.setattr(heading_runs, "run_first", slow)
    assert client.post(f"/api/docs/{d}/headings", json={"first": True}).status_code == 202
    assert entered.wait(10)
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert v["base"] == "running" and v["busy"] is True and v["job"]["status"] == "running" and v["job"]["first"] is True and (a["heads"]["state"], a["tables"]["state"]) == ("running", "wait")
    gate.set()
    _wait_heads(client, d)
    v = client.get(f"/api/docs/{d}/analysis").json()
    a = _items(v)
    assert v["base"] == "failed" and v["busy"] is False and a["heads"]["state"] == "failed" and "멈춤" in a["heads"]["error"] and a["tables"]["state"] == "none" and v["job"]["status"] == "failed"


def test_api_division_item_kind_and_docx(client):
    """구분 기준 항목 = hwpx 이고 지원 양식일 때만(문서의 성질) · kind = 작업에 적힌 작업 종류(화면이 그것으로 보일지 정한다) · docx 는 항목 없음. 404 = 없는 문서."""
    small = client.get(f"/api/docs/{_upload(client)}/analysis").json()
    assert [i["key"] for i in small["items"]] == ["heads", "tables"]   # 기술수요조사서 — 구분 기준 지원 양식이 아니다
    f = _upload(client, FORM)
    v = client.get(f"/api/docs/{f}/analysis").json()
    assert [i["key"] for i in v["items"]] == ["heads", "tables", "division"] and _items(v)["division"]["state"] == "none" and _items(v)["division"]["optional"] is True
    assert client.get(f"/api/docs/{f}").status_code == 200 and client.get(f"/api/docs/{f}/analysis").json()["kind"] == "rnd"   # 문서를 열면 양식에서 짐작한 작업 종류가 작업에 적힌다
    server.DOCS[f].division["reviewing"] = True
    assert _items(client.get(f"/api/docs/{f}/analysis").json())["division"]["state"] == "running"
    server.DOCS[f].division["reviewing"] = False
    server.DOCS[f].division["review"] = {"at": 1.0, "missing": {"missing": [{"id": "a"}]}, "review": None}
    dv = _items(client.get(f"/api/docs/{f}/analysis").json())["division"]
    assert (dv["state"], dv["found"], dv["applied"]) == ("done", 1, 0)
    x = _upload(client, DOCX)
    assert client.get(f"/api/docs/{x}/analysis").json() | {"kind": ""} == {"rev": 0, "format": "docx", "kind": "", "base": "na", "busy": False, "job": None, "items": []}
    assert client.get("/api/docs/nope/analysis").status_code == 404
