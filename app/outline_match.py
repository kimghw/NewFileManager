"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 개요 오버레이(`app/outline_edit.py`) 위.

- 서식 갈래(`variants`): 슬롯(템플릿, 레벨)의 줄들을 비교 값(`look`)이 같은 것끼리 묶는다 — 접두(앞 공백·레터 글자·레터 뒤 공백) · 문단 · 레터 글자 · 본문 바탕 글자.
- 대표 정하기(`set_rep`) = 오버레이 슬롯의 rep·동결 접두·모양을 그 문단의 지금 것으로(문서는 안 바뀜).
- 대표에 맞추기(`match`) = 대표와 다른 슬롯 줄을 대표의 지금 모양으로(문서를 바꿈 — 부르는 쪽이 트랜잭션 안에서).
- 템플릿 종속(`merge`·`unmerge`·`carry`) = 템플릿 B 가 (A, at) 줄 아래 매달린 곳의 B 줄을 (A, at + 레벨)로 — 오버레이만 바꾼다.
"""
from app import outline_edit as OE
from app.hwpx_struct import OBJECTS, P, RUN

CHAR_KEYS = ("font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct")
PARA_KEYS = ("align", "line1Mm", "line2Mm", "indentRightMm", "spaceBeforePt", "spaceAfterPt", "lineSpacingPct")
# 비교 값의 차례(화면의 「대표와 다른 값」 차례) — 접두 → 문단 → 레터 글자(L.) → 본문 바탕 글자
KEYS = ("lead", "letter", "gap") + PARA_KEYS + tuple("L." + k for k in CHAR_KEYS) + CHAR_KEYS
LABELS = {"lead": "앞 공백", "letter": "레터", "gap": "레터 뒤 공백", "align": "정렬", "line1Mm": "앞 여백", "line2Mm": "2번째 줄",
          "indentRightMm": "오른쪽 여백", "spaceBeforePt": "위 간격", "spaceAfterPt": "아래 간격", "lineSpacingPct": "줄 간격",
          "font": "글꼴", "sizePt": "크기", "bold": "굵게", "italic": "기울임", "underline": "밑줄", "color": "색", "ratioPct": "장평", "spacingPct": "자간"}
LABELS.update({"L." + k: "레터 " + LABELS[k] for k in CHAR_KEYS})
_LIST_MAX = 30  # 갈래마다 보내는 줄 id 수


def _r(v, nd=1):
    return round(float(v), nd) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def ws(s):
    """공백 글을 사람이 읽는 꼴로 — 「2칸」 · 「탭」 · 「전각 1칸」 · 「없음」."""
    if not s:
        return "없음"
    parts, i = [], 0
    while i < len(s):
        ch, j = s[i], i
        while j < len(s) and s[j] == ch:
            j += 1
        n = j - i
        parts.append(f"{n}칸" if ch == " " else f"탭{n if n > 1 else ''}" if ch == "\t" else f"전각 {n}칸" if ch == "　" else f"U+{ord(ch):04X}×{n}")
        i = j
    return " + ".join(parts)


def _form(tok, key):
    """레터의 꼴 — 번호형은 번호 글자를 「#」 로(「3.」·「4.」 는 같은 꼴), 기호는 글자 그대로(「o」·「ㅇ」 는 다른 꼴)."""
    if not OE.is_numbered(key):
        return tok
    out, last = [], 0
    for s, e, t in OE._runs(tok):
        if OE._ordinal(t) is not None:
            out.append(tok[last:s] + "#")
            last = e
    out.append(tok[last:])
    return "".join(out)


def _runs_pos(doc, p):
    """[(시작, 끝, 런)] — 글자 자리(UTF-16 이 아니라 _text 와 같은 코드포인트 자리)."""
    out, pos = [], 0
    for r in p.iterchildren(RUN):
        k = sum(doc._clen(c) for c in r)
        out.append((pos, pos + k, r))
        pos += k
    return out


