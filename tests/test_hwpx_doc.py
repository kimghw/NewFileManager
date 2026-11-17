import io
import zipfile
from functools import cache
from pathlib import Path

import pytest
from lxml import etree
from PIL import Image

from app.hwpx_doc import FONT_LANGS, HH, HP, HwpxDoc
from app.hwpx_format import LANG_FONT_KEYS

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
LARGE = Path("E:/dev/choi/3편_비교프로젝트/3편_선체구조_구조화/3편 국문-25.hwpx")
large = pytest.mark.skipif(not LARGE.exists(), reason="large real sample not on this PC")
REFS = {"charPrIDRef": "charProperties", "paraPrIDRef": "paraProperties", "styleIDRef": "styles",
        "charStyleIDRef": "styles", "borderFillIDRef": "borderFills"}


@cache
def _bytes(path):
    return path.read_bytes()


def _walk(blocks):
    """Every block and cell, depth first."""
    for b in blocks:
        yield b
        for c in b.get("cells", ()):
            yield c
            yield from _walk(c["blocks"])


def _check(data):
    """Valid zip, mimetype first+STORED, XML parses, section refs resolve, counts match -> reloaded doc."""
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    roots = {n: etree.fromstring(z.read(n)) for n in z.namelist() if n.endswith((".xml", ".hpf"))}
    ids = {}
    for lst in roots["Contents/header.xml"].find(f"{{{HH}}}refList"):
        if lst.get("itemCnt") is not None:
            assert int(lst.get("itemCnt")) == len(lst), etree.QName(lst).localname
        ids[etree.QName(lst).localname] = {e.get("id") for e in lst}
    for face in roots["Contents/header.xml"].iter(f"{{{HH}}}fontface"):
        assert int(face.get("fontCnt")) == len(face)
    items = {i.get("id"): i for i in roots["Contents/content.hpf"].iter("{*}item")}
    for name, root in roots.items():
        if name.startswith("Contents/section"):
            for e in root.iter(tag=etree.Element):
                for attr, lst in REFS.items():
                    assert e.get(attr) is None or e.get(attr) in ids[lst], (name, attr, e.get(attr))
                item = items.get(e.get("binaryItemIDRef")) if e.get("binaryItemIDRef") else None
                if item is not None and item.get("isEmbeded") != "0":  # linked images live outside the zip
                    assert item.get("href") in z.namelist()
                assert e.get("binaryItemIDRef") is None or item is not None
    return HwpxDoc(data)


