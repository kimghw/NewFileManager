"""문서 서식(spec_서식복사 ② §5 · §10 — app/style_page.py): 꼴 검사 · hwpx 쪽 설정 읽기·바꾸기(저장 뒤 다시 열어도 · 가로 · 구역 여럿 · 줄 배치 캐시) · 바탕 글 · hwpx 운반 문서 ·
docx 구역 · PDF 측정에서 어림 · 요약 글. 한글·Word 없이(PDF 는 손으로 만든 measure 사전)."""
from pathlib import Path

import pytest
from lxml import etree

from app import style_carrier as SC
from app import style_docx as D
from app import style_page as SP
from app.docx_doc import DocxDoc
from app.hwpx_doc import HwpxDoc, P, _p
from app.hwpx_format import LINESEG, SUMMARY_KEYS

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, RND = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx"
W = SP.W


def _page(**over):
    return {"widthMm": 210, "heightMm": 297, "landscape": False, "marginsMm": {"l": 30, "r": 25, "t": 35, "b": 30, "header": 15, "footer": 10, "gutter": 0}, **over}


def _same(got, want, tol=0.02):
    assert got is not None and got["landscape"] is want["landscape"]
    assert (got["widthMm"], got["heightMm"]) == pytest.approx((want["widthMm"], want["heightMm"]), abs=tol)
    assert got["marginsMm"] == pytest.approx(want["marginsMm"], abs=tol)


# ---- clean · summary ------------------------------------------------------------------------------------------------

def test_clean_returns_the_canonical_shape():
    got = SP.clean({"widthMm": 297, "heightMm": 210.004, "landscape": False, "marginsMm": {"l": 20, "r": 20, "t": 15.127, "b": 15}})
    assert got == {"widthMm": 297.0, "heightMm": 210.0, "landscape": True,  # 가로 = 폭이 더 큼(준 값이 아니라 두 값에서)
                   "marginsMm": {"l": 20.0, "r": 20.0, "t": 15.13, "b": 15.0, "header": 0.0, "footer": 0.0, "gutter": 0.0}}
    assert SP.clean(got) == got


@pytest.mark.parametrize("bad", [
    None, [], {}, {"widthMm": 210, "heightMm": 297},  # 여백 없음
    _page(widthMm=10), _page(heightMm=3000), _page(widthMm="210"), _page(widthMm=True),  # 폭·높이 범위·꼴
    _page(marginsMm={"l": 30, "r": 25, "t": 35}),  # 아래 여백 없음
    _page(marginsMm={"l": -1, "r": 25, "t": 35, "b": 30}), _page(marginsMm={"l": 301, "r": 25, "t": 35, "b": 30}),  # 여백 범위
    _page(marginsMm={"l": 110, "r": 100, "t": 35, "b": 30}),  # 좌우 합 ≥ 폭
    _page(marginsMm={"l": 100, "r": 100, "t": 35, "b": 30, "gutter": 10}),  # 제본 여백까지
    _page(marginsMm={"l": 30, "r": 25, "t": 150, "b": 147}),  # 위아래 합 ≥ 높이
    _page(marginsMm={"l": 30, "r": 25, "t": 20, "b": 30, "header": 25}),  # 머리말이 위 여백보다 큼(위 여백 = 종이 끝에서 본문까지)
    _page(marginsMm={"l": 30, "r": 25, "t": 35, "b": 10, "footer": 12}),
])
def test_clean_refuses(bad):
    with pytest.raises(ValueError):
        SP.clean(bad)


