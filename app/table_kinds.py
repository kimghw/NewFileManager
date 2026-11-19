"""표(서브 테이블 = 띠)의 병합 방식 식별 — 순수 계산(spec_테이블매니저 ② §5 「병합 방식」).

여러 기관의 문서를 한 문서에 모을 때 그 띠를 어떻게 모으는 표인지를 **식별만** 한다 — 취합 · 이관의 넣기 동작은 바꾸지 않는다(읽는 쪽이 참고한다).
`app.server` · `heading_runs` · `zones` 를 import 하지 않는다: 3단계 결과의 표(dict — 고치지 않는다)와 편집 구역의 귀속을 읽는 함수(`zone_of`)를 **인자로** 받는다. 문서를 안 고치고 LLM 도 안 부른다.

방식 넷(화면 말 = `KIND_KO` — 사용자의 말 그대로):
- `perOrg`     기관마다 작성         — 그 띠가 통째로 한 기관의 것(기관마다 같은 표를 하나씩 쓴다)
- `byDivision` 구분 기준에 따라 병합 — 띠 안에서 구분 기준의 값마다 행 · 열이 갈린다(기관 행 · 기관 열 · 차년도 열 …)
- `sum`        셀 값 합산            — 기관이 갈리지 않은 표인데 숫자를 채운다(기관마다 낸 값을 같은 칸에 더한다)
- `common`     공통                  — 위 셋이 아닌 표

근거는 둘이고 `sure` 가 그것을 가른다:
- **편집 구역**(`zone_of` — 프로젝트 구성의 값으로 읽은 귀속: `zones_api.read` · `zones.label_of`) → `sure` True. 기관 · 차년도 자리를 여기서 다시 계산하지 않는다.
- **머리글의 꼴**(3단계 결과의 표 소속 `owner` · 표 안의 구분 칸 `labels` · 머리 칸의 `basis`·`basisKind`) → `sure` False(일반 의미 후보 — 「발행기관」 열 · 「TRL 1단계」 처럼 과제의 기관 · 단계가 아닌 것도 걸린다).
  편집 구역이 기관을 못 읽은 곳(「기관 모름」 · 「기관 확인 필요」)은 한 기관으로 치지 않는다 — 근거로 쓰지 않고 `sure` 만 내린다(`why` 에 칸 수를 적는다).

정하는 차례(띠마다 — 먼저 맞는 것):
 1. 기관(편집 구역): 띠의 칸이 서로 다른 기관 둘 이상 → `byDivision` · 띠의 모든 칸이 한 기관 → `perOrg`
 2. 기관(머리글의 꼴 — 한 기관의 표): 표 소속이 기관 구분 줄 아래 · 표 안의 기관 구분 칸 하나 · 「기관별 작성」 이라 적힌 표 → `perOrg`(구분 칸이 둘 이상이면 `byDivision`)
 3. 기관(띠 안에서 갈림): 편집 구역이 띠의 일부 칸에만 한 기관을 줌 · 머리 칸의 기관 행/열(`_org_axis`) → `byDivision`
 4. 기관(머리글의 꼴 — 한 기관의 양식): 표의 기관 머리가 기관 이름 칸(「연구개발기관명 | 값」)뿐이다(`_one_org_form`) → `perOrg`
 5. 계산식 표(`calc.is`)이고 합계 · 비율 · 코드 식이 있으며(`_fill` — 숫자 필드가 여럿일 뿐인 띠는 아니다) 숫자를 채우는 필드가 있다 → `sum`
 6. 차년도 · 단계 · 연도(기관은 없음 — `VALUE_DIMS`): 편집 구역이 띠의 칸에 서로 다른 차년도(단계) 둘 이상을 줌 · 값 머리(「1차년도」 · 「2차년도」 — 연도 값 머리 「2024」 · 「2025」 도)가 둘 이상 → `byDivision`
 7. `common`
사양(② §5)의 차례 1~5 를 실물(저장된 3단계 결과 · 견본 양식에 값을 반영한 문서 — 프로브 artifacts/table_manager_astra_2026-11-19/probe_kinds.py)에 재 보고 다듬은 것이다 — 달라진 곳:
편집 구역의 근거를 머리글의 꼴보다 먼저 본다 · 기관 이름 머리(「기관명」)를 열의 이름(→ 기관 행)과 양식의 이름 칸(→ 한 기관의 양식)으로 가른다 · 값 머리 하나는 행/열로 치지 않는다 ·
차년도 · 단계 · 연도는 값 머리만 본다 · 숫자 필드만으로는 합산이라 하지 않는다 · 「기관별 작성」 이라 적힌 글도 근거로 쓴다.

표의 방식(`_table_kind`) = 띠가 모두 같으면 그 방식 · **공통인 띠는 빼고 본다**(`QUIET`): 공통 말고 방식이 하나면 그 방식 · 둘 이상이면 `mixed` · 모두 공통이면 공통. `subs` 에는 공통 띠도 그대로 남는다.

사람이 더 고칠 두 곳은 상수 하나씩이다(2026-11-19 사용자 답 「일단 하고 추가로 수정할게」): 연도 열을 구분 기준으로 치나 = `VALUE_DIMS` 의 "period" · 표 수준에서 빼고 보는 방식 = `QUIET`.
"""
import re

