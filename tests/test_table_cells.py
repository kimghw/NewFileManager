"""표 편집 확장(spec_owpml_편집 ② §5) — 열 폭 규칙 · 칸 단위 편집 · 표 나누기/합치기 · 헤더 지정: 격자·어댑터·서버 API."""
from functools import cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import owpml_check as oc, server
from app import table_grid as grid
from app import table_heads as TH
from app import table_ops
from app.hwpx_doc import HP, HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL, PLAN = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "연구개발계획서_양식.hwpx"
P, TBL, TC = f"{{{HP}}}p", f"{{{HP}}}tbl", f"{{{HP}}}tc"


@cache
def _bytes(path):
    return path.read_bytes()


def _doc(path=PLAN):
    d = HwpxDoc(_bytes(path))
    d.blocks()
    return d


@cache
def _base(path):
    return oc.counts(oc.check_doc(_doc(path)))


def _ok(d, path=PLAN):
    """저장본을 다시 열어 문서 전체 판정 — 실패 아님 · 참조 규칙 위반 0."""
    again = HwpxDoc(d.save())
    again.adopt_ids(d.id_state())
    res = oc.check_doc(again)
    assert oc.verdict(again, _base(path), res)["status"] != "fail" and not res["rules"], res["rules"][:3]


def _grid(d, tid):
    tbl, cells, nr, nc = d._tgrid(d._ids[tid])
    return cells, nr, nc, d._tsizes(cells, nr, nc)


def _para(d, cell):
    return d._id(next(cell.el.iter(P)))


def _table(d, pred):
    """조건에 맞는 첫 표 → (표 id, layout)."""
    for sec in d._sections:
        for tbl in sec.iter(TBL):
            tid = d._rev.get(tbl)
            if tid is None or int(tbl.get("rowCnt")) * int(tbl.get("colCnt")) < 6:
                continue
            lay = TH.layout(d, tid)
            if pred(d, tid, lay):
                return tid, lay
    raise AssertionError("조건에 맞는 표 없음")


def _plain_units(d, tid, lay):
    """왼쪽 헤더 열 + 한 열짜리 필드 열 단위 3개 이상 + 헤더 열 뒤가 모두 필드 열."""
    return lay["headCols"] >= 1 and len(lay["units"]) >= 3 and all(a == b for a, b in lay["units"]) and all(lay["fieldCols"][lay["headCols"]:])


# ---------------------------------------------------------------- 격자
def _cells(spec):
    return [grid.Cell(None, *x) for x in spec]


def test_clone_lenient_grows_partly_covering_cell():
    # 0열: 0~3행 묶음 제목(KEIT) · 1열: 행마다 한 칸. 0~1행을 통째로 아래에 넣기 — 엄격하면 거절, 너그러우면 묶음 제목이 늘어난다
    spec = [(0, 0, 4, 1), (0, 1), (1, 1), (2, 1), (3, 1)]
    with pytest.raises(ValueError, match="병합 칸"):
        grid.clone(_cells(spec), 4, 2, 0, 1, 0, 1)
    cells = _cells(spec)
    new, grown = grid.clone(cells, 4, 2, 0, 1, 0, 1, lenient=True)
    assert [(x.r, x.c) for x in new] == [(2, 1), (3, 1)] and [(x.r, x.rs) for x in grown] == [(0, 6)]
    assert sum(x.rs * x.cs for x in cells) == 6 * 2  # 빈 자리·겹침 없음
    # 위로: 묶음 제목이 r0 에서 시작 — 그 자리에 남아 새 행까지 덮는다
    cells = _cells(spec)
    new, grown = grid.clone(cells, 4, 2, 0, 1, 0, 1, above=True, lenient=True)
    assert [(x.r, x.c) for x in new] == [(0, 1), (1, 1)] and [(x.r, x.rs) for x in grown] == [(0, 6)]
    # 넣는 자리(아래 = r1)를 안 덮는 걸친 칸은 너그러워도 거절(새 행에 빈 자리가 생긴다)
    with pytest.raises(ValueError, match="병합 칸"):
        grid.clone(_cells([(0, 0, 2, 1), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1)]), 4, 2, 1, 2, 0, 1, lenient=True)
    # 늘어나는 칸의 열에 든 칸은 복사하지 않는다(겹침 방지): 0열 1행 칸 + 2~3행 묶음, 1~2행을 넣음
    cells = _cells([(0, 0), (1, 0), (2, 0, 2, 1), (0, 1), (1, 1), (2, 1), (3, 1)])
    new, grown = grid.clone(cells, 4, 2, 1, 2, 0, 1, lenient=True)
    assert [(x.r, x.c) for x in new] == [(3, 1), (4, 1)] and [(x.r, x.rs) for x in grown] == [(2, 4)]
    assert sum(x.rs * x.cs for x in cells) == 6 * 2


