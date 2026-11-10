"""DOCX 웹 편집·검증 흐름(spec_docx_웹편집 ② §2~§5) — hwpx 시험(test_server·test_owpml)과 같은 흐름을 docx 예제로. Word 없이(NFM_PDF=off)
패키지 단계, 가짜 PDF 출력으로 PDF 단계."""
import io
import zipfile
from pathlib import Path

import docx
import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import docx_restore, docx_struct, pdf_map, pdf_render, server, verify
from app.docx_doc import W, DocxDoc
from tests.test_server import _fake_pdf, _paras, _wait

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.docx"
DATA = SMALL.read_bytes()


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _upload(c, data=DATA, name=SMALL.name):
    r = c.post("/api/docs", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _first(blocks, pred):
    return next(p for p in _paras(blocks) if pred(p))


def test_open_docx_blocks_and_view_keys(client):
    d = _upload(client)
    g = client.get(f"/api/docs/{d}").json()
    assert g["format"] == "docx" and g["pristine"]
    tbl = next(b for b in g["blocks"] if b["type"] == "table")
    assert tbl["borderFills"] and all(c["bf"] in tbl["borderFills"] for c in tbl["cells"])
    line = tbl["borderFills"][tbl["cells"][0]["bf"]]["t"]
    assert line["type"] == "SOLID" and line["color"] == "#000000"  # TableGrid 스타일의 선
    f = g["blocks"][0]["format"]
    assert f["font"] == "맑은 고딕" and f["wordBreak"] in ("word", "char")
    assert "맑은 고딕" in g["webFonts"]["alias"].get("HANGUL", {})
    assert {"name": SMALL.name, "size": len(DATA)} in client.get("/api/samples").json()


def test_import_verify_without_word(client):
    d = _upload(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s for s in v["import"]["steps"]}
    assert st["package"]["status"] == st["xml"]["status"] == st["model"]["status"] == "ok", st
    assert st["owpml"]["status"] == "ok" and st["owpml"]["title"] == "OOXML 참조 검사"
    assert st["pdf"]["status"] == "skip" and "Word" in st["pdf"]["title"]
    assert v["import"]["status"] == "ok"


def test_rebuild_docx_members_identical():
    rebuilt, differ, n = verify.rebuild_all(DATA, "docx")
    assert not differ and n == 5  # [Content_Types]·본문·본문 관계·스타일·번호(verify.docx_writable)
    za, zb = (zipfile.ZipFile(io.BytesIO(x)) for x in (DATA, rebuilt))
    assert za.namelist() == zb.namelist() and all(za.read(m) == zb.read(m) for m in za.namelist())


def test_edit_download_and_restore_to_original_bytes(client):
    d = _upload(client)
    paras = _paras(client.get(f"/api/docs/{d}").json()["blocks"])
    a, b = [p for p in paras if len(p["text"]) > 6][2:4]
    for p in (a, b):
        r = client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★\t탭 줄"}).json()
        assert r["edited"] and not r["pristine"]
    dl = client.get(f"/api/docs/{d}/download")
    assert dl.headers["X-Same-As-Original"] == "0" and "_%EC%88%98%EC%A0%95.docx" in dl.headers["Content-Disposition"]
    assert "wordprocessingml" in dl.headers["content-type"]
    again = DocxDoc(dl.content)
    texts = {p["id"]: p["text"] for p in _paras(again.blocks())}
    assert texts[a["id"]] == a["text"] + "★\t탭 줄"
    docx.Document(io.BytesIO(dl.content))  # python-docx 도 연다
    # 하나는 손으로 원래 글, 하나는 되돌리기 → 원본 바이트
    r = client.patch(f"/api/docs/{d}/blocks/{a['id']}", json={"text": a["text"]}).json()
    assert r["restored"] and not r["edited"]
    r = client.post(f"/api/docs/{d}/blocks/{b['id']}/revert").json()
    assert r["restored"] and r["pristine"]
    assert client.get(f"/api/docs/{d}/download").content == DATA


def test_split_merge_format_table_undo_roundtrip(client):
    d = _upload(client)
    blocks = client.get(f"/api/docs/{d}").json()["blocks"]
    p = _first(blocks, lambda x: x["text"] == "[1] 전력변환시스템")
    r = client.post(f"/api/docs/{d}/split", json={"id": p["id"], "offset": 4})
    assert r.status_code == 200, r.text
    r = r.json()
    new = r["focus"]["id"]
    assert r["texts"][p["id"]] == "[1] " and r["texts"][new] == "전력변환시스템"
    assert r["kinds"] == {p["id"]: "struct", new: "new"} and r["owpml"]["status"] == "ok"
    tid = next(b["id"] for b in blocks if b["type"] == "table")
    assert tid in r["tops"]["drop"] and tid in {b["id"] for b in r["tops"]["blocks"]}  # 칸 안 편집 = 그 표째 바꿔 끼움
    assert client.patch(f"/api/docs/{d}/blocks/{new}", json={"text": "새 글"}).json()["edited"]
    r = client.post(f"/api/docs/{d}/merge", json={"id": new, "dir": "prev"}).json()
    assert r["focus"] == {"id": p["id"], "offset": 4} and r["texts"][p["id"]] == "[1] 새 글"
    r = client.post(f"/api/docs/{d}/format/chars", json={"id": p["id"], "start": 0, "end": 3,
                                                          "changes": {"bold": "toggle", "color": "#FF0000"}}).json()
    assert r["focus"] == {"id": p["id"], "offset": 0, "end": 3}
    look = next(b for b in _paras(r["tops"]["blocks"]) if b["id"] == p["id"])
    assert look["runs"][0]["format"]["color"] == "#FF0000"
    r = client.post(f"/api/docs/{d}/format/para", json={"ids": [p["id"]], "changes": {"align": "center", "lineSpacingPct": 160}}).json()
    assert next(b for b in _paras(r["tops"]["blocks"]) if b["id"] == p["id"])["format"]["align"] == "center"
    tbl = next(b for b in blocks if b["type"] == "table")
    home = next(c for c in tbl["cells"][12:] if any(x["type"] == "paragraph" for x in c["blocks"]))
    cell_p = next(x["id"] for x in home["blocks"] if x["type"] == "paragraph")
    for op, dr, dc in (("row_below", 1, 0), ("col_right", 0, 1), ("col_left", 0, 1), ("row_delete", -1, 0), ("col_delete", 0, -1)):
        if op == "row_delete":  # 지우기는 표 마지막 행에서(col_left 가 고른 문단을 오른쪽 사본 칸으로 옮겼으므로)
            cell_p = next(x["id"] for c in tbl["cells"] if c["row"] == tbl["nRows"] - 1 for x in c["blocks"] if x["type"] == "paragraph")
        if op == "col_delete":  # col_left 가 만든 빈 칸(원래 칸 자리) — 같은 열 구조의 사본이라 병합 경계에 안 걸림
            cell_p = next(x["id"] for c in tbl["cells"] if (c["row"], c["col"]) == (home["row"], home["col"])
                          for x in c["blocks"] if x["type"] == "paragraph")
        r = client.post(f"/api/docs/{d}/table", json={"id": cell_p, "op": op})
        assert r.status_code == 200, (op, r.text)
        tb = next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)
        assert (tb["nRows"], tb["nCols"]) == (tbl["nRows"] + dr, tbl["nCols"] + dc), op
        tbl = tb
    # 끌어 고른 칸 묶음(range) — 원래 칸 + 아래에 넣은 빈 행(같은 구조) 두 행을 기준으로 두 행 넣고 세 행 지움
    cell_p = next(x["id"] for c in tbl["cells"] if (c["row"], c["col"]) == (home["row"], home["col"]) for x in c["blocks"] if x["type"] == "paragraph")
    rng = {"r0": home["row"], "c0": home["col"], "r1": home["row"], "c1": home["col"]}
    assert client.post(f"/api/docs/{d}/table", json={"id": cell_p, "op": "row_below", "range": rng}).status_code == 200
    r = client.post(f"/api/docs/{d}/table", json={"id": cell_p, "op": "row_below", "range": {**rng, "r1": home["row"] + 1}})
    assert r.status_code == 200, r.text
    assert next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)["nRows"] == tbl["nRows"] + 3
    r = client.post(f"/api/docs/{d}/table", json={"id": cell_p, "op": "row_delete", "range": {**rng, "r0": home["row"] + 1, "r1": home["row"] + 3}})
    assert r.status_code == 200, r.text
    assert next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)["nRows"] == tbl["nRows"]
    bad = client.post(f"/api/docs/{d}/table", json={"id": cell_p, "op": "col_delete", "range": {**rng, "c1": 99}})
    assert bad.status_code == 400 and "표 밖" in bad.json()["detail"]
    saved = client.get(f"/api/docs/{d}/download").content
    docx.Document(io.BytesIO(saved))
    assert client.get(f"/api/docs/{d}/owpml").json()["status"] == "ok"
    g = client.get(f"/api/docs/{d}").json()
    while g["undo"]:
        g = client.post(f"/api/docs/{d}/undo").json()
    assert g["pristine"] and g["edited"] == []
    assert client.get(f"/api/docs/{d}/download").content == DATA


