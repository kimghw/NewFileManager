"""매칭 지침 — 표 · 본문별(spec_병합 ② §5-6, 2026-11-22 사용자 「테이블, 본문별로 어떻게 매칭해야하는지 지침을 관리하고 LLM 이 검토할때 이 부분을 검토할 수 있도록」 ·
「LLM 검토할때 매핑 참고하도록 지침을 해당 테이블에 넣어주고」): 목적 양식의 양식 정보 「자리 연결」 절(`forms/<양식>.md` — 연결 코멘트의 원본: ② §5-3 1)에 적어 둔
「어느 표 · 본문 자리를 원본의 어디와 **어떻게** 이을지」 를 **자리마다** 읽고 고친다. 원본은 그 절 그대로다(새 저장소를 만들지 않는다) — 여기는 그 글을 지침 하나하나로 가르는 순수 함수뿐.

절의 꼴(사람이 「양식 정보」 편집기에서 고쳐도 같은 꼴이면 읽힌다):
    표:
    - **「2-1. 기술개발 추진 일정」 표** ← … (이어지는 줄은 두 칸 들여 씀)
    본문:                      ← 옛 글의 「단락:」 도 같은 묶음
    - **「1. 연구개발과제의 개요 ※ 2page 이내 요약 작성」** ← …
    코멘트 — 화면에서 남긴 것(새 것이 아래):      ← 이 줄부터는 연결 코멘트(heading_forms.comments)

- `entries(raw)` = 지침 목록 [{n, kind("table" | "body"), title(굵은 글 안의 「…」 — 그 표 · 그 본문 자리의 제목), head(굵은 글 그대로), text, pages(글에 「N page 이내」 가 있으면 N)}] — raw = 양식 정보 파일 원문.
- `match(ents, texts, kind=None)` = 그 자리(제목 · 위 제목들의 글 `texts`)에 걸린 지침들 — 글자 · 숫자만 견준다(빈칸 · 기호 · 「※」 무시). 한쪽이 다른 쪽을 품으면 같은 자리다
  (문서 정리로 「※ 2page 이내 요약 작성」 이 지워진 제목 「1. 연구개발과제의 개요」 도 그 지침의 자리).
- `pages(text)` = 글에 적힌 쪽 한도 | None — 「2page 이내」 · 「2쪽 이내」 · 「2페이지 이내」.
- `put(raw, kind, title, text, n=None)` · `drop(raw, n)` = 지침 하나를 더하거나(n None) 고치거나 지운 **새 원문**. 절이 없으면 만든다(heading_forms.LINK_TITLE).
이 글은 LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 읽는 판단 기준이다 — 스크립트의 동작은 이 글로 바뀌지 않는다(쪽 한도 `pages` 하나만 빈 자리 검토가 읽는다: merge_gaps)."""
import re

from app import heading_forms as HF

KINDS = {"table": "표", "body": "본문"}
TITLE_MAX, TEXT_MAX = 120, 1200
_GROUP = re.compile(r"^(표|단락|본문)[ \t]*[:：][ \t]*$")
_ENTRY = re.compile(r"^-[ \t]+\*\*(.+?)\*\*[ \t]*(.*)$")
_QUOTE = re.compile(r"「([^」]+)」")
_KEEP = re.compile(r"[0-9A-Za-z가-힣]")
_PAGES = re.compile(r"(\d{1,2})\s*(?:pages?|페이지|쪽|p)\s*(?:이내|이하|내외)", re.I)
_SEC = re.compile(r"^(#{1,2})[ \t]+(.*?)[ \t]*$")
KEY_MIN, PART_MIN = 4, 6   # 지침 제목이 자리 글에 들어 있으려면 · 자리 글이 지침 제목에 들어 있으려면 있어야 하는 글자 수(짧은 글이 아무 데나 맞지 않게)


def norm(text):
    """견줄 꼴 — 글자 · 숫자만(빈칸 · 기호 · 괄호 · 「※」 뺌), 영문은 소문자."""
    return "".join(_KEEP.findall(text or "")).lower()


def pages(text):
    """글에 적힌 쪽 한도 | None."""
    m = _PAGES.search(text or "")
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def _title(head):
    """굵은 글 → 자리의 제목 — 「…」 가 있으면 가장 긴 것, 없으면 굵은 글(끝의 「표」 낱말은 뗌)."""
    q = _QUOTE.findall(head)
    return max(q, key=len).strip() if q else re.sub(r"[ \t]+표$", "", head).strip()


