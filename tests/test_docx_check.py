"""OOXML(DOCX) 참조 검사(app/docx_check.py) — 실물 기준선, 넣은 결함 찾기, 원본 대비 판정."""
import copy
import struct
import time
import zlib
from io import BytesIO
from pathlib import Path

import docx
import pytest
from lxml import etree

from app import docx_check as dc
from app.docx_doc import W, WP, DocxDoc

ROOT = Path(__file__).parent.parent
SAMPLE = (ROOT / "samples" / "기술수요조사서.docx").read_bytes()
HAZID = Path("E:/dev/docx_form/KR-HSE-HAZD-RPT-052 Rev.0 HAZID Report (K) - Youngchang_Ocean Cleaning Vessel.docx")


def _png(w=4, h=3):
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _built():
    d = docx.Document()
    d.add_heading("제목", 1)
    d.add_paragraph("번호 문단", style="List Number")
    d.add_paragraph("글머리 문단", style="List Bullet")
    t = d.add_table(rows=3, cols=3)
    t.cell(0, 0).merge(t.cell(1, 0))  # 세로 병합
    t.cell(2, 1).merge(t.cell(2, 2))  # 가로 병합
    t.cell(0, 1).text = "칸"
    d.add_picture(BytesIO(_png()))
    d.add_picture(BytesIO(_png(5, 5)))
    buf = BytesIO()
    d.save(buf)
    return buf.getvalue()


def _open(data):
    d = DocxDoc(data)
    d.blocks()  # 블록 id — 위반 예시의 자리
    return d


def _kinds(doc, hosts=None):
    res = dc.check_doc(doc) if hosts is None else dc.check_hosts(doc, hosts)
    return {v["kind"] for v in res["rules"]}


@pytest.mark.parametrize("data", [SAMPLE, _built()], ids=["sample", "python-docx"])
def test_clean_documents_have_no_violations(data):
    doc = _open(data)
    res = dc.check_doc(doc)
    assert res == {"schema": [], "rules": []}
    v = dc.verdict(doc, dc.counts(res), res)
    assert v["status"] == "ok" and v["ruleTotal"] == 0
    assert "원본에 없던 위반 없음" in dc.summary_text(v)


def _body(doc):
    return doc._part(doc._doc).find(W + "body")


def _first_p(doc, text=None):
    return next(p for p in _body(doc).iter(W + "p") if text is None or text in "".join(p.itertext()))


