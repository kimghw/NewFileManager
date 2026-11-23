"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 개요 오버레이(`app/outline_edit.py`) 위.

- 서식 갈래(`variants`): 슬롯(템플릿, 레벨)의 줄들을 비교 값(`look`)이 같은 것끼리 묶는다 — 접두(앞 공백·레터 글자·레터 뒤 공백) · 문단 · 레터 글자 · 본문 바탕 글자.
- 대표 정하기(`set_rep`) = 오버레이 슬롯의 rep·동결 접두·모양을 그 문단의 지금 것으로(문서는 안 바뀜).
- 대표에 맞추기(`match`) = 대표와 다른 슬롯 줄을 대표의 지금 모양으로(문서를 바꿈 — 부르는 쪽이 트랜잭션 안에서).
- 템플릿 종속(`merge`·`unmerge`·`carry`) = 템플릿 B 가 (A, at) 줄 아래 매달린 곳의 B 줄을 (A, at + 레벨)로 — 오버레이만 바꾼다.
- 서식 종속 템플릿(`split`·`unsplit` — ② §8-5) = (A, Lk) 의 일부러 다른 서식 갈래를 「T{A}L{k}a」 로 뗀다(그 줄과 자손 · base = k − 1) — 오버레이만 바꾼다.
"""
import copy
import hashlib
import json
import re
import weakref
from collections import Counter

from app import outline_edit as OE
from app.hwpx_format import CHAR_LANGS, _h
from app.hwpx_struct import OBJECTS, P, RUN, TC, TR, MarkBlock

CHAR_KEYS = ("font", "sizePt", "bold", "italic", "underline", "color", "ratioPct", "spacingPct")
PARA_KEYS = ("align", "line1Mm", "line2Mm", "indentRightMm", "spaceBeforePt", "spaceAfterPt", "lineSpacingPct")
# 줄 맞춤 값(② §8-2 「줄 맞춤 값」 — 2026-11-16): 장평·자간은 한 줄에 넣으려고 줄마다 줄여 둔 값일 수 있다 — 갈래를 가르는 비교 값에 넣지 않고(자간만 다른 줄은 같은 갈래),
# 맞출 때도 그 줄의 것을 지킨다(`keep_fit`). `look` 에는 그대로 실린다(화면 견본 · 지킬 값).
FIT_KEYS = ("ratioPct", "spacingPct")
CMP_CHAR = tuple(k for k in CHAR_KEYS if k not in FIT_KEYS)
# 비교 값의 차례(화면의 「대표와 다른 값」 차례) — 접두 → 문단 → 레터 글자(L.) → 본문 바탕 글자
KEYS = ("lead", "letter", "gap") + PARA_KEYS + tuple("L." + k for k in CMP_CHAR) + CMP_CHAR
LABELS = {"lead": "레터 앞 빈칸", "letter": "레터", "gap": "레터 뒤 빈칸", "align": "정렬", "line1Mm": "앞 여백", "line2Mm": "2번째 줄",
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
        parts.append(f"{n}칸" if ch == " " else f"묶음 {n}칸" if ch == "\u2002" else f"탭{n if n > 1 else ''}" if ch == "\t" else f"전각 {n}칸" if ch == "　" else f"U+{ord(ch):04X}×{n}")
        i = j
    return " + ".join(parts)


def _form(tok, key):
    """레터의 꼴 — 번호형은 번호 글자를 「#」 로(「3.」·「4.」 는 같은 꼴), 기호는 글자 그대로(「o」·「ㅇ」 는 다른 꼴). 본은 outline_edit.letter_form(오버레이가 자동 글머리 줄을 고를 때도 같은 꼴)."""
    return OE.letter_form(tok, key)


# 닮은 레터 글자(spec_hwpx_웹편집 ② §8-5 「닮은 글자」 — 2026-11-17 사용자 「이것도 같은 서식을 갖어야 하는데 .. 식별이 안되었나? 이건 같은 템플릿에서 같은 뿌리인데」 → 답 「같은 레터 · 글자도 대표로」):
# 헤딩 판정이 **같은 레터 키**로 묶는 글자(「o」·「ㅇ」·「○」 → 「o」 · 「·」·「⋅」·「•」 → 「·」 — heading_graph.VARIANTS · heading_rules 의 계열)는 사람마다 다르게 친 같은 레터다 — 「레터」 가 다른 것이 아니다.
# 속이 찬 기호는 닮은 글자로 보지 않는다 — 같은 꼴의 빈 기호(□·○·△·◇·▫·▷)와 일부러 달리 썼을 수 있다(에이전트 판단 — 사용자 확인 전: 같은 사양서 ④).
FILLED = frozenset("■●▲◆▪▶►➤")
GLYPH = "닮은 레터 글자"  # diff 의 이름 — 레터는 같고 글자만 다름(LABELS["letter"] = 「레터」 는 레터가 다를 때만)


def kin(tok, key):
    """레터의 **계열** — 같으면 같은 레터다(글자가 달라도 닮은 글자). 줄의 레터 키(헤딩 판정의 정규 키) + 속이 찬 기호인가. 키가 없는 줄은 글자 그대로."""
    return (key or tok) + ("/찬" if tok[:1] in FILLED else "")


# 자동 글머리 줄(spec_hwpx_웹편집 ② §8-8 「자동 글머리 줄」 — 2026-11-17 사용자 「이거는 LLM 조정할 때 대표 서식에 포함되도록 안 되나? 왜 남아 있지?」 → 답 「친 레터로 바꿔 맞춤」):
# 레터가 글이 아니라 문단 모양의 글머리표·문단 번호인 줄(오버레이 ov["autos"] — outline_edit.auto_view). 그 레벨의 서식 갈래에 들고, 비교 값 「자동 글머리」 가 대표(친 레터)와 다르다 —
# 레터가 다른 것이 아니다(라벨이 그 레벨의 레터: 떼는 기준이 아님). 대표가 될 수 없고(접두를 얼릴 글이 없다) 다른 템플릿으로 떼지 않는다 · 맞추면 친 레터의 보통 줄이 된다(match_one).
AUTO = "자동 글머리"  # diff 의 이름
AUTO_SHOWN = {"": "친 글자", "bullet": "자동 글머리표", "number": "자동 번호"}
AUTO_REP = "자동 글머리표·문단 번호 줄은 레터가 글에 없어 대표가 될 수 없습니다 — 친 레터의 줄을 대표로 정하세요(맞추면 이 줄도 친 레터가 됩니다)"
AUTO_SPLIT = "자동 글머리표·문단 번호 줄은 다른 템플릿으로 떼지 않습니다 — 대표에 맞추면 친 레터가 됩니다"


def auto_kind(doc, pid):
    """문단 pid 의 문단 모양이 글머리표 · 문단 번호면 "bullet" | "number", 아니면 None(개요 번호 OUTLINE 은 아니다 — 한글이 번호 글을 비워 둔 양식이 흔하다)."""
    el = doc._ids.get(pid) if hasattr(doc, "_heading") else None
    h = doc._heading(el) if el is not None and el.tag == P else None
    kind = h.get("type") if h is not None else None
    return {"BULLET": "bullet", "NUMBER": "number"}.get(kind)


def _is_auto(ov, pid):
    return pid not in ov["lines"] and pid in (ov.get("autos") or {})


def auto_numbers(doc, ov, tid=None, level=None):
    """자동 번호 줄(ov["autos"] 의 number — tid·level 을 주면 그 레벨 것만)의 레터를 **지금 문서에 보이는 번호**로 — 맞추기 전에 한 번(맞추면 그 줄이 번호 매김에서 빠져
    뒤 줄의 번호가 당겨지므로, 맞출 줄들의 번호는 바꾸기 전에 함께 센다). 번호는 화면 블록과 같은 셈(hwpx_doc._list_info — 번호 정의마다 문서 차례로). -> 바꾼 줄 수."""
    autos = ov.get("autos") or {}
    want = [p for p, a in autos.items() if a.get("auto") == "number"
            and (tid is None or (OE.auto_slot(ov, p) or (None, None)) == (str(tid), int(level)))]
    if not want or not hasattr(doc, "_list_info"):
        return 0
    want, labels = set(want), {}
    saved = doc._num_ctr
    doc._num_ctr = {}
    try:
        for sec in doc._sections:
            for p in sec.iter(P):
                h = doc._heading(p)
                if h is None or h.get("type") != "NUMBER":
                    continue
                info = doc._list_info(h)
                pid = doc._rev.get(p)
                if pid in want and info.get("label"):
                    labels[pid] = info["label"]
    finally:
        doc._num_ctr = saved
    n = 0
    for pid, lab in labels.items():
        if autos[pid]["letter"] != lab:
            autos[pid]["letter"] = lab
            n += 1
    return n


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
    if x is None and pid in (ov.get("autos") or {}):
        x = OE.auto_view(ov, pid)  # 자동 글머리 줄 — 지금 자리(템플릿·레벨)의 줄 꼴(사본: 고쳐도 오버레이는 안 바뀐다 — 맞추면 promote)
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
    lt = tok or (x.get("letter") or "" if x.get("auto") else "")  # 자동 글머리 줄(② §8-8) — 레터는 글이 아니라 라벨(그 레벨의 레터: 「레터」 가 다른 것이 아니다)
    out = {"lead": lead, "letter": "" if x.get("role") in OE.ROOTED else _form(lt, x.get("key") or ""), "gap": gap}
    out["kin"] = "" if x.get("role") in OE.ROOTED else kin(lt, x.get("key") or "")  # 레터 계열 — 비교 값(KEYS)이 아니다: 갈래는 전처럼 글자로 가르고, diff 가 다른 글자의 이름만 정한다
    if x.get("auto"):
        out["auto"] = x["auto"]  # 자동 글머리(② §8-8) — KEYS 밖의 비교 값(same · diff · 갈래 열쇠가 따로 본다: 친 레터 줄의 지문은 전과 같다)
    tf = table_form(doc, ov, p)  # 표 양식(② §8-11) — 비교 값(KEYS)이 아니다: 대표와 서식이 다른 표 안의 줄을 표 양식마다 다른 갈래로 가른다(variants · mate)
    out["form"], out["formLabel"] = (tf["key"], tf["label"]) if tf else ("", "")
    if left is None or first is None:
        out["line1Mm"] = out["line2Mm"] = None
    else:
        out["line1Mm"], out["line2Mm"] = _r(left + max(first, 0.0)), _r(left + max(-first, 0.0))
        if x.get("role") not in OE.ROOTED and _at_text(doc, p, lead, tok, gap, first):
            out["line2At"] = AT_TEXT  # 둘째 줄이 제 글 시작에 있다 — 비교는 mm 값이 아니라 이것으로(cval)
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
    if key == "auto":
        return AUTO_SHOWN.get(v or "", str(v))
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


AT_TEXT = "글 시작"  # 「2번째 줄」 의 비교 값 — 둘째 줄이 그 줄의 글 시작에 있다(자리 규칙대로: spec_hwpx_웹편집 ② §8-8 「규칙이 같으면 같은 서식」)
_MEASURES = weakref.WeakKeyDictionary()  # 문서 → (글자 폭 재개 outline_pos.Measure, 접두 폭 기억 {(접두 글, 글자 모양 id 들): mm | None})


def _at_text(doc, p, lead, tok, gap, first):
    """그 줄의 둘째 줄이 **제 글 시작**(첫 줄 시작 + 접두 폭)에 있는가 — 내어쓰기 값이 접두 폭과 같다. 접두를 못 재면(탭 · 긴 접두) False.
    같은 레벨에서도 접두 폭은 줄마다 다를 수 있다(번호형 「9.」·「10.」 · 줄 맞춤으로 자간을 줄인 레터) — 그런 줄들의 둘째 줄 mm 값은 달라도 서식(규칙)은 같다."""
    if not tok:
        return False
    from app import outline_pos as OP  # outline_pos 는 이 모듈을 함수 안에서만 읽는다 — 서로 물리지 않게 여기서도 함수 안에서
    from app.heading_extract import _cid_at as cid_of, run_ranges
    # 재개는 문서를 약하게 쥔다(weakref.proxy) — 값이 문서를 강하게 쥐면 약한 키가 끝내 안 풀려, 실행 취소 · 되돌림이 새 문서를 열 때마다 옛 문서 전체가 남았다(2026-11-17 검토)
    m, memo = _MEASURES.get(doc) or _MEASURES.setdefault(doc, (OP.Measure(weakref.proxy(doc)), {}))
    rr, fb = run_ranges(doc, p), doc._char_id(p)
    text = lead + tok + gap
    cids = tuple(cid_of(rr, i, fb) for i in range(len(text)))
    key = (text, cids)
    if key not in memo:
        try:
            memo[key] = m.width(text, lambda i: cids[i]) if all(ch in OP.BLANKS for ch in lead + gap) else None
        except Exception:  # noqa: BLE001 — 폭을 못 재는 줄 하나가 서식 갈래 읽기를 막지 않게
            memo[key] = None
    w = memo[key]
    return w is not None and w <= OP.MAX_PREFIX_MM and abs(max(first, 0.0) + w - max(-first, 0.0)) <= 0.05


def cval(lk, k):
    """비교에 쓰는 값 — 「2번째 줄」 은 둘째 줄이 제 글 시작에 있으면 mm 값이 아니라 AT_TEXT(규칙이 같으면 같은 서식 — ② §8-8). 그 밖은 `look` 의 값 그대로."""
    return AT_TEXT if k == "line2Mm" and lk.get("line2At") else lk.get(k)


def cshown(lk, k):
    """비교 값의 화면 글 — 「2번째 줄」 이 글 시작에 있으면 「글 시작(9.7mm)」."""
    v = lk.get(k)
    return f"{AT_TEXT}({v:g}mm)" if k == "line2Mm" and lk.get("line2At") and v is not None else shown(k, v)


def diff(a, b):
    """비교 값 a(대표) 와 b 의 다른 키 → [[키, 이름, 대표 글, b 글]…](KEYS 차례).
    레터 글자가 달라도 **계열이 같으면**(`kin` — 닮은 글자) 이름은 「레터」 가 아니라 「닮은 레터 글자」(GLYPH)다 — 서식 정리 에이전트가 떼는 기준은 이름이 「레터」 인 항목뿐이다."""
    glyph = bool(a.get("kin")) and a.get("kin") == b.get("kin")
    out = [["auto", AUTO, shown("auto", a.get("auto")), shown("auto", b.get("auto"))]] if (a.get("auto") or "") != (b.get("auto") or "") else []  # 자동 글머리(② §8-8) — 맨 앞
    out += [[k, GLYPH if k == "letter" and glyph else LABELS.get(k, k), cshown(a, k), cshown(b, k)] for k in KEYS if cval(a, k) != cval(b, k)]
    if b.get("form") and (a.get("form") or "") != b["form"]:  # 표 안의 줄 — 대표 줄과 표 양식이 다르다(② §8-11: 「표: 대표의 머리글 → 이 갈래의 머리글」)
        out.append(["form", FORM, a.get("formLabel") or "표 밖", b.get("formLabel") or "—"])
    return out


