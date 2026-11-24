"""같은 양식 취합 API — 기관 문서 등록부 · 출처 원장 · 수정본 반영(spec_취합 ② §10 — 조립 틀 `collect`: 기관이 같은 양식(사업계획서)으로 따로 쓴 문서 여럿 → 사업계획서 하나).

엔진은 이관의 것(app/merge_api.py — 자리 연결 · 넣기 계획 · 내용 반영)을 **지금 원본 하나**로 쓴다. 이 모듈은 그 위에 얹는 것만 지닌다:
- **등록부**(목적 작업 폴더 `collect.json` — app/merge_collect.py 의 꼴): 같은 묶음(프로젝트 · 워크플로우 · 라운드)의 기관 문서(`task.file == 원본 종류`)를 저절로 싣고(올린 차례), 문서마다 반영할 기관 · 공통 자리 포함 · 수정본 표시(revOf)를 둔다.
  `GET /api/docs/{to}/collect` · `PUT …/collect/parts/{part} {orgs?, common?, revOf?}` · `POST …/collect/parts/{part}/auto`(자동 지정) · `POST …/collect/parts/{part}/bind`(엔진의 지금 원본을 그 문서로).
- **문맥** `context(to, part)` — merge_api 가 연결 목록 · 넣기 계획 · 반영에서 읽는다(반영할 기관 · 공통 자리 · 수정본 · 등록부의 판).
- **원장** `record(s, src, C, frm, plan, done)` — 「내용 반영」 의 run() 안에서 부른다: 실제로 쓴 본문 블록 · 표 칸 · 늘린 행을 출처 이벤트(편집 구역 — app/zones_api.py)로 남기고 그 이벤트에 원장 줄(`led`)을 얹는다.
  출처는 세션 상태라 실행 취소 · 표준 검사 실패와 함께 돌아간다(문서와 원장이 따로 놀지 않는다).
- **수정본 반영** `POST …/collect/parts/{part}/revise/plan` → `…/revise/apply {planId}` — 앞 제출본(사슬)의 원장 줄 ↔ 수정본의 짝 ↔ 지금 목적 문서의 3방향(merge_collect 의 셈). 스크립트만(LLM 없음) · 편집 하나 · 실행 취소 1.
  바뀐 단순 문단 · 표 칸만 제자리에서 고치고, 수정본에 새로 생긴 블록은 앞뒤가 분명할 때만 넣고, 새 자리(앞 제출본이 안 넣은 빈 자리)는 보통 넣기 규칙으로 같은 편집에 넣는다. 지우지 않는다."""
import threading
import time
import uuid
from collections import Counter

from fastapi import APIRouter, Body, HTTPException

from app import merge_collect as MC
from app import merge_pairs as P
from app import projects, works

router = APIRouter()
_LOCK = threading.Lock()
_MEM, _RPLANS = {}, {}   # 작업 저장이 꺼졌을 때의 collect.json · 목적 작업 id → 마지막 수정 계획(메모리만)


def is_collect(job):
    """그 워크플로우가 같은 양식 취합(조립 틀 collect)인가."""
    from app import custom_tasks
    t = custom_tasks.get(job) if job else None
    return bool(t) and t.get("shape") == "collect"


def _job(to_id):
    return ((works.work(to_id) or {}).get("task") or {}).get("job") or ""


def _store(wid, data=None):
    d = works.folder(wid)
    if data is None:
        return (works._read_json(d / "collect.json") if d is not None and (d / "collect.json").is_file() else _MEM.get(wid)) or {}
    if d is not None:
        works._write_json(d / "collect.json", data)
    else:
        _MEM[wid] = data
    return data


def _bundle(to_id):
    """같은 묶음(프로젝트 · 워크플로우 · 라운드)의 기관 문서 작업들(올린 차례) — 프로젝트가 없는 문서는 묶음이 없다."""
    from app import custom_tasks
    task = (works.work(to_id) or {}).get("task") or {}
    kind = custom_tasks.source_file(task.get("job") or "")
    if not task.get("project") or not kind:
        return []
    key = projects.group_key(task)
    rows = [w for w in works.list_works() if w["id"] != to_id and (w.get("task") or {}).get("file") == kind and projects.group_key(w.get("task")) == key]
    return sorted(rows, key=lambda w: (w.get("created") or 0, w["id"]))


def load(to_id):
    """등록부(정리한 꼴) — 묶음의 기관 문서를 맞춘다: 새로 들어온 문서는 끝에 싣고(미지정) 묶음에서 빠진 문서는 뺀다. 바뀌면 판 +1 로 저장."""
    with _LOCK:
        G = MC.clean(_store(to_id))
        have = {w["id"]: w for w in _bundle(to_id)}
        changed = False
        for k in [k for k in G["parts"] if k not in have]:
            G["parts"].pop(k)
            changed = True
        for k, w in have.items():
            if k not in G["parts"]:
                G["parts"][k] = {"orgs": [], "orgsBy": "", "common": False, "revOf": None, "added": w.get("created") or time.time(), "done": None}
                changed = True
        if changed:
            G = MC.clean({**G, "order": [k for k in G["order"] if k in G["parts"]] + [k for k in have if k not in G["order"]], "version": G["version"] + 1})
            _store(to_id, G)
        return G


def order(to_id):
    """등록한 기관 문서의 작업 id(차례대로) — 워크플로우 실행 층의 문(app/unit_steps.py pair)이 읽는다."""
    return list(load(to_id)["order"])


