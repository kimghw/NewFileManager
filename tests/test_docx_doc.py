import re
import struct
import zlib
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import docx
import pytest
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn

from app.docx_doc import DocxDoc

SAMPLE = (Path(__file__).parent.parent / "samples" / "기술수요조사서.docx").read_bytes()
# Real report with heading styles, multi-level numbering, SEQ captions and 30 pictures - read in place, never copied.
HAZID = Path("E:/dev/docx_form/KR-HSE-HAZD-RPT-052 Rev.0 HAZID Report (K) - Youngchang_Ocean Cleaning Vessel.docx")
needs_hazid = pytest.mark.skipif(not HAZID.exists(), reason="external HAZID sample not available")


@pytest.fixture(scope="module")
def hazid():
    d = DocxDoc(HAZID.read_bytes())
    return d, list(walk(d.blocks()))


def walk(blocks):
    for b in blocks:
        yield b
        for c in b.get("cells", []):
            yield from walk(c["blocks"])


def reopen(data):
    docx.Document(BytesIO(data))  # python-docx must be able to open every output
    return DocxDoc(data)


def members(data):
    z = ZipFile(BytesIO(data))
    return {n: z.read(n) for n in z.namelist()}


def build(fill):
    doc = docx.Document()
    fill(doc)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def png(w, h):
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def assert_refs_resolve(data):
    """No dangling r:id, and every style / numId the body uses is defined."""
    m = members(data)
    body = m["word/document.xml"].decode()
    rels = set(re.findall(r'Id="([^"]+)"', m["word/_rels/document.xml.rels"].decode()))
    assert set(re.findall(r'r:(?:id|embed|link)="([^"]+)"', body)) <= rels
    styles = set(re.findall(r'w:styleId="([^"]+)"', m["word/styles.xml"].decode()))
    assert set(re.findall(r'<w:(?:pStyle|rStyle|tblStyle) w:val="([^"]+)"', body)) <= styles
    nums = set(re.findall(r'<w:num w:numId="(\d+)"', m.get("word/numbering.xml", b"").decode()))
    assert set(re.findall(r'<w:numId w:val="(\d+)"', body)) - {"0"} <= nums


def without_numbering(data):
    """The sample minus numbering.xml (part, relationship and content type)."""
    zin, out = ZipFile(BytesIO(data)), BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as z:
        for info in zin.infolist():
            if info.filename != "word/numbering.xml":
                z.writestr(info, re.sub(rb"<(Relationship|Override)[^>]*numbering[^>]*/>", b"", zin.read(info)))
    return out.getvalue()


def test_untouched_save_returns_original_bytes():
    d = DocxDoc(SAMPLE)
    d.blocks()
    assert d.save() is SAMPLE


def test_set_text_paragraph_and_cell_keeps_formatting():
    d = DocxDoc(SAMPLE)
    blocks = d.blocks()
    title, table = blocks[1], blocks[3]
    value = next(c for c in table["cells"] if c["row"] == 4 and c["col"] == 1)  # empty 「기술수요 과제명」 value cell
    d.set_text(title["id"], "필요 기술 수요조사서 (수정)")
    d.set_text(value["id"], "과제 A\n세부\t내용")
    assert d.blocks()[1]["id"] == title["id"]  # ids survive edits
    out = d.save()

    before, after = members(SAMPLE), members(out)
    assert [n for n in before if before[n] != after[n]] == ["word/document.xml"]
    blocks = reopen(out).blocks()
    assert blocks[1]["text"] == "필요 기술 수요조사서 (수정)" and blocks[1]["bold"]
    cell = next(c for c in blocks[3]["cells"] if c["row"] == 4 and c["col"] == 1)
    assert cell["text"] == "과제 A\n세부\t내용"
    paras = docx.Document(BytesIO(out)).tables[0].cell(4, 1).paragraphs
    assert [r.font.size.pt for p in paras for r in p.runs if r.text] == [10, 10]  # value cell's 10pt run style

    two_runs = build(lambda doc: (p := doc.add_paragraph(), setattr(p.add_run("Hello "), "bold", True),
                                  setattr(p.add_run("World"), "italic", True)))
    d = DocxDoc(two_runs)
    d.set_text(d.blocks()[0]["id"], "Hello big World")
    runs = docx.Document(BytesIO(d.save())).paragraphs[0].runs
    assert [(r.text, r.bold, r.italic) for r in runs] == [("Hello big ", True, None), ("World", None, True)]


