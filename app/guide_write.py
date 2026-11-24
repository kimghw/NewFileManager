"""지침 작성(spec_양식작성 ② §5) — 양식의 **자리(헤딩 · 표)마다 작성 지침을 주고, 받은 자료에서 그 자리에 넣을 내용을 에이전트가 제안**하게 하는 도구의 순수 계산.
2026-11-24 사용자 "다른 도구는 작성 지침을 주면문서에 채워주는 LLM 도구도 넣어주면 될거 같아". 문서를 고치지 않고 LLM 도 부르지 않는다 — 끝점 · 실행은 `app/guide_write_api.py`.

- 새 LLM 호출 · 새 반영 길을 만들지 않는다: 자리마다 **문서 에이전트의 한 턴**(`doc_agent` — 요청 → 제안)을 돌리고, 제안은 에이전트 보기의 제안 카드로 나와 사람이 고른 것만 반영된다(spec_일반편집 ② §8 · §9).
  이 모듈은 그 턴의 **요청 글**을 짓는다(`request`) — 그 자리의 작성 지침(양식의 것 · 사람이 적은 것: `place_guides` 하나로 고른다) + 이번 실행에 사람이 적은 지침(note).
- `places(blocks, graph, ix)` → 자리 목록 [{id, kind("head" | "table"), text(헤딩 글 · 표 이름), depth, guides[{src, kind, text}], n(지침 수), user(사람 지침이 있나), filled(그 자리에 이미 글이 있나), head(표가 속한 헤딩 id)}]
  — 본문 헤딩 줄 전부(지침이 없어도 — 사람이 이번 실행의 지침만으로 채우게 할 수 있다) + 지침이 붙은 표. 문서 차례.
- 스크립트가 판정하지 못한 것 = 그 자리에 무엇을 써야 하는지(지침과 자료를 읽어야 안다) — 문서 에이전트가 판정한다. 자료에 없는 내용은 에이전트가 행동 없이 그렇게 답한다(지어내지 않는다 — jobs/form_write.md)."""
from app import place_guides as PG
from app.headings import iter_blocks

TEXT_MAX = 3800          # 요청 글(doc_agent.TEXT_MAX 4,000 안쪽)
GUIDE_MAX = 2400         # 요청 글에 싣는 그 자리의 지침(합쳐)
NOTE_MAX = 1000          # 이번 실행에 사람이 적는 지침
PLACES_MAX = 40          # 한 번에 돌리는 자리 수
HEAD_TEXT = 160


def _one(text, n=HEAD_TEXT):
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _heads(blocks, graph):
    """본문 헤딩 줄 [(본문 최상위 차례, 문단 id, 깊이 | None)] — 문서 차례(guide_fix._heads 와 같은 줄)."""
    pos = {b["id"]: k for k, b in enumerate(blocks or ())}
    out = {(pos[n["para"]], n["para"], n.get("depth")) for n in (graph or {}).get("nodes") or ()
           if isinstance(n, dict) and n.get("role") == "heading" and n.get("area") == "body" and n.get("para") in pos}
    return sorted(out, key=lambda x: x[0])


def _table_name(b):
    """표의 이름 — 첫 행의 글(짧게)."""
    cells = sorted(b.get("cells") or (), key=lambda c: (c.get("row") or 0, c.get("col") or 0))
    row0 = [" ".join(x.get("text") or "" for x in iter_blocks(c.get("blocks") or ()) if x.get("type") == "paragraph").strip() for c in cells if (c.get("row") or 0) == 0]
    return _one(" | ".join(t for t in row0 if t), 80) or "표"


def places(blocks, graph, ix):
    """자리 목록(문서 차례) — 위 머리말."""
    blocks = list(blocks or ())
    heads = _heads(blocks, graph)
    by_id = {b["id"]: b for b in blocks}
    ix = ix or {"heads": {}, "tables": {}}
    out, rows = [], []
    for n, (i, pid, depth) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(blocks)
        seq = blocks[i + 1:end]
        filled = any(b.get("type") == "paragraph" and (b.get("text") or "").strip() for b in seq)
        guides = [dict(g) for g in ix["heads"].get(pid) or ()]
        rows.append((i, {"id": pid, "kind": "head", "text": _one(by_id[pid].get("text")), "depth": depth, "guides": guides, "n": len(guides), "user": any(g.get("src") == "user" for g in guides),
                         "filled": filled, "tables": [b["id"] for b in seq if b.get("type") == "table"]}))
    find = PG.heading_finder(blocks, graph)
    pos = {b["id"]: k for k, b in enumerate(blocks)}
    top = {}
    for k, b in enumerate(blocks):
        for x in iter_blocks([b]):
            top.setdefault(x["id"], k)
    for tid, guides in (ix.get("tables") or {}).items():
        if not guides or tid not in top:
            continue
        k = top[tid]
        host = blocks[k]
        b = next((x for x in iter_blocks([host]) if x["id"] == tid), host)
        guides = [dict(g) for g in guides]
        rows.append((k + 0.5, {"id": tid, "kind": "table", "text": _table_name(b), "depth": None, "guides": guides, "n": len(guides), "user": any(g.get("src") == "user" for g in guides),
                               "filled": False, "head": find(host["id"]), "top": tid in pos}))
    for _, p in sorted(rows, key=lambda r: r[0]):
        out.append(p)
    return out


