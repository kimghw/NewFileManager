"""양식 테마(테이블 타입 · 구분 기준 타입 · 개요 템플릿 — 테마마다 YAML 하나)의 끝점(spec_양식작성 ② §5-7) — server.py 가 include 한다.
읽기 · 합치기 · 더하기는 `app/form_themes.py`(순수 모듈). 이 PC 의 사용자 설정이다 — 모든 계정 · 모든 문서가 같이 쓴다(작업 폴더 `works.root()` 아래가 아니다: 도구 이름 · 덧붙이는 글과 같다).

- `GET /api/form-themes` → {themes[{id, name, docs, signs, custom(사람이 고친 사본이 있음), default(기본본이 있음), division[…], templates[…], tables[…]}], max} — 합친 것 · 항목마다 `src`(default | user | llm).
- `GET /api/form-themes/{id}/yaml` → {id, text(그 테마의 지금 YAML 글), custom, default} · 404 = 없는 테마.
- `PUT /api/form-themes/{id}/yaml` {text} → {theme} — 글을 검사한 뒤 이 PC 의 사본에 저장(사본이 기본본보다 먼저다) · 400 = 틀린 YAML · 꼴 · 503 = 저장 실패.
- `DELETE /api/form-themes/{id}/yaml` → {theme | null, removed} — 사본을 지운다(기본으로 · LLM 이 더한 항목도 함께 지워진다 · 기본본이 없는 테마는 없어진다)."""
from fastapi import APIRouter, Body, HTTPException

from app import form_themes as T

router = APIRouter()


def _id(tid):
    if not T.ID.fullmatch(tid or ""):
        raise HTTPException(404, "그런 테마가 없습니다")
    return tid


@router.get("/api/form-themes")
def themes_get():
    return {"themes": T.listing(), "max": T.TEXT_MAX}


@router.get("/api/form-themes/{tid}/yaml")
def theme_yaml_get(tid: str):
    text, theme = T.text(_id(tid)), T.get(tid)
    if text is None or theme is None:
        raise HTTPException(404, "그런 테마가 없습니다")
    return {"id": tid, "text": text, "custom": theme["custom"], "default": theme["default"]}


@router.put("/api/form-themes/{tid}/yaml")
def theme_yaml_put(tid: str, body: dict = Body(...)):
    try:
        return {"theme": T.save(_id(tid), body.get("text"))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"테마를 저장하지 못했습니다: {e}") from e


@router.delete("/api/form-themes/{tid}/yaml")
def theme_yaml_delete(tid: str):
    try:
        removed = T.reset(_id(tid))
    except OSError as e:
        raise HTTPException(503, f"테마의 사본을 지우지 못했습니다: {e}") from e
    return {"theme": T.get(tid), "removed": removed}
