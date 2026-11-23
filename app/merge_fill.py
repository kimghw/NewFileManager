"""병합 — 넣기 계획(본문) · ④ 내용 반영(spec_병합 ② §5 「문단 묶음 항목」 · §6): 짝지은 문단 묶음의 항목마다 원본 항목 내용을 목적 항목의 넣을 자리 뒤에 복사한다.

- `plan(to_side, from_side, to_values, from_values, pairs, applied=None)` = 문서를 고치지 않는 모의 계획 → {"items": [...], "counts": {...}}. side = {"doc", "graph"}(merge_data·작업의 그 꼴),
  pairs = `merge_pairs.pair` 결과 — `paired` 인 문단 묶음만 든다. 항목 = 구분 기준 엔진(`core.find`)의 항목(라벨 id 로 찾음 — 묶음 key 가 바뀌어도 항목은 찾는다).
  원본 내용 = 원본 항목 roots 의 라벨 다음부터(표 캡션 블록은 표와 함께 가므로 뺌) — 글머리만 있는 자리표시 줄은 빼고 앞뒤 빈 줄을 깎는다. 남는 것이 없으면 `noSource`.
  넣을 자리(anchor) = 묶음 짝의 anchor 글(merge_pairs `inner` 꼴 「레터 글」)과 같은 목적 항목 안 소제목, 없거나 못 찾으면 **첫 잎 소제목**(목적 항목 roots 안 2단계 그래프의
  heading·subtitle·label 노드 중 그 안에 자식 노드가 없는 첫 것), 소제목이 없으면 라벨. 자리 = 넣을 자리 다음부터 다음 소제목(또는 항목 끝) 앞까지 —
  표가 있으면 `tables`(표 칸 넣기 몫), 글·그림이 있으면 `occupied`(※ 안내 줄·빈 줄은 글이 아님), 글머리만 있는 줄은 넣은 뒤 지울 `placeholders`.
  `applied` = {목적 항목 key(라벨 id): {from, hash}} — 같은 해시면 `applied`, 다르면 `changed`(「원본 바뀜」 — 다시 넣지 않음).
- `apply(to_doc, from_doc, plan, convert=None)` = 할 일(skip 없음) 항목마다 넣을 자리 뒤에 원본 블록을 원본 차례로 복사(`insert_after(kind=copy)`) → `convert(anchor, [(원본 id, 새 id)])`(템플릿 변환 갈고리 —
  merge_convert) → 자리표시 줄 지움. 복사에서 빠지는 개체(`DROP_ON_COPY` — OLE·차트·구역 설정 등)는 `dropped` 로 알린다. 원본 문서는 읽기만 한다.
  갈고리가 결과를 돌려주고 거기에 넘친 줄의 기록(`over` — merge_convert.record, spec_병합 ② §5-5 7)이 있으면 그 항목의 `applied` 에 함께 적는다(넣은 뒤 다시 맞추기의 근거)."""
import hashlib
import json
from collections import Counter

from lxml import etree

from app import merge_pairs as P
from app import merge_take as TK
from app.division_profiles import _structure as structure
from app.division_profiles import rnd
from app.division_profiles.rnd import core
from app.hwpx_doc import DROP_ON_COPY

HEADS = ("heading", "subtitle", "label")   # 넣을 자리가 되는 그래프 노드 — merge_pairs._inner 와 같은 갈래(anchor 글을 같은 꼴로 견준다)
SKIPS = ("noSource", "applied", "changed", "tables", "occupied", "outside")   # outside = 「넣을 구성 선택」 에서 고르지 않은 기관 · 단계 · 차년도의 항목(merge_take — spec_병합 ② §4-1)


def _engine(side, values):
    """문서 하나 → (블록 색인, {라벨 id: 엔진 항목}, 그래프 노드)."""
    blocks = side["doc"].blocks()
    groups = core.find(blocks, rnd.levels_of(blocks), core.norm_values(values))
    items = {it["label"]: it for g in groups for it in g["items"] if it.get("label")}
    return structure.index_blocks(blocks), items, {n["id"]: n for n in (side.get("graph") or {}).get("nodes") or ()}


