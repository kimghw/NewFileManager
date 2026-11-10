"""구조·서식 편집(spec_docx_웹편집 ② §3) — DocxDoc 믹스인 + 실행 취소 묶음 + 서버가 쓰는 최상위 블록 찾기.

hwpx_struct 와 같은 이름·모양(split_para · merge_paras · format_chars · format_para · table_edit · snapshot · restore · top_host · top_ids)이라
서버는 형식으로 모듈만 고른다. 글 위치(offset)는 블록 글 단위 — 탭·강제 줄 바꿈(w:br)·줄 안 붙임표 = 한 글자, SEQ 필드 = 그 표시 번호.
「끊는 자리」의 길이 0 자식(rPr·그림·필드 표지·쪽 나눔 캐시·책갈피)은 언제나 앞쪽에 남는다. docx 의 구역 나누기(pPr/sectPr)는 구역 **마지막**
문단에 있으므로 나누면 뒤 문단으로 옮긴다(hwpx 는 구역 첫 문단 맨 앞 — 앞 문단에 남김).

docx_doc 과 서로 import 한다 — 이 모듈은 함수 안에서만 `D.`(docx_doc) 이름을 쓴다."""
import copy
import io
import zipfile

from lxml import etree

from app.hwpx_struct import CHAR_EDIT, LIMITS, PARA_EDIT, TOGGLES, UNDO_MAX  # noqa: F401 — 같은 항목·한도
from app.table_ops import TABLE_OPS, table_range  # 표 행·열의 형식 중립부(hwpx 와 공용 — 2026-11-10 hwpx_struct 에서 옮김)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
P, R, T, TBL, TC, PPR, RPR = (W + t for t in ("p", "r", "t", "tbl", "tc", "pPr", "rPr"))
ONE_CHAR = {W + "t", W + "tab", W + "br", W + "noBreakHyphen"}  # docx_doc._TEXT_TAGS (w:br 쪽·단 나눔은 0)
# 이 안에서는 끊지 않는다 — 짝·범위가 갈라지거나(변경 추적·콘텐츠 컨트롤·필드) 뜻이 바뀐다. 하이퍼링크·w:dir·w:bdo 는 같은 속성으로 둘로.
NO_CUT = {W + t for t in ("fldSimple", "sdt", "sdtContent", "ins", "del", "moveFrom", "moveTo", "customXml", "smartTag")}
OBJECTS = {W + "drawing", W + "pict", W + "object", MC + "AlternateContent"}
BETWEEN = {W + t for t in ("bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd", "proofErr",
                           "permStart", "permEnd")}  # 문단 사이에 있어도 블록이 아닌 표지
UNIQUE = (W14 + "paraId", W14 + "textId")


def _len(c):
    if c.tag == T:
        return len(c.text or "")
    return int(D._is_text(c)) if c.tag in ONE_CHAR else 0


def _bare(r):
    """rPr 밖 자식이 없는 런."""
    return all(c.tag == RPR for c in r)


def _plain(r):
    return r.tag == R and all(c.tag in (RPR, T) for c in r)


def _put_text(t, text):
    t.text = text
    if text != text.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _split_t(t, k):
    t2 = t.makeelement(T, t.attrib)
    whole = t.text or ""
    _put_text(t, whole[:k])
    _put_text(t2, whole[k:])
    t.addnext(t2)
    return t2


def _split_el(node, i):
    """node 를 i 번째 자식 앞에서 둘로 — 뒤쪽은 같은 태그·속성의 새 요소(런이면 rPr 사본을 맨 앞에)를 바로 뒤에 두고 돌려준다."""
    half = node.makeelement(node.tag, node.attrib)
    if node.tag == R and node.find(RPR) is not None:
        half.append(copy.deepcopy(node.find(RPR)))
    for c in list(node)[i:]:
        half.append(c)
    node.addnext(half)
    return half


def top_host(doc, el):
    """el 이 든 최상위 블록 요소(본문 w:p·w:tbl — sdt·customXml 감싸개는 건너봄). 표 칸 안이면 그 표."""
    best = None
    while el is not None and el.getparent() is not None:
        if el.tag in (P, TBL):
            par = el.getparent()
            while par is not None and par.tag in (W + "sdtContent", W + "sdt", W + "customXml"):
                par = par.getparent()
            if par is doc._body:
                best = el
        el = el.getparent()
    return best


