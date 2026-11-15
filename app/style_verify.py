"""서식 보관함 PDF 검증(spec_일반편집 ② §6 「② 견본 출력」) — 템플릿의 운반 문서를 한글로 출력해, 운반 문서 XML 이 뜻한 값과 PDF 에서 잰 값을 견준다.

- 기대값은 **운반 문서**에서 읽는다(`expect_table`·`expect_text`): 표 = 문서의 첫 표 — 행·열·합친 칸 · 칸의 제 폭(cellSz — HWPUNIT, 100 = 1pt) · 칸 변의 괘선(`_border_lines`) ·
  칸 음영 · 칸 글 서식. 글 = 첫 문단 뒤의 본문 최상위 문단들(n번째 ↔ `meta.items[n]`). 이웃 모듈(style_carrier)에 기대지 않는다.
- 표의 자리: 왼끝·폭 = 잰 선·채움의 범위 · 칸 상자의 x = 행마다 칸의 제 폭을 왼쪽부터 쌓은 것(`cell_boxes` — 한글이 그렇게 그린다, 열 경계가 행마다 다른 표가 있다) ·
  행 경계 y = 가로선·채움의 y 를 **보일 경계**(괘선·음영이 닿는 경계)에 차례대로 맞춘 것(`row_bounds` — 수가 다르면 자리 검사 전체가 unknown). 밑줄·취소선은 괘선으로 세지 않는다(`plain_segs`).
- 잰 값은 `measure_pdf`: 글자 = pdf_map 의 측정기(`_line`·`_stroked` — 가짜 굵게까지), 선·채움 = PyMuPDF `get_drawings`, 표 감지(`find_tables`)는 참고로만.
  `pdf_map.read_pdf` 를 그대로 쓰지 않는 까닭: 그 함수는 쪽 위·아래 8% 띠의 숫자뿐인 줄을 쪽 번호로 보고 뺀다 — 운반 문서의 칸 글 「0」 이 거기 걸리면 사라진다.
- 견줌(`check_table`·`check_text`)은 순수 함수 — 기대값 사전과 잰 값 사전만 받는다(시험은 한글 없이 지어낸 값으로). 검사마다 pass·fail·unknown 을 세고
  못 잰 것은 지어내지 않는다(행 경계 수가 안 맞으면 자리 검사는 unknown · Type3 글꼴의 굵게는 unknown · 겹줄·점선의 굵기는 unknown).
  글꼴 대체는 실패가 아니라 경고다(「대체 글꼴로 출력」 — 그 검사 unknown · 전체는 높아야 warn).
- 한글 PDF 실측(2026-11-13, 빈 바탕 A4): 쪽 595×841pt(문서 pt × 0.9995) · 음영 = 칸 상자 그대로의 채움 사각형(선 4개 경로) · 실선 0.12mm → 0.36pt, 0.4mm → 1.08pt, 0.1mm → 0.24pt ·
  겹줄(DOUBLE_SLIM 0.5mm) = 경계 ±0.6pt 의 0.36pt 선 둘 · 가로선은 표 왼끝 −0.48pt ~ 오른끝 +0.60pt · 높이 0.01pt 로 저장된 행은 경계가 겹친다 · 한글 전용 글꼴(HFT)은 이름 없는 Type3 「T1」 ·
  실제 표 21개(연구개발계획서 양식 19 · 기술수요조사서 2)를 옮긴 운반 문서에서 거짓 fail 0 — 2쪽으로 넘친 큰 표 2개와 무늬(가는 선 다발) 채움 표 1개는 unknown(warn).
- 작업(`start`): 스레드 하나가 시작 때의 revision 을 고정해(`style_lib.pin` — 도는 동안 안 치워진다) `run` → `style_lib.put_verify` → `unpin`. 도는 동안 `running(sid)`.
- **안 잰 것을 통과로 읽지 않는다**(astra 12): 빈 칸에 찍힌 글 = 「뜻밖의 글」 fail · 핵심 검사(글자 크기·굵게·글꼴)가 전부 미측정이면 warn(`summarize`) ·
  견주지 않는 것(표: 선 색·칸 여백·세로 정렬·칸 안 글 정렬·대각선 / 글: 줄 간격·문단 간격)은 `unsupported` 줄로 늘 싣는다 · 글의 견본 문단 수 ≠ meta item 수 = fail.
- **두 형식**(spec_서식복사 ② §7): `start` 가 hwpx(한글) → docx(Word)를 차례로 출력해 잰다. 기록 둘 — `meta.verify`(hwpx) · `meta.verifyDocx`(같은 꼴 + `format: "docx"` · `renderer: {name: "Word"}`),
  그림 `proof.png` · `proof_docx.png`. docx 운반 문서가 없으면 그 자리에서 지어 붙이고(`style_docx.build` → `style_lib.put_docx`), 못 지으면 `verifyDocx` 는 비운 채 둔다.
  docx 의 기대값은 **명세에서** 읽는다(`expect_table_spec` = 운반 문서의 표 명세 · `expect_text_items` = meta.items · `expect_page` = meta.page·body). 한글에 맞춘 보정은 Word 에 쓰지 않는다:
  칸의 x 는 칸의 제 폭을 쌓지 않고 **잰 세로선·채움의 열 경계**(수가 안 맞으면 명세의 열 폭 — 표 폭까지 다르면 자리 검사는 unknown), 선 굵기는 견주지 않음(unsupported).
  Word PDF 실측(2026-11-14 — references/DOCX_포맷.md 「Word PDF 에서 표·쪽 서식 재기」): 칸 음영 위에 글 줄마다 덧칠한 사각형 · 선 옆 음영 띠 · 교차점 조각을 걷어 낸 뒤(`word_page`) 견준다 — 못 잰 것은 unknown.
- **문서 서식**(종류 `page` · profile `page-v1` — 검사 항목은 두 형식이 같다): `render` · `pageSize`(한글 ±1.0mm `PAGE_TOL_HWPX` · Word ±0.5mm `PAGE_TOL`) · `marginLeft`·`marginTop`(견본 첫 줄의 자리 ±1.5mm) · `fontSize` · `fontFace` + unsupported(아래·오른쪽 여백 · 머리말·꼬리말 여백).
  견줌 `check_page(exp, measure)` 는 순수 함수.
- **표지 서식**(종류 `cover` · profile `cover-v1` — spec_서식복사 ② §14): `render` · `pageSize` · 글 부분마다 `text`·`fontSize`·`bold`·`fontFace`(글 서식과 같은 견줌 — `expect_cover` 가 부분의 견본 글·서식 요약으로
  `check_text` 의 기대값 꼴을 만든다) + unsupported(자리·정렬·간격 · 색·들여쓰기 · 표 부분). 견줌 `check_cover(exp, measure)` 는 순수 함수.
- **첫 쪽 전체 그림**(② §13): 쪽 설정·표지(`FULL_PROOF`)의 견본 그림은 내용 둘레를 자르지 않은 첫 쪽 전체(`proof_png(path, full=True)` — 긴 변 1,100px 안팎 · 110dpi 이하)."""
import hashlib
import json
import logging
import re
import threading
import time
from bisect import bisect_right
from collections import Counter

from app import fonts, hwpx_layout, pdf_map, pdf_render, pdf_style
from app.hwpx_doc import HwpxDoc, P
from app.pdf_map import key_text
from app.table_formula import a1

log = logging.getLogger(__name__)
PT_MM = 72 / 25.4
SIZE_TOL = 0.3        # 글자 크기 pt
COLOR_TOL = 0.03      # 색 — 채널마다(0~1)
LINE_TOL = 0.35       # 선 굵기 — 비율(한글이 굵기를 정해진 값으로 맞춘다)
WIDTH_TOL = 0.01      # 표 폭 — 비율
INDENT_TOL = 1.0      # 글 왼끝 mm
EDGE_TOL = 1.5        # 경계 자리와 선 사이 pt(겹줄은 경계 ±0.6pt)
ROW_TOL = 2.0         # 가로선 y 를 한 행 경계로 묶는 폭 pt
COVER_SOLID, COVER_ANY = 0.8, 0.2   # 변을 덮은 비율 — 실선 / 점선·겹줄 등
THIN = 2.5            # 이보다 가는 채움 사각형은 선(Word PDF 는 괘선을 가는 사각형으로 그린다)
EXAMPLES = 10
UNKNOWN_SHARE = 0.3
LIMIT = 120           # 한글 출력 시간 한도(초)
PROOF_DPI, PROOF_PAD = 110, 14
TABLE_CHECKS = ("pages", "text", "fontSize", "bold", "color", "fontFace", "fill", "edge", "lineWidth", "width")
TEXT_CHECKS = ("pages", "text", "fontSize", "bold", "color", "fontFace", "indent")
UNSUPPORTED_TEXT = (("lineSpacing", "줄 간격 — 견본이 한 줄이라 재지 못함"), ("paraSpacing", "문단 위·아래 간격 — 견본이 한 줄이라 재지 못함"))
# 표에서 **견주지 않는 것** — 기록에 「재지 못함」 으로 늘 싣는다(안 본 것을 통과로 읽지 않게: astra 12 「모든 괘선 색을 빨강으로 바꿔도 ok」)
UNSUPPORTED_TABLE = (("lineColor", "선 색 — 견주지 않음(선의 자리와 굵기만 봄)"), ("cellMargin", "칸 여백 — 견주지 않음"), ("valign", "세로 정렬 — 견주지 않음"),
                     ("cellAlign", "칸 안 글 정렬(왼쪽·가운데·오른쪽) — 견주지 않음"), ("diagonal", "대각선 — 견주지 않음(비스듬한 선은 재지 않음)"))
# 핵심 검사 — 하나라도 「통과 0 · 모름 1 이상」(전부 못 잼: 글꼴이 모두 Type3 등)이면 전체는 높아야 warn. 다른 검사(괘선)의 통과 수에 묻히지 않게 검사마다 본다
CORE_CHECKS = (("fontSize", "글자 크기를"), ("bold", "굵게를"), ("fontFace", "글꼴을"))
# ---- 두 형식 · 문서 서식(spec_서식복사 ② §7) ----
FORMATS = ("hwpx", "docx")            # 검증하는 차례 — 한글 → Word
RENDERERS = {"hwpx": "Hancom", "docx": "Word"}
PROFILES = {"text": "text-v1", "page": "page-v1", "cover": "cover-v1"}   # 종류 → profile(그 밖 = table-v1)
# ---- 첫 쪽 전체 그림 · 표지 서식(spec_서식복사 ② §13·§14) ----
FULL_PROOF = ("page", "cover")        # 견본 그림이 내용 둘레가 아니라 첫 쪽 전체인 종류(여백·배치가 보여야 한다)
PROOF_FULL_PX = 1100                  # 첫 쪽 전체 그림의 긴 변(px 안팎 — PROOF_DPI 를 넘지 않는다)
COVER_CHECKS = ("pageSize", "text", "fontSize", "bold", "fontFace")   # cover-v1 — render 는 run 이 붙인다
UNSUPPORTED_COVER = (("coverLayout", "부분의 자리·정렬·간격 — 견주지 않음"), ("coverColor", "글자 색·들여쓰기 — 견주지 않음"))
UNSUPPORTED_COVER_TABLE = ("coverTable", "표지 안 표는 견주지 않음")
PROOFS = {"hwpx": ("proof.png", "proof.pdf"), "docx": ("proof_docx.png", "proof_docx.pdf")}
WIDTH_TOL_DOCX = 0.02                 # Word 의 표 폭 — 비율(명세의 열 폭 합과)
ROW_NOMINAL = 20.0                    # 명세에는 행 높이가 없다 — 행 경계를 맞출 때 쓰는 어림 높이(pt · 높이 0 인 행으로 묶이지 않게)
PAGE_CHECKS = ("pageSize", "marginLeft", "marginTop", "fontSize", "fontFace")
PAGE_TOL, MARGIN_TOL = 0.5, 1.5       # 쪽 크기 · 견본 첫 줄의 자리(mm)
JOINT_MAX = 4.0                       # Word PDF 에서 선이 만나는 자리의 조각 — 가로·세로가 모두 이보다 작은 채움 사각형(pt)은 칸 음영이 아니다(word_page)
PAGE_TOL_HWPX = 1.0                # 한글 PDF 의 쪽 크기는 문서 값보다 조금 작다(실측 2026-11-14: A4 297 → 296.7 · Letter 279.4 → 278.7mm)
LINE_NATURAL = 1.5                    # Word 의 한 줄 높이 ÷ 글자 크기의 위쪽 어림 — 줄 간격이 100% 를 넘는 만큼 첫 줄이 내려올 수 있는 폭을 잡는다
UNSUPPORTED_PAGE = (("marginRightBottom", "아래·오른쪽 여백 — 견본 글로는 재지 못함"), ("headerFooter", "머리말·꼬리말 여백 — 재지 못함"))
UNSUPPORTED_LINE_WIDTH = ("lineWidth", "선 굵기 — Word 는 굵기를 제 값으로 그려 견주지 않음(선이 있는지만 봄)")
DOCX_FORMAT_KEYS = ("font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct", "align", "indentLeftMm", "indentRightMm", "firstLineMm", "lineSpacingPct",
                    "spaceBeforePt", "spaceAfterPt")  # docx 로 옮기는 서식 요약(`style_docx._format` 과 같은 키) — 언어별 글꼴·윗/아래첨자는 안 옮긴다(글꼴은 rFonts 넷 모두 font)
