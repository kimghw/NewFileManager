"""그림 도구(spec_그림) — 순수 로직(선명하게 · LLM 에 보낼 그림 · 소속 헤딩) · llm.call 의 그림 길 · 끝점(그림 → 표 · 캡션 · 선명하게 · 가운데 · 한 줄에).
LLM 은 부르지 않는다: llm.call 을 가짜로 바꾼다. 견본 = 연구개발계획서 양식에 그림 넷을 넣은 문서(본문 셋 · 칸 안 하나)."""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import llm, pic_tools as PT, server
from app.hwpx_doc import CAPTION, HwpxDoc

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


def _png(w=120, h=60, color=(30, 30, 30)):
    im = Image.new("RGB", (w, h), "white")
    for x in range(10, w - 10):
        im.putpixel((x, h // 2), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- 순수
def test_enhance_upscales_small_picture_and_keeps_jpeg():
    r = PT.enhance(_png(100, 50), "png", 50.0, "normal")   # 50mm × 220dpi ≈ 433px → 4배 한도
    assert r["ext"] == "png" and (r["w"], r["h"]) == (400, 200) and r["before"] == (100, 50) and r["scale"] == 4.0
    big = PT.enhance(_png(1200, 600), "png", 50.0, "strong")   # 이미 넉넉 — 크기 그대로, 또렷하게만
    assert (big["w"], big["h"]) == (1200, 600) and big["scale"] == 1.0
    buf = io.BytesIO()
    Image.new("RGB", (80, 40), "white").save(buf, "JPEG")
    j = PT.enhance(buf.getvalue(), "jpg", 30.0)
    assert j["ext"] == "jpg" and Image.open(io.BytesIO(j["data"])).format == "JPEG"


def test_for_llm_shrinks_long_side_to_png():
    r = PT.for_llm(_png(3000, 1000))
    assert r["media"] == "image/png" and (r["w"], r["h"]) == (2000, 667) and Image.open(io.BytesIO(r["data"])).size == (2000, 667)


def test_llm_call_sends_images_through_cli_stream_json(monkeypatch, tmp_path):
    """그림이 있으면 CLI 를 stream-json 입력 · 출력으로 부르고(stdin = 사용자 메시지 한 줄 — 그림 블록 + 글) 끝의 result 줄을 읽는다(② §7)."""
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("NFM_LLM_BACKEND", "cli")
    monkeypatch.setenv("NFM_CLAUDE_CLI", str(exe))
    seen = {}

    class Run:
        returncode, stderr = 0, ""
        stdout = "\n".join([json.dumps({"type": "system", "subtype": "init"}),
                            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": '"type":"result"'}]}}),
                            json.dumps({"type": "result", "subtype": "success", "is_error": False, "structured_output": {"ok": 1}, "total_cost_usd": 0.01})])

    def run(args, **kw):
        seen["args"], seen["input"] = args, kw["input"]
        return Run()
    monkeypatch.setattr(llm.subprocess, "run", run)
    out = llm.call({"type": "object"}, "글", "pic-table", images=[{"data": b"\x89PNG", "media": "image/png"}])
    assert out["data"] == {"ok": 1} and out["backend"] == "cli" and out["costUsd"] == 0.01
    a = seen["args"]
    assert a[a.index("--input-format") + 1] == "stream-json" and a[a.index("--output-format") + 1] == "stream-json" and "--verbose" in a
    msg = json.loads(seen["input"])
    blocks = msg["message"]["content"]
    assert msg["type"] == "user" and [b["type"] for b in blocks] == ["image", "text"] and blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[1]["text"].startswith("글")
    seen.clear()   # 그림이 없으면 전과 같은 길(json 출력 · 글 그대로)
    Run.stdout = json.dumps({"type": "result", "subtype": "success", "is_error": False, "structured_output": {"ok": 2}})
    assert llm.call({"type": "object"}, "글2", "pic-table")["data"] == {"ok": 2}
    assert "--input-format" not in seen["args"] and seen["args"][seen["args"].index("--output-format") + 1] == "json" and seen["input"].startswith("글2")


# ---------------------------------------------------------------- 문서
def _made():
    """양식에 그림 넷: A = 「□」(p1014) 뒤 · B = 「o」(p1016) 뒤 · C = 「-」(p1018) 뒤 · D = 표 t996 의 첫 칸 안."""
    d = HwpxDoc(PLAN.read_bytes())
    bs = d.blocks()
    cell = next(c for b in bs if b["id"] == "t996" for c in b["cells"] if c.get("blocks"))
    ids = [d.insert_image(ref, _png(400, 200), "png", width_mm=60) for ref in ("p1014", "p1016", "p1018", cell["blocks"][0]["id"])]
    return d.save(), ids


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pics")
    data, _ = _made()
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": ("그림_넷.hwpx", data, "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        pics = []
        for b in PT.H.iter_blocks(s.doc.blocks()):
            if b.get("type") == "image" and (b.get("media") or "").endswith(".png"):   # 넣은 그림(양식의 bmp 하나는 뺌)
                pics.append(b["id"])
        assert len(pics) == 4
        pics.sort(key=lambda i: s.doc.pic_info(i)["cell"])   # 본문 A · B · C(문서 차례) 다음에 칸 안 D(표 t996 은 A 보다 앞)
        yield c, d, s, pics
        server.DOCS.clear()


def _fake(monkeypatch, data):
    seen = []
    monkeypatch.setattr(llm, "status", lambda: {"available": True})
    monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: seen.append((what, content, kw)) or {"data": data, "backend": "x", "ms": 1, "costUsd": 0.0, "error": None, "model": "m", "effort": "low"})
    return seen


def _blk(s, bid):
    return next((b for b in PT.H.iter_blocks(s.doc.blocks()) if b.get("id") == bid), None)


def test_info_heading_and_template(doc):
    c, d, s, (a, b, cc, dd) = doc
    r = c.get(f"/api/docs/{d}/pics/{a}").json()
    assert r["raster"] and not r["hasCaption"] and r["inline"] and not r["cell"] and r["widthMm"] == 60.0
    assert r["heading"][:2] == ["2. 연구개발과제의 목표 및 내용", "2-1. 최종목표"] and r["heading"][-1].startswith("□"), r["heading"]
    assert r["template"] == "t996"   # 그림 앞의 가장 가까운 여러 칸 표
    assert c.get(f"/api/docs/{d}/pics/{dd}").json()["cell"] is True
    assert c.get(f"/api/docs/{d}/pics/p1014").status_code == 404   # 그림이 아닌 블록


def test_read_table_then_insert_replaces_the_picture(doc, monkeypatch):
    c, d, s, (a, b, cc, dd) = doc
    grid = {"headerRows": 0, "headerCols": 1, "footRows": 0, "rows": [{"cells": [{"text": "Ship ID", "rowSpan": 1, "colSpan": 1}, {"text": "imo1234567", "rowSpan": 1, "colSpan": 1}]},
                                                                      {"cells": [{"text": "Short ID", "rowSpan": 1, "colSpan": 1}, {"text": "0001", "rowSpan": 1, "colSpan": 1}]}]}
    seen = _fake(monkeypatch, {"tables": [grid, {"rows": []}], "caption": ["1.4 Data Channel ID 의 예시", "아래 예시에서 …"], "note": "표 둘"})
    r = c.post(f"/api/docs/{d}/pics/{a}/read-table", json={})
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["tables"]) == 1 and j["dropped"] and j["caption"][0].startswith("1.4") and j["template"] == "t996"
    what, content, kw = seen[0]
    assert what == "pic-table" and kw["images"][0]["media"] == "image/png" and "2-1. 최종목표" in content   # 그림 + 소속 헤딩이 함께
    r = c.post(f"/api/docs/{d}/pics/{a}/table", json={"template": "t996", "tables": j["tables"], "caption": j["caption"]})
    assert r.status_code == 200, r.text
    made = r.json()["made"]
    tid = made["tables"][0]
    assert _blk(s, a) is None and a in made["removed"]   # 그림은 지워짐
    t = s.doc._ids[tid]
    cap = t.find(CAPTION)
    assert cap is not None and cap.get("side") == "TOP" and len(made["caption"]) == 2
    tb = _blk(s, tid)
    assert tb["nRows"] == 2 and tb["nCols"] == 2 and [x["text"] for x in sorted(tb["cells"], key=lambda x: (x["row"], x["col"]))][:2] == ["Ship ID", "imo1234567"]
    assert [x.get("text") for x in PT.H.iter_blocks(s.doc.blocks()) if x.get("captionOf") == tid] == ["1.4 Data Channel ID 의 예시", "아래 예시에서 …"]
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and _blk(s, a) is not None and tid not in s.doc._ids or not s.doc._attached(s.doc._ids[tid])


