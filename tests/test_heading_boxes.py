"""헤딩 추출 2단계 — 1칸 제목 상자(spec_헤딩_추출 ② §6 「1칸 제목 상자」, 2026-11-23 사용자 "국내 기술 동향 및 수준이 L4 가 되어야 하는데 … 저런 테이블에 헤딩을 넣는 경우가 있으니
이것도 템플릿에 반영을 하란말이지" · "지금도 이 테이블은 헤딩으로 인식을 못하냐?" → 권장안 ⓑ-1 「상자 = T1 L4 · o = L5」).
ⓐ 상자 찾기(본문의 1칸 표 · 제목 한 줄 · 그림만 · 바로 아래 헤딩 줄 · 같은 꼴 둘 이상) · ⓑ 그래프 — 상자는 바로 아래 헤딩 줄의 부모이고 그 줄의 레벨 바로 위에 「▦」 레벨이 끼워진다
(상자 없는 절의 같은 레터 줄도 한 칸 밀림) · A · B 의 답으로 안 바뀜 · ⓒ 오버레이 — 표 줄 · ⓓ 옛 오버레이 이행(앵커 · 레벨). LLM 은 가짜 ask."""
import copy

import pytest

from app import heading_boxes as BX
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import outline_edit as OE
from app import outline_lift
from tests.test_headings_branch import _nodes, _rec, _res, fake_ask

MAIN = "body:N.›N-N.›(N)›▦›o›-"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _host(i):
    """표를 품은 글 없는 본문 문단."""
    return {"id": f"p{i}", "n": i, "area": "body", "path": [], "table": None, "cell": None, "kind": "object", "family": None, "shape": "", "letter": "", "rest": "",
            "text": "", "leadSpaces": 0, "fmt": "S8", "char": {"text": {"sizePt": 4.0, "bold": True}}, "blank": True, "spans": [], "objects": ["tbl"]}


def _empty(i):
    return {"id": f"p{i}", "n": i, "area": "body", "path": [], "table": None, "cell": None, "kind": "empty", "family": None, "shape": "", "letter": "", "rest": "",
            "text": "", "leadSpaces": 0, "fmt": "S1", "char": {"text": {"sizePt": 10.0, "bold": False}}, "blank": True, "spans": [], "objects": []}


def _box(i, tbl, text, fill="#F2F2F2", size=13.0, objects=("pic",), cells=1, outer=(), kind="plain"):
    """1칸 상자 — 표를 품은 문단(i) + 칸 안 제목 문단(i+1)."""
    title = {"id": f"p{i + 1}", "n": i + 1, "area": "box", "table": tbl, "cell": f"{tbl}c", "kind": kind, "family": None, "shape": "", "letter": "", "rest": text,
             "text": " " + text, "leadSpaces": 1, "fmt": "S7", "char": {"text": {"sizePt": size, "bold": True, "font": "DotumChe"}}, "blank": False, "spans": [],
             "objects": list(objects),
             "path": [*outer, {"t": "tbl", "id": tbl, "rows": 1, "cols": cells, "cells": cells, "host": f"p{i}"}, {"t": "cell", "id": f"{tbl}c", "row": 0, "col": 0, "fill": fill}]}
    return [_host(i), title]


def _m(i, letter, shape, family, text, lead=0):
    return _rec(i, letter, shape, family, text, lead)


def _doc():
    """1. › 1-1. › (1) › [상자 A] › o · - · o | (2) › [상자 B] › o | (3) › o(상자 없음) | 2."""
    paras = [_m(0, "1.", "N.", "decimal", "장"), _m(1, "1-1.", "N-N.", "hyphen", "절"), _m(2, "(1)", "(N)", "paren-num", "국내 기술의 수준"),
             *_box(3, "t3", "국내 기술 동향 및 수준"), _empty(5),
             _m(6, "o", "o", "latin-o", "(국내 현황 총괄) 국내는 …"), _m(7, "-", "-", "dash", "세부"), _m(8, "o", "o", "latin-o", "(둘째) …"),
             _m(9, "(2)", "(N)", "paren-num", "국외 기술의 수준"),
             *_box(10, "t10", "국외 기술 동향 및 수준"),
             _m(12, "o", "o", "latin-o", "(국외 총괄 동향) …"),
             _m(13, "(3)", "(N)", "paren-num", "셋째"), _m(14, "o", "o", "latin-o", "상자 없는 절"),
             _m(15, "2.", "N.", "decimal", "다음 장")]
    return {"paras": paras, "labels": {"S1": {"name": "보통"}, "S7": {"name": "상자"}}}


