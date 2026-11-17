"""표 서식(spec_헤딩_추출 ② §19) — 표 **하나씩**, 같은 자리(머리행 · 머리열 · 합계행 · 열 · 빈 값)의 칸끼리 서식이 같은지 보고(점검), 다른 것을 그 자리의 대표에 맞춘다(맞추기).

- 칸 역할은 부르는 쪽이 준다(`tables_api._style_tb` — 3단계 결과의 그 표 | 그 표만의 초안 · 둘 다 사람의 헤더 지정을 덮음). 꼴 = heading_tables.collect 의 표(칸마다 id · row · col · rs · cs · role · sub? · paras).
- 견주는 서식 = 문단의 서식 요약(글꼴 · 크기 · 굵게 … · 정렬 · 줄 간격 · 문단 여백 — `doc.get_format`) + 칸의 세로 정렬 · 칸 여백(`doc.get_cell_format`). 음영 · 괘선은 안 본다(표 모양 — § 11).
- **빈 값 표시**: 표마다 글이 빈 값 표시뿐인 필드(빈 칸 · 줄표 홀로 · 「해당없음」 …) — 가장 많이 쓴 보이는 표시가 그 표의 표시. 줄표 글자가 다른 칸 · (조건이 맞으면) 빈 칸이 다른 서식.
- **맞추기**(`conform`)는 역변환 스크립트다 — 무엇을 맞출지는 사람(뒤에 LLM 계획)이 고르고, 바꾸는 것은 여기 하나다. 문서를 바꾸므로 부르는 쪽이 트랜잭션(`server._edit`) 안에서 부른다.
hwpx 만(칸 역할 판정이 hwpx 레코드 기반). 끝점은 `app/tables_api.py`, 화면은 `app/static/table_style.js`."""
import re
from collections import Counter

from app.hwpx_doc import P, RUN, SUBLIST, T
from app.hwpx_format import CHAR_KEYS as SETTABLE_CHAR_KEYS
from app.table_make import TOTAL_RE

# 장평 · 자간은 견주지 않는다 — 칸 폭에 맞춰 줄인 글이 많다(연구개발계획서 양식 135표: 다른 서식 326 가운데 자간 121). 맞출 때도 그 문단의 값을 지킨다.
PARA_KEYS = ("font", "fontLatin", "sizePt", "bold", "italic", "underline", "color",
             "align", "lineSpacingPct", "indentLeftMm", "indentRightMm", "firstLineMm", "spaceBeforePt", "spaceAfterPt")
CHAR_KEYS = frozenset({"font", "fontLatin", "sizePt", "bold", "italic", "underline", "color"})
BIG_SIZE = 2.0  # 크기가 이만큼(pt) 넘게 다르거나 글꼴 · 굵게가 다르면 「확인」 — 제목처럼 일부러 준 서식일 수 있다
LABELS = {"font": "글꼴", "fontLatin": "영문 글꼴", "sizePt": "크기", "bold": "굵게", "italic": "기울임", "underline": "밑줄", "color": "글자 색",
          "ratioPct": "장평", "spacingPct": "자간", "align": "가로 정렬", "lineSpacingPct": "줄 간격", "indentLeftMm": "왼쪽 여백",
          "indentRightMm": "오른쪽 여백", "firstLineMm": "첫 줄", "spaceBeforePt": "문단 위", "spaceAfterPt": "문단 아래",
          "valign": "세로 정렬", "margins": "칸 여백", "mark": "빈 값 표시"}
KINDS = {"head": "머리행", "stub": "머리열", "foot": "합계행", "col": "열", "empty": "빈 값"}
WHAT = ("para", "cell", "mark", "blank")
KEY_RE = re.compile(r"^(para|cell|mark|blank):[\w.-]+:[\w.-]*$")
_DASH = re.compile(r"^[\-–—－ㅡ‐‑]+$")
_WORD = re.compile(r"^(?:해당\s*없음|없음|미해당|N/?A)$", re.I)
_ALIGN = {"left": "왼쪽", "center": "가운데", "right": "오른쪽", "justify": "양쪽", "distribute": "배분"}
_VALIGN = {"top": "위", "center": "가운데", "bottom": "아래"}
_SIDES = (("l", "왼"), ("r", "오"), ("t", "위"), ("b", "아래"))
TEXT_MAX = 40  # 화면에 보이는 칸 글


# ---- 빈 값 표시 · 값 꼴 ---------------------------------------------------------------------------------------------

