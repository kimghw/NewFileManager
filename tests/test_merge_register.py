"""넘친 줄의 템플릿 등록(spec_병합 ② §5-12 — app/merge_register.py) + 뼈대 유지의 「확정 서식을 지키는 줄」(spec_헤딩_추출 ② §17 — heading_drift.confirmed).
자료 = 작은 쌍(tests/merge_data.small): 원본 □›o›-›· 사슬을 연차보고서의 마지막 레벨 자리 「- (추진 내용)」 아래 넣으면 네 줄이 모두 넘친다(test_merge_over 와 같은 쌍)."""
from types import SimpleNamespace

import pytest

from app import heading_drift as HD
from app import merge_convert as MC
from app import merge_register as MR
from app import outline_edit as OE
from app import outline_match as OM
from tests import merge_data as M
from tests.test_merge_over import _anchor, _docs, _src


@pytest.fixture(scope="module")
def S():
    return M.small()


def _ov(g, doc):
    from app import server
    return OE.build_overlay(g, server._outline_probe(SimpleNamespace(doc=doc)))


def _insert(S, to, frm, src, anchor, converted=None):
    new = to.insert_after(anchor, [{"kind": "copy", "srcId": s} for s in src], src=frm)
    res = MC.converter(to, S["to"]["graph"], S["from"]["graph"])(anchor, list(zip(src, new)))
    return res, new


def test_overflow_lines_join_a_dependent_template_under_the_anchor_level(S):
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, letters = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    res, _ = _insert(S, to, frm, src, anchor)
    ids = [x["id"] for x in res["over"]["lines"]]
    assert res["converted"] == 0 and len(ids) == 4   # 넘친 줄 넷 — 서식은 원본 그대로(바꾸지 않음)
    before = {i: (to._text(to._ids[i]), to.para_attrs(i)) for i in ids}
    reg = MR.register(to, ov_to, frm, ov_from, anchor, res["lines"], res["ids"], res["plan"])
    assert reg["lines"] == 4 and reg["new"] == 1 and reg["left"] == {}
    cid = reg["templates"][0]
    A = ov_to["lines"][anchor]
    C = ov_to["templates"][cid]
    K = int(A["level"])
    assert C["variant"] == {"of": A["tpl"], "level": K + 1, "sfx": "a", "by": MR.BY} and C["base"] == K and C["max"] == K + 4
    assert C["chain"][:K] == ov_to["templates"][A["tpl"]]["chain"][:K] and len(C["chain"]) == K + 4
    assert cid in ov_to["branches"][f"{A['tpl']}|{K}"]
    lines = [ov_to["lines"][i] for i in ids]
    assert [x["level"] for x in lines] == [K + 1, K + 2, K + 3, K + 4] and [x["tpl"] for x in lines] == [cid] * 4
    assert [x["parent"] for x in lines] == [anchor, ids[0], ids[1], ids[2]] and all(x["flow"] == A["flow"] for x in lines)
    assert {i: (to._text(to._ids[i]), to.para_attrs(i)) for i in ids} == before   # 문서는 안 바뀐다(소속만)
    reps = [C["slots"][str(K + j)] for j in range(1, 5)]
    assert all(sl["rep"] in ids and sl["attrs"] and sl["bodyChar"] and sl["prefix"] for sl in reps)   # 원본 대표와 같은 넣은 줄이 대표 · 동결 모양은 목적 문서의 그 줄
    assert set(HD.confirmed(to, ov_to, ids)) == set(ids)   # 뼈대 유지 — 제 슬롯의 확정 서식을 지키는 줄은 「새 서식」 · 「새 레터」 로 안 센다

    again, _ = _insert(S, to, frm, src, anchor)   # 같은 사례를 다시 넣음 — 같은 종속 템플릿에 더한다(중복 0)
    reg2 = MR.register(to, ov_to, frm, ov_from, anchor, again["lines"], again["ids"], again["plan"])
    assert reg2["templates"] == [cid] and reg2["new"] == 0 and reg2["lines"] == 4
    assert [t for t in ov_to["templates"].values() if (t.get("variant") or {}).get("by") == MR.BY] == [C]
    assert C["slots"][str(K + 1)]["count"] == 2