def same(a, b):
    """두 줄의 비교 값이 같은가 — KEYS 와 자동 글머리(② §8-8)를 견준다(`look` 에 함께 실린 줄 맞춤 값 FIT_KEYS 는 안 본다). 「2번째 줄」 은 규칙으로(cval)."""
    return (a.get("auto") or "") == (b.get("auto") or "") and all(cval(a, k) == cval(b, k) for k in KEYS)


def _cell_of(p):
    """문단이 든 **여러 칸 표의 칸**(hp:tc) | None(본문 · 머리말 …). 1칸 상자는 투명 — 바깥 그릇으로(헤딩 그래프의 흐름과 같은 기준: heading_graph._flow)."""
    el = p.getparent()
    while el is not None:
        if el.tag == TC:
            tr = el.getparent()
            tbl = tr.getparent() if tr is not None else None
            if tbl is not None and sum(1 for r in tbl.iterchildren(TR) for _ in r.iterchildren(TC)) > 1:
                return el
        el = el.getparent()
    return None


# ---------------------------------------------------------------- 표 안의 줄 — 표 양식마다의 서식(spec_hwpx_웹편집 ② §8-11)
# 2026-11-17 사용자 「테이블은 같은 형식/ 헤더열/행을 보면 같은건지 알겠지? 같은 것끼리는 서식을 공유하지만 그렇지 않은 경유, 기존 테이블 안의 서식을 사용해 주는게 맞는거 같아」 —
# 표 칸의 줄은 레터 사슬이 같으면 문서 전체에서 한 템플릿이라(「N. › -」), 「레터가 같으면 대표에 맞춘다」 를 그대로 걸면 8pt 표의 줄이 다른 표의 대표 서식(10pt 굵게)이 된다.
FORM = "표"  # diff 의 이름 — 대표 줄과 표 양식이 다름(키 `form` — 비교 값 KEYS 가 아니다)
_FORMS = weakref.WeakKeyDictionary()  # 문서 → (고친 차례 doc._gen, {표 요소: 표 양식})
_FORM_DROP = re.compile(r"[\W\d_]+")  # 머리글 지문에서 빼는 것 — 빈칸 · 숫자 · 문장 부호(「1차년도」·「2차년도」 는 같은 머리글)


def _read_form(doc, tbl, lines):
    """표 하나 → {key(양식 지문), label(머리글 — 화면 글), around(주변 글 Counter{(글꼴, 크기, 굵게): 글자 수})}.
    머리글 = 음영이 있는 칸의 글((행, 열) 차례) — 없으면 첫 행, 그것도 비면 그 표 하나가 한 양식. 주변 글 = 개요 줄(lines)이 아닌 문단의 첫 글자 모양(머리글 칸은 빼고 — 다 머리글이면 전부)."""
    from app.hwpx_doc import CELLADDR, SUBLIST  # 함수 안에서 — 모듈을 서로 물리지 않게

    cells = []
    for r, tr in enumerate(tbl.iterchildren(TR)):
        for c, tc in enumerate(tr.iterchildren(TC)):
            addr, sub = tc.find(CELLADDR), tc.find(SUBLIST)
            ps = [q for q in sub.iterchildren(P)] if sub is not None else []
            cells.append((int(addr.get("rowAddr", r)) if addr is not None else r, int(addr.get("colAddr", c)) if addr is not None else c,
                          bool(doc._shaded(tc.get("borderFillIDRef"))), ps))
    cells.sort(key=lambda x: (x[0], x[1]))
    text = lambda ps: " ".join(t for t in (doc._text(q).strip() for q in ps) if t)  # noqa: E731
    heads = [text(ps) for _, _, shaded, ps in cells if shaded]
    if not any(heads):
        top = min((x[0] for x in cells), default=0)
        heads = [text(ps) for r, _, _, ps in cells if r == top]
    heads = [h for h in heads if _FORM_DROP.sub("", h)]
    sig = "|".join(_FORM_DROP.sub("", h)[:24] for h in heads)
    key = hashlib.sha1((sig or f"표 {id(tbl)}").encode("utf-8")).hexdigest()[:10]
    short = [h if len(h) <= 14 else h[:13] + "…" for h in (" ".join(h.split()) for h in heads[:3])]
    label = (" · ".join(short) + (" …" if len(heads) > 3 else "")) if short else "머리글 없는 표"
    around, shaded_only = Counter(), not any(not sh for _, _, sh, _ in cells)
    for _, _, shaded, ps in cells:
        if shaded and not shaded_only:
            continue
        for q in ps:
            n = len(doc._text(q).strip())
            if not n or doc._rev.get(q) in lines:
                continue
            sm = doc._summary(q.get("paraPrIDRef"), doc._char_id(q))
            around[(sm.get("font") or "", sm.get("sizePt") or 0, bool(sm.get("bold")))] += n
    return {"key": key, "label": label, "around": around}


def table_of(p):
    """문단이 든 여러 칸 표(hp:tbl) | None(표 밖 · 1칸 상자 안 — `_cell_of` 와 같은 기준)."""
    tc = _cell_of(p)
    tr = tc.getparent() if tc is not None else None
    return tr.getparent() if tr is not None else None


def table_form(doc, ov, p):
    """문단 p 가 든 표의 **표 양식**(② §8-11) → {key, label, around} | None(표 밖). 같은 문서 상태에서는 표마다 한 번만 읽는다(문서를 고치면 다시 — doc._gen)."""
    tbl = table_of(p)
    if tbl is None:
        return None
    gen = getattr(doc, "_gen", 0)
    memo = _FORMS.get(doc)
    if memo is None or memo[0] != gen:
        memo = _FORMS[doc] = (gen, {})
    if tbl not in memo[1]:
        memo[1][tbl] = _read_form(doc, tbl, ov.get("lines") or {})
    return memo[1][tbl]


def around_text(counter):
    """주변 글 Counter → 「Dotum 8pt」 · 「Dotum 10pt 굵게」 | ""(글이 없음) — 가장 흔한 글자 모양 하나."""
    if not counter:
        return ""
    font, size, bold = counter.most_common(1)[0][0]
    return " ".join(x for x in (font, f"{size:g}pt" if size else "", "굵게" if bold else "") if x)


_LOOK_ONLY = ("line2At", "kin", "form", "formLabel", "auto")  # `look` 에 함께 실리지만 화면의 서식 값(갈래의 look)이 아닌 것


def _form_view(doc, ov, paras):
    """줄들이 든 표들의 양식 → {key, label(머리글), tables(표 수), around(주변 글 — 그 표들의 가장 흔한 글자 모양)} | None(표 밖)."""
    tabs, total, first = set(), Counter(), None
    for q in paras:
        el = doc._ids.get(q)
        tbl = table_of(el) if el is not None else None
        if tbl is None or tbl in tabs:
            continue
        tabs.add(tbl)
        f = table_form(doc, ov, el)
        first = first or f
        total.update(f["around"])
    return {"key": first["key"], "label": first["label"], "tables": len(tabs), "around": around_text(total)} if first else None


def mate(lk, kind, base=None):
    """lk 가 kind 와 **같은 갈래**인가(② §8-11 「갈래는 표 양식마다」) — 서식(KEYS)이 같고, 표 양식도 같다. kind 가 대표(base)와 같은 서식이면 표 양식은 안 본다(대표 갈래는 어느 표든 하나)."""
    return same(lk, kind) and ((lk.get("form") or "") == (kind.get("form") or "") or (base is not None and same(kind, base)))


def rep_forms(looks, base):
    """대표(base)와 서식이 같은 줄이 있는 표 양식들 — 그 표는 대표 서식을 쓴다. looks = 그 레벨 줄들의 비교 값."""
    return {lk["form"] for lk in looks if lk.get("form") and same(lk, base)}


def is_own(lk, base, forms):
    """「표의 서식」 인가(② §8-11) — 표 안의 줄이고 대표와 서식이 다르며, 그 표 양식에 대표 서식의 줄이 하나도 없다. 대표에 맞추지 않는다(골라서 맞추는 것은 됨)."""
    return bool(lk.get("form")) and lk["form"] not in forms and not same(lk, base)


def lone_value(doc, ov, pid):
    """값 칸(② §8-2 「값 칸」 — 2026-11-16): 여러 칸 표의 칸에 **글이 있는 문단이 이 줄 하나뿐이고 레터만 있는**(제목 없음) 줄 — 표의 빈 값 「-」 · 번호 칸 「1.」.
    개요 줄처럼 보여도 값이라 서식 갈래에 넣지 않고 맞추지도 떼지도 않는다(가운데 놓인 「-」 가 글머리 서식(왼쪽 · 「- 」)이 된다). 괄호 줄(구분 라벨)은 값이 아니다."""
    x, p = ov["lines"].get(pid), doc._ids.get(pid)
    if x is None or p is None or x.get("role") in OE.ROOTED:
        return False
    try:
        lead, tok, gap, plen, text = parts(doc, ov, pid)
    except (KeyError, ValueError):
        return False
    if not tok or text[plen:].strip():
        return False
    cell = _cell_of(p)
    if cell is None:
        return False
    # 그 칸의 흐름에 든 다른 문단(안쪽 여러 칸 표의 칸은 다른 흐름 — 헤딩 그래프의 값 칸 규칙 heading_graph.value_cell 과 같은 셈)에 글·개체가 있으면 값 칸이 아니다
    return not any(q is not p and _cell_of(q) is cell and (doc._text(q).strip() or doc._has_object(q)) for q in cell.iter(P))


def _fit_of(doc, cid):
    """글자 모양 cid 의 줄 맞춤 값 ((언어, 장평)…, (언어, 자간)…) | None(정의 없음) — **언어마다의 값 그대로**(한글 −10 · 영문 0 처럼 다를 수 있다)."""
    c = doc._defs["charPr"].get(str(cid)) if cid is not None else None
    if c is None:
        return None
    out = []
    for tag, dflt in (("ratio", "100"), ("spacing", "0")):
        e = c.find(_h(tag))
        out.append(tuple((lang, e.get(lang, dflt) if e is not None else dflt) for lang in CHAR_LANGS))
    return tuple(out)


def _bare(doc, cid):
    """글자 모양 cid 에서 줄 맞춤 값(장평·자간)을 뺀 지문 | None(정의 없음) — 두 글자 모양이 장평·자간만 다른가를 견준다(같은 바탕의 본문 런)."""
    c = doc._defs["charPr"].get(str(cid)) if cid is not None else None
    if c is None:
        return None
    skip = {_h("ratio"), _h("spacing")}

    def sig(e):
        return (e.tag, tuple(sorted((k, v) for k, v in e.attrib.items() if not (e is c and k == "id"))), (e.text or "").strip(), tuple(sig(x) for x in e if not (e is c and x.tag in skip)))
    return sig(c)


def keep_fit(doc, new_id, old_id):
    """글자 모양 new_id 에 old_id 의 장평·자간을 얹은 글자 모양 id — 맞춰도 그 줄의 줄 맞춤 값은 지킨다(FIT_KEYS · 언어마다의 값 그대로). 같으면 new_id 그대로."""
    a, b = _fit_of(doc, new_id), _fit_of(doc, old_id)
    if a is None or b is None or a == b:
        return new_id
    c = copy.deepcopy(doc._defs["charPr"][str(new_id)])
    doc._set_chars(c, {"ratioPct": 100, "spacingPct": 0})  # 요소가 없으면 제자리에 만든다(값은 아래에서 언어마다)
    for tag, vals in zip(("ratio", "spacing"), b):
        e = c.find(_h(tag))
        for lang, v in vals:
            e.set(lang, v)
    return doc._add_def("charPr", c)


# 본문 강조(굵게 · 기울임 · 밑줄 — 본문 바탕 글자의 것): 넣은 뒤 정리(spec_병합 ② §5-9)가 넣는 쪽의 서식을 받는 레벨(grown · deep · cut — 「긴 쪽을 받아서」)에서 줄마다 지킨다.
# 원본에서 굵은 소제목이던 넣은 줄(레터 런은 보통 · 본문 런은 굵게)이 넣은 줄끼리의 대표(본문 보통)에 맞춰지며 굵기를 잃었다(한글 출력 실측 2026-11-22). 레터 런 · 문단 · 그 밖의 글자 값(글꼴 · 크기 …)은 대표를 따른다.
EMPH = ("bold", "italic", "underline")


def keep_emph(doc, new_id, old_id, keys=EMPH):
    """글자 모양 new_id 에 old_id 의 강조(keys — 굵게 · 기울임 · 밑줄)를 얹은 글자 모양 id — 같으면 new_id 그대로 · 같은 정의가 이미 있으면 그것(_add_def).
    밑줄은 그 줄의 꼴(종류 · 모양 · 색) 그대로 옮긴다."""
    defs = doc._defs["charPr"]
    a, b = defs.get(str(new_id)) if new_id is not None else None, defs.get(str(old_id)) if old_id is not None else None
    if a is None or b is None or str(new_id) == str(old_id):
        return new_id
    sa, sb = doc._char_summary(a), doc._char_summary(b)
    ch = {k: sb[k] for k in keys if sa.get(k) != sb.get(k)}
    if not ch:
        return new_id
    c = copy.deepcopy(a)
    doc._set_chars(c, ch)
    if ch.get("underline"):
        u, ub = c.find(_h("underline")), b.find(_h("underline"))
        if u is not None and ub is not None:
            u.attrib.update(ub.attrib)
    return doc._add_def("charPr", c)


def own_emph(doc, ov, pid, sh, keys=EMPH):
    """대표 모양 sh(rep_shape)의 본문 바탕 글자를 **줄 pid 의 강조를 얹은 것**으로 바꾼 사본 — match_one 이 옛 본문 바탕 글자의 런을 그것으로 바꾼다(강조는 그 줄의 것 · 나머지는 대표).
    본문이 없는 줄 · 바꿀 것이 없으면 sh 그대로."""
    lead, tok, gap, plen, text = parts(doc, ov, pid)
    if plen >= len(text):
        return sh
    body = sh.get("body") or sh["attrs"]["charPrIDRef"]
    got = keep_emph(doc, body, _cid_at(doc, doc._ids[pid], plen), keys)
    return sh if got == body else {**sh, "body": got}


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
    """(tid, level) 의 줄 — 개요 줄 + 자동 글머리 줄(② §8-8 — 지금 자리가 그 레벨인 것: outline_edit.auto_slot)."""
    out = [pid for pid, x in ov["lines"].items() if x["tpl"] == str(tid) and int(x["level"]) == int(level)]
    if ov.get("autos"):
        want = (str(tid), int(level))
        out += [pid for pid in ov["autos"] if pid not in ov["lines"] and OE.auto_slot(ov, pid) == want]
    return out


