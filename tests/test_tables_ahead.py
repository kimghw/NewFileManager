"""큰 문서의 병렬 판정(spec_헤딩_추출 ② §8 「헤딩 판정과 같이」 · spec_작업 ② §20 — 2026-11-17 사용자 "문서가 큰 경우 병렬에이전트를 사용해서 판정 및 실행을 할 수 있도록").

「LLM 검증·보완」 은 헤딩 판정(2단계 LLM)이 도는 동안 표 판정의 호출(T)을 같이 돌린다 — T 호출은 1단계 결과에만 기대므로 규칙 보강이 끝나면 바로 묻고,
헤딩 그래프가 끝난 뒤 받은 답에 표의 소속을 붙여 맺는다(heading_runs.TablesAhead · heading_tables.ask_tables / build(asked=…) · analysis_llm.run).
LLM 은 끈다(NFM_LLM_BACKEND=off) — 가짜 llm.ask_all. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS)."""
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import analysis_llm, heading_runs, llm, server
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app import heading_tables as HT

ROOT = Path(__file__).parents[1]
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"   # 못 맞춤·충돌 27묶음 · 여러 칸 표 여럿


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


def _table_ids(job):
    return [t["table"] for t in json.loads(job["content"].split("## 자료(JSON)\n", 1)[1])["tables"]]


def _asker(types_ok=True, on_types=None):
    """가짜 llm.ask_all — 일어난 일을 차례로 적는다(`ask:<무엇>` · `done:<무엇>`). 규칙 보강은 실패(그래프는 이어서 한다) · 유형 판정(A)은 types_ok 면 빈 답(= LLM 을 거침),
    구간 검토(B)는 바꿀 것 없음 · 표 판정(T)은 표마다 요약만 적은 답. **유형 판정은 표 판정 호출이 시작될 때까지 기다린다** — 표 판정이 헤딩 판정을 기다리면 여기서 시간 초과로 떨어진다."""
    log, tables_in = [], threading.Event()

    def ask(jobs, **kw):
        out = []
        for i, job in enumerate(jobs):
            what = job["what"].split("#", 1)[0]
            log.append(f"ask:{what}")
            if what == "heading_tables":
                tables_in.set()
                # 띠는 초안 그대로 적는다(계약 「초안이 맞으면 초안 영역을 그대로」) — 빈 subtables + 빈 cells 는 「하나도 받아들이지 못한 답」 이라 판정으로 세지 않는다(heading_tables._settle — astra 결과 검토 P1-11:
                # 이 가짜 답이 그 규칙보다 먼저 쓰여 빈 띠였다. 2026-11-24 전체 시험부터 떨어져 있던 것을 2026-11-26 고침)
                tabs = json.loads(job["content"].split("## 자료(JSON)\n", 1)[1])["tables"]
                data = {"tables": [{"table": tp["table"], "subtables": [{"sub": b["id"], "rows": b["rows"], "cols": b["cols"], "kind": b["kind"], "headerRows": -1, "headerCols": -1, "note": ""}
                                                                        for b in tp["draft"]], "cells": [], "summary": "가짜 요약"} for tp in tabs], "summary": "표 묶음"}
            elif what == "heading_types":
                assert tables_in.wait(60), "헤딩 판정(유형 판정)이 도는 동안 표 판정 호출이 시작되지 않음"
                if on_types:
                    on_types()
                data = {"types": [], "mainChain": [], "summary": "가짜"} if types_ok else None
            elif what == "heading_section":
                data = {"changes": [], "summary": ""}
            else:
                data = None
            log.append(f"done:{what}")
            out.append(_res(data, None if data is not None else "가짜 실패"))
            if kw.get("progress"):
                kw["progress"](i + 1, len(jobs))
        return out
    ask.log = log
    return ask


def _chain(s):
    """기본 분석(스크립트)을 마친 문서의 「LLM 검증·보완」 작업."""
    heading_runs.run_sync(s, 2, False)
    heading_runs.run_sync(s, 3, False)
    job = heading_runs.Job(2, True, s.rev)
    job.chain = "llm"
    heading_runs.state(s)["job"] = job
    return job


