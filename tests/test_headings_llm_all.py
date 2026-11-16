"""LLM 판정은 스크립트가 판정하지 못한 것까지 본다(spec_헤딩_추출 ② §3, 2026-11-16 사용자 "LLM 검증 단계는 스크립트가 판정한 것과 판정하지 못한것들 모두 해야지").

2단계 LLM 실행(`heading_runs.run_stage2(use_llm=True)`)은 그래프를 짓기 전에 1단계의 못 맞춤·충돌 묶음을 규칙 보강으로 먼저 보낸다.
LLM 은 끈다(NFM_LLM_BACKEND=off) — 가짜 llm.ask_all. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS), 작업 폴더는 conftest 의 NFM_WORKS."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, llm, server, works

ROOT = Path(__file__).parents[1]
SMALL = ROOT / "samples" / "기술수요조사서.hwpx"      # 못 맞춤·충돌 0묶음
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"   # 못 맞춤 25 · 충돌 2묶음 — 「(1-1) …」 꼴 묶음 `u:(N-N)` 이 있다
GROUP, PATTERN = "u:(N-N)", r"\(\d{1,2}-\d{1,2}\)"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture
def c():
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)
    server.DOCS.clear()


def _open_ready(c, path):
    """올리고 가져오기 검증이 끝날 때까지 — 뒤 스레드가 세션을 건드리지 않게."""
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    end = time.time() + 60
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if "import" in v and not v["import"]["running"]:
            return d
        time.sleep(0.05)
    raise AssertionError("가져오기 검증이 끝나지 않음")


def _res(data=None, error=None):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": 0.0, "error": error}


def _asker(rules=None):
    """가짜 llm.ask_all — 부른 것(`what` 의 「#」 앞)을 차례로 적는다. 규칙 보강(heading_rules)에는 rules(job) 의 답(None = 실패), 나머지(그래프 A·B·C·D)는 실패 → 스크립트 대체 판정."""
    seen = []

    def ask(jobs, **kw):
        out = []
        for job in jobs:
            what = job["what"].split("#", 1)[0]
            seen.append(what)
            data = rules(job) if what == "heading_rules" and rules else None
            out.append(_res(data, None if data is not None else "가짜 실패"))
        return out
    ask.seen = seen
    return ask


def _rule_for(s1):
    """`u:(N-N)` 묶음(「(1-1) …」)을 레터로 읽는 규칙 제안 — 검증(positives · 빼앗음 검사)을 통과하는 것."""
    g = next(x for x in s1["review"]["unmatched"] if x["key"] == GROUP)
    return g, {"items": [{"group": GROUP, "decision": "rule", "name": "(N-N)", "kind": "marker", "family": "paren-hyphen", "pattern": PATTERN, "scope": "prefix",
                          "first": False, "positives": g["ids"], "negatives": ["(우)"], "globalHint": False, "reason": "번호 꼴"}], "summary": ""}


def _steps(job):
    return {s["name"]: s for s in job.view()["steps"]}


def test_llm_graph_asks_unjudged_groups_first_then_not_again(c, monkeypatch):
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    n1 = heading_runs.run_sync(s, 1, False).run
    s1 = heading_runs.state(s)["stage1"]
    g, answer = _rule_for(s1)
    assert s1["llm"] is None and all(p["kind"] == "plain" for p in s1["paras"] if p["id"] in g["ids"])  # 스크립트는 판정하지 못했다(보통 글)
    ask = _asker(lambda job: answer)
    monkeypatch.setattr(llm, "ask_all", ask)
    job = heading_runs.run_sync(s, 2, True)
    st = heading_runs.state(s)
    s1b, graph = st["stage1"], st["stage2"]
    assert ask.seen[0] == "heading_rules" and "heading_types" in ask.seen  # 판정하지 못한 묶음 먼저, 그다음 그래프(판정한 것)
    assert s1b["meta"]["run"] > n1 and graph["meta"]["stage1Run"] == s1b["meta"]["run"]  # 다시 추출한 1단계 위에 그래프
    assert len(s1b["llm"]["saved"]) == 1 and all(p["kind"] == "marker" for p in s1b["paras"] if p["id"] in g["ids"])
    assert set(g["ids"]) & {n["para"] for n in graph["nodes"]}  # 새로 레터가 된 줄이 헤딩 후보에 든다
    r = graph["llm"]["rules"]
    assert r["run"] == s1b["meta"]["run"] and r["saved"] == 1 and r["groups"] == 27 and r["error"] is None and r["left"] < 27
    step = _steps(job)["1단계 다시 — 못 맞춤·충돌 LLM 규칙 보강"]
    assert step["status"] == "ok" and "규칙 저장 1" in step["msg"]
    log = [e for e in works.events(d) if e.get("kind") == "headings" and e.get("within") == 2]
    assert len(log) == 1 and log[0]["stage"] == 1 and log[0]["llm"] is True and log[0]["n"] == r["run"]
    # 이미 답을 받은 1단계 — 남은 묶음을 다시 묻지 않는다
    ask2 = _asker(lambda job: answer)
    monkeypatch.setattr(llm, "ask_all", ask2)
    heading_runs.run_sync(s, 2, True)
    st = heading_runs.state(s)
    assert "heading_rules" not in ask2.seen and "heading_types" in ask2.seen
    assert st["stage2"]["llm"]["rules"] is None and st["stage1"]["meta"]["run"] == s1b["meta"]["run"]


def test_script_graph_never_asks_and_failed_rule_call_is_retried(c, monkeypatch):
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)

    def boom(jobs, **kw):
        raise AssertionError("스크립트 실행은 LLM 을 부르지 않는다")
    monkeypatch.setattr(llm, "ask_all", boom)
    heading_runs.run_sync(s, 2, False)
    st = heading_runs.state(s)
    assert st["stage2"]["llm"]["rules"] is None and st["stage1"]["llm"] is None
    # 보강 호출이 모두 실패해도 그래프의 LLM 판정은 이어서 한다(여기서는 그것도 실패 → 스크립트 대체) · 단계 줄에 실패로 남긴다
    ask = _asker()
    monkeypatch.setattr(llm, "ask_all", ask)
    job = heading_runs.run_sync(s, 2, True)
    st = heading_runs.state(s)
    assert job.status == "done" and ask.seen[0] == "heading_rules" and "heading_types" in ask.seen
    r = st["stage2"]["llm"]["rules"]
    assert r["error"] and r["saved"] == 0 and r["left"] == 27
    assert _steps(job)["1단계 다시 — 못 맞춤·충돌 LLM 규칙 보강"]["status"] == "failed"
    # 답을 못 받은 1단계 — 다음 LLM 판정이 다시 묻는다
    ask2 = _asker()
    monkeypatch.setattr(llm, "ask_all", ask2)
    heading_runs.run_sync(s, 2, True)
    assert ask2.seen[0] == "heading_rules"


def test_no_unjudged_groups_no_rule_call(c, monkeypatch):
    d = _open_ready(c, SMALL)
    s = server.DOCS[d]
    ask = _asker()
    monkeypatch.setattr(llm, "ask_all", ask)
    job = heading_runs.run_sync(s, 2, True)  # 1단계 결과가 없다 — 다시 뽑되 물을 묶음이 없다
    st = heading_runs.state(s)
    assert "heading_rules" not in ask.seen and st["stage2"]["llm"]["rules"] is None
    assert "판정하지 못한 묶음 없음" in _steps(job)["1단계 다시 — 못 맞춤·충돌 LLM 규칙 보강"]["msg"]
