"""TEMP 라벨(spec_헤딩_추출 ② §15, 2026-11-10 사용자 「테이블에서 작성요령이나 향후 작성되어야 할 것들은 … TEMP 라벨을 줘서 작업을 하지 않도록 하고 향후 삭제할 수 있도록」).
판정 규칙(작성 요령 표 · 안내 상자 · 안내 칸 · 지시문 · 빈 글머리 줄 · 사용자 지정/해제) · 2단계 후보에서 빠짐 · 3단계 TEMP 표 빠짐 · 지정 → LLM 없는 다시 셈 · 문서에서 지우기(실행 취소)."""
import gzip
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, heading_tables as HT, heading_temp as TP, server, works
from app.hwpx_doc import HwpxDoc

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
EMPTY = {"version": 0, "rules": [], "builtin": {}, "keeps": [], "lastId": 0}


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


# ---- 합성 1단계 레코드 ------------------------------------------------------------------------------------------

def _tbl(tid, cells, rows=2, cols=2, host=None):
    return {"t": "tbl", "id": tid, "key": int(tid[1:]), "cells": cells, "rows": rows, "cols": cols, "host": host}


def _cell(cid, row=0, col=0):
    return {"t": "cell", "id": cid, "key": int(cid[1:]) + 1000, "row": row, "col": col, "rs": 1, "cs": 1, "fill": None}


class _Doc:
    """문단을 차례로 쌓는다 — add(글, 그릇 사슬, kind=…) → 문단 id."""

    def __init__(self):
        self.paras = []

    def add(self, text, path=(), kind=None, family=None, blank=False, block=True):
        path = list(path)
        if kind is None:
            kind = "empty" if not text.strip() else "note" if text.lstrip().startswith("※") else "plain"
        cells = [c for c in path if c["t"] == "cell"]
        tbls = [c for c in path if c["t"] == "tbl"]
        box = bool(tbls) and tbls[-1]["cells"] == 1
        i = len(self.paras)
        letter = text.split(" ", 1)[0] if kind in ("marker", "label") else ""
        rest = text[len(letter):].strip() if letter else text
        self.paras.append({"id": f"p{i}", "n": i, "block": block, "area": ("box" if box else "cell") if cells else "body", "path": path,
                           "table": tbls[-1]["id"] if tbls else None, "cell": cells[-1]["id"] if cells else None, "kind": kind, "family": family,
                           "shape": letter, "letter": letter, "rest": rest, "text": text, "blank": blank, "ord": None, "leadSpaces": 0, "fmt": "S1",
                           "char": {"text": {"sizePt": 10.0, "bold": False}},
                           "spans": [{"i": 0, "line": 0, "kind": kind, "family": family, "letter": letter}]})
        return f"p{i}"

    def stage1(self):
        return {"paras": self.paras, "labels": {"S1": {"name": "보통"}}}


def _items(t):
    return {it["id"]: it for it in t["items"]}


