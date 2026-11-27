"""양식 검토 끝점(spec_양식작성 ② §5-1) — 프롬프트 · 답 검증은 `app/form_review.py`(순수), 자리 목록은 지침 작성의 것(`guide_write_api._places`). hwpx 문서만 · 어느 워크플로우에서나.
문서를 바꾸지 않는다. 지침 작성의 「작성 초안 받기」 는 검토 · 작성 계획이 있을 때만 돈다(`gate` — guide_write_api 가 부른다) · 답하지 않은 물음은 그 물음이 닿는 자리만 막는다(`held` — ② §5-12 6).

- `GET /api/docs/{id}/form-review` → {hwpx, enabled(LLM), review | null, decided[{key, q, a, places, at}], open[아직 답 안 한 물음 key], stale(검토 뒤 자리 · 지침이 바뀜), run | null}.
- `POST /api/docs/{id}/form-review` {materials: [자료 id…], note, planNote?(작성 계획에 줄 요청 — 자료가 있을 때만 씀)} →배경에서 한 번(유료 LLM — 기본 LLM1 한 번 · `duo`(두 모델로 협의 — 옵션: ② §5-12 1)를 켠 실행은 모델마다 한 번 + 둘 이상 답하면 협의 한 번: `_ask`) → {run}. materials 가 비면 **양식 검토**(양식 · 작성 지침 · 사람의 요청 note 만 — 자료는 안 읽음),
  있으면 **작성 계획**(양식 검토가 먼저 — 없으면 409 · 양식이 그대로면 검토의 요약 · 작성 방향 · 테마는 그대로 두고 자리마다 use · gap 과 물음만 받는다). 409 = 도는 중 · 503 = LLM 없음.
- `PUT /api/docs/{id}/form-review/answers` {answers: [{key?, q?, a}]} → 정한 것을 고친다(key = 검토의 물음 · 없으면 q 로 새 줄 · a 가 빈 글이면 그 줄을 지움) → 보기.
저장 = 작업 폴더 `form_review.json` {review, decided} — 다시 검토해도 정한 것(decided)은 버리지 않는다(같은 물음은 다시 묻지 않는다 · 검토 실패는 앞 검토를 지우지 않는다).
작업 저장이 꺼진 문서는 이 프로세스의 메모리에 둔다. 끝나면 작업 기록에 `formReview` 한 줄."""
import threading
import time

from fastapi import APIRouter, Body, HTTPException

from app import agent_notes, agent_settings, doc_agent, form_review, job_prompts, llm, llm_duo, material_index, merge_guides, works

router = APIRouter()
FILE = "form_review.json"
_MEM = {}             # 작업 저장이 꺼진 문서 — 작업 id → {review, decided}
_RUNS = {}            # 작업 id → {state, at, ended, error, materials}
_LOCK = threading.Lock()
DECIDED_MAX = 40


def _sess(doc_id):
    from app import server
    return server._sess(doc_id)


def _path(wid):
    f = works.folder(wid)
    return f / FILE if f is not None and (f / "work.json").is_file() else None


def load(wid):
    """{review | None, decided[]} — 읽는 기능(지침 작성 · 화면)은 이것으로 읽는다."""
    p = _path(wid)
    got = works._read_json(p) if p is not None and p.is_file() else _MEM.get(wid)
    got = got if isinstance(got, dict) else {}
    rv = got.get("review") if isinstance(got.get("review"), dict) else None
    dec = [d for d in got.get("decided") or () if isinstance(d, dict) and isinstance(d.get("q"), str) and isinstance(d.get("a"), str)]
    opts = got.get("opts") if isinstance(got.get("opts"), dict) else {}
    return {"review": rv, "decided": dec, "opts": {"duo": opts.get("duo") is True}}   # opts.duo = 두 모델로 협의(옵션 — 기본 한 모델: spec_양식작성 ② §5-12 1)


def _save(wid, data):
    if "opts" not in data:   # 검토 · 답을 쓰는 길은 옵션을 모른다 — 있던 것을 지닌다
        data = {**data, "opts": load(wid)["opts"]}
    p = _path(wid)
    if p is not None:
        works._write_json(p, data)
    else:
        _MEM[wid] = data


