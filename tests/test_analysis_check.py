"""구간 검증 — 10쪽씩 · 구간마다 검증 에이전트(app/analysis_check.py · analysis_llm._check — spec_작업 ② §20 「구간 검증 — 10쪽씩」 · 2026-11-26 사용자 「10페이지씩 검증 에이전트를 병렬로 추가해서 처리」).
LLM 은 가짜(llm.ask_all) · 문서는 손으로 지은 블록(쪽마다 헤딩 하나 + 짧은 문단 하나, 12쪽에 표 하나)."""
import threading
from types import SimpleNamespace

import pytest

from app import analysis_check as AC
from app import analysis_llm, heading_runs, llm


def _doc(pages=25):
    blocks, nodes = [], []
    for p in range(1, pages + 1):
        blocks.append({"id": f"h{p}", "type": "paragraph", "text": f"{p}. 제목 {p}", **({"pageStart": True} if p > 1 else {})})
        nodes.append({"id": f"n{p}", "para": f"h{p}", "n": 2 * p, "role": "heading", "letter": f"{p}.", "text": f"제목 {p}", "parent": "n1" if p > 1 else None, "tplNo": 1, "level": 1 if p == 1 else 2, "blank": False})
        blocks.append({"id": f"p{p}", "type": "paragraph", "text": f"짧은 줄 {p}"})
        if p == 12:
            blocks.append({"id": "t1", "type": "table", "cells": [{"id": "c1", "row": 0, "col": 0, "blocks": []}, {"id": "c2", "row": 0, "col": 1, "blocks": []}]})
            blocks.append({"id": "long", "type": "paragraph", "text": "긴 본문 문단 " * 20})
    tables = {"tables": [{"id": "t1", "depth": 1, "rows": 1, "cols": 2, "before": "표 앞 글", "subtables": [{"id": "A", "kind": "matrix", "headerRows": 1, "headerCols": 0}],
                          "cells": [{"id": "c1", "role": "colhead", "text": "구분"}, {"id": "c2", "role": "field", "text": ""}]}]}
    return blocks, {"nodes": nodes}, tables


def test_windows_cut_by_ten_pages_with_context():
    blocks, graph, tables = _doc()
    wins = AC.windows(blocks, graph, tables)
    assert [w["pages"] for w in wins] == [[1, 10], [11, 20], [21, 25]] and [w["no"] for w in wins] == [1, 2, 3]
    w1, w2, w3 = wins
    assert w1["before"] == [] and len(w1["after"]) == AC.EDGE and w1["after"][0][:2] == ["h", "n11"]   # 뒤 구간의 가장자리 줄(문맥)
    assert len(w2["before"]) == AC.EDGE and w2["before"][-1] == ["p", "p10", "짧은 줄 10"] and w3["after"] == []
    assert w2["open"] == [["n1", "T1 L1", "1.", "제목 1"]] and w1["open"] == []   # 구간 앞에서 열린 헤딩 사슬 — 경계에 걸친 헤딩을 읽는 문맥
    assert w2["targets"]["table"] == ["t1"] and "n12" in w2["targets"]["heading"] and "p12" in w2["targets"]["missed"] and "long" not in w2["targets"]["missed"]   # 표는 한 구간에 통째로 · 긴 본문 문단은 싣지 않는다
    assert ["t", "t1", "1x2", "표 앞 글", {"subs": [["A", "matrix", 1, 0]], "heads": ["구분"], "fields": 1}] in w2["lines"]
    assert ["h", "n12", "T1 L2", "heading", "12.", "제목 12", "n1"] in w2["lines"]
    assert not set(w1["isig"]) & set(w2["isig"]) and len({w["sig"] for w in wins}) == 3
    assert AC.windows([], graph, tables) == [] and len(AC.windows(blocks, graph, tables, pages=5)) == 5


