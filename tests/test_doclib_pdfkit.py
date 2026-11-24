"""문서 라이브러리 서버의 PDF 스크립트(doclib/pdfkit.py — spec_양식작성 ② §3): 쪽 묶음 · 쪼개진 그림 합치기(작은 조각 · 이음매) · 모서리 확인 · 수식 후보 · 상자 변환 · 자르기. LLM 을 부르지 않는다."""
import io

import fitz
import pytest
from PIL import Image, ImageDraw

from doclib import pdfkit as K


def _png(w, h, draw=None, bg="white"):
    im = Image.new("RGB", (w, h), bg)
    if draw:
        draw(ImageDraw.Draw(im))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _page():
    doc = fitz.open()
    return doc, doc.new_page(width=595, height=842)


def test_split_and_part_and_boxes():
    assert K.split(68) == [(1, 20), (21, 40), (41, 60), (61, 68)] and K.split(5) == [(1, 5)] and K.split(0) == []
    assert K.split(68, span=(10, 15)) == [(10, 15)] and K.split(68, span=(19, 45)) == [(19, 38), (39, 45)] and K.split(10, span=(8, 99)) == [(8, 10)] and K.split(10, span=(11, 12)) == []
    doc = fitz.open()
    for i in range(5):
        doc.new_page().insert_text((72, 72), f"page {i + 1}")
    cut = K.open_pdf(K.part(doc, 2, 4))
    assert len(cut) == 3 and "page 2" in cut[0].get_text() and "page 4" in cut[2].get_text()
    rect = fitz.Rect(0, 0, 600, 800)
    assert K.norm((60, 80, 300, 400), rect) == [100, 100, 500, 500]
    assert K.denorm([100, 100, 500, 500], rect) == (60.0, 80.0, 300.0, 400.0)
    assert K.denorm([500, 500, 100, 100], rect) == (60.0, 80.0, 300.0, 400.0)       # 거꾸로 준 상자는 바로잡는다
    assert K.denorm([0, 0, 2, 2], rect) is None and K.denorm("x", rect) is None and K.denorm([1, 2, 3], rect) is None   # 너무 작은 상자 · 꼴이 틀림
    with pytest.raises(ValueError):
        K.open_pdf(b"not a pdf")


def test_touching():
    assert K.touching((0, 0, 10, 10), (10, 0, 20, 10)) == "x" and K.touching((0, 0, 10, 10), (0, 10, 10, 20)) == "y"
    assert K.touching((0, 0, 10, 10), (5, 5, 20, 20)) == "in"
    assert K.touching((0, 0, 10, 10), (10, 10, 20, 20)) == ""       # 모서리만 스침
    assert K.touching((0, 0, 10, 10), (14, 0, 24, 10)) == ""        # 틈이 있음
    assert K.touching((0, 0, 10, 100), (10, 90, 20, 190)) == ""     # 같이 쓰는 변이 짧음


def test_small_tiles_are_joined_into_one_figure():
    """쪼개져서 붙은 그림 — 작은 조각 16개(4×4)는 한 그림이다."""
    doc, page = _page()
    tile = _png(20, 20, lambda d: d.rectangle([0, 0, 19, 19], fill=(40, 90, 200)))
    for r in range(4):
        for c in range(4):
            page.insert_image(fitz.Rect(100 + c * 30, 100 + r * 30, 130 + c * 30, 130 + r * 30), stream=tile)
    figs = K.figures(page, 3)
    assert len(figs) == 1 and figs[0]["key"] == "p3_F1" and figs[0]["parts"] == 16 and figs[0]["kind"] == "image"
    assert [round(v) for v in figs[0]["box"]] == [100, 100, 220, 220]


def test_big_images_join_only_when_the_seam_continues():
    """큰 그림 둘이 맞닿았을 때 — 이음매가 흰 띠면 따로 선 그림 둘, 그림이 이어지면(한 그림을 반으로 쪼갠 것) 한 그림."""
    def apart(d):   # 가운데에 그림, 둘레는 흰 여백
        d.ellipse([20, 20, 180, 130], fill=(200, 60, 60))
    doc, page = _page()
    page.insert_image(fitz.Rect(60, 100, 260, 250), stream=_png(200, 150, apart))
    page.insert_image(fitz.Rect(260, 100, 460, 250), stream=_png(200, 150, apart))
    assert len(K.figures(page, 1)) == 2

    whole = Image.new("RGB", (400, 150), "white")
    d = ImageDraw.Draw(whole)
    for y in range(10, 150, 12):   # 이음매를 가로지르는 줄들
        d.line([0, y, 399, y], fill=(30, 30, 30), width=4)
    doc, page = _page()
    for k, x in enumerate((60, 260)):
        buf = io.BytesIO()
        whole.crop((k * 200, 0, k * 200 + 200, 150)).save(buf, "PNG")
        page.insert_image(fitz.Rect(x, 100, x + 200, 250), stream=buf.getvalue())
    figs = K.figures(page, 1)
    assert len(figs) == 1 and figs[0]["parts"] == 2 and [round(v) for v in figs[0]["box"]] == [60, 100, 460, 250]


