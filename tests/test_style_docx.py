"""docx 운반 문서(spec_서식복사 ② §4 · §10 — app/style_docx.py): 지은 docx 가 `DocxDoc` 으로 열림 · 표 명세 왕복(`style_carrier.spec_of_block`) · 글 item 의 서식 요약 왕복 ·
문서 서식 왕복(`style_page.of_docx`) · losses(넓은 표 · Word 에 없는 선 · 자동 번호 · 어긋난 칸) · `build` 가름 · 다른 docx 로 복사(적용 때의 `src`). 한글·Word 없이."""
import io
import zipfile

import pytest
from lxml import etree

from app import style_carrier as SC
from app import style_docx as D
from app import style_page as SP
from app.docx_doc import DocxDoc
from app.hwpx_doc import HwpxDoc, P

W = D.W
LINE = {"type": "SOLID", "widthMm": 0.12, "color": "#000000"}
THICK = {"type": "SOLID", "widthMm": 0.4, "color": "#FF0000"}
BOX = {"t": LINE, "r": LINE, "b": LINE, "l": LINE}
HEAD = {"font": "맑은 고딕", "sizePt": 11, "bold": True, "italic": False, "underline": False, "color": "#000000", "align": "center", "lineSpacingPct": 130}
BODY = {"font": "바탕", "sizePt": 9.5, "bold": False, "italic": True, "underline": True, "color": "#1F3864", "align": "right", "lineSpacingPct": 160}
CHAR_KEYS = ("font", "sizePt", "bold", "italic", "underline", "color", "align", "lineSpacingPct")


def _cell(row, col, text, fmt, **more):
    return {"row": row, "col": col, "rowSpan": 1, "colSpan": 1, "text": text, "fill": None, "valign": "center",
            "marginsMm": {"l": 1.8, "r": 1.8, "t": 0.5, "b": 0.5}, "edges": dict(BOX), "format": dict(fmt), **more}


def _spec():
    """3행 × 3열 — 머리행(음영·굵게: 가로로 합친 칸 하나) · 세로로 합친 머리열 칸 · 선 없는 변·굵은 빨간 선·점선 · 칸 글 두 줄."""
    return {"rows": 3, "cols": 3, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}, "widthsMm": [30, 50.5, 40],
            "cells": [_cell(0, 0, "구분", HEAD, fill="#D9D9D9"),
                      _cell(0, 1, "내용", HEAD, fill="#D9D9D9", colSpan=2, edges={**BOX, "b": THICK}),
                      _cell(1, 0, "가나다", HEAD, rowSpan=2, valign="top", edges={**BOX, "l": None}),
                      _cell(1, 1, "첫 줄\n둘째 줄", BODY, marginsMm={"l": 3, "r": 1, "t": 1, "b": 2}),
                      _cell(1, 2, "0", BODY, valign="bottom", edges={**BOX, "r": {"type": "DOT", "widthMm": 0.25, "color": "#0000FF"}}),
                      _cell(2, 1, "", BODY),
                      _cell(2, 2, "0", BODY, fill="#FFF2CC")]}


def _table(data):
    """지은 docx → (DocxDoc, 표 블록 하나)."""
    doc = DocxDoc(data)
    tables = [b for b in doc.blocks() if b["type"] == "table"]
    assert len(tables) == 1
    return doc, tables[0]


def _same_edge(want, got):
    if want is None:
        assert got is None
        return
    assert got is not None and got["type"] == want["type"] and got["color"] == want["color"]
    assert got["widthMm"] == pytest.approx(want["widthMm"], abs=0.03)


def test_package_is_minimal_and_deterministic():
    data, losses = D.from_table_spec(_spec())
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert names[0] == "[Content_Types].xml"
    assert set(names) == {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml", "word/settings.xml", "word/_rels/document.xml.rels"}
    assert losses == []
    assert D.from_table_spec(_spec())[0] == data  # 같은 명세 → 같은 바이트
    for n in names:  # 멤버마다 XML 로 읽힌다
        etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read(n))


