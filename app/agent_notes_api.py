"""도구 · 에이전트에 적어 두는 내용의 끝점 · 줄마다 쓰는 에이전트(spec_에이전트 ② §6 · 화면 spec_워크플로우 ② §18-16 「에이전트 열」) — server.py 가 include 하고 `Scope` 를 미들웨어로 건다.
저장 · 프롬프트에 붙이기 · 줄 → 에이전트는 `app/agent_notes.py`(가벼운 모듈), 에이전트 등록부는 `app/agents.py`, 줄이 쓰는 에이전트 · 도구의 근거는 워크플로우 등록부 `app/workflow.py` 의 단계 줄(`agents` · `uses`).

- `GET /api/agent-notes` → {version, max, tools{"<틀>.<줄 key>": 글}, jobTools{워크플로우 키: {줄 key: 글}}, all{에이전트 id: 글}, jobs{워크플로우 키: {에이전트 id: 글}}}
- `GET /api/agent-notes/lines` → {families{relay|gather|single: {줄 key: {name, agents[에이전트 id…], tools[{id, name}]}}}, agents{에이전트 id: {id, no, name, group, role, runText, model{id, source}, effort{id, source}, parts[조각 종류…]}}}
  — 조립 화면의 「에이전트」 열이 줄 카드마다 쓰는 에이전트 · 도구를 이것으로 안다(틀마다 줄 key 가 겹친다 — 가족으로 가른다: 이관형 = 일반 단계 · 취합형 = 사업계획서 취합 · 문서 하나 = 양식 표준화 + 양식 맞추기).
- **도구에 적어 두는 내용**(단위 = 도구 — 사용자 「공통적으로 그 도구에서 쓰는 내용과 워크플로우마다 사용되는 내용 2가지」):
  `PUT /api/agent-notes/tools/{틀}/{줄 key}` {text, job?(워크플로우 키 — 없으면 도구 공통), version?} → {family, unit, job, text, version} · 빈 글 = 지움 · `DELETE …?job=` = 그 글 지움.
  400 = 글 · 키의 꼴 · 그 틀의 워크플로우가 아님 · 404 = 그 틀에 없는 줄 · 없는 워크플로우 · 409 = 판 · 503 = 저장 실패. 「사람이 하는 일」(hand)에는 적지 않는다(줄마다 이름 · 글이 따로 있다).
- **에이전트에만 덧붙이는 글**(더 좁은 층): `PUT /api/agent-notes/{에이전트 id}` {text, job?(워크플로우 키 — 없으면 모든 워크플로우), version?} → {aid, job, text, version} · 빈 글 = 지움.
  400 = 글이 아님 · 너무 김 · 키의 꼴 · 404 = 없는 에이전트 · 없는 워크플로우 · 409 = 그 사이에 바뀜(version) · 503 = 파일 저장 실패.
- `DELETE /api/agent-notes/{에이전트 id}?job=` → 같은 꼴(text "") — 그 글을 지운다(에이전트 설정 페이지의 「기본으로 되돌리기」 가 범용 글에 이것을 부른다).
- `Scope` = 요청 주소의 작업 id(`/api/docs/<id>/…` · `/api/works/<id>/…`)를 그 요청의 **지금 워크플로우 맥락**으로 건다(agent_notes.scope(work=…)) — 그 요청이 부르는 LLM 호출에 그 작업의 워크플로우 전용 글이 붙는다.
  작업을 읽는 것은 LLM 을 실제로 부를 때뿐이다(요청마다 읽지 않는다)."""
import re

from fastapi import APIRouter, Body, HTTPException

from app import agent_notes as N
from app import agent_settings

router = APIRouter()
_WORK_PATH = re.compile(r"^/api/(?:docs|works)/([0-9a-f]{12})(?:/|$)")   # 작업 id 가 든 주소(works.ID 의 꼴)


