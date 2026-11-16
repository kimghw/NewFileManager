"""헤딩 레벨·레터 꼴 추출(spec_hwpx_웹편집 ② §7) — FileMergeManager `app/structure.py`(레벨 판정)·`app/letter_patterns.py`(레터 꼴·둘째 줄)에서
레벨·레터·앞 공백·레터 뒤 공백·둘째 줄 들여쓰기만 옮긴 것(2026-11-08). 앵커·구역·사용자 지정·표 분류는 옮기지 않았다.

- **레벨**(H): 문서 순서로 열린 헤딩 스택 하나 — 고정헤딩(개요 문단 `outlineLevel`)은 제 수준, 문자헤딩(리터럴 「□」「1.」「가.」…, 자동 번호·글머리 `list`,
  판별 모양)은 같은 레터 형제·더 깊은 십진 번호를 닫은 뒤 맨 위 + 1. 표 칸은 표 앞 스택을 이어받고, 칸 안 고정헤딩은 표 뒤에도 남는다.
- **T**(표 칸 깊이): 칸 2개 이상 표의 칸 안 문자헤딩은 H 없이 칸마다 새 스택(칸 맨 앞 = T1). 1칸 표(글상자)는 본문처럼 H.
  FileMergeManager 는 표 분류로 머리 칸을 H 로 빼지만 여기엔 표 분류가 없어 모든 칸이 T.
- **레터 꼴**(`head`): 줄 앞머리 = 앞 공백(`lead`) · 레터 토큰(`letter`) · 레터 뒤 공백(`gap`). `full` = 공백 칸 수까지 적은 꼴(`_2□_1` — `_n` 반각·`＿n` 전각·`⇥n` 탭),
  `core` = 공백 뺀 레터 꼴. 자동 번호·글머리는 레터 = 라벨(한글이 글 앞에 찍는 것), 앞 공백 없음, 뒤 공백 = 글 앞 공백.
- **둘째 줄**(`line2`): 강제 줄 바꿈(U+2028)이면 둘째 줄 글의 꼴, 자동 줄넘김(줄 배치 캐시 2줄 이상)이면 문단 서식의 왼쪽 여백·내어쓰기(mm),
  한 줄이면 서식 값만(둘째 줄이 생기면 따를 규칙).
읽기만 — 문서·블록을 바꾸지 않는다."""
import re

GA = "가나다라마바사아자차카타파하"  # 순서 글자(가. 나. 다. …)

# (유형 키, 패턴) — 순서가 중요: 여러 단 십진 번호가 「N.」 보다 먼저, 처음 맞는 것
_MARKERS = [
    ("제N장", r"제\s*\d+\s*장"),
    ("제N절", r"제\s*\d+\s*절"),
    ("N.N", r"\d{1,2}(?:\.\d{1,2})+(?:\.|(?=\s))"),  # 1.1 / 1.1. / 1.1.1. — 깊이가 실제 키
    ("N.", r"\d{1,2}\.(?!\d)"),
    ("가.", rf"[{GA}]\.(?!\d)"),
    ("N)", r"\d{1,2}\)"),
    ("가)", rf"[{GA}]\)"),
    ("(N)", r"\(\d{1,2}\)"),
    ("(가)", rf"\([{GA}]\)"),
    ("①", r"[①-⑳]"),
    ("□", r"[□■]"),
    ("○", r"[○◦●]"),
    ("o", r"o(?=\s)"),  # ○ 대신 친 영문 「o」 — 따로 유형(한 문서에 둘 다 쓰기도)
    ("ㅇ", r"ㅇ(?=\s)"),  # ○ 대신 친 한글 자모 ㅇ — 「ㅇㅇㅇ」 자리표시는 빠짐
    ("△", r"[△▲]"),
    ("-", r"[-–](?=\s)"),
    ("·", r"[·․•ㆍ]"),
    ("▫", r"▫"),
    ("*", r"\*"),
]
_MARKER_RE = re.compile(r"\s*(?:" + "|".join(f"(?P<m{i}>{p})" for i, (_, p) in enumerate(_MARKERS)) + r")\s*")
_BUILTIN = {k for k, _ in _MARKERS}


