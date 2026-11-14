"""양식 안내 지우기 — 이관 3단계 「문서 정리」 ⑥ 작성요령 삭제(spec_작업 ② §14 「3단계」).

2026-11-12 사용자 "그냥 위 첨자, 작성요령이 테이블 첫번째 줄에 있는 경우, ※ 2page 이내 요약 작성.. 당구장 표시랑 색이랑 폰트가 같은 경우 정도만 삭제해도 되겠고만"
— 양식이 글쓴이에게 주는 안내 가운데 꼴이 분명한 셋만 지운다(헤딩 추출의 TEMP 「작성요령」 판정 전부를 지우지 않는다):
- marks  : 위첨자 각주 번호(「연구개발비15)」 의 「15)」 — 어댑터 `superscript_marks`/`strip_superscript_marks`, FMM 양식 정리와 같은 것). 글자만 지우고 런은 둔다.
- tables : 첫 줄(0행)에 「작성 요령」 이 든 표(「작성 요령 | 작성 후 작성 요령 표는 삭제」 · 「요약문 작성 요령(작성 요령은 제출하지 않습니다)」) — 표째.
           앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도(지운 자리에 빈 줄이 겹치지 않게 — FMM `_guides` 와 같음).
- notes  : 「※」 안내 — ※ 부터 문단 끝까지가 ※ 와 같은 색인 글, 그 색이 본문 색(검정)이 아닐 때(양식의 안내는 파랑·빨강 — 실측: 연차보고서 서식의 ※ 33줄 모두,
           계획서에서 옮겨 온 검정 ※ 줄은 내용이라 남는다). 글꼴은 안 따진다(같은 안내 줄 안에서 돋움체·돋움이 섞인다 — 「※ 본문내용은 돋움체 12pt, 표는 돋움 8pt로 작성」).
           문단이 그 안내뿐이면 문단째, 앞에 다른 글이 있으면(「1. 연구개발과제의 개요 ※ 2page 이내 요약 작성」) ※ 앞 글만 남긴다(그 글의 서식은 그대로).
           지울 표 안의 줄은 표와 함께 지워지니 뺀다. 빈칸만 있는 런은 색을 안 따진다.
- refs   : 「<참고 N>」 자료(2026-11-12 사용자 "<참고 N> 이 패턴도 삭제하도록 해줘라") — 「<참고 1> 연구성과 실적 증빙자료 예시」 처럼 <참고 N> 으로 시작하는 문단과
           바로 뒤의 표(사이 빈 줄 포함 — 표가 여럿 이어지면 다). 앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도. 뒤에 표가 없는 <참고 N> 줄은 안 지운다(무엇을 가리키는지 꼴로 알 수 없음).
지우는 패턴의 목록 = PATTERNS(2026-11-12 사용자 "문서 정리에는 어떤 패턴을 삭제해야하는지 목록이 있어야함") — 화면 ⑥ 「목록 보기」 의 「지우는 패턴」 표 · 확인 창 글이 이것을 쓴다.
패턴을 늘릴 때는 PATTERNS 에 한 줄 + find/apply 에 그 종류(키) + 시험.
find(doc) → {"marks": [{id, text}], "tables": [{id, label, rows, blank}], "notes": [{id, text, guide, whole}], "refs": [{id, label, last, tables, blank}],
"counts", "patterns"} · apply(doc, found) → 지운 수."""
import re

from app.division_profiles import _structure as structure

GUIDE_ROW = re.compile(r"작\s*성\s*요\s*령")
REF_HEAD = re.compile(r"^\s*[<〈＜]\s*참\s*고\s*[\d\-.]*\s*[>〉＞]")
BODY_COLORS = {None, "", "#000000", "#000", "black"}

# 지우는 패턴 목록(화면 차례) — key = find/apply 의 종류, name = 화면 이름, rule = 무엇을 찾나, how = 어떻게 지우나, example = 서식의 보기
PATTERNS = (
    {"key": "tables", "name": "작성 요령 표", "rule": "첫 줄(0행)에 「작성 요령」 이 든 표", "how": "표째(앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도)",
     "example": "작성 요령 | 작성 후 작성 요령 표는 삭제"},
    {"key": "refs", "name": "<참고 N> 자료", "rule": "「<참고 N>」 으로 시작하는 문단 + 바로 뒤의 표", "how": "제목 줄과 표째(앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도)",
     "example": "<참고 1> 연구성과 실적 증빙자료 예시"},
    {"key": "notes", "name": "※ 안내", "rule": "※ 부터 ※ 와 같은 색인 글 — 그 색이 본문 색(검정)이 아닐 때", "how": "문단째(앞에 제목이 있으면 ※ 앞 글은 남김)",
     "example": "※ 2page 이내 요약 작성"},
    {"key": "marks", "name": "위첨자 각주 번호", "rule": "위첨자로 쓴 각주 번호 「15)」·「15-1)」", "how": "번호 글자만(글은 남김)", "example": "연구개발비15)"},
)
KINDS = tuple(p["key"] for p in PATTERNS)


