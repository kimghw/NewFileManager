"""문서 서식(spec_서식복사 ② §5 · §10) — 서식 종류 `page`: **쪽 설정 + 본문 바탕 글 모양**. 추출(hwpx · docx · pdf) · hwpx 운반 문서 · 쪽 설정 읽기·바꾸기.

- `page` = `{widthMm, heightMm, landscape, marginsMm{l, r, t, b, header, footer, gutter}}` — 형식 중립(mm · 소수 둘째 자리). `widthMm`·`heightMm` = 보이는 방향의 값,
  `landscape` = 폭이 높이보다 큼(따로 적는 값이 아니라 두 값에서 나온다 — `clean` 이 맞춘다).
- **여백의 뜻(두 형식이 같은 쪽을 그리게 하나로 정했다 — 화면이 쪽을 그리는 규칙 `hwpx_layout.page`·`docx_layout.page` 와 같다)**:
  `t`·`b` = 종이 끝에서 **본문**까지 · `header`·`footer` = 그 가운데 머리말·꼬리말이 차지하는 높이(본문 쪽에 붙은 몫) · `l`·`r` = 종이 끝에서 본문까지(제본 여백 `gutter` 는 따로).
  - 한글(`hp:margin`): 본문 시작 = 위쪽 + 머리말(references/HWPX_포맷.md 「용지」) → `t` = top + header · `header` = header. 쓸 때 top = t − header.
  - Word(`w:pgMar`): top = 본문 시작 · header = 종이 끝에서 머리말까지 → `t` = top · `header` = top − header(음수면 0). 쓸 때 header = t − header(`style_docx.from_page`).
  - PDF: 글이 놓인 상자의 가장자리 = `t`·`b`·`l`·`r`, `header`·`footer`·`gutter` = 0(재지 못함).
- `body` = `{format: 서식 요약 사전(None 인 값은 뺌), count: 그 서식의 문단 수} | None` — 본문 최상위 문단(표 칸 안 · 빈 문단 · 캡션 제외) 가운데 서식 요약이 같은 것끼리 묶어 **글자 수가 가장 많은** 서식.
  2차(② §12·§15): 헤딩 노드의 문단은 세지 않고(`skip`) 상위 3개를 후보로 낸다(`bodies` — body 는 그 1위) · 쪽 설정은 첫 구역이 아니라 **본문 글이 가장 많은 구역**의 것(`section`).
- 하지 않는 것(v1 — spec ② §5): 머리말·꼬리말 내용 · 쪽 번호 · 단 · 구역마다 다른 설정 · 바탕 글 모양을 문서 전체에 입히기."""
import json
import statistics
from collections import Counter

from lxml import etree

from app.hwpx_doc import P, _p
from app.hwpx_format import LINESEG, SUMMARY_KEYS

HU_MM, TW_MM, PT_MM = 25.4 / 7200, 25.4 / 1440, 25.4 / 72  # HWPUNIT · twip · pt → mm
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SAMPLES = ["문서 서식 견본입니다", "가나다라마바사 ABC abc 0123", "본문 바탕 글 모양을 보이는 견본 줄입니다"]  # 견본 문단 글 3줄 — 첫 줄 = 검증이 자리를 재는 줄
SIDES, EXTRA = ("l", "r", "t", "b"), ("header", "footer", "gutter")  # 꼭 있어야 하는 여백 · 없으면 0 인 여백
SIZE_MIN, SIZE_MAX, MARGIN_MAX = 20, 2000, 300  # mm
PAPERS = (("A3", 297, 420), ("A4", 210, 297), ("A5", 148, 210), ("B4", 257, 364), ("B5", 182, 257), ("Letter", 215.9, 279.4), ("Legal", 215.9, 355.6))  # 세로 기준 mm
PAPER_TOL = 1.0  # 용지 이름을 붙이는 오차 mm(한글 A4 높이 84186 = 296.99mm · Word A4 = 210.01 × 297.01mm)
DIFF_HEAD = "구역마다 쪽 설정이 다릅니다"  # 그 알림의 머리 글 — `style_extract` 의 자기 점검(`sectionsDiffer`)이 losses 에서 이것으로 찾는다
DIFF_NOTE = DIFF_HEAD + " — 첫 구역 것"
BODIES_MAX, BODY_SAMPLE = 3, 60  # 바탕 글 후보 수 · 견본 글 길이(spec_서식복사 ② §12)
PDF_NOTES = ("여백은 글이 놓인 자리로 어림했습니다", "머리말·꼬리말 여백은 재지 못함")
PDF_FAR_SHARE = 0.35  # PDF 의 아래·오른쪽 「여백」 이 쪽 크기의 이 몫을 넘으면 글이 쪽을 다 채우지 않은 것 — 여백으로 읽지 않는다(of_pdf)
WORD = {"l": "왼쪽", "r": "오른쪽", "t": "위", "b": "아래", "header": "머리말", "footer": "꼬리말", "gutter": "제본"}