def split_marker(text):
    """-> (유형 키, 리터럴 앞머리, 제목). 레터 뒤에 글(제목)이 있어야 한다."""
    text = text or ""
    m = _MARKER_RE.match(text)
    if not m or not text[m.end():].strip():
        return None, None, text.strip()
    kind, prefix = _MARKERS[int(m.lastgroup[1:])][0], m.group(m.lastgroup)
    if kind == "N.N":
        kind = "N" + ".N" * prefix.rstrip(".").count(".")
    return kind, prefix, text[m.end():].strip()


_BARE_BULLETS = [("□", "[□■]"), ("○", "[○◦●]"), ("o", "o"), ("ㅇ", "ㅇ"), ("△", "[△▲]"), ("-", "[-–]"), ("·", "[·․•ㆍ]"), ("▫", "▫"),
                 ("*", r"\*")]
_BARE_RE = re.compile(r"\s*(?:" + "|".join(f"(?P<m{i}>{p})" for i, (_, p) in enumerate(_BARE_BULLETS)) + r")\s*$")


def bare_bullet(text):
    """글머리만 있고 글이 없는 줄(양식의 쓸 자리 「-」·「o」) -> (유형 키, 글머리) | None — 같은 글머리 헤딩으로 쌓는다."""
    m = _BARE_RE.match(text or "")
    return (_BARE_BULLETS[int(m.lastgroup[1:])][0], m.group(m.lastgroup)) if m else None


FOOTNOTE = re.compile(r"^\s*\*+\s*\S")  # 각주 안내 줄 「* 1」 …」·「** …」 — 헤딩 아님


def is_footnote(text):
    return bool(FOOTNOTE.match(text or ""))


def _shape(label):
    """자동 번호 라벨 -> 유형 모양: '2.1.' -> 'N.N.', '다)' -> '가)'."""
    if not label:
        return None
    s = re.sub(r"\d+", "N", label)
    s = re.sub(f"[{GA}]", "가", s)
    return re.sub("[①-⑳]", "①", s)


# ---- 기본 패턴이 놓치는 앞머리 모양(FileMergeManager structure §3-1) ----------------------------------------

_ENCLOSED = {chr(c): lo for lo, hi in ("❶❿", "➀➉", "➊➓", "⑴⒇", "⒈⒛", "⒜⒵", "ⓐⓩ", "ⒶⓏ", "㉠㉭", "㉮㉻")
             for c in range(ord(lo), ord(hi) + 1)}
_ORDINAL_TOKEN = re.compile(r"(?:[IVX]+|[ivx]+|[A-Za-z]|\d{1,2}(?:-\d{1,2})+)[.)]|\d{1,2}(?:-\d{1,2})+|[Ⅰ-Ⅻ]+[.)]?|[ⅰ-ⅻ]+[.)]?")
_GLUED = re.compile(r"[^\w\s(\[<{【〈《「『〔]+(?=[가-힣A-Za-z])")  # 「▶추진 배경」: 레터는 「▶」 만
_NOT_MARKERS = "※\"'“”‘’"  # 참고·인용
_BRACKETS = ("()", "[]", "<>", "{}", "【】", "〈〉", "《》", "「」", "『』", "〔〕")
_LABELS = {"[": "]", "【": "】"}  # 줄 전체가 이 괄호 안이면 라벨 「[1차년도 개발내용]」


def _shape_run(m):
    s = m.group()
    if s.isascii() and s.isdigit():
        return "N"
    if "가" <= s[0] <= "힣":
        return "가"
    if "Ⅰ" <= s[0] <= "Ⅻ" or re.fullmatch("[IVX]+", s):
        return "R"
    if "ⅰ" <= s[0] <= "ⅻ" or re.fullmatch("[ivx]+", s):
        return "r"
    if s.isascii() and s.isalpha():
        return "A" if s[0].isupper() else "a"
    return _ENCLOSED.get(s, s)


