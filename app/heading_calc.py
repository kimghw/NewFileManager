"""헤딩 추출 3단계 — 표 의미(spec_헤딩_추출 ② §9): 구분 헤더(단계·차년도·기관·연도·합계·비율) · 구분 축·필드의 구분 값 · 계산식 표 판정 ·
합계/소계/비율/코드 수식을 엑셀 수식으로 바꿔 값 검증 · 표의 소속(2단계 헤딩 노드·구분 라벨·템플릿 앵커, 없으면 1단계 어림) · 엑셀(.xlsx) 내보내기.

3단계 `heading_tables.build` 가 띠(서브 테이블)·헤더 트리·필드 경로(rowPath·colPath)를 만든 뒤 표마다 `annotate` 를 부른다. 스크립트만(정규식·헤더 트리) —
문서를 다시 읽지 않고 LLM 도 부르지 않는다. 수식의 피연산자가 빈 칸이면 「미검증」(blank·incomplete)이라 빈 양식에서 거짓 불일치가 나지 않는다."""
import io
import re
from collections import Counter

BASIS = ("stage", "year", "org", "period", "total", "ratio")
DIV = ("stage", "year", "org", "period")
STATUS = ("ok", "mismatch", "missing", "incomplete", "blank", "nonnumeric")
TEXT_MAX = 30
MAX_LABELS = 50
MAX_FORMULAS = 400

_WS = re.compile(r"\s+")
_CODE = re.compile(r"\(\s*([A-Z])\s*\)")
_EXPR = re.compile(r"\(\s*([A-Z](?:\s*[+\-*/]\s*[A-Z])+)\s*\)")
_FOOT = re.compile(r"(?<=[가-힣A-Za-z\]）)])\s*\d{1,2}(?:-\d)?\)")  # 「연구개발비15)」「단계14-2)」 각주 번호
_UNIT_PAREN = re.compile(r"[\(（]\s*단위\s*[:：]?[^)）]*[\)）]|[\(（]\s*(?:%|％|원|천원|백만원|억원|명|건|개|회|년|개월|시간|점|㎡|kg|t)\s*[\)）]")
_UNIT_OF = re.compile(r"단위\s*[:：]?\s*([^)）\]】>\s,]{1,8})")
_N = r"(?:\d{1,3}|[nNxX]|[①-⑳⑴-⒇]|[Ⅰ-Ⅻⅰ-ⅻ])"
_STAGE_V = re.compile(rf"(?<![가-힣\w]){_N}\s*단계(?![가-힣])")
_YEAR_V = re.compile(rf"(?<![가-힣\w]){_N}\s*(?:차\s*년\s*도|년\s*차|연\s*차|차년)(?![가-힣])")
_YEAR_BARE = re.compile(rf"^{_N}\s*차$")
_PERIOD_V = re.compile(r"(?<![\d.])(?:19|20)(?:\d{2}|[xX×]{2}|YY)(?:\s*년|\.)?(?!\d)|YYYY")
_ORG_V = re.compile(r"(?:주관|공동|위탁|참여|협동|세부|국외|해외)\s*(?:연구\s*개발\s*)?기관(?:\s*\d{1,2}|\s*[①-⑳])?|기관명\s*기입|\[[^\]]*기관[^\]]*\]")
_ORG_PH = re.compile(r"^(?:[xXＸ×]{3,}|[oOㅇ○◯]{2,}\s*(?:기관|대학교?|연구원|주식회사|\(주\))?|\(주\)\s*[oOㅇ○◯]{2,})$")
_ORG_NOT = re.compile(r"중앙\s*행정|전문\s*기관|주무|관리\s*기관|평가\s*기관|지원\s*기관|전담\s*기관|행정\s*기관")
_STAGE_N = re.compile(r"^(?:사업\s*)?단\s*계(?:\s*구분|별)?$")
_YEAR_N = re.compile(r"차\s*년\s*도|연\s*차|년\s*차|연\s*도|년\s*도")
_ORG_N = re.compile(r"(?:연구\s*개발\s*)?기관\s*(?:명|유형|구분|별)?$|^소속(?:\s*기관)?(?:\s*\(.*\))?$|^참여\s*기관|^수행\s*기관|기관명")
_TOTAL = re.compile(r"^(?:총\s*)?(?:합\s*계|소\s*계|총\s*계|계|총\s*액|총\s*합|누\s*계|합|total|sum|subtotal)(?:\s*(?:금액|액))?$", re.I)
_SUBTOTAL = re.compile(r"소\s*계|subtotal", re.I)
_RATIO = re.compile(r"^(?:구성\s*)?비\s*율|^구성비|^비\s*중|^점유\s*(?:율|비율)|^ratio$|^share$", re.I)
_ORDINAL = re.compile(r"^(?:\d{1,3}|[①-⑳⑴-⒇]|[가-힣]|[a-zA-Z]|[ⅰ-ⅻⅠ-Ⅻ])\s*[.)]?$")
_DIGIT = re.compile(r"\d")
_NUM = re.compile(r"^([+\-−▲△]?)\s*(\(?)\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(\)?)\s*(%|％)?\s*"
                  r"(?:원|천원|백만원|억원|명|건|개|회|년|개월|월|일|시간|점|㎡|m|kg|t|톤|p)?$")
