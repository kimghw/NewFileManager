"""짝 표지(형광펜 · 필드 · 변경 추적)가 든 문단의 편집 — spec_owpml_편집 ② §2 「짝 표지」.

실제 HwpxDoc(samples/연구개발계획서_양식.hwpx)을 열고 본문 글 문단 하나의 런을 손으로 지은 런으로 갈아 끼워 시험한다.
반례의 출처: artifacts/markers_astra_2026-11-17/astra_answer.md(외부 검토 — 메모리 재현)."""
from functools import cache
from pathlib import Path

import pytest
from lxml import etree

from app.hwpx_doc import HP, HwpxDoc
from app.hwpx_struct import LINESEG, MARKERS, P, RUN, SECPR, T, TBL, MarkBlock, _p, top_host

SAMPLE = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
MP = '<hp:markpenBegin color="#FFFF00"/>'
ME = "<hp:markpenEnd/>"


@cache
def _bytes():
    return SAMPLE.read_bytes()


def _doc():
    return HwpxDoc(_bytes())  # blocks() 는 안 부른다(문단 id 는 _id 가 그때그때 붙인다 — 열기가 빨라짐)


def _body(d):
    """본문 글 문단(구역 바로 아래 · 개체·구역 설정·표지 없음 · 글 있음 · 뒤에 글 문단이 있음)."""
    for sec in d._sections:
        for p in sec.iterchildren(P):
            nxt = d._sibling(p, +1)
            if (d._text(p).strip() and not d._has_object(p) and next(p.iter(SECPR), None) is None and next(p.iter(*MARKERS), None) is None
                    and nxt is not None and not d._has_object(nxt) and next(nxt.iter(SECPR), None) is None):
                return p
    raise AssertionError("본문 글 문단이 없습니다")


def _put(d, runs, p=None):
    """문단 p(없으면 _body)의 런을 runs(XML — CID = 그 문단의 글자 모양 id · 런을 안 쓰면 hp:run 하나로 감싼다)로 갈아 끼운다 -> 문단 id."""
    p = _body(d) if p is None else p
    cid = d._char_id(p)
    if "<hp:run" not in runs:
        runs = f'<hp:run charPrIDRef="CID">{runs}</hp:run>'
    for c in list(p):
        if c.tag in (RUN, LINESEG):
            p.remove(c)
    for r in etree.fromstring(f'<x xmlns:hp="{HP}">{runs.replace("CID", cid)}</x>'):
        p.append(r)
    d._touch(p)
    return d._id(p)


def _spans(d, pid):
    return [(s["kind"], s["start"], s["end"]) for s in d.mark_spans(d._ids[pid])[0]]


def _xml(d, pid):
    return etree.tostring(d._ids[pid])


def _tags(d, pid, name):
    return len(list(d._ids[pid].iter(_p(name))))


# ---- 표지 읽기 -------------------------------------------------------------------------------------------------------

def test_own_marks_and_spans():
    d = _doc()
    pid = _put(d, f"<hp:t>{MP}A{MP}B{ME}C{ME}</hp:t>")
    marks = d.own_marks(d._ids[pid])
    assert [(m["kind"], m["end"], m["pos"]) for m in marks] == [("markpen", False, 0), ("markpen", False, 1), ("markpen", True, 2), ("markpen", True, 3)]
    assert _spans(d, pid) == [("markpen", 0, 3), ("markpen", 1, 2)] and d.mark_spans(d._ids[pid])[1]
    pid = _put(d, '<hp:ctrl><hp:fieldBegin id="5" type="HYPERLINK"/></hp:ctrl><hp:t>AB</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="5"/></hp:ctrl>'
                  '<hp:t><hp:insertBegin TcId="1" Id="9"/>CD<hp:insertEnd TcId="1" Id="9"/></hp:t>')
    spans, ok = d.mark_spans(d._ids[pid])
    assert ok and [(s["kind"], s["type"], s["start"], s["end"]) for s in spans] == [("field", "HYPERLINK", 0, 2), ("track", "insert", 2, 4)]
    assert [m["type"] for m in d.own_marks(d._ids[pid])] == ["HYPERLINK", "HYPERLINK", "insert", "insert"]  # 끝 표지는 짝 시작의 종류
    assert d.mark_names(d._ids[pid]) == ["하이퍼링크", "변경 추적"]


