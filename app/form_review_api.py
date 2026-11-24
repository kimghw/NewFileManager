"""양식 검토 끝점(spec_양식작성 ② §5-1) — 프롬프트 · 답 검증은 `app/form_review.py`(순수), 자리 목록은 지침 작성의 것(`guide_write_api._places`). hwpx 문서만 · 어느 워크플로우에서나.
문서를 바꾸지 않는다. 지침 작성의 「제안 받기」 는 검토가 있고 물음에 모두 답했을 때만 돈다(`gate` — guide_write_api 가 부른다).

- `GET /api/docs/{id}/form-review` → {hwpx, enabled(LLM), review | null, decided[{key, q, a, places, at}], open[아직 답 안 한 물음 key], stale(검토 뒤 자리 · 지침이 바뀜), run | null}.
- `POST /api/docs/{id}/form-review` {materials: [자료 id…]} → 배경에서 양식 전체를 한 번 검토(유료 LLM · 호출 1번 — 고른 자료가 있으면 물음의 답 후보를 자료에서 찾는다) → {run}. 409 = 도는 중 · 503 = LLM 없음.
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


def _view(s, places=None):
    st = load(s.id)
    rv = st["review"]
    if places is None and rv is not None:
        from app import guide_write_api
        places, _ = guide_write_api._places(s)
    with _LOCK:
        run = dict(_RUNS[s.id]) if s.id in _RUNS else None
    return {"hwpx": True, "enabled": bool(llm.status()["available"]), "review": rv, "planned": form_review.planned(rv), "decided": st["decided"],
            "open": [q["key"] for q in form_review.open_questions(rv, st["decided"])], "stale": bool(rv and places is not None and rv.get("sig") != form_review.sig(places)), "run": run}


@router.get("/api/docs/{doc_id}/form-review")
def review_get(doc_id: str):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        return {"hwpx": False, "enabled": False, "review": None, "planned": False, "decided": [], "open": [], "stale": False, "run": None}
    return _view(s)


def _go(s, places, mids, run):
    """검토 한 번(배경 스레드) — 실패해도 앞 검토는 그대로 둔다."""
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
        data = form_review.payload(blocks, graph, places, st["decided"], mtext)
        got = llm.call(form_review.SCHEMA, form_review.prompt(data, job, g), "form-review", timeout=600.0, effort="medium", model=form_review.MODEL)
        if got.get("data") is None:
            raise RuntimeError(f"LLM 이 답하지 못했습니다({got.get('error') or '까닭 모름'})")
        rv = form_review.check(got["data"], [p["id"] for p in places], bool(mats))
        rv.update(at=round(time.time(), 3), rev=s.rev, sig=form_review.sig(places), materials=list(mids), cut=data["cut"],
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
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    places, _ = guide_write_api._places(s)
    if not places:
        raise HTTPException(400, "자리가 없습니다 — 헤딩 · 표 분석(헤딩 그래프)이 끝났는지 확인하세요")
    run = {"state": "running", "at": round(time.time(), 3), "ended": None, "error": None, "materials": list(mids)}
    with _LOCK:
        cur = _RUNS.get(s.id)
        if cur is not None and cur["state"] == "running":
            raise HTTPException(409, "이 문서의 양식 검토가 이미 돌고 있습니다")
        _RUNS[s.id] = run
    threading.Thread(target=agent_notes.carry(_go), args=(s, places[:200], mids, run), name=f"form-review-{s.id}", daemon=True).start()
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
            text = q["text"] if q else " ".join(str(x.get("q") or "").split())[:form_review.Q_MAX]
            if not text:
                raise HTTPException(400, "q(물음 글) 또는 key 가 필요합니다")
            dec = [d for d in dec if not ((q and d.get("key") == q["key"]) or d["q"] == text)]
            if a:
                dec.append({"key": q["key"] if q else "", "q": text, "a": a, "places": q["places"] if q else [], "at": round(time.time(), 3)})
        if len(dec) > DECIDED_MAX:
            raise HTTPException(400, f"정한 것은 {DECIDED_MAX}개까지 둘 수 있습니다")
        _save(s.id, {"review": st["review"], "decided": dec})
    works.log(s.id, "formReviewAnswer", n=len(ans), decided=len(dec))
    return _view(s)


def plans(wid, places):
    """지침 작성의 자리마다 붙일 검토 글 {자리 id: 글} — 검토 · 정한 것이 없으면 빈 dict."""
    st = load(wid)
    out = {}
    for p in places:
        t = form_review.plan_text(form_review.plan_for(st["review"], st["decided"], p["id"]))
        if t:
            out[p["id"]] = t
    return out

