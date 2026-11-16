"""고친 문단이 어떻게 바뀌었나(spec_작업 ② §8 「화면」 — 깃 diff 처럼) — 기준 블록과 지금 블록의 모양 값을 견준다.

순수 함수만(세션·문서를 모른다 — 부르는 쪽 server.edits_detail 이 기준 블록 s.blocks 와 지금 블록 s.doc.blocks() 를 넘긴다).
글의 다름은 화면이 원래 글(state.original)과 지금 글로 그린다 — 여기서는 모양(문단 스타일 · 문단 모양 · 글자 모양 · 목록)만.
값은 화면에 보이는 꼴(「15pt」·「10.4mm」·「양쪽」)로 견준다 — 소수 끝자리만 다른 값은 같은 값.
"""

# 문단 모양 — 블록 format 의 문단 키(hwpx_format · docx_format 의 요약 키)
PARA = (("align", "정렬"), ("indentLeftMm", "왼쪽 여백"), ("firstLineMm", "첫 줄"), ("indentRightMm", "오른쪽 여백"),
        ("spaceBeforePt", "위 간격"), ("spaceAfterPt", "아래 간격"), ("lineSpacingPct", "줄 간격"), ("wordBreak", "줄 나눔"))
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


def changes(before, after):
    """기준 블록 → 지금 블록의 모양 다름 [{key, label, before, after, part?}] — part = 문단 일부 글자만 다름(한쪽에 값이 둘 이상).
    한쪽 블록이 없으면(새 문단 · 지운 문단 · 문단이 아닌 블록이 됨) None."""
    if not before or not after:
        return None
    out = []

    def add(key, label, a, b, part=False):
        if a != b:
            out.append({"key": key, "label": label, "before": a, "after": b, **({"part": True} if part else {})})

    add("style", "문단 스타일", shown("style", before.get("style")), shown("style", after.get("style")))
    add("outlineLevel", "개요 수준", shown("outlineLevel", before.get("outlineLevel")), shown("outlineLevel", after.get("outlineLevel")))
    add("list", "목록", _list(before), _list(after))
    fa, fb = before.get("format") or {}, after.get("format") or {}
    for key, label in PARA:
        add(key, label, shown(key, fa.get(key)), shown(key, fb.get(key)))
    for key, label in CHAR:
        va, vb = _char_values(before, key), _char_values(after, key)
        add(key, label, " · ".join(va), " · ".join(vb), part=len(va) > 1 or len(vb) > 1)
    return out
