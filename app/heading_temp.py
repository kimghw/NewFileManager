"""TEMP 라벨(spec_헤딩_추출 ② §15) — 표 안의 **임시 글**(작성요령 · 쓸 자리)에 TEMP 라벨을 단다. 문서를 바꾸지 않는다(읽기만).

TEMP = 양식이 글쓴이에게 주는 안내이거나 아직 안 쓴 자리라서, 다 쓴 문서에는 남지 않을 글. 헤딩·템플릿을 주지 않고(2단계 후보에서 뺌) 표 구조도 만들지 않으며
(3단계 — TEMP 표), 나중에 문서에서 지울 수 있다(지우는 일은 heading_temp_api — 구조 편집 트랜잭션).

- 입력 = 1단계 결과(문단 레코드의 그릇 사슬) + 사용자 지정(작업 폴더 `headings/hints.json` 의 `temp`). 2·3단계가 시작할 때 `label()` 로 다시 셈한다 —
  1단계를 다시 뽑지 않아도 지정이 바로 듣는다.
- 항목(item) = TEMP 라벨이 붙는 단위 하나: 표(`tbl:<표 id>` — 그 안 문단·안쪽 표 전부) · 칸(`cell:<칸 id>` — 칸 안 표도) · 문단(`para:<문단 id>`). 큰 단위가 덮은 것은 따로 항목이 안 된다.
  TEMP 표 = 표 항목의 표 + 그 안쪽 표·상자 + 칸 항목 안의 표·상자(`tables` — 3단계가 건너뛰는 문단은 `tableParas`).
- 까닭(why): `guide` 작성요령(안내) · `todo` 쓸 자리(향후 작성). 차례는 큰 단위부터 — 표(사용자 지정 → 1 → 2) → 칸(사용자 지정 → 3) → 문단(사용자 지정 → 4 → 5); 앞에서 덮인 문단은 뒤 규칙이 다시 보지 않는다.
  1. `guide_table` — 표의 처음 두 행(또는 첫 글 문단)에 「작성 요령」 제목 칸이 있는 표(「작성 요령」·「작성요령(계속)」·「앞표지 작성 요령(…)」) → 표 전체.
  2. `guide_box` — 1칸 표(상자)의 첫 글 문단이 「※」 안내이거나 안내 낱말(작성 요령·방법·예시, 유의 사항, ☞)로 시작 → 상자 전체.
  3. `guide_cell` — 여러 칸 표의 칸에서 첫 글 문단이 「※」 안내이고 글 문단이 둘 이상(안내 + 그 아래 줄들) → 그 칸.
  4. `guide_line` — 표 칸 안 문단의 글이 지시문으로 끝남(「… 작성합니다」「… 기재 요망」「… 작성할 것」) → 그 문단.
  5. `blank` — 표 칸(여러 칸 표) 안의 빈 글머리 줄(레터만 있고 글 없음 = 쓸 자리) → 그 문단. 그 칸의 글 문단이 둘 이상이고 모두 레터·괄호 줄일 때만
     (칸에 그 줄 하나뿐인 「1.」「(A)」「-」 = 순번·코드·대시 값, 보통 글과 섞인 헤더 칸의 「(A)」 는 쓸 자리가 아님 — 사용자 2026-11-10 「칸 안 빈 글머리 줄」 만).
  · `user` — 사용자가 지정한 표·칸·문단(웹 블록이 있는 것 — 본문 문단도), 단위마다 자동 규칙보다 앞. 사용자가 해제한 항목(`off` — 항목 단위)은 TEMP 가 아니고,
    해제한 표·칸 안에는 자동 규칙도 안 듣는다.
  2 는 본문에 놓인 1칸 상자도 잡는다(상자 안 문단은 본문 흐름). 4·5 의 「표 칸 안」 = 여러 칸 표의 칸(1칸 상자는 투명), 3·5 의 「그 칸의 글 문단」 = 문단이 바로 든 칸의 것."""
import re
from collections import Counter

from app import heading_rules as R
from app.heading_tables import _NOTE_WORDS

