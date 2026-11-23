"""줄 정리 — 줄 끝에서 낱말이 1~2자로 갈린 곳을 자간으로 당기거나 민다(spec/spec_줄정리.md ② §1~§4).

2026-11-23 사용자(이관 결과의 「'선내 데이터 가 / 이드라인'」 · 「실시간 예지보 / 전 가동」 을 보며) "4단계에 줄정리 도구를 넣고 … 5글자 중 1개가 분리되어 있으면
장평을 조금씩 조절해서 … 2자까지는 땡겨서 갖어오고 반대로 다음줄에 3자 이상 넘어 앞에 1,2 자는 장평을 늘려서 보내버려 … 문단의 마지막 줄에 2자인 경우 바로 윗줄을 장평을
줄여서 갖어오고 … 땡긴 글자 총 합이 3자인 경우는 연속해서 … 이 규칙도 관리할 수 있도록 도구에서 볼수 있게".

- **줄 나눔은 한글이 정한 것을 쓴다** — 웹 화면(브라우저 글꼴)의 줄이 아니다. 한글이 끝 쪽까지 조판한 사본의 줄 배치 캐시(hp:linesegarray)를 읽는다(pdf_render.layout_hwpx).
  글자 폭 모형(outline_pos.Measure)은 **얼마나 바꿀지 어림**하는 데만 쓰고, 고친 뒤 한글로 다시 재어 맞았는지 본다(맞지 않으면 1%씩 더 — `Para.observe`).
- **바꾸는 것은 자간이다**(같은 날 사용자(한글에서 장평 96% 인 줄을 보며) "이 부분들 폰트가 좀 이상한거 같은데" → 답 「자간으로 당기기」 — 처음에는 사용자 말대로 장평이었다):
  장평은 글자 모양을 눌러 그 줄만 글꼴이 달라 보인다 · 자간은 글자 모양은 그대로 두고 글자 사이만 바꾼다. 계산의 배율(pct — 그 범위의 폭을 몇 % 로)은 전과 같고, 문서에는
  자간 = (100 + 지금 자간) × pct ÷ 100 − 100 으로 입힌다(`scale_spacing` — 한글의 글자 나아감 = 글자 폭 × 장평 × (1 + 자간)). 전에 장평으로 고친 줄은 그 장평이 문서에 있다는 근거가 설 때만 반영 때 되돌린다(`ratio_proof` · `restore`).
- 이 파일은 순수 계산 + HwpxDoc 문단 한 곳 고치기(`scale_spacing`)다 — 서버 · 한글 · 저장은 `app/line_tidy_api.py`.
- 글자 수 = 글자(한글 · 영문 · 숫자 — 유니코드 L · N)만 센다. 따옴표 · 괄호 · 쉼표는 세지 않는다. 규칙에 견주는 조각 · 마지막 줄의 수는 그 안에 통째로 든 괄호의 글자도 뺀다(`count`).
- **쪽에 걸친 줄**(② §8 — 같은 날 사용자 "페이지에 1개 문단의 1줄이 걸쳐 있는 경우 해당 페이지의 공백줄을 높이를 일부 조금씩 조정해서 한 페이지 안에 들어 가도록"):
  자간 걸음이 끝난 뒤의 둘째 걸음 — 문단이 두 쪽에 나뉘었고 다음 쪽으로 넘어간 줄이 규칙(`pageTail`) 이하면 그 쪽의 빈 줄(글 없는 문단) 높이를 같은 비율로 조금씩 낮춰 당긴다.
  쪽 나눔도 한글의 줄 자리(lineseg 의 vertpos — 쪽마다 · 쪽에 걸쳐 나뉜 표 칸에서는 이어지는 쪽마다 0 부터)로 읽고, 낮춘 뒤 한글로 다시 재어 확인한다(`Pages` · `scale_height`).
"""
import copy
import functools
import math
import unicodedata