def marker_token(text):
    """기본 패턴이 못 덮는 앞머리 -> (모양, 토큰) | None. 토큰 = 첫 공백 앞 토큰(6자 이하)이고 보통 낱말이 아닌 것(기호·괄호 시작, 로마 숫자,
    `A.`/`a)`, `1-1.`, 동그라미 숫자류). 닫히지 않은 괄호·뒤에 글자/숫자가 든 제목이 없는 것은 아님. 줄 전체 [ ]/【 】 = 라벨 「[…]」."""
    text = (text or "").strip()
    if not text or split_marker(text)[0]:
        return None
    close = _LABELS.get(text[0])
    if close and text.endswith(close) and text.count(close) == 1 and any(ch.isalnum() for ch in text):
        return text[0] + "…" + close, text[0]
    glued = _GLUED.match(text)
    tok = glued.group() if glued else text.split(None, 1)[0]
    if len(tok) > 6 or tok[0] in _NOT_MARKERS or not any(ch.isalnum() for ch in text[len(tok):]):
        return None
    if any(o in tok and c not in tok for o, c in _BRACKETS):
        return None
    if tok[0].isalnum() and tok[0] not in _ENCLOSED and not _ORDINAL_TOKEN.fullmatch(tok):
        return None
    return re.sub(r"[0-9]+|[가-힣]+|[Ⅰ-Ⅻ]+|[ⅰ-ⅻ]+|[A-Za-z]+|.", _shape_run, tok), tok


_PAGE_REF = re.compile(r"\S *\t[ .·…]*\d{1,4}\s*$")  # 「1-1. 개요\t7」: 쪽 번호로 끝나는 목차 줄
_CAPTION_RE = re.compile(r"^\s*[<\[(]?\s*(그림|표|Figure|Fig\.|Table)\s*\d", re.I)


def is_caption(p):
    style = (p.get("style") or "").lower()
    return bool(p.get("captionOf") or "caption" in style or "캡션" in style or _CAPTION_RE.match(p.get("text") or ""))


def iter_blocks(blocks):
    """문서 순서의 모든 블록 — 표 칸 안으로(칸 자신도)."""
    for b in blocks:
        yield b
        if b.get("type") == "table":
            for c in b["cells"]:
                yield c
                yield from iter_blocks(c.get("blocks") or [])


def _sibling_lists(blocks):
    yield blocks
    for b in blocks:
        if b.get("type") == "table":
            for c in b["cells"]:
                yield from _sibling_lists(c.get("blocks") or [])


def toc_ids(blocks):
    """목차 문단 id: 쪽 번호 줄·빈 줄·쪽 번호 줄 바로 앞 줄이 이어진 형제 문단 묶음 중 쪽 번호 줄이 3개 이상인 것 — 본문 헤딩을 되풀이하므로 레벨 없음."""
    out = set()
    for items in _sibling_lists(blocks):
        ref = [b.get("type") == "paragraph" and bool(_PAGE_REF.search(b.get("text") or "")) for b in items] + [False]
        run, n = [], 0
        for i, b in enumerate(items + [None]):
            if b and b.get("type") == "paragraph" and (ref[i] or ref[i + 1] or not (b.get("text") or "").strip()):
                run.append(b["id"])
                n += ref[i]
            else:
                out |= set(run) if n >= 3 else set()
                run, n = [], 0
    return out


def _decimal_depth(letter):
    """'N.' -> 1, 'N.N' -> 2, 'N.N.N' -> 3(리터럴 십진 번호), 그 밖 레터 -> 0."""
    return letter.count("N") if re.fullmatch(r"N(?:\.N)*\.?", letter) else 0


def _letter(kind, lst):
    """레터: 자동 번호·글머리 = "list:" + 라벨 모양(리터럴 기호와 다른 레터), 리터럴 = 유형 이름, 판별 모양 = 그 모양."""
    if lst:
        return "list:" + (_shape(lst.get("label")) or lst.get("numFmt") or lst.get("kind") or "")
    return kind[1] if isinstance(kind, tuple) else kind


