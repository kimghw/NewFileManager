"""캡션 템플릿 「CN」(spec_hwpx_웹편집 ② §8-10) — 그림 아래 · 표 위의 캡션을 꼴이 같은 것끼리 묶어 템플릿 C1 · C2 … 로 관리한다(개요 템플릿 「TN」 의 캡션 짝).

- **캡션 줄**(`scan`) = ⓐ 개체 캡션: 표·그림에 붙은 hp:caption 안의 글 문단 · ⓑ 글 캡션: 본문에 문단으로 친 캡션 — 「표 N」·「그림 N」 꼴(이웃 문단이 표·그림) 또는 줄 전체가
  홑화살괄호 「< 제목 >」 인 줄(바로 아래가 표 · 바로 위가 그림). 개요 줄(개요 오버레이의 줄)은 캡션 줄이 아니다(`skip`).
- **캡션의 꼴**(`parse`): label 「<표 1> 제목」·「표 1-1 제목」·「[그림 2] 제목」(번호 붙은 머리) · wrap 「< 제목 >」(줄 전체를 괄호로) · note 「*. 출처 …」·「※ …」(개체 캡션의 출처·주 줄) ·
  plain(레터 없는 글 — 개체 캡션만: 첫 줄 = 제목, 뒤 줄 = 이어지는 줄).
- **캡션 템플릿**(`model`) = (대상 표|그림, 레터 꼴)이 같은 캡션 줄의 묶음 — 레터가 다르면 다른 템플릿, 레터가 같으면 서식이 달라도 같은 템플릿의 「다른 서식」(개요 템플릿과 같은 기준).
  번호는 문서에 먼저 나온 차례로 C1 … 을 매기고 한 번 매긴 번호는 지킨다(`state["ids"]` — 개요 오버레이 `ov["caps"]` 에 든다: 실행 취소 · 작업 저장과 함께).
- **서식 갈래**: 비교 값(`look` — 앞 빈칸 · 레터 · 레터 뒤 빈칸 · 닫는 괄호 · 문단 모양 · 레터 글자 · 본문 바탕 글자)이 같은 줄끼리. 대표 = 사람이 정한 줄(`state["reps"]`), 없으면 줄이 가장 많은 갈래의 첫 줄.
- **역변환 스크립트**(`conform` — spec ② §8-8 의 원칙: 추출에는 짝이 되는 스크립트가 있다): 캡션 줄 하나를 대표의 모양(`shape`)으로 — 문단 모양·스타일 · 레터/바탕 글자 모양 · 앞 빈칸·레터·레터 뒤 빈칸 · 닫는 괄호.
  자동 번호(hp:autoNum)·표지가 든 머리는 글을 안 바꾸고 모양만 바꾼다. 번호는 제 번호 · 따로 모양을 준 런(강조)과 줄 맞춤 값(장평·자간)은 그대로(`outline_match.keep_fit`).

값 읽기·견주기의 낱 함수는 `app/outline_match.py` 것을 쓴다(같은 단위 · 같은 화면 글). 이 모듈은 문서를 `conform` 에서만 바꾼다(부르는 쪽이 트랜잭션 안에서).
"""
import hashlib
import json
import re

from app import outline_match as OM
from app.hwpx_doc import CAPTION
from app.hwpx_struct import AUTONUM_EL, AUTONUM_TYPES, CTRL, MARKERS, OBJECTS, RUN, SUBLIST, TBL, P, _split_t

