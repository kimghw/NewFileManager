"""헤딩 추출 3단계 — 표 의미(spec_헤딩_추출 ② §9): 구분 헤더(단계·차년도·기관·연도·합계·비율·코드) · 숫자 · 합계/소계/코드/비율 수식과 엑셀 수식 글 ·
값 검증 상태 · 계층 합계(「계」 행) · 가중치 열 제외 · 표의 소속(2단계 그래프 / 1단계 어림) · 실물 양식(거짓 불일치 0) · 엑셀 내보내기 · API."""
import copy
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_calc as HC
from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, server
from app import heading_tables as HT
from app.hwpx_doc import HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
RND = SAMPLES / "연구개발계획서_양식.hwpx"
SMALL = SAMPLES / "기술수요조사서.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}
GREY = "#D9D9D9"


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


def _no_llm(jobs):
    return [{"data": None, "error": "off"} for _ in jobs]


# ---- 합성 표(1단계 레코드 꼴 — test_headings_tables 의 Tab 과 같은 계약) --------------------------------------------------

class Tab:
    def __init__(self, tid="t1", host="p0"):
        self.tid, self.host, self.cells = tid, host, []

    def cell(self, row, col, text="", rs=1, cs=1, kind=None, fill=None, bold=False, blank=False):
        cid = f"{self.tid}c{len(self.cells) + 1}"
        if kind is None:
            kind = "empty" if not text else "plain"
        self.cells.append({"id": cid, "row": row, "col": col, "rs": rs, "cs": cs, "fill": fill, "bold": bold, "text": text, "kind": kind, "blank": blank})
        return cid

    def head(self, row, col, text, rs=1, cs=1):
        return self.cell(row, col, text, rs=rs, cs=cs, fill=GREY)

    def num(self, row, col, text, rs=1, cs=1):
        return self.cell(row, col, text, rs=rs, cs=cs, kind="data")

    def paras(self, start_n=0):
        rows = max(c["row"] + c["rs"] for c in self.cells)
        cols = max(c["col"] + c["cs"] for c in self.cells)
        out, n = [], start_n
        for c in self.cells:
            n += 1
            out.append({"id": f"p{n}", "n": n, "kind": c["kind"], "text": c["text"], "blank": c["blank"], "fmt": "S1", "area": "cell",
                        "char": {"text": {"bold": c["bold"], "sizePt": 10}, "letter": None},
                        "path": [{"t": "tbl", "id": self.tid, "rows": rows, "cols": cols, "cells": len(self.cells), "key": 1, "host": self.host},
                                 {"t": "cell", "id": c["id"], "row": c["row"], "col": c["col"], "rs": c["rs"], "cs": c["cs"], "fill": c["fill"], "key": 2}]})
        return out


def stage1(*tabs, before=None, body=()):
    """body = 표 앞 본문 문단 [(kind, text)…] — 1단계 어림 소속 시험용."""
    paras = []
    for kind, text in body:
        paras.append({"id": f"p{len(paras)}", "n": len(paras), "kind": kind, "text": text, "blank": False, "fmt": "S0", "area": "body",
                      "char": {"text": {}, "letter": None}, "path": []})
    if before:
        paras.append({"id": f"p{len(paras)}", "n": len(paras), "kind": "marker", "text": before, "blank": False, "fmt": "S0", "area": "body",
                      "char": {"text": {}, "letter": None}, "path": []})
    for t in tabs:
        paras += t.paras(len(paras))
    return {"paras": paras, "labels": {}}


def build(*tabs, before=None, body=(), stage2=None):
    return HT.build(stage1(*tabs, before=before, body=body), use_llm=False, ask=_no_llm, stage2=stage2)


def cell_at(t, row, col):
    return next(c for c in t["cells"] if c["row"] == row and c["col"] == col)


def fx(t, row, col):
    """칸의 수식들 {axis: 수식}."""
    c = cell_at(t, row, col)
    return {f["axis"]: f for f in t["formulas"] if f["id"] in (c.get("formulas") or [])}


def budget_tab():
    """8-1. 연구개발비 꼴 — 구분(2x2 귀퉁이) | 정부지원 | 기관부담(1x3) | 합계(1x3) ; 단계 | 기관 | 현금(A) | 현금(B) | 현물(C) | 소계(D) | 현금 | 현물 | 합계(E) ;
    ^ | ^ | 비율(A/E) | 비율(B/D) | 비율(C/D) | 비율(D/E) | ^ | ^ | ^ ; 값 줄 + 비율 줄 × 2 기관(둘째 기관의 소계(D)가 틀림) ; 소계 줄(세로 합)."""
    t = Tab("t1")
    t.head(0, 0, "구분", rs=1, cs=2)
    t.head(0, 2, "정부지원 연구개발비")
    t.head(0, 3, "기관부담연구개발비", cs=3)
    t.head(0, 6, "합  계", cs=3)
    t.head(1, 0, "단계", rs=2)
    t.head(1, 1, "연구개발기관", rs=2)
    for i, name in enumerate(["현금(A)", "현금(B)", "현물(C)", "소계(D)"]):
        t.head(1, 2 + i, name)
    for i, name in enumerate(["현금", "현물", "합계(E)"]):
        t.head(1, 6 + i, name, rs=2)
    for i, name in enumerate(["비율(A/E)", "비율(B/D)", "비율(C/D)", "비율(D/E)"]):
        t.head(2, 2 + i, name)
    rows = [("1", "주관연구개발기관", ["800,000", "20,000", "180,000", "200,000", "820,000", "180,000", "1,000,000"], ["80% (A/E)", "10.0% (B/D)", "90.0% (C/D)", "20.0% (D/E)"]),
            ("1", "공동연구개발기관", ["100,000", "10,000", "10,000", "25,000", "110,000", "10,000", "120,000"], ["83.3% (A/E)", "40.0% (B/D)", "40.0% (C/D)", "20.8% (D/E)"])]
    r = 3
    for stage, org, vals, pcts in rows:
        t.num(r, 0, stage, rs=2)
        t.cell(r, 1, org, rs=2)
        for i, v in enumerate(vals[:4]):
            t.num(r, 2 + i, v)
        for i, v in enumerate(vals[4:]):
            t.num(r, 6 + i, v, rs=2)
        for i, v in enumerate(pcts):
            t.num(r + 1, 2 + i, v)
        r += 2
    t.cell(r, 0, "소계", cs=2)
    for i, v in enumerate(["900,000", "30,000", "190,000", "225,000", "930,000", "190,000", "1,120,000"]):
        t.num(r, 2 + i, v)
    return t


