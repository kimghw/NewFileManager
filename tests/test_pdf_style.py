"""헤딩 레벨·레터 꼴 추출(headings), 레터·글꼴 대조(pdf_style), 검증 단계 병렬 실행(verify.run_flow), 한글 출력 풀(pdf_render) —
spec_hwpx_웹편집 ② §3-2·§5·§7."""
import threading
import time
from pathlib import Path

import fitz
import pytest

from app import fonts, headings, pdf_map, pdf_render, pdf_style, verify
from app.hwpx_doc import HwpxDoc

MALGUN, MALGUN_B = Path("C:/Windows/Fonts/malgun.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf")
PAGE = {"widthMm": 210.0, "heightMm": 297.0, "marginsMm": {"l": 20.0, "r": 20.0, "t": 20.0, "b": 20.0}}
MM = 72 / 25.4


def _fmt(**kw):
    return {"font": "맑은 고딕", "sizePt": 10.0, "bold": False, "color": "#000000", "align": "justify",
            "indentLeftMm": 0.0, "firstLineMm": 0.0, **kw}


def _para(pid, text, **kw):
    lst = kw.pop("list", None)
    return {"id": pid, "type": "paragraph", "text": text, "format": _fmt(**kw), "runs": None, "list": lst, "outlineLevel": None}


# ---- headings ----------------------------------------------------------------------------------------

def test_skeleton_lead_letter_gap():
    sk = headings.skeleton("  □ 추진 배경")
    assert (sk["lead"], sk["letter"], sk["gap"], sk["full"], sk["core"]) == ("  ", "□", " ", "_2□_1", "□")
    sk = headings.skeleton("  1) 「방위사업법」 제3조")
    assert (sk["letter"], sk["gap"]) == ("1)", " ")  # 레터 = 공백 없이 붙은 첫 토큰 묶음
    sk = headings.skeleton("1.1.1. 세부 내용")
    assert (sk["letter"], sk["core"]) == ("1.1.1.", "N.N.N.")
    assert headings.skeleton("본문 글입니다")["letter"] == ""


def test_levels_stack_and_cells():
    """문자헤딩은 같은 레터 형제를 닫고 맨 위 + 1, 표 칸(2칸 이상)은 칸마다 T 스택."""
    cell = lambda cid, *ps: {"id": cid, "row": 0, "col": 0, "rowSpan": 1, "colSpan": 1, "blocks": list(ps)}  # noqa: E731
    blocks = [_para("a", "1. 개요"), _para("b", "□ 추진 배경"), _para("c", "- 세부 하나"), _para("d", "□ 필요성"),
              _para("e", "2. 내용"),
              {"id": "t", "type": "table", "cells": [cell("c1", _para("x", "o 칸 첫 줄"), _para("y", "- 칸 아래")), cell("c2", _para("z", "o 둘째 칸"))]}]
    an = headings.levels(blocks)
    assert [an["levels"].get(i) for i in "abcde"] == [1, 2, 3, 2, 1]
    assert an["fieldLevels"] == {"x": 1, "y": 2, "z": 1}
    assert an["parents"]["c"] == "b" and an["parents"]["d"] == "a"


def test_line2_hang_width():
    p = _para("p", "1. 첫째", firstLineMm=-5.0, indentLeftMm=2.0)
    l2 = headings.line2(None, p)
    assert l2["kind"] == "single" and l2["hangMm"] == 5.0 and l2["rule"] == "왼 2 · 내어 5"
    assert headings.line2(None, _para("q", "가. 첫 줄\u2028  - 둘째 줄"))["kind"] == "forced"
    rows = headings.extract([_para("p", "1. 첫째"), _para("q", "본문")])["rows"]
    assert set(rows) == {"p"} and rows["p"]["head"]["letter"] == "1."


# ---- pdf_style: 레터·글꼴 대조(가짜 한글 PDF) ---------------------------------------------------------

