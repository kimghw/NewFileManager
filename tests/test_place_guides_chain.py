"""place_guides.chain — 한 줄에 닿는 작성 지침의 층(이 줄 → 윗 줄 → 칸 → 상자 · 표 → 절). 2026-11-25 사용자 「헤딩마다 작성 지침 … 1.1 도 하위 내용에 대한 작성지침 … 아이콘」 · 「테이블 필드도 마찬가지로」."""
from app import place_guides as PG


def _p(i, text=""):
    return {"id": i, "type": "paragraph", "text": text}


BLOCKS = [
    _p("p1", "1. 성과목표"),
    {"id": "t1", "type": "table", "cells": [{"id": "c1", "row": 0, "col": 0, "blocks": [
        _p("p10", "공동(기업명 작성) :"), _p("p11"), _p("p12"), _p("p20", "공동(기업명 작성) :"), _p("p21")]}]},
    {"id": "t2", "type": "table", "cells": [{"id": "c2", "row": 0, "col": 0, "blocks": [_p("p30", "금액")]}, {"id": "c3", "row": 0, "col": 1, "blocks": [_p("p31")]}]},
]
GRAPH = {"nodes": [
    {"id": "p1", "para": "p1", "role": "heading", "area": "body", "parent": None},
    {"id": "p10", "para": "p10", "role": "heading", "area": "box", "parent": "p1", "level": 1},
    {"id": "p11", "para": "p11", "role": "heading", "area": "box", "parent": "p10", "level": 2},
    {"id": "p12", "para": "p12", "role": "heading", "area": "box", "parent": "p10", "level": 2},
    {"id": "p20", "para": "p20", "role": "heading", "area": "box", "parent": "p1", "level": 1},
    {"id": "p21", "para": "p21", "role": "heading", "area": "box", "parent": "p20", "level": 2},
]}
RULES = {"t1": [{"instruction": "상자 안은 당해연도만.", "basis": "explicit"},
                {"instruction": "p10 줄 괄호에 기관명, 그 아래 p11~p12 에 수행 내용.", "basis": "example"},
                {"instruction": "p11 은 첫 수행 항목.", "basis": "example"},
                {"instruction": "p20 은 둘째 공동기관.", "basis": "example"}]}
IX = {"heads": {"p1": [{"src": "doc", "kind": "※", "text": "절의 지침"}]}, "tables": {"t2": [{"src": "doc", "kind": "각주", "text": "천원 단위", "cell": "r0c1"}, {"src": "doc", "kind": "요령", "text": "표 전체"}]},
      "t3": ["t2"], "struct": {}}


def _layers(bid, **kw):
    return [(L["key"], [i["text"] for i in L["items"]]) for L in PG.chain(IX, BLOCKS, GRAPH, bid, RULES, kw.get("hows"))]


def test_mentions_expands_ranges():
    assert PG.mentions("p48 줄 · p50~p52 · t44") == {"p48", "p50", "p51", "p52", "t44"}
    assert PG.mentions("p5 와 p500-p2") == {"p5", "p500"}   # 거꾸로 된 범위는 앞 것만


def test_child_line_sees_its_set_parent_box_and_section():
    got = _layers("p11")
    assert got[0] == ("line", ["p11 은 첫 수행 항목."])
    assert got[1] == ("up", ["p10 줄 괄호에 기관명, 그 아래 p11~p12 에 수행 내용."])   # 윗 줄과 그 아래를 함께 가리킴 = 그 묶음(윗 줄)의 지침
    assert got[2] == ("table", ["상자 안은 당해연도만."])
    assert got[3] == ("head", ["절의 지침"])
    assert all("p20" not in t for _, ts in got for t in ts)   # 다른 묶음(둘째 공동기관)의 지침은 안 닿는다


def test_empty_line_and_parent_layers_still_show():
    got = _layers("p21")
    assert got[0] == ("line", []) and got[1] == ("up", ["p20 은 둘째 공동기관."])


def test_table_field_gets_cell_then_table():
    got = _layers("p31")
    assert got[0] == ("line", []) and got[1] == ("cell", ["천원 단위"]) and got[2] == ("table", ["표 전체"]) and got[3][0] == "head"


def test_review_how_goes_with_its_place():
    got = _layers("p12", hows={"t1": "상자의 작성 방향"})
    assert "상자의 작성 방향" in dict(got)["table"]


def test_chain_lines_lists_box_heading_lines_with_mention_counts():
    lines = PG.chain_lines(GRAPH, BLOCKS, RULES)
    assert lines == {"p10": 1, "p11": 2, "p12": 1, "p20": 1, "p21": 0}
    assert "p1" not in lines   # 본문 헤딩은 전의 단추(지침이 있을 때)가 맡는다
