"""레터 넣기(spec_hwpx_웹편집 ② §8-9) — 도구 줄 「문단 수정」 묶음의 단추로 문단을 **헤딩(레터 줄)** 으로.

2026-11-17 사용자 "여기 문단에 속한 아이콘 중에서 레터를 선택해서 헤딩으로 넣을 수 있는 기능을 넣어줘, 둥근 숫자, 숫자. 숫자., 숫자) 이런것도 포함해서".

두 길(둘 다 계획만 낸다 — 문서는 app/para_letter_api.py 가 트랜잭션 하나로 바꾼다):
- **레터만**(`plan_plain` — hwpx · docx): 문단 첫머리(레터 앞 빈칸 뒤)에 레터 + 레터 뒤 빈칸을 넣는다. 이미 레터가 있으면 그 레터를 바꾼다. 문단 모양은 그대로.
  번호형(① 1. 1) (1) 1.1. 1-1. 가. … — `NUMBERED`)은 **앞의 같은 꼴 줄에 이어서**(`prior` — 거슬러 올라가다 더 얕은 서열의 레터 줄을 만나면 새 묶음: 그 꼴의 첫 번호),
  고른 문단이 여럿이면 차례로(① ② ③), 뒤에 **바로 이어지던** 같은 꼴 줄들의 번호도 밀어 매긴다(`_follow`). `restart` = 앞 줄과 무관하게 고른 레터 그대로부터.
  레터는 헤딩 추출의 **내장 레터 규칙**(heading_rules BUILTIN 의 marker)이 읽는 글자만 — 넣은 줄을 헤딩 추출이 헤딩으로 읽어야 「헤딩으로 넣기」 다(안내 ※ · 각주 * 는 거절).
- **개요 레벨로**(`plan_adopt` — hwpx + 2단계 오버레이): 문단을 그 문서 템플릿의 (TN, Lk) 줄로 — 접두(레터 앞 빈칸 · 레터 · 레터 뒤 빈칸)와 문단·글자 모양을 그 레벨 슬롯 것으로
  (Alt+↑/↓ 와 같은 `restyle` 행동 · 같은 실행 `server._outline_run` — 새 길을 만들지 않는다), 부모는 앞 줄에서 찾고(`outline_edit._resolve_parent`), 번호형이면 형제 차례로 번호를 매긴다(`outline_edit.renumber`).
  개요 줄이 아니던 문단도, 다른 레벨·다른 템플릿의 줄도 된다(Alt+↑/↓ 는 한 단계씩 · 개요 줄만).
- `plan_remove` = 레터 빼기(레터 + 레터 뒤 빈칸을 지움 — 레터 앞 빈칸은 그대로 · 번호형이면 뒤에 이어지던 줄의 번호를 당긴다).
- `suggest` = 단추를 눌렀을 때 화면이 보일 것(지금 레터 · 이 문서의 개요 레벨 · 번호·기호 후보마다 **넣을 레터** — 이어서/처음부터).

seq = 그릇(구역·표 칸) 하나의 문단 열 [{id, text, blank, object}](outline_edit 과 같은 꼴). 순수 함수 — 문서 객체를 읽지 않는다(서식·오버레이는 인자로)."""
import re

from app import heading_rules as HR
from app import outline_edit as OE

# 후보(화면 차례 그대로) — 번호형 · 기호. 모두 내장 레터 규칙이 marker 로 읽는 글자(tests/test_para_letter.py 가 본다)
NUMBERS = ("①", "1.", "1)", "(1)", "1.1.", "1-1.", "가.", "가)", "(가)", "a.", "a)", "(a)", "A.", "Ⅰ.", "⑴", "❶", "㉠", "㉮")
SYMBOLS = ("□", "■", "○", "●", "o", "-", "·", "•", "▪", "◇", "◆", "▶", "△")
LETTER_MAX = 8   # 직접 입력 글자 수(outline_grow 와 같다)
LEVELS_MAX = 14  # 메뉴에 보이는 개요 레벨 줄 수

