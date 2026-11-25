"""app/llm_keys.py — fable 스킬의 키들을 차례대로 · 키 탓 실패면 다음 키로(2026-11-25 사용자 "fable 키를 사용할 수 있도록 해줘")."""
import json

import pytest

from app import llm, llm_keys


class _Err(Exception):
    def __init__(self, status, text=""):
        super().__init__(text)
        self.status_code = status


@pytest.fixture
def fable(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"keys": [{"key": "sk-ant-aaaa1111", "name": "", "saved": ""},
                                        {"key": "sk-ant-bbbb2222", "name": "", "saved": ""}]}), encoding="utf-8")
    monkeypatch.setenv("NFM_LLM_KEYS", "fable")
    monkeypatch.setenv("FABLE_CONFIG", str(cfg))
    monkeypatch.delenv("FABLE_API_KEY", raising=False)
    monkeypatch.setattr(llm_keys, "_REST", {})
    return cfg


def test_reads_fable_keys_in_order(fable, monkeypatch):
    assert llm_keys.keys() == ["sk-ant-aaaa1111", "sk-ant-bbbb2222"]
    monkeypatch.setenv("FABLE_API_KEY", "sk-ant-envv0000")
    assert llm_keys.keys()[0] == "sk-ant-envv0000"


def test_env_source_unchanged(monkeypatch):
    monkeypatch.delenv("NFM_LLM_KEYS", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert llm_keys.keys() == ["sk-x"]


@pytest.mark.parametrize("err,reason", [(_Err(401), "키 거절"), (_Err(403), "권한 없음"), (_Err(429), "사용 한도"),
                                        (_Err(400, "Your credit balance is too low"), "크레딧 부족")])
def test_key_failure_moves_to_next(fable, monkeypatch, err, reason):
    used = []

    def one(cfg, schema, content, timeout, key, max_tokens=32000, images=None):
        used.append(key)
        if key.endswith("1111"):
            raise err
        return {"ok": True}, None

    monkeypatch.setattr(llm, "_api_one", one)
    assert llm._api({"model": "m"}, {}, "x", 5) == ({"ok": True}, None)
    assert used == ["sk-ant-aaaa1111", "sk-ant-bbbb2222"]
    assert llm_keys.keys()[0] == "sk-ant-bbbb2222"  # 실패한 키는 뒤로
    assert llm_keys.view()["resting"][0]["reason"] == reason


def test_other_errors_do_not_rotate(fable, monkeypatch):
    def one(cfg, schema, content, timeout, key, max_tokens=32000, images=None):
        raise _Err(529, "overloaded")

    monkeypatch.setattr(llm, "_api_one", one)
    with pytest.raises(_Err):
        llm._api({"model": "m"}, {}, "x", 5)
    assert llm_keys.view()["resting"] == []


def test_all_keys_fail(fable, monkeypatch):
    monkeypatch.setattr(llm, "_api_one", lambda *a, **k: (_ for _ in ()).throw(_Err(401)))
    with pytest.raises(RuntimeError, match="쓸 수 있는 키가 없습니다"):
        llm._api({"model": "m"}, {}, "x", 5)


def test_view_has_no_key_text(fable):
    s = json.dumps(llm_keys.view())
    assert "aaaa1111" not in s and llm_keys.view()["n"] == 2