def test_split_refusals_and_section_move():
    doc = DocxDoc(DATA)
    doc.blocks()
    body_ps = [p for p in doc._body.iterchildren(W + "p")]
    last = body_ps[-1] if body_ps[-1].find(f"{W}pPr/{W}sectPr") is not None else None
    if last is not None:  # 구역 나누기는 뒤 문단으로
        pid = doc._id(last)
        new = doc.split_para(pid, 0)
        assert doc._ids[new].find(f"{W}pPr/{W}sectPr") is not None and last.find(f"{W}pPr/{W}sectPr") is None
    # 복합 필드 가운데는 거절
    p = etree.SubElement(doc._body, W + "p")
    for kind, text in (("begin", None), (None, " PAGE "), ("separate", None), (None, "12"), ("end", None)):
        r = etree.SubElement(p, W + "r")
        if kind:
            etree.SubElement(r, W + "fldChar").set(W + "fldCharType", kind)
        elif text.strip().isdigit():
            etree.SubElement(r, W + "t").text = text
        else:
            etree.SubElement(r, W + "instrText").text = text
    doc.blocks()
    with pytest.raises(ValueError, match="필드"):
        doc.split_para(doc._id(p), 1)


def test_server_rejects_ooxml_violation_and_rolls_back(client, monkeypatch):
    d = _upload(client)
    p = _first(client.get(f"/api/docs/{d}").json()["blocks"], lambda x: x["text"] == "[1] 전력변환시스템")
    real = DocxDoc.split_para

    def broken(self, block_id, offset):
        new = real(self, block_id, offset)
        etree.SubElement(self._ids[new], W + "pPr")  # pPr 두 번째·맨 앞 아님 — OOXML 위반
        return new
    monkeypatch.setattr(DocxDoc, "split_para", broken)
    r = client.post(f"/api/docs/{d}/split", json={"id": p["id"], "offset": 2})
    assert r.status_code == 422 and "OOXML" in r.json()["detail"]
    g = client.get(f"/api/docs/{d}").json()
    assert g["undo"] == 0 and g["pristine"]
    assert client.get(f"/api/docs/{d}/download").content == DATA


