"""서식 보관함 PDF 검증(spec_일반편집 ② §6) — 한글 없이: 출력 없음(none) · 대상 해시 · 견줌(지어낸 잰 값으로 pass·fail·unknown) · 작업(start). 실제 한글 출력은 test_style_verify_pdf.py."""
import copy
import sys
import threading
import time
import types
from pathlib import Path

import fitz
import pytest

import app
from app import pdf_render, pdf_style
from app import style_verify as V
from app import table_make
from app.hwpx_doc import HwpxDoc

BASE = Path(__file__).resolve().parent.parent / "app" / "style_base.hwpx"
THIN = {"type": "SOLID", "widthMm": 0.12, "color": "#000000"}
THICK = {"type": "SOLID", "widthMm": 0.4, "color": "#000000"}
DOUBLE = {"type": "DOUBLE_SLIM", "widthMm": 0.5, "color": "#000000"}


def _fmt(**kw):
    return {"font": "맑은 고딕", "sizePt": 10.0, "bold": False, "color": "#000000", "align": "left", "indentLeftMm": 0.0, "firstLineMm": 0.0, **kw}


def _chars(text, **kw):
    """칸 글 → expect 의 chars(글자·숫자만 — pdf_style._web_chars 와 같은 꼴)."""
    f = _fmt(**kw)
    return [(kc, ch, f) for ch in text for kc in V.key_text(ch)]


def _cell(row, col, text="", fill=None, edges=None, rs=1, cs=1, width=None, **fmt):
    return {"row": row, "col": col, "rowSpan": rs, "colSpan": cs, "text": text, "fill": fill, "widthPt": width or 0,
            "edges": dict.fromkeys("trbl", THIN) if edges is None else edges, "chars": _chars(text, **fmt), "auto": False, "nested": False, "zoned": False}


def _exp(cells, rows, cols, widths=None, heights=None):
    return {"table": "t1", "rows": rows, "cols": cols, "widthsPt": widths or [100.0] * cols, "heightsPt": heights or [20.0] * rows, "cells": cells}


def _grid():
    """머리행(음영·굵게) + 몸 2행 × 2열 — 바깥 굵은 선·안 가는 선."""
    def edges(r, c):
        return {"t": THICK if r == 0 else THIN, "b": THICK if r == 2 else THIN, "l": THICK if c == 0 else THIN, "r": THICK if c == 1 else THIN}
    return _exp([_cell(0, 0, "구분", "#D9E2F3", edges(0, 0), bold=True), _cell(0, 1, "금액", "#D9E2F3", edges(0, 1), bold=True),
                 _cell(1, 0, "인건비", None, edges(1, 0)), _cell(1, 1, "100", None, edges(1, 1), align="right"),
                 _cell(2, 0, "합계", "#FFF2CC", edges(2, 0)), _cell(2, 1, "100", "#FFF2CC", edges(2, 1), align="right")], 3, 2)


FACE = {"맑은 고딕": "MalgunGothic", "함초롬돋움": "HCRDotum", "한양신명조": "T1"}


def _text_line(text_chars, x, y, block=0):
    """글자 [(키, 원 글자, 모양)] → pdf_map 줄 하나(글자마다 span 하나 — 글꼴 이름은 FACE, 굵게는 이름 꼬리 Bold + flags 16)."""
    chars, spans = [], []
    for _, ch, f in text_chars:
        size = f["sizePt"]
        face = pdf_style._web_face(ch, f)[0]  # 영문·숫자는 그 언어 글꼴(서식 요약 fontLatin)로 찍힌다
        spans.append((FACE.get(face, face) + ("Bold" if f.get("bold") else ""), size, 16 if f.get("bold") else 0, int((f.get("color") or "#000000")[1:], 16)))
        chars.append((ch, x, y, x + size, y + size, len(spans) - 1, bool(f.get("bold"))))
        x += size
    return {"text": "".join(c[1] for c in text_chars), "bbox": [chars[0][1], y, x, y + chars[0][4] - chars[0][2]], "block": block, "chars": chars, "spans": spans}


def _draw(exp, left=60.0, top=90.0, ys=None):
    """기대값대로 그린 쪽(잰 값 꼴) — 한글 PDF 흉내: 음영 = 칸 상자 채움 · 괘선 = 변마다 선(겹줄은 ±0.54pt 의 가는 선 둘) · 글 = 칸 안 한 줄."""
    occ = V._occupancy(exp)
    Y = ys or [top + sum(exp["heightsPt"][:r]) for r in range(exp["rows"] + 1)]
    box, _ = V.cell_boxes(exp, occ, left, 1.0, Y)
    segs, rects, lines = [], [], []
    for i, c in enumerate(exp["cells"]):
        x0, y0, x1, y1 = box[i]
        if c["fill"]:
            rects.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "fill": V._channels(c["fill"])})
        for side, e in c["edges"].items():
            if not e:
                continue
            at, lo, hi = V._side_span(box[i], side)
            for off in ((-0.54, 0.54) if e["type"].startswith("DOUBLE") else (0.0,)):
                w = 0.36 if e["type"].startswith("DOUBLE") else round(e["widthMm"] * V.PT_MM * 1.03, 3)
                segs.append({"dir": "h", "x0": lo, "y0": at + off, "x1": hi, "y1": at + off, "w": w, "color": (0, 0, 0), "dashed": False} if side in "tb" else
                            {"dir": "v", "x0": at + off, "y0": lo, "x1": at + off, "y1": hi, "w": w, "color": (0, 0, 0), "dashed": False})
        if c["chars"]:
            lines.append(_text_line(c["chars"], x0 + 4, y0 + 4, block=i))
    return {"count": 1, "pages": [{"w": 595.0, "h": 841.0, "sheet": 0, "lines": lines, "segs": segs, "rects": rects, "tables": [], "type3": set()}]}


def _by(checks):
    return {c["what"]: c for c in checks}


def _status(checks):
    return {c["what"]: c["status"] for c in checks}


def _measured(checks):
    """잰 검사들의 상태 모음 — 「재지 못함」(unsupported: 선 색·칸 여백 …)으로 늘 실리는 줄은 뺀다."""
    return {c["status"] for c in checks if c["status"] != "unsupported"}


# ---- 출력 없음 · 대상 해시 -----------------------------------------------------------------------------------------

def test_run_without_hangul_is_none():
    """conftest: NFM_PDF=off — 한글이 없으면 status none(「PDF 출력 없음」), 파일 없음, 예외 없음."""
    data = BASE.read_bytes()
    rec, files = V.run(data, {"kind": "table", "revision": "r3", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}})
    assert rec["status"] == "none" and files == {} and "PDF 출력 없음" in rec["note"]
    assert rec["revision"] == "r3" and rec["profile"] == "table-v1" and rec["renderer"] == {"name": "Hancom"} and rec["checks"] == []
    assert rec["coverage"] == {"pass": 0, "fail": 0, "unknown": 0, "unsupported": 0} and len(rec["subjectHash"]) == 64
    assert V.run(data, {"kind": "text"})[0]["profile"] == "text-v1"
    assert V.run(b"", None)[0]["status"] == "none"  # 틀린 입력에도 예외를 내지 않는다


def test_subject_hash_follows_meaning_not_names():
    item = {"key": "i1", "name": "제목", "level": 1, "marker": {"mode": "literal", "literal": "1.", "lead": "", "gap": " ", "family": "num"}, "sample": "1. 견본", "format": {"sizePt": 14}}
    meta = {"carrierSha256": "a" * 64, "name": "표", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}, "blueprint": None, "items": [item]}
    h = V.subject_hash(meta)
    assert h == V.subject_hash(dict(reversed(list(meta.items())))) and len(h) == 64                      # 키 차례와 무관
    assert h == V.subject_hash({**meta, "name": "다른 이름", "note": "메모", "items": [{**item, "name": "새 이름", "sample": "x", "format": {}}]})  # 이름·사본은 뜻이 아니다
    for change in ({"carrierSha256": "b" * 64}, {"bands": {"headerRows": 2, "headerCols": 0, "footRows": 0}},
                   {"blueprint": {"cells": [], "formulas": []}}, {"items": [{**item, "level": 2}]},
                   {"items": [{**item, "marker": {**item["marker"], "literal": "가."}}]}, {"items": []}):
        assert V.subject_hash({**meta, **change}) != h
    assert V.subject_hash(None) == V.subject_hash({})


