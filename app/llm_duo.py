"""두 모델이 따로 답하고 협의해 하나로 — 함께 부르는 에이전트(LLM1 · LLM2 …)의 공통 길(spec_에이전트 ② §8 「함께 부르기 — 공통 함수」).

2026-11-25 사용자 「양식 검토할때 claude fable, 하고 codex astra 모두 추출해서 협의」 로 양식 검토(25)에만 있던 틀을 뽑은 것 — 2026-11-26 사용자
「한개의 에이전트로 하지 말고 … 2개의 에이전트가 검증보완」 · 「문서의 지침을 작성할 떄는 2가지 모델을 같이 사용 … 불가피한 경우 1개만 선택」 으로
04 「LLM 검증·보완」 의 판정 호출(규칙 보강 · 유형 · 구간 · 표)과 작성 지침 보완(26)이 같이 쓴다. **두 모델을 부르는 길을 새로 짓지 말고 이것을 쓴다.**

- `ask(schema, prompt, what, models, …)` → {"got", "rec", "drafts"}: 모델마다(자리 LLM1 · LLM2 …) 같은 프롬프트로 **따로** 부르고(같이 — 자리는 서버 전체의 LLM 자리를 나눠 쓴다),
  둘 이상 답했고 답이 서로 다르면 LLM1 의 모델이 **협의** 프롬프트로 하나로 낸다. 한쪽만 답하면 그 답(협의 없음) · 협의가 실패하면 LLM1 의 답(없으면 먼저 답한 것) · 모두 실패면 data None.
  모델이 하나(사람이 「한 모델만」 으로 둔 것)면 전과 같은 한 번. 모델 자리의 None = 그 에이전트가 평소 부르는 모델(`llm.call` 의 보통 차례 — 서버 설정 · 「에이전트 설정」 의 model).
- `job(j, models)` = `llm.ask_all` 의 호출 하나를 그렇게(`llm.ask_all` 이 함께 부르는 에이전트의 호출에 쓴다) → `llm.call` 과 같은 꼴의 결과 + `duo`(자리마다 기록 · 답 — 실행 폴더의 호출 기록에 남는다:
  두 모델의 답을 협의한 답과 **따로** 지닌다).
- 답을 덮지 않는다: 이 함수는 「하나의 답」 을 돌려줄 뿐이고, 그 답을 스크립트 결과에 어떻게 얹는지는 부르는 쪽의 것 그대로다(spec_작업 ② §22)."""
import concurrent.futures
import json

from app import agent_notes, llm

CONSULT_SLOT = "협의"
LOOSE = ("reason", "summary", "note", "why", "detail")   # 답을 견줄 때 안 보는 칸(풀이 글 — 판정이 같아도 글은 다르다)
CONSULT = """

## 두 검토자의 답 — 협의
위 일을 두 검토자(LLM1 · LLM2 — 서로 다른 모델)가 같은 입력으로 **따로** 했습니다. 아래 두 답을 견줘 위와 **같은 출력 꼴로 하나의 답**을 내세요.
- 두 답이 같은 판정은 그대로 둡니다.
- 서로 다른 판정은 입력(자료)과 지침을 다시 읽고 근거가 더 분명한 쪽을 고릅니다. 한쪽에만 있는 판정 · 고침은 입력에서 근거를 확인할 수 있을 때만 받습니다.
- 어느 쪽도 확신할 수 없으면 스크립트 초안을 바꾸지 않는 쪽(고침을 적지 않음 · 모름)으로 둡니다 — 틀린 고침보다 남겨 두는 편이 낫습니다.
- 두 답 어디에도 없는 판정을 새로 짓지 않습니다. 입력에 없는 id · key 는 쓰지 않습니다.
"""


def consult_prompt(base, drafts):
    """협의 프롬프트 = 처음 프롬프트 그대로 + 협의 기준 + 검토자들의 답(자리 · 모델과 함께)."""
    return base + CONSULT + "\n".join(f"### {d['slot']} ({d['model']})\n" + json.dumps(d["data"], ensure_ascii=False, separators=(",", ":")) for d in drafts)


def _bare(x):
    if isinstance(x, dict):
        return {k: _bare(v) for k, v in sorted(x.items()) if k not in LOOSE}
    if isinstance(x, list):
        return [_bare(v) for v in x]
    return x