# ---- 꼴 · 요약 ------------------------------------------------------------------------------------------------------

def _num(v, what, lo, hi) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not lo <= v <= hi:
        raise ValueError(f"문서 서식의 {what} 값이 틀렸습니다({v!r} — {lo}~{hi}mm)")
    return round(float(v), 2)


def clean(page) -> dict:
    """꼴·범위 검사 → 고른 사전 `{widthMm, heightMm, landscape, marginsMm{l,r,t,b,header,footer,gutter}}`(mm 는 소수 둘째 자리). 틀리면 ValueError.
    폭·높이 20~2000mm · 여백 0~300mm(`header`·`footer`·`gutter` 는 없으면 0) · 좌우 여백(+ 제본)의 합 < 폭 · 위아래 여백의 합 < 높이 ·
    머리말 ≤ 위 여백 · 꼬리말 ≤ 아래 여백(위·아래 여백은 종이 끝에서 본문까지 — 머리말·꼬리말은 그 안의 몫이다: 모듈 설명).
    `landscape` 는 준 값이 아니라 폭 > 높이로 정한다(가로면 폭이 더 크다 — spec ② §5)."""
    if not isinstance(page, dict):
        raise ValueError("문서 서식에 쪽 설정이 없습니다")
    w, h = _num(page.get("widthMm"), "쪽 폭", SIZE_MIN, SIZE_MAX), _num(page.get("heightMm"), "쪽 높이", SIZE_MIN, SIZE_MAX)
    m = page.get("marginsMm")
    if not isinstance(m, dict):
        raise ValueError("문서 서식에 쪽 여백이 없습니다")
    mar = {k: _num(m.get(k), f"{WORD[k]} 여백", 0, MARGIN_MAX) for k in SIDES}
    mar.update({k: _num(m.get(k) if m.get(k) is not None else 0, f"{WORD[k]} 여백", 0, MARGIN_MAX) for k in EXTRA})
    if mar["l"] + mar["r"] + mar["gutter"] >= w:
        raise ValueError(f"문서 서식의 좌우 여백 합({mar['l'] + mar['r'] + mar['gutter']:g}mm)이 쪽 폭({w:g}mm)보다 작아야 합니다")
    if mar["t"] + mar["b"] >= h:
        raise ValueError(f"문서 서식의 위아래 여백 합({mar['t'] + mar['b']:g}mm)이 쪽 높이({h:g}mm)보다 작아야 합니다")
    for part, whole in (("header", "t"), ("footer", "b")):
        if mar[part] > mar[whole] + 0.011:  # 0.01mm 는 반올림 몫
            raise ValueError(f"문서 서식의 {WORD[part]} 여백({mar[part]:g}mm)이 {WORD[whole]} 여백({mar[whole]:g}mm)보다 큽니다 — {WORD[whole]} 여백은 종이 끝에서 본문까지입니다")
        mar[part] = min(mar[part], mar[whole])
    return {"widthMm": w, "heightMm": h, "landscape": w > h, "marginsMm": mar}