def _guide_doc():
    """본문 헤딩 · 작성 요령 표(안에 상자) · 보통 표(지시문·쓸 자리·값 칸) · 안내 상자 · 제목 상자."""
    d = _Doc()
    ids = {}
    ids["h1"] = d.add("1. 개요", kind="marker", family="decimal")
    ids["b1"] = d.add("o 내용", kind="marker", family="latin-o")
    ids["bodyblank"] = d.add("o", kind="marker", family="latin-o", blank=True)          # 본문의 빈 글머리 — 개요템플릿의 뼈대(TEMP 아님)
    ids["bodynote"] = d.add("※ 본문 안내는 12pt 로 작성합니다.")                           # 본문의 안내 — 대상 아님
    ids["host1"] = d.add("", kind="object")
    g = _tbl("t1", 3, host=ids["host1"])                                                  # 작성 요령 표
    ids["g_title"] = d.add("작성 요령", [g, _cell("c1", 0, 0)])
    ids["g_note"] = d.add("연구개발계획서 작성 후 작성 요령 표는 삭제", [g, _cell("c2", 0, 1)])
    c3 = _cell("c3", 1, 0)
    ids["g_b1"] = d.add("◦ 개발 대상 기술의 개요", [g, c3], kind="marker", family="circle")
    ids["g_b2"] = d.add("- 기본 개념도로 작성", [g, c3], kind="marker", family="dash")
    ids["g_boxhost"] = d.add("", [g, c3], kind="object")
    box = _tbl("t2", 1, 1, 1, host=ids["g_boxhost"])
    ids["g_box"] = d.add("※ AI 관련 과제는 아래를 고려하여 작성 요망", [g, c3, box, _cell("c4")])
    ids["host2"] = d.add("", kind="object")
    t = _tbl("t3", 8, rows=4, cols=2, host=ids["host2"])                                  # 보통 표
    ids["t_head"] = d.add("구분", [t, _cell("c5", 0, 0)])
    ids["t_code"] = d.add("급여총액", [t, _cell("c6", 0, 1)])
    ids["t_codeA"] = d.add("(A)", [t, _cell("c6", 0, 1)], kind="marker", family="paren-alpha", blank=True)   # 헤더 칸의 코드 — 값
    c7 = _cell("c7", 1, 0)
    ids["t_lab"] = d.add("[1차년도 목표]", [t, c7], kind="label", family="bracket-label")
    ids["t_blank1"] = d.add("ㅇ", [t, c7], kind="marker", family="jamo-o", blank=True)     # 쓸 자리
    ids["t_lab2"] = d.add("[2차년도 목표]", [t, c7], kind="label", family="bracket-label")
    ids["t_blank2"] = d.add("ㅇ ", [t, c7], kind="marker", family="jamo-o", blank=True)
    c8 = _cell("c8", 1, 1)
    ids["t_stage"] = d.add("[1단계 목표]", [t, c8], kind="label", family="bracket-label")
    ids["t_instr"] = d.add("ㅇ 연구개발기간이 단계로 구분된 경우 작성합니다.", [t, c8], kind="marker", family="jamo-o")   # 지시문
    ids["t_dash"] = d.add("-", [t, _cell("c9", 2, 0)], kind="marker", family="dash", blank=True)       # 칸에 홀로 — 대시 값
    ids["t_num"] = d.add("1.", [t, _cell("c10", 2, 1)], kind="marker", family="decimal", blank=True)   # 순번 칸
    c11 = _cell("c11", 3, 0)
    ids["t_gnote"] = d.add("※ 작성 시 유의 사항", [t, c11])                                # 안내 칸(안내 + 아래 줄)
    ids["t_gline"] = d.add("- 천원 단위로 적음", [t, c11], kind="marker", family="dash")
    ids["t_oath"] = d.add("위와 같이 증빙서류를 제출합니다.", [t, _cell("c12", 3, 1)])       # 다짐 글 — 지시문 아님
    ids["host3"] = d.add("", kind="object")
    nb = _tbl("t4", 1, 1, 1, host=ids["host3"])                                           # 안내 상자(본문)
    ids["nb1"] = d.add("※ ①효율적인 수행을 위해 AI 를 활용하는 경우", [nb, _cell("c13")])
    ids["nb2"] = d.add("o", [nb, _cell("c13")], kind="marker", family="latin-o", blank=True)
    ids["host4"] = d.add("", kind="object")
    tb = _tbl("t5", 1, 1, 1, host=ids["host4"])                                           # 제목 상자 — TEMP 아님
    ids["tb1"] = d.add("기술준비도(TRL) 목표", [tb, _cell("c14")])
    ids["tb2"] = d.add("o", [tb, _cell("c14")], kind="marker", family="latin-o", blank=True)   # 본문 흐름(상자는 투명)의 빈 글머리 — TEMP 아님
    ids["host5"] = d.add("", kind="object")
    fb = _tbl("t6", 1, 1, 1, host=ids["host5"])                                           # 「*」 각주로 시작하는 상자 — TEMP 아님
    ids["fb1"] = d.add("* 신규 채용 구분 : 청년인력", [fb, _cell("c15")], kind="footnote", family="footnote")
    return d, ids


# ---- 판정 규칙 -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("line, want", [
    ("작성 요령", True), ("작성요령", True), ("작성요령(계속)", True), ("< 작성요령 >", True), ("【작성 방법】", True), ("※ 작성 가이드라인", True),
    ("앞표지 작성 요령(작성 요령은 삭제 후 제출합니다.)", True), ("작성 지침 :", True),
    ("연구개발계획서 작성 후 작성 요령 표는 삭제", False), ("작성 요령을 참고하여 선택적으로 작성", False), ("평가 방법", False), ("작성일", False), ("작성자 성명", False)])
def test_guide_title_line(line, want):
    assert bool(TP._GUIDE_TITLE.match(line)) is want


@pytest.mark.parametrize("text, want", [
    ("ㅇ 연구개발기간이 단계로 구분된 경우 작성합니다.", True), ("※ 요약문은 5쪽 이내로 작성합니다.", True), ("* 직접 관계에 대한 내용을 기재할 것", True),
    ("해당 시 기재 요망", True), ("[√] 표시합니다", True), ("세부 내용을 서술하십시오.", True),
    ("[기술도입비 현물산정]을 위해 증빙서류를 제출합니다.", False), ("관련 서류를 첨부합니다.", False), ("- 최종보고서를 작성함", False), ("o 사업화 형태 :", False),
    ("작성합니다만 예외가 있음", False)])