def test_clone_inside_fits_divided_rows():
    # 2026-11-22 「다음연도 연구개발비」 표: 0열 묶음(0~1행) · 1열 「800,000」(0행) / 「80%」(1행) · 2열 「1,000,000」(0~1행).
    # 2열만 골라 위에 넣기 = 새 칸이 0행(800,000 줄)에, 1,000,000 은 1행(80% 줄)으로 — 격자 행이 안 늘어 1열 칸 높이 그대로(② §5-2 「나뉜 필드에 맞춰」)
    spec = [(0, 0, 2, 1), (0, 1), (1, 1), (0, 2, 2, 1)]
    cells = _cells(spec)
    new, picked = grid.clone_inside(cells, 2, 3, 0, 1, 2, 2, above=True)
    assert [(x.r, x.c, x.rs) for x in new] == [(0, 2, 1)] and [(x.r, x.rs) for x in picked] == [(1, 1)] and new[0].src is picked[0]
    assert sum(x.rs * x.cs for x in cells) == 2 * 3 and [(x.r, x.rs) for x in cells[:3]] == [(0, 2), (0, 1), (1, 1)]  # 다른 열 그대로
    cells = _cells(spec)
    new, picked = grid.clone_inside(cells, 2, 3, 0, 1, 2, 2)  # 아래에 = 마지막 나뉜 줄
    assert [(x.r, x.rs) for x in new] == [(1, 1)] and [(x.r, x.rs) for x in picked] == [(0, 1)]
    # 3줄로 나뉜 곳: 위 = 첫 나눔까지(1줄), 아래 = 마지막 나눔부터(1줄) — 고른 칸은 나머지 2줄
    cells = _cells([(0, 0), (1, 0), (2, 0), (0, 1, 3, 1)])
    new, picked = grid.clone_inside(cells, 3, 2, 0, 2, 1, 1, above=True)
    assert [(x.r, x.rs) for x in new] == [(0, 1)] and [(x.r, x.rs) for x in picked] == [(1, 2)]
    # 맞지 않는 곳은 None(clone 이 행을 늘린다): 한 줄짜리 고름 · 다른 열도 안 나뉨 · 고른 열 안이 여러 줄 · 열 경계에 걸친 칸
    assert grid.clone_inside(_cells(spec), 2, 3, 0, 0, 1, 1) is None
    assert grid.clone_inside(_cells([(0, 0, 2, 1), (0, 1, 2, 1)]), 2, 2, 0, 1, 1, 1) is None
    assert grid.clone_inside(_cells(spec), 2, 3, 0, 1, 1, 2) is None
    assert grid.clone_inside(_cells([(0, 0, 1, 2), (1, 0), (1, 1), (0, 2, 2, 1)]), 2, 3, 0, 1, 1, 2) is None


def test_band_col_run_units_and_keep():
    cells = _cells([(0, 0, 3, 1), (0, 1), (0, 2), (1, 1), (1, 2), (2, 1), (2, 2)])
    assert grid.band(cells, 3, 1, 2) is None and grid.band(cells, 3, 0, 1) == (1, 2)
    flags = [False, False, True, True, True, False, True]
    assert grid.col_run(flags, 3, 3) == (2, 4) and grid.col_run(flags, 6, 6) == (6, 6) and grid.col_run(flags, 1, 2) is None
    # 필드 열 단위: 헤더 열 뒤에서 시작하는 칸이 가르지 않는 경계 — 전체 너비 줄(0열에서 시작)은 안 셈
    cells = _cells([(0, 0), (0, 1, 1, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3), (2, 0, 1, 4)])
    assert grid.col_units(cells, 4, 1) == [(1, 2), (3, 3)]
    # 폭을 나눠 가질 범위: 필드 열 묶음 · 헤더 열이 끼거나 묶음에 남는 열이 없으면 표 전체 · 판정 없으면 예전 규칙
    assert table_ops.col_keep(flags, 7, 3, 3, add=False) == (2, 4) and table_ops.col_keep(flags, 7, 3, 3, add=True) == (2, 4)
    assert table_ops.col_keep(flags, 7, 1, 1, add=False) == (0, 6) and table_ops.col_keep(flags, 7, 6, 6, add=False) == (0, 6)
    assert table_ops.col_keep(None, 7, 3, 3, add=False) == (2, 3) and table_ops.col_keep(None, 7, 0, 0, add=False) == (0, 1)
    assert table_ops.col_keep(None, 7, 3, 4, add=True) == (3, 4)