def _members(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return {n: z.read(n) for n in z.namelist()}


def _changed(old, new):
    old, new = _members(old), _members(new)
    return {n for n in new if old.get(n) != new[n]}


def _paras(doc):
    return [b for b in _walk(doc.blocks()) if b.get("type") == "paragraph"]


def _replace_member(data, name, new):
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as out:
        for zi in src.infolist():
            out.writestr(zi, new if zi.filename == name else src.read(zi.filename))
    return buf.getvalue()


def test_untouched_save_returns_original_bytes():
    for path in [SMALL] + ([LARGE] if LARGE.exists() else []):
        d = HwpxDoc(_bytes(path))
        d.blocks()
        assert d.save() == _bytes(path)


def test_set_text_paragraph_keeps_run_formatting():
    d = HwpxDoc(_bytes(SMALL))
    before = _paras(d)
    target = next(b for b in before if b["text"].startswith("[작성가이드라인] 제안 기술의 핵심"))
    d.set_text(target["id"], "[작성가이드라인] 수정된 내용")
    out = d.save()
    after = _paras(_check(out))
    assert [b["text"] for b in after] == [
        "[작성가이드라인] 수정된 내용" if b["id"] == target["id"] else b["text"] for b in before]
    old, new = _members(_bytes(SMALL)), _members(out)
    assert all(old[n] == new[n] for n in old if n != "Contents/section0.xml")
    sec = etree.fromstring(new["Contents/section0.xml"])
    p = next(p for p in sec.iter(f"{{{HP}}}p") if "".join(p.itertext()).startswith("[작성가이드라인] 수정"))
    runs = [(r.get("charPrIDRef"), "".join(r.itertext())) for r in p.iterchildren(f"{{{HP}}}run")]
    assert runs == [("31", "[작성가이드라인] "), ("38", "수정된 내용")]
    assert p.find(f"{{{HP}}}linesegarray") is None


def test_set_text_cell_splits_into_paragraphs():
    d = HwpxDoc(_bytes(SMALL))
    cell = next(c for c in _walk(d.blocks()) if c.get("text") == "기술개발의\n필요성")
    others = {c["id"]: c["text"] for c in _walk(d.blocks()) if "row" in c and c["id"] != cell["id"]}
    d.set_text(cell["id"], "가\n나\n다")
    cells = [c for c in _walk(_check(d.save()).blocks()) if "row" in c]
    new = next(c for c in cells if (c["row"], c["col"]) == (cell["row"], cell["col"]) and c["text"] == "가\n나\n다")
    assert len(new["blocks"]) == 3
    assert sorted(c["text"] for c in cells if c is not new) == sorted(others.values())


def test_append_rows_updates_row_count():
    d = HwpxDoc(_bytes(SMALL))
    t1, t2 = d.blocks()
    ids = d.append_rows(t1["id"], [["a", "b", "c"], ["d"]])
    assert len(ids) == 6
    with pytest.raises(ValueError):  # last row of the big form table is covered by a rowSpan
        d.append_rows(t2["id"], [["x"]])
    t = _check(d.save()).blocks()[0]
    assert t["nRows"] == 3
    assert [(c["row"], c["text"]) for c in t["cells"][3:]] == [(1, "a"), (1, "b"), (1, "c"), (2, "d"), (2, ""), (2, "")]


def test_insert_rows_copies_set_and_grows_label():  # spec_표_분류 §5 끼우기, S2
    d = HwpxDoc(_bytes(SMALL))
    t = d.blocks()[1]
    (row12,) = [c for c in t["cells"] if c["row"] == 12]  # 기술내용 label covers rows 9-12
    with pytest.raises(ValueError):  # 「제안하는 기술의 수준」 rows 13-15 would be cut
        d.insert_rows(t["id"], 13, 13, [{}])
    out = d.insert_rows(t["id"], 12, 12, [{row12["id"]: "새 값"}, {}])
    assert [set(o) for o in out] == [{row12["id"]}] * 2
    t = _check(d.save()).blocks()[1]
    cells = {(c["row"], c["col"]): (c["text"], c["rowSpan"]) for c in t["cells"]}
    assert t["nRows"] == 20 and cells[9, 0] == ("기술내용", 6)
    assert cells[13, 1][0] == "새 값" and cells[14, 1][0] == row12["text"]
    assert cells[15, 0] == ("제안하는 기술의 수준", 3)

    d = HwpxDoc(_bytes(SMALL))  # S2: a label starting in the copied rows grows when asked to
    t = d.blocks()[1]
    label = next(c for c in t["cells"] if c["text"] == "기술수요 과제명")  # rows 3-4
    d.insert_rows(t["id"], 3, 4, [{}], grow=[label["id"]])
    t = _check(d.save()).blocks()[1]
    cells = {(c["row"], c["col"]): (c["text"], c["rowSpan"]) for c in t["cells"]}
    assert t["nRows"] == 20 and cells[3, 0] == ("기술수요 과제명", 4) and (5, 0) not in cells
    assert [cells[r, 1] for r in (5, 6)] == [cells[3, 1], cells[4, 1]]


def test_ids_stable_across_edits():
    d = HwpxDoc(_bytes(SMALL))
    before = {b["id"]: b.get("type") for b in _walk(d.blocks())}
    para = next(b for b in _paras(d) if b["text"] == "기술수요 과제명")
    d.set_text(para["id"], "기술수요 과제명(수정)")
    new_ids = d.insert_after(para["id"], [{"kind": "paragraph", "text": "추가", "templateId": para["id"]}])
    d.append_rows(d.blocks()[0]["id"], [["x"]])
    after = {b["id"]: b.get("type") for b in _walk(d.blocks())}
    assert before.items() <= after.items() and new_ids[0] in after and new_ids[0] not in before


def test_autonum_slot_kept_or_replaced():
    sec = zipfile.ZipFile(SMALL).read("Contents/section0.xml").replace(
        "<hp:t>별첨</hp:t>".encode(),
        ('<hp:t>표 </hp:t><hp:ctrl><hp:autoNum num="1" numType="TABLE"><hp:autoNumFormat type="DIGIT" '
         'userChar="" prefixChar="" suffixChar="" supscript="0"/></hp:autoNum></hp:ctrl><hp:t> 별첨</hp:t>').encode())
    d = HwpxDoc(_replace_member(_bytes(SMALL), "Contents/section0.xml", sec))
    b = next(b for b in _paras(d) if b["autoNum"])
    assert (b["text"], b["autoNum"]) == ("표 1 별첨", "table")
    d.set_text(b["id"], "표 1 별첨 수정")
    d = _check(d.save())
    b = next(b for b in _paras(d) if b["text"].startswith("표 "))
    assert (b["text"], b["autoNum"]) == ("표 1 별첨 수정", "table")
    d.set_text(b["id"], "표 7 별첨")
    b = next(b for b in _paras(_check(d.save())) if b["text"].startswith("표 "))
    assert (b["text"], b["autoNum"]) == ("표 7 별첨", None)


def test_insert_image_into_small_doc():
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "red").save(buf, "PNG")
    png = buf.getvalue()
    d = HwpxDoc(_bytes(SMALL))
    iid = d.insert_image(d.blocks()[1]["id"], png, "png")
    assert d.blocks()[2]["id"] == iid
    d2 = _check(d.save())
    img = d2.blocks()[2]
    assert img["type"] == "image" and d2.media(img["media"]) == png
    assert img["widthMm"] == pytest.approx(200 * 25.4 / 96, abs=0.1)