KINDS = ("perOrg", "byDivision", "sum", "common")
KIND_KO = {"perOrg": "기관마다 작성", "byDivision": "구분 기준에 따라 병합", "sum": "셀 값 합산", "common": "공통"}   # 화면 말(사용자의 말 그대로 — 화면은 tables.js TP_KIND)
QUIET = ("common",)                         # 표의 방식을 정할 때 빼고 보는 띠의 방식(숫자 띠 + 꼬리 양식 띠 = 셀 값 합산) — 화면은 tables.js TP_KIND_QUIET
DIMS = ("org", "stage", "year", "period")   # basis · axes 에 싣는 기준(이 차례로). period = 연도(「2024」 · 「2025」 — 3단계의 basis)
ZONE_DIMS = ("org", "stage", "year")        # 편집 구역이 주는 기준 — 연도는 주지 않는다(연도의 근거는 머리글의 꼴뿐)
VALUE_DIMS = ("stage", "year", "period")    # 차례 6 — 값 머리가 둘 이상이면 행/열로 치는 기준. "period" 를 빼면 연도 열을 구분 기준으로 치지 않는다
DIM_KO = {"org": "기관", "stage": "단계", "year": "차년도", "period": "연도"}
ON_KO = {"row": "행", "col": "열"}
DATA_BANDS = ("matrix", "form", "plain", "list")   # 방식을 정하는 띠 — 제목 · 안내 · 간격 띠(title · note · spacer)는 값을 모으는 자리가 아니다
HEADS = ("colhead", "rowhead", "corner")
UNREAD = {"unknown": "기관 모름", "conflict": "기관 확인 필요"}   # 편집 구역이 기관을 못 읽은 곳(zones.ORG_TEXT 와 같은 말)
PER_ORG_TEXT = re.compile(r"기관\s*별\s*(?:로\s*)?작성|기관\s*마다\s*작성")   # 양식이 스스로 적은 말(「[해당 기관별 작성] …」)
TEXT_MAX = 24
_WS = re.compile(r"\s+")
_NO = r"(\d{1,3}|[nN]|[①-⑳]|[Ⅰ-Ⅻⅰ-ⅻ])"
_STAGE_NO = re.compile(_NO + r"\s*단계")
_YEAR_NO = re.compile(_NO + r"\s*(?:차\s*년\s*도|년\s*차|연\s*차|차년|차$)")
_PERIOD_NO = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _short(text, n=TEXT_MAX):
    t = _WS.sub(" ", str(text or "")).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def _uniq(xs):
    return list(dict.fromkeys(x for x in xs if x))


def _list(texts, n=3):
    return " · ".join(texts[:n]) + (" …" if len(texts) > n else "")


# ---- 편집 구역(zone_of) ------------------------------------------------------------------------------------------------

