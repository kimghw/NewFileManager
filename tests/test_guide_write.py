"""지침 작성 · 문서 라이브러리에서 자료 가져오기(app/guide_write.py · guide_write_api.py · doclib_client.py — spec_양식작성 ② §4 · §5).
LLM 을 부르지 않는다(자리마다의 턴 `doc_agent_api.agent_turn` 을 가짜로) · 문서 라이브러리 서버에 닿지 않는다(`doclib_client` 를 가짜로)."""
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app import doc_agent as A
from app import doc_agent_api, doclib_client, guide_write, server
from app import guide_write_api as API

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


def P(i, text):
    return {"id": i, "type": "paragraph", "text": text}


def T(i, first_row, inner=()):
    return {"id": i, "type": "table", "cells": [{"id": f"{i}k{k}", "row": 0, "col": k, "blocks": [P(f"{i}c{k}", t)]} for k, t in enumerate(first_row)] + [{"id": f"{i}k9", "row": 1, "col": 0, "blocks": list(inner)}]}


BLOCKS = [P("h1", "1. 연구개발 목표"), P("p1", "이미 쓴 글"), T("t1", ["구분", "내용"]), P("h2", "1-1. 최종 목표"), P("p2", ""), P("h3", "2. 추진 전략"), T("t2", ["항목", "값"], inner=[T("t3", ["안쪽", "표"])])]
GRAPH = {"nodes": [{"role": "heading", "area": "body", "para": "h1", "depth": 1}, {"role": "heading", "area": "body", "para": "h2", "depth": 2}, {"role": "heading", "area": "body", "para": "h3", "depth": 1},
                   {"role": "heading", "area": "table", "para": "t1c0", "depth": 1}, {"role": "label", "area": "body", "para": "p1"}, {"role": "heading", "area": "body", "para": "gone", "depth": 1}]}
IX = {"heads": {"h2": [{"src": "doc", "kind": "작성 요령", "text": "최종 목표를 정량 지표와 함께 3줄 이내로 쓴다."}, {"src": "user", "kind": "사용자 지침", "text": "한국선급 몫만"}], "h9": [{"src": "doc", "kind": "", "text": "없는 헤딩"}]},
      "tables": {"t1": [{"src": "doc", "kind": "※ 안내", "text": "구분마다 한 줄"}], "t3": [{"src": "user", "kind": "표 지침(이 표)", "text": "안쪽 표 지침"}], "tx": [{"src": "doc", "kind": "", "text": "없는 표"}]}}


def test_places_list_body_headings_and_guided_tables_in_document_order():
    ps = guide_write.places(BLOCKS, GRAPH, IX)
    assert [(p["id"], p["kind"]) for p in ps] == [("h1", "head"), ("t1", "table"), ("h2", "head"), ("h3", "head"), ("t3", "table")]   # 본문 헤딩 전부 + 지침이 붙은 표(문서 차례) · 문서에 없는 것은 뺀다
    h1, t1, h2, h3, t3 = ps
    assert (h1["n"], h1["filled"], h1["tables"], h1["depth"]) == (0, True, ["t1"], 1) and (h2["n"], h2["user"], h2["filled"], h2["depth"]) == (2, True, False, 2) and h3["tables"] == ["t2"]
    assert (t1["text"], t1["head"], t1["top"], t1["n"]) == ("구분 | 내용", "h1", True, 1) and (t3["text"], t3["head"], t3["top"], t3["user"]) == ("안쪽 | 표", "h3", False, True)
    assert guide_write.places([], None, None) == [] and [p["id"] for p in guide_write.places(BLOCKS, GRAPH, None)] == ["h1", "h2", "h3"]


def test_request_text_carries_the_place_guides_and_the_run_note():
    ps = {p["id"]: p for p in guide_write.places(BLOCKS, GRAPH, IX)}
    r = guide_write.request(ps["h2"], "  개조식으로\n3줄 ", "")
    assert r.startswith("[지침 작성] 헤딩 「1-1. 최종 목표」(id h2) 아래 자리를") and "- (사람) 한국선급 몫만\n- (양식 · 작성 요령) 최종 목표를 정량 지표와 함께 3줄 이내로 쓴다." in r   # 사람의 것이 앞
    assert "이번 작성의 지침(사람이 적음): 개조식으로 3줄" in r and "자료에 이 자리에 해당하는 내용이 없으면 행동 없이" in r and "이미 글이 있습니다" not in r and "tableFill" not in r
    r1 = guide_write.request(ps["h1"], "", "")
    assert "작성 지침은 없습니다" in r1 and "이미 글이 있습니다" in r1 and "표 채우기(tableFill)" in r1          # 글이 있는 자리 · 표가 딸린 자리
    rt = guide_write.request(ps["t1"], "", "1. 연구개발 목표")
    assert "표 「구분 | 내용」(id t1 · 헤딩 「1. 연구개발 목표」 아래)" in rt and "- (양식 · ※ 안내) 구분마다 한 줄" in rt and "tableFill" in rt
    long = guide_write.request({**ps["h2"], "guides": [{"src": "doc", "kind": "k", "text": "가" * 9000}]}, "나" * 5000)
    assert len(long) <= guide_write.TEXT_MAX <= A.TEXT_MAX and "나" * (guide_write.NOTE_MAX + 1) not in long
    assert guide_write.selection(ps["h2"]) == {"paras": [], "table": None, "range": None, "cursor": "h2"}
    assert guide_write.selection(ps["t1"])["table"] == "t1" and guide_write.selection(ps["t3"]) == {"paras": [], "table": None, "range": None, "cursor": "h3"}   # 칸 안의 표는 고를 수 없다 — 그 헤딩에 커서
    got, lost = guide_write.pick(list(ps.values()), ["h3", "h2", "h2", "zz", 7])
    assert [p["id"] for p in got] == ["h2", "h3"] and lost == 1


