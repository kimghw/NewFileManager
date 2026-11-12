"""표 엑셀화(spec_헤딩_추출 ② §14) — 지금 문서의 표·범위만 수식 판정(3단계 없이) · 「총 …비」 합계 · 부제가 낀 꼬리 · 범위 자르기와 표 전체 맥락 대체 ·
숫자 칸 · 수식 주소 옮기기 · 격자 → .xlsx · API(400/404·hwpx 만)."""
import copy
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_calc as HC
from app import heading_guides as G
from app import heading_rules as R
from app import server
from app import table_excel as TX
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


@pytest.fixture(scope="module")
def rnd_doc():
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    return d


def _cover(doc):
    """표지 표(「총 연구개발비」 가 든 표) id."""
    for b in doc.blocks():
        if b.get("type") == "table" and any("총 연구개발비" in (p.get("text") or "") for c in b["cells"] for p in c.get("blocks") or []):
            return b["id"]
    raise AssertionError("표지 표 없음")


def _by_ref(out):
    return {f["ref"]: f for f in out["formulas"] if f.get("excel")}


# ---- 판정 ----------------------------------------------------------------------------------------------------

def test_header_basis_grand_total():
    for t in ("총 연구개발비", "총사업비", "총 매출액", "총 인원", "총 정부지원금"):
        assert HC.header_basis(t)["kind"] == "total", t
    for t in ("총괄연구개발과제명", "총괄 연구개발비", "총 연구개발기간", "총장"):
        assert HC.header_basis(t)["kind"] != "total", t


def test_judge_cover_table_without_stage3(rnd_doc):
    tid = _cover(rnd_doc)
    out = TX.judge(rnd_doc, tid, store=copy.deepcopy(EMPTY))
    assert out["scope"] == "table" and out["range"] is None and out["unit"] == "천원"
    f = _by_ref(out)
    # 총 현금 = 정부지원 현금 + 기관부담 현금 + 그 외(지방자치단체 등 › 현금 — 부제가 낀 꼬리) · 총 현물 = 기관부담 현물 + 그 외 현물
    assert f["T32"]["formula"] == "=E32+F32+N32" and f["X32"]["formula"] == "=H32+Q32"
    assert f["AB32"]["formula"] == "=SUM(T32:X32)"
    assert f["E37"]["formula"] == "=SUM(E32:E36)" and f["AB37"]["formula"] == "=SUM(AB32:AB36)"
    assert len(f) >= 20 and out["counts"]["excel"] == len(f)
    assert all(x["status"] == "blank" for x in out["formulas"])  # 빈 양식 — 자리표시는 값이 아님
    assert f["T32"]["refs"] == ["E32", "F32", "N32"]
    cells = {HC.ref(c): c for c in out["cells"]}
    assert cells["E32"]["input"] and cells["N32"]["input"] and cells["H36"]["input"]  # 피연산자(빈 칸도)·자리표시
    assert not cells["T32"].get("input") and not cells["AB37"].get("input")  # 수식 칸은 숫자 칸이 아님
    assert cells["E32"]["role"] == "field" and cells["T31"]["role"] == "colhead"
    assert cells["E32"]["paras"]  # 화면이 문서 문단과 잇는다


def test_judge_range_crop_and_fallback(rnd_doc):
    tid = _cover(rnd_doc)
    whole = TX.judge(rnd_doc, tid, store=copy.deepcopy(EMPTY))
    # 연구개발비 띠만(헤더 포함) — 범위만으로 판정, 주소는 표 기준
    part = TX.judge(rnd_doc, tid, {"r0": 28, "c0": 0, "r1": 36, "c1": 29}, store=copy.deepcopy(EMPTY))
    assert part["scope"] == "range" and part["range"] == {"r0": 28, "c0": 0, "r1": 36, "c1": 29}
    assert _by_ref(part)["T32"]["formula"] == "=E32+F32+N32" and set(_by_ref(part)) == set(_by_ref(whole))
    assert all(28 <= c["row"] <= 36 for c in part["cells"])
    # 값 칸만(헤더 없이) — 범위로는 수식이 없어 표 전체 맥락으로, 범위 안 칸의 수식만
    vals = TX.judge(rnd_doc, tid, {"r0": 31, "c0": 4, "r1": 36, "c1": 29}, store=copy.deepcopy(EMPTY))
    assert vals["scope"] == "table" and vals["formulas"]
    assert all(31 <= int("".join(ch for ch in f["ref"] if ch.isdigit())) - 1 <= 36 for f in vals["formulas"])
    assert _by_ref(vals)["T32"]["formula"] == "=E32+F32+N32"
    # 표 전체와 같은 범위 = 범위 없음
    full = TX.judge(rnd_doc, tid, {"r0": 0, "c0": 0, "r1": whole["rows"] - 1, "c1": whole["cols"] - 1}, store=copy.deepcopy(EMPTY))
    assert full["range"] is None and full["scope"] == "table"