def test_pdf_steps_and_edit_verify_with_fake_word(client, monkeypatch):
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "export_pdf", _fake_pdf)
    added = []

    def fake_resave(data, fmt="hwpx", limit=None):  # Word 처럼 끝 표 뒤에 빈 문단 하나를 더한 다시 저장
        doc = DocxDoc(data)
        etree.SubElement(doc._body, W + "p").getparent().insert(len(doc._body) - 1, doc._body[-1])
        doc._dirty.add(doc._doc)
        added.append(fmt)
        return doc.save()
    monkeypatch.setattr(pdf_render, "resave", fake_resave)
    d = _upload(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s for s in v["import"]["steps"]}
    assert st["pdf"]["status"] == "ok" and st["map"]["status"] == "ok", st["map"]
    assert st["render"]["status"] == "ok" and v["mapping"]["ratio"] >= 0.9
    p = [x for x in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if pdf_map.key_text(x["text"])][-1]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "추가글"})
    client.post(f"/api/docs/{d}/verify", json={"kind": "edit"})
    v = _wait(client, d, "edit")
    st = {s["key"]: s for s in v["edit"]["steps"]}
    assert st["epackage"]["status"] == "ok", st["epackage"]
    assert st["eowpml"]["status"] == "ok" and st["eowpml"]["title"] == "수정본 OOXML 검사"
    assert st["esave"]["status"] == "ok" and "Word" in st["esave"]["title"] and added == ["docx"], st["esave"]
    assert st["epages"]["status"] == "ok" and st["etext"]["status"] == "ok", (st["epages"], st["etext"])