def test_instruction_ending(text, want):
    assert bool(TP._INSTRUCT.search(text)) is want


def test_label_rules_on_synthetic_document():
    d, ids = _guide_doc()
    t = TP.label(d.stage1())
    it = _items(t)
    assert set(it) == {"tbl:t1", "tbl:t4", "cell:c11", f"para:{ids['t_instr']}", f"para:{ids['t_blank1']}", f"para:{ids['t_blank2']}"}
    g = it["tbl:t1"]
    assert (g["unit"], g["why"], g["rule"], g["by"], g["text"], g["paras"], g["candidates"], g["block"]) == ("table", "guide", "guide_table", "script", "작성 요령", 6, 2, True)
    assert g["rows"] == 2 and g["cols"] == 2 and g["box"] is False and g["para"] == ids["g_title"] and g["host"] == ids["host1"]
    assert t["tables"] == {"t1": "tbl:t1", "t2": "tbl:t1", "t4": "tbl:t4"}          # 작성 요령 표 안의 상자도 TEMP 표 · 따로 항목은 아님
    assert (it["tbl:t4"]["rule"], it["tbl:t4"]["box"], it["tbl:t4"]["paras"]) == ("guide_box", True, 2)
    assert (it["cell:c11"]["rule"], it["cell:c11"]["unit"], it["cell:c11"]["paras"], it["cell:c11"]["table"]) == ("guide_cell", "cell", 2, "t3")
    assert (it[f"para:{ids['t_instr']}"]["rule"], it[f"para:{ids['t_instr']}"]["why"]) == ("guide_line", "guide")
    assert (it[f"para:{ids['t_blank1']}"]["rule"], it[f"para:{ids['t_blank1']}"]["why"], it[f"para:{ids['t_blank1']}"]["cell"]) == ("blank", "todo", "c7")
    covered = set(t["paras"])
    assert {ids[k] for k in ("g_title", "g_note", "g_b1", "g_b2", "g_boxhost", "g_box", "nb1", "nb2", "t_gnote", "t_gline", "t_instr", "t_blank1", "t_blank2")} == covered
    # TEMP 아님: 본문 헤딩·빈 글머리·안내 · 헤더 칸의 코드 · 칸에 홀로 있는 대시·순번 · 다짐 글 · 괄호 줄 · 제목 상자·각주 상자
    for k in ("h1", "b1", "bodyblank", "bodynote", "t_head", "t_code", "t_codeA", "t_lab", "t_lab2", "t_stage", "t_dash", "t_num", "t_oath", "tb1", "tb2", "fb1", "host1"):
        assert ids[k] not in covered, k
    c = t["counts"]
    assert (c["items"], c["tables"], c["cells"], c["lines"], c["paras"], c["user"], c["off"]) == (6, 2, 1, 3, 13, 0, 0)
    assert c["byRule"] == {"guide_table": 1, "guide_box": 1, "guide_cell": 1, "guide_line": 1, "blank": 2}
    assert c["byWhy"]["guide"]["items"] == 4 and c["byWhy"]["todo"] == {"items": 2, "paras": 2, "candidates": 2, "para": 2}
    assert [x["id"] for x in t["items"]] == sorted(it, key=lambda i: it[i]["n"])     # 문서 순
    assert "작성 요령 표 1" in TP.summary_text(t) and "빈 글머리 줄 2" in TP.summary_text(t) and TP.summary_text(TP.label({"paras": []})) == "TEMP 없음"


