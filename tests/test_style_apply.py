"""서식 적용(spec_일반편집 ② §4): 다른 문서에 새 표(구역 서식 · 폭 맞춤) · 빈 표 · 표 서식 입히기 · 글 서식 입히기 · 줄 쓰기(레터 차례) · 가져온 정의 검사."""
import types
from collections import Counter
from pathlib import Path

import pytest

from app import owpml_check as C
from app import style_apply as SA
from app import style_carrier as SC
from app import style_lib as L
from app import table_make as M
from app.hwpx_doc import RUN, HwpxDoc, P

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, RND = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx"
GRID = {"rows": [["구분", "2024", "2025"], ["매출", "1,200", "1,450"], ["비용", "800", "900"], ["합계", "2,000", "2,350"]], "headerRows": 1, "headerCols": 0, "footRows": 1}
KEYS = ("font", "sizePt", "bold", "italic", "align", "lineSpacingPct", "indentLeftMm", "firstLineMm")


@pytest.fixture(scope="module")
def big():
    """연구개발계획서 양식(읽기만 — 서식의 원본)."""
    d = HwpxDoc(RND.read_bytes())
    d.blocks()
    return d


@pytest.fixture(scope="module")
def table_style(big):
    """연구개발계획서의 표(머리 1행 · 합계 1행) → 운반 문서 바이트 + info."""
    tb = next(b for b in big.blocks() if b["type"] == "table" and b["nRows"] >= 4 and b["nCols"] >= 3 and not M.block_nested(b)
              and M.roles_of(b["cells"], b["nRows"], b["nCols"]) == {"headerRows": 1, "headerCols": 0, "footRows": 1})
    return SC.from_table(big, tb["id"], None)


@pytest.fixture(scope="module")
def text_style(big):
    """연구개발계획서의 문단 넷(1. · 1-1. · □ · o) + 레터 없는 문단 → 운반 문서 바이트 + items."""
    para = lambda start: next(b["id"] for b in big.blocks() if b["type"] == "paragraph" and b["text"].startswith(start))  # noqa: E731
    return SC.from_paras(big, [{"para": para("1. "), "level": 1}, {"para": para("  1-1. "), "level": 2}, {"para": para("□ "), "level": 3}, {"para": para("  o "), "level": 4},
                               {"para": para("\t(페이지"), "level": None}])


def _target():
    d = HwpxDoc(SMALL.read_bytes())
    d.blocks()
    return d


def _style(carrier, bands, meta=None):
    src = SC.doc(carrier)
    return {"src": src, "table": SC.table_id(src), "bands": bands, "meta": meta}


def _tstyle(carrier, items):
    src = SC.doc(carrier)
    return {"src": src, "paras": SC.para_ids(src), "items": items, "meta": None}


def _verdict(doc, hosts, src=None):
    """편집 뒤 지역 검사(server._hosts_check 와 같은 것) — 기준선 = 작은 문서 원본 + 운반 문서의 위반 종류(SA.allow)."""
    base = C.counts(C.check_doc(HwpxDoc(SMALL.read_bytes())))
    base = {"schema": Counter(base["schema"]), "rules": base["rules"]}
    SA.allow(base, src)
    return C.verdict(doc, base, C.check_hosts(doc, hosts, header=True), local=True)


def _cover(block, r, c):
    return next(x for x in block["cells"] if x["row"] <= r < x["row"] + x["rowSpan"] and x["col"] <= c < x["col"] + x["colSpan"])


def _look(doc, cell):
    f = doc.get_cell_format(cell["id"])
    return {"fill": f["fill"], "valign": f["valign"], "marginsMm": f["marginsMm"], **{k: f["text"]["summary"][k] for k in KEYS}}


def _tables(blocks):
    return [b for b in blocks if b["type"] == "table"]


def _drop_def(carrier, kind, i):
    """운반 문서 바이트에서 header 정의 하나(kind 의 id i)를 지운 것 — 그 정의를 가리키는 참조가 끊어진다."""
    d = SC.doc(carrier)
    el = d._defs[kind].pop(i)
    lst = el.getparent()
    lst.remove(el)
    lst.set("itemCnt", str(len(lst)))
    d._touch(lst)
    return d.save()


# ---- 서식 고르기 · 넣을 자리 -------------------------------------------------------------------------------------------

