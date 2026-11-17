"""분석 상태(spec_작업 ② §20) — 문서마다 「분석이 어디까지 됐는지」 를 어느 TASK 에서나 같은 꼴로 센다: 기본 분석(헤딩 · 표 — 스크립트, 올리면 저절로) ·
LLM 판정(헤딩 · 표 — 사람이 단추로) · 구분 기준 LLM 검토(옵션 — 연구개발 문서만). 사용자 2026-11-15 "task 마다 작업을 표준화 … 올리면 어디까지 작업이 되었는지 표시".

읽기만 한다 — 분석을 시작하지 않고 결과·문서를 바꾸지 않는다. 헤딩·표는 헤딩 추출의 지금 결과(heading_runs.state — 2단계 헤딩 그래프 · 3단계 표 구조)와 도는 작업,
구분 기준은 세션의 마지막 LLM 검토(division.review · reviewing)를 본다. 화면 = 문서 이름 줄의 표시(app/static/doc_status.js), 끝점 = app/analysis_api.py.

- 상태: none 없음 · wait 대기(앞 항목이 도는 중) · running 도는 중 · done 됨 · failed 실패. 해당 없는 항목은 목록에 넣지 않는다(docx = 항목 없음 · base "na").
- 문서를 고친 뒤에도 done 이다(뼈대 유지 — spec_헤딩_추출 ② §17). moved = 그 결과를 뽑은 뒤 문서가 바뀜(도움말에만 쓴다).
- 넷 · 진행표(2026-11-16 — ② §20 「넷 · 진행표 · LLM 검증·보완」): 헤딩 · **템플릿** · **서식** · 표를 스크립트 · LLM 검증·보완 · 문서 반영 세 칸으로. 템플릿 · 서식은 개요 오버레이와
  서식 갈래(outline=(ov, variants) — analysis_api 가 server 에서 읽어 넘긴다)와 받은 서식 정리 계획(plans — tpl_agent_api)으로 센다. 「LLM 검증·보완」 의 실행은 app/analysis_llm.py."""
from app import heading_runs, outline_match, tpl_agent

STATES = ("none", "wait", "running", "done", "failed")
NAMES = {"heads": "헤딩", "templates": "템플릿", "formats": "서식", "tables": "표", "division": "구분 기준"}
PLAN_STATES = ("none", "planned", "applied", "stale")  # 템플릿마다 서식 정리 계획(② §20): 안 받음 · 받음(바로 적용 가능) · 적용함 · 받았지만 그 뒤 문서가 바뀜
STAGE = {"heads": ("stage2", 2, "헤딩 그래프"), "tables": ("stage3", 3, "표 구조")}
# 이어 돌리기(job.chain — app/analysis_llm.py CHAINS)의 화면 이름: llm = 진행표의 「LLM 검증·보완」(헤딩 · 표 판정 같이 → 서식) · heads = 「헤딩 그래프(LLM)」(헤딩 판정 → 서식 정리 계획:
# 2026-11-16 사용자 답 「헤딩 LLM 판정에 늘 이어서」) · formats = 서식 정리 계획만(헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」)
CHAIN_NAMES = {"llm": "LLM 검증·보완", "heads": "헤딩 LLM 판정 · 서식 계획", "formats": "서식 정리 계획"}
CHAIN_PARTS = {"llm": ("heads", "tables", "formats"), "heads": ("heads", "formats"), "formats": ("formats",)}


def _llm(res, running, failed=None, waiting=False):
    """그 결과의 LLM 판정 → {state, text, error} — 지금 결과가 LLM 을 거친 것인가(스크립트로 다시 돌려 덮었으면 none).
    failed = 방금 LLM 실행이 예외로 끝난 까닭(앞 결과는 그대로 남는다) — 지금 결과가 LLM 을 거친 것이 아니면 failed 로 보인다.
    waiting = LLM 검증·보완이 앞 일을 하는 중 — 이 항목의 LLM 은 그 뒤에 돈다(wait)."""
    if running:
        return {"state": "running", "text": "LLM 판정 중", "error": None}
    if waiting:
        return {"state": "wait", "text": "LLM 검증·보완 — 앞 일이 끝나면 돕니다", "error": None}
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


