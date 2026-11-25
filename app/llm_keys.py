"""LLM 의 API 키 — `api` 길이 쓸 키들(차례대로 · 쓸 수 없는 키는 잠시 뒤로).

2026-11-25 사용자 "fable 키를 사용할 수 있도록 해줘": 구독의 Fable 사용 한도(429) 때문에 8114 가 Opus 5.5(CLI)로 돌던 것을, fable 스킬에 등록한 API 키들로 Fable 을 부르게 한다.
- env `NFM_LLM_KEYS=fable` 이면 fable 스킬의 키 목록(`FABLE_CONFIG` 또는 ~/.claude/fable/config.json 의 keys — 스킬의 꼴 그대로 · env `FABLE_API_KEY` 가 맨 앞)을 읽는다.
  아니면 전처럼 env ANTHROPIC_API_KEY · ANTHROPIC_AUTH_TOKEN 하나(이 모듈을 안 거친 것과 같은 동작).
- 키 글은 env · 명령 줄 · 기록에 남기지 않는다(띄우개는 이 설정만 건다) — 로그에는 끝 네 글자만.
- 키 탓 실패(키 거절 401 · 권한 403 · 사용 한도 429 · 크레딧 부족)는 그 키를 잠시 뒤로 미루고 다음 키로 넘어간다(스킬과 같은 기준 · 미룸은 이 프로세스의 메모리에만 —
  스킬의 key_state.json 은 안 고친다). 과부하 · 서버 오류 · 연결 오류는 키 탓이 아니라 넘어가지 않는다.
"""
import json
import os
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()
_REST = {}   # 키 끝 12자 → (까닭, 쉬는 끝 시각)
REST_S = {"키 거절": 24 * 3600, "권한 없음": 24 * 3600, "크레딧 부족": 3600, "사용 한도": 60}


def source():
    return "fable" if os.environ.get("NFM_LLM_KEYS", "").strip().lower() == "fable" else "env"


def _fable_config():
    p = os.environ.get("FABLE_CONFIG", "").strip()
    return Path(p) if p else Path.home() / ".claude" / "fable" / "config.json"


def _fable_keys():
    keys = []
    k = os.environ.get("FABLE_API_KEY", "").strip()
    if k:
        keys.append(k)
    try:
        cfg = json.loads(_fable_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    for item in cfg.get("keys") or ([{"key": cfg["api_key"]}] if cfg.get("api_key") else []):
        k = str((item or {}).get("key") or "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def keys():
    """쓸 차례의 키 목록 — 쉬는 키는 뒤로(모두 쉬면 그래도 차례대로 해 본다)."""
    if source() == "fable":
        ks = _fable_keys()
    else:
        k = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        return [k] if k else []
    now = time.time()
    with _LOCK:
        ok = [k for k in ks if _REST.get(k[-12:], ("", 0))[1] <= now]
    return ok + [k for k in ks if k not in ok]


def tail(k):
    return "…" + k[-4:]


def why(e):
    """예외가 키 탓이면 까닭 글, 아니면 None."""
    status = getattr(e, "status_code", None)
    text = str(e)
    if status == 401:
        return "키 거절"
    if status == 403:
        return "권한 없음"
    if status == 429:
        return "사용 한도"
    if status == 400 and "credit balance" in text.lower():
        return "크레딧 부족"
    return None


def rest(k, reason):
    with _LOCK:
        _REST[k[-12:]] = (reason, time.time() + REST_S.get(reason, 60))


def ok(k):
    with _LOCK:
        _REST.pop(k[-12:], None)


def view():
    """화면 · 상태용 {source, n, resting: [{key: "…abcd", reason, left}]} — 키 글은 안 싣는다."""
    ks = keys()
    now = time.time()
    with _LOCK:
        resting = [{"key": tail(k), "reason": _REST[k[-12:]][0], "left": round(_REST[k[-12:]][1] - now)}
                   for k in ks if _REST.get(k[-12:], ("", 0))[1] > now]
    return {"source": source(), "n": len(ks), "resting": resting}