# ---------------------------------------------------------------- 열 폭 규칙(§5-1)
def test_col_delete_and_insert_keep_header_width_and_field_ratio():
    d = _doc()
    tid, lay = _table(d, _plain_units)
    hc = lay["headCols"]
    cells, nr, nc, (_h, w0) = _grid(d, tid)
    fields = lambda tid_: TH.fields_of(d, tid_)  # noqa: E731
    c = lay["units"][1][0]
    x = next(x for x in cells if x.c == c and x.cs == 1)
    d.table_edit(_para(d, x), "col_delete", {"r0": x.r, "c0": c, "r1": x.r, "c1": c}, {"fields": fields})
    cells, _nr, nc1, (_h, w1) = _grid(d, tid)
    assert nc1 == nc - 1 and sum(w1) == sum(w0) and w1[:hc] == w0[:hc]  # 표 폭·헤더 열 폭 그대로
    rest = w0[hc:c] + w0[c + 1:]
    assert all(abs(a * sum(rest) - b * sum(w1[hc:])) <= sum(rest) + sum(w1[hc:]) for a, b in zip(w1[hc:], rest))  # 남은 필드 열끼리 비율 그대로(반올림 1 이내)
    assert all(a > b for a, b in zip(w1[hc:], rest))  # 넓어졌다
    x = next(x for x in cells if x.c == hc and x.cs == 1)
    d.table_edit(_para(d, x), "col_right", {"r0": x.r, "c0": hc, "r1": x.r, "c1": hc}, {"fields": fields})
    _cells2, _nr, nc2, (_h, w2) = _grid(d, tid)
    assert nc2 == nc and sum(w2) == sum(w0) and w2[:hc] == w0[:hc]
    assert abs(w2[hc] - w2[hc + 1]) <= 1 and all(a < b for a, b in zip(w2[hc + 2:], w1[hc + 1:]))  # 새 열 = 복사한 열 폭, 나머지 필드 열은 줄어듦
    _ok(d)


# ---------------------------------------------------------------- 고른 칸만(§5-2)
def _group_table(d):
    """왼쪽에 2행 이상 걸친 행헤더(묶음 제목)가 있고 그 오른쪽이 한 행짜리 칸들인 표 → (표 id, 묶음 제목 칸)."""
    for sec in d._sections:
        for tbl in sec.iter(TBL):
            tid = d._rev.get(tbl)
            if tid is None:
                continue
            _t, cells, nr, nc = d._tgrid(tbl)
            for g in cells:
                if g.c == 0 and g.rs >= 2 and g.cs == 1 and nc >= 3 and g.r + g.rs < nr:
                    right = [x for x in cells if g.r <= x.r < g.r + g.rs and x.c >= 1]
                    if all(x.rs == 1 and x.cs == 1 for x in right) and len(right) == g.rs * (nc - 1):
                        return tid, g
    raise AssertionError("묶음 제목이 있는 표 없음")


