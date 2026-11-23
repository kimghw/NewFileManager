"""양식 안내 지우기 — 이관 3단계 「문서 정리」 ⑥ 작성요령 삭제(spec_작업 ② §14 「3단계」).

2026-11-12 사용자 "그냥 위 첨자, 작성요령이 테이블 첫번째 줄에 있는 경우, ※ 2page 이내 요약 작성.. 당구장 표시랑 색이랑 폰트가 같은 경우 정도만 삭제해도 되겠고만"
— 양식이 글쓴이에게 주는 안내 가운데 꼴이 분명한 셋만 지운다(헤딩 추출의 TEMP 「작성요령」 판정 전부를 지우지 않는다):
- marks  : 위첨자 각주 번호(「연구개발비15)」 의 「15)」 — 어댑터 `superscript_marks`/`strip_superscript_marks`, FMM 양식 정리와 같은 것). 글자만 지우고 런은 둔다.
- tables : 첫 줄(글이 있는 첫 행 — 빈 0행은 건너뜀)에 「작성 요령」 이 든 표(「작성 요령 | 작성 후 작성 요령 표는 삭제」 · 「요약문 작성 요령(작성 요령은 제출하지 않습니다)」) — 표째.
           앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도(지운 자리에 빈 줄이 겹치지 않게 — FMM `_guides` 와 같음).
- notes  : 「※」 안내 — ※ 부터 문단 끝까지가 ※ 와 같은 색인 글, 그 색이 본문 색(검정)이 아닐 때(양식의 안내는 파랑·빨강 — 실측: 연차보고서 서식의 ※ 33줄 모두,
           계획서에서 옮겨 온 검정 ※ 줄은 내용이라 남는다). 글꼴은 안 따진다(같은 안내 줄 안에서 돋움체·돋움이 섞인다 — 「※ 본문내용은 돋움체 12pt, 표는 돋움 8pt로 작성」).
           문단이 그 안내뿐이면 문단째, 앞에 다른 글이 있으면(「1. 연구개발과제의 개요 ※ 2page 이내 요약 작성」) ※ 앞 글만 남긴다(그 글의 서식은 그대로).
           지울 표 안의 줄은 표와 함께 지워지니 뺀다. 빈칸만 있는 런은 색을 안 따진다.
- refs   : 「<참고 N>」 자료(2026-11-12 사용자 "<참고 N> 이 패턴도 삭제하도록 해줘라") — 「<참고 1> 연구성과 실적 증빙자료 예시」 처럼 <참고 N> 으로 시작하는 문단과
           바로 뒤의 표(사이 빈 줄 포함 — 표가 여럿 이어지면 다). 앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도. 뒤에 표가 없는 <참고 N> 줄은 안 지운다(무엇을 가리키는지 꼴로 알 수 없음).
- boxes  : 「안내 상자」(2026-11-23 사용자(「5-1. 연구개발 목표 및 내용」 아래 상자의 빨간 글 「당초계획 대비 변경사항이 있는 경우 작성 … (예시: N차년도 수정계획서 p.10~13)」 을 보이며)
           "왜 작성 지침은 4단계에서 정리가 안되지?") — 1칸 상자(칸이 하나인 표)의 글 있는 문단이 **모두 본문 색이 아닌 한 가지 색**(빨강 · 파랑 — 흰 글은 아님: 짙은 바탕의 제목)이고
           그 글에 **안내 낱말**(작성 · 기재 · 기입 · 예시 · 서술 · 기술 · 명시 · 입력)이 있을 때. 글만 지운다 — 상자는 쓸 자리라 남기고, 칸이 비어 남은 빈 줄은 본문 글 모양으로(검정 · 보통 굵기 · 양쪽 맞춤).
           본문 색 글이 한 줄이라도 있는 상자(사람이 쓴 내용이 섞임) · 칸 안에 표 · 그림이 든 상자 · 색 글이어도 안내 낱말이 없는 상자(색 글 제목 상자)는 건드리지 않는다. 「※」 가 없어 notes 가 못 잡던 꼴이다.
           첫 글이 「※」 로 시작하는 상자(안내뿐인 상자 — 연구개발계획서 양식의 빨간 「※ AI 관련 R&D 과제의 경우 … 작성 요망 ① …」: 전에는 ※ 줄만 지워져 「① …」 줄이 남았다)는 **상자째**(whole — 앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도).
지우는 패턴의 목록 = PATTERNS(2026-11-12 사용자 "문서 정리에는 어떤 패턴을 삭제해야하는지 목록이 있어야함") — 화면 ⑥ 「목록 보기」 의 「지우는 패턴」 표 · 확인 창 글이 이것을 쓴다.
패턴을 늘릴 때는 PATTERNS 에 한 줄 + find/apply 에 그 종류(키) + 시험.
find(doc) → {"marks": [{id, text}], "tables": [{id, label, rows, blank}], "notes": [{id, text, guide, whole}], "refs": [{id, label, last, tables, blank}],
"boxes": [{id(상자 = 표), first, last(지울 문단의 처음 · 끝), paras[글 있는 문단], text, color, whole(상자째인가), blank}], "counts", "patterns"} · apply(doc, found) → 지운 수."""
import re