def marker_shapes(blocks):
    """판별 모양 중 헤딩으로 볼 것(FileMergeManager marker_verdicts 의 자동 판정): 두 번 이상 쓰이고 그 문단 하나라도 위에 다른 헤딩이 있는 모양."""
    groups, above, seen, toc = {}, set(), set(), toc_ids(blocks)
    for p in iter_blocks(blocks):
        if p.get("type") != "paragraph" or is_caption(p) or p["id"] in toc:
            continue
        text, lst = (p.get("text") or "").strip(), p.get("list")
        kind = split_marker(text)[0]
        if mt := not lst and marker_token(text):
            groups[mt[0]] = groups.get(mt[0], 0) + 1
            if seen - {mt[0]}:  # 같은 모양은 제 상위가 아니다
                above.add(mt[0])
            seen.add(mt[0])
        elif p.get("outlineLevel") or lst or kind:
            seen.add(None)
    return {s for s, n in groups.items() if n >= 2 and s in above}


# ---- 레벨 판정 -------------------------------------------------------------------------------------

def levels(blocks, shapes=None):
    """-> {"levels": {id: H}, "fieldLevels": {id: T}, "letters": {id: 레터}, "sources": {id: style|list|marker|shape},
    "parents": {id: 바로 위 헤딩 id | None}, "markers": {id: 리터럴 앞머리}, "maxLevel"}.
    shapes: 헤딩으로 볼 판별 모양(None = marker_shapes 자동 판정)."""
    shapes = marker_shapes(blocks) if shapes is None else set(shapes)
    toc = toc_ids(blocks)
    fields = {c["id"] for t in iter_blocks(blocks) if t.get("type") == "table" and len(t.get("cells") or ()) > 1 for c in t["cells"]}
    found, outline, keys, letters, judged = {}, {}, {}, {}, set()
    for p in iter_blocks(blocks):
        if p.get("type") != "paragraph" or is_caption(p) or p["id"] in toc or is_footnote(p.get("text")):
            continue
        kind, prefix, _ = split_marker(p.get("text"))
        lst = p.get("list")
        if not kind and not lst and (mt := marker_token(p.get("text"))) and mt[0] in shapes:
            kind, prefix = mt[0] if mt[0] in _BUILTIN else ("x", mt[0]), mt[1]
            judged.add(p["id"])
        if not kind and not lst and (bb := bare_bullet(p.get("text"))):  # 글 없는 「-」·「o」 쓸 자리도 그 글머리 헤딩
            kind, prefix = bb
        if prefix:
            found[p["id"]] = prefix
        if p.get("outlineLevel"):
            outline[p["id"]] = p["outlineLevel"]  # 고정헤딩: 레터 없음 — 개요 번호는 레터로 다루지 않는다
            if lst and lst.get("label"):  # docx: 제목 스타일에 번호가 걸린 개요 문단(「1. 서론」) — 웹이 그 라벨을 보이므로 레터로 잰다(hwpx 개요 번호는 list 가 아님)
                letters[p["id"]] = _letter(kind, lst)
        elif kind or lst:
            # 형제 판정 키 = 레터, 자동 list 는 (레터, 수준) — 같은 글머리 글자를 여러 수준에 쓰는 목록은 형제가 아님
            letters[p["id"]] = _letter(kind, lst)
            keys[p["id"]] = ("list", letters[p["id"]], lst.get("level")) if lst else kind
    lv, sources, field_levels, parents = {}, {}, {}, {}

    def push(st, pid, lvl):  # 고정헤딩: 제 수준 이상을 모두 닫는다 -> 부모 id
        while st and st[-1][0] >= lvl:
            st.pop()
        parent = st[-1][1] if st else None
        st.append((lvl, pid))
        return parent

    def stack_letter(st, pid):
        """문자헤딩 pid 를 스택에 쌓은 (레벨, 부모 id): 가장 가까운 고정헤딩 위에서만 같은 레터 형제·더 깊은 십진 번호를 닫고 맨 위 + 1."""
        floor = next((i + 1 for i in range(len(st) - 1, -1, -1) if st[i][1] not in keys), 0)
        dec = _decimal_depth(letters[pid])
        for i in range(floor, len(st)):
            o = st[i][1]
            if keys[o] == keys[pid] or dec and _decimal_depth(letters[o]) > dec:
                del st[i:]
                break
        parent = st[-1][1] if st else None
        st.append((st[-1][0] + 1 if st else 1, pid))
        return st[-1][0], parent

    def place(items, st, cell, out):
        """out += 이 목록(칸 안 포함)의 고정헤딩 id(문서 순) — 표 뒤 본문 스택에도 남는 것."""
        t_st = [] if cell in fields else None  # 표 칸: 칸마다 새 스택, 칸 맨 앞 = T1
        for b in items:
            pid = b["id"]
            if b.get("type") == "table":
                inner = []
                for c in b["cells"]:
                    place(c.get("blocks") or [], list(st), c["id"], inner)  # 칸마다 표 앞 스택을 이어받는다
                for h in inner:  # 칸 안 고정헤딩은 표 뒤에도 「바로 위 헤딩」 — 칸 안 문자헤딩·T 는 안 샌다
                    push(st, h, lv[h])
                out.extend(inner)
            elif b.get("type") != "paragraph":
                continue
            elif pid in outline:
                parents[pid] = push(st, pid, outline[pid])
                lv[pid], sources[pid] = outline[pid], "style"
                out.append(pid)
            elif pid in keys and t_st is not None:
                field_levels[pid], parents[pid] = stack_letter(t_st, pid)
                sources[pid] = "list" if b.get("list") else "shape" if pid in judged else "marker"
            elif pid in keys:
                lv[pid], parents[pid] = stack_letter(st, pid)
                sources[pid] = "list" if b.get("list") else "shape" if pid in judged else "marker"
    place(blocks, [], None, [])
    return {"levels": lv, "fieldLevels": field_levels, "letters": letters, "sources": sources, "parents": parents,
            "markers": found, "maxLevel": max(lv.values(), default=0), "shapes": sorted(shapes)}


