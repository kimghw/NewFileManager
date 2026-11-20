"""대시보드의 문서별 워크플로우 목록·진행 요약·워크플로우 전환.

단계 실행은 기존 TASK 기능을 쓴다. 목록의 진행 요약은 화면이 마지막으로 확인한 값이며,
문서나 분석 상태를 복제하지 않는다. TASK 문맥만 보관해 돌아올 때 역할·라운드를 복원한다.
목록에서 한 줄을 빼는 끝점(DELETE …/workflows/{job})은 그 진행 요약 줄만 뺀다 — 문서 · 분석은 그대로이고, 지금 워크플로우의 줄은 빼지 않는다
(목록에만 든 조립한 워크플로우는 그 줄을 빼야 지울 수 있다 — app/custom_tasks_api.py).
"""
import threading

from fastapi import APIRouter, Body, HTTPException

from app import projects, workflow, works

router = APIRouter()
_locks = {}
_guard = threading.Lock()
_FIELDS = ("job", "status", "done", "total", "updated")


def _lock(wid):
    with _guard:
        return _locks.setdefault(wid, threading.Lock())


def _work(wid):
    value = works.work(wid)
    if value is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    return value


def _job(value, work):
    if not isinstance(value, str):
        raise HTTPException(400, "워크플로우를 선택하세요")
    from app import custom_tasks
    if custom_tasks.is_key(value):   # 화면에서 조립한 TASK(spec_워크플로우 ② §14) — 이관과 같은 형식(hwp · hwpx)
        if work.get("format") not in ("hwp", "hwpx"):
            raise HTTPException(400, "이 문서 형식으로 사용할 수 없는 워크플로우입니다")
        return value
    task = next((t for t in workflow.TASKS if t["job"] == value), None)
    catalog = workflow.catalog()[0]
    if task is None or task.get("soon") or value not in catalog:
        raise HTTPException(400, "사용할 수 없는 워크플로우입니다")
    if work.get("format") not in catalog[value]["accept"]:
        raise HTTPException(400, "이 문서 형식으로 사용할 수 없는 워크플로우입니다")
    return value


def _relay_made(job):
    """이관형으로 조립한 워크플로우인가(원본 문서 하나 → 목적 문서 — 문서의 역할이 둘이라 전환할 때 제 역할을 지킨다). 취합형 · 문서 하나로 조립한 것은 아니다
    (그 문서는 목적 문서 종류로 둔다 — 문서 하나는 그 문서가 곧 목적 문서다: custom_tasks.is_single)."""
    from app import custom_tasks
    return custom_tasks.is_key(job) and not custom_tasks.is_gather(job) and not custom_tasks.is_single(job)


def _view(work):
    active = (work.get("task") or {}).get("job") or ""
    items = [{k: row[k] for k in _FIELDS} for row in work.get("workflows") or []]
    if active and not any(row["job"] == active for row in items):
        items.insert(0, {"job": active, "status": "ready", "done": 0, "total": 0, "updated": work.get("updated", 0)})
    return {"items": items, "active": active}


def _context(task):
    return {"kind": task.get("kind") or "", "file": task.get("file") or "", "round": projects.round_of(task),
            "project": task.get("project") or ""}


def _remember(wid, task):
    job = task.get("job") or ""
    if job:
        saved = works.workflow_update(wid, job, context=_context(task))
        if saved is None:
            raise HTTPException(404, "그런 작업이 없습니다")
        return saved
    return _work(wid)


@router.get("/api/works/{wid}/workflows")
def workflow_runs_get(wid: str):
    """목록과 현재 워크플로우. 옛 작업은 현재 워크플로우를 읽기 응답에 포함한다(조회만으로 저장하지 않음)."""
    return _view(_work(wid))