def test_insert_heading_and_paragraph():
    data = build(lambda doc: (doc.add_paragraph("본문"), doc.add_paragraph("항목", style="List Number")))
    d = DocxDoc(data)
    body, item = d.blocks()
    assert item["list"] == {"kind": "number", "level": 1, "label": "1."}
    ids = d.insert_after(item["id"], [
        {"kind": "heading", "text": "새 제목", "templateId": item["id"], "keepNumbering": False},
        {"kind": "paragraph", "text": "번호 유지", "templateId": item["id"]},
        {"kind": "paragraph", "text": "기본 본문", "templateId": None}])
    out = d.save()
    assert '<w:numPr><w:numId w:val="0"/></w:numPr>' in members(out)["word/document.xml"].decode()
    blocks = reopen(out).blocks()
    assert [b["text"] for b in blocks] == ["본문", "항목", "새 제목", "번호 유지", "기본 본문"]
    assert blocks[2]["list"] is None and blocks[2]["style"] == "List Number"
    assert blocks[3]["list"]["label"] == "2." and blocks[4]["list"] is None
    assert [b["id"] for b in d.blocks()[2:]] == ids


def test_merged_cells_report_spans():
    def fill(doc):
        t = doc.add_table(rows=3, cols=3)
        t.cell(0, 0).merge(t.cell(0, 1))
        t.cell(1, 2).merge(t.cell(2, 2))
        t.cell(1, 2).text = "세로"
    cells = DocxDoc(build(fill)).blocks()[0]["cells"]
    spans = {(c["row"], c["col"]): (c["rowSpan"], c["colSpan"]) for c in cells}
    assert spans == {(0, 0): (1, 2), (0, 2): (1, 1), (1, 0): (1, 1), (1, 1): (1, 1), (1, 2): (2, 1),
                     (2, 0): (1, 1), (2, 1): (1, 1)}
    assert next(c for c in cells if c["row"] == 1 and c["col"] == 2)["text"] == "세로"


