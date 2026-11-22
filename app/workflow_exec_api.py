"""워크플로우 실행의 끝점(spec_워크플로우 ② §17-5 「끝점」) — 실행기는 app/workflow_exec.py, 상태 셈은 app/workflow_state.py. `attach(app, unit)` 한 번으로 8114 의 라우터에 붙는다(새 포트 없음 — server 를 import 하지 않는다).

`wid` = 그 묶음(프로젝트 · 워크플로우 · 라운드)의 **어느 문서든** — 서버가 목적 문서를 찾는다. 첫 화면의 대시보드와 문서 화면의 대시보드가 같은 끝점을 읽는다(spec_작업에이전트 ② §10 「첫 화면의 대시보드」).
- `GET /api/works/{wid}/flow` → 지금 상태 {job, sig, docs{target, source}, ready, why, stages[{id, no, name, does, server, steps[{key, name, st, done, skipped, busy, text, per?, paid?}] | null, total, done, left, can, why, paid, change,
  solo?[{role, title, name, total, left, can, why, paid, change, wait?}](「한 문서만 진행」 — 그 묶음에서 그 문서만 따로 돌 수 있는 몫: ② §18-21 · 묶음 전체와 같으면 없음), leftBy?{역할: 그 문서의 눈으로 본 남은 줄},
  lane(그 묶음을 도는 실행이 잡는 문서 — source | target | "" 두 문서), wait(첫 남은 줄이 구성 값을 기다리는 까닭 | "")}], llmSkip[문서 id], run, runs[], held{source, target}, last, lasts[]}
  — `server: false` 인 묶음은 `steps: null`(화면이 센다). 404 = 그런 작업 없음. llmSkip = 사람이 「LLM 검증·보완」 을 건너뛴 문서(화면이 「건너뛰기 취소」 를 그 문서에만 보인다).
  **문서마다 따로 도는 실행**(② §18-22): runs = 도는 실행들(문서 하나만 잡은 실행은 둘까지 같이 돈다 — 요약의 `lane`) · run = 이 문서를 잡은 실행(없으면 첫 실행) · held = 역할 → 그 문서를 잡은 실행의 번호 | null ·
  lasts = 지난 실행의 끝들(같이 돌던 다른 문서의 실행도 — 끝난 차례) · last = 그 마지막(도는 실행이 없을 때). 줄의 `wait` = 그 줄이 구성 값을 기다리는 까닭(시작 요청은 409 `needs`).
- `GET /api/works/{wid}/flow/live?screen=&dirty=` → {run | null(이 문서를 잡은 실행), runs[](이 문서의 묶음에서 도는 실행들), notice | null, rev | null, base | null(기준 확정 번호 — ② §18-24)} — 메모리만(세션을 열지 않고 디스크를 읽지 않는다: 확인 폴링 · 고치던 글 보고 · 울타리 알림 — ② §17-8).
- `POST /api/works/{wid}/flow/runs` {from, to?, only?, role?(source | target — 한 문서만: 409 reason `role` = 그 묶음에 그 문서만 따로 할 것이 없음), redo?, skill?, skip?[구조 반영에서 뺄 자리 key — 화면의 「반영에서 빼기」 · LLM 「건너뛰기」 와 다르다], by?, where?, screen?, turn?, key?, paid?[문서 id], sig?, docs?{target, source}} → 202 {run} | 409 {reason, message, run?} | 400 ·
  409 `busy` = 이 실행이 잡을 문서를 다른 실행이 잡고 있음(run = 그 실행) · 409 `needs` = 첫 줄이 구성 값을 기다림(「프로젝트 구성 추출」 이 먼저).
  **200 {run: null, reason: "client", message}** = 서버가 아직 맡지 않는 묶음(또는 끄는 스위치) — 거절이 아니라 「화면이 돈다」 는 답(화면이 묶음마다 먼저 묻는다).
- `GET …/flow/runs?limit=` → {runs[요약 — 새 것부터]} · `GET …/flow/runs/{n}` → 기록 하나 · `POST …/flow/runs/{n}/stop` → {stopping}(어느 화면에서나 · 409 = 도는 실행이 없음).
- `PUT …/flow/skip` {doc, on} → {llmSkip[문서 id]} — 「LLM 검증·보완」 의 건너뛰기 · 건너뛰기 취소(워크플로우 옵션 — 모든 화면 · 실행이 같이 본다).
- `GET · PUT …/flow/take` → 「넣을 구성 선택」(spec_병합 ② §4-1): {take(넣을 기관 · 단계 · 차년도 | null = 전부), text, year(대상 차년도 = 목적 문서의 당해 차년도), yearApplied, choices, ready, why} · PUT {take?, year?}.
- `GET · PUT …/flow/caption?doc=` → 「캡션 맞추기」 의 꼴(spec_hwpx_웹편집 ② §8-10 「모든 캡션을 한 꼴로」): 그 문서(안 주면 목적 문서)의 고를 꼴들 · 쓸 꼴 · 맞출 줄의 수(caption_tpl_api.unify_view) ·
  PUT {form: 꼴 열쇠 | null(줄이 가장 많은 꼴)} — 묶음의 워크플로우 옵션에 적는다(문서 안 바뀜 · 도는 실행이 있으면 409).
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
def flow_live(wid: str, screen: str = "", dirty: int = -1, ack: str = ""):
    """도는 실행의 요약(메모리만) — 확인 폴링. screen = 이 화면(탭)의 id · dirty = 그 화면이 이 문서에서 서버에 아직 반영하지 못한 글 수(-1 = 보고 안 함) →
    울타리의 기다림이 읽는다(② §17-8). notice = 실행이 이 문서를 바꾸려는 알림 {key, since, fenced} | null — 화면은 고치던 글을 보내고 읽기 전용 띠를 보인다."""
    if dirty >= 0:
        X.report(wid, screen, dirty, ack)   # ack = 이 화면이 받아 입력을 막고 고친 글을 보낸 알림의 key(울타리는 그 보고만 「받았음」 으로 센다)
    return {"run": X.live(wid), "notice": X.notice_of(wid), "rev": X.UNIT.rev_now(wid) if hasattr(X.UNIT, "rev_now") else None,   # rev = 메모리의 문서 차례(없으면 null) — 알림이 내린 뒤 화면이 다시 읽을지
            "runs": X.live_all(wid),   # 이 문서의 묶음에서 도는 실행들(이 문서를 잡지 않은 다른 문서의 실행도 — 문서마다 따로 도는 실행: ② §18-22). run = 그 가운데 이 문서를 잡은 것
            "lastRun": X.last_n(wid),   # 이 문서가 목적 문서인 마지막 실행의 번호(메모리) — 실행을 통째로 놓친 화면이 다시 읽을지
            "base": X.UNIT.base_now(wid) if hasattr(X.UNIT, "base_now") else None}   # 메모리의 기준 확정 번호(없으면 null) — 묶음째 실행의 끝 확정 뒤 그 문서를 연 화면이 새 기준을 따라온다(② §18-24 「한 번에 진행 뒤 고친 문단 확정」)


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
    if X.held_text(doc):   # 그 문서를 잡은 실행이 돌 때만 — 같은 묶음의 다른 문서만 도는 실행은 이 문서의 건너뛰기와 무관하다(문서마다 따로 도는 실행: ② §18-22)
        raise HTTPException(409, X.BUSY_TEXT)
    got = X.UNIT.skip_set(wid, doc, on)
    if not got.ok:
        raise HTTPException(404 if got.code == "missing" else 409, got.text)
    return {"llmSkip": got.data}


@router.get("/api/works/{wid}/flow/take")
def flow_take_get(wid: str):
    """「넣을 구성 선택」 — 지금 고른 것(넣을 기관 · 단계 · 차년도 | 전부) · 대상 차년도(목적 문서의 당해 차년도) · 고를 수 있는 값(spec_병합 ② §4-1)."""
    got = X.UNIT.take_get(_target(wid))
    if not got.ok:
        raise HTTPException(404 if got.code == "missing" else 409, got.text or "넣을 구성을 읽지 못했습니다")
    return got.data


@router.put("/api/works/{wid}/flow/take")
def flow_take_put(wid: str, body: dict = Body(...)):
    """{take?: {org?, stage?, year?} | null(전부), year?: 대상 차년도} → 다시 읽은 보기. 도는 실행이 있으면 409(그 실행의 계획이 낡는다)."""
    if X.busy_text(wid):
        raise HTTPException(409, X.BUSY_TEXT)
    got = X.UNIT.take_set(_target(wid), body)
    if not got.ok:
        raise HTTPException({"invalid": 400, "missing": 404}.get(got.code, 409), got.text or "넣을 구성을 적지 못했습니다")
    return got.data


def _cap_doc(wid, doc):
    """「캡션 맞추기」 의 꼴을 셀 문서 — doc 를 주면 그 묶음의 문서여야 한다(원본 · 목적) · 안 주면 목적 문서."""
    pair = X.UNIT.pair(wid)
    if pair is None:
        raise HTTPException(404, _NO)
    ids = {(pair.get(r) or {}).get("id") for r in ("source", "target")} - {None}
    if doc:
        if doc not in ids:
            raise HTTPException(400, "그 묶음의 문서가 아닙니다")
        return doc
    return ((pair.get("target") or {}).get("id")) or wid


@router.get("/api/works/{wid}/flow/caption")
def flow_caption_get(wid: str, doc: str | None = None):
    """「캡션 맞추기」 — 그 문서의 고를 꼴들 · 묶음에 고른 꼴 · 쓸 꼴 · 맞출 줄의 수(문서 안 바뀜)."""
    got = X.UNIT.cap_unify_view(_cap_doc(wid, doc))
    if not got.ok:
        raise HTTPException(404 if got.code == "missing" else 409, got.text or "캡션을 읽지 못했습니다")
    return got.data


@router.put("/api/works/{wid}/flow/caption")
def flow_caption_put(wid: str, body: dict = Body(...), doc: str | None = None):
    """{form: 꼴 열쇠 | null} → 그 문서(안 주면 목적 문서)의 다시 읽은 보기. 꼴은 묶음에 하나다(원본 · 목적 문서에 같이 쓴다). 도는 실행이 있으면 409(그 실행이 맞출 꼴이 바뀐다)."""
    if "form" not in body:
        raise HTTPException(400, "form(꼴 열쇠 | null)이 있어야 합니다")
    if X.busy_text(wid):
        raise HTTPException(409, X.BUSY_TEXT)
    got = X.UNIT.cap_form_set(_cap_doc(wid, doc), body["form"])
    if not got.ok:
        raise HTTPException({"invalid": 400, "missing": 404}.get(got.code, 409), got.text or "캡션의 꼴을 적지 못했습니다")
    return got.data


@router.get("/api/flow/active")
def flow_active():
    """도는 워크플로우 실행 목록(메모리)."""
    return {"runs": X.active(), "boot": X.BOOT}


def attach(app, unit):
    """8114 의 앱에 붙인다 — 문(unit = app/unit_steps.py)을 실행기에 넣고 라우터 · 끌 때의 뒷정리를 건다. server.py 가 한 번 부른다."""
    X.configure(unit)
    app.include_router(router)
    app.router.on_shutdown.append(X.shutdown)