VERSION = 1
WHYS = ("guide", "todo")
WHY_NAME = {"guide": "작성요령", "todo": "쓸 자리"}
RULE_NAME = {"guide_table": "작성 요령 표", "guide_box": "안내 상자", "guide_cell": "안내 칸", "guide_line": "지시문", "blank": "빈 글머리 줄", "user": "사용자 지정"}
UNIT_PREFIX = {"table": "tbl", "cell": "cell", "para": "para"}
PREFIX_UNIT = {v: k for k, v in UNIT_PREFIX.items()}
TEXT_MAX = 80
TITLE_MAX = 60
# 「작성 요령」 제목 줄 — 앞에 짧은 꾸밈 낱말 하나(「앞표지」), 뒤에 괄호 덧글(「(계속)」「(작성 요령은 삭제 후 제출합니다.)」)까지. 문장 속 「작성 요령」 은 아님
_GUIDE_TITLE = re.compile(r"^[\s<〈《\[【(※☞*·]*(?:[가-힣A-Za-z0-9]{1,8}\s+)?작성\s*(?:요령|방법|가이드\s*라인|가이드|안내|지침)\s*(?:\(.{0,40}\))?[\s>〉》\]】):]*$")
# 지시문 끝 — 양식의 안내 말투(「합니다」체·「요망」·「할 것」). 개조식 내용 글(「… 작성함」「… 제출 완료」)은 아님
_INSTRUCT = re.compile(r"(?:작성|기재|기입|표시|서술|기술|명시|입력)\s*(?:합니다|하십시오|하세요|바랍니다|바람|요망|할\s*것|하여\s*주십시오|해\s*주십시오)\s*[.)]?\s*$")
# 「제출합니다」「첨부합니다」 는 뺀다 — 신청서의 다짐 글(「… 증빙서류를 제출합니다.」)이 같은 꼴


def _tid(item):
    return item.get("id") or f"k{item.get('key')}"


def item_id(unit, raw):
    return f"{UNIT_PREFIX[unit]}:{raw}"


def split_id(iid):
    """항목 id → (단위, 블록 id) | (None, None)."""
    if not isinstance(iid, str) or ":" not in iid:
        return None, None
    pre, raw = iid.split(":", 1)
    return (PREFIX_UNIT.get(pre), raw) if raw and pre in PREFIX_UNIT else (None, None)


def _first_line(rec):
    return (rec.get("text") or "").split(R.BR, 1)[0].strip()


def _has_text(rec):
    return rec.get("kind") not in ("empty", "object") and bool((rec.get("text") or "").strip())


def _excerpt(rec):
    t = (rec.get("text") or "").replace(R.BR, " ").replace("\t", " ").strip()
    return t[:TEXT_MAX] + ("…" if len(t) > TEXT_MAX else "")


def clean_hints(h):
    """사용자 지정(hints["temp"]) 을 고른 꼴로 → {"version": int, "set": {항목 id: {"state": "on"|"off", "why", "at", "text"}}}. 모르는 꼴은 버린다."""
    h = h if isinstance(h, dict) else {}
    out = {}
    for iid, v in (h.get("set") or {}).items() if isinstance(h.get("set"), dict) else ():
        unit, raw = split_id(iid)
        if unit is None or not isinstance(v, dict) or v.get("state") not in ("on", "off"):
            continue
        out[iid] = {"state": v["state"], "why": v.get("why") if v.get("why") in WHYS else "guide", "at": v.get("at"), "text": str(v.get("text") or "")[:TEXT_MAX]}
    return {"version": int(h.get("version") or 0) if isinstance(h.get("version"), (int, float)) else 0, "set": out}


def block_text(stage1, unit, raw):
    """그 표·칸·문단의 첫 글(지정에 적어 둘 미리보기) | None(1단계 결과에 그 블록이 없음). 글이 없는 블록은 "".
    **웹 블록이 있는** 표·칸·문단만 찾는다 — 웹 블록이 없는 자리(머리말·글상자 안)의 id(`k<번호>`·`x<구역>.<순번>`)는 자리 번호라 편집 뒤 다른 블록을 가리킬 수 있어 지정 대상이 아니다."""
    want = {"table": "tbl", "cell": "cell"}.get(unit)
    found = False
    for rec in (stage1 or {}).get("paras") or ():
        if (rec["id"] == raw and rec.get("block")) if unit == "para" else any(c["t"] == want and c.get("id") == raw for c in rec.get("path") or ()):
            found = True
            if _has_text(rec):
                return _excerpt(rec)
    return "" if found else None