def _g(v) -> str:
    """mm·pt 값을 글로 — 소수 첫째 자리까지, 0 은 뗀다(30.0 → 「30」 · 19.99 → 「20」 · 12.5 → 「12.5」)."""
    return f"{round(float(v), 1):g}"


def paper_name(page) -> str:
    """용지 이름(A4·A3·B5·Letter … — 세로·가로 어느 쪽이든 ±1mm) · 모르면 「210×297mm」(보이는 방향의 폭×높이)."""
    w, h = sorted((page["widthMm"], page["heightMm"]))
    name = next((n for n, pw, ph in PAPERS if abs(w - pw) <= PAPER_TOL and abs(h - ph) <= PAPER_TOL), None)
    return name or f"{_g(page['widthMm'])}×{_g(page['heightMm'])}mm"


def summary(page, body=None) -> str:
    """한 줄 요약 — 「A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm · 본문 함초롬바탕 11pt」(용지 이름 + 방향 + 여백 + 바탕 글. body 가 없으면 「본문 …」 은 뺀다).
    위·아래 = 종이 끝에서 본문까지."""
    page = clean(page)
    m = page["marginsMm"]
    out = [f"{paper_name(page)} {'가로' if page['landscape'] else '세로'}", f"여백 왼 {_g(m['l'])}", f"오 {_g(m['r'])}", f"위 {_g(m['t'])}", f"아래 {_g(m['b'])}mm"]
    f = body.get("format") if isinstance(body, dict) and isinstance(body.get("format"), dict) else {}
    font = f["font"].strip() if isinstance(f.get("font"), str) else ""
    size = f"{_g(f['sizePt'])}pt" if isinstance(f.get("sizePt"), (int, float)) and not isinstance(f.get("sizePt"), bool) else ""
    if font or size:
        out.append(" ".join(x for x in ("본문", font, size) if x))
    return " · ".join(out)


def _chars(b) -> int:
    """바탕 글로 셀 문단 블록의 글자 수(빈칸 뺌) — 문단이 아니거나 캡션이면 0."""
    if b.get("type") != "paragraph" or b.get("captionOf"):
        return 0
    return len("".join((b.get("text") or "").split()))


def _body_groups(blocks, skip=()) -> list[dict]:
    """최상위 글 문단(캡션·빈 문단·`skip` 의 문단 id 제외)을 서식 요약(`SUMMARY_KEYS` 의 값 — None 은 뺌)이 같은 것끼리 묶은 것 — 글자 수 많은 차례(같으면 먼저 나온 것).
    묶음 = `{format, count, chars, sample}`(sample = 그 묶음 첫 문단의 글 `BODY_SAMPLE` 자)."""
    skip, groups = set(skip or ()), {}
    for b in blocks or []:
        n = _chars(b)
        if not n or b.get("id") in skip:
            continue
        fmt = {k: v for k, v in (b.get("format") or {}).items() if k in SUMMARY_KEYS and v is not None}
        text = " ".join((b.get("text") or "").split())
        g = groups.setdefault(json.dumps(fmt, sort_keys=True, ensure_ascii=False),
                              {"format": fmt, "count": 0, "chars": 0, "sample": text if len(text) <= BODY_SAMPLE else text[:BODY_SAMPLE - 1] + "…"})
        g["count"] += 1
        g["chars"] += n
    return sorted(groups.values(), key=lambda g: -g["chars"])  # 안정 정렬 — 같으면 먼저 나온 묶음


def bodies(blocks, skip=()) -> list[dict]:
    """바탕 글 후보 상위 `BODIES_MAX`(3)개(spec_서식복사 ② §12·§15·§16) → `[{"key": "b1"…, "format", "count", "chars", "sample"}]`(글자 수 많은 차례 · 글 문단이 없으면 []).
    blocks = `HwpxDoc.blocks()` · `DocxDoc.blocks()`(최상위만 본다 — 표 칸 안 문단은 표 블록 안에 있다) · skip = 세지 않을 문단 id(헤딩 그래프의 노드 문단 —
    양식 문서에서 굵은 제목 줄이 바탕 글로 뽑히던 것: 2026-11-14 Fable 검토)."""
    return [{"key": f"b{n}", **g} for n, g in enumerate(_body_groups(blocks, skip)[:BODIES_MAX], 1)]


