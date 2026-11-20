"""LLM 검증·보완(spec_작업 ② §20 「넷 · 진행표 · LLM 검증·보완」 — 2026-11-16 사용자 답 「단추 하나로 넷을 차례로」).

헤딩 작업 자리 하나(heading_runs.start 의 runner — 다른 헤딩 작업과 겹치면 Busy)에서:
  ① 헤딩 · 템플릿 = 「헤딩 그래프(LLM)」(heading_runs.run_stage2 — 못 맞춤·충돌 규칙 보강부터) — 지금 결과가 이미 LLM 을 거쳤으면 건너뜀
  ② 표 = 「표 구조(LLM)」(run_stage3) — 이미 LLM 을 거쳤고 ①이 다시 돌지 않았으면 건너뜀
  ③ 서식 = 갈래가 둘 이상인 템플릿마다 「템플릿 서식 정리」 계획만(tpl_agent_api.plan_one — 받은 계획은 작업 폴더에 남는다) — 계획이 없거나 옛것인 템플릿만.
     템플릿끼리도 같이(LLM 자리 수까지 — 템플릿마다 따로 선 일)
같이 도는 것(2026-11-16 사용자 "각각 병렬로 할 수 있는 작업은 표기를 하고 병렬로 할 수 있으면 병렬로 해줘" · 2026-11-17 "문서가 큰 경우 병렬에이전트를 사용해서 판정 및 실행을 할 수 있도록"):
  - **①이 돌 때 — ②의 판정 호출(T)은 ①과 같이**: T 호출은 1단계 결과에만 기댄다(보낼 표 · 초안) — ①의 규칙 보강이 끝나 1단계가 정해지면 바로 묻기 시작하고(heading_runs.TablesAhead),
    ①이 끝나면 받은 답에 표의 소속(헤딩 그래프)을 붙여 ②를 맺는다. 큰 문서에서 ①의 유형 판정(한 호출 · 1~3분) 동안 비던 LLM 자리를 표 판정이 쓴다. ③ 은 ①의 헤딩 그래프(템플릿)가 있어야 해서 ①이 끝난 뒤.
  - **①을 건너뛸 때 — ②·③ 이 같이**(둘 다 지금 헤딩 그래프에만 기대고 서로는 기대지 않는다).
  차례 번호(analysis.part_nos — 같은 번호 = 같이 돎 · 화면이 「같이」 로 적는다): ①이 돌면 1 · 1 · 2, 건너뛰면 1 · 2 · 2.
LLM 자리(llm — NFM_LLM_SLOTS)는 서버 전체가 나눠 쓴다 — 같이 돌아도 자리보다 많이 부르지는 않는다(넘는 호출은 자리를 기다린다).
**문서는 바꾸지 않는다** — 계획의 반영은 사람이 「템플릿 서식 정리」 열에서 고른 것만. 한 단계의 LLM 이 답을 못 하면(스크립트로 대신함) 그 단계를 실패로 남기고 아직 시작하지 않은 단계는 돌리지 않는다
(①이 실패하면 ③ 은 대기로 남음 · **이미 묻기 시작한 ②는 받은 답으로 맺는다** — 유료 답을 버리지 않는다: 소속은 스크립트 헤딩 그래프에서 · 같이 도는 단계는 한쪽이 실패해도 다른 쪽은 제 일을 마친다 — 작업은 실패로 끝남).
멈추기는 지금 도는 단계가 끝나면(①과 같이 묻던 ②는 맺고 · ③ 은 아직 시작하지 않은 템플릿부터).
건너뛰는 기준은 분석 상태(app/analysis.py llm_plan)와 같다. server 를 import 하지 않는다 — outline · plans · plan 을 받는다(app/analysis_api.py 가 넘긴다).

이어 돌리기는 셋이다(CHAINS — job.chain 의 이름 · 화면 이름은 analysis.CHAIN_NAMES):
  llm     = 위 ① → ②·③ — 진행표의 「LLM 검증·보완」
  heads   = ① → ③ — 「헤딩 그래프(LLM)」(2026-11-16 사용자 답 「헤딩 LLM 판정에 늘 이어서」: 어디서 돌리든 헤딩 판정이 끝나면 서식 정리 계획까지). 사람이 그 단추를 눌렀으므로 ①은 이미 LLM 을
            거친 결과여도 **다시 돈다**(force) · LLM 이 답을 못 해 스크립트로 대신했으면 전처럼 작업은 끝난 것으로 두고(단계 줄에 실패) ③ 은 돌리지 않는다(strict 아님)
  formats = ③ 만 — 헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」(계획이 없거나 옛것인 템플릿만)"""
import concurrent.futures
import threading

from app import agent_notes, analysis, heading_runs, llm, tpl_agent, works