def test_label_user_hints_on_off_and_gone():
    d, ids = _guide_doc()
    s1 = d.stage1()
    hints = {"version": 3, "set": {
        "tbl:t1": {"state": "off"},                                # 작성 요령 표 해제 — 안의 상자·글머리에도 자동 규칙이 안 듣는다
        f"para:{ids['bodynote']}": {"state": "on"},                # 본문 문단을 TEMP 로
        "cell:c12": {"state": "on", "why": "todo"},                # 칸을 TEMP 로(까닭 쓸 자리)
        "tbl:t5": {"state": "on"},                                 # 제목 상자를 TEMP 로
        f"para:{ids['t_blank1']}": {"state": "off"},               # 빈 글머리 줄 하나 해제
        "para:p999": {"state": "on"}, "bogus": {"state": "on"}, "tbl:t3": {"state": "maybe"}}}
    t = TP.label(s1, hints)
    it = _items(t)
    assert "tbl:t1" not in it and not any(ids[k] in t["paras"] for k in ("g_title", "g_b1", "g_box")) and "t2" not in t["tables"]
    assert (it[f"para:{ids['bodynote']}"]["by"], it[f"para:{ids['bodynote']}"]["rule"], it[f"para:{ids['bodynote']}"]["why"]) == ("user", "user", "guide")
    assert (it["cell:c12"]["by"], it["cell:c12"]["why"], it["cell:c12"]["paras"]) == ("user", "todo", 1)
    assert it["tbl:t5"]["by"] == "user" and t["tables"]["t5"] == "tbl:t5" and ids["tb2"] in t["paras"]
    assert f"para:{ids['t_blank1']}" not in it and f"para:{ids['t_blank2']}" in it
    assert t["off"] == sorted(["tbl:t1", f"para:{ids['t_blank1']}"]) and t["gone"] == ["para:p999"] and t["hintsVersion"] == 3
    assert (t["counts"]["user"], t["counts"]["off"]) == (3, 2)
    assert TP.clean_hints(hints)["set"].keys() == {"tbl:t1", f"para:{ids['bodynote']}", "cell:c12", "tbl:t5", f"para:{ids['t_blank1']}", "para:p999"}
    assert TP.clean_hints(None) == {"version": 0, "set": {}} and TP.clean_hints({"version": "x", "set": []}) == {"version": 0, "set": {}}
    # 이미 TEMP 표 안인 문단을 지정해도 따로 항목이 되지 않는다(큰 단위가 덮음)
    t2 = TP.label(s1, {"set": {f"para:{ids['g_b1']}": {"state": "on"}}})
    assert f"para:{ids['g_b1']}" not in _items(t2) and t2["paras"][ids["g_b1"]] == "tbl:t1"
    # 해제한 칸 안의 상자·줄에도 자동 규칙이 안 듣는다
    d2 = _Doc()
    host = d2.add("", kind="object")
    outer, c20 = _tbl("t10", 2, rows=1, cols=2, host=host), _cell("c20")
    d2.add("구분", [outer, _cell("c21", 0, 1)])
    bh = d2.add("", [outer, c20], kind="object")
    d2.add("※ 아래를 참고하여 작성", [outer, c20, _tbl("t11", 1, 1, 1, host=bh), _cell("c22")])
    d2.add("o 해당 시 기재합니다.", [outer, c20], kind="marker", family="latin-o")
    assert set(_items(TP.label(d2.stage1()))) == {"tbl:t11", "para:p4"}
    assert TP.label(d2.stage1(), {"set": {"cell:c20": {"state": "off"}}})["items"] == []
    # 칸을 TEMP 로 지정하면 그 칸 안의 표·상자도 TEMP 표(3단계가 건너뛸 문단 = TEMP 표 안의 문단)
    d3 = _Doc()
    host = d3.add("", kind="object")
    outer, c30 = _tbl("t20", 2, rows=1, cols=2, host=host), _cell("c30")
    d3.add("구분", [outer, _cell("c31", 0, 1)])
    ih = d3.add("", [outer, c30], kind="object")
    inner = _tbl("t21", 2, rows=1, cols=2, host=ih)
    d3.add("예시 항목", [outer, c30, inner, _cell("c32")])
    d3.add("예시 값", [outer, c30, inner, _cell("c33", 0, 1)])
    d3.add("o 예시 설명", [outer, c30], kind="marker", family="latin-o")
    assert TP.label(d3.stage1())["items"] == []
    tc = TP.label(d3.stage1(), {"set": {"cell:c30": {"state": "on"}}})
    assert set(_items(tc)) == {"cell:c30"} and tc["tables"] == {"t21": "cell:c30"} and tc["tableParas"] == ["p3", "p4"] and set(tc["paras"]) == {"p2", "p3", "p4", "p5"}
    skip, listed = HT.temp_tables(tc)
    assert skip == {"p3", "p4"} and listed == [{"id": "t21", "item": "cell:c30", "why": "guide", "rule": "user", "rows": None, "cols": None, "n": None, "host": None}]
    # 표 단위가 먼저 — 지정한 칸 안의 안내 상자는 제 항목으로 남고(tbl:t11), 칸 항목은 나머지를 덮는다
    assert set(_items(TP.label(d2.stage1(), {"set": {"cell:c20": {"state": "on"}}}))) == {"tbl:t11", "cell:c20"}
    assert HT.temp_tables(None) == (frozenset(), []) and TP.label(s1)["tableParas"] == sorted(ids[k] for k in ("g_title", "g_note", "g_b1", "g_b2", "g_boxhost", "g_box", "nb1", "nb2"))
    assert TP.block_text(s1, "table", "t1") == "작성 요령" and TP.block_text(s1, "cell", "c7") == "[1차년도 목표]" and TP.block_text(s1, "para", ids["h1"]) == "1. 개요"
    assert TP.block_text(s1, "table", "t99") is None and TP.block_text(s1, "para", ids["host1"]) == ""
    assert TP.split_id("tbl:t1") == ("table", "t1") and TP.split_id("x:1") == (None, None) and TP.split_id(None) == (None, None) and TP.split_id("para:") == (None, None)


