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