@large
def test_large_doc_outline_headings_and_images():
    d = HwpxDoc(_bytes(LARGE))
    blocks = list(_walk(d.blocks()))
    assert {1, 2, 3, 4} <= {b["outlineLevel"] for b in blocks if b.get("outlineLevel")}
    imgs = [b for b in blocks if b.get("type") == "image" and b["media"]]
    assert sum(b["widthMm"] > 0 for b in imgs) > 500  # a few real pics are 0x0 (hidden)
    assert d.media(imgs[0]["media"])[:4] == b"\x89PNG"
    ids = {b["id"] for b in blocks}
    caps = [b for b in blocks if b.get("captionOf")]
    assert caps and all(c["captionOf"] in ids for c in caps)


@large
def test_insert_heading_and_paragraph_turns_numbering_off():
    d = HwpxDoc(_bytes(LARGE))
    h = next(b for b in d.blocks() if b.get("outlineLevel") == 3)
    ids = d.insert_after(h["id"], [{"kind": "heading", "text": "새 절", "templateId": h["id"]},
                                   {"kind": "heading", "text": "새 절 2", "templateId": h["id"]},
                                   {"kind": "paragraph", "text": "본문 추가", "templateId": None}])
    p1, p2 = d._ids[ids[0]], d._ids[ids[1]]
    assert p1.get("paraPrIDRef") == p2.get("paraPrIDRef") != d._ids[h["id"]].get("paraPrIDRef")  # deduped clone
    top = _check(d.save()).blocks()
    i = next(i for i, b in enumerate(top) if b.get("text") == "새 절")
    assert [b.get("text") for b in top[i - 1:i + 3]] == [h["text"], "새 절", "새 절 2", "본문 추가"]
    assert top[i]["outlineLevel"] is None and top[i]["style"] == h["style"]


@large
def test_copy_table_and_heading_from_large_into_small():
    src = HwpxDoc(_bytes(LARGE))
    sb = src.blocks()
    head = next(b for b in sb if b.get("outlineLevel") == 2)
    tbl = next(b for b in sb if b["type"] == "table")
    d = HwpxDoc(_bytes(SMALL))
    d.insert_after(d.blocks()[-1]["id"], [{"kind": "copy", "srcId": head["id"]}, {"kind": "copy", "srcId": tbl["id"]}],
                   src=src)
    d2 = _check(d.save())
    blocks = d2.blocks()
    h2 = next(b for b in blocks if b.get("text") == head["text"])
    assert h2["outlineLevel"] == 2 and h2["style"] == head["style"]
    t2 = next(b for b in blocks[blocks.index(h2):] if b["type"] == "table")
    assert [c["text"] for c in t2["cells"]] == [c["text"] for c in tbl["cells"]]


@large
def test_copy_image_block_brings_bindata_and_manifest():
    src = HwpxDoc(_bytes(LARGE))
    img = next(b for b in _walk(src.blocks()) if b.get("type") == "image" and b["media"])
    d = HwpxDoc(_bytes(SMALL))
    ref = d.blocks()[-1]["id"]
    d.insert_after(ref, [{"kind": "copy", "srcId": img["id"]}, {"kind": "copy", "srcId": img["id"]}], src=src)
    out = d.save()
    d2 = _check(out)
    imgs = [b for b in d2.blocks() if b["type"] == "image"]
    assert len(imgs) == 2 and imgs[0]["media"] == imgs[1]["media"]  # identical bytes -> one BinData member
    assert d2.media(imgs[0]["media"]) == src.media(img["media"])
    assert [n for n in _members(out) if n.startswith("BinData/")] == [imgs[0]["media"]]