KEYS = ("lead", "letter", "gap", "close") + OM.PARA_KEYS + tuple("L." + k for k in OM.CMP_CHAR) + OM.CMP_CHAR  # 비교 값의 차례(화면의 「대표와 다른 값」 차례)
LABELS = {**OM.LABELS, "lead": "앞 빈칸", "close": "닫는 괄호"}  # 캡션에는 레터가 없는 줄도 있어 「레터 앞 빈칸」 이 아니라 「앞 빈칸」(줄 앞 빈칸 — spec_헤딩_추출 ② §0 「줄 첫머리의 말」)
LIST_MAX = 30  # 갈래마다 보내는 줄 id 수(outline_match._LIST_MAX 와 같은 값)
NEAR_MAX = 2   # 글 캡션과 표·그림 사이에 낄 수 있는 순수 간격 문단 수
KINDS = {"table": "표", "figure": "그림"}
SIDES = {"TOP": "top", "BOTTOM": "bottom", "LEFT": "left", "RIGHT": "right"}
SIDE_NAMES = {"top": "위", "bottom": "아래", "left": "왼쪽", "right": "오른쪽", "own": "같은 문단"}

# 괄호의 갈래 — a = 화살괄호(< 〈 《) · s = 대괄호([ 【) · r = 소괄호
_OPEN = {"<": "a", "＜": "a", "〈": "a", "《": "a", "[": "s", "［": "s", "【": "s", "(": "r", "（": "r"}
_CLOSE = {">": "a", "＞": "a", "〉": "a", "》": "a", "]": "s", "］": "s", "】": "s", ")": "r", "）": "r"}
_WRAP_KEY = {"<": "<…>", "＜": "<…>", "〈": "〈…〉", "《": "《…》", "[": "[…]", "［": "[…]", "【": "【…】"}
_FOLD = str.maketrans({"＜": "<", "＞": ">", "［": "[", "］": "]", "（": "(", "）": ")", "：": ":", "–": "-"})
_WORDS = {"표": "table", "table": "table"}  # 그 밖의 낱말(그림 · 사진 · Figure · Fig.)은 그림
# 번호 붙은 머리 — [여는 괄호] 낱말 번호 [닫는 괄호] [. :] (「<표 1>」 · 「표 1-1」 · 「[그림 2]」 · 「그림 3.」 · 「Table 2:」). 번호 사이 구분자 뒤에는 빈칸을 두지 않는다(「표 1. 2024년 …」 의 「1」)
_LABEL = re.compile(r"(?P<open>[<\[(〈《【＜［（]?)[ 　]*(?P<word>그림|표|사진|Figure|Fig\.?|Table)[ 　]*\d+(?:[-.–]\d+)*(?:[ 　]*(?P<close>[>\])〉》】＞］）]))?(?P<punct>[.:：]?)", re.I)
_NOTE = re.compile(r"\*{1,3}\.?|※|주\s*\)|\(\s*주\s*\)|(?:출처|자료)\s*[:：]?")  # 개체 캡션의 출처·주 줄 머리
_FIRST = re.compile(r"[<〈《＜\[(【［（]|그림|표|사진|fig|table", re.I)  # 글 캡션 후보를 싸게 거른다(글 첫머리)


def _lead(text):
    return text[:len(text) - len(text.lstrip())]


def _ws_split(s):
    """글 s 를 (앞 빈칸, 몸, 뒤 빈칸)으로."""
    a = _lead(s)
    body = s[len(a):].rstrip()
    return a, body, s[len(a) + len(body):]


