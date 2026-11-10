"""PDF 매핑(spec_hwpx_웹편집 ② §3·§4) — 웹 블록 ↔ 한글 PDF 글자열·쪽, PDF 쪽 픽셀 비교.

자리 찾기는 FileMergeManager render_anchors.locate 와 같은 생각: 글자·숫자만 남긴 열(key_text)에서 양쪽에 한 번뿐인 긴 글을 고정점으로 잡고
(순서가 맞는 가장 긴 부분열), 나머지는 앞뒤 고정점 사이에서 앞으로만 찾는다. 머리말·꼬리말(위·아래 8% 띠에서 되풀이)과 쪽 번호는 뺀다."""
import bisect
import io
import re
import unicodedata
from collections import Counter

BAND = 0.08
REPEAT = 3
PROBE = 24
FIXED_MIN = 12
DIFF_DPI = 72
DIFF_LEVEL = 40  # 회색조 차이가 이보다 크면 「다른 픽셀」(차이 그림·비율용)


def key_text(text):
    """비교 글자 = NFKC 뒤 글자·숫자만(소문자) — 띄어쓰기·기호·글머리 차이 없이 블록과 PDF 를 맞춘다."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text or "").lower() if ch.isalnum())


# ---- PDF 읽기 -------------------------------------------------------------------------------------

def _halves(pages):
    """2쪽 모아 찍기: 가로 장마다 왼·오른 반을 문서 쪽 둘로(줄은 상자 가운데로 고르고 오른 반은 x 를 반 폭만큼 당김). 마지막 장의 빈 오른 반은 뺀다.
    쪽마다 "sheet" = 그 쪽이 찍힌 PDF 장(0부터). FileMergeManager render_anchors._halves 와 같은 생각."""
    out = []
    for i, p in enumerate(pages):
        if p["w"] <= p["h"]:
            out.append({**p, "sheet": i})
            continue
        mid = p["w"] / 2

        def shift(ln, dx):
            ln = {**ln, "bbox": [ln["bbox"][0] - dx, ln["bbox"][1], ln["bbox"][2] - dx, ln["bbox"][3]]}
            if "chars" in ln:
                ln["chars"] = [(c, x0 - dx, y0, x1 - dx, y1, *rest) for c, x0, y0, x1, y1, *rest in ln["chars"]]
            return ln
        for side in (False, True):
            dx = mid if side else 0
            lines = [shift(ln, dx) for ln in p["lines"] if ((ln["bbox"][0] + ln["bbox"][2]) / 2 >= mid) == side]
            out.append({"w": mid, "h": p["h"], "lines": lines, "sheet": i, "half": int(side), "type3": p.get("type3", set())})
    if len(out) > 1 and out[-1]["sheet"] == out[-2]["sheet"] and not out[-1]["lines"]:
        out.pop()
    return out


def _stroked(page):
    """가짜 굵게(한글 PDF — 글자를 채운 뒤 같은 자리를 한 번 더 긋는다, references/HWPX_렌더링_검증.md)인 글자 자리 {(x, y) 원점 0.1pt}."""
    return {(round(ch[2][0], 1), round(ch[2][1], 1)) for s in page.get_texttrace() if s.get("type") == 1 for ch in s["chars"]}


def _line(blk_no, ln, stroked=None):
    """PyMuPDF 줄 -> {"text", "bbox", "block"} (+ chars=True 면 "chars": [(글자, x0, y0, x1, y1, span 번호, 굵게)], "spans": [(글꼴, 크기, flags, 색)])."""
    if stroked is None:
        return {"text": "".join(s["text"] for s in ln["spans"]), "bbox": list(ln["bbox"]), "block": blk_no}
    chars, spans = [], []
    for s in ln["spans"]:
        si = len(spans)
        spans.append((s["font"], s["size"], s["flags"], s["color"]))
        bold = bool(s["flags"] & 16) or "bold" in s["font"].lower()
        for ch in s["chars"]:
            o = ch["origin"]
            chars.append((ch["c"], *ch["bbox"], si, bold or (round(o[0], 1), round(o[1], 1)) in stroked))
    return {"text": "".join(ch[0] for ch in chars), "bbox": list(ln["bbox"]), "block": blk_no, "chars": chars, "spans": spans}


def read_pdf(path, halves=False, chars=False):
    """-> [{"w", "h", "sheet", "lines": [{"text", "bbox", "block"}]}] — 머리말·꼬리말·쪽 번호를 뺀 본문 줄. halves 면 2쪽 모아 찍기 장을 문서 쪽으로 나눈다.
    chars 면 줄마다 글자 자리·글꼴·크기·굵게(가짜 굵게 포함)도(`_line` — 레터·글꼴 대조, pdf_style)."""
    import fitz
    pages = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            lines = []
            stroked = _stroked(page) if chars else None
            mode = "rawdict" if chars else "dict"
            for bi, blk in enumerate(page.get_text(mode, flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)["blocks"]):
                for ln in blk.get("lines") or []:
                    line = _line(bi, ln, stroked)
                    if line["text"].strip():
                        lines.append(line)
            pages.append({"w": page.rect.width, "h": page.rect.height, "lines": lines, "sheet": i})
            if chars:  # Type3 글꼴(한글 HFT 「T1」 등): 굵게를 글꼴·긋기로 알 수 없다
                pages[-1]["type3"] = {f[3] for f in page.get_fonts() if f[2] == "Type3"} | {f[4] for f in page.get_fonts() if f[2] == "Type3"}
    if halves:
        pages = _halves(pages)

    def band(p, b):
        # 띠 = 긴 변의 8% — 머리말·꼬리말 거리는 용지 방향과 무관한 물리 거리(Word 가로 쪽 h=595 에서 머리말 아래끝 ≈50pt 가 h 기준 47.6pt 띠 밖이었다)
        edge = max(p["w"], p["h"]) * BAND
        return b[3] < edge or b[1] > p["h"] - edge

    sig = lambda ln: re.sub(r"\d+", "#", re.sub(r"\s+", "", ln["text"]))  # noqa: E731
    seen = Counter(s for p in pages for s in {sig(ln) for ln in p["lines"] if band(p, ln["bbox"])})
    for p in pages:
        p["lines"] = [ln for ln in p["lines"] if not (band(p, ln["bbox"]) and (
            seen[sig(ln)] >= REPEAT or re.fullmatch(r"[-–—\s\d/()쪽page]*", ln["text"], re.I)))]
    return pages


def page_count(path):
    import fitz
    with fitz.open(path) as doc:
        return len(doc)


def two_up(path, blocks):
    """한 PDF 장에 문서 두 쪽(2쪽 모아 찍기 — 한글이 문서 인쇄 설정 PrintMethod 를 따름): 문서 첫 구역은 세로인데 PDF 장 대부분이 가로."""
    import fitz
    first = next((b.get("page") for b in blocks if b.get("page")), None)
    if not first or first["widthMm"] >= first["heightMm"]:
        return False
    with fitz.open(path) as doc:
        wide = sum(p.rect.width > p.rect.height for p in doc)
        return wide * 2 > len(doc)


def strict_text(text):
    """기호까지 보는 비교 글 — NFKC 뒤 공백·줄 바꿈만 뺀다(체크 표·부호·소수점은 남김)."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text or "") if not ch.isspace() and ch not in "\u2028\u2029")