def variants(doc, ov, tid, level, order=None, full=False):
    """슬롯 (tid, level) 의 서식 갈래 → {total, rep, repMissing, values(값 칸 줄 수 — 갈래에 안 넣음: lone_value), groups[{key, count, paras(문서 순 30개까지 — full 이면 전부), more, rep, look(화면 글), raw(원값), diff, near(대표와 오차 안)}]} — 대표 갈래 먼저, 그다음 줄 수 순.
    갈래는 비교 값 KEYS 가 모두 같은 줄 — 줄 맞춤 값(장평·자간)은 달라도 같은 갈래다."""
    order = order if order is not None else _order(doc)
    sl = OE._slot(ov, tid, level) or {}
    alive = sorted((p for p in slot_ids(ov, tid, level) if _alive(doc, p)), key=lambda p: order.get(p, 1 << 30))
    ids = [p for p in alive if not lone_value(doc, ov, p)]
    groups, looks, fkey = {}, {}, {}
    for pid in ids:
        try:
            lk = look(doc, ov, pid)
        except (KeyError, ValueError):
            continue
        looks[pid] = lk
        fkey[pid] = repr([cval(lk, k) for k in KEYS]) + (f"|자동:{lk['auto']}" if lk.get("auto") else "")  # 자동 글머리 줄(② §8-8)은 따로 — 친 레터 줄의 열쇠는 전과 같다
    rep = sl.get("rep") if sl.get("rep") in looks and not _is_auto(ov, sl["rep"]) else None  # 자동 글머리 줄은 대표가 아니다(② §8-8 — 그래프가 그 줄을 대표로 뽑았던 레벨은 「대표 없음」)
    rep_key = fkey[rep] if rep else None
    base = looks[rep] if rep else None  # 대표 **줄**의 비교 값(대표 갈래의 첫 줄이 아니라 — 표 양식은 줄마다 다를 수 있다)
    for pid, lk in looks.items():
        # 갈래 열쇠(② §8-11 「갈래는 표 양식마다」): 대표와 서식이 같은 줄 · 표 밖의 줄 = 서식 / 표 안의 다른 서식 줄 = 서식 + 표 양식(서식이 같아도 표 양식이 다르면 다른 갈래)
        key = fkey[pid] if (fkey[pid] == rep_key or not lk.get("form")) else fkey[pid] + "|" + lk["form"]
        groups.setdefault(key, {"key": key, "paras": [], "look": lk})["paras"].append(pid)
    uses_rep = {looks[p]["form"] for p in groups[rep_key]["paras"] if looks[p].get("form")} if rep_key else set()  # 대표 서식의 줄이 있는 표 양식 — 그 표는 대표 서식을 쓴다
    out, tol = [], None  # tol = 오차 기준(지침 tolerance — 대표와 다른 갈래가 있을 때만 한 번 읽는다)
    fit = lambda q: tuple(looks[q].get(k) for k in ("ratioPct", "spacingPct", "L.ratioPct", "L.spacingPct"))  # noqa: E731
    for g in groups.values():
        is_rep = g["key"] == rep_key
        # 갈래의 열쇠 줄(key — 그 갈래를 가리키는 줄 · 계획에서 대표로 삼을 줄): 대표 갈래는 **대표 줄 그대로**(같은 갈래의 첫 줄로 바꾸지 않는다 — 사람이 정한 대표), 그 밖은 그 갈래에서
        # 가장 흔한 줄 맞춤 값(장평·자간)을 지닌 첫 줄(자간을 줄여 둔 한 줄이 대표가 되면 새 줄이 그 자간을 물려받는다)
        top = Counter(fit(q) for q in g["paras"]).most_common(1)[0][0]
        key = rep if is_rep else next(q for q in g["paras"] if fit(q) == top)
        lk = looks[key]
        # form = 표 안의 줄이면 그 표 양식{key, label(머리글), tables(표 수), around(주변 글)} | None · own = 「표의 서식」(그 표 양식에 대표 서식의 줄이 없다 — 대표에 맞추지 않는다: ② §8-11)
        form = _form_view(doc, ov, [key] if is_rep else g["paras"]) if lk.get("form") else None
        out.append({"key": key, "count": len(g["paras"]), "paras": g["paras"] if full else g["paras"][:_LIST_MAX], "more": 0 if full else max(0, len(g["paras"]) - _LIST_MAX),
                    "rep": is_rep, "look": {k: cshown(lk, k) for k in lk if k not in _LOOK_ONLY}, "raw": lk,  # raw = 비교 값 원값(화면 「서식 비교」 의 견본 글 — outline_preview.js)
                    "diff": diff(base, lk) if base and not is_rep else [],
                    # near = 대표와 **거의 같은** 갈래(레터가 같고 다른 값이 모두 오차 안 — 서식 라벨의 「≈」 와 같은 판단: labels_now · near). 화면의 「≈ 2번째 줄」 / 「≠ 2번째 줄」(fmt_focus.js fmDiffInfo)
                    "near": bool(base) and not is_rep and near(base, lk, tol := tol or _tolerance()),
                    "form": form, "own": bool(rep) and not is_rep and bool(lk.get("form")) and lk["form"] not in uses_rep})
    out.sort(key=lambda g: (not g["rep"], -g["count"], order.get(g["paras"][0], 1 << 30) if g["paras"] else 0))
    # sig = 이 레벨의 줄 구성 지문(줄 id → 갈래 — 값 칸도 줄로 든다: 서식 비교에서는 빠져도 떼기·번호형 형제 검사에는 든다) · repIds = 대표 줄이 실제로 지닌 모양 참조(맞추면 복사되는 문단·스타일·글자 정의):
    # 서식 정리 계획을 문서 차례가 아니라 **그 템플릿 줄의 지문**에 묶는 데 쓴다(tpl_agent.fingerprint — spec_hwpx_웹편집 ② §8-4 「계획은 줄 지문에」)
    # 표 안의 줄은 표 양식도 든다(② §8-11 「계획 지문」 — 표를 모르고 받은 옛 계획이 그대로 반영되지 않게 · 표 밖의 줄만 있는 레벨의 지문은 전과 같다)
    sig = hashlib.sha1(json.dumps([([p, fkey[p]] + ([looks[p]["form"]] if looks[p].get("form") else [])) if p in looks else [p, "V"] for p in alive],
                                  ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    rep_ids = None
    if rep:
        try:
            sh = rep_shape(doc, ov, rep)
            rep_ids = [sh["attrs"].get("paraPrIDRef"), sh["attrs"].get("styleIDRef"), sh["attrs"].get("charPrIDRef"), sh.get("body"), sh["prefix"]]
        except (KeyError, ValueError):
            rep_ids = None
    return {"tpl": str(tid), "level": int(level), "total": len(looks), "rep": rep, "repMissing": bool(ids) and rep is None, "values": len(alive) - len(ids),
            # others = 「대표에 맞추기」 가 맞출 줄(표의 서식 갈래는 뺀다) · ownLines = 표의 서식 갈래의 줄(대표에 맞추지 않는다 — 떼거나 골라서 맞춘다: ② §8-11)
            "others": sum(g["count"] for g in out if not g["rep"] and not g["own"]) if rep else 0, "ownLines": sum(g["count"] for g in out if g["own"]),
            "groups": out, "sig": sig, "repIds": rep_ids}


def all_variants(doc, ov):
    """모든 슬롯 → {tpl: {레벨: variants}}(줄이 있는 슬롯만)."""
    order = _order(doc)
    out = {}
    for tid, t in ov["templates"].items():
        for lv, sl in t.get("slots", {}).items():
            if slot_ids(ov, tid, lv) and not sl.get("table"):  # 표 제목 레벨(② §8-7)은 서식 갈래·대표·맞추기가 없다
                out.setdefault(tid, {})[lv] = variants(doc, ov, tid, lv, order)
    return out


def label_sync(doc, ov, g):
    """오버레이 줄의 서식 라벨(`fmt` — 여백의 「S41」)을 **지금 서식**에 맞춘다(spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」 — 2026-11-16 사용자 「S41, S42 도 왜 템플릿이 같은데 변환이 안된거야」):
    라벨이 없는 옛 오버레이에는 헤딩 그래프 g 의 라벨을 싣고, 줄의 비교 값이 그 레벨 대표와 같으면 대표의 라벨로 바꾼다(맞춘 줄의 라벨이 추출한 때의 것으로 남던 것).
    오버레이마다 한 번(`ov["fmtv"]`) — 그 뒤로는 맞추기(`match_one`)가 줄마다 바꾼다. -> 맞췄나."""
    if ov.get("fmtv"):
        return False
    by = {}
    for n in (g or {}).get("nodes") or []:
        if n.get("fmt"):
            by.setdefault(n.get("para"), n["fmt"])
    for pid, x in ov["lines"].items():
        if "fmt" not in x:
            x["fmt"] = by.get(pid, "")
    for tid, t in ov["templates"].items():
        for lv, sl in (t.get("slots") or {}).items():
            rep = sl.get("rep")
            want = (ov["lines"].get(rep) or {}).get("fmt") if rep else ""
            if not want or not _alive(doc, rep) or lone_value(doc, ov, rep):
                continue
            try:
                base = look(doc, ov, rep)
            except (KeyError, ValueError):
                continue
            for pid in slot_ids(ov, tid, lv):
                if pid == rep or pid not in ov["lines"] or ov["lines"][pid].get("fmt") == want or not _alive(doc, pid):  # 자동 글머리 줄(② §8-8)은 대표와 서식이 늘 달라 라벨이 그래프 것 그대로
                    continue
                try:
                    if same(look(doc, ov, pid), base):
                        ov["lines"][pid]["fmt"] = want
                except (KeyError, ValueError):
                    continue
    ov["fmtv"] = 1
    return True


OFF = "≠"  # 번호 대신 보이는 표시 — 서식이 대표와 다른데 저장된 라벨로는 구별되지 않는 줄(대표의 라벨이던 줄을 손으로 바꿈 · 라벨이 없는 줄). 저장하지 않는다(보일 때 셈한다)
NEAR = "≈"  # 그런 줄 가운데 **대표와 거의 같은** 줄 — 레터가 같고 다른 값이 모두 오차 안(추출이 대표와 같은 번호로 묶는 줄). 2026-11-16 사용자 "≠ 이거는 유사한 의미가 아니라 ≈ 이걸로 수정해줘야지"
# 오차로 견주는 비교 값 → tolerance 의 문턱 키(여럿이면 합 — 「2번째 줄」 = 왼쪽 여백 + 내어쓰기라 둘의 합) · 같은 군이면 같은 값(글꼴 별칭 · 색 군)
_NEAR_NUM = {"line1Mm": ("indentMm",), "line2Mm": ("indentMm", "firstLineMm"), "indentRightMm": ("indentMm",), "spaceBeforePt": ("spacePt",),
             "spaceAfterPt": ("spacePt",), "lineSpacingPct": ("lineSpacingPct",), "sizePt": ("sizePt",), "L.sizePt": ("sizePt",)}
_NEAR_GROUP = {"font": "fontAliases", "L.font": "fontAliases", "color": "colors", "L.color": "colors"}


def _group(v, groups):
    """값 v 가 든 군(글꼴 별칭군 · 색 군) — 어느 군에도 없으면 값 그대로(대·소문자 무시)."""
    key = str(v).casefold() if v is not None else None
    for i, grp in enumerate(groups or ()):
        if any((str(x).casefold() if x is not None else None) == key for x in grp):
            return ("군", i)
    return key


def near(a, b, tol):
    """비교 값 a(대표)와 b 가 **오차 안**인가(spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」 ⓓ 의 「≈」) — 다른 값마다: 레터 · 정렬 · 굵게 · 기울임 · 밑줄이 다르면 아님 ·
    앞 공백 · 레터 뒤 공백은 빈칸뿐일 때 칸 수 차이 ≤ leadSpaces(보통 빈칸과 묶음 빈칸은 같은 한 칸) · mm·pt·% 는 문턱 이하 · 글꼴 · 색은 같은 군. tol = heading_guides 의 오차 기준.
    자동 글머리(② §8-8)가 다르면 아니다 — 친 레터와 자동 글머리표는 오차가 아니다."""
    if (a.get("auto") or "") != (b.get("auto") or ""):
        return False
    for k in KEYS:
        if cval(a, k) == cval(b, k):
            continue
        x, y = a.get(k), b.get(k)
        if k in ("lead", "gap"):
            x, y = (x or "").replace("\u2002", " "), (y or "").replace("\u2002", " ")
            if x.strip(" ") or y.strip(" ") or abs(len(x) - len(y)) > float(tol.get("leadSpaces") or 0):
                return False
        elif k in _NEAR_NUM:
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
                return False
            if abs(x - y) > sum(float(tol.get(t) or 0) for t in _NEAR_NUM[k]) + 1e-9:
                return False
        elif k in _NEAR_GROUP:
            if _group(x, tol.get(_NEAR_GROUP[k])) != _group(y, tol.get(_NEAR_GROUP[k])):
                return False
        else:
            return False
    return True


def _tolerance():
    """지금 오차 기준(지침 tolerance) — 못 읽으면 기본값(라벨 하나 때문에 화면이 멈추지 않게)."""
    from app import heading_guides as G  # 라벨을 셈할 때만 읽는다
    try:
        return G.tolerance()
    except (ValueError, OSError):
        return dict(G.TOLERANCE_DEFAULT)


def labels_now(doc, ov, ids=None):
    """줄마다 **지금 보일** 서식 라벨 {문단 id: 라벨}(spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」) — 저장된 라벨(`lines[].fmt`: 추출한 때의 것 · 맞추면 대표의 것)을 그대로 믿지 않고
    **지금 비교 값을 레벨 대표와 견줘** 정한다(2026-11-16 astra: 손으로 서식을 바꾸는 길이 여럿이라 편집마다 라벨을 고치는 것보다 보일 때 셈하는 쪽이 빠짐이 없다):
    대표와 비교 값이 같은 줄 = 대표의 라벨(화면은 대표의 라벨과 같으면 번호를 안 그린다) · 다른 줄 = 제 라벨, 제 라벨이 대표의 것과 같거나 없으면
    오차 안이면 NEAR(「≈」 — 대표와 거의 같음: `near`), 레터가 다르거나 오차 밖이면 OFF(「≠」).
    대표가 없거나 대표의 라벨이 없는 레벨은 저장된 라벨 그대로. ids 를 주면 그 줄이 든 레벨의 줄만(대표 줄이 바뀌면 그 레벨 전부가 달라지므로 레벨 단위)."""
    lines, out, slots, tol = ov["lines"], {}, {}, None
    for pid, x in lines.items():
        slots.setdefault((x["tpl"], str(x["level"])), []).append(pid)
    want_ids = None if ids is None else set(ids)
    for (tid, lv), pids in slots.items():
        if want_ids is not None and not want_ids & set(pids):
            continue
        rep = (OE._slot(ov, tid, lv) or {}).get("rep")
        want = ((lines.get(rep) or {}).get("fmt") or "") if rep else ""
        base = None
        if want and _alive(doc, rep) and not lone_value(doc, ov, rep):
            try:
                base = look(doc, ov, rep)
            except (KeyError, ValueError):
                base = None
        for pid in pids:
            own = lines[pid].get("fmt") or ""
            lab = own
            if base is not None and pid != rep and _alive(doc, pid) and not lone_value(doc, ov, pid):
                try:
                    lk = look(doc, ov, pid)
                    if same(lk, base):
                        lab = want
                    elif not own or own == want:  # 번호로는 대표와 구별되지 않는다 — 거의 같은가(≈), 다른가(≠)
                        tol = tol or _tolerance()
                        lab = NEAR if near(base, lk, tol) else OFF
                except (KeyError, ValueError):
                    lab = own
            if lab:
                out[pid] = lab
    return out


# ---------------------------------------------------------------- 대표 정하기 · 맞추기
VALUE_REP = "이 레벨의 대표가 값 칸(표 칸에 혼자 있는 레터)입니다 — 글이 있는 줄을 대표로 정한 뒤 맞추세요"


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
            "first": ov["lines"][pid].get("first"),  # 대표 줄의 「저절로 맞춘 첫 줄 값」 기억(spec_hwpx_웹편집 ② §8-1) — 맞춘 줄도 같은 기억을 갖는다
            "fmt": ov["lines"][pid].get("fmt") or ""}  # 대표 줄의 서식 라벨 — 맞춘 줄의 라벨도 이것이 된다(여백의 「S41」 이 추출한 때의 것으로 남던 것)


def rep_origin(sl):
    """슬롯 대표의 출처 — "user"(사람이 정함: repSet — 서식 정리 계획이 못 바꾼다) · "agent"(서식 정리 계획이 정함: agentRep = 그 줄 id — 잠기지 않아 다음 계획이 바꿀 수 있다) ·
    None(헤딩 그래프가 뽑았거나 저절로 다시 뽑힘). agentRep 은 **그 줄이 지금도 대표일 때만** 뜻이 있다 — 떼기·종속이 대표를 다른 줄로 다시 뽑으면 저절로 출처가 없어진다(지울 곳이 따로 없다)."""
    if not sl or not sl.get("rep"):
        return None
    if sl.get("repSet"):
        return "user"
    return "agent" if sl.get("agentRep") == sl["rep"] else None


def set_rep(doc, ov, tid, level, pid, by=None):
    """슬롯의 대표를 pid 로 — rep · 동결 접두(prefix·letter) · 모양 참조(attrs)를 그 문단의 지금 것으로. 문서는 안 바꾼다. -> 슬롯.
    by = 누가 정했나: None = 사람(대표 정하기 · 대표 미리보기의 묶음 맞추기 — repSet: 잠긴다) · "agent" = 서식 정리 계획의 반영(agentRep: 잠기지 않는다 — 전에는 이것도 repSet 을 켜서
    다음 계획이 「사람이 정한 대표」 로 보고 못 바꿨다: 2026-11-17 astra). 출처는 rep_origin 으로 읽는다."""
    sl = OE._slot(ov, tid, level)
    if sl is None:
        raise KeyError("그런 템플릿 레벨이 없습니다")
    if not _alive(doc, pid):
        raise ValueError("그 문단이 지금 문서에 없습니다")
    _check_member(ov, tid, level, pid)
    if lone_value(doc, ov, pid):
        raise ValueError("값 칸(표 칸에 혼자 있는 레터)은 대표가 될 수 없습니다 — 글이 있는 줄을 대표로 정하세요")
    if _is_auto(ov, pid):
        raise ValueError(AUTO_REP)
    sh = rep_shape(doc, ov, pid)
    sl.update(rep=pid, prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])
    if by == "agent":
        sl["agentRep"] = pid
        sl.pop("repSet", None)
    else:
        sl["repSet"] = True
        sl.pop("agentRep", None)
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
    if lone_value(doc, ov, rep):  # 옛 그래프에서 값 칸이 대표로 잡힌 레벨 — 그 모양(가운데 「-」)으로 글 줄을 맞추지 않는다
        raise ValueError(VALUE_REP)
    base = look(doc, ov, rep)
    if like is not None:
        if not _alive(doc, like):
            raise ValueError("그 서식의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
        _check_member(ov, tid, level, like)
    kind = look(doc, ov, like) if like is not None else None
    order = _order(doc)
    want = set(paras) if paras else None
    auto_numbers(doc, ov, tid, level)  # 자동 번호 줄의 레터를 지금 번호로 — 맞추기 전에 한 번(② §8-8 「자동 글머리 줄」)
    rows = []
    for pid in sorted(slot_ids(ov, tid, level), key=lambda p: order.get(p, 1 << 30)):
        if pid == rep or not _alive(doc, pid) or lone_value(doc, ov, pid):  # 값 칸은 맞추지 않는다
            continue
        try:
            rows.append((pid, look(doc, ov, pid)))
        except (KeyError, ValueError):
            continue
    # 갈래도 줄도 고르지 않은 맞추기(「대표에 맞추기」)는 **표의 서식** 갈래를 건드리지 않는다(② §8-11 — 그 표 양식에 대표 서식의 줄이 없다). 골라서(paras · like) 맞추는 것은 된다
    forms = rep_forms([base] + [lk for _, lk in rows], base) if want is None and kind is None else None
    return [pid for pid, lk in rows if (want is None or pid in want) and not same(lk, base) and (kind is None or mate(lk, kind, base))
            and not (forms is not None and is_own(lk, base, forms))]


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
    if lone_value(doc, ov, rep):
        raise ValueError(f"L{level} — {VALUE_REP}")
    base = look(doc, ov, rep)
    kinds = None
    if likes is not None:
        kinds = []
        for q in likes:
            if not _alive(doc, q):
                raise ValueError("그 서식의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
            _check_member(ov, tid, level, q)
            kinds.append(look(doc, ov, q))
    order = _order(doc)
    auto_numbers(doc, ov, tid, level)  # 자동 번호 줄의 레터를 지금 번호로 — 맞추기 전에 한 번(② §8-8 「자동 글머리 줄」)
    rows = []
    for pid in sorted(slot_ids(ov, tid, level), key=lambda p: order.get(p, 1 << 30)):
        if pid == rep or not _alive(doc, pid) or lone_value(doc, ov, pid):  # 값 칸은 맞추지 않는다(옛 계획이 그 갈래를 가리켜도)
            continue
        try:
            rows.append((pid, look(doc, ov, pid)))
        except (KeyError, ValueError):
            continue
    # likes 가 없는 「모두」 는 표의 서식 갈래를 건드리지 않는다 · likes 는 그 줄의 갈래만(서식 + 표 양식 — ② §8-11)
    forms = rep_forms([base] + [lk for _, lk in rows], base) if kinds is None else None
    return rep, [pid for pid, lk in rows if not same(lk, base) and (kinds is None or any(mate(lk, k, base) for k in kinds))
                 and not (forms is not None and is_own(lk, base, forms))]


def match_one(doc, ov, pid, sh, left=None):
    """줄 pid 를 대표 모양 sh(rep_shape)로 — 접두 · 문단 모양·스타일 · 레터 런 · 옛 본문 바탕 글자 모양을 쓰던 런. -> 바뀐 줄의 새 레터(모양만 맞춘 줄은 옛 레터).
    **짝 표지가 든 줄**(형광펜 · 필드 · 변경 추적 — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」): 제 표지가 없으면 전처럼 접두를 다시 쓴다(replace_prefix).
    있으면 레터가 그대로일 때 레터 앞·뒤 빈칸만 제자리에서 바꾸고(prefix_keep_marks — 완전히 맞춤), 레터를 바꿔야 하거나 표지 때문에 못 바꾸면(MarkBlock)
    **모양만**(prefix_shape_only — 글 · 오버레이의 letter · fmt 는 그대로) 맞추고 left 에 {"id", "why"("letter" | MarkBlock.why), "kinds"} 를 더한다 — 표지 때문에는 예외를 내지 않는다.
    **자동 글머리 줄**(ov["autos"] — ② §8-8 「자동 글머리 줄」): 대표의 접두(레터 앞 빈칸 · 레터 · 레터 뒤 빈칸)를 글 앞에 넣고(글 앞의 빈칸은 레터 뒤 빈칸이라 덮는다) 문단 모양을 대표 것으로 —
    대표의 문단 모양에는 글머리표·문단 번호가 없어 **친 레터**가 된다 — 레터는 **보이던 그대로**(숫자 · 영문 · 글자 — 번호는 맞추기 전에 센 것: auto_numbers ·
    그 레벨과 같은 레터가 생기는 줄만 오버레이에 든다). 맞춘 줄은 ov["lines"] 로 옮긴다(outline_edit.promote).
    표지가 든 줄은 새 접두를 표지 밖에 넣고(prefix_keep_marks), 못 넣으면 **문서를 안 바꾸고** left 에 싣는다(모양만 맞추면 글머리표가 꺼져 레터가 없어진다)."""
    auto = _is_auto(ov, pid)
    x = _line_of(ov, pid)
    p = doc._ids[pid]
    lead, tok, gap, plen, text = parts(doc, ov, pid)
    if not tok and not auto:
        raise ValueError(f"{pid} 의 첫머리에 레터가 없습니다")
    own = tok or (x.get("letter") or "" if auto else "")  # 자동 글머리 줄의 지금 레터 = 라벨(번호형은 그 번호)
    if auto:
        new_tok = own  # 자동 글머리 줄 — 보이던 레터 그대로(숫자 · 영문 · 글자: 그 레벨과 같은 레터가 생기는 줄만 든다 — outline_edit.build_overlay)
    elif x.get("role") in OE.ROOTED:
        new_tok = tok  # 괄호 줄 — 글 전체가 레터(구분 값)라 글은 그대로
    elif OE.is_numbered(x.get("key") or "") or (OE.numbers_of(own) and OE.numbers_of(sh["tok"])):
        # 대표 꼴에 제 번호 — 키가 번호형이 아니어도(그래프가 「(1-1)」 · 「(2-1)」 을 글자 그대로의 키로 둔 줄) 두 레터에 다 번호가 있으면 제 번호를 지킨다
        # (2026-11-22: 이관의 「다시 문서 검토(LLM)」 뒤 조정이 연차보고서의 「(2-1) 연구재료제작비」 · 「(3-1) 연구활동비」 를 대표의 「(1-1)」 로 바꿨다)
        new_tok = OE.with_numbers(sh["tok"], OE.numbers_of(own)) or own
    else:
        new_tok = sh["tok"]
    new_prefix = sh["lead"] + new_tok + sh["gap"]
    # 옛 본문 바탕 글자 모양(접두 뒤 첫 글자의 런)을 쓰던 런의 자리(본문 시작에서 잰 것) — 접두를 바꾸면 런이 합쳐지고 갈라져 요소로는 못 좇는다
    old_body = _cid_at(doc, p, plen) if plen < len(text) else None
    old_letter = _cid_at(doc, p, len(lead)) or doc._char_id(p)
    # 본문 바탕 = 옛 본문 바탕 글자 모양과 **장평·자간만 다른** 런도(줄 정리가 문단의 한 줄에만 자간을 걸면 같은 바탕의 본문이 글자 모양 id 가 다른 런 둘이 된다 — id 로만 고르면 뒤쪽 런이 옛 크기 · 글꼴로 남았다:
    # 2026-11-23 astra 재현 · newfilemanager-8c). 런마다의 장평·자간은 아래 fits · refit 이 다시 얹는다
    body_spans, bares = [], {}
    bare = lambda c: bares[c] if c in bares else bares.setdefault(c, _bare(doc, c))  # noqa: E731 — 글자 모양마다 한 번
    for a, b, r in _runs_pos(doc, p) if old_body else ():
        if b > max(a, plen) and not any(o.tag in OBJECTS for o in r) and (r.get("charPrIDRef") == old_body or (bare(old_body) is not None and bare(r.get("charPrIDRef")) == bare(old_body))):
            body_spans.append((max(a, plen) - plen, b - plen))
    # 줄 맞춤 값(장평·자간)은 이 줄 **본문**의 것을 지킨다(자간을 줄여 한 줄에 넣은 줄이 대표의 0% 가 되면 넘친다) — 바꾸기 전에 글 자리마다(본문 시작에서 잰 자리) 그 런의 글자 모양을 적어 두고,
    # 접두·본문 바탕을 다 바꾼 뒤 그 자리의 런에 그 장평·자간을 다시 얹는다(런마다 값이 달라도 · 접두 교체가 다른 런의 글자 모양을 바꿔도 제 값으로)
    fits = [(max(a, plen) - plen, b - plen, r.get("charPrIDRef")) for a, b, r in _runs_pos(doc, p) if b > max(a, plen) and not any(o.tag in OBJECTS for o in r)]
    # **접두(레터 앞 빈칸 · 레터 · 레터 뒤 빈칸)는 대표의 레터 런 그대로** — 그 줄 레터의 장평·자간을 얹지 않는다(② §8-2 「줄 맞춤 값 — 접두는 대표 것」 · 2026-11-23 사용자 「레터 앞 너비가 왜 조금씩 다르냐」:
    # 레터부터 자간을 줄여 둔 줄을 맞추면 그 자간이 레터 앞 빈칸 전체로 번져, 빈칸이 좁아진 만큼 레터가 왼쪽에 섰다 — 한글 출력). 괄호 줄은 글 전체가 레터라 전처럼 제 값
    attrs = {**sh["attrs"], "charPrIDRef": keep_fit(doc, sh["attrs"]["charPrIDRef"], old_letter)} if x.get("role") in OE.ROOTED else dict(sh["attrs"])
    why = None  # 모양만 맞춘 까닭(완전히 맞추면 None)
    if not doc.own_marks(p):
        doc.replace_prefix(pid, plen, new_prefix, attrs=attrs)
        n0 = len(new_prefix)
    elif auto:  # 자동 글머리 줄 + 제 표지 — 글 앞의 빈칸 자리에 접두 전체를 넣는다(새 글은 형광펜 밖)
        try:
            n0 = doc.prefix_keep_marks(pid, lead, "", "", new_prefix, "", attrs=attrs)["offset"]
        except MarkBlock as e:  # 문서는 그대로(모양만 맞추면 글머리표가 꺼져 레터가 없어진다) — 자동 글머리 줄로 남는다
            if left is not None:
                left.append({"id": pid, "why": e.why, "kinds": doc.mark_names(p)})
            return own
    else:
        if new_tok == tok:
            try:
                n0 = doc.prefix_keep_marks(pid, lead, tok, gap, sh["lead"], sh["gap"], attrs=attrs)["offset"]
            except MarkBlock as e:  # 문서는 그대로 — 아래 모양만
                why = e.why
        else:
            why = "letter"  # 레터 글자를 바꾸면 그 자리의 표지가 갈라질 수 있다
        if why is not None:
            n0 = doc.prefix_shape_only(pid, plen, attrs)["offset"]  # 실제로 남은 접두 길이 — 본문 바탕 · 줄 맞춤 자리는 이것으로 잰다
            if left is not None:
                left.append({"id": pid, "why": why, "kinds": doc.mark_names(p)})
    body = sh.get("body") or sh["attrs"]["charPrIDRef"]
    # 그 자리가 **실제로 받을** 글자 모양(본문 바탕 자리 = 대표의 본문 바탕 · 그 밖 = 지금 그 자리의 런)의 줄 맞춤 값이 옛 값과 다른 자리만(없으면 런을 가르지 않는다).
    # 전에는 「대표의 레터 런 · 본문 바탕 가운데 하나와 같으면 그대로」 로 걸러, 본문 자간 0% 인 줄이 대표의 본문 자간(−8%)을 받았다(대표의 레터 런이 0% 라 걸러짐 — 2026-11-23 astra 재현)
    now = [(a, b, r.get("charPrIDRef")) for a, b, r in _runs_pos(doc, p) if b > a] if fits else []   # 접두를 바꾼 뒤의 런 자리 — 한 번만 읽는다(런이 많은 줄에서 자리마다 다시 훑지 않게)
    starts = [a for a, _, _ in now]

    def at(i):   # 글 자리 i 의 글자 모양 id(지금) — 런 자리는 차례대로라 이분 탐색
        from bisect import bisect_right
        k = bisect_right(starts, i) - 1
        return now[k][2] if k >= 0 and i < now[k][1] else None
    refit =[f for f in fits if _fit_of(doc, f[2]) != _fit_of(doc, body if any(s <= f[0] and f[1] <= e for s, e in body_spans) else at(n0 + f[0]))]
    if body_spans or refit:
        for a, b in body_spans + [(a, b) for a, b, _ in refit]:
            doc._boundary(p, n0 + a)
            doc._boundary(p, n0 + b)
        for a, b, r in _runs_pos(doc, p):
            if b <= a or any(o.tag in OBJECTS for o in r):
                continue
            if any(n0 + s <= a and b <= n0 + e for s, e in body_spans):
                r.set("charPrIDRef", body)
            old = next((o for s, e, o in refit if n0 + s <= a and b <= n0 + e), None)
            if old is not None:
                r.set("charPrIDRef", keep_fit(doc, r.get("charPrIDRef"), old))
        doc._tidy(p)
        doc._drop_cache(p)
        doc._touch(p)
    if auto:  # 친 레터가 됐다 — 보통 개요 줄로(ov["autos"] → ov["lines"])
        x = OE.promote(ov, pid, new_tok)
    if why is None:  # 완전히 맞춘 줄만 — 모양만 맞춘 줄은 레터 · 서식 라벨이 그대로다(글이 그대로)
        x["letter"] = new_tok
        if sh.get("fmt"):
            x["fmt"] = sh["fmt"]  # 서식이 대표 것이 됐다 — 서식 라벨도
    if sh.get("first") is not None:  # 문단 모양을 대표 것으로 바꿨으니 저절로 맞춘 값의 기억도 대표 것 — 다르면 뒤의 글 고침이 사람이 정한 값으로 보고 안 맞춘다
        x["first"] = sh["first"]
    else:
        x.pop("first", None)
    return new_tok if why is None else tok


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
    for pid, x in ov["lines"].items():
        el = doc._ids.get(pid)
        if el is None or not doc._attached(el) or x.get("role") == OE.TABLE:  # 표 제목 줄(② §8-7)은 칸 안 문단이 열쇠지만 본문 줄이다
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


def _members(ov, tid, roots, stop=()):
    """roots(B 첫 레벨 줄) 와 그 아래 B 줄(부모 사슬이 B 줄로만 roots 에 닿는 것). stop 의 줄은 넣지 않고 그 아래로도 내려가지 않는다
    (넣은 뒤 정리가 떼는 서식 종속 템플릿 — 넣은 줄 아래에 매달린 목적 문서의 줄은 남는다: spec_병합 ② §5-9)."""
    tid = str(tid)
    stop = set(stop or ())
    got = set(roots)
    changed = True
    while changed:
        changed = False
        for pid, x in ov["lines"].items():
            if pid not in got and pid not in stop and x["tpl"] == tid and x.get("parent") in got:
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
    for T in (A, B):  # 띠 표 템플릿(「별첨N」 — spec_헤딩_추출 ② §6 「띠 표 줄」): 늘 문서 맨 위의 제 템플릿이고 그 아래 줄도 제 템플릿 그대로다
        if T.get("kind") == OE.BAND:
            raise ValueError(f"T{T['no']} 는 별첨·부록 표 제목 템플릿이라 종속 템플릿을 만들 수 없습니다 — 그 줄은 문서 맨 위의 줄이고 그 아래 줄은 제 템플릿 그대로입니다")
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
    # 사람이 푼 종속은 다시 제안하지 않는다(merge_hints) — 앵커로 적어 헤딩 그래프를 다시 지어도 이어진다(carry)
    ov.setdefault("unmerged", []).append({"child": B.get("anchor"), "parent": A.get("anchor"), "at": int(rec.get("at") or 0)})
    return back


def carry(old, new, ctx=None, doc=None):
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 옛 오버레이의 종속(같은 앵커끼리 · 넣은 차례대로 — 겹친 종속도)을 다시 건다(ctx = context — 칸 안 매달림).
    사람이 정한 대표도 옮긴다. -> 못 건 것 [(기록, 까닭)].
    doc = 지금 문서(자리로 나눈 기록 — ② §8-13 — 의 번호 묶음을 같은 표의 형제끼리 보게: 없으면 칸 흐름으로). 못 건 **자리로 나눈 기록**은 새 오버레이의 `lost` 에 까닭과 함께 남아
    다음에 다시 분석할 때 제 차례에 다시 건다(사람의 나누기가 한 번 못 걸렸다고 사라지지 않게 — 합치면 지워진다)."""
    fails = []
    if not old or not new:
        return fails
    if old.get("unmerged"):
        new["unmerged"] = [dict(x) for x in old["unmerged"]]  # 사람이 푼 종속(다시 제안하지 않을 것 — 앵커 · 레벨)
    ops = [("merge", m) for m in old.get("merges") or []] + [("split", m) for m in (old.get("splits") or []) + (old.get("lost") or [])]
    ops.sort(key=lambda o: o[1].get("n") or 0)  # 넣은 차례대로(차례 번호가 없는 옛 종속 기록이 먼저 — 안정 정렬이라 그 안의 차례는 그대로)
    for kind, m in ops:
        by_anchor = {t.get("anchor"): tid for tid, t in new.get("templates", {}).items()}  # 앞의 종속·떼기가 만든 템플릿도 앵커로 찾게 매번
        if kind == "split":  # 서식 종속 템플릿(② §8-5) — 기록의 줄 가운데 지금도 (A, Lk) 줄인 것만, 슬롯은 옛 것
            why = _carry_split(old, new, m, by_anchor.get(m.get("of")), doc=doc)
            if why:
                fails.append((m, why))
                if m.get("cut") or m.get("add"):
                    new.setdefault("lost", []).append({**{k: v for k, v in m.items() if k != "why"}, "n": _seq(new), "why": why})
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
    for t in old.get("templates", {}).values():  # 정해 둔 대표(사람이 정함 repSet · 서식 정리 계획이 정함 agentRep) — 그 문단이 새 오버레이에서도 같은 앵커·레벨 줄이면 그대로, 출처도 같이(사람 것만 잠긴다)
        tid = by_anchor.get(t.get("anchor"))
        for lv, sl in t.get("slots", {}).items():
            dz = sl.get(RETIDY_DEEP) if tid is not None else None
            if dz:  # 넣은 뒤 정리의 표(넣은 줄끼리 맞춘 레벨) — 지금도 그 템플릿 · 레벨 줄인 것만
                here = [p for p in dz.get("lines") or () if (new["lines"].get(p) or {}).get("tpl") == tid and str(new["lines"][p]["level"]) == str(lv)]
                nsl = OE._slot(new, tid, lv)
                if nsl is not None and here:
                    nsl[RETIDY_DEEP] = {"rep": dz.get("rep") if dz.get("rep") in here else None, "lines": here}
            who = rep_origin(sl)
            if not who or tid is None:
                continue
            x = new["lines"].get(sl.get("rep"))
            nsl = OE._slot(new, tid, lv)
            if nsl is not None and x is not None and x["tpl"] == tid and str(x["level"]) == str(lv):
                nsl.update({k: sl.get(k) for k in ("rep", "prefix", "letter", "attrs", "bodyChar")})
                nsl.pop("repSet", None)
                nsl.pop("agentRep", None)
                nsl.update({"repSet": True} if who == "user" else {"agentRep": sl["rep"]})
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


def merge_hints(ov):
    """종속 제안(spec_hwpx_웹편집 ② §8-2 「종속 제안」 — 2026-11-16 사용자 「템플릿이 상위레벨 별로 다를 수 있고 같을 수도 있고 종속된 형태로 될 수도」 · 「템플릿 사이 관계 … 다 해줘」):
    가지 템플릿 B 의 첫 레벨 줄이 **모두 한 자리 (A, Lk) 의 줄 아래에만** 매달려 있으면 「B 를 A 의 Lk 아래 종속 템플릿(T{A}T{B})으로」 를 **제안**한다 — 저절로 걸지 않는다(사람이 「하위로 넣기」 를 눌러야:
    한 자리에만 온다는 것은 관측일 뿐이고, 떼고 묶은 결과가 아직 다른 화면에 닿지 않는다 — astra).
    여러 자리에 매달린 B(여러 상위 레벨이 같이 쓰는 템플릿 = 같음) · 자리마다 다른 템플릿(다름)은 그대로 둔다. 제안하지 않는 것: 가지(branch)가 아닌 템플릿(주 사슬 · 구분 라벨 · 표 칸) ·
    이미 종속/서식 종속인 것 · 표 칸이나 다른 그릇에 줄이 있는 것 · 본문 최상위에 놓인 줄이 있는 것 · B 의 첫 레터가 A 의 그 자리보다 깊은 레벨 레터와 같은 것(그 레벨의 줄로 볼 것 —
    다음 레벨만이 아니라 건너뛴 레벨도: 2026-11-17 「잇닿은 사슬」 · spec_헤딩_추출 ② §6 — 다시 세지 않은 옛 그래프의 「1-1.」 아래 「o › -」 를 「T1T8」 로 넣지 않는다) ·
    사람이 넣었다가 푼 쌍(`unmerged`). -> [{child, childNo, parent, parentNo, at, places(매달린 곳 수), lines(B 의 줄 수), chain}] — 한 건을 넣으면 다시 셈한다(B → A · C → B 처럼 이어진 것)."""
    tp, lines, out = ov.get("templates") or {}, ov.get("lines") or {}, []
    undone = {(m.get("child"), m.get("parent"), int(m.get("at") or 0)) for m in ov.get("unmerged") or []}
    count = {}
    for x in lines.values():
        count[x["tpl"]] = count.get(x["tpl"], 0) + 1
    for tid, B in tp.items():
        if B.get("kind") != "branch" or B.get("composite") or B.get("variant") or _base(B):
            continue
        firsts = [x for x in lines.values() if x["tpl"] == tid and int(x["level"]) == 1]
        if not firsts or any((x.get("flow") or "body") != "body" for x in firsts):
            continue
        spots = set()
        for x in firsts:
            par = lines.get(x.get("parent")) if x.get("parent") else None
            spots.add((par["tpl"], int(par["level"])) if par else None)
        if len(spots) != 1 or None in spots:
            continue
        (ptid, at), = spots
        A = tp.get(ptid)
        if A is None or ptid == tid or A.get("variant") or A.get("kind") == "cell" or comp_id(ptid, tid) in tp:
            continue
        if A.get("kind") == OE.BAND:  # 띠 표 템플릿(「별첨N」 — spec_헤딩_추출 ② §6 「띠 표 줄」) 아래의 줄은 제 템플릿 그대로다(사용자 답 「제 템플릿으로」 — 별첨 아래 「□」 = T2 L1): 종속으로 제안하지 않는다
            continue
        achain, bchain = list(A.get("chain") or []), list(B.get("chain") or [])
        if bchain and bchain[0] in achain[at:]:  # A 의 그 자리보다 깊은 레벨 레터 — 종속이 아니라 A 의 그 레벨 줄(잇닿은 사슬)
            continue
        if (B.get("anchor"), A.get("anchor"), at) in undone:
            continue
        # sure = **확실한 것** — 「모두 반영」·「전체 실행」 이 저절로 건다(2026-11-16 사용자 「확실이 구분되는건 자동으로 하고 애매한것만 제안 … 다시 되돌리면 되는 거잖아」).
        # 애매한 것(제안만): **번호가 자리를 넘어 이어지는** 번호형 가지 — 윗줄마다 「가.」 부터 다시 시작하지 않고 앞 자리의 번호를 잇는 곳이 있다(그 가지가 윗줄에 딸린 것인지 문서 전체를 꿰는 번호인지 사람이 본다).
        # 윗줄마다 1번(「가.」·「1)」·「①」)부터 시작하는 번호형 가지와 기호 가지는 확실하다. 그 밖의 조건(한 자리 · 본문 · 가지 · 다음 레터와 다름 · 사람이 푼 적 없음)은 위에서 이미 걸렀다
        runs_on = False
        if bchain and OE.is_numbered(bchain[0]):
            low = {}
            for x in firsts:
                nums = OE.numbers_of(x.get("letter") or "")
                if nums:
                    low[x.get("parent")] = min(low.get(x.get("parent"), nums[-1]), nums[-1])
            runs_on = not low or any(v != 1 for v in low.values())
        out.append({"child": tid, "childNo": B.get("no"), "parent": ptid, "parentNo": A.get("no"), "at": at, "places": len(firsts), "lines": count.get(tid, 0), "chain": bchain,
                    "sure": bool(bchain) and not runs_on, "why": "번호가 윗줄을 넘어 이어지는 곳이 있습니다" if runs_on else ""})
    out.sort(key=lambda h: (str(h["parentNo"]), h["at"], str(h["childNo"])))
    return out


def auto_merge(ov, limit=60):
    """확실한 종속 제안(merge_hints 의 sure)을 건다 — **한 건 넣을 때마다 다시 셈한다**(B 를 A 아래로 넣으면 B 아래에 매달렸던 C 의 자리가 바뀐다). 오버레이만 바꾼다(문서는 그대로).
    부르는 쪽이 트랜잭션 안에서(실행 취소 1) — 「모두 반영」 이 서식 계획을 반영한 **뒤에** 같은 트랜잭션으로 부른다(줄을 제 템플릿의 대표에 맞춘 다음 옮긴다 — 받아 둔 계획이 헛되지 않게).
    -> 넣은 것 [{id, no, child, childNo, parent, parentNo, at, moved(옮긴 줄 수), ids(옮긴 줄)}]. 못 넣는 쌍(merge 가 거절)은 건너뛴다."""
    done, skip = [], set()
    for _ in range(limit):
        h = next((x for x in merge_hints(ov) if x["sure"] and (x["child"], x["parent"], x["at"]) not in skip), None)
        if h is None:
            break
        try:
            rec = merge(ov, h["child"], h["parent"], h["at"])
        except (KeyError, ValueError):
            skip.add((h["child"], h["parent"], h["at"]))
            continue
        ids = list(rec.get("moved") or [])
        cid = rec.get("id") or comp_id(h["parent"], h["child"])
        done.append({"id": cid, "no": (ov["templates"].get(cid) or {}).get("no"), "child": h["child"], "childNo": h["childNo"], "parent": h["parent"], "parentNo": h["parentNo"],
                     "at": h["at"], "moved": len(ids), "ids": ids})
    return done


# ---------------------------------------------------------------- 서식 종속 템플릿 — 서식 갈래를 다른 템플릿으로(spec_hwpx_웹편집 ② §8-5)
SFX = "abcdefghijklmnopqrstuvwxyz"  # 같은 (A, Lk) 에서 뗀 차례 — 「T1L3a」·「T1L3b」…
RETIDY_DEEP = "retidyDeep"  # 슬롯의 표 — 넣은 뒤 정리(merge_retidy.mark)가 넣은 줄끼리 맞추기로 정한 레벨 {rep(넣은 줄의 대표 — 레벨의 대표 rep 이 아니다), lines[그때의 넣은 줄]}: carry 가 옮기고 split 은 안 옮긴다


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
        raise ValueError("뗄 서식의 줄(likes)이 필요합니다")
    kinds = []
    for q in likes:
        if not _alive(doc, q):
            raise ValueError("그 서식의 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
        _check_member(ov, tid, level, q)
        kinds.append(look(doc, ov, q))
    order = _order(doc)
    rep = (OE._slot(ov, tid, level) or {}).get("rep")
    base = look(doc, ov, rep) if rep and _alive(doc, rep) and rep in ov["lines"] else None  # 갈래 = 서식 + (대표와 다른 서식이면) 표 양식 — ② §8-11
    out = []
    for pid in sorted(slot_ids(ov, tid, level), key=lambda p: order.get(p, 1 << 30)):
        if not _alive(doc, pid) or lone_value(doc, ov, pid):  # 값 칸은 떼지 않는다(갈래에 없다)
            continue
        try:
            lk = look(doc, ov, pid)
        except (KeyError, ValueError):
            continue
        if any(mate(lk, k, base) for k in kinds):
            out.append(pid)
    return out


def split_units(ov, tid, level, doc=None):
    """번호형 레벨 (tid, level) 의 **함께 옮겨야 하는 형제 묶음** {줄 id: 묶음 열쇠} | None(번호형이 아님 — 묶음 제약 없음).
    묶음 = 같은 부모 아래 형제 — 표 안의 줄은 **같은 표**의 형제끼리(② §8-11 「번호형 레벨의 떼기」: 번호 묶음은 표를 넘지 않는다). doc 이 없으면(2단계를 다시 돌린 뒤 떼기를 다시 걸 때 —
    carry) 표 대신 그 줄의 흐름(칸)으로 가른다 — 전에 문서로 검사해 건 떼기를 다시 거는 길이다."""
    sl = OE._slot(ov, tid, level)
    if sl is None or not OE.is_numbered(sl.get("key") or ""):
        return None
    out = {}
    for pid in slot_ids(ov, tid, level):
        x = _line_of(ov, pid)  # 자동 글머리 줄도(② §8-8 — 번호 묶음의 형제로 센다)
        if doc is not None:
            el = doc._ids.get(pid)
            tbl = table_of(el) if el is not None else None
            where = id(tbl) if tbl is not None else None
        else:
            where = x.get("flow") if str(x.get("flow") or "").startswith("cell") else None
        out[pid] = (x.get("parent"), where)
    return out


def split_block(ov, tid, level, paras, rep=None, doc=None, partial=True, whole=False):
    """(tid, level) 줄 paras 를 서식 종속 템플릿으로 못 떼는 까닭 | None — 종속 템플릿의 부모 레벨 · 대표 갈래 · 번호형 레벨에서 같은 부모 아래 형제의 일부
    (번호 다시 매김이 (부모, 템플릿, 레벨) 묶음마다라 「1. 3.」 이 된다 — 표 안의 줄은 같은 표의 형제끼리가 한 묶음: split_units). rep = 그 레벨의 대표로 볼 줄(같은 트랜잭션에서 대표를 바꾼 뒤 뗄 때 — 없으면 슬롯의 지금 대표).
    whole = 자리로 나누기(② §8-13 `cut` — 서식과 무관하게 그 줄 · 그 레벨 전체를 옮긴다): 「대표 줄」 검사만 건너뛴다(다른 검사는 그대로)."""
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
    if any(_is_auto(ov, p) for p in want):  # 자동 글머리 줄(② §8-8)은 떼지 않는다 — 맞추면 친 레터가 된다(그 뒤에 뗄 수 있다)
        return AUTO_SPLIT
    if not whole and (rep or sl.get("rep")) in want:
        return f"T{t['no']} L{level} 의 대표 서식은 뗄 수 없습니다 — 다른 줄을 대표로 정한 뒤 떼세요"
    units = split_units(ov, tid, level, doc) if partial else None  # partial=False — 「형제의 일부」 는 안 본다(계획 검사가 한 split 항목의 줄을 합쳐서 본다: tpl_agent.check_plan)
    if units is not None:
        by_parent = {}
        for pid, u in units.items():
            by_parent.setdefault(u, []).append(pid)
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


def split(ov, tid, level, paras, rep=None, shape=None, into=None, sfx=None, slots=None, doc=None, stop=None, by=None, side=None, cut=None):
    """템플릿 tid(A) 의 L level 줄 paras(일부러 다르게 준 서식의 갈래)를 **서식 종속 템플릿**(표기 「T{A}L{k}{a…}」 · id 「A~k글자」)으로 뗀다
    (2026-11-15 사용자 "서식이 다르면 템플릿도 다른거잖아 … T1L3 로 하고 a,b,c 를 붙이자 … 종속템플릿이기 때문에 이 템플릿의 시작은 L3 부터").
    새 템플릿 = A 의 사슬 그대로 · base = level − 1(L1~L level−1 은 A 의 레벨 — 그 줄은 A 것) · L level 슬롯 = rep 줄의 모양(shape = rep_shape — 대표·동결 접두·모양,
    A 의 자리 규칙·repSet 은 안 옮김) · 더 깊은 레벨 = A 의 슬롯 그대로. 옮기는 줄 = paras + 그 아래 A 줄(자손 — 레벨은 그대로). A 는 안 바뀐다.
    into(이미 있는 서식 종속 템플릿 id)를 주면 새로 만들지 않고 거기에 더 넣는다. slots(옛 템플릿의 슬롯 — carry)을 주면 그 슬롯으로.
    stop = 자손으로 데려가지 않을 줄(그 아래도) · by = 누가 뗐나(「retidy」 = 넣은 뒤 정리 — variant · 떼기 기록에 남아 carry 가 다시 건다: spec_병합 ② §5-9) ·
    side = 뗀 줄이 어느 쪽인가(넣은 뒤 정리 — 「ins」 넣은 줄 · 「form」 목적 문서의 줄: variant · 떼기 기록에 남는다 — 화면 이름표 · merge_retidy.plan).
    cut = 자리로 나누기(② §8-13 — 「here」 그 줄만 · 「all」 그 레벨 줄 모두: variant · 떼기 기록에 남는다): 서식과 무관하게 옮기므로 대표 줄도 옮긴다 —
    그 레벨에 남은 줄이 없으면 A 의 그 슬롯은 대표 없이 동결 모양만 남는다(합치면 그 템플릿의 대표가 돌아온다 — unsplit).
    오버레이만 바꾼다 — 검사는 바꾸기 전에 다 한다(ValueError·KeyError). -> {"id", "no", "moved"[자손 포함], "paras", "new"}."""
    tid, level = str(tid), int(level)
    A = _tpl(ov, tid)
    paras = list(dict.fromkeys(paras or []))
    for pid in paras:
        _check_member(ov, tid, level, pid)
    why = split_block(ov, tid, level, paras, doc=doc, whole=bool(cut))  # doc = 표 안의 줄을 같은 표의 형제끼리 본다(split_units — 없으면 흐름으로)
    if why:
        raise ValueError(why)
    rep = rep or paras[0]
    if rep not in paras:
        raise ValueError("대표로 삼을 줄은 떼는 서식의 줄이어야 합니다")
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
                sl.pop(RETIDY_DEEP, None)  # A 의 레벨에 적은 넣은 뒤 정리의 표 — 새 템플릿의 것이 아니다
                sl["rep"] = None
                if k == level:
                    sl.pop("pos", None)
            made[str(k)] = sl
        C = {"no": f"{A['no']}L{level}{sfx}", "kind": A.get("kind"), "anchor": f"{A.get('anchor')}~L{level}{sfx}", "chain": chain, "slots": made, "max": amax,
             "base": level - 1, "variant": {"of": tid, "level": level, "sfx": sfx, **({"by": by} if by else {}), **({"side": side} if side else {}), **({"cut": cut} if cut else {})}}
        new = True
    # ---- 여기부터 오버레이를 바꾼다
    moved = sorted(_members(ov, tid, paras, stop))
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
            else:  # 그 레벨에 남은 줄이 없다(자리로 나눈 레벨 · 뗀 줄이 데려간 더 깊은 레벨) — 대표 없이 동결 모양만: 다른 템플릿의 줄을 대표로 가리키지 않는다
                sl["rep"] = None  # (그대로 두면 그 레벨에 줄을 새로 만든 뒤의 「대표에 맞추기」 가 대표의 소속 검사에서 400 — a6 의 astra 2차. 합치면 돌아온 줄이 대표가 된다: unsplit)
                sl.pop("repSet", None)
                sl.pop("agentRep", None)
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
    if cut:  # 자리로 나눈 줄은 레벨을 건너뛴 자리(「1.」 바로 아래의 L4 상자)에도 매달린다 — 실제로 매달린 자리마다 가지로(부모 찾기가 (A, level − 1) 만 보면 그 자리를 놓친다: astra)
        br = ov.setdefault("branches", {})
        for pid in paras:
            p = ov["lines"].get(ov["lines"][pid].get("parent"))
            if p is not None and p["tpl"] != cid:
                lst = br.setdefault(f"{p['tpl']}|{p['level']}", [])
                if cid not in lst:
                    lst.append(cid)
        for pid, x in ov["lines"].items():  # 옮긴 줄 아래에 남은 **다른 템플릿의 첫 레벨 줄**(이미 뗀 「T1L5a」 …)도 — 그 템플릿은 이제 (새 템플릿, 그 레벨)에도 매달린다(부모 찾기: astra 2차)
            p = ov["lines"].get(x.get("parent")) if x["tpl"] != cid else None
            if p is not None and p["tpl"] == cid and x.get("parent") in gone and int(x["level"]) == _base(ov["templates"].get(x["tpl"]) or {}) + 1:
                lst = br.setdefault(f"{cid}|{p['level']}", [])
                if x["tpl"] not in lst:
                    lst.append(x["tpl"])
        for T in (A, C):  # 대표가 제 템플릿 · 제 레벨의 줄이 아니면(앞선 떼기가 대표를 데려간 채 둔 것 · 다시 분석해 레벨이 달라진 것) 그 레벨의 첫 줄로, 없으면 비운다 — 출처 표지도 함께
            T_id = tid if T is A else cid
            for k, sl in T["slots"].items():
                x = ov["lines"].get(sl.get("rep")) if sl.get("rep") else None
                if x is not None and int(k) >= level and not (x["tpl"] == T_id and str(x["level"]) == str(k)):  # 오버레이 줄이 아닌 대표(자동 글머리 줄 …)와 나눈 레벨 위는 건드리지 않는다
                    rest =[pid for pid, y in ov["lines"].items() if y["tpl"] == T_id and str(y["level"]) == str(k)]
                    sl["rep"] = rest[0] if rest else None
                    sl.pop("repSet", None)
                    sl.pop("agentRep", None)
    # 자리로 나눈 것 · 자리로 나눈 템플릿에 더 넣은 것은 **따로 한 건**(add — 제 차례 n): 만든 기록에 합치면 다시 걸 때 그 사이에 한 다른 떼기보다 앞서 걸려 소속이 달라진다
    # (astra — 실제 함수로 본 반례: 서식 떼기의 「더 넣기」 로 자리로 나눈 템플릿에 넣어도 같다). 서식 떼기끼리의 더 넣기는 전처럼 만든 기록에 합친다
    apart = not new and bool(cut or (C.get("variant") or {}).get("cut"))
    rec = None if apart else next((r for r in recs if r.get("id") == cid and not r.get("add")), None)
    if rec is None:
        asl = A["slots"].get(str(level)) or {}
        rec = {"of": A.get("anchor"), "ofId": tid, "level": level, "sfx": C["variant"]["sfx"], "id": cid, "lines": [], "n": _seq(ov), **({"by": by} if by else {}),
               **({"side": side} if side else {}), **({"cut": cut} if cut else {}), **({"add": True} if apart else {}),
               # 자리로 나눈 때의 그 레벨의 레터 · 표 레벨인가 — 다시 분석해 그 레벨 번호가 다른 레벨이 됐으면 걸지 않는다(_carry_split: 상자 레벨이 없어져 「o」 가 그 번호가 된 문서)
               **({"key": asl.get("key"), "table": bool(asl.get("table"))} if cut or apart else {})}
        recs.append(rec)
    rec["lines"] = sorted(set(rec["lines"]) | set(paras))
    if stop:
        rec["stop"] = sorted(set(rec.get("stop") or ()) | set(stop))
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
    if v.get("by") == "merge" or any(str(k) not in (A.get("slots") or {}) for k in (C.get("slots") or {})):   # 「내용 반영」 이 A 의 끝 아래에 등록한 넣은 꼬리(spec_병합 ② §5-12 · merge_register) — A 에 그 레벨이 없어 합치면 슬롯 없는 줄이 된다(astra 3차)
        raise ValueError(f"T{C['no']} 는 「내용 반영」 이 T{A['no']} L{v['level'] - 1} 아래에 넣은 내용의 템플릿이라 합칠 수 없습니다 — 「넣은 뒤 정리」 가 소속과 서식을 다시 정합니다")
    for m in ov.get("merges") or []:
        if cid in (m.get("childId"), m.get("parentId")):
            other = ov["templates"].get(m.get("id"), {}).get("no", m.get("id"))
            raise ValueError(f"T{C['no']} 로 만든 종속 템플릿 T{other} 가 있습니다 — 그것부터 떼세요")
    _no_variants(ov, cid, C["no"])
    ids = [pid for pid, x in ov["lines"].items() if x["tpl"] == cid]
    for pid in ids:
        ov["lines"][pid].update(tpl=tid, no=A["no"])
    _deep_shift(ov, cid, tid, ids)  # 넣은 뒤 정리의 표 — 돌아온 줄의 몫을 A 로
    for k, sl in (A.get("slots") or {}).items():  # A 의 그 레벨에 유효한 대표가 없으면(자리로 나눠 비었던 레벨 …) 돌아온 줄 가운데 그 템플릿의 대표였던 줄을 대표로 — 동결 모양은 A 것 그대로 · 대표의 출처도 함께
        if not sl.get("rep") or sl["rep"] in ov["lines"]:  # 오버레이 줄이 아닌 대표(자동 글머리 줄 …)는 건드리지 않는다
            x = ov["lines"].get(sl.get("rep")) if sl.get("rep") else None
            if x is not None and x["tpl"] == tid and str(x["level"]) == str(k):
                continue  # 그 사이 A 에 정한 대표가 먼저다
            csl = (C.get("slots") or {}).get(str(k)) or {}
            y = ov["lines"].get(csl.get("rep")) if csl.get("rep") else None
            if y is not None and y["tpl"] == tid and str(y["level"]) == str(k):
                sl["rep"] = csl["rep"]
                for key in ("repSet", "agentRep"):
                    sl.pop(key, None)
                    if csl.get(key):
                        sl[key] = csl[key]
    ov["templates"].pop(cid, None)
    br = ov.get("branches") or {}
    for key in [k for k in br if k.split("|")[0] == cid]:
        br.pop(key, None)
    for lst in br.values():
        if cid in lst:
            lst.remove(cid)
    ov["splits"] = [r for r in ov.get("splits") or [] if r.get("id") != cid]
    if ov.get("lost"):
        ov["lost"] = [r for r in ov["lost"] if r.get("id") != cid]
    _settle_cuts(ov)  # 돌아온 줄이 자리로 나눈 다른 템플릿의 줄 아래에 있으면 그 템플릿으로(다시 분석해 다시 걸 때와 같은 소속)
    return len(ids)


def _within(ov, t, cid):
    """템플릿 t 가 cid 이거나 거기서 다시 뗀 템플릿인가(variant.of 사슬)."""
    seen = set()
    while t is not None and t not in seen:
        if t == cid:
            return True
        seen.add(t)
        t = ((ov["templates"].get(t) or {}).get("variant") or {}).get("of")
        t = None if t is None else str(t)
    return False


def _settle_cuts(ov):
    """**자리로 나눈 템플릿**(② §8-13)이 지금 데려갈 줄을 데려간다 — 그 템플릿의 첫 레벨 줄(뿌리) 아래에 원래 템플릿의 줄이 매달려 있으면 그 템플릿의 줄로. 다시 분석해 나누기를 다시 걸 때(`carry`)
    그 줄이 가는 곳과 같게 하려는 것이다(astra 2차의 반례: 안쪽 템플릿을 합친 직후에는 원래 템플릿 · 다시 분석하면 나눈 템플릿 — 겹쳐 나눈 템플릿 · 멈춤 경계가 풀린 줄도). 만든 차례대로.
    받은 레벨에 유효한 대표가 없으면 받은 첫 줄이 대표. -> 옮긴 줄 수."""
    order = {}
    for m in ov.get("splits") or []:
        if m.get("cut") and not m.get("add"):
            order.setdefault(m.get("id"), m.get("n") or 0)
    n = 0
    for cid in sorted(order, key=lambda c: order[c]):
        C = ov["templates"].get(cid)
        v = (C or {}).get("variant") or {}
        if not v.get("cut"):
            continue
        of, first = str(v["of"]), int(v["level"])
        roots = [pid for pid, x in ov["lines"].items() if int(x["level"]) == first and _within(ov, x["tpl"], cid)]
        took = [pid for pid in _members(ov, of, roots) if ov["lines"][pid]["tpl"] == of and str(ov["lines"][pid]["level"]) in C["slots"]]
        if not took:
            continue
        for pid in took:
            ov["lines"][pid].update(tpl=cid, no=C["no"])
        _deep_shift(ov, of, cid, took)
        gone = set(took)
        for k in sorted({str(ov["lines"][pid]["level"]) for pid in took}):  # 받은 레벨 — 나눈 템플릿에 대표가 없으면 받은 첫 줄 · 원래 템플릿의 대표가 떠났으면 남은 첫 줄(없으면 비움)
            sl = C["slots"][k]
            x = ov["lines"].get(sl.get("rep")) if sl.get("rep") else None
            if not sl.get("rep") or (x is not None and not (x["tpl"] == cid and str(x["level"]) == k)):
                sl["rep"] = next(pid for pid in took if str(ov["lines"][pid]["level"]) == k)
                sl.pop("repSet", None)
                sl.pop("agentRep", None)
            asl = ((ov["templates"].get(of) or {}).get("slots") or {}).get(k)
            if asl is not None and asl.get("rep") in gone:
                rest = [pid for pid, y in ov["lines"].items() if y["tpl"] == of and str(y["level"]) == k]
                asl["rep"] = rest[0] if rest else None
                asl.pop("repSet", None)
                asl.pop("agentRep", None)
        n += len(took)
    return n


def _deep_shift(ov, src, dst, ids):
    """넣은 뒤 정리의 표(RETIDY_DEEP — 줄 소속에 묶인 것: 다음 「넣은 뒤 정리」 · 자리 맞춤이 읽는다)를 옮긴 줄 ids 의 몫만 템플릿 src → dst 의 같은 레벨로. 남은 줄의 몫은 src 에."""
    S, D = ov["templates"].get(str(src)) or {}, ov["templates"].get(str(dst)) or {}
    ids = set(ids)
    for k, sl in (S.get("slots") or {}).items():
        dz = sl.get(RETIDY_DEEP)
        mine = [p for p in (dz or {}).get("lines") or () if p in ids]
        if not mine:
            continue
        rest = [p for p in dz["lines"] if p not in ids]
        dsl = (D.get("slots") or {}).get(str(k))
        if dsl is not None:
            cur = dsl.get(RETIDY_DEEP) or {}
            dsl[RETIDY_DEEP] = {"rep": cur.get("rep") or (dz.get("rep") if dz.get("rep") in mine else None), "lines": list(dict.fromkeys(list(cur.get("lines") or ()) + mine))}
        if rest:
            sl[RETIDY_DEEP] = {"rep": dz.get("rep") if dz.get("rep") in rest else None, "lines": rest}
        else:
            sl.pop(RETIDY_DEEP, None)


def _carry_split(old, new, m, tid, doc=None):
    """carry 의 떼기 한 건 — 새 오버레이의 템플릿 tid(같은 앵커)에서 기록 m 의 줄 가운데 지금도 (tid, level) 줄인 것을 다시 뗀다. -> 못 건 까닭 | None.
    기능이 쪽을 골라 뗀 것(by — 넣은 뒤 정리: 넣은 줄 · 목적 문서의 줄)은 옛 오버레이에서 그 템플릿 밖이던 줄을 데려가지 않는다 — 다시 분석한 그래프에서 그 줄의 부모가
    뗀 줄이 되어도(넣은 줄 아래로 매달린 양식 줄이 넣은 내용의 템플릿에 들면 다음 정리가 그 줄을 넣은 줄의 서식으로 바꾼다: spec_병합 ② §5-9). 그 줄은 기록의 stop 에 더한다.
    옛 오버레이에 없던 줄(그 뒤에 생긴 줄 — 뗀 템플릿에서 Enter 로 만든 줄 …)은 전처럼 자손이면 데려간다."""
    if tid is None:
        return "템플릿이 없음"
    level = int(m["level"])
    lines = [p for p in m.get("lines") or [] if p in new["lines"] and new["lines"][p]["tpl"] == tid and int(new["lines"][p]["level"]) == level]
    stop = list(m.get("stop") or ())
    cut, placed = m.get("cut"), bool(m.get("cut") or m.get("add"))  # placed = 자리로 나눈 것 · 자리로 나눈 템플릿에 더 넣은 것(② §8-13)
    oc = (old.get("templates") or {}).get(m.get("id")) or {}
    ol, otp = old.get("lines") or {}, old.get("templates") or {}
    into, hold = None, set()

    def inside(t):  # 옛 오버레이에서 그 템플릿이거나 거기서 다시 뗀 서식 종속 템플릿(그 기록이 뒤에서 다시 뗀다)
        seen = set()
        while t is not None and t not in seen:
            if t == m.get("id"):
                return True
            seen.add(t)
            t = ((otp.get(t) or {}).get("variant") or {}).get("of")
            t = None if t is None else str(t)
        return False
    if placed:  # 자리로 나누기 — 「누른 때의 그 자리」 를 잇는다
        # ⓐ 그 레벨이 나눈 때의 그 레벨이어야 한다 — 기록에 적어 둔 그때의 레터 · 표 레벨 여부로 본다(나눈 템플릿의 지금 슬롯으로 보지 않는다: 상자 레벨이 없어지면 레벨 번호를 맞추는 길
        #   heading_boxes.align_old 가 그 슬롯을 다른 레터로 덮는다 — astra 2차). 사람이 그 레벨의 레터를 고친 것(옛 A 의 지금 레터 = 새 A 의 레터 · 표 레벨 여부 같음)은 같은 레벨이다
        nsl0, osl0 = OE._slot(new, tid, level) or {}, ((otp.get(str(m.get("ofId"))) or {}).get("slots") or {}).get(str(level)) or {}
        if "key" in m and nsl0.get("key") != m["key"] and not (osl0.get("key") == nsl0.get("key") and bool(m.get("table")) == bool(nsl0.get("table"))):
            return f"그 레벨이 달라짐(나눌 때 「{m['key']}」 → 지금 「{nsl0.get('key')}」)"
        # 그 템플릿이 이미 다시 걸려 있으면 거기에 넣는다 — 더 넣은 기록은 보통 그렇고, 없으면(만든 기록의 줄이 다 없어짐) 이 줄들로 그 템플릿을 다시 만든다(살아 있는 줄까지 잃지 않게).
        # 못 걸려 남아 있던 만든 기록(lost)이 뒤에 다시 걸릴 때도, 그 사이 더 넣은 기록이 그 템플릿을 다시 만들어 뒀으면 거기에 넣는다
        anchor = oc.get("anchor") or f"{m.get('of')}~L{level}{m.get('sfx')}"
        into = next((k for k, t in new["templates"].items() if t.get("anchor") == anchor and (t.get("variant") or {}).get("of") == tid), None)
        if not m.get("add") and not m.get("why"):  # (못 걸려 남아 있던 기록 why 는 제 줄만 — 그 사이 그 템플릿을 다시 만든 기록이 제 차례에 제 줄을 건다) ⓑ 기록의 줄 + 다시 분석하기 직전에 그 템플릿(과 거기서 다시 나눈 템플릿)의 첫 레벨이던 줄 — 나눈 템플릿에서 사람이 만든 형제. 더 넣은 줄은 제 기록이 제 차례에 건다
            later = {p for r in old.get("splits") or [] if r.get("add") and r.get("id") == m.get("id") for p in r.get("lines") or ()}
            was = [p for p, x in ol.items() if int(x.get("level") or 0) == level and inside(x.get("tpl")) and p not in later]
            lines += [p for p in was if p not in lines and p in new["lines"] and new["lines"][p]["tpl"] == tid and int(new["lines"][p]["level"]) == level]
        # ⓒ 새로 잡힌 그 레벨 줄은 「모두」 로 나눈 것이어도 데려가지 않는다 — 뿌리로도, 뿌리 아래에 매달린 줄(같은 레벨끼리 부모 · 자식으로 읽힌 것)로도(레벨 번호만 같은 다른 줄일 수 있다)
        hold = {p for p, x in new["lines"].items() if x["tpl"] == tid and int(x["level"]) == level and p not in lines}
    if m.get("by"):
        out = {p for p in new["lines"] if p in ol and not inside(ol[p].get("tpl"))}
        lines = [p for p in lines if p not in out]
        stop = sorted(set(stop) | (_members(new, tid, lines, stop) & out))
    if not lines:
        return "뗀 줄이 없음"
    oa = (old.get("templates") or {}).get(m.get("ofId")) or {}
    nsl, osl = OE._slot(new, tid, level), (oa.get("slots") or {}).get(str(level)) or {}
    if not placed and nsl is not None and nsl.get("rep") in lines and osl.get("rep"):  # 새 그래프의 대표가 뗄 줄 — 옛 오버레이에서 A 의 대표였던 줄이 지금도 그 레벨 줄이면 그것으로
        x = new["lines"].get(osl.get("rep"))  # (자리로 나눈 것은 대표 줄도 옮기니 A 의 대표를 미리 바꾸지 않는다 — 못 걸었을 때 A 만 바뀐 채 남지 않게)
        if x is not None and x["tpl"] == tid and int(x["level"]) == level and osl["rep"] not in lines:
            nsl.update({k: osl.get(k) for k in ("rep", "prefix", "letter", "attrs", "bodyChar")})
    rep = ((oc.get("slots") or {}).get(str(level)) or {}).get("rep")
    try:
        if into is not None:
            split(new, tid, level, lines, into=into, doc=doc, stop=sorted(hold) or None, cut=cut)
        else:
            split(new, tid, level, lines, rep=rep if rep in lines else lines[0], sfx=m.get("sfx"), slots=oc.get("slots") or None, stop=sorted(set(stop) | hold) or None,
                  by=m.get("by"), side=m.get("side"), cut=cut or ("here" if placed else None), doc=doc if placed else None)
    except (KeyError, ValueError) as e:
        return str(e)
    if placed:  # 방금 적힌 기록 — 나눈 때의 레터 · 표 여부는 처음 것 그대로, 이번에 건너뛴 「새로 잡힌 줄」 은 기록의 멈춤 경계로 남기지 않는다(다음에 다시 센다)
        rec = new["splits"][-1]
        rec.update({k: m[k] for k in ("key", "table") if k in m})
        if stop:
            rec["stop"] = sorted(stop)
        else:
            rec.pop("stop", None)
    return None


# ---------------------------------------------------------------- 자리로 나누기 — 「여기부터 새 템플릿으로」(spec_hwpx_웹편집 ② §8-13)
CUT_SCOPES = ("here", "all")  # 여기서만(그 줄과 그 아래) · 모두(그 템플릿 · 그 레벨 줄 전부)


CUT_BAND = "별첨·부록 표 제목 줄은 나누지 않습니다 — 그 템플릿의 줄은 표 제목 한 레벨뿐이고 아래 줄은 제 템플릿을 씁니다"
CUT_MERGE = "「내용 반영」 이 넣은 내용의 템플릿은 여기서 나누지 않습니다 — 「넣은 뒤 정리」 가 소속과 서식을 다시 정합니다"
CUT_VALUE = "값 칸(표 칸에 혼자 있는 레터)뿐이라 나누지 않습니다 — 글이 있는 줄에서 나누세요"


def cut_paras(doc, ov, tid, level, paras, scope):
    """나눌 (tid, level) 줄(문서 순). scope 「here」 = paras(라벨 하나가 가리키는 줄 — 보통 하나 · 표 한 행의 칸들이면 여럿) — 번호형 레벨이면 그 줄과 같은 (부모, 표) 형제 묶음 전체
    (번호가 템플릿마다 따로 매겨진다: split_units) · 「all」 = 그 레벨의 줄 모두(값 칸 · 지금 문서에 없는 줄도 — 레벨이 통째로 옮겨 간다). paras 가 그 레벨 줄이 아니면 ValueError."""
    tid, level = str(tid), int(level)
    paras = list(dict.fromkeys(paras or []))
    if scope not in CUT_SCOPES:
        raise ValueError("scope 는 here | all")
    if OE._slot(ov, tid, level) is None:
        raise KeyError("그런 템플릿 레벨이 없습니다")
    if not paras:
        raise ValueError("나눌 줄이 없습니다")
    for p in paras:
        if not _alive(doc, p):
            raise ValueError("그 줄이 지금 문서에 없습니다 — 다시 읽어 주세요")
        _check_member(ov, tid, level, p)
    order = _order(doc)
    by_doc = lambda ids: sorted(ids, key=lambda p: order.get(p, 1 << 30))  # noqa: E731
    if scope == "all":
        return by_doc(slot_ids(ov, tid, level))
    units = split_units(ov, tid, level, doc)
    if units is None:
        return by_doc(paras)
    want = {units[p] for p in paras if p in units}
    return by_doc(set(paras) | {p for p, u in units.items() if u in want})


def cut_block(ov, tid, level, paras, doc=None, into=None):
    """자리로 나눌 수 없는 까닭 | None — split_block 의 검사(대표 줄은 빼고) + 띠 표 템플릿 · 「내용 반영」 이 넣은 내용의 템플릿(by merge — 떼기 기록이 없어 다시 분석하면 못 잇는다) ·
    into 가 기능이 쪽을 골라 뗀 템플릿(by — 넣은 뒤 정리의 넣은 줄 · 목적 문서의 줄: 거기에 다른 줄을 넣으면 다음 정리가 그 줄까지 그쪽 것으로 본다)."""
    tid = str(tid)
    t = ov["templates"].get(tid) or {}
    if t.get("kind") == OE.BAND:
        return CUT_BAND
    seen, x = set(), tid
    while x is not None and x not in seen:  # 그 템플릿이나 그 윗 템플릿이 넣은 내용의 템플릿
        seen.add(x)
        v = (ov["templates"].get(x) or {}).get("variant") or {}
        if v.get("by") == "merge":
            return CUT_MERGE
        x = None if v.get("of") is None else str(v["of"])
    sl = OE._slot(ov, tid, level) or {}
    if doc is not None and not sl.get("table") and paras and all(lone_value(doc, ov, p) for p in paras):
        return CUT_VALUE  # 값 칸뿐 — 새 템플릿의 대표가 될 줄이 없다(값 칸이 대표면 「대표 맞추기」 가 거절한다)
    if into is not None:
        C = ov["templates"].get(str(into)) or {}
        v = C.get("variant") or {}
        if v.get("of") != tid or int(v.get("level") or 0) != int(level):
            return f"그 템플릿은 T{t.get('no')} L{level} 에서 나눈 템플릿이 아닙니다"
        if v.get("by"):
            return f"T{C.get('no')} 는 「넣은 뒤 정리」 · 「내용 반영」 이 만든 템플릿이라 줄을 더 넣지 않습니다"
        for k in sorted({int(ov["lines"][p]["level"]) for p in _members(ov, tid, paras) if p in ov["lines"]}):  # 옮길 줄이 있는 레벨마다 — 레터가 달라진 레벨(그 템플릿에서 레터를 고친 것)에는 넣지 않는다
            a, c = (t.get("slots") or {}).get(str(k)) or {}, (C.get("slots") or {}).get(str(k))
            if c is None or c.get("key") != a.get("key") or bool(c.get("table")) != bool(a.get("table")):
                return f"T{C.get('no')} 의 L{k} 는 레터가 T{t.get('no')} L{k}(「{a.get('letter') or a.get('key')}」)와 달라 넣지 않습니다 — 새 템플릿으로 나누세요"
    return split_block(ov, tid, level, paras, doc=doc, whole=True)


def cut_sig(ov, tid, level, paras):
    """나누기 계획의 지문 — 메뉴가 보인 것(옮길 줄 · 그 아래 줄 · 그 레벨에서 이미 나눈 템플릿 · 헤딩 그래프의 실행)과 실행할 때의 것이 같은가(다르면 409: 그 사이 줄이 생기거나 빠진 것 ·
    합쳤다가 같은 이름으로 다시 나눈 것 · 다시 분석한 것 — 줄 수가 같아도 대상이 다를 수 있다: astra 2차)."""
    tid = str(tid)
    made = sorted((oid, o.get("anchor") or "", sum(1 for x in ov["lines"].values() if x["tpl"] == oid)) for oid, o in ov["templates"].items()
                  if (o.get("variant") or {}).get("of") == tid and int(o["variant"]["level"]) == int(level))
    raw = json.dumps([tid, int(level), sorted(paras), sorted(_members(ov, tid, paras)), made, ov.get("run")], ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def unsplit_block(ov, cid):
    """서식 종속 템플릿 cid 를 합칠 수 없는 까닭 | None(`unsplit` 이 거절하는 것과 같다 — 화면이 미리 묻는다)."""
    try:
        unsplit(copy.deepcopy({k: ov.get(k) for k in ("templates", "lines", "branches", "splits", "merges")}), cid)
    except (KeyError, ValueError) as e:
        return str(e)
    return None


def cut_view(doc, ov, paras):
    """줄 paras(라벨 하나가 가리키는 줄 — 같은 템플릿 · 레벨)의 라벨 메뉴 자료(② §8-13) — {tpl, no, level, paras, table(표 제목 레벨인가), numbered(번호형 레벨인가), next(새 템플릿 이름 「1L4a」 |
    None = 글자를 다 씀), here{lines, moved, why}, all{…}, made[{id, no, lines, why}](그 레벨에서 이미 나눈 템플릿 — why = 더 넣을 수 없는 까닭), back{id, no, ofNo, lines, cut, why} | None
    (이 줄의 템플릿이 다른 템플릿에서 나눈 것이면 — 합치기)}. lines = 그 레벨에서 옮길 줄 · moved = 그 아래 줄까지(실제로 옮겨 가는 줄 — 그 템플릿에서 이미 뗀 다른 템플릿의 줄은 안 간다) · why = 못 하는 까닭.
    읽기만 한다."""
    paras = list(dict.fromkeys(paras or []))
    if not paras:
        raise ValueError("줄이 없습니다")
    x = _line_of(ov, paras[0])
    tid, level = str(x["tpl"]), int(x["level"])
    A = _tpl(ov, tid)
    sl = OE._slot(ov, tid, level) or {}
    sfx = _free_sfx(ov, tid, level)
    count = {}
    for y in ov["lines"].values():
        count[y["tpl"]] = count.get(y["tpl"], 0) + 1
    made = []
    for oid, o in ov["templates"].items():
        ovr = o.get("variant") or {}
        if ovr.get("of") == tid and int(ovr.get("level") or 0) == level:
            made.append({"id": oid, "no": o["no"], "lines": count.get(oid, 0),
                         "why": f"T{o['no']} 는 「넣은 뒤 정리」 · 「내용 반영」 이 만든 템플릿이라 줄을 더 넣지 않습니다" if ovr.get("by") else None})
    out = {"tpl": tid, "no": A["no"], "level": level, "paras": paras, "table": bool(sl.get("table")), "numbered": OE.is_numbered(sl.get("key") or ""),
           "next": f"{A['no']}L{level}{sfx}" if sfx else None, "made": sorted(made, key=lambda m: str(m["no"])), "back": None}
    for scope in CUT_SCOPES:
        one = {"lines": 0, "moved": 0, "why": None, "sig": None}
        try:
            got = cut_paras(doc, ov, tid, level, paras, scope)
            one["lines"], one["moved"], one["sig"] = len(got), len(_members(ov, tid, got)), cut_sig(ov, tid, level, got)
            one["why"] = cut_block(ov, tid, level, got, doc=doc)
        except (KeyError, ValueError) as e:
            one["why"] = str(e)
        out[scope] = one
    v = A.get("variant")
    if v:
        of = ov["templates"].get(str(v["of"])) or {}
        out["back"] = {"id": tid, "no": A["no"], "ofNo": of.get("no"), "lines": count.get(tid, 0), "cut": v.get("cut"), "why": unsplit_block(ov, tid)}
    return out


def cut(doc, ov, tid, level, paras, scope="here", into=None):
    """**자리로 나누기** — 템플릿 tid(A) 를 줄 paras 의 L level 에서 새 템플릿으로 나눈다(2026-11-23 사용자 "T1L1, L2, L3, L4 이렇게 가다가 L4부터 새로운 템플릿으로 나눌 수 있도록 …
    바꾸면 다른 템플릿도 다바꿀건지.. 아니면 여기서만 바꿀지도 선택"). 서식 갈래를 떼는 `split`(② §8-5)과 달리 **서식과 무관하게** 그 줄을 옮긴다 — 대표 서식의 줄이어도, 그 레벨 줄 전부여도.
    새 템플릿 = 서식 종속 템플릿과 같은 틀(표기 「T{A}L{k}a」 · 줄은 L level 부터 · 그 줄과 그 아래 A 줄이 간다 · A 에서 이미 뗀 다른 템플릿의 줄은 제 템플릿 그대로).
    scope 「here」 = 그 줄만(번호형 레벨이면 같은 번호 묶음의 형제도 — cut_paras): 새 템플릿 L level 의 대표 · 모양 = 그 줄의 지금 것(표 제목 줄 · 1칸 제목 상자처럼 레터가 없는 줄은 슬롯 그대로, 대표만 그 줄).
    scope 「all」 = 그 레벨 줄 모두: 대표 · 대표의 출처(사람이 정함 · 계획이 정함)도 그대로 옮겨 간다. A 의 그 레벨은 대표 없이 동결 모양만 남는다.
    두 범위 모두 A 의 슬롯을 본뜬다 — 동결 모양 · **사람이 정한 자리 규칙(pos)도**(같은 서식의 줄을 자리로만 나눈 것이다 — 서식 갈래를 떼는 split 은 떼는 레벨의 자리 규칙을 안 옮긴다).
    넣은 뒤 정리의 표(retidyDeep)는 옮겨 간 줄의 몫만 새 템플릿으로.
    into(그 레벨에서 이미 나눈 템플릿 id)를 주면 거기에 더 넣는다(그 템플릿의 대표 · 모양 그대로 — 기록은 따로 한 건). 오버레이만 바꾼다 — 검사는 바꾸기 전에 다 한다. -> split 의 답 + {"scope"}."""
    tid, level = str(tid), int(level)
    A = _tpl(ov, tid)
    got = cut_paras(doc, ov, tid, level, paras, scope)
    why = cut_block(ov, tid, level, got, doc=doc, into=into)
    if why:
        raise ValueError(why)
    if into is not None:
        out = split(ov, tid, level, got, into=into, doc=doc, cut=scope)
        _deep_shift(ov, tid, out["id"], out["moved"])  # 넣은 뒤 정리의 표 — 옮겨 간 줄의 몫만 그 템플릿으로
        return {**out, "scope": scope}
    keep = scope == "all"
    table = bool((OE._slot(ov, tid, level) or {}).get("table"))
    fit = [p for p in got if table or not lone_value(doc, ov, p)]  # 대표가 될 수 있는 줄 — 값 칸(표 칸에 혼자 있는 레터)은 글 레벨의 대표가 아니다(cut_block 이 하나는 있음을 봤다)
    slots = {}
    for k, sl in A["slots"].items():
        if int(k) >= level:
            slots[k] = {kk: vv for kk, vv in sl.items() if kk != RETIDY_DEEP and (keep or kk not in ("repSet", "agentRep"))}
    cur = (OE._slot(ov, tid, level) or {}).get("rep")
    rep, shape = (cur if cur in fit else fit[0]), None
    if rep != cur:  # 대표가 바뀐다(여기서만 · 지금 대표가 값 칸) — 사람이 정한 표지는 그 줄의 것이 아니다
        for key in ("repSet", "agentRep"):
            slots[str(level)].pop(key, None)
    if not keep:
        rep = next((p for p in fit if p in paras), fit[0])  # 누른 줄(번호 묶음이면 그 가운데 누른 줄 — 값 칸이면 묶음의 글이 있는 첫 줄)
        slots[str(level)]["rep"] = None
        try:
            shape = None if table else rep_shape(doc, ov, rep)
        except (KeyError, ValueError):
            shape = None  # 레터가 없는 줄 — 슬롯의 동결 모양 그대로, 대표만 그 줄로
    elif rep != cur and not table:
        slots[str(level)]["rep"] = None
        try:
            shape = rep_shape(doc, ov, rep)
        except (KeyError, ValueError):
            shape = None
    out = split(ov, tid, level, got, rep=rep, shape=shape, slots=slots, doc=doc, cut=scope)
    _deep_shift(ov, tid, out["id"], out["moved"])  # 넣은 뒤 정리의 표 — 줄 소속에 묶인 것이라 옮겨 간 줄의 몫만 새 템플릿으로, 남은 줄의 몫은 A 에
    return {**out, "scope": scope}


def apply_reps(g, ov):
    """그래프 g 의 템플릿 레벨 대표 문단(slots[].rep)을 정해 둔 대표(오버레이 — 사람이 정한 repSet · 서식 정리 계획이 정한 agentRep: rep_origin)로 바꾼 **사본** — 서식 복사의 내용 서식 후보가 그 줄의 서식을 뽑게
    (spec_hwpx_웹편집 ② §8-2 · spec_서식복사 ② §12). 그 대표가 오버레이에서 같은 템플릿·레벨 줄일 때만. 바꿀 것이 없으면 g 그대로."""
    if not g or not ov:
        return g
    picks = {}
    for tid, t in (ov.get("templates") or {}).items():
        for lv, sl in (t.get("slots") or {}).items():
            x = ov["lines"].get(sl.get("rep")) if rep_origin(sl) else None  # 계획이 정한 대표도(전에는 계획 반영도 repSet 을 켰다 — 서식 후보가 쓰는 대표는 그대로)
            if x is not None and x["tpl"] == tid and str(x["level"]) == str(lv):
                picks[(tid, int(lv) - OE.lift_depth(t))] = sl["rep"]  # 표 제목을 표 레벨로 넣은 템플릿(② §8-7)은 오버레이 레벨이 그래프보다 표 레벨 수만큼 깊다
    if not picks:
        return g
    tpls = []
    for t in g.get("templates") or []:
        tid = str(t.get("id", t.get("no")))
        if any(k[0] == tid for k in picks):
            t = {**t, "slots": [{**s, "rep": picks.get((tid, int(s.get("level") or 0)), s.get("rep"))} for s in t.get("slots") or []]}
        tpls.append(t)
    return {**g, "templates": tpls}

