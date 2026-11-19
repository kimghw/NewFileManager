"""빈 필드 제거(spec_헤딩_추출 ② §16) — 표 하나에서 **필드가 모두 빈 행·열**을 찾아 지운다. 사용자 2026-11-10 "테이블 … 모서리 클릭하면, 빈필드 제거하기".

- **칸 역할**은 수식 판정(§14 `table_excel`)과 같은 길로 정한다 — 지금 문서의 그 표만 1단계 꼴 레코드로 만들어 3단계 스크립트 초안(`heading_tables.draft`)과
  §9 표 의미(`heading_calc.annotate`)를 돌린다. 3단계 실행을 기다리지 않고 LLM 도 안 쓴다. hwpx 만.
- **빈 필드** = 역할 field 인 칸 가운데 글이 없거나 자리표시(「0,000」·「○○」·1단계 kind placeholder)뿐인 칸. 칸 안 표·그림이 있으면 빈 칸이 아니다. 「-」 는 값(0)이다.
  자리표시 줄 아래에 글을 써 넣은 칸은 채워진 칸이다(`cell_empty`). 행헤더·열헤더·제목·안내 칸의 글과 칸 음영은 「채워짐」 으로 세지 않는다 — 필드만 본다.
- **빈 행(열)** = 그 줄에 걸친 **채우는 필드**(수식으로 셈하는 칸 — 합계·비율 — 을 뺀 필드)가 하나 이상 있고 모두 빈 줄. 헤더뿐인 줄·제목·안내·간격 줄,
  합계·비율 헤더가 걸친 줄(「계」 행·「비율」 열)은 대상이 아니다. 필드가 하나도 안 채워진 표(빈 양식)는 지울 줄을 정하지 않는다(`allEmpty`).
- **작성 글 보호**(spec_테이블매니저 ② §4 「지우거나 쓰는 도구」 ⓐ — `_written`·`_guard`): 역할이 헤더(열헤더·행헤더·귀퉁이)여도 **성격이 필드인 칸**(긴 글·문장·값 — `nature == "field"`)에
  글이 있으면(자리표시뿐이 아님) 그 칸의 줄은 채워진 줄이다 — 「내용」 열 아래 사람이 쓴 긴 글이 헤더 열 낱말 규칙으로 행헤더가 되어도 그 행을 지우지 않는다.
  사람이 그 칸의 역할을 지정했으면(`roles`) 지정이 먼저다(보호하지 않는다). 에이전트 판단 둘(2026-11-19 샘플 양식에서 잰 것 — 코디네이터 확인 전):
  ⓘ 순번 칸(「1」·「①」·「가」 — 초안이 순번이라서 헤더 열로 본 값)은 작성 글이 아니라 보호하지 않는다(번호 붙은 표의 빈 줄이 모두 후보에서 빠진다)
  ⓙ 여러 줄에 걸친 칸은 걸친 줄이 **모두** 지울 줄일 때(= 칸이 통째로 없어질 때)만 막는다 — 남는 줄이 있으면 칸이 줄어들 뿐 글은 남는다
  (양식의 묶음 제목 「참여 연구자 (기존)」 = 짧은 글 3문단이라 성격이 필드 — 걸친 줄을 다 막으면 그 표의 빈 사람 줄이 후보에서 빠진다).
- **빈 것으로 본 까닭**(같은 절 ⓑ — `_why`): 결과의 `why {rows: {줄: [자리표시 글…]}, cols}` — 줄마다 그 줄의 빈 필드에 든 자리표시 글(「00%」·「0,000」 은 값일 수도 있다 — 화면이 줄 이름 옆에 보인다).
- **지우기**는 뒤에서부터 이어진 묶음마다. 지울 행에서 시작해 아래로 넘어가는 합친 칸(행 묶음 제목)은 글째 남기고 남은 행으로 줄인다(`delete_rows(cols=…)` —
  `table_grid.drop_band`). 그래도 합친 칸에 걸려 못 지우는 줄은 건너뛴다(`skip*`). 열을 지운 폭은 남은 열이 나눠 가져 표 폭은 그대로.
"""
from app import heading_calc as HC
from app import heading_tables as HT
from app import table_excel as TX
from app import table_grid as grid
from app import table_heads, table_ops

