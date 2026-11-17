"""헤딩 추출 2단계 — 띠 표 줄(spec_헤딩_추출 ② §6 「띠 표 줄」, 2026-11-17 사용자 "테이블도 헤딩레벨로 간주 … 별첨, 부록 appendix … 템플릿 문서 구조상에서는 잡히질 않아" →
답 「제 템플릿으로」 · 「헤딩 추출이 스스로」).
ⓐ 이름표(별첨N · 부록A · Appendix …)와 정규 키 · ⓑ 띠 표 찾기(본문의 1행 표 · 이름표 칸 + 제목 칸) · ⓒ 그래프 — 띠 표 줄은 늘 헤딩 · 문서 맨 위 · 제 템플릿(kind band · 번호 맨 뒤) L1,
그 아래 줄은 다음 띠 표·주 사슬 첫 레터까지 그 줄의 자식이고 템플릿 사슬에는 투명 · A·B 의 답으로 안 바뀜 · ⓓ 샘플 문서(별첨1~9) · ⓔ 오버레이 — 표 줄(role table)로.
LLM 은 가짜 ask."""
import copy

import pytest

from app import heading_bands as HB
from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import outline_edit as OE
from app import outline_lift
from app.hwpx_doc import HwpxDoc
from tests.test_headings_branch import EMPTY, RND, _nodes, _rec, _res, fake_ask

MAIN = "body:N.›N-N.›(N)"
BAND = "body:별첨N"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


# ---- ⓐ 이름표 ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, key", [
    ("별첨1", "별첨N"), ("별첨 2", "별첨N"), ("[별첨 3]", "별첨N"), ("<별표 1>", "별표N"), ("부록 A", "부록A"), ("부록Ⅱ", "부록A"), ("붙임 1.", "붙임N"),
    ("별지 제1호서식", "별지N"), ("Appendix A", "AppendixA"), ("APPENDIX II.", "AppendixA"), ("Annex 3", "AnnexN"), ("별첨", "별첨"), ("별첨1-2", "별첨N-N"), ("첨부 가", "첨부가")])
def test_name_of_gives_key(text, key):
    got = HB.name_of(f"  {text} ")
    assert got == (text, key) and HB.is_key(key)


@pytest.mark.parametrize("text", ["별첨자료", "부록의 내용", "부록의", "1.", "별첨 1 연구시설 활용계획서", "참고 1", "Appendixes", "", "제2장", "별첨 1234567890123456789012"])
def test_name_of_rejects(text):
    assert HB.name_of(text) is None


def test_is_key_only_name_keys():
    assert [k for k in ("별첨N", "부록A", "Appendix", "별첨N-N", "N.", "□", "[기관]", "[…]", "제목", "") if HB.is_key(k)] == ["별첨N", "부록A", "Appendix", "별첨N-N"]


# ---- ⓑ 띠 표 찾기 ------------------------------------------------------------------------------------------

def _cell(i, text, tbl, col, cells=3, rows=1, row=0, kind=None, outer=(), **more):
    """표 tbl 의 col 째 칸 문단 레코드(1단계 꼴 — 필요한 칸만). outer = 그 표를 품은 바깥 그릇 사슬(칸 안 표 · 글상자)."""
    cid = f"{tbl}c{row}_{col}"
    kind = kind or ("plain" if text.strip() else "empty")
    return {"id": f"p{i}", "n": i, "area": "cell", "table": tbl, "cell": cid, "kind": kind, "family": None, "shape": "", "letter": "", "rest": text.strip(), "text": text,
            "leadSpaces": 0, "fmt": "S9", "char": {"text": {"sizePt": 15.0, "bold": False}}, "blank": False, "spans": [], "objects": [],
            "path": [*outer, {"t": "tbl", "id": tbl, "rows": rows, "cols": cells, "cells": cells * rows, "host": f"h{tbl}"}, {"t": "cell", "id": cid, "row": row, "col": col}], **more}


def _band(i, tbl, name, title, mid=True):
    """1행 3칸 띠 표 — 이름표 칸 · 빈 칸 · 제목 칸(레코드 3개 — i, i+1, i+2)."""
    return [_cell(i, name, tbl, 0), _cell(i + 1, "" if mid else "가운데 글", tbl, 1), _cell(i + 2, title, tbl, 2)]


