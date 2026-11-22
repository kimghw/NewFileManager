"""구분 기준 자리 표시의 「표 구조」 보탬(spec_구분_기준 ② §25) — 순수 계산: 서버 · 세션 · 3단계 실행 상태를 모른다(부르는 쪽이 표마다 테이블 매니저의 「지금 판정」 을 준다).

2026-11-23 사용자(표 「(2) 정량적 목표 항목의 평가방법 및 평가환경」 — 1~4차년도가 다 있는 항목만 띠가 있고 3·4차년도 · 4차년도 하나인 항목은 없음 · 일정 표의 「1단계」 · 월별 표 「3차년도(12개월)」 도 없음)
"스크립트라서 이해는 하지만 LLM 검증 보완에서 왜 누락되었는지 검토하고 …" · "하나의 헤딩안에 있는 테이블들은 같이 두고 검토해야지 … 개별테이블도 하고, 하나의 헤딩 아래 있는 같은 테이블도 하고" → astra 검토(artifacts/table_division_astra_2026-11-23).

까닭: 엔진 묶음(`core.find`)은 값이 1부터 2개 이상 이어질 때만 서고(그래서 「3·4차년도」 항목은 묶음이 아니다 — 늘리고 줄이는 반영의 입력이라 넓히지 않는다), 판독(`division_scan`)의 표 안 읽기는 「차년도」 같은 이름표 칸 아래만 본다.
반면 헤딩 추출 3단계(「LLM 검증·보완」 의 표 구조 — 칸 역할은 LLM 이 고치고 `heading_calc.annotate` 가 구분 헤더를 적는다)는 그 칸들을 이미 **구분 값 머리**(basisKind value)로 봤다. 그 판정을 표시에 잇는다.

- **식별만**(판독만 — 가는 띠): 반영 대상이 아니고 행 · 열 · 표 수를 바꾸지 않는다. 판독(scan)과 그 고정본은 그대로(§23 한 방향 — 이 보탬은 members 응답을 지을 때만 합친다).
- 값 머리 = 머리 역할(rowhead · colhead)이고 3단계가 구분 값으로 본 칸(basis stage · year · org — 둘이 겹치면 단계-차년도). 자리표시(「N차년도」 · 「○단계」)는 뺀다 · 기관은 칸 글이 과제 기관 이름과 통째로 같을 때만.
  같은 구분의 엔진 묶음 라벨인 칸은 뺀다(같은 띠를 두 번 그리지 않는다 — 다른 구분은 그대로: 일정 표의 차년도 엔진 띠 + 「1단계」 단계 띠).
- 자리 안(scope) = 같은 띠(서브 테이블)에서 그 머리의 **행 범위(행 머리) · 열 범위(열 머리) 안에 온전히 든** 필드 칸 — 두 값의 행에 걸친 칸(3·4차년도 공통 「평가환경」 칸)은 어느 한 값의 자리로 칠하지 않는다(astra P1).
- **같은 헤딩 아래 표 묶음**(`series`): 같은 소속 헤딩(3단계 owner — 실제 헤딩 id 가 있는 것만)의 본문 표가 문서 차례로 잇달아(사이에 헤딩 줄 없음) 같은 타입(`table_kv.type_key`)이고
  표마다 같은 자리 · 같은 역할의 값 머리가 **하나**씩, 값이 서로 다르고 차례대로 커지면(1 → 4 · 1부터가 아니어도) — 그 표들을 「값마다 표 하나」 자리로 보고 표 전체를 그 값의 자리로 칠한다.
  캡션 글(숫자 뺀 것)이 서로 다르면 묶지 않는다(용도가 다른 같은 꼴 표 — astra 반례)."""
import re

from app import table_kv
from app.division_profiles.rnd import core

DIM_NAME = core.DIM_NAME
HEAD_ROLES = ("rowhead", "colhead")
_PLACE = re.compile(r"[NＮ○◯□xXＸ]\s*(?:단계|차\s*년도|년차|연차)")
_DIGITS = re.compile(r"[\s\d.,·:\-–()\[\]<>「」『』]+")


def _dim_of(basis):
    b = set(basis or ())
    if {"stage", "year"} <= b:
        return core.STAGE_YEAR
    if "year" in b:
        return core.YEAR
    if "stage" in b:
        return core.STAGE
    if "org" in b:
        return core.ORG
    return None


