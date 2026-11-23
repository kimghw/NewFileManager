"""병합 — 줄 안의 빈 자리(「라벨 : ___ 꼬리」)에 원본의 값만 넣는다(spec_병합 ② §5-13). 순수 계산 — 부르는 곳은 `merge_fixed.plan`(같은 이름 자리의 칸 넣기 · 머리 없는 글 칸의 줄).

2026-11-23 사용자(이관한 연차보고서의 표지 서명 줄 「연구책임자: (서명)」 · 「주관연구개발기관의 장: (직인)」 과 요약문 「총 천원 (정부지원연구개발비 : 천원, …)」 이 빈 것을 보이며)
"이거 왜 ... 작성안되었나?" — 같은 날 앞서 "기관장의 이름이 누락되었다 … 이름은 들어 가도 될거 같은데 … 구조가 같은데 빠진게 문제인듯".
서식이 한 줄 · 한 칸 안에 **라벨과 빈칸을 같이 적어 둔 자리**다: 칸이 비어 있지 않아 「빈 칸」 이 아니고, 통째로 원본 글로 바꾸면 서식의 말(「(직인)」 · 원본에 없는 「지방자치단체지원연구개발비」)이 사라진다.
그래서 **서식의 글은 그대로 두고 빈칸에 값만** 넣는다.

- 빈 자리 = 한 줄 안에서 두 토큰 사이의 빈칸 둘 이상(줄 처음 · 끝의 빈칸은 아니다 — 들여쓰기). 라벨 = 그 앞의 낱말들(콜론은 건너뛰고, 괄호 · 쉼표 · 줄 처음 · 앞 빈 자리에서 끊는다). 꼬리 = 바로 뒤 토큰(「천원」 · 「(」).
- `fill(form, src)` = 서식 글 form 의 빈 자리마다 **같은 라벨**을 원본 글 src 에서 찾아(하나뿐일 때만) 라벨(과 콜론) 뒤부터 같은 꼬리 앞까지를 값으로 넣는다 → (새 글, 넣은 수) | None.
  원본에 그 라벨이 없으면 그 자리는 빈 채로 둔다(「지방자치단체지원연구개발비 : 천원」).
- `fill_at(line, src_line)` = 짝지은 **줄끼리**(라벨이 달라도 — 차례로 맞춘 서명 줄): 서식 줄의 콜론 뒤 빈 자리 하나에, 원본 줄의 콜론 뒤부터 같은 꼬리 앞까지를 넣는다 → 새 줄 | None.
- 값은 짧은 한 토막이어야 한다(VALUE_MAX 자 · 콜론 없음 · 글자나 숫자가 있음). 날짜 줄(「년 월 일」 뿐인 줄)은 보지 않는다 — 계획서를 낸 날이지 보고서를 내는 날이 아니다.
- 넣은 값의 앞뒤 빈칸은 빈 자리의 폭을 나눠 둔다(전각 글자 = 빈칸 둘) — 뒤의 「(직인)」 이 제자리 가까이 남는다. 모자라면 한 칸씩."""
import re
import unicodedata

_TOK = re.compile(r"\d[\d,.]*\d|\d|[A-Za-z가-힣]+|\S")
_GAP = re.compile(r"[ \t   　]{2,}")
_WORD = re.compile(r"[0-9A-Za-z가-힣]")
_STOP = set("()[]<>〈〉「」,·ㆍ/;")   # 라벨을 끊는 글자
COLONS = (":", "：")
DATE = {"년", "월", "일"}
VALUE_MAX = 40


def _toks(text):
    return [(m.group(0), m.start(), m.end()) for m in _TOK.finditer(text or "")]


def _is_word(tok):
    return bool(_WORD.match(tok))


def _dated(toks):
    """낱말이 「년 · 월 · 일」 뿐인 줄(날짜 줄)인가."""
    words = {t for t, _, _ in toks if _is_word(t) and not t[0].isdigit()}
    return bool(words) and words <= DATE


def slots(line):
    """서식 한 줄의 빈 자리 [{a, b(빈칸의 범위), label(앞 라벨의 글자), last(라벨의 마지막 낱말), colon(바로 앞이 콜론), tail(바로 뒤 토큰)}] — 라벨이 없는 빈 자리 · 날짜 줄은 안 낸다."""
    toks = _toks(line)
    if _dated(toks):
        return []
    out, edge = [], -1   # edge = 앞 빈 자리의 뒤 토큰 차례(라벨은 그 앞으로 못 넘어간다)
    for i in range(len(toks) - 1):
        a, b = toks[i][2], toks[i + 1][1]
        if not _GAP.fullmatch(line[a:b]):
            continue
        k, colon, words = i, False, []
        if toks[k][0] in COLONS:
            colon, k = True, k - 1
        while k > edge and _is_word(toks[k][0]):
            words.append(toks[k][0])
            k -= 1
        if words:
            out.append({"a": a, "b": b, "label": "".join(reversed(words)), "last": words[0], "colon": colon, "tail": toks[i + 1][0]})
        edge = i
    return out


