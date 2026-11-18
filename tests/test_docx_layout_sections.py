"""docx 구역의 쪽 설정 — 「이어서」 구역 표지(spec_hwpx_웹편집 ② §3-1 「구역이 바뀌면 새 쪽」).

웹은 구역이 바뀌면 새 쪽 상자를 연다(한글 구역은 늘 새 쪽). Word 의 「이어서」 구역(`w:type continuous`)만 용지가 같을 때 같은 쪽에 잇는다 —
그 표지를 `docx_layout.page` 가 구역의 첫 블록 `page.continuous` 로 넘긴다(app.js `paginate` `newSec`)."""
import io

import docx
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.shared import Mm

from app.docx_doc import DocxDoc


def _three_sections() -> bytes:
    d = docx.Document()
    d.add_paragraph("첫 구역")
    s2 = d.add_section(WD_SECTION.CONTINUOUS)  # 같은 용지 · 이어서
    d.add_paragraph("이어서 구역")
    s3 = d.add_section(WD_SECTION.NEW_PAGE)  # 가로 · 새 쪽
    s3.orientation = WD_ORIENT.LANDSCAPE
    s3.page_width, s3.page_height = s2.page_height, s2.page_width
    d.add_paragraph("가로 구역")
    for s in d.sections:
        s.left_margin = s.right_margin = Mm(20)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_section_pages_mark_continuous_only():
    blocks = DocxDoc(_three_sections()).blocks()
    pages = [(b.get("text"), b["page"]) for b in blocks if b.get("page")]
    assert [t for t, _ in pages] == ["첫 구역", "이어서 구역", "가로 구역"]
    first, cont, wide = (p for _, p in pages)
    assert "continuous" not in first
    assert cont["continuous"] is True and (cont["widthMm"], cont["heightMm"]) == (first["widthMm"], first["heightMm"])
    assert "continuous" not in wide and wide["widthMm"] > wide["heightMm"]
