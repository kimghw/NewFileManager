"""표 헤더 지정 · 헤더 열/필드 열 판정 · 표 나누기 자리(spec_owpml_편집 ② §5 — §5-1 열 폭 규칙 · §5-3 표 나누기 · §5-4 헤더 지정). 표 모듈.

- **칸 역할**은 그 표만 그 자리에서 판정한다 — 3단계 스크립트 초안(`table_excel.records` → `heading_tables.collect`·`draft`, LLM·3단계 실행 없음) 위에 **사용자 지정**을 덮는다(`table`).
- **필드 열** = 필드 칸이 걸친 격자 열(전체 너비 한 칸은 안 셈), **헤더 열** = 그 밖(`field_cols`). 왼쪽부터 이어진 헤더 열 수 = `head_cols`.
- **사용자 지정**: 작업 폴더 `table_heads.json` {version, updated, tables: {표 id: {칸 id: "rowhead" | "colhead" | "field"}}} — 작업 저장이 꺼져 있거나 작업 폴더가 없으면 메모리.
  문서를 바꾸지 않는다(실행 취소와 무관). 지정한 칸이 문서에서 없어지면 그 표를 다음에 저장할 때 버린다.
- **도장 · 보류**(spec_테이블매니저 ② §3 「사람의 헤더 지정」): 지정할 때 그 칸의 자리와 글을 `stamps: {표 id: {칸 id: {at: [행, 열, 행 병합, 열 병합], text}}}` 로 같이 적어 두고(`stamp` · `put(stamps=)`),
  읽을 때 지금 칸과 견줘 다르면 그 지정을 **보류**한다(`check` → 유효 · 보류). 구조 편집 · 실행 취소 뒤 같은 칸 id 가 다른 칸을 가리키게 된 지정이 문서를 바꾸는 데 쓰이지 않게 하려는 것이다
  (열을 넣으면 옛 id 가 빈 칸에 남고 글은 새 id 로 간다 · 실행 취소 뒤 새 칸이 옛 id 를 다시 받는다). 도장이 없는 옛 지정은 유효로 본다.
- `layout`: 화면(메뉴·미리보기·표 나누기 목록)이 읽는 한 표의 판정 — 필드 열 표시 · 헤더 열 수 · 필드 열 단위 · 이어진 표(앞·뒤).
hwpx 만(칸 역할 판정이 hwpx 레코드 기반). 끝점은 `app/tables_api.py`."""
import threading
import time

from app import heading_tables as HT
from app import table_excel as TX
from app import table_grid as grid
from app import works

ROLES = ("rowhead", "colhead", "field")
ROLE_KO = {"rowhead": "행헤더", "colhead": "열헤더", "field": "필드"}
CELLS_MAX = 2000  # 한 번에 지정하는 칸 수
_LOCK = threading.RLock()
_MEMORY = {}  # {작업 id: 기록} — 저장 끔·작업 폴더 없음


# ---- 사용자 지정 저장 ------------------------------------------------------------------------------------------

def _path(wid):
    d = works.folder(wid)
    return None if d is None else d / "table_heads.json"


def _stamp_text(cell):
    """도장에 적는 견줄 글 — 칸 글에서 공백을 뺀 앞 60자."""
    t = cell.get("textFull") if cell.get("textFull") is not None else cell.get("text")
    return "".join((t or "").split())[:60]


def stamp(cell):
    """칸의 도장 — 지정할 때의 자리와 글(spec_테이블매니저 ② §3 「사람의 헤더 지정」). cell = heading_tables.collect 꼴(row · col · rs · cs · textFull)."""
    return {"at": [cell["row"], cell["col"], cell["rs"], cell["cs"]], "text": _stamp_text(cell)}


def _stamps_of(rec):
    """기록의 도장 {표 id: {칸 id: {at, text}}} — 꼴이 틀린 것은 버린다(도장이 없으면 그 지정은 옛 지정 = 유효)."""
    out = {}
    raw = rec.get("stamps") if isinstance(rec, dict) else None
    for tid, cells in (raw.items() if isinstance(raw, dict) else ()):
        got = {}
        for c, s in (cells.items() if isinstance(cells, dict) else ()):
            at = s.get("at") if isinstance(s, dict) else None
            if isinstance(c, str) and isinstance(at, list) and len(at) == 4 and all(isinstance(v, int) for v in at) and isinstance(s.get("text"), str):
                got[c] = {"at": list(at), "text": s["text"]}
        if isinstance(tid, str) and got:
            out[tid] = got
    return out