def _run(s, job):
    return analysis_llm.run(s, job, outline=lambda x: None, plans=lambda x, g: {}, plan=lambda x, tid: None)


def _parts(job):
    return [(p["key"], p["no"], p["status"]) for p in job.parts]


def test_table_calls_run_alongside_heading_judgment(c, monkeypatch):
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    job = _chain(s)
    ask = _asker()
    monkeypatch.setattr(llm, "ask_all", ask)
    n = _run(s, job)
    st = heading_runs.state(s)
    s1, s2, s3 = st["stage1"], st["stage2"], st["stage3"]
    log = ask.log
    # 표 판정 호출은 규칙 보강 뒤 · 유형 판정이 끝나기 전에 시작한다(헤딩 판정을 기다리지 않는다) · 한 번만 묻는다
    assert log.index("ask:heading_rules") < log.index("ask:heading_tables") < log.index("done:heading_types")
    asked = log.count("ask:heading_tables")
    assert asked >= 1 and s3["llm"]["calls"] == asked and s3["llm"]["failed"] == 0
    # 받은 답으로 맺은 표 구조 — LLM 을 거침 · 소속은 새 헤딩 그래프에서 · 같은 1단계
    assert s3["llm"]["requested"] and not s3["llm"]["fallback"] and s3["llm"]["ahead"] is True
    assert s3["meta"]["stage2Run"] == s2["meta"]["run"] and s3["meta"]["stage1Run"] == s2["meta"]["stage1Run"] == s1["meta"]["run"]
    sent = [t for t in s3["tables"] if t["llm"]["sent"]]
    assert sent and all(t["llm"].get("summary") == "가짜 요약" and not t["llm"]["undecided"] for t in sent)
    assert s2["llm"]["requested"] and not s2["llm"]["fallback"] and n == s3["meta"]["run"] and job.stage == 3
    # 표기 — 헤딩 · 표가 같은 차례 번호(같이) · 서식은 그 뒤. 단계 글에 「헤딩 판정과 같이」
    assert _parts(job) == [("heads", 1, "ok"), ("tables", 1, "ok"), ("formats", 2, "skip")]
    assert "호출은 헤딩 판정과 같이" in {p["key"]: p for p in job.parts}["tables"]["msg"]
    step = {x["name"]: x for x in job.view()["steps"]}[heading_runs.STEP3_LLM]
    assert step["status"] == "ok" and "호출은 헤딩 판정과 같이" in step["msg"]


def test_heading_failure_still_closes_tables_with_the_answers(c, monkeypatch):
    """헤딩 LLM 이 답을 못 하면 작업은 그 까닭으로 실패 — 이미 묻기 시작한 표 판정은 받은 답으로 맺는다(유료 답을 버리지 않는다). 서식은 대기로 남는다."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    job = _chain(s)
    ask = _asker(types_ok=False)
    monkeypatch.setattr(llm, "ask_all", ask)
    with pytest.raises(analysis_llm.Stop, match="헤딩 그래프 LLM 판정을 못 함"):
        _run(s, job)
    st = heading_runs.state(s)
    assert _parts(job) == [("heads", 1, "failed"), ("tables", 1, "ok"), ("formats", 2, "wait")]
    assert st["stage2"]["llm"]["fallback"] and st["stage3"]["llm"]["ahead"] is True and not st["stage3"]["llm"]["fallback"]
    assert st["stage3"]["meta"]["stage2Run"] == st["stage2"]["meta"]["run"]   # 소속은 (스크립트로 대신한) 지금 헤딩 그래프에서
    assert ask.log.count("ask:heading_tables") == st["stage3"]["llm"]["calls"]   # 다시 묻지 않는다


def test_heading_failure_without_any_table_answer_leaves_tables_untouched(c, monkeypatch):
    """LLM 이 꺼져 있을 때처럼 어느 호출도 답하지 못하면 — 헤딩에서 멈추고 표는 전처럼 대기(앞 표 구조를 「LLM 실패」 결과로 덮지 않는다)."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    job = _chain(s)
    before = heading_runs.state(s)["stage3"]["meta"]["run"]
    monkeypatch.setattr(llm, "ask_all", lambda jobs, **kw: [_res(None, "off") for _ in jobs])
    with pytest.raises(analysis_llm.Stop, match="헤딩 그래프 LLM 판정을 못 함"):
        _run(s, job)
    st = heading_runs.state(s)
    assert _parts(job) == [("heads", 1, "failed"), ("tables", 1, "wait"), ("formats", 2, "wait")] and job.stage == 2
    assert st["stage3"]["meta"]["run"] == before and not st["stage3"]["llm"]["requested"]   # 표 구조는 앞 결과 그대로
    step = {x["name"]: x for x in job.view()["steps"]}[heading_runs.STEP3_LLM]
    assert step["status"] == "failed" and "앞 결과 그대로" in step["msg"]   # 단계 줄이 「도는 중」 으로 남지 않는다


