"""빈 필드 제거(spec_헤딩_추출 ② §16) — 표 하나에서 **필드가 모두 빈 행·열**을 찾아 지운다. 사용자 2026-11-10 "테이블 … 모서리 클릭하면, 빈필드 제거하기".

- **칸 역할**은 수식 판정(§14 `table_excel`)과 같은 길로 정한다 — 지금 문서의 그 표만 1단계 꼴 레코드로 만들어 3단계 스크립트 초안(`heading_tables.draft`)과
  §9 표 의미(`heading_calc.annotate`)를 돌린다. 3단계 실행을 기다리지 않고 LLM 도 안 쓴다. hwpx 만.
- **빈 필드** = 역할 field 인 칸 가운데 글이 없거나 자리표시(「0,000」·「○○」·1단계 kind placeholder)뿐인 칸. 칸 안 표·그림이 있으면 빈 칸이 아니다. 「-」 는 값(0)이다.
  자리표시 줄 아래에 글을 써 넣은 칸은 채워진 칸이다(`cell_empty`). 행헤더·열헤더·제목·안내 칸의 글과 칸 음영은 「채워짐」 으로 세지 않는다 — 필드만 본다.
- **빈 행(열)** = 그 줄에 걸친 **채우는 필드**(수식으로 셈하는 칸 — 합계·비율 — 을 뺀 필드)가 하나 이상 있고 모두 빈 줄. 헤더뿐인 줄·제목·안내·간격 줄,
  합계·비율 헤더가 걸친 줄(「계」 행·「비율」 열)은 대상이 아니다. 필드가 하나도 안 채워진 표(빈 양식)는 지울 줄을 정하지 않는다(`allEmpty`).
- **지우기**는 뒤에서부터 이어진 묶음마다. 지울 행에서 시작해 아래로 넘어가는 합친 칸(행 묶음 제목)은 글째 남기고 남은 행으로 줄인다(`delete_rows(cols=…)` —
  `table_grid.drop_band`). 그래도 합친 칸에 걸려 못 지우는 줄은 건너뛴다(`skip*`). 열을 지운 폭은 남은 열이 나눠 가져 표 폭은 그대로.
"""
from app import heading_calc as HC
from app import heading_tables as HT
from app import table_excel as TX
from app import table_grid as grid
from app import table_heads, table_ops

_SUM_KINDS = ("total", "ratio")


def cell_empty(x):
    """필드 칸이 비었는가 — 글이 없거나 **자리표시뿐**. 칸 안 표·그림(개체 문단)이 있으면 빈 칸이 아니다.
    자리표시뿐 = 칸 글 전체가 숫자 자리표시 꼴(「0,000」·「00%」·「○○」 — `heading_calc._PH`)이거나, 글 문단이 모두 1단계 kind placeholder(「○○대학교」·「XXX」).
    §9 `parse_num(text, kinds)` 를 그대로 쓰지 않는다 — 그것은 자리표시 문단이 하나라도 있고 수 문단이 없으면 자리표시로 보아(수 판정용), 자리표시 줄 아래에 글을 써 넣은 칸까지
    빈 칸이 된다. 여기서는 지우는 판단이라 쓴 글이 한 문단이라도 있으면 채워진 칸이다."""
    if x.get("nested") or (x.get("kinds") or {}).get("object"):
        return False
    text = (x.get("textFull") or "").strip()
    if not text:
        return True
    kinds = {k for k, v in (x.get("kinds") or {}).items() if v and k != "empty"}
    return kinds == {"placeholder"} or bool(HC.parse_num(text).get("placeholder"))


def _span(x, axis):
    return (x["row"], x["rs"]) if axis == "r" else (x["col"], x["cs"])


def _empty_lines(cells, inputs, empty, n, axis):
    """축(axis "r" 행 · "c" 열)의 빈 줄 번호 — 채우는 필드가 걸쳐 있고 모두 비었으며 합계·비율 헤더가 안 걸친 줄."""
    has, filled, summed = [False] * n, [False] * n, [False] * n
    head = "rowhead" if axis == "r" else "colhead"
    for x in cells:
        a, k = _span(x, axis)
        lines = range(max(0, a), min(n, a + k))
        if x["id"] in inputs:
            for i in lines:
                has[i] = True
                filled[i] = filled[i] or x["id"] not in empty
        elif x.get("role") == head and (x.get("basisKind") in _SUM_KINDS or any(b in _SUM_KINDS for b in x.get("basis") or [])):
            for i in lines:
                summed[i] = True
    return [i for i in range(n) if has[i] and not filled[i] and not summed[i]]