def test_find_band_table():
    paras = _band(0, "t1", "별첨1", " 연구시설 · 장비   구입 계획서") + [_cell(3, "별첨2", "t2", 0, cells=2), _cell(4, "", "t2", 1, cells=2)]
    got = HB.find(paras)
    assert got["p0"] == {"table": "t1", "host": "ht1", "cell": "t1c0_0", "letter": "별첨1", "key": "별첨N", "title": "p2", "titleCell": "t1c0_2", "text": "연구시설 · 장비 구입 계획서"}
    assert got["p3"]["title"] is None and got["p3"]["text"] == "" and list(got) == ["p0", "p3"]  # 이름표 칸뿐인 띠 표도


def test_find_skips_tables_that_are_not_bands():
    cases = {
        "글 있는 칸이 셋": _band(0, "t1", "별첨1", "제목", mid=False),
        "여러 행 표": [_cell(0, "별첨1", "t1", 0, rows=2), _cell(1, "제목", "t1", 1, rows=2), _cell(2, "", "t1", 0, rows=2, row=1)],
        "1칸 상자": [_cell(0, "별첨1", "t1", 0, cells=1)],
        "칸이 일곱": [_cell(0, "별첨1", "t1", 0, cells=7), _cell(1, "제목", "t1", 1, cells=7)],
        "칸 안 표": [_cell(0, "별첨1", "t1", 0, outer=({"t": "tbl", "id": "t0", "rows": 2, "cols": 2, "cells": 4}, {"t": "cell", "id": "c0"})), _cell(1, "제목", "t1", 2)],
        "글상자 안 표": [_cell(0, "별첨1", "t1", 0, outer=({"t": "shape", "key": 3},)), _cell(1, "제목", "t1", 2, outer=({"t": "shape", "key": 3},))],
        "이름표가 아님": _band(0, "t1", "구분", "제목"),
        "이름표 칸에 글 문단이 둘": [_cell(0, "별첨1", "t1", 0), _cell(1, "(양식)", "t1", 0), _cell(2, "제목", "t1", 2)],
        "이름표 칸이 둘": [_cell(0, "별첨1", "t1", 0), _cell(1, "별첨2", "t1", 2)],
        "제목이 너무 김": _band(0, "t1", "별첨1", "가" * 201),
        "칸에 개체": [_cell(0, "별첨1", "t1", 0), _cell(1, "제목", "t1", 2, objects=[{"t": "pic"}])],
    }
    for why, paras in cases.items():
        assert HB.find(paras) == {}, why
    assert HB.find(_band(0, "t1", "별첨1", "제목"), skip={"p2"}) == {}  # TEMP 문단이 든 표


# ---- ⓒ 그래프 ---------------------------------------------------------------------------------------------

def _body(i, letter, shape, family, text="", lead=0):
    return _rec(i, letter, shape, family, text, lead)


def _doc():
    """1. › 1-1. › (1) | 별첨1 띠 표 › □ › o · 1-2.(주 사슬 L2 — 띠 표 아래) | 별첨2 띠 표 | 2.(주 사슬 첫 레터 — 띠 표를 닫는다) › □."""
    paras = [_body(0, "1.", "N.", "decimal", "장"), _body(1, "1-1.", "N-N.", "hyphen", "절"), _body(2, "(1)", "(N)", "paren-num", "괄호", 1),
             *_band(3, "t1", "별첨1", "첫 별첨"),
             _body(6, "□", "□", "square", "네모"), _body(7, "o", "o", "latin-o", "동그라미", 1), _body(8, "1-2.", "N-N.", "hyphen", "별첨 안 절"),
             *_band(9, "t2", "별첨2", "[해당 기관별 작성] 둘째 별첨"),
             _body(12, "2.", "N.", "decimal", "다음 장"), _body(13, "□", "□", "square", "장 아래 네모")]
    return {"paras": paras, "labels": {"S1": {"name": "보통"}, "S9": {"name": "띠"}}}