def test_counts_balanced_but_ids_wrong_is_unpaired():
    """종류별 개수만 맞는 짝(astra 반례 counts-balanced-ids-wrong)을 짝으로 치지 않는다."""
    d = _doc()
    pid = _put(d, '<hp:ctrl><hp:fieldBegin id="1" type="HYPERLINK"/></hp:ctrl><hp:t>AB</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="2"/></hp:ctrl>')
    assert d.mark_spans(d._ids[pid]) == ([], False)
    before, saved = _xml(d, pid), d.save()
    with pytest.raises(MarkBlock) as e:
        d.prefix_keep_marks(pid, "", "AB", "", "  ", "", None)
    assert e.value.why == "unpaired" and e.value.kinds == ["하이퍼링크", "필드"] and _xml(d, pid) == before and d.save() == saved  # 짝 없는 끝 표지 = 「필드」
    for runs in (f"<hp:t>{MP}A{ME}{ME}</hp:t>", "<hp:t><hp:insertBegin Id=\"1\"/>A<hp:insertEnd Id=\"2\"/></hp:t>",
                 "<hp:t><hp:insertBegin Id=\"1\"/>A<hp:deleteEnd Id=\"1\"/></hp:t>"):
        assert not d.mark_spans(d._ids[_put(d, runs)])[1]


def test_mark_names_own_or_all():
    d = _doc()
    for typ, name in (("FORMULA", "계산식"), ("BOOKMARK", "책갈피"), ("MEMO", "메모"), ("CLICK_HERE", "누름틀"), ("DATE", "필드")):
        pid = _put(d, f'<hp:ctrl><hp:fieldBegin id="3" type="{typ}"/></hp:ctrl><hp:t>AB</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="3"/></hp:ctrl>')
        assert d.mark_names(d._ids[pid]) == d.mark_names(d._ids[pid], own=False) == [name]
    pid = _put(d, f"<hp:t>{MP}A{ME}</hp:t><hp:t><hp:deleteBegin Id=\"4\"/>B<hp:deleteEnd Id=\"4\"/></hp:t>")
    assert d.mark_names(d._ids[pid]) == ["형광펜", "변경 추적"]


# ---- 거절 글 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("runs", [f"<hp:t>AB{MP}CD{ME}EF</hp:t>", f"<hp:t>AB</hp:t><hp:t>{MP}CD{ME}EF</hp:t>"])
def test_guard_says_the_action_and_the_kind(runs):
    """나누기 · 합치기 · 문단 지우기 · 고른 글 지우기 · 레터 바꾸기 — 글은 행동과 표지 종류로(전에는 모두 「나누거나 합칠 수 없습니다」). 문서는 그대로."""
    d = _doc()
    pid = _put(d, runs)
    before = _xml(d, pid)
    for call, what in ((lambda: d.split_para(pid, 2), "이 문단에 형광펜 표지가 있어 Enter 로 나눌 수 없습니다"),
                       (lambda: d.merge_paras(pid), "합칠 문단에 형광펜 표지가 있어 두 문단을 합칠 수 없습니다"),
                       (lambda: d.remove_para(pid), "이 문단에 형광펜 표지가 있어 문단을 지울 수 없습니다"),
                       (lambda: d.delete_text(pid, 1, 5), "이 문단에 형광펜 표지가 있어 고른 글을 지울 수 없습니다"),
                       (lambda: d.replace_prefix(pid, 2, "X"), "이 문단에 형광펜 표지가 있어 레터를 바꿀 수 없습니다")):
        with pytest.raises(ValueError, match=what):
            call()
        assert _xml(d, pid) == before
    pid = _put(d, '<hp:ctrl><hp:fieldBegin id="5" type="HYPERLINK"/></hp:ctrl><hp:t>AB</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="5"/></hp:ctrl>')
    with pytest.raises(ValueError, match="하이퍼링크 표지가 있어 Enter"):
        d.split_para(pid, 1)


