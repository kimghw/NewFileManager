"""TASK 옵션 끝점(GET·PUT /api/works/{wid}/task-options — spec_구역 ② §1 「TASK 옵션 — TASK 묶음마다」). server.py 가 include 한다. 저장소·규칙은 app/task_options.py.

작업의 `task`(`PUT …/task`)는 안 건드린다 — 옵션은 그 작업의 TASK 묶음(프로젝트 · TASK · 라운드)에 따로 적힌다. `app.server` 를 import 하지 않는다(작업은 works.work 로 읽는다)."""
from fastapi import APIRouter, Body, HTTPException

from app import task_options, works

router = APIRouter()


def _work(wid):
    """작업 사전({id, task …}) — 없으면: 작업 저장이 켜져 있으면 404, 꺼져 있으면(시험·임시 서버) 묶음 없는 작업 {id, task: None} 로 본다(그 문서만의 옵션 · 메모리)."""
    w = works.work(wid)
    if w is not None:
        return w
    if works.enabled() or not works.ID.match(wid):
        raise HTTPException(404, "그런 작업이 없습니다")
    return {"id": wid, "task": None}


@router.get("/api/works/{wid}/task-options")
def task_options_get(wid: str):
    """그 작업의 TASK 옵션 → {scope, offered, zones: {dims[org|stage|year — 늘 이 차례], defaulted}, rev}.
    scope = 옵션이 적히는 TASK 묶음(`p:<프로젝트>|<job>|<라운드>` | `w:<작업 id>`) · offered = 연구개발 문서인가 · defaulted = 사람이 정한 적 없음(그 TASK 의 기본값 — 취합 = 기관) · rev = 저장된 판(없으면 0).
    읽기만 한다. 404 없는 작업."""
    return task_options.resolve(_work(wid))


@router.put("/api/works/{wid}/task-options")
def task_options_put(wid: str, body: dict = Body(...)):
    """{zones: {dims: [...]}, rev?, scope?} → GET 과 같은 꼴(defaulted false · rev +1). 그 작업의 TASK 묶음에 적는다 — 같은 묶음의 다른 문서도 같은 옵션을 본다. 빈 목록 = 사람이 끔.
    rev 를 보내면 저장된 판과 같을 때만 적는다(시작 화면처럼 안 보내면 그냥 적는다). 문서도 작업의 task 도 안 바뀐다 · 작업 기록 `taskOptions`.
    400 zones.dims 없음 · 모르는 기준 · 연구개발 문서가 아님 · 404 없는 작업 · 409 {reason: "staleOptions", message, options(지금 옵션)} 판이 다름 · 409 {reason: "brokenOptions", message} 저장 파일이 깨짐(덮어쓰지 않는다)."""
    work = _work(wid)
    z = body.get("zones")
    if not isinstance(z, dict) or "dims" not in z:
        raise HTTPException(400, "zones.dims(편집 구역에서 보일 기준 목록)가 필요합니다")
    rev = body.get("rev")
    if rev is not None and (not isinstance(rev, int) or isinstance(rev, bool) or rev < 0):
        raise HTTPException(400, "rev 는 0 이상의 정수여야 합니다")
    scope = body.get("scope")   # 화면이 옵션을 읽을 때의 묶음 — 보내면 그 작업의 지금 묶음과 같을 때만 적는다(그 사이 작업이 다른 프로젝트·TASK·라운드로 옮겨졌으면 409)
    if scope is not None and not isinstance(scope, str):
        raise HTTPException(400, "scope 는 글이어야 합니다")
    try:
        out = task_options.set_zones(work, z["dims"], rev, scope)
    except task_options.Stale as exc:
        raise HTTPException(409, {"reason": "staleOptions", "message": "다른 화면에서 옵션이 바뀌었습니다 — 다시 읽었습니다",
                                  "options": task_options.resolve(work)}) from exc
    except task_options.Broken as exc:
        raise HTTPException(409, {"reason": "brokenOptions", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    works.log(wid, "taskOptions", scope=out["scope"], dims=out["zones"]["dims"], rev=out["rev"])
    return out