# ---------------------------------------------------------------- formats (spec §8)
def test_format_summary_and_block_keys():
    d = HwpxDoc(_bytes(SMALL))
    cells = [c for c in _walk(d.blocks()) if "row" in c]
    title = next(b for b in _paras(d) if b["text"] == " 필요 기술 수요조사")
    head = next(c for c in cells if c["text"] == "기술수요 과제명")
    s = d.get_format(title["id"])["summary"]
    assert (s["font"], s["sizePt"], s["bold"], s["lineSpacingPct"]) == ("HY헤드라인M", 15.0, False, 160)
    assert title["format"] == s
    hs = d.get_cell_format(head["id"])
    assert (hs["text"]["summary"]["bold"], hs["text"]["summary"]["align"]) == (True, "center")
    assert (hs["fill"], hs["valign"], hs["marginsMm"]) == ("#DFE6F7", "center", {"l": 1.8, "r": 1.8, "t": 0.5, "b": 0.5})
    assert {k: head[k] for k in ("fill", "valign", "marginsMm")} == {k: hs[k] for k in ("fill", "valign", "marginsMm")}


def test_derive_apply_format_roundtrip_and_dedupe():
    d = HwpxDoc(_bytes(SMALL))
    para = next(b for b in _paras(d) if b["text"] == "기술수요 과제명")
    fmt = d.get_format(para["id"])
    assert d.derive_format(fmt, {"bold": True, "sizePt": None}) == fmt  # nothing new -> nothing added
    assert d.save() == _bytes(SMALL)
    changes = {"font": "테스트글꼴", "sizePt": 14.5, "bold": False, "italic": True, "underline": True,
               "color": "#FF0000", "align": "right", "indentLeftMm": 5.0, "firstLineMm": -3.0,
               "spaceBeforePt": 6.0, "spaceAfterPt": 4.0, "lineSpacingPct": 200}
    n = {k: len(d._defs[k]) for k in ("charPr", "paraPr")}
    f1 = d.derive_format(fmt, changes)
    assert d.derive_format(fmt, changes) == f1  # identical definitions reused
    assert {k: len(d._defs[k]) for k in n} == {k: v + 1 for k, v in n.items()}
    assert f1["summary"] == {**fmt["summary"], **changes, **dict.fromkeys(LANG_FONT_KEYS, "테스트글꼴")}  # 글꼴은 모든 언어에
    d.apply_format([para["id"]], f1)
    out = d.save()
    assert _changed(_bytes(SMALL), out) == {"Contents/header.xml", "Contents/section0.xml"}
    d2 = _check(out)
    p2 = next(b for b in _paras(d2) if b["text"] == "기술수요 과제명")
    assert p2["format"] == d2.get_format(p2["id"])["summary"] == f1["summary"]
    fr = d2._defs["charPr"][f1["token"].split("|c")[1]].find(f"{{{HH}}}fontRef")
    assert {d2._fontface(lang).find(f"{{{HH}}}font[@id='{fr.get(a)}']").get("face")
            for a, lang in FONT_LANGS.items()} == {"테스트글꼴"}


def test_cell_format_roundtrip_keeps_shared_borderfill():
    d = HwpxDoc(_bytes(SMALL))
    cells = [c for c in _walk(d.blocks()) if "row" in c]
    head = next(c for c in cells if c["text"] == "기술수요 과제명")
    cf = d.get_cell_format(head["id"])
    d.apply_cell_format([head["id"]], cf, ["text", "fill", "valign"])  # same values -> untouched
    assert d.save() == _bytes(SMALL)
    bf = d._ids[head["id"]].get("borderFillIDRef")
    twins = [i for i, c in enumerate(cells) if c is not head and d._ids[c["id"]].get("borderFillIDRef") == bf]
    other = next(c for c in cells if c["fill"] and d._ids[c["id"]].get("borderFillIDRef") != bf)
    new = {"text": d.derive_format(cf["text"], {"sizePt": 12}), "fill": "#ffee00", "valign": "bottom",
           "marginsMm": {"l": 3.0, "t": 1.0}}
    d.apply_cell_format([head["id"]], new, ["text", "fill", "valign", "margins"])
    d.apply_cell_format([other["id"]], {"fill": None}, ["fill"])
    cells2 = [c for c in _walk(_check(d.save()).blocks()) if "row" in c]
    h2, o2 = cells2[cells.index(head)], cells2[cells.index(other)]
    assert (h2["fill"], h2["valign"], h2["marginsMm"]) == ("#FFEE00", "bottom", {"l": 3.0, "r": 1.8, "t": 1.0, "b": 0.5})
    assert h2["blocks"][0]["format"]["sizePt"] == 12 and h2["text"] == head["text"]
    assert (o2["fill"], o2["shaded"]) == (None, False)
    assert twins and [cells2[i]["fill"] for i in twins] == [cells[i]["fill"] for i in twins] == [cf["fill"]] * len(twins)


