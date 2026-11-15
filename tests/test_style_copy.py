"""문서 서식 복사(spec_서식복사 ② §4~§9): 저장소의 종류 `page`·docx 운반 문서·형식마다의 검증 기록 · 문서 서식 후보 · 두 형식 검증(docx 기대값은 명세에서 · `check_page`) · 끝점(문서 서식 ·
`?format=` · name-file · docx 문서 · `{mode: "page"}`). 한글·Word·LLM 없이 — `app.style_page`·`app.style_docx`(다른 모듈)는 흉내로 물린다."""
import re
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
from app import heading_rules as R
from app import pdf_style, server, style_api, style_carrier, style_lib
from app import style_extract as X
from app import style_lib as L
from app import style_verify as V

if not any(getattr(r, "path", "") == "/api/styles" for r in server.app.routes):  # 서버가 아직 이 라우터를 안 물었으면 여기서
    server.app.include_router(style_api.router)

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, DOCX = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "기술수요조사서.docx"
PAGE = {"widthMm": 210.0, "heightMm": 297.0, "landscape": False, "marginsMm": {"l": 30.0, "r": 30.0, "t": 20.0, "b": 15.0, "header": 15.0, "footer": 15.0, "gutter": 0.0}}
FMT = {"font": "맑은 고딕", "sizePt": 11.0, "bold": False, "color": "#000000", "align": "left", "indentLeftMm": 0.0, "firstLineMm": 0.0, "lineSpacingPct": 160}
BODY = {"format": FMT, "count": 12}
BODIES = [{"key": "b1", "format": FMT, "count": 12, "chars": 400, "sample": "한글 20자"}, {"key": "b2", "format": {**FMT, "sizePt": 9.0}, "count": 3, "chars": 80, "sample": "한글 8자"}]  # 바탕 글 후보(② §12)
PAGE_KEYS = ("key", "page", "body", "sample", "losses")  # 쪽 설정 후보에서 견주는 칸 — 2차의 추출 모듈은 여기에 bodies·doubts 를 더 싣는다
SUMMARY = "A4 세로 · 여백 왼 30"
SAMPLE = "견본 첫 줄입니다"
LINE = {"type": "SOLID", "widthMm": 0.12, "color": "#000000"}
FACE = {"맑은 고딕": "MalgunGothic"}
BANDS = {"headerRows": 1, "headerCols": 0, "footRows": 0}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    yield
    R._MEMORY.clear()


@pytest.fixture()
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


@pytest.fixture()
def page_mod(monkeypatch):
    """`app.style_page` 흉내(spec_서식복사 ② §10 의 시그니처) — 어느 문서에서든 PAGE·BODY 를 읽고, 운반 문서는 빈 바탕 그대로. calls = set_page 가 받은 (page, 구역 수)."""
    sp = types.ModuleType("app.style_page")
    sp.SAMPLES, sp.calls = [SAMPLE, "견본 둘째 줄입니다", "견본 셋째 줄입니다"], []

    def clean(page):
        if not isinstance(page, dict) or not page.get("widthMm") or not page.get("heightMm"):
            raise ValueError("쪽 설정이 틀렸습니다")
        mar = page.get("marginsMm") or {}
        return {"widthMm": float(page["widthMm"]), "heightMm": float(page["heightMm"]), "landscape": bool(page.get("landscape")),
                "marginsMm": {k: float(mar.get(k) or 0) for k in ("l", "r", "t", "b", "header", "footer", "gutter")}}

    def set_page(doc, page):
        sp.calls.append((page, len(doc._sections)))
        return len(doc._sections)
    sp.clean, sp.set_page = clean, set_page
    sp.of_hwpx = lambda doc, skip=(): {"page": PAGE, "body": BODY, "bodies": BODIES, "section": 0, "losses": []}   # skip·bodies·section = 2차(② §16 — 본문 글이 가장 많은 구역 · 바탕 글 후보 상위 3)
    sp.of_docx = lambda doc, skip=(): {"page": PAGE, "body": BODY, "bodies": BODIES, "section": 0, "losses": ["docx 에서"]}
    sp.of_pdf = lambda measure: 1 / 0
    sp.summary = lambda page, body: SUMMARY
    sp.carrier = lambda page, body: (style_carrier.base(), {"fonts": ["맑은 고딕"], "losses": ["운반 문서에서"]})
    monkeypatch.setitem(sys.modules, "app.style_page", sp)
    monkeypatch.setattr(app, "style_page", sp, raising=False)
    return sp


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait(cond, seconds=5.0):
    end = time.time() + seconds
    while not cond() and time.time() < end:
        time.sleep(0.01)
    return cond()


def _by(checks):
    return {c["what"]: c for c in checks}


def _status(checks):
    return {c["what"]: c["status"] for c in checks}


def _line(chars, x, y, block=0):
    """글자 [(키, 원 글자, 모양)] → pdf_map 줄 하나(글자마다 span 하나 — tests/test_style_verify.py 의 _text_line 과 같은 꼴)."""
    out, spans = [], []
    for _, ch, f in chars:
        size = f["sizePt"]
        face = pdf_style._web_face(ch, f)[0]
        spans.append((FACE.get(face, face) + ("Bold" if f.get("bold") else ""), size, 16 if f.get("bold") else 0, int((f.get("color") or "#000000")[1:], 16)))
        out.append((ch, x, y, x + size, y + size, len(spans) - 1, bool(f.get("bold"))))
        x += size
    return {"text": "".join(c[1] for c in chars), "bbox": [out[0][1], y, x, y + out[0][4] - out[0][2]], "block": block, "chars": out, "spans": spans}


def _measure(lines, segs=(), rects=(), w=595.0, h=842.0):
    return {"count": 1, "pages": [{"w": w, "h": h, "sheet": 0, "lines": list(lines), "segs": list(segs), "rects": list(rects), "tables": [], "type3": set()}]}


# ---- 저장소: 종류 page · docx 운반 문서 · 형식마다의 검증 기록 ------------------------------------------------------------

def test_lib_page_kind_keeps_two_carriers_and_two_verify_records():
    m = L.create({"kind": "page", "name": "보고서 문서 서식", "page": PAGE, "body": BODY, "docx": {"losses": ["자동 번호", ""], "sha256": "남이 준 해시"}}, b"hwpx-1", {"carrier.docx": b"docx-1"})
    sid = m["id"]
    assert m["kind"] == "page" and m["page"] == PAGE and m["body"] == BODY and m["verify"] is None and m["verifyDocx"] is None
    assert m["docx"] == {"sha256": L.sha256(b"docx-1"), "losses": ["자동 번호"]}                         # 해시는 저장소가 그 바이트에서 낸다
    assert L.carrier(sid) == b"hwpx-1" and L.carrier(sid, fmt="docx") == b"docx-1" == L.carrier(sid, "r1", "docx") and L.get(sid) == m
    for bad in ({"kind": "page", "name": "x"}, {"kind": "page", "name": "x", "page": {**PAGE, "widthMm": 0}}, {"kind": "page", "name": "x", "page": {**PAGE, "marginsMm": {"l": 1}}}):
        with pytest.raises(ValueError):
            L.create(bad, b"c")
    with pytest.raises(ValueError):
        L.create({"kind": "page", "name": "x", "page": PAGE}, b"c", {"carrier.docx": b""})
    assert L.put_verify(sid, "r1", {"status": "ok"}, {"proof.png": b"p"}) is True
    assert L.put_verify(sid, "r1", {"status": "warn", "format": "docx"}, {"proof_docx.png": b"q"}, fmt="docx") is True and L.put_verify(sid, "r1", {"status": "ok"}, fmt="pdf") is False
    assert L.get(sid)["verify"] == {"status": "ok"} and L.get(sid)["verifyDocx"] == {"status": "warn", "format": "docx"}
    r2 = L.revise(sid, "r1", {"name": "새 이름", "docx": None, "verifyDocx": None})                      # 이름만 — 두 운반 문서·두 기록을 물려받는다(저장소가 정하는 칸은 못 바꾼다)
    assert r2["docx"] == m["docx"] and r2["verifyDocx"]["status"] == "warn" and r2["verify"] == {"status": "ok"} and L.carrier(sid, fmt="docx") == b"docx-1" and L.file(sid, "proof_docx.png") is not None
    r3 = L.revise(sid, "r2", {"docx": {"losses": ["다시 지음"]}}, None, {"carrier.docx": b"docx-2"})       # docx 만 바뀜 — 그 검증·그림만 버린다
    assert r3["docx"] == {"sha256": L.sha256(b"docx-2"), "losses": ["다시 지음"]} and r3["verifyDocx"] is None and r3["verify"] == {"status": "ok"}
    assert L.file(sid, "proof_docx.png") is None and L.file(sid, "proof.png") is not None and L.carrier(sid, fmt="docx") == b"docx-2"
    r4 = L.revise(sid, "r3", None, b"hwpx-2")                                                           # 운반 문서가 바뀌었는데 docx 를 안 줌 → docx 없음
    assert r4["docx"] is None and r4["verifyDocx"] is None and L.carrier(sid, fmt="docx") is None and L.carrier(sid) == b"hwpx-2" and L.listing()["broken"] == []


def test_lib_put_docx_attaches_to_an_old_template(tmp_path):
    m = L.create({"kind": "table", "name": "옛 표", "rows": 2, "cols": 2}, b"c1")                          # docx 없이 저장된 옛 템플릿
    sid = m["id"]
    assert m["docx"] is None and L.carrier(sid, fmt="docx") is None
    assert L.put_docx(sid, "r9", b"d") is False and L.put_docx(sid, "r1", b"") is False and L.put_docx("0" * 12, "r1", b"d") is False
    r2 = L.revise(sid, "r1", {"name": "이름만"})
    assert L.put_docx(sid, "r1", b"docx", ["뺀 것"]) is True                                             # 옛 revision 에 붙이면 운반 문서가 같은 지금 revision 에도
    g = L.get(sid)
    assert g["revision"] == "r2" and g["docx"] == {"sha256": L.sha256(b"docx"), "losses": ["뺀 것"]} and g["updated"] == r2["updated"]
    assert L.carrier(sid, fmt="docx") == b"docx" == L.carrier(sid, "r1", "docx")
    assert L.put_docx(sid, "r1", b"other") is True and L.carrier(sid, fmt="docx") == b"docx"            # 성한 것이 있으면 그대로
    (tmp_path / "styles" / sid / "revisions" / "r2" / "carrier.docx").write_bytes(b"altered")           # docx 가 바뀜 — 템플릿은 성하고 docx 만 없는 것이 된다
    assert L.carrier(sid, fmt="docx") is None and L.get(sid) is not None and L.listing()["broken"] == []
    assert L.put_docx(sid, "r2", b"again") is True and L.carrier(sid, fmt="docx") == b"again"