def test_caption_from_picture_and_heading(doc, monkeypatch):
    c, d, s, (a, b, cc, dd) = doc
    seen = _fake(monkeypatch, {"caption": "< 최종목표 개념도 >", "note": "헤딩"})
    r = c.post(f"/api/docs/{d}/pics/{b}/read-caption")
    assert r.status_code == 200 and r.json()["caption"] == "< 최종목표 개념도 >"
    assert seen[0][0] == "pic-caption" and "최종목표" in seen[0][1] and seen[0][2]["images"]
    r = c.post(f"/api/docs/{d}/pics/{b}/caption", json={"caption": "< 최종목표 개념도 >"})
    assert r.status_code == 200, r.text
    assert s.doc._ids[b].find(CAPTION).get("side") == "BOTTOM"
    assert [x["text"] for x in PT.H.iter_blocks(s.doc.blocks()) if x.get("captionOf") == b] == ["< 최종목표 개념도 >"]
    assert c.get(f"/api/docs/{d}/pics/{b}").json()["hasCaption"] is True
    assert c.post(f"/api/docs/{d}/pics/{b}/read-caption").status_code == 409   # 이미 캡션이 있음
    HwpxDoc(s.doc.save()).blocks()   # 저장본을 다시 열 수 있다


def test_sharpen_preview_and_replace(doc):
    c, d, s, (a, b, cc, dd) = doc
    r = c.get(f"/api/docs/{d}/pics/{cc}/sharpen.png", params={"level": "strong"})
    assert r.status_code == 200 and r.headers["x-pixels"] == "400x200>709x354"   # 60mm × 300dpi ≈ 709px
    before = s.doc.pic_info(cc)
    r = c.post(f"/api/docs/{d}/pics/{cc}/sharpen", json={"level": "normal"})
    assert r.status_code == 200, r.text
    after = s.doc.pic_info(cc)
    assert after["media"] != before["media"] and (after["widthMm"], after["heightMm"]) == (before["widthMm"], before["heightMm"])
    org = s.doc._ids[cc].find("{http://www.hancom.co.kr/hwpml/2011/paragraph}orgSz")
    w, h = Image.open(io.BytesIO(s.doc.media(after["media"]))).size
    assert (int(org.get("width")), int(org.get("height"))) == (w * 75, h * 75) and r.json()["made"]["after"] == [w, h]
    assert c.get(f"/api/docs/{d}/pics/{cc}/sharpen.png", params={"level": "x"}).status_code == 400