def unplan(wid):
    """작성 계획만 비운다(양식 작성의 「작성 초기화」 — spec_양식작성 ② §6-1) → 비웠나. 양식 검토(요약 · 자리마다 how · needs · 찾을 테마 · 물음)와 사람이 정한 답은 남긴다 —
    자료로 세운 것(자리마다 use · gap · 계획 때의 자료)만 지워 「작성 계획 세우기」 를 다시 하게 한다."""
    st = load(wid)
    rv = st["review"]
    if not form_review.planned(rv):
        return False
    ps = rv.get("places")
    wipe = lambda p: {**{k: v for k, v in p.items() if k != "evidence"}, "use": "", "gap": ""} if isinstance(p, dict) else p  # noqa: E731 — 근거 절(evidence)도 자료로 세운 것
    ps = {k: wipe(p) for k, p in ps.items()} if isinstance(ps, dict) else [wipe(p) for p in ps or ()]
    # 작성 계획이 뽑은 테마 · 자료 지문 · **자료를 읽고 낸 물음**(kind content)도 함께 비운다 — 남기면 자료가 없는 검토의 물음으로 읽혀, 거기 한 답이 자료에 묶이지 않는 답으로 저장된다(astra R2). 범위 물음 · 갈래를 모르는 옛 물음은 남긴다
    qs = [q for q in rv.get("questions") or () if not (isinstance(q, dict) and q.get("kind") == "content")]
    _save(wid, {"review": {**{k: v for k, v in rv.items() if k not in ("planTopics", "matSigs", "secVer")}, "places": ps, "materials": [], "questions": qs}, "decided": st["decided"]})
    return True


def gate(wid):
    """지침 작성을 돌려도 되나 → (된다?, 까닭, 저장본). 양식 검토가 없거나 · 자료로 세운 작성 계획이 없으면 안 된다(검토 → 계획 → 묻기 → 쓰기).
    답하지 않은 물음은 여기서 막지 않는다 — **그 물음이 닿는 자리만** 막는다(`held` — 2026-11-27 astra: 한 자리의 물음 하나가 모든 자리의 초안을 막았다 · spec_양식작성 ② §5-12 6)."""
    st = load(wid)
    if st["review"] is None:
        return False, "먼저 「양식 검토」 를 하세요 — 양식 전체를 읽고 어떻게 쓸지 · 정해 줄 것을 정리합니다", st
    if not form_review.planned(st["review"]):
        return False, "자료를 고르고 「작성 계획 세우기」 를 하세요 — 자료로 자리마다 무엇을 쓸지 계획하고 확인할 것을 묻습니다", st
    return True, "", st


def held(st, place_ids):
    """답하지 않은 물음이 막는 자리 {자리 id: [물음 글…]} — 문서 전체에 닿는 물음(자리를 안 적음)은 모든 자리 · 자리를 적은 물음은 그 자리만 · 자리를 잃은 물음(unplaced)은 어느 자리도 막지 않는다(화면이 따로 알린다)."""
    out = {}
    for q in form_review.open_questions(st["review"], st["decided"]):
        if q.get("unplaced"):
            continue
        for pid in (q.get("places") or place_ids):
            if pid in set(place_ids):
                out.setdefault(pid, []).append(q["text"])
    return out