def parse(text, struct=True, first=True):
    """캡션 글의 꼴 → {shape(label|wrap|note|plain), lead, tok(레터), gap(레터 뒤 빈칸), plen(머리 길이 = 앞 빈칸 + 레터 + 레터 뒤 빈칸), close(닫는 쪽 — wrap 만: 닫는 괄호 앞 빈칸 + 괄호 + 뒤 빈칸),
    key(레터 꼴의 정규 키), word(table|figure|None — label 의 낱말이 가리키는 대상)} | None(글 캡션인데 캡션 꼴이 아님 · 빈 글).
    struct = 개체 캡션(hp:caption 안)인가 — 그때만 note·plain 을 낸다. first = 그 캡션의 첫 글 문단인가(plain 의 키: 제목 「글」 · 이어지는 줄 「글+」)."""
    text = text or ""
    if not text.strip():
        return None
    lead = _lead(text)
    rest = text[len(lead):]
    base = {"lead": lead, "close": "", "word": None}
    m = _LABEL.match(rest)
    if m and (_OPEN.get(m["open"]) == _CLOSE.get(m["close"])):  # 괄호는 짝으로(둘 다 없거나 같은 갈래) — 「<표 1. 제목>」 은 머리가 아니라 줄 전체 괄호(wrap)
        tok = m.group(0)
        after = rest[len(tok):]
        if not after or after[0].isspace() or m["punct"] or m["close"]:  # 「Table 2에 따른 …」 처럼 글자가 바로 붙으면 머리가 아니다
            gap = _lead(after)
            return {**base, "shape": "label", "tok": tok, "gap": gap, "plen": len(lead) + len(tok) + len(gap),
                    "key": re.sub(r"\d+", "N", re.sub(r"\s+", "", tok)).translate(_FOLD).casefold(), "word": _WORDS.get(m["word"].casefold(), "figure")}
    cls = _OPEN.get(rest[0])
    if cls in ("a", "s") and (struct or cls == "a"):  # 줄 전체 괄호 — 글 캡션은 화살괄호만(대괄호 줄은 구분 라벨·괄호 소제목: 헤딩 그래프의 것)
        _, body, tail = _ws_split(rest)
        inner = body[1:-1]
        if len(body) >= 3 and _CLOSE.get(body[-1]) == cls and inner.strip() and not any(_OPEN.get(c) == cls or _CLOSE.get(c) == cls for c in inner):
            gap, _, in2 = _ws_split(inner)
            return {**base, "shape": "wrap", "tok": rest[0], "gap": gap, "plen": len(lead) + 1 + len(gap), "close": in2 + body[-1] + tail, "key": _WRAP_KEY[rest[0]]}
    if not struct:
        return None
    m = _NOTE.match(rest)
    if m:
        tok = m.group(0)
        gap = _lead(rest[len(tok):])
        return {**base, "shape": "note", "tok": tok, "gap": gap, "plen": len(lead) + len(tok) + len(gap), "key": re.sub(r"\s+", "", tok).translate(_FOLD)}
    return {**base, "shape": "plain", "tok": "", "gap": "", "plen": len(lead), "key": "글" if first else "글+"}


def _name(shape, key, tok):
    """템플릿의 화면 이름(레터 꼴) — 「<표 N>」 · 「< … >」 · 「*.」 · 「글만」 · 「이어지는 줄」."""
    if shape == "label":
        return re.sub(r"\d+", "N", tok)
    if shape == "wrap":
        return f"{key[0]} … {key[-1]}"
    if shape == "note":
        return tok
    return "글만" if key == "글" else "이어지는 줄"


def _objects(q):
    """문단 q 가 품은 개체의 태그들."""
    return [o.tag for r in q.iterchildren(RUN) for o in r if o.tag in OBJECTS] if q is not None and q.tag == P else []


def _near(doc, p, step):
    """p 의 앞(step −1)·뒤(+1) 이웃 문단 — 순수 간격 문단은 NEAR_MAX 개까지 건너뛴다. 없으면 None."""
    q, n = p, 0
    while True:
        q = q.getnext() if step > 0 else q.getprevious()
        if q is None or q.tag != P:
            return None
        if n < NEAR_MAX and doc.is_spacer(q):
            n += 1
            continue
        return q