_DIGIT = ("decimal", "hyphen", "num-paren", "paren-num", "bracket-num", "chapter", "section", "article")
_HANGUL = ("hangul-dot", "hangul-paren", "paren-hangul", "bracket-hangul")
_ALPHA = ("alpha-upper", "alpha-lower", "paren-alpha")
_ROMAN = ("roman-upper", "roman-lower")
NUMBERED = frozenset(_DIGIT + _HANGUL + _ALPHA + _ROMAN + ("circled", "enclosed"))
_CIRCLED = ((0x2460, 0x2473, 1), (0x3251, 0x325F, 21), (0x32B1, 0x32BF, 36))  # ①-⑳ · ㉑-㉟ · ㊱-㊿ (첫 글자, 끝 글자, 첫 번호 — heading_rules._ordinal 과 같다)
# 서열 = 한국어 개요의 흔한 깊이(얕음 → 깊음 — heading_graph._RANK · outline_grow.RANK 와 같은 뜻). 번호를 이을 앞 줄을 찾을 때 「더 얕은 줄을 만나면 새 묶음」 을 가르는 데만 쓴다.
_RANK = {"chapter": 1, "section": 2, "roman-upper": 2, "article": 3, "decimal": 5, "hyphen": 5, "hangul-dot": 6, "alpha-upper": 6, "paren-num": 7, "num-paren": 7,
         "hangul-paren": 8, "paren-hangul": 8, "circled": 9, "enclosed": 9, "alpha-lower": 9, "paren-alpha": 9, "roman-lower": 9, "square": 10,
         "circle": 11, "latin-o": 11, "jamo-o": 11, "dash": 12, "dot": 13, "small-square": 14, "diamond": 14, "arrow": 14, "triangle": 14}

_RULES = []


def _rules():
    """내장 레터 규칙만(배운 규칙·끈 규칙과 무관 — 넣는 레터는 어느 문서에서나 같은 뜻이어야 한다: outline_grow._rules 와 같다)."""
    if not _RULES:
        _RULES.extend(HR.active({"rules": [], "builtin": {}}))
    return _RULES


def read(text, known=None):
    """문단 글 → {lead(레터 앞 빈칸), letter(없으면 ""), gap(레터 뒤 빈칸), family, shape, ord}. known = 개요 오버레이가 아는 그 줄의 레터(첫머리에 그대로 있으면 그것 —
    배운 규칙으로 읽힌 레터도 바꿀 수 있게). 레터 = 내장 규칙의 marker 뿐(구분 라벨 「[…]」 · 안내 ※ · 값은 레터가 아니다 — 그 앞에 넣는다)."""
    text = text or ""
    c = HR.classify(text, _rules())
    if c["kind"] == "marker" and c["letter"]:
        return {"lead": c["lead"], "letter": c["letter"], "gap": c["gap"], "family": c["family"], "shape": c["shape"], "ord": c["ord"]}
    lead, tok, gap = OE.prefix_of(text, known or None)
    if tok:
        return {"lead": lead, "letter": tok, "gap": gap, "family": None, "shape": tok, "ord": None}
    return {"lead": HR.split_lead(text)[0], "letter": "", "gap": "", "family": None, "shape": "", "ord": None}


def check(letter):
    """고른 레터 → 분류 {letter, family, shape, ord}. 헤딩 추출이 레터로 읽지 않는 글자면 ValueError."""
    s = letter.strip() if isinstance(letter, str) else ""
    if not s or len(s) > LETTER_MAX or any(ch.isspace() for ch in s):
        raise ValueError(f"레터는 빈칸 없는 1~{LETTER_MAX}글자입니다")
    c = HR.classify(s + " 가", _rules())
    if c["kind"] != "marker" or c["letter"] != s:
        raise ValueError(f"「{s}」 는 헤딩 레터로 읽히지 않습니다 — 번호 꼴(① 1. 1) (1) 1.1. 가. 가) a.)이나 기호(□ ○ o - · ▪ ◇ ▶)로 고르세요")
    return {"letter": s, "family": c["family"], "shape": c["shape"], "ord": c["ord"]}