def load(wid):
    """{version, updated, tables: {표 id: {칸 id: 역할}}, stamps: {표 id: {칸 id: 도장}}} — 없거나 못 읽으면 빈 기록."""
    with _LOCK:
        p = _path(wid)
        rec = _MEMORY.get(wid) if p is None or not p.is_file() else works._read_json(p)
    out = {"version": 0, "updated": None, "tables": {}, "stamps": _stamps_of(rec)}
    if isinstance(rec, dict):
        try:
            out["version"] = int(rec.get("version") or 0)
        except (TypeError, ValueError):
            pass
        out["updated"] = rec.get("updated")
        for tid, cells in (rec.get("tables") or {}).items() if isinstance(rec.get("tables"), dict) else ():
            got = {c: r for c, r in cells.items() if isinstance(c, str) and r in ROLES} if isinstance(cells, dict) else {}
            if isinstance(tid, str) and got:
                out["tables"][tid] = got
    out["stamps"] = {t: {c: s for c, s in cs.items() if c in out["tables"].get(t, ())} for t, cs in out["stamps"].items() if t in out["tables"]}  # 지정 없는 도장은 버린다
    out["stamps"] = {t: cs for t, cs in out["stamps"].items() if cs}
    return out


def get(wid, tid):
    """표 tid 의 지정 {칸 id: 역할}(없으면 빈 것) — **모든** 지정(보류 여부를 안 본다: 옛 호출자용). 문서를 바꾸는 길은 `check` 의 유효한 지정만 쓴다."""
    return dict(load(wid)["tables"].get(tid) or {})


def check(wid, tid, tb):
    """표 tid 의 지정을 지금 표와 견줘 → (유효 {칸 id: 역할}, 보류 [{cell, role, why}])(spec_테이블매니저 ② §3 「사람의 헤더 지정」).
    tb = 지금 표(heading_tables.collect 꼴 — 칸마다 id · row · col · rs · cs · textFull). 도장의 자리나 글이 지금 그 칸과 다르면 보류(why 「자리가 바뀜」 | 「글이 바뀜」) —
    쓰지 않고, 버리지도 않는다(다시 지정하거나 풀 때까지). 도장이 없는 옛 지정은 유효. 지금 표에 없는 칸의 지정은 어느 쪽에도 넣지 않는다(다음 저장 때 버려진다)."""
    rec = load(wid)
    roles, stamps = rec["tables"].get(tid) or {}, rec["stamps"].get(tid) or {}
    now = {x["id"]: x for x in (tb or {}).get("cells") or ()}
    valid, held = {}, []
    for cid, role in roles.items():
        x = now.get(cid)
        if x is None:
            continue
        s = stamps.get(cid)
        if s is None:
            valid[cid] = role
        elif s["at"] != [x["row"], x["col"], x["rs"], x["cs"]]:
            held.append({"cell": cid, "role": role, "why": "자리가 바뀜"})
        elif s["text"] != _stamp_text(x):
            held.append({"cell": cid, "role": role, "why": "글이 바뀜"})
        else:
            valid[cid] = role
    return valid, held


def put(wid, tid, cells, role, alive=None, stamps=None):
    """칸들의 지정을 role(None = 풀기 — 자동 판정으로)로 → 그 표의 새 지정. alive = 지금 그 표에 있는 칸 id(주면 없어진 칸의 지정을 버린다).
    stamps = {칸 id: 도장(`stamp`)} — 주면 그 칸의 지정에 도장을 같이 적는다(안 준 칸은 도장 없이 = 옛 지정처럼 유효 · 그 칸의 옛 도장은 지운다).
    ValueError: 값이 틀림."""
    if role is not None and role not in ROLES:
        raise ValueError(f"role 은 {'·'.join(ROLES)} 또는 null(지정 풀기)")
    if not isinstance(cells, (list, tuple)) or not cells or len(cells) > CELLS_MAX or not all(isinstance(c, str) and c for c in cells):
        raise ValueError(f"cells 는 칸 id 1~{CELLS_MAX}개")
    with _LOCK:
        rec = load(wid)
        cur = dict(rec["tables"].get(tid) or {})
        marks = dict(rec["stamps"].get(tid) or {})
        if alive is not None:
            cur = {c: r for c, r in cur.items() if c in alive}
        for c in cells:
            marks.pop(c, None)  # 다시 지정 · 풀기 → 옛 도장은 지운다(새 도장은 아래에서)
            if role is None:
                cur.pop(c, None)
            else:
                cur[c] = role
                s = (stamps or {}).get(c)
                if isinstance(s, dict) and isinstance(s.get("at"), list) and len(s["at"]) == 4 and isinstance(s.get("text"), str):
                    marks[c] = {"at": [int(v) for v in s["at"]], "text": s["text"]}
        marks = {c: s for c, s in marks.items() if c in cur}
        if cur:
            rec["tables"][tid] = cur
        else:
            rec["tables"].pop(tid, None)
        if marks:
            rec["stamps"][tid] = marks
        else:
            rec["stamps"].pop(tid, None)
        rec["version"] += 1
        rec["updated"] = round(time.time(), 3)
        p = _path(wid)
        if p is None or not (p.parent / "work.json").exists():  # 저장 끔 · 지운 작업 → 메모리
            _MEMORY[wid] = rec
        else:
            works._write_json(p, rec)
            _MEMORY.pop(wid, None)
    works.log(wid, "tableHeads", table=tid, role=role, cells=len(cells), kept=len(cur), version=rec["version"])
    return cur