def _short(key, res):
    """진행표 칸의 짧은 글 — 「헤딩 146」 · 「표 17 · 칸 469」(결과가 없으면 빈 글)."""
    if res is None:
        return ""
    counts = res.get("counts") or {}
    return f"헤딩 {counts.get('nodes', 0)}" if key == "heads" else f"표 {counts.get('tables', 0)} · 칸 {counts.get('cells', 0)}"


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
    part = (chain_parts(job).get(key) or {}) if job is not None and job.chain else {}
    here = (part.get("status") == "failed" if job is not None and job.chain  # 이어 돌리기(LLM 검증·보완)는 그 단계의 상태로 가른다(헤딩 · 표 · 서식이 같이 돌 수 있다)
            else job is not None and job.stage == STAGE[key][1])
    # 같이 돈 단계가 둘 다 실패하면 작업 오류 글은 하나뿐이다(헤딩이 먼저) — 그 단계의 글이 있으면 그것을 보인다
    llm_failed = (part.get("msg") or job.error) if job is not None and job.status == "failed" and job.use_llm and not job.first and here else None
    chain = bool(job is not None and job.chain)
    if chain and res is not None:  # LLM 검증·보완은 결과가 있는 항목의 스크립트 칸을 건드리지 않는다 — 기다림은 LLM 칸에만
        state = "done"
    else:
        state = "running" if turn in ("run", "llm") and (res is None or turn == "run") else "wait" if turn == "wait" else "done" if res is not None else "failed" if failed else "none"
    out = {"key": key, "name": NAMES[key], "state": state, "run": meta.get("run"), "at": meta.get("at"), "moved": res is not None and meta.get("rev") != sess.rev,
           "text": _text(key, res), "short": _short(key, res), "error": job.error if failed else None, "llm": _llm(res, turn == "llm", llm_failed, waiting=chain and turn == "wait")}
    if key == "heads":
        out["rules"] = heading_runs.rules_view(st) if "runs" in st else None  # 못 맞춤·충돌 규칙 보강(LLM)을 마지막으로 한 실행 | None(spec_헤딩_추출 ② §7 「진행 줄」)
        # 미판정 = LLM 구간 검증(B)이 실패해 스크립트 초안으로 남은 노드 수 — LLM 판정은 「함」 이지만 다 본 것이 아니다: 「전체 실행」 은 이 수가 있으면 조정(반영)을 하지 않고 남긴다
        und = int(((res or {}).get("counts") or {}).get("undecided") or 0) if out["llm"]["state"] == "done" else 0
        out["undecided"] = und
        if und:
            out["llm"] = {**out["llm"], "text": out["llm"]["text"] + f" · 미판정 {und}(구간 검증 실패 — 스크립트 초안 그대로)"}
    if key == "tables":
        calc = ((res or {}).get("counts") or {}).get("calc") or {}
        out["calc"] = {"formulas": calc.get("formulas", 0), "ok": calc.get("ok", 0), "mismatch": calc.get("mismatch", 0)} if calc else None  # 검산(스크립트) — 진행표의 표 줄
    return out


def _turns(st, job):
    """도는 헤딩 작업 → {"heads": turn, "tables": turn}. 첫 분석은 2단계 → 3단계를 잇달아(있는 단계는 건너뜀 — heading_runs.run_first), 1단계 작업은 항목에 영향이 없다."""
    if job is None or job.status != "running":
        return {}
    if job.first:
        if st.get("stage2") is None:
            return {"heads": "run", **({"tables": "wait"} if st.get("stage3") is None else {})}
        return {"tables": "run"} if st.get("stage3") is None else {}
    if job.chain:  # LLM 검증·보완 — 헤딩(+템플릿)과 표 판정 호출이 같이, 헤딩이 끝나면 서식(app/analysis_llm.py) — 단계마다 제 상태로
        p = chain_parts(job)
        out = {k: ("llm" if x["status"] == "running" else "wait") for k, x in p.items() if x["status"] in ("running", "wait")}
        if out.get("heads") == "llm":
            out["templates"] = "llm"
        return out
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
    # 구분 기준 판독(스크립트 — 헤딩 추출 앞 · spec_구분_기준 ② §23): 읽어 둔 것만 보인다(상태 읽기는 세지 않는다 — astra · Fable 협의). state 는 LLM 검토의 뜻 그대로
    from app import division_scan_api as DSA
    scan = DSA.summary(DSA.last(sess), sess)
    if scan:
        c = scan["counts"]
        text = (f"구분 기준 판독(스크립트) — 라벨 문단 {c['labels']} · 표 안 기관·차년도 {c['tables']}표" + ("" if scan.get("fresh") else " · 문서가 바뀌어 다음 읽기에 다시 셈")
                + "\n" + text)
    return {"key": "division", "name": NAMES["division"], "optional": True, "state": state, "at": (r or {}).get("at"), "found": found, "applied": applied,
            "partial": state == "done" and bool(errors), "error": error if state == "done" else None, "text": text, "scan": scan}


# ---------------------------------------------------------------- 템플릿 · 서식(2026-11-16 — ② §20 「넷 · 진행표 · LLM 검증·보완」)