def test_formula_field_in_a_cell_does_not_block_the_host_prefix():
    """표 칸 안 문단의 계산식 필드는 그 표를 품은 본문 문단의 「제 표지」 가 아니다 — 레터 바꾸기 · 고른 글 지우기는 되고, 나누기는 전처럼 막힌다(아래 전부)."""
    d = _doc()
    host = next(h for t in d._sections[0].iter(TBL) if (h := top_host(d, t)) is not None and next(h.iter(SECPR), None) is None)
    cell = next(next(host.iter(TBL)).iter(P))
    run = next(cell.iterchildren(RUN))
    for i, xml in ((0, '<hp:ctrl><hp:fieldBegin id="9" type="FORMULA"/></hp:ctrl>'), (None, '<hp:ctrl><hp:fieldEnd beginIDRef="9"/></hp:ctrl>')):
        el = etree.fromstring(f'<x xmlns:hp="{HP}">{xml}</x>')[0]
        run.insert(0, el) if i == 0 else run.append(el)
    new = etree.fromstring(f'<x xmlns:hp="{HP}"><hp:run charPrIDRef="{d._char_id(host)}"><hp:t>1. 가나</hp:t></hp:run></x>')[0]
    host.insert(0, new)
    d._touch(host)
    hid = d._id(host)
    assert d.own_marks(host) == [] and d.mark_names(host) == [] and d.mark_names(host, own=False) == ["계산식"]
    assert d.replace_prefix(hid, 3, "가) ")["offset"] == 3 and d._text(host).startswith("가) 가나")
    d.delete_text(hid, 0, 1)
    assert d._text(host).startswith(") 가나") and _tags(d, hid, "fieldBegin") == _tags(d, hid, "fieldEnd") == 1
    with pytest.raises(ValueError, match="계산식 표지가 있어 Enter"):
        d.split_para(hid, 1)


# ---- 글자 걷어 내기(_erase) -----------------------------------------------------------------------------------------

def test_erase_keeps_zero_length_children_in_place():
    """astra 반례 zero-length — 전에는 titleMark 를 한 글자로 세어 빼고 한 글자 덜 지웠다(DEF · ZDEF)."""
    d = _doc()
    pid = _put(d, "<hp:t>AB<hp:titleMark/>CDEF</hp:t>")
    d.delete_text(pid, 0, 4)
    assert d._text(d._ids[pid]) == "EF" and _tags(d, pid, "titleMark") == 1
    pid = _put(d, "<hp:t>AB<hp:titleMark/>CDEF</hp:t>")
    assert d.replace_prefix(pid, 4, "Z")["offset"] == 1
    assert d._text(d._ids[pid]) == "ZEF" and _tags(d, pid, "titleMark") == 1


def test_erase_refuses_autonum_in_range():
    """자동 번호(표시 글이 있는 hp:ctrl)가 지우는 범위에 걸치면 거절 — 전에는 세기만 하고 안 지워 범위가 밀렸다(1C · Z1BC). 문서는 그대로."""
    d = _doc()
    pid = _put(d, '<hp:ctrl><hp:autoNum num="1" numType="TABLE"/></hp:ctrl><hp:t>ABC</hp:t>')
    p = d._ids[pid]
    assert d._text(p) == "1ABC"
    before = _xml(d, pid)
    for start, end in ((0, 2), (0, 1)):
        with pytest.raises(ValueError, match="자동 번호"):
            d.delete_text(pid, start, end)
        assert _xml(d, pid) == before
    with pytest.raises(ValueError, match="자동 번호"):
        d.replace_prefix(pid, 2, "Z")
    d.delete_text(pid, 1, 2)
    assert d._text(p) == "1BC"