_DASH = re.compile(r"^[\-－—–ㅡ]+$")
_PH = re.compile(r"^0{1,3}(?:,0{3})+$|^0{2,}(?:%|％)?$|^[0○◯]{2,}$")  # 「0,000,000」「000,000」「00%」「○○」 자리표시
_PCT_END = re.compile(r"(?:%|％)\s*$")
_PCT_UNIT = re.compile(r"[\(（]\s*(?:단위\s*[:：]?\s*)?(?:%|％)\s*[\)）]|(?:%|％)\s*$")
_WEIGHT = re.compile(r"가중치|비중|비율|구성비|점유율|증감률|성장률|달성률|달성도|율$")


# ---- 글 다듬기 · 구분 헤더 ------------------------------------------------------------------------------------

def clean(text):
    return _WS.sub(" ", text or "").strip()


def core(text):
    """헤더의 핵심 글 — 코드 「(A)」·식 「(A/E)」·단위 괄호·각주 번호를 뗀 것."""
    s = clean(text)
    s = _EXPR.sub("", s)
    s = _CODE.sub("", s)
    s = _UNIT_PAREN.sub("", s)
    s = _FOOT.sub("", s)
    return _WS.sub(" ", s).strip(" :·-–—")


def key(text):
    return core(text).replace(" ", "").lower()


def header_basis(text, above=None):
    """헤더 칸 글 → {basis[], kind(name|value|total|ratio|None), subtotal?, code?, expr?, pctUnit?}. above = 같은 열 위 열헤더(또는 부모)의 판정 —
    순번 값(「1」)·자리표시(「XXXXX」)·「N차」 가 그 이름의 basis 를 받는다. pctUnit = 단위가 % 인 헤더(「가중치 (%)」 — 합계의 피연산자가 아님)."""
    raw = clean(text)
    c = core(raw)
    out = {"basis": [], "kind": None}
    m, e = _CODE.search(raw), _EXPR.search(raw)
    if m:
        out["code"] = m.group(1)
    if e:
        out["expr"] = _WS.sub("", e.group(1))
    if _PCT_UNIT.search(raw) or _WEIGHT.search(c):
        out["pctUnit"] = True
    if not c:
        return out
    if _TOTAL.match(c):
        out.update(basis=["total"], kind="total", subtotal=bool(_SUBTOTAL.search(c)))
        return out
    if _RATIO.search(c):
        out.update(basis=["ratio"], kind="ratio")
        return out
    ab = set((above or {}).get("basis") or [])
    vals = []
    if _STAGE_V.search(c):
        vals.append("stage")
    if _YEAR_V.search(c) or ("year" in ab and _YEAR_BARE.match(c)):
        vals.append("year")
    if _PERIOD_V.search(c):
        vals.append("period")
    if (_ORG_V.search(raw) and not _ORG_NOT.search(c)) or ("org" in ab and _ORG_PH.match(c)):
        vals.append("org")
    if vals:
        out.update(basis=vals, kind="value")
        return out
    names = []
    if len(c) <= 14 and not _DIGIT.search(c):
        if _STAGE_N.match(c):
            names.append("stage")
        if _YEAR_N.search(c):
            names.append("year")
        if _ORG_N.search(c) and not _ORG_NOT.search(c):
            names.append("org")
    if names:
        out.update(basis=names, kind="name")
        return out
    if above and above.get("kind") == "name" and _ORDINAL.match(c):
        out.update(basis=[b for b in above["basis"] if b in DIV], kind="value")
    return out


def label_basis(text):
    """칸 안 라벨 문단(「[주관연구개발기관(기관명 기입)]」「[1단계]」) → basis 목록."""
    raw = clean(text)
    c = core(raw)
    out = []
    if _STAGE_V.search(c):
        out.append("stage")
    if _YEAR_V.search(c):
        out.append("year")
    if _PERIOD_V.search(c):
        out.append("period")
    if _ORG_V.search(raw) and not _ORG_NOT.search(c):
        out.append("org")
    return out


# ---- 숫자 -------------------------------------------------------------------------------------------------

def parse_num(text, kinds=None):
    """필드 글 → {num, pct?, dec?, dash?, placeholder?, text?}. 전체가 수(부호·괄호 음수·쉼표·소수·뒤 단위·뒤 코드)일 때만 num.
    「-」 홀로 = 0(dash), 자리표시(1단계 kind placeholder·「0,000,000」·「00%」) = None(placeholder), 그 밖 글 = None(text)."""
    s = clean(text)
    s = _EXPR.sub("", s)
    s = _CODE.sub("", s).strip()
    if not s:
        return {"num": None}
    if _DASH.match(s):
        return {"num": 0.0, "dash": True}
    kinds = kinds or {}
    if (kinds.get("placeholder") and not kinds.get("data")) or _PH.match(s):
        return {"num": None, "placeholder": True}
    m = _NUM.match(s)
    if not m:
        return {"num": None, "text": True}
    sign, lp, ip, fp, rp, pct = m.groups()
    v = float(ip.replace(",", "") + (fp or ""))
    if sign in ("-", "−", "▲", "△") or (lp and rp):
        v = -v
    out = {"num": v, "dec": len(fp) - 1 if fp else 0}
    if pct:
        out["pct"] = True
    return out


def _fmt_num(v):
    if v is None:
        return None
    return int(v) if float(v).is_integer() and abs(v) < 1e15 else round(v, 6)