def need_templates(variants):
    """서식 갈래(outline_match.all_variants — {tpl: {레벨: variants}}) → 정리할 템플릿 id 목록: 갈래가 둘 이상이거나 대표가 없는 레벨이 있는 것
    (tpl_agent_api.plan 이 422 「정리할 것이 없습니다」 로 거절하지 않는 것과 같은 기준)."""
    return [str(tid) for tid, lvs in (variants or {}).items() if any(len(v.get("groups") or []) > 1 or v.get("repMissing") for v in lvs.values())]


def plan_applied(rec, ov):
    """그 계획의 반영이 **지금 문서에 남아 있나** — 반영할 때 개요 오버레이에 적어 둔 표(ov["agent"][템플릿] = 그 계획의 at — tpl_agent_api.applied)가 이 계획의 것인가.
    오버레이는 실행 취소 · 모두 되돌리기 · 확정 복원과 함께 되돌아가므로 반영을 되돌리면 표도 사라진다 — 기록의 applied 만 보면 되돌린 뒤에도 「반영함」 으로 남는다
    (2026-11-16 사용자 「완료되었다고 나오는데 실제는 잘못된거 같아」 — spec_hwpx_웹편집 ② §8-4 「반영함은 문서에 남아 있을 때만」)."""
    if not rec or not rec.get("applied") or not isinstance(ov, dict):
        return False
    mark = (ov.get("agent") or {}).get(str(rec.get("tpl")))
    return mark is not None and mark == rec.get("at")


def plan_state(rec, rev, ov=None, fp=None):
    """받은 서식 정리 계획 하나 → PLAN_STATES 가운데 하나. ov = 지금 개요 오버레이 · fp = 그 템플릿의 **지금 지문**(tpl_agent.fingerprint).
    계획은 문서 차례가 아니라 그 템플릿 줄의 지문에 묶인다(기록의 `fp` — spec_hwpx_웹편집 ② §8-4 「계획은 줄 지문에」): 지문이 같으면 planned — 문서의 다른 곳을 고쳤어도,
    **반영했다가 되돌려 처음 상태로 돌아왔어도**(기록에 applied 가 있고 오버레이 표는 없다) 그 계획을 그대로 쓴다. 지문이 다르면(그 템플릿의 줄이 바뀜) stale.
    지문이 없는 옛 기록은 전처럼 rev(지금 문서 차례)로 — 반영한 적 있으면 stale."""
    if not rec:
        return "none"
    if plan_applied(rec, ov):
        # 갈래가 많아 일부만 본 계획(plan.omitted — tpl_agent.GROUP_MAX 를 넘는 갈래는 보내지 않는다)은 반영해도 못 본 갈래가 남는다 — 「반영함」 으로 닫지 않고 다시 받을 계획으로
        # (2026-11-16 astra: 미검토를 완료로 보이지 않는다 — spec_hwpx_웹편집 ② §8-4 「계획 검사」)
        return "stale" if ((rec.get("plan") or {}).get("omitted") or 0) > 0 else "applied"
    if rec.get("fp"):
        state = "planned" if fp and rec["fp"] == fp else "stale"
    else:
        state = "planned" if rec.get("rev") == rev and not rec.get("applied") else "stale"
    plan = rec.get("plan") or {}
    if state == "planned" and (plan.get("omitted") or 0) > 0 and not (plan.get("change") or plan.get("moved") or tpl_agent.todo(plan)["reps"]):
        return "stale"  # 바꿀 줄도 바꿀 대표도 없는데 못 본 갈래가 남은 계획 — 반영할 것이 없으니 바로 다음 갈래를 받을 계획이다(보낸 갈래는 기록에 남아 다음 자료에서 뒤로 돈다)
    return state


