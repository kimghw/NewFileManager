"""Web-view geometry for HWPX blocks (spec_웹UI.md ②): page per section, cell sizes, table/image alignment.

`annotate(doc, blocks)` decorates the blocks() tree in place (HWPUNIT -> mm); the adapter calls it once at the end
of blocks(). Read-only: nothing in the document changes."""
HU_MM = 25.4 / 7200
ALIGN = {"CENTER": "center", "RIGHT": "right"}  # anything else renders left
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
# lineseg textpos counts HWP chars (한글 문서 파일 형식 5.0 표 6): text and char controls 1, inline controls (tab,
# title mark) and extended ones (objects, secPr, every hp:ctrl child) 8, range tags (markpen, 변경 추적) 0.
# Value = (HWP width, length in block text — hwpx_doc SPECIAL).
T_KIDS = {HP + "lineBreak": (1, 1), HP + "hyphen": (1, 1), HP + "nbSpace": (1, 1), HP + "fwSpace": (1, 1),
          HP + "tab": (8, 1), HP + "titleMark": (8, 0)}


def _mm(v):
    return round(int(v or 0) * HU_MM, 2)


def hu(v):
    """A stored size (hp:cellSz / hp:sz width·height) in HWPUNIT. 한글 writes a size that went negative as an unsigned
    32-bit number (실파일 cellSz height="4294967256" = −40 — references/HWPX_포맷.md 「셀 높이」) and lays the row out by
    its other cells and its text, so such a value says nothing: 0, the same as a merged cell's 0."""
    n = int(v or 0)
    return n if 0 <= n < 1 << 31 else 0


def _q(el, tag):
    return el.find(f"{{http://www.hancom.co.kr/hwpml/2011/paragraph}}{tag}")


def page(section_root):
    """Section paper and body margins: {widthMm, heightMm, marginsMm{l,r,t,b}} or None."""
    pp = next(section_root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}pagePr"), None)
    if pp is None:
        return None
    w, h = _mm(pp.get("width")), _mm(pp.get("height"))
    if pp.get("landscape") == "NARROWLY":  # NARROWLY = landscape; width/height stay stored portrait-wise
        w, h = h, w
    m = _q(pp, "margin")
    g = lambda k: _mm(m.get(k)) if m is not None else 0.0
    # header/footer areas sit between the paper margin and the body (한글 편집 용지: 위쪽 + 머리말 = 본문 시작)
    left = g("left") + (g("gutter") if pp.get("gutterType", "LEFT_ONLY") in ("LEFT_ONLY", "LEFT_RIGHT") else 0)
    return {"widthMm": w, "heightMm": h,
            "marginsMm": {"l": round(left, 2), "r": g("right"), "t": round(g("top") + g("header"), 2),
                          "b": round(g("bottom") + g("footer"), 2)}}


def _align(doc, obj):
    """Inline (treatAsChar) objects follow the host paragraph's alignment; floating ones their own horzAlign."""
    pos = _q(obj, "pos")
    if pos is not None and pos.get("treatAsChar") == "0":
        return ALIGN.get(pos.get("horzAlign"), "left")
    host = obj.getparent().getparent()  # hp:run -> hp:p
    pp = doc._defs["paraPr"].get(host.get("paraPrIDRef"))
    a = pp.find("{http://www.hancom.co.kr/hwpml/2011/head}align") if pp is not None else None
    return ALIGN.get(a.get("horizontal") if a is not None else None, "left")


def _u16(s):  # HWP WCHAR and JS string offsets are both UTF-16 units
    return len(s.encode("utf-16-le")) // 2


