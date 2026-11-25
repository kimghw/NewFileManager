"""목적 양식의 작성 예시와 그림을 자리·서식·실제 이미지로 읽는다(양식 작성 04)."""
import re
from itertools import islice, zip_longest
from zipfile import BadZipFile

from PIL import Image

from app import pic_tools
from app.headings import iter_blocks


# 예시라는 제목 하나가 붙은 자료만 채울 자리에서 제외한다. '예시를 참고하여 작성'
# 같은 지침이나 실제 표의 '예시 | 입력값' 열에는 다른 쓸 자리가 있을 수 있다.
_LABEL = re.compile(r"(?:(?:샘플|견본|예시)(?:\s*(?:자료|서식|양식|표|그림))?|작성\s*예(?:문)?|sample(?:\s+(?:form|report))?|example)\s*$", re.I)
_FRAME = " \t\n[]［］()（）<>＜＞〈〉≪≫《》【】■□○◦※*:-"
TEXT_LIMIT = 6500
IMAGE_LIMIT = 16


def _label(text):
    clean = re.sub(r"\s*[(（]\s*작성\s*후\s*삭제\s*[)）]\s*$", "", (text or "").strip()).strip(_FRAME)
    return clean if len(clean) <= 100 and _LABEL.search(clean) else ""


def _table_title(table):
    # 첫 행의 장식용 빈 칸은 건너뛴다. 안쪽 표의 제목을 바깥 표의 것으로 보지 않는다.
    rows = {}
    for cell in table.get("cells") or ():
        lines = [p["text"].strip() for p in cell.get("blocks") or () if p.get("type") == "paragraph" and (p.get("text") or "").strip()]
        if not cell.get("blocks") and (cell.get("text") or "").strip():
            lines = cell["text"].strip().splitlines()
        if lines:
            rows.setdefault(cell.get("row", 0), []).append(lines[0])
    first = rows[min(rows)] if rows else []
    return _label(first[0]) if len(first) == 1 else ""


def _examples(blocks, head_ids=(), head=None, owner=None):
    """(원본 블록, 제목, 함께 읽을 블록들, 소속 헤딩, 부모 표). 제목과 표가 다른 블록인 양식도 읽는다."""
    i = 0
    while i < len(blocks):
        b = blocks[i]
        i += 1
        kind = b.get("type")
        name = _table_title(b) if kind == "table" else _label(b.get("text")) if kind == "paragraph" else ""
        if name:
            body = [b]
            if kind == "paragraph":
                j = i
                while j < len(blocks) and blocks[j].get("type") == "paragraph" and not (blocks[j].get("text") or "").strip():
                    j += 1
                if j < len(blocks) and blocks[j].get("type") in ("table", "image"):
                    body.append(blocks[j])
                    i = j + 1
                else:
                    # 예시 제목 다음의 예문은 문단 단위. 빈 줄·다음 절·다음 표시 앞에서 멈춘다.
                    while j < len(blocks) and blocks[j].get("type") == "paragraph" and blocks[j].get("id") not in head_ids:
                        line = (blocks[j].get("text") or "").strip()
                        if not line or _label(line):
                            break
                        body.append(blocks[j])
                        j += 1
                    i = j
            if kind == "table" or len(body) > 1:
                yield b, name, body, head, owner
        elif kind == "table":
            for cell in b.get("cells") or ():
                yield from _examples(cell.get("blocks") or [], head_ids, head, b["id"])
        elif kind == "image":
            yield b, "", [b], head, owner
        elif b.get("id") in head_ids:
            head = b["id"]


def example_ids(blocks, head_ids=()):
    """명시된 예시 블록과 그 안 블록들. 일반 그림·그림을 포함한 양식은 쓸 수 있다."""
    return {x["id"] for _, name, body, _, _ in _examples(blocks, head_ids) if name
            for x in iter_blocks(body) if x.get("id")}


def _style(b):
    fmt = b.get("format") or {}
    parts = [str(fmt[key]) + suffix for key, suffix in (("font", ""), ("sizePt", "pt"), ("color", ""), ("align", ""), ("lineSpacingPct", "% 줄간격"))
             if fmt.get(key) is not None]
    parts.extend(name for key, name in (("bold", "굵게"), ("italic", "기울임")) if fmt.get(key))
    return " · ".join(parts)


def _table_shape(b):
    cells = b.get("cells") or ()
    rows = b.get("nRows") or max((c.get("row", 0) + c.get("rowSpan", 1) for c in cells), default=0)
    cols = b.get("nCols") or max((c.get("col", 0) + c.get("colSpan", 1) for c in cells), default=0)
    return f"표 [{b['id']}] {rows}행 × {cols}열"