# ---- 표 견줌(지어낸 잰 값) ----------------------------------------------------------------------------------------

def test_table_all_pass_on_a_faithful_page():
    exp = _grid()
    checks = V.check_table(exp, _draw(exp))
    assert [c["what"] for c in checks] == [*V.TABLE_CHECKS, "lineColor", "cellMargin", "valign", "cellAlign", "diagonal"]
    assert _measured(checks) == {"pass"}, _status(checks)
    by = _by(checks)
    assert by["text"]["pass"] == 6 and by["fill"]["pass"] == 6 and by["edge"]["pass"] == 24 and by["lineWidth"]["pass"] == 24 and by["width"]["pass"] == 1
    status, cov, notes = V.summarize(checks, 1)
    assert status == "ok" and cov["fail"] == 0 and cov["unknown"] == 0 and notes == [] and cov["unsupported"] == 5


def test_table_lists_what_it_never_checks_as_unsupported():
    """astra 12: 모든 괘선 색을 빨강으로 바꿔도 ok 였다 — 선 색은 견주지 않는다. 견주지 않는 것(선 색 · 칸 여백 · 세로 정렬 · 칸 안 글 정렬 · 대각선)을 「재지 못함」 으로 적어 화면에 보인다."""
    exp = _grid()
    m = _draw(exp)
    for s in m["pages"][0]["segs"]:
        s["color"] = (1, 0, 0)
    checks = V.check_table(exp, m)
    by = _by(checks)
    assert [(k, by[k]["status"]) for k, _ in V.UNSUPPORTED_TABLE] == [(k, "unsupported") for k in ("lineColor", "cellMargin", "valign", "cellAlign", "diagonal")]
    assert "선 색" in by["lineColor"]["note"] and "칸 여백" in by["cellMargin"]["note"] and "세로 정렬" in by["valign"]["note"] and "정렬" in by["cellAlign"]["note"] and "대각선" in by["diagonal"]["note"]
    status, cov, _ = V.summarize(checks, 1)
    assert status == "ok" and cov["unsupported"] == 5 and by["edge"]["fail"] == 0  # 판정은 그대로 ok — 다만 「선 색은 안 봤다」 가 기록에 남는다
    assert all(c["pass"] == c["fail"] == c["unknown"] == 0 for c in checks if c["status"] == "unsupported")


def test_text_in_a_cell_expected_empty_fails():
    """astra 12: 기대 표는 전부 빈 칸인데 PDF 에는 원래 글·숫자가 남아 있어도 ok(pass 56) 였다 — 빈 칸도 글 견줌에 넣는다: 빈 칸에 글이 있으면 「뜻밖의 글」."""
    full = _grid()
    empty = copy.deepcopy(full)
    for c in empty["cells"]:
        c["text"], c["chars"] = "", []
    checks = V.check_table(empty, _draw(full))
    by = _by(checks)
    assert by["text"]["status"] == "fail" and by["text"]["fail"] == 6 and by["text"]["examples"][0] == {"where": "A1", "want": "빈 칸", "got": "뜻밖의 글 「구분」"}
    assert V.summarize(checks, 1)[0] == "fail"
    one = copy.deepcopy(full)  # 한 칸만 비었다고 적힌 운반 문서 — 그 칸의 글만 뜻밖의 글
    one["cells"][3]["text"], one["cells"][3]["chars"] = "", []
    by = _by(V.check_table(one, _draw(full)))
    assert (by["text"]["pass"], by["text"]["fail"]) == (5, 1) and by["text"]["examples"][0]["where"] == "B2" and by["fontSize"]["pass"] == 5
    # PDF 에서도 비어 있으면 통과로 센다 · 글자·숫자가 아닌 것(「-」)만 있는 칸은 기대값에 글자가 없으니 그대로 통과
    checks = V.check_table(empty, _draw(empty))
    assert _by(checks)["text"]["pass"] == 6 and _by(checks)["text"]["status"] == "pass" and V.summarize(checks, 1)[0] == "ok"
    dash = copy.deepcopy(empty)
    dash["cells"][3]["text"] = "-"
    m = _draw(dash)
    m["pages"][0]["lines"].append({"text": "-", "bbox": [170.0, 114.0, 180.0, 124.0], "block": 3, "chars": [("-", 170.0, 114.0, 180.0, 124.0, 0, False)], "spans": [("MalgunGothic", 10.0, 0, 0)]})
    assert _by(V.check_table(dash, m))["text"]["pass"] == 6
    # 칸 안 표·그림 · 자동 번호 문단이 든 칸은 운반 문서 XML 에 없는 글이 찍힌다 — 모름
    auto = copy.deepcopy(one)
    auto["cells"][3]["auto"] = True
    by = _by(V.check_table(auto, _draw(full)))
    assert (by["text"]["pass"], by["text"]["fail"], by["text"]["unknown"]) == (5, 0, 1)


def test_unmeasured_core_checks_cap_the_verdict_at_warn():
    """astra 12: 모든 글꼴이 Type3 이라 굵게·글꼴이 전부 미측정인데(모름 12) 괘선 통과(74)에 묻혀 ok 였다 — 글자 크기·굵게·글꼴 가운데 하나라도 **통과 0 · 모름 1 이상**이면 높아야 warn."""
    exp = _grid()
    m = _draw(exp)
    page = m["pages"][0]
    for ln in page["lines"]:
        ln["spans"] = [("T1", s[1], 0, s[3]) for s in ln["spans"]]
        ln["chars"] = [(*c[:6], False) for c in ln["chars"]]
    page["type3"] = {"T1"}
    checks = V.check_table(exp, m)
    by = _by(checks)
    assert (by["bold"]["pass"], by["bold"]["unknown"], by["fontFace"]["pass"], by["fontFace"]["unknown"], by["fontSize"]["pass"]) == (0, 6, 0, 6, 6)
    status, cov, notes = V.summarize(checks, 1)
    assert (cov["pass"], cov["unknown"], cov["fail"]) == (74, 12, 0) and cov["unknown"] / 86 < V.UNKNOWN_SHARE  # 30% 규칙에는 안 걸린다(괘선 통과가 많다)
    assert status == "warn" and any("굵게" in n and "재지 못함" in n for n in notes) and any("글꼴" in n and "재지 못함" in n for n in notes) and not any("글자 크기" in n for n in notes)

    def chk(what, p=0, f=0, u=0):
        return {"what": what, "status": "fail" if f else "pass" if p else "unknown", "pass": p, "fail": f, "unknown": u, "examples": [], "note": ""}
    many = [chk("edge", 500), chk("lineWidth", 500), chk("text", 3)]
    assert V.summarize([*many, chk("fontSize", 3), chk("bold", 3), chk("fontFace", 3)], 1)[0] == "ok"
    assert V.summarize([*many, chk("fontSize", 0, 0, 3), chk("bold", 3), chk("fontFace", 3)], 1)[::2] == ("warn", ["글자 크기를 재지 못함(모름 3 · 통과 0)"])
    assert V.summarize([*many, chk("fontSize", 2, 0, 1), chk("bold", 1, 0, 2), chk("fontFace", 3)], 1)[0] == "ok"   # 하나라도 쟀으면 30% 규칙만
    assert V.summarize([*many, chk("fontSize", 0), chk("bold", 0), chk("fontFace", 0)], 1)[0] == "ok"              # 글이 없는 표(잴 것이 없음)는 미측정이 아니다
    assert V.summarize([*many, chk("fontSize", 3), chk("bold", 0, 1, 2), chk("fontFace", 3)], 1)[0] == "fail"