def test_heading_error_drops_the_table_answers(c, monkeypatch):
    """헤딩 판정이 오류(예외)로 끝나면 — 표는 「멈춤」, 받은 답은 쓰지 않는다(붙일 헤딩 그래프가 없다)."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    job = _chain(s)
    before = heading_runs.state(s)["stage3"]["meta"]["run"]

    def ask(jobs, **kw):
        if jobs[0]["what"].startswith("heading_types"):
            raise RuntimeError("그래프를 짓다가 오류")
        return _asker()(jobs, **kw) if jobs[0]["what"].startswith("heading_tables") else [_res(None, "가짜 실패") for _ in jobs]
    monkeypatch.setattr(llm, "ask_all", ask)
    with pytest.raises(RuntimeError, match="그래프를 짓다가 오류"):
        _run(s, job)
    assert _parts(job) == [("heads", 1, "running"), ("tables", 1, "stopped"), ("formats", 2, "wait")]
    assert heading_runs.state(s)["stage3"]["meta"]["run"] == before and job.tables_ahead.take(heading_runs.state(s)["stage1"]) is None


def test_stop_request_closes_tables_and_skips_formats(c, monkeypatch):
    """멈추기 — 헤딩 판정과 같이 묻던 표 판정은 「도는 단계」 라 맺고, 아직 시작하지 않은 서식은 하지 않는다."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    job = _chain(s)

    def stop():
        job.stop = True
    monkeypatch.setattr(llm, "ask_all", _asker(on_types=stop))
    n = _run(s, job)
    st = heading_runs.state(s)
    assert _parts(job) == [("heads", 1, "ok"), ("tables", 1, "ok"), ("formats", 2, "stopped")]
    assert n == st["stage3"]["meta"]["run"] and st["stage3"]["llm"]["ahead"] is True


def test_skipped_heads_keeps_tables_and_formats_together(c, monkeypatch):
    """헤딩 판정을 건너뛰면(이미 LLM 을 거침) 미리 묻지 않는다 — 표는 전처럼 제 손으로 묻고 차례 번호는 1 · 2 · 2."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    job = _chain(s)
    heading_runs.state(s)["stage2"]["llm"].update(requested=True, fallback=False)
    ask = _asker()
    monkeypatch.setattr(llm, "ask_all", ask)
    _run(s, job)
    st = heading_runs.state(s)
    assert _parts(job) == [("heads", 1, "skip"), ("tables", 2, "ok"), ("formats", 2, "skip")] and job.tables_ahead is None
    assert "ask:heading_types" not in ask.log and ask.log.count("ask:heading_tables") == st["stage3"]["llm"]["calls"] >= 1
    assert "ahead" not in st["stage3"]["llm"]


def test_asked_answers_give_the_same_tables_as_asking_inside_build(c):
    """ask_tables 로 미리 받은 답을 build(asked=…) 에 넣은 결과 = build 가 제 손으로 물은 결과(같은 1단계 · 같은 TEMP)."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)
    s1 = heading_runs.state(s)["stage1"]

    def ask(jobs, **kw):
        out = []
        for job in jobs:
            ids = _table_ids(job)
            out.append(_res({"tables": [{"table": tid, "subtables": [], "cells": [], "summary": f"요약 {tid}"} for tid in ids[:-1] or ids], "summary": "묶음"}))  # 묶음의 마지막 표는 답에 없음 → 미판정
        return out
    seen = []
    got = HT.ask_tables(s1, ask=ask, progress=lambda done, total: seen.append((done, total)))
    assert got["jobs"] >= 1 and got["sent"] == len(got["answers"]) and seen[0] == (0, got["jobs"])   # 시작할 때 (0, n)
    a = HT.build(s1, use_llm=True, ask=ask)
    b = HT.build(s1, use_llm=True, asked=got, ask=lambda jobs: pytest.fail("미리 받은 답이 있으면 다시 묻지 않는다"))
    assert a["tables"] == b["tables"] and a["counts"] == b["counts"] and len(a["_calls"]) == len(b["_calls"]) == got["jobs"]
    la, lb = ({k: v for k, v in x["llm"].items() if k not in ("seconds", "ahead")} for x in (a, b))
    assert la == lb and b["llm"]["ahead"] is True and "ahead" not in a["llm"] and a["llm"]["undecided"] >= 1
    assert HT.build(s1, use_llm=False, asked=got)["llm"]["calls"] == 0   # 스크립트 실행은 답을 쓰지 않는다