def _name(wid):
    w = works.work(wid) or {}
    return works.shown_name(w.get("name") or wid, w.get("task"), w.get("alias"))


def context(to_id, part):
    """merge_api 가 읽는 문맥(모듈 설명) | None(그 틀이 아님). 등록부에 없는 원본(다른 묶음의 문서를 손으로 고름)은 미지정으로 본다(아무것도 안 넣는다)."""
    if not is_collect(_job(to_id)):
        return None
    G = load(to_id)
    p = G["parts"].get(part) or {}
    return {"part": part, "own": set(p.get("orgs") or ()), "orgs": list(p.get("orgs") or ()), "common": bool(p.get("common")), "revOf": p.get("revOf"),
            "later": MC.later(G, part) if part else [], "version": G["version"], "name": _name(part) if part else ""}


def _values(to_id):
    from app import merge_api
    try:
        return merge_api._read(to_id, target=True).get("values")
    except HTTPException:
        return None


def _led_ids(s, part, orgs=None):
    """그 기관 문서의 출처 이벤트의 목적 id 가운데 **지금 문서에 붙어 있는 것**(실행 취소 · 지우기로 떼어 낸 요소는 뺀다 — 문서의 id 표에는 남는다). orgs 를 주면 그 반영할 기관으로 넣은 이벤트만
    (지정을 바꾼 뒤 옛 지정으로 넣은 것을 새 지정의 「넣은 것」 으로 세지 않는다). 부르는 쪽이 세션 잠금을 잡는다."""
    from app import zones_api
    want = None if orgs is None else sorted(orgs)
    return [i for e in s.zones["origins"] if e.get("part") == part and (want is None or sorted(e.get("orgs") or ()) == want)
            for i in e.get("ids") or () if zones_api._attached(s, i)]


def _led_alive(to_id, part, orgs=None):
    """위의 수 | None(문서를 못 엶). 세션을 연다(상태가 「모름」 인 채로 「반영함」 을 믿지 않게)."""
    from app import server
    try:
        s = server._sess(to_id)
        with s.lock:
            return len(_led_ids(s, part, orgs))
    except Exception:   # noqa: BLE001
        return None


def _state(to_id, G, k):
    """기관 문서 한 줄의 (상태, 글) — unassigned · superseded · revision · todo · done · left(모듈 머리의 꼴 — 워크플로우 실행기 · 대시보드가 읽는다).
    끝 표식(done)은 원본 문서의 차례 · 지정(기관 · 공통 · 수정본 표시)이 그대로이고 **넣은 것이 표식을 찍을 때 그대로 지금 문서에 붙어 있을 때만** 믿는다(일부라도 실행 취소 · 지워졌으면 다시 넣을 차례 —
    다시 계획하면 남은 것만 할 일이 되고 표식이 지금 수로 다시 찍힌다)."""
    p = G["parts"][k]
    w = works.work(k) or {}
    d = p.get("done") or None
    sig = [sorted(p["orgs"]), p["common"], p["revOf"]]
    valid = bool(d) and d.get("srcRev") == w.get("rev") and d.get("sig") == sig
    if valid and _led_alive(to_id, k, p["orgs"]) != (d.get("total") or 0):
        valid = False
    later = MC.later(G, k)
    if not p["orgs"]:
        return "unassigned", "반영할 기관 미지정 — 넣지 않습니다"
    left = sum((d.get("left") or {}).values()) if valid else 0
    tail = f" · 남은 것 {left}(확인 필요 · 겹침)" if left else ""
    if later:
        return "superseded", "수정본이 등록됨 — 넣기는 수정본이 맡습니다" + (" (앞서 반영함)" if valid else "")
    if p["revOf"]:
        if valid:
            return ("left" if left else "done"), f"수정본 반영함 — 고친 곳 {d.get('wrote', 0)}{tail}"
        return "revision", f"「{_name(p['revOf'])}」 의 수정본 — 「수정본 반영」 으로 바뀐 곳만 고칩니다"
    if valid:
        if not (d.get("total") or 0):
            return "left", "넣을 수 있는 자리를 찾지 못했습니다 — 연결 목록에서 확인하세요" + tail
        return ("left" if left else "done"), f"반영함 — 본문 블록 · 표 칸 {d.get('total', 0)}곳{tail}"
    return "todo", "넣을 차례" if not d else "문서 · 지정이 바뀌었거나 넣은 것이 되돌려져 다시 넣을 차례"


NO_ORGS = "프로젝트 구성(기관)이 아직 없어 반영할 기관을 고를 수 없습니다 — 「프로젝트 구성 추출」 뒤에 고릅니다"   # 미지정 문서의 글(고를 기관이 없을 때) — 상태 식 workflow_units._c_part 도 같은 글


