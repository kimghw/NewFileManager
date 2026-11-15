"""표지 서식(spec_서식복사 ② §14 · §16) — 서식 종류 `cover`: 문서 **첫 쪽의 블록 묶음**을 배치 그대로 저장하고 글은 **역할 견본**(「제목」·「기관명」·「날짜」 …)으로 바꾼다.
후보(`find`·`shrink`) · hwpx 운반 문서(`carrier`) · 보기(`view`) · 다른 문서의 맨 앞에 넣기(`insert`). docx 운반 문서는 `style_docx.from_cover`(이 모듈의 `view` 를 읽는다).

- 범위(스크립트 — hwpx·docx 같은 규칙: 두 문서 클래스의 `blocks()` 최상위 블록 꼴이 같다): 처음부터 **다음 쪽이 시작하는 블록 앞까지**(블록의 `pageStart` · 둘째 구역을 여는 `page`).
  그런 표시가 없으면 첫 개요 헤딩(2단계 그래프의 주 사슬 1레벨 문단 — 그래프가 없으면 개요 수준 1 문단)이나 「목차」 문단 앞까지. 블록 40개·표 4개를 넘거나 경계를 못 찾으면 후보를 내지 않는다.
  캡션 문단은 제 표·그림에 딸린 것이라 범위의 블록으로 세지 않는다.
- 부분(part) = 범위 안의 **글이 있는 문단**과 **표**. 빈 문단은 간격으로만 센다(운반 문서에 그대로 옮기고, 보기에서는 다음 부분의 `gapBeforeMm`). 그림은 옮기지 않는다(losses).
- 역할 어림(`ROLES` — LLM 이 고친다: ② §15): 날짜 꼴 = `date` · 가장 큰 글자 = `title` · 「작성자·책임자」 = `person` · 「기관·회사·연구원·대학」 = `org` · 그다음 크기 = `subtitle` · 그 밖 `other`. 표에는 역할이 없다.
- 후보의 글은 **가린 글**이다(`mask` — 「한글 5자」·「날짜」: 성명·과제명이 후보·LLM 으로 그대로 나가지 않게). 운반 문서의 글은 역할 견본(`SAMPLES` — `keep_text` 면 원문 60자).
- **첫 문단**: 운반 문서의 첫 문단(구역 설정 hp:secPr 을 품은 문단)이 곧 표지의 첫 블록이다 — 빈 바탕의 첫 문단을 비운 채 두면 표지 전체가 한 줄 내려간다(2026-11-14 `style_page.carrier` 실측).
  옮긴 첫 블록의 문단 맨 앞에 구역 설정을 옮겨 싣고(`_take_section` — `HwpxDoc.insert_line(before=True)` 와 같은 길) 빈 바탕의 첫 문단은 지운다. 표가 첫 블록이어도 같다(한글 문서도 그렇게 저장한다 — 연구개발계획서 양식).
- 넣기(`insert`)도 같은 길: 표지 블록들을 대상 문서의 첫 문단 뒤에 복사하고 → 구역 설정(과 구역에 딸린 제어: 단·머리말·꼬리말·쪽 번호)을 표지의 첫 문단으로 옮기고 → 원래 첫 문단을 표지 뒤로 옮겨 쪽 나눔(`pageBreak="1"`)을 건다.
  대상 문서의 쪽 설정은 그대로다(표지의 쪽 설정을 입히지 않는다 — 구역을 새로 만들지 않는다)."""
import copy
import re

from app import style_carrier as SC
from app import style_page as SP
from app import table_make as M
from app.hwpx_doc import CAPTION, CTRL, DROP_ON_COPY, LINESEG, PIC, RUN, SECTION_CTRL, SUBLIST, TBL, TC, TR, HwpxDoc, P, _p
from app.hwpx_format import LANG_FONT_KEYS, SUMMARY_KEYS

ROLES = (("title", "제목"), ("subtitle", "부제"), ("org", "기관명"), ("date", "날짜"), ("person", "작성자"), ("label", "라벨"), ("other", "기타"))
SAMPLES = {"title": "제목", "subtitle": "부제", "org": "기관명", "date": "0000. 00. 00.", "person": "작성자", "label": "라벨", "other": "견본 글입니다"}  # 역할 → 견본 글
ROLE_NAME = dict(ROLES)
MAX_BLOCKS, MAX_TABLES = 40, 4  # 표지 범위의 한도(② §14) — 넘으면 후보를 내지 않는다
MASK_MAX, LINE_PARTS = 80, 6    # 가린 글 길이 · 한 줄 요약에 싣는 부분 수
PT_MM = 25.4 / 72
LINE_PCT = 160                  # 줄 간격을 못 읽은(퍼센트가 아닌) 빈 문단의 높이 어림 — 한글 기본 160%
SECPR = _p("secPr")
IMAGE_NOTE = "그림은 옮기지 않았습니다"
AUTO_NOTE = "자동 번호 문단이 있습니다 — 넣는 문서의 번호 설정을 따릅니다"
SHAPE_NOTE = "문단 안 그리기 개체·수식은 옮기지 않았습니다"