# ---- 레터 꼴(FileMergeManager letter_patterns) -------------------------------------------------------

BR = " "
WS = {" ": "_", "\t": "⇥", "　": "＿", " ": "_", "\u2002": "_"}  # U+2002 = 묶음 빈칸(hwpx_doc.SPECIAL)
OPEN = {"(": ")", "[": "]", "<": ">", "{": "}", "【": "】", "〈": "〉", "《": "》", "「": "」", "『": "』", "〔": "〕"}
ENC = {chr(c): lo for lo, hi in ("①⑳", "❶❿", "➀➉", "➊➓", "⑴⒇", "⒈⒛", "⒜⒵", "ⓐⓩ", "ⒶⓏ", "㉠㉭", "㉮㉻") for c in range(ord(lo), ord(hi) + 1)}
MAX_TOK = 6
QUOTES = "‘’“”\"'「『"
SYMBOL_LETTERS = "ㆍ"  # isalnum 이 참인 가운뎃점 꼴 글자
_LEAD = re.compile("[ \t　 \u2002]*")


def _run(m):
    s = m.group()
    if s.isdecimal():
        return "N"
    if "가" <= s[0] <= "힣":
        return "가" if len(s) == 1 and s in GA else "글"  # 「(가)」 순서 글자 / 「(시험)」 낱말
    if "Ⅰ" <= s[0] <= "Ⅻ" or re.fullmatch("[IVX]{2,}", s):
        return "R"
    if "ⅰ" <= s[0] <= "ⅻ" or re.fullmatch("[ivx]{2,}", s):
        return "r"
    if len(s) == 1:
        return "A" if s.isupper() else "a"
    return "W" if s[0].isupper() else "w"


def _tok_shape(s):
    return re.sub(r"[0-9]+|[가-힣]+|[Ⅰ-Ⅻ]+|[ⅰ-ⅻ]+|[A-Za-z]+", _run, s)