def body_of(blocks, skip=()) -> dict | None:
    """블록 열 → 바탕 글 `{format, count}` | None(글 문단 없음) — `bodies` 의 1위(빈칸을 뺀 글자 수가 가장 많은 서식 묶음 · 같으면 먼저 나온 것)."""
    top = _body_groups(blocks, skip)[:1]
    return {"format": top[0]["format"], "count": top[0]["count"]} if top else None


def diff_note(section) -> str:
    """구역마다 쪽 설정이 다를 때 losses 에 적는 글 — 고른 구역이 첫 구역이면 `DIFF_NOTE` 그대로, 아니면 몇째 구역 것인지."""
    return DIFF_NOTE if not section else f"{DIFF_HEAD} — 본문 글이 가장 많은 {section + 1}번째 구역 것"


def _pick_section(pages, chars) -> int | None:
    """구역마다의 쪽 설정 pages([page | None …])와 글자 수 chars({구역 번호: 수}) → 고를 구역 번호 | None(읽을 수 있는 쪽 설정이 없음).
    **본문 글이 가장 많은 구역**(spec_서식복사 ② §15 — 표지를 따로 구역으로 둔 문서에서 표지의 쪽 설정이 뽑히던 것) · 같으면 앞 구역 · 글이 없는 문서는 첫 구역."""
    ok = [k for k, p in enumerate(pages) if p is not None]
    return max(ok, key=lambda k: (chars.get(k, 0), -k)) if ok else None


# ---- hwpx ----------------------------------------------------------------------------------------------------------

def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _mm(hu) -> float:
    return round(hu * HU_MM, 2)


def _hu(mm) -> int:
    return round(float(mm) / HU_MM)


def _hwpx_page(pp) -> dict | None:
    """`hp:pagePr` → page | None(값이 없거나 범위 밖). `landscape="NARROWLY"` = 가로(폭·높이는 세로 기준으로 적힌 값 → 바꿔 읽는다 — `HwpxDoc._body_width_mm`·`hwpx_layout.page` 와 같은 규칙).
    위 여백 = top + header(본문 시작) · 아래 여백 = bottom + footer."""
    w, h = _int(pp.get("width")), _int(pp.get("height"))
    if pp.get("landscape") == "NARROWLY":
        w, h = h, w
    m = pp.find(_p("margin"))
    g = lambda k: _int(m.get(k)) if m is not None else 0  # noqa: E731
    try:
        return clean({"widthMm": _mm(w), "heightMm": _mm(h),
                      "marginsMm": {"l": _mm(g("left")), "r": _mm(g("right")), "t": _mm(g("top") + g("header")), "b": _mm(g("bottom") + g("footer")),
                                    "header": _mm(g("header")), "footer": _mm(g("footer")), "gutter": _mm(g("gutter"))}})
    except ValueError:
        return None


def _page_prs(doc) -> list:
    return [pp for sec in doc._sections for pp in sec.iter(_p("pagePr"))]


def read(doc) -> dict | None:
    """`HwpxDoc` 의 첫 구역 쪽 설정(page 꼴) | None(쪽 설정이 없거나 읽을 수 없는 값)."""
    pps = _page_prs(doc)
    return _hwpx_page(pps[0]) if pps else None


def _found(pages, chars, blocks, skip) -> dict | None:
    """of_hwpx·of_docx 의 돌려주는 꼴 — 구역마다의 쪽 설정·글자 수에서 구역을 고르고(`_pick_section`) 바탕 글 후보를 붙인다."""
    k = _pick_section(pages, chars)
    if k is None:
        return None
    top = bodies(blocks, skip)
    return {"page": pages[k], "body": {"format": top[0]["format"], "count": top[0]["count"]} if top else None, "bodies": top, "section": k,
            "losses": [diff_note(k)] if any(p is not None and p != pages[k] for p in pages) else []}