def numbered(c):
    """번호형인가 — 번호 열을 아는 계열이고 번호가 읽힌 레터."""
    return c.get("family") in NUMBERED and bool(c.get("ord"))


def same(a, b):
    """같은 꼴(같은 계열 · 같은 모양 키 — 「②」 와 「①」, 「2.3.」 과 「1.1.」)."""
    return bool(a.get("letter")) and a.get("family") is not None and a.get("family") == b.get("family") and a.get("shape") == b.get("shape")


def rank(c):
    """서열(작을수록 얕다) | None(모름). 「1.」 5.0 · 「1.1.」「1-1.」 5.1 · 「1.1.1.」 5.2 — 번호가 하나 더 붙으면 한 칸 깊다."""
    r = _RANK.get(c.get("family"))
    if r is not None and c.get("family") in ("decimal", "hyphen"):
        r += 0.1 * (len(c.get("ord") or [1]) - 1)
    return r


def _roman(n):
    out = ""
    for v, s in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + s, n - v
    return out


def with_last(family, letter, n):
    """letter 와 같은 꼴에서 **마지막 번호**만 n 으로(1부터 — 「2.3.」 → 「2.n.」, 「③」 → n 번째 둘레 숫자). 번호 열을 넘으면 None."""
    if not letter or n < 1:
        return None
    if family in _DIGIT:
        ms = list(re.finditer(r"\d+", letter))
        return letter[:ms[-1].start()] + str(n) + letter[ms[-1].end():] if ms and n <= 99 else None
    if family in _HANGUL:
        m = re.search(f"[{HR.GA}]", letter)
        return letter[:m.start()] + HR.GA[n - 1] + letter[m.end():] if m and n <= len(HR.GA) else None
    if family == "circled":
        for lo, hi, base in _CIRCLED:
            if base <= n <= base + hi - lo:
                return chr(lo + n - base) + letter[1:]
        return None
    if family == "enclosed":
        c = ord(letter[0])
        rng = next(((lo, hi) for lo, hi in HR._ENCLOSED if lo <= c <= hi), None)
        return chr(rng[0] + n - 1) + letter[1:] if rng and rng[0] + n - 1 <= rng[1] else None
    if family in _ALPHA:
        m = re.search("[A-Za-z]", letter)
        if not m or n > 26:
            return None
        return letter[:m.start()] + chr(ord("A" if m.group().isupper() else "a") + n - 1) + letter[m.end():]
    if family in _ROMAN:
        ch = letter[0]
        if "Ⅰ" <= ch <= "Ⅻ" or "ⅰ" <= ch <= "ⅻ":
            return chr((0x2160 if ch <= "Ⅻ" else 0x2170) + n - 1) + letter[1:] if n <= 12 else None
        m = re.match("[IVXivx]+", letter)
        if not m or n > 39:
            return None
        return (_roman(n) if ch.isupper() else _roman(n).lower()) + letter[m.end():]
    return None


def _last(c):
    return (c.get("ord") or [None])[-1]


def prior(seq, i, cls, want):
    """자리 i 앞에서 want 와 **같은 꼴**의 가장 가까운 줄(번호를 이을 줄) → (그 분류 | None, 묶음을 연 더 얕은 줄의 분류 | None).
    거슬러 올라가다 want 보다 서열이 얕은 레터 줄을 만나면 멈춘다(그 줄 아래의 새 묶음 — 이을 줄 없음). 서열을 모르는 레터 · 더 깊은 레터 · 본문은 건너뛴다."""
    r = rank(want)
    for j in range(i - 1, -1, -1):
        c = cls(j)
        if not c["letter"]:
            continue
        if same(c, want):
            return c, None
        cr = rank(c)
        if r is not None and cr is not None and cr < r:
            return None, c
    return None, None