def test_style_of_and_text_style_refs(table_style, text_style):
    tgt = _target()
    b = SA.style_of(tgt, "builtin")
    assert isinstance(b["src"], HwpxDoc) and b["bands"] == {"headerRows": 0, "headerCols": 0, "footRows": 0} and b["meta"] is None and b["src"].table_block(b["table"])["nRows"] == 2
    own = SA.style_of(tgt, "doc:t8")
    assert own == {"src": None, "table": "t8", "bands": {"headerRows": 0, "headerCols": 1, "footRows": 0}, "meta": None}
    for missing in ("doc:t9999", "doc:p10", "0" * 12, "nope", None):
        with pytest.raises(KeyError):
            SA.style_of(tgt, missing)
    info = table_style[1]
    tm = L.create({"kind": "table", "name": "성과지표 표", "rows": info["rows"], "cols": info["cols"], "bands": info["bands"]}, table_style[0])
    xm = L.create({"kind": "text", "name": "본문 글", "items": text_style[1]}, text_style[0])
    st = SA.style_of(tgt, tm["id"])
    assert st["meta"]["id"] == tm["id"] and st["bands"] == info["bands"] and st["src"].table_block(st["table"])["nRows"] == info["rows"]
    ts = SA.text_style(xm["id"])
    assert len(ts["paras"]) == len(ts["items"]) == 5 and ts["meta"]["id"] == xm["id"] and ts["src"]._text(ts["src"]._ids[ts["paras"][0]]) == "1. 견본 글입니다"
    with pytest.raises(ValueError):
        SA.style_of(tgt, xm["id"])  # 글 서식을 표 서식 자리에
    with pytest.raises(ValueError):
        SA.text_style(tm["id"])
    with pytest.raises(KeyError):
        SA.text_style("f" * 12)


def test_top_level_accepts_only_body_blocks(big):
    tgt = _target()
    t8 = tgt.table_block("t8")
    assert SA.top_level(tgt, "t8") is tgt._ids["t8"] and SA.top_level(tgt, "t1") is tgt._ids["t1"]
    cell_para = next(b["id"] for b in t8["cells"][0]["blocks"])
    for bad in (cell_para, t8["cells"][0]["id"], "p99999", None, 7):
        with pytest.raises(ValueError, match="본문 최상위 블록만"):
            SA.top_level(tgt, bad)
    nested = next(b for b in big.blocks() if b["type"] == "table" and M.block_nested(b))
    inner = next(x["id"] for c in nested["cells"] for x in c["blocks"] if x["type"] in ("table", "image"))
    with pytest.raises(ValueError, match="본문 최상위 블록만"):
        SA.top_level(big, inner)
    top = next(b["id"] for b in big.blocks() if b["type"] == "paragraph" and b["text"].strip())
    assert SA.top_level(big, top) is big._ids[top] and not big._dirty


# ---- 새 표 ----------------------------------------------------------------------------------------------------------

def test_table_new_in_another_document_takes_zone_formats(table_style):
    carrier, info = table_style
    style, tgt = _style(carrier, info["bands"]), _target()
    n_tables, n_tops = len(_tables(tgt.blocks())), sum(1 for _ in tgt._sections[0].iterchildren(P))
    r = SA.table_new(tgt, style, M.normalize(GRID), "t8")
    assert (r["rows"], r["cols"]) == (4, 3) and set(r) == {"table", "host", "rows", "cols"}
    host = tgt._ids[r["host"]]
    assert host.getprevious() is tgt._host(tgt._ids["t8"]) and (host.get("pageBreak"), host.get("columnBreak")) == ("0", "0")
    assert len(_tables(tgt.blocks())) == n_tables + 1 and sum(1 for _ in tgt._sections[0].iterchildren(P)) == n_tops + 1  # 임시로 넣었다 지운 양식 표가 없다
    assert not style["src"]._dirty  # 운반 문서는 안 바뀐다
    nb, tpl = tgt.table_block(r["table"]), style["src"].table_block(style["table"])
    at = {(c["row"], c["col"]): c for c in nb["cells"]}
    assert [[at[y, x]["text"] for x in range(3)] for y in range(4)] == GRID["rows"]
    last = tpl["nRows"] - 1
    for (y, x), (ty, tx) in {(0, 0): (0, 0), (0, 2): (0, tpl["nCols"] - 1), (1, 1): (1, 1), (3, 0): (last, 0), (3, 2): (last, tpl["nCols"] - 1)}.items():
        assert _look(tgt, at[y, x]) == _look(style["src"], _cover(tpl, ty, tx)), (y, x)  # 머리 ↔ 머리 · 몸 ↔ 몸 · 합계 ↔ 합계: 음영·세로 정렬·칸 여백·글 모양
    assert at[0, 0]["fill"] == info["preview"]["looks"]["head"]["fill"] and at[3, 1]["fill"] == info["preview"]["looks"]["foot"]["fill"]
    tw = sum(c["widthMm"] for c in tpl["cells"] if c["row"] == 0)
    assert abs(sum(at[0, x]["widthMm"] for x in range(3)) - tw) < 0.1  # 쪽 폭 안이면 양식 폭 그대로
    assert _verdict(tgt, [host], style["src"])["status"] != "fail"
    d2 = HwpxDoc(tgt.save())
    assert len(_tables(d2.blocks())) == n_tables + 1 and not C.check_doc(d2)["rules"]  # 저장·다시 열기 · 끊어진 참조 없음
    with pytest.raises(ValueError):
        SA.table_new(tgt, style, M.normalize(GRID), next(b["id"] for b in at[0, 0]["blocks"]))  # 칸 안에는 안 넣는다


