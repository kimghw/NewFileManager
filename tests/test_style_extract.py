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
    assert set(got) == {"tables", "texts", "paras", "pages", "covers"}        # 2차 꼴(spec_서식복사 ② §12·§16) — 문단 묶음 · 표지 후보가 따로
    assert isinstance(got["paras"], list) and isinstance(got["covers"], list) and len(got["covers"]) <= 1
    assert all(isinstance(c["doubts"], list) for k in got for c in got[k])  # 후보마다 스크립트 자기 점검(없으면 [])
    c = got["tables"][0]
    assert c["sizes"] == [[2, 2]] and [r["row"] for r in c["sketch"]] == [0, 1] and c["doubts"] == []
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
    # 자기 점검(② §15): 빠진 슬롯이 있다 → levelGap · 노드가 없는 그래프는 슬롯 요약의 count 그대로(서식 비율은 모름)
    assert texts[0]["doubts"] == ["levelGap"] and [(i["count"], i["sameShare"], i["others"]) for i in items] == [(2, None, []), (3, None, [])]
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
    """LLM 검토(옛 이름 name — spec_서식복사 ② §15·§16): 호출은 보낼 후보가 있는 것만(표 · 내용+문단) 차례로, 답은 다시 검사해 후보마다 R(`review` 포함)로."""
    seen = {}
    rec = {"backend": "api", "model": "m", "ms": 12, "costUsd": None, "error": None}
    answers = {
        "style-review-tables": {"tables": [
            {"key": "t1", "name": "  예산 총괄표 —\n 머리 1행·합계행 ", "keep": True, "role": "data", "bandsSure": True, "headerRows": 9, "headerCols": 1, "footRows": 9,
             "doubts": ["bandsUnsure", "repAtypical", "x"], "sameAs": "t2"},                                                    # 표의 것이 아닌 코드 · 모르는 코드 · 서식이 가깝지 않은 sameAs
            {"key": "t2", "name": "", "keep": False, "role": "sign", "bandsSure": False, "headerRows": 1, "headerCols": 0, "footRows": 0, "doubts": [], "sameAs": ""},      # 이름 없는 답
            {"key": "zz", "name": "없는 표", "keep": True, "role": "data", "bandsSure": False, "headerRows": 0, "headerCols": 0, "footRows": 0, "doubts": [], "sameAs": ""}],  # 모르는 key
            "note": "표 요약"},
        "style-review-texts": {"texts": [{"key": "tpl1", "name": "개요 1. › □ — 본문 2레벨", "keep": False, "doubts": ["guideText", "nope"], "sameAs": "", "rep": []},
                                         {"key": "nope", "name": "x", "keep": True, "doubts": [], "sameAs": "", "rep": []}], "paras": [], "note": "글 요약"}}

    def call(schema, content, what, *, timeout=None, effort=None):
        seen[what] = {"schema": schema, "content": content, "timeout": timeout, "effort": effort}
        return {"data": answers[what], **rec, "effort": effort}
    out = X.name(CANDS, call=call)
    assert X.name is X.review and X.name_data is X.review_data
    assert list(seen) == ["style-review-tables", "style-review-texts"]                    # 쪽 설정·표지 후보가 없으면 그 호출은 하지 않는다
    # 띠를 넓히자는 답(표 크기 안으로 다듬은 것)은 bandsWider 로만 — bands 는 스크립트 값 그대로(저절로 넓히지 않는다: test_name_never_widens_bands_by_itself)
    assert out["tables"] == {
        "t1": {"name": "예산 총괄표 — 머리 1행·합계행", "keep": True, "role": "data", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "bandsChanged": False,
               "bandsWider": {"headerRows": 4, "headerCols": 1, "footRows": 0},
               "review": {"by": "llm", "seen": ["이름", "띠 수", "역할"], "fixed": [], "doubts": [{"code": "bandsUnsure", "text": X.DOUBTS["bandsUnsure"], "by": "llm"}]}},
        "t2": {"keep": False, "role": "sign", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "bandsChanged": False,   # 이름이 없으면 R 에 name 이 없다(스크립트의 기본 이름으로)
               "review": {"by": "llm", "seen": ["이름", "띠 수", "역할"], "fixed": [], "doubts": []}}}
    assert out["texts"] == {"tpl1": {"name": "개요 1. › □ — 본문 2레벨", "keep": False,
                                     "review": {"by": "llm", "seen": ["이름", "레벨"], "fixed": [], "doubts": [{"code": "guideText", "text": X.DOUBTS["guideText"], "by": "llm"}]}}}
    assert out["paras"] == out["pages"] == out["covers"] == {} and out["note"] == "표 요약 글 요약"
    assert out["call"] == {**rec, "effort": "low"} and out["calls"] == [{"part": "tables", **rec, "effort": "low"}, {"part": "texts", **rec, "effort": "low"}]
    assert out["response"]["note"] == "표 요약" and set(out["responses"]) == {"tables", "texts"} and out["responses"]["texts"]["note"] == "글 요약"
    tab, txt = seen["style-review-tables"], seen["style-review-texts"]
    assert (tab["timeout"], tab["effort"], txt["timeout"], txt["effort"]) == (120.0, "low", 120.0, "low")
    assert tab["schema"] is X.SCHEMA is X.SCHEMA_TABLES and txt["schema"] is X.SCHEMA_TEXTS
    assert out["prompt"] == tab["content"] == out["prompts"]["tables"] and out["prompts"]["texts"] == txt["content"]
    for schema in (X.SCHEMA_TABLES, X.SCHEMA_TEXTS, X.SCHEMA_PAGES):
        _strict(schema)
    assert tab["content"].startswith(X.CONTRACT) and txt["content"].startswith(X.CONTRACT_TEXTS) and all("답은 고르기뿐" in p["content"] and "## 자료(JSON)" in p["content"] for p in seen.values())
    data = json.loads(tab["content"].split("## 자료(JSON)\n", 1)[1])            # 후보의 요약만 — 표 id 목록·서식 사전 전체는 안 싣는다
    # 스케치가 없는 옛 꼴 후보: 첫 행은 머리행이라 그대로, 첫 열의 아래 칸은 머리열이 없으면 가린다(「합계」 꼴만 그대로)
    assert data == {"tables": [
        {"key": "t1", "rows": 4, "cols": 3, "count": 2, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0},
         "sketch": [{"row": 0, "cells": ["구분", "1차", "2차"]}, {"row": 1, "cells": ["한글 3자"]}, {"row": 2, "cells": ["한글 3자"]}, {"row": 3, "cells": ["합계"]}],
         "lines": {"outer": "SOLID 0.4", "inner": "SOLID 0.12"},
         "looks": {"head": {"fill": "#D9E2F3", "font": "맑은 고딕", "sizePt": 10.0, "bold": True, "align": "center"}, "stub": None, "body": None, "foot": None}},
        {"key": "t2", "rows": 2, "cols": 2, "count": 1, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sketch": [{"row": 0, "cells": ["서명"]}], "looks": {}, "lines": None}]}
    assert "인건비" not in tab["content"] and "재료비" not in tab["content"]
    assert json.loads(txt["content"].split("## 자료(JSON)\n", 1)[1]) == {"paras": [], "texts": [
        {"key": "tpl1", "chain": ["N.", "□"], "doubts": [],
         "items": [{"level": 1, "letter": "N.", "sample": "숫자 1자리 기호 한글 2자", "font": "바탕", "sizePt": 12.0, "bold": True, "count": None, "sameShare": None, "others": []}]}]}
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
    assert set(pub) == {"name", "format", "fidelity", "tables", "texts", "paras", "pages", "covers", "losses"} and pub["fidelity"] == "native" and json.dumps(pub, ensure_ascii=False)  # ② §12·§16 의 다섯 종류
    assert all(set(i) >= {"count", "sameShare", "others"} for t in e["texts"] for i in t["items"]) and all(set(t["doubts"]) <= set(X.DOUBTS) for t in e["texts"])
    heads = X.head_paras(e["_graph"])                                        # 문단 묶음은 헤딩 노드의 문단을 세지 않는다
    assert heads and all(p["items"][0]["para"] not in heads and p["items"][0]["level"] is None for p in e["paras"])
    assert len(e["pages"]) == 1 and e["pages"][0]["bodies"] == [] and e["pages"][0]["section"] == 0  # 기술수요조사서 = 최상위가 표뿐 — 바탕 글 후보 없음


def test_from_file_hwpx_keeps_tables_when_the_stages_fail(monkeypatch):
    monkeypatch.setattr(X, "script_graph", lambda *a, **k: 1 / 0)
    e = X.from_file("a.hwpx", SURVEY.read_bytes())
    assert e["tables"] and e["texts"] == [] and e["_graph"] is None and "글 서식 후보는 내지 못했습니다" in e["losses"][0]
    assert isinstance(e["paras"], list) and len(e["pages"]) == 1               # 그래프가 없어도 문단 묶음·쪽 설정 후보는 낸다


def test_from_file_docx_tables_and_paragraph_groups():
    e = X.from_file("기술수요조사서.docx", DOCX.read_bytes())
    assert (e["format"], e["fidelity"]) == ("docx", "summary") and [(c["rows"], c["cols"]) for c in e["tables"]] == [(20, 6)] and e["tables"][0]["key"] in e["_blocks"]
    assert e["tables"][0]["looks"]["head"]["fill"] == "#DEEAF6" and e["tables"][0]["lines"]["outer"] == "SOLID 0.18"
    assert e["texts"] == [] and 1 <= len(e["paras"]) <= X.TEXT_GROUPS            # 서식이 같은 문단 묶음은 paras 로(전에는 texts 에 template None 으로 — ② §12)
    for t in e["paras"]:                                                     # 레벨을 지어내지 않는다
        assert "template" not in t and t["count"] >= 1 and len(t["items"]) == 1 and t["items"][0]["level"] is None and t["items"][0]["marker"]["mode"] in ("literal", "auto", "none")
        assert t["role"] in (None, "body", "caption", "note", "box") and set(t["where"]) == {"caption", "note", "box"} and t["doubts"] == []
    assert [t["count"] for t in e["paras"]] == sorted((t["count"] for t in e["paras"]), reverse=True)
    assert set(X.public(e)) == {"name", "format", "fidelity", "tables", "texts", "paras", "pages", "covers", "losses"}
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
    group = e["paras"][0]                                                    # 문단 묶음 후보(② §12) — kind "text" 의 key 로 저장하고 역할이 meta 에 실린다
    data, meta = X.build_pick(e, {"kind": "text", "key": group["key"], "name": "별첨 줄", "role": "note"})
    assert (meta["kind"], meta["fidelity"], meta["name"], meta["role"]) == ("text", "summary", "별첨 줄", "note") and X.DOCX_TEXT_LOSS in meta["losses"] and len(meta["items"]) == 1
    assert meta["items"][0]["level"] is None and meta["items"][0]["format"]["sizePt"] == group["items"][0]["format"]["sizePt"]
    assert X.build_pick(e, {"kind": "text", "key": group["key"], "role": "weird"})[1]["role"] == group["role"]   # 모르는 역할은 후보의 어림으로
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


def test_name_attaches_the_style_copy_job_prompt(monkeypatch):
    """에이전트 추출 ①(이름 붙이기)은 TASK 「문서 서식 복사」 의 전제 글(jobs/style_copy.md)을 계약 바로 뒤에 붙인다(spec_서식복사 ② §6 — 무엇이 다시 쓸 만한가·이름 기준의 원본은 그 글)."""
    from app import job_prompts
    monkeypatch.setenv("NFM_JOBS", str(job_prompts.DEFAULT_DIR))             # 저장소 jobs/ 의 글을 본다(conftest 는 빈 임시 폴더로 돌려 둔다)
    seen = {}

    def fake(schema, prompt, tag, **kw):
        seen["prompt"] = prompt
        return {"data": {"tables": [], "texts": [], "note": ""}, "backend": "fake", "model": "m", "effort": "low", "ms": 1, "costUsd": 0, "error": None}
    cands = {"tables": [{"key": "t1", "rows": 2, "cols": 2, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "sample": "a"}], "texts": []}
    job = job_prompts.get("style_copy")
    assert job is not None and job["name"] == "문서 서식 복사"
    got = X.name(cands, call=fake, job=job)
    p = seen["prompt"]
    assert got["job"] == {"job": "style_copy", "name": "문서 서식 복사", "sha1": job["sha1"]}
    assert "## 할 일 — 문서 서식 복사" in p and "구조와 겉모습" in p and p.index(X.CONTRACT[:20]) < p.index("## 할 일") < p.index("## 자료(JSON)")
    assert "<!--" not in p                                                    # 주석(사용자 원문 메모)은 프롬프트에 안 들어간다
    assert X.name(cands, call=fake)["job"] is None and "## 할 일" not in seen["prompt"]   # 안 주면 전과 같은 프롬프트


def test_name_never_widens_bands_by_itself():
    """LLM 이 띠를 **넓히자고** 해도 저절로 받지 않는다(머리 띠 안 칸의 글은 라벨로 보관함에 남는다 — 잘못 넓어지면 자료값이 저장된다: 2026-11-14 Fable 검토). 좁히는 쪽만 bands 에, 넓히자는 답은 bandsWider 로."""
    cands = {"tables": [{"key": "t1", "rows": 6, "cols": 4, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "sample": "a"},
                        {"key": "t2", "rows": 6, "cols": 4, "bands": {"headerRows": 2, "headerCols": 1, "footRows": 1}, "sample": "b"}], "texts": []}

    def fake(schema, prompt, tag, **kw):
        return {"data": {"tables": [{"key": "t1", "name": "넓히자는 표", "keep": True, "bandsSure": True, "headerRows": 2, "headerCols": 1, "footRows": 1},
                                    {"key": "t2", "name": "좁히자는 표", "keep": True, "bandsSure": True, "headerRows": 1, "headerCols": 1, "footRows": 0}], "texts": [], "note": ""},
                "backend": "fake", "model": "m", "effort": "low", "ms": 1, "costUsd": 0, "error": None}
    got = X.name(cands, call=fake)["tables"]
    assert got["t1"]["bands"] == {"headerRows": 1, "headerCols": 1, "footRows": 0} and got["t1"]["bandsChanged"] is False
    assert got["t1"]["bandsWider"] == {"headerRows": 2, "headerCols": 1, "footRows": 1}
    assert got["t2"]["bands"] == {"headerRows": 1, "headerCols": 1, "footRows": 0} and got["t2"]["bandsChanged"] is True and "bandsWider" not in got["t2"]
    # 좁힌 것은 「LLM 고침」 으로 남는다(되돌릴 수 있게 전·후 값) — 넓히자는 제안은 고침이 아니다
    assert got["t2"]["review"]["fixed"] == [{"what": "띠 수", "from": {"headerRows": 2, "headerCols": 1, "footRows": 1}, "to": {"headerRows": 1, "headerCols": 1, "footRows": 0}}]
    assert got["t1"]["review"]["fixed"] == [] and got["t1"]["keep"] is True


# ---- 2차: 가리기 · 스케치 · 문단 묶음 · 자기 점검 · LLM 검토의 재검사(spec_서식복사 ② §12·§15·§16) ---------------------

RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"
GRID = [["성명", "소속", "금액"], ["홍길동", "한국선급", "1,200,000"], ["김철수", "부산대학교", "950,000"], ["이영희", "KRISO", "2026-11-14"], ["박민수", "해양대", "30"], ["합계", "", "2,150,030"]]


def _view(rows):
    """글의 격자 → 칸 보기(`block_cells` 꼴) — 첫 행만 음영·굵게."""
    return [{"row": r, "col": k, "rowSpan": 1, "colSpan": 1, "text": t, "shaded": r == 0, "bold": r == 0, "edges": {}, "look": {}} for r, row in enumerate(rows) for k, t in enumerate(row)]


def _fake(answers, seen=None):
    """가짜 call — 호출 이름의 끝 낱말(tables · texts · pages)로 답을 고른다(없으면 답 없음)."""
    def call(schema, content, what, **kw):
        if seen is not None:
            seen[what] = (schema, content, kw)
        return {"data": answers.get(what.rsplit("-", 1)[-1]), "backend": "fake", "model": "m", "effort": kw.get("effort"), "ms": 1, "costUsd": 0, "error": None}
    return call


def _sent(prompt):
    return json.loads(prompt.split("## 자료(JSON)\n", 1)[1])


def test_mask_hides_every_character_behind_its_shape():
    assert X.mask("") == X.mask(None) == X.mask("  \n ") == ""
    assert X.mask("홍길동") == "한글 3자" and X.mask("KRISO 2026-11-14") == "영문 5자 날짜" and X.mask("1,200,000원") == "숫자 7자리 한글 1자"
    assert X.mask("2026. 11. 14.") == "날짜" and X.mask("2026년 3월 5일") == "날짜" and X.mask("韓國 --") == "글자 2자 기호"
    assert X.mask("(주)한국 A-1") == "기호 한글 1자 기호 한글 2자 영문 1자 기호 숫자 1자리"
    assert X.mask("가 나 다 라 마 바 사 아 자 차") == " ".join(["한글 1자"] * X.MASK_TOKENS) + " …"   # 짧게 — 조각 8개까지
    assert X._masked("한글 3자 숫자 2자리 …") == "한글 3자 숫자 2자리 …" and X._masked("과제 책임자") == "한글 2자 한글 3자"   # 이미 가린 글은 그대로 · 원문이면 가린다


def test_sketch_shows_head_band_text_and_masks_the_rest():
    bands = {"headerRows": 1, "headerCols": 0, "footRows": 0}
    sk = X.sketch(_view(GRID), 6, 3, bands)
    assert [r["row"] for r in sk] == [0, 1, 2, 4, 5]                          # 앞 3행 + 끝 2행
    assert sk[0]["cells"][0] == {"col": 0, "span": [1, 1], "text": "성명", "shaded": True, "bold": True}
    assert [[c["text"] for c in r["cells"]] for r in sk] == [["성명", "소속", "금액"], ["한글 3자", "한글 4자", "숫자 7자리"], ["한글 3자", "한글 5자", "숫자 6자리"],
                                                             ["한글 3자", "한글 3자", "숫자 2자리"], ["합계", "", "숫자 7자리"]]   # 머리 띠 밖은 꼴만 · 「합계」 꼴 글은 그대로
    assert X.sketch(_view(GRID), 6, 3, {**bands, "headerCols": 1})[1]["cells"][0]["text"] == "홍길동"   # 머리열 안은 그대로
    assert [r["row"] for r in X.sketch(_view(GRID[:2]), 2, 3, bands)] == [0, 1]
    merged = [{"row": 0, "col": 0, "rowSpan": 2, "colSpan": 1, "text": "구분", "shaded": True, "bold": False}, {"row": 0, "col": 1, "rowSpan": 1, "colSpan": 1, "text": "가"},
              {"row": 1, "col": 1, "rowSpan": 1, "colSpan": 1, "text": "나"}]
    got = X.sketch(merged, 2, 2, bands)
    assert got[0]["cells"][0]["span"] == [2, 1] and [c["col"] for c in got[1]["cells"]] == [1]   # 그 행에서 시작하는 칸만
    assert X._cell_line({"text": "구분", "span": [2, 1], "shaded": True, "bold": True}) == "구분 [음영·굵게·합침 2×1]" and X._cell_line({"text": "", "span": [1, 1]}) == ""
    body, _ = X.table_look(_view(GRID), 6, 3)                                 # 표 후보가 스케치를 지닌다(띠 수는 자동 판정 — 합계행 1)
    assert body["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 1} and body["sketch"] == X.sketch(_view(GRID), 6, 3, body["bands"])


def test_review_sends_only_masked_text_in_three_calls():
    """LLM 에 보내는 것(② §15): 호출 셋 — 표 · 내용+문단 · 쪽 설정+표지. 머리 띠 밖 칸 글과 문단 글은 꼴로 가린다(성명·기관·금액이 나가지 않는다)."""
    body, _ = X.table_look(_view(GRID), 6, 3)
    cands = {"tables": [{"key": "t1", "table": "t1", "same": ["t1", "t4"], "count": 2, "sizes": [[6, 3], [9, 3]], "doubts": [], **body}],
             "texts": [{"key": "tpl1", "template": {"id": 1, "no": 1, "name": "", "chain": ["N.", "가."]}, "doubts": ["repAtypical"],
                        "items": [{"para": "p1", "level": 1, "letter": "1.", "sample": "1. 홍길동 과제의 필요성", "format": {"font": "바탕", "sizePt": 14.0, "bold": True}, "count": 9, "sameShare": 0.33,
                                   "others": ["p7"], "otherLooks": [{"para": "p7", "sample": "2. 한국선급 현황", "format": {"font": "돋움", "sizePt": 12.0, "bold": False}, "count": 6}]}]}],
             "paras": [{"key": "p20", "role": "body", "count": 40, "where": {"caption": 0, "note": 0, "box": 0}, "doubts": [],
                        "items": [{"para": "p20", "level": None, "letter": "", "sample": "본 과제는 한국선급이 수행한다", "format": {"font": "바탕", "sizePt": 11.0, "bold": False, "align": "justify"}, "marker": None}]}],
             "pages": [{"key": "page", "page": {}, "body": None, "sample": "A4 세로 · 여백 왼 20 · 오 20 · 위 20 · 아래 15mm", "losses": [], "doubts": ["bodyClose"],
                        "bodies": [{"key": "b1", "format": {"font": "돋움", "sizePt": 13.0, "bold": True}, "count": 12, "chars": 400, "sample": "자율운항선박 기술개발 사업"},
                                   {"key": "b2", "format": {"font": "바탕", "sizePt": 11.0, "bold": False}, "count": 30, "chars": 380, "sample": "부산대학교 연구진이 참여한다"}]}],
             "covers": [{"key": "cover", "blocks": ["p1", "t2", "p3"], "end": "p3", "signals": {"centered": True}, "sample": "", "doubts": [],
                         "parts": [{"block": "p1", "type": "text", "role": "title", "sample": "자율운항선박 기술개발 계획서", "sizePt": 22.0, "align": "center"},   # 원문이 와도 가려 보낸다
                                   {"block": "t2", "type": "table", "role": "other", "sample": "한글 3자", "rows": 3, "cols": 2},
                                   {"block": "p3", "type": "text", "role": "date", "sample": "2026. 11. 14.", "sizePt": 14.0, "align": "center"}]}]}
    seen = {}
    out = X.review(cands, call=_fake({"tables": {"note": ""}, "texts": {"note": ""}, "pages": {"note": ""}}, seen))
    assert list(seen) == ["style-review-tables", "style-review-texts", "style-review-pages"] and [c["part"] for c in out["calls"]] == ["tables", "texts", "pages"]
    assert [s for s, _, _ in seen.values()] == [X.SCHEMA_TABLES, X.SCHEMA_TEXTS, X.SCHEMA_PAGES] and all(kw == {"timeout": 120.0, "effort": "low"} for _, _, kw in seen.values())
    assert [p.startswith(c) for (_, p, _), c in zip(seen.values(), (X.CONTRACT_TABLES, X.CONTRACT_TEXTS, X.CONTRACT_PAGES))] == [True] * 3
    sent = "".join(p.split("## 자료(JSON)\n", 1)[1] for _, p, _ in seen.values())
    for raw in ("홍길동", "김철수", "박민수", "한국선급", "부산대학교", "해양대", "1,200,000", "2,150,030", "자율운항선박", "연구진", "과제", "2026"):
        assert raw not in sent, raw
    table = _sent(seen["style-review-tables"][1])["tables"][0]
    assert table["sizes"] == [[6, 3], [9, 3]] and table["sketch"][0] == {"row": 0, "cells": ["성명 [음영·굵게]", "소속 [음영·굵게]", "금액 [음영·굵게]"]}
    assert table["sketch"][1] == {"row": 1, "cells": ["한글 3자", "한글 4자", "숫자 7자리"]} and table["sketch"][-1]["cells"][0] == "합계" and "head" not in table and "stub" not in table
    texts = _sent(seen["style-review-texts"][1])
    assert texts["texts"][0]["doubts"] == ["repAtypical"] and texts["texts"][0]["items"][0] == {
        "level": 1, "letter": "1.", "sample": "숫자 1자리 기호 한글 3자 한글 3자 한글 3자", "font": "바탕", "sizePt": 14.0, "bold": True, "count": 9, "sameShare": 0.33,
        "others": [{"para": "p7", "sample": "숫자 1자리 기호 한글 4자 한글 2자", "font": "돋움", "sizePt": 12.0, "bold": False, "count": 6}]}   # 레터는 그대로 · 견본은 꼴
    assert texts["paras"] == [{"key": "p20", "count": 40, "role": "body", "sample": "한글 1자 한글 3자 한글 5자 한글 4자", "letter": "", "font": "바탕", "sizePt": 11.0, "bold": False, "align": "justify",
                               "where": {"caption": 0, "note": 0, "box": 0}}]
    pages = _sent(seen["style-review-pages"][1])
    assert pages["pages"][0]["doubts"] == ["bodyClose"] and pages["pages"][0]["summary"].startswith("A4 세로") and [b["key"] for b in pages["pages"][0]["bodies"]] == ["b1", "b2"]
    assert pages["pages"][0]["bodies"][1] == {"key": "b2", "count": 30, "chars": 380, "sample": "한글 5자 한글 4자 한글 4자", "font": "바탕", "sizePt": 11.0, "bold": False, "align": None}
    parts = pages["covers"][0]["parts"]
    assert [p["sample"] for p in parts] == ["한글 6자 한글 4자 한글 3자", "한글 3자", "날짜"] and parts[1] == {"block": "t2", "type": "table", "role": "other", "sample": "한글 3자", "rows": 3, "cols": 2}
    # 답에서 빠진 후보는 검토 결과가 없다 — keep 이 저절로 참이 되지 않는다(전에는 `is not False`)
    assert out["tables"] == out["texts"] == out["paras"] == out["pages"] == out["covers"] == {} and all(c["error"] is None for c in out["calls"])
    assert X.review({**cands, "pages": [{**cands["pages"][0], "bodies": []}], "covers": []}, call=_fake({}, seen := {}))["calls"][-1]["part"] == "texts" and len(seen) == 2   # 보낼 것이 없는 호출은 하지 않는다


def _tpl(key, others=(), second=None):
    first, second = {"font": "바탕", "sizePt": 14.0, "bold": True}, second or {"font": "바탕", "sizePt": 12.0, "bold": False}
    return {"key": key, "template": {"id": key, "no": 1, "name": "", "chain": ["N.", "□"]}, "doubts": ["repAtypical"],
            "items": [{"para": "p1", "level": 1, "letter": "N.", "sample": "1. 가", "format": first, "count": 10, "sameShare": 0.3, "others": list(others)},
                      {"para": "p2", "level": 2, "letter": "□", "sample": "□ 나", "format": second, "count": 4, "sameShare": 1.0, "others": []}]}


def _loose(key, role):
    return {"key": key, "role": role, "count": 3, "items": [{"para": key, "level": None, "letter": "", "sample": "가", "format": {}, "marker": None}], "where": {"caption": 0, "note": 0, "box": 0}, "doubts": []}


RECHECK = {"texts": [_tpl("tplA", ["p7", "p8"]), _tpl("tplB"), _tpl("tplC", second={"font": "돋움", "sizePt": 12.0, "bold": False})],
           "paras": [_loose("p20", "body"), _loose("p21", None), _loose("p22", "box")],
           "pages": [{"key": "page", "sample": "A4 세로", "doubts": ["bodyClose"],
                      "bodies": [{"key": "b1", "format": {}, "count": 3, "chars": 90, "sample": "가"}, {"key": "b2", "format": {}, "count": 5, "chars": 80, "sample": "나"}]}],
           "covers": [{"key": "cover", "blocks": ["p1", "t2", "p3", "p4"], "end": "p4", "signals": {}, "doubts": [],
                       "parts": [{"block": "p1", "type": "text", "role": "title", "sample": "한글 2자"}, {"block": "t2", "type": "table", "role": "other", "sample": "", "rows": 2, "cols": 2},
                                 {"block": "p3", "type": "text", "role": "other", "sample": "한글 4자"}, {"block": "p4", "type": "text", "role": "date", "sample": "날짜"}]}]}


def test_review_rechecks_every_pick_of_the_answer():
    """스크립트 재검사(② §15): 모르는 key·id·코드는 버림 · rep 는 그 레벨의 others 안의 id · sameAs 는 서식이 가까울 때만 · end 는 표지 범위 안(줄이는 쪽만) · bodyKey 는 보낸 key 나 none ·
    연도·긴 수가 든 이름은 버림 · keep 이 빠지면 추천 아님."""
    answers = {"texts": {"texts": [
                   {"key": "tplA", "name": "2026년 개요 사슬", "keep": True, "doubts": ["levelOrder", "repAtypical", "bandsUnsure"], "sameAs": "tplB",
                    "rep": [{"level": 1, "para": "p7"}, {"level": 2, "para": "p7"}, {"level": 1, "para": "p8"}, {"level": 9, "para": "p7"}, {"level": 1, "para": "p1"}]},
                   {"key": "tplB", "name": "개요 1234567", "doubts": [], "sameAs": "tplC", "rep": [{"level": 1, "para": "zzz"}]},      # keep 이 빠진 답
                   {"key": "tplZ", "name": "없는 후보", "keep": True, "doubts": [], "sameAs": "", "rep": []}],
                 "paras": [{"key": "p20", "name": "캡션 — 가운데 정렬", "keep": True, "role": "caption"}, {"key": "p21", "name": "목차 줄", "keep": True, "role": "toc"},
                           {"key": "p22", "name": "상자 글", "keep": False, "role": "weird"}, {"key": "p99", "name": "x", "keep": True, "role": "body"}], "note": ""},
               "pages": {"pages": [{"key": "page", "bodyKey": "b2", "doubts": ["bodyClose", "levelGap"]}],
                         "covers": [{"key": "cover", "name": "표지 — 제목·기관·날짜", "isCover": True, "end": "p9",
                                     "roles": [{"block": "p3", "role": "org"}, {"block": "p1", "role": "title"}, {"block": "zz", "role": "org"}, {"block": "p4", "role": "king"}],
                                     "doubts": ["coverUnsure"]}], "note": ""}}
    out = X.review(RECHECK, call=_fake(answers))
    assert set(out["texts"]) == {"tplA", "tplB"}                                # 답에서 빠진 후보(tplC) · 모르는 key(tplZ)는 결과가 없다
    a, b = out["texts"]["tplA"], out["texts"]["tplB"]
    assert "name" not in a and a["keep"] is True and a["rep"] == {"1": "p7"} and a["sameAs"] == "tplB"   # 연도가 든 이름은 버린다 · rep = 그 레벨의 others 안의 id 만(레벨마다 첫 것)
    assert a["review"] == {"by": "llm", "seen": ["이름", "레벨"], "fixed": [{"what": "대표 문단", "level": 1, "from": "p1", "to": "p7"}],
                           "doubts": [{"code": "repAtypical", "text": X.DOUBTS["repAtypical"], "by": "script"}, {"code": "levelOrder", "text": X.DOUBTS["levelOrder"], "by": "llm"}]}
    assert "name" not in b and b["keep"] is False and "rep" not in b and "sameAs" not in b and b["review"]["fixed"] == []   # 6자리 넘는 수 · keep 빠짐 · 슬롯 밖 rep · 서식이 다른 sameAs
    assert set(out["paras"]) == {"p20", "p21", "p22"} and out["paras"]["p20"]["name"] == "캡션 — 가운데 정렬"
    assert out["paras"]["p20"]["role"] == "caption" and out["paras"]["p20"]["review"]["fixed"] == [{"what": "역할", "from": "body", "to": "caption"}]
    assert out["paras"]["p21"]["role"] == "toc" and out["paras"]["p21"]["review"]["fixed"] == []      # 모르던 역할을 채운 것은 고침이 아니다
    assert "role" not in out["paras"]["p22"] and out["paras"]["p22"]["keep"] is False and out["paras"]["p22"]["review"]["seen"] == ["이름", "역할"]   # 모르는 역할 코드는 버린다
    page, cover = out["pages"]["page"], out["covers"]["cover"]
    assert page["keep"] is True and page["bodyKey"] == "b2" and page["review"]["fixed"] == [{"what": "바탕 글", "from": "b1", "to": "b2"}]
    assert page["review"]["doubts"] == [{"code": "bodyClose", "text": X.DOUBTS["bodyClose"], "by": "script"}] and page["review"]["seen"] == ["바탕 글"]
    assert cover["name"] == "표지 — 제목·기관·날짜" and cover["keep"] is True and cover["isCover"] is True and "end" not in cover and cover["roles"] == {"p3": "org"}   # 범위 밖 end(p9)는 버린다
    assert cover["review"] == {"by": "llm", "seen": ["범위", "역할"], "fixed": [{"what": "역할", "from": {"p3": "other"}, "to": {"p3": "org"}}],
                               "doubts": [{"code": "coverUnsure", "text": X.DOUBTS["coverUnsure"], "by": "llm"}]}
    # 범위를 줄이는 end · 모르는 bodyKey · 답이 없는 호출(내용+문단)은 그 후보만 결과가 없다
    again = X.review(RECHECK, call=_fake({"pages": {"pages": [{"key": "page", "bodyKey": "b9", "doubts": []}],
                                                    "covers": [{"key": "cover", "name": "", "isCover": False, "end": "t2", "roles": [], "doubts": []}], "note": ""}}))
    assert "bodyKey" not in again["pages"]["page"] and again["pages"]["page"]["review"]["fixed"] == []
    assert again["covers"]["cover"]["end"] == "t2" and again["covers"]["cover"]["keep"] is False and again["covers"]["cover"]["review"]["fixed"] == [{"what": "범위", "from": "p4", "to": "t2"}]
    assert again["texts"] == again["paras"] == {} and [(c["part"], c["error"]) for c in again["calls"]] == [("texts", "답이 없습니다"), ("pages", None)] and again["call"]["error"] == "답이 없습니다"
    none = X.review(RECHECK, call=_fake({"pages": {"pages": [{"key": "page", "bodyKey": "none", "doubts": []}],
                                                   "covers": [{"key": "cover", "name": "", "isCover": True, "end": "p4", "roles": [], "doubts": []}], "note": ""}}))
    assert none["pages"]["page"]["bodyKey"] == "none" and "end" not in none["covers"]["cover"]       # 끝 블록 그대로는 줄임이 아니다


def test_review_keeps_the_other_calls_when_one_fails(monkeypatch):
    def call(schema, content, what, **kw):
        if what == "style-review-tables":
            raise RuntimeError("끊김")
        return {"data": {"texts": [{"key": "tpl1", "name": "개요 두 레벨", "keep": True, "doubts": [], "sameAs": "", "rep": []}], "paras": [], "note": "n"}, "backend": "fake", "error": None}
    out = X.review(CANDS, call=call)
    assert out["tables"] == {} and out["texts"]["tpl1"]["keep"] is True and "끊김" in out["calls"][0]["error"] and out["calls"][1]["error"] is None and "끊김" in out["call"]["error"]
    asked = {}

    def ask_all(jobs):                                                       # call 을 안 주면 호출들을 함께(llm.ask_all) — 호출마다 120초 · effort low
        asked["jobs"] = jobs
        return [{"data": None, "backend": None, "ms": 0, "costUsd": None, "error": "off"} for _ in jobs]
    monkeypatch.setattr(X.llm, "ask_all", ask_all)
    off = X.review(CANDS)
    assert [(j["what"], j["timeout"], j["effort"]) for j in asked["jobs"]] == [("style-review-tables", 120.0, "low"), ("style-review-texts", 120.0, "low")]
    assert [j["schema"] for j in asked["jobs"]] == [X.SCHEMA_TABLES, X.SCHEMA_TEXTS] and [j["content"] for j in asked["jobs"]] == [off["prompts"]["tables"], off["prompts"]["texts"]]
    assert [c["error"] for c in off["calls"]] == ["off", "off"] and off["tables"] == off["texts"] == {}


def test_para_groups_roles_boxes_and_skipped_heading_paragraphs():
    """문단 묶음 후보(② §12): 헤딩 노드의 문단은 빼고 · 1칸 표(글상자) 안 문단을 더하고 · 역할을 어림한다(캡션 · 주석 · 상자 글 · 본문)."""
    body = {"font": "바탕", "sizePt": 10.0, "bold": False}
    fmt = lambda size, **kw: {"font": "바탕", "sizePt": size, "bold": False, **kw}  # noqa: E731
    para = lambda i, text, f, **kw: {"id": i, "type": "paragraph", "text": text, "format": dict(f), **kw}  # noqa: E731
    cell = lambda i, col, blocks: {"id": i, "row": 0, "col": col, "rowSpan": 1, "colSpan": 1, "text": "", "blocks": blocks}  # noqa: E731
    box = {"id": "t1", "type": "table", "nRows": 1, "nCols": 1, "cells": [cell("c1", 0, [para("b1", "상자 글 하나", fmt(9.0)), para("b2", "상자 글 둘", fmt(9.0)), para("b3", "  ", fmt(9.0))])]}
    grid = {"id": "t2", "type": "table", "nRows": 1, "nCols": 2, "cells": [cell("c2", 0, [para("x1", "칸 글", fmt(7.0))]), cell("c3", 1, [])]}          # 2칸 표 안 문단은 세지 않는다
    guide = {"id": "t3", "type": "table", "nRows": 1, "nCols": 1, "cells": [cell("c4", 0, [para("g1", "< 작성 요령 >", fmt(6.0)), para("g2", "o 이렇게 씁니다", fmt(6.0))])]}  # 안내문 상자도
    blocks = [para("h1", "1. 제목", fmt(14.0, bold=True)), para("p1", "본문 하나", {**body, "lineSpacingPct": None}), para("p2", "본문 둘", {**body, "lineSpacingPct": None}),
              para("p3", "본문 셋", {**body, "lineSpacingPct": None}), box, para("c9", "<표 1> 예산", fmt(8.0), captionOf="t9"), para("n1", "※ 주석 하나", fmt(8.5)), para("n2", "* 주석 둘", fmt(8.5)),
              grid, guide, para("o1", "그 밖의 줄", fmt(12.0))]
    got = X.para_groups(blocks, skip={"h1"}, body=body)
    assert [(g["key"], g["role"], g["count"]) for g in got] == [("p1", "body", 3), ("b1", "box", 2), ("n1", "note", 2), ("c9", "caption", 1), ("o1", None, 1)]
    assert [g["where"] for g in got[1:4]] == [{"caption": 0, "note": 0, "box": 2}, {"caption": 0, "note": 2, "box": 0}, {"caption": 1, "note": 0, "box": 0}]
    assert all(g["doubts"] == [] and g["items"][0]["level"] is None and g["items"][0]["para"] == g["key"] for g in got)
    loose = X.para_groups(blocks)                                            # skip·body 없이(그래프가 없는 문서) — 제목 줄도 묶음이 되고 본문 역할은 모른다
    assert "h1" in [g["key"] for g in loose] and loose[0]["key"] == "p1" and loose[0]["role"] is None
    graph = {"nodes": [{"id": "h1", "para": "h1", "role": "heading", "template": "main", "tplNo": 1, "level": 1, "span": 0}, {"id": "p1", "para": "p1", "role": "not_heading", "template": None},
                       {"id": "n1", "para": "n1", "role": "note"}, {"id": "o1#1", "para": "o1", "role": "label", "span": 1}, "junk", {"para": 3, "role": "heading"}]}
    assert X.head_paras(graph) == {"h1", "o1"} and X.head_paras(None) == set() and X.head_paras({"nodes": None}) == set()


def test_text_candidates_check_themselves_against_the_slot_paragraphs():
    """스크립트 자기 점검(② §15): 슬롯의 구성 문단(그래프의 노드)을 지금 문서의 서식으로 견준다 — 대표가 다수 서식이 아님(repAtypical) · 다수가 80% 미만(mixedSlot)."""
    doc, first, _ = _base()
    ids = [first]
    for text in ("1. 하나", "2. 둘", "3. 셋", "4. 넷", " □ 가", " □ 나"):
        ids.append(doc.insert_line(ids[-1], text))
    a, b, c, d, e, f = ids[1:]
    doc.apply_format([a], doc.derive_format(doc.get_format(a), {"bold": not doc.get_format(a)["summary"]["bold"]}))   # 대표 문단(a)만 다른 서식 — 나머지 셋이 다수
    node = lambda pid, level, **kw: {"id": pid, "para": pid, "role": "heading", "template": "main", "tplNo": 1, "level": level, "span": 0, **kw}  # noqa: E731
    graph = {"version": 2, "templates": [{"id": 1, "no": 1, "name": "main", "anchor": "main", "chain": ["N.", "□"],
                                          "slots": [{"level": 1, "letter": "N.", "count": 4, "format": "S1", "rep": a}, {"level": 2, "letter": "□", "count": 2, "format": "S2", "rep": e}]}],
             "nodes": [node(a, 1), node(b, 1), node(c, 1), node(d, 1), node(e, 2), node(f, 2), node(f, 2, id=f + "#1", span=1),
                       {"id": "x", "para": c, "role": "not_heading", "tplNo": 1, "level": 2}]}
    got = X.candidates(doc, graph)
    cand = got["texts"][0]
    one, two = cand["items"]
    assert cand["doubts"] == ["repAtypical", "mixedSlot"] and set(cand["doubts"]) <= set(X.DOUBTS)
    assert (one["count"], one["sameShare"], one["others"]) == (4, 0.25, [b]) and (two["count"], two["sameShare"], two["others"]) == (2, 1.0, [])
    assert [(o["para"], o["sample"], o["count"]) for o in one["otherLooks"]] == [(b, "2. 둘", 3)] and one["otherLooks"][0]["format"] == doc.get_format(b)["summary"]
    assert not {a, b, c, d, e, f} & {g["items"][0]["para"] for g in got["paras"]}   # 헤딩 노드의 문단은 문단 묶음에 들지 않는다
    # LLM 이 대표를 others 의 것으로 바꾸면 그 id 로 받는다(값은 스크립트가 다시 읽는다 — 저장 `rep: {레벨: 문단 id}`)
    ans = {"texts": {"texts": [{"key": cand["key"], "name": "개요 두 레벨", "keep": True, "doubts": [], "sameAs": "", "rep": [{"level": 1, "para": b}, {"level": 1, "para": c}]}], "paras": [], "note": ""}}
    r = X.review({"texts": got["texts"]}, call=_fake(ans))["texts"][cand["key"]]
    assert r["rep"] == {"1": b} and [d["code"] for d in r["review"]["doubts"]] == ["repAtypical", "mixedSlot"] and all(d["by"] == "script" for d in r["review"]["doubts"])


def test_page_candidates_carry_bodies_and_doubts(monkeypatch):
    from app import style_page as SP
    page = {"widthMm": 210, "heightMm": 297, "marginsMm": {"l": 20, "r": 20, "t": 20, "b": 15}}
    tops = [{"key": "b1", "format": {"font": "돋움", "sizePt": 13.0, "bold": True}, "count": 4, "chars": 100, "sample": "제목 줄"},
            {"key": "b2", "format": {"font": "바탕", "sizePt": 11.0}, "count": 9, "chars": 85, "sample": "본문 줄"}]
    seen = {}

    def of_hwpx(doc, skip=()):
        seen["skip"] = skip
        return {"page": page, "body": {"format": tops[0]["format"], "count": 4}, "bodies": tops, "section": 1, "losses": [SP.diff_note(1)]}
    monkeypatch.setattr(SP, "of_hwpx", of_hwpx)
    c = X.page_candidates("hwpx", object(), {"p1"})[0]
    assert seen["skip"] == {"p1"} and c["key"] == "page" and c["bodies"] == tops and c["section"] == 1 and c["body"] == {"format": tops[0]["format"], "count": 4}
    assert c["doubts"] == ["bodyClose", "sectionsDiffer"] and c["losses"] == [SP.diff_note(1)] and "본문 돋움 13pt" in c["sample"]   # 1·2위 차이 15% · 구역마다 다름
    assert X.body_pick(c, None) == c["body"] and X.body_pick(c, "none") is None and X.body_pick(c, "b2") == {"format": {"font": "바탕", "sizePt": 11.0}, "count": 9}
    with pytest.raises(ValueError, match="bodyKey"):
        X.body_pick(c, "b9")
    far = [tops[0], {**tops[1], "chars": 80}]                                # 차이 20% — 가깝지 않다
    monkeypatch.setattr(SP, "of_hwpx", lambda doc, skip=(): {"page": page, "body": None, "bodies": far, "section": 0, "losses": []})
    assert X.page_candidates("hwpx", object())[0]["doubts"] == []


def test_bodies_of_the_rnd_form_skip_heading_paragraphs():
    """연구개발계획서 양식: 바탕 글 후보는 헤딩 노드의 문단을 빼고 센다(② §15 — 굵은 제목 줄이 바탕 글 1위로 뽑히던 것). 무엇이 1위가 되는지는 문서에 달렸다 — 여기서는 세는 규칙만 본다."""
    from app import style_page as SP
    from app.hwpx_format import SUMMARY_KEYS
    doc = HwpxDoc(RND.read_bytes())
    heads = X.head_paras(X.script_graph(doc, RND.name))
    blocks = doc.blocks()
    tops = SP.bodies(blocks, heads)
    assert heads and 1 <= len(tops) <= 3 and [t["key"] for t in tops] == ["b1", "b2", "b3"][:len(tops)]
    assert [t["chars"] for t in tops] == sorted((t["chars"] for t in tops), reverse=True) and all(len(t["sample"]) <= 60 for t in tops)
    look = lambda b: {k: v for k, v in b["format"].items() if k in SUMMARY_KEYS and v is not None}  # noqa: E731
    counted = [b for b in blocks if b["type"] == "paragraph" and b["text"].strip() and not b.get("captionOf") and b["id"] not in heads]
    for t in tops:                                                           # 후보의 수·글자 수 = 헤딩 문단을 뺀 것
        same = [b for b in counted if look(b) == t["format"]]
        assert len(same) == t["count"] and sum(len("".join(b["text"].split())) for b in same) == t["chars"]
    assert SP.body_of(blocks, heads) == {"format": tops[0]["format"], "count": tops[0]["count"]}
    assert SP.bodies(blocks)[0]["chars"] >= tops[0]["chars"]                  # 빼지 않고 세면 1위가 더 크거나 같다
    page = X.page_candidates("hwpx", doc, heads)[0]
    assert page["bodies"] == tops and page["body"] == SP.body_of(blocks, heads) and isinstance(page["section"], int)
