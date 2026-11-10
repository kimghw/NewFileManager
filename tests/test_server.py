"""서버·검증 흐름(spec_hwpx_웹편집 ② §2~§4) — 한글 없이(NFM_PDF=off) 패키지 단계, 가짜 PDF 출력으로 PDF 단계."""
import io
import time
import zipfile
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app import pdf_map, pdf_render, server, verify

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _wait(c, d, kind, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if kind in v and not v[kind]["running"]:
            return v
        time.sleep(0.1)
    raise AssertionError("검증이 끝나지 않음")


def _paras(blocks):
    out = []
    for b in blocks:
        if b["type"] == "paragraph":
            out.append(b)
        for c in b.get("cells", ()):
            out += _paras(c["blocks"])
    return out


def _upload(c, path=SMALL):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def test_upload_import_verify_without_hangul(client):
    d = _upload(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s["status"] for s in v["import"]["steps"]}
    assert st["package"] == st["xml"] == st["model"] == "ok"
    assert st["pdf"] == st["map"] == st["render"] == "skip"
    assert v["import"]["status"] == "ok"


def test_unmodified_download_is_byte_identical(client):
    d = _upload(client)
    assert client.get(f"/api/docs/{d}/download").content == SMALL.read_bytes()


def test_edit_roundtrip_and_revert(client):
    d = _upload(client)
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip()]
    p = paras[3]
    r = client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★\u2028둘째 줄\t탭"}).json()
    assert r["edited"] and r["editedCount"] == 1
    saved = client.get(f"/api/docs/{d}/download").content
    assert saved != SMALL.read_bytes()
    again = {b["id"]: b["text"] for b in _paras(server.HwpxDoc(saved).blocks())}
    assert again[p["id"]] == p["text"] + "★\u2028둘째 줄\t탭"
    others = {b["id"]: b["text"] for b in _paras(server.HwpxDoc(SMALL.read_bytes()).blocks())}
    assert {i for i in others if others[i] != again.get(i)} == {p["id"]}
    # 원래 글로 되돌리면 고친 문단에서 빠진다
    r = client.post(f"/api/docs/{d}/blocks/{p['id']}/revert").json()
    assert not r["edited"] and r["editedCount"] == 0
    assert client.get(f"/api/docs/{d}").json()["edited"] == []


def test_revert_restores_original_bytes(client):
    """되돌리기는 글만이 아니라 원본 XML(줄 배치 캐시 포함)을 되놓는다 — 모두 되돌리면 저장본 = 원본 바이트(astra 검토 4)."""
    d = _upload(client)
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip()]
    a, b = paras[2], paras[5]
    for p in (a, b):
        r = client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★\t탭"}).json()
        assert r["pristine"] is False
    r = client.post(f"/api/docs/{d}/blocks/{a['id']}/revert").json()
    assert r["restored"] is True and r["editedCount"] == 1 and r["pristine"] is False
    # 남은 하나는 글을 손으로 원래대로 고쳐 넣어도(PATCH) 원본 XML 로 돌아간다
    r = client.patch(f"/api/docs/{d}/blocks/{b['id']}", json={"text": b["text"]}).json()
    assert r["restored"] is True and r["editedCount"] == 0 and r["pristine"] is True
    got = client.get(f"/api/docs/{d}/download")
    assert got.content == SMALL.read_bytes() and got.headers["x-same-as-original"] == "1"


def test_edit_verify_package_step(client):
    d = _upload(client)
    _wait(client, d, "import")
    p = next(p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip())
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 수정"})
    assert client.post(f"/api/docs/{d}/verify", json={"kind": "edit"}).status_code == 200
    v = _wait(client, d, "edit")
    ep = next(s for s in v["edit"]["steps"] if s["key"] == "epackage")
    assert ep["status"] == "ok", ep
    assert all(m.startswith("Contents/section") for m in ep["members"])
    assert {s["key"]: s["status"] for s in v["edit"]["steps"]}["epdf"] == "skip"