def plan_left(plan, lvs):
    """반영한 계획이 **지금 문서에 남긴 줄** → {"kept": 에이전트가 「그대로」 로 답한 갈래의 줄, "unanswered": 답이 말하지 않아 안 바꾼 갈래의 줄(검토한 것이 아니다)}.
    계획의 keep 갈래 가운데 **지금도 그 레벨에 대표와 다른 갈래로 남아 있는 것**만 지금 줄 수로 센다 — 반영 뒤 사람이 그 갈래를 맞췄거나 뗐거나 대표로 삼았으면 빠진다.
    갈래는 **지문**(tpl_agent.group_sig — 레벨 + 비교 값)으로 찾는다: 그 서식의 갈래가 지금도 대표와 다른 갈래로 있으면 그 줄 수, 없으면 0(그 서식의 줄이 남지 않았다).
    열쇠 줄이 바뀌어도(열쇠 줄만 대표에 맞춤) 서식이 같은 나머지 줄은 센다. lvs = 그 템플릿의 {레벨: outline_match.variants}.
    지문이 없는 옛 계획의 항목은 열쇠 줄이 든 「대표와 다른 갈래」 로 찾고, **못 찾았다고 해결된 것으로 보지 않는다**(열쇠 줄만 맞췄을 수 있다 — 2026-11-17 astra): 아직 어느 항목에도 안 붙은
    대표와 다른 줄이 남아 있는 만큼은 남은 것으로 세고(답 없는 쪽부터 — 그 줄이 하나도 없을 때만 해결된 것이 지금 갈래로 증명된다), 그 수를 넘겨 세지는 않는다.
    「받음」 인 계획에서만 세면 반영한 뒤 이 수가 사라져, 답이 없던 줄이 「끝남」 으로 보인다(2026-11-16 astra — spec_hwpx_웹편집 ② §8-4)."""
    out = {"kept": 0, "unanswered": 0}
    for L in (plan or {}).get("levels") or []:
        v = (lvs or {}).get(str(L.get("level"))) or (lvs or {}).get(L.get("level")) or {}
        rest = [g for g in v.get("groups") or [] if not g.get("rep")]  # 지금 대표와 다른 갈래 가운데 아직 어느 keep 항목에도 안 붙은 것
        lost = []  # 지문이 없고 열쇠 줄도 못 찾은 항목 [(kept | unanswered, 계획 때의 줄 수)]
        for k in L.get("keep") or []:
            who = "unanswered" if k.get("auto") else "kept"
            if k.get("sig"):
                g = next((g for g in rest if isinstance(g.get("raw"), dict) and tpl_agent.group_sig(L["level"], g["raw"]) == k["sig"]), None)
            else:
                g = next((g for g in rest if k.get("para") and (g.get("key") == k["para"] or k["para"] in (g.get("paras") or ()))), None)
                if g is None:
                    lost.append((who, int(k.get("count") or 0)))
            if g is not None:
                out[who] += int(g.get("count") or 0)
                rest = [x for x in rest if x is not g]
        pool = sum(int(g.get("count") or 0) for g in rest)
        for who, n in sorted(lost, key=lambda x: x[0] != "unanswered"):
            take = min(n, pool)
            out[who] += take
            pool -= take
    return out


def _others(v):
    """레벨 하나에서 대표와 다른 줄 수 — 대표가 없으면 가장 많은 갈래를 대표로 보고 센다."""
    if v.get("rep"):
        return int(v.get("others") or 0)
    counts = [g.get("count", 0) for g in v.get("groups") or []]
    return sum(counts) - max(counts) if counts else 0


def _tpl_rows(ov):
    """개요 오버레이 → 줄이 있는 템플릿 [{id, no, chain, lines}] — 번호 차례."""
    lines = {}
    for x in (ov.get("lines") or {}).values():
        lines[str(x.get("tpl"))] = lines.get(str(x.get("tpl")), 0) + 1
    rows = [{"id": str(tid), "no": str(t.get("no", tid)), "chain": " › ".join(str(c) for c in (t.get("chain") or [])), "lines": lines.get(str(tid), 0)}
            for tid, t in (ov.get("templates") or {}).items() if lines.get(str(tid))]

    def order(r):
        head = ""
        for ch in r["no"]:  # 「1」 · 「1L3a」 — 앞 숫자로, 같으면 글 차례
            if not ch.isdigit():
                break
            head += ch
        return (int(head) if head else 1 << 30, r["no"])
    return sorted(rows, key=order)


def _templates_item(heads, ov):
    """템플릿 — 스크립트 칸은 헤딩 그래프(2단계)가 세운 템플릿, LLM 칸은 같은 「헤딩 그래프(LLM)」 의 구간 그래프 검토(B) — 헤딩과 한 실행이라 같은 상태."""
    rows = _tpl_rows(ov) if ov else []
    llm = dict(heads["llm"])
    if llm["state"] == "done":
        llm["text"] = "헤딩 그래프(LLM)의 구간 검토를 거침"
    elif llm["state"] == "none":
        llm["text"] = "LLM 검토 안 함 — 헤딩 그래프(LLM)이 함께 봅니다"
    text = (" · ".join(f"T{r['no']} {r['chain']}".strip() for r in rows) if rows else "템플릿 없음") if heads["state"] == "done" else ""
    # hints = 종속 제안(한 자리에만 매달린 가지 템플릿 → 그 자리의 템플릿 아래로 — outline_match.merge_hints): 확실한 것(sure)은 「모두 반영」·「전체 실행」 이 저절로 넣고 애매한 것은 제안만. 조정 층 「템플릿 조정」 칸 · 결과 화면이 보인다
    hints = outline_match.merge_hints(ov) if ov and heads["state"] == "done" else []
    return {"key": "templates", "name": NAMES["templates"], "state": heads["state"], "count": len(rows), "list": rows, "text": text, "llm": llm, "hints": hints}