def of_hwpx(doc, skip=()) -> dict | None:
    """`HwpxDoc` → `{"page", "body", "bodies", "section", "losses"}` | None(쪽 설정 없음 — spec_서식복사 ② §15·§16).
    page = **본문 글이 가장 많은 구역**의 쪽 설정(구역마다 그 구역 최상위 글 문단의 글자 수를 센다 — 캡션 제외 · 같으면 앞 구역 · 글이 없는 문서는 첫 구역), section = 그 구역 번호(0부터).
    구역마다 값이 다르면 losses 에 적는다(`diff_note`). bodies = 바탕 글 후보 상위 3(`bodies(doc.blocks(), skip)`) · body = 그 1위 · skip = 세지 않을 문단 id(헤딩 노드).
    구역 하나에 쪽 설정이 여럿이면 그 구역의 첫 것."""
    secs = {s: k for k, s in enumerate(doc._sections)}
    pages = []
    for sec in doc._sections:
        pp = next(sec.iter(_p("pagePr")), None)
        pages.append(_hwpx_page(pp) if pp is not None else None)
    blocks, chars = doc.blocks(), Counter()
    for b in blocks:
        n = _chars(b)
        el = doc._ids.get(b.get("id")) if n else None
        k = secs.get(el.getparent()) if el is not None else None
        if k is not None:
            chars[k] += n
    return _found(pages, chars, blocks, skip)


def _box(page) -> tuple:
    """본문 상자의 (폭, 높이) mm — 이것이 바뀌면 줄 배치가 달라진다."""
    m = page["marginsMm"]
    return round(page["widthMm"] - m["l"] - m["r"] - m["gutter"], 2), round(page["heightMm"] - m["t"] - m["b"], 2)


def set_page(doc, page, *, reflow=True) -> int:
    """`HwpxDoc` 의 **모든 구역**의 쪽 설정(`hp:pagePr` 의 landscape·width·height · `hp:margin` 의 left·right·top·bottom·header·footer·gutter)을 page 로 → 그 쪽 설정이 된 구역 수
    (쪽 설정이 없는 문서 = 0 · 이미 같은 값인 구역도 센다). 값이 이미 같은 구역(mm 소수 둘째 자리까지)은 XML 을 안 건드린다(다시 써서 1 HWPUNIT 씩 밀리지 않게).
    가로는 한글이 쓰는 꼴로(폭·높이는 세로 기준 · `landscape="NARROWLY"`), 세로는 `"WIDELY"`. 제본 방식(`gutterType`)·단·머리말 내용은 그대로.
    바뀐 부분은 `doc._touch` 로 표시한다(저장 때 다시 쓰고 blocks() 캐시를 버린다 — 다른 편집 메서드와 같다).
    reflow: 본문 상자(폭·높이)가 바뀐 구역은 최상위 문단의 줄 배치 캐시(`hp:linesegarray`)를 지운다 — 한글은 캐시가 있는 문단을 다시 조판하지 않아
    (references/HWPX_포맷.md 「한글 실물 렌더 관찰」) 옛 쪽 폭의 줄 나눔이 그대로 남는다(`apply_format` 이 서식을 바꾼 문단의 캐시를 지우는 것과 같은 까닭). 표 칸 안 문단은 그대로(칸 폭은 안 바뀐다)."""
    page = clean(page)
    m, n = page["marginsMm"], 0
    w, h = _hu(page["widthMm"]), _hu(page["heightMm"])
    size = {"landscape": "NARROWLY", "width": str(min(w, h)), "height": str(max(w, h))} if page["landscape"] else {"landscape": "WIDELY", "width": str(w), "height": str(h)}
    head, foot = _hu(m["header"]), _hu(m["footer"])
    margin = {"left": _hu(m["l"]), "right": _hu(m["r"]), "top": max(0, _hu(m["t"]) - head), "bottom": max(0, _hu(m["b"]) - foot), "header": head, "footer": foot, "gutter": _hu(m["gutter"])}
    for sec in doc._sections:
        moved = False
        for pp in sec.iter(_p("pagePr")):
            n += 1
            old = _hwpx_page(pp)
            if old == page:
                continue
            pp.attrib.update(size)
            mg = pp.find(_p("margin"))
            if mg is None:
                mg = etree.SubElement(pp, _p("margin"))
            mg.attrib.update({k: str(v) for k, v in margin.items()})
            moved = moved or old is None or _box(old) != _box(page)
            doc._touch(pp)
        if reflow and moved:
            for p in sec.iterchildren(P):
                for ls in p.findall(LINESEG):
                    p.remove(ls)
    return n