# ---- 1. 구분 헤더 · 숫자 -----------------------------------------------------------------------------------------

def test_header_basis_patterns():
    hb = HC.header_basis
    assert hb("1단계")["basis"] == ["stage"] and hb("1단계")["kind"] == "value"
    assert hb("n단계 (YYYY~YYYY)")["basis"] == ["stage", "period"]
    assert hb("2차년도")["basis"] == ["year"] and hb("3년차")["basis"] == ["year"] and hb("매출액발생 1년차")["basis"] == ["year"] and hb("1차 년도")["basis"] == ["year"]
    assert hb("1단계-1차년도")["basis"] == ["stage", "year"]
    assert hb("2024년")["basis"] == ["period"] and hb("YYYY. MM.")["basis"] == ["period"]
    assert hb("단계")["kind"] == "name" and hb("단계")["basis"] == ["stage"]
    assert hb("연 도")["basis"] == ["year"] and hb("차년도")["basis"] == ["year"] and hb("연차")["kind"] == "name"
    assert hb("연구개발기관")["basis"] == ["org"] and hb("기관명")["kind"] == "name" and hb("연구개발 기관명")["basis"] == ["org"]
    assert hb("주관연구개발기관")["kind"] == "value" and hb("공동연구개발기관2")["basis"] == ["org"]
    assert hb("[주관연구개발기관(기관명 기입)]")["basis"] == ["org"] and HC.label_basis("[주관연구개발기관(기관명 기입)]") == ["org"] and HC.label_basis("[1단계]") == ["stage"]
    assert hb("중앙행정기관명")["basis"] == [] and hb("전문기관명")["basis"] == []
    for s in ("계", "합  계", "총계", "Total", "합계 금액"):
        assert hb(s)["kind"] == "total" and not hb(s).get("subtotal"), s
    d = hb("소계(D)")
    assert d["kind"] == "total" and d["subtotal"] is True and d["code"] == "D"
    r = hb("비율(A/E)")
    assert r["kind"] == "ratio" and r["expr"] == "A/E" and r["basis"] == ["ratio"]
    a = hb("현금(A)")
    assert a["code"] == "A" and a["basis"] == [] and a["kind"] is None
    w = hb("가중치 (%)")
    assert w.get("pctUnit") is True and w["basis"] == []
    assert hb("연구개발비15)")["basis"] == [] and HC.core("주관연구개발기관14)") == "주관연구개발기관" and HC.core("기술기여도(단위: %)") == "기술기여도"
    # above(같은 열 위 열헤더 이름)에서 받는 값
    assert hb("1", {"basis": ["stage"], "kind": "name"}) == {"basis": ["stage"], "kind": "value"}
    assert hb("XXXXX", {"basis": ["org"], "kind": "name"})["basis"] == ["org"]
    assert hb("1차", {"basis": ["year"], "kind": "name"})["basis"] == ["year"] and hb("1차")["basis"] == []
    assert hb("계획수립")["basis"] == [] and hb("")["kind"] is None


def test_parse_num():
    p = HC.parse_num
    assert p("800,000") == {"num": 800000.0, "dec": 0}
    assert p("80% (A/E)") == {"num": 80.0, "dec": 0, "pct": True} and p("10.0% (B/D)") == {"num": 10.0, "dec": 1, "pct": True}
    assert p("(1,234)")["num"] == -1234.0 and p("-5")["num"] == -5.0 and p("▲ 5")["num"] == -5.0
    assert p("-") == {"num": 0.0, "dash": True} and p("—")["dash"] is True
    assert p("0,000,000", {"placeholder": 1}) == {"num": None, "placeholder": True} and p("000,000") == {"num": None, "placeholder": True} and p("00%")["placeholder"]
    assert p("1,234천원")["num"] == 1234.0 and p("12.5%")["pct"] is True
    assert p("총    천원 (") == {"num": None, "text": True} and p("") == {"num": None} and p("0")["num"] == 0.0
    assert HC.col_letter(0) == "A" and HC.col_letter(25) == "Z" and HC.col_letter(26) == "AA" and HC.ref({"row": 3, "col": 5}) == "F4"


# ---- 2. 수식 — 합계·코드·비율·검증 ------------------------------------------------------------------------------------

