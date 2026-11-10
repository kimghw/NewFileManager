"""Paragraph and cell formats for DocxDoc (spec §8); DocxDoc's public format methods delegate here.

A format token is the XML `<w:fmt><w:pPr/><w:rPr/></w:fmt>`: the exemplar paragraph's pPr (numbering included,
section break and revision marks left out) and its first text run's rPr. Self-contained, but document-local: the
style and numbering ids in it only mean something in the document it came from.
A summary resolves effective values: direct properties, then the style chains (rStyle, pStyle and their basedOn),
then w:docDefaults, then Word's own defaults."""
import copy
import re
import weakref

from lxml import etree

from app.docx_doc import (_parser, _REVISIONS, A, W, W_NS, _has_text, _kids, _number_off, _on, _runs, _strip, _text,
                          _val)


def _seq(names):
    return [W + t for t in names.split()]


# Schema child sequences (CT_PPr, CT_ParaRPr/CT_RPr, CT_TcPr, CT_TcMar) - new children go to their place in these.
_PPR = _seq("pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs "
            "suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi "
            "adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection "
            "textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange")
_RPR = _seq("ins del moveFrom moveTo rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss "
            "imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr "
            "shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange")
_TCPR = _seq("cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark "
             "headers cellIns cellDel cellMerge tcPrChange")
_TCMAR = _seq("top start left bottom end right")
# What a target keeps of its own when a format is applied: section break, revision marks, hidden-text flags.
_KEEP_P = set(_seq("sectPr pPrChange"))
_KEEP_MARK = set(_seq("ins del moveFrom moveTo rPrChange"))
_KEEP_R = set(_seq("rPrChange vanish specVanish webHidden"))
_ALIGN_IN = {"left": "left", "start": "left", "center": "center", "right": "right", "end": "right", "both": "justify",
             "distribute": "distribute"}
_ALIGN_OUT = {"left": "left", "center": "center", "right": "right", "justify": "both", "distribute": "distribute"}
_KEYS = {"font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct", "align", "indentLeftMm", "indentRightMm",
         "firstLineMm", "spaceBeforePt", "spaceAfterPt", "lineSpacingPct"}
_HEX6 = re.compile(r"#[0-9A-Fa-f]{6}")
_TW_MM = 1440 / 25.4  # twips per mm
_PT_MM = 25.4 / 72
_SIDES = {"t": ("top",), "l": ("left", "start"), "b": ("bottom",), "r": ("right", "end")}
_CACHE = weakref.WeakKeyDictionary()  # DocxDoc -> {(pPr xml, rPr xml): summary, "tblDefault": table style id}


# ---- small XML helpers ----------------------------------------------------------------------------------------

def _place(parent, el, order):
    """Insert el after the last child of parent that precedes it in the schema sequence `order`."""
    before = set(order[:order.index(el.tag)])
    parent.insert(max((i + 1 for i, c in enumerate(parent) if c.tag in before), default=0), el)
    return el


def _child(parent, tag, order):
    e = parent.find(W + tag)
    return e if e is not None else _place(parent, etree.Element(W + tag), order)


def _set(parent, tag, order, val):
    """parent/tag holding only w:val=val (theme colour and other attributes dropped)."""
    e = _child(parent, tag, order)
    e.attrib.clear()
    e.set(W + "val", val)


def _keep(old, new, tags, order):
    """new takes old's children with `tags` in place of its own."""
    for c in [c for c in new if c.tag in tags]:
        new.remove(c)
    for c in old if old is not None else ():
        if c.tag in tags:
            _place(new, copy.deepcopy(c), order)


def _num(e, attr):
    v = e.get(W + attr) if e is not None else None
    return int(v) if v and v.lstrip("-").isdigit() else 0


def _el(doc, block_id, tag):
    el = doc._ids[block_id]
    if el.tag != W + tag:
        raise ValueError(f"{block_id} is not a {'paragraph' if tag == 'p' else 'table cell'}")
    return el


# ---- summaries ------------------------------------------------------------------------------------------------

def _props(p):
    """(pPr, rPr) of paragraph p: its pPr and its first text run's rPr (no text run: the paragraph mark's)."""
    ppr = p.find(W + "pPr")
    run = next((r for r in _runs(p) if _has_text(r)), None)
    if run is None:   # 글 런이 없으면 빈 런(rPr 만 — 글 없는 칸, 표 서식 정리가 쓴 모양), 그것도 없으면 문단 끝 표식의 모양
        run = next((r for r in _runs(p) if len(r) and all(c.tag == W + "rPr" for c in r)), None)
    if run is not None:
        return ppr, run.find(W + "rPr")
    return ppr, ppr.find(W + "rPr") if ppr is not None else None