def test_snapshot_restore_baseline_is_original():
    d = DocxDoc(DATA)
    d.blocks()
    snap = docx_struct.snapshot(d)
    new = d.split_para("p6", 2)
    snap2 = docx_struct.snapshot(d)
    back = docx_struct.restore(DocxDoc, DATA, snap2)
    assert back._data is DATA and back._doc in back._dirty and new in back._ids
    pr = DocxDoc(DATA)
    pr.blocks()
    back.merge_paras("p6")
    assert docx_restore.restore_para(back, pr, "p6")
    docx_restore.settle(back, [back._doc])
    assert back.save() == DATA and docx_struct.restore(DocxDoc, DATA, snap).save() == DATA


# ---- 실물(Word 16 PDF·HAZID 보고서)에서 찾은 것 — spec_docx_웹편집 ③ ----------------------------------------------

def _numbered_doc():
    """numId 1·2 가 같은 abstractNum(수준 0 「%1.」·수준 1 「%1.%2.」·수준 1 들여쓰기 left 720 hanging 360)을 쓰고, 2 는 모든 수준 startOverride 1."""
    from docx.oxml import parse_xml
    d = docx.Document()
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    numbering = d.part.numbering_part.element
    numbering.append(parse_xml(
        f'<w:abstractNum {ns} w:abstractNumId="90"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2."/>'
        '<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'))
    numbering.append(parse_xml(f'<w:num {ns} w:numId="91"><w:abstractNumId w:val="90"/></w:num>'))
    numbering.append(parse_xml(f'<w:num {ns} w:numId="92"><w:abstractNumId w:val="90"/>'
                               '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>'
                               '<w:lvlOverride w:ilvl="1"><w:startOverride w:val="1"/></w:lvlOverride></w:num>'))
    for num, lvl, text in ((91, 0, "가"), (91, 0, "나"), (91, 1, "나-1"), (92, 1, "다른 num 첫 문단(수준 1)"), (92, 0, "다른 num 수준 0")):
        p = d.add_paragraph(text)
        p._p.get_or_add_pPr().append(parse_xml(f'<w:numPr {ns}><w:ilvl w:val="{lvl}"/><w:numId w:val="{num}"/></w:numPr>'))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_shared_list_counters_and_first_use_start_override():
    """같은 abstractNum 의 w:num 은 번호를 잇고, startOverride 는 그 w:num 이 처음 쓰인 문단의 수준만 다시 센다(Word 「5.1.」 → 「6.」)."""
    labels = [(p["text"], p["list"]["label"]) for p in _paras(DocxDoc(_numbered_doc()).blocks()) if p.get("list")]
    assert labels == [("가", "1."), ("나", "2."), ("나-1", "2.1."), ("다른 num 첫 문단(수준 1)", "2.1."), ("다른 num 수준 0", "3.")]


def test_numbering_level_indent_in_summary():
    """번호 수준의 들여쓰기(abstractNum lvl/pPr)가 서식 요약에 — 직접 서식 다음, 스타일 앞."""
    p = next(p for p in _paras(DocxDoc(_numbered_doc()).blocks()) if p["text"] == "나-1")
    assert p["format"]["indentLeftMm"] == pytest.approx(12.7, abs=0.1) and p["format"]["firstLineMm"] == pytest.approx(-6.35, abs=0.1)
    # 레터 대조는 hwpx 뜻(첫 줄 = 왼쪽 여백)으로: Word 내어쓰기 첫 줄 = left − hanging
    b = verify.hang_as_hwpx([{"type": "paragraph", "format": dict(p["format"])}])[0]
    assert b["format"]["indentLeftMm"] == pytest.approx(6.35, abs=0.1)