_TOC = re.compile(r"\s*(?:목\s*차|차\s*례|contents|table\s+of\s+contents)\s*", re.I)
# 날짜 꼴 — 「2026. 3.」·「2026. 3. 15.」·「2026년 3월」·「0000년 0월」·「2026.  .  .」(빈 자리)·「26년 3월」. 해(4자리 · 「년」 앞 2자리 · 「0000」) + 구분 + 달·날(없어도 된다)
_Y = r"(?<!\d)(?:(?:19|20)\d{2}|[0Oo○]{4}|\d{2}(?=\s*년))"
_N = r"(?:\d{1,2}|[0Oo○]{1,2})"
_DATE = re.compile(rf"{_Y}\s*(?:년|[.\-/])\s*(?P<m>{_N})?\s*(?P<s>월|[.\-/])?\s*(?:{_N})?\s*(?:일|\.)?")
_ORG = re.compile(r"기관|회사|연구원|연구소|대학|㈜|\(주\)")
_WHO = re.compile(r"작성자|책임자|성명|제출자|담당자")
_WROTE = re.compile(r"작성")
_TOKEN = re.compile(r"[가-힣ㄱ-ㅣ]+|[A-Za-z]+|\d+|[一-鿿]+|\s+|.", re.S)


# ---- 가린 글 · 역할 어림 ----------------------------------------------------------------------------------------------

def _note(losses, *texts) -> None:
    for t in texts:
        if t and t not in losses:
            losses.append(t)


def _is_date(text) -> bool:
    """날짜 줄인가 — 날짜 꼴이 있고 그 밖의 글자가 없거나(「2026. 3.」·「2026년」), 달까지 적힌 날짜에 짧은 말(6자까지 — 「작성일: 2026. 3. 15.」)만 붙은 줄.
    「2026년도 연구개발계획서」 처럼 해만 있고 다른 글이 붙은 줄은 날짜가 아니다."""
    text = str(text or "")
    m = _DATE.search(text)
    if not m:
        return False
    rest = len(re.sub(r"[\W_]", "", text[:m.start()] + text[m.end():]))
    return rest == 0 or (rest <= 6 and bool(m.group("m") or m.group("s")))


def _mask(text) -> str:
    """글을 꼴로 가린 것(이 모듈의 것 — `style_extract.mask` 가 없을 때): 날짜 줄 = 「날짜」 · 그 밖은 낱말마다 「한글 5자」·「영문 3자」·「숫자 4자리」·「한자 2자」, 문장 부호·기호는 그대로."""
    if _is_date(text):
        return "날짜"
    out = []
    for tok in _TOKEN.findall(text):
        c = tok[0]
        if tok.isspace():
            continue
        if "가" <= c <= "힣" or "ㄱ" <= c <= "ㅣ":
            out.append(f"한글 {len(tok)}자")
        elif c.isascii() and c.isalpha():
            out.append(f"영문 {len(tok)}자")
        elif c.isdigit():
            out.append(f"숫자 {len(tok)}자리")
        elif "一" <= c <= "鿿":
            out.append(f"한자 {len(tok)}자")
        elif c.isalnum():
            out.append("글자 1자")
        else:
            out.append(tok)
    return " ".join(out)[:MASK_MAX]


def mask(text) -> str:
    """후보에 싣는 가린 글 — `style_extract.mask`(② §16 — LLM 에 보내는 글과 같은 규칙)가 있으면 그것, 없거나 실패하면 이 모듈의 `_mask`. 빈 글은 ""."""
    t = str(text or "").strip()
    if not t:
        return ""
    try:
        from app import style_extract  # 함수 안에서 — style_extract 가 이 모듈을 읽어도 서로 물리지 않게
        fn = getattr(style_extract, "mask", None)
        got = fn(t) if callable(fn) else None
        if isinstance(got, str) and got.strip():
            return got[:MASK_MAX]
    except Exception:  # noqa: BLE001 — 가리는 길이 막혀도 원문을 내보내지 않는다(아래 제 것으로)
        pass
    return _mask(t)


def _roles(items) -> list[str]:
    """글 부분들(문서 차례 — `[{"text", "sizePt"}]`)의 역할 어림 → 역할 코드 목록(같은 차례). 차례대로 본다:
    날짜 꼴 → `date` · (크기가 둘 이상일 때) 가장 큰 글자 → `title` · 「작성자·책임자·성명·제출자·담당자」 → `person` · 「기관·회사·연구원·연구소·대학」 → `org` · 「작성」 → `person` ·
    (크기가 한 가지뿐일 때) 낱말에 안 걸린 첫 줄 → `title` · 둘째로 큰 크기의 첫 줄 → `subtitle` · 그 밖 `other`."""
    sizes = sorted({i["sizePt"] for i in items if i.get("sizePt")}, reverse=True)
    top, second = (sizes[0] if sizes else None), (sizes[1] if len(sizes) > 1 else None)
    out, titled, sub = [], False, False
    for it in items:
        text, size = str(it.get("text") or ""), it.get("sizePt")
        word = "person" if _WHO.search(text) else "org" if _ORG.search(text) else "person" if _WROTE.search(text) else None
        if _is_date(text):
            role = "date"
        elif second is not None and size == top:
            role = "title"
        elif word:
            role = word
        elif second is None and not titled:
            role = "title"
        elif second is not None and size == second and not sub:
            role, sub = "subtitle", True
        else:
            role = "other"
        titled = titled or role == "title"
        out.append(role)
    return out