def test_cells_ops_grow_and_shrink_the_header_cell():
    d = _doc()
    tid, g = _group_table(d)
    cells, nr, nc, (h0, _w) = _grid(d, tid)
    gid, r0, rs = d._id(g.el), g.r, g.rs
    span = lambda: int(d._ids[gid].find(f"{{{HP}}}cellSpan").get("rowSpan"))  # noqa: E731
    first = next(x for x in cells if x.r == r0 and x.c == 1)
    pid, text = _para(d, first), d._text(next(first.el.iter(P)))
    # 고른 칸(묶음 제목 오른쪽 첫 행의 1..끝 열)만 아래에: 묶음 제목은 복사되지 않고 늘어난다
    box = {"r0": r0, "c0": 1, "r1": r0, "c1": nc - 1}
    res = d.table_edit(pid, "cells_below", box)
    assert span() == rs + 1 and int(d._ids[tid].get("rowCnt")) == nr + 1 and len(res["new"]) == nc - 1
    assert not d._text(next(d._ids[res["new"][0]].iter(P))).strip()  # 빈 칸
    res = d.table_edit(pid, "cells_copy", box)  # 글째 복사
    assert span() == rs + 2 and d._text(next(d._ids[res["new"][0]].iter(P))) == text
    # 고른 칸 줄 지우기: 묶음 제목은 줄어든다
    d.table_edit(pid, "cells_delete", {"r0": r0 + 1, "c0": 1, "r1": r0 + 2, "c1": nc - 1})
    assert span() == rs and int(d._ids[tid].get("rowCnt")) == nr
    # 행 전체 넣기·지우기도 일부만 걸친 묶음 제목에 막히지 않는다(§5-2 — 전에는 거절)
    d.table_edit(pid, "row_below", {"r0": r0, "c0": 1, "r1": r0, "c1": 1})
    assert span() == rs + 1
    d.table_edit(pid, "row_delete", {"r0": r0, "c0": 1, "r1": r0, "c1": 1})  # 묶음 제목이 시작하는 행 — 글째 남고 줄어든다
    assert span() == rs and d._attached(d._ids[gid]) and int(d._ids[tid].get("rowCnt")) == nr
    _ok(d)


def test_cells_insert_fits_divided_rows_without_growing():
    # 묶음 제목(0열, rs 줄)만 골라 위/아래에 넣기·복사 — 오른쪽 열이 그 줄들을 나눠 두었으니 새 칸은 묶음 제목 안의 나뉜 줄에 들고,
    # 표 행 수·행 높이·오른쪽 칸은 그대로(전에는 행이 rs 개 늘고 오른쪽 맨 위/아래 칸이 그만큼 길어졌다 — ② §5-2 「나뉜 필드에 맞춰」)
    d = _doc()
    tid, g = _group_table(d)
    cells, nr, nc, (h0, _w) = _grid(d, tid)
    gid, r0, rs = d._id(g.el), g.r, g.rs
    right = {d._id(x.el): (x.r, x.rs, x.el.find(f"{{{HP}}}cellSz").get("height")) for x in cells if x.c >= 1}
    box = {"r0": r0, "c0": 0, "r1": r0 + rs - 1, "c1": 0}
    pid, text = _para(d, g), d._text(next(g.el.iter(P)))

    def check(op, new_row, g_row):
        res = d.table_edit(pid, op, box)
        cells2, nr2, _nc, (h2, _w2) = _grid(d, tid)
        assert nr2 == nr and h2 == h0 and len(res["new"]) == 1  # 표 크기 그대로
        assert {d._id(x.el): (x.r, x.rs, x.el.find(f"{{{HP}}}cellSz").get("height")) for x in cells2 if x.c >= 1} == right
        y = next(x for x in cells2 if d._id(x.el) == res["new"][0])
        gg = next(x for x in cells2 if d._id(x.el) == gid)
        assert (y.r, y.rs, gg.r, gg.rs) == (new_row, 1, g_row, rs - 1) and res["map"] == {gid: res["new"][0]}
        assert int(y.el.find(f"{{{HP}}}cellSz").get("height")) == h0[new_row]
        return y

    y = check("cells_above", r0, r0 + 1)
    assert not d._text(next(y.el.iter(P))).strip()
    _ok(d)
    d = _doc()
    pid = _para(d, next(x for x in _grid(d, tid)[0] if d._id(x.el) == gid))
    check("cells_below", r0 + rs - 1, r0)
    d = _doc()
    pid = _para(d, next(x for x in _grid(d, tid)[0] if d._id(x.el) == gid))
    y = check("cells_copy", r0 + rs - 1, r0)
    assert d._text(next(y.el.iter(P))) == text  # 글째
    _ok(d)