def _formats_item(heads, ov, variants, plans, rev, job, place=0):
    """서식 — 스크립트 칸 = 템플릿 레벨마다 서식 갈래 · LLM 칸 = 템플릿 서식 정리 계획(정리할 템플릿마다) · 반영 칸 = 맞춘 레벨(갈래 하나뿐이고 대표가 있음) · 대표와 다른 줄.
    place = 확정 서식(레터 뒤 묶음 빈칸 · 자리 규칙 — spec_hwpx_웹편집 ② §8-8)이 아직 안 걸린 줄 수(대표와 그 갈래의 줄 — 조정 줄의 「모두 반영」 이 스크립트로 건다).
    LLM 칸의 수: change · moved · **reps**(대표를 바꿀 레벨 — 맞출 줄이 0 이어도 반영할 것이다) = 받아 둔 계획을 반영하면 바뀔 것 · kept · unanswered · omitted = 그 계획을 반영해도 남을 것 ·
    **left**{kept, unanswered} = **반영한** 계획이 지금 문서에 남긴 줄(plan_left — 반영한 뒤에도 센다: 답이 없던 줄을 「끝남」 으로 보이지 않게) ·
    left.marked(있을 때만) = 반영이 형광펜 · 필드 · 변경 추적 표지 때문에 모양만 맞추고 남긴 줄(오버레이 agentLeft) 가운데 지금도 대표와 다른 서식인 줄 · leftMarked = 그 줄 id(30개까지).
    계획 상태는 그 줄 때문에 바뀌지 않는다(「반영함」 그대로 — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」)."""
    names = {r["id"]: r["no"] for r in _tpl_rows(ov)} if ov else {}
    slots = []
    for tid, lvs in (variants or {}).items():
        for lv, v in sorted(lvs.items(), key=lambda kv: int(kv[0])):
            slots.append({"tpl": str(tid), "no": names.get(str(tid), str(tid)), "level": int(lv), "groups": len(v.get("groups") or []), "others": _others(v), "total": v.get("total", 0),
                          "values": v.get("values", 0),  # values = 값 칸(표 칸에 혼자 있는 레터 — 갈래에 안 넣고 안 맞춘다: outline_match.lone_value)
                          "repMissing": bool(v.get("repMissing"))})  # 대표가 없는 레벨 — 갈래가 하나여도 맞춘 레벨이 아니다(자리 맞춤도 새 줄의 서식도 대표에서 나온다)
    levels, aligned = len(slots), sum(1 for x in slots if x["groups"] <= 1 and not x["repMissing"])
    norep = sum(1 for x in slots if x["repMissing"])
    groups, others = sum(x["groups"] for x in slots), sum(x["others"] for x in slots)
    need = need_templates(variants)

    def marked_left():
        """반영한 계획(plan_applied)이 표지 때문에 모양만 맞추고 남긴 줄(오버레이 agentLeft — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」) 가운데 **지금도 대표와 다른 서식**에 있는 줄
        → {템플릿 id: [줄 id]}. 줄은 지금 서식 목록(모든 템플릿 · 레벨의 대표가 아닌 갈래의 paras · key)에서 찾는다 — 떼기로 다른 템플릿에 간 줄도. 그 뒤 사람이 맞췄거나 대표로 삼은 줄은 빠진다."""
        box = ov.get("agentLeft") if isinstance(ov, dict) else None
        if not isinstance(box, dict) or not box:
            return {}
        off = set()
        for lvs in (variants or {}).values():
            for v in lvs.values():
                for g in v.get("groups") or []:
                    if not g.get("rep"):
                        off.update(g.get("paras") or ())
                        off.add(g.get("key"))
        got = {}
        for tid, rows in box.items():
            if plan_applied((plans or {}).get(str(tid)), ov):
                ids = list(dict.fromkeys(x.get("id") for x in rows or () if isinstance(x, dict) and x.get("id") in off))
                if ids:
                    got[str(tid)] = ids
        return got
    marked = marked_left()
    plist = []
    for tid in need:
        rec = (plans or {}).get(tid)
        row = {"tpl": tid, "no": names.get(tid, tid), "state": plan_state(rec, rev, ov, tpl_agent.fingerprint(ov, tid, (variants or {}).get(tid)) if rec and rec.get("fp") else None)}
        if rec and isinstance(rec.get("plan"), dict) and rec["plan"].get("omitted"):
            row["omitted"] = rec["plan"]["omitted"]  # 못 본 갈래가 남은 계획(반영했어도) — 「전체 실행」 이 다음 갈래를 받으러 다시 부른다
        if row["state"] == "planned" and isinstance(rec.get("plan"), dict):  # 지금 반영할 수 있는 계획 — 에이전트가 고른 그대로 반영하면 바뀔 줄 · 다른 템플릿으로 옮길 줄(진행 줄 「조정」 의 두 칸 · 「모두 반영」 의 수)
            t = tpl_agent.todo(rec["plan"])
            left = rec["plan"].get("left") or {}
            # at = 그 계획의 표시(「모두 반영」 이 화면이 본 계획 그대로인지 서버가 견준다) · reps = 대표를 바꿀 레벨 · kept/unanswered/omitted = 반영해도 남는 것(에이전트가 그대로 둔 줄 · 답이 없던 줄 · 못 본 갈래)
            row.update(change=t["n"], moved=t["moved"], reps=t["reps"], at=rec.get("at"), kept=left.get("kept", 0), unanswered=left.get("unanswered", 0), omitted=rec["plan"].get("omitted", 0))
        elif rec and isinstance(rec.get("plan"), dict) and plan_applied(rec, ov):  # 반영한 계획 — 그 계획이 지금 문서에 남긴 줄(그대로 둔 줄 · 답이 없던 줄)을 지금 갈래로 다시 센다
            row["left"] = plan_left(rec["plan"], (variants or {}).get(tid))
            if marked.get(tid):  # 표지 때문에 모양만 맞춘 줄 가운데 지금도 대표와 다른 서식인 줄(있을 때만 — 없으면 키를 안 둔다)
                row["left"]["marked"] = len(marked[tid])
        plist.append(row)
    planned = sum(1 for x in plist if x["state"] == "planned")
    applied = sum(1 for x in plist if x["state"] == "applied")
    stale = sum(1 for x in plist if x["state"] == "stale")
    left = {k: sum((x.get("left") or {}).get(k, 0) for x in plist) for k in ("kept", "unanswered")}  # 반영한 계획들이 지금 문서에 남긴 줄
    mk = list(dict.fromkeys(i for ids in marked.values() for i in ids))  # 반영한 계획들이 표지 때문에 모양만 맞추고 남긴 줄(모든 템플릿 — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」)
    if mk:
        left["marked"] = len(mk)
    part = (chain_parts(job).get("formats") or {}) if job is not None and job.chain else {}
    chain = bool(job is not None and job.chain and job.status == "running")
    running = chain and part.get("status") == "running"
    failed = bool(job is not None and job.chain and job.status == "failed" and part.get("status") == "failed")
    ready = heads["state"] == "done" and ov is not None
    if not ready:
        llm = {"state": "wait" if chain else "none", "text": "헤딩 그래프가 있어야 셉니다", "error": None}
    elif running:
        llm = {"state": "running", "text": f"서식 정리 계획을 받는 중 — {part['msg']}" if part.get("msg") else "서식 정리 계획을 받는 중", "error": None}
    elif chain and part.get("status") == "wait":
        llm = {"state": "wait", "text": ("LLM 검증·보완 — 헤딩 · 템플릿이 끝나면 서식 정리 계획을 받습니다(템플릿끼리 같이)" if job.chain == "llm"
                                         else "헤딩 판정이 끝나면 이어서 서식 정리 계획을 받습니다"), "error": None}
    elif not need:
        llm = {"state": "done", "text": "정리할 것 없음 — 레벨마다 서식이 한 가지", "error": None}
    else:
        got = planned + applied
        bits = [f"받음 {planned}" if planned else "", f"적용함 {applied}" if applied else "", f"옛 계획 {stale}" if stale else "",
                f"반영한 계획이 그대로 둔 줄 {left['kept']}" if left["kept"] else "", f"답이 없어 안 바꾼 줄 {left['unanswered']}" if left["unanswered"] else "",
                f"표지 때문에 모양만 맞춘 줄 {len(mk)}" if mk else ""]
        state = "done" if got == len(need) else "failed" if failed and not got else "partial" if got else "none"
        text = (f"서식 정리 계획 {got}/{len(need)} 템플릿" + (" — " + " · ".join(b for b in bits if b) if any(bits) else "")) if state != "none"             else f"서식 정리 계획 안 받음 — 정리할 템플릿 {len(need)}" + (f" · 옛 계획 {stale}" if stale else "")
        llm = {"state": state, "text": text, "error": (part.get("msg") or job.error) if failed else None}  # 같이 돈 표도 실패했으면 작업 오류는 표의 것 — 서식은 제 단계 글
    done = sum(1 for r in (plans or {}).values() if plan_applied(r, ov))  # 이 헤딩 그래프에서 반영한 계획 수(모든 템플릿 — 다 맞춰 「정리할 템플릿」 에서 빠진 것도: 진행 줄 「조정」 의 ✓) — 반영을 되돌린 계획은 안 센다
    llm.update({"need": len(need), "planned": planned, "applied": applied, "stale": stale, "done": done, "change": sum(x.get("change", 0) for x in plist), "moved": sum(x.get("moved", 0) for x in plist),
                "reps": sum(x.get("reps", 0) for x in plist),  # 받아 둔 계획이 대표를 바꿀 레벨 수 — 「맞출 줄 0 · 대표 변경 1」 도 반영할 것이 있다(조정 줄 · 「전체 실행」)
                "kept": sum(x.get("kept", 0) for x in plist), "unanswered": sum(x.get("unanswered", 0) for x in plist), "omitted": sum(x.get("omitted", 0) for x in plist),
                "left": left, "list": plist,
                "leftMarked": mk[:30]})  # 그 줄 id(30개까지) — 조정 줄의 「서식 조정 · 표지 n줄」 을 누르면 차례로 간다
    place = place if ready else 0
    apply = {"state": "done" if aligned == levels and not place else "none",
             "text": f"맞춘 레벨 {aligned}/{levels}" + (f" · 대표와 다른 줄 {others}" if others else "") + (f" · 자리 안 맞은 줄 {place}" if place else "")
             + (f" · 대표 없는 레벨 {norep}" if norep else "")} if ready         else {"state": "none", "text": ""}
    return {"key": "formats", "name": NAMES["formats"], "state": heads["state"] if ov is not None or heads["state"] != "done" else "none",
            "levels": levels, "aligned": aligned, "noRep": norep, "groups": groups, "others": others, "slots": slots, "place": place,
            "text": f"레벨 {levels} · 서식 {groups}가지" if ready else "", "llm": llm, "apply": apply}


