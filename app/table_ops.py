"""표 행·열 편집의 형식 중립 부분(spec_owpml_편집 ② §2 「표 행·열」) — hwpx(`hwpx_struct.StructMixin.table_edit`)와 docx(`docx_struct.DocxStructMixin.table_edit`)가
함께 쓴다. 표 모듈(spec_헤딩_추출 ② §10 「모듈」, 사용자 2026-11-10 "본문 따로, 테이블 따로")의 서버 쪽 공통부 — 끝점은 `app/tables_api.py` `POST /api/docs/{id}/table`,
격자 연산은 형식마다(`hwpx_doc`·`docx_doc` + `table_grid`). 2026-11-10 astra 협의(Q6)로 `hwpx_struct` 에서 옮김 — 옛 이름은 `hwpx_struct` 에서도 보인다."""

from app import table_grid as grid

LINE_OPS = ("row_above", "row_below", "row_delete", "col_left", "col_right", "col_delete", "cols_even")  # 행·열 전체(② §2 「표 행·열」 · cols_even = 열 폭 같게 ② §5-1)
CELL_OPS = ("cells_below", "cells_above", "cells_copy", "cells_delete", "merge", "unmerge", "split")  # 고른 칸만(② §5-2)
TABLE_OPS = LINE_OPS + CELL_OPS
SPLIT_KEEPS = ("table", "cell")  # 칸 나누기 — 표 크기 그대로 | 칸 크기 그대로(위아래로 나눌 때 표가 늘어남)


def col_keep(flags, n_cols, c0, c1, add):
    """열 c0..c1 을 넣거나(add) 지울 때 **폭을 나눠 가질 열 범위** (a, b) — 어댑터 `clone_cols`·`delete_cols` 의 keep(그 범위의 합계 폭이 그대로, spec_owpml_편집 ② §5-1).
    flags = 열마다 필드 열인가(None = 판정 없음). 고른 열을 품은 이어진 필드 열 묶음, 헤더 열이 끼었거나 지우면 묶음에 남는 열이 없으면 표의 모든 열,
    판정이 없으면 예전 규칙(지우기 = 이웃 열이 받음 · 넣기 = 고른 열과 새 열이 반씩)."""
    d = c1 - c0 + 1
    if flags and len(flags) == n_cols:
        run = grid.col_run([bool(f) for f in flags], c0, c1)
        if run is None or (not add and run[1] - run[0] + 1 == d):
            run = (0, n_cols - 1)
        if add or run[1] - run[0] + 1 > d:
            return run
    return (c0, c1) if add else ((c0 - 1, c1) if c0 > 0 else (c0, c1 + 1))


def even_spans(cells, n_cols, flags, c0, c1):
    """「열 폭 같게」(② §5-1) 가 합계 폭을 고르게 나눌 열 묶음 [(c0, c1)…] — 어댑터 `even_cols` 의 spans. 열을 둘 이상 골랐으면 그 열들, 하나면 그 열을 품은 필드 열 묶음
    (flags = 열마다 필드 열인가). 묶음은 필드 열 단위로 나눈다(합친 헤더 아래 열들은 한 단위 — 단위 안 비율은 그대로); 단위가 범위와 안 맞으면 열 하나씩.
    ValueError: 고르게 나눌 열이 하나뿐."""
    a, b = c0, c1
    if a == b:
        run = grid.col_run([bool(f) for f in flags], c0, c1) if flags and len(flags) == n_cols else None
        if run is None or run[0] == run[1]:
            raise ValueError("폭을 같게 할 열을 둘 이상 고르세요 — 필드 열의 칸 하나를 고르면 이어진 필드 열 전부가 대상입니다")
        a, b = run
    units = [u for u in grid.col_units(cells, n_cols, a) if u[1] <= b]
    if len(units) < 2 or units[0][0] != a or units[-1][1] != b:
        units = [(c, c) for c in range(a, b + 1)]
    return units


def cell_op(doc, tid, op, box, opts, inside):
    """고른 칸만(② §5-2) — 어댑터 공용 메서드로: 고른 칸의 열 범위에서만 넣기·복사·줄 지우기, 합치기·풀기·나누기. box = (r0, c0, r1, c1),
    inside() = 그 범위에 통째로 든 칸 id(행 우선 — 풀기·나누기는 칸마다). → 어댑터 결과(풀기·나누기는 모은 것 {"cell", "new", "grown"})."""
    r0, c0, r1, c1 = box
    opts = opts if isinstance(opts, dict) else {}
    if op in ("cells_below", "cells_above", "cells_copy"):
        return doc.clone_rows(tid, r0, r1, cols=[c0, c1], keep_text=op == "cells_copy", above=op == "cells_above")
    if op == "cells_delete":
        return doc.delete_rows(tid, r0, r1, cols=[c0, c1])
    ids = inside()
    if op == "merge":
        if len(ids) < 2:
            raise ValueError("합칠 칸을 둘 이상 고르세요")
        return doc.merge_cells(tid, r0, c0, r1, c1)
    if not ids:
        raise ValueError("고른 범위에 통째로 든 칸이 없습니다 — 합친 칸은 걸친 행·열까지 함께 고르세요")
    out = {"cell": ids[0], "new": [], "grown": []}
    if op == "unmerge":
        done = [doc.unmerge_cell(i) for i in ids]
        if not any(r["new"] for r in done):
            raise ValueError("고른 칸에 합친 칸이 없습니다")
    else:
        try:
            rows, cols = int(opts.get("rows", 1)), int(opts.get("cols", 1))
        except (TypeError, ValueError):
            raise ValueError("나눌 행·열 수(rows·cols)는 정수여야 합니다") from None
        keep = opts.get("keep") or "table"
        if keep not in SPLIT_KEEPS:
            raise ValueError("keep 은 table(표 크기 그대로) 또는 cell(칸 크기 그대로)")
        if rows * cols < 2:
            raise ValueError("나눌 행·열 수를 2 이상으로 고르세요")
        if keep == "cell" and not getattr(doc, "SPLIT_KEEP_CELL", False):
            raise ValueError("칸 크기 그대로 나누기는 지금 hwpx 문서만 됩니다")
        done = [doc.split_cell(i, rows, cols, keep) if keep == "cell" else doc.split_cell(i, rows, cols) for i in ids]
    for r in done:
        out["new"] += r.get("new") or []
        out["grown"] += [g for g in r.get("grown") or [] if g not in out["grown"]]
    return out


def table_range(rng, bounds, nr, nc):
    """끌어 고른 칸 묶음 {r0, c0, r1, c1}(격자 좌표, spec_owpml_편집 ② §2 「표 행·열」) -> (r0, c0, r1, c1).
    없으면 bounds(그 칸이 걸친 행·열) 그대로. 표 밖·뒤집힌 범위는 거절(표가 바뀐 뒤 옛 좌표)."""
    if not rng:
        return bounds
    try:
        r0, c0, r1, c1 = (int(rng[k]) for k in ("r0", "c0", "r1", "c1"))
    except (KeyError, TypeError, ValueError):
        raise ValueError("range 는 {r0, c0, r1, c1}(정수)여야 합니다") from None
    if not (0 <= r0 <= r1 < nr and 0 <= c0 <= c1 < nc):
        raise ValueError("고른 범위가 표 밖입니다 — 표가 바뀌었으면 칸을 다시 고르세요")
    return r0, c0, r1, c1