def view(to_id):
    """등록부의 보기(GET …/collect) — 워크플로우 실행기 · 대시보드 · 화면의 「기관 문서」 목록이 읽는다."""
    if not is_collect(_job(to_id)):
        return {"collect": False, "version": 0, "orgs": [], "parts": []}
    G = load(to_id)
    values = _values(to_id)
    orgs = [{"key": P.org_key(n), "name": str(n), "role": r} for r, n in (P._orgs(values) if (values or {}).get("orgs") else ()) if P.org_key(n)]
    names = {o["key"]: o["name"] for o in orgs}
    parts = []
    for i, k in enumerate(G["order"]):
        p = G["parts"][k]
        st, text = _state(to_id, G, k)
        if st == "unassigned" and not orgs:   # 고를 기관이 없다 — 고르기가 꺼진 까닭을 그 줄에 보인다(풍선 도움말에만 두면 「왜 선택이 안 되지?」: 2026-11-24 사용자)
            text = NO_ORGS
        parts.append({"work": k, "name": _name(k), "order": i, "orgs": list(p["orgs"]), "orgNames": [names.get(o, o) for o in p["orgs"]], "orgsBy": p["orgsBy"], "common": p["common"],
                      "revOf": p["revOf"], "revName": _name(p["revOf"]) if p["revOf"] else "", "later": MC.later(G, k), "state": st, "text": text, "done": p.get("done")})
    return {"collect": True, "version": G["version"], "orgs": orgs, "parts": parts}


def _need(to_id, part):
    if not is_collect(_job(to_id)):
        raise HTTPException(400, "같은 양식 취합(조립한 워크플로우)의 목적 문서가 아닙니다")
    G = load(to_id)
    if part not in G["parts"]:
        raise HTTPException(404, "이 취합에 등록된 기관 문서가 아닙니다")
    return G


def _busy(to_id):
    from app import server
    task = (works.work(to_id) or {}).get("task") or {}
    server._flow_busy(to_id, task.get("project"))   # 도는 워크플로우 실행에 든 묶음이면 409(바쁨 막이)


@router.get("/api/docs/{doc_id}/collect")
def collect_get(doc_id: str):
    if works.work(doc_id) is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    return view(doc_id)


@router.put("/api/docs/{doc_id}/collect/parts/{part}")
def part_put(doc_id: str, part: str, body: dict = Body(...)):
    """{orgs?: [기관 이름 | 이름 꼴], common?: bool, revOf?: 앞 제출본 작업 id | null} → 보기. 사람이 정한 것으로 적는다(orgsBy user). 400 모르는 기관 · 수정본으로 삼을 수 없는 문서."""
    G = _need(doc_id, part)
    _busy(doc_id)
    p = dict(G["parts"][part])
    if "orgs" in body:
        known = {P.org_key(n) for _, n in P._orgs(_values(doc_id) or {"orgs": {"lead": "", "joint": []}})}
        orgs = [P.org_key(o) for o in body.get("orgs") or () if isinstance(o, str) and P.org_key(o)]
        if any(o not in known for o in orgs):
            raise HTTPException(400, "프로젝트 구성에 없는 기관입니다")
        p.update(orgs=list(dict.fromkeys(orgs)), orgsBy="user" if orgs else "")
    if "common" in body:
        p["common"] = body.get("common") is True
    if "revOf" in body:
        was = body.get("revOf") or None
        if was is not None and (was not in G["parts"] or was == part or part in MC.chain(G, was) or any(k != part for k in MC.later(G, was))):
            raise HTTPException(400, "그 문서의 수정본으로 삼을 수 없습니다(이 취합의 다른 기관 문서 가운데 아직 수정본이 없는 것을 고르세요)")
        p["revOf"] = was
    with _LOCK:
        G = MC.clean(_store(doc_id)) or G
        G["parts"][part] = {**(G["parts"].get(part) or {}), **p}
        _store(doc_id, MC.clean({**G, "version": G["version"] + 1}))
    _drop_plans(doc_id)
    return view(doc_id)


def _drop_plans(to_id):
    from app import merge_api
    merge_api._PLANS.pop(to_id, None)
    _RPLANS.pop(to_id, None)


def _labels(part, values):
    """그 문서의 기관 라벨이 밝힌 프로젝트 기관 이름 꼴의 모음 — 2단계 그래프의 줄 가운데 기관 낱말(주관 · 공동연구개발기관 …)이 든 줄에 적힌 이름."""
    from app import merge_api
    from app.division_profiles.rnd import core
    try:
        side = merge_api._read(part)
    except HTTPException:
        return set()
    keys = [k for k in (P.org_key(n) for _, n in P._orgs(values)) if k]
    out = set()
    for n in (side.get("graph") or {}).get("nodes") or ():
        text = f"{n.get('letter') or ''} {n.get('text') or ''}"
        if core.ORG_RE.search(text):
            t = P.org_key(text)
            hit = [k for k in keys if k in t]
            if hit:
                out.add(max(hit, key=len))
    return out


def part_auto(doc_id, part):
    """반영할 기관 자동 지정 — 이미 지정돼 있으면 안 바꾼다 → 보기 + auto{part, org, by, why}."""
    G = _need(doc_id, part)
    p = G["parts"][part]
    if p["orgs"]:
        return {**view(doc_id), "auto": {"part": part, "org": p["orgs"][0], "by": p["orgsBy"] or "user", "why": "이미 지정됨"}}
    values = _values(doc_id)
    if not (values or {}).get("orgs"):
        return {**view(doc_id), "auto": {"part": part, "org": None, "by": None, "why": "프로젝트 구성(기관)이 아직 없습니다"}}
    raw = lambda wid: (works.work(wid) or {}).get("name") or ""  # noqa: E731 — 올린 파일 이름(보이는 이름이 아니라)
    others = [raw(k) for k in G["order"] if k != part] + [raw(doc_id)]
    org, by, why = MC.auto_org(raw(part), others, values, _labels(part, values))
    if org:
        with _LOCK:
            G = MC.clean(_store(doc_id))
            if part in G["parts"] and not G["parts"][part]["orgs"]:
                G["parts"][part].update(orgs=[org], orgsBy=by)
                _store(doc_id, MC.clean({**G, "version": G["version"] + 1}))
        _drop_plans(doc_id)
    return {**view(doc_id), "auto": {"part": part, "org": org, "by": by or None, "why": why}}