def _index(paras):
    """문단 레코드 → (표 색인, 칸 색인). 표 {id, block, cells, rows, cols, host, n, outer[바깥 표 id…], direct[이 표가 가장 안쪽 표인 문단], all[표 안 모든 문단]},
    칸 {id, table, row, col, block, n, direct[그 칸에 바로 든 문단], all[칸 안 모든 문단 — 안쪽 표 포함]}."""
    tables, cells = {}, {}
    for rec in paras:
        path = rec.get("path") or []
        tbls = [i for i, c in enumerate(path) if c["t"] == "tbl"]
        for j, i in enumerate(tbls):
            c = path[i]
            tid = _tid(c)
            tb = tables.get(tid)
            if tb is None:
                tb = tables[tid] = {"id": tid, "block": bool(c.get("id")), "cells": c.get("cells"), "rows": c.get("rows"), "cols": c.get("cols"),
                                    "host": c.get("host"), "n": rec["n"], "outer": [_tid(path[k]) for k in tbls[:j]],
                                    "outerCells": [_tid(path[k + 1]) for k in tbls[:j] if k + 1 < len(path) and path[k + 1]["t"] == "cell"],
                                    "direct": [], "all": []}
            tb["all"].append(rec)
            cc = path[i + 1] if i + 1 < len(path) and path[i + 1]["t"] == "cell" else None
            if cc is None:
                continue
            cid = _tid(cc)
            cell = cells.get(cid)
            if cell is None:
                cell = cells[cid] = {"id": cid, "table": tid, "row": cc.get("row"), "col": cc.get("col"), "block": bool(cc.get("id")), "n": rec["n"],
                                     "direct": [], "all": []}
            cell["all"].append(rec)
            if i == tbls[-1]:
                tb["direct"].append(rec)
                cell["direct"].append(rec)
    return tables, cells


def _guide_table(tb, cells):
    """표의 처음 두 행(또는 첫 글 문단)에 「작성 요령」 제목 줄이 있는가 → 그 문단 | None."""
    first = True
    for rec in tb["direct"]:
        if not _has_text(rec):
            continue
        cell = cells.get(rec.get("cell")) or {}
        if (first or (cell.get("row") or 0) <= 1) and len(_first_line(rec)) <= TITLE_MAX and _GUIDE_TITLE.match(_first_line(rec)):
            return rec
        first = False
        if (cell.get("row") or 0) > 1:
            break
    return None


def _guide_start(rec):
    """안내로 시작하는 문단인가 — 「※」 안내(kind note) 또는 안내 낱말로 시작하는 짧은 줄."""
    if rec.get("kind") == "note":
        return True
    line = _first_line(rec)
    m = _NOTE_WORDS.search(line)
    return bool(m) and m.start() <= 12 and len(line) <= TITLE_MAX


def _cell_flow(rec):
    """여러 칸 표의 칸 안 문단인가(1칸 상자는 투명 — 그 바깥 그릇을 본다; 2단계 흐름 `cell:` 과 같은 기준)."""
    path = rec.get("path") or []
    for i in range(len(path) - 1, -1, -1):
        c = path[i]
        if c["t"] == "cell":
            if i and path[i - 1]["t"] == "tbl" and path[i - 1].get("cells") == 1:
                continue
            return True
        if c["t"] in ("shape", "caption", "header", "footer", "footnote", "endnote", "master"):
            return False
    return False


def _texts(cell):
    return sum(1 for r in cell["direct"] if _has_text(r))


def _write_spot(rec, cells):
    """빈 글머리 줄이 쓸 자리인가 — 그 칸의 글 문단이 둘 이상이고 모두 레터·괄호 줄일 때만(「[1차년도 목표]」 아래 「ㅇ」 · 「o」 두 줄).
    칸에 그 줄 하나뿐이거나(「1.」「(A)」「-」 = 순번·코드·대시 값) 보통 글과 섞인 칸(헤더 「급여총액 / (A)」 · 「- / (특허전략보고서)」 · 「[1] / 전력변환시스템」)의 빈 레터는
    다 쓴 문서에도 남는 값이라 쓸 자리가 아니다."""
    cell = cells.get(rec.get("cell"))
    if cell is None:
        return False
    texts = [r for r in cell["direct"] if _has_text(r)]
    return len(texts) >= 2 and all(r.get("kind") in ("marker", "label") for r in texts)


