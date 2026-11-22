"""빈 구역 지우기 끝점(spec_워크플로우 ② §18-23 「빈 구역 지우기」) — `GET /api/docs/{id}/zone-prune`(미리 보기 — 문서 안 바뀜) · `POST …/zone-prune {expectRev}`(한 번에 지우기 — 실행 취소 1).
찾기 · 지우기는 `app/zone_prune.py`(순수). 연구개발과제 문서(hwpx · 구분 기준 판독의 관문 `division_scan_api.inputs`)이고 프로젝트 구성 값이 있을 때만 — 아니면 `reasons` 를 싣고 빈 목록.

- 값 = 반영한 값 → 입력 값(편집 구역 · 구분 기준 판독과 같은 차례) · prior · hints 도 그 둘과 같게(`division_scan_api.inputs`).
- 그림 · 개체(블록 JSON 에 안 보이는 묶음 개체 포함)가 든 문단은 문서의 XML 로 가린다(`_objects` — 잠금 안에서 뜬 id 집합).
- 이름(`name`)은 편집 구역의 이름(`zones.label_text(zones.label_of(zones_api.read(s), 라벨 id))`) — 기관 · 차년도를 여기서 다시 셈하지 않는다.
- 읽기는 (문서 차례 · 값 · prior · hints)가 같으면 셈한 것을 쓴다(`_CACHE` — 워크플로우 상태가 GET …/flow 마다 부른다: 큰 문서는 1초 안팎)."""
import json
import logging
import threading
from collections import Counter

from fastapi import APIRouter, Body, HTTPException

from app import zone_prune

router = APIRouter()
log = logging.getLogger("uvicorn.error")
_CACHE = {}   # 문서 id → (열쇠, 찾은 것)
_LOCK = threading.Lock()
CACHE_MAX = 16
REASON = {"unsupportedForm": "hwpx 문서가 아닙니다", "notRnd": "연구개발과제 양식이 아닙니다", "noValues": "프로젝트 구성 값이 없습니다"}


def _guide_ids(found, blocks):
    """양식 안내 블록 id(작성 요령 표 · <참고 N> 자료 · 안내뿐인 ※ 줄) — 빈 구역을 셀 때 내용으로 보지 않는다(작성요령 삭제 앞이든 뒤든 같은 답)."""
    from app.division_profiles import _structure as structure
    from app.division_profiles.rnd import core
    idx = structure.index_blocks(blocks)
    out = set()
    for t in found.get("tables") or ():
        b = idx.get(t["id"])
        out |= {x["id"] for x in core._under(b)} if b is not None else set()
    top = [b["id"] for b in blocks]
    pos = {i: k for k, i in enumerate(top)}
    for r in found.get("refs") or ():
        a, e = pos.get(r["id"]), pos.get(r.get("last"))
        for k in range(a, (e if e is not None and e >= a else a) + 1) if a is not None else ():
            out |= {x["id"] for x in core._under(blocks[k])}
        out.add(r["id"])
    out |= {n["id"] for n in found.get("notes") or () if n.get("whole")}
    return out


def _objects(doc):
    """그림 · 개체(표 말고)가 든 문단 id 집합 — 블록 JSON 에 안 보이는 묶음 개체(hp:container)까지(세션 잠금 안에서)."""
    from app import hwpx_doc as H
    objs = H.OBJECTS - {H.TBL}
    return {i for i, el in doc._ids.items() if el.tag == H.P and any(o.tag in objs for r in el.iterchildren(H.RUN) for o in r)}


def _taken(s):
    """(세션 잠금 안) 셈에 쓸 것 → dict | 까닭 key(REASON)."""
    from app import division_scan_api as DSA
    from app import form_cleanup
    if s.fmt != "hwpx":
        return "unsupportedForm"
    blocks = s.doc.blocks()
    inp = DSA.inputs(s, blocks)
    if inp is None:
        return "notRnd"
    if inp["values"] is None:
        return "noValues"
    key = json.dumps([s.rev, s.base_n, inp["values"], inp["hints"], inp["prior"]], ensure_ascii=False, sort_keys=True, default=str)
    with _LOCK:
        hit = _CACHE.get(s.id)
    if hit is not None and hit[0] == key:
        return {"key": key, "found": hit[1], "rev": s.rev}
    from app.division_profiles import rnd
    return {"key": key, "rev": s.rev, "blocks": blocks, "values": inp["values"], "levels": rnd.levels_of(blocks), "hints": [h["para"] for h in inp["hints"]] or None,
            "prior": inp["prior"], "guides": _guide_ids(form_cleanup.find(s.doc), blocks), "objects": _objects(s.doc)}


