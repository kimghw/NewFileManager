"""워크플로우 실행의 끝점(spec_워크플로우 ② §17-5 「끝점」) — 실행기는 app/workflow_exec.py, 상태 셈은 app/workflow_state.py. `attach(app, unit)` 한 번으로 8114 의 라우터에 붙는다(새 포트 없음 — server 를 import 하지 않는다).

`wid` = 그 묶음(프로젝트 · 워크플로우 · 라운드)의 **어느 문서든** — 서버가 목적 문서를 찾는다. 첫 화면의 대시보드와 문서 화면의 대시보드가 같은 끝점을 읽는다(spec_작업에이전트 ② §10 「첫 화면의 대시보드」).
- `GET /api/works/{wid}/flow` → 지금 상태 {job, sig, docs{target, source}, ready, why, stages[{id, no, name, does, server, steps[{key, name, st, done, skipped, busy, text, per?, paid?}] | null, total, done, left, can, why, paid, change}], run, last}
  — `server: false` 인 묶음은 `steps: null`(화면이 센다). 404 = 그런 작업 없음.
- `GET /api/works/{wid}/flow/live` → {run | null} — 메모리만(세션을 열지 않고 디스크를 읽지 않는다: 확인 폴링).
- `POST /api/works/{wid}/flow/runs` {from, to?, only?, redo?, skill?, by?, where?, screen?, turn?, key?, paid?[문서 id], sig?, docs?{target, source}} → 202 {run} | 409 {reason, message, run?} | 400 ·
  **200 {run: null, reason: "client", message}** = 서버가 아직 맡지 않는 묶음(또는 끄는 스위치) — 거절이 아니라 「화면이 돈다」 는 답(화면이 묶음마다 먼저 묻는다).
- `GET …/flow/runs?limit=` → {runs[요약 — 새 것부터]} · `GET …/flow/runs/{n}` → 기록 하나 · `POST …/flow/runs/{n}/stop` → {stopping}(어느 화면에서나 · 409 = 도는 실행이 없음).
- `PUT …/flow/skip` {doc, on} → {llmSkip[문서 id]} — 「LLM 검증·보완」 의 건너뛰기 · 건너뛰기 취소(워크플로우 옵션 — 모든 화면 · 실행이 같이 본다).
- `GET /api/flow/active` → {runs[도는 실행]} — 8114 를 다시 켜기 전에 본다."""
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from app import workflow_exec as X

router = APIRouter()
_NO = "그런 작업이 없습니다"


def _target(wid):
    """그 문서가 든 묶음의 목적 문서 id(실행 기록이 놓이는 곳) — 없으면 404."""
    pair = X.UNIT.pair(wid)
    if pair is None:
        raise HTTPException(404, _NO)
    return ((pair.get("target") or {}).get("id")) or wid


@router.get("/api/works/{wid}/flow")
def flow_get(wid: str):
    """워크플로우의 지금 상태 — 묶음 › 단계의 상태 · 「한 번에 진행」 을 할 수 있나 · 도는 실행 · 지난 실행."""
    got = X.status_of(wid)
    if got is None:
        raise HTTPException(404, _NO)
    return got


@router.get("/api/works/{wid}/flow/live")
def flow_live(wid: str):
    """도는 실행의 요약(메모리만) — 확인 폴링."""
    return {"run": X.live(wid)}


@router.post("/api/works/{wid}/flow/runs", status_code=202)
def flow_start(wid: str, body: dict = Body(...)):
    """워크플로우 실행 시작 — 「한 번에 진행」 · 「이어서 한 번에」 · 줄 하나(only)."""
    try:
        return {"run": X.start(wid, body)}
    except X.Refuse as e:
        if e.reason == "client":   # 서버가 아직 맡지 않는 묶음 · 끄는 스위치 — 거절이 아니라 「화면이 돈다」 는 답이다(200 {run: null}: 화면이 묶음마다 먼저 묻는다 — 브라우저 콘솔에 409 를 남기지 않게)
            return JSONResponse({"run": None, "reason": e.reason, "message": e.message}, status_code=200)
        return JSONResponse({"reason": e.reason, "message": e.message, **({"run": e.run} if e.run else {})}, status_code=409)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/works/{wid}/flow/runs")
def flow_runs(wid: str, limit: int = 20):
    """지난 실행 기록(요약 — 새 것부터)."""
    return {"runs": X.records(_target(wid), limit)}


@router.get("/api/works/{wid}/flow/runs/{n}")
def flow_run(wid: str, n: int):
    """실행 기록 하나."""
    got = X.record(_target(wid), n)
    if got is None:
        raise HTTPException(404, "그런 실행 기록이 없습니다")
    return got


@router.post("/api/works/{wid}/flow/runs/{n}/stop")
def flow_stop(wid: str, n: int):
    """멈춤 — 지금 하는 일이 끝나면 멈춘다(어느 화면에서나)."""
    got = X.stop(wid, n)
    if got is None:
        raise HTTPException(409, "도는 실행이 없습니다")
    return got


@router.put("/api/works/{wid}/flow/skip")
def flow_skip(wid: str, body: dict = Body(...)):
    """「LLM 검증·보완」 의 건너뛰기 · 건너뛰기 취소 — 그 문서는 스크립트 분석만으로 진행한다."""
    doc, on = body.get("doc"), body.get("on")
    if not isinstance(doc, str) or not isinstance(on, bool):
        raise HTTPException(400, "doc(문서 id) · on(true | false)이 있어야 합니다")
    if X.busy_text(wid):
        raise HTTPException(409, X.BUSY_TEXT)
    got = X.UNIT.skip_set(wid, doc, on)
    if not got.ok:
        raise HTTPException(404 if got.code == "missing" else 409, got.text)
    return {"llmSkip": got.data}


@router.get("/api/flow/active")
def flow_active():
    """도는 워크플로우 실행 목록(메모리)."""
    return {"runs": X.active(), "boot": X.BOOT}


def attach(app, unit):
    """8114 의 앱에 붙인다 — 문(unit = app/unit_steps.py)을 실행기에 넣고 라우터 · 끌 때의 뒷정리를 건다. server.py 가 한 번 부른다."""
    X.configure(unit)
    app.include_router(router)
    app.router.on_shutdown.append(X.shutdown)