def test_budget_sums_codes_and_mismatch():
    out = build(budget_tab(), before="8-1. 연구개발비 지원·부담계획 (단위: 천원)")
    t = out["tables"][0]
    s = t["subtables"][0]
    assert s["kind"] == "matrix" and s["headerRows"] == 3 and s["headerCols"] == 2, s
    assert t["unit"] == "천원" and t["basis"] == ["org", "stage"] and t["calc"]["is"] is True
    assert s["calc"]["why"] == "합계 헤더 · 비율 헤더 · 코드 식 · 숫자 필드 29"
    assert [a["basis"] for a in s["axes"]["row"]] == ["stage", "org"] and s["axes"]["row"][1]["values"] == ["주관연구개발기관", "공동연구개발기관"]
    heads = {c["text"]: c for c in t["cells"] if c["role"] in ("colhead", "rowhead", "corner")}
    assert heads["소계(D)"]["code"] == "D" and heads["소계(D)"]["subtotal"] and heads["비율(A/E)"]["expr"] == "A/E" and heads["1"]["basis"] == ["stage"]
    assert heads["주관연구개발기관"]["basis"] == ["org"] and heads["소계"]["basis"] == ["total"]
    # 첫 기관 값 줄(엑셀 4행): 소계(D) = B + C · 합계›현금 = A + B · 합계›현물 = C · 합계(E) = 현금 + 현물
    f = fx(t, 3, 5)["col"]
    assert f["formula"] == "=SUM(D4:E4)" and f["expected"] == 200000 and f["actual"] == 200000 and f["status"] == "ok" and f["kind"] == "sum" and f["excel"] is True
    assert fx(t, 3, 6)["col"]["formula"] == "=SUM(C4:D4)" and fx(t, 3, 6)["col"]["expected"] == 820000 and fx(t, 3, 6)["col"]["status"] == "ok"
    assert fx(t, 3, 7)["col"]["formula"] == "=E4" and fx(t, 3, 8)["col"]["formula"] == "=SUM(G4:H4)" and fx(t, 3, 8)["col"]["expected"] == 1000000
    # 비율 줄(엑셀 5행): 코드 식 — 값이 % 라 ×100
    r = fx(t, 4, 2)["col"]
    assert r["kind"] == "expr" and r["formula"] == "=(C4/I4)*100" and r["expected"] == 80 and r["status"] == "ok"
    assert fx(t, 4, 5)["col"]["formula"] == "=(F4/I4)*100" and fx(t, 4, 5)["col"]["expected"] == 20
    assert fx(t, 4, 3)["col"]["formula"] == "=(D4/F4)*100" and fx(t, 4, 3)["col"]["expected"] == 10
    # 둘째 기관(엑셀 6행): 소계(D) 25,000 ≠ 10,000 + 10,000 → 불일치, 나머지는 맞음, 비율 20.8% ≈ 25,000/120,000
    bad = fx(t, 5, 5)["col"]
    assert bad["status"] == "mismatch" and bad["expected"] == 20000 and bad["actual"] == 25000 and bad["diff"] == 5000
    assert fx(t, 5, 8)["col"]["status"] == "ok" and fx(t, 6, 5)["col"]["status"] == "ok" and fx(t, 6, 5)["col"]["expected"] == pytest.approx(20.8333, abs=1e-3)
    # 소계 줄(엑셀 8행): 세로 합(행 축) — 비율 줄은 % 라 피연산자가 아님 → 이어지지 않아 더하기 꼴; 소계(D) 칸은 두 수식(행 축 맞음 · 열 축 틀림), 엑셀엔 행 축만
    assert fx(t, 7, 2)["row"]["formula"] == "=C4+C6" and fx(t, 7, 2)["row"]["expected"] == 900000 and fx(t, 7, 2)["row"]["status"] == "ok"
    both = fx(t, 7, 5)
    assert set(both) == {"row", "col"} and both["row"]["formula"] == "=F4+F6" and both["row"]["status"] == "ok" and both["row"]["excel"] is True
    assert both["col"]["formula"] == "=SUM(D8:E8)" and both["col"]["status"] == "mismatch" and both["col"]["expected"] == 220000 and both["col"]["excel"] is False
    assert "현금(A)" not in both["col"]["note"] and both["row"]["note"].startswith("소계 = 1 + 1")
    c = t["calc"]
    assert c["formulas"] == len(t["formulas"]) == 27 and c["mismatch"] == 2 and c["ok"] == 25 and c["missing"] == c["blank"] == c["incomplete"] == 0, c
    # 필드의 구분 값
    assert cell_at(t, 3, 2)["div"] == {"stage": "1", "org": "주관연구개발기관"} and cell_at(t, 5, 8)["div"]["org"] == "공동연구개발기관"
    assert cell_at(t, 3, 2)["num"] == 800000 and cell_at(t, 4, 2)["pct"] is True and cell_at(t, 4, 2)["num"] == 80
    assert out["counts"]["calc"] == {"tables": 1, "formulas": 27, "ok": 25, "mismatch": 2, "missing": 0, "incomplete": 0, "blank": 0, "nonnumeric": 0}
    assert out["counts"]["basis"] == {"stage": 1, "year": 0, "org": 1, "period": 0} and out["counts"]["basisTables"] == 1
    assert out["counts"]["owners"] == {"stage1": 1} and t["owner"]["text"].startswith("8-1.") and t["owner"]["source"] == "stage1"


def test_hierarchical_total_row_and_weight_column():
    """연도 \\ 성과지표명 | 1단계 | n단계 | 계 | 가중치(%) ; 전담기관(2x1) › 지표1 › 목표 | 10 | 20 | 30 | 40% ; 지표2 … | 5 | 5 | 10 | 20% ; 과제특성 › 지표1 › 목표 | 1 | 2 | 3 | 40% ;
    계(1x2) | (빈 행헤더) | 16 | 27 | 43 | 100%"""
    t = Tab("t2")
    t.head(0, 0, "연도 성과지표명", cs=3)
    for i, name in enumerate(["1단계 (YYYY~YYYY)", "n단계 (YYYY~YYYY)", "계", "가중치 (%)"]):
        t.head(0, 3 + i, name)
    t.cell(1, 0, "전담기관 등록ㆍ기탁 지표", rs=2)
    for r, (ind, vals) in enumerate([("지표1", ["10", "20", "30", "40%"]), ("지표2", ["5", "5", "10", "20%"])], start=1):
        t.cell(r, 1, ind)
        t.cell(r, 2, "목표(단계별)")
        for i, v in enumerate(vals):
            t.num(r, 3 + i, v)
    t.cell(3, 0, "연구개발과제 특성 반영 지표")
    t.cell(3, 1, "지표1")
    t.cell(3, 2, "목표(단계별)")
    for i, v in enumerate(["1", "2", "3", "40%"]):
        t.num(3, 3 + i, v)
    t.cell(4, 0, "계", cs=2)
    t.cell(4, 2, "")
    for i, v in enumerate(["16", "27", "43", "100%"]):
        t.num(4, 3 + i, v)
    out = build(t)
    tb = out["tables"][0]
    s = tb["subtables"][0]
    assert s["headerRows"] == 1 and s["headerCols"] == 3 and s["calc"]["is"] and "합계 헤더" in s["calc"]["why"]
    assert tb["basis"] == ["period", "stage", "year"] and s["axes"]["col"][0]["basis"] == "year" and s["axes"]["col"][0]["kind"] == "name"
    # 계 열 = 1단계 + n단계 (가중치 제외)
    f = fx(tb, 1, 5)["col"]
    assert f["formula"] == "=SUM(D2:E2)" and f["expected"] == 30 and f["status"] == "ok" and len(f["operands"]) == 2
    assert fx(tb, 2, 5)["col"]["expected"] == 10 and fx(tb, 3, 5)["col"]["expected"] == 3
    # 계 행(빈 행헤더는 투명) = 묶음(전담기관 › 지표1·지표2 · 과제특성 › 지표1) 잎 전부 — 가중치 열도 세로 합(% 끼리)
    assert fx(tb, 4, 3)["row"]["formula"] == "=SUM(D2:D4)" and fx(tb, 4, 3)["row"]["expected"] == 16 and fx(tb, 4, 3)["row"]["status"] == "ok"
    assert fx(tb, 4, 4)["row"]["expected"] == 27 and fx(tb, 4, 6)["row"]["formula"] == "=SUM(G2:G4)" and fx(tb, 4, 6)["row"]["expected"] == 100
    both = fx(tb, 4, 5)
    assert both["row"]["formula"] == "=SUM(F2:F4)" and both["col"]["formula"] == "=SUM(D5:E5)" and both["row"]["excel"] and not both["col"]["excel"]
    assert all(f["status"] == "ok" for f in tb["formulas"]) and tb["calc"]["formulas"] == 8  # 계 열 3 + 계 행 4(계×계 칸은 행·열 둘)
    assert cell_at(tb, 1, 3)["div"] == {"stage": "1단계 (YYYY~YYYY)", "period": "1단계 (YYYY~YYYY)"}