def _zone(zone_of, i):
    """zone_of(i) 의 답 → None(편집 구역이 모르는 id) | {"org": 읽힌 기관 | None, "name": 보일 이름, "unread": unknown|conflict|None, "year", "stage"}.
    `orgKind` 가 unknown · conflict 면 `org` 가 무엇이든 못 읽은 곳이다(한 기관으로 치지 않는다)."""
    if zone_of is None or i is None:
        return None
    z = zone_of(i)
    if not isinstance(z, dict):
        return None
    unread = z.get("orgKind") if z.get("orgKind") in UNREAD else None
    org = None if unread else (z.get("org") or None)
    return {"org": org, "name": str(z.get("orgName") or org or ""), "unread": unread, "year": z.get("year"), "stage": z.get("stage")}


def _on(cells, state):
    """칸마다의 값이 행을 따라 갈리나 열을 따라 갈리나 → "row"(행마다 값 하나 — 기관 행) | "col"(열마다 값 하나 — 기관 열). 가를 수 없으면 "row".
    state = {칸 id: 값} — 값이 없는 **필드 칸**도 한 상태로 센다(기관 열이 하나만 읽힌 표: 그 행에는 값 있는 칸과 없는 칸이 섞이고, 그 열은 값 하나뿐이다)."""
    rows, cols = {}, {}
    for x in cells:
        v = state.get(x.get("id"))
        if v is None and x.get("role") != "field":
            continue
        for r in range(x.get("row") or 0, (x.get("row") or 0) + (x.get("rs") or 1)):
            rows.setdefault(r, set()).add(v)
        for c in range(x.get("col") or 0, (x.get("col") or 0) + (x.get("cs") or 1)):
            cols.setdefault(c, set()).add(v)
    return "row" if sum(len(s) > 1 for s in rows.values()) <= sum(len(s) > 1 for s in cols.values()) else "col"


def _zone_band(cells, whole, zone_of):
    """띠의 칸마다 편집 구역의 귀속을 모은다(제 값이 없는 칸 · 편집 구역이 모르는 칸은 표의 것 `whole`) →
    {"orgs": [(기관, 보일 이름)…](나온 차례), "none": 기관이 없는 칸 수, "unread": {unknown: n, conflict: n}, "years": [...], "stages": [...], "on": {기준: row|col}}."""
    orgs, unread, none = {}, {}, 0
    val = {d: {} for d in ZONE_DIMS}
    for x in sorted(cells, key=lambda c: (c.get("row") or 0, c.get("col") or 0)):
        z = _zone(zone_of, x.get("id")) or whole
        if z is None:
            none += 1
            continue
        if z["unread"]:
            unread[z["unread"]] = unread.get(z["unread"], 0) + 1
            val["org"][x.get("id")] = ("?", z["unread"])   # 기관 자리인데 못 읽은 칸 — 행·열을 가를 때만 한 상태로 센다(기관 수에는 안 든다)
        elif z["org"] is not None:
            orgs.setdefault(z["org"], z["name"])
            val["org"][x.get("id")] = z["org"]
        else:
            none += 1
        for d in ("stage", "year"):
            if z[d] is not None:
                val[d][x.get("id")] = z[d]
    return {"orgs": list(orgs.items()), "none": none, "unread": unread, "years": sorted(set(val["year"].values()), key=str), "stages": sorted(set(val["stage"].values()), key=str),
            "on": {d: _on(cells, val[d]) for d in ZONE_DIMS}}


# ---- 머리글의 꼴(3단계 결과) --------------------------------------------------------------------------------------------

def _org_head(x):
    return isinstance(x, dict) and x.get("role") in HEADS and x.get("basisKind") in ("name", "value") and "org" in (x.get("basis") or ())