def test_ahead_answers_are_dropped_for_another_stage1_or_on_error(monkeypatch):
    job = heading_runs.Job(2, True, 0)
    s1, other = {"paras": []}, {"paras": []}
    seen = []
    monkeypatch.setattr(heading_runs.HT, "ask_tables", lambda stage1, **kw: kw["progress"](0, 2) or {"answers": {}, "calls": [], "guides": {}, "jobs": 2, "sent": 0, "summary": ""})
    ahead = heading_runs.TablesAhead(on_progress=lambda done, total: seen.append((done, total)))
    assert ahead.take(s1) is None   # 시작하지 않음
    ahead.start(job, s1, {"tables": {"text": "", "sha1": "x"}}, {})
    ahead.start(job, other, {}, {})   # 두 번째 시작은 무시
    asked, temp, guides = ahead.take(s1)
    assert asked["jobs"] == 2 and "tables" in guides and temp is not None and seen == [(0, 2)]
    assert ahead.take(other) is None   # 그 사이 1단계를 다시 뽑음 — 버린다(run_stage3 이 다시 묻는다)
    step = {x["name"]: x for x in job.view()["steps"]}[heading_runs.STEP3_LLM]
    assert step["status"] == "running" and "헤딩 판정과 같이" in step["msg"]

    def boom(stage1, **kw):
        raise RuntimeError("묻다가 오류")
    monkeypatch.setattr(heading_runs.HT, "ask_tables", boom)
    bad = heading_runs.TablesAhead()
    bad.start(job, s1, {}, {})
    assert bad.take(s1) is None


def test_ask_all_reports_progress_and_survives_a_failing_callback(monkeypatch):
    monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: _res({"ok": content}))
    jobs = [{"schema": {}, "content": str(i), "what": f"t#{i}"} for i in range(5)]
    seen = []
    out = llm.ask_all(jobs, progress=lambda done, total: seen.append((done, total)))
    assert [r["data"]["ok"] for r in out] == ["0", "1", "2", "3", "4"] and seen == [(i, 5) for i in range(1, 6)]

    def bad(done, total):
        raise RuntimeError("진행 글 실패")
    assert len(llm.ask_all(jobs, progress=bad)) == 5 and llm.slots_n() >= 1


def test_rule_groups_are_split_so_calls_run_together(c):
    """규칙 보강 — 묶음이 많은 문서는 여러 호출로 나뉜다(호출 하나에 10묶음 — 같이 돈다)."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)
    s1 = heading_runs.state(s)["stage1"]
    groups = HL.rule_groups(s1)
    jobs, _ = HL.rule_jobs(s1)
    assert HL.BATCH_GROUPS == 10 and len(groups) == 27 and len(jobs) == 3 and [j["what"] for j in jobs] == ["heading_rules#1", "heading_rules#2", "heading_rules#3"]