def _size_of(b):
    """문단 블록의 글자 크기(pt) — 글자 모양이 여럿이면(`runs`) 글이 가장 긴 조각의 것, 아니면 문단의 것."""
    runs = [r for r in b.get("runs") or [] if isinstance(r, dict)]
    if runs:
        size = (max(runs, key=lambda r: len(str(r.get("text") or "").strip())).get("format") or {}).get("sizePt")
        if size:
            return size
    return (b.get("format") or {}).get("sizePt")


def _texted(b) -> bool:
    return b.get("type") == "paragraph" and bool(str(b.get("text") or "").strip())


def _scan(blocks) -> list[dict]:
    """범위의 최상위 블록들 → 후보의 parts(글이 있는 문단 · 표 — 문서 차례). 글은 가린 글, 표의 sample 은 크기 글."""
    texts = [b for b in blocks if _texted(b)]
    role = dict(zip((b["id"] for b in texts), _roles([{"text": b["text"], "sizePt": _size_of(b)} for b in texts])))
    out = []
    for b in blocks:
        if b["id"] in role:
            out.append({"block": b["id"], "type": "text", "role": role[b["id"]], "sample": mask(b["text"]), "sizePt": _size_of(b), "align": (b.get("format") or {}).get("align")})
        elif b.get("type") == "table":
            rows, cols = b.get("nRows") or 0, b.get("nCols") or 0
            out.append({"block": b["id"], "type": "table", "role": None, "sample": f"표 {rows}행 × {cols}열", "sizePt": None, "align": b.get("align"), "rows": rows, "cols": cols})
    return out


def _signals(parts, body_pt, own) -> dict:
    """표지 신호(② §14) — `bigTitle` 가장 큰 글자가 문서 본문보다 큰가 · `centered` 가운데 정렬 문단이 있는가 · `ownSection` 범위가 구역 하나를 다 차지하는가(범위 뒤가 새 구역) ·
    `tableOnly` 범위의 내용이 표 하나뿐인가(양식의 표지 표) · `maxSizePt`·`bodySizePt` 견준 두 크기."""
    texts = [p for p in parts if p["type"] == "text"]
    top = max((p["sizePt"] for p in texts if p.get("sizePt")), default=None)
    return {"bigTitle": bool(top and body_pt and top > body_pt), "centered": any(p.get("align") == "center" for p in texts), "ownSection": bool(own),
            "tableOnly": len(parts) == 1 and parts[0]["type"] == "table", "maxSizePt": top, "bodySizePt": body_pt}


def _line(parts) -> str:
    """후보의 한 줄 — 「제목 22pt · 부제 16pt · 날짜 14pt · 표 2행 × 2열」(원문 글은 싣지 않는다)."""
    out = []
    for p in parts[:LINE_PARTS]:
        if p["type"] == "table":
            out.append(p["sample"])
        else:
            out.append(ROLE_NAME.get(p["role"], "기타") + (f" {p['sizePt']:g}pt" if isinstance(p.get("sizePt"), (int, float)) else ""))
    return " · ".join(out) + (f" 외 {len(parts) - LINE_PARTS}" if len(parts) > LINE_PARTS else "")


# ---- 후보 ----------------------------------------------------------------------------------------------------------

def _fallback_cut(blocks, graph):
    """쪽 표시가 없는 문서의 경계 — 첫 개요 헤딩(그래프 v2 의 주 사슬(`templates[].kind == "main"`) 1레벨 노드의 문단 · 그래프에서 못 찾으면 개요 수준 1 문단)과
    「목차」 문단 가운데 먼저 나오는 블록의 차례 | None."""
    at = {b["id"]: i for i, b in enumerate(blocks)}
    cuts = []
    g = graph if isinstance(graph, dict) else {}
    main = next((t for t in g.get("templates") or [] if isinstance(t, dict) and t.get("kind") == "main"), None)
    nodes = g.get("nodes") if isinstance(g.get("nodes"), list) else []
    if main is not None:
        cuts += [at[n["para"]] for n in nodes if isinstance(n, dict) and n.get("level") == 1 and n.get("tplNo") == main.get("id") and n.get("para") in at]
    if not cuts:
        cuts += [i for i, b in enumerate(blocks) if b.get("type") == "paragraph" and b.get("outlineLevel") == 1][:1]
    cuts += [i for i, b in enumerate(blocks) if b.get("type") == "paragraph" and _TOC.fullmatch(str(b.get("text") or ""))][:1]
    return min(cuts) if cuts else None