def _one_org_form(table):
    """표의 기관 머리가 **기관 이름 칸**(양식 띠의 행헤더 「연구개발기관명」·「직장 › 기관명」 — 값은 그 오른쪽 한 칸)뿐인가 → 그 머리 글 | None.
    한 기관의 이름을 한 번 적는 양식(활용계획서 · 인적사항)이다 — 그 칸이 든 띠만이 아니라 표 전체가 그 기관의 것이라 표 수준의 근거로 쓴다.
    기관 값 머리(「주관연구개발기관」) · 열의 이름 머리(「기관명」 열) · 되풀이되는 이름 칸이 하나라도 있으면 아니다(그런 표는 표 안에서 기관이 갈린다)."""
    forms = {b.get("id") for b in table.get("subtables") or () if isinstance(b, dict) and b.get("kind") == "form"}
    slots = []
    for x in table.get("cells") or ():
        if not _org_head(x):
            continue
        if x.get("basisKind") != "name" or x.get("role") != "rowhead" or x.get("sub") not in forms:
            return None
        slots.append(_short(x.get("text")) or "(빈 머리)")
    return slots[0] if slots and len(set(slots)) == len(slots) else None


def _table_shape(table):
    """표 전체에 걸리는 「한 기관의 표」 근거(머리글의 꼴) → {"division": 기관 구분 줄 글 | None, "labels": [표 안의 기관 구분 칸 글…], "per": 「기관별 작성」 이 적힌 글 | None, "form": 기관 이름 칸의 머리 글 | None}."""
    owner = table.get("owner") if isinstance(table.get("owner"), dict) else {}
    div = owner.get("division") if isinstance(owner.get("division"), dict) else {}
    labels = [x for x in table.get("labels") or () if isinstance(x, dict)]
    said = [table.get("before"), owner.get("text"), *(owner.get("path") or ()), *(x.get("text") for x in labels)]
    return {"division": (_short(div.get("text"), 30) or "기관 구분") if "org" in (div.get("basis") or ()) else None,
            "labels": _uniq(_short(x.get("text"), 30) for x in labels if "org" in (x.get("basis") or ())),
            "per": next((_short(t, 30) for t in said if isinstance(t, str) and PER_ORG_TEXT.search(t)), None),
            "form": _one_org_form(table)}


def _value_key(d, text):
    """값 머리의 값(같은 값을 한 번만 세려고) — 「1단계-1차년도」·「1단계-2차년도」 는 단계 하나 · 차년도 둘이다. 연도는 적힌 해(「2024년」 = 「2024」 · 「2026~2029」 는 두 해 묶음).
    번호를 못 읽으면 글 그대로(빈 양식의 「20xx | 20xx」 는 같은 글이라 값 하나다)."""
    t = _WS.sub("", str(text or ""))
    s, y = _STAGE_NO.search(t), _YEAR_NO.search(t)
    if d == "stage" and s:
        return s.group(1)
    if d == "year" and y:
        return (s.group(1) if s else "", y.group(1))
    if d == "period" and (p := tuple(_PERIOD_NO.findall(t))):
        return p
    return t


def _heads(cells):
    """띠의 머리 칸(열헤더 · 행헤더 · 귀퉁이)이 말하는 구분 기준 → {기준: {"col": [값 머리 글…](열마다 값), "row": [값 머리 글…](행마다 값), "down": [이름 머리 글…](열의 이름 — 값은 그 아래 행마다),
    "slot": [이름 머리 글…](행의 이름 — 값은 그 오른쪽 칸), "again": 같은 이름 칸이 되풀이되나}}. 값 머리 = 「1차년도」·「주관연구개발기관」(basisKind value — 같은 값은 한 번), 이름 머리 = 「기관명」·「연차」(basisKind name)."""
    out = {d: {"col": {}, "row": {}, "down": [], "slot": []} for d in DIMS}
    for x in sorted(cells, key=lambda c: (c.get("row") or 0, c.get("col") or 0)):
        role, kind = x.get("role"), x.get("basisKind")
        if role not in HEADS or kind not in ("name", "value"):
            continue
        t = _short(x.get("text")) or "(빈 머리)"
        for d in x.get("basis") or ():
            if d not in out:
                continue
            if kind == "value":
                out[d]["row" if role == "rowhead" else "col"].setdefault(_value_key(d, x.get("text")), t)
            else:
                out[d]["slot" if role == "rowhead" else "down"].append(t)
    return {d: {"col": list(h["col"].values()), "row": list(h["row"].values()), "down": _uniq(h["down"]), "slot": _uniq(h["slot"]), "again": len(set(h["slot"])) < len(h["slot"])}
            for d, h in out.items()}


