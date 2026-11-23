"""넣은 뒤 템플릿 · 서식 정리(spec_병합 ② §5-9) — app/merge_retidy.py 의 넣은 블록 찾기 · 레벨마다 대표 고르기 규칙.
실제 이관 문서에서의 확인(다시 분석 → 반영 → 두 번째는 할 것 없음)은 artifacts/retidy_2026-11-22/try_retidy.py."""
import copy

import pytest

from app import merge_retidy as MR
from app import outline_match as OM


def test_inserted_walks_into_inserted_tables_and_reads_every_record():
    blocks = [
        {"id": "p1"},
        {"id": "t2", "cells": [{"id": "c1", "blocks": [{"id": "p3"}, {"id": "t4", "cells": [{"id": "c2", "blocks": [{"id": "p5"}]}]}]}]},
        {"id": "t6", "cells": [{"id": "c3", "blocks": [{"id": "p7"}, {"id": "p8"}]}]},
        {"id": "p9"}, {"id": "p10"},
    ]
    rec = {"applied": {"a": {"ids": ["t2"], "over": {"lines": [{"id": "p8"}, {"id": None}]}}},
           "filled": {"ids": ["p9", "gone"]}, "copied": {"표": {"to": "p10"}}}
    got = MR.inserted(blocks, rec)
    assert got == {"t2", "p3", "t4", "p5", "p8", "p9", "p10"}   # 넣은 표 안의 블록은 모두(칸 id 는 블록이 아니다) · 넣지 않은 표(t6)는 넣은 줄(p8)만 · 지금 문서에 없는 id 는 뺌
    assert MR.inserted(blocks, {}) == set() and MR.inserted(blocks, None) == set()


@pytest.fixture
def fake(monkeypatch):
    """개요 오버레이 · 비교 값을 글로 꾸민다 — look = 서식 이름 글(같으면 같은 서식) · near = 「≈」 로 적은 줄."""
    looks, near, bad = {}, set(), set()
    monkeypatch.setattr(OM, "look", lambda doc, ov, p: looks[p])
    monkeypatch.setattr(OM, "same", lambda a, b: a["f"] == b["f"])
    monkeypatch.setattr(OM, "near", lambda a, b, tol: b["f"] in near)
    monkeypatch.setattr(OM, "_tolerance", lambda: {})
    monkeypatch.setattr(OM, "_alive", lambda doc, p: True)
    monkeypatch.setattr(OM, "lone_value", lambda doc, ov, p: False)
    monkeypatch.setattr(OM, "_order", lambda doc: {f"p{i}": i for i in range(100)})

    def rep_shape(doc, ov, p):
        if p in bad:
            raise ValueError("레터 없음")
        return {}
    monkeypatch.setattr(OM, "rep_shape", rep_shape)

    def make(lines, reps, user=()):
        ov = {"lines": {}, "templates": {}}
        for p, (t, lv, f, *form) in lines.items():
            ov["lines"][p] = {"tpl": t, "level": lv, "role": "heading"}
            looks[p] = {"f": f, **({"form": form[0]} if form else {})}
            sl = ov["templates"].setdefault(t, {"no": int(t), "slots": {}})["slots"].setdefault(str(lv), {"letter": "o"})
            sl["rep"] = reps.get((t, lv))
            if (t, lv) in user:
                sl["repSet"] = True
        return ov
    return make, near, bad


def test_form_line_is_the_rep_when_an_inserted_line_took_that_level(fake):
    make, _, _ = fake
    # T1 L1: 목적 문서 줄 p1 · p2(S1) + 넣은 줄 p3(S1 — 넣을 때 그 레벨로 바뀐 줄) · p4 · p5(S9 — 더 많다) · 그래프가 넣은 줄 p4 를 대표로 뽑았다
    ov = make({"p1": ("1", 1, "S1"), "p2": ("1", 1, "S1"), "p3": ("1", 1, "S1"), "p4": ("1", 1, "S9"), "p5": ("1", 1, "S9")}, {("1", 1): "p4"})
    P = MR.plan(None, ov, {"p3", "p4", "p5"})
    (row,) = P["rows"]
    assert (row["kind"], row["rep"], row["slot"], row["fix"], row["same"]) == ("form", "p1", True, ["p4", "p5"], ["p3"]) and P["tpls"] == ["1"]


def test_deeper_content_is_not_given_the_form_lines_look(fake):
    make, _, _ = fake
    # 연차보고서 「- (추진 내용)」 아래 넣은 「o」 내용(p3~p5) — 그래프는 양식의 굵은 소제목 「ㅇ」(p1 · S1B)과 같은 레벨로 읽는다: 넣은 줄 가운데 S1B 인 줄이 없다 → 넣은 줄끼리(가장 많은 S7)
    ov = make({"p1": ("1", 3, "S1B"), "p3": ("1", 3, "S7"), "p4": ("1", 3, "S8"), "p5": ("1", 3, "S7")}, {("1", 3): "p1"})
    (row,) = MR.plan(None, ov, {"p3", "p4", "p5"})["rows"]
    assert (row["kind"], row["rep"], row["slot"], row["fix"], row["same"], row["near"]) == ("deep", "p3", False, ["p4"], ["p3", "p5"], [])   # 레벨의 대표(p1)는 그대로


def test_grown_level_takes_the_most_common_inserted_format(fake):
    make, _, _ = fake
    # T2 L2: 목적 문서에 없던 레벨(넣는 쪽 개요가 더 길다) — 넣은 줄 S5 둘 · S7 셋 → S7 의 첫 줄이 레벨의 대표
    ov = make({"p10": ("2", 2, "S5"), "p11": ("2", 2, "S7"), "p12": ("2", 2, "S5"), "p13": ("2", 2, "S7"), "p14": ("2", 2, "S7")}, {("2", 2): "p10"})
    (row,) = MR.plan(None, ov, {"p10", "p11", "p12", "p13", "p14"})["rows"]
    assert (row["kind"], row["rep"], row["slot"], row["fix"]) == ("grown", "p11", True, ["p10", "p12"])
    assert MR.summary([row]) == {"levels": 1, "grown": 1, "deep": 0, "lines": 5, "fix": 2, "near": 0, "own": 0, "cutLevels": 0, "cut": 0, "cutLines": 0, "held": 0,
                                 "letters": 0, "letterSwaps": [], "lettersLeft": 0}


