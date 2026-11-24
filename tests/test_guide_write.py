"""지침 작성 · 문서 라이브러리에서 자료 가져오기(app/guide_write.py · guide_write_api.py · doclib_client.py — spec_양식작성 ② §4 · §5).
LLM 을 부르지 않는다(자리마다의 턴 `doc_agent_api._turn` 을 가짜로 — 서버 쪽 범위 scope 를 함께 받는다) · 문서 라이브러리 서버에 닿지 않는다(`doclib_client` 를 가짜로)."""
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app import doc_agent as A
from app import doc_agent_api, doclib_client, form_review, form_review_api, guide_write, server
from app import guide_write_api as API
from tests.test_form_slots import BOX44, BOX97, CHECK, LEVELS, box, para, table

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
    assert guide_write.selection(ps["t1"])["table"] == "t1" and guide_write.selection(ps["t3"]) == {"paras": [], "table": "t3", "range": None, "cursor": "t3"}   # 칸 안의 표도 그 표를 고른다(요청 글이 가리키는 id 가 보낸 자료에 있어야 한다)
    got, lost = guide_write.pick(list(ps.values()), ["h3", "h2", "h2", "zz", 7])
    assert [p["id"] for p in got] == ["h2", "h3"] and lost == 1


def _reviewed(doc, places, mids, decided=()):
    """양식 검토 · 작성 계획이 끝난 저장본을 적는다(물음 없음 — 문 `form_review_api.gate` 가 열린다). 자리마다의 지문은 지금 자리 목록의 것."""
    form_review_api._save(server._sess(doc).id, {"review": {"summary": "", "places": {}, "questions": [], "topics": [], "materials": list(mids), "sig": form_review.sig(places), "sigs": form_review.sigs(places)},
                                                "decided": list(decided)})


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
    _reviewed(doc, places, [mid])   # 양식 검토 · 작성 계획이 있고 물음이 없는 저장본(문의 조건은 tests/test_form_review.py 가 본다)
    assert c.post(url, json={"places": ["h2"], "materials": []}).status_code == 400                          # 자료를 골라야 한다 — 자료에 있는 내용만 넣는다
    assert c.post(url, json={"places": ["h2"], "materials": ["m00000000"]}).status_code == 400
    assert c.post(url, json={"places": [], "materials": [mid]}).status_code == 400 and c.post(url, json={"places": ["zz"], "materials": [mid]}).status_code == 400
    assert c.post(url, json={"places": ["h2"], "materials": [mid], "note": "x" * 2000}).status_code == 400
    seen, scopes = [], {}

    def turn(doc_id, body, scope=None):
        seen.append(body)
        scopes[body["selection"]["cursor"]] = scope
        if "id h3" in body["text"]:
            raise HTTPException(400, "가짜 400")
        if "id t1" in body["text"]:
            return JSONResponse({"detail": "LLM 이 답하지 못했습니다: 가짜", "turn": {"id": "t9"}}, status_code=502)
        if "id h1" in body["text"]:
            return {"turn": {"id": "t1", "reply": "자료에 없습니다", "proposals": [], "dropped": []}}
        return {"turn": {"id": "t2", "reply": "넣을 글을 제안합니다", "proposals": [{"id": "p1", "preselect": True, "state": "open"}, {"id": "p2", "preselect": False, "state": "open"}]}}
    monkeypatch.setattr(doc_agent_api, "_turn", turn, raising=False)
    r = c.post(url, json={"places": ["h3", "h2", "t1", "h1"], "materials": [mid], "note": "개조식"})
    assert r.status_code == 200 and [i["id"] for i in r.json()["run"]["items"]] == ["h1", "t1", "h2", "h3"] and "stop" not in r.json()["run"]
    run = _wait(c, doc)
    by = {i["id"]: i for i in run["items"]}
    assert run["state"] == "done" and (by["h2"]["state"], by["h2"]["proposals"], by["h2"]["picked"], by["h2"]["turn"]) == ("done", 2, 1, "t2")
    assert (by["h1"]["state"], by["h1"]["reply"], by["h1"]["why"], by["h2"]["why"]) == ("none", "자료에 없습니다", "noaction", None) and (by["t1"]["state"], by["t1"]["turn"]) == ("failed", "t9") and "가짜" in by["t1"]["error"] and by["h3"]["error"] == "가짜 400"
    assert len(seen) == 4 and all(b["materials"] == [mid] and "이번 작성의 지침(사람이 적음): 개조식" in b["text"] for b in seen)
    sel = {b["selection"]["cursor"] or b["selection"]["table"]: b["selection"] for b in seen}
    assert sel["h2"]["cursor"] == "h2" and sel["t1"]["table"] == "t1"
    # 자리마다의 서버 쪽 범위 — 헤딩 = 글 쓰기(+ 그 헤딩 아래의 표) · 표 = 그 표의 표 채우기만. 사람이 정한 답 · 올린 원본도 함께 간다
    assert (scopes["h1"]["types"], scopes["h1"]["tables"], scopes["h2"]["tables"]) == ({"write", "tableFill"}, {"t1"}, set()) and (scopes["t1"]["types"], scopes["t1"]["tables"], scopes["t1"]["paras"]) == ({"tableFill"}, {"t1"}, set())
    assert scopes["h2"]["decided"] == [] and isinstance(scopes["h2"]["uploaded"], dict) and "decided" not in run and "plans" not in run
    assert c.get(f"/api/docs/{doc}/guide-write").json()["run"]["id"] == run["id"] and c.post(f"/api/docs/{doc}/guide-write/stop").json() == {"ok": True, "stopping": False}
    wid = c.get(f"/api/docs/{doc}").json().get("workId") or doc
    log = [e for e in c.get(f"/api/works/{wid}/log").json().get("log", []) if e.get("kind") == "guideWrite" or e.get("op") == "guideWrite"] if c.get(f"/api/works/{wid}/log").status_code == 200 else None
    assert log is None or len(log) <= 1