def _blank(b):
    return b.get("type") == "paragraph" and not (b.get("text") or "").strip()


def _paras(blocks):
    return [b for b in structure.iter_blocks(blocks) if b.get("type") == "paragraph"]


def _runs(b):
    """문단의 런 [(시작, 끝, 글, 색)] — 런이 하나면 블록의 글자 모양."""
    runs = b.get("runs") or [{"text": b.get("text") or "", "format": b.get("format") or {}}]
    out, k = [], 0
    for r in runs:
        t = r.get("text") or ""
        out.append((k, k + len(t), t, ((r.get("format") or {}).get("color") or "").upper() or None))
        k += len(t)
    return out


def note_of(b):
    """문단 b 의 ※ 안내 → (※ 자리, 안내 끝, 안내 색) | None. 안내 = ※ 부터 ※ 와 같은 색 런이 이어지는 데까지(빈칸 런은 색을 안 봄)."""
    text = "".join(t for _, _, t, _ in _runs(b))
    i = text.find("※")
    if i < 0:
        return None
    runs = _runs(b)
    color = next((c for a, e, _, c in runs if a <= i < e), None)
    if color in BODY_COLORS:   # 본문 색(검정) ※ 은 내용으로 본다 — 계획서에서 옮겨 온 「※ 차도선 하루 10회 …」 같은 줄
        return None
    end = i
    for a, e, t, c in runs:
        if e <= i:
            continue
        if c == color or not t.strip():
            end = e
            continue
        break
    return i, end, color


def _guide_tables(blocks):
    """첫 줄에 「작성 요령」 이 든 바깥 표(안쪽 표는 함께 지워짐) → [{id, label, rows, inside(그 안 블록 id 들)}]."""
    out, inside = [], set()
    for t in structure.iter_blocks(blocks):
        if t.get("type") != "table" or t["id"] in inside:
            continue
        first = sorted((c for c in t.get("cells") or () if c.get("row") == 0), key=lambda c: c.get("col", 0))
        head = " | ".join((c.get("text") or "").strip().split("\n")[0] for c in first)
        if not GUIDE_ROW.search(head):
            continue
        ids = {x["id"] for x in structure.iter_blocks([t])}
        inside |= ids
        rows = max((c["row"] + c.get("rowSpan", 1) for c in t.get("cells") or ()), default=0)
        out.append({"id": t["id"], "label": head[:60], "rows": rows, "inside": ids})
    return out


def _blank_after(blocks, ids):
    """표 id → 그 표 앞뒤가 다 빈 문단이면 뒤 빈 문단 id(FMM _guides 의 near)."""
    near = {}
    for _, items in _containers(blocks):
        for i, b in enumerate(items):
            if b["id"] in ids and 0 < i < len(items) - 1 and all(
                    x.get("type") == "paragraph" and not (x.get("text") or "").strip() for x in (items[i - 1], items[i + 1])):
                near[b["id"]] = items[i + 1]["id"]
    return near


def _containers(blocks):
    """(부모, 같은 자리의 블록 목록) — 본문 차례 + 표 칸마다(칸 안 표의 칸도)."""
    out = [(None, blocks)]
    for t in structure.iter_blocks(blocks):
        if t.get("type") == "table":
            for c in t.get("cells") or ():
                if c.get("blocks"):
                    out.append((c["id"], c["blocks"]))
    return out


def _refs(blocks, skip):
    """「<참고 N>」 자료 → [{id(제목 줄), label, last(마지막 블록 id — id..last 를 한 번에 지움), tables, blank(뒤 빈 줄 id | None), inside}].
    한 자리(본문 차례·표 칸) 안에서: 제목 줄 → (빈 줄*, 표)+ 까지. 앞 줄이 빈 줄(또는 맨 앞)이고 마지막 표 뒤가 빈 줄이면 그 빈 줄 하나도. skip(지울 표 안) 의 제목 줄은 뺀다."""
    out = []
    for _, items in _containers(blocks):
        for i, b in enumerate(items):
            if b.get("type") != "paragraph" or b["id"] in skip or not REF_HEAD.match(b.get("text") or ""):
                continue
            j, last, tabs = i + 1, i, 0
            while j < len(items):
                k = j
                while k < len(items) and _blank(items[k]):
                    k += 1
                if k < len(items) and items[k].get("type") == "table":
                    last, tabs, j = k, tabs + 1, k + 1
                    continue
                break
            if not tabs:
                continue
            blank = None
            if last + 1 < len(items) and _blank(items[last + 1]) and (i == 0 or _blank(items[i - 1])):
                blank = items[last + 1]["id"]
            ids = {x["id"] for x in structure.iter_blocks(items[i:last + 1])}
            out.append({"id": b["id"], "label": (b.get("text") or "").strip()[:80], "last": items[last]["id"], "tables": tabs, "blank": blank, "inside": ids})
    return out


