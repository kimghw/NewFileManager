"""고친 문단이 어떻게 바뀌었나(spec_작업 ② §8 「화면」 — 깃 diff 처럼) — 기준 블록과 지금 블록의 모양 값을 견준다.

순수 함수만(세션·문서를 모른다 — 부르는 쪽 server.edits_detail 이 기준 블록 s.blocks 와 지금 블록 s.doc.blocks() 를 넘긴다).
글의 다름은 화면이 원래 글(state.original)과 지금 글로 그린다 — 여기서는 모양(문단 스타일 · 문단 모양 · 글자 모양 · 목록)만.
값은 화면에 보이는 꼴(「15pt」·「10.4mm」·「양쪽」)로 견준다 — 소수 끝자리만 다른 값은 같은 값.

줄의 자리는 서식 값(왼쪽 여백 · 첫 줄)이 아니라 **줄이 시작하는 자리**로 견준다 — 「앞 여백」(첫 줄) · 「2번째 줄」(둘째 줄부터): 「템플릿 관계」·서식 관리자와 같은 말(`outline_match.look` 의 line1Mm·line2Mm).
2026-11-17 사용자(「□ 추진배경(목적)」 꼬리표 「첫 줄 0mm → -7.8mm」 를 보고) "이게 원본이 원래 0은 아닌데" → 답 「2번째 줄 자리로」: 한글의 내어쓰기는 첫 줄을 그대로 두고 둘째 줄부터를 들이는데
「첫 줄 -7.8mm」 는 첫 줄이 왼쪽으로 옮겨진 것처럼 읽힌다(움직이지 않은 첫 줄은 적지 않고, 바뀐 「2번째 줄 0mm → 7.8mm」 만 적는다).
"""

# 문단 모양 — 블록 format 의 문단 키(hwpx_format · docx_format 의 요약 키). line1Mm·line2Mm 은 왼쪽 여백·첫 줄 값에서 센 자리(`lines`).
PARA = (("align", "정렬"), ("line1Mm", "앞 여백"), ("line2Mm", "2번째 줄"), ("indentRightMm", "오른쪽 여백"),
        ("spaceBeforePt", "위 간격"), ("spaceAfterPt", "아래 간격"), ("lineSpacingPct", "줄 간격"), ("wordBreak", "줄 나눔"))
LINE_KEYS = ("line1Mm", "line2Mm")
# 줄의 자리 값의 뜻(화면 도움말 — 값 `hint`): 문단 모양에서 센 자리이지 레터 뒤 빈칸을 잰 폭이 아니다(2026-11-17 사용자 "0mm 측정 자체가 잘못된거야. 빈칸이 있는데 한글에서는 빈칸이잖아" — 0 을 빈칸 폭으로 읽음)
HINTS = {"line1Mm": "앞 여백 = 첫 줄이 시작하는 자리(문단 상자 왼끝에서) — 한글 「문단 모양」 의 왼쪽 여백·첫 줄 값에서 센 것입니다(레터 뒤 빈칸의 폭이 아님).",
         "line2Mm": "2번째 줄 = 글이 다음 줄로 넘어갈 때 둘째 줄부터가 시작하는 자리(문단 상자 왼끝에서) — 한글 「문단 모양」 의 왼쪽 여백·내어쓰기 값에서 센 것입니다. "
                    "0mm = 내어쓰기 없음(둘째 줄이 레터 아래에서 시작) — 레터 뒤 빈칸의 폭을 잰 값이 아닙니다."}
# 글자 모양 — 블록 format(런이 하나일 때) 또는 런마다의 format
CHAR = (("font", "글꼴"), ("sizePt", "크기"), ("bold", "굵게"), ("italic", "기울임"), ("underline", "밑줄"), ("color", "색"),
        ("ratioPct", "장평"), ("spacingPct", "자간"))
ALIGN = {"left": "왼쪽", "right": "오른쪽", "center": "가운데", "justify": "양쪽", "distribute": "배분", "distribute_space": "나눔"}
WORD_BREAK = {"word": "어절", "char": "글자"}


def index(blocks):
    """{문단 id: 문단 블록} — 최상위·칸 안 문단(verify.flat_texts 와 같은 길)."""
    out = {}

    def walk(bs):
        for b in bs or ():
            if b.get("type") == "paragraph" and b.get("id"):
                out[b["id"]] = b
            for c in b.get("cells") or ():
                walk(c.get("blocks"))
    walk(blocks)
    return out