def _text_caption(doc, p, text):
    """본문에 문단으로 친 캡션인가 → (꼴, 대상 kind, 자리 side) | None. 이웃이 표·그림이어야 한다(「Table 2에 따른 시험 수행」 같은 문장은 아님)."""
    if not _FIRST.match(text.lstrip()[:8]):
        return None
    f = parse(text, struct=False)
    if f is None:
        return None
    prev, nxt, own = _objects(_near(doc, p, -1)), _objects(_near(doc, p, +1)), _objects(p)
    if f["shape"] == "label":
        if f["word"] == "table":  # 「표 N」 — 표가 아래(캡션이 위)인 것이 먼저
            side = "top" if TBL in nxt else "bottom" if TBL in prev else "own" if TBL in own else None
        else:                     # 「그림 N」 — 개체가 위(캡션이 아래)인 것이 먼저. 그림을 표 틀에 넣은 문서도 있어 표도 받는다
            side = "bottom" if prev else "top" if nxt else "own" if own else None
        return (f, f["word"], side) if side else None
    if TBL in nxt:  # 줄 전체 괄호 — 표 위 · 그림 아래만
        return f, "table", "top"
    if any(t != TBL for t in prev):
        return f, "figure", "bottom"
    return None


def scan(doc, skip=()):
    """문서의 캡션 줄(문서 순) → ([{id, kind(table|figure), side(top|bottom|left|right|own), struct(개체 캡션인가), text, …parse 의 값}], missed).
    missed = 블록 id 가 없어 다루지 못한 개체 캡션 줄 수(묶음 개체 hp:container 의 캡션 — 화면에 블록으로 안 나온다). skip = 캡션으로 보지 않을 문단 id(개요 줄)."""
    out, missed, firsts = [], 0, {}
    for sec in doc._sections:
        for p in sec.iter(P):
            par = p.getparent()
            cap = par.getparent() if par is not None and par.tag == SUBLIST else None
            if cap is not None and cap.tag == CAPTION:
                text = doc._text(p)
                if not text.strip():
                    continue
                pid = doc._rev.get(p)
                first = firsts.setdefault(par, p) is p  # 그 캡션의 첫 글 문단(문서 순으로 처음 본 것)
                if pid is None:
                    missed += 1
                    continue
                f = parse(text, struct=True, first=first)
                out.append({**f, "id": pid, "kind": "table" if cap.getparent().tag == TBL else "figure", "side": SIDES.get(cap.get("side"), "bottom"), "struct": True, "text": text})
                continue
            pid = doc._rev.get(p)
            if pid is None or pid in skip:
                continue
            text = doc._text(p)
            hit = _text_caption(doc, p, text) if text else None
            if hit:
                f, kind, side = hit
                out.append({**f, "id": pid, "kind": kind, "side": side, "struct": False, "text": text})
    return out, missed


# ---------------------------------------------------------------- 비교 값 · 갈래
def _cids(doc, p, ln, text):
    """(레터 글자 모양 id, 본문 바탕 글자 모양 id) — 레터 = 앞 빈칸 뒤 첫 글자의 런, 바탕 = 머리 뒤 첫 글자의 런(글이 머리뿐이면 레터 것)."""
    lc = OM._cid_at(doc, p, len(ln["lead"])) or doc._char_id(p)
    bc = OM._cid_at(doc, p, ln["plen"]) if ln["plen"] < len(text) else lc
    return lc, bc or lc


def look(doc, ln):
    """캡션 줄의 비교 값(KEYS — 줄 맞춤 값 장평·자간도 함께 실린다: 견주지는 않는다)."""
    p = doc._ids[ln["id"]]
    text = doc._text(p)
    lc, bc = _cids(doc, p, ln, text)
    pp = p.get("paraPrIDRef")
    para, lch, bch = doc._summary(pp, lc), doc._summary(pp, lc), doc._summary(pp, bc)
    left, first = para.get("indentLeftMm"), para.get("firstLineMm")
    # 닫는 괄호 뒤 빈칸은 견주지 않는다(보이지 않는 글 — 맞출 때는 지운다)
    out = {"lead": ln["lead"], "letter": re.sub(r"\d+", "#", ln["tok"]) if ln["shape"] == "label" else ln["tok"], "gap": ln["gap"], "close": ln["close"].rstrip()}
    if left is None or first is None:
        out["line1Mm"] = out["line2Mm"] = None
    else:
        out["line1Mm"], out["line2Mm"] = OM._r(left + max(first, 0.0)), OM._r(left + max(-first, 0.0))
    for k in ("align", "indentRightMm", "spaceBeforePt", "spaceAfterPt"):
        out[k] = OM._r(para.get(k))
    out["lineSpacingPct"] = OM._r(para.get("lineSpacingPct"), 0)
    for k in OM.CHAR_KEYS:
        out["L." + k] = OM._r(lch.get(k))
        out[k] = OM._r(bch.get(k))
    return out