def sample_ids(cdoc) -> list[str]:
    """문서 서식 운반 문서의 견본 문단 id 들(`SAMPLES` 차례) — **첫 문단부터**(견본 첫 줄은 구역 설정을 품은 첫 문단에 있다: `carrier`). 표·글 운반 문서의 `style_carrier.para_ids` 는 첫 문단을 뺀다."""
    return [cdoc._id(p) for p in cdoc._sections[0].iterchildren(P)]


def carrier(page, body=None) -> tuple[bytes, dict]:
    """문서 서식의 hwpx 운반 문서 → (바이트, info `{"fonts": [...], "losses": [...]}`). 빈 바탕(`style_carrier.open_base`)의 쪽 설정을 page 로 바꾸고(`set_page`),
    바탕 글 모양(`body.format`)의 견본 문단 3줄(`SAMPLES`)을 둔다 — 바탕의 평범한 표는 지운다. 글 모양은 `style_carrier.from_text_spec` 과 같은 길
    (평범한 문단에서 출발해 `derive_format` → `apply_format`: 서식 요약에 있는 값만 옮겨진다). 견본 문단 id = `sample_ids(운반 문서)`(첫 문단부터 셋)."""
    from app import style_carrier as SC  # 함수 안에서 — style_carrier 쪽이 이 모듈을 읽어도 서로 물리지 않게
    page = clean(page)
    fmt = body.get("format") if isinstance(body, dict) else None
    losses = []
    cdoc, first, plain = SC.open_base()
    if not set_page(cdoc, page):
        raise ValueError("빈 바탕에 쪽 설정이 없어 문서 서식의 운반 문서를 만들지 못했습니다")
    like = cdoc._id(next(cdoc._ids[plain].iter(P)))
    anchor, want = first, SC._clean_format(fmt)
    if isinstance(fmt, dict) and not want:
        losses.append("바탕 글 모양에 옮길 값이 없어 기본 글 모양의 견본입니다")
    for n, text in enumerate(SAMPLES):
        if n == 0:  # 견본 첫 줄은 바탕의 첫 문단(구역 설정을 품은 문단)에 쓴다 — 빈 채 두면 견본이 둘째 줄로 밀려 본문 위끝을 잴 수 없다(실측 2026-11-14: 위 여백 20mm 인데 첫 견본 줄이 25.6mm)
            cdoc.set_text(first, text)
            cdoc.apply_format([first], cdoc.get_format(like))  # 평범한 문단의 모양에서 출발(다른 견본 줄과 같게)
        else:
            anchor = cdoc.insert_after(anchor, [{"kind": "paragraph", "text": text, "templateId": like}])[0]
        cdoc._ids[anchor].attrib.update({"pageBreak": "0", "columnBreak": "0"})
        if want:
            cdoc.apply_format([anchor], cdoc.derive_format(cdoc.get_format(anchor), want))
    cdoc.delete_blocks(plain, plain)
    if want.get("font") and cdoc.get_format(anchor)["summary"].get("font") != want["font"]:
        losses.append(f"바탕 글꼴 「{want['font']}」 을 견본에 입히지 못했습니다 — 빈 바탕의 글꼴 그대로")
    SC._need_refs(cdoc)
    return cdoc.save(), {"fonts": SC.fonts_of(cdoc), "losses": losses}


