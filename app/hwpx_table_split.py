"""표 나누기 · 다시 합치기 — HwpxDoc 믹스인(spec_owpml_편집 ② §5-3). 표 모듈의 hwpx 어댑터.

- `split_table(tid, hc, cut)`: 표를 열 cut 에서 둘로 — 앞 표 = 열 0..cut-1, 뒤 표(바로 뒤 새 문단) = 헤더 열 0..hc-1 + 열 cut..끝. 두 표 모두 원래 폭(필드 열이 비율대로 넓어짐).
- `join_tables(first, second, hc)`: 뒤 표의 필드 열(hc..끝)을 앞 표 오른쪽에 붙이고 뒤 표를 지운다 — 칸 요소를 옮긴다(칸·문단 id 그대로).
- `split_partner(tid, hc, forward)`: 이어진 표 — 바로 다음(앞) 문단의 표가 행 수가 같고 헤더 열의 칸 자리·글이 같으면 그 표.
헤더 열 수·필드 열 단위는 `app/table_heads.py`·`table_grid.col_units` 가 정한다. 끝점은 `app/tables_api.py` `POST …/tables/{tid}/split`(트랜잭션 `server._edit`)."""
import copy

from app import table_grid as grid
from app.hwpx_format import _h, _p

P, RUN, TBL, PIC, SUBLIST = map(_p, ["p", "run", "tbl", "pic", "subList"])
BF = "borderFillIDRef"
CUT_BAD = "나눌 자리는 헤더 열 뒤 · 마지막 열 앞이어야 합니다"
CUT_CROSS = "그 자리는 합친 칸을 가릅니다 — 필드 열 단위의 경계에서 나누세요"
JOIN_DIFF = "두 표의 행 구조나 헤더 열이 달라 한 표로 합칠 수 없습니다"
BLANK_BETWEEN = 2  # 짝 사이에 건너뛰는 빈 문단 수


