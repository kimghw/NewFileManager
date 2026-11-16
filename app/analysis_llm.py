"""LLM 검증·보완(spec_작업 ② §20 「넷 · 진행표 · LLM 검증·보완」 — 2026-11-16 사용자 답 「단추 하나로 넷을 차례로」).

헤딩 작업 자리 하나(heading_runs.start 의 runner — 다른 헤딩 작업과 겹치면 Busy)에서 차례로:
  ① 헤딩 · 템플릿 = 「헤딩 그래프(LLM)」(heading_runs.run_stage2 — 못 맞춤·충돌 규칙 보강부터) — 지금 결과가 이미 LLM 을 거쳤으면 건너뜀
  ② 표 = 「표 구조(LLM)」(run_stage3) — 이미 LLM 을 거쳤고 ①이 다시 돌지 않았으면 건너뜀
  ③ 서식 = 갈래가 둘 이상인 템플릿마다 「템플릿 서식 정리」 계획만(tpl_agent_api.plan_one — 받은 계획은 작업 폴더에 남는다) — 계획이 없거나 옛것인 템플릿만
**문서는 바꾸지 않는다** — 계획의 반영은 사람이 「템플릿 서식 정리」 열에서 고른 것만. 한 단계의 LLM 이 답을 못 하면(스크립트로 대신함) 거기서 멈추고 실패로 남긴다.
건너뛰는 기준은 분석 상태(app/analysis.py llm_plan)와 같다. server 를 import 하지 않는다 — outline · plans · plan 을 받는다(app/analysis_api.py 가 넘긴다)."""
from app import analysis, heading_runs, works

PARTS = (("heads", "헤딩 · 템플릿 — 헤딩 그래프(LLM)"), ("tables", "표 — 표 구조(LLM)"), ("formats", "서식 — 템플릿 서식 정리 계획"))


class Stop(Exception):
    """한 단계의 LLM 이 답을 못 함 — 이어 돌리기를 멈추고 실패로 남긴다(plain = 작업 오류 글에 예외 이름을 붙이지 않는다 — heading_runs.start)."""
    plain = True


def _why(err):
    """LLM 이 답을 못 한 까닭 — 사람이 읽는 글로."""
    return {"off": "LLM 이 꺼져 있습니다(서버의 LLM 설정)", "busy": "다른 LLM 작업이 자리를 다 쓰고 있습니다", None: "LLM 응답 없음", "": "LLM 응답 없음"}.get(err, err)


def llm_done(res):
    """그 결과가 LLM 판정을 거쳤는가(analysis._llm 의 done 과 같은 기준)."""
    lm = (res or {}).get("llm") or {}
    return bool(lm.get("requested") and not lm.get("fallback"))


def _part(job, key, status, msg=""):
    with job.lock:
        for x in job.parts:
            if x["key"] == key:
                x.update(status=status, msg=msg)


def _stopped(job):
    """멈추기를 눌렀으면 남은 일을 「멈춤」 으로 적고 참."""
    if not job.stop:
        return False
    with job.lock:
        for x in job.parts:
            if x["status"] == "wait":
                x.update(status="stopped", msg="멈추기를 눌러 돌리지 않음")
    return True


def _log(sess, st, stage, job, n):
    works.log(sess.id, "headings", stage=stage, llm=True, status="done", rev=job.rev, chain="llm",
              **({"n": n} if st.get("lastSaved") is not False else {"saved": False}))