def test_current_rep_kept_when_it_already_has_the_chosen_format(fake):
    make, _, _ = fake
    ov = make({"p1": ("1", 1, "S1"), "p2": ("1", 1, "S1"), "p3": ("1", 1, "S1"), "p4": ("1", 1, "S2")}, {("1", 1): "p2"})
    (row,) = MR.plan(None, ov, {"p3", "p4"})["rows"]
    assert (row["kind"], row["rep"], row["fix"]) == ("form", "p2", ["p4"])
    ov2 = make({"p5": ("2", 1, "S3"), "p6": ("2", 1, "S3")}, {("2", 1): "p6"})
    (row2,) = MR.plan(None, ov2, {"p5", "p6"})["rows"]
    assert (row2["rep"], row2["fix"]) == ("p6", [])   # 넣은 줄이 이미 한 서식 — 맞출 줄 없음(확정 서식은 반영이 대표 갈래에 건다)


def test_user_rep_is_kept_even_if_it_is_an_inserted_line(fake):
    make, _, _ = fake
    ov = make({"p1": ("1", 1, "S1"), "p3": ("1", 1, "S2"), "p4": ("1", 1, "S3")}, {("1", 1): "p3"}, user={("1", 1)})
    (row,) = MR.plan(None, ov, {"p3", "p4"})["rows"]
    assert (row["kind"], row["rep"], row["fix"]) == ("user", "p3", ["p4"])


def test_table_own_format_left_and_near_form_lines_follow(fake):
    make, near, _ = fake
    near.add("S1b")
    # 대표 p1(S1 · 표 양식 A) · 목적 문서의 「≈」 줄 p2(S1b) · 다른 서식 p5(S8 — 사람이 둔 것일 수 있다) · 넣은 줄 p6(S1 — 그 레벨을 받은 줄) ·
    # p3(표 양식 B — 그 양식에 대표 서식이 없다: 표의 서식) · p4(표 양식 A)
    ov = make({"p1": ("1", 1, "S1", "A"), "p2": ("1", 1, "S1b", "A"), "p5": ("1", 1, "S8", "A"), "p6": ("1", 1, "S1", "A"), "p3": ("1", 1, "S3", "B"), "p4": ("1", 1, "S3", "A")}, {("1", 1): "p1"})
    (row,) = MR.plan(None, ov, {"p3", "p4", "p6"})["rows"]
    assert (row["kind"], row["fix"], row["own"], row["near"]) == ("form", ["p4"], ["p3"], ["p2"])


def test_bracket_lines_and_lines_without_letter_are_not_reps(fake):
    make, _, bad = fake
    ov = make({"p2": ("1", 1, "S2"), "p3": ("1", 1, "S2"), "p4": ("1", 1, "S4")}, {("1", 1): None})
    ov["lines"]["p9"] = {"tpl": "1", "level": 1, "role": "label"}   # 괄호 줄은 계획에 안 든다
    bad.add("p2")   # 첫머리에 레터가 없는 줄은 대표가 못 된다 — 같은 서식의 다음 줄
    (row,) = MR.plan(None, ov, {"p2", "p3", "p4", "p9"})["rows"]
    assert (row["rep"], row["kind"], row["lines"]) == ("p3", "grown", 3)


# ---------------------------------------------------------------- deep 레벨 → 서식 종속 템플릿(2026-11-22 · merge_retidy.cut_all)
SHAPE = {"lead": "", "tok": "o", "gap": " ", "prefix": "o ", "attrs": {"paraPrIDRef": "0", "styleIDRef": "0", "charPrIDRef": "0"}, "body": "0", "first": None, "fmt": ""}


@pytest.fixture
def tree(monkeypatch):
    """줄마다 부모가 있는 개요 오버레이(서식 종속 템플릿으로 가르기 — 진짜 outline_match.split) · look = 서식 이름 글."""
    looks = {}
    monkeypatch.setattr(OM, "look", lambda doc, ov, p: looks[p])
    monkeypatch.setattr(OM, "same", lambda a, b: a["f"] == b["f"])
    monkeypatch.setattr(OM, "near", lambda a, b, tol: False)
    monkeypatch.setattr(OM, "_tolerance", lambda: {})
    monkeypatch.setattr(OM, "_alive", lambda doc, p: True)
    monkeypatch.setattr(OM, "lone_value", lambda doc, ov, p: False)
    monkeypatch.setattr(OM, "_order", lambda doc: {f"p{i}": i for i in range(100)})
    monkeypatch.setattr(OM, "rep_shape", lambda doc, ov, p: dict(SHAPE))

    def make(lines, reps, keys=None):
        ov = {"lines": {}, "templates": {}, "branches": {}}
        for p, (t, lv, f, parent) in lines.items():
            ov["lines"][p] = {"tpl": t, "no": int(t), "level": lv, "role": "heading", "parent": parent}
            looks[p] = {"f": f}
            T = ov["templates"].setdefault(t, {"no": int(t), "anchor": f"A{t}", "chain": [], "slots": {}})
            T["slots"].setdefault(str(lv), {"letter": "o", "key": (keys or {}).get((t, lv), "o"), "rep": reps.get((t, lv))})
        return ov
    return make


def _tpls(ov, *ps):
    return {p: ov["lines"][p]["tpl"] for p in ps}