def lines(doc, p, text):
    """Block-text offsets (UTF-16) where 한글 started a new line — the saved layout cache hp:linesegarray, first
    line excluded ([] = one line). None when the cache is missing (edited paragraph: 한글 recomputes it)."""
    segs = p.findall(f"{HP}linesegarray/{HP}lineseg")
    if len(segs) < 2:
        return [] if segs else None
    at, pos = {}, [0, 0]  # HWP position -> text offset; [HWP, text] cursor

    def put(width, length):
        at.setdefault(pos[0], pos[1])
        pos[0] += width
        pos[1] += length

    def chars(s):
        for ch in s or "":
            put(_u16(ch), _u16(ch))
    for r in p.iterchildren(HP + "run"):
        for c in r:
            if c.tag == HP + "t":
                chars(c.text)
                for k in c:
                    put(*T_KIDS.get(k.tag, (0, 0)))
                    chars(k.tail)
            elif c.tag == HP + "ctrl":  # autoNum (figure/table/equation) shows its number in the block text
                for k in c:
                    put(8, _u16(doc._slot_text(k)) if k.tag == HP + "autoNum" and k in doc._an_val else 0)
            else:  # secPr, tbl, pic, equation, shapes …
                put(8, 0)
    at.setdefault(pos[0], pos[1])
    n = _u16(text)
    return sorted({at[t] for t in (int(s.get("textpos", 0)) for s in segs[1:]) if t in at and 0 < at[t] < n})


def _vert(p):
    v = [int(s.get("vertpos", 0)) for s in p.iterfind(f"{HP}linesegarray/{HP}lineseg")]
    return (v[0], v[-1]) if v else None


def annotate(doc, blocks):
    annotate_pages(doc, blocks)
    _walk(doc, blocks)
    return blocks


def annotate_pages(doc, blocks):
    seen, prev, last_p = set(), None, None
    for b in blocks:  # top level: the first block of each section carries that section's page
        b.pop("pageStart", None)
        el = doc._ids[b["id"]]
        root = el.getroottree().getroot()
        if root not in seen:
            seen.add(root)
            b["page"] = page(root)
            prev, last_p = None, None
        p = el if el.tag == HP + "p" else el.getparent().getparent()  # tbl/pic -> run -> host paragraph
        if p is last_p or p.getparent() is not root:  # captions: their vertpos is inside the caption box
            continue
        v = _vert(p)
        # 한글 쪽 나눔: line top (vertpos, from the page body top) going back up = a new page. After a table the drop
        # may be the table splitting across pages, so it says nothing about the next block.
        # ponytail: multi-column sections (vertpos restarts per column) and breaks inside a paragraph/table are ignored.
        if last_p is not None and (p.get("pageBreak") == "1" or
                                   (prev and v and v[0] < prev[0] and not prev[1])):
            b["pageStart"] = True
        last_p = p
        prev = (v[1], p.find(f"{HP}run/{HP}tbl") is not None) if v else None
    return blocks


def annotate_hosts(doc, blocks):
    """annotate() 의 부분판 — 최상위 문단 몇 개가 낸 블록만(HwpxDoc.host_blocks, 문서 순). 쪽 정보는 annotate_pages 와 같은 규칙을
    그 문단의 **바로 앞 최상위 문단**에서 이어 셈한다(annotate_pages 는 문서 처음부터 훑으며 같은 값을 들고 온다 — 견줌은 tests/test_host_blocks.py)."""
    last_p = None
    for b in blocks:
        el = doc._ids[b["id"]]
        root = el.getroottree().getroot()
        p = el if el.tag == HP + "p" else el.getparent().getparent()
        if p is last_p or p.getparent() is not root:  # 그 문단의 둘째 블록부터(표·그림) · 캡션
            continue
        last_p = p
        q = next(p.itersiblings(HP + "p", preceding=True), None)
        if q is None:  # 구역의 첫 블록 — 그 구역의 쪽 설정
            b["page"] = page(root)
            continue
        v, pv = _vert(p), _vert(q)
        prev = (pv[1], q.find(f"{HP}run/{HP}tbl") is not None) if pv else None
        if p.get("pageBreak") == "1" or (prev and v and v[0] < prev[0] and not prev[1]):
            b["pageStart"] = True
    _walk(doc, blocks)
    return blocks


def _walk(doc, blocks):
    for b in blocks:
        if b["type"] == "paragraph":
            ls = lines(doc, doc._ids[b["id"]], b["text"])
            if ls is not None:
                b["lines"] = ls
        elif b["type"] == "table":
            tbl = doc._ids[b["id"]]
            b["align"] = _align(doc, tbl)
            for c in b["cells"]:
                sz = _q(doc._ids[c["id"]], "cellSz")
                if sz is not None:
                    c["widthMm"], c["heightMm"] = _mm(hu(sz.get("width"))), _mm(hu(sz.get("height")))
                _walk(doc, c.get("blocks") or [])
        elif b["type"] == "image":
            b["align"] = _align(doc, doc._ids[b["id"]])