# ---- 문서 서식 후보(style_extract) ----------------------------------------------------------------------------------

def test_page_candidates_and_build_pick(page_mod):
    got = X.page_candidates("hwpx", object())
    assert len(got) == 1 and {k: got[0][k] for k in PAGE_KEYS} == {"key": "page", "page": PAGE, "body": BODY, "sample": SUMMARY, "losses": []}
    assert X.page_candidates("pdf", {}) == [] and X.page_candidates("txt", object()) == []           # 추출이 실패해도(of_pdf 가 예외) 예외를 내지 않는다
    entry = {"name": "보고서 양식.docx", "format": "docx", "fidelity": "summary", "tables": [], "texts": [], "pages": X.page_candidates("docx", object()), "_sha256": "s" * 64}
    data, meta = X.build_pick(entry, {"kind": "page", "key": "page"})
    assert data == style_carrier.base() and (meta["kind"], meta["name"], meta["fidelity"], meta["page"], meta["body"]) == ("page", "보고서 양식 문서 서식", "summary", PAGE, BODY)
    assert meta["losses"] == ["docx 에서", "운반 문서에서"] and meta["requirements"] == {"fonts": ["맑은 고딕"]}
    assert meta["source"] == {"name": "보고서 양식.docx", "format": "docx", "work": None, "block": None, "page": None, "sha256": "s" * 64}
    assert X.build_pick(entry, {"kind": "page", "key": "page", "name": " 내  서식 "})[1]["name"] == "내 서식"
    for bad in ({"kind": "page", "key": "nope"}, {"kind": "chart", "key": "page"}):
        with pytest.raises(ValueError):
            X.build_pick(entry, bad)
    assert X.page_name("가" * 80 + ".hwpx").endswith(" 문서 서식") and len(X.page_name("가" * 80 + ".hwpx")) == X.NAME_MAX
    assert L.create({**meta, "note": ""}, data)["kind"] == "page"                                      # 저장소가 받는 꼴이다


def test_page_candidates_without_the_module(monkeypatch):
    monkeypatch.delattr(app, "style_page", raising=False)
    monkeypatch.setitem(sys.modules, "app.style_page", None)                                           # 그 모듈이 아직 없다 — 그 기능만 빠진다
    assert X.page_candidates("hwpx", object()) == []
    with pytest.raises(ValueError):
        X.build_page({"page": PAGE})
    assert style_carrier.view(style_carrier.base(), {"kind": "page", "page": PAGE, "body": None})["summary"] == ""


# ---- 검증: 대상 해시 · 문서 서식(page-v1) ---------------------------------------------------------------------------------

def test_subject_hash_page_and_docx():
    meta = {"kind": "page", "carrierSha256": "a" * 64, "page": PAGE, "body": BODY, "docx": {"sha256": "d" * 64}}
    h, hd = V.subject_hash(meta), V.subject_hash(meta, "docx")
    assert V.subject_hash({**meta, "name": "다른 이름"}) == h and V.subject_hash({**meta, "page": {**PAGE, "widthMm": 297.0}}) != h and V.subject_hash({**meta, "body": None}) != h
    assert hd != h and V.subject_hash({**meta, "docx": {"sha256": "e" * 64}}, "docx") != hd and V.subject_hash({**meta, "docx": {"sha256": "e" * 64}}) == h   # docx 가 바뀌어도 hwpx 쪽 해시는 그대로
    table = {"carrierSha256": "a" * 64, "bands": BANDS}
    assert V.subject_hash({**table, "kind": "table", "page": PAGE, "docx": {"sha256": "d" * 64}}) == V.subject_hash(table)   # 표·글 서식의 해시는 전과 같다


def _page_measure(exp, left=None, top=None, size=11.0, face=None, w=210.0, h=297.0, text=SAMPLE):
    f = {**FMT, "sizePt": size, **({"font": face} if face else {})}
    x, y = (exp["leftMm"] if left is None else left) * V.PT_MM, ((exp["topMm"] or 0.0) if top is None else top) * V.PT_MM
    return _measure([_line([(ch if V.key_text(ch) else "", ch, f) for ch in text], x, y)], w=w * V.PT_MM, h=h * V.PT_MM)


def test_check_page_measures_size_first_line_and_body_font(monkeypatch):
    monkeypatch.setattr(V, "page_sample", lambda: SAMPLE)
    meta = {"kind": "page", "page": PAGE, "body": BODY}
    exp = V.expect_page(meta)
    assert (exp["widthMm"], exp["heightMm"], exp["leftMm"], exp["topMm"], exp["slackMm"], exp["sample"]) == (210.0, 297.0, 30.0, 20.0, 0.0, SAMPLE)   # 위 여백 t = 종이 끝에서 본문까지(머리말 몫을 품은 값)
    checks = V.check_page(exp, _page_measure(exp))
    assert [c["what"] for c in checks] == [*V.PAGE_CHECKS, "marginRightBottom", "headerFooter"]
    st = _status(checks)
    assert all(st[k] == "pass" for k in V.PAGE_CHECKS) and st["marginRightBottom"] == st["headerFooter"] == "unsupported" and V.summarize(checks, 1)[0] == "ok"
    assert _status(V.check_page(exp, _page_measure(exp, w=297.0, h=210.0)))["pageSize"] == "fail"
    assert _status(V.check_page(exp, _page_measure(exp, left=35.0)))["marginLeft"] == "fail" and _status(V.check_page(exp, _page_measure(exp, left=31.0)))["marginLeft"] == "pass"
    assert _status(V.check_page(exp, _page_measure(exp, top=40.0)))["marginTop"] == "fail" and _status(V.check_page(exp, _page_measure(exp, size=9.0)))["fontSize"] == "fail"
    sub = V.check_page(exp, _page_measure(exp, face="Gulim"))                                          # 대체 글꼴 — 실패가 아니라 경고
    assert _status(sub)["fontFace"] == "unknown" and V.summarize(sub, 1)[0] == "warn"
    other = _status(V.check_page(exp, _page_measure(exp, text="다른 글입니다")))                        # 못 잰 것을 통과로 덮지 않는다
    assert other["pageSize"] == "pass" and {other[k] for k in V.PAGE_CHECKS[1:]} == {"unknown"}
    bare = V.check_page({**exp, "format": None}, _page_measure(exp))                                   # 바탕 글 모양이 없는 문서 서식(본문 글이 모두 표 안) — 글 모양은 「재지 못함」, 쪽·여백은 잰다
    assert _status(bare)["fontSize"] == _status(bare)["fontFace"] == "unsupported" and _status(bare)["marginLeft"] == _status(bare)["marginTop"] == "pass" and V.summarize(bare, 1)[0] == "ok"
    assert _status(V.check_page({**exp, "format": None}, _page_measure(exp, left=35.0)))["marginLeft"] == "fail"
    assert V.expect_page(meta)["sizeTolMm"] == V.PAGE_TOL_HWPX and V.expect_page(meta, "docx")["sizeTolMm"] == V.PAGE_TOL                       # 한글 PDF 의 쪽 크기는 조금 작다(실측)
    assert _status(V.check_page(exp, _page_measure(exp, h=296.3)))["pageSize"] == "pass" and _status(V.check_page({**exp, "sizeTolMm": V.PAGE_TOL}, _page_measure(exp, h=296.3)))["pageSize"] == "fail"
    assert {v for k, v in _status(V.check_page(exp, {"count": 0, "pages": []})).items() if k in V.PAGE_CHECKS} == {"unknown"}
    # docx: 같은 명세 · 줄 간격이 100% 를 넘는 만큼 첫 줄이 내려와도 통과(Word 는 늘어난 줄 높이를 글 위에 둔다)
    dx = V.expect_page(meta, "docx")
    assert dx["topMm"] == 20.0 and dx["slackMm"] > 2.0 and "lineSpacingPct" in dx["format"]
    assert _status(V.check_page(dx, _page_measure(dx, top=22.5)))["marginTop"] == "pass" and _status(V.check_page(dx, _page_measure(dx, top=30.0)))["marginTop"] == "fail"
    assert _status(V.check_page({**dx, "topMm": None}, _page_measure(exp)))["marginTop"] == "unknown"
    assert V.expect_page({"kind": "page"}) is None and V.expect_page({"kind": "page", "page": PAGE, "body": None})["format"] is None


# ---- 검증: docx 쪽 기대값은 명세에서 ---------------------------------------------------------------------------------

def _spec():
    cell = lambda r, c, text, fill=None, edges=None, **f: {"row": r, "col": c, "rowSpan": 1, "colSpan": 1, "text": text, "fill": fill,   # noqa: E731
                                                            "edges": dict.fromkeys("trbl", LINE) if edges is None else edges, "format": {**FMT, "sizePt": 10.0, **f}}
    return {"rows": 2, "cols": 2, "bands": BANDS, "widthsMm": [40.0, 60.0], "cells": [
        cell(0, 0, "구분", "#D9E2F3", bold=True, script="sup", fontLatin="Arial"), cell(0, 1, "금액", "#D9E2F3", bold=True),
        cell(1, 0, "가나다"), cell(1, 1, "0", edges={"t": LINE, "l": LINE, "r": LINE, "b": {"type": "NONE", "widthMm": 0.1, "color": "#000000"}})]}