# ---- 글 고침(_write_t) ----------------------------------------------------------------------------------------------

def test_text_edit_keeps_markpen():
    """astra 반례 ordinary-text-edit — 전에는 hp:t 를 통째로 다시 써 형광펜 표지 둘이 사라졌다."""
    d = _doc()
    pid = _put(d, f"<hp:t>{MP}ABC{ME}</hp:t>")
    d.set_text(pid, "ABX")
    assert d._text(d._ids[pid]) == "ABX" and _spans(d, pid) == [("markpen", 0, 3)]
    assert _tags(d, pid, "markpenBegin") == _tags(d, pid, "markpenEnd") == 1


@pytest.mark.parametrize("new, span", [("ABxCDEF", (3, 5)),     # 시작 표지 자리에서 넣음 → 형광펜 밖(앞)
                                       ("ABCDyEF", (2, 4)),     # 끝 표지 자리에서 넣음 → 형광펜 밖(뒤)
                                       ("ABCxDEF", (2, 5)),     # 안에서 넣음 → 안
                                       ("ABzzEF", (2, 4)),      # 칠한 글 통째로 바꿈 → 경계 표지는 새 글을 감쌈
                                       ("AEF", (1, 1))])        # 칠한 글을 지움 → 빈 짝(차례 그대로)
def test_text_edit_at_marker_edges(new, span):
    d = _doc()
    pid = _put(d, f"<hp:t>AB{MP}CD{ME}EF</hp:t>")
    d.set_text(pid, new)
    assert d._text(d._ids[pid]) == new and _spans(d, pid) == [("markpen", *span)] and d.mark_spans(d._ids[pid])[1]


def test_text_edit_keeps_fw_space_and_tab_attributes():
    d = _doc()
    pid = _put(d, '<hp:t>A<hp:fwSpace/>B<hp:tab width="1234" leader="NONE" type="LEFT"/>C</hp:t>')
    assert d._text(d._ids[pid]) == "A B\tC"
    d.set_text(pid, "A B\tD")
    assert d._text(d._ids[pid]) == "A B\tD" and _tags(d, pid, "fwSpace") == 1 and next(d._ids[pid].iter(_p("tab"))).get("width") == "1234"
    pid = _put(d, '<hp:t>X<hp:tab width="1111" leader="NONE" type="LEFT"/>Y</hp:t>')
    d.set_text(pid, "Z\tW\tV")  # 가운데의 탭 = 옛 탭 속성 차례로, 모자라면 새 탭
    assert d._text(d._ids[pid]) == "Z\tW\tV" and [t.get("width") for t in d._ids[pid].iter(_p("tab"))] == ["1111", "4000"]
    pid = _put(d, "<hp:t>A B</hp:t>")
    d.set_text(pid, "A\u2002B\u2028C")
    assert _tags(d, pid, "nbSpace") == 1 and _tags(d, pid, "lineBreak") == 1 and d._text(d._ids[pid]) == "A\u2002B\u2028C"