def _find(t):
    if "found" in t:
        return t["found"]
    return zone_prune.find(t["blocks"], t["values"], t["levels"], hints=t["hints"], prior=t["prior"], guide_ids=t["guides"], has_object=t["objects"].__contains__)


def _remember(doc_id, key, found):
    with _LOCK:
        _CACHE.pop(doc_id, None)
        _CACHE[doc_id] = (key, found)
        while len(_CACHE) > CACHE_MAX:
            del _CACHE[next(iter(_CACHE))]


def count(doc_id):
    """워크플로우 상태가 읽는 것 → {rev, counts, kept, reasons[]} — 문서 안 바뀜 · 이름 없이(빠르게)."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
    if isinstance(t, str):
        return {"rev": s.rev, "counts": {"items": 0, "blocks": 0, "rows": 0, "cols": 0, "kept": 0}, "kept": 0, "reasons": [t], "why": REASON[t]}
    found = _find(t)
    _remember(doc_id, t["key"], found)
    return {"rev": t["rev"], "counts": found["counts"], "kept": len(found["kept"]), "reasons": [], "why": ""}


def _names(s, items):
    """항목 라벨 id → 편집 구역의 이름(「한국선급 · 1단계 2차년도」) — 못 읽으면 라벨 글."""
    try:
        from app import zones, zones_api
        view = zones_api.read(s)
    except Exception:   # noqa: BLE001 — 이름은 보기일 뿐(못 읽으면 라벨 글)
        log.exception("[빈 구역 지우기] 편집 구역을 읽지 못했습니다")
        return {}
    return {it["label"]: zones.label_text(zones.label_of(view, it["label"]), view) for it in items}


@router.get("/api/docs/{doc_id}/zone-prune")
def zone_prune_get(doc_id: str):
    """지울 빈 구역(문서 안 바뀜) → {rev, reasons[], why, items[{key, kind, kindName, dim, table, label, labelText, name}], kept[{key, kind, dim, why, labels[], message?}], counts{items, blocks, rows, cols, kept}}."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
        rev = s.rev
    if isinstance(t, str):
        return {"rev": rev, "reasons": [t], "why": REASON[t], "items": [], "kept": [], "counts": {"items": 0, "blocks": 0, "rows": 0, "cols": 0, "kept": 0}}
    found = _find(t)
    _remember(doc_id, t["key"], found)
    names = _names(s, found["items"])
    items = [{k: it[k] for k in ("key", "kind", "dim", "table", "label", "labelText")} | {"kindName": zone_prune.KIND_NAME[it["kind"]], "name": names.get(it["label"]) or ""} for it in found["items"]]
    return {"rev": t["rev"], "reasons": [], "why": "", "items": items, "kept": found["kept"], "counts": found["counts"]}


@router.post("/api/docs/{doc_id}/zone-prune")
def zone_prune_post(doc_id: str, body: dict = Body(default={})):
    """{expectRev?} → 지금 문서에서 다시 찾아 한 번에 지운다(구조 편집 트랜잭션 하나 — 실행 취소 1 · rev +1 · 기록 `zonePrune`). 지울 것이 없으면 {nothing: true}.
    표준 검사의 기준선 = 올린 원본 + 편집 바로 전 문서의 위반(작성요령 삭제와 같게 — 앞 단계가 옮겨 온 위반을 이 지우기 탓으로 보지 않는다). → {done{removed, skipped, labels}, …편집 상태}. 409 expectRev 가 지금과 다름."""
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    with s.lock:
        if body.get("expectRev") is not None and body["expectRev"] != s.rev:
            raise HTTPException(409, "미리 본 뒤 문서가 바뀌었습니다 — 다시 읽으세요")
        t = _taken(s)
        if isinstance(t, str):
            raise HTTPException(409, REASON[t])
        found = _find(t)
        if not found["items"]:
            return {"nothing": True, **s.state()}
        chk = s.kit["check"]
        pre = chk.counts(chk.check_doc(s.doc))
        done = {}

        def run():
            done.update(zone_prune.apply(s.doc, found))
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None, "log": {"removed": done["removed"], "skipped": len(done["skipped"])}}

        def check(s_, out, base, header):
            return chk.verdict(s_.doc, {"schema": Counter(base["schema"]) | pre["schema"], "rules": Counter(base["rules"]) | pre["rules"]}, chk.check_doc(s_.doc))
        out, after = server._transact(s, run, "zonePrune", req={"counts": found["counts"]}, check=check)
        with _LOCK:
            _CACHE.pop(doc_id, None)
        if after is None:
            return out
        return {"done": done, **s.state()}
