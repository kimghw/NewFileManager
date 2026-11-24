"""지침 작성(spec_양식작성 ② §5) — 양식의 **자리(헤딩 · 표)마다 작성 지침을 주고, 받은 자료에서 그 자리에 넣을 내용을 에이전트가 제안**하게 하는 도구의 순수 계산.
2026-11-24 사용자 "다른 도구는 작성 지침을 주면문서에 채워주는 LLM 도구도 넣어주면 될거 같아". 문서를 고치지 않고 LLM 도 부르지 않는다 — 끝점 · 실행은 `app/guide_write_api.py`.

- 새 LLM 호출 · 새 반영 길을 만들지 않는다: 자리마다 **문서 에이전트의 한 턴**(`doc_agent` — 요청 → 제안)을 돌리고, 제안은 에이전트 보기의 제안 카드로 나와 사람이 고른 것만 반영된다(spec_일반편집 ② §8 · §9).
  이 모듈은 그 턴의 **요청 글**을 짓는다(`request`) — 그 자리의 작성 지침(양식의 것 · 사람이 적은 것: `place_guides` 하나로 고른다) + 이번 실행에 사람이 적은 지침(note).
- `places(blocks, graph, ix)` → 자리 목록 [{id, kind("head" | "table"), text(헤딩 글 · 표 이름), depth, guides[{src, kind, text}], n(지침 수), user(사람 지침이 있나), filled(그 자리에 이미 글이 있나), head(표가 속한 헤딩 id)}]
  — 본문 헤딩 줄 전부(지침이 없어도 — 사람이 이번 실행의 지침만으로 채우게 할 수 있다) + 지침이 붙은 표. 문서 차례.
- 스크립트가 판정하지 못한 것 = 그 자리에 무엇을 써야 하는지(지침과 자료를 읽어야 안다) — 문서 에이전트가 판정한다. 자료에 없는 내용은 에이전트가 행동 없이 그렇게 답한다(지어내지 않는다 — jobs/form_write.md)."""
from app import form_slots as FS
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


def levels_of(graph):
    """헤딩 그래프가 매긴 줄의 레벨 {문단 id: 레벨} — 상자 안 줄(area box)도 든다(상자의 덩이가 「어느 제목 아래 몇 레벨」 로 읽히게: form_slots)."""
    return {n["para"]: n["level"] for n in (graph or {}).get("nodes") or () if isinstance(n, dict) and n.get("para") and n.get("level")}


def boxes(blocks, graph, orig=None):
    """쓸 자리가 있는 상자(본문 최상위 1칸 표) {표 id: {"at": 본문 차례, "entries", "chunks", "targets", "inner"[상자 안 표 id]}} — 칸의 직접 문단에 빈 줄 · 글머리 줄 · 같은 줄 뒤에 값을 쓰는 줄 · 표시 줄이
    하나라도 있는 것(form_slots). orig = 올린 원본의 문단 원문 {id: 글}(주면 이미 채운 자리를 가린다 — 다 채운 상자도 자리로 남는다)."""
    lv, out = levels_of(graph), {}
    for k, b in enumerate(blocks or ()):
        cell = FS.box_cell(b)
        if cell is None:
            continue
        ents = FS.entries(cell, lv, orig)
        chs = FS.chunks(ents)
        if any(c["slots"] or c["head"]["kind"] in ("label", "check", "filled") or any(e["kind"] == "filled" for e in ents) for c in chs):
            out[b["id"]] = {"at": k, "entries": ents, "chunks": chs, "targets": FS.targets(chs), "inner": [x["id"] for x in iter_blocks([b]) if x.get("type") == "table" and x["id"] != b["id"]]}
    return out


_SAMPLE = ("샘플", "예시", "작성 예", "작성예", "견본")


def _sample(table):
    """그 표가 본보기 · 그림 자리인가 — 표 안에 그림이 있거나(캡처 · 성과 그림) 제목 글에 「샘플」 · 「예시」 가 있다. 헤딩의 턴이 「그 아래의 표」 로 채우지 않는다(astra 3차: 「작성을 위한 샘플자료」 표의 꾸밈 칸 넷이 열렸다).
    지침이 붙은 표는 따로 선 자리로 그대로 선다(사람이 고른다)."""
    xs = list(iter_blocks([table]))
    return any(x.get("type") == "image" or x.get("pics") for x in xs) or any(w in (x.get("text") or "") for x in xs if x.get("type") == "paragraph" for w in _SAMPLE)