# ---- 2단계 · 3단계 — TEMP 는 후보·표 구조에서 빠진다 ---------------------------------------------------------------

def test_stage2_candidates_skip_temp():
    d, ids = _guide_doc()
    s1 = d.stage1()
    t = TP.label(s1)
    g0 = HG.build(s1, use_llm=False)
    g1 = HG.build(s1, use_llm=False, temp=t)
    n0, n1 = {n["para"] for n in g0["nodes"]}, {n["para"] for n in g1["nodes"]}
    assert {ids[k] for k in ("g_b1", "g_b2", "t_instr", "t_blank1", "t_blank2", "t_gline", "nb2")} <= n0     # TEMP 없이는 모두 헤딩 후보
    assert n0 - n1 == {ids[k] for k in ("g_b1", "g_b2", "t_instr", "t_blank1", "t_blank2", "t_gline", "nb2")} and not n1 & set(t["paras"])
    assert {ids[k] for k in ("h1", "b1", "bodyblank", "t_lab", "t_lab2", "t_stage", "tb2")} <= n1   # 나머지는 그대로
    assert not {ids["t_dash"], ids["t_num"]} & (n0 | n1)   # 채워진 표의 칸에 혼자 있는 「-」·「1.」 = 값 칸 — TEMP 가 아니어도 헤딩 후보가 아니다(spec_헤딩_추출 ② §6 「값 칸」 2026-11-16)
    assert g0["temp"] is None and g1["temp"]["items"] == [x["id"] for x in t["items"]] and g1["temp"]["counts"]["items"] == 6
    assert len(g1["templates"]) < len(g0["templates"])                                   # 작성 요령 칸에만 있던 템플릿이 사라진다
    assert TP.same_items(g1["temp"], t) and not TP.same_items(g0["temp"], t) and TP.same_items(None, TP.label({"paras": []}))


@pytest.fixture(scope="module")
def rnd1():
    return E.extract(HwpxDoc(RND.read_bytes()), store=EMPTY)


def test_form_counts_and_stage3_skips_temp_tables(rnd1):
    t = TP.label(rnd1)
    c = t["counts"]
    assert c["byRule"] == {"guide_table": 30, "guide_box": 1, "guide_line": 6, "blank": 15} and (c["items"], c["tables"], c["lines"]) == (52, 31, 21)
    assert c["paras"] == 730 and c["candidates"] == 394 and c["byWhy"]["todo"]["items"] == 15
    it = _items(t)
    assert it["tbl:t996"]["text"] == "작성 요령" and it["tbl:t494"]["text"].startswith("앞표지 작성 요령") and it["tbl:t12521"]["text"] == "작성요령(계속)"
    assert it["tbl:t956"]["rule"] == "guide_box" and it["para:p707"]["rule"] == "guide_line" and it["para:p684"]["rule"] == "blank"
    by = {r["id"]: r for r in rnd1["paras"]}
    assert all(by[x["para"]]["letter"].strip() in ("o", "ㅇ") for x in t["items"] if x["rule"] == "blank")   # 「-」「1.」「(A)」 값 칸은 아님
    assert "para:p12678" not in it                                                        # 「… 증빙서류를 제출합니다.」 — 신청서의 다짐 글
    t0 = HT.build(rnd1, use_llm=False)
    t1 = HT.build(rnd1, use_llm=False, temp=t)
    ids0, ids1 = {x["id"] for x in t0["tables"]}, {x["id"] for x in t1["tables"]}
    temp_ids = set(t["tables"])
    assert ids0 - ids1 == {i for i in temp_ids if i in ids0} and len(ids0 - ids1) >= 30 and not ids1 & temp_ids
    assert {x["id"] for x in t1["tempTables"]} == temp_ids and t1["counts"]["tempTables"] == len(temp_ids) and t0["tempTables"] == [] and t0["temp"] is None
    tt = {x["id"]: x for x in t1["tempTables"]}
    assert (tt["t996"]["item"], tt["t996"]["why"], tt["t996"]["rule"], tt["t996"]["rows"], tt["t996"]["cols"]) == ("tbl:t996", "guide", "guide_table", 2, 2)
    assert not any(n in temp_ids for x in t1["tables"] for cell in x["cells"] for n in cell.get("nested") or [])   # 바깥 칸의 「칸 안 표」 에도 없다
    b0, b1 = ({x["id"]: x["before"] for x in r["tables"]}["t572"] for r in (t0, t1))      # 표 앞 문단(제목 맥락)도 TEMP 표 안의 글은 건너뛴다
    assert "기관장 서명" in b0 and b1 and "기관장 서명" not in b1 and "작성" not in b1
    assert TP.same_tables(t1, t) and not TP.same_tables(t0, t)
    g = HG.build(rnd1, use_llm=False, temp=t)
    assert not {n["para"] for n in g["nodes"]} & set(t["paras"])
    g0 = HG.build(rnd1, use_llm=False)
    assert len(g0["nodes"]) - len(g["nodes"]) >= 394 and len(g["templates"]) < len(g0["templates"])