def test_rejects_non_hwpx(client):
    assert client.post("/api/docs", files={"file": ("a.txt", b"x")}).status_code == 400
    assert client.post("/api/docs", files={"file": ("a.hwpx", b"not a zip")}).status_code == 400


def test_media_and_samples(client):
    names = [s["name"] for s in client.get("/api/samples").json()]
    assert SMALL.name in names
    d = client.post(f"/api/samples/{SMALL.name}").json()["docId"]
    assert client.get(f"/api/docs/{d}/media", params={"name": "BinData/x.wmf"}).status_code == 415
    assert client.post("/api/samples/..%2Frequirements.txt").status_code == 404


# ---- PDF 단계: 한글 대신 블록 글로 PDF 를 만드는 가짜 출력 --------------------------------------------

def _fake_pdf(data, limit=None, fmt="hwpx"):
    """블록 글을 한 쪽에 30문단씩 찍은 PDF — 한글(docx 는 Word) PDF 처럼 글자열로 매핑·픽셀 비교가 된다."""
    out = pdf_render.render_dir()
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / f"{pdf_render.sha(data)}.pdf"
    texts = [t for t in verify.flat_texts(verify.KIT[fmt][0](data).blocks()).values() if pdf_map.key_text(t)]
    doc = fitz.open()
    font = fitz.Font(fontfile="C:/Windows/Fonts/malgun.ttf") if Path("C:/Windows/Fonts/malgun.ttf").exists() else None
    lines = [t.replace("\u2028", " ").replace("\t", " ")[k:k + 40] for t in texts for k in range(0, len(t), 40)]
    for i in range(0, len(lines), 30):
        page = doc.new_page()
        tw = fitz.TextWriter(page.rect)
        for k, t in enumerate(lines[i:i + 30]):
            tw.append((40, 90 + k * 22), t, font=font, fontsize=9)
        tw.write_text(page)
    doc.save(pdf)
    return pdf


def test_pdf_steps_with_fake_renderer(client, monkeypatch):
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "export_pdf", _fake_pdf)
    d = _upload(client)
    v = _wait(client, d, "import")
    st = {s["key"]: s for s in v["import"]["steps"]}
    assert st["pdf"]["status"] == "ok" and st["pdf"]["pages"] >= 1
    assert st["map"]["status"] == "ok", st["map"]
    assert st["render"]["status"] == "ok", st["render"]
    assert v["mapping"]["ratio"] >= 0.9
    # 고친 문단이 든 쪽만 달라진다
    paras = [p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if pdf_map.key_text(p["text"])]
    target = paras[-1]
    client.patch(f"/api/docs/{d}/blocks/{target['id']}", json={"text": target["text"] + "추가글"})
    client.post(f"/api/docs/{d}/verify", json={"kind": "edit"})
    v = _wait(client, d, "edit")
    st = {s["key"]: s for s in v["edit"]["steps"]}
    assert st["epages"]["status"] == "ok", st["epages"]
    assert [x["page"] for x in st["epages"]["diffPages"]] == st["epages"]["expected"]
    assert st["etext"]["status"] == "ok", st["etext"]
    page = st["epages"]["expected"][0]
    assert client.get(f"/api/docs/{d}/pdf/original/{page}.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/docs/{d}/diff/edited/{page}.png").status_code == 200


def test_pagination_follows_pdf_page_tops(tmp_path):
    """쪽 나눔(paginate): 쪽마다 하나씩, PDF 맨 위 줄과 맞거나(ok·moved) 앞 쪽에서 이어진 문단(split) — 못 맞춘 쪽 없음."""
    data = SMALL.read_bytes()
    pdf = _fake_pdf(data)
    m = pdf_map.map_blocks(server.HwpxDoc(data).blocks(), pdf, halves=False)
    assert m["pageCount"] >= 2 and [b["page"] for b in m["breaks"]] == list(range(1, len(m["breaks"]) + 1))
    assert all(c["status"] in ("ok", "moved", "split") for c in m["checks"]), m["checks"]
    assert m["agree"] >= 0.95 and m["sheets"] == list(range(1, m["pageCount"] + 1))