def fresh(st, todo, mids):
    """초안을 받아도 되는가 — 저장한 검토(gate 가 준 st)와 이번 실행을 견준다 → 안 되는 까닭 | "". ⓐ 계획을 세운 자료와 이번에 쓸 자료가 다르다(자료 id 모음 — 차례는 안 본다)
    ⓑ 고른 자리 가운데 검토에 없거나 검토한 뒤 바뀐 자리가 있다(자리마다의 지문 `form_review.sigs` — 옛 검토(지문 없음)는 자리 id 만 본다). 무관한 자리가 바뀐 것은 막지 않는다(stale 로 알릴 뿐)."""
    rv = st["review"] or {}
    if set(rv.get("materials") or ()) != set(mids or ()):
        return "작성 계획을 세운 자료와 고른 자료가 다릅니다 — 양식에 넣을 내용의 자료를 계획 때와 같게 고르거나 「작성 계획 세우기」 를 다시 하세요"
    sigs = rv.get("sigs")
    known = sigs if sigs is not None else rv.get("places") or {}   # 검토한 때 있던 자리 = 지문을 적어 둔 자리(LLM 이 작성 방향을 안 낸 자리도 검토한 자리다 — rv.places 로 보면 그 자리는 다시 검토해도 영영 막힌다) · 옛 검토(지문 없음)만 rv.places
    bad = [p for p in todo if p["id"] not in known or (sigs is not None and sigs.get(p["id"]) != form_review.place_sig(p))
           or (sigs is None and p.get("writingGuidanceSig"))]
    if bad:
        names = " · ".join(f"「{(p.get('text') or p['id'])[:20]}」" for p in bad[:3])
        return f"양식 검토 뒤에 생기거나 바뀐 자리 {len(bad)}곳({names}{' …' if len(bad) > 3 else ''}) — 「다시 검토」 로 작성 계획을 다시 세우세요(정한 답은 남습니다)"
    return ""


def _view(s, places=None):
    st = load(s.id)
    rv = st["review"]
    if places is None and rv is not None:
        from app import guide_write_api
        places, _ = guide_write_api._places(s)
    with _LOCK:
        run = dict(_RUNS[s.id]) if s.id in _RUNS else None
    ids = [p["id"] for p in places] if places is not None else None
    left = form_review.open_questions(rv, st["decided"])
    prev = {q["key"]: d["a"] for q in left for d in [form_review.prev_answer(q, st["decided"], set(ids) if ids is not None else None)] if d}   # 답 안 한 물음의 「이전 답」(다른 자료로 물었을 때 · 다른 자리에서 한 답 — 후보로만: ② §5-12 6)
    return {"hwpx": True, "enabled": bool(llm.status()["available"]), "review": rv, "planned": form_review.planned(rv), "decided": st["decided"],
            "opts": st["opts"], "llm2": len(agent_settings.models("form_review", form_review.LLMS)) > 1,   # 두 모델 협의(옵션) · 둘째 모델이 설정에 있나
            "prev": prev, "held": held(st, ids) if rv is not None and ids is not None else {},               # 답하지 않은 물음이 막는 자리 {자리 id: [물음 글]}
            "open": [q["key"] for q in form_review.open_questions(rv, st["decided"])], "stale": bool(rv and places is not None and rv.get("sig") != form_review.sig(places)), "run": run,
            "lost": [d["q"] for d in form_review.lost(rv, st["decided"], ids)] if ids is not None else [],   # 자리를 잃은 답(어느 자리에도 싣지 않는다 — 화면이 알린다)
            "topicLines": [form_review.scope_line(t) for t in (rv or {}).get("topics") or ()],   # 테마마다 「뽑을 범위」 에 붙일 한 줄(앞말 없이 — 화면이 앞말을 붙인다)
            "planTopicLines": [form_review.scope_line(t) for t in (rv or {}).get("planTopics") or ()]}   # 작성 계획이 뽑은 테마의 줄(화면의 「작성 계획」 탭)


@router.get("/api/docs/{doc_id}/form-review")
def review_get(doc_id: str):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        return {"hwpx": False, "enabled": False, "review": None, "planned": False, "decided": [], "open": [], "stale": False, "run": None, "opts": {"duo": False}, "llm2": False, "prev": {}, "held": {}}
    return _view(s)


CALL_S = 900.0   # 한 모델의 검토 한 번(Codex 도 같은 한도)