def _org_axis(h, form):
    """머리 칸이 말하는 기관 행/열 → {"on", "values": 값 머리 수(이름 머리뿐이면 0), "texts": [머리 글…], "named": 이름 머리가 근거인가} | None.
    값 머리 하나뿐인 띠(양식의 「주관연구개발기관 | 값」 — 주관이 누구인지 적는 칸)와 양식 띠의 되풀이되지 않는 이름 칸(한 기관의 이름 · 유형 — `_one_org_form`)은 기관 행/열이 아니다."""
    nr, nc = len(h["row"]), len(h["col"])
    if max(nr, nc) >= 2:
        side = "row" if nr >= nc else "col"
        return {"on": side, "values": len(h[side]), "texts": h[side], "named": False}
    if h["down"]:                    # 「기관명」 열 — 값은 그 아래 행마다
        return {"on": "row", "values": 0, "texts": h["down"], "named": True}
    if h["slot"] and not form:       # 격자 띠의 「기관명」 행 — 값은 열마다
        return {"on": "col", "values": 0, "texts": h["slot"], "named": True}
    if h["slot"] and h["again"]:     # 양식 띠에 같은 이름 칸이 되풀이 — 기관마다 한 묶음
        return {"on": "row", "values": 0, "texts": h["slot"], "named": True}
    return None


def _value_axis(h):
    """머리 칸이 말하는 차년도 · 단계 · 연도 행/열(`VALUE_DIMS`) — **값 머리**(「1차년도」 · 「2단계」 · 「2024」)가 둘 이상일 때만. 값 하나는 갈린 것이 아니고(그 표의 차년도를 적은 머리),
    이름 머리(「발표연도」 · 「구축연도」)는 과제의 차년도가 아닌 것이 많다."""
    nr, nc = len(h["row"]), len(h["col"])
    if max(nr, nc) < 2:
        return None
    side = "row" if nr > nc else "col"
    return {"on": side, "values": len(h[side]), "texts": h[side], "named": False}


def _axis_text(basis, ax, paren=False):
    """「기관 행 3 — 가 · 나 · 다」 · 「기관 행 — 머리글 「기관명」」 · paren: 「차년도 열 2(1차년도 · 2차년도)」(여러 기준을 한 줄에 이을 때)."""
    head = f"{DIM_KO[basis]} {ON_KO[ax['on']]}" + (f" {ax['values']}" if ax["values"] else "")
    if not ax["texts"]:
        return head
    if ax.get("named"):
        return f"{head} — 머리글 「{_list(ax['texts'], 2)}」"
    return f"{head}({_list(ax['texts'])})" if paren else f"{head} — {_list(ax['texts'])}"


def _fill(cells):
    """(숫자를 채우는 필드 수, 그 가운데 지금 수가 든 칸 수, 합계 · 비율 · 코드 식이 있나) — 채우는 칸 = 수 · 숫자 자리표시 · 수식 칸 · 빈 칸(글이 든 필드는 숫자 칸이 아니다).
    셋째 = 머리 칸에 합계(「계」·「소계」)·비율·코드 식(「(E1=A+B)」)이 있거나 수식이 붙은 필드가 있다 — 숫자 필드가 여럿일 뿐인 띠(표지 양식의 과제번호 · 성능 목표치)는 더하는 표가 아니다."""
    n = filled = 0
    total = False
    for x in cells:
        if x.get("role") in HEADS and ("total" in (x.get("basis") or ()) or x.get("basisKind") == "ratio" or x.get("expr")):
            total = True
        if x.get("role") != "field":
            continue
        total = total or bool(x.get("formulas"))
        if x.get("num") is not None and not x.get("dash"):
            n, filled = n + 1, filled + 1
        elif x.get("num") is not None or x.get("placeholder") or x.get("formulas") or not _WS.sub("", str(x.get("text") or "")):
            n += 1
    return n, filled, total