def _placeholder(b):
    """글머리만 있는 자리표시 줄(「ㅇ」·「-」, 또는 글 없이 자동 글머리만 있는 줄)."""
    t = (b.get("text") or "").strip()
    return b.get("type") == "paragraph" and bool(core.PLACEHOLDER.match(t)) and bool(t or b.get("list"))


def _blank(b):
    return b.get("type") == "paragraph" and not (b.get("text") or "").strip()


def _source(idx, it):
    """원본 항목 → 복사할 블록(라벨 뒤 · 캡션 뺌 · 자리표시 줄 뺌 · 앞뒤 빈 줄 깎음)."""
    out = [b for r in it["roots"][1:] if (b := idx.get(r)) and not b.get("captionOf") and not _placeholder(b)]
    while out and _blank(out[0]):
        out.pop(0)
    while out and _blank(out[-1]):
        out.pop()
    return out


def _hash(src):
    rows = [[x.get("type"), x.get("text") or ""] for b in src for x in core._under(b)]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _head_text(n):
    return P._ws(f"{n.get('letter') or ''} {n.get('text') or ''}")[:P.TEXT_MAX]


def _anchor(it, nodes, want):
    """목적 항목 → (넣을 자리 id, 글, 자리 블록 id 들, 알림). want = 묶음 짝의 anchor 글(없으면 기본)."""
    roots = it["roots"]
    heads = [nodes[r] for r in roots[1:] if r in nodes and nodes[r].get("role") in HEADS and not nodes[r].get("blank")]
    note, pick = "", None
    if want:
        pick = next((n for n in heads if _head_text(n) == P._ws(want)), None)
        if pick is None:
            note = f"넣을 자리 「{want}」 없음 — 기본 자리"
    if pick is None:   # 첫 잎 — 항목 안에 자식 소제목이 없는 첫 소제목
        pick = next((n for n in heads if not any(m.get("parent") == n["id"] for m in heads)), None)
    at = pick["id"] if pick else roots[0]
    k = roots.index(at) + 1
    stops = {n["id"] for n in heads}
    end = next((j for j in range(k, len(roots)) if roots[j] in stops), len(roots))
    return at, _head_text(pick) if pick else "", roots[k:end], note


def _count(src):
    c = Counter(x.get("type") for b in src for x in core._under(b))
    return c["paragraph"], c["table"], c["image"]