def test_dangling_relationship_id():
    doc = _open(_built())
    blip = next(_body(doc).iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"))
    blip.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", "rId999")
    assert ("rule", "rel", "blip@embed") in _kinds(doc)


def test_relationship_target_missing_and_content_type():
    doc = _open(_built())
    rels = doc._part(doc._rels_name)
    etree.SubElement(rels, dc.PKG_REL + "Relationship", Id="rId900",
                     Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", Target="media/nothing.png")
    doc._names.add("word/media/extra.bin")
    k = _kinds(doc)
    assert ("rule", "relTarget", "image") in k
    assert ("rule", "contentType", "bin") in k


def test_undefined_style_and_number():
    doc = _open(_built())
    ppr = _first_p(doc, "제목").find(W + "pPr")
    ppr.find(W + "pStyle").set(W + "val", "NoSuchStyle")
    numbered = _first_p(doc, "번호 문단")
    ppr = numbered.find(W + "pPr")
    num_pr = etree.SubElement(ppr, W + "numPr")  # 자리는 순서 규칙과 따로 — pStyle 바로 뒤
    ppr.remove(num_pr)
    ppr.find(W + "pStyle").addnext(num_pr)
    etree.SubElement(num_pr, W + "ilvl").set(W + "val", "0")
    etree.SubElement(num_pr, W + "numId").set(W + "val", "777")
    k = _kinds(doc)
    assert ("rule", "style", "pStyle") in k
    assert ("rule", "num", "numId") in k


def test_numbering_parts():
    doc = _open(_built())
    numbering = doc._sub_part("numbering")
    num = numbering.find(W + "num")
    num.find(W + "abstractNumId").set(W + "val", "4242")
    numbering.append(copy.deepcopy(numbering.find(W + "abstractNum")))  # abstractNum 이 num 뒤
    k = _kinds(doc)
    assert ("rule", "num", "abstractNumId") in k
    assert ("rule", "num", "order") in k


def test_table_structure():
    doc = _open(_built())
    tbl = next(_body(doc).iter(W + "tbl"))
    trs = tbl.findall(W + "tr")
    tc = trs[0].findall(W + "tc")[1]
    for p in tc.findall(W + "p"):
        tc.remove(p)
    tc.append(copy.deepcopy(tbl))  # 칸이 표로 끝남 — Word 오류
    k = _kinds(doc)
    assert ("rule", "tbl", "endP") in k
    # 세로 병합 이어짐 칸 위에 병합 칸이 없음 · 칸 없는 행 · 격자보다 넓은 행
    doc = _open(_built())
    tbl = next(_body(doc).iter(W + "tbl"))
    trs = tbl.findall(W + "tr")
    first = trs[0].findall(W + "tc")[0]
    first.find(W + "tcPr").remove(first.find(f"{W}tcPr/{W}vMerge"))
    span = trs[1].findall(W + "tc")[2].find(W + "tcPr")
    etree.SubElement(span if span is not None else trs[1].findall(W + "tc")[2], W + "gridSpan").set(W + "val", "2")
    for tc in trs[2].findall(W + "tc"):
        trs[2].remove(tc)
    k = _kinds(doc)
    assert {("rule", "tbl", "vMerge"), ("rule", "tbl", "emptyRow"), ("rule", "tbl", "gridSpan")} <= k


def test_property_place_and_order():
    doc = _open(_built())
    p = _first_p(doc, "제목")
    r = p.find(W + "r")
    rpr = r.find(W + "rPr") if r.find(W + "rPr") is not None else etree.SubElement(r, W + "rPr")
    r.remove(rpr)
    r.append(rpr)  # rPr 가 w:t 뒤
    ppr = p.find(W + "pPr")
    etree.SubElement(ppr, W + "jc").set(W + "val", "center")
    ppr.append(etree.Element(W + "keepNext"))  # keepNext 는 jc 앞이어야 함
    k = _kinds(doc)
    assert ("rule", "r", "first") in k
    assert ("rule", "order", "pPr/keepNext") in k
    res = dc.check_doc(doc)
    ex = next(v for v in res["rules"] if v["kind"] == ("rule", "order", "pPr/keepNext"))
    assert ex["block"] == doc._rev[p]  # 위반 자리 = 그 문단 블록


def test_duplicate_unique_ids_but_not_in_fallback():
    doc = _open(_built())
    prs = list(_body(doc).iter(WP + "docPr"))
    prs[1].set("id", prs[0].get("id"))
    assert ("rule", "dup", "docPr") in _kinds(doc)
    # mc:Fallback(VML 사본) 안의 같은 id 는 셈하지 않는다 — Word 는 가지 하나만 읽음
    doc = _open(_built())
    mc = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
    drawing = next(_body(doc).iter(W + "drawing"))
    alt = etree.Element(mc + "AlternateContent")
    drawing.addprevious(alt)
    etree.SubElement(alt, mc + "Choice", Requires="wps").append(drawing)
    etree.SubElement(alt, mc + "Fallback").append(copy.deepcopy(drawing))
    assert not _kinds(doc)


def test_verdict_against_baseline_and_hosts():
    doc = _open(SAMPLE)
    base = dc.counts(dc.check_doc(doc))
    host = next(e for e in _body(doc) if e.tag == W + "p" and e.find(W + "pPr") is not None)
    assert dc.verdict(doc, base, dc.check_hosts(doc, [host]), local=True)["status"] == "ok"
    ppr = host.find(W + "pPr")
    etree.SubElement(ppr, W + "jc").set(W + "val", "center")
    ppr.append(etree.Element(W + "keepNext"))  # keepNext 가 jc 뒤 — 원본에 없던 종류(순서)
    v =dc.verdict(doc, base, dc.check_hosts(doc, [host]), local=True)
    assert v["status"] == "fail" and v["rules"][0]["examples"][0]["block"] == doc._rev.get(host)
    assert "OOXML 참조 규칙 위반" in dc.summary_text(v)
    full = dc.verdict(doc, base, dc.check_doc(doc))
    assert full["status"] == "fail" and full["rules"][0]["count"] == 1 and full["rules"][0]["base"] == 0
    # 다른 문단(범위 밖)은 local 검사에 안 나온다
    other = [e for e in _body(doc) if e.tag == W + "p" and e is not host][0]
    assert dc.verdict(doc, base, dc.check_hosts(doc, [other]), local=True)["status"] == "ok"


def test_saved_edit_keeps_clean():
    """어댑터로 글을 고쳐 저장·다시 열어도 위반이 생기지 않는다."""
    doc = _open(SAMPLE)
    pid = next(i for i, el in doc._ids.items() if el.tag == W + "p" and "".join(el.itertext()).strip())
    doc.set_text(pid, "바뀐 글\t탭\u2028줄")
    again = _open(doc.save())
    assert dc.check_doc(again)["rules"] == []


@pytest.mark.skipif(not HAZID.exists(), reason="external HAZID sample not available")
def test_real_report_baseline_and_speed():
    doc = _open(HAZID.read_bytes())
    t = time.perf_counter()
    res = dc.check_doc(doc)
    took = time.perf_counter() - t
    assert res["rules"] == [], [v["message"] for v in res["rules"][:5]]
    assert took < 1.0
