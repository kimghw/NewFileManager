"""헤딩 추출 3단계 — 표 구조(spec_헤딩_추출 ② §8): 표마다 칸의 역할(열헤더·행헤더·귀퉁이·필드·제목·안내·간격)과 **서브 테이블**(한 표 안에서
헤더 구조가 다시 시작하는 행 띠·열 띠), 헤더 트리(열헤더·행헤더의 부모 사슬)와 필드마다의 (행헤더 경로, 열헤더 경로). 문서를 바꾸지 않는다.

흐름: 1단계 결과(문단 레코드의 그릇 사슬 — 표·칸·fill) → 표·칸 모으기 → **스크립트 초안**(칸 성격 → 행 띠 나누기 → 띠마다 헤더 행·헤더 열 세기 → 이웃 규칙으로 역할)
→ **T 호출**(표 묶음마다: 서브 테이블 영역·헤더 행/열 수·초안과 다른 칸만 — LLM 은 칸의 값을 보고 판단) → 검증·적용 → 헤더 트리·필드 경로·되풀이·문제.
LLM 이 없거나 실패하면 초안 그대로(`llm.fallback`·표마다 `undecided`).

용어(② §0): **열헤더**(colhead) = 아래 칸들의 이름, **행헤더**(rowhead) = 오른쪽 칸들의 이름(키-값 양식의 키도), **귀퉁이**(corner) = 헤더 행과 헤더 열이 겹치는 칸,
**필드**(field) = 채우는 값 칸(빈 칸·자리표시·값), **제목**(title) = 표(서브 테이블) 전체 너비의 제목 행, **안내**(note) = ※·작성 요령 글, **간격**(spacer) = 빈 전체 너비 행.
1칸 표(글상자)는 표로 세지 않고 그 글을 바깥 칸에 합친다(2단계의 「투명 1칸 상자」 와 같음)."""
import hashlib
import json
import re
import time
from collections import Counter, defaultdict

from app import heading_llm as HL
from app import heading_calc as HC
from app import heading_rules as R

VERSION = 2  # 2 = 표 의미(§9) 키 추가
ROLES = ("colhead", "rowhead", "corner", "field", "title", "note", "spacer")
KINDS = ("matrix", "form", "list", "title", "note", "spacer", "plain")
MIN_CELLS_LLM = 4       # 이보다 작은 표(1~3칸)는 LLM 에 안 보냄(초안 그대로)
BATCH_CELLS = 500       # T 호출 하나에 담는 칸 수 상한(큰 표 하나는 혼자)
BATCH_TABLES = 10
TABLE_GUIDES_MAX = 4000  # T 호출에 표 하나마다 싣는 작성 지침 글의 합(spec ② §20) — 넘는 지침은 빼고 자료에 guidesCut(KEIT 연차보고서 표지 표의 각주 29개 ≈ 3.4천 자)
MAX_HEADER_ROWS = 4
MAX_HEADER_COLS = 4
TEXT_MAX = 80
_WHITE = (None, "", "#FFFFFF", "NONE", "none")
_BLANKY = re.compile(r"^[\s()\[\]（）［］_·․~～\-–—.,:/]*$")
_CHECK = re.compile(r"[\[（(]\s*[√✓vV]?\s*[\])）]")
_ORDINAL = re.compile(r"^\s*(?:\d{1,3}|[①-⑳⑴-⒇㉠-㉭㉮-㉻]|[가-힣]|[a-zA-Z]|[ⅰ-ⅻⅠ-Ⅻ])\s*[.)]?\s*$")
_STUB_WORDS = re.compile(r"번\s*호|순\s*번|구\s*분|항\s*목|내\s*용|명$|기관|지표|단계|연도|차년도|No\.?|목표|성명|이름|대상", re.I)
_NOTE_WORDS = re.compile(r"작성\s*(?:가이드라인|요령|방법|예시)|※|☞|유의\s*사항")
SENT_END = re.compile(r"(?:다|음|함|요|임|것|됨|있음|없음)\.?\s*$")
_DIGITS = re.compile(r"\d+")


# ---- 표·칸 모으기 ------------------------------------------------------------------------------------------

def _tid(item):
    return item.get("id") or f"k{item.get('key')}"


def _cid(item):
    return item.get("id") or f"k{item.get('key')}"


def _new_cell(item):
    return {"id": _cid(item), "row": int(item.get("row") or 0), "col": int(item.get("col") or 0), "rs": max(1, int(item.get("rs") or 1)),
            "cs": max(1, int(item.get("cs") or 1)), "fill": item.get("fill"), "paras": [], "n": None, "texts": [], "kinds": Counter(), "bolds": [],
            "fmts": Counter(), "nested": [], "ordinal": False}


def _add_para(cell, rec):
    cell["paras"].append(rec["id"])
    if cell["n"] is None:
        cell["n"] = rec["n"]
    kind = rec["kind"]
    if kind in ("empty", "object"):
        cell["kinds"][kind] += 1
        return
    cell["texts"].append(rec["text"].replace(R.BR, " ").strip())
    cell["kinds"][kind] += 1
    cell["bolds"].append(bool((rec["char"]["text"] or {}).get("bold")))
    if rec.get("fmt"):
        cell["fmts"][rec["fmt"]] += 1
    if kind == "marker" and rec.get("blank"):
        cell["ordinal"] = True


def collect(stage1, skip=()):
    """1단계 레코드 → 표 목록(문서 순) [{id, key, host, depth, rows, cols, n, parentCell, cells: [칸…]}]. 여러 칸 표만(1칸 상자는 투명 — 그 글은 바깥 칸에).
    skip = 건너뛸 문단 id(TEMP 표 안의 문단 — spec ② §15): 그 표는 목록에 없고 바깥 칸의 글·「칸 안 표」 에도 안 든다."""
    tables = {}
    for rec in stage1["paras"]:
        if rec["id"] in skip:
            continue
        path = rec.get("path") or []
        inner = None  # 이 문단이 직접 든 「여러 칸 표」 의 칸 자리(path 인덱스)
        for i in range(len(path) - 1, -1, -1):
            c = path[i]
            if c["t"] == "cell" and i and path[i - 1]["t"] == "tbl" and path[i - 1].get("cells") != 1:
                inner = i
                break
        for i, c in enumerate(path):
            if c["t"] != "tbl" or c.get("cells") == 1:
                continue
            tid = _tid(c)
            tb = tables.get(tid)
            if tb is None:
                outer = next((path[j] for j in range(i - 1, -1, -1)  # 바깥 「여러 칸 표」 의 칸(1칸 상자의 칸은 투명)
                              if path[j]["t"] == "cell" and j and path[j - 1]["t"] == "tbl" and path[j - 1].get("cells") != 1), None)
                tb = tables[tid] = {"id": tid, "key": c.get("key"), "host": c.get("host"), "depth": sum(1 for x in path[:i] if x["t"] == "tbl" and x.get("cells") != 1) + 1,
                                    "rows": int(c.get("rows") or 0), "cols": int(c.get("cols") or 0), "n": rec["n"], "parentCell": _cid(outer) if outer else None,
                                    "cells": {}}
            item = path[i + 1] if i + 1 < len(path) and path[i + 1]["t"] == "cell" else None
            if item is None:
                continue
            cid = _cid(item)
            cell = tb["cells"].get(cid)
            if cell is None:
                cell = tb["cells"][cid] = _new_cell(item)
            if i + 1 == inner:
                _add_para(cell, rec)
            else:
                nxt = next((x for x in path[i + 2:] if x["t"] == "tbl" and x.get("cells") != 1), None)
                if nxt is not None and _tid(nxt) not in cell["nested"]:
                    cell["nested"].append(_tid(nxt))
    out = []
    for tb in sorted(tables.values(), key=lambda t: t["n"]):
        cells = sorted(tb["cells"].values(), key=lambda x: (x["row"], x["col"]))
        for cell in cells:
            full = " ".join(t for t in cell["texts"] if t)
            cell["textFull"] = full
            cell["text"] = full[:TEXT_MAX]
            cell["shaded"] = cell["fill"] not in _WHITE
            cell["bold"] = (all(cell["bolds"]) if cell["bolds"] else None)
            cell["fmt"] = cell["fmts"].most_common(1)[0][0] if cell["fmts"] else None
            cell["kinds"] = dict(cell["kinds"])
            for k in ("texts", "bolds", "fmts"):
                cell.pop(k)
            cell["nature"] = nature(cell)
        tb["cells"] = cells
        tb["rows"] = max([tb["rows"]] + [c["row"] + c["rs"] for c in cells])
        tb["cols"] = max([tb["cols"]] + [c["col"] + c["cs"] for c in cells])
        out.append(tb)
    return out


