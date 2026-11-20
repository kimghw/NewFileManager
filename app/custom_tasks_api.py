"""조립한 TASK 끝점(spec_워크플로우 ② §14) — 화면 `/workflow` 의 「TASK 조립」 이 쓴다. 저장 · 검사는 `app/custom_tasks.py`(가벼운 모듈), 단계의 뜻은 등록부 `app/workflow.py` `STAGE_MODULES`.

- `GET /api/tasks` → {tasks[조립한 워크플로우…], stages[고를 수 있는 단계 — id · 이름 · 하는 일 · 묶음 · 단계 줄 · cells(문서 역할마다의 칸)], pairs[조립할 수 있는 문서 쌍], blocked[아직 조립할 수 없는 틀과 까닭],
  base(전제를 물려받는 붙박이 키), limits, broken(저장 파일을 못 읽음 — 그동안 목록은 비고 쓰기는 409), warn{fillNoFit(목적 문서에 「구성 맞추기」 없이 「내용 넣기」 를 고를 때의 경고 뒷부분 —
  등록부 app/workflow.py FILL_NO_FIT)}}
- `POST /api/tasks` {name, desc?, source?, target?, assign?{source[], target[], llm?[]}, stages?[](옛 꼴 — assign 이 없을 때만), premise?} → 201 {task} · `PUT /api/tasks/{key}`(보낸 키만 — 문서 쌍은 못 고침) → {task} ·
  `DELETE /api/tasks/{key}` → {deleted} · 400 = 값이 틀림(글이 화면에 그대로) · 409 = 쓰는 중(PUT 은 배정을 바꿀 때 · 지금 워크플로우로 둔 작업이 있으면 — 글 = editWhy /
  DELETE 는 지금 워크플로우로 둔 작업 + 목록에만 든 작업이 있으면 — 글 = deleteWhy) · 저장 파일을 못 읽음(쓰지 않음)
- 조립한 워크플로우의 꼴(view) = {key, name, desc, source, target, assign{source, target, llm}, stages(합집합), premise, at, sourceName, targetName, groups(합집합의 묶음 id), does{묶음 id: 묶음 설명},
  sig(단계의 지문 — custom_tasks.sig), descAuto(실제 배정에서 지은 한 줄 설명 — 등록부 app/workflow.py custom_desc)} + 목록 · POST · PUT 의 응답에는 쓰는 곳
  {inUse(그 키를 지금 워크플로우로 둔 작업 수), listed(문서의 워크플로우 목록에만 든 작업 수), editWhy(단계를 못 바꾸는 까닭 | null), deleteWhy(못 지우는 까닭 | null),
  uses[{wid, name, project, round, active}](그 작업들 — 지금 워크플로우로 둔 것(active true) 먼저 · 목록에만 든 것(active false) 뒤 · 저마다 최근 바뀐 차례 · 앞 USES_MAX 개),
  usesMore(uses 에 못 실은 나머지 수 — 0 이면 다 실음)}. name = 작업 리스트가 보이는 그 작업의 이름(works.shown — 올린 파일 이름 + 목적 문서의 프로젝트 이름 · 별칭 · 프레임 이름) ·
  화면 /workflow 의 조립 목록 줄이 그 작업을 여는 링크로 보인다(spec_워크플로우 ② §15 「조립」 「쓰는 중인 정의」).
  문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」): assign = 원본 · 목적 문서마다 고른 단계(원본은 「문서 검토」 만) + llm(1단계 「LLM 검증·보완」 을 할 문서) ·
  does = 그 정의의 묶음 설명(등록부 app/workflow.py assemble 과 같은 글 — 화면 실행이 묶음 머리 · 「한 번에 진행」 · 실행 카드에 그대로 쓴다).
- **쓰는 곳**(`_uses` — 작업마다 한 번: 셈 · 작업 목록을 같은 한 번의 작업 읽기에서) = 그 키를 지금 워크플로우로 둔 작업(task.job — inUse: 단계를 못 바꾸고 못 지움) · 문서의 워크플로우 목록(works 의 workflows[].job — 대시보드의
  「이 문서의 워크플로우」)에만 그 키가 든 작업(listed: 단계는 고치지만 못 지움 — 목록에서 빼면 지운다: DELETE /api/works/{wid}/workflows/{job}).
- `GET /api/tasks.js` → 화면이 스크립트로 읽는 글(`taskCatalogCustom([...], {broken})` — task_catalog.js 다음 · app.js 앞: 화면의 목록 · 문서 칸이 처음부터 조립한 워크플로우를 안다 ·
  꼴은 view 그대로(쓰는 곳은 빼고 — 앱 화면은 그것을 쓰지 않고, 읽을 때마다 작업을 모두 훑지 않게) · broken = 저장 파일을 못 읽음). 캐시 안 함."""