def _start(want, model, parent, restart):
    """첫 문단에 넣을 레터 — 이어서(앞의 같은 꼴 줄 + 1) | 처음부터(고른 레터 그대로 — 번호가 여럿인 꼴은 앞 번호를 앞 줄·윗 줄 것으로: 「2.3.」 뒤 → 「2.1.」 · 「3.」 아래 → 「3.1.」)."""
    if not numbered(want):
        return want["letter"]
    if model is not None and _last(model) is not None:
        return with_last(model["family"], model["letter"], _last(want) if restart else _last(model) + 1)
    if parent is not None and want["family"] in ("decimal", "hyphen") and parent.get("family") in ("decimal", "hyphen"):
        pn, wn = parent.get("ord") or [], want["ord"]
        if pn and len(wn) == len(pn) + 1:
            return OE.with_numbers(want["letter"], pn + [wn[-1]]) or want["letter"]
    return want["letter"]


def _targets(seq, idxs):
    """레터를 넣을 자리들(문서 순) — 여러 문단을 골랐으면 빈 문단(간격 줄)과 표·그림만 든 문단은 뺀다. 하나만 골랐으면 빈 문단에도 넣는다(레터만 있는 줄 — 이어서 글을 친다)."""
    idxs = sorted(set(idxs))
    solo = len(idxs) == 1
    out = [i for i in idxs if not (seq[i].get("object") and not (seq[i]["text"] or "").strip()) and (solo or (seq[i]["text"] or "").strip())]
    if not out:
        raise ValueError("표·그림만 든 문단에는 레터를 넣을 수 없습니다" if solo else "레터를 넣을 글 문단이 없습니다(빈 문단 · 표·그림만 든 문단은 건너뜁니다)")
    return out


def _cls(seq, known):
    memo = {}

    def cls(j):
        if j not in memo:
            memo[j] = read(seq[j]["text"], (known or {}).get(seq[j]["id"]))
        return memo[j]
    return cls


def _follow(seq, last, cls, want, n, exp):
    """뒤에 **바로 이어지던** 같은 꼴 줄들의 번호를 n + 1 부터 다시 → 행동 목록. exp = 고치기 전에 다음 줄이 가졌을 번호 — 그 번호로 이어지는 동안만
    (다른 번호로 시작하는 줄 = 다른 묶음 · 더 얕은 레터 줄 = 묶음의 끝에서 멈춘다)."""
    acts, r = [], rank(want)
    for j in range(last + 1, len(seq)):
        c = cls(j)
        if not c["letter"]:
            continue
        if same(c, want):
            if _last(c) != exp:
                break
            n, exp = n + 1, exp + 1
            new = with_last(c["family"], c["letter"], n)
            if new is None:
                raise ValueError(f"번호 열의 끝입니다 — 뒤 줄 「{c['letter']}」 에 매길 다음 번호가 없습니다")
            if new != c["letter"]:
                acts.append({"id": seq[j]["id"], "old_len": len(c["lead"]) + len(c["letter"]), "prefix": c["lead"] + new, "letter": new, "follow": True})
            continue
        cr = rank(c)
        if r is not None and cr is not None and cr < r:
            break
    return acts