def _texty_kinds(kinds):
    return {k: v for k, v in kinds.items() if k not in ("empty", "object")}


def nature(cell):
    """칸 성격(초안의 근거) — header(강: 음영 칸) · headish(약: 굵은 짧은 글·라벨) · text(중립: 짧은 보통 글·순번) · field(빈 칸·값·자리표시·체크 칸·긴 글·글머리 글) · note(※·작성 요령)."""
    kinds, text = _texty_kinds(cell["kinds"]), cell["textFull"]
    n = sum(kinds.values())
    if not n:
        return "header" if cell["shaded"] else "empty"
    if kinds.get("note") or kinds.get("footnote") or (not cell["shaded"] and _NOTE_WORDS.search(text)):
        return "note"
    if cell["shaded"]:
        return "header" if len(text) <= 40 or kinds.get("label") else "headish"
    vals = kinds.get("data", 0) + kinds.get("placeholder", 0)
    if vals and vals >= n:
        return "field"
    if _BLANKY.match(text) or _CHECK.search(text):
        return "field"
    if cell["ordinal"] and n == 1:
        return "text"  # 「1.」「①」 홀로 — 순번 자리(행머리 후보)
    if kinds.get("marker") and (n >= 2 or len(text) > 30):
        return "field"  # 글머리 글 내용
    if len(text) > 40 or n >= 3 or SENT_END.search(text):
        return "field"
    if cell["bold"] and len(text) <= 24:
        return "headish"
    if kinds.get("label") and n == 1:
        return "headish"
    return "text"


# ---- 격자 -------------------------------------------------------------------------------------------------

def grid(tb):
    """{(r, c): 칸} — 칸이 덮는 모든 자리(병합 포함). 겹치면 먼저 온 칸."""
    occ = {}
    for cell in tb["cells"]:
        for r in range(cell["row"], cell["row"] + cell["rs"]):
            for c in range(cell["col"], cell["col"] + cell["cs"]):
                occ.setdefault((r, c), cell)
    return occ


def _starts(occ, r, c0, c1):
    """행 r 에서 시작하는 칸들(왼쪽 → 오른쪽), 열 범위 안."""
    out, seen = [], set()
    for c in range(c0, c1):
        cell = occ.get((r, c))
        if cell is not None and cell["row"] == r and id(cell) not in seen:
            seen.add(id(cell))
            out.append(cell)
    return out


def _cut_ok(occ, r, c0, c1):
    """행 경계 r-1|r 를 걸치는 칸이 없나."""
    return all(occ[(r, c)]["row"] == r for c in range(c0, c1) if (r, c) in occ)


def _is_header_row(cells):
    nat = [x["nature"] for x in cells]
    if not nat or any(x in ("field", "note", "text", "empty") for x in nat):
        return False
    return "header" in nat or len(nat) >= 2


def _fieldish(cell):
    return cell is not None and cell["nature"] in ("empty", "field", "text")


def _shaded_blank(cell):
    """글 없는 음영 칸 — 성격은 header(강)지만 이름이 없으니 헤더 행·열 밖에서는 음영 값 칸(합계·총액 줄, 「합계」 열)으로 본다."""
    return cell["nature"] == "header" and not cell["textFull"]


def _value_row(occ, a, r, cols, starts):
    """행 r 이 띠 [a, r) 의 음영 값 행인가 — 「연구개발비 총액(M=K+L) | (음영 빈 칸)…」 처럼 왼쪽 이름 칸 뒤가 모두 글 없는 음영 칸이고, 그 띠의 앞선 행 가운데
    **같은 자리에서 이름과 값이 갈리는 행**(「간접비(L) | (빈 칸)…」)이 있는 행. 시작 칸이 모두 음영이라 헤더 행처럼 보이지만 헤더가 다시 시작하는 것이 아니다
    (2026-11-10 연구개발기관별 사용계획 총괄표 — 총액 행이 딴 띠로 잘려 코드 식이 끊김). 앞선 행이 모두 빈 칸뿐이면(이름이 갈리는 자리를 모름) 예전대로 자른다."""
    named = [x for x in starts if x["textFull"]]
    blank = [x for x in starts if not x["textFull"]]
    if not named or len(blank) < len(named) or not all(_shaded_blank(x) for x in blank):
        return False
    edge = min(x["col"] for x in blank)  # 값 칸이 시작하는 열
    if any(x["col"] + x["cs"] > edge for x in named):
        return False
    for q in range(r - 1, a - 1, -1):
        prev = _starts(occ, q, 0, cols)
        left, right = [x for x in prev if x["col"] < edge], [x for x in prev if x["col"] >= edge]
        if left and right and all(x["col"] + x["cs"] <= edge and x["textFull"] and x["nature"] in ("header", "headish", "text") for x in left) \
                and all(_fieldish(x) or _shaded_blank(x) for x in right) and any(_fieldish(x) for x in right):
            return True
    return False


# ---- 초안: 띠 나누기 · 헤더 행/열 · 역할 ----------------------------------------------------------------------

def header_rows(tb, occ, r0, r1, c0, c1):
    """띠 위부터 이어지는 헤더 행 수 — 시작 칸이 모두 header·headish(음영·굵게·라벨)인 행(위에서 내려온 칸뿐인 행은 이어짐). 필드 행이 하나는 남아야 한다."""
    n = 0
    for r in range(r0, min(r1, r0 + MAX_HEADER_ROWS)):
        starts = _starts(occ, r, c0, c1)
        if not starts:
            n += 1
            continue
        if not _is_header_row(starts):
            break
        n += 1
    if r0 + n >= r1:
        return 0
    return n