def test_table_hand_written_measure():
    """그리는 도우미 없이 손으로 적은 잰 값 — 1×2 표(왼 칸 음영), 가로선은 표 끝보다 조금 길다(한글 실측 −0.48 · +0.60pt)."""
    exp = _exp([_cell(0, 0, "가", "#F2F2F2", width=80.0), _cell(0, 1, "12", None, width=120.0)], 1, 2, widths=[80.0, 120.0])
    seg = lambda d, x0, y0, x1, y1: {"dir": d, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "w": 0.36, "color": (0, 0, 0), "dashed": False}  # noqa: E731
    page = {"w": 595.0, "h": 841.0, "sheet": 0, "type3": set(), "tables": [{"rows": 1, "cols": 2, "bbox": [50, 100, 250, 120], "cells": []}],
            "rects": [{"x0": 50.0, "y0": 100.0, "x1": 130.0, "y1": 120.0, "fill": (0.95, 0.95, 0.95)}],
            "segs": [seg("h", 49.52, 100.0, 250.6, 100.0), seg("h", 49.52, 120.0, 250.6, 120.0), seg("v", 50.0, 100.0, 50.0, 120.0), seg("v", 130.0, 100.0, 130.0, 120.0),
                     seg("v", 250.0, 100.0, 250.0, 120.0)],
            "lines": [_text_line(_chars("가"), 60.0, 105.0), _text_line(_chars("12"), 200.0, 105.0, block=1)]}
    checks = V.check_table(exp, {"count": 1, "pages": [page]})
    assert _measured(checks) == {"pass"}, checks
    assert "표 감지(참고) 1×2" in _by(checks)["edge"]["note"]            # find_tables 는 참고로만


def test_table_fails_on_real_differences():
    exp = _grid()
    m = _draw(exp)
    want = copy.deepcopy(exp)
    want["cells"][0]["fill"] = "#FFC000"                                    # 머리 음영이 다름
    want["cells"][2]["fill"] = "#EEEEEE"                                    # 음영 없는 칸에 음영을 기대
    want["cells"][4]["fill"] = None                                         # 음영 칸에 음영 없음을 기대
    want["cells"][3]["chars"] = _chars("100", bold=True, align="right")     # 굵게
    want["cells"][5]["chars"] = _chars("100", sizePt=12.0)                  # 크기
    want["cells"][2]["chars"] = _chars("인건비", color="#C00000")           # 색
    want["cells"][1]["chars"] = _chars("단가", bold=True)                   # 글
    want["cells"][0]["edges"] = {**want["cells"][0]["edges"], "t": {**THICK, "widthMm": 0.12}}  # 굵은 선 자리에 가는 선을 기대
    by = _by(V.check_table(want, m))
    assert by["fill"]["fail"] == 3 and {e["where"] for e in by["fill"]["examples"]} == {"A1", "A2", "A3"}
    assert by["fill"]["examples"][0] == {"where": "A1", "want": "#FFC000", "got": "#D9E2F3"}
    assert by["bold"]["fail"] == 1 and by["bold"]["examples"][0]["where"] == "B2"
    assert by["fontSize"]["fail"] == 1 and by["fontSize"]["examples"][0]["want"] == "12pt"
    assert by["color"]["fail"] == 1 and by["color"]["examples"][0]["where"] == "A2"
    assert by["text"]["fail"] == 1 and by["text"]["examples"][0]["where"] == "B1" and by["fontSize"]["unknown"] == 1   # 글이 다른 칸은 글자 모양을 견주지 않는다
    assert by["lineWidth"]["fail"] == 1 and by["lineWidth"]["examples"][0]["where"] == "A1 위"
    assert V.summarize(list(by.values()), 1)[0] == "fail"


def test_table_edges_missing_and_unexpected():
    exp = _grid()
    m = _draw(exp)
    page = m["pages"][0]
    y_mid = 90.0 + 20.0                                                     # 머리행 아래 경계
    page["segs"] = [s for s in page["segs"] if not (s["dir"] == "h" and abs(s["y0"] - y_mid) < 0.1 and s["x0"] < 100)]  # A1 아래 = A2 위 선을 지움
    by = _by(V.check_table(exp, m))
    assert by["edge"]["fail"] == 2 and {e["where"] for e in by["edge"]["examples"]} == {"A1 아래", "A2 위"} and by["edge"]["examples"][0]["got"] == "선 없음"
    # 괘선이 없어야 할 자리(트인 왼쪽 변)에 선이 그려짐
    open_left = copy.deepcopy(exp)
    for i in (0, 2, 4):
        open_left["cells"][i]["edges"]["l"] = None
    by = _by(V.check_table(open_left, _draw(exp)))
    assert by["edge"]["fail"] == 3 and by["edge"]["examples"][0]["want"] == "선 없음"
    assert _measured(V.check_table(open_left, _draw(open_left))) == {"pass"}   # 그 꼴대로 그리면 통과
    # 맞닿은 칸의 맞은편 변에 괘선이 있으면 「없어야 함」 으로 보지 않는다
    one_side = copy.deepcopy(exp)
    one_side["cells"][0]["edges"]["r"] = None                               # A1 오른쪽은 없음 — B1 왼쪽이 그린다
    assert _by(V.check_table(one_side, _draw(exp)))["edge"]["fail"] == 0


def test_table_double_line_and_underline():
    exp = _grid()
    for i in (0, 1):
        exp["cells"][i]["edges"]["b"] = DOUBLE
    m = _draw(exp)
    by = _by(V.check_table(exp, m))
    assert by["edge"]["fail"] == 0 and by["lineWidth"]["fail"] == 0
    assert by["lineWidth"]["unknown"] == 4 and "겹줄" in by["lineWidth"]["note"]     # 겹줄 자리(A1·B1 아래, A2·B2 위)는 굵기를 견주지 않는다
    assert by["fill"]["fail"] == 0                                                  # 겹줄의 두 선이 행 경계 하나로 묶인다
    # 밑줄(글 줄 상자 안의 가로선)은 행 경계·괘선으로 세지 않는다
    ln = m["pages"][0]["lines"][2]
    m["pages"][0]["segs"].append({"dir": "h", "x0": ln["bbox"][0], "y0": ln["bbox"][3] + 1.0, "x1": ln["bbox"][2], "y1": ln["bbox"][3] + 1.0, "w": 0.5, "color": (0, 0, 0), "dashed": False})
    assert len(V.plain_segs(m["pages"][0])) == len(m["pages"][0]["segs"]) - 1
    assert _by(V.check_table(exp, m))["fill"]["unknown"] == 0


def test_table_unknown_when_rows_cannot_be_placed():
    """행 경계 수가 안 맞으면 자리에 기대는 검사는 unknown(실패 아님) — 글은 PDF 에 있는지만 본다."""
    exp = _grid()
    m = _draw(exp)
    m["pages"][0]["segs"].append({"dir": "h", "x0": 60.0, "y0": 97.0, "x1": 260.0, "y1": 97.0, "w": 0.36, "color": (0, 0, 0), "dashed": False})  # 정체 모를 가로선
    by = _by(V.check_table(exp, m))
    assert by["edge"]["status"] == "unknown" and by["fill"]["status"] == "unknown" and by["fontSize"]["status"] == "unknown" and "가로 경계 5개" in by["fill"]["note"]
    assert by["text"]["status"] == "pass" and by["text"]["pass"] == 6 and by["width"]["status"] == "pass"
    status, cov, notes = V.summarize(list(by.values()), 1)
    assert status == "warn" and cov["fail"] == 0 and any("못 잰 것" in n for n in notes)
    # 2쪽 이상도 자리 검사는 unknown
    m2 = _draw(exp)
    m2["count"] = 2
    by = _by(V.check_table(exp, m2))
    assert by["pages"]["status"] == "unknown" and by["edge"]["status"] == "unknown" and V.summarize(list(by.values()), 2)[0] == "warn"
    # 선·음영이 하나도 없는 표
    bare = _exp([_cell(0, 0, "가", None, dict.fromkeys("trbl")), _cell(0, 1, "나", None, dict.fromkeys("trbl"))], 1, 2)
    by = _by(V.check_table(bare, _draw(bare)))
    assert by["width"]["status"] == "unknown" and by["text"]["pass"] == 2 and by["edge"]["status"] == "unknown" and by["edge"]["note"]