def shown(key, v):
    """화면용 값 글 — 닫는 괄호는 「1칸 + 「>」」, 그 밖은 개요 템플릿과 같은 글(outline_match.shown)."""
    if key == "close":
        if not v:
            return "—"
        a, body, b = _ws_split(v)
        return " + ".join(x for x in (OM.ws(a) if a else "", f"「{body}」", OM.ws(b) if b else "") if x)
    if key == "letter":
        return v if v else "없음"
    return OM.shown(key, v)


def _sig(lk):
    return repr([lk.get(k) for k in KEYS])


def diff(a, b):
    """비교 값 a(대표)와 b 의 다른 키 → [[키, 이름, 대표 글, b 글]…](KEYS 차례 — outline_match.diff 와 같은 꼴: 화면이 「이름: 지금 b → 대표 a」 로 적는다)."""
    return [[k, LABELS.get(k, k), shown(k, a.get(k)), shown(k, b.get(k))] for k in KEYS if a.get(k) != b.get(k)]


def _auto_in_head(doc, p, plen):
    """머리(첫 plen 글자) 안에 자동 번호(hp:autoNum — 「표 」 뒤의 번호)가 들었나 — 그런 머리는 글을 다시 쓰지 않는다(번호 컨트롤이 지워진다)."""
    pos = 0
    for r in p.iterchildren(RUN):
        for c in r:
            n = doc._clen(c)
            if c.tag == CTRL and n and pos < plen and any(a.get("numType") in AUTONUM_TYPES for a in c.iterchildren(AUTONUM_EL)):
                return True
            pos += n
    return False


def frozen(doc, ln):
    """글(앞 빈칸 · 레터 · 닫는 괄호)을 다시 쓸 수 없는 줄인가 — 머리에 자동 번호가 들었거나 문단에 짝 표지(형광펜 · 변경 추적 · 필드)가 있다. 그런 줄은 모양만 맞춘다."""
    p = doc._ids[ln["id"]]
    return next(p.iter(*MARKERS), None) is not None or _auto_in_head(doc, p, ln["plen"])


