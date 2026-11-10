"""LLM 관문(app/llm.py) — Claude Agent SDK 길. 실제 모델은 부르지 않는다: claude_agent_sdk.query 를 가짜로 바꾼다."""
import asyncio
from pathlib import Path

import pytest

import claude_agent_sdk
from claude_agent_sdk import ResultMessage

from app import llm

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def _result(**kw):
    base = dict(subtype="success", duration_ms=10, duration_api_ms=8, is_error=False, num_turns=1, session_id="s",
                total_cost_usd=0.0123, structured_output={"ok": True})
    return ResultMessage(**{**base, **kw})


@pytest.fixture
def fake_sdk(monkeypatch):
    """가짜 query — 받은 (prompt, options) 를 남기고 정한 메시지들을 낸다."""
    seen = {}

    def install(*msgs, delay=0.0, raise_exc=None):
        async def query(*, prompt, options=None, transport=None):
            seen.update(prompt=prompt, options=options)
            if delay:
                await asyncio.sleep(delay)
            for m in msgs:
                yield m
            if raise_exc:
                raise raise_exc
        monkeypatch.setattr(claude_agent_sdk, "query", query)
        return seen
    monkeypatch.setenv("NFM_LLM_BACKEND", "sdk")
    llm.reset_slots()
    return install


def test_auto_tries_sdk_first(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "auto")
    monkeypatch.setattr(llm, "cli_path", lambda cfg=None: r"C:\x\claude.exe")
    monkeypatch.setattr(llm, "_has_key", lambda: True)
    assert llm._tries(llm.settings()) == ["sdk", "cli", "api"]
    st = llm.status()
    assert st["active"] == "sdk" and st["sdk"] == claude_agent_sdk.__version__
    monkeypatch.setenv("NFM_LLM_BACKEND", "sdk")
    assert llm._tries(llm.settings()) == ["sdk"]


def test_sdk_call_options_and_result(fake_sdk):
    seen = fake_sdk(_result())
    out = llm.call(SCHEMA, "프롬프트 본문", "시험", effort="medium")
    assert out["data"] == {"ok": True} and out["backend"] == "sdk" and out["costUsd"] == 0.0123 and out["error"] is None
    o = seen["options"]
    assert seen["prompt"] == "프롬프트 본문"
    assert o.model == "claude-opus-5-5" and o.effort == "medium"
    assert o.tools == [] and o.setting_sources == []  # 도구 없음 · 사용자·프로젝트 설정(CLAUDE.md) 안 읽음
    assert o.output_format == {"type": "json_schema", "schema": SCHEMA}
    assert "no-session-persistence" in o.extra_args
    cwd = Path(o.cwd)
    assert "nfm-llm-" in cwd.name and not cwd.exists()  # 빈 임시 폴더 — 끝나면 지움
    assert Path(__file__).parents[1] not in cwd.parents


@pytest.mark.parametrize("res", [
    _result(subtype="error_max_structured_output_retries", is_error=True, structured_output=None, errors=["검증 실패"]),
    _result(stop_reason="refusal", is_error=True, structured_output=None),
    _result(structured_output=None),  # success 인데 구조화 출력 없음
])
def test_sdk_bad_result_is_error_not_data(fake_sdk, res):
    fake_sdk(res)
    out = llm.call(SCHEMA, "x", "시험")
    assert out["data"] is None and out["error"].startswith("sdk:")


def test_sdk_falls_back_to_cli_in_auto(fake_sdk, monkeypatch):
    fake_sdk(raise_exc=claude_agent_sdk.CLIConnectionError("연결 안 됨"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "auto")
    monkeypatch.setattr(llm, "cli_path", lambda cfg=None: r"C:\x\claude.exe")
    monkeypatch.setattr(llm, "_has_key", lambda: False)
    monkeypatch.setattr(llm, "_cli", lambda cfg, schema, content, timeout: ({"ok": False}, 0.01))
    out = llm.call(SCHEMA, "x", "시험")
    assert out["backend"] == "cli" and out["data"] == {"ok": False}


def test_sdk_timeout(fake_sdk):
    fake_sdk(_result(), delay=5.0)
    out = llm.call(SCHEMA, "x", "시험", timeout=0.2)
    assert out["data"] is None and "시간 초과" in out["error"]


def test_sdk_from_worker_threads(fake_sdk):
    """ask_all 은 스레드마다 asyncio.run — 이벤트 루프가 겹치지 않는다."""
    fake_sdk(_result())
    outs = llm.ask_all([{"schema": SCHEMA, "content": f"{i}", "what": f"t#{i}"} for i in range(6)], workers=3)
    assert [o["backend"] for o in outs] == ["sdk"] * 6 and all(o["data"] == {"ok": True} for o in outs)
