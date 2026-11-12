"""표 만들기 · 서식 입히기 — HwpxDoc 믹스인(spec_헤딩_추출 ② §11 「서식 따오기 규칙」). 표 모듈의 hwpx 어댑터.

- `table_make(ref_id, template_id, norm, roles)`: ref 블록의 문단 바로 뒤에, 양식 표(template)의 서식으로 격자(norm — `table_make.normalize` 결과)의 새 표.
- `table_restyle(table_id, template_id, roles, tpl_roles)`: 문서의 표에 양식 표의 서식만 입힌다(구조·글·칸 크기 그대로).
- 대상 줄 → 양식 줄은 `table_make.zone_index`(구역끼리). 칸의 바탕 서식은 왼쪽 위 자리의 양식 칸, 괘선 네 변은 따로(표 바깥 변은 양식의 바깥 변 칸).
끝점은 `app/tables_api.py`(트랜잭션 `server._edit`), 형식 중립부는 `app/table_make.py`. docx 어댑터는 아직 없다(spec ④)."""
import copy

from lxml import etree

from app import table_grid as grid
from app import table_make as M
from app.hwpx_format import _h, _p
from app.hwpx_struct import OBJECTS

P, RUN, TBL, TR, TC, SUBLIST, LINESEG, CELLADDR, CELLSPAN, CELLSZ, CELLMARGIN, CAPTION, CELLZONES, SZ, INMARGIN, OUTMARGIN = map(_p, [
    "p", "run", "tbl", "tr", "tc", "subList", "linesegarray", "cellAddr", "cellSpan", "cellSz", "cellMargin", "caption", "cellzoneList", "sz",
    "inMargin", "outMargin"])
SKIP_ON_MAKE = frozenset([TR, CAPTION, CELLZONES])  # 새 표로 안 옮기는 양식 표의 자식(행은 새로 짓고, 캡션·cellzone 은 안 옮김)
NEW_PARA = {"id": "0", "paraPrIDRef": "0", "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"}
BODY_ROW_MIN = 1000  # 양식에서 행 높이를 못 읽었을 때(HWPUNIT ≈ 3.5mm)


class _Tpl:
    """양식 표를 구역으로 읽은 것 — 자리(행, 열)의 칸 · 줄 크기 · 구역 수."""

    def __init__(self, tbl, cells, nr, nc, heights, widths, roles):
        self.tbl, self.cells, self.nr, self.nc, self.heights, self.widths = tbl, cells, nr, nc, heights, widths
        self.h, self.k, self.f = roles["headerRows"], roles["headerCols"], roles["footRows"]
        self.occ = {}
        for x in cells:
            for r in range(x.r, x.r + x.rs):
                for c in range(x.c, x.c + x.cs):
                    self.occ.setdefault((r, c), x)

    def at(self, r, c):
        return self.occ.get((r, c)) or self.cells[0]

    def maps(self, n_rows, n_cols, roles):
        """대상 표(n_rows × n_cols, roles)의 행·열 → 양식의 행·열."""
        return ([M.zone_index(r, n_rows, roles["headerRows"], roles["footRows"], self.nr, self.h, self.f) for r in range(n_rows)],
                [M.zone_index(c, n_cols, roles["headerCols"], 0, self.nc, self.k, 0) for c in range(n_cols)])

    def body_height(self):
        body = [v for v in self.heights[self.h:self.nr - self.f] if v > 0] or [v for v in self.heights if v > 0]
        return min(body) if body else BODY_ROW_MIN