def _ask(prompt, place_ids, has_mats, run, refs=None, duo=False):
    """검토를 함께 부를 모델마다(LLM1 · LLM2 … — `agent_settings.models`, 기본 `form_review.LLMS`) 따로 받고, 둘 이상 답하면 LLM1 의 모델이 **협의**해 하나로 낸다
    (2026-11-25 사용자 「양식 검토할때 claude fable, 하고 codex astra 모두 추출해서 협의하도록」). → (협의한 답 · 자리마다 기록 [{slot, model, backend, ms, ok, error, questions}] | []).
    모델이 하나면 전과 같은 한 번(에이전트 설정의 모델). 한 모델만 답하면 그 답을 쓰고 협의는 건너뛴다(기록에 남김) · 협의가 실패하면 LLM1 의 답(없으면 먼저 답한 것)."""
    # 두 모델 + 협의의 틀은 공통 함수(app/llm_duo.py — 2026-11-26 부터 04 「LLM 검증·보완」 · 작성 지침 보완도 같이 쓴다). 양식 검토는 답이 같아 보여도 늘 협의한다(same_fn 없음 — 물음을 하나로 모으는 일).
    # 두 모델 협의는 **옵션**이다(2026-11-27 사용자 「양식 검토의 두 모델 협의 는 옵션으로 둘 수 있고」 — 기본 = 한 모델 LLM1: spec_양식작성 ② §5-12 1). 어느 모델인지는 전처럼 에이전트 설정의 models 가 정한다
    models = agent_settings.models("form_review", form_review.LLMS)
    models = models if duo else models[:1]
    out = llm_duo.ask(form_review.SCHEMA, prompt, "form-review", models, timeout=CALL_S, single_timeout=600.0, effort="medium", default_model=form_review.MODEL,
                      check=lambda d: form_review.check(d, place_ids, has_mats, refs), consult=form_review.consult_prompt, same_fn=None, on=run.__setitem__)
    got, rec, by = out["got"], out["rec"], {d["slot"]: d["data"] for d in out["drafts"]}
    if not rec:   # 한 모델(사람이 「한 모델만」 으로 둠)
        if got.get("data") is None:
            raise RuntimeError(f"LLM 이 답하지 못했습니다({got.get('error') or '까닭 모름'})")
        return got, []
    if not out["drafts"]:
        err = got.get("error") or "까닭 모름"
        raise RuntimeError(err if err.startswith("모든 모델") else f"모든 모델이 답하지 못했습니다({err})")
    for r in rec:   # 자리마다 그 답의 물음 수(협의는 협의한 답의 것)
        d = by.get(r["slot"]) if r["slot"] != llm_duo.CONSULT_SLOT else (got.get("data") if r.get("ok") else None)
        if r.get("backend") is not None or r["slot"] != llm_duo.CONSULT_SLOT:
            r["questions"] = len((d or {}).get("questions") or []) if r.get("ok") else 0
    return got, rec


