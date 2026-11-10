"""Table cell editing on a format-neutral grid (spec_표_편집 ② §2·§3): merge, unmerge, split, clone.

An adapter (HwpxDoc / DocxDoc) reads its table into `Cell`s, one of the functions here changes the grid in place, and
the adapter writes the cells back (hwpx: cellAddr/cellSpan/cellSz, docx: gridSpan/vMerge/tcW). Grid lines count from
0; a cell covers rows r..r+rs-1 and columns c..c+cs-1. Axis "r" = rows, "c" = columns.
ValueError messages are shown to the user as they are (server: 「… 실패: {메시지}」)."""

OUTSIDE = "범위가 표 밖입니다"
CROSS = "병합된 칸이 범위 경계에 걸쳐 있습니다 — 범위를 그 칸 전체로 넓혀 주세요"
HOLE = "범위가 칸으로 다 채워지지 않습니다(표 격자 오류)"
ROWS_CROSS = "선택 행 범위의 일부에만 걸친 병합 칸이 있어 행을 복사할 수 없습니다 — 그 칸 전체가 들도록 선택을 넓혀 주세요"
COLS_CROSS = "선택 열 경계에 걸친 병합 칸이 있어 행을 복사할 수 없습니다 — 그 칸 전체가 들도록 선택을 넓혀 주세요"
SPLIT_MAX = 50  # 한 번에 나눌 행·열 수 상한(화면 입력칸 max 와 같음)
COUNT = f"나눌 행·열 수는 1 이상 {SPLIT_MAX} 이하여야 합니다"
NOTHING = "선택 열에는 위에서 내려온 병합 칸만 있어 복사할 칸이 없습니다 — 그 병합 칸이 시작하는 행까지 선택을 넓혀 주세요"
UNEVEN = "{n}칸에 걸친 칸은 {k}개로 고르게 나눌 수 없습니다 — 병합을 먼저 풀어 주세요"
DROP_CROSS = "지울 행에서 시작해 아래로 넘어가는 병합 칸이 있어 행을 지울 수 없습니다"
DROP_ALL = "표의 모든 행(열)을 지울 수는 없습니다"
COLS_CROSS_EDIT = "열 범위 경계에 걸친 병합 칸이 있어 열을 복사·삭제할 수 없습니다"
KEEP_RANGE = "너비를 지킬 열 범위는 복사·삭제할 열을 담아야 하고, 지운 뒤에도 열이 남아야 합니다"
KEEP_OUTSIDE = "남길 칸이 병합 범위 안에 없습니다"
COLS_CROSS_PICK = "선택 열 경계에 걸친 병합 칸이 있습니다 — 그 칸 전체가 들도록 선택을 넓혀 주세요"
MOVE_SAME = "옮길 자리가 지금 자리와 같습니다"
MOVE_CROSS = "옮길 자리나 선택 행 경계에 걸친 병합 칸이 있어 옮길 수 없습니다 — 그 칸 전체가 들도록 선택을 넓히거나 다른 자리에 놓아 주세요"


class Cell:
    __slots__ = ("el", "r", "c", "rs", "cs", "src", "rows")

    def __init__(self, el, r, c, rs=1, cs=1, src=None):
        self.el, self.r, self.c, self.rs, self.cs, self.src = el, r, c, rs, cs, src
        self.rows = {}  # docx: grid row -> this cell's w:tc in that row (its start tc or a vMerge continuation)

    def at(self, axis):
        """(first line, span) on axis."""
        return (self.r, self.rs) if axis == "r" else (self.c, self.cs)

    def put(self, axis, first, span):
        if axis == "r":
            self.r, self.rs = first, span
        else:
            self.c, self.cs = first, span

    def __repr__(self):
        return f"Cell({self.r},{self.c} {self.rs}x{self.cs})"


def rect(cells, n_rows, n_cols, r0, c0, r1, c1):
    """Cells of rows r0..r1 × columns c0..c1 in row-major order; ValueError when the range leaves the table or a cell
    sticks out of it."""
    if not (0 <= r0 <= r1 < n_rows and 0 <= c0 <= c1 < n_cols):
        raise ValueError(OUTSIDE)
    inside = []
    for x in cells:
        if x.r <= r1 and x.r + x.rs > r0 and x.c <= c1 and x.c + x.cs > c0:
            if x.r < r0 or x.r + x.rs - 1 > r1 or x.c < c0 or x.c + x.cs - 1 > c1:
                raise ValueError(CROSS)
            inside.append(x)
    if sum(x.rs * x.cs for x in inside) != (r1 - r0 + 1) * (c1 - c0 + 1):
        raise ValueError(HOLE)
    return sorted(inside, key=lambda x: (x.r, x.c))


