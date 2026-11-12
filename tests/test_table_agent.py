"""헤딩 추출 — 표 도구(spec_헤딩_추출 ② §10): 작성요령 추출(표 안 안내 칸 · 표 앞뒤 안내 문단) · 표 지침·사용자 수식 저장(version·409·검사) · 에이전트 입력 묶음 글 · API."""
import copy
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_extract as E
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, server, table_agent, works
from app import heading_tables as HT
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL = SAMPLES / "기술수요조사서.hwpx"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    table_agent._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()
    table_agent._MEMORY.clear()


# ---- 합성 1단계(test_headings_tables 의 Tab 과 같은 계약) ------------------------------------------------------------

def _para(n, text, kind="plain", area="body", path=None, pid=None):
    return {"id": pid or f"p{n}", "n": n, "kind": kind, "text": text, "blank": False, "fmt": "S0", "area": area,
            "char": {"text": {"bold": False, "sizePt": 10}, "letter": None}, "path": path or []}


def _table(tid, host, start, cells, rows=None, cols=None):
    """cells = [(row, col, text, kind, rs, cs)] → (문단 목록, 다음 n)."""
    rows = rows or max(c[0] + (c[4] if len(c) > 4 else 1) for c in cells)
    cols = cols or max(c[1] + (c[5] if len(c) > 5 else 1) for c in cells)
    out, n = [], start
    for i, c in enumerate(cells):
        row, col, text = c[0], c[1], c[2]
        kind = c[3] if len(c) > 3 else ("empty" if not text else "plain")
        rs, cs = (c[4] if len(c) > 4 else 1), (c[5] if len(c) > 5 else 1)
        path = [{"t": "tbl", "id": tid, "rows": rows, "cols": cols, "cells": len(cells), "key": 1, "host": host},
                {"t": "cell", "id": f"{tid}c{i + 1}", "row": row, "col": col, "rs": rs, "cs": cs, "fill": None, "key": 2}]
        out.append(_para(n, text, kind, "cell", path))
        n += 1
    return out, n


def _stage1():
    """「※ 작성 요령」 앞 문단 2개 → 표(안에 안내 칸 1) → 「※」 뒤 문단 1 + 보통 글(끝) → 다음 표의 개체 문단."""
    paras = [_para(0, "1. 연구개발비", "marker"), _para(1, "※ 금액은 천원 단위로 적는다", "note"), _para(2, "☞ 합계는 행·열을 모두 맞춘다", "plain"), _para(3, "", "object", pid="p3")]
    cells = [(0, 0, "구분", "plain"), (0, 1, "1차년도", "plain"), (1, 0, "현금", "plain"), (1, 1, "1,000", "data"), (2, 0, "현물", "plain"), (2, 1, "2,000", "data"),
             (3, 0, "합계", "plain"), (3, 1, "3,000", "data"), (4, 0, "※ 현물은 인건비만 적는다", "note", 1, 2)]
    tbl, n = _table("t1", "p3", 4, cells)
    paras += tbl
    paras += [_para(n, "", "empty"), _para(n + 1, "※ 뒤 안내 — 비율은 소수 첫째 자리", "note"), _para(n + 2, "다음 절의 보통 글이다.", "plain"), _para(n + 3, "※ 다음 표의 안내(여기 안 듦)", "note"),
              _para(n + 4, "", "object", pid=f"p{n + 4}")]
    tbl2, m = _table("t2", f"p{n + 4}", n + 5, [(0, 0, "a"), (0, 1, "b"), (1, 0, "c"), (1, 1, "d")])
    paras += tbl2
    return {"paras": paras, "labels": {}}


def _no_llm(jobs):
    pytest.fail("LLM 을 부르면 안 됨")


def test_table_notes_before_cell_after():
    s1 = _stage1()
    out = HT.build(s1, use_llm=False, ask=_no_llm)
    t1 = out["tables"][0]
    assert t1["id"] == "t1"
    notes = t1["notes"]
    where = [n["where"] for n in notes]
    assert where == ["cell", "before", "before", "after"], notes
    assert notes[0]["text"].startswith("※ 현물은") and notes[0]["cell"] == "t1c9" and notes[0]["para"] == "p12"
    assert [n["text"] for n in notes if n["where"] == "before"] == ["※ 금액은 천원 단위로 적는다", "☞ 합계는 행·열을 모두 맞춘다"]  # 문서 순
    assert notes[3]["text"].startswith("※ 뒤 안내") and notes[3]["para"] == "p14"
    # 뒤 안내는 보통 글에서 끊기고, 다음 표 앞의 「※」 는 t2 의 「앞 안내」
    t2 = out["tables"][1]
    assert [n["where"] for n in t2["notes"]] == ["before"] and t2["notes"][0]["text"].startswith("※ 다음 표의 안내")
    assert out["version"] == 2  # 키 추가만