def find(doc, graph=None):
    """표지 후보(② §14 — `HwpxDoc`·`DocxDoc`) → `{"key": "cover", "blocks": [id…], "end": 끝 블록 id, "signals": {…}, "parts": [{"block", "type": "text" | "table", "role",
    "sample"(가린 글), "sizePt", "align", "rows"?, "cols"?}], "sample": 한 줄}` | None(경계를 못 찾음 · 한도를 넘음 · 범위에 글도 표도 없음). 문서는 안 바뀐다.
    blocks = 범위의 최상위 블록 id(빈 문단·그림 포함 — 캡션 제외), graph = 2단계 그래프(없으면 개요 수준·「목차」 로만 경계를 찾는다)."""
    blocks = [b for b in doc.blocks() if not b.get("captionOf")]
    cut = next((i for i, b in enumerate(blocks) if i and (b.get("pageStart") or "page" in b)), None)
    own = cut is not None and "page" in blocks[cut]
    if cut is None:
        cut = _fallback_cut(blocks, graph)
    if not cut:
        return None
    rng = blocks[:cut]
    if len(rng) > MAX_BLOCKS or sum(1 for b in rng if b.get("type") == "table") > MAX_TABLES:
        return None
    parts = _scan(rng)
    if not parts:
        return None
    body = SP.body_of(blocks[cut:]) or SP.body_of(blocks)
    body_pt = ((body or {}).get("format") or {}).get("sizePt")
    return {"key": "cover", "blocks": [b["id"] for b in rng], "end": rng[-1]["id"], "signals": _signals(parts, body_pt, own), "parts": parts, "sample": _line(parts)}


def shrink(cand, end):
    """후보의 범위를 블록 end 까지 줄인 새 후보(② §15 — LLM·사람이 범위를 **줄이는** 쪽만) | None(end 가 범위 밖 · 줄이면 글도 표도 안 남음). 역할 어림은 그대로 두고 신호·한 줄만 다시 낸다."""
    blocks = list((cand or {}).get("blocks") or []) if isinstance(cand, dict) else []
    if end not in blocks:
        return None
    keep = blocks[:blocks.index(end) + 1]
    parts = [dict(p) for p in cand.get("parts") or [] if p.get("block") in keep]
    if not parts:
        return None
    old = cand.get("signals") if isinstance(cand.get("signals"), dict) else {}
    own = bool(old.get("ownSection")) and len(keep) == len(blocks)
    return {**cand, "blocks": keep, "end": end, "signals": {**old, **_signals(parts, old.get("bodySizePt"), own)}, "parts": parts, "sample": _line(parts)}


# ---- 운반 문서 --------------------------------------------------------------------------------------------------------

def _fmt(summary) -> dict:
    """서식 요약에서 형식 중립 값만(`SUMMARY_KEYS` — None 은 뺌)."""
    return {k: v for k, v in (summary or {}).items() if k in SUMMARY_KEYS and v is not None}


def _take_section(doc, old, new) -> int:
    """문단 old 가 품은 구역 설정(hp:secPr)과 구역에 딸린 제어(단·머리말·꼬리말·쪽 번호 — `SECTION_CTRL` 만 든 hp:ctrl)를 문단 new 의 **맨 앞 새 런**으로 옮긴다 → 옮긴 수.
    `HwpxDoc.insert_line(before=True)` 가 구역 첫 문단 위로 줄을 넣을 때와 같은 것을 옮긴다. 새 런의 글자 모양은 new 의 것(그 문단의 줄 높이·서식 요약이 안 바뀌게).
    두 문단의 줄 배치 캐시는 지운다(한글이 다시 배치)."""
    parts = [x for r in old.iterchildren(RUN) for x in r if x.tag == SECPR or (x.tag == CTRL and len(x) and all(c.tag in SECTION_CTRL for c in x))]
    if not parts:
        return 0
    run = new.makeelement(RUN, {"charPrIDRef": doc._char_id(new)})
    new.insert(0, run)
    for x in parts:
        run.append(x)  # lxml: 옮김
    for p in (old, new):
        for ls in p.findall(LINESEG):
            p.remove(ls)
    doc._touch(new)
    return len(parts)


def _fonts(cdoc) -> list[str]:
    """표지 운반 문서가 쓰는 글꼴 이름 — `style_carrier.fonts_of` 와 같되 첫 문단부터(표지의 첫 블록이 첫 문단이다)."""
    names = set()
    for p in cdoc._sections[0].iterchildren(P):
        for r in p.iter(RUN):
            s = cdoc._char_summary(cdoc._defs["charPr"].get(r.get("charPrIDRef")))
            names.update(s.get(k) for k in ("font", *LANG_FONT_KEYS))
    return sorted(n for n in names if n)


