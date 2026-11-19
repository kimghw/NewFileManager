"""작업 진행 에이전트 API(spec_작업에이전트 ② §4) — server.py 가 include 한다. 계약 · 프롬프트 · 검사 · 스크립트 답은 `app/work_guide.py`.

- `POST /api/docs/{id}/agent/guide` — 진행 턴 하나(문서는 안 바뀐다): 화면이 보낸 사건(start · say · answer · result)과 지금 상태(steps · actions · facts)로 에이전트의 말 · 질문 카드 · 다음 행동을 낸다.
  저장은 편집 턴과 같은 저장소(`doc_agent.Store` — `agent/chat.jsonl` · `agent/turns/<id>.json`: 턴의 `kind` 가 `guide`) — `GET /api/docs/{id}/agent` 의 `turns` 에 차례대로 섞여 보인다.
- `PUT /api/docs/{id}/agent/guide/{turn}` — 카드의 끝(실행함 · 건너뜀 · 답함)을 적는다.
- `POST /api/agent/guide` — 첫 화면(문서 없음): 올린 파일의 이름·형식과 사람의 글로 어느 TASK 로 시작할지. 저장하지 않는다(화면이 붙들고 있다가 시작 턴의 `carry` 로 넘긴다).
LLM 이 꺼져 있거나 호출이 실패하면 스크립트가 답한다(`work_guide.fallback` — 턴의 `llm: false`).
로그(spec ② §8): 진행 턴의 자료에 `logs`(로그 목록 · 작업 기록의 끝 몇 줄)를 싣고, 에이전트가 답의 `read` 로 더 청하면 `app/work_logs.py` 로 읽어 `logsRead` 에 붙여 다시 부른다(`_answer` — 두 번까지)."""
import logging
import time

from fastapi import APIRouter, Body, HTTPException

from app import doc_agent, llm, work_guide, work_logs, workflow, works

router = APIRouter()
log = logging.getLogger(__name__)
work_logs.install()   # 서버 로그(경고 · 오류)를 모으기 시작한다 — 에이전트가 읽는 로그의 하나(spec ② §8)
OUTCOME_MAX = 500
ACCEPT = ("hwp", "hwpx")   # task_catalog.js taskAcceptOf 의 기본(accept 가 없는 TASK)


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _task(s):
    """그 작업의 TASK → {job, name, project, round, role} — role: target(목적 문서) · source(원본 문서) · ""(그 TASK 에 목적 문서 종류가 없음 · TASK 없음).
    name = 화면의 이름(task_catalog.js — 조립한 워크플로우는 저장소의 이름: 키를 이름으로 내지 않는다)."""
    from app import custom_tasks   # 가벼운 모듈
    t = ((works.work(s.id) or {}).get("task") or {})
    job = t.get("job") or ""
    target = works.TARGET_FILE.get(job)
    cat = workflow.catalog()[0]
    return {"job": job, "name": (cat.get(job) or {}).get("name") or (custom_tasks.get(job) or {}).get("name") or job, "project": t.get("project") or "", "round": t.get("round") or 1,
            "role": ("target" if t.get("file") == target else "source") if target and t.get("file") else ""}


def _text(body, key="text", cap=work_guide.TEXT_MAX):
    v = body.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        raise HTTPException(400, f"{key} 는 글")
    return v.strip()[:cap]


def _sum_calls(calls):
    """로그를 읽고 다시 물은 호출들 → 호출 기록 하나(시간 · 비용은 더하고 나머지는 마지막 것) + rounds(부른 횟수)."""
    last = dict(calls[-1])
    if len(calls) > 1:
        last["ms"] = sum(c.get("ms") or 0 for c in calls)
        costs = [c["costUsd"] for c in calls if c.get("costUsd") is not None]
        last["costUsd"] = round(sum(costs), 6) if costs else None
        last["rounds"] = len(calls)
    return last