def test_library_listing_and_material_import(c, monkeypatch):
    doc = _doc(c)
    got = c.get("/api/doclib").json()                                    # 닿지 않는 주소(conftest) — 꺼짐으로 보이고 8114 는 그대로 답한다
    assert got["alive"] is False and got["docs"] == [] and "닿지 못했습니다" in got["why"] and got["url"] == "http://127.0.0.1:9"
    assert c.get("/api/doclib/where").json() == {"url": "http://127.0.0.1:9", "alive": False, "why": got["why"]}   # 상단 바 「문서 라이브러리」 아이콘이 묻는 것(doclib_link.js)
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "../x"}).status_code == 400
    assert c.post(f"/api/docs/{doc}/agent/material/library", json={"extract": "xaaaaaaaaaa"}).status_code == 502
    metas = {"xaaaaaaaaaa": {"id": "xaaaaaaaaaa", "doc": "d1", "state": "done", "focus": "한국선급의 연구", "figures": 2, "formulas": 1, "open": 1}, "xbbbbbbbbbb": {"id": "xbbbbbbbbbb", "doc": "d1", "state": "running"}}
    monkeypatch.setattr(doclib_client, "health", lambda: {"ok": True, "llm": {"available": True}})
    monkeypatch.setattr(doclib_client, "docs", lambda: [{"id": "d1", "name": "연차보고서.pdf", "ext": "pdf", "pages": 9, "org": "한국선급", "topic": "", "bytes": 1,
                                                          "extracts": [{**metas["xaaaaaaaaaa"], "chars": 10, "span": [1, 9], "at": 1.0}, metas["xbbbbbbbbbb"]]}])
    monkeypatch.setattr(doclib_client, "extract", lambda eid: metas[eid] if eid in metas else (_ for _ in ()).throw(LookupError("그런 추출이 없습니다")))
    monkeypatch.setattr(doclib_client, "md", lambda eid: "# 연차보고서\n\n<!-- p.1 -->\n본문 글\n")
    assert c.get("/api/doclib/where").json() == {"url": "http://127.0.0.1:9", "alive": True, "why": ""}
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