def test_row_bounds_zero_height_and_invisible_rows():
    # 높이 0.01pt 로 저장된 행 — 그 위·아래 경계가 겹친다(연구개발계획서 양식 첫 표)
    exp = _exp([_cell(0, 0, "가"), _cell(1, 0, ""), _cell(2, 0, "나")], 3, 1, heights=[20.0, 0.01, 20.0])
    assert V.row_bounds(exp, [100.0, 120.0, 140.0]) == ([100.0, 120.0, 120.0, 140.0], 0)
    assert V.row_bounds(exp, [100.0, 120.0]) is None and V.row_bounds(exp, [100.0, 120.0, 130.0, 140.0]) is None
    by = _by(V.check_table(exp, _draw(exp, ys=[100.0, 120.0, 120.0, 140.0])))
    assert by["text"]["pass"] == 2 and by["edge"]["fail"] == 0 and by["edge"]["pass"] == 8     # 높이 0 인 칸의 변은 안 센다
    # 선 없는 제목 행(맨 위) — 그 위 경계는 PDF 에 없다: 저장된 높이로 어림하고 글·음영 찾기에만 쓴다
    none = dict.fromkeys("trbl")
    exp = _exp([_cell(0, 0, "단위", None, none, cs=2, width=200.0), _cell(1, 0, "구분", "#D9E2F3"), _cell(1, 1, "값", "#D9E2F3"), _cell(2, 0, "가"), _cell(2, 1, "1")], 3, 2,
               heights=[15.0, 20.0, 20.0])
    Y, guessed = V.row_bounds(exp, [105.0, 125.0, 145.0])
    assert Y == [90.0, 105.0, 125.0, 145.0] and guessed == 1
    by = _by(V.check_table(exp, _draw(exp)))
    assert _measured(list(by.values())) == {"pass"} and by["text"]["pass"] == 5


def test_cell_boxes_follow_each_cells_own_width():
    """한글은 행마다 칸의 제 폭을 쌓는다 — 한 칸만 넓힌 표는 열 경계가 행마다 다르다. 위에서 내려온 합친 칸은 그 칸의 오른끝에서 잇는다."""
    exp = _exp([_cell(0, 0, "가", rs=2, width=50.0), _cell(0, 1, "나", width=60.0), _cell(0, 2, "다", width=90.0),
                _cell(1, 1, "라", width=100.0), _cell(1, 2, "마", width=50.0)], 2, 3, widths=[50.0, 60.0, 90.0])
    box, rows = V.cell_boxes(exp, V._occupancy(exp), 10.0, 1.0, [0.0, 20.0, 40.0])
    assert [b[0] for b in box] == [10.0, 60.0, 120.0, 60.0, 160.0] and box[0][3] == 40.0 and box[3][2] == 160.0
    assert rows[1] == [(10.0, 60.0, 0), (60.0, 160.0, 3), (160.0, 210.0, 4)]
    assert _measured(V.check_table(exp, _draw(exp))) == {"pass"}


def test_table_font_substitution_is_a_warning_not_a_failure():
    exp = _grid()
    m = _draw(exp)
    line = m["pages"][0]["lines"][3]                                         # B2 「100」 을 다른 글꼴로 찍음
    line["spans"] = [("ArialMT", s[1], s[2], s[3]) for s in line["spans"]]
    checks = V.check_table(exp, m)
    by = _by(checks)
    assert by["fontFace"]["status"] == "unknown" and by["fontFace"]["fail"] == 0 and by["fontFace"]["unknown"] == 1 and by["fontFace"]["substituted"] == 1
    assert "대체 글꼴로 출력 — 맑은 고딕 → ArialMT" in by["fontFace"]["note"] and by["fontFace"]["examples"][0]["where"] == "B2"
    status, cov, notes = V.summarize(checks, 1)
    assert status == "warn" and cov["fail"] == 0 and "대체 글꼴로 출력 1곳" in notes
    # Type3(한글 전용 글꼴): 굵게·글꼴은 unknown — 대체로 세지 않는다
    exp2 = _exp([_cell(0, 0, "가", font="한양신명조", bold=True), _cell(0, 1, "나")], 1, 2)
    m2 = _draw(exp2)
    m2["pages"][0]["lines"][0]["spans"] = [("T1", 10.0, 0, 0)]
    m2["pages"][0]["lines"][0]["chars"] = [(*c[:6], False) for c in m2["pages"][0]["lines"][0]["chars"]]
    m2["pages"][0]["type3"] = {"T1"}
    by = _by(V.check_table(exp2, m2))
    assert by["bold"]["unknown"] == 1 and by["bold"]["fail"] == 0 and by["fontFace"]["unknown"] == 1 and not by["fontFace"].get("substituted")
    assert "Type3" in by["bold"]["note"]


def test_face_verdict_is_loose_about_names():
    assert V.face_verdict("맑은 고딕", "MalgunGothicBold") == "same"          # 오차 기준의 별칭 + 굵게 꼬리
    assert V.face_verdict("함초롬돋움", "ABCDEF+HCRDotum") == "same"          # 부분 글꼴 머리
    assert V.face_verdict("돋움", "DotumChe") == "same" and V.face_verdict("Malgun Gothic", "malgun gothic") == "same"
    assert V.face_verdict("Arial", "MalgunGothic") == "subst" and V.face_verdict("맑은 고딕", "HCRBatang-Bold") == "subst"
    assert V.face_verdict("한양신명조", "T1", type3=True) == "unknown" and V.face_verdict("휴먼명조", "????") == "unknown" and V.face_verdict(None, "Dotum") == "unknown"

    class Index:  # 이 PC 글꼴 이름표 흉내 — 한글 이름과 PostScript 이름을 같은 가족으로
        def family(self, name):
            return {"hy견고딕": "hygothicextra", "h2gtre": "hygothicextra", "휴먼명조": "휴먼명조"}.get(V.fonts._norm(name or ""))

        def broken_match(self, pdf_name, key):
            return key == "휴먼명조" and pdf_name == "????"
    assert V.face_verdict("HY견고딕", "H2gtrE") == "subst" and V.face_verdict("HY견고딕", "H2gtrE", index=Index()) == "same"
    assert V.face_verdict("휴먼명조", "????", index=Index()) == "same"


def test_summarize_rules():
    def chk(what, p=0, f=0, u=0, status=None, **more):
        return {"what": what, "status": status or ("fail" if f else "pass"), "pass": p, "fail": f, "unknown": u, "examples": [], "note": "", **more}
    assert V.summarize([chk("a", 10)], 1)[0] == "ok"
    assert V.summarize([chk("a", 10), chk("b", 9, 1)], 1)[0] == "fail"
    assert V.summarize([chk("a", 7, 0, 3)], 1)[0] == "ok" and V.summarize([chk("a", 6, 0, 4)], 1)[0] == "warn"      # unknown 30% 초과
    assert V.summarize([chk("a", 10), chk("fontFace", 9, 0, 1, substituted=1)], 1)[0] == "warn"
    assert V.summarize([chk("a", 10)], 2)[0] == "warn" and V.summarize([], 1)[0] == "warn"
    status, cov, _ = V.summarize([chk("a", 3), V.unsupported("lineSpacing", "x"), V.unsupported("paraSpacing", "y")], 1)
    assert status == "ok" and cov == {"pass": 3, "fail": 0, "unknown": 0, "unsupported": 2}


# ---- 운반 문서에서 읽는 기대값 -------------------------------------------------------------------------------------

def _carrier_table():
    """빈 바탕에서 HwpxDoc 연산만으로 지은 표 운반 문서(2×2 — 머리행 음영·굵게, 바깥 0.4mm)."""
    car = HwpxDoc(BASE.read_bytes())
    bl = car.blocks()
    first, plain = bl[0]["id"], next(b["id"] for b in bl if b["type"] == "table")
    norm = table_make.normalize({"rows": [[{"text": "구분"}, {"text": "값"}], [{"text": "가"}, {"text": "12"}]], "headerRows": 1, "headerCols": 0, "footRows": 0})
    made = car.table_make(first, plain, norm, {"headerRows": 0, "headerCols": 0, "footRows": 0})
    car.delete_blocks(plain, plain)
    for c in car.table_block(made["table"])["cells"]:
        cur = car.get_cell_format(c["id"])
        text = car.derive_format(cur["text"], {"sizePt": 11 if c["row"] == 0 else 9, "bold": c["row"] == 0, "color": "#000000"})
        car.apply_cell_format([c["id"]], {"text": text, "fill": "#D9E2F3" if c["row"] == 0 else None, "valign": "center", "marginsMm": cur["marginsMm"]}, ["text", "fill"])
        car.set_cell_edges(c["id"], {"top": {"type": "SOLID", "width": "0.4 mm", "color": "#000000"}} if c["row"] == 0 else {"bottom": {"type": "NONE", "width": "0.1 mm", "color": "#000000"}})
    return car.save()


