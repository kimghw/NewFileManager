"""양식 검토 — 모델 여럿(LLM1 · LLM2)이 따로 검토하고 협의(2026-11-25 사용자 「claude fable, 하고 codex astra 모두 추출해서 협의」 · 「LLM1, LLM2 … 클릭 해서 모델을 선택」)."""
import pytest

from app import agent_settings, agents, form_review, form_review_api, llm


def _ans(q="범위?"):
    return {"summary": "s", "sees": {"write": "w", "guides": "g", "request": "r"} if "sees" in form_review.SCHEMA["properties"] else None,
            "places": [], "topics": [], "questions": [{"text": q, "why": "", "places": [], "choices": [], "suggest": "", "source": ""}]}


def _valid(q="범위?"):
    a = _ans(q)
    return {k: v for k, v in a.items() if k in form_review.SCHEMA["properties"] and v is not None} | {
        k: ("" if form_review.SCHEMA["properties"][k].get("type") == "string" else []) for k in form_review.SCHEMA["properties"] if k not in a or a[k] is None}


@pytest.fixture
def calls(monkeypatch):
    log = []

    def fake(schema, content, what, **kw):
        log.append({"what": what, **kw, "content": content})
        fail = kw.get("model") in fake.fail
        return {"data": None if fail else _valid(kw.get("slot") or "?"), "backend": "codex" if llm.is_codex(kw.get("model") or "") else "api", "ms": 1,
                "error": "boom" if fail else None, "model": kw.get("model")}
    fake.fail = set()
    monkeypatch.setattr(form_review_api.llm, "call", fake)
    monkeypatch.setattr(form_review_api.form_review, "check", lambda d, *a: d)
    monkeypatch.setenv("NFM_AGENTS", "off")
    agent_settings._MEMORY.update(version=0, agents={})
    return log, fake


def test_default_is_one_model_consult_is_an_option(calls):
    """2026-11-27 사용자 「양식 검토의 두 모델 협의 는 옵션으로 둘 수 있고」 — 기본은 한 모델(LLM1) · 켜면 두 모델 + 협의(spec_양식작성 ② §5-12 1)."""
    log, _ = calls
    got, rec = form_review_api._ask("P", [], False, {})
    assert [c["model"] for c in log] == ["claude-fable-5-2"] and rec == [] and got["data"]["questions"][0]["text"] == "LLM1"
    agent_settings.save("form_review", {"models": ["claude-opus-5-5"]})   # 둘째 모델이 설정에 없으면 켜도 한 번
    log.clear()
    got, rec = form_review_api._ask("P", [], False, {}, duo=True)
    assert [c["model"] for c in log] == ["claude-opus-5-5"] and rec == []


def test_two_models_then_consult(calls):
    log, _ = calls
    got, rec = form_review_api._ask("P", [], False, {}, duo=True)
    assert [(c["slot"], c["model"]) for c in log] == [("LLM1", "claude-fable-5-2"), ("LLM2", "gpt-6-astra"), ("협의", "claude-fable-5-2")]
    assert "LLM1 (claude-fable-5-2)" in log[2]["content"] and "LLM2 (gpt-6-astra)" in log[2]["content"]
    assert got["data"]["questions"][0]["text"] == "협의"
    assert [r["slot"] for r in rec] == ["LLM1", "LLM2", "협의"] and all(r["ok"] for r in rec)


def test_one_fails_uses_other_without_consult(calls):
    log, fake = calls
    fake.fail = {"gpt-6-astra"}
    got, rec = form_review_api._ask("P", [], False, {}, duo=True)
    assert got["data"]["questions"][0]["text"] == "LLM1" and len(log) == 2
    assert rec[1]["ok"] is False and rec[-1]["slot"] == "협의" and rec[-1]["ok"] is False


def test_all_fail_raises(calls):
    _, fake = calls
    fake.fail = {"claude-fable-5-2", "gpt-6-astra"}
    with pytest.raises(RuntimeError, match="모든 모델"):
        form_review_api._ask("P", [], False, {}, duo=True)


def test_single_model_setting_is_one_call(calls):
    log, _ = calls
    agent_settings.save("form_review", {"models": ["claude-opus-5-5"]})
    got, rec = form_review_api._ask("P", [], False, {})
    assert len(log) == 1 and log[0]["model"] == "claude-opus-5-5" and rec == []


def test_registry_default_matches_code():
    assert tuple(agents.BY_ID["form_review"]["llms"]) == form_review.LLMS


def test_llms_listing_and_models_setting(monkeypatch):
    monkeypatch.setenv("NFM_AGENTS", "off")
    agent_settings._MEMORY.update(version=0, agents={})
    a = agents.BY_ID["form_review"]
    assert [x["slot"] for x in agents.llms_of(a)] == ["LLM1", "LLM2"] and agents.llms_of(a)[1]["model"] == "gpt-6-astra"
    agent_settings.save("form_review", {"models": ["claude-opus-5-5", "gpt-6-astra", "claude-fable-5-2"]})
    assert [x["model"] for x in agents.llms_of(a)] == ["claude-opus-5-5", "gpt-6-astra", "claude-fable-5-2"]
    one = agents.BY_ID["doc_agent"]
    assert agents.llms_of(one)[0]["slot"] == "LLM1" and agents.llms_of(one)[0]["multi"] is False
    with pytest.raises(ValueError):
        agent_settings.check({"models": ["bad model!"]})


def test_codex_routing(monkeypatch):
    monkeypatch.setattr(llm, "codex_path", lambda: "C:/x/codex.cmd")
    seen = {}

    def fake_codex(cfg, schema, content, timeout, images=None):
        seen.update(cfg)
        return {"ok": True}, None
    monkeypatch.setattr(llm, "_codex", fake_codex)
    monkeypatch.setenv("NFM_LLM_MODEL_FORCE", "claude-fable-5-2")
    out = llm.call({"type": "object"}, "x", "form-review", model="gpt-6-astra", slot="LLM2")
    assert out["backend"] == "codex" and seen["model"] == "gpt-6-astra" and out["slot"] == "LLM2"
    monkeypatch.setattr(llm, "codex_path", lambda: None)
    assert llm.call({"type": "object"}, "x", "form-review", model="gpt-6-astra", slot="LLM2")["error"] == "codex 없음"
