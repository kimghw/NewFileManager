"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 개요 오버레이(`app/outline_edit.py`) 위.

- 서식 갈래(`variants`): 슬롯(템플릿, 레벨)의 줄들을 비교 값(`look`)이 같은 것끼리 묶는다 — 접두(앞 공백·레터 글자·레터 뒤 공백) · 문단 · 레터 글자 · 본문 바탕 글자.
- 대표 정하기(`set_rep`) = 오버레이 슬롯의 rep·동결 접두·모양을 그 문단의 지금 것으로(문서는 안 바뀜).
- 대표에 맞추기(`match`) = 대표와 다른 슬롯 줄을 대표의 지금 모양으로(문서를 바꿈 — 부르는 쪽이 트랜잭션 안에서).
- 템플릿 종속(`merge`·`unmerge`·`carry`) = 템플릿 B 가 (A, at) 줄 아래 매달린 곳의 B 줄을 (A, at + 레벨)로 — 오버레이만 바꾼다.
- 서식 종속 템플릿(`split`·`unsplit` — ② §8-5) = (A, Lk) 의 일부러 다른 서식 갈래를 「T{A}L{k}a」 로 뗀다(그 줄과 자손 · base = k − 1) — 오버레이만 바꾼다.
"""
import copy

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


def variants(doc, ov, tid, level, order=None, full=False):
    """슬롯 (tid, level) 의 서식 갈래 → {total, rep, repMissing, groups[{key, count, paras(문서 순 30개까지 — full 이면 전부), more, rep, look(화면 글), raw(원값), diff}]} — 대표 갈래 먼저, 그다음 줄 수 순."""
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
        out.append({"key": g["paras"][0], "count": len(g["paras"]), "paras": g["paras"] if full else g["paras"][:_LIST_MAX], "more": 0 if full else max(0, len(g["paras"]) - _LIST_MAX),
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


def match_set(doc, ov, tid, level, rep=None, likes=None):
    """템플릿 단위 맞추기의 한 레벨(§8-2 「템플릿 맞추기」 · §8-4 정리 에이전트) — 대표를 rep(없으면 슬롯의 지금 대표)로 **삼았을 때** 그 모양으로 바꿀 줄(문서 순).
    likes(그 레벨 줄 id 들)를 주면 그 줄들과 비교 값이 같은 갈래만, None 이면 대표와 다른 줄 모두, 빈 목록이면 없음. 오버레이·문서를 안 바꾼다(대표 바꿈은 부른 쪽이
    트랜잭션 안에서 `set_rep`). -> (대표 문단 id, [바꿀 줄 id]). 대표·likes 문제는 ValueError · 없는 레벨은 KeyError."""
    sl = OE._slot(ov, tid, level)
    if sl is None:
        raise KeyError("그런 템플릿 레벨이 없습니다")
    rep = rep or sl.get("rep")
    if not rep or not _alive(doc, rep) or rep not in ov["lines"]:
        raise ValueError(f"L{level} 의 대표 문단이 문서에 없습니다 — 줄 하나를 대표로 정한 뒤 맞추세요")
    _check_member(ov, tid, level, rep)
    base = look(doc, ov, rep)
    kinds = None
    if likes is not None:
        kinds = []
        for q in likes:
            if not _alive(doc, q):
                raise ValueError("그 갈래의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
            _check_member(ov, tid, level, q)
            kinds.append(look(doc, ov, q))
    order = _order(doc)
    out = []
    for pid in sorted(slot_ids(ov, tid, level), key=lambda p: order.get(p, 1 << 30)):
        if pid == rep or not _alive(doc, pid):
            continue
        try:
            lk = look(doc, ov, pid)
        except (KeyError, ValueError):
            continue
        if lk != base and (kinds is None or any(lk == k for k in kinds)):
            out.append(pid)
    return rep, out


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
    if B.get("variant"):  # 서식 종속 템플릿(② §8-5)은 이미 제 템플릿의 레벨 아래에 있다
        raise ValueError(f"T{B['no']} 는 서식 종속 템플릿이라 다른 템플릿 아래로 넣을 수 없습니다 — 합친 뒤 원래 템플릿을 넣으세요")
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
    rec = {"child": B.get("anchor"), "parent": A.get("anchor"), "childId": child, "parentId": parent, "at": at, "id": cid, "moved": moved, "adopt": adopt,
           "n": _seq(ov)}  # n = 종속·떼기(② §8-5)를 넣은 차례 — carry 가 그 차례대로 다시 건다
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
    _no_variants(ov, cid, C.get("no", cid))
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
    ops = [("merge", m) for m in old.get("merges") or []] + [("split", m) for m in old.get("splits") or []]
    ops.sort(key=lambda o: o[1].get("n") or 0)  # 넣은 차례대로(차례 번호가 없는 옛 종속 기록이 먼저 — 안정 정렬이라 그 안의 차례는 그대로)
    for kind, m in ops:
        by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}  # 앞의 종속·떼기가 만든 템플릿도 앵커로 찾게 매번
        if kind == "split":  # 서식 종속 템플릿(② §8-5) — 기록의 줄 가운데 지금도 (A, Lk) 줄인 것만, 슬롯은 옛 것
            why = _carry_split(old, new, m, by_anchor.get(m.get("of")))
            if why:
                fails.append((m, why))
            continue
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
    made(이 템플릿을 넣어 만든 종속 템플릿들) · all(줄을 다 넣음) · vari(서식 종속 템플릿이면 {of, ofNo, level, sfx} — ② §8-5) ·
    splits(이 템플릿에서 뗀 서식 종속 템플릿들 [{id, no, level, sfx, lines}]), 레벨마다 rep(ctx = context — 칸 안 매달림)."""
    out = {}
    recs = ov.get("merges") or []
    tp = ov["templates"]
    count = {}
    for x in ov["lines"].values():
        count[x["tpl"]] = count.get(x["tpl"], 0) + 1
    for tid, t in tp.items():
        left = count.get(tid, 0)
        comp = t.get("composite")
        var = t.get("variant")
        made = [{"id": m.get("id"), "no": tp.get(m.get("id"), {}).get("no"), "parent": m["parentId"], "parentNo": tp.get(m["parentId"], {}).get("no"), "at": m["at"],
                 "moved": len(m.get("moved") or [])} for m in recs if m.get("childId") == tid]
        out[tid] = {"hang": hang(ov, tid, ctx), "lines": left, "base": _base(t), "made": made, "all": bool(made) and not left,
                    "comp": {**comp, "parentNo": tp.get(comp["parent"], {}).get("no"), "childNo": tp.get(comp["child"], {}).get("no")} if comp else None,
                    "vari": {**var, "ofNo": tp.get(var["of"], {}).get("no")} if var else None,
                    "splits": sorted(({"id": oid, "no": o["no"], "level": int(o["variant"]["level"]), "sfx": o["variant"]["sfx"], "lines": count.get(oid, 0)}
                                      for oid, o in tp.items() if (o.get("variant") or {}).get("of") == tid), key=lambda v: (v["level"], v["sfx"])),
                    "slots": {lv: {"rep": sl.get("rep")} for lv, sl in t.get("slots", {}).items()}}
    return out