def test_deep_level_is_cut_into_a_format_variant_and_form_lines_under_it_stay(tree):
    # 연차보고서 T1: 양식 p1(L1) · 굵은 소제목 p2 「ㅇ」(L2 · B) · 그 아래 p7(L3) / 「- (추진 내용)」 아래 넣은 내용 p3 · p6 「o」(L2 — 레터가 같아 소제목과 같은 레벨로 읽힘) · p4 「-」(L3)
    # · 넣은 내용 뒤의 양식 줄 p5 「- (추진 실적)」 — 그래프가 넣은 줄 p3 의 아이로 읽음. 그래프는 넣은 줄 p3 을 L2 대표로 뽑았다
    ov = tree({"p1": ("1", 1, "H", None), "p2": ("1", 2, "B", "p1"), "p7": ("1", 3, "F", "p2"), "p3": ("1", 2, "S7", "p1"), "p4": ("1", 3, "S8", "p3"),
               "p5": ("1", 3, "F", "p3"), "p6": ("1", 2, "S7", "p1")}, {("1", 1): "p1", ("1", 2): "p3", ("1", 3): "p4"})
    ins = {"p3", "p4", "p6"}
    assert [r["kind"] for r in MR.plan(None, ov, ins)["rows"]] == ["deep", "deep"]
    cuts, left = MR.cut_all(None, ov, ins)
    assert left == [] and [(c["id"], c["name"], c["side"], c["lines"], c["moved"], c["stop"]) for c in cuts] == [("1~2a", "1L2a", "ins", 2, 3, 1)]
    assert _tpls(ov, "p3", "p4", "p6", "p5", "p7", "p2") == {"p3": "1~2a", "p4": "1~2a", "p6": "1~2a", "p5": "1", "p7": "1", "p2": "1"}   # 양식 줄(p5)은 남는다
    A = ov["templates"]["1"]["slots"]
    assert (A["2"]["rep"], OM.rep_origin(A["2"])) == ("p2", "agent") and (A["3"]["rep"], OM.rep_origin(A["3"])) == ("p5", "agent")   # 레벨의 대표 = 양식 줄(떼기가 데려간 L3 대표 p4 대신 — 동결 모양도)
    C = ov["templates"]["1~2a"]
    assert C["variant"] == {"of": "1", "level": 2, "sfx": "a", "by": "retidy", "side": "ins"} and C["base"] == 1 and C["slots"]["2"]["rep"] == "p3"
    (rec,) = ov["splits"]
    assert (rec["by"], rec["side"], rec["stop"], rec["lines"]) == ("retidy", "ins", ["p5"], ["p3", "p6"])
    rows = MR.plan(None, ov, ins)["rows"]
    assert [(r["tpl"], r["level"], r["kind"], r["rep"], r["fix"]) for r in rows] == [("1~2a", 2, "cut", "p3", []), ("1~2a", 3, "cut", "p4", [])]
    assert MR.summary(rows, cuts, left) == {"levels": 2, "grown": 0, "deep": 0, "lines": 3, "fix": 0, "near": 0, "own": 0, "cutLevels": 2, "cut": 1, "cutLines": 3, "held": 0,
                                            "letters": 0, "letterSwaps": [], "lettersLeft": 0}
    assert MR.cut_all(None, ov, ins) == ([], [])   # 두 번째 누름 — 가를 것 없음


def test_cut_carries_over_a_rebuilt_overlay_with_its_stop_lines(tree):
    ov = tree({"p1": ("1", 1, "H", None), "p2": ("1", 2, "B", "p1"), "p3": ("1", 2, "S7", "p1"), "p4": ("1", 3, "S8", "p3"), "p5": ("1", 3, "F", "p3")},
              {("1", 1): "p1", ("1", 2): "p2", ("1", 3): "p5"})
    fresh = copy.deepcopy(ov)   # 2단계를 다시 돌려 그래프에서 새로 만든 오버레이(떼기 없음)
    MR.cut_all(None, ov, {"p3", "p4"})
    assert OM.carry(ov, fresh) == []
    assert _tpls(fresh, "p3", "p4", "p5") == {"p3": "1~2a", "p4": "1~2a", "p5": "1"}   # stop 줄은 다시 걸어도 남는다
    assert fresh["templates"]["1~2a"]["variant"]["by"] == "retidy" and fresh["splits"][0]["stop"] == ["p5"]


def test_cut_moves_the_form_line_when_the_template_grew_from_inserted_lines(tree):
    # 다시 분석한 그래프가 넣은 줄(p1 □ · p2 o · p3 -)로 만든 T6 에 양식 줄 p4 「- (추진 실적)」 이 매달렸다 — 떼는 쪽은 양식 줄
    ov = tree({"p1": ("6", 1, "A", None), "p2": ("6", 2, "B", "p1"), "p3": ("6", 3, "C", "p2"), "p4": ("6", 3, "FB", "p2")}, {("6", 1): "p1", ("6", 2): "p2", ("6", 3): "p3"})
    ins = {"p1", "p2", "p3"}
    cuts, left = MR.cut_all(None, ov, ins)
    assert left == [] and [(c["id"], c["side"], c["lines"]) for c in cuts] == [("6~3a", "form", 1)]
    assert _tpls(ov, "p3", "p4") == {"p3": "6", "p4": "6~3a"} and ov["templates"]["6"]["slots"]["3"]["rep"] == "p3"
    assert ov["templates"]["6~3a"]["variant"]["side"] == "form" and ov["splits"][0]["side"] == "form"   # 화면 이름표가 「양식 줄」 로 보인다(outline_match.js)
    assert [r["kind"] for r in MR.plan(None, ov, ins)["rows"]] == ["grown", "grown", "grown"]
    # 그 템플릿에 넣은 줄이 들어와도(다시 분석한 그래프) 그 줄만 넣은 쪽 — 양식 줄(p4)을 넣은 줄의 서식으로 바꾸지 않는다
    ov["lines"]["p9"] = {"tpl": "6~3a", "no": "6L3a", "level": 3, "role": "heading", "parent": "p2"}
    orig = OM.look
    OM.look = lambda doc, ov_, p: {"f": "C"} if p == "p9" else orig(doc, ov_, p)
    try:
        row = next(r for r in MR.plan(None, ov, ins | {"p9"})["rows"] if r["tpl"] == "6~3a")
    finally:
        OM.look = orig
    assert (row["lines"], row["form"], row["kind"]) == (1, 1, "deep") and "p4" not in row["fix"] + row["same"] + row["near"]