class TableMakeMixin:
    # ---------------------------------------------------------------- 양식 읽기 · 칸 서식
    def _tm_template(self, template_id, roles):
        tbl = self._ids.get(template_id)
        if tbl is None or tbl.tag != TBL or not self._attached(tbl):
            raise ValueError("표 양식으로 고른 표가 지금 문서에 없습니다 — 양식을 다시 고르세요")
        _, cells, nr, nc = self._tgrid(tbl)
        if not cells or nr <= 0 or nc <= 0:
            raise ValueError("표 양식에 칸이 없습니다")
        heights, widths = self._tsizes(cells, nr, nc)
        return _Tpl(tbl, cells, nr, nc, heights, widths, M.clean_roles(roles, nr, nc))

    def _tm_bf(self, cache, base, top, bottom, left, right, diag=True):
        """base borderFill 의 네 변을 top·bottom·left·right borderFill 의 그 변으로 바꾼 정의의 id — 같은 정의가 있으면 그 id(_add_def), 바뀐 게 없으면 base.
        diag False 면 대각선(slash·backSlash)을 뺀다 — 양식 귀퉁이 칸의 대각선은 두 제목을 나눠 적는 칸이라 글이 하나인 새 칸에는 안 맞는다."""
        key = (base, top, bottom, left, right, diag)
        if key not in cache:
            src, new = self._defs["borderFill"].get(base), None
            if src is not None and not diag:
                marks = [t for t in ("slash", "backSlash") if (e := src.find(_h(t))) is not None and e.get("type", "NONE") != "NONE"]
                if marks:
                    new = copy.deepcopy(src)
                    for t in marks:
                        new.find(_h(t)).set("type", "NONE")
            for side, other in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
                o = self._defs["borderFill"].get(other) if other != base else None
                line = o.find(_h(f"{side}Border")) if o is not None else None
                if src is None or line is None:
                    continue
                if new is None:
                    new = copy.deepcopy(src)
                old = new.find(_h(f"{side}Border"))
                if old is not None:
                    new.replace(old, copy.deepcopy(line))
            cache[key] = self._add_def("borderFill", new) if new is not None else base
        return cache[key]

    def _tm_look(self, tpl, cache, rmap, cmap, r0, c0, r1, c1):
        """대상 칸(행 r0..r1 · 열 c0..c1)의 (바탕 양식 칸 요소, borderFill id). 바깥 변은 양식의 그 바깥 변 칸에서."""
        n_rows, n_cols = len(rmap), len(cmap)
        base, br = tpl.at(rmap[r0], cmap[c0]), tpl.at(rmap[r1], cmap[c1])
        top = tpl.at(0, cmap[c0]) if r0 == 0 else base
        left = tpl.at(rmap[r0], 0) if c0 == 0 else base
        bottom = tpl.at(tpl.nr - 1, cmap[c1]) if r1 == n_rows - 1 else br
        right = tpl.at(rmap[r1], tpl.nc - 1) if c1 == n_cols - 1 else br
        bf = lambda x: x.el.get("borderFillIDRef")  # noqa: E731
        same = rmap == list(range(tpl.nr)) and cmap == list(range(tpl.nc))  # 양식과 같은 꼴 — 대각선까지 그대로
        return base.el, self._tm_bf(cache, bf(base), bf(top), bf(bottom), bf(left), bf(right), diag=same)

    def _tm_para_like(self, tc):
        """양식 칸에서 문단 모양을 따올 문단 — 첫 글 문단(없으면 첫 문단, 문단이 없으면 None)."""
        sub = tc.find(SUBLIST)
        ps = list(sub.iterchildren(P)) if sub is not None else []
        return next((p for p in ps if self._text(p).strip()), ps[0] if ps else None)

    def _tm_cell(self, src, bf, text, r, c, rs, cs, w, h):
        """양식 칸 src 모양의 새 칸 — 속성·칸 여백은 src, 자리·크기는 인자, 문단은 src 의 첫 글 문단 모양으로 줄마다 하나."""
        tc = src.makeelement(TC, src.attrib)
        if bf is not None:
            tc.set("borderFillIDRef", bf)
        like = self._tm_para_like(src)
        attrs = {**(dict(like.attrib) if like is not None else NEW_PARA), "pageBreak": "0", "columnBreak": "0"}
        cid = self._char_id(like) if like is not None else "0"
        done = set()
        for ch in src:
            if ch.tag in done:
                continue
            done.add(ch.tag)
            if ch.tag == SUBLIST:
                sub = etree.SubElement(tc, SUBLIST, ch.attrib)
                for line in text.split("\n"):
                    self._put_text(etree.SubElement(etree.SubElement(sub, P, attrs), RUN, {"charPrIDRef": cid}), line)
            elif ch.tag == CELLADDR:
                etree.SubElement(tc, CELLADDR, {"colAddr": str(c), "rowAddr": str(r)})
            elif ch.tag == CELLSPAN:
                etree.SubElement(tc, CELLSPAN, {"colSpan": str(cs), "rowSpan": str(rs)})
            elif ch.tag == CELLSZ:
                etree.SubElement(tc, CELLSZ, {"width": str(w), "height": str(h)})
            else:
                tc.append(copy.deepcopy(ch))
        if tc.find(SUBLIST) is None or tc.find(CELLADDR) is None or tc.find(CELLSPAN) is None:
            raise ValueError("표 양식의 칸 구조를 읽지 못했습니다(subList·cellAddr·cellSpan 없음)")
        return tc

    def _tm_new_id(self, tpl):
        """새 표의 개체 id — 구역의 개체 id 와 안 겹치는 수(양식 표 id 다음부터)."""
        used = {el.get("id") for sec in self._sections for el in sec.iter(*OBJECTS)}
        try:
            n = int(tpl.get("id", "0"))
        except ValueError:
            n = 0
        for k in range(1, len(used) + 2):
            cand = str((n + k) % 2147483647 or 1)
            if cand not in used:
                return cand
        return str(n)

    def _tm_anchor(self, ref_id):
        """넣을 자리(블록 id — 문단·표·그림·칸)의 문단: 표·그림은 그것을 품은 문단, 칸은 그 칸의 마지막 문단."""
        el = self._ids.get(ref_id)
        if el is None or not self._attached(el):
            raise ValueError("넣을 자리의 블록이 지금 문서에 없습니다 — 자리를 다시 고르세요")
        if el.tag == TC:
            ps = list(el.find(SUBLIST).iterchildren(P))
            if not ps:
                raise ValueError("넣을 자리의 칸에 문단이 없습니다")
            return ps[-1]
        return self._host(el)

    # ---------------------------------------------------------------- 새 표
    def table_make(self, ref_id: str, template_id: str, norm: dict, roles: dict | None = None) -> dict:
        """ref 블록의 문단 바로 뒤에 새 문단(양식 표를 품은 문단 모양) + 그 안에 양식 서식의 새 표 -> {"table", "host", "rows", "cols"}.
        norm = table_make.normalize 결과, roles = 양식 표의 구역 수 {headerRows, headerCols, footRows}(없으면 0·0·0)."""
        ref = self._tm_anchor(ref_id)
        tpl = self._tm_template(template_id, roles)
        n_rows, n_cols = norm["nRows"], norm["nCols"]
        rmap, cmap = tpl.maps(n_rows, n_cols, norm)
        total = sum(tpl.widths)
        if (cell := next(ref.iterancestors(TC), None)) is not None:  # 칸 안에 넣으면 그 칸의 글 폭까지만
            sz, mg = cell.find(CELLSZ), cell.find(CELLMARGIN)
            avail = (int(sz.get("width", 0)) if sz is not None else 0) - (int(mg.get("left", 0)) + int(mg.get("right", 0)) if mg is not None else 0)
            if 0 < avail < total:
                total = avail
        # 열 폭 — 열 수가 양식과 같으면 양식의 열 폭 그대로(비례), 다르면 양식의 열 폭은 이 내용과 무관하므로 칸 글 길이로 표 폭을 나눈다
        widths = [max(1, tpl.widths[c]) for c in cmap] if n_cols == tpl.nc else [w * 100 for w in M.col_weights(norm)]
        if total > 0:
            grid.refit(widths, 0, n_cols - 1, total)
        body_h = tpl.body_height()
        heights = [tpl.heights[t] if (t < tpl.h or t >= tpl.nr - tpl.f) and tpl.heights[t] > 0 else body_h for t in rmap]
        src = tpl.tbl
        new = src.makeelement(TBL, src.attrib)
        new.attrib.update({"id": self._tm_new_id(src), "rowCnt": str(n_rows), "colCnt": str(n_cols)})
        first_tr = src.find(TR)
        trs = [new.makeelement(TR, first_tr.attrib if first_tr is not None else {}) for _ in range(n_rows)]
        placed = False
        for ch in src:
            if ch.tag == TR and not placed:
                placed = True
                for tr in trs:
                    new.append(tr)
            elif ch.tag not in SKIP_ON_MAKE:
                new.append(copy.deepcopy(ch))
        if not placed:
            for tr in trs:
                new.append(tr)
        cache = {}
        for x in norm["cells"]:
            r, c, rs, cs = x["row"], x["col"], x["rowSpan"], x["colSpan"]
            base, bf = self._tm_look(tpl, cache, rmap, cmap, r, c, r + rs - 1, c + cs - 1)
            trs[r].append(self._tm_cell(base, bf, x["text"], r, c, rs, cs, sum(widths[c:c + cs]), sum(heights[r:r + rs])))
        if any(len(tr) == 0 for tr in trs):
            raise ValueError("칸이 시작하지 않는 행이 있습니다(격자 오류)")
        if (sz := new.find(SZ)) is not None:
            sz.attrib.update({"width": str(sum(widths)), "height": str(sum(heights))})
        host = self._obj_para(src, new)
        host.attrib.update({"pageBreak": "0", "columnBreak": "0"})
        ref.addnext(host)
        self._touch(host)
        return {"table": self._id(new), "host": self._id(host), "rows": n_rows, "cols": n_cols}

    # ---------------------------------------------------------------- 서식만 입히기
    def table_restyle(self, table_id: str, template_id: str, roles: dict | None = None, tpl_roles: dict | None = None) -> dict:
        """문서의 표 table_id 에 양식 표의 서식만 — 칸 괘선·음영·칸 여백·세로 정렬, 칸 바로 안 문단의 문단 모양·글자 모양(개체가 든 런은 그대로),
        표의 바깥/안 여백·표 괘선. 구조·글·칸 크기는 그대로. roles = 이 표의 구역 수, tpl_roles = 양식의 구역 수.
        -> {"table", "cells", "formatted": 모양이 바뀐 문단 id}."""
        tbl = self._ids.get(table_id)
        if tbl is None or tbl.tag != TBL or not self._attached(tbl):
            raise ValueError("서식을 입힐 표가 지금 문서에 없습니다")
        if table_id == template_id:
            raise ValueError("표 양식과 같은 표입니다 — 다른 표를 양식으로 고르세요")
        tpl = self._tm_template(template_id, tpl_roles)
        _, cells, nr, nc = self._tgrid(tbl)
        rmap, cmap = tpl.maps(nr, nc, M.clean_roles(roles, nr, nc))
        cache, changed = {}, []
        for x in cells:
            r1, c1 = min(nr, x.r + x.rs) - 1, min(nc, x.c + x.cs) - 1
            base, bf = self._tm_look(tpl, cache, rmap, cmap, min(x.r, nr - 1), min(x.c, nc - 1), max(r1, 0), max(c1, 0))
            tc = x.el
            if bf is not None:
                tc.set("borderFillIDRef", bf)
            for a in ("hasMargin", "header"):
                if base.get(a) is not None:
                    tc.set(a, base.get(a))
            m_src, m_dst = base.find(CELLMARGIN), tc.find(CELLMARGIN)
            if m_src is not None and m_dst is not None:
                m_dst.attrib.update(m_src.attrib)
            s_src, sub = base.find(SUBLIST), tc.find(SUBLIST)
            if s_src is not None and sub is not None and s_src.get("vertAlign") is not None:
                sub.set("vertAlign", s_src.get("vertAlign"))
            like = self._tm_para_like(base)
            if like is None or sub is None:
                continue
            cid = self._char_id(like)
            for p in sub.iterchildren(P):
                was = (p.get("paraPrIDRef"), p.get("styleIDRef"), [r.get("charPrIDRef") for r in p.iterchildren(RUN)])
                p.set("paraPrIDRef", like.get("paraPrIDRef", "0"))
                p.set("styleIDRef", like.get("styleIDRef", "0"))
                for r in p.iterchildren(RUN):
                    if not any(o.tag in OBJECTS for o in r):
                        r.set("charPrIDRef", cid)
                if was != (p.get("paraPrIDRef"), p.get("styleIDRef"), [r.get("charPrIDRef") for r in p.iterchildren(RUN)]):
                    self._drop_cache(p)
                    changed.append(self._id(p))
        for a in ("borderFillIDRef", "cellSpacing"):
            if tpl.tbl.get(a) is not None:
                tbl.set(a, tpl.tbl.get(a))
        for tag in (INMARGIN, OUTMARGIN):
            a, b = tpl.tbl.find(tag), tbl.find(tag)
            if a is not None and b is not None:
                b.attrib.update(a.attrib)
        self._touch(tbl)
        return {"table": table_id, "cells": len(cells), "formatted": changed}