def _word_page(exp, left=70.0, top=90.0, widths=None):
    """Word 꼴로 그린 쪽(잰 값) — 칸은 격자(열 폭 widths pt · 행 높이 24pt)대로: 음영 = 칸 상자 채움 · 괘선 = 변마다 선 0.5pt · 글 = 칸 안 한 줄."""
    wd = widths or exp["widthsPt"]
    xs, ys = [left + sum(wd[:k]) for k in range(exp["cols"] + 1)], [top + 24.0 * r for r in range(exp["rows"] + 1)]
    segs, rects, lines = [], [], []
    for i, c in enumerate(exp["cells"]):
        x0, y0, x1, y1 = xs[c["col"]], ys[c["row"]], xs[c["col"] + c["colSpan"]], ys[c["row"] + c["rowSpan"]]
        if c["fill"]:
            rects.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "fill": V._channels(c["fill"])})
        for side, e in c["edges"].items():
            if e:
                at, lo, hi = V._side_span((x0, y0, x1, y1), side)
                segs.append({"dir": "h", "x0": lo, "y0": at, "x1": hi, "y1": at, "w": 0.5, "color": (0, 0, 0), "dashed": False} if side in "tb" else
                            {"dir": "v", "x0": at, "y0": lo, "x1": at, "y1": hi, "w": 0.5, "color": (0, 0, 0), "dashed": False})
        if c["chars"]:
            lines.append(_line(c["chars"], x0 + 4, y0 + 4, block=i))
    return _measure(lines, segs, rects)


def test_docx_table_expectation_comes_from_the_spec_and_uses_measured_columns():
    exp = V.expect_table_spec(_spec())
    assert (exp["rows"], exp["cols"]) == (2, 2) and exp["widthsPt"] == pytest.approx([40 * V.PT_MM, 60 * V.PT_MM]) and all(c["widthPt"] == 0 for c in exp["cells"])
    f = exp["cells"][0]["chars"][0][2]
    assert f["bold"] is True and "script" not in f and "fontLatin" not in f and exp["cells"][3]["edges"]["b"] is None   # docx 로 안 옮기는 값은 기대하지 않는다 · NONE 선 = 선 없음
    assert V.expect_table_spec({"rows": 1, "cols": 1, "cells": []}) is None and V.expect_table_spec(None) is None
    checks = V.check_table_docx(exp, _word_page(exp))
    st = _status(checks)
    assert [c["what"] for c in checks][:len(V.TABLE_CHECKS)] == list(V.TABLE_CHECKS) and st["lineWidth"] == "unsupported"   # 선 굵기는 Word 에서 견주지 않는다(통과가 아니라 「재지 못함」)
    assert {st[k] for k in V.TABLE_CHECKS if k != "lineWidth"} == {"pass"} and V.summarize(checks, 1)[0] == "ok"
    wide = _status(V.check_table_docx(exp, _word_page(exp, widths=[w * 1.05 for w in exp["widthsPt"]])))    # 폭이 5% 넓다 — 표 폭만 fail, 칸 자리는 잰 열 경계로 잡는다
    assert wide["width"] == "fail" and wide["text"] == wide["fill"] == wide["edge"] == wide["fontSize"] == "pass"
    off = copy_fill(exp, "#FFC000")
    assert _status(V.check_table_docx(off, _word_page(exp)))["fill"] == "fail"
    # 세로선·음영이 없어 열 경계를 못 세고 표 폭도 명세와 다르다 — 자리에 기대는 검사는 unknown(지어낸 자리로 fail 을 내지 않는다)
    bare = {**exp, "cells": [{**c, "fill": None, "edges": {"t": LINE, "b": LINE, "l": None, "r": None}} for c in exp["cells"]]}
    lost = V.check_table_docx(bare, _word_page(bare, widths=[w * 1.2 for w in bare["widthsPt"]]))
    ls = _status(lost)
    assert ls["width"] == "fail" and ls["text"] == "pass" and ls["fill"] == ls["edge"] == ls["fontSize"] == "unknown" and "칸 자리를 견주지 않음" in _by(lost)["edge"]["note"]
    nowidth = V.expect_table_spec({**_spec(), "widthsMm": None})                                           # 명세에 열 폭이 없다 — 표 폭은 unknown, 나머지는 잰 열 경계로
    nw = _status(V.check_table_docx(nowidth, _word_page(exp)))
    assert nw["width"] == "unknown" and nw["text"] == nw["fill"] == nw["edge"] == "pass"


def copy_fill(exp, fill):
    return {**exp, "cells": [{**c, "fill": fill} if i == 0 else c for i, c in enumerate(exp["cells"])]}


def test_docx_text_items_expectation():
    items = [{"key": "i1", "sample": "1. 견본 글입니다", "marker": {"mode": "literal"}, "format": {**FMT, "sizePt": 14.0, "fontLatin": "Arial", "wordBreak": "char"}},
             {"key": "i2", "sample": "- 견본 글 둘입니다", "marker": {"mode": "none"}, "format": {**FMT, "indentLeftMm": 10.0, "firstLineMm": -5.0}},
             {"key": "i3", "sample": "견본 글 셋입니다", "marker": {"mode": "auto"}, "format": dict(FMT)}]
    exp = V.expect_text_items(items, 25.0)
    assert exp["leftMm"] == 25.0 and exp["metaItems"] == 3 and [i["auto"] for i in exp["items"]] == [False, False, True] and set(exp["items"][0]["format"]) == set(FMT)   # docx 로 옮기는 값만
    assert [i["text"] for i in exp["items"]] == [i["sample"] for i in items] and [i["key"] for i in exp["items"]] == ["i1", "i2", "i3"]
    lines = []
    for n, it in enumerate(exp["items"]):
        f = it["format"]
        x = (exp["leftMm"] + f["indentLeftMm"] + max(f["firstLineMm"], 0)) * V.PT_MM
        lines.append(_line([(ch if V.key_text(ch) else "", ch, f) for ch in it["text"]], x, 100.0 + 30 * n, block=n))
    by = _by(V.check_text(exp, _measure(lines)))
    assert by["text"]["pass"] == 3 and by["fontSize"]["fail"] == 0 and (by["indent"]["pass"], by["indent"]["unknown"], by["indent"]["fail"]) == (2, 1, 0)   # 내어쓰기는 한글과 같은 자리 · 자동 번호의 왼끝은 unknown
    assert V.expect_text_items([]) is None and V.expect_text_items(None) is None


def test_run_docx_without_word_is_none():
    rec, files = V.run_docx(b"docx", b"hwpx", {"kind": "page", "revision": "r2", "page": PAGE})
    assert rec["status"] == "none" and files == {} and rec["format"] == "docx" and rec["renderer"] == {"name": "Word"} and rec["profile"] == "page-v1" and "Word" in rec["note"]
    assert rec["revision"] == "r2" and len(rec["subjectHash"]) == 64 and rec["checks"] == []
    assert V.run(b"", {"kind": "page"})[0]["profile"] == "page-v1" and "format" not in V.run(b"", {"kind": "table"})[0] and V.run_docx(b"", None, None)[0]["status"] == "none"


def test_start_verifies_hwpx_then_docx(monkeypatch):
    fake = types.ModuleType("app.style_lib")
    meta, events, docx, seen, gate = {"id": "s1", "revision": "r1", "kind": "table", "carrierSha256": "d" * 64}, [], {}, [], threading.Event()
    fake.get = lambda sid: meta
    fake.carrier = lambda sid, rid=None, fmt="hwpx": docx.get(rid) if fmt == "docx" else b"hwpx"
    fake.put_docx = lambda sid, rid, data, losses=None: events.append(("docx", rid, data, losses)) or docx.__setitem__(rid, data) or True
    fake.put_verify = lambda sid, rid, record, files=None, fmt="hwpx": events.append(("verify", fmt, record["status"], sorted(files or {}))) or True
    fake.pin, fake.unpin = (lambda sid, rid: True), (lambda sid, rid: None)
    monkeypatch.setitem(sys.modules, "app.style_lib", fake)
    monkeypatch.setattr(app, "style_lib", fake, raising=False)

    def run(carrier, meta, force=False):
        seen.append(V.pending("s1"))
        gate.wait(5)
        return {"status": "ok", "checks": []}, {"proof.png": b"p"}

    def run_docx(data, carrier, meta, force=False):
        seen.append((V.pending("s1"), data, meta["docx"]["sha256"] == L.sha256(data)))
        return {"status": "warn", "format": "docx", "checks": []}, {"proof_docx.png": b"q"}
    monkeypatch.setattr(V, "run", run)
    monkeypatch.setattr(V, "run_docx", run_docx)
    monkeypatch.setattr(V, "build_docx", lambda meta, carrier: (b"built", ["자동 번호"]))
    assert V.start("s1") == {"status": "running", "revision": "r1"} and _wait(lambda: seen) and V.pending("s1") == ("hwpx", "docx")
    gate.set()
    assert _wait(lambda: not V.running("s1")) and V.pending("s1") == ()
    assert seen == [("hwpx", "docx"), (("docx",), b"built", True)]                                      # 한글 → Word 차례 · 도는 동안 남은 형식
    assert events == [("verify", "hwpx", "ok", ["proof.png"]), ("docx", "r1", b"built", ["자동 번호"]), ("verify", "docx", "warn", ["proof_docx.png"])]   # docx 가 없으면 지어 붙인 뒤 잰다
    events.clear()
    assert V.start("s1", formats=["docx"])["status"] == "running" and _wait(lambda: not V.running("s1"))
    assert events == [("verify", "docx", "warn", ["proof_docx.png"])]                                   # 고른 형식만 · 이미 있는 docx 는 다시 짓지 않는다
    with pytest.raises(ValueError):
        V.start("s1", formats=["pdf"])
    monkeypatch.setattr(V, "build_docx", lambda meta, carrier: None)                                   # 못 지으면 verifyDocx 는 비운 채(docx 서식이 없다)
    docx.clear()
    events.clear()
    assert V.start("s1")["status"] == "running" and _wait(lambda: not V.running("s1")) and events == [("verify", "hwpx", "ok", ["proof.png"])]


# ---- 끝점 ----------------------------------------------------------------------------------------------------------