def part_nos(parts, heads_run):
    """이어 돌리기 단계의 차례 번호 {key: no} — **같은 번호는 같이 돈다**(도는 단계끼리 1부터). parts = 그 이어 돌리기의 단계 · heads_run = 헤딩 판정이 실제로 도나.
    헤딩 판정이 돌면 표 판정의 호출이 그것과 같이 돈다(헤딩 1 · 표 1 · 서식 2 — 표 판정 호출은 1단계에만 기댄다: heading_runs.TablesAhead · 서식 계획은 헤딩 그래프가 끝나야 한다),
    헤딩 판정을 건너뛰면 표 · 서식이 같이(헤딩 1 · 표 2 · 서식 2). 실행(app/analysis_llm.run)과 「돌 것」(llm_plan)이 같이 쓴다."""
    raw = {"heads": 1, "tables": 1 if heads_run and "heads" in parts else 2, "formats": 2}
    nos = sorted({raw[k] for k in parts})
    return {k: nos.index(raw[k]) + 1 for k in parts}


def llm_plan(items, need_plans):
    """지금 「LLM 검증·보완」 을 누르면 돌 것 → [{key, no, name, run, why}] — app/analysis_llm.py 가 실행 때 쓰는 기준과 같다(건너뜀은 run False + why · no 가 같으면 같이 돎 — part_nos).
    need_plans = 정리할 템플릿 가운데 계획이 없거나 옛것인 수."""
    by = {i["key"]: i for i in items}
    heads, tables = by.get("heads"), by.get("tables")
    if heads is None or tables is None:
        return []
    h_run = heads["llm"]["state"] != "done"
    t_run = h_run or tables["llm"]["state"] != "done"
    f_need = by["formats"]["llm"].get("need", 0) if "formats" in by else 0
    f_run = h_run or need_plans > 0
    nos = part_nos(("heads", "tables", "formats"), h_run)
    both = " — 서식과 같이" if t_run and f_run and not h_run else ""  # 같이 도는 것이 실제로 있을 때만 적는다(헤딩이 돌면 표는 헤딩과 같이)
    many = " · 템플릿끼리도 같이" if h_run or need_plans > 1 else ""
    return [
        {"key": "heads", "no": nos["heads"], "name": "헤딩 · 템플릿 — 헤딩 그래프(LLM)", "run": h_run,
         "why": "못 맞춤·충돌 규칙 보강 → 유형 판정 · 구간 검토 — 규칙 보강이 끝나면 표 판정 호출이 같이 돕니다(서식 계획은 이 결과가 나온 뒤)" if h_run else "지금 결과가 이미 LLM 판정을 거쳤습니다 — 건너뜀"},
        {"key": "tables", "no": nos["tables"], "name": "표 — 표 구조(LLM)", "run": t_run,
         "why": (("헤딩 그래프를 다시 지으므로 표 구조도 다시" if tables["llm"]["state"] == "done" else "칸 역할 · 서브 테이블 판정")
                 + " — 호출은 헤딩 판정과 같이(규칙 보강 뒤 바로) · 소속은 헤딩 그래프가 끝난 뒤 붙임" if h_run else "칸 역할 · 서브 테이블 판정" + both) if t_run
         else "지금 결과가 이미 LLM 판정을 거쳤습니다 — 건너뜀"},
        {"key": "formats", "no": nos["formats"], "name": "서식 — 템플릿 서식 정리 계획", "run": f_run,
         "why": ("헤딩 그래프를 다시 지은 뒤 서식이 두 가지 이상인 템플릿마다 계획만(문서는 안 바뀜)" if h_run
                 else f"정리할 템플릿 {need_plans}개 — 계획만(문서는 안 바뀜)" if need_plans
                 else "정리할 것 없음 — 건너뜀" if not f_need else "모든 템플릿의 계획을 받았습니다 — 건너뜀") + ((" — 표와 같이" if t_run and not h_run else "") + many if f_run else "")},
    ]  # no = 차례 번호 — 같은 번호는 같이 돈다(part_nos — app/analysis_llm.run 과 같음)


