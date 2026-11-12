"""엑셀 수식 글의 문법·계산 — 화면 격자 엔진(`app/static/tables.js` xlTokenize·xlParse·xlEval)과 **같은 문법·함수**의 파이썬 짝(spec_헤딩_추출 ② §14 「LLM 수식 판정」).

서버가 LLM 이 제안한 수식을 검사하고(문법·주소·순환) 스크립트 수식과 값이 같은지 견줄 때 쓴다. 문서·화면을 모른다 — 수식 글과 칸 값 함수만.

- `parse(글)` → 트리(튜플) | `FormulaError`(까닭).
- `rects(트리)` → 가리키는 주소 [(r0, c0, r1, c1)…](0부터, 칸 하나는 r0 == r1).
- `evaluate(트리, value)` → 값. value(행, 열) = 그 자리 칸의 값(수 | None | 글) — 병합 칸·수식 칸 풀기는 부르는 쪽이.
- `shift(글, 행, 열)` → 상대 주소를 옮긴 수식 글(엑셀의 채우기 — `$` 붙은 쪽은 그대로) | None(표 밖으로 나감).
- `canon(글)` → 견줄 꼴(공백 없이 · 대문자 · 글 상수는 그대로)."""
import math
import re

FUNCTIONS = frozenset({"SUM", "AVERAGE", "MIN", "MAX", "COUNT", "COUNTA", "ABS", "INT", "SQRT", "ROUND", "ROUNDUP", "ROUNDDOWN", "MOD", "POWER", "AND", "OR", "NOT", "IF"})
MAX_LEN = 500  # 사용자 수식 길이 한도(table_agent.FORMULA_MAX 와 같다)
_REF = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)([1-9]\d{0,3})$")
_TOKEN = re.compile(r"""\s*(?:
    (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?) |
    (?P<str>"(?:[^"]|"")*") |
    (?P<id>[A-Za-z_$ㄱ-힝][\w$.ㄱ-힝]*) |
    (?P<op><>|<=|>=|[+\-*/^%(),:=<>&])
)""", re.X)
_REF_IN_TEXT = re.compile(r'"(?:[^"]|"")*"|(?<![A-Za-z0-9_$.])(\$?)([A-Za-z]{1,3})(\$?)([1-9]\d{0,3})(?![\w(.])')


class FormulaError(ValueError):
    """수식 글을 못 읽거나 계산할 수 없음 — 글은 사람이 읽는 까닭."""


def col_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def col_letter(c):
    s, c = "", c + 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def a1(row, col):
    return f"{col_letter(col)}{row + 1}"


def pos(ref):
    """「E26」「$E$26」 → (행, 열) | None."""
    m = _REF.match((ref or "").strip().upper())
    return (int(m.group(4)) - 1, col_index(m.group(2))) if m else None


def tokens(text):
    s = (text or "").strip()
    if s.startswith("="):
        s = s[1:]
    out, i = [], 0
    while i < len(s):
        m = _TOKEN.match(s, i)
        if not m or m.end() == i:
            if not s[i:].strip():
                break
            raise FormulaError(f"모르는 글자 {s[i:].strip()[:1]!r}")
        kind = m.lastgroup
        v = m.group(kind)
        if kind == "num":
            out.append(("num", float(v)))
        elif kind == "str":
            out.append(("str", v[1:-1].replace('""', '"')))
        else:
            out.append((kind, v))
        i = m.end()
    return out