def merge(cells, n_rows, n_cols, r0, c0, r1, c1):
    """One cell over the range: the top-left cell grows, the others leave `cells`.
    -> (top-left cell, bottom-right cell, removed cells in row-major order)."""
    inside = rect(cells, n_rows, n_cols, r0, c0, r1, c1)
    tl = inside[0]
    br = next(x for x in inside if x.r + x.rs - 1 == r1 and x.c + x.cs - 1 == c1)
    others = inside[1:]
    for x in others:
        cells.remove(x)
    tl.put("r", r0, r1 - r0 + 1)
    tl.put("c", c0, c1 - c0 + 1)
    return tl, br, others


def kept(inside, keep, cell_id):
    """merge with keep (매직 브러쉬 규칙 C9): the one cell of `inside` (the range's cells) whose id is `keep` — only its
    content goes into the merged cell. cell_id(el) -> the adapter's id of a cell element. ValueError when it is not there."""
    hit = [x for x in inside if cell_id(x.el) == keep]
    if not hit:
        raise ValueError(KEEP_OUTSIDE)
    return hit


def unmerge(cells, x):
    """x back to its grid: x keeps the top-left line, a new cell (src = x) for each other one. -> new cells, row-major."""
    new = [Cell(None, x.r + i, x.c + j, src=x) for i in range(x.rs) for j in range(x.cs) if i or j]
    x.rs = x.cs = 1
    cells += new
    return new


def insert(cells, axis, after, k, grow):
    """k new lines right after line `after`: later cells move on, the `grow` cells span the new lines too."""
    for x in cells:
        s, n = x.at(axis)
        if s > after:
            x.put(axis, s + k, n)
        elif x in grow:
            x.put(axis, s, n + k)
        if axis == "r" and x.rows:
            x.rows = {(i + k if i > after else i): tc for i, tc in x.rows.items()}


def split(cells, x, rows, cols):
    """x into rows × cols pieces (한글 「셀 나누기」). On an axis where x spans one line, new lines go in after it (the
    other cells on that line span them); a span divisible by the count is shared out.
    -> (new cells row-major — x stays the top-left piece, cells that grew, [(axis, line, k)] k lines added after line)."""
    if not (1 <= rows <= SPLIT_MAX and 1 <= cols <= SPLIT_MAX):
        raise ValueError(COUNT)
    grown, added, step = set(), [], {}
    for axis, k in (("r", rows), ("c", cols)):
        s, n = x.at(axis)
        if k == 1 or n % k == 0:
            step[axis] = n // k
        elif n == 1:
            g = {y for y in cells if y is not x and y.at(axis)[0] <= s < sum(y.at(axis))}
            insert(cells, axis, s, k - 1, g)
            grown |= g
            added.append((axis, s, k - 1))
            step[axis] = 1
        else:
            raise ValueError(UNEVEN.format(n=n, k=k))
    new = [Cell(None, x.r + i * step["r"], x.c + j * step["c"], step["r"], step["c"], src=x)
           for i in range(rows) for j in range(cols) if i or j]
    x.rs, x.cs = step["r"], step["c"]
    cells += new
    return new, grown, added