def top_ids(doc, host):
    """host 가 blocks() 최상위에 내는 블록 id — 글 문단(글이 있거나 그림이 없을 때)과 그 그림들, 또는 표(DocxDoc._para_blocks 와 같은 것)."""
    if host.tag == TBL:
        return [doc._rev[host]] if host in doc._rev else []
    pics = [d for d in doc._drawings(host) if d in doc._rev]
    out = [doc._rev[host]] if host in doc._rev and (doc._text(host).strip() or not pics) else []
    return out + [doc._rev[d] for d in pics]


class DocxStructMixin:
    _blocks_cache = None  # 서버 _edit 가 「고치다 만 경우」를 이것으로 본다 — docx 는 블록 캐시가 없어 늘 직전 상태로 되돌린다

    # ---------------------------------------------------------------- 공통
    def _text(self, p):
        """블록 글(DocxDoc._para_blocks 와 같은 것) — SEQ 필드는 마지막 blocks() 가 센 번호."""
        return "".join(D._run_text(x) if kind == "run" else self._seq.get(x["key"], (None, ""))[1]
                       for kind, x in self._slots(p))

    def _para(self, block_id):
        el = self._ids.get(block_id)
        if el is None or el.tag != P:
            raise ValueError(f"{block_id} 는 문단이 아닙니다")
        return el

    def _attached(self, el):
        """el 이 지금 본문 트리 안에 있는지(떼어 낸 요소도 lxml 은 원래 문서에 묶어 두므로 부모를 따라 올라간다)."""
        if el is None:
            return False
        while el.getparent() is not None:
            el = el.getparent()
        return el is self._part(self._doc)

    def _has_object(self, p):
        return next(p.iter(*OBJECTS), None) is not None

    def _sibling(self, p, step):
        q = p.getnext() if step > 0 else p.getprevious()
        while q is not None and (not isinstance(q.tag, str) or q.tag in BETWEEN):
            q = q.getnext() if step > 0 else q.getprevious()
        return q if q is not None and q.tag == P else None

    def _touch_doc(self):
        self._dirty.add(self._doc)

    def font_table(self, blocks=None) -> dict:
        """{언어: {글꼴: {"type": "TTF", "subst": [w:altName]}}} — 블록 서식에 쓰인 글꼴만(spec_docx_웹편집 ② §2, 웹 글꼴 계획 app/fonts.py).
        HANGUL·HANJA·JAPANESE = 동아시아 글꼴(font), LATIN = 영문 글꼴(fontLatin, 없으면 font)."""
        alt = {}
        rel = next((r for r in self._rels.values() if r.get("Type", "").endswith("/fontTable")), None)
        ft = self._part(self._resolve(self._dir, rel.get("Target"))) if rel is not None else None
        for f in ft.iterfind(W + "font") if ft is not None else ():
            a = f.find(W + "altName")
            alt[f.get(W + "name")] = [a.get(W + "val")] if a is not None and a.get(W + "val") else []
        used = {"HANGUL": set(), "LATIN": set()}

        def look(fmt):
            if fmt.get("font"):
                used["HANGUL"].add(fmt["font"])
            if fmt.get("fontLatin") or fmt.get("font"):
                used["LATIN"].add(fmt.get("fontLatin") or fmt["font"])

        def walk(bs):
            for b in bs:
                if b.get("type") == "paragraph":
                    look(b.get("format") or {})
                    for r in b.get("runs") or ():
                        look(r.get("format") or {})
                for c in b.get("cells") or ():
                    walk(c.get("blocks") or [])
        walk(self.blocks() if blocks is None else blocks)
        from app.docx_format import summary
        base = summary(self, None, None).get("font")  # 기본 문단 스타일·문서 기본값의 글꼴 — 이 PC 에 없는 글꼴을 Word 가 대신 쓰는 자리(대개 맑은 고딕)
        out = {}
        for lang in ("HANGUL", "LATIN", "HANJA", "JAPANESE"):
            for face in sorted(used["LATIN" if lang == "LATIN" else "HANGUL"]):
                subst = alt.get(face) or ([base] if base and base != face else [])
                out.setdefault(lang, {})[face] = {"type": "TTF", "subst": subst}
        return out

    # ---------------------------------------------------------------- 끊는 자리
    def _cut(self, p, offset):
        """offset 자리 -> (요소, i) = 그 요소의 i 번째 자식 앞. 지나는 w:t 는 둘로 나눈다. 길이 0 자식은 앞쪽에 남고, SEQ 필드 글 가운데는
        필드 앞으로. 글 뒤(끝)면 (p, len(p))."""
        pos = 0
        for kind, x in self._slots(p):
            if kind == "seq":
                n = len(self._seq.get(x["key"], (None, ""))[1])
                if pos + n <= offset:
                    pos += n
                    continue
                first = x["el"] if x.get("el") is not None else x["runs"][0]
                return first.getparent(), first.getparent().index(first)
            for i, c in enumerate(list(x)):
                n = _len(c)
                if pos + n <= offset:
                    pos += n
                    continue
                if c.tag == T and pos < offset:
                    _split_t(c, offset - pos)
                    return x, i + 1
                return x, i
        return p, len(p)

    def _norm(self, p, node, i):
        """끊는 자리를 위로 올린다 — 요소 맨 앞(런이면 rPr 바로 뒤)·맨 뒤에서 끊는 것은 그 요소 앞·뒤에서 끊는 것과 같다."""
        while node is not p:
            head = 1 if node.tag == R and len(node) and node[0].tag == RPR else 0
            par = node.getparent()
            if i <= head:
                node, i = par, par.index(node)
            elif i >= len(node):
                node, i = par, par.index(node) + 1
            else:
                break
        return node, i

    def _check_cut(self, p, node, i):
        for a in [node, *node.iterancestors()]:
            if a is p:
                break
            if a.tag in NO_CUT:
                raise ValueError("필드·콘텐츠 컨트롤·변경 추적 안에서는 나눌 수 없습니다")
        order = {e: k for k, e in enumerate(p.iter())}
        if i < len(node):
            at = order[node[i]]
        else:
            last = node
            while len(last):
                last = last[-1]
            at = order[last] + 1
        depth = 0
        for f in p.iter(W + "fldChar"):
            if order[f] < at:
                depth += {"begin": 1, "end": -1}.get(f.get(W + "fldCharType"), 0)
        if depth > 0:
            raise ValueError("필드(번호·참조·목차 등) 글 가운데서는 나눌 수 없습니다")

    def _boundary(self, p, offset):
        """offset 자리에 런 경계를 만든다(런을 같은 속성의 두 런으로) — 다른 감싸개는 나누지 않는다."""
        node, i = self._cut(p, offset)
        node, i = self._norm(p, node, i)
        if node.tag == R and node is not p:
            _split_el(node, i)

    def _text_run(self, p, like=None):
        """글 런이 없는 문단에 빈 w:t 런 — 이어 쓸 자리(like 런의 rPr, 없으면 문단 끝 표식 모양)."""
        if any(D._has_text(r) for r in D._runs(p)):
            return
        bare = [r for r in D._runs(p) if _bare(r)]
        if bare:
            etree.SubElement(bare[-1], T)
            return
        r = p.makeelement(R, {})
        src = like.find(RPR) if like is not None else None
        if src is None and p.find(PPR) is not None and p.find(PPR).find(RPR) is not None:
            src = p.find(PPR).find(RPR)
        if src is not None:
            r.append(D._strip(copy.deepcopy(src), "ins", "del", "moveFrom", "moveTo", "rPrChange"))
        etree.SubElement(r, T)
        ppr = p.find(PPR)
        (ppr.addnext(r) if ppr is not None else p.insert(0, r))

    def _tidy(self, p):
        """글 없는 빈 런 빼기(글 런이 따로 있을 때), 같은 rPr 의 이웃 글 런(자식이 rPr·w:t 뿐) 합치기, 런 안 이웃 w:t 합치기."""
        has_text = any(D._has_text(r) for r in D._runs(p))
        for r in list(D._runs(p)):
            if has_text and _bare(r):
                r.getparent().remove(r)
        for par in {r.getparent() for r in D._runs(p)}:
            prev = None
            for r in list(par):
                if not (isinstance(r.tag, str) and _plain(r)):
                    prev = None
                    continue
                if prev is not None and etree.tostring(prev.find(RPR) if prev.find(RPR) is not None else etree.Element(RPR)) == \
                        etree.tostring(r.find(RPR) if r.find(RPR) is not None else etree.Element(RPR)):
                    for c in [c for c in r if c.tag == T]:
                        prev.append(c)
                    par.remove(r)
                else:
                    prev = r
        for r in D._runs(p):
            ts = [c for c in r if c.tag == T]
            for a, b in zip(ts, ts[1:]):
                if a.getnext() is b:
                    _put_text(b, (a.text or "") + (b.text or ""))
                    r.remove(a)

    # ---------------------------------------------------------------- 문단 나누기·합치기
    def split_para(self, block_id: str, offset: int) -> str:
        """문단을 offset 에서 둘로 -> 새(뒤) 문단 id. 앞 문단은 id 를 지키고 구역 나누기는 뒤 문단으로(spec_docx_웹편집 ② §3)."""
        p = self._para(block_id)
        offset = max(0, min(int(offset), len(self._text(p))))
        node, i = self._cut(p, offset)
        node, i = self._norm(p, node, i)
        self._check_cut(p, node, i)
        like = node if node.tag == R else None
        half = None
        while node is not p:  # 끊는 자리를 품은 요소들을 바깥으로 올라가며 둘로
            par = node.getparent()
            half = _split_el(node, i)
            node, i = par, par.index(half)
        q = p.makeelement(P, {k: v for k, v in p.attrib.items() if k not in UNIQUE})
        ppr = p.find(PPR)
        if ppr is not None:
            q.append(D._strip(copy.deepcopy(ppr), "pPrChange", "ins", "del", "moveFrom", "moveTo"))
            sect = ppr.find(W + "sectPr")
            if sect is not None:
                ppr.remove(sect)
        for c in list(p)[max(i, 1 if ppr is not None else 0):]:
            q.append(c)
        if like is None and half is not None and half.tag == R:
            like = half
        if like is None:
            like = next((r for r in reversed(list(D._runs(p))) if r.find(RPR) is not None), None)
        for x in (p, q):
            for r in [r for r in D._runs(x) if _bare(r) and r.getparent() is not None]:  # 끊어 비게 된 런·감싸개
                if any(D._has_text(o) for o in D._runs(x)):
                    par = r.getparent()
                    par.remove(r)
                    while par is not x and len(par) == 0:
                        gp = par.getparent()
                        gp.remove(par)
                        par = gp
            self._text_run(x, like)
        p.addnext(q)
        self._touch_doc()
        return self._id(q, "p")

    def merge_paras(self, block_id: str) -> dict:
        """block_id 문단과 바로 다음 형제 문단을 하나로(뒤 문단의 자식을 앞 문단 끝으로, 문단 모양은 앞 문단 것)
        -> {"id", "offset": 이음 자리, "removed": 지운 문단 id}."""
        p = self._para(block_id)
        q = self._sibling(p, +1)
        if q is None:
            raise ValueError("다음 문단이 없습니다(구역·칸의 마지막 문단이거나 다음이 표)")
        for x in (p, q):
            if self._has_object(x):
                raise ValueError("그림·개체가 든 문단은 합칠 수 없습니다")
        ppr = p.find(PPR)
        if ppr is not None and ppr.find(W + "sectPr") is not None:
            raise ValueError("구역 나누기가 든 문단은 다음 문단과 합칠 수 없습니다(구역이 없어짐)")
        at = len(self._text(p))
        qppr = q.find(PPR)
        sect = qppr.find(W + "sectPr") if qppr is not None else None
        for c in list(q):
            if c is not qppr:
                p.append(c)
        if sect is not None:
            if ppr is None:
                ppr = etree.Element(PPR)
                p.insert(0, ppr)
            from app.docx_format import _PPR, _place
            _place(ppr, sect, _PPR)
        removed = self._rev.get(q)
        q.getparent().remove(q)
        self._tidy(p)
        self._text_run(p)
        self._touch_doc()
        return {"id": block_id, "offset": at, "removed": removed}

    # ---------------------------------------------------------------- 글자 모양
    def format_chars(self, block_id: str, start: int, end: int, changes: dict) -> dict:
        """start..end 글자의 글자 모양 바꾸기(빈 범위 = 문단 전체) -> {"id", "start", "end", "changed": 바뀐 런 수}."""
        from app import docx_format as F
        ch = {k: v for k, v in (changes or {}).items() if v is not None and v != ""}
        if not ch or set(ch) - CHAR_EDIT:
            raise ValueError(f"글자 모양 항목은 {sorted(CHAR_EDIT)} 중에서: {sorted(set(ch) - CHAR_EDIT) or '없음'}")
        if "sizePt" in ch and not LIMITS["sizePt"][0] <= float(ch["sizePt"]) <= LIMITS["sizePt"][1]:
            raise ValueError("sizePt 는 {}~{}".format(*LIMITS["sizePt"]))
        if "color" in ch and not F._HEX6.fullmatch(str(ch["color"])):
            raise ValueError("color 는 #RRGGBB")
        p = self._para(block_id)
        n = len(self._text(p))
        start, end = sorted((max(0, min(int(start), n)), max(0, min(int(end), n))))
        if start == end:
            start, end = 0, n
        self._boundary(p, end)
        self._boundary(p, start)
        sel, pos = [], 0
        for kind, x in self._slots(p):
            runs = [x] if kind == "run" else x["runs"]
            k = len(D._run_text(x)) if kind == "run" else len(self._seq.get(x["key"], (None, ""))[1])
            if k and start <= pos and pos + k <= end:
                sel += runs
            pos += k
        if n == 0:
            sel = list(D._runs(p))
        ppr = p.find(PPR)
        for key in TOGGLES:
            if ch.get(key) == "toggle":
                ch[key] = not (sel and all(F.summary(self, ppr, r.find(RPR), F.cell_ctx(self, p))[key] for r in sel))  # 표 스타일 모양 포함
            elif key in ch:
                ch[key] = bool(ch[key])
        if "sizePt" in ch:
            ch["sizePt"] = float(ch["sizePt"])
        changed = 0
        targets = [r.find(RPR) if r.find(RPR) is not None else r.insert(0, etree.Element(RPR)) or r.find(RPR) for r in sel]
        if not sel:  # 글 런이 없는 빈 문단 — 문단 끝 표식(새로 칠 글의 모양)
            if ppr is None:
                ppr = etree.Element(PPR)
                p.insert(0, ppr)
            targets = [F._child(ppr, "rPr", F._PPR)]
        for rpr in targets:
            before = etree.tostring(rpr)
            F._set_chars(rpr, ch)
            changed += etree.tostring(rpr) != before
        self._tidy(p)
        self._touch_doc()
        return {"id": block_id, "start": start, "end": end, "changed": changed}

    # ---------------------------------------------------------------- 문단 모양
    def format_para(self, block_ids: list[str], changes: dict) -> list[str]:
        """문단 모양(정렬·여백·줄 간격) 바꾸기 — 런마다 글자 모양·번호·구역 나누기는 그대로 -> 바뀐 문단 id."""
        ch = {k: v for k, v in (changes or {}).items() if v is not None and v != ""}
        if not ch or set(ch) - PARA_EDIT:
            raise ValueError(f"문단 모양 항목은 {sorted(PARA_EDIT)} 중에서: {sorted(set(ch) - PARA_EDIT) or '없음'}")
        for k, v in ch.items():
            if k in LIMITS and not LIMITS[k][0] <= float(v) <= LIMITS[k][1]:
                raise ValueError(f"{k} 는 {LIMITS[k][0]}~{LIMITS[k][1]}")
        out = []
        for pid in block_ids:
            p = self._para(pid)
            before = etree.tostring(p.find(PPR)) if p.find(PPR) is not None else b""
            self.apply_format([pid], self.derive_format(self.get_format(pid), ch), keep_numbering=True, runs={})
            if (etree.tostring(p.find(PPR)) if p.find(PPR) is not None else b"") != before:
                out.append(pid)
        if out:
            self._touch_doc()
        return out

    # ---------------------------------------------------------------- 표 행·열
    def _blank_cell(self, tc):
        """칸을 그 자리에서 비운다 — 첫 글 문단(없으면 첫 문단) 모양의 빈 문단 하나."""
        ps = list(D._kids(tc, (P,)))
        tpl = next((p for p in ps if D._text(p).strip()), ps[0] if ps else None)
        new = self._new_para(tpl, "")
        for c in [c for c in tc if c.tag != W + "tcPr"]:
            tc.remove(c)
        tc.append(new)

    def table_edit(self, block_id: str, op: str, rng=None) -> dict:
        """block_id(칸, 또는 칸 안 문단 — 가장 안쪽 칸)이 걸친 행·열 기준 표 편집 -> {"table", "op", ...어댑터 결과}.
        rng = {r0, c0, r1, c1}(격자 좌표) 면 그 칸 대신 끌어 고른 그 범위의 행·열 기준(hwpx_struct.table_range)."""
        if op not in TABLE_OPS:
            raise ValueError(f"표 편집은 {', '.join(TABLE_OPS)} 중 하나")
        tc = self._ids[block_id]
        while tc is not None and tc.tag != TC:
            tc = tc.getparent()
        tbl = next(tc.iterancestors(TBL), None) if tc is not None else None
        if tbl is None or not self._attached(tbl):
            raise ValueError("표 칸 안이 아닙니다")
        tid = self._id(tbl, "t")
        trs, cells, widths = self._tgrid(tbl)
        x = next(c for c in cells if any(t is tc for t in c.rows.values()))
        r0, c0, r1, c1 = x.r, x.c, x.r + x.rs - 1, x.c + x.cs - 1
        nr, nc = len(trs), len(widths)
        r0, c0, r1, c1 = table_range(rng, (r0, c0, r1, c1), nr, nc)
        if op in ("row_above", "row_below"):
            res = self.clone_rows(tid, r0, r1, keep_text=False, above=op == "row_above")
        elif op == "row_delete":
            if r1 - r0 + 1 >= nr:
                raise ValueError("표의 모든 행을 지울 수는 없습니다 — 표째 지우세요")
            res = self.delete_rows(tid, r0, r1)
        elif op == "col_delete":
            if c1 - c0 + 1 >= nc:
                raise ValueError("표의 모든 열을 지울 수는 없습니다 — 표째 지우세요")
            res = self.delete_cols(tid, c0, c1, keep=(c0 - 1, c1) if c0 > 0 else (c0, c1 + 1))  # 지운 폭은 이웃 열에 — 표 폭 그대로
        else:
            res = self.clone_cols(tid, c0, c1, keep=(c0, c1))  # 고른 열과 새 열이 원래 폭을 나눔 — 표 폭 그대로
            for src_id, copy_id in res["map"].items():
                src, cp = self._ids[src_id], self._ids[copy_id]
                if op == "col_left":  # 글(과 문단 id)은 오른쪽(사본 자리)으로, 왼쪽 원래 칸이 빈 새 칸이 된다
                    a = [c for c in src if c.tag != W + "tcPr"]
                    b = [c for c in cp if c.tag != W + "tcPr"]
                    for c in a + b:
                        c.getparent().remove(c)
                    cp.extend(a)
                    src.extend(b)
                    self._blank_cell(src)
                else:
                    self._blank_cell(cp)
        self._touch_doc()
        return {"table": tid, "op": op, **res}


