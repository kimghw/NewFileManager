"""분석 상태 API(spec_작업 ② §20) — 문서 이름 줄의 표시(app/static/doc_status.js)가 읽는다. server.py 가 include 한다. 셈은 app/analysis.py.
읽기만 한다 — 분석을 시작하지 않는다(시작은 `POST …/headings {first: true}` · `POST …/divisions/review`)."""
from fastapi import APIRouter

from app import analysis, works

router = APIRouter()


def _division(server, s):
    """이 문서에 구분 기준 항목이 있는가 — hwpx 이고 지원 양식. 양식 판정은 문서 차례(rev)마다 한 번(도는 동안 2초마다 읽힌다)."""
    if s.fmt != "hwpx":
        return False
    got = getattr(s, "analysis_form", None)
    if got is None or got[0] != s.rev:
        with s.lock:
            got = s.analysis_form = (s.rev, bool(server.PROFILE.supported(server.PROFILE.form_of(s.doc.blocks()))))
    return got[1]


@router.get("/api/docs/{doc_id}/analysis")
def analysis_get(doc_id: str):
    """{rev, format, kind, base: "done" | "running" | "none" | "failed" | "na", busy, job: null | {first, stage, llm, status, what, started, error},
    items: [{key: "heads" | "tables", name, state, run, at, moved, text, error, llm: {state, text, error}}, {key: "division", name, optional, state, at, found, applied, partial, error, text}]}
    — state = none · wait · running · done · failed(구분 기준은 none · running · done 만 — 한쪽 검토만 답했으면 partial). 해당 없는 항목은 없다(docx 는 items 가 비고 base "na" · 구분 기준은 hwpx 지원 양식일 때만).
    busy = 헤딩 작업이 하나라도 도는 중(1단계 포함) · job = 도는 중이거나 실패로 끝난 마지막 헤딩 작업(잘 끝났으면 null).
    kind = 작업에 적힌 작업 종류("rnd" | "general" | "" — 작업 저장이 꺼져 있으면 빈 글)."""
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    kind = ((works.work(s.id) or {}).get("task") or {}).get("kind") or ""
    return analysis.status(s, kind=kind, division=_division(server, s))
