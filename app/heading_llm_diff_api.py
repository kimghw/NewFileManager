"""LLM 이 바꾼 것 API(spec_헤딩_추출 ② §7 「LLM 이 바꾼 것」) — server.py 가 include 한다. 모으기는 app/heading_llm_diff.py(읽기만 — 문서·결과를 바꾸지 않는다)."""
from fastapi import APIRouter, HTTPException

from app import heading_llm_diff, outline_match, tpl_agent_api

router = APIRouter()


@router.get("/api/docs/{doc_id}/headings/llm-changes")
def llm_changes(doc_id: str):
    """{rev, rules, heads, tables, formats} — 헤딩 추출의 LLM 실행과 서식 정리 계획이 스크립트와 다르게 정한 것(heading_llm_diff.report). 400 = hwpx 아님."""
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "헤딩 추출은 지금 hwpx 만 됩니다")
    with s.lock:
        ov = server._outline_ov(s)
        rev = s.rev
    got = tpl_agent_api.plans(s, (ov or {}).get("run")) if ov is not None else {}
    with s.lock:
        states = {k: {**v, "state": tpl_agent_api.state_of(s, ov, v, rev)} for k, v in got.items()}
    out = heading_llm_diff.report(s, states)
    with s.lock:
        out["relations"] = outline_match.merge_hints(ov) if ov is not None else []  # 종속 제안(템플릿 사이 관계 — 저절로 걸지 않는다: spec_hwpx_웹편집 ② §8-2 「종속 제안」)
        out["applies"] = tpl_agent_api.applies(s, ov.get("run")) if ov is not None else []   # 실제 반영 기록(실행마다 — 결과 화면: ② §7 「결과 화면」)
    return out