def plan_plain(seq, idxs, letter, restart=False, known=None):
    """레터만 넣기 → {"actions": [{id, old_len, prefix, letter, follow?}], "focus": {id, offset}, "put": [넣은 레터…], "from": 이은 앞 줄의 레터 | None, "follow": 번호를 민 뒤 줄 수}.
    actions = 바뀌는 문단만(이미 그 레터인 문단은 없다). known = {문단 id: 오버레이가 아는 레터}."""
    want = check(letter)
    tg = _targets(seq, idxs)
    cls = _cls(seq, known)
    model, parent = prior(seq, tg[0], cls, want)
    cur = _start(want, model, parent, bool(restart))
    if cur is None:
        raise ValueError(f"번호 열의 끝입니다 — 앞 줄 「{model['letter']}」 다음 번호가 없습니다")
    n = (HR._ordinal(want["family"], cur) or [None])[-1] if numbered(want) else None
    num = n is not None
    gap = (model or {}).get("gap") or " "
    acts, puts, base = [], [], cur
    last_old = None
    for k, i in enumerate(tg):
        c = cls(i)
        if k and num:
            n += 1
            cur = with_last(want["family"], base, n)
            if cur is None:
                raise ValueError(f"번호 열의 끝입니다 — 「{puts[-1]}」 다음 번호가 없습니다")
        old_len = len(c["lead"]) + len(c["letter"]) + len(c["gap"])
        prefix = c["lead"] + cur + (c["gap"] if c["letter"] and c["gap"] else gap)
        puts.append(cur)
        last_old = _last(c) if same(c, want) else None
        if (seq[i]["text"] or "")[:old_len] != prefix or not c["letter"]:
            acts.append({"id": seq[i]["id"], "old_len": old_len, "prefix": prefix, "letter": cur})
    follow = []
    if num:
        exp = (last_old if last_old is not None else (_last(model) or 0) if model is not None else 0) + 1
        follow = _follow(seq, tg[-1], cls, want, n, exp)
    first = next((a for a in acts if a["id"] == seq[tg[0]]["id"]), None)
    c0 = cls(tg[0])
    return {"actions": acts + follow, "focus": {"id": seq[tg[0]]["id"], "offset": len(first["prefix"]) if first else len(c0["lead"]) + len(c0["letter"]) + len(c0["gap"])},
            "put": puts, "from": model["letter"] if model is not None and num and not restart else None, "follow": len(follow)}


def plan_remove(seq, idxs, known=None):
    """레터 빼기 → plan_plain 과 같은 꼴(put = 뺀 레터들). 레터 + 레터 뒤 빈칸을 지운다(레터 앞 빈칸은 그대로). 번호형이면 뒤에 이어지던 같은 꼴 줄의 번호를 당긴다."""
    idxs = sorted(set(idxs))
    cls = _cls(seq, known)
    tg = [i for i in idxs if cls(i)["letter"]]
    if not tg:
        raise ValueError("뺄 레터가 없습니다 — 레터로 시작하는 문단이 아닙니다")
    acts = [{"id": seq[i]["id"], "old_len": len(cls(i)["lead"]) + len(cls(i)["letter"]) + len(cls(i)["gap"]), "prefix": cls(i)["lead"], "letter": ""} for i in tg]
    want, follow = cls(tg[-1]), []
    if numbered(want):
        firsts = [cls(i) for i in tg if same(cls(i), want)]
        follow = _follow(seq, tg[-1], cls, want, _last(firsts[0]) - 1, _last(want) + 1)
    return {"actions": acts + follow, "focus": {"id": seq[tg[0]]["id"], "offset": len(cls(tg[0])["lead"])}, "put": [cls(i)["letter"] for i in tg], "from": None, "follow": len(follow)}


# ---------------------------------------------------------------- 개요 레벨로(hwpx + 2단계 오버레이)
def _level_ok(ov, tid, level):
    """(템플릿, 레벨)이 「개요 레벨로」 의 대상인가 → 슬롯 | None. 본보기(동결 접두·모양)가 있고, 표 제목 레벨·괄호 줄 레벨(구분 라벨 · 괄호 소제목 — 글 전체가 레터)이 아닌 것."""
    t = ov["templates"].get(str(tid))
    sl = OE._slot(ov, tid, level)
    if t is None or sl is None or sl.get("table") or not sl.get("prefix") or not sl.get("attrs") or int(level) <= int(t.get("base") or 0):
        return None
    lt = sl.get("letter") or ""
    if not lt or not OE.prefix_of(sl["prefix"], lt)[1]:
        return None
    c = HR.classify(sl["prefix"] + "가", _rules())
    if c["kind"] == "label" or lt.startswith(("[", "【")) and c["kind"] != "marker":
        return None
    return sl


