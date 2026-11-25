"""양식 작성 04의 샘플·서식은 실제 문서 근거 자료와 따로 저장하고 이미지도 전달한다."""
import io

import fitz
import pytest
from docx import Document
from docx.shared import Pt
from fastapi.testclient import TestClient
from PIL import Image

from app import doc_agent, form_examples_api as E, server
from tests.test_guide_write import SMALL


def _png():
    out = io.BytesIO()
    Image.new("RGB", (32, 8), "blue").save(out, "PNG")
    return out.getvalue()


@pytest.mark.parametrize("disk", [False, True])
def test_attach_read_and_remove_in_one_work(monkeypatch, tmp_path, disk):
    monkeypatch.setenv("NFM_WORKS", str(tmp_path / "works") if disk else "off")
    c = TestClient(server.app)
    def new():
        return c.post("/api/docs?new=1", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    wid, other = new(), new()
    path = f"/api/docs/{wid}/form-examples"
    assert c.get(path).json() == {"files": []}
    doc = Document()
    doc.add_paragraph().add_run("작성 예시").font.size = Pt(19)
    t = doc.add_table(2, 2)
    t.cell(0, 0).merge(t.cell(0, 1)).text = "단위(천원)"
    t.cell(1, 0).text = "기관명"
    t.cell(1, 1).text = "예시 기관"
    doc.add_picture(io.BytesIO(_png()))
    out = io.BytesIO()
    doc.save(out)
    fixture = {"file": ("기관별 작성 예시.docx", out.getvalue())}
    resp = c.post(path, files=fixture)
    assert resp.status_code == 200, resp.text
    files = resp.json()["files"]
    assert len(files) == 1 and files[0]["imageCount"] == 1 and not files[0]["cut"] and "text" not in files[0]
    assert c.post(path, files=fixture).json()["files"] == files
    data, = E.evidence(wid)
    assert (data["sha256"], data["name"]) == (files[0]["sha256"], "기관별 작성 예시.docx")
    assert "sizePt=19" in data["text"] and "1행 × 2열 병합" in data["text"] and "예시 기관" in data["text"]
    assert data["images"][0]["data"].startswith(b"\x89PNG") and data["images"][0]["label"] in data["text"]
    assert not doc_agent.Store(wid).materials()
    other_path = f"/api/docs/{other}/form-examples"
    assert c.get(other_path).json() == {"files": []}
    assert c.delete(f"{other_path}/{data['id']}").status_code == 404
    assert c.post(path, files={"file": ("broken.docx", b"oops")}).status_code == 400
    assert c.get(path).json()["files"] == files
    assert c.delete(f"{path}/{data['id']}").json()["files"] == []
    assert not E.evidence(wid)


def test_pdf_reads_late_sample_page_and_tells_which_pages_have_images():
    with fitz.open() as doc:
        for i in range(7):
            p = doc.new_page()
            p.insert_text((30, 50), "Completed sample" if i == 5 else f"Page {i + 1}")
        text, images, cut = E._pdf(doc.tobytes())
    assert "Completed sample" in text and "원본 7쪽 중 본문 7쪽" in text
    assert cut and len(images) == E.IMAGES_MAX and any(im["label"] == "6쪽" for im in images)
    assert all(im["data"].startswith(b"\xff\xd8") for im in images)


def test_deleted_work_during_upload_cannot_receive_old_attachment(monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    c = TestClient(server.app)
    wid = c.post("/api/docs?new=1", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    def while_reading(*args):
        server.work_delete(wid)
        return "첨부 내용", [], False
    monkeypatch.setattr(E, "_extract", while_reading)
    resp = c.post(f"/api/docs/{wid}/form-examples", files={"file": ("예시.md", b"sample")})
    assert resp.status_code == 409 and not E.listing(wid) and wid not in E._MEM


def test_hwpx_and_long_appendix_keep_real_content():
    text, _, _ = E._extract(SMALL.name, SMALL.read_bytes(), "hwpx")
    assert "기술수요" in text and "[표 " in text and "sizePt=" in text
    raw = "처음\n" + "x" * (4 * E.TEXT_MAX) + "\n부록 작성 예시 — 단위는 백만 원"
    text, _, _ = E._extract("예시.md", raw.encode(), "md")
    short, cut = E._shorten(text)
    assert cut and len(short) <= E.TEXT_MAX and short.startswith("처음") and short.endswith("단위는 백만 원")