def test_check_takes_only_this_windows_lines():
    wins = AC.windows(*_doc())
    w2 = wins[1]
    data = {"findings": [{"kind": "heading", "id": "n12", "what": "레벨이 형제와 다름", "suggest": "T1 L2", "sure": True},
                         {"kind": "heading", "id": "n12", "what": "같은 줄 두 번", "suggest": "", "sure": False},
                         {"kind": "heading", "id": "n10", "what": "문맥 줄(앞 구간)", "suggest": "", "sure": True},
                         {"kind": "table", "id": "n12", "what": "종류가 다른 id", "suggest": "", "sure": True},
                         {"kind": "missed", "id": "p13", "what": "앞뒤 헤딩과 같은 꼴", "suggest": "o 레벨 헤딩", "sure": False},
                         {"kind": "table", "id": "t1", "what": "", "suggest": "", "sure": True}, {"kind": "모름", "id": "t1", "what": "x", "suggest": "", "sure": True}, "깨진 줄"]}
    assert AC.check(data, w2) == [{"kind": "heading", "id": "n12", "what": "레벨이 형제와 다름", "suggest": "T1 L2", "sure": True},
                                  {"kind": "missed", "id": "p13", "what": "앞뒤 헤딩과 같은 꼴", "suggest": "o 레벨 헤딩", "sure": False}]
    assert AC.check(None, w2) == [] and AC.check({"findings": None}, w2) == []


def test_store_keeps_findings_per_item_and_drops_them_when_the_judgment_changes():
    blocks, graph, tables = _doc()
    wins = AC.windows(blocks, graph, tables)
    store = AC.empty()
    AC.merge(store, wins[1], [{"kind": "heading", "id": "n12", "what": "레벨", "suggest": "", "sure": True}, {"kind": "table", "id": "t1", "what": "헤더 행", "suggest": "헤더 행 2", "sure": False}], 10.0, "m")
    v = AC.view(store, wins)
    assert [(f["kind"], f["id"], f["name"], f["text"]) for f in v["finds"]] == [("heading", "n12", "헤딩", "제목 12"), ("table", "t1", "표", "표 앞 글")]
    assert v["left"] == 2 and [r["checked"] for r in v["windows"]] == [False, True, False] and v["counts"] == {"heading": 1, "table": 1, "missed": 0}
    assert AC.counts_text(v["counts"]) == "확인 필요 2곳(헤딩 1 · 표 1)" and AC.counts_text({"heading": 0, "table": 0, "missed": 0}) == "확인 필요 없음"
    AC.merge(store, wins[1], [{"kind": "table", "id": "t1", "what": "다시 봄", "suggest": "", "sure": True}], 20.0)   # 같은 구간의 새 답 — 그 구간의 줄에 붙은 앞 항목만 바뀐다
    assert [(f["id"], f["what"]) for f in AC.view(store, wins)["finds"]] == [("t1", "다시 봄")]
    next(n for n in graph["nodes"] if n["id"] == "n13")["level"] = 3   # 판정이 바뀜(같은 구간의 다른 줄) — 구간은 다시 볼 것이 되지만 안 바뀐 줄의 항목은 남는다
    again = AC.windows(blocks, graph, tables)
    v = AC.view(store, again)
    assert [r["checked"] for r in v["windows"]] == [False, False, False] and [f["id"] for f in v["finds"]] == ["t1"]
    tables["tables"][0]["subtables"][0]["headerRows"] = 2   # 그 표의 판정을 고침 — 그 항목은 저절로 빠진다(저장본에서 지우지는 않는다)
    assert AC.view(store, AC.windows(blocks, graph, tables))["finds"] == [] and len(store["finds"]) == 1


@pytest.fixture
def chain(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "headings"))
    blocks, graph, tables = _doc()
    sess = SimpleNamespace(id="check-test", name="문서.hwpx", rev=3, lock=threading.RLock(), doc=SimpleNamespace(blocks=lambda: blocks))
    st = {"stage2": graph, "stage3": tables}
    asked = []

    def ask_all(jobs, **kw):
        out = []
        for j in jobs:
            no = int(j["what"].split("#")[1])
            asked.append(no)
            assert j["schema"] == AC.SCHEMA and "검증" in j["content"] and '"window":{"no":%d,"of":3' % no in j["content"]
            got = ask_all.answers.get(no, {"findings": [], "summary": ""})
            out.append({"data": got, "error": None if got is not None else "boom", "model": "m"})
        if kw.get("progress"):
            kw["progress"](len(jobs), len(jobs))
        ask_all.after()
        return out
    ask_all.answers, ask_all.after = {}, lambda: None
    monkeypatch.setattr(llm, "ask_all", ask_all)
    monkeypatch.setattr(llm, "status", lambda: {"available": True})
    monkeypatch.setattr(llm, "slots_n", lambda: 2)
    monkeypatch.setattr(analysis_llm.works, "log", lambda *a, **k: None)
    AC._MEM.pop("check-test", None)

    def go(stop_after_first=False):
        job = heading_runs.Job(2, True, 3)
        job.parts = [{"key": "check", "name": "구간 검증", "no": 3, "status": "wait", "msg": ""}]
        ask_all.after = (lambda: setattr(job, "stop", True)) if stop_after_first else (lambda: None)
        analysis_llm._check(sess, job, st)
        return job.parts[0], job
    return go, asked, ask_all, st