def test_table_new_fits_the_body_width_when_narrow(table_style):
    tgt = _target()
    margin = next(tgt._sections[0].iter("{*}pagePr")).find("{*}margin")
    margin.attrib.update({"left": "17008", "right": "17008"})  # 좌우 여백 60mm — 글 폭 90mm
    avail = round(tgt._body_width_mm(tgt._host(tgt._ids["t8"])) * 7200 / 25.4)
    assert 25000 < avail < 26000
    width = lambda d, tid: sum(int(tc.find("{*}cellSz").get("width")) for tc in next(d._ids[tid].iterchildren("{*}tr")))  # noqa: E731
    style = _style(table_style[0], table_style[1]["bands"])
    assert width(style["src"], style["table"]) > avail
    r = SA.table_new(tgt, style, M.normalize(GRID), "t8")
    assert width(tgt, r["table"]) == avail == int(tgt._ids[r["table"]].find("{*}sz").get("width"))  # 다른 문서의 양식 — 그 구역의 글 폭까지만
    same = M.normalize({**M.block_grid(style["src"].table_block(style["table"])), **table_style[1]["bands"]})
    r2 = SA.table_new(tgt, style, same, "t8")
    ws, tws = ([int(tc.find("{*}cellSz").get("width")) for tc in next(d._ids[t].iterchildren("{*}tr"))] for d, t in ((tgt, r2["table"]), (style["src"], style["table"])))
    assert sum(ws) == avail and all(abs(a / avail - b / sum(tws)) < 0.01 for a, b in zip(ws, tws))  # 열 폭 비율은 양식 그대로
    r3 = SA.table_new(tgt, SA.style_of(tgt, "builtin"), M.normalize(GRID), "t8")
    r4 = SA.table_new(tgt, SA.style_of(tgt, "doc:t8"), M.normalize(GRID), "t8")
    assert width(tgt, r3["table"]) == avail == width(tgt, r4["table"])  # 기본 표 · 이 문서의 표도 본문에 맞춘다
    old = tgt.table_make("t8", "t8", M.normalize(GRID), {"headerRows": 0, "headerCols": 1, "footRows": 0})  # 기존 호출(src 없음)은 전과 같이 양식 폭 그대로
    assert width(tgt, old["table"]) == width(tgt, "t8") > avail


def test_table_new_keeps_document_valid_for_builtin_and_bad_template(table_style):
    tgt = _target()
    st = SA.style_of(tgt, "builtin")
    r = SA.table_new(tgt, st, M.normalize(GRID), "t1")
    nb = tgt.table_block(r["table"])
    assert {c["fill"] for c in nb["cells"]} == {None} and nb["borderFills"][nb["cells"][0]["bf"]]["t"] == {"type": "SOLID", "widthMm": 0.12, "color": "#000000"}
    assert _verdict(tgt, [tgt._ids[r["host"]]], st["src"])["status"] != "fail"
    with pytest.raises(ValueError):
        SA.table_new(tgt, {**st, "table": "t999"}, M.normalize(GRID), "t1")  # 운반 문서에 그 표가 없음
    with pytest.raises(ValueError):
        tgt.table_make("t1", "t2", M.normalize(GRID), None, src=object())  # src 가 문서가 아님


# ---- 빈 표 · 서식 입히기 ----------------------------------------------------------------------------------------------

