"""양식의 표 판정 — 확정본의 꼴 · 구조 견주기 · 저장(spec_테이블매니저 ② §10 「양식의 표 판정」). 문서 · 세션 · 서버를 모른다(`app.server` 를 import 하지 않는다).

사람이 한 번 확정한 표 판정(모든 칸의 역할 · 띠 · 고정 머리글)을 양식마다 저장해 두고, 구조가 꼭 같은 표에 다시 쓴다 — 저절로 배워서 저절로 쓰지 않는다(astra 3차: artifacts/table_manager_astra_2026-11-19/answer3.md).

- **확정본** `{id, form: 양식 키, type: 표 타입(table_kv.type_key), name: 보일 이름(머리글), rows, cols, geometry: [[행, 열, 행 병합, 열 병합, 음영 0|1]…](모든 칸 · 정렬),
  roles: [[행, 열, 역할]…](**모든 칸**), bands: [{id, rows, cols, kind, headerRows, headerCols}…], labels: [[행, 열, 견줄 글, 가변 0|1]…](헤더 · 제목 · 안내 역할의 칸),
  from: {work, table, rev, source}, rev: 판(고칠 때마다 +1), at}`. **칸의 값은 저장하지 않는다** — 자리 · 역할 · 머리글뿐(필드 · 간격 칸의 글은 어디에도 안 든다 · 가변 머리글의 글도 비워 둔다).
  역할을 띠(헤더 행 · 열 수)로 되살리지 않는다 — 엔진이 다시 내용을 읽기 때문이다(음영 값 칸에 수를 채우면 필드 → 열헤더): 모든 칸의 역할을 자리로 지닌다.
- **견줄 글**(`label_text`) = 칸 글에서 공백을 뺀 글(긴 글은 앞 `LABEL_MAX` 자 + 전체 글의 해시 — 뒤쪽만 다른 글도 가른다).
  **가변 머리글** = 문서마다 달라도 되는 머리 칸(기관 이름 · 연도 · 차수) — 견주지 않는다. 기본 = 구분 기준의 값 머리(`basisKind == "value"`)인 헤더 칸(`default_variable`), 사람이 확정 화면에서 더하거나 뺀다.
- **맞는 확정본**(`match`): ① `geometry` 가 꼭 같고(모든 칸의 자리 · 병합 · 음영 — 행 · 열 수 포함) ② 가변이 아닌 `labels` 의 글이 모두 같은 것이 **하나뿐일 때** 그것.
  행이 늘어난 표 · 병합이 다른 표 · 중간에 줄이 끼인 표 · 고정 머리글이 바뀐 표는 안 맞는다(「마지막 띠를 늘려」 쓰지 않는다).
  **더 좁은 확정본이 먼저**(`pick` — astra 4차: artifacts/table_manager_astra_2026-11-19/answer4.md 7번): 둘 이상이 맞을 때, 그 가운데 하나의 고정 머리글 칸(`fixed_cells`)이 다른 모든 것의 고정 머리글 칸을 **다 품고 더 많으면** 그것을 쓴다
  (한 표에서는 값 칸인 자리가 다른 표에서는 고정 행머리인 두 표 — 둘째 표를 따로 확정하면 그 글이 있는 표는 둘째 확정본, 그 자리에 다른 값이 든 표는 첫 확정본). 서로 품지 않으면 쓰지 않는다(`state_of` = ambiguous).
  표 타입은 **거르는 조건이 아니다**(음영 칸의 글에서 숫자만 뺀 해시라 기관 이름 같은 가변 머리글 · 글을 채운 음영 값 칸에서 달라진다) — 「같은 타입의 확정본은 있으나 안 맞음」(changed)을 가를 때만 쓴다.
- 저장: **서버 전체에 하나** — 헤딩 저장소 폴더(`heading_rules.store_dir()` — env `NFM_HEADINGS`)의 `table_types.json` `{version: 1, forms: {양식 키: {확정본 id: 확정본}}, removed: [지운 확정본…]}`(양식마다 여럿 — 타입마다 하나로 덮지 않는다).
  저장이 꺼져 있으면(`NFM_HEADINGS=off`) 메모리. 통째 원자적 저장(임시 파일 → 바꿔 넣기 · 프로세스 안 잠금). 손상된 파일(JSON · 파일의 꼴): 조회는 빈 목록, 고치는 길(`put` · `delete` · `restore`)은 `Broken` 으로 멈춘다(덮어쓰지 않는다).
  **틀린 확정본 하나하나는 읽을 때 건너뛴다**(`clean` 을 못 넘는 것 — 목록 조회가 그것 때문에 죽지 않게). 건너뛴 것이 있는 파일을 고쳐 쓸 때는 쓰기 전의 파일을 옆에 `table_types.json.skipped-<때>` 로 남긴다.
- **저장 전 검사**(`clean` · `_stamped` — 확정 · 되살리기 · 파일을 읽을 때 같이): 수는 유한한 정수(`at` 은 유한한 수) · 칸의 자리와 병합은 표(`rows`×`cols`) 안 · 띠는 표 안이고 서로 안 겹침 · 머리 행 · 열 수는 띠의 크기 이하 · 역할 · 띠 종류는 정해진 값.
- `list(form)` · `get(id)` · `put(확정본, replace=None, expect=None)`(같은 구조 — 격자와 고정 머리글이 꼭 같은 것, 또는 `replace` 로 가리킨 것 — 가 있으면 고침 `rev` +1 · 기대 판이 다르면 `StaleVersion`) · `delete(id)` · `restore(id)`.
  확정본은 `put` 을 부를 때만 생긴다(읽기 · 견주기는 아무것도 저장하지 않는다). 지운 확정본은 파일의 `removed`(마지막 `REMOVED_MAX` 개)에 남고, **되살리기는 그 가운데 id 로만** 한다 — 밖에서 받은 확정본을 저장하지 않는다(astra 4차 9번).
- 이 모듈의 `list` 는 확정본 목록을 주는 함수다 — 모듈 안에서 내장 `list(…)` 를 쓰지 않는다."""
import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import uuid

