"""두 모델이 따로 답하고 협의(app/llm_duo.py — spec_에이전트 ② §8 「함께 부르기 — 공통 함수」 · 2026-11-26 사용자 「2개의 에이전트가 검증보완」 · 「2가지 모델을 같이 사용 … 불가피한 경우 1개만 선택」).
LLM 은 가짜(llm.call) — 부른 차례 · 자리 · 모델을 적는다. 에이전트 설정은 conftest 의 임시 파일(NFM_AGENTS)."""
import pytest

from app import agent_settings, agents, llm, llm_duo

SCHEMA = {"type": "object"}


@pytest.fixture
def calls(monkeypatch):
    log = []

    def fake(schema, content, what, **kw):
        log.append({"what": what, "content": content, **kw})
        model = kw.get("model")
        if model in fake.fail:
            return {"data": None, "backend": None, "ms": 1, "costUsd": None, "error": fake.fail[model], "model": model}
        data = fake.answer(kw.get("slot"), model, content)
        return {"data": data, "backend": "codex" if llm.is_codex(model or "") else "api", "ms": 10, "costUsd": 0.5, "error": None, "model": model or "usual"}
    fake.fail = {}
    fake.answer = lambda slot, model, content: {"changes": [], "summary": f"{slot or '평소'} 의 말"}
    monkeypatch.setattr(llm, "call", fake)
    monkeypatch.delenv("NFM_LLM_BACKEND", raising=False)
    return log, fake


def test_same_ignores_free_text_and_order():
    a = {"changes": [{"id": "n1", "parent": "n0", "reason": "가"}, {"id": "n2", "parent": "n0", "reason": "나"}], "summary": "x"}
    b = {"changes": [{"id": "n2", "parent": "n0", "reason": "다르게 씀"}, {"id": "n1", "parent": "n0", "reason": ""}], "summary": "y"}
    assert llm_duo.same(a, b)
    assert not llm_duo.same(a, {**b, "changes": b["changes"][:1]})
    assert not llm_duo.same(a, {"changes": [{"id": "n1", "parent": "n9", "reason": "가"}, a["changes"][1]], "summary": "x"})


def test_same_keeps_the_order_only_for_the_ordered_keys():
    """차례가 뜻인 목록(작성 지침 보완의 템플릿 `levels`: 위 레벨 → 아래 레벨)은 ordered 로 준 키만 차례까지 견준다 — 기본은 전과 같이 차례 없이(astra 2026-11-27 P1-6: 전에는 레터의 차례가 뒤바뀐 두 답을 같다고 봤다)."""
    a = {"templates": [{"id": "new", "new": {"name": "기호", "levels": ["□", "o", "-"]}}, {"id": "rnd.main"}], "decisions": [{"place": "h1"}, {"place": "h2"}]}
    b = {"templates": [{"id": "rnd.main"}, {"id": "new", "new": {"name": "기호", "levels": ["o", "□", "-"]}}], "decisions": [{"place": "h2"}, {"place": "h1"}]}
    assert llm_duo.same(a, b)   # 기본 — 목록은 차례 없이(다른 에이전트의 견줌은 그대로)
    assert not llm_duo.same(a, b, ordered=("levels",))
    c = {**b, "templates": [{"id": "rnd.main"}, {"id": "new", "new": {"name": "기호", "levels": ["□", "o", "-"]}}]}
    assert llm_duo.same(a, c, ordered=("levels",))   # levels 가 같으면 그 밖의 목록(templates · decisions)의 차례는 여전히 안 본다


def test_ask_consults_when_only_an_ordered_list_differs(calls):
    log, fake = calls
    fake.answer = lambda slot, model, content: {"templates": [{"levels": ["o", "□"] if slot == "LLM2" else ["□", "o"]}]}
    out = llm_duo.ask(SCHEMA, "P", "writing-guidance", ["claude-fable-5-2", "gpt-6-astra"])
    assert len(log) == 2 and out["rec"][2]["same"] is True   # 기본 — 차례만 다른 목록은 같은 답
    log.clear()
    out = llm_duo.ask(SCHEMA, "P", "writing-guidance", ["claude-fable-5-2", "gpt-6-astra"], ordered=("levels",))
    assert [c["what"] for c in log].count("writing-guidance#consult") == 1 and len(log) == 3 and out["rec"][2]["ok"] is True   # 차례가 뜻인 키를 주면 다른 답 — 협의한다