def test_toc_hyperlink_keeps_toc_look():
    from docx.oxml import parse_xml
    d = docx.Document()
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    styles = d.styles.element
    styles.append(parse_xml(f'<w:style {ns} w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/>'
                            '<w:rPr><w:color w:val="262626"/></w:rPr></w:style>'))
    styles.append(parse_xml(f'<w:style {ns} w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
                            '<w:rPr><w:color w:val="0000FF"/><w:u w:val="single"/></w:rPr></w:style>'))
    for style in ("TOC1", None):
        p = d.add_paragraph(style=None)
        if style:
            p._p.get_or_add_pPr().append(parse_xml(f'<w:pStyle {ns} w:val="{style}"/>'))
        p._p.append(parse_xml(f'<w:hyperlink {ns} w:anchor="_Toc1"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>목차 항목</w:t></w:r></w:hyperlink>'))
    buf = io.BytesIO()
    d.save(buf)
    toc, plain = [p["format"] for p in _paras(DocxDoc(buf.getvalue()).blocks())]
    assert toc["color"] == "#262626" and not toc["underline"]
    assert plain["color"] == "#0000FF" and plain["underline"]


def test_word_pdf_lines_trailing_space_and_pua_bullet():
    pages = [{"lines": [{"text": " Senior Researcher ", "chars": [("",), (" ",), ("S",), (" ",)]}]}]
    verify.word_pdf_lines(pages)
    ln = pages[0]["lines"][0]
    assert ln["text"] == "• Senior Researcher" and [c[0] for c in ln["chars"]] == ["•", " ", "S"]
    pages = [{"lines": [{"text": "⚫ 기관명", "chars": [("⚫",), (" ",), ("기",)]}]}]  # Wingdings 「l」을 Word 는 ⚫ 로
    assert verify.word_pdf_lines(pages)[0]["lines"][0]["text"] == "● 기관명"


def test_numbered_outline_heading_gets_letter():
    """제목 스타일(개요 수준)에 번호가 걸린 docx 문단 — 웹이 라벨을 보이므로 레터로 잰다(hwpx 개요 번호는 list 가 아님)."""
    from app import headings
    blocks = [{"id": "p1", "type": "paragraph", "text": "서론", "outlineLevel": 1, "list": {"kind": "number", "level": 1, "label": "1."}},
              {"id": "p2", "type": "paragraph", "text": "개요만", "outlineLevel": 1, "list": None}]
    rows = headings.extract(blocks)["rows"]
    assert rows["p1"]["head"]["auto"] and rows["p1"]["head"]["letter"] == "1." and rows["p1"]["level"] == 1
    assert rows["p2"]["letter"] is None


def test_table_style_conditional_look_and_auto_white():
    """표 스타일 조건부 서식(머리 행 흰 굵은 글·음영)과 어두운 칸 음영 위 자동 글자색 흰색(spec_docx_웹편집 ② §2 — Word 16 PDF: AIP 서식)."""
    from docx.oxml import parse_xml
    d = docx.Document()
    t = d.add_table(rows=3, cols=2)
    t.style = d.styles["Medium Shading 1 Accent 1"]  # python-docx 기본 서식: firstRow = 흰 굵은 글 + 4F81BD 음영
    for r, row in enumerate(t.rows):
        for c, cell in enumerate(row.cells):
            cell.paragraphs[0].text = f"칸{r}{c}"
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    t.rows[2].cells[1]._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {ns} w:val="clear" w:color="auto" w:fill="002060"/>'))
    buf = io.BytesIO()
    d.save(buf)
    tb = next(b for b in DocxDoc(buf.getvalue()).blocks() if b["type"] == "table")
    cell = {(c["row"], c["col"]): c for c in tb["cells"]}
    head = cell[0, 1]["blocks"][0]["format"]
    assert head["color"] == "#FFFFFF" and head["bold"] and cell[0, 1]["fill"] == "#4F81BD"
    assert cell[1, 1]["blocks"][0]["format"]["color"] != "#FFFFFF"
    assert cell[2, 1]["fill"] == "#002060" and cell[2, 1]["blocks"][0]["format"]["color"] == "#FFFFFF"  # 자동 색 → 흰색