def test_lines_a_person_chose_to_reshape_stay_out_and_take_their_children_with_them(S):
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    res, _ = _insert(S, to, frm, src, anchor)
    first = res["over"]["lines"][0]["id"]
    reg = MR.register(to, ov_to, frm, ov_from, anchor, res["lines"], [first], res["plan"])   # 첫 줄은 사람이 고른 처리로 바꾼 줄(그 서식 그대로)
    assert reg == {"lines": 0, "templates": [], "new": 0, "left": {"chosen": 1, "parent": 3}}   # 부모를 등록 못 한 줄은 소속을 안 정한다 · 등록할 줄이 없으면 빈 템플릿도 안 만든다
    assert first not in ov_to["lines"] and not [t for t in ov_to["templates"].values() if (t.get("variant") or {}).get("by") == MR.BY]


def test_source_line_outside_the_source_overlay_is_not_registered(S):
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    res, _ = _insert(S, to, frm, src, anchor)
    ov_from["lines"].pop(res["over"]["lines"][0]["src"])   # 원본의 지금 오버레이에 없는 줄 — 소속을 확인할 수 없다
    reg = MR.register(to, ov_to, frm, ov_from, anchor, res["lines"], res["ids"], res["plan"])
    assert reg == {"lines": 0, "templates": [], "new": 0, "left": {"srcUnknown": 1, "parent": 3}}


def test_a_hand_changed_rep_stops_vouching_for_its_level(S):
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    res, _ = _insert(S, to, frm, src, anchor)
    ids = [x["id"] for x in res["over"]["lines"]]
    reg = MR.register(to, ov_to, frm, ov_from, anchor, res["lines"], res["ids"], res["plan"])
    C = ov_to["templates"][reg["templates"][0]]
    rep = C["slots"][str(int(ov_to["lines"][ids[1]]["level"]))]["rep"]
    lead, tok, gap = OE.prefix_of(to._text(to._ids[rep]), ov_to["lines"][rep]["letter"])
    to.set_text(rep, lead + tok + gap + "  " + OE.body_of(to._text(to._ids[rep]), tok).lstrip())   # 레터 뒤에 빈칸을 더 친 손 편집 — 접두가 동결 모양과 다르다
    assert OM.rep_shape(to, ov_to, rep)["gap"] != OE.prefix_of(C["slots"][str(int(ov_to["lines"][rep]["level"]))]["prefix"], tok)[2]
    assert set(HD.confirmed(to, ov_to, ids)) == set(ids) - {rep}   # 그 레벨은 지금처럼 뼈대와 견준다 — 다른 레벨은 그대로 앎


def test_a_deeper_second_insert_of_the_same_tail_extends_the_same_template(S):
    """같은 꼬리를 얕게 넣은 뒤 더 깊게 넣어도 종속 템플릿은 하나 — 사슬 · 슬롯이 늘어난다(종속 중복 0 · astra 3차 대비)."""
    src, anchor = _src(S), _anchor(S, leaf=True)
    lv = {n["para"]: n["level"] for n in S["from"]["graph"]["nodes"] if n["para"] in src and n.get("level")}
    cut = next(i for i, s in enumerate(src) if lv.get(s) == 3)   # 첫 두 레벨만
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    short, _ = _insert(S, to, frm, src[:cut], anchor)
    r1 = MR.register(to, ov_to, frm, ov_from, anchor, short["lines"], short["ids"], short["plan"])
    C = ov_to["templates"][r1["templates"][0]]
    assert r1["lines"] == 2 and len(C["chain"]) == int(ov_to["lines"][anchor]["level"]) + 2
    full, _ = _insert(S, to, frm, src, anchor)
    r2 = MR.register(to, ov_to, frm, ov_from, anchor, full["lines"], full["ids"], full["plan"])
    assert r2["templates"] == r1["templates"] and r2["new"] == 0 and r2["lines"] == 4
    assert len(C["chain"]) == int(ov_to["lines"][anchor]["level"]) + 4 and C["max"] == int(ov_to["lines"][anchor]["level"]) + 4
    assert len([t for t in ov_to["templates"].values() if (t.get("variant") or {}).get("by") == MR.BY]) == 1