# ---- 엑셀 주소 ---------------------------------------------------------------------------------------------

def col_letter(c):
    s, c = "", c + 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def ref(cell):
    return f"{col_letter(cell['col'])}{cell['row'] + 1}"


def _sum_formula(ops):
    """이어진 한 줄(한 열의 잇단 행 · 한 행의 잇단 열)이면 SUM(범위), 아니면 더하기."""
    ops = sorted(ops, key=lambda x: (x["row"], x["col"]))
    if len(ops) >= 2:
        same_col = all(x["col"] == ops[0]["col"] for x in ops) and all(ops[i + 1]["row"] == ops[i]["row"] + ops[i]["rs"] for i in range(len(ops) - 1))
        same_row = all(x["row"] == ops[0]["row"] for x in ops) and all(ops[i + 1]["col"] == ops[i]["col"] + ops[i]["cs"] for i in range(len(ops) - 1))
        if same_col or same_row:
            return f"=SUM({ref(ops[0])}:{ref(ops[-1])})"
    return "=" + "+".join(ref(x) for x in ops)


# ---- 띠 안 구분 헤더 · 축 · 구분 값 ---------------------------------------------------------------------------------

def _band_cells(tb, band):
    (r0, r1), (c0, c1) = band["rows"], band["cols"]
    return [x for x in tb["cells"] if r0 <= x["row"] < r1 and c0 <= x["col"] < c1]


def _above_header(x, colheads):
    """행헤더 x 와 같은 열 위의 가장 가까운 열헤더(귀퉁이) — 그 이름(「단계」「연차」)이 순번 값의 basis."""
    cand = [h for h in colheads if h["row"] + h["rs"] <= x["row"] and h["col"] <= x["col"] < h["col"] + h["cs"]]
    return max(cand, key=lambda h: h["row"] + h["rs"]) if cand else None


def _depth(x, by_id):
    d, p, seen = 1, x.get("parent"), set()
    while p and p in by_id and p not in seen:
        seen.add(p)
        d += 1
        p = by_id[p].get("parent")
    return d


def _put(x, hb):
    """판정을 칸에 — 뜻 있는 키만(결과 크기)."""
    for k in ("basis", "basisKind", "code", "expr", "subtotal", "pctUnit"):
        x.pop(k, None)
    if hb.get("basis"):
        x["basis"] = hb["basis"]
    if hb.get("kind"):
        x["basisKind"] = hb["kind"]
    if hb.get("subtotal"):
        x["subtotal"] = True
    if hb.get("pctUnit"):
        x["pctUnit"] = True
    if hb.get("code"):
        x["code"] = hb["code"]
    if hb.get("expr"):
        x["expr"] = hb["expr"]


def band_basis(tb, band, by_id):
    """띠의 헤더 칸마다 basis 를 정하고 축(axes)·basis 요약을 띠에 적는다. 열헤더는 부모의 판정을, 행헤더는 같은 열 위 열헤더의 판정을 above 로."""
    cells = _band_cells(tb, band)
    colheads = [x for x in cells if x["role"] in ("colhead", "corner")]
    rowheads = [x for x in cells if x["role"] in ("rowhead", "corner")]
    judged = {}
    for x in sorted(colheads, key=lambda h: (h["row"], h["col"])):  # 위부터 — 부모가 먼저
        p = by_id.get(x.get("parent") or "")
        hb = header_basis(x["textFull"], judged.get(p["id"]) if p else None)
        judged[x["id"]] = hb
        _put(x, hb)
    for x in sorted(rowheads, key=lambda h: (h["col"], h["row"])):
        if x["role"] == "corner":
            continue
        above = _above_header(x, colheads)
        p = by_id.get(x.get("parent") or "")
        hb = header_basis(x["textFull"], judged.get(above["id"]) if above else (judged.get(p["id"]) if p else None))
        judged[x["id"]] = hb
        _put(x, hb)
    axes = {}
    for axis, heads in (("col", colheads), ("row", rowheads)):
        levels = {}
        for h in heads:
            hb = judged.get(h["id"]) or {}
            if not hb.get("basis") or hb["kind"] not in ("name", "value"):
                continue
            lv = levels.setdefault(_depth(h, by_id) if h["role"] != "corner" else 1, {"names": Counter(), "values": Counter(), "texts": {}})
            for b in hb["basis"]:
                if b not in DIV:
                    continue
                (lv["names"] if hb["kind"] == "name" else lv["values"])[b] += 1
                if hb["kind"] == "value":
                    lv["texts"].setdefault(b, []).append(core(h["textFull"])[:TEXT_MAX])
        out = []
        for level in sorted(levels):
            lv = levels[level]
            if lv["names"]:
                basis, kind = lv["names"].most_common(1)[0][0], "name"
            else:
                basis, kind = lv["values"].most_common(1)[0][0], "value"
            vals = []
            for t in lv["texts"].get(basis, []):
                if t not in vals:
                    vals.append(t)
            out.append({"level": level, "basis": basis, "kind": kind, "count": lv["values"][basis] + lv["names"][basis], "values": vals[:12]})
        axes[axis] = out
    band["axes"] = axes
    band["basis"] = sorted({b for hb in judged.values() if hb.get("kind") in ("name", "value") for b in hb["basis"] if b in DIV})
    for f in [x for x in cells if x["role"] == "field"]:
        div = {}
        for path in (f.get("rowPath") or [], f.get("colPath") or []):
            for cid in path:
                h = by_id.get(cid)
                if h is None or h.get("basisKind") != "value":
                    continue
                for b in h.get("basis") or []:
                    if b in DIV and b not in div:
                        div[b] = core(h["textFull"])[:TEXT_MAX]
        f.pop("div", None)
        if div:
            f["div"] = div
    return judged