def empty_mark(text):
    """칸 글 → (무리, 표시) | None(값). 무리: blank(글 없음) · dash(줄표 홀로 — 「-」·「–」·「—」·「－」·「ㅡ」) · word(「해당없음」·「없음」·「N/A」)."""
    t = (text or "").strip()
    if not t:
        return ("blank", "")
    if _DASH.match(t):
        return ("dash", t)
    if _WORD.match(t):
        return ("word", t)
    return None


def _r(v, nd=1):
    return round(float(v), nd) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def para_look(summary):
    """서식 요약 → 견주는 값만 {키: 값}(mm · pt 는 0.1 단위)."""
    return {k: _r(summary.get(k)) for k in PARA_KEYS}


def cell_look(cf):
    """칸 서식(`get_cell_format`) → {valign, margins{l, r, t, b}}."""
    m = cf.get("marginsMm") or {}
    return {"valign": cf.get("valign"), "margins": {k: _r(m.get(k, 0.0)) for k, _ in _SIDES}}


def _sig(look):
    return tuple((k, tuple(sorted(v.items())) if isinstance(v, dict) else v) for k, v in sorted(look.items()))


def show(key, v):
    """값 하나의 화면 글(「160%」·「가운데」·「왼 1.8 · 오 1.8 · 위 0.5 · 아래 0.5mm」)."""
    if v is None:
        return "없음"
    if key == "margins":
        return " · ".join(f"{name} {v.get(k, 0):g}" for k, name in _SIDES) + "mm"
    if isinstance(v, bool):
        return "켬" if v else "끔"
    if key == "align":
        return _ALIGN.get(v, str(v))
    if key == "valign":
        return _VALIGN.get(v, str(v))
    if key in ("sizePt", "spaceBeforePt", "spaceAfterPt"):
        return f"{v:g}pt"
    if key in ("ratioPct", "spacingPct", "lineSpacingPct"):
        return f"{v:g}%"
    if key.endswith("Mm"):
        return f"{v:g}mm"
    if key == "mark":
        return f"「{v}」" if v else "빈 칸"
    return str(v)


def diff(now, want):
    """두 꼴의 다른 키 → [{key, label, now, want}](글은 `show`)."""
    return [{"key": k, "label": LABELS.get(k, k), "now": show(k, now.get(k)), "want": show(k, want.get(k))}
            for k in want if now.get(k) != want.get(k)]


def summary_text(look):
    """대표 서식 한 줄(「함초롬바탕 10pt · 가운데 · 줄 간격 130%」 — 굵게는 켜졌을 때만)."""
    if not look:
        return ""
    bits = [str(look.get("font") or "?"), show("sizePt", look.get("sizePt"))]
    bits += [LABELS[k] for k in ("bold", "italic", "underline") if look.get(k)]
    if look.get("align"):
        bits.append(show("align", look["align"]))
    if look.get("lineSpacingPct") is not None:
        bits.append(f"줄 간격 {show('lineSpacingPct', look['lineSpacingPct'])}")
    return " · ".join(bits)


def ref(row, col):
    """격자 자리 → 「B3」."""
    s, c = "", col + 1
    while c:
        c, m = divmod(c - 1, 26)
        s = chr(65 + m) + s
    return f"{s}{row + 1}"


