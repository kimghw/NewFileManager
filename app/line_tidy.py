"""줄 정리 — 줄 끝에서 낱말이 1~2자로 갈린 곳을 장평으로 당기거나 민다(spec/spec_줄정리.md ② §1~§4).

2026-11-23 사용자(이관 결과의 「'선내 데이터 가 / 이드라인'」 · 「실시간 예지보 / 전 가동」 을 보며) "4단계에 줄정리 도구를 넣고 … 5글자 중 1개가 분리되어 있으면
장평을 조금씩 조절해서 … 2자까지는 땡겨서 갖어오고 반대로 다음줄에 3자 이상 넘어 앞에 1,2 자는 장평을 늘려서 보내버려 … 문단의 마지막 줄에 2자인 경우 바로 윗줄을 장평을
줄여서 갖어오고 … 땡긴 글자 총 합이 3자인 경우는 연속해서 … 이 규칙도 관리할 수 있도록 도구에서 볼수 있게".

- **줄 나눔은 한글이 정한 것을 쓴다** — 웹 화면(브라우저 글꼴)의 줄이 아니다. 한글이 끝 쪽까지 조판한 사본의 줄 배치 캐시(hp:linesegarray)를 읽는다(pdf_render.layout_hwpx).
  글자 폭 모형(outline_pos.Measure)은 **얼마나 바꿀지 어림**하는 데만 쓰고, 고친 뒤 한글로 다시 재어 맞았는지 본다(맞지 않으면 1%씩 더 — `Para.observe`).
- 이 파일은 순수 계산 + HwpxDoc 문단 한 곳 고치기(`scale_ratio`)다 — 서버 · 한글 · 저장은 `app/line_tidy_api.py`.
- 글자 수 = 글자(한글 · 영문 · 숫자 — 유니코드 L · N)만 센다. 따옴표 · 괄호 · 쉼표는 세지 않는다.
"""
import copy
import math
import unicodedata

# ---------------------------------------------------------------- 규칙(화면 「도구 설명」 · 대시보드가 이 표로 그린다 — 키 · 기본값 · 범위 · 이름 · 설명)
RULE_DEFS = (
    {"key": "pull", "default": 2, "lo": 1, "hi": 4, "unit": "자", "name": "당기기",
     "text": "낱말이 줄 끝에서 갈렸을 때 다음 줄로 넘어간 조각이 이 글자 수 이하면 윗줄의 장평을 줄여 그 조각을 윗줄로 당깁니다(1자/1자 · 2자/1자 · 3자/1자 · 2자/2자 · 3자/2자)."},
    {"key": "pushHead", "default": 3, "lo": 2, "hi": 10, "unit": "자", "name": "밀기 — 다음 줄 조각",
     "text": "다음 줄로 넘어간 조각이 이 글자 수 이상이고"},
    {"key": "pushTail", "default": 2, "lo": 1, "hi": 4, "unit": "자", "name": "밀기 — 줄 끝 조각",
     "text": "줄 끝에 남은 조각이 이 글자 수 이하면 그 줄의 장평을 늘려 남은 조각을 다음 줄로 보냅니다."},
    {"key": "last", "default": 2, "lo": 0, "hi": 4, "unit": "자", "name": "마지막 줄",
     "text": "문단의 마지막 줄이 이 글자 수 이하면 바로 윗줄의 장평을 줄여 그 줄을 윗줄로 당깁니다(0 = 안 함)."},
    {"key": "chain", "default": 3, "lo": 0, "hi": 6, "unit": "자", "name": "연속 당기기",
     "text": "당긴 뒤 마지막 줄이 짧아지면(「예지보 / 전 가동」) 한 번만 당기되, 한 줄로 당기는 글자의 합이 이 수 이하면 이어서 마지막 줄까지 당깁니다."},
    {"key": "minRatio", "default": 85, "lo": 50, "hi": 99, "unit": "%", "name": "장평 하한",
     "text": "줄일 때 이보다 좁게 하지 않습니다. 더 줄여야 하면 그 자리는 그대로 둡니다."},
    {"key": "maxRatio", "default": 110, "lo": 101, "hi": 150, "unit": "%", "name": "장평 상한",
     "text": "늘릴 때 이보다 넓게 하지 않습니다. 더 늘려야 하면 그 자리는 그대로 둡니다."},
    {"key": "minLine", "default": 8, "lo": 1, "hi": 40, "unit": "자", "name": "고칠 줄의 길이",
     "text": "장평을 바꿀 줄이 이 글자 수보다 짧으면(좁은 표 칸의 머리글 같은 줄) 고치지 않습니다."},
    {"key": "rounds", "default": 6, "lo": 1, "hi": 12, "unit": "번", "name": "한글로 다시 재기",
     "text": "바꾼 뒤 한글로 다시 조판해 맞았는지 보는 횟수의 상한입니다. 맞지 않으면 장평을 1%씩 더 바꿉니다."},
)
DEFAULTS = {d["key"]: d["default"] for d in RULE_DEFS}
_DEF = {d["key"]: d for d in RULE_DEFS}


