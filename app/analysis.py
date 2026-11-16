"""분석 상태(spec_작업 ② §20) — 문서마다 「분석이 어디까지 됐는지」 를 어느 TASK 에서나 같은 꼴로 센다: 기본 분석(헤딩 · 표 — 스크립트, 올리면 저절로) ·
LLM 판정(헤딩 · 표 — 사람이 단추로) · 구분 기준 LLM 검토(옵션 — 연구개발 문서만). 사용자 2026-11-15 "task 마다 작업을 표준화 … 올리면 어디까지 작업이 되었는지 표시".

읽기만 한다 — 분석을 시작하지 않고 결과·문서를 바꾸지 않는다. 헤딩·표는 헤딩 추출의 지금 결과(heading_runs.state — 2단계 헤딩 그래프 · 3단계 표 구조)와 도는 작업,
구분 기준은 세션의 마지막 LLM 검토(division.review · reviewing)를 본다. 화면 = 문서 이름 줄의 표시(app/static/doc_status.js), 끝점 = app/analysis_api.py.

- 상태: none 없음 · wait 대기(앞 항목이 도는 중) · running 도는 중 · done 됨 · failed 실패. 해당 없는 항목은 목록에 넣지 않는다(docx = 항목 없음 · base "na").
- 문서를 고친 뒤에도 done 이다(뼈대 유지 — spec_헤딩_추출 ② §17). moved = 그 결과를 뽑은 뒤 문서가 바뀜(도움말에만 쓴다)."""
from app import heading_runs

STATES = ("none", "wait", "running", "done", "failed")
NAMES = {"heads": "헤딩", "tables": "표", "division": "구분 기준"}
STAGE = {"heads": ("stage2", 2, "헤딩 그래프"), "tables": ("stage3", 3, "표 구조")}


def _llm(res, running, failed=None):
    """그 결과의 LLM 판정 → {state, text, error} — 지금 결과가 LLM 을 거친 것인가(스크립트로 다시 돌려 덮었으면 none).
    failed = 방금 LLM 실행이 예외로 끝난 까닭(앞 결과는 그대로 남는다) — 지금 결과가 LLM 을 거친 것이 아니면 failed 로 보인다."""
    if running:
        return {"state": "running", "text": "LLM 판정 중", "error": None}
    lm = (res or {}).get("llm") or {}
    if failed and not (lm.get("requested") and not lm.get("fallback")):
        return {"state": "failed", "text": "LLM 판정 실행이 실패함" + (" — 앞 결과는 그대로" if res is not None else ""), "error": failed}
    if not lm.get("requested"):
        return {"state": "none", "text": "LLM 판정 안 함" + (" — 스크립트 결과" if res is not None else ""), "error": None}   # 결과가 아예 없으면 「스크립트 결과」 라고 하지 않는다
    if lm.get("fallback"):
        return {"state": "failed", "text": "LLM 판정을 못 해 스크립트 결과로 대신함", "error": lm.get("error") or "LLM 응답 없음"}
    bits = [f"반영 {lm['applied']}" if lm.get("applied") is not None else "", f"호출 {lm['calls']}" if lm.get("calls") else "", f"실패 {lm['failed']}" if lm.get("failed") else ""]
    return {"state": "done", "text": "LLM 판정함" + (" — " + " · ".join(b for b in bits if b) if any(bits) else ""), "error": None}


def _text(key, res):
    """도움말 한 줄 — 「헤딩 그래프 — 실행 5 · 템플릿 21」."""
    name, meta, counts = STAGE[key][2], (res or {}).get("meta") or {}, (res or {}).get("counts") or {}
    if res is None:
        return f"{name} 결과 없음"
    what = (f"템플릿 {counts.get('templates', 0)} · 헤딩 {counts.get('nodes', 0)}" if key == "heads" else f"표 {counts.get('tables', 0)} · 칸 {counts.get('cells', 0)}")
    return f"{name} — " + " · ".join(b for b in (f"실행 {meta['run']}" if meta.get("run") else "", what) if b)


def _failed(key, st, job):
    """결과 없이 헤딩 작업이 실패로 끝남 — 첫 분석은 멈춘 단계만(헤딩에서 멈췄으면 표는 「없음」)."""
    if job is None or job.status != "failed" or st.get(STAGE[key][0]) is not None:
        return False
    if job.first:
        return key == "heads" or st.get("stage2") is not None
    return job.stage == STAGE[key][1]