# ---------------------------------------------------------------- 실행 취소 묶음
def snapshot(doc) -> dict:
    """지금 문서 상태 — 저장 바이트·고친 부분·새 바이너리·블록 id 자리표."""
    return {"bytes": doc.save(), "dirty": set(doc._dirty), "blobs": dict(doc._blobs), "ids": doc.id_state()}


def restore(doc_cls, original: bytes, snap: dict):
    """snapshot 을 다시 연 문서 — 기준(_data·_zip)은 원본이라 save()·원본 복원·바이트 동일 판정이 원본 기준으로 계속된다.
    고친 XML 부분은 묶음 바이트에서 먼저 읽어 둔다(기준을 원본으로 바꾸면 거기서 읽으므로)."""
    d = doc_cls(snap["bytes"])
    if snap["bytes"] is not original:
        for name in snap["dirty"]:
            d._part(name)
        d._blobs = dict(snap["blobs"])
        d._data = original
        d._zip = zipfile.ZipFile(io.BytesIO(original))
        d._dirty = set(snap["dirty"])
    if not d.adopt_ids(snap["ids"]):
        raise RuntimeError("실행 취소: 블록 id 자리표가 맞지 않습니다")
    return d


from app import docx_doc as D  # noqa: E402 — 맨 끝: docx_doc 이 이 모듈의 DocxStructMixin 을 먼저 가져간다(어느 쪽을 먼저 import 해도 됨)