def test_numbered_level_siblings_are_not_cut_and_stay_deep(tree):
    # 번호형 레벨에서 양식 줄 p2 「1.」 와 같은 부모 아래 넣은 줄 p3 「2.」 — 일부만 떼면 번호가 템플릿마다 따로 매겨진다(outline_match.split_block) → 전처럼 넣은 줄끼리
    ov = tree({"p1": ("1", 1, "H", None), "p2": ("1", 2, "F", "p1"), "p3": ("1", 2, "S", "p1")}, {("1", 1): "p1", ("1", 2): "p2"}, keys={("1", 2): "N."})
    cuts, left = MR.cut_all(None, ov, {"p3"})
    assert cuts == [] and [(x["level"], "번호형" in x["why"]) for x in left] == [(2, True)]
    (row,) = MR.plan(None, ov, {"p3"})["rows"]
    assert row["kind"] == "deep" and not ov.get("splits")


def test_lines_made_later_in_a_cut_template_count_as_inserted(tree):
    ov = tree({"p1": ("1", 1, "H", None), "p2": ("1", 2, "B", "p1"), "p3": ("1", 2, "S7", "p1"), "p6": ("1", 2, "S7", "p1")}, {("1", 1): "p1", ("1", 2): "p2"})
    MR.cut_all(None, ov, {"p3", "p6"})
    ov["lines"]["p9"] = {"tpl": "1~2a", "no": "1L2a", "level": 2, "role": "heading", "parent": "p1"}   # 뗀 뒤 Enter 로 만든 줄(넣은 기록에 없다)
    looks_p9 = {"f": "S7"}
    orig = OM.look
    OM.look = lambda doc, ov_, p: looks_p9 if p == "p9" else orig(doc, ov_, p)
    try:
        (row,) = MR.plan(None, ov, {"p3", "p6"})["rows"]
    finally:
        OM.look = orig
    assert (row["tpl"], row["kind"], row["rep"], row["lines"], row["form"], row["fix"]) == ("1~2a", "cut", "p3", 3, 0, [])   # 대표를 그 줄로 옮기지 않는다


def test_rank_orders_variant_and_composite_templates_without_crashing():
    # 전에는 int(번호) 라 서식 종속 템플릿 「1L2a」 · 종속 템플릿 「1T3」 에서 떨어졌다
    ov = {"templates": {"1": {"no": 1}, "2": {"no": 2}, "1~2a": {"no": "1L2a", "variant": {"of": "1", "level": 2, "sfx": "a"}},
                        "1~3a": {"no": "1L3a", "variant": {"of": "1", "level": 3, "sfx": "a"}}, "1T3": {"no": "1T3"}}}
    assert sorted(ov["templates"], key=lambda t: MR._rank(ov, t)) == ["1", "1~2a", "1~3a", "2", "1T3"]


@pytest.fixture
def emph(monkeypatch):
    """비교 값 = 서식 이름 + 본문 강조(bold) — same 은 모두 견준다(진짜처럼: 강조가 다르면 다른 서식)."""
    looks = {}
    monkeypatch.setattr(OM, "look", lambda doc, ov, p: looks[p])
    monkeypatch.setattr(OM, "same", lambda a, b: a == b)
    monkeypatch.setattr(OM, "near", lambda a, b, tol: False)
    monkeypatch.setattr(OM, "_tolerance", lambda: {})
    monkeypatch.setattr(OM, "_alive", lambda doc, p: True)
    monkeypatch.setattr(OM, "lone_value", lambda doc, ov, p: False)
    monkeypatch.setattr(OM, "_order", lambda doc: {f"p{i}": i for i in range(100)})
    monkeypatch.setattr(OM, "rep_shape", lambda doc, ov, p: {})

    def make(lines, reps):
        ov = {"lines": {}, "templates": {}}
        for p, (t, lv, f, bold) in lines.items():
            ov["lines"][p] = {"tpl": t, "level": lv, "role": "heading"}
            looks[p] = {"f": f, "bold": bold, "L.bold": False}
            ov["templates"].setdefault(t, {"no": int(t), "slots": {}})["slots"].setdefault(str(lv), {"letter": "-", "rep": reps.get((t, lv))})
        return ov
    return make


def test_keep_levels_see_emphasis_only_differences_as_the_same_format(emph):
    # 넣은 줄만 있는 레벨(grown): 원본에서 굵은 소제목이던 「-」 둘(p2 · p4 — 본문 굵게)과 보통 「-」 둘(p1 · p3) + 다른 서식 p5.
    # 굵기만 다른 줄은 같은 서식 — 맞출 줄이 아니고(그 줄의 굵기는 지킨다) 가장 많은 서식도 그것을 함께 센다
    ov = emph({"p1": ("1", 4, "S1", False), "p2": ("1", 4, "S1", True), "p3": ("1", 4, "S1", False), "p4": ("1", 4, "S1", True), "p5": ("1", 4, "S2", False),
               "p6": ("1", 4, "S2", False)}, {("1", 4): "p5"})
    (row,) = MR.plan(None, ov, {"p1", "p2", "p3", "p4", "p5", "p6"})["rows"]
    assert (row["kind"], row["rep"], row["fix"], row["same"]) == ("grown", "p1", ["p5", "p6"], ["p1", "p2", "p3", "p4"])
    # 목적 문서의 서식을 따르는 레벨(form): 강조까지 대표 것 — 굵기만 다른 넣은 줄도 맞출 줄
    ov2 = emph({"p10": ("2", 1, "S1", False), "p11": ("2", 1, "S1", False), "p12": ("2", 1, "S1", True)}, {("2", 1): "p10"})
    (row2,) = MR.plan(None, ov2, {"p11", "p12"})["rows"]
    assert (row2["kind"], row2["rep"], row2["fix"], row2["same"]) == ("form", "p10", ["p12"], ["p11"])
    assert set(MR.KEEP) == {"grown", "deep", "cut"} and "bold" in OM.EMPH and "L.bold" not in OM.EMPH
    # 새로 고르는 대표는 그 묶음에서 가장 많은 강조의 줄 — 굵은 소제목(p20)이 먼저 나와도 내용(보통)의 줄(Enter 로 만든 새 줄이 그 모양을 받는다) · 지금 대표가 그 묶음이면 그대로
    ov3 = emph({"p20": ("3", 2, "S1", True), "p21": ("3", 2, "S1", False), "p22": ("3", 2, "S1", False)}, {("3", 2): None})
    (row3,) = MR.plan(None, ov3, {"p20", "p21", "p22"})["rows"]
    assert (row3["rep"], row3["fix"], row3["same"]) == ("p21", [], ["p20", "p21", "p22"])
    ov3["templates"]["3"]["slots"]["2"]["rep"] = "p20"
    assert MR.plan(None, ov3, {"p20", "p21", "p22"})["rows"][0]["rep"] == "p20"