def _pick(chain, fn):
    return next((v for v in map(fn, chain) if v is not None), None)


def _group(chain, tag, attrs):
    """First `tag` element in the chain setting any of `attrs` (w:ind / w:spacing inherit attribute group-wise)."""
    return next((e for e in (x.find(W + tag) for x in chain)
                 if e is not None and any(e.get(W + a) is not None for a in attrs)), None)


def _theme_font(doc, name):
    """Typeface of a theme font reference (minorEastAsia, majorHAnsi, ...); None without a theme part."""
    rel = next((r for r in doc._rels.values() if r.get("Type", "").endswith("/theme")), None)
    theme = doc._part(doc._resolve(doc._dir, rel.get("Target"))) if rel is not None else None
    font = theme.find(f".//{A}{name[:5]}Font") if theme is not None else None
    if font is None:
        return None
    kind = "ea" if name.endswith("EastAsia") else "cs" if name.endswith("Bidi") else "latin"
    face = font.find(A + kind).get("typeface") if font.find(A + kind) is not None else ""
    if not face and kind == "ea":
        # ponytail: an empty East Asian theme font is taken from the Hangul script entry (Korean documents);
        # settings.xml w:themeFontLang is not consulted.
        face = next((f.get("typeface") for f in font.findall(A + "font") if f.get("script") == "Hang"), "")
    return face or None


def _font(doc, rprs):
    """East Asian font of the chain, else its ASCII font; a theme reference wins over a name on the same rFonts."""
    for kind in ("eastAsia", "ascii"):
        face = _font_of(doc, rprs, kind)
        if face:
            return face
    return None


def _font_of(doc, rprs, kind):
    """rFonts `kind` (eastAsia | ascii | hAnsi) of the chain — attribute-wise inheritance, theme reference wins on the same rFonts."""
    for x in rprs:
        f = x.find(W + "rFonts")
        if f is not None and f.get(W + kind + "Theme"):
            return _theme_font(doc, f.get(W + kind + "Theme"))
        if f is not None and f.get(W + kind):
            return f.get(W + kind)
    return None


def _lang_fonts(doc, rprs, font):
    """NFM 웹 보기(spec_docx_웹편집 ② §2): 영문 글꼴 fontLatin(ascii, 없으면 hAnsi) — 한자·일어는 동아시아 글꼴(= font)이라 따로 두지 않는다."""
    latin = _font_of(doc, rprs, "ascii") or _font_of(doc, rprs, "hAnsi")
    return {"fontLatin": latin if latin and latin != font else None}


def _num_ppr(doc, pprs):
    """문단의 번호(numPr — 직접 또는 스타일 체인, numId 0 = 번호 없음) 수준 정의의 pPr: w:num 의 lvlOverride/lvl 이 있으면 그것, 아니면
    abstractNum 의 같은 ilvl. 없으면 None."""
    num = lvl = None
    for x in pprs:
        npr = x.find(W + "numPr") if x is not None else None
        if npr is not None:
            num = num if num is not None else _val(npr, W + "numId")
            lvl = lvl if lvl is not None else _val(npr, W + "ilvl")
            if num is not None:
                break
    n = doc._nums.get(num) if num not in (None, "0") else None
    if n is None:
        return None
    ilvl = lvl or "0"
    ov = next((o for o in n.findall(W + "lvlOverride") if o.get(W + "ilvl") == ilvl), None)
    el = ov.find(W + "lvl") if ov is not None else None
    if el is None:
        a = doc._abstracts.get(_val(n, W + "abstractNumId"))
        el = next((x for x in a.findall(W + "lvl") if x.get(W + "ilvl") == ilvl), None) if a is not None else None
    return el.find(W + "pPr") if el is not None else None


# 표 스타일 조건부 서식(NFM spec_docx_웹편집 ② §2): cnfStyle 속성 → tblStylePr type, val 비트 차례도 이것과 같다
_CNF = {"firstRow": "firstRow", "lastRow": "lastRow", "firstColumn": "firstCol", "lastColumn": "lastCol",
        "oddVBand": "band1Vert", "evenVBand": "band2Vert", "oddHBand": "band1Horz", "evenHBand": "band2Horz",
        "firstRowFirstColumn": "nwCell", "firstRowLastColumn": "neCell", "lastRowFirstColumn": "swCell", "lastRowLastColumn": "seCell"}