def check_texts(texts, pages, located):
    """{id: 글} 이 PDF 에 있는지 — 매핑된 쪽(±1)에서 먼저, 없으면 PDF 전체에서. {"strict": 기호까지 같음, "loose": 글자·숫자만 같음,
    "lost": 못 찾음, "empty": 글이 빔} (id 목록)."""
    page_strict = [strict_text("".join(ln["text"] for ln in p["lines"])) for p in pages]
    page_key = [key_text("".join(ln["text"] for ln in p["lines"])) for p in pages]
    whole_strict, whole_key = "".join(page_strict), "".join(page_key)
    out = {"strict": [], "loose": [], "lost": [], "empty": []}
    for i, t in texts.items():
        st, kt = strict_text(t), key_text(t)
        if not st:
            out["empty"].append(i)
            continue
        pg = located.get(i)
        near = sorted({q for p in pg for q in (p - 1, p, p + 1) if 1 <= q <= len(pages)}) if pg else []
        s_near = "".join(page_strict[q - 1] for q in near)
        k_near = "".join(page_key[q - 1] for q in near)
        if st in s_near or st in whole_strict:
            out["strict"].append(i)
        elif kt and (kt in k_near or kt in whole_key):
            out["loose"].append(i)
        else:
            out["lost"].append(i)
    return out


# ---- 블록 ↔ PDF ----------------------------------------------------------------------------------

def items(blocks):
    """글 있는 문단 블록(최상위·표 칸 안·캡션)을 문서 순서로 — [{"id", "text", "key", "inCell"}]."""
    out = []

    def walk(bs, in_cell):
        for b in bs:
            if b.get("type") == "paragraph":
                k = key_text(b.get("text"))
                if k:
                    out.append({"id": b["id"], "text": b.get("text") or "", "key": k, "inCell": in_cell})
            elif b.get("type") == "table":
                for c in b.get("cells") or []:
                    walk(c.get("blocks") or [], True)
    walk(blocks, False)
    return out


def _stream(pages):
    chars, where = [], []
    for pg, p in enumerate(pages):
        for li, ln in enumerate(p["lines"]):
            k = key_text(ln["text"])
            chars.append(k)
            where += [(pg, li)] * len(k)
    return "".join(chars), where