@pytest.mark.skipif(not MALGUN.exists() or not MALGUN_B.exists(), reason="맑은 고딕 필요")
def test_check_heads_and_fonts(tmp_path):
    left = 20 * MM
    lines = [  # (x, y, 글, 크기, 굵게) — 한글 PDF 처럼 앞 공백도 글자로
        (left, 100, "  □ 추진 배경과 필요성 설명", 10, False),
        (left, 130, "1. 첫째 항목입니다 길게", 10, False),
        (left + 5 * MM, 144, "이어지는 둘째 줄 글", 10, False),
        (left, 170, "굵은 제목 문단입니다", 10, True),
        (left, 200, "1. 번호 붙은 문단 내용", 10, False),
        (left, 230, "□ 다른 레터 문단 내용", 10, False),
        (left, 260, "크기가 다른 문단입니다", 14, False),
    ]
    blocks = [{**_para("p1", "  □ 추진 배경과 필요성 설명"), "page": PAGE},
              _para("p2", "1. 첫째 항목입니다 길게 이어지는 둘째 줄 글", firstLineMm=-5.0),
              _para("p3", "굵은 제목 문단입니다", bold=True),
              _para("p4", "번호 붙은 문단 내용", list={"kind": "number", "level": 1, "label": "1.", "numFmt": "DIGIT"}),
              _para("p5", "○ 다른 레터 문단 내용"),
              _para("p6", "크기가 다른 문단입니다")]
    doc = fitz.open()
    page = doc.new_page(width=595.3, height=841.9)
    reg, bold = fitz.Font(fontfile=str(MALGUN)), fitz.Font(fontfile=str(MALGUN_B))
    for x, y, t, size, b in lines:
        tw = fitz.TextWriter(page.rect)
        tw.append((x, y), t, font=bold if b else reg, fontsize=size)
        tw.write_text(page)
    pdf = tmp_path / "x.pdf"
    doc.save(pdf)
    m, pages, its = pdf_map.map_detail(blocks, pdf, halves=False, chars=True)
    assert m["located"] == 6
    rows = headings.extract(blocks)["rows"]
    h = pdf_style.check_heads(rows, blocks, its, pages)
    assert h["letter"] == {"ok": 3, "bad": 1} and [i["id"] for i in h["issues"]] == ["p5"]
    assert h["lead"]["ok"] == 3 and not h["lead"].get("bad")
    assert h["gap"] == {"ok": 2}  # 자동 번호(p4) 뒤 간격은 폭만 잼
    pat = {p["full"]: p for p in h["patterns"]}
    assert pat["_2□_1"]["leadMm"] > 0 and pat["N._1"]["line2Mm"] == 5.0
    assert h["line2"] == {"ok": 1}  # p2: 둘째 줄이 첫 줄보다 5mm 안 = 내어쓰기 5mm
    assert h["left"].get("ok", 0) >= 3 and not h["left"].get("bad")
    f = pdf_style.check_fonts(blocks, its, pages)
    assert f["bold"]["bad"] == 0 and f["color"]["bad"] == 0
    assert {e["id"] for e in f["size"]["examples"]} == {"p6"}
    face = next(x for x in f["faces"] if x["web"] == "맑은 고딕")
    assert face["verdict"] == "same"
    status, detail = verify.fonts_verdict(f)
    assert status == "fail" and "크기 다름" in detail  # p6 글자 전부 = 2% 넘음
    assert verify.letters_verdict(h)[0] == "warn"


def test_font_index_reads_korean_names():
    if not MALGUN.exists():
        pytest.skip("맑은 고딕 필요")
    idx = pdf_style.font_index()
    assert idx.family("맑은 고딕") == idx.family("MalgunGothicBold") == idx.family("Malgun Gothic")
    assert idx.family("T9") is None
    r = idx.resolve("없는글꼴이름")
    assert r["how"] == "fallback" and r["key"]  # 웹은 기본 글꼴(HCR Dotum …)로 그린다