def clone(cells, n_rows, n_cols, r0, r1, c0, c1, above=False):
    """Copy rows r0..r1 of columns c0..c1 right below row r1 (spec ② §2 클론·행 추가). In those columns a cell inside
    the rows is copied and one covering all of them from above grows; outside them every cell on row r1 grows, so the
    new rows share it (선택 밖 칸 공유). above=True (끌어 복사 위로 — ② §2a): the copies go right above row r0, the
    originals move down, and outside the columns the cells on row r0 grow up over the new rows instead.
    ValueError when a merged cell crosses the range or nothing would be copied.
    -> (copies row-major, src = the copied cell; grown cells)."""
    if not (0 <= r0 <= r1 < n_rows and 0 <= c0 <= c1 < n_cols):
        raise ValueError(OUTSIDE)
    src, grow = [], set()
    edge = r0 if above else r1
    for x in cells:
        xr1, xc1 = x.r + x.rs - 1, x.c + x.cs - 1
        if xr1 < r0 or x.r > r1:
            continue
        if c0 <= x.c and xc1 <= c1:
            if r0 <= x.r and xr1 <= r1:
                src.append(x)
            elif x.r < r0 and xr1 >= r1:
                grow.add(x)
            else:
                raise ValueError(ROWS_CROSS)
        elif xc1 < c0 or x.c > c1:
            if x.r <= edge <= xr1:
                grow.add(x)
        else:
            raise ValueError(COLS_CROSS)
    if not src:
        raise ValueError(NOTHING)
    d = r1 - r0 + 1
    if above:
        top = {x for x in grow if x.r == r0}  # starts on r0: stays there and spans the new rows too (its own lines move down)
        insert(cells, "r", r0 - 1, d, grow - top)
        for x in top:
            x.r, x.rs = r0, x.rs + d
            if x.rows:
                x.rows = {r0: x.el, **{i: t for i, t in x.rows.items() if t is not x.el}}
        new = [Cell(None, x.r - d, x.c, x.rs, x.cs, src=x) for x in sorted(src, key=lambda x: (x.r, x.c))]
    else:
        insert(cells, "r", r1, d, grow)
        new = [Cell(None, x.r + d, x.c, x.rs, x.cs, src=x) for x in sorted(src, key=lambda x: (x.r, x.c))]
    cells += new
    return new, grow


def drop_rows(cells, n_rows, r0, r1):
    """Rows r0..r1 out of the grid (spec_구분_초기화 ② §4): cells inside them leave `cells`, cells from above across them
    span fewer rows, later cells move up. ValueError when a cell starts inside and reaches below r1.
    -> (removed cells, shrunk cells as [(cell, rows it lost)])."""
    if not (0 <= r0 <= r1 < n_rows):
        raise ValueError(OUTSIDE)
    if r1 - r0 + 1 == n_rows:
        raise ValueError(DROP_ALL)
    d, gone, shrunk = r1 - r0 + 1, [], []
    for x in cells:
        if x.r >= r0 and x.r <= r1 < x.r + x.rs - 1:
            raise ValueError(DROP_CROSS)
    for x in list(cells):
        xr1 = x.r + x.rs - 1
        if x.r > r1:
            x.r -= d
        elif x.r >= r0:
            gone.append(x)
            cells.remove(x)
        elif xr1 >= r0:
            lost = min(xr1, r1) - r0 + 1
            x.rs -= lost
            shrunk.append((x, lost))
        if x.rows:
            x.rows = {(i - d if i > r1 else i): tc for i, tc in x.rows.items() if not r0 <= i <= r1}
    return gone, shrunk


def drop_band(cells, n_rows, n_cols, r0, r1, c0, c1):
    """Rows r0..r1 out for the picked cells of columns c0..c1 (끌어 지우기 — ② §2a, 연결은 그래프를 따름): the grid rows go;
    a cell inside them goes, a cell across them spans fewer rows, and outside the columns a cell that starts inside them
    and reaches below keeps its text and starts on the first row after (inside the columns that is a ValueError — the
    pick must hold the whole merged cell). -> (removed cells, shrunk cells as [(cell, first lost row, last lost row)])."""
    if not (0 <= r0 <= r1 < n_rows and 0 <= c0 <= c1 < n_cols):
        raise ValueError(OUTSIDE)
    if r1 - r0 + 1 == n_rows:
        raise ValueError(DROP_ALL)
    for x in cells:
        xr1, xc1 = x.r + x.rs - 1, x.c + x.cs - 1
        if xr1 < r0 or x.r > r1 or xc1 < c0 or x.c > c1:
            continue
        if x.c < c0 or xc1 > c1:
            raise ValueError(COLS_CROSS_PICK)
        if r0 <= x.r and xr1 > r1:
            raise ValueError(DROP_CROSS)
    d, gone, shrunk = r1 - r0 + 1, [], []
    for x in list(cells):
        xr1 = x.r + x.rs - 1
        if x.r > r1:
            x.r -= d
            if x.rows:
                x.rows = {i - d: t for i, t in x.rows.items()}
        elif x.r >= r0 and xr1 <= r1:
            gone.append(x)
            cells.remove(x)
        elif x.r >= r0:  # 선택 열 밖에서 지울 행에서 시작해 아래로 — 글째 남고 지운 행 다음부터
            shrunk.append((x, x.r, r1))
            x.r, x.rs = r0, xr1 - r1
            if x.rows:
                x.rows = {**{i - d: t for i, t in x.rows.items() if i > r1}, r0: x.el}
        elif xr1 >= r0:
            shrunk.append((x, r0, min(xr1, r1)))
            x.rs -= min(xr1, r1) - r0 + 1
            if x.rows:
                x.rows = {(i - d if i > r1 else i): t for i, t in x.rows.items() if not r0 <= i <= r1}
    return gone, shrunk