def _repeat_index(repeats):
    """3단계 결과의 `repeats`([{signature, count, …}]) 또는 {서명: 수} → {서명: 수}."""
    if isinstance(repeats, dict):
        return {k: v for k, v in repeats.items() if isinstance(v, int)}
    return {r["signature"]: r["count"] for r in repeats or () if isinstance(r, dict) and isinstance(r.get("signature"), str) and r["signature"] and isinstance(r.get("count"), int)}


# ---- 띠 하나 · 표 하나 ----------------------------------------------------------------------------------------------------

def _band(band, cells, shape, whole, seen, zone_of, rep):
    z = _zone_band(cells, whole, zone_of) if zone_of is not None else None
    h = _heads(cells)
    calc = band.get("calc") if isinstance(band.get("calc"), dict) else {}
    axes, kind, by, sure, why, orgs = {}, None, None, False, "", 0

    # 차년도 · 단계 · 연도의 행/열(VALUE_DIMS — 어느 방식이든 적어 둔다): 편집 구역이 띠의 칸에 서로 다른 값 둘 이상을 줌(연도는 주지 않는다) → 없으면 값 머리 둘 이상
    zone_axis = False
    zone_got = {"stage": z["stages"], "year": z["years"]} if z else {}
    for d in VALUE_DIMS:
        got = zone_got.get(d, ())
        if len(got) >= 2:
            on = z["on"][d]
            axes[d], zone_axis = {"on": on, "values": len(got), "texts": h[d][on] if len(h[d][on]) == len(got) else [], "named": False}, True   # 머리 글은 수가 맞을 때만 곁들인다
        elif (ax := _value_axis(h[d])) is not None:
            axes[d] = ax

    names = [n or str(k) for k, n in z["orgs"]] if z else []
    org_ax = _org_axis(h["org"], band.get("kind") == "form")
    if z and len(names) >= 2:                                   # 1 — 편집 구역: 띠 안에서 기관이 갈린다
        axes["org"] = {"on": z["on"]["org"], "values": len(names), "texts": names, "named": False}
        kind, by, sure, orgs, why = "byDivision", "zone", True, len(names), _axis_text("org", axes["org"])
    elif z and len(names) == 1 and not z["none"]:               # 1 — 편집 구역: 띠의 모든 칸이 한 기관(못 읽은 칸이 섞였으면 확실하지 않다)
        kind, by, sure, orgs, why = "perOrg", "zone", not z["unread"], 1, f"한 기관의 구역 — {names[0]}"
    elif shape["division"]:                                     # 2 — 표 소속이 기관 구분 줄 아래
        kind, by, why = "perOrg", "owner", f"기관 구분 아래의 표 — {shape['division']}"
    elif len(shape["labels"]) == 1:                             # 2 — 표 안의 기관 구분 칸 하나
        kind, by, why = "perOrg", "labels", f"표 안의 기관 구분 칸 — {shape['labels'][0]}"
    elif len(shape["labels"]) >= 2:                             # 2 — 구분 칸이 여럿이면 표 안에서 기관이 갈린다
        axes["org"] = {"on": "row", "values": len(shape["labels"]), "texts": shape["labels"], "named": False}
        kind, by, orgs, why = "byDivision", "labels", len(shape["labels"]), "표 안의 기관 구분 칸 — " + _axis_text("org", axes["org"], paren=True)
    elif shape["per"]:                                          # 2 — 양식이 「기관별 작성」 이라 적은 표
        kind, by, why = "perOrg", "text", f"「기관별 작성」 이라 적힌 표 — {shape['per']}"
    elif z and len(names) == 1:                                 # 3 — 편집 구역: 띠의 일부 칸만 한 기관(기관 행 · 열이 하나만 읽힘)
        axes["org"] = {"on": z["on"]["org"], "values": 1, "texts": names, "named": False}
        kind, by, orgs, why = "byDivision", "zone", 1, _axis_text("org", axes["org"]) + "(한 기관만 읽힘)"
    elif org_ax is not None:                                    # 3 — 머리 칸의 기관 행/열
        axes["org"] = org_ax
        kind, by, orgs, why = "byDivision", "heads", org_ax["values"], _axis_text("org", org_ax)
    elif shape["form"]:                                         # 4 — 기관 이름 칸뿐인 표(한 기관의 양식)
        kind, by, why = "perOrg", "form", f"기관 이름 칸뿐인 표 — 머리글 「{shape['form']}」"
    else:
        other, said = [], None
        for d in VALUE_DIMS:
            if d in axes:   # 같은 머리가 두 기준을 말하면(「1단계-1차년도」 · 「1차년도(2026년)」) 글은 한 번만
                other.append(_axis_text(d, axes[d] if axes[d]["texts"] != said else {**axes[d], "texts": []}, paren=True))
                said = axes[d]["texts"]
        n, filled, total = _fill(cells)
        looked = bool(z) and seen and not z["unread"]   # 편집 구역이 이 표의 칸을 보았고 못 읽은 칸이 없다 — 「기관이 갈리지 않음」 이 프로젝트 구성으로 뒷받침된다
        if calc.get("is") and total and n:                      # 5 — 계산식 표(합계 · 비율 · 코드 식) + 숫자를 채우는 필드
            said = str(calc.get("why") or "합계가 있는 표")       # heading_calc.band_calc 의 글(「합계 헤더 · 숫자 필드 22」)
            head = said if "숫자 필드" in said else f"{said} · " + (f"숫자 필드 {filled}" if filled else f"채울 칸 {n}")
            kind, by, sure, why = "sum", "calc", looked, " · ".join([head, "기관 행·열 없음", *other])
        elif other:                                             # 6 — 차년도 · 단계 · 연도의 행/열만
            kind, by, sure, why = "byDivision", "zone" if zone_axis else "heads", zone_axis, " · ".join([*other, "기관 행·열 없음"])
        else:                                                   # 7
            kind, by, sure, why = "common", "none", looked, " · ".join(DIM_KO[d] for d in ("org", *VALUE_DIMS)) + "로 갈리지 않음"
    again = rep.get(band.get("signature"), 0) if isinstance(band.get("signature"), str) else 0
    if kind == "perOrg" and again >= 2:
        why += f" · 같은 꼴의 표 {again}곳"
    if z and z["unread"]:
        why += " · " + " · ".join(f"{UNREAD[k]} {n}칸" for k, n in z["unread"].items())
    basis = [d for d in DIMS if d in axes or (d == "org" and kind == "perOrg")]
    return {"sub": band.get("id"), "kind": kind, "basis": basis, "axes": [{"basis": d, "on": axes[d]["on"], "values": axes[d]["values"]} for d in DIMS if d in axes],
            "orgs": orgs, "why": why, "sure": bool(sure), "by": by}


