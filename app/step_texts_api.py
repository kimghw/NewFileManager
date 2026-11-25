"""단계 설명 고치기의 끝점(spec_워크플로우 ② §18-26) — server.py 가 include 한다. 저장 · 얹기는 `app/step_texts.py`, 그 워크플로우에 그 줄이 있는지 · 기본 글은 등록부(`workflow.task_of`)에서.

- `GET /api/step-texts` → {version, max, fields[{key, name}], texts{"<워크플로우 키>.<줄 key>": {글 키: 글}}} — 고친 것만.
- `PUT /api/step-texts/{워크플로우 키}/{줄 key}` {texts{글 키: 글}, version?} → {job, step, texts(고친 글만), base{글 키: 기본 글}, version} · 준 키만 바꾼다(빈 글 · 기본 글과 같은 글 = 기본 글로).
- `DELETE /api/step-texts/{워크플로우 키}/{줄 key}` → 같은 꼴 — 그 단계의 고친 글을 모두 지움(기본 글로).
  400 = 글의 꼴 · 404 = 그 워크플로우에 없는 줄 · 409 = 그 사이에 바뀜(version) · 503 = 저장 실패.
**화면(등록부 응답)에만 보인다** — 만든 글(workflow.md · tasks/)과 에이전트의 프롬프트는 등록부의 기본 글 그대로다."""
from fastapi import APIRouter, Body, HTTPException

from app import step_texts as T

router = APIRouter()


def base_of(job, unit):
    """그 워크플로우 그 줄의 기본 글 {글 키: 글} | None(없는 워크플로우 · 줄)."""
    from app import workflow
    t = workflow.task_of(job)
    for g in (t or {}).get("stages") or ():
        for s in g["steps"]:
            if s["key"] == unit:
                return {f: s.get(f, "") or "" for f in T.KEYS}
    return None


@router.get("/api/step-texts")
def texts_get():
    return {**T.load(), "max": T.TEXT_MAX, "fields": [{"key": k, "name": n} for k, n in T.FIELDS]}


def _save(job, unit, given, ver):
    base = base_of(job, unit)
    if base is None:
        raise HTTPException(404, "그 워크플로우에 그런 단계가 없습니다")
    if ver is not None and (isinstance(ver, bool) or not isinstance(ver, int)):
        raise HTTPException(400, "version 은 정수")
    try:
        got = T.save(job, unit, given, base, ver)
    except T.Stale as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"단계 설명을 저장하지 못했습니다: {e}") from e
    return {"job": job, "step": unit, "texts": got["texts"], "base": base, "version": got["version"]}


@router.put("/api/step-texts/{job}/{unit}")
def text_put(job: str, unit: str, body: dict = Body(...)):
    given = body.get("texts")
    if not isinstance(given, dict):
        raise HTTPException(400, "texts 는 {글 키: 글}")
    return _save(job, unit, given, body.get("version"))


@router.delete("/api/step-texts/{job}/{unit}")
def text_delete(job: str, unit: str):
    return _save(job, unit, {k: "" for k in T.KEYS}, None)