_COND_HIGH = ("nwCell", "neCell", "swCell", "seCell", "firstRow", "lastRow", "firstCol", "lastCol",
              "band1Horz", "band2Horz", "band1Vert", "band2Vert")  # Word 가 겹쳐 그리는 차례 — 앞이 이김
_CORNER = {"nwCell": ("firstRow", "firstCol"), "neCell": ("firstRow", "lastCol"), "swCell": ("lastRow", "firstCol"), "seCell": ("lastRow", "lastCol")}
_LOOK_BITS = {"firstRow": 0x20, "lastRow": 0x40, "firstColumn": 0x80, "lastColumn": 0x100, "noHBand": 0x200, "noVBand": 0x400}


def table_style_id(doc, tbl):
    """표의 스타일 id — tblStyle, 없으면 기본 표 스타일(w:default)."""
    cache = _CACHE.setdefault(doc, {})
    if "tblDefault" not in cache:
        cache["tblDefault"] = next((k for k, s in doc._styles.items() if s.get(W + "type") == "table"
                                    and s.get(W + "default") in ("1", "true", "on")), None)
    return _val(tbl.find(W + "tblPr"), W + "tblStyle") or cache["tblDefault"]


def _look(tbl):
    look = tbl.find(f"{W}tblPr/{W}tblLook")
    if look is None:
        return {"firstRow": True, "firstColumn": True, "noVBand": True}  # Word 새 표 기본(04A0)
    bits = int(look.get(W + "val") or "0", 16) if all(look.get(W + k) is None for k in _LOOK_BITS) else 0
    return {k: (look.get(W + k) in ("1", "true", "on")) if look.get(W + k) is not None else bool(bits & b) for k, b in _LOOK_BITS.items()}