def test_judge_not_a_table(rnd_doc):
    assert TX.judge(rnd_doc, "p1", store=copy.deepcopy(EMPTY)) is None


def test_shift_formula():
    assert TX.shift_formula("=SUM(T32:X32)+$B$29", -28, -1) == "=SUM(S4:W4)+$A$1"
    assert TX.shift_formula("=E32/K32*100", 0, 0) == "=E32/K32*100"
    assert TX.shift_formula("=A1+B2", -1, 0) is None  # 범위 밖


# ---- 격자 → .xlsx ----------------------------------------------------------------------------------------------

def test_grid_workbook_range_shift_and_marks():
    from openpyxl import load_workbook
    grid = {"table": "t1", "rows": 40, "cols": 30, "unit": "천원", "range": {"r0": 30, "c0": 4, "r1": 32, "c1": 6},
            "cells": [{"ref": "E31", "row": 30, "col": 4, "rs": 1, "cs": 1, "role": "colhead", "value": "현금"},
                      {"ref": "E32", "row": 31, "col": 4, "rs": 1, "cs": 1, "role": "field", "value": "1,200", "num": 1200, "grouped": True, "input": True},
                      {"ref": "F32", "row": 31, "col": 5, "rs": 1, "cs": 1, "role": "field", "value": "300", "num": 300, "input": True, "orig": True, "origText": "0,000"},
                      {"ref": "G32", "row": 31, "col": 6, "rs": 1, "cs": 1, "role": "field", "formula": "=E32+F32", "calc": 1500, "status": "bad", "doc": "1,400"},
                      {"ref": "E33", "row": 32, "col": 4, "rs": 1, "cs": 2, "role": "rowhead", "value": "합계"},
                      {"ref": "G33", "row": 32, "col": 6, "rs": 1, "cs": 1, "role": "field", "formula": "=A1+E32", "calc": 9, "status": "ok", "doc": "9"}]}
    wb = load_workbook(io.BytesIO(TX.grid_workbook(grid, "문서.hwpx")))
    ws = wb["표"]
    assert ws["A1"].value == "현금" and ws["A2"].value == 1200 and ws["A2"].number_format == "#,##0"
    assert ws["C2"].value == "=A2+B2" and ws["C2"].fill.fgColor.rgb.endswith("F8CBAD") and "1,400" in ws["C2"].comment.text
    assert ws["C3"].value == 9 and "범위 밖" in ws["C3"].comment.text  # 범위 밖을 가리키는 수식은 값으로
    assert ws["A2"].fill.fgColor.rgb.endswith("FFF2CC") and "원문: 0,000" in ws["B2"].comment.text
    assert "A3:B3" in [str(r) for r in ws.merged_cells.ranges]
    assert wb["수식"]["A2"].value == "C2" and wb["수식"]["B2"].value == "=A2+B2"
    assert wb.sheetnames == ["표", "수식", "정보"]


# ---- API ---------------------------------------------------------------------------------------------------