def test_table_opens_as_one_table_between_blank_paragraphs():
    doc, tb = _table(D.from_table_spec(_spec())[0])
    kinds = [b["type"] for b in doc.blocks()]
    assert kinds == ["paragraph", "table", "paragraph"]
    assert (tb["nRows"], tb["nCols"]) == (3, 3) and len(tb["cells"]) == 7
    assert D.table_id(doc) == tb["id"]
    assert len(D.para_ids(doc)) == 2
    assert doc.save() == D.from_table_spec(_spec())[0]  # 읽기만 해서는 안 바뀐다


def test_table_spec_round_trips_through_docxdoc():
    spec = _spec()
    _, tb = _table(D.from_table_spec(spec)[0])
    got = SC.spec_of_block(tb)
    assert (got["rows"], got["cols"]) == (3, 3)
    assert got["widthsMm"] == pytest.approx(spec["widthsMm"], abs=0.5)
    assert got["bands"]["headerRows"] == 1  # 음영·굵게 머리행이 다시 읽힌다
    want = {(c["row"], c["col"]): c for c in spec["cells"]}
    have = {(c["row"], c["col"]): c for c in got["cells"]}
    assert set(have) == set(want)
    for rc, w in want.items():
        g = have[rc]
        assert (g["rowSpan"], g["colSpan"], g["text"], g["fill"], g["valign"]) == (w["rowSpan"], w["colSpan"], w["text"], w["fill"], w["valign"]), rc
        assert g["marginsMm"] == pytest.approx(w["marginsMm"], abs=0.06), rc
        for k in CHAR_KEYS:
            assert g["format"][k] == w["format"][k], (rc, k)
        for side in "trbl":
            _same_edge(w["edges"][side], g["edges"][side])


def test_merged_cells_use_gridspan_and_vmerge():
    data = D.from_table_spec(_spec())[0]
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    rows = root.findall(f".//{W}tr")
    assert [len(tr.findall(f"{W}tc")) for tr in rows] == [2, 3, 3]
    assert rows[0].findall(f"{W}tc")[1].find(f"{W}tcPr/{W}gridSpan").get(W + "val") == "2"
    start, cont = (rows[r].find(f"{W}tc") for r in (1, 2))
    assert start.find(f"{W}tcPr/{W}vMerge").get(W + "val") == "restart"
    assert cont.find(f"{W}tcPr/{W}vMerge").get(W + "val") is None
    # 이어지는 칸은 글 없이, 선·세로 정렬은 첫 칸과 같게(Word 는 합친 칸의 아래 선을 마지막 칸에서 읽는다)
    assert "".join(cont.itertext()) == "" and len(cont.findall(f"{W}p")) == 1
    assert cont.find(f"{W}tcPr/{W}tcBorders/{W}bottom").get(W + "val") == "single"
    assert cont.find(f"{W}tcPr/{W}tcBorders/{W}left").get(W + "val") == "nil"
    grid = [int(g.get(W + "w")) for g in root.findall(f".//{W}tblGrid/{W}gridCol")]
    assert rows[0].findall(f"{W}tc")[1].find(f"{W}tcPr/{W}tcW").get(W + "w") == str(grid[1] + grid[2])
    assert root.find(f".//{W}tblPr/{W}tblLayout").get(W + "type") == "fixed"


def test_wide_table_is_scaled_to_the_text_width():
    spec = _spec()
    spec["widthsMm"] = [60, 120, 160]  # 340mm → 170mm
    data, losses = D.from_table_spec(spec)
    assert any("표 폭 340mm" in x and "줄였습니다" in x for x in losses)
    got = SC.spec_of_block(_table(data)[1])
    assert got["widthsMm"] == pytest.approx([30, 60, 80], abs=0.5)


def test_missing_widths_split_the_text_width_evenly():
    spec = _spec()
    spec["widthsMm"] = None
    data, losses = D.from_table_spec(spec)
    assert losses == []
    assert SC.spec_of_block(_table(data)[1])["widthsMm"] == pytest.approx([170 / 3] * 3, abs=0.5)