def _grow_groups(cells, rows, n):
    """행 묶음째 비었으면 딸린 줄도 함께 — 여러 행에 걸친 행헤더(묶음 제목)가 빈 행에서 시작하고, 걸친 나머지 행이 모두 빈 행이거나 **딸린 줄**
    (그 줄에서 시작하는 칸이 안내·간격뿐 — 항목 아래 「작성 가이드라인」 줄)이면 그 행들도 빈 행으로 센다. 값 줄만 지워 제목과 안내만 남는 것을 막는다."""
    starts = [[] for _ in range(n)]
    for x in cells:
        if 0 <= x["row"] < n:
            starts[x["row"]].append(x.get("role"))
    dep = [bool(rs) and all(r in ("note", "spacer") for r in rs) for rs in starts]
    out, changed = set(rows), True
    while changed:
        changed = False
        for x in cells:
            if x.get("role") != "rowhead" or x["rs"] < 2 or x["row"] not in out:
                continue
            ext = range(x["row"], min(n, x["row"] + x["rs"]))
            if all(i in out or dep[i] for i in ext) and not all(i in out for i in ext):
                out.update(ext)
                changed = True
    return sorted(out)


def _names(cells, lines, axis, limit=24):
    """줄 번호 → 그 줄의 헤더 글(행 = 가장 안쪽 행헤더, 열 = 가장 아래 열헤더; 없으면 그 줄에서 시작하는 첫 글 칸) — 화면이 「4행 「연구활동비」」 로 보인다."""
    head = "rowhead" if axis == "r" else "colhead"
    other = "c" if axis == "r" else "r"
    out = {}
    for i in lines:
        on = [x for x in cells if _span(x, axis)[0] <= i < sum(_span(x, axis)) and (x.get("textFull") or "").strip()]
        heads = [x for x in on if x.get("role") in (head, "corner")]
        pick = max(heads, key=lambda x: _span(x, other)[0]) if heads else next((x for x in sorted(on, key=lambda x: _span(x, other)[0]) if _span(x, axis)[0] == i), None)
        if pick is not None:
            out[str(i)] = " ".join(pick["textFull"].split())[:limit]
    return out


def _runs(lines):
    """줄 번호들 → 이어진 묶음 [(a, b)…] — 뒤에서부터(앞 줄 번호가 안 밀리게)."""
    out = []
    for i in sorted(lines):
        if out and out[-1][1] == i - 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [tuple(r) for r in reversed(out)]


def _each(lines, drop):
    """lines 를 묶음마다 drop(a, b) — 묶음째 못 지우면(ValueError: 합친 칸에 걸림) 한 줄씩 다시. → (지운 줄, 못 지운 줄) 오름차순."""
    done, skip = [], []
    for a, b in _runs(lines):
        try:
            drop(a, b)
            done += range(a, b + 1)
        except ValueError:
            for i in range(b, a - 1, -1):
                try:
                    drop(i, i)
                    done.append(i)
                except ValueError:
                    skip.append(i)
    return sorted(done), sorted(skip)


def band(cells, nc, r0, r1):
    """행 r0..r1 을 지울 때 넘길 열 띠 — 그 행에서 시작해 아래로 넘어가는 합친 칸(행 묶음 제목)을 피한 가장 넓은 이어진 열 범위 (c0, c1).
    그런 칸이 없으면 None(행 통째). cells = table_grid.Cell 들. 구현은 `table_grid.band`(행 전체 지우기 — spec_owpml_편집 ② §5-2 — 와 같이 씀)."""
    return grid.band(cells, nc, r0, r1)


def analyze(doc, tid, store=None, doc_key=None, roles=None):
    """표의 빈 필드 줄 → {table, rows, cols, fields(채우는 필드 수), emptyFields, allEmpty, emptyRows[], emptyCols[], rowNames{줄: 헤더 글}, colNames, note?} —
    지울 수 있는지는 아직 안 본다. 표가 아니면 None, 너무 크면 ValueError. roles = 사용자 헤더 지정(spec_owpml_편집 ② §5-4 — `table_excel._analyze`)."""
    stage1 = TX.records(doc, tid, store, doc_key)
    if stage1 is None:
        return None
    tb = next((t for t in HT.collect(stage1) if t["id"] == tid), None)
    out = {"table": tid, "rows": 1, "cols": 1, "fields": 0, "emptyFields": 0, "allEmpty": False, "emptyRows": [], "emptyCols": [], "rowNames": {}, "colNames": {}}
    if tb is None:
        return {**out, "note": "1칸 표(글상자)에는 필드가 없습니다"}
    if len(tb["cells"]) > TX.MAX_CELLS:
        raise ValueError(f"표가 너무 큽니다(칸 {len(tb['cells'])} > {TX.MAX_CELLS})")
    _subs, sem = TX._analyze(tb, roles)
    targets = {f["cell"] for f in sem["formulas"]}  # 수식으로 셈하는 칸(합계·비율·코드 식) — 사람이 채우는 칸이 아니다
    inputs = {x["id"] for x in tb["cells"] if x.get("role") == "field" and x["id"] not in targets}
    empty = {x["id"] for x in tb["cells"] if x["id"] in inputs and cell_empty(x)}
    out.update(rows=tb["rows"], cols=tb["cols"], fields=len(inputs), emptyFields=len(empty))
    if not inputs:
        return {**out, "note": "채우는 필드가 없는 표입니다"}
    if len(empty) == len(inputs):
        return {**out, "allEmpty": True, "note": "필드가 모두 비어 있습니다(빈 양식) — 지울 줄을 정하지 않습니다"}
    out["emptyRows"] = _grow_groups(tb["cells"], _empty_lines(tb["cells"], inputs, empty, tb["rows"], "r"), tb["rows"])
    out["emptyCols"] = _empty_lines(tb["cells"], inputs, empty, tb["cols"], "c")
    out["rowNames"] = _names(tb["cells"], out["emptyRows"], "r")
    out["colNames"] = _names(tb["cells"], out["emptyCols"], "c")
    return out