def same(a, b):
    """두 답의 판정이 같은가 — 풀이 글(LOOSE)은 빼고, 목록은 차례 없이 견준다."""
    def norm(x):
        x = _bare(x)
        if isinstance(x, dict):
            return {k: norm(v) for k, v in x.items()}
        if isinstance(x, list):
            return sorted((norm(v) for v in x), key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
        return x
    return norm(a) == norm(b)


def ask(schema, prompt, what, models, *, timeout=600.0, effort=None, default_model=None, check=None, consult=None, same_fn=same, on=None, images=None, single_timeout=None):
    """→ {"got": llm.call 꼴의 답(모두 실패면 data None · error), "rec": 자리마다 기록 [{slot, model, backend, ms, costUsd, ok, error}] (한 모델이면 []), "drafts": [{slot, model, data, got}]}.
    models = 모델 자리들(None = 평소 모델) · default_model = None 자리에 넘길 코드의 모델(없으면 서버 기본) · check(data) = 답의 꼴 검사(예외 = 그 모델의 실패) ·
    consult(prompt, drafts) → 협의 프롬프트(없으면 consult_prompt) · same_fn(a, b) = 두 답이 같으면 협의를 건너뛴다(None = 늘 협의) · on(kind, value) = 진행 알림("llms" 자리 상태 · "consult" 상태)."""
    extra = {"images": images} if images else {}
    tell = on or (lambda kind, value: None)
    models = list(models or ())

    def call(slot, model, content, name, t):
        kw = dict(extra, timeout=t, effort=effort)
        if model is None:   # 평소 모델 — 자리 이름은 결과에만 붙인다(slot 을 넘기면 준 모델이 끝 값이 되어 서버 설정 · 사람이 정한 model 을 건너뛴다)
            kw.update(model=default_model)
        else:
            kw.update(model=model, slot=slot)
        got = llm.call(schema, content, name, **kw)   # 호출 이름(name)은 부르는 쪽의 것 — 등록은 그쪽 에이전트(tests/test_agents.py 가 코드의 호출 이름을 훑는다: 이 줄에 글 상수를 두지 않는다)
        return {**got, "slot": slot}

    if len(models) <= 1:
        got = call("LLM1", models[0], prompt, what, single_timeout or timeout) if models else llm.call(schema, prompt, what, timeout=single_timeout or timeout, effort=effort, model=default_model, **extra)
        return {"got": got, "rec": [], "drafts": []}
    slots = [(f"LLM{i + 1}", m) for i, m in enumerate(models)]
    tell("llms", [{"slot": sl, "model": m, "state": "running"} for sl, m in slots])
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(slots), thread_name_prefix="llm-duo") as ex:
        outs = list(ex.map(agent_notes.carry(lambda sm: call(sm[0], sm[1], prompt, what, timeout)), slots))   # carry = 지금 워크플로우 · 계정 맥락을 일꾼 스레드로
    rec, drafts = [], []
    for (sl, m), got in zip(slots, outs):
        ok, err = got.get("data") is not None, got.get("error")
        if ok and check is not None:
            try:
                check(got["data"])
            except Exception as e:   # noqa: BLE001 — 꼴이 틀린 답은 그 모델의 실패로
                ok, err = False, f"답의 꼴: {e}"[:200]
        rec.append({"slot": sl, "model": m or got.get("model"), "backend": got.get("backend"), "ms": got.get("ms"), "costUsd": got.get("costUsd"), "ok": ok,
                    "error": None if ok else (err or "까닭 모름")[:200]})
        if ok:
            drafts.append({"slot": sl, "model": m or got.get("model"), "data": got["data"], "got": got})
    tell("llms", [{**r, "state": "done" if r["ok"] else "failed"} for r in rec])
    if not drafts:
        err = "모든 모델이 답하지 못했습니다(" + " · ".join(f"{r['slot']} {r['error']}" for r in rec) + ")"
        head_err = outs[0].get("error")
        return {"got": {**outs[0], "data": None, "error": head_err if head_err in ("off", "busy") else err}, "rec": rec, "drafts": []}   # LLM1 이 꺼짐 · 자리 없음이면 그 까닭 그대로(부르는 쪽이 off · busy 를 가른다 — llm.ask_all 은 그것을 다시 부르지 않는다)
    if len(drafts) == 1:
        rec.append({"slot": CONSULT_SLOT, "model": None, "ok": False, "error": f"{drafts[0]['slot']} 만 답해 협의 없이 그 답을 씀"})
        return {"got": drafts[0]["got"], "rec": rec, "drafts": drafts}
    if same_fn is not None and all(same_fn(drafts[0]["data"], d["data"]) for d in drafts[1:]):
        rec.append({"slot": CONSULT_SLOT, "model": None, "ok": False, "error": "답이 같아 협의 없이 LLM1 의 답을 씀", "same": True})
        return {"got": drafts[0]["got"], "rec": rec, "drafts": drafts}
    tell("consult", "running")
    head = models[0]
    text = (consult or consult_prompt)(prompt, drafts)
    got = call(CONSULT_SLOT, head, text, f"{what}#consult", timeout)
    ok = got.get("data") is not None
    if ok and check is not None:
        try:
            check(got["data"])
        except Exception as e:   # noqa: BLE001
            ok, got = False, {**got, "error": f"답의 꼴: {e}"[:200]}
    rec.append({"slot": CONSULT_SLOT, "model": head or got.get("model"), "backend": got.get("backend"), "ms": got.get("ms"), "costUsd": got.get("costUsd"), "ok": ok,
                "error": None if ok else (got.get("error") or "까닭 모름")[:200]})
    tell("consult", "done" if ok else "failed")
    return {"got": got if ok else drafts[0]["got"], "rec": rec, "drafts": drafts}


def job(j, models):
    """`llm.ask_all` 의 호출 하나(j = {schema, content, what, timeout?, effort?, model?})를 함께 부른다 → llm.call 꼴의 결과. 비용 · 시간은 자리 모두의 것을 더하고(시간은 같이 돈 자리 가운데 긴 것 + 협의),
    `duo` = 자리마다 기록 + 그 자리의 답(response) — 호출 기록(heading_llm._call_record)에 남는다."""
    out = ask(j["schema"], j["content"], j.get("what", "llm"), models, timeout=j.get("timeout", 180.0), effort=j.get("effort"), default_model=j.get("model"))
    got, rec = dict(out["got"]), out["rec"]
    if not rec:
        return got
    by = {d["slot"]: d["data"] for d in out["drafts"]}
    asked = [r for r in rec if r["slot"] != CONSULT_SLOT]
    talk = [r for r in rec if r["slot"] == CONSULT_SLOT and r.get("ms") is not None]
    costs = [r["costUsd"] for r in rec if r.get("costUsd") is not None]
    got.update(ms=max((r.get("ms") or 0 for r in asked), default=0) + sum(r.get("ms") or 0 for r in talk), costUsd=round(sum(costs), 6) if costs else None,
               duo=[{**r, **({"response": by[r["slot"]]} if r["slot"] in by else {})} for r in rec])
    return got