def test_table_notes_skip_other_area_and_limits():
    s1 = _stage1()
    s1["paras"][1]["area"] = "cell"  # 다른 흐름의 안내는 안 든다 → 그 자리에서 끊김(앞 안내는 ☞ 하나)
    out = HT.build(s1, use_llm=False, ask=_no_llm)
    befores = [n for n in out["tables"][0]["notes"] if n["where"] == "before"]
    assert [n["text"][:1] for n in befores] == ["☞"]
    assert HT.table_notes({"paras": []}, {"id": "x", "cells": [], "n": 0, "host": None}) == []


# ---- 저장 ------------------------------------------------------------------------------------------------------

def test_store_memory_when_works_off(monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    assert works.folder("abc123def456") is None
    wid = "abc123def456"
    assert table_agent.get(wid, "t1") == {"instructions": "", "rules": "", "formulas": {}, "version": 0, "updated": None}
    r = table_agent.save(wid, "t1", instructions="천원 단위", formulas={"B4": "=SUM(B2:B3)", "C2": ""})
    assert r["version"] == 1 and r["formulas"] == {"B4": "=SUM(B2:B3)", "C2": ""} and r["updated"]
    assert table_agent.get(wid, "t1")["instructions"] == "천원 단위"
    with pytest.raises(R.StaleVersion):
        table_agent.save(wid, "t1", instructions="다시", expect=0)
    r2 = table_agent.save(wid, "t1", instructions="다시", expect=1)
    assert r2["version"] == 2 and r2["formulas"] == {"B4": "=SUM(B2:B3)", "C2": ""}  # 주지 않은 항목은 그대로
    c = table_agent.save(wid, table_agent.COMMON, instructions="모든 표")
    assert c == {"instructions": "모든 표", "rules": "", "version": 1, "updated": c["updated"]}
    allv = table_agent.all_tables(wid)
    assert allv["common"]["instructions"] == "모든 표" and set(allv["tables"]) == {"t1"}


def test_store_validation():
    wid = "abc123def456"
    with pytest.raises(ValueError):
        table_agent.save(wid, "t1", instructions="x" * (table_agent.TEXT_MAX + 1))
    with pytest.raises(ValueError):
        table_agent.save(wid, "t1", formulas={"b4": "=1"})  # 소문자 주소
    with pytest.raises(ValueError):
        table_agent.save(wid, "t1", formulas={"B4": "SUM(B2)"})  # = 없음
    with pytest.raises(ValueError):
        table_agent.save(wid, table_agent.COMMON, formulas={"B4": "=1"})
    with pytest.raises(ValueError):
        table_agent.save(wid, "t1", instructions="x", expect="one")
    with pytest.raises(KeyError):
        table_agent.save(wid, "../x", instructions="x")
    with pytest.raises(KeyError):
        table_agent.get(wid, "t 1")


def test_store_on_disk_and_log(tmp_path):
    wid = "0123456789ab"
    assert works.create(wid, "a.hwpx", "hwpx", b"x") is not None
    r = table_agent.save(wid, "t5", instructions="지침", formulas={"A1": "=1+1"})
    p = works.folder(wid) / "tables" / "t5.json"
    assert p.is_file() and works._read_json(p) == r
    assert table_agent.get(wid, "t5") == r and (wid, "t5") not in table_agent._MEMORY
    ev = [e for e in works.events(wid) if e["kind"] == "tableGuide"]
    assert ev and ev[-1]["table"] == "t5" and ev[-1]["chars"] == 2 and ev[-1]["formulas"] == 1 and ev[-1]["version"] == 1
    assert table_agent.all_tables(wid)["tables"]["t5"]["version"] == 1
    # 작업 폴더가 지워졌으면 메모리로
    works.delete(wid)
    r2 = table_agent.save(wid, "t5", instructions="지움 뒤")
    assert r2["version"] == 1 and (wid, "t5") in table_agent._MEMORY  # 디스크 기록이 사라져 0 부터


# ---- 묶음 글 ----------------------------------------------------------------------------------------------------

def test_prompt_sections():
    s1 = _stage1()
    out = HT.build(s1, use_llm=False, ask=_no_llm)
    tb = out["tables"][0]
    tb["owner"] = {"id": "n1", "para": "p0", "text": "1. 연구개발비", "role": "heading", "tplNo": 1, "level": 1, "path": ["0. 개요"], "source": "stage2",
                   "division": {"id": "n2", "para": "p9", "text": "[주관연구개발기관]", "basis": ["org"]}}
    common = {"instructions": "모든 표 공통", "version": 1}
    own = {"instructions": "이 표만", "version": 2, "formulas": {"B4": "=SUM(B2:B3)", "C2": ""}}
    txt = table_agent.prompt(tb, common, own)
    for s in ("[표 식별]", "표 t1 · 5행×2열", "소속: 1. 연구개발비 (T1 L1) · 출처 2단계 그래프", "경로: 0. 개요", "구분 라벨: [주관연구개발기관] (기관)",
              "[작성요령(문서에서)]", "- (표 안) ※ 현물은", "- (표 앞) ※ 금액은", "- (표 뒤) ※ 뒤 안내", "[공통 지침]\n모든 표 공통", "[이 표 지침]\n이 표만",
              "[표 구조]", "격자(주소|역할|글):", "A1|", "[수식]", "[사용자 수식]", "- B4 =SUM(B2:B3)", "- C2 (수식 끔)"):
        assert s in txt, s
    none = table_agent.prompt(None, {"instructions": ""}, {"instructions": "", "formulas": {}}, tid="t9")
    assert "표 t9 — 3단계 표 구조 결과가 없어" in none and "(문서에서 찾은 작성요령 없음)" in none and "[공통 지침]\n(없음)" in none and "[표 구조]" not in none
    assert table_agent.ident(tb)["cells"] == 9 and table_agent.ident(None) is None


def test_rnd_notes_find_guidelines():
    rnd = E.extract(HwpxDoc(RND.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="rnd", tol=G.parse_tolerance(G.default_text("tolerance")))
    out = HT.build(rnd, use_llm=False, ask=_no_llm)
    with_notes = [t for t in out["tables"] if t["notes"]]
    assert len(with_notes) >= 10, len(with_notes)  # 양식엔 「※」 안내 문단이 많다
    assert all(n["where"] in ("before", "cell", "after") and n["text"] for t in with_notes for n in t["notes"])
    assert all(len(n["text"]) <= 300 for t in with_notes for n in t["notes"])


# ---- API --------------------------------------------------------------------------------------------------------

def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_api_agent_get_put_and_errors():
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        d = _upload(c, SMALL)
        assert c.get(f"/api/docs/{d}/headings/tables/t999/agent").status_code == 404
        assert c.get(f"/api/docs/{d}/headings/tables/p1/agent").status_code == 404  # 문단은 표가 아니다
        a = c.get(f"/api/docs/{d}/headings/tables/agents").json()
        assert a == {"common": {"instructions": "", "rules": "", "version": 0, "updated": None}, "tables": {}}
        sess = server.DOCS[d]
        heading_runs.run_sync(sess, 3, False)
        tid = heading_runs.summary(sess)["stage3"]["tables"][1]["id"]
        g = c.get(f"/api/docs/{d}/headings/tables/{tid}/agent").json()
        assert g["table"] == tid and g["stage3"] is True and g["ident"]["id"] == tid and "owner" in g["ident"] and isinstance(g["notes"], list)
        assert g["own"]["version"] == 0 and g["common"]["version"] == 0 and f"표 {tid} ·" in g["prompt"] and "[표 구조]" in g["prompt"]
        r = c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"instructions": "천원 단위", "formulas": {"B2": "=A2*2"}, "version": 0})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["own"]["instructions"] == "천원 단위" and v["own"]["formulas"] == {"B2": "=A2*2"} and v["own"]["version"] == 1 and "[이 표 지침]\n천원 단위" in v["prompt"]
        assert "- B2 =A2*2" in v["prompt"]
        assert c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"instructions": "x", "version": 0}).status_code == 409
        assert c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"formulas": {"b2": "=1"}}).status_code == 400
        assert c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"instructions": 5}).status_code == 400
        assert c.put(f"/api/docs/{d}/headings/tables/_common/agent", json={"formulas": {"B2": "=1"}}).status_code == 400
        cm = c.put(f"/api/docs/{d}/headings/tables/_common/agent", json={"instructions": "모든 표"}).json()
        assert cm["table"] == "_common" and cm["common"]["instructions"] == "모든 표" and cm["own"] is None and cm["stage3"] is False and "[공통 지침]\n모든 표" in cm["prompt"]
        a2 = c.get(f"/api/docs/{d}/headings/tables/agents").json()
        assert a2["common"]["version"] == 1 and a2["tables"][tid]["formulas"] == {"B2": "=A2*2"}
        # 3단계 없는 표 id 도(문서의 표면) 지침은 저장된다 · 기록 탭 줄
        other = heading_runs.summary(sess)["stage3"]["tables"][0]["id"]
        assert c.put(f"/api/docs/{d}/headings/tables/{other}/agent", json={"instructions": "둘째"}).json()["own"]["version"] == 1
        log = c.get(f"/api/works/{d}/log").json()
        assert [e for e in log["events"] if e["kind"] == "tableGuide" and e["table"] == tid]
        assert c.get(f"/api/docs/{d}/headings/tables/{tid}/xlsx").status_code == 200  # 기존 끝점은 그대로
    finally:
        server.DOCS.clear()


def test_api_agent_persists_across_reopen():
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        d = _upload(c, SMALL)
        sess = server.DOCS[d]
        heading_runs.run_sync(sess, 3, False)
        tid = heading_runs.summary(sess)["stage3"]["tables"][0]["id"]
        assert c.put(f"/api/docs/{d}/headings/tables/{tid}/agent", json={"instructions": "유지", "formulas": {"A1": "=1"}}).status_code == 200
        server.DOCS.clear()  # 메모리에서 비움 → 작업 폴더에서 다시 연다
        g = c.get(f"/api/docs/{d}/headings/tables/{tid}/agent").json()
        assert g["own"]["instructions"] == "유지" and g["own"]["formulas"] == {"A1": "=1"} and g["own"]["version"] == 1
        time.sleep(0.01)
    finally:
        server.DOCS.clear()