def test_append_rows():
    def fill(doc):
        t = doc.add_table(rows=2, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "이름", "값"
    d = DocxDoc(build(fill))
    table = d.blocks()[0]
    new = d.append_rows(table["id"], [["a", "1"], ["b"]])
    table = reopen(d.save()).blocks()[0]
    assert len(new) == 4 and table["nRows"] == 4
    assert [c["text"] for c in table["cells"][4:]] == ["a", "1", "b", ""]

    def merged_last_row(doc):
        t = doc.add_table(rows=2, cols=2)
        t.cell(0, 1).merge(t.cell(1, 1))
    d = DocxDoc(build(merged_last_row))
    with pytest.raises(ValueError):
        d.append_rows(d.blocks()[0]["id"], [["x", "y"]])


def test_insert_rows_copies_set_and_grows_label():  # spec_표_분류 §5 끼우기, S2·S7
    def fill(doc):
        t = doc.add_table(rows=5, cols=3)
        rows = [["공동기관", "A대학", "김"], ["", "010-1", ""], ["", "B연구원", "이"], ["", "010-2", ""], ["끝", "x", "y"]]
        for r, row in enumerate(rows):
            for k, v in enumerate(row):
                t.cell(r, k).text = v
        t.cell(0, 0).merge(t.cell(3, 0))  # label over both sets
        t.cell(0, 2).merge(t.cell(1, 2))  # 책임자 over each 2-row set
        t.cell(2, 2).merge(t.cell(3, 2))
    d = DocxDoc(build(fill))
    t = d.blocks()[0]
    at = {(c["row"], c["col"]): c["id"] for c in t["cells"]}
    with pytest.raises(ValueError):  # 김 (rows 0-1) would be cut
        d.insert_rows(t["id"], 1, 2, [{}])
    out = d.insert_rows(t["id"], 2, 3, [{at[2, 1]: "C연구소", at[3, 1]: "010-3", at[2, 2]: "박"}])
    assert set(out[0]) == {at[2, 1], at[2, 2], at[3, 1]}
    t = reopen(d.save()).blocks()[0]
    cells = {(c["row"], c["col"]): (c["text"].strip(), c["rowSpan"]) for c in t["cells"]}  # merge() keeps empty paras
    assert t["nRows"] == 7 and cells[0, 0] == ("공동기관", 6)
    assert (cells[4, 1], cells[5, 1], cells[4, 2]) == (("C연구소", 1), ("010-3", 1), ("박", 2))
    assert cells[6, 0] == ("끝", 1)

    def one_row(doc):  # S2: the label sits in the copied row itself -> grow it into a vertical merge
        t = doc.add_table(rows=2, cols=2)
        for r, row in enumerate([["공동기관", "A대학"], ["끝", "x"]]):
            for k, v in enumerate(row):
                t.cell(r, k).text = v
    d = DocxDoc(build(one_row))
    t = d.blocks()[0]
    at = {(c["row"], c["col"]): c["id"] for c in t["cells"]}
    out = d.insert_rows(t["id"], 0, 0, [{at[0, 1]: "B연구원"}, {at[0, 1]: "C대학"}], grow=[at[0, 0]])
    assert [set(o) for o in out] == [{at[0, 1]}] * 2
    cells = {(c["row"], c["col"]): (c["text"], c["rowSpan"]) for c in reopen(d.save()).blocks()[0]["cells"]}
    assert cells == {(0, 0): ("공동기관", 3), (0, 1): ("A대학", 1), (1, 1): ("B연구원", 1), (2, 1): ("C대학", 1),
                     (3, 0): ("끝", 1), (3, 1): ("x", 1)}


@needs_hazid
def test_outline_levels_and_numbering_labels(hazid):
    _, blocks = hazid
    by_text = {b["text"]: b for b in blocks if b["type"] == "paragraph"}
    assert by_text["서론"]["outlineLevel"] == 1 and by_text["서론"]["list"]["label"] == "1."
    assert by_text["약어"]["outlineLevel"] == 2 and by_text["약어"]["list"]["label"] == "2.1."
    assert by_text["약어"]["style"] == "heading 2"


@needs_hazid
def test_image_blocks_and_caption_numbers(hazid):
    d, blocks = hazid
    images = [b for b in blocks if b["type"] == "image"]
    assert len(images) == 30 and all(b["media"].startswith("word/media/") and b["widthMm"] > 0 for b in images)
    assert d.media(images[0]["media"]).startswith(b"\x89PNG")
    captions = [b["text"] for b in blocks if b.get("autoNum") == "figure"]
    assert captions[:3] == ["[그림 3-1] Overall Schematic Diagram of HAZID Study Procedure",
                            "[그림 4-1] General Arrangement of Ocean Cleaning Vessel",
                            "[그림 5-1] System Node of G/T 100 Class Hybrid Ocean Cleaning Vessel"]


@needs_hazid
def test_copy_table_and_paragraph_from_other_styles(hazid):
    src, blocks = hazid
    table = next(b for b in blocks if b["type"] == "table" and b["nRows"] > 3)
    para = next(b for b in blocks if b["type"] == "paragraph" and b["style"] == "04_내용_참조목록_L1")
    d = DocxDoc(without_numbering(SAMPLE))
    ids = d.insert_after(d.blocks()[2]["id"], [{"kind": "copy", "srcId": para["id"]},
                                               {"kind": "copy", "srcId": table["id"]}], src=src)
    out = d.save()
    assert_refs_resolve(out)
    m = members(out)
    assert "04_내용_참조목록_L1".encode() in m["word/styles.xml"] and "word/numbering.xml" in m
    assert b"numbering.xml" in m["word/_rels/document.xml.rels"] and b"/word/numbering.xml" in m["[Content_Types].xml"]
    blocks = reopen(out).blocks()
    assert blocks[3]["text"] == para["text"] and blocks[3]["list"]["label"] == "[1]"
    assert blocks[4]["type"] == "table" and blocks[4]["nRows"] == table["nRows"]
    assert len(ids) == 2


@needs_hazid
def test_copy_image_carries_media(hazid):
    src, blocks = hazid
    image = next(b for b in blocks if b["type"] == "image")
    d = DocxDoc(SAMPLE)
    first = d.blocks()[0]["id"]
    new = d.insert_after(first, [{"kind": "copy", "srcId": image["id"]}] * 2, src=src)
    out = d.save()
    assert_refs_resolve(out)
    m = members(out)
    media = [n for n in m if n.startswith("word/media/")]
    assert media == ["word/media/image1.png"]  # identical bytes are stored once
    assert m["word/media/image1.png"] == src.media(image["media"])
    assert b'Extension="png"' in m["[Content_Types].xml"]
    copied = [b for b in reopen(out).blocks() if b["type"] == "image"]
    assert len(copied) == 2 and copied[0]["widthMm"] == image["widthMm"] and new[0].startswith("i")


def test_insert_image():
    d = DocxDoc(SAMPLE)
    data = png(2000, 1000)
    image_id = d.insert_image(d.blocks()[2]["id"], data, "png")
    out = d.save()
    assert_refs_resolve(out)
    e = reopen(out)
    image = next(b for b in e.blocks() if b["type"] == "image")
    assert e.media(image["media"]) == data
    assert image["widthMm"] == pytest.approx(175.9, abs=0.1)  # page width minus margins
    assert image["heightMm"] == pytest.approx(image["widthMm"] / 2, abs=0.1)
    assert d.insert_image(image_id, data, "png", width_mm=50) != image_id


def test_insert_image_creates_missing_document_relationships():
    raw, out = build(lambda doc: doc.add_paragraph("본문")), BytesIO()
    with ZipFile(BytesIO(raw)) as zin, ZipFile(out, "w", ZIP_DEFLATED) as z:
        for info in zin.infolist():
            if info.filename != "word/_rels/document.xml.rels":
                z.writestr(info, zin.read(info))
    d = DocxDoc(out.getvalue())
    data = png(200, 100)
    d.insert_image(d.blocks()[0]["id"], data, "png", width_mm=20)
    saved = d.save()
    assert_refs_resolve(saved)
    e = reopen(saved)
    image = next(b for b in e.blocks() if b["type"] == "image")
    assert e.media(image["media"]) == data
    assert image["widthMm"] == 20


def test_seq_field_slot_kept_or_replaced():
    def fill(doc):
        for tail, field in ((". 첫째", '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                                      '<w:r><w:instrText xml:space="preserve"> SEQ 그림 \\* ARABIC </w:instrText></w:r>'
                                      '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>7</w:t></w:r>'
                                      '<w:r><w:fldChar w:fldCharType="end"/></w:r>'),
                            (". 둘째", '<w:fldSimple w:instr=" SEQ Figure "><w:r><w:t>9</w:t></w:r></w:fldSimple>')):
            p = doc.add_paragraph("그림 ")
            for el in parse_xml(f"<x {nsdecls('w')}>{field}</x>"):
                p._p.append(el)
            p.add_run(tail)
    d = DocxDoc(build(fill))
    first, second = d.blocks()
    assert (first["text"], first["autoNum"], second["text"]) == ("그림 1. 첫째", "figure", "그림 2. 둘째")
    d.set_text(first["id"], "그림 1. 첫째 수정")  # number unchanged -> field kept
    d.set_text(second["id"], "그림 5. 둘째")  # number changed -> literal text
    out = d.save()
    body = members(out)["word/document.xml"].decode()
    assert "SEQ 그림" in body and "fldSimple" not in body and "<w:t>7</w:t>" not in body  # stale cache refreshed
    first, second = reopen(out).blocks()
    assert (first["text"], first["autoNum"]) == ("그림 1. 첫째 수정", "figure")
    assert (second["text"], second["autoNum"]) == ("그림 5. 둘째", None)

def test_mixed_run_formats_become_runs():
    """A paragraph whose runs differ in character look carries runs (spec_서식 §1); one look -> None."""
    d = DocxDoc(SAMPLE)
    title = d.blocks()[1]
    assert title["runs"] is None
    p = d._ids[title["id"]]
    lead = parse_xml(f'<w:r {nsdecls("w")}><w:rPr><w:i/></w:rPr><w:t>■</w:t></w:r>')
    first = p.find(qn("w:r"))
    first.addprevious(lead)
    runs = d.blocks()[1]["runs"]
    assert [(r["text"], r["format"]["italic"]) for r in runs] == [("■", True), (title["text"], False)]


def test_char_summary_ratio_and_spacing():
    """w:w (장평 %) and w:spacing (twips -> % of font size) are in the character summary (spec_서식 §1)."""
    d = DocxDoc(SAMPLE)
    title = d.blocks()[1]
    assert (title["format"]["ratioPct"], title["format"]["spacingPct"]) == (100, 0)
    lead = parse_xml(f'<w:r {nsdecls("w")}><w:rPr><w:w w:val="90"/><w:spacing w:val="-20"/></w:rPr><w:t>■</w:t></w:r>')
    d._ids[title["id"]].find(qn("w:r")).addprevious(lead)
    f = d.blocks()[1]["runs"][0]["format"]
    assert (f["ratioPct"], f["spacingPct"]) == (90, round(-1 / f["sizePt"] * 100, 1))