def test_check_runs_windows_in_slot_sized_batches_and_carries_over(chain):
    go, asked, ask_all, st = chain
    ask_all.answers = {2: {"findings": [{"kind": "table", "id": "t1", "what": "헤더 행이 모자람", "suggest": "헤더 행 2", "sure": True}], "summary": ""}}
    part, job = go(stop_after_first=True)   # 자리 2 → 구간 둘씩: 첫 묶음 뒤 멈추기
    assert asked == [1, 2] and part["status"] == "partial" and "구간 2/3 검증" in part["msg"] and "멈춤 — 남은 구간 1" in part["msg"] and "확인 필요 1곳(표 1)" in part["msg"]
    assert any(s["name"] == analysis_llm.CHECK_STEP for s in job.view()["steps"])
    part, _ = go()   # 다시 — 답을 받은 구간은 묻지 않는다(이어 씀)
    assert asked == [1, 2, 3] and part["status"] == "ok" and "구간 1/1 검증(이어 씀 2)" in part["msg"]
    part, _ = go()
    assert asked == [1, 2, 3] and part["status"] == "skip" and "모두 앞 검증을 이어 씀" in part["msg"] and "확인 필요 1곳" in part["msg"]
    next(n for n in st["stage2"]["nodes"] if n["id"] == "n24")["role"] = "not_heading"   # 판정이 바뀐 구간만 다시(n24 = 셋째 구간 안쪽 줄 — 앞 구간의 가장자리 문맥(첫 네 줄)에는 안 든다)
    ask_all.answers = {3: None}   # 그 구간의 답을 못 받음 — 앞 검증(다른 구간의 확인 필요)은 그대로
    part, _ = go()
    assert asked == [1, 2, 3, 3] and part["status"] == "failed" and "답을 못 받은 구간 1" in part["msg"] and "확인 필요 1곳(표 1)" in part["msg"]
    assert [f["id"] for f in AC.load("check-test")["finds"]] == ["t1"]


def test_check_skips_without_llm_or_graph(chain, monkeypatch):
    go, asked, _, st = chain
    monkeypatch.setattr(llm, "status", lambda: {"available": False})
    part, _ = go()
    assert part["status"] == "skip" and "LLM 을 쓸 수 없어" in part["msg"] and asked == []
    monkeypatch.setattr(llm, "status", lambda: {"available": True})
    st["stage2"] = None
    assert go()[0]["status"] == "skip" and asked == []


def test_run_adds_the_check_part_only_when_asked(monkeypatch):
    sess = SimpleNamespace(id="check-run", name="x", rev=1)
    done = {"llm": {"requested": True, "fallback": False}, "meta": {"rev": 1}}
    monkeypatch.setattr(heading_runs, "state", lambda s: {"stage2": done, "stage3": {**done, "tables": []}})
    seen = []
    monkeypatch.setattr(analysis_llm, "_check", lambda s, job, st: seen.append([p["key"] for p in job.parts]))
    kw = dict(outline=lambda s: None, plans=lambda s, g: {}, plan=lambda s, t: None)
    job = heading_runs.Job(2, True, 1)
    analysis_llm.run(sess, job, **kw)
    assert [p["key"] for p in job.parts] == ["heads", "tables", "formats"] and seen == []   # 청하지 않으면 전과 같은 셋
    job = heading_runs.Job(2, True, 1)
    analysis_llm.run(sess, job, windows=True, **kw)
    assert [(p["key"], p["no"]) for p in job.parts] == [("heads", 1), ("tables", 2), ("formats", 2), ("check", 3)] and seen == [["heads", "tables", "formats", "check"]]
    job = heading_runs.Job(2, True, 1)
    analysis_llm.run(sess, job, windows=True, parts=("heads", "formats"), **kw)   # 표가 없는 이어 돌리기(「헤딩 그래프(LLM)」)에는 붙지 않는다
    assert [p["key"] for p in job.parts] == ["heads", "formats"] and len(seen) == 1