def _lis(pairs, strict=True):
    """(항목 순번, 자리) 열에서 자리가 늘어나는(strict=False 면 줄지 않는) 가장 긴 부분열."""
    tails, prev, at = [], [None] * len(pairs), []
    for i, (_, pos) in enumerate(pairs):
        k = (bisect.bisect_left if strict else bisect.bisect_right)(tails, pos)
        if k == len(tails):
            tails.append(pos)
            at.append(i)
        else:
            tails[k], at[k] = pos, i
        prev[i] = at[k - 1] if k else None
    out, i = [], at[-1] if at else None
    while i is not None:
        out.append(pairs[i])
        i = prev[i]
    return out[::-1]


def _seq(its, stream, where, lo, hi):
    """글자열 [lo, hi) 안에서 항목들을 순서대로 찾는다 — 양쪽에 한 번뿐인 긴 글을 고정점(순서가 맞는 가장 긴 부분열)으로, 나머지는
    앞 항목 뒤·다음 고정점 앞에서 앞으로만."""
    probes = Counter(it["key"][:PROBE] for it in its if len(it["key"]) >= FIXED_MIN)
    fixed = [(i, pos) for i, it in enumerate(its) if len(it["key"]) >= FIXED_MIN and probes[it["key"][:PROBE]] == 1
             and stream.count(it["key"][:PROBE], lo, hi) == 1 and (pos := stream.find(it["key"][:PROBE], lo, hi)) >= 0]
    fixed = dict(_lis(fixed))
    stops = sorted(fixed)
    cur, nxt = lo, 0
    for i, it in enumerate(its):
        if "pages" in it:
            continue
        k = it["key"]
        while nxt < len(stops) and stops[nxt] <= i:
            nxt += 1
        limit = fixed[stops[nxt]] if nxt < len(stops) else hi
        if i in fixed:
            pos = fixed[i]
        else:
            probe = k[:PROBE]
            pos = stream.find(probe, cur, min(hi, limit + len(probe)))
            if pos < 0 and len(k) >= 2 * PROBE:  # 머리가 다르면(글머리·자동 번호가 글에 섞임) 가운데 조각으로
                mid = len(k) // 2
                hit = stream.find(k[mid:mid + PROBE], cur, min(hi, limit + len(k)))
                pos = hit - mid if hit >= 0 else -1
            if pos < 0:
                continue
            pos = max(pos, cur)
        end = min(pos + len(k), hi if i in fixed else max(min(limit, hi), pos + 1))  # 다음 고정점을 넘지 않게
        if len(k) >= 2 * PROBE:  # PDF 글이 블록보다 짧으면(숨은 글·빈 칸) 끝을 당긴다 — 뒤 항목을 삼키지 않게
            tail = k[-PROBE:]
            hit = stream.find(tail, pos + len(k) // 2, end)
            if hit >= 0:
                end = hit + len(tail)
        if end <= pos:
            continue
        it["pages"] = sorted({where[j][0] + 1 for j in range(pos, end)})
        it["pos"] = pos
        cur = end


def locate(its, pages):
    """항목마다 `pages` = PDF 쪽 번호(1부터) 목록을 붙인다. 못 찾은 항목은 키 없음.

    한글 PDF 는 한 쪽의 본문 글을 먼저, 표 칸 글을 뒤에 쓰는 일이 많아(연구개발계획서 양식 — 표가 다음 본문 문단 글 뒤에 나옴) 문서 순서
    하나로는 표 칸을 놓친다. ① 본문 문단(칸 밖)을 문서 순서대로 찾고 ② 두 본문 문단 사이의 표 칸 묶음은 앞 문단 쪽 ~ 뒤 문단 쪽 범위
    안에서 따로 순서대로 찾고 ③ 남은 것 중 글이 길고 PDF 전체에 한 번뿐인 것은 그 자리로 둔다(떠 있는 표·글상자)."""
    stream, where = _stream(pages)
    starts, k = [], 0
    for p in pages:
        starts.append(k)
        k += sum(len(key_text(ln["text"])) for ln in p["lines"])
    starts.append(k)
    _seq([it for it in its if not it["inCell"]], stream, where, 0, len(stream))
    i = 0
    while i < len(its):
        if not its[i]["inCell"]:
            i += 1
            continue
        j = i
        while j < len(its) and its[j]["inCell"]:
            j += 1
        prev = next((its[x] for x in range(i - 1, -1, -1) if not its[x]["inCell"] and "pages" in its[x]), None)
        nxt = next((its[x] for x in range(j, len(its)) if not its[x]["inCell"] and "pages" in its[x]), None)
        p0 = prev["pages"][-1] if prev else 1
        p1 = nxt["pages"][0] if nxt else len(pages)
        lo, hi = starts[p0 - 1], starts[max(p0, p1)]
        group = its[i:j]
        _seq(group, stream, where, lo, hi)
        # 칸 글 순서가 PDF 와 다른 표(세로 병합 칸·떠 있는 표): 남은 칸은 같은 범위에서 앞 칸 자리에 가장 가까운 것
        near = lo
        for it in group:
            if "pages" in it:
                near = it["pos"]
                continue
            k, hits, x = it["key"], [], stream.find(it["key"], lo, hi)
            while x >= 0 and len(hits) < 200:
                hits.append(x)
                x = stream.find(k, x + 1, hi)
            if hits:
                pos = min(hits, key=lambda h: abs(h - near))
                it["pages"], it["pos"], it["near"] = sorted({where[y][0] + 1 for y in range(pos, pos + len(k))}), pos, True
                near = pos
        i = j
    for it in its:
        k = it["key"]
        if "pages" not in it and len(k) >= 6 and stream.count(k) == 1:
            pos = stream.find(k)
            it["pages"], it["pos"] = sorted({where[x][0] + 1 for x in range(pos, pos + len(k))}), pos
    return its


def map_blocks(blocks, pdf_path, halves=None):
    """웹 블록 → 원본 PDF 문서 쪽. {"total", "located", "ratio", "pages": {id: [쪽]}, "missing": [{id, text}], "pageCount",
    "twoUp", "sheets": [쪽마다 PDF 장 번호], "breaks"·"checks"(paginate)}. 2쪽 모아 찍기면 쪽 = 장의 반(문서 쪽)."""
    return map_detail(blocks, pdf_path, halves)[0]


def map_detail(blocks, pdf_path, halves=None, chars=False):
    """map_blocks 와 같은 매핑 + (PDF 쪽, 항목) — 항목마다 찾았으면 "pos"(글자·숫자 열의 자리). chars 면 쪽 줄에 글자 자리·글꼴도(pdf_style)."""
    if halves is None:
        halves = two_up(pdf_path, blocks)
    pages = read_pdf(pdf_path, halves, chars)
    its = locate(items(blocks), pages)
    found = [it for it in its if "pages" in it]
    located = {it["id"]: it["pages"] for it in found}
    return ({"total": len(its), "located": len(found), "ratio": round(len(found) / len(its), 4) if its else 1.0,
             "pages": located, "missing": [{"id": it["id"], "text": it["text"][:80]} for it in its if "pages" not in it],
             "pageCount": len(pages), "twoUp": halves, "sheets": [p["sheet"] + 1 for p in pages],
             **paginate(blocks, pages, located)}, pages, its)


# ---- 쪽 나눔 -------------------------------------------------------------------------------------

def _paras(bs, out):
    for b in bs:
        if b.get("type") == "paragraph":
            out.append(b)
        for c in b.get("cells") or ():
            _paras(c.get("blocks") or [], out)
    return out


def units(blocks):
    """쪽 나눔 단위(문서 순서): 최상위 블록 하나, 또는 최상위 표의 행 묶음(세로 병합 칸이 걸친 행은 함께 — 그 사이는 못 나눔).
    [{"kind": "block"|"rows", "id", "r0", "r1", "paras": [문단 블록]}]"""
    out = []
    for b in blocks:
        if b.get("type") == "table" and b.get("cells"):
            starts = {}
            for c in b["cells"]:
                starts.setdefault(c["row"], []).append(c)
            n = max([b.get("nRows") or 0] + [c["row"] + c["rowSpan"] for c in b["cells"]])
            r0, reach = 0, 0
            for r in range(n):
                for c in starts.get(r, ()):
                    reach = max(reach, r + c["rowSpan"])
                if reach <= r + 1:
                    out.append(_rows_unit(b, [c for rr in range(r0, r + 1) for c in starts.get(rr, ())], r0, r))
                    r0 = r + 1
            if r0 < n:
                out.append(_rows_unit(b, [c for rr in range(r0, n) for c in starts.get(rr, ())], r0, n - 1))
        else:
            ps = _paras([b], [])
            out.append({"kind": "block", "id": b["id"], "r0": None, "r1": None, "paras": ps, "heads": _first_text(ps)})
    return out


def _first_text(ps):
    return [p for p in ps if (p.get("text") or "").strip()][:1]


def _rows_unit(table, cells, r0, r1):
    """표 행 묶음 단위 — heads = 칸마다 첫 글 문단(쪽 맨 위 줄이 이것들이면 그 행이 이 쪽에서 시작, 칸의 뒤 문단이면 앞 쪽에서 이어진 행)."""
    return {"kind": "rows", "id": table["id"], "r0": r0, "r1": r1,
            "paras": _paras([x for c in cells for x in c.get("blocks") or []], []),
            "heads": [h for c in cells if c["row"] == r0 for h in _first_text(_paras(c.get("blocks") or [], []))]}


TOP_TOL = 2.0  # pt — 쪽 맨 위 줄: 가장 위 줄과 높이가 이만큼 안인 줄들(표 한 행의 칸들)
WINDOW = 8     # 쪽 첫 줄을 찾을 단위 범위: 매핑으로 정한 나눔 앞뒤 이만큼


def _tops(page):
    """쪽 맨 위 본문 줄들의 키(2자 이상) — 같은 높이의 칸 글들 모두."""
    ls = [ln for ln in page["lines"] if key_text(ln["text"])]
    if not ls:
        return [], ""
    y = min(ln["bbox"][1] for ln in ls)
    top = sorted((ln for ln in ls if ln["bbox"][1] <= y + TOP_TOL), key=lambda ln: ln["bbox"][0])
    return [k for ln in top if len(k := key_text(ln["text"])) >= 2], " ".join(ln["text"].strip() for ln in top)


def paginate(blocks, pages, located):
    """웹 쪽 나눔 = 각 쪽이 시작하는 단위. ① 단위의 쪽 = 그 안 문단들이 찍힌 가장 앞 쪽, 순서가 맞는 가장 긴 부분열만 믿는다(잘못 잡힌 짧은 칸 글이
    쪽을 앞으로 당기지 않게) ② 쪽마다 PDF 맨 위 줄의 글이 든 단위를 매핑 나눔 앞뒤 WINDOW 안에서 찾아 나눔을 맞추고 대조 결과를 남긴다.
    -> {"breaks": [{"page", "kind", "id", "row"}], "checks": [{"page", "status", "top", "unit"}]}
    status: ok(맨 위 줄이 그 쪽 첫 단위에 있음) · moved(맨 위 줄로 나눔을 옮김) · split(맨 위 줄이 앞 쪽에서 이어진 문단·표 행 — 웹은 그 뒤에서 나눔)
            · miss(맨 위 줄을 근처 단위에서 못 찾음 — 매핑 나눔 그대로) · none(이 쪽에서 시작하는 단위 없음) · blank(쪽에 글 없음)."""
    us = units(blocks)
    keys = [[key_text(p.get("text")) for p in u["paras"]] for u in us]
    heads = [[key_text(p.get("text")) for p in u["heads"]] for u in us]
    # 자동 번호 문단: 번호(list.label)는 블록 글에 없고 PDF 줄에는 있다 — 「1.」+「서론」 = 맨 위 줄 「1. 서론」 전체와 같으면 길이와 무관하게 바로 시작
    labs = [[key_text(((p.get("list") or {}).get("label") or "") + (p.get("text") or "")) if (p.get("list") or {}).get("label") else ""
             for p in u["heads"]] for u in us]
    raw = [sorted({pg for p in u["paras"] for pg in located.get(p["id"], ())}) for u in us]
    seq = [(k, r[0]) for k, r in enumerate(raw) if r]
    trusted = dict(_lis(seq, strict=False))
    start, cur = {}, 0
    for k in range(len(us)):
        p = trusted.get(k)
        if p and p > cur:
            start[p], cur = k, p
    start.setdefault(1, 0)

    def text_of(k):
        return next((p.get("text") for p in us[k]["paras"] if (p.get("text") or "").strip()), "") if k is not None and 0 <= k < len(us) else ""

    def starts_with(x, t):
        # 쪽 맨 위 줄 = 그 문단의 첫 줄: 문단 키가 줄 키로 시작(또는 짧은 칸 글이면 줄 키가 문단 키로 시작). 줄 앞 몇 글자는 자동 번호(「1.」)일 수 있다.
        # 짧은 칸 글(「3」·「2」)이 긴 줄(「3. 연구개발과제의…」)의 머리와 우연히 같은 것은 빼다 — 줄 키의 6할 이상·4자 이상일 때만
        # 세기: 2 = 문단이 줄 글로 바로 시작, 1 = 짧은 칸 글이 줄 머리이거나 줄 앞 자동 번호를 건너 맞음(「5.」 + 「연구개발성과…」), 0 = 아님
        if x.startswith(t):
            return 2
        at = t.find(x[:12]) if len(x) >= 4 else -1
        label = 0 < at <= 3 and (t[:at].isdigit() or at == 1)  # 건너뛰는 앞 글은 번호꼴만(「1」「12」「가」) — 문장 끝 「였다」는 아님(HAZID 21쪽)
        return 1 if (len(x) >= max(4, 0.6 * len(t)) and t.startswith(x)) or label else 0

    def strength(k, t):
        best = 0
        for x, lab in zip(heads[k], labs[k]):
            if lab and lab == t:
                return 2
            if x:
                best = max(best, starts_with(x, t))
        return best

    def score(k, tops):
        """맨 위 줄 글마다 이 단위 첫 문단 첫머리와 맞춘 세기의 합."""
        return sum(strength(k, t) for t in tops) if 0 <= k < len(us) else 0

    def match(k, tops):
        """'start' = 맨 위 줄 글의 절반 이상이 이 단위의 첫 문단(표 행이면 칸마다 첫 글 문단) 첫머리, 'inside' = 그 밖 문단에 있음(앞 쪽에서
        이어진 문단·칸), None. 절반 — 머리 표처럼 아래 행 칸이 같은 높이에 함께 잡히는 쪽(연구개발계획서 양식 8쪽: 「[ ] 일반형」·「[ ] 통합형」…
        사이에 다음 행 칸 하나)이 통째로 「이어짐」으로 몰리지 않게."""
        if not 0 <= k < len(us):
            return None
        ks = [x for x in keys[k] if x]
        n = sum(strength(k, t) > 0 for t in tops)
        if n and n * 2 >= len(tops):
            return "start"
        return "inside" if any(t in x for t in tops for x in ks) else None

    def rows_of(page):
        """쪽의 줄을 같은 높이(TOP_TOL) 무리로 — 표 한 행의 칸 글이 한 무리. [[키]]"""
        out, last = [], None
        for ln in sorted(page["lines"], key=lambda ln: ln["bbox"][1]):
            k = key_text(ln["text"])
            if not k:
                continue
            if last is None or ln["bbox"][1] > last + TOP_TOL:
                out.append([])
                last = ln["bbox"][1]
            out[-1].append(k)
        return out

    page_rows = [rows_of(p) for p in pages]
    # 문서 블록에 있는 모든 글(번호 붙인 키 포함) — 쪽 맨 위 줄이 여기 없으면 글상자·그리기 개체·머리말처럼 웹 블록에 없는 글이다
    doc_text = "|".join([x for row in keys for x in row if x] + [x for row in labs for x in row if x])

    def in_doc(ts):
        return any(t in doc_text for t in ts)
    breaks, checks, prev, prev_page = {1: 0}, [], 0, 1
    for pg in range(2, len(pages) + 1):
        tops, top_text = _tops(pages[pg - 1])
        first_row = 0
        if tops and not in_doc(tops):
            # 맨 위 줄이 웹 블록에 없는 글(AIP 신청서식 왼쪽 글상자 라벨 「AIP 신청 개발품의 명칭」) — 그 아래 행 무리 가운데 블록에 있는 첫 무리로 대조
            for i, row in enumerate(page_rows[pg - 1][1:4], 1):
                ts = [t for t in row if len(t) >= 2]
                if ts and in_doc(ts):
                    tops, first_row, top_text = ts, i, f"(블록에 없는 「{top_text[:20]}」 건너뜀) " + " ".join(ts)
                    break
        k0 = start.get(pg)
        if not tops:
            checks.append({"page": pg, "status": "blank" if not top_text else "short", "top": top_text, "unit": text_of(k0) if k0 is not None else ""})
            if k0 is not None and k0 > prev:
                breaks[pg], prev, prev_page = k0, k0, pg
            continue
        # 찾는 범위: 앞 쪽을 시작한 단위부터, 매핑으로 이 쪽 뒤에 확실히 있는 단위(+WINDOW)까지
        limit = next((k for k in range(prev + 1, len(us)) if trusted.get(k, 0) > pg), len(us))
        span = range(prev, min(len(us), max(limit, k0 or 0) + WINDOW + 1))
        starts = [k for k in span if match(k, tops) == "start"]
        best = max((score(k, tops) for k in starts), default=0)
        starts = [k for k in starts if score(k, tops) == best]  # 맨 위 줄 글을 가장 많이 맞춘 단위만(「일련」만 같은 다른 일정표는 빼다)
        # 이어진 단위: 맨 위 줄이 단위의 첫 문단이 아닌 곳에 있음 — 매핑이 이 쪽 시작으로 잡은 단위(k0) 자신도(세로 병합 행 묶음이 앞 쪽에서 시작한 경우)
        insides = [k for k in span if k <= (k0 if k0 is not None else limit - 1) and match(k, tops) == "inside"]
        # 같은 글의 표·제목이 되풀이되는 문서(같은 칸의 일정표 여러 개): 앞 쪽(앞 나눔 쪽 ~ 이 쪽 앞)의 PDF 글에 맨 위 줄 글이 몇 번 나왔는지 세어
        # 그다음 것을 고른다 — 가장 긴 맨 위 키로 센다
        # 맨 위 줄 무리와 같은 **행**(같은 높이에 맨 위 줄 글이 모두 줄머리로 있음)만 센다 — 문장·제목 속에 든 같은 글(「부록 IV. 안전조치기록부
        # (SAFETY ACTION LOG)」, 「…구체적인 내용…」)이나 칸 하나만 같은 행은 그 표 머리가 아니다
        seen = sum(all(any(x.startswith(t) for x in row) for t in tops) for q in range(prev_page, pg) for row in page_rows[q - 1])
        before = [k for k in starts if k < limit]
        # 후보는 매핑으로 이 쪽 뒤에 있는 단위 앞까지만 — 같은 머리 행의 다음 표가 범위(WINDOW) 안에 있어도 고르지 않게(HAZID 28쪽 Node 1 표 ↔ 29쪽 Node 2 표)
        starts = before or starts
        # 앞 쪽에 그 글로 시작하는 줄이 후보 수만큼 이미 나왔으면 이 맨 위 줄은 **되풀이**(Word·한글이 쪽마다 표 머리 행을 다시 찍음) — 그 머리 행의 표에서
        # 이 쪽에 처음 찍힌 행부터 나눈다(HAZID 보고서 42쪽 「No. Name Company…」, 연구개발계획서 양식 44쪽 「20××년」). 같은 글의 표가 여럿이면 센 수가 후보
        # 수보다 작아 다음 후보를 고른다(연구개발계획서 양식 31쪽 「구분 구체적인 내용」 표 2개).
        repeat = bool(starts) and seen >= len(starts)
        hit = starts[seen] if seen < len(starts) else (before[-1] if before else None)
        if not repeat and hit is not None and us[hit]["kind"] == "rows" and us[hit]["r0"] == 0 and raw[hit] and raw[hit][-1] < pg:
            # 앞 쪽 행 무리가 높이가 달라 위 셈에 안 잡힌 두 줄 머리 행(HAZID 28쪽 「Hazard … RI RI RI」): 매핑이 머리 행과 그 표의 다음 행까지 앞 쪽에 두었으면 되풀이
            tid = us[hit]["id"]
            nxt_row = next((j for j in range(hit + 1, len(us)) if us[j]["id"] == tid and raw[j]), None)
            repeat = nxt_row is not None and raw[nxt_row][0] < pg
        if hit is not None and hit <= prev and not repeat:
            hit = next((k for k in starts if k > prev), None)
        if repeat and hit is not None and us[hit]["kind"] == "rows":
            # 이 쪽에서 시작하는 행 = 되풀이 머리 아래 첫 행 무리(PDF 둘째 행)의 글이 첫머리인 그 표의 행 — 글로 못 찾으면 매핑(이 쪽 이상에 찍힌 첫 행)
            tid = us[hit]["id"]
            cands = []
            for j in range(max(hit, prev) + 1, len(us)):
                if us[j]["id"] != tid:
                    break
                cands.append(j)
            second = [t for t in (page_rows[pg - 1][first_row + 1] if len(page_rows[pg - 1]) > first_row + 1 else []) if len(t) >= 2]
            by_text = [j for j in cands if second and sum(strength(j, t) > 0 for t in second) * 2 >= len(second)]
            nxt = by_text[0] if by_text else next((j for j in cands if raw[j] and raw[j][0] >= pg), None)
            status, k = "repeat", (nxt if nxt is not None else (k0 if k0 is not None and k0 > prev else None))
        elif hit is not None and hit > prev:
            status, k = ("ok" if hit == k0 else "moved"), hit
        elif insides:
            # 맨 위 줄은 앞 쪽에서 이어진 문단·표 행 — 그 다음 단위부터 이 쪽(그 단위가 이 쪽보다 뒤에서 시작하면 나눔 없음)
            inside = insides[-1]
            nxt = inside + 1
            status, k = "split", (nxt if nxt < len(us) and not (raw[nxt] and raw[nxt][0] > pg) else None)
        else:
            status, k = ("miss" if k0 is not None else "none"), k0
        if k is not None and k > prev:
            breaks[pg], prev, prev_page = k, k, pg
        checks.append({"page": pg, "status": status, "top": top_text[:60], "unit": text_of(k if k is not None else k0)[:60]})
    out = []
    for pg, k in sorted(breaks.items()):
        u = us[k]
        out.append({"page": pg, "kind": u["kind"], "id": u["id"], "row": u["r0"]})
    # 독립 대조: 웹에서 문단이 놓인 쪽이 PDF 에서 찾은 그 문단의 쪽(들) 가운데 하나인지 — 쪽 나눔이 문단 위치와 얼마나 맞는지
    at, cur, agree, total = sorted((k, pg) for pg, k in breaks.items()), 1, 0, 0
    nxt = iter(at)
    pending = next(nxt, None)
    for k, u in enumerate(us):
        while pending is not None and pending[0] <= k:
            cur, pending = pending[1], next(nxt, None)
        for p in u["paras"]:
            if p["id"] in located:
                total += 1
                agree += cur in located[p["id"]]
    return {"breaks": out, "checks": checks, "agree": round(agree / total, 4) if total else 1.0,
            "pageStatus": {c["page"]: c["status"] for c in checks if c["status"] != "ok"}}


# ---- 쪽 그림·픽셀 비교 -----------------------------------------------------------------------------

def _gray(page, dpi):
    import fitz
    import numpy as np
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)