def test_api_page_style_is_saved_in_two_formats(client, page_mod, monkeypatch):
    built = []

    def build(meta, carrier):
        built.append(meta["kind"])
        return b"DOCX-" + meta["kind"].encode(), ["자동 번호"]
    mods = {"style_extract": X, "style_docx": types.SimpleNamespace(build=build)}
    monkeypatch.setattr(style_api, "_mod", lambda n: mods.get(n))                                      # 검증 모듈 없이(스레드가 시험 사이로 새지 않게)
    d = _upload(client, SMALL)
    c = client.post(f"/api/docs/{d}/styles/candidates", json={}).json()
    assert len(c["pages"]) == 1 and {k: c["pages"][0][k] for k in PAGE_KEYS} == {"key": "page", "page": PAGE, "body": BODY, "sample": SUMMARY, "losses": []}
    assert (c["format"], c["fidelity"]) == ("hwpx", "native") and c["stage2"] in ("script", False) and isinstance(c["paras"], list) and isinstance(c["covers"], list)
    r = client.post(f"/api/docs/{d}/styles", json={"kind": "page"})
    assert r.status_code == 201, r.text
    m = r.json()
    sid = m["id"]
    assert (m["kind"], m["name"], m["fidelity"], m["page"], m["body"]) == ("page", "기술수요조사서 문서 서식", "native", PAGE, BODY) and m["source"]["block"] is None and m["source"]["format"] == "hwpx"
    assert m["docx"] == {"sha256": style_lib.sha256(b"DOCX-page"), "losses": ["자동 번호"]} and m["verify"] is None and m["verifyDocx"] is None and built == ["page"]
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True                                     # 문서는 안 바뀐다
    got = client.get("/api/styles").json()
    assert got["pdfDocx"] is False and (got["styles"][0]["kind"], got["styles"][0]["docx"], got["styles"][0]["verifyDocx"]) == ("page", True, None)
    full = client.get(f"/api/styles/{sid}").json()
    assert (full["view"]["page"], full["view"]["body"], full["view"]["summary"]) == (PAGE, BODY, SUMMARY) and full["docx"]["losses"] == ["자동 번호"] and "viewError" not in full
    car = client.get(f"/api/styles/{sid}/carrier?format=docx")
    assert car.status_code == 200 and car.content == b"DOCX-page" and ".docx" in car.headers["content-disposition"] and "wordprocessingml" in car.headers["content-type"]
    assert client.get(f"/api/styles/{sid}/carrier").headers["content-type"] == "application/hwp+zip" and client.get(f"/api/styles/{sid}/carrier?format=pdf").status_code == 400
    assert client.get(f"/api/styles/{sid}/proof.png?format=docx").status_code == 404
    assert style_lib.put_verify(sid, "r1", {"status": "warn", "format": "docx", "coverage": {"pass": 1}}, {"proof_docx.png": b"\x89PNG-d"}, fmt="docx") is True
    assert client.get(f"/api/styles/{sid}/proof.png?format=docx").content == b"\x89PNG-d" and client.get(f"/api/styles/{sid}/proof.png").status_code == 404
    assert client.get("/api/styles").json()["styles"][0]["verifyDocx"] == {"status": "warn", "coverage": {"pass": 1}, "stale": False}
    p = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r1", "name": "보고서 쪽", "note": "A4"})   # 문서 서식은 이름·메모만
    assert p.status_code == 200 and (p.json()["name"], p.json()["note"], p.json()["revision"]) == ("보고서 쪽", "A4", "r2") and p.json()["docx"] == m["docx"] and p.json()["verifyDocx"]["status"] == "warn"
    for bad in ({"bands": {"headerRows": 1}}, {"items": [{"key": "i1"}]}, {"blueprint": {"cells": []}}):
        r = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r2", **bad})
        assert r.status_code == 400 and "이름·메모만" in r.json()["detail"], r.text
    old = style_lib.create({"kind": "page", "name": "옛 것", "page": PAGE, "body": None}, style_carrier.base())   # docx 없이 저장된 옛 템플릿 — 내려받을 때 지어 붙인다
    car = client.get(f"/api/styles/{old['id']}/carrier?format=docx")
    assert car.status_code == 200 and car.content == b"DOCX-page" and style_lib.get(old["id"])["docx"]["sha256"] == style_lib.sha256(b"DOCX-page") and style_lib.get(old["id"])["revision"] == "r1"
    mods.pop("style_docx")                                                                             # docx 모듈이 없으면: 저장은 그대로 docx null · 내려받기는 422
    lone = client.post(f"/api/docs/{d}/styles", json={"kind": "page", "name": "docx 없이"}).json()
    assert lone["docx"] is None and client.get(f"/api/styles/{lone['id']}/carrier?format=docx").status_code == 422 and client.get(f"/api/styles/{lone['id']}/carrier").status_code == 200


def test_api_apply_page_to_hwpx(client, page_mod, monkeypatch):
    monkeypatch.setattr(style_api, "_mod", lambda n: None)
    sid = style_lib.create({"kind": "page", "name": "쪽", "page": PAGE, "body": BODY}, style_carrier.base())["id"]
    tab = style_lib.create({"kind": "table", "name": "표", "rows": 2, "cols": 2}, style_carrier.base())["id"]
    d = _upload(client, SMALL)
    r = client.post(f"/api/docs/{d}/styles/{sid}/apply", json={"mode": "page"})
    assert r.status_code == 200, r.text
    assert page_mod.calls and page_mod.calls[-1][0] == PAGE and r.json()["paged"] == {"sections": page_mod.calls[-1][1]} and r.json()["undo"] == 1   # 구조 편집 한 번(실행 취소 1개)
    assert "styleApply" in [e["kind"] for e in client.get(f"/api/works/{d}/log").json()["events"]]
    assert client.post(f"/api/docs/{d}/styles/{tab}/apply", json={"mode": "page"}).status_code == 400            # 문서 서식이 아닌 것
    assert client.post(f"/api/docs/{d}/styles/ffffffffffff/apply", json={"mode": "page"}).status_code == 404
    assert client.post(f"/api/docs/{d}/styles/{sid}/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 400   # 문서 서식을 표로 쓸 수 없다
    assert len(page_mod.calls) == 1


def test_api_docx_document_candidates_save_and_format(client, monkeypatch):
    monkeypatch.setattr(style_api, "_mod", lambda n: X if n == "style_extract" else None)
    d = _upload(client, DOCX)
    c = client.post(f"/api/docs/{d}/styles/candidates", json={})
    assert c.status_code == 200, c.text
    c = c.json()
    assert (c["format"], c["fidelity"], c["stage2"]) == ("docx", "summary", False) and [(t["rows"], t["cols"]) for t in c["tables"]] == [(20, 6)] and c["texts"] == [] and c["paras"]   # 파일 추출과 같은 규칙 — docx 의 글은 레벨 없는 문단 묶음(paras: spec_서식복사 ② §12)
    para = c["paras"][0]["items"][0]["para"]
    r = client.post(f"/api/docs/{d}/styles", json={"kind": "text", "paras": [para, para]})
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["kind"], m["fidelity"], m["source"]["format"], m["source"]["block"], len(m["items"])) == ("text", "summary", "docx", para, 1)   # 서식이 같은 문단은 하나로
    assert m["items"][0]["origin"]["para"] == para and m["items"][0]["level"] is None and m["docx"] is None
    assert client.post(f"/api/docs/{d}/styles", json={"kind": "text", "paras": ["p99999"]}).status_code == 404
    assert client.post(f"/api/docs/{d}/styles", json={"kind": "text", "paras": []}).status_code == 400
    # 문단에 입히기 — 템플릿 항목의 서식 요약을 덮는다(글은 그대로 · 실행 취소 1개)
    data, items = style_carrier.from_text_spec([{"sample": "견본", "format": {"sizePt": 23.0, "bold": True, "align": "center"}}])
    tid = style_lib.create({"kind": "text", "name": "큰 글", "items": items, "source": {"format": "docx"}}, data)["id"]
    before = next(b for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["id"] == para)
    r = client.post(f"/api/docs/{d}/styles/{tid}/apply", json={"mode": "format", "item": "i1", "paras": [para]})
    assert r.status_code == 200, r.text
    after = next(b for b in r.json()["tops"]["blocks"] if b["id"] == para)
    assert r.json()["formatted"] == {"paras": 1} and r.json()["undo"] == 1 and after["text"] == before["text"]
    assert (after["format"]["sizePt"], after["format"]["bold"], after["format"]["align"]) == (23.0, True, "center")
    assert client.post(f"/api/docs/{d}/styles/{tid}/apply", json={"mode": "format", "item": "i9", "paras": [para]}).status_code == 400
    assert client.post(f"/api/docs/{d}/styles/{tid}/apply", json={"mode": "tableBlank", "after": para}).status_code == 400   # 글 서식으로 표를 넣을 수 없다


def test_api_docx_blank_table_with_the_real_docx_builder(client, monkeypatch):
    """`app.style_docx`(다른 모듈)가 있으면 실제로 물려 본다 — docx 문서에서 저장한 표 서식을 그 문서에 빈 표로 넣는다. 없으면 건너뜀."""
    sd = pytest.importorskip("app.style_docx")
    monkeypatch.setattr(style_api, "_mod", lambda n: sd if n == "style_docx" else None)
    d = _upload(client, DOCX)
    tid = max((b for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["type"] == "table"), key=lambda b: len(b["cells"]))["id"]
    r = client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": tid})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["docx"] and len(m["docx"]["sha256"]) == 64 and client.get(f"/api/styles/{m['id']}/carrier?format=docx").content[:2] == b"PK"
    r = client.post(f"/api/docs/{d}/styles/{m['id']}/apply", json={"mode": "tableBlank", "after": tid})
    assert r.status_code == 200, r.text
    made = next(b for b in r.json()["tops"]["blocks"] if b["id"] == r.json()["made"]["table"])
    labels = {tuple(rc) for rc in m["labels"]}
    assert (r.json()["made"]["rows"], r.json()["made"]["cols"]) == (m["rows"], m["cols"]) and r.json()["undo"] == 1
    assert all(not c["text"].strip() or (c["row"], c["col"]) in labels for c in made["cells"])           # 채울 칸은 비고 라벨만 남는다