def ws_code(s):
    """공백 칸 -> '_3'(반각) '＿1'(전각) '⇥1'(탭) 이어 붙임."""
    out, prev, n = [], None, 0
    for ch in s:
        k = WS.get(ch, "_")
        if k == prev:
            n += 1
        else:
            if prev:
                out.append(f"{prev}{n}")
            prev, n = k, 1
    if prev:
        out.append(f"{prev}{n}")
    return "".join(out)


def _mark(text, i):
    """i 에서 레터 토큰 하나 -> (모양, 다음 i) | None(제목 시작)."""
    ch = text[i]
    m = re.match(r"제\s*\d+\s*([장절])", text[i:])
    if m:
        return f"제N{m.group(1)}", i + m.end()
    if ch in ENC:
        return ENC[ch], i + 1
    if ch.isdecimal():  # isdigit 는 ①·² 도 참
        m = re.match(r"\d+", text[i:])
        j = i + m.end()
        if j < len(text) and text[j].isalpha():  # 「1차년도」·「2026년」 = 글
            return None
        return "N", j
    if ch in GA and i + 1 < len(text) and text[i + 1] in ".)":
        return "가", i + 1
    if "Ⅰ" <= ch <= "Ⅻ":
        return "R", i + 1
    if "ⅰ" <= ch <= "ⅻ":
        return "r", i + 1
    m = re.match(r"([IVX]+|[ivx]+|[A-Za-z])(?=[.)])", text[i:])
    if m:
        s = m.group(1)
        k = ("R" if re.fullmatch("[IVX]+", s) and len(s) > 1 else "r" if re.fullmatch("[ivx]+", s) and len(s) > 1
             else "A" if s.isupper() else "a")
        return k, i + m.end()
    if ch in "oㅇ" and (i + 1 == len(text) or text[i + 1].isspace()):
        return ch, i + 1
    if ch in OPEN:  # 짧은 괄호 토큰(공백 없이 6자 이하) 「(1)」「(가)」「[별첨1]」 — 「(국내 기관)」·「[ ]」 은 아님
        close = OPEN[ch]
        j = text.find(close, i + 1)
        inner = text[i + 1:j] if j > 0 else ""
        if 0 < len(inner) <= 6 and not re.search(r"\s", inner):
            return ch + _tok_shape(inner) + close, j + 1
        return None
    if ch in QUOTES:
        return None
    if ch.isalnum() and ch not in SYMBOL_LETTERS:
        return None
    return ch, i + 1  # 그 밖 기호(□ ○ - · ▶ ⋅ ※ * . ) : 등) 글자 그대로


def skeleton(text):
    """-> {"full", "core", "lead", "letter", "gap", "rest"}: lead = 앞 공백, letter = 레터 토큰 글(사이 공백 포함, 여러 토큰이면 이어서),
    gap = 레터 뒤 공백, full = 공백 칸 수까지 적은 꼴, core = 공백 뺀 레터 꼴('' = 레터 없음), rest = 꼴 뒤 글."""
    text = text or ""
    s = text.strip()
    lead = text[:len(text) - len(text.lstrip())]
    close = {"[": "]", "【": "】"}.get(s[:1])
    if close and s.endswith(close) and s.count(close) == 1:  # 줄 전체 괄호 라벨 「[1차년도 개발내용]」
        return {"full": ws_code(lead) + s[0] + "…" + close, "core": s[0] + "…" + close, "lead": lead, "letter": s[0], "gap": "",
                "rest": s[1:-1]}
    m = _LEAD.match(text)
    full, core, i = [ws_code(m.group())], [], m.end()
    lead, start, end, gap = m.group(), m.end(), None, ""
    while i < len(text) and len(core) < MAX_TOK:
        t = _mark(text, i)
        if not t:
            break
        core.append(t[0])
        full.append(t[0])
        i = t[1]
        m = _LEAD.match(text, i)
        if m.end() > i:
            full.append(ws_code(m.group()))
            if end is None:  # 레터 = 공백 없이 붙은 첫 토큰 묶음(「1.1.」·「(1)」·「□」), 레터 뒤 공백 = 그 바로 뒤 공백
                end, gap = i, m.group()
            i = m.end()
    if end is None:
        end = i if core else start
    return {"full": "".join(full), "core": "".join(core), "lead": lead, "letter": text[start:end], "gap": gap, "rest": text[i:]}