# ---- 수식 --------------------------------------------------------------------------------------------------

def _is_ratio_head(h):
    return h.get("basisKind") == "ratio" or ("/" in (h.get("expr") or ""))


def _eff(path, f, by_id):
    """적용 경로 — 끝 헤더가 비율(또는 나누기 식)인데 값이 % 가 아니면 그 헤더를 뗀다(금액 줄과 비율 줄이 한 행헤더 아래 겹치는 양식)."""
    if len(path) >= 2 and not f.get("pct"):
        last = by_id.get(path[-1])
        prev = by_id.get(path[-2])
        if last is not None and _is_ratio_head(last) and prev is not None and not _is_ratio_head(prev):
            return list(path[:-1])
    return list(path)


def _pos(axis):
    """축의 「다른 쪽」 자리 키 — 열 축 수식은 같은 행을, 행 축 수식은 같은 열을 먼저 고른다."""
    return "row" if axis == "col" else "col"


def _pick(cands, f, axis):
    if not cands:
        return None
    p = _pos(axis)
    return sorted(cands, key=lambda g: (g[p] != f[p], abs(g[p] - f[p]), g["row"], g["col"]))[0]


def _belongs(fields, axis, hid, other):
    """헤더 hid 에 속하고(적용 경로의 끝) 다른 축 적용 경로가 other 인 필드들."""
    pk, ok = ("_effc", "_effr") if axis == "col" else ("_effr", "_effc")
    return [g for g in fields if g[pk] and g[pk][-1] == hid and tuple(g[ok]) == tuple(other)]


def _siblings(h, heads, by_id):
    """h 와 같은 부모의 형제 헤더(자리 순, h 포함)."""
    par = h.get("parent")
    axis_pos = "col" if h["role"] in ("colhead",) or (h["role"] == "corner") else "row"
    return sorted([s for s in heads if (s.get("parent") or None) == (par or None)], key=lambda s: (s[axis_pos], s["row"], s["col"]))


def _sum_operand_heads(h, heads, by_id):
    """합계 헤더 h 의 피연산 형제 — 소계가 있으면 소계들 + 어느 소계에도 안 든 항목, 없으면 total 아닌 항목 전부; 소계 h 는 제 묶음(앞 total 뒤 ~ h) 항목만."""
    sibs = [s for s in _siblings(h, heads, by_id) if s is h or not (s.get("pctUnit") or s.get("basisKind") == "ratio" or _is_ratio_head(s))]
    is_total = lambda s: "total" in (s.get("basis") or [])  # noqa: E731
    if h.get("subtotal"):
        group = []
        for s in sibs:
            if s is h:
                return group
            if is_total(s):
                group = []
            else:
                group.append(s)
        return []
    subs, items, group = [], [], []
    for s in sibs:
        if s is h:
            continue
        if is_total(s):
            if s.get("subtotal"):
                subs.append(s)
                group = []
            else:
                items += group  # 다른 합계 앞의 항목은 어느 소계에도 안 들었음
                group = []
        else:
            group.append(s)
    items += group
    return subs + items if subs else items


def _ratio_base(h, heads, by_id):
    sibs = _siblings(h, heads, by_id)
    i = next((k for k, s in enumerate(sibs) if s is h), -1)
    ok = lambda s: not any(b in ("total", "ratio") for b in (s.get("basis") or [])) and not _is_ratio_head(s)  # noqa: E731
    before = [s for s in sibs[:i] if ok(s)]
    after = [s for s in sibs[i + 1:] if ok(s)]
    return before[-1] if before else (after[0] if after else None)


def _eval_expr(expr, values):
    """「A/E」「B+C」 식 → 값(변수 값 dict). 곱·나누기 먼저, 왼쪽부터. 0 으로 나누면 None."""
    cur, op = None, "+"
    tokens = re.findall(r"[A-Z]|[+\-*/]", expr)
    stack = []
    for t in tokens:
        if t in "+-":
            stack.append(("num", cur, op))
            cur, op = None, t
            continue
        if t in "*/":
            op = op + t
            continue
        v = values[t]
        if cur is None:
            cur = v
        elif op.endswith("*"):
            cur = cur * v
            op = op[:-1]
        elif op.endswith("/"):
            if v == 0:
                return None
            cur = cur / v
            op = op[:-1]
    stack.append(("num", cur, op))
    total = 0.0
    for _, v, o in stack:
        if v is None:
            continue
        total = total - v if o.startswith("-") else total + v
    return total


def _expr_formula(expr, refs, pct):
    out = re.sub(r"[A-Z]", lambda m: refs[m.group(0)], expr)
    out = out.replace("*", "*").replace("/", "/")
    if "/" in expr and pct:
        return f"=({out})*100"
    return "=" + out