def guides_text(guides, limit=GUIDE_MAX):
    """그 자리의 지침들 → 요청 글에 싣는 줄들(사람의 것이 앞 · 합쳐 limit 자까지)."""
    packed, _ = PG.pack(sorted(guides or (), key=lambda g: g.get("src") != "user"), limit=limit)   # 사람의 것이 앞(자를 때 남는다 — 같은 원천끼리는 차례 그대로)
    lines = []
    for g in packed:
        who = "사람" if g.get("src") == "user" else "양식"
        kind = f" · {g['kind']}" if g.get("kind") and g.get("src") != "user" else ""
        lines.append(f"- ({who}{kind}) {' '.join((g.get('text') or '').split())}")
    return "\n".join(lines)


def request(place, note="", head_text=""):
    """자리 하나의 요청 글(문서 에이전트의 한 턴에 보내는 글) — 그 자리 · 그 자리의 작성 지침 · 이번 실행의 지침 · 무엇을 답할지. TEXT_MAX 자 안."""
    note = " ".join((note or "").split())[:NOTE_MAX]
    gt = guides_text(place.get("guides"))
    if place["kind"] == "table":
        where = f"표 「{place['text']}」(id {place['id']}" + (f" · 헤딩 「{_one(head_text, 80)}」 아래" if head_text else "") + ")"
        ask = ("받은 자료에서 이 표에 들어갈 값을 찾아 이 표를 채우는 제안(tableFill)을 내세요. 자료에 그 값이 없는 칸은 비워 둡니다. "
               "자료에 이 표에 해당하는 내용이 전혀 없으면 행동 없이 그렇게 답하세요.")
    else:
        where = f"헤딩 「{place['text']}」(id {place['id']}) 아래"
        ask = ("받은 자료에서 이 자리에 해당하는 내용을 찾아 이 헤딩 줄 바로 아래에 넣을 글을 제안(write — after 는 이 헤딩 줄)하세요. "
               "자료의 글을 그대로 옮길 수 있으면 옮긴 글(extract)로, 작성 지침이 정리 · 요약해 쓰라고 한 자리면 자료의 내용만으로 지은 글(draft)로 씁니다. "
               + ("이 헤딩 아래의 표는 자료에 그 값이 있을 때만 표 채우기(tableFill)를 함께 제안합니다. " if place.get("tables") else "")
               + ("이 자리에는 이미 글이 있습니다 — 있는 글과 겹치는 내용은 다시 쓰지 않습니다. " if place.get("filled") else "")
               + "자료에 이 자리에 해당하는 내용이 없으면 행동 없이 그렇게 답하세요(지어내지 않습니다).")
    parts = [f"[지침 작성] {where} 자리를 작성 지침에 따라 채웁니다."]
    if gt:
        parts.append("이 자리의 작성 지침:\n" + gt)
    if note:
        parts.append("이번 작성의 지침(사람이 적음): " + note)
    if not gt and not note:
        parts.append("이 자리에 적힌 작성 지침은 없습니다 — 헤딩의 뜻에 맞는 내용을 자료에서 찾습니다.")
    parts.append(ask)
    text = "\n\n".join(parts)
    return text if len(text) <= TEXT_MAX else text[:TEXT_MAX - 1] + "…"


def selection(place):
    """그 자리의 턴에 줄 selection — 헤딩 = 그 줄에 커서 · 표 = 그 표를 고름(문서 에이전트가 그 둘레의 개요 · 그 표의 격자를 싣는다)."""
    if place["kind"] == "table":
        return {"paras": [], "table": place["id"] if place.get("top", True) else None, "range": None, "cursor": place["id"] if place.get("top", True) else place.get("head")}
    return {"paras": [], "table": None, "range": None, "cursor": place["id"]}


def pick(all_places, ids):
    """고른 id 들 → 그 자리들(문서 차례 · 모르는 id 는 버림 · PLACES_MAX 까지) + 버린 수."""
    want = [i for i in dict.fromkeys(ids or ()) if isinstance(i, str)]
    got = [p for p in all_places if p["id"] in set(want)]
    return got[:PLACES_MAX], len(want) - len(got) + max(0, len(got) - PLACES_MAX)
