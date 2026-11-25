"""양식 검토 끝점(spec_양식작성 ② §5-1) — 프롬프트 · 답 검증은 `app/form_review.py`(순수), 자리 목록은 지침 작성의 것(`guide_write_api._places`). hwpx 문서만 · 어느 워크플로우에서나.
문서를 바꾸지 않는다. 지침 작성의 「제안 받기」 는 검토가 있고 물음에 모두 답했을 때만 돈다(`gate` — guide_write_api 가 부른다).

- `GET /api/docs/{id}/form-review` → {hwpx, enabled(LLM), review | null, decided[{key, q, a, places, at}], open[아직 답 안 한 물음 key], stale(검토 뒤 자리 · 지침이 바뀜), run | null}.
- `POST /api/docs/{id}/form-review` {materials: [자료 id…], note, planNote?(작성 계획에 줄 요청 — 자료가 있을 때만 씀)} →배경에서 한 번(유료 LLM — 함께 검토하는 모델(LLM1 · LLM2 …)마다 한 번 + 둘 이상 답하면 협의 한 번: `_ask`) → {run}. materials 가 비면 **양식 검토**(양식 · 작성 지침 · 사람의 요청 note 만 — 자료는 안 읽음),
  있으면 **작성 계획**(양식 검토가 먼저 — 없으면 409 · 양식이 그대로면 검토의 요약 · 작성 방향 · 테마는 그대로 두고 자리마다 use · gap 과 물음만 받는다). 409 = 도는 중 · 503 = LLM 없음.
- `PUT /api/docs/{id}/form-review/answers` {answers: [{key?, q?, a}]} → 정한 것을 고친다(key = 검토의 물음 · 없으면 q 로 새 줄 · a 가 빈 글이면 그 줄을 지움) → 보기.
저장 = 작업 폴더 `form_review.json` {review, decided} — 다시 검토해도 정한 것(decided)은 버리지 않는다(같은 물음은 다시 묻지 않는다 · 검토 실패는 앞 검토를 지우지 않는다).
작업 저장이 꺼진 문서는 이 프로세스의 메모리에 둔다. 끝나면 작업 기록에 `formReview` 한 줄."""
import threading
import time

from fastapi import APIRouter, Body, HTTPException

from app import agent_notes, doc_agent, form_review, job_prompts, llm, merge_guides, works

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
    return {"review": rv, "decided": dec}


def _save(wid, data):
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
    wipe = lambda p: {**p, "use": "", "gap": ""} if isinstance(p, dict) else p  # noqa: E731
    ps = {k: wipe(p) for k, p in ps.items()} if isinstance(ps, dict) else [wipe(p) for p in ps or ()]
    _save(wid, {"review": {**rv, "places": ps, "materials": []}, "decided": st["decided"]})
    return True


def gate(wid):
    """지침 작성을 돌려도 되나 → (된다?, 까닭, 저장본). 양식 검토가 없거나 · 자료로 세운 작성 계획이 없거나 · 답하지 않은 물음이 있으면 안 된다(검토 → 계획 → 묻기 → 쓰기)."""
    st = load(wid)
    if st["review"] is None:
        return False, "먼저 「양식 검토」 를 하세요 — 양식 전체를 읽고 어떻게 쓸지 · 정해 줄 것을 정리합니다", st
    if not form_review.planned(st["review"]):
        return False, "자료를 고르고 「작성 계획 세우기」 를 하세요 — 자료로 자리마다 무엇을 쓸지 계획하고 확인할 것을 묻습니다", st
    left = form_review.open_questions(st["review"], st["decided"])
    if left:
        return False, f"쓰기 전에 확인할 것 {len(left)}개에 답하세요(「양식 검토」 의 물음 — 따로 정하지 않으려면 「{form_review.SKIP}」)", st
    return True, "", st


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
    return {"hwpx": True, "enabled": bool(llm.status()["available"]), "review": rv, "planned": form_review.planned(rv), "decided": st["decided"],
            "open": [q["key"] for q in form_review.open_questions(rv, st["decided"])], "stale": bool(rv and places is not None and rv.get("sig") != form_review.sig(places)), "run": run,
            "lost": [d["q"] for d in form_review.lost(rv, st["decided"], ids)] if ids is not None else [],   # 자리를 잃은 답(어느 자리에도 싣지 않는다 — 화면이 알린다)
            "topicLines": [form_review.scope_line(t) for t in (rv or {}).get("topics") or ()]}   # 테마마다 「뽑을 범위」 에 붙일 한 줄(앞말 없이 — 화면이 앞말을 붙인다)


@router.get("/api/docs/{doc_id}/form-review")
def review_get(doc_id: str):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        return {"hwpx": False, "enabled": False, "review": None, "planned": False, "decided": [], "open": [], "stale": False, "run": None}
    return _view(s)