@router.post("/api/docs/{doc_id}/collect/parts/{part}/auto")
def part_auto_post(doc_id: str, part: str):
    _busy(doc_id)
    return part_auto(doc_id, part)


def bind(doc_id, part):
    """엔진(merge_api)의 지금 원본을 그 기관 문서로 못 박는다 → {"from": part}. 이미 그 문서면 아무것도 안 한다."""
    from app import merge_api
    _need(doc_id, part)
    saved = merge_api._store(doc_id)
    if merge_api._mate(doc_id, saved)[1] != part or saved.get("src") not in (None, part):
        merge_api.merge_pairs_post(doc_id, {"from": part})
    if merge_api._mate(doc_id, merge_api._store(doc_id))[1] != part:
        raise HTTPException(409, "원본 문서를 그 기관 문서로 정하지 못했습니다(같은 프로젝트 · 워크플로우 · 라운드의 문서여야 합니다)")
    return {"from": part}


@router.post("/api/docs/{doc_id}/collect/parts/{part}/bind")
def bind_post(doc_id: str, part: str):
    _busy(doc_id)
    return bind(doc_id, part)


# ---- 원장 ----

class _Texts:
    """문서의 블록 · 칸 → 글 · 종류 · 칸의 표 · 본문 최상위 차례(칸 안 블록까지 — 중첩 표 포함)."""

    def __init__(self, doc):
        self.text, self.kind, self.table_of, self.order = {}, {}, {}, {}
        for i, b in enumerate(doc.blocks()):
            self.order[b["id"]] = i
            self._walk(b)

    def _walk(self, b):
        self.text[b["id"]] = b.get("text") or ""
        self.kind[b["id"]] = b.get("type") or "paragraph"
        for c in b.get("cells") or ():
            self.text[c["id"]] = c.get("text") or ""
            self.kind[c["id"]] = "cell"
            self.table_of[c["id"]] = b["id"]
            for x in c.get("blocks") or ():
                self._walk(x)


def _letters(graph):
    return {n.get("para") or n["id"]: n.get("letter") or None for n in (graph or {}).get("nodes") or () if not n.get("span")}


def _claim(s, ids):
    """그 목적 id 들을 앞선 출처 이벤트에서 뺀다(현행 출처는 id 마다 하나 — 되돌린 뒤 다시 넣거나 수정본이 고친 자리) · 빈 이벤트는 지운다."""
    ids = set(ids)
    if not ids:
        return
    keep = []
    for e in s.zones["origins"]:
        if not ids.intersection(e.get("ids") or ()):
            keep.append(e)
            continue
        left = [i for i in e.get("ids") or () if i not in ids]
        if left:
            keep.append({**e, "ids": left, **({"led": [r for r in e["led"] if r and r[0] not in ids]} if isinstance(e.get("led"), list) else {})})
    s.zones["origins"] = keep
    s.zones["rev"] += 1


def _add_events(s, C, src, body, cells, grown, new_cells, anchors, tag=None):
    from app import zones_api
    extra = {"src": {"work": src.id, "rev": src.rev}, **({"mode": tag} if tag else {})}
    _claim(s, [r[0] for r in (*body, *cells, *grown)])
    name, orgs, part = C["name"], C["orgs"], C["part"]
    if body:
        zones_api.origin_add(s, part, name, orgs, "filled", [r[0] for r in body], None, extra={**extra, "led": body, "anchors": anchors})
    if cells:
        zones_api.origin_add(s, part, name, orgs, "cells", [r[0] for r in cells], None, extra={**extra, "led": cells})
    if grown:
        zones_api.origin_add(s, part, name, orgs, "rows", list(dict.fromkeys([*new_cells, *(r[0] for r in grown)])), None, extra={**extra, "led": grown})
    return {"body": len(body), "cells": len(cells), "rows": len(grown)}


def record(s, src, C, frm, plan, done, tag=None):
    """「내용 반영」 의 run() 안에서(세션 잠금 안) — 실제로 쓴 것의 출처 이벤트 + 원장 줄(모듈 설명) → {body, cells, rows}(적은 줄 수).
    plan · done = merge_api.merge_apply 의 계획과 반영 결과(fill · fixed · tables — 표 대응 · 빈 자리 · 일정 · 통째 복사는 같은 양식 취합의 계획에 없다: merge_api 의 collect 가지).
    본문 줄에는 그 자리 안의 차례(pos) · 계산 칸에는 표(calc)를 적어 둔다(수정본 반영이 읽는다)."""
    T, S, letters = _Texts(s.doc), _Texts(frm["doc"]), _letters(frm.get("graph"))
    rows_by = {r["to"]: r for r in (*plan["fill"]["items"], *plan["fixed"]["labels"])}
    calc = {c["to"] for k in ("tables", "fixed") for c in (plan.get(k) or {}).get("cells") or () if c.get("calc")}
    body, anchors = [], {}
    for d in (done.get("fill") or {}, done.get("fixed") or {}):
        for key, ids in (d.get("inserted") or {}).items():
            row = rows_by.get(key) or {}
            anchors[key] = row.get("anchor")
            srcs = row.get("src") or ()
            for i, tid in enumerate(ids):
                sid = srcs[i] if i < len(srcs) else None
                simple = sid is not None and S.kind.get(sid) == "paragraph" and T.kind.get(tid) == "paragraph"
                body.append(MC.led_row(tid, sid, S.text.get(sid) if simple else None, T.text.get(tid) if simple else None, key, letters.get(sid), pos=i))
    new_cells = set((done.get("tables") or {}).get("new") or ())
    cells, grown = [], []
    for to, f in [*((done.get("tables") or {}).get("wrote") or ()), *((done.get("fixed") or {}).get("wrote") or ())]:
        if f is None or to not in T.text:
            continue
        (grown if to in new_cells else cells).append(MC.led_row(to, f, S.text.get(f), T.text.get(to), T.table_of.get(to), calc=to in calc))
    return _add_events(s, C, src, body, cells, grown, new_cells, anchors, tag)