def _a(st1, main=("N.", "N-N.", "(N)"), band_role="title"):
    """가짜 A — 띠 표 유형에는 일부러 틀린 답(제목 · 부모 (N))을 준다: 스크립트 규칙이 이긴다."""
    know = {"N.": ["root"], "N-N.": ["N."], "(N)": ["N-N."], "□": ["N.", "(N)"], "o": ["□"]}
    out = []
    for tid, t in HG.type_table(HG.candidates(st1)).items():
        if t["kind"] == HB.KIND:
            out.append({"type": tid, "role": band_role, "parents": ["(N)"], "variantOf": "", "basis": "", "reason": "틀린 답"})
        else:
            out.append({"type": tid, "role": "heading", "parents": know.get(t["shape"], []), "variantOf": "", "basis": "", "reason": ""})
    return {"types": out, "mainChain": list(main), "summary": "가짜"}


def _check(g):
    N = _nodes(g)
    assert [n["id"] for n in g["nodes"] if n["kind"] == HB.KIND] == ["p3", "p9"]
    b1, b2 = N["p3"], N["p9"]
    assert (b1["letter"], b1["text"], b1["flow"], b1["area"], b1["key"], b1["role"]) == ("별첨1", "첫 별첨", "body", "cell", "별첨N", "heading")
    assert b1["band"] == {"table": "t1", "title": "p5", "host": "ht1"} and b2["text"] == "[해당 기관별 작성] 둘째 별첨"
    assert [(b["parent"], b["template"], b["level"], b["heuristic"]) for b in (b1, b2)] == [("root", BAND, 1, False)] * 2  # 늘 문서 맨 위 · 제 템플릿 L1
    assert "band" not in N["p0"]
    # 띠 표 아래 줄 = 그 줄의 자식 — 템플릿·레벨은 문서 맨 위에 매달린 줄처럼(띠 표 템플릿은 L1 하나뿐)
    assert (N["p6"]["parent"], N["p6"]["template"], N["p6"]["level"]) == ("p3", "body:□›o", 1)
    assert (N["p7"]["parent"], N["p7"]["template"], N["p7"]["level"]) == ("p6", "body:□›o", 2)
    assert (N["p8"]["parent"], N["p8"]["template"], N["p8"]["level"]) == ("p3", MAIN, 2)  # 주 사슬 레터 — 잇닿은 사슬(L2)
    # 주 사슬 첫 레터(장)는 띠 표를 닫고 문서 맨 위로
    assert (N["p12"]["parent"], N["p12"]["template"], N["p12"]["level"]) == ("root", MAIN, 1)
    assert N["p13"]["parent"] == "p12"
    t = {x["anchor"]: x for x in g["templates"]}
    band = t[BAND]
    assert (band["kind"], band["chain"], band["instances"], band["where"]) == ("band", ["별첨N"], 2, [{"parent": "root", "count": 2}])
    assert band["no"] == len(g["templates"]) and [x["kind"] for x in g["templates"]][:2] == ["main", "branch"]  # 번호는 맨 뒤(있던 템플릿을 밀지 않는다)
    assert [s["level"] for s in band["slots"]] == [1] and band["slots"][0]["count"] == 2
    assert t[MAIN]["chain"] == ["N.", "N-N.", "(N)"]
    return N


def test_band_lines_without_llm():
    g = HG.build(_doc(), use_llm=False)
    _check(g)
    assert g["llm"]["mainChain"][0] == "N."  # 띠 표 줄·그 아래 줄은 주 사슬 첫 레터 셈에 들지 않는다


def test_band_lines_ignore_llm_answers():
    """A 가 띠 표 유형을 제목·(N) 아래로 답하고 B 가 띠 표 줄의 부모·역할을 바꾸려 해도 스크립트 규칙 그대로다(B 의 그 변경은 버림)."""
    st1 = _doc()
    b = lambda job, d: _res({"changes": [{"id": "p9", "parent": "p3", "role": "not_heading", "template": "", "level": 0, "reason": "별첨1 의 것"}], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(_a(st1)), heading_section=b))
    _check(g)
    assert {"id": "p9", "why": "별첨·부록 표 제목 줄 — 스크립트가 정한다"} in g["rejected"] and not g["changes"]  # 화면에 보이는 글 — 「띠 표」 는 코드·사양서의 말
    ty = next(x for x in g["types"] if x["kind"] == HB.KIND)
    assert (ty["role"], ty["parents"], ty["key"], ty["shape"]) == ("heading", ["root"], "별첨N", "별첨N")
    assert g["llm"]["mainChainFixed"]


