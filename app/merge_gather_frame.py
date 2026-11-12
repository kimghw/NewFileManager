"""취합 — 배포 기준본의 자리 정보(spec_취합 ② §3) + 기준본·기관 문서·취합본을 **같은 꼴로 읽는 줄**(`rows`)과 견줄 꼴(`norm`·`block_key`). 문서를 안 고치고 LLM 도 안 부른다.

- `make(side)` = 1단계가 끝난 취합본 한 쪽(merge_api._read 의 꼴 {rev, values, blocks, graph, tables, doc?}) → `{rev, values, orgs[{key, name, role}], blocks[…]}`.
  blocks = 본문 최상위 블록 차례 전체(캡션 블록은 표·그림에 딸려 가므로 뺌): `{i, id, kind: p|tbl|pic, key, text, cls, path[소속 제목 사슬], scope{kind, org, year, stage, labels[]},
  table?: {rows, cols, list, guide, cells[{r, c, rs, cs, id, cls, text, scope?}]}}`. API 층이 여기에 frameId·at·sha256·runs 를 더해 저장한다.
  - `cls`: `label`(구분 라벨 — 구분 기준 묶음의 라벨 줄 · 2단계 role label) · `guide`(빈 줄 · 글머리만 있는 자리표시 줄 · 「※」 안내 줄 · 쌍점으로 끝나는 쓸 자리 줄 「o 세부계획1 :」) ·
    `title`(2단계 heading·subtitle·title) · `fixed`(그 밖의 양식 글) · 표 `table` · 그림 `pic`. 표 칸: `calc`(3단계 수식이 걸린 칸) · `complex`(칸 안에 표·그림) ·
    `head`(3단계 머리·제목·안내 칸, 구분 기준 라벨 칸, 3단계가 안 본 표(작성요령 표·1칸 상자)의 칸 — **글이 있을 때만**: 빈 머리 칸은 쓸 칸이다) · `input`(그 밖).
  - `scope`: 구분 기준 묶음 항목(`core.find` — 읽기만, prior 없음)에 든 블록·칸은 가장 안쪽 항목의 값(`merge_pairs._ident` — 기관 = 이름 열쇠, 차년도 = 전체 차례)으로.
    기관 항목인데 어느 기관인지 모르면(자리표시 열 「○○○」 · 외 기관·국외기관 절) `unknown`. 항목 밖 블록은 2단계 그래프의 윗 제목 가운데 **기관 낱말이 든 구분 라벨**이
    있으면 그 이름의 기관(이름을 못 읽으면 `unknown`), 없으면 `common`. `labels` = 그 자리를 품은 항목의 라벨 id(기관·차년도 — 자리 연결이 「라벨이 맞았는지」 본다).
  - `table.list`(이어 넣는 표) = 기관-연도 행 표(엔진 `orgYear`) 또는 3단계가 열 머리만 있는 표(matrix · 머리 열 0 · 수식 없음)로 본 표. `table.guide` = 작성요령 표(TEMP guide).
- `norm(text)` = 견줄 글: 한글이 저장하며 바꾸는 것(잇단 빈칸 · 줄 끝 빈칸 · 줄 나눔 · 빈칸 종류)을 흡수 — 빈칸 무리는 하나로, 그 빈칸도 양옆이 한글·기호면 지운다.
  **수 옆 빈칸과 영문·숫자 낱말 사이 빈칸은 남긴다**(「100 만원」 ≠ 「100만원」). `block_key(b, …)` = 문단은 「※ …」 꼬리(작성요령)를 뗀 글의 norm(빈 줄 = ""),
  표는 **머리 칸 글의 서명**(기준본의 머리 칸 글이 차례대로 다 있는 표면 그 기준본 표의 열쇠 — 칸을 채우거나 행을 늘려도 같다. 기관 문서의 3단계 분석에 기대지 않는다),
  그림은 파일 바이트의 해시.
- `rows(blocks, frame=None, doc=None)` = 본문 최상위 블록 → 견줄 줄 `[{i, id, kind, key, text, table?}]`(기준본·기관 문서·취합본 모두 이 함수 — 열쇠가 같은 꼴)."""
import hashlib
import json
import re