@pytest.mark.skipif(not MALGUN.exists() or not MALGUN_B.exists(), reason="맑은 고딕 필요")
def test_script_and_ratio_sizes(tmp_path):
    """윗첨자 런은 크기 × 0.64 로, 장평 80% 문단은 √0.8 배로 읽히는 PDF 크기로 견준다 — 크기 다름 0. 웹 서식에 첨자가 없으면 「첨자로 보임」."""
    sup = {**_fmt(), "script": "sup"}
    blocks = [{**_para("a", "보안등급1) 연구개발과제 정보입니다"), "runs": [
                  {"text": "보안등급", "format": _fmt()}, {"text": "1)", "format": sup}, {"text": " 연구개발과제 정보입니다", "format": _fmt()}]},
              _para("b", "장평을 줄인 문단 글입니다", ratioPct=80),
              _para("c", "첨자인데2 웹 서식엔 없는 문단")]
    doc = fitz.open()
    page = doc.new_page(width=595.3, height=841.9)
    reg = fitz.Font(fontfile=str(MALGUN))

    def put(x, y, t, size, morph=None):
        tw = fitz.TextWriter(page.rect)
        end = tw.append((x, y), t, font=reg, fontsize=size)[1]
        tw.write_text(page, morph=morph)
        return end.x
    x = put(60, 100, "보안등급", 10)
    x = put(x, 100 - 4.4, "1)", 6.4)
    put(x, 100, " 연구개발과제 정보입니다", 10)
    put(60, 140, "장평을 줄인 문단 글입니다", 10, morph=(fitz.Point(60, 140), fitz.Matrix(0.8, 1)))
    x = put(60, 180, "첨자인데", 10)
    x = put(x, 180 - 4.4, "2", 6.4)
    put(x, 180, " 웹 서식엔 없는 문단", 10)
    pdf = tmp_path / "s.pdf"
    doc.save(pdf)
    m, pages, its = pdf_map.map_detail(blocks, pdf, halves=False, chars=True)
    assert m["located"] == 3
    f = pdf_style.check_fonts(blocks, its, pages)
    assert f["size"]["scripted"] == 1 and f["size"]["ratio"] == len("장평을줄인문단글입니다")
    assert f["size"]["bad"] == 1 and f["size"]["script"] == 1 and f["size"]["examples"][0]["id"] == "c"
    assert "첨자로 보임 1자" in verify.fonts_verdict(f)[1]