def test_band_key_never_joins_main_chain():
    st1 = _doc()
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(_a(st1, main=("별첨N", "N.", "N-N.", "(N)")))))
    assert g["llm"]["mainChainRejected"] == ["별첨N", "N.", "N-N.", "(N)"] and not g["llm"]["mainChainFixed"]
    N = _nodes(g)
    assert (N["p3"]["template"], N["p3"]["level"]) == (BAND, 1) and next(t for t in g["templates"] if t["kind"] == "main")["chain"][0] == "N."


def test_other_name_is_other_template():
    """이름말이 다르면 키가 다르다 — 「부록 A」 띠 표는 「별첨N」 과 다른 템플릿이고 서로 형제다(뒤 띠 표가 앞 띠 표 아래로 들지 않는다)."""
    st1 = {"paras": [*_band(0, "t1", "별첨1", "하나"), *_band(3, "t2", "부록 A", "둘"), _body(6, "□", "□", "square", "네모")], "labels": {}}
    g = HG.build(st1, use_llm=False)
    N = _nodes(g)
    assert [(N[p]["parent"], N[p]["template"]) for p in ("p0", "p3")] == [("root", "body:별첨N"), ("root", "body:부록A")] and N["p6"]["parent"] == "p3"
    assert [t["kind"] for t in g["templates"]] == ["branch", "band", "band"]  # 띠 표 아래 줄은 주 사슬 첫 레터 셈에 들지 않는다 — □ 는 가지 템플릿


def test_lines_under_band_are_not_offered_as_dependent_template():
    """별첨 아래에만 오는 가지 템플릿(「□」)을 띠 표 템플릿의 종속 템플릿으로 제안하지 않는다(사용자 답 「제 템플릿으로」 — 별첨 아래 □ = 제 템플릿 L1). 조정의 「모두 반영」 이 저절로 걸지 않게."""
    from app import outline_match as OM
    st1 = {"paras": [_body(0, "1.", "N.", "decimal", "장"), *_band(1, "t1", "별첨1", "하나"), _body(4, "□", "□", "square", "네모"),
                     *_band(5, "t2", "별첨2", "둘"), _body(8, "□", "□", "square", "네모 둘")], "labels": {}}
    g = HG.build(st1, use_llm=False)
    g["meta"] = {"run": 1, "at": 0}
    text = {r["id"]: r["text"] for r in st1["paras"]}
    ov = OE.build_overlay(g, lambda pid: {"text": text[pid], "attrs": {"para": "1", "char": "1"}, "spacer": None} if pid in text else None)
    band = next(tid for tid, t in ov["templates"].items() if t["kind"] == OE.BAND)
    assert [ov["lines"][p]["parent"] for p in ("p4", "p8")] == ["p1", "p5"] and ov["branches"][f"{band}|1"]
    assert OM.merge_hints(ov) == []
    sq = ov["lines"]["p4"]["tpl"]
    for child, parent in ((sq, band), (band, sq)):  # 손으로도 못 건다 — 띠 표 템플릿은 종속 템플릿의 부모도 자식도 아니다
        with pytest.raises(ValueError, match="별첨·부록 표 제목 템플릿"):
            OM.merge(copy.deepcopy(ov), child, parent, 1)
    ov["templates"][band]["kind"] = "branch"  # 띠 표 템플릿이 아니라면 제안됐을 자리다
    assert [(h["parent"], h["at"]) for h in OM.merge_hints(ov)] == [(band, 1)]


# ---- ⓓ 샘플 문서 · ⓔ 오버레이 ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rnd():
    doc = HwpxDoc(RND.read_bytes())
    st1 = E.extract(doc, store=copy.deepcopy(EMPTY), doc_key="rnd")
    g = HG.build(st1, use_llm=False)
    g["meta"] = {"run": 1, "at": 0}

    def probe(pid):
        el = doc._ids.get(pid)
        return None if el is None else {"text": doc._text(el), "attrs": doc.para_attrs(pid), "spacer": None}
    return doc, g, OE.build_overlay(g, probe)


