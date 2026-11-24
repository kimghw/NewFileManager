"""Claude Code CLI 헤드리스 한 번(spec_양식작성 ② §3) — 문서 라이브러리 서버의 LLM 관문. `app/llm.py` 를 가져오지 않는다(따로 선 서버 — 8114 의 에이전트 설정 · 덧붙이는 글과 무관).

- `run(prompt, schema, cwd=, tools=("Read",), images=())` → {"data": dict | None, "error", "ms", "costUsd", "model", "turns", "reads"}. 예외를 내지 않는다.
  - tools 가 있으면 그 도구만 준다(`--tools Read --allowedTools Read` — 물어야 하는 것은 자동 거절 `--permission-prompts none`). cwd = 읽을 파일을 둔 **임시 폴더**(CLAUDE.md 가 없는 곳 — 설정도 안 읽는다 `--setting-sources ""`).
  - images = 글 앞에 실을 그림들 [{data: bytes, media}] — stream-json 입력(도구 없이 그림을 바로 보일 때: 수식 캡처 → LaTeX).
  - 구조화 출력(`--json-schema`) — 결과 줄(type: result)의 `structured_output`. 2026-11-24 실측: Opus 5.5 · Read 로 PDF 4쪽 → 33초 · 도구 Read 1번(references/Claude_CLI_헤드리스.md 「Read 도구로 PDF 읽기」).
- 모델 = env NFM_DOCLIB_MODEL | `MODEL`(claude-opus-5-5 — 사용자 "claude opus 최신모델을 이용해서 read 도구 이용해서"). 실행 파일 = env NFM_CLAUDE_CLI | PATH 의 claude.
- 청구: 자식 env 에서 ANTHROPIC_API_KEY · ANTHROPIC_AUTH_TOKEN 과 부른 세션에 묶인 CLAUDE* 를 뺀다(구독 로그인으로 — 8114 의 띄우개와 같은 까닭).
- 동시 실행 = env NFM_DOCLIB_SLOTS(기본 3) 자리."""
import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_MODEL_RE = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}")
_SLOTS = None
_GUARD = threading.Lock()


def model():
    m = os.environ.get("NFM_DOCLIB_MODEL", "").strip()
    return m if m and _MODEL_RE.fullmatch(m) else MODEL


def cli():
    """CLI 실행 파일 절대 경로 | None."""
    cand = os.environ.get("NFM_CLAUDE_CLI", "").strip() or shutil.which("claude")
    if not cand:
        return None
    p = Path(cand)
    return str(p) if p.is_absolute() and p.is_file() and p.stem.lower() == "claude" else None


def off():
    return os.environ.get("NFM_DOCLIB_LLM", "").strip().lower() == "off"


def status():
    return {"available": bool(cli()) and not off(), "cli": cli(), "model": model(), "slots": slots_n()}


def slots_n():
    try:
        return max(1, int(os.environ.get("NFM_DOCLIB_SLOTS") or 3))
    except ValueError:
        return 3


def _slots():
    global _SLOTS
    with _GUARD:
        if _SLOTS is None:
            _SLOTS = threading.BoundedSemaphore(slots_n())
        return _SLOTS


def _env():
    return {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))}


def _why(code, result, stderr, name):
    """실패의 까닭 — 결과 줄의 result 글(사용 한도 429 는 줄여서)."""
    if isinstance(result, dict) and result.get("result"):
        text = " ".join(str(result["result"]).split())
        if result.get("api_error_status") == 429 or re.search(r"reached your .*limit", text, re.I):
            return f"{name} 사용 한도에 닿음(429) — 한도가 풀린 뒤 다시"
        return f"{result.get('api_error_status') or f'exit {code}'}: {text[:240]}"
    return f"exit {code}: {(stderr or '')[-300:]}"


def run(prompt, schema, *, cwd, tools=("Read",), images=(), effort="medium", timeout=900.0, stop=None):
    """한 번 부른다 → {"data", "error", "ms", "costUsd", "model", "turns", "reads"}. stop = threading.Event(멈춤 — 도는 CLI 를 끊는다)."""
    name = model()
    out = {"data": None, "error": None, "ms": 0, "costUsd": None, "model": name, "turns": 0, "reads": 0}
    exe = cli()
    if off() or not exe:
        out["error"] = "off" if off() else "Claude CLI 실행 파일이 없습니다(NFM_CLAUDE_CLI)"
        return out
    args = [exe, "-p", "--model", name, "--effort", effort if effort in EFFORTS else "medium", "--output-format", "stream-json", "--verbose",
            "--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":")), "--setting-sources", "", "--no-session-persistence", "--permission-prompts", "none"]
    args += ["--tools", ",".join(tools), "--allowedTools", ",".join(tools)] if tools else ["--tools", ""]
    if images:
        args += ["--input-format", "stream-json"]
        blocks = [{"type": "image", "source": {"type": "base64", "media_type": im.get("media") or "image/png", "data": base64.b64encode(im["data"]).decode("ascii")}} for im in images]
        feed = json.dumps({"type": "user", "session_id": "", "parent_tool_use_id": None, "message": {"role": "user", "content": blocks + [{"type": "text", "text": prompt}]}}, ensure_ascii=False) + "\n"
    else:
        feed = prompt
    slots = _slots()
    while not slots.acquire(timeout=1.0):
        if stop is not None and stop.is_set():
            out["error"] = "stopped"
            return out
    t = time.monotonic()
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(cwd), env=_env(),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        box = {}

        def pump():
            try:
                box["out"], box["err"] = proc.communicate(feed)
            except Exception as e:   # noqa: BLE001
                box["err"] = str(e)
        th = threading.Thread(target=pump, daemon=True)
        th.start()
        while th.is_alive():
            th.join(0.5)
            if (stop is not None and stop.is_set()) or time.monotonic() - t > timeout:
                proc.kill()
                th.join(5)
                out["error"] = "stopped" if stop is not None and stop.is_set() else f"시간 초과 {timeout:g}초"
                return out
        result = None
        for ln in (box.get("out") or "").splitlines():
            if '"type"' not in ln:
                continue
            try:
                m = json.loads(ln)
            except ValueError:
                continue
            if m.get("type") == "assistant":
                out["reads"] += sum(1 for c in ((m.get("message") or {}).get("content") or ()) if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Read")
            elif m.get("type") == "result":
                result = m
        if result is None or proc.returncode or result.get("is_error") or not isinstance(result.get("structured_output"), dict):
            out["error"] = _why(proc.returncode, result, box.get("err"), name) if (proc.returncode or result is None or result.get("is_error")) else f"구조화된 답이 없습니다({result.get('subtype')})"
            if result:
                out["costUsd"] = result.get("total_cost_usd")
            return out
        out.update(data=result["structured_output"], costUsd=result.get("total_cost_usd"), turns=result.get("num_turns") or 0)
        return out
    except OSError as e:
        out["error"] = f"CLI 를 띄우지 못했습니다: {e}"
        return out
    finally:
        out["ms"] = round((time.monotonic() - t) * 1000)
        slots.release()