PARTS = (("heads", "헤딩 · 템플릿 — 헤딩 그래프(LLM)"), ("tables", "표 — 표 구조(LLM)"), ("formats", "서식 — 템플릿 서식 정리 계획"))  # 차례 번호는 analysis.part_nos(헤딩이 도느냐에 따라 — 같은 번호 = 같이 돎)
PLAN_WORKERS = None  # 서식 정리 계획을 같이 받는 템플릿 수 — None = LLM 자리 수(llm.slots_n: 자리는 서버 전체가 나눠 쓴다 — 표 판정이 아직 돌면 자리를 기다릴 뿐이다) · 시험이 수로 바꾼다
AHEAD_NOTE = "헤딩 판정과 같이"  # 표 판정 호출을 ①과 같이 돌릴 때 단계 글에 붙는 말
CHAINS = {"llm": {"parts": ("heads", "tables", "formats"), "force": False, "strict": True},      # 이름 → 도는 단계 · 헤딩을 늘 다시 도나 · 헤딩 LLM 이 답을 못 하면 작업을 실패로 끝내나
          "heads": {"parts": ("heads", "formats"), "force": True, "strict": False},
          "formats": {"parts": ("formats",), "force": False, "strict": True}}
FORMATS_STEP = "서식 정리 계획 — LLM"  # 헤딩 작업의 단계 줄 이름(추출·설정의 진행 목록 · 요약의 「지금 하는 일」 — app.js headsProgNow 가 이 이름으로 가른다)


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
    """단계 하나의 상태 — job.phase 는 지금 도는 단계 가운데 첫째(같이 돌면 둘 — 분석 상태는 parts 로 가른다: analysis.chain_parts)."""
    with job.lock:
        for x in job.parts:
            if x["key"] == key:
                x.update(status=status, msg=msg)
        run = [x["key"] for x in job.parts if x["status"] == "running"]
        if run:
            job.phase = run[0]


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
    works.log(sess.id, "headings", stage=stage, llm=True, status="done", rev=job.rev, chain=job.chain or "llm",
              **({"n": n} if st.get("lastSaved") is not False else {"saved": False}))


def run(sess, job, *, outline, plans, plan, parts=None, force=False, strict=True):
    """job = heading_runs.Job(chain "llm" · "heads" · "formats" — CHAINS). outline(sess) → (개요 오버레이, 서식 갈래) | None · plans(sess, graph) → {tpl: 기록} · plan(sess, tpl) → 계획(실패는 예외).
    parts = 돌 단계(없으면 셋 다) · force = 헤딩이 이미 LLM 을 거쳤어도 다시 돈다 · strict = 헤딩 LLM 이 답을 못 하면 작업을 실패로 끝낸다(아니면 단계만 실패로 적고 뒤 단계는 돌리지 않은 채 끝낸다).
    → 마지막으로 저장한 헤딩 실행 번호 | None."""
    st = heading_runs.state(sess)
    parts = tuple(parts or [k for k, _ in PARTS])
    heads_run = "heads" in parts and (force or not llm_done(st.get("stage2")))  # ①이 실제로 도나(_heads 와 같은 기준)
    nos = analysis.part_nos(parts, heads_run)  # 차례 번호는 도는 단계끼리 1부터(같은 번호 = 같이 돎)
    job.parts = [{"key": k, "name": name, "no": nos[k], "status": "wait", "msg": ""} for k, name in PARTS if k in parts]
    n = None
    rebuilt = False
    ahead = None
    if "heads" in parts:
        if heads_run and "tables" in parts:  # ②의 판정 호출을 ①과 같이 — run_stage2 가 1단계를 정한 뒤 시작한다(TablesAhead)
            ahead = job.tables_ahead = heading_runs.TablesAhead(
                on_progress=lambda done, total: _part(job, "tables", "running", f"표 판정 호출 {done}/{total} 끝남 — {AHEAD_NOTE}"))
        try:
            n, rebuilt, ok = _heads(sess, job, st, force, strict)
        except Stop:  # ①의 LLM 이 답을 못 함 — 이미 묻기 시작한 ②는 받은 답으로 맺고(유료 답을 버리지 않는다) 작업은 ①의 까닭으로 실패
            if ahead is not None and ahead.started:
                _close_ahead(sess, job, st, "wait", "")  # 쓸 답이 없으면(LLM 꺼짐 …) 전처럼 대기로 — 표의 앞 결과를 건드리지 않는다
            raise
        except Exception:  # ①이 오류로 끝남 — ②의 답은 붙일 그래프가 없다(묻던 스레드는 저절로 끝난다)
            if ahead is not None and ahead.started:
                why = "헤딩 판정이 오류로 끝나 표 구조를 짓지 않음 — 받은 답은 쓰지 않음"
                ahead.drop(job, why)
                _part(job, "tables", "stopped", why)
            raise
        if not ok or _stopped(job):
            if ahead is not None and ahead.started:  # 멈추기 — ①과 같이 묻던 ②는 「도는 단계」 라 맺는다
                n3 = _close_ahead(sess, job, st, "stopped", "멈추기를 눌러 돌리지 않음")
                return n3 if n3 is not None else n
            return n
    rest = [k for k in ("tables", "formats") if k in parts]
    if not rest:
        return n

    # ② 표(①과 같이 물었으면 받은 답에 소속을 붙여 맺는다) · ③ 서식(계획만) — 같이(둘 다 ①의 헤딩 그래프에만 기댄다)
    if "tables" in rest:
        job.stage = 3
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(rest), thread_name_prefix="llm-check") as ex:
        ft = ex.submit(agent_notes.carry(_tables), sess, job, st, rebuilt) if "tables" in rest else None   # carry = 지금 워크플로우(에이전트에 덧붙이는 글의 전용 범위)를 일꾼 스레드로
        ff = ex.submit(agent_notes.carry(_formats), sess, job, outline, plans, plan) if "formats" in rest else None
    err = (ft.exception() if ft else None) or (ff.exception() if ff else None)  # 둘 다 끝난 뒤 — 실패는 표가 먼저(작업 오류 글 하나)
    if err is not None:
        raise err
    n3 = ft.result() if ft else None
    return n3 if n3 is not None else n