def _short(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= TEXT_MAX else t[:TEXT_MAX - 1] + "…"


# ---- 자리 나누기 ----------------------------------------------------------------------------------------------------

def _paras(doc, cell):
    """칸의 지금 문서 문단 [(id, 글, 개체 있음)] — 없어진 문단은 뺀다."""
    out = []
    for pid in cell.get("paras") or []:
        el = doc._ids.get(pid)
        if el is None or el.tag != P or not doc._attached(el):
            continue
        out.append((pid, doc._text(el), doc._has_object(el)))
    return out


def places(doc, tb):
    """칸 → 자리. → (자리 키 → {kind, sub, col?, name, cells[칸…]}(문서 순), 칸 id → 그 칸의 지금 글).
    역할이 colhead·corner → 머리행, rowhead → 머리열, field 가운데 빈 값 표시뿐 → 빈 값(표 하나), 합계 행의 필드 → 합계행, 나머지 필드 → 열(서브 테이블 · 격자 열)."""
    cells = sorted(tb.get("cells") or [], key=lambda x: (x["row"], x["col"]))
    occ = {}
    for x in cells:
        for r in range(x["row"], x["row"] + x.get("rs", 1)):
            for c in range(x["col"], x["col"] + x.get("cs", 1)):
                occ.setdefault((r, c), x)
    texts, subs = {}, []
    for x in cells:
        texts[x["id"]] = " ".join(t for _, t, _ in _paras(doc, x)).strip()
        if x.get("sub") not in subs:
            subs.append(x.get("sub"))
    many = len([s for s in subs if s is not None]) > 1
    left = {}  # 서브 테이블마다 가장 왼쪽 격자 열
    for x in cells:
        left[x.get("sub")] = min(left.get(x.get("sub"), x["col"]), x["col"])

    def tag(sub):
        return f" · 표 {subs.index(sub) + 1}" if many else ""

    def col_name(x):
        heads = [h for h in cells if h.get("role") in ("colhead", "corner") and h.get("sub") == x.get("sub") and h["row"] < x["row"]
                 and h["col"] <= x["col"] < h["col"] + h.get("cs", 1)]
        h = max(heads, key=lambda h: h["row"], default=None)
        name = _short(texts.get(h["id"], "")) if h else ""
        return f"열 「{name}」" if name else f"{ref(0, x['col'])[:-1]}열"

    out = {}
    for x in cells:
        role, sub = x.get("role"), x.get("sub")
        objects = any(o for _, _, o in _paras(doc, x))
        if role in ("colhead", "corner"):
            key, kind, name = f"head:{sub}", "head", "머리행" + tag(sub)
        elif role == "rowhead":
            key, kind, name = f"stub:{sub}", "stub", "머리열" + tag(sub)
        elif role != "field":
            continue
        elif not objects and empty_mark(texts[x["id"]]) is not None:
            key, kind, name = "empty", "empty", "빈 값"
        else:
            first = occ.get((x["row"], left.get(sub, 0)))
            if first is not None and first is not x and TOTAL_RE.match(texts.get(first["id"], "")):
                key, kind, name = f"foot:{sub}", "foot", "합계행" + tag(sub)
            else:
                key, kind, name = f"col:{sub}:{x['col']}", "col", col_name(x) + tag(sub)
        pl = out.setdefault(key, {"key": key, "kind": kind, "sub": sub, "name": name, "cells": []})
        pl["cells"].append(x)
    return out, texts


# ---- 점검 ---------------------------------------------------------------------------------------------------------

def _rep(counts, order):
    """가장 많이 쓴 꼴(수가 같으면 문서 순 앞) | None."""
    if not counts:
        return None
    top = max(counts.values())
    return next(s for s in order if counts[s] == top)


def check(doc, tb, skip=frozenset(), source="stage3"):
    """표 하나의 점검 → {table, rows, cols, source, empty{…}, places[…], counts{places, odd, check}} — 문서는 안 바뀐다.
    skip = 견주지 않을 문단 id(개요 줄 — 템플릿이 다룬다). 빈 값 칸의 문단은 skip 이어도 본다(값 칸 — 「-」 홀로 줄)."""
    pls, texts = places(doc, tb)
    fmt_cache = {}

    def fmt(pid):
        if pid not in fmt_cache:
            fmt_cache[pid] = doc.get_format(pid)
        return fmt_cache[pid]
    out, total, checks = [], 0, 0
    empty_info = {"mark": None, "family": None, "counts": {}, "blanks": 0, "mixed": False, "fillBlanks": False}
    for pl in pls.values():
        empty = pl["kind"] == "empty"
        paras, cells = [], []  # [(칸, 문단 id, 꼴)] · [(칸, 칸 꼴)]
        for x in pl["cells"]:
            ps = _paras(doc, x)
            for pid, text, _obj in ps:
                if not text.strip() or (pid in skip and not empty):
                    continue
                paras.append((x, pid, para_look(fmt(pid)["summary"])))
            if ps or empty:
                cells.append((x, cell_look(doc.get_cell_format(x["id"]))))
        pc = Counter(_sig(lk) for _, _, lk in paras)
        cc = Counter(_sig(lk) for _, lk in cells)
        prep = _rep(pc, [_sig(lk) for _, _, lk in paras]) if len(paras) >= 2 else None
        crep = _rep(cc, [_sig(lk) for _, lk in cells]) if len(cells) >= 2 else None
        rp = next(((x, pid, lk) for x, pid, lk in paras if _sig(lk) == prep), None) if prep else (paras[0] if paras else None)
        rc = next(((x, lk) for x, lk in cells if _sig(lk) == crep), None) if crep else (cells[0] if cells else None)
        odd = []
        for x, pid, lk in paras:
            if prep and _sig(lk) != prep:
                dd = diff(lk, rp[2])
                why = _big(lk, rp[2])
                odd.append({"key": f"para:{x['id']}:{pid}", "what": "para", "cell": x["id"], "para": pid, "ref": ref(x["row"], x["col"]), "row": x["row"], "col": x["col"],
                            "text": _short(doc._text(doc._ids[pid])), "diff": dd, "check": bool(why), "why": why})
        for x, lk in cells:
            if crep and _sig(lk) != crep:
                odd.append({"key": f"cell:{x['id']}:", "what": "cell", "cell": x["id"], "para": None, "ref": ref(x["row"], x["col"]), "row": x["row"], "col": x["col"],
                            "text": _short(texts.get(x["id"], "")), "diff": diff(lk, rc[1]), "check": False, "why": ""})
        if empty:
            odd += _empty_odd(pl, texts, empty_info)
        odd.sort(key=lambda o: (o["what"] in ("mark", "blank"), o["row"], o["col"], WHAT.index(o["what"])))  # 서식은 칸 차례로, 빈 값 표시는 뒤에
        total += len(odd)
        checks += sum(1 for o in odd if o["check"])
        out.append({"key": pl["key"], "kind": pl["kind"], "kindName": KINDS[pl["kind"]], "name": pl["name"], "sub": pl["sub"], "cells": len(pl["cells"]),
                    "paras": len(paras), "looks": len(pc), "cellLooks": len(cc),
                    "rep": {"para": rp[1] if rp else None, "cell": rc[0]["id"] if rc else None, "look": rp[2] if rp else None,
                            "cellLook": rc[1] if rc else None, "text": summary_text(rp[2]) if rp else ""},
                    "odd": odd})
    order = {"head": 0, "stub": 1, "col": 2, "foot": 3, "empty": 4}
    out.sort(key=lambda p: (order[p["kind"]], str(p["sub"]), min((c["col"] for c in pls[p["key"]]["cells"]), default=0)))
    return {"table": tb.get("id"), "rows": tb.get("rows"), "cols": tb.get("cols"), "source": source, "empty": empty_info, "places": out,
            "counts": {"places": len(out), "odd": total, "check": checks}}


def _big(now, want):
    """크게 다른 꼴인가 → 까닭 글 | ""(글꼴 · 굵게가 다르거나 크기가 BIG_SIZE 넘게 다름 — 제목 · 강조처럼 일부러 준 서식일 수 있다)."""
    a, b = now.get("sizePt"), want.get("sizePt")
    if now.get("font") != want.get("font") or now.get("bold") != want.get("bold") or (isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) > BIG_SIZE):
        return "글꼴 · 크기 · 굵게가 크게 다릅니다 — 일부러 준 서식일 수 있습니다"
    return ""