def test_table_blank_inserts_template_and_blanks_inputs(table_style):
    carrier, info = table_style
    tgt, style = _target(), _style(carrier, info["bands"])
    tpl = style["src"].table_block(style["table"])
    r = SA.table_blank(tgt, style, "t8")
    nb = tgt.table_block(r["table"])
    assert (r["rows"], r["cols"]) == (tpl["nRows"], tpl["nCols"]) and tgt._ids[r["host"]].getprevious() is tgt._host(tgt._ids["t8"])
    key = lambda c: (c["row"], c["col"], c["rowSpan"], c["colSpan"])  # noqa: E731
    was = {key(c): c for c in tpl["cells"]}
    assert sorted(was) == sorted(map(key, nb["cells"]))
    labels = SC.kept_labels(tpl, info["bands"])
    assert labels == {tuple(rc) for rc in info["labels"]} and labels  # 운반 문서에 글이 남은 라벨 칸 = 만들 때 남긴 칸
    for c in nb["cells"]:
        label = (c["row"], c["col"]) in labels
        assert c["text"] == (was[key(c)]["text"] if label else ""), key(c)  # 라벨 칸(머리 표시가 있는 머리행 · 합계 라벨)은 글 그대로, 나머지는 빈 칸
        assert (c["fill"], c["valign"], c["marginsMm"], c["widthMm"]) == (was[key(c)]["fill"], was[key(c)]["valign"], was[key(c)]["marginsMm"], was[key(c)]["widthMm"])
    assert any(c["text"] for c in nb["cells"]) and any(was[key(c)]["text"] and not c["text"] for c in nb["cells"])
    r2 = SA.table_blank(tgt, style, "t8")
    assert tgt._ids[r2["table"]].get("id") != tgt._ids[r["table"]].get("id") != style["src"]._ids[style["table"]].get("id")  # 개체 id 는 넣을 때마다 새로
    assert _verdict(tgt, [tgt._ids[r["host"]], tgt._ids[r2["host"]]], style["src"])["status"] != "fail" and not C.check_doc(HwpxDoc(tgt.save()))["rules"]
    # blueprint 가 있으면 그 역할대로 — input·computed 만 비우고 label·note 는 남긴다
    cells = sorted(tpl["cells"], key=lambda c: (c["row"], c["col"]))
    bp = {"cells": [{"row": c["row"], "col": c["col"], "rowSpan": c["rowSpan"], "colSpan": c["colSpan"], "role": "note" if n == len(cells) - 1 else "input" if n == 0 else "label", "label": None}
                    for n, c in enumerate(cells)], "formulas": []}
    tgt3 = _target()
    got = tgt3.table_block(SA.table_blank(tgt3, {**style, "meta": {"blueprint": bp}}, "t8")["table"])
    texts = [c["text"] for c in sorted(got["cells"], key=lambda c: (c["row"], c["col"]))]
    assert texts[0] == "" and texts[1:] == [c["text"] for c in cells][1:]
    with pytest.raises(ValueError):
        SA.table_blank(tgt, style, tgt.table_block("t8")["cells"][0]["id"])


def test_table_blank_leaves_no_sample_text_in_an_unmarked_header_band(table_style):
    """astra 10: 표시 없는 표의 첫 행은 라벨이 아니라 견본으로 저장된다 — 빈 표로 넣을 때 그 견본(「가나다」)이 머리 띠라는 까닭으로 남으면 안 된다."""
    src, first, plain = SC.open_base()
    tid = src.table_make(first, plain, M.normalize({"rows": [["홍길동", "910101-1234567"], ["김철수", "920202-2345678"]]}), SC.ZERO)["table"]
    carrier, info = SC.from_table(src, tid, None)
    assert info["bands"]["headerRows"] == 1 and info["labels"] == []
    for meta in (None, {"labels": info["labels"]}):  # meta 에 labels 가 없는 템플릿(파일에서 추출 · 전에 저장한 것)도 같은 결과
        tgt = _target()
        got = tgt.table_block(SA.table_blank(tgt, _style(carrier, info["bands"], meta), "t8")["table"])
        assert [c["text"] for c in got["cells"]] == [""] * 4, meta
    # meta.labels = 운반 문서에 글을 남긴 칸 — 띠 수를 나중에 고쳐도(PUT bands) 그 칸의 글은 남고 다른 칸은 빈다
    carrier, info = table_style
    none, tgt = {"headerRows": 0, "headerCols": 0, "footRows": 0}, _target()
    got = tgt.table_block(SA.table_blank(tgt, _style(carrier, none, {"labels": info["labels"]}), "t8")["table"])
    assert sorted([c["row"], c["col"]] for c in got["cells"] if c["text"]) == info["labels"] != []
    got = tgt.table_block(SA.table_blank(tgt, _style(carrier, none), "t8")["table"])
    assert not any(c["text"] for c in got["cells"])  # labels 도 띠 수도 없으면 다 비운다