def test_ratio_column_without_codes_and_statuses():
    """항목 | 금액 | 구성비(%) ; A 30 30.0% ; B 70 70.0% ; C (빈 칸) (빈 칸) ; 합계 100 100% — 구성비 = 금액 ÷ 합계 금액 × 100, 빈 칸은 미검증, 합계 칸이 비면 미기입."""
    t = Tab("t3")
    for i, name in enumerate(["항목", "금액", "구성비(%)"]):
        t.head(0, i, name)
    for r, (a, b, c) in enumerate([("A", "30", "30.0%"), ("B", "70", "70.0%"), ("C", "", "")], start=1):
        t.cell(r, 0, a)
        t.num(r, 1, b) if b else t.cell(r, 1, "")
        t.num(r, 2, c) if c else t.cell(r, 2, "")
    t.cell(4, 0, "합계")
    t.num(4, 1, "100")
    t.num(4, 2, "100%")
    out = build(t)
    tb = out["tables"][0]
    ra = fx(tb, 1, 2)["col"]
    assert ra["kind"] == "ratio" and ra["formula"] == "=B2/B5*100" and ra["expected"] == 30 and ra["status"] == "ok"
    assert fx(tb, 2, 2)["col"]["expected"] == 70 and fx(tb, 2, 2)["col"]["status"] == "ok"
    assert fx(tb, 3, 2)["col"]["status"] == "incomplete"  # 금액이 비어 비율을 셀 수 없음
    tot = fx(tb, 4, 1)["row"]
    assert tot["formula"] == "=SUM(B2:B4)" and tot["status"] == "incomplete"  # C 가 빈 칸 → 미검증(거짓 불일치 아님)
    both = fx(tb, 4, 2)
    assert both["col"]["kind"] == "ratio" and both["col"]["expected"] == 100 and both["col"]["status"] == "ok" and both["row"]["status"] == "incomplete"
    # 합계 칸이 비어 있으면 미기입, 수가 아닌 글이면 nonnumeric, 모두 비면 blank
    t2 = Tab("t4")
    for i, name in enumerate(["항목", "금액"]):
        t2.head(0, i, name)
    t2.cell(1, 0, "A")
    t2.num(1, 1, "3")
    t2.cell(2, 0, "B")
    t2.num(2, 1, "4")
    t2.cell(3, 0, "합계")
    t2.cell(3, 1, "")
    t2.cell(4, 0, "총계")
    t2.cell(4, 1, "미정")
    tb2 = build(t2)["tables"][0]
    assert fx(tb2, 3, 1)["row"]["status"] == "missing" and fx(tb2, 3, 1)["row"]["expected"] == 7 and fx(tb2, 3, 1)["row"]["actual"] is None
    assert fx(tb2, 4, 1)["row"]["status"] == "nonnumeric" and fx(tb2, 4, 1)["row"]["formula"] == "=SUM(B2:B3)"
    t3 = Tab("t5")
    for i, name in enumerate(["항목", "금액"]):
        t3.head(0, i, name)
    for r, a in enumerate(["A", "B", "합계"], start=1):
        t3.cell(r, 0, a)
        t3.cell(r, 1, "0,000,000", kind="placeholder")
    tb3 = build(t3)["tables"][0]
    assert fx(tb3, 3, 1)["row"]["status"] == "blank" and tb3["calc"]["is"] and tb3["calc"]["blank"] == 1 and tb3["calc"]["mismatch"] == 0


def test_subtotal_groups_and_dash():
    """인건비 10 · 재료비 - (0) · 소계 10 · 간접비 5 · 소계 5 · 합계 15 — 소계는 제 묶음만, 합계는 소계들의 합."""
    t = Tab("t6")
    t.head(0, 0, "비목")
    t.head(0, 1, "금액")
    for r, (a, b) in enumerate([("인건비", "10"), ("재료비", "-"), ("소계", "10"), ("간접비", "5"), ("소계", "5"), ("합계", "15")], start=1):
        t.cell(r, 0, a)
        t.num(r, 1, b)
    tb = build(t)["tables"][0]
    assert fx(tb, 3, 1)["row"]["formula"] == "=SUM(B2:B3)" and fx(tb, 3, 1)["row"]["expected"] == 10 and fx(tb, 3, 1)["row"]["status"] == "ok"
    assert fx(tb, 5, 1)["row"]["formula"] == "=B5" and fx(tb, 5, 1)["row"]["expected"] == 5
    assert fx(tb, 6, 1)["row"]["formula"] == "=B4+B6" and fx(tb, 6, 1)["row"]["expected"] == 15 and fx(tb, 6, 1)["row"]["status"] == "ok"
    assert cell_at(tb, 2, 1)["dash"] is True and cell_at(tb, 2, 1)["num"] == 0


# ---- 3. 소속 -------------------------------------------------------------------------------------------------------

def test_owner_from_graph_climbs_nested_cells():
    nodes = [{"id": "pX", "para": "pX", "letter": "1.", "text": "개요", "role": "heading", "parent": "root", "division": "pL", "template": "body:N.", "tplNo": 1, "level": 1},
             {"id": "pL", "para": "pL", "letter": "[1단계]", "text": "", "role": "label", "parent": "pX", "division": None, "template": "body:[단계]", "tplNo": 2, "level": 1},
             {"id": "pY", "para": "pY", "letter": "가.", "text": "세부", "role": "heading", "parent": "pX", "division": "pL", "template": "body:N.›가.", "tplNo": 1, "level": 2}]
    containers = [{"id": "tbl:t0", "kind": "table", "parent": "pY"}, {"id": "cell:c9", "kind": "cell", "parent": "tbl:t0"}, {"id": "tbl:t1", "kind": "table", "parent": "cell:c9"},
                  {"id": "tbl:t7", "kind": "table", "parent": "root"}, {"id": "tbl:t8", "kind": "table", "parent": "pL"}]
    s2 = {"nodes": nodes, "containers": containers}
    owner = HC.owners_index({"paras": []}, s2)
    o = owner({"id": "t1", "n": 0})
    assert o["text"] == "가. 세부" and o["path"] == ["1. 개요"] and o["tplNo"] == 1 and o["level"] == 2 and o["source"] == "stage2"
    assert o["division"]["text"] == "[1단계]" and o["division"]["basis"] == ["stage"]
    assert owner({"id": "t7", "n": 0}) == {"source": "stage2", "root": True}
    lab = owner({"id": "t8", "n": 0})
    assert lab["role"] == "label" and lab["division"]["id"] == "pL" and lab["text"] == "[1단계]"
    assert owner({"id": "t99", "n": 0}) is None  # 그래프에 없고 1단계 본문도 없음