def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_api_excel_judge_and_xlsx():
    server.DOCS.clear()
    c = TestClient(server.app)
    try:
        d = _upload(c, RND)
        tid = _cover(server.DOCS[d].doc)
        r = c.post(f"/api/docs/{d}/tables/{tid}/excel", json={})
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["table"] == tid and v["rev"] == server.DOCS[d].rev and any(f["ref"] == "T32" and f["formula"] == "=E32+F32+N32" for f in v["formulas"])
        r2 = c.post(f"/api/docs/{d}/tables/{tid}/excel", json={"range": {"r0": 28, "c0": 0, "r1": 36, "c1": 29}}).json()
        assert r2["scope"] == "range" and r2["range"]["r0"] == 28
        assert c.post(f"/api/docs/{d}/tables/{tid}/excel", json={"range": {"r0": 3, "c0": 0, "r1": 1, "c1": 2}}).status_code == 400
        assert c.post(f"/api/docs/{d}/tables/{tid}/excel", json={"range": {"r0": "x"}}).status_code == 400
        assert c.post(f"/api/docs/{d}/tables/t99999/excel", json={}).status_code == 404
        assert c.post(f"/api/docs/{d}/tables/p1/excel", json={}).status_code == 404
        x = c.post(f"/api/docs/{d}/tables/{tid}/excel/xlsx", json={"rows": 2, "cols": 2, "range": {"r0": 28, "c0": 0, "r1": 36, "c1": 29},
                                                                   "cells": [{"ref": "A29", "row": 28, "col": 0, "rs": 1, "cs": 1, "value": "연구개발비"}]})
        assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert "_t" in x.headers["content-disposition"] and "A29-AD37" in x.headers["content-disposition"]
        assert c.post(f"/api/docs/{d}/tables/{tid}/excel/xlsx", json={"cells": "x"}).status_code == 400
        assert c.post(f"/api/docs/{d}/tables/{tid}/excel/xlsx", json={"cells": [{"row": "a"}]}).status_code == 400
    finally:
        server.DOCS.clear()


def test_judge_plan_table_code_definitions(rnd_doc):
    """「연구개발기관별 사용계획 총괄표」(26×11 — 「연구개발비 총액(M=K+L)」) — 3단계·LLM 없이 표에 적힌 코드 식대로 수식 자리, 참조 칸(refs), 숫자 칸."""
    tid = next(b["id"] for b in _tables(rnd_doc.blocks()) if b["nRows"] == 26 and any("연구개발비 총액(M=K+L)" in (p.get("text") or "") for c in b["cells"] for p in c.get("blocks") or []))
    out = TX.judge(rnd_doc, tid, store=copy.deepcopy(EMPTY))
    assert [(s["rows"], s["kind"], s["headerRows"], s["headerCols"]) for s in out["subtables"]] == [([0, 26], "matrix", 2, 4)]
    f = _by_ref(out)
    assert f["E26"]["formula"] == "=E23+E24" and f["E26"]["refs"] == ["E23", "E24"] and f["E26"]["kind"] == "expr" and "M=K+L" in f["E26"]["note"]
    assert f["E10"]["formula"] == "=SUM(E3:E4)+E5+E6+SUM(E8:E9)" and f["E10"]["refs"] == ["E3", "E4", "E5", "E6", "E8", "E9"]
    assert f["E20"]["formula"] == "=(E19/E11)*100" and f["K20"]["formula"] == "=(K19/K11)*100" and f["K3"]["formula"] == "=SUM(E3:J3)"
    assert f["E25"]["formula"] == "=(E24/(E3+E5+E6+SUM(E8:E9)+E12+E15+E17+E19+E21))*100"
    assert out["counts"]["excel"] == len(f) == 66
    cells = {HC.ref(c): c for c in out["cells"]}
    assert cells["E26"]["role"] == "field" and not cells["E26"].get("input") and cells["K5"]["role"] == "field"  # 음영 값 칸(합계 줄·열)은 필드 — 수식 칸은 숫자 칸이 아님
    assert cells["E3"]["input"] and cells["E24"]["input"] and cells["E14"]["role"] == "field"  # 피연산자 = 숫자 칸 · 「…중 통합관리비」 행은 어느 식에도 안 듦
    # 범위(총액 행만 — 헤더 없이)로는 수식이 없어 표 전체 맥락으로, 범위 안 칸의 수식만
    part = TX.judge(rnd_doc, tid, {"r0": 25, "c0": 4, "r1": 25, "c1": 10}, store=copy.deepcopy(EMPTY))
    assert part["scope"] == "table" and _by_ref(part)["E26"]["formula"] == "=E23+E24" and len(_by_ref(part)) == 7


def _tables(blocks):
    """문서의 표 블록 전부(칸 안 표 포함)."""
    for b in blocks:
        if b.get("type") == "table":
            yield b
        for c in b.get("cells") or []:
            yield from _tables(c.get("blocks") or [])
