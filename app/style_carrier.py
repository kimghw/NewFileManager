"""운반 문서(spec_일반편집 ② §3) — 서식 템플릿의 서식 정의를 담은 작은 hwpx 하나: 빈 바탕(`app/style_base.hwpx`)의 첫 문단 + **표 하나를 품은 문단**(표 서식)
또는 **item 차례대로 견본 문단 하나씩**(글 서식 — n번째 견본 문단 ↔ `items[n]`). 화면에는 안 나오는 말이다.

- 만들기: hwpx 원본에서 `from_table`·`from_paras`(고유 정의 그대로 — `insert_after(copy, src=)`) · 형식 중립 명세에서 `from_table_spec`·`from_text_spec`
  (빈 바탕의 평범한 표·문단에서 출발해 `table_make` → `derive_format`·`apply_cell_format`·`set_cell_edges` — docx·PDF 원본).
- **자료값은 저장하지 않는다**(`keep_text` 가 아니면): 표 = **라벨 칸**(`label_cells` — 머리 표시가 있는 머리 띠 줄의, 자료처럼 보이지 않는 글)의 보이는 글만 같은 모양으로
  다시 쓰고(각주·필드·숨은 설명·책갈피·개체는 안 따라온다), 나머지 칸은 견본(수 꼴 「0」 · 그 밖 「가나다」 · 빈 칸은 빈 채) /
  글 = 레터(앞 공백 + 레터 + 사이 공백) + 「견본 글입니다」 — 견본 문단에는 글 조각만 남긴다. 견본이 있어야 PDF 검증이 글자 모양을 잰다.
  띠 수(머리행·머리열·합계행)는 **서식의 구역**일 뿐 글을 남길 권한이 아니다 — 표시 없는 표의 첫 행(관례로 머리행)·사람이나 LLM 이 넓힌 띠의 글은 자료일 수 있다(astra 10).
  옮길 때 들여온 그림 바이트(BinData)도 안 가리키면 뺀다(`_drop_unused_bins`).
- 원본에 **없는 정의를 가리키는 참조**(`broken_refs`)가 닿는 표·문단은 서식으로 만들지 않는다 — 문서 사이 복사가 그 번호를 그대로 넘겨 받는 문서의 같은 번호 정의에 말없이 붙는다(astra 8).
  만든 운반 문서에 끊어진 참조가 있어도 내지 않는다(깨진 템플릿이 보관함에 들어가지 않게).
- 운반 문서는 **무손실이 아니다** — 뺀 것은 `losses`(표) · `unsupported`(글 item)에 적는다. 띠 수·레벨·레터 정책·라벨 칸 같은 **뜻의 원본은 meta**(app/style_lib.py)다.
- 읽기: `doc`(적용 때의 `src`) · `table_id` · `para_ids` · `view`(끝점 `GET /api/styles/{sid}` 가 싣는 것) · `cell_texts` · `spec_of_block`(웹 표 블록 → 표 명세)."""
import copy
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree

from app import heading_rules as R
from app import owpml_check
from app import table_grid as grid
from app import table_make as M
from app.hwpx_doc import CAPTION, HC, HEADER, HPF, OBJECTS, PIC, RUN, SUBLIST, TAB, TBL, TC, TR, HwpxDoc, P, T, _h, _p
from app.hwpx_format import ALIGN, HEX6, LANG_FONT_KEYS, SUMMARY_KEYS