def test_docx_cells_insert_fits_divided_rows():
    from app.docx_doc import DocxDoc
    d = DocxDoc((SAMPLES / "기술수요조사서.docx").read_bytes())
    tb = next(b for b in d.blocks() if b.get("type") == "table" and b["nRows"] >= 3 and b["nCols"] >= 2
              and sum(1 for c in b["cells"] if c["col"] == 1 and c["rowSpan"] == 1 and c["colSpan"] == 1 and c["row"] in (1, 2)) == 2
              and sum(1 for c in b["cells"] if c["col"] == 0 and c["rowSpan"] == 1 and c["colSpan"] == 1 and c["row"] in (1, 2)) == 2)
    tid, nr = tb["id"], tb["nRows"]
    d.merge_cells(tid, 1, 1, 2, 1)  # 1열 1~2행을 한 칸으로 — 0열은 두 줄로 나뉨
    res = d.clone_rows(tid, 1, 2, cols=[1, 1], keep_text=False, above=True, fit=True)
    tables = lambda doc: [b for b in doc.blocks() if b.get("type") == "table"]  # noqa: E731
    t2 = next(b for b in tables(d) if b["id"] == tid)
    k = [b["id"] for b in tables(d)].index(tid)
    t3 = tables(DocxDoc(d.save()))[k]  # 저장본을 다시 읽어도 같은 격자
    assert [(c["row"], c["col"], c["rowSpan"], c["colSpan"]) for c in t3["cells"]] == [(c["row"], c["col"], c["rowSpan"], c["colSpan"]) for c in t2["cells"]]
    at = {(c["row"], c["col"]): c for c in t2["cells"]}
    assert t2["nRows"] == nr and len(res["new"]) == 1
    assert at[(1, 1)]["rowSpan"] == 1 and not at[(1, 1)]["text"].strip() and at[(2, 1)]["rowSpan"] == 1 and (1, 0) in at and (2, 0) in at


def test_merge_unmerge_split_keep_table_or_cell():
    d = _doc()
    tid, g = _group_table(d)
    cells, nr, nc, (h0, w0) = _grid(d, tid)
    r0 = g.r
    a = next(x for x in cells if x.r == r0 and x.c == 1)
    pid = _para(d, a)
    height = lambda: int(d._ids[tid].find(f"{{{HP}}}sz").get("height"))  # noqa: E731
    t0 = height()
    box = {"r0": r0, "c0": 1, "r1": r0 + 1, "c1": 2}
    res = d.table_edit(pid, "merge", box)
    assert len(res["removed"]) == 3
    with pytest.raises(ValueError, match="둘 이상"):
        d.table_edit(pid, "merge", box)  # 이제 한 칸
    d.table_edit(pid, "unmerge", box)
    assert len(_grid(d, tid)[0]) == len(cells) and height() == t0
    one = {"r0": r0, "c0": 1, "r1": r0, "c1": 1}
    # 표 크기 그대로: 그 행 높이를 반씩 — 표 높이 그대로
    d.table_edit(pid, "split", one, {"rows": 2, "cols": 1})
    _c, nr1, _nc, (h1, _w) = _grid(d, tid)
    assert nr1 == nr + 1 and height() == t0 and h1[r0] + h1[r0 + 1] == h0[r0]
    d.table_edit(pid, "merge", {"r0": r0, "c0": 1, "r1": r0 + 1, "c1": 1})  # 되돌림(격자 행은 다른 칸이 시작하지 않아 접힌다)
    assert int(d._ids[tid].get("rowCnt")) == nr
    # 칸 크기 그대로: 새 행이 원래 행 높이로 — 표가 그만큼 늘어난다
    d.table_edit(pid, "split", one, {"rows": 2, "cols": 1, "keep": "cell"})
    _c, nr2, _nc, (h2, _w) = _grid(d, tid)
    assert nr2 == nr + 1 and h2[r0] == h2[r0 + 1] == h0[r0] and height() == t0 + h0[r0]
    # 좌우로: 표 폭 그대로
    d.table_edit(pid, "split", one, {"rows": 1, "cols": 2})
    _c, _nr, nc3, (_h, w3) = _grid(d, tid)
    assert nc3 == nc + 1 and sum(w3) == sum(w0)
    with pytest.raises(ValueError, match="2 이상"):
        d.table_edit(pid, "split", one, {"rows": 1, "cols": 1})
    with pytest.raises(ValueError, match="keep"):
        d.table_edit(pid, "split", one, {"rows": 2, "keep": "x"})
    _ok(d)


