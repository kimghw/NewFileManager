"""서식 보관함 PDF 검증 — **실제 한글 출력**(spec_일반편집 ② §6). 한글이 없는 PC 에서는 건너뛴다. 출력은 시험 임시 폴더(conftest 의 NFM_RENDER)에만 남는다.
한글 출력 3번(약 10초) — 견줌 논리 자체는 한글 없이 test_style_verify.py 가 본다."""
import copy
from pathlib import Path

import pytest

from app import pdf_render, table_make
from app import style_verify as V
from app.hwpx_doc import HwpxDoc

BASE = Path(__file__).resolve().parent.parent / "app" / "style_base.hwpx"
pytestmark = pytest.mark.skipif(not pdf_render.available("hwpx"), reason="한글(HWPFrame.HwpObject)이 없는 PC")
OUTER, INNER = {"type": "SOLID", "width": "0.4 mm", "color": "#000000"}, {"type": "SOLID", "width": "0.12 mm", "color": "#7F7F7F"}


def _by(checks):
    return {c["what"]: c for c in checks}


@pytest.fixture(autouse=True)
def _hangul(_no_hangul, monkeypatch):
    monkeypatch.delenv("NFM_PDF", raising=False)   # conftest 가 끈 PDF 출력을 이 파일에서만 켠다(렌더 캐시는 임시 폴더 그대로)


def _table_carrier():
    """빈 바탕에서 지은 3×3 표 — 머리행(음영·굵게 11pt) · 합계행(음영) · 바깥 0.4mm · 안 0.12mm 회색."""
    car = HwpxDoc(BASE.read_bytes())
    bl = car.blocks()
    first, plain = bl[0]["id"], next(b["id"] for b in bl if b["type"] == "table")
    rows = [["구분", "1차", "2차"], ["인건비", "100", "120"], ["합계", "100", "120"]]
    made = car.table_make(first, plain, table_make.normalize({"rows": rows}), {"headerRows": 0, "headerCols": 0, "footRows": 0})
    car.delete_blocks(plain, plain)
    for c in car.table_block(made["table"])["cells"]:
        r, k = c["row"], c["col"]
        cur = car.get_cell_format(c["id"])
        text = car.derive_format(cur["text"], {"sizePt": 11 if r == 0 else 10, "bold": r == 0, "color": "#C00000" if r == 2 else "#000000", "align": "center" if r == 0 else "right"})
        car.apply_cell_format([c["id"]], {"text": text, "fill": {0: "#D9E2F3", 2: "#FFF2CC"}.get(r), "valign": "center", "marginsMm": cur["marginsMm"]}, ["text", "fill"], keep_numbering=False)
        car.set_cell_edges(c["id"], {"top": OUTER if r == 0 else INNER, "bottom": OUTER if r == 2 else INNER, "left": OUTER if k == 0 else INNER, "right": OUTER if k == 2 else INNER})
    return car.save()