def test_owner_stage1_fallback_and_stage2_passthrough():
    body = [("marker", "1. 개요"), ("label", "[주관연구개발기관(기관명 기입)]"), ("plain", "본문 글"), ("marker", "□ 목표")]
    t = Tab("t1")
    t.head(0, 0, "항목")
    t.head(0, 1, "값")
    t.cell(1, 0, "A")
    t.num(1, 1, "1")
    tb = build(t, body=body)["tables"][0]
    o = tb["owner"]
    assert o["source"] == "stage1" and o["text"] == "□ 목표" and o["role"] == "heading" and o["division"] is None and o["template"] is None
    tb = build(t, body=body[:3])["tables"][0]
    o = tb["owner"]
    assert o["text"] == "1. 개요" and o["division"]["text"] == "[주관연구개발기관(기관명 기입)]" and o["division"]["basis"] == ["org"]
    tb = build(t, body=[("label", "[1단계]")])["tables"][0]
    assert tb["owner"]["role"] == "label" and tb["owner"]["text"] == "[1단계]"
    assert build(t)["tables"][0]["owner"] is None and build(t)["counts"]["owners"] == {"none": 1}
    s2 = {"nodes": [{"id": "pZ", "para": "pZ", "letter": "2.", "text": "둘", "role": "heading", "parent": "root", "division": None, "template": "body:N.", "tplNo": 1, "level": 1}],
          "containers": [{"id": "tbl:t1", "kind": "table", "parent": "pZ"}]}
    tb = build(t, body=body, stage2=s2)["tables"][0]
    assert tb["owner"]["source"] == "stage2" and tb["owner"]["text"] == "2. 둘"


# ---- 4. 실물 양식 ---------------------------------------------------------------------------------------------------

def test_rnd_form_no_false_alarms_and_semantics(rnd):
    out = HT.build(rnd, use_llm=False, ask=_no_llm)
    c = out["counts"]
    assert c["calc"]["mismatch"] == 0 and c["calc"]["missing"] == 0 and c["calc"]["nonnumeric"] == 0 and c["calc"]["tables"] >= 15 and c["calc"]["ok"] == 8
    assert c["basisTables"] >= 60 and c["basis"]["stage"] >= 15 and c["basis"]["year"] >= 20 and c["basis"]["org"] >= 40
    assert c["owners"]["stage1"] > 120 and "stage2" not in c["owners"]
    by = {t["id"]: t for t in out["tables"]}
    b = by["t8546"]  # 8-1. 연구개발비 지원·부담계획 — 코드 헤더 양식
    assert b["unit"] == "천원" and b["basis"] == ["org", "stage", "year"] and b["calc"]["is"] and b["calc"]["ok"] == 8 and b["calc"]["mismatch"] == 0
    ok = [f for f in b["formulas"] if f["status"] == "ok"]
    assert sorted(f["formula"] for f in ok) == sorted(["=SUM(F5:G5)", "=SUM(E5:F5)", "=G5", "=SUM(I5:J5)", "=(E5/K5)*100", "=(F5/H5)*100", "=(G5/H5)*100", "=(H5/K5)*100"])
    assert {f["expected"] for f in ok} == {200000, 820000, 180000, 1000000, 80, 10, 90, 20}
    assert b["owner"]["source"] == "stage1" and b["owner"]["text"].startswith("8-1.")
    heads = {x["text"]: x for x in b["cells"] if x.get("basis")}
    assert heads["단계"]["basisKind"] == "name" and heads["연차"]["basis"] == ["year"] and heads["연구개발기관"]["basis"] == ["org"]
    assert heads["1"]["basisKind"] == "value" and heads["소계(D)"]["code"] == "D" and heads["비율(A/E)"]["expr"] == "A/E" and heads["합계(E)"]["code"] == "E"
    g = by["t1339"]  # <연구개발성과의 지표 및 목표> — 「계」 열·행, 가중치(%) 제외
    assert g["calc"]["is"] and all(f["status"] == "blank" for f in g["formulas"]) and len(g["formulas"]) == 9
    names = {x["id"]: x["text"] for x in g["cells"]}
    assert all("가중치" not in names[o] for f in g["formulas"] if f["axis"] == "col" for o in f["operands"])
    sched = by["t1888"]["subtables"][0]["axes"]["col"]  # 2-3. 수행일정 — 추진 일정 › 단계 › 차년도
    assert [(a["level"], a["basis"]) for a in sched] == [(2, "stage"), (3, "year")] and sched[1]["values"][:2] == ["1차년도", "2차년도"]
    assert by["t1533"]["subtables"][0]["axes"]["row"][0]["values"][0] == "1단계-1차년도"
    assert by["t734"]["basis"] == ["org", "year"] and by["t734"]["subtables"][0]["axes"]["col"][0] == {"level": 1, "basis": "org", "kind": "name", "count": 1, "values": []}
    assert any(l["basis"] == ["org"] for t in out["tables"] for l in t["labels"])  # 칸 안 「[…기관명 기입]」 라벨


def test_rnd_owner_from_stage2_graph(rnd):
    g = HG.build(rnd, use_llm=False, ask=_no_llm)
    g["meta"] = {"stage1Run": 1}
    out = HT.build(rnd, use_llm=False, ask=_no_llm, stage2=g)
    assert out["counts"]["owners"] == {"stage2": 135}
    by = {t["id"]: t for t in out["tables"]}
    o = by["t8546"]["owner"]
    assert o["text"] == "8-1. 연구개발비 지원·부담계획" and o["tplNo"] == 1 and o["level"] == 2 and o["template"].startswith("body:") and o["path"] and o["division"] is None
    sub = by["t734"]["owner"]  # 괄호 소제목 — 표의 소속(제목)은 되지만 구분 라벨이 아니다(구분 소속 없음, spec ② §13)
    assert sub["role"] == "subtitle" and sub["text"] == "[연구개발성과의 기술기여도]" and sub["division"] is None
    div = next(t["owner"]["division"] for t in out["tables"] if (t["owner"] or {}).get("division"))  # 구분 라벨 아래 표 — 구분 기준은 2단계가 정한 것 그대로
    assert div["key"] in ("[기관]", "[단계]", "[차년도]") and div["basis"] == [{"[기관]": "org", "[단계]": "stage", "[차년도]": "year"}[div["key"]]]
    assert by["t1"]["owner"] == {"source": "stage2", "root": True}


# ---- 5. 엑셀 · API --------------------------------------------------------------------------------------------------