def test_expect_table_reads_the_carrier():
    exp = V.expect_table(HwpxDoc(_carrier_table()))
    assert (exp["rows"], exp["cols"]) == (2, 2) and len(exp["cells"]) == 4 and abs(sum(exp["widthsPt"]) - sum(c["widthPt"] for c in exp["cells"][:2])) < 0.1
    a1, b2 = exp["cells"][0], exp["cells"][3]
    assert a1["fill"] == "#D9E2F3" and a1["edges"]["t"] == {"type": "SOLID", "widthMm": 0.4, "color": "#000000"} and b2["edges"]["b"] is None and b2["fill"] is None
    assert [x[0] for x in a1["chars"]] == ["구", "분"] and a1["chars"][0][2]["bold"] is True and a1["chars"][0][2]["sizePt"] == 11.0 and b2["chars"][0][2]["sizePt"] == 9.0
    assert _measured(V.check_table(exp, _draw(exp))) == {"pass"}                # 그 꼴대로 그린 쪽은 모두 통과
    assert V.expect_table(HwpxDoc(_carrier_text()[0])) is None                               # 표 없는 문서


def _carrier_text():
    car = HwpxDoc(BASE.read_bytes())
    bl = car.blocks()
    ref, plain, ids = bl[0]["id"], next(b["id"] for b in bl if b["type"] == "table"), []
    for text, ch in (("1. 견본 글입니다", {"sizePt": 14, "bold": True, "align": "left", "indentLeftMm": 0, "firstLineMm": 0}),
                     ("  - 견본 글입니다", {"sizePt": 9, "bold": False, "align": "left", "indentLeftMm": 10, "firstLineMm": 3, "color": "#C00000"})):
        ref = car.insert_line(ref, text)
        car.apply_format([ref], car.derive_format(car.get_format(ref), ch))
        ids.append(ref)
    car.delete_blocks(plain, plain)
    return car.save(), ids


def test_expect_text_pairs_paragraphs_with_items():
    data, _ = _carrier_text()
    exp = V.expect_text(HwpxDoc(data), {"items": [{"key": "h1", "marker": {"mode": "literal"}}, {"key": "h2", "marker": {"mode": "auto"}}]})
    assert exp["leftMm"] == 20.0 and [i["key"] for i in exp["items"]] == ["h1", "h2"] and [i["auto"] for i in exp["items"]] == [False, True]
    assert exp["items"][0]["text"] == "1. 견본 글입니다" and exp["items"][1]["format"]["indentLeftMm"] == 10.0
    assert [i["key"] for i in V.expect_text(HwpxDoc(data))["items"]] == ["i1", "i2"]         # meta 가 없으면 차례로 지은 key
    assert V.expect_text(HwpxDoc(BASE.read_bytes())) is None                                 # 견본 문단이 없는 문서(빈 바탕)


# ---- 글 견줌 ------------------------------------------------------------------------------------------------------

def _text_exp(*items, left=20.0):
    out = []
    for n, (text, kw) in enumerate(items, 1):
        auto = kw.pop("auto", False)
        out.append({"key": f"i{n}", "id": f"p{n}", "text": text, "format": _fmt(**kw), "runs": None, "auto": auto})
    return {"leftMm": left, "metaItems": len(out), "items": out}


def _text_page(exp, shift=0.0, skip=()):
    lines = []
    for n, it in enumerate(exp["items"]):
        if it["key"] in skip or not it["text"]:
            continue
        f = it["format"]
        x = (exp["leftMm"] + f["indentLeftMm"] + max(f["firstLineMm"], 0)) * V.PT_MM + shift
        lines.append(_text_line([(ch if V.key_text(ch) else "", ch, f) for ch in it["text"]], x, 100.0 + 30 * n, block=n))
    return {"count": 1, "pages": [{"w": 595.0, "h": 841.0, "sheet": 0, "lines": lines, "segs": [], "rects": [], "tables": [], "type3": set()}]}


def test_text_items_pass_and_fail():
    exp = _text_exp(("1. 견본 글입니다 하나", {"sizePt": 14.0, "bold": True}), ("□ 견본 글입니다 둘", {"indentLeftMm": 5.0}),
                    ("- 견본 글입니다 셋", {"indentLeftMm": 10.0, "firstLineMm": 3.0, "color": "#C00000"}))
    checks = V.check_text(exp, _text_page(exp))
    assert [c["what"] for c in checks] == [*V.TEXT_CHECKS, "lineSpacing", "paraSpacing"]
    st = _status(checks)
    assert all(st[k] == "pass" for k in V.TEXT_CHECKS) and st["lineSpacing"] == st["paraSpacing"] == "unsupported"
    status, cov, _ = V.summarize(checks, 1)
    assert status == "ok" and cov["unsupported"] == 2 and _by(checks)["indent"]["pass"] == 3
    # 왼끝이 5mm 밀림 → indent fail(±1mm) · 그 밖은 통과
    by = _by(V.check_text(exp, _text_page(exp, shift=5 * V.PT_MM)))
    assert by["indent"]["fail"] == 3 and by["indent"]["examples"][0]["want"] == "20.0mm" and by["fontSize"]["fail"] == 0
    assert _by(V.check_text(exp, _text_page(exp, shift=0.8 * V.PT_MM)))["indent"]["fail"] == 0
    # 견본 줄이 PDF 에 없음 → text fail, 그 item 의 나머지는 unknown
    by = _by(V.check_text(exp, _text_page(exp, skip={"i2"})))
    assert by["text"]["fail"] == 1 and by["text"]["examples"][0]["where"] == "i2" and by["fontSize"]["unknown"] == 1 and by["indent"]["unknown"] == 1
    # 기대값이 다르면(굵게·크기·색) fail
    wrong = copy.deepcopy(exp)
    wrong["items"][0]["format"].update(bold=False, sizePt=12.0)
    wrong["items"][2]["format"]["color"] = "#000000"
    by = _by(V.check_text(wrong, _text_page(exp)))
    assert by["bold"]["fail"] == 1 and by["fontSize"]["fail"] == 1 and by["color"]["fail"] == 1 and by["color"]["examples"][0]["where"] == "i3"


def test_text_indent_unknown_for_centered_and_auto():
    exp = _text_exp(("가운데 견본 글입니다", {"align": "center"}), ("자동 번호 견본 글입니다", {"auto": True}), ("", {}))
    by = _by(V.check_text(exp, _text_page(exp)))
    assert by["indent"]["unknown"] == 3 and by["indent"]["fail"] == 0 and by["text"]["pass"] == 2 and by["text"]["unknown"] == 1   # 빈 견본은 unknown


def test_text_item_count_mismatch_fails():
    """astra 12: 운반 문서의 견본 문단 수가 meta 의 item 수와 달라도 알림 글만 붙고 ok 였다 — n번째 견본 문단 ↔ items[n] 의 짝이 깨진 것이므로 fail."""
    exp = _text_exp(("1. 견본 글입니다 하나", {"sizePt": 14.0}), ("□ 견본 글입니다 둘", {}))
    assert V.summarize(V.check_text(exp, _text_page(exp)), 1)[0] == "ok"
    for n in (1, 3, 0):
        checks = V.check_text({**exp, "metaItems": n}, _text_page(exp))
        text = _by(checks)["text"]
        assert text["status"] == "fail" and text["fail"] == 1 and text["pass"] == 2 and "수가 다름" in text["note"], n
        assert text["examples"][0] == {"where": "문서", "want": f"item {n}개", "got": "견본 문단 2개"} and V.summarize(checks, 1)[0] == "fail"
    assert _by(V.check_text({**exp, "metaItems": None}, _text_page(exp)))["text"]["fail"] == 0  # meta 없이 부른 것(item 수를 모름)은 견주지 않는다
    data, _ = _carrier_text()
    items = [{"key": "i1", "marker": {"mode": "literal"}}]
    assert V.expect_text(HwpxDoc(data), {"items": items})["metaItems"] == 1 and V.expect_text(HwpxDoc(data))["metaItems"] is None
    assert V.expect_text(HwpxDoc(data), {"kind": "text"})["metaItems"] is None and V.expect_text(HwpxDoc(data), {"items": []})["metaItems"] == 0


# ---- PDF 재기(PyMuPDF 로 지은 PDF) ---------------------------------------------------------------------------------