def test_table_restyle_keeps_structure_and_text(table_style):
    carrier, info = table_style
    tgt, style = _target(), _style(carrier, info["bands"])
    before = tgt.table_block("t8")
    r = SA.table_restyle(tgt, style, "t8", {"headerRows": 1, "headerCols": 0, "footRows": 1})
    after = tgt.table_block("t8")
    key = lambda c: (c["id"], c["row"], c["col"], c["rowSpan"], c["colSpan"], c["text"], c["widthMm"])  # noqa: E731
    assert sorted(map(key, after["cells"])) == sorted(map(key, before["cells"]))  # 구조·글·칸 크기·칸 id 그대로
    assert r["table"] == "t8" and r["cells"] == len(before["cells"]) and (r["rows"], r["cols"]) == (18, 11) and r["bands"] == {"headerRows": 1, "headerCols": 0, "footRows": 1}
    tpl = style["src"].table_block(style["table"])
    assert {c["fill"] for c in after["cells"]} <= {c["fill"] for c in tpl["cells"]} and r["formatted"] and all(tgt._ids[i].tag == P for i in r["formatted"])
    assert _look(tgt, _cover(after, 0, 0))["fill"] == _look(style["src"], _cover(tpl, 0, 0))["fill"]
    assert _verdict(tgt, [tgt._host(tgt._ids["t8"])], style["src"])["status"] != "fail"
    want = M.roles_of(tgt.table_block("t1")["cells"], 1, 3)
    assert SA.table_restyle(tgt, style, "t1")["bands"] == want  # 띠 수를 안 주면 자동 판정(입히기 전의 표로)
    with pytest.raises(ValueError):
        SA.table_restyle(tgt, SA.style_of(tgt, "doc:t8"), "t8")  # 같은 표
    with pytest.raises(ValueError):
        SA.table_restyle(tgt, style, "t9999")
    own = SA.table_restyle(tgt, SA.style_of(tgt, "doc:t1"), "t8")  # 이 문서의 다른 표를 양식으로(가져오기 없음)
    assert own["cells"] == len(before["cells"])


# ---- 글 서식 입히기 · 줄 쓰기 ------------------------------------------------------------------------------------------

def test_format_paras_copies_format_and_keeps_text(text_style):
    carrier, items = text_style
    tgt, ts = _target(), _tstyle(carrier, items)
    paras = [b["id"] for c in tgt.table_block("t8")["cells"] for b in c["blocks"] if b["type"] == "paragraph" and b["text"].strip()][:3]
    texts = [tgt._text(tgt._ids[i]) for i in paras]
    changed = SA.format_paras(tgt, ts, "i3", paras)
    assert changed == paras and [tgt._text(tgt._ids[i]) for i in paras] == texts  # 글·레터는 안 바꾼다
    for i in paras:
        got = tgt.get_format(i)["summary"]
        assert {k: got[k] for k in KEYS} == {k: items[2]["format"][k] for k in KEYS}
    assert SA.format_paras(tgt, ts, "i3", paras) == []  # 이미 그 모양 — 바뀐 것 없음
    assert not ts["src"]._dirty and _verdict(tgt, [tgt._host(tgt._ids["t8"])], ts["src"])["status"] != "fail"
    bullet = next(tgt._rev[p] for p in tgt._sections[0].iter(P) if tgt._heading(p) is not None and tgt._heading(p).get("type") == "BULLET" and tgt._text(p).strip())
    SA.format_paras(tgt, ts, "i1", [bullet])
    assert tgt._heading(tgt._ids[bullet]).get("type") == "BULLET" and tgt.get_format(bullet)["summary"]["sizePt"] == items[0]["format"]["sizePt"]  # 제 번호 설정은 지킨다
    SA.format_paras(tgt, ts, "i1", [bullet], keep_numbering=False)
    assert tgt._heading(tgt._ids[bullet]).get("type") == "NONE"
    for key, ids in (("i9", paras), ("i1", ["p99999"]), ("i1", ["t8"])):
        with pytest.raises(ValueError):
            SA.format_paras(tgt, ts, key, ids)


def test_write_lines_numbers_literal_sequences_and_writes_plain_text_otherwise(text_style):
    carrier, items = text_style
    tgt, ts = _target(), _tstyle(carrier, items)
    assert [i["marker"]["literal"] for i in items] == ["1.", "1-1.", "□", "o", ""] and [i["marker"]["family"] for i in items[:2]] == ["decimal", "hyphen"]
    lines = [{"text": "첫 장", "item": "i1"}, {"text": "첫 절", "item": "i2"}, {"text": "둘째 절", "item": "i2"}, {"text": "네모\n줄", "item": "i3"}, {"text": "동그라미", "item": "i4"},
             {"text": "둘째 장", "item": "i1"}, {"text": "새 장의 첫 절", "item": "i2"}, {"text": "레터 없는 글", "item": "i5"}, {"text": "견본 없는 줄", "item": None}, {"text": "셋째 장", "item": "i1"}]
    ids = SA.write_lines(tgt, "t8", lines, ts)
    assert [tgt._text(tgt._ids[i]) for i in ids] == ["1. 첫 장", "  1-1. 첫 절", "  1-2. 둘째 절", "□ 네모 줄", "  o 동그라미", "2. 둘째 장", "  2-1. 새 장의 첫 절",
                                                    "레터 없는 글", "견본 없는 줄", "3. 셋째 장"]  # 차례 계열은 1부터 · 위 레벨이 나오면 아래는 다시 1 · 기호는 그대로
    assert len(set(ids)) == 10 and all(tgt._ids[i].tag == P for i in ids)
    host = tgt._host(tgt._ids["t8"])
    assert tgt._ids[ids[0]].getprevious() is host and all(tgt._ids[b].getprevious() is tgt._ids[a] for a, b in zip(ids, ids[1:]))  # 넣을 자리 뒤에 차례대로
    assert all((tgt._ids[i].get("pageBreak"), tgt._ids[i].get("columnBreak")) == ("0", "0") for i in ids)
    by = {it["key"]: it for it in items}
    for i, ln in zip(ids, lines):
        if ln["item"]:
            got = tgt.get_format(i)["summary"]
            assert {k: got[k] for k in KEYS} == {k: by[ln["item"]]["format"][k] for k in KEYS}, ln
    assert _verdict(tgt, [tgt._ids[i] for i in ids], ts["src"])["status"] != "fail" and not C.check_doc(HwpxDoc(tgt.save()))["rules"]
    with pytest.raises(ValueError, match="본문 최상위 블록만"):
        SA.write_lines(tgt, tgt.table_block("t8")["cells"][0]["id"], lines, ts)
    for bad in ([], None, ["글"], [{"text": "x", "item": "i9"}]):
        with pytest.raises(ValueError):
            SA.write_lines(tgt, "t8", bad, ts)


