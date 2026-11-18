"""Web-view geometry for DOCX blocks (spec_웹UI.md ②): page per section, cell sizes, table/image alignment.

`annotate(doc, blocks)` decorates the blocks() tree in place (twips -> mm); the adapter calls it once at the end
of blocks(). Read-only: nothing in the document changes.
NFM(spec_docx_웹편집 ② §2): 표 선(칸 `bf` + 표 `borderFills`, hwpx 와 같은 모양) · 매핑 전 추정 쪽 `pageStart`(Word 쪽 나눔 캐시)."""
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TW_MM = 25.4 / 1440
PT_MM = 25.4 / 72
ALIGN = {"center": "center", "right": "right", "end": "right"}  # anything else renders left
# w:val of a border -> the Hancom line type names app.js already draws (hwpx borderFill)
BORDER = {"single": "SOLID", "thick": "SOLID", "double": "DOUBLE_SLIM", "dashed": "DASH", "dashSmallGap": "DASH",
          "dotted": "DOT", "dotDash": "DASH_DOT", "dotDotDash": "DASH_DOT_DOT", "triple": "DOUBLE_SLIM",
          "thinThickSmallGap": "DOUBLE_SLIM", "thickThinSmallGap": "DOUBLE_SLIM"}
SIDES = {"t": ("top",), "l": ("left", "start"), "b": ("bottom",), "r": ("right", "end")}


def _mm(v):
    return round(abs(int(v or 0)) * TW_MM, 2)


def page(sect):
    """Section paper and body margins: {widthMm, heightMm, marginsMm{l,r,t,b}} or None. pgMar top/bottom already
    measure to the body (the header sits inside them); negative values mean 'fixed' and count by magnitude."""
    size = sect.find(W + "pgSz") if sect is not None else None
    if size is None or not size.get(W + "w"):
        return None
    m = sect.find(W + "pgMar")
    g = lambda k: _mm(m.get(W + k)) if m is not None else 0.0
    out = {"widthMm": _mm(size.get(W + "w")), "heightMm": _mm(size.get(W + "h")),
           "marginsMm": {"l": round(g("left") + g("gutter"), 2), "r": g("right"), "t": g("top"), "b": g("bottom")}}
    t = sect.find(W + "type")  # how this section starts: continuous = same page (web: unless the paper differs — app.js paginate)
    if t is not None and t.get(W + "val") == "continuous":
        out["continuous"] = True
    return out


def _jc(pr):
    jc = pr.find(W + "jc") if pr is not None else None
    return ALIGN.get(jc.get(W + "val") if jc is not None else None, "left")


def _top(doc, el):
    while el.getparent() is not None and el.getparent() is not doc._body:
        el = el.getparent()
    return el


def _on(el):
    return el is not None and el.get(W + "val", "true") not in ("0", "false", "off")


def _starts_page(doc, p):
    """문단이 새 쪽에서 시작하는지(매핑 전 추정) — 쪽 앞 나눔(pageBreakBefore, 스타일 체인 포함) 또는 글보다 앞선 Word 쪽 나눔 캐시
    (w:lastRenderedPageBreak)·쪽 나눔(w:br type=page)."""
    if any(_on(x.find(W + "pageBreakBefore")) for x in [p.find(W + "pPr"), *(s.find(W + "pPr") for s in doc._pchain(p))]
           if x is not None):
        return True
    for e in p.iter(W + "t", W + "tab", W + "drawing", W + "lastRenderedPageBreak", W + "br"):
        if e.tag == W + "lastRenderedPageBreak" or (e.tag == W + "br" and e.get(W + "type") == "page"):
            return True
        if e.tag != W + "t" or (e.text or "").strip():
            return False
    return False


def _ends_page(p):
    """문단 끝(뒤에 글이 없는) 쪽 나눔 — 다음 블록이 새 쪽."""
    tail = False
    for e in p.iter(W + "t", W + "tab", W + "drawing", W + "br"):
        if e.tag == W + "br" and e.get(W + "type") == "page":
            tail = True
        elif e.tag != W + "t" or (e.text or "").strip():
            tail = False
    return tail