def _sim(doc, tid):
    """문서 표의 격자 사본(요소 없이) — 미리보기에서 지울 수 있는지만 본다."""
    _tbl, cells, nr, nc = doc._tgrid(doc._ids.get(tid))
    return [grid.Cell(None, x.r, x.c, x.rs, x.cs) for x in cells], nr, nc


def plan(doc, tid, store=None, doc_key=None, roles=None):
    """미리보기(문서는 안 바뀜) — analyze + 지울 수 있는 줄만 남기고 못 지우는 줄은 skipRows·skipCols 로. 행과 열은 따로 본다(둘 다 지울 때의 열은 행을 지운 뒤 다시 셈)."""
    out = analyze(doc, tid, store, doc_key, roles)
    if out is None:
        return None
    out.update(skipRows=[], skipCols=[])
    if out["emptyRows"]:
        cells, nr, nc = _sim(doc, tid)
        size = [nr]

        def drop_rows(a, b):
            cols = band(cells, nc, a, b)
            if cols is None:
                grid.drop_rows(cells, size[0], a, b)
            else:
                grid.drop_band(cells, size[0], nc, a, b, *cols)
            size[0] -= b - a + 1
        out["emptyRows"], out["skipRows"] = _each(out["emptyRows"], drop_rows)
    if out["emptyCols"]:
        cells, nr, nc = _sim(doc, tid)
        size = [nc]

        def drop_cols(a, b):
            grid.drop_cols(cells, size[0], a, b)
            size[0] -= b - a + 1
        out["emptyCols"], out["skipCols"] = _each(out["emptyCols"], drop_cols)
    return out


def apply(doc, tid, rows=True, cols=True, store=None, doc_key=None, roles=None):
    """빈 행(rows)·빈 열(cols)을 문서에서 지운다 → {rows[], cols[], skipRows[], skipCols[]}(지운 줄 번호 — 지우기 전 격자 기준, 열은 행을 지운 뒤 격자 기준).
    어댑터 `delete_rows`·`delete_cols` 는 격자 검사에서 막히면 XML 을 건드리기 전에 ValueError — 그 줄만 건너뛴다. 부르는 쪽이 트랜잭션(`server._edit`)으로 감싼다."""
    out = {"rows": [], "cols": [], "skipRows": [], "skipCols": []}
    if rows:
        a = analyze(doc, tid, store, doc_key, roles)
        if a is None:
            raise ValueError("그 표가 지금 문서에 없습니다")

        def drop_rows(r0, r1):
            _tbl, cells, _nr, nc = doc._tgrid(doc._ids.get(tid))
            doc.delete_rows(tid, r0, r1, cols=band(cells, nc, r0, r1))
        out["rows"], out["skipRows"] = _each(a["emptyRows"], drop_rows)
    if cols:
        a = analyze(doc, tid, store, doc_key, roles)  # 행을 지운 뒤의 격자로 다시(행을 지우면 시작하는 칸이 없는 열이 접혀 열 번호가 바뀔 수 있다)
        if a is None:
            raise ValueError("그 표가 지금 문서에 없습니다")

        def drop_cols(c0, c1):
            nc = int(doc._ids[tid].get("colCnt"))
            flags = table_heads.fields_of(doc, tid, roles, doc_key=doc_key)  # 열 폭 규칙(spec_owpml_편집 ② §5-1): 헤더 열 폭 그대로 · 남은 필드 열이 비율대로 — 표 폭 그대로
            doc.delete_cols(tid, c0, c1, keep=table_ops.col_keep(flags, nc, c0, c1, add=False) if flags else (0, nc - 1))
        out["cols"], out["skipCols"] = _each(a["emptyCols"], drop_cols)
    if out["rows"] or out["cols"]:
        doc._touch(doc._ids[tid])
    return out