def test_sample_appendix_bands(rnd):
    """연구개발계획서 양식 — 「별첨1」~「별첨9」 띠 표(1행 3칸) 아홉이 맨 뒤 번호의 띠 표 템플릿 L1 이고 문서 맨 위의 줄이다."""
    _, g, _ = rnd
    bands = [n for n in g["nodes"] if n["kind"] == HB.KIND]
    assert [n["letter"] for n in bands] == [f"별첨{i}" for i in range(1, 10)]
    assert {(n["parent"], n["template"], n["level"], n["role"], n["flow"]) for n in bands} == {("root", BAND, 1, "heading", "body")}
    assert bands[1]["text"] == "시약·재료구입 및 활용계획서" and bands[4]["text"].startswith("[해당 기관별 작성]")
    t = g["templates"][-1]
    assert (t["kind"], t["anchor"], t["instances"], t["no"]) == ("band", BAND, 9, len(g["templates"]))
    N = _nodes(g)
    assert N[bands[4]["band"]["title"]]["role"] == "label" and N[bands[4]["band"]["title"]]["flow"].startswith("cell:")  # 제목 칸의 대괄호 줄은 전처럼 칸 안 구분 라벨
    kids = [n for n in g["nodes"] if n["parent"] == bands[3]["id"]]  # 별첨4 아래 — □ 과제개요 …
    assert kids and all(k["template"] != BAND for k in kids) and "□" in {k["key"] for k in kids}


def test_overlay_band_lines_are_table_lines(rnd):
    doc, g, ov = rnd
    tid = str(g["templates"][-1]["id"])
    t = ov["templates"][tid]
    assert (t["kind"], t["chain"], t["max"]) == (OE.BAND, ["별첨N"], 1)
    sl = t["slots"]["1"]
    assert (sl["table"], sl["name"], sl["letter"], sl["prefix"], sl["attrs"]) == (True, "별첨N", "", None, None)
    lines = {p: x for p, x in ov["lines"].items() if x["tpl"] == tid}
    assert len(lines) == 9 and sl["rep"] in lines
    first = next(iter(lines.values()))
    assert (first["role"], first["letter"], first["name"], first["key"], first["level"], first["parent"]) == (OE.TABLE, "", "별첨1", "별첨N", 1, None)
    assert first["table"] and first["title"] and OE.line_view(first)["name"] == "별첨1"
    assert any(x.get("parent") in lines for x in ov["lines"].values()) and ov["branches"].get(f"{tid}|1")  # 별첨 아래 줄 · 그 레벨에 매달린 템플릿
    # 이름표 글을 고쳐도 줄이 남는다(표 줄은 문단이 살아 있는지만 본다)
    assert not set(OE.sync(copy.deepcopy(ov), lambda p: True, lambda p: "고친 글")) & set(lines)
    # 개요 편집 — 띠 표 줄은 Enter 로 새 줄을 만들 레벨이 없고 그 밖의 키는 거절
    pid = next(iter(lines))
    seq = [{"id": pid, "text": "별첨1", "blank": False, "object": True}]
    with pytest.raises(ValueError, match="표 제목 아래 레벨이 없습니다"):
        OE.plan_enter(seq, 0, 0, None, ov, lambda p: "별첨1")
    with pytest.raises(ValueError, match="Enter"):
        OE._check_line(ov, pid, "level")
    # 「표를 L1 으로」 는 띠 표 템플릿에 못 건다
    assert "별첨·부록 표 제목 템플릿" in outline_lift._blocked(ov, tid)
    with pytest.raises(ValueError, match="별첨·부록 표 제목 템플릿"):
        outline_lift.lift(doc, copy.deepcopy(ov), tid)
    assert outline_lift.host_of(doc, ov, pid, None) is not None and doc._rev.get(outline_lift.host_of(doc, ov, pid, None)) != pid  # 본문 자리 = 그 표를 품은 문단