def test_library_original_file_as_material(c, monkeypatch):
    """추출 전인 등록 문서 — {doc} 로 원본 파일을 글로 읽어 자료로(에이전트 보기의 「라이브러리」 고르기 — 2026-11-24 사용자 「라이브러리에서 등록한 파일들을 선택해서 참조」)."""
    doc, raw, did, hwp, big = _doc(c), SMALL.read_bytes(), "d0123456789ab", "d1111111111aa", "d2222222222bb"
    U = f"/api/docs/{doc}/agent/material/library"
    assert c.post(U, json={"doc": "../x"}).status_code == 400 and c.post(U, json={}).status_code == 400 and c.post(U, json={"doc": did}).status_code == 502   # id 꼴 · 꺼진 서버
    docs = [{"id": did, "name": "기술수요조사서.hwpx", "ext": "hwpx", "pages": 3, "org": "", "topic": "", "bytes": len(raw), "sha256": "ab" * 32, "extracts": []},
            {"id": hwp, "name": "옛 문서.hwp", "ext": "hwp", "pages": None, "bytes": 10, "sha256": "cd" * 32, "extracts": []},
            {"id": big, "name": "큰 문서.pdf", "ext": "pdf", "pages": 900, "bytes": A.MATERIAL_BYTES + 1, "sha256": "ef" * 32, "extracts": []}]
    asked = []
    monkeypatch.setattr(doclib_client, "health", lambda: {"ok": True})
    monkeypatch.setattr(doclib_client, "docs", lambda: docs)
    monkeypatch.setattr(doclib_client, "file", lambda d, limit: (asked.append((d, limit)), ("머리말의 이름.hwpx", raw))[1])
    got = {d["id"]: d for d in c.get("/api/doclib").json()["docs"]}
    assert (got[did]["raw"], got[hwp]["raw"], got[big]["raw"]) == (True, False, False) and got[did]["bytes"] == len(raw) and got[did]["sha256"] == "ab" * 32   # 화면이 고를 수 있나 · 「가져옴」(같은 sha256)을 이것으로
    assert c.post(U, json={"doc": "d9999999999cc"}).status_code == 404
    r = c.post(U, json={"doc": hwp})
    assert r.status_code == 400 and "자료 추출(MD)을 한 뒤" in r.json()["detail"] and c.post(U, json={"doc": big}).status_code == 413 and asked == []   # 못 읽는 형식 · 한도 초과는 파일을 받지도 않는다
    m = c.post(U, json={"doc": did}).json()
    assert asked == [(did, A.MATERIAL_BYTES)] and m["name"] == "기술수요조사서.hwpx" and m["kind"] == "hwpx" and m["chars"] > 0 and f"문서 라이브러리의 원본({did})" in m["note"] and "reused" not in m
    assert c.post(U, json={"doc": did}).json()["reused"] is True and [x["id"] for x in c.get(f"/api/docs/{doc}/agent").json()["materials"]] == [m["id"]]
    monkeypatch.setattr(doclib_client, "file", lambda d, limit: (_ for _ in ()).throw(doclib_client.TooBig("원본 파일이 너무 큽니다")))
    assert c.post(U, json={"doc": did}).status_code == 413
    monkeypatch.setattr(A, "MATERIALS_MAX", 1)
    monkeypatch.setattr(doclib_client, "file", lambda d, limit: ("다른 글.txt", "다른 자료 글".encode("utf-8")))
    docs.append({"id": "d3333333333dd", "name": "다른 글.pdf", "ext": "pdf", "bytes": 5, "extracts": []})
    r = c.post(U, json={"doc": "d3333333333dd"})                         # 글이 없는 PDF(읽지 못함) = 400 · 자료 한도는 그 뒤의 일
    assert r.status_code == 400
    docs[-1].update(name="다른 글.docx", ext="docx")
    monkeypatch.setattr(A, "material_from_file", lambda name, data: A.material_from_text(name, data.decode("utf-8")))
    r = c.post(U, json={"doc": "d3333333333dd"})
    assert r.status_code == 400 and "1개까지" in r.json()["detail"]      # 자료 한도 — 화면은 여기서 멈추고 못 가져온 수를 알린다


