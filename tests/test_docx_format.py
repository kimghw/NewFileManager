"""DocxDoc formats (spec §8): summaries, derive/apply, cell formats."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import docx
import pytest

from app.docx_doc import DocxDoc

SAMPLE = (Path(__file__).parent.parent / "samples" / "기술수요조사서.docx").read_bytes()
# Real report with heading styles and several sections - read in place, never copied.
HAZID = Path("E:/dev/docx_form/KR-HSE-HAZD-RPT-052 Rev.0 HAZID Report (K) - Youngchang_Ocean Cleaning Vessel.docx")
needs_hazid = pytest.mark.skipif(not HAZID.exists(), reason="external HAZID sample not available")


@pytest.fixture(scope="module")
def hazid():
    return HAZID.read_bytes()


def walk(blocks):
    for b in blocks:
        yield b
        for c in b.get("cells", []):
            yield from walk(c["blocks"])


def reopen(data):
    docx.Document(BytesIO(data))  # python-docx must be able to open every output
    return list(walk(DocxDoc(data).blocks()))


def first(blocks, **kw):
    return next(b for b in blocks if all(b.get(k) == v for k, v in kw.items()))


@needs_hazid
def test_heading_and_body_summaries(hazid):
    d = DocxDoc(hazid)
    blocks = list(walk(d.blocks()))
    h1, body = first(blocks, style="heading 1"), first(blocks, style="03_내용_단락_L1")
    assert d.get_format(h1["id"])["summary"] == h1["format"]
    assert {"font": "맑은 고딕", "sizePt": 16.0, "bold": True, "color": "#025B95", "align": "left"}.items() \
        <= h1["format"].items()
    assert {"sizePt": 10.0, "bold": False, "italic": False, "align": "justify", "lineSpacingPct": 115,
            "spaceAfterPt": 9.0}.items() <= body["format"].items()


def test_derive_apply_survives_save():
    d = DocxDoc(SAMPLE)
    p = first(walk(d.blocks()), type="paragraph")
    changes = {"font": "굴림", "sizePt": 14.0, "bold": False, "italic": True, "underline": True, "color": "#C00000",
               "align": "center", "indentLeftMm": 10.0, "firstLineMm": -5.0, "spaceBeforePt": 6.0,
               "spaceAfterPt": 3.0, "lineSpacingPct": 150}
    fmt = d.derive_format(d.get_format(p["id"]), changes)
    assert changes.items() <= fmt["summary"].items()
    with pytest.raises(ValueError):
        d.derive_format(fmt, {"color": "red"})
    d.apply_format([p["id"]], fmt)
    assert changes.items() <= first(reopen(d.save()), text=p["text"])["format"].items()


def test_noop_apply_keeps_original_bytes():
    d = DocxDoc(SAMPLE)
    p = first(walk(d.blocks()), type="paragraph")
    d.apply_format([p["id"]], d.get_format(p["id"]))
    assert d.save() == SAMPLE


@needs_hazid
def test_heading_format_copies_to_other_heading(hazid):
    d = DocxDoc(hazid)
    blocks = list(walk(d.blocks()))
    h1, h2 = first(blocks, style="heading 1"), first(blocks, style="heading 2")
    assert h1["format"] != h2["format"]
    d.apply_format([h2["id"]], d.get_format(h1["id"]))
    assert d.get_format(h2["id"])["summary"] == h1["format"]
    after = reopen(d.save())
    assert first(after, text=h2["text"], style="heading 1")["format"] == h1["format"]


@needs_hazid
def test_section_breaks_survive_apply(hazid):
    d = DocxDoc(hazid)
    paras = [b["id"] for b in d.blocks() if b["type"] == "paragraph"]  # includes the 9 paragraphs holding a sectPr
    d.apply_format(paras, d.get_format(paras[-1]))
    out = d.save()

    def sections(data):
        return [(s.start_type, s.orientation, s.page_width, s.page_height, s.left_margin,
                 s.different_first_page_header_footer) for s in docx.Document(BytesIO(data)).sections]

    assert len(sections(hazid)) == 10 and sections(out) == sections(hazid)
    old, new = ZipFile(BytesIO(hazid)), ZipFile(BytesIO(out))
    assert [n for n in old.namelist() if old.read(n) != new.read(n)] == ["word/document.xml"]


def test_cell_format_round_trip():
    d = DocxDoc(SAMPLE)
    cells = [c for b in d.blocks() if b["type"] == "table" for c in b["cells"]]
    src, dst = cells[0], cells[2]
    cf = d.get_cell_format(src["id"])
    assert (cf["fill"], cf["valign"], cf["marginsMm"]) == (src["fill"], src["valign"], src["marginsMm"])
    margins = {"l": 2.5, "r": 3.0, "t": 1.0, "b": 0.5}
    d.apply_cell_format([dst["id"]], {**cf, "fill": "#FFEEDD", "valign": "center", "marginsMm": margins},
                        ["text", "fill", "valign", "margins"])
    d.apply_cell_format([src["id"]], {"fill": None}, ["fill"])
    after = {c["id"]: c for b in walk(DocxDoc(d.save()).blocks()) if b["type"] == "table" for c in b["cells"]}
    reopen(d.save())
    cell = after[dst["id"]]
    assert (cell["fill"], cell["valign"], cell["marginsMm"]) == ("#FFEEDD", "center", margins)
    assert first(cell["blocks"], type="paragraph")["format"] == cf["text"]["summary"]
    assert after[src["id"]]["fill"] is None


def test_cell_text_format_keeps_numbering():
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=2)
    t.cell(0, 0).paragraphs[0].text = "plain"
    item = t.cell(0, 1).paragraphs[0]
    item.text, item.style = "item", doc.styles["List Number"]  # numbered through its style
    buf = BytesIO()
    doc.save(buf)
    d = DocxDoc(buf.getvalue())
    plain, numbered = d.blocks()[0]["cells"]
    plain_fmt, numbered_fmt = d.get_cell_format(plain["id"]), d.get_cell_format(numbered["id"])
    d.apply_cell_format([numbered["id"]], plain_fmt, ["text"])
    d.apply_cell_format([plain["id"]], numbered_fmt, ["text"])
    paras = [b for b in reopen(d.save()) if b["type"] == "paragraph"]
    assert [(b["style"], b["list"] and b["list"]["label"]) for b in paras] == [("List Number", None), (None, "1.")]