def _cid_at(doc, p, offset):
    """offset 글자가 든 런의 글자 모양 id — 글 끝이면 마지막 글 런, 런이 없으면 None."""
    last = None
    for a, b, r in _runs_pos(doc, p):
        if b > a:
            last = r.get("charPrIDRef")
            if a <= offset < b:
                return last
    return last


def _line_of(ov, pid):
    x = ov["lines"].get(pid)
    if x is None:
        raise ValueError("개요 줄이 아닙니다 — 헤딩 추출 2단계가 템플릿을 매긴 문단만 됩니다")
    return x


def _alive(doc, pid):
    el = doc._ids.get(pid)
    return el is not None and doc._attached(el)


def parts(doc, ov, pid):
    """줄 pid 의 접두 조각 (lead, tok, gap, plen, text)."""
    x = _line_of(ov, pid)
    text = doc._text(doc._ids[pid])
    lead, tok, gap = OE.prefix_of(text, x["letter"] or None)
    return lead, tok, gap, len(lead) + len(tok) + len(gap), text


def look(doc, ov, pid):
    """줄 pid 의 비교 값(KEYS) — 대표 갈래 묶음·다른 값의 바탕."""
    x = _line_of(ov, pid)
    p = doc._ids[pid]
    lead, tok, gap, plen, text = parts(doc, ov, pid)
    lc = _cid_at(doc, p, len(lead)) or doc._char_id(p)
    bc = _cid_at(doc, p, plen) if plen < len(text) else lc
    pp = p.get("paraPrIDRef")
    para, lch, bch = doc._summary(pp, lc), doc._summary(pp, lc), doc._summary(pp, bc)
    left, first = para.get("indentLeftMm"), para.get("firstLineMm")
    out = {"lead": lead, "letter": "" if x.get("role") in OE.ROOTED else _form(tok, x.get("key") or ""), "gap": gap}
    if left is None or first is None:
        out["line1Mm"] = out["line2Mm"] = None
    else:
        out["line1Mm"], out["line2Mm"] = _r(left + max(first, 0.0)), _r(left + max(-first, 0.0))
    for k in ("align", "indentRightMm", "spaceBeforePt", "spaceAfterPt"):
        out[k] = _r(para.get(k))
    out["lineSpacingPct"] = _r(para.get("lineSpacingPct"), 0)
    for k in CHAR_KEYS:
        out["L." + k] = _r(lch.get(k))
        out[k] = _r(bch.get(k))
    return out


def shown(key, v):
    """화면용 값 글 — 공백은 「2칸」, mm·pt·% 는 단위."""
    if key in ("lead", "gap"):
        return ws(v)
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "켬" if v else "끔"
    base = key[2:] if key.startswith("L.") else key
    if base.endswith("Mm"):
        return f"{v:g}mm"
    if base.endswith("Pt"):
        return f"{v:g}pt"
    if base in ("lineSpacingPct", "ratioPct", "spacingPct"):
        return f"{v:g}%"
    return str(v) if v != "" else "—"


def diff(a, b):
    """비교 값 a(대표) 와 b 의 다른 키 → [[키, 이름, 대표 글, b 글]…](KEYS 차례)."""
    return [[k, LABELS.get(k, k), shown(k, a.get(k)), shown(k, b.get(k))] for k in KEYS if a.get(k) != b.get(k)]


def _order(doc):
    """문단 id → 문서 차례(표 칸 안 포함)."""
    out = {}
    for sec in doc._sections:
        for p in sec.iter(P):
            i = doc._rev.get(p)
            if i is not None and i not in out:
                out[i] = len(out)
    return out


def slot_ids(ov, tid, level):
    return [pid for pid, x in ov["lines"].items() if x["tpl"] == str(tid) and int(x["level"]) == int(level)]