def test_workbook_grid_formulas_and_sheets():
    from openpyxl import load_workbook
    out = build(budget_tab(), before="8-1. 연구개발비 지원·부담계획 (단위: 천원)")
    t = out["tables"][0]
    wb = load_workbook(io.BytesIO(HC.workbook(t, "양식.hwpx")))
    assert wb.sheetnames == ["표", "검증", "필드", "정보"]
    ws = wb["표"]
    assert ws["F4"].value == "=SUM(D4:E4)" and ws["C4"].value == 800000 and ws["C5"].value == "=(C4/I4)*100" and ws["I4"].value == "=SUM(G4:H4)"
    assert ws["F8"].value == "=F4+F6" and ws["A2"].value == "단계" and ws["C2"].value == "현금(A)" and ws["F4"].comment and "불일치" in ws["F6"].comment.text
    assert any(str(m) == "A1:B1" for m in ws.merged_cells.ranges) and any(str(m) == "G2:G3" for m in ws.merged_cells.ranges)
    v = wb["검증"]
    rows = list(v.iter_rows(values_only=True))
    assert rows[0][:3] == ("수식", "칸", "주소") and len(rows) == len(t["formulas"]) + 1 and any(r[9] == "불일치" for r in rows[1:])
    p = wb["필드"]
    prow = list(p.iter_rows(values_only=True))
    assert prow[0][5:8] == ("단계", "차년도", "기관") and len(prow) == 1 + sum(1 for c in t["cells"] if c["role"] == "field")
    assert any(r[7] == "주관연구개발기관" and r[9] == 800000 for r in prow[1:])
    info = list(wb["정보"].iter_rows(values_only=True))
    assert info[0][:2] == ("문서", "양식.hwpx") and info[6][1] == "천원"


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_api_xlsx_route_and_summary():
    from openpyxl import load_workbook
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        d = _upload(c, SMALL)
        assert c.get(f"/api/docs/{d}/headings/tables/t8/xlsx").status_code == 404
        sess = server.DOCS[d]
        j = heading_runs.run_sync(sess, 3, False)
        assert j.status == "done" and "소속 = 1단계 어림" in j.steps[-1]["msg"] and "계산식 표" in j.steps[-1]["msg"]
        v = heading_runs.summary(sess)["stage3"]
        assert v["tables"][1]["id"] == "t8" and "owner" in v["tables"][1] and v["tables"][1]["calc"]["is"] is False and v["counts"]["owners"]
        r = c.get(f"/api/docs/{d}/headings/tables/t8/xlsx")
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats") and "t8.xlsx" in r.headers["content-disposition"]
        wb = load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames == ["표", "검증", "필드", "정보"] and wb["표"].max_row == 18
        assert c.get(f"/api/docs/{d}/headings/tables/t999/xlsx").status_code == 404
        full = c.get(f"/api/docs/{d}/headings/tables").json()
        assert full["version"] == 2 and "calc" in full["tables"][1] and "formulas" in full["tables"][1] and full["counts"]["basisTables"] == 0
    finally:
        server.DOCS.clear()


def test_run_stage3_uses_fresh_stage2_only():
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        d = _upload(c, SMALL)
        sess = server.DOCS[d]
        heading_runs.run_sync(sess, 1, False)
        heading_runs.run_sync(sess, 2, False)
        j = heading_runs.run_sync(sess, 3, False)
        assert "소속 = 2단계 그래프" in j.steps[-1]["msg"]
        st = heading_runs.state(sess)
        assert all(t["owner"] and t["owner"]["source"] == "stage2" for t in st["stage3"]["tables"])
        sess.rev += 1  # 문서가 바뀜 → 1단계를 다시 뽑고, 옛 2단계는 다른 1단계 실행의 것이라 안 씀
        j = heading_runs.run_sync(sess, 3, False)
        assert "소속 = 1단계 어림" in j.steps[-1]["msg"]
        time.sleep(0.05)
    finally:
        server.DOCS.clear()


# ---- 6. 코드 정의 「(M=K+L)」 · 두 글자 코드 「E1」 · 안쪽 괄호 · 부모 헤더 코드 (2026-11-10 연구개발기관별 사용계획 총괄표) ------------------------------

def test_code_info_forms():
    ci = HC.code_info
    e1 = ci("총 인건비1)(E1=A+B+C+D)")
    assert (e1["code"], e1["expr"]) == ("E1", "A+B+C+D") and ci("연구개발비 총액(M=K+L)")["code"] == "M" and ci("연구개발비 총액(M=K+L)")["expr"] == "K+L"
    r = ci("간접비 비율4)(L/(N+O+C+D+P+Q+R+I+S))")
    assert r.get("code") is None and r["expr"] == "L/(N+O+C+D+P+Q+R+I+S)"
    assert ci("연구수당 비율3)(I/E2)")["expr"] == "I/E2" and ci("현금(N)") == {"spans": [(2, 5)], "code": "N"}
    assert ci("소계 ( A + B + C )")["expr"] == "A+B+C" and ci("금액（C＝A×10%）")["expr"] == "A*10%" and ci("금액（C＝A×10%）")["code"] == "C"
    for s in ("(연구시설‧장비비 중 통합관리비(현금))", "기관(R&D)", "항목(1)", "비고(SW)", "단위(%)", "안 닫힌 (A+B", ""):
        assert ci(s) == {"spans": []}, s
    assert HC.core("총 인건비1)(E1=A+B+C+D)") == "총 인건비" and HC.core("직접비 소계 (K=E1+F+G+H+I+S+T)") == "직접비 소계" and HC.core("간접비 비율4)(L/(N+O+C))") == "간접비 비율"
    hb = HC.header_basis
    assert hb("총 인건비1)(E1=A+B+C+D)")["kind"] == "total" and hb("연구수당 비율3)(I/E2)").get("pctUnit") is True and hb("연구개발비 총액(M=K+L)")["code"] == "M"
    assert HC.parse_num("1,000 (E1)")["num"] == 1000 and HC.parse_num("20% (I/E2)") == {"num": 20.0, "dec": 0, "pct": True}
    ev = HC._eval_expr
    assert ev("L/(N+O)", {"L": 10, "N": 3, "O": 2}) == 2 and ev("A+B*C", {"A": 1, "B": 2, "C": 3}) == 7 and ev("K-E1-T", {"K": 10, "E1": 3, "T": 2}) == 5
    assert ev("A*10%", {"A": 50}) == pytest.approx(5) and ev("A/B", {"A": 1, "B": 0}) is None and ev("A+", {"A": 1}) is None and ev("A+Z", {"A": 1}) is None