def _go(s, places, mids, run, request="", plan_request="", duo=False):
    """검토 한 번(배경 스레드) — 실패해도 앞 검토는 그대로 둔다. mids 가 있으면 작성 계획(앞 양식 검토의 요약 · 작성 방향 · 테마는 지닌다 — form_review.keep_review).
    plan_request = 「작성 계획에 줄 요청」(작성 계획 때만 프롬프트에 싣고 검토에 planRequest 로 남긴다 — 다시 열면 그 칸의 처음 값). duo = 두 모델로 협의(옵션)."""
    from app import heading_runs
    try:
        graph = heading_runs.graph(s)
        with s.lock:
            blocks = s.doc.blocks()
        store = doc_agent.Store(s.id)
        mats = [m for m in (store.material(i) for i in mids) if m is not None]
        # 작성 계획의 자료 글은 절마다 머리 줄 「[[자료 id/절 id | p.쪽 | 제목]]」 을 붙여 싣는다 — 계획이 자리마다 근거 절(evidence)을 그 id 로 고른다(spec_양식작성 ② §5-12 4)
        mtext = form_review.materials_marked(mats) if mats else ""
        refs = form_review.material_refs(mats, mtext) if mats else None   # 실제로 보낸 절만(잘려서 못 본 절을 근거로 받아 주지 않는다)
        st = load(s.id)
        job = job_prompts.for_work(s.id)
        g = merge_guides.get(form_review.GUIDE)
        from app import guide_write_api
        plan_request = plan_request if mats else ""
        # 「정한 것」 은 **이번 입력에 쓸 수 있는 답만** 싣는다(호출 전에 가린다 — form_review.usable: 다른 자료로 물은 답 · 이전 답은 빼고, 양식 검토에는 자료로 물은 답을 모두 뺀다)
        data = form_review.payload(blocks, graph, places, form_review.usable(st["decided"], mids), mtext, guide_write_api.uploaded_texts(s), request, plan_request)
        t0 = time.time()
        got, llms = _ask(form_review.prompt(data, job, g), [p["id"] for p in places], bool(mats), run, refs, duo)
        wall = int((time.time() - t0) * 1000)
        rv = form_review.check(got["data"], [p["id"] for p in places], bool(mats), refs)
        if llms:
            rv["llms"] = llms
        # 기록 = 이 검토에 든 **모든 호출**(2026-11-27 Carbon P1-3 — 전에는 협의 호출 하나의 ms · costUsd 만 적어 두 모델의 호출이 빠졌다): calls = 답을 받은 호출 수 · wallMs = 기다린 시간 · costUsd = 모든 호출의 합
        costs = [r.get("costUsd") for r in llms or [got] if isinstance(r.get("costUsd"), (int, float))]
        n_calls = sum(1 for r in llms if r.get("backend") is not None or r.get("ok")) if llms else 1
        prev = st["review"] or {}
        if mats:   # 작성 계획이 자료를 읽고 뽑은 테마는 따로 남긴다(2026-11-26 사용자 「작성계획 세우기에서 나온 결과 인지 6번에서 나온 결과 인지 모르잖아. 탭으로 해서 구분」) — topics 는 06 양식 검토의 것
            rv["planTopics"] = list(rv.get("topics") or [])
        if mats and prev.get("sig") == form_review.sig(places):   # 작성 계획 — 양식 · 지침이 그대로면 요약 · 작성 방향 · 테마는 앞 양식 검토의 것(astra 2차 G14 의 테마 잇기를 넓힘)
            form_review.keep_review(rv, prev)
            request = prev.get("request") or ""   # 검토가 본 요청 그대로 둔다(계획은 요청을 다시 읽지만 검토를 바꾸지 않는다)
        rv.update(at=round(time.time(), 3), rev=s.rev, sig=form_review.sig(places), sigs=form_review.sigs(places), materials=list(mids), cut=data["cut"],
                  request=request, planRequest=plan_request, fed=form_review.fed(places, request), duo=bool(llms),
                  matSigs={m["id"]: m.get("sha256") for m in mats}, secVer=material_index.VERSION,   # 계획이 본 자료의 지문 · 절을 가른 규칙의 판 — 근거 절(evidence)은 둘 다 그대로일 때만 쓴다(evidence)
                  call={**{k: got.get(k) for k in ("backend", "model", "effort", "ms", "costUsd")}, "calls": n_calls, "wallMs": wall, **({"costUsd": round(sum(costs), 6)} if costs else {})},
                  guide=merge_guides.brief(g), job=job_prompts.brief(job))
        with _LOCK:   # 읽기 → 잇기 → 쓰기를 답 저장(review_answers)과 같은 잠금 안에서 — 도는 동안 사람이 저장한 답을 옛 것으로 덮지 않는다(astra R2)
            st = load(s.id)   # 도는 동안 사람이 답을 고쳤을 수 있다 — 지금 것에 얹는다
            stale = form_review.mark_stale(st["decided"], mids) if mats else 0   # 다른 자료로 물은 답은 「이전 답」 으로(쓰지 않고 후보로만 — ② §5-12 6)
            if mats:   # 양식 검토가 낸 범위 물음 가운데 아직 답하지 않은 것은 계획이 다시 내지 않아도 남긴다(계획 모델이 빠뜨리면 그 자리의 보류가 사라졌다 — astra R2)
                for q in prev.get("questions") or ():
                    if (isinstance(q, dict) and q.get("kind") == "scope" and len(rv["questions"]) < form_review.QUESTIONS_MAX and not any(x["text"] == q.get("text") for x in rv["questions"])
                            and form_review.open_questions({"questions": [q]}, st["decided"])):
                        rv["questions"].append({**q, "key": f"q{len(rv['questions']) + 1}", "suggest": "", "source": ""})
            for d in st["decided"]:   # 정한 것의 key 를 새 물음에 다시 잇는다(같은 물음 글) — 이은 것이 없으면 열쇠 없이 남는다(답은 답한 때의 자리에 그대로 닿는다)
                q = next((x for x in rv["questions"] if x["text"] == d["q"]), None)
                d["key"] = q["key"] if q else ""
            _save(s.id, {"review": rv, "decided": st["decided"]})
        run.update(state="done", questions=len(rv["questions"]), places=len(rv["places"]))
        works.log(s.id, "formReview", places=len(places), questions=len(rv["questions"]), open=len(form_review.open_questions(rv, st["decided"])), materials=len(mids), ms=wall,
                  calls=n_calls, duo=bool(llms), **({"deferred": rv["deferred"]} if rv.get("deferred") else {}), **({"stale": stale} if stale else {}),
                  **({"evidence": sum(1 for p in rv["places"].values() if p.get("evidence"))} if mats else {}))
    except Exception as e:   # noqa: BLE001 — 실패는 실행 상태로 보인다(앞 검토는 그대로)
        run.update(state="failed", error=f"{e}"[:300])
    finally:
        run["ended"] = round(time.time(), 3)