def _docx_page(doc):
    """`DocxDoc` 의 **첫 구역** 쪽 설정(page 꼴) | None — 표지는 첫 구역에 있다(`style_page.of_docx` 는 본문 글이 가장 많은 구역을 고른다: ② §15)."""
    w = SP.W
    sect = next((s for p in doc._body.iterchildren(w + "p") if (s := p.find(f"{w}pPr/{w}sectPr")) is not None), None)
    return SP._docx_page(sect if sect is not None else doc._body.find(w + "sectPr"))


def _para_from_hwpx(cdoc, anchor, src, b, sample, keep_text, like, losses) -> str:
    """hwpx 원본의 문단 하나를 anchor 뒤에 옮긴다(`style_carrier.from_paras` 의 방식: 복사 → 쪽·단 나눔 끔 → 개체 뺌 → 글 조각만 남김 → 글을 견본으로) → 새 문단 id.
    sample 이 빈 글 = 빈 문단(간격) — 모양째 그대로 옮긴다. keep_text 면 딸린 내용도 그대로 두고 글만 60자로 줄인다(60자 안이면 그대로)."""
    pid = b["id"]
    p = src._ids.get(pid)
    if p is None or p.tag != P or not src._attached(p):
        raise ValueError("표지의 문단이 지금 문서에 없습니다")
    own = copy.deepcopy(p)  # 옮겨질 것만(표·그림은 따로 블록 · 구역 설정은 복사가 뺀다) — 거기서 닿는 정의를 원본에서 본다
    for o in [o for r in own.iterchildren(RUN) for o in r if o.tag in (TBL, PIC)] + list(own.iter(*DROP_ON_COPY)):
        if o.getparent() is not None:
            o.getparent().remove(o)
    SC._need_refs(src, [own], what="원본 문서", did="표지 서식으로 저장하지")
    _note(losses, *[x for x in SC._copy_losses(src, p) if x != SC.STYLE_NOTE])
    h = src._heading(p)
    if sample and h is not None and h.get("type") in ("OUTLINE", "NUMBER", "BULLET"):
        _note(losses, AUTO_NOTE)
    new = cdoc.insert_after(anchor, [{"kind": "copy", "srcId": pid}], src=src)[0]
    el = cdoc._ids[new]
    SC._no_break(el)
    if SC._strip_objects(cdoc, el):
        _note(losses, SHAPE_NOTE)
    text = src._text(p)
    if not sample or not keep_text:
        SC._scrub(cdoc, el)  # 글 조각만 — 각주·필드·숨은 설명·책갈피는 안 따라온다
    if sample and (not keep_text or len(text) > SC.SAMPLE_MAX):
        SC.put_text(cdoc, el, "", text[:SC.SAMPLE_MAX] if keep_text else sample, 0)
    cdoc._touch(el)
    return new


def _para_from_spec(cdoc, anchor, src, b, sample, keep_text, like, losses) -> str:
    """docx 원본의 문단 하나를 서식 요약으로 다시 짓는다(`style_carrier.from_text_spec` 의 방식: 빈 바탕의 평범한 문단에서 출발해 `derive_format` → `apply_format`) → 새 문단 id."""
    new = cdoc.insert_after(anchor, [{"kind": "paragraph", "text": sample, "templateId": like}])[0]
    SC._no_break(cdoc._ids[new])
    cdoc.apply_format([new], cdoc.derive_format(cdoc.get_format(new), SC._clean_format(b.get("format"))))
    return new