import json

from fastapi import APIRouter, Body, HTTPException, Response

from app import custom_tasks, works

router = APIRouter()

# 아직 조립할 수 없는 틀 — 화면이 까닭과 함께 보인다(고를 수 없는 것을 감추지 않는다)
BLOCKED = (
    {"name": "다른 문서 쌍(사업계획서 → 사업계획서 · 연차보고서 → 연차보고서 · 연차보고서 → 사업계획서)",
     "why": "문서의 역할을 문서 종류(사업계획서 · 연차보고서 · 기관 문서)로만 가르고 있어 같은 종류끼리는 원본 · 목적을 가를 수 없고, 이관 실행의 글과 판정이 사업계획서 → 연차보고서에 맞춰져 있습니다."},
    {"name": "취합형(원본 문서 여럿 → 목적 문서 하나 — 예: 연차보고서 취합)",
     "why": "취합의 실행(기관 문서마다 되풀이 · 배포 기준본)이 사업계획서 취합의 묶음에 묶여 있습니다 — 그 실행을 이 단계 틀로 옮긴 뒤에 조립할 수 있습니다."},
)


# 문서 역할 × 단계 표의 칸 글(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 조립 화면이 그대로 보인다). 칸의 꼴(mode)은 cells() 가 정한다:
# pick = 체크로 고름 · follow = 다른 역할이 이 단계를 고르면 따라오는 일(화면은 목적 문서가 골랐을 때만 이 글, 아니면 「—」) · no = 고를 수 없음(글 = 까닭)
CELL_TEXT = {
    "stage_review": {"source": "헤딩 · 표 분석 › LLM 검증·보완",
                     "target": "헤딩 · 표 분석 — LLM 검증·보완은 「구성 맞추기」 를 고르면 구조를 맞춘 뒤 「다시 문서 검토(LLM)」 에서, 안 고르면 여기서"},
    "stage_fit": {"source": "구성의 기준 — 구성 불러오기 › 프로젝트 구성 확정(문서는 안 바뀜)", "target": "프로젝트 구성 반영 › 다시 문서 검토(헤딩 · 표 분석 › LLM 검증·보완)"},   # 단계 사이 「 › 」(= 다음 — spec_워크플로우 ② §15 「이음 기호」)
    "stage_fill": {"source": "내용을 줌(바뀌지 않음)", "target": "← 원본 문서의 내용을 받음 — 자리 연결 › 넣기 계획 › 내용 반영"},
    "stage_clean": {"source": "원본은 바꾸지 않습니다", "target": "작성요령 삭제 — 지우기 전에 작성 지침을 저장"},
}


def cells(mid, steps):
    """단계 하나의 문서 역할마다 칸 → {역할: {mode, text}}. steps = 그 단계(모듈)의 단계들 — 하는 문서(on)가 적힌 것(app/workflow.py).
    그 역할이 고를 수 있으면 pick(custom_tasks.ROLE_STAGES), 아니면 그 단계의 일이 그 문서에 닿을 때(on 이 그 역할 · both · pair — 내용을 줌 · 구성의 기준 문서(custom_tasks.BASE_ROLE)면
    flow — 워크플로우 전체의 프로젝트 구성 확정) follow, 안 닿으면 no."""
    ons = {s["on"] for s in steps}
    touch = lambda r: {r, "both", "pair"} | ({"flow"} if r == custom_tasks.BASE_ROLE else set())  # noqa: E731
    return {r: {"mode": "pick" if mid in custom_tasks.ROLE_STAGES[r] else "follow" if ons & touch(r) else "no", "text": CELL_TEXT[mid][r]} for r in custom_tasks.ROLES}