@pytest.fixture
def etree(monkeypatch):
    """부모가 있는 개요 오버레이 + 본문 강조(bold) — same 은 모두 견준다(강조가 다르면 다른 서식)."""
    looks = {}
    monkeypatch.setattr(OM, "look", lambda doc, ov, p: looks[p])
    monkeypatch.setattr(OM, "same", lambda a, b: a == b)
    monkeypatch.setattr(OM, "near", lambda a, b, tol: False)
    monkeypatch.setattr(OM, "_tolerance", lambda: {})
    monkeypatch.setattr(OM, "_alive", lambda doc, p: True)
    monkeypatch.setattr(OM, "lone_value", lambda doc, ov, p: False)
    monkeypatch.setattr(OM, "_order", lambda doc: {f"p{i}": i for i in range(100)})
    monkeypatch.setattr(OM, "rep_shape", lambda doc, ov, p: dict(SHAPE))

    def make(lines, reps, keys=None):
        ov = {"lines": {}, "templates": {}, "branches": {}}
        for p, (t, lv, f, bold, parent) in lines.items():
            ov["lines"][p] = {"tpl": t, "no": int(t), "level": lv, "role": "heading", "parent": parent}
            looks[p] = {"f": f, "bold": bold, "L.bold": False}
            T = ov["templates"].setdefault(t, {"no": int(t), "anchor": f"A{t}", "chain": [], "slots": {}})
            T["slots"].setdefault(str(lv), {"letter": "1.", "key": (keys or {}).get((t, lv), "o"), "rep": reps.get((t, lv))})
        return ov
    return make, looks


def test_deep_left_level_stays_deep_on_the_second_press_after_kept_emphasis(etree):
    # 번호형 레벨(못 가름): 양식 줄 p2(S1 · 굵게 — 소제목) · 넣은 줄 p3 · p5(S1 · 보통 — 내용) · p4(S2 · 굵게 — 원본의 굵은 소제목)
    make, looks = etree
    ov = make({"p1": ("1", 1, "H", False, None), "p2": ("1", 2, "S1", True, "p1"), "p3": ("1", 2, "S1", False, "p1"), "p4": ("1", 2, "S2", True, "p1"),
               "p5": ("1", 2, "S1", False, "p1")}, {("1", 1): "p1", ("1", 2): "p2"}, keys={("1", 2): "N."})
    ins = {"p3", "p4", "p5"}
    cuts, left = MR.cut_all(None, ov, ins)
    assert cuts == [] and [x["level"] for x in left] == [2]
    rows = MR.plan(None, ov, ins)["rows"]
    assert [(r["kind"], r["rep"], r["fix"]) for r in rows] == [("deep", "p3", ["p4"])]
    assert MR.mark(ov, rows) == 1 and ov["templates"]["1"]["slots"]["2"][OM.RETIDY_DEEP] == {"rep": "p3", "lines": ["p3", "p4", "p5"]}
    looks["p4"] = {**looks["p3"], "bold": True}   # 반영(KEEP): p4 가 대표 서식 + 제 굵기 — 양식 소제목 p2 와 서식이 같아졌다
    bare = copy.deepcopy(ov)
    bare["templates"]["1"]["slots"]["2"].pop(OM.RETIDY_DEEP)
    assert MR.plan(None, bare, ins)["rows"][0]["kind"] == "form"   # 표가 없으면 form 으로 바뀌어 내용(p3 · p5)이 소제목 모양이 된다(전의 결함)
    assert MR.cut_all(None, ov, ins)[0] == []
    rows2 = MR.plan(None, ov, ins)["rows"]
    assert [(r["kind"], r["rep"], r["fix"], r["same"]) for r in rows2] == [("deep", "p3", [], ["p3", "p4", "p5"])]   # 두 번째 누름 — 할 것 없음 · 대표 그대로
    MR.mark(ov, rows2)
    assert ov["templates"]["1"]["slots"]["2"][OM.RETIDY_DEEP]["lines"] == ["p3", "p4", "p5"]   # 다시 적어도 그 줄들(합침)
    # 2단계를 다시 돌려 새로 만든 오버레이에도 표가 옮겨진다(carry — 그 줄이 같은 템플릿 · 레벨일 때)
    fresh = copy.deepcopy(bare)
    assert OM.carry(ov, fresh) == [] and fresh["templates"]["1"]["slots"]["2"][OM.RETIDY_DEEP] == {"rep": "p3", "lines": ["p3", "p4", "p5"]}
    assert MR.plan(None, fresh, ins)["rows"][0]["kind"] == "deep"