def test_tiny_and_page_covering_images_are_not_candidates():
    doc, page = _page()
    page.insert_image(fitz.Rect(50, 50, 60, 60), stream=_png(10, 10, bg=(0, 0, 0)))             # 글머리 그림
    page.insert_image(page.rect, stream=_png(60, 84, bg=(240, 240, 240)))                        # 쪽을 덮는 바탕(스캔)
    assert K.figures(page, 1) == []


def test_settle_grows_a_box_that_cuts_the_picture_and_leaves_separate_things_alone():
    doc, page = _page()
    page.draw_rect(fitz.Rect(100, 100, 300, 260), color=(0, 0, 0), fill=(0.2, 0.4, 0.8), width=1)   # 그림
    page.insert_text((100, 300), "caption below the picture", fontsize=11)                          # 변 밖에 따로 선 글
    box, edges = K.settle(page, (100, 100, 300, 200))        # 아래를 잘라 잡은 상자
    assert edges["bottom"] == "grown" and box[3] >= 259 and box[3] < 290 and edges["left"] == edges["top"] == edges["right"] == "ok"
    box, edges = K.settle(page, (96, 96, 304, 264))          # 그림을 다 두른 상자 — 캡션 쪽으로 밀지 않는다
    assert set(edges.values()) == {"ok"} and box == (96, 96, 304, 264)
    box, edges = K.settle(page, (100, 100, 300, 200), most=9)   # 한도까지 밀어도 그림이 이어짐 — 사람이 볼 것
    assert edges["bottom"] == "open"


def test_formula_candidates_come_from_math_fonts(monkeypatch):
    monkeypatch.setattr(K, "MATH_FONTS", K.MATH_FONTS + ("symbol",))   # 시험은 내장 글꼴 Symbol 을 수식 글꼴로 본다(실제 목록에는 없다 — 글머리에 흔한 글꼴이라)
    assert K._mathy("CambriaMath") and K._mathy("HancomEQN") and K._mathy("HYhwpEQ") and not K._mathy("Dotum") and not K._mathy("")
    doc, page = _page()
    page.insert_text((72, 100), "plain text before the formula", fontname="helv", fontsize=11)
    page.insert_text((150, 140), "abgdSabgdSabgdSabgd", fontname="symb", fontsize=14)     # 따로 선 수식 줄
    page.insert_text((72, 180), "plain text after", fontname="helv", fontsize=11)
    page.insert_text((300, 180), "ab", fontname="symb", fontsize=11)                       # 글 속의 기호 둘 — 폭이 좁아 후보가 아니다
    eqs = K.formulas(page, 7)
    assert [e["key"] for e in eqs] == ["p7_E1"] and 125 < eqs[0]["box"][1] < 145 and eqs[0]["box"][2] - eqs[0]["box"][0] > K.FORMULA_MIN_W
    assert K.formulas(page, 7, inside=[(100, 120, 500, 160)]) == []                         # 그림 후보 안의 수식은 그림의 일부


def test_snap_and_crop_and_blank():
    doc, page = _page()
    page.insert_image(fitz.Rect(100, 100, 300, 250), stream=_png(200, 150, bg=(10, 120, 60)))
    snapped = K.snap(page, (110, 110, 290, 260))                 # 어림 상자 — 그림의 절반 넘게 겹치면 그림을 다 품게
    assert [round(v) for v in snapped] == [100, 100, 300, 260]
    assert K.snap(page, (400, 400, 450, 450)) == (400, 400, 450, 450)   # 아무것도 없으면 그대로
    png, w, h = K.crop(page, (100, 100, 300, 250), dpi=144)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and abs(w - 408) <= 2 and abs(h - 308) <= 2 and not K.blank(png)
    assert K.blank(K.crop(page, (400, 500, 500, 600))[0])
    big, w, h = K.crop(page, (0, 0, 595, 842), dpi=600)           # 긴 변 2400px 까지
    assert max(w, h) <= 2410