@router.post("/api/docs/{doc_id}/form-review")
def review_run(doc_id: str, body: dict = Body(default={})):
    from app import guide_write_api
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "양식 검토는 hwpx 문서만 됩니다")
    mids = (body if isinstance(body, dict) else {}).get("materials") or []
    store = doc_agent.Store(s.id)
    if not isinstance(mids, list) or not all(isinstance(m, str) for m in mids) or len(set(mids)) != len(mids) or any(store.material(m) is None for m in mids):
        raise HTTPException(400, "materials 는 이 문서의 자료 id 목록(겹침 없이)")
    bad = guide_write_api.outside(s.id, mids)   # 양식 작성 — 이 프로젝트의 참조 문서에서 온 자료만(spec_양식작성 ② §2-1)
    if bad:
        raise HTTPException(409, f"이 프로젝트의 참조 문서가 아닌 문서의 자료입니다({' · '.join(bad[:3])}) — 빼고 고르거나 그 문서를 「이 프로젝트에 넣기」 합니다")
    note = (body if isinstance(body, dict) else {}).get("note") or ""
    if not isinstance(note, str) or len(note) > form_review.REQUEST_MAX:
        raise HTTPException(400, f"note(사람의 요청 — 이번 작성의 지침)는 {form_review.REQUEST_MAX:,}자까지")
    plan_note = (body if isinstance(body, dict) else {}).get("planNote") or ""
    if not isinstance(plan_note, str) or len(plan_note) > form_review.REQUEST_MAX:
        raise HTTPException(400, f"planNote(작성 계획에 줄 요청)는 {form_review.REQUEST_MAX:,}자까지")
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    st0 = load(s.id)
    if mids and st0["review"] is None:   # 작성 계획은 양식 검토 뒤 — 한 단추가 두 걸음을 함께 돌리지 않는다(2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려」)
        raise HTTPException(409, "먼저 「양식 검토」 를 하세요 — 작성 계획은 양식 검토 뒤에 자료로 세웁니다")
    duo = (body if isinstance(body, dict) else {}).get("duo")   # 두 모델로 협의(옵션) — 안 주면 이 문서에 마지막으로 쓴 값(처음은 한 모델)
    if duo is not None and not isinstance(duo, bool):
        raise HTTPException(400, "duo 는 true · false")
    duo = st0["opts"]["duo"] if duo is None else duo
    if duo and len(agent_settings.models("form_review", form_review.LLMS)) < 2:
        raise HTTPException(400, "둘째 모델(LLM2)이 설정에 없습니다 — LLM 칩에서 「두 모델로」 를 고른 뒤 협의를 켭니다")
    places, _ = guide_write_api._places(s)
    if not places:
        raise HTTPException(400, "자리가 없습니다 — 헤딩 · 표 분석(헤딩 그래프)이 끝났는지 확인하세요")
    run = {"state": "running", "at": round(time.time(), 3), "ended": None, "error": None, "materials": list(mids)}
    with _LOCK:
        cur = _RUNS.get(s.id)
        if cur is not None and cur["state"] == "running":
            raise HTTPException(409, "이 문서의 양식 검토가 이미 돌고 있습니다")
        now = load(s.id)   # 고른 옵션을 이 문서에 기억한다 — **지금 저장본**에 옵션만 얹는다(위에서 읽은 뒤 다른 창이 저장한 답을 옛 것으로 덮지 않게: astra R2)
        if duo != now["opts"]["duo"]:
            _save(s.id, {"review": now["review"], "decided": now["decided"], "opts": {"duo": duo}})   # 못 쓰면 여기서 예외 — 실행을 등록하기 전이라 「도는 중」 이 남지 않는다
        _RUNS[s.id] = run
    run["duo"] = duo
    threading.Thread(target=agent_notes.carry(_go), args=(s, places[:200], mids, run, form_review.request_text(note), form_review.request_text(plan_note) if mids else "", duo), name=f"form-review-{s.id}", daemon=True).start()
    return {"run": dict(run)}