def test_cell_border_lines_per_table():
    d = HwpxDoc(_bytes(SMALL))
    tables = [b for b in _walk(d.blocks()) if b.get("type") == "table"]
    for t in tables:
        assert {c["bf"] for c in t["cells"]} == set(t["borderFills"])
        assert all(set(lines) == {"t", "r", "b", "l"} for lines in t["borderFills"].values())
    assert any(s and s["type"] == "SOLID" for t in tables for lines in t["borderFills"].values() for s in lines.values())
    bf_id = next(c["bf"] for t in tables for c in t["cells"] if c["text"] == "기술수요 과제명")
    bf = d._defs["borderFill"][bf_id]
    bf.find(f"{{{HH}}}topBorder").attrib.update({"type": "DASH", "width": "0.4 mm", "color": "#ff0000"})
    bf.find(f"{{{HH}}}leftBorder").set("type", "NONE")
    lines = d._border_lines(bf_id)
    assert lines["t"] == {"type": "DASH", "widthMm": 0.4, "color": "#FF0000"} and lines["l"] is None
    assert d._border_lines("999999") is None


@large
def test_apply_heading_format_to_another_heading():
    d = HwpxDoc(_bytes(LARGE))
    top = d.blocks()
    h2 = next(b for b in top if b.get("outlineLevel") == 2)
    h3 = next(b for b in top if b.get("outlineLevel") == 3)
    body = next(b for b in top if b.get("type") == "paragraph" and not b["outlineLevel"] and len(b["text"]) > 80)
    assert h2["format"]["bold"] and not body["format"]["bold"] and h2["format"]["sizePt"] > body["format"]["sizePt"]
    d.apply_format([h3["id"]], d.get_format(h2["id"]))
    out = d.save()
    changed = _changed(_bytes(LARGE), out)
    assert changed and all(n.startswith("Contents/section") for n in changed)  # header untouched
    d2 = _check(out)
    b2, b3 = (next(b for b in d2.blocks() if b.get("text") == h["text"]) for h in (h2, h3))
    p2, p3 = d2._ids[b2["id"]], d2._ids[b3["id"]]
    assert p2.get("paraPrIDRef") == p3.get("paraPrIDRef") and d2._char_id(p2) == d2._char_id(p3)
    assert b3["outlineLevel"] == 2 and b3["format"] == b2["format"]


def test_cell_text_format_keeps_numbering():
    d = HwpxDoc(_bytes(SMALL))
    blocks = list(_walk(d.blocks()))
    src = next(c for c in blocks if "row" in c and c["text"] == "기술수요 과제명")  # plain bold header cell
    bullets = [b for b in _paras(d) if b["list"] and b["text"]]  # ◦ paragraphs inside cells
    cell = next(c for c in blocks if "row" in c and any(x["id"] == bullets[0]["id"] for x in c["blocks"]))
    fmt = d.get_cell_format(src["id"])["text"]
    d.apply_cell_format([cell["id"]], {"text": fmt}, ["text"])  # keep_numbering=True for cells
    d.apply_format([bullets[1]["id"]], fmt)  # paragraphs default: the format's own (no) numbering
    after = {b["text"]: b for b in _paras(_check(d.save()))}
    kept, dropped = after[bullets[0]["text"]], after[bullets[1]["text"]]
    assert kept["list"] == bullets[0]["list"] and kept["format"] == fmt["summary"]
    assert dropped["list"] is None and dropped["format"] == fmt["summary"]
    if LARGE.exists():  # outline paragraph in a cell keeps its outline level
        d = HwpxDoc(_bytes(LARGE))
        blocks = list(_walk(d.blocks()))
        cell = next(c for c in blocks if "row" in c and any(x.get("outlineLevel") for x in c["blocks"]))
        body = next(b for b in blocks if b.get("type") == "paragraph" and not b["outlineLevel"] and not b["list"])
        d.apply_cell_format([cell["id"]], {"text": d.get_format(body["id"])}, ["text"])
        cell2 = next(c for c in _walk(_check(d.save()).blocks()) if c.get("text") == cell["text"] and "row" in c)
        assert [b.get("outlineLevel") for b in cell2["blocks"]] == [b.get("outlineLevel") for b in cell["blocks"]]