def _go(s, places, mids, run, request="", plan_request=""):
    """검토 한 번(배경 스레드) — 실패해도 앞 검토는 그대로 둔다. mids 가 있으면 작성 계획(앞 양식 검토의 요약 · 작성 방향 · 테마는 지닌다 — form_review.keep_review).
    plan_request = 「작성 계획에 줄 요청」(작성 계획 때만 프롬프트에 싣고 검토에 planRequest 로 남긴다 — 다시 열면 그 칸의 처음 값)."""
    from app import heading_runs
    try:
        graph = heading_runs.graph(s)
        with s.lock:
            blocks = s.doc.blocks()
        store = doc_agent.Store(s.id)
        mats = [m for m in (store.material(i) for i in mids) if m is not None]
        mtext = doc_agent.materials_text(mats, form_review.MATERIAL_MAX) if mats else ""
        st = load(s.id)
        job = job_prompts.for_work(s.id)
        g = merge_guides.get(form_review.GUIDE)
        from app import guide_write_api
        plan_request = plan_request if mats else ""
        data = form_review.payload(blocks, graph, places, st["decided"], mtext, guide_write_api.uploaded_texts(s), request, plan_request)
        got = llm.call(form_review.SCHEMA, form_review.prompt(data, job, g), "form-review", timeout=600.0, effort="medium", model=form_review.MODEL)
        if got.get("data") is None:
            raise RuntimeError(f"LLM 이 답하지 못했습니다({got.get('error') or '까닭 모름'})")
        rv = form_review.check(got["data"], [p["id"] for p in places], bool(mats))
        prev = st["review"] or {}
        if mats and prev.get("sig") == form_review.sig(places):   # 작성 계획 — 양식 · 지침이 그대로면 요약 · 작성 방향 · 테마는 앞 양식 검토의 것(astra 2차 G14 의 테마 잇기를 넓힘)
            form_review.keep_review(rv, prev)
            request = prev.get("request") or ""   # 검토가 본 요청 그대로 둔다(계획은 요청을 다시 읽지만 검토를 바꾸지 않는다)
        rv.update(at=round(time.time(), 3), rev=s.rev, sig=form_review.sig(places), sigs=form_review.sigs(places), materials=list(mids), cut=data["cut"],
                  request=request, planRequest=plan_request, fed=form_review.fed(places, request),
                  call={k: got.get(k) for k in ("backend", "model", "effort", "ms", "costUsd")}, guide=merge_guides.brief(g), job=job_prompts.brief(job))
        st = load(s.id)   # 도는 동안 사람이 답을 고쳤을 수 있다 — 지금 것에 얹는다
        for d in st["decided"]:   # 정한 것의 key 를 새 물음에 다시 잇는다(같은 물음 글) — 이은 것이 없으면 자리 모름(모든 자리에)으로 남는다
            q = next((x for x in rv["questions"] if x["text"] == d["q"]), None)
            d["key"] = q["key"] if q else ""
        _save(s.id, {"review": rv, "decided": st["decided"]})
        run.update(state="done", questions=len(rv["questions"]), places=len(rv["places"]))
        works.log(s.id, "formReview", places=len(places), questions=len(rv["questions"]), open=len(form_review.open_questions(rv, st["decided"])), materials=len(mids), ms=got.get("ms"))
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
    note = (body if isinstance(body, dict) else {}).get("note") or ""
    if not isinstance(note, str) or len(note) > form_review.REQUEST_MAX:
        raise HTTPException(400, f"note(사람의 요청 — 이번 작성의 지침)는 {form_review.REQUEST_MAX:,}자까지")
    plan_note = (body if isinstance(body, dict) else {}).get("planNote") or ""
    if not isinstance(plan_note, str) or len(plan_note) > form_review.REQUEST_MAX:
        raise HTTPException(400, f"planNote(작성 계획에 줄 요청)는 {form_review.REQUEST_MAX:,}자까지")
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    if mids and load(s.id)["review"] is None:   # 작성 계획은 양식 검토 뒤 — 한 단추가 두 걸음을 함께 돌리지 않는다(2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려」)
        raise HTTPException(409, "먼저 「양식 검토」 를 하세요 — 작성 계획은 양식 검토 뒤에 자료로 세웁니다")
    places, _ = guide_write_api._places(s)
    if not places:
        raise HTTPException(400, "자리가 없습니다 — 헤딩 · 표 분석(헤딩 그래프)이 끝났는지 확인하세요")
    run = {"state": "running", "at": round(time.time(), 3), "ended": None, "error": None, "materials": list(mids)}
    with _LOCK:
        cur = _RUNS.get(s.id)
        if cur is not None and cur["state"] == "running":
            raise HTTPException(409, "이 문서의 양식 검토가 이미 돌고 있습니다")
        _RUNS[s.id] = run
    threading.Thread(target=agent_notes.carry(_go), args=(s, places[:200], mids, run, form_review.request_text(note), form_review.request_text(plan_note) if mids else ""), name=f"form-review-{s.id}", daemon=True).start()
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
            dec = [d for d in dec if not ((q and d.get("key") == q["key"]) or d["q"] == text)]
            if a:
                dec.append({"key": q["key"] if q else "", "q": text, "a": a, "places": q["places"] if q else [], "at": round(time.time(), 3),
                            **({"unplaced": True} if q and q.get("unplaced") else {})})   # 자리를 잃은 물음의 답 — 물음이 사라져도 어느 자리에도 싣지 않는다
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