def _answer(data, job, home=False, wid=None):
    """LLM 을 쓸 수 있으면 부르고, 꺼져 있거나 못 쓰는 답이면 스크립트 답 → (답 {reply, act, ask, notes}, llm 을 썼나, 호출 기록 | None, 프롬프트, 받은 그대로, 읽은 로그 [{log, find, n, total, lines(줄 수)}]).
    에이전트가 로그 읽기를 청하면(`reads` — spec ② §8) 그 줄을 읽어 자료의 `logsRead` 에 붙이고 다시 부른다(`READ_ROUNDS` 번까지 — 넘으면 읽은 것으로 답하게 한다). wid = 로그를 읽을 작업(첫 화면은 None — 읽지 않는다)."""
    fb = work_guide.home_fallback if home else work_guide.fallback
    if not llm.status()["available"]:
        return fb(data), False, None, "", None, []
    calls, reads, got = [], [], None
    for left in range(work_guide.READ_ROUNDS, -1, -1):
        if wid is not None:
            data["logs"] = {**(data.get("logs") or {}), "rounds": left}
        got = work_guide.ask(data, job, home=home)
        calls.append(got["call"])
        want = got.get("reads") or []
        if wid is None or not want or left == 0 or got["data"] is None:
            break
        for w in want:
            res = work_logs.read(wid, w["log"], w["n"], w["find"])
            data.setdefault("logsRead", []).append(res)
            reads.append({"log": res["log"], "find": res.get("find") or "", "n": w["n"], "total": res.get("total") or 0, "lines": len(res.get("lines") or []), "error": res.get("error") or ""})
    call = _sum_calls(calls)
    if got["data"] is not None:
        ans = got["data"]
        if reads:
            ans["notes"] = ["로그를 읽었습니다 — " + " · ".join(f"{work_logs.TITLE.get(r['log'], r['log'])} {r['lines']}줄" + (f"(「{r['find']}」)" if r["find"] else "") for r in reads)[:280]] + ans["notes"]
        return ans, True, call, got["prompt"], got["response"], reads
    ans = fb(data)
    ans["notes"] = [f"LLM 답을 받지 못해 스크립트가 답했습니다 — {call.get('error') or '까닭 모름'}"[:300]] + ans["notes"]
    return ans, False, call, got["prompt"], got["response"], reads


@router.post("/api/docs/{doc_id}/agent/guide")
def guide_turn(doc_id: str, body: dict = Body(...)):
    """{event: "start" | "say" | "answer" | "result", text?, ok?(result 의 됐는지), act?(result·answer 가 가리키는 행동 이름), steps, actions, facts, carry?[{who, text}]} → {turn: 진행 턴 보기(`work_guide.view`)}.
    400 꼴이 틀림 · 409 그 사이 「비우기」 를 함. 문서는 바뀌지 않는다."""
    event = body.get("event")
    if event not in work_guide.EVENTS:
        raise HTTPException(400, "event 는 " + " · ".join(work_guide.EVENTS))
    text = _text(body)
    if event in ("say", "answer") and not text:
        raise HTTPException(400, "글이 비었습니다")
    s = _sess(doc_id)
    store = doc_agent.Store(s.id)
    gen, task = store.gen(), _task(s)
    steps, actions, carry = work_guide.steps_in(body.get("steps")), work_guide.actions_in(body.get("actions")), work_guide.talk_in(body.get("carry"), work_guide.CARRY_MAX)
    data = {"event": event, "text": text, "task": task, "doc": {"name": getattr(s, "name", "") or "", "format": s.fmt}, "steps": steps, "actions": actions, "facts": work_guide.facts_in(body.get("facts")),
            "history": (carry + work_guide.history_of(store.turns()))[-work_guide.HISTORY:]}
    if event == "result":
        data.update(ok=body.get("ok") is not False, act=_text(body, "act", 40))
    data["logs"] = {"index": work_logs.index(s.id), "recent": work_logs.recent(s.id)}   # 로그(spec ② §8) — 목록 · 작업 기록의 끝 몇 줄은 늘 싣고, 더 볼 것은 에이전트가 read 로 청한다
    ans, used, call, prompt, response, reads = _answer(data, task["job"], wid=s.id)
    act = next((a for a in actions if a["name"] == ans["act"]), None)
    rec = {"id": store.new_turn_id(), "kind": "guide", "at": round(time.time(), 3), "rev": s.rev, "event": event, "request": {"text": text if event in ("say", "answer") else ""}, "result": text if event == "result" else "",
           "carry": carry if event == "start" else [], "reply": ans["reply"], "ask": ans["ask"], "act": {k: act[k] for k in ("name", "label", "does", "change", "paid", "key")} if act else None,   # key = 그 카드가 가리키는 계획(화면이 「진행」 때 견준다)
           "state": "open" if (act or ans["ask"]) else "done", "outcome": "", "llm": used, "notes": ans["notes"], "steps": steps, "error": (call or {}).get("error") if not used else None,
           "call": call, "prompt": prompt, "response": response, "job": task["job"], "reads": reads}   # reads = 이 턴에 읽은 로그(어느 로그 · 몇 줄 — 읽은 줄 자체는 prompt 의 자료에)
    if store.save_turn(rec, gen=gen) is None:
        raise HTTPException(409, doc_agent.CLEARED)
    works.log(s.id, "agentGuide", event=event, act=ans["act"], ask=(ans["ask"] or {}).get("kind") or "", llm=used, reads=[r["log"] for r in reads], **{k: (call or {}).get(k) for k in ("backend", "model", "ms", "costUsd")})
    return {"turn": work_guide.view(rec)}