def test_carry_does_not_drag_a_form_line_into_the_cut_template(tree):
    # 넣은 내용 p3(L2) · p4(L3) 를 뗐다(양식 줄 p5 는 stop). 다시 분석한 그래프가 양식 줄 p8(L4 — 원래 양식 p7 아래)을 넣은 줄 p4 의 아이로 읽었다
    lines = {"p1": ("1", 1, "H", None), "p2": ("1", 2, "B", "p1"), "p7": ("1", 3, "F", "p2"), "p8": ("1", 4, "G", "p7"), "p3": ("1", 2, "S7", "p1"),
             "p4": ("1", 3, "S8", "p3"), "p5": ("1", 3, "F", "p3")}
    ov = tree(lines, {("1", 1): "p1", ("1", 2): "p2", ("1", 3): "p7", ("1", 4): "p8"})
    fresh = copy.deepcopy(ov)
    cuts, _ = MR.cut_all(None, ov, {"p3", "p4"})
    assert [c["id"] for c in cuts] == ["1~2a"] and _tpls(ov, "p3", "p4", "p5", "p8") == {"p3": "1~2a", "p4": "1~2a", "p5": "1", "p8": "1"}
    fresh["lines"]["p8"]["parent"] = "p4"
    fresh["lines"]["p9"] = {"tpl": "1", "no": 1, "level": 4, "role": "heading", "parent": "p4"}   # 옛 오버레이에 없던 줄(뗀 뒤 Enter 로 만든 줄) — 전처럼 데려간다
    assert OM.carry(ov, fresh) == []
    assert _tpls(fresh, "p3", "p4", "p5", "p8", "p9") == {"p3": "1~2a", "p4": "1~2a", "p5": "1", "p8": "1", "p9": "1~2a"}
    assert fresh["splits"][0]["stop"] == ["p5", "p8"] and fresh["templates"]["1~2a"]["variant"]["side"] == "ins"


# ---------------------------------------------------------------- 취합에 걸기 · 사람이 고른 넘친 줄(2026-11-22 — spec_병합 ② §5-9 9 · 3-1)
def test_record_ids_and_within_are_the_old_inserted():
    blocks = [{"id": "p1"}, {"id": "t2", "cells": [{"id": "c1", "blocks": [{"id": "p3"}]}]}, {"id": "p4"}]
    rec = {"applied": {"a": {"ids": ["t2"], "over": {"lines": [{"id": "p4"}]}}}, "filled": {"ids": ["p1"]}}
    assert MR.record_ids(rec) == {"t2", "p4", "p1"} and MR.within(blocks, MR.record_ids(rec)) == MR.inserted(blocks, rec) == {"p1", "t2", "p3", "p4"}
    assert MR.within(blocks, ()) == set() and MR.record_ids(None) == set()


def test_cells_written_by_the_table_paths_bring_their_paragraphs():
    """표 묶음 · 표 대응이 글을 쓴 칸(filled.cells — 칸 id)의 문단도 넣은 줄이다(2026-11-23 실제 이관: 성능 목표 표의 「1. 선내 데이터 …」 가 원본의 두 문단 모양 그대로 들어와
    「≈」 로 남았는데, 칸 채움이 넣은 기록에 없어 넣은 뒤 서식 정리가 그 줄을 못 봤다). 칸 id 자체는 블록이 아니라 결과에 안 든다 · 다른 칸의 문단은 안 든다."""
    blocks = [{"id": "t1", "cells": [{"id": "c1", "blocks": [{"id": "p2"}, {"id": "p3"}]}, {"id": "c2", "blocks": [{"id": "p4"}]}]}]
    rec = {"filled": {"ids": [], "cells": ["c1"]}}
    assert MR.record_ids(rec) == {"c1"} and MR.inserted(blocks, rec) == {"p2", "p3"}


def test_gather_ids_read_body_records_of_parts_and_gone_but_not_cells_or_rows():
    from app import merge_gather as MG
    assert MR.GATHER_BODY == MG.BODY   # 취합의 본문 기록 kind 와 같아야 한다(merge_gather 를 가져오지 않으려 따로 둔다)
    G = {"parts": {"A": {"applied": {"k1": {"kind": "added", "ids": ["p1", "t2"], "convert": {"over": {"key": "o1", "lines": [{"id": "p9"}]}}},
                                     "k2": {"kind": "cells", "ids": ["c1", "c2"]}, "k3": {"kind": "rows", "ids": ["c3"]}}},
                   "B": {"applied": {"k4": {"kind": "filled", "ids": ["p5"]}}}, "C": {"name": "기록 없음"}},
         "gone": {"D": {"applied": {"k5": {"kind": "added", "ids": ["p7"]}}}}}
    assert MR.gather_ids(G) == {"p1", "t2", "p9", "p5", "p7"}   # 칸 id(c1 · c2 · c3)는 넣은 줄이 아니다 · 뺀 기관 문서(D)의 것도
    assert MR.gather_ids({}) == set() and MR.gather_ids(None) == set()
    assert [o["key"] for o in MR.overs(G, gather=True)] == ["o1"]
    rec = {"applied": {"a": {"over": {"key": "r1", "lines": []}}, "b": {"ids": ["x"]}}}
    assert [o["key"] for o in MR.overs(rec)] == ["r1"] and MR.overs({}, gather=True) == []


def test_held_ids_are_the_lines_of_cases_the_person_chose():
    recs = [{"key": "o1", "lines": [{"id": "p1"}, {"id": "p2"}]}, {"key": "o2", "lines": [{"id": "p3"}]}, {"key": "o3", "lines": [{"id": None}]}]
    assert MR.held_ids(recs, {"o1": {"mode": "cover"}, "o3": {"mode": "edit"}}) == {"p1", "p2"}   # 「덮은 템플릿 그대로」 를 고른 것도 · 고르지 않은 사례(o2)는 아니다
    assert MR.held_ids(recs, {}) == set() and MR.held_ids(None, {"o1": {}}) == set()