# ---------------------------------------------------------------- 표 나누기(§5-3)
def test_split_join_resplit_tables():
    d = _doc()
    tid, lay = _table(d, _plain_units)
    hc, n = lay["headCols"], len(lay["units"])
    cells, nr, nc, (h0, w0) = _grid(d, tid)
    texts = lambda t: sorted(" ".join(d._text(p) for p in x.el.iter(P)) for x in d._tgrid(d._ids[t])[1] if x.c >= hc)  # noqa: E731
    before = texts(tid)
    new = d.split_table(tid, hc, lay["units"][1][0])["new"]
    c1, nr1, nc1, (_h, w1) = _grid(d, tid)
    c2, nr2, nc2, (_h, w2) = _grid(d, new)
    assert (nr1, nc1) == (nr, hc + 1) and (nr2, nc2) == (nr, nc - 1)
    assert sum(w1) == sum(w2) == sum(w0) and w1[:hc] == w2[:hc] == w0[:hc]  # 두 표 모두 원래 폭 · 헤더 열 폭 그대로
    assert d._host(d._ids[new]).getprevious() is d._host(d._ids[tid])  # 바로 뒤 문단
    assert d.split_partner(tid, hc) == new and d.split_partner(new, hc, False) == tid and d.split_partner(new, hc) is None
    assert sorted(texts(tid) + texts(new)) == before
    lay2 = TH.layout(d, tid)
    assert lay2["partner"]["next"] == {"table": new, "units": n - 1} and len(lay2["units"]) == 1
    with pytest.raises(ValueError, match="헤더 열 뒤"):
        d.split_table(new, hc, hc)
    # 다시 합치기 — 칸은 옮겨진다(id 그대로), 뒤 표 문단은 없어진다
    moved = d.join_tables(tid, new, hc)["moved"]
    c3, nr3, nc3, (_h, w3) = _grid(d, tid)
    assert (nr3, nc3) == (nr, nc) and sum(w3) == sum(w0) and w3[:hc] == w0[:hc] and texts(tid) == before
    assert all(abs(a - b) <= 2 for a, b in zip(w3, w0)) or len(set(w0[hc:])) > 1  # 같은 폭 열이면 나누기 전과 같다
    assert not d._attached(d._ids[new]) and all(d._attached(d._ids[i]) for i in moved)
    assert sum(x.rs * x.cs for x in c3) == nr * nc
    _ok(d)


# ---------------------------------------------------------------- 헤더 지정(§5-4)
def test_user_roles_change_field_cols():
    d = _doc()
    tid, lay = _table(d, _plain_units)
    hc = lay["headCols"]
    col = [x["id"] for x in lay["cells"] if x["col"] == hc and x["cs"] == 1]
    as_head = TH.layout(d, tid, {c: "rowhead" for c in col})
    assert as_head["headCols"] == hc + 1 and not as_head["fieldCols"][hc] and len(as_head["units"]) == len(lay["units"]) - 1
    assert all(x.get("user") for x in as_head["cells"] if x["id"] in col)
    back = [x["id"] for x in lay["cells"] if x["col"] == 0 and x["role"] in ("rowhead", "corner")]
    as_field = TH.layout(d, tid, {c: "field" for c in back})
    assert as_field["fieldCols"][0] and as_field["headCols"] == 0 and as_field["units"] == []  # 헤더 열이 없으면 나눌 수 없다


# ---------------------------------------------------------------- 서버
@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _open(c, path=PLAN):
    return c.post("/api/docs", files={"file": (path.name, path.read_bytes())}).json()["docId"]