def test_summary_line():
    page = {"widthMm": 210, "heightMm": 297, "marginsMm": {"l": 30, "r": 30, "t": 20, "b": 15}}
    assert SP.summary(page, None) == "A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm"
    assert SP.summary(page, {"format": {"font": "함초롬바탕", "sizePt": 11.0}, "count": 3}) == "A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm · 본문 함초롬바탕 11pt"
    assert SP.summary(page, {"format": {"sizePt": 10.5}, "count": 1}).endswith(" · 본문 10.5pt")
    wide = {"widthMm": 420, "heightMm": 296.99, "marginsMm": {"l": 12.5, "r": 12.5, "t": 10, "b": 10}}  # 한글의 A4·A3 높이는 0.01mm 모자란다
    assert SP.summary(wide) == "A3 가로 · 여백 왼 12.5 · 오 12.5 · 위 10 · 아래 10mm"
    assert SP.summary({"widthMm": 200, "heightMm": 250, "marginsMm": {"l": 10, "r": 10, "t": 10, "b": 10}}).startswith("200×250mm 세로 · ")
    assert SP.paper_name(SP.clean({"widthMm": 215.9, "heightMm": 279.4, "marginsMm": {"l": 10, "r": 10, "t": 10, "b": 10}})) == "Letter"


# ---- hwpx ----------------------------------------------------------------------------------------------------------

def test_base_is_a4_portrait_with_20mm_sides():
    d, _, _ = SC.open_base()
    got = SP.of_hwpx(d)
    page = got["page"]
    assert page == SP.read(d) and page["landscape"] is False
    assert (page["widthMm"], page["heightMm"]) == pytest.approx((210, 297), abs=0.05)
    assert (page["marginsMm"]["l"], page["marginsMm"]["r"]) == pytest.approx((20, 20), abs=0.01)
    assert page["marginsMm"]["header"] <= page["marginsMm"]["t"] and page["marginsMm"]["footer"] <= page["marginsMm"]["b"]
    assert got["losses"] == [] and got["body"] is None  # 빈 바탕 — 글 문단이 없다
    assert SP.summary(page, got["body"]).startswith("A4 세로 · 여백 왼 20 · 오 20 · ")


def test_set_page_then_read_and_reopen():
    d, _, _ = SC.open_base()
    want = SP.clean(_page())
    assert SP.set_page(d, _page()) == 1
    _same(SP.read(d), want)
    again = HwpxDoc(d.save())
    _same(SP.read(again), want)
    pp = next(again._sections[0].iter(_p("pagePr")))
    mg = pp.find(_p("margin"))
    hu = lambda mm: round(mm * 7200 / 25.4)  # noqa: E731
    assert pp.get("landscape") == "WIDELY" and (int(pp.get("width")), int(pp.get("height"))) == (hu(210), hu(297))
    # 한글의 위쪽 = 본문까지의 여백 − 머리말(본문 시작 = 위쪽 + 머리말)
    assert (int(mg.get("top")), int(mg.get("header")), int(mg.get("bottom")), int(mg.get("footer"))) == (hu(35) - hu(15), hu(15), hu(30) - hu(10), hu(10))
    assert (int(mg.get("left")), int(mg.get("right")), int(mg.get("gutter"))) == (hu(30), hu(25), 0)


def test_set_page_with_the_same_values_leaves_the_document_untouched():
    d, _, _ = SC.open_base()
    assert SP.set_page(d, SP.read(d)) == 1  # 이미 같은 구역도 센다
    assert not d._dirty and d.save() == SC.base()


def test_landscape_round_trips_the_way_hangul_stores_it():
    d, _, _ = SC.open_base()
    page = _page(widthMm=297, heightMm=210)
    SP.set_page(d, page)
    again = HwpxDoc(d.save())
    pp = next(again._sections[0].iter(_p("pagePr")))
    assert pp.get("landscape") == "NARROWLY" and int(pp.get("width")) < int(pp.get("height"))  # 폭·높이는 세로 기준으로 적는다
    got = SP.read(again)
    _same(got, SP.clean(page))
    assert got["landscape"] is True and got["widthMm"] > got["heightMm"]
    assert again._body_width_mm(next(again._sections[0].iterchildren(P))) == pytest.approx(297 - 30 - 25, abs=0.05)  # 문서 클래스의 글 폭 규칙과 맞는다
    SP.set_page(again, _page())  # 다시 세로로
    assert next(again._sections[0].iter(_p("pagePr"))).get("landscape") == "WIDELY" and SP.read(again)["landscape"] is False