def test_mixed_run_formats_become_runs():
    """A paragraph whose runs differ in character look carries runs (spec_서식 §1); one look -> None."""
    d = HwpxDoc(_bytes(SMALL))
    title = next(b for b in _paras(d) if b["text"] == " 필요 기술 수요조사")
    assert title["runs"] is None
    bold = next(i for i, c in d._defs["charPr"].items() if c.find(f"{{{HH}}}bold") is not None)
    lead = etree.Element(f"{{{HP}}}run", charPrIDRef=bold)
    etree.SubElement(lead, f"{{{HP}}}t").text = "■"
    p = d._ids[title["id"]]
    p.insert(p.index(next(p.iterchildren(f"{{{HP}}}run"))), lead)
    d._blocks_cache = None   # XML 을 직접 고쳤으니 blocks() 캐시를 비움(고치는 메서드는 _mark 가 함)
    runs = next(b for b in _paras(d) if b["id"] == title["id"])["runs"]
    assert [(r["text"], r["format"]["bold"]) for r in runs] == [("■", True), (" 필요 기술 수요조사", False)]
    assert set(runs[0]["format"]) == {"font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct",
                                      "halfSpace", *LANG_FONT_KEYS}  # + 언어별 글꼴(읽기만 — 웹 글꼴, spec_hwpx_웹편집 ② §3-3)


def test_char_summary_ratio_and_spacing():
    """장평 hh:ratio / 자간 hh:spacing (hangul values, %) are in the character summary (spec_서식 §1)."""
    d = HwpxDoc(_bytes(SMALL))
    looks = {(s["ratioPct"], s["spacingPct"]) for s in map(d._char_summary, d._defs["charPr"].values())}
    assert {(100, 0), (90, 0), (100, -6)} <= looks
    c = next(iter(d._defs["charPr"].values()))  # useFontSpace="0" (글꼴에 어울리는 빈칸 끔) -> 읽기 전용 halfSpace
    assert d._char_summary(c)["halfSpace"] is True
    c.set("useFontSpace", "1")
    assert "halfSpace" not in d._char_summary(c)


@pytest.mark.parametrize("image_text,only_image", [("", False), ("설명", False), ("", True)])
def test_set_text_cell_preserves_image_paragraphs(image_text, only_image):
    d = HwpxDoc(_bytes(SMALL))
    cell = d.blocks()[0]["cells"][0]
    d.set_text(cell["id"], "")
    sub = d._ids[cell["id"]].find(f"{{{HP}}}subList")
    first = sub.find(f"{{{HP}}}p")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, "PNG")
    iid = d.insert_image(d._id(first), buf.getvalue(), "png")
    host = d._host(d._ids[iid])
    if image_text:
        d.set_text(d._id(host), image_text)
    if only_image:
        sub.remove(first)
    d.set_text(cell["id"], "수정")
    after = _check(d.save())
    edited = after.blocks()[0]["cells"][0]
    images = [b for b in edited["blocks"] if b["type"] == "image"]
    assert len(images) == 1
    assert edited["text"] == "수정"
    assert after._text(after._host(after._ids[images[0]["id"]])) == ""
    assert after.media(images[0]["media"]) == buf.getvalue()


def test_cell_text_mapping_skips_image_only_paragraphs():
    d = HwpxDoc(_bytes(SMALL))
    cell = d.blocks()[0]["cells"][0]
    d.set_text(cell["id"], "앞\n뒤")
    sub = d._ids[cell["id"]].find(f"{{{HP}}}subList")
    first, last = sub.findall(f"{{{HP}}}p")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, "PNG")
    iid = d.insert_image(d._id(first), buf.getvalue(), "png")
    assert d.blocks()[0]["cells"][0]["text"] == "앞\n뒤"
    d.set_text(cell["id"], "수정 앞\n수정 뒤")
    assert d._text(last) == "수정 뒤" and last.getparent() is sub
    assert d._text(d._host(d._ids[iid])) == ""


def test_forced_line_break_and_tab_survive_text_edit():
    d = HwpxDoc(_bytes(SMALL))
    para = _paras(d)[0]
    p = d._ids[para["id"]]
    for child in list(p):
        p.remove(child)
    run = etree.SubElement(p, f"{{{HP}}}run", charPrIDRef="0")
    t = etree.SubElement(run, f"{{{HP}}}t")
    t.text = "A"
    etree.SubElement(t, f"{{{HP}}}lineBreak").tail = "B"
    etree.SubElement(t, f"{{{HP}}}tab", width="123", leader="0").tail = "C"
    assert d._text(p) == "A\u2028B\tC"
    d.set_text(para["id"], d._text(p) + "!")
    after = _check(d.save())
    edited = next(b for b in _paras(after) if b["text"] == "A\u2028B\tC!")
    p = after._ids[edited["id"]]
    assert len(p.findall(f".//{{{HP}}}lineBreak")) == 1
    assert p.find(f".//{{{HP}}}tab").attrib == {"width": "123", "leader": "0"}