def find(doc):
    blocks = doc.blocks()
    tables = _guide_tables(blocks)
    inside = set().union(*(t["inside"] for t in tables)) if tables else set()
    refs = _refs(blocks, inside)
    ref_in = set().union(*(r["inside"] for r in refs)) if refs else set()
    tables = [t for t in tables if t["id"] not in ref_in]   # <참고 N> 자료의 표이기도 하면 그 자료와 함께
    inside = set().union(ref_in, *(t["inside"] for t in tables))
    blank = _blank_after(blocks, {t["id"] for t in tables})
    notes = []
    for b in _paras(blocks):
        if b["id"] in inside:
            continue
        hit = note_of(b)
        if not hit:
            continue
        i, end, color = hit
        text = "".join(t for _, _, t, _ in _runs(b))
        keep = (text[:i].rstrip() + text[end:]).strip()
        notes.append({"id": b["id"], "text": text.strip()[:120], "guide": text[i:end].strip()[:120], "color": color, "whole": not keep,
                      "keep": text[:i].rstrip() + text[end:]})
    marks = doc.superscript_marks() if hasattr(doc, "superscript_marks") else []
    marks = [m for m in marks if m["id"] not in inside]   # 지울 표 안의 것은 표와 함께
    tabs = [{k: t[k] for k in ("id", "label", "rows")} | {"blank": blank.get(t["id"])} for t in tables]
    refs = [{k: r[k] for k in ("id", "label", "last", "tables", "blank")} for r in refs]
    found = {"marks": marks, "tables": tabs, "notes": notes, "refs": refs}
    counts = {k: len(found[k]) for k in KINDS}
    return {**found, "counts": {**counts, "total": sum(counts.values())}, "patterns": patterns(counts)}


def patterns(counts=None):
    """지우는 패턴 목록(PATTERNS) + 찾은 수 — 화면의 「지우는 패턴」 표."""
    return [{**p, "count": (counts or {}).get(p["key"], 0)} for p in PATTERNS]


def empty():
    """hwpx 가 아닌 문서의 빈 목록(find 와 같은 꼴)."""
    counts = {k: 0 for k in KINDS}
    return {**{k: [] for k in KINDS}, "counts": {**counts, "total": 0}, "patterns": patterns(counts)}


def apply(doc, found):
    """found(find 의 결과 — 같은 문서·같은 차례에서 구한 것)대로 지운다 → {"marks", "tables", "notes", "refs", "notesWhole", "notesInline", "skipped": [{id, why}]}.
    차례: ※ 안내 → <참고 N> 자료 → 작성 요령 표 → 위첨자(표 안의 위첨자는 표와 함께 사라진 뒤에 센다)."""
    out = {"marks": 0, "tables": 0, "notes": 0, "refs": 0, "notesWhole": 0, "notesInline": 0, "skipped": []}
    for it in found["notes"]:
        if it["whole"]:
            try:
                doc.delete_blocks(it["id"], it["id"])
                out["notesWhole"] += 1
            except ValueError:   # 구역 설정이 든 문단 — 문단은 두고 글만 비운다
                doc.set_text(it["id"], it["keep"].strip())
                out["notesInline"] += 1
        else:
            doc.set_text(it["id"], it["keep"])
            out["notesInline"] += 1
        out["notes"] += 1
    for it in found.get("refs") or ():
        try:
            doc.delete_blocks(it["id"], it["blank"] or it["last"])
        except ValueError:   # 구역 설정이 든 빈 줄 — 그 빈 줄은 두고 제목 줄~표만
            try:
                doc.delete_blocks(it["id"], it["last"])
            except ValueError as e:
                out["skipped"].append({"id": it["id"], "why": str(e)})
                continue
        out["refs"] += 1
    for it in found["tables"]:
        try:
            doc.delete_blocks(it["id"], it["id"])
        except ValueError as e:
            out["skipped"].append({"id": it["id"], "why": str(e)})
            continue
        out["tables"] += 1
        if it.get("blank"):
            try:
                doc.delete_blocks(it["blank"], it["blank"])
            except (ValueError, KeyError):   # 구역 설정이 든 빈 줄 — 남김
                pass
    if found["marks"] and hasattr(doc, "strip_superscript_marks"):
        out["marks"] = doc.strip_superscript_marks()
    return out