def run(sess, job, *, outline, plans, plan):
    """job = heading_runs.Job(chain "llm"). outline(sess) → (개요 오버레이, 서식 갈래) | None · plans(sess, graph) → {tpl: 기록} · plan(sess, tpl) → 계획(실패는 예외).
    → 마지막으로 저장한 헤딩 실행 번호 | None."""
    st = heading_runs.state(sess)
    job.parts = [{"key": k, "name": name, "status": "wait", "msg": ""} for k, name in PARTS]
    n = None

    # ① 헤딩 · 템플릿
    job.phase, job.stage = "heads", 2
    rebuilt = False
    if llm_done(st.get("stage2")):
        _part(job, "heads", "skip", "지금 결과가 이미 LLM 판정을 거쳤습니다 — 건너뜀")
    else:
        _part(job, "heads", "running")
        n = heading_runs.run_stage2(sess, job, True)
        _log(sess, st, 2, job, n)
        lm = (st.get("stage2") or {}).get("llm") or {}
        if not llm_done(st.get("stage2")):
            why = _why(lm.get("error"))
            _part(job, "heads", "failed", f"LLM 판정을 못 해 스크립트 결과로 대신함 — {why}")
            raise Stop(f"헤딩 그래프 LLM 판정을 못 함 — {why}")
        rebuilt = True
        rules = lm.get("rules") or {}
        _part(job, "heads", "ok", " · ".join(b for b in (f"규칙 보강 {rules.get('saved', 0)}" if rules else "", f"반영 {lm.get('applied', 0)}",
                                                            f"호출 {lm.get('calls', 0)}" if lm.get("calls") else "") if b))
    if _stopped(job):
        return n

    # ② 표
    job.phase, job.stage = "tables", 3
    if llm_done(st.get("stage3")) and not rebuilt:
        _part(job, "tables", "skip", "지금 결과가 이미 LLM 판정을 거쳤습니다 — 건너뜀")
    else:
        _part(job, "tables", "running")
        n = heading_runs.run_stage3(sess, job, True)
        _log(sess, st, 3, job, n)
        lm = (st.get("stage3") or {}).get("llm") or {}
        if not llm_done(st.get("stage3")):
            why = _why(lm.get("error"))
            _part(job, "tables", "failed", f"LLM 판정을 못 해 스크립트 결과로 대신함 — {why}")
            raise Stop(f"표 구조 LLM 판정을 못 함 — {why}")
        _part(job, "tables", "ok", " · ".join(b for b in (f"반영 {lm.get('applied', 0)}", f"호출 {lm.get('calls', 0)}" if lm.get("calls") else "") if b))
    if _stopped(job):
        return n

    # ③ 서식 — 계획만
    job.phase = "formats"
    got = outline(sess)
    if got is None:
        _part(job, "formats", "skip", "헤딩 그래프가 없어 서식 갈래를 셀 수 없습니다")
        return n
    ov, variants = got
    have = plans(sess, ov.get("run"))
    todo = [tid for tid in analysis.need_templates(variants) if analysis.plan_state(have.get(tid), sess.rev) in ("none", "stale")]
    if not todo:
        _part(job, "formats", "skip", "정리할 것 없음" if not analysis.need_templates(variants) else "모든 템플릿의 계획을 받았습니다 — 건너뜀")
        return n
    names = {str(tid): str(t.get("no", tid)) for tid, t in (ov.get("templates") or {}).items()}
    ok, bad = [], []
    for i, tid in enumerate(todo):
        if job.stop:
            break
        _part(job, "formats", "running", f"T{names.get(tid, tid)} 계획 받는 중 ({i + 1}/{len(todo)})")
        try:
            plan(sess, tid)
            ok.append(f"T{names.get(tid, tid)}")
        except Exception as e:  # 템플릿 하나의 실패는 그것만 — 다음 템플릿을 한다
            bad.append(f"T{names.get(tid, tid)}: {getattr(e, 'detail', None) or e}")
    left = len(todo) - len(ok) - len(bad)
    msg = " · ".join(b for b in (f"계획 받음 {' · '.join(ok)}" if ok else "", f"실패 {' / '.join(bad)}" if bad else "",
                                 f"멈춤 — 남은 템플릿 {left}" if left else "") if b)
    if bad and not ok:
        _part(job, "formats", "failed", msg)
        raise Stop(f"서식 정리 계획을 하나도 받지 못함 — {bad[0]}")
    _part(job, "formats", "partial" if bad or left else "ok", msg + (" — 반영은 「템플릿 서식 정리」 열에서 고른 것만(문서는 안 바뀜)" if ok else ""))
    return n