def _verify(f, operands, calc, ratio=False):
    nums = [g.get("num") for g in operands]
    if all(v is None for v in nums):
        return None, "blank", None
    if any(v is None for v in nums):
        return None, "incomplete", None
    expected = calc(nums)
    if expected is None:
        return None, "incomplete", None
    actual = f.get("num")
    if actual is None:
        return expected, ("nonnumeric" if f.get("nonnum") else "missing"), None
    tol = 0.5 * 10 ** (-int(f.get("dec") or 0)) + (0.05 if ratio else 0.0) + 1e-9
    diff = actual - expected
    return expected, ("ok" if abs(diff) <= tol else "mismatch"), diff


def band_formulas(tb, band, by_id, next_id):
    """띠의 수식 목록(spec ② §9) — 필드마다 축별로 하나: 코드 식 > 합계 > 비율. 양 축이 모두 합계인 칸은 둘 다 적되 엑셀 수식은 행 축 하나."""
    cells = _band_cells(tb, band)
    fields = [x for x in cells if x["role"] == "field"]
    heads = {"col": [x for x in cells if x["role"] in ("colhead", "corner")], "row": [x for x in cells if x["role"] in ("rowhead", "corner")]}
    for f in fields:
        f["_effc"] = _eff(f.get("colPath") or [], f, by_id)
        f["_effr"] = _eff(f.get("rowPath") or [], f, by_id)
    codes = {axis: {h["code"]: h for h in hs if h.get("code")} for axis, hs in heads.items()}
    out = []
    for f in fields:
        found = {}
        for axis in ("col", "row"):
            path = f["_effc"] if axis == "col" else f["_effr"]
            other = f["_effr"] if axis == "col" else f["_effc"]
            if not path:
                continue
            last = by_id.get(path[-1])
            rec = None
            if last is not None and last.get("expr"):
                rec = _expr_record(f, last, axis, other, fields, codes, by_id)
            if rec is None:
                for i in range(len(path) - 1, -1, -1):
                    h = by_id.get(path[i])
                    if h is None or "total" not in (h.get("basis") or []):
                        continue
                    rec = _sum_record(f, h, i, path, axis, other, fields, heads[axis], by_id)
                    if rec is not None:
                        break
            if rec is None and last is not None and last.get("basisKind") == "ratio":
                rec = _ratio_record(f, last, axis, other, fields, heads[axis], by_id)
            if rec is not None:
                found[axis] = rec
        if not found:
            continue
        excel_axis = "row" if "row" in found else "col"
        for axis, rec in found.items():
            rec.update(id=f"f{next_id + len(out) + 1}", cell=f["id"], ref=ref(f), axis=axis, excel=(axis == excel_axis), sub=band["id"])
            out.append(rec)
            f.setdefault("formulas", []).append(rec["id"])
    for f in fields:
        f.pop("_effc", None)
        f.pop("_effr", None)
    return out


def _finish_record(f, kind, operands, formula, calc, ratio=False, note=""):
    expected, status, diff = _verify(f, operands, calc, ratio)
    return {"kind": kind, "formula": formula, "operands": [g["id"] for g in operands], "expected": _fmt_num(expected), "actual": _fmt_num(f.get("num")),
            "status": status, "diff": _fmt_num(diff), "note": note}


def _sum_record(f, h, i, path, axis, other, fields, heads, by_id):
    tail_of = lambda ids: tuple(k for k in (key(by_id[c]["textFull"]) for c in ids if c in by_id) if k)  # noqa: E731 — 글 없는 헤더(「계 | (빈 칸)」)는 투명
    tail = tail_of(path[i + 1:])
    pk = "_effc" if axis == "col" else "_effr"
    ok = "_effr" if axis == "col" else "_effc"
    same_pct = lambda g: bool(g.get("pct")) == bool(f.get("pct")) or g.get("num") is None  # noqa: E731 — % 값은 금액 합의 피연산자가 아님
    ops = []
    for s in _sum_operand_heads(h, heads, by_id):
        under = [g for g in fields if g is not f and len(g[pk]) > i and g[pk][:i] == path[:i] and g[pk][i] == s["id"] and tuple(g[ok]) == tuple(other) and same_pct(g)]
        cands = [g for g in under if tail_of(g[pk][i + 1:]) == tail]
        g = _pick(cands, f, axis)
        if g is not None:
            ops.append(g)
            continue
        if tail:
            continue
        # 꼬리 없는 합계(「계」 행이 「전담기관 › 지표1·지표2」 묶음 전체를 더함) — 형제 아래 잎 필드 전부, 안쪽에 소계가 있으면 가장 얕은 소계들만
        inner = [g for g in under if any("total" in (by_id[c].get("basis") or []) for c in g[pk][i + 1:] if c in by_id)]
        if inner:
            depth = min(next(k for k, c in enumerate(g[pk][i + 1:]) if c in by_id and "total" in (by_id[c].get("basis") or [])) for g in inner)
            ops += [g for g in inner if next(k for k, c in enumerate(g[pk][i + 1:]) if c in by_id and "total" in (by_id[c].get("basis") or [])) == depth]
        else:
            ops += sorted(under, key=lambda g: (g["row"], g["col"]))
    if not ops:
        return None
    note = f"{core(h['textFull'])[:20]} = " + " + ".join(core(by_id[g[('_effc' if axis == 'col' else '_effr')][i]]["textFull"])[:12] for g in ops)
    return _finish_record(f, "sum", ops, _sum_formula(ops), lambda v: sum(v), note=note)