def _empty_odd(pl, texts, info):
    """빈 값 자리 → 표시가 다른 칸(`mark`) · 표시를 넣을 빈 칸(`blank` — 확인)의 다른 서식. info 를 채운다."""
    seen = [(x, empty_mark(texts.get(x["id"], ""))) for x in pl["cells"]]
    seen = [(x, m) for x, m in seen if m is not None]
    visible = [(x, m) for x, m in seen if m[0] != "blank"]
    blanks = [x for x, m in seen if m[0] == "blank"]
    counts = Counter(m[1] for _, m in visible)
    mark = _rep(counts, [m[1] for _, m in visible])
    family = next((m[0] for _, m in visible if m[1] == mark), None)
    info.update(mark=mark, family=family, counts=dict(counts), blanks=len(blanks), mixed=len({m[0] for _, m in visible}) > 1,
                fillBlanks=len(visible) >= 2 and len(visible) > len(blanks) > 0)
    odd = []
    for x, (fam, m) in visible:
        if fam == family and m != mark:
            odd.append({"key": f"mark:{x['id']}:", "what": "mark", "cell": x["id"], "para": None, "ref": ref(x["row"], x["col"]), "row": x["row"], "col": x["col"], "text": m,
                        "diff": [{"key": "mark", "label": LABELS["mark"], "now": show("mark", m), "want": show("mark", mark)}], "check": False, "why": ""})
    if info["fillBlanks"]:
        for x in blanks:
            odd.append({"key": f"blank:{x['id']}:", "what": "blank", "cell": x["id"], "para": None, "ref": ref(x["row"], x["col"]), "row": x["row"], "col": x["col"], "text": "",
                        "diff": [{"key": "mark", "label": LABELS["mark"], "now": "빈 칸", "want": show("mark", mark)}], "check": True,
                        "why": "양식의 쓸 자리일 수 있습니다"})
    return odd