def plan(to_side, from_side, to_values, from_values, pairs, applied=None, part=None, singles=None):
    """넣기 계획(모듈 설명) → {"items": [{group, value, to, from, anchor, anchorText, src, blocks, paragraphs, tables, pictures, placeholders, hash, skip, detail}], "counts"}.
    part · own = 같은 양식 취합(spec_취합 ② §10-2)의 지금 기관 문서(작업 id)와 그 반영할 기관: 넣은 기록에 적힌 문서(`applied[k].part`)가 다른 문서면 「원본 바뀜」 이 아니라 **겹침**(occupied — 앞 문서의 내용을 둔다) ·
    singles = 기관 문서의 홑 기관 라벨 {라벨 id: {label, roots}}(merge_pairs._singles — 구분 기준 엔진이 묶음으로 못 읽는 조각 문서의 항목): 엔진 항목에 없는 원본 항목은 여기서 찾는다."""
    applied = applied or {}
    t_idx, t_items, nodes = _engine(to_side, to_values)
    f_idx, f_items, _ = _engine(from_side, from_values)
    out, ambiguous = [], 0
    for g in pairs["groups"]:
        if g["kind"] != "paragraph" or not g.get("to"):
            continue
        if g["status"] != "paired":
            ambiguous += g["status"] == "ambiguous"
            continue
        for pi in g["items"]:
            key, frm = pi["to"]["id"], (pi.get("from") or {}).get("id")
            row = {"group": g["id"], "value": pi["value"], "to": key, "from": frm, "anchor": None, "anchorText": "", "src": [], "blocks": 0,
                   "paragraphs": 0, "tables": 0, "pictures": 0, "placeholders": [], "hash": None, "skip": None, "detail": ""}
            out.append(row)
            ti, si = t_items.get(key), f_items.get(frm) or (singles or {}).get(frm)
            if pi.get("status") == "outside":   # 고르지 않은 구성(연결 목록이 적어 둔 것 — merge_take.narrow): 넣지 않는다
                row.update(skip="outside", detail=TK.OUT)
                continue
            if ti is None:
                row.update(skip="shape", detail="목적 항목을 다시 못 찾음")
                continue
            src = _source(f_idx, si) if si else []
            if not src:
                row.update(skip="noSource", detail="원본 항목 없음" if si is None else "원본 항목에 내용 없음")
                continue
            h = _hash(src)
            row.update(src=[b["id"] for b in src], blocks=len(src), hash=h)
            row["paragraphs"], row["tables"], row["pictures"] = _count(src)
            if key in applied and part is not None and applied[key].get("part") not in (None, part):
                row.update(skip="occupied", detail="다른 기관 문서가 먼저 넣은 자리 — 그대로 둠")
                continue
            if key in applied:
                same = applied[key].get("hash") == h
                row.update(skip="applied" if same else "changed", detail="" if same else "원본 바뀜 — 다시 넣지 않음")
                continue
            at, text, place, note = _anchor(ti, nodes, g.get("anchor"))
            row.update(anchor=at, anchorText=text, detail=note)
            blocks = [b for r in place if (b := t_idx.get(r)) and not b.get("captionOf")]
            if any(b.get("type") == "table" for b in blocks):
                row.update(skip="tables", detail="넣을 자리에 양식 표 — 표 칸 넣기 몫")
            elif hit := next((b for b in blocks if not (_blank(b) or _placeholder(b) or (b.get("text") or "").lstrip().startswith("※"))), None):   # 그림도 여기(글 없음 ≠ 빈 줄)
                row.update(skip="occupied", detail=P._ws(hit.get("text"))[:P.TEXT_MAX] or "그림")
            else:
                row["placeholders"] = [b["id"] for b in blocks if _placeholder(b)]
    c = Counter(r["skip"] or "todo" for r in out)
    return {"items": out, "counts": {"todo": c["todo"], **{k: c[k] for k in (*SKIPS, "shape")}, "ambiguous": ambiguous}}


def _dropped(from_doc, sid):
    """원본 블록 sid 를 복사할 때 빠지는 요소 이름들 — 문단은 제 표·그림(따로 복사되는 블록)을 빼고 센다."""
    el = from_doc._ids[sid]
    if etree.QName(el).localname != "p":
        return [etree.QName(e).localname for e in el.iter(*DROP_ON_COPY)]
    return [etree.QName(e).localname for r in el for c in r if etree.QName(c).localname not in ("tbl", "pic") for e in c.iter(*DROP_ON_COPY)]


def apply(to_doc, from_doc, plan, convert=None):
    """계획의 할 일 항목을 목적 문서에 넣는다(모듈 설명) → {"inserted": {항목 key: [새 블록 id]}, "applied": {항목 key: {from, hash}}, "dropped": [{item, src, what}], "counts"}."""
    inserted, done, dropped, gone = {}, {}, [], 0
    for row in plan["items"]:
        if row["skip"] is not None:
            continue
        dropped += [{"item": row["to"], "src": s, "what": w} for s in row["src"] for w in _dropped(from_doc, s)]
        new = to_doc.insert_after(row["anchor"], [{"kind": "copy", "srcId": s} for s in row["src"]], src=from_doc)
        res = convert(row["anchor"], list(zip(row["src"], new))) if convert else None
        for pid in row["placeholders"]:
            to_doc.delete_blocks(pid, pid)
        gone += len(row["placeholders"])
        inserted[row["to"]] = new
        done[row["to"]] = {"from": row["from"], "hash": row["hash"]}
        if isinstance(res, dict) and res.get("over"):   # 넘친 줄의 기록(merge_convert.record — spec_병합 ② §5-5 7): 고리가 돌려줄 때만 적는다(다시 맞추기의 근거)
            done[row["to"]]["over"] = res["over"]
    return {"inserted": inserted, "applied": done, "dropped": dropped,
            "counts": {"items": len(inserted), "blocks": sum(map(len, inserted.values())), "placeholders": gone, "dropped": len(dropped)}}