def test_set_page_refuses_a_bad_page_before_touching_anything():
    d, _, _ = SC.open_base()
    with pytest.raises(ValueError):
        SP.set_page(d, _page(widthMm=5))
    assert not d._dirty


def test_document_page_and_body_text():
    small = SP.of_hwpx(HwpxDoc(SMALL.read_bytes()))
    assert small["page"]["landscape"] is False and small["body"] is None  # 기술수요조사서 = 최상위가 표 둘뿐(글은 모두 칸 안) — 바탕 글 없음(쪽 설정만)
    d = HwpxDoc(RND.read_bytes())
    got = SP.of_hwpx(d)
    page, body = got["page"], got["body"]
    assert page["landscape"] is False and (page["widthMm"], page["heightMm"]) == pytest.approx((210, 297), abs=0.05)
    assert (page["marginsMm"]["l"], page["marginsMm"]["r"]) == pytest.approx((20, 20), abs=0.01)
    assert body["count"] >= 1 and body["format"].get("sizePt") and set(body["format"]) <= SUMMARY_KEYS
    assert None not in body["format"].values()
    # 바탕 글 = 본문 최상위 글 문단 가운데 글자 수가 가장 많은 서식 묶음
    tops = [b for b in d.blocks() if b["type"] == "paragraph" and b["text"].strip() and not b.get("captionOf")]
    same = [b for b in tops if {k: v for k, v in b["format"].items() if k in SUMMARY_KEYS and v is not None} == body["format"]]
    assert len(same) == body["count"]


def test_body_of_groups_by_format_and_picks_the_most_characters():
    a, b = {"font": "바탕", "sizePt": 10, "bold": False, "wordBreak": "char"}, {"font": "돋움", "sizePt": 14, "bold": True, "lineSpacingPct": None}
    blocks = [{"type": "paragraph", "text": "짧은 제목", "format": b}, {"type": "paragraph", "text": "   ", "format": b},
              {"type": "paragraph", "text": "본문 한 줄 " * 3, "format": a}, {"type": "paragraph", "text": "본문 두 줄 " * 3, "format": dict(a)},
              {"type": "paragraph", "text": "캡션 " * 40, "format": b, "captionOf": "t1"},
              {"type": "table", "cells": [{"blocks": [{"type": "paragraph", "text": "칸 안 글 " * 40, "format": b}]}]}]
    assert SP.body_of(blocks) == {"format": {"font": "바탕", "sizePt": 10, "bold": False}, "count": 2}  # 서식 요약 키만 · 캡션·칸 안·빈 문단은 안 센다
    assert SP.body_of([]) is None and SP.body_of([{"type": "paragraph", "text": "", "format": a}]) is None