def test_font_plan_follows_hangul_order(tmp_path):
    """문서 글꼴 -> 웹이 그릴 글꼴: 있으면 그것 · HFT 한글 글자는 한컴 대응표(같은 디자인) · HFT 영문은 문서 대체 글꼴 · 없는 TTF 는 대체 글꼴."""
    if not MALGUN.exists() or not MALGUN_B.exists():
        pytest.skip("맑은 고딕 필요")
    fm = tmp_path / "FontMap.dat"
    fm.write_bytes("; 시험\nmapFont=Malgun Gothic,Malgun Gothic,가짜한양고딕,가짜고딕\n".encode("utf-16"))
    idx = fonts.FontIndex(dirs=[MALGUN.parent], bundled=[], fontmap=fm)
    malgun = idx.family("Malgun Gothic")
    assert idx.resolve("맑은 고딕") == {"key": malgun, "how": "same", "via": "맑은 고딕"}
    assert idx.resolve("가짜한양고딕", "HANGUL", "HFT", ["없는대체"])["how"] == "equiv"
    assert idx.resolve("가짜한양고딕", "LATIN", "HFT", ["맑은 고딕"]) == {"key": malgun, "how": "subst", "via": "맑은 고딕"}
    assert idx.resolve("없는글꼴", "HANGUL", "TTF", ["Malgun Gothic"])["how"] == "subst"
    table = {"HANGUL": {"가짜한양고딕": {"type": "HFT", "subst": []}}, "LATIN": {"맑은 고딕": {"type": "TTF", "subst": []}}}
    w = fonts.web_fonts(table, idx)
    assert w["alias"] == {"HANGUL": {"가짜한양고딕": "nfm-hangul-0"}, "LATIN": {"맑은 고딕": "nfm-latin-0"}}
    hangul, latin = (r for r in w["css"].splitlines() if "font-weight:400" in r)
    assert 'local("Malgun Gothic")' in hangul and "unicode-range" not in hangul
    assert "unicode-range:U+0000-024F" in latin
    assert any("font-weight:700" in r and "Bold" in r for r in w["css"].splitlines())  # 굵은 face 가 있으면 따로
    assert w["plan"]["HANGUL"]["가짜한양고딕"]["how"] == "equiv"
    # PDF 이름이 「????」(한글 PostScript 이름) — 글자 수가 같은 한글 PS 이름이면 같은 가족
    idx.fams["fake"] = [{"ps": {"휴먼명조"}}]
    assert idx.broken_match("ABCDEF+????", "fake") and not idx.broken_match("???", "fake") and not idx.broken_match("T9", "fake")
    assert fonts.lang_of("A") == "LATIN" and fonts.lang_of("漢") == "HANJA" and fonts.lang_of("한") == "HANGUL" and fonts.lang_of("㎎") == "SYMBOL"
    # 한글이 기호 글꼴로 찍는 글자(2026-11-17 시험 문서 실측) — 「√」 를 한글 글꼴(전각)로 그려 표 칸 줄이 한글보다 더 갈렸다
    assert all(fonts.lang_of(c) == "SYMBOL" for c in "√∼①□○※「」〈→℃ⅠΩ～＋㈜") and fonts.lang_of("•") == "SYMBOL"
    assert fonts.lang_of("‘") == fonts.lang_of("”") == fonts.lang_of("·") == "LATIN" and fonts.lang_of("〓") == "JAPANESE"
    assert fonts.lang_of("ㆍ") == fonts.lang_of("ㅇ") == fonts.lang_of("　") == fonts.lang_of(" ") == "HANGUL"  # 호환 자모 · 빈칸 글자는 넣지 않음
    # 대체 글꼴 없는 HFT 의 영문·기호 = 한글의 기본 대체 글꼴(고딕 계열 영문·한자·일어 → 돋움, 그 밖 → 바탕)
    assert fonts.hft_subst("한양견고딕", "LATIN") == fonts.hft_subst("한양중고딕", "HANJA") == fonts.hft_subst("HCI Hollyhock", "LATIN") == ("Dotum",)
    assert fonts.hft_subst("한양중고딕", "SYMBOL") == fonts.hft_subst("한양신명조", "LATIN") == fonts.hft_subst("HCI Poppy", "LATIN") == ("Batang",)
    if dotum := idx.family("Dotum"):
        assert idx.resolve("가짜한양고딕", "LATIN", "HFT") == {"key": dotum, "how": "subst", "via": "Dotum"}
        assert idx.resolve("가짜한양고딕", "LATIN", "HFT", ["맑은 고딕"])["key"] == malgun  # 문서에 대체 글꼴이 있으면 그것
    assert idx.resolve("가짜한양고딕", "HANGUL", "HFT")["how"] == "equiv"  # 한글 글자는 그대로 같은 디자인


SAMPLE = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"