_SUM_KINDS = ("total", "ratio")
_HEADS = ("colhead", "rowhead", "corner")
_USER_ROLES = ("rowhead", "colhead", "field")  # 사람의 헤더 지정으로 쓰이는 값(`table_excel._analyze` 와 같다)
WHY_MAX = 3      # 줄마다 보이는 자리표시 글 수
WHY_TEXT = 24    # 자리표시 글 하나의 길이(줄 이름 `_names` 와 같다)


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


def _written(cells, roles=None):
    """작성 글 보호(spec_테이블매니저 ② §4 ⓐ)의 대상 칸 id — 역할은 헤더(열헤더·행헤더·귀퉁이)인데 **성격이 필드**(긴 글·문장·값 — `heading_tables.nature`)이고
    글이 있는(자리표시뿐이 아닌) 칸. 빼는 것: 사람이 역할을 지정한 칸(roles — 지정이 먼저: 헤더로 지정했으면 전처럼 헤더) ·
    순번 칸(`heading_tables._ORDINAL` 꼴 「1」·「①」·「가」 — 초안이 순번이라서 헤더 열로 본 값이지 작성 글이 아니다: 번호 붙은 목록 표의 빈 줄은 전처럼 지울 줄)."""
    user = {i for i, r in (roles or {}).items() if r in _USER_ROLES}
    return {x["id"] for x in cells if x.get("role") in _HEADS and x.get("nature") == "field" and x["id"] not in user
            and not cell_empty(x) and not HT._ORDINAL.match(x.get("textFull") or "")}


def _guard(cells, kept, lines, n, axis):
    """lines(지울 줄)를 지우면 **통째로 없어지는** 작성 글 칸(kept — `_written`)이 걸친 줄 집합 — 이 줄들은 채워진 줄이다(지울 줄에서 뺀다).
    한 줄짜리 칸은 그 줄이 지울 줄이면 곧 없어지는 칸이다. 여러 줄에 걸친 칸(행 묶음 제목 꼴)은 걸친 줄이 **모두** 지울 줄일 때만 — 남는 줄이 있으면
    칸은 그 줄로 줄어들 뿐 글은 남으므로(`table_grid.drop_band`·위에서 내려온 합친 칸) 막지 않는다: 양식의 묶음 제목 「참여 연구자 (기존)」(짧은 글 3문단 = 성격 필드)
    아래 빈 사람 줄은 전처럼 지울 줄. 지울 줄이 줄면 없어지는 칸도 줄 뿐이라 한 번 보면 된다."""
    gone, out = set(lines), set()
    for x in cells:
        if x["id"] in kept:
            a, k = _span(x, axis)
            span = range(max(0, a), min(n, a + k))
            if len(span) and all(i in gone for i in span):
                out.update(span)
    return out


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


def _grow_groups(cells, rows, n, keep=()):
    """행 묶음째 비었으면 딸린 줄도 함께 — 여러 행에 걸친 행헤더(묶음 제목)가 빈 행에서 시작하고, 걸친 나머지 행이 모두 빈 행이거나 **딸린 줄**
    (그 줄에서 시작하는 칸이 안내·간격뿐 — 항목 아래 「작성 가이드라인」 줄)이면 그 행들도 빈 행으로 센다. 값 줄만 지워 제목과 안내만 남는 것을 막는다.
    keep = 작성 글 때문에 남기는 행(`_guard`) — 그런 행이 낀 묶음은 키우지 않는다(보호된 줄이 묶음에 딸려 지워지지 않게)."""
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
            if any(i in keep for i in ext):
                continue
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