def test_bodies_are_the_top_three_groups_and_skip_heading_paragraphs():
    """바탕 글 후보 상위 3(spec_서식복사 ② §12·§15): 글자 수 많은 차례 · 헤딩 노드의 문단(skip)은 세지 않는다 — 양식 문서에서 굵은 제목 줄이 바탕 글이 되던 것."""
    head, body, small, tiny = ({"font": "돋움", "sizePt": 13, "bold": True}, {"font": "바탕", "sizePt": 10, "bold": False}, {"font": "바탕", "sizePt": 9, "bold": False},
                               {"font": "바탕", "sizePt": 8, "bold": False})
    para = lambda i, text, f, **kw: {"id": i, "type": "paragraph", "text": text, "format": dict(f), **kw}  # noqa: E731
    blocks = [para("h1", "가" * 30, head), para("h2", "나" * 30, head), para("p1", "본문 " + "다" * 38, body), para("p2", "라" * 10, small), para("p3", "마" * 5, small),
              para("p4", "바" * 3, tiny), para("c1", "사" * 99, tiny, captionOf="t1"), para("p5", "  ", body)]
    got = SP.bodies(blocks)
    assert [(b["key"], b["format"], b["count"], b["chars"]) for b in got] == [("b1", head, 2, 60), ("b2", body, 1, 40), ("b3", small, 2, 15)]  # 제목 줄이 글자 수로는 1위 · 넷째 묶음은 안 낸다
    assert got[0]["sample"] == "가" * 30 and got[1]["sample"] == "본문 " + "다" * 38 and SP.body_of(blocks) == {"format": head, "count": 2}
    skipped = SP.bodies(blocks, skip={"h1", "h2"})                             # 헤딩 문단을 빼면 본문 서식이 1위
    assert [(b["key"], b["format"], b["chars"]) for b in skipped] == [("b1", body, 40), ("b2", small, 15), ("b3", tiny, 3)]
    assert SP.body_of(blocks, skip={"h1", "h2"}) == {"format": body, "count": 1} and SP.bodies([]) == [] and SP.bodies(blocks, skip={"h1", "h2", "p1", "p2", "p3", "p4"}) == []
    long = SP.bodies([para("p9", "긴 글 " * 40, body)])[0]["sample"]
    assert len(long) == SP.BODY_SAMPLE == 60 and long.endswith("…")
    same = [para("a", "가" * 10, body), para("b", "나" * 10, small)]             # 글자 수가 같으면 먼저 나온 묶음
    assert [b["format"] for b in SP.bodies(same)] == [body, small]


def test_the_page_is_the_one_of_the_section_with_the_most_body_text():
    a, b = SP.clean(_page()), SP.clean(_page(widthMm=297, heightMm=210))
    assert SP._pick_section([a, b, a], {0: 10, 1: 50, 2: 49}) == 1            # 글자 수가 가장 많은 구역
    assert SP._pick_section([a, b], {}) == 0 and SP._pick_section([a, b], {0: 7, 1: 7}) == 0   # 글이 없는 문서 · 같으면 앞 구역
    assert SP._pick_section([None, b], {0: 99, 1: 1}) == 1 and SP._pick_section([None], {0: 5}) is None and SP._pick_section([], {}) is None   # 쪽 설정을 못 읽는 구역은 고르지 않는다
    got = SP._found([a, b, None], {1: 3}, [{"id": "p1", "type": "paragraph", "text": "본문", "format": {"sizePt": 10}}], ())
    assert got == {"page": b, "body": {"format": {"sizePt": 10}, "count": 1}, "section": 1, "losses": [SP.diff_note(1)],
                   "bodies": [{"key": "b1", "format": {"sizePt": 10}, "count": 1, "chars": 2, "sample": "본문"}]}
    assert SP._found([a, a], {}, [], ())["losses"] == [] and SP._found([a, a], {}, [], ())["body"] is None
    d = HwpxDoc(RND.read_bytes())                                            # 실제 문서 — 인자 없이 불러도(기존 부르는 곳) 같은 꼴
    full = SP.of_hwpx(d)
    assert set(full) == {"page", "body", "bodies", "section", "losses"} and 0 <= full["section"] < len(d._sections) and full["bodies"][0]["key"] == "b1"
    assert full["body"] == {"format": full["bodies"][0]["format"], "count": full["bodies"][0]["count"]} and len(full["bodies"]) <= 3
    skip = {b["id"] for b in d.blocks() if b["type"] == "paragraph" and b["format"] == {**b["format"], **full["body"]["format"]}}   # 1위 서식의 문단을 다 빼면 다른 서식이 1위
    assert SP.of_hwpx(d, skip)["body"] != full["body"] and SP.of_hwpx(d, skip)["page"] == full["page"]