def _value(text):
    """값으로 받을 수 있는 글인가 → 다듬은 값 | None."""
    v = " ".join((text or "").split())
    return v if v and len(v) <= VALUE_MAX and _WORD.search(v) and not any(c in v for c in COLONS) and "\n" not in (text or "").strip() else None


def _until(src, toks, k, tail, start):
    """src 의 start 부터, 토큰 차례 k 뒤에서 처음 나오는 tail 토큰 앞까지 — 같은 줄 안에서만 → 값 | None."""
    end = src.find("\n", start)
    end = len(src) if end < 0 else end
    for t, a, _ in toks[k:]:
        if a >= end:
            break
        if t == tail and a >= start:
            return _value(src[start:a])
    return None


def take(src, label, tail):
    """원본 글에서 라벨(낱말을 이은 글자) 뒤의 값 — 라벨이 꼭 한 번 나올 때만. 라벨 바로 뒤의 콜론은 건너뛰고 같은 줄의 tail 토큰 앞까지 → 값 | None."""
    toks = _toks(src)
    hits = []
    for i in range(len(toks)):   # 낱말 토큰을 이어 라벨과 같아지는 자리(한 줄 안)
        acc, j = "", i
        while j < len(toks) and _is_word(toks[j][0]) and label.startswith(acc + toks[j][0]) and "\n" not in src[toks[i][1]:toks[j][2]]:
            acc += toks[j][0]
            j += 1
            if acc == label:
                hits.append(j)
                break
    if len(hits) != 1:   # 없음 · 둘 이상(어느 것인지 모른다)
        return None
    k = hits[0]
    if k < len(toks) and toks[k][0] in COLONS:
        k += 1
    return _until(src, toks, k, tail, toks[k - 1][2])


def _width(v):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in v)


def _put(line, slot, value):
    rest = (slot["b"] - slot["a"]) - _width(value)
    left = max(1, rest // 2)
    return line[:slot["a"]] + " " * left + value + " " * max(1, rest - left) + line[slot["b"]:]


def fill(form, src):
    """서식 글(여러 줄일 수 있다)의 빈 자리마다 같은 라벨의 값을 원본 글에서 찾아 넣는다 → (새 글, 넣은 수) | None(넣을 것이 없음). 서식에 같은 라벨의 빈 자리가 둘이면 그 라벨은 안 넣는다."""
    lines = (form or "").split("\n")
    found = [(i, s) for i, ln in enumerate(lines) for s in slots(ln)]
    seen = {}
    for _, s in found:
        seen[s["label"]] = seen.get(s["label"], 0) + 1
    n = 0
    for i, s in reversed(found):   # 뒤에서부터(앞 자리의 범위가 안 밀리게)
        if seen[s["label"]] != 1:
            continue
        v = take(src or "", s["label"], s["tail"])
        if v is not None:
            lines[i] = _put(lines[i], s, v)
            n += 1
    return ("\n".join(lines), n) if n else None


def lone(line):
    """줄에 빈 자리가 꼭 하나이고 콜론 뒤의 것이면 그 빈 자리 | None — 「연구책임자:        (서명)」 꼴."""
    s = slots(line)
    return s[0] if len(s) == 1 and s[0]["colon"] else None


def family(line):
    """콜론이 든 줄의 갈래 — 첫 콜론 앞 마지막 낱말(「주관연구개발기관의 장:」 · 「공동연구개발기관의 장:」 → 「장」) | None."""
    cut = min((i for i in (line.find(c) for c in COLONS) if i >= 0), default=-1)
    words = [t for t, _, _ in _toks(line[:cut])] if cut > 0 else []
    return words[-1] if words and _is_word(words[-1]) else None


def fill_at(line, src_line):
    """짝지은 줄끼리 — 서식 줄 line 의 빈 자리 하나(lone)에 원본 줄 src_line 의 첫 콜론 뒤부터 같은 꼬리 토큰 앞까지를 넣는다 → 새 줄 | None."""
    s = lone(line)
    cut = min((i for i in (src_line.find(c) for c in COLONS) if i >= 0), default=-1)
    if s is None or cut < 0:
        return None
    toks = _toks(src_line)
    k = next((i for i, (_, a, _) in enumerate(toks) if a > cut), len(toks))
    v = _until(src_line, toks, k, s["tail"], cut + 1)
    return _put(line, s, v) if v is not None else None
