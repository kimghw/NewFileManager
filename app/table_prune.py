"""빈 필드 제거(spec_헤딩_추출 ② §16 · spec_테이블매니저 ② §12) — 표 하나에서 **입력하는 줄(레코드)이 통째로 빈 행**을 찾아 지운다. 사용자 2026-11-10 "테이블 … 모서리 클릭하면, 빈필드 제거하기".

2026-11-22 다시 정의(사용자 "빈 필드란느건.... 빈 칸만 이야기 하는게 아니고 행, 열헤딩의 서브테이블에서 입력해야할 행을 이야기 하는거야" · "구분기준, 구역이 되는 필드는 열 또는 행 헤더로봐야지" ·
"서브 테이블이면 그 섭테이블에 필드가 없으면 삭제, 만약 테이블 이면 테이블을 삭제, … 그 헤딩까지 삭제" — astra 협의 artifacts/table_prune_astra_2026-11-22/). 아래 본디 규칙 위에 바뀐 것:
- **열은 지우지 않는다** — 값이 하나라도 든 줄의 빈 칸(속성)은 그대로다. 빈 열을 찾지 않는다(`emptyCols` 는 늘 빈 목록 — 옛 화면 호환).
- **열쇠 칸**(`_keys`): 구분 기준 · 번호 머리 아래의 칸(「한국선급」 · 「2027」 · 「1」)은 줄의 열쇠이지 입력값이 아니다 — 그런 칸만 든 줄은 빈 줄. 역할(role)은 안 바꾼다(이 판정 안에서만).
- **쓴 값이 든 칸은 줄째 지우지 않는다**: 셈하는 칸에 0 아닌 값이 적힘(`_hand` — 수기 합계) · 음영 때문에 머리로 읽힌 수(`_figure` — 「24,000」) · 목표 · 실적 쌍의 한쪽(`_pairs`) ·
  그리고 지울 범위 전체를 마지막에 다시 본다(`_loose` — 통째로 없어지는 칸이 빈 입력 · 열쇠 · 머리 · 안내뿐인가).
- **빈 서브 테이블**(`_band_rows`): 입력 줄이 모두 지울 줄인 전폭 띠는 머리 행까지 띠째 · **이미 머리만 남은 서브 테이블**(`orphans`)은 저장된 3단계 표(지우기 전)의 띠와 칸 id 로 대조해서만.
- **표째**(`tableGone`): 지우면 표에 입력 줄이 하나도 안 남을 때 — 줄을 지우지 않고 표째 지우기를 따로 낸다(사람이 확인). 그 범위 · 소속 헤딩은 `table_scope`.

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
import re

from app import heading_calc as HC
from app import heading_tables as HT
from app import table_excel as TX
from app import table_grid as grid
from app import table_heads, table_ops

_SUM_KINDS = ("total", "ratio")
_HEADS = ("colhead", "rowhead", "corner")
_FRAME = ("title", "note", "spacer")   # 표의 틀 — 제목 · 안내 · 간격 칸(줄 · 표와 함께 지워져도 쓴 값이 아니다)
_USER_ROLES = ("rowhead", "colhead", "field")  # 사람의 헤더 지정으로 쓰이는 값(`table_excel._analyze` 와 같다)
DATA_KINDS = ("matrix", "form", "plain", "list")   # 입력 줄을 가질 수 있는 띠(제목 · 안내 · 간격 띠는 아니다)
WHY_MAX = 3      # 줄마다 보이는 자리표시 글 수
WHY_TEXT = 24    # 자리표시 글 하나의 길이(줄 이름 `_names` 와 같다)
KEY_TEXT = 30    # 열쇠 칸 글 길이 상한(빈칸 뗀 글) — 그보다 긴 글은 작성 글이다
# 열쇠 머리(그 아래 칸이 줄의 열쇠) — 빈칸 · 괄호 · 각주 번호를 뗀 머리 글이 **이 낱말 그대로**일 때만(fullmatch). 「구축연도」 · 「발행기관」 · 「소속기관명」 · 「해당연도」 · 「기관유형」 은 속성이라 아니다.
_KEY_HEAD = (("org", re.compile(r"(?:연구개발|수행|참여|주관|공동|협동|위탁)?(?:연구)?(?:개발)?기관명?")),
             ("time", re.compile(r"연도|년도|연차|차년도|년차|단계")),
             ("ord", re.compile(r"번호|순번|연번|순서|no\.?", re.I)))
_PAIR = {"목표", "실적", "계획", "당초", "변경", "목표치", "실적치"}   # 한 레코드의 두 줄(같은 지표의 목표 · 실적)
_MARK = re.compile(r"(?<=[^\d\s])\d{1,3}(?:-\d{1,3})?\)")           # 각주 번호(「건수21)」 — 양식 정리가 떼는 위첨자)
_PAREN = re.compile(r"\([^)]*\)|（[^）]*）")
_WS = re.compile(r"\s+")


def _plain(text):
    """견줄 꼴 — 각주 번호와 빈칸을 뗀 글."""
    return _WS.sub("", _MARK.sub("", text or ""))


def _key_head(text):
    """열쇠 머리의 종류(org | time | ord) | None."""
    t = _PAREN.sub("", _plain(text))
    return next((k for k, rx in _KEY_HEAD if t and rx.fullmatch(t)), None)


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
    """작성 글 보호(spec_테이블매니저 ② §4 ⓐ)의 대상 칸 id — 역할은 헤더(열헤더·행헤더·귀퉁이)인데 **성격이 필드**(긴 글·문장·값 — `heading_tables.nature`)이거나
    **수가 적힌**(`_figure` — 음영 때문에 머리로 읽힌 금액 「24,000」 · 비율 「7.1%」: 2026-11-22 astra 가 t9199 에서 그 줄을 지우면 세 칸이 없어지는 것을 재현) 칸이고
    글이 있는(자리표시뿐이 아닌) 칸. 빼는 것: 사람이 역할을 지정한 칸(roles — 지정이 먼저: 헤더로 지정했으면 전처럼 헤더) ·
    순번 칸(`heading_tables._ORDINAL` 꼴 「1」·「①」·「가」 — 초안이 순번이라서 헤더 열로 본 값이지 작성 글이 아니다: 번호 붙은 목록 표의 빈 줄은 전처럼 지울 줄)."""
    user = {i for i, r in (roles or {}).items() if r in _USER_ROLES}
    ords = _ordinals(cells)
    return {x["id"] for x in cells if x.get("role") in _HEADS and x["id"] not in user and not cell_empty(x)
            and (x.get("nature") == "field" or _figure(x) or _CHECK.match(x.get("textFull") or "")) and x["id"] not in ords}


_CHECK = re.compile(r"^[\s\[(]*[☑✓✔√■●◎]\s*[\])]?\s*$")   # 체크 표시(머리로 읽힌 결과 칸의 「☑」 — 쓴 값: astra 2차)


def _ordinals(cells):
    """순번 칸 id — 머리 역할 칸 가운데 `_ORDINAL` 꼴(「1」 · 「①」 · 「가」)이고 **같은 열에서 위부터 1, 2, 3 … 차례**인 것(`_in_order` — 숫자가 아닌 순번 글자는 꼴만).
    꼴만 보고 빼면 「수량 | 금액」 의 「10」 같은 쓴 값이 순번으로 빠진다(astra 2차)."""
    by = {}
    for x in cells:
        if x.get("role") in _HEADS and HT._ORDINAL.match(x.get("textFull") or ""):
            by.setdefault((x["col"], x["cs"]), []).append(x)
    out = set()
    for xs in by.values():
        nums = [x for x in xs if re.sub(r"[.)\s]", "", x.get("textFull") or "").isdigit()]
        if not nums or _in_order(nums):
            out.update(x["id"] for x in xs)
    return out


def _figure(x):
    """수가 적힌 칸인가 — 구분 기준 값(「2026」 · 「1차년도」 — 머리 의미 `basis` 가 있음)과 「-」 는 아니다."""
    n = HC.parse_num(x.get("textFull") or "")
    return n.get("num") is not None and not n.get("dash") and not x.get("basis")


def _hand(x):
    """셈하는 칸(합계 · 비율)에 쓴 값이 있나 — 빈 칸 · 자리표시가 아니면 쓴 값(「0」 · 「-」 도 — 사람이 적었는지 양식의 기본값인지 근거가 없다: astra 2차).
    있으면 그 줄은 채워진 줄이다(피연산자가 비어도 적힌 합계는 남긴다)."""
    return not cell_empty(x)


def _in_order(cells):
    """번호 열인가 — 글이 있는 칸의 값이 위에서부터 1, 2, 3 … (빈 칸은 끝에만)."""
    vals = [(x.get("textFull") or "").strip().rstrip(".)") for x in sorted(cells, key=lambda x: x["row"])]
    got = [v for v in vals if v]
    return bool(got) and vals[:len(got)] == got and got == [str(i) for i in range(1, len(got) + 1)]


_ORG_MARK = re.compile(r"㈜|\(주\)|（주）|주식회사|\(재\)|㈔|\(사\)")
_TIME_VALUE = re.compile(r"\(?(?:(\d{1,2})\s*단계\)?[-–·,\s]*)?(?:(\d{1,2})\s*(?:차\s*년\s*도|년\s*차|차)?)?(?:\(\s*((?:19|20)\d\d)\s*년?\s*\))?")
_TIME_VALUE2 = re.compile(r"(\d{1,2})\s*(?:차\s*년\s*도|년\s*차|차)[-–·,\s]*\(?\s*(\d{1,2})\s*단계\s*\)?")


def _org_value(text, names):
    """칸 글이 프로젝트 구성의 기관 이름 그대로인가(법인 표시 · 빈칸은 뗌 — 「㈜랩오투원」 = 「랩오투원」)."""
    t = _WS.sub("", _ORG_MARK.sub("", text or ""))
    return bool(t) and t in names


def _time_value(text, values):
    """칸 글이 프로젝트 구성의 단계 · 차년도 · 연도 값인가 — 「1단계-1차년도」 · 「2차년도」 · 「2」(차년도 수 안) · 「(1단계)」 · 「2027」 · 「2027년」(사업기간의 해)."""
    t = _WS.sub("", text or "")
    stages = [int(n) for n in (values.get("stages") or ()) if isinstance(n, int)]
    period = values.get("period") or {}
    years = set()
    try:
        years = set(range(int(str(period["start"])[:4]), int(str(period["end"])[:4]) + 1))
    except (KeyError, TypeError, ValueError):
        pass
    y = re.fullmatch(r"((?:19|20)\d\d)년?", t)
    if y:
        return int(y.group(1)) in years
    m = _TIME_VALUE.fullmatch(t)
    if not m or not (m.group(1) or m.group(2)):
        r = _TIME_VALUE2.fullmatch(t)   # 차년도가 앞 — 「2차 (1단계)」 · 「2차년도(1단계)」
        if not r:
            return False
        yr, st = r.group(1), r.group(2)
        return 1 <= int(st) <= len(stages) and 1 <= int(yr) <= sum(stages)
    st, yr, cal = m.group(1), m.group(2), m.group(3)
    return (not st or 1 <= int(st) <= len(stages)) and (not yr or 1 <= int(yr) <= sum(stages)) and (not cal or int(cal) in years)


def _key_names(values):
    """프로젝트 구성의 기관 이름들(견줄 꼴 — `_org_value`)."""
    from app import zone_prune
    try:
        return {_WS.sub("", _ORG_MARK.sub("", n)) for n in zone_prune._names(values)}
    except (KeyError, TypeError, AttributeError):
        return set()


def _keys(cells, subs, roles=None, values=None):
    """레코드 열쇠 칸 → {칸 id: 종류(org | time | ord)} — 사용자 2026-11-22 "구분기준, 구역이 되는 필드는 열 또는 행 헤더로봐야지 .. 입력하는 값이 아니니깐"(spec_테이블매니저 ② §12 「열쇠 칸」).
    역할(role)은 바꾸지 않는다 — 이 판정 안에서만 「입력값이 아님」 으로 본다(astra: 공용 역할을 바꾸면 키-값 · 표 채우기 · 3단계가 함께 바뀐다).
    편집 구역의 근거(`ev: cell`)는 쓰지 않는다 — 그 근거는 같은 줄의 값 칸까지 퍼져 있어(실적 「75」 에도 기관이 붙는다) 값을 열쇠로 잘못 뺀다(astra 재현).
    머리 낱말만으로도 부족하다(「신청자 | 직책 | 기관」 의 기관 열은 속성 — astra 2차): 기관 · 단계 · 차년도 · 연도 열쇠는 **칸 글이 프로젝트 구성의 값 그대로**일 때만(values — 연구개발과제 문서에서
    끝점이 준다 · 없으면 그 두 종류는 열쇠가 없다: 구분 기준이 구성의 값이라는 사용자 말 그대로). 번호 머리는 그 열 값이 1, 2, 3 … 차례일 때만.
    조건(모두): ⓐ 머리 행이 있는 격자 띠(matrix) ⓑ 바로 위 열 머리 글이 `_KEY_HEAD` 그대로 ⓒ 그 열에 열쇠 값이 든 레코드가 둘 이상 ⓓ 그 띠에 열쇠가 아닌 입력 칸이 있다(열쇠뿐인 표의 열쇠는 그 자체가 쓴 값)
    ⓔ 칸 글이 비었거나 열쇠 값(구성의 값 · 차례 번호) ⓕ 사람이 그 칸을 필드로 지정하지 않았다 ⓖ 칸에 표 · 그림이 없다."""
    by = {x["id"]: x for x in cells}
    user = {i for i, r in (roles or {}).items() if r == "field"}
    names = _key_names(values) if values else set()
    out = {}
    for b in subs:
        if b.get("kind") != "matrix" or not b.get("headerRows"):
            continue
        fields = [x for x in cells if x.get("sub") == b["id"] and x.get("role") == "field"]
        under = {}
        for f in fields:
            path = f.get("colPath") or []
            h = by.get(path[-1]) if path else None
            kind = _key_head(h.get("textFull")) if h is not None else None
            if kind == "ord" or (kind and values):
                under.setdefault(h["id"], (kind, []))[1].append(f)
        keyed = {f["id"] for _k, fs in under.values() for f in fs}
        if not any(f["id"] not in keyed for f in fields):
            continue
        for kind, fs in under.values():
            if kind == "ord":
                good = [f for f in fs if (f.get("textFull") or "").strip()]
                if not _in_order(fs):
                    continue
            else:
                is_key = (lambda t: _org_value(t, names)) if kind == "org" else (lambda t: _time_value(t, values))
                good = [f for f in fs if (f.get("textFull") or "").strip() and is_key(f["textFull"])]
            if len({f["row"] for f in good}) < 2:
                continue
            for f in fs:
                if f["id"] in user or f.get("nested") or (f.get("kinds") or {}).get("object"):
                    continue
                if f in good or not (f.get("textFull") or "").strip():
                    out[f["id"]] = kind
    return out


def _pairs(cells, lines):
    """목표 · 실적 쌍(astra P2 — 사용자 확인 전): 여러 행에 걸친 행 머리 바로 오른쪽의 행 머리들이 모두 `_PAIR` 이면 그 행들은 한 레코드다 — 한 행이라도 남으면 쌍째 남긴다."""
    gone = set(lines)
    for p in cells:
        if p.get("role") != "rowhead" or p["rs"] < 2:
            continue
        span = set(range(p["row"], p["row"] + p["rs"]))
        kids = [x for x in cells if x.get("role") == "rowhead" and x["col"] == p["col"] + p["cs"] and x["row"] in span]
        if len(kids) >= 2 and all(_PAREN.sub("", _plain(x.get("textFull"))) in _PAIR for x in kids) and gone & span and not span <= gone:
            gone -= span
    return sorted(gone)


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


def _empty_lines(cells, inputs, empty, n, axis, written=()):
    """축(axis "r" 행 · "c" 열)의 빈 줄 번호 — 채우는 필드가 걸쳐 있고 모두 비었으며 합계·비율 헤더가 안 걸친 줄. written = 그 줄을 채워진 줄로 만드는 칸(쓴 값이 든 셈하는 칸 — `_hand`)."""
    has, filled, summed = [False] * n, [False] * n, [False] * n
    head = "rowhead" if axis == "r" else "colhead"
    for x in cells:
        a, k = _span(x, axis)
        lines = range(max(0, a), min(n, a + k))
        if x["id"] in written:
            for i in lines:
                filled[i] = True
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


def _band_name(cells, b):
    """띠의 이름 — 띠 왼쪽 위의 머리 칸(귀퉁이 · 행 머리) 글, 없으면 첫 열 머리 글(각주 번호를 뗌)."""
    (r0, r1), (c0, c1) = b["rows"], b["cols"]
    inb = sorted((x for x in cells if r0 <= x["row"] < r1 and c0 <= x["col"] < c1 and x.get("role") in _HEADS and (x.get("textFull") or "").strip()),
                 key=lambda x: (x["col"], x["row"]))
    pick = next((x for x in inb if x["col"] == c0), inb[0] if inb else None)
    return " ".join(_MARK.sub("", pick["textFull"]).split())[:WHY_TEXT] if pick else ""


def _band_rows(cells, subs, lines, has, ncols):
    """빈 서브 테이블(사용자 2026-11-22 "이게 서브 테이블이면 그 섭테이블에 필드가 없으면 삭제") — 입력 줄(has)이 있던 띠의 입력 줄이 모두 지울 줄(lines)이면
    그 띠의 행 전부(머리 행 · 띠 안 안내 줄)를 더 지운다 → [{sub, rows: [첫 행, 끝 행], name, how: "empty"}]. **지우기 전 표의 띠**로 본다(값 행을 지운 뒤에는 그 띠가 앞뒤와 한 띠로 읽힌다).
    전폭 띠만 — 좌우로 나란한 띠는 행째 지우면 옆 띠의 칸도 같이 지워진다(astra). 머리 행이 더해지지 않는 띠(키-값 띠의 줄이 모두 빔)는 그 줄들만이라 따로 적지 않는다."""
    gone, out = set(lines), []
    for b in subs:
        (r0, r1), (c0, c1) = b["rows"], b["cols"]
        if b.get("kind") not in DATA_KINDS or (c0, c1) != (0, ncols):
            continue
        recs = [i for i in range(r0, r1) if has[i]]
        if recs and all(i in gone for i in recs) and any(i not in gone for i in range(r0, r1)):
            out.append({"sub": b["id"], "rows": [r0, r1 - 1], "name": _band_name(cells, b), "how": "empty"})
    return out


def orphans(tb, saved):
    """이미 머리만 남은 서브 테이블(사용자 2026-11-22 그림 — 앞서 「빈 필드 제거」 로 값 행만 지워 「등록·기탁 건수」 · 「연구시설·장비 … 등록 현황」 의 머리 행만 남음)
    → [{sub, rows: [첫 행, 끝 행], name, how: "orphan", heads: [칸 id…]}]. saved = 저장된 3단계 결과의 **같은 표**(지우기 전 — `heading_runs.tables`).
    머리 음영만 보고 짐작하지 않는다(범례 · 체크 안내 · 다음 묶음의 공통 열 머리도 같은 꼴 — astra): 저장된 띠마다 ⓐ 입력 칸(역할 또는 초안이 field)이 있었고 지금 하나도 없으며
    ⓑ 머리 칸은 모두 지금도 있고 ⓒ 지금 그 머리 칸들이 차지한 행에 그 칸들 말고 다른 칸이 없고 ⓓ 글이 같다(각주 번호 · 빈칸만 다를 수 있다 — 양식 정리가 위첨자 번호를 뗀다)."""
    if not isinstance(saved, dict) or saved.get("id") != tb["id"] or not isinstance(saved.get("cells"), list):
        return []
    now = {x["id"]: x for x in tb["cells"]}
    out = []
    for s in saved.get("subtables") or ():
        try:
            (r0, r1), (c0, c1) = s["rows"], s["cols"]
        except (KeyError, TypeError, ValueError):
            continue
        if s.get("kind") not in DATA_KINDS:
            continue
        inb = [x for x in saved["cells"] if isinstance(x, dict) and r0 <= x.get("row", -1) < r1 and c0 <= x.get("col", -1) < c1]
        ins = [x for x in inb if "field" in (x.get("role"), x.get("draft"))]
        heads = [x for x in inb if x not in ins]
        if not ins or not heads or any(x["id"] in now for x in ins) or not all(x["id"] in now for x in heads):
            continue
        cur = [now[x["id"]] for x in heads]
        a, b = min(x["row"] for x in cur), max(x["row"] + x["rs"] for x in cur)
        on = {x["id"] for x in tb["cells"] if x["row"] < b and x["row"] + x["rs"] > a}
        if on != {x["id"] for x in cur} or any(x["row"] < a or x["row"] + x["rs"] > b for x in cur):
            continue
        if not all(_same_head(x, now[x["id"]]) for x in heads):
            continue
        out.append({"sub": s.get("id"), "rows": [a, b - 1], "name": _band_name(tb["cells"], {"rows": [a, b], "cols": [0, tb["cols"]]}), "how": "orphan",
                    "heads": sorted(on)})
    return out


def _same_head(old, new):
    """저장된 머리 칸(old — 3단계 결과의 칸)과 지금 칸(new)이 같은 칸인가 — 자리(열 · 폭)가 같고, 지금 역할이 머리 · 틀이며, 글이 같다(지금 글이 저장 글에서 각주 번호만 뗀 것도 같음 —
    양식 정리가 위첨자 번호를 뗀다). 저장 글이 잘렸으면(TEXT_MAX) 뒤에 덧붙인 글을 알 수 없어 같다고 하지 않는다 · 칸 안 표 · 그림이 있으면 아님(astra 2차)."""
    saved = old.get("text") or ""
    if len(saved) >= HT.TEXT_MAX or (old.get("col"), old.get("cs", 1)) != (new.get("col"), new.get("cs")):
        return False
    if new.get("role") not in _HEADS + _FRAME or new.get("nested") or (new.get("kinds") or {}).get("object"):
        return False
    t = _WS.sub("", new.get("textFull") or "")
    return t == _WS.sub("", saved) or t == _plain(saved)


def _loose(cells, lines, ok):
    """마지막 내용 검사(astra P1 「최종 범위에 대한 작성 내용 검사」) — lines(지울 행)를 지우면 **통째로 없어지는** 칸 가운데 ok 가 아닌 칸(쓴 값)이 걸친 행들.
    그 행은 지우지 않는다. 여러 줄에 걸쳐 남는 칸은 줄어들 뿐 글이 남아 보지 않는다(`_guard` 와 같은 전제)."""
    gone, out = set(lines), set()
    for x in cells:
        span = range(x["row"], x["row"] + x["rs"])
        if all(i in gone for i in span) and not ok(x):
            out.update(span)
    return out


_OBJ = {"pic", "equation", "ole", "container", "rect", "line", "ellipse", "arc", "polygon", "curve", "connectLine", "textart", "video", "chart", "tbl"}


def _objects(doc, tid):
    """칸 안에 표 · 그림 · 수식 · 도형 같은 개체가 든 칸 id — XML 에서 바로(1단계 레코드는 글 분류가 빈 문단일 때만 개체를 올려, 「00%」 와 그림이 한 문단이면 놓친다: astra 2차)."""
    el = doc._ids.get(tid)
    out = set()
    if el is None:
        return out
    for tc in el.iter():
        if not isinstance(tc.tag, str) or tc.tag.rsplit("}", 1)[-1] != "tc":
            continue
        cid = doc._rev.get(tc)
        if cid is not None and any(isinstance(x.tag, str) and x.tag.rsplit("}", 1)[-1] in _OBJ for x in tc.iter() if x is not tc):
            out.add(cid)
    return out


def analyze(doc, tid, store=None, doc_key=None, roles=None, history=None, values=None):
    """표의 빈 줄 → `analyze_table` 의 결과. 표가 아니면 None, 너무 크면 ValueError.
    roles = 사용자 헤더 지정(spec_owpml_편집 ② §5-4 — `table_excel._analyze`) · history = 저장된 3단계 결과의 같은 표(`orphans`) · values = 프로젝트 구성 값(`_keys` — 연구개발과제 문서만)."""
    stage1 = TX.records(doc, tid, store, doc_key)
    if stage1 is None:
        return None
    return analyze_table(next((t for t in HT.collect(stage1) if t["id"] == tid), None), tid, roles, history, values, _objects(doc, tid))


def _merge(bands):
    """겹치는 띠를 하나로(지금 판정의 빈 띠와 저장된 판정의 머리만 남은 띠가 같은 행을 가리킬 수 있다 — 따로 두면 같은 자리를 두 번 지워 미리보기 밖 행이 지워진다: astra 2차)."""
    out = []
    for b in sorted(bands, key=lambda b: (b["rows"][0], b["rows"][1])):
        if out and b["rows"][0] <= out[-1]["rows"][1]:
            m = out[-1]
            m["rows"][1] = max(m["rows"][1], b["rows"][1])
            m["name"] = m["name"] if not b["name"] or b["name"] in m["name"] else f"{m['name']} · {b['name']}".strip(" ·")
            m["how"] = "empty" if "empty" in (m["how"], b["how"]) else m["how"]
            m["heads"] = sorted(set(m.get("heads") or ()) | set(b.get("heads") or ()))
            m["recs"] = sorted(set(m.get("recs") or ()) | set(b.get("recs") or ()))
        else:
            out.append({**b, "rows": list(b["rows"])})
    return out


def analyze_table(tb, tid, roles=None, history=None, values=None, objects=()):
    """`analyze` 의 몸통(문서 없이) — tb = `heading_tables.collect` 꼴의 표(1칸 표면 None). 여기서 초안 역할·표 의미를 매긴다(`table_excel._analyze` — tb 의 칸에 적힌다).
    → {table, rows, cols, fields(채우는 필드 수 — 열쇠 칸은 뺌), emptyFields, keys(열쇠 칸 수), allEmpty, emptyRows[](빈 레코드 줄), bands[](통째로 지울 띠 — 빈 서브 테이블 · 머리만 남은 서브 테이블),
    drop[](지울 행 전부), kept[](쓴 값이 있어 남긴 행 — 마지막 내용 검사), tableGone(지우면 입력 줄이 하나도 안 남음 — 줄 대신 표째), goneCells[](통째로 없어질 칸 id),
    emptyCols[](늘 빈 목록) · rowNames{줄: 헤더 글} · colNames{} · why{rows, cols}, note?} — 지울 수 있는지(합친 칸)는 아직 안 본다."""
    out = {"table": tid, "rows": 1, "cols": 1, "fields": 0, "emptyFields": 0, "keys": 0, "allEmpty": False, "emptyRows": [], "emptyCols": [], "bands": [], "drop": [],
           "kept": [], "tableGone": False, "goneCells": [], "rowNames": {}, "colNames": {}, "why": {"rows": {}, "cols": {}}}
    if tb is None:
        return {**out, "note": "1칸 표(글상자)에는 필드가 없습니다"}
    if len(tb["cells"]) > TX.MAX_CELLS:
        raise ValueError(f"표가 너무 큽니다(칸 {len(tb['cells'])} > {TX.MAX_CELLS})")
    subs, sem = TX._analyze(tb, roles)
    cells, nr = tb["cells"], tb["rows"]
    objects = set(objects or ())
    targets = {f["cell"] for f in sem["formulas"]}  # 수식으로 셈하는 칸(합계·비율·코드 식) — 사람이 채우는 칸이 아니다
    keys = _keys(cells, subs, roles, values)        # 레코드 열쇠(구분 기준 · 번호 머리 아래) — 입력값이 아니다
    keys = {i: k for i, k in keys.items() if i not in objects}
    inputs = {x["id"] for x in cells if x.get("role") == "field" and x["id"] not in targets and x["id"] not in keys}
    empty = {x["id"] for x in cells if x["id"] in inputs and cell_empty(x) and x["id"] not in objects}
    hand = {x["id"] for x in cells if x["id"] in targets and (_hand(x) or x["id"] in objects)}
    saved_ids = {x.get("id") for x in (history or {}).get("cells") or () if isinstance(x, dict)}
    orph = []
    for o in orphans(tb, history):   # 지금 값 칸(저장된 판정에 없던 새 칸)이 그 머리 아래에 있으면 머리만 남은 것이 아니다(astra 2차 — 옛 값 행을 지우고 새 행에 쓴 값)
        heads = set(o["heads"])
        live = any(x["id"] not in saved_ids and x.get("role") == "field" and not cell_empty(x) and heads & set((x.get("colPath") or []) + (x.get("rowPath") or []))
                   for x in cells)
        if not live and not any((roles or {}).get(i) == "field" for i in heads):
            orph.append({**o, "recs": []})
    out.update(rows=nr, cols=tb["cols"], fields=len(inputs), emptyFields=len(empty), keys=len(keys))
    if not inputs and not orph:
        return {**out, "note": "채우는 필드가 없는 표입니다"}
    out["allEmpty"] = all_empty = bool(inputs) and len(empty) == len(inputs) and not hand
    kept = _written(cells, roles)  # 작성 글이 든 헤더 역할 칸 — 이 칸이 통째로 없어지게 되는 줄은 채워진 줄(`_guard`)
    base = _pairs(cells, _empty_lines(cells, inputs, empty, nr, "r", hand))
    rows = _grow_groups(cells, base, nr)
    keep = _guard(cells, kept, rows, nr, "r")
    if keep:
        rows = _grow_groups(cells, [i for i in base if i not in keep], nr, keep)
    has = [False] * nr
    for x in cells:
        if x["id"] in inputs:
            for i in range(max(0, x["row"]), min(nr, x["row"] + x["rs"])):
                has[i] = True
    bands = [{**b, "recs": [i for i in range(b["rows"][0], b["rows"][1] + 1) if has[i]]} for b in _band_rows(cells, subs, rows, has, tb["cols"])]
    orph_ok = {i for o in orph for i in o["heads"]}

    def ok(x):   # 통째로 없어져도 되는 칸 — 빈 입력 · 열쇠 · 쓴 값 없는 셈 칸 · 쓴 값이 아닌 머리 · 틀(긴 글이 아닌) · 머리만 남은 서브 테이블의 머리
        i = x["id"]
        if i in objects or x.get("nested") or (x.get("kinds") or {}).get("object"):
            return False
        if i in empty or i in keys or i in orph_ok:
            return True
        if i in targets:
            return i not in hand
        if x.get("role") in _FRAME:   # 안내 · 제목 칸에 쓴 긴 글(성격이 필드)은 쓴 값이다(astra 2차 — 「… 확정되었습니다.」 한 칸 행)
            return x.get("nature") != "field"
        if x.get("role") in _HEADS:
            return i not in kept
        return x.get("role") == "field" and cell_empty(x)
    span = lambda b: set(range(b["rows"][0], b["rows"][1] + 1))  # noqa: E731
    rows0, bands0, blocked = rows, bands + orph, set()
    while True:   # 남긴 행이 생기면 쌍 · 띠가 다시 갈린다 — 남긴 행은 늘기만 하니 멈춘다
        rows = _pairs(cells, [i for i in rows0 if i not in blocked])   # 작성값 보호로 한쪽이 남으면 쌍째 남긴다(astra 2차)
        bands = [b for b in _merge([b for b in bands0 if not blocked & span(b)]) if set(b["recs"]) <= set(rows)]   # 겹치는 띠는 하나로 · 입력 줄이 남는 띠는 아님
        drop = set(rows) | {i for b in bands for i in span(b)}
        more = _loose(cells, drop, ok) - blocked
        if not more:
            break
        blocked |= more
    out["kept"] = sorted(blocked & (set(base) | {i for i in range(nr) if has[i]}))
    rest = [x for x in cells if not all(i in drop for i in range(x["row"], x["row"] + x["rs"]))]
    out["tableGone"] = bool(drop) and all(x.get("role") in _FRAME and ok(x) for x in rest)
    if all_empty and not out["tableGone"]:   # 빈 양식(입력 칸이 모두 빔)은 줄을 정하지 않는다 — 표째 지우기만 사람이 확인해 고른다
        return {**out, "note": "필드가 모두 비어 있습니다(빈 양식) — 지울 줄을 정하지 않습니다"}
    out["emptyRows"], out["drop"] = sorted(rows), sorted(drop)
    out["bands"] = [{k: b[k] for k in ("sub", "rows", "name", "how")} for b in bands]
    out["goneCells"] = sorted(x["id"] for x in cells if all(i in drop for i in range(x["row"], x["row"] + x["rs"])))
    out["rowNames"] = _names(cells, out["emptyRows"], "r")
    out["why"] = {"rows": _why(cells, empty, out["emptyRows"], "r"), "cols": {}}
    return out


def _sim(doc, tid):
    """문서 표의 격자 사본(요소 없이) — 미리보기에서 지울 수 있는지만 본다."""
    _tbl, cells, nr, nc = doc._tgrid(doc._ids.get(tid))
    return [grid.Cell(None, x.r, x.c, x.rs, x.cs) for x in cells], nr, nc


def _units(a):
    """지울 묶음 → [(첫 행, 끝 행, 띠 | None)] 아래부터 — 띠(빈 서브 테이블 · 머리만 남은 서브 테이블)는 **한 번에 지우거나 통째로 남긴다**(한 줄씩 다시 하면 머리만 남는다 — astra),
    나머지 빈 줄은 이어진 묶음(못 지우면 한 줄씩 — 전과 같음)."""
    inband = {i for b in a["bands"] for i in range(b["rows"][0], b["rows"][1] + 1)}
    units = [(b["rows"][0], b["rows"][1], b) for b in a["bands"]] + [(x, y, None) for x, y in _runs([i for i in a["drop"] if i not in inband])]
    return sorted(units, key=lambda u: -u[0])


def _run(a, drop):
    """`_units` 차례로 drop(a, b) → (지운 행, 못 지운 행, 지운 띠, 못 지운 띠, 지운 차례[(첫 행, 끝 행)…])."""
    done, skip, bands, skip_bands, steps = [], [], [], [], []

    def go(x, y):
        drop(x, y)
        steps.append([x, y])
    for x, y, b in _units(a):
        if b is not None:
            try:
                go(x, y)
                done += range(x, y + 1)
                bands.append({k: b[k] for k in ("sub", "rows", "name", "how")})
            except ValueError:
                skip_bands.append({k: b[k] for k in ("sub", "rows", "name", "how")})
            continue
        d, s = _each(range(x, y + 1), go)
        done += d
        skip += s
    return sorted(done), sorted(skip), sorted(bands, key=lambda b: b["rows"][0]), sorted(skip_bands, key=lambda b: b["rows"][0]), steps


def _gone_ids(doc, tid, rows):
    """지금 문서의 그 표에서 rows(지우기 전 격자의 행)를 지우면 **통째로 없어지는** 칸 id — 미리보기와 지우기가 같은 칸을 지우는지 견준다(astra 2차)."""
    _tbl, cells, _nr, _nc = doc._tgrid(doc._ids.get(tid))
    gone = set(rows)
    return sorted(i for x in cells if all(r in gone for r in range(x.r, x.r + x.rs)) and (i := doc._rev.get(x.el)) is not None)


def plan(doc, tid, store=None, doc_key=None, roles=None, history=None, values=None):
    """미리보기(문서는 안 바뀜) — analyze + 격자 사본으로 지울 수 있는 줄만: emptyRows = 실제로 지울 행 전부(빈 레코드 줄 + 띠째 지울 행 — 지우기 전 격자),
    skipRows(합친 칸에 걸려 못 지움) · bands(띠째 지울 서브 테이블) · skipBands · steps(지울 차례 — `apply` 가 그대로 한다) · goneCells(통째로 없어질 칸 id — 지금 문서 격자에서).
    표째(tableGone)면 줄은 셈하지 않는다(표째 지우기는 `table_scope`)."""
    out = analyze(doc, tid, store, doc_key, roles, history, values)
    if out is None:
        return None
    out.update(records=len(out["emptyRows"]), skipRows=[], skipCols=[], skipBands=[], steps=[])
    if out["tableGone"] or not out["drop"]:
        out["emptyRows"] = [] if out["tableGone"] else out["emptyRows"]
        return out
    cells, nr, nc = _sim(doc, tid)
    size = [nr]

    def drop_rows(a, b):
        cols = band(cells, nc, a, b)
        if cols is None:
            grid.drop_rows(cells, size[0], a, b)
        else:
            grid.drop_band(cells, size[0], nc, a, b, *cols)
        size[0] -= b - a + 1
    out["emptyRows"], out["skipRows"], out["bands"], out["skipBands"], out["steps"] = _run(out, drop_rows)
    out["goneCells"] = _gone_ids(doc, tid, out["emptyRows"])
    return out


def apply(doc, tid, p):
    """미리 본 계획(p — `plan` 의 결과: 끝점이 잠금 안에서 다시 세워 planId 로 견준 것)을 **그대로** 지운다 → {rows[], cols[], skipRows[], skipCols[], bands[], skipBands[]}
    (지운 행 번호 — 지우기 전 격자 기준 · 열은 늘 빈 목록). 다시 판정하지 않는다 — 계획을 확인한 뒤 규칙이 바뀌면 다른 줄을 지운다(astra 2차).
    지우기 전 지금 격자에서 통째로 없어질 칸이 계획의 goneCells 와 같아야 하고, 차례(steps) 하나라도 못 하면 ValueError(부르는 쪽 트랜잭션이 되돌린다 — `server._edit`).
    표째(tableGone)는 여기서 하지 않는다(`drop_table`)."""
    out = {"rows": [], "cols": [], "skipRows": [], "skipCols": [], "bands": [], "skipBands": []}
    if p.get("tableGone") or not p.get("steps"):
        return out
    if doc._ids.get(tid) is None or _gone_ids(doc, tid, p["emptyRows"]) != p["goneCells"]:
        raise ValueError("미리 본 칸과 지금 표의 칸이 다릅니다 — 「빈 필드 제거하기」 를 다시 누르세요")
    for a, b in p["steps"]:
        _tbl, cells, _nr, nc = doc._tgrid(doc._ids.get(tid))
        doc.delete_rows(tid, a, b, cols=band(cells, nc, a, b))
    doc._touch(doc._ids[tid])
    return {**out, "rows": p["emptyRows"], "skipRows": p["skipRows"], "bands": p["bands"], "skipBands": p["skipBands"]}


# ---- 표째 · 소속 헤딩까지(사용자 2026-11-22 "만약 테이블 이면 테이블을 삭제, 이 테이블의 소속 헤딩이 있고 .. 그 헤딩의 테이블 이였다면 그 헤딩까지 삭제") ------------------------
_HEAD_ROLES = ("heading", "subtitle")   # 지울 수 있는 소속 — 구분 라벨 · 문서 제목 · 안내 · 헤딩 아님 · 문서 맨 위는 아니다(astra: 직접 소속을 입증한 헤딩 하나까지만)


def _local(el):
    return str(el.tag).rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def _parts(p):
    """문단의 런 아래 요소 이름들(글 「t」 · 표 「tbl」 · 그림 · 수식 · 조판 부호 …)과 글."""
    names, text = [], []
    for r in p:
        if _local(r) == "run":
            for c in r:
                names.append((_local(c), c))
                if _local(c) == "t":
                    text.append("".join(c.itertext()))
        elif _local(r) not in ("linesegarray", ""):
            names.append((_local(r), r))
    return names, "".join(text)


def _bare(p):
    """빈 문단인가 — 글이 없고 런에 빈 글 말고 아무것도 없다(쪽 제어 · 책갈피 · 개체가 든 빈 줄은 빈 문단이 아니다 — astra) · 쪽 · 단 나눔이 걸린 문단과
    글 안에 탭 · 줄바꿈 같은 조판 글자가 든 문단도 아니다(astra 2차)."""
    if any(str(p.get(k) or "").lower() in ("1", "true") for k in ("pageBreak", "columnBreak")):
        return False
    names, text = _parts(p)
    return not text.strip() and all(n == "t" and len(c) == 0 for n, c in names)


def table_scope(doc, tid, graph=None):
    """표째 지울 범위 → {first, last, heading: {para, text} | None, why(헤딩을 남긴 까닭 — 없으면 ""), block(표째 못 지우는 까닭 — 없으면 "")}.
    ⓐ 표를 품은 문단에 이 표 말고 다른 것(글 · 다른 표 · 그림 · 수식 · 도형 · 조판 부호)이 있으면 표째 지우지 않는다 — `delete_blocks` 가 같은 문단의 수식 · 도형을 함께 지운다(astra 재현).
    ⓑ 헤딩까지는 2단계 그래프가 이 표(`tbl:<id>`)를 **바로** 그 헤딩(heading · subtitle · title) 아래에 둘 때만 — 구분 라벨 · 문서 맨 위 · 칸 · 1단계 어림 · 낡은 소속은 표까지만.
    그 헤딩 문단이 지금도 있고(글이 같음 — 각주 번호 · 「※ 안내」 꼬리는 달라도 됨) 같은 그릇(본문 · 같은 칸)이며, 헤딩 ~ 표 사이가 빈 문단뿐이고, 표 뒤 첫 빈 문단 아닌 블록이
    그 헤딩 아래가 아닌 헤딩이거나 그릇의 끝일 때(하위 헤딩 · 다른 글 · 다른 표가 있으면 헤딩은 남긴다). 위로 번지지 않는다(그 위 헤딩이 비게 돼도 남김)."""
    el = doc._ids.get(tid)
    if el is None or not doc._attached(el):
        return {"block": "그 표가 지금 문서에 없습니다"}
    host = doc._host(el)
    names, text = _parts(host)
    if text.strip() or [n for n, c in names if not (n == "t" or c is el)]:
        return {"block": "표를 품은 문단에 이 표 말고 다른 글 · 개체가 있어 표째 지우지 않습니다"}
    cap = next((c for c in el if _local(c) == "caption"), None)   # 표에 붙은 캡션은 표와 함께 없어진다 — 글이 있으면 확인 창에 보인다(astra 2차)
    caption = " ".join(" ".join("".join(t.itertext()) for t in cap.iter() if _local(t) == "t").split()) if cap is not None else ""
    out = {"first": tid, "last": tid, "heading": None, "why": "", "block": "", "caption": caption[:60]}
    if not isinstance(graph, dict):
        return {**out, "why": "헤딩 판정(2단계) 결과가 없어 헤딩은 남깁니다"}
    nodes = {n["id"]: n for n in graph.get("nodes") or () if isinstance(n, dict) and n.get("id")}
    box = next((c for c in graph.get("containers") or () if isinstance(c, dict) and c.get("id") == f"tbl:{tid}"), None)
    node = nodes.get((box or {}).get("parent"))
    if node is None or node.get("role") not in _HEAD_ROLES:
        return {**out, "why": "이 표를 바로 거느린 헤딩이 없어(문서 맨 위 · 구분 라벨 · 칸 · 헤딩 판정 뒤에 새로 생긴 표) 헤딩은 남깁니다"}
    hp = doc._ids.get(node.get("para"))
    if hp is None or not doc._attached(hp) or _local(hp) != "p" or hp.getparent() is not host.getparent():
        return {**out, "why": "소속 헤딩 문단이 지금 문서의 같은 자리에 없어 헤딩은 남깁니다"}
    hn, htext = _parts(hp)
    now, was = _plain(htext), _plain(HC._node_text(node))
    if not now or not (now == was or was.startswith(now) and was[len(now):].startswith("※")) or any(n != "t" for n, _ in hn):
        return {**out, "why": "헤딩 문단이 헤딩 판정 때와 달라(글 · 조판 부호) 헤딩은 남깁니다"}
    q = hp.getnext()
    while q is not None and q is not host:
        if _local(q) != "p" or not _bare(q):
            return {**out, "why": "헤딩과 표 사이에 다른 내용이 있어 헤딩은 남깁니다"}
        q = q.getnext()
    if q is None:
        return {**out, "why": "헤딩이 표보다 뒤에 있어 헤딩은 남깁니다"}
    q = host.getnext()
    while q is not None and _local(q) == "p" and _bare(q):
        q = q.getnext()
    if q is not None:   # 뒤 경계 — 그 헤딩 아래가 아닌 헤딩이어야 하고, 그것도 지금 글이 판정 때와 같아야 한다(옛 헤딩이 본문으로 바뀌면 앞 헤딩을 잘못 지운다 — astra 2차)
        nxt = next((n for n in nodes.values() if n.get("para") and doc._ids.get(n["para"]) is q), None)
        p, hops = (nxt or {}).get("parent"), 0
        while p and p in nodes and p != node["id"] and hops < 40:
            p, hops = nodes[p].get("parent"), hops + 1
        ended = p in (None, "", "root") or str(p).startswith("area:")   # 조상 사슬이 문서 맨 위에서 끝남(그릇 · 한도에서 끊기면 모름 — 헤딩을 남긴다)
        same = nxt is not None and _local(q) == "p" and (lambda now, was: bool(now) and (now == was or was.startswith(now) and was[len(now):].startswith("※")))(
            _plain(_parts(q)[1]), _plain(HC._node_text(nxt)))
        if nxt is None or nxt.get("role") not in _HEAD_ROLES + ("label",) or p == node["id"] or not ended or not same:
            return {**out, "why": "그 헤딩 아래에 이 표 말고 다른 내용(하위 헤딩 · 글 · 표)이 있거나 다음 헤딩을 확인할 수 없어 헤딩은 남깁니다"}
    return {**out, "first": doc._id(hp), "heading": {"para": doc._id(hp), "text": " ".join(htext.split())[:60]}}


def drop_table(doc, scope):
    """`table_scope` 의 범위를 지운다(헤딩 문단 ~ 표 — 사이 빈 문단 포함) → {removed[]}. 부르는 쪽이 트랜잭션(문서 전체 검사)으로 감싼다."""
    return doc.delete_blocks(scope["first"], scope["last"])