def undone(to_id, part):
    """그 기관 문서의 끝 표식을 내린다 — 사람이 그 문서의 연결을 고쳤다(연결 목록에서 원본 묶음을 고르거나 끊음): 다시 계획하면 넣을 것이 생길 수 있다 → 상태가 「넣을 차례」 로(실행이 다시 돈다)."""
    with _LOCK:
        G = MC.clean(_store(to_id))
        p = G["parts"].get(part)
        if p is not None and p.get("done"):
            p["done"] = None
            _store(to_id, G)


def led_matches(s):
    """원장 줄 가운데 지금 목적 문서의 글이 「넣은 글」 그대로인 것의 목적 id 모음 | None(원장 없음) — 「넣은 뒤 정리」 가 반영 전에 읽는다(부르는 쪽이 세션 잠금을 잡는다)."""
    if not any(isinstance(e.get("led"), list) for e in s.zones["origins"]):
        return None
    T = _Texts(s.doc)
    return {r[0] for e in s.zones["origins"] for r in e.get("led") or () if isinstance(r, list) and len(r) > 3 and r[3] is not None and r[0] in T.text and P._ws(T.text[r[0]]) == P._ws(r[3])}


def led_refit(s, matched):
    """정리 직전에 「넣은 글」 과 같던 원장 줄(matched)의 넣은 글을 정리 뒤의 글로 다시 적는다 → 고친 줄 수. 그 편집의 run() 안에서 부른다(출처 스냅샷이 앞 값을 붙들고 있어 실행 취소하면 함께 돌아간다).
    사람이 그 전에 고친 줄(matched 에 없음)은 그대로 — 「사람이 고친 자리」 신호를 지우지 않는다."""
    T, n = _Texts(s.doc), 0
    for e in s.zones["origins"]:
        for r in e.get("led") or ():
            if isinstance(r, list) and len(r) > 3 and r[0] in matched and r[0] in T.text and T.text[r[0]] != r[3]:
                r[3] = T.text[r[0]]
                n += 1
    if n:
        s.zones["rev"] += 1
    return n


def mark_done(s, C, src_rev, plan, done, kind="fill", left=None, wrote=None):
    """그 기관 문서의 끝 표식(등록부 `parts[part].done`) — 「내용 반영」 · 「수정본 반영」 이 끝난 뒤. 상태(반영함 · 남음)가 이것과 살아 있는 원장으로 센다.
    **부르는 쪽이 목적 문서의 세션 잠금을 잡고 있다**(s = 그 세션 — 여기서 다시 잠그지 않는다: 세션 잠금은 다시 들어갈 수 없다)."""
    to_id, rev = s.id, s.rev
    if left is None:
        f, t, x = plan["fill"]["counts"], (plan["tables"]["counts"].get("skipped") or {}), (plan["fixed"]["counts"].get("skipped") or {})
        left = {"ambiguous": f.get("ambiguous", 0) + t.get("ambiguous", 0) + x.get("ambiguous", 0), "occupied": f.get("occupied", 0) + t.get("occupied", 0) + x.get("occupied", 0)}
    if wrote is None:
        wrote = sum((done.get("led") or {}).values()) if done else 0
    total = len(_led_ids(s, C["part"], C["orgs"]))   # 지금 문서에 붙어 있는 넣은 블록 · 칸(이 지정으로 넣은 것만)
    with _LOCK:
        G = MC.clean(_store(to_id))
        p = G["parts"].get(C["part"])
        if p is None:
            return
        p["done"] = {"at": time.time(), "kind": kind, "rev": rev, "srcRev": src_rev, "sig": [sorted(p["orgs"]), p["common"], p["revOf"]], "wrote": wrote,
                     "total": total, "left": left}
        _store(to_id, G)


# ---- 수정본 반영 ----

_PLAIN = {"p", "run", "t", "linesegarray", "lineseg", "nbSpace", "fwSpace", "tab", "lineBreak", "markpenBegin", "markpenEnd",
          "tc", "subList", "cellAddr", "cellSpan", "cellSz", "cellMargin"}


def _plain_ids(doc, ids):
    """글만 든 목적 문단 · 칸의 id — 그 요소 아래에 글 · 빈칸 · 형광펜 표지 말고 다른 것(각주 · 필드 · 자동 번호 · 표 · 그림 …)이 없다. 그런 것이 든 자리의 글을 통째로 바꾸면 그것을 잃는다(수정본 반영이 「확인 필요」 로 둔다)."""
    from lxml import etree
    out = set()
    for i in ids:
        el = doc._ids.get(i)
        if el is not None and all(etree.QName(x).localname in _PLAIN for x in el.iter() if isinstance(x.tag, str)):
            out.add(i)
    return out