def test_write_lines_auto_none_and_plain_shape(big):
    src = _target()
    bullet = next(src._rev[p] for p in src._sections[0].iter(P) if src._heading(p) is not None and src._heading(p).get("type") == "BULLET" and src._text(p).strip())
    carrier, items = SC.from_paras(src, [{"para": bullet}, {"para": next(b["id"] for b in src.table_block("t8")["cells"][0]["blocks"])}])
    assert [i["marker"]["mode"] for i in items] == ["auto", "none"]
    tgt = HwpxDoc(RND.read_bytes())
    anchor = next(b["id"] for b in tgt.blocks() if b["type"] == "paragraph" and b["text"].startswith("1. "))
    want = tgt.get_format(anchor)["summary"]
    ids = SA.write_lines(tgt, anchor, [{"text": "자동 번호 줄", "item": "i1"}, {"text": "레터 없는 줄", "item": "i2"}, {"text": "자리 문단 모양", "item": None}], _tstyle(carrier, items))
    assert [tgt._text(tgt._ids[i]) for i in ids] == ["자동 번호 줄", "레터 없는 줄", "자리 문단 모양"]  # auto·none 은 글만(레터를 글에 쓰지 않는다)
    assert tgt._heading(tgt._ids[ids[0]]).get("type") == "BULLET" and tgt._heading(tgt._ids[ids[0]]).get("idRef") in tgt._defs["bullet"]  # 번호 정의도 가져옴
    assert {k: tgt.get_format(ids[2])["summary"][k] for k in KEYS} == {k: want[k] for k in KEYS}  # 견본 없는 줄 = 넣을 자리 문단 모양
    plain = SA.write_lines(tgt, ids[2], [{"text": "서식 없이 한 줄"}, {"text": "또 한 줄", "item": "i1"}])  # 글 서식 없이 — item 은 무시
    assert [tgt._text(tgt._ids[i]) for i in plain] == ["서식 없이 한 줄", "또 한 줄"] and tgt._ids[plain[0]].getprevious() is tgt._ids[ids[2]]
    table = next(b["id"] for b in tgt.blocks() if b["type"] == "table")
    after_table = SA.write_lines(tgt, table, [{"text": "표 뒤의 줄"}])
    assert tgt._ids[after_table[0]].getprevious() is tgt._host(tgt._ids[table]) and tgt.get_format(after_table[0])["summary"]["font"]


def test_write_lines_keeps_marker_run_shape():
    src = _target()
    pid = next(b["id"] for c in src.table_block("t8")["cells"] for b in c["blocks"] if b["type"] == "paragraph" and b["text"].strip())
    src.set_text(pid, "(1) 본문 글")
    src.format_chars(pid, 0, 4, {"bold": "toggle", "sizePt": 14})  # 레터 런만 다른 글자 모양
    carrier, items = SC.from_paras(src, [{"para": pid, "level": 1}])
    assert items[0]["marker"]["family"] == "paren-num"
    tgt = _target()
    ids = SA.write_lines(tgt, "t8", [{"text": "하나", "item": "i1"}, {"text": "둘", "item": "i1"}], _tstyle(carrier, items))
    for i, (letter, body) in zip(ids, (("(1) ", "하나"), ("(2) ", "둘"))):
        runs = [("".join(tgt._slot_text(s) for s in tgt._run_slots(r)), tgt._char_summary(tgt._defs["charPr"][r.get("charPrIDRef")])) for r in tgt._ids[i].iterchildren(RUN)]
        runs = [(t, s["sizePt"]) for t, s in runs if t]
        assert runs == [(letter, 14.0), (body, items[0]["format"]["sizePt"])]  # 레터는 레터 런 모양 · 본문은 본문 런 모양