def kinds(table, zone_of=None, repeats=None):
    """표 하나의 병합 방식(spec_테이블매니저 ② §5 「병합 방식」) → {"table": 표 id, "kind": 방식 | "mixed", "subs": [{"sub": 띠 id, "kind": 방식, "basis": [org|stage|year|period…],
    "axes": [{"basis", "on": "row"|"col", "values": n}], "orgs": n, "why": 화면에 보일 한 줄, "sure": bool, "by": 정한 근거}]}.

    - `table` = 3단계 결과 꼴의 표(`heading_tables.build` — 칸 `role`·`sub`·`basis`·`basisKind`·`num`, 띠 `kind`·`calc`·`signature`, 표 `owner`·`labels`·`before`·`parentCell`). 고치지 않는다.
    - `zone_of(블록 · 칸 id)` → `{"org": 값 | None, "year", "stage"(, "orgKind": org|unknown|conflict|None, "orgName": 보일 이름)}` | None(편집 구역이 모르는 id — 칸 안의 표 · 그 칸).
      편집 구역이 읽은 귀속이다(`zones_api.read` · `zones.label_of`) — 없으면(None) 머리글의 꼴만으로 정하고 `sure` 는 모두 False.
    - `repeats` = 3단계 결과의 `repeats`(같은 꼴의 띠가 문서에 몇 곳인가 — `perOrg` 의 `why` 에 「같은 꼴의 표 n곳」 을 붙인다. 방식은 바꾸지 않는다).
    - `subs` = 값을 모으는 띠(matrix · form · plain · list)마다 하나 — 제목 · 안내 · 간격 띠는 뺀다(그런 띠뿐인 표는 모든 띠).
    - 표의 방식(`_table_kind`) = 띠가 모두 같으면 그 방식 · 공통인 띠는 빼고 본다: 공통 말고 방식이 하나면 그 방식 · 둘 이상이면 "mixed" · 모두 공통이면 공통(`subs` 에는 공통 띠도 그대로).
    - `by` = 그 방식을 정한 근거: zone(편집 구역) · owner(표 소속의 기관 구분 줄) · labels(표 안의 기관 구분 칸) · text(「기관별 작성」 이라 적힌 글) · heads(머리 칸의 행/열) ·
      form(기관 이름 칸뿐인 양식) · calc(계산식 표) · none(근거 없음 — 공통).
    - `sure` = 편집 구역이 뒷받침할 때만 True: 띠의 칸에 서로 다른 기관(차년도 · 단계) 둘 이상 · 못 읽은 칸 없이 모든 칸이 한 기관 · calc · none 인데 편집 구역이 그 표의 칸을 보았고 못 읽은 칸이 없다.
      zone 이어도 False 인 때 = 일부 칸에만 한 기관이 읽힘 · 한 기관의 띠에 못 읽은 칸이 섞임.
    - `axes` 의 `values` = 그 행/열의 값 수(이름 머리 「기관명」 열만 보고 정했으면 0 — 몇 기관인지는 모른다) · `orgs` = 읽힌 기관 수(못 읽은 곳은 세지 않는다)."""
    cells = [x for x in table.get("cells") or () if isinstance(x, dict)]
    bands = [b for b in table.get("subtables") or () if isinstance(b, dict)]
    data = [b for b in bands if b.get("kind") in DATA_BANDS] or bands
    own = _zone(zone_of, table.get("id"))                       # 편집 구역이 이 표(본문 최상위 표)를 아는가 — 칸 안의 표는 모른다(바깥 칸의 귀속을 물려받는다)
    whole = own if own is not None else _zone(zone_of, table.get("parentCell"))
    shape, rep = _table_shape(table), _repeat_index(repeats)
    subs = [_band(b, [x for x in cells if x.get("sub") == b.get("id")], shape, whole, own is not None, zone_of, rep) for b in data]
    return {"table": table.get("id"), "kind": _table_kind(subs), "subs": subs}


def _table_kind(subs):
    """띠마다의 방식 → 표의 방식. 띠가 모두 같으면 그 방식 · `QUIET`(공통)인 띠는 빼고 본다: 그 밖의 방식이 하나면 그 방식(숫자 띠 + 꼬리 양식 띠 = 셀 값 합산) · 둘 이상이면 "mixed" ·
    하나도 없으면(모두 공통 · 띠가 없음) 공통. 2026-11-19 사용자 답 「일단 하고 추가로 수정할게」 — 빼고 볼 방식은 `QUIET` 한 곳이다."""
    got = list(dict.fromkeys(s["kind"] for s in subs))
    if len(got) <= 1:
        return got[0] if got else "common"
    loud = [k for k in got if k not in QUIET]
    return loud[0] if len(loud) == 1 else "mixed"


def counts(results):
    """표마다의 결과 → {perOrg, byDivision, sum, common, mixed}(표 수 — 합 = 표 수)."""
    out = {k: 0 for k in (*KINDS, "mixed")}
    for r in results:
        out[r["kind"]] = out.get(r["kind"], 0) + 1
    return out