def _builtin_names():
    from app import workflow
    return [v["name"] for v in workflow.catalog()[0].values()]


def view(t, used=None):
    """조립한 워크플로우 → 화면에 내는 꼴(문서 이름 · 묶음 id · 묶음 설명 · 단계의 지문 · 지은 한 줄 설명을 더한다 — assign(llm 포함) · stages(합집합)는 저장된 그대로).
    does = {묶음 id: 그 정의의 묶음 설명} — 등록부(app/workflow.py assemble)가 실제 배정에서 지은 글 그대로(화면 실행이 그대로 쓴다) · sig = custom_tasks.sig · descAuto = workflow.custom_desc.
    used = _uses() 의 값이면 쓰는 곳(inUse · listed · editWhy · deleteWhy — PUT 409 · DELETE 409 와 같은 글 · uses · usesMore — 그 작업들)도 더한다."""
    from app import workflow
    v = {**t, "sourceName": custom_tasks.FILES[t["source"]], "targetName": custom_tasks.FILES[t["target"]], "groups": [custom_tasks.STAGE_GROUP[s] for s in t["stages"]],
         "does": {g["id"]: g["does"] for g in workflow.assemble(t)["stages"]}, "sig": custom_tasks.sig(t), "descAuto": workflow.custom_desc(t)}
    if used is not None:
        n, m, rows = used[0].get(t["key"], 0), used[1].get(t["key"], 0), used[2].get(t["key"], [])
        v.update(inUse=n, listed=m, editWhy=custom_tasks.IN_USE.format(n=n) if n else None, deleteWhy=custom_tasks.DELETE_IN_USE.format(n=n + m) if n + m else None,
                 uses=[dict(r) for r in rows[:USES_MAX]], usesMore=max(0, len(rows) - USES_MAX))
    return v


USES_MAX = 20   # view 의 uses 에 싣는 작업 수 — 나머지는 usesMore(셈 inUse · listed 는 늘 다 센다)
NO_USES = ({}, {}, {})   # _uses() 의 꼴 — 쓰는 작업이 없음(새로 만든 정의)


def _uses():
    """조립한 정의의 키 → 쓰는 작업(작업마다 한 번 — 셈과 작업 목록을 같은 한 번의 작업 읽기에서) —
    ({키: 그 키를 지금 워크플로우로 둔 작업 수(task.job)}, {키: 문서의 워크플로우 목록(workflows[].job)에만 그 키가 든 작업 수},
     {키: [{wid, name, project, round, active} …] — 지금 워크플로우로 둔 작업(active true) 먼저 · 목록에만 든 작업 뒤 · 저마다 최근 바뀐 차례(works.list_works)}).
    지금 워크플로우로 둔 작업은 그 목록에 같은 키가 있어도 앞에만 센다. name = 작업 리스트가 보이는 이름(works.shown — 이름이 없는 작업은 id)."""
    from app import projects
    active, listed, now_rows, list_rows = {}, {}, {}, {}
    for w in works.list_works():
        task = w.get("task") if isinstance(w.get("task"), dict) else {}
        now, row = task.get("job"), None
        for k in {now} | {r.get("job") for r in w.get("workflows") or [] if isinstance(r, dict)}:
            if isinstance(k, str) and custom_tasks.KEY.fullmatch(k):
                box, rows = (active, now_rows) if k == now else (listed, list_rows)
                box[k] = box.get(k, 0) + 1
                row = row or {"wid": w["id"], "name": (works.shown(w) if w.get("name") else "") or w["id"], "project": str(task.get("project") or ""), "round": projects.round_of(task)}   # 작업마다 한 번
                rows.setdefault(k, []).append({**row, "active": k == now})
    return active, listed, {k: now_rows.get(k, []) + list_rows.get(k, []) for k in {*now_rows, *list_rows}}


def uses(key):
    """그 정의를 쓰는 작업 수 → (지금 워크플로우로 둔 것 — inUse, 목록에만 든 것 — listed)."""
    active, listed, _ = _uses()
    return active.get(key, 0), listed.get(key, 0)