# ---- 가져온 정의 검사 · 판정 기준선 --------------------------------------------------------------------------------------

def test_imported_check_raises_on_dangling_numbering_ref(text_style):
    carrier, items = text_style
    bad = SC.doc(carrier)
    p = bad._ids[SC.para_ids(bad)[0]]
    h = bad._heading(p)
    h.attrib.update({"type": "NUMBER", "idRef": "777", "level": "0"})  # 손으로 만든 끊어진 번호 참조 — 운반 문서에 numbering 777 이 없다
    bad._touch(h)
    broken = bad.save()
    assert "777" not in SC.doc(broken)._defs["numbering"]
    tgt = _target()
    para = next(b["id"] for b in tgt.table_block("t8")["cells"][0]["blocks"])
    state = SA.defs_state(tgt)
    assert set(state) == set(tgt._defs) and SA.imported_check(tgt, state) is None  # 더해진 정의가 없으면 통과
    with pytest.raises(ValueError, match="정의 참조가 깨져 있어 적용하지 않았습니다.*idRef=777"):  # 가져오기 전에 운반 문서에서 잡는다(source_check)
        SA.format_paras(tgt, _tstyle(broken, items), "i1", [para], keep_numbering=False)
    assert not tgt._dirty and SA.defs_state(tgt) == state
    with pytest.raises(ValueError, match="정의 참조가 깨져"):
        SA.write_lines(_target(), "t8", [{"text": "줄", "item": "i1"}], _tstyle(broken, items))
    seen = _tstyle(broken, items)
    SA._SRC_BAD[seen["src"]] = []  # 운반 문서 검사를 지난 것으로 쳐도 — 가져온 정의의 끊어진 참조는 뒤에서 또 잡는다(imported_check)
    with pytest.raises(ValueError, match="끊어진 참조"):
        SA.format_paras(_target(), seen, "i1", [para], keep_numbering=False)
    ok = _target()
    assert SA.write_lines(ok, "t8", [{"text": "줄", "item": "i1"}], _tstyle(carrier, items))  # 성한 운반 문서는 통과
    # 손으로 더한 정의 — 없는 테두리/배경을 가리키는 글자 모양
    d = _target()
    before = SA.defs_state(d)
    c = __import__("copy").deepcopy(next(iter(d._defs["charPr"].values())))
    c.set("borderFillIDRef", "9999")
    d._add_def("charPr", c)
    with pytest.raises(ValueError, match="borderFillIDRef=9999"):
        SA.imported_check(d, before)


def test_source_with_dangling_refs_is_refused_before_anything_is_imported(table_style, text_style, monkeypatch):
    """astra 8: 운반 문서의 borderFill 1 을 지우면 그것을 가리키던 참조가 대상 문서의 borderFill 1 에 붙어 `imported_check` 가 통과했다(원본 참조 오류 → 적용 성공 → 대상 참조 오류 0).
    가져오기 전에 **운반 문서에서** 본다 — 끊어진 참조가 하나라도 있으면 적용하지 않는다."""
    carrier, info = table_style
    good = SC.doc(carrier)
    cell_bf = next(tc.get("borderFillIDRef") for tc in good._ids[SC.table_id(good)].iter("{*}tc"))
    assert SC.broken_refs(good) == [] and "1" in _target()._defs["borderFill"]  # 대상 문서에 같은 번호의 정의가 있다 — 말없이 붙을 수 있었다
    norm = M.normalize(GRID)
    for bf in ("1", cell_bf):
        bad = _drop_def(carrier, "borderFill", bf)
        assert any(f"borderFillIDRef={bf}" in m for m in SC.broken_refs(SC.doc(bad)))
        for call in (lambda t, st: SA.table_new(t, st, norm, "t8"), lambda t, st: SA.table_blank(t, st, "t8"), lambda t, st: SA.table_restyle(t, st, "t8")):
            tgt = _target()
            state = SA.defs_state(tgt)
            with pytest.raises(ValueError, match=f"서식 템플릿의 정의 참조가 깨져 있어 적용하지 않았습니다.*borderFillIDRef={bf}"):
                call(tgt, _style(bad, info["bands"]))
            assert not tgt._dirty and SA.defs_state(tgt) == state and tgt.save() == SMALL.read_bytes()  # 아무것도 가져오지 않았다
    tcarrier, items = text_style
    src = SC.doc(tcarrier)
    cid = SC.body_char(src, src._ids[SC.para_ids(src)[2]], 2)  # 「□ 」 뒤 본문 런의 글자 모양
    bad = _drop_def(tcarrier, "charPr", cid)
    para = next(b["id"] for b in _target().table_block("t8")["cells"][0]["blocks"])
    for call in (lambda t, ts: SA.format_paras(t, ts, "i3", [para]), lambda t, ts: SA.write_lines(t, "t8", [{"text": "줄", "item": "i3"}], ts)):
        tgt = _target()
        with pytest.raises(ValueError, match=f"정의 참조가 깨져 있어 적용하지 않았습니다.*charPrIDRef={cid}"):
            call(tgt, _tstyle(bad, items))
        assert not tgt._dirty
    # 판정은 운반 문서(객체)마다 한 번만 센다
    calls, real = [], SC.broken_refs
    monkeypatch.setattr(SC, "broken_refs", lambda *a, **k: calls.append(a) or real(*a, **k))
    tgt, style = _target(), _style(carrier, info["bands"])
    SA.table_new(tgt, style, norm, "t8")
    SA.table_blank(tgt, style, "t8")
    assert len(calls) == 1 and SA.table_new(tgt, SA.style_of(tgt, "doc:t8"), norm, "t8") and len(calls) == 1  # 이 문서의 표(가져오기 없음)는 안 본다
    assert SA.table_new(tgt, SA.style_of(tgt, "builtin"), norm, "t8") and len(calls) == 2  # 기본 표(빈 바탕)도 가져오기 전에 본다