def _revise_build(doc_id, part):
    """수정 계획(문서를 안 고친다) — 수정본을 엔진의 원본으로 못 박고 연결 · 넣기 계획의 짝을 낸 뒤 원장과 3방향으로 견준다.
    원장 = 앞 제출본 사슬 + **이 수정본이 앞서 고친 것**(같은 수정본을 다시 계획하면 할 일 0) · 사람이 지운 줄도 자리를 지키는 줄로 읽는다(수정본에 그 글이 그대로면 되살리지 않는다)."""
    from app import merge_api, merge_fill, merge_fixed, server
    G = _need(doc_id, part)
    C = context(doc_id, part)
    if not C["revOf"]:
        raise HTTPException(409, "수정본으로 등록된 문서가 아닙니다 — 「기관 문서」 목록에서 어느 문서의 수정본인지 먼저 정하세요")
    if C["later"]:
        raise HTTPException(409, "이 문서의 수정본이 또 등록돼 있습니다 — 「수정본 반영」 은 가장 뒤의 수정본이 맡습니다")
    if not C["own"]:
        raise HTTPException(409, "반영할 기관이 미지정입니다")
    ver0 = merge_api._collect_ver(doc_id, part)   # 계획이 쓴 등록부의 판 — 끝에서 다시 견준다(그 사이 지정 · 공통 · 수정본 표시가 바뀌면 이 계획을 내지 않는다)
    bind(doc_id, part)
    view, ctx = merge_api._view(doc_id)
    if ctx is None:
        why = [*view["to"]["reasons"], *((view.get("from") or {}).get("reasons") or ())]
        raise HTTPException(409, {"reason": (why or ["blocked"])[0], "message": "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)", "reasons": why})
    _, fs, saved, to, frm = ctx
    base = MC.chain(G, part)
    s = server._sess(doc_id)
    with s.lock:
        applied = merge_api._alive(saved.get("applied"), to)
        fill = merge_fill.plan(to, frm, to["values"], frm["values"], view, applied=applied, part=part, singles=merge_api._singles(fs))
        merge_api._collect_fill_trim(C, fill, frm)
        _, tabs, fixed, _ = merge_api._plan_parts(doc_id, view, saved, to, frm)
        T, S, letters = _Texts(s.doc), _Texts(frm["doc"]), _letters(frm.get("graph"))
        led = MC.led_rows(s.zones["origins"], [*base, part])
        owned = {r[0] for _, r in led}
        own_tables = {r[4] for e, r in led if e.get("kind") != "filled"}
        outside = {t["to"] for t in fixed["tables"] if t.get("why") == "outside"}   # 범위(반영할 기관 · 공통 자리) 밖의 같은 이름 표 — 그 표의 칸 짝은 쓰지 않는다
        pair = {}
        for a, b in tabs.get("pairs") or ():
            pair.setdefault(a, b)
        for a, b in merge_fixed.pairs(to, frm, forced=merge_api._forced(saved))[1]:
            if T.table_of.get(a) not in outside:
                pair.setdefault(a, b)
        for c in (*tabs["cells"], *fixed["cells"]):
            if c.get("from"):
                pair.setdefault(c["to"], c["from"])
        plain = _plain_ids(s.doc, [i for i in owned if i in T.text])
        src_of = {r["to"]: r for r in (*fill["items"], *fixed["labels"]) if r.get("src") and r.get("skip") != "outside"}
        items, by_place, anchors = [], {}, {}
        for e, r in led:
            if e.get("kind") == "filled":
                by_place.setdefault(r[4], []).append(r)
                if (e.get("anchors") or {}).get(r[4]):
                    anchors.setdefault(r[4], e["anchors"][r[4]])
            elif r[0] in T.text:   # 지금 문서에 있는 칸만(지워진 행의 칸은 볼 것이 없다)
                s2 = pair.get(r[0])
                it = MC.cell_item(r, s2, S.text.get(s2) if s2 else None, T.text[r[0]])
                if it and it["status"] == "ready" and r[0] not in plain:
                    it.update(status="hold", detail="각주 · 필드 · 개체가 든 칸 — 글을 바꾸면 그것을 잃습니다: 확인 필요")
                if it:
                    items.append(it)
        for place, rows in by_place.items():
            rows.sort(key=lambda r: MC.meta(r).get("pos", 0))   # 그 자리 안의 차례(일부만 고쳐 다른 이벤트로 옮긴 줄도 제자리에)
            hit = src_of.get(place)
            if hit is None:
                first = next((r for r in rows if r[0] in T.text), None)
                if first is not None:
                    items.append({"kind": "para", "to": first[0], "from": None, "place": place, "was": T.text.get(first[0]), "text": None, "status": "missing", "detail": "수정본에 이 자리가 없음 — 그대로 둠"})
                continue
            new = [{"id": i, "text": S.text.get(i) if S.kind.get(i) == "paragraph" else None, "letter": letters.get(i),
                    "key": P._ws(S.text.get(i)) if S.kind.get(i) == "paragraph" else f"\0{S.kind.get(i)}:{P._ws(S.text.get(i))}"} for i in hit["src"]]
            anchor = anchors.get(place)
            for it in MC.body_items(rows, new, T.text, T.order, plain):
                it["anchor"] = anchor
                if it["kind"] == "add" and it["status"] == "ready" and (not anchor or anchor not in T.text):
                    it.update(status="hold", after=None, detail="넣을 자리의 기준 줄이 지금 문서에 없음 — 확인 필요")
                items.append(it)
        # 새 자리 — 앞 제출본이 안 넣은 빈 자리(보통 넣기 규칙). 앞 사슬(과 이 수정본)이 넣은 **칸은 다시 쓰지 않고**(사람이 지운 칸을 되살리지 않는다), 넣은 적이 있는 **표에는 새 칸 · 새 행을 넣지 않는다**
        # (바뀐 행이 빈 행 · 새 행으로 한 번 더 붙지 않게 — 같은 행인지 가를 열쇠가 없다: spec_취합 ④ ⓚ ㉢)
        n0 = len(tabs["cells"]) + len(tabs["rows"]) + len(fixed["cells"])
        tabs = {**tabs, "cells": [c for c in tabs["cells"] if c["to"] not in owned and c.get("table") not in own_tables], "rows": [r for r in tabs["rows"] if r.get("table") not in own_tables]}
        fixed = {**fixed, "cells": [c for c in fixed["cells"] if c["to"] not in owned and c.get("table") not in own_tables]}
        fixed["todo"] = len(fixed["cells"]) + sum(1 for r in fixed["labels"] if r["skip"] is None)
        held = n0 - len(tabs["cells"]) - len(tabs["rows"]) - len(fixed["cells"])
        fresh_todo = fill["counts"].get("todo", 0) + len(tabs["cells"]) + len(tabs["rows"]) + fixed["todo"]
        c = MC.counts(items)
        plan = {"planId": uuid.uuid4().hex[:12], "part": part, "base": base, "baseRev": to["rev"], "fromRev": frm["rev"], "inputs": merge_api._inputs(doc_id, saved, to, frm),
                "items": items, "counts": c, "fresh": {"fill": fill, "tables": tabs, "fixed": fixed, "todo": fresh_todo, "heldRows": held},
                "todo": c["ready"] + fresh_todo}
    if merge_api._collect_ver(doc_id, part) != ver0:
        raise HTTPException(409, "계획을 세우는 사이 기관 문서의 지정이 바뀌었습니다 — 다시 계획하세요")
    return plan