def in_use(key):
    """그 키를 지금 워크플로우로 둔 작업 수(inUse) — 하나라도 있으면 단계(배정)를 바꾸지 못한다(PUT 409 · 「복제」). 지우기는 목록에만 든 작업도 센다(uses — DELETE 409)."""
    return uses(key)[0]


_NO_TASK = "그런 워크플로우가 없습니다"   # 없는 키(API 404 — 화면에 그대로)


@router.get("/api/tasks")
def tasks_get():
    from app import workflow
    stages = [{"id": mid, "name": name, "does": does, "group": custom_tasks.STAGE_GROUP[mid], "steps": [{"key": s["key"], "name": s["name"], "optional": s["optional"]} for s in steps],
               "cells": cells(mid, steps)}   # 문서 역할 × 단계 표의 칸(② §15)
              for mid, name, make, does in workflow.STAGE_MODULES for steps in [make(*workflow._GENERIC)]]
    used = _uses()
    return {"tasks": [view(t, used) for t in custom_tasks.all()], "stages": stages,
            "pairs": [{"source": a, "target": b, "name": f"{custom_tasks.FILES[a]} → {custom_tasks.FILES[b]}"} for a, b in custom_tasks.PAIRS], "blocked": list(BLOCKED), "base": custom_tasks.BASE,
            "limits": {"name": custom_tasks.NAME_MAX, "desc": custom_tasks.DESC_MAX, "premise": custom_tasks.PREMISE_MAX, "tasks": custom_tasks.TASKS_MAX},
            "broken": custom_tasks.broken(), "warn": {"fillNoFit": workflow.FILL_NO_FIT}}


@router.post("/api/tasks", status_code=201)
def tasks_post(body: dict = Body(...)):
    try:
        return {"task": view(custom_tasks.create(body, _builtin_names()), NO_USES)}   # 새 키 — 쓰는 작업이 없다
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/api/tasks/{key}")
def tasks_put(key: str, body: dict = Body(...)):
    used = _uses()
    try:
        t = custom_tasks.update(key, body, _builtin_names(), busy=used[0].get(key, 0))   # 단계를 못 바꾸는 것은 지금 워크플로우로 둔 작업이 있을 때만(목록에만 든 정의는 고친다)
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if t is None:
        raise HTTPException(404, _NO_TASK)
    return {"task": view(t, used)}


@router.delete("/api/tasks/{key}")
def tasks_delete(key: str):
    try:
        custom_tasks.writable()   # 못 읽은 저장 파일 — 「없음」 이 아니라 「쓰지 않음」(409)
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    if custom_tasks.get(key) is None:
        raise HTTPException(404, _NO_TASK)
    n, m = uses(key)
    if n + m:   # 지금 워크플로우로 둔 작업 + 목록에만 든 작업(지우면 그 줄이 모르는 키로 남는다) — 화면의 deleteWhy 와 같은 글
        raise HTTPException(409, custom_tasks.DELETE_IN_USE.format(n=n + m))
    try:
        gone = custom_tasks.delete(key)
    except custom_tasks.Refused as e:
        raise HTTPException(409, str(e)) from e
    if gone:
        from app import form_files
        form_files.forget_job(key)   # 그 워크플로우에 건 양식 설정도 푼다(spec_워크플로우 ② §18-9 — 지운 키의 설정이 남아 양식을 못 지우지 않게)
    return {"deleted": gone}


@router.get("/api/tasks.js")
def tasks_js():
    """화면의 워크플로우 목록에 조립한 워크플로우를 더하는 스크립트 — task_catalog.js 의 `taskCatalogCustom(목록, {broken})` 을 부른다(그 함수가 없으면 아무 일도 안 함).
    목록의 꼴 = view(쓰는 곳은 빼고) · broken = 저장 파일을 못 읽음(그동안 목록은 비어 있다 — 화면이 까닭을 보일 수 있게)."""
    made, broken = [view(t) for t in custom_tasks.all()], custom_tasks.broken()
    body = ("if (typeof taskCatalogCustom === \"function\") taskCatalogCustom(" + json.dumps(made, ensure_ascii=False).replace("</", "<\\/")
            + ", " + json.dumps({"broken": broken}) + ");\n")
    return Response(body, media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})