def levels(ov, seq, i):
    """자리 i 에서 권하는 개요 레벨들 [{tpl, no, level, letter(번호형은 그 꼴의 첫 번호), key, numbered, cur(지금 그 레벨의 줄)}] — 그 자리의 **개요 사슬** 차례(바깥 → 안):
    그 자리(또는 그 앞 가장 가까운 개요 줄)의 윗줄들의 템플릿 → 그 줄의 템플릿 → 바로 뒤 개요 줄의 템플릿 → 그 줄 아래에 매달리는 템플릿(branches — 「1-1.」 아래의 「□›o›-」 · 많이 쓰인 차례).
    개요 줄이 하나도 없는 그릇이면 주 사슬(main) 템플릿. LEVELS_MAX 줄을 넘으면 먼 것부터 뺀다(남기는 차례: 그 줄의 템플릿 · 바로 뒤 줄의 템플릿 · 윗줄들(안 → 바깥) · 매달리는 템플릿). 오버레이가 없으면 []."""
    if not ov:
        return []
    lines, tps, here = ov["lines"], ov["templates"], ov["lines"].get(seq[i]["id"])
    near = next((lines[seq[j]["id"]] for j in range(i, -1, -1) if seq[j]["id"] in lines), None)
    nxt = next((lines[seq[j]["id"]] for j in range(i + 1, len(seq)) if seq[j]["id"] in lines), None)
    if near is None:
        near, nxt = nxt, None
    if near:
        x, up = near, []
        for _ in range(64):  # 윗줄을 따라 올라가며 템플릿을 모은다(안 → 바깥)
            up.append(x["tpl"])
            x = lines.get(x["parent"]) if x.get("parent") else None
            if x is None:
                break
        hang = list((ov.get("branches") or {}).get(f"{near['tpl']}|{near['level']}") or [])
        order = up[::-1] + ([nxt["tpl"]] if nxt else []) + hang                # 보이는 차례(바깥 → 안)
        prio = [near["tpl"]] + ([nxt["tpl"]] if nxt else []) + up[1:] + hang   # 남기는 차례
    else:
        order = prio = [tid for tid, t in tps.items() if t.get("kind") == "main"]
    made = {}
    for tid in dict.fromkeys(order):
        t, rows = tps.get(tid), []
        for lv in sorted((t or {}).get("slots", {}), key=int):
            sl = _level_ok(ov, tid, lv)
            if sl is None:
                continue
            key = t["chain"][int(lv) - 1] if int(lv) - 1 < len(t.get("chain") or []) else sl.get("key") or ""
            num = OE.is_numbered(key)
            rows.append({"tpl": tid, "no": t["no"], "level": int(lv), "letter": (OE.first(sl["letter"]) or sl["letter"]) if num else sl["letter"], "key": key, "numbered": num,
                         "cur": bool(here) and here["tpl"] == tid and int(here["level"]) == int(lv)})
        if rows:
            made[tid] = rows
    keep, n = set(), 0
    for tid in dict.fromkeys(prio):
        if tid in made and (not keep or n + len(made[tid]) <= LEVELS_MAX):
            keep.add(tid)
            n += len(made[tid])
    return [r for tid in dict.fromkeys(order) if tid in keep for r in made[tid]][:LEVELS_MAX]