def plan_tab(blank=False, bad=False):
    """연구개발기관별 사용계획 총괄표 꼴(줄임) — 비목 | 항목(1x2) | 1차년도 | 2차년도 | 합계 ; 직접비(7x1) › 인건비(A)(2x1) › 현금(N)·현물 · 재료비(B) · 총 인건비1)(E1=A+B) ·
    수당(I) · 수당 비율2)(I/E1) · 직접비 소계 (K=E1+I) ; 간접비(L) ; 간접비 비율3)(L/(N+B)) ; 총액(M=K+L). blank = 빈 양식(합계 줄·합계 열은 음영 빈 칸)."""
    t = Tab("t9")
    t.head(0, 0, "비목")
    t.head(0, 1, "항목", cs=2)
    for i, name in enumerate(["1차년도", "2차년도", "합계"]):
        t.head(0, 3 + i, name)
    t.head(1, 0, "직접비", rs=7)
    t.head(1, 1, "인건비(A)", rs=2)
    t.head(1, 2, "현금(N)")
    t.head(2, 2, "현물")
    for r, name in ((3, "재료비(B)"), (4, "총 인건비1)(E1=A+B)"), (5, "수당(I)"), (6, "수당 비율2)(I/E1)"), (7, "직접비 소계 (K=E1+I)")):
        t.head(r, 1, name, cs=2)
    for r, name in ((8, "간접비(L)"), (9, "간접비 비율3)(L/(N+B))"), (10, "총액(M=K+L)")):
        t.head(r, 0, name, cs=3)
    vals = {1: ["10", "20", "30"], 2: ["5", "5", "10"], 3: ["3", "4", "7"], 4: ["18", "29", "47"], 5: ["9", "2.9", "11.9"], 6: ["50%", "10%", "25.3%"],
            7: ["27", "31.9", "58.9"], 8: ["3", "3.1", "6.1"], 9: ["23.1%", "12.9%", "16.5%"], 10: ["30", "36" if bad else "35", "65"]}
    for r, row in vals.items():
        for i, v in enumerate(row):
            if blank:
                t.cell(r, 3 + i, "", fill=GREY if (r in (4, 7, 10) or i == 2) else None)
            else:
                t.num(r, 3 + i, v)
    return t


def test_code_definitions_parent_codes_and_nested_ratio():
    tb = build(plan_tab(), before="(단위: 천원)")["tables"][0]
    s = tb["subtables"]
    assert len(s) == 1 and s[0]["kind"] == "matrix" and s[0]["headerRows"] == 1 and s[0]["headerCols"] == 3 and "코드 식" in s[0]["calc"]["why"]
    heads = {c["text"]: c for c in tb["cells"] if c["role"] in ("colhead", "rowhead", "corner")}
    assert heads["총 인건비1)(E1=A+B)"]["code"] == "E1" and heads["총 인건비1)(E1=A+B)"]["expr"] == "A+B" and heads["총액(M=K+L)"]["expr"] == "K+L"
    assert heads["간접비 비율3)(L/(N+B))"]["expr"] == "L/(N+B)" and heads["인건비(A)"]["code"] == "A"
    # 부모 헤더 코드 A = 아래 잎 칸 전부(현금 + 현물 — SUM 범위) · 잎 코드 B = 칸 하나
    e1 = fx(tb, 4, 3)["row"]
    assert e1["kind"] == "expr" and e1["formula"] == "=SUM(D2:D3)+D4" and e1["expected"] == 18 and e1["status"] == "ok" and e1["excel"] is True
    assert len(e1["operands"]) == 3 and "E1=A+B" in e1["note"]
    # 정의한 코드를 다른 식이 쓴다 — K = E1 + I · M = K + L
    assert fx(tb, 7, 3)["row"]["formula"] == "=D5+D6" and fx(tb, 7, 4)["row"]["expected"] == pytest.approx(31.9) and fx(tb, 7, 4)["row"]["status"] == "ok"
    m = fx(tb, 10, 3)["row"]
    assert m["formula"] == "=D8+D9" and m["expected"] == 30 and m["status"] == "ok" and "M=K+L" in m["note"]
    # 비율 식 — 헤더가 「비율」 이라 백분율(×100) · 안쪽 괄호
    assert fx(tb, 6, 3)["row"]["formula"] == "=(D6/D5)*100" and fx(tb, 6, 3)["row"]["expected"] == 50 and fx(tb, 6, 3)["row"]["status"] == "ok"
    r = fx(tb, 9, 3)["row"]
    assert r["formula"] == "=(D9/(D2+D4))*100" and r["expected"] == pytest.approx(23.0769, abs=1e-3) and r["status"] == "ok"
    # 「합계」 열: 값 행은 가로 합 · 코드 식 행은 두 수식(엑셀엔 코드 식) · 비율 행은 코드 식만(비율의 합이 아니라 합의 비율)
    assert set(fx(tb, 1, 5)) == {"col"} and fx(tb, 1, 5)["col"]["formula"] == "=SUM(D2:E2)"
    both = fx(tb, 10, 5)
    assert set(both) == {"row", "col"} and both["row"]["formula"] == "=F8+F9" and both["row"]["excel"] and both["col"]["formula"] == "=SUM(D11:E11)" and not both["col"]["excel"]
    ratio = fx(tb, 6, 5)
    assert set(ratio) == {"row"} and ratio["row"]["formula"] == "=(F6/F5)*100" and ratio["row"]["expected"] == pytest.approx(25.319, abs=1e-3) and ratio["row"]["status"] == "ok"
    assert tb["calc"]["mismatch"] == 0 and tb["calc"]["ok"] == tb["calc"]["formulas"] == len(tb["formulas"]) == 23  # 코드 식 5행 × 3열 + 합계 열 가로 합 8행
    # 값이 틀리면 불일치
    x = fx(build(plan_tab(bad=True))["tables"][0], 10, 4)["row"]
    assert x["status"] == "mismatch" and x["expected"] == 35 and x["actual"] == 36 and x["diff"] == 1
    # 빈 양식 — 합계 줄·합계 열의 음영 빈 칸도 필드라 같은 수식이 나오고 모두 미검증(빈 칸). 빈 비율 칸도 ×100
    blank = build(plan_tab(blank=True))["tables"][0]
    assert len(blank["subtables"]) == 1 and blank["subtables"][0]["headerCols"] == 3 and all(c["role"] == "field" for c in blank["cells"] if c["row"] >= 1 and c["col"] >= 3)
    assert [f["formula"] for f in blank["formulas"]] == [f["formula"] for f in tb["formulas"]] and all(f["status"] == "blank" for f in blank["formulas"])
    assert fx(blank, 6, 3)["row"]["formula"] == "=(D6/D5)*100" and fx(blank, 10, 5)["row"]["formula"] == "=F8+F9"