BASE = Path(__file__).with_name("style_base.hwpx")
SAMPLE, SAMPLE_NUM, SAMPLE_TEXT = "견본 글입니다", "0", "가나다"  # 견본 글 — 문단 · 수 꼴 칸 · 그 밖의 칸
SAMPLE_MAX, PREVIEW_TEXT, NAME_MAX = 60, 40, 60
ZERO = {"headerRows": 0, "headerCols": 0, "footRows": 0}
SIDES = {"t": "top", "r": "right", "b": "bottom", "l": "left"}
# OWPML 이 받는 선 굵기(hc:LineWidth)·선 종류(hc:LineType2) — 명세의 값은 이 가운데 가장 가까운 것으로(다른 값은 스키마 위반)
LINE_WIDTHS = (0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
LINE_TYPES = frozenset(["NONE", "SOLID", "DOT", "DASH", "DASH_DOT", "DASH_DOT_DOT", "LONG_DASH", "CIRCLE", "DOUBLE_SLIM", "SLIM_THICK", "THICK_SLIM", "SLIM_THICK_SLIM"])
NO_LINE = {"type": "NONE", "width": "0.1 mm", "color": "#000000"}
ALIGNS = frozenset(ALIGN.values())
NUM_RANGES = (("sizePt", 1, 400), ("lineSpacingPct", 50, 500), ("ratioPct", 50, 200), ("spacingPct", -50, 50), ("firstLineMm", -200, 200),
              ("indentLeftMm", 0, 200), ("indentRightMm", 0, 200), ("spaceBeforePt", 0, 200), ("spaceAfterPt", 0, 200))
_NUMLIKE = re.compile(r"[\s\d,.%+\-−–~∼()△▲]+")
# 라벨로 남기지 않을 「자료처럼 보이는 글」(data_like) — 숫자 사이의 구분 글자를 떼고 DATA_DIGITS 자리 이상 이어지는 숫자 · 전자우편 · 전화번호 꼴
DATA_DIGITS = 6
_DIGIT_SEP = re.compile(r"(?<=\d)[\s\-–−.,/()·:]{1,3}(?=\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)0\d{1,2}[-.\s)]{1,2}\d{3,4}[-.\s]\d{4}(?!\d)")
AUTO_NOTE = "자동 번호 — 대상 문서의 번호 설정을 따름"
STYLE_NOTE = "같은 이름의 스타일은 넣는 문서의 것을 씁니다(문단·글자 모양 값은 그대로 옮김)"
SPEC_NOTE = "서식 요약(글꼴·크기·굵게·정렬·줄 간격·음영·괘선·칸 여백)만 옮겼습니다 — 그 밖의 모양은 기본값"


# ---- 빈 바탕 · 읽기 ------------------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def base() -> bytes:
    """빈 바탕(A4 · 좌우 여백 20mm · 구역 설정 문단 하나 + 평범한 2×2 표 하나 — tools/make_style_base.py)의 바이트."""
    return BASE.read_bytes()


def open_base():
    """빈 바탕을 새로 연 것 -> (HwpxDoc, 첫 문단 id, 평범한 표 id)."""
    d = HwpxDoc(base())
    d.blocks()
    return d, d._id(next(d._sections[0].iterchildren(P))), d._id(next(d._sections[0].iter(TBL)))


def doc(carrier: bytes) -> HwpxDoc:
    """운반 문서를 연 것(블록 id 가 붙은 채 — 적용 때의 `src`). 못 열면 ValueError."""
    try:
        d = HwpxDoc(carrier)
        d.blocks()
    except Exception as e:  # noqa: BLE001 — 깨진 zip·XML 은 종류가 여럿이다
        raise ValueError(f"운반 문서를 열 수 없습니다: {type(e).__name__}: {e}") from e
    return d


def table_id(cdoc) -> str:
    """운반 문서의 (하나뿐인) 표 id — 없으면 ValueError."""
    tbl = next((o for sec in cdoc._sections for p in sec.iterchildren(P) for r in p.iterchildren(RUN) for o in r.iterchildren(TBL)), None)
    if tbl is None:
        raise ValueError("운반 문서에 표가 없습니다")
    return cdoc._id(tbl)


def para_ids(cdoc) -> list[str]:
    """견본 문단 id 들(item 차례) — 빈 바탕의 첫 문단(구역 설정)은 뺀다."""
    return [cdoc._id(p) for p in list(cdoc._sections[0].iterchildren(P))[1:]]


# ---- 공통 ---------------------------------------------------------------------------------------------------------

def sample_of(text) -> str:
    """칸 글의 견본 — 빈 칸은 빈 채, 수 꼴(숫자·쉼표·%·-)은 「0」, 그 밖은 「가나다」."""
    t = (text or "").strip()
    if not t:
        return ""
    return SAMPLE_NUM if _NUMLIKE.fullmatch(t) and (re.search(r"\d", t) or len(t) == 1) else SAMPLE_TEXT


def is_label(row, col, text, bands, rows) -> bool:
    """머리 띠 안의 칸인가(서식의 구역): 머리행 · 머리열(합계행의 머리열 칸 포함) + 합계행의 「합계·소계·계」 칸(머리열이 없는 표의 합계 라벨).
    **글을 남길 칸인지는 `label_cells` 가 따로 본다** — 띠 안이라도 머리 표시가 없는 줄·자료처럼 보이는 글은 라벨이 아니다."""
    return row < bands["headerRows"] or col < bands["headerCols"] or (row >= rows - bands["footRows"] and bool(M.TOTAL_RE.match(text or "")))


def data_like(text) -> bool:
    """라벨로 남기기에는 자료처럼 보이는 글인가 — 숫자 사이의 구분 글자(빈칸·-·.·,·/·괄호)를 떼고 숫자가 6자리 이상 이어짐(주민번호·계좌·금액·날짜) · 전자우편 주소 · 전화번호 꼴."""
    t = str(text or "")
    return bool(_EMAIL.search(t) or _PHONE.search(t) or re.search(r"\d{%d,}" % DATA_DIGITS, _DIGIT_SEP.sub("", t)))


def label_cells(cells, bands, rows) -> set:
    """글을 남길 **라벨 칸**의 (행, 열) 들. cells = 표 블록의 칸(row·col·rowSpan·colSpan·text·shaded·bold), bands = 띠 수, rows = 행 수.
    띠 수는 서식의 구역이고 글을 남길 권한은 따로 본다 — 띠 안의 칸 가운데:
    - 머리행의 칸은 그 **행에 머리 표시**(음영 또는 굵게)가 있는 칸이 있을 때만, 머리열의 칸은 머리행 아래에서 그 **열에 머리 표시**가 있는 칸이 있을 때만.
      표 전체가 음영(글이 있는 칸이 모두 굵게)이면 그것은 구별되는 표시가 아니다 — 표시 없는 표의 첫 행은 관례로 머리행이지만(`table_make.roles_of`) 라벨이 아니다.
    - 합계행의 「합계·소계·계」 꼴 글 칸은 글 자체가 라벨(표시가 없어도).
    - 어느 것이든 빈 글과 자료처럼 보이는 글(`data_like`)은 뺀다."""
    cells = list(cells)
    h, k, f = bands["headerRows"], bands["headerCols"], bands["footRows"]
    texted = [c for c in cells if (c.get("text") or "").strip()]
    plain_shade, plain_bold = all(c.get("shaded") for c in cells), bool(texted) and all(c.get("bold") for c in texted)
    marked = [c for c in cells if (c.get("shaded") and not plain_shade) or (c.get("bold") and not plain_bold)]
    span = lambda c, at, n: range(c[at], c[at] + c.get(n, 1))  # noqa: E731
    row_ev = {r for c in marked for r in span(c, "row", "rowSpan") if r < h}
    col_ev = {x for c in marked if c["row"] + c.get("rowSpan", 1) > h for x in span(c, "col", "colSpan") if x < k}
    out = set()
    for c in texted:
        text = c["text"].strip()
        if data_like(text):
            continue
        if (any(r in row_ev for r in span(c, "row", "rowSpan")) and c["row"] < h) or (any(x in col_ev for x in span(c, "col", "colSpan")) and c["col"] < k) \
                or (c["row"] >= rows - f and bool(M.TOTAL_RE.match(text))):
            out.add((c["row"], c["col"]))
    return out


def kept_labels(block, bands) -> set:
    """운반 문서(또는 양식으로 고른 표)의 표 블록에서 **글이 남아 있는 라벨 칸**의 (행, 열) — 빈 표로 넣을 때 안 비우는 칸(meta 에 `labels` 가 없는 템플릿·이 문서의 표).
    만들 때와 같은 규칙(`label_cells`)이고, 견본 글(「가나다」·「0」)만 든 칸은 라벨이 아니다(만들 때 견본으로 바꾼 머리 띠 칸)."""
    at = {(c["row"], c["col"]): c for c in block["cells"]}
    return {rc for rc in label_cells(block["cells"], bands, block["nRows"]) if at[rc]["text"].strip() not in (SAMPLE_NUM, SAMPLE_TEXT)}


def broken_refs(doc, els=None, shallow=()) -> list[str]:
    """doc 안에서 **풀리지 않는 정의 참조**(없는 문단·글자 모양·테두리/배경·탭·스타일·번호 정의 · 글꼴 · 그림 — `owpml_check` 의 「ref」 규칙)의 글들(겹침 없이).
    els None = 문서 전체(header + 본문 — 운반 문서처럼 작은 문서). els = 그 요소들과 거기서 **닿는 정의**만(큰 원본 문서에서 옮길 표·문단 — 문서 다른 곳의 손상은 안 본다),
    shallow = 속성만 볼 요소(표를 품은 문단·런 — 그 모양만 따라온다).
    문서 사이 복사(`HwpxDoc._import_def`·`_import_font`)는 원본에 없는 정의의 번호를 그대로 넘긴다 — 받는 문서의 같은 번호 정의에 말없이 붙으므로 **가져오기 전에 원본에서** 본다."""
    if els is None:
        return list(dict.fromkeys(v["message"] for v in owpml_check.rule_violations(doc) if v["kind"][1] == "ref"))
    out, seen, todo = [], set(), [*els, *(e.makeelement(e.tag, dict(e.attrib)) for e in shallow)]
    while todo:
        el = todo.pop()
        owpml_check._refs(doc, el, out, "section")
        for e in el.iter():
            if not isinstance(e.tag, str):
                continue
            found = [(kind, e.get(attr)) for attr, kind in owpml_check.REF_ATTRS.items() if e.get(attr) is not None]
            if e.tag == _h("heading") and e.get("type") in ("BULLET", "NUMBER"):
                found.append(("bullet" if e.get("type") == "BULLET" else "numbering", e.get("idRef")))
            for key in found:
                d = doc._defs[key[0]].get(key[1])
                if d is not None and key not in seen:
                    seen.add(key)
                    todo.append(d)
    return list(dict.fromkeys(v["message"] for v in out))


def _need_refs(doc, els=None, shallow=(), what="서식 템플릿", did="저장하지") -> None:
    """`broken_refs` 가 있으면 ValueError — 원본에서(옮기기 전) · 만든 운반 문서에서(내기 전)."""
    bad = broken_refs(doc, els, shallow)
    if bad:
        raise ValueError(f"{what}의 정의 참조가 깨져 있어 {did} 않았습니다 — " + " · ".join(bad[:5]))


def _drop_unused_bins(cdoc) -> int:
    """운반 문서를 만들며 들여온 그림 바이트(새 BinData 멤버) 가운데 header·본문 어디서도 안 가리키는 것을 뺀다(zip 멤버 + content.hpf 의 manifest 항목) -> 뺀 수.
    문서 사이 복사는 그림 XML 과 함께 바이트를 먼저 들여온다 — 칸 안 그림을 XML 에서만 빼면 원본 그림이 zip 에 남는다(astra 10)."""
    used = {e.get("binaryItemIDRef") for root in (cdoc._roots[HEADER], *cdoc._sections) for e in root.iter() if isinstance(e.tag, str) and e.get("binaryItemIDRef")}
    n = 0
    for iid, item in list(cdoc._items.items()):
        href = item.get("href")
        if iid not in used and href in cdoc._new_members:
            del cdoc._new_members[href], cdoc._items[iid]
            item.getparent().remove(item)
            cdoc._mark(HPF)
            n += 1
    return n


def _no_break(p):
    """옮긴 문단의 쪽·단 나눔을 끈다 — 원본 문단이 `pageBreak="1"` 을 물고 오면 운반 문서 첫 쪽이 비고, 적용한 문서에서는 쪽이 갈린다."""
    p.attrib.update({"pageBreak": "0", "columnBreak": "0"})


def _strip_objects(doc, p) -> int:
    """문단 p 의 런에서 개체(표·그림·그리기 개체·수식)를 뺀다 -> 뺀 수."""
    n = 0
    for r in p.iterchildren(RUN):
        for o in [o for o in r if o.tag in OBJECTS]:
            r.remove(o)
            n += 1
    return n


def _plain_para(doc, p):
    """문단 p 의 **보이는 글만** 든 새 문단(붙이지 않은 것) — 문단 속성(문단 모양·스타일)과 글이 든 런마다의 글자 모양은 그대로, 런에는 글 조각(hp:t) 하나만(탭·줄 바꿈은 남는다).
    각주·필드·숨은 설명·책갈피(hp:ctrl) · 개체 · 겹친 글자·덧말 · 글 조각 안의 표시 요소는 따라오지 않는다. 글이 없으면 첫 글 런 모양의 빈 런 하나."""
    new = p.makeelement(P, dict(p.attrib))
    for r in p.iterchildren(RUN):
        text = "".join(doc._slot_text(s) for s in doc._run_slots(r))
        if text:
            t = etree.SubElement(etree.SubElement(new, RUN, dict(r.attrib)), T)
            for tab in [c for s in r.iterchildren(T) for c in s if c.tag == TAB]:
                etree.SubElement(t, TAB, dict(tab.attrib))  # 탭의 폭·채움은 그대로(_write_t 가 차례대로 되쓴다)
            doc._write_t(t, text)
    if not len(new):
        etree.SubElement(new, RUN, {"charPrIDRef": doc._char_id(p)})
    return new


def _plain_cell(doc, tc, dropped=()) -> None:
    """칸 tc 의 문단들을 보이는 글만 든 문단으로 다시 쓴다(라벨 칸 — 줄 수·문단 모양·글자 모양은 그대로). dropped = 개체만 들었다가 빈 문단들 — 뺀다."""
    sub = tc.find(SUBLIST)
    old = list(sub.iterchildren(P)) if sub is not None else []
    if not old:
        return
    new = [_plain_para(doc, p) for p in old if p not in dropped] or [_plain_para(doc, old[0])]
    for ch in list(sub):
        sub.remove(ch)
    sub.extend(new)


def _scrub(doc, p) -> None:
    """문단 p 에 글 조각(hp:t)만 남긴다 — 런의 다른 자식(각주·필드·숨은 설명·책갈피를 품은 hp:ctrl · 겹친 글자 · 덧말 · 양식 개체)과 문단의 런 아닌 자식을 빼고,
    글 조각은 보이는 글만으로 다시 쓴다(탭·줄 바꿈만 남는다). 런·글 조각의 경계와 글자 모양은 그대로(레터 런 ↔ 본문 런 — `put_text` 가 그 경계에 쓴다)."""
    for ch in [c for c in p if c.tag != RUN]:
        p.remove(ch)
    for r in p.iterchildren(RUN):
        for ch in [c for c in r if c.tag != T]:
            r.remove(ch)
        for t in r.iterchildren(T):
            doc._write_t(t, doc._slot_text(t))


def _img_fill(src, el) -> bool:
    """el 이 쓰는 테두리/배경 정의(직접 + 그 문단·글자 모양을 거쳐)에 그림 채움이 있는가 — `_import_def` 가 옮기지 않는 것."""
    ids = set()
    for e in el.iter():
        if not isinstance(e.tag, str):
            continue
        ids.add(e.get("borderFillIDRef"))
        for attr, kind in (("charPrIDRef", "charPr"), ("paraPrIDRef", "paraPr")):
            d = src._defs[kind].get(e.get(attr))
            if d is not None:
                ids.update(x.get("borderFillIDRef") for x in d.iter() if isinstance(x.tag, str))
    return any((bf := src._defs["borderFill"].get(i)) is not None and next(bf.iter(f"{{{HC}}}imgBrush"), None) is not None for i in ids if i)


def _copy_losses(src, el) -> list[str]:
    """원본 요소 el(표·문단)을 옮기며 빠지는 것 가운데 **원본에서 알 수 있는 것** — 그림 채움 · 번호 다시 시작 · 같은 이름 스타일."""
    out = []
    if _img_fill(src, el):
        out.append("그림 채움(칸·문단 배경 그림)은 옮기지 않았습니다")
    if next(el.iter(_p("newNum")), None) is not None:
        out.append("번호 다시 시작(newNum)은 옮기지 않았습니다")
    if any(e.get("styleIDRef") in src._defs["style"] for e in el.iter() if isinstance(e.tag, str)):
        out.append(STYLE_NOTE)
    return out


def fonts_of(cdoc) -> list[str]:
    """운반 문서의 본문(첫 문단 뒤)이 쓰는 글꼴 이름(언어별 글꼴 포함) — `requirements.fonts`."""
    names = set()
    for p in list(cdoc._sections[0].iterchildren(P))[1:]:
        for r in p.iter(RUN):
            s = cdoc._char_summary(cdoc._defs["charPr"].get(r.get("charPrIDRef")))
            names.update(s.get(k) for k in ("font", *LANG_FONT_KEYS))
    return sorted(n for n in names if n)


def fit_width(doc, tid, avail_mm=None) -> bool:
    """표 tid 가 넣인 자리의 글 폭(avail_mm 을 안 주면 `_body_width_mm` — 본문 = 쪽 폭 − 좌우 여백 · 칸 안 = 칸 폭 − 칸 여백)보다 넓으면 열 폭을 비례로 줄인다 -> 줄였나.
    칸 높이·구조는 그대로(열 폭과 표 폭만)."""
    tbl = doc._ids[tid]
    _, cells, nr, nc = doc._tgrid(tbl)
    heights, widths = doc._tsizes(cells, nr, nc)
    avail = round((avail_mm if avail_mm is not None else doc._body_width_mm(doc._host(tbl))) * 7200 / 25.4)
    if avail <= 0 or sum(widths) <= avail or nc <= 0:
        return False
    after = list(widths)
    grid.refit(after, 0, nc - 1, avail)
    doc._col_put(tbl, cells, heights, widths, after, (0, nc - 1), [])
    if (sz := tbl.find(_p("sz"))) is not None:
        sz.set("width", str(avail))
    return True


def body_char(doc, p, plen: int = 0) -> str:
    """문단 p 에서 본문(앞 plen 글자 = 레터 자리 뒤)이 시작하는 글 런의 글자 모양 id — 그런 런이 없으면 첫 글 런 것."""
    acc = 0
    for r in p.iterchildren(RUN):
        n = sum(len(doc._slot_text(s)) for s in doc._run_slots(r))
        if n and acc + n > plen:
            return r.get("charPrIDRef", "0")
        acc += n
    return doc._char_id(p)


def put_text(doc, p, prefix: str, body: str, plen: int = 0) -> bool:
    """문단 p 의 글을 prefix + body 로 쓴다(런과 그 글자 모양은 그대로) -> 레터와 본문을 따로 넣었나.
    plen = 지금 글에서 레터 자리(앞 공백 + 레터 + 사이 공백)의 길이 — 그 자리가 **글 조각(hp:t) 경계**에서 끝나면 prefix 는 첫 글 조각에, body 는 경계 뒤 첫 글 조각에 쓴다
    (레터 런과 본문 런의 글자 모양이 다른 문단: 「□」 는 기호 글꼴 · 본문은 본문 글꼴). 경계가 안 맞거나 레터가 없으면 통째로 첫 글 조각에(= 첫 글 런 모양 하나).
    글 조각이 없거나 자동 번호 조각이 끼어 있으면 기존 길(`set_text` — 글을 조각에 나눠 넣기)."""
    prefix, body = prefix.replace("\n", " "), body.replace("\n", " ")
    slots = doc._slots(p)
    if not slots or any(s.tag != T for s in slots):
        doc.set_text(doc._id(p), prefix + body)
        return False
    texts = [doc._slot_text(s) for s in slots]
    first = next((k for k, t in enumerate(texts) if t), 0)
    cut, acc = None, 0
    for k, t in enumerate(texts):
        if plen and acc == plen and t:
            cut = k
            break
        acc += len(t)
    new = [""] * len(slots)
    if cut is not None and prefix:
        new[first], new[cut] = prefix, body
    else:
        new[first], cut = prefix + body, None
    for s, old, text in zip(slots, texts, new):
        if old != text:
            doc._write_t(s, text)
    doc._drop_cache(p)
    doc._touch(p)
    return cut is not None


# ---- hwpx 표에서 ----------------------------------------------------------------------------------------------------

def _look(cdoc, c) -> dict:
    """칸 블록 c 의 겉모습 요약 — 음영 + 그 칸의 첫 글 문단(없으면 첫 문단)의 글꼴·크기·굵게·정렬."""
    like = cdoc._tm_para_like(cdoc._ids[c["id"]])
    s = cdoc._summary(like.get("paraPrIDRef"), cdoc._char_id(like)) if like is not None else {}
    return {"fill": c.get("fill"), "font": s.get("font"), "sizePt": s.get("sizePt"), "bold": bool(s.get("bold")), "align": s.get("align")}


def _rows_of(block, limit=None) -> list[dict]:
    """표 블록 → 격자의 행 [{"cells": [{text, rowSpan, colSpan}]}] — limit 이 있으면 칸 글을 그만큼만."""
    rows = [{"cells": []} for _ in range(block["nRows"])]
    for c in sorted(block["cells"], key=lambda c: (c["row"], c["col"])):
        if 0 <= c["row"] < len(rows):
            text = c.get("text") or ""
            rows[c["row"]]["cells"].append({"text": text[:limit] if limit else text, "rowSpan": c["rowSpan"], "colSpan": c["colSpan"]})
    return rows


def _preview(cdoc, tid, bands) -> dict:
    """meta.preview — 격자(칸 글 40자) + 구역(head·stub·body·foot)마다 대표 칸의 겉모습(그 구역이 없으면 None)."""
    b = cdoc.table_block(tid)
    h, k, f, nr, nc = bands["headerRows"], bands["headerCols"], bands["footRows"], b["nRows"], b["nCols"]
    at = {}
    for c in b["cells"]:
        for r in range(c["row"], c["row"] + c["rowSpan"]):
            for x in range(c["col"], c["col"] + c["colSpan"]):
                at.setdefault((r, x), c)
    body = h if h < nr - f else None
    spots = {"head": (h - 1, min(k, nc - 1)) if h else None, "stub": (body, 0) if k and body is not None else None,
             "body": (body, k) if body is not None and k < nc else None, "foot": (nr - f, min(k, nc - 1)) if f else None}
    return {"grid": {"rows": _rows_of(b, PREVIEW_TEXT), **bands},
            "looks": {zone: _look(cdoc, at[rc]) if rc in at else None for zone, rc in spots.items()}}


def _info(cdoc, tid, bands, losses, labels=()) -> dict:
    tbl = cdoc._ids[tid]
    return {"rows": int(tbl.get("rowCnt")), "cols": int(tbl.get("colCnt")), "bands": bands, "losses": losses, "fonts": fonts_of(cdoc), "preview": _preview(cdoc, tid, bands),
            "labels": [list(rc) for rc in sorted(labels)]}


def from_table(src, tid, bands, keep_text=False):
    """hwpx 문서 src 의 표 tid → (운반 문서 바이트, info {rows, cols, bands, losses, fonts, preview{grid, looks}, labels: [[행, 열]…]}). src 는 안 바뀐다.
    빈 바탕에 표를 host 문단째 옮기고(`insert_after(copy, src=)` — 쓰는 정의만 따라온다) 평범한 표는 지운다. 옮긴 문단의 쪽·단 나눔은 끈다.
    칸 안 표·그림과 캡션은 뺀다(칸은 글만) — 함께 들여온 그림 바이트도. keep_text 가 아니면 **라벨 칸**(`label_cells` — info.labels)은 보이는 글만 같은 모양으로 다시 쓰고
    (각주·필드·숨은 설명·책갈피는 안 따라온다) 나머지 칸은 첫 글 문단 모양의 문단 하나로 줄여 글을 견본으로 바꾼다. bands = 띠 수(없는 값은 자동 판정).
    표가 닿는 정의 참조가 원본에서 끊어져 있으면 ValueError(`broken_refs` — 옮기면 빈 바탕의 같은 번호 정의에 붙는다)."""
    tbl = src._ids.get(tid) if isinstance(tid, str) else None
    if tbl is None or tbl.tag != TBL or not src._attached(tbl):
        raise ValueError("서식으로 저장할 표가 지금 문서에 없습니다")
    own = copy.deepcopy(tbl)  # 옮긴 뒤에도 남을 것만(캡션·칸 안 표·그림은 어차피 뺀다) — 거기서 닿는 정의를 원본에서 본다
    for cap in own.findall(CAPTION):
        own.remove(cap)
    for p in (p for tr in own.iterchildren(TR) for tc in tr.iterchildren(TC) if (sub := tc.find(SUBLIST)) is not None for p in sub.iterchildren(P)):
        _strip_objects(src, p)
    _need_refs(src, [own], shallow=[src._host(tbl), tbl.getparent()], what="원본 문서", did="서식으로 저장하지")
    losses = _copy_losses(src, tbl)
    cdoc, first, plain = open_base()
    new = cdoc.insert_after(first, [{"kind": "copy", "srcId": tid}], src=src)[0]
    cdoc.delete_blocks(plain, plain)
    ctbl = cdoc._ids[new]
    _no_break(cdoc._host(ctbl))
    for cap in ctbl.findall(CAPTION):
        ctbl.remove(cap)
        losses.append("표 캡션은 옮기지 않았습니다")
    if not keep_text:
        for note in ctbl.findall(_p("shapeComment")):  # 개체 설명 글(보이지 않는 글)
            ctbl.remove(note)
    cells = [tc for tr in ctbl.iterchildren(TR) for tc in tr.iterchildren(TC)]
    nested, emptied = 0, set()  # 뺀 개체 수 · 개체만 들었다가 빈 문단
    for p in (p for tc in cells if (sub := tc.find(SUBLIST)) is not None for p in sub.iterchildren(P)):
        had_text = bool(cdoc._text(p).strip())
        n = _strip_objects(cdoc, p)
        nested += n
        if n and not had_text:
            emptied.add(p)
    if nested:
        losses.append(f"칸 안 표·그림 {nested}개는 옮기지 않았습니다(칸은 글만)")
    cdoc._touch(ctbl)
    block = cdoc.table_block(new)
    rows, cols = block["nRows"], block["nCols"]
    bands = M.clean_roles(bands, rows, cols, default=M.roles_of(block["cells"], rows, cols))
    labels = label_cells(block["cells"], bands, rows)
    if not keep_text:
        for c in block["cells"]:
            if (c["row"], c["col"]) in labels:
                _plain_cell(cdoc, cdoc._ids[c["id"]], emptied)  # 라벨 — 보이는 글만 같은 모양으로 다시 쓴다
                continue
            cdoc._blank_cell(cdoc._ids[c["id"]])  # 첫 글 문단 모양의 빈 문단 하나 — 각주·필드 같은 딸린 내용도 함께 빠진다
            if text := sample_of(c["text"]):
                cdoc.set_text(c["id"], text)
        cdoc._touch(ctbl)
    was = sum(cdoc._tsizes(*cdoc._tgrid(ctbl)[1:])[1]) * 25.4 / 7200
    if fit_width(cdoc, new):
        losses.append(f"표 폭 {was:.0f}mm 를 바탕 쪽의 글 폭에 맞춰 줄였습니다(열 폭 비율은 그대로)")
    _drop_unused_bins(cdoc)
    _need_refs(cdoc)
    return cdoc.save(), _info(cdoc, new, bands, losses, labels)


# ---- hwpx 문단에서 --------------------------------------------------------------------------------------------------

def _marker(src, p, text, rules) -> dict:
    """문단의 레터 정책 {mode: literal|auto|none, literal, lead, gap, family}. 자동 번호(문단 모양의 hh:heading 이 OUTLINE·NUMBER·BULLET)는 auto —
    레터를 글에 다시 쓰지 않는다. 아니면 글머리 규칙(내장 규칙만 — 보관함은 문서와 무관)으로 읽은 레터가 있으면 literal, 없으면 none."""
    h = src._heading(p)
    if h is not None and h.get("type") in ("OUTLINE", "NUMBER", "BULLET"):
        return {"mode": "auto", "literal": "", "lead": "", "gap": "", "family": None}
    head = R.classify(text, rules)
    if head["letter"] and head["kind"] in ("marker", "note", "footnote"):
        return {"mode": "literal", "literal": head["letter"], "lead": head["lead"], "gap": head["gap"], "family": head["family"]}
    return {"mode": "none", "literal": "", "lead": "", "gap": "", "family": None}


def _clean_marker(m) -> dict:
    """명세로 받은 레터 정책을 고른 꼴로 — 글자 레터가 비었으면 none."""
    m = m if isinstance(m, dict) else {}
    mode = m.get("mode") if m.get("mode") in ("literal", "auto", "none") else "none"
    lit = str(m.get("literal") or "")[:20] if mode == "literal" else ""
    if mode == "literal" and not lit.strip():
        mode = "none"
    ws = lambda v: v[:20] if isinstance(v, str) and mode == "literal" and not v.strip(R.WS) else ""  # noqa: E731
    return {"mode": mode, "literal": lit, "lead": ws(m.get("lead")), "gap": ws(m.get("gap")), "family": m.get("family") if mode == "literal" and isinstance(m.get("family"), str) else None}


def _prefix(marker) -> str:
    return marker["lead"] + marker["literal"] + marker["gap"] if marker["mode"] == "literal" else ""


def _item(n, pick, marker, sample, fmt, unsupported, para=None) -> dict:
    """meta.items 의 항목 하나(spec ② §2) — key 는 차례(i1·i2…), 레벨은 준 것만(지어내지 않는다)."""
    level, origin = pick.get("level"), pick.get("origin") if isinstance(pick.get("origin"), dict) else {}
    name = re.sub(r"\s+", " ", pick["name"]).strip() if isinstance(pick.get("name"), str) else ""
    name = name or (marker["literal"].strip() or {"auto": "자동 번호", "none": "문단"}.get(marker["mode"], "문단")) + f" {n}"
    return {"key": f"i{n}", "name": name[:NAME_MAX], "level": level if isinstance(level, int) and not isinstance(level, bool) and level > 0 else None,
            "origin": {"template": origin.get("template"), "slot": origin.get("slot"), "para": para}, "marker": marker, "sample": sample[:SAMPLE_MAX],
            "format": fmt, "unsupported": unsupported}


def from_paras(src, picks, keep_text=False):
    """hwpx 문서 src 의 문단들 → (운반 문서 바이트, items). picks = [{"para": 문단 id, "level"?, "origin"?, "name"?}] — 문단마다 견본 문단 하나(차례대로).
    문단을 복사하고(표·그림·개체는 뺌, 쪽·단 나눔은 끔) 글을 레터 + 「견본 글입니다」 로 바꾼다 — 견본 문단에는 **글 조각만** 남긴다(`_scrub`: 각주·필드·숨은 설명·책갈피·겹친 글자·덧말은
    안 따라온다). keep_text 면 원문 60자 — 딸린 내용도 그대로(사람이 글째 저장하기로 한 것).
    레터 런과 본문 런이 갈린 문단은 그 경계를 지켜 쓴다(put_text). 본문의 글자 모양이 여러 가지면 `unsupported` 에 적는다(줄 쓰기는 첫 모양 하나로 쓴다).
    문단이 닿는 정의 참조가 원본에서 끊어져 있으면 ValueError(`broken_refs`)."""
    if not isinstance(picks, list) or not picks:
        raise ValueError("서식으로 저장할 문단을 고르세요")
    cdoc, first, plain = open_base()
    rules, anchor, items = R.active({}), first, []
    for n, pick in enumerate(picks, 1):
        pid = pick.get("para") if isinstance(pick, dict) else None
        p = src._ids.get(pid) if isinstance(pid, str) else None
        if p is None or p.tag != P or not src._attached(p):
            raise ValueError("서식으로 저장할 문단이 지금 문서에 없습니다")
        own = copy.deepcopy(p)  # 옮겨질 것만(문단의 표·그림은 따로 블록이라 안 따라온다) — 거기서 닿는 정의를 원본에서 본다
        for o in [o for r in own.iterchildren(RUN) for o in r if o.tag in (TBL, PIC)]:
            o.getparent().remove(o)
        _need_refs(src, [own], what="원본 문서", did="서식으로 저장하지")
        text = src._text(p)
        marker = _marker(src, p, text, rules)
        unsupported = [AUTO_NOTE] if marker["mode"] == "auto" else []
        unsupported += [x for x in _copy_losses(src, p) if x != STYLE_NOTE]
        if src._has_object(p):
            unsupported.append("문단 안 표·그림·개체는 옮기지 않았습니다")
        anchor = cdoc.insert_after(anchor, [{"kind": "copy", "srcId": pid}], src=src)[0]
        el = cdoc._ids[anchor]
        _no_break(el)
        _strip_objects(cdoc, el)
        if not keep_text:
            _scrub(cdoc, el)  # 글 조각만 — 그 글은 바로 아래에서 레터 + 견본으로 바뀐다
        plen = len(_prefix(marker))
        split = put_text(cdoc, el, text[:plen], text[plen:SAMPLE_MAX] if keep_text else SAMPLE, plen)
        if len(set(_shapes_after(src, p, plen if split else 0))) > 1:  # 레터를 따로 넣었으면 본문 쪽만 본다
            unsupported.append("글자 모양이 여러 가지인 문단 — 줄 쓰기는 본문의 첫 글 런 모양 하나로 씁니다")
        fmt = cdoc._summary(el.get("paraPrIDRef"), body_char(cdoc, el, plen))  # 서식 요약은 본문 쪽 글자 모양으로(레터 런이 따로면 그것은 레터만의 모양)
        items.append(_item(n, pick, marker, cdoc._text(el), fmt, unsupported, para=pid))
    cdoc.delete_blocks(plain, plain)
    _drop_unused_bins(cdoc)
    _need_refs(cdoc)
    return cdoc.save(), items


def _shapes_after(src, p, skip) -> list:
    """원본 문단 p 에서 앞 skip 글자 뒤의 글이 든 런들의 글자 모양 id(차례대로)."""
    out, acc = [], 0
    for r in p.iterchildren(RUN):
        n = sum(len(src._slot_text(s)) for s in src._run_slots(r))
        if n and acc + n > skip:
            out.append(r.get("charPrIDRef"))
        acc += n
    return out


# ---- 명세에서 -------------------------------------------------------------------------------------------------------

def _clean_format(fmt) -> dict:
    """서식 요약 사전에서 `derive_format` 이 받는 값만 — 꼴이 틀리거나 범위 밖인 값은 버린다(명세는 docx·PDF 측정에서도 온다)."""
    f, out = fmt if isinstance(fmt, dict) else {}, {}
    if isinstance(f.get("font"), str) and f["font"].strip():
        out["font"] = f["font"].strip()[:60]
    for k, lo, hi in NUM_RANGES:
        if isinstance(f.get(k), (int, float)) and not isinstance(f[k], bool) and lo <= f[k] <= hi:
            out[k] = f[k]
    out.update({k: f[k] for k in ("bold", "italic", "underline") if isinstance(f.get(k), bool)})
    if isinstance(f.get("color"), str) and HEX6.fullmatch(f["color"]):
        out["color"] = f["color"].upper()
    if f.get("align") in ALIGNS:
        out["align"] = f["align"]
    return out


def _line(e) -> dict:
    """명세의 변 {type, widthMm, color} | None(선 없음) → `set_cell_edges` 의 선 — 굵기·종류는 OWPML 이 받는 값 가운데 가장 가까운 것."""
    kind = str(e.get("type") or "NONE").upper() if isinstance(e, dict) else "NONE"
    if kind == "NONE":
        return dict(NO_LINE)
    try:
        w = float(e.get("widthMm") or 0.12)
    except (TypeError, ValueError):
        w = 0.12
    w = min(LINE_WIDTHS, key=lambda x: abs(x - w))
    color = e.get("color") if isinstance(e.get("color"), str) and HEX6.fullmatch(e["color"]) else "#000000"
    return {"type": kind if kind in LINE_TYPES else "SOLID", "width": f"{w:.1f} mm" if w >= 1 else f"{w:g} mm", "color": color.upper()}


def _margins(m, default):
    try:
        out = {k: round(float(m[k]), 2) for k in ("l", "r", "t", "b")} if isinstance(m, dict) else None
    except (KeyError, TypeError, ValueError):
        out = None
    return out if out is not None and all(0 <= v <= 50 for v in out.values()) else default


def from_table_spec(spec, keep_text=False):
    """표 명세(spec ② §3 — `{rows, cols, bands, widthsMm, cells: [{row, col, rowSpan, colSpan, text, fill, valign, marginsMm, edges, format}]}`) →
    (운반 문서 바이트, info — from_table 과 같은 꼴). 빈 바탕의 평범한 표에서 그 격자의 표를 만들고 칸마다 글 모양·음영·세로 정렬·칸 여백·괘선을 입힌다.
    칸 글은 from_table 과 같은 규칙(keep_text 가 아니면 라벨 칸(`label_cells` — 음영 = fill · 굵게 = format.bold)만 그대로, 나머지는 견본).
    명세에 없는 칸 자리는 빈 칸(기본 모양), 겹치는 칸은 버린다 — 그 수를 losses 에 적는다."""
    if not isinstance(spec, dict) or not isinstance(spec.get("cells"), list) or not spec["cells"]:
        raise ValueError("표 명세에 칸이 없습니다")
    try:
        rows, cols = int(spec.get("rows")), int(spec.get("cols"))
        given = sorted(((int(c["row"]), int(c["col"]), max(1, int(c.get("rowSpan") or 1)), max(1, int(c.get("colSpan") or 1)), c) for c in spec["cells"]), key=lambda x: x[:2])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"표 명세의 행·열 값이 틀렸습니다: {e}") from e
    if not (1 <= rows <= M.ROWS_MAX and 1 <= cols <= M.COLS_MAX):
        raise ValueError(f"표 명세의 크기가 한도 밖입니다({rows}행 × {cols}열)")
    bands = M.clean_roles(spec.get("bands"), rows, cols)
    occ, by, bad = set(), {}, 0
    for r, k, rs, cs, c in given:
        area = {(y, x) for y in range(r, min(rows, r + rs)) for x in range(k, min(cols, k + cs))}
        if not (0 <= r < rows and 0 <= k < cols) or area & occ:
            bad += 1
            continue
        occ |= area
        by[r, k] = (c, {"text": str(c.get("text") or ""), "rowSpan": min(rs, rows - r), "colSpan": min(cs, cols - k)})
    shaded = lambda c: isinstance(c.get("fill"), str) and bool(HEX6.fullmatch(c["fill"])) and c["fill"].upper() != "#FFFFFF"  # noqa: E731
    labels = label_cells([{"row": r, "col": k, **cell, "shaded": shaded(c), "bold": isinstance(c.get("format"), dict) and c["format"].get("bold") is True}
                          for (r, k), (c, cell) in by.items()], bands, rows)  # from_table 과 같은 규칙 — 머리 표시(음영·굵게)가 있는 줄의, 자료처럼 보이지 않는 글만
    if not keep_text:
        for rk, (_, cell) in by.items():
            if rk not in labels:
                cell["text"] = sample_of(cell["text"])
    holes = [(r, k) for r in range(rows) for k in range(cols) if (r, k) not in occ]
    cells = {**{rk: v[1] for rk, v in by.items()}, **{rk: {"text": "", "rowSpan": 1, "colSpan": 1} for rk in holes}}
    order = sorted(cells)  # (행, 열) 차례 = 정규화한 칸 차례(칸이 시작하지 않는 줄을 없애도 차례는 그대로)
    norm = M.normalize({"rows": [[cells[r, k] for k in range(cols) if (r, k) in cells] for r in range(rows)], **bands})
    same = len(norm["cells"]) == len(order)
    at = {(n["row"], n["col"]): by[rk][0] for n, rk in zip(norm["cells"], order) if rk in by} if same else {rk: v[0] for rk, v in by.items()}
    labels = {(n["row"], n["col"]) for n, rk in zip(norm["cells"], order) if rk in labels} if same else labels  # 정규화한 격자의 자리로
    bands = M.clean_roles(bands, norm["nRows"], norm["nCols"])
    cdoc, first, plain = open_base()
    tid = cdoc.table_make(first, plain, norm, ZERO)["table"]
    cdoc.delete_blocks(plain, plain)
    losses, widths = [SPEC_NOTE], spec.get("widthsMm")
    if isinstance(widths, list) and len(widths) == norm["nCols"] and all(isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0 for w in widths):
        cdoc.set_line_sizes(tid, "c", dict(enumerate(widths)))
        if fit_width(cdoc, tid):
            losses.append(f"표 폭 {sum(widths):.0f}mm 를 바탕 쪽의 글 폭에 맞춰 줄였습니다(열 폭 비율은 그대로)")
    for c in cdoc.table_block(tid)["cells"]:
        s = at.get((c["row"], c["col"]))
        if s is None:  # 메운 자리 — 기본 모양으로 둔다
            continue
        cur = cdoc.get_cell_format(c["id"])
        fill = s.get("fill").upper() if isinstance(s.get("fill"), str) and HEX6.fullmatch(s["fill"]) else None
        look = {"text": cdoc.derive_format(cur["text"], _clean_format(s.get("format"))), "fill": fill,
                "valign": s["valign"] if s.get("valign") in ("top", "center", "bottom") else cur["valign"], "marginsMm": _margins(s.get("marginsMm"), cur["marginsMm"])}
        cdoc.apply_cell_format([c["id"]], look, ["text", "fill", "valign", "margins"], keep_numbering=False)
        if isinstance(s.get("edges"), dict):
            cdoc.set_cell_edges(c["id"], {SIDES[k]: _line(v) for k, v in s["edges"].items() if k in SIDES})
    if bad or holes:
        losses.append(f"명세의 칸 자리가 격자와 어긋났습니다 — 버린 칸 {bad}개 · 빈 칸으로 메운 자리 {len(holes)}곳")
    _need_refs(cdoc)
    return cdoc.save(), _info(cdoc, tid, bands, losses, labels)