def _item(key, st, sess, job, turn):
    """헤딩·표 항목 하나. turn = 지금 도는 작업이 이 항목에 하는 일: None | "run"(스크립트로 뽑는 중) | "llm"(LLM 판정 중) | "wait"(앞 항목 차례)."""
    res = st.get(STAGE[key][0])
    meta = (res or {}).get("meta") or {}
    failed = _failed(key, st, job)
    llm_failed = job.error if job is not None and job.status == "failed" and job.use_llm and not job.first and job.stage == STAGE[key][1] else None
    state = "running" if turn in ("run", "llm") and (res is None or turn == "run") else "wait" if turn == "wait" else "done" if res is not None else "failed" if failed else "none"
    return {"key": key, "name": NAMES[key], "state": state, "run": meta.get("run"), "at": meta.get("at"), "moved": res is not None and meta.get("rev") != sess.rev,
            "text": _text(key, res), "error": job.error if failed else None, "llm": _llm(res, turn == "llm", llm_failed)}


def _turns(st, job):
    """도는 헤딩 작업 → {"heads": turn, "tables": turn}. 첫 분석은 2단계 → 3단계를 잇달아(있는 단계는 건너뜀 — heading_runs.run_first), 1단계 작업은 항목에 영향이 없다."""
    if job is None or job.status != "running":
        return {}
    if job.first:
        if st.get("stage2") is None:
            return {"heads": "run", **({"tables": "wait"} if st.get("stage3") is None else {})}
        return {"tables": "run"} if st.get("stage3") is None else {}
    kind = "llm" if job.use_llm else "run"
    return {"heads": kind} if job.stage == 2 else {"tables": kind} if job.stage == 3 else {}


def _division(sess):
    dv = getattr(sess, "division", None) or {}
    r = dv.get("review") if isinstance(dv.get("review"), dict) else None
    found, applied = len(((r or {}).get("missing") or {}).get("missing") or []), len(((r or {}).get("review") or {}).get("applied") or [])
    errors = (r or {}).get("errors") or {}   # 부른 검토 가운데 답을 못 받은 것 {review | missing: 까닭} — 한쪽만 답해도 결과는 남는다(server.divisions_review)
    error = " · ".join(f"{'재검토' if k == 'review' else '빠진 자리 검토'} — {v}" for k, v in errors.items()) or None
    state = "running" if dv.get("reviewing") else "done" if r else "none"   # 구분 기준은 none · running · done 셋뿐 — 모두 실패한 검토는 저장되지 않아 none 으로 남는다(알림만)
    text = ("구분 기준 LLM 검토 중" if state == "running" else f"구분 기준 LLM 검토함 — 빠진 자리 후보 {found} · 재검토 반영 {applied}" + (f" · 답을 못 받은 검토: {error}" if error else "")
            if r else "구분 기준 LLM 검토 안 함(옵션)")
    return {"key": "division", "name": NAMES["division"], "optional": True, "state": state, "at": (r or {}).get("at"), "found": found, "applied": applied,
            "partial": state == "done" and bool(errors), "error": error if state == "done" else None, "text": text}


def _base(items):
    states = [i["state"] for i in items if i["key"] in STAGE]
    if not states:
        return "na"
    return ("running" if any(s in ("running", "wait") for s in states) else "done" if all(s == "done" for s in states)
            else "failed" if "failed" in states else "none")


def status(sess, kind="", division=False):
    """→ {rev, format, kind, base, busy, job, items[…]} — spec_작업 ② §20. busy = 헤딩 작업이 하나라도 도는 중(1단계 포함 — 그동안은 새 분석을 못 건다). kind = 작업에 적힌 작업 종류(화면이 구분 기준 항목을 보일지 정한다), division = 이 문서에 구분 기준 항목이 있는가(hwpx · 지원 양식)."""
    out = {"rev": sess.rev, "format": sess.fmt, "kind": kind or "", "base": "na", "busy": False, "job": None, "items": []}
    if sess.fmt != "hwpx":   # 헤딩 추출은 hwpx 만 — 항목 없음
        return out
    st = heading_runs.state(sess)
    job = st.get("job")
    turns = _turns(st, job)
    out["items"] = [_item(key, st, sess, job, turns.get(key)) for key in ("heads", "tables")]
    if division:
        out["items"].append(_division(sess))
    out["base"] = _base(out["items"])
    out["busy"] = job is not None and job.status == "running"
    if job is not None and (job.status == "running" or job.status == "failed"):
        v = job.view()
        what = "첫 분석" if job.first else f"{job.stage}단계" + (" · LLM" if job.use_llm else "")
        out["job"] = {"first": job.first, "stage": job.stage, "llm": job.use_llm, "status": job.status, "what": what, "started": v["started"], "error": v["error"]}
    return out