def _rootless_ok(seq, i, o2, tid, level, t):
    """부모 줄 없이 놓여도 되는 자리인가 — 주 사슬의 첫 글 레벨이거나, 그 그릇에 이미 부모 없는 같은 (템플릿, 레벨) 줄이 있을 때(표 칸의 칸 템플릿 L1 · 부모 문단이 개요 줄이 아닌 가지)."""
    if level == 1 + OE.lift_depth(t) and t.get("kind") == "main":
        return True
    for k, it in enumerate(seq):
        y = o2["lines"].get(it["id"]) if k != i else None
        if y is not None and y["tpl"] == tid and int(y["level"]) == level and y["parent"] is None:
            return True
    return False


def plan_adopt(seq, idxs, tid, level, ov, text_of):
    """문단들(같은 그릇)을 템플릿 tid 의 레벨 level 줄로 → outline_edit 계획 {"actions", "focus", "focuses"}(`server._outline_run` 이 실행).
    개요 줄이 아니던 문단은 새 줄로(있던 레터는 바꾸고 없으면 레터 앞 빈칸 자리에 접두를 넣는다), 다른 (템플릿, 레벨)의 줄은 그 레벨로(Alt+↑/↓ 의 `plan_level` 과 같은 행동:
    접두·모양 = 슬롯 것 · 부모 다시 찾기 · 영향 구간의 부모 다시 붙임 · 번호형이면 형제 차례로 번호). 이미 그 레벨인 줄은 그대로. 하나라도 못 바꾸면 전부 거절(ValueError)."""
    tid, level = str(tid), int(level)
    t = ov["templates"].get(tid)
    if t is None:
        raise ValueError("그 템플릿이 없습니다 — 문서를 다시 읽어 주세요")
    slot = _level_ok(ov, tid, level)
    if slot is None:
        if OE._slot(ov, tid, level) is None:
            raise ValueError(f"T{t['no']} 에 L{level} 이 없습니다")
        raise ValueError(f"T{t['no']} L{level} 로는 바꿀 수 없습니다 — 표 제목 레벨 · 괄호 줄(구분 라벨·괄호 소제목) 레벨이거나 그 레벨의 본보기 문단이 문서에 없습니다")
    key = t["chain"][level - 1] if level - 1 < len(t.get("chain") or []) else slot.get("key") or ""
    tg = _targets(seq, idxs)
    shadow = {p: dict(v) for p, v in ov["lines"].items()}
    o2 = {**ov, "lines": shadow}
    acts, focus = [], []
    for i in tg:
        pid = seq[i]["id"]
        x = ov["lines"].get(pid)
        text = text_of(pid)
        if x is not None:
            if x.get("role") in OE.ROOTED or x.get("role") == OE.TABLE:
                raise ValueError("구분 라벨 · 괄호 소제목 · 표 제목 줄은 다른 레벨로 바꿀 수 없습니다")
            if x["tpl"] == tid and int(x["level"]) == level:
                continue
            lead, tok, gap = OE.prefix_of(text, x["letter"] or None)
            old_len, old_parent, old_group, flow = len(lead) + len(tok) + len(gap), x["parent"], (x["parent"], x["tpl"], int(x["level"])), x.get("flow", "body")
        else:
            c = read(text)
            old_len, old_parent, old_group = len(c["lead"]) + len(c["letter"]) + len(c["gap"]), None, None
            flow = next((shadow[seq[j]["id"]].get("flow", "body") for j in range(i - 1, -1, -1) if seq[j]["id"] in shadow), "body")
        if x is not None:  # 있던 줄 — plan_level 처럼 자리만 바꾼다(role · flow 는 그대로)
            shadow[pid] = {**x, "tpl": tid, "no": t["no"], "level": level, "key": key}
        else:
            shadow[pid] = {**OE._line(ov, tid, level, None, slot["letter"], flow), "key": key}
        parent = OE._resolve_parent(seq, i, o2, tid, level)
        if parent is None and not _rootless_ok(seq, i, o2, tid, level, t):
            raise ValueError(f"이 자리에서는 T{t['no']} L{level} 줄이 매달릴 윗 레벨 줄이 없습니다 — 그 템플릿의 줄 아래에서 고르세요")
        shadow[pid]["parent"] = parent
        letter = slot["letter"]
        if OE.is_numbered(key):
            letter = OE.first(letter, OE._parent_letter(o2, parent))  # 번호는 아래 renumber 가 형제 차례로 다시 매김
        shadow[pid]["letter"] = letter
        prefix = OE._prefix_for(slot, letter)
        acts.append({"act": "restyle", "id": pid, "old_len": old_len, "prefix": prefix, "attrs": slot["attrs"], "line": dict(shadow[pid])})
        focus.append({"id": pid, "offset": len(prefix), "shift": len(prefix) - old_len})
        scope = old_parent if x is not None else parent  # 영향 구간 — 옛 부모(새 줄은 새 부모)의 부분 트리 안: 뒤 줄들의 부모를 다시 찾는다
        for j in range(i + 1, len(seq)):
            q = seq[j]["id"]
            if q not in shadow:
                continue
            if scope is not None and not OE.is_descendant(o2, q, scope) and shadow[q]["parent"] != pid:
                break
            if x is None and shadow[q]["tpl"] == tid and int(shadow[q]["level"]) <= level:
                break  # 새 줄의 영향은 제 부분 트리까지 — 같은 템플릿의 같거나 얕은 줄부터는 그 줄의 것(주 사슬 L1 을 새로 넣어도 문서 끝까지 훑지 않는다)
            np = OE._resolve_parent(seq, j, o2, shadow[q]["tpl"], shadow[q]["level"])
            if np is not None and np != shadow[q]["parent"]:
                shadow[q]["parent"] = np
                acts.append({"act": "reparent", "id": q, "parent": np})
        for gp, gt, gl in {(parent, tid, level)} | ({old_group} if old_group else set()):
            anchor = i if (gp, gt, gl) == (parent, tid, level) else OE._nearest_sibling(seq, i, o2, gp, gt, gl)
            acts += OE.renumber(seq, ov, OE._texts_with(text_of, acts), gp, gt, gl, shadow=shadow, anchor=anchor, fresh=(pid,))
    if not acts:
        raise ValueError(f"이미 T{t['no']} L{level} 줄입니다")
    return {"actions": acts, "focus": focus[0] if focus else None, "focuses": focus}