@pytest.fixture
def c(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")   # 실제 LLM 을 부르지 않는다 — 쓸 수 있는 척은 그 시험이 status 만 바꾼다
    A._MEMORY.clear()
    server.DOCS.clear()
    API._RUNS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()
    API._RUNS.clear()


def _doc(c):
    r = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait(c, doc):
    for _ in range(200):
        run = c.get(f"/api/docs/{doc}/guide-write/run").json()["run"]
        if run and run["state"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("지침 작성이 끝나지 않음")


def test_guide_write_runs_one_agent_turn_per_place(c, monkeypatch):
    doc = _doc(c)
    got = c.get(f"/api/docs/{doc}/guide-write").json()
    assert got["hwpx"] and got["materials"] == [] and got["run"] is None and got["limits"] == {"places": guide_write.PLACES_MAX, "note": guide_write.NOTE_MAX} and isinstance(got["places"], list)
    places = [p for p in guide_write.places(BLOCKS, GRAPH, IX)]
    monkeypatch.setattr(API, "_places", lambda s: (places, 0))
    assert [p["id"] for p in c.get(f"/api/docs/{doc}/guide-write").json()["places"]] == ["h1", "t1", "h2", "h3", "t3"]
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "자료.md", "text": "최종 목표: 차단 시간 1 ms 이하"}).json()["id"]
    url = f"/api/docs/{doc}/guide-write/run"
    assert c.post(url, json={"places": ["h2"], "materials": [mid]}).status_code == 503                       # LLM 꺼짐(conftest)
    monkeypatch.setattr(API.llm, "status", lambda: {"available": True})
    assert c.post(url, json={"places": ["h2"], "materials": []}).status_code == 400                          # 자료를 골라야 한다 — 자료에 있는 내용만 넣는다
    assert c.post(url, json={"places": ["h2"], "materials": ["m00000000"]}).status_code == 400
    assert c.post(url, json={"places": [], "materials": [mid]}).status_code == 400 and c.post(url, json={"places": ["zz"], "materials": [mid]}).status_code == 400
    assert c.post(url, json={"places": ["h2"], "materials": [mid], "note": "x" * 2000}).status_code == 400
    seen = []

    def turn(doc_id, body):
        seen.append(body)
        if "id h3" in body["text"]:
            raise HTTPException(400, "가짜 400")
        if "id t1" in body["text"]:
            return JSONResponse({"detail": "LLM 이 답하지 못했습니다: 가짜", "turn": {"id": "t9"}}, status_code=502)
        if "id h1" in body["text"]:
            return {"turn": {"id": "t1", "reply": "자료에 없습니다", "proposals": []}}
        return {"turn": {"id": "t2", "reply": "넣을 글을 제안합니다", "proposals": [{"id": "p1", "preselect": True, "state": "open"}, {"id": "p2", "preselect": False, "state": "open"}]}}
    monkeypatch.setattr(doc_agent_api, "agent_turn", turn)
    r = c.post(url, json={"places": ["h3", "h2", "t1", "h1"], "materials": [mid], "note": "개조식"})
    assert r.status_code == 200 and [i["id"] for i in r.json()["run"]["items"]] == ["h1", "t1", "h2", "h3"] and "stop" not in r.json()["run"]
    run = _wait(c, doc)
    by = {i["id"]: i for i in run["items"]}
    assert run["state"] == "done" and (by["h2"]["state"], by["h2"]["proposals"], by["h2"]["picked"], by["h2"]["turn"]) == ("done", 2, 1, "t2")
    assert (by["h1"]["state"], by["h1"]["reply"]) == ("none", "자료에 없습니다") and (by["t1"]["state"], by["t1"]["turn"]) == ("failed", "t9") and "가짜" in by["t1"]["error"] and by["h3"]["error"] == "가짜 400"
    assert len(seen) == 4 and all(b["materials"] == [mid] and "이번 작성의 지침(사람이 적음): 개조식" in b["text"] for b in seen)
    sel = {b["selection"]["cursor"] or b["selection"]["table"]: b["selection"] for b in seen}
    assert sel["h2"]["cursor"] == "h2" and sel["t1"]["table"] == "t1"
    assert c.get(f"/api/docs/{doc}/guide-write").json()["run"]["id"] == run["id"] and c.post(f"/api/docs/{doc}/guide-write/stop").json() == {"ok": True, "stopping": False}
    wid = c.get(f"/api/docs/{doc}").json().get("workId") or doc
    log = [e for e in c.get(f"/api/works/{wid}/log").json().get("log", []) if e.get("kind") == "guideWrite" or e.get("op") == "guideWrite"] if c.get(f"/api/works/{wid}/log").status_code == 200 else None
    assert log is None or len(log) <= 1


