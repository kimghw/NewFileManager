"""조립한 TASK 끝점(spec_워크플로우 ② §14) — 화면 `/workflow` 의 「TASK 조립」 이 쓴다. 저장 · 검사는 `app/custom_tasks.py`(가벼운 모듈), 단계의 뜻은 등록부 `app/workflow.py` `STAGE_MODULES`.

- `GET /api/tasks` → {tasks[조립한 TASK…], stages[고를 수 있는 단계 — id · 이름 · 하는 일 · 묶음], pairs[조립할 수 있는 문서 쌍], blocked[아직 조립할 수 없는 틀과 까닭], base(전제를 물려받는 붙박이 TASK), limits}
- `POST /api/tasks` {name, desc?, source?, target?, stages[], premise?} → 201 {task} · `PUT /api/tasks/{key}`(보낸 키만 — 문서 쌍은 못 고침) → {task} · `DELETE /api/tasks/{key}` → {deleted} · 409 = 그 TASK 로 하던 작업이 있음
- `GET /api/tasks.js` → 화면이 스크립트로 읽는 글(`taskCatalogCustom([...])` — task_catalog.js 다음 · app.js 앞: 화면의 TASK 목록 · 문서 칸이 처음부터 조립한 TASK 를 안다). 캐시 안 함."""
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


def _builtin_names():
    from app import workflow
    return [v["name"] for v in workflow.catalog()[0].values()]


def view(t):
    """조립한 TASK → 화면에 내는 꼴(문서 이름 · 묶음 id 를 더한다)."""
    return {**t, "sourceName": custom_tasks.FILES[t["source"]], "targetName": custom_tasks.FILES[t["target"]], "groups": [custom_tasks.STAGE_GROUP[s] for s in t["stages"]]}


def in_use(key):
    """그 TASK 로 하던 작업 수."""
    return sum(1 for w in works.list_works() if (w.get("task") or {}).get("job") == key)


@router.get("/api/tasks")
def tasks_get():
    from app import workflow
    stages = [{"id": mid, "name": name, "does": does, "group": custom_tasks.STAGE_GROUP[mid], "steps": [{"key": s["key"], "name": s["name"], "optional": s["optional"]} for s in make(*workflow._GENERIC)]}
              for mid, name, make, does in workflow.STAGE_MODULES]
    return {"tasks": [{**view(t), "inUse": in_use(t["key"])} for t in custom_tasks.all()], "stages": stages,
            "pairs": [{"source": a, "target": b, "name": f"{custom_tasks.FILES[a]} → {custom_tasks.FILES[b]}"} for a, b in custom_tasks.PAIRS], "blocked": list(BLOCKED), "base": custom_tasks.BASE,
            "limits": {"name": custom_tasks.NAME_MAX, "desc": custom_tasks.DESC_MAX, "premise": custom_tasks.PREMISE_MAX, "tasks": custom_tasks.TASKS_MAX}}


@router.post("/api/tasks", status_code=201)
def tasks_post(body: dict = Body(...)):
    try:
        return {"task": view(custom_tasks.create(body, _builtin_names()))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/api/tasks/{key}")
def tasks_put(key: str, body: dict = Body(...)):
    try:
        t = custom_tasks.update(key, body, _builtin_names())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if t is None:
        raise HTTPException(404, "그런 TASK 가 없습니다")
    return {"task": view(t)}


@router.delete("/api/tasks/{key}")
def tasks_delete(key: str):
    if custom_tasks.get(key) is None:
        raise HTTPException(404, "그런 TASK 가 없습니다")
    n = in_use(key)
    if n:
        raise HTTPException(409, f"이 TASK 로 하던 작업이 {n}개 있습니다 — 그 작업의 TASK 를 바꾸거나 작업을 지운 뒤에 지울 수 있습니다")
    return {"deleted": custom_tasks.delete(key)}


@router.get("/api/tasks.js")
def tasks_js():
    """화면의 TASK 목록에 조립한 TASK 를 더하는 스크립트 — task_catalog.js 의 `taskCatalogCustom` 을 부른다(그 함수가 없으면 아무 일도 안 함)."""
    body = "if (typeof taskCatalogCustom === \"function\") taskCatalogCustom(" + json.dumps([view(t) for t in custom_tasks.all()], ensure_ascii=False).replace("</", "<\\/") + ");\n"
    return Response(body, media_type="text/javascript; charset=utf-8", headers={"Cache-Control": "no-store"})
