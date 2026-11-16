"""작업 진행 에이전트가 읽는 로그(spec_작업에이전트 ② §8 — app/work_logs.py) — 로그의 목록 · 끝 몇 줄 읽기 · 찾기 · 줄이기·가리기 · 서버 경고 모으기.
읽기만 한다(문서 · 기록을 바꾸지 않는다). LLM 은 부르지 않는다."""
import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import agent_settings, doc_agent, server, work_logs as L, works

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    doc_agent._MEMORY.clear()
    server.DOCS.clear()
    yield
    server.DOCS.clear()
    doc_agent._MEMORY.clear()


def _doc(c, task=None, name=SMALL.name):
    r = c.post("/api/docs?new=1", files={"file": (name, SMALL.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    if task:
        assert c.put(f"/api/works/{d}/task", json=task).status_code == 200
    return _settled(d)   # 배경의 가져오기 검증(PDF 출력 포함)이 끝난 뒤에 돌려준다 — 기록을 견주는 검사가 흔들리지 않고, 시험이 끝날 때 임시 폴더의 파일을 붙들고 있지 않게


def _settled(d, quiet=0.3, limit=20.0):
    """올린 뒤 배경에서 도는 가져오기 검증이 기록을 다 적을 때까지 기다린다 — 시작(`verify`)마다 끝(`verified`)이 적혔고 기록 수가 quiet 초 동안 그대로일 때까지.
    줄 수 · 기록을 견주는 검사가 그 사이에 흔들리지 않게(검증은 0.3초를 넘기도 한다 — 기록 수가 잠깐 그대로인 것만으로는 끝난 것이 아니다)."""
    end, last, since = time.time() + limit, -1, time.time()
    while time.time() < end:
        kinds = [e.get("kind") for e in works.events(d)]
        if len(kinds) != last:
            last, since = len(kinds), time.time()
        elif kinds.count("verify") <= kinds.count("verified") and time.time() - since >= quiet:
            break
        time.sleep(0.05)
    return d


def test_sources_are_the_logs_the_agent_can_read():
    assert L.NAMES == ("work", "peers", "verify", "agent", "llm", "server") and all(title and what for _, title, what in L.SOURCES)
    assert L.TITLE["work"] == "작업 기록" and set(L._READ) == set(L.NAMES)


def test_work_log_is_read_as_lines_with_find_and_caps():
    c = TestClient(server.app)
    d = _doc(c)
    works.log(d, "text", id="p1", before="가" * 300, after="비밀 sk-ant-abcdefgh12345678 값", restored=False)
    works.log(d, "divisionPlan", applied=12, summary={"errors": 0, "unresolved": 2})
    for i in range(100):
        works.log(d, "undo", i=i)
    idx = {x["log"]: x for x in L.index(d)}
    assert list(idx) == list(L.NAMES) and idx["work"]["lines"] >= 103 and idx["work"]["title"] == "작업 기록" and idx["peers"]["lines"] == 0
    got = L.read(d, "work", 500)
    assert got["log"] == "work" and got["title"] == "작업 기록" and got["total"] == idx["work"]["lines"] and len(got["lines"]) == L.N_MAX and got["lines"][-1].endswith("undo i=99")   # 한 번에 80줄까지 · 끝에서부터
    plan = L.read(d, "work", 5, "divisionplan")
    assert plan["total"] == 1 and "divisionPlan applied=12" in plan["lines"][0] and '"unresolved":2' in plan["lines"][0] and plan["find"] == "divisionplan"   # 찾기는 대소문자를 가리지 않는다
    text = L.read(d, "work", 5, " text ")["lines"][0]
    assert "sk-ant-abcdefgh12345678" not in text and "sk-…" in text and "가" * 41 not in text and len(text) <= L.LINE   # 키처럼 보이는 글은 가리고 문단 글은 줄인다
    assert len(L.recent(d)) == L.RECENT and L.recent(d)[-1].endswith("undo i=99")
    bad = L.read(d, "nope", 5)
    assert bad["log"] == "nope" and "그런 로그가 없습니다" in bad["error"] and "work" in bad["error"]
    assert L.read(d, "work", "x")["lines"] and len(L.read(d, "work", 0)["lines"]) == 1   # 줄 수가 꼴이 아니면 기본 · 1 보다 작으면 1
    assert L.read("nope-work", "work")["lines"] == [] and [x["lines"] for x in L.index("nope-work")][:4] == [0, 0, 0, 0]   # 없는 작업 — 빈 로그(오류 아님)


def test_peers_are_the_other_documents_of_the_same_project_task_and_round():
    c = TestClient(server.app)
    task = {"kind": "rnd", "job": "plan_to_report", "project": "수소선박", "round": 1}
    a = _doc(c, {**task, "file": "report"}, "연차보고서.hwpx")
    b = _doc(c, {**task, "file": "plan"}, "사업계획서.hwpx")
    other = _doc(c, {**task, "file": "plan", "project": "다른 과제"}, "남의 문서.hwpx")
    works.log(b, "headings", stage=2)
    works.log(other, "headings", stage=3)
    lines = L.read(a, "peers", 80)["lines"]
    assert lines and all("[사업계획서" in x for x in lines) and any(" headings stage=2" in x for x in lines) and not any("남의 문서" in x or "stage=3" in x for x in lines)
    assert L.read(_doc(c, None, "혼자.hwpx"), "peers")["lines"] == []   # 프로젝트 · TASK 가 없으면 함께 쓰는 문서도 없다


def test_agent_turns_llm_runs_and_server_warnings_are_logs_too():
    c = TestClient(server.app)
    d = _doc(c, {"kind": "", "file": "plan", "job": "plan_fit", "project": ""})
    t = c.post(f"/api/docs/{d}/agent/guide", json={"event": "start", "steps": [{"name": "준비", "state": "done"}], "actions": [{"name": "plan", "label": "변경 계획 보기", "primary": True}]}).json()["turn"]
    c.put(f"/api/docs/{d}/agent/guide/{t['id']}", json={"state": "done", "outcome": "실행함 — 맞출 자리 12"})
    row = L.read(d, "agent")["lines"][-1]
    assert t["id"] in row and "사건=start" in row and "행동=plan" in row and "끝=done(「실행함 — 맞출 자리 12」)" in row and "스크립트 답" in row
    assert any(" agentGuide " in x for x in L.read(d, "work")["lines"])
    agent_settings.reset_runs()
    agent_settings.record("work-guide", {"model": "m", "effort": "low", "backend": "api", "ms": 12, "costUsd": 0.002, "error": "시간 초과", "data": None})
    run = L.read(d, "llm")["lines"]
    assert len(run) == 1 and "work_guide(work-guide)" in run[0] and "12ms" in run[0] and "$0.002" in run[0] and "답 없음" in run[0] and "오류=시간 초과" in run[0]
    agent_settings.reset_runs()
    L.install()
    L.install()   # 여러 번 불러도 듣는 이는 하나
    assert sum(1 for h in logging.getLogger().handlers if h is L._KEEP) == 1 and sum(1 for h in logging.getLogger("uvicorn").handlers if h is L._KEEP) == 1
    before = len(L.read(d, "server", 80, "work-logs-test")["lines"])
    log = logging.getLogger("app.test_work_logs")
    log.info("work-logs-test 정보는 안 모은다")
    log.warning("work-logs-test 경고 %s", "하나")
    try:
        raise ValueError("work-logs-test 깨짐")
    except ValueError:
        log.exception("work-logs-test 오류")
    got = L.read(d, "server", 80, "work-logs-test")["lines"]
    assert len(got) == before + 2 and "WARNING app.test_work_logs — work-logs-test 경고 하나" in got[-2] and "ERROR" in got[-1] and "ValueError: work-logs-test 깨짐" in got[-1]


def test_reading_logs_changes_nothing():
    c = TestClient(server.app)
    d = _doc(c)
    before = (works.events(d), works.work(d))
    L.index(d)
    for name in L.NAMES:
        L.read(d, name, 80)
    assert (works.events(d), works.work(d)) == before