def test_api_name_file_names_held_candidates(client, monkeypatch):
    entry = {"name": "보고서.pdf", "format": "pdf", "tables": [{"key": "f:1", "rows": 3, "cols": 2}], "texts": [],
             "pages": [{"key": "page", "page": PAGE, "body": None, "sample": "A4", "losses": []}], "_specs": {}}
    seen = []

    def name(cands, job=None):  # job = 「문서 서식 복사」 의 할 일 프롬프트(끝점이 붙인다 — spec_서식복사 ② §6)
        seen.append(sorted(cands))
        return {"tables": {"f:1": {"name": "예산표", "keep": True, "bands": BANDS, "bandsChanged": False}}, "texts": {}, "note": "하나", "call": {"backend": "api", "error": None},
                "prompt": "긴 프롬프트", "response": {}}
    fake = types.SimpleNamespace(name=name, held=lambda token: entry if token == "tok" else None)
    monkeypatch.setattr(style_api, "_mod", lambda n: fake if n == "style_extract" else None)
    assert client.post("/api/styles/name-file", json={"token": "tok"}).status_code == 503              # LLM 꺼짐
    monkeypatch.setattr("app.llm.status", lambda: {"available": True})
    assert client.post("/api/styles/name-file", json={"token": "gone"}).status_code == 410
    r = client.post("/api/styles/name-file", json={"token": "tok"})
    assert r.status_code == 200, r.text
    assert r.json() == {"tables": [{"key": "f:1", "rows": 3, "cols": 2, "name": "예산표", "keep": True, "bands": BANDS, "bandsChanged": False}], "texts": [], "paras": [], "covers": [],
                        "pages": [{**entry["pages"][0], "name": "보고서 문서 서식", "keep": True}], "note": "하나", "call": {"backend": "api", "error": None},
                        "calls": [{"backend": "api", "error": None}]}   # 옛 `name` 은 문서 서식을 안 묻는다 — 추천 · paras·covers·calls = ② §16
    assert seen == [["covers", "pages", "paras", "tables", "texts"]]
    monkeypatch.setattr(style_api, "_mod", lambda n: None)
    assert client.post("/api/styles/name-file", json={"token": "tok"}).status_code == 501


def test_api_verify_takes_formats_and_shows_each_format(client, monkeypatch):
    started = []
    fake = types.SimpleNamespace(start=lambda s, force=False, formats=None: started.append((force, formats)) or {"status": "running", "revision": "r1"},
                                 running=lambda s: True, pending=lambda s: ("docx",), subject_hash=lambda meta, fmt="hwpx": "h")
    monkeypatch.setattr(style_api, "_mod", lambda n: fake if n == "style_verify" else None)
    sid = style_lib.create({"kind": "page", "name": "쪽", "page": PAGE}, style_carrier.base())["id"]
    assert client.post(f"/api/styles/{sid}/verify", json={"formats": ["docx"], "force": False}).status_code == 202 and started[-1] == (False, ["docx"])
    assert client.post(f"/api/styles/{sid}/verify").status_code == 202 and started[-1] == (True, None)   # 형식을 안 고르면 둘 다(검증 모듈의 기본)
    for bad in ([], ["pdf"], "docx"):
        assert client.post(f"/api/styles/{sid}/verify", json={"formats": bad}).status_code == 400, bad
    full = client.get(f"/api/styles/{sid}").json()
    assert full["verify"] is None and full["verifyDocx"] == {"stale": False, "status": "running"}        # 형식마다 — 한글은 끝났고 Word 가 도는 중
    assert client.get("/api/styles").json()["styles"][0]["verifyDocx"] == {"status": "running", "coverage": None, "stale": False}


def test_api_same_look_is_saved_once(client, monkeypatch):
    """같은 서식은 한 번만(spec_서식복사 ② §4 「같은 서식은 한 번만」): 같은 표를 다시 저장하면 있던 템플릿을 `existing: true` 로 돌려주고 보관함에 겹쳐 쌓지 않는다 — 띠 수가 다르면 다른 서식이다."""
    pytest.importorskip("app.style_docx")
    real = style_api._mod
    monkeypatch.setattr(style_api, "_mod", lambda n: None if n == "style_verify" else real(n))        # 검증 스레드 없이
    d = _upload(client, SMALL)
    tid = client.post(f"/api/docs/{d}/styles/candidates", json={}).json()["tables"][0]["table"]
    a = client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": tid, "name": "첫 이름"}).json()
    b = client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": tid, "name": "둘째 이름"}).json()
    assert a["docx"] and "existing" not in a and (b["id"], b["name"], b.get("existing")) == (a["id"], "첫 이름", True)
    bands = {**a["bands"], "headerRows": a["bands"]["headerRows"] + 1}
    c = client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": tid, "bands": bands}).json()
    assert c["id"] != a["id"] and "existing" not in c
    assert len(client.get("/api/styles").json()["styles"]) == 2


def test_api_source_doc_record_and_seen_in(client, monkeypatch):
    """원본 문서 기록(spec_서식복사 ② §17 — 사용자 "어떤 문서에서 추출한 건지 정보를 넣어줘 … 에이전트가 사용할때 참조할 수 있도록"): 저장한 서식에 문서 이름·작업·프로젝트·TASK·라운드·자리·때가 남고,
    같은 서식이 **다른 문서**에서 또 나오면 새로 저장하지 않고 그 문서를 `seenIn` 에 남긴다(같은 문서는 다시 안 적는다)."""
    pytest.importorskip("app.style_docx")
    from app.hwpx_doc import HwpxDoc
    real = style_api._mod
    monkeypatch.setattr(style_api, "_mod", lambda n: None if n == "style_verify" else real(n))        # 검증 스레드 없이
    d = _upload(client, SMALL)
    assert client.put(f"/api/works/{d}/task", json={"kind": "general", "job": "style_copy", "file": "", "project": "갑 과제", "round": 2}).status_code == 200
    tabs = client.post(f"/api/docs/{d}/styles/candidates", json={}).json()["tables"]
    tid, t0 = tabs[0]["table"], time.time()
    a = client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": tid}).json()
    src = a["source"]
    assert (src["name"], src["format"], src["work"], src["block"], src["project"], src["job"], src["round"]) == (SMALL.name, "hwpx", d, tid, "갑 과제", "style_copy", 2)
    assert re.fullmatch(r"표 \d+번째", src["where"]) and t0 - 1 <= src["at"] <= time.time() + 1 and len(src["sha256"]) == 64 and a["seenIn"] == []
    page = client.post(f"/api/docs/{d}/styles", json={"kind": "page"}).json()["source"]
    assert (page["project"], page["where"], page["block"]) == ("갑 과제", None, None)
    # 다른 문서 — 같은 표가 든 다른 파일(**다른 표**의 칸 글 하나를 바꿔 바이트가 다르다)
    doc = HwpxDoc(SMALL.read_bytes())
    other = next(b for b in doc.blocks() if b["type"] == "table" and b["id"] != tid)
    doc.set_text(next(x["id"] for c in other["cells"] for x in c["blocks"] if x["type"] == "paragraph"), "다른 문서입니다")
    r = client.post("/api/docs?new=1", files={"file": ("다른 문서.hwpx", doc.save())})
    assert r.status_code == 200, r.text
    d2 = r.json()["docId"]
    b = client.post(f"/api/docs/{d2}/styles", json={"kind": "table", "table": tid}).json()
    assert b["id"] == a["id"] and b["existing"] is True and b["revision"] == "r1" and b["source"]["work"] == d                      # 원본은 처음 뽑은 문서 그대로
    assert [(x["name"], x["work"], x["project"], x["where"]) for x in b["seenIn"]] == [("다른 문서.hwpx", d2, None, src["where"])]
    assert client.post(f"/api/docs/{d2}/styles", json={"kind": "table", "table": tid}).json()["seenIn"] == b["seenIn"]             # 다시 뽑아도 한 번만 적는다
    assert client.post(f"/api/docs/{d}/styles", json={"kind": "table", "table": tid}).json()["seenIn"] == b["seenIn"]              # 원본 문서는 seenIn 에 안 든다
    row = next(s for s in client.get("/api/styles").json()["styles"] if s["id"] == a["id"])
    assert row["source"]["project"] == "갑 과제" and [x["name"] for x in row["seenIn"]] == ["다른 문서.hwpx"]                       # 목록에도 실린다(서식 관리자의 「원본 …」 줄)


def test_word_page_drops_words_drawing_habits():
    """Word PDF 의 그림 버릇(spec_서식복사 ② §7 — 실측 2026-11-14): 칸 음영 위에 글 줄마다 덧칠한 같은 색 사각형 · 굵은 선이 만나는 자리의 작은 조각 · 괘선 옆 음영 색 띠는 걷어 낸다 —
    그대로 두면 그 변이 행 경계로 더 세어져 칸 자리를 못 잡는다(「가로 경계 12개 — 행 6개」)."""
    grey, black = (0.84, 0.84, 0.84), (0.0, 0.0, 0.0)
    exp = {"cells": [{"edges": {"t": {"type": "SOLID", "color": "#000000"}}}]}
    page = {"rects": [{"x0": 56.6, "y0": 74.3, "x1": 127.3, "y1": 117.7, "fill": grey},      # 칸 음영
                      {"x0": 58.1, "y0": 82.6, "x1": 126.0, "y1": 96.0, "fill": grey},       # 글 줄마다 덧칠(안에 든 같은 색)
                      {"x0": 56.6, "y0": 126.7, "x1": 57.7, "y1": 129.3, "fill": black},     # 굵은 바깥선의 교차 조각
                      {"x0": 127.3, "y0": 74.0, "x1": 127.6, "y1": 74.3, "fill": black}],    # 교차점
            "segs": [{"dir": "h", "x0": 56.6, "y0": 74.16, "x1": 127.3, "y1": 74.16, "w": 0.24, "color": black, "dashed": False},
                     {"dir": "h", "x0": 56.6, "y0": 75.06, "x1": 127.3, "y1": 75.06, "w": 1.56, "color": grey, "dashed": False}]}  # 음영 색 띠(선으로 읽힌 것)
    got = V.word_page(page, exp)
    assert [(r["y0"], r["y1"]) for r in got["rects"]] == [(74.3, 117.7)] and [s["y0"] for s in got["segs"]] == [74.16]
    assert V.word_page({"rects": [], "segs": []}, exp) == {"rects": [], "segs": []}