# ---- ⓐ 상자 찾기 ------------------------------------------------------------------------------------------

def test_find_title_boxes():
    got = BX.find(_doc()["paras"])
    assert list(got) == ["p4", "p11"]
    assert got["p4"] == {"table": "t3", "host": "p3", "cell": "t3c", "title": "p4", "text": "국내 기술 동향 및 수준", "sig": got["p11"]["sig"], "child": "p6"}
    assert got["p11"]["child"] == "p12"


@pytest.mark.parametrize("why, change", [
    ("같은 꼴이 하나뿐", lambda ps: ps[11]["path"][-1].update(fill="#FFFFFF")),
    ("아래가 헤딩 줄이 아님", lambda ps: ps[12].update(kind="plain")),
    ("칸에 표", lambda ps: ps[11].update(objects=["pic", "tbl"])),
    ("문장으로 끝남", lambda ps: ps[11].update(text=" 국외 기술은 이렇다.")),
    ("너무 김", lambda ps: ps[11].update(text=" " + "가" * 81)),
    ("개요 레터 줄", lambda ps: ps[11].update(kind="marker")),
    ("표를 품은 문단에 글", lambda ps: ps[10].update(text="앞 글")),
    ("여러 칸 표", lambda ps: ps[11]["path"][-2].update(cells=2)),
])
def test_find_skips(why, change):
    paras = copy.deepcopy(_doc()["paras"])
    change(paras)
    got = BX.find(paras)
    assert "p11" not in got, why
    if why == "같은 꼴이 하나뿐":
        assert got == {}  # 같은 꼴이 둘 이상이어야 한다 — 남은 하나도 빠진다


def test_find_skips_temp_and_nested():
    paras = _doc()["paras"]
    assert "p11" not in BX.find(paras, skip={"p11"}) and BX.find(paras, skip={"p11"}) == {}
    nested = copy.deepcopy(paras)
    for r in (nested[4], nested[11]):  # 칸 안 표(바깥 그릇이 있음)는 본문의 상자가 아니다
        r["path"] = [{"t": "tbl", "id": "tout", "rows": 2, "cols": 2, "cells": 4}, {"t": "cell", "id": "cout"}, *r["path"]]
    assert BX.find(nested) == {}


# ---- ⓑ 그래프 ---------------------------------------------------------------------------------------------

def _check(g):
    N = _nodes(g)
    a, b = N["p4"], N["p11"]
    assert (a["kind"], a["key"], a["role"], a["letter"], a["text"], a["flow"]) == (BX.KIND, BX.KEY, "heading", "", "국내 기술 동향 및 수준", "body")
    assert a["box"] == {"table": "t3", "title": "p4", "host": "p3", "child": "p6"}
    # 상자 = 그 자리(o 가 설 자리)의 줄 · 그 아래 줄은 상자의 것 — 「(1) › 상자 › o」
    assert [(N[p]["parent"], N[p]["template"], N[p]["level"]) for p in ("p2", "p4", "p6", "p7", "p8")] == [
        ("p1", MAIN, 3), ("p2", MAIN, 4), ("p4", MAIN, 5), ("p6", MAIN, 6), ("p4", MAIN, 5)]
    assert [(N[p]["parent"], N[p]["level"]) for p in ("p11", "p12")] == [("p9", 4), ("p11", 5)]
    # 상자 없는 절의 o 도 L5(같은 레터가 두 레벨로 갈리지 않게 — 「레벨을 건너뛴 줄」 과 같다)
    assert (N["p14"]["parent"], N["p14"]["template"], N["p14"]["level"]) == ("p13", MAIN, 5)
    assert (N["p15"]["parent"], N["p15"]["level"]) == ("root", 1)
    t = next(x for x in g["templates"] if x["anchor"] == MAIN)
    assert t["chain"] == ["N.", "N-N.", "(N)", BX.KEY, "o", "-"] and t["no"] == 1 and len(g["templates"]) == 1
    sl = {s["level"]: s for s in t["slots"]}
    assert (sl[4]["letter"], sl[4]["count"], sl[4]["rep"]) == (BX.KEY, 2, "p4")
    ins = {x["root"]: x for x in g["instances"]}
    assert list(ins) == ["p0", "p15"] and ins["p0"]["missing"] == [] and 4 not in ins["p15"]["missing"]  # 상자 레벨이 빠진 절은 편차가 아니다
    assert not [a for a in g["adjustments"] if a["level"] == 4] and not any(BX.KEY in [x["key"] for x in h["letters"]] for h in g["heterogeneous"])
    return N