def _expr_record(f, last, axis, other, fields, codes, by_id):
    expr = last["expr"]
    vals, refs, ops = {}, {}, []
    for code in dict.fromkeys(re.findall(r"[A-Z]", expr)):
        hx = codes[axis].get(code)
        g = None
        if hx is not None:
            g = _pick(_belongs(fields, axis, hx["id"], other), f, axis)
        if g is None:
            oaxis = "row" if axis == "col" else "col"
            hx = codes[oaxis].get(code)
            if hx is not None:
                mine = (f["_effc"] if axis == "col" else f["_effr"])[:-1]
                g = _pick(_belongs(fields, oaxis, hx["id"], mine), f, oaxis)
        if g is None:
            return None
        vals[code] = g
        refs[code] = ref(g)
        ops.append(g)
    pct = bool(f.get("pct"))
    ratio = "/" in expr

    def calc(nums):
        v = _eval_expr(expr, {c: n for c, n in zip(vals, nums)})
        return None if v is None else (v * 100 if ratio and pct else v)
    return _finish_record(f, "expr", ops, _expr_formula(expr, refs, pct), calc, ratio=ratio, note=f"{core(last['textFull'])[:20]} ({expr})")


def _ratio_record(f, last, axis, other, fields, heads, by_id):
    base = _ratio_base(last, heads, by_id)
    if base is None:
        return None
    num = _pick(_belongs(fields, axis, base["id"], other), f, axis)
    if num is None:
        return None
    ok = "_effr" if axis == "col" else "_effc"
    pk = "_effc" if axis == "col" else "_effr"
    den = None
    for g in fields:
        if not g[pk] or g[pk][-1] != base["id"]:  # 합계 줄 자신의 비율(100%)은 분자 = 분모
            continue
        op = g[ok]
        for j in range(len(op) - 1, -1, -1):
            hj = by_id.get(op[j])
            if hj is not None and "total" in (hj.get("basis") or []) and list(op[:j]) == list(other[:j]):
                if den is None or j > den[1]:
                    den = (g, j)
                break
    if den is None:
        return None
    den = den[0]
    formula = f"={ref(num)}/{ref(den)}*100"  # 비율 헤더의 값은 백분율로 본다(「12.5」 도)
    return _finish_record(f, "ratio", [num, den], formula, lambda v: None if v[1] == 0 else v[0] / v[1] * 100, ratio=True,
                          note=f"{core(last['textFull'])[:20]} = {core(base['textFull'])[:12]} ÷ 합계 × 100")


# ---- 단위 · 계산식 판정 ---------------------------------------------------------------------------------------

def _unit(tb, before=""):
    for x in tb["cells"]:
        if x["role"] in ("title", "note", "corner", "colhead"):
            m = _UNIT_OF.search(x["textFull"] or "")
            if m:
                return m.group(1)
    m = _UNIT_OF.search(before or "")
    return m.group(1) if m else None


def band_calc(tb, band, by_id, formulas):
    cells = _band_cells(tb, band)
    heads = [x for x in cells if x["role"] in ("colhead", "rowhead", "corner")]
    fields = [x for x in cells if x["role"] == "field"]
    nums = [x for x in fields if x.get("num") is not None and not x.get("dash")]
    rows, cols = {x["row"] for x in nums}, {x["col"] for x in nums}
    has_total = any("total" in (h.get("basis") or []) for h in heads)
    has_ratio = any(h.get("basisKind") == "ratio" for h in heads)
    has_expr = any(h.get("expr") for h in heads)
    why = []
    if has_total:
        why.append("합계 헤더")
    if has_ratio:
        why.append("비율 헤더")
    if has_expr:
        why.append("코드 식")
    if len(nums) >= 4 and len(rows) >= 2 and len(cols) >= 2:
        why.append(f"숫자 필드 {len(nums)}")
    mine = [r for r in formulas if r["sub"] == band["id"]]
    is_calc = band["kind"] in ("matrix", "form", "plain") and bool(why)
    counts = Counter(r["status"] for r in mine)
    band["calc"] = {"is": is_calc, "why": " · ".join(why), "numeric": len(nums), "formulas": len(mine), **{s: counts.get(s, 0) for s in STATUS}}
    return band["calc"]


# ---- 소속(2단계 그래프 · 1단계 어림) ----------------------------------------------------------------------------

def _node_text(nd):
    """노드 글 = 레터 + 제목(그래프 노드의 text 는 레터 뒤 글만 — 「8-1.」 + 「연구개발비 지원·부담계획」, 라벨은 레터가 라벨 글 전체)."""
    return clean(f"{nd.get('letter') or ''} {nd.get('text') or ''}")


def _node_owner(nd, nodes):
    path, p, hops = [], nd.get("parent"), 0
    while p in nodes and hops < 40:
        path.append(_node_text(nodes[p])[:40])
        p = nodes[p].get("parent")
        hops += 1
    path.reverse()
    div = nd if nd.get("role") == "label" else nodes.get(nd.get("division") or "")
    division = None
    if div:
        division = {"id": div["id"], "para": div.get("para"), "text": _node_text(div)[:60], "key": div.get("key"), "basis": label_basis(_node_text(div))}
    return {"id": nd["id"], "para": nd.get("para"), "text": _node_text(nd)[:80], "blank": bool(nd.get("blank")), "role": nd.get("role"),
            "template": nd.get("template"), "tplNo": nd.get("tplNo"), "level": nd.get("level"), "path": path, "division": division, "source": "stage2"}


