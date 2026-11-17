"""운반 문서(spec_일반편집 ② §3): hwpx 표·문단에서(쪽 나눔 끔 · 평범한 표 지움 · 자료값 → 견본 · 뺀 것) · 명세에서(음영·괘선·글 모양이 다시 읽힘) · 표 블록 → 명세 · 보기."""
import copy
import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from PIL import Image

from app import owpml_check as C
from app import style_carrier as SC
from app import table_make as M
from app.docx_doc import DocxDoc
from app.hwpx_doc import CTRL, RUN, TC, HwpxDoc, P, T, _h, _p

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, RND, DOCX = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx", SAMPLES / "기술수요조사서.docx"
BIG_TABLE = "t8"  # 기술수요조사서의 18×11 표(머리열 1)


@pytest.fixture(scope="module")
def big():
    """연구개발계획서 양식(읽기만 — 운반 문서 만들기는 원본을 안 바꾼다)."""
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    return d


@pytest.fixture()
def small():
    d = HwpxDoc(SMALL.read_bytes())
    d.blocks()
    return d


def _tables(blocks, out=None):
    out = [] if out is None else out
    for b in blocks:
        if b["type"] == "table":
            out.append(b)
            for c in b["cells"]:
                _tables(c.get("blocks") or [], out)
    return out


def _tops(d):
    return [p for s in d._sections for p in s.iterchildren(P)]


def _ok(data):
    """빈 바탕 대비 OWPML 판정이 fail 이 아닌가 — 운반 문서가 옮겨 온 원본의 위반 종류는 기준선에 더하고 본다(문서 사이 복사의 규칙)."""
    d = HwpxDoc(data)
    res = C.check_doc(d)
    assert not res["rules"], [v["message"] for v in res["rules"]][:3]  # 끊어진 참조·표 격자 위반은 하나도 없어야 한다
    return d


def _para(d, start):
    return next(b["id"] for b in d.blocks() if b["type"] == "paragraph" and b["text"].startswith(start))