@router.put("/api/docs/{doc_id}/form-review/answers")
def review_answers(doc_id: str, body: dict = Body(...)):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "양식 검토는 hwpx 문서만 됩니다")
    ans = (body if isinstance(body, dict) else {}).get("answers")
    if not isinstance(ans, list) or not all(isinstance(x, dict) and isinstance(x.get("a", ""), str) for x in ans):
        raise HTTPException(400, "answers = [{key?, q?, a}]")
    with _LOCK:
        st = load(s.id)
        qs = {q["key"]: q for q in (st["review"] or {}).get("questions") or ()}
        dec = st["decided"]
        for x in ans:
            a = " ".join(x.get("a", "").split())[:form_review.ANSWER_MAX]
            q = qs.get(x.get("key")) if x.get("key") else None
            if x.get("key") and q is None:
                raise HTTPException(400, f"모르는 물음입니다: {x['key']} — 검토를 다시 읽어 주세요")
            sent = " ".join(str(x.get("q") or "").split())[:form_review.Q_MAX]
            if q is not None and sent and sent != q["text"]:   # 옛 화면의 물음 번호 — 다시 검토한 뒤 같은 번호가 다른 물음이 됐다(astra 3차: 「보고서 종류」 의 답이 「주관기관」 물음에 저장됐다)
                raise HTTPException(409, "검토가 바뀌었습니다 — 물음을 다시 읽어 주세요")
            text = q["text"] if q else sent
            if not text:
                raise HTTPException(400, "q(물음 글) 또는 key 가 필요합니다")
            old = next((d for d in dec if d["q"] == text), None)   # 같은 물음의 앞 답(이전 답 stale 포함) — 새 답이 바꾼다
            dec = [d for d in dec if not ((q and d.get("key") == q["key"] and d["q"] == text) or d["q"] == text)]
            if a:
                # basis = 답한 때 검토가 본 자료 id 들 — **자료를 읽고 물은 물음(kind content)의 답만** 적는다: 뒤의 작성 계획이 다른 자료로 서면 「이전 답」 이 된다(form_review.mark_stale).
                # 범위 물음(scope — 무엇을 추출할지)과 물음 없이 적은 답은 빈 목록 = 자료가 바뀌어도 그대로(계획 화면에서 범위 답을 고쳐도 자료에 묶이지 않는다 — astra R2)
                rv0 = st["review"] or {}
                basis = list(rv0.get("materials") or []) if q is not None and q.get("kind") != "scope" else []
                # 물음 없이 다시 쓰는 답(「이전 답」 의 「다시 씀」)은 그 답이 닿던 자리 · 자리 잃음 표시를 지닌다 — 빈 목록(문서 전체)으로 넓히지 않는다(astra R2)
                places = list(q["places"]) if q else list((old or {}).get("places") or [])
                lostq = bool(q.get("unplaced")) if q else bool((old or {}).get("unplaced"))
                dec.append({"key": q["key"] if q else "", "q": text, "a": a, "places": places, "at": round(time.time(), 3), "basis": basis,
                            **({"unplaced": True} if lostq else {})})   # 자리를 잃은 물음의 답 — 물음이 사라져도 어느 자리에도 싣지 않는다
        if len(dec) > DECIDED_MAX:   # 넘치면 이전 답(stale — 쓰지 않는 답)을 오래된 것부터 버린다(2026-11-27 Carbon P1-2 — 다시 검토할 때마다 쌓여 답 저장이 막혔다)
            drop = {id(d) for d in sorted((d for d in dec if d.get("stale")), key=lambda d: d.get("at") or 0)[:len(dec) - DECIDED_MAX]}
            dec = [d for d in dec if id(d) not in drop]
        if len(dec) > DECIDED_MAX:
            raise HTTPException(400, f"정한 것은 {DECIDED_MAX}개까지 둘 수 있습니다")
        _save(s.id, {"review": st["review"], "decided": dec})
    works.log(s.id, "formReviewAnswer", n=len(ans), decided=len(dec))
    return _view(s)


