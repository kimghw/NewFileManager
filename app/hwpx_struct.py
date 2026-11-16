"""구조·서식 편집(spec_owpml_편집 ② §2) — HwpxDoc 믹스인 + 실행 취소 묶음.

글 위치(offset)는 HwpxDoc._text(p) 의 글자 단위다(탭 \\t·강제 줄 바꿈 U+2028·고정폭 빈칸 등 = 한 글자, 그림·표 번호 자동 번호 = 그 표시 글).
「끊는 자리」의 길이 0 자식(구역 설정·단 설정 ctrl·표·그림·빈 hp:t·필드 표지 등)은 언제나 **앞쪽**에 남는다 — 그래서 구역 설정은 구역 첫 문단을
떠나지 않고, 글 끝에서 나누면 개체는 앞 문단에 둔 채 빈 새 문단이 생긴다."""
import copy
import io
import zipfile

from lxml import etree

from app.hwpx_format import CHAR_KEYS, _h, _p
from app import table_grid as grid
from app.table_ops import CELL_OPS, TABLE_OPS, cell_op, col_keep, even_spans, table_range  # noqa: F401 — 표 행·열의 형식 중립부(app/table_ops.py 가 원본, 2026-11-10). 옛 이름은 여기서도 보인다.

P, RUN, T, TBL, PIC, TR, TC, SUBLIST, CTRL, LINESEG, CELLADDR, CELLSPAN, SECPR, AUTONUM_EL = map(_p, [
    "p", "run", "t", "tbl", "pic", "tr", "tc", "subList", "ctrl", "linesegarray", "cellAddr", "cellSpan", "secPr", "autoNum"])
ONE_CHAR = frozenset(map(_p, ["tab", "lineBreak", "fwSpace", "nbSpace", "hyphen"]))  # hwpx_doc.SPECIAL 과 같은 것
OBJECTS = frozenset(map(_p, ["tbl", "pic", "ole", "container", "equation", "line", "rect", "ellipse", "arc",
                             "polygon", "curve", "connectLine", "textart", "chart", "video"]))
AUTONUM_TYPES = frozenset(["PICTURE", "TABLE", "EQUATION"])
# 짝을 이루는 표지 — 두 문단으로 갈라지면 짝이 깨진다(형광펜·변경 추적·필드)
MARKERS = frozenset(map(_p, ["markpenBegin", "markpenEnd", "insertBegin", "insertEnd", "deleteBegin", "deleteEnd",
                             "fieldBegin", "fieldEnd"]))
TOGGLES = ("bold", "italic", "underline")
CHAR_EDIT = {"bold", "italic", "underline", "sizePt", "color"}
PARA_EDIT = {"align", "indentLeftMm", "indentRightMm", "firstLineMm", "lineSpacingPct", "spaceBeforePt", "spaceAfterPt"}
LIMITS = {"sizePt": (1, 4096), "lineSpacingPct": (50, 500), "indentLeftMm": (-300, 300), "indentRightMm": (-300, 300),
          "firstLineMm": (-300, 300), "spaceBeforePt": (0, 1000), "spaceAfterPt": (0, 1000)}
UNDO_MAX = 20


# ---------------------------------------------------------------- hp:t 조각
def _atoms(t):
    """hp:t 의 섞인 내용 — 글 조각(str)과 자식 요소를 차례대로(자식 뒤 글 = 다음 조각)."""
    out = [t.text] if t.text else []
    for c in t:
        out.append(c)
        if c.tail:
            out.append(c.tail)
    return out


def _alen(a):
    return len(a) if isinstance(a, str) else int(a.tag in ONE_CHAR)


def _fill(t, atoms):
    for c in list(t):
        t.remove(c)
    t.text, last = None, None
    for a in atoms:
        if isinstance(a, str):
            if last is None:
                t.text = (t.text or "") + a
            else:
                last.tail = (last.tail or "") + a
        else:
            a.tail = None
            t.append(a)
            last = a


def _split_t(t, k):
    """hp:t 를 글자 k 에서 둘로 — 뒤쪽은 같은 속성의 새 hp:t(바로 뒤)."""
    first, second, pos = [], [], 0
    for a in _atoms(t):
        n = _alen(a)
        if pos + n <= k:
            first.append(a)
        elif pos >= k:
            second.append(a)
        else:
            first.append(a[:k - pos])
            second.append(a[k - pos:])
        pos += n
    t2 = t.makeelement(T, t.attrib)
    _fill(t, first)
    _fill(t2, second)
    t.addnext(t2)
    return t2