def test_line_kinds_word_lacks_become_the_nearest_and_are_reported():
    spec = _spec()
    spec["cells"][0]["edges"] = {"t": {"type": "LONG_DASH", "widthMm": 0.12, "color": "#000000"}, "r": {"type": "CIRCLE", "width": "0.4 mm", "color": "#00FF00"},
                                 "b": {"type": "WAVY_UNKNOWN", "widthMm": 0.12, "color": "#000000"}, "l": {"type": "DOUBLE_SLIM", "widthMm": 0.5, "color": "#000000"}}
    data, losses = D.from_table_spec(spec)
    assert sum("Word 에 없는 선 종류" in x for x in losses) == 3 and not any("DOUBLE_SLIM" in x for x in losses)
    edges = next(c for c in SC.spec_of_block(_table(data)[1])["cells"] if (c["row"], c["col"]) == (0, 0))["edges"]
    assert (edges["t"]["type"], edges["r"]["type"], edges["b"]["type"], edges["l"]["type"]) == ("DASH", "DOT", "SOLID", "DOUBLE_SLIM")
    assert edges["r"]["widthMm"] == pytest.approx(0.4, abs=0.03) and edges["r"]["color"] == "#00FF00"  # 「0.4 mm」 꼴의 굵기도 읽는다


def test_cells_off_the_grid_are_dropped_and_holes_filled():
    spec = _spec()
    spec["cells"] = [c for c in spec["cells"] if (c["row"], c["col"]) != (2, 1)]  # 빈 자리 하나
    spec["cells"].append(_cell(1, 1, "겹침", BODY))  # 겹치는 칸
    spec["cells"].append(_cell(5, 0, "밖", BODY))  # 격자 밖
    data, losses = D.from_table_spec(spec)
    assert any("버린 칸 2개" in x and "메운 자리 1곳" in x for x in losses)
    tb = _table(data)[1]
    assert (tb["nRows"], tb["nCols"]) == (3, 3) and len(tb["cells"]) == 7


@pytest.mark.parametrize("bad", [None, {}, {"rows": 1, "cols": 1, "cells": []}, {"rows": "x", "cols": 1, "cells": [{"row": 0, "col": 0}]},
                                 {"rows": 0, "cols": 1, "cells": [{"row": 0, "col": 0}]}])
def test_bad_table_spec_is_refused(bad):
    with pytest.raises(ValueError):
        D.from_table_spec(bad)


def test_spec_from_measurement_keys_only_what_it_has():
    """PDF 에서 잰 명세처럼 글 모양이 일부만 있고 괘선·칸 여백을 모르는 칸 — 지어지고, 없는 값은 Word 기본."""
    spec = {"rows": 1, "cols": 2, "bands": None, "widthsMm": None,
            "cells": [{"row": 0, "col": 0, "text": "가", "format": {"sizePt": 12, "bold": True}}, {"row": 0, "col": 1, "text": "나\t다", "edges": None, "format": None}]}
    data, losses = D.from_table_spec(spec)
    assert losses == []
    cells = SC.spec_of_block(_table(data)[1])["cells"]
    assert cells[0]["format"]["sizePt"] == 12 and cells[0]["format"]["bold"] is True
    assert cells[1]["text"] == "나\t다" and cells[1]["edges"] == {"t": None, "r": None, "b": None, "l": None}


# ---- 글 서식 --------------------------------------------------------------------------------------------------------

def _items():
    return [{"key": "i1", "name": "□ 1", "level": 1, "marker": {"mode": "literal", "literal": "□", "lead": " ", "gap": " ", "family": None}, "sample": " □ 견본 글입니다",
             "format": {"font": "맑은 고딕", "sizePt": 13, "bold": True, "italic": False, "underline": False, "color": "#000000", "ratioPct": 100, "spacingPct": 0,
                        "align": "justify", "lineSpacingPct": 160, "indentLeftMm": 5, "indentRightMm": 2, "firstLineMm": 3, "spaceBeforePt": 6, "spaceAfterPt": 3}},
            {"key": "i2", "name": "자동 번호 2", "level": 2, "marker": {"mode": "auto", "literal": "", "lead": "", "gap": "", "family": None}, "sample": "견본 글입니다",
             "format": {"font": "바탕", "sizePt": 10, "bold": False, "italic": False, "underline": False, "color": "#404040", "ratioPct": 95, "spacingPct": -5,
                        "align": "left", "lineSpacingPct": 130, "indentLeftMm": 0, "indentRightMm": 0, "firstLineMm": 0, "spaceBeforePt": 0, "spaceAfterPt": 0}},
            {"key": "i3", "name": "문단 3", "level": None, "marker": {"mode": "none", "literal": "", "lead": "", "gap": "", "family": None}, "sample": "",
             "format": {"sizePt": 9.7, "align": "center", "indentLeftMm": 10, "firstLineMm": -4}}]