MINOR_PT = 1.0  # 줄 상자가 이만큼(pt) 안에서만 움직였으면 「미세 차이」


def _page_lines(page):
    import fitz
    out = []
    for blk in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        for ln in blk.get("lines") or []:
            t = strict_text("".join(s["text"] for s in ln["spans"]))
            if t:
                out.append((t, ln["bbox"]))
    return out


def _images(page):
    return sorted((i.get("digest") or b"", tuple(round(v) for v in i["bbox"])) for i in page.get_image_info(hashes=True))


def _minor(pa, pb):
    """글(기호 포함)이 같고 줄마다 자리가 MINOR_PT 안이며 그림(바이트 해시·자리)도 같으면 True — 한글이 줄 캐시를 다시 계산하며 글자 자리가
    픽셀 아래로 흔들린 차이로 본다. 선·도형 같은 벡터 그림의 변화는 이 판정으로 알 수 없다(눈으로 확인 — 비교 창)."""
    la, lb = _page_lines(pa), _page_lines(pb)
    if len(la) != len(lb) or any(x[0] != y[0] for x, y in zip(la, lb)):
        return False
    if not all(abs(u - v) <= MINOR_PT for x, y in zip(la, lb) for u, v in zip(x[1], y[1])):
        return False
    return _images(pa) == _images(pb)