def from_text_spec(items, keep_text=False):
    """글 서식 명세 items = [{"name", "level", "marker", "sample", "format": 서식 요약 사전}] → (운반 문서 바이트, meta.items 꼴의 items).
    빈 바탕의 평범한 문단(평범한 표의 칸 문단 모양 — 10pt · 왼쪽 정렬 · 줄 간격 160%)에서 출발해 서식 요약을 입힌다. 견본 글 = 레터 + 「견본 글입니다」
    (keep_text 면 준 sample 60자 — 원본 글을 싣는 것이므로 부르는 쪽이 정한다). 자동 번호는 되살리지 않는다(그 정의가 명세에 없다)."""
    if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
        raise ValueError("글 서식 명세에 항목이 없습니다")
    cdoc, first, plain = open_base()
    like = cdoc._id(next(cdoc._ids[plain].iter(P)))
    anchor, out = first, []
    for n, it in enumerate(items, 1):
        marker = _clean_marker(it.get("marker"))
        sample = str(it.get("sample") or "")[:SAMPLE_MAX] if keep_text and it.get("sample") else _prefix(marker) + SAMPLE
        anchor = cdoc.insert_after(anchor, [{"kind": "paragraph", "text": sample, "templateId": like}])[0]
        _no_break(cdoc._ids[anchor])
        cdoc.apply_format([anchor], cdoc.derive_format(cdoc.get_format(anchor), _clean_format(it.get("format"))))
        out.append(_item(n, it, marker, sample, cdoc.get_format(anchor)["summary"], [AUTO_NOTE] if marker["mode"] == "auto" else []))
    cdoc.delete_blocks(plain, plain)
    _need_refs(cdoc)
    return cdoc.save(), out