from app import heading_rules as R
from app import heading_tables as HT
from app.table_kv import type_key

FILE = "table_types.json"
VERSION = 1            # 파일 꼴의 판
LABEL_ROLES = ("colhead", "rowhead", "corner", "title", "note")   # 헤더 · 제목 · 안내 — 머리글을 견주는 역할(필드 · 간격 칸의 글은 값이라 안 본다)
HEAD_ROLES = ("colhead", "rowhead", "corner")
BAND_KEYS = ("id", "rows", "cols", "kind", "headerRows", "headerCols")
LABEL_MAX = 120        # 견줄 글의 길이 — 넘으면 앞 LABEL_MAX 자 + 「…」 + 전체 글의 해시 10자
NAME_MAX = 60
NAME_PART = 20
FORM_MAX = 60
CELLS_MAX = 4000       # table_excel.MAX_CELLS 와 같은 한도(그보다 큰 표는 판정하지 않는다)
ENTRIES_MAX = 2000     # 양식 하나의 확정본 수
REMOVED_MAX = 20       # 지운 확정본을 지니는 수(되살리기 — 마지막 것부터)
INT_MAX = 1_000_000    # 행 · 열 · 판 같은 수의 위 끝 — 그보다 큰 수는 틀린 값이다
AT_MAX = 1e11          # `at`(초)의 위 끝
_ID = re.compile(r"^e[0-9a-f]{10}$")
_TYPE = re.compile(r"^[0-9a-f]{12}$")
_WS = re.compile(r"\s+")
_LOCK = threading.RLock()
_MEMORY = {}           # 저장 끔(off)일 때의 저장소 {"data": …}
_CACHE = {}            # 읽어 둔 파일 {"mark": (경로, 고친 때, 크기), "data": 저장소} — 표 서식 점검 · 키-값이 표마다 부르므로 같은 파일을 다시 읽고 검사하지 않는다

StaleVersion = R.StaleVersion


class Broken(ValueError):
    """저장 파일이 손상됨 — 고치지 않는다(API 503)."""


# ---- 확정본의 꼴 · 견주기(순수) ---------------------------------------------------------------------------------------

def ref(row, col):
    """격자 자리 → 「B3」."""
    s, c = "", col + 1
    while c:
        c, m = divmod(c - 1, 26)
        s = chr(65 + m) + s
    return f"{s}{row + 1}"


def label_text(cell):
    """칸의 견줄 글 — 공백을 뺀 글. 긴 글은 앞 LABEL_MAX 자 + 전체 글의 해시(저장은 짧게, 견주기는 글 전체로). cell = heading_tables.collect 꼴(textFull)."""
    t = cell.get("textFull") if cell.get("textFull") is not None else cell.get("text")
    s = "".join((t or "").split())
    return s if len(s) <= LABEL_MAX else f"{s[:LABEL_MAX]}…{hashlib.sha1(s.encode('utf-8')).hexdigest()[:10]}"


def geometry_of(tb):
    """표의 격자 — 모든 칸의 [행, 열, 행 병합, 열 병합, 음영 0|1](행 · 열 차례). tb = heading_tables.collect 꼴."""
    return sorted([x["row"], x["col"], x["rs"], x["cs"], 1 if x.get("shaded") else 0] for x in tb["cells"])


def default_variable(table):
    """가변 머리글의 기본 — 구분 기준의 값 머리(`basisKind == "value"` — 「1차년도」 · 기관 이름 · 연도)인 헤더 칸의 id. table = `table_manager.judge()["table"]`."""
    return [x["id"] for x in table["cells"] if x.get("role") in HEAD_ROLES and x.get("basisKind") == "value"]


def name_of(table, var=()):
    """보일 이름 — 고정 머리글 몇 개(제목 · 열헤더 · 귀퉁이, 없으면 행헤더). 값 칸 · 가변 머리글(var — 칸 id 들)의 글은 안 쓴다. table = `judge()["table"]`."""
    cells = sorted(table["cells"], key=lambda x: (x["row"], x["col"]))
    for roles in (("title", "colhead", "corner"), ("rowhead",)):
        parts = [_WS.sub(" ", x.get("textFull") or "").strip()[:NAME_PART] for x in cells if x.get("role") in roles and x["id"] not in var]
        parts = [p for p in parts if p][:3]
        if parts:
            return " · ".join(parts)[:NAME_MAX]
    return f"{table['rows']}×{table['cols']} 표"