def _pdf(tmp_path, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(60, 100, 160, 120), color=None, fill=(0.85, 0.89, 0.95))      # 음영
        page.draw_rect(fitz.Rect(60, 100, 260, 140), color=(0, 0, 0), width=1.0)               # 바깥 테두리(사각형 → 선 넷)
        page.draw_line((160, 100), (160, 140), color=(0.5, 0.5, 0.5), width=0.36)
        page.draw_line((60, 120), (260, 120), color=(0, 0, 0), width=0.36, dashes="[2 2] 0")
        page.draw_rect(fitz.Rect(60, 150, 260, 150.8), color=None, fill=(0, 0, 0))             # 가는 채움 사각형 = 선(Word 꼴)
        page.draw_line((60, 160), (260, 200), color=(0, 0, 0), width=0.5)                      # 비스듬한 선은 뺀다
        page.insert_text((70, 114), "Head", fontname="hebo", fontsize=10)
        page.insert_text((170, 134), "12", fontname="helv", fontsize=9, color=(0.75, 0, 0))
    path = tmp_path / "made.pdf"
    doc.save(path)
    return path


def test_measure_pdf_reads_text_lines_and_fills(tmp_path):
    path = _pdf(tmp_path)
    for src in (path, path.read_bytes()):                                   # 경로 · 바이트 둘 다
        m = V.measure_pdf(src)
        assert m["count"] == 1 and len(m["pages"]) == 1
        p = m["pages"][0]
        assert [r["fill"] for r in p["rects"]] == [pytest.approx((0.85, 0.89, 0.95), abs=0.01)] and p["rects"][0]["x1"] == pytest.approx(160, abs=0.1)
        hs, vs = [s for s in p["segs"] if s["dir"] == "h"], [s for s in p["segs"] if s["dir"] == "v"]
        assert len(vs) == 3 and len(hs) == 4 and all(s["dir"] in "hv" for s in p["segs"])       # 테두리 4 + 세로 1 + 점선 1 + 가는 사각형 1(비스듬한 선 없음)
        assert sorted(round(s["w"], 2) for s in hs) == [0.36, 0.8, 1.0, 1.0] and [s["dashed"] for s in hs if abs(s["y0"] - 120) < 0.1] == [True]
        head = next(ln for ln in p["lines"] if ln["text"].strip() == "Head")
        assert head["spans"][0][0] == "Helvetica-Bold" and head["spans"][0][1] == pytest.approx(10) and all(c[6] for c in head["chars"])
        num = next(ln for ln in p["lines"] if ln["text"].strip() == "12")
        assert num["spans"][0][3] == 0xBF0000 and not num["chars"][0][6]
        assert p["tables"] and p["tables"][0]["cols"] >= 2
    assert V.measure_pdf(_pdf(tmp_path, pages=3), tables=False, limit=2)["count"] == 3 and len(V.measure_pdf(path, limit=0)["pages"]) == 0
    png = V.proof_png(path)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pix = fitz.Pixmap(png)
    assert pix.width < 595 * V.PROOF_DPI / 72 * 0.6 and pix.height < 842 * V.PROOF_DPI / 72 * 0.4   # 내용 둘레로 잘랐다


