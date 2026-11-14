"""서식 추출 후보(spec_일반편집 ② §5) — 문서의 후보(스크립트) · 이름 붙이기(가짜 LLM) · 파일에서(hwpx·docx·PyMuPDF 로 지은 pdf) · 토큰 · 저장할 것(style_carrier 가 있을 때)."""
import json
from pathlib import Path

import fitz
import pytest

from app import style_extract as X
from app import table_make
from app.hwpx_doc import HwpxDoc

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "app" / "style_base.hwpx"
SURVEY, DOCX = ROOT / "samples" / "기술수요조사서.hwpx", ROOT / "samples" / "기술수요조사서.docx"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", "off")   # 헤딩 규칙 저장소 — 사용자 것(%LOCALAPPDATA%)을 읽지 않는다
    X._HELD.clear()
    yield
    X._HELD.clear()


def _base():
    doc = HwpxDoc(BASE.read_bytes())
    bl = doc.blocks()
    return doc, bl[0]["id"], next(b["id"] for b in bl if b["type"] == "table")


def _fill_row(doc, tid, row, fill):
    for c in doc.table_block(tid)["cells"]:
        if c["row"] == row:
            doc.apply_cell_format([c["id"]], {"fill": fill}, ["fill"])


# ---- 문서의 후보 ---------------------------------------------------------------------------------------------------