def test_plan_keeps_the_lines_the_person_chose_out_of_fix_same_and_reps(fake):
    make, _, _ = fake
    # 넣은 줄만 있는 레벨(grown) — p11 · p13 · p14(S7 — 가장 많다 · p11 은 사람이 고른 넘친 줄) · p10 · p12(S5)
    ov = make({"p10": ("2", 2, "S5"), "p11": ("2", 2, "S7"), "p12": ("2", 2, "S5"), "p13": ("2", 2, "S7"), "p14": ("2", 2, "S7")}, {("2", 2): "p11"})
    ins = {"p10", "p11", "p12", "p13", "p14"}
    P = MR.plan(None, ov, ins, keep={"p11", "p13"})
    (row,) = P["rows"]
    assert row["held"] == ["p11", "p13"] and P["held"] == ["p11", "p13"]
    assert row["rep"] not in ("p11", "p13") and not {"p11", "p13"} & set(row["fix"] + row["same"] + row["near"] + row["own"])   # 맞추지 않고 대표 후보도 아니다
    assert (row["rep"], row["lines"], row["fix"]) == ("p10", 3, ["p14"])   # 남은 줄끼리(S5 둘 · S7 하나)
    assert MR.summary(P["rows"])["held"] == 2
    # 그 레벨의 넣은 줄이 모두 사람이 고른 줄이면 줄이 없다 — 수는 plan 의 held 로
    P2 = MR.plan(None, ov, ins, keep=ins)
    assert P2["rows"] == [] and len(P2["held"]) == 5 and MR.summary(P2["rows"], held=P2["held"])["held"] == 5 and MR.summary(P2["rows"])["held"] == 0


def test_plan_without_near_leaves_form_lines_alone(fake):
    make, near, _ = fake
    near.add("S1b")
    ov = make({"p1": ("1", 1, "S1"), "p2": ("1", 1, "S1b"), "p6": ("1", 1, "S1"), "p7": ("1", 1, "S2")}, {("1", 1): "p1"})
    (with_near,) = MR.plan(None, ov, {"p6", "p7"})["rows"]
    (no_near,) = MR.plan(None, ov, {"p6", "p7"}, near=False)["rows"]
    assert with_near["near"] == ["p2"] and no_near["near"] == [] and (no_near["kind"], no_near["rep"], no_near["fix"]) == ("form", "p1", ["p7"])   # 취합 — 취합본의 「≈」 줄은 건드리지 않는다


def test_cut_does_not_pick_a_held_line_as_the_new_templates_rep(tree):
    ov = tree({"p1": ("1", 1, "H", None), "p2": ("1", 2, "B", "p1"), "p3": ("1", 2, "S7", "p1"), "p6": ("1", 2, "S7", "p1")}, {("1", 1): "p1", ("1", 2): "p2"})
    cuts, left = MR.cut_all(None, ov, {"p3", "p6"}, keep={"p3"})
    assert left == [] and [c["id"] for c in cuts] == ["1~2a"]
    assert ov["templates"]["1~2a"]["slots"]["2"]["rep"] == "p6" and ov["lines"]["p3"]["tpl"] == "1~2a"   # 사람이 고른 줄(p3)도 같이 옮기되(오버레이만) 대표는 다른 줄
    (row,) = MR.plan(None, ov, {"p3", "p6"}, keep={"p3"})["rows"]
    assert (row["kind"], row["rep"], row["held"], row["lines"]) == ("cut", "p6", ["p3"], 1)


def test_conform_without_rules_only_matches_and_freeze_sets_the_slot_shape(monkeypatch):
    """취합의 넣은 뒤 정리(spec_병합 ② §5-9 9 ⓐ) — 대표가 ①② 를 갖추지 않은 레벨에서 넣은 줄은 역변환 스크립트(outline_conform.conform)의 rules=False 로 대표의 모양만 받고
    (그 길을 따로 두지 않는다) · 대표(넣은 줄)에 ①② 를 건 뒤에는 슬롯의 동결 모양도 그것으로(outline_conform.freeze — settle 과 같다: Enter 로 만드는 새 줄)."""
    from app import outline_conform as OC
    seen = []
    monkeypatch.setattr(OM, "match_one", lambda doc, ov, p, sh, left: seen.append(("match", p, sh)))
    monkeypatch.setattr(OC, "place", lambda doc, ov, p, m: seen.append(("place", p)) or True)
    OC.conform(None, {}, "p1", {"x": 1}, None, rules=False)
    OC.conform(None, {}, "p2", {"x": 1}, None)
    assert seen == [("match", "p1", {"x": 1}), ("match", "p2", {"x": 1}), ("place", "p2")]
    ov = {"templates": {"1": {"slots": {"2": {"rep": "p1", "prefix": "o ", "letter": "o", "agentRep": "p1"}}}}}
    OC.freeze(ov, "1", 2, {"prefix": "o" + OC.NB, "tok": "o", "attrs": {"para": 3}, "body": {"char": 4}})
    assert ov["templates"]["1"]["slots"]["2"] == {"rep": "p1", "prefix": "o" + OC.NB, "letter": "o", "attrs": {"para": 3}, "bodyChar": {"char": 4}, "agentRep": "p1"}


# ---------------------------------------------------------------- 넣은 줄의 레터 — 위 레벨과 같은 레터를 쓰지 않는다(spec_병합 ② §5-9 11 · merge_retidy.reletter_of · reletter)
def _lettered(tree):
    """연차보고서 「□ 평가항목 › ㅇ (2차년도) 추진 내용 및 실적 › - (추진 내용)」(T1 — 가장 긴 사슬 □ › o › - › ·) 아래(문서 차례로 「- (추진 내용)」 바로 뒤) 넣은 「o › - › ⋅」(T2 — 목적 문서에 없던 레벨).
    다시 분석한 그래프는 넣은 「o」 를 같은 레터인 「ㅇ」 와 같은 레벨로 읽어 부모를 「□」(p1)로 둔다 — 넣은 자리(p3)는 문서 차례로 잡는다. 양식의 「⋅」 줄(p20)은 넣은 내용 뒤."""
    ov = tree({"p1": ("1", 1, "F1", None), "p2": ("1", 2, "F2", "p1"), "p3": ("1", 3, "F3", "p2"), "p20": ("1", 4, "F4", "p3"),
               "p10": ("2", 1, "S1", "p1"), "p11": ("2", 2, "S2", "p10"), "p12": ("2", 3, "S3", "p11"), "p13": ("2", 2, "S2", "p10")},
              {("1", 1): "p1", ("1", 2): "p2", ("1", 3): "p3", ("1", 4): "p20", ("2", 1): "p10", ("2", 2): "p11", ("2", 3): "p12"})
    for p, (letter, key) in {"p1": ("□", "□"), "p2": ("ㅇ", "o"), "p3": ("-", "-"), "p20": ("⋅", "·"), "p10": ("o", "o"), "p11": ("-", "-"), "p12": ("⋅", "·"), "p13": ("-", "-")}.items():
        x = ov["lines"][p]
        x.update(letter=letter, key=key)
        ov["templates"][x["tpl"]]["slots"][str(x["level"])].update(letter=letter, key=key)
    ov["templates"]["1"]["chain"], ov["templates"]["2"]["chain"] = ["□", "o", "-", "·"], ["o", "-", "·"]
    return ov