def test_text_items_become_one_sample_paragraph_each():
    items = _items()
    data, losses = D.from_text_items(items)
    doc = DocxDoc(data)
    blocks = doc.blocks()
    assert [b["type"] for b in blocks] == ["paragraph"] * 3
    assert [b["id"] for b in blocks] == D.para_ids(doc)
    assert [b["text"] for b in blocks] == [" □ 견본 글입니다", "견본 글입니다", "견본 글입니다"]  # 앞 빈칸을 지킨다 · 빈 sample 은 견본 글로
    for b, it in zip(blocks[:2], items[:2]):  # 서식 요약 왕복(크기·굵게·정렬·줄 간격·여백 …)
        for k, v in it["format"].items():
            assert b["format"][k] == (pytest.approx(v, abs=0.06) if isinstance(v, float) or k.endswith(("Mm", "Pt")) else v), (it["key"], k)
    assert any("자동 번호" in x and "자동 번호 2" in x for x in losses)


def test_text_size_rounds_to_half_points_and_hanging_indent_keeps_the_first_line_in_place():
    data, losses = D.from_text_items(_items())
    f = DocxDoc(data).blocks()[2]["format"]
    assert f["sizePt"] == 9.5 and any("9.7pt" in x and "9.5pt" in x for x in losses)
    # 한글의 내어쓰기(왼쪽 10 · 첫 줄 −4) = 첫 줄 10mm · 둘째 줄부터 14mm → Word: left 14 · hanging 4
    assert f["firstLineMm"] == pytest.approx(-4, abs=0.06) and f["indentLeftMm"] == pytest.approx(14, abs=0.06)
    assert f["align"] == "center" and f["lineSpacingPct"] == 100 and f["spaceAfterPt"] == 0


@pytest.mark.parametrize("bad", [None, [], ["x"], {"items": []}])
def test_bad_text_items_are_refused(bad):
    with pytest.raises(ValueError):
        D.from_text_items(bad)


# ---- 문서 서식 ------------------------------------------------------------------------------------------------------

def _page(**over):
    return {"widthMm": 210, "heightMm": 297, "landscape": False, "marginsMm": {"l": 30, "r": 25, "t": 35, "b": 30, "header": 15, "footer": 10, "gutter": 0}, **over}


def _same_page(got, want):
    assert got["landscape"] is want["landscape"]
    assert (got["widthMm"], got["heightMm"]) == pytest.approx((want["widthMm"], want["heightMm"]), abs=0.1)
    assert got["marginsMm"] == pytest.approx(want["marginsMm"], abs=0.1)


def test_page_round_trips_through_of_docx():
    body = {"format": {"font": "바탕", "sizePt": 11, "bold": False, "align": "justify", "lineSpacingPct": 160}, "count": 7}
    data, losses = D.from_page(_page(), body)
    assert losses == []
    doc = DocxDoc(data)
    got = SP.of_docx(doc)
    _same_page(got["page"], SP.clean(_page()))
    assert got["losses"] == []
    assert [b["text"] for b in doc.blocks()] == SP.SAMPLES and len(D.para_ids(doc)) == 3
    assert got["body"]["count"] == 3
    for k, v in body["format"].items():
        assert got["body"]["format"][k] == v, k


def test_page_margins_are_written_the_way_word_means_them():
    """위 여백 = 종이 끝에서 본문까지 → Word 의 top · 머리말 몫을 뺀 것이 Word 의 header(종이 끝에서 머리말까지)."""
    data = D.from_page(_page(), None)[0]
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    sect = root.find(f"{W}body/{W}sectPr")
    assert root.find(f"{W}body")[-1] is sect
    mar = {k: int(sect.find(W + "pgMar").get(W + k)) for k in ("top", "right", "bottom", "left", "header", "footer", "gutter")}
    tw = lambda mm: round(mm * 1440 / 25.4)  # noqa: E731
    assert mar == {"top": tw(35), "right": tw(25), "bottom": tw(30), "left": tw(30), "header": tw(20), "footer": tw(20), "gutter": 0}
    assert sect.find(W + "pgSz").get(W + "orient") is None