class TableSplitMixin:
    def _line_from(self, bf_id, side, src_bf_id, src_side):
        """borderFill bf_id 의 한 변(side — leftBorder·rightBorder…)을 src 정의의 src_side 선으로 바꾼 정의의 id. 이미 같거나 정의가 없으면 bf_id 그대로."""
        a, b = self._defs["borderFill"].get(bf_id), self._defs["borderFill"].get(src_bf_id)
        if a is None or b is None:
            return bf_id
        old, line = a.find(_h(side)), b.find(_h(src_side))
        if old is None or line is None or dict(old.attrib) == dict(line.attrib):
            return bf_id
        new = copy.deepcopy(a)
        tgt = new.find(_h(side))
        tgt.attrib.clear()
        tgt.attrib.update(line.attrib)
        return self._add_def("borderFill", new)

    def split_table(self, table_id: str, hc: int, cut: int) -> dict:
        """표를 열 cut 에서 둘로. 헤더 열(0..hc-1)은 두 표에 똑같이, 뒤 표는 표만 든 새 문단(쪽 나눔 속성 끔)으로 바로 뒤에. 두 표 모두 원래 표 폭 —
        남은 필드 열이 비율대로 넓어진다. 앞 표의 새 오른쪽 변은 원래 오른쪽 변의 선을 물려받는다. ValueError: 자리가 틀렸거나 헤더 열 뒤에서 시작하는 칸을 가름.
        -> {"table": 앞 표 id, "new": 뒤 표 id, "map": {원래 블록 id: 뒤 표 사본의 id}}."""
        tbl, cells, _nr, nc = self._tgrid(self._ids.get(table_id))
        hc, cut = int(hc), int(cut)
        if not 0 < hc < cut < nc:
            raise ValueError(CUT_BAD)
        if any(x.c >= hc and x.c < cut <= x.c + x.cs - 1 for x in cells):
            raise ValueError(CUT_CROSS)
        edge = {r: x for x in cells if x.c + x.cs == nc for r in range(x.r, x.r + x.rs)}  # 행 → 원래 오른쪽 끝 칸
        fix = [(x, edge.get(x.r)) for x in cells if x.c >= hc and x.c + x.cs == cut]
        mapping = self.clone_blocks(table_id, table_id)["map"]
        new_id = mapping[table_id]
        host = self._host(self._ids[new_id])
        for k in ("pageBreak", "columnBreak"):  # 사본은 앞 표 바로 아래에 — 쪽·단 나눔을 물려받지 않는다
            if host.get(k) not in (None, "0"):
                host.set(k, "0")
        self.delete_cols(table_id, cut, nc - 1, keep=(hc, nc - 1))
        self.delete_cols(new_id, hc, cut - 1, keep=(hc, nc - 1))
        for x, e in fix:
            if e is not None and e is not x:
                x.el.set(BF, self._line_from(x.el.get(BF), "rightBorder", e.el.get(BF), "rightBorder"))
        self._touch(tbl)
        return {"table": table_id, "new": new_id, "map": mapping}

    def join_tables(self, first_id: str, second_id: str, hc: int) -> dict:
        """뒤 표의 필드 열(hc..끝)을 앞 표 오른쪽에 붙이고 뒤 표(그 문단)를 지운다. 앞 표의 헤더 열·표 폭 그대로 — 필드 폭은 두 표의 격자 열 수에 비례해 몫을 나눈 뒤
        표 안에서는 가진 비율대로(같은 폭 열이면 나누기 전과 같다). 헤더 열에서 필드 열 끝까지 걸친 칸(전체 너비 줄)은 앞 표의 같은 자리 칸이 넓어진다.
        이어 붙는 변의 괘선은 안쪽 선으로. ValueError: 행 수·헤더 열 칸 자리가 다름. -> {"table": 앞 표 id, "removed": [지운 블록 id], "moved": [옮긴 칸 id]}."""
        t1, c1, nr1, nc1 = self._tgrid(self._ids.get(first_id))
        t2, c2, nr2, nc2 = self._tgrid(self._ids.get(second_id))
        hc = int(hc)
        if t1 is t2 or nr1 != nr2 or not (0 < hc < nc1 and hc < nc2):
            raise ValueError(JOIN_DIFF)
        heads = lambda cells: sorted((x.r, x.c, x.rs, min(x.c + x.cs, hc) - x.c) for x in cells if x.c < hc)  # noqa: E731
        if heads(c1) != heads(c2):
            raise ValueError(JOIN_DIFF)
        h1, w1 = self._tsizes(c1, nr1, nc1)
        _h2, w2 = self._tsizes(c2, nr2, nc2)
        d = nc2 - hc
        at1 = {(x.r, x.c): x for x in c1}
        moved, wide = [], []
        for y in c2:
            if y.c >= hc:
                moved.append(y)
            elif y.c + y.cs > hc:  # 헤더 열에서 필드 열까지 걸친 칸 — 두 표 모두 끝 열까지여야 하나로 이을 수 있다
                x = at1.get((y.r, y.c))
                if x is None or x.c + x.cs != nc1 or y.c + y.cs != nc2:
                    raise ValueError(JOIN_DIFF)
                wide.append(x)
        if any(x.c < hc < x.c + x.cs and x not in wide for x in c1):
            raise ValueError(JOIN_DIFF)
        # 이어 붙는 변의 괘선 — 앞 표 오른쪽 끝 필드 칸의 오른쪽 변 · 뒤 표 첫 필드 칸의 왼쪽 변을 안쪽 선으로(뒤 표 첫 칸의 오른쪽 선, 없으면 앞 칸의 왼쪽 선)
        last1 = {r: x for x in c1 if x.c >= hc and x.c + x.cs == nc1 for r in range(x.r, x.r + x.rs)}
        first2 = {r: y for y in c2 if y.c == hc for r in range(y.r, y.r + y.rs)}
        for y in dict.fromkeys(first2.values()):
            x = last1.get(y.r)
            src = (y.el.get(BF), "rightBorder") if y.c + y.cs < nc2 else (x.el.get(BF), "leftBorder") if x is not None and x.c > hc else None
            if src is None:
                continue
            if x is not None:
                x.el.set(BF, self._line_from(x.el.get(BF), "rightBorder", *src))
            y.el.set(BF, self._line_from(y.el.get(BF), "leftBorder", *src))
        for x in wide:
            x.cs += d
        for y in moved:
            c1.append(grid.Cell(y.el, y.r, y.c - hc + nc1, y.rs, y.cs))
        total = sum(w1[hc:])
        widths = w1 + w2[hc:]
        own = total * (nc1 - hc) // (nc1 - hc + d)
        grid.refit(widths, hc, nc1 - 1, own)
        grid.refit(widths, nc1, len(widths) - 1, total - own)
        ids = [self._id(y.el) for y in moved]
        self._tput(t1, c1, h1, widths, sized=[x for x in c1 if x.c + x.cs > hc])
        removed = self.delete_blocks(second_id, second_id)["removed"]
        self._touch(t1)
        return {"table": first_id, "removed": removed, "moved": ids}

    def _head_sig(self, tbl, hc):
        """헤더 열(0..hc-1) 서명 — (행 수, 헤더 열 칸의 자리·글). 필드 열이 없으면 None."""
        _t, cells, nr, nc = self._tgrid(tbl)
        if nc <= hc:
            return None
        text = lambda x: " ".join("".join(self._text(p) for p in x.el.find(SUBLIST).iterchildren(P)).split())  # noqa: E731
        return nr, sorted((x.r, x.c, x.rs, min(x.c + x.cs, hc) - x.c, text(x)) for x in cells if x.c < hc)

    def split_partner(self, table_id: str, hc: int, forward: bool = True):
        """이어진 표(② §5-3): 표 문단 바로 다음(forward=False: 앞) 문단 — 빈 문단은 BLANK_BETWEEN 개까지 건너뜀 — 에 표 하나만 있고, 행 수와 헤더 열의 칸 자리·글이
        같으면 그 표 id. 아니면 None."""
        tbl = self._ids.get(table_id)
        if tbl is None or tbl.tag != TBL or not self._attached(tbl) or int(hc) <= 0:
            return None
        el, skipped = self._host(tbl), 0
        if sum(1 for r in el.iterchildren(RUN) for _ in r.iterchildren(TBL, PIC)) != 1:
            return None
        while True:
            el = el.getnext() if forward else el.getprevious()
            if el is None or el.tag != P:
                return None
            objs = [o for r in el.iterchildren(RUN) for o in r.iterchildren(TBL, PIC)]
            if objs:
                break
            if self._text(el).strip() or skipped >= BLANK_BETWEEN:
                return None
            skipped += 1
        if len(objs) != 1 or objs[0].tag != TBL:
            return None
        sig = self._head_sig(tbl, int(hc))
        return self._id(objs[0]) if sig is not None and sig == self._head_sig(objs[0], int(hc)) else None