def owners_index(stage1, stage2=None):
    """표 → 소속. 2단계 결과(같은 1단계 실행)가 있으면 그래프의 tbl: 그릇 parent 를 따라 헤딩 노드까지, 없으면(그 표가 그래프에 없으면) 1단계 어림."""
    paras = stage1.get("paras") or []
    cont = {c["id"]: c for c in (stage2 or {}).get("containers") or []} if stage2 else {}
    nodes = {n["id"]: n for n in (stage2 or {}).get("nodes") or []} if stage2 else {}

    def from_graph(tb):
        cur = cont.get(f"tbl:{tb['id']}")
        if cur is None:
            return None
        p, hops = cur.get("parent"), 0
        while p and hops < 30:
            if p in nodes:
                return _node_owner(nodes[p], nodes)
            if p == "root" or str(p).startswith("area:"):
                return {"source": "stage2", "root": True}
            c = cont.get(p)
            if c is None:
                return None
            p, hops = c.get("parent"), hops + 1
        return {"source": "stage2", "root": True} if p in (None, "root") else None

    def from_stage1(tb):
        n = tb.get("n") or 0
        owner = div = None
        for i in range(min(n, len(paras)) - 1, max(-1, n - 800), -1):
            rec = paras[i]
            if rec.get("area") != "body" or rec.get("kind") not in ("marker", "label") or rec.get("blank") or not clean(rec.get("text")):
                continue
            if rec["kind"] == "label":
                if div is None:
                    div = rec
                continue
            owner = rec
            break
        base = owner or div
        if base is None:
            return None
        division = None
        if div is not None:
            division = {"id": div["id"], "para": div["id"], "text": clean(div["text"])[:60], "key": None, "basis": label_basis(div["text"])}
        return {"id": base["id"], "para": base["id"], "text": clean(base["text"])[:80], "role": "heading" if owner else "label", "template": None,
                "tplNo": None, "level": None, "path": [], "division": division, "source": "stage1"}

    def owner(tb):
        o = from_graph(tb) if cont else None
        return o if o is not None else from_stage1(tb)
    return owner


# ---- 표 하나 ------------------------------------------------------------------------------------------------

def annotate(tb, subs, owner_fn=None, before=""):
    """3단계 표(칸 역할·경로가 있는 tb, 띠 subs) → 표 의미. 칸에 basis·num·div·formulas 를, 띠에 axes·basis·calc 를 적고 표 수준 키를 돌려준다."""
    by_id = {x["id"]: x for x in tb["cells"]}
    labels = []
    for x in tb["cells"]:
        for k in ("num", "pct", "dec", "dash", "placeholder", "nonnum", "formulas"):
            x.pop(k, None)
        if x["role"] == "field":
            p = parse_num(x["textFull"], x.get("kinds"))
            x["num"] = p.get("num")
            for k in ("pct", "dec", "dash", "placeholder", "text"):
                if p.get(k):
                    x[k if k != "text" else "nonnum"] = p[k]
        if (x.get("kinds") or {}).get("label") and len(labels) < MAX_LABELS:
            labels.append({"cell": x["id"], "text": clean(x["textFull"])[:60], "basis": label_basis(x["textFull"])})
    for b in subs:
        band_basis(tb, b, by_id)
    formulas = []
    for b in subs:
        if b["kind"] not in ("matrix", "form", "plain"):
            b["calc"] = {"is": False, "why": "", "numeric": 0, "formulas": 0, **{s: 0 for s in STATUS}}
            continue
        formulas += band_formulas(tb, b, by_id, len(formulas))
    formulas = formulas[:MAX_FORMULAS]
    for b in subs:
        if b["kind"] in ("matrix", "form", "plain"):
            band_calc(tb, b, by_id, formulas)
    for x in tb["cells"]:
        x.pop("nonnum", None)
    counts = Counter(r["status"] for r in formulas)
    calc = {"is": any(b["calc"]["is"] for b in subs), "formulas": len(formulas), **{s: counts.get(s, 0) for s in STATUS}}
    basis = sorted({b for s in subs for b in s.get("basis") or []} | {b for l in labels for b in l["basis"]})
    owner = owner_fn(tb) if owner_fn else None
    return {"owner": owner, "labels": labels, "basis": basis, "unit": _unit(tb, before), "formulas": formulas, "calc": calc}


def counts(tables):
    """전체 요약 — 계산식 표·수식 상태·basis 별 표 수·소속 출처."""
    calc, basis, owners, basis_tables = Counter(), Counter(), Counter(), 0
    for t in tables:
        c = t.get("calc") or {}
        if c.get("is"):
            calc["tables"] += 1
        calc["formulas"] += c.get("formulas", 0)
        for s in STATUS:
            calc[s] += c.get(s, 0)
        for b in t.get("basis") or []:
            basis[b] += 1
        if t.get("basis"):
            basis_tables += 1
        o = t.get("owner")
        owners[(o or {}).get("source") or "none"] += 1
    return {"calc": {k: calc[k] for k in ("tables", "formulas") + STATUS}, "basis": {b: basis[b] for b in DIV}, "basisTables": basis_tables,
            "owners": dict(owners)}