_PAREN = re.compile(r"\([^()]*\)")
_SLOT = re.compile(r"\{[^}]*\}")
_REST = re.compile(r"[\s\d.,·:\-–~년()\[\]<>]")
TIME_DIMS = (core.STAGE, core.YEAR, core.STAGE_YEAR)


def _read(text):
    """머리 글 → (구분, 견줄 값) | None — 칸 글이 **그 자체로** 구분 값 꼴일 때만(「3차년도」 · 「3차년도(12개월)」 · 「1단계 (기반 구축)」 · 「2026 (1차년도)」 · 「1단계 1차년도」).
    값 낱말 · 괄호 안 · 연도 · 숫자 · 문장 부호를 뗀 나머지가 있으면 아니다(「매출액발생 1년차」 · 「당해연도 개발기간(1단계, 1차년도)」 — 다른 뜻의 글). 자리표시(N) · 숫자만(「1」) · 「건」 은 아니다.
    3단계의 구분 헤더(`heading_calc.annotate`)가 값 머리로 본 칸만 여기 온다 — 그래도 그 판정은 열 경로로 번진 것이 있어(「건」 · 「척」) 글로 다시 본다. 견줄 값은 표 묶음의 차례 검사에만 쓴다(화면에는 칸 글)."""
    h = core.hint_info(text)
    if not h or h["dim"] not in TIME_DIMS:
        return None
    v = h["value"]
    if v == core.N or (isinstance(v, tuple) and core.N in v):
        return None
    if _REST.sub("", _SLOT.sub("", _PAREN.sub("", h.get("shape") or ""))):
        return None
    return h["dim"], v


def heads(tb, keys=(), names=None):
    """판정된 표 하나(테이블 매니저 `judge()["table"]`) → 값 머리 [{cell, dim, value(보일 글), num, org?, role, sub, rows(r0, r1), cols(c0, c1), paras}] — 표의 칸 차례."""
    out = []
    for x in sorted(tb.get("cells") or (), key=lambda c: (c["row"], c["col"])):
        if x.get("role") not in HEAD_ROLES or x.get("basisKind") != "value" or x.get("nested"):
            continue
        dim = _dim_of(x.get("basis"))
        text = core.NOTE.sub("", str(x.get("textFull") or x.get("text") or "")).strip()
        if dim is None or not text or _PLACE.search(text):
            continue
        h = {"cell": x["id"], "dim": dim, "value": re.sub(r"\s+", " ", text)[:40], "role": x["role"], "sub": x.get("sub"),
             "rows": (x["row"], x["row"] + (x.get("rs") or 1)), "cols": (x["col"], x["col"] + (x.get("cs") or 1)), "paras": list(x.get("paras") or ())}
        if dim == core.ORG:
            from app import zones
            k = zones._cell_org(text, list(keys or ()))
            if not k:
                continue   # 과제 기관 이름과 통째로 같은 칸만 — 역할 낱말 · 예시 글은 기관 자리로 올리지 않는다(astra P1)
            h.update(org=k, value=(names or {}).get(k) or text, num=k)
        else:
            got = _read(text)
            if got is None:
                continue
            h["dim"], h["num"] = got   # 글이 말한 구분이 먼저(「1단계 1차년도」 = 단계-차년도)
        out.append(h)
    return out


def _fits(h, stages):
    st = list(stages or ())
    if not st or h["dim"] == core.ORG:
        return True
    v = h["num"]
    if h["dim"] == core.STAGE:
        return 1 <= v <= len(st)
    if h["dim"] == core.STAGE_YEAR:
        s, y = v
        return 1 <= s <= len(st) and 1 <= y <= st[s - 1]
    return 1 <= v <= sum(st)


def fit(hs, stages):
    """값 머리 가운데 프로젝트 구성(단계마다 차년도 수 — 모르면 그대로)의 범위 밖 값이 있는 구분은 그 표에서 통째로 뺀다 —
    「1단계 · 2단계 · 3단계」 로드맵 표가 1단계뿐인 과제에 있으면 그 단계는 과제의 단계가 아니다(한 칸만 남겨 칠하지 않는다)."""
    bad = {h["dim"] for h in hs if not _fits(h, stages)}
    return [h for h in hs if h["dim"] not in bad]