# ---------------------------------------------------------------- 서식 종속 템플릿 — 서식 갈래를 다른 템플릿으로(spec_hwpx_웹편집 ② §8-5)
SFX = "abcdefghijklmnopqrstuvwxyz"  # 같은 (A, Lk) 에서 뗀 차례 — 「T1L3a」·「T1L3b」…


def var_id(tid, level, sfx):
    """서식 종속 템플릿의 id — 「A~k글자」(그래프 템플릿 id 는 정수 글 · 종속 템플릿은 「A+B」 라 겹치지 않는다)."""
    return f"{tid}~{int(level)}{sfx}"


def _seq(ov):
    """종속·떼기 기록의 차례 번호 — 2단계를 다시 돌린 뒤 carry 가 넣은 차례대로 다시 건다."""
    ov["seq"] = int(ov.get("seq") or 0) + 1
    return ov["seq"]


def _no_variants(ov, tid, no):
    """템플릿 tid 에서 뗀 서식 종속 템플릿이 있으면 ValueError — tid 를 지우기 전에(떼기·합치기)."""
    for t in ov["templates"].values():
        if (t.get("variant") or {}).get("of") == str(tid):
            raise ValueError(f"T{no} 에서 뗀 서식 종속 템플릿 T{t['no']} 가 있습니다 — 그것부터 합치세요")