def cell_ctx(doc, el):
    """el(w:p·w:tc 또는 그 안 요소)이 든 표 칸 -> (표 스타일 id, 걸리는 조건부 서식 종류 — 이기는 것 먼저) | None. Word 가 저장한 칸·문단의
    w:cnfStyle 을 먼저 믿고, 없으면 칸 자리 + tblLook(머리 행·첫 열·줄무늬 크기)으로 센다."""
    if el is None:
        return None
    tc = el if el.tag == W + "tc" else next(el.iterancestors(W + "tc"), None)
    tbl = next(tc.iterancestors(W + "tbl"), None) if tc is not None else None
    sid = table_style_id(doc, tbl) if tbl is not None else None
    if sid not in doc._styles:
        return None
    p = el if el.tag == W + "p" else next(el.iterancestors(W + "p"), None)
    cnf = tc.find(f"{W}tcPr/{W}cnfStyle")
    if cnf is None and p is not None and p.find(f"{W}pPr/{W}cnfStyle") is not None:
        cnf = p.find(f"{W}pPr/{W}cnfStyle")
    if cnf is not None:
        on = {t for a, t in _CNF.items() if cnf.get(W + a) in ("1", "true", "on")}
        if not on and cnf.get(W + "val"):
            on = {t for t, ch in zip(_CNF.values(), cnf.get(W + "val")) if ch == "1"}
    else:
        tr = tc.getparent()
        rows = list(_kids(tbl, (W + "tr",)))
        r = rows.index(tr) if tr in rows else 0
        col = int(_val(tr.find(W + "trPr"), W + "gridBefore") or 0)
        for x in _kids(tr, (W + "tc",)):
            if x is tc:
                break
            col += int(_val(x.find(W + "tcPr"), W + "gridSpan") or 1)
        span = int(_val(tc.find(W + "tcPr"), W + "gridSpan") or 1)
        ncols = len(tbl.findall(f"{W}tblGrid/{W}gridCol")) or col + span
        lk, st = _look(tbl), doc._styles[sid].find(W + "tblPr")
        rb, cb = int(_val(st, W + "tblStyleRowBandSize") or 1), int(_val(st, W + "tblStyleColBandSize") or 1)
        on = set()
        first, last = lk["firstRow"] and r == 0, lk["lastRow"] and r == len(rows) - 1
        fcol, lcol = lk["firstColumn"] and col == 0, lk["lastColumn"] and col + span >= ncols
        on |= {t for t, ok in (("firstRow", first), ("lastRow", last), ("firstCol", fcol), ("lastCol", lcol),
                               ("nwCell", first and fcol), ("neCell", first and lcol), ("swCell", last and fcol), ("seCell", last and lcol)) if ok}
        if not lk["noHBand"] and not first and not last:
            on.add("band1Horz" if ((r - lk["firstRow"]) // rb) % 2 == 0 else "band2Horz")
        if not lk["noVBand"] and not fcol and not lcol:
            on.add("band1Vert" if ((col - lk["firstColumn"]) // cb) % 2 == 0 else "band2Vert")
    for corner, (row, col) in _CORNER.items():  # 모서리 칸은 그 행·열 서식도(AIP 서식: cnfStyle firstRowFirstColumn=1·firstRow=0 인 칸을 Word 는 머리 행 흰 글로 찍음)
        if corner in on:
            on |= {row, col}
    return sid, tuple(t for t in _COND_HIGH if t in on)


def _table_props(doc, ctx, tag):
    """표 스타일 체인의 tag(pPr|rPr|tcPr) — 조건부 서식(이기는 것 먼저) 다음 표 전체."""
    if not ctx:
        return []
    chain = list(doc._chain(ctx[0]))
    out = [x.find(W + tag) for t in ctx[1] for s in chain for x in s.findall(W + "tblStylePr") if x.get(W + "type") == t]
    return [x for x in out + [s.find(W + tag) for s in chain] if x is not None]


def summary(doc, ppr, rpr, ctx=None):
    """Spec §8 summary of a pPr + run rPr pair, effective values resolved (memoised per distinct XML pair:
    the adapter only ever adds styles, never changes one). ctx = cell_ctx() — 표 칸 안 문단이면 표 스타일(조건부 서식 포함)도 체인에."""
    key = (*(b"" if e is None else etree.tostring(e) for e in (ppr, rpr)), ctx)
    cache = _CACHE.setdefault(doc, {})
    if key not in cache:
        cache[key] = _summary(doc, ppr, rpr, ctx)
    return dict(cache[key])


def _summary(doc, ppr, rpr, ctx=None):
    # 표 스타일(조건부 서식 → 표 전체)은 기본 문단 스타일보다 이기고, 따로 고른 문단 스타일에는 진다(NFM — Word 16 PDF: AIP 서식 머리 행 흰 굵은 글).
    styles = doc._sub_part("styles")
    dd = styles.find(W + "docDefaults") if styles is not None else None
    dd = dd if dd is not None else etree.Element(W + "docDefaults")
    pstyles = list(doc._chain(_val(ppr, W + "pStyle") or doc._default_pstyle))
    rstyles = list(doc._chain(_val(rpr, W + "rStyle")))
    if rstyles and (_val(rstyles[0], W + "name") or "").lower() == "hyperlink" and pstyles \
            and re.fullmatch(r"toc \d", (_val(pstyles[0], W + "name") or "").lower()):
        rstyles = []  # Word 는 목차 항목 하이퍼링크에 Hyperlink 글자 스타일(파랑·밑줄)을 안 그린다 — 목차 문단 모양(NFM, Word 16 PDF 실측)
    spprs = [s.find(W + "pPr") for s in pstyles]
    # NFM(spec_docx_웹편집 ② §2): 번호 수준의 문단 속성(abstractNum lvl/pPr — 들여쓰기·탭)은 직접 서식 다음, 문단 스타일 앞
    nppr = _num_ppr(doc, [ppr, *spprs])
    tp, tr_ = _table_props(doc, ctx, "pPr"), _table_props(doc, ctx, "rPr")
    own = bool(pstyles) and (_val(ppr, W + "pStyle") or doc._default_pstyle) != doc._default_pstyle  # 따로 고른 문단 스타일
    srprs = [s.find(W + "rPr") for s in pstyles]
    pc = [x for x in [ppr, nppr, *(spprs + tp if own else tp + spprs), dd.find(f"{W}pPrDefault/{W}pPr")] if x is not None]
    rc = [x for x in [rpr, *(s.find(W + "rPr") for s in rstyles), *(srprs + tr_ if own else tr_ + srprs),
                      dd.find(f"{W}rPrDefault/{W}rPr")] if x is not None]
    size = int(_pick(rc, lambda x: _val(x, W + "sz")) or 20) / 2  # half-points; Word's default is 10pt
    color = _pick(rc, lambda x: _val(x, W + "color"))
    # ponytail: *Chars indents count one character as the font size, *Lines spacing one line as 12pt;
    # w:beforeAutospacing/afterAutospacing (HTML-style spacing) are ignored.
    left = _group(pc, "ind", ("left", "start", "leftChars", "startChars"))
    chars = _num(left, "leftChars") or _num(left, "startChars")
    left_mm = chars / 100 * size * _PT_MM if chars else (_num(left, "left") or _num(left, "start")) / _TW_MM
    right = _group(pc, "ind", ("right", "end", "rightChars", "endChars"))
    chars = _num(right, "rightChars") or _num(right, "endChars")
    right_mm = chars / 100 * size * _PT_MM if chars else (_num(right, "right") or _num(right, "end")) / _TW_MM
    first =_group(pc, "ind", ("firstLine", "hanging", "firstLineChars", "hangingChars"))
    chars = _num(first, "firstLineChars") - _num(first, "hangingChars")
    hang = first is not None and first.get(W + "hanging") is not None
    first_mm = chars / 100 * size * _PT_MM if chars else (-_num(first, "hanging") if hang
                                                         else _num(first, "firstLine")) / _TW_MM

    def space(side):
        e = _group(pc, "spacing", (side, side + "Lines"))
        return _num(e, side + "Lines") * 12 / 100 or _num(e, side) / 20

    line = _group(pc, "spacing", ("line",))
    if line is None:
        pct = 100
    elif line.get(W + "lineRule", "auto") == "auto":
        pct = round(_num(line, "line") / 2.4)  # 240ths of a line
    else:
        pct = None  # exact / atLeast: a fixed height, not a percentage
    font = _font(doc, rc)
    va = _pick(rc, lambda x: _val(x, W + "vertAlign"))
    extra = {**_lang_fonts(doc, rc, font),
             # NFM 웹 보기(spec_docx_웹편집 ② §2): 윗·아래첨자, 줄 나눔 단위 — w:wordWrap 0 = 영문 단어 중간 줄 바꿈 허용
             "script": {"superscript": "sup", "subscript": "sub"}.get(va),
             "wordBreak": "char" if _pick(pc, lambda x: _on(x, W + "wordWrap")) is False else "word"}
    return {**{k: v for k, v in extra.items() if v is not None}, "font": font, "sizePt": size,
            "bold": bool(_pick(rc, lambda x: _on(x, W + "b"))), "italic": bool(_pick(rc, lambda x: _on(x, W + "i"))),
            "underline": bool(_pick(rc, lambda x: None if x.find(W + "u") is None else _val(x, W + "u") != "none")),
            "color": "#" + color.upper() if color and color != "auto" else None,
            # 장평 = w:w %, 자간 = w:spacing twips as % of the font size (spec_서식 §1).
            # ponytail: Word's spacing is absolute, not scaled by w:w — matches 한글 자간 only at 100% 장평 (Word default)
            "ratioPct": int(_pick(rc, lambda x: _val(x, W + "w")) or 100),
            "spacingPct": round(int(_pick(rc, lambda x: _val(x, W + "spacing")) or 0) / 20 / size * 100, 1),
            "align": _ALIGN_IN.get(_pick(pc, lambda x: _val(x, W + "jc")) or "left"),
            "indentLeftMm": round(left_mm, 1), "indentRightMm": round(right_mm, 1), "firstLineMm": round(first_mm, 1),
            "spaceBeforePt": round(space("before"), 1), "spaceAfterPt": round(space("after"), 1), "lineSpacingPct": pct}


def para_summary(doc, p):
    return summary(doc, *_props(p), cell_ctx(doc, p))


CHAR_KEYS = ("font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct", "fontLatin", "script")


def run_looks(doc, p, pieces):
    """spec_서식 §1 `runs` from (text, w:r) pairs: text per character look (same-look neighbours merged), None for
    one look."""
    ppr, out, ctx = p.find(W + "pPr"), [], cell_ctx(doc, p)
    for text, r in pieces:
        if not text:
            continue
        s = summary(doc, ppr, r.find(W + "rPr"), ctx)
        look = {k: s[k] for k in CHAR_KEYS if k in s}
        if out and out[-1]["format"] == look:
            out[-1]["text"] += text
        else:
            out.append({"text": text, "format": look})
    return out if len(out) > 1 else None


# ---- paragraph formats ----------------------------------------------------------------------------------------

def _fmt(doc, ppr, rpr, ctx=None):
    """ctx = 본보기 문단의 표 칸(cell_ctx) — 요약에 표 스타일 모양을 넣는다(토큰 XML 에는 없음: 다른 칸에 입히면 그 칸의 표 스타일이 걸림)."""
    box = etree.Element(W + "fmt", nsmap={"w": W_NS})
    for e in (ppr, rpr):
        if e is not None:
            box.append(_strip(copy.deepcopy(e), *_REVISIONS))
    return {"token": etree.tostring(box, encoding="unicode"),
            "summary": summary(doc, box.find(W + "pPr"), box.find(W + "rPr"), ctx)}


def _parse(doc, fmt):
    try:
        box = etree.fromstring(str(fmt.get("token")), _parser())
    except etree.XMLSyntaxError:
        box = None
    if box is None or box.tag != W + "fmt":
        raise ValueError("not a docx format token")
    if {e.get(W + "val") for e in box.iter(W + "pStyle", W + "rStyle")} - set(doc._styles):
        raise ValueError("format token is not from this document")
    return box.find(W + "pPr"), box.find(W + "rPr")


def get_format(doc, para_id):
    p = _el(doc, para_id, "p")
    return _fmt(doc, *_props(p), cell_ctx(doc, p))


def derive_format(doc, fmt, changes):
    ch = {k: v for k, v in changes.items() if v is not None}  # None = keep (as HwpxDoc)
    if set(ch) - _KEYS:
        raise ValueError(f"unknown format keys: {sorted(set(ch) - _KEYS)}")
    if "color" in ch and not _HEX6.fullmatch(str(ch["color"])):
        raise ValueError("color must be #RRGGBB")
    if "align" in ch and ch["align"] not in _ALIGN_OUT:
        raise ValueError(f"unknown align {ch['align']!r}")
    ppr, rpr = _parse(doc, fmt)
    ppr = ppr if ppr is not None else etree.Element(W + "pPr")
    rpr = rpr if rpr is not None else etree.Element(W + "rPr")
    _set_chars(rpr, ch)
    if "align" in ch:
        _set(ppr, "jc", _PPR, _ALIGN_OUT[ch["align"]])
    ind = {}  # attribute -> value; *Chars / *Lines = 0 so a style's character/line units don't override twips
    if "indentLeftMm" in ch:
        ind.update(left=round(float(ch["indentLeftMm"]) * _TW_MM), leftChars=0, start=None, startChars=None)
    if "indentRightMm" in ch:
        ind.update(right=round(float(ch["indentRightMm"]) * _TW_MM), rightChars=0, end=None, endChars=None)
    if "firstLineMm" in ch:
        tw = round(float(ch["firstLineMm"]) * _TW_MM)
        ind.update(firstLine=None, hanging=None, firstLineChars=None, hangingChars=None)
        ind.update({"hanging": -tw, "hangingChars": 0} if tw < 0 else {"firstLine": tw, "firstLineChars": 0})
    spacing = {}
    for key, side in (("spaceBeforePt", "before"), ("spaceAfterPt", "after")):
        if key in ch:
            spacing.update({side: round(float(ch[key]) * 20), side + "Lines": 0, side + "Autospacing": None})
    if "lineSpacingPct" in ch:
        spacing.update(line=round(float(ch["lineSpacingPct"]) * 2.4), lineRule="auto")
    for tag, attrs in (("spacing", spacing), ("ind", ind)):
        if attrs:
            e = _child(ppr, tag, _PPR)
            for a, v in attrs.items():
                e.attrib.pop(W + a, None) if v is None else e.set(W + a, str(v))
    return _fmt(doc, ppr, rpr)


_CHAR_KEYS = {"font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct"}  # the rPr part of _KEYS


def _set_chars(rpr, ch):
    """Char summary keys of `ch` onto rPr element rpr (in place, direct properties)."""
    if "font" in ch:
        e = _child(rpr, "rFonts", _RPR)
        for a in ("ascii", "hAnsi", "eastAsia"):
            e.attrib.pop(W + a + "Theme", None)
            e.set(W + a, str(ch["font"]))
    if "sizePt" in ch:
        for tag in ("sz", "szCs"):
            _set(rpr, tag, _RPR, str(round(float(ch["sizePt"]) * 2)))
    if "ratioPct" in ch:   # 장평 = w:w %
        v = round(float(ch["ratioPct"]))
        if not 1 <= v <= 600:
            raise ValueError(f"ratioPct 는 1~600: {ch['ratioPct']!r}")
        _set(rpr, "w", _RPR, str(v))
    if "spacingPct" in ch:   # 자간 = w:spacing twips, 글자 크기(바뀐 값 또는 rPr 의 w:sz, 없으면 10pt) 대비 %
        sz = rpr.find(W + "sz")
        size = float(ch["sizePt"]) if "sizePt" in ch else int(sz.get(W + "val")) / 2 if sz is not None and (sz.get(W + "val") or "").isdigit() else 10.0
        _set(rpr, "spacing", _RPR, str(round(float(ch["spacingPct"]) / 100 * size * 20)))
    for key, tag in (("bold", "b"), ("italic", "i")):
        if key in ch:
            _set(rpr, tag, _RPR, "1" if ch[key] else "0")
    if "underline" in ch:
        _set(rpr, "u", _RPR, "single" if ch["underline"] else "none")
    if "color" in ch:
        _set(rpr, "color", _RPR, ch["color"][1:].upper())


def _apply(doc, p, ppr, rpr, keep_numbering, runs=None):
    """Give p the format's pPr and every text run the format's rPr; returns whether p changed.
    keep_numbering: p keeps its own list membership (numId + level), whatever numPr / pStyle the format brings.
    runs: a dict of char keys = each text run keeps its own rPr with just those keys changed (rpr unused)."""
    before, num = etree.tostring(p), doc._num_ref(p)
    old = p.find(W + "pPr")
    new = copy.deepcopy(ppr) if ppr is not None else etree.Element(W + "pPr")
    old_mark = old.find(W + "rPr") if old is not None else None
    if old_mark is not None and any(c.tag in _KEEP_MARK for c in old_mark):
        _keep(old_mark, _child(new, "rPr", _PPR), _KEEP_MARK, _RPR)
    _keep(old, new, _KEEP_P | ({W + "numPr"} if keep_numbering else set()), _PPR)
    _swap(p, old, new)
    if keep_numbering and doc._num_ref(p) != num:  # the format's pStyle numbers differently: pin p's own list
        _number_off(p)
        if num is not None:
            num_pr = p.find(f"{W}pPr/{W}numPr")
            num_pr.clear()
            etree.SubElement(num_pr, W + "ilvl").set(W + "val", str(num[1]))
            etree.SubElement(num_pr, W + "numId").set(W + "val", num[0])
    for r in _runs(p):
        if _has_text(r) or all(c.tag == W + "rPr" for c in r):   # 글 런과 빈 런(글 없는 칸 — 뒤에 칠 글의 모양, 표 서식 정리); 그림·개체 런은 그대로
            old = r.find(W + "rPr")
            if runs is not None:  # the run's own properties, just `runs` keys changed
                new = copy.deepcopy(old) if old is not None else etree.Element(W + "rPr")
                _set_chars(new, runs)
                _swap(r, old, new)
                continue
            new = copy.deepcopy(rpr) if rpr is not None else etree.Element(W + "rPr")
            # a hyperlink run keeps its own character style (link colour/underline) under the format's properties
            keep = _KEEP_R | ({W + "rStyle"} if next(r.iterancestors(W + "hyperlink"), None) is not None else set())
            _keep(old, new, keep, _RPR)
            _swap(r, old, new)
    if runs is not None and not any(_has_text(r) for r in _runs(p)):   # 글 없는 문단: 문단 끝 표식의 글자 모양도(Word 는 빈 문단에 칠 글을 이것으로 그림)
        pp = p.find(W + "pPr")
        if pp is None:
            pp = etree.Element(W + "pPr")
            p.insert(0, pp)
        _set_chars(_child(pp, "rPr", _PPR), runs)
    return etree.tostring(p) != before


def _swap(parent, old, new):
    """Replace parent's first-child property element old (or None) with new, leaving no empty element behind."""
    if old is not None:
        parent.remove(old)
    if len(new) or new.attrib:
        parent.insert(0, new)


def apply_format(doc, para_ids, fmt, keep_numbering=False, runs=None):
    """runs: None = every text run takes fmt's rPr; a dict of char keys = fmt gives the paragraph properties only and
    each text run keeps its own rPr with just those keys changed (spec_서식 ② §3 적용 — 런 강조 보존)."""
    if runs is not None:
        runs = {k: v for k, v in runs.items() if v is not None}
        if bad := set(runs) - _CHAR_KEYS:
            raise ValueError(f"runs takes char keys only: {sorted(bad)}")
        if "color" in runs and not _HEX6.fullmatch(str(runs["color"])):
            raise ValueError("color must be #RRGGBB")
    paras = [_el(doc, i, "p") for i in para_ids]
    ppr, rpr = _parse(doc, fmt)
    changed = [_apply(doc, p, ppr, rpr, keep_numbering, runs) for p in paras]  # every paragraph, no short-circuit
    if any(changed):
        doc._dirty.add(doc._doc)


# ---- table cells ----------------------------------------------------------------------------------------------

def cell_props(doc, tc):
    """Block keys fill / valign / marginsMm of a w:tc (direct tcPr; margins fall back to the table and its style)."""
    pr = tc.find(W + "tcPr")
    shd = next((x.find(W + "shd") for x in [pr, *_table_props(doc, cell_ctx(doc, tc), "tcPr")]  # 칸 직접 → 표 스타일 조건부·전체
                if x is not None and x.find(W + "shd") is not None), None)
    fill = (shd.get(W + "fill") if shd is not None else None) or ""
    tbl_pr = next(tc.iterancestors(W + "tbl")).find(W + "tblPr")
    sid = table_style_id(doc, next(tc.iterancestors(W + "tbl")))
    mars = [pr.find(W + "tcMar") if pr is not None else None,
            tbl_pr.find(W + "tblCellMar") if tbl_pr is not None else None,
            *(s.find(f"{W}tblPr/{W}tblCellMar") for s in doc._chain(sid))]
    margins = {}
    for key, names in _SIDES.items():
        e = next((m.find(W + n) for m in mars if m is not None for n in names if m.find(W + n) is not None), None)
        tw = (108 if key in "lr" else 0) if e is None else 0 if e.get(W + "type") == "nil" else _num(e, "w")
        margins[key] = round(tw / _TW_MM, 1)  # Word's own default: 0.19cm left/right, 0 top/bottom
    return {"fill": "#" + fill.upper() if _HEX6.fullmatch("#" + fill) else None,
            "valign": {"center": "center", "bottom": "bottom"}.get(_val(pr, W + "vAlign"), "top"),
            "marginsMm": margins}


def get_cell_format(doc, cell_id):
    tc = _el(doc, cell_id, "tc")
    paras = list(_kids(tc, (W + "p",)))
    p = next((p for p in paras if _text(p).strip()), paras[0])
    return {"text": _fmt(doc, *_props(p), cell_ctx(doc, p)), **cell_props(doc, tc)}


def apply_cell_format(doc, cell_ids, cell_fmt, parts, keep_numbering=True):
    parts = set(parts)
    if parts - {"text", "fill", "valign", "margins"}:
        raise ValueError(f"unknown parts: {sorted(parts)}")
    fill, valign = cell_fmt.get("fill"), cell_fmt.get("valign")
    if "fill" in parts and fill is not None and not _HEX6.fullmatch(str(fill)):
        raise ValueError("fill must be #RRGGBB or null")
    if "valign" in parts and valign not in ("top", "center", "bottom"):
        raise ValueError("valign must be top, center or bottom")
    cells = [_el(doc, i, "tc") for i in cell_ids]
    text = _parse(doc, cell_fmt["text"]) if "text" in parts else None
    changed = False
    for tc in cells:
        before = etree.tostring(tc)
        if text:
            for p in _kids(tc, (W + "p",)):
                _apply(doc, p, *text, keep_numbering)
        pr = _child(tc, "tcPr", [W + "tcPr"])
        if "fill" in parts:  # explicit "auto" (no fill) also overrides table-style shading
            shd = _child(pr, "shd", _TCPR)
            shd.attrib.clear()
            shd.attrib.update({W + "val": "clear", W + "color": "auto",
                               W + "fill": fill[1:].upper() if fill else "auto"})
        if "valign" in parts:
            _set(pr, "vAlign", _TCPR, valign)
        if "margins" in parts:
            mm = {**cell_props(doc, tc)["marginsMm"], **cell_fmt["marginsMm"]}
            mar = _child(pr, "tcMar", _TCPR)
            for key, names in _SIDES.items():
                for n in names:
                    for e in mar.findall(W + n):
                        mar.remove(e)
                e = _place(mar, etree.Element(W + names[0]), _TCMAR)
                e.attrib.update({W + "w": str(round(float(mm[key]) * _TW_MM)), W + "type": "dxa"})
        if not len(pr) and not pr.attrib:
            tc.remove(pr)
        changed |= etree.tostring(tc) != before
    if changed:
        doc._dirty.add(doc._doc)