def test_units_keep_row_spans_together():
    """세로 병합 칸이 걸친 행은 한 단위 — 그 사이에서는 쪽을 나누지 않는다."""
    cell = lambda r, c, rs=1, t="x": {"row": r, "col": c, "rowSpan": rs, "colSpan": 1, "blocks": [{"id": f"p{r}{c}", "type": "paragraph", "text": t}]}  # noqa: E731
    tbl = {"id": "t1", "type": "table", "nRows": 4, "cells": [cell(0, 0), cell(1, 0, 2), cell(1, 1), cell(2, 1), cell(3, 0)]}
    us = pdf_map.units([{"id": "p0", "type": "paragraph", "text": "a"}, tbl])
    assert [(u["kind"], u["r0"], u["r1"]) for u in us] == [("block", None, None), ("rows", 0, 0), ("rows", 1, 2), ("rows", 3, 3)]
    assert [h["id"] for h in us[2]["heads"]] == ["p10", "p11"]


def test_rebuild_all_members_identical():
    data = SMALL.read_bytes()
    rebuilt, differ, n = verify.rebuild_all(data)
    assert not differ and n >= 3
    za, zb = (zipfile.ZipFile(io.BytesIO(x)) for x in (data, rebuilt))
    assert za.namelist() == zb.namelist()
    assert all(za.read(m) == zb.read(m) for m in za.namelist())


def test_paginate_repeated_header_row():
    """쪽마다 다시 찍힌 표 머리 행(Word·한글 반복 머리)은 그 쪽의 시작이 아니다 — 머리 아래 첫 행에서 나눈다(HAZID 42쪽·연구개발계획서 양식 31쪽)."""
    para = lambda i, t: {"id": i, "type": "paragraph", "text": t}  # noqa: E731
    cell = lambda r, c, t: {"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "blocks": [para(f"c{r}{c}", t)]}  # noqa: E731
    rows = [("구분", "구체적인 내용"), ("가나다라", "첫째 행 글"), ("마바사아", "둘째 행 글"), ("자차카타", "셋째 행 글"), ("파하거너", "넷째 행 글")]
    tbl = {"id": "t1", "type": "table", "nRows": len(rows), "cells": [cell(r, c, t) for r, row in enumerate(rows) for c, t in enumerate(row)]}
    blocks = [para("p0", "제목 문단입니다"), tbl]
    line = lambda t, x, y: {"text": t, "bbox": [x, y, x + 50, y + 10]}  # noqa: E731
    pages = [{"w": 595, "h": 842, "sheet": 0, "lines": [line("제목 문단입니다", 50, 80), line("구분", 50, 100), line("구체적인 내용", 150, 100),
                                                       line("가나다라", 50, 120), line("첫째 행 글", 150, 120), line("마바사아", 50, 140), line("둘째 행 글", 150, 140)]},
             {"w": 595, "h": 842, "sheet": 1, "lines": [line("구분", 50, 80), line("구체적인 내용", 150, 80),
                                                       line("자차카타", 50, 100), line("셋째 행 글", 150, 100), line("파하거너", 50, 120), line("넷째 행 글", 150, 120)]}]
    located = {"p0": [1], **{f"c{r}{c}": [1] for r in range(3) for c in range(2)}, **{f"c{r}{c}": [2] for r in (3, 4) for c in range(2)}}
    res = pdf_map.paginate(blocks, pages, located)
    assert res["breaks"][1] == {"page": 2, "kind": "rows", "id": "t1", "row": 3}
    assert res["checks"][0]["status"] == "repeat"