def test_text_edit_keeps_adjacent_highlights_apart():
    """\ubd99\uc740 \ub450 \ud615\uad11\ud39c(\ub178\ub791 \u300cAB\u300d + \ucd08\ub85d \u300cCD\u300d)\uc5d0\uc11c \u300cBC\u300d \ub97c X \ub85c \u2014 \ubc14\ub010 \uacf3 \uc548\ucabd\uc758 \u300c\ub05d \u2192 \uc2dc\uc791\u300d \uc744 \ucc28\ub840 \uadf8\ub300\ub85c \ub450\uace0 \uc0c8 \uae00\uc740 \uccab \ub05d \ud45c\uc9c0 \uc55e(2026-11-17 \uac80\ud1a0:
    \uc804\uc5d0\ub294 \u300c\uc2dc\uc791 \u2192 \uc0c8 \uae00 \u2192 \ub05d\u300d \uc73c\ub85c \ub298\uc5b4\ub193\uc544 \ucd08\ub85d\uc774 \ub178\ub791 \uc548\uc5d0 \ub4e4\uace0 \uace0\uce58\uc9c0 \uc54a\uc740 D \uac00 \ub178\ub791\uc774 \ub410\ub2e4 \u2014 artifacts/markers_astra_2026-11-17/tmp_advxml/r1b_cross_min.py)."""
    d = _doc()
    pid = _put(d, f'<hp:t>{MP}AB{ME}<hp:markpenBegin color="#00FF00"/>CD{ME}</hp:t>')
    d.set_text(pid, "AXD")
    spans, ok = d.mark_spans(d._ids[pid])
    assert d._text(d._ids[pid]) == "AXD" and ok
    assert [(s["begin"].get("color"), s["start"], s["end"]) for s in spans] == [("#FFFF00", 0, 2), ("#00FF00", 2, 3)]   # D \ub294 \ucd08\ub85d \uadf8\ub300\ub85c \u00b7 \ub450 \uc9dd\uc774 \uc548 \uacb9\uce68
    pid = _put(d, f'<hp:t>{MP}AB{ME}<hp:insertBegin Id="5" TcId="1"/>CD<hp:insertEnd Id="5" TcId="1"/></hp:t>')
    d.set_text(pid, "AXD")
    assert _spans(d, pid) == [("markpen", 0, 2), ("track", 2, 3)]                                                    # \ud615\uad11\ud39c\uacfc \ub123\uae30 \ubc94\uc704\uac00 \uc548 \uacb9\uce68


def test_text_edit_in_two_places_keeps_what_lies_between():
    """\ud55c hp:t \ub97c \ub450 \uacf3\uc5d0\uc11c \ud55c \ubc88\uc5d0 \uace0\uce68(\uad6c\ubd84 \uae30\uc900 \ubc18\uc601\uc758 \uc0ac\uc5c5\uae30\uac04 \u300c2026 \u2192 2027\u300d \ub450 \uacf3) \u2014 \ubc14\ub010 \uacf3\ub9c8\ub2e4 \ub530\ub85c \uc368\uc11c \uadf8 \uc0ac\uc774\uc758 \uce60\ud55c \uae00 \u00b7 \uace0\uc815\ud3ed \ube48\uce78 \u00b7 \ud558\uc774\ud508\uc740 \uc790\uc2dd\uc9f8 \uadf8\ub300\ub85c
    (\uc804\uc5d0\ub294 \uccab \ub2e4\ub984 ~ \ub05d \ub2e4\ub984\uc744 \ud1b5\uc9f8\ub85c \ub2e4\uc2dc \uc368 \ud615\uad11\ud39c\uc774 \u300c2027.01.01 ~ 2027\u300d \uae4c\uc9c0 \ubc88\uc9c0\uace0 \uace0\uc815\ud3ed \ube48\uce78\uc774 \ubcf4\ud1b5 \ube48\uce78\uc774 \ub410\ub2e4 \u2014 tmp_advxml/r3_period.py)."""
    d = _doc()
    pid = _put(d, f"<hp:t>\uc0ac\uc5c5\uae30\uac04: {MP}2026.01.01{ME}<hp:fwSpace/>~<hp:fwSpace/>2026<hp:hyphen/>12.31</hp:t>")
    assert d._text(d._ids[pid]) == "\uc0ac\uc5c5\uae30\uac04: 2026.01.01 ~ 2026-12.31" and _spans(d, pid) == [("markpen", 6, 16)]
    d.set_text(pid, "\uc0ac\uc5c5\uae30\uac04: 2027.01.01 ~ 2027-12.31")
    assert d._text(d._ids[pid]) == "\uc0ac\uc5c5\uae30\uac04: 2027.01.01 ~ 2027-12.31" and _spans(d, pid) == [("markpen", 6, 16)]
    assert _tags(d, pid, "fwSpace") == 2 and _tags(d, pid, "hyphen") == 1