def test_two_models_same_answer_skip_consult(calls):
    log, _ = calls
    out = llm_duo.ask(SCHEMA, "P", "heading_section#1", [None, "gpt-6-astra"], effort="medium")
    assert {(c.get("slot"), c.get("model")) for c in log} == {(None, None), ("LLM2", "gpt-6-astra")} and len(log) == 2   # LLM1 의 None = 평소 모델(자리 이름 없이 불러 서버 설정 · 사람이 정한 model 이 그대로 먹는다)
    assert out["got"]["slot"] == "LLM1" and out["got"]["data"]["summary"] == "평소 의 말"
    assert [r["slot"] for r in out["rec"]] == ["LLM1", "LLM2", "협의"] and out["rec"][2]["same"] is True and len(out["drafts"]) == 2


def test_two_models_differ_then_consult_by_llm1(calls):
    log, fake = calls
    fake.answer = lambda slot, model, content: {"changes": [{"id": slot or "협의?", "parent": "root"}], "summary": ""}
    out = llm_duo.ask(SCHEMA, "P", "heading_section#2", ["claude-fable-5-2", "gpt-6-astra"])
    assert [(c["slot"], c["model"], c["what"]) for c in log[2:]] == [("협의", "claude-fable-5-2", "heading_section#2#consult")]
    assert "### LLM1 (claude-fable-5-2)" in log[2]["content"] and "### LLM2 (gpt-6-astra)" in log[2]["content"] and log[2]["content"].startswith("P")
    assert out["got"]["data"]["changes"][0]["id"] == "협의" and [r["ok"] for r in out["rec"]] == [True, True, True]
    assert agent_settings.agent_of("heading_section#2#consult") == "heading_section"   # 협의 호출도 그 에이전트의 것(덧붙이는 글 · 실행 기록)


def test_one_model_fails_keeps_the_other(calls):
    log, fake = calls
    fake.fail = {"gpt-6-astra": "codex 없음"}
    out = llm_duo.ask(SCHEMA, "P", "heading_tables#1", ["claude-fable-5-2", "gpt-6-astra"])
    assert len(log) == 2 and out["got"]["data"] is not None and out["got"]["slot"] == "LLM1"
    assert out["rec"][1]["ok"] is False and out["rec"][2]["error"].startswith("LLM1 만 답해")


def test_all_fail_and_off_passthrough(calls):
    _, fake = calls
    fake.fail = {"claude-fable-5-2": "boom", "gpt-6-astra": "boom2"}
    got = llm_duo.ask(SCHEMA, "P", "heading_tables#1", ["claude-fable-5-2", "gpt-6-astra"])["got"]
    assert got["data"] is None and got["error"].startswith("모든 모델이 답하지 못했습니다")
    fake.fail = {"claude-fable-5-2": "off", "gpt-6-astra": "codex 없음"}
    assert llm_duo.ask(SCHEMA, "P", "heading_tables#1", ["claude-fable-5-2", "gpt-6-astra"])["got"]["error"] == "off"   # LLM1 이 꺼짐이면 그 까닭 그대로(ask_all 이 다시 부르지 않는다)


def test_bad_shape_is_that_models_failure(calls):
    _, fake = calls
    fake.answer = lambda slot, model, content: {"ok": slot != "LLM2"}

    def check(d):
        if not d["ok"]:
            raise ValueError("꼴")
    out = llm_duo.ask(SCHEMA, "P", "writing-guidance", ["claude-fable-5-2", "gpt-6-astra"], check=check)
    assert out["rec"][1]["ok"] is False and out["rec"][1]["error"].startswith("답의 꼴") and out["got"]["slot"] == "LLM1"


def test_single_model_is_one_call(calls):
    log, _ = calls
    out = llm_duo.ask(SCHEMA, "P", "writing-guidance", ["claude-opus-5-5"], default_model="claude-fable-5-2")
    assert len(log) == 1 and (log[0]["slot"], log[0]["model"]) == ("LLM1", "claude-opus-5-5") and out["rec"] == [] and out["drafts"] == []
    log.clear()
    llm_duo.ask(SCHEMA, "P", "x", [], default_model="claude-fable-5-2")
    assert len(log) == 1 and "slot" not in log[0] and log[0]["model"] == "claude-fable-5-2"


