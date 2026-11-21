"""병합 — 넣을 구성 선택(spec_병합 ② §4-1 「넣을 구성 선택」 — 2026-11-21 사용자 "이관, 병합을 할떄는 어떤 구성을 추출해서 넣을건지에 대한 것이 매칭하기 전에 결정되어야 하는데.. 이걸 선택하는 도구가 있었으면 좋겠어"
→ 물어서 받은 답 「넣을 범위」 · 「전부 넣음」): 원본 문서에서 **어느 기관 · 단계 · 차년도의 내용을 뽑아 목적 문서에 넣을지**. 순수 — 저장은 app/task_options.py(묶음마다의 실행 옵션 `take`), 쓰는 곳은 app/merge_api.py(자리 연결 · 넣기 계획).

- 고른 것(take) = {"org": [기관 이름…], "stage": [단계 번호…], "year": [전체 차례 차년도 수…]} — **열쇠가 없으면 그 기준은 전부**(아무것도 안 골랐으면 None = 전부 넣음: 전과 같은 동작).
  기관은 이름으로(문서마다 「공동1」 이 다른 기관일 수 있다 — merge_pairs.org_key 로 견준다) · 차년도는 전체 차례 수(1단계 2년 · 2단계 2년이면 2단계 1차년도 = 3) · 단계를 고르면 그 단계의 차년도만 남는다.
- `clean(take, values)` = 받은 것을 정리(모르는 기준 · 꼴이 틀리면 ValueError · 그 기준의 값을 모두 골랐으면 그 열쇠를 뺀다 = 전부) → take | None.
- `allowed(take, values)` → Allowed: `ident(("org"|"year"|"stage", 값))` · `ctx({"org", "year"})` = 그 값의 자리에 넣어도 되나(값을 모르는 자리 — None · 구분 기준이 걸리지 않은 자리 — 는 늘 참).
- `narrow(view, to_groups, A)` = 연결 목록(merge_pairs.pair 의 결과)에서 고르지 않은 구성의 묶음 · 항목을 「범위 밖」 으로 적는다(status "outside" — 넣기 계획 · LLM 검토 · 저장된 짝이 그 묶음을 건너뛴다) → 범위 밖이 된 묶음 수.
- `choices(values)` = 고를 수 있는 값(화면의 고르기) · `text(take, values)` = 한 줄 글(「기관: 한국선급 · 차년도: 2차년도」 | 「전부」)."""
from collections import Counter

from app import merge_pairs as P

DIMS = ("org", "stage", "year")
NAMES = {"org": "기관", "stage": "단계", "year": "차년도"}
OUT = "고르지 않은 구성 — 넣지 않음"   # 넣기 계획 · 연결 목록의 까닭 글(「넣을 구성 선택」 에서 뺀 기관 · 단계 · 차년도의 자리)
ALL = "전부"


def _stages(values):
    return [int(n) for n in (values or {}).get("stages") or () if isinstance(n, int) and n > 0]


def _org_rows(values):
    """구분 값의 기관 → [(역할, 이름)] — 주관 · 공동 … (이름이 빈 것은 뺀다 · 같은 이름은 한 번). 수요기업으로 고른 공동(spec_구분_기준 ② §24)의 역할 글은 「수요기업」."""
    seen, out = set(), []
    dm = ((values or {}).get("orgs") or {}).get("demand") or []
    for i, (role, name) in enumerate(P._orgs(values or {"orgs": {}}) if (values or {}).get("orgs") else ()):
        k = P.org_key(name)
        if k and k not in seen:
            seen.add(k)
            out.append(("수요기업" if 0 < i < len(dm) and dm[i] else role, str(name).strip()))
    return out


def stage_of(values, year):
    """전체 차례 차년도 수 → 그 차년도가 든 단계 번호 | None."""
    n = 0
    for i, k in enumerate(_stages(values), 1):
        n += k
        if year <= n:
            return i
    return None


def choices(values):
    """고를 수 있는 값 → {org[{name, role}], stage[{n, name}], year[{n, stage, name}]} — 프로젝트 구성(정리한 꼴)에서. 값이 없으면 모두 빈 목록."""
    st = _stages(values)
    years, n = [], 0
    for i, k in enumerate(st, 1):
        for j in range(1, k + 1):
            n += 1
            years.append({"n": n, "stage": i, "name": f"{n}차년도" + (f"({i}단계 {j}차년도)" if len(st) > 1 else "")})
    return {"org": [{"name": name, "role": role} for role, name in _org_rows(values)], "stage": [{"n": i, "name": f"{i}단계"} for i in range(1, len(st) + 1)], "year": years}