def test_sections_with_different_pages_are_reported_and_set_page_sets_them_all():
    d = HwpxDoc(RND.read_bytes())
    pages = [pp for sec in d._sections for pp in sec.iter(_p("pagePr"))]
    n = len(pages)
    before = SP.of_hwpx(d)
    assert n > 1 and before["losses"] == []  # 이 양식은 구역 셋의 쪽 설정이 같다 — 알릴 것이 없다
    # 쪽 설정은 **본문 글이 가장 많은 구역**의 것(spec_서식복사 ② §15 — 전에는 첫 구역): 구역마다 최상위 글 문단의 글자 수를 세어 견준다
    secs = {s: k for k, s in enumerate(d._sections)}
    chars = [0] * len(d._sections)
    for b in d.blocks():
        if b["type"] == "paragraph" and not b.get("captionOf"):
            chars[secs[d._ids[b["id"]].getparent()]] += len("".join(b["text"].split()))
    k = before["section"]
    assert k == chars.index(max(chars)) and before["page"] == SP._hwpx_page(next(d._sections[k].iter(_p("pagePr"))))
    other = next(i for i in range(len(d._sections)) if i != k)
    next(d._sections[other].iter(_p("pagePr"))).find(_p("margin")).set("left", "8504")  # 다른 구역의 왼쪽 여백만 30mm 로 — 구역마다 다른 문서
    got = SP.of_hwpx(d)
    assert got["losses"] == [SP.diff_note(k)] and got["losses"][0].startswith(SP.DIFF_HEAD) and got["section"] == k
    assert got["page"] == before["page"] and got["page"]["marginsMm"]["l"] == pytest.approx(20, abs=0.01)  # 고른 구역 것(바꾼 구역이 아니다)
    assert SP.diff_note(0) == SP.DIFF_NOTE and "2번째 구역" in SP.diff_note(1)
    assert SP.set_page(d, _page()) == n
    want = SP.clean(_page())
    for sec in d._sections:
        for pp in sec.iter(_p("pagePr")):
            _same(SP._hwpx_page(pp), want)


def test_reflow_drops_the_line_cache_of_top_level_paragraphs_only():
    """본문 상자가 바뀌면 최상위 문단의 줄 배치 캐시를 지운다(한글은 캐시가 있는 문단을 다시 조판하지 않는다) — 칸 안 문단 것은 그대로."""
    count = lambda doc, top: sum(len(p.findall(LINESEG)) for sec in doc._sections  # noqa: E731
                                 for p in (sec.iterchildren(P) if top else sec.iter(P)) if top or p.getparent() not in doc._sections)
    d = HwpxDoc(SMALL.read_bytes())
    top, inner = count(d, True), count(d, False)
    if not top:
        pytest.skip("견본 문서의 최상위 문단에 줄 배치 캐시가 없다")
    keep = HwpxDoc(SMALL.read_bytes())
    SP.set_page(keep, _page(), reflow=False)
    assert (count(keep, True), count(keep, False)) == (top, inner)
    SP.set_page(d, _page())
    assert (count(d, True), count(d, False)) == (0, inner)
    same_box = HwpxDoc(SMALL.read_bytes())  # 본문 상자가 그대로면(왼쪽·오른쪽 여백을 맞바꿔도 폭은 같다) 캐시를 안 지운다
    cur = SP.read(same_box)
    SP.set_page(same_box, {**cur, "marginsMm": {**cur["marginsMm"], "l": cur["marginsMm"]["r"] + 1, "r": cur["marginsMm"]["l"] - 1}})
    assert count(same_box, True) == top and same_box._dirty