def head_of(p):
    """문단의 앞머리 꼴 — 자동 번호·글머리는 라벨이 레터(한글이 글 앞에 찍음), 글 앞 공백이 레터 뒤 공백."""
    text = p.get("text") or ""
    lst = p.get("list")
    if lst:
        label = lst.get("label") or ""
        gap = text[:len(text) - len(text.lstrip())]
        sk = skeleton(label)
        return {"full": "list:" + sk["full"] + ws_code(gap), "core": ("list:" + sk["core"]) if sk["core"] else "", "lead": "",
                "letter": label, "gap": gap, "rest": text.lstrip(), "auto": True}
    return {**skeleton(text.split(BR, 1)[0]), "auto": False}


def _mm(v):
    return f"{round(float(v) * 2) / 2:g}" if v else "0"


def line2(doc, p):
    """-> {"kind": forced|wrap|single, "leftMm", "firstLineMm", "hangMm", "rule", "sample"}: 강제 줄 바꿈 = 둘째 줄 글의 꼴(rule), 자동 줄넘김 =
    서식 왼쪽 여백·내어쓰기(hangMm = 둘째 줄이 첫 줄보다 들어간 폭 — 내어쓰기면 양수, 들여쓰기면 음수), 한 줄 = 서식 값만."""
    text = p.get("text") or ""
    f = p.get("format") or {}
    left, first = float(f.get("indentLeftMm") or 0), float(f.get("firstLineMm") or 0)
    kind = "내어" if first < 0 else "들여" if first > 0 else "첫줄"
    out = {"leftMm": left, "firstLineMm": first, "hangMm": round(-first, 2) or 0.0,
           "rule": f"왼 {_mm(left)} · {kind} {_mm(abs(first))}" if first else f"왼 {_mm(left)} · 첫줄 0"}
    if BR in text:
        second = text.split(BR, 2)[1]
        return {**out, "kind": "forced", "rule": skeleton(second)["full"] or "0", "sample": second}
    segs = []
    if doc is not None:
        from app.hwpx_doc import LINESEG
        el = doc._ids.get(p["id"])
        la = el.find(LINESEG) if el is not None else None
        segs = list(la) if la is not None else []
    if len(segs) < 2:
        return {**out, "kind": "single", "sample": ""}
    pos = int(segs[1].get("textpos") or 0)
    return {**out, "kind": "wrap", "sample": text[pos:] if pos < len(text) else ""}


def extract(blocks, doc=None):
    """문단마다 헤딩 정보 -> {"rows": {id: {"level", "field", "letter", "source", "parent", "head", "line2", "place"}}, "levels"(levels() 결과)}.
    행은 헤딩(H·T)인 문단만. place = body|box|cell."""
    an = levels(blocks)
    place_of = {}

    def walk(bs, place):
        for b in bs:
            if b.get("type") == "paragraph":
                place_of[b["id"]] = (b, place)
            elif b.get("type") == "table":
                sub = "box" if len(b.get("cells") or ()) == 1 and place == "body" else "cell"
                for c in b.get("cells") or ():
                    walk(c.get("blocks") or [], sub)
    walk(blocks, "body")
    rows = {}
    for pid, (p, place) in place_of.items():
        lvl, fld = an["levels"].get(pid), an["fieldLevels"].get(pid)
        if not lvl and not fld:
            continue
        head = head_of(p) if pid in an["letters"] else {"full": f"H{lvl}", "core": "", "lead": "", "letter": "", "gap": "", "auto": False,
                                                        "rest": p.get("text") or ""}
        rows[pid] = {"level": lvl, "field": fld, "letter": an["letters"].get(pid), "source": an["sources"].get(pid),
                     "parent": an["parents"].get(pid), "head": head, "line2": line2(doc, p), "place": place}
    return {"rows": rows, "levels": an}