def _revise_view(plan):
    f = plan["fresh"]
    keys = ("kind", "to", "from", "place", "status", "detail")
    cut = lambda t: None if t is None else (t if len(t) <= 200 else t[:200] + "…")  # noqa: E731
    return {"planId": plan["planId"], "part": plan["part"], "base": plan["base"], "todo": plan["todo"], "counts": plan["counts"],
            "text": MC.count_text(plan["counts"]) + (f" · 새 자리 {f['todo']}" if f["todo"] else "") + (f" · 앞 제출본이 넣은 표의 새 칸 · 새 행 {f['heldRows']}(확인 필요 — 넣지 않음)" if f["heldRows"] else ""),
            "items": [{**{k: it.get(k) for k in keys}, "was": cut(it.get("was")), "text": cut(it.get("text"))} for it in plan["items"] if it["status"] != "same"][:300],
            "fresh": {"todo": f["todo"], "body": f["fill"]["counts"], "tables": {**f["tables"]["counts"], "cells": len(f["tables"]["cells"]), "rows": len(f["tables"]["rows"])},
                      "fixed": {**f["fixed"]["counts"], "cells": len(f["fixed"]["cells"])}, "heldRows": f["heldRows"]}}


def revise_plan(doc_id, part):
    _RPLANS.pop(doc_id, None)
    plan = _revise_build(doc_id, part)
    _RPLANS[doc_id] = plan
    return _revise_view(plan)


@router.post("/api/docs/{doc_id}/collect/parts/{part}/revise/plan")
def revise_plan_post(doc_id: str, part: str):
    return revise_plan(doc_id, part)


def _left(plan):
    """수정 계획에서 사람이 볼 것으로 남는 수 — 끝 표식의 left(상태가 「남은 것 있음」)."""
    f = plan["fresh"]
    return {"overlap": plan["counts"]["overlap"], "hold": plan["counts"]["hold"], "held": f["heldRows"], "ambiguous": f["fill"]["counts"].get("ambiguous", 0)}