def test_client_file_reads_the_registered_original(monkeypatch):
    import http.server
    import threading
    from urllib.parse import quote

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path == "/api/docs/d0123456789ab/file"
            body = b"x" * 40 if ok else '{"detail": "그런 문서가 없습니다"}'.encode("utf-8")
            self.send_response(200 if ok else 404)
            if ok:
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote("연차 보고서.pdf"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("NFM_DOCLIB_URL", f"http://127.0.0.1:{srv.server_address[1]}")
        assert doclib_client.ok_doc("d0123456789ab") and not doclib_client.ok_doc("x0123456789") and not doclib_client.ok_doc("d012") and not doclib_client.ok_doc(None)
        assert doclib_client.file("d0123456789ab", 100) == ("연차 보고서.pdf", b"x" * 40)
        with pytest.raises(doclib_client.TooBig):
            doclib_client.file("d0123456789ab", 10)
        with pytest.raises(LookupError, match="그런 문서가 없습니다"):
            doclib_client.file("d000000000000", 100)
        with pytest.raises(LookupError, match="꼴이 아닙니다"):
            doclib_client.file("../x", 100)
    finally:
        srv.shutdown()
        srv.server_close()
    monkeypatch.setenv("NFM_DOCLIB_URL", "http://127.0.0.1:9")
    with pytest.raises(doclib_client.Down):
        doclib_client.file("d0123456789ab", 100)


def test_registry_has_the_workflow_and_its_tools():
    from app import agents, job_prompts, workflow
    t = workflow.BY_JOB["form_write"]
    assert [g["id"] for g in t["stages"]] == ["open", "material", "write"] and [s["key"] for s in t["stages"][1]["steps"]] == ["keep", "extract", "take"]
    # 2026-11-24 차례를 다시 놓음: 양식 검토(찾을 테마)가 자료 준비 앞 — 준비의 끝 · 작성 = 작성 계획 → 양식 초안 작성 → 검사 → 반영
    assert [s["key"] for s in t["stages"][0]["steps"]] == ["open", "heads", "headsLlm", "guides", "review"]
    assert [s["key"] for s in t["stages"][2]["steps"]] == ["plan", "ask", "check", "apply"] and {"doclib", "guidewrite"} <= set(workflow.BY_COMMON)
    names = {s["key"]: s["name"] for g in t["stages"] for s in g["steps"]}
    assert (names["review"], names["plan"], names["ask"], names["apply"]) == ("양식 검토 · 찾을 테마", "작성 계획 · 확인할 것", "양식 초안 작성", "고른 초안을 문서에 반영")
    ask = next(s for s in t["stages"][2]["steps"] if s["key"] == "ask")
    assert ask["agents"] == ("doc_agent", "table_fill") and ask["change"] == "store" and next(s for s in t["stages"][2]["steps"] if s["key"] == "apply")["change"] == "doc"
    assert agents.JOB_NAMES["form_write"] == "양식 작성" and server.TASK_KIND["form_write"] == "general" and "form_write" in server.TASK["job"]
    text = (Path(__file__).parents[1] / "jobs" / "form_write.md").read_text(encoding="utf-8")
    assert "자료에 있는 내용만" in job_prompts.body(text) and "사용자 원문" not in job_prompts.body(text)


# ---- 상자 안의 쓸 자리 · 같은 줄 자리(2026-11-24 — spec_양식작성 ② §5-3) -------------------------------------------------------------------

FORM = [para("f1", "■ 연구개발과제명 : "), para("f2", CHECK), para("f3", "■ 세부 과제별 당해연도 성과목표 관리"), BOX44, BOX97, para("f4", "■ 붙임"), box("tb", [para("tbp", "제목 상자")]), table("t9")]
FGRAPH = {"nodes": [{"role": "heading", "area": "body", "para": i, "depth": 1} for i in ("f1", "f2", "f3", "f4")] + [{"role": "heading", "area": "box", "para": i, "level": lv} for i, lv in LEVELS.items()]}
FIX = {"heads": {"f4": [{"src": "doc", "kind": "※ 안내", "text": "붙임은 한 쪽"}]},
       "tables": {"t97": [{"src": "doc", "kind": "※ 안내", "text": "최종보고서 제출 기관은 작성하지 않아도 됨"}], "t117": [{"src": "user", "kind": "표 지침(이 표)", "text": "샘플 표는 지운다"}], "t9": [{"src": "doc", "kind": "", "text": "표 지침"}]}}
_BOXES = guide_write.boxes   # 가짜로 바꾸기 전의 것


def _filled(block_id, text):
    """FORM 에서 문단 하나의 글만 바꾼 사본(상자 안 문단도) + 올린 원본의 원문 {id: 글}."""
    def swap(b):
        if b["type"] == "paragraph":
            return {**b, "text": text} if b["id"] == block_id else b
        return {**b, "cells": [{**c, "blocks": [swap(x) for x in c["blocks"]]} for c in b["cells"]]}
    orig = {x["id"]: x["text"] for b in FORM for x in ([b] if b["type"] == "paragraph" else b["cells"][0]["blocks"] if len(b["cells"]) == 1 else ()) if x["type"] == "paragraph"}
    return [swap(b) for b in FORM], orig


def test_boxes_chunk_views_and_chunk_paras():
    bx = guide_write.boxes(FORM, FGRAPH)
    assert list(bx) == ["t44", "t97"] and bx["t44"]["inner"] == ["t55", "t81"] and bx["t97"]["inner"] == ["t117"] and (bx["t44"]["at"], bx["t97"]["at"]) == (3, 4)   # 제목뿐인 상자(tb) · 여러 칸 표(t9)는 아니다
    views = guide_write.chunk_views(bx["t44"])
    assert [(v["key"], v["head"], v["kind"], v["paras"], v["dup"]) for v in views] == [("p49", "추진 내용 작성", "text", ["p50", "p51", "p52"], [1, 1]),      # 제목 머리는 쓸 줄이 아니다(v1 — 붙이기 · 표시만)
                                                                                 ("p69", "공동(기업명 작성) :", "label", ["p69", "p70", "p71"], [1, 2]), ("p75", "공동(기업명 작성) :", "label", ["p75", "p76", "p77"], [2, 2])]
    assert [v["slots"] for v in views] == [3, 3, 3] and views[1]["under"] == "추진 내용 작성" and views[1]["level"] == 4
    assert [(v["key"], v["under"], v["paras"]) for v in guide_write.chunk_views(bx["t97"])] == [("p103", "연구개발 목표", ["p104", "p105", "p109"]), ("p111", "연구개발 내용 및 범위", ["p112", "p113"])]
    cp = guide_write.chunk_paras
    assert cp(bx["t44"]) == ["p50", "p51", "p52"]                                                  # 고르지 않으면 같은 이름이 여럿인 덩이는 뺀다
    assert cp(bx["t44"], ["p75"]) == ["p75", "p76", "p77"] and cp(bx["t44"], ["p49", "p69"]) == ["p50", "p51", "p52", "p69", "p70", "p71"]   # 같은 이름의 덩이는 고른 것 하나만
    assert cp(bx["t44"], ["p69", "p75"]) == [] and cp(bx["t44"], ["p49", "p69", "p75"]) == ["p50", "p51", "p52"] and cp(bx["t44"], []) == [] and cp(bx["t44"], ["zz"]) == []
    assert cp(bx["t97"]) == ["p104", "p105", "p109", "p112", "p113"]
    # 같은 이름의 자리 둘 가운데 하나를 채운 뒤에도 둘을 함께 고르면 뺀다(채운 머리는 올린 원본의 글로 같은 이름을 가린다)
    blocks, orig = _filled("p69", "공동(기업명 작성) : 한국선급 목표")
    b2 = guide_write.boxes(blocks, FGRAPH, orig)["t44"]
    v2 = {v["key"]: v for v in guide_write.chunk_views(b2)}
    assert v2["p69"]["paras"] == ["p70", "p71"] and v2["p69"]["dup"] == [1, 2] and v2["p75"]["dup"] == [2, 2] and v2["p69"]["group"] == v2["p75"]["group"]
    assert cp(b2) == ["p50", "p51", "p52"] and cp(b2, ["p69", "p75"]) == [] and cp(b2, ["p75"]) == ["p75", "p76", "p77"]


def test_places_have_box_places_and_line_slots():
    ps = guide_write.places(FORM, FGRAPH, FIX)
    assert [(p["id"], p["kind"]) for p in ps] == [("f1", "head"), ("f2", "head"), ("f3", "head"), ("t44", "box"), ("t97", "box"), ("f4", "head"), ("t9", "table")]   # 상자 안의 표(t117)는 따로 서지 않는다 · 제목 상자(tb)는 자리가 아니다
    by = {p["id"]: p for p in ps}
    assert (by["f1"]["slot"], by["f2"]["slot"], by["f3"]["slot"], by["f4"]["slot"]) == ("label", "check", None, None)
    assert (by["f3"]["boxed"], by["f3"]["tables"], by["f4"]["boxed"], by["f4"]["tables"]) == (True, [], False, ["tb", "t9"])     # 상자 자리는 헤딩의 표 채우기 대상이 아니다
    t44, t97 = by["t44"], by["t97"]
    assert (t44["text"], t44["head"], t44["top"], t44["n"], t44["slots"], [v["key"] for v in t44["chunks"]]) == ("< 연구개발 과제명 작성 >", "f3", True, 0, 3, ["p49", "p69", "p75"])
    assert (t97["text"], t97["n"], t97["user"], t97["slots"]) == ("■ 다음연도 연구개발 계획", 2, True, 5)                         # 지침 = 그 상자 + 상자 안 표에 붙은 것 모두
    assert [g["text"] for g in t97["guides"]] == ["최종보고서 제출 기관은 작성하지 않아도 됨", "샘플 표는 지운다"] and by["t9"]["head"] == "f4"
    assert "fp" in t44 and "fp" not in API._place_view(t44) and API._place_view(t44)["chunks"] == t44["chunks"]                  # 지문 재료는 화면에 보내지 않는다
    blocks, orig = _filled("f1", "■ 연구개발과제명 : 시험 과제")
    again = {p["id"]: p for p in guide_write.places(blocks, FGRAPH, FIX, orig)}
    assert again["f1"]["slot"] == "filled" and {p["id"]: p for p in guide_write.places(blocks, FGRAPH, FIX)}["f1"]["slot"] is None   # 올린 원본을 알 때만 「이미 채운 줄」
    blocks, orig = _filled("p104", "    - 채운 목표")
    assert [v["paras"] for v in {p["id"]: p for p in guide_write.places(blocks, FGRAPH, FIX, orig)}["t97"]["chunks"]] == [["p105", "p109"], ["p112", "p113"]]


def test_request_and_selection_per_place_kind():
    by = {p["id"]: p for p in guide_write.places(FORM, FGRAPH, FIX)}
    rb = guide_write.request(by["t44"], "", "■ 세부 과제별 당해연도 성과목표 관리")
    assert rb.startswith("[지침 작성] 상자 「< 연구개발 과제명 작성 >」(id t44 · 헤딩 「■ 세부 과제별 당해연도 성과목표 관리」 아래) 자리를") and "제안(fill)" in rb and "상자 안의 표 · 그림 자리는 채우지 않습니다" in rb
    assert "같은 이름의 자리가 여럿" in rb and "write" not in rb and "tableFill" not in rb
    rl = guide_write.request(by["f1"], "", "")
    assert "줄 「■ 연구개발과제명 :」(id f1)" in rl and "제안(fill" in rl and "이 줄 아래에 새 문단을 넣지 않습니다" in rl and "write" not in rl
    rc = guide_write.request(by["f2"], "", "")
    assert "「□」 를 「■」 로" in rc and "fill" in rc and "**하나**" in rc
    rh = guide_write.request(by["f3"], "", "")
    assert "이 헤딩 아래의 상자는 따로 선 자리입니다" in rh and "제안(write" in rh and "표 채우기(tableFill)" not in rh           # 상자밖에 없는 헤딩 — 표 채우기를 권하지 않는다
    assert "따로 선 자리" not in guide_write.request(by["f4"], "", "") and "표 채우기(tableFill)" in guide_write.request(by["f4"], "", "")
    assert guide_write.selection(by["t44"]) == {"paras": [], "table": "t44", "range": None, "cursor": "t44"} and guide_write.selection(by["f1"])["cursor"] == "f1"
    assert len(guide_write.request({**by["t97"], "guides": [{"src": "doc", "kind": "k", "text": "가" * 9000}]}, "나" * 900, "헤딩", "다" * 1100)) <= guide_write.TEXT_MAX


def test_scope_per_place_kind(monkeypatch):
    import threading
    from types import SimpleNamespace
    s = SimpleNamespace(id="w0", lock=threading.Lock(), doc=SimpleNamespace(blocks=lambda: FORM))
    monkeypatch.setattr("app.heading_runs.graph", lambda sess: FGRAPH)
    monkeypatch.setattr(API, "uploaded_texts", lambda sess: {"f1": "■ 연구개발과제명 : "})
    by = {p["id"]: p for p in guide_write.places(FORM, FGRAPH, FIX)}
    assert API._scope(s, by["t44"], None, ["한국선급"]) == {"decided": ["한국선급"], "uploaded": {"f1": "■ 연구개발과제명 : "}, "types": {"fill"}, "paras": {"p50", "p51", "p52"}, "tables": set()}   # 고르지 않으면 같은 이름의 덩이는 뺀다
    assert API._scope(s, by["t44"], ["p75"], None)["paras"] == {"p75", "p76", "p77"} and API._scope(s, by["t44"], ["p69", "p75"], None)["paras"] == set() and API._scope(s, by["t44"], [], None)["paras"] == set()
    assert API._scope(s, {**by["t44"], "id": "gone"}, None, None)["paras"] == set()                                              # 그 사이 상자가 없어짐

    def g(p, k):
        return API._scope(s, p, None, None)[k]
    assert (g(by["t9"], "types"), g(by["t9"], "tables"), g(by["t9"], "paras")) == ({"tableFill"}, {"t9"}, set())
    assert (g(by["f1"], "types"), g(by["f1"], "paras"), g(by["f1"], "tables")) == ({"fill"}, {"f1"}, set()) and (g(by["f2"], "types"), g(by["f2"], "paras")) == ({"fill"}, {"f2"})
    assert (g({**by["f1"], "slot": "filled"}, "types"), g({**by["f1"], "slot": "filled"}, "paras")) == (set(), set())
    assert (g(by["f3"], "types"), g(by["f3"], "tables"), g(by["f4"], "tables"), g(by["f4"], "paras")) == ({"write", "tableFill"}, set(), {"tb", "t9"}, set())


def test_uploaded_texts_reads_the_uploaded_original(c, monkeypatch):
    from app.headings import iter_blocks
    s = server._sess(_doc(c))
    got = API.uploaded_texts(s)
    assert isinstance(got, dict) and got and all(isinstance(k, str) and isinstance(v, str) for k, v in got.items())
    with s.lock:
        now = {b["id"]: b.get("text") or "" for b in iter_blocks(s.doc.blocks()) if b.get("type") == "paragraph"}
    assert got == now and API.uploaded_texts(s) is got                                              # 갓 올린 문서 = 올린 원본 · 같은 파일이면 다시 읽지 않는다
    monkeypatch.setattr(API.works, "file_path", lambda wid, which: None)
    assert API.uploaded_texts(s) is None                                                            # 올린 원본 파일이 없으면 모른다(세션의 기준 바이트로 대신하지 않는다)


def test_run_chunks_filled_slots_and_zero_draft_reasons(c, monkeypatch):
    doc = _doc(c)
    blocks, orig = _filled("f1", "■ 연구개발과제명 : 시험 과제")
    places = guide_write.places(blocks, FGRAPH, FIX, orig)
    monkeypatch.setattr(API, "_places", lambda s: (places, 0))
    monkeypatch.setattr(API.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(API.guide_write, "boxes", lambda *a, **k: _BOXES(blocks, FGRAPH, orig))   # 올린 문서(견본)에는 상자가 없다 — 범위 셈이 읽는 상자만 견본 양식의 것으로
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "자료.md", "text": "한국선급 목표"}).json()["id"]
    _reviewed(doc, places, [mid], [{"key": "", "q": "누구의 몫", "a": "한국선급"}, {"key": "", "q": "분량", "a": form_review.SKIP}])
    url = f"/api/docs/{doc}/guide-write/run"
    for bad in ("x", {"t44": "p69"}, {"t44": [1]}, {"t44": {"p69": True}}):
        assert c.post(url, json={"places": ["t44"], "materials": [mid], "chunks": bad}).status_code == 400
    seen = {}

    def turn(doc_id, body, scope=None):
        seen[body["selection"]["cursor"]] = (body, scope)
        if "id t9" in body["text"]:
            return {"turn": {"id": "t3", "reply": "넣을 자리가 아닙니다", "proposals": [], "dropped": [{"action": 0, "type": "tableFill", "why": "이 자리에서는 채우지 않는 표입니다"}]}}
        return {"turn": {"id": "t4", "reply": "자료에 없습니다", "proposals": [], "dropped": []}}
    monkeypatch.setattr(doc_agent_api, "_turn", turn, raising=False)
    r = c.post(url, json={"places": ["f1", "f3", "f4", "t44", "t97", "t9"], "materials": [mid], "chunks": {"t44": []}})
    assert r.status_code == 200 and r.json()["run"]["chunks"] == {"t44": []} and "decided" not in r.json()["run"]
    by = {i["id"]: i for i in _wait(c, doc)["items"]}
    assert (by["f1"]["state"], by["f1"]["why"]) == ("none", "filled") and "f1" not in seen                 # 이미 채운 줄 — LLM 을 부르지 않는다
    assert (by["t44"]["state"], by["t44"]["why"]) == ("none", "noslot") and "t44" not in seen               # 쓸 자리를 하나도 고르지 않은 상자
    assert (by["t9"]["why"], by["t9"]["dropped"], by["t9"]["note"]) == ("dropped", 1, "이 자리에서는 채우지 않는 표입니다") and (by["f4"]["why"], by["f4"]["dropped"], by["f4"]["note"]) == ("noaction", 0, "")
    assert (by["f3"]["state"], by["f3"]["why"]) == ("none", "boxed") and "f3" not in seen                   # 쓸 자리가 아래 상자에 있는 헤딩 — LLM 을 부르지 않는다(상자 내용을 헤딩 아래에 또 쓰지 않게: astra 3차)
    body, scope = seen["t97"]                                                                               # 고르지 않은 상자 = 같은 이름이 여럿인 덩이를 뺀 모두
    assert body["selection"] == {"paras": [], "table": "t97", "range": None, "cursor": "t97"} and scope["types"] == {"fill"} and scope["paras"] == {"p104", "p105", "p109", "p112", "p113"}
    assert scope["decided"] == ["한국선급"] and seen["f4"][1]["types"] == {"write", "tableFill"} and seen["f4"][1]["after"] == {"f4"}   # 「자료대로」 는 정한 값이 아니다 · 헤딩의 글은 그 헤딩 줄 뒤에만
    r = c.post(url, json={"places": ["t44"], "materials": [mid], "chunks": {"t44": ["p75", "p49"]}})
    assert r.status_code == 200 and _wait(c, doc)["items"][0]["why"] == "noaction" and seen["t44"][1]["paras"] == {"p50", "p51", "p52", "p75", "p76", "p77"}