# ---- 맞추기(역변환 스크립트) ------------------------------------------------------------------------------------------

def _text_runs(p):
    return [r for r in p.iterchildren(RUN) if r.find(T) is not None]


def _fix_para(doc, pl, o):
    """문단 하나를 그 자리의 대표 문단 서식으로 — 바뀐 문단 id 목록."""
    rid = pl["rep"]["para"]
    el, rel = doc._ids.get(o["para"]), doc._ids.get(rid) if rid else None
    if el is None or not doc._attached(el):
        raise ValueError("그 문단이 없어졌습니다")
    if rel is None or not doc._attached(rel):
        raise ValueError("대표 문단이 없어졌습니다 — 다시 점검하세요")
    want = doc.get_format(rid)
    chars = {d["key"] for d in o["diff"]} & CHAR_KEYS
    if chars - SETTABLE_CHAR_KEYS:   # 영문 글꼴만 다름 — 글자 값으로는 못 바꾼다(글꼴 이름이 모든 언어에 걸림)
        if len({r.get("charPrIDRef") for r in _text_runs(el)}) > 1:
            raise ValueError("글자 모양이 섞인 문단의 영문 글꼴은 손으로 맞추세요")
        doc.apply_format([o["para"]], want, keep_numbering=True)            # 한 글자 모양 문단 — 대표의 글자 모양을 통째로(장평 · 자간도 대표 것)
    else:   # 런마다 제 글자 모양(강조 · 첨자 · 장평 · 자간)을 지키고 다른 값만 — 문단 모양은 대표 것
        doc.apply_format([o["para"]], want, keep_numbering=True, runs={k: want["summary"][k] for k in chars})
    return [o["para"]]


def _fix_cell(doc, pl, o):
    cl = pl["rep"]["cellLook"]
    if not cl:
        raise ValueError("대표 칸이 없습니다")
    if doc._ids.get(o["cell"]) is None:
        raise ValueError("그 칸이 없어졌습니다")
    parts = [{"valign": "valign", "margins": "margins"}[d["key"]] for d in o["diff"] if d["key"] in ("valign", "margins")]
    if parts:
        doc.apply_cell_format([o["cell"]], {"valign": cl["valign"], "marginsMm": cl["margins"]}, parts, keep_numbering=True)
    return []


def _fix_mark(doc, report, pl, o):
    """빈 값 칸의 글을 그 표의 표시로 + 빈 값 대표 문단의 서식."""
    mark = report["empty"].get("mark")
    if not mark:
        raise ValueError("이 표의 빈 값 표시가 없습니다")
    tc = doc._ids.get(o["cell"])
    if tc is None or not doc._attached(tc):
        raise ValueError("그 칸이 없어졌습니다")
    doc.set_text(o["cell"], mark)
    rid = pl["rep"]["para"]
    rel = doc._ids.get(rid) if rid else None
    if rel is None or not doc._attached(rel):
        return []
    sub = doc._ids[o["cell"]].find(SUBLIST)
    ids = [doc._id(p) for p in sub.iterchildren(P)] if sub is not None else []
    if ids:
        doc.apply_format(ids, doc.get_format(rid), keep_numbering=True)
    return ids


def conform(doc, report, keys):
    """고른 다른 서식(항목 키)을 그 자리의 대표로 → {done[키], skipped[{key, why}], formatted[문단 id]}.
    report = 같은 문서 상태에서 막 낸 `check` 결과(요청 직전에 다시 점검한 것 — 그 사이 같아진 항목은 건너뜀). 차례: 문단 · 칸 → 빈 값 표시(칸 글을 바꾸므로 뒤)."""
    items = {o["key"]: (pl, o) for pl in report["places"] for o in pl["odd"]}
    todo = list(dict.fromkeys(keys))
    todo.sort(key=lambda k: k.split(":", 1)[0] in ("mark", "blank"))
    done, skipped, formatted = [], [], []
    for k in todo:
        if k not in items:
            skipped.append({"key": k, "why": "이미 같거나 없어졌습니다"})
            continue
        pl, o = items[k]
        try:
            if o["what"] == "para":
                ids = _fix_para(doc, pl, o)
            elif o["what"] == "cell":
                ids = _fix_cell(doc, pl, o)
            else:
                ids = _fix_mark(doc, report, pl, o)
        except (ValueError, KeyError) as e:
            skipped.append({"key": k, "why": str(e) or "맞추지 못했습니다"})
            continue
        done.append(k)
        formatted += [i for i in ids if i not in formatted]
    return {"done": done, "skipped": skipped, "formatted": formatted}