# ---- 칸 역할 · 헤더 열 · 필드 열 ---------------------------------------------------------------------------------

def apply(tb, user):
    """사용자 지정을 칸 역할 위에 덮는다(칸에 user · reason) → 덮은 칸 수. tb = heading_tables.collect 의 표(칸마다 role 이 있어야)."""
    n = 0
    for x in tb["cells"]:
        role = (user or {}).get(x["id"])
        if role in ROLES:
            x["role"], x["user"], x["reason"] = role, True, "사용자 지정"
            n += 1
    return n


def table(doc, tid, user=None, store=None, doc_key=None):
    """표 tid 의 칸 역할(스크립트 초안 + 사용자 지정) → heading_tables.collect 꼴 표(칸마다 role) | None(표가 아니거나 1칸 표·hwpx 가 아님).
    너무 큰 표는 ValueError."""
    if not hasattr(doc, "_sections"):
        return None
    stage1 = TX.records(doc, tid, store, doc_key)
    if stage1 is None:
        return None
    tb = next((t for t in HT.collect(stage1) if t["id"] == tid), None)
    if tb is None:
        return None
    if len(tb["cells"]) > TX.MAX_CELLS:
        raise ValueError(f"표가 너무 큽니다(칸 {len(tb['cells'])} > {TX.MAX_CELLS})")
    HT.draft(tb)
    apply(tb, user)
    return tb


def field_cols(tb):
    """열마다 필드 열인가 — 필드 칸이 걸친 격자 열. 전체 너비 한 칸(제목·안내·간격 줄이 필드로 읽혀도)은 안 센다."""
    nc = tb["cols"]
    flags = [False] * nc
    for x in tb["cells"]:
        if x.get("role") != "field" or (nc > 1 and x["col"] <= 0 and x["col"] + x["cs"] >= nc):
            continue
        for c in range(max(0, x["col"]), min(nc, x["col"] + x["cs"])):
            flags[c] = True
    return flags


def head_cols(flags):
    """왼쪽부터 이어진 헤더 열 수(첫 필드 열의 번호 — 필드 열이 없으면 열 수)."""
    return next((i for i, f in enumerate(flags) if f), len(flags))


def fields_of(doc, tid, user=None, doc_key=None):
    """열 폭 규칙(§5-1)에 넘길 필드 열 표시 — 판정하지 못하면 None(예전 규칙)."""
    try:
        tb = table(doc, tid, user, doc_key=doc_key)
    except ValueError:
        return None
    return field_cols(tb) if tb is not None else None


def layout(doc, tid, user=None, doc_key=None):
    """한 표의 판정 → {table, rows, cols, fieldCols[], headCols, units[[c0, c1]…], partner{prev, next — {table, units} | None}, roles{칸 id: 지정}, cells[{id, row, col, rs, cs, role, user?}]}.
    표 나누기는 units 가 2개 이상(또는 partner 가 있을 때)만. 1칸 표·hwpx 가 아니면 빈 판정."""
    out = {"table": tid, "rows": 1, "cols": 1, "fieldCols": [], "headCols": 0, "units": [], "partner": {"prev": None, "next": None}, "roles": dict(user or {}), "cells": []}
    tb = table(doc, tid, user, doc_key=doc_key)
    if tb is None:
        return out
    flags = field_cols(tb)
    hc = head_cols(flags)
    _tbl, cells, _nr, nc = doc._tgrid(doc._ids[tid])
    units = grid.col_units(cells, nc, hc) if 0 < hc < nc else []
    partner = {"prev": None, "next": None}
    if units and hasattr(doc, "split_partner"):
        for key, forward in (("next", True), ("prev", False)):
            pid = doc.split_partner(tid, hc, forward)
            if pid:
                _t2, c2, _n2, nc2 = doc._tgrid(doc._ids[pid])
                partner[key] = {"table": pid, "units": len(grid.col_units(c2, nc2, hc))}
    out.update(rows=tb["rows"], cols=tb["cols"], fieldCols=flags, headCols=hc, units=[list(u) for u in units], partner=partner,
               cells=[{"id": x["id"], "row": x["row"], "col": x["col"], "rs": x["rs"], "cs": x["cs"], "role": x["role"], **({"user": True} if x.get("user") else {})}
                      for x in tb["cells"]])
    return out