def _table_from_hwpx(cdoc, anchor, src, b, keep_text, losses):
    """hwpx 원본의 표 하나를 anchor 뒤에 옮긴다 — `style_carrier.from_table` 과 같은 규칙(host 문단째 복사 · 캡션·칸 안 표·그림은 뺌 · keep_text 가 아니면 라벨 칸(`label_cells`)만
    보이는 글 그대로, 나머지 칸은 견본 · 띠 수 = `table_make.roles_of` · 표지 쪽의 글 폭보다 넓으면 줄임) → (새 표 id, {rows, cols, bands, labels})."""
    tid = b["id"]
    tbl = src._ids.get(tid)
    if tbl is None or tbl.tag != TBL or not src._attached(tbl):
        raise ValueError("표지의 표가 지금 문서에 없습니다")
    own = copy.deepcopy(tbl)  # 옮긴 뒤에도 남을 것만 — 거기서 닿는 정의를 원본에서 본다
    for cap in own.findall(CAPTION):
        own.remove(cap)
    for p in (p for tr in own.iterchildren(TR) for tc in tr.iterchildren(TC) if (sub := tc.find(SUBLIST)) is not None for p in sub.iterchildren(P)):
        SC._strip_objects(src, p)
    SC._need_refs(src, [own], shallow=[src._host(tbl), tbl.getparent()], what="원본 문서", did="표지 서식으로 저장하지")
    _note(losses, *SC._copy_losses(src, tbl))
    new = cdoc.insert_after(anchor, [{"kind": "copy", "srcId": tid}], src=src)[0]
    ctbl = cdoc._ids[new]
    SC._no_break(cdoc._host(ctbl))
    for cap in ctbl.findall(CAPTION):
        ctbl.remove(cap)
        _note(losses, "표 캡션은 옮기지 않았습니다")
    if not keep_text:
        for note in ctbl.findall(_p("shapeComment")):  # 개체 설명 글(보이지 않는 글)
            ctbl.remove(note)
    cells = [tc for tr in ctbl.iterchildren(TR) for tc in tr.iterchildren(TC)]
    nested, emptied = 0, set()  # 뺀 개체 수 · 개체만 들었다가 빈 문단
    for p in (p for tc in cells if (sub := tc.find(SUBLIST)) is not None for p in sub.iterchildren(P)):
        had_text = bool(cdoc._text(p).strip())
        n = SC._strip_objects(cdoc, p)
        nested += n
        if n and not had_text:
            emptied.add(p)
    if nested:
        _note(losses, f"칸 안 표·그림 {nested}개는 옮기지 않았습니다(칸은 글만)")
    cdoc._touch(ctbl)
    block = cdoc.table_block(new)
    rows, cols = block["nRows"], block["nCols"]
    bands = M.clean_roles(None, rows, cols, default=M.roles_of(block["cells"], rows, cols))
    labels = SC.label_cells(block["cells"], bands, rows) | _form_labels(block["cells"])
    if not keep_text:
        for c in block["cells"]:
            if (c["row"], c["col"]) in labels:
                SC._plain_cell(cdoc, cdoc._ids[c["id"]], emptied)  # 라벨 — 보이는 글만 같은 모양으로 다시 쓴다
                continue
            cdoc._blank_cell(cdoc._ids[c["id"]])
            if text := SC.sample_of(c["text"]):
                cdoc.set_text(c["id"], text)
        cdoc._touch(ctbl)
    was = sum(cdoc._tsizes(*cdoc._tgrid(ctbl)[1:])[1]) * 25.4 / 7200
    if SC.fit_width(cdoc, new):
        _note(losses, f"표 폭 {was:.0f}mm 를 표지 쪽의 글 폭에 맞춰 줄였습니다(열 폭 비율은 그대로)")
    return new, {"rows": rows, "cols": cols, "bands": bands, "labels": [list(rc) for rc in sorted(labels)]}


def _table_from_spec(cdoc, anchor, src, b, keep_text, losses):
    """docx 원본의 표 하나를 표 명세로 다시 짓는다 — `spec_of_block` → `style_carrier.from_table_spec`(따로 지은 작은 운반 문서)의 표를 이 운반 문서로 복사한다
    (같은 빈 바탕에서 나온 정의라 그대로 겹친다) → (새 표 id, {rows, cols, bands, labels})."""
    data, info = SC.from_table_spec(SC.spec_of_block(b), keep_text)
    td = SC.doc(data)
    new = cdoc.insert_after(anchor, [{"kind": "copy", "srcId": SC.table_id(td)}], src=td)[0]
    SC._no_break(cdoc._host(cdoc._ids[new]))
    _note(losses, *(info.get("losses") or []))
    if SC.fit_width(cdoc, new):
        _note(losses, "표를 표지 쪽의 글 폭에 맞춰 줄였습니다(열 폭 비율은 그대로)")
    return new, {"rows": info["rows"], "cols": info["cols"], "bands": info["bands"], "labels": info.get("labels") or []}


def _form_labels(cells) -> set:
    """표지의 양식 표에서 글을 남길 칸 (행, 열) — **음영 칸**의 글(자료처럼 보이는 글은 뺌 · 표 전체가 음영이면 표시가 아니다).
    표지 표는 머리 띠가 아니라 흩어진 음영 칸이 라벨이다(실측 2026-11-14: 연구개발계획서 양식의 표지 표 49×30 — 띠 규칙(`style_carrier.label_cells`)만 쓰면
    「중앙행정기관명」·「연구개발과제명」 같은 라벨이 모두 견본 「가나다」 가 되어 무엇의 표지인지 알 수 없다). 음영 없는 칸(채우는 자리)은 전처럼 견본으로."""
    cells = list(cells)
    if not cells or all(c.get("shaded") for c in cells):
        return set()
    return {(c["row"], c["col"]) for c in cells if c.get("shaded") and (c.get("text") or "").strip() and not SC.data_like(c["text"].strip())}