def entry_of(judgment, form, variable=None, origin=None):
    """`table_manager.judge()` 의 결과 → 확정본의 내용(id · rev · at 은 `put` 이 붙인다). 역할 = 그 판정의 **최종 역할**(헤더 지정 · 확정본 · 3단계 · 초안을 합친 것 — 사람이 화면에서 보고 확정하는 그것).
    form = 양식 키(또는 `{key, …}`). variable = 가변 머리글로 둘 칸 id 들(None = 기본 `default_variable` · 빈 목록 = 가변 없음) — 헤더 · 제목 · 안내 칸이 아닌 id 는 무시한다.
    origin = `from` 에 적을 것 {work, table, rev, source}. **필드 · 간격 칸의 글은 읽지 않는다.**"""
    tb = judgment["table"]
    cells = sorted(tb["cells"], key=lambda x: (x["row"], x["col"]))
    var = set(default_variable(tb) if variable is None else variable)
    var = {x["id"] for x in cells if x["id"] in var and x["role"] in LABEL_ROLES}
    o = origin if isinstance(origin, dict) else {}
    return {"form": form.get("key") if isinstance(form, dict) else form, "type": type_key(tb), "name": name_of(tb, var), "rows": tb["rows"], "cols": tb["cols"],
            "geometry": geometry_of(tb), "roles": [[x["row"], x["col"], x["role"]] for x in cells],
            "bands": [{k: ([*b[k]] if k in ("rows", "cols") else b[k]) for k in BAND_KEYS} for b in judgment["subs"]],
            "labels": [[x["row"], x["col"], "" if x["id"] in var else label_text(x), 1 if x["id"] in var else 0] for x in cells if x["role"] in LABEL_ROLES],
            "from": {"work": o.get("work"), "table": o.get("table") or tb.get("id"), "rev": o.get("rev"), "source": o.get("source") or judgment.get("source")}}


def why_not(entry, tb):
    """확정본이 표에 안 맞는 까닭 → None(맞음) | {"what": "size"} | {"what": "geometry"} | {"what": "labels", "labels": [{cell, ref, now, template}]}.
    tb = heading_tables.collect 꼴(칸마다 row · col · rs · cs · shaded · textFull — 역할은 안 본다)."""
    cells = tb.get("cells") or []
    if entry["rows"] != tb.get("rows") or entry["cols"] != tb.get("cols") or len(entry["geometry"]) != len(cells):
        return {"what": "size"}
    if entry["geometry"] != geometry_of(tb):
        return {"what": "geometry"}
    at = {(x["row"], x["col"]): x for x in cells}
    bad = []
    for r, c, text, var in entry["labels"]:
        x = at[(r, c)]
        now = label_text(x)
        if not var and now != text:
            bad.append({"cell": x["id"], "ref": ref(r, c), "now": now, "template": text})
    return {"what": "labels", "labels": bad} if bad else None


def fits(entry, tb):
    """확정본이 이 표의 구조와 꼭 같은가 — 격자(모든 칸의 자리 · 병합 · 음영 · 행 · 열 수)와 가변이 아닌 머리글의 글."""
    return why_not(entry, tb) is None


def matches(entries, tb):
    """이 표에 맞는 확정본 전부."""
    return [e for e in entries or () if fits(e, tb)]


def fixed_cells(entry):
    """확정본의 고정 머리글 칸 — 가변이 아닌 `labels` 의 자리 {(행, 열)}."""
    return {(r, c) for r, c, _t, v in entry["labels"] if not v}


def pick(hits):
    """맞는 확정본들(`matches`) 가운데 쓸 것 → 확정본 | None. 하나면 그것. 둘 이상이면 **더 좁은 확정본이 먼저** — 하나의 고정 머리글 칸이 다른 모든 것의 고정 머리글 칸을 다 품고 더 많을 때 그것
    (그 표에만 있는 고정 머리글까지 맞은 확정본이다). 서로 품지 않으면 None(어느 쪽도 쓰지 않는다 — 짐작하지 않는다)."""
    if len(hits) <= 1:
        return hits[0] if hits else None
    sets = [fixed_cells(e) for e in hits]
    return next((e for i, e in enumerate(hits) if all(k == i or sets[k] < sets[i] for k in range(len(hits)))), None)


def match(entries, tb):
    """이 표에 맞는 확정본 → 확정본 | None. 맞는 것이 하나면 그것, 둘 이상이면 더 좁은 것(`pick`), 그런 것이 없으면 None(`state_of` 의 ambiguous: 어느 쪽도 쓰지 않는다)."""
    return pick(matches(entries, tb))


def state_of(entries, tb, kind=None):
    """표의 상태 — confirmed(쓸 확정본이 하나로 정해짐) | ambiguous(둘 이상이 맞고 더 좁은 것이 없음) | changed(같은 타입의 확정본은 있으나 구조 · 머리글이 달라 안 맞음) | none.
    kind = 이 표의 타입(`table_kv.type_key` — 모르면 None: changed 를 가르지 않는다)."""
    hits = matches(entries, tb)
    if hits:
        return "confirmed" if pick(hits) is not None else "ambiguous"
    return "changed" if kind and any(e.get("type") == kind for e in entries or ()) else "none"