def test_an_incompatible_second_copy_gets_its_own_template_and_a_level_clash_is_refused(S):
    """같은 꼬리라도 이미 있는 대표와 서식이 다르면 새 종속(「대표에 맞추기」 가 다른 서식을 덮지 않게) · 지금 오버레이의 A 에 K+1 이 있으면 등록 안 함(astra 3차)."""
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    first, _ = _insert(S, to, frm, src, anchor)
    r1 = MR.register(to, ov_to, frm, ov_from, anchor, first["lines"], first["ids"], first["plan"])
    second, _ = _insert(S, to, frm, src, anchor)
    top = second["over"]["lines"][0]["id"]
    to.set_text(top, "      " + to._text(to._ids[top]))   # 둘째 사본의 첫 줄만 레터 앞 빈칸이 다르다 — 그 레벨 대표와 서식이 다름
    r2 = MR.register(to, ov_to, frm, ov_from, anchor, second["lines"], second["ids"], second["plan"])
    assert r2["new"] == 1 and r2["templates"] != r1["templates"] and r2["templates"][0].endswith("b")

    to2, frm2, _ = _docs(S, src)
    ov2, ovf2 = _ov(S["to"]["graph"], to2), _ov(S["from"]["graph"], frm2)
    res, _ = _insert(S, to2, frm2, src, anchor)
    A = ov2["lines"][anchor]
    ov2["templates"][A["tpl"]]["slots"][str(int(A["level"]) + 1)] = {"letter": "x", "key": "x", "rep": None}   # 오버레이의 A 가 그래프보다 길다
    reg = MR.register(to2, ov2, frm2, ovf2, anchor, res["lines"], res["ids"], res["plan"])
    assert reg == {"lines": 0, "templates": [], "new": 0, "left": {"levelMismatch": 4}}


def test_the_rep_comes_from_lines_that_survive_the_parent_filter(S):
    """레벨의 대표 후보는 부모 거르기를 지난 줄에서 — 떨어진 줄이 대표 자리를 차지해 슬롯이 대표 없이 남지 않게(astra 3차)."""
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    a, _ = _insert(S, to, frm, src, anchor)
    b, _ = _insert(S, to, frm, src, anchor)
    lines = a["lines"] + b["lines"]
    chosen = [a["over"]["lines"][0]["id"]]   # 첫 사본의 첫 줄은 사람이 고른 처리 — 첫 사본은 모두 떨어진다
    reg = MR.register(to, ov_to, frm, ov_from, anchor, lines, chosen, a["plan"])
    C = ov_to["templates"][reg["templates"][0]]
    K = int(ov_to["lines"][anchor]["level"])
    assert reg["lines"] == 4 and reg["left"] == {"chosen": 1, "parent": 3}
    assert all(C["slots"][str(K + j)]["rep"] in {x["id"] for x in b["over"]["lines"]} for j in range(1, 5))


def test_merging_a_registered_tail_back_is_refused(S):
    """「합치기」(unsplit) — 넣은 꼬리는 A 에 그 레벨이 없어 합치면 슬롯 없는 줄이 된다: 거절(astra 3차)."""
    src, anchor = _src(S), _anchor(S, leaf=True)
    to, frm, _ = _docs(S, src)
    ov_to, ov_from = _ov(S["to"]["graph"], to), _ov(S["from"]["graph"], frm)
    res, _ = _insert(S, to, frm, src, anchor)
    cid = MR.register(to, ov_to, frm, ov_from, anchor, res["lines"], res["ids"], res["plan"])["templates"][0]
    with pytest.raises(ValueError, match="합칠 수 없습니다"):
        OM.unsplit(ov_to, cid)
    assert cid in ov_to["templates"]