def test_table_candidates_group_tables_of_the_same_look():
    doc, first, tid = _base()
    got = X.candidates(doc)
    assert got["texts"] == [] and len(got["tables"]) == 1                    # 그래프가 없으면 글 후보는 내지 않는다
    c = got["tables"][0]
    assert (c["key"], c["table"], c["same"], c["count"], c["rows"], c["cols"]) == (tid, tid, [tid], 1, 2, 2)
    assert c["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 0} and c["sample"] == "" and c["lines"] == {"outer": "SOLID 0.12", "inner": "SOLID 0.12"}
    assert set(c["looks"]) == {"head", "stub", "body", "foot"} and c["looks"]["stub"] is None and c["looks"]["foot"] is None
    assert c["looks"]["head"] == {"fill": None, "font": c["looks"]["body"]["font"], "sizePt": 10.0, "bold": False, "align": "left"}
    json.dumps(got, ensure_ascii=False)
    # 같은 서식의 표는 한 후보(대표 = 문서 순 첫 표) · 서식이 다르면 따로 — 쓰인 수 많은 차례
    made = [doc.table_make(first, tid, table_make.normalize({"rows": [["가", "나"], ["다", "라"]]}), {"headerRows": 0, "headerCols": 0, "footRows": 0})["table"] for _ in range(3)]
    _fill_row(doc, made[0], 0, "#D9E2F3")
    order = [b["id"] for b in doc.blocks() if b["type"] == "table"]
    cands = X.candidates(doc)["tables"]
    assert [c["count"] for c in cands] == [3, 1] and cands[0]["same"] == [i for i in order if i != made[0]] and cands[0]["key"] == cands[0]["table"] == cands[0]["same"][0]
    shaded = cands[1]
    assert shaded["table"] == made[0] and shaded["same"] == [made[0]] and shaded["looks"]["head"]["fill"] == "#D9E2F3" and shaded["looks"]["body"]["fill"] is None
    assert shaded["sample"] == "가" and shaded["headTexts"] == ["가", "나"] and shaded["stubTexts"] == ["가", "다"]


def test_table_candidates_skip_boxes_and_guide_tables():
    doc, first, tid = _base()
    guide = doc.table_make(first, tid, table_make.normalize({"rows": [["< 작성 요령 >", ""], ["o 이렇게 씁니다", ""]]}), {"headerRows": 0, "headerCols": 0, "footRows": 0})["table"]
    doc.merge_cells(tid, 0, 0, 1, 1)                                         # 1칸 표 = 글상자
    assert len(doc.table_block(tid)["cells"]) == 1 and doc.table_block(guide) is not None
    assert X.candidates(doc)["tables"] == []
    assert X.TABLES_MAX == 60
    found = [(f"t{n}", {"rows": 2, "cols": 2}, f"sig{n % 70}", None) for n in range(140)]   # 지문 70가지 × 2 → 60개까지
    out = X.group_tables(found)
    assert len(out) == 60 and all(c["count"] == 2 for c in out) and out[0]["key"] == "t0" and out[0]["same"] == ["t0", "t70"]


def test_text_candidates_follow_the_graph_but_not_blindly():
    doc, first, _ = _base()
    a = doc.insert_line(first, "1. 연구개발의 필요성")
    b = doc.insert_line(a, " □ 국내외 현황 " + "가" * 80)
    c = doc.insert_line(b, "  - 세부")
    graph = {"version": 2, "templates": [
        {"id": 1, "no": 1, "name": "body:N.›□", "displayName": "", "chain": ["N.", "□", "-"],
         "slots": [{"level": 2, "letter": "□", "count": 3, "format": "S2", "rep": b}, {"level": 1, "letter": "N.", "count": 2, "format": "S1", "rep": a},
                   {"level": 3, "letter": "-", "count": 1, "format": None, "rep": c},          # 대표 서식이 없는 슬롯
                   {"level": 4, "letter": "·", "count": 1, "format": "S9", "rep": "p999999"}]},  # 문서에 없는 문단
        {"id": 2, "no": 2, "name": "cell:[N]", "displayName": "표 안 번호", "chain": ["[N]"], "slots": []}]}
    texts = X.candidates(doc, graph)["texts"]
    assert len(texts) == 1 and texts[0]["key"] == "tpl1" and texts[0]["template"] == {"id": 1, "no": 1, "name": "body:N.›□", "chain": ["N.", "□", "-"]}
    items = texts[0]["items"]
    assert [(i["para"], i["level"], i["letter"]) for i in items] == [(a, 1, "N."), (b, 2, "□")]
    assert items[0]["sample"] == "1. 연구개발의 필요성" and len(items[1]["sample"]) == 60 and items[1]["sample"].endswith("…")
    assert items[0]["format"]["sizePt"] == doc.get_format(a)["summary"]["sizePt"] and "font" in items[0]["format"]
    doc.delete_blocks(b, b)                                                  # 대표 문단이 지워짐 — 그 슬롯은 뺀다
    assert [i["para"] for i in X.candidates(doc, graph)["texts"][0]["items"]] == [a]
    doc.delete_blocks(a, a)
    assert X.candidates(doc, graph)["texts"] == [] and X.candidates(doc, {"templates": None})["texts"] == []


# ---- 이름 붙이기 ---------------------------------------------------------------------------------------------------

CANDS = {"tables": [{"key": "t1", "table": "t1", "same": ["t1", "t5"], "count": 2, "rows": 4, "cols": 3, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "구분",
                     "looks": {"head": {"fill": "#D9E2F3", "font": "맑은 고딕", "sizePt": 10.0, "bold": True, "align": "center", "extra": 1}, "stub": None, "body": None, "foot": None},
                     "lines": {"outer": "SOLID 0.4", "inner": "SOLID 0.12"}, "headTexts": ["구분", "1차", "2차"], "stubTexts": ["구분", "인건비", "재료비", "합계"]},
                    {"key": "t2", "table": "t2", "same": ["t2"], "count": 1, "rows": 2, "cols": 2, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "서명", "looks": {}}],
         "texts": [{"key": "tpl1", "template": {"id": 1, "no": 1, "name": "body:N.", "chain": ["N.", "□"]},
                    "items": [{"para": "p3", "level": 1, "letter": "N.", "sample": "1. 개요", "format": {"font": "바탕", "sizePt": 12.0, "bold": True, "align": "left"}}]}]}


def _strict(schema):
    """구조화 출력 스키마 — 객체마다 additionalProperties false · 모든 키 required."""
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False and schema["required"] == list(schema["properties"])
        for v in schema["properties"].values():
            _strict(v)
    elif schema.get("type") == "array":
        _strict(schema["items"])


def test_name_cleans_the_answer():
    seen = {}

    def call(schema, content, what, *, timeout=None, effort=None):
        seen.update(schema=schema, content=content, what=what, timeout=timeout, effort=effort)
        return {"data": {"tables": [{"key": "t1", "name": "  예산 총괄표 —\n 머리 1행·합계행 ", "keep": True, "bandsSure": True, "headerRows": 9, "headerCols": 1, "footRows": 9},
                                    {"key": "t2", "name": "", "keep": False, "bandsSure": False, "headerRows": 1, "headerCols": 0, "footRows": 0},      # 이름 없는 답
                                    {"key": "zz", "name": "없는 표", "keep": True, "bandsSure": False, "headerRows": 0, "headerCols": 0, "footRows": 0}],  # 모르는 key
                         "texts": [{"key": "tpl1", "name": "개요 1. › □ — 본문 2레벨", "keep": False}, {"key": "nope", "name": "x", "keep": True}], "note": "요약"},
                "backend": "api", "model": "m", "effort": effort, "ms": 12, "costUsd": None, "error": None}
    out = X.name(CANDS, call=call)
    assert out["tables"] == {"t1": {"name": "예산 총괄표 — 머리 1행·합계행", "keep": True, "bands": {"headerRows": 4, "headerCols": 1, "footRows": 0}, "bandsChanged": True}}
    assert out["texts"] == {"tpl1": {"name": "개요 1. › □ — 본문 2레벨", "keep": False}} and out["note"] == "요약"
    assert out["call"] == {"backend": "api", "model": "m", "effort": "low", "ms": 12, "costUsd": None, "error": None} and out["response"]["note"] == "요약"
    assert (seen["what"], seen["timeout"], seen["effort"]) == ("style-name", 120.0, "low") and seen["schema"] is X.SCHEMA and out["prompt"] == seen["content"]
    _strict(X.SCHEMA)
    assert seen["content"].startswith(X.CONTRACT) and "## 자료(JSON)" in seen["content"]
    data = json.loads(seen["content"].split("## 자료(JSON)\n", 1)[1])            # 후보의 요약만 — 표 id 목록·서식 사전 전체는 안 싣는다
    assert data["tables"][0] == {"key": "t1", "rows": 4, "cols": 3, "count": 2, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "head": ["구분", "1차", "2차"],
                                 "stub": ["구분", "인건비", "재료비", "합계"], "lines": {"outer": "SOLID 0.4", "inner": "SOLID 0.12"},
                                 "looks": {"head": {"fill": "#D9E2F3", "font": "맑은 고딕", "sizePt": 10.0, "bold": True, "align": "center"}, "stub": None, "body": None, "foot": None}}
    assert data["tables"][1]["head"] == ["서명"] and data["texts"] == [{"key": "tpl1", "chain": ["N.", "□"], "items": [{"level": 1, "letter": "N.", "sample": "1. 개요", "font": "바탕", "sizePt": 12.0, "bold": True}]}]
    # 확신하지 않는 띠 수는 스크립트 값 그대로
    unsure = lambda *a, **k: {"data": {"tables": [{"key": "t1", "name": "가" * 80, "keep": True, "bandsSure": False, "headerRows": 3, "headerCols": 2, "footRows": 1}], "texts": [], "note": ""}}  # noqa: E731
    got = X.name(CANDS, call=unsure, effort="medium")["tables"]["t1"]
    assert got["bands"] == CANDS["tables"][0]["bands"] and got["bandsChanged"] is False and len(got["name"]) == X.NAME_MAX


def test_name_never_raises():
    off = X.name(CANDS, call=lambda *a, **k: {"data": None, "backend": None, "ms": 0, "costUsd": None, "error": "off"})
    assert off["tables"] == {} and off["texts"] == {} and off["call"]["error"] == "off" and off["response"] is None and off["prompt"]

    def boom(*a, **k):
        raise RuntimeError("끊김")
    assert "끊김" in X.name(CANDS, call=boom)["call"]["error"]
    assert X.name(CANDS, call=lambda *a, **k: {"data": {"tables": "x", "texts": [None, 3], "note": None}})["tables"] == {}   # 꼴이 틀린 답
    called = []
    empty = X.name({"tables": [], "texts": []}, call=lambda *a, **k: called.append(1))
    assert not called and empty["tables"] == {} and "후보가 없습니다" in empty["call"]["error"] and X.name(None, call=boom)["tables"] == {}


# ---- 파일에서 ------------------------------------------------------------------------------------------------------

def test_from_file_rejects_what_it_cannot_read():
    for name, data, word in (("a.txt", b"x", "hwpx · docx · pdf"), ("a.hwp", b"\xd0\xcf\x11\xe0", "hwpx 로 바꾼"), ("a.hwpx", b"", "빈 파일"), ("a.hwpx", b"not a zip", "읽지 못했습니다"),
                             ("a.docx", b"junk", "읽지 못했습니다"), ("a.pdf", b"%PDF-1.4 junk", "읽지 못했습니다"), ("", b"x", "hwpx · docx · pdf")):
        with pytest.raises(ValueError, match=word):
            X.from_file(name, data)


def test_from_file_hwpx_runs_the_script_stages():
    e = X.from_file("기술수요조사서.hwpx", SURVEY.read_bytes())
    assert e["format"] == "hwpx" and e["name"] == "기술수요조사서.hwpx" and e["losses"] == [] and isinstance(e["_doc"], HwpxDoc)
    assert e["tables"] and all(set(c) >= {"key", "table", "same", "count", "rows", "cols", "bands", "sample", "looks"} for c in e["tables"])
    assert e["_graph"]["version"] == 2 and "_calls" not in e["_graph"] and e["_graph"]["llm"]["fallback"] is True      # 스크립트만(LLM 없음)
    assert e["texts"] and all(t["template"]["chain"] and t["items"] for t in e["texts"])
    assert all(isinstance(i["level"], int) and i["format"].get("sizePt") and len(i["sample"]) <= 60 for t in e["texts"] for i in t["items"])
    pub = X.public(e)
    assert set(pub) == {"name", "format", "fidelity", "tables", "texts", "losses"} and pub["fidelity"] == "native" and json.dumps(pub, ensure_ascii=False)


def test_from_file_hwpx_keeps_tables_when_the_stages_fail(monkeypatch):
    monkeypatch.setattr(X, "script_graph", lambda *a, **k: 1 / 0)
    e = X.from_file("a.hwpx", SURVEY.read_bytes())
    assert e["tables"] and e["texts"] == [] and e["_graph"] is None and "글 서식 후보는 내지 못했습니다" in e["losses"][0]


def test_from_file_docx_tables_and_paragraph_groups():
    e = X.from_file("기술수요조사서.docx", DOCX.read_bytes())
    assert (e["format"], e["fidelity"]) == ("docx", "summary") and [(c["rows"], c["cols"]) for c in e["tables"]] == [(20, 6)] and e["tables"][0]["key"] in e["_blocks"]
    assert e["tables"][0]["looks"]["head"]["fill"] == "#DEEAF6" and e["tables"][0]["lines"]["outer"] == "SOLID 0.18"
    assert 1 <= len(e["texts"]) <= X.TEXT_GROUPS
    for t in e["texts"]:                                                     # 레벨을 지어내지 않는다
        assert t["template"] is None and t["count"] >= 1 and len(t["items"]) == 1 and t["items"][0]["level"] is None and t["items"][0]["marker"]["mode"] in ("literal", "auto", "none")
    assert [t["count"] for t in e["texts"]] == sorted((t["count"] for t in e["texts"]), reverse=True)
    json.dumps(X.public(e), ensure_ascii=False)


def test_para_groups_merge_identical_formats():
    f1, f2 = {"font": "바탕", "sizePt": 10.0, "bold": False}, {"font": "바탕", "sizePt": 14.0, "bold": True}
    para = lambda i, text, f, **kw: {"id": i, "type": "paragraph", "text": text, "format": dict(f), **kw}  # noqa: E731
    blocks = [para("p1", "1. 제목", f2), para("p2", "본문 하나", f1), {"id": "t1", "type": "table", "cells": []}, para("p3", "본문 둘", f1), para("p4", "  ", f1),
              para("p5", "□ 항목", f1), para("p6", "자동", {**f1, "sizePt": 9.0}, list={"kind": "number", "level": 1, "label": "1."})]
    got = X.para_groups(blocks)
    assert [(g["key"], g["count"]) for g in got] == [("p2", 3), ("p1", 1), ("p6", 1)]
    assert got[0]["items"][0] == {"para": "p2", "level": None, "letter": "", "sample": "본문 하나", "format": f1,
                                  "marker": {"mode": "none", "literal": "", "lead": "", "gap": "", "family": None}}
    assert got[1]["items"][0]["marker"]["mode"] == "literal" and got[1]["items"][0]["letter"] == "1." and got[2]["items"][0]["marker"]["mode"] == "auto"


# ---- pdf(잰 값으로 근사) -------------------------------------------------------------------------------------------

def _table_pdf(pages=1, text=True):
    """3×2 표 — 머리행 음영·굵게, 바깥 1pt · 안 0.36pt, 둘째 열은 오른쪽 정렬(빨강), 마지막 행 「Total」."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(60, 100, 300, 120), color=None, fill=(0.851, 0.886, 0.953))
        for y in (100, 120, 140, 160):
            page.draw_line((60, y), (300, y), color=(0, 0, 0), width=1.0 if y in (100, 160) else 0.36)
        for x in (60, 160, 300):
            page.draw_line((x, 100), (x, 160), color=(0, 0, 0), width=1.0 if x in (60, 300) else 0.36)
        if text:
            page.insert_text((64, 114), "Item", fontname="hebo", fontsize=10)
            page.insert_text((164, 114), "Amount", fontname="hebo", fontsize=10)
            for y, label in ((134, "Labor"), (154, "Total")):
                page.insert_text((64, y), label, fontname="helv", fontsize=9)
                page.insert_text((296 - fitz.get_text_length("1,200", "helv", 9), y), "1,200", fontname="helv", fontsize=9, color=(0.75, 0, 0))
    return doc.tobytes()


def test_from_file_pdf_measures_a_table_spec():
    e = X.from_file("made.pdf", _table_pdf(pages=2))
    assert (e["format"], e["fidelity"]) == ("pdf", "approx") and e["texts"] == [] and e["losses"][:2] == X.PDF_LOSSES and e["_pages"] == 2
    assert len(e["tables"]) == 1                                             # 두 쪽의 같은 서식 표 → 한 후보
    c = e["tables"][0]
    assert (c["key"], c["same"], c["count"], c["page"], c["rows"], c["cols"], c["sample"]) == ("p1t1", ["p1t1", "p2t1"], 2, 1, 3, 2, "Item")
    assert c["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 1} and c["looks"]["head"]["fill"] == "#D9E2F3" and c["looks"]["head"]["bold"] is True
    spec = e["_specs"]["p1t1"]
    assert set(e["_specs"]) == {"p1t1"} and (spec["rows"], spec["cols"]) == (3, 2) and spec["widthsMm"] == pytest.approx([35.28, 49.39], abs=0.1)
    at = {(x["row"], x["col"]): x for x in spec["cells"]}
    head, num = at[0, 0], at[1, 1]
    assert head["text"] == "Item" and head["fill"] == "#D9E2F3" and head["format"]["bold"] is True and head["format"]["sizePt"] == 10.0 and head["format"]["align"] == "left"
    assert "Helvetica" in head["format"]["font"] and head["marginsMm"] is None and head["valign"] in ("top", "center", "bottom")
    assert head["edges"]["t"] == {"type": "SOLID", "widthMm": 0.35, "color": "#000000"} and head["edges"]["b"]["widthMm"] == 0.13 and head["edges"]["l"]["widthMm"] == 0.35
    assert num["text"] == "1,200" and num["fill"] is None and num["format"] == {"font": head["format"]["font"], "sizePt": 9.0, "bold": False, "color": "#BF0000", "align": "right"}
    assert at[2, 0]["text"] == "Total" and at[2, 0]["edges"]["b"]["widthMm"] == 0.35 and all(x["rowSpan"] == x["colSpan"] == 1 for x in spec["cells"])
    json.dumps(X.public(e), ensure_ascii=False)


def test_from_file_pdf_limits(monkeypatch):
    assert (X.PDF_PAGES, X.PDF_BYTES, X.HOLD_MAX, X.HOLD_SECONDS) == (80, 40 * 2 ** 20, 4, 1800)
    with pytest.raises(ValueError, match="스캔본"):
        X.from_file("scan.pdf", _table_pdf(text=False))
    monkeypatch.setattr(X, "PDF_PAGES", 2)
    with pytest.raises(ValueError, match="쪽이 너무 많습니다 — 3쪽"):
        X.from_file("long.pdf", _table_pdf(pages=3))
    monkeypatch.setattr(X, "PDF_BYTES", 100)
    with pytest.raises(ValueError, match="너무 큽니다"):
        X.from_file("big.pdf", _table_pdf())


def test_pdf_table_spec_reads_merged_cells_and_double_lines():
    seg = lambda d, a, lo, hi, w=0.36: ({"dir": "h", "x0": lo, "y0": a, "x1": hi, "y1": a, "w": w, "color": (0, 0, 0), "dashed": False} if d == "h" else  # noqa: E731
                                        {"dir": "v", "x0": a, "y0": lo, "x1": a, "y1": hi, "w": w, "color": (0.5, 0.5, 0.5), "dashed": False})
    page = {"w": 595, "h": 841, "sheet": 0, "type3": set(), "lines": [], "rects": [{"x0": 50, "y0": 100, "x1": 250, "y1": 120, "fill": (1.0, 0.95, 0.8)}],
            "segs": [seg("h", 100, 50, 250), seg("h", 119.46, 50, 250), seg("h", 120.54, 50, 250), seg("h", 140, 50, 250), seg("v", 50, 100, 140), seg("v", 250, 100, 140), seg("v", 150, 120, 140)]}
    spec = X.pdf_table_spec(page, {"cells": [(50, 100, 250, 120), (50, 120, 150, 140), (150, 120, 250, 140), None]})
    assert (spec["rows"], spec["cols"]) == (2, 2) and [(c["row"], c["col"], c["rowSpan"], c["colSpan"]) for c in spec["cells"]] == [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)]
    top = spec["cells"][0]
    assert top["fill"] == "#FFF2CC" and top["edges"]["b"]["type"] == "DOUBLE_SLIM" and top["edges"]["t"]["type"] == "SOLID" and top["edges"]["l"]["color"] == "#808080"
    assert spec["cells"][1]["edges"]["t"]["type"] == "DOUBLE_SLIM" and spec["cells"][1]["format"] == {} and spec["cells"][1]["text"] == ""
    assert X.pdf_table_spec(page, {"cells": [(50, 100, 250, 120)]}) is None  # 칸 하나 = 상자


# ---- 토큰 ----------------------------------------------------------------------------------------------------------

def test_hold_keeps_four_for_thirty_minutes(monkeypatch):
    tokens = [X.hold({"name": f"f{n}", "_doc": object()}) for n in range(5)]
    assert len(set(tokens)) == 5 and all(len(t) >= 20 for t in tokens)
    assert X.held(tokens[0]) is None and [X.held(t)["name"] for t in tokens[1:]] == ["f1", "f2", "f3", "f4"]   # 다섯째를 잡으면 가장 오래된 것을 놓는다
    assert X.held("nope") is None and X.held(None) is None
    monkeypatch.setattr(X, "HOLD_SECONDS", -1)
    gone = X.hold({"name": "old"})
    assert X.held(gone) is None and gone not in X._HELD                      # 만료 — 끝점 410
    assert X.public({"name": "a", "format": "pdf", "_specs": {}, "_sha256": "x"}) == {"name": "a", "format": "pdf"}


# ---- 저장할 것(style_carrier) --------------------------------------------------------------------------------------

def test_build_pick_hwpx_native():
    pytest.importorskip("app.style_carrier")
    e = X.from_file("기술수요조사서.hwpx", SURVEY.read_bytes())
    cand = max(e["tables"], key=lambda c: c["rows"] * c["cols"])
    data, meta = X.build_pick(e, {"kind": "table", "key": cand["key"]})
    tabs = [b for b in HwpxDoc(data).blocks() if b["type"] == "table"]
    assert len(tabs) == 1 and (tabs[0]["nRows"], tabs[0]["nCols"]) == (meta["rows"], meta["cols"]) == (cand["rows"], cand["cols"])
    assert (meta["kind"], meta["fidelity"], meta["name"]) == ("table", "native", f"기술수요조사서 표 {cand['rows']}×{cand['cols']}") and meta["bands"] == cand["bands"]
    assert meta["source"] == {"name": "기술수요조사서.hwpx", "format": "hwpx", "work": None, "block": cand["table"], "page": None, "sha256": e["_sha256"]}
    assert isinstance(meta["losses"], list) and isinstance(meta["requirements"]["fonts"], list) and meta["preview"]["grid"]["rows"]
    _, named = X.build_pick(e, {"kind": "table", "key": cand["key"], "name": "  내  표 ", "bands": {"headerRows": 99, "headerCols": 1}})
    assert named["name"] == "내 표" and named["bands"] == {"headerRows": cand["rows"], "headerCols": 1, "footRows": 0}
    text = e["texts"][0]
    data, meta = X.build_pick(e, {"kind": "text", "key": text["key"]})
    assert (meta["kind"], meta["fidelity"]) == ("text", "native") and len(meta["items"]) == len(text["items"]) and meta["name"].startswith("기술수요조사서 글 서식")
    assert [i["level"] for i in meta["items"]] == [i["level"] for i in text["items"]] and all(i["origin"]["template"] == text["template"]["id"] for i in meta["items"])
    assert len([b for b in HwpxDoc(data).blocks() if b["type"] == "paragraph"]) == 1 + len(meta["items"])            # 첫 문단 + 견본 문단 하나씩
    for bad in ({"kind": "table", "key": "nope"}, {"kind": "text", "key": cand["key"]}, {"kind": "image", "key": cand["key"]}, None):
        with pytest.raises(ValueError, match="없는 서식 후보"):
            X.build_pick(e, bad)


def test_build_pick_keeps_no_values_of_an_unmarked_table():
    """파일에서 추출해 저장하는 길도 같다(astra 10): 머리 표시(음영·굵게)가 없는 표의 첫 행은 띠 수로는 머리행이지만 라벨이 아니다 — 이름·주민번호가 운반 문서·미리보기·기본 이름에 안 실린다."""
    pytest.importorskip("app.style_carrier")
    import io
    import zipfile
    doc, first, tid = _base()
    doc.table_make(first, tid, table_make.normalize({"rows": [["홍길동", "910101-1234567"], ["김철수", "920202-2345678"]]}), {"headerRows": 0, "headerCols": 0, "footRows": 0})
    e = X.from_file("명단.hwpx", doc.save())
    cand = next(c for c in e["tables"] if c["sample"] == "홍길동")
    assert cand["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 0}                                         # 관례대로 첫 행 = 머리행(서식의 구역)
    data, meta = X.build_pick(e, {"kind": "table", "key": cand["key"]})
    z = zipfile.ZipFile(io.BytesIO(data))
    raw = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()) + json.dumps(meta, ensure_ascii=False)
    assert meta["name"] == "명단 표 2×2" and not [s for s in ("홍길동", "김철수", "910101", "920202") if s in raw]
    assert {c["text"] for r in meta["preview"]["grid"]["rows"] for c in r["cells"]} == {"가나다", "0"}


def test_build_pick_docx_summary_and_pdf_approx():
    pytest.importorskip("app.style_carrier")
    from app import style_verify as V
    e = X.from_file("기술수요조사서.docx", DOCX.read_bytes())
    data, meta = X.build_pick(e, {"kind": "table", "key": e["tables"][0]["key"]})
    assert (meta["fidelity"], meta["rows"], meta["cols"], meta["source"]["format"]) == ("summary", 20, 6, "docx") and meta["losses"]
    assert V.expect_table(HwpxDoc(data))["cells"][0]["fill"] == "#DEEAF6"
    data, meta = X.build_pick(e, {"kind": "text", "key": e["texts"][0]["key"], "name": "별첨 줄"})
    assert (meta["kind"], meta["fidelity"], meta["name"]) == ("text", "summary", "별첨 줄") and X.DOCX_TEXT_LOSS in meta["losses"] and len(meta["items"]) == 1
    assert meta["items"][0]["level"] is None and meta["items"][0]["format"]["sizePt"] == e["texts"][0]["items"][0]["format"]["sizePt"]
    # pdf — 잰 명세로 지은 운반 문서가 그 명세의 음영·괘선·글자 모양을 갖는다
    e = X.from_file("made.pdf", _table_pdf())
    data, meta = X.build_pick(e, {"kind": "table", "key": "p1t1"})
    assert (meta["fidelity"], meta["rows"], meta["cols"], meta["source"]["page"], meta["bands"]) == ("approx", 3, 2, 1, {"headerRows": 1, "headerCols": 0, "footRows": 1})
    assert meta["losses"][:2] == X.PDF_LOSSES and meta["source"]["block"] is None
    exp = V.expect_table(HwpxDoc(data))
    at = {(c["row"], c["col"]): c for c in exp["cells"]}
    assert at[0, 0]["fill"] == "#D9E2F3" and at[1, 1]["fill"] is None and at[0, 0]["edges"]["t"]["widthMm"] in (0.3, 0.4) and at[0, 0]["edges"]["b"]["widthMm"] == 0.12
    assert at[0, 0]["chars"][0][2]["bold"] is True and at[1, 1]["chars"][0][2]["color"] == "#BF0000" and at[1, 1]["chars"][0][2]["align"] == "right"
    assert at[0, 0]["text"] == "Item" and at[2, 0]["text"] == "Total" and at[1, 0]["text"] != "Labor"                 # 머리 띠 밖의 자료값은 싣지 않는다(견본)