def clean_rules(body):
    """화면이 보낸 규칙 → 저장 꼴(모든 키 · 정수) — 모르는 키 · 범위 밖 · 정수가 아님은 ValueError(그 키의 이름으로)."""
    if not isinstance(body, dict):
        raise ValueError("규칙은 {키: 값} 이어야 합니다")
    out = dict(DEFAULTS)
    for k, v in body.items():
        d = _DEF.get(k)
        if d is None:
            raise ValueError(f"모르는 규칙: {k}")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
            raise ValueError(f"「{d['name']}」 은 정수여야 합니다")
        v = int(v)
        if not d["lo"] <= v <= d["hi"]:
            raise ValueError(f"「{d['name']}」 은 {d['lo']}~{d['hi']}{d['unit']} 입니다")
        out[k] = v
    return out


def rules_of(saved):
    """저장된 값(일부 · 옛 키 섞임)을 지금 규칙 꼴로 — 못 읽는 값은 기본값."""
    out = dict(DEFAULTS)
    for k, v in (saved or {}).items():
        d = _DEF.get(k)
        if d is not None and isinstance(v, int) and not isinstance(v, bool) and d["lo"] <= v <= d["hi"]:
            out[k] = v
    return out


def rules_text(R):
    """규칙 한 줄 요약(상태 글 · 끝 글)."""
    s = f"당기기 {R['pull']}자 이하 · 밀기 {R['pushTail']}자/{R['pushHead']}자 이상"
    if R["last"]:
        s += f" · 마지막 줄 {R['last']}자 이하"
    return s + f" · 연속 {R['chain']}자까지 · 장평 {R['minRatio']}~{R['maxRatio']}%"


# ---------------------------------------------------------------- 글자 · 줄
def is_letter(ch):
    return unicodedata.category(ch)[0] in "LN"


def letters(s):
    """글자 수 — 한글 · 영문 · 숫자만(따옴표 · 괄호 · 문장 부호 · 빈칸은 안 셈)."""
    return sum(1 for c in s if is_letter(c))


def spans_of(text, breaks):
    """줄 시작 자리(둘째 줄부터 — hwpx_layout.lines) → 줄마다 (시작, 끝)."""
    cuts = [0, *breaks, len(text)]
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def _trim(text, a, b):
    """[a, b) 의 끝 빈칸을 뺀 끝 자리."""
    while b > a and text[b - 1].isspace():
        b -= 1
    return b


def protect(text):
    """첫 줄에서 장평을 바꾸지 않을 첫머리 길이 — 앞 빈칸 + 짧은 첫 토막(레터 「ㅇ」 · 「-」 · 「1)」 …, 4자까지) + 그 뒤 빈칸.
    개요 줄의 둘째 줄은 「글 시작」 에 맞춰 둔 내어쓰기라(outline_conform) 레터와 레터 뒤 빈칸의 폭이 바뀌면 첫 줄 글 시작이 어긋난다."""
    i = 0
    while i < len(text) and text[i].isspace():
        i += 1
    j = i
    while j < len(text) and not text[j].isspace():
        j += 1
    if j == i or j - i > 4 or j >= len(text):
        return i
    while j < len(text) and text[j].isspace():
        j += 1
    return j