def move_band(cells, n_rows, n_cols, r0, r1, c0, c1, to):
    """Rows r0..r1 of columns c0..c1 to the row line `to` (0..n_rows — right above row `to`; 끌어 옮기기 — ② §2a 「그 해당
    셀만 움직인다」): inside the columns the rows in between shift over, outside them nothing moves. ValueError when a cell
    crosses the columns' edge or, inside them, a row line the move cuts, or when `to` touches the rows (nothing moves).
    -> {old row: new row} of the rows that moved inside the columns."""
    if not (0 <= r0 <= r1 < n_rows and 0 <= c0 <= c1 < n_cols and 0 <= to <= n_rows):
        raise ValueError(OUTSIDE)
    if r0 <= to <= r1 + 1:
        raise ValueError(MOVE_SAME)
    d = r1 - r0 + 1
    lo, hi = (to, r1) if to < r0 else (r0, to - 1)
    perm = {r: (r + (to - r0 if to < r0 else to - 1 - r1) if r0 <= r <= r1 else r + (d if to < r0 else -d)) for r in range(lo, hi + 1)}
    band = []
    for x in cells:
        xr1, xc1 = x.r + x.rs - 1, x.c + x.cs - 1
        if xc1 < c0 or x.c > c1 or xr1 < lo or x.r > hi:
            continue
        if x.c < c0 or xc1 > c1:
            raise ValueError(COLS_CROSS_PICK)
        if any(x.r < b <= xr1 for b in (lo, r0, r1 + 1, hi + 1)):
            raise ValueError(MOVE_CROSS)
        band.append(x)
    for x in band:
        to_r = perm[x.r]
        if x.rows:
            x.rows = {i - x.r + to_r: t for i, t in x.rows.items()}
        x.r = to_r
    return perm


def clone_cols(cells, n_cols, c0, c1):
    """Copy columns c0..c1 (every row) right after c1 (spec_구분_초기화 ② §4 열 묶음). A cell inside the columns is copied,
    one covering all of them from the left grows. ValueError when a merged cell crosses the columns.
    -> (copies, src = the copied cell; grown cells)."""
    if not (0 <= c0 <= c1 < n_cols):
        raise ValueError(OUTSIDE)
    src, grow = [], set()
    for x in cells:
        xc1 = x.c + x.cs - 1
        if xc1 < c0 or x.c > c1:
            continue
        if c0 <= x.c and xc1 <= c1:
            src.append(x)
        elif x.c < c0 and xc1 >= c1:
            grow.add(x)
        else:
            raise ValueError(COLS_CROSS_EDIT)
    d = c1 - c0 + 1
    insert(cells, "c", c1, d, grow)
    new = [Cell(None, x.r, x.c + d, x.rs, x.cs, src=x) for x in sorted(src, key=lambda x: (x.r, x.c))]
    cells += new
    return new, grow


def drop_cols(cells, n_cols, c0, c1):
    """Columns c0..c1 out: cells inside them go, cells from the left across them span fewer columns, later cells move
    left. ValueError when a cell starts inside and reaches past c1, or every column would go.
    -> (removed cells, shrunk cells as [(cell, columns it lost)])."""
    if not (0 <= c0 <= c1 < n_cols):
        raise ValueError(OUTSIDE)
    if c1 - c0 + 1 == n_cols:
        raise ValueError(DROP_ALL)
    if any(c0 <= x.c <= c1 < x.c + x.cs - 1 for x in cells):
        raise ValueError(COLS_CROSS_EDIT)
    d, gone, shrunk = c1 - c0 + 1, [], []
    for x in list(cells):
        xc1 = x.c + x.cs - 1
        if x.c > c1:
            x.c -= d
        elif x.c >= c0:
            gone.append(x)
            cells.remove(x)
        elif xc1 >= c0:
            lost = min(xc1, c1) - c0 + 1
            x.cs -= lost
            shrunk.append((x, lost))
    return gone, shrunk