def _context_table(table):
    """같은 칸의 반복되는 글꼴 정보는 한 번만. 빈 자리에 반복되는 줄과 첫 제목의 모양도 남긴다."""
    lines = [_table_shape(table)]
    for cell in table.get("cells", ())[:8]:
        paras = [p for p in cell.get("blocks") or () if p.get("type") == "paragraph"]
        text = " ".join((cell.get("text") or " ".join(p.get("text") or "" for p in paras)).split())
        lines.append(f"{cell.get('row', 0) + 1}행 {cell.get('col', 0) + 1}열 {text[:260]}")
        seen = set()
        for p in paras:
            style = _style(p)
            if style and style not in seen and len(seen) < 5:
                lines.append(f"  [{p['id']}] {(p.get('text') or '').strip()[:45] or '(빈 줄)'} ({style})")
                seen.add(style)
    return "\n".join(lines)


def evidence(doc, blocks, graph):
    """명시된 예시(우선)와 그 밖의 양식 그림 → 출처별 텍스트·서식 및 LLM용 이미지 바이트."""
    head_ids = {n.get("para") for n in (graph or {}).get("nodes") or () if n.get("role") == "heading" and n.get("area") == "body"}
    groups = sorted(_examples(blocks, head_ids), key=lambda x: not x[1])
    if not groups:
        return []
    table_by_id = {x["id"]: x for x in iter_blocks(blocks) if x.get("type") == "table"}
    top = {x["id"]: i for i, b in enumerate(blocks) for x in iter_blocks([b]) if x.get("id")}
    # 큰 샘플 하나가 모든 그림 자리를 차지하지 않도록 출처마다 한 장씩 고른다.
    per_source = [[x["id"] for x in iter_blocks(body) if x.get("type") == "image" and x.get("media")] for _, _, body, _, _ in groups]
    image_order = (id_ for row in zip_longest(*per_source) for id_ in row if id_)
    included = set(islice(image_order, IMAGE_LIMIT))
    out = []
    for source, name, body, head, owner in groups:
        images, lines = [], []
        cut = False
        # 샘플의 바깥 표(상자) 또는 앞쪽 본문 블록이 어떤 형식의 예인지 보여 준다.
        i = top[source["id"]]
        previous = next((blocks[j] for j in range(i - 1, -1, -1) if blocks[j].get("type") == "table" or (blocks[j].get("text") or "").strip()), None)
        if owner:
            lines.append("바깥 " + _context_table(table_by_id[owner]))
        elif previous and previous.get("type") == "table":
            lines.append("앞쪽 " + _context_table(previous))
        elif previous:
            lines.append(f"앞쪽 문단 [{previous['id']}] {(previous.get('text') or '').strip()[:160]} ({_style(previous)})")
        for x in iter_blocks(body):
            kind = x.get("type")
            if kind == "table":
                lines.append(_table_shape(x))
            elif "row" in x and "col" in x:
                span = f" ({x.get('rowSpan', 1)}행 × {x.get('colSpan', 1)}열 병합)" if x.get("rowSpan", 1) > 1 or x.get("colSpan", 1) > 1 else ""
                lines.append(f"{x['row'] + 1}행 {x['col'] + 1}열{span}")
                if not x.get("blocks") and x.get("text"):
                    lines.append(x["text"])
            elif kind == "paragraph" and (x.get("text") or "").strip():
                lines.append(f"[{x['id']}] {x['text'].strip()}" + (f" ({_style(x)})" if x.get("format") else ""))
            elif kind == "image":
                tag = f"그림 [{x['id']}]"
                try:
                    if not x.get("media"):
                        raise ValueError("그림 파일 없음")
                    if x["id"] not in included:
                        raise ValueError("그림 첨부 한도")
                    picture = pic_tools.for_llm(doc.media(x["media"]))
                except (OSError, ValueError, KeyError, BadZipFile, Image.DecompressionBombError) as e:
                    lines.append(f"{tag} 이미지 미첨부 ({e})")
                    cut = True
                else:
                    images.append({**picture, "label": tag})
                    lines.append(f"{tag} 이 자료의 첨부 그림 {len(images)} ({picture['w']} × {picture['h']} px)")
        text = "\n".join(lines)
        place = owner or head
        out.append({"id": source["id"], "name": name or "양식 내 그림", "text": text[:TEXT_LIMIT], "cut": cut or len(text) > TEXT_LIMIT,
                    "images": images, **({"head": place} if place else {})})
    return out