def issue_at(text, spans, k, R):
    """줄 k 와 k+1 사이의 갈림 → {kind: pull | push, line: k, a, b, cut(줄 끝 조각의 시작), at(다음 줄 조각의 끝)} | None(빈칸에서 나뉨 · 규칙 밖의 갈림)."""
    a0, a1 = spans[k]
    b0, b1 = spans[k + 1]
    x, y = text[a0:a1], text[b0:b1]
    if not x or not y or x[-1] == "\n" or not (is_letter(x[-1]) and is_letter(y[0])):
        return None
    cut = a1
    while cut > a0 and not text[cut - 1].isspace():
        cut -= 1
    at = b0
    while at < b1 and not text[at].isspace():
        at += 1
    a, b = letters(text[cut:a1]), letters(text[b0:at])
    if b <= R["pull"]:
        return {"kind": "pull", "line": k, "a": a, "b": b, "cut": cut, "at": at}
    if b >= R["pushHead"] and a <= R["pushTail"]:
        return {"kind": "push", "line": k, "a": a, "b": b, "cut": cut, "at": at}
    return None


def last_issue(text, spans, R):
    """마지막 줄이 R.last 글자 이하 → {kind: last, line: n-2, b, at(내용 끝)} | None. 앞 줄이 강제 줄 바꿈으로 끝나면(쓴 사람이 나눈 줄) 아니다."""
    if len(spans) < 2 or not R["last"]:
        return None
    s, e = spans[-1]
    b = letters(text[s:e])
    p0, p1 = spans[-2]
    if not 0 < b <= R["last"] or text[p0:p1].endswith("\n"):
        return None
    return {"kind": "last", "line": len(spans) - 2, "a": 0, "b": b, "cut": s, "at": _trim(text, s, e)}


def issues(text, spans, R, start=0):
    """규칙에 걸린 자리 — 위에서 아래로(줄 k 의 갈림 · 마지막 줄)."""
    out = [x for k in range(start, len(spans) - 1) if (x := issue_at(text, spans, k, R))]
    last = last_issue(text, spans, R)
    if last and last["line"] >= start and not any(x["line"] == last["line"] and x["kind"] == "pull" for x in out):
        out.append(last)
    return out


def lines_text(text, spans):
    return [text[a:b] for a, b in spans]


# ---------------------------------------------------------------- 문단 하나의 시도 · 확인
WHY = {"short": "줄이 짧음(좁은 칸)", "limit": "장평 한도", "measure": "잴 수 없는 글자", "worse": "나아지지 않음", "rounds": "다시 재기 횟수",
       "moved": "윗줄이 움직임", "chain": "연속 당기기 한도"}