# ---- 엑셀 --------------------------------------------------------------------------------------------------

_FILL = {"colhead": "DCE6F1", "rowhead": "E2EFDA", "corner": "E4DFEC", "title": "FCE4D6", "note": "F2F2F2", "spacer": "F2F2F2"}
_STAT_FILL = {"ok": "E2F0D9", "mismatch": "F8CBAD", "missing": "FFE699", "nonnumeric": "F8CBAD"}
_STAT_KO = {"ok": "일치", "mismatch": "불일치", "missing": "미기입", "incomplete": "미검증(일부 빈 칸)", "blank": "미검증(빈 칸)", "nonnumeric": "수가 아님"}


def workbook(t, doc_name=""):
    """3단계 결과의 표 하나 → .xlsx 바이트. 시트 「표」(격자·병합·역할 색·숫자·수식 칸은 엑셀 수식 + 메모) · 「검증」 · 「필드」. openpyxl 이 없으면 ImportError."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "표"
    cells = t.get("cells") or []
    by_id = {x["id"]: x for x in cells}
    fmap = {}
    for f in t.get("formulas") or []:
        if f.get("excel"):
            fmap[f["cell"]] = f
    for x in cells:
        r, c = x["row"] + 1, x["col"] + 1
        cell = ws.cell(row=r, column=c)
        f = fmap.get(x["id"])
        if f:
            cell.value = f["formula"]
            cell.comment = Comment(f"문서 값: {x.get('text') or '(빈 칸)'} · 상태: {_STAT_KO.get(f['status'], f['status'])} · 기대값: {f.get('expected')}"
                                   + (f" · {f.get('note')}" if f.get("note") else ""), "NewFileManager")
            fill = _STAT_FILL.get(f["status"])
            if fill:
                cell.fill = PatternFill("solid", start_color=fill)
        elif x["role"] == "field" and x.get("num") is not None and not x.get("dash"):
            cell.value = _fmt_num(x["num"])
            if x.get("pct"):
                cell.number_format = '0.0"%"' if (x.get("dec") or 0) else '0"%"'
        else:
            cell.value = x.get("text") or None
        if x["role"] in _FILL:
            cell.fill = PatternFill("solid", start_color=_FILL[x["role"]])
            cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if x["rs"] > 1 or x["cs"] > 1:
            ws.merge_cells(start_row=r, start_column=c, end_row=r + x["rs"] - 1, end_column=c + x["cs"] - 1)
    for c in range(1, (t.get("cols") or 0) + 1):
        ws.column_dimensions[col_letter(c - 1)].width = 13
    name = lambda cid: (clean(by_id[cid].get("text")) if cid in by_id else cid) or "(빈 칸)"  # noqa: E731
    path = lambda ids: " › ".join(name(i) for i in ids or [])  # noqa: E731
    sub = lambda cid: (by_id.get(cid) or {}).get("sub") or ""  # noqa: E731
    v = wb.create_sheet("검증")
    v.append(["수식", "칸", "주소", "서브 테이블", "축", "종류", "엑셀 수식", "기대값", "문서 값", "상태", "차이", "행헤더", "열헤더", "설명"])
    for f in t.get("formulas") or []:
        x = by_id.get(f["cell"]) or {}
        v.append([f["id"], f["cell"], f["ref"], f.get("sub") or sub(f["cell"]), "열" if f["axis"] == "col" else "행", f["kind"], f["formula"], f.get("expected"),
                  x.get("text"), _STAT_KO.get(f["status"], f["status"]), f.get("diff"), path(x.get("rowPath")), path(x.get("colPath")), f.get("note")])
    p = wb.create_sheet("필드")
    p.append(["칸", "주소", "서브 테이블", "행헤더 경로", "열헤더 경로", "단계", "차년도", "기관", "연도", "값(수)", "글", "수식"])
    for x in cells:
        if x["role"] != "field":
            continue
        d = x.get("div") or {}
        p.append([x["id"], ref(x), x.get("sub"), path(x.get("rowPath")), path(x.get("colPath")), d.get("stage"), d.get("year"), d.get("org"), d.get("period"),
                  _fmt_num(x.get("num")), x.get("text"), ", ".join(x.get("formulas") or [])])
    for sh in (v, p):
        for col in sh.columns:
            sh.column_dimensions[col[0].column_letter].width = 18
        sh.freeze_panes = "A2"
    info = wb.create_sheet("정보")
    o = t.get("owner") or {}
    info.append(["문서", doc_name])
    info.append(["표", t.get("id"), f"{t.get('rows')}×{t.get('cols')}", f"칸 {len(cells)}"])
    info.append(["앞 문단", t.get("before")])
    info.append(["소속", o.get("text"), (f"T{o['tplNo']} L{o['level']}" if o.get("tplNo") else ""), " › ".join(o.get("path") or []), o.get("source")])
    info.append(["구분 라벨", ((o.get("division") or {}).get("text"))])
    info.append(["구분", ", ".join(t.get("basis") or [])])
    info.append(["단위", t.get("unit")])
    c = t.get("calc") or {}
    info.append(["계산식", "예" if c.get("is") else "아니오", f"수식 {c.get('formulas', 0)}", *[f"{_STAT_KO[s]} {c.get(s, 0)}" for s in STATUS]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