# ---- 실행 · API — 양식(LLM 끔) ------------------------------------------------------------------------------------

@pytest.fixture
def c():
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)
    server.DOCS.clear()


def _open(c):
    r = c.post("/api/docs", files={"file": (RND.name, RND.read_bytes())})
    d = r.json()["docId"]
    return d, server.DOCS[d]


def _graph(c, d):
    return c.get(f"/api/docs/{d}/headings/graph").json()


def test_temp_api_lists_designates_and_reextracts_without_llm(c):
    d, s = _open(c)
    v = c.get(f"/api/docs/{d}/headings/temp").json()
    assert v["items"] == [] and v["key"] is None and v["version"] == 0 and v["stage2"] is None and c.get(f"/api/docs/{d}/headings").json()["temp"] is None
    assert c.put(f"/api/docs/{d}/headings/temp", json={"id": "tbl:t996", "state": "off"}).status_code == 400      # 1단계 결과가 아직 없음
    j1 = heading_runs.run_sync(s, 1, False)
    assert [x["name"] for x in j1.view()["steps"]][-1] == "TEMP 라벨" and "작성 요령 표 30" in j1.view()["steps"][-1]["msg"]
    j2 = heading_runs.run_sync(s, 2, False)
    steps2 = j2.view()["steps"]   # 연구개발과제 문서는 「구분 기준 판독」 이 먼저(spec_구분_기준 ② §23) — 그 다음이 TEMP 라벨
    assert [x["name"] for x in steps2][0] == "구분 기준 판독" and steps2[1]["name"].startswith("TEMP 라벨") and "헤딩 후보 394" in steps2[1]["msg"]
    j3 = heading_runs.run_sync(s, 3, False)
    nt = len(heading_runs.temp_label(s)["tables"])                                        # TEMP 표 = 항목 31(작성 요령 표 30 + 안내 상자 1) + 그 안쪽 표·상자
    assert nt > 31 and [x["name"] for x in j3.view()["steps"]][0].startswith("TEMP 라벨") and f"TEMP 표 {nt} 뺌" in j3.view()["steps"][-1]["msg"]
    v = c.get(f"/api/docs/{d}/headings/temp").json()
    assert v["counts"]["items"] == 52 and v["stale"] is False and v["stage2"]["tempStale"] is False and v["stage3"]["tempStale"] is False and v["off"] == []
    it = {x["id"]: x for x in v["items"]}
    assert it["tbl:t996"]["block"] is True and it["tbl:t996"]["para"].startswith("p")
    st = c.get(f"/api/docs/{d}/headings").json()
    assert st["temp"]["counts"]["items"] == 52 and st["temp"]["key"] == v["key"] and st["temp"]["text"].startswith("TEMP 52항목")
    assert st["stage2"]["tempStale"] is False and st["stage3"]["tempStale"] is False and st["stage3"]["tempTables"] == nt
    assert "t996" not in {x["id"] for x in st["stage3"]["tables"]}
    g0 = _graph(c, d)
    n0 = {n["id"]: (n["role"], n["key"], n["parent"], n["tplNo"], n["level"]) for n in g0["nodes"]}
    assert not [n for n in g0["nodes"] if n["flow"] == "cell:c1001"] and "p684" not in n0 and "p707" not in n0 and "p683" in n0   # 작성 요령 칸 · 쓸 자리 · 지시문은 노드 없음
    assert g0["temp"]["counts"]["items"] == 52
    # 잘못된 값 — 400
    for body in ({"id": "t996", "state": "off"}, {"id": "tbl:t996", "state": "delete"}, {"id": "tbl:t99999", "state": "on"}, {"id": "para:p1", "state": "on", "why": "x"}, {},
                 {"id": "cell:c1001", "state": "off"},      # 해제는 항목 단위 — TEMP 표 안의 칸만 따로 풀 수 없다
                 {"id": "para:p683", "state": "off"},       # TEMP 가 아닌 문단
                 {"id": "para:x0.3", "state": "on"}):       # 웹 블록이 없는 자리 번호
        assert c.put(f"/api/docs/{d}/headings/temp", json=body).status_code == 400, body
    assert c.get(f"/api/docs/{d}/headings/temp").json()["version"] == 0
    # 해제 — 저장 + 2단계를 곧바로 다시 셈(새 실행, LLM 호출 없음): 그 표 안 글머리가 헤딩 후보로 돌아온다
    r = c.put(f"/api/docs/{d}/headings/temp", json={"id": "tbl:t996", "state": "off"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["applied"] is True and v["note"] == "" and v["version"] == 1 and v["off"] == [{"id": "tbl:t996", "text": "작성 요령"}] and v["counts"]["items"] == 51
    g1 = _graph(c, d)
    assert g1["meta"]["derivedFrom"] == g0["meta"]["run"] and g1["meta"]["what"] == "TEMP 지정" and [n for n in g1["nodes"] if n["flow"] == "cell:c1001"]
    assert g1["temp"]["off"] == ["tbl:t996"] and "tbl:t996" not in g1["temp"]["items"]
    st = c.get(f"/api/docs/{d}/headings").json()
    assert st["stage2"]["tempStale"] is False and st["stage3"]["tempStale"] is True and "TEMP 지정 반영" in st["job"]["steps"][0]["name"]   # 3단계는 다시 안 돌림
    heading_runs.run_sync(s, 3, False)
    st = c.get(f"/api/docs/{d}/headings").json()
    assert st["stage3"]["tempStale"] is False and "t996" in {x["id"] for x in st["stage3"]["tables"]}
    # 지정 — 본문 문단(괄호 소제목)을 TEMP 로: 그 노드가 사라진다
    v = c.put(f"/api/docs/{d}/headings/temp", json={"id": "para:p5876", "state": "on"}).json()
    u = {x["id"]: x for x in v["items"]}["para:p5876"]
    assert (u["by"], u["rule"], u["why"]) == ("user", "user", "guide") and v["counts"]["user"] == 1 and "p5876" not in {n["id"] for n in _graph(c, d)["nodes"]}
    folder = works.folder(d) / "headings"
    saved = json.loads((folder / "hints.json").read_text("utf-8"))
    assert saved["temp"]["version"] == 2 and saved["temp"]["set"]["tbl:t996"]["state"] == "off" and saved["temp"]["set"]["para:p5876"]["text"].startswith("[국내 기술")
    assert saved["labels"] == {}                                                          # 라벨 지정(§13)과 같은 파일 — 서로 건드리지 않는다
    # 다시 열어도(세션을 비움) 지정이 남는다
    server.DOCS.clear()
    v = c.get(f"/api/docs/{d}/headings/temp").json()
    assert set(v["hints"]) == {"tbl:t996", "para:p5876"} and v["version"] == 2 and v["counts"]["items"] == 52
    # 지정을 지우면 처음 결과로 돌아온다
    c.put(f"/api/docs/{d}/headings/temp", json={"id": "tbl:t996", "state": "auto"})
    v = c.put(f"/api/docs/{d}/headings/temp", json={"id": "para:p5876", "state": "auto"}).json()
    g3 = _graph(c, d)
    assert v["hints"] == {} and v["counts"]["items"] == 52 and {n["id"]: (n["role"], n["key"], n["parent"], n["tplNo"], n["level"]) for n in g3["nodes"]} == n0
    # 문서가 추출 뒤 바뀌었으면 — 지정은 저장하고 다시 셈하지 않는다
    s = server.DOCS[d]
    s.rev += 1
    r = c.put(f"/api/docs/{d}/headings/temp", json={"id": "tbl:t996", "state": "off"})
    assert r.status_code == 200 and r.json()["applied"] is False and "다시" in r.json()["note"] and r.json()["stale"] is True
    assert _graph(c, d)["meta"]["run"] == g3["meta"]["run"]
    assert c.post(f"/api/docs/{d}/headings/temp/delete", json={"why": "guide"}).status_code == 409   # 1단계가 지금 문서 것이 아님
    s.rev -= 1
    r = c.post(f"/api/docs/{d}/headings/temp/apply")                                      # 저장만 해 둔 지정을 반영
    assert r.status_code == 200 and r.json()["applied"] is True and [n for n in _graph(c, d)["nodes"] if n["flow"] == "cell:c1001"]


def test_old_results_without_temp_are_flagged_stale(c):
    d, s = _open(c)
    heading_runs.run_sync(s, 1, False)
    st = heading_runs.state(s)
    st["stage2"] = {**HG.build(st["stage1"], use_llm=False), "meta": {"rev": s.rev, "stage1Run": st["stage1"]["meta"]["run"], "run": 99, "at": 1.0}}   # TEMP 를 모르던 결과
    st["stage3"] = {**HT.build(st["stage1"], use_llm=False), "meta": {"rev": s.rev, "stage1Run": st["stage1"]["meta"]["run"], "run": 98, "at": 1.0}}
    v = c.get(f"/api/docs/{d}/headings").json()
    assert v["stage2"]["tempStale"] is True and v["stage3"]["tempStale"] is True and v["stage3"]["tempTables"] == 0
    t = c.get(f"/api/docs/{d}/headings/temp").json()
    assert t["stage2"] == {"run": 99, "tempStale": True} and t["stage3"] == {"run": 98, "tempStale": True}


def test_temp_delete_removes_blocks_in_one_undoable_edit(c):
    d, s = _open(c)
    heading_runs.run_sync(s, 1, False)
    doc0 = c.get(f"/api/docs/{d}").json()
    assert c.post(f"/api/docs/{d}/headings/temp/delete", json={}).status_code == 400
    assert c.post(f"/api/docs/{d}/headings/temp/delete", json={"ids": []}).status_code == 400
    assert c.post(f"/api/docs/{d}/headings/temp/delete", json={"ids": ["tbl:t1"]}).status_code == 400            # TEMP 가 아닌 표
    assert c.post(f"/api/docs/{d}/headings/temp/delete", json={"why": "all"}).status_code == 400
    assert s.rev == doc0["rev"] and s.doc._attached(s.doc._ids["t996"])
    # 고른 것만 — 작성 요령 표 하나 + 쓸 자리 한 줄 + 지시문 한 줄
    r = c.post(f"/api/docs/{d}/headings/temp/delete", json={"ids": ["tbl:t996", "para:p684", "para:p707"]})
    assert r.status_code == 200, r.text
    v = r.json()
    assert sorted(v["deleted"]) == ["para:p684", "para:p707", "tbl:t996"] and v["skipped"] == [] and v["rev"] == doc0["rev"] + 1 and v["undo"] == 1
    doc = server.DOCS[d].doc
    for i in ("t996", "p684", "p707"):
        assert not doc._attached(doc._ids.get(i)), i
    assert doc._attached(doc._ids["p683"]) and doc._attached(doc._ids["c682"]) and doc._attached(doc._ids["t1428"])   # 이웃 문단·칸·다른 표는 그대로
    log = [x for x in c.get(f"/api/works/{d}/log").json()["events"] if x.get("kind") == "tempDelete"]
    assert len(log) == 1 and log[0]["deleted"] == 3
    t = c.get(f"/api/docs/{d}/headings/temp").json()
    assert t["stale"] is True                                                             # 문서가 바뀜 — 다시 추출해야 지울 수 있다
    assert c.post(f"/api/docs/{d}/headings/temp/delete", json={"ids": ["tbl:t1428"]}).status_code == 409
    HwpxDoc(c.get(f"/api/docs/{d}/download").content)                                     # 지운 문서가 열린다
    # 실행 취소 — 한 번에 모두 돌아온다
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    doc = server.DOCS[d].doc
    assert all(doc._attached(doc._ids.get(i)) for i in ("t996", "p684", "p707"))
    # 까닭 하나 전부 — 작성요령(표 31 + 지시문 6)
    heading_runs.run_sync(server.DOCS[d], 1, False)
    r = c.post(f"/api/docs/{d}/headings/temp/delete", json={"why": "guide"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert len(v["deleted"]) + len(v["skipped"]) == 37 and len(v["deleted"]) >= 36 and "tbl:t494" in v["deleted"] and "para:p684" not in v["deleted"]
    doc = server.DOCS[d].doc
    assert not doc._attached(doc._ids.get("t494")) and doc._attached(doc._ids["p684"])
    heading_runs.run_sync(server.DOCS[d], 1, False)
    t = c.get(f"/api/docs/{d}/headings/temp").json()
    assert t["counts"]["byRule"].get("guide_table", 0) + t["counts"]["byRule"].get("guide_box", 0) == len(v["skipped"]) and t["counts"]["byRule"]["blank"] == 15
    blob = c.get(f"/api/docs/{d}/download").content
    again = E.extract(HwpxDoc(blob), store=EMPTY)
    assert TP.label(again)["counts"]["byRule"].get("guide_table", 0) == 0 and again["counts"]["check"]