def chain_parts(job):
    """LLM 검증·보완의 단계 {key: {key, name, no, status, msg}} — 단계가 아직 적히지 않았으면(막 시작) 헤딩이 도는 것으로(app/analysis_llm.run 이 곧 적는다)."""
    with job.lock:
        got = {x["key"]: dict(x) for x in getattr(job, "parts", None) or []}
    if got:
        return got
    keys = CHAIN_PARTS.get(job.chain) or CHAIN_PARTS["llm"]  # 그 이어 돌리기가 도는 단계만(「헤딩 그래프(LLM)」 = 헤딩 · 서식 — 표는 없다)
    return {k: {"key": k, "status": "running" if i == 0 else "wait", "msg": ""} for i, k in enumerate(keys)}


def _chain_view(job):
    """도는(또는 막 끝난) LLM 검증·보완의 차례 — {steps[{key, name, no, status, msg}], running[지금 도는 key — 표 · 서식은 같이], at(그 첫째 · 옛 이름), stopping, status} | None.
    no = 차례 번호(같은 번호 = 같이 돎)."""
    if job is None or not job.chain:
        return None
    with job.lock:
        parts = [dict(x) for x in getattr(job, "parts", None) or []]
    running = [x["key"] for x in parts if x["status"] == "running"]
    return {"steps": parts, "running": running, "at": running[0] if running else job.phase, "stopping": bool(job.stop), "status": job.status,
            "chain": job.chain, "name": CHAIN_NAMES.get(job.chain, CHAIN_NAMES["llm"])}