@router.put("/api/works/{wid}/workflows")
def workflow_runs_put(wid: str, body: dict = Body(...)):
    """{job, status?, done?, total?}: 한 항목을 추가하거나 마지막 확인 진행 상태를 저장한다."""
    with _lock(wid):
        work = _work(wid)
        job = _job(body.get("job"), work)
        old = next((row for row in work.get("workflows") or [] if row["job"] == job), {})
        status, done, total = (body.get(k, old.get(k, fallback)) for k, fallback in (("status", "ready"), ("done", 0), ("total", 0)))
        if status not in ("ready", "progress", "done") or any(not isinstance(n, int) or isinstance(n, bool) for n in (done, total)):
            raise HTTPException(400, "워크플로우 진행 상태가 올바르지 않습니다")
        if not 0 <= done <= total <= 10000 or (status == "done" and (not total or done != total)):
            raise HTTPException(400, "완료 단계 수와 전체 단계 수를 확인하세요")
        fields = {"status": status, "done": done, "total": total}
        if (work.get("task") or {}).get("job") == job:
            fields["context"] = _context(work["task"])
        saved = works.workflow_update(wid, job, **fields)
        if saved is None:
            raise HTTPException(404, "그런 작업이 없습니다")
        return _view(saved)


@router.delete("/api/works/{wid}/workflows/{job}")
def workflow_runs_delete(wid: str, job: str):
    """그 워크플로우의 줄을 문서의 워크플로우 목록에서 뺀다 → GET 과 같은 꼴. 문서 · 분석은 그대로(진행 요약 줄만).
    400 = 지금 워크플로우(목록에서 뺄 수 없음 — 다른 워크플로우로 바꾼 뒤) · 404 = 작업이 없음 · 목록에 그 줄이 없음. 키는 따지지 않는다(지운 · 모르는 워크플로우의 줄도 뺀다)."""
    with _lock(wid):
        work = _work(wid)
        if (work.get("task") or {}).get("job") == job:
            raise HTTPException(400, "지금 워크플로우는 목록에서 뺄 수 없습니다 — 다른 워크플로우로 바꾼 뒤에 빼세요")
        if not any(isinstance(row, dict) and row.get("job") == job for row in work.get("workflows") or []):
            raise HTTPException(404, "목록에 그 워크플로우가 없습니다")
        saved = works.workflow_remove(wid, job)
        if saved is None:
            raise HTTPException(404, "그런 작업이 없습니다")
        works.log(wid, "workflowRemove", job=job)
        return _view(saved)


@router.post("/api/works/{wid}/workflows/activate")
def workflow_runs_activate(wid: str, body: dict = Body(...)):
    """{job}: 같은 문서에서 워크플로우를 전환하고, 앞 워크플로우의 역할·라운드와 진행 요약을 남긴다."""
    from app import server  # server가 router를 넣은 뒤 요청 때 읽는다(순환 import 방지).

    with _lock(wid):
        work = _work(wid)
        job = _job(body.get("job"), work)
        current = work.get("task") or {}
        remembered = _remember(wid, current)
        if current.get("job") == job:
            return {**_view(remembered), "task": current}
        row = next((item for item in remembered.get("workflows") or [] if item["job"] == job), {})
        context = row.get("context") or {}
        role = current.get("file") or ""
        if job in works.FRAME_FILE:
            role = works.FRAME_FILE[job]
        elif job == "plan_to_report" or _relay_made(job):   # 이관형(붙박이 이관 · 조립한 TASK) — 원본 · 목적 문서 어느 쪽이든 제 역할 그대로 · 취합형 · 문서 하나로 조립한 것은 아래(목적 문서 종류 — 붙박이 취합 · 양식 표준화와 같다)
            role = role if role in ("plan", "report") else ""
        elif job in works.TARGET_FILE:
            role = works.TARGET_FILE[job]
        task = {"kind": context.get("kind", server.TASK_KIND.get(job, "rnd")), "file": context.get("file", role), "job": job, "project": current.get("project") or ""}
        # 프로젝트는 문서 공통. 다른 프로젝트로 옮긴 뒤에는 옛 프로젝트의 라운드 번호를 가져오지 않는다.
        if context and context.get("project", "") == task["project"]:
            task["round"] = context["round"]
        result = server._work_task(wid, task)
        saved = _remember(wid, result["task"])
        if saved is None:
            raise HTTPException(404, "그런 작업이 없습니다")
        works.log(wid, "workflow", previous=current.get("job") or "", job=job)
        return {**_view(saved), **result}