def _raw(data) -> str:
    """운반 문서 zip 의 모든 멤버를 풀어 이은 글 — 「그 글이 어디에도 안 남았다」 를 본다(XML · 미리보기 글 · manifest)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())


def _made(rows, shade=(), bold=()):
    """빈 바탕에 평범한 표(음영·굵게 없음)로 지은 문서 -> (HwpxDoc, 표 id). shade·bold = 음영·굵게를 줄 (행, 열)들(「all」 = 모든 칸)."""
    d, first, plain = SC.open_base()
    tid = d.table_make(first, plain, M.normalize({"rows": rows}), SC.ZERO)["table"]
    d.delete_blocks(plain, plain)
    for c in d.table_block(tid)["cells"]:
        rc = (c["row"], c["col"])
        if shade == "all" or rc in shade:
            d.apply_cell_format([c["id"]], {"fill": "#D9E2F3"}, ["fill"])
        if bold == "all" or rc in bold:
            d.apply_cell_format([c["id"]], {"text": d.derive_format(d.get_cell_format(c["id"])["text"], {"bold": True})}, ["text"])
    return d, tid


def _texts(data):
    d = SC.doc(data)
    tb = d.table_block(SC.table_id(d))
    at = {(c["row"], c["col"]): c["text"] for c in tb["cells"]}
    return [[at.get((r, k)) for k in range(tb["nCols"])] for r in range(tb["nRows"])]


def _png(color):
    buf = io.BytesIO()
    Image.new("RGB", (9, 7), color).save(buf, "PNG")
    return buf.getvalue()


def _hide(doc, pid, **secrets):
    """문단 pid 의 첫 글 런에 「보이는 글」 이 아닌 딸린 내용을 손으로 붙인다 — 각주 · 필드(하이퍼링크) · 숨은 설명 · 책갈피 · 글자 겹치기 · 덧말 · 글 조각 안의 낯선 요소."""
    p = doc._ids[pid]
    run = doc._first_run(p)

    def sub_text(parent, text):
        q = etree.SubElement(etree.SubElement(parent, _p("subList")), P, {"paraPrIDRef": p.get("paraPrIDRef"), "styleIDRef": p.get("styleIDRef", "0")})
        etree.SubElement(etree.SubElement(q, RUN, {"charPrIDRef": run.get("charPrIDRef")}), T).text = text
    sub_text(etree.SubElement(etree.SubElement(run, CTRL), _p("footNote"), {"number": "1", "instId": "1"}), secrets["foot"])
    etree.SubElement(etree.SubElement(run, CTRL), _p("fieldBegin"), {"id": "1", "type": "HYPERLINK", "name": secrets["field"], "command": secrets["field"]})
    sub_text(etree.SubElement(etree.SubElement(run, CTRL), _p("hiddenComment")), secrets["memo"])
    etree.SubElement(etree.SubElement(run, CTRL), _p("bookmark"), {"name": secrets["mark"]})
    etree.SubElement(run, _p("compose"), {"composeText": secrets["compose"]})
    etree.SubElement(etree.SubElement(run, _p("dutmal")), _p("subText")).text = secrets["dutmal"]
    etree.SubElement(run.find(T), _p("unknownInline")).text = secrets["inline"]
    doc._drop_cache(p)
    doc._touch(p)


SECRETS = {"foot": "PRIVATE_ACCOUNT_123456", "field": "https://secret.example/회계", "memo": "SECRET_MEMO", "mark": "SECRET_BOOKMARK", "compose": "SECRET_COMPOSE",
           "dutmal": "SECRET_DUTMAL", "inline": "SECRET_INLINE"}


# ---- 빈 바탕 --------------------------------------------------------------------------------------------------------

def test_base_is_first_paragraph_plus_plain_table():
    d, first, plain = SC.open_base()
    assert SC.base() is SC.base() and [b["type"] for b in d.blocks()] == ["paragraph", "table"] and d.blocks()[0]["id"] == first
    tb = d.table_block(plain)
    assert (tb["nRows"], tb["nCols"]) == (2, 2) and all(not c["text"] and c["fill"] is None for c in tb["cells"]) and SC.table_id(d) == plain
    assert len(_tops(d)) == 2 and SC.para_ids(d) == [d._id(_tops(d)[1])] and SC.fonts_of(d)
    d2 = SC.doc(SC.base())
    assert SC.table_id(d2) == plain  # 다시 열어도 같은 id(블록 차례)
    with pytest.raises(ValueError):
        SC.doc(b"not a zip")


# ---- hwpx 표에서 ----------------------------------------------------------------------------------------------------

def test_from_table_copies_look_and_replaces_data_values(small):
    src = small.table_block(BIG_TABLE)
    data, info = SC.from_table(small, BIG_TABLE, None)
    assert not small._dirty and small.save() == SMALL.read_bytes()  # 원본 문서는 안 바뀐다
    d = _ok(data)
    assert [b["type"] for b in d.blocks()] == ["paragraph", "table"] and len(_tables(d.blocks())) == 1 and len(_tops(d)) == 2  # 첫 문단 + 표 하나(평범한 2×2 는 지움)
    assert all((p.get("pageBreak"), p.get("columnBreak")) == ("0", "0") for p in _tops(d))
    tb = d.table_block(SC.table_id(d))
    assert (tb["nRows"], tb["nCols"]) == (18, 11) == (info["rows"], info["cols"]) and info["bands"] == {"headerRows": 0, "headerCols": 1, "footRows": 0}
    key = lambda c: (c["row"], c["col"], c["rowSpan"], c["colSpan"])  # noqa: E731
    was = {key(c): c for c in src["cells"]}
    assert sorted(was) == sorted(map(key, tb["cells"]))
    for c in tb["cells"]:
        w = was[key(c)]
        assert (c["fill"], c["valign"], c["marginsMm"], c["widthMm"]) == (w["fill"], w["valign"], w["marginsMm"], w["widthMm"]), key(c)  # 칸 모양·폭 그대로
        if c["col"] == 0:
            assert c["text"] == w["text"]  # 머리열 = 라벨 — 글 그대로
        else:
            assert c["text"] == ("가나다" if w["text"].strip() else "") and len(c["blocks"]) == 1  # 자료값은 견본으로 · 빈 칸은 빈 채 · 문단 하나
    texts = " ".join(c["text"] for c in tb["cells"])
    assert "제안기술 분류" in texts and "전력변환시스템" not in texts and "작성가이드라인" not in texts
    assert SC.STYLE_NOTE in info["losses"] and "맑은 고딕" in info["fonts"] and info["fonts"] == sorted(info["fonts"])
    g = info["preview"]["grid"]
    assert len(g["rows"]) == 18 and g["headerCols"] == 1 and g["rows"][0]["cells"][0] == {"text": "제안기술 분류", "rowSpan": 3, "colSpan": 1}
    assert all(len(c["text"]) <= 40 for r in g["rows"] for c in r["cells"])
    looks = info["preview"]["looks"]
    assert looks["head"] is None and looks["foot"] is None and looks["stub"]["fill"] == was[0, 0, 3, 1]["fill"] and looks["stub"]["bold"] is True and looks["body"]["font"]
    # 글 모양도 그대로 — 견본 칸의 첫 문단 서식 = 원본 칸의 첫 글 문단 서식
    c0 = next(c for c in tb["cells"] if key(c) == (0, 1, 1, 1))
    w0 = next(b for b in was[0, 1, 1, 1]["blocks"] if b["text"].strip())
    assert c0["blocks"][0]["format"] == w0["format"]


def test_from_table_keep_text_bands_and_number_samples(small):
    cells = {(c["row"], c["col"]): c["id"] for c in small.table_block(BIG_TABLE)["cells"]}
    for rc, text in (((0, 2), "1,234"), ((0, 7), "-"), ((0, 10), "12.5%"), ((1, 2), "(3)")):
        small.set_text(cells[rc], text)
    data, info = SC.from_table(small, BIG_TABLE, {"headerRows": 1, "headerCols": 0, "footRows": 0})
    tb = SC.doc(data).table_block("t2")
    at = {(c["row"], c["col"]): c["text"] for c in tb["cells"]}
    assert info["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 0}
    assert at[0, 2] == "1,234" and at[0, 0] == "제안기술 분류"  # 머리행(띠 수를 준 대로)은 글 그대로
    assert at[1, 2] == "0" and at[3, 0] == "가나다"  # 머리 띠 밖: 수 꼴 → 0 · 글 → 가나다
    assert [SC.sample_of(t) for t in ("", "  ", "1,234", "-", "12.5%", "(3)", "0,000", "3 ~ 5", "△12", "3월", "N/A", "–", "( )")] == ["", "", "0", "0", "0", "0", "0", "0", "0", "가나다", "가나다", "0", "가나다"]
    kept, _ = SC.from_table(small, BIG_TABLE, None, keep_text=True)
    assert [c["text"] for c in SC.doc(kept).table_block("t2")["cells"]] == [c["text"] for c in small.table_block(BIG_TABLE)["cells"]]  # keep_text — 글 그대로
    total = {"headerRows": 0, "headerCols": 0, "footRows": 1}
    assert SC.is_label(17, 0, "합 계", total, 18) and not SC.is_label(17, 1, "1,000", total, 18) and not SC.is_label(16, 0, "합계", total, 18)  # 머리열 없는 표의 합계 라벨


def test_from_table_resets_page_break_and_drops_nested_tables(big, small):
    host = small._host(small._ids[BIG_TABLE])
    host.set("pageBreak", "1")  # 쪽을 나누는 문단에 든 표 — 그대로 옮기면 운반 문서 첫 쪽이 빈다
    data, _ = SC.from_table(small, BIG_TABLE, None)
    assert all((p.get("pageBreak"), p.get("columnBreak")) == ("0", "0") for p in _tops(HwpxDoc(data))) and host.get("pageBreak") == "1"
    nested = next(b for b in big.blocks() if b["type"] == "table" and M.block_nested(b) and big._host(big._ids[b["id"]]).get("pageBreak") == "1")
    data, info = SC.from_table(big, nested["id"], None)
    d = _ok(data)
    assert len(_tables(d.blocks())) == 1 and not M.block_nested(d.table_block(SC.table_id(d)))  # 칸 안 표·그림은 뺀다(칸은 글만)
    assert any("칸 안 표·그림" in x for x in info["losses"]) and all(p.get("pageBreak") == "0" for p in _tops(d))
    assert (info["rows"], info["cols"]) == (nested["nRows"], nested["nCols"]) and not big._dirty


def test_from_table_adds_losses_only_when_they_happen(big, small):
    assert SC.from_table(small, BIG_TABLE, None)[1]["losses"] == [SC.STYLE_NOTE]  # 캡션·칸 안 표·그림 채움·newNum 이 없는 표
    with_new_num = next((b for b in big.blocks() if b["type"] == "table" and next(big._ids[b["id"]].iter("{*}newNum"), None) is not None), None)
    if with_new_num is not None:
        assert any("newNum" in x for x in SC.from_table(big, with_new_num["id"], None)[1]["losses"])
    tbl = small._ids[BIG_TABLE]
    cap = tbl.makeelement("{http://www.hancom.co.kr/hwpml/2011/paragraph}caption", {})
    tbl.append(cap)
    data, info = SC.from_table(small, BIG_TABLE, None)
    assert any("캡션" in x for x in info["losses"]) and next(HwpxDoc(data)._sections[0].iter("{*}caption"), None) is None


def test_from_table_fits_wide_table_to_base_body(small):
    small.set_line_sizes(BIG_TABLE, "c", {0: 80.0})  # 표 폭 227mm — A4 바탕의 글 폭 170mm 보다 넓다
    data, info = SC.from_table(small, BIG_TABLE, None)
    d = SC.doc(data)
    tb = d.table_block("t2")
    width = sum(c["widthMm"] for c in tb["cells"] if c["row"] == 3)
    assert abs(width - 170.0) < 0.1 and any("표 폭" in x for x in info["losses"]) and int(d._ids["t2"].find("{*}sz").get("width")) == round(d._body_width_mm(_tops(d)[1]) * 7200 / 25.4)


def test_from_table_rejects_missing_table(small):
    for bad in ("t9999", "p10", None, 3):
        with pytest.raises(ValueError):
            SC.from_table(small, bad, None)


# ---- 자료값을 남기지 않는다(astra 10) -----------------------------------------------------------------------------------

PEOPLE = [["홍길동", "910101-1234567"], ["김철수", "920202-2345678"]]


def test_first_row_of_an_unmarked_table_is_not_kept_as_labels():
    """머리글 없는 표는 띠 수 자동 판정이 관례대로 첫 행을 머리행으로 본다(서식용) — 그 행을 라벨로 남기면 첫 사람의 이름·주민번호가 운반 문서·미리보기·빈 표에 실렸다."""
    d, tid = _made(PEOPLE)
    assert M.roles_of(d.table_block(tid)["cells"], 2, 2) == {"headerRows": 1, "headerCols": 0, "footRows": 0}  # 표시가 없어도 첫 행 = 머리행(서식의 구역)
    for bands in (None, {"headerRows": 1, "headerCols": 1, "footRows": 0}, {"headerRows": 2, "headerCols": 2, "footRows": 0}):  # 띠 수를 넓혀 줘도(사람·이름 붙이기 LLM) 근거가 없으면 라벨이 아니다
        data, info = SC.from_table(d, tid, bands)
        assert info["bands"]["headerRows"] >= 1 and info["labels"] == [] and _texts(data) == [["가나다", "0"], ["가나다", "0"]], bands
        raw = _raw(data)
        assert not [s for s in ("홍길동", "김철수", "910101", "1234567", "920202") if s in raw]
        shown = [c["text"] for r in info["preview"]["grid"]["rows"] for c in r["cells"]] + [c["text"] for r in SC.view(data, {"kind": "table", "bands": info["bands"]})["grid"]["rows"] for c in r["cells"]]
        assert set(shown) == {"가나다", "0"}
    # 표 전체가 한 가지(모든 칸 굵게 · 모든 칸 음영)인 것도 머리 띠의 근거가 아니다 — 구별되는 표시가 없다
    for mark in ({"bold": "all"}, {"shade": "all"}):
        d2, t2 = _made(PEOPLE, **mark)
        assert SC.from_table(d2, t2, None)[1]["labels"] == [] and "홍길동" not in _raw(SC.from_table(d2, t2, None)[0])
    kept, info = SC.from_table(d, tid, None, keep_text=True)  # keep_text = 사람이 글째 저장하기로 한 것 — 글은 그대로, 라벨 목록은 같은 규칙
    assert _texts(kept) == PEOPLE and info["labels"] == []


def test_header_band_keeps_labels_only_on_marked_lines_and_never_data_like_text():
    rows = [["이름", "주민번호", "hong@example.com", "010-1234-5678", "2024"], ["홍길동", "910101-1234567", "가", "나", "1"], ["김철수", "920202-2345678", "다", "라", "2"]]
    d, tid = _made(rows, shade=[(0, k) for k in range(5)])
    data, info = SC.from_table(d, tid, None)
    assert info["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 0} and info["labels"] == [[0, 0], [0, 1], [0, 4]]
    assert _texts(data) == [["이름", "주민번호", "가나다", "0", "2024"], ["가나다", "0", "가나다", "가나다", "0"], ["가나다", "0", "가나다", "가나다", "0"]]  # 음영 띠 안이라도 전자우편·전화번호는 견본으로
    assert "hong@" not in _raw(data) and "1234-5678" not in _raw(data)
    # 넓힌 띠 수(머리 2행 · 머리열 1): 둘째 행·첫 열에는 머리 표시(음영·굵게)가 없다 — 그 줄의 글은 자료다
    wide, winfo = SC.from_table(d, tid, {"headerRows": 2, "headerCols": 1, "footRows": 0})
    assert winfo["bands"]["headerRows"] == 2 and winfo["labels"] == info["labels"] and _texts(wide) == _texts(data)
    # 머리열에 표시가 있으면 그 열의 글은 라벨 — 다만 수 꼴 긴 숫자는 아니다
    d2, t2 = _made([["구분", "값"], ["인건비", "100"], ["20240101", "200"], ["합계", "300"]], shade=[(0, 0), (0, 1)], bold=[(1, 0), (2, 0), (3, 0)])
    data2, info2 = SC.from_table(d2, t2, {"headerRows": 1, "headerCols": 1, "footRows": 1})
    assert _texts(data2) == [["구분", "값"], ["인건비", "0"], ["0", "0"], ["합계", "0"]] and info2["labels"] == [[0, 0], [0, 1], [1, 0], [3, 0]]
    d3, t3 = _made([["가", "나"], ["다", "라"], ["합 계", "9"]])  # 머리열 없는 표의 합계 라벨(「합계·소계·계」 꼴의 글)은 표시 없이도 남긴다
    assert _texts(SC.from_table(d3, t3, {"headerRows": 0, "headerCols": 0, "footRows": 1})[0]) == [["가나다", "가나다"], ["가나다", "가나다"], ["합 계", "0"]]
    assert [SC.data_like(t) for t in ("910101-1234567", "123456", "12 34 56", "1,234,567", "hong@example.com", "010-1234-5678", "02) 123-4567", "2024.01.31",
                                      "2024", "2024년 12월", "제1차년도", "합계", "12,345", "1-1.", "(단위: 천원)", "")] == [True] * 8 + [False] * 8
    spec = {"rows": 2, "cols": 2, "cells": [{"row": r, "col": k, "text": PEOPLE[r][k]} for r in range(2) for k in range(2)]}  # 명세(docx·PDF)에서 지을 때도 같은 규칙
    sdata, sinfo = SC.from_table_spec({**spec, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}})
    assert _texts(sdata) == [["가나다", "0"], ["가나다", "0"]] and sinfo["labels"] == [] and "홍길동" not in _raw(sdata)
    spec["cells"][0]["fill"], spec["cells"][1]["format"] = "#D9E2F3", {"bold": True}
    assert _texts(SC.from_table_spec({**spec, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}})[0]) == [["홍길동", "0"], ["가나다", "0"]]  # 표시된 머리행 — 글은 남기되 긴 숫자는 견본


def test_kept_labels_are_rewritten_as_plain_text(small):
    """라벨 칸을 원본 XML 그대로 두면 각주·필드·숨은 설명·책갈피·겹친 글자 같은 딸린 내용이 따라온다(astra: 각주 안의 PRIVATE_ACCOUNT_123456) — 보이는 글만 같은 모양으로 다시 쓴다."""
    cells = {(c["row"], c["col"]): c for c in small.table_block(BIG_TABLE)["cells"]}
    label, body = cells[0, 0], cells[0, 1]
    multi = next(c for c in cells.values() if c["col"] == 0 and c["text"] == "기술개발의\n필요성")  # 줄이 둘인 라벨
    for c in (label, body):
        _hide(small, next(b["id"] for b in c["blocks"] if b["text"].strip()), **SECRETS)
    assert small.table_block(BIG_TABLE)["cells"][0]["text"] == label["text"] == "제안기술 분류"  # 보이는 글은 그대로다(딸린 내용은 칸 글에 안 든다)
    data, info = SC.from_table(small, BIG_TABLE, None)
    raw = _raw(data)
    assert not [s for s in SECRETS.values() if s in raw]
    _ok(data)
    d = SC.doc(data)
    got = {(c["row"], c["col"]): c for c in d.table_block(SC.table_id(d))["cells"]}
    assert got[0, 0]["text"] == "제안기술 분류" and [0, 0] in info["labels"] and got[multi["row"], 0]["text"] == multi["text"]  # 줄이 여럿인 라벨도 줄마다
    fmt = lambda c: [b["format"] for b in c["blocks"] if b["type"] == "paragraph"]  # noqa: E731
    assert fmt(got[0, 0]) == fmt(label) and fmt(got[multi["row"], 0]) == fmt(multi)  # 문단·글자 모양은 그대로
    for tc in d._ids[SC.table_id(d)].iter(TC):
        assert all(ch.tag == T for p in tc.iter(P) for r in p.iterchildren(RUN) for ch in r) and all(len(t) == 0 or {x.tag for x in t} <= {_p("tab"), _p("lineBreak")} for t in tc.iter(T))
    kept = _raw(SC.from_table(small, BIG_TABLE, None, keep_text=True)[0])  # keep_text 는 글째(딸린 내용도) — 사람이 고른 것
    assert SECRETS["foot"] in kept
    lp = small._ids[next(b["id"] for b in label["blocks"] if b["text"].strip())]  # 탭이 든 라벨 — 탭의 폭·채움은 그대로 다시 쓴다
    small.set_text(small._id(lp), "가\t나")
    next(lp.iter(_p("tab"))).set("width", "9999")
    plain = SC._plain_para(small, lp)
    assert small._text(plain) == "가\t나" and next(plain.iter(_p("tab"))).get("width") == "9999" and SECRETS["foot"] not in etree.tostring(plain, encoding="unicode")


def test_cell_picture_bytes_do_not_stay_in_the_carrier(small):
    """칸 안 그림은 운반 문서에 안 싣는데(칸은 글만), 표를 옮길 때 들여온 그림 바이트(BinData)와 manifest 항목이 zip 에 남았다."""
    cells = {(c["row"], c["col"]): c for c in small.table_block(BIG_TABLE)["cells"]}
    pngs = [_png((200, 10, 10)), _png((10, 200, 10))]
    for c, png in zip((cells[0, 0], cells[0, 1]), pngs):  # 라벨 칸 · 자료 칸에 그림 하나씩
        small.insert_image(next(b["id"] for b in c["blocks"]), png, "png")
    assert M.block_nested(small.table_block(BIG_TABLE)) and len([n for n in zipfile.ZipFile(io.BytesIO(small.save())).namelist() if n.startswith("BinData/")]) == 2
    for keep in (False, True):
        data, info = SC.from_table(small, BIG_TABLE, None, keep_text=keep)
        z = zipfile.ZipFile(io.BytesIO(data))
        assert not [n for n in z.namelist() if n.startswith("BinData/")] and b"BinData" not in z.read("Contents/content.hpf"), keep
        assert not any(png in z.read(n) for n in z.namelist() for png in pngs)
        assert any("칸 안 표·그림 2개" in x for x in info["losses"]) and _ok(data) and not M.block_nested(SC.doc(data).table_block("t2"))
    assert sorted(z.namelist()) == sorted(zipfile.ZipFile(io.BytesIO(SC.base())).namelist())  # 빈 바탕의 멤버뿐


def test_builders_refuse_sources_with_dangling_references(small):
    """astra 8: 원본에 없는 정의를 가리키는 참조는 가져올 때 번호 그대로 넘어와 운반 문서(빈 바탕)의 같은 번호 정의에 말없이 붙는다 — 그런 표·문단은 서식으로 저장하지 않는다."""
    assert SC.broken_refs(small) == [] and SC.broken_refs(small, [small._ids[BIG_TABLE]]) == []
    pid = next(b["id"] for c in small.table_block(BIG_TABLE)["cells"] for b in c["blocks"] if b["type"] == "paragraph" and b["text"].strip())
    assert SC.from_paras(small, [{"para": pid}])
    cid = small._first_run(small._ids[pid]).get("charPrIDRef")
    gone = small._defs["charPr"].pop(cid)
    gone.getparent().remove(gone)
    assert any(f"charPrIDRef={cid}" in m for m in SC.broken_refs(small, [small._ids[pid]])) and any(f"charPrIDRef={cid}" in m for m in SC.broken_refs(small))
    assert cid in SC.open_base()[0]._defs["charPr"]  # 빈 바탕에는 그 번호의 글자 모양이 있다 — 막지 않으면 그것에 붙는다
    with pytest.raises(ValueError, match="정의 참조가 깨져"):
        SC.from_paras(small, [{"para": pid}])
    with pytest.raises(ValueError, match="정의 참조가 깨져"):
        SC.from_table(small, BIG_TABLE, None)
    other = HwpxDoc(SMALL.read_bytes())
    other.blocks()
    bf = next(tc.get("borderFillIDRef") for tc in other._ids[BIG_TABLE].iter(TC))
    gone = other._defs["borderFill"].pop(bf)
    gone.getparent().remove(gone)
    with pytest.raises(ValueError, match=f"borderFillIDRef={bf}"):
        SC.from_table(other, BIG_TABLE, None)
    assert SC.broken_refs(other) and SC.from_paras(other, [{"para": pid}])  # 그 정의에 닿지 않는 문단은 된다(문서 어딘가의 손상 때문에 다 막지 않는다)
    third = HwpxDoc(SMALL.read_bytes())
    third.blocks()
    pic = third._ids[third.insert_image(pid, _png((1, 2, 3)), "png")]
    item = third._items.pop(pic.find("{*}img").get("binaryItemIDRef"))
    item.getparent().remove(item)  # 칸 안 그림이 가리키는 그림 항목이 없는 문서
    assert any("binaryItemIDRef" in m for m in SC.broken_refs(third, [third._ids[BIG_TABLE]]))
    data, info = SC.from_table(third, BIG_TABLE, None)  # 그 그림은 어차피 안 옮긴다(칸은 글만) — 옮길 것만 본다
    assert _ok(data) and any("칸 안 표·그림 1개" in x for x in info["losses"])


# ---- hwpx 문단에서 --------------------------------------------------------------------------------------------------

def test_from_paras_marker_literal_auto_none(big, small):
    picks = [{"para": _para(big, "1. "), "level": 1, "name": "장 제목", "origin": {"template": 3, "slot": 1}}, {"para": _para(big, "□ "), "level": 2},
             {"para": _para(big, "  o "), "level": "3"}, {"para": _para(big, "\t(페이지"), "level": None}]
    data, items = SC.from_paras(big, picks)
    assert not big._dirty
    d = _ok(data)
    ids = SC.para_ids(d)
    assert len(ids) == len(items) == 4 and [b["type"] for b in d.blocks()] == ["paragraph"] * 5 and not _tables(d.blocks())  # 첫 문단 + 견본 문단들(평범한 표는 지움)
    assert all((p.get("pageBreak"), p.get("columnBreak")) == ("0", "0") for p in _tops(d))
    assert [i["key"] for i in items] == ["i1", "i2", "i3", "i4"] and [i["level"] for i in items] == [1, 2, None, None]  # 레벨은 준 정수만(지어내지 않는다)
    assert items[0]["name"] == "장 제목" and items[1]["name"] == "□ 2" and items[0]["origin"] == {"template": 3, "slot": 1, "para": picks[0]["para"]}
    assert items[0]["marker"] == {"mode": "literal", "literal": "1.", "lead": "", "gap": " ", "family": "decimal"}
    assert items[1]["marker"] == {"mode": "literal", "literal": "□", "lead": "", "gap": " ", "family": "square"}
    assert items[2]["marker"] == {"mode": "literal", "literal": "o", "lead": "  ", "gap": " ", "family": "latin-o"}
    assert items[3]["marker"] == {"mode": "none", "literal": "", "lead": "", "gap": "", "family": None}
    assert [i["sample"] for i in items] == ["1. 견본 글입니다", "□ 견본 글입니다", "  o 견본 글입니다", "견본 글입니다"] == [d._text(d._ids[i]) for i in ids]
    for it, i, pick in zip(items, ids, picks):
        want = big.get_format(pick["para"])["summary"]
        assert it["format"] == d.get_format(i)["summary"] and {k: it["format"][k] for k in ("font", "sizePt", "bold", "align", "lineSpacingPct", "indentLeftMm")} == \
            {k: want[k] for k in ("font", "sizePt", "bold", "align", "lineSpacingPct", "indentLeftMm")}
        assert it["unsupported"] == []
    # 자동 번호(문단 모양의 hh:heading 이 BULLET) — 레터를 글에 쓰지 않는다
    bullet = next(small._rev[p] for p in small._sections[0].iter(P) if small._heading(p) is not None and small._heading(p).get("type") == "BULLET" and small._text(p).strip())
    data2, items2 = SC.from_paras(small, [{"para": bullet}])
    assert items2[0]["marker"]["mode"] == "auto" and items2[0]["sample"] == "견본 글입니다" and items2[0]["unsupported"] == [SC.AUTO_NOTE] and items2[0]["level"] is None
    d2 = _ok(data2)
    assert d2._heading(d2._ids[SC.para_ids(d2)[0]]).get("type") == "BULLET"  # 번호 설정은 견본 문단의 문단 모양에 그대로
    kept, items3 = SC.from_paras(big, picks[:2], keep_text=True)
    assert [i["sample"] for i in items3] == [big._text(big._ids[p["para"]])[:60] for p in picks[:2]] and items3[0]["marker"]["literal"] == "1."


def test_from_paras_outline_with_blank_number_keeps_typed_letter():
    """개요 문단(OUTLINE)이지만 구역의 개요 번호 모양에서 그 수준의 번호 글이 비었다 = 한글이 번호를 안 그리고 레터는 글로 쳤다(실측 2026-11-17 연구계획서_공통.hwpx —
    「1.」·「2-1.」·「(1)」·「①」 이 모두 자동 번호로 읽혀 회색 「1.」 자리표로 그려졌다). → 레터를 읽고(literal) 운반 문서의 개요 번호 모양도 원본 구역의 것(빈 글)으로.
    번호 글이 있는 모양이면 전처럼 자동 번호(auto)이고, 운반 문서는 원본 구역의 번호 모양을 쓴다(바탕의 「1. 가. 1) …」 이 아니라)."""
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    pid = _para(d, "1. ")
    p = d._ids[pid]
    d._defs["paraPr"][p.get("paraPrIDRef")].find(_h("heading")).attrib.update({"type": "OUTLINE", "idRef": "0", "level": "0"})
    sid = SC.outline_shape(d, p)
    head = next(x for x in d._defs["numbering"][sid].iterchildren(_h("paraHead")) if x.get("level") == "1")

    def shape_text(data):  # 운반 문서 구역의 개요 번호 모양에서 수준 1 의 번호 글
        c = _ok(data)
        num = c._defs["numbering"][next(c._sections[0].iter(SC.SECPR)).get("outlineShapeIDRef")]
        return next(x for x in num.iterchildren(_h("paraHead")) if x.get("level") == "1").text or ""

    head.text = None  # 번호 글이 빈 개요 모양
    assert not SC.shown_number(d, p)
    data, items = SC.from_paras(d, [{"para": pid, "level": 1}])
    assert items[0]["marker"]["mode"] == "literal" and items[0]["marker"]["literal"] == "1." and items[0]["sample"].startswith("1. 견본 글입니다")
    assert items[0]["unsupported"] == [] and shape_text(data) == ""   # 바탕의 「^1.」 이 끼면 한글이 「1. 1. 견본 …」 으로 그린다
    head.text = "^1."  # 번호 글이 있는 개요 모양 — 한글이 번호를 그린다
    assert SC.shown_number(d, p)
    data, items = SC.from_paras(d, [{"para": pid, "level": 1}])
    assert items[0]["marker"]["mode"] == "auto" and items[0]["sample"] == "견본 글입니다" and items[0]["unsupported"] == [SC.AUTO_NOTE] and shape_text(data) == "^1."
    d._defs["paraPr"][p.get("paraPrIDRef")].find(_h("heading")).set("type", "NONE")
    assert not SC.shown_number(d, p)


def test_from_paras_keeps_marker_run_apart_from_body(small):
    pid = next(b["id"] for c in small.table_block(BIG_TABLE)["cells"] for b in c["blocks"] if b["type"] == "paragraph" and b["text"].strip())
    small.set_text(pid, "□ 본문 글")
    small.format_chars(pid, 0, 2, {"bold": "toggle", "sizePt": 14})  # 레터 런만 다른 글자 모양(굵게·14pt)
    body_fmt = small._summary(small._ids[pid].get("paraPrIDRef"), SC.body_char(small, small._ids[pid], 2))
    data, items = SC.from_paras(small, [{"para": pid}])
    d = SC.doc(data)
    p = d._ids[SC.para_ids(d)[0]]
    runs = [("".join(d._slot_text(s) for s in d._run_slots(r)), d._char_summary(d._defs["charPr"][r.get("charPrIDRef")])) for r in p.iterchildren(RUN)]
    runs = [(t, s["bold"], s["sizePt"]) for t, s in runs if t]
    assert runs == [("□ ", not body_fmt["bold"], 14.0), ("견본 글입니다", body_fmt["bold"], body_fmt["sizePt"])]  # 레터는 레터 런에 · 본문은 본문 런에
    assert items[0]["format"]["sizePt"] == body_fmt["sizePt"] and items[0]["format"]["bold"] == body_fmt["bold"] and items[0]["unsupported"] == []  # 서식 요약 = 본문 쪽
    small.format_chars(pid, 4, 6, {"italic": True})  # 본문 안에서 모양이 갈림 — 줄 쓰기는 한 모양으로만 쓴다
    assert any("글자 모양이 여러 가지" in x for x in SC.from_paras(small, [{"para": pid}])[1][0]["unsupported"])


def test_from_paras_rejects_bad_picks(small):
    for bad in ([], None, [{"para": "p99999"}], [{"para": BIG_TABLE}], [{}], ["p10"]):
        with pytest.raises(ValueError):
            SC.from_paras(small, bad)


def test_from_paras_leaves_only_the_marker(small):
    """글 서식의 견본 문단에는 레터만 남는다 — 본문 글도, 각주·필드·숨은 설명·책갈피·겹친 글자·덧말·글 조각 안의 낯선 요소도 싣지 않는다(astra 10 — from_paras 도 같은 눈으로)."""
    pid = next(b["id"] for c in small.table_block(BIG_TABLE)["cells"] for b in c["blocks"] if b["type"] == "paragraph" and b["text"].strip())
    small.set_text(pid, "□ 홍길동 910101-1234567 비밀글")
    small.format_chars(pid, 0, 2, {"bold": "toggle"})  # 레터 런 · 본문 런이 갈린 문단
    _hide(small, pid, **SECRETS)
    data, items = SC.from_paras(small, [{"para": pid, "name": "네모"}, {"para": pid}])
    raw = _raw(data)
    assert not [s for s in (*SECRETS.values(), "홍길동", "910101", "비밀글") if s in raw]
    d = _ok(data)
    ps = list(d._sections[0].iterchildren(P))[1:]  # 견본 문단들(첫 문단 뒤)
    assert [d._text(p) for p in ps] == ["□ 견본 글입니다"] * 2 == [i["sample"] for i in items] and [i["name"] for i in items] == ["네모", "□ 2"]
    assert all(ch.tag == T and len(ch) == 0 for p in ps for r in p.iterchildren(RUN) for ch in r) and all(ch.tag == RUN for p in ps for ch in p)  # 런에는 글 조각만, 글 조각에는 글만
    assert [len([r for r in p.iterchildren(RUN) if d._text(p) and "".join(d._slot_text(s) for s in d._run_slots(r))]) for p in ps] == [2, 2]  # 레터 런 · 본문 런은 그대로
    kept = _raw(SC.from_paras(small, [{"para": pid}], keep_text=True)[0])
    assert "홍길동" in kept and SECRETS["foot"] in kept  # keep_text 는 원문째(딸린 내용도) — 사람이 고른 것


# ---- 명세에서 -------------------------------------------------------------------------------------------------------

LINE = {"type": "SOLID", "widthMm": 0.4, "color": "#000000"}
THIN = {"type": "DOT", "widthMm": 0.13, "color": "#7f7f7f"}


def _spec():
    def cell(r, c, text, zone):
        look = {"head": ("#D9E2F3", True, "center"), "stub": ("#F2F2F2", False, "center"), "body": (None, False, "right"), "foot": ("#FFF2CC", True, "right")}[zone]
        return {"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": text, "fill": look[0], "valign": "bottom" if zone == "foot" else "center",
                "marginsMm": {"l": 2.0, "r": 2.0, "t": 0.7, "b": 0.7},
                "edges": {"t": LINE if r == 0 else THIN, "b": LINE if r == 3 else THIN, "l": LINE if c == 0 else None, "r": {"type": "WAVE", "widthMm": 0.36, "color": "red"}},
                "format": {"font": "맑은 고딕", "sizePt": 9, "bold": look[1], "align": look[2], "lineSpacingPct": 130, "color": "#112233", "halfSpace": True, "sizePtX": 1, "ratioPct": 500}}
    rows = [["구분", "1차", "2차"], ["인건비", "100", "1,200"], ["재료비", "50", "-"], ["합계", "150", "2,000"]]
    cells = [cell(r, c, t, "head" if r == 0 else "foot" if r == 3 else "stub" if c == 0 else "body") for r, row in enumerate(rows) for c, t in enumerate(row)]
    return {"rows": 4, "cols": 3, "bands": {"headerRows": 1, "headerCols": 1, "footRows": 1}, "widthsMm": [40, 50, 60], "cells": cells}


def test_from_table_spec_look_reads_back():
    data, info = SC.from_table_spec(_spec())
    d = _ok(data)
    assert [b["type"] for b in d.blocks()] == ["paragraph", "table"] and len(_tops(d)) == 2
    tid = SC.table_id(d)
    tb = d.table_block(tid)
    at = {(c["row"], c["col"]): c for c in tb["cells"]}
    assert (info["rows"], info["cols"], info["bands"]) == (4, 3, {"headerRows": 1, "headerCols": 1, "footRows": 1}) and info["losses"] == [SC.SPEC_NOTE] and "맑은 고딕" in info["fonts"]
    assert [[at[r, c]["text"] for c in range(3)] for r in range(4)] == [["구분", "1차", "2차"], ["인건비", "0", "0"], ["재료비", "0", "0"], ["합계", "0", "0"]]  # 머리 띠만 글 그대로
    assert [at[r, c]["fill"] for r, c in ((0, 0), (1, 0), (1, 1), (3, 2))] == ["#D9E2F3", "#F2F2F2", None, "#FFF2CC"]
    assert at[3, 1]["valign"] == "bottom" and at[1, 1]["valign"] == "center" and at[1, 1]["marginsMm"] == {"l": 2.0, "r": 2.0, "t": 0.7, "b": 0.7}
    assert [at[0, c]["widthMm"] for c in range(3)] == [40.0, 50.0, 60.0]
    for rc, bold, align in (((0, 1), True, "center"), ((1, 0), False, "center"), ((1, 2), False, "right"), ((3, 1), True, "right")):
        s = d.get_cell_format(at[rc]["id"])["text"]["summary"]
        assert (s["font"], s["sizePt"], s["bold"], s["align"], s["lineSpacingPct"], s["color"], s["ratioPct"]) == ("맑은 고딕", 9.0, bold, align, 130, "#112233", 100), rc  # 범위 밖 값(장평 500)은 버림
    edge = tb["borderFills"][at[0, 0]["bf"]]
    assert edge["t"] == {"type": "SOLID", "widthMm": 0.4, "color": "#000000"} and edge["l"] == edge["t"] and edge["b"] == {"type": "DOT", "widthMm": 0.12, "color": "#7F7F7F"}  # 굵기는 OWPML 값으로
    assert edge["r"] == {"type": "SOLID", "widthMm": 0.4, "color": "#000000"}  # 모르는 선 종류 → 실선 · 0.36 → 0.4 · 색 꼴이 틀리면 검정
    assert tb["borderFills"][at[1, 1]["bf"]]["l"] is None and tb["borderFills"][at[3, 1]["bf"]]["b"]["widthMm"] == 0.4
    looks = info["preview"]["looks"]
    assert looks["head"] == {"fill": "#D9E2F3", "font": "맑은 고딕", "sizePt": 9.0, "bold": True, "align": "center"} and looks["foot"]["fill"] == "#FFF2CC" and looks["stub"]["fill"] == "#F2F2F2"
    kept = SC.doc(SC.from_table_spec(_spec(), keep_text=True)[0])
    assert [c["text"] for c in kept.table_block(SC.table_id(kept))["cells"]][3:6] == ["인건비", "100", "1,200"]


def test_from_table_spec_merges_holes_overlaps_and_wide_tables():
    spec = _spec()
    spec["cells"] = [c for c in spec["cells"] if (c["row"], c["col"]) not in ((0, 2), (2, 1))]  # (0,2) 는 (0,1) 이 합친 칸으로 덮고, (2,1) 은 구멍
    spec["cells"][1] = {**spec["cells"][1], "colSpan": 2}
    spec["cells"].append({**spec["cells"][0], "row": 1, "col": 1, "text": "겹침"})  # 이미 있는 자리
    spec["cells"].append({**spec["cells"][0], "row": 9, "col": 0})  # 표 밖
    spec["widthsMm"] = [100, 100, 100]
    data, info = SC.from_table_spec(spec)
    d = _ok(data)
    tb = d.table_block(SC.table_id(d))
    at = {(c["row"], c["col"]): c for c in tb["cells"]}
    assert at[0, 1]["colSpan"] == 2 and at[0, 1]["fill"] == "#D9E2F3" and at[2, 1]["text"] == "" and at[2, 1]["fill"] is None and at[1, 1]["text"] == "0"
    assert any("버린 칸 2개" in x and "메운 자리 1곳" in x for x in info["losses"]) and any("표 폭 300mm" in x for x in info["losses"])
    assert abs(sum(at[1, c]["widthMm"] for c in range(3)) - 170.0) < 0.1 and abs(at[1, 0]["widthMm"] - at[1, 2]["widthMm"]) < 0.1  # 바탕 쪽 폭에 맞춤(비율 그대로)
    for bad in (None, {}, {"rows": 2, "cols": 2, "cells": []}, {"rows": "x", "cols": 2, "cells": [{"row": 0, "col": 0}]}, {"rows": 999, "cols": 2, "cells": [{"row": 0, "col": 0}]},
                {"rows": 1, "cols": 1, "cells": [{"col": 0}]}):
        with pytest.raises(ValueError):
            SC.from_table_spec(bad)


def test_spec_of_block_from_docx_and_hwpx(small):
    dx = DocxDoc(DOCX.read_bytes())
    block = next(b for b in dx.blocks() if b["type"] == "table")
    spec = SC.spec_of_block(block)
    assert (spec["rows"], spec["cols"]) == (block["nRows"], block["nCols"]) and len(spec["widthsMm"]) == spec["cols"] and len(spec["cells"]) == len(block["cells"])
    c0 = spec["cells"][0]
    assert set(c0) == {"row", "col", "rowSpan", "colSpan", "text", "fill", "valign", "marginsMm", "edges", "format"} and set(c0["edges"]) == {"t", "r", "b", "l"}
    assert c0["fill"] == block["cells"][0]["fill"] and c0["format"]["font"] and "wordBreak" not in c0["format"] and spec["bands"] == M.roles_of(block["cells"], block["nRows"], block["nCols"])
    data, info = SC.from_table_spec(spec)  # docx 표 → 명세 → 운반 문서(충실도 summary)
    d = _ok(data)
    tb = d.table_block(SC.table_id(d))
    assert (tb["nRows"], tb["nCols"]) == (block["nRows"], block["nCols"]) and sorted((c["row"], c["col"], c["rowSpan"], c["colSpan"]) for c in tb["cells"]) == \
        sorted((c["row"], c["col"], c["rowSpan"], c["colSpan"]) for c in block["cells"])
    assert [c["fill"] for c in tb["cells"]] == [c["fill"] for c in sorted(block["cells"], key=lambda c: (c["row"], c["col"]))]
    head = next(c for c in tb["cells"] if c["row"] == 0)
    assert d.get_cell_format(head["id"])["text"]["summary"]["font"] == c0["format"]["font"] and head["text"] == c0["text"] and info["bands"] == spec["bands"]
    hs = SC.spec_of_block(small.table_block(BIG_TABLE))
    assert hs["rows"] == 18 and hs["cols"] == 11 and len(hs["widthsMm"]) == 11 and abs(sum(hs["widthsMm"]) - 169.33) < 0.5
    assert hs["cells"][0]["edges"]["t"] == {"type": "SOLID", "widthMm": 0.4, "color": "#000000"} and hs["cells"][0]["format"]["bold"] is True
    assert SC._col_widths([{"col": 0, "colSpan": 2, "widthMm": 30.0}, {"col": 0, "colSpan": 1, "widthMm": 10.0}], 2) == [10.0, 20.0]  # 합친 칸에서 남은 열
    assert SC._col_widths([{"col": 0, "colSpan": 2, "widthMm": 30.0}], 2) is None


def test_from_text_spec():
    spec = [{"name": "큰 제목", "level": 1, "marker": {"mode": "literal", "literal": "□", "lead": "", "gap": " ", "family": "square"}, "sample": "□ 원본의 글",
             "format": {"font": "맑은 고딕", "sizePt": 14, "bold": True, "align": "center", "lineSpacingPct": 180}},
            {"level": None, "marker": {"mode": "literal", "literal": " ", "lead": "x"}, "format": {"sizePt": 11, "indentLeftMm": 5, "spaceAfterPt": 6, "align": "가운데"}},
            {"name": "번호", "marker": {"mode": "auto"}}]
    data, items = SC.from_text_spec(spec)
    d = _ok(data)
    ids = SC.para_ids(d)
    assert len(ids) == 3 == len(items) and not _tables(d.blocks()) and all(p.get("pageBreak") == "0" for p in _tops(d))
    assert [i["sample"] for i in items] == ["□ 견본 글입니다", "견본 글입니다", "견본 글입니다"] == [d._text(d._ids[i]) for i in ids]  # 원본 글(sample)은 싣지 않는다
    assert [(i["key"], i["name"], i["level"], i["marker"]["mode"]) for i in items] == [("i1", "큰 제목", 1, "literal"), ("i2", "문단 2", None, "none"), ("i3", "번호", None, "auto")]
    f1, f2 = (d.get_format(i)["summary"] for i in ids[:2])
    assert (f1["font"], f1["sizePt"], f1["bold"], f1["align"], f1["lineSpacingPct"]) == ("맑은 고딕", 14.0, True, "center", 180) and items[0]["format"] == f1
    assert (f2["sizePt"], f2["indentLeftMm"], f2["spaceAfterPt"], f2["align"], f2["bold"]) == (11.0, 5.0, 6.0, "left", False)  # 틀린 값(정렬 「가운데」)은 버리고 바탕 모양
    assert items[2]["unsupported"] == [SC.AUTO_NOTE] and items[0]["origin"] == {"template": None, "slot": None, "para": None}
    assert SC.from_text_spec(spec[:1], keep_text=True)[1][0]["sample"] == "□ 원본의 글"
    for bad in (None, [], ["글"]):
        with pytest.raises(ValueError):
            SC.from_text_spec(bad)


# ---- 보기 · 도구 ----------------------------------------------------------------------------------------------------

def test_view_of_table_and_text_carriers(small, big):
    data, info = SC.from_table(small, BIG_TABLE, None)
    v = SC.view(data, {"kind": "table", "bands": {"headerRows": 1, "headerCols": 1, "footRows": 0}})
    assert v["table"] == "t2" and len(v["grid"]["rows"]) == 18 and (v["grid"]["headerRows"], v["grid"]["headerCols"], v["grid"]["footRows"]) == (1, 1, 0)  # 띠 수는 meta 것
    assert v["grid"]["rows"][5]["cells"][0]["text"] == "기술개발의\n필요성" and v["spec"]["rows"] == 18 and v["spec"]["bands"] == {"headerRows": 1, "headerCols": 1, "footRows": 0}
    data2, items = SC.from_paras(big, [{"para": _para(big, "□ ")}])
    v2 = SC.view(data2, {"kind": "text", "items": items})
    pos = v2.pop("pos")[items[0]["key"]]  # 항목마다 견본 문단에서 잰 자리(spec_서식복사 ② §13 「내용 서식의 견본」) — items 는 meta 것 그대로
    assert v2 == {"paras": ["p2"], "items": items}
    f = items[0]["format"]
    assert abs(pos["line1Mm"] - (f["indentLeftMm"] + max(f["firstLineMm"], 0))) < .02 and abs(pos["line2Mm"] - (f["indentLeftMm"] + max(-f["firstLineMm"], 0))) < .02
    assert pos["prefixMm"] > pos["leadMm"] >= 0 and abs(pos["textMm"] - pos["line1Mm"] - pos["prefixMm"]) < .02 and pos["letter"]["sizePt"] > 0  # 글 시작 = 앞 여백 + 레터 자리 폭(「□ 」)
    plain, auto = SC.place(SC.doc(data2), SC.doc(data2)._ids["p2"], {"mode": "none"}), SC.place(SC.doc(data2), SC.doc(data2)._ids["p2"], {"mode": "auto"})
    assert plain["prefixMm"] == 0 and plain["textMm"] == plain["line1Mm"] and plain["letter"] is None and auto is None  # 글자 레터가 없으면 글 시작 = 앞 여백 · 자동 번호는 못 잰다
    with pytest.raises(ValueError):
        SC.view(SC.base()[:100], {"kind": "table"})
    with pytest.raises(ValueError):
        SC.view(data2, {"kind": "table"})  # 표가 없는 운반 문서


def test_view_of_cover_carrier_asks_the_cover_module(monkeypatch):
    """표지 서식의 보기(spec_서식복사 ② §14·§16) = `style_cover.view(carrier, meta)` 그대로 — 그 모듈이 아직 없으면 meta 의 값(page · parts), 보기를 못 지으면 ValueError(끝점의 viewError 길)."""
    import sys
    import types

    import app
    page = {"widthMm": 210.0, "heightMm": 297.0, "marginsMm": {"l": 20.0, "r": 20.0, "t": 20.0, "b": 20.0}}
    meta = {"kind": "cover", "page": page, "parts": [{"key": "p1", "type": "text", "role": "title", "sample": "제목", "format": {"sizePt": 22.0}}, {"key": "p2", "type": "table", "rows": 2, "cols": 2}, "junk"]}
    monkeypatch.delattr(app, "style_cover", raising=False)
    monkeypatch.setitem(sys.modules, "app.style_cover", None)                 # 모듈 없음 — meta 의 값 그대로(표 부분의 spec 은 없다)
    assert SC.view(SC.base(), meta) == {"page": page, "parts": meta["parts"][:2]}
    assert SC.view(SC.base(), {"kind": "cover", "page": "A4"}) == {"page": None, "parts": []}
    with pytest.raises(ValueError):
        SC.view(SC.base()[:100], meta)                                        # 운반 문서가 깨졌으면 모듈이 없어도 ValueError
    seen = []
    fake = types.ModuleType("app.style_cover")

    def view(carrier, m):
        seen.append((carrier, m["kind"]))
        return {"page": m["page"], "parts": [{"type": "text", "key": "p1", "role": "title", "sample": "제목", "format": {"sizePt": 22.0}, "gapBeforeMm": 0.0}, {"type": "table", "key": "p2", "spec": {"rows": 2, "cols": 2}}]}
    fake.view = view
    monkeypatch.setitem(sys.modules, "app.style_cover", fake)
    monkeypatch.setattr(app, "style_cover", fake, raising=False)
    v = SC.view(b"cover-carrier", meta)                                       # 운반 문서는 표지 모듈이 연다(여기서 열지 않는다)
    assert v["parts"][1] == {"type": "table", "key": "p2", "spec": {"rows": 2, "cols": 2}} and v["parts"][0]["gapBeforeMm"] == 0.0 and seen == [(b"cover-carrier", "cover")]
    fake.view = lambda carrier, m: 1 / 0
    with pytest.raises(ValueError, match="표지 서식의 보기"):
        SC.view(b"cover-carrier", meta)

    def bad(carrier, m):
        raise ValueError("운반 문서를 열 수 없습니다")
    fake.view = bad
    with pytest.raises(ValueError, match="열 수 없습니다"):
        SC.view(b"x", meta)


def test_put_text_writes_marker_and_body_into_their_runs(small):
    pid = next(b["id"] for c in small.table_block(BIG_TABLE)["cells"] for b in c["blocks"] if b["type"] == "paragraph" and b["text"].strip())
    small.set_text(pid, "1. 처음 글")
    small.format_chars(pid, 0, 3, {"bold": "toggle"})
    p = small._ids[pid]
    texts = lambda: [t for r in p.iterchildren(RUN) if (t := "".join(small._slot_text(s) for s in small._run_slots(r)))]  # noqa: E731
    assert texts() == ["1. ", "처음 글"]
    assert SC.put_text(small, p, "2. ", "둘째 글\n줄 바꿈", 3) is True and texts() == ["2. ", "둘째 글 줄 바꿈"]
    assert SC.put_text(small, p, "", "레터 없이", 3) is False and texts() == ["레터 없이"]  # 레터가 없으면 통째로 첫 글 조각에
    small.set_text(pid, "가. 글")
    assert SC.put_text(small, p, "나. ", "경계가 안 맞음", 2) is False and small._text(p) == "나. 경계가 안 맞음"
    before = copy.deepcopy(p)
    assert SC.put_text(small, p, "나. ", "경계가 안 맞음", 2) is False and [dict(r.attrib) for r in p] == [dict(r.attrib) for r in before]