def test_carrier_holds_the_page_and_three_sample_lines():
    body = {"format": {"sizePt": 12, "bold": True, "align": "center", "lineSpacingPct": 180, "indentLeftMm": 5, "color": "#1F3864"}, "count": 9}
    data, info = SP.carrier(_page(), body)
    cdoc = SC.doc(data)
    _same(SP.read(cdoc), SP.clean(_page()))
    ids = SP.sample_ids(cdoc)  # 견본 첫 줄은 첫 문단(구역 설정을 품은 문단)에 — 비워 두면 견본이 둘째 줄로 밀려 본문 위끝을 못 잰다(한글 실측)
    blocks = {b["id"]: b for b in cdoc.blocks()}
    assert [blocks[i]["text"] for i in ids] == SP.SAMPLES and SC.para_ids(cdoc) == ids[1:]
    assert not any(b["type"] == "table" for b in cdoc.blocks())  # 바탕의 평범한 표는 지웠다
    for i in ids:
        f = blocks[i]["format"]
        assert (f["sizePt"], f["bold"], f["align"], f["lineSpacingPct"], f["color"]) == (12, True, "center", 180, "#1F3864")
        assert f["indentLeftMm"] == pytest.approx(5, abs=0.02)
    assert isinstance(info["fonts"], list) and info["losses"] == []
    got = SP.of_hwpx(cdoc)  # 운반 문서에서 다시 읽어도 같은 쪽 · 그 바탕 글
    assert got["body"]["count"] == 3 and got["body"]["format"]["sizePt"] == 12 and got["losses"] == []
    assert SC.broken_refs(cdoc) == []


def test_carrier_without_body_uses_the_plain_look():
    data, info = SP.carrier(_page(widthMm=297, heightMm=210), None)
    cdoc = SC.doc(data)
    assert SP.read(cdoc)["landscape"] is True and len(SP.sample_ids(cdoc)) == 3 and info["losses"] == []
    with pytest.raises(ValueError):
        SP.carrier({"widthMm": 210}, None)


# ---- docx ----------------------------------------------------------------------------------------------------------

def test_docx_first_section_and_differing_sections():
    doc = DocxDoc(D.from_page(_page(), {"format": {"sizePt": 11}, "count": 1})[0])
    one = SP.of_docx(doc)
    _same(one["page"], SP.clean(_page()), tol=0.1)
    assert one["losses"] == [] and one["body"]["format"]["sizePt"] == 11 and one["body"]["count"] == 3
    assert one["section"] == 0 and [b["key"] for b in one["bodies"]] == ["b1"] and one["bodies"][0]["count"] == 3 and one["bodies"][0]["format"] == one["body"]["format"]
    # 앞에 가로 구역 하나를 더한다(글 없는 표지 구역) — 구역 끝 문단의 pPr/sectPr 가 첫 구역
    first = etree.fromstring(
        f'<w:p xmlns:w="{D.W_NS}"><w:pPr><w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
        '<w:pgMar w:top="1440" w:right="1134" w:bottom="1440" w:left="1701" w:header="720" w:footer="2000" w:gutter="0"/></w:sectPr></w:pPr></w:p>')
    doc._body.insert(0, first)
    two = SP.of_docx(doc)
    # 쪽 설정은 첫 구역이 아니라 **본문 글이 가장 많은 구역**의 것(spec_서식복사 ② §15) — 견본 글 3줄이 있는 둘째 구역
    assert two["section"] == 1 and two["losses"] == [SP.diff_note(1)] and two["page"]["landscape"] is False
    _same(two["page"], SP.clean(_page()), tol=0.1)
    for t in doc._body.iter(W + "t"):  # 글이 없는 문서는 첫 구역
        t.text = ""
    empty = SP.of_docx(doc)
    assert empty["section"] == 0 and empty["losses"] == [SP.DIFF_NOTE] and empty["page"]["landscape"] is True and empty["body"] is None and empty["bodies"] == []
    m = empty["page"]["marginsMm"]
    assert (m["l"], m["r"], m["t"], m["b"]) == pytest.approx((30.0, 20.0, 25.4, 25.4), abs=0.02)
    assert m["header"] == pytest.approx(12.7, abs=0.02)  # 머리말 몫 = top − header(종이 끝에서 머리말까지)
    assert m["footer"] == 0  # 꼬리말 거리가 아래 여백보다 크면 몫은 0
    doc._body.find(W + "sectPr").getparent().remove(doc._body.find(W + "sectPr"))
    doc._body.remove(first)
    assert SP.of_docx(doc) is None  # 쪽 설정 없음


# ---- pdf -----------------------------------------------------------------------------------------------------------

