"""워크플로우 API · 페이지(spec_워크플로우 ② §2) — server.py 가 include 한다. 등록부는 `app/workflow.py`.
문서·작업과 무관하다(읽기만 — 시작 화면에서도 열리고 LLM 연결이 없어도 된다)."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

from app import workflow, workflow_runs

router = APIRouter()
router.include_router(workflow_runs.router)
STATIC = Path(__file__).with_name("static")
VERSIONED = ("style.css", "panel_help.css", "workflow.css", "workflow_agents.css", "task_catalog.js", "panel_help.js", "workflow_agents.js", "workflow.js")   # 주소에 수정 시각을 붙이는 파일(시작 화면 server.index 와 같은 규칙 — 고친 뒤 새로 고침만으로 새 파일)


@router.get("/api/workflow")
def workflow_get():
    """{tasks[{job, inputs, output, note, soon, prompt, roles[…], stages[{id, meta, no, name, does, steps[단계]}]}], common[{id, name, does, where, usedBy[job…], steps[단계]}], by, change}
    — 단계 = {key, no, name, by[…], does, out, change, auto, optional, soon, on, uses[…], spec{file, at} | null, modules[{name, path, doc}], agents[{id, no, name, group, role, run, model{id, source}}]}.
    roles = 문서 역할마다 {role, name, kind, many, unit[{stage, steps[단계 key…]}]}(원본 → 목적) · on = 그 단계가 하는 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」)."""
    return workflow.listing()


@router.get("/workflow")
def workflow_page():
    """워크플로우 페이지 — 따로 선 페이지(문서 화면과 다른 탭)."""
    html = (STATIC / "workflow.html").read_text(encoding="utf-8")
    for name in VERSIONED:
        html = html.replace(f'"/static/{name}"', f'"/static/{name}?v={int((STATIC / name).stat().st_mtime)}"')
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})