def test_server_cells_layout_heads_split(client):
    doc = _doc()
    tid, lay = _table(doc, _plain_units)
    hc, n = lay["headCols"], len(lay["units"])
    d = _open(client)
    got = client.get(f"/api/docs/{d}/tables/{tid}/layout")
    assert got.status_code == 200, got.text
    got = got.json()
    assert got["headCols"] == hc and got["units"] == lay["units"] and got["partner"] == {"prev": None, "next": None} and "rev" in got
    # 헤더 지정 — 저장·목록·판정
    col = [x["id"] for x in got["cells"] if x["col"] == hc and x["cs"] == 1]
    r = client.put(f"/api/docs/{d}/tables/{tid}/heads", json={"cells": col, "role": "rowhead"})
    assert r.status_code == 200, r.text
    assert r.json()["layout"]["headCols"] == hc + 1 and set(r.json()["roles"]) == set(col)
    assert client.get(f"/api/docs/{d}/tables/heads").json()["tables"][tid] == {c: "rowhead" for c in col}
    assert client.put(f"/api/docs/{d}/tables/{tid}/heads", json={"cells": ["nope"], "role": "field"}).status_code == 400
    assert client.put(f"/api/docs/{d}/tables/{tid}/heads", json={"cells": col, "role": "x"}).status_code == 400
    r = client.put(f"/api/docs/{d}/tables/{tid}/heads", json={"cells": col, "role": None})
    assert r.json()["roles"] == {} and r.json()["layout"]["headCols"] == hc
    # 나누기 → 다시 나누기 → 합치기 → 실행 취소
    bad = client.post(f"/api/docs/{d}/tables/{tid}/split", json={"op": "split", "first": n})
    assert bad.status_code == 400 and "나눌 자리" in bad.json()["detail"]
    assert client.post(f"/api/docs/{d}/tables/{tid}/split", json={"op": "join"}).status_code == 400  # 짝 없음
    r = client.post(f"/api/docs/{d}/tables/{tid}/split", json={"op": "split", "first": n - 1})
    assert r.status_code == 200, r.text
    r = r.json()
    new = r["split"]["tables"][1]
    assert r["split"]["units"] == [n - 1, 1] and {tid, new} <= {b["id"] for b in r["tops"]["blocks"]}
    r = client.post(f"/api/docs/{d}/tables/{new}/split", json={"op": "resplit", "first": 1})  # 뒤 표에서 불러도 된다
    assert r.status_code == 200, r.text
    r = r.json()
    new2 = r["split"]["tables"][1]
    assert r["split"]["tables"][0] == tid and r["split"]["units"] == [1, n - 1] and new in r["tops"]["drop"] and new2 != new
    cols = {b["id"]: b["nCols"] for b in r["tops"]["blocks"] if b["type"] == "table"}
    assert cols[tid] == lay["units"][0][1] + 1 and cols[new2] == hc + lay["cols"] - lay["units"][1][0]
    r = client.post(f"/api/docs/{d}/tables/{tid}/split", json={"op": "join"})
    assert r.status_code == 200, r.text
    assert r.json()["split"]["tables"] == [tid, None] and new2 in r.json()["tops"]["drop"]
    assert next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)["nCols"] == lay["cols"]
    for _ in range(3):
        g = client.post(f"/api/docs/{d}/undo").json()
    assert g["pristine"] and client.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def test_server_cell_ops_and_col_rule(client):
    doc = _doc()
    tid, g = _group_table(doc)
    cells, nr, nc, _sz = _grid(doc, tid)
    first = next(x for x in cells if x.r == g.r and x.c == 1)
    pid = _para(doc, first)
    d = _open(client)
    box = {"r0": g.r, "c0": 1, "r1": g.r, "c1": nc - 1}
    r = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "cells_below", "range": box})
    assert r.status_code == 200, r.text
    tb = next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)
    assert tb["nRows"] == nr + 1 and next(c for c in tb["cells"] if c["id"] == doc._id(g.el))["rowSpan"] == g.rs + 1
    r = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "split", "range": {**box, "c1": 1}, "opts": {"rows": 2, "keep": "cell"}})
    assert r.status_code == 200, r.text
    assert next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)["nRows"] == nr + 2
    bad = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "merge", "range": {**box, "c1": 1}})
    assert bad.status_code == 400 and "둘 이상" in bad.json()["detail"]
    bad = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "cells_delete", "range": box})  # 나눈 칸 옆 칸들이 두 행에 걸친다 — 범위가 그 칸을 다 품어야
    assert bad.status_code == 400 and "병합 칸" in bad.json()["detail"]
    r = client.post(f"/api/docs/{d}/table", json={"id": pid, "op": "cells_delete", "range": {**box, "r1": g.r + 1}})
    assert r.status_code == 200, r.text
    tb = next(b for b in r.json()["tops"]["blocks"] if b["id"] == tid)
    assert tb["nRows"] == nr and next(c for c in tb["cells"] if c["id"] == doc._id(g.el))["rowSpan"] == g.rs  # 묶음 제목은 글째 남아 줄어든다
    # 열 지우기 — 서버가 칸 역할을 판정해 헤더 열 폭을 지킨다
    tid2, lay = _table(doc, _plain_units)
    hc, c = lay["headCols"], lay["units"][1][0]
    c2, _nr, _nc, (_h, w0) = _grid(doc, tid2)
    x = next(x for x in c2 if x.c == c and x.cs == 1)
    r = client.post(f"/api/docs/{d}/table", json={"id": _para(doc, x), "op": "col_delete", "range": {"r0": x.r, "c0": c, "r1": x.r, "c1": c}})
    assert r.status_code == 200, r.text
    live = server.DOCS[d].doc
    _c, _nr, _nc, (_h, w1) = _grid(live, tid2)
    assert sum(w1) == sum(w0) and w1[:hc] == w0[:hc] and all(a > b for a, b in zip(w1[hc:], w0[hc:c] + w0[c + 1:]))