def test_cell_text_with_a_line_removed_keeps_the_marks_of_the_kept_lines():
    """\uce78 \uae00 \uace0\uce68\uc5d0\uc11c \uc904 \uc218\uac00 \ubc14\ub00c\uba74 \uc904\uc744 \ucc28\ub840\uac00 \uc544\ub2c8\ub77c \ubb38\ub2e8 \uae00\ub07c\ub9ac \ub9de\ucd98\ub2e4 \u2014 \u300cA\u300d \u00b7 \u300cB\u300d \u00b7 \u300c[\uacc4\uc0b0\uc2dd \ud544\ub4dc [\ud615\uad11\ud39c C]]\u300d \uc5d0\uc11c \u300cB\u300d \ub97c \ube7c\uba74 C \uc758 \ubb38\ub2e8(\ud544\ub4dc \u00b7 \ud615\uad11\ud39c)\uc774 \uadf8\ub300\ub85c \ub0a8\uace0,
    \ub9e8 \uc55e\uc5d0 \uc904\uc744 \ub123\uc73c\uba74 \uadf8 \uc790\ub9ac\uc5d0 \uc0c8 \ubb38\ub2e8(2026-11-17 \uac80\ud1a0: \uc804\uc5d0\ub294 \uc904\uc744 \ucc28\ub840\ub85c \ucc44\uc6b0\uace0 \ub4a4 \ubb38\ub2e8\uc744 \uc9c0\uc6cc C \uc758 \ud544\ub4dc \u00b7 \ud615\uad11\ud39c\uc774 \uc0ac\ub77c\uc84c\ub2e4 \u2014 tmp_advxml/r2_cell.py)."""
    d = _doc()
    tc = next(c for t in d._sections[0].iter(TBL) for c in t.iter(_p("tc")) if next(c.find(_p("subList")).iter(TBL), None) is None)
    sub = tc.find(_p("subList"))
    first = next(sub.iterchildren(P))
    for q in list(sub.iterchildren(P)):
        sub.remove(q)
    head = f'<hp:p xmlns:hp="{HP}" paraPrIDRef="{first.get("paraPrIDRef")}" styleIDRef="{first.get("styleIDRef")}" pageBreak="0" columnBreak="0" merged="0">'
    for x in ("<hp:t>A</hp:t>", "<hp:t>B</hp:t>",
              f'<hp:ctrl><hp:fieldBegin id="77" type="FORMULA"/></hp:ctrl><hp:t>{MP}C{ME}</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="77"/></hp:ctrl>'):
        sub.append(etree.fromstring(f'{head}<hp:run charPrIDRef="{d._char_id(first)}">{x}</hp:run></hp:p>'))
    d._touch(tc)
    cell = d._id(tc)

    def now():
        return [(d._text(q), len(list(q.iter(_p("fieldBegin")))), len(list(q.iter(_p("markpenBegin"))))) for q in sub.iterchildren(P)]
    d.set_text(cell, "A\nC")
    assert now() == [("A", 0, 0), ("C", 1, 1)]
    d.set_text(cell, "Z\nA\nC")
    assert now() == [("Z", 0, 0), ("A", 0, 0), ("C", 1, 1)]


def test_write_same_text_keeps_the_piece_and_rewrite_cleans_it():
    """같은 글로 _write_t = 아무것도 안 바뀜(자식째 그대로) · 정리는 _rewrite_t(style_carrier._scrub — 표지·낯선 자식을 걷고 보이는 글만)."""
    d = _doc()
    pid = _put(d, f"<hp:t>{MP}A<hp:fwSpace/>B{ME}</hp:t>")
    t = next(d._ids[pid].iter(T))
    before = etree.tostring(t)
    d._write_t(t, d._slot_text(t))
    assert etree.tostring(t) == before
    d._rewrite_t(t, d._slot_text(t))
    assert len(t) == 0 and t.text == "A B"