def clean(take, values=None):
    """받은 고른 것 → 정리한 꼴 | None(전부). values 를 주면 그 구성에 있는 값만 받고(없는 값 — ValueError) 그 기준의 값을 모두 골랐으면 열쇠를 뺀다.
    values 없이는 꼴만 본다(저장된 것을 읽을 때 — 구성이 그 사이 바뀌었을 수 있다: 없는 값도 그대로 둔다 · 그 값의 자리는 없으니 아무것도 안 넣는다)."""
    if take is None:
        return None
    if not isinstance(take, dict) or any(k not in DIMS for k in take):
        raise ValueError("넣을 구성의 꼴이 틀립니다 — {org: [기관 이름…], stage: [단계…], year: [차년도…]}")
    C = choices(values) if values else None
    out = {}
    for d in DIMS:
        v = take.get(d)
        if v is None:
            continue
        if not isinstance(v, list) or len(v) > 200:
            raise ValueError(f"넣을 {NAMES[d]}의 꼴이 틀립니다")
        if d == "org":
            got = list(dict.fromkeys(" ".join(str(x).split()) for x in v if isinstance(x, str) and str(x).strip()))
            if len(got) != len(v):
                raise ValueError("넣을 기관은 기관 이름의 목록이어야 합니다")
            have = [c["name"] for c in C["org"]] if C else None
            keys = {P.org_key(x) for x in got}
            if have is not None:
                if any(P.org_key(x) not in {P.org_key(h) for h in have} for x in got):
                    raise ValueError("프로젝트 구성에 없는 기관이 있습니다 — 다시 고르세요")
                got = [h for h in have if P.org_key(h) in keys]   # 구성의 차례 · 구성의 이름으로
        else:
            if any(not isinstance(x, int) or isinstance(x, bool) or x < 1 for x in v):
                raise ValueError(f"넣을 {NAMES[d]}는 번호의 목록이어야 합니다")
            got = sorted(set(v))
            have = [c["n"] for c in C[d]] if C else None
            if have is not None and any(x not in have for x in got):
                raise ValueError(f"프로젝트 구성에 없는 {NAMES[d]}가 있습니다 — 다시 고르세요")
        if not got:
            raise ValueError(f"{NAMES[d]}를 하나는 골라야 합니다(모두 넣으려면 그 기준을 고르지 않은 채 두세요)")
        if have is not None and len(got) == len(have):
            continue   # 그 기준의 값을 모두 골랐다 = 전부
        out[d] = got
    return out or None


class Allowed:
    """그 값의 자리에 넣어도 되나 — 고른 것이 없으면(active 거짓) 늘 참. 값을 모르는 자리(None)는 참(짐작해서 빼지 않는다 — 구분 기준이 걸리지 않은 자리도 그렇다)."""

    def __init__(self, take, values):
        self.take = take or None
        self.active = bool(self.take)
        self.values = values or {}
        t = self.take or {}
        self._org = {P.org_key(x) for x in t["org"]} if "org" in t else None
        self._stage = set(t["stage"]) if "stage" in t else None
        self._year = set(t["year"]) if "year" in t else None

    def org(self, key):
        return self._org is None or key is None or P.org_key(key) in self._org

    def year(self, n):
        if n is None or not isinstance(n, int):
            return True
        if self._year is not None and n not in self._year:
            return False
        return self._stage is None or stage_of(self.values, n) in self._stage

    def stage(self, n):
        if n is None or not isinstance(n, int):
            return True
        if self._stage is not None and n not in self._stage:
            return False
        if self._year is None:
            return True
        return any(stage_of(self.values, y) == n for y in self._year)   # 그 단계의 차년도를 하나도 안 골랐으면 그 단계의 자리도 뺀다

    def ident(self, ident):
        """항목 값(merge_pairs._ident — ("org", 이름 꼴) · ("year", 전체 차례 수) · ("stage", n) · ("raw", …) | None)."""
        if not self.active or not ident:
            return True
        kind, v = ident[0], ident[1]
        return self.org(v) if kind == "org" else self.year(v) if kind == "year" else self.stage(v) if kind == "stage" else True

    def ctx(self, ctx):
        """묶음 · 표의 맥락({"org": 기관 이름 꼴 | None, "year": 전체 차례 수 | None} — 그 묶음을 품은 기관 절 · 차년도 절)."""
        if not self.active or not ctx:
            return True
        return self.org(ctx.get("org")) and self.year(ctx.get("year"))


def allowed(take, values):
    return Allowed(take, values)


def text(take, values=None):
    """한 줄 글 — 「기관: 한국선급 · 가나대 / 차년도: 2차년도」 | 「전부」."""
    if not take:
        return ALL
    C = choices(values) if values else {"org": [], "stage": [], "year": []}
    yname = {c["n"]: c["name"] for c in C["year"]}
    parts = []
    for d in DIMS:
        if d in take:
            v = take[d]
            parts.append(f"{NAMES[d]}: " + " · ".join(str(x) if d == "org" else f"{x}단계" if d == "stage" else yname.get(x, f"{x}차년도") for x in v))
    return " / ".join(parts)


def narrow(view, to_groups, A):
    """연결 목록(view — merge_pairs.pair 의 {"groups", "counts"})을 고른 구성으로 좁힌다(그 자리에서 고침) → 범위 밖이 된 묶음 수.
    묶음 전체가 범위 밖(맥락의 기관 · 차년도가 밖이거나 항목이 모두 밖) = status "outside"(전의 status 는 `was`) · 일부 항목만 밖 = 그 항목의 status "outside". counts 는 다시 세고 `outside` 를 더한다.
    원본에만 있는 묶음(fromOnly)은 그대로 둔다(넣는 자리가 아니다)."""
    if not A.active:
        return 0
    by = {t["key"]: t for t in to_groups}
    n = 0
    for g in view.get("groups") or ():
        t = by.get((g.get("to") or {}).get("key"))
        if t is None:
            continue
        outs = [not A.ident(it.get("ident")) for it in t.get("items") or ()]
        if not A.ctx(g.get("ctx")) or (outs and all(outs)):
            g["was"], g["status"], g["reason"] = g["status"], "outside", OUT
            for it in g.get("items") or ():
                it["status"] = "outside"
            n += 1
        else:
            for it, o in zip(g.get("items") or (), outs):
                if o:
                    it["status"] = "outside"
    c = Counter(g["status"] for g in view.get("groups") or ())
    view["counts"] = {**{k: c.get(k, 0) for k in ("paired", "ambiguous", "toOnly", "fromOnly")}, "outside": c.get("outside", 0)}
    return n
