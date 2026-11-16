"""분석 상태 API(spec_작업 ② §20) — 문서 이름 줄의 표시(app/static/doc_status.js)가 읽는다. server.py 가 include 한다. 셈은 app/analysis.py.
GET 은 읽기만 한다 — 분석을 시작하지 않는다(시작은 `POST …/headings {first: true}` · `POST …/divisions/review`).
「LLM 검증·보완」(2026-11-16 — ② §20 「넷 · 진행표 · LLM 검증·보완」)은 `POST …/analysis/llm` 으로 시작하고 `DELETE` 로 멈춘다 — 실행은 app/analysis_llm.py."""
from fastapi import APIRouter, Body, HTTPException

from app import analysis, analysis_llm, heading_runs, outline_conform, outline_match, tpl_agent_api, works

router = APIRouter()


def _place(s, ov):
    """확정 서식(spec_hwpx_웹편집 ② §8-8 — 레터 뒤 묶음 빈칸 · 자리 규칙)이 아직 안 걸린 줄 수 — 문서 차례·헤딩 그래프마다 한 번 센다(도는 동안 2초마다 읽힌다)."""
    got = getattr(s, "analysis_place", None)
    if got is None or got[:2] != (s.rev, ov.get("run")):
        with s.lock:
            got = s.analysis_place = (s.rev, ov.get("run"), len(outline_conform.pending(s.doc, ov)))
    return got[2]


def _outline(server, s):
    """→ (개요 오버레이, 서식 갈래 {tpl: {레벨: variants}}) | None(2단계 결과 없음 · hwpx 아님) — 세션 잠금 안에서. 오버레이가 옛 그래프의 것이면 GET …/outline 처럼 새로 만든다."""
    if s.fmt != "hwpx":
        return None
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            return None
        return ov, outline_match.all_variants(s.doc, ov)


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
    """{rev, format, kind, base: "done" | "running" | "none" | "failed" | "na", busy, job: null | {first, chain, stage, llm, status, what, started, error}, chain: null | {steps, at, stopping, status}, llmPlan[{key, name, run, why}],
    items: [{key: "heads" | "tables", name, state, run, at, moved, text, error, llm: {state, text, error}, rules?(헤딩), calc?(표)}, {key: "templates", …}, {key: "formats", …},
    {key: "division", name, optional, state, at, found, applied, partial, error, text}]} — 항목 차례 = 헤딩 · 템플릿 · 서식 · 표 · 구분 기준(spec_작업 ② §20).
    — state = none · wait · running · done · failed(구분 기준은 none · running · done 만 — 한쪽 검토만 답했으면 partial). 해당 없는 항목은 없다(docx 는 items 가 비고 base "na" · 구분 기준은 hwpx 지원 양식일 때만).
    busy = 헤딩 작업이 하나라도 도는 중(1단계 포함) · job = 도는 중이거나 실패로 끝난 마지막 헤딩 작업(잘 끝났으면 null).
    kind = 작업에 적힌 작업 종류("rnd" | "general" | "" — 작업 저장이 꺼져 있으면 빈 글)."""
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    kind = ((works.work(s.id) or {}).get("task") or {}).get("kind") or ""
    ol = _outline(server, s)
    plans = tpl_agent_api.plans(s, ol[0].get("run")) if ol else {}
    return analysis.status(s, kind=kind, division=_division(server, s), outline=ol, plans=plans, place=_place(s, ol[0]) if ol else 0)


def start_chain(s, chain, key=None):
    """이어 돌리기를 헤딩 작업 자리에서 시작한다 → 헤딩 작업. chain = analysis_llm.CHAINS 의 이름("llm" LLM 검증·보완 · "heads" 헤딩 그래프(LLM) → 서식 정리 계획 · "formats" 서식 정리 계획만),
    key = 서식 정리 스킬 키(기본 "tidy"). 400 hwpx 아님 · skill 꼴 · 404 스킬 없음 · 409 헤딩 작업이 도는 중."""
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    if s.fmt != "hwpx":
        raise HTTPException(400, "LLM 검증·보완은 hwpx 문서에서만 됩니다(헤딩 추출이 hwpx 만)")
    key = key or "tidy"
    if not isinstance(key, str):
        raise HTTPException(400, "skill 은 스킬 키")
    try:
        tpl_agent_api.A.skill(key)
    except KeyError:
        raise HTTPException(404, "그런 스킬이 없습니다") from None
    how = analysis_llm.CHAINS[chain]

    def runner(sess, job):
        return analysis_llm.run(sess, job, outline=lambda x: _outline(server, x), plans=tpl_agent_api.plans,
                                plan=lambda x, tid: tpl_agent_api.plan_one(server, x, tid, key), **how)
    try:
        return heading_runs.start(s, 2, True, chain=chain, runner=runner)
    except heading_runs.Busy as e:
        raise HTTPException(409, str(e)) from e


@router.post("/api/docs/{doc_id}/analysis/llm", status_code=202)
def analysis_llm_start(doc_id: str, body: dict = Body(default={})):
    """「LLM 검증·보완」 시작 {skill?(서식 정리 스킬 키 — 기본 "tidy"), only?("formats" — 서식 정리 계획만)} → 202 헤딩 작업(job.view — chain "llm" | "formats"). 유료 LLM — 화면은 진행표의 「돌 것」(llmPlan)을 보인 단추로만 부른다.
    헤딩 · 템플릿 먼저 → 표 · 서식(계획만) 같이(app/analysis_llm.py) · 이미 LLM 을 거친 것은 건너뜀 · 문서는 안 바뀜.
    only "formats" = 계획이 없거나 옛것인 템플릿의 서식 정리 계획만(헤딩 · 표 LLM 은 안 돎 — 헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」). 400 hwpx 아님 · only 꼴 · 404 스킬 없음 · 409 헤딩 작업이 도는 중."""
    from app import server
    only = body.get("only")
    if only not in (None, "formats"):
        raise HTTPException(400, 'only 는 "formats" 뿐입니다')
    return start_chain(server._sess(doc_id), "formats" if only else "llm", body.get("skill")).view()


@router.delete("/api/docs/{doc_id}/analysis/llm")
def analysis_llm_stop(doc_id: str):
    """도는 이어 돌리기(「LLM 검증·보완」 · 「헤딩 그래프(LLM)」 → 서식 정리 계획 · 서식 정리 계획만)를 지금 도는 일(같이 도는 표 · 서식이면 둘 다 — 서식은 시작한 템플릿까지)이 끝나면 멈춘다 → {stopping: true}. 409 = 도는 것이 없음."""
    from app import server
    s = server._sess(doc_id)
    job = heading_runs.state(s).get("job") if s.fmt == "hwpx" else None
    if job is None or not job.chain or job.status != "running":
        raise HTTPException(409, "도는 LLM 검증·보완이 없습니다")
    job.stop = True
    return {"stopping": True}