_STYLE_TAIL = re.compile(r"(?:bold|italic|regular|oblique|medium|light|semilight|extrabold|mt|ps)+$")
_ALIASES = []


# ---- 대상 해시 --------------------------------------------------------------------------------------------------

def subject_hash(meta: dict, fmt: str = "hwpx") -> str:
    """검증 대상의 해시 = sha256(운반 문서 해시 + 띠 수 + blueprint + items 의 뜻(key·level·marker)) — meta 의 뜻이 바뀌면 달라진다(화면 「검증 뒤 바뀜」).
    이름·견본 글·서식 요약(운반 문서에서 다시 만들 수 있는 사본)은 넣지 않는다 — 이름만 바꾼 것으로 검증이 낡지 않게.
    문서 서식(종류 page)은 쪽 설정·바탕 글도 넣고, fmt="docx"(`verifyDocx` 의 해시)는 docx 운반 문서의 해시도 넣는다 — 표·글 서식의 hwpx 해시는 전과 같다(이미 붙은 기록이 낡지 않게)."""
    m = meta if isinstance(meta, dict) else {}
    items = [{"key": i.get("key"), "level": i.get("level"), "marker": i.get("marker")} for i in m.get("items") or [] if isinstance(i, dict)]
    subject = {"carrier": m.get("carrierSha256"), "bands": m.get("bands"), "blueprint": m.get("blueprint"), "items": items}
    if m.get("kind") == "page":
        subject.update(page=m.get("page"), body=m.get("body"))
    if m.get("kind") == "cover":  # 표지 서식(② §14) — 쪽 설정 + 부분의 뜻(차례 · 종류 · 역할). 견본 글·서식 요약은 운반 문서의 사본이라 넣지 않는다
        subject.update(page=m.get("page"), parts=[{"key": p.get("key"), "type": p.get("type"), "role": p.get("role")} for p in m.get("parts") or [] if isinstance(p, dict)])
    if fmt == "docx":
        subject["docx"] = m["docx"].get("sha256") if isinstance(m.get("docx"), dict) else None
    return hashlib.sha256(json.dumps(subject, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


# ---- PDF 재기 ----------------------------------------------------------------------------------------------------

def _rgb3(c):
    """PyMuPDF 색(회색 1값 · RGB 3값 · CMYK 4값) → (r, g, b) 0~1 | None."""
    if c is None:
        return None
    c = tuple(float(x) for x in c) if isinstance(c, (tuple, list)) else (float(c),)
    if len(c) == 1:
        return (c[0],) * 3
    if len(c) == 4:
        return tuple((1 - x) * (1 - c[3]) for x in c[:3])
    return c[:3] if len(c) == 3 else None


def _seg(out, a, b, width, color, dashed):
    """두 점 → 가로·세로 선 하나(비스듬한 선은 뺀다 — 칸 대각선 등)."""
    (ax, ay), (bx, by) = a, b
    d = "h" if abs(ay - by) < 0.3 and abs(ax - bx) >= 0.3 else "v" if abs(ax - bx) < 0.3 and abs(ay - by) >= 0.3 else None
    if d:
        out.append({"dir": d, "x0": min(ax, bx), "y0": min(ay, by), "x1": max(ax, bx), "y1": max(ay, by), "w": float(width or 0), "color": color, "dashed": dashed})


def _shapes(page):
    """쪽의 그림 명령 → (선 [{dir: h|v, x0, y0, x1, y1, w(pt), color, dashed}], 채움 사각형 [{x0, y0, x1, y1, fill}] — 그린 차례)."""
    segs, rects = [], []
    for d in page.get_drawings():
        items, kind = d.get("items") or (), d.get("type") or ""
        fill, color = _rgb3(d.get("fill")), _rgb3(d.get("color"))
        if "f" in kind and fill is not None:
            r = d["rect"]
            w, h = r.x1 - r.x0, r.y1 - r.y0
            boxy = bool(items) and all(it[0] in ("re", "qu") or (it[0] == "l" and (abs(it[1].x - it[2].x) < 0.05 or abs(it[1].y - it[2].y) < 0.05)) for it in items)
            if boxy and w > 0 and h > 0:
                if min(w, h) <= THIN and max(w, h) >= 3 * min(w, h):  # 가는 채움 사각형 = 선
                    mid = ((r.y0 + r.y1) / 2, (r.x0 + r.x1) / 2)
                    _seg(segs, (r.x0, mid[0]) if w >= h else (mid[1], r.y0), (r.x1, mid[0]) if w >= h else (mid[1], r.y1), min(w, h), fill, False)
                else:
                    rects.append({"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1, "fill": fill})
        if "s" in kind and color is not None:
            dashed = bool(re.search(r"\d", str(d.get("dashes") or "").split("]")[0]))
            for it in items:
                if it[0] == "l":
                    _seg(segs, (it[1].x, it[1].y), (it[2].x, it[2].y), d.get("width"), color, dashed)
                elif it[0] in ("re", "qu"):
                    q = it[1]
                    pts = [(q.x0, q.y0), (q.x1, q.y0), (q.x1, q.y1), (q.x0, q.y1)] if it[0] == "re" else [(p.x, p.y) for p in (q.ul, q.ur, q.lr, q.ll)]
                    for a, b in zip(pts, pts[1:] + pts[:1]):
                        _seg(segs, a, b, d.get("width"), color, dashed)
    return segs, rects


def measure_pdf(path, tables=True, limit=None) -> dict:
    """PDF → {"count": 쪽 수, "pages": [{"w", "h", "sheet", "lines": [pdf_map 줄 — text·bbox·block·chars[(글자, x0, y0, x1, y1, span 번호, 굵게)]·spans[(글꼴, 크기, flags, 색)]],
    "type3": {Type3 글꼴 이름}, "segs": [가로·세로 선], "rects": [채움 사각형], "tables": [{"rows", "cols", "bbox", "cells": [칸 상자 | None]}]}]}.
    path = PDF 경로 또는 PDF 바이트(올린 파일). 줄은 머리말·꼬리말 띠를 거르지 않은 것(pdf_map.read_pdf 와 다른 점). tables=False 면 표 감지를 안 한다 · limit = 읽을 쪽 수(파일에서 추출)."""
    import fitz
    out = []
    with (fitz.open(stream=bytes(path), filetype="pdf") if isinstance(path, (bytes, bytearray)) else fitz.open(path)) as doc:
        if doc.needs_pass:
            raise ValueError("암호가 걸린 PDF 입니다")
        count = len(doc)
        for i, page in enumerate(doc):
            if limit is not None and i >= limit:
                break
            stroked, lines = pdf_map._stroked(page), []
            for bi, blk in enumerate(page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)["blocks"]):
                for ln in blk.get("lines") or []:
                    line = pdf_map._line(bi, ln, stroked)
                    if line["text"].strip():
                        lines.append(line)
            segs, rects = _shapes(page)
            found = []
            if tables and (segs or rects):
                try:
                    found = [{"rows": t.row_count, "cols": t.col_count, "bbox": [float(v) for v in t.bbox], "cells": [tuple(c) if c else None for c in t.cells]}
                             for t in page.find_tables().tables]
                except Exception as e:  # 표 감지는 참고 — 실패해도 잰 값은 쓴다
                    log.info("find_tables 실패(%s쪽): %s", i + 1, e)
            fs = page.get_fonts()
            out.append({"w": page.rect.width, "h": page.rect.height, "sheet": i, "lines": lines, "segs": segs, "rects": rects, "tables": found,
                        "type3": {f[3] for f in fs if f[2] == "Type3"} | {f[4] for f in fs if f[2] == "Type3"}})
    return {"count": count, "pages": out}


def proof_png(path, full=False) -> bytes | None:
    """견본 그림 — 글·선이 있는 첫 쪽을 내용 둘레(여백 PROOF_PAD pt)로 잘라 PROOF_DPI 로.
    full(spec_서식복사 ② §13 — 쪽 설정·표지): 내용 둘레를 자르지 않은 **첫 쪽 전체**(여백이 보여야 하는 서식) — PROOF_DPI 를 넘지 않고 긴 변이 PROOF_FULL_PX 안팎이 되게 줄인다(A4 = 약 94dpi).
    path = PDF 경로 또는 PDF 바이트."""
    import fitz
    with (fitz.open(stream=bytes(path), filetype="pdf") if isinstance(path, (bytes, bytearray)) else fitz.open(path)) as doc:
        if not len(doc):
            return None
        if full:
            page = doc[0]
            long_in = max(page.rect.width, page.rect.height) / 72 or 1.0
            return page.get_pixmap(dpi=max(24, min(PROOF_DPI, round(PROOF_FULL_PX / long_in))), alpha=False).tobytes("png")
        for page in doc:
            box = fitz.Rect()
            for b in page.get_text("blocks"):
                if str(b[4]).strip():
                    box |= fitz.Rect(b[:4])
            for d in page.get_drawings():
                box |= d["rect"]
            if not box.is_empty:
                clip = (box + (-PROOF_PAD, -PROOF_PAD, PROOF_PAD, PROOF_PAD)) & page.rect
                return page.get_pixmap(dpi=PROOF_DPI, clip=clip, alpha=False).tobytes("png")
        return doc[0].get_pixmap(dpi=PROOF_DPI, alpha=False).tobytes("png")


# ---- 기대값(운반 문서) -------------------------------------------------------------------------------------------

def _paras(blocks):
    return [b for b in blocks or [] if b.get("type") == "paragraph"]


def expect_table(cdoc) -> dict | None:
    """운반 문서의 첫 표 → {"table", "rows", "cols", "widthsPt"(격자 열 폭), "heightsPt", "cells": [{row, col, rowSpan, colSpan, text, fill, widthPt(칸의 제 폭), edges{t,r,b,l}, chars[(키 글자, 원 글자, 글자 모양)],
    auto(자동 번호 문단이 있음), nested(칸 안 표·그림), zoned(영역 배경이 덮음)}]} | None(표 없음)."""
    tb = next((b for b in cdoc.blocks() if b["type"] == "table"), None)
    if tb is None:
        return None
    tbl, cells, nr, nc = cdoc._tgrid(cdoc._ids[tb["id"]])
    heights, widths = cdoc._tsizes(cells, nr, nc)
    lines = tb.get("borderFills") or {}
    zoned = set()
    for z in tbl.iter("{*}cellzone"):  # 표 「셀 영역」 배경 — 칸의 fill 에 안 잡힌다
        if cdoc._fill(z.get("borderFillIDRef")) is not None:
            zoned |= {(r, c) for r in range(int(z.get("startRowAddr", 0)), int(z.get("endRowAddr", -1)) + 1)
                      for c in range(int(z.get("startColAddr", 0)), int(z.get("endColAddr", -1)) + 1)}
    out = []
    for c in tb["cells"]:
        ps = _paras(c.get("blocks"))
        sz = cdoc._ids[c["id"]].find("{*}cellSz")
        out.append({"row": c["row"], "col": c["col"], "rowSpan": c["rowSpan"], "colSpan": c["colSpan"], "text": c.get("text") or "", "fill": c.get("fill"),
                    "widthPt": hwpx_layout.hu(sz.get("width")) / 100 if sz is not None else 0,
                    "edges": lines.get(c.get("bf")) or {}, "chars": [x for p in ps for x in pdf_style._web_chars(p)],
                    "auto": any(p.get("list") or p.get("outlineLevel") or p.get("autoNum") for p in ps),
                    "nested": any(b.get("type") != "paragraph" for b in c.get("blocks") or []),
                    "zoned": any((r, k) in zoned for r in range(c["row"], c["row"] + c["rowSpan"]) for k in range(c["col"], c["col"] + c["colSpan"]))})
    return {"table": tb["id"], "rows": nr, "cols": nc, "widthsPt": [w / 100 for w in widths], "heightsPt": [h / 100 for h in heights], "cells": out}


def expect_text(cdoc, meta=None) -> dict | None:
    """글 운반 문서 → {"leftMm": 쪽 왼 여백, "items": [{key, id, text, format, runs, auto}], "metaItems": meta 의 item 수 | None(meta·items 를 안 줌 — 수를 모름)} —
    첫 문단 뒤의 본문 최상위 문단이 차례대로 meta.items. 견본 문단(글·서식을 읽을 수 있는 문단)이 하나도 없으면 None."""
    blocks = cdoc.blocks()
    by = {b["id"]: b for b in _paras(blocks) if not b.get("captionOf")}
    ids = [cdoc._id(p) for p in list(cdoc._sections[0].iterchildren(P))[1:]]   # style_carrier.para_ids 와 같은 차례(글 없는 문단도 자리를 지킨다)
    if not any(i in by for i in ids):
        return None
    ps = [by.get(i) or {"id": i} for i in ids]
    given = meta.get("items") if isinstance(meta, dict) else None
    items = [i if isinstance(i, dict) else {} for i in given or []]
    page = next((b["page"] for b in blocks if b.get("page")), None) or {}
    out = []
    for n, p in enumerate(ps):
        it = items[n] if n < len(items) else {}
        out.append({"key": it.get("key") or f"i{n + 1}", "id": p["id"], "text": p.get("text") or "", "format": p.get("format") or {}, "runs": p.get("runs"),
                    "auto": bool(p.get("list") or p.get("outlineLevel") or p.get("autoNum")) or (it.get("marker") or {}).get("mode") == "auto"})
    return {"leftMm": float((page.get("marginsMm") or {}).get("l") or 0), "items": out, "metaItems": len(items) if isinstance(given, list) else None}


# ---- 검사 한 줄 ---------------------------------------------------------------------------------------------------

def _tally(what):
    return {"what": what, "status": "unknown", "pass": 0, "fail": 0, "unknown": 0, "examples": [], "note": ""}


def _put(t, v, where="", want="", got="", show=None):
    """검사 t 에 한 건(v = pass|fail|unknown). 보기는 fail 만(show 를 주면 그대로) EXAMPLES 개까지."""
    t[v] += 1
    if (v == "fail" if show is None else show) and len(t["examples"]) < EXAMPLES:
        t["examples"].append({"where": str(where), "want": str(want), "got": str(got)})


def _done(t, note="", empty="잴 것이 없음", strict=False):
    """세기 → 상태: fail 이 있으면 fail · 통과가 없거나(strict 면 하나라도) 모르는 것이 있으면 unknown · 아니면 pass."""
    t["status"] = "fail" if t["fail"] else "unknown" if (t["unknown"] and (strict or not t["pass"])) or not (t["pass"] or t["unknown"]) else "pass"
    t["note"] = note or t["note"] or ("" if t["pass"] or t["fail"] or t["unknown"] else empty)
    return t


def unsupported(what, note):
    return {"what": what, "status": "unsupported", "pass": 0, "fail": 0, "unknown": 0, "examples": [], "note": note}


def summarize(checks, pages=1):
    """검사들 → (전체 판정, coverage, 알림 글들). fail 이 하나라도 fail · fail 0 이고 (unknown 이 검사한 것의 30% 초과 · 글꼴 대체 · 2쪽 이상 · 검사한 것이 없음 ·
    **핵심 검사(글자 크기·굵게·글꼴) 가운데 하나가 통과 0 · 모름 1 이상**) 이면 warn · 아니면 ok. 핵심 검사는 검사마다 따로 본다 — 전체 비율(30%)만 보면 괘선 통과 수에 묻힌다."""
    cov = {k: sum(c.get(k, 0) for c in checks) for k in ("pass", "fail", "unknown")}
    cov["unsupported"] = sum(1 for c in checks if c["status"] == "unsupported")
    n = cov["pass"] + cov["fail"] + cov["unknown"]
    subst = sum(c.get("substituted", 0) for c in checks)
    notes = []
    if subst:
        notes.append(f"대체 글꼴로 출력 {subst}곳")
    if pages >= 2:
        notes.append(f"{pages}쪽으로 출력됨")
    if n and cov["unknown"] / n > UNKNOWN_SHARE:
        notes.append(f"못 잰 것 {cov['unknown']}/{n}")
    if not n:
        notes.append("검사한 것이 없음")
    for what, name in CORE_CHECKS:
        c = next((c for c in checks if c.get("what") == what), None)
        if c is not None and not c.get("pass") and c.get("unknown") and not c.get("substituted"):  # 대체 글꼴은 위에서 이미 알린다
            notes.append(f"{name} 재지 못함(모름 {c['unknown']} · 통과 0)")
    status = "fail" if cov["fail"] or any(c["status"] == "fail" for c in checks) else "warn" if notes else "ok"
    return status, cov, notes


# ---- 글자 모양 견줌 -----------------------------------------------------------------------------------------------

def _aliases():
    if not _ALIASES:
        from app import heading_guides
        _ALIASES.extend({fonts._norm(n) for n in g} for g in heading_guides.TOLERANCE_DEFAULT["fontAliases"])
    return _ALIASES


def _face_keys(name):
    n = fonts._norm(re.sub(r"^[A-Z]{6}\+", "", name or ""))
    return {n, _STYLE_TAIL.sub("", n)} - {""}


def face_verdict(want, got, type3=False, index=None):
    """요청 글꼴 이름과 PDF 글꼴 이름 → same(같은 글꼴) · subst(다른 글꼴 = 대체 글꼴로 출력) · unknown(PDF 글꼴 이름을 모름 — Type3 「T1」·깨진 「????」, 또는 요청 글꼴 없음).
    느슨하게: 공백·대소문자·굵게 꼬리(Bold…)를 접고, 한글 ↔ 영문 이름은 오차 기준의 글꼴 별칭과 이 PC 글꼴 이름표(index = fonts.FontIndex, 없으면 건너뜀)로."""
    bare = re.sub(r"^[A-Z]{6}\+", "", got or "")
    if not want:
        return "unknown"
    if type3 or not bare or set(bare) <= {"?"}:
        return "same" if index is not None and bare and index.broken_match(bare, index.family(want)) else "unknown"
    a, b = _face_keys(want), _face_keys(got)
    if a & b or any(g & a and g & b for g in _aliases()):
        return "same"
    if index is not None:
        fa, fb = index.family(want), index.family(got)
        if fa and fa == fb:
            return "same"
    return "subst"


def _channels(c):
    """'#RRGGBB' | 0xRRGGBB → (r, g, b) 0~1."""
    n = int(c[1:], 16) if isinstance(c, str) else int(c)
    return ((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02X}" for v in rgb)


def _near(a, b, tol=COLOR_TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


_RANK = {"pass": 0, "unknown": 1, "fail": 2}


def compare_chars(pairs, where, T, index=None):
    """글자 짝 [(원 글자, 웹 글자 모양, PDF 글자(pdf_map chars 항목), span (글꼴, 크기, flags, 색), Type3?)] → 검사 T["fontSize"|"bold"|"color"|"fontFace"] 에 한 건씩
    (그 묶음(칸·견본 줄)에서 가장 나쁜 글자의 판정: fail > unknown > pass). 글꼴이 다르면 unknown + T["fontFace"]["substituted"]."""
    res = {k: ["pass", "", ""] for k in ("fontSize", "bold", "color", "fontFace")}

    def worse(k, v, want, got):
        if _RANK[v] > _RANK[res[k][0]]:
            res[k] = [v, want, got]
    subst = None
    for ch, wf, pc, sp, t3 in pairs:
        want, why = pdf_style._want(wf)
        if not want:
            worse("fontSize", "unknown", "크기 모름", f"{sp[1]:.1f}pt")
        elif abs(sp[1] - want) > SIZE_TOL:
            worse("fontSize", "fail", f"{wf['sizePt']:g}pt" + (f"({why} → {want:.1f}pt)" if why else ""), f"{sp[1]:.1f}pt 「{ch}」")
        if t3:  # Type3(한글 전용 글꼴 HFT): 굵게를 글꼴 이름·긋기로 알 수 없다
            worse("bold", "unknown", "굵게" if wf.get("bold") else "보통", "Type3 글꼴 — 알 수 없음")
        elif bool(wf.get("bold")) != bool(pc[6]):
            worse("bold", "fail", "굵게" if wf.get("bold") else "보통", ("굵게" if pc[6] else "보통") + f" 「{ch}」 {sp[0]}")
        color = (wf.get("color") or "#000000").upper()
        if not _near(_channels(color), _channels(sp[3])):
            worse("color", "fail", color, f"#{int(sp[3]):06X} 「{ch}」")
        face, _ = pdf_style._web_face(ch, wf)
        v = face_verdict(face, sp[0], t3, index)
        if v == "subst":
            subst = subst or (face, re.sub(r"^[A-Z]{6}\+", "", sp[0]))
            worse("fontFace", "unknown", face, f"대체 글꼴로 출력 — {subst[1]}")
        elif v == "unknown":
            T["fontFace"]["_nameless"] = True
            worse("fontFace", "unknown", face or "글꼴 모름", "PDF 글꼴 이름을 알 수 없음" + (" (Type3)" if t3 else ""))
    for k, (v, want, got) in res.items():
        _put(T[k], v, where, want, got, show=v == "fail" or (k == "fontFace" and subst is not None))
    if subst:
        T["fontFace"]["substituted"] = T["fontFace"].get("substituted", 0) + 1
        T["fontFace"].setdefault("_faces", Counter())[subst] += 1


def _face_note(t):
    """fontFace 검사의 알림 — 대체된 글꼴(요청 → PDF) 또는 이름 모를 글꼴. 견줌 중에 쓴 안쪽 키(_faces·_nameless)는 여기서 뗀다."""
    faces, nameless = t.pop("_faces", None), t.pop("_nameless", False)
    if faces:
        return "대체 글꼴로 출력 — " + " · ".join(f"{a} → {b}" for (a, b), _ in faces.most_common(4))
    return "PDF 글꼴 이름을 알 수 없는 글자가 있음(한글 전용 글꼴 등)" if nameless else ""


def _pairs_of(web, got, type3):
    """웹 글자 [(키, 원 글자, 모양)] 와 PDF 글자 [(글자, span)] 의 키가 같으면 글자 짝, 아니면 None."""
    pdf = [(kc, pc, sp) for pc, sp in got for kc in key_text(pc[0])]
    if "".join(w[0] for w in web) != "".join(p[0] for p in pdf):
        return None
    return [(ch, wf, pc, sp, sp[0] in type3) for (_, ch, wf), (_, pc, sp) in zip(web, pdf)]


# ---- 표 견줌 ------------------------------------------------------------------------------------------------------

def _clusters(vals, tol):
    """정렬한 (값, 정확한가) 들을 tol 안끼리 묶어 대표값 — 묶음에 정확한 값(채움 사각형의 변)이 있으면 그 평균, 없으면 전체 평균."""
    out = []
    for v, exact in sorted(vals):
        if out and v - out[-1][-1][0] <= tol:
            out[-1].append((v, exact))
        else:
            out.append([(v, exact)])
    return [sum(x) / len(x) for g in out for x in [[v for v, e in g if e] or [v for v, _ in g]]]


def plain_segs(page):
    """쪽의 선에서 글 꾸밈(밑줄·취소선)을 뺀 것 — 글 줄 상자의 가로 범위 안(±1pt)에 들고 그 줄 높이(아래로 2.5pt 까지)에 걸친 가로선.
    칸의 괘선은 칸 여백만큼 글보다 길어 여기 안 걸린다(실측: 밑줄 친 「예시)」 가 행 경계로 세어졌다)."""
    boxes = [ln["bbox"] for ln in page.get("lines") or []]
    return [s for s in page.get("segs") or [] if not (s["dir"] == "h" and any(
        b[0] - 1 <= s["x0"] and s["x1"] <= b[2] + 1 and b[1] - 0.5 <= s["y0"] <= b[3] + 2.5 for b in boxes))]


def row_bounds(exp, ys):
    """잰 가로 경계 ys(위 → 아래 묶음 대표값)를 행 경계 0..rows 에 맞춘다 → ([y…], 어림한 경계 수) | None.
    **보일 경계**(그 경계에 닿는 칸 변에 괘선이 있거나 음영 칸의 위·아래)만 PDF 에 그려진다 — 그 수가 잰 수와 같을 때만 차례대로 맞춘다(다르면 None: 지어내지 않는다).
    사이 높이가 1pt 미만으로 저장된 보일 경계들은 겹친 한 묶음(실측: 0.01pt 행). 안 보이는 경계(선 없는 제목 행의 위 등)는 저장된 행 높이의 비율로 어림한다 —
    그 자리에는 견줄 선이 없고, 칸 상자(글·음영 찾기)에만 쓴다."""
    nr, cells = exp["rows"], exp["cells"]
    H = list(exp.get("heightsPt") or []) + [0.0] * nr
    vis = [False] * (nr + 1)
    for c in cells:
        top, bot = c["row"], min(nr, c["row"] + c["rowSpan"])
        vis[top] = vis[top] or bool(c.get("fill") or c["edges"].get("t"))
        vis[bot] = vis[bot] or bool(c.get("fill") or c["edges"].get("b"))
    groups = []
    for j in range(nr + 1):
        if vis[j]:
            if groups and sum(H[groups[-1][-1]:j]) < 1.0:
                groups[-1].append(j)
            else:
                groups.append([j])
    if not groups or len(groups) != len(ys):
        return None
    Y = [None] * (nr + 1)
    for g, y in zip(groups, ys):
        for j in g:
            Y[j] = y
    known = [j for j in range(nr + 1) if Y[j] is not None]
    for j in [j for j in range(nr + 1) if Y[j] is None]:
        a, b = max((k for k in known if k < j), default=None), min((k for k in known if k > j), default=None)
        if a is None:
            Y[j] = Y[b] - sum(H[j:b])
        elif b is None:
            Y[j] = Y[a] + sum(H[a:j])
        else:
            Y[j] = Y[a] + (Y[b] - Y[a]) * (sum(H[a:j]) / sum(H[a:b]) if sum(H[a:b]) > 0 else 0)
    return Y, nr + 1 - len(known)


def table_frame(exp, page) -> dict:
    """잰 선·채움에서 표의 틀 → {"left", "right", "widthPt", "y": 행 경계(rows+1) | None, "guessed": 어림한 경계 수, "note"}. 못 정한 것은 None(까닭은 note).
    행 경계 = 가로선·채움 사각형의 y 를 묶은 것을 보일 경계에 맞춘 것(row_bounds) — 수가 안 맞으면 None(행은 내용만큼 자라므로 저장된 높이로 지어내지 않는다)."""
    segs, rects = page.get("segs") or [], page.get("rects") or []
    hs, vs = [s for s in segs if s["dir"] == "h"], [s for s in segs if s["dir"] == "v"]
    out = {"left": None, "right": None, "widthPt": None, "y": None, "guessed": 0, "note": ""}
    exact = [v for r in rects for v in (r["x0"], r["x1"])] + [s["x0"] for s in vs]
    lo, hi = [s["x0"] for s in hs] + exact, [s["x1"] for s in hs] + exact
    if not lo:
        out["note"] = "표의 선·음영이 PDF 에 없어 자리를 못 잡음"
        return out

    def snap(v):  # 가로선은 표 끝보다 조금 길다(실측 −0.48 · +0.60pt) — 가까운 세로선·채움 변이 있으면 그 자리
        near = [e for e in exact if abs(e - v) <= EDGE_TOL]
        return min(near, key=lambda e: abs(e - v)) if near else v
    out["left"], out["right"] = snap(min(lo)), snap(max(hi))
    out["widthPt"] = out["right"] - out["left"]
    ys = _clusters([(v, True) for r in rects for v in (r["y0"], r["y1"])] + [(s["y0"], False) for s in hs], ROW_TOL)
    got = row_bounds(exp, ys)
    if got is None:
        out["note"] = f"가로 경계 {len(ys)}개 — 행 {exp['rows']}개의 보일 경계와 수가 안 맞아 칸 자리를 못 잡음"
    else:
        out["y"], out["guessed"] = got
    return out


def _occupancy(exp):
    occ = [[None] * exp["cols"] for _ in range(exp["rows"])]
    for i, c in enumerate(exp["cells"]):
        for r in range(c["row"], min(exp["rows"], c["row"] + c["rowSpan"])):
            for k in range(c["col"], min(exp["cols"], c["col"] + c["colSpan"])):
                occ[r][k] = i
    return occ


def cell_boxes(exp, occ, left, scale, Y):
    """칸마다 PDF 상자 (x0, y0, x1, y1) + 행마다 [(x0, x1, 칸 번호)]. 한글은 행마다 칸의 **제 폭**(cellSz)을 왼쪽부터 쌓는다 — 칸 하나만 끌어 넓힌 표는
    열 경계가 행마다 다르다(실측: 연구개발계획서 양식 첫 표, 격자 폭 누적과 3.9pt 어긋남). 위 행에서 내려온 합친 칸은 그 칸의 오른끝에서 잇는다."""
    cells, widths = exp["cells"], exp["widthsPt"]
    box, rows = [None] * len(cells), []
    for r in range(exp["rows"]):
        x, prev, row = left, None, []
        for k in range(exp["cols"]):
            i = occ[r][k]
            if i is None or i == prev:
                continue
            prev, c = i, cells[i]
            if box[i] is None:
                w = c.get("widthPt") or sum(widths[c["col"]:c["col"] + c["colSpan"]])
                box[i] = (x, Y[c["row"]], x + w * scale, Y[min(exp["rows"], c["row"] + c["rowSpan"])])
            x = box[i][2]
            row.append((box[i][0], box[i][2], i))
        rows.append(row)
    return box, rows


def _cell_chars(page, Y, rows):
    """쪽의 글자를 칸으로(글자 가운데 점이 든 칸) → {칸 번호: [(PDF 글자, span)]} — 칸 안에서 읽는 차례(위 → 아래 줄, 줄 안 왼 → 오른)."""
    nr, lines, got = len(Y) - 1, page.get("lines") or [], {}
    for li, ln in enumerate(lines):
        for pc in ln.get("chars") or ():
            r, cx = bisect_right(Y, (pc[2] + pc[4]) / 2) - 1, (pc[1] + pc[3]) / 2
            i = next((i for x0, x1, i in rows[r] if x0 <= cx < x1), None) if 0 <= r < nr else None
            if i is not None:
                got.setdefault(i, []).append((li, pc, ln["spans"][pc[5]]))
    out = {}
    for i, items in got.items():
        mid = {li: (lines[li]["bbox"][1] + lines[li]["bbox"][3]) / 2 for li in {x[0] for x in items}}
        rank, last, n = {}, None, 0
        for li in sorted(mid, key=mid.get):  # 같은 높이의 줄(글꼴이 달라 나뉜 줄)은 한 줄로
            h = lines[li]["bbox"][3] - lines[li]["bbox"][1]
            if last is not None and mid[li] - last > 0.5 * h:
                n += 1
            rank[li], last = n, mid[li]
        out[i] = [(pc, sp) for li, pc, sp in sorted(items, key=lambda x: (rank[x[0]], x[1][1]))]
    return out


def _cover(near, axis, lo, hi):
    """경계 가까이의 선 near 가 [lo, hi] 를 덮은 비율 · 그 변의 반 이상을 덮은 선들."""
    a, b = ("x0", "x1") if axis == "h" else ("y0", "y1")
    spans = sorted(((max(lo, s[a]), min(hi, s[b]), s) for s in near if min(hi, s[b]) > max(lo, s[a])), key=lambda t: t[:2])
    got, end = 0.0, lo
    for s0, s1, _ in spans:
        if s1 > end:
            got += s1 - max(s0, end)
            end = s1
    return got / (hi - lo), [s for s0, s1, s in spans if s1 - s0 >= 0.5 * (hi - lo)]


def _line_text(side):
    return f"{side.get('type')} {side.get('widthMm')}mm"


_SIDES = (("t", "h", "위"), ("b", "h", "아래"), ("l", "v", "왼쪽"), ("r", "v", "오른쪽"))


def _side_span(box, side):
    """칸 상자의 한 변 → (자리, 시작, 끝)."""
    x0, y0, x1, y1 = box
    return {"t": (y0, x0, x1), "b": (y1, x0, x1), "l": (x0, y0, y1), "r": (x1, y0, y1)}[side]


def _edges(exp, box, page, T):
    """칸의 변마다: 괘선이 있는 변의 자리에 선이 있는가(edge) · 그 선의 굵기(lineWidth). 괘선이 없는 변은 그 자리에 다른 칸의 괘선(맞닿은 칸의 맞은편 변 —
    높이 0 인 행 너머의 칸까지)도 없을 때만 「선이 없어야 함」 으로 본다. 굵기는 그 자리의 괘선(이 칸·맞닿은 칸)이 모두 실선일 때만 견준다(겹줄은 가는 선 둘, 점선은 조각)."""
    cells = exp["cells"]
    want = {"h": {}, "v": {}}   # 축 → 자리 통(4pt) → [(자리, 시작, 끝, 괘선, 칸 번호)]
    drawn = {"h": {}, "v": {}}  # 축 → 자리 통 → [선]
    live = [i for i, b in enumerate(box) if b is not None and b[2] - b[0] >= 2 and b[3] - b[1] >= 2]  # 높이·폭이 0 인 칸은 변을 견주지 않는다(괘선 기대에는 넣는다)
    for i, b in enumerate(box):
        if b is None:
            continue
        for side, axis, _ in _SIDES:
            line = cells[i]["edges"].get(side)
            at, lo, hi = _side_span(b, side)
            if line and hi - lo >= 0.5:
                want[axis].setdefault(int(at // 4), []).append((at, lo, hi, line, i))
    for s in page.get("segs") or []:
        drawn[s["dir"]].setdefault(int(s["y0" if s["dir"] == "h" else "x0"] // 4), []).append(s)

    def around(table, at):
        return [x for k in (int(at // 4) - 1, int(at // 4), int(at // 4) + 1) for x in table.get(k, ())]
    for i in live:
        c = cells[i]
        for side, axis, name in _SIDES:
            at, lo, hi = _side_span(box[i], side)
            own, where = c["edges"].get(side), f"{a1(c['row'], c['col'])} {name}"
            others = [w[3] for w in around(want[axis], at) if w[4] != i and abs(w[0] - at) <= EDGE_TOL and min(hi, w[2]) - max(lo, w[1]) >= COVER_ANY * (hi - lo)]
            near = [s for s in around(drawn[axis], at) if abs(s["y0" if axis == "h" else "x0"] - at) <= EDGE_TOL + s["w"] / 2]
            cov, hit = _cover(near, axis, lo, hi)
            if not own:
                if not others:  # 어느 칸도 이 자리에 괘선을 두지 않았다
                    _put(T["edge"], "fail" if cov >= COVER_SOLID else "pass", where, "선 없음", f"선 {max((s['w'] for s in hit), default=0):.2f}pt")
                continue
            both = [own, *others]
            solid = all(s["type"] == "SOLID" for s in both)
            if cov < (COVER_SOLID if own["type"] == "SOLID" else COVER_ANY):
                _put(T["edge"], "fail", where, _line_text(own), "선 없음" if cov < 0.05 else f"변의 {cov:.0%} 만")
                continue
            _put(T["edge"], "pass")
            if not solid or not hit:
                _put(T["lineWidth"], "unknown")
                continue
            wants = sorted({s["widthMm"] * PT_MM for s in both})
            ok = any(abs(s["w"] / w - 1) <= LINE_TOL for s in hit for w in wants if w > 0)
            _put(T["lineWidth"], "pass" if ok else "fail", where, " / ".join(f"{w / PT_MM:.2g}mm({w:.2f}pt)" for w in wants),
                 " / ".join(dict.fromkeys(f"{s['w']:.2f}pt" for s in hit)))


def check_table(exp, measure, index=None) -> list[dict]:
    """표 운반 문서의 기대값(expect_table) × 잰 값(measure_pdf) → 검사 목록(TABLE_CHECKS 차례 + 견주지 않는 것 UNSUPPORTED_TABLE(「재지 못함」) — render 는 run 이 붙인다).
    칸 단위: text(글이 있는 칸은 그 글이 나옴 · **빈 칸은 PDF 에서도 빔** — 글자·숫자가 있으면 「뜻밖의 글」 fail)·fontSize·bold·color·fontFace·fill · 칸의 변 단위: edge·lineWidth ·
    한 건: pages·width. 자리(행 경계)를 못 잡거나 2쪽 이상이면 자리에 기대는 검사는 unknown."""
    T = {k: _tally(k) for k in TABLE_CHECKS}
    pages, count = measure.get("pages") or [], measure.get("count") or 0
    page = next((p for p in pages if p.get("segs") or p.get("rects") or p.get("lines")), pages[0] if pages else {})
    page = {**page, "segs": plain_segs(page)}  # 밑줄·취소선은 괘선이 아니다
    nr, nc, cells = exp["rows"], exp["cols"], exp["cells"]
    _put(T["pages"], "pass" if count == 1 else "unknown", "문서", "1쪽", f"{count}쪽", show=count != 1)
    fr = table_frame(exp, page)
    located = count == 1 and fr["y"] is not None and fr["left"] is not None
    why = fr["note"] or (f"{count}쪽으로 출력되어 칸 자리를 견주지 않음" if count != 1 else "")
    total = sum(exp["widthsPt"])
    scale = 1.0
    if fr["widthPt"] is None or total <= 0:
        _put(T["width"], "unknown", "표 폭", f"{total:.1f}pt", "못 잼", show=True)
    else:
        ok = abs(fr["widthPt"] / total - 1) <= WIDTH_TOL
        scale = fr["widthPt"] / total if ok else 1.0  # 쪽 배율(한글 PDF 는 문서 pt × 0.9995) — 폭이 어긋난 표는 배율로 덮지 않는다
        _put(T["width"], "pass" if ok else "fail", "표 폭", f"{total:.1f}pt", f"{fr['widthPt']:.1f}pt")
    occ = _occupancy(exp)
    texted = [(i, c) for i, c in enumerate(cells) if c["chars"]]
    type3 = page.get("type3") or ()
    if located:
        box, rows = cell_boxes(exp, occ, fr["left"], scale, fr["y"])
        got = _cell_chars(page, fr["y"], rows)
        for i, c in texted:
            where = a1(c["row"], c["col"])
            pairs = None if c.get("nested") else _pairs_of(c["chars"], got.get(i) or [], type3)
            if pairs is None:
                seen = "".join(pc[0] for pc, _ in got.get(i) or [])
                v = "unknown" if c.get("nested") or (c.get("auto") and seen.strip()) else "fail"
                _put(T["text"], v, where, c["text"][:40], seen[:40] or "글 없음")
                for k in ("fontSize", "bold", "color", "fontFace"):
                    _put(T[k], "unknown")
                continue
            _put(T["text"], "pass")
            compare_chars(pairs, where, T, index)
        for i, c in enumerate(cells):  # 빈 칸도 글 견줌에 넣는다 — 운반 문서가 비었다고 한 칸에 글자·숫자가 찍혀 있으면 「뜻밖의 글」(남은 원본 글 · 엉뚱한 운반 문서)
            if c["chars"] or box[i] is None or box[i][2] - box[i][0] < 2 or box[i][3] - box[i][1] < 2:
                continue  # 글이 있는 칸(위에서 봄) · 높이·폭이 0 인 칸
            seen = "".join(pc[0] for pc, _ in got.get(i) or [])
            if not key_text(seen):
                _put(T["text"], "pass")
            else:  # 칸 안 표·그림 · 자동 번호 문단은 운반 문서 XML 에 없는 글이 찍힌다 — 모름
                _put(T["text"], "unknown" if c.get("nested") or c.get("auto") else "fail", a1(c["row"], c["col"]), "빈 칸", f"뜻밖의 글 「{seen.strip()[:40]}」")
        rects = page.get("rects") or []
        for i, c in enumerate(cells):
            if box[i] is None or box[i][2] - box[i][0] < 2 or box[i][3] - box[i][1] < 2:
                continue  # 높이·폭이 0 인 칸
            where, cx, cy = a1(c["row"], c["col"]), (box[i][0] + box[i][2]) / 2, (box[i][1] + box[i][3]) / 2
            hit = [r for r in rects if r["x0"] - 0.5 <= cx <= r["x1"] + 0.5 and r["y0"] - 0.5 <= cy <= r["y1"] + 0.5]
            top = hit[-1]["fill"] if hit else None
            if c.get("zoned"):
                _put(T["fill"], "unknown", where, c["fill"] or "없음", "표 영역 배경이 덮은 칸", show=True)
            elif c["fill"]:
                ok = _near(_channels(c["fill"]), top) if top else c["fill"].upper() == "#FFFFFF"
                _put(T["fill"], "pass" if ok else "fail", where, c["fill"].upper(), _hex(top) if top else "채움 없음")
            else:
                ok = top is None or _near(top, (1, 1, 1))
                _put(T["fill"], "pass" if ok else "fail", where, "음영 없음", _hex(top) if top else "")
        _edges(exp, box, page, T)
    else:  # 자리를 모름: 글은 PDF 전체에 있는지만, 나머지는 unknown
        stream = "".join(key_text(ln["text"]) for p in pages for ln in p.get("lines") or [])
        need = Counter("".join(x[0] for x in c["chars"]) for _, c in texted)
        short = {k for k, n in need.items() if stream.count(k) < n}
        for i, c in texted:
            k = "".join(x[0] for x in c["chars"])
            _put(T["text"], "pass" if k not in short else "unknown" if c.get("nested") or c.get("auto") else "fail", a1(c["row"], c["col"]), c["text"][:40], "PDF 에 없음")
            for name in ("fontSize", "bold", "color", "fontFace"):
                _put(T[name], "unknown")
        for c in cells:
            _put(T["fill"], "unknown")
            for s in "trbl":
                if c["edges"].get(s):
                    _put(T["edge"], "unknown")
                    _put(T["lineWidth"], "unknown")
    notes = {"pages": "" if count == 1 else f"{count}쪽으로 출력됨 — 표가 한 쪽에 안 들어가거나 쪽 나눔이 남았습니다", "fontFace": _face_note(T["fontFace"]),
             "lineWidth": "겹줄·점선은 굵기를 견주지 않음" if T["lineWidth"]["unknown"] and located else "",
             "bold": "Type3(한글 전용 글꼴)은 굵게를 알 수 없음" if T["bold"]["unknown"] and located and type3 else ""}
    empty = {"text": "글이 있는 칸이 없음", "fontSize": "잴 글이 없음", "bold": "잴 글이 없음", "color": "잴 글이 없음", "fontFace": "잴 글이 없음",
             "edge": "괘선이 없는 표", "lineWidth": "잴 선이 없음"}
    for k, t in T.items():
        _done(t, notes.get(k) or (why if not located and k not in ("pages", "width", "text") and t["unknown"] else ""), empty.get(k, "잴 것이 없음"),
              strict=k == "fontFace" and bool(t.get("substituted")))
    det = (page.get("tables") or [None])[0]
    more = ([f"선 없는 행 경계 {fr['guessed']}개는 저장된 행 높이로 어림"] if located and fr["guessed"] else []) + (
        [f"표 감지(참고) {det['rows']}×{det['cols']} — 운반 문서 {nr}×{nc}"] if det else [])  # 표 감지는 참고로만 — 합친 칸 때문에 다르게 센다
    T["edge"]["note"] = " · ".join([x for x in [T["edge"]["note"]] if x] + more)
    return [T[k] for k in TABLE_CHECKS] + [unsupported(k, note) for k, note in UNSUPPORTED_TABLE]


# ---- 글 견줌 ------------------------------------------------------------------------------------------------------

def check_text(exp, measure, index=None) -> list[dict]:
    """글 운반 문서의 기대값(expect_text) × 잰 값 → 검사 목록(TEXT_CHECKS 차례 + 못 재는 것 unsupported). item(견본 줄) 단위.
    견본 문단 수가 meta 의 item 수(metaItems — None 이면 모름)와 다르면 text 가 fail.
    견본 줄은 글자·숫자 열에서 문서 차례로 찾는다(pdf_map.locate) · indent = 그 줄의 왼끝 x 와 「쪽 왼 여백 + 왼쪽 여백 + 첫 줄 들여쓰기」(±INDENT_TOL mm —
    가운데·오른쪽 정렬과 자동 번호 문단은 unknown)."""
    T = {k: _tally(k) for k in TEXT_CHECKS}
    pages, count = measure.get("pages") or [], measure.get("count") or 0
    _put(T["pages"], "pass" if count == 1 else "unknown", "문서", "1쪽", f"{count}쪽", show=count != 1)
    n_meta, n_paras = exp.get("metaItems"), len(exp["items"])
    mismatch = n_meta is not None and n_meta != n_paras  # n번째 견본 문단 ↔ meta.items[n] 의 짝이 깨졌다(운반 문서와 meta 가 어긋남) — 알림만이 아니라 실패
    if mismatch:
        _put(T["text"], "fail", "문서", f"item {n_meta}개", f"견본 문단 {n_paras}개")
    blocks = [{"id": it["id"], "type": "paragraph", "text": it["text"], "format": it["format"], "runs": it.get("runs")} for it in exp["items"]]
    its = {it["id"]: it for it in pdf_map.locate(pdf_map.items(blocks), pages)}
    at = pdf_style.key_index(pages)
    for item, blk in zip(exp["items"], blocks):
        where, it = item["key"], its.get(item["id"])
        web = pdf_style._web_chars(blk)
        if not web:
            for k in ("text", "fontSize", "bold", "color", "fontFace", "indent"):
                _put(T[k], "unknown", where, "", "견본 글이 없음", show=k == "text")
            continue
        pairs, first = [], None
        if it is not None and "pos" in it and "".join(w[0] for w in web) == it["key"]:
            for k, (kc, ch, wf) in enumerate(web):
                if it["pos"] + k >= len(at):
                    break
                pg, li, ci = at[it["pos"] + k]
                if ci is None:
                    break
                ln = pages[pg]["lines"][li]
                pc = ln["chars"][ci]
                if kc not in key_text(pc[0]):
                    break
                sp = ln["spans"][pc[5]]
                first = first or (pg, li)
                pairs.append((ch, wf, pc, sp, sp[0] in (pages[pg].get("type3") or ())))
        if len(pairs) < len(web):
            _put(T["text"], "fail", where, item["text"][:40], "견본 줄이 PDF 에 없음" if not pairs else "견본 줄의 일부만 찾음")
            for k in ("fontSize", "bold", "color", "fontFace", "indent"):
                _put(T[k], "unknown")
            continue
        _put(T["text"], "pass")
        compare_chars(pairs, where, T, index)
        f = item["format"]
        if item.get("auto") or f.get("align") in ("center", "right", "distribute"):
            _put(T["indent"], "unknown", where, "", "자동 번호 문단" if item.get("auto") else "가운데·오른쪽 정렬은 왼끝을 못 잼", show=True)
            continue
        line = pdf_style.visual_line(pages[first[0]], first[1])
        want = exp["leftMm"] + float(f.get("indentLeftMm") or 0) + max(float(f.get("firstLineMm") or 0), 0)
        got = line[0][2][1] / PT_MM
        _put(T["indent"], "pass" if abs(got - want) <= INDENT_TOL else "fail", where, f"{want:.1f}mm", f"{got:.1f}mm")
    notes = {"pages": "" if count == 1 else f"{count}쪽으로 출력됨", "fontFace": _face_note(T["fontFace"]),
             "text": f"견본 문단 {n_paras}개 — meta 의 item {n_meta}개와 수가 다름" if mismatch else ""}
    for k, t in T.items():
        _done(t, notes.get(k, ""), "견본 줄이 없음", strict=k == "fontFace" and bool(t.get("substituted")))
    return [T[k] for k in TEXT_CHECKS] + [unsupported(k, note) for k, note in UNSUPPORTED_TEXT]


# ---- 문서 서식 견줌(page-v1 — spec_서식복사 ② §7: 두 형식 같다) ---------------------------------------------------------

def _num(v, default=0.0):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def page_sample():
    """문서 서식 운반 문서의 견본 첫 줄 글(`style_page.SAMPLES[0]` — 검증이 자리를 재는 줄) | None(그 모듈이 없음)."""
    try:
        from app import style_page
        return str(style_page.SAMPLES[0])
    except Exception:  # noqa: BLE001 — 모듈 없음 · SAMPLES 가 비었음: 견본 글을 모른 채 첫 줄을 잰다
        return None


def expect_page(meta, fmt="hwpx", own=None) -> dict | None:
    """문서 서식의 기대값(명세 = meta.page · meta.body) → {"widthMm", "heightMm", "leftMm": 본문 왼끝, "topMm": 본문 위끝 | None(모름), "slackMm": 첫 줄이 더 내려올 수 있는 폭,
    "sample": 견본 첫 줄 글 | None, "format": 바탕 글의 서식 요약 | None} | None(쪽 설정이 없음).
    본문 왼끝 = 왼쪽 여백 + 제본 여백 · 본문 위끝 = 위 여백 t(`style_page` 의 뜻: 종이 끝에서 **본문**까지 — 한글의 위쪽 + 머리말, Word 의 top. 두 형식이 같다 · 값이 없으면 None = marginTop unknown).
    own(운반 문서가 스스로 적은 본문 상자)은 받기만 한다 — 기대값은 명세에서만 읽는다.
    slackMm = 문단 위 간격 + (docx 만) 줄 간격이 100% 를 넘는 만큼 — Word 는 늘어난 줄 높이를 글 위에 둔다(한글은 아래)."""
    m = meta if isinstance(meta, dict) else {}
    page = m.get("page") if isinstance(m.get("page"), dict) else None
    if page is None or _num(page.get("widthMm")) <= 0 or _num(page.get("heightMm")) <= 0:
        return None
    mar = page.get("marginsMm") if isinstance(page.get("marginsMm"), dict) else {}
    body = m.get("body") if isinstance(m.get("body"), dict) else {}
    f = body.get("format") if isinstance(body.get("format"), dict) else None
    f = ({k: f[k] for k in DOCX_FORMAT_KEYS if k in f} if fmt == "docx" else dict(f)) if f else None
    top = _num(mar.get("t"), None)  # 위 여백 t = 종이 끝에서 본문까지(머리말 몫을 이미 품은 값 — style_page 모듈 설명: 두 형식이 같은 뜻)
    slack = _num((f or {}).get("spaceBeforePt")) / PT_MM
    if fmt == "docx" and f:
        slack += max(_num(f.get("lineSpacingPct"), 100.0) - 100.0, 0.0) / 100 * _num(f.get("sizePt")) * LINE_NATURAL / PT_MM
    return {"widthMm": _num(page["widthMm"]), "heightMm": _num(page["heightMm"]), "leftMm": _num(mar.get("l")) + _num(mar.get("gutter")), "topMm": top, "slackMm": round(slack, 2),
            "sizeTolMm": PAGE_TOL_HWPX if fmt == "hwpx" else PAGE_TOL, "sample": page_sample(), "format": f}


def check_page(exp, measure, index=None) -> list[dict]:
    """문서 서식의 기대값(expect_page) × 잰 값(measure_pdf) → 검사 목록(PAGE_CHECKS 차례 + 못 재는 것 UNSUPPORTED_PAGE — render 는 run 이 붙인다).
    pageSize = 첫 쪽의 크기(±PAGE_TOL mm) · marginLeft·marginTop = **견본 첫 줄**(첫 쪽의 맨 위 글 줄)의 왼끝·위끝과 본문 상자(±MARGIN_TOL mm — 위끝은 slackMm 만큼 더 내려와도 통과) ·
    fontSize·fontFace = 그 줄의 글자와 바탕 글 모양. 못 재는 것은 unknown: 견본 줄이 없음 · 첫 줄이 견본 글이 아님 · 바탕 글 모양이 없음 · 가운데·오른쪽 정렬(왼끝) · 본문 위끝을 모름."""
    T = {k: _tally(k) for k in (*PAGE_CHECKS, "bold", "color")}
    pages = measure.get("pages") or []
    page = pages[0] if pages else None
    f = exp.get("format") if isinstance(exp.get("format"), dict) else None

    def unknown(keys, why):
        for k in keys:
            _put(T[k], "unknown", "견본 첫 줄", "", why, show=True)
    if page is None:
        unknown(PAGE_CHECKS, "PDF 에 쪽이 없음")
    else:
        w, h = page["w"] / PT_MM, page["h"] / PT_MM
        tol = _num(exp.get("sizeTolMm"), PAGE_TOL)
        ok = abs(w - exp["widthMm"]) <= tol and abs(h - exp["heightMm"]) <= tol
        _put(T["pageSize"], "pass" if ok else "fail", "쪽 크기", f"{exp['widthMm']:.1f}×{exp['heightMm']:.1f}mm", f"{w:.1f}×{h:.1f}mm")
        lines = page.get("lines") or []
        tops = [i for i, ln in enumerate(lines) if (ln.get("text") or "").strip() and ln.get("chars")]
        li = min(tops, key=lambda i: (lines[i]["bbox"][1], lines[i]["bbox"][0]), default=None)
        row = [(lj, pc) for lj, _, pc in pdf_style.visual_line(page, li)] if li is not None else []
        ink = [(lj, pc) for lj, pc in row if not pc[0].isspace()]
        want_key = key_text(exp.get("sample") or "")
        got_key = "".join(key_text(pc[0]) for _, pc in ink)
        if not ink:
            unknown(PAGE_CHECKS[1:], "견본 줄이 PDF 에 없음")
        elif want_key and not (got_key.startswith(want_key) or want_key.startswith(got_key)):
            unknown(PAGE_CHECKS[1:], f"첫 줄이 견본 글이 아님 — 「{''.join(pc[0] for _, pc in ink)[:30]}」")
        else:
            if f is not None and f.get("align") in ("center", "right", "distribute"):
                _put(T["marginLeft"], "unknown", "견본 첫 줄", "", "가운데·오른쪽 정렬은 왼끝을 못 잼", show=True)
            else:  # 바탕 글 모양이 없는 문서 서식(본문 글이 모두 표 안인 문서)의 견본은 평범한 문단 — 왼쪽 정렬 · 들여쓰기 없음: 왼끝 = 본문 왼끝
                want = exp["leftMm"] + _num((f or {}).get("indentLeftMm")) + max(_num((f or {}).get("firstLineMm")), 0.0)
                got = min(pc[1] for _, pc in ink) / PT_MM
                _put(T["marginLeft"], "pass" if abs(got - want) <= MARGIN_TOL else "fail", "견본 첫 줄 왼끝", f"{want:.1f}mm", f"{got:.1f}mm")
            if exp.get("topMm") is None:
                _put(T["marginTop"], "unknown", "견본 첫 줄 위끝", "", "본문 위끝을 모름(운반 문서의 쪽 설정을 읽지 못함)", show=True)
            else:
                want, slack, got = exp["topMm"], _num(exp.get("slackMm")), min(pc[2] for _, pc in ink) / PT_MM
                ok = want - MARGIN_TOL <= got <= want + slack + MARGIN_TOL
                _put(T["marginTop"], "pass" if ok else "fail", "견본 첫 줄 위끝", f"{want:.1f}mm" + (f"(+{slack:.1f}mm 까지)" if slack >= 0.05 else ""), f"{got:.1f}mm")
            if f is not None:  # 바탕 글 모양이 없는 문서 서식은 글 모양을 견주지 않는다(아래에서 「재지 못함」 으로 — 못 잰 것을 모름으로 세어 「확인 필요」 가 되지 않게)
                type3 = page.get("type3") or ()
                pairs = [(pc[0], f, pc, lines[lj]["spans"][pc[5]], lines[lj]["spans"][pc[5]][0] in type3) for lj, pc in ink if key_text(pc[0])]
                if pairs:
                    compare_chars(pairs, "견본 첫 줄", T, index)
                else:
                    unknown(("fontSize", "fontFace"), "견본 줄에 글자·숫자가 없음")
    notes = {"fontFace": _face_note(T["fontFace"]), "marginTop": "견본 첫 줄의 자리 — 줄 간격·문단 위 간격만큼의 폭을 둠" if _num(exp.get("slackMm")) >= 0.05 else ""}
    for k in PAGE_CHECKS:
        _done(T[k], notes.get(k, ""), "잴 것이 없음", strict=k == "fontFace" and bool(T[k].get("substituted")))
    bare = lambda k: f is None and k in ("fontSize", "fontFace") and not (T[k]["pass"] or T[k]["fail"] or T[k]["unknown"])  # noqa: E731
    return [unsupported(k, "바탕 글 모양이 없는 문서 서식 — 견줄 글 모양이 없음") if bare(k) else T[k] for k in PAGE_CHECKS] + [unsupported(k, note) for k, note in UNSUPPORTED_PAGE]


# ---- 표지 서식 견줌(cover-v1 — spec_서식복사 ② §14: 두 형식 같다) -------------------------------------------------------

def cover_parts(carrier, meta) -> list[dict]:
    """표지 서식의 부분들 — 보기(`style_cover.view(carrier, meta)["parts"]`: 운반 문서에서 읽은 것)가 되면 그것, 아니면(모듈 없음 · 못 읽음 · 운반 문서를 안 줌) meta.parts."""
    own = [p for p in (meta.get("parts") if isinstance(meta, dict) else None) or [] if isinstance(p, dict)]
    if not carrier:
        return own
    try:
        from app import style_cover
        got = style_cover.view(carrier, meta).get("parts")
        return [p for p in got if isinstance(p, dict)] if isinstance(got, list) and got else own
    except Exception as e:  # noqa: BLE001 — 표지 모듈이 없거나 보기를 못 지음: meta 의 부분으로 견준다
        log.info("표지 서식의 보기를 읽지 못해 meta.parts 로 견줌: %r", e)
        return own


def expect_cover(meta, fmt="hwpx", parts=None, own=None) -> dict | None:
    """표지 서식의 기대값(명세 = meta.page · 부분들) → {"page": {"widthMm", "heightMm", "sizeTolMm"} | None(쪽 설정을 모름), "leftMm": 쪽 왼 여백, "tables": 표 부분 수,
    "items": [글 부분마다 `check_text` 가 받는 item — {key, id, text: 견본 글, format, runs: None, auto: False}]} | None(부분이 하나도 없음).
    parts = 부분 목록(없으면 meta.parts — `cover_parts`) · own = 운반 문서가 스스로 적은 쪽 설정(docx — 왼 여백만 읽는다). fmt="docx" 면 서식은 docx 로 옮기는 값만(`_docx_format`).
    글 부분의 견본 글(sample)과 서식 요약(format)이 운반 문서에 쓴 그 값이다(`style_cover.carrier` 의 info.parts — spec ② §16)."""
    m = meta if isinstance(meta, dict) else {}
    parts = [p for p in (m.get("parts") if parts is None else parts) or [] if isinstance(p, dict)]
    if not parts:
        return None
    page = m.get("page") if isinstance(m.get("page"), dict) else None
    known = page is not None and _num(page.get("widthMm")) > 0 and _num(page.get("heightMm")) > 0
    mar = (own or page or {}).get("marginsMm") if isinstance((own or page or {}).get("marginsMm"), dict) else {}
    items = []
    for n, p in enumerate(parts, 1):
        if p.get("type") != "text":
            continue
        f = p.get("format") if isinstance(p.get("format"), dict) else {}
        items.append({"key": str(p.get("key") or f"p{n}"), "id": f"c{n}", "text": str(p.get("sample") or ""), "format": _docx_format(f) if fmt == "docx" else dict(f), "runs": None, "auto": False})
    return {"page": {"widthMm": _num(page["widthMm"]), "heightMm": _num(page["heightMm"]), "sizeTolMm": PAGE_TOL_HWPX if fmt == "hwpx" else PAGE_TOL} if known else None,
            "leftMm": _num(mar.get("l")) + _num(mar.get("gutter")), "tables": sum(1 for p in parts if p.get("type") == "table"), "items": items}


def check_cover(exp, measure, index=None) -> list[dict]:
    """표지 서식의 기대값(expect_cover) × 잰 값(measure_pdf) → 검사 목록(COVER_CHECKS 차례 + 못 재는 것 — render 는 run 이 붙인다).
    pageSize = 첫 쪽의 크기(page-v1 과 같은 오차 — 쪽 설정을 모르면 unknown) · text·fontSize·bold·fontFace = **글 부분마다** 글 서식과 같은 견줌(`check_text` — 견본 줄을 PDF 에서 찾아 그 글자들과).
    글 부분이 하나도 없는 표지(표 하나뿐인 양식의 표지)는 글 검사가 「재지 못함」 이다. 표 부분은 늘 「견주지 않음」(unsupported) — 통과로 세지 않는다. 자리·정렬·간격·색도 견주지 않는다."""
    size = _tally("pageSize")
    pages = measure.get("pages") or []
    want = exp.get("page") if isinstance(exp.get("page"), dict) else None
    if not pages:
        _put(size, "unknown", "쪽 크기", "", "PDF 에 쪽이 없음", show=True)
    elif want is None:
        _put(size, "unknown", "쪽 크기", "", "표지 서식에 쪽 설정이 없음", show=True)
    else:
        w, h, tol = pages[0]["w"] / PT_MM, pages[0]["h"] / PT_MM, _num(want.get("sizeTolMm"), PAGE_TOL)
        ok = abs(w - want["widthMm"]) <= tol and abs(h - want["heightMm"]) <= tol
        _put(size, "pass" if ok else "fail", "쪽 크기", f"{want['widthMm']:.1f}×{want['heightMm']:.1f}mm", f"{w:.1f}×{h:.1f}mm")
    out = [_done(size)]
    items = exp.get("items") or []
    if items:
        by = {c["what"]: c for c in check_text({"leftMm": _num(exp.get("leftMm")), "items": items, "metaItems": None}, measure, index)}
        out += [by[k] for k in COVER_CHECKS[1:]]
    else:
        out += [unsupported(k, "표지에 글 부분이 없음 — 견줄 글 모양이 없음") for k in COVER_CHECKS[1:]]
    out += [unsupported(k, note) for k, note in UNSUPPORTED_COVER]
    if exp.get("tables"):
        out.append(unsupported(UNSUPPORTED_COVER_TABLE[0], f"{UNSUPPORTED_COVER_TABLE[1]}(표 {exp['tables']}개)"))
    return out


# ---- docx(Word) 쪽 기대값 · 견줌 — 명세에서(spec_서식복사 ② §7) ------------------------------------------------------------

def _docx_format(fmt) -> dict:
    """서식 요약 사전에서 docx 로 옮기는 값만(② §4 — `style_docx._format` 과 같은 키) — 윗/아래첨자·언어별 글꼴은 docx 운반 문서에 없으므로 기대하지 않는다."""
    f = fmt if isinstance(fmt, dict) else {}
    return {k: f[k] for k in DOCX_FORMAT_KEYS if k in f}


def expect_table_spec(spec) -> dict | None:
    """표 명세(`style_carrier.view(carrier, meta)["spec"]` — 칸 글 포함: docx 운반 문서를 지은 그 명세) → `check_table` 이 받는 기대값(expect_table 과 같은 꼴) | None(칸 없음).
    칸의 제 폭(widthPt)은 0 = 격자의 열 폭을 쓴다(Word 는 칸을 격자대로 그린다 — 한글의 「칸 폭 쌓기」 가 아니다) · 행 높이는 명세에 없어 어림값(ROW_NOMINAL) ·
    열 폭이 명세에 없으면 0(표 폭은 unknown — 열 경계는 `check_table_docx` 가 잰 선에서 센다)."""
    cells = spec.get("cells") if isinstance(spec, dict) else None
    if not isinstance(cells, list) or not cells:
        return None
    rows, cols = int(spec.get("rows") or 0), int(spec.get("cols") or 0)
    if rows < 1 or cols < 1:
        return None
    widths = spec.get("widthsMm")
    known = isinstance(widths, list) and len(widths) == cols and all(_num(w) > 0 for w in widths)
    out = []
    for c in cells:
        text, edges = str(c.get("text") or ""), c.get("edges") if isinstance(c.get("edges"), dict) else {}
        out.append({"row": int(c["row"]), "col": int(c["col"]), "rowSpan": int(c.get("rowSpan") or 1), "colSpan": int(c.get("colSpan") or 1), "text": text,
                    "fill": c.get("fill") if isinstance(c.get("fill"), str) else None, "widthPt": 0,
                    "edges": {k: v if isinstance(v, dict) and str(v.get("type") or "NONE").upper() != "NONE" else None for k, v in edges.items()},
                    "chars": pdf_style._web_chars({"text": text, "format": _docx_format(c.get("format"))}), "auto": False, "nested": False, "zoned": False})
    return {"table": None, "rows": rows, "cols": cols, "widthsPt": [float(w) * PT_MM for w in widths] if known else [0.0] * cols, "heightsPt": [ROW_NOMINAL] * rows, "cells": out}


def expect_text_items(items, left_mm=20.0) -> dict | None:
    """글 서식의 명세(meta.items — 차례대로 견본 문단 하나씩) → `check_text` 가 받는 기대값(expect_text 와 같은 꼴) | None(항목 없음). left_mm = docx 운반 문서의 쪽 왼 여백.
    견본 줄 = item.sample(레터 + 견본 글 — 운반 문서에 쓴 그 글) · 서식 = item.format 가운데 docx 로 옮기는 값. 내어쓰기(첫 줄 < 0)도 한글과 같은 뜻으로 옮겨져 있다
    (`style_docx._ppr`: Word 의 left 에 그 폭을 더함 → 첫 줄은 왼쪽 여백 자리) — 왼끝의 기대값은 `check_text` 의 식 그대로."""
    items = [i for i in items or [] if isinstance(i, dict)] if isinstance(items, list) else []
    if not items:
        return None
    out = []
    for n, it in enumerate(items, 1):
        mode = it["marker"].get("mode") if isinstance(it.get("marker"), dict) else None
        out.append({"key": it.get("key") or f"i{n}", "id": f"d{n}", "text": str(it.get("sample") or ""), "format": _docx_format(it.get("format")), "runs": None, "auto": mode == "auto"})
    return {"leftMm": float(left_mm), "items": out, "metaItems": len(items)}


def measured_cols(exp, page) -> list | None:
    """잰 세로선·채움 사각형의 x 를 묶은 열 경계(왼 → 오른, cols + 1 개) | None(수가 안 맞음 — 세로선이 없는 표 · 뜻밖의 선: 지어내지 않는다)."""
    xs = _clusters([(v, True) for r in page.get("rects") or [] for v in (r["x0"], r["x1"])] + [(s["x0"], False) for s in page.get("segs") or [] if s["dir"] == "v"], EDGE_TOL)
    return xs if len(xs) == exp["cols"] + 1 else None


def word_page(page, exp) -> dict:
    """Word 가 PDF 에 그리는 버릇을 걷어 낸 쪽(실측 2026-11-14 — 연구개발계획서 양식의 표를 docx 로 지어 출력: 가로 경계가 7 이 아니라 12 로 세어져 칸 자리를 못 잡았다):
    ⓐ 칸 음영을 칸 크기로 칠한 뒤 **글 줄마다 같은 색 사각형을 한 번 더** 칠한다 — 다른 채움 사각형 안에 든 같은 색 사각형은 뺀다(그 변이 행 경계로 세어진다)
    ⓑ 선이 만나는 자리의 조각(가로·세로 모두 4pt 미만 사각형 — 굵은 바깥선은 행 경계마다 1.1×2.6pt 검은 조각을 더 그린다: 그 아랫변이 2pt 넘게 떨어져 경계 하나로 더 세어졌다)을 뺀다 ⓒ 괘선 옆에 **음영 색의 가는 띠**를 칠한다(가는 채움 사각형이라 선으로 읽힌다) — 색이 음영 색이고
    기대한 괘선 색(명세의 선 색 · 검정)이 아닌 선은 뺀다(선 없는 음영 칸의 변에 「뜻밖의 선」 이 되지 않게)."""
    rects = [r for r in page.get("rects") or [] if max(r["x1"] - r["x0"], r["y1"] - r["y0"]) >= JOINT_MAX]
    inside = lambda r, q: q is not r and _near(r["fill"], q["fill"]) and q["x0"] - 0.5 <= r["x0"] and r["x1"] <= q["x1"] + 0.5 and q["y0"] - 0.5 <= r["y0"] and r["y1"] <= q["y1"] + 0.5 and (  # noqa: E731
        (q["x1"] - q["x0"]) * (q["y1"] - q["y0"]) > (r["x1"] - r["x0"]) * (r["y1"] - r["y0"]) + 0.01)
    rects = [r for r in rects if not any(inside(r, q) for q in rects)]
    lines = [(0.0, 0.0, 0.0)] + [_channels(e["color"]) for c in exp.get("cells") or [] for e in (c.get("edges") or {}).values()
                                 if isinstance(e, dict) and isinstance(e.get("color"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", e["color"])]
    fills = [r["fill"] for r in rects if r.get("fill") is not None]
    band = lambda s: s.get("color") is not None and any(_near(s["color"], f) for f in fills) and not any(_near(s["color"], c) for c in lines)  # noqa: E731
    return {**page, "rects": rects, "segs": [s for s in page.get("segs") or [] if not band(s)]}


def check_table_docx(exp, measure, index=None) -> list[dict]:
    """표 명세의 기대값(expect_table_spec) × Word PDF 에서 잰 값 → 검사 목록(check_table 과 같은 차례 — `lineWidth` 는 「재지 못함」 으로).
    한글에 맞춘 보정을 쓰지 않는다: 칸의 x = **잰 열 경계**(measured_cols — 세로선·채움), 못 세면 명세의 열 폭(표 폭이 맞을 때만), 그것도 아니면 자리에 기대는 검사 전체가 unknown
    (글은 PDF 어디에든 있는지만). 표 폭 = 잰 폭과 명세의 열 폭 합(±WIDTH_TOL_DOCX — 명세에 열 폭이 없으면 unknown). 견줌 자체는 `check_table` 그대로."""
    measure = {**measure, "pages": [word_page(p, exp) for p in measure.get("pages") or []]}  # Word 의 그림 버릇(글 줄마다 덧칠한 음영 · 선 옆 음영 띠 · 교차점)을 걷어 낸 뒤 견준다
    pages, count = measure.get("pages") or [], measure.get("count") or 0
    page = next((p for p in pages if p.get("segs") or p.get("rects") or p.get("lines")), pages[0] if pages else {})
    plain = {**page, "segs": plain_segs(page)}
    total, why = sum(exp["widthsPt"]), ""
    X = measured_cols(exp, plain) if count == 1 else None
    fr = table_frame(exp, plain)
    got = X[-1] - X[0] if X else fr["widthPt"]
    width = _tally("width")
    if got is None or total <= 0:
        _put(width, "unknown", "표 폭", f"{total:.1f}pt" if total > 0 else "명세에 열 폭 없음", "못 잼" if got is None else f"{got:.1f}pt", show=True)
    else:
        _put(width, "pass" if abs(got / total - 1) <= WIDTH_TOL_DOCX else "fail", "표 폭", f"{total:.1f}pt", f"{got:.1f}pt")
    if X:  # 잰 열 경계로 칸 자리를 잡는다
        use, m = {**exp, "widthsPt": [b - a for a, b in zip(X, X[1:])]}, measure
    elif total > 0 and fr["widthPt"] and abs(fr["widthPt"] / total - 1) <= WIDTH_TOL:  # 열 경계는 못 셌지만 표 폭이 명세와 같다 — 명세의 열 폭으로
        use, m = exp, measure
    else:  # 칸 자리를 정할 수 없다 — 선·채움을 뺀 잰 값으로 견줘, 자리에 기대는 검사를 unknown 으로 둔다(지어낸 자리로 fail 을 내지 않는다)
        use, m = {**exp, "widthsPt": [1.0] * exp["cols"]}, {**measure, "pages": [{**p, "segs": [], "rects": []} for p in pages]}
        why = "열 경계를 PDF 의 선에서 세지 못했고 표 폭도 명세와 달라 칸 자리를 견주지 않음" if count == 1 else f"{count}쪽으로 출력되어 칸 자리를 견주지 않음"
    out = []
    for c in check_table(use, m, index):
        if c["what"] == "width":
            c = _done(width)
        elif c["what"] == "lineWidth":
            c = unsupported(*UNSUPPORTED_LINE_WIDTH)
        elif why and c["status"] == "unknown" and c["what"] not in ("pages", "text"):
            c = {**c, "note": why}
        out.append(c)
    return out


def docx_page(docx: bytes) -> dict | None:
    """docx 운반 문서가 스스로 적은 쪽 설정(본문 상자) {widthMm, heightMm, marginsMm{l,r,t,b}} | None(못 읽음) — `DocxDoc.blocks()` 의 page."""
    try:
        from app.docx_doc import DocxDoc
        return next((b["page"] for b in DocxDoc(docx).blocks() if b.get("page")), None)
    except Exception as e:  # noqa: BLE001 — 깨진 docx · 구역 설정 없음
        log.info("docx 운반 문서의 쪽 설정을 읽지 못함: %r", e)
        return None


def expect_docx(docx: bytes, carrier, meta: dict, profile: str):
    """docx 쪽 기대값 — **명세에서**(spec_서식복사 ② §7): 표 = hwpx 운반 문서의 표 명세(`style_carrier.view(carrier, meta)["spec"]`) · 글 = meta.items · 문서 서식 = meta.page·body.
    → 기대값 사전 | None(표 명세·항목·쪽 설정이 없음). 운반 문서를 못 읽으면 ValueError."""
    own = docx_page(docx)
    if profile == "page-v1":
        return expect_page(meta, "docx", own)
    if profile == "cover-v1":  # 표지 서식(② §14) — 글 부분의 견본 글·서식 요약(docx 로 옮기는 값만) · 쪽 크기. 부분은 hwpx 운반 문서의 보기에서(docx 를 지은 그 명세)
        return expect_cover(meta, "docx", cover_parts(carrier, meta), own)
    if profile == "text-v1":
        left = (own or {}).get("marginsMm", {}).get("l")
        return expect_text_items(meta.get("items"), _num(left, 20.0))
    from app import style_carrier
    return expect_table_spec(style_carrier.view(carrier or b"", meta).get("spec"))


def build_docx(meta: dict, carrier: bytes):
    """docx 운반 문서를 그 자리에서 짓는다(옛 템플릿 — spec_서식복사 ② §4) → (docx 바이트, losses) | None(`app.style_docx` 가 없음 · 못 지음)."""
    try:
        from app import style_docx
    except ImportError:
        return None
    try:
        data, losses = style_docx.build(meta, carrier)
    except Exception as e:  # noqa: BLE001 — ValueError(못 지음)와 그 밖의 오류 모두: docx 없이 둔다
        log.info("docx 운반 문서를 짓지 못함 %s: %r", meta.get("id"), e)
        return None
    return (bytes(data), [str(x) for x in losses or [] if x]) if data else None


# ---- 실행 ---------------------------------------------------------------------------------------------------------

def _cached_pdf(carrier, fmt="hwpx"):
    """이 운반 문서의 PDF 캐시 파일 — pdf_render.export_pdf 와 같은 이름(출력용 사본 바이트의 해시). fmt = 운반 문서의 형식(docx 는 바깥을 뗀 사본의 해시)."""
    return pdf_render.render_dir() / f"{pdf_render.sha(pdf_render.render_copy(carrier) if fmt == 'hwpx' else pdf_render.render_copy(carrier, fmt))}.pdf"


def _blank(meta, status="none", note="", fmt="hwpx"):
    """빈 기록(spec ② §6 의 꼴) — 검사 없이. docx 쪽 기록(`verifyDocx`)은 같은 꼴 + `format: "docx"` · renderer Word."""
    return {"status": status, "at": time.time(), "revision": meta.get("revision"), "subjectHash": "", "profile": PROFILES.get(meta.get("kind"), "table-v1"),
            **({"format": fmt} if fmt != "hwpx" else {}), "renderer": {"name": RENDERERS.get(fmt, fmt)}, "pages": 0, "checks": [],
            "coverage": {"pass": 0, "fail": 0, "unknown": 0, "unsupported": 0}, "note": note}


def run(carrier: bytes, meta: dict, force: bool = False) -> tuple[dict, dict]:
    """운반 문서 한 번 검증 → (기록(spec ② §6), 파일 {"proof.png", "proof.pdf"}). 예외를 내지 않는다 — 한글이 없으면 status "none", 출력·읽기 실패는 "fail" + note.
    force = 이 운반 문서의 PDF 캐시를 지우고 다시 출력(글꼴을 깔았거나 한글을 바꾼 뒤의 「다시 검증」)."""
    meta = meta if isinstance(meta, dict) else {}
    rec, files = _blank(meta), {}
    render = _tally("render")

    def failed(note):
        _put(render, "fail", "출력", "PDF 출력", note)
        checks = [_done(render), *rec["checks"]]
        return {**rec, "status": "fail", "checks": checks, "coverage": summarize(checks)[1], "note": note}, files
    try:
        rec["subjectHash"] = subject_hash({**meta, "carrierSha256": meta.get("carrierSha256") or hashlib.sha256(carrier or b"").hexdigest()})
        if not pdf_render.available("hwpx"):
            return {**rec, "note": "PDF 출력 없음 — 이 PC 에 한글이 없어 견본을 출력하지 못했습니다"}, files
        try:
            cdoc = HwpxDoc(carrier)
            exp = (expect_page(meta) if rec["profile"] == "page-v1" else expect_text(cdoc, meta) if rec["profile"] == "text-v1"
                   else expect_cover(meta, "hwpx", cover_parts(carrier, meta)) if rec["profile"] == "cover-v1" else expect_table(cdoc))
        except Exception as e:  # 깨진 zip·XML · zip_guard
            return failed(f"운반 문서를 읽지 못했습니다: {e}"[:300])
        if exp is None:
            return failed({"text-v1": "운반 문서에 견본 문단이 없습니다", "page-v1": "문서 서식에 쪽 설정(meta.page)이 없습니다",
                           "cover-v1": "표지 서식에 부분(meta.parts)이 없습니다"}.get(rec["profile"], "운반 문서에 표가 없습니다"))
        try:
            if force:
                old = _cached_pdf(carrier)
                with pdf_render._once(old):
                    old.unlink(missing_ok=True)
            try:
                pdf = pdf_render.export_pdf(carrier, limit=LIMIT)
            except PermissionError:  # 한글이 막 쓴 PDF 를 아직 쥐고 있어 캐시로 옮기지 못함(WinError 32 — 실측 1회) — 한 번 더
                time.sleep(0.5)
                pdf = pdf_render.export_pdf(carrier, limit=LIMIT)
            files["proof.pdf"] = pdf.read_bytes()
            measure = measure_pdf(pdf)
        except Exception as e:  # 시간 초과(한글 창)·한글 실패·PDF 읽기 실패
            return failed(f"한글 PDF 출력 실패: {e}"[:300])
        try:
            png = proof_png(pdf, full=meta.get("kind") in FULL_PROOF)  # 쪽 설정·표지 = 첫 쪽 전체(② §13)
            if png:
                files["proof.png"] = png
        except Exception as e:
            log.warning("견본 그림을 못 만듦: %s", e)
        rec["pages"] = measure["count"]
        _put(render, "pass")
        index = fonts.font_index()
        check = {"page-v1": check_page, "text-v1": check_text, "cover-v1": check_cover}.get(rec["profile"], check_table)
        checks = [_done(render), *check(exp, measure, index)]
        status, cov, notes = summarize(checks, measure["count"])
        return {**rec, "status": status, "checks": checks, "coverage": cov, "note": " · ".join(notes)}, files
    except Exception as e:  # 견줌 코드의 예상 밖 오류 — 검증이 서버를 죽이지 않게
        log.exception("서식 검증 실패")
        return failed(f"검증 중 오류: {type(e).__name__}: {e}"[:300])


def run_docx(docx: bytes, carrier, meta: dict, force: bool = False) -> tuple[dict, dict]:
    """docx 운반 문서 한 번 검증(Word — spec_서식복사 ② §7) → (기록(`verifyDocx` — run 과 같은 꼴 + format "docx" · renderer Word), 파일 {"proof_docx.png", "proof_docx.pdf"}).
    carrier = 그 템플릿의 hwpx 운반 문서(표의 기대값 = 그 표 명세). 예외를 내지 않는다 — Word 가 없으면 status "none", 출력·읽기 실패는 "fail" + note.
    기대값은 명세에서(`expect_docx`), 견줌은 표 `check_table_docx` · 글 `check_text` · 문서 서식 `check_page`."""
    meta = meta if isinstance(meta, dict) else {}
    rec, files = _blank(meta, fmt="docx"), {}
    render = _tally("render")
    png_name, pdf_name = PROOFS["docx"]

    def failed(note):
        _put(render, "fail", "출력", "PDF 출력", note)
        checks = [_done(render), *rec["checks"]]
        return {**rec, "status": "fail", "checks": checks, "coverage": summarize(checks)[1], "note": note}, files
    try:
        rec["subjectHash"] = subject_hash({**meta, "carrierSha256": meta.get("carrierSha256") or hashlib.sha256(carrier or b"").hexdigest(),
                                           "docx": {"sha256": hashlib.sha256(docx or b"").hexdigest()}}, "docx")
        if not pdf_render.available("docx"):
            return {**rec, "note": "PDF 출력 없음 — 이 PC 에 Word 가 없어 견본을 출력하지 못했습니다"}, files
        try:
            exp = expect_docx(docx, carrier, meta, rec["profile"])
        except Exception as e:  # 깨진 운반 문서 · 틀린 명세
            return failed(f"docx 서식의 기대값(명세)을 읽지 못했습니다: {e}"[:300])
        if exp is None:
            return failed({"text-v1": "글 서식에 항목(meta.items)이 없습니다", "page-v1": "문서 서식에 쪽 설정(meta.page)이 없습니다",
                           "cover-v1": "표지 서식에 부분(meta.parts)이 없습니다"}.get(rec["profile"], "운반 문서에 표 명세가 없습니다"))
        try:
            if force:
                old = _cached_pdf(docx, "docx")
                with pdf_render._once(old):
                    old.unlink(missing_ok=True)
            try:
                pdf = pdf_render.export_pdf(docx, limit=LIMIT, fmt="docx")
            except PermissionError:  # 막 쓴 PDF 를 아직 쥐고 있어 캐시로 옮기지 못함 — 한 번 더(run 과 같다)
                time.sleep(0.5)
                pdf = pdf_render.export_pdf(docx, limit=LIMIT, fmt="docx")
            files[pdf_name] = pdf.read_bytes()
            measure = measure_pdf(pdf)
        except Exception as e:  # 시간 초과(Word 대화상자)·Word 실패·PDF 읽기 실패 · 읽을 수 없는 docx(render_copy)
            return failed(f"Word PDF 출력 실패: {e}"[:300])
        try:
            png = proof_png(pdf, full=meta.get("kind") in FULL_PROOF)  # 쪽 설정·표지 = 첫 쪽 전체(② §13)
            if png:
                files[png_name] = png
        except Exception as e:
            log.warning("견본 그림을 못 만듦(docx): %s", e)
        rec["pages"] = measure["count"]
        _put(render, "pass")
        index = fonts.font_index()
        check = {"page-v1": check_page, "text-v1": check_text, "cover-v1": check_cover}.get(rec["profile"], check_table_docx)
        checks = [_done(render), *check(exp, measure, index)]
        status, cov, notes = summarize(checks, measure["count"])
        return {**rec, "status": status, "checks": checks, "coverage": cov, "note": " · ".join(notes)}, files
    except Exception as e:  # 견줌 코드의 예상 밖 오류 — 검증이 서버를 죽이지 않게
        log.exception("서식 검증 실패(docx)")
        return failed(f"검증 중 오류: {type(e).__name__}: {e}"[:300])


_JOBS, _JOBS_LOCK = {}, threading.Lock()   # {템플릿 id: {"revision", "at", "force", "left": 아직 안 끝난 형식들}} — 도는 검증(메모리)


def running(sid: str) -> bool:
    with _JOBS_LOCK:
        return sid in _JOBS


def pending(sid: str) -> tuple:
    """도는 검증에서 **아직 안 끝난 형식**들(차례대로 — ("hwpx", "docx") · ("docx",) · ()) — 안 돌고 있으면 (). 화면은 형식마다 「검증 중」 을 이것으로 보인다."""
    with _JOBS_LOCK:
        j = _JOBS.get(sid)
        return tuple(j.get("left") or ()) if j else ()


def job(sid: str) -> dict | None:
    """도는 검증의 기록 {"status": "running", "revision", "at"} | None."""
    with _JOBS_LOCK:
        j = _JOBS.get(sid)
        return {"status": "running", "revision": j["revision"], "at": j["at"]} if j else None


def _meta_of(got):
    """style_lib.get 의 답 → meta(사양 §2 는 {meta, dir}, 약속한 시그니처는 meta 그대로 — 둘 다 받는다)."""
    if isinstance(got, dict) and isinstance(got.get("meta"), dict) and "revision" not in got:
        return got["meta"]
    return got if isinstance(got, dict) else None


def _hold(lib, sid, rid, on=True):
    """시작 때의 revision 을 붙든다 / 놓는다(`style_lib.pin`·`unpin`) — 도는 동안 revision 이 여러 번 바뀌어도 그 revision 이 치워지지 않게(최근 5개만 남기는 정리가 건너뛴다).
    못 붙들어도(옛 저장소 · 오류) 검증은 돈다."""
    fn = getattr(lib, "pin" if on else "unpin", None)
    try:
        if fn is not None:
            fn(sid, rid)
    except Exception:
        log.exception("서식 revision 을 %s 못함: %s %s", "붙들지" if on else "놓지", sid, rid)


def start(sid: str, force: bool = False, formats=None) -> dict:
    """템플릿 sid 의 검증을 스레드로 건다 → {"status": "running", "revision": 시작 때의 revision}. 이미 돌고 있으면 그 기록 그대로(새로 걸지 않음).
    끝나면 **시작할 때의 revision** 에 기록·proof.png·proof.pdf 를 붙인다(style_lib.put_verify) — 그 revision 은 시작할 때 붙들어(`style_lib.pin`) 끝날 때까지 치워지지 않는다.
    formats = 검증할 형식(없으면 둘 다 — hwpx(한글) → docx(Word) 차례: spec_서식복사 ② §7). 아는 형식이 하나도 없으면 ValueError. 없는 id 는 LookupError."""
    from app import style_lib
    fmts = tuple(f for f in FORMATS if formats is None or f in formats)
    if not fmts:
        raise ValueError(f"formats 는 {'·'.join(FORMATS)} 가운데")
    with _JOBS_LOCK:
        j = _JOBS.get(sid)
        if j is not None:
            return {"status": "running", "revision": j["revision"]}
        meta = _meta_of(style_lib.get(sid))
        if meta is None:
            raise LookupError("없는 서식 템플릿입니다")
        rid = meta.get("revision")
        _JOBS[sid] = {"revision": rid, "at": time.time(), "force": bool(force), "left": fmts}
        _hold(style_lib, sid, rid)
    try:
        threading.Thread(target=_work, args=(sid, rid, meta, bool(force), fmts), daemon=True, name=f"style-verify-{sid}").start()
    except BaseException:  # 스레드를 못 띄움 — 도는 것으로 남기지 않는다
        _hold(style_lib, sid, rid, on=False)
        with _JOBS_LOCK:
            _JOBS.pop(sid, None)
        raise
    return {"status": "running", "revision": rid}


def _work_hwpx(style_lib, sid, rid, meta, force):
    """한글 쪽 한 번 — 기록을 `verify` 에 붙인다."""
    data = style_lib.carrier(sid, rid)
    if data is None:
        record, files = {**_blank(meta, "fail", "운반 문서가 없습니다"), "subjectHash": subject_hash(meta)}, {}
    else:
        record, files = run(data, meta, force=force)
    record["revision"] = rid
    style_lib.put_verify(sid, rid, record, files)


def _work_docx(style_lib, sid, rid, meta, force):
    """Word 쪽 한 번 — 기록을 `verifyDocx` 에 붙인다. docx 운반 문서가 그 revision 에 없으면 그 자리에서 지어 붙이고(`build_docx` → `style_lib.put_docx`),
    못 지으면 아무것도 안 붙인다(`verifyDocx` 는 null — docx 서식이 없다). docx 형식을 모르는 저장소(put_docx 없음)에서는 아무것도 안 한다."""
    if not hasattr(style_lib, "put_docx"):
        return
    docx, carrier = style_lib.carrier(sid, rid, fmt="docx"), style_lib.carrier(sid, rid)
    if docx is None:
        built = build_docx(meta, carrier) if carrier is not None else None
        if built is None or not style_lib.put_docx(sid, rid, built[0], built[1]):
            return
        docx = built[0]
    record, files = run_docx(docx, carrier, {**meta, "docx": {"sha256": hashlib.sha256(docx).hexdigest()}}, force=force)
    record["revision"] = rid
    style_lib.put_verify(sid, rid, record, files, fmt="docx")


def _work(sid, rid, meta, force, formats=("hwpx",)):
    from app import style_lib
    try:
        for fmt in formats:  # 한글 → Word 차례로(한 형식이 실패해도 다음 형식은 돈다)
            try:
                (_work_docx if fmt == "docx" else _work_hwpx)(style_lib, sid, rid, meta, force)
            except Exception:
                log.exception("서식 검증 작업 실패: %s %s %s", sid, rid, fmt)
            finally:
                with _JOBS_LOCK:
                    j = _JOBS.get(sid)
                    if j is not None:
                        j["left"] = tuple(f for f in j.get("left") or () if f != fmt)
    finally:
        _hold(style_lib, sid, rid, on=False)  # 기록을 붙인 뒤에 놓는다 — 그 사이 밀린 옛 revision 은 저장소가 그때 치운다
        with _JOBS_LOCK:
            _JOBS.pop(sid, None)
