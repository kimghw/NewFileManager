"""사람이 하는 일의 「했음」 끝점(spec_워크플로우 ② §18-7 · §18-12 ⑦) — 저장은 app/flow_hands.py · 판은 app/unit_steps.py `hand_ver`. server.py 가 include 한다.

- `GET /api/works/{wid}/flow/hand` → {target(목적 문서 id | null), lines[{key, name, does, on, ver, done, at?}]} — wid = 그 묶음의 어느 문서든(서버가 목적 문서를 찾는다 — unit_steps.pair).
- `POST /api/works/{wid}/flow/hand/{key}` {ver} → {line} — 사람이 「했음」(화면이 읽은 판을 싣는다 — 정의 · 줄의 글이 그 사이 바뀌었으면 409 「다시 읽은 뒤」) · 404 = 그 워크플로우에 그런 줄이 없음.
- `DELETE /api/works/{wid}/flow/hand/{key}` → {line} — 「했음 취소」.
에이전트의 행동 목록에는 이 끝점을 넣지 않는다(사람의 확인 — astra). 문서는 바뀌지 않는다."""
from fastapi import APIRouter, Body, HTTPException

from app import flow_hands

router = APIRouter()
HAND_KEY = r"hand[1-9][0-9]?"


def _lines(wid):
    """(목적 문서 id, 그 워크플로우의 사람이 하는 일 줄들 [{key, name, does, on, ver}]) — 묶음 · 정의를 못 찾으면 404."""
    from app import unit_steps, workflow
    p = unit_steps.pair(wid)
    if p is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    task = workflow.task_of(p["job"]) if p["job"] else None
    tgt = (p.get("target") or {}).get("id")
    if task is None or not tgt:
        return tgt, []
    return tgt, [{"key": s["key"], "name": s["name"], "does": s["does"], "on": s["on"], "ver": unit_steps.hand_ver(task, s["key"])}
                 for g in task.get("stages") or () for s in g["steps"] if s["key"].startswith("hand") and s["key"][4:].isdigit()]


def _view(tgt, line):
    r = flow_hands.read(tgt).get(line["key"]) if tgt else None
    return {**line, "done": bool(r) and r["ver"] == line["ver"], **({"at": r["at"]} if r and r["ver"] == line["ver"] else {})}


@router.get("/api/works/{wid}/flow/hand")
def hand_get(wid: str):
    tgt, lines = _lines(wid)
    return {"target": tgt, "lines": [_view(tgt, x) for x in lines]}


def _one(wid, key):
    tgt, lines = _lines(wid)
    line = next((x for x in lines if x["key"] == key), None)
    if line is None or not tgt:
        raise HTTPException(404, "이 워크플로우에 그런 「사람이 하는 일」 줄이 없습니다")
    return tgt, line


@router.post("/api/works/{wid}/flow/hand/{key}")
def hand_post(wid: str, key: str, body: dict = Body(default={})):
    tgt, line = _one(wid, key)
    if body.get("ver") != line["ver"]:
        raise HTTPException(409, "이 줄의 정의나 글이 바뀌었습니다 — 다시 읽은 뒤 「했음」 을 누르세요")
    from app import unit_steps, works
    p = unit_steps.pair(wid) or {}
    docs = [d["id"] for d in (p.get("source"), p.get("target")) if d] if line["on"] in ("both", "flow") else [((p.get(line["on"]) or {}).get("id"))] if line["on"] in ("source", "target") else []
    flow_hands.mark(tgt, key, line["ver"], [d for d in docs if d])
    works.log(tgt, "flowHand", line=key, done=True)
    return {"line": _view(tgt, line)}


@router.delete("/api/works/{wid}/flow/hand/{key}")
def hand_delete(wid: str, key: str):
    tgt, line = _one(wid, key)
    if flow_hands.clear(tgt, key):
        from app import works
        works.log(tgt, "flowHand", line=key, done=False)
    return {"line": _view(tgt, line)}