def chunk_views(box):
    """상자의 덩이를 화면 · 실행이 읽는 꼴로 [{key(머리 문단 id), no, head(머리 글), under(윗 제목 글), level, kind(머리의 종류), slots(쓸 수 있는 줄 수 — 머리 포함), paras[쓸 수 있는 문단 id], dup[몇 번째, 몇 개], filled(이미 채운 줄 수)}]
    — 쓸 수 있는 줄이 없는 덩이(제목뿐)는 뺀다. 같은 이름의 덩이가 여럿이면(dup[1] > 1) 사람이 그 가운데 하나를 골라야 쓴다(guide_write_api — astra 2차 G5)."""
    tg, out = box["targets"], []
    for c in box["chunks"]:
        ids = [e["id"] for e in (c["head"], *c["slots"]) if e["id"] in tg and tg[e["id"]]["kind"] in WRITABLE]
        if ids:
            out.append({"key": c["head"]["id"], "no": c["no"], "head": _one(c["head"]["raw"].strip(), 80), "under": _one(c.get("under") or "", 80), "level": c["head"].get("level"), "kind": c["head"]["kind"],
                        "slots": len(ids), "paras": ids, "dup": c["dup"], "group": c.get("name", c["head"]["raw"].strip())})   # group = 같은 이름을 가리는 글(form_slots 의 name — 채운 머리는 올린 원본의 글)
    return out


def chunk_paras(box, keys=None):
    """그 상자에서 이번에 쓸 수 있는 문단 id 들 — keys(사람이 고른 덩이의 key 들 | None = 고르지 않음: 같은 이름이 여럿인 덩이를 뺀 모두). 같은 이름의 덩이는 **고른 것 하나만**(둘 이상 고르면 그 이름은 모두 뺀다)."""
    views = chunk_views(box)
    if keys is None:
        return [i for v in views if v["dup"][1] == 1 for i in v["paras"]]
    want, out = set(keys), []
    for v in views:
        if v["key"] not in want:
            continue
        if v["dup"][1] > 1 and sum(1 for x in views if x["key"] in want and x["group"] == v["group"] and x["under"] == v["under"]) > 1:
            continue
        out += v["paras"]
    return out


WRITABLE = ("blank", "stub", "label", "check")   # v1 — 붙이기 · 표시만(양식에 있던 글을 바꾸는 줄은 내지 않는다: astra 2차 G4)


def places(blocks, graph, ix, orig=None):
    """자리 목록(문서 차례) — 위 머리말. orig = 올린 원본의 문단 원문(채운 자리를 가린다). 2026-11-24 더함(spec_양식작성 ② §5-3): 쓸 자리가 있는 상자 = 자리(kind "box" — 지침 = 그 상자와 상자 안 표에 붙은 것 모두 · 상자 안의 표는 따로 자리로 서지 않는다) ·
    헤딩 줄이 같은 줄에 값을 쓰는 자리면 slot("label" | "check") · 헤딩의 구간에 상자 자리가 있으면 boxed."""
    blocks = list(blocks or ())
    heads = _heads(blocks, graph)
    by_id = {b["id"]: b for b in blocks}
    ix = ix or {"heads": {}, "tables": {}}
    bx = boxes(blocks, graph, orig)
    out, rows = [], []
    for n, (i, pid, depth) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(blocks)
        seq = blocks[i + 1:end]
        filled = any(b.get("type") == "paragraph" and (b.get("text") or "").strip() for b in seq)
        guides = [dict(g) for g in ix["heads"].get(pid) or ()]
        rows.append((i, {"id": pid, "kind": "head", "text": _one(by_id[pid].get("text")), "depth": depth, "guides": guides, "n": len(guides), "user": any(g.get("src") == "user" for g in guides),
                         "filled": filled, "tables": [b["id"] for b in seq if b.get("type") == "table" and b["id"] not in bx and not _sample(b)], "slot": FS.line_slot(by_id[pid], (orig or {}).get(pid) if orig is not None else None),
                         "boxed": any(b["id"] in bx for b in seq), "fp": by_id[pid].get("text") or ""}))
    find = PG.heading_finder(blocks, graph)
    pos = {b["id"]: k for k, b in enumerate(blocks)}
    top = {}
    for k, b in enumerate(blocks):
        for x in iter_blocks([b]):
            top.setdefault(x["id"], k)
    tabs, boxed = ix.get("tables") or {}, set()
    for tid, box in bx.items():
        boxed.update([tid, *box["inner"]])
        guides = [dict(g) for t in (tid, *box["inner"]) for g in tabs.get(t) or ()]
        name = next((c["head"]["raw"].strip() for c in box["chunks"]), "") or "상자"
        rows.append((box["at"] + 0.5, {"id": tid, "kind": "box", "text": _one(name, 80), "depth": None, "guides": guides, "n": len(guides), "user": any(g.get("src") == "user" for g in guides),
                                       "filled": False, "head": find(tid), "top": True, "slots": len(chunk_paras(box, [v["key"] for v in chunk_views(box)])), "chunks": chunk_views(box),
                                       "fp": [[e.get("id"), e["kind"], e.get("raw", ""), e.get("level")] for e in box["entries"]]}))
    for tid, guides in tabs.items():
        if not guides or tid not in top or tid in boxed:   # 상자 자리 안의 표는 따로 서지 않는다(그 지침은 상자 자리가 지닌다)
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


