"""템플릿 변환(app/merge_convert) — 작은 쌍(tests/merge_data.small): 원본 계획서의 □›o›-›· 사슬(L1~L4) + 본문 줄을 연차보고서 기관 소제목([…]›□›o›- 의 L1) 아래 복사해 바꾼다."""
import pytest

from app import hwpx_struct
from app import merge_convert as MC
from app.hwpx_doc import HwpxDoc
from app.outline_edit import body_of, prefix_of
from tests import merge_data as M

SRC_TPL, TO_TPL = "body:□›o›-›·", "body:[…]›□›o›-"


@pytest.fixture(scope="module")
def S():
    return M.small()


def _src_lines(S):
    """원본 첫 □ 인스턴스의 □ … ⋅(L4) 까지 블록 id(사이 빈 줄 포함)."""
    nodes = S["from"]["graph"]["nodes"]
    top = next(n for n in nodes if n["template"] == SRC_TPL and n["level"] == 1)
    leaf = next(n for n in nodes if n["template"] == SRC_TPL and n["level"] == 4 and n["instance"] == top["instance"])
    ids = [b["id"] for b in S["from"]["doc"].blocks()]
    return ids[ids.index(top["para"]):ids.index(leaf["para"]) + 1]


def _anchor(S, leaf=False):
    nodes = S["to"]["graph"]["nodes"]
    if leaf:
        return next(n["para"] for n in nodes if n["template"] == TO_TPL and (n.get("text") or "").startswith("(추진 내용)"))
    return next(n["para"] for n in nodes if n["template"] == TO_TPL and n["level"] == 1 and "주관" in (n.get("letter") or ""))