def _line(text, x0, y0, x1, y1, span):
    step = (x1 - x0) / max(1, len(text))
    return {"text": text, "bbox": [x0, y0, x1, y1], "block": 0, "chars": [(ch, x0 + k * step, y0, x0 + (k + 1) * step, y1, span, False) for k, ch in enumerate(text)],
            "spans": [("ABCDEF+FooSans-Regular", 10.98, 0, 0), ("BarSerif-Bold", 14.0, 16, 0)]}


def _sheet(left=85.04, w=595.28, h=841.89):
    """A4 한 쪽 — 글 상자: 왼 30mm(85.04pt) · 오른 30mm · 위 35mm(99.21pt) · 아래 30mm."""
    return {"w": w, "h": h, "sheet": 0, "segs": [], "rects": [], "tables": [], "type3": set(),
            "lines": [_line("큰 제목", left, 99.21, 200, 113.21, 1), _line("본문 글이 길게 이어지는 줄 하나", left, 120, w - 85.04, 131, 0),
                      _line("   ", 10, 10, 20, 20, 0), _line("본문 글이 길게 이어지는 줄 둘", left, 740, 400, h - 85.04, 0)]}


def test_of_pdf_estimates_page_margins_and_body_text():
    measure = {"count": 5, "pages": [_sheet(), _sheet(left=141.7), _sheet(), {**_sheet(), "w": 841.89, "h": 595.28}, {"w": 595.28, "h": 841.89, "lines": []}]}
    got = SP.of_pdf(measure)
    page = got["page"]
    assert page["landscape"] is False and (page["widthMm"], page["heightMm"]) == pytest.approx((210, 297), abs=0.05)  # 가장 많은 크기
    m = page["marginsMm"]
    assert (m["l"], m["r"], m["t"], m["b"]) == pytest.approx((30, 30, 35, 30), abs=0.1)  # 쪽마다의 가장자리 → 중앙값(한 쪽만 왼쪽이 50mm)
    assert (m["header"], m["footer"], m["gutter"]) == (0, 0, 0)
    assert got["body"] == {"format": {"font": "FooSans", "sizePt": 11.0}, "count": 6}  # 가장 많이 쓰인 글 조각 — 쪽 셋 × 줄 둘
    assert got["losses"] == list(SP.PDF_NOTES) and any("어림" in x for x in got["losses"]) and any("머리말" in x for x in got["losses"])
    assert SP.summary(page, got["body"]) == "A4 세로 · 여백 왼 30 · 오 30 · 위 35 · 아래 30mm · 본문 FooSans 11pt"


@pytest.mark.parametrize("measure", [None, {}, {"count": 0, "pages": []}, {"count": 1, "pages": [{"w": 595.28, "h": 841.89, "lines": []}]},
                                     {"count": 1, "pages": [{"w": 595.28, "h": 841.89, "lines": [{"text": "  ", "bbox": [0, 0, 1, 1]}]}]}])
def test_of_pdf_without_text_is_none(measure):
    assert SP.of_pdf(measure) is None


def test_of_pdf_does_not_read_an_unfilled_page_edge_as_a_margin():
    """글이 쪽을 다 채우지 않은 PDF(표 하나뿐인 한 쪽)의 아래·오른쪽 「가장자리」 는 여백이 아니다 — 맞은편 여백과 같게 두고 알린다(실측 2026-11-14: 「아래 219mm」)."""
    sheet = _sheet()
    top = min(ln["bbox"][1] for ln in sheet["lines"] if ln["text"].strip())
    short = {**sheet, "lines": [ln for ln in sheet["lines"] if ln["text"].strip() and ln["bbox"][1] <= top + 1]}  # 맨 윗줄만 남긴 쪽
    got = SP.of_pdf({"count": 1, "pages": [short]})
    m = got["page"]["marginsMm"]
    assert m["b"] == m["t"] and m["b"] < 60 and any("아래 여백" in x for x in got["losses"]) and got["losses"][:2] == list(SP.PDF_NOTES)