def test_ask_all_calls_both_models_for_duo_agents_only(calls, monkeypatch):
    log, fake = calls
    monkeypatch.setitem(agent_settings.LLMS, "heading_types", (None, agent_settings.LLM2))   # 길 시험 — 헤딩 판정은 기본이 한 모델(2026-11-26 「작성지침 내용만」)이라 여기서만 두 모델로 연다
    fake.answer = lambda slot, model, content: {"v": "협의" if "두 검토자의 답" in content else slot or "LLM1"}   # LLM1 이 평소 모델이면 협의도 자리 이름 없이 부른다 — 글로 가른다
    jobs =[{"schema": SCHEMA, "content": "A", "what": "heading_types"}, {"schema": SCHEMA, "content": "B", "what": "tpl-agent"}]
    a, b = llm.ask_all(jobs)
    assert [r["slot"] for r in a["duo"]] == ["LLM1", "LLM2", "협의"] and a["duo"][0]["response"] == {"v": "LLM1"} and a["duo"][1]["response"] == {"v": "LLM2"}   # 두 모델의 답을 협의한 답과 따로 남긴다
    assert a["costUsd"] == 1.5 and a["data"] == {"v": "협의"} and "duo" not in b
    assert sorted(c["what"] for c in log) == ["heading_types", "heading_types", "heading_types#consult", "tpl-agent"]


def test_ask_all_one_model_setting_and_off(calls, monkeypatch):
    log, _ = calls
    monkeypatch.setitem(agent_settings.LLMS, "heading_types", (None, agent_settings.LLM2))
    agent_settings.save("heading_types", {"models": ["claude-opus-5-5"]})   # 「한 모델만」 — 기본 두 모델로 되돌아가지 않는다
    assert agent_settings.duo("heading_types") == ["claude-opus-5-5"]
    out = llm.ask_all([{"schema": SCHEMA, "content": "A", "what": "heading_types"}])[0]
    assert len(log) == 1 and (log[0]["slot"], log[0]["model"]) == ("LLM1", "claude-opus-5-5") and "duo" not in out
    agent_settings.save("heading_types", {"models": None})   # 지우면 기본(두 모델)
    assert agent_settings.duo("heading_types") == [None, "gpt-6-astra"]
    log.clear()
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")   # LLM 을 끈 서버 — 둘째 모델(Codex)도 부르지 않는다
    llm.ask_all([{"schema": SCHEMA, "content": "A", "what": "heading_types"}])
    assert len(log) == 1 and "slot" not in log[0]


def test_registry_matches_settings_and_one_model_listing():
    assert {a["id"]: tuple(a["llms"]) for a in agents.AGENTS if a.get("llms")} == {k: tuple(v) for k, v in agent_settings.LLMS.items()}
    assert {"writing_guidance", "form_review"} == set(agent_settings.LLMS)   # 04 의 두 모델은 작성 지침 보완만(2026-11-26 사용자 「작성지침 내용만 넣어줘」) — 헤딩 · 표 판정은 한 모델
    assert all(not agents.BY_ID[x].get("llms") for x in ("heading_rules", "heading_types", "heading_section", "heading_tables"))
    a = agents.BY_ID["writing_guidance"]
    two = agents.llms_of(a)
    assert [x["slot"] for x in two] == ["LLM1", "LLM2"] and two[1]["model"] == "gpt-6-astra" and two[0]["model"] == agents.model_of(a)["id"] and all(x["multi"] for x in two)
    agent_settings.save("writing_guidance", {"models": [two[0]["model"]]})
    one = agents.llms_of(a)
    assert [x["slot"] for x in one] == ["LLM1"] and one[0]["multi"] is True
    assert agents.llms_default(a)[1] == "gpt-6-astra" and len(agents.llms_default(agents.BY_ID["doc_agent"])) == 0   # 칩의 「두 모델로」 가 채울 자리
    brief = next(x for x in agents.listing()["agents"] if x["id"] == "writing_guidance")
    assert len(brief["llms"]) == 1 and len(brief["llmsDefault"]) == 2