def request(place, note="", head_text="", plan=""):
    """자리 하나의 요청 글(문서 에이전트의 한 턴에 보내는 글) — 그 자리 · 그 자리의 작성 지침 · 이번 실행의 지침 · 양식 검토의 글(plan — 사람이 정해 준 것 + 이 자리의 작성 방향:
    form_review.plan_text) · 무엇을 답할지. TEXT_MAX 자 안 — 넘치면 작성 지침 몫을 줄인다(묻는 말 · 정해 준 것은 늘 남는다)."""
    note = " ".join((note or "").split())[:NOTE_MAX]
    plan = (plan or "").strip()
    room = TEXT_MAX - len(note) - len(plan) - 1300   # 자리 · 묻는 말 · 머리들의 몫을 뗀 나머지
    gt = guides_text(place.get("guides"), limit=max(400, min(GUIDE_MAX, room)))
    if place["kind"] == "box":
        where = f"상자 「{place['text']}」(id {place['id']}" + (f" · 헤딩 「{_one(head_text, 80)}」 아래" if head_text else "") + ")"
        ask = ("이 상자 안의 쓸 자리(selection.table.lines 의 문단)를 받은 자료의 내용으로 채우는 제안(fill)을 내세요. 줄마다 그 문단의 **새 글 전체**를 적습니다 — 라벨 줄 · 글머리 줄은 지금 글(앞 빈칸 · 글머리 · 라벨) 뒤에 값을 붙이고, "
               "빈 줄은 그 위 제목에 해당하는 내용을 씁니다. 한 제목의 내용은 그 제목 바로 아래의 자리에만 쓰고, 자리가 모자라면 남는 내용은 쓰지 않고 reply 에 무엇이 빠졌는지 적습니다. "
               "제목 · 안내(※) · 캡션과 「○○ 작성」 · 「000」 같은 양식의 자리표시 글은 바꾸지 않습니다(사람이 고칩니다). 「쓸 자리」 라고 적힌 줄만 씁니다 — 「이번에는 쓰지 않는 자리」 는 사람이 이번에 열지 않은 자리입니다"
               "(같은 이름의 자리가 여럿이면 열린 쪽이 사람이 고른 자리입니다). "
               "상자 안의 표 · 그림 자리는 채우지 않습니다 — 자료에 그 그림의 캡션이 있으면 reply 에 「(그림: 캡션)」 으로 알립니다. 자료에 이 상자에 해당하는 내용이 없으면 행동 없이 그렇게 답하세요(지어내지 않습니다).")
    elif place["kind"] == "table":
        where = f"표 「{place['text']}」(id {place['id']}" + (f" · 헤딩 「{_one(head_text, 80)}」 아래" if head_text else "") + ")"
        ask = ("받은 자료에서 이 표에 들어갈 값을 찾아 이 표를 채우는 제안(tableFill)을 내세요. 자료에 그 값이 없는 칸은 비워 둡니다. "
               "자료에 이 표에 해당하는 내용이 전혀 없으면 행동 없이 그렇게 답하세요.")
    elif place.get("slot") == "label":
        where = f"줄 「{place['text']}」(id {place['id']})"
        ask = ("이 줄은 라벨 뒤에 값을 쓰는 자리입니다. 받은 자료 · 정해 준 것에서 그 값을 찾아 이 줄을 채우는 제안(fill — para 는 이 줄 · text 는 지금 글 뒤에 값을 붙인 새 글 전체)을 내세요. 이 줄 아래에 새 문단을 넣지 않습니다. "
               "자료 · 정해 준 것에 그 값이 없으면 행동 없이 그렇게 답하세요(지어내지 않습니다).")
    elif place.get("slot") == "check":
        where = f"줄 「{place['text']}」(id {place['id']})"
        ask = ("이 줄은 항목 가운데 하나에 표시하는 자리입니다. 정해 준 것 · 받은 자료가 가리키는 항목 **하나**의 「□」 를 「■」 로 바꾼 새 글 전체를 fill 로 내세요(다른 글자는 그대로). "
               "어느 항목인지 정할 수 없으면 행동 없이 그렇게 답하세요.")
    else:
        where = f"헤딩 「{place['text']}」(id {place['id']}) 아래"
        ask = (("이 헤딩 아래의 상자는 따로 선 자리입니다 — 상자에 들어갈 내용을 여기 쓰지 않습니다. 상자 밖에 쓸 것이 자료 · 지침에 없으면 행동 없이 그렇게 답하세요. " if place.get("boxed") else "")
               + "받은 자료에서 이 자리에 해당하는 내용을 찾아 이 헤딩 줄 바로 아래에 넣을 글을 제안(write — after 는 이 헤딩 줄)하세요. "
               "자료의 글을 그대로 옮길 수 있으면 옮긴 글(extract)로, 작성 지침이 정리 · 요약해 쓰라고 한 자리면 자료의 내용만으로 지은 글(draft)로 씁니다. "
               + ("이 헤딩 아래의 표는 자료에 그 값이 있을 때만 표 채우기(tableFill)를 함께 제안합니다. " if place.get("tables") else "")
               + ("이 자리에는 이미 글이 있습니다 — 있는 글과 겹치는 내용은 다시 쓰지 않습니다. " if place.get("filled") else "")
               + "자료에 이 자리에 해당하는 내용이 없으면 행동 없이 그렇게 답하세요(지어내지 않습니다).")
    parts = [f"[지침 작성] {where} 자리를 작성 지침에 따라 채웁니다."]
    if gt:
        parts.append("이 자리의 작성 지침:\n" + gt)
    if note:
        parts.append("이번 작성의 지침(사람이 적음): " + note)
    if plan:
        parts.append(plan)
    if not gt and not note and not plan:
        parts.append("이 자리에 적힌 작성 지침은 없습니다 — 헤딩의 뜻에 맞는 내용을 자료에서 찾습니다.")
    parts.append(ask)
    text = "\n\n".join(parts)
    return text if len(text) <= TEXT_MAX else text[:TEXT_MAX - 1] + "…"