def _close_ahead(sess, job, st, status, msg):
    """①이 실패했거나 멈추기를 누른 뒤 — ①과 같이 묻기 시작한 ②를 받은 답으로 맺는다 → 저장한 실행 번호 | None. ②의 실패는 단계 줄에만 남긴다(작업의 까닭은 ①의 것).
    **받은 답 가운데 쓸 것이 하나도 없으면**(LLM 꺼짐 · 자리 없음 · 호출이 모두 실패) 표 구조를 짓지 않는다 — ②를 status · msg 로 적고 앞 결과는 그대로 둔다(「LLM 실패」 결과로 덮지 않는다)."""
    ahead = job.tables_ahead
    if not ahead.useful():
        ahead.drop(job, "표 판정 호출이 답을 받지 못함 — 표 구조는 앞 결과 그대로")
        _part(job, "tables", status, msg)
        return None
    job.stage = 3
    try:
        return _tables(sess, job, st, True)
    except Exception as e:  # 표 LLM 도 답을 못 함(Stop) · 조립 오류 — 단계 줄에 적고 삼킨다
        if not isinstance(e, Stop):
            _part(job, "tables", "failed", f"표 구조를 짓다가 오류 — {type(e).__name__}: {e}"[:300])
        return None


def _heads(sess, job, st, force, strict):
    """① 헤딩 · 템플릿 → (저장한 실행 번호 | None, 다시 지었나, 뒤 단계를 돌려도 되나)."""
    n = None
    job.phase, job.stage = "heads", 2
    rebuilt = False
    if llm_done(st.get("stage2")) and not force:
        _part(job, "heads", "skip", "지금 결과가 이미 LLM 판정을 거쳤습니다 — 건너뜀")
    else:
        _part(job, "heads", "running")
        n = heading_runs.run_stage2(sess, job, True)
        _log(sess, st, 2, job, n)
        lm = (st.get("stage2") or {}).get("llm") or {}
        if not llm_done(st.get("stage2")):
            why = _why(lm.get("error"))
            _part(job, "heads", "failed", f"LLM 판정을 못 해 스크립트 결과로 대신함 — {why}")
            if strict:
                raise Stop(f"헤딩 그래프 LLM 판정을 못 함 — {why}")
            with job.lock:  # 「헤딩 그래프(LLM)」 — 전처럼 작업은 끝난 것으로(결과 = 스크립트 대체 판정 · 단계 줄에 실패). 뒤 단계는 돌리지 않는다
                for x in job.parts:
                    if x["status"] == "wait":
                        x.update(status="stopped", msg="헤딩 LLM 판정을 못 해 돌리지 않음")
            return n, True, False
        rebuilt = True
        rules = lm.get("rules") or {}
        _part(job, "heads", "ok", " · ".join(b for b in (f"규칙 보강 {rules.get('saved', 0)}" if rules else "", f"반영 {lm.get('applied', 0)}",
                                                            f"호출 {lm.get('calls', 0)}" if lm.get("calls") else "") if b))
    return n, rebuilt, True