def revise_apply(doc_id, part, body):
    """{planId} → 그 수정 계획을 목적 문서에 반영(편집 하나 · 실행 취소 1 · 표준 검사 실패면 전부 되돌리고 422). → {counts{…}, fresh{…}, …편집 상태} | {nothing: true}. 409 = 계획이 없거나 낡음."""
    from app import merge_api, merge_convert, merge_fill, merge_fixed, merge_tables, server
    plan = _RPLANS.get(doc_id)
    if plan is None or plan["planId"] != (body or {}).get("planId") or plan["part"] != part:
        raise HTTPException(409, "수정 계획이 없거나 바뀌었습니다 — 다시 계획하세요")
    C = context(doc_id, part)
    to, frm = merge_api._read(doc_id, target=True), merge_api._read(part)
    s, src = server._sess(doc_id), server._sess(part)
    first, second = sorted((s, src), key=lambda x: x.id)
    with first.lock, second.lock:
        if _RPLANS.get(doc_id) is not plan:
            raise HTTPException(409, "수정 계획이 없거나 바뀌었습니다 — 다시 계획하세요")
        saved = merge_api._store(doc_id)
        if plan["baseRev"] != s.rev or plan["fromRev"] != src.rev or merge_api._mate(doc_id, saved)[1] != part or plan["inputs"] != merge_api._inputs(doc_id, saved, to, frm):
            _RPLANS.pop(doc_id, None)
            raise HTTPException(409, "계획을 세운 뒤 문서 · 등록부 · 자리 연결이 바뀌었습니다 — 다시 계획하세요")
        ready = [it for it in plan["items"] if it["status"] == "ready"]
        fresh = plan["fresh"]
        if not ready and not fresh["todo"]:
            _RPLANS.pop(doc_id, None)
            mark_done(s, C, src.rev, None, None, kind="revise", left=_left(plan), wrote=0)
            return {"nothing": True, "counts": plan["counts"], **s.state()}
        done = {}

        def run():
            letters = _letters(frm.get("graph"))
            convert = merge_convert.converter(s.doc, to["graph"], frm["graph"], over=None)
            S = _Texts(frm["doc"])
            old = {r[0]: r for e in s.zones["origins"] for r in e.get("led") or () if isinstance(r, list) and r}   # 고치기 전의 원장 줄(그 자리 안의 차례 · 계산 칸 표를 잇는다)
            wrote, adds = [], []
            for it in ready:
                if it["kind"] in ("cell", "para"):
                    s.doc.set_text(it["to"], it["text"])
                    wrote.append(it)
            groups = []   # 같은 앞 줄 뒤에 잇달아 넣는 블록은 한 번에(틀 맞춤의 번호가 이어지게)
            for it in ready:
                if it["kind"] != "add":
                    continue
                if groups and groups[-1][0] == (it["after"], it["place"]):
                    groups[-1][1].append(it)
                else:
                    groups.append(((it["after"], it["place"]), [it]))
            for (after, _place), its in groups:
                srcs = [it["from"] for it in its]
                new = s.doc.insert_after(after, [{"kind": "copy", "srcId": x} for x in srcs], src=frm["doc"])
                convert(its[0]["anchor"], list(zip(srcs, new)))
                for i in new:
                    s.doc.fit_image(i)
                adds += list(zip(its, new))
            # 새 자리 — 보통 넣기와 같은 차례(표 묶음 → 같은 이름 자리 → 본문)
            fdone = {"tables": merge_tables.apply(s.doc, frm["doc"], fresh["tables"]), "fixed": merge_fixed.apply(s.doc, frm["doc"], fresh["fixed"]),
                     "fill": merge_fill.apply(s.doc, frm["doc"], fresh["fill"], convert=lambda anchor, pairs: convert(anchor, pairs))}
            T = _Texts(s.doc)
            body, cells, anchors = [], [], {}
            for it in wrote:
                m = MC.meta(old.get(it["to"]) or [])
                row = MC.led_row(it["to"], it["from"], S.text.get(it["from"]), T.text.get(it["to"]), it["place"], letters.get(it["from"]) if it["kind"] == "para" else None, pos=m.get("pos"), calc=bool(m.get("calc")))
                (cells if it["kind"] == "cell" else body).append(row)
                if it["kind"] == "para":
                    anchors[it["place"]] = it.get("anchor")
            for it, i in adds:
                anchors[it["place"]] = it.get("anchor")
                simple = S.kind.get(it["from"]) == "paragraph" and T.kind.get(i) == "paragraph"
                body.append(MC.led_row(i, it["from"], S.text.get(it["from"]) if simple else None, T.text.get(i) if simple else None, it["place"], letters.get(it["from"]), pos=it.get("pos")))
            done["led"] = _add_events(s, C, src, body, cells, [], (), anchors, tag="revise")
            done["fresh"] = record(s, src, C, frm, {"fill": fresh["fill"], "fixed": fresh["fixed"], "tables": fresh["tables"]}, fdone, tag="revise")
            done["fdone"] = fdone
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None,
                    "log": {"planId": plan["planId"], "part": part, "base": plan["base"], "counts": plan["counts"], "wrote": done["led"], "fresh": done["fresh"]}}

        out, after = server._transact(s, run, "collectRevise", req={"planId": plan["planId"], "part": part}, check=server.import_check(src))
        _RPLANS.pop(doc_id, None)
        merge_api._PLANS.pop(doc_id, None)
        if after is None:
            return out
        fdone = done["fdone"]
        saved = merge_api._store(doc_id)
        new = {k: {**v, "ids": list(d["inserted"].get(k) or ()), "part": part} for d in (fdone["fill"], fdone["fixed"]) for k, v in d["applied"].items()}
        if new:
            merge_api._store(doc_id, {**saved, "applied": {**(saved.get("applied") or {}), **new}})
        wrote = sum(done["led"].values()) + sum(done["fresh"].values())
        mark_done(s, C, src.rev, None, None, kind="revise", left=_left(plan), wrote=wrote)
        return {"counts": {**plan["counts"], "wrote": done["led"]}, "fresh": done["fresh"], "text": MC.count_text(plan["counts"]), **s.state()}


@router.post("/api/docs/{doc_id}/collect/parts/{part}/revise/apply")
def revise_apply_post(doc_id: str, part: str, body: dict = Body(...)):
    return revise_apply(doc_id, part, body)


def summary(to_id):
    """상태별 기관 문서 수(대시보드의 한 줄) — {unassigned, superseded, revision, todo, done, left}."""
    c = Counter(p["state"] for p in view(to_id)["parts"])
    return {k: c.get(k, 0) for k in ("unassigned", "superseded", "revision", "todo", "done", "left")}