def _why(cells, empty, lines, axis):
    """줄 번호 → 그 줄을 빈 줄로 보게 한 **자리표시 글**(spec_테이블매니저 ② §4 ⓑ) — 그 줄에 걸친 빈 필드에 든 글을 칸 차례로, 중복 없이 WHY_MAX 개까지.
    글이 아예 없는 칸뿐인 줄(딸린 안내 줄 포함)은 빈 목록. 열쇠 꼴은 `_names` 와 같다. 「00%」·「0,000」 같은 수 자리표시 꼴은 사람이 쓴 값일 수도 있어 화면이 줄 이름 옆에 보인다."""
    out = {str(i): [] for i in lines}
    for x in cells:
        if x["id"] not in empty:
            continue
        text = " ".join((x.get("textFull") or "").split())[:WHY_TEXT]
        if not text:
            continue
        a, k = _span(x, axis)
        for i in range(a, a + k):
            got = out.get(str(i))
            if got is not None and text not in got and len(got) < WHY_MAX:
                got.append(text)
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
    """표의 빈 필드 줄 → {table, rows, cols, fields(채우는 필드 수), emptyFields, allEmpty, emptyRows[], emptyCols[], rowNames{줄: 헤더 글}, colNames,
    why{rows: {줄: [자리표시 글…]}, cols}, note?} — 지울 수 있는지는 아직 안 본다. 표가 아니면 None, 너무 크면 ValueError.
    roles = 사용자 헤더 지정(spec_owpml_편집 ② §5-4 — `table_excel._analyze`)."""
    stage1 = TX.records(doc, tid, store, doc_key)
    if stage1 is None:
        return None
    return analyze_table(next((t for t in HT.collect(stage1) if t["id"] == tid), None), tid, roles)


def analyze_table(tb, tid, roles=None):
    """`analyze` 의 몸통(문서 없이) — tb = `heading_tables.collect` 꼴의 표(1칸 표면 None). 여기서 초안 역할·표 의미를 매긴다(`table_excel._analyze` — tb 의 칸에 적힌다)."""
    out = {"table": tid, "rows": 1, "cols": 1, "fields": 0, "emptyFields": 0, "allEmpty": False, "emptyRows": [], "emptyCols": [], "rowNames": {}, "colNames": {},
           "why": {"rows": {}, "cols": {}}}
    if tb is None:
        return {**out, "note": "1칸 표(글상자)에는 필드가 없습니다"}
    if len(tb["cells"]) > TX.MAX_CELLS:
        raise ValueError(f"표가 너무 큽니다(칸 {len(tb['cells'])} > {TX.MAX_CELLS})")
    _subs, sem = TX._analyze(tb, roles)
    cells = tb["cells"]
    targets = {f["cell"] for f in sem["formulas"]}  # 수식으로 셈하는 칸(합계·비율·코드 식) — 사람이 채우는 칸이 아니다
    inputs = {x["id"] for x in cells if x.get("role") == "field" and x["id"] not in targets}
    empty = {x["id"] for x in cells if x["id"] in inputs and cell_empty(x)}
    out.update(rows=tb["rows"], cols=tb["cols"], fields=len(inputs), emptyFields=len(empty))
    if not inputs:
        return {**out, "note": "채우는 필드가 없는 표입니다"}
    if len(empty) == len(inputs):
        return {**out, "allEmpty": True, "note": "필드가 모두 비어 있습니다(빈 양식) — 지울 줄을 정하지 않습니다"}
    kept = _written(cells, roles)  # 작성 글이 든 헤더 역할 칸 — 이 칸이 통째로 없어지게 되는 줄은 채워진 줄(`_guard`)
    base = _empty_lines(cells, inputs, empty, tb["rows"], "r")
    rows = _grow_groups(cells, base, tb["rows"])
    keep = _guard(cells, kept, rows, tb["rows"], "r")
    if keep:
        rows = _grow_groups(cells, [i for i in base if i not in keep], tb["rows"], keep)
    cols = _empty_lines(cells, inputs, empty, tb["cols"], "c")
    keep = _guard(cells, kept, cols, tb["cols"], "c")
    out["emptyRows"], out["emptyCols"] = rows, [i for i in cols if i not in keep]
    out["rowNames"] = _names(cells, out["emptyRows"], "r")
    out["colNames"] = _names(cells, out["emptyCols"], "c")
    out["why"] = {"rows": _why(cells, empty, out["emptyRows"], "r"), "cols": _why(cells, empty, out["emptyCols"], "c")}
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