from app import merge_pairs as P
from app.division_profiles import rnd
from app.division_profiles.rnd import core

TEXT_MAX = 200
PATH_MAX, TITLE_MAX = 8, 60
HEAD_ROLES = ("colhead", "rowhead", "corner", "title", "note", "spacer")
TITLE_ROLES = ("heading", "subtitle", "title")
ANCHOR = ("title", "label", "table")   # 닻이 될 수 있는 자리(spec ② §4-1)
SKIP_SUB = ("title", "note", "spacer")
UNKNOWN = "?"

_WS = re.compile(r"\s+")
_ZW = re.compile("[​‌‍⁠﻿­]")
_NOTE = re.compile(r"\s*※.*$", re.S)
_BULLET = r"[oOㅇ○●◦•□■▪▫◇◆△▲▶\-–—·‧∙⋅*]"
PLACE = re.compile(rf"^\s*{_BULLET}?\s*$")   # 빈 줄 · 글머리만 있는 자리표시 줄(core.PLACEHOLDER 보다 넓다 — 「⋅」·「□」 만 있는 줄도)
SLOT = re.compile(r"[:：]\s*$")              # 쌍점으로 끝나는 쓸 자리 줄 「o 세부계획1 :」
SLOT_MAX = 60


def _sha(x):
    return hashlib.sha1(json.dumps(x, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]


def _keep(a, b):
    """빈칸을 남길 자리 — 수 옆, 영문·숫자 낱말 사이."""
    return a.isdigit() or b.isdigit() or (a.isascii() and a.isalnum() and b.isascii() and b.isalnum())


def norm(text):
    """견줄 글(모듈 설명) — 빈칸·줄 나눔만 다른 글은 같고, 수·단위 사이 빈칸은 뜻이 있어 지우지 않는다."""
    s = _WS.sub(" ", _ZW.sub("", str(text or ""))).strip()
    if " " not in s:
        return s
    parts = s.split(" ")
    out = [parts[0]]
    for p in parts[1:]:
        out.append((" " if _keep(out[-1][-1], p[0]) else "") + p)
    return "".join(out)


def para_key(text):
    """문단의 견줄 꼴 — 「※ …」 꼬리(작성요령 — 기관이 지우고 낸다)를 뗀 글. ※ 로 시작하는 줄은 글 그대로. 빈 줄 = ""."""
    t = str(text or "")
    cut = _NOTE.sub("", t)
    return norm(cut if cut.strip() else t)


def placeholder(text):
    """채우면 지울 자리표시 줄인가 — 글머리만 있는 줄 · 쌍점으로 끝나는 짧은 쓸 자리 줄(빈 줄은 아님 — 빈 줄은 줄 맞춤에 안 든다)."""
    t = str(text or "")
    if not t.strip():
        return False
    if PLACE.match(t):
        return True
    cut = _NOTE.sub("", t).strip()
    return bool(cut) and len(cut) <= SLOT_MAX and bool(SLOT.search(cut))


def _short(text, n=TEXT_MAX):
    t = _WS.sub(" ", str(text or "")).strip()
    return t if len(t) <= n else t[:n] + "…"


# ---- 표 — 격자·열쇠 ---------------------------------------------------------------------------------------------

def _deep(c):
    """칸 안의 글 전부(칸 안 표·그 칸의 글까지, 문서 순) — 칸 안에 표·그림이 든 칸은 칸 글(cell text)에 안 든 글이 있다."""
    return "\n".join(x.get("text") or "" for b in c.get("blocks") or () for x in core._under(b) if x.get("type") == "paragraph")


def _complex(c):
    return any(x.get("type") in ("table", "image") for x in c.get("blocks") or ())


def grid(b):
    """표 블록 → {rows, cols, cells[{r, c, rs, cs, id, text, cx}]}(행·열 차례) — cx = 칸 안에 표·그림(글 = 칸 안 글 전부)."""
    cells = []
    for c in b.get("cells") or ():
        cx = _complex(c)
        cells.append({"r": c["row"], "c": c["col"], "rs": c.get("rowSpan") or 1, "cs": c.get("colSpan") or 1, "id": c["id"],
                      "text": _deep(c) if cx else c.get("text") or "", "cx": cx})
    cells.sort(key=lambda c: (c["r"], c["c"]))
    rows = max([b.get("nRows") or 0, *(c["r"] + c["rs"] for c in cells)])
    cols = max([b.get("nCols") or 0, *(c["c"] + c["cs"] for c in cells)])
    return {"rows": rows, "cols": cols, "cells": cells}


def table_full(g):
    """표의 칸 글·격자 전체 지문 — 같으면 달라진 칸이 없다."""
    return _sha([[c["r"], c["c"], c["rs"], c["cs"], norm(c["text"])] for c in g["cells"]])


def _heads(g):
    """기준본 표의 머리 칸 [(r, c, cs, 견줄 글)] — 행·열 차례."""
    return [(c["r"], c["c"], c["cs"], norm(c["text"])) for c in g["cells"] if c.get("cls") == "head" and norm(c["text"])]


def _head_key(cols, heads):
    return f"T{cols}:h:{_sha([[c, cs, k] for _, c, cs, k in heads])}"


def _all_key(g):
    return f"T{g['cols']}:a:{_sha([norm(c['text']) for c in g['cells']])}"


def table_index(frame):
    """기준본 표의 머리 서명 색인 {열 수: [(열쇠, 머리 칸들)]} — 다른 문서의 표가 어느 기준본 표와 같은 머리인지 찾는다(같은 서명은 한 번)."""
    out, seen = {}, set()
    for b in (frame or {}).get("blocks") or ():
        t = b.get("table")
        if t is None or b["key"] in seen or ":h:" not in b["key"]:
            continue
        seen.add(b["key"])
        out.setdefault(t["cols"], []).append((b["key"], _heads(t)))
    for v in out.values():
        v.sort(key=lambda x: -len(x[1]))   # 머리가 많은 표부터(더 엄한 것 먼저)
    return out


def _has_heads(g, heads):
    """표 g 에 기준본 머리 칸들이 **차례대로 다** 있나 — 첫 행(r 0)의 머리는 같은 자리에, 그 아래는 (열·열 병합·글)이 차례대로(행이 끼어들어도 같다)."""
    at = {(c["r"], c["c"]): c for c in g["cells"]}
    k, cells = 0, g["cells"]
    for r, c, cs, text in heads:
        if r == 0:
            x = at.get((0, c))
            if x is None or x["cs"] != cs or norm(x["text"]) != text:
                return False
            continue
        while k < len(cells) and not (cells[k]["r"] > 0 and cells[k]["c"] == c and cells[k]["cs"] == cs and norm(cells[k]["text"]) == text):
            k += 1
        if k == len(cells):
            return False
        k += 1
    return True


def table_key(g, index):
    """표의 열쇠 — 기준본 표와 머리가 같으면 그 표의 열쇠, 아니면 칸 글 전체의 서명."""
    for key, heads in (index or {}).get(g["cols"], ()):
        if _has_heads(g, heads):
            return key
    return _all_key(g)


def block_key(b, index=None, doc=None, g=None):
    """본문 최상위 블록의 견줄 꼴(모듈 설명). index = table_index(frame), doc = 그림 바이트를 읽을 문서, g = 미리 읽은 격자."""
    t = b.get("type")
    if t == "table":
        return table_key(g or grid(b), index)
    if t == "image":
        name = b.get("media")
        try:
            return "I:" + (hashlib.sha1(doc.media(name)).hexdigest()[:12] if doc is not None and name else str(name))
        except (KeyError, OSError):
            return "I:" + str(name)
    return para_key(b.get("text"))


def rows(blocks, frame=None, doc=None, index=None):
    """본문 최상위 블록 → 견줄 줄(모듈 설명). 캡션 블록(captionOf)은 표·그림에 딸려 복사되므로 줄이 아니다."""
    index = table_index(frame) if index is None else index
    out = []
    for b in blocks or ():
        if b.get("captionOf"):
            continue
        t = b.get("type")
        row = {"i": len(out), "id": b["id"], "kind": "tbl" if t == "table" else "pic" if t == "image" else "p"}
        if t == "table":
            g = grid(b)
            row.update(key=table_key(g, index), text=_short(" | ".join(x for c in g["cells"][:8] if (x := _WS.sub(" ", c["text"]).strip()))), table=g)
        else:
            row.update(key=block_key(b, index, doc), text=b.get("text") or "")
        out.append(row)
    return out


# ---- 자리 정보 -----------------------------------------------------------------------------------------------

def orgs_of(values):
    """[{key, name, role}] — 주관 → 공동 차례(key = merge_pairs.org_key)."""
    return [{"key": P.org_key(core.org_name(values, k)), "name": core.org_name(values, k), "role": "lead" if k == 0 else "joint"}
            for k in range(len(values["orgs"]["joint"]) + 1)]


def _memberships(blocks, values):
    """구분 기준 묶음 항목 → ({블록·칸 id: {"org"|"year"|"stage": (항목 크기, 값, 라벨 id)}}, 문단 라벨 id 모음, 라벨 칸 id 모음, 기관-연도 표 id 모음). 가장 안쪽(작은) 항목이 이긴다."""
    best, para_labels, cell_labels, org_year = {}, set(), set(), set()
    for g in core.find(blocks, rnd.levels_of(blocks), values):
        if g.get("orgYear") and g.get("table"):
            org_year.add(g["table"])
        base = g.get("yearBase") or 0
        for it in g["items"]:
            ident = P._ident(g["dim"], it["value"], it.get("labelText"), values, base)
            if g["dim"] == core.ORG:
                what, val = "org", ident[1] if ident and ident[0] == "org" and ident[1] else UNKNOWN
            elif ident and ident[0] in ("year", "stage") and isinstance(ident[1], int):
                what, val = ident
            else:
                continue
            ids = set(it.get("scope") or ())
            if it.get("label"):
                ids.add(it["label"])
                (cell_labels if g.get("table") or str(it["label"]).startswith("c") else para_labels).add(it["label"])
            for x in ids:
                cur = best.setdefault(x, {})
                if what not in cur or len(ids) < cur[what][0]:
                    cur[what] = (len(ids), val, it.get("label"))
    return best, para_labels, cell_labels, org_year


def _scope(m, values):
    """항목 소속 m({"org": (…), "year": (…), "stage": (…)} | None) → scope 사전."""
    m = m or {}
    org, year, stage = (m.get(k, (0, None, None)) for k in ("org", "year", "stage"))
    st = stage[1] if stage[1] is not None else core.stage_year(values, year[1])[0] if year[1] is not None else None
    kind = "common" if org[1] is None else "unknown" if org[1] == UNKNOWN else "org"
    return {"kind": kind, "org": org[1] if kind == "org" else None, "year": year[1], "stage": st,
            "labels": [x for x in (year[2], org[2]) if x]}


def _title(n):
    return _short(_NOTE.sub("", f"{n.get('letter') or ''} {n.get('text') or ''}") or n.get("letter") or "", TITLE_MAX)


def _chain(by_id, n):
    """그래프에서 n 의 조상 노드(안쪽 → 바깥)."""
    out, seen = [], set()
    n = by_id.get((n or {}).get("parent"))
    while n is not None and n["id"] not in seen and len(out) < 16:
        seen.add(n["id"])
        out.append(n)
        n = by_id.get(n.get("parent"))
    return out


def _path_org(nodes, keys):
    """윗 제목들(안쪽 → 바깥) 가운데 기관 낱말이 든 구분 라벨 → (기관 열쇠 | UNKNOWN, 라벨 문단 id) | None. 절 제목(「8-3.」·「8.」)이 먼저 나오면 그 바깥은 안 본다(merge_pairs._path_org)."""
    for n in nodes:
        raw = P._ws(f"{n.get('letter') or ''} {n.get('text') or ''}")
        if core.SECTION.match(raw) or P._CHAPTER.match(raw):
            return None
        if n.get("role") == "label" and core.ORG_RE.search(raw):
            hit = [k for k in keys if k and k in P.org_key(raw)]
            return (max(hit, key=len) if hit else UNKNOWN), n.get("para")
    return None


def _para_cls(b, node, labels):
    text = b.get("text") or ""
    if not text.strip() or PLACE.match(text):
        return "guide"
    if b["id"] in labels or (node or {}).get("role") == "label":
        return "label"
    if text.lstrip().startswith("※") or placeholder(text):
        return "guide"
    return "title" if (node or {}).get("role") in TITLE_ROLES else "fixed"


def make(side):
    """배포 기준본의 자리 정보(모듈 설명) — side 를 읽기만 한다."""
    blocks = side.get("blocks")
    if blocks is None:
        blocks = side["doc"].blocks()
    values = core.norm_values(side["values"])
    graph, s3 = side.get("graph") or {}, side.get("tables") or {}
    best, para_labels, cell_labels, org_year = _memberships(blocks, values)
    orgs = orgs_of(values)
    keys = sorted({o["key"] for o in orgs if o["key"]}, key=len, reverse=True)
    by_id = {n["id"]: n for n in graph.get("nodes") or ()}
    body = {n["para"]: n for n in graph.get("nodes") or () if n.get("flow") == "body"}
    tabs = {t["id"]: t for t in s3.get("tables") or ()}
    guides = {t["id"] for t in s3.get("tempTables") or () if t.get("why") == "guide"}
    out, cur = [], None   # cur = 지금까지 본 마지막 본문 제목 노드
    for b in blocks:
        if b.get("captionOf"):
            continue
        t, node = b.get("type"), body.get(b["id"])
        if node is not None and (node.get("role") not in (*TITLE_ROLES, "label") or PLACE.match(b.get("text") or "")):
            node = None   # 글머리만 있는 줄·헤딩이 아닌 줄은 소속 사슬에 안 든다
        above = [cur, *_chain(by_id, cur)] if node is None and cur is not None else _chain(by_id, node)
        sc = _scope(best.get(b["id"]), values)
        if sc["kind"] == "common" and (hit := _path_org([node, *above] if node is not None else above, keys)):
            sc.update(kind="unknown" if hit[0] == UNKNOWN else "org", org=None if hit[0] == UNKNOWN else hit[0], labels=[*sc["labels"], *([hit[1]] if hit[1] else [])])
        row = {"i": len(out), "id": b["id"], "kind": "tbl" if t == "table" else "pic" if t == "image" else "p",
               "path": [x for x in (_title(n) for n in reversed(above)) if x and not PLACE.match(x)][-PATH_MAX:], "scope": sc}   # 글머리만 있는 줄은 소속이 아니다
        if t == "table":
            g, t3 = grid(b), tabs.get(b["id"])
            role = {c["id"]: c.get("role") for c in (t3 or {}).get("cells") or ()}
            calc = {f["cell"] for f in (t3 or {}).get("formulas") or ()}
            for c in g["cells"]:
                head = t3 is None or role.get(c["id"]) in HEAD_ROLES or c["id"] in cell_labels
                c["cls"] = "calc" if c["id"] in calc else "complex" if c.pop("cx") else "head" if head and norm(c["text"]) else "input"
                cs = _scope(best.get(c["id"]), values) if c["id"] in best else None
                if cs is not None and any(cs[k] != sc[k] for k in ("kind", "org", "year", "stage")):
                    c["scope"] = cs
            subs = [s for s in (t3 or {}).get("subtables") or () if s.get("kind") not in SKIP_SUB]
            g["list"] = b["id"] in org_year or (len(subs) == 1 and subs[0].get("kind") == "matrix" and not subs[0].get("headerCols")
                                                 and bool(subs[0].get("headerRows")) and not calc)
            g["guide"] = b["id"] in guides
            heads = _heads(g)
            row.update(key=_head_key(g["cols"], heads) if heads else _all_key(g), cls="table", table=g,
                       text=_short(" | ".join(x for c in g["cells"][:8] if (x := _WS.sub(" ", c["text"]).strip()))))
        elif t == "image":
            row.update(key=block_key(b, None, side.get("doc")), cls="pic", text="")
        else:
            row.update(key=para_key(b.get("text")), cls=_para_cls(b, node, para_labels), text=b.get("text") or "")
            if node is not None:
                cur = node
        out.append(row)
    return {"rev": side.get("rev"), "values": values, "orgs": orgs, "blocks": out}