class Para:
    """문단 하나 — 위에서 아래로 한 자리씩: 어림한 장평으로 시도(trial) → 한글 줄로 확인(observe) → 맞으면 다음 자리 · 아니면 1%씩 더 · 한도면 그 자리를 둔다.
    ops 는 늘 **처음 문서** 기준의 (범위, 배율) 이다 — 고칠 때는 처음 문단에 ops 를 모두 다시 입힌다(배율이 겹쳐 쌓이지 않게)."""

    def __init__(self, idx, text, spans, R, width, ratios):
        """width(a, b) → 처음 서식으로 잰 [a, b) 의 폭 | None · ratios(a, b) → (가장 좁은, 가장 넓은) 지금 장평(%)."""
        self.idx, self.text, self.R, self.width, self.ratios = idx, text, R, width, ratios
        self.spans0 = self.spans = spans
        self.ops, self.trial, self.gave, self.left = [], None, set(), []
        self.pf = protect(text)
        self.base = len(issues(text, spans, R))
        self.next_from = 0
        self._plan()

    # ---- 고를 자리
    def _give(self, it, why):
        key = (it["kind"], self.spans[it["line"]][0])
        if key not in self.gave:
            self.gave.add(key)
            self.left.append({"kind": it["kind"], "line": it["line"], "a": it["a"], "b": it["b"], "why": why,
                              "at": self.text[max(0, it["cut"] - 6):it["at"] + 2]})

    def _plan(self):
        self.trial = None
        for it in issues(self.text, self.spans, self.R, self.next_from):
            if (it["kind"], self.spans[it["line"]][0]) in self.gave:
                continue
            op = self._op(it)
            if isinstance(op, str):
                self._give(it, op)
                continue
            self.trial = op
            return

    def _w(self, a, b):
        return self.width(a, b) if b > a else 0.0

    def _op(self, it):
        T, R, sp = self.text, self.R, self.spans
        k = it["line"]
        s, e = sp[k]
        if any(o["s"] == s for o in self.ops):   # 이미 고친 줄에 또 — 한 번만(사용자 「1번만 실행」 · 미리 본 연속 당기기는 한 op 로 합쳐 있다) · 배율이 겹쳐 쌓이지 않게
            return "chain"
        if letters(T[s:e]) < R["minLine"]:
            return "short"
        rs = s + (self.pf if s == 0 else 0)   # 첫 줄의 첫머리(레터 · 레터 뒤 빈칸)는 그대로
        F = self._w(s, rs)
        if it["kind"] == "push":
            cut = it["cut"]
            if cut <= rs:
                return "short"
            W_all, S, wc = self._w(s, e + 1), self._w(s, cut), self._w(cut, cut + 1)
            if None in (W_all, S, wc, F) or S - F <= 0:
                return "measure"
            pct = max(101, math.ceil(100 * (W_all - wc - F) / (S - F)))
            hi = math.floor(100 * R["maxRatio"] / self.ratios(rs, cut)[1])
            if pct > hi:
                return "limit"
            return {"kind": "push", "s": s, "rs": rs, "re": cut, "cut": cut, "pct": pct, "lo": 100, "hi": hi + 1, "b": it["a"], "line": k, "it": it}
        at, b, kind = it["at"], it["b"], it["kind"]
        if kind == "pull" and k + 2 == len(sp) and R["last"]:   # 당긴 뒤 남는 마지막 줄(「예지보 / 전 가동」 → 「가동」)
            rest = letters(T[at:sp[-1][1]])
            if 0 < rest <= R["last"]:
                if b + rest <= R["chain"]:
                    at, b, kind = _trim(T, *sp[-1]), b + rest, "pull+last"
                else:
                    self.left.append({"kind": "last", "line": k + 1, "a": 0, "b": rest, "why": "chain", "at": T[at:sp[-1][1]]})
        W_T, W_N = self._w(s, _trim(T, s, e)), self._w(s, at)
        if None in (W_T, W_N, F) or W_N - F <= 0:
            return "measure"
        pct = min(99, math.floor(100 * (W_T - F) / (W_N - F)))
        lo = math.ceil(100 * R["minRatio"] / self.ratios(rs, at)[0])
        if pct < lo:
            return "limit"
        return {"kind": kind, "s": s, "rs": rs, "re": at, "at": at, "pct": pct, "lo": lo - 1, "hi": 100, "b": b, "line": k, "it": it}

    def all_ops(self):
        return self.ops + ([self.trial] if self.trial else [])

    # ---- 한글 줄로 확인
    def _line(self, spans, s):
        return next((i for i, (a, _) in enumerate(spans) if a == s), None)

    def observe(self, spans):
        """ops(+시도)를 입힌 문단의 한글 줄 → 시도가 맞았나 보고 다음 시도를 정한다. 시도가 없으면 아무 일도 안 한다."""
        op = self.trial
        if op is None:
            return
        k = self._line(spans, op["s"])
        if k is None or spans[:k] != self.spans[:k]:   # 윗줄이 움직임(일어나면 안 됨 — 그 문단의 시도를 거둔다)
            return self._fail(op, "moved")
        e = spans[k][1]
        clean = k + 1 >= len(spans) or issue_at(self.text, spans, k, self.R) is None
        if op["kind"] == "push":
            if e > op["cut"]:   # 아직 안 넘어감 — 더 넓게
                op["lo"] = op["pct"]
                return self._step(op, +1)
            if clean:
                return self._ok(op, spans, k + 1)
            op["hi"] = op["pct"]   # 더 넘어가 새 갈림 — 덜 넓게
            return self._step(op, -1)
        if e < op["at"]:   # 아직 안 올라옴 — 더 좁게
            op["hi"] = op["pct"]
            return self._step(op, -1)
        if clean:
            return self._ok(op, spans, k)
        op["lo"] = op["pct"]   # 더 올라와 새 갈림 — 덜 좁게
        return self._step(op, +1)

    def _step(self, op, d):
        nxt = op["pct"] + d
        if not op["lo"] < nxt < op["hi"]:
            return self._fail(op, "limit")
        op["pct"] = nxt

    def _ok(self, op, spans, nxt):
        self.ops.append(op)
        self.spans, self.next_from = spans, nxt
        self._plan()

    def _fail(self, op, why):
        self._give(op["it"], why)
        self._plan()

    # ---- 끝
    def finish(self):
        """시도를 거두고(확인 못 함) 나아졌는지 본다 → 남길 ops(나아지지 않았으면 빈 것)."""
        if self.trial is not None:
            self._give(self.trial["it"], "rounds")
            self.trial = None
        if self.ops and len(issues(self.text, self.spans, self.R)) >= self.base:
            self.left.append({"kind": "", "line": 0, "a": 0, "b": 0, "why": "worse", "at": ""})
            self.ops, self.spans = [], self.spans0
        return self.ops