def template_of(entry):
    """확정본 → `table_manager.judge` 의 `template` 꼴 {id, rev, roles, bands}(새 목록 — 저장된 것을 고치지 않는다)."""
    return {"id": entry["id"], "rev": entry["rev"], "roles": [[*x] for x in entry["roles"]],
            "bands": [{k: ([*b[k]] if k in ("rows", "cols") else b[k]) for k in BAND_KEYS} for b in entry["bands"]]}


def variable_cells(entry, tb):
    """확정본이 가변으로 둔 머리 칸 → 이 표의 그 자리 칸 id 들(확정본이 이 표에 맞을 때 쓴다)."""
    at = {(x["row"], x["col"]): x["id"] for x in tb.get("cells") or ()}
    return [at[(r, c)] for r, c, _t, var in entry["labels"] if var and (r, c) in at]


def differs(entry, table, key="auto"):
    """확정본과 역할이 다른 칸 [{cell, ref, now, template}] — table = 확정본 **없이** 낸 판정의 표(`judge()["table"]`), now = 그 판정의 자동 역할(`auto` — 3단계 결과 · 초안).
    확정본이 무엇을 바로잡고 있는지를 보이는 데 쓴다(값을 채워 초안이 흔들린 칸)."""
    want = {(r, c): role for r, c, role in entry["roles"]}
    out = []
    for x in sorted(table["cells"], key=lambda x: (x["row"], x["col"])):
        w, now = want.get((x["row"], x["col"])), x.get(key) or x.get("role")
        if w is not None and now != w:
            out.append({"cell": x["id"], "ref": ref(x["row"], x["col"]), "now": now, "template": w})
    return out


def overlaps(entry, entries):
    """entry 와 **함께 맞아 어느 쪽도 안 쓰이는 표가 있을 수 있는** 다른 확정본들 — 격자가 꼭 같고, 둘 다 고정으로 둔 머리 칸의 글이 서로 어긋나지 않는데, 고정 머리글 칸이 서로를 품지 않는 것
    (한쪽이 다른 쪽을 다 품으면 더 좁은 쪽이 쓰인다 — `pick`). 확정한 뒤 사람에게 알리는 데 쓴다(저절로 지우거나 고르지 않는다)."""
    mine, cells = {(r, c): t for r, c, t, v in entry["labels"] if not v}, fixed_cells(entry)
    out = []
    for e in entries or ():
        if e.get("id") == entry.get("id") or e["rows"] != entry["rows"] or e["cols"] != entry["cols"] or e["geometry"] != entry["geometry"]:
            continue
        theirs = fixed_cells(e)
        if all(mine.get((r, c), t) == t for r, c, t, v in e["labels"] if not v) and not (theirs < cells or cells < theirs):
            out.append(e)
    return out


def separable(hit, entry):
    """그 표에 맞아 쓰이는 확정본(hit) 말고 **그 표만 따로 확정**할 수 있는가 → (bool, 못 하는 까닭 | ""). entry = 지금 확정하려는 것(`clean` 을 거친 꼴 — 그 표에서 지은 것이라 hit 의 고정 머리글과 글이 같다).
    따로 확정한 것이 그 표에 쓰이려면 더 좁아야 한다(`pick`): hit 의 고정 머리글 칸을 다 품고 **글이 있는 고정 머리글 칸**이 더 있어야 한다 — 더 있는 것이 빈 칸뿐이면 그 자리가 빈 다른 표까지 새 확정본으로 읽힌다."""
    mine, theirs = fixed_cells(entry), fixed_cells(hit)
    if not theirs < mine:
        return False, "이 표에만 있는 고정 머리글이 없습니다 — 따로 확정해도 이 표에는 지금 확정본이 쓰입니다(이 표에만 있는 머리 칸을 헤더 지정으로 헤더로 만든 뒤 따로 확정하거나, 이 확정본을 고치세요)"
    if not any(t for r, c, t, v in entry["labels"] if not v and (r, c) not in theirs):
        return False, "이 표에만 있는 고정 머리글이 빈 칸뿐입니다 — 따로 확정하면 그 자리가 빈 다른 표까지 새 확정본으로 읽힙니다(글이 있는 머리 칸이 있어야 합니다)"
    return True, ""


def same_judgment(a, b):
    """두 확정본의 판정 내용(역할 · 띠 · 머리글과 가변 여부)이 같은가 — 둘 다 `clean` 을 거친 꼴."""
    return (a["roles"], a["bands"], a["labels"]) == (b["roles"], b["bands"], b["labels"])


def summary(entry):
    """확정본의 요약(목록 · 화면용 — 격자 · 역할 · 머리글 글은 뺀다)."""
    return {"id": entry["id"], "rev": entry["rev"], "at": entry.get("at"), "form": entry["form"], "type": entry["type"], "name": entry["name"], "rows": entry["rows"], "cols": entry["cols"],
            "cells": len(entry["geometry"]), "fixed": sum(1 for x in entry["labels"] if not x[3]), "variable": sum(1 for x in entry["labels"] if x[3]), "from": dict(entry.get("from") or {})}