def plans(wid, places, place_ids=None):
    """지침 작성의 자리마다 붙일 검토 글 {자리 id: 글} — 검토 · 정한 것이 없으면 빈 dict. place_ids(지금의 자리 id 모두)를 주면 자리를 잃은 답은 싣지 않는다(form_review.lost)."""
    st = load(wid)
    out = {}
    for p in places:
        t = form_review.plan_text(form_review.plan_for(st["review"], st["decided"], p["id"], place_ids))
        if t:
            out[p["id"]] = t
    return out


def answers(st, places, place_ids=None):
    """자리마다 그 자리에 닿는 사람의 답 {자리 id: [답 글…]} — 자리 턴의 값 근거(`form_review.answers_for`: 요청 글에 싣는 것과 같은 목록)."""
    return {p["id"]: form_review.answers_for(st["review"], st["decided"], p["id"], place_ids) for p in places}


def plan_sig(st, place_id, place_ids=None):
    """그 자리의 초안이 기댄 것의 지문 — 작성 계획(세운 때 · 자료) + 그 자리에 닿는 답. 초안을 받을 때 턴에 적어 두고(`doc_agent_api._turn` 의 planSig), 덮임이 지금 것과 견준다:
    다르면 「이전 계획의 초안」 이다(계획을 다시 세웠거나 그 자리의 답을 고쳤다 — 옛 초안을 그대로 「모두 반영」 하지 않는다: 2026-11-27 astra R2 P1)."""
    import hashlib
    import json
    rv = st["review"] or {}
    raw = json.dumps([rv.get("at"), sorted(rv.get("materials") or ()), form_review.answers_for(rv, st["decided"], place_id, place_ids)], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def evidence(st, mats):
    """자리마다의 근거 절 {자리 id: [{mat, sec, …}]} — 작성 계획이 고른 것 가운데 **계획 때와 글이 같은 자료**의 것만(자료 지문 `matSigs` — 자료를 지우고 다시 가져와 글이 달라졌으면 절 id 가 가리키는 곳이 다르다)."""
    rv = st["review"] or {}
    if rv.get("secVer") != material_index.VERSION:   # 절을 가르는 규칙이 계획 때와 다르다 — 절 id 가 다른 절을 가리킬 수 있다: 근거 없이(자료 전체로)
        return {}
    sigs = rv.get("matSigs") if isinstance(rv.get("matSigs"), dict) else {}
    same = {m["id"] for m in mats or () if sigs.get(m.get("id")) is not None and sigs[m["id"]] == m.get("sha256")}
    out = {}
    for pid, p in (rv.get("places") or {}).items() if isinstance(rv.get("places"), dict) else ():
        ev = [e for e in (p or {}).get("evidence") or () if isinstance(e, dict) and e.get("mat") in same]
        if ev:
            out[pid] = ev
    return out