def refit(widths, a, b, total):
    """Columns a..b scaled so they add up to `total` again (proportional, integers — the last takes the rest)."""
    cur = sum(widths[a:b + 1]) or 1
    out = [w * total // cur for w in widths[a:b + 1]]
    out[-1] += total - sum(out)
    widths[a:b + 1] = out


def even(widths, spans):
    """Column spans [(c0, c1)…] side by side (each starting right after the previous) share their total width equally;
    columns inside a span keep their proportions. -> (new widths, (first c0, last c1) — the refit range)."""
    out, a, b = list(widths), spans[0][0], spans[-1][1]
    for (c0, c1), w in zip(spans, share(sum(widths[a:b + 1]), len(spans))):
        refit(out, c0, c1, w)
    return out, (a, b)


def col_widths(widths, c0, c1, keep, add):
    """Column widths after copying columns c0..c1 right after c1 (add=True) or dropping them. keep = (a, b): pre-op
    columns a..b, holding c0..c1, keep their total width — after the op a..b±d share it in proportion (refit); None:
    the table gets wider/narrower. -> (new widths, the refit range after the op or None)."""
    d = c1 - c0 + 1
    out = widths[:c1 + 1] + widths[c0:c1 + 1] + widths[c1 + 1:] if add else widths[:c0] + widths[c1 + 1:]
    if keep is None:
        return out, None
    a, b = int(keep[0]), int(keep[1])
    if not (0 <= a <= c0 and c1 <= b < len(widths)) or (not add and b - a + 1 == d):
        raise ValueError(KEEP_RANGE)
    total, b = sum(widths[a:b + 1]), b + d if add else b - d
    refit(out, a, b, total)
    return out, (a, b)


def squeeze(cells, n, axis):
    """Drop the lines of axis where no cell starts; the cells across such a line span one less (한글은 셀 합치기 뒤
    그런 줄·칸을 없앤다 — 빈 hp:tr 이 남으면 한글이 저장하다 멈춘다). -> dropped lines, high to low (old numbers)."""
    starts = {x.at(axis)[0] for x in cells}
    gone = [k for k in range(n) if k not in starts][::-1]
    for k in gone:
        for x in cells:
            s, m = x.at(axis)
            if s > k:
                x.put(axis, s - 1, m)
            elif s + m - 1 >= k:
                x.put(axis, s, m - 1)
    return gone


def sizes(cells, n, axis, size):
    """Per-line sizes (column widths / row heights) from the cells' sizes: one-line cells first (the largest), then a
    cell with one line still unknown, last an even share of what a cell leaves to its unknown lines. A size of 0 says
    nothing (한글 often stores 0 as a merged cell's height)."""
    out, known = [None] * n, [(x, v) for x in cells if (v := size(x)) > 0]
    for x, v in known:
        s, m = x.at(axis)
        if m == 1:
            out[s] = max(out[s] or 0, v)

    def rest(x, v):
        s, m = x.at(axis)
        unknown = [i for i in range(s, s + m) if out[i] is None]
        return unknown, max(0, v - sum(out[i] for i in range(s, s + m) if out[i] is not None))
    todo = True
    while todo:
        todo = False
        for x, v in known:
            unknown, left = rest(x, v)
            if len(unknown) == 1:
                out[unknown[0]], todo = left, True
    for x, v in known:
        unknown, left = rest(x, v)
        for i in unknown:
            out[i] = left // len(unknown)
    return [v or 0 for v in out]


def share(v, k):
    """v split into k near-equal integer parts (the last takes the remainder)."""
    parts = [v // k] * k
    parts[-1] += v - sum(parts)
    return parts


def result(ids, cell=None, new=(), removed=(), grown=(), mapping=None):
    """The adapters' common return value (spec ② §3)."""
    return {"cell": ids(cell) if cell is not None else None, "new": [ids(x) for x in new],
            "removed": list(removed), "grown": [ids(x) for x in sorted(grown, key=lambda x: (x.r, x.c))],
            "map": {ids(x.src): ids(x) for x in new} if mapping else {}}