# ---- 접두 빈칸만 바꾸기(prefix_keep_marks) --------------------------------------------------------------------------------

@pytest.mark.parametrize("runs, lead, span", [
    (f"<hp:t>{MP}[ABC]{ME}</hp:t>", "", (4, 9)),          # 레터 앞 빈칸 없이 시작 표지가 자리 0 → 새 빈칸은 형광펜 밖
    (f"<hp:t>  {MP}[ABC]{ME}</hp:t>", "  ", (4, 9)),     # 빈칸 뒤 시작 표지 → 바꾼 뒤에도 레터 바로 앞
    (f"<hp:t>{MP}  [ABC]{ME}</hp:t>", "  ", (0, 9)),     # 레터 앞 빈칸까지 칠한 것 → 바뀐 빈칸도 안(astra 반례 highlighted-leading-blanks)
])
def test_keep_marks_lead(runs, lead, span):
    d = _doc()
    pid = _put(d, runs)
    got = d.prefix_keep_marks(pid, lead, "[ABC]", "", "    ", "", None)
    assert got == {"id": pid, "offset": 9} and d._text(d._ids[pid]) == "    [ABC]" and _spans(d, pid) == [("markpen", *span)]


def test_keep_marks_gap_to_bound_space():
    """레터 뒤 빈칸 → 묶음 빈칸(hp:nbSpace) — 레터에서 끝난 형광펜 뒤라 밖에 둔다."""
    d = _doc()
    pid = _put(d, f"<hp:t>{MP}□{ME} 본문</hp:t>")
    assert d.prefix_keep_marks(pid, "", "□", " ", "", "\u2002", None)["offset"] == 2
    assert d._text(d._ids[pid]) == "□\u2002본문" and _spans(d, pid) == [("markpen", 0, 1)] and _tags(d, pid, "nbSpace") == 1


def test_keep_marks_inserts_outside_a_field_in_a_new_piece():
    """필드 시작 표지(hp:ctrl)가 자리 0 — 사이에 hp:t 가 없어 같은 런의 그 자리에 새 hp:t 를 만들고, 새 빈칸은 필드 밖."""
    d = _doc()
    pid = _put(d, '<hp:ctrl><hp:fieldBegin id="3" type="FORMULA"/></hp:ctrl><hp:t>ABCD</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="3"/></hp:ctrl>')
    d.prefix_keep_marks(pid, "", "A", "", "  ", "", None)
    p = d._ids[pid]
    assert d._text(p) == "  ABCD" and _spans(d, pid) == [("field", 2, 6)]
    assert [c.tag for r in p.iterchildren(RUN) for c in r][:2] == [T, _p("ctrl")]


@pytest.mark.parametrize("runs, args, why", [
    (f"<hp:t> {MP} [ABC]{ME}</hp:t>", ("  ", "[ABC]", "", "    ", ""), "inside"),          # 바꿀 빈칸 사이에 표지
    ('<hp:t>A</hp:t><hp:ctrl><hp:fieldBegin id="3" type="HYPERLINK"/></hp:ctrl><hp:t> BCD</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="3"/></hp:ctrl>',
     ("", "A", " ", "", "\u2002"), "field"),                                                   # 필드 안쪽 빈칸(astra 반례 edit-inside-field)
    ('<hp:ctrl><hp:fieldBegin id="3" type="HYPERLINK"/></hp:ctrl><hp:t>AB</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="3"/></hp:ctrl>',
     ("", "A", "", "", " "), "field"),                                                         # 넣기만 — 필드 범위 안쪽 자리
    ('<hp:t><hp:insertBegin TcId="1" Id="1"/>  AB<hp:insertEnd TcId="1" Id="1"/></hp:t>', ("  ", "AB", "", "    ", ""), "track"),
])
def test_keep_marks_refuses_and_leaves_the_document(runs, args, why):
    d = _doc()
    pid = _put(d, runs)
    before, saved = _xml(d, pid), d.save()
    with pytest.raises(MarkBlock) as e:
        d.prefix_keep_marks(pid, *args, {"paraPrIDRef": "0", "charPrIDRef": "0"})
    assert e.value.why == why and isinstance(e.value, ValueError) and e.value.kinds
    assert _xml(d, pid) == before and d.save() == saved