def shown(key, v):
    """화면용 값 글 — mm·pt·% 는 단위, 켬/끔, 정렬·줄 나눔은 우리말, 없으면 「없음」."""
    if v is None or v == "":
        return "없음"
    if isinstance(v, bool):
        return "켬" if v else "끔"
    if key == "align":
        return ALIGN.get(v, str(v))
    if key == "wordBreak":
        return WORD_BREAK.get(v, str(v))
    if isinstance(v, (int, float)):
        n = f"{round(float(v), 1):g}"
        return n + ("mm" if key.endswith("Mm") else "pt" if key.endswith("Pt") else "%" if key.endswith("Pct") else "")
    return str(v)


def lines(f, word=False):
    """문단 format → {line1Mm, line2Mm} — 첫 줄 · 둘째 줄부터가 시작하는 자리(mm — 문단 상자 왼끝에서). 두 서식 값이 다 없으면 둘 다 None.
    한글(hwpx): 왼쪽 여백 L · 첫 줄 f — 내어쓰기(f < 0)는 첫 줄이 L 에 있고 둘째 줄부터 L + |f|, 들여쓰기(f > 0)는 첫 줄이 L + f 이고 둘째 줄부터 L(`outline_match.look` 과 같은 셈).
    Word(docx — word=True): 왼쪽 값이 둘째 줄부터의 자리이고 첫 줄 = 왼쪽 + f(내어쓰기는 f < 0 — 화면 `indentLook` 과 같은 셈)."""
    left, first = f.get("indentLeftMm"), f.get("firstLineMm")
    if left is None and first is None:
        return dict.fromkeys(LINE_KEYS)
    left, first = float(left or 0), float(first or 0)
    one, two = (left + first, left) if word else (left + max(first, 0.0), left + max(-first, 0.0))
    return {"line1Mm": round(one, 2), "line2Mm": round(two, 2)}


def _list(b):
    x = b.get("list")
    if not isinstance(x, dict):
        return "없음"
    lv = f" 수준 {x['level']}" if x.get("level") else ""
    if x.get("kind") == "bullet":
        return f"글머리표 {x.get('label') or ''}".rstrip() + lv   # 글머리표 글자는 정의 — 번호(label)는 문서 차례로 세는 값이라 견주지 않는다
    return "번호" + lv


def _segments(b):
    """[(글, 글자 모양)] — 런이 없으면 문단 전체가 블록 format 한 조각. 글이 있는 조각만(없으면 전부)."""
    runs = b.get("runs") or [{"text": b.get("text") or "", "format": b.get("format") or {}}]
    segs = [(r.get("text") or "", r.get("format") or {}) for r in runs]
    return [s for s in segs if s[0].strip()] or segs


def _char_values(b, key):
    """그 글자 키의 값들(화면 꼴) — 문단 안 차례대로, 겹침 없이."""
    return list(dict.fromkeys(shown(key, f.get(key)) for _, f in _segments(b)))


def changes(before, after, word=False):
    """기준 블록 → 지금 블록의 모양 다름 [{key, label, before, after, part?, hint?}] — part = 문단 일부 글자만 다름(한쪽에 값이 둘 이상) · hint = 그 값의 뜻(줄의 자리 값에만).
    한쪽 블록이 없으면(새 문단 · 지운 문단 · 문단이 아닌 블록이 됨) None. word = Word 문서(줄의 자리 셈이 다르다 — `lines`)."""
    if not before or not after:
        return None
    out = []

    def add(key, label, a, b, part=False):
        if a != b:
            out.append({"key": key, "label": label, "before": a, "after": b, **({"part": True} if part else {}), **({"hint": HINTS[key]} if key in HINTS else {})})

    add("style", "문단 스타일", shown("style", before.get("style")), shown("style", after.get("style")))
    add("outlineLevel", "개요 수준", shown("outlineLevel", before.get("outlineLevel")), shown("outlineLevel", after.get("outlineLevel")))
    add("list", "목록", _list(before), _list(after))
    fa, fb = before.get("format") or {}, after.get("format") or {}
    fa, fb = {**fa, **lines(fa, word)}, {**fb, **lines(fb, word)}
    for key, label in PARA:
        add(key, label, shown(key, fa.get(key)), shown(key, fb.get(key)))
    for key, label in CHAR:
        va, vb = _char_values(before, key), _char_values(after, key)
        add(key, label, " · ".join(va), " · ".join(vb), part=len(va) > 1 or len(vb) > 1)
    return out