@router.put("/api/docs/{doc_id}/agent/guide/{turn}")
def guide_close(doc_id: str, turn: str, body: dict = Body(...)):
    """{state: "done" | "skipped", outcome?(한 줄 — 실행 결과 · 답한 값)} → {turn} — 카드(질문 · 실행)의 끝을 적는다. 404 그런 진행 턴 없음 · 400 꼴."""
    state = body.get("state")
    if state not in ("done", "skipped"):
        raise HTTPException(400, "state 는 done · skipped")
    store = doc_agent.Store(_sess(doc_id).id)
    with store.lock:
        rec = store.turn(turn)
        if rec is None or rec.get("kind") != "guide":
            raise HTTPException(404, "그런 진행 턴이 없습니다")
        rec.update(state=state, outcome=_text(body, "outcome", OUTCOME_MAX))
        store.save_turn(rec)
    return {"turn": work_guide.view(rec)}


def _tasks():
    """첫 화면에 보낼 워크플로우 목록 [{job, name, desc, accept, soon}] — 붙박이는 이름·설명이 task_catalog.js, 받는 확장자도 그 파일의 accept(없으면 hwp·hwpx).
    그 뒤에 화면에서 조립한 워크플로우(app/custom_tasks.py — 만든 차례): 이름 = 저장소의 이름 · 설명 = 적은 한 줄 설명(비웠으면 등록부가 실제 배정에서 지은 글 — workflow.custom_desc) ·
    받는 형식 = 이관과 같은 hwp · hwpx(spec_워크플로우 ② §14)."""
    from app import custom_tasks   # 가벼운 모듈
    cat = workflow.catalog()[0]
    return [{"job": t["job"], "name": (cat.get(t["job"]) or {}).get("name") or t["job"], "desc": (cat.get(t["job"]) or {}).get("desc") or "",
             "accept": list((cat.get(t["job"]) or {}).get("accept") or ACCEPT), "soon": bool(t.get("soon"))} for t in workflow.TASKS] \
        + [{"job": c["key"], "name": c["name"], "desc": c["desc"] or workflow.custom_desc(c), "accept": list(ACCEPT), "soon": False} for c in custom_tasks.all()]


@router.post("/api/agent/guide")
def guide_home(body: dict = Body(...)):
    """첫 화면(문서 없음) — {text?, files?[{name, ext, size}], history?[{who, text}]} → {reply, ask | null, act: "start:<job>" | "", llm, notes[], tasks[…]}.
    행동은 「그 워크플로우로 시작」 뿐이다(파일이 있을 때 · 준비 중인 워크플로우 제외 · 그 확장자를 받는 워크플로우만). 저장하지 않는다."""
    text = _text(body)
    files = []
    for f in body.get("files") if isinstance(body.get("files"), list) else ():
        if isinstance(f, dict) and str(f.get("name") or "").strip():
            name = str(f["name"]).strip()[:200]
            files.append({"name": name, "ext": (name.rsplit(".", 1)[-1].lower() if "." in name else "")[:8], "size": f.get("size") if isinstance(f.get("size"), int) else 0, "target": f.get("target") is True})
    files = files[:work_guide.FILES_MAX]
    if not text and not files:
        raise HTTPException(400, "글이나 파일이 있어야 합니다")
    if len(files) == 1:
        files[0]["target"] = True   # 하나면 그것이 목적 문서(화면의 문서 목록과 같은 규칙)
    raw = body.get("list") if isinstance(body.get("list"), dict) else {}
    picked = next((f["name"] for f in files if f["target"]), "")
    lst = {"target": picked, "project": " ".join(str(raw.get("project") or "").split())[:60], "auto": raw.get("auto") is True}   # 첫 화면 문서 목록의 상태 — 목적 문서는 files 의 target 이 원본(글로 온 이름을 믿지 않는다)
    tasks = _tasks()
    exts = work_guide.target_exts(files)
    # 시작은 목적 문서가 정해졌을 때만(파일 하나 · 사람이 고름) — 둘 이상인데 안 골랐으면 행동이 없다: 에이전트는 문서 목록에서 고르라고 말한다(목적 문서를 짐작하지 않는다)
    actions = work_guide.actions_in([{"name": work_guide.START + t["job"], "label": f"「{t['name']}」 로 시작", "does": t["desc"], "change": "store"} for t in tasks if picked and not t["soon"] and exts <= set(t["accept"])])
    data = {"text": text, "files": files, "list": lst, "tasks": tasks, "actions": actions, "history": work_guide.talk_in(body.get("history"), work_guide.HISTORY)}
    ans, used, _call, _prompt, _response, _reads = _answer(data, None, home=True)
    if ans["ask"] and ans["ask"]["kind"] == "choice":   # 선택지는 지금 시작할 수 있는 TASK 만
        names = {a["name"] for a in actions}
        ans["ask"]["options"] = [o for o in ans["ask"]["options"] if o["value"] in names]
        if len(ans["ask"]["options"]) < 2:
            ans["ask"] = None
    elif ans["ask"] and ans["ask"]["kind"] == "config":
        ans["ask"] = None
    return {"reply": ans["reply"], "ask": ans["ask"], "act": ans["act"], "llm": used, "notes": ans["notes"], "tasks": tasks}