def _tables(sess, job, st, rebuilt):
    """② 표 구조(LLM) → 저장한 실행 번호 | None(건너뜀)."""
    if llm_done(st.get("stage3")) and not rebuilt:
        _part(job, "tables", "skip", "지금 결과가 이미 LLM 판정을 거쳤습니다 — 건너뜀")
        return None
    ahead = getattr(job, "tables_ahead", None)
    with job.lock:
        going = any(x["key"] == "tables" and x["status"] == "running" for x in job.parts)
    if not going:  # ①과 같이 묻기 시작했으면 이미 「도는 중」 — 그 진행 글(호출 n/m)을 지우지 않는다
        _part(job, "tables", "running", "받은 표 판정 답을 헤딩 그래프에 붙이는 중" if ahead is not None and ahead.started else "")
    n = heading_runs.run_stage3(sess, job, True)
    _log(sess, st, 3, job, n)
    lm = (st.get("stage3") or {}).get("llm") or {}
    if not llm_done(st.get("stage3")):
        why = _why(lm.get("error"))
        _part(job, "tables", "failed", f"LLM 판정을 못 해 스크립트 결과로 대신함 — {why}")
        raise Stop(f"표 구조 LLM 판정을 못 함 — {why}")
    _part(job, "tables", "ok", " · ".join(b for b in (f"반영 {lm.get('applied', 0)}", f"호출 {lm.get('calls', 0)}" if lm.get("calls") else "",
                                                       f"호출은 {AHEAD_NOTE}" if lm.get("ahead") else "") if b))
    return n


def _formats(sess, job, outline, plans, plan):
    """③ 서식 — 정리할 템플릿마다 계획만, 템플릿끼리 같이(LLM 자리 수까지 — PLAN_WORKERS). 멈추기를 누르면 아직 시작하지 않은 템플릿은 하지 않는다.
    단계의 상태는 이어 돌리기의 단계(job.parts — 분석 상태)와 헤딩 작업의 단계 줄(job.step — 추출·설정의 진행 목록) 두 곳에 같이 적는다."""
    def part(status, msg=""):
        _part(job, "formats", status, msg)
        job.step(FORMATS_STEP, "running" if status == "running" else "failed" if status == "failed" else "ok", msg)
    got = outline(sess)
    if got is None:
        part("skip", "헤딩 그래프가 없어 서식 가짓수를 셀 수 없습니다")
        return
    ov, variants = got
    have = plans(sess, ov.get("run"))
    todo = [tid for tid in analysis.need_templates(variants) if analysis.plan_state(have.get(tid), sess.rev, ov, tpl_agent.fingerprint(ov, tid, variants.get(tid))) in ("none", "stale")]  # 반영했다가 되돌린 계획도 stale — 다시 받는다
    if not todo:
        part("skip", "정리할 것 없음" if not analysis.need_templates(variants) else "모든 템플릿의 계획을 받았습니다 — 건너뜀")
        return
    names = {str(tid): str(t.get("no", tid)) for tid, t in (ov.get("templates") or {}).items()}
    tag = {tid: f"T{names.get(tid, tid)}" for tid in todo}
    lock = threading.Lock()  # 아래 셋 — 잡은 채 job.lock(_part)을 잡는다(거꾸로는 없음)
    ok, bad, now = set(), {}, []

    def show():  # lock 안에서
        doing = f"{' · '.join(now)} 계획 받는 중" + (f"(같이 {len(now)})" if len(now) > 1 else "") if now else "계획 받는 중"
        part("running", f"{doing} — 끝남 {len(ok) + len(bad)}/{len(todo)}")

    def one(tid):
        if job.stop:
            return
        with lock:
            now.append(tag[tid])
            show()
        why = None
        try:
            plan(sess, tid)
        except Exception as e:  # 템플릿 하나의 실패는 그것만 — 다른 템플릿은 그대로
            why = str(getattr(e, "detail", None) or e)
        with lock:
            now.remove(tag[tid])
            if why is None:
                ok.add(tid)
            else:
                bad[tid] = why
            show()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(todo), PLAN_WORKERS or llm.slots_n()), thread_name_prefix="tpl-plan") as ex:
        list(ex.map(agent_notes.carry(one), todo))   # carry = 지금 워크플로우를 일꾼 스레드로(같은 함수를 여러 스레드가 함께 불러도 된다)
    got_ok = [tag[t] for t in todo if t in ok]  # 템플릿 차례로(끝난 차례가 아니라)
    got_bad = [f"{tag[t]}: {bad[t]}" for t in todo if t in bad]
    left = len(todo) - len(got_ok) - len(got_bad)
    msg = " · ".join(b for b in (f"계획 받음 {' · '.join(got_ok)}" if got_ok else "", f"실패 {' / '.join(got_bad)}" if got_bad else "",
                                 f"멈춤 — 남은 템플릿 {left}" if left else "") if b)
    if got_bad and not got_ok:
        part("failed", msg)
        raise Stop(f"서식 정리 계획을 하나도 받지 못함 — {got_bad[0]}")
    part("partial" if got_bad or left else "ok", msg + (" — 문서는 안 바뀜 · 반영은 헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」(템플릿 하나만은 템플릿 줄의 「계획대로 맞추기」)" if got_ok else ""))