def test_boxes_without_llm():
    g = HG.build(_doc(), use_llm=False)
    _check(g)
    assert g["llm"]["mainChain"][:3] == ["N.", "N-N.", "(N)"]


def _a(st1, box_role="title"):
    """가짜 A — 상자 유형에는 일부러 틀린 답(제목)을 준다: 스크립트 규칙이 이긴다."""
    know = {"N.": ["root"], "N-N.": ["N."], "(N)": ["N-N."], "o": ["(N)"], "-": ["o"]}
    out = []
    for tid, t in HG.type_table(HG.candidates(st1)).items():
        if t["kind"] == BX.KIND:
            out.append({"type": tid, "role": box_role, "parents": ["(N)"], "variantOf": "", "basis": "", "reason": "틀린 답"})
        else:
            out.append({"type": tid, "role": "heading", "parents": know.get(t["shape"], []), "variantOf": "", "basis": "", "reason": ""})
    return {"types": out, "mainChain": ["N.", "N-N.", "(N)", "o", "-"], "summary": "가짜"}


def test_boxes_ignore_llm_answers():
    """A 가 상자 유형을 제목으로 답하고 B 가 상자의 부모 · 역할을 바꾸려 해도 스크립트 규칙 그대로다(B 의 그 변경은 버림)."""
    st1 = _doc()
    b = lambda job, d: _res({"changes": [{"id": "p11", "parent": "p2", "role": "not_heading", "template": "", "level": 0, "reason": "틀린 답"}], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(_a(st1)), heading_section=b))
    _check(g)
    assert {"id": "p11", "why": "1칸 제목 상자 — 스크립트가 정한다"} in g["rejected"]
    ty = next(x for x in g["types"] if x["kind"] == BX.KIND)
    assert (ty["role"], ty["key"], ty["shape"]) == ("heading", BX.KEY, BX.KEY)
    assert g["llm"]["mainChainFixed"]


def test_box_key_never_joins_main_chain():
    st1 = _doc()
    a = _a(st1)
    a["mainChain"] = ["N.", "N-N.", "(N)", BX.KEY, "o", "-"]
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(a)))
    assert g["llm"]["mainChainRejected"] == a["mainChain"] and not g["llm"]["mainChainFixed"]
    _check(g)


def test_box_over_non_heading_is_title_leaf():
    """바로 아래 줄을 A 가 헤딩 아님으로 답하면 상자는 전처럼 제목 잎이다(스택을 흔들지 않음 · 템플릿 없음)."""
    st1 = _doc()
    a = _a(st1)
    o = next(t for t in a["types"] if HG.type_table(HG.candidates(st1))[t["type"]]["shape"] == "o")
    o["role"] = "not_heading"
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(a)))
    N = _nodes(g)
    assert (N["p4"]["role"], N["p4"]["key"], N["p4"]["template"]) == ("title", None, None) and "box" not in N["p4"]
    assert BX.KEY not in next(t for t in g["templates"] if t["kind"] == "main")["chain"]


def test_next_box_closes_previous_box():
    """같은 레터를 이끄는 상자가 열려 있으면 다음 상자는 그 상자의 형제(앞 상자 아래 o · - 뒤에 와도)."""
    paras = [_m(0, "1.", "N.", "decimal", "장"), _m(1, "□", "□", "square", "배경"),
             *_box(2, "t2", "첫 상자"), _m(4, "o", "o", "latin-o", "가"), _m(5, "-", "-", "dash", "나"),
             *_box(6, "t6", "둘째 상자"), _m(8, "o", "o", "latin-o", "다"),
             _m(9, "□", "□", "square", "필요성"), _m(10, "o", "o", "latin-o", "상자 없음")]
    g = HG.build({"paras": paras, "labels": {}}, use_llm=False)
    N = _nodes(g)
    assert [N[p]["parent"] for p in ("p3", "p4", "p5", "p7", "p8", "p9", "p10")] == ["p1", "p3", "p4", "p1", "p7", "p0", "p9"]
    t = next(t for t in g["templates"] if t["kind"] == "main")
    assert t["chain"] == ["N.", "□", BX.KEY, "o", "-"] and [N[p]["level"] for p in ("p3", "p4", "p7", "p10")] == [3, 4, 3, 4]