def parse(text):
    """수식 글 → 트리. 꼴: ("num", v) · ("str", v) · ("bool", v) · ("ref", r, c) · ("range", r0, c0, r1, c1) · ("fn", 이름, [인자…]) · ("bin", 연산, a, b) · ("un", 부호, a) · ("pct", a)."""
    if not isinstance(text, str) or not text.strip().startswith("="):
        raise FormulaError("수식은 「=」 로 시작해야 합니다")
    if len(text) > MAX_LEN:
        raise FormulaError(f"수식이 너무 깁니다({len(text)}자 > {MAX_LEN})")
    tk = tokens(text)
    if not tk:
        raise FormulaError("빈 수식")
    p = 0

    def peek(v=None):
        return p < len(tk) and tk[p][0] == "op" and (v is None or tk[p][1] == v)

    def expect(v):
        nonlocal p
        if not peek(v):
            raise FormulaError(f"「{v}」 가 있어야 할 자리")
        p += 1

    def ref_of(name):
        m = _REF.match(name.upper())
        return (int(m.group(4)) - 1, col_index(m.group(2))) if m else None

    def primary():
        nonlocal p
        if p >= len(tk):
            raise FormulaError("수식이 끊겼습니다")
        kind, v = tk[p]
        p += 1
        if kind in ("num", "str"):
            return (kind, v)
        if kind == "op" and v == "(":
            e = cmp()
            expect(")")
            return e
        if kind == "op" and v in "+-":
            return ("un", v, unary())
        if kind == "id":
            up = v.upper()
            if peek("("):
                p += 1
                if up not in FUNCTIONS:
                    raise FormulaError(f"모르는 함수 {up}")
                args = []
                if not peek(")"):
                    while True:
                        args.append(cmp())
                        if peek(","):
                            p += 1
                            continue
                        break
                expect(")")
                return ("fn", up, args)
            if up in ("TRUE", "FALSE"):
                return ("bool", up == "TRUE")
            a = ref_of(up)
            if a is None:
                raise FormulaError(f"주소도 함수도 아닌 이름 {v}")
            if peek(":"):
                p += 1
                b = ref_of(tk[p][1]) if p < len(tk) and tk[p][0] == "id" else None
                if b is None:
                    raise FormulaError("범위의 끝 주소가 없습니다")
                p += 1
                return ("range", min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            return ("ref", a[0], a[1])
        raise FormulaError(f"자리에 안 맞는 「{v}」")

    def postfix():
        nonlocal p
        e = primary()
        while peek("%"):
            p += 1
            e = ("pct", e)
        return e

    def unary():
        nonlocal p
        if peek("-") or peek("+"):
            op = tk[p][1]
            p += 1
            return ("un", op, unary())
        return postfix()

    def power():
        nonlocal p
        a = unary()
        if peek("^"):
            p += 1
            return ("bin", "^", a, power())
        return a

    def mul():
        nonlocal p
        a = power()
        while peek("*") or peek("/"):
            op = tk[p][1]
            p += 1
            a = ("bin", op, a, power())
        return a

    def add():
        nonlocal p
        a = mul()
        while peek("+") or peek("-") or peek("&"):
            op = tk[p][1]
            p += 1
            a = ("bin", op, a, mul())
        return a

    def cmp():
        nonlocal p
        a = add()
        while p < len(tk) and tk[p][0] == "op" and tk[p][1] in ("=", "<>", "<", ">", "<=", ">="):
            op = tk[p][1]
            p += 1
            a = ("bin", op, a, add())
        return a

    e = cmp()
    if p < len(tk):
        raise FormulaError(f"수식 뒤에 남은 「{tk[p][1]}」")
    return e


def rects(tree):
    """트리가 가리키는 주소들 [(r0, c0, r1, c1)…] — 나온 순서."""
    out = []

    def walk(e):
        k = e[0]
        if k == "ref":
            out.append((e[1], e[2], e[1], e[2]))
        elif k == "range":
            out.append(e[1:5])
        elif k == "fn":
            for a in e[2]:
                walk(a)
        elif k == "bin":
            walk(e[2])
            walk(e[3])
        elif k in ("un", "pct"):
            walk(e[2] if k == "un" else e[1])
    walk(tree)
    return out


def _num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError as e:
        raise FormulaError("#VALUE!") from e


def _truthy(v):
    return v != 0 if isinstance(v, (int, float)) and not isinstance(v, bool) else v if isinstance(v, bool) else v not in (None, "")


def _round(x, d, fn):
    m = 10 ** int(d or 0)
    return fn(x * m) / m


def evaluate(tree, value, cells=None):
    """트리 → 값(수 | 참거짓 | 글 | None). value(행, 열) = 칸 값. cells(r0, c0, r1, c1) = 범위의 칸 자리들(병합 칸을 한 번만 세게 — 없으면 자리마다).
    화면 엔진과 같은 뜻: 빈 값끼리의 더하기·곱·나누기는 빈 값, SUM 은 수만 더함, 0 으로 나누면 FormulaError("#DIV/0!")."""
    blank = lambda v: v is None or v == ""  # noqa: E731

    def flat(args):
        out = []
        for a in args:
            if a[0] == "range":
                spots = cells(*a[1:5]) if cells else [(r, c) for r in range(a[1], a[3] + 1) for c in range(a[2], a[4] + 1)]
                out += [value(r, c) for r, c in spots]
            else:
                out.append(ev(a))
        return out

    def nums(vals):
        return [float(v) if not isinstance(v, bool) else (1.0 if v else 0.0) for v in vals if isinstance(v, (int, float))]

    def one(v, f):
        return None if blank(v[0]) else f(_num(v[0]))

    def ev(e):
        k = e[0]
        if k in ("num", "str", "bool"):
            return e[1]
        if k == "ref":
            return value(e[1], e[2])
        if k == "range":
            spots = cells(*e[1:5]) if cells else [(e[1], e[2])]
            return value(*spots[0]) if spots else None
        if k == "pct":
            a = ev(e[1])
            return None if blank(a) else _num(a) / 100
        if k == "un":
            a = ev(e[2])
            return None if blank(a) else (-_num(a) if e[1] == "-" else _num(a))
        if k == "fn":
            name, args = e[1], e[2]
            if name == "IF":
                if not args:
                    raise FormulaError("#VALUE!")
                c = ev(args[0])
                return (ev(args[1]) if len(args) > 1 else True) if _truthy(c) else (ev(args[2]) if len(args) > 2 else False)
            v = flat(args)
            n = nums(v)
            if name == "SUM":
                return sum(n) if n else None
            if name == "AVERAGE":
                return sum(n) / len(n) if n else None
            if name == "MIN":
                return min(n) if n else None
            if name == "MAX":
                return max(n) if n else None
            if name == "COUNT":
                return float(len(n))
            if name == "COUNTA":
                return float(sum(1 for x in v if not blank(x)))
            if name in ("AND", "OR"):
                t = [_truthy(x) for x in v]
                return all(t) if name == "AND" else any(t)
            if not v:
                raise FormulaError("#VALUE!")
            if name == "NOT":
                return not _truthy(v[0])
            if name == "ABS":
                return one(v, abs)
            if name == "INT":
                return one(v, math.floor)
            if name == "SQRT":
                if not blank(v[0]) and _num(v[0]) < 0:
                    raise FormulaError("#NUM!")
                return one(v, math.sqrt)
            if name in ("ROUND", "ROUNDUP", "ROUNDDOWN"):
                if blank(v[0]):
                    return None
                x, d = _num(v[0]), _num(v[1]) if len(v) > 1 else 0
                if name == "ROUND":
                    return _round(x, d, lambda y: math.floor(y + 0.5))
                up = name == "ROUNDUP"
                return _round(x, d, lambda y: math.copysign(math.ceil(abs(y)) if up else math.floor(abs(y)), y))
            if name in ("MOD", "POWER"):
                if len(v) < 2 or blank(v[0]) or blank(v[1]):
                    return None
                a, b = _num(v[0]), _num(v[1])
                if name == "MOD":
                    if b == 0:
                        raise FormulaError("#DIV/0!")
                    return a - b * math.floor(a / b)
                return a ** b
            raise FormulaError("#NAME?")
        if k == "bin":
            op, a, b = e[1], ev(e[2]), ev(e[3])
            if op == "&":
                return f"{'' if a is None else a}{'' if b is None else b}"
            if op in ("=", "<>", "<", ">", "<=", ">="):
                x, y = ("" if a is None else a), ("" if b is None else b)
                if type(x) is not type(y) and not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                    return op == "<>"
                return {"=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]
            if blank(a) and blank(b):
                return None
            if (blank(a) or blank(b)) and op not in "+-":
                return None
            x, y = _num(a), _num(b)
            if op == "+":
                return x + y
            if op == "-":
                return x - y
            if op == "*":
                return x * y
            if op == "/":
                if y == 0:
                    raise FormulaError("#DIV/0!")
                return x / y
            try:
                return x ** y
            except (OverflowError, ZeroDivisionError) as err:
                raise FormulaError("#NUM!") from err
        raise FormulaError("#VALUE!")

    try:
        return ev(tree)
    except (OverflowError, RecursionError) as err:
        raise FormulaError("#NUM!") from err


def shift(text, dr, dc, rows=None, cols=None):
    """수식 글의 상대 주소를 (dr 행, dc 열) 옮긴다 — 엑셀의 채우기(`$E$3` 은 그대로, `E$3` 은 열만). 표(rows × cols) 밖으로 나가면 None. 글 상수 안은 안 건드린다."""
    bad = []

    def sub(m):
        if m.group(2) is None:  # 글 상수
            return m.group(0)
        c = col_index(m.group(2)) + (0 if m.group(1) else dc)
        r = int(m.group(4)) - 1 + (0 if m.group(3) else dr)
        if r < 0 or c < 0 or (rows is not None and r >= rows) or (cols is not None and c >= cols):
            bad.append(m.group(0))
            return m.group(0)
        return f"{m.group(1)}{col_letter(c)}{m.group(3)}{r + 1}"
    out = _REF_IN_TEXT.sub(sub, text or "")
    return None if bad else out


def canon(text):
    """견줄 꼴 — 글 상수 밖의 공백을 빼고 대문자로, `$` 는 뗀다(같은 칸을 가리키면 같은 수식)."""
    out = []
    for i, part in enumerate(re.split(r'("(?:[^"]|"")*")', text or "")):
        out.append(part if i % 2 else re.sub(r"\s+", "", part).upper().replace("$", ""))
    return "".join(out)