def _base(items):
    states = [i["state"] for i in items if i["key"] in STAGE]
    if not states:
        return "na"
    return ("running" if any(s in ("running", "wait") for s in states) else "done" if all(s == "done" for s in states)
            else "failed" if "failed" in states else "none")


def status(sess, kind="", division=False, outline=None, plans=None, place=0):
    """→ {rev, format, kind, base, busy, job, chain, llmPlan, items[…]} — spec_작업 ② §20. busy = 헤딩 작업이 하나라도 도는 중(1단계 포함 — 그동안은 새 분석을 못 건다). kind = 작업에 적힌 작업 종류(화면이 구분 기준 항목을 보일지 정한다), division = 이 문서에 구분 기준 항목이 있는가(hwpx · 지원 양식).
    outline = (개요 오버레이, 서식 갈래) | None(2단계 결과 없음) · plans = 지금 헤딩 그래프의 받은 서식 정리 계획 {tpl: 기록}. items 차례 = 헤딩 · 템플릿 · 서식 · 표(· 구분 기준)."""
    out = {"rev": sess.rev, "format": sess.fmt, "kind": kind or "", "base": "na", "busy": False, "job": None, "chain": None, "llmPlan": [], "items": []}
    if sess.fmt != "hwpx":   # 헤딩 추출은 hwpx 만 — 항목 없음
        return out
    st = heading_runs.state(sess)
    job = st.get("job")
    turns = _turns(st, job)
    heads, tables = (_item(key, st, sess, job, turns.get(key)) for key in ("heads", "tables"))
    ov, variants = outline if outline else (None, None)
    formats = _formats_item(heads, ov, variants, plans, sess.rev, job, place)
    out["items"] = [heads, _templates_item(heads, ov), formats, tables]
    need_plans = sum(1 for x in formats["llm"]["list"] if x["state"] in ("none", "stale"))
    out["llmPlan"] = llm_plan(out["items"], need_plans)
    out["chain"] = _chain_view(job)
    if division:
        out["items"].append(_division(sess))
    out["base"] = _base(out["items"])
    out["busy"] = job is not None and job.status == "running"
    if job is not None and (job.status == "running" or job.status == "failed"):
        v = job.view()
        what = "첫 분석" if job.first else CHAIN_NAMES.get(job.chain, CHAIN_NAMES["llm"]) if job.chain else f"{job.stage}단계" + (" · LLM" if job.use_llm else "")
        out["job"] = {"first": job.first, "chain": job.chain, "stage": job.stage, "llm": job.use_llm, "status": job.status, "what": what, "started": v["started"], "error": v["error"]}
    return out