def test_box_on_branch_root_takes_instance():
    """상자가 가지 템플릿의 뿌리 자리에 서면(아래 줄이 L1) 상자가 그 인스턴스의 뿌리 · 같은 상자 아래 형제 줄은 한 인스턴스."""
    paras = [_m(0, "1.", "N.", "decimal", "장"), *[_m(i, "□", "□", "square", "네모") for i in (1, 2, 3, 4)], _m(5, "2.", "N.", "decimal", "장 둘"),
             *_box(6, "t6", "첫 상자"), _m(8, "▸", "▸", "arrow", "가"), _m(9, "▸", "▸", "arrow", "나"),
             *_box(10, "t10", "둘째 상자"), _m(12, "▸", "▸", "arrow", "다")]
    g = HG.build({"paras": paras, "labels": {}}, use_llm=False)
    N = _nodes(g)
    br = next(t for t in g["templates"] if t["kind"] == "branch")
    assert br["chain"] == [BX.KEY, "▶"] and br["anchor"] == "body:▦›▶" and next(t for t in g["templates"] if t["kind"] == "main")["chain"] == ["N.", "□"]
    assert [(N[p]["parent"], N[p]["level"]) for p in ("p7", "p8", "p9", "p11", "p12")] == [("p5", 1), ("p7", 2), ("p7", 2), ("p5", 1), ("p11", 2)]
    roots = [i["root"] for i in g["instances"] if i["template"] == br["id"]]
    assert roots == ["p7", "p11"] and next(i for i in g["instances"] if i["root"] == "p7")["members"] == ["p8", "p9"]


def test_b_slot_level_counts_box_level():
    """B 가 상자 레벨이 낀 사슬의 번호로 슬롯 예외를 적으면 그 번호로 읽는다(배우는 동안의 번호로 바꿈) · 상자 레벨 자체는 슬롯 예외가 안 된다."""
    st1 = _doc()
    b = lambda job, d: _res({"changes": [{"id": "p7", "parent": "p6", "role": "heading", "template": MAIN, "level": 6, "reason": "그대로"},
                                         {"id": "p14", "parent": "p13", "role": "heading", "template": MAIN, "level": 4, "reason": "상자 레벨"}], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(_a(st1)), heading_section=b))
    N = _nodes(g)
    assert N["p7"]["level"] == 6 and N["p14"]["level"] == 5
    assert [u["id"] for u in g["llm"]["slotUnresolved"]] == ["p14"]


# ---- ⓒ 오버레이 ---------------------------------------------------------------------------------------------

def _ov(st1=None):
    st1 = st1 or _doc()
    g = HG.build(st1, use_llm=False)
    g["meta"] = {"run": 1, "at": 0}
    text = {r["id"]: r["text"] for r in st1["paras"]}
    return g, OE.build_overlay(g, lambda pid: {"text": text[pid], "attrs": {"para": "1", "char": "1"}, "spacer": None} if pid in text else None)


def test_overlay_box_lines_are_table_lines():
    _, ov = _ov()
    x = ov["lines"]["p4"]
    assert (x["role"], x["letter"], x["key"], x["level"], x["table"], x["parent"]) == (OE.TABLE, "", BX.KEY, 4, "t3", "p2")
    t = ov["templates"][x["tpl"]]
    assert t["chain"] == ["N.", "N-N.", "(N)", BX.KEY, "o", "-"] and t["max"] == 6 and not t.get("lift") and OE.lift_depth(t) == 0
    sl = t["slots"]["4"]
    assert (sl["table"], sl["letter"], sl["key"], sl["prefix"], sl["rep"]) == (True, "", BX.KEY, None, "p4")
    assert [ov["lines"][p]["parent"] for p in ("p6", "p8", "p12", "p14")] == ["p4", "p4", "p11", "p13"]
    assert [ov["lines"][p]["level"] for p in ("p6", "p7", "p14")] == [5, 6, 5]
    assert OE.line_view(x)["key"] == BX.KEY


# ---- ⓓ 옛 오버레이 이행 -------------------------------------------------------------------------------------