def variants(doc, ov, tid, level, order=None):
    """슬롯 (tid, level) 의 서식 갈래 → {total, rep, repMissing, groups[{key, count, paras(문서 순 30개까지), more, rep, look(화면 글), raw(원값), diff}]} — 대표 갈래 먼저, 그다음 줄 수 순."""
    order = order if order is not None else _order(doc)
    sl = OE._slot(ov, tid, level) or {}
    ids = sorted((p for p in slot_ids(ov, tid, level) if _alive(doc, p)), key=lambda p: order.get(p, 1 << 30))
    groups, looks = {}, {}
    for pid in ids:
        try:
            lk = look(doc, ov, pid)
        except (KeyError, ValueError):
            continue
        key = repr([lk.get(k) for k in KEYS])
        looks[pid] = lk
        groups.setdefault(key, {"key": key, "paras": [], "look": lk})["paras"].append(pid)
    rep = sl.get("rep") if sl.get("rep") in looks else None
    rep_key = repr([looks[rep].get(k) for k in KEYS]) if rep else None
    base = groups[rep_key]["look"] if rep_key else None
    out = []
    for g in groups.values():
        is_rep = g["key"] == rep_key
        out.append({"key": g["paras"][0], "count": len(g["paras"]), "paras": g["paras"][:_LIST_MAX], "more": max(0, len(g["paras"]) - _LIST_MAX),
                    "rep": is_rep, "look": {k: shown(k, v) for k, v in g["look"].items()}, "raw": g["look"],  # raw = 비교 값 원값(화면 「서식 비교」 의 견본 글 — outline_preview.js)
                    "diff": diff(base, g["look"]) if base and not is_rep else []})
    out.sort(key=lambda g: (not g["rep"], -g["count"], order.get(g["paras"][0], 1 << 30) if g["paras"] else 0))
    return {"tpl": str(tid), "level": int(level), "total": len(looks), "rep": rep, "repMissing": bool(ids) and rep is None,
            "others": sum(g["count"] for g in out if not g["rep"]) if rep else 0, "groups": out}


def all_variants(doc, ov):
    """모든 슬롯 → {tpl: {레벨: variants}}(줄이 있는 슬롯만)."""
    order = _order(doc)
    out = {}
    for tid, t in ov["templates"].items():
        for lv in t.get("slots", {}):
            if slot_ids(ov, tid, lv):
                out.setdefault(tid, {})[lv] = variants(doc, ov, tid, lv, order)
    return out


# ---------------------------------------------------------------- 대표 정하기 · 맞추기
def _check_member(ov, tid, level, pid):
    x = _line_of(ov, pid)
    if x["tpl"] != str(tid) or int(x["level"]) != int(level):
        raise ValueError(f"그 문단은 T{ov['templates'][str(tid)]['no']} L{level} 줄이 아닙니다(지금 T{x.get('no')} L{x['level']})")
    return x


def rep_shape(doc, ov, pid):
    """대표 문단의 지금 모양 → {lead, tok, gap, prefix, attrs{paraPrIDRef, styleIDRef, charPrIDRef(레터 런)}, body(본문 바탕 글자 모양 id)}."""
    lead, tok, gap, plen, text = parts(doc, ov, pid)
    if not tok:
        raise ValueError("대표 문단의 첫머리에 레터가 없습니다 — 다른 줄을 대표로 정하세요")
    p = doc._ids[pid]
    lc = _cid_at(doc, p, len(lead)) or doc._char_id(p)
    bc = _cid_at(doc, p, plen) if plen < len(text) else lc
    return {"lead": lead, "tok": tok, "gap": gap, "prefix": lead + tok + gap,
            "attrs": {"paraPrIDRef": p.get("paraPrIDRef", "0"), "styleIDRef": p.get("styleIDRef", "0"), "charPrIDRef": lc}, "body": bc,
            "first": ov["lines"][pid].get("first")}  # 대표 줄의 「저절로 맞춘 첫 줄 값」 기억(spec_hwpx_웹편집 ② §8-1) — 맞춘 줄도 같은 기억을 갖는다