def _col_header_text(occ, c, r0, hr):
    """열 c 위 헤더 행들의 가장 아래 열헤더 글."""
    for r in range(r0 + hr - 1, r0 - 1, -1):
        cell = occ.get((r, c))
        if cell is not None:
            return cell["textFull"]
    return ""


def header_cols(tb, occ, r0, r1, c0, c1, hr):
    """띠 왼쪽부터 이어지는 헤더 열 수(격자 열 단위). 필드 행에서 그 열에 시작하는 칸이 모두 헤더·중립 글(첫 열은 순번 값도)이고 오른쪽에 채울 칸이 있어야 한다.
    열 위의 열헤더 글이 번호·구분·항목·내용·명 같은 말이면 빈 칸이 섞여도 헤더 열(빈 양식 줄)."""
    n = 0
    body = range(r0 + hr, r1)
    for c in range(c0, min(c1, c0 + MAX_HEADER_COLS)):
        cells, seen = [], set()
        for r in body:
            cell = occ.get((r, c))
            if cell is None:
                continue
            if cell["col"] < c0:
                return n  # 띠 밖에서 넘어온 칸
            if cell["col"] == c and id(cell) not in seen:
                seen.add(id(cell))
                cells.append(cell)
        if not cells:
            break
        if c + max(x["cs"] for x in cells) >= c1:
            break  # 오른쪽에 아무것도 없는 마지막 열
        keyword = bool(hr) and bool(_STUB_WORDS.search(_col_header_text(occ, c, r0, hr) or ""))
        stubby = [x["nature"] in ("header", "headish", "text") or (c == c0 and x["nature"] == "field" and _ORDINAL.match(x["textFull"] or "") is not None)
                  for x in cells]
        named = sum(1 for x, s in zip(cells, stubby) if s and not _shaded_blank(x))  # 글 없는 음영 칸(합계·총액 줄의 값 칸)은 헤더 열의 근거가 아니다
        if not named:
            break
        if not all(stubby):
            if not (keyword and not any(x["nature"] in ("note",) for x in cells)):
                break
        if not any(x["nature"] in ("header", "headish") for x in cells) and not keyword:
            right = sum(1 for x in cells if _fieldish(occ.get((x["row"], x["col"] + x["cs"]))))
            if right < max(1, len(cells) // 2):
                break
        n += 1
    return n


def _band(r0, r1, c0, c1, **kw):
    return {"rows": [r0, r1], "cols": [c0, c1], **kw}


def _full_width(cell, c0, c1):
    return cell["col"] <= c0 and cell["col"] + cell["cs"] >= c1


def bands(tb, occ):
    """스크립트 초안의 행 띠 — ⓐ 전체 너비 한 칸 행은 자기 띠(제목·안내·간격), ⓑ 필드 행 뒤에 헤더 행(시작 칸 모두 음영·굵게)이 다시 오면 새 띠
    (그 띠의 음영 값 행 — 앞선 행과 같은 자리에서 갈리는 이름 + 글 없는 음영 칸들 — 은 헤더 행이 아니다 `_value_row`),
    ⓒ 열헤더가 있는 띠에서 키-값 행(음영 키 + 바로 오른쪽 필드)의 필드가 헤더 행의 열 경계와 안 맞으면 새 띠. 병합 칸을 가르는 경계는 안 자른다."""
    rows, cols = tb["rows"], tb["cols"]
    if cols <= 1:
        return [_band(0, rows, 0, cols, kind="list", headerRows=0, headerCols=0, source="script")]
    cuts, seen_field, prev_full = [0], False, False
    for r in range(rows):
        starts = _starts(occ, r, 0, cols)
        full = len(starts) == 1 and _full_width(starts[0], 0, cols) and starts[0]["rs"] == 1 and all(occ[(r, c)] is starts[0] for c in range(cols) if (r, c) in occ)
        if r and _cut_ok(occ, r, 0, cols):
            if full or prev_full:
                if cuts[-1] != r:
                    cuts.append(r)
                seen_field = False
            elif seen_field and _is_header_row(starts) and not _value_row(occ, cuts[-1], r, cols, starts):
                cuts.append(r)
                seen_field = False
        prev_full = full
        seen_field = seen_field or any(x["nature"] in ("field", "empty") for x in starts)
    cuts.append(rows)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if a < b:
            out += _split_kv(tb, occ, a, b, 0, cols)
    return out


def _split_kv(tb, occ, r0, r1, c0, c1):
    """규칙 ⓒ — 열헤더 띠 안에서 열 경계가 어긋난 키-값 행부터 새 띠로(재귀)."""
    hr = header_rows(tb, occ, r0, r1, c0, c1)
    if hr:
        ranges = set()  # 헤더 행 칸들의 열 범위 — 필드가 이 중 하나와 꼭 맞아야 「헤더 아래 칸」
        for r in range(r0, r0 + hr):
            for x in _starts(occ, r, c0, c1):
                ranges.add((x["col"], x["col"] + x["cs"]))
        seen_field = False
        for r in range(r0 + hr, r1):
            starts = _starts(occ, r, c0, c1)
            if seen_field and _cut_ok(occ, r, c0, c1):
                for x in starts:
                    right = occ.get((x["row"], x["col"] + x["cs"]))
                    if x["nature"] == "header" and right is not None and right["row"] == r and right["nature"] in ("empty", "field") \
                            and (right["col"], right["col"] + right["cs"]) not in ranges:
                        return _split_kv(tb, occ, r0, r, c0, c1) + _split_kv(tb, occ, r, r1, c0, c1)
            seen_field = seen_field or any(x["nature"] in ("field", "empty") for x in starts)
    return [_describe(tb, occ, _band(r0, r1, c0, c1, source="script"))]


def _describe(tb, occ, band):
    """띠의 헤더 행·열 수와 종류 — 전체 너비 한 칸이면 title·note·spacer."""
    (r0, r1), (c0, c1) = band["rows"], band["cols"]
    cells = cells_in(tb, band)
    if len(cells) == 1 and _full_width(cells[0], c0, c1) and cells[0]["row"] <= r0 and cells[0]["row"] + cells[0]["rs"] >= r1:
        nat = cells[0]["nature"]
        kind = "spacer" if nat == "empty" else "note" if nat in ("note", "field") else "title"
        return {**band, "kind": kind, "headerRows": 0, "headerCols": 0}
    if c1 - c0 <= 1:
        return {**band, "kind": "list", "headerRows": 0, "headerCols": 0}
    hr = band.get("headerRows")
    if not isinstance(hr, int) or hr < 0:
        hr = header_rows(tb, occ, r0, r1, c0, c1)
    hc = band.get("headerCols")
    if not isinstance(hc, int) or hc < 0:
        hc = header_cols(tb, occ, r0, r1, c0, c1, hr)
    kind = band.get("kind") if band.get("kind") in KINDS else None
    return {**band, "headerRows": min(hr, r1 - r0), "headerCols": min(hc, c1 - c0), "kind": kind or ("matrix" if hr else "form" if hc else "plain")}


def cells_in(tb, band):
    (r0, r1), (c0, c1) = band["rows"], band["cols"]
    return [x for x in tb["cells"] if r0 <= x["row"] < r1 and c0 <= x["col"] < c1]


def _neighbor(occ, band, r, c):
    (r0, r1), (c0, c1) = band["rows"], band["cols"]
    if not (r0 <= r < r1 and c0 <= c < c1):
        return None
    return occ.get((r, c))


def assign_roles(tb, occ, band):
    """띠 안 칸마다 역할 — 헤더 행 → colhead(헤더 열과 겹치면 corner), 헤더 열 → rowhead, 그 밖 헤더 성격 칸은 이웃 규칙(오른쪽이 채울 칸이면 rowhead,
    아래가 채울 칸이면 colhead, 둘 다 헤더면 병합 방향), 안내 → note, 나머지 → field. 전체 너비 한 칸 띠는 띠 종류가 역할.
    헤더 행·열이 있는 띠에서 그 밖에 놓인 **글 없는 음영 칸**은 field — 이름이 없는 칸은 헤더가 아니라 음영 값 칸(합계·총액 줄, 「합계」 열)이다."""
    (r0, r1), (c0, c1) = band["rows"], band["cols"]
    hr, hc = band["headerRows"], band["headerCols"]
    cells = cells_in(tb, band)
    if band["kind"] in ("title", "note", "spacer") and len(cells) == 1:
        cells[0]["role"] = band["kind"]
        return
    if band["kind"] == "list":
        for x in cells:
            x["role"] = "title" if x["nature"] in ("header", "headish") else "note" if x["nature"] == "note" or x["kinds"].get("marker") else "field"
        return
    for x in cells:
        in_hr, in_hc = x["row"] < r0 + hr, x["col"] < c0 + hc
        nat = x["nature"]
        if in_hr and in_hc:
            role = "corner"
        elif in_hr:
            role = "colhead"
        elif in_hc:
            role = "rowhead"
        elif nat == "note":
            role = "note"
        elif (hr or hc) and _shaded_blank(x):
            role = "field"
        elif nat in ("header", "headish"):
            right = _neighbor(occ, band, x["row"], x["col"] + x["cs"])
            down = _neighbor(occ, band, x["row"] + x["rs"], x["col"])
            rf, df = _fieldish(right), _fieldish(down)
            if rf and not df:
                role = "rowhead"
            elif df and not rf:
                role = "colhead"
            elif rf and df:
                role = "colhead" if x["cs"] > 1 and x["rs"] == 1 else "rowhead"
            elif x["rs"] > 1 and right is not None and x["cs"] <= x["rs"]:
                role = "rowhead"  # 여러 행에 걸친 헤더 — 오른쪽 헤더들의 부모
            elif x["cs"] > 1 and down is not None:
                role = "colhead"  # 여러 열에 걸친 헤더 — 아래 헤더들의 부모
            elif right is None and down is not None:
                role = "colhead"
            else:
                role = "rowhead"
        else:
            role = "field"
        x["role"] = role


def draft(tb):
    """표 하나의 스크립트 초안 → (띠 목록, 격자). 칸마다 role·draft(같은 값)."""
    occ = grid(tb)
    bs = bands(tb, occ)
    for i, b in enumerate(bs):
        b["id"] = _sub_id(i)
        assign_roles(tb, occ, b)
    for x in tb["cells"]:
        x.setdefault("role", "field")
        x["draft"] = x["role"]
    return bs, occ


def _sub_id(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# ---- T 호출(표 구조) ----------------------------------------------------------------------------------------

_KIND_LETTER = {"plain": "T", "label": "L", "data": "D", "placeholder": "P", "note": "N", "footnote": "N", "marker": "M", "empty": "E", "object": "O",
                "toc": "T", "caption": "T"}


def _token(cell):
    flags = ("F" if cell["shaded"] else "") + ("B" if cell["bold"] else "") + "".join(sorted({_KIND_LETTER.get(k, "T") for k in cell["kinds"]}))
    if not cell["textFull"] and cell["rs"] == 1 and cell["cs"] == 1 and cell["role"] == "field" and not cell["nested"]:
        return cell["id"]
    text = cell["textFull"][:30].replace("|", "/")
    if cell["nested"]:
        text = (text + " " if text else "") + f"〔표 {','.join(cell['nested'])}〕"
    return f"{cell['id']}|{cell['rs']}x{cell['cs']}|{flags}|{text}|{cell['role']}"


def table_payload(tb, occ, bs, before="", guides=None):
    """T 호출 자료의 표 하나. guides = 그 표의 작성 지침(table_guides — spec ② §20: 있을 때만 칸을 둔다 · input_key 는 이것 없이 셈한다)."""
    rows = []
    for r in range(tb["rows"]):
        row = []
        for c in range(tb["cols"]):
            cell = occ.get((r, c))
            if cell is None:
                row.append("")
            elif cell["row"] == r and cell["col"] == c:
                row.append(_token(cell))
            else:
                row.append("^" if cell["row"] < r else "<")
        rows.append(row)
    out = {"table": tb["id"], "rows": tb["rows"], "cols": tb["cols"], "cells": len(tb["cells"]), "before": before[:60],
           "draft": [{k: b[k] for k in ("id", "rows", "cols", "kind", "headerRows", "headerCols")} for b in bs], "grid": rows}
    if guides:
        out["guides"], cut = guides
        if cut:
            out["guidesCut"] = True
    return out


def table_guides(stage1, place, sent):
    """그 자리의 작성 지침 가운데 표에 붙은 것(pinned["place"]["tables"] — 본문 최상위 표 id 열쇠 · spec ② §20) → {T 로 보내는 표 id: ([{kind, text, label?, cell?}], 뺀 것이 있나)}.
    칸 안의 지침(각주 번호 · 칸 안 ※)은 그 문단이 든 **가장 안쪽 표**로(cell = 그 칸 id) · 표 바깥의 지침(표 바로 앞뒤 ※ · 칸 안의 작성 요령 표)은 그 표로 —
    그 표를 보내지 않으면(겉 상자 · 작은 표) 그 안에서 처음 보내는 표로, 그것도 없으면 싣지 않는다. 표마다 글의 합이 TABLE_GUIDES_MAX 를 넘게 하는 지침은 뺀다."""
    by_top = (place or {}).get("tables") or {}
    if not by_top:
        return {}
    where, first_in = {}, {}   # 문단 id → (가장 안쪽 표, 칸) · 최상위 표 → 그 안에서 처음 보내는 표
    for rec in stage1.get("paras") or ():
        tbls = [c["id"] for c in rec.get("path") or () if c.get("t") == "tbl" and c.get("id")]
        if not tbls:
            continue
        if rec.get("table"):
            where[rec["id"]] = (rec["table"], rec.get("cell"))
        if tbls[0] not in first_in:
            hit = next((t for t in tbls if t in sent), None)
            if hit:
                first_in[tbls[0]] = hit
    out = {}
    for top, rows in by_top.items():
        for g in rows:
            tid, cell = where.get(g.get("at")) or (None, None)
            if tid not in sent:
                tid, cell = (top if top in sent else first_in.get(top)), None
            if tid is None:
                continue
            one = {k: g[k] for k in ("kind", "label", "text") if g.get(k)}
            if cell:
                one["cell"] = cell
            got, size = out.setdefault(tid, ([], [0, False]))
            if size[0] + len(one.get("text", "")) > TABLE_GUIDES_MAX:
                size[1] = True
                continue
            size[0] += len(one.get("text", ""))
            got.append(one)
    return {tid: (got, size[1]) for tid, (got, size) in out.items() if got}


def input_key(tb, occ, bs):
    """그 표로 LLM 에 보내는 자료(초안 띠 + 격자 토막 — 칸 id · 크기 · 음영/굵게/문단 종류 · 글 30자 · 초안 역할)의 해시 — 「판정에 들어간 입력이 같은가」 의 열쇠
    (spec_테이블매니저 ② §2 「지금 판정」). **초안을 지은 바로 뒤**(LLM 답 · 사람 지정을 얹기 전)에 불러야 한다 — 토막에 그때의 역할이 든다. 표 앞 문단은 넣지 않는다."""
    return hashlib.sha1(json.dumps(table_payload(tb, occ, bs), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _before_text(stage1, tb, skip=()):
    """표 바로 앞의 글 있는 문단(이 표 안이 아닌 것) — 표 제목 맥락. 앞 39문단까지 본다. skip = 건너뛸 문단 id(TEMP 표 안의 문단 — spec ② §15:
    「작성 요령」 표의 글이 뒤 표의 제목 맥락이 되지 않게; 건너뛴 문단은 39문단 한도에 세지 않는다)."""
    paras = stage1["paras"]
    left = 39
    for i in range(tb["n"] - 1, -1, -1):
        rec = paras[i]
        if rec["id"] in skip:
            continue
        if left <= 0:
            break
        left -= 1
        if any(c["t"] == "tbl" and _tid(c) == tb["id"] for c in rec.get("path") or ()):
            continue
        if rec["text"].strip() and rec["kind"] not in ("empty", "object"):
            return rec["text"].replace(R.BR, " ").strip()
    return ""


def _noteish(rec):
    """안내 문단인가 — 1단계 kind note·footnote 또는 「※·☞·작성 가이드라인/요령/방법/예시·유의 사항」 글(spec ② §10 작성요령)."""
    return rec.get("kind") in ("note", "footnote") or bool(_NOTE_WORDS.search(rec.get("text") or ""))


def table_notes(stage1, tb, max_before=6, max_after=12):
    """표의 작성요령(spec ② §10) — [{where: before|cell|after, para, cell?, text}]: ① 표 안 안내 칸(역할 note · 성격 note) ② 표 바로 앞 같은 흐름의 잇단 안내 문단
    (빈·개체 문단은 건너뜀, 다른 글이 나오면 끝) ③ 표 바로 뒤 같은 꼴(다음 개체 문단이 나오면 끝). 스크립트만 — 문서를 다시 읽지 않는다."""
    out = []
    for x in tb["cells"]:
        if x.get("role") == "note" or x.get("nature") == "note":
            text = (x.get("textFull") or x.get("text") or "").strip()
            if text:
                out.append({"where": "cell", "cell": x["id"], "para": (x.get("paras") or [None])[0], "text": text[:300]})
    paras = stage1.get("paras") or []
    if not paras:
        return out
    inside = lambda rec: any(c["t"] == "tbl" and _tid(c) == tb["id"] for c in rec.get("path") or ())  # noqa: E731
    host = next((r for r in paras if r.get("id") == tb.get("host")), None)
    area = (host or {}).get("area") or "body"
    n0 = min(max(0, int(tb.get("n") or 0)), len(paras))
    before = []
    for i in range(n0 - 1, max(-1, n0 - 60), -1):
        rec = paras[i]
        if inside(rec) or rec.get("kind") in ("empty", "object") or not (rec.get("text") or "").strip():
            continue
        if rec.get("area") != area or not _noteish(rec) or len(before) >= max_before:
            break
        before.append(rec)
    for rec in reversed(before):
        out.append({"where": "before", "para": rec["id"], "text": rec["text"].replace(R.BR, " ").strip()[:300]})
    i = n0
    while i < len(paras) and inside(paras[i]):
        i += 1
    after = 0
    for j in range(i, min(len(paras), i + 80)):
        rec = paras[j]
        if inside(rec):
            continue
        if rec.get("kind") == "empty" or not (rec.get("text") or "").strip():
            if rec.get("kind") == "object":
                break  # 다음 표·그림
            continue
        if rec.get("kind") == "object" or rec.get("area") != area or not _noteish(rec) or after >= max_after:
            break
        out.append({"where": "after", "para": rec["id"], "text": rec["text"].replace(R.BR, " ").strip()[:300]})
        after += 1
    return out


def sendable(tb):
    return len(tb["cells"]) >= MIN_CELLS_LLM and tb["rows"] >= 2 and tb["cols"] >= 2


def t_jobs(tables, drafts, stage1, pinned=None, skip=()):
    """표를 문서 순으로 묶어(칸 BATCH_CELLS·표 BATCH_TABLES 까지, 큰 표는 혼자) T 호출 job 들 → (jobs, 쓴 지침)."""
    batches, cur, n = [], [], 0
    for tb in tables:
        if not sendable(tb):
            continue
        k = len(tb["cells"])
        if cur and (n + k > BATCH_CELLS or len(cur) >= BATCH_TABLES):
            batches.append(cur)
            cur, n = [], 0
        cur.append(tb)
        n += k
    if cur:
        batches.append(cur)
    jobs, used = [], {}
    place = (pinned or {}).get("place")   # 그 자리의 작성 지침(§20) — 표에 붙은 것만 그 표의 자료에
    guides = table_guides(stage1, place, {tb["id"] for b in batches for tb in b}) if place else {}
    for i, batch in enumerate(batches):
        tg = {tb["id"]: guides[tb["id"]] for tb in batch if tb["id"] in guides}
        data = {"tables": [table_payload(tb, drafts[tb["id"]][1], drafts[tb["id"]][0], _before_text(stage1, tb, skip), tg.get(tb["id"])) for tb in batch]}
        if tg:
            used["place"] = place["sha1"]
        content, u = HL.prompt(HL.TABLES_CONTRACT, ["tables", "tolerance"], data, pinned)
        used.update(u)
        jobs.append({"schema": HL.TABLES_SCHEMA, "content": content, "what": f"heading_tables#{i + 1}", "timeout": 900.0, "effort": "medium",
                     "_tables": [tb["id"] for tb in batch], "_guides": {t: len(g[0]) for t, g in tg.items() if g}})
    return jobs, used


def _regions(tb, items):
    """T 응답의 서브 테이블 영역 검증 → (띠 목록 | None, 까닭). 표 안·겹침 없음·모든 칸을 하나의 영역이 통째로 품어야 한다."""
    regs = []
    for it in items or []:
        rows, cols = it.get("rows"), it.get("cols")
        ok = (isinstance(rows, list) and isinstance(cols, list) and len(rows) == 2 and len(cols) == 2
              and all(isinstance(v, int) and not isinstance(v, bool) for v in rows + cols))
        if not ok:
            return None, f"영역 값이 정수 쌍이 아님: {it.get('sub')}"
        r0, r1 = rows
        c0, c1 = cols
        if not (0 <= r0 < r1 <= tb["rows"] and 0 <= c0 < c1 <= tb["cols"]):
            return None, f"영역이 표 밖: {it.get('sub')} {rows} {cols}"
        hr, hc = it.get("headerRows"), it.get("headerCols")
        regs.append(_band(r0, r1, c0, c1, id=str(it.get("sub") or "")[:8], kind=it.get("kind") if it.get("kind") in KINDS else None,
                          headerRows=hr if isinstance(hr, int) and not isinstance(hr, bool) else -1,
                          headerCols=hc if isinstance(hc, int) and not isinstance(hc, bool) else -1, note=str(it.get("note") or "")[:200], source="llm"))
    if not regs:
        return None, "영역 없음"
    for i, a in enumerate(regs):
        for b in regs[i + 1:]:
            if a["rows"][0] < b["rows"][1] and b["rows"][0] < a["rows"][1] and a["cols"][0] < b["cols"][1] and b["cols"][0] < a["cols"][1]:
                return None, f"영역이 겹침: {a['id']}·{b['id']}"
    for x in tb["cells"]:
        home = [g for g in regs if g["rows"][0] <= x["row"] < g["rows"][1] and g["cols"][0] <= x["col"] < g["cols"][1]]
        if len(home) != 1:
            return None, f"칸 {x['id']} 을 품은 영역이 {len(home)}개"
        g = home[0]
        if x["row"] + x["rs"] > g["rows"][1] or x["col"] + x["cs"] > g["cols"][1]:
            return None, f"영역 {g['id']} 가 병합 칸 {x['id']} 을 가름"
    regs = [g for g in regs if any(g["rows"][0] <= x["row"] < g["rows"][1] and g["cols"][0] <= x["col"] < g["cols"][1] for x in tb["cells"])]
    used = set()
    for i, g in enumerate(regs):  # 빈 id·겹치는 id 는 다시 매김
        if not g["id"] or g["id"] in used:
            g["id"] = _sub_id(i)
            while g["id"] in used:
                g["id"] += "'"
        used.add(g["id"])
    return sorted(regs, key=lambda g: (g["rows"][0], g["cols"][0])), ""


def apply_answer(tb, occ, bs, ans):
    """T 응답(표 하나) 적용 → (띠 목록, 변경 수, 거절 목록). 영역이 검증을 못 넘으면 초안 띠 + 헤더 수는 LLM 값, 칸 역할 덮어쓰기는 그래도 적용."""
    rejected, changed = [], 0
    regs, why = _regions(tb, ans.get("subtables"))
    if regs is None:
        rejected.append({"what": "subtables", "why": why})
        regs = bs
    else:
        regs = [_describe(tb, occ, g) for g in regs]
    for x in tb["cells"]:
        x["role"] = x["draft"]
    for g in regs:
        assign_roles(tb, occ, g)
    by_id = {x["id"]: x for x in tb["cells"]}
    for it in ans.get("cells") or []:
        cid, role = it.get("cell"), it.get("role")
        x = by_id.get(cid)
        if x is None:
            rejected.append({"what": "cell", "cell": cid, "why": "없는 칸 id"})
            continue
        if role not in ROLES:
            rejected.append({"what": "cell", "cell": cid, "why": f"모르는 역할 {role!r}"})
            continue
        x["role"] = role
        x["reason"] = str(it.get("reason") or "")[:200]
    for x in tb["cells"]:
        x["changed"] = x["role"] != x["draft"]
        changed += x["changed"]
    return regs, changed, rejected


# ---- 헤더 트리 · 필드 경로 · 되풀이 ----------------------------------------------------------------------------

def _covers(a, b, axis):
    """a 가 b 의 (axis 0 = 행, 1 = 열) 범위를 품나."""
    if axis == 0:
        return a["row"] <= b["row"] and b["row"] + b["rs"] <= a["row"] + a["rs"]
    return a["col"] <= b["col"] and b["col"] + b["cs"] <= a["col"] + a["cs"]


def _parent_col(x, heads):
    """열헤더 x 의 부모 — 바로 위에 끝나며 x 의 열 범위를 품는 열헤더(없으면 위쪽에서 가장 가까운 것)."""
    above = [h for h in heads if h is not x and h["row"] + h["rs"] <= x["row"] and _covers(h, x, 1)]
    if not above:
        return None
    return max(above, key=lambda h: (h["row"] + h["rs"], -h["cs"]))


def _parent_row(x, heads):
    left = [h for h in heads if h is not x and h["col"] + h["cs"] <= x["col"] and _covers(h, x, 0)]
    if not left:
        return None
    return max(left, key=lambda h: (h["col"] + h["cs"], -h["rs"]))


def _chain(x, parent_of):
    out, seen = [], set()
    p = parent_of.get(x["id"])
    while p is not None and p["id"] not in seen:
        seen.add(p["id"])
        out.append(p["id"])
        p = parent_of.get(p["id"])
    return out[::-1]


def _nearest(cells, pred, key):
    cand = [h for h in cells if pred(h)]
    return max(cand, key=key) if cand else None


def finish_band(tb, occ, band):
    """띠의 헤더 트리(colhead·rowhead 의 parent)와 필드 경로(rowPath·colPath — 위 → 아래, 왼쪽 → 오른쪽 조상 사슬 + 바로 붙은 헤더) → 띠 요약."""
    cells = cells_in(tb, band)
    (r0, r1), (c0, c1) = band["rows"], band["cols"]
    colheads = [x for x in cells if x["role"] in ("colhead", "corner")]
    rowheads = [x for x in cells if x["role"] in ("rowhead", "corner")]
    pc, pr = {}, {}
    for x in colheads:
        p = _parent_col(x, colheads)
        pc[x["id"]] = p
        if x["role"] == "colhead":
            x["parent"] = p["id"] if p else None
    for x in rowheads:
        p = _parent_row(x, rowheads)
        pr[x["id"]] = p
        if x["role"] == "rowhead":
            x["parent"] = p["id"] if p else None
    fields = [x for x in cells if x["role"] == "field"]
    for f in fields:
        # 열헤더: 위쪽에서 f 의 열 범위와 겹치며 가장 가까운(아래쪽) 열헤더
        ch = _nearest(colheads, lambda h: h["row"] + h["rs"] <= f["row"] and h["col"] < f["col"] + f["cs"] and f["col"] < h["col"] + h["cs"],
                      key=lambda h: (h["row"] + h["rs"], -h["cs"]))
        rh = _nearest(rowheads, lambda h: h["col"] + h["cs"] <= f["col"] and h["row"] < f["row"] + f["rs"] and f["row"] < h["row"] + h["rs"],
                      key=lambda h: (h["col"] + h["cs"], -h["rs"]))
        f["colPath"] = (_chain(ch, pc) + [ch["id"]]) if ch else []
        f["rowPath"] = (_chain(rh, pr) + [rh["id"]]) if rh else []
    counts = Counter(x["role"] for x in cells)
    issues = []
    for x in cells:
        if x["role"] in ("colhead", "rowhead") and not any(x["id"] in (f.get("colPath") or []) or x["id"] in (f.get("rowPath") or []) for f in fields) \
                and not any(pc.get(h["id"]) is x or pr.get(h["id"]) is x for h in colheads + rowheads):
            issues.append({"cell": x["id"], "why": "헤더인데 거느린 필드·헤더가 없음"})
    for f in fields:
        if not f["colPath"] and not f["rowPath"]:
            issues.append({"cell": f["id"], "why": "헤더 없는 필드"})
    norm = lambda s: _DIGITS.sub("N", (s or "").strip())[:20]  # noqa: E731
    sig_src = [band["kind"], band["headerRows"], band["headerCols"]] + [norm(x["textFull"]) for x in sorted(colheads, key=lambda h: (h["row"], h["col"]))] \
        + ["|"] + [norm(x["textFull"]) for x in sorted(rowheads, key=lambda h: (h["row"], h["col"])) if x["col"] < c0 + band["headerCols"]]
    sig = hashlib.sha1(json.dumps(sig_src, ensure_ascii=False).encode()).hexdigest()[:10] if (colheads or rowheads) else None
    return {**band, "counts": dict(counts), "cells": len(cells), "signature": sig, "issues": issues[:50]}


# ---- 3단계 실행 ---------------------------------------------------------------------------------------------

def _out_cell(x):
    return {k: x.get(k) for k in ("id", "row", "col", "rs", "cs", "fill", "shaded", "bold", "kinds", "text", "paras", "n", "nested", "nature", "draft", "role",
                                  "auto",  # 사람 지정이 덮은 칸에만 — 덮기 전 역할(spec_테이블매니저 ② §2 「지금 판정」: 지정을 풀면 풀리게)
                                  "sub", "parent", "rowPath", "colPath", "changed", "reason",
                                  "basis", "basisKind", "code", "expr", "subtotal", "num", "pct", "dec", "dash", "placeholder", "div", "formulas")  # §9
            if x.get(k) is not None or k in ("role", "draft", "text")}


def temp_tables(temp):
    """TEMP 라벨(heading_temp.label 결과) → (건너뛸 문단 id 집합 = TEMP 표 안의 문단, 결과에 남길 TEMP 표 목록 [{id, item, why, rule, rows, cols, n, host}]) —
    표 단위 항목 · 그 안쪽 표 · 칸 단위 항목 안의 표(1칸 상자 포함). rows·cols·n·host 는 표 단위 항목 자신의 표에만(안쪽 표는 None)."""
    if not temp:
        return frozenset(), []
    items = {it["id"]: it for it in temp.get("items") or ()}
    skip = frozenset(temp.get("tableParas") or ())
    out = []
    for tid, iid in (temp.get("tables") or {}).items():
        it = items.get(iid) or {}
        own = it.get("unit") == "table" and it.get("table") == tid
        out.append({"id": tid, "item": iid, "why": it.get("why"), "rule": it.get("rule"), "rows": it.get("rows") if own else None,
                    "cols": it.get("cols") if own else None, "n": it.get("n") if own else None, "host": it.get("host") if own else None})
    return skip, out


def ask_tables(stage1, *, ask=None, pinned=None, temp=None, progress=None, tables=None, drafts=None):
    """T 호출만 한다(spec ② §8 「헤딩 판정과 같이」) → asked {"answers": {표 id: 답 | None(그 호출이 실패 · 답에 그 표가 없음)}, "calls": [호출 기록], "guides": 쓴 지침,
    "jobs": 호출 수, "sent": 보낸 표 수, "summary": 호출들의 요약 글}. 보낼 표 · 초안 · 자료는 **1단계 결과에서만** 나온다 — 2단계(헤딩 그래프)에 기대는 것은 표의 소속뿐이고 그것은 build 가 붙인다.
    그래서 이 호출은 헤딩 판정(LLM)과 같이 돌 수 있다(heading_runs.TablesAhead). build(asked=…) 는 **같은 1단계 · 같은 TEMP** 로 부른다(표 id · 초안이 같아야 답이 맞는다).
    ask = llm.ask_all 대신(시험). progress(끝난 호출 수, 호출 수) = 시작할 때 (0, n) · 호출 하나가 끝날 때마다. tables · drafts = build 가 이미 모은 것(없으면 여기서 모은다)."""
    from app import llm
    skip, _ = temp_tables(temp)
    if tables is None:
        tables = collect(stage1, skip)
        drafts = {tb["id"]: draft(tb) for tb in tables}
    jobs, used = t_jobs(tables, drafts, stage1, pinned, skip)
    out = {"answers": {}, "calls": [], "guides": used, "jobs": len(jobs), "sent": sum(len(j["_tables"]) for j in jobs), "summary": ""}
    if (pinned or {}).get("place"):   # 그 자리의 작성 지침을 실은 표 · 지침 수(§20 — 결과 화면 · 기록)
        out["placeGuides"] = {"tables": sum(len(j["_guides"]) for j in jobs), "items": sum(n for j in jobs for n in j["_guides"].values())}
    if not jobs:
        return out
    if progress is not None:
        progress(0, len(jobs))
    clean = [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]
    results = ask(clean) if ask is not None else llm.ask_all(clean, progress=progress) if progress is not None else llm.ask_all(clean)
    summaries = []
    for job, res in zip(jobs, results):
        out["calls"].append(HL._call_record(job, res))
        data = res.get("data")
        if not data:
            for tid in job["_tables"]:
                out["answers"][tid] = None
            continue
        if data.get("summary"):
            summaries.append(str(data["summary"])[:300])
        got = {str(t.get("table")): t for t in data.get("tables") or [] if isinstance(t, dict)}
        for tid in job["_tables"]:
            out["answers"][tid] = got.get(tid, {"subtables": [], "cells": []}) if tid in got else None
    out["summary"] = " ".join(summaries)[:600]
    return out


def build(stage1, *, use_llm=True, ask=None, doc_name="", pinned=None, stage2=None, temp=None, roles=None, asked=None):
    """3단계 — 1단계 결과 → 표 구조 dict(spec ② §8 + 표 의미 §9). ask = llm.ask_all 대신(시험). use_llm False 면 스크립트 초안만. pinned = 실행 시작 때 고정한 지침.
    stage2 = 같은 1단계 실행의 2단계 결과(있으면 표의 소속을 그래프에서, 없으면 1단계 어림). temp = TEMP 라벨(§15) — TEMP 표는 표 구조를 만들지 않는다(`tempTables` 에만).
    roles = 사용자 헤더 지정 {표 id: {칸 id: rowhead | colhead | field}}(spec_owpml_편집 ② §5-4) — 초안·LLM 답 위에 덮는다(칸 `reason` 「사용자 지정」, 헤더 트리·수식은 그 역할로).
    asked = 미리 받은 T 호출의 답(ask_tables — 같은 stage1 · 같은 temp 로 물은 것: 헤딩 판정과 같이 돌린 것) — 주면 여기서는 묻지 않고 그 답을 붙인다(결과 `llm.ahead` = True)."""
    t0 = time.monotonic()
    skip, temp_list = temp_tables(temp)
    tables = collect(stage1, skip)
    drafts = {tb["id"]: draft(tb) for tb in tables}
    info = {"requested": bool(use_llm), "fallback": False, "error": None, "calls": 0, "failed": 0, "sent": 0, "skipped": 0, "applied": 0, "rejected": 0,
            "undecided": 0, "summary": ""}
    calls, guides, answers = [], {}, {}
    for tb in tables:
        tb["llm"] = {"sent": False, "changed": 0, "rejected": [], "error": None, "undecided": False}
    if use_llm and tables:
        got = asked if asked is not None else ask_tables(stage1, ask=ask, pinned=pinned, temp=temp, tables=tables, drafts=drafts)
        calls, answers = list(got["calls"]), got["answers"]
        guides.update(got["guides"])
        info["sent"] = got["sent"]
        info["skipped"] = len(tables) - info["sent"]
        info["summary"] = got["summary"]
        info["calls"] = len(calls)
        info["failed"] = sum(1 for c in calls if c["response"] is None)
        if got.get("placeGuides"):
            info["placeGuides"] = got["placeGuides"]   # 그 자리의 작성 지침을 실은 표 · 지침 수(§20)
        if asked is not None:
            info["ahead"] = True  # T 호출을 헤딩 판정과 같이 미리 돌린 실행(§8 「헤딩 판정과 같이」)
        if got["jobs"] and info["failed"] == got["jobs"]:
            info["fallback"] = True
            info["error"] = next((c["error"] for c in calls if c.get("error")), "T 호출 실패")
    out_tables, repeats = [], defaultdict(list)
    owner_fn = HC.owners_index(stage1, stage2)
    for tb in tables:
        bs, occ = drafts[tb["id"]]
        key = input_key(tb, occ, bs)  # 초안 그대로일 때의 자료 열쇠 — 아래에서 LLM 답 · 사람 지정을 얹기 전에(spec_테이블매니저 ② §2 「지금 판정」)
        ans = answers.get(tb["id"]) if use_llm else None
        if use_llm and sendable(tb):
            tb["llm"]["sent"] = True
            tb["llm"]["draftSubs"] = len(bs)  # 초안의 서브 테이블 수 — 「LLM 이 바꾼 것」 이 LLM 이 나눈·합친 것을 견준다(spec ② §7)
            if ans is None:
                tb["llm"]["undecided"] = True
                tb["llm"]["error"] = "T 호출 실패 — 초안 그대로"
                info["undecided"] += 1
            else:
                bs, changed, rejected = apply_answer(tb, occ, bs, ans)
                tb["llm"].update(changed=changed, rejected=rejected, summary=str(ans.get("summary") or "")[:300])
                info["applied"] += changed
                info["rejected"] += len(rejected)
        mine = (roles or {}).get(tb["id"]) or {}
        for x in tb["cells"]:
            if mine.get(x["id"]) in ("rowhead", "colhead", "field"):  # 사용자 헤더 지정 — 초안·LLM 답보다 앞
                x["auto"] = x["role"]  # 덮기 전 역할(자동 역할)을 남긴다 — 지정을 푼 뒤 이 결과를 다시 쓸 수 있게
                x["role"], x["reason"] = mine[x["id"]], "사용자 지정"
                x["changed"] = x["role"] != x["draft"]
            x.setdefault("changed", False)
            x["sub"] = next((b["id"] for b in bs if b["rows"][0] <= x["row"] < b["rows"][1] and b["cols"][0] <= x["col"] < b["cols"][1]), None)
        subs = [finish_band(tb, occ, b) for b in bs]
        before = _before_text(stage1, tb, skip)
        sem = HC.annotate(tb, subs, owner_fn, before=before)  # §9 구분 헤더·계산식·수식·소속
        notes = table_notes(stage1, tb)  # §10 작성요령(표 안 안내 칸 · 표 앞뒤 안내 문단)
        for s in subs:
            if s["signature"] and s["kind"] in ("matrix", "form"):
                repeats[s["signature"]].append({"table": tb["id"], "sub": s["id"]})
        counts = Counter(x["role"] for x in tb["cells"])
        out_tables.append({"id": tb["id"], "n": tb["n"], "host": tb["host"], "before": before[:60], "depth": tb["depth"],
                           "parentCell": tb["parentCell"], "rows": tb["rows"], "cols": tb["cols"],
                           "cells": [_out_cell(x) for x in tb["cells"]], "subtables": subs, "counts": dict(counts),
                           "issues": [i for s in subs for i in s["issues"]][:100], "llm": tb["llm"], "notes": notes, "inputKey": key, **sem})
    rep = [{"signature": k, "count": len(v), "where": v[:50]} for k, v in repeats.items() if len(v) >= 2]
    rep.sort(key=lambda r: -r["count"])
    roles = Counter(x["role"] for t in out_tables for x in t["cells"])
    cost = sum((c.get("costUsd") or 0) for c in calls)
    temp_brief = None if temp is None else {"version": temp.get("version"), "hintsVersion": temp.get("hintsVersion"), "counts": temp.get("counts") or {},
                                            "items": [it["id"] for it in temp.get("items") or ()], "off": list(temp.get("off") or ())}
    return {"version": VERSION, "tables": out_tables, "repeats": rep[:100],
            "tempTables": temp_list, "temp": temp_brief,  # §15 — TEMP 표(표 구조 없음)와 이 결과가 쓴 TEMP 요약(None = TEMP 없이 만든 결과)
            "counts": {"tables": len(out_tables), "cells": sum(len(t["cells"]) for t in out_tables), "subtables": sum(len(t["subtables"]) for t in out_tables),
                       "tempTables": len(temp_list),
                       "split": sum(1 for t in out_tables if len(t["subtables"]) > 1), "roles": dict(roles), "repeats": len(rep),
                       "changed": sum(1 for t in out_tables for x in t["cells"] if x.get("changed")),
                       "issues": sum(len(t["issues"]) for t in out_tables), "nested": sum(1 for t in out_tables if t["depth"] > 1),
                       **HC.counts(out_tables)},
            "llm": {**info, "costUsd": round(cost, 4), "seconds": round(time.monotonic() - t0, 2)}, "guides": guides, "_calls": calls}