def _inside(h, c):
    """필드 칸 c 가 값 머리 h 의 자리 안인가 — 같은 띠 · 머리의 행(행 머리) · 열(열 머리) 범위 안에 온전히 들고 머리의 오른쪽 · 아래에 있다."""
    if c.get("role") != "field" or c.get("sub") != h["sub"]:
        return False
    r0, r1 = c["row"], c["row"] + (c.get("rs") or 1)
    c0, c1 = c["col"], c["col"] + (c.get("cs") or 1)
    if h["role"] == "rowhead":
        return h["rows"][0] <= r0 and r1 <= h["rows"][1] and c0 >= h["cols"][1]
    return h["cols"][0] <= c0 and c1 <= h["cols"][1] and r0 >= h["rows"][1]


def table_reads(tid, tb, hs, engine_labels=None):
    """표 하나의 보탬 → [{kind: label|scope, dim, dimName, value, src: "struct", inGroup: False, table, paras, text}].
    engine_labels = {구분: 엔진 묶음의 라벨 문단 id 모음} — 같은 구분의 엔진 라벨인 머리는 뺀다."""
    out, labs = [], engine_labels or {}
    cells = tb.get("cells") or ()
    for h in hs:
        if h["paras"] and set(h["paras"]) <= set(labs.get(h["dim"]) or ()):
            continue
        row = {"dim": h["dim"], "dimName": DIM_NAME.get(h["dim"], h["dim"]), "value": h["value"], "src": "struct", "inGroup": False, "table": tid, "text": h["value"]}
        if h["paras"]:
            out.append({"kind": "label", **row, "paras": list(h["paras"])})
        scope = [p for c in cells if _inside(h, c) for p in c.get("paras") or ()]
        if scope:
            out.append({"kind": "scope", **row, "paras": scope})
    return out


def _caption_key(text):
    return _DIGITS.sub("", str(text or ""))


def series(tables, levels=None, order=None):
    """같은 헤딩 아래 표 묶음 → [[{tid, head}, …], …](묶음마다 2표 이상 · 문서 차례).

    tables = [{tid, tb(판정된 표), hs(그 표의 값 머리), owner(3단계 소속 {id, source} | None), caption(표 캡션 글 | "")}] — 본문 표, 문서 차례.
    order = {블록 id: 문서 차례} · levels = {문단 id: 간이 레벨}(사이에 헤딩 줄이 있으면 끊는다 — 둘 다 없으면 차례 검사를 건너뛴다)."""
    def own(t):
        o = t.get("owner") or {}
        return o.get("id") if o.get("id") and o.get("source") == "stage2" and not o.get("root") else None

    def heads_between(a, b):
        if not order or not levels:
            return False
        lo, hi = order.get(a), order.get(b)
        return lo is None or hi is None or any(lo < order.get(p, -1) < hi for p in levels)

    out, cur = [], []

    def close():
        if len(cur) >= 2:
            out.append(list(cur))
        cur.clear()

    for t in tables:
        hs = t.get("hs") or ()
        one = hs[0] if len(hs) == 1 and hs[0]["num"] is not None else None
        k = (own(t), table_kv.type_key(t["tb"]), _caption_key(t.get("caption"))) if one and own(t) else None
        if cur:
            prev = cur[-1]
            ph = prev["head"]
            same = (k is not None and k == prev["key"] and one["dim"] == ph["dim"] and one["role"] == ph["role"] and one["rows"][0] == ph["rows"][0]
                    and one["cols"][0] == ph["cols"][0] and _after(ph["num"], one["num"]) and not heads_between(prev["tid"], t["tid"]))
            if not same:
                close()
        if k is not None:
            cur.append({"tid": t["tid"], "head": one, "key": k})
    close()
    return [[{"tid": x["tid"], "head": x["head"]} for x in run] for run in out]


def _after(a, b):
    """b 가 a 보다 뒤 값인가(같은 구분 — 수 · 튜플 · 기관 열쇠는 서로 다르기만)."""
    if isinstance(a, str) or isinstance(b, str):
        return a != b
    try:
        return b > a
    except TypeError:
        return False


def series_reads(runs, cell_paras):
    """표 묶음 → [{kind: table, dim, dimName, value, src: "series", inGroup: False, table, paras(그 표의 모든 칸 문단), text}]. cell_paras = {표 id: [문단 id …]}."""
    out = []
    for run in runs:
        for x in run:
            h = x["head"]
            ps = list(cell_paras.get(x["tid"]) or ())
            if ps:
                out.append({"kind": "table", "dim": h["dim"], "dimName": DIM_NAME.get(h["dim"], h["dim"]), "value": h["value"], "src": "series", "inGroup": False,
                            "table": x["tid"], "paras": ps, "text": f"{h['value']} · 같은 헤딩 아래 표 {len(run)}개"})
    return out
