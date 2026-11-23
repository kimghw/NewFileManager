"""헤딩 추출 3단계 — 표 구조(spec_헤딩_추출 ② §8): 표·칸 모으기, 칸 성격, 띠(서브 테이블) 나누기, 헤더 행·열, 역할, 헤더 트리·필드 경로,
T 호출 적용·검증(가짜 LLM), 묶음, 실행·API. LLM 은 늘 끈다(NFM_LLM_BACKEND=off) — 가짜 ask(jobs) 로 답한다."""
import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_extract as E
from app import heading_guides as G
from app import heading_llm as HL
from app import heading_rules as R
from app import heading_runs, server, works
from app import heading_tables as HT
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
SMALL = SAMPLES / "기술수요조사서.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _tol():
    return G.parse_tolerance(G.default_text("tolerance"))


@pytest.fixture(scope="module")
def rnd():
    return E.extract(HwpxDoc(RND.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="rnd", tol=_tol())


@pytest.fixture(scope="module")
def small():
    return E.extract(HwpxDoc(SMALL.read_bytes()), store=copy.deepcopy(EMPTY), doc_key="small", tol=_tol())


# ---- 합성 표(1단계 레코드 꼴) ------------------------------------------------------------------------------------

class Tab:
    """합성 표 — cell(row, col, text, …) 로 칸을 더하고 stage1() 로 1단계 결과 꼴을 만든다. 칸 id = t<표>c<번호>."""
    _n = [0]

    def __init__(self, tid="t1", rows=None, cols=None, host="p0"):
        self.tid, self.rows, self.cols, self.host, self.cells = tid, rows, cols, host, []

    def cell(self, row, col, text="", rs=1, cs=1, kind=None, fill=None, bold=False, blank=False, extra=()):
        cid = f"{self.tid}c{len(self.cells) + 1}"
        if kind is None:
            kind = "empty" if not text else "plain"
        paras = [(text, kind, blank)] + list(extra)
        self.cells.append({"id": cid, "row": row, "col": col, "rs": rs, "cs": cs, "fill": fill, "bold": bold, "paras": paras})
        return cid

    def paras(self, start_n=0):
        rows = self.rows or max(c["row"] + c["rs"] for c in self.cells)
        cols = self.cols or max(c["col"] + c["cs"] for c in self.cells)
        out, n = [], start_n
        for c in self.cells:
            for text, kind, blank in c["paras"]:
                n += 1
                out.append({"id": f"p{n}", "n": n, "kind": kind, "text": text, "blank": blank, "fmt": "S1", "area": "cell",
                            "char": {"text": {"bold": c["bold"], "sizePt": 10}, "letter": None},
                            "path": [{"t": "tbl", "id": self.tid, "rows": rows, "cols": cols, "cells": len(self.cells), "key": 1, "host": self.host},
                                     {"t": "cell", "id": c["id"], "row": c["row"], "col": c["col"], "rs": c["rs"], "cs": c["cs"], "fill": c["fill"], "key": 2}]})
        return out


def stage1(*tabs, before=None):
    paras = []
    if before:
        paras.append({"id": "p0", "n": 0, "kind": "marker", "text": before, "blank": False, "fmt": "S0", "area": "body", "char": {"text": {}, "letter": None}, "path": []})
    for t in tabs:
        paras += t.paras(len(paras))
    return {"paras": paras, "labels": {}}


def _no_llm(jobs):
    pytest.fail("LLM 을 부르면 안 됨")


def roles(out, tid=None):
    t = out["tables"][0] if tid is None else next(x for x in out["tables"] if x["id"] == tid)
    return {c["text"] or c["id"]: c["role"] for c in t["cells"]}, t


def by_text(t, text):
    return next(c for c in t["cells"] if c["text"] == text)


def matrix_tab():
    """2단 열헤더 + 순번·이름 행헤더 매트릭스(음영 헤더):
    구분 | 내용 | 추진 일정(1x4) ; ^ | ^ | 1단계(1x2) | 2단계(1x2) ; ^ | ^ | 1차 | 2차 | 1차 | 2차 ; 1 | 계획수립 | . . . . ; 2 | 설계 | . . . ."""
    t = Tab("t1")
    t.cell(0, 0, "구분", rs=3, fill="#D9D9D9")
    t.cell(0, 1, "내용", rs=3, fill="#D9D9D9")
    t.cell(0, 2, "추진 일정", cs=4, fill="#D9D9D9")
    t.cell(1, 2, "1단계", cs=2, fill="#D9D9D9")
    t.cell(1, 4, "2단계", cs=2, fill="#D9D9D9")
    for i, name in enumerate(["1차년도", "2차년도", "1차년도", "2차년도"]):
        t.cell(2, 2 + i, name, fill="#D9D9D9")
    t.cell(3, 0, "1", kind="data")
    t.cell(3, 1, "계획수립 및 자료조사")
    for i in range(4):
        t.cell(3, 2 + i, "")
    t.cell(4, 0, "2", kind="data")
    t.cell(4, 1, "설계도면 작성")
    for i in range(4):
        t.cell(4, 2 + i, "")
    return t


def form_tab():
    """키-값 양식: 기관명 | [ ] | 사업자등록번호 | [ ] ; 주소(2x1) | (우) | 법인등록번호 | [ ] ; ^ | ^ | 기관유형 | [ ]"""
    t = Tab("t2")
    t.cell(0, 0, "기관명", fill="#EEEEEE")
    t.cell(0, 1, "")
    t.cell(0, 2, "사업자등록번호", fill="#EEEEEE")
    t.cell(0, 3, "")
    t.cell(1, 0, "주소", rs=2, fill="#EEEEEE")
    t.cell(1, 1, "(우)", rs=2)
    t.cell(1, 2, "법인등록번호", fill="#EEEEEE")
    t.cell(1, 3, "")
    t.cell(2, 2, "기관유형", fill="#EEEEEE")
    t.cell(2, 3, "")
    return t


# ---- 1. 모으기 · 성격 ------------------------------------------------------------------------------------------

def test_collect_small(small):
    tables = HT.collect(small)
    assert [t["id"] for t in tables] == ["t1", "t8"] and tables[1]["rows"] == 18 and tables[1]["cols"] == 11 and len(tables[1]["cells"]) == 40
    t8 = tables[1]
    guide = [c for c in t8["cells"] if c["textFull"].startswith("[작성가이드라인]")]
    assert len(guide) == 8 and all(c["nature"] == "note" and c["cs"] == 10 for c in guide)
    first = next(c for c in t8["cells"] if c["textFull"].startswith("제안기술 분류"))
    assert first["shaded"] and first["bold"] and first["nature"] == "header" and first["rs"] == 3 and first["paras"]
    paren = next(c for c in t8["cells"] if c["textFull"].startswith("("))
    assert paren["nature"] == "field"
    assert all(c["fill"] is None or c["fill"].startswith("#") for c in t8["cells"])  # 1단계 칸 사슬의 fill


def test_collect_counts_rnd(rnd):
    """여러 칸 표만(1칸 상자 제외), 칸 id 는 표마다 유일, 중첩 표는 바깥 칸에 기록."""
    tables = HT.collect(rnd)
    assert len(tables) == 135 and sum(len(t["cells"]) for t in tables) == 5797
    for t in tables:
        assert len({c["id"] for c in t["cells"]}) == len(t["cells"]) and t["rows"] >= 1 and t["cols"] >= 1
    nested = [t for t in tables if t["depth"] > 1]
    assert nested and all(t["parentCell"] for t in nested)
    hosts = {c["id"]: c for t in tables for c in t["cells"] if c["nested"]}
    assert all(t["parentCell"] in hosts and t["id"] in hosts[t["parentCell"]]["nested"] for t in nested)
    assert all(not any(x["t"] == "tbl" and x.get("cells") == 1 and _tid(x) in {t["id"] for t in tables} for x in r["path"]) for r in rnd["paras"])


def _tid(x):
    return x.get("id") or f"k{x.get('key')}"


def test_nature_rules():
    t = Tab("t9")
    t.cell(0, 0, "YYYY. MM.", kind="placeholder")
    t.cell(0, 1, "0,000,000", kind="data")
    t.cell(0, 2, "[ ] 일반형", kind="label")
    t.cell(0, 3, "※ 작성 시 유의", kind="note")
    t.cell(0, 4, "1.", kind="marker", blank=True)
    t.cell(0, 5, "이 표는 연구개발의 목표를 적는 곳이며 각 항목은 상세히 기술한다.")
    t.cell(0, 6, "성명", bold=True)
    t.cell(0, 7, "성명")
    t.cell(0, 8, "0,000", kind="data", fill="#CCCCCC")
    t.cell(0, 9, "")
    t.cell(0, 10, "", fill="#CCCCCC")
    t.cell(0, 11, "◦ 첫째 항목", kind="marker", extra=[("◦ 둘째 항목", "marker", False)])
    tb = HT.collect(stage1(t))[0]
    nat = [c["nature"] for c in tb["cells"]]
    assert nat == ["field", "field", "field", "note", "text", "field", "headish", "text", "header", "empty", "header", "field"]


# ---- 2. 초안 — 띠 · 헤더 행/열 · 역할 · 경로 ------------------------------------------------------------------------

def test_draft_matrix_roles_and_paths():
    out = HT.build(stage1(matrix_tab(), before="2-3. 수행일정"), use_llm=False, ask=_no_llm)
    rl, t = roles(out)
    assert len(t["subtables"]) == 1 and t["subtables"][0]["kind"] == "matrix" and t["subtables"][0]["headerRows"] == 3 and t["subtables"][0]["headerCols"] == 2
    assert rl["구분"] == rl["내용"] == "corner" and rl["추진 일정"] == rl["1단계"] == rl["2단계"] == rl["1차년도"] == "colhead"
    assert rl["1"] == rl["계획수립 및 자료조사"] == rl["설계도면 작성"] == "rowhead"
    assert by_text(t, "1단계")["parent"] == by_text(t, "추진 일정")["id"] and by_text(t, "계획수립 및 자료조사")["parent"] == by_text(t, "1")["id"]
    first_year = [c for c in t["cells"] if c["text"] == "1차년도"]
    assert [c["parent"] for c in first_year] == [by_text(t, "1단계")["id"], by_text(t, "2단계")["id"]]
    f = next(c for c in t["cells"] if c["role"] == "field" and c["row"] == 4 and c["col"] == 5)
    name = lambda cid: next(c["text"] for c in t["cells"] if c["id"] == cid)  # noqa: E731
    assert [name(i) for i in f["colPath"]] == ["추진 일정", "2단계", "2차년도"] and [name(i) for i in f["rowPath"]] == ["2", "설계도면 작성"]
    assert t["before"] == "2-3. 수행일정" and t["counts"]["field"] == 8 and not t["issues"]
    core = {k: v for k, v in out["counts"].items() if k not in ("basis", "basisTables", "calc", "owners")}  # 표 의미(§9) 키는 test_headings_calc 에서
    assert core == {"tables": 1, "cells": 21, "subtables": 1, "split": 0, "roles": {"corner": 2, "colhead": 7, "rowhead": 4, "field": 8}, "repeats": 0,
                    "changed": 0, "issues": 0, "nested": 0, "tempTables": 0}  # tempTables = 표 구조에서 뺀 TEMP 표(§15 — test_headings_temp)
    assert out["llm"]["requested"] is False and out["llm"]["calls"] == 0 and "_calls" in out


def test_draft_form_keys_anywhere_in_row():
    out = HT.build(stage1(form_tab()), use_llm=False, ask=_no_llm)
    rl, t = roles(out)
    s = t["subtables"][0]
    assert s["kind"] == "form" and s["headerRows"] == 0 and s["headerCols"] == 1
    assert rl["기관명"] == rl["주소"] == rl["사업자등록번호"] == rl["법인등록번호"] == rl["기관유형"] == "rowhead"
    assert rl["(우)"] == "field"
    val = next(c for c in t["cells"] if c["row"] == 2 and c["col"] == 3)
    assert val["rowPath"] == [by_text(t, "주소")["id"], by_text(t, "기관유형")["id"]] and val["colPath"] == []  # 왼쪽에서 행 범위를 품은 「주소」 가 부모(④ 후속)
    addr = next(c for c in t["cells"] if c["text"] == "(우)")
    assert addr["rowPath"] == [by_text(t, "주소")["id"]]


def test_bands_title_restart_and_spacer():
    """제목 행(전체 너비) → 키-값 → 헤더 행이 다시 시작 → 매트릭스 → 빈 전체 너비 행 → 안내 글."""
    t = Tab("t3")
    t.cell(0, 0, "< 요 약 문 >", cs=4, bold=True)
    t.cell(1, 0, "사업명", fill="#EEEEEE")
    t.cell(1, 1, "", cs=3)
    t.cell(2, 0, "과제명", fill="#EEEEEE")
    t.cell(2, 1, "", cs=3)
    t.cell(3, 0, "기관명", fill="#EEEEEE")
    t.cell(3, 1, "책임자", fill="#EEEEEE")
    t.cell(3, 2, "직위", fill="#EEEEEE")
    t.cell(3, 3, "전화", fill="#EEEEEE")
    for r in (4, 5):
        for c in range(4):
            t.cell(r, c, "")
    t.cell(6, 0, "", cs=4)
    t.cell(7, 0, "※ 기관명은 사업자등록증 기준으로 적습니다.", cs=4, kind="note")
    out = HT.build(stage1(t), use_llm=False, ask=_no_llm)
    rl, tb = roles(out)
    subs = [(s["id"], tuple(s["rows"]), s["kind"], s["headerRows"], s["headerCols"]) for s in tb["subtables"]]
    assert subs == [("A", (0, 1), "title", 0, 0), ("B", (1, 3), "form", 0, 1), ("C", (3, 6), "matrix", 1, 0), ("D", (6, 7), "spacer", 0, 0), ("E", (7, 8), "note", 0, 0)]
    assert rl["< 요 약 문 >"] == "title" and rl["사업명"] == "rowhead" and rl["기관명"] == rl["전화"] == "colhead" and rl["※ 기관명은 사업자등록증 기준으로 적습니다."] == "note"
    assert out["counts"]["split"] == 1 and out["counts"]["roles"]["spacer"] == 1
    assert all(c["sub"] for c in tb["cells"])


def test_bands_kv_after_matrix_rule_c():
    """열헤더 띠 아래에 열 경계가 어긋난 키-값 행이 오면 새 띠(규칙 ⓒ) — 어긋나지 않은 음영 행머리 행은 그대로."""
    t = Tab("t4")
    for c, name in enumerate(["기관명", "책임자", "직위", "전화", "비고"]):
        t.cell(0, c, name, fill="#EEEEEE")
    t.cell(1, 0, "주관기관", fill="#EEEEEE")
    for c in range(1, 5):
        t.cell(1, c, "")
    t.cell(2, 0, "참여기관", fill="#EEEEEE")
    for c in range(1, 5):
        t.cell(2, c, "")
    t.cell(3, 0, "실무책임자", fill="#EEEEEE")
    t.cell(3, 1, "", cs=2)  # 열 경계가 헤더 행과 다름(1~3)
    t.cell(3, 3, "직위", fill="#EEEEEE")
    t.cell(3, 4, "")
    out = HT.build(stage1(t), use_llm=False, ask=_no_llm)
    rl, tb = roles(out)
    assert [tuple(s["rows"]) for s in tb["subtables"]] == [(0, 3), (3, 4)] and tb["subtables"][1]["kind"] == "form"
    assert rl["주관기관"] == rl["참여기관"] == rl["실무책임자"] == "rowhead" and rl["직위"] in ("colhead", "rowhead")
    assert {c["role"] for c in tb["cells"] if c["row"] == 3 and c["col"] == 3} == {"rowhead"} and {c["role"] for c in tb["cells"] if c["row"] == 0 and c["col"] == 2} == {"colhead"}


def test_no_cut_through_merged_cell():
    """헤더 행처럼 보여도 병합 칸이 경계를 걸치면 자르지 않는다."""
    t = Tab("t5")
    t.cell(0, 0, "항목", rs=3, fill="#EEEEEE")
    t.cell(0, 1, "값1")
    t.cell(0, 2, "")
    t.cell(1, 1, "소계", fill="#EEEEEE")
    t.cell(1, 2, "합계", fill="#EEEEEE")
    t.cell(2, 1, "")
    t.cell(2, 2, "")
    out = HT.build(stage1(t), use_llm=False, ask=_no_llm)
    assert len(out["tables"][0]["subtables"]) == 1


def test_one_column_table_is_list():
    t = Tab("t6")
    t.cell(0, 0, "작성 요령", fill="#EEEEEE")
    t.cell(1, 0, "◦ 개발 대상 기술의 개요를 적는다.", kind="marker")
    out = HT.build(stage1(t), use_llm=False, ask=_no_llm)
    rl, tb = roles(out)
    assert tb["subtables"][0]["kind"] == "list" and rl["작성 요령"] == "title" and list(rl.values())[1] == "note"


def test_draft_small_sample(small):
    out = HT.build(small, use_llm=False, ask=_no_llm)
    rl, t8 = roles(out, "t8")
    get = lambda prefix: next(v for k, v in rl.items() if k.startswith(prefix))  # noqa: E731
    assert get("제안기술 분류") == "rowhead" and get("[1] 전력변환") == "rowhead" and get("(") == "field"
    assert get("현재") == "colhead" and get("사업 종료 후") == "colhead" and get("제안하는 기술의 수") == "corner" and get("[작성가이드라인]") == "note"
    assert get("연구개발 기간") == "rowhead" and get("소요예산") == "rowhead"
    kinds = [s["kind"] for s in t8["subtables"]]
    assert kinds == ["form", "matrix", "form"] and t8["subtables"][1]["headerRows"] == 1
    trl = next(c for c in t8["cells"] if c["text"].startswith("TRL") and c["col"] == 1)
    assert [c["text"][:2] for c in t8["cells"] if c["id"] in trl["colPath"]] == ["현재"] and [c["text"][:4] for c in t8["cells"] if c["id"] in trl["rowPath"]] == ["제안하는"]


def test_draft_rnd_cover_and_gantt(rnd):
    out = HT.build(rnd, use_llm=False, ask=_no_llm)
    assert out["counts"]["tables"] == 135 and out["llm"]["seconds"] < 5
    rl, t1 = roles(out, "t1")
    get = lambda prefix: next(v for k, v in rl.items() if k.startswith(prefix))  # noqa: E731
    kinds = [s["kind"] for s in t1["subtables"]]
    assert kinds[:4] == ["form", "matrix", "matrix", "form"]  # 표지 키-값 → 연구개발비 → 공동연구개발기관 → 실무책임자
    assert get("중앙행정기관명") == "rowhead" and get("산업통상부") == "field" and get("국문") == "rowhead"
    assert get("1단계") == "rowhead" and get("1년차") == "rowhead" and get("단계14-2") == "rowhead"  # 겹친 행헤더(단계 › 1단계 › 1년차)
    year1 = next(c for c in t1["cells"] if c["text"] == "1년차")
    chain = [next(x["text"] for x in t1["cells"] if x["id"] == i) for i in [year1["parent"]]]
    assert chain == ["1단계"]
    money = next(c for c in t1["cells"] if c["text"] == "0,000,000" and c["role"] == "field")
    names = lambda ids: [next(x["text"] for x in t1["cells"] if x["id"] == i) for i in ids]  # noqa: E731
    assert "현금" in names(money["colPath"]) and "1차년도" in names(money["rowPath"])
    gantt = next(t for t in out["tables"] if t["before"].startswith("2-3. 연구개발과제 수행일정"))
    s = gantt["subtables"][0]
    assert len(gantt["subtables"]) == 1 and s["headerRows"] == 3 and s["headerCols"] == 2
    grl = {c["text"]: c["role"] for c in gantt["cells"]}
    assert grl["일련 번호"] == grl["개발 내용"] == "corner" and grl["추진 일정"] == grl["1단계"] == "colhead" and grl["계획수립 및 자료조사"] == "rowhead"
    blank_stub = [c for c in gantt["cells"] if c["col"] == 1 and c["row"] > 2 and not c["text"]]
    assert blank_stub and all(c["role"] == "rowhead" for c in blank_stub)  # 열헤더 「개발 내용」 아래 빈 양식 줄도 행헤더
    assert out["counts"]["repeats"] >= 1 and all(r["count"] >= 2 for r in out["repeats"])


# ---- 3. T 호출 — 묶음 · 적용 · 검증 ----------------------------------------------------------------------------------

def _data(job):
    return json.loads(job["content"].rsplit("## 자료(JSON)\n", 1)[1])


def _res(data=None, error=None, cost=0.0):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": cost, "error": error}


def test_t_jobs_batches_and_skips_small():
    tabs = []
    for i in range(12):
        t = Tab(f"t{i}")
        for r in range(5):
            for c in range(10):
                t.cell(r, c, "h" if r == 0 else "", fill="#EEEEEE" if r == 0 else None)
        tabs.append(t)
    tiny = Tab("tiny")
    tiny.cell(0, 0, "별첨", fill="#EEEEEE")
    tiny.cell(0, 1, "")
    tiny.cell(0, 2, "제목")
    one_row = Tab("row1")
    for c in range(6):
        one_row.cell(0, c, "x")
    s1 = stage1(*tabs, tiny, one_row)
    tables = HT.collect(s1)
    drafts = {tb["id"]: HT.draft(tb) for tb in tables}
    jobs, used = HT.t_jobs(tables, drafts, s1)
    assert set(used) == {"tables", "tolerance"}
    assert [len(j["_tables"]) for j in jobs] == [10, 2] and all(j["what"].startswith("heading_tables#") for j in jobs)  # 표 10개 상한 → 50칸 × 10 = 500
    assert not any("tiny" in j["_tables"] or "row1" in j["_tables"] for j in jobs)
    d = _data(jobs[0])
    assert d["tables"][0]["table"] == "t0" and len(d["tables"][0]["grid"]) == 5 and d["tables"][0]["grid"][0][0].endswith("|colhead")
    assert d["tables"][0]["grid"][1][0] == "t0c11"  # 빈 1×1 필드는 칸 id 만
    assert jobs[0]["content"].startswith(HL.TABLES_CONTRACT[:30]) and "## 지침 — 표 구조" in jobs[0]["content"]


def test_payload_tokens_cover_spans():
    tb = HT.collect(stage1(matrix_tab()))[0]
    bs, occ = HT.draft(tb)
    p = HT.table_payload(tb, occ, bs, "앞 글")
    assert p["grid"][0][3] == "<" and p["grid"][1][0] == "^" and p["grid"][0][0].startswith("t1c1|3x1|FT|구분|corner") and p["before"] == "앞 글"
    assert p["draft"] == [{"id": "A", "rows": [0, 5], "cols": [0, 6], "kind": "matrix", "headerRows": 3, "headerCols": 2}]


def test_apply_answer_regions_and_overrides():
    """제목 행 + 매트릭스를 하나의 띠로 본 초안을 LLM 이 둘로 나누고 헤더 수를 고치고 칸 하나를 note 로."""
    t = Tab("t7")
    t.cell(0, 0, "평가 항목", cs=3, bold=True)
    for c, name in enumerate(["항목", "단위", "목표"]):
        t.cell(1, c, name)  # 음영 없는 헤더 — 스크립트는 못 알아본다
    t.cell(2, 0, "회수율")
    t.cell(2, 1, "%")
    t.cell(2, 2, "")
    t.cell(3, 0, "※ 단위는 SI 단위로")
    t.cell(3, 1, "")
    t.cell(3, 2, "")
    s1 = stage1(t)
    tb = HT.collect(s1)[0]
    bs, occ = HT.draft(tb)
    assert [b["kind"] for b in bs] == ["title", "plain"] or [b["kind"] for b in bs] == ["title", "form"]
    ans = {"table": "t7", "subtables": [{"sub": "A", "rows": [0, 1], "cols": [0, 3], "kind": "title", "headerRows": 0, "headerCols": 0, "note": ""},
                                        {"sub": "B", "rows": [1, 4], "cols": [0, 3], "kind": "matrix", "headerRows": 1, "headerCols": 1, "note": "음영 없는 헤더"}],
           "cells": [{"cell": "t7c8", "role": "note", "reason": "안내"}, {"cell": "없음", "role": "field", "reason": ""}, {"cell": "t7c2", "role": "boss", "reason": ""}],
           "summary": "평가 항목 표"}
    regs, changed, rejected = HT.apply_answer(tb, occ, bs, ans)
    rl = {c["text"] or c["id"]: c["role"] for c in tb["cells"]}
    assert [r["id"] for r in regs] == ["A", "B"] and regs[1]["headerRows"] == 1 and regs[1]["headerCols"] == 1 and regs[1]["source"] == "llm"
    assert rl["평가 항목"] == "title" and rl["항목"] == "corner" and rl["단위"] == rl["목표"] == "colhead" and rl["회수율"] == "rowhead" and rl["※ 단위는 SI 단위로"] == "note"
    assert [r["why"] for r in rejected] == ["없는 칸 id", "모르는 역할 'boss'"]
    assert changed >= 4 and all(c["changed"] == (c["role"] != c["draft"]) for c in tb["cells"])
    fin = HT.finish_band(tb, occ, regs[1])
    pct = next(c for c in tb["cells"] if c["text"] == "%")
    assert pct["colPath"] == ["t7c3"] and pct["rowPath"] == ["t7c5"] and fin["counts"]["colhead"] == 2


def test_apply_answer_rejects_bad_regions_keeps_draft():
    tb = HT.collect(stage1(matrix_tab()))[0]
    bs, occ = HT.draft(tb)
    before = {c["id"]: c["role"] for c in tb["cells"]}
    for bad, why in (([{"sub": "A", "rows": [0, 2], "cols": [0, 6]}, {"sub": "B", "rows": [2, 5], "cols": [0, 6]}], "가름"),  # 구분(3x1)을 가름
                     ([{"sub": "A", "rows": [0, 5], "cols": [0, 3]}, {"sub": "B", "rows": [0, 5], "cols": [2, 6]}], "겹침"),
                     ([{"sub": "A", "rows": [0, 3], "cols": [0, 6]}], "품은 영역이 0개"),
                     ([{"sub": "A", "rows": [0, 9], "cols": [0, 6]}], "표 밖"),
                     ([{"sub": "A", "rows": "0-5", "cols": [0, 6]}], "정수 쌍"),
                     ([], "영역 없음")):
        regs, changed, rejected = HT.apply_answer(tb, occ, bs, {"subtables": bad, "cells": []})
        assert regs is bs and changed == 0 and rejected and why in rejected[0]["why"], (bad, rejected)
        assert {c["id"]: c["role"] for c in tb["cells"]} == before
    # 헤더 수 -1 = 스크립트 값 그대로
    regs, changed, rejected = HT.apply_answer(tb, occ, bs, {"subtables": [{"sub": "", "rows": [0, 5], "cols": [0, 6], "kind": "matrix", "headerRows": -1, "headerCols": -1}], "cells": []})
    assert not rejected and regs[0]["headerRows"] == 3 and regs[0]["headerCols"] == 2 and regs[0]["id"] == "A" and changed == 0


def test_build_llm_fake_applies_and_marks_failures(small):
    """표 2개 중 t8 만 보냄(t1 은 3칸) — 답에 t8 의 칸 하나 바꿈 · 다른 묶음은 실패 → 미판정."""
    calls = []

    def ask(jobs):
        out = []
        for job in jobs:
            calls.append(job)
            assert job["what"].startswith("heading_tables#") and job["schema"] is HL.TABLES_SCHEMA
            d = _data(job)
            tabs = []
            for tp in d["tables"]:
                tabs.append({"table": tp["table"], "subtables": [{"sub": b["id"], "rows": b["rows"], "cols": b["cols"], "kind": b["kind"], "headerRows": -1, "headerCols": -1, "note": ""}
                                                              for b in tp["draft"]],
                             "cells": [{"cell": tp["grid"][0][1].split("|")[0], "role": "colhead", "reason": "분류 이름"}], "summary": f"{tp['table']} 요약"})
            out.append(_res({"tables": tabs, "summary": "전체 요약"}, cost=0.02))
        return out
    out = HT.build(small, use_llm=True, ask=ask, doc_name="시험")
    lm = out["llm"]
    assert lm["requested"] and lm["calls"] == 1 and lm["failed"] == 0 and lm["sent"] == 1 and lm["skipped"] == 1 and lm["applied"] == 1 and lm["rejected"] == 0
    assert lm["costUsd"] == 0.02 and lm["summary"] == "전체 요약" and set(out["guides"]) == {"tables", "tolerance"}
    t8 = next(t for t in out["tables"] if t["id"] == "t8")
    ch = [c for c in t8["cells"] if c["changed"]]
    assert len(ch) == 1 and ch[0]["role"] == "colhead" and ch[0]["draft"] == "rowhead" and ch[0]["reason"] == "분류 이름" and t8["llm"]["summary"] == "t8 요약"
    assert out["counts"]["changed"] == 1 and len(out["_calls"]) == 1 and out["_calls"][0]["response"]["summary"] == "전체 요약"
    t1 = next(t for t in out["tables"] if t["id"] == "t1")
    assert t1["llm"] == {"sent": False, "changed": 0, "rejected": [], "error": None, "undecided": False, "state": "unsent"}   # 보낼 수 없는 표(3칸) — 보완 대상이 아니다
    assert t8["llm"]["state"] == "answered" and (lm["asked"], lm["carried"], lm["pending"], lm["pendingTables"]) == (1, 0, 0, [])
    # 실패
    out2 = HT.build(small, use_llm=True, ask=lambda jobs: [_res(None, "가짜 실패") for _ in jobs])
    t8 = next(t for t in out2["tables"] if t["id"] == "t8")
    assert out2["llm"]["fallback"] and out2["llm"]["error"] == "가짜 실패" and out2["llm"]["undecided"] == 1 and t8["llm"]["undecided"]
    assert all(c["role"] == c["draft"] for c in t8["cells"])
    assert t8["llm"]["state"] == "failed" and (out2["llm"]["pending"], out2["llm"]["pendingTables"]) == (1, ["t8"])   # 이을 판정이 없으면 초안 그대로 — 보완 대상
    # 답에 그 표가 빠짐 → 초안 그대로(미판정 아님), 모르는 표 id 는 버림
    out3 = HT.build(small, use_llm=True, ask=lambda jobs: [_res({"tables": [{"table": "t999", "subtables": [], "cells": [], "summary": ""}], "summary": ""}) for _ in jobs])
    t8 = next(t for t in out3["tables"] if t["id"] == "t8")
    assert t8["llm"]["sent"] and t8["llm"]["undecided"] and out3["llm"]["undecided"] == 1


def test_build_uses_pinned_guides():
    pinned = G.snapshot()
    pinned["tables"] = {**pinned["tables"], "text": "# 고정 지침\n표 지침 고정본", "sha1": "deadbeef"}
    seen = []

    def ask(jobs):
        seen.extend(j["content"] for j in jobs)
        return [_res({"tables": [], "summary": ""}) for _ in jobs]
    out = HT.build(stage1(matrix_tab()), use_llm=True, ask=ask, pinned=pinned)
    assert seen and "표 지침 고정본" in seen[0] and out["guides"]["tables"] == "deadbeef"


# ---- 4. 지침 · 계약 ---------------------------------------------------------------------------------------------

def test_tables_guide_registered():
    assert "tables" in G.NAMES and G.default_text("tables").startswith("# 표 구조")
    assert G.get("tables")["title"].startswith("표 구조") and set(G.snapshot()) == set(G.NAMES) and any(x["name"] == "tables" for x in G.listing())
    text, used = HL.prompt(HL.TABLES_CONTRACT, ["tables", "tolerance"], {"tables": []})
    assert set(used) == {"tables", "tolerance"} and "## 지침 — 표 구조" in text
    assert HL.TABLES_SCHEMA["properties"]["tables"]["items"]["properties"]["cells"]["items"]["properties"]["role"]["enum"] == list(HT.ROLES)


# ---- 5. 실행 · API --------------------------------------------------------------------------------------------------

@pytest.fixture
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait(c, d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("헤딩 추출이 끝나지 않음")


def test_api_stage3(client):
    d = _upload(client, SMALL)
    v = client.get(f"/api/docs/{d}/headings").json()
    assert v["stage3"] is None and client.get(f"/api/docs/{d}/headings/tables").status_code == 404
    assert client.post(f"/api/docs/{d}/headings", json={"stage": 3, "llm": "false"}).status_code == 400
    r = client.post(f"/api/docs/{d}/headings", json={"stage": 3, "llm": False})  # 1단계 없이 바로 — 1단계를 먼저 뽑는다
    assert r.status_code == 202 and r.json()["stage"] == 3
    v = _wait(client, d)
    assert v["job"]["status"] == "done", v["job"]
    assert [s["name"] for s in v["job"]["steps"]][:2] == ["1단계(스크립트) 다시", "추출"] and v["job"]["steps"][-1]["name"] == "표 구조 — 스크립트"
    s3 = v["stage3"]
    assert s3["counts"]["tables"] == 2 and not s3["stale"] and s3["meta"]["run"] == 2 and s3["meta"]["stage1Run"] == 1 and set(s3["meta"]["guides"]) == set(G.NAMES)
    assert [t["id"] for t in s3["tables"]] == ["t1", "t8"] and s3["tables"][1]["cells"] == 40 and s3["tables"][1]["subtables"][1]["kind"] == "matrix"
    assert s3["llm"]["requested"] is False and v["stage1"]["meta"]["run"] == 1
    full = client.get(f"/api/docs/{d}/headings/tables")
    assert full.status_code == 200
    full = full.json()
    assert "_calls" not in full and full["meta"]["run"] == 2 and len(full["tables"][1]["cells"]) == 40 and full["tables"][1]["cells"][0]["role"]
    hd = works.folder(d) / "headings"
    assert json.loads((hd / "current.json").read_text("utf-8")) == {"stage1": 1, "stage3": 2} and (hd / "2" / "tables.json.gz").is_file()
    assert json.loads((hd / "2" / "run.json").read_text("utf-8"))["stage"] == 3
    # 다시 연 세션이 current.json 에서 3단계 결과를 되읽는다
    sess = server.DOCS[d]
    sess.heads = None
    st = heading_runs.state(sess)
    assert st["stage3"]["counts"]["tables"] == 2 and st["stage3"]["meta"]["run"] == 2
    end = time.time() + 10
    while not [e for e in works.events(d) if e["kind"] == "headings" and e.get("stage") == 3] and time.time() < end:
        time.sleep(0.05)
    ev = [e for e in works.events(d) if e["kind"] == "headings"]
    assert [(e["stage"], e["status"]) for e in ev] == [(3, "done")] and ev[0]["n"] == 2


def test_run_sync_stage3_reuses_fresh_stage1():
    from app.hwpx_doc import HwpxDoc as _D  # noqa: F401
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _upload(c, SMALL)
    sess = server.DOCS[d]
    heading_runs.run_sync(sess, 1, False)
    j = heading_runs.run_sync(sess, 3, False)
    assert j.status == "done" and [s["name"] for s in j.steps] == ["TEMP 라벨 — 표 구조에서 뺌", "표 구조 — 스크립트"] and j.run == 2  # 표 검토 전에 TEMP 라벨(§15)
    st = heading_runs.state(sess)
    assert st["stage3"]["meta"]["stage1Run"] == 1 and heading_runs.summary(sess)["stage3"]["counts"]["cells"] == 43
    server.DOCS.clear()


def test_shaded_value_row_and_column_are_fields():
    """음영 값 칸(2026-11-10 연구개발기관별 사용계획 총괄표) — 「합계」 열·「총액」 행의 글 없는 음영 칸은 헤더가 아니라 필드, 헤더 열을 꼭 채운 이름 + 음영 빈 칸 행은
    새 띠로 자르지 않는다. 이름 칸이 헤더 열보다 넓으면(「합 계」 가 표 폭을 거의 다 차지) 예전대로 제 띠 — 그래도 음영 빈 칸은 필드."""
    g = "#D9D9D9"
    t = Tab("t7")
    for c, name in enumerate(["비목", "항목", "1차년도", "2차년도", "합계"]):
        t.cell(0, c, name, fill=g)
    t.cell(1, 0, "직접비", rs=2, fill=g)
    t.cell(1, 1, "인건비(A)", fill=g)
    t.cell(2, 1, "재료비(B)", fill=g)
    for r in (1, 2, 3):
        t.cell(r, 2, "")
        t.cell(r, 3, "")
        t.cell(r, 4, "", fill=g)
    t.cell(3, 0, "간접비(L)", cs=2, fill=g)
    t.cell(4, 0, "총액(M=A+B+L)", cs=2, fill=g)
    for c in (2, 3, 4):
        t.cell(4, c, "", fill=g)
    tb = HT.build(stage1(t), use_llm=False, ask=_no_llm)["tables"][0]
    assert [(tuple(s["rows"]), s["kind"], s["headerRows"], s["headerCols"]) for s in tb["subtables"]] == [((0, 5), "matrix", 1, 2)]
    assert {c["role"] for c in tb["cells"] if c["row"] >= 1 and c["col"] >= 2} == {"field"}
    assert by_text(tb, "총액(M=A+B+L)")["role"] == "rowhead" and by_text(tb, "합계")["role"] == "colhead"
    last = next(c for c in tb["cells"] if c["row"] == 4 and c["col"] == 2)
    assert last["nature"] == "header" and last["shaded"] and len(last["rowPath"]) == 1 and len(last["colPath"]) == 1
    # 음영 빈 칸만 있는 열은 헤더 열의 근거가 아니다 — 「차년도」 열(헤더 낱말)에 합계 줄의 음영 빈 칸이 섞여도 값 열
    w = Tab("t8")
    for c, name in enumerate(["소속기관", "과정명", "월 급여", "합계"]):
        w.cell(0, c, name, fill=g)
    for r in (1, 2):
        for c in range(4):
            w.cell(r, c, "")
    w.cell(3, 0, "합 계", cs=3, fill=g)
    w.cell(3, 3, "", fill=g)
    tb2 = HT.build(stage1(w), use_llm=False, ask=_no_llm)["tables"][0]
    assert [(tuple(s["rows"]), s["headerCols"]) for s in tb2["subtables"]] == [((0, 3), 0), ((3, 4), 1)]
    assert by_text(tb2, "합 계")["role"] == "rowhead" and next(c for c in tb2["cells"] if c["row"] == 3 and c["col"] == 3)["role"] == "field"
    y = Tab("t9")
    for c, name in enumerate(["항목", "1차년도", "2차년도"]):
        y.cell(0, c, name, fill=g)
    y.cell(1, 0, "인건비", fill=g)
    y.cell(2, 0, "소계", fill=g)
    for c in (1, 2):
        y.cell(1, c, "")
        y.cell(2, c, "", fill=g)
    tb3 = HT.build(stage1(y), use_llm=False, ask=_no_llm)["tables"][0]
    assert tb3["subtables"][0]["headerCols"] == 1 and {c["role"] for c in tb3["cells"] if c["row"] >= 1 and c["col"] >= 1} == {"field"}


def _budget_tab(tid="t10", filled=True):
    """연차 총괄표(2026-11-23 사용자 화면 — 「공동연구개발기관3」 연구개발비 표의 꼴): 비목 | 항목 | 1단계(1x3: 1차·2차·3차년도) | 합계 ; 직접비(인건비 · 소계 · 총 인건비) · 간접비 · 비율 · 총액.
    음영 = 헤더(회색) + 「합계」 열 · 「총 인건비」 · 「총액」 줄(회색) + 3차년도 값 열(하늘색 — 당해 연도를 칠해 둔 값 칸). filled = 값이 채워진 것(False = 빈 양식)."""
    g, b = "#D6D6D6", "#DFEAF5"
    t = Tab(tid)
    t.cell(0, 0, "비목", rs=2, fill=g)
    t.cell(0, 1, "항목", rs=2, fill=g)
    t.cell(0, 2, "1단계", cs=3, fill=g)
    t.cell(0, 5, "합계", rs=2, fill=g)
    for i, name in enumerate(["1차년도", "2차년도", "3차년도"]):
        t.cell(1, 2 + i, name, fill=g)
    t.cell(2, 0, "직접비", rs=3, fill=g)
    names = ["인건비(A)", "소계(A+B)", "총 인건비(E=A+B)"]
    vals = [["245,600", "220,000", "142,000", "607,600"], ["365,600", "325,000", "247,000", "937,600"], ["365,600", "325,000", "247,000", "937,600"],
            ["", "", "24,000", "24,000"], ["0.0%", "0.0%", "7.1%", "3.7%"], ["533,334", "466,667", "466,667", "1,466,668"]]
    fills = [[None, None, b, g], [None, None, b, g], [g, g, b, g], [None, None, b, g], [None, None, b, g], [g, g, b, g]]
    for r, name in enumerate(names):
        t.cell(2 + r, 1, name, fill=g)
    t.cell(5, 0, "간접비(L)", cs=2, fill=g)
    t.cell(6, 0, "간접비 비율(L/E)", cs=2, fill=g)
    t.cell(7, 0, "연구개발비 총액(M=E+L)", cs=2, fill=g)
    for r in range(6):
        for c in range(4):
            v = vals[r][c] if filled else ""
            t.cell(2 + r, 2 + c, v, kind="data" if v else None, fill=fills[r][c])
    return t


def test_shaded_number_cells_are_fields():
    """숫자 값만 든 음영 칸(2026-11-23 사용자 「색상이 있다 할지라도 이건 내부는 필드」) — 금액 · 비율이 든 음영 칸은 헤더 행·열 밖에서 필드이고(합계 열 · 소계 · 총액 줄 · 당해 연도를
    칠한 값 열), 그 줄 때문에 띠가 잘리지 않는다. 같은 표의 빈 양식과 판정이 같다. 이름일 수 있는 숫자(연도 · 순번 꼴)는 전처럼 이웃 규칙."""
    filled = HT.build(stage1(_budget_tab()), use_llm=False, ask=_no_llm)["tables"][0]
    blank = HT.build(stage1(_budget_tab("t11", filled=False)), use_llm=False, ask=_no_llm)["tables"][0]
    for tb in (filled, blank):
        assert [(tuple(s["rows"]), s["kind"], s["headerRows"], s["headerCols"]) for s in tb["subtables"]] == [((0, 8), "matrix", 2, 2)]
        assert {c["role"] for c in tb["cells"] if c["row"] >= 2 and c["col"] >= 2} == {"field"}
    assert [c["role"] for c in filled["cells"]] == [c["role"] for c in blank["cells"]]
    total = by_text(filled, "1,466,668")
    assert total["nature"] == "header" and total["shaded"] and total["role"] == "field" and len(total["rowPath"]) == 1 and len(total["colPath"]) == 1
    assert by_text(filled, "연구개발비 총액(M=E+L)")["role"] == "rowhead" and by_text(filled, "합계")["role"] == "colhead"
    # 헤더 바로 아래의 음영 합계 줄(「합계 | 1,000 | 2,000」)은 헤더 행이 아니다 — 금액 칸이 열헤더가 되지 않는다
    g = "#D9D9D9"
    t = Tab("t12")
    for c, name in enumerate(["항목", "1차년도", "2차년도"]):
        t.cell(0, c, name, fill=g)
    t.cell(1, 0, "합계", fill=g)
    t.cell(1, 1, "1,000", kind="data", fill=g)
    t.cell(1, 2, "2,000", kind="data", fill=g)
    t.cell(2, 0, "인건비", fill=g)
    t.cell(2, 1, "1,000", kind="data")
    t.cell(2, 2, "2,000", kind="data")
    tb = HT.build(stage1(t), use_llm=False, ask=_no_llm)["tables"][0]
    assert [(s["headerRows"], s["headerCols"]) for s in tb["subtables"]] == [(1, 1)]
    assert {c["role"] for c in tb["cells"] if c["row"] >= 1 and c["col"] >= 1} == {"field"} and by_text(tb, "합계")["role"] == "rowhead"
    # 「차년도」 열(헤더 낱말) 아래 값 + 합계 줄의 음영 금액 칸 — 음영 금액 칸은 헤더 열의 근거가 아니다(값 열)
    v = Tab("t13")
    for c, name in enumerate(["항목", "1차년도", "2차년도", "합계"]):
        v.cell(0, c, name, fill=g)
    for r, (name, a, b2) in enumerate([("인건비", "100,000", "200,000"), ("재료비", "50,000", "60,000")]):
        v.cell(1 + r, 0, name, fill=g)
        v.cell(1 + r, 1, a, kind="data")
        v.cell(1 + r, 2, b2, kind="data")
        v.cell(1 + r, 3, "300,000", kind="data", fill=g)
    v.cell(3, 0, "소계", fill=g)
    for c, x in enumerate(["150,000", "260,000", "410,000"]):
        v.cell(3, 1 + c, x, kind="data", fill=g)
    tb = HT.build(stage1(v), use_llm=False, ask=_no_llm)["tables"][0]
    assert [(tuple(s["rows"]), s["headerRows"], s["headerCols"]) for s in tb["subtables"]] == [((0, 4), 1, 1)]
    assert {c["role"] for c in tb["cells"] if c["row"] >= 1 and c["col"] >= 1} == {"field"}
    # 이름일 수 있는 숫자는 스크립트가 값으로 단정하지 않는다 — 「단계 | 1 | 1차년도 …」 의 단계 값 머리(순번 꼴) · 연도 꼴
    s = Tab("t14")
    for c, name in enumerate(["단계", "연차", "정부지원", "합계"]):
        s.cell(0, c, name, fill=g)
    s.cell(1, 0, "1", rs=2, kind="data", fill=g)
    s.cell(1, 1, "2025", kind="data", fill=g)
    s.cell(2, 1, "2026", kind="data", fill=g)
    for r in (1, 2):
        s.cell(r, 2, "")
        s.cell(r, 3, "", fill=g)
    tb = HT.build(stage1(s), use_llm=False, ask=_no_llm)["tables"][0]
    assert by_text(tb, "1")["role"] == "rowhead" and by_text(tb, "2025")["role"] == "rowhead" and by_text(tb, "2026")["role"] == "rowhead"


# ---- 6. 판정을 이어 쓰는 실행 · 보완 대상만 묻기(spec_작업 ② §22 「구현 계약」 22-4) ---------------------------------------------------------

def _plan_tab(tid="t20", rows=("인건비", "합계"), vals=None):
    """항목 | 1차년도 | 2차년도 ; 인건비 | . | . ; 합계 | . | . — 칸 id 는 넣은 차례라 줄을 끝에 늘려도 앞 칸의 id 가 그대로다(c7 = 「합계」). vals = {(줄, 열): 값}."""
    g = "#D9D9D9"
    t = Tab(tid)
    for c, name in enumerate(["항목", "1차년도", "2차년도"]):
        t.cell(0, c, name, fill=g)
    for r, name in enumerate(rows):
        t.cell(1 + r, 0, name, fill=g)
        for c in (1, 2):
            v = (vals or {}).get((r, c), "")
            t.cell(1 + r, c, v, kind="data" if v else None)
    return t


def _ask_roles(changes, seen=None, drop=()):
    """가짜 T 호출(`ask(jobs)` · `llm.ask_all(jobs, **kw)` 둘 다로 쓴다) — 띠는 초안 그대로, changes = {칸 id: 역할} 만 바꾼다. seen 에 물은 표 id · drop 에 든 표는 답에서 뺀다."""
    def ask(jobs, **kw):
        out = []
        for job in jobs:
            tabs = []
            for tp in _data(job)["tables"]:
                if seen is not None:
                    seen.append(tp["table"])
                if tp["table"] in drop:
                    continue
                ids = {tok.split("|")[0] for row in tp["grid"] for tok in row if tok not in ("", "^", "<")}
                tabs.append({"table": tp["table"], "subtables": [{"sub": b["id"], "rows": b["rows"], "cols": b["cols"], "kind": b["kind"], "headerRows": -1, "headerCols": -1, "note": ""}
                                                                  for b in tp["draft"]],
                             "cells": [{"cell": c, "role": r, "reason": "가짜 판정"} for c, r in changes.items() if c in ids], "summary": f"{tp['table']} 요약"})
            out.append(_res({"tables": tabs, "summary": ""}))
        return out
    return ask


def _dead(jobs, **kw):
    return [_res(None, "가짜 실패") for _ in jobs]


def by_id(t, cid):
    return next(c for c in t["cells"] if c["id"] == cid)


def _changed(t):
    return [c["id"] for c in t["cells"] if c["changed"]]


def test_script_rerun_carries_the_llm_judgment():
    """스크립트로 3단계를 다시 돌려도 LLM 이 고친 칸 역할이 남는다 — 표가 그대로일 때 · 값이 채워졌을 때 · 줄이 늘었을 때(늘어난 표는 보완 대상).
    이어 쓴 결과를 또 이어 써도(스크립트로 거듭) 판정 뒤 생긴 칸은 보완 대상으로 남는다. 앞 판정을 안 주면 초안이다(틀린 쪽)."""
    from app import table_manager as TM
    s1 = stage1(_plan_tab())
    first = HT.build(s1, use_llm=True, ask=_ask_roles({"t20c7": "note"}))
    tb = first["tables"][0]
    assert (by_id(tb, "t20c7")["role"], by_id(tb, "t20c7")["draft"]) == ("note", "rowhead") and tb["llm"]["state"] == "answered" and tb["judged"] is None
    assert (first["llm"]["asked"], first["llm"]["carried"], first["llm"]["pending"]) == (1, 0, 0)
    prior = {"t20": {**tb, "judged": {"run": 5, "rev": 2}}}   # 저장할 때 heading_runs 가 채우는 출처
    keep = copy.deepcopy(prior)
    plain = HT.build(s1, use_llm=False, ask=_no_llm)["tables"][0]   # 앞 판정 없이 — 초안으로
    assert by_id(plain, "t20c7")["role"] == "rowhead" and plain["llm"]["state"] == "pending" and plain["judged"] is None
    again = HT.build(s1, use_llm=False, ask=_no_llm, prior=prior, carry=TM.carry_over)   # 표가 그대로
    t = again["tables"][0]
    c = by_id(t, "t20c7")
    assert (c["role"], c["draft"], c["changed"], c["reason"]) == ("note", "rowhead", True, "가짜 판정")
    assert t["llm"]["state"] == "carried" and t["llm"]["carried"] == {"run": 5, "mode": "same", "kept": 9, "new": 0, "gone": 0, "bands": "stored"}
    assert t["judged"] == {"run": 5, "rev": 2} and t["llm"]["sent"] is False and t["llm"]["summary"] == "t20 요약" and not t["llm"]["undecided"]
    lm = again["llm"]
    assert (lm["requested"], lm["fallback"], lm["asked"], lm["carried"], lm["pending"], lm["pendingTables"]) == (False, False, 0, 1, 0, []) and again["counts"]["changed"] == 1
    assert prior == keep   # 저장된 결과는 안 고친다
    filled = HT.build(stage1(_plan_tab(vals={(0, 1): "1,000", (1, 2): "2,000"})), use_llm=False, ask=_no_llm, prior=prior, carry=TM.carry_over)   # 값이 채워짐
    t = filled["tables"][0]
    assert by_id(t, "t20c7")["role"] == "note" and by_id(t, "t20c5")["text"] == "1,000" and t["llm"]["state"] == "carried"
    assert (t["llm"]["carried"]["mode"], t["llm"]["carried"]["kept"], t["llm"]["carried"]["new"], filled["llm"]["pending"]) == ("carried", 9, 0, 0)
    grown_s1 = stage1(_plan_tab(rows=("인건비", "합계", "재료비")))   # 줄이 늘어남 — 있던 칸은 그 역할 · 새 줄은 보완 대상
    grown = HT.build(grown_s1, use_llm=False, ask=_no_llm, prior=prior, carry=TM.carry_over)
    t = grown["tables"][0]
    assert by_id(t, "t20c7")["role"] == "note" and t["llm"]["state"] == "carried" and {by_id(t, i)["role"] for i in ("t20c11", "t20c12")} == {"field"}
    assert (t["llm"]["carried"]["kept"], t["llm"]["carried"]["new"], t["llm"]["carried"]["fresh"]) == (9, 3, ["t20c10", "t20c11", "t20c12"])
    assert (grown["llm"]["carried"], grown["llm"]["pending"], grown["llm"]["pendingTables"]) == (1, 1, ["t20"])
    twice = HT.build(grown_s1, use_llm=False, ask=_no_llm, prior={"t20": t}, carry=TM.carry_over)   # 이어 쓴 결과를 다시 이어 씀 — 새 칸이 「판정 때 있던 칸」 으로 바뀌지 않는다
    t2 = twice["tables"][0]
    assert (t2["llm"]["carried"]["mode"], t2["llm"]["carried"]["new"], twice["llm"]["pending"]) == ("same", 3, 1) and t2["judged"] == {"run": 5, "rev": 2}
    assert by_id(t2, "t20c7")["role"] == "note" and prior == keep
    assert HT.pending(grown_s1, {"t20": t}, TM.carry_over) == {"t20"} and HT.pending(s1, prior, TM.carry_over) == set() and HT.pending(s1, {}, TM.carry_over) == {"t20"}


def test_complement_run_asks_only_pending_tables():
    """보완 실행(only = 보완 대상) — 판정이 없는 표만 묻고 나머지는 이어 쓴다 · 보완 대상이 없으면 호출이 없다 · only 없이(전부 다시)는 판정이 있어도 다 묻는다."""
    from app import table_manager as TM
    s1 = stage1(_plan_tab("t20"), _plan_tab("t21"))
    seen = []
    first = HT.build(s1, use_llm=True, ask=_ask_roles({"t20c7": "note", "t21c7": "note"}, seen))
    assert seen == ["t20", "t21"]
    prior = {"t20": {**first["tables"][0], "judged": {"run": 3, "rev": 1}}}   # t21 의 판정은 없다(그 표만 답을 못 받았던 꼴)
    only = HT.pending(s1, prior, TM.carry_over)
    assert only == {"t21"}
    seen.clear()
    out = HT.build(s1, use_llm=True, ask=_ask_roles({"t21c7": "title"}, seen), prior=prior, carry=TM.carry_over, only=only)
    ta, tb = out["tables"]
    assert seen == ["t21"]   # 물은 표
    assert (ta["llm"]["state"], ta["llm"]["sent"], by_id(ta, "t20c7")["role"], ta["judged"]) == ("carried", False, "note", {"run": 3, "rev": 1})
    assert (tb["llm"]["state"], tb["llm"]["sent"], by_id(tb, "t21c7")["role"], tb["judged"]) == ("answered", True, "title", None)
    lm = out["llm"]
    assert (lm["requested"], lm["fallback"], lm["asked"], lm["sent"], lm["carried"], lm["pending"]) == (True, False, 1, 1, 1, 0)
    both = {**prior, "t21": {**tb, "judged": {"run": 4, "rev": 1}}}
    assert HT.pending(s1, both, TM.carry_over) == set()
    none = HT.build(s1, use_llm=True, ask=_no_llm, prior=both, carry=TM.carry_over, only=set())   # 보완 대상 없음 — 호출 없이 끝난 것으로
    assert (none["llm"]["requested"], none["llm"]["fallback"], none["llm"]["calls"], none["llm"]["asked"], none["llm"]["carried"], none["llm"]["pending"]) == (True, False, 0, 0, 2, 0)
    assert [by_id(t, f"{t['id']}c7")["role"] for t in none["tables"]] == ["note", "title"]
    seen.clear()
    full = HT.build(s1, use_llm=True, ask=_ask_roles({}, seen), prior=both, carry=TM.carry_over)   # 전부 다시
    assert seen == ["t20", "t21"] and [t["llm"]["state"] for t in full["tables"]] == ["answered", "answered"] and full["llm"]["carried"] == 0


def test_failed_llm_run_keeps_the_prior_judgment():
    """호출이 모두 실패한 LLM 실행 · 답에 그 표가 빠진 호출 뒤에도 앞 판정이 남는다(초안으로 안 돌아감) — 그 표는 보완 대상으로 센다. 이을 판정이 없을 때만 전처럼 초안 · 미판정."""
    from app import table_manager as TM
    s1 = stage1(_plan_tab())
    first = HT.build(s1, use_llm=True, ask=_ask_roles({"t20c7": "note"}))
    prior = {"t20": {**first["tables"][0], "judged": {"run": 2, "rev": 0}}}
    for ask in (_dead, _ask_roles({"t20c7": "title"}, drop=("t20",))):
        bad = HT.build(s1, use_llm=True, ask=ask, prior=prior, carry=TM.carry_over)
        t = bad["tables"][0]
        assert by_id(t, "t20c7")["role"] == "note" and _changed(t) == ["t20c7"] and t["llm"]["state"] == "carried" and t["judged"] == {"run": 2, "rev": 0}
        assert t["llm"]["sent"] and not t["llm"]["undecided"] and t["llm"]["error"] == "T 호출 실패 — 앞 판정을 이어 씀"
        assert (bad["llm"]["undecided"], bad["llm"]["carried"], bad["llm"]["pending"], bad["llm"]["pendingTables"]) == (0, 1, 1, ["t20"])
    assert HT.build(s1, use_llm=True, ask=_dead, prior=prior, carry=TM.carry_over)["llm"]["fallback"]
    lone = HT.build(s1, use_llm=True, ask=_dead, carry=TM.carry_over)   # 이을 판정이 없다
    t = lone["tables"][0]
    assert (t["llm"]["state"], t["llm"]["undecided"], by_id(t, "t20c7")["role"], lone["llm"]["undecided"], lone["llm"]["pending"]) == ("failed", True, "rowhead", 1, 1)


def test_answer_accepted_in_no_part_is_not_a_new_judgment():
    """답은 왔는데 하나도 받아들이지 못한 표(띠 나눔이 검증을 못 넘고 받은 칸도 없음)는 「고칠 것 없음」 이 아니다 — 새 판정으로 세지 않고 앞 판정을 이어 쓰며 보완 대상으로 남긴다.
    이을 판정이 없으면 초안 · 미판정(전에는 answered · 보완 대상 0 이 되어 다음 실행이 그 초안을 LLM 판정으로 이어 썼다)."""
    from app import table_manager as TM
    s1 = stage1(_plan_tab())

    def junk(jobs, **kw):   # 표 밖의 영역 + 없는 칸 id 만 답한다
        return [_res({"tables": [{"table": tp["table"], "subtables": [{"sub": "a", "rows": [0, 999], "cols": [0, 999], "kind": "matrix", "headerRows": 1, "headerCols": 1, "note": ""}],
                                  "cells": [{"cell": "없는칸", "role": "note", "reason": ""}], "summary": "엉뚱한 답"} for tp in _data(job)["tables"]], "summary": ""}) for job in jobs]
    first = HT.build(s1, use_llm=True, ask=_ask_roles({"t20c7": "note"}))
    prior = {"t20": {**first["tables"][0], "judged": {"run": 2, "rev": 0}}}
    bad = HT.build(s1, use_llm=True, ask=junk, prior=prior, carry=TM.carry_over)
    t = bad["tables"][0]
    assert by_id(t, "t20c7")["role"] == "note" and t["llm"]["state"] == "carried" and t["judged"] == {"run": 2, "rev": 0} and "받아들이지 못함" in t["llm"]["error"]
    assert (bad["llm"]["carried"], bad["llm"]["pending"], bad["llm"]["pendingTables"]) == (1, 1, ["t20"]) and t["llm"]["rejected"]
    lone = HT.build(s1, use_llm=True, ask=junk, carry=TM.carry_over)["tables"][0]   # 이을 판정이 없다 — 초안 · 미판정
    assert (lone["llm"]["state"], lone["llm"]["undecided"], by_id(lone, "t20c7")["role"]) == ("failed", True, "rowhead")


def test_only_picks_tables_after_place_guides_are_assigned():
    """자리 지침은 보낼 수 있는 표 전부에 먼저 배정하고 그다음에 물을 표를 고른다 — 겉 표를 묻지 않는다고 겉 표의 지침이 안쪽 표의 자료로 가지 않는다."""
    outer, inner = Tab("tA"), Tab("tB")
    for r in range(2):
        for c in range(2):
            outer.cell(r, c, f"겉{r}{c}", fill="#EEEEEE" if r == 0 else None)
            inner.cell(r, c, f"안{r}{c}", fill="#EEEEEE" if r == 0 else None)
    s1 = stage1(outer, inner)
    host = next(r["path"] for r in s1["paras"] if r["path"][-1]["id"] == "tAc4")   # 겉 표의 마지막 칸에 안쪽 표를 넣는다
    for r in s1["paras"]:
        if r["path"][0]["id"] == "tB":
            r["path"] = [host[0], host[1]] + r["path"]
        r["table"], r["cell"] = r["path"][-2]["id"], r["path"][-1]["id"]
    tables = HT.collect(s1)
    assert [(t["id"], t["depth"], HT.sendable(t)) for t in tables] == [("tA", 1, True), ("tB", 2, True)]
    drafts = {tb["id"]: HT.draft(tb) for tb in tables}
    pinned = {**G.snapshot(), "place": {"sha1": "s", "tables": {"tA": [{"at": "p1", "kind": "※ 안내", "text": "겉 표의 지침"}]}}}   # p1 = 겉 표 첫 칸의 문단
    jobs, _ = HT.t_jobs(tables, drafts, s1, pinned)
    got = {t["table"]: t for j in jobs for t in _data(j)["tables"]}
    assert got["tA"]["guides"] == [{"kind": "※ 안내", "text": "겉 표의 지침", "cell": "tAc1"}] and "guides" not in got["tB"]
    jobs, _ = HT.t_jobs(tables, drafts, s1, pinned, only={"tB"})
    assert [j["_tables"] for j in jobs] == [["tB"]] and jobs[0]["_guides"] == {} and "guides" not in _data(jobs[0])["tables"][0]
    assert HT.t_jobs(tables, drafts, s1, pinned, only=set())[0] == []
    asked = HT.ask_tables(s1, ask=_ask_roles({}), pinned=pinned, only={"tB"})
    assert asked["only"] == ["tB"] and list(asked["answers"]) == ["tB"] and HT.ask_tables(s1, ask=_ask_roles({}))["only"] is None


def _t(res, tid):
    return next(t for t in res["tables"] if t["id"] == tid)


def _first_cell(seen):
    """기술수요조사서 t8 — 첫 줄 둘째 칸을 열헤더로 고치는 가짜 `llm.ask_all`(초안은 행헤더 — test_build_llm_fake_applies_and_marks_failures 와 같은 칸)."""
    def ask(jobs, **kw):
        out = []
        for job in jobs:
            tabs = []
            for tp in _data(job)["tables"]:
                seen.append(tp["table"])
                tabs.append({"table": tp["table"], "subtables": [{"sub": b["id"], "rows": b["rows"], "cols": b["cols"], "kind": b["kind"], "headerRows": -1, "headerCols": -1, "note": ""}
                                                                  for b in tp["draft"]],
                             "cells": [{"cell": tp["grid"][0][1].split("|")[0], "role": "colhead", "reason": "분류 이름"}], "summary": ""})
            out.append(_res({"tables": tabs, "summary": ""}))
        return out
    return ask


def test_stage3_runs_carry_judgments_and_complement_asks_only_pending(client, monkeypatch):
    """3단계 실행(heading_runs.run_stage3) — 스크립트로 다시 돌려도 LLM 판정이 남고 · 보완 실행(again=False)은 보완 대상만(없으면 호출 없음) · 「표 구조(LLM)」(again 기본)은 전부 다시 ·
    호출이 모두 실패한 LLM 실행 뒤에도 앞 판정이 남는다. 답을 받은 표의 출처(judged)와 실행 목록의 judged 는 파일에 남는다."""
    from app import llm
    d = _upload(client, SMALL)
    sess = server.DOCS[d]
    seen = []
    monkeypatch.setattr(llm, "ask_all", _first_cell(seen))
    heading_runs.run_sync(sess, 3, True)   # 「표 구조(LLM)」 — 전부 묻는다(t1 은 3칸이라 안 보냄)
    st = heading_runs.state(sess)
    r1 = st["stage3"]
    n1, ch = r1["meta"]["run"], _changed(_t(r1, "t8"))
    assert seen == ["t8"] and len(ch) == 1 and _t(r1, "t8")["llm"]["state"] == "answered" and _t(r1, "t8")["judged"] == {"run": n1, "rev": sess.rev}
    assert _t(r1, "t1")["judged"] is None and _t(r1, "t1")["llm"]["state"] == "unsent"
    hd = works.folder(d) / "headings"
    assert json.loads((hd / str(n1) / "run.json").read_text("utf-8"))["judged"] == 1
    seen.clear()
    j2 = heading_runs.run_sync(sess, 3, False)   # 스크립트로 다시 — 초안으로 안 돌아간다
    r2 = st["stage3"]
    assert not seen and r2["meta"]["run"] == j2.run > n1 and not r2["llm"]["requested"]
    assert _changed(_t(r2, "t8")) == ch and _t(r2, "t8")["llm"]["state"] == "carried" and _t(r2, "t8")["judged"] == {"run": n1, "rev": sess.rev}
    assert (r2["llm"]["carried"], r2["llm"]["pending"]) == (1, 0) and "이어 씀 1 · 보완 대상 0" in j2.steps[-1]["msg"]
    assert json.loads((hd / str(j2.run) / "run.json").read_text("utf-8"))["judged"] == 1   # 스크립트 실행이어도 이어 쓴 판정이 들었다
    job = heading_runs.Job(3, True, sess.rev)
    st["job"] = job
    n3 = heading_runs.run_stage3(sess, job, True, again=False)   # 보완 실행 — 보완 대상이 없으면 호출이 없다
    r3 = st["stage3"]
    assert not seen and r3["meta"]["run"] == n3 and r3["llm"]["requested"] and not r3["llm"]["fallback"] and r3["llm"]["calls"] == 0
    assert _t(r3, "t8")["llm"]["state"] == "carried" and _changed(_t(r3, "t8")) == ch and "이어 씀 1 · 보완 대상 0" in job.steps[-1]["msg"]
    job = heading_runs.Job(3, True, sess.rev)   # 「LLM 검증·보완」 이 거는 꼴 — 인자 셋으로 불러도 보완 대상만
    job.tables_again = False
    heading_runs.run_stage3(sess, job, True)
    assert not seen and _t(st["stage3"], "t8")["llm"]["state"] == "carried"
    heading_runs.run_sync(sess, 3, True)   # 전부 다시 — 판정이 있어도 묻는다
    r5 = st["stage3"]
    assert seen == ["t8"] and _t(r5, "t8")["llm"]["state"] == "answered" and _t(r5, "t8")["judged"]["run"] == r5["meta"]["run"]
    monkeypatch.setattr(llm, "ask_all", _dead)
    heading_runs.run_sync(sess, 3, True)   # 호출이 모두 실패 — 앞 판정이 남는다
    r6 = st["stage3"]
    assert r6["llm"]["fallback"] and _changed(_t(r6, "t8")) == ch and _t(r6, "t8")["llm"]["state"] == "carried" and _t(r6, "t8")["judged"]["run"] == r5["meta"]["run"]
    assert (r6["llm"]["carried"], r6["llm"]["pending"], r6["llm"]["undecided"]) == (1, 1, 0)
    sess.heads = None   # 다시 연 세션 — 파일에 남은 것으로 같은 판정
    again = heading_runs.state(sess)["stage3"]
    assert _changed(_t(again, "t8")) == ch and _t(again, "t8")["judged"]["run"] == r5["meta"]["run"]
    assert heading_runs.stored_table(sess, "t8")[0] is _t(again, "t8") and heading_runs.stored_table(sess, "t8")[1] is True


def _old(res):
    """이 고침 전의 3단계 결과 꼴로 — 표의 `llm.state` · `judged`, 결과의 asked · carried · pending 이 없다."""
    res = copy.deepcopy(res)
    res.pop("_calls", None)
    for k in ("asked", "carried", "pending", "pendingTables"):
        res["llm"].pop(k, None)
    for t in res["tables"]:
        t.pop("judged", None)
        for k in ("state", "carried"):
            t["llm"].pop(k, None)
    return res


def _put_run(d, n, res, llm):
    """작업 폴더에 3단계 실행 하나를 손으로 적는다(옛 실행 — run.json 에 judged 가 없다)."""
    run = works.folder(d) / "headings" / str(n)
    run.mkdir(parents=True)
    res = {**res, "meta": {**res["meta"], "run": n}}
    (run / "tables.json").write_text(json.dumps(res, ensure_ascii=False), "utf-8")
    (run / "run.json").write_text(json.dumps({"stage": 3, "stage_key": "stage3", "n": n, "llm": llm, "rev": res["meta"]["rev"], "at": res["meta"]["at"]}), "utf-8")


def test_llm_tables_reads_back_to_the_last_valid_judgment(client, monkeypatch):
    """표마다 마지막으로 유효한 LLM 판정(heading_runs.llm_tables) — 최근 LLM 실행에서 그 표만 답을 못 받았으면 더 앞 실행의 판정을 고른다.
    이 고침 전의 꼴(지금 결과가 스크립트 초안 · 앞 실행에 LLM 판정)에서 stored_table 이 앞 판정을 주고, 스크립트로 다시 돌리면 그 판정을 이어 쓴다. 저장된 결과는 안 고친다."""
    from app import llm
    d = _upload(client, SMALL)
    sess = server.DOCS[d]
    seen = []
    monkeypatch.setattr(llm, "ask_all", _first_cell(seen))
    heading_runs.run_sync(sess, 3, True)
    st = heading_runs.state(sess)
    good = _old(st["stage3"])   # 옛 꼴의 LLM 결과 — t8 이 답을 받음
    ch = _changed(_t(good, "t8"))
    failed = _old(st["stage3"])   # 더 새 LLM 실행 — 그 표만 답을 못 받음(초안 그대로 · 미판정)
    _t(failed, "t8")["llm"].update(undecided=True, changed=0)
    for c in _t(failed, "t8")["cells"]:
        c["role"], c["changed"] = c["draft"], False
    script = _old({**HT.build(st["stage1"], use_llm=False), "meta": dict(good["meta"])})   # 그 뒤 스크립트로 다시 돌림(옛 동작 — 초안만 남음)
    assert len(ch) == 1 and not _changed(_t(script, "t8")) and "state" not in _t(good, "t8")["llm"]
    _put_run(d, 10, good, True)
    _put_run(d, 11, failed, True)
    _put_run(d, 12, script, False)
    hd = works.folder(d) / "headings"
    (hd / "current.json").write_text(json.dumps({"stage1": st["stage1"]["meta"]["run"], "stage3": 12}), "utf-8")
    on_disk = (hd / "10" / "tables.json").read_text("utf-8")
    sess.heads = None   # 다시 연 세션
    st = heading_runs.state(sess)
    cur = st["stage3"]
    assert cur["meta"]["run"] == 12 and not _changed(_t(cur, "t8"))
    got = heading_runs.llm_tables(sess)
    assert set(got) == {"t8"} and got["t8"]["judged"] == {"run": 10, "rev": good["meta"]["rev"]} and _changed(got["t8"]) == ch   # 11(그 표만 실패)을 지나 10 의 판정
    assert heading_runs.llm_tables(sess) is got   # 세션에 기억한다
    stored, same = heading_runs.stored_table(sess, "t8")
    assert stored is got["t8"] and same is False
    plain, same1 = heading_runs.stored_table(sess, "t1")   # 판정이 없는 표 — 지금 결과의 그 표 그대로
    assert plain is _t(cur, "t1") and same1 is True and heading_runs.stored_table(sess, "t999") == (None, True)
    assert "judged" not in _t(cur, "t8") and (hd / "10" / "tables.json").read_text("utf-8") == on_disk   # 저장된 결과는 그대로
    seen.clear()
    heading_runs.run_sync(sess, 3, False)   # 스크립트로 다시 — 앞 판정을 이어 쓴다
    t = _t(st["stage3"], "t8")
    assert not seen and _changed(t) == ch and t["llm"]["state"] == "carried" and t["judged"] == {"run": 10, "rev": good["meta"]["rev"]}
    assert heading_runs.stored_table(sess, "t8") == (t, True)
    monkeypatch.setattr(heading_runs, "T3_BACK", 0)   # 거슬러 읽지 않으면 지금 결과만
    st.pop("t3llm")
    assert set(heading_runs.llm_tables(sess)) == {"t8"}   # 지금 결과가 이어 쓴 것이라 그대로 유효하다