def compare_pdfs(a, b, dpi=DIFF_DPI):
    """두 PDF 를 쪽마다 픽셀 비교 — {"pagesA", "pagesB", "diff": [{"page", "ratio", "minor"}]} (쪽은 1부터, 한쪽에만 있는 쪽도 차이).
    minor = 글·줄 자리가 같고 글자 가장자리 픽셀만 다른 쪽."""
    import fitz
    import numpy as np
    out = []
    with fitz.open(a) as da, fitz.open(b) as db:
        for i in range(max(len(da), len(db))):
            if i >= len(da) or i >= len(db):
                out.append({"page": i + 1, "ratio": 1.0, "minor": False})
                continue
            x, y = _gray(da[i], dpi), _gray(db[i], dpi)
            if x.shape != y.shape:
                out.append({"page": i + 1, "ratio": 1.0, "minor": False})
            elif not np.array_equal(x, y):
                d = np.abs(x.astype(np.int16) - y.astype(np.int16)) > DIFF_LEVEL
                out.append({"page": i + 1, "ratio": round(float(d.mean()), 5), "minor": _minor(da[i], db[i])})
        return {"pagesA": len(da), "pagesB": len(db), "diff": out}


def page_png(pdf, page, dpi=110):
    """PDF 한 쪽(1부터) → PNG 바이트. 없는 쪽은 None."""
    import fitz
    with fitz.open(pdf) as doc:
        if not 1 <= page <= len(doc):
            return None
        return doc[page - 1].get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def diff_png(a, b, page, dpi=110):
    """두 PDF 의 같은 쪽 차이 그림 — 원본을 옅게 깔고 달라진 픽셀을 빨강(원본에만)·파랑(수정본에만)으로."""
    import fitz
    import numpy as np
    from PIL import Image
    with fitz.open(a) as da, fitz.open(b) as db:
        xa = _gray(da[page - 1], dpi) if 1 <= page <= len(da) else None
        xb = _gray(db[page - 1], dpi) if 1 <= page <= len(db) else None
    if xa is None and xb is None:
        return None
    h = max(v.shape[0] for v in (xa, xb) if v is not None)
    w = max(v.shape[1] for v in (xa, xb) if v is not None)

    def pad(v):
        out = np.full((h, w), 255, np.uint8)
        if v is not None:
            out[:v.shape[0], :v.shape[1]] = v
        return out
    xa, xb = pad(xa), pad(xb)
    base = (255 - (255 - np.minimum(xa, xb)) * 0.25).astype(np.uint8)
    rgb = np.stack([base] * 3, axis=-1)
    d = xb.astype(np.int16) - xa.astype(np.int16)
    only_a, only_b = d > DIFF_LEVEL, d < -DIFF_LEVEL  # 원본 쪽이 더 진함(지워진 잉크) / 수정본 쪽이 더 진함(새 잉크)
    rgb[only_a] = (220, 38, 38)
    rgb[only_b] = (37, 99, 235)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "PNG")
    return buf.getvalue()