def split_targets(doc, ov, tid, level, likes):
    """likes(그 레벨 줄 id 들)와 비교 값이 같은 (tid, level) 줄 모두(문서 순) — 갈래를 줄 하나로 가리킨다(화면이 가진 갈래의 줄 목록은 30줄까지).
    likes 문제는 ValueError · 없는 레벨은 KeyError."""
    if OE._slot(ov, tid, level) is None:
        raise KeyError("그런 템플릿 레벨이 없습니다")
    if not likes:
        raise ValueError("뗄 갈래의 줄(likes)이 필요합니다")
    kinds = []
    for q in likes:
        if not _alive(doc, q):
            raise ValueError("그 갈래의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
        _check_member(ov, tid, level, q)
        kinds.append(look(doc, ov, q))
    order = _order(doc)
    out = []
    for pid in sorted(slot_ids(ov, tid, level), key=lambda p: order.get(p, 1 << 30)):
        if not _alive(doc, pid):
            continue
        try:
            lk = look(doc, ov, pid)
        except (KeyError, ValueError):
            continue
        if any(lk == k for k in kinds):
            out.append(pid)
    return out


def split_block(ov, tid, level, paras, rep=None):
    """(tid, level) 줄 paras 를 서식 종속 템플릿으로 못 떼는 까닭 | None — 종속 템플릿의 부모 레벨 · 대표 갈래 · 번호형 레벨에서 같은 부모 아래 형제의 일부
    (번호 다시 매김이 (부모, 템플릿, 레벨) 묶음마다라 「1. 3.」 이 된다). rep = 그 레벨의 대표로 볼 줄(같은 트랜잭션에서 대표를 바꾼 뒤 뗄 때 — 없으면 슬롯의 지금 대표)."""
    tid = str(tid)
    t = ov["templates"].get(tid)
    sl = OE._slot(ov, tid, level)
    if t is None or sl is None:
        return "그런 템플릿 레벨이 없습니다"
    if int(level) <= _base(t):
        return f"L{level} 은 T{t['no']} 의 레벨이 아닙니다 — 이 템플릿의 줄은 L{_base(t) + 1} 부터입니다"
    want = set(paras)
    if not want:
        return "뗄 줄이 없습니다"
    if (rep or sl.get("rep")) in want:
        return f"T{t['no']} L{level} 의 대표 갈래는 뗄 수 없습니다 — 다른 줄을 대표로 정한 뒤 떼세요"
    if OE.is_numbered(sl.get("key") or ""):
        by_parent = {}
        for pid in slot_ids(ov, tid, level):
            by_parent.setdefault(ov["lines"][pid].get("parent"), []).append(pid)
        for sibs in by_parent.values():
            k = sum(1 for p in sibs if p in want)
            if 0 < k < len(sibs):
                return (f"번호형 레벨(「{sl.get('letter') or sl.get('key')}」)은 같은 부모 아래 형제 줄의 일부만 뗄 수 없습니다 — 번호가 템플릿마다 따로 매겨집니다"
                        f"(그 부모 아래 형제 {len(sibs)}줄 가운데 {k}줄)")
    return None


def used_sfx(ov, tid, level):
    """(tid, level) 에서 뗀 서식 종속 템플릿들이 쓴 글자."""
    return {t["variant"]["sfx"] for t in ov["templates"].values() if (t.get("variant") or {}).get("of") == str(tid) and int(t["variant"]["level"]) == int(level)}


def _free_sfx(ov, tid, level):
    used = used_sfx(ov, tid, level)
    return next((ch for ch in SFX if ch not in used), None)


def split(ov, tid, level, paras, rep=None, shape=None, into=None, sfx=None, slots=None):
    """템플릿 tid(A) 의 L level 줄 paras(일부러 다르게 준 서식의 갈래)를 **서식 종속 템플릿**(표기 「T{A}L{k}{a…}」 · id 「A~k글자」)으로 뗀다
    (2026-11-15 사용자 "서식이 다르면 템플릿도 다른거잖아 … T1L3 로 하고 a,b,c 를 붙이자 … 종속템플릿이기 때문에 이 템플릿의 시작은 L3 부터").
    새 템플릿 = A 의 사슬 그대로 · base = level − 1(L1~L level−1 은 A 의 레벨 — 그 줄은 A 것) · L level 슬롯 = rep 줄의 모양(shape = rep_shape — 대표·동결 접두·모양,
    A 의 자리 규칙·repSet 은 안 옮김) · 더 깊은 레벨 = A 의 슬롯 그대로. 옮기는 줄 = paras + 그 아래 A 줄(자손 — 레벨은 그대로). A 는 안 바뀐다.
    into(이미 있는 서식 종속 템플릿 id)를 주면 새로 만들지 않고 거기에 더 넣는다. slots(옛 템플릿의 슬롯 — carry)을 주면 그 슬롯으로.
    오버레이만 바꾼다 — 검사는 바꾸기 전에 다 한다(ValueError·KeyError). -> {"id", "no", "moved"[자손 포함], "paras", "new"}."""
    tid, level = str(tid), int(level)
    A = _tpl(ov, tid)
    paras = list(dict.fromkeys(paras or []))
    for pid in paras:
        _check_member(ov, tid, level, pid)
    why = split_block(ov, tid, level, paras)
    if why:
        raise ValueError(why)
    rep = rep or paras[0]
    if rep not in paras:
        raise ValueError("대표로 삼을 줄은 떼는 갈래의 줄이어야 합니다")
    recs = ov.setdefault("splits", [])
    if into is not None:
        cid = str(into)
        C = ov["templates"].get(cid)
        v = (C or {}).get("variant") or {}
        if C is None or v.get("of") != tid or int(v.get("level") or 0) != level:
            raise ValueError(f"그 템플릿은 T{A['no']} L{level} 에서 뗀 서식 종속 템플릿이 아닙니다")
        new = False
    else:
        sfx = sfx or _free_sfx(ov, tid, level)
        if not sfx:
            raise ValueError(f"T{A['no']} L{level} 에서 뗄 수 있는 템플릿 수({len(SFX)}개)를 다 썼습니다 — 안 쓰는 것을 합친 뒤 떼세요")
        if not (isinstance(sfx, str) and len(sfx) == 1 and sfx in SFX):
            raise ValueError("글자(sfx)는 a~z 한 글자")
        cid = var_id(tid, level, sfx)
        if cid in ov["templates"]:
            raise ValueError(f"T{A['no']}L{level}{sfx} 는 이미 있습니다")
        chain = list(A.get("chain") or [])
        amax = max([int(k) for k in A["slots"]] + [len(chain), level])
        made = {}
        for k in range(level, amax + 1):
            src = (slots or {}).get(str(k)) or A["slots"].get(str(k))
            key = chain[k - 1] if k - 1 < len(chain) else (src or {}).get("key", "")
            sl = copy.deepcopy(src) if src else {"letter": key, "key": key, "rep": None, "count": 0, "prefix": None, "attrs": None, "spacer": None}
            if not (slots or {}).get(str(k)):  # A 의 슬롯에서 — 사람이 A 에 정한 대표 표지는 안 옮기고, 떼는 레벨은 자리 규칙도(일부러 다른 서식)
                sl.pop("repSet", None)
                sl["rep"] = None
                if k == level:
                    sl.pop("pos", None)
            made[str(k)] = sl
        C = {"no": f"{A['no']}L{level}{sfx}", "kind": A.get("kind"), "anchor": f"{A.get('anchor')}~L{level}{sfx}", "chain": chain, "slots": made, "max": amax,
             "base": level - 1, "variant": {"of": tid, "level": level, "sfx": sfx}}
        new = True
    # ---- 여기부터 오버레이를 바꾼다
    moved = sorted(_members(ov, tid, paras))
    gone = set(moved)
    by_level = {}
    for pid in moved:
        by_level.setdefault(int(ov["lines"][pid]["level"]), []).append(pid)
    if new:
        ov["templates"][cid] = C
        top = C["slots"][str(level)]
        if shape:
            top.update(rep=rep, prefix=shape["prefix"], letter=shape["tok"], attrs=shape["attrs"], bodyChar=shape["body"])
        elif top.get("rep") not in paras:
            top["rep"] = rep
    for k, ids in by_level.items():  # 대표가 비었거나 이 템플릿 밖이면 옮긴 줄의 첫 것(동결 모양은 그대로)
        sl = C["slots"].get(str(k))
        if sl is not None and (not sl.get("rep") or (sl["rep"] not in gone and ov["lines"].get(sl["rep"], {}).get("tpl") != cid)):
            sl["rep"] = ids[0]
            sl.pop("repSet", None)
    for k, sl in C["slots"].items():  # carry — 옛 슬롯의 대표가 이제 이 템플릿 줄이 아니면 비운다
        if sl.get("rep") and sl["rep"] not in gone and ov["lines"].get(sl["rep"], {}).get("tpl") != cid:
            sl["rep"] = None
            sl.pop("repSet", None)
    for k, sl in A["slots"].items():  # A 의 더 깊은 레벨 대표가 옮긴 줄이면 남은 줄의 첫 것으로(동결 모양은 그대로)
        if sl.get("rep") in gone:
            rest = [pid for pid, x in ov["lines"].items() if x["tpl"] == tid and str(x["level"]) == k and pid not in gone]
            if rest:
                sl["rep"] = rest[0]
                sl.pop("repSet", None)
    for pid in moved:
        ov["lines"][pid].update(tpl=cid, no=C["no"])
    if new:
        br = ov.setdefault("branches", {})
        for k in range(level, int(C["max"]) + 1):  # A 의 그 레벨들에 매달리던 가지 → 새 템플릿의 그 레벨에도
            for c in list(br.get(f"{tid}|{k}") or []):
                lst = br.setdefault(f"{cid}|{k}", [])
                if c not in lst:
                    lst.append(c)
        if level - 1 > _base(A):  # 새 템플릿은 (A, level − 1) 에 매달린다(첫 레벨의 Alt+↑ · 부모 찾기)
            lst = br.setdefault(f"{tid}|{level - 1}", [])
            if cid not in lst:
                lst.append(cid)
        else:  # level 이 A 의 첫 레벨 — A 가 매달린 자리마다
            for key, lst in list(br.items()):
                if tid in lst and cid not in lst and key.split("|")[0] != cid:
                    lst.append(cid)
    rec = next((r for r in recs if r.get("id") == cid), None)
    if rec is None:
        rec = {"of": A.get("anchor"), "ofId": tid, "level": level, "sfx": C["variant"]["sfx"], "id": cid, "lines": [], "n": _seq(ov)}
        recs.append(rec)
    rec["lines"] = sorted(set(rec["lines"]) | set(paras))
    return {"id": cid, "no": C["no"], "moved": moved, "paras": paras, "new": new}


def unsplit(ov, cid):
    """split 을 거꾸로 — 서식 종속 템플릿 cid 의 줄 모두(뗀 뒤 Enter 로 만든 줄 포함)를 원래 템플릿의 같은 레벨로 되돌리고 그 템플릿을 지운다. -> 되돌린 줄 수.
    그 템플릿으로 만든 종속 템플릿·서식 종속 템플릿이 있으면 그것부터(ValueError)."""
    cid = str(cid)
    C = ov["templates"].get(cid)
    v = (C or {}).get("variant")
    if not v:
        raise ValueError("서식 종속 템플릿이 아닙니다")
    tid = str(v["of"])
    A = ov["templates"].get(tid)
    if A is None:
        raise ValueError(f"T{C['no']} 의 원래 템플릿이 없습니다")
    for m in ov.get("merges") or []:
        if cid in (m.get("childId"), m.get("parentId")):
            other = ov["templates"].get(m.get("id"), {}).get("no", m.get("id"))
            raise ValueError(f"T{C['no']} 로 만든 종속 템플릿 T{other} 가 있습니다 — 그것부터 떼세요")
    _no_variants(ov, cid, C["no"])
    back = 0
    for x in ov["lines"].values():
        if x["tpl"] == cid:
            x.update(tpl=tid, no=A["no"])
            back += 1
    ov["templates"].pop(cid, None)
    br = ov.get("branches") or {}
    for key in [k for k in br if k.split("|")[0] == cid]:
        br.pop(key, None)
    for lst in br.values():
        if cid in lst:
            lst.remove(cid)
    ov["splits"] = [r for r in ov.get("splits") or [] if r.get("id") != cid]
    return back


def _carry_split(old, new, m, tid):
    """carry 의 떼기 한 건 — 새 오버레이의 템플릿 tid(같은 앵커)에서 기록 m 의 줄 가운데 지금도 (tid, level) 줄인 것을 다시 뗀다. -> 못 건 까닭 | None."""
    if tid is None:
        return "템플릿이 없음"
    level = int(m["level"])
    lines = [p for p in m.get("lines") or [] if p in new["lines"] and new["lines"][p]["tpl"] == tid and int(new["lines"][p]["level"]) == level]
    if not lines:
        return "뗀 줄이 없음"
    oc = (old.get("templates") or {}).get(m.get("id")) or {}
    oa = (old.get("templates") or {}).get(m.get("ofId")) or {}
    nsl, osl = OE._slot(new, tid, level), (oa.get("slots") or {}).get(str(level)) or {}
    if nsl is not None and nsl.get("rep") in lines:  # 새 그래프의 대표가 뗄 줄 — 옛 오버레이에서 A 의 대표였던 줄이 지금도 그 레벨 줄이면 그것으로
        x = new["lines"].get(osl.get("rep"))
        if x is not None and x["tpl"] == tid and int(x["level"]) == level and osl["rep"] not in lines:
            nsl.update({k: osl.get(k) for k in ("rep", "prefix", "letter", "attrs", "bodyChar")})
    rep = ((oc.get("slots") or {}).get(str(level)) or {}).get("rep")
    try:
        split(new, tid, level, lines, rep=rep if rep in lines else lines[0], sfx=m.get("sfx"), slots=oc.get("slots") or None)
    except (KeyError, ValueError) as e:
        return str(e)
    return None


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