def carrier(src, block_ids, roles=None, keep_text=False):
    """표지의 hwpx 운반 문서(② §14) → (바이트, info `{"page", "parts": [{"key", "type": "text" | "table", "role", "sample", "format" | "rows"·"cols"(+ "bands"·"labels")}], "fonts", "losses"}`).
    src = `HwpxDoc`(블록을 정의째 옮긴다 — `insert_after(copy, src=)`) | `DocxDoc`(정의를 옮길 수 없어 서식 요약·표 명세로 다시 짓는다). src 는 안 바뀐다.
    block_ids = 표지 범위의 최상위 블록 id 들(`find(...)["blocks"]` — 문서 차례로 옮긴다) · roles = `{블록 id: 역할 코드}`(없거나 모르는 코드는 스크립트 어림) · keep_text = 원문 그대로(문단은 60자).
    빈 바탕에 차례대로: 글 문단 = 그 모양에 역할 견본 글(`SAMPLES`) · 빈 문단 = 그대로(간격) · 표 = 표 서식과 같은 규칙 · 그림 = 뺌(losses). 쪽 설정 = 원본 첫 구역의 것.
    끝에 구역 설정을 표지의 첫 블록 문단으로 옮기고 빈 바탕의 첫 문단을 지운다(모듈 설명 「첫 문단」 — 한 줄 밀림 없음). parts 의 key = 글·표 부분의 차례(p1·p2…)."""
    ids = {i for i in block_ids if isinstance(i, str)} if isinstance(block_ids, (list, tuple)) else set()
    rng = [b for b in src.blocks() if not b.get("captionOf") and b["id"] in ids]
    if not ids or len(rng) != len(ids):
        raise ValueError("표지로 저장할 블록이 지금 문서에 없습니다")
    guess = {p["block"]: p["role"] for p in _scan(rng)}
    if not guess:
        raise ValueError("표지에 옮길 글·표가 없습니다")
    roles = roles if isinstance(roles, dict) else {}
    hwpx = isinstance(src, HwpxDoc)
    put_para, put_table = (_para_from_hwpx, _table_from_hwpx) if hwpx else (_para_from_spec, _table_from_spec)
    losses = [] if hwpx else [SC.SPEC_NOTE]
    cdoc, first, plain = SC.open_base()
    page = SP.read(src) if hwpx else _docx_page(src)
    if page is None:
        page = SP.read(cdoc)
        _note(losses, "원본의 쪽 설정을 읽지 못해 빈 바탕(A4 세로)의 쪽 설정입니다")
    else:
        SP.set_page(cdoc, page)  # 표 폭 맞춤(fit_width)이 표지 쪽의 글 폭을 보게 먼저
    like = cdoc._id(next(cdoc._ids[plain].iter(P)))
    anchor, parts, images = first, [], 0
    for b in rng:
        if b["type"] == "image":
            images += 1
        elif b["type"] == "table":
            anchor, got = put_table(cdoc, anchor, src, b, keep_text, losses)
            parts.append({"key": f"p{len(parts) + 1}", "type": "table", "role": None, "sample": "", **got})
        elif b["type"] == "paragraph":
            text = str(b.get("text") or "")
            role = roles[b["id"]] if roles.get(b["id"]) in ROLE_NAME else guess.get(b["id"], "other")
            sample = (text[:SC.SAMPLE_MAX] if keep_text else SAMPLES[role]) if text.strip() else ""
            anchor = put_para(cdoc, anchor, src, b, sample, keep_text, like, losses)
            if sample:
                el = cdoc._ids[anchor]
                parts.append({"key": f"p{len(parts) + 1}", "type": "text", "role": role, "sample": cdoc._text(el)[:SC.SAMPLE_MAX],
                              "format": _fmt(cdoc._summary(el.get("paraPrIDRef"), SC.body_char(cdoc, el)))})
    if images:
        _note(losses, f"{IMAGE_NOTE}({images}개)")
    cdoc.delete_blocks(plain, plain)
    head = cdoc._ids[first]
    lead = next(head.itersiblings(P), None)
    if lead is None:
        raise ValueError("표지에 옮길 글·표가 없습니다")
    _take_section(cdoc, head, lead)  # 구역 설정을 표지의 첫 블록 문단으로 — 빈 첫 문단을 남기면 표지가 한 줄 내려간다
    cdoc.delete_blocks(first, first)
    SC._drop_unused_bins(cdoc)
    SC._need_refs(cdoc, what="표지 서식")
    return cdoc.save(), {"page": page, "parts": parts, "fonts": _fonts(cdoc), "losses": losses}


# ---- 보기 ----------------------------------------------------------------------------------------------------------

def _line_mm(b) -> float:
    """빈 문단 하나가 차지하는 높이의 어림(mm) — 글자 크기 × 줄 간격(퍼센트가 아니면 160%) + 문단 위·아래 간격. 문단 끝 표시가 더 크면 그 크기(`endSizePt`)."""
    f = b.get("format") or {}
    size = b.get("endSizePt") or f.get("sizePt") or 10
    return (size * (f.get("lineSpacingPct") or LINE_PCT) / 100 + (f.get("spaceBeforePt") or 0) + (f.get("spaceAfterPt") or 0)) * PT_MM