def test_unresolved_code_expr_makes_no_guess():
    """식의 코드를 못 찾으면 수식을 만들지 않는다 — 「총 인건비(E1=A+Z)」 를 「총 …비」 합계 규칙(형제 전부의 합)으로 어림하지 않는다. 식이 없는 「총 …비」 는 예전대로 합."""
    t = Tab("t10")
    t.head(0, 0, "항목")
    t.head(0, 1, "금액")
    for r, (a, b) in enumerate([("인건비(A)", "10"), ("재료비(B)", "5"), ("총 인건비(E1=A+Z)", "10"), ("총 연구개발비", "15")], start=1):
        t.cell(r, 0, a)
        t.num(r, 1, b)
    tb = build(t)["tables"][0]
    assert fx(tb, 3, 1) == {} and cell_at(tb, 3, 0)["expr"] == "A+Z"
    assert fx(tb, 4, 1)["row"]["kind"] == "sum"


def test_rnd_plan_table_code_formulas(rnd):
    """실물 — 「연구개발기관별 사용계획 총괄표」(26×11): 스크립트 초안만으로 띠 하나 · 합계 줄/열이 필드 · 표에 적힌 코드 식대로 수식."""
    out = HT.build(rnd, use_llm=False, ask=_no_llm)
    plans = [x for x in out["tables"] if any("연구개발비 총액(M=K+L)" in c["text"] for c in x["cells"])]
    t = next(x for x in plans if x["rows"] == 26)
    assert [(tuple(s["rows"]), s["kind"], s["headerRows"], s["headerCols"]) for s in t["subtables"]] == [((0, 26), "matrix", 2, 4)]
    f = {x["ref"]: x["formula"] for x in t["formulas"] if x["excel"]}
    assert f["E26"] == "=E23+E24" and f["K26"] == "=K23+K24"                                  # 연구개발비 총액(M=K+L)
    assert f["E10"] == "=SUM(E3:E4)+E5+E6+SUM(E8:E9)" and f["E11"] == "=SUM(E3:E4)+E5+SUM(E8:E9)"  # 총 인건비(E1=A+B+C+D) · 수정인건비(E2=A+B+D)
    assert f["E23"] == "=E10+SUM(E12:E13)+SUM(E15:E16)+SUM(E17:E18)+E19+E21+E22"                 # 직접비 소계(K=E1+F+G+H+I+S+T) — 「…중 통합관리비」 행(14)은 안 듦
    assert f["E20"] == "=(E19/E11)*100" and f["K20"] == "=(K19/K11)*100"                          # 연구수당 비율(I/E2)
    assert f["E25"] == "=(E24/(E3+E5+E6+SUM(E8:E9)+E12+E15+E17+E19+E21))*100"                    # 간접비 비율(L/(N+O+C+D+P+Q+R+I+S))
    assert f["E7"] == "=SUM(E3:E4)+E5+E6" and f["K3"] == "=SUM(E3:J3)" and f["J26"] == "=J23+J24"
    assert len(f) == 66 and all(x["status"] == "blank" for x in t["formulas"])
    # 같은 꼴의 다른 표(22행 — 헤더 열이 5칸 폭, 총액 행의 이름 칸이 헤더 열 한도(4)보다 넓음): 총액 행이 같은 띠 · 뒤에 정의된 코드(M)를 앞 행이 씀
    u = next(x for x in plans if x["rows"] == 22)
    g = {x["ref"]: x["formula"] for x in u["formulas"] if x["excel"]}
    assert len(u["subtables"]) == 1 and g["F22"] == "=F20+F21" and g["F10"] == "=(F9/F22)*100" and g["F9"] == "=SUM(F4:F5)+F6+F7+F8"
    # 참여연구자 인건비 현황표 — 「총액(G=D+E+F)」 = 소계(D) + 소계(E) + 소계(F)
    p = next(x for x in out["tables"] if any("총액(G=D+E+F)" in c["text"] for c in x["cells"]))
    assert {x["ref"]: x["formula"] for x in p["formulas"] if x["excel"]}["I12"] == "=I6+I9+I11"


def test_abbreviation_is_not_an_expr_and_ratio_expr_definition():
    """코드가 하나도 정의되지 않은 괄호 글(「(M/M)」)은 식이 아니라 약어 — 합계 낱말 규칙 그대로. 나누기 식 = 코드로 나누는 식(상수로 나누는 「(A/12)×B×C」 는 금액 식).
    못 푸는 나누기 식 줄에는 다른 축의 「비율의 합」 도 붙이지 않는다."""
    assert HC._ratio_expr("I/E2") and HC._ratio_expr("L/(N+O)") and HC._ratio_expr("A/B*100") and HC._ratio_expr("100*(A/(B+C))")
    assert not HC._ratio_expr("(A/12)*B*C") and not HC._ratio_expr("(A+B)/2") and not HC._ratio_expr("A+B") and not HC._ratio_expr("") and not HC._ratio_expr(None)
    t = Tab("t11")
    t.head(0, 0, "항목")
    t.head(0, 1, "투입(M/M)")
    for r, (a, b) in enumerate([("책임연구원", "3"), ("연구원", "5"), ("소계(M/M)", "8")], start=1):
        t.cell(r, 0, a)
        t.num(r, 1, b)
    tb = build(t)["tables"][0]
    assert "expr" not in cell_at(tb, 3, 0) and "expr" not in cell_at(tb, 0, 1) and cell_at(tb, 3, 0)["basis"] == ["total"]
    assert fx(tb, 3, 1)["row"]["formula"] == "=SUM(B2:B3)" and fx(tb, 3, 1)["row"]["status"] == "ok"
    r = Tab("t12")
    for i, name in enumerate(["항목", "1차년도", "2차년도", "합계"]):
        r.head(0, i, name)
    r.cell(1, 0, "금액(A)")
    r.cell(2, 0, "비율(A/Z)")
    for i, (a, b) in enumerate([("10", "50%"), ("20", "40%"), ("30", "90%")]):
        r.num(1, 1 + i, a)
        r.num(2, 1 + i, b)
    tb2 = build(r)["tables"][0]
    assert cell_at(tb2, 2, 0)["expr"] == "A/Z"  # A 는 정의돼 있어 식으로 남음 — Z 를 못 찾아 수식 없음
    assert fx(tb2, 1, 3)["col"]["formula"] == "=SUM(B2:C2)" and fx(tb2, 2, 3) == {} and fx(tb2, 2, 1) == {}