def model(doc, state=None, skip=(), full=False, only=None):
    """캡션 템플릿들 → {templates[{id 「C1」, no, key, kind, kindName, shape, name, total, sides{자리: 수}, struct(개체 캡션 수), text(글 캡션 수), frozen(글을 못 바꾸는 줄 수),
    rep, repSet(사람이 정한 대표인가), others(대표와 서식이 다른 줄 수), groups[{key(그 갈래의 열쇠 줄), count, paras(30줄까지 — full 이면 전부), more, rep, look(화면 글), raw(원값), diff}], sig}],
    lines{문단 id: {tpl, no, shape}}, missed, keys[[키, 이름]…]}. 대표 갈래 먼저, 그다음 줄 수 순.
    state = {"ids": {템플릿 키: 번호}, "reps": {템플릿 키: 대표 문단 id}}(없으면 번호를 문서 차례로만 매기고 남기지 않는다) — 새 템플릿의 번호는 여기에 적는다.
    only = 그 템플릿(「C1」)만 갈래를 셈한다(다른 템플릿은 줄 수까지)."""
    lines, missed = scan(doc, skip)
    ids = state.setdefault("ids", {}) if state is not None else {}
    reps = (state or {}).get("reps") or {}
    by = {}
    for ln in lines:
        by.setdefault(f"{ln['kind']}|{ln['shape']}|{ln['key']}", []).append(ln)
    nxt = max(ids.values(), default=0)
    for key in by:  # 문서에 먼저 나온 차례(by 는 넣은 차례)로 새 번호
        if key not in ids:
            nxt += 1
            ids[key] = nxt
    out, where = [], {}
    for key, mine in sorted(by.items(), key=lambda kv: ids[kv[0]]):
        cid = f"C{ids[key]}"
        for ln in mine:
            where[ln["id"]] = {"tpl": cid, "no": ids[key], "shape": ln["shape"]}
        sides = {}
        for ln in mine:
            sides[ln["side"]] = sides.get(ln["side"], 0) + 1
        t = {"id": cid, "no": ids[key], "key": key, "kind": mine[0]["kind"], "kindName": KINDS[mine[0]["kind"]], "shape": mine[0]["shape"], "total": len(mine), "sides": sides,
             "struct": sum(1 for ln in mine if ln["struct"]), "text": sum(1 for ln in mine if not ln["struct"])}
        if only is not None and cid != only:
            t.update(name=_name(mine[0]["shape"], mine[0]["key"], mine[0]["tok"]), rep=None, repSet=False, others=0, groups=[], frozen=0, sig="")
            out.append(t)
            continue
        looks = {ln["id"]: look(doc, ln) for ln in mine}
        groups = {}
        for ln in mine:
            groups.setdefault(_sig(looks[ln["id"]]), []).append(ln["id"])
        rep = reps.get(key) if reps.get(key) in looks else None
        rep_set = rep is not None
        if rep is None:  # 사람이 정한 대표가 없다 — 줄이 가장 많은 갈래의 첫 줄(같은 수면 문서에 먼저 나온 갈래)
            rep = max(groups.values(), key=len)[0]
        rep_sig, base = _sig(looks[rep]), looks[rep]
        gs = []
        for sg, paras in groups.items():
            is_rep = sg == rep_sig
            k = rep if is_rep else paras[0]
            gs.append({"key": k, "count": len(paras), "paras": paras if full else paras[:LIST_MAX], "more": 0 if full else max(0, len(paras) - LIST_MAX), "rep": is_rep,
                       "look": {x: shown(x, v) for x, v in looks[k].items()}, "raw": looks[k], "diff": [] if is_rep else diff(base, looks[k])})
        order = {ln["id"]: i for i, ln in enumerate(mine)}
        gs.sort(key=lambda g: (not g["rep"], -g["count"], order[g["paras"][0]]))
        rep_ln = next(ln for ln in mine if ln["id"] == rep)
        t.update(name=_name(rep_ln["shape"], rep_ln["key"], rep_ln["tok"]), rep=rep, repSet=rep_set, others=len(mine) - len(groups[rep_sig]), groups=gs,
                 frozen=sum(1 for ln in mine if frozen(doc, ln)),
                 sig=hashlib.sha1(json.dumps([[ln["id"], _sig(looks[ln["id"]])] for ln in mine], ensure_ascii=False).encode("utf-8")).hexdigest()[:16])
        out.append(t)
    return {"templates": out, "lines": where, "missed": missed, "keys": [[k, LABELS.get(k, k)] for k in KEYS]}


def lines_of(doc, key, skip=()):
    """템플릿 키 key 의 캡션 줄(문서 순)."""
    return [ln for ln in scan(doc, skip)[0] if f"{ln['kind']}|{ln['shape']}|{ln['key']}" == key]


def key_of(state, cid):
    """「C1」 → 템플릿 키 | None(그런 번호 없음)."""
    m = re.fullmatch(r"C(\d+)", str(cid or ""))
    no = int(m.group(1)) if m else None
    return next((k for k, n in ((state or {}).get("ids") or {}).items() if n == no), None)