# ---- docx ----------------------------------------------------------------------------------------------------------

def _tw(el, attr) -> int:
    """twip 속성(음수 = 「고정」 — 크기로 센다: `docx_layout.page`)."""
    v = el.get(W + attr) if el is not None else None
    try:
        return abs(int(float(v))) if v else 0
    except (TypeError, ValueError):
        return 0


def _docx_page(sect) -> dict | None:
    """`w:sectPr` → page | None(`pgSz`·`pgMar` 가 없거나 범위 밖). 위 여백 = top(본문 시작) · 머리말 = top − header(종이 끝에서 머리말까지 — 음수면 0), 아래도 같다."""
    size, mar = (sect.find(W + t) if sect is not None else None for t in ("pgSz", "pgMar"))
    if size is None or mar is None:
        return None
    mm = lambda tw: round(tw * TW_MM, 2)  # noqa: E731
    top, bottom, head, foot = (_tw(mar, k) for k in ("top", "bottom", "header", "footer"))
    try:
        return clean({"widthMm": mm(_tw(size, "w")), "heightMm": mm(_tw(size, "h")),
                      "marginsMm": {"l": mm(_tw(mar, "left")), "r": mm(_tw(mar, "right")), "t": mm(top), "b": mm(bottom),
                                    "header": mm(max(0, top - head)), "footer": mm(max(0, bottom - foot)), "gutter": mm(_tw(mar, "gutter"))}})
    except ValueError:
        return None


def of_docx(doc, skip=()) -> dict | None:
    """`DocxDoc` → `{"page", "body", "bodies", "section", "losses"}` | None(쪽 설정 없음). 구역 = 구역 끝 문단의 pPr/sectPr 가 앞 구역들, 본문 끝의 sectPr 가 마지막 구역
    (구역이 하나면 본문 끝 것 — `docx_layout.annotate` 와 같은 규칙). page = **본문 글이 가장 많은 구역**의 `w:sectPr`(hwpx 와 같은 규칙: `of_hwpx`) — 구역마다 다르면 losses 에 적는다.
    bodies·body·skip 도 hwpx 와 같다."""
    sect_of, sects, n = {}, [], 0
    for el in doc._body:
        sect_of[el] = n
        s = el.find(f"{W}pPr/{W}sectPr") if el.tag == W + "p" else None
        if s is not None:
            sects.append(s)
            n += 1
    last = doc._body.find(W + "sectPr")
    if last is not None:
        sects.append(last)
    pages = [_docx_page(s) for s in sects]
    blocks, chars = doc.blocks(), Counter()
    for b in blocks:
        n_chars = _chars(b)
        el = doc._ids.get(b.get("id")) if n_chars else None
        while el is not None and el.getparent() is not None and el.getparent() is not doc._body:  # 최상위 요소까지(w:sdt 안 문단 등)
            el = el.getparent()
        k = sect_of.get(el) if el is not None else None
        if k is not None and k < len(pages):
            chars[k] += n_chars
    return _found(pages, chars, blocks, skip)


# ---- pdf -----------------------------------------------------------------------------------------------------------