def test_carry_uses_the_given_session_instead_of_scanning_docs(table_style, text_style, monkeypatch):
    """astra(표 「_carry 의 DOCS 역탐색」): 판정 기준선에 더할 세션을 `server.DOCS` 에서 문서 객체로 되찾았다 — LRU 로 밀려난(DOCS 에 없는) 세션은 못 찾아 그 편집의 위반 종류를
    못 더했다. 부르는 쪽이 세션을 넘긴다(`session=`)."""
    from app import server
    calls = []
    monkeypatch.setattr(server, "owpml_allow", lambda s, kinds: calls.append((s, list(kinds))) or [])
    monkeypatch.setattr(server, "DOCS", {})
    carrier, info = table_style
    tgt, style, norm = _target(), _style(carrier, info["bands"]), M.normalize(GRID)
    sess = types.SimpleNamespace(doc=tgt)  # DOCS 에 없는 세션(밀려난 것)
    SA.table_new(tgt, style, norm, "t8")
    assert calls == []  # 세션을 안 줬고 DOCS 에도 없다 — 못 더한다
    SA.table_new(tgt, style, norm, "t8", session=sess)
    assert len(calls) == 1 and calls[0][0] is sess and calls[0][1] == list(SA.carried(style["src"])) != []
    ts = _tstyle(*text_style)
    para = next(b["id"] for b in tgt.table_block("t8")["cells"][0]["blocks"])
    SA.table_blank(tgt, style, "t8", session=sess)
    SA.table_restyle(tgt, style, "t1", session=sess)
    SA.format_paras(tgt, ts, "i3", [para], session=sess)
    SA.write_lines(tgt, "t8", [{"text": "줄", "item": "i3"}], ts, session=sess)
    assert len(calls) == 5 and all(c[0] is sess for c in calls)  # 적용 함수 다섯 모두
    SA.table_new(tgt, SA.style_of(tgt, "doc:t8"), norm, "t8", session=sess)
    SA.write_lines(tgt, "t8", [{"text": "서식 없는 줄"}], session=sess)
    assert len(calls) == 5  # 가져오기가 없으면 더할 것도 없다
    server.DOCS["x"] = sess  # 세션을 안 주면 전처럼 DOCS 에서 찾는다(옛 호출)
    SA.table_new(tgt, style, norm, "t8")
    assert len(calls) == 6 and calls[-1][0] is sess


def test_allow_adds_carried_violation_kinds_to_the_baseline(big, table_style):
    src = SC.doc(table_style[0])
    kinds = SA.carried(src)
    assert kinds and all(isinstance(k, tuple) for k in kinds)
    base = {"schema": Counter(), "rules": Counter()}
    added = SA.allow(base, src)
    assert set(added) == set(kinds) == set(base["schema"]) and SA.allow(base, src) == [] and SA.allow(base, None) == [] and not base["rules"]  # 없는 종류만 · 규칙 위반 기준선은 그대로
    big_kinds, small_kinds = (set(C.counts(C.check_doc(HwpxDoc(p.read_bytes())))["schema"]) for p in (RND, SMALL))
    assert big_kinds - small_kinds and small_kinds - big_kinds  # 두 견본 문서는 한글이 써 둔 위반 종류가 서로 다르다 — 그래서 기준선에 더해야 한다