def _scan(raw):
    """원문 → (줄 목록, 지침 [{…, a, b(줄 범위)}], 절 {a, b(절의 줄 범위 | None), groups{kind: 그 묶음의 끝 줄 다음}, note(코멘트 머리 줄 | None)})."""
    lines = (raw or "").replace("\r\n", "\n").split("\n")
    ents, sec, kind, cur, hidden = [], {"a": None, "b": None, "groups": {}, "note": None}, None, None, False
    inside = False

    def close(i):
        nonlocal cur
        if cur is not None:
            end = i
            while end > cur["a"] + 1 and not lines[end - 1].strip():
                end -= 1
            cur["b"] = end
            cur["text"] = " ".join(x.strip() for x in cur.pop("rows") if x.strip())[:TEXT_MAX]
            cur["pages"] = pages(cur["head"]) or pages(cur["text"])
            ents.append(cur)
            sec["groups"][cur["kind"]] = end
            cur = None
    for i, line in enumerate(lines):
        if hidden:   # HTML 주석 안은 안 본다(LLM 에도 안 간다)
            hidden = "-->" not in line
            continue
        if "<!--" in line:
            hidden = "-->" not in line.split("<!--", 1)[1]
            continue
        if m := _SEC.match(line):
            close(i)
            if inside:
                sec["b"] = i
            inside = len(m.group(1)) == 2 and HF._starts(m.group(2), HF.LINK_SECTION) and sec["a"] is None
            if inside:
                sec["a"], kind = i, None
            continue
        if not inside or sec["note"] is not None:
            continue
        if HF._comment_head(line):
            close(i)
            sec["note"] = i
        elif g := _GROUP.match(line.strip()):
            close(i)
            kind = "table" if g.group(1) == "표" else "body"
            sec["groups"].setdefault(kind, i + 1)
        elif m := _ENTRY.match(line):
            close(i)
            head = m.group(1).strip()
            cur = {"n": len(ents), "kind": kind or ("table" if head.endswith("표") else "body"), "title": _title(head)[:TITLE_MAX], "head": head, "rows": [m.group(2)], "a": i}
        elif cur is not None and line[:1] in (" ", "\t") and line.strip():
            cur["rows"].append(line)
        elif line.strip():
            close(i)
    close(len(lines))
    if inside and sec["b"] is None:
        sec["b"] = len(lines)
    return lines, ents, sec


def entries(raw):
    """지침 목록(모듈 설명) — 줄 범위는 뺀다."""
    return [{k: e[k] for k in ("n", "kind", "title", "head", "text", "pages")} for e in _scan(raw)[1]]


def match(ents, texts, kind=None):
    """그 자리(texts = 제목 · 위 제목들의 글)에 걸린 지침들(모듈 설명). kind = 그 종류의 지침만."""
    seen = [n for n in map(norm, texts or ()) if n]
    out = []
    for e in ents or ():
        key = norm(e.get("title"))
        if kind and e.get("kind") != kind or len(key) < KEY_MIN:
            continue
        if any(key in n or (len(n) >= PART_MIN and n in key) for n in seen):
            out.append(e)
    return out


def _clean(text, limit, what):
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", (text or "").replace("\r\n", "\n")).strip() if isinstance(text, str) else ""
    t = re.sub(r"\*\*|<!--|-->", "", t)
    if not t:
        raise ValueError(f"{what}이 비어 있습니다")
    if len(t) > limit:
        raise ValueError(f"{what}은 {limit}자까지입니다(지금 {len(t)}자)")
    return t


def _rows(kind, title, text):
    """지침 하나의 줄들 — 첫 줄 「- **「제목」[ 표]** 글」 + 이어지는 줄(두 칸 들여 씀)."""
    title = re.sub(r"[「」\n]", " ", _clean(title, TITLE_MAX, "제목")).strip()
    body = [x for x in _clean(text, TEXT_MAX, "지침 글").split("\n") if x.strip()]
    return [f"- **「{title}」{' 표' if kind == 'table' else ''}** {body[0].strip()}", *(f"  {x.strip()}" for x in body[1:])]


def put(raw, kind, title, text, n=None):
    """지침 하나를 더하거나(n None) 고친 새 원문(모듈 설명). ValueError = 모르는 종류 · 빈 글 · 없는 n."""
    if kind not in KINDS:
        raise ValueError("종류는 표(table) · 본문(body) 가운데 하나입니다")
    rows = _rows(kind, title, text)
    lines, ents, sec = _scan(raw)
    if n is not None:
        e = next((x for x in ents if x["n"] == n), None)
        if e is None:
            raise ValueError("그런 지침이 없습니다(그 사이 양식 정보가 바뀌었습니다 — 다시 여세요)")
        if e["kind"] == kind:
            lines[e["a"]:e["b"]] = rows
            return "\n".join(lines).rstrip("\n") + "\n"
        del lines[e["a"]:e["b"]]   # 종류를 바꿈 — 지우고 그 종류의 묶음에 더한다
        lines, ents, sec = _scan("\n".join(lines))
    if sec["a"] is None:
        return f"{(raw or '').rstrip()}\n\n## {HF.LINK_TITLE}\n\n{KINDS[kind]}:\n" + "\n".join(rows) + "\n"
    at = sec["groups"].get(kind)
    if at is None:   # 그 종류의 묶음이 없다 — 코멘트 목록 앞(없으면 절 끝)에 묶음 머리부터
        at = sec["note"] if sec["note"] is not None else sec["b"]
        while at > sec["a"] + 1 and not lines[at - 1].strip():
            at -= 1
        rows = ["", f"{KINDS[kind]}:", *rows]
        if at < len(lines) and lines[at].strip():
            rows.append("")
    lines[at:at] = rows
    return "\n".join(lines).rstrip("\n") + "\n"


def drop(raw, n):
    """지침 하나를 지운 새 원문. ValueError = 없는 n."""
    lines, ents, _ = _scan(raw)
    e = next((x for x in ents if x["n"] == n), None)
    if e is None:
        raise ValueError("그런 지침이 없습니다(그 사이 양식 정보가 바뀌었습니다 — 다시 여세요)")
    del lines[e["a"]:e["b"]]
    return "\n".join(lines).rstrip("\n") + "\n"