class Scope:
    """순수 ASGI 미들웨어 — 주소에 작업 id 가 있으면 그 요청을 그 작업의 워크플로우 맥락에서 돌린다(동기 끝점의 일꾼 스레드는 이 맥락의 사본을 받는다)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        m = _WORK_PATH.match(scope.get("path") or "") if scope.get("type") == "http" else None
        if m is None:
            await self.app(scope, receive, send)
            return
        with N.scope(work=m.group(1)):
            await self.app(scope, receive, send)


def job_ok(job):
    """실제로 있는 워크플로우인가 — 붙박이(등록부) · 조립한 것(저장소)."""
    from app import custom_tasks, workflow
    return isinstance(job, str) and (job in workflow.BY_JOB or custom_tasks.get(job) is not None)


def lines():
    """틀(가족)마다 줄 key → {name, agents, tools} — 등록부의 그 줄에서(app/agent_notes.py tool_map: 프롬프트에 붙일 때도 같은 것을 읽는다)."""
    return N.tool_map()


def _agents():
    """에이전트 id → 열이 머리에 보이는 것(번호 · 이름 · 역할 · 모델 · 생각 깊이) + 프롬프트 조각의 종류(글은 GET /api/agents/{id})."""
    from app import agents as A
    kinds = {a["id"]: [p[0] for p in a["parts"]] for a in A.AGENTS}
    return {a["id"]: {**{k: a[k] for k in ("id", "no", "name", "group", "role", "runText", "model", "effort")}, "parts": kinds[a["id"]]} for a in A.listing()["agents"]}


@router.get("/api/agent-notes")
def notes_get():
    return {**N.load(), "max": N.TEXT_MAX}


@router.get("/api/agent-notes/lines")
def notes_lines():
    return {"families": lines(), "agents": _agents()}


def _args(job, ver):
    if ver is not None and (isinstance(ver, bool) or not isinstance(ver, int)):
        raise HTTPException(400, "version 은 정수")
    if job is not None:
        if not (isinstance(job, str) and N.JOB.fullmatch(job)):
            raise HTTPException(400, "워크플로우 키의 꼴이 아닙니다")
        if not job_ok(job):
            raise HTTPException(404, "그런 워크플로우가 없습니다")


def _store(fn):
    try:
        return fn()
    except N.Stale as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"덧붙이는 글을 저장하지 못했습니다: {e}") from e


def _save_tool(family, unit, text, job, ver):
    rows = N.tool_map().get(family)
    if rows is None or unit not in rows or unit == "hand":
        raise HTTPException(404, "그 틀에 그런 도구가 없습니다")
    _args(job, ver)
    if job is not None and N.family_of(job)[0] != family:
        raise HTTPException(400, "그 워크플로우는 이 틀이 아닙니다")
    return {"family": family, "unit": unit, "job": job, **_store(lambda: N.save_tool(family, unit, text, job, ver))}


@router.put("/api/agent-notes/tools/{family}/{unit}")
def tool_put(family: str, unit: str, body: dict = Body(...)):
    return _save_tool(family, unit, body.get("text"), body.get("job") or None, body.get("version"))


@router.delete("/api/agent-notes/tools/{family}/{unit}")
def tool_delete(family: str, unit: str, job: str = ""):
    return _save_tool(family, unit, "", job or None, None)


def _save(aid, text, job, ver):
    if aid not in agent_settings.IDS:
        raise HTTPException(404, "그런 에이전트가 없습니다")
    _args(job, ver)
    try:
        got = N.save(aid, text, job, ver)
    except N.Stale as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"덧붙이는 글을 저장하지 못했습니다: {e}") from e
    return {"aid": aid, "job": job, **got}


@router.put("/api/agent-notes/{aid}")
def notes_put(aid: str, body: dict = Body(...)):
    return _save(aid, body.get("text"), body.get("job") or None, body.get("version"))


@router.delete("/api/agent-notes/{aid}")
def notes_delete(aid: str, job: str = ""):
    return _save(aid, "", job or None, None)