@pytest.mark.parametrize("part,changed", [("margins", True), ("margins", False), ("fill", True)])
def test_cell_margins_invalidate_only_changed_layout(part, changed):
    d = HwpxDoc(_bytes(SMALL))
    cell = next(c for c in _walk(d.blocks()) if c.get("text") == "기술수요 과제명" and "row" in c)
    para = cell["blocks"][0]
    assert "lines" in para
    fmt = d.get_cell_format(cell["id"])
    if part == "margins" and changed:
        fmt["marginsMm"] = {**fmt["marginsMm"], "l": 15.0, "r": 15.0}
    elif part == "fill":
        fmt["fill"] = "#112233"
    d.apply_cell_format([cell["id"]], fmt, [part])
    edited = next(b for b in _paras(_check(d.save())) if b["text"] == para["text"])
    assert ("lines" not in edited) == (part == "margins" and changed)


def test_inline_objects_in_one_paragraph_share_a_row():
    # 한 문단에 글자처럼 취급 그림이 둘 이상이면 한글은 한 줄에 나란히 — 블록에 같은 inlineRow(첫 그림 id), 하나뿐이거나
    # 글자처럼 취급이 아니면 없음(웹 쪽 보기가 세로로 쌓아 쪽이 밀리던 것, 2026-10-28)
    import copy
    d = HwpxDoc(_bytes(SMALL))
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "PNG")
    iid = d.insert_image(d.blocks()[1]["id"], buf.getvalue(), "png")
    def images():
        d._blocks_cache = None   # XML 을 직접 고치는 시험 — blocks() 캐시를 비움(고치는 메서드는 _mark 가 함)
        return [b for b in _walk(d.blocks()) if b.get("type") == "image"]
    assert all("inlineRow" not in b for b in images())
    pic = d._ids[iid]
    twin = copy.deepcopy(pic)
    pic.addnext(twin)
    assert [b.get("inlineRow") for b in images()] == [iid, iid]
    twin.find(f"{{{HP}}}pos").set("treatAsChar", "0")
    assert all("inlineRow" not in b for b in images())


def test_inline_picture_in_a_text_paragraph_rides_in_the_text():
    # 글이 있는 문단에 글자처럼 취급으로 놓인 그림(글머리 아이콘 「▶ 제목」 — <run><pic/><t> 제목</t></run>): 한글은 글과 같은 줄의 그 자리에 놓는다.
    # 문단 블록에 pics [{id, at(그 그림 앞까지의 글자 수), …}] · 그 그림 블록에 inlineOf(문단 id) — 블록 목록·차례는 그대로이고 그 그림은 inlineRow 를 안 받는다
    # (웹이 그림을 글 아래 줄에 따로 그려 1줄 표가 2줄 높이가 되던 것 — 2026-11-17 사용자, spec_hwpx_웹편집 ② §3-6)
    import copy
    d = HwpxDoc(_bytes(SMALL))
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "PNG")
    iid = d.insert_image(d.blocks()[1]["id"], buf.getvalue(), "png")
    pic = d._ids[iid]
    run = pic.getparent()

    def read():
        d._blocks_cache = None   # XML 을 직접 고치는 시험 — blocks() 캐시를 비움
        bl = d.blocks()
        k = next(i for i, b in enumerate(bl) if b["id"] == iid)
        return bl[k - 1], bl[k]

    assert "inlineOf" not in read()[1]                      # 글 없는 문단의 그림 — 전처럼 따로(문단 블록이 없다)
    for t in run.findall(f"{{{HP}}}t"):
        run.remove(t)
    tail = etree.SubElement(run, f"{{{HP}}}t")
    tail.text = " 제목"
    para, img = read()
    assert para["type"] == "paragraph" and para["text"] == " 제목"
    assert para["pics"] == [{"id": iid, "at": 0, "media": img["media"], "widthMm": img["widthMm"], "heightMm": img["heightMm"]}]
    assert img["type"] == "image" and img["inlineOf"] == para["id"] and "inlineRow" not in img
    head = etree.Element(f"{{{HP}}}t")
    head.text = "앞글"
    pic.addprevious(head)                                   # 글 사이의 그림 — 그 그림 앞까지의 글자 수
    para, img = read()
    assert para["text"] == "앞글 제목" and [x["at"] for x in para["pics"]] == [2]
    d.set_text(para["id"], "앞글 새 제목")                    # 글을 고쳐도 그림은 그 자리(글만 고친다)
    para, img = read()
    assert para["text"] == "앞글 새 제목" and [x["at"] for x in para["pics"]] == [2] and img["inlineOf"] == para["id"]
    twin = copy.deepcopy(pic)
    pic.addnext(twin)                                       # 글 속 그림 둘 — 둘 다 글 속에(나란히 묶음 inlineRow 가 아니다)
    d._blocks_cache = None
    imgs = [b for b in d.blocks() if b["type"] == "image"]
    assert [b.get("inlineOf") for b in imgs] == [para["id"]] * 2 and all("inlineRow" not in b for b in imgs)
    assert [x["at"] for x in next(b for b in d.blocks() if b["id"] == para["id"])["pics"]] == [2, 2]
    run.remove(twin)
    pic.find(f"{{{HP}}}pos").set("treatAsChar", "0")        # 글자처럼 취급이 아닌 그림(떠 있는 그림) — 글 속 그림이 아니다
    para, img = read()
    assert "pics" not in para and "inlineOf" not in img
    out = _check(d.save())                                   # 저장본도 멀쩡
    assert any(b["type"] == "image" for b in out.blocks())