def key_of(entry):
    """확정본의 구조 열쇠 — 격자와 고정 머리글(견주는 것 전부)의 해시. 열쇠가 같은 두 확정본은 늘 같은 표에 맞으므로 하나만 둔다(`put` 이 고친다)."""
    src = [entry["rows"], entry["cols"], entry["geometry"], [[r, c, t] for r, c, t, v in entry["labels"] if not v]]
    return hashlib.sha1(json.dumps(src, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


# ---- 꼴 검사 --------------------------------------------------------------------------------------------------------

def _int(v, lo=0, hi=INT_MAX):
    """유한한 정수인가 — 참/거짓 · 소수(무한대 · NaN 포함) · 터무니없이 큰 수는 아니다."""
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _seq(v):
    return isinstance(v, (tuple, type([])))


def clean(entry):
    """확정본의 내용(form · type · name · rows · cols · geometry · roles · bands · labels · from)을 정리한 꼴로 — 꼴이 틀리면 ValueError. id · rev · at 은 여기서 안 본다.
    저장된 확정본은 늘 쓸 수 있는 것이어야 한다: 모든 칸에 역할이 있고 · 모든 칸이 한 띠에 들고 · 머리글 목록이 헤더 · 제목 · 안내 역할의 칸과 꼭 같다.
    수는 유한한 정수 · 칸의 자리와 병합은 표 안 · 띠는 표 안이고 서로 안 겹치고 머리 행 · 열 수가 띠의 크기 이하 · 역할 · 띠 종류는 정해진 값(spec_테이블매니저 ② §10 「양식의 표 판정」 — 저장 전 검사)."""
    if not isinstance(entry, dict):
        raise ValueError("확정본이 아닙니다")
    form, kind, name = entry.get("form"), entry.get("type"), entry.get("name")
    if not isinstance(form, str) or not form.strip() or len(form) > FORM_MAX:
        raise ValueError(f"form: 양식 키(1~{FORM_MAX}자)")
    if not isinstance(kind, str) or not _TYPE.match(kind):
        raise ValueError("type: 표 타입(12자리)")
    name = _WS.sub(" ", name).strip()[:NAME_MAX] if isinstance(name, str) else ""
    rows, cols, geo = entry.get("rows"), entry.get("cols"), entry.get("geometry")
    if not _int(rows, 1) or not _int(cols, 1):
        raise ValueError("rows · cols: 1 이상의 정수")
    if not _seq(geo) or not 2 <= len(geo) <= CELLS_MAX:
        raise ValueError(f"geometry: 칸 2~{CELLS_MAX}개의 목록")
    out_g, seen = [], set()
    for g in geo:
        if not _seq(g) or len(g) != 5 or not _int(g[0]) or not _int(g[1]) or not _int(g[2], 1) or not _int(g[3], 1) or not _int(g[4], 0, 1) \
                or g[0] + g[2] > rows or g[1] + g[3] > cols or (g[0], g[1]) in seen:
            raise ValueError("geometry: [행, 열, 행 병합, 열 병합, 음영 0|1] — 표 안의 자리 · 자리마다 하나")
        seen.add((g[0], g[1]))
        out_g.append([*g])
    if out_g != sorted(out_g):
        raise ValueError("geometry: 행 · 열 차례여야 합니다")
    out_r, role_at = [], {}
    for x in entry.get("roles") if _seq(entry.get("roles")) else ():
        if not _seq(x) or len(x) != 3 or not _int(x[0]) or not _int(x[1]) or (x[0], x[1]) not in seen or (x[0], x[1]) in role_at or not isinstance(x[2], str) or x[2] not in HT.ROLES:
            raise ValueError("roles: [행, 열, 역할] — 그 표의 칸 · 자리마다 하나")
        role_at[(x[0], x[1])] = x[2]
        out_r.append([*x])
    if set(role_at) != seen:
        raise ValueError("roles: 모든 칸의 역할이 있어야 합니다")
    out_b = []
    for b in entry.get("bands") if _seq(entry.get("bands")) else ():
        ok = isinstance(b, dict) and isinstance(b.get("id"), str) and b["id"] and len(b["id"]) <= 8 and isinstance(b.get("kind"), str) and b["kind"] in HT.KINDS
        ok = ok and _int(b.get("headerRows")) and _int(b.get("headerCols"))
        ok = ok and all(_seq(b.get(k)) and len(b[k]) == 2 and _int(b[k][0]) and _int(b[k][1]) and b[k][0] < b[k][1] for k in ("rows", "cols"))
        if not ok:
            raise ValueError("bands: {id, rows: [처음, 끝), cols: [처음, 끝), kind, headerRows, headerCols}")
        if b["rows"][1] > rows or b["cols"][1] > cols:
            raise ValueError(f"bands: 띠 {b['id']} 가 표({rows}×{cols}) 밖입니다")
        if b["headerRows"] > b["rows"][1] - b["rows"][0] or b["headerCols"] > b["cols"][1] - b["cols"][0]:
            raise ValueError(f"bands: 띠 {b['id']} 의 머리 행 · 열 수가 띠보다 큽니다")
        out_b.append({k: ([*b[k]] if k in ("rows", "cols") else b[k]) for k in BAND_KEYS})
    if not out_b or len({b["id"] for b in out_b}) != len(out_b):
        raise ValueError("bands: 띠가 하나 이상 · id 가 서로 달라야 합니다")
    for i, a in enumerate(out_b):
        for b in out_b[i + 1:]:
            if a["rows"][0] < b["rows"][1] and b["rows"][0] < a["rows"][1] and a["cols"][0] < b["cols"][1] and b["cols"][0] < a["cols"][1]:
                raise ValueError(f"bands: 띠 {a['id']} · {b['id']} 가 겹칩니다")
    if not all(any(b["rows"][0] <= r < b["rows"][1] and b["cols"][0] <= c < b["cols"][1] for b in out_b) for r, c in seen):
        raise ValueError("bands: 모든 칸이 한 띠에 들어야 합니다")
    out_l, lab = [], set()
    for x in entry.get("labels") if _seq(entry.get("labels")) else ():
        if not _seq(x) or len(x) != 4 or not _int(x[0]) or not _int(x[1]) or (x[0], x[1]) not in seen or (x[0], x[1]) in lab or not isinstance(x[2], str) or len(x[2]) > LABEL_MAX + 11 \
                or not _int(x[3], 0, 1):
            raise ValueError("labels: [행, 열, 견줄 글, 가변 0|1] — 그 표의 칸 · 자리마다 하나")
        lab.add((x[0], x[1]))
        out_l.append([x[0], x[1], "" if x[3] else x[2], x[3]])
    if lab != {p for p, role in role_at.items() if role in LABEL_ROLES}:
        raise ValueError("labels: 헤더 · 제목 · 안내 역할의 칸과 꼭 같아야 합니다")
    o = entry.get("from") if isinstance(entry.get("from"), dict) else {}
    origin = {"work": o.get("work") if isinstance(o.get("work"), str) else None, "table": o.get("table") if isinstance(o.get("table"), str) else None,
              "rev": o.get("rev") if _int(o.get("rev")) else None, "source": o.get("source") if isinstance(o.get("source"), str) else None}
    return {"form": form, "type": kind, "name": name or f"{rows}×{cols} 표", "rows": rows, "cols": cols, "geometry": out_g, "roles": sorted(out_r), "bands": out_b,
            "labels": sorted(out_l), "from": origin}


def _stamped(eid, body, rev, at):
    """저장 꼴의 확정본 — id · 내용 · 판 · 때. 판은 1 이상의 정수, 때(`at`)는 없거나 유한한 수(무한대 · NaN 은 틀린 값 — 저장하면 그 뒤 목록을 JSON 으로 못 낸다)."""
    if not isinstance(eid, str) or not _ID.match(eid):
        raise ValueError("id 가 확정본의 id 꼴이 아닙니다")
    if not _int(rev, 1):
        raise ValueError("rev: 1 이상의 정수")
    if at is not None and not (isinstance(at, (int, float)) and not isinstance(at, bool) and math.isfinite(at) and 0 <= at <= AT_MAX):
        raise ValueError("at: 유한한 수(초)")
    return {"id": eid, **body, "rev": rev, "at": at}


# ---- 저장 ----------------------------------------------------------------------------------------------------------

def _path():
    d = R.store_dir()
    return None if d is None else d / FILE


def _empty():
    return {"version": VERSION, "forms": {}, "removed": []}


_BAD = (ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError)   # 틀린 확정본 하나를 읽다 날 수 있는 것 — 그 확정본만 건너뛴다


def _parse(data):
    """파일 내용 → 저장소 {version, forms, removed(, skipped: 건너뛴 수)}. 파일의 꼴(객체 · 판 · forms · 양식마다의 묶음)이 틀리면 ValueError.
    **틀린 확정본 하나하나는 건너뛴다**(`clean` · `_stamped` 를 못 넘는 것 — 무한대가 든 `at` · 표 밖의 띠 …): 그것 때문에 다른 확정본까지 못 읽지 않게. 지운 확정본(`removed`)도 같은 검사를 거친 것만 지닌다."""
    if not isinstance(data, dict) or not isinstance(data.get("forms"), dict) or data.get("version") != VERSION:
        raise ValueError("양식의 표 판정 파일 꼴이 아닙니다")
    out, skipped = _empty(), 0
    for form, bucket in data["forms"].items():
        if not isinstance(form, str) or not isinstance(bucket, dict):
            raise ValueError(f"forms.{form}: 확정본 묶음이 아님")
        got = {}
        for eid, e in bucket.items():
            try:
                body = clean(e)
                if body["form"] != form:
                    raise ValueError("양식 키가 다름")
                got[eid] = _stamped(eid, body, e.get("rev"), e.get("at"))
            except _BAD:
                skipped += 1
        if got:
            out["forms"][form] = got
    for e in data.get("removed") if _seq(data.get("removed")) else ():
        try:
            out["removed"].append(_stamped(e.get("id"), clean(e), e.get("rev"), e.get("at")))
        except _BAD:
            skipped += 1
    out["removed"] = out["removed"][-REMOVED_MAX:]
    if skipped:
        out["skipped"] = skipped
    return out


def _shared(strict=False):
    """저장소(읽기 전용 — **고치지 않는다**: 같은 파일을 다시 읽지 않게 지니고 있는 것을 그대로 준다). 잠금 안에서 부른다. 손상 · 못 읽음은 `load` 의 설명대로."""
    p = _path()
    if p is None:
        return _MEMORY.get("data") or _empty()
    try:
        st = p.stat()
        mark = (str(p), st.st_mtime_ns, st.st_size)
        if _CACHE.get("mark") == mark:
            return _CACHE["data"]
        raw = R._retry(p.read_bytes)
    except FileNotFoundError:
        return _empty()
    except OSError:
        if strict:
            raise
        return _empty()
    try:
        data = _parse(json.loads(raw.decode("utf-8")))
    except (ValueError, KeyError, TypeError) as e:   # json 오류도 ValueError
        if strict:
            raise Broken(f"양식의 표 판정 파일이 손상되어 고치지 않았습니다: {p} ({e}) — 파일을 고치거나 옮긴 뒤 다시 하세요") from e
        return _empty()
    _CACHE.update(mark=mark, data=data)
    return data


def load(strict=False):
    """저장소 {version, forms: {양식 키: {id: 확정본}}, removed: [지운 확정본 — 마지막 REMOVED_MAX 개](, skipped: 읽을 때 건너뛴 틀린 확정본 수)}(새 사본 — 고쳐도 된다) — 없으면 빈 것. 손상(JSON · 꼴): strict=False(조회)면 빈 것, strict=True(고치기 전)면 `Broken`. 못 읽으면(OSError) 조회는 빈 것 · 고치기는 그 오류."""
    with _LOCK:
        st = json.loads(json.dumps(_shared(strict)))
        st.setdefault("removed", [])
        return st


def _dump(data):
    """저장 글 — 확정본 하나가 한 줄(격자 · 역할 목록이 길다: 들여 쓰면 칸마다 여러 줄이 된다)."""
    def one(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"), allow_nan=False)   # 무한대 · NaN 은 쓰지 않는다(ValueError — 저장하지 않는다)
    forms = []
    for form, bucket in data["forms"].items():
        if bucket:
            forms.append(f" {one(form)}:{{\n" + ",\n".join(f"  {one(eid)}:{one(e)}" for eid, e in bucket.items()) + "\n }")
    gone = data.get("removed") or []
    return (f'{{"version":{one(data["version"])},"forms":{{' + ("\n" + ",\n".join(forms) + "\n" if forms else "") + '},"removed":['
            + ("\n" + ",\n".join(f" {one(e)}" for e in gone) + "\n" if gone else "") + "]}\n")


def _save(data):
    """통째 원자적 저장(임시 파일 → 바꿔 넣기). 잠금 안에서 부른다. data = `load(strict=True)` 로 읽어 고친 것 — 읽을 때 건너뛴 확정본이 있었으면(`skipped`) 쓰기 전의 파일을 옆에 남긴다
    (건너뛴 것은 새 파일에 없다 — 조용히 잃지 않게)."""
    p = _path()
    _CACHE.clear()
    skipped = data.pop("skipped", 0)
    if p is None:
        _MEMORY["data"] = json.loads(json.dumps(data))
        return
    text = _dump(data).encode("utf-8")
    p.parent.mkdir(parents=True, exist_ok=True)
    if skipped and p.is_file():
        shutil.copyfile(p, p.with_name(f"{p.name}.skipped-{time.strftime('%Y%m%d-%H%M%S')}"))
    tmp = p.with_name(f"{p.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_bytes(text)
        R._retry(lambda: os.replace(tmp, p))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _MEMORY.pop("data", None)


def _order(entries):
    return sorted(entries, key=lambda e: (-(e.get("at") or 0), e["name"], e["id"]))


def list(form=None):  # noqa: A001 — 사양의 이름(모듈 안에서 내장 list 를 쓰지 않는다)
    """그 양식의 확정본 전부(최근에 확정한 것부터) — form 이 None 이면 모든 양식의 것. 돌려준 확정본은 **고치지 않는다**(지니고 있는 것을 그대로 준다 — 고칠 것은 `template_of` · `summary` 처럼 새로 만든다)."""
    with _LOCK:
        forms = _shared()["forms"]
        if form is None:
            return _order([e for bucket in forms.values() for e in bucket.values()])
        return _order((forms.get(form) or {}).values()) if isinstance(form, str) else []


def get(eid):
    """확정본 하나 | None(돌려준 것은 고치지 않는다)."""
    if not isinstance(eid, str):
        return None
    with _LOCK:
        return next((bucket[eid] for bucket in _shared()["forms"].values() if eid in bucket), None)


def put(entry, replace=None, expect=None):
    """확정본을 저장 → 저장한 확정본(id · rev · at 이 붙은 것). entry = `entry_of` 의 결과.
    같은 구조의 확정본이 이미 있으면 **그것을 고친다**(id 그대로 · `rev` +1): `replace`(확정본 id — 지금 그 표에 맞아 쓰이고 있는 것)를 주면 그것, 안 주면 구조 열쇠(`key_of` — 격자와 고정 머리글)가 같은 것.
    없으면 새로(`rev` 1) — 같은 양식 · 같은 타입에 다른 구조의 확정본이 있어도 덮지 않는다. expect = 고칠 확정본의 기대 판 — 지금 판과 다르거나 그 확정본이 없으면 `StaleVersion`.
    ValueError 꼴이 틀림 · replace 가 다른 양식의 것 · 열쇠가 같은 확정본이 따로 있음 / Broken 파일 손상 / OSError 못 씀."""
    body = clean(entry)
    expect = R.expect_version(expect)
    if replace is not None and (not isinstance(replace, str) or not _ID.match(replace)):
        raise ValueError("replace 가 확정본의 id 꼴이 아닙니다")
    key = key_of(body)
    with _LOCK:
        st = load(strict=True)
        bucket = st["forms"].setdefault(body["form"], {})
        same = next((e for e in bucket.values() if key_of(e) == key), None)
        cur = bucket.get(replace) if replace is not None else same
        if replace is not None and cur is None:
            raise StaleVersion("그 확정본이 없습니다(지워졌습니다) — 다시 읽으세요")
        if cur is not None and same is not None and same["id"] != cur["id"]:
            raise ValueError("같은 구조 · 같은 머리글의 확정본이 따로 있습니다 — 그것을 지우거나 그 표에서 확정하세요")
        if cur is None:
            if expect is not None:
                raise StaleVersion("그 확정본이 없습니다(지워졌습니다) — 다시 읽으세요")
            if len(bucket) >= ENTRIES_MAX:
                raise ValueError(f"한 양식의 확정본은 {ENTRIES_MAX}개까지 저장합니다 — 안 쓰는 것을 지우세요")
            rec = _stamped("e" + uuid.uuid4().hex[:10], body, 1, round(time.time(), 3))
        else:
            if expect is not None and expect != cur["rev"]:
                raise StaleVersion(f"확정본이 그 사이 바뀌었습니다(지금 판 {cur['rev']}, 요청 {expect}) — 다시 읽으세요")
            rec = _stamped(cur["id"], body, cur["rev"] + 1, round(time.time(), 3))
        bucket[rec["id"]] = rec
        _save(st)
        return json.loads(json.dumps(rec))


def delete(eid):
    """확정본을 지운다 → 지운 확정본. 지운 것은 저장소의 `removed` 에 남는다(마지막 `REMOVED_MAX` 개 — `restore(id)` 가 거기서 되살린다). 없는 id 는 KeyError · 파일 손상은 Broken."""
    with _LOCK:
        st = load(strict=True)
        for form, bucket in st["forms"].items():
            if isinstance(eid, str) and eid in bucket:
                gone = bucket.pop(eid)
                if not bucket:
                    del st["forms"][form]
                st["removed"] = ([e for e in st["removed"] if e["id"] != eid] + [gone])[-REMOVED_MAX:]
                _save(st)
                return json.loads(json.dumps(gone))
        raise KeyError(eid)


def removed():
    """지운 확정본들(되살릴 수 있는 것 — 오래된 것부터 · 돌려준 것은 고치지 않는다)."""
    with _LOCK:
        return [*(_shared().get("removed") or ())]


def restore(eid):
    """지운 확정본을 그대로 되살린다(id · rev · at 그대로) → 되살린 확정본. **저장소가 지닌 지운 확정본(`removed`)에서만** — 밖에서 받은 확정본을 저장하는 길이 아니다(새 확정은 `put`).
    KeyError 그 id 의 지운 확정본이 없음(지운 적이 없거나 오래돼 밀려남) / ValueError id 꼴이 아님 · 그 id 가 이미 있음 · 구조 열쇠가 같은 확정본이 그 사이 생김 / Broken 파일 손상."""
    if not isinstance(eid, str) or not _ID.match(eid):
        raise ValueError("id 가 확정본의 id 꼴이 아닙니다")
    with _LOCK:
        st = load(strict=True)
        rec = next((e for e in reversed(st["removed"]) if e["id"] == eid), None)
        if rec is None:
            raise KeyError(eid)
        if any(eid in bucket for bucket in st["forms"].values()):
            raise ValueError("이미 있는 확정본입니다")
        key, bucket = key_of(rec), st["forms"].setdefault(rec["form"], {})
        if any(key_of(e) == key for e in bucket.values()):
            raise ValueError("같은 구조 · 같은 머리글의 확정본이 그 사이 생겼습니다 — 되살리지 않았습니다")
        if len(bucket) >= ENTRIES_MAX:
            raise ValueError(f"한 양식의 확정본은 {ENTRIES_MAX}개까지 저장합니다 — 안 쓰는 것을 지우세요")
        bucket[eid] = rec
        st["removed"] = [e for e in st["removed"] if e["id"] != eid]
        _save(st)
        return json.loads(json.dumps(rec))