def test_table_carrier_verifies_and_a_wrong_expectation_fails():
    data = _table_carrier()
    rec, files = V.run(data, {"kind": "table", "revision": "r1", "bands": {"headerRows": 1, "headerCols": 0, "footRows": 1}})
    by = _by(rec["checks"])
    assert rec["status"] in ("ok", "warn") and rec["pages"] == 1 and rec["coverage"]["fail"] == 0, rec     # warn = 이 PC 에 그 글꼴이 없어 대체됐을 때만
    assert {k: by[k]["status"] for k in ("render", "pages", "text", "fontSize", "bold", "color", "fill", "edge", "lineWidth", "width")} == dict.fromkeys(
        ("render", "pages", "text", "fontSize", "bold", "color", "fill", "edge", "lineWidth", "width"), "pass")
    assert by["text"]["pass"] == 9 and by["fill"]["pass"] == 9 and by["edge"]["pass"] == 36 and by["lineWidth"]["pass"] == 36 and by["fontFace"]["fail"] == 0
    assert files["proof.pdf"][:5] == b"%PDF-" and files["proof.png"][:4] == b"\x89PNG" and len(rec["subjectHash"]) == 64
    # 같은 PDF 를 어긋난 기대값(다른 음영·굵게·크기·선 굵기)과 견주면 그 검사가 fail
    measure = V.measure_pdf(V._cached_pdf(data))
    wrong = V.expect_table(HwpxDoc(data))
    for c in wrong["cells"]:
        if c["row"] == 0:
            c["fill"] = "#FFC000"
        if c["row"] == 1:
            c["chars"] = [(k, ch, {**f, "bold": True, "sizePt": 14.0}) for k, ch, f in c["chars"]]
            c["edges"] = {**c["edges"], "b": {**c["edges"]["b"], "widthMm": 0.7}}
        if c["row"] == 2:                                                   # 맞닿은 두 칸이 모두 굵은 선을 기대(한쪽만 다르면 그 자리의 어느 괘선이든 맞으면 통과)
            c["edges"] = {**c["edges"], "t": {**c["edges"]["t"], "widthMm": 0.7}}
    by = _by(V.check_table(wrong, measure))
    assert by["fill"]["fail"] == 3 and by["bold"]["fail"] == 3 and by["fontSize"]["fail"] == 3 and by["lineWidth"]["fail"] == 6 and by["edge"]["fail"] == 0
    assert by["fill"]["examples"][0] == {"where": "A1", "want": "#FFC000", "got": "#D9E2F3"} and V.summarize(list(by.values()), 1)[0] == "fail"
    # 없는 선을 기대하면 edge 가 fail
    gone = copy.deepcopy(measure)
    gone["pages"][0]["segs"] = [s for s in gone["pages"][0]["segs"] if s["dir"] == "h"]
    assert _by(V.check_table(V.expect_table(HwpxDoc(data)), gone))["edge"]["fail"] == 18


def test_text_carrier_verifies_and_force_renders_again():
    car = HwpxDoc(BASE.read_bytes())
    bl = car.blocks()
    ref, plain = bl[0]["id"], next(b["id"] for b in bl if b["type"] == "table")
    for text, ch in (("1. 견본 글입니다", {"sizePt": 14, "bold": True, "color": "#000000", "align": "left", "indentLeftMm": 0, "firstLineMm": 0}),
                     ("  - 견본 글입니다", {"sizePt": 9, "bold": False, "color": "#C00000", "align": "left", "indentLeftMm": 10, "firstLineMm": 3})):
        ref = car.insert_line(ref, text)
        car.apply_format([ref], car.derive_format(car.get_format(ref), ch))
    car.delete_blocks(plain, plain)
    data = car.save()
    meta = {"kind": "text", "items": [{"key": "i1", "level": 1, "marker": {"mode": "literal"}}, {"key": "i2", "level": 2, "marker": {"mode": "literal"}}]}
    rec, files = V.run(data, meta)
    by = _by(rec["checks"])
    assert rec["status"] in ("ok", "warn") and rec["profile"] == "text-v1" and rec["pages"] == 1 and rec["coverage"]["fail"] == 0, rec
    assert by["text"]["pass"] == 2 and by["fontSize"]["pass"] == 2 and by["bold"]["pass"] == 2 and by["color"]["pass"] == 2 and by["indent"]["pass"] == 2
    assert by["lineSpacing"]["status"] == by["paraSpacing"]["status"] == "unsupported" and rec["coverage"]["unsupported"] == 2 and "proof.png" in files
    pdf = V._cached_pdf(data)
    first = pdf.stat().st_mtime_ns
    assert V.run(data, meta)[0]["status"] == rec["status"] and pdf.stat().st_mtime_ns == first       # 캐시 — 다시 찍지 않는다
    again, _ = V.run(data, meta, force=True)                                                          # 다시 검증 — 캐시를 지우고 다시 찍는다
    assert again["status"] == rec["status"] and pdf.stat().st_mtime_ns > first