# ---- 2차(spec_서식복사 ② §12~§16): 견본 끝점 · 쪽 설정의 bodyKey · 표지 서식 · LLM 검토 합치기 · 첫 쪽 전체 그림 ---------------------------

def _mods(monkeypatch, **mods):
    """`style_api._mod` 를 이 모듈들로만(없는 이름 = None — 검증 스레드가 시험 사이로 새지 않게)."""
    monkeypatch.setattr(style_api, "_mod", lambda n: mods.get(n))
    return mods


def _verifier(kicked):
    """검증 모듈 흉내 — 걸린 서식 id 만 적는다(스레드 없음)."""
    return types.SimpleNamespace(start=lambda sid, **kw: kicked.append(sid) or {"status": "running", "revision": "r1"}, running=lambda sid: False, subject_hash=lambda meta, fmt="hwpx": "h")


def _log_kinds(c, d):
    return [e["kind"] for e in c.get(f"/api/works/{d}/log").json()["events"]]


def test_api_preview_builds_like_save_but_writes_nothing(client, page_mod, monkeypatch):
    """견본 끝점(② §13): 몸은 저장과 같은 꼴 — 같은 생성 함수(`build_doc_style`)로 지은 운반 문서의 보기만 돌려준다. 보관함에 아무것도 쓰지 않고 검증을 걸지 않으며, 그 보기는 같은 몸으로 저장한 서식의 보기와 같다."""
    kicked = []
    _mods(monkeypatch, style_extract=X, style_verify=_verifier(kicked))
    d = _upload(client, SMALL)
    url = f"/api/docs/{d}/styles"
    tb = next(b for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["id"] == "t8")
    paras = [x["id"] for cell in tb["cells"] for x in cell["blocks"] if x["type"] == "paragraph" and x["text"].strip()][:6]
    bodies = ({"kind": "table", "table": "t8", "bands": {"headerRows": 0, "headerCols": 1, "footRows": 0}}, {"kind": "text", "paras": paras, "role": "box"}, {"kind": "page"})
    views = []
    for body in bodies:
        r = client.post(f"{url}/preview", json=body)
        assert r.status_code == 200, r.text
        pv = r.json()
        assert set(pv) == {"rev", "kind", "view", "losses", "fidelity"} and (pv["rev"], pv["kind"], pv["fidelity"]) == (0, body["kind"], "native")
        views.append(pv["view"])
    assert client.get("/api/styles").json()["styles"] == [] and kicked == [] and "styleSave" not in _log_kinds(client, d)   # 보관함에 아무것도 안 쓰고 · 검증도 안 걸고 · 기록도 없다
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True
    assert views[0]["spec"]["rows"] == 18 and views[1]["items"] and (views[2]["page"], views[2]["summary"]) == (PAGE, SUMMARY)
    for body, view in zip(bodies, views):                                                              # 같은 몸으로 저장한 서식의 보기와 같다
        r = client.post(url, json=body)
        assert r.status_code == 201, r.text
        assert client.get(f"/api/styles/{r.json()['id']}").json()["view"] == view, body["kind"]
    assert len(kicked) == 3 and style_lib.get(kicked[1])["role"] == "box"
    # 같은 문서 차례·같은 몸은 기억해 둔 답 — 다시 짓지 않는다. 띠 수를 바꾸면 다시 짓고 라벨 칸이 달라진다
    built, real = [], style_carrier.from_table
    monkeypatch.setattr(style_carrier, "from_table", lambda *a, **k: built.append(1) or real(*a, **k))
    again = client.post(f"{url}/preview", json=bodies[0]).json()
    assert built == [] and again["view"] == views[0]
    zero = client.post(f"{url}/preview", json={**bodies[0], "bands": {"headerRows": 0, "headerCols": 0, "footRows": 0}}).json()
    first = lambda v: v["grid"]["rows"][0]["cells"][0]["text"]  # noqa: E731
    assert built == [1] and (first(views[0]), first(zero["view"])) == ("제안기술 분류", "가나다") and (views[0]["grid"]["headerCols"], zero["view"]["grid"]["headerCols"]) == (1, 0)
    kept = client.post(f"{url}/preview", json={**bodies[0], "bands": {"headerRows": 0, "headerCols": 0, "footRows": 0}, "keepText": True}).json()
    assert first(kept["view"]) == "제안기술 분류" and built == [1, 1]                                    # 「글도 그대로」 를 켜면 견본도 글째
    # 문서가 바뀌면 기억을 버린다
    assert client.post(f"/api/docs/{d}/styles/builtin/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 200
    late = client.post(f"{url}/preview", json=bodies[0]).json()
    assert late["rev"] == 1 and built == [1, 1, 1] and late["view"] == views[0]
    # 오류는 저장과 같다 · 보관함이 꺼져 있으면 503
    for bad, code in (({"kind": "chart"}, 400), ({"kind": "table", "table": "t9999"}, 404), ({"kind": "text", "paras": []}, 400), ({"kind": "text", "paras": paras[:1], "role": "제목"}, 400)):
        assert client.post(f"{url}/preview", json=bad).status_code == code, bad
    assert client.post("/api/docs/nope/styles/preview", json=bodies[0]).status_code == 404
    monkeypatch.setenv("NFM_STYLES", "off")
    assert client.post(f"{url}/preview", json=bodies[0]).status_code == 503


def test_build_doc_style_only_builds(client, monkeypatch):
    """`build_doc_style(s, body) -> (meta, data)` 는 짓기만 한다 — `save_doc_style` 이 그것 + 저장 + 기록 + 검증(에이전트 반영이 부르는 이름·인자·돌려주는 값은 그대로)."""
    kicked = []
    _mods(monkeypatch, style_verify=_verifier(kicked))
    d = _upload(client, SMALL)
    s = server.DOCS[d]
    meta, data = style_api.build_doc_style(s, {"kind": "table", "table": "t8", "name": "지은 표", "note": "메모"})
    assert (meta["kind"], meta["name"], meta["note"], meta["fidelity"], meta["source"]["block"]) == ("table", "지은 표", "메모", "native", "t8") and data[:2] == b"PK" and "id" not in meta
    assert style_lib.listing()["styles"] == [] and kicked == [] and "styleSave" not in _log_kinds(client, d)
    out = style_api.save_doc_style(s, {"kind": "table", "table": "t8", "name": "저장한 표"})
    assert out["id"] and out["revision"] == "r1" and out["name"] == "저장한 표" and kicked == [out["id"]] and "styleSave" in _log_kinds(client, d)
    assert [m["id"] for m in style_lib.listing()["styles"]] == [out["id"]] and style_lib.carrier(out["id"])[:2] == b"PK"


def test_api_page_style_takes_a_body_key(client, page_mod, monkeypatch):
    """쪽 설정 저장의 `bodyKey`(② §12): 바탕 글 후보(`bodies`) 가운데 그 key 의 서식을 바탕 글로 · "none" = 바탕 글 없음 · 모르는 key 는 400. 견본도 같은 몸을 받는다."""
    _mods(monkeypatch, style_extract=X, style_page=page_mod)
    d = _upload(client, SMALL)
    url = f"/api/docs/{d}/styles"
    assert client.post(url, json={"kind": "page"}).json()["body"] == BODY                                # 안 주면 스크립트가 고른 것
    r = client.post(url, json={"kind": "page", "bodyKey": "b2", "name": "둘째 바탕"})
    assert r.status_code == 201 and r.json()["body"] == {"format": BODIES[1]["format"], "count": 3} and r.json()["page"] == PAGE
    assert client.post(url, json={"kind": "page", "bodyKey": "none", "name": "바탕 없이"}).json()["body"] is None
    for bad in ("b9", "", 2):
        r = client.post(url, json={"kind": "page", "bodyKey": bad})
        assert r.status_code == 400 and "bodyKey" in r.json()["detail"], bad
    pv = client.post(f"{url}/preview", json={"kind": "page", "bodyKey": "b2"})
    assert pv.status_code == 200 and pv.json()["view"]["body"]["format"]["sizePt"] == 9.0 and pv.json()["view"]["page"] == PAGE
    assert client.post(f"{url}/preview", json={"kind": "page", "bodyKey": "none"}).json()["view"]["body"] is None


@pytest.fixture()
def cover_mod(monkeypatch):
    """`app.style_cover` 흉내(spec_서식복사 ② §16 의 시그니처) — 표지 = 문서의 앞 최상위 블록 셋까지 · 운반 문서는 빈 바탕 그대로. calls = carrier 가 받은 (블록들, roles, keep_text) · none 을 켜면 후보 없음."""
    from app.hwpx_doc import P
    sc = types.ModuleType("app.style_cover")
    sc.ROLES = (("title", "제목"), ("subtitle", "부제"), ("org", "기관명"), ("date", "날짜"), ("person", "작성자"), ("label", "라벨"), ("other", "기타"))
    sc.calls, sc.none, sc.graphs = [], False, []

    def find(doc, graph=None):
        sc.graphs.append(graph)
        ids = [b["id"] for b in doc.blocks()][:3]
        if sc.none or len(ids) < 2:
            return None
        return {"key": "cover", "blocks": ids, "end": ids[-1], "signals": {"centered": True}, "parts": [{"block": i, "type": "text", "role": "other", "sample": "한글 2자", "sizePt": 11.0, "align": "left"} for i in ids],
                "sample": "표지"}

    def shrink(cand, end):
        if end not in cand["blocks"]:
            return None
        keep = cand["blocks"][:cand["blocks"].index(end) + 1]
        return {**cand, "blocks": keep, "end": end, "parts": cand["parts"][:len(keep)]}

    def carrier(src, block_ids, roles=None, keep_text=False):
        sc.calls.append((list(block_ids), roles, keep_text))
        parts = [{"key": f"p{n}", "type": "text", "role": (roles or {}).get(i, "other"), "sample": "원문" if keep_text else "견본", "format": dict(FMT)} for n, i in enumerate(block_ids, 1)]
        return style_carrier.base(), {"page": PAGE, "parts": parts, "fonts": ["맑은 고딕"], "losses": ["그림은 옮기지 않았습니다"]}

    def view(data, meta):
        return {"page": meta.get("page"), "parts": [{**p, "gapBeforeMm": 0.0} for p in meta.get("parts") or []]}

    def insert(doc, cdoc):
        first = doc._id(next(doc._sections[0].iterchildren(P)))
        return {"blocks": doc.insert_after(first, [{"kind": "paragraph", "text": "표지 제목"}, {"kind": "paragraph", "text": "표지 기관명"}]), "after": None}
    sc.find, sc.shrink, sc.carrier, sc.view, sc.insert = find, shrink, carrier, view, insert
    monkeypatch.setitem(sys.modules, "app.style_cover", sc)
    monkeypatch.setattr(app, "style_cover", sc, raising=False)
    return sc


def test_api_cover_style_save_view_and_apply(client, cover_mod, monkeypatch):
    """표지 서식(② §14): 저장 `{kind: "cover", end?, roles?, name?, keepText?}`(범위 = 그때의 표지 후보 · end 로 줄임) · 보기 = `style_cover.view` · 견본 · 이름·메모만 고침 · 적용 `{mode: "cover"}`(covered)."""
    kicked = []
    _mods(monkeypatch, style_cover=cover_mod, style_verify=_verifier(kicked))
    d = _upload(client, SMALL)
    url = f"/api/docs/{d}/styles"
    ids = [b["id"] for b in client.get(f"/api/docs/{d}").json()["blocks"]][:3]                              # 흉내 모듈의 표지 범위 = 앞 최상위 블록 셋까지
    assert len(ids) >= 2
    pv = client.post(f"{url}/preview", json={"kind": "cover"})
    assert pv.status_code == 200 and pv.json()["kind"] == "cover" and [p["sample"] for p in pv.json()["view"]["parts"]] == ["견본"] * len(ids) and pv.json()["losses"] == ["그림은 옮기지 않았습니다"]
    assert client.get("/api/styles").json()["styles"] == [] and kicked == [] and cover_mod.calls[-1] == (ids, None, False)
    r = client.post(url, json={"kind": "cover", "end": ids[0], "roles": {ids[0]: "title", ids[-1]: "date"}, "keepText": True})
    assert r.status_code == 201, r.text
    m = r.json()
    sid = m["id"]
    assert (m["kind"], m["name"], m["fidelity"], m["page"], m["source"]["block"], m["source"]["format"]) == ("cover", "기술수요조사서 표지", "native", PAGE, ids[0], "hwpx")
    assert [(p["key"], p["role"], p["sample"]) for p in m["parts"]] == [("p1", "title", "원문")] and m["losses"] == ["그림은 옮기지 않았습니다"] and m["requirements"] == {"fonts": ["맑은 고딕"]}
    assert cover_mod.calls[-1] == (ids[:1], {ids[0]: "title"}, True) and kicked == [sid]                  # end 로 줄인 범위 · 범위 밖 블록의 역할은 버린다 · 저장하면 검증을 건다
    assert client.get(f"/api/docs/{d}").json()["pristine"] is True and "styleSave" in _log_kinds(client, d)
    full = client.get(f"/api/styles/{sid}").json()
    assert full["view"]["page"] == PAGE and [p["gapBeforeMm"] for p in full["view"]["parts"]] == [0.0] and "viewError" not in full
    row = client.get("/api/styles").json()["styles"][0]
    assert row["kind"] == "cover" and "leveled" not in row and "role" not in row
    assert client.post(url, json={"kind": "cover", "name": "내 표지"}).json()["name"] == "내 표지" and cover_mod.calls[-1] == (ids, None, False)
    for bad, word in (({"end": "p99999"}, "end"), ({"end": 3}, "end"), ({"roles": {ids[0]: "heading"}}, "roles"), ({"roles": [ids[0]]}, "roles")):
        r = client.post(url, json={"kind": "cover", **bad})
        assert r.status_code == 400 and word in r.json()["detail"], bad
    p = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r1", "name": "보고서 표지", "note": "첫 쪽"})
    assert p.status_code == 200 and (p.json()["name"], p.json()["note"], p.json()["parts"]) == ("보고서 표지", "첫 쪽", m["parts"])
    for bad in ({"bands": {"headerRows": 1}}, {"items": [{"key": "i1"}]}, {"role": "body"}):
        r = client.put(f"/api/styles/{sid}", json={"expectedRevision": "r2", **bad})
        assert r.status_code == 400, bad
    # 적용 — 문서의 맨 앞에 표지의 블록들을(구조 편집 한 번 · 실행 취소 1개)
    tab = style_lib.create({"kind": "table", "name": "표", "rows": 2, "cols": 2}, style_carrier.base())["id"]
    a = client.post(f"{url}/{sid}/apply", json={"mode": "cover"})
    assert a.status_code == 200, a.text
    assert a.json()["covered"] == {"blocks": 2} and a.json()["undo"] == 1 and "styleApply" in _log_kinds(client, d)
    texts = [b["text"] for b in client.get(f"/api/docs/{d}").json()["blocks"] if b["type"] == "paragraph"]
    assert "표지 제목" in texts and texts[texts.index("표지 제목") + 1] == "표지 기관명"
    assert client.post(f"{url}/{tab}/apply", json={"mode": "cover"}).status_code == 400                    # 표지 서식이 아닌 것
    assert client.post(f"{url}/ffffffffffff/apply", json={"mode": "cover"}).status_code == 404
    assert client.post(f"{url}/{sid}/apply", json={"mode": "tableBlank", "after": "t8"}).status_code == 400   # 표지 서식을 표로 쓸 수 없다
    cover_mod.insert = lambda doc, cdoc: {"blocks": [], "after": None}
    assert client.post(f"{url}/{sid}/apply", json={"mode": "cover"}).status_code == 400                    # 넣은 블록이 없으면 되돌린다
    # 후보가 없으면 400 · 표지 모듈이 없으면 501
    cover_mod.none = True
    r = client.post(url, json={"kind": "cover"})
    assert r.status_code == 400 and r.json()["detail"] == "이 문서에서 표지를 찾지 못했습니다"
    _mods(monkeypatch)
    assert client.post(url, json={"kind": "cover"}).status_code == 501


def test_api_cover_on_a_docx_document(client, cover_mod, monkeypatch):
    """docx 문서: 표지 서식의 저장은 되고(`style_cover` 가 명세로 다시 짓는다 — fidelity summary), 「표지 넣기」 는 400(v1 — hwpx 문서만)."""
    _mods(monkeypatch, style_cover=cover_mod)
    d = _upload(client, DOCX)
    r = client.post(f"/api/docs/{d}/styles", json={"kind": "cover"})
    assert r.status_code == 201, r.text
    assert (r.json()["kind"], r.json()["fidelity"], r.json()["source"]["format"]) == ("cover", "summary", "docx") and cover_mod.graphs[-1] is None
    a = client.post(f"/api/docs/{d}/styles/{r.json()['id']}/apply", json={"mode": "cover"})
    assert a.status_code == 400 and "빈 표 넣기 · 문단에 입히기만" in a.json()["detail"]


def test_api_candidates_merge_the_review_into_five_kinds(client, monkeypatch):
    """LLM 검토 합치기(② §15·§16): `style_extract.review` 의 답 {종류: {후보 key: R}} 을 다섯 종류의 후보에 **그대로** 얹는다 — 응답의 `call` 은 첫 호출(옛 꼴), `calls` 는 호출마다. 상세 기록에는 프롬프트·답 전부."""
    cands = {"tables": [{"key": "t:1", "table": "t8", "rows": 18, "cols": 11, "bands": BANDS, "doubts": []}],
             "texts": [{"key": "tpl1", "template": {"id": 1}, "items": [{"para": "p1", "level": 1}], "doubts": ["mixedSlot"]}],
             "paras": [{"key": "g1", "role": "body", "count": 7, "items": [{"para": "p3", "level": None}], "doubts": []}],
             "pages": [{"key": "page", "page": PAGE, "body": BODY, "bodies": BODIES, "sample": SUMMARY, "losses": [], "doubts": ["bodyClose"]}],
             "covers": [{"key": "cover", "blocks": ["p1", "p2"], "end": "p2", "parts": [], "sample": "표지", "doubts": []}]}
    rv = lambda seen, fixed=(), doubts=(): {"by": "llm", "seen": list(seen), "fixed": list(fixed), "doubts": list(doubts)}  # noqa: E731
    answer = {"tables": {"t:1": {"name": "수요조사 양식", "keep": True, "role": "form", "bands": BANDS, "bandsChanged": False, "bandsWider": {"headerRows": 2, "headerCols": 0, "footRows": 0},
                                 "review": rv(["이름", "띠 수", "역할"])}},
              "texts": {"tpl1": {"name": "개요 3레벨", "keep": True, "rep": {"1": "p9"}, "review": rv(["이름", "레벨"], [{"what": "rep", "from": "p1", "to": "p9"}], [{"code": "mixedSlot", "text": "한 레벨에 서식이 여럿", "by": "script"}])}},
              "paras": {"g1": {"name": "본문 글", "keep": True, "role": "caption", "sameAs": "g2", "review": rv(["이름", "역할"])}},
              "pages": {"page": {"keep": True, "bodyKey": "b2", "review": rv(["바탕 글"], [{"what": "bodyKey", "from": "b1", "to": "b2"}])}},
              "covers": {"cover": {"keep": False, "isCover": True, "end": "p1", "roles": {"p1": "title"}, "review": rv(["범위", "역할"])}, "ghost": {"keep": True}},
              "note": "셋으로 나눠 봄", "call": {"backend": "api", "model": "m", "ms": 5, "costUsd": 0.01, "error": None},
              "calls": [{"backend": "api", "model": "m", "ms": 5, "costUsd": 0.01, "error": None}, {"backend": "api", "model": "m", "ms": 9, "costUsd": 0.02, "error": "시간 초과"}],
              "prompt": "첫 프롬프트", "prompts": ["첫 프롬프트", "둘째 프롬프트"], "response": {"tables": []}, "responses": [{"tables": []}, None]}
    seen = {}

    def review(given, call=None, effort=None, job=None):
        seen["keys"], seen["job"] = sorted(given), job
        return answer
    fake = types.SimpleNamespace(candidates=lambda doc, graph=None: cands, review=review, name=lambda *a, **k: 1 / 0)   # 새 모듈이면 옛 이름을 부르지 않는다
    _mods(monkeypatch, style_extract=fake)
    d = _upload(client, SMALL)
    plain = client.post(f"/api/docs/{d}/styles/candidates", json={}).json()
    assert {k: plain[k] for k in ("tables", "texts", "paras", "pages", "covers")} == cands and "call" not in plain   # 스크립트 후보 그대로 — doubts 도 온 그대로
    monkeypatch.setattr("app.llm.status", lambda: {"available": True})
    n = client.post(f"/api/docs/{d}/styles/candidates", json={"llm": True}).json()
    assert seen["keys"] == ["covers", "pages", "paras", "tables", "texts"]
    assert n["tables"] == [{**cands["tables"][0], **answer["tables"]["t:1"]}] and n["texts"] == [{**cands["texts"][0], **answer["texts"]["tpl1"]}] and n["paras"] == [{**cands["paras"][0], **answer["paras"]["g1"]}]
    assert n["pages"] == [{**cands["pages"][0], **answer["pages"]["page"], "name": "기술수요조사서 문서 서식"}]                 # 쪽 설정 — 이름은 기본 이름
    assert n["covers"] == [{**cands["covers"][0], **answer["covers"]["cover"], "name": "기술수요조사서 표지"}]                 # 표지 — keep 은 검토의 답 그대로(false)
    assert n["call"] == answer["call"] and n["calls"] == answer["calls"] and n["note"] == "셋으로 나눠 봄" and "prompt" not in n and "prompts" not in n
    ev = [e for e in client.get(f"/api/works/{d}/log").json()["events"] if e["kind"] == "styleName"]
    assert len(ev) == 1 and (ev[0]["named"], ev[0]["reviewed"], ev[0]["calls"], ev[0]["costUsd"]) == (3, 6, 2, 0.03) and str(ev[0]["detail"]).startswith("styles/name_")
    # 호출이 모두 실패하고 답이 닿은 후보가 없으면 502 · 일부만 실패하면 200(calls 에 오류가 보인다)
    answer.update({k: {} for k in ("tables", "texts", "paras", "pages", "covers")})
    answer.update(call={"backend": "api", "error": "한도"}, calls=[{"backend": "api", "error": "한도"}, {"backend": "api", "error": "시간 초과"}])
    r = client.post(f"/api/docs/{d}/styles/candidates", json={"llm": True})
    assert r.status_code == 502 and "한도" in r.json()["detail"]
    answer.update(calls=[{"backend": "api", "error": "한도"}, {"backend": "api", "error": None}])
    r = client.post(f"/api/docs/{d}/styles/candidates", json={"llm": True})
    assert r.status_code == 200 and r.json()["pages"][0]["keep"] is True and "name" not in r.json()["tables"][0]
    # 파일 후보도 같은 꼴(name-file)
    entry = {"name": "보고서.hwpx", "format": "hwpx", **cands}
    fake.held = lambda token: entry if token == "tok" else None
    answer.update(paras={"g1": {"name": "본문 글", "keep": True, "role": "body", "review": rv(["이름"])}}, calls=[{"backend": "api", "error": None}], call={"backend": "api", "error": None})
    f = client.post("/api/styles/name-file", json={"token": "tok"})
    assert f.status_code == 200 and f.json()["paras"][0]["review"]["by"] == "llm" and f.json()["covers"][0]["name"] == "보고서 표지" and f.json()["pages"][0]["name"] == "보고서 문서 서식"
    assert set(f.json()) == {"tables", "texts", "paras", "pages", "covers", "note", "call", "calls"}


def test_api_file_picks_paras_roles_and_covers(client, cover_mod, monkeypatch):
    """파일 후보의 저장·견본(`from-file` · `preview-file`): 문단 묶음(`paras`)의 key 도 글 pick 으로 받고 역할을 싣는다 · 표지 pick 은 entry 의 `covers` 후보로(없으면 400)."""
    from app.hwpx_doc import HwpxDoc
    doc = HwpxDoc(SMALL.read_bytes())
    ids = [b["id"] for b in doc.blocks()][:3]                                                           # 흉내 모듈의 표지 범위(앞 최상위 블록 셋까지)
    para = {"key": "g1", "role": "caption", "count": 4, "items": [{"para": ids[0], "level": None, "sample": "한글 4자", "format": dict(FMT), "marker": {"mode": "none", "literal": "", "lead": "", "gap": "", "family": None}}]}
    entry = {"name": "보고서.hwpx", "format": "hwpx", "fidelity": "native", "tables": [], "texts": [], "paras": [para], "pages": [], "covers": [cover_mod.find(doc)], "_doc": doc, "_sha256": "s" * 64}
    seen = []

    def build_pick(ent, pick):
        seen.append([c["key"] for c in ent.get("texts") or []])
        cand = next((c for c in ent.get("texts") or [] if c["key"] == pick.get("key")), None)
        if pick.get("kind") != "text" or cand is None:
            raise ValueError("없는 서식 후보입니다")
        data, items = style_carrier.from_text_spec([{"level": None, "marker": i["marker"], "sample": i["sample"], "format": i["format"]} for i in cand["items"]])
        return data, {"kind": "text", "name": "보고서 글 서식", "source": {"name": ent["name"], "format": "hwpx"}, "fidelity": "native", "losses": [], "requirements": {"fonts": []}, "items": items}
    fake = types.SimpleNamespace(build_pick=build_pick, held=lambda token: entry if token == "tok" else None)
    _mods(monkeypatch, style_extract=fake, style_cover=cover_mod)
    pv = client.post("/api/styles/preview-file", json={"token": "tok", "pick": {"kind": "text", "key": "g1"}})
    assert pv.status_code == 200, pv.text
    assert pv.json()["kind"] == "text" and len(pv.json()["view"]["items"]) == 1 and seen == [[], ["g1"]] and entry["texts"] == []   # 옛 추출 모듈(글 후보에서만 찾는다)이면 문단 묶음을 얹어 한 번 더(entry 는 안 바꾼다)
    made = client.post("/api/styles/from-file", json={"token": "tok", "picks": [{"kind": "text", "key": "g1"}, {"kind": "text", "key": "g1", "role": "note", "name": "주석 글"},
                                                                               {"kind": "cover", "key": "cover", "end": ids[1], "roles": {ids[0]: "title"}}]})
    assert made.status_code == 200, made.text
    a, b, c = made.json()["styles"]
    assert (a["role"], b["role"], b["name"]) == ("caption", "note", "주석 글")                            # 역할 = pick 의 것 → 없으면 후보에 스크립트가 붙인 것
    assert (c["kind"], c["name"], c["fidelity"], c["source"]["block"], c["source"]["sha256"], c["source"]["work"]) == ("cover", "보고서 표지", "native", ids[0], "s" * 64, None)
    assert cover_mod.calls[-1] == (ids[:2], {ids[0]: "title"}, False) and [p["role"] for p in c["parts"]] == ["title", "other"]
    assert client.post("/api/styles/preview-file", json={"token": "tok", "pick": {"kind": "cover", "key": "cover"}}).json()["kind"] == "cover"
    for bad in ({"kind": "text", "key": "g1", "role": "제목"}, {"kind": "cover", "key": "nope"}, {"kind": "cover", "key": "cover", "end": "p99999"}, {"kind": "text", "key": "nope"}):
        assert client.post("/api/styles/from-file", json={"token": "tok", "picks": [bad]}).status_code == 400, bad
    assert len(client.get("/api/styles").json()["styles"]) == 3


def test_api_proof_full_redraws_the_first_page_from_the_stored_pdf(client, monkeypatch):
    """`GET …/proof.png?full=1`(② §13): 그 revision 의 proof.pdf 에서 첫 쪽 전체를 그 자리에서 다시 그린다(저장된 그림은 그대로) — PDF 가 없으면 저장된 그림."""
    import fitz
    _mods(monkeypatch, style_verify=V)
    sid = style_lib.create({"kind": "page", "name": "쪽", "page": PAGE, "body": None}, style_carrier.base(), {"carrier.docx": b"docx"})["id"]
    pdf = fitz.open()
    pdf.new_page(width=595, height=842).insert_text((70, 100), "proof", fontname="helv", fontsize=10)
    assert style_lib.put_verify(sid, "r1", {"status": "ok"}, {"proof.png": b"\x89PNG-cropped", "proof.pdf": pdf.tobytes()}) is True
    assert style_lib.put_verify(sid, "r1", {"status": "ok", "format": "docx"}, {"proof_docx.png": b"\x89PNG-word"}, fmt="docx") is True
    assert client.get(f"/api/styles/{sid}/proof.png").content == b"\x89PNG-cropped"                      # 기본은 저장된 그림
    full = client.get(f"/api/styles/{sid}/proof.png?full=1")
    pix = fitz.Pixmap(full.content)
    assert full.status_code == 200 and full.headers["content-type"] == "image/png" and abs(pix.height - V.PROOF_FULL_PX) <= 12 and pix.width > 700   # A4 한 쪽 통째로
    assert style_lib.file(sid, "proof.png").read_bytes() == b"\x89PNG-cropped"                           # 파일은 덮어쓰지 않는다
    assert client.get(f"/api/styles/{sid}/proof.png?format=docx&full=1").content == b"\x89PNG-word"      # PDF 가 없으면 저장된 그림
    assert client.get(f"/api/styles/{sid}/proof.png?full=0").content == b"\x89PNG-cropped"
    _mods(monkeypatch)                                                                                   # 검증 모듈이 없어도 저장된 그림은 준다
    assert client.get(f"/api/styles/{sid}/proof.png?full=1").content == b"\x89PNG-cropped"