def set_rep(doc, state, cid, pid, skip=()):
    """템플릿 cid 의 대표를 캡션 줄 pid 로(state["reps"]) — 문서는 안 바꾼다. -> 전의 대표(사람이 정한 것 | None). 그 템플릿의 줄이 아니면 ValueError · 없는 템플릿은 KeyError."""
    key = key_of(state, cid)
    if key is None:
        raise KeyError("그런 캡션 템플릿이 없습니다")
    if pid not in {ln["id"] for ln in lines_of(doc, key, skip)}:
        raise ValueError(f"그 문단은 {cid} 의 캡션 줄이 아닙니다")
    reps = state.setdefault("reps", {})
    was = reps.get(key)
    reps[key] = pid
    return was


def targets(doc, state, cid, paras=None, likes=None, skip=()):
    """맞출 줄 → (대표 줄, [대표와 비교 값이 다른 그 템플릿의 줄(문서 순)]). paras 를 주면 그 가운데서만 · likes(그 템플릿의 줄 id 들)를 주면 그 줄들과 비교 값이 같은 갈래만.
    없는 템플릿은 KeyError · likes 가 그 템플릿의 줄이 아니면 ValueError."""
    key = key_of(state, cid)
    mine = lines_of(doc, key, skip) if key else []
    if not mine:
        raise KeyError("그런 캡션 템플릿이 없습니다")
    looks = {ln["id"]: look(doc, ln) for ln in mine}
    rep = ((state or {}).get("reps") or {}).get(key)
    if rep not in looks:
        groups = {}
        for ln in mine:
            groups.setdefault(_sig(looks[ln["id"]]), []).append(ln["id"])
        rep = max(groups.values(), key=len)[0]
    kinds = None
    if likes is not None:
        if any(q not in looks for q in likes):
            raise ValueError("그 서식의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
        kinds = {_sig(looks[q]) for q in likes}
    want = set(paras) if paras else None
    base = _sig(looks[rep])
    hit = [ln for ln in mine if ln["id"] != rep and (want is None or ln["id"] in want) and _sig(looks[ln["id"]]) != base and (kinds is None or _sig(looks[ln["id"]]) in kinds)]
    return next(ln for ln in mine if ln["id"] == rep), hit


# ---------------------------------------------------------------- 역변환 — 캡션 줄을 대표의 모양으로
def shape(doc, ln):
    """대표 캡션 줄의 지금 모양 → {shape, lead, tok, gap, close, para{paraPrIDRef, styleIDRef}, letter(레터 글자 모양 id), body(본문 바탕 글자 모양 id)}."""
    p = doc._ids[ln["id"]]
    lc, bc = _cids(doc, p, ln, doc._text(p))
    return {"shape": ln["shape"], "lead": ln["lead"], "tok": ln["tok"], "gap": ln["gap"], "close": ln["close"].rstrip(),  # 닫는 괄호 뒤 빈칸은 옮기지 않는다(보이지 않는 글)
            "para": {"paraPrIDRef": p.get("paraPrIDRef", "0"), "styleIDRef": p.get("styleIDRef", "0")}, "letter": lc, "body": bc}


def _renumber(rep_tok, tok):
    """대표의 레터 꼴에 제 번호 — 「< 표 1 >」(대표) + 「<표12>」 → 「< 표 12 >」. 번호 자리 수가 다르면(「1-2」 와 「3」) 제 레터 그대로."""
    mine = re.findall(r"\d+", tok)
    if len(re.findall(r"\d+", rep_tok)) != len(mine):
        return tok
    it = iter(mine)
    return re.sub(r"\d+", lambda _m: next(it), rep_tok)


def _splice(doc, p, start, n, new, at):
    """문단 글의 [start, start + n) 을 new 로 — 새 글은 글자 자리 at 이 든 런에 넣는다(그 런의 글자 모양을 따른다). 자동 번호·표지가 없는 구간에만 쓴다."""
    host, base = None, 0
    for a, b, r in OM._runs_pos(doc, p):
        if a <= at < b:
            host, base = r, a
            break
    if n:
        doc._erase(p, start, n)
    if not new:
        return
    if host is None:
        host = doc._first_text_run(p)
        if host is None:
            raise ValueError("글을 넣을 런이 없습니다")
        base = start
    t = doc._put_text(host, new)  # 런 끝에 붙는다 → 아래에서 제자리로
    off, pos = max(start - base, 0), 0  # 그 런에서 새 글 앞에 남는 글자 수
    for c in list(host):
        if c is t:
            break
        k = doc._clen(c)
        if pos + k > off:  # 이 자식이 off 자리 글자를 품는다 — 그 앞(또는 그 글 조각을 갈라 사이)에
            if pos < off:
                _split_t(c, off - pos)
                c.addnext(t)
            else:
                c.addprevious(t)
            break
        pos += k


def conform(doc, ln, sh):
    """캡션 줄 ln 을 대표 모양 sh(`shape`)로 — **캡션 줄 하나를 대표 서식으로 바꾸는 단 하나의 길**. 부르는 쪽이 트랜잭션 안에서(문서를 바꾼다).
    ① 문단 모양·스타일 = 대표 것 ② 머리의 옛 레터 글자 모양 런 → 대표의 레터 글자 모양 · 본문의 옛 바탕 글자 모양 런 → 대표의 바탕 글자 모양(따로 모양을 준 런은 그대로 · 장평·자간은 제 것)
    ③ 글: 앞 빈칸 · 레터(번호형은 대표 꼴에 제 번호 · 괄호·기호는 대표 글자) · 레터 뒤 빈칸 · 닫는 괄호(wrap). 머리에 자동 번호·표지가 있으면 ③ 은 건너뛴다. -> {"id", "text": 글을 바꿨나, "frozen"}."""
    p = doc._ids[ln["id"]]
    text = doc._text(p)
    plen = ln["plen"]
    old_l, old_b = _cids(doc, p, ln, text)
    hold = frozen(doc, ln)
    for k, v in sh["para"].items():
        p.set(k, v)
    if 0 < plen < len(text):
        doc._boundary(p, plen)  # 머리와 본문이 한 런이면 갈라 둔다(대표의 레터·바탕 글자 모양이 다를 수 있다)
    for a, b, r in OM._runs_pos(doc, p):
        if b <= a or any(o.tag in OBJECTS for o in r):
            continue
        cid = r.get("charPrIDRef")
        if b <= plen and cid == old_l:
            r.set("charPrIDRef", OM.keep_fit(doc, sh["letter"], cid))
        elif a >= plen and cid == old_b:
            r.set("charPrIDRef", OM.keep_fit(doc, sh["body"], cid))
    wrote = False
    if not hold:
        tok = _renumber(sh["tok"], ln["tok"]) if ln["shape"] == "label" else sh["tok"]
        head = sh["lead"] + tok + sh["gap"]
        if head != text[:plen]:
            _splice(doc, p, 0, plen, head, len(ln["lead"]) if ln["tok"] else 0)
            wrote = True
        if ln["shape"] == "wrap" and ln["close"] != sh["close"]:
            now = doc._text(p)
            at = len(now) - len(ln["close"])
            _splice(doc, p, at, len(ln["close"]), sh["close"], at - 1)  # 닫는 괄호는 제목 끝 글자의 런에
            wrote = True
    doc._tidy(p)
    doc._drop_cache(p)
    doc._touch(p)
    return {"id": ln["id"], "text": wrote, "frozen": hold}


def carry(old, new):
    """2단계를 다시 돌려 개요 오버레이를 새로 만들 때 — 캡션 템플릿의 번호·사람이 정한 대표(`caps`)를 새 오버레이로(템플릿 키는 그래프와 무관해 그대로 옮긴다)."""
    if old and new is not None and old.get("caps") and "caps" not in new:
        new["caps"] = json.loads(json.dumps(old["caps"]))