def test_inserted_levels_that_repeat_an_upper_letter_take_the_next_free_letter_of_the_longest_chain(tree):
    """위 레벨(넣을 자리 「-」 · 그 위 「ㅇ」 · 「□」)과 같은 레터를 쓰는 넣은 레벨 — 가장 긴 사슬(□ › o › - › ·)에서 처음 안 겹치는 레터, 모자라면 덧붙인 기호(사용자 답 「기호를 더 씀」).
    아래 레벨은 바꾼 위 레벨의 레터와도 안 겹치게(「⋅」 는 첫 레벨이 「⋅」 가 되어 다시 바뀐다) · 글자는 그 키로 문서에 친 글자(「·」 키 → 「⋅」)."""
    ov = _lettered(tree)
    ins = {"p10", "p11", "p12", "p13"}
    assert [(k, g) for k, g in MR.pool(ov)][:4] == [("□", "□"), ("o", "ㅇ"), ("-", "-"), ("·", "⋅")] and [k for k, _ in MR.pool(ov)][4:] == list(MR.EXTRA)
    got = MR.reletter_of(None, ov, ins)
    assert [(r["tpl"], r["level"], r["was"], r["now"], sorted(r["lines"]), r["why"]) for r in got] == [
        ("2", 1, "o", "⋅", ["p10"], None), ("2", 2, "-", "▪", ["p11", "p13"], None), ("2", 3, "⋅", "◦", ["p12"], None)]
    assert ov["lines"]["p10"]["letter"] == "o"   # 계획만 — 오버레이는 그대로
    c = MR.summary(MR.plan(None, ov, ins)["rows"], relet=got)
    assert (c["letters"], c["letterSwaps"], c["lettersLeft"]) == (3, ["o → ⋅", "- → ▪", "⋅ → ◦"], 0)
    # 「ㅇ › - (정의)」 아래 넣은 「-」(위 줄에 「□」 가 없다) — 차례의 처음(「□」)이 아니라 위 줄이 쓴 가장 깊은 레터(「-」) 다음부터: 「⋅」
    ov2 = _lettered(tree)
    ov2["lines"]["p2"]["parent"] = None
    ov2["lines"]["p1"].update(letter="1.", key="N.")
    got2 = MR.reletter_of(None, ov2, {"p10", "p11", "p12", "p13"})
    assert [(r["level"], r["was"], r["now"]) for r in got2][:1] == [(1, "o", "⋅")]


def test_reletter_writes_the_letter_line_by_line_and_the_slot_key_and_chain_follow(tree, monkeypatch):
    ov = _lettered(tree)
    ins = {"p10", "p11", "p12", "p13"}
    seen = []

    def match_one(doc, ov_, pid, sh, left=None):   # 진짜는 접두를 다시 쓰고 오버레이의 레터를 그 글자로(outline_match.match_one)
        seen.append((pid, sh["tok"], sh["prefix"]))
        ov_["lines"][pid]["letter"] = sh["tok"]
    monkeypatch.setattr(OM, "match_one", match_one)
    monkeypatch.setattr(OM, "_is_auto", lambda ov_, p: False)
    changed = MR.reletter(None, ov, MR.reletter_of(None, ov, ins))
    assert sorted(changed) == ["p10", "p11", "p12", "p13"] and ("p11", "▪", "▪ ") in seen   # 줄마다 제 모양(레터 앞 · 뒤 빈칸)에 레터만
    assert [(ov["lines"][p]["letter"], ov["lines"][p]["key"]) for p in ("p10", "p11", "p12", "p13")] == [("⋅", "·"), ("▪", "▪"), ("◦", "◦"), ("▪", "▪")]
    S = ov["templates"]["2"]["slots"]
    assert [(S[k]["letter"], S[k]["key"]) for k in ("1", "2", "3")] == [("⋅", "·"), ("▪", "▪"), ("◦", "◦")] and ov["templates"]["2"]["chain"] == ["·", "▪", "◦"]
    assert MR.reletter_of(None, ov, ins) == []   # 두 번째 누름 — 겹치는 레터 없음


def test_inserted_levels_that_do_not_repeat_an_upper_letter_keep_their_letters(tree, monkeypatch):
    """문서 차례로 「□」 바로 뒤(넣은 자리 = 「□」)에 넣은 「o › - › ⋅」 — 위 레벨(□)과 안 겹친다: 그대로. 목적 문서의 줄이 있는 레벨 · 사람이 처리를 고른 줄이 든 레벨은 건드리지 않는다."""
    ov = _lettered(tree)
    monkeypatch.setattr(OM, "_order", lambda doc: {"p1": 1, "p10": 2, "p11": 3, "p12": 4, "p13": 5, "p2": 6, "p3": 7, "p20": 8})
    assert MR.reletter_of(None, ov, {"p10", "p11", "p12", "p13"}) == []
    monkeypatch.setattr(OM, "_order", lambda doc: {f"p{i}": i for i in range(100)})
    assert [r["level"] for r in MR.reletter_of(None, ov, {"p10", "p11", "p13"})] == [1, 2]   # p12(⋅)는 넣은 줄이 아니다 → 그 레벨(L3)은 목적 문서의 줄(form) — 안 바꾼다
    got = MR.reletter_of(None, _lettered(tree), {"p10", "p11", "p12", "p13"}, keep={"p11"})
    assert [(r["level"], r["now"], r["why"]) for r in got if r["level"] == 2] == [(2, None, "사람이 넘친 레벨의 처리를 고른 줄이 있어 그대로 둠")]