def selection(place):
    """그 자리의 턴에 줄 selection — 헤딩 = 그 줄에 커서 · 표 = 그 표를 고름(문서 에이전트가 그 둘레의 개요 · 그 표의 격자를 싣는다).
    칸 안의 표(상자 안에 든 표)도 그 표를 고른다 — `doc_agent.selection_of` · 표 채우기는 칸 안의 표를 그대로 다룬다(2026-11-24: 전에는 헤딩에 커서만 줘서 요청 글이 가리키는 표 id 가 보낸 자료에 없었다 —
    에이전트가 「그 표가 받은 문서 정보에 없습니다」 로 답하고 제안이 0개였다)."""
    if place["kind"] in ("table", "box"):
        return {"paras": [], "table": place["id"], "range": None, "cursor": place["id"]}
    return {"paras": [], "table": None, "range": None, "cursor": place["id"]}


def pick(all_places, ids):
    """고른 id 들 → 그 자리들(문서 차례 · 모르는 id 는 버림 · PLACES_MAX 까지) + 버린 수."""
    want = [i for i in dict.fromkeys(ids or ()) if isinstance(i, str)]
    got = [p for p in all_places if p["id"] in set(want)]
    return got[:PLACES_MAX], len(want) - len(got) + max(0, len(got) - PLACES_MAX)