def test_keep_marks_wrong_prefix_is_a_plain_error():
    d = _doc()
    pid = _put(d, f"<hp:t>{MP}[ABC]{ME}</hp:t>")
    with pytest.raises(ValueError) as e:
        d.prefix_keep_marks(pid, " ", "[ABC]", "", "    ", "", None)
    assert not isinstance(e.value, MarkBlock)


def _other(d, kind, *not_these):
    return next(i for i in d._defs[kind] if i not in not_these)


def test_keep_marks_and_shape_only_apply_the_prefix_look():
    """모양 = replace_prefix 와 같은 규칙 — 문단 속성 · 접두의 글 런 · 옛 접두 첫 글자 모양을 쓰던 런 = attrs, 따로 모양을 준 런은 그대로."""
    d = _doc()
    p = _body(d)
    cid = d._char_id(p)
    body = _other(d, "charPr", cid)
    new_c, new_p = _other(d, "charPr", cid, body), _other(d, "paraPr", p.get("paraPrIDRef"))
    attrs = {"paraPrIDRef": new_p, "styleIDRef": "0", "charPrIDRef": new_c}
    runs = f'<hp:run charPrIDRef="CID"><hp:t>  {MP}[ABC]{ME} </hp:t></hp:run><hp:run charPrIDRef="{body}"><hp:t>본문</hp:t></hp:run>'
    pid = _put(d, runs, p)
    d.prefix_keep_marks(pid, "  ", "[ABC]", " ", "    ", " ", attrs)
    p = d._ids[pid]
    assert d._text(p) == "    [ABC] 본문" and _spans(d, pid) == [("markpen", 4, 9)] and p.get("paraPrIDRef") == new_p
    assert [(r.get("charPrIDRef"), "".join(d._slot_text(t) for t in r.iterchildren(T))) for r in p.iterchildren(RUN)] == [(new_c, "    [ABC] "), (body, "본문")]
    pid = _put(d, runs, p)
    p.set("paraPrIDRef", "0")
    assert d.prefix_shape_only(pid, 3, attrs) == {"id": pid, "offset": 3}
    assert d._text(p) == "  [ABC] 본문" and _spans(d, pid) == [("markpen", 2, 7)] and p.get("paraPrIDRef") == new_p
    assert [r.get("charPrIDRef") for r in p.iterchildren(RUN)] == [new_c, body]  # 옛 첫 글자 모양의 런 = 접두 런(경계로 갈랐다 다시 합쳐짐) · 본문 런은 그대로


def test_keep_marks_survives_save_and_reopen():
    d = _doc()
    pid = _put(d, f"<hp:t>{MP}  [ABC]{ME} 본문</hp:t>")
    d.prefix_keep_marks(pid, "  ", "[ABC]", " ", "    ", "\u2002", None)
    p = d._ids[pid]
    sec = d._sections.index(p.getparent())
    d2 = HwpxDoc(d.save())
    p2 = d2._sections[sec][list(p.getparent()).index(p)]
    assert d2._text(p2) == "    [ABC]\u2002본문" and [(s["kind"], s["start"], s["end"]) for s in d2.mark_spans(p2)[0]] == [("markpen", 0, 9)]
    assert d2.mark_spans(p2)[1] and len(list(p2.iter(_p("nbSpace")))) == 1
