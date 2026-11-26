"""분석 상태 API(spec_작업 ② §20) — 문서 이름 줄의 표시(app/static/doc_status.js)가 읽는다. server.py 가 include 한다. 셈은 app/analysis.py.
GET 은 읽기만 한다 — 분석을 시작하지 않는다(시작은 `POST …/headings {first: true}` · `POST …/divisions/review`).
「LLM 검증·보완」(2026-11-16 — ② §20 「넷 · 진행표 · LLM 검증·보완」)은 `POST …/analysis/llm` 으로 시작하고 `DELETE` 로 멈춘다 — 실행은 app/analysis_llm.py."""
from fastapi import APIRouter, Body, HTTPException

from app import analysis, analysis_check, analysis_llm, heading_runs, outline_conform, outline_match, tpl_agent_api, works

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
    out = analysis.status(s, kind=kind, division=_division(server, s), outline=ol, plans=plans, place=_place(s, ol[0]) if ol else 0)
    if out["items"]:
        out["check"] = _check_view(s)   # 구간 검증이 남긴 「확인 필요」(지금 판정에 유효한 것만) | None(한 번도 안 함 · 못 셈) — 진행표가 보인다
    return out


def _check_view(s):
    """구간 검증(app/analysis_check.py)의 지금 보기 {pages, windows, left, finds, counts} | None(검증한 적 없음 · 헤딩 그래프 없음). 문서 차례 · 헤딩/표 실행 · 저장본마다 한 번 센다(도는 동안 2초마다 읽힌다)."""
    try:
        store = analysis_check.load(s.id)
        if not store["checked"]:
            return None
        graph, tables = heading_runs.graph(s), heading_runs.tables(s)
        if not graph:
            return None
        key = (s.rev, (graph.get("meta") or {}).get("run"), ((tables or {}).get("meta") or {}).get("run"), len(store["checked"]), max((c.get("at") or 0 for c in store["checked"].values()), default=0))
        got = getattr(s, "analysis_check_view", None)
        if got is None or got[0] != key:
            with s.lock:
                blocks = s.doc.blocks()
            got = s.analysis_check_view = (key, analysis_check.view(store, analysis_check.windows(blocks, graph, tables)))
        return got[1]
    except Exception:  # noqa: BLE001 — 보기를 못 세도 분석 상태는 그대로 낸다
        return None


@router.get("/api/docs/{doc_id}/analysis/check")
def analysis_check_get(doc_id: str):
    """구간 검증의 지금 보기 → {pages(구간의 쪽 수), windows[{no, pages[첫 쪽, 끝 쪽], checked}], left(아직 검증 안 한 구간 수), finds[{kind, name, id, text, what, suggest, sure, pages, at}], counts{heading, table, missed}}
    — 한 번도 검증하지 않았으면 {pages, windows: [], left: 0, finds: [], counts: {}}. 읽기만 한다(검증은 「LLM 검증·보완」 이 한다 — POST …/analysis/llm {check: true})."""
    from app import server
    s = server._sess(doc_id)
    return (_check_view(s) if s.fmt == "hwpx" else None) or {"pages": analysis_check.PAGES, "windows": [], "left": 0, "finds": [], "counts": {}}


def start_chain(s, chain, key=None, *, writing_guidance=False, windows=False):
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
        n = analysis_llm.run(sess, job, outline=lambda x: _outline(server, x), plans=tpl_agent_api.plans,
                             plan=lambda x, tid: tpl_agent_api.plan_one(server, x, tid, key), windows=windows and chain == "llm", **how)
        if writing_guidance and not job.stop:
            from app import writing_guidance_api
            writing_guidance_api.start(sess)
        return n
    try:
        return heading_runs.start(s, 2, True, chain=chain, runner=runner)
    except heading_runs.Busy as e:
        raise HTTPException(409, str(e)) from e


@router.post("/api/docs/{doc_id}/analysis/llm", status_code=202)
def analysis_llm_start(doc_id: str, body: dict = Body(default={})):
    """「LLM 검증·보완」 시작 {skill?(기본 "tidy"), only?("formats"), writingGuidance?(양식 작성 04), check?(끝에 구간 검증 — 10쪽씩)} → 202 헤딩 작업.
    헤딩 · 표의 판정 호출은 두 모델(LLM1 · LLM2 — 그 에이전트의 모델 자리)이 따로 답하고 다르면 협의한다(app/llm_duo.py — 「한 모델만」 으로 둔 에이전트는 한 번).
    writingGuidance가 참이면 구조 판정이 성공한 뒤 작성 지침을 추출한다. 그 실행 상태는 GET …/writing-guidance에서 읽는다.
    헤딩 · 템플릿과 표 판정의 호출을 같이 → 헤딩 그래프가 끝나면 서식(계획만 — 템플릿끼리 같이)(app/analysis_llm.py — 헤딩을 건너뛰면 표 · 서식이 같이) · 이미 LLM 을 거친 것은 건너뜀 · 문서는 안 바뀜.
    only "formats" = 계획이 없거나 옛것인 템플릿의 서식 정리 계획만(헤딩 · 표 LLM 은 안 돎 — 헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」). 400 hwpx 아님 · only 꼴 · 404 스킬 없음 · 409 헤딩 작업이 도는 중."""
    from app import server
    only = body.get("only")
    if only not in (None, "formats"):
        raise HTTPException(400, 'only 는 "formats" 뿐입니다')
    server._flow_busy_other(doc_id, "single")   # 문서 하나의 서버 실행이 이 문서에서 도는 동안 사람이 건 「LLM 검증·보완」 은 409(그 실행이 스스로 거는 것은 지나간다 — spec_워크플로우 ② §18-13)
    guidance = body.get("writingGuidance", False)
    if not isinstance(guidance, bool) or (guidance and only):
        raise HTTPException(400, "writingGuidance는 전체 검증·보완에서만 쓰는 참·거짓 값입니다")
    windows = body.get("check", False)   # 끝에 구간 검증(10쪽씩 — app/analysis_check.py)을 더한다: 화면의 「LLM 검증·보완」 · 워크플로우의 그 줄이 청한다(2026-11-26)
    if not isinstance(windows, bool) or (windows and only):
        raise HTTPException(400, "check 는 전체 검증·보완에서만 쓰는 참·거짓 값입니다")
    return start_chain(server._sess(doc_id), "formats" if only else "llm", body.get("skill"), writing_guidance=guidance, windows=windows).view()


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
