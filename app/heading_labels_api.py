"""구분 라벨 지정 API(spec_헤딩_추출 ② §13) — 괄호 줄(「[…]」)을 구분 라벨(구분 기준 값)·괄호 소제목으로 지정하고, 지금 2단계 결과에 곧바로 반영한다(LLM 호출 없음).
server.py 가 include 한다(양식 정보 `heading_forms_api` 와 같은 꼴). 끝점 이름은 `div_labels` — `…/headings/labels` 는 서식 라벨(S) 목록이라 다르다."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_runs as HR

router = APIRouter()


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "헤딩 추출은 지금 hwpx 만 됩니다")
    return s


@router.get("/api/docs/{doc_id}/headings/div_labels")
def div_labels(doc_id: str):
    """{bases[구분 기준], version, hints{꼴: 지정}, items[{shape, text, count, role, basis, key, tplNos, para, hint}], run, stale}."""
    return HR.div_labels(_sess(doc_id))


@router.put("/api/docs/{doc_id}/headings/div_labels")
def div_labels_put(doc_id: str, body: dict = Body(...)):
    """{shape, role: "label" | "subtitle" | "auto", basis?, text?} — 지정을 저장하고 지금 2단계 결과를 다시 셈해 새 실행으로 둔다.
    → GET 과 같은 꼴 + `applied`(다시 셈했나) · `note`(못 했으면 까닭 — 지정은 저장됨). 400 잘못된 값 · 409 헤딩 추출이 돌고 있음."""
    s = _sess(doc_id)
    try:
        HR.set_hint(s, body.get("shape"), body.get("role"), body.get("basis") or "", body.get("text") or "")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"지정을 저장하지 못했습니다: {e}") from e
    applied, note = False, ""
    try:
        n = HR.relabel(s)
        applied = n is not None
        if not applied:
            note = "2단계 결과가 아직 없습니다 — 2단계를 돌리면 지정이 반영됩니다"
    except HR.Stale as e:
        note = str(e)
    except HR.Busy as e:
        raise HTTPException(409, f"지정은 저장했습니다. {e}") from e
    return {**HR.div_labels(s), "applied": applied, "note": note}