# ---------------------------------------------------------------- 메뉴
def suggest(seq, idxs, ov=None, known=None):
    """단추를 눌렀을 때 화면이 보일 것 → {count(레터를 넣을 문단 수), cur{letter, tpl?, no?, level?}(첫 문단의 지금 레터 · 개요 줄이면 그 자리), levels[…](개요 레벨 — levels()),
    numbers[{letter, next(이어서 넣을 레터), from(이은 앞 줄의 레터 | None), first(처음부터 넣을 레터)}], symbols[{letter}], max(직접 입력 글자 수)}.
    레터를 넣을 수 없는 자리(표·그림만 든 문단)면 ValueError. 문서·오버레이는 안 바꾼다."""
    tg = _targets(seq, idxs)
    cls = _cls(seq, known)
    i, c = tg[0], cls(tg[0])
    line = (ov or {}).get("lines", {}).get(seq[i]["id"])
    nums = []
    for lt in NUMBERS:
        want = check(lt)
        model, parent = prior(seq, i, cls, want)
        nums.append({"letter": lt, "next": _start(want, model, parent, False) or "", "from": model["letter"] if model is not None else None,
                     "first": _start(want, model, parent, True) or lt})
    return {"count": len(tg), "cur": {"letter": c["letter"], **({"tpl": line["tpl"], "no": line["no"], "level": int(line["level"])} if line else {})},
            "levels": levels(ov, seq, i), "numbers": nums, "symbols": [{"letter": lt} for lt in SYMBOLS], "max": LETTER_MAX}