@pytest.mark.skipif(not SAMPLE.exists(), reason="예제 필요")
def test_summary_has_script_and_language_fonts():
    """서식 요약에 윗첨자(hh:supscript)·언어별 글꼴, 문서 글꼴 표에 종류(HFT)·대체 글꼴(hh:substFont)."""
    doc = HwpxDoc(SAMPLE.read_bytes())
    runs = [r for p in _all_paras(doc.blocks()) for r in p.get("runs") or ()]
    sup = [r for r in runs if r["format"].get("script") == "sup"]
    assert sup and all(r["format"]["fontLatin"] for r in sup)
    t = doc.font_table()
    assert t["HANGUL"]["한양중고딕"] == {"type": "HFT", "subst": []}
    assert t["LATIN"]["한양중고딕"] == {"type": "HFT", "subst": ["Dotum"]}
    # 문단 끝 빈 런(10pt)이 글(8pt)보다 크면 endSizePt — 한글은 마지막 줄을 그 크기로 높인다(lineseg vertsize 1000, ② §3-4)
    paras = {p["id"]: p for p in _all_paras(doc.blocks())}
    assert paras["p1528"]["endSizePt"] == 10.0 and paras["p1528"]["format"]["sizePt"] == 8.0
    assert "endSizePt" not in paras["p1527"]
    assert sum("endSizePt" in p for p in paras.values()) == 20


def _all_paras(blocks):
    out = []
    for b in blocks:
        if b.get("type") == "paragraph":
            out.append(b)
        for c in b.get("cells") or ():
            out += _all_paras(c.get("blocks") or [])
    return out


# ---- 병렬 실행 ---------------------------------------------------------------------------------------

def test_run_flow_parallel_and_skip():
    """앞 단계가 없는 두 단계는 함께 돈다(서로 기다려도 안 막힘), 막힌 단계 뒤는 건너뜀, 오류는 그 단계 실패."""
    job = verify.Job("t", [(k, k, "") for k in ("a", "b", "c", "d", "e")])
    ea, eb = threading.Event(), threading.Event()

    def a():
        job.set("a", "run")
        ea.set()
        assert eb.wait(5), "b 가 함께 돌지 않음"
        job.set("a", "ok")

    def b():
        job.set("b", "run")
        eb.set()
        assert ea.wait(5), "a 가 함께 돌지 않음"
        raise verify.Stop("b 가 막음", "fail")

    def boom():
        raise ValueError("터짐")
    verify.run_flow(job, {"a": a, "b": b, "c": lambda: job.set("c", "ok"), "d": boom, "e": lambda: job.set("e", "ok")},
                    {"c": ["b"], "e": ["a", "d"]})
    st = {s["key"]: (s["status"], s["detail"]) for s in job.steps}
    assert st["a"][0] == "ok" and st["b"] == ("fail", "b 가 막음")
    assert st["c"] == ("skip", "b 가 막음") and st["d"][0] == "fail" and st["e"] == ("skip", "앞 단계 오류로 건너뜀")
    assert job.finished and job.view()["status"] == "fail" and "터짐" in job.error


def test_same_bytes_export_once(monkeypatch, tmp_path):
    """두 단계가 같은 바이트를 동시에 찍으면 한글 출력은 한 번(캐시 이름 잠금)."""
    calls = []

    class Fake:
        def run(self, src, out, limit, fmt="PDF"):
            calls.append(src)
            time.sleep(0.3)
            Path(out).write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(pdf_render, "EXPORTER", Fake())
    got = []
    ths = [threading.Thread(target=lambda: got.append(pdf_render.export_pdf(b"same bytes"))) for _ in range(3)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert len(calls) == 1 and len(set(got)) == 1


def test_pool_runs_on_idle_exporters(monkeypatch):
    """풀은 쉬는 프로세스에 하나씩 — 2개면 두 요청이 함께 돈다."""
    active, peak, lock = [0], [0], threading.Lock()

    class Fake:
        def run(self, src, out, limit, fmt="PDF"):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.2)
            with lock:
                active[0] -= 1
            return out
    monkeypatch.setattr(pdf_render, "Exporter", Fake)
    pool = pdf_render.Pool(2)
    ths = [threading.Thread(target=pool.run, args=("s", f"o{i}", 5)) for i in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert peak[0] == 2