def test_run_is_refused_when_the_plan_no_longer_fits(c, monkeypatch):
    doc = _doc(c)
    places = guide_write.places(FORM, FGRAPH, FIX)
    monkeypatch.setattr(API, "_places", lambda s: (places, 0))
    monkeypatch.setattr(API.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(doc_agent_api, "_turn", lambda doc_id, body, scope=None: {"turn": {"id": "t", "reply": "", "proposals": []}}, raising=False)
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "가.md", "text": "가 기관 자료"}).json()["id"]
    mid2 = c.post(f"/api/docs/{doc}/agent/material", json={"name": "나.md", "text": "나 기관 자료"}).json()["id"]
    _reviewed(doc, places, [mid])
    url = f"/api/docs/{doc}/guide-write/run"
    for mats in ([mid2], [mid, mid2]):                                                                       # 계획을 세운 자료와 다르다(다른 기관의 자료 · 하나 더)
        r = c.post(url, json={"places": ["f4"], "materials": mats})
        assert r.status_code == 409 and "작성 계획을 세운 자료와 고른 자료가 다릅니다" in r.json()["detail"]
    changed = [{**p, "guides": [{"src": "user", "kind": "사용자 지침", "text": "붙임은 두 쪽"}]} if p["id"] == "f4" else p for p in places]
    monkeypatch.setattr(API, "_places", lambda s: (changed, 0))
    r = c.post(url, json={"places": ["f4", "f3"], "materials": [mid]})
    assert r.status_code == 409 and "바뀐 자리 1곳(「■ 붙임」)" in r.json()["detail"]                        # 고른 자리가 검토한 뒤 바뀜 — 그 자리만 센다
    assert c.post(url, json={"places": ["f3"], "materials": [mid]}).status_code == 200 and _wait(c, doc)["state"] == "done"   # 무관한 자리가 바뀐 것은 막지 않는다
    swapped = [{**p, "fp": [[i, k, {"p102": "연구개발 내용 및 범위", "p110": "연구개발 목표"}.get(i, raw)] for i, k, raw, _lv in p["fp"]]} if p["id"] == "t97" else p for p in places]
    monkeypatch.setattr(API, "_places", lambda s: (swapped, 0))
    r = c.post(url, json={"places": ["t97"], "materials": [mid]})
    assert r.status_code == 409 and "바뀐 자리 1곳" in r.json()["detail"]                                     # 상자 안 고정 제목을 맞바꿈(id · 덩이 수는 같다 — astra 2차 G11)
    new = [*places, {**places[0], "id": "f9", "text": "새 헤딩", "fp": "새 헤딩"}]
    monkeypatch.setattr(API, "_places", lambda s: (new, 0))
    assert c.post(url, json={"places": ["f9"], "materials": [mid]}).status_code == 409                       # 검토 뒤에 생긴 자리