def test_library_listing_and_material_import(c, monkeypatch):
    doc = _doc(c)
    got = c.get("/api/doclib").json()                                    # 닿지 않는 주소(conftest) — 꺼짐으로 보이고 8114 는 그대로 답한다
    assert got["alive"] is False and got["docs"] == [] and "닿지 못했습니다" in got["why"] and got["url"] == "http://127.0.0.1:9"
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "../x"}).status_code == 400
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "xaaaaaaaaaa"}).status_code == 502
    metas = {"xaaaaaaaaaa": {"id": "xaaaaaaaaaa", "doc": "d1", "state": "done", "focus": "한국선급의 연구", "figures": 2, "formulas": 1, "open": 1}, "xbbbbbbbbbb": {"id": "xbbbbbbbbbb", "doc": "d1", "state": "running"}}
    monkeypatch.setattr(doclib_client, "health", lambda: {"ok": True, "llm": {"available": True}})
    monkeypatch.setattr(doclib_client, "docs", lambda: [{"id": "d1", "name": "연차보고서.pdf", "ext": "pdf", "pages": 9, "org": "한국선급", "topic": "", "bytes": 1,
                                                          "extracts": [{**metas["xaaaaaaaaaa"], "chars": 10, "span": [1, 9], "at": 1.0}, metas["xbbbbbbbbbb"]]}])
    monkeypatch.setattr(doclib_client, "extract", lambda eid: metas[eid] if eid in metas else (_ for _ in ()).throw(LookupError("그런 추출이 없습니다")))
    monkeypatch.setattr(doclib_client, "md", lambda eid: "# 연차보고서\n\n<!-- p.1 -->\n본문 글\n")
    got = c.get("/api/doclib").json()
    assert got["alive"] and got["docs"][0]["running"] == 1 and [e["id"] for e in got["docs"][0]["extracts"]] == ["xaaaaaaaaaa"] and got["docs"][0]["extracts"][0]["open"] == 1   # 끝난 추출만
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "xbbbbbbbbbb"}).status_code == 409
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "xcccccccccc"}).status_code == 404
    m = c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "xaaaaaaaaaa"}).json()
    assert m["name"] == "연차보고서 — 한국선급의 연구.md" and m["kind"] == "md" and "(xaaaaaaaaaa)" in m["note"] and "확인 필요 1곳" in m["note"] and "reused" not in m
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "xaaaaaaaaaa"}).json()["reused"] is True
    assert [x["id"] for x in c.get(f"/api/docs/{doc}/guide-write").json()["materials"]] == [m["id"]] and [x["id"] for x in c.get(f"/api/docs/{doc}/agent").json()["materials"]] == [m["id"]]


def test_client_address_and_ids(monkeypatch):
    monkeypatch.delenv("NFM_DOCLIB_URL", raising=False)
    monkeypatch.setenv("NFM_DOCLIB_PORT", "18999")
    assert doclib_client.url() == "http://127.0.0.1:18999"
    monkeypatch.setenv("NFM_DOCLIB_URL", "http://127.0.0.1:9/")
    assert doclib_client.url() == "http://127.0.0.1:9" and doclib_client.ok_id("x0123456789") and not doclib_client.ok_id("x012") and not doclib_client.ok_id(None)
    with pytest.raises(doclib_client.Down):
        doclib_client.health()
    with pytest.raises(LookupError):
        doclib_client.md("nope")


def test_registry_has_the_workflow_and_its_tools():
    from app import agents, job_prompts, workflow
    t = workflow.BY_JOB["form_write"]
    assert [g["id"] for g in t["stages"]] == ["open", "material", "write"] and [s["key"] for s in t["stages"][1]["steps"]] == ["keep", "extract", "take"]
    assert [s["key"] for s in t["stages"][2]["steps"]] == ["guides", "ask", "check", "apply"] and {"doclib", "guidewrite"} <= set(workflow.BY_COMMON)
    ask = next(s for s in t["stages"][2]["steps"] if s["key"] == "ask")
    assert ask["agents"] == ("doc_agent", "table_fill") and ask["change"] == "store" and next(s for s in t["stages"][2]["steps"] if s["key"] == "apply")["change"] == "doc"
    assert agents.JOB_NAMES["form_write"] == "양식 작성" and server.TASK_KIND["form_write"] == "general" and "form_write" in server.TASK["job"]
    text = (Path(__file__).parents[1] / "jobs" / "form_write.md").read_text(encoding="utf-8")
    assert "자료에 있는 내용만" in job_prompts.body(text) and "사용자 원문" not in job_prompts.body(text)