def set_rep(doc, ov, tid, level, pid):
    """슬롯의 대표를 pid 로 — rep · 동결 접두(prefix·letter) · 모양 참조(attrs)를 그 문단의 지금 것으로. 문서는 안 바꾼다. -> 슬롯."""
    sl = OE._slot(ov, tid, level)
    if sl is None:
        raise KeyError("그런 템플릿 레벨이 없습니다")
    if not _alive(doc, pid):
        raise ValueError("그 문단이 지금 문서에 없습니다")
    _check_member(ov, tid, level, pid)
    sh = rep_shape(doc, ov, pid)
    sl.update(rep=pid, prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"], repSet=True)
    return sl


def match_targets(doc, ov, tid, level, paras=None, like=None):
    """대표와 비교 값이 다른 슬롯 줄(문서 순) — paras 를 주면 그 가운데 슬롯 줄만, like(그 슬롯의 줄 id)를 주면 그 줄과 비교 값이 같은 줄(그 갈래 — 화면이 보내는
    갈래의 줄 목록은 30줄까지라 갈래는 like 로: 2026-11-15 newfilemanager-af 지적)만. 대표·like 문제는 ValueError."""
    sl = OE._slot(ov, tid, level)
    if sl is None:
        raise KeyError("그런 템플릿 레벨이 없습니다")
    rep = sl.get("rep")
    if not rep or not _alive(doc, rep) or rep not in ov["lines"]:
        raise ValueError("이 레벨의 대표 문단이 문서에 없습니다 — 줄 하나를 대표로 정한 뒤 맞추세요")
    _check_member(ov, tid, level, rep)
    base = look(doc, ov, rep)
    if like is not None:
        if not _alive(doc, like):
            raise ValueError("그 갈래의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
        _check_member(ov, tid, level, like)
    kind = look(doc, ov, like) if like is not None else None
    order = _order(doc)
    want = set(paras) if paras else None
    out = []
    for pid in sorted(slot_ids(ov, tid, level), key=lambda p: order.get(p, 1 << 30)):
        if pid == rep or (want is not None and pid not in want) or not _alive(doc, pid):
            continue
        try:
            lk = look(doc, ov, pid)
            if lk != base and (kind is None or lk == kind):
                out.append(pid)
        except (KeyError, ValueError):
            continue
    return out


def match_one(doc, ov, pid, sh):
    """줄 pid 를 대표 모양 sh(rep_shape)로 — 접두 · 문단 모양·스타일 · 레터 런 · 옛 본문 바탕 글자 모양을 쓰던 런. -> 바뀐 줄의 새 레터."""
    x = ov["lines"][pid]
    p = doc._ids[pid]
    lead, tok, gap, plen, text = parts(doc, ov, pid)
    if not tok:
        raise ValueError(f"{pid} 의 첫머리에 레터가 없습니다")
    if x.get("role") in OE.ROOTED:
        new_tok = tok  # 괄호 줄 — 글 전체가 레터(구분 값)라 글은 그대로
    elif OE.is_numbered(x.get("key") or ""):
        new_tok = OE.with_numbers(sh["tok"], OE.numbers_of(tok)) or tok  # 대표 꼴에 제 번호
    else:
        new_tok = sh["tok"]
    new_prefix = sh["lead"] + new_tok + sh["gap"]
    # 옛 본문 바탕 글자 모양(접두 뒤 첫 글자의 런)을 쓰던 런의 자리(본문 시작에서 잰 것) — 접두를 바꾸면 런이 합쳐지고 갈라져 요소로는 못 좇는다
    old_body = _cid_at(doc, p, plen) if plen < len(text) else None
    body_spans = []
    for a, b, r in _runs_pos(doc, p) if old_body else ():
        if b > max(a, plen) and r.get("charPrIDRef") == old_body and not any(o.tag in OBJECTS for o in r):
            body_spans.append((max(a, plen) - plen, b - plen))
    doc.replace_prefix(pid, plen, new_prefix, attrs=sh["attrs"])
    body = sh.get("body") or sh["attrs"]["charPrIDRef"]
    if body_spans:
        n0 = len(new_prefix)
        for a, b in body_spans:
            doc._boundary(p, n0 + a)
            doc._boundary(p, n0 + b)
        for a, b, r in _runs_pos(doc, p):
            if b > a and not any(o.tag in OBJECTS for o in r) and any(n0 + s <= a and b <= n0 + e for s, e in body_spans):
                r.set("charPrIDRef", body)
        doc._tidy(p)
        doc._drop_cache(p)
        doc._touch(p)
    x["letter"] = new_tok
    if sh.get("first") is not None:  # 문단 모양을 대표 것으로 바꿨으니 저절로 맞춘 값의 기억도 대표 것 — 다르면 뒤의 글 고침이 사람이 정한 값으로 보고 안 맞춘다
        x["first"] = sh["first"]
    else:
        x.pop("first", None)
    return new_tok


# ---------------------------------------------------------------- 템플릿 종속
def _tpl(ov, tid):
    t = ov["templates"].get(str(tid))
    if t is None:
        raise KeyError(f"템플릿 {tid} 가 없습니다")
    return t


def context(doc, ov):
    """종속 판단의 문서 자리 — {"cell": 표 칸 안 줄 id 집합, "prev": 칸 안 줄 → 같은 칸의 바로 앞 줄(없으면 None)}.
    표 칸 안 노드는 그래프에서 부모가 칸 그릇이라 오버레이 부모가 비어 있다(spec_헤딩_추출 ② §6) — 칸 안에서는 바로 앞 줄을 매달린 자리로 본다."""
    from app.hwpx_struct import SUBLIST
    cell, prev, seen = set(), {}, set()
    for pid in ov["lines"]:
        el = doc._ids.get(pid)
        if el is None or not doc._attached(el):
            continue
        par = el.getparent()
        if par is None or par.tag != SUBLIST or par in seen:
            continue
        seen.add(par)
        last = None
        for c in par.iterchildren(P):
            q = doc._rev.get(c)
            if q in ov["lines"]:
                cell.add(q)
                prev[q] = last
                last = q
    return {"cell": cell, "prev": prev}


def attach(ov, pid, ctx=None):
    """줄 pid(템플릿 L1)가 매달린 줄 — 부모 줄이 있으면 그것, 칸 안에서 부모가 없으면 같은 템플릿 줄을 건너뛴 바로 앞 줄(ctx), 아니면 None."""
    x = ov["lines"][pid]
    if x.get("parent") in ov["lines"]:
        return x["parent"]
    if not ctx or pid not in ctx["cell"]:
        return None
    q = ctx["prev"].get(pid)
    while q is not None and ov["lines"][q]["tpl"] == x["tpl"]:
        q = ctx["prev"].get(q)
    return q


def _base(t):
    """템플릿의 시작 레벨 − 1 — 종속 템플릿(「T1T3」)은 부모 템플릿의 L at 아래에서 시작하므로 at, 보통 템플릿은 0."""
    return int(t.get("base") or 0)


def hang(ov, tid, ctx=None):
    """템플릿 tid 의 첫 레벨(L base+1) 줄이 매달린 자리 → 수: 「A|k」(매달린 줄의 템플릿·레벨 — attach) · 「root」(본문 최상위) · 「cell」(표 칸 — 앞에 매달 줄 없음)."""
    first = _base(ov["templates"].get(str(tid)) or {}) + 1
    out = {}
    for pid, x in ov["lines"].items():
        if x["tpl"] != str(tid) or int(x["level"]) != first:
            continue
        a = attach(ov, pid, ctx)
        p = ov["lines"][a] if a else None
        k = f"{p['tpl']}|{p['level']}" if p else ("cell" if ctx and pid in ctx["cell"] else "root")
        out[k] = out.get(k, 0) + 1
    return out


def _members(ov, tid, roots):
    """roots(B 첫 레벨 줄) 와 그 아래 B 줄(부모 사슬이 B 줄로만 roots 에 닿는 것)."""
    tid = str(tid)
    got = set(roots)
    changed = True
    while changed:
        changed = False
        for pid, x in ov["lines"].items():
            if pid not in got and x["tpl"] == tid and x.get("parent") in got:
                got.add(pid)
                changed = True
    return got


def comp_id(parent, child):
    """종속 템플릿의 id — 「부모+자식」(오버레이 템플릿 id 는 글 · 그래프 템플릿 id 는 정수 글이라 겹치지 않음)."""
    return f"{parent}+{child}"


def merge(ov, child, parent, at, ctx=None):
    """템플릿 child(B) 를 parent(A) 의 L at 아래로 — **종속 템플릿**(표기 「T{A}T{B}」, id 「A+B」)을 새로 만들어 (A, at) 줄 아래 매달린 B 줄을 거기로 옮긴다
    (2026-11-15 사용자 "T1 이 주고 종속이 T3 라면 T1T3 템플릿으로"). 종속 템플릿 = A 의 L1~L at(사슬만 — 그 레벨 줄은 A 것) + B 의 레벨들을 L at+1 부터: base = at.
    A 는 안 바뀐다(A 의 다른 줄 · Enter 가 그대로) · 레벨의 레터가 A 의 더 깊은 레벨과 달라도 된다(다른 템플릿). 오버레이만 바꾼다. -> 기록(merges 의 한 항목).
    ctx(context) 를 주면 표 칸 안에서 부모 줄이 없는 B 첫 줄도 바로 앞 줄로 매단다(그 줄의 부모를 그 (A, at) 줄로 — 떼면 되돌림)."""
    child, parent, at = str(child), str(parent), int(at)
    if child == parent:
        raise ValueError("템플릿을 제 아래로 넣을 수는 없습니다")
    A, B = _tpl(ov, parent), _tpl(ov, child)
    if OE._slot(ov, parent, at) is None:
        raise ValueError(f"T{A['no']} 에 L{at} 이 없습니다")
    cid = comp_id(parent, child)
    if cid in ov["templates"]:
        raise ValueError(f"T{B['no']} 는 이미 T{A['no']} 아래로 넣었습니다(T{ov['templates'][cid]['no']}) — 떼고 다시 넣으세요")
    bb = _base(B)
    roots, adopt = [], {}
    for pid, x in ov["lines"].items():
        if x["tpl"] != child or int(x["level"]) != bb + 1:
            continue
        a = attach(ov, pid, ctx)
        if a and ov["lines"][a]["tpl"] == parent and int(ov["lines"][a]["level"]) == at:
            roots.append(pid)
            if x.get("parent") != a:
                adopt[pid] = x.get("parent")  # 칸 안 — 부모가 없던 줄을 그 줄 아래로(떼면 되돌림)
    if not roots:
        raise ValueError(f"T{B['no']} 가 T{A['no']} L{at} 줄 아래 매달린 곳이 없습니다")
    for pid in adopt:
        ov["lines"][pid]["parent"] = attach(ov, pid, ctx)
    moved = sorted(_members(ov, child, roots))
    by_level = {}
    for pid in moved:
        by_level.setdefault(int(ov["lines"][pid]["level"]), []).append(pid)
    bchain = list(B.get("chain") or [])
    bmax = max([int(k) for k in B["slots"]] + [len(bchain), bb])
    achain = list(A.get("chain") or [])[:at]
    achain += [""] * (at - len(achain))
    chain = achain + bchain[bb:]
    slots = {}
    for k in range(bb + 1, bmax + 1):  # B 의 레벨 k → 종속 템플릿의 레벨 at + (k − bb)
        bsl = B["slots"].get(str(k))
        key = bchain[k - 1] if k - 1 < len(bchain) else (bsl or {}).get("key", "")
        sl = dict(bsl) if bsl else {"letter": key, "key": key, "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None}
        if sl.get("rep") not in by_level.get(k, ()):  # B 의 대표가 이 자리 밖(다른 곳에 매달린 B)이면 옮긴 줄의 첫 것을 대표로 — 동결 모양은 B 것 그대로
            sl["rep"] = (by_level.get(k) or [None])[0]
            sl.pop("repSet", None)
        slots[str(at + k - bb)] = sl
    C = {"no": f"{A['no']}T{B['no']}", "kind": B.get("kind"), "anchor": f"{A.get('anchor')}>{at}>{B.get('anchor')}", "chain": chain, "slots": slots,
         "max": at + bmax - bb, "base": at, "composite": {"parent": parent, "child": child, "at": at}}
    ov["templates"][cid] = C
    for k, sl in B["slots"].items():  # B 에 남는 줄이 있으면 B 의 대표는 남는 줄에서
        if sl.get("rep") in moved:
            rest = [pid for pid, x in ov["lines"].items() if x["tpl"] == child and str(x["level"]) == k and pid not in moved]
            sl["rep"] = rest[0] if rest else sl.get("rep")
    for pid in moved:
        x = ov["lines"][pid]
        lv = at + int(x["level"]) - bb
        x.update(tpl=cid, no=C["no"], level=lv, key=chain[lv - 1] if lv - 1 < len(chain) else x.get("key", ""))
    br = ov.setdefault("branches", {})
    for k in range(bb + 1, bmax + 1):  # B 레벨에 매달리던 가지 → 종속 템플릿의 그 레벨에도
        for c in br.get(f"{child}|{k}") or []:
            lst = br.setdefault(f"{cid}|{at + k - bb}", [])
            if c not in lst:
                lst.append(c)
    lst = br.setdefault(f"{parent}|{at}", [])  # 종속 템플릿은 (A, at) 에 매달린다(첫 레벨의 Alt+↑ · 부모 찾기)
    if cid not in lst:
        lst.append(cid)
    rec = {"child": B.get("anchor"), "parent": A.get("anchor"), "childId": child, "parentId": parent, "at": at, "id": cid, "moved": moved, "adopt": adopt}
    ov.setdefault("merges", []).append(rec)
    return rec


def unmerge(ov, child, parent):
    """merge 를 거꾸로 — 종속 템플릿의 줄 모두(넣은 뒤 Enter 로 만든 줄 포함)를 B 의 (레벨 − at + B 의 base)로 되돌리고 종속 템플릿을 지운다. -> 되돌린 줄 수.
    그 종속 템플릿으로 또 종속 템플릿을 만들었으면(겹친 종속) 그것부터 떼라고 거절."""
    child, parent = str(child), str(parent)
    A, B = _tpl(ov, parent), _tpl(ov, child)
    recs = ov.get("merges") or []
    rec = next((m for m in recs if m.get("childId") == child and m.get("parentId") == parent), None)
    if rec is None:
        raise ValueError(f"T{B['no']} 를 T{A['no']} 아래로 넣은 기록이 없습니다")
    cid = rec.get("id") or comp_id(parent, child)
    C = ov["templates"].get(cid) or {}
    for m in recs:
        if m is not rec and cid in (m.get("childId"), m.get("parentId")):
            other = ov["templates"].get(m.get("id"), {}).get("no", m.get("id"))
            raise ValueError(f"T{C.get('no', cid)} 로 만든 종속 템플릿 T{other} 가 있습니다 — 그것부터 떼세요")
    at, bb = int(rec["at"]), _base(B)
    bchain = list(B.get("chain") or [])
    back = 0
    for pid, x in ov["lines"].items():
        if x["tpl"] != cid:
            continue
        k = int(x["level"]) - at + bb
        x.update(tpl=child, no=B["no"], level=k, key=bchain[k - 1] if 0 < k <= len(bchain) else x.get("key", ""))
        if pid in (rec.get("adopt") or {}):
            x["parent"] = rec["adopt"][pid]
        back += 1
    ov["templates"].pop(cid, None)
    br = ov.get("branches") or {}
    for key in [k for k in br if k.split("|")[0] == cid]:
        br.pop(key, None)
    for lst in br.values():
        if cid in lst:
            lst.remove(cid)
    recs.remove(rec)
    return back


def carry(old, new, ctx=None):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 옛 오버레이의 종속(같은 앵커끼리 · 넣은 차례대로 — 겹친 종속도)을 다시 건다(ctx = context — 칸 안 매달림).
    사람이 정한 대표도 옮긴다. -> 못 건 것 [(기록, 까닭)]."""
    fails = []
    if not old or not new:
        return fails
    for m in old.get("merges") or []:
        by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}  # 앞의 종속이 만든 템플릿도 앵커로 찾게 매번
        c, p = by_anchor.get(m.get("child")), by_anchor.get(m.get("parent"))
        if c is None or p is None:
            fails.append((m, "템플릿이 없음"))
            continue
        try:
            merge(new, c, p, m["at"], ctx)
        except (KeyError, ValueError) as e:
            fails.append((m, str(e)))
    by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}
    for t in old.get("templates", {}).values():  # 사람이 정한 대표(repSet) — 그 문단이 새 오버레이에서도 같은 앵커·레벨 줄이면 그대로
        tid = by_anchor.get(t.get("anchor"))
        for lv, sl in t.get("slots", {}).items():
            if not sl.get("repSet") or tid is None:
                continue
            x = new["lines"].get(sl.get("rep"))
            nsl = OE._slot(new, tid, lv)
            if nsl is not None and x is not None and x["tpl"] == tid and str(x["level"]) == str(lv):
                nsl.update({k: sl.get(k) for k in ("rep", "prefix", "letter", "attrs", "bodyChar", "repSet")})
    return fails


def view_extra(ov, ctx=None):
    """오버레이 요약에 더할 것 — 템플릿마다 hang · lines · base · comp(종속 템플릿이면 {parent, parentNo, child, childNo, at}) ·
    made(이 템플릿을 넣어 만든 종속 템플릿들) · all(줄을 다 넣음), 레벨마다 rep(ctx = context — 칸 안 매달림)."""
    out = {}
    recs = ov.get("merges") or []
    tp = ov["templates"]
    for tid, t in tp.items():
        left = sum(1 for x in ov["lines"].values() if x["tpl"] == tid)
        comp = t.get("composite")
        made = [{"id": m.get("id"), "no": tp.get(m.get("id"), {}).get("no"), "parent": m["parentId"], "parentNo": tp.get(m["parentId"], {}).get("no"), "at": m["at"],
                 "moved": len(m.get("moved") or [])} for m in recs if m.get("childId") == tid]
        out[tid] = {"hang": hang(ov, tid, ctx), "lines": left, "base": _base(t), "made": made, "all": bool(made) and not left,
                    "comp": {**comp, "parentNo": tp.get(comp["parent"], {}).get("no"), "childNo": tp.get(comp["child"], {}).get("no")} if comp else None,
                    "slots": {lv: {"rep": sl.get("rep")} for lv, sl in t.get("slots", {}).items()}}
    return out


def apply_reps(g, ov):
    """그래프 g 의 템플릿 레벨 대표 문단(slots[].rep)을 사람이 정한 대표(오버레이 repSet)로 바꾼 **사본** — 서식 복사의 내용 서식 후보가 그 줄의 서식을 뽑게
    (spec_hwpx_웹편집 ② §8-2 · spec_서식복사 ② §12). 그 대표가 오버레이에서 같은 템플릿·레벨 줄일 때만. 바꿀 것이 없으면 g 그대로."""
    if not g or not ov:
        return g
    picks = {}
    for tid, t in (ov.get("templates") or {}).items():
        for lv, sl in (t.get("slots") or {}).items():
            x = ov["lines"].get(sl.get("rep")) if sl.get("repSet") else None
            if x is not None and x["tpl"] == tid and str(x["level"]) == str(lv):
                picks[(tid, int(lv))] = sl["rep"]
    if not picks:
        return g
    tpls = []
    for t in g.get("templates") or []:
        tid = str(t.get("id", t.get("no")))
        if any(k[0] == tid for k in picks):
            t = {**t, "slots": [{**s, "rep": picks.get((tid, int(s.get("level") or 0)), s.get("rep"))} for s in t.get("slots") or []]}
        tpls.append(t)
    return {**g, "templates": tpls}

