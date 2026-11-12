"""hwp 올리기(spec_작업 ② §1) — 한글로 hwpx 로 바꿔 hwpx 작업으로 받는다. 변환 자체(한글 COM)는 시험에서 바꿔 끼운다."""
from pathlib import Path

from fastapi.testclient import TestClient

from app import pdf_render, server

HWPX = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


def test_hwp_upload_becomes_hwpx_work(monkeypatch):
    server.DOCS.clear()
    c = TestClient(server.app)
    r = c.post("/api/docs?new=1", files={"file": ("계획서.hwp", b"hwp bytes")})
    assert r.status_code == 400 and "한글" in r.json()["detail"]   # 시험은 한글 없음(NFM_PDF=off) — 까닭을 알린다
    seen = []
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "hwp_to_hwpx", lambda data, limit=None: seen.append(data) or HWPX.read_bytes())
    r = c.post("/api/docs?new=1", files={"file": ("계획서.HWP", b"hwp bytes")})
    assert r.status_code == 200 and r.json()["name"] == "계획서.hwpx" and seen == [b"hwp bytes"]
    assert server._sess(r.json()["docId"]).fmt == "hwpx"
    monkeypatch.setattr(pdf_render, "hwp_to_hwpx", lambda data, limit=None: (_ for _ in ()).throw(RuntimeError("한글이 파일을 열지 못함")))
    r = c.post("/api/docs?new=1", files={"file": ("깨진.hwp", b"??")})
    assert r.status_code == 400 and "바꾸지 못했습니다" in r.json()["detail"]