def test_survey_finds_running_text_decorative_images_and_heading_hints():
    """문서 전체를 한 번 훑기(앞선 구현 makemd 의 규칙) — 머리말 · 꼬리말 · 여러 쪽에 되풀이되는 그림(로고) · 글꼴 크기 단계의 헤딩 힌트."""
    doc = fitz.open()
    logo = _png(60, 30, lambda d: d.rectangle([0, 0, 59, 29], fill=(200, 30, 30)))
    for i in range(4):
        p = doc.new_page(width=595, height=842)
        p.insert_text((60, 40), "R&D Plan - Korean Register", fontsize=9)              # 머리말(위 띠 · 쪽마다)
        p.insert_text((290, 820), f"- {i + 1} -", fontsize=9)                          # 쪽 번호
        p.insert_image(fitz.Rect(480, 20, 540, 50), stream=logo)                       # 로고(쪽마다 같은 그림)
        p.insert_text((60, 120), f"{i + 1}. Big heading", fontsize=18)
        for k in range(12):
            p.insert_text((60, 160 + k * 16), "body text line that is long enough to count as prose", fontsize=10)
    doc[1].insert_image(fitz.Rect(100, 400, 300, 550), stream=_png(200, 150, lambda d: d.ellipse([10, 10, 190, 140], fill=(30, 90, 200))))
    info = K.survey(doc)
    assert info["pages"] == 4 and "R&D Plan - Korean Register" in info["running"] and info["body"] == 10.0 and len(info["decorative"]) == 1 and info["scanned"] == [] and info["outline"] == []
    assert info["tiers"][0].startswith("18pt → 단계 1") and [h["text"] for h in info["hints"][2]] == ["2. Big heading"] and info["hints"][2][0]["level"] == 1
    assert [f["key"] for f in K.figures(doc[1], 2, info)] == ["p2_F1"] and K.figures(doc[0], 1, info) == []      # 로고는 그림 후보가 아니다(훑은 값을 줄 때)
    assert len(K.figures(doc[0], 1)) == 1                                                                         # 훑은 값이 없으면 꾸밈인지 모른다
    assert K.is_running(K.lines_of(doc[0])[0], doc[0].rect, info["keys"]) and not K.is_running(K.lines_of(doc[0])[3], doc[0].rect, info["keys"])


def test_math_lines_by_symbol_density_and_equation_number():
    """수식 줄 판정 — 수식 글꼴이 아니어도 기호 밀도 · 수식 번호로(앞선 구현 makemd 의 규칙)."""
    def line(text, font="helv"):
        return K.Line((0, 0, 100, 10), text, [{"text": text, "font": font, "flags": 0, "size": 10}], 0, 10, False, len(text.replace(" ", "")))
    assert K.is_math_line(line("V = I × R (3)")) and K.is_math_line(line("σ = F / A")) and K.is_math_line(line("x", "CambriaMath") ) is False   # 한 글자는 아님
    assert K.is_math_line(line("a b c", "Cambria Math")) and not K.is_math_line(line("이 식에서 전압은 전류와 저항의 곱이다")) and not K.is_math_line(line("(3)"))
    assert not K.is_math_line(line("The result shows that performance improved significantly"))
    doc, page = _page()
    page.insert_text((72, 100), "The voltage is given by the following relation where R is resistance.", fontsize=10)
    page.insert_text((200, 140), "V = I × R", fontsize=12)
    page.insert_text((480, 140), "(3)", fontsize=12)
    page.insert_text((72, 180), "This paragraph continues with ordinary prose after the equation line.", fontsize=10)
    eqs = K.formulas(page, 4)
    assert len(eqs) == 1 and eqs[0]["key"] == "p4_E1" and eqs[0]["src"] == "text" and eqs[0]["box"][2] > 480 and "(3)" in eqs[0]["text"]   # 오른쪽의 수식 번호까지 묶는다
    page.insert_image(fitz.Rect(200, 300, 320, 318), stream=_png(240, 36, lambda d: d.text((4, 4), "E = m c 2", fill=(0, 0, 0))))            # 납작한 작은 그림 = 수식 그림 후보
    assert [e["src"] for e in K.formulas(page, 4)] == ["text", "raster"] and K.figures(page, 4) == []
    assert K.caption_of((100, 100, 300, 250), [K.Line((100, 256, 300, 268), "그림 3. 시스템 구성도", [], 0, 10, False, 10)]) == "그림 3. 시스템 구성도"
    assert K.caption_of((100, 100, 300, 250), [K.Line((100, 400, 300, 412), "그림 4. 멀리 있는 캡션", [], 0, 10, False, 10)]) == ""