def label(stage1, hints=None):
    """1단계 결과 + 사용자 지정 → TEMP 라벨 {"version", "items": [항목…](문서 순), "paras": {문단 id: 항목 id}, "tables": {표 id: 항목 id}(TEMP 표 — 표 단위 항목 ·
    그 안쪽 표 · 칸 단위 항목 안의 표), "tableParas": [TEMP 표 안의 문단 id…], "off": [해제한 항목 id…], "gone": [문서에 없는 지정 id…], "counts", "hintsVersion"}.
    항목 = {id, unit: table|cell|para, why: guide|todo, rule, by: script|user, table, cell, para(자리로 갈 문단), block(문서에서 지울 수 있는 블록인가), n, paras(덮은 문단 수),
    candidates(그 안 헤딩 후보 = 레터·괄호 줄 문단 수), text, rows?, cols?}."""
    paras = stage1.get("paras") or []
    hs = clean_hints(hints)
    tables, cells = _index(paras)
    by_id = {r["id"]: r for r in paras}
    on = {i: v for i, v in hs["set"].items() if v["state"] == "on"}
    off = {i for i, v in hs["set"].items() if v["state"] == "off"}
    items, covered, temp_tables = [], {}, {}
    off_tables = {split_id(i)[1] for i in off if split_id(i)[0] == "table"}
    off_cells = {split_id(i)[1] for i in off if split_id(i)[0] == "cell"}
    gone = []

    def exempt(rec):  # 사용자가 해제한 표·칸 안 — 자동 규칙이 안 듣는다
        return any((c["t"] == "tbl" and _tid(c) in off_tables) or (c["t"] == "cell" and _tid(c) in off_cells) for c in rec.get("path") or ())

    def inside_off(tb):  # 표가 해제한 표·칸 안에 있나(그 표 자신의 해제는 따로 본다)
        return any(o in off_tables for o in tb.get("outer") or ()) or any(c in off_cells for c in tb.get("outerCells") or ())

    def add(unit, raw, why, rule, recs, rep, by="script", **more):
        iid = item_id(unit, raw)
        mine = [r for r in recs if r["id"] not in covered]
        if not mine and by == "script":
            return None
        for r in mine:
            covered[r["id"]] = iid
        rep = rep or next((r for r in recs if _has_text(r)), recs[0] if recs else None)
        items.append({"id": iid, "unit": unit, "why": why, "rule": rule, "by": by, "table": more.pop("table", None), "cell": more.pop("cell", None),
                      "para": next((r["id"] for r in ([rep] if rep else []) + list(recs) if r and r.get("block")), None),
                      "n": min((r["n"] for r in recs), default=0), "paras": len(mine),
                      "candidates": sum(1 for r in mine if r.get("kind") in ("marker", "label")), "text": _excerpt(rep) if rep else "", **more})
        return iid

    def add_table(tb, why, rule, rep, by="script"):
        iid = add("table", tb["id"], why, rule, tb["all"], rep, by, table=tb["id"], block=tb["block"], rows=tb["rows"], cols=tb["cols"], box=tb["cells"] == 1,
                  host=tb["host"])
        if iid:
            temp_tables[tb["id"]] = iid
            for t2 in tables.values():  # 안쪽 표도 TEMP 표
                if tb["id"] in t2["outer"]:
                    temp_tables.setdefault(t2["id"], iid)
        return iid

    def add_cell(cell, why, rule, rep, by="script"):
        iid = add("cell", cell["id"], why, rule, cell["all"], rep, by, table=cell["table"], cell=cell["id"], block=cell["block"])
        if iid:
            for t2 in tables.values():  # 그 칸 안의 표도 TEMP 표(「칸 안 전부」 — 3단계 표 구조에서도 빠진다)
                if cell["id"] in t2["outerCells"]:
                    temp_tables.setdefault(t2["id"], iid)
        return iid

    # ---- 표 단위: 사용자 지정 → 작성 요령 표 → 안내 상자 (바깥 표 먼저 — 덮인 안쪽 표는 건너뜀)
    for tb in sorted(tables.values(), key=lambda t: (t["n"], len(t["outer"]))):
        iid = item_id("table", tb["id"])
        if tb["id"] in temp_tables or iid in off:
            continue
        if iid in on:
            add_table(tb, on[iid]["why"], "user", None, "user")
            continue
        if inside_off(tb):
            continue
        rep = _guide_table(tb, cells)
        if rep is not None:
            add_table(tb, "guide", "guide_table", rep)
            continue
        if tb["cells"] == 1:
            first = next((r for r in tb["direct"] if _has_text(r)), None)
            if first is not None and _guide_start(first):
                add_table(tb, "guide", "guide_box", first)
    # ---- 칸 단위: 사용자 지정 → 안내 칸
    for cell in sorted(cells.values(), key=lambda c: c["n"]):
        iid = item_id("cell", cell["id"])
        if iid in off or all(r["id"] in covered for r in cell["all"]):
            continue
        tb = tables.get(cell["table"]) or {}
        if iid in on:
            add_cell(cell, on[iid]["why"], "user", None, "user")
            continue
        if tb.get("cells") == 1 or cell["table"] in off_tables or inside_off(tb):
            continue
        first = next((r for r in cell["direct"] if _has_text(r)), None)
        if first is not None and first.get("kind") == "note" and first["id"] not in covered and _texts(cell) >= 2:
            add_cell(cell, "guide", "guide_cell", first)
    # ---- 문단 단위: 사용자 지정 → 지시문 → 빈 글머리 줄
    for iid, v in on.items():
        unit, raw = split_id(iid)
        if unit == "para" and raw in by_id and raw not in covered:
            rec = by_id[raw]
            add("para", raw, v["why"], "user", [rec], rec, "user", table=rec.get("table"), cell=rec.get("cell"), block=bool(rec.get("block")))
    for rec in paras:
        if rec["id"] in covered or item_id("para", rec["id"]) in off or not _has_text(rec) or not _cell_flow(rec) or exempt(rec):
            continue
        more = {"table": rec.get("table"), "cell": rec.get("cell"), "block": bool(rec.get("block"))}
        if rec.get("kind") in ("marker", "label", "plain", "note", "footnote") and _INSTRUCT.search(rec["text"].replace(R.BR, " ")):
            add("para", rec["id"], "guide", "guide_line", [rec], rec, **more)
        elif rec.get("kind") == "marker" and rec.get("blank") and _write_spot(rec, cells):
            add("para", rec["id"], "todo", "blank", [rec], rec, **more)
    for iid in hs["set"]:  # 문서에 없는 지정(그 블록이 지워짐) — 버리지는 않고 알린다
        unit, raw = split_id(iid)
        if not (raw in tables if unit == "table" else raw in cells if unit == "cell" else raw in by_id):
            gone.append(iid)
    items.sort(key=lambda it: (it["n"], it["unit"] != "table"))
    by_why = {}
    for it in items:
        c = by_why.setdefault(it["why"], Counter())
        c["items"] += 1
        c["paras"] += it["paras"]
        c["candidates"] += it["candidates"]
        c[it["unit"]] += 1
    units = Counter(it["unit"] for it in items)
    return {"version": VERSION, "items": items, "paras": covered, "tables": temp_tables, "off": sorted(i for i in off if i not in gone), "gone": gone,
            "tableParas": sorted({r["id"] for tid in temp_tables for r in tables[tid]["all"]}),  # TEMP 표 안의 문단 — 3단계가 건너뛴다
            "hintsVersion": hs["version"],
            "counts": {"items": len(items), "tables": units.get("table", 0), "cells": units.get("cell", 0), "lines": units.get("para", 0),
                       "paras": len(covered), "candidates": sum(it["candidates"] for it in items), "user": sum(1 for it in items if it["by"] == "user"),
                       "off": len(off), "byWhy": {k: dict(v) for k, v in by_why.items()},
                       "byRule": dict(Counter(it["rule"] for it in items))}}