def test_convert_small(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src = _src_lines(S)
    letters = {n["para"]: n["letter"] for n in fg["nodes"] if n["para"] in src and n.get("level")}
    frm, to = M.fresh(S["from"]), M.fresh(S["to"])
    frm.blocks(), to.blocks()  # 블록 id 붙이기
    body_id = next(s for s in src if s not in letters)
    for k, s in enumerate(src):  # 글을 넣는다(블록 id·레터는 그대로라 그래프가 그대로 맞다)
        t = frm._text(frm._ids[s])
        frm.set_text(s, (t.rstrip() + f" 내용{k} 가나다") if s in letters else ("본문 줄 그대로" if s == body_id else t))
    o_id = next(s for s in src if letters.get(s) == "o")
    ot = frm._text(frm._ids[o_id])
    frm.format_chars(o_id, len(ot) - 3, len(ot), {"bold": True})  # 따로 강조한 런
    before = {s: frm._text(frm._ids[s]) for s in src}

    anchor = _anchor(S)
    new = to.insert_after(anchor, [{"kind": "copy", "srcId": s} for s in src], src=frm)
    pairs = list(zip(src, new))
    res = MC.converter(to, tg, fg)(anchor, pairs)

    p = res["plan"]
    assert p["base"] == [SRC_TPL, 1] and p["anchor"] == [TO_TPL, 1] and not p["anchorLeaf"]
    rows = {r["src"]: r for r in MC.plan(tg, fg, anchor, src)["rows"]}
    assert [rows[s]["slot"] for s in src if letters.get(s) in ("□", "o", "-")] == [[TO_TPL, 2], [TO_TPL, 3], [TO_TPL, 4]]
    deep = next(s for s in src if letters.get(s) not in (None, "□", "o", "-"))
    assert rows[deep]["why"] == "tooDeep"
    n_body = sum(1 for s in src if s not in letters)
    assert res["converted"] == 3 and res["kept"] == {"body": n_body, "tooDeep": 1}

    new_of = dict(pairs)
    for s in src:
        nid, r = new_of[s], rows[s]
        text = to._text(to._ids[nid])
        if r["why"]:  # 그대로 둔 줄 — 원본 글 그대로
            assert text == before[s]
            continue
        like = to.para_attrs(r["like"])
        assert prefix_of(text, r["letter"])[1] == r["letter"] == prefix_of(to._text(to._ids[r["like"]]), r["likeLetter"])[1]
        assert to.para_attrs(nid) == like  # 문단 속성·스타일·첫 글 런 글자 모양 = 같은 자리의 목적 줄
        assert body_of(text, r["letter"]) == body_of(before[s], letters[s])
    runs = [r.get("charPrIDRef") for r in to._ids[new_of[o_id]].iterchildren(hwpx_struct.RUN)]
    assert any(to._is_bold(c) for c in runs) and to.para_attrs(rows[o_id]["like"])["charPrIDRef"] in runs  # 강조 런은 남고 나머지는 목적 모양

    again = HwpxDoc(hwpx_struct.snapshot(to)["bytes"])  # 다시 열림
    texts = [b.get("text") or "" for b in again.blocks()]
    assert any("본문 줄 그대로" in t for t in texts) and sum("가나다" in t for t in texts) == 4


def test_plan_leaf_anchor_and_numbering(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src = _src_lines(S)
    leaf = MC.plan(tg, fg, _anchor(S, leaf=True), src)  # 「- (추진 내용)」 = 템플릿 마지막 레벨 → 자식 자리 없음
    assert leaf["summary"]["anchorLeaf"] and leaf["summary"]["convertible"] == 0
    assert {r["why"] for r in leaf["rows"]} == {"tooDeep", "body"}

    tops = [n["para"] for n in fg["nodes"] if n["template"] == SRC_TPL and n["level"] == 1][:2]  # 두 □ 인스턴스 → 「2.」 아래 N-N. 자리(번호형)
    two = next(n["para"] for n in tg["nodes"] if (n["template"] or "").startswith("body:N.›N-N.") and n["letter"] == "2.")
    got = [r["letter"] for r in MC.plan(tg, fg, two, tops)["rows"]]
    assert got == ["2-1.", "2-2."]


# ---- 넘친 개요 레벨(spec_병합 ② §5-5): 자리 템플릿보다 깊은 줄 = 사례 · over 지정 · 반영 기록 ---------------------------------

def _copied(S, anchor, src):
    """원본 줄에 글을 넣고 anchor 뒤에 복사한 것 → (목적 문서, 원본 문서, [(원본 id, 사본 id)], {원본 id: 원본 레터})."""
    letters = {n["para"]: n["letter"] for n in S["from"]["graph"]["nodes"] if n["para"] in src and n.get("level")}
    frm, to = M.fresh(S["from"]), M.fresh(S["to"])
    frm.blocks(), to.blocks()
    for k, s in enumerate(src):
        if s in letters:
            frm.set_text(s, frm._text(frm._ids[s]).rstrip() + f" 넘침{k}")
    new = to.insert_after(anchor, [{"kind": "copy", "srcId": s} for s in src], src=frm)
    return to, frm, list(zip(src, new)), letters


def test_over_default_is_the_source_shape_and_reports_the_case(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src, anchor = _src_lines(S), _anchor(S)
    p = MC.plan(tg, fg, anchor, src)
    deep = next(r for r in p["rows"] if r["why"] == "tooDeep")
    ov = p["summary"]["over"]
    assert deep["over"] == 1 and deep["slot"] is None   # 넘친 줄 — 지정이 없으면 전처럼 그대로 둔다
    assert ov["key"] == f"{TO_TPL}<·" and ov["to"] == [TO_TPL, 4] and ov["from"] == [SRC_TPL, 4] and ov["tail"] == ["·"] and ov["lines"] == 1
    assert [(x["n"], x["src"], x["key"], x["lines"], x["rep"]) for x in ov["levels"]] == [(5, 4, "·", 1, deep["src"])] and ov["levels"][0]["was"] == deep["was"]
    assert MC.plan(tg, fg, anchor, src, over={})["rows"] == p["rows"] and MC.plan(tg, fg, anchor, src, over={"다른 사례": [{"letter": "x"}]})["rows"] == p["rows"]
    assert "over" not in MC.plan(tg, fg, anchor, [s for s in src if s != deep["src"]])["summary"]   # 넘친 줄이 없으면 사례도 없다
    leaf = MC.plan(tg, fg, _anchor(S, leaf=True), src)["summary"]["over"]   # 마지막 레벨 자리 — 내용 전부가 넘친다(꼬리 = 원본 사슬 전체)
    assert leaf["key"] == f"{TO_TPL}<□›o›-›·" and leaf["from"] == [SRC_TPL, 1] and [x["n"] for x in leaf["levels"]] == [5, 6, 7, 8] and leaf["lines"] == 4

    to, frm, pairs, letters = _copied(S, anchor, src)
    before = {n: to._text(to._ids[n]) for _, n in pairs}
    res = MC.converter(to, tg, fg)(anchor, pairs)
    nid = dict(pairs)[deep["src"]]
    assert to._text(to._ids[nid]) == before[nid] and res["kept"]["tooDeep"] == 1   # 문서 결과는 이 기능 전과 같다
    (line,) = res["lines"]   # 넘친 줄은 그대로 두어도 적어 둔다(다시 맞추기의 근거)
    assert (line["id"], line["src"], line["over"], line["was"], line["letter"]) == (nid, deep["src"], 1, letters[deep["src"]], letters[deep["src"]])
    assert before[nid].startswith(line["orig"]["prefix"]) and line["orig"]["attrs"] == to.para_attrs(nid) and line["parent"] == dict(pairs)[deep["parent"]]
    assert res["over"] == {"key": ov["key"], "to": ov["to"], "lines": res["lines"]} == MC.record(p["summary"], res)


def test_over_spec_shapes_the_line_like_a_target_level_or_keeps_its_own_shape(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    src, anchor = _src_lines(S), _anchor(S)
    base = MC.plan(tg, fg, anchor, src)
    key, deep = base["summary"]["over"]["key"], next(r for r in base["rows"] if r["why"] == "tooDeep")["src"]
    like = next(r for r in base["rows"] if r["slot"] == [TO_TPL, 3])["like"]   # 목적 문서의 「o」 줄(자리 템플릿 L3 의 본보기)
    like_letter = next(n["letter"] for n in tg["nodes"] if n["para"] == like)

    to, frm, pairs, letters = _copied(S, anchor, src)   # 본보기가 있으면 맞는 레벨과 같은 길 — 접두·문단 속성·글자 모양이 본보기 것
    res = MC.converter(to, tg, fg, over={key: [{"like": like, "likeLetter": like_letter, "letter": None, "lead": None, "numbered": False}]})(anchor, pairs)
    nid = dict(pairs)[deep]
    row = next(r for r in MC.plan(tg, fg, anchor, src, over={key: [{"like": like}]})["rows"] if r["src"] == deep)
    assert (row["why"], row["slot"], row["like"], row["letter"], row["over"]) == (None, [TO_TPL, 5], like, like_letter, 1)
    assert res["converted"] == 4 and "tooDeep" not in res["kept"] and to.para_attrs(nid) == to.para_attrs(like)
    text, src_text = to._text(to._ids[nid]), frm._text(frm._ids[deep])
    assert prefix_of(text, like_letter)[1] == like_letter and body_of(text, like_letter) == body_of(src_text, letters[deep])
    (line,) = res["lines"]
    assert (line["was"], line["letter"]) == (letters[deep], like_letter) and src_text.startswith(line["orig"]["prefix"])   # 원본 접두가 기록에 남는다

    to, frm, pairs, letters = _copied(S, anchor, src)   # 본보기 없이 레터·앞 공백만 — 제 모양은 그대로
    nid = dict(pairs)[deep]
    attrs = to.para_attrs(nid)
    res = MC.converter(to, tg, fg, over={key: [{"like": None, "letter": "▪", "lead": 7, "numbered": False}]})(anchor, pairs)
    text = to._text(to._ids[nid])
    assert text.startswith(" " * 7 + "▪") and not text.startswith(" " * 8) and to.para_attrs(nid) == attrs and body_of(text, "▪") == body_of(frm._text(frm._ids[deep]), letters[deep])
    assert res["lines"][0]["letter"] == "▪" and res["converted"] == 4

    gone = MC.plan(tg, fg, anchor, src, over={key: [{"like": "?없는 본보기"}]})   # 본보기 문단이 그래프에 없다 → 원본 모양 그대로 + 까닭
    assert next(r for r in gone["rows"] if r["src"] == deep)["why"] == "noLike" and gone["summary"]["over"]["lines"] == 1


def test_over_numbered_letter_counts_from_one_under_each_parent(S):
    fg, tg = S["from"]["graph"], S["to"]["graph"]
    tops = [n["para"] for n in fg["nodes"] if n["template"] == SRC_TPL and n["level"] == 1][:2]   # 두 □ 줄을 마지막 레벨 자리(「- (추진 내용)」) 아래 — 둘 다 넘친 레벨 1
    leaf = _anchor(S, leaf=True)
    key = MC.plan(tg, fg, leaf, tops)["summary"]["over"]["key"]
    rows = MC.plan(tg, fg, leaf, tops, over={key: [{"like": None, "letter": "(3)", "numbered": True}]})["rows"]
    assert [(r["letter"], r["own"], r["why"]) for r in rows] == [("(1)", True, None), ("(2)", True, None)]
    rows = MC.plan(tg, fg, leaf, tops, over={key: [{"like": None, "letter": None, "lead": 2, "numbered": False}]})["rows"]   # 앞 공백만 고친 줄은 레터를 그대로
    assert [(r["letter"], r["lead"]) for r in rows] == [(r["was"], 2) for r in rows]