def test_copy_keeps_objects_of_one_paragraph_together():
    # 한 문단에 나란히 놓인 그림은 다른 문서로 복사해도 한 문단 — 그림마다 문단으로 풀려 두 줄이 되던 것(2026-11-12 사용자, spec_병합 ② §5 「한 문단의 표·그림」).
    # insert_after 의 계약은 그대로: items 와 같은 차례·같은 수의 id.
    def png(color):
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), color).save(buf, "PNG")
        return buf.getvalue()
    src = HwpxDoc(_bytes(SMALL))
    ids = [src.insert_image(src.blocks()[1]["id"], png(c), "png") for c in ("red", "green", "blue")]
    a, b, c = (src._ids[i] for i in ids)
    for x, y in ((a, b), (b, c)):   # 그림 셋을 한 문단·한 런에(한글이 저장한 꼴 <run><pic/><pic/><t/></run>), 빈 문단은 지움
        old = src._host(y)
        x.addnext(y)
        old.getparent().remove(old)
    gap = etree.Element(f"{{{HP}}}t")
    gap.text = "  "
    a.addnext(gap)   # 첫 그림과 둘째 그림 사이 빈칸
    src._blocks_cache = None
    host = src._host(a)

    def put(sids):
        to = HwpxDoc(_bytes(SMALL))
        new = to.insert_after(to.blocks()[-1]["id"], [{"kind": "copy", "srcId": s} for s in sids], src=src)
        assert len(new) == len(sids)
        return to, new, [to._host(to._ids[i]) for i in new]

    to, new, hosts = put(ids)
    assert len(set(hosts)) == 1 and to._text(hosts[0]) == "  "   # 한 문단 · 그림 사이 빈칸도 함께(글 없는 문단은 따로 복사되지 않는다)
    out = _check(to.save())
    imgs = [x for x in out.blocks() if x["type"] == "image"][-3:]
    assert len({x["inlineRow"] for x in imgs}) == 1   # 화면도 한 줄로 묶는다
    assert [out.media(x["media"]) for x in imgs] == [png("red"), png("green"), png("blue")]   # 차례 그대로
    assert len(set(put([ids[0], ids[2]])[2])) == 1          # 사이 그림을 건너뛰어도 한 문단
    assert len(set(put([ids[1], ids[0]])[2])) == 2          # 문서 순이 아니면 따로(차례를 바꾸지 않는다)
    assert len(set(put([ids[0], ids[0]])[2])) == 2          # 같은 그림 되풀이 = 그림마다 문단
    assert len(set(put([ids[2]])[2])) == 1
    host.findall(f"{{{HP}}}run")[-1].findall(f"{{{HP}}}t")[-1].text = "설명"   # 글이 있는 문단 = 문단이 제 블록 — 글은 문단 사본에만
    src._blocks_cache = None
    to, new, hosts = put([src._id(host), *ids])
    assert to._text(hosts[0]) == "  설명" and not to._ids[new[0]].findall(f".//{{{HP}}}pic")
    assert hosts[1] is not hosts[0] and len(set(hosts[1:])) == 1 and to._text(hosts[1]) == ""
    assert len([x for x in _check(to.save()).blocks() if x["type"] == "image"][-3:]) == 3


def test_blocks_cached_until_edit():
    """blocks() 는 고치기 전까지 같은 열(캐시) — 고치는 메서드(_mark)가 비우면 다시 읽어 바뀐 글이 보인다(spec_구분_초기화 ② §4)."""
    d = HwpxDoc(_bytes(SMALL))
    a = d.blocks()
    assert d.blocks() is a
    target = next(b for b in _paras(d) if b["text"].startswith("[작성가이드라인] 제안 기술의 핵심"))
    assert d.blocks() is a   # _paras 도 blocks() 를 거침 — 읽기만으로는 그대로
    d.set_text(target["id"], "[작성가이드라인] 캐시 뒤 수정")
    b = d.blocks()
    assert b is not a and next(x for x in _paras(d) if x["id"] == target["id"])["text"] == "[작성가이드라인] 캐시 뒤 수정"
    assert d.blocks() is b