# ---- 표 블록 → 명세 · 보기 ------------------------------------------------------------------------------------------

def _col_widths(cells, cols):
    """칸 폭(widthMm)에서 열 폭 [mm…] — 한 열만 덮는 칸에서 읽고, 남은 열은 합친 칸의 폭에서 아는 열을 빼서. 다 못 구하면 None."""
    out = [None] * cols
    for _ in range(cols + 1):
        done = True
        for c in cells:
            span = range(c["col"], min(cols, c["col"] + c["colSpan"]))
            miss = [k for k in span if out[k] is None]
            if len(miss) == 1 and isinstance(c.get("widthMm"), (int, float)) and c["widthMm"] > 0:
                w = c["widthMm"] - sum(out[k] for k in span if out[k] is not None)
                if w > 0:
                    out[miss[0]], done = round(w, 2), False
        if done:
            break
    return out if cols and all(v is not None for v in out) else None


def spec_of_block(block) -> dict:
    """웹 표 블록(hwpx `HwpxDoc.table_block` · docx `DocxDoc.blocks()` 의 표) → 표 명세(형식 중립 — from_table_spec 이 받는 꼴). 칸의 글 모양 = 그 칸의 첫 글 문단
    (없으면 첫 문단)의 서식 요약, 괘선 = 표 블록의 borderFills 에서. 띠 수는 자동 판정(`table_make.roles_of`)."""
    cells = sorted(block.get("cells") or [], key=lambda c: (c["row"], c["col"]))
    rows = block.get("nRows") or max((c["row"] + c.get("rowSpan", 1) for c in cells), default=0)
    cols = block.get("nCols") or max((c["col"] + c.get("colSpan", 1) for c in cells), default=0)
    lines, out = block.get("borderFills") or {}, []
    for c in cells:
        paras = [b for b in c.get("blocks") or [] if b.get("type") == "paragraph"]
        like = next((b for b in paras if (b.get("text") or "").strip()), paras[0] if paras else {})
        edges = lines.get(c.get("bf"))
        out.append({"row": c["row"], "col": c["col"], "rowSpan": c.get("rowSpan", 1), "colSpan": c.get("colSpan", 1), "text": c.get("text") or "",
                    "fill": c.get("fill"), "valign": c.get("valign"), "marginsMm": c.get("marginsMm"),
                    "edges": {k: edges.get(k) for k in SIDES} if isinstance(edges, dict) else None,
                    "format": {k: v for k, v in (like.get("format") or {}).items() if k in SUMMARY_KEYS}})
    return {"rows": rows, "cols": cols, "bands": M.roles_of(cells, rows, cols), "cells": out,
            "widthsMm": _col_widths([{**c, "colSpan": c.get("colSpan", 1)} for c in cells], cols)}