def test_center_and_row(doc):
    c, d, s, (a, b, cc, dd) = doc
    with s.lock:   # 넣은 그림의 문단은 양식 그림의 문단을 본떠 이미 가운데 — 왼쪽으로 돌려 두고 본다
        s.doc.format_para([s.doc.pic_info(b)["host"]], {"align": "left"})
    assert s.doc.pic_info(b)["align"] == "left"
    r = c.post(f"/api/docs/{d}/pics/center", json={"ids": [b]})
    assert r.status_code == 200 and r.json()["made"]["centered"] == [b] and s.doc.pic_info(b)["align"] == "center"
    assert c.post(f"/api/docs/{d}/pics/center", json={"ids": [b]}).json() == {"same": True}
    assert c.post(f"/api/docs/{d}/pics/row", json={"ids": [b, dd]}).status_code == 400   # 본문과 칸 — 같은 곳이 아님
    hb, hc = s.doc.pic_info(b)["host"], s.doc.pic_info(cc)["host"]
    r = c.post(f"/api/docs/{d}/pics/row", json={"ids": [cc, b]})   # 차례는 문서 차례로(b 가 앞)
    assert r.status_code == 200, r.text
    m = r.json()["made"]
    assert m["first"] == b and m["second"] == cc and m["host"] == hb and hc in m["removed"] and m["scaled"] is None   # 60 + 60 + 3mm < 글 폭
    assert s.doc.pic_info(cc)["host"] == hb and s.doc.pic_info(b)["align"] == "center"
    row = [x for x in s.doc.blocks() if x.get("type") == "image" and x["id"] in (b, cc)]
    assert len(row) == 2 and row[0].get("inlineRow") == row[1].get("inlineRow") == b
    HwpxDoc(s.doc.save()).blocks()


def test_docx_is_refused(tmp_path, monkeypatch):
    for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp_path / "works", "NFM_RENDER": tmp_path / "render"}.items():
        monkeypatch.setenv(k, str(v))
    c = TestClient(server.app, raise_server_exceptions=False)
    r = c.post("/api/docs", files={"file": ("기술수요조사서.docx", (ROOT / "samples" / "기술수요조사서.docx").read_bytes(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/docs/{r.json()['docId']}/pics/x1").status_code == 415