def annotate(doc, blocks):
    # a paragraph holding pPr/sectPr ends its section; the body's own sectPr is the last section
    sect_of, start, n = {}, set(), 0
    ends = []
    for el in doc._body:
        sect_of[el] = n
        if el.tag == W + "p" and el.find(f"{W}pPr/{W}sectPr") is not None:
            ends.append(el.find(f"{W}pPr/{W}sectPr"))
            n += 1
    ends.append(doc._body.find(W + "sectPr"))
    prev_top, brk = None, False
    for b in blocks:
        b.pop("pageStart", None)
        top = _top(doc, doc._ids[b["id"]])
        i = sect_of.get(top)
        if i is not None and i not in start:
            start.add(i)
            b["page"] = page(ends[i])
        elif top is not prev_top and prev_top is not None:
            first_p = top if top.tag == W + "p" else next(top.iter(W + "p"), None)
            if brk or (first_p is not None and _starts_page(doc, first_p)):
                b["pageStart"] = True
        if top is not prev_top:
            brk = top.tag == W + "p" and _ends_page(top)
            prev_top = top
    _walk(doc, blocks)
    return blocks


def _line(e):
    """w:top/left/... border element -> {type, widthMm, color} | None(선 없음)."""
    v = e.get(W + "val", "nil")
    if v in ("nil", "none"):
        return None
    color = e.get(W + "color") or "auto"
    sz = int(e.get(W + "sz") or 4) if (e.get(W + "sz") or "4").isdigit() else 4
    return {"type": BORDER.get(v, "SOLID"), "widthMm": round(sz / 8 * PT_MM, 2),
            "color": "#000000" if color.lower() == "auto" or len(color) != 6 else "#" + color.upper()}


def _side(groups, names):
    """첫 번째로 그 쪽 선을 가진 묶음(칸 → 표 → 표 스타일 체인)의 선 — 아무도 없으면 None."""
    for g in groups:
        if g is None:
            continue
        for n in names:
            e = g.find(W + n)
            if e is not None:
                return _line(e)
    return None


def _table_lines(doc, tbl):
    """표의 바깥·안쪽 선 묶음 차례: 표 tblBorders, 표 스타일(없으면 기본 표 스타일) 체인의 tblBorders."""
    pr = tbl.find(W + "tblPr")
    sid = pr.find(W + "tblStyle").get(W + "val") if pr is not None and pr.find(W + "tblStyle") is not None else None
    if sid is None:
        sid = next((k for k, s in doc._styles.items() if s.get(W + "type") == "table"
                    and s.get(W + "default") in ("1", "true", "on")), None)
    return [pr.find(W + "tblBorders") if pr is not None else None,
            *(s.find(f"{W}tblPr/{W}tblBorders") for s in doc._chain(sid))]


def _borders(doc, b, tbl):
    """칸마다 {t,r,b,l} 선 — 칸 tcBorders 가 이기고, 없으면 바깥 칸은 표 top/left/bottom/right, 안쪽은 insideH/insideV."""
    groups = _table_lines(doc, tbl)
    n_rows, n_cols = b.get("nRows") or 0, b.get("nCols") or 0
    keys, out = {}, {}
    for c in b["cells"]:
        tc = doc._ids[c["id"]]
        own = tc.find(f"{W}tcPr/{W}tcBorders")
        edge = {"t": c["row"] == 0, "b": c["row"] + c.get("rowSpan", 1) >= n_rows,
                "l": c["col"] == 0, "r": c["col"] + c.get("colSpan", 1) >= n_cols}
        lines = {}
        for k, names in SIDES.items():
            inner = ("insideH",) if k in "tb" else ("insideV",)
            lines[k] = _side([own], names) if own is not None and any(own.find(W + n) is not None for n in names) \
                else _side(groups, names if edge[k] else inner)
        key = repr(sorted((k, tuple(sorted(v.items())) if v else None) for k, v in lines.items()))
        c["bf"] = keys.setdefault(key, f"b{len(keys) + 1}")
        out[c["bf"]] = lines
    return out


def _walk(doc, blocks):
    for b in blocks:
        el = doc._ids[b["id"]]
        if b["type"] == "table":
            b["align"] = _jc(el.find(W + "tblPr"))
            grid = [int(c.get(W + "w") or 0) for c in el.iterfind(f"{W}tblGrid/{W}gridCol")]
            rows = [tr.find(f"{W}trPr/{W}trHeight") for tr in el.iterchildren(W + "tr")]
            for c in b["cells"]:
                span = grid[c["col"]:c["col"] + c["colSpan"]]
                if len(span) == c["colSpan"] and all(span):
                    c["widthMm"] = round(sum(span) * TW_MM, 2)
                h = rows[c["row"]] if c["row"] < len(rows) else None
                if h is not None and h.get(W + "val"):
                    c["heightMm"] = _mm(h.get(W + "val"))
                _walk(doc, c.get("blocks") or [])
            b["borderFills"] = _borders(doc, b, el)
        elif b["type"] == "image":
            p = next(el.iterancestors(W + "p"), None)
            b["align"] = _jc(p.find(W + "pPr")) if p is not None else "left"