def _old_ov():
    """상자를 모르던 때의 오버레이 — 사슬 「N.›N-N.›(N)›o›-」, 상자 없는 o 줄들이 L4 · 서식 종속(T1L4a) · 종속 · 더한 레벨 기록."""
    return {"run": [0, 0], "lines": {"p6": {"tpl": "1", "no": 1, "level": 4, "parent": "p2", "letter": "o", "key": "o"},
                                     "p7": {"tpl": "1~4a", "no": "1L4a", "level": 5, "parent": "p6", "letter": "-", "key": "-"},
                                     "p2": {"tpl": "1", "no": 1, "level": 3, "parent": "p1", "letter": "(1)", "key": "(N)"}},
            "templates": {"1": {"no": 1, "kind": "main", "anchor": "body:N.›N-N.›(N)›o›-", "chain": ["N.", "N-N.", "(N)", "o", "-"],
                                "slots": {str(i): {"letter": k, "pos": {"rule": i}} for i, k in enumerate(["1.", "1-1.", "(1)", "o", "-"], 1)}, "max": 5},
                          "1~4a": {"no": "1L4a", "kind": "main", "anchor": "body:N.›N-N.›(N)›o›-~L4a", "chain": ["N.", "N-N.", "(N)", "o", "-"],
                                   "slots": {"4": {"letter": "o"}, "5": {"letter": "-"}}, "max": 5, "base": 3, "variant": {"of": "1", "level": 4, "sfx": "a"}},
                          "2": {"no": 2, "kind": "branch", "anchor": "body:▸", "chain": ["▸"], "slots": {"1": {}}, "max": 1}},
            "branches": {"1|4": ["2"], "1|2": ["2"]},
            "grows": [{"tid": "1", "level": 6}],
            "splits": [{"of": "body:N.›N-N.›(N)›o›-", "ofId": "1", "level": 4, "sfx": "a", "id": "1~4a", "lines": ["p6"], "n": 1}],
            "merges": [{"child": "body:▸", "parent": "body:N.›N-N.›(N)›o›-", "childId": "2", "parentId": "1", "at": 4, "id": "1+2", "n": 2}],
            "unmerged": [{"child": "body:▸", "parent": "body:N.›N-N.›(N)›o›-", "at": 5}]}


def test_align_old_maps_anchor_and_levels():
    _, new = _ov()
    old = _old_ov()
    keep = copy.deepcopy(old)
    out = BX.align_old(old, new)
    assert old == keep and out is not old  # 옛것은 그대로 — 사본
    t, v = out["templates"]["1"], out["templates"]["1~4a"]
    assert (t["anchor"], t["chain"], sorted(t["slots"], key=int), t["max"]) == (MAIN, ["N.", "N-N.", "(N)", BX.KEY, "o", "-"], ["1", "2", "3", "5", "6"], 6)
    assert t["slots"]["5"]["pos"] == {"rule": 4} and t["slots"]["3"]["pos"] == {"rule": 3}
    assert (v["anchor"], v["variant"]["level"], v["base"], sorted(v["slots"], key=int)) == (MAIN + "~L5a", 5, 4, ["5", "6"])
    assert [out["lines"][p]["level"] for p in ("p6", "p7", "p2")] == [5, 6, 3]
    assert out["branches"] == {"1|5": ["2"], "1|2": ["2"]} and out["grows"] == [{"tid": "1", "level": 7}]
    assert (out["splits"][0]["of"], out["splits"][0]["level"]) == (MAIN, 5)
    assert (out["merges"][0]["parent"], out["merges"][0]["at"], out["merges"][0]["child"]) == (MAIN, 5, "body:▸")
    assert (out["unmerged"][0]["parent"], out["unmerged"][0]["at"]) == (MAIN, 6)
    assert out["templates"]["2"]["anchor"] == "body:▸"  # 상자와 무관한 템플릿은 그대로


def test_align_old_noop_without_box_change():
    _, new = _ov()
    assert BX.align_old(new, new) is new
    old = _old_ov()
    plain = {"templates": {"1": {"anchor": "body:N.›N-N.›(N)›o›-"}}}
    assert BX.align_old(old, plain) is old and BX.align_old(None, new) is None


def test_lift_carry_runs_align_first():
    """2단계를 다시 돌릴 때 carry 들의 맨 앞(outline_lift.carry)이 상자 레벨 이행을 한다 — 뒤의 carry 가 새 앵커 · 레벨로 읽는다."""
    _, new = _ov()
    out = outline_lift.carry(_old_ov(), new, doc=None)
    assert out["templates"]["1"]["anchor"] == MAIN and out["splits"][0]["level"] == 5