def test_text_in_page_bands_is_kept(tmp_path):
    """pdf_map.read_pdf 는 위·아래 8% 띠의 숫자뿐인 줄을 쪽 번호로 보고 뺀다 — 검증의 측정은 빼지 않는다(운반 문서 칸 글 「0」)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((70, 40), "0", fontname="helv", fontsize=10)
    page.insert_text((70, 400), "body", fontname="helv", fontsize=10)
    path = tmp_path / "band.pdf"
    doc.save(path)
    from app import pdf_map
    assert [ln["text"].strip() for ln in pdf_map.read_pdf(path, False, True)[0]["lines"]] == ["body"]
    assert [ln["text"].strip() for ln in V.measure_pdf(path)["pages"][0]["lines"]] == ["0", "body"]


# ---- run 의 흐름(가짜 출력) ----------------------------------------------------------------------------------------

def _fake_export(tmp_path, monkeypatch, draw):
    """한글 대신: export_pdf 가 빈 PDF 를 캐시 이름으로 쓰고, measure_pdf 는 draw(운반 문서의 기대값) 를 돌려준다."""
    calls = []

    def export(data, limit=None, fmt="hwpx"):
        out = V._cached_pdf(data)
        calls.append({"limit": limit, "cached": out.exists()})
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open()
        doc.new_page(width=595, height=842).insert_text((70, 100), "proof", fontname="helv", fontsize=10)
        doc.save(out)
        return out
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "export_pdf", export)
    monkeypatch.setattr(V, "measure_pdf", lambda path, **kw: draw())
    return calls


def test_run_builds_record_and_proof_files(tmp_path, monkeypatch):
    data = _carrier_table()
    exp = V.expect_table(HwpxDoc(data))
    calls = _fake_export(tmp_path, monkeypatch, lambda: _draw(exp))
    rec, files = V.run(data, {"kind": "table", "revision": "r2", "carrierSha256": "c" * 64, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}})
    assert rec["status"] == "ok" and rec["pages"] == 1 and rec["revision"] == "r2" and rec["profile"] == "table-v1" and rec["note"] == ""
    assert [c["what"] for c in rec["checks"]] == ["render", *V.TABLE_CHECKS, *(k for k, _ in V.UNSUPPORTED_TABLE)] and rec["checks"][0]["status"] == "pass" and rec["coverage"]["unsupported"] == 5
    assert rec["coverage"]["fail"] == 0 and rec["coverage"]["pass"] == sum(c["pass"] for c in rec["checks"])
    assert rec["subjectHash"] == V.subject_hash({"carrierSha256": "c" * 64, "bands": {"headerRows": 1, "headerCols": 0, "footRows": 0}})
    assert files["proof.pdf"][:5] == b"%PDF-" and files["proof.png"][:4] == b"\x89PNG" and calls == [{"limit": V.LIMIT, "cached": False}]
    # 다시 검증(force): 캐시 PDF 를 지우고 다시 출력한다 — force 가 아니면 캐시가 그대로 있다
    V.run(data, {"kind": "table"})
    V.run(data, {"kind": "table"}, force=True)
    assert [c["cached"] for c in calls] == [False, True, False]
    # 어긋난 출력 → fail + 보기
    wrong = copy.deepcopy(exp)
    wrong["cells"][0]["fill"] = "#FFC000"
    monkeypatch.setattr(V, "measure_pdf", lambda path, **kw: _draw(wrong))
    rec, _ = V.run(data, {"kind": "table"})
    assert rec["status"] == "fail" and next(c for c in rec["checks"] if c["what"] == "fill")["examples"][0]["got"] == "#FFC000"


def test_run_text_profile_and_failures_never_raise(tmp_path, monkeypatch):
    data, _ = _carrier_text()
    exp = V.expect_text(HwpxDoc(data))
    _fake_export(tmp_path, monkeypatch, lambda: _text_page(exp))
    rec, files = V.run(data, {"kind": "text", "items": [{"key": "i1", "level": 1}, {"key": "i2", "level": 2}]})
    assert rec["profile"] == "text-v1" and rec["status"] in ("ok", "warn") and rec["coverage"]["fail"] == 0 and rec["coverage"]["unsupported"] == 2
    assert [c["what"] for c in rec["checks"]][:3] == ["render", "pages", "text"] and "proof.png" in files
    rec, _ = V.run(data, {"kind": "text", "items": [{"key": "i1", "level": 1}]})  # 견본 문단은 둘인데 meta 의 item 은 하나
    assert rec["status"] == "fail" and "수가 다름" in next(c for c in rec["checks"] if c["what"] == "text")["note"]
    # 한글 출력 실패(시간 초과) → fail + note
    def boom(data, limit=None, fmt="hwpx"):
        raise TimeoutError("한글 PDF 출력 120s 초과")
    monkeypatch.setattr(pdf_render, "export_pdf", boom)
    rec, files = V.run(data, {"kind": "text"})
    assert rec["status"] == "fail" and "120s 초과" in rec["note"] and rec["checks"][0]["what"] == "render" and rec["checks"][0]["status"] == "fail" and files == {}
    # 못 읽는 운반 문서 · 표 없는 운반 문서 · 견줌 중 오류
    assert "읽지 못했습니다" in V.run(b"not a zip", {"kind": "table"})[0]["note"]
    rec, _ = V.run(data, {"kind": "table"})
    assert rec["status"] == "fail" and rec["note"] == "운반 문서에 표가 없습니다"
    monkeypatch.setattr(V, "expect_text", lambda *a: 1 / 0)
    assert V.run(data, {"kind": "text"})[0]["status"] == "fail"


# ---- 2차: 첫 쪽 전체 그림 · 표지 서식(cover-v1 — spec_서식복사 ② §13·§14) ------------------------------------------------------

def test_proof_png_full_is_the_whole_first_page(tmp_path):
    """쪽 설정·표지의 견본 그림은 내용 둘레를 자르지 않은 첫 쪽 전체 — 긴 변 1,100px 안팎 · 110dpi 를 넘지 않는다. 경로·바이트 둘 다 받는다(끝점이 저장된 proof.pdf 에서 다시 그린다)."""
    path = _pdf(tmp_path)
    for src in (path, path.read_bytes()):
        png = V.proof_png(src, full=True)
        pix = fitz.Pixmap(png)
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and abs(pix.height - V.PROOF_FULL_PX) <= 12 and pix.width == pytest.approx(pix.height * 595 / 842, abs=2)   # A4 한 쪽 통째로(약 94dpi)
        assert pix.height <= 842 * V.PROOF_DPI / 72 + 1
    small = fitz.open()
    small.new_page(width=200, height=300).insert_text((20, 40), "x", fontname="helv", fontsize=10)      # 작은 쪽 — 110dpi 를 넘겨 키우지 않는다
    spath = tmp_path / "small.pdf"
    small.save(spath)
    assert fitz.Pixmap(V.proof_png(spath, full=True)).height == pytest.approx(300 * V.PROOF_DPI / 72, abs=2)
    assert fitz.Pixmap(V.proof_png(path)).height < fitz.Pixmap(V.proof_png(path, full=True)).height * 0.4   # 기본은 전처럼 내용 둘레


COVER_PAGE = {"widthMm": 210.0, "heightMm": 297.0, "landscape": False, "marginsMm": {"l": 20.0, "r": 20.0, "t": 30.0, "b": 20.0, "gutter": 0.0}}


def _cover(**kw):
    """표지 서식의 meta — 글 부분 둘(제목 · 기관명) 사이에 표 하나."""
    return {"kind": "cover", "page": COVER_PAGE, "parts": [{"key": "p1", "type": "text", "role": "title", "sample": "제목", "format": _fmt(sizePt=22.0, bold=True)},
                                                             {"key": "p2", "type": "table", "rows": 2, "cols": 2},
                                                             {"key": "p3", "type": "text", "role": "org", "sample": "기관명", "format": _fmt(sizePt=14.0, fontLatin="Arial")}], **kw}


def _cover_page(exp, w=595.0, h=841.0):
    page = _text_page({"leftMm": exp["leftMm"], "items": exp["items"]})
    page["pages"][0].update(w=w, h=h)
    return page


def test_cover_checks_text_parts_and_never_counts_tables_as_passed():
    exp = V.expect_cover(_cover())
    assert exp["page"] == {"widthMm": 210.0, "heightMm": 297.0, "sizeTolMm": V.PAGE_TOL_HWPX} and exp["leftMm"] == 20.0 and exp["tables"] == 1
    assert [(i["key"], i["id"], i["text"], i["format"]["sizePt"]) for i in exp["items"]] == [("p1", "c1", "제목", 22.0), ("p3", "c3", "기관명", 14.0)]   # 글 부분만 — 표 부분은 견주지 않는다
    checks = V.check_cover(exp, _cover_page(exp))
    assert [c["what"] for c in checks] == [*V.COVER_CHECKS, "coverLayout", "coverColor", "coverTable"]
    st = _status(checks)
    assert all(st[k] == "pass" for k in V.COVER_CHECKS) and st["coverLayout"] == st["coverColor"] == st["coverTable"] == "unsupported" and "표 1개" in _by(checks)["coverTable"]["note"]
    status, cov, _ = V.summarize(checks, 1)
    assert status == "ok" and cov["unsupported"] == 3 and _by(checks)["text"]["pass"] == 2 and cov["fail"] == 0
    # 글자 크기·굵게가 다르면 그 부분이 fail · 쪽 크기가 다르면 pageSize fail
    wrong = V.expect_cover({**_cover(), "parts": [{**_cover()["parts"][0], "format": _fmt(sizePt=18.0)}, *_cover()["parts"][1:]]})
    by = _by(V.check_cover(wrong, _cover_page(exp)))
    assert by["fontSize"]["fail"] == 1 and by["bold"]["fail"] == 1 and by["fontSize"]["examples"][0]["where"] == "p1" and by["pageSize"]["status"] == "pass"
    by = _by(V.check_cover(exp, _cover_page(exp, w=612.0, h=792.0)))
    assert by["pageSize"]["status"] == "fail" and by["pageSize"]["examples"][0]["want"] == "210.0×297.0mm" and by["fontSize"]["fail"] == 0
    # 견본 줄이 PDF 에 없으면 text fail(안 잰 것을 통과로 읽지 않는다)
    gone = _text_page({"leftMm": 20.0, "items": exp["items"]}, skip={"p3"})
    assert _by(V.check_cover(exp, gone))["text"]["fail"] == 1 and V.summarize(V.check_cover(exp, gone), 1)[0] == "fail"


def test_cover_expectations_follow_the_format_and_missing_pieces():
    assert V.PROFILES["cover"] == "cover-v1" and V.expect_cover({"kind": "cover", "parts": []}) is None and V.expect_cover({"kind": "cover"}) is None and V.expect_cover(None) is None
    dx = V.expect_cover(_cover(), "docx", own={"marginsMm": {"l": 25.0}})
    assert dx["page"]["sizeTolMm"] == V.PAGE_TOL and dx["leftMm"] == 25.0 and "fontLatin" not in dx["items"][1]["format"] and dx["items"][1]["format"]["sizePt"] == 14.0   # docx 로 옮기는 값만
    assert V.expect_cover(_cover())["items"][1]["format"]["fontLatin"] == "Arial"
    given = V.expect_cover(_cover(), parts=[{"key": "v1", "type": "text", "sample": "보기에서 읽은 글", "format": _fmt()}])   # 부분을 따로 주면(운반 문서의 보기) 그것으로
    assert [i["key"] for i in given["items"]] == ["v1"] and given["tables"] == 0
    # 글 부분이 없는 표지(표 하나뿐인 양식의 표지) — 글 검사는 「재지 못함」
    only = V.expect_cover({"kind": "cover", "page": COVER_PAGE, "parts": [{"key": "p1", "type": "table", "rows": 3, "cols": 4}]})
    st = _status(V.check_cover(only, _cover_page({"leftMm": 20.0, "items": []})))
    assert st["pageSize"] == "pass" and all(st[k] == "unsupported" for k in V.COVER_CHECKS[1:]) and st["coverTable"] == "unsupported"
    # 쪽 설정을 모르는 표지 — pageSize 는 모름
    bare = V.expect_cover({"kind": "cover", "parts": _cover()["parts"]})
    assert bare["page"] is None and _status(V.check_cover(bare, _cover_page(bare)))["pageSize"] == "unknown"
    # 대상 해시 — 부분의 역할·쪽 설정이 바뀌면 달라지고, 견본 글·이름으로는 안 달라진다
    meta = {**_cover(), "carrierSha256": "a" * 64}
    h = V.subject_hash(meta)
    renamed = {**meta, "name": "새 이름", "parts": [{**meta["parts"][0], "sample": "다른 견본"}, *meta["parts"][1:]]}
    assert V.subject_hash(renamed) == h and V.subject_hash({**meta, "parts": [{**meta["parts"][0], "role": "subtitle"}, *meta["parts"][1:]]}) != h
    assert V.subject_hash({**meta, "page": {**COVER_PAGE, "widthMm": 297.0}}) != h


def test_run_cover_profile_and_full_page_proof(tmp_path, monkeypatch):
    """표지 서식의 한글 쪽 검증(가짜 출력) — profile cover-v1 · 부분은 표지 모듈이 없으면 meta.parts · 견본 그림은 첫 쪽 전체(표·글 서식은 전처럼 내용 둘레)."""
    monkeypatch.delattr(app, "style_cover", raising=False)
    monkeypatch.setitem(sys.modules, "app.style_cover", None)                 # 표지 모듈이 아직 없다 — meta 의 부분으로 견준다
    meta = _cover(revision="r3")
    exp = V.expect_cover(meta)
    assert V.cover_parts(BASE.read_bytes(), meta) == meta["parts"] == V.cover_parts(None, meta)
    assert V.run(b"", {"kind": "cover"})[0]["profile"] == "cover-v1"          # 한글 없이 — 출력 없음
    _fake_export(tmp_path, monkeypatch, lambda: _cover_page(exp, h=842.0))
    rec, files = V.run(BASE.read_bytes(), meta)
    assert rec["profile"] == "cover-v1" and rec["status"] in ("ok", "warn") and rec["coverage"]["fail"] == 0 and rec["revision"] == "r3"
    assert [c["what"] for c in rec["checks"]] == ["render", *V.COVER_CHECKS, "coverLayout", "coverColor", "coverTable"]
    assert fitz.Pixmap(files["proof.png"]).height > 1000                      # 첫 쪽 전체(A4 = 1,100px 안팎)
    rec, _ = V.run(BASE.read_bytes(), {"kind": "cover", "parts": []})
    assert rec["status"] == "fail" and rec["note"] == "표지 서식에 부분(meta.parts)이 없습니다"
    data, _ = _carrier_text()
    text = V.expect_text(HwpxDoc(data))
    monkeypatch.setattr(V, "measure_pdf", lambda path, **kw: _text_page(text))
    _, files = V.run(data, {"kind": "text"})
    assert fitz.Pixmap(files["proof.png"]).height < 300                       # 글 서식은 전처럼 내용 둘레로 자른다
    # 표지 모듈이 있으면 그 보기의 부분으로(운반 문서에서 읽은 것)
    fake = types.ModuleType("app.style_cover")
    fake.view = lambda carrier, m: {"page": m.get("page"), "parts": [{"key": "v1", "type": "text", "sample": "보기", "format": _fmt()}]}
    monkeypatch.setitem(sys.modules, "app.style_cover", fake)
    monkeypatch.setattr(app, "style_cover", fake, raising=False)
    assert [p["key"] for p in V.cover_parts(b"carrier", meta)] == ["v1"]
    fake.view = lambda carrier, m: 1 / 0                                      # 보기를 못 지으면 meta 의 부분으로
    assert V.cover_parts(b"carrier", meta) == meta["parts"]


# ---- 작업(start) ---------------------------------------------------------------------------------------------------

@pytest.fixture
def lib(monkeypatch):
    """style_lib 흉내(이웃 모듈과 무관하게) — get·carrier·put_verify · pin·unpin 만. events = 부른 차례."""
    fake = types.ModuleType("app.style_lib")
    fake.metas = {"s1": {"id": "s1", "revision": "r1", "kind": "table", "carrierSha256": "d" * 64}}
    fake.put, fake.events = [], []
    fake.get = lambda sid: fake.metas.get(sid)
    fake.carrier = lambda sid, rid=None: b"carrier-" + rid.encode()
    fake.put_verify = lambda sid, rid, record, files=None: fake.events.append(f"put {rid}") or fake.put.append((sid, rid, record, files)) or True
    fake.pin = lambda sid, rid: fake.events.append(f"pin {rid}") or True
    fake.unpin = lambda sid, rid: fake.events.append(f"unpin {rid}")
    monkeypatch.setitem(sys.modules, "app.style_lib", fake)
    monkeypatch.setattr(app, "style_lib", fake, raising=False)
    return fake


def _wait(cond, seconds=5.0):
    end = time.time() + seconds
    while not cond() and time.time() < end:
        time.sleep(0.01)
    return cond()


def test_start_runs_once_and_attaches_to_the_starting_revision(lib, monkeypatch):
    gate, seen = threading.Event(), []

    def run(carrier, meta, force=False):
        seen.append((carrier, meta["revision"], force))
        gate.wait(5)
        return {"status": "ok", "revision": meta["revision"], "checks": []}, {"proof.png": b"png"}
    monkeypatch.setattr(V, "run", run)
    assert not V.running("s1") and V.job("s1") is None
    assert V.start("s1") == {"status": "running", "revision": "r1"}
    assert _wait(lambda: seen) and V.running("s1") and V.job("s1")["status"] == "running"
    assert lib.events == ["pin r1"]                                          # 시작할 때의 revision 을 붙든다 — 도는 동안 치워지지 않게(style_lib.pin)
    lib.metas["s1"] = {**lib.metas["s1"], "revision": "r2"}                  # 도는 사이 새 revision
    assert V.start("s1", force=True) == {"status": "running", "revision": "r1"}   # 도는 동안 또 걸면 그 기록 그대로 — 새로 돌리지 않는다
    gate.set()
    assert _wait(lambda: not V.running("s1")) and len(seen) == 1 and seen[0] == (b"carrier-r1", "r1", False)
    assert lib.put == [("s1", "r1", {"status": "ok", "revision": "r1", "checks": []}, {"proof.png": b"png"})]   # 시작할 때의 revision 에 붙인다
    assert lib.events == ["pin r1", "put r1", "unpin r1"]                    # 기록을 붙인 뒤에 놓는다
    assert V.start("s1", force=True) == {"status": "running", "revision": "r2"}
    assert _wait(lambda: len(lib.put) == 2) and seen[1] == (b"carrier-r2", "r2", True) and _wait(lambda: not V.running("s1"))


def test_start_unknown_template_and_broken_run(lib, monkeypatch):
    with pytest.raises(LookupError):
        V.start("nope")
    assert not V.running("nope")
    lib.carrier = lambda sid, rid=None: None                                 # 운반 문서가 사라짐 → fail 기록을 붙인다
    assert V.start("s1")["status"] == "running" and _wait(lambda: lib.put) and _wait(lambda: not V.running("s1"))
    assert lib.put[0][:2] == ("s1", "r1") and lib.put[0][2]["status"] == "fail" and lib.put[0][2]["note"] == "운반 문서가 없습니다"
    lib.carrier = lambda sid, rid=None: b"x"
    monkeypatch.setattr(V, "run", lambda *a, **k: 1 / 0)                     # run 은 예외를 안 내지만 — 내더라도 작업이 남지 않는다
    assert V.start("s1")["status"] == "running" and _wait(lambda: not V.running("s1")) and len(lib.put) == 1
    assert _wait(lambda: lib.events.count("unpin r1") == 2) and lib.events.count("pin r1") == 2   # 실패한 검증도 붙든 것을 놓는다


def test_running_verification_keeps_its_revision_through_pruning(monkeypatch):
    """astra 14: 검증이 도는 동안 revision 이 다섯 번 넘게 바뀌면 시작 때의 revision 이 치워져(최근 5개만) 결과가 버려졌다 — 실제 저장소로: 붙든 revision 은 검증이 끝날 때까지 남는다."""
    from app import style_lib as L
    sid = L.create({"kind": "text", "name": "글", "items": [{"key": "i1"}]}, b"carrier-1")["id"]
    gate, started = threading.Event(), threading.Event()

    def run(carrier, meta, force=False):
        started.set()
        gate.wait(5)
        return {"status": "ok", "revision": meta["revision"], "checks": []}, {"proof.png": b"png"}
    monkeypatch.setattr(V, "run", run)
    assert V.start(sid) == {"status": "running", "revision": "r1"} and started.wait(5)
    for n in range(2, 9):                                                    # 도는 동안 운반 문서가 일곱 번 바뀐다
        L.revise(sid, f"r{n - 1}", None, f"carrier-{n}".encode())
    assert L.carrier(sid, "r1") == b"carrier-1" and L.carrier(sid, "r2") is None and L.get(sid)["revision"] == "r8"   # r2·r3 은 치워졌지만 r1 은 붙들려 있다
    gate.set()
    assert _wait(lambda: not V.running(sid)) and _wait(lambda: L.carrier(sid, "r1") is None)   # 끝나면 놓고, 밀린 r1 을 치운다
    assert L.get(sid)["verify"] is None and not [k for k in L._PINS if k[0] == sid]             # 운반 문서가 다른 지금 revision 에는 안 붙는다(검증한 것이 아니다)
    L.revise(sid, "r8", {"name": "이름만"})                                  # 운반 문서가 같은 새 revision — 도는 검증의 결과가 거기에도 붙는다
    gate.clear()
    started.clear()
    assert V.start(sid)["revision"] == "r9" and started.wait(5)
    L.revise(sid, "r9", {"name": "또 이름만"})
    gate.set()
    assert _wait(lambda: not V.running(sid)) and _wait(lambda: (L.get(sid)["verify"] or {}).get("status") == "ok") and L.get(sid)["revision"] == "r10"
