"""에이전트 설정 API(spec_에이전트 ② §3) — server.py 가 include 한다. 등록부·프롬프트 구성은 `app/agents.py`, 사용자 설정·실행 기록은 `app/agent_settings.py`.
문서와 무관하다(이 PC 의 모든 문서가 같은 설정을 쓴다) — 화면은 따로 선 페이지 `/agents`(② §5 — 상단 바 링크가 새 탭으로 연다)."""
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from app import agent_settings as S
from app import agents as A, prompt_texts
from app.agent_notes_api import job_ok

router = APIRouter()
STATIC = Path(__file__).with_name("static")
VERSIONED = ("style.css", "agents.css", "agents.js")   # 주소에 수정 시각을 붙이는 파일(워크플로우 페이지 workflow_api 와 같은 규칙 — 고친 뒤 새로 고침만으로 새 파일)


@router.get("/agents")
def agents_page():
    """에이전트 설정 페이지 — 따로 선 페이지(문서 화면과 다른 탭). #overview · #runs · #<에이전트 id>."""
    html = (STATIC / "agents.html").read_text(encoding="utf-8")
    for name in VERSIONED:
        html = html.replace(f'"/static/{name}"', f'"/static/{name}?v={int((STATIC / name).stat().st_mtime)}"')
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@router.get("/api/agents")
def agents_list():
    """{version, groups, models, efforts, llm{backend, active, available, model, forced}, agents[{id, no, noDefault, group, name, role, roleDefault, where, run, runText,
    model{id, source}, modelCode, pin, effort{id, source}, effortCode, custom[고친 키], user{no, role, model, effort}, whats, runs, fails, last}]}."""
    return A.listing()


@router.get("/api/agents/runs")
def agents_runs(agent: str = None, limit: int = 50):
    """실행 기록(새 것부터 — 서버를 켠 뒤의 것, 메모리) [{n(실행 번호), t, agent, what, model, effort, backend, ms, costUsd, error, ok}]. agent = 에이전트 id(그 에이전트 것만)."""
    if agent is not None and agent not in A.BY_ID:
        raise HTTPException(404, "그런 에이전트가 없습니다")
    return {"runs": S.runs(agent, limit)}


@router.get("/api/agents/{aid}")
def agent_get(aid: str, job: str = ""):
    """목록의 한 줄 + version · prompt[{kind, title, source, editable, text, note, …}](보내는 글의 차례 — 계약 → 지침·스킬·할 일 프롬프트·양식 정보·표 지침 → 자료) · recent(최근 실행 30)."""
    if aid not in A.BY_ID:
        raise HTTPException(404, "그런 에이전트가 없습니다")
    if job and not job_ok(job):
        raise HTTPException(404, "그런 워크플로우가 없습니다")
    return A.detail(aid, job or None)


def _edit_prompt(aid, kind, name, text, version):
    agent = A.BY_ID.get(aid)
    if agent is None or kind not in ("contract", "merge", "job"):
        raise HTTPException(404, "그런 프롬프트가 없습니다")
    if kind == "job" and not job_ok(name):
        raise HTTPException(404, "그런 워크플로우가 없습니다")
    job = name if kind == "job" else None
    from app import custom_tasks
    try:
        with prompt_texts._LOCK:
            part = next((p for p in A._parts(agent, job) if p["kind"] == kind and p.get("name") == name and p["editable"]), None)
            if part is None:
                raise HTTPException(404, "그 에이전트가 사용하는 프롬프트가 아닙니다")
            storage_name = f"{agent['contract'][0]}.{name}" if kind == "contract" else name
            if kind == "job" and custom_tasks.KEY.fullmatch(name):
                custom_tasks.set_premise(name, text, version)
            else:
                prompt_texts.save(kind, storage_name, text, version)
            updated = next((p for p in A._parts(agent, job) if p["kind"] == kind and p.get("name") == name), None)
            if updated is None:
                raise HTTPException(404, "그 프롬프트에 연결된 워크플로우가 없습니다")
            return updated
    except KeyError as e:
        raise HTTPException(404, "그런 워크플로우가 없습니다") from e
    except S.Stale as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, "프롬프트를 저장하지 못했습니다") from e


@router.put("/api/agents/{aid}/prompt/{kind}/{name}")
def prompt_put(aid: str, kind: str, name: str, body: dict = Body(...)):
    if not isinstance(body.get("text"), str):
        raise HTTPException(400, "프롬프트 원문이 필요합니다")
    return _edit_prompt(aid, kind, name, body["text"], body.get("version"))


@router.delete("/api/agents/{aid}/prompt/{kind}/{name}")
def prompt_reset(aid: str, kind: str, name: str, version: int):
    return _edit_prompt(aid, kind, name, None, version)


@router.put("/api/agents/{aid}")
def agent_put(aid: str, body: dict = Body(...)):
    """{no?, role?, model?, effort?, version?} — 작업 번호 · 역할 글 · 모델 · 생각 깊이를 고친다(null·"" = 기본으로). → 그 에이전트(GET 꼴).
    400 꼴이 틀림·작업 번호가 다른 에이전트와 겹침 · 404 없는 에이전트 · 409 그 사이에 바뀜(version)."""
    if aid not in A.BY_ID:
        raise HTTPException(404, "그런 에이전트가 없습니다")
    ver = body.get("version")
    if ver is not None and (isinstance(ver, bool) or not isinstance(ver, int)):
        raise HTTPException(400, "version 은 정수")
    try:
        return A.update(aid, {k: body[k] for k in ("no", "role", "model", "effort") if k in body}, ver)
    except S.Stale as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"에이전트 설정을 저장하지 못했습니다: {e}") from e