def view(carrier: bytes, meta: dict) -> dict:
    """표지 서식의 보기(② §14 · 끝점 `GET /api/styles/{sid}` · 견본 그림 · docx 운반 문서가 읽는다) →
    `{"page", "parts": [{"type": "text", "key", "role", "sample", "format", "gapBeforeMm"} | {"type": "table", "key", "spec", "gapBeforeMm"}]}`.
    운반 문서를 읽어 부분마다: 글 = 지금 글(견본)·서식 요약 · 표 = 표 명세(`style_carrier.spec_of_block` — 띠 수는 meta 의 것). 역할은 meta.parts 의 같은 key(차례) 것 — 없으면 `other`.
    `gapBeforeMm` = 그 부분 앞의 빈 문단들이 차지하는 높이의 어림(`_line_mm`). page = meta.page(없으면 운반 문서의 쪽 설정). 못 열면 ValueError."""
    d = SC.doc(carrier)
    meta = meta if isinstance(meta, dict) else {}
    by = {p.get("key"): p for p in meta.get("parts") or [] if isinstance(p, dict)}
    parts, gap = [], 0.0
    for b in d.blocks():
        if b.get("captionOf") or b["type"] not in ("paragraph", "table"):
            continue
        if b["type"] == "paragraph" and not b["text"].strip():
            gap += _line_mm(b)
            continue
        key = f"p{len(parts) + 1}"
        m = by.get(key) or {}
        if b["type"] == "table":
            spec = SC.spec_of_block(d.table_block(b["id"]))
            if isinstance(m.get("bands"), dict):
                spec["bands"] = M.clean_roles(m["bands"], spec["rows"], spec["cols"])
            parts.append({"type": "table", "key": key, "spec": spec, "gapBeforeMm": round(gap, 2)})
        else:
            parts.append({"type": "text", "key": key, "role": m.get("role") if m.get("role") in ROLE_NAME else "other", "sample": b["text"],
                          "format": _fmt(b.get("format")), "gapBeforeMm": round(gap, 2)})
        gap = 0.0
    return {"page": meta.get("page") if isinstance(meta.get("page"), dict) else SP.read(d), "parts": parts}


# ---- 넣기 ----------------------------------------------------------------------------------------------------------

def insert(doc, cdoc) -> dict:
    """대상 `HwpxDoc` 의 **맨 앞**에 운반 문서 cdoc(`style_carrier.doc(...)` 로 연 것 — 바이트도 받는다)의 표지 블록들을 넣는다(② §14 「적용」 — 구조 편집의 run() 안에서 부른다)
    → `{"blocks": [새 블록 id…], "after": 표지 바로 뒤 블록 id(= 원래 첫 블록)}`. 못 넣으면 ValueError.
    ① 표지의 최상위 문단·표를 대상의 첫 문단 뒤에 복사(`insert_after(copy, src=cdoc)` — 쓰는 정의만 따라온다 · 운반 문서의 구역 설정은 복사가 뺀다)
    ② 대상 첫 문단의 구역 설정과 구역 제어(단·머리말·꼬리말·쪽 번호)를 표지의 첫 문단으로 옮긴다(`_take_section` — secPr 는 늘 구역 첫 문단에 있어야 한다)
    ③ 원래 첫 문단(제 표·그림째)을 표지 뒤로 옮기고 `pageBreak="1"` — 다음 쪽에서 시작한다(블록의 `pageStart` 가 이 속성에서 나온다: `hwpx_layout.annotate_pages`).
    넣은 표는 대상 쪽의 글 폭보다 넓으면 줄인다. 대상의 쪽 설정·머리말은 그대로다(표지 쪽에도 대상의 머리말·쪽 번호가 놓인다)."""
    if isinstance(cdoc, (bytes, bytearray)):
        cdoc = SC.doc(bytes(cdoc))
    if not isinstance(doc, HwpxDoc) or not isinstance(cdoc, HwpxDoc):
        raise ValueError("표지 넣기는 hwpx 문서에만 됩니다")
    items = [{"kind": "copy", "srcId": b["id"]} for b in cdoc.blocks() if not b.get("captionOf") and b["type"] in ("paragraph", "table")]
    if not items:
        raise ValueError("표지 서식에 넣을 글·표가 없습니다")
    tops = doc.blocks()
    head = next(doc._sections[0].iterchildren(P), None) if doc._sections else None
    if head is None or not tops or doc._host(doc._ids[tops[0]["id"]]) is not head:
        raise ValueError("문서의 첫 문단을 찾지 못해 표지를 넣지 못했습니다")
    after = tops[0]["id"]
    SC._need_refs(cdoc, what="표지 서식", did="넣지")
    new = doc.insert_after(after, items, src=cdoc)
    lead, last = doc._host(doc._ids[new[0]]), doc._host(doc._ids[new[-1]])
    _take_section(doc, head, lead)
    last.addnext(head)  # lxml: 옮김 — 원래 첫 문단(제 표·그림째)이 표지 바로 뒤로
    for ls in list(head.iter(LINESEG)):  # 쪽 안 자리가 바뀜 — 한글이 다시 배치(move_blocks 와 같다)
        ls.getparent().remove(ls)
    head.set("pageBreak", "1")
    for i in new:
        if doc._ids[i].tag == TBL:
            SC.fit_width(doc, i)
    doc._touch(head)
    return {"blocks": new, "after": after}