def of_pdf(measure) -> dict | None:
    """`style_verify.measure_pdf(...)` 의 값(쪽마다 `w`·`h`(pt) · `lines`: [{text, bbox, chars[(글자, x0, y0, x1, y1, span 번호, 굵게)], spans[(글꼴, 크기, flags, 색)]}] · `type3`)
    → `{"page", "body", "losses"}` | None(글이 없음 · 값이 범위 밖).
    쪽 크기 = 가장 많은 크기(pt 로 반올림해 묶음) · 여백 = 그 크기의 쪽마다 글 줄을 모두 싼 상자의 가장자리 → 쪽들의 **중앙값**(header·footer·gutter = 0) ·
    바탕 글 = 빈칸을 뺀 글자 수가 가장 많은 글 조각의 (글꼴, 크기) — 글꼴 이름·크기 어림은 표 추출과 같은 규칙(`style_extract._font_name`·`_size`), count = 그 조각이 가장 많은 줄 수.
    어림이다 — 쪽 번호·머리말 글도 상자에 든다(losses)."""
    pages = [p for p in (measure.get("pages") if isinstance(measure, dict) else None) or [] if p.get("w") and p.get("h")]
    if not pages:
        return None
    key = lambda p: (round(p["w"]), round(p["h"]))  # noqa: E731
    size = Counter(key(p) for p in pages).most_common(1)[0][0]
    same = [p for p in pages if key(p) == size]
    boxes, votes, per_line, type3 = [], Counter(), Counter(), set()
    for p in same:
        lines = [ln for ln in p.get("lines") or [] if (ln.get("text") or "").strip() and len(ln.get("bbox") or ()) == 4]
        if not lines:
            continue
        type3 |= set(p.get("type3") or ())
        x0, y0 = min(ln["bbox"][0] for ln in lines), min(ln["bbox"][1] for ln in lines)
        x1, y1 = max(ln["bbox"][2] for ln in lines), max(ln["bbox"][3] for ln in lines)
        boxes.append((x0, p["w"] - x1, y0, p["h"] - y1))
        for ln in lines:
            spans, own = ln.get("spans") or [], Counter()
            for ch in ln.get("chars") or []:
                if not str(ch[0]).isspace() and 0 <= ch[5] < len(spans):
                    own[spans[ch[5]][0], round(float(spans[ch[5]][1]), 2)] += 1
            votes.update(own)
            if own:
                per_line[own.most_common(1)[0][0]] += 1
    if not boxes:
        return None
    side = lambda k: round(max(0.0, statistics.median(b[k] for b in boxes)) * PT_MM, 2)  # noqa: E731
    w_mm, h_mm = round(same[0]["w"] * PT_MM, 2), round(same[0]["h"] * PT_MM, 2)
    mar, notes = {"l": side(0), "r": side(1), "t": side(2), "b": side(3)}, list(PDF_NOTES)
    # 글이 쪽을 다 채우지 않은 PDF(한두 쪽 · 표 하나) — 글 상자의 아래·오른쪽 가장자리는 여백이 아니다(실측 2026-11-14: 표 하나뿐인 쪽에서 「아래 219mm」). 맞은편 여백과 같게 두고 알린다
    for far, near, size, name in (("b", "t", h_mm, "아래"), ("r", "l", w_mm, "오른쪽")):
        if mar[far] > PDF_FAR_SHARE * size:
            mar[far] = mar[near]
            notes.append(f"{name} 여백은 글이 쪽을 채우지 않아 재지 못했습니다 — {'위' if near == 't' else '왼쪽'} 여백과 같게 두었습니다")
    try:
        page = clean({"widthMm": w_mm, "heightMm": h_mm, "marginsMm": {**mar, "header": 0, "footer": 0, "gutter": 0}})
    except ValueError:
        return None
    body = None
    if votes:
        from app import style_extract  # 함수 안에서 — PDF 글꼴 이름·크기 어림을 표 추출과 같게
        (face, pt), _ = votes.most_common(1)[0]
        try:  # 표 추출(`style_extract._from_pdf`)과 **같은 글꼴 색인**으로 — 색인 없이 부르면 같은 PDF 의 표와 바탕 글의 글꼴 이름이 달라질 수 있다(2026-11-14 Fable 검토)
            from app import fonts
            index = fonts.font_index()
        except Exception:  # noqa: BLE001 — 글꼴 색인을 못 지으면 색인 없이(이름 어림만)
            index = None
        font = style_extract._font_name(face, face in type3, index)
        body = {"format": {**({"font": font} if font else {}), "sizePt": style_extract._size(pt)}, "count": per_line[face, pt]}
    return {"page": page, "body": body, "losses": notes}