def cell_texts(carrier: bytes) -> dict:
    """표 운반 문서의 칸 글 {(행, 열): 글 전체} — 구조(blueprint)의 라벨 글과 기본 이름은 **운반 문서에 남긴 글**에서만 읽는다(원본 문서의 칸 글이 아니라)."""
    d = doc(carrier)
    return {(c["row"], c["col"]): c["text"] for c in d.table_block(table_id(d))["cells"]}


def view(carrier: bytes, meta: dict) -> dict:
    """운반 문서의 보기(끝점 `GET /api/styles/{sid}`) — 표 서식: {"table": 운반 문서 안 표 id, "grid": 글 전체 격자(띠 수는 meta 것), "spec": 표 명세} ·
    글 서식: {"paras": [견본 문단 id…], "items": meta.items} · 문서 서식(spec_서식복사 ② §5·§8): {"page": meta.page, "body": meta.body, "summary": 요약 한 줄 —
    「A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm · 본문 함초롬바탕 11pt」(`style_page.summary` — 그 모듈이 없으면 빈 글), "paras": [견본 문단 id…]} ·
    표지 서식(spec_서식복사 ② §14·§16): `style_cover.view(carrier, meta)` = {"page", "parts": [{"type": "text", …} | {"type": "table", "spec"}]} — 그 모듈이 아직 없으면 meta 의 값 그대로
    ({"page": meta.page, "parts": meta.parts} — 표 부분의 명세 `spec` 은 없다)."""
    if meta.get("kind") == "cover":
        try:
            from app import style_cover
        except ImportError:  # 표지 모듈이 아직 없음 — 운반 문서가 열리는지만 보고 meta 의 값을 그대로 보인다
            doc(carrier)
            return {"page": meta.get("page") if isinstance(meta.get("page"), dict) else None, "parts": [p for p in meta.get("parts") or [] if isinstance(p, dict)]}
        try:
            return style_cover.view(carrier, meta)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001 — 보기를 못 지은 것은 「운반 문서를 못 읽음」 과 같은 길로(끝점이 view: null + viewError)
            raise ValueError(f"표지 서식의 보기를 짓지 못했습니다: {type(e).__name__}: {e}") from e
    d = doc(carrier)
    if meta.get("kind") == "page":
        page, body = meta.get("page") if isinstance(meta.get("page"), dict) else None, meta.get("body") if isinstance(meta.get("body"), dict) else None
        try:
            from app import style_page
            summary, paras = (style_page.summary(page, body) if page else ""), getattr(style_page, "sample_ids", para_ids)(d)  # 견본 첫 줄은 첫 문단(구역 설정을 품은 문단)에 있다 — para_ids 는 그 문단을 뺀다
        except ImportError:  # 문서 서식 모듈이 아직 없음 — 값은 그대로 보인다
            summary, paras = "", para_ids(d)
        return {"page": page, "body": body, "summary": summary, "paras": paras}
    if meta.get("kind") == "text":
        return {"paras": para_ids(d), "items": meta.get("items") or []}
    tid = table_id(d)
    b = d.table_block(tid)
    bands = M.clean_roles(meta.get("bands"), b["nRows"], b["nCols"])
    return {"table": tid, "grid": {"rows": _rows_of(b), **bands}, "spec": {**spec_of_block(b), "bands": bands}}