def test_landscape_page_round_trips():
    page = _page(widthMm=297, heightMm=210, landscape=True)
    data = D.from_page(page, None)[0]
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    size = root.find(f"{W}body/{W}sectPr/{W}pgSz")
    assert size.get(W + "orient") == "landscape" and int(size.get(W + "w")) > int(size.get(W + "h"))
    got = SP.of_docx(DocxDoc(data))
    _same_page(got["page"], SP.clean(page))
    assert got["page"]["landscape"] is True


def test_bad_page_is_refused():
    with pytest.raises(ValueError):
        D.from_page({"widthMm": 210}, None)
    with pytest.raises(ValueError):
        D.from_page(None, None)


# ---- build · 복사 ---------------------------------------------------------------------------------------------------

def test_build_picks_by_kind():
    carrier, info = SC.from_table_spec(_spec(), keep_text=True)
    meta = {"kind": "table", "bands": info["bands"]}
    data, losses = D.build(meta, carrier)
    tb = _table(data)[1]
    assert (tb["nRows"], tb["nCols"]) == (3, 3)
    assert {(c["row"], c["col"]): c["text"] for c in tb["cells"]} == SC.cell_texts(carrier)  # hwpx 운반 문서에 남은 글 그대로
    assert isinstance(losses, list)

    data, _ = D.build({"kind": "text", "items": _items()}, b"")
    assert len(DocxDoc(data).blocks()) == 3
    data, _ = D.build({"kind": "page", "page": _page(), "body": None}, b"")
    _same_page(SP.of_docx(DocxDoc(data))["page"], SP.clean(_page()))


@pytest.mark.parametrize("meta", [None, {}, {"kind": "chart"}, {"kind": "text"}, {"kind": "page"}, {"kind": "table"}])
def test_build_refuses_what_it_cannot_make(meta):
    with pytest.raises(ValueError):
        D.build(meta, b"not a zip")


def test_carrier_table_copies_into_another_docx_with_its_look():
    """적용 때의 길(`DocxDoc.insert_after([{kind: "copy", srcId}], src=운반 문서)`) — 모양이 직접 서식이라 받는 문서에서도 같은 명세로 읽힌다."""
    src = DocxDoc(D.from_table_spec(_spec())[0])
    dst = DocxDoc(D.from_text_items(_items())[0])
    new = dst.insert_after(D.para_ids(dst)[0], [{"kind": "copy", "srcId": D.table_id(src)}], src=src)[0]
    again = DocxDoc(dst.save())
    tb = next(b for b in again.blocks() if b["type"] == "table")
    assert new.startswith("t")
    got = {(c["row"], c["col"]): c for c in SC.spec_of_block(tb)["cells"]}
    for c in _spec()["cells"]:
        g = got[c["row"], c["col"]]
        assert (g["text"], g["fill"], g["format"]["sizePt"], g["format"]["bold"], g["format"]["align"]) == (c["text"], c["fill"], c["format"]["sizePt"], c["format"]["bold"], c["format"]["align"])


# ---- 표지 서식(spec_서식복사 ② §14) -----------------------------------------------------------------------------------

def _cover_parts():
    """`style_cover.view` 의 parts 꼴 — 글 셋(앞 간격 30mm · 0 · 5mm) + 잇단 표 둘(앞 간격 12mm · 없음)."""
    return [{"type": "text", "key": "p1", "role": "title", "sample": "제목", "format": {"font": "맑은 고딕", "sizePt": 22, "bold": True, "align": "center", "lineSpacingPct": 160}, "gapBeforeMm": 30},
            {"type": "text", "key": "p2", "role": "date", "sample": "0000. 00. 00.", "format": {"sizePt": 14, "align": "center", "spaceBeforePt": 6}, "gapBeforeMm": 0},
            {"type": "table", "key": "p3", "spec": _spec(), "gapBeforeMm": 12},
            {"type": "table", "key": "p4", "spec": _spec()},
            {"type": "text", "key": "p5", "role": "org", "sample": "기관명", "format": {"sizePt": 16, "align": "right"}, "gapBeforeMm": 5}]