from app.division_profiles import _structure as structure

GUIDE_ROW = re.compile(r"작\s*성\s*요\s*령")
REF_HEAD = re.compile(r"^\s*[<〈＜]\s*참\s*고\s*[\d\-.]*\s*[>〉＞]")
BODY_COLORS = {None, "", "#000000", "#000", "black"}
BOX_WORD = re.compile(r"작\s*성|기\s*재|기\s*입|예\s*시|서\s*술|기\s*술|명\s*시|입\s*력")   # 안내 상자의 안내 낱말 — 색 글이어도 이 낱말이 없는 상자(색 글 제목 상자)는 안내로 보지 않는다
BOX_SKIP = {"#FFFFFF", "#FFF"}   # 흰 글 = 짙은 바탕 위의 제목(안내 색이 아니다)
BOX_PLAIN = {"color": "#000000", "bold": False, "align": "justify", "firstLineMm": 0}   # 안내를 지워 빈 상자에 남는 빈 줄의 글 모양(안내의 빨강 · 굵게 · 가운데 · 내어쓰기를 물려받지 않게)

# 지우는 패턴 목록(화면 차례) — key = find/apply 의 종류, name = 화면 이름, rule = 무엇을 찾나, how = 어떻게 지우나, example = 서식의 보기
PATTERNS = (
    {"key": "tables", "name": "작성 요령 표", "rule": "첫 줄(글이 있는 첫 행)에 「작성 요령」 이 든 표", "how": "표째(앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도)",
     "example": "작성 요령 | 작성 후 작성 요령 표는 삭제"},
    {"key": "refs", "name": "<참고 N> 자료", "rule": "「<참고 N>」 으로 시작하는 문단 + 바로 뒤의 표", "how": "제목 줄과 표째(앞뒤가 다 빈 줄이면 뒤 빈 줄 하나도)",
     "example": "<참고 1> 연구성과 실적 증빙자료 예시"},
    {"key": "notes", "name": "※ 안내", "rule": "※ 부터 ※ 와 같은 색인 글 — 그 색이 본문 색(검정)이 아닐 때", "how": "문단째(앞에 제목이 있으면 ※ 앞 글은 남김)",
     "example": "※ 2page 이내 요약 작성"},
    {"key": "boxes", "name": "안내 상자", "rule": "1칸 상자의 글이 모두 본문 색(검정)이 아닌 한 가지 색이고 안내 낱말(작성 · 기재 · 예시 …)이 있을 때", "how": "글만(상자는 쓸 자리로 남김 — 남는 빈 줄은 본문 글 모양으로) · 「※」 로 시작하는 안내뿐인 상자는 상자째",
     "example": "당초계획 대비 변경사항이 있는 경우 작성 … (예시: N차년도 수정계획서 p.10~13)"},
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


def _whole_color(b):
    """문단의 글(빈칸 아닌 런)이 모두 본문 색이 아닌 한 가지 색이면 그 색(흰 글은 아님) | None."""
    cs = {c for _, _, t, c in _runs(b) if t.strip()}
    c = next(iter(cs)) if len(cs) == 1 else None
    return None if c in BODY_COLORS or c in BOX_SKIP else c


def _boxes(blocks, skip):
    """안내 상자 → [{id(표), first, last(지울 문단의 처음 · 끝 — 사이의 빈 줄도 함께), paras[글 있는 문단 id], text, color}] — 모듈 설명의 boxes. skip(지울 표 · <참고 N> 자료 안)의 상자는 뺀다."""
    out = []
    for t in structure.iter_blocks(blocks):
        cells = t.get("cells") or () if t.get("type") == "table" else ()
        if len(cells) != 1 or t["id"] in skip:
            continue
        items = cells[0].get("blocks") or ()
        if any(b.get("type") != "paragraph" for b in items):   # 칸 안의 표 · 그림 — 안내만 든 상자가 아니다
            continue
        paras = [b for b in items if (b.get("text") or "").strip()]
        colors = {_whole_color(b) for b in paras}
        if not paras or len(colors) != 1 or None in colors:
            continue
        text = "\n".join((b.get("text") or "").strip() for b in paras)
        if not BOX_WORD.search(text):
            continue
        out.append({"id": t["id"], "first": paras[0]["id"], "last": paras[-1]["id"], "paras": [b["id"] for b in paras], "text": text[:200], "color": next(iter(colors)),
                    "whole": text.startswith("※"), "inside": {x["id"] for x in structure.iter_blocks([t])}})
    return out


def _guide_tables(blocks):
    """첫 줄에 「작성 요령」 이 든 바깥 표(안쪽 표는 함께 지워짐) → [{id, label, rows, inside(그 안 블록 id 들)}]."""
    out, inside = [], set()
    for t in structure.iter_blocks(blocks):
        if t.get("type") != "table" or t["id"] in inside:
            continue
        cells = t.get("cells") or ()
        top = min((c.get("row", 0) for c in cells if (c.get("text") or "").strip()), default=0)   # 첫 줄 = 글이 있는 첫 행(연차보고서 「앞표지 작성 요령」 표는 0행이 빈 줄이라 0행만 보면 안 지워졌다 — 2026-11-22)
        first = sorted((c for c in cells if c.get("row") == top), key=lambda c: c.get("col", 0))
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
    boxes = _boxes(blocks, inside)
    inside = inside.union(*(b.pop("inside") for b in boxes))   # 안내 상자의 문단 — 상자와 함께 지운다(그 안의 ※ 안내 · 위첨자를 따로 세지 않는다)
    near = _blank_after(blocks, {b["id"] for b in boxes if b["whole"]})
    for b in boxes:
        b["blank"] = near.get(b["id"])
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
    found = {"marks": marks, "tables": tabs, "notes": notes, "refs": refs, "boxes": boxes}
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
    """found(find 의 결과 — 같은 문서·같은 차례에서 구한 것)대로 지운다 → {"marks", "tables", "notes", "refs", "boxes", "notesWhole", "notesInline", "skipped": [{id, why}]}.
    차례: ※ 안내 → <참고 N> 자료 → 작성 요령 표 → 안내 상자 → 위첨자(표 안의 위첨자는 표와 함께 사라진 뒤에 센다)."""
    out = {"marks": 0, "tables": 0, "notes": 0, "refs": 0, "boxes": 0, "notesWhole": 0, "notesInline": 0, "skipped": []}
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
    emptied = []
    for it in found.get("boxes") or ():
        try:
            if it.get("whole"):   # 안내뿐인 상자(「※ …」) — 상자째
                doc.delete_blocks(it["id"], it["id"])
            else:
                doc.delete_blocks(it["first"], it["last"])   # 칸이 비면 어댑터가 빈 문단 하나를 남긴다(상자는 그대로 — 쓸 자리)
        except (ValueError, KeyError) as e:
            out["skipped"].append({"id": it["id"], "why": str(e)})
            continue
        out["boxes"] += 1
        if not it.get("whole"):
            emptied.append(it)
        elif it.get("blank"):
            try:
                doc.delete_blocks(it["blank"], it["blank"])
            except (ValueError, KeyError):   # 구역 설정이 든 빈 줄 — 남김
                pass
    if emptied and hasattr(doc, "derive_format"):
        _plain_boxes(doc, emptied)
    if found["marks"] and hasattr(doc, "strip_superscript_marks"):
        out["marks"] = doc.strip_superscript_marks()
    return out


def _plain_boxes(doc, boxes):
    """안내를 지운 상자에 남은 빈 줄 가운데 글 모양이 그 안내 색인 줄(지운 문단의 모양을 물려받은 빈 문단)을 본문 글 모양(BOX_PLAIN)으로 — 거기 쓰는 글이 빨강 · 굵게로 시작하지 않게. 못 바꾸면 그대로 둔다."""
    by = {b["id"]: b for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "table"}
    for it in boxes:
        cells = (by.get(it["id"]) or {}).get("cells") or ()
        for b in (cells[0].get("blocks") or ()) if len(cells) == 1 else ():
            if b.get("type") != "paragraph" or (b.get("text") or "").strip() or (((b.get("format") or {}).get("color") or "").upper() or None) != it["color"]:
                continue
            try:
                doc.apply_format([b["id"]], doc.derive_format(doc.get_format(b["id"]), BOX_PLAIN))
            except (ValueError, KeyError):
                continue
