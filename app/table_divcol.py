"""구분 기준 열 넣기 — 순수 계산(spec_테이블매니저 ② §13 「구분 기준 열 넣기」). 서버 · 세션을 import 하지 않는다.

사용자 2026-11-23 "테이블 기능 중에 열에 구분기준을 추가할 수 있는 옵션을 넣어줘, 그럼 해당 행이 어떤 기관, 어떤 차년, 어떤 단계 인지 추가로 넣는거지.
1단계 구분기준이 추가된 이후에 하면 선택해서 넣을 수 있겠지?" — 표에 기관 · 차년도 · 단계 열을 넣고, 값 줄마다 그 줄이 어느 값의 것인지 적는다.

- `tb` = `table_manager.judge()["table"]`(칸 `id` · `row` · `col` · `rs` · `cs` · `role` · `sub` · `text`/`textFull` · 표 `rows` · `cols`) — 쓰는 도구의 기본 역할(초안 + 유효한 사람 지정 · 확정본).
- 줄의 갈래(`classes`): `head`(머리 행 — 머리 칸(열머리 · 귀퉁이)만 덮고 필드 칸이 없는 행) · `data`(필드 칸이 덮는 행) · `other`(제목 · 안내 · 간격 · 행머리만).
- 넣을 자리(`positions`): 열 사이의 경계 b(0 = 맨 앞 … cols = 맨 끝) 가운데 머리 행에서 합친 칸이 가로지르지 않는 곳 + 본뜰 열(머리 행에서 그 열을 덮는 칸이 모두
  한 열 폭이고, 그 열에서 시작해 오른쪽으로 넘어가는 합친 칸이 없는 열 — `hwpx_doc.clone_cols` 가 받는 꼴)이 옆에 있는 곳. 왼쪽 열이 먼저(`col_right` — 본뜬 열의 칸 id 가 그대로) ·
  안 되면 오른쪽 열(`col_left` — 지금의 「열 넣기」 와 같이 본뜬 열의 글이 사본 쪽으로 옮겨 간다).
- 값 줄 항목(`items`): 본뜰 열에서 값 줄을 덮는 칸 하나하나(합친 칸이면 그 칸 하나가 한 항목) — 항목 id = 본뜰 열의 그 칸 id(넣은 뒤 새 열의 칸은 열 넣기의 `map` 으로 찾는다).
  합계 · 소계 줄(행 머리 글이 「합계」 · 「소계」 · 「총계」 · 「계」)은 뺀다.
- 권하는 값(`suggest`): 편집 구역이 그 줄의 칸에 준 귀속(`zone_of(칸 id)` → {org, year, stage} — `table_kinds_api._zone_of`)이 한 값일 때만.
"""
import hashlib
import json
import re

BASES = ("stage", "year", "org")   # 구분 순서(바깥 → 안) = 넣는 열의 차례(왼쪽 → 오른쪽)
HEAD_TEXT = {"stage": "단계", "year": "차년도", "org": "기관"}   # 새 열 머리 칸의 기본 글
HEAD_ROLES = ("colhead", "corner")
LABEL_MAX = 40      # 항목 이름(줄의 행 머리 글)
COLNAME_MAX = 16    # 자리 이름에 쓰는 열 머리 글
TEXT_MAX = 200      # 칸 하나에 적는 글
HEAD_MAX = 30       # 머리 칸 글
MM = 7200 / 25.4    # HWPUNIT / mm
WIDTH_MM = (15.0, 25.0)   # 새 열 폭의 하한 · 상한(값 글 길이로 어림 — ② §13 「열 폭」)
CHAR_MM, PAD_MM = 3.4, 4.0   # 글자 하나 · 칸 안 여백의 어림(10pt 한글)
WIDTH_SHARE = 0.3   # 새 열 하나가 표 폭에서 넘지 않는 몫
_TOTAL = re.compile(r"^(합|소|총)?계$")
_FOOT = re.compile(r"\s*\d+\)\s*$")   # 머리 글 끝의 각주 번호(「비중2)」)
_WS = re.compile(r"\s+")


def _text(c):
    t = c.get("textFull") if isinstance(c.get("textFull"), str) else c.get("text")
    return _WS.sub(" ", t or "").strip()