def top_ids(doc, host):
    """host(최상위 문단)가 blocks() 최상위에 내는 블록 id — 글 문단·표·그림·그 캡션 문단(HwpxDoc._para_blocks 와 같은 것)."""
    out = [doc._rev[host]] if host in doc._rev else []
    for r in host.iterchildren(RUN):
        for o in r.iterchildren(TBL, PIC):
            if o in doc._rev:
                out.append(doc._rev[o])
            out += [doc._rev[p] for c in o.iterchildren(_p("caption")) for s in c.iterchildren(SUBLIST)
                    for p in s.iterchildren(P) if p in doc._rev]
    return out


def top_host(doc, el):
    """el 이 든 최상위 문단(구역 바로 아래 hp:p) — 표 칸 안이면 그 표를 품은 본문 문단."""
    secs = set(doc._sections)
    while el is not None and el.getparent() is not None and el.getparent() not in secs:
        el = el.getparent()
    return el if el is not None and el.getparent() in secs else None


class StructMixin:
    # ---------------------------------------------------------------- 공통
    def _clen(self, c):
        if c.tag == T:
            return len(self._slot_text(c))
        if c.tag == CTRL:
            return sum(len(self._slot_text(a)) for a in c.iterchildren(AUTONUM_EL) if a.get("numType") in AUTONUM_TYPES)
        return 0

    def _attached(self, el):
        """el 이 지금 문서 트리 안에 있는지. getroottree() 로는 못 본다 — lxml 은 떼어 낸 요소도 같은 문서에 묶어 두어
        getroottree().getroot() 가 원래 뿌리를 돌려준다. 부모를 따라 올라간다."""
        if el is None:
            return False
        while el.getparent() is not None:
            el = el.getparent()
        return el in self._name_of

    def _no_markers(self, p):
        if next(p.iter(*MARKERS), None) is not None:
            raise ValueError("형광펜·변경 추적·필드 표지가 든 문단은 나누거나 합칠 수 없습니다(짝이 갈라짐)")

    def _cut(self, p, offset):
        """offset 자리 = (런, i): 그 런의 i 번째 자식 앞. offset 을 지나는 hp:t 는 먼저 둘로 나눈다. 길이 0 자식은 앞쪽에 남는다.
        자동 번호 글 한가운데는 그 앞으로 맞춘다. 런이 없으면 (None, 0)."""
        runs, pos = list(p.iterchildren(RUN)), 0
        for r in runs:
            for i, c in enumerate(list(r)):
                n = self._clen(c)
                if pos + n <= offset:
                    pos += n
                    continue
                if c.tag == T and pos < offset:
                    _split_t(c, offset - pos)
                    return r, i + 1
                return r, i
        return (runs[-1], len(runs[-1])) if runs else (None, 0)

    def _boundary(self, p, offset):
        """offset 자리에 런 경계를 만든다(런을 같은 속성의 두 런으로)."""
        r, i = self._cut(p, offset)
        if r is not None and 0 < i < len(r):
            r2 = r.makeelement(RUN, r.attrib)
            for c in list(r)[i:]:
                r2.append(c)
            r.addnext(r2)

    def _drop_cache(self, p):
        for ls in p.findall(LINESEG):
            p.remove(ls)

    def _tidy(self, p):
        """글 없는 빈 런 빼기(런 하나는 남김), 같은 속성의 이웃 글 런(자식이 hp:t 뿐) 합치기, 런 안 이웃 hp:t 합치기."""
        def plain(r):
            return all(c.tag == T for c in r)

        for r in list(p.iterchildren(RUN)):
            if plain(r) and not any(len(c) or c.text for c in r) and sum(1 for _ in p.iterchildren(RUN)) > 1:
                p.remove(r)
        prev = None
        for r in list(p.iterchildren(RUN)):
            if prev is not None and plain(prev) and plain(r) and dict(prev.attrib) == dict(r.attrib):
                for c in list(r):
                    prev.append(c)
                p.remove(r)
            else:
                prev = r
        for r in p.iterchildren(RUN):
            last = None
            for c in list(r):
                if c.tag == T and last is not None and dict(last.attrib) == dict(c.attrib):
                    _fill(last, _atoms(last) + _atoms(c))
                    r.remove(c)
                else:
                    last = c if c.tag == T else None

    def _sibling(self, p, step):
        q = p.getnext() if step > 0 else p.getprevious()
        while q is not None and not isinstance(q.tag, str):
            q = q.getnext() if step > 0 else q.getprevious()
        return q if q is not None and q.tag == P else None

    # ---------------------------------------------------------------- 문단 나누기·합치기
    def split_para(self, block_id: str, offset: int) -> str:
        """문단을 offset 에서 둘로 -> 새(뒤) 문단 id. 앞 문단은 id·구역 설정을 지킨다(spec_owpml_편집 ② §2)."""
        p = self._para(block_id)
        self._no_markers(p)
        offset = max(0, min(int(offset), len(self._text(p))))
        r, i = self._cut(p, offset)
        new = p.makeelement(P, p.attrib)
        for a in ("pageBreak", "columnBreak"):
            if new.get(a) not in (None, "0"):
                new.set(a, "0")
        if r is None:
            r2 = etree.SubElement(new, RUN, {"charPrIDRef": "0"})
        else:
            later = [x for x in p.iterchildren(RUN) if p.index(x) > p.index(r)]
            r2 = r.makeelement(RUN, r.attrib)
            for c in list(r)[i:]:
                r2.append(c)
            new.append(r2)
            for x in later:
                new.append(x)
            if len(r) == 0 and sum(1 for _ in p.iterchildren(RUN)) > 1:  # 다 옮겨 빈 런은 뺀다(앞에 다른 런이 있을 때)
                p.remove(r)
                r = None
        if next(new.iter(T), None) is None:
            etree.SubElement(r2, T)
        if next(p.iter(T), None) is None:  # 앞 문단이 글 칸 없이 남으면(맨 앞에서 나눔) 빈 hp:t — 이어 쓸 자리
            runs = list(p.iterchildren(RUN))
            run = r if r is not None else runs[-1] if runs else etree.SubElement(p, RUN, {"charPrIDRef": "0"})
            etree.SubElement(run, T)
        self._drop_cache(p)
        p.addnext(new)
        self._touch(p)
        return self._id(new)

    def merge_paras(self, block_id: str) -> dict:
        """block_id 문단과 바로 다음 형제 문단을 하나로(뒤 문단의 런을 앞 문단 끝으로, 문단 모양은 앞 문단 것)
        -> {"id", "offset": 이음 자리, "removed": 지운 문단 id}."""
        p = self._para(block_id)
        q = self._sibling(p, +1)
        if q is None:
            raise ValueError("다음 문단이 없습니다(구역·칸의 마지막 문단)")
        for x in (p, q):
            if self._has_object(x):
                raise ValueError("표·그림 등 개체가 든 문단은 합칠 수 없습니다")
            self._no_markers(x)
        if next(q.iter(SECPR), None) is not None:
            raise ValueError("구역 설정이 든 문단은 앞 문단과 합칠 수 없습니다")
        at = len(self._text(p))
        self._drop_cache(p)
        runs = list(p.iterchildren(RUN))
        anchor = runs[-1] if runs else None
        for r in list(q.iterchildren(RUN)):
            if anchor is None:
                p.insert(0, r)
            else:
                anchor.addnext(r)
            anchor = r
        removed = self._rev.get(q)
        q.getparent().remove(q)
        self._tidy(p)
        self._touch(p)
        return {"id": block_id, "offset": at, "removed": removed}

    # ---------------------------------------------------------------- 글자 모양
    def _char_on(self, r, key):
        c = self._defs["charPr"].get(r.get("charPrIDRef"))
        if c is None:
            return False
        e = c.find(_h(key))
        return e is not None and (key != "underline" or e.get("type", "NONE") != "NONE")

    def format_chars(self, block_id: str, start: int, end: int, changes: dict) -> dict:
        """start..end 글자의 글자 모양 바꾸기(빈 범위 = 문단 전체) -> {"id", "start", "end", "changed": 바뀐 런 수}."""
        ch = {k: v for k, v in (changes or {}).items() if v is not None and v != ""}
        if not ch or set(ch) - CHAR_EDIT:
            raise ValueError(f"글자 모양 항목은 {sorted(CHAR_EDIT)} 중에서: {sorted(set(ch) - CHAR_EDIT) or '없음'}")
        assert CHAR_EDIT <= CHAR_KEYS
        for k in ("sizePt",):
            if k in ch:
                lo, hi = LIMITS[k]
                if not lo <= float(ch[k]) <= hi:
                    raise ValueError(f"{k} 는 {lo}~{hi}")
        p = self._para(block_id)
        n = len(self._text(p))
        start, end = sorted((max(0, min(int(start), n)), max(0, min(int(end), n))))
        if start == end:
            start, end = 0, n
        self._boundary(p, end)
        self._boundary(p, start)
        sel, pos = [], 0
        for r in p.iterchildren(RUN):
            k = sum(self._clen(c) for c in r)
            if not any(c.tag in OBJECTS for c in r) and (k and start <= pos and pos + k <= end or n == 0):
                sel.append(r)
            pos += k
        for key in TOGGLES:
            if ch.get(key) == "toggle":
                ch[key] = not (sel and all(self._char_on(r, key) for r in sel))
            elif key in ch:
                ch[key] = bool(ch[key])
        made, changed = {}, 0
        for r in sel:
            old = r.get("charPrIDRef")
            if old not in made:
                c = copy.deepcopy(self._defs["charPr"].get(old))
                if c is None:
                    raise ValueError(f"글자 모양 {old} 정의가 없습니다")
                self._set_chars(c, ch)
                made[old] = self._add_def("charPr", c)
            if made[old] != old:
                r.set("charPrIDRef", made[old])
                changed += 1
        self._tidy(p)
        self._drop_cache(p)
        self._touch(p)
        return {"id": block_id, "start": start, "end": end, "changed": changed}

    # ---------------------------------------------------------------- 문단 모양
    def format_para(self, block_ids: list[str], changes: dict) -> list[str]:
        """문단 모양(정렬·여백·줄 간격) 바꾸기 — 런마다 글자 모양·문단 번호는 그대로 -> 바뀐 문단 id."""
        ch = {k: v for k, v in (changes or {}).items() if v is not None and v != ""}
        if not ch or set(ch) - PARA_EDIT:
            raise ValueError(f"문단 모양 항목은 {sorted(PARA_EDIT)} 중에서: {sorted(set(ch) - PARA_EDIT) or '없음'}")
        for k, v in ch.items():
            if k in LIMITS and not LIMITS[k][0] <= float(v) <= LIMITS[k][1]:
                raise ValueError(f"{k} 는 {LIMITS[k][0]}~{LIMITS[k][1]}")
        out = []
        for pid in block_ids:
            p = self._para(pid)
            before = p.get("paraPrIDRef")
            self.apply_format([pid], self.derive_format(self.get_format(pid), ch), keep_numbering=True, runs={})
            if p.get("paraPrIDRef") != before:
                out.append(pid)
        return out

    def drop_unused_defs(self, keep: dict) -> int:
        """keep = {정의 종류: 원본 id 집합} 밖이면서 아무 데서도 가리키지 않는 정의(서식 편집이 더했다가 되돌려 안 쓰게 된 것)를
        header 에서 뺀다(itemCnt 갱신) -> 뺀 수. 모두 빠지면 header 가 원본 바이트로 돌아간다."""
        from app.owpml_check import REF_ATTRS
        used = {k: set() for k in self._defs}
        for root in self._roots.values():
            for el in root.iter():
                if isinstance(el.tag, str):
                    for attr, kind in REF_ATTRS.items():
                        if (v := el.get(attr)) is not None and kind in used:
                            used[kind].add(v)
        n = 0
        for kind, defs in self._defs.items():
            for i in [i for i in defs if i not in keep.get(kind, ()) and i not in used[kind]]:
                el = defs.pop(i)
                lst = el.getparent()
                lst.remove(el)
                lst.set("itemCnt", str(len(lst)))
                n += 1
            self._sigs.pop(kind, None)
        if n:
            self._summ.clear()  # 뺀 id 는 다음 새 정의가 다시 쓴다(_add_def = 가장 큰 id + 1) — 옛 id 의 서식 요약이 남으면 새 정의가 옛 모양으로 읽힌다(2026-11-10)
            self._touch(self._reflist)
        return n

    # ---------------------------------------------------------------- 표 행·열
    def _blank_cell(self, tc):
        """칸을 그 자리에서 비운다 — 첫 글 문단(없으면 첫 문단) 모양의 빈 문단 하나."""
        sub = tc.find(SUBLIST)
        ps = list(sub.iterchildren(P))
        tpl = next((p for p in ps if self._text(p).strip()), ps[0] if ps else None)
        p = sub.makeelement(P, tpl.attrib if tpl is not None else {"paraPrIDRef": "0", "styleIDRef": "0"})
        etree.SubElement(p, RUN, {"charPrIDRef": self._char_id(tpl) if tpl is not None else "0"})
        for q in ps:
            sub.remove(q)
        sub.append(p)

    @staticmethod
    def _field_cols(tid, opts):
        """열마다 필드 열인가 — 끝점이 넘긴 판정(opts["fields"]: 표 id → [참/거짓…] | None). 없거나 못 구하면 None(예전 폭 규칙)."""
        fn = opts.get("fields")
        try:
            return fn(tid) if callable(fn) else None
        except (KeyError, ValueError):
            return None

    def table_edit(self, block_id: str, op: str, rng=None, opts=None) -> dict:
        """block_id(칸, 또는 칸 안 문단 — 가장 안쪽 칸)이 걸친 행·열 기준 표 편집 -> {"table", "op", ...어댑터 결과}.
        rng = {r0, c0, r1, c1}(격자 좌표) 면 그 칸 대신 끌어 고른 그 범위의 행·열 기준(table_range).
        opts(spec_owpml_편집 ② §5): `fields` = 표 id → 열마다 필드 열인가(열 폭 규칙 §5-1 — 없으면 예전 규칙) · `rows`·`cols`·`keep`(칸 나누기 §5-2)."""
        if op not in TABLE_OPS:
            raise ValueError(f"표 편집은 {', '.join(TABLE_OPS)} 중 하나")
        opts = opts if isinstance(opts, dict) else {}
        tc = self._ids[block_id]
        while tc is not None and tc.tag != TC:
            tc = tc.getparent()
        if tc is None:
            raise ValueError("표 칸 안이 아닙니다")
        tbl = tc.getparent().getparent()
        tid = self._id(tbl)
        a, s = tc.find(CELLADDR), tc.find(CELLSPAN)
        r0, c0 = int(a.get("rowAddr")), int(a.get("colAddr"))
        r1, c1 = r0 + int(s.get("rowSpan", 1)) - 1, c0 + int(s.get("colSpan", 1)) - 1
        nr, nc = int(tbl.get("rowCnt")), int(tbl.get("colCnt"))
        r0, c0, r1, c1 = table_range(rng, (r0, c0, r1, c1), nr, nc)
        if op in ("row_above", "row_below"):  # 일부만 걸친 합친 칸(바깥 묶음 제목)은 늘어난다 — ② §5-2
            res = self.clone_rows(tid, r0, r1, keep_text=False, above=op == "row_above", lenient=True)
        elif op == "row_delete":
            if r1 - r0 + 1 >= nr:
                raise ValueError("표의 모든 행을 지울 수는 없습니다 — 표째 지우세요")
            res = self.delete_rows(tid, r0, r1, cols=grid.band(self._tgrid(tbl)[1], nc, r0, r1))  # 그 행에서 시작해 아래로 넘어가는 합친 칸은 글째 남고 줄어든다
        elif op in CELL_OPS:
            def inside():
                return [self._id(x.el) for x in sorted(self._tgrid(tbl)[1], key=lambda x: (x.r, x.c))
                        if r0 <= x.r and x.r + x.rs - 1 <= r1 and c0 <= x.c and x.c + x.cs - 1 <= c1]
            res = cell_op(self, tid, op, (r0, c0, r1, c1), opts, inside)
        elif op == "cols_even":  # 열 폭 같게 — 고른 열들, 하나면 그 열을 품은 필드 열 묶음(표 폭·그 밖 열 그대로)
            res = self.even_cols(tid, even_spans(self._tgrid(tbl)[1], nc, self._field_cols(tid, opts), c0, c1))
        elif op == "col_delete":
            if c1 - c0 + 1 >= nc:
                raise ValueError("표의 모든 열을 지울 수는 없습니다 — 표째 지우세요")
            res = self.delete_cols(tid, c0, c1, keep=col_keep(self._field_cols(tid, opts), nc, c0, c1, add=False))  # 표 폭 그대로 — 남은 필드 열이 비율대로(② §5-1)
        else:
            res = self.clone_cols(tid, c0, c1, keep=col_keep(self._field_cols(tid, opts), nc, c0, c1, add=True))  # 표 폭 그대로 — 필드 열 묶음이 비율대로 줄어듦
            for src_id, copy_id in res["map"].items():
                src, cp = self._ids[src_id], self._ids[copy_id]
                if op == "col_left":  # 글(과 문단 id)은 오른쪽(사본 자리)으로, 왼쪽 원래 칸이 빈 새 칸이 된다
                    a_sub, b_sub = src.find(SUBLIST), cp.find(SUBLIST)
                    hold = etree.Element("hold")
                    src.replace(a_sub, hold)
                    cp.replace(b_sub, a_sub)
                    src.replace(hold, b_sub)
                    self._blank_cell(src)
                else:
                    self._blank_cell(cp)
        self._touch(tbl)
        return {"table": tid, "op": op, **res}

    # ---------------------------------------------------------------- 개요(템플릿) 편집용 원시 연산(spec_hwpx_웹편집 ② §8)
    def _put_text(self, run, text):
        """런 끝에 hp:t 하나로 글을 넣는다 — 탭·강제 줄 바꿈·묶음 빈칸(U+2002)은 hp:tab·hp:lineBreak·hp:nbSpace 자식(_text 가 한 글자로 읽는 것과 같은 꼴)."""
        t = etree.SubElement(run, T)
        atoms, buf = [], ""
        for ch in text or "":
            if ch in ("\t", "\u2028", "\u2002"):
                if buf:
                    atoms.append(buf)
                    buf = ""
                atoms.append(t.makeelement(_p("tab" if ch == "\t" else "nbSpace" if ch == "\u2002" else "lineBreak"), {}))
            else:
                buf += ch
        if buf:
            atoms.append(buf)
        _fill(t, atoms)
        return t

    def _first_text_run(self, p):
        return next((r for r in p.iterchildren(RUN) if next(r.iterchildren(T), None) is not None), None)

    @staticmethod
    def _like_attrs(like, attrs):
        """새 문단·접두의 모양 — attrs {paraPrIDRef, styleIDRef, charPrIDRef}(오버레이에 동결한 값)가 있으면 그것, 없으면 like 문단에서."""
        if attrs:
            return {k: str(attrs[k]) for k in ("paraPrIDRef", "styleIDRef") if attrs.get(k) is not None}, str(attrs.get("charPrIDRef", "0"))
        if like is None:
            return {}, None
        return {k: v for k, v in like.attrib.items() if k in ("paraPrIDRef", "styleIDRef")}, None

    def para_attrs(self, block_id: str) -> dict:
        """문단의 모양 참조 {paraPrIDRef, styleIDRef, charPrIDRef(첫 글 런)} — 오버레이에 동결해 두는 값."""
        p = self._para(block_id)
        return {"paraPrIDRef": p.get("paraPrIDRef", "0"), "styleIDRef": p.get("styleIDRef", "0"), "charPrIDRef": self._char_id(p)}

    def is_spacer(self, p) -> bool:
        """순수 간격 문단 — 글·개체·구역 설정·쪽/단 나눔·표지가 없는 빈 문단."""
        return (p.tag == P and not self._text(p).strip() and not self._has_object(p) and next(p.iter(SECPR), None) is None
                and p.get("pageBreak", "0") == "0" and p.get("columnBreak", "0") == "0" and next(p.iter(*MARKERS), None) is None)

    def insert_like(self, ref_id: str, like_id: str | None, text: str, after: bool = True, attrs: dict | None = None) -> str:
        """ref 문단 바로 뒤(앞)에 like 문단 모양(또는 attrs 로 동결한 모양 — 문단 속성 + 글자 모양)의 새 문단 하나(글 = text) -> 새 id.
        쪽·단 나눔은 안 물려받는다. ref 와 like 는 다른 그릇이어도 된다(모양만 빌림)."""
        ref = self._para(ref_id)
        like = self._para(like_id) if like_id else None
        pattrs, cid = self._like_attrs(like, attrs)
        if cid is None:
            cid = self._char_id(like) if like is not None else self._char_id(ref)
        new = ref.makeelement(P, {**ref.attrib, "pageBreak": "0", "columnBreak": "0", **pattrs})  # id·merged 는 ref 꼴(OWPML 필수 속성)
        run = etree.SubElement(new, RUN, {"charPrIDRef": cid})
        self._put_text(run, text)
        if after:
            ref.addnext(new)
        else:
            ref.addprevious(new)
        self._touch(ref)
        return self._id(new)

    def _erase(self, p, start, n):
        """start 부터 n 글자(글 조각·탭·줄 바꿈)를 걷어 낸다 — 길이 0 자식(구역 설정·개체·표지)은 그대로. 비게 된 hp:t 는 _tidy 가 정리."""
        pos, left = 0, n
        for r in list(p.iterchildren(RUN)):
            for c in list(r):
                if left <= 0:
                    return
                if c.tag != T:
                    pos += self._clen(c)
                    continue
                keep = []
                for a in _atoms(c):
                    k = _alen(a)
                    if left <= 0 or pos + k <= start:
                        keep.append(a)
                    elif isinstance(a, str):
                        cut0 = max(0, start - pos)
                        cut1 = min(k, cut0 + left)
                        left -= cut1 - cut0
                        piece = a[:cut0] + a[cut1:]
                        if piece:
                            keep.append(piece)
                    else:  # 탭·줄 바꿈 한 글자
                        left -= 1
                    pos += k
                _fill(c, keep)

    def delete_text(self, block_id: str, start: int, end: int) -> dict:
        """start..end 글자 지우기(고른 글 — 개요 편집과 한 트랜잭션에) -> {"id", "offset": start}."""
        p = self._para(block_id)
        self._no_markers(p)
        n = len(self._text(p))
        start, end = max(0, min(int(start), n)), max(0, min(int(end), n))
        if end > start:
            self._erase(p, start, end - start)
            self._tidy(p)
            self._drop_cache(p)
            self._touch(p)
        return {"id": block_id, "offset": start}

    def set_chars(self, block_id: str, start: int, text: str) -> bool:
        """start 부터 len(text) 글자를 text 로 **글자마다 제 자리에서** 바꾼다 — 길이는 그대로, 런·글자 모양·길이 0 자식(표지·개체)은 안 건드린다. -> 바뀌었는가.
        탭·강제 줄 바꿈·묶음 빈칸(U+2002)은 한 글자 요소(hp:tab·hp:lineBreak·hp:nbSpace)로 쓴다. 레터 뒤 빈칸을 묶음 빈칸으로 바꿀 때 쓴다(outline_conform —
        접두를 통째로 다시 쓰면(replace_prefix) 앞 공백·레터·뒤 빈칸의 글자 모양이 하나로 합쳐진다)."""
        p = self._para(block_id)
        cur, end = self._text(p), start + len(text)
        if start < 0 or end > len(cur):
            raise ValueError("바꿀 글자 범위가 문단 글을 벗어납니다")
        if cur[start:end] == text:
            return False
        kinds = {"\t": "tab", "\u2028": "lineBreak", "\u2002": "nbSpace"}
        pos = 0
        for r in p.iterchildren(RUN):
            for c in list(r):
                n = self._clen(c)
                if c.tag != T or pos + n <= start or pos >= end:
                    pos += n
                    continue
                out = []
                for a in _atoms(c):
                    k = _alen(a)
                    for j in range(k):  # 글 조각은 글자마다 · 한 글자 요소는 그 하나
                        q = pos + j
                        if not start <= q < end or cur[q] == text[q - start]:
                            out.append(a[j] if isinstance(a, str) else a)
                        else:
                            ch = text[q - start]
                            out.append(c.makeelement(_p(kinds[ch]), {}) if ch in kinds else ch)
                    if k == 0:
                        out.append(a)
                    pos += k
                _fill(c, out)
        self._drop_cache(p)
        self._touch(p)
        return True

    def replace_prefix(self, block_id: str, old_len: int, new_prefix: str, like_id: str | None = None, attrs: dict | None = None) -> dict:
        """문단 첫 old_len 글자(접두 = 앞 공백·레터·뒤 공백)를 new_prefix 로. like(또는 attrs)가 있으면 문단 속성(paraPr·style)과 접두의 글자 모양을 그것으로 하고,
        옛 접두와 같은 글자 모양을 쓰던 런(문단 기본 모양을 따르던 글)도 그 글자 모양으로 — 따로 모양을 준 런(강조·색)은 그대로.
        길이 0 자식(구역 설정·개체·표지)은 건드리지 않는다. -> {"id", "offset": 새 접두 끝}."""
        p = self._para(block_id)
        self._no_markers(p)
        old_len = max(0, min(int(old_len), len(self._text(p))))
        first = self._first_text_run(p)
        old_cid = first.get("charPrIDRef") if first is not None else None
        self._erase(p, 0, old_len)
        like = self._para(like_id) if like_id else None
        if like is None and not attrs:
            pattrs, cid = {}, old_cid or "0"
        else:
            pattrs, cid = self._like_attrs(like, attrs)
            if cid is None:
                cid = self._char_id(like)
        for k, v in pattrs.items():
            p.set(k, v)
        if (like is not None or attrs) and old_cid is not None:
            for r in p.iterchildren(RUN):
                if r.get("charPrIDRef") == old_cid and not any(o.tag in OBJECTS for o in r):
                    r.set("charPrIDRef", cid)
        run = p.makeelement(RUN, {"charPrIDRef": cid})
        self._put_text(run, new_prefix)
        anchor = self._first_text_run(p)
        if anchor is not None:
            anchor.addprevious(run)
        else:
            p.append(run)
        self._tidy(p)
        self._drop_cache(p)
        self._touch(p)
        return {"id": block_id, "offset": len(new_prefix)}

    def move_paras(self, first_id: str, last_id: str, ref_id: str, after: bool = True) -> list[str]:
        """first..last(같은 부모 아래 이웃 형제 문단 범위, 문서 순)를 ref 문단 바로 뒤(앞)로 — 같은 그릇(구역·칸) 안에서만. -> 옮긴 문단 id 들."""
        a, b, ref = self._para(first_id), self._para(last_id), self._para(ref_id)
        par = a.getparent()
        if b.getparent() is not par or ref.getparent() is not par:
            raise ValueError("같은 구역·칸 안에서만 옮길 수 있습니다")
        i, j, k = par.index(a), par.index(b), par.index(ref)
        if i > j:
            raise ValueError("옮길 범위의 앞뒤가 바뀌었습니다")
        if i <= k <= j:
            raise ValueError("범위 안으로는 옮길 수 없습니다")
        seg = list(par)[i:j + 1]
        for el in seg:
            if el.tag == P and next(el.iter(SECPR), None) is not None:
                raise ValueError("구역 설정이 든 문단은 옮길 수 없습니다")
        if after:
            anchor = ref
            for el in seg:
                anchor.addnext(el)
                anchor = el
        else:
            for el in seg:
                ref.addprevious(el)
        for el in seg:
            if el.tag == P:
                self._drop_cache(el)
        self._touch(ref)
        return [self._rev[el] for el in seg if el in self._rev]

    def remove_para(self, block_id: str) -> dict:
        """글 문단 하나 지우기(개체·구역 설정·표지가 든 문단과 그릇의 마지막 문단은 거절) -> {"removed", "prev": 앞 형제 id | None, "next"}."""
        p = self._para(block_id)
        if self._has_object(p):
            raise ValueError("표·그림 등 개체가 든 문단은 지울 수 없습니다")
        if next(p.iter(SECPR), None) is not None:
            raise ValueError("구역 설정이 든 문단은 지울 수 없습니다")
        self._no_markers(p)
        prev, nxt = self._sibling(p, -1), self._sibling(p, +1)
        if prev is None and nxt is None:
            raise ValueError("그릇의 하나뿐인 문단은 지울 수 없습니다")
        par = p.getparent()
        par.remove(p)
        self._touch(par)
        return {"removed": self._rev.get(p), "prev": self._rev.get(prev) if prev is not None else None,
                "next": self._rev.get(nxt) if nxt is not None else None}


# ---------------------------------------------------------------- 실행 취소 묶음
def snapshot(doc) -> dict:
    """지금 문서 상태 — 저장 바이트·고친 부분·새 멤버·블록 id 자리표."""
    return {"bytes": doc.save(), "dirty": set(doc._dirty), "new": dict(doc._new_members), "ids": doc.id_state()}


def restore(doc_cls, original: bytes, snap: dict):
    """snapshot 을 다시 연 문서 — 기준(_data·_zip)은 원본이라 save()·원본 복원·바이트 동일 판정이 원본 기준으로 계속된다."""
    d = doc_cls(snap["bytes"])
    if snap["bytes"] is not original:
        d._data = original
        d._zip = zipfile.ZipFile(io.BytesIO(original))
        d._infos = {zi.filename: zi for zi in d._zip.infolist()}
        d._dirty, d._new_members = set(snap["dirty"]), dict(snap["new"])
    if not d.adopt_ids(snap["ids"]):
        raise RuntimeError("실행 취소: 블록 id 자리표가 맞지 않습니다")
    return d