def summary_text(t):
    """실행 단계 줄 — 「TEMP 52항목 — 작성 요령 표 30 · 안내 상자 1 · 지시문 6 · 빈 글머리 줄 15 · 문단 730(헤딩 후보 394)」."""
    c = (t or {}).get("counts") or {}
    if not c.get("items"):
        return "TEMP 없음" + (f" · 해제 {c['off']}" if c.get("off") else "")
    rule = c.get("byRule") or {}
    parts = [f"{RULE_NAME[k]} {rule[k]:,}" for k in ("guide_table", "guide_box", "guide_cell", "guide_line", "blank", "user") if rule.get(k)]
    return f"TEMP {c['items']:,}항목 — " + " · ".join(parts) + f" · 문단 {c['paras']:,}(헤딩 후보 {c['candidates']:,})" + (f" · 해제 {c['off']}" if c.get("off") else "")


def same_items(brief, t):
    """결과가 쓴 TEMP 요약(2·3단계 결과의 `temp` — None = TEMP 없이 만든 결과)이 지금 TEMP 라벨 t 와 같은 항목인가."""
    return set((brief or {}).get("items") or ()) == {it["id"] for it in (t or {}).get("items") or ()}


def same_tables(result, t):
    """3단계 결과가 뺀 TEMP 표가 지금 TEMP 표와 같은가."""
    return {x["id"] for x in (result or {}).get("tempTables") or ()} == set((t or {}).get("tables") or ())