def _cut(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def _cover(tb):
    """행마다 그 행을 덮는 칸 목록."""
    by = [[] for _ in range(int(tb.get("rows") or 0))]
    for c in tb.get("cells") or ():
        for r in range(c["row"], min(len(by), c["row"] + c["rs"])):
            by[r].append(c)
    return by


def classes(tb):
    """행마다 "head" | "data" | "other"(모듈 머리 설명)."""
    out = []
    for cs in _cover(tb):
        roles = {c.get("role") for c in cs}
        out.append("data" if "field" in roles else "head" if roles & set(HEAD_ROLES) else "other")
    return out


def _head_rows(cls):
    return {r for r, k in enumerate(cls) if k == "head"}


def _covers(c, rows):
    return any(r in rows for r in range(c["row"], c["row"] + c["rs"]))


def source_ok(tb, col, heads):
    """col 을 본떠 새 열을 만들 수 있나 — 머리 행에서 그 열을 덮는 칸이 모두 그 열 하나 폭 · 그 열에서 시작해 오른쪽으로 넘어가는 칸이 없음."""
    for c in tb.get("cells") or ():
        if not c["col"] <= col < c["col"] + c["cs"]:
            continue
        if c["col"] == col and c["cs"] > 1:   # clone_cols 가 거절한다(합친 칸이 가로지름)
            return False
        if _covers(c, heads) and (c["col"] != col or c["cs"] != 1):   # 새 열이 제 머리 칸을 못 가진다(묶음 머리 안)
            return False
    return True


def crossed(tb, b, heads):
    """경계 b 를 머리 행의 합친 칸이 가로지르나."""
    return any(_covers(c, heads) and c["col"] < b < c["col"] + c["cs"] for c in tb.get("cells") or ())


def _short(t):
    """머리 글의 짧은 이름 — 괄호 앞(앞 글이 두 자 이상일 때) · 끝의 각주 번호(「비중2)」) 뗌."""
    i = t.find("(")
    t = t[:i] if i >= 2 else t
    return _FOOT.sub("", t).strip() or t.strip()


def col_name(tb, col, heads):
    """열 col 의 이름(그 열 바로 오른쪽 경계의 이름에 쓴다) — 그 열에서 **끝나는** 머리 칸 가운데 가장 위 것의 글(「개발 목표치」 묶음의 마지막 열이면 「개발 목표치」) ·
    없으면 그 열을 덮는 가장 아래 머리 칸 · 그것도 없으면 「A열」 꼴."""
    hs = [c for c in tb.get("cells") or () if c["col"] <= col < c["col"] + c["cs"] and _covers(c, heads) and _text(c)]
    ends = [c for c in hs if c["col"] + c["cs"] - 1 == col]
    if ends:
        return _cut(_short(_text(min(ends, key=lambda c: c["row"]))), COLNAME_MAX)
    if hs:
        return _cut(_short(_text(max(hs, key=lambda c: c["row"] + c["rs"]))), COLNAME_MAX)
    n, s = col + 1, ""
    while n:
        n, k = divmod(n - 1, 26)
        s = chr(65 + k) + s
    return f"{s}열"


def default_at(tb, cls):
    """기본 경계 — 값 줄을 덮는 행머리 칸의 가장 오른쪽 열 바로 오른쪽(행 머리가 없으면 첫 열 오른쪽)."""
    data = {r for r, k in enumerate(cls) if k == "data"}
    rh = [c["col"] + c["cs"] for c in tb.get("cells") or () if c.get("role") == "rowhead" and _covers(c, data)]
    return max(rh) if rh else min(1, int(tb.get("cols") or 0))


def positions(tb, cls=None):
    """넣을 자리 [{at, label, src: 본뜰 열, op: col_right | col_left, cell: 본뜰 열의 칸 id(맨 위), default: bool}] — 경계 차례."""
    cls = classes(tb) if cls is None else cls
    heads, cols = _head_rows(cls), int(tb.get("cols") or 0)
    out = []
    for b in range(cols + 1):
        if 0 < b < cols and crossed(tb, b, heads):
            continue
        if b > 0 and source_ok(tb, b - 1, heads):
            src, op = b - 1, "col_right"
        elif b < cols and source_ok(tb, b, heads):
            src, op = b, "col_left"
        else:
            continue
        own = sorted((c for c in tb.get("cells") or () if c["col"] == src and c["cs"] == 1), key=lambda c: c["row"])
        if not own:
            continue
        label = "맨 앞" if b == 0 else "맨 끝" if b == cols else f"「{col_name(tb, b - 1, heads)}」 다음"
        out.append({"at": b, "label": label, "src": src, "op": op, "cell": own[0]["id"], "default": False})
    if out:
        want = default_at(tb, cls)
        pick = min(out, key=lambda p: (abs(p["at"] - want), p["at"]))   # 기본 자리가 안 되면 가장 가까운 자리(같으면 왼쪽)
        pick["default"] = True
    return out


def _row_label(tb, r):
    """줄 r 의 이름 — 그 줄을 덮는 행머리 칸의 글(왼쪽부터 « › » 로) · 없으면 그 줄에서 시작하는 첫 글 있는 칸."""
    cover = sorted((c for c in tb.get("cells") or () if c["row"] <= r < c["row"] + c["rs"]), key=lambda c: c["col"])
    heads = [_text(c) for c in cover if c.get("role") == "rowhead" and _text(c)]
    if heads:
        return " › ".join(heads)
    return next((_text(c) for c in cover if c["row"] == r and _text(c)), "")


def is_total(label):
    last = (label or "").split(" › ")[-1]
    return bool(_TOTAL.match(_WS.sub("", last)))


def items(tb, src, cls=None):
    """값을 적을 항목 [{id, label, rows: [r0, r1], sub, cells: [그 줄의 칸 id…]}] — 본뜰 열 src 에서 값 줄을 덮는 칸마다(합계 줄 뺌)."""
    cls = classes(tb) if cls is None else cls
    out = []
    for c in sorted((c for c in tb.get("cells") or () if c["col"] == src and c["cs"] == 1), key=lambda c: c["row"]):
        rows = range(c["row"], c["row"] + c["rs"])
        if not any(r < len(cls) and cls[r] == "data" for r in rows):
            continue
        label = _row_label(tb, c["row"])
        if is_total(label):
            continue
        r0, r1 = c["row"], c["row"] + c["rs"] - 1
        ids = [x["id"] for x in tb.get("cells") or () if x["row"] <= r1 and x["row"] + x["rs"] - 1 >= r0]
        out.append({"id": c["id"], "label": _cut(label, LABEL_MAX) or f"{r0 + 1}행", "rows": [r0, r1], "sub": c.get("sub"), "cells": ids})
    return out


def heads_of(tb, src, cls=None):
    """새 열에서 머리 글을 적을 칸 — 본뜰 열의 머리 행 칸 가운데, 이어진 머리 행 묶음마다 맨 위 칸의 id."""
    cls = classes(tb) if cls is None else cls
    out, last = [], None
    for c in sorted((c for c in tb.get("cells") or () if c["col"] == src and c["cs"] == 1), key=lambda c: c["row"]):
        is_head = all(r < len(cls) and cls[r] == "head" for r in range(c["row"], c["row"] + c["rs"]))
        if is_head and last is None:
            out.append(c["id"])
        last = c["id"] if is_head else None
    return out


def suggest(item, zone_of, choices):
    """권하는 값 → ({기준: [값 key]}, {기준: "zone"}) — 편집 구역이 그 줄의 칸에 준 귀속이 한 값이고 고를 값에 있을 때만(짐작하지 않는다)."""
    got, by = {}, {}
    if zone_of is None:
        return got, by
    zs = [zone_of(i) or {} for i in item["cells"]]
    for b in BASES:
        vals = {z.get(b) for z in zs if z.get(b) is not None}
        keys = {v["key"] for v in (choices or {}).get(b) or ()}
        if len(vals) == 1 and (v := next(iter(vals))) in keys:
            got[b], by[b] = [v], "zone"
    return got, by


def plan_id(rev, tid, tb, cls=None):
    """계획의 도장 — 문서 차례 · 표 id · 격자(칸 자리 · 병합) · 줄의 갈래. 넣기는 이것이 같을 때만."""
    cls = classes(tb) if cls is None else cls
    grid = sorted((c["id"], c["row"], c["col"], c["rs"], c["cs"]) for c in tb.get("cells") or ())
    raw = json.dumps([rev, tid, grid, cls], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def plan(tb, rev, tid, zone_of=None, choices=None):
    """→ {positions, items, heads: {열 번호: [칸 id…]}, planId} — items 마다 suggest · by. 본뜰 열은 자리마다 달라 items 는 자리마다다(`byAt`)."""
    cls = classes(tb)
    pos = positions(tb, cls)
    by_src = {}
    for p in pos:
        if p["src"] not in by_src:
            its = items(tb, p["src"], cls)
            for it in its:
                it["suggest"], it["by"] = suggest(it, zone_of, choices)
            by_src[p["src"]] = {"items": its, "heads": heads_of(tb, p["src"], cls)}
    return {"positions": pos, "bySrc": by_src, "classes": cls, "planId": plan_id(rev, tid, tb, cls)}


def width_of(texts, total):
    """새 열의 폭(HWPUNIT) — 넣을 글 가운데 가장 긴 것의 글자 수로 어림(15~25mm) · 표 폭의 30% 를 넘지 않음."""
    n = max((len(t) for t in texts if t), default=2)
    mm = min(WIDTH_MM[1], max(WIDTH_MM[0], n * CHAR_MM + PAD_MM))
    return int(min(mm * MM, total * WIDTH_SHARE)) if total else int(mm * MM)