# ---------------------------------------------------------------- 문서 고치기
def _hh(tag):
    return "{http://www.hancom.co.kr/hwpml/2011/head}" + tag


LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def scale_ratio(doc, p, start, end, pct):
    """HwpxDoc 문단 p 의 [start, end) 글자(블록 글 자리)의 장평을 pct% 배로(언어마다 지금 값 × pct/100 · 50~200) — 런을 나누고 새 글자 모양을 들인다.
    표 · 그림 같은 개체가 든 런은 건드리지 않는다. → 바꾼 런 수."""
    from app.hwpx_doc import OBJECTS, RUN
    if end <= start:
        return 0
    doc._boundary(p, end)
    doc._boundary(p, start)
    made, pos, n = {}, 0, 0
    for r in p.iterchildren(RUN):
        k = sum(doc._clen(c) for c in r)
        if k and start <= pos and pos + k <= end and not any(c.tag in OBJECTS for c in r):
            old = r.get("charPrIDRef", "0")
            if old not in made:
                src = doc._defs["charPr"].get(old)
                if src is None:
                    raise ValueError(f"글자 모양 {old} 정의가 없습니다")
                c = copy.deepcopy(src)
                e = c.find(_hh("ratio"))
                if e is None:   # 차례는 fontRef 바로 뒤(hwpx_format.CHAR_ORDER — OWPML)
                    e = c.makeelement(_hh("ratio"), {x: "100" for x in LANGS})
                    fr = c.find(_hh("fontRef"))
                    (fr.addnext(e) if fr is not None else c.insert(0, e))
                for attr in list(e.attrib):
                    e.set(attr, str(max(50, min(200, round(int(e.get(attr) or 100) * pct / 100)))))
                made[old] = doc._add_def("charPr", c)
            if made[old] != old:
                r.set("charPrIDRef", made[old])
                n += 1
        pos += k
    doc._tidy(p)
    doc._drop_cache(p)
    doc._touch(p)
    return n