# ---------------------------------------------------------------- 규칙(화면 「도구 설명」 · 대시보드가 이 표로 그린다 — 키 · 기본값 · 범위 · 이름 · 설명)
RULE_DEFS = (
    {"key": "pull", "default": 2, "lo": 1, "hi": 4, "unit": "자", "name": "당기기",
     "text": "낱말이 줄 끝에서 갈렸을 때 다음 줄로 넘어간 조각이 이 글자 수 이하면 윗줄의 자간을 줄여 그 조각을 윗줄로 당깁니다(1자/1자 · 2자/1자 · 3자/1자 · 2자/2자 · 3자/2자)."},
    {"key": "pushHead", "default": 3, "lo": 2, "hi": 10, "unit": "자", "name": "밀기 — 다음 줄 조각",
     "text": "다음 줄로 넘어간 조각이 이 글자 수 이상이고"},
    {"key": "pushTail", "default": 2, "lo": 1, "hi": 4, "unit": "자", "name": "밀기 — 줄 끝 조각",
     "text": "줄 끝에 남은 조각이 이 글자 수 이하면 그 줄의 자간을 늘려 남은 조각을 다음 줄로 보냅니다."},
    {"key": "last", "default": 2, "lo": 0, "hi": 4, "unit": "자", "name": "마지막 줄",
     "text": "문단의 마지막 줄이 이 글자 수 이하면 바로 윗줄의 자간을 줄여 그 줄을 윗줄로 당깁니다(0 = 안 함)."},
    {"key": "chain", "default": 3, "lo": 0, "hi": 6, "unit": "자", "name": "연속 당기기",
     "text": "당긴 뒤 마지막 줄이 짧아지면(「예지보 / 전 가동」) 한 번만 당기되, 한 줄로 당기는 글자의 합이 이 수 이하면 이어서 마지막 줄까지 당깁니다."},
    {"key": "minSpace", "default": -15, "lo": -50, "hi": -1, "unit": "%", "name": "자간 하한",
     "text": "줄일 때 자간을 이보다 좁게 하지 않습니다(이미 좁혀 둔 글은 그만큼 덜 줄입니다). 더 줄여야 하면 그 자리는 그대로 둡니다."},
    {"key": "maxSpace", "default": 10, "lo": 1, "hi": 50, "unit": "%", "name": "자간 상한",
     "text": "늘릴 때 자간을 이보다 넓게 하지 않습니다. 더 늘려야 하면 그 자리는 그대로 둡니다."},
    {"key": "minLine", "default": 8, "lo": 1, "hi": 40, "unit": "자", "name": "고칠 줄의 길이",
     "text": "자간을 바꿀 줄이 이 글자 수보다 짧으면(좁은 표 칸의 머리글 같은 줄) 고치지 않습니다."},
    {"key": "cellWord", "default": 3, "lo": 0, "hi": 6, "unit": "자", "name": "표 칸 — 짧은 낱말",
     "text": "표 칸에서 이 글자 수 이하의 낱말(「조류계」 · 「트리거」 — 가운뎃점 · 괄호 · 빗금 사이의 토막도 낱말)이 줄 끝에서 갈리면, 줄이 「고칠 줄의 길이」 보다 짧아도 자간으로 붙입니다(0 = 안 함)."},
    {"key": "rounds", "default": 6, "lo": 1, "hi": 12, "unit": "번", "name": "한글로 다시 재기",
     "text": "바꾼 뒤 한글로 다시 조판해 맞았는지 보는 횟수의 상한입니다. 맞지 않으면 자간을 조금씩(그 줄의 폭을 1%씩) 더 바꿉니다."},
    {"key": "pageTail", "default": 1, "lo": 0, "hi": 3, "unit": "줄", "name": "쪽에 걸친 줄",
     "text": "문단이 두 쪽에 나뉘어 있고 다음 쪽으로 넘어간 줄이 이 줄 수 이하면, 그 쪽에 있는 빈 줄의 높이를 조금씩 낮춰 넘어간 줄을 그 쪽으로 당깁니다(0 = 안 함)."},
    {"key": "blankMin", "default": 60, "lo": 30, "hi": 95, "unit": "%", "name": "빈 줄 높이 하한",
     "text": "빈 줄의 높이(글자 크기)를 처음의 이 비율보다 낮추지 않습니다. 더 낮춰야 하면 그 문단은 그대로 둡니다."},
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
    s += f" · 연속 {R['chain']}자까지 · 자간 {R['minSpace']}~+{R['maxSpace']}%"
    if R.get("cellWord"):
        s += f" · 표 칸 낱말 {R['cellWord']}자 이하"
    if R.get("pageTail"):
        s += f" · 쪽에 걸친 줄 {R['pageTail']}줄 이하(빈 줄 높이 {R['blankMin']}% 까지)"
    return s


# ---------------------------------------------------------------- 글자 · 줄
def is_letter(ch):
    return unicodedata.category(ch)[0] in "LN"


def letters(s):
    """글자 수 — 한글 · 영문 · 숫자만(따옴표 · 괄호 · 문장 부호 · 빈칸은 안 셈)."""
    return sum(1 for c in s if is_letter(c))


_OPEN, _CLOSE = "(（", ")）"


@functools.lru_cache(maxsize=512)
def _pairs(text):
    """짝이 맞는 괄호의 (여는 자리, 닫는 자리)들 — 짝이 없는 괄호는 안 본다."""
    out, open_at = [], []
    for i, c in enumerate(text):
        if c in _OPEN:
            open_at.append(i)
        elif c in _CLOSE and open_at:
            out.append((open_at.pop(), i))
    return tuple(out)


def count(text, a, b):
    """조각 · 줄 [a, b) 의 글자 수 — 규칙에 견주는 수(② §1). 그 안에 **통째로 든** 괄호의 글자는 빼고 센다(「약(MOU)」 = 1자 — 2026-11-23 사용자 "() 빼고 계산해줘") ·
    줄을 넘어 짝지어진 괄호는 빼지 않는다(「(보안경, 안전모 / 등) 착용」 의 「등) 착용」 = 3자) · 괄호 밖에 글자가 없으면(「(MOU)」) 모두 센다."""
    skip = set()
    for o, c in _pairs(text):
        if a <= o and c < b:
            skip.update(range(o, c + 1))
    return sum(1 for i in range(a, b) if i not in skip and is_letter(text[i])) or letters(text[a:b])


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
    """첫 줄에서 자간을 바꾸지 않을 첫머리 길이 — 앞 빈칸 + 짧은 첫 토막(레터 「ㅇ」 · 「-」 · 「1)」 …, 4자까지) + 그 뒤 빈칸.
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


def _cell_issue(text, a0, a1, b0, b1, R):
    """표 칸의 짧은 낱말(② §2 `cellWord`) — 갈린 곳 양쪽의 글자 토막(가운뎃점 · 괄호 · 빗금에서 끊음)의 합이 cellWord 이하 → 갈림 | None.
    당기는 토막은 뒤에 붙은 닫는 문장 부호까지(「이벤 / 트)」 의 「트)」 — 「)」 가 혼자 남지 않게)."""
    c0 = a1
    while c0 > a0 and is_letter(text[c0 - 1]):
        c0 -= 1
    c1 = b0
    while c1 < b1 and is_letter(text[c1]):
        c1 += 1
    a, b = a1 - c0, c1 - b0
    if a + b > R["cellWord"]:
        return None
    at = c1
    while at < b1 and not text[at].isspace() and not is_letter(text[at]) and unicodedata.category(text[at]) != "Ps":
        at += 1
    if b <= R["pull"]:
        return {"kind": "pull", "a": a, "b": b, "cut": c0, "at": at, "cell": True}
    if a <= R["pushTail"]:
        return {"kind": "push", "a": a, "b": b, "cut": c0, "at": at, "cell": True}
    return None


def issue_at(text, spans, k, R, cell=False):
    """줄 k 와 k+1 사이의 갈림 → {kind: pull | push, line: k, a, b, cut(줄 끝 조각의 시작), at(다음 줄 조각의 끝)[, cell]} | None(빈칸에서 나뉨 · 규칙 밖의 갈림).
    cell = 표 칸의 문단 — 짧은 낱말은 `_cell_issue` 가 먼저 본다(그 갈림은 「고칠 줄의 길이」 와 무관: `cell` 표시)."""
    a0, a1 = spans[k]
    b0, b1 = spans[k + 1]
    x, y = text[a0:a1], text[b0:b1]
    if not x or not y or x[-1] == "\n" or not (is_letter(x[-1]) and is_letter(y[0])):
        return None
    if cell and R.get("cellWord"):
        got = _cell_issue(text, a0, a1, b0, b1, R)
        if got:
            return {**got, "line": k}
    cut = a1
    while cut > a0 and not text[cut - 1].isspace():
        cut -= 1
    at = b0
    while at < b1 and not text[at].isspace():
        at += 1
    a, b = count(text, cut, a1), count(text, b0, at)
    if b <= R["pull"]:
        return {"kind": "pull", "line": k, "a": a, "b": b, "cut": cut, "at": at}
    if b >= R["pushHead"] and a <= R["pushTail"] and cut > a0:   # 줄 전체가 그 조각이면(「연속(트리」 — 괄호 안을 빼면 2자) 밀 수 없다
        return {"kind": "push", "line": k, "a": a, "b": b, "cut": cut, "at": at}
    return None


def last_issue(text, spans, R):
    """마지막 줄이 R.last 글자 이하 → {kind: last, line: n-2, b, at(내용 끝)} | None. 앞 줄이 강제 줄 바꿈으로 끝나면(쓴 사람이 나눈 줄) 아니다."""
    if len(spans) < 2 or not R["last"]:
        return None
    s, e = spans[-1]
    b = count(text, s, e)
    p0, p1 = spans[-2]
    if not 0 < b <= R["last"] or text[p0:p1].endswith("\n"):
        return None
    return {"kind": "last", "line": len(spans) - 2, "a": 0, "b": b, "cut": s, "at": _trim(text, s, e)}


def issues(text, spans, R, start=0, cell=False):
    """규칙에 걸린 자리 — 위에서 아래로(줄 k 의 갈림 · 마지막 줄)."""
    out = [x for k in range(start, len(spans) - 1) if (x := issue_at(text, spans, k, R, cell))]
    last = last_issue(text, spans, R)
    if last and last["line"] >= start and not any(x["line"] == last["line"] and x["kind"] == "pull" for x in out):
        out.append(last)
    return out


def lone(text, spans):
    """낱말 가운데서 갈렸고 한쪽 토막이 한 글자인 곳(가운뎃점 · 괄호 · 빗금에서 끊은 토막 — 「조류 / 계」 · 「기 / 반」)의 다음 줄 시작 자리들."""
    out = set()
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        if a1 > a0 and b1 > b0 and is_letter(text[a1 - 1]) and is_letter(text[b0]):
            if not (a1 - 1 > a0 and is_letter(text[a1 - 2])) or not (b0 + 1 < b1 and is_letter(text[b0 + 1])):
                out.add(b0)
    return out


def lines_text(text, spans):
    return [text[a:b] for a, b in spans]


# ---------------------------------------------------------------- 문단 하나의 시도 · 확인
WHY = {"short": "줄이 짧음(좁은 칸)", "limit": "자간 한도", "measure": "잴 수 없는 글자", "worse": "나아지지 않음", "rounds": "다시 재기 횟수",
       "moved": "윗줄이 움직임", "chain": "연속 당기기 한도"}
PAGE_WHY = {"noBlank": "그 쪽에 빈 줄 없음", "floor": "빈 줄 높이 하한", "rounds": "다시 재기 횟수"}   # 쪽에 걸친 줄을 그대로 둔 까닭(② §8)


class Para:
    """문단 하나 — 위에서 아래로 한 자리씩: 어림한 배율(그 범위의 폭을 몇 % 로 — 문서에는 자간으로 입힌다)로 시도(trial) → 한글 줄로 확인(observe) → 맞으면 다음 자리 · 아니면 1%씩 더 · 한도면 그 자리를 둔다.
    ops 는 늘 **처음 문서** 기준의 (범위, 배율) 이다 — 고칠 때는 처음 문단에 ops 를 모두 다시 입힌다(배율이 겹쳐 쌓이지 않게)."""

    def __init__(self, idx, text, spans, R, width, spaces, cell=False):
        """width(a, b) → 처음 서식으로 잰 [a, b) 의 폭 | None · spaces(a, b) → (가장 좁은, 가장 넓은) 지금 자간(%) · cell = 표 칸의 문단(② §2 `cellWord`)."""
        self.idx, self.text, self.R, self.width, self.spaces, self.cell = idx, text, R, width, spaces, cell
        self.spans0 = self.spans = spans
        self.ops, self.trial, self.gave, self.left = [], None, set(), []
        self.pf = protect(text)
        self.base = len(issues(text, spans, R, cell=cell))
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
        for it in issues(self.text, self.spans, self.R, self.next_from, self.cell):
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
        if letters(T[s:e]) < R["minLine"] and not it.get("cell"):
            return "short"
        rs = s + (self.pf if s == 0 else 0)   # 첫 줄의 첫머리(레터 · 레터 뒤 빈칸)는 그대로
        # 앞에서 고친 범위와 겹치지 않게 — 밀기가 어림보다 더 밀리면 새 줄이 앞 범위 안에서 시작한다: 그 글자에 배율이 두 번 걸려 자간이 한도를 넘는다(0 → +4 → +14%: astra 2026-11-23)
        rs = max([rs] + [o["re"] for o in self.ops if o["rs"] < e and o["re"] > rs])
        if rs >= e:
            return "chain"
        F = self._w(s, rs)
        if it["kind"] == "push":
            cut = it["cut"]
            if cut <= rs:
                return "short"
            W_all, S, wc = self._w(s, e + 1), self._w(s, cut), self._w(cut, cut + 1)
            if None in (W_all, S, wc, F) or S - F <= 0:
                return "measure"
            pct = max(101, math.ceil(100 * (W_all - wc - F) / (S - F)))
            hi = pct_limit(self.spaces(rs, cut)[1], R["maxSpace"], up=True)   # 배율의 상한 = 적힐 자간이 상한에 닿는 곳
            if pct > hi:
                if not it.get("cell") or hi <= 100:
                    return "limit"
                pct = hi   # 표 칸 — 어림이 거친 좁은 줄이라 상한에서 한 번 재어 본다(맞지 않으면 「자간 한도」)
            return {"kind": "push", "s": s, "rs": rs, "re": cut, "cut": cut, "pct": pct, "lo": 100, "hi": hi + 1, "b": it["a"], "line": k, "it": it}
        at, b, kind = it["at"], it["b"], it["kind"]
        if kind == "pull" and k + 2 == len(sp) and R["last"]:   # 당긴 뒤 남는 마지막 줄(「예지보 / 전 가동」 → 「가동」)
            rest = count(T, at, sp[-1][1])
            if 0 < rest <= R["last"]:
                if b + rest <= R["chain"]:
                    at, b, kind = _trim(T, *sp[-1]), b + rest, "pull+last"
                else:
                    self.left.append({"kind": "last", "line": k + 1, "a": 0, "b": rest, "why": "chain", "at": T[at:sp[-1][1]]})
        W_T, W_N = self._w(s, _trim(T, s, e)), self._w(s, at)
        if None in (W_T, W_N, F) or W_N - F <= 0:
            return "measure"
        pct = min(99, math.floor(100 * (W_T - F) / (W_N - F)))
        if at <= rs:
            return "chain"
        lo = pct_limit(self.spaces(rs, at)[0], R["minSpace"], up=False)   # 배율의 하한 = 적힐 자간이 하한에 닿는 곳(이미 좁힌 글은 덜 줄인다)
        if pct < lo:
            # 어림(W_T / W_N)은 줄이 꽉 찼다고 본 값이라 실제보다 더 줄인다 — 줄 끝에 남은 자리는 다음 줄 첫 글자의 폭보다 작으니(그 글자가 안 들어가 넘어갔다)
            # 그만큼 남았다고 봐도 하한에 못 미치면 「자간 한도」 · 아니면 하한에서 한 번 재어 본다(좁은 표 칸에서 어림이 크게 빗나간다 — 2026-11-23 「연속(트리 / 거」)
            w1 = self._w(e, e + 1) if e < len(T) else None
            if w1 is None or lo > 99 or math.floor(100 * (W_T + w1 - F) / (W_N - F)) < lo:
                return "limit"
            pct = lo
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
        clean = k + 1 >= len(spans) or issue_at(self.text, spans, k, self.R, self.cell) is None
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
        if self.ops and self._worse():
            self.left.append({"kind": "", "line": 0, "a": 0, "b": 0, "why": "worse", "at": ""})
            self.ops, self.spans = [], self.spans0
        return self.ops

    def _worse(self):
        """고친 뒤가 나아지지 않았나 — 규칙에 걸린 자리 수가 줄지 않으면. 표 칸은 그것에 더해 한 글자만 갈라진 자리(`lone`)가 줄지 않았는데 새 자리에 생겼으면
        (「AI 플랫폼 기 / 반 … 운항 / 지원」 → 「기반 … 운항지 / 원」 — 걸린 자리는 2 → 1 이지만 한 글자 갈림을 옮겨 놓았을 뿐) 나아지지 않은 것."""
        if len(issues(self.text, self.spans, self.R, cell=self.cell)) >= self.base:
            return True
        if not self.cell:
            return False
        was, now = lone(self.text, self.spans0), lone(self.text, self.spans)
        return bool(now - was) and len(now) >= len(was)


# ---------------------------------------------------------------- 쪽에 걸친 줄(② §8) — 줄 자리 = 한글의 lineseg (vertpos, vertsize, spacing)
def page_breaks(segs):
    """문단의 줄 자리 [(vertpos, vertsize, spacing)] → 새 쪽에서 시작하는 줄의 차례들. 줄 자리가 위로 되돌아간 곳이 쪽 나눔이다 —
    vertpos 는 쪽(단)마다, 쪽에 걸쳐 나뉜 표 칸에서는 이어지는 쪽마다 0 부터 다시 센다(2026-11-23 한글 2020 실측 — references/한글_문단모양_줄나눔.md 「쪽 나눔 읽기」)."""
    return [k for k in range(1, len(segs)) if segs[k][0] < segs[k - 1][0]]


def page_issue(segs, R):
    """문단 하나 → {k(넘어간 첫 줄), tail(넘어간 줄 수), need(넘어간 줄이 윗쪽에 들어가려면 낮춰야 할 높이 — 넉넉히: 윗쪽에 남은 자리를 0 으로 셈)} |
    None(쪽에 안 걸침 · 넘어간 줄이 규칙보다 많음 · 세 쪽 넘게 걸침)."""
    if not R.get("pageTail") or len(segs) < 2:
        return None
    br = page_breaks(segs)
    if len(br) != 1:
        return None
    k = br[0]
    tail = len(segs) - k
    if tail > R["pageTail"]:
        return None
    return {"k": k, "tail": tail, "need": sum(max(0, segs[j - 1][2]) + segs[j][1] for j in range(k, len(segs)))}


def page_blanks(flow, at):
    """flow = 같은 흐름(본문 · 표 칸 하나)의 문단들 [{"segs", "blank", "obj"}] · at = 쪽에 걸친 문단의 자리 → 그 문단 위, **같은 쪽**에 있는 빈 줄의 자리들(아래에서 위로).
    위 문단의 마지막 줄 자리가 아래 문단의 첫 줄 자리보다 위가 아니면 앞 쪽이다 — 거기서 멈춘다. 쪽에 걸친 윗 문단(꼬리만 이 쪽) · 쪽을 넘는 개체 문단(여러 쪽 표)에서도 멈춘다."""
    out, nxt = [], flow[at]["segs"][0][0]
    for i in range(at - 1, -1, -1):
        q = flow[i]
        segs = q["segs"]
        if not segs:
            break
        vp, vs, _ = segs[-1]
        if vp >= nxt or page_breaks(segs) or (q["obj"] and vp + vs > nxt):
            break
        if q["blank"] and len(segs) == 1:
            out.append(i)
        nxt = segs[0][0]
    return out


def blank_scale(need, pitches, cur, floor, force=False):
    """need = 낮춰야 할 높이 · pitches = 빈 줄마다 지금 줄 높이(줄 + 줄 사이) · cur = 빈 줄마다 지금 배율(처음 높이의 %) · floor = 하한(%)
    → 빈 줄마다 새 배율 — 모두 같은 비율로 조금씩(하한보다 낮게는 안 함 · 올리지 않음). force = 하한까지 한 번에(어림이 모자랐을 때). 더 낮출 수 없으면 None."""
    total = sum(pitches)
    if total <= 0:
        return None
    f = 0.0 if force else max(0.0, 1 - need / total)
    new = [min(c, max(floor, math.floor(c * f))) for c in cur]
    return None if new == list(cur) else new


class Pages:
    """쪽에 걸친 줄 — 문서 전체의 시도와 확인(② §8). 빈 줄의 배율(scale — 처음 높이의 %)을 정하고(`step`), 부르는 쪽이 그 배율을 사본에 입혀 한글로 다시 잰 흐름을 다시 넘긴다.
    쪽은 서로 닿는다(윗쪽에서 한 줄을 당기면 아래 쪽들이 한 줄씩 올라온다) — 그래서 걸린 문단을 한 번에 모두 시도하고, 다시 잰 줄로 문단마다 「아직 걸쳐 있나」 만 본다.
    flows = [[{"idx", "segs", "blank", "obj", "ok"}…]…] — 흐름(본문 · 표 칸)마다 문서 차례의 문단. ok = 볼 문단(블록 문단 · 개체 없음)."""

    def __init__(self, R):
        self.R = R
        self.scale = {}      # 빈 줄 idx → 배율(%) — 100 이 아닌 것만
        self.tries = {}      # 걸친 문단 idx → {"prev": {빈 줄: 전 배율}, "want": {빈 줄: 새 배율}, "tail", "forced"} — 다시 재기를 기다리는 시도
        self.fixed = {}      # 걸친 문단 idx → {"tail", "blanks": {빈 줄: 배율}}
        self.gave = {}       # 걸친 문단 idx → 까닭(PAGE_WHY 의 키)
        self.first = None    # 처음에 걸려 있던 문단 수

    def _issues(self, flows):
        for flow in flows:
            for at, q in enumerate(flow):
                if q["ok"] and not q["blank"]:
                    it = page_issue(q["segs"], self.R)
                    if it:
                        yield flow, at, q["idx"], it

    def _put(self, pcts):
        for b, pct in pcts.items():
            if pct == 100:
                self.scale.pop(b, None)
            else:
                self.scale[b] = pct

    def _try(self, flow, at, idx, it, force=False):
        """그 문단의 쪽에 있는 빈 줄로 시도를 세운다 → 세웠나(못 세우면 까닭을 적는다)."""
        blanks = [flow[i] for i in page_blanks(flow, at) if flow[i]["ok"]]
        if not blanks:
            self.gave[idx] = "noBlank"
            return False
        cur = [self.scale.get(b["idx"], 100) for b in blanks]
        new = blank_scale(it["need"], [b["segs"][0][1] + max(0, b["segs"][0][2]) for b in blanks], cur, self.R["blankMin"], force)
        if new is None:
            self.gave[idx] = "floor"
            return False
        t = {"prev": {b["idx"]: c for b, c in zip(blanks, cur)}, "want": {b["idx"]: n for b, n in zip(blanks, new)}, "tail": it["tail"],
             "forced": force or all(n <= self.R["blankMin"] or n == c for n, c in zip(new, cur))}   # forced = 더 낮출 데가 없음(안 맞으면 그만둔다)
        self.tries[idx] = t
        self._put(t["want"])
        return True

    def step(self, flows, more=True):
        """다시 잰 흐름으로 앞 시도를 확인하고(맞음 = 그 문단이 쪽에 안 걸침 · 아니면 하한까지 한 번 더 · 그래도 아니면 되돌림) more 면 새로 걸린 문단의 시도를 세운다
        → 배율이 바뀌었나(바뀌었으면 부르는 쪽이 사본에 입혀 다시 잰다). more=False = 다시 재기 횟수가 다함 — 확인 · 되돌림만."""
        now = {idx: (flow, at, it) for flow, at, idx, it in self._issues(flows)}
        if self.first is None:
            self.first = len(now)
        before = dict(self.scale)
        for idx, t in list(self.tries.items()):
            del self.tries[idx]
            if idx not in now:
                self.fixed[idx] = {"tail": t["tail"], "blanks": dict(t["want"])}
                continue
            self._put(t["prev"])   # 아직 걸쳐 있음 — 이 시도는 거둔다
            flow, at, it = now[idx]
            if t["forced"]:
                self.gave[idx] = "floor"
            elif not more:
                self.gave[idx] = "rounds"
            else:
                self._try(flow, at, idx, it, force=True)
        if more:
            for idx, (flow, at, it) in now.items():
                if idx in self.tries or idx in self.gave:
                    continue
                self.fixed.pop(idx, None)   # 고쳤던 문단이 다시 걸침(윗쪽의 시도를 거둬 내려옴) — 다시 시도
                self._try(flow, at, idx, it)
        return self.scale != before

    def result(self, flows):
        """마지막으로 잰 흐름 → (고친 문단 [{idx, tail, blanks[{idx, pct}]}], 그대로 둔 문단 [{idx, tail, why}], 바꾼 빈 줄 [{idx, pct}]).
        고쳤다고 세는 것은 마지막으로 잰 줄에서 쪽에 안 걸친 것뿐이다."""
        now = {idx: it for _, _, idx, it in self._issues(flows)}
        done = [{"idx": i, "tail": f["tail"], "blanks": [{"idx": b, "pct": self.scale[b]} for b in sorted(f["blanks"]) if b in self.scale]}
                for i, f in sorted(self.fixed.items()) if i not in now]
        left = [{"idx": i, "tail": it["tail"], "why": self.gave.get(i, "rounds")} for i, it in sorted(now.items())]
        return done, left, [{"idx": b, "pct": p} for b, p in sorted(self.scale.items())]


# ---------------------------------------------------------------- 문서 고치기
def _hh(tag):
    return "{http://www.hancom.co.kr/hwpml/2011/head}" + tag


LANGS = ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user")


def _rescale(doc, p, start, end, tag, default, value):
    """HwpxDoc 문단 p 의 [start, end) 글자(블록 글 자리)의 글자 모양에서 언어마다의 값(tag = ratio 장평 | spacing 자간)을 value(지금 값) 로 바꾼다 — 런을 나누고 새 글자 모양을 들인다
    (같은 정의가 있으면 그것). 표 · 그림 같은 개체가 든 런은 건드리지 않는다. → 바꾼 런 수."""
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
                e = c.find(_hh(tag))
                if e is None:   # 차례는 fontRef · ratio · spacing(hwpx_format.CHAR_ORDER — OWPML)
                    e = c.makeelement(_hh(tag), {x: str(default) for x in LANGS})
                    prev = next((x for t in (("ratio", "fontRef") if tag == "spacing" else ("fontRef",)) if (x := c.find(_hh(t))) is not None), None)
                    (prev.addnext(e) if prev is not None else c.insert(0, e))
                for x in LANGS:   # 스키마에서 속성은 선택(기본값) — 빠진 언어도 같이 바꾼다
                    e.set(x, str(value(int(e.get(x) or default))))
                made[old] = doc._add_def("charPr", c)
            if made[old] != old:
                r.set("charPrIDRef", made[old])
                n += 1
        pos += k
    doc._tidy(p)
    doc._drop_cache(p)
    doc._touch(p)
    return n


def spacing_for(cur, pct):
    """지금 자간 cur(%) 인 글자의 폭을 pct% 배로 만드는 자간(%) — 글자 나아감 = 글자 폭 × 장평 × (1 + 자간) 이라 (100 + cur) × pct ÷ 100 − 100 · −50~50."""
    return max(-50, min(50, round((100 + cur) * pct / 100 - 100)))


def scale_spacing(doc, p, start, end, pct):
    """HwpxDoc 문단 p 의 [start, end) 글자의 폭을 pct% 배로 — **자간으로**(언어마다 `spacing_for` · 장평 · 글자 모양은 그대로). → 바꾼 런 수."""
    return _rescale(doc, p, start, end, "spacing", 0, lambda cur: spacing_for(cur, pct))


def pct_limit(cur, bound, up):
    """지금 자간 cur(%) 인 글자에 걸 수 있는 배율의 끝 — **적힐 자간**(`spacing_for` 의 정수)이 bound 를 안 넘는 가장 작은(up=False · 하한) · 가장 큰(up=True · 상한) 배율.
    식 (100 + bound) ÷ (100 + cur) 로 세면 반올림 때문에 되는 값을 버린다(−10% 에서 94% 는 −15% 가 되는데 하한을 95% 로 셈 — astra 2026-11-23).
    이미 한도 밖인 글(cur 가 하한보다 좁음)은 줄이는 쪽 100 · 늘리는 쪽 100 — 그 방향으로는 안 바꾼다."""
    if up:
        return max([q for q in range(101, 201) if spacing_for(cur, q) <= bound] or [100])
    return min([q for q in range(50, 100) if spacing_for(cur, q) >= bound] or [100])


def _ratio_before(cur, pct):
    """장평을 pct% 배 해서 cur 가 된 처음 값들 — round(o × pct ÷ 100) == cur 인 o(50~200). 없으면 빈 목록."""
    guess = cur * 100 / pct
    return [o for o in range(math.floor(guess) - 1, math.ceil(guess) + 2) if 50 <= o <= 200 and max(50, min(200, round(o * pct / 100))) == cur]


def _ratio_of(d):
    e = d.find(_hh("ratio"))
    return tuple(int(e.get(x) or 100) if e is not None else 100 for x in LANGS)


def _plain_index(doc):
    """글자 모양을 「장평만 뺀 꼴」 로 묶은 색인 {장평 뺀 지문: [(id, 언어마다 장평)…]} — 정의 수가 바뀌면 다시 짓는다(문서마다 한 번)."""
    from app.hwpx_doc import _sig
    defs = doc._defs["charPr"]
    got = getattr(doc, "_lt_plain", None)
    if got is None or got[0] != len(defs):
        index = {}
        for i, d in defs.items():
            index.setdefault(_plain_sig(d, _sig), []).append((i, _ratio_of(d)))
        got = doc._lt_plain = (len(defs), index)
    return got[1]


def _plain_sig(d, _sig):
    c = copy.deepcopy(d)
    e = c.find(_hh("ratio"))
    if e is not None:
        c.remove(e)
    return _sig(c)


def _before_defs(doc, cid, pct):
    """글자 모양 cid 에서 **장평만** pct 로 나눈 꼴인, 문서에 이미 있는 정의들의 id — 언어마다 round(그 정의의 장평 × pct ÷ 100) == 지금 장평(한글 87 · 영문 88 처럼 언어마다 달라도 찾는다).
    제 자신은 뺀다."""
    from app.hwpx_doc import _sig
    src = doc._defs["charPr"].get(cid)
    if src is None:
        return []
    cur = _ratio_of(src)
    return [i for i, was in _plain_index(doc).get(_plain_sig(src, _sig), ()) if i != cid and all(o in _ratio_before(c, pct) for o, c in zip(was, cur))]


def ratio_proof(doc, p, ops, neighbor=True):
    """전에 장평으로 고친 문단(2026-11-23 의 자간으로 바꾸기 전 — 기록의 ops [(rs, re, pct)…])의 장평을 **되돌려도 되는 근거**가 지금 문서에 있나 → [(런, 되돌릴 글자 모양 id)…] | None.
    문서를 안 바꾼다(되돌리기는 `restore`). 기록은 반영을 「실행 취소」 해도 남고 다른 도구 · 사람도 장평을 바꾼다 — 기록만 믿고 나누면 처음대로인 100% 가 104% 로 넓어진다. 근거:
    ① 범위의 양 끝이 **런의 경계**다(줄 정리가 거기서 런을 나눴다 — 실행 취소한 문서에서는 한 런이 그 경계를 지나간다) · 개체가 든 런 · 서로 겹친 범위가 없다
    ② 범위 안의 런마다 「장평만 되돌린 글자 모양」 이 문서에 이미 있는 정의다(`_before_defs`)
    ③ neighbor — 범위 바로 앞이나 바로 뒤의 런(범위 밖)이 **그 되돌린 정의를 그대로 쓰고 있다**(같은 런이던 글의 나머지). 문단 본문 전체가 범위라 옆 런이 없으면 ③ 은 못 본다 —
       그런 문단은 부르는 쪽이 한글의 줄(옛 계획의 after 와 같은가)로 본 뒤 neighbor=False 로 부른다(line_tidy_api.plan_bytes)."""
    from app.hwpx_doc import OBJECTS, RUN
    runs, pos = [], 0
    for r in p.iterchildren(RUN):
        k = sum(doc._clen(c) for c in r)
        if k:
            runs.append((pos, pos + k, r))
        pos += k
    spans = []
    for rs, re_, pct in sorted(ops):   # 맞닿은 같은 배율의 범위는 한 런으로 합쳐져 있다 — 범위도 합쳐 본다
        if spans and rs < spans[-1][1]:
            return None
        if spans and spans[-1][1] == rs and spans[-1][2] == pct:
            spans[-1][1] = re_
        else:
            spans.append([rs, re_, pct])
    held = {id(r) for a, b, r in runs if any(rs <= a and b <= re_ for rs, re_, _ in spans)}
    out, seen = [], False
    for rs, re_, pct in spans:
        inside = [(a, b, r) for a, b, r in runs if rs <= a and b <= re_]
        if not inside or inside[0][0] != rs or inside[-1][1] != re_ or any(c.tag in OBJECTS for _, _, r in inside for c in r):
            return None
        sides = [r.get("charPrIDRef", "0") for a, b, r in runs if (b == rs or a == re_) and id(r) not in held]   # 범위 밖의 바로 옆 런
        for a, b, r in inside:
            cands = _before_defs(doc, r.get("charPrIDRef", "0"), pct)
            near = [c for c in cands if c in sides]
            if near:
                seen = seen or (a == rs or b == re_)
            pick = near[0] if near else cands[0] if len(cands) == 1 else None   # 여럿이면 옆 런이 쓰는 것 · 그것도 없으면 정할 수 없다
            if pick is None:
                return None
            out.append((r, pick))
    return out if out and (seen or not neighbor) else None


def restore(doc, p, proof):
    """`ratio_proof` 의 답대로 그 런들을 되돌린 글자 모양으로 → 바꾼 런 수. proof 를 낸 뒤 그 문단을 바꾸지 않았어야 한다."""
    for r, was in proof:
        r.set("charPrIDRef", was)
    doc._tidy(p)
    doc._drop_cache(p)
    doc._touch(p)
    return len(proof)


def scale_height(doc, p, pct):
    """HwpxDoc 빈 문단 p 의 높이를 pct% 로 — 런마다 글자 크기(charPr height)를 지금 값 × pct/100(0.1pt 단위 · 1pt 이상)인 글자 모양으로 바꾼다(같은 정의가 있으면 그것).
    빈 줄의 높이 = 문단 끝 빈 런의 글자 크기 × 줄 간격(줄 간격이 「글자에 따라」 일 때 — 고정 값이면 안 낮아지고, 다시 잴 때 드러난다). → 바꾼 런 수."""
    from app.hwpx_doc import RUN
    made, n = {}, 0
    for r in p.iterchildren(RUN):
        old = r.get("charPrIDRef", "0")
        if old not in made:
            src = doc._defs["charPr"].get(old)
            if src is None:
                raise ValueError(f"글자 모양 {old} 정의가 없습니다")
            h = int(src.get("height") or 1000)
            new = max(100, int(round(h * pct / 1000.0)) * 10)
            if new == h:
                made[old] = old
            else:
                c = copy.deepcopy(src)
                c.set("height", str(new))
                made[old] = doc._add_def("charPr", c)
        if made[old] != old:
            r.set("charPrIDRef", made[old])
            n += 1
    doc._drop_cache(p)
    doc._touch(p)
    return n