def test_stage_reset_clears_only_that_stage(c):
    """단계 초기화(spec_양식작성 ② §6-1 — 2026-11-24 사용자 "준비/자료,작성 단계를 따로 두고 단계별로 … 초기화"): 작성 = 초안 · 작성 계획을 비우고 문서를 올린 원본으로(자료 · 양식 검토 · 정한 답은 남김) ·
    자료 준비 = 이 문서의 자료만 · 준비 = 작업 내용 초기화에서 자료만 남김(`…/reset?keep=materials`)."""
    doc = _doc(c)
    wid = server._sess(doc).id
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"text": "자료 글 — 한국선급 2차년도 목표"}).json()
    mats = lambda: [m["id"] for m in c.get(f"/api/docs/{doc}/agent").json()["materials"]]  # noqa: E731
    assert len(mats()) == 1, mid
    store = A.Store(wid)
    store.save_turn({"id": store.new_turn_id(), "at": 1.0, "request": {"text": "쓰기"}, "reply": "초안", "proposals": []})
    form_review_api._save(wid, {"review": {"summary": "요약", "places": {"h1": {"how": "개조식", "needs": "목표", "use": "자료 1절", "gap": ""}}, "questions": [], "topics": [{"name": "목표"}], "materials": mats()},
                                "decided": [{"key": "q1", "q": "몇 차년도?", "a": "2차년도"}]})
    from app.headings import iter_blocks
    flat = lambda: list(iter_blocks(c.get(f"/api/docs/{doc}").json()["blocks"]))  # noqa: E731 — 표 칸 안의 문단까지
    para = next(b for b in flat() if b.get("type") == "paragraph" and (b.get("text") or "").strip())
    assert c.patch(f"/api/docs/{doc}/blocks/{para['id']}", json={"text": para["text"] + " 고친 글"}).status_code == 200
    assert c.post(f"/api/docs/{doc}/form-write/reset", json={"stage": "nope"}).status_code == 400

    r = c.post(f"/api/docs/{doc}/form-write/reset", json={"stage": "write"})
    assert r.status_code == 200 and r.json() == {"stage": "write", "reverted": True, "turns": 1, "plan": True}, r.text
    after = next(b for b in flat() if b["id"] == para["id"])
    assert after["text"] == para["text"] and c.get(f"/api/docs/{doc}/agent").json()["turns"] == [] and len(mats()) == 1   # 문서는 올린 원본 · 초안은 비움 · 자료는 그대로
    st = form_review_api.load(wid)
    assert not form_review.planned(st["review"]) and st["review"]["places"]["h1"] == {"how": "개조식", "needs": "목표", "use": "", "gap": ""}   # 작성 계획만 비운다 — 양식 검토 · 찾을 테마 · 정한 답은 남는다
    assert st["review"]["topics"] == [{"name": "목표"}] and [d["a"] for d in st["decided"]] == ["2차년도"]
    assert c.post(f"/api/docs/{doc}/form-write/reset", json={"stage": "write"}).json() == {"stage": "write", "reverted": False, "turns": 0, "plan": False}   # 두 번째 — 되돌릴 것이 없다

    r = c.post(f"/api/works/{wid}/reset?keep=materials")   # 준비 — 올린 직후로 · 자료만 남김
    assert r.status_code == 200 and len(mats()) == 1 and form_review_api.load(wid)["review"] is None, r.text
    assert c.post(f"/api/works/{wid}/reset?keep=nope").status_code == 400

    assert c.post(f"/api/docs/{doc}/form-write/reset", json={"stage": "material"}).json() == {"stage": "material", "materials": 1} and mats() == []
    API._RUNS[wid] = {"state": "running"}
    assert c.post(f"/api/docs/{doc}/form-write/reset", json={"stage": "material"}).status_code == 409   # 초안을 받는 중에는 못 한다