def test_cover_parts_become_paragraphs_and_tables_on_the_cover_page():
    data, losses = D.from_cover(_cover_parts(), _page())
    assert losses == [] and D.from_cover(_cover_parts(), _page())[0] == data
    doc = DocxDoc(data)
    blocks = doc.blocks()
    # 글 둘 · 간격 문단(12mm) · 표 · 사이 문단(잇단 표를 Word 가 하나로 붙이지 않게) · 표 · 글
    assert [b["type"] for b in blocks] == ["paragraph", "paragraph", "paragraph", "table", "paragraph", "table", "paragraph"]
    texts = [b for b in blocks if b["type"] == "paragraph" and b["text"].strip()]
    assert [b["text"] for b in texts] == ["제목", "0000. 00. 00.", "기관명"]
    title = texts[0]["format"]
    assert (title["sizePt"], title["bold"], title["align"], title["lineSpacingPct"]) == (22, True, "center", 160)
    mm = lambda v: v * 72 / 25.4  # noqa: E731 — 앞 간격(mm)은 문단 위 간격(pt)에 더해진다
    assert [b["format"]["spaceBeforePt"] for b in texts] == pytest.approx([mm(30), 6, mm(5)], abs=0.1)
    for tb in (b for b in blocks if b["type"] == "table"):
        got = SC.spec_of_block(tb)
        assert (got["rows"], got["cols"]) == (3, 3) and got["widthsMm"] == pytest.approx(_spec()["widthsMm"], abs=0.5)
    _same_page(SP.of_docx(doc)["page"], SP.clean(_page()))
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    gap = root.find(f"{W}body")[2].find(f"{W}pPr/{W}spacing")  # 표 앞 간격 = 줄 높이를 고정한 빈 문단
    assert gap.get(W + "lineRule") == "exact" and int(gap.get(W + "line")) == round(12 * 1440 / 25.4)


def test_cover_table_is_scaled_to_a_narrow_cover_page_and_a_cover_may_end_with_a_table():
    narrow = _page(marginsMm={"l": 60, "r": 60, "t": 35, "b": 30, "header": 15, "footer": 10, "gutter": 0})  # 글 폭 90mm < 표 120.5mm
    data, losses = D.from_cover(_cover_parts()[2:3], narrow)
    assert any("표 폭" in x and "줄였습니다" in x for x in losses)
    blocks = DocxDoc(data).blocks()
    assert [b["type"] for b in blocks] == ["paragraph", "table", "paragraph"]  # 앞 간격 · 표 · 닫는 문단(Word 는 표 뒤에 문단이 있어야 한다)
    assert sum(SC.spec_of_block(blocks[1])["widthsMm"]) == pytest.approx(90, abs=0.5)


@pytest.mark.parametrize("parts", [None, [], ["x"], [{"type": "image"}], [{"type": "table", "spec": None}]])
def test_bad_cover_is_refused(parts):
    with pytest.raises(ValueError):
        D.from_cover(parts, _page())
    with pytest.raises(ValueError):
        D.from_cover(_cover_parts(), {"widthMm": 210})


def test_build_cover_reads_the_parts_from_the_hwpx_carrier():
    from app import style_cover as C
    d, first, plain = SC.open_base()
    like = d._id(next(d._ids[plain].iter(P)))
    d.set_text(first, "연구개발 계획서")
    d.apply_format([first], d.derive_format(d.get_format(like), {"sizePt": 20, "bold": True, "align": "center"}))
    d.insert_after(first, [{"kind": "paragraph", "text": "2026. 3.", "templateId": like}])
    src = HwpxDoc(d.save())
    carrier, info = C.carrier(src, [b["id"] for b in src.blocks()])  # 문단 둘 + 평범한 2×2 표
    data, losses = D.build({"kind": "cover", "page": info["page"], "parts": info["parts"]}, carrier)
    doc = DocxDoc(data)
    blocks = doc.blocks()
    assert [b["text"] for b in blocks if b["type"] == "paragraph" and b["text"].strip()] == ["제목", "0000. 00. 00."]  # 역할 견본 글
    assert sum(b["type"] == "table" for b in blocks) == 1 and isinstance(losses, list)
    assert blocks[0]["format"]["sizePt"] == 20 and blocks[0]["format"]["align"] == "center"
    got, want = SP.of_docx(doc)["page"], info["page"]
    assert (got["widthMm"], got["heightMm"]) == pytest.approx((want["widthMm"], want["heightMm"]), abs=0.1) and got["marginsMm"] == pytest.approx(want["marginsMm"], abs=0.1)
    with pytest.raises(ValueError):
        D.build({"kind": "cover"}, b"not a zip")