def test_stage3_build_takes_user_roles():
    """3단계 표 구조(heading_tables.build)가 사용자 헤더 지정을 초안 위에 덮는다 — 칸 reason 「사용자 지정」 · changed."""
    from app import heading_tables as HT
    from app import table_excel as TX
    d = _doc()
    tid, lay = _table(d, _plain_units)
    hc = lay["headCols"]
    col = [x["id"] for x in lay["cells"] if x["col"] == hc and x["cs"] == 1 and x["role"] == "field"]
    assert col
    out = HT.build(TX.records(d, tid), use_llm=False, ask=lambda jobs: [], roles={tid: {c: "rowhead" for c in col}})
    tb = next(t for t in out["tables"] if t["id"] == tid)
    got = [x for x in tb["cells"] if x["id"] in col]
    assert got and all(x["role"] == "rowhead" and x["reason"] == "사용자 지정" and x["changed"] for x in got)
    plain = HT.build(TX.records(d, tid), use_llm=False, ask=lambda jobs: [])
    assert all(x["role"] == "field" for x in next(t for t in plain["tables"] if t["id"] == tid)["cells"] if x["id"] in col)


def test_cols_even_shares_the_field_run_equally():
    """열 폭 같게(§5-1): 칸 하나를 고르면 그 열을 품은 필드 열 묶음이 합계 폭을 똑같이 — 헤더 열·표 폭 그대로. 옛 규칙으로 한 열만 넓어진 표를 고치는 길."""
    d = _doc()
    tid, lay = _table(d, _plain_units)
    hc = lay["headCols"]
    cells, _nr, nc, (_h, w0) = _grid(d, tid)
    c = lay["units"][1][0]
    x = next(x for x in cells if x.c == c and x.cs == 1)
    d.table_edit(_para(d, x), "col_delete", {"r0": x.r, "c0": c, "r1": x.r, "c1": c})  # 판정 없이(옛 규칙) — 왼쪽 이웃 열만 넓어진다
    cells, _nr, nc1, (_h, w1) = _grid(d, tid)
    assert max(w1[hc:]) - min(w1[hc:]) > 10
    x = next(x for x in cells if x.c == hc and x.cs == 1)
    d.table_edit(_para(d, x), "cols_even", {"r0": x.r, "c0": hc, "r1": x.r, "c1": hc}, {"fields": lambda t: TH.fields_of(d, t)})
    _c, _nr, _nc, (_h, w2) = _grid(d, tid)
    assert sum(w2) == sum(w0) and w2[:hc] == w0[:hc] and max(w2[hc:]) - min(w2[hc:]) <= nc1
    with pytest.raises(ValueError, match="둘 이상"):
        d.table_edit(_para(d, x), "cols_even", {"r0": x.r, "c0": 0, "r1": x.r, "c1": 0}, {"fields": lambda t: TH.fields_of(d, t)})  # 헤더 열 하나
    d.table_edit(_para(d, x), "cols_even", {"r0": x.r, "c0": 0, "r1": x.r, "c1": 1})  # 열을 둘 골랐으면 그 열들(판정 없이도)
    _c, _nr, _nc, (_h, w3) = _grid(d, tid)
    assert abs(w3[0] - w3[1]) <= 1 and sum(w3) == sum(w0)
    _ok(d)
