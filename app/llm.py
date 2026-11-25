"""LLM 관문 — Claude 구조화 출력(JSON schema) 한 번 부르기(spec_헤딩_추출 ② §6).

FileMergeManager `app/llm.py` 의 CLI·SDK 호출부만 옮겨 줄인 것(2026-11-09). 설정 파일·에이전트 등록부·스킬은 안 옮겼다 — LLM 에 줄 지침은
`app/heading_guides.py` 가 맡는다(코드 고정 출력 계약 + 사용자 지침 + 자료).

- 길(2026-11-09 사용자 "claude sdk cli 로 LLM 을 호출"): **Claude Agent SDK 먼저**(`claude_agent_sdk.query` — 패키지에 든 Claude Code CLI 를 SDK 가 띄움,
  도구 없음·설정 안 읽음·빈 임시 폴더·세션 안 남김, `output_format` json_schema → `ResultMessage.structured_output`, references/Claude_Agent_SDK.md),
  안 되면 CLI 헤드리스(`claude -p … --json-schema`, references/Claude_CLI_헤드리스.md), 그다음 Anthropic API SDK(ANTHROPIC_API_KEY·ANTHROPIC_AUTH_TOKEN 이 있을 때만).
  env `NFM_LLM_BACKEND` = auto|sdk|cli|api|off(기본 auto = sdk → cli → api) · `NFM_LLM_MODEL`(기본 claude-opus-5-5) ·
  `NFM_LLM_MODEL_FORCE`(모든 호출의 모델 — 검토마다 코드에 정한 모델(merge_llm.MODEL 등)보다도 먼저. 2026-11-12 사용자 「api 키로 해서 fable로 해줘」) ·
  `NFM_CLAUDE_CLI`(cli 길의 실행 파일 절대 경로 — 없으면 PATH 의 claude. sdk 길은 패키지에 든 CLI).
- 동시 호출: 프로세스 전체 `NFM_LLM_SLOTS`(기본 8 — `SLOTS_DEFAULT`) 자리. Windows 에서 `claude -p` 를 13개 한꺼번에 띄우면 일부가 0xC0000409 로 죽은 실측(FileMergeManager 2026-10-31)이 있어
  처음에는 4 였고, 2026-11-17 다시 재서(8개 × 5바퀴 · 12개 × 2바퀴 모두 성공 — references/Claude_CLI_헤드리스.md) 8 로 올렸다(사용자 "문서가 큰 경우 병렬에이전트를 사용해서" — 큰 문서는 호출이 수십 개라 자리 수가 걸리는 시간을 정한다).
  `ask_all` 은 실패한 것만 병렬 2 로 한 번 더 부른다.
- 예외를 내지 않는다: 결과 = {"data": dict | None, "backend": "sdk"|"cli"|"api"|None, "ms", "costUsd", "error"}."""
import concurrent.futures
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app import agent_notes, agent_settings, llm_keys

log = logging.getLogger(__name__)
BACKENDS = ("auto", "sdk", "cli", "api", "off")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MODEL = "claude-opus-5-5"
# server-side refusal fallback("default" 형) — 받는 모델만(references/Claude_API_구조화출력.md)
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_MODEL_RE = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}")


def _env_num(name, default, cast):
    try:
        return cast(os.environ.get(name) or default)
    except ValueError:
        log.warning("env %s=%r 이 숫자가 아니라 기본값 %s 을 씁니다", name, os.environ.get(name), default)
        return default


def forced():
    """env NFM_LLM_MODEL_FORCE 의 모델 | None — 있으면 모든 호출이 이 모델(호출이 따로 정한 모델보다 먼저)."""
    m = os.environ.get("NFM_LLM_MODEL_FORCE", "").strip()
    return m if m and _MODEL_RE.fullmatch(m) else None


def settings():
    """지금 설정 {backend, model, effort, cli} — env 에서 읽는다(설정 파일 없음)."""
    backend = os.environ.get("NFM_LLM_BACKEND", "auto").strip().lower()
    model = os.environ.get("NFM_LLM_MODEL", "").strip() or DEFAULT_MODEL
    return {"backend": backend if backend in BACKENDS else "auto",
            "model": model if _MODEL_RE.fullmatch(model) else DEFAULT_MODEL,
            "effort": "low", "cli": os.environ.get("NFM_CLAUDE_CLI", "").strip()}


_BAD_CLI = set()


def cli_path(cfg=None):
    """CLI 실행 파일 — 「절대 경로·UNC 아님·있는 파일·이름 claude(확장자 없음·.exe·.cmd)」 일 때만, 아니면 None(FileMergeManager 와 같은 막이)."""
    cfg = cfg or settings()
    cand = cfg["cli"] or shutil.which("claude")
    if not cand:
        return None
    p = Path(cand)
    unc = cand[:2].replace("\\", "/") == "//"
    if unc or not p.is_absolute() or not p.is_file() or p.stem.lower() != "claude" or p.suffix.lower() not in ("", ".exe", ".cmd"):
        if cand not in _BAD_CLI:
            _BAD_CLI.add(cand)
            log.warning("LLM CLI 실행 파일로 쓸 수 없어 CLI 없음으로 봅니다: %s", cand)
        return None
    return cand


def _has_key():
    return bool(llm_keys.keys())  # env NFM_LLM_KEYS=fable 이면 fable 스킬의 키들 · 아니면 env 의 키(app/llm_keys.py)


_SDK = []  # [판 | None] — 한 번만 찾는다(가져오기는 무겁다)


def sdk_version():
    """Claude Agent SDK(claude-agent-sdk) 판 — 설치 안 됐거나 가져오기 실패면 None."""
    if not _SDK:
        try:
            import claude_agent_sdk
            _SDK.append(getattr(claude_agent_sdk, "__version__", "?"))
        except Exception as e:  # 없음·깨진 설치
            log.info("Claude Agent SDK 없음: %s", e)
            _SDK.append(None)
    return _SDK[0]


def _tries(cfg):
    order = {"auto": ("sdk", "cli", "api"), "sdk": ("sdk",), "cli": ("cli",), "api": ("api",), "off": ()}[cfg["backend"]]
    return [b for b in order if (b == "sdk" and sdk_version()) or (b == "cli" and cli_path(cfg)) or (b == "api" and _has_key())]


def status():
    """화면용 {backend, model, sdk, cli, available, active}: active = 먼저 시도할 길(없으면 None), sdk = Agent SDK 판."""
    cfg = settings()
    tries = _tries(cfg)
    return {"backend": cfg["backend"], "model": forced() or cfg["model"], "sdk": sdk_version(), "cli": cli_path(cfg), "available": bool(tries),
            "active": tries[0] if tries else None, "keys": llm_keys.view()}


def _blocks(content, images):
    """메시지 content 목록 — 그림들(base64) 다음에 글(spec_그림 ② §7). images = [{data: bytes, media: "image/png" …}]."""
    import base64
    return [{"type": "image", "source": {"type": "base64", "media_type": im["media"], "data": base64.b64encode(im["data"]).decode("ascii")}}
            for im in images] + [{"type": "text", "text": content}]


def _user_line(content, images):
    """stream-json 입력의 사용자 메시지 하나(CLI stdin · SDK 스트림 공용 — references/Claude_CLI_헤드리스.md 「그림 입력」)."""
    return {"type": "user", "session_id": "", "parent_tool_use_id": None, "message": {"role": "user", "content": _blocks(content, images)}}


def _is_result(line):
    """stream-json 출력의 한 줄이 결과 메시지(type: result)인가."""
    if '"result"' not in line:
        return False
    try:
        return json.loads(line).get("type") == "result"
    except (ValueError, AttributeError):
        return False


def _sdk(cfg, schema, content, timeout, images=None):
    """Claude Agent SDK 한 번 — 도구 없음(구조화 출력용 StructuredOutput 만 CLI 가 붙임)·설정 안 읽음·빈 임시 폴더·세션 안 남김.
    프롬프트는 SDK 가 stdin(stream-json)으로 보내 Windows 명령 줄 길이(약 32 KB)에 안 걸린다. images 가 있으면 사용자 메시지 하나의 스트림(그림 + 글)."""
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    errs = []

    async def stream():
        yield _user_line(content, images)

    async def run(cwd):
        opts = ClaudeAgentOptions(model=cfg["model"], effort=cfg["effort"], tools=[], setting_sources=[], cwd=cwd,
                                  output_format={"type": "json_schema", "schema": schema},
                                  extra_args={"no-session-persistence": None}, env={"CLAUDE_AGENT_SDK_CLIENT_APP": "NewFileManager"},
                                  stderr=lambda line: errs.append(line) if len(errs) < 50 else None)
        res = None
        async for m in query(prompt=stream() if images else content, options=opts):
            if isinstance(m, ResultMessage):
                res = m
        return res

    with tempfile.TemporaryDirectory(prefix="nfm-llm-", ignore_cleanup_errors=True) as cwd:  # 시간 초과로 끊긴 CLI 가 폴더를 잡고 있어도
        try:
            res = asyncio.run(asyncio.wait_for(run(cwd), timeout))
        except (TimeoutError, asyncio.TimeoutError):
            raise RuntimeError(f"시간 초과 {timeout:g}s") from None
        except Exception as e:  # ResultError(오류 결과)·ProcessError·CLINotFoundError — 까닭 + CLI stderr 끝
            tail = " | ".join(errs[-3:])
            raise RuntimeError(f"{type(e).__name__}: {e}"[:300] + (f" — {tail[-200:]}" if tail else "")) from None
    if res is None:
        raise RuntimeError("결과 메시지 없음")
    if res.subtype != "success" or res.is_error or not isinstance(res.structured_output, dict):  # 거절·재시도 한도·구조화 출력 없음
        why = res.errors or [res.result or ""]
        raise RuntimeError(f"{res.subtype} stop={res.stop_reason}: {str(why)[:300]}")
    return res.structured_output, res.total_cost_usd


def cli_why(code, stdout, stderr, model):
    """종료 코드가 0 이 아닌 CLI 의 까닭 — 사람이 읽는 짧은 글. stdout 이 결과 JSON 이면 그 `result`(+ HTTP 상태)를 쓰고,
    사용 한도(429 — 「You've reached your Fable limit …」)는 「<모델> 사용 한도에 닿음」 으로 줄인다(2026-11-22: JSON 끝 300자를 그대로 실어
    실행 멈춤 글이 잘리고 그 뒤의 「건너뛰기」 안내가 안 보였다 — references/Claude_CLI_헤드리스.md 「실패 결과」)."""
    try:
        out = json.loads(stdout or "")
    except ValueError:
        out = None
    if isinstance(out, dict) and out.get("result"):
        status, text = out.get("api_error_status"), " ".join(str(out["result"]).split())
        if status == 429 or re.search(r"reached your .*limit", text, re.I):
            return f"{model} 사용 한도에 닿음(429) — 다른 모델로 바꾸거나 한도가 풀린 뒤 다시"
        return f"{status or f'exit {code}'}: {text[:200]}"
    return f"exit {code}: {(stderr or stdout or '')[-300:]}"


def _cli(cfg, schema, content, timeout, images=None):
    """CLI 헤드리스 한 번. images 가 있으면 `--input-format stream-json --output-format stream-json --verbose`(stdin = 사용자 메시지 한 줄 · 끝의 result 줄을 읽음 —
    references/Claude_CLI_헤드리스.md 「그림 입력」), 없으면 전처럼 글을 stdin 으로 · 결과 JSON 하나."""
    exe = cli_path(cfg)
    if not exe:
        raise RuntimeError("CLI 실행 파일 없음")
    fmt = ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"] if images else ["--output-format", "json"]
    args = [exe, "-p", "--model", cfg["model"], "--effort", cfg["effort"], *fmt,
            "--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":")), "--tools", "", "--setting-sources", "",
            "--no-session-persistence"]
    feed = json.dumps(_user_line(content, images), ensure_ascii=False) + "\n" if images else content
    with tempfile.TemporaryDirectory(prefix="nfm-llm-") as cwd:
        run = subprocess.run(args, input=feed, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    stdout = run.stdout
    if images:   # stream-json — 줄마다 메시지, 끝의 type: result 가 결과(구조화 출력 · 비용)
        stdout = next((ln for ln in reversed((run.stdout or "").splitlines()) if _is_result(ln)), "")
    if run.returncode:
        raise RuntimeError(cli_why(run.returncode, stdout or run.stdout, run.stderr, cfg["model"]))
    out = json.loads(stdout)
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        raise RuntimeError(f"{out.get('subtype')}: {str(out.get('result'))[:300]}")
    return out["structured_output"], out.get("total_cost_usd")


CODEX_PREFIX = ("gpt-",)   # 이 꼴의 모델은 Codex CLI(OpenAI 로그인)로 부른다 — 2026-11-25 사용자 「양식 검토할때 claude fable, 하고 codex astra 모두 추출해서 협의」
CODEX_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "max": "xhigh"}


def is_codex(model):
    return bool(model) and model.startswith(CODEX_PREFIX)


def codex_path():
    """Codex CLI 실행 파일(env NFM_CODEX_CLI · 아니면 PATH 의 codex) | None."""
    cand = os.environ.get("NFM_CODEX_CLI", "").strip() or shutil.which("codex")
    return cand if cand and Path(cand).is_file() else None


def _codex(cfg, schema, content, timeout, images=None):
    """Codex CLI 헤드리스 한 번(`codex exec -s read-only --output-schema … -o …` — 빈 임시 폴더 · 읽기만 · 프롬프트는 stdin). 비용은 모른다(None)."""
    exe = codex_path()
    if not exe:
        raise RuntimeError("Codex CLI 실행 파일 없음")
    with tempfile.TemporaryDirectory(prefix="nfm-codex-") as cwd:
        sp, op = Path(cwd) / "schema.json", Path(cwd) / "out.json"
        sp.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        args = [exe, "exec", "-s", "read-only", "--skip-git-repo-check", "--color", "never", "-m", cfg["model"],
                "-c", f'model_reasoning_effort="{CODEX_EFFORT.get(cfg["effort"], "medium")}"', "--output-schema", str(sp), "-o", str(op)]
        for i, im in enumerate(images or ()):
            ip = Path(cwd) / f"img{i}.{(im.get('media') or 'image/png').split('/')[-1]}"
            ip.write_bytes(im["data"])
            args += ["-i", str(ip)]
        run = subprocess.run(args + ["-"], input=content, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = op.read_text(encoding="utf-8") if op.is_file() else ""
    if run.returncode or not text.strip():
        raise RuntimeError(f"codex exit {run.returncode}: {(run.stderr or run.stdout or '')[-300:]}")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError("codex: JSON 객체가 아닙니다")
    return data, None


def _api(cfg, schema, content, timeout, max_tokens=32000, images=None):
    """키를 차례대로 — 키 탓 실패(거절 · 권한 · 한도 · 크레딧)면 그 키를 잠시 뒤로 미루고 다음 키로(app/llm_keys.py)."""
    errs = []
    for key in llm_keys.keys():
        try:
            out = _api_one(cfg, schema, content, timeout, key, max_tokens, images)
        except Exception as e:
            reason = llm_keys.why(e)
            if not reason:
                raise
            llm_keys.rest(key, reason)
            log.warning("LLM api: 키 %s %s — 다음 키로", llm_keys.tail(key), reason)
            errs.append(f"{llm_keys.tail(key)} {reason}")
            continue
        llm_keys.ok(key)
        return out
    raise RuntimeError("쓸 수 있는 키가 없습니다: " + (", ".join(errs) or "키 없음"))


def _api_one(cfg, schema, content, timeout, key, max_tokens=32000, images=None):
    import anthropic

    own = {"api_key": key} if llm_keys.source() == "fable" else {}  # env 의 키는 전처럼 SDK 가 env 에서(ANTHROPIC_AUTH_TOKEN 도)
    client = anthropic.Anthropic(timeout=timeout, max_retries=0, **own)
    kw = {"model": cfg["model"], "max_tokens": max_tokens, "messages": [{"role": "user", "content": _blocks(content, images) if images else content}],
          "output_config": {"effort": cfg["effort"], "format": {"type": "json_schema", "schema": schema}}}
    if cfg["model"] in FALLBACK_MODELS:
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
    else:
        resp = client.messages.create(**kw)
    if resp.stop_reason != "end_turn":  # refusal·max_tokens → 스키마에 안 맞을 수 있음
        raise RuntimeError(f"stop_reason={resp.stop_reason}")
    return json.loads(next(b.text for b in resp.content if b.type == "text")), None


SLOTS_DEFAULT = 8  # 동시에 부르는 호출 수의 기본(env NFM_LLM_SLOTS 가 먼저) — 위 「동시 호출」
_SLOTS = None
_SLOTS_GUARD = threading.Lock()


def _slots():
    global _SLOTS
    with _SLOTS_GUARD:
        if _SLOTS is None:
            _SLOTS = threading.BoundedSemaphore(slots_n())
        return _SLOTS


def reset_slots():
    """시험용 — 자리 수 env 를 바꾼 뒤 다시 만들게."""
    global _SLOTS
    with _SLOTS_GUARD:
        _SLOTS = None


def call(schema, content, what, *, timeout=180.0, effort=None, model=None, pin=False, images=None, slot=None):
    """구조화 출력 한 번 → {"data", "backend", "ms", "costUsd", "error"}. data 가 None 이면 error 에 까닭(off·busy·길마다 실패 글).
    자리는 NFM_LLM_WAIT초(기본 900) 기다린다 — 기다린 시간은 ms 에 안 넣는다.
    pin=True 면 준 model 이 NFM_LLM_MODEL_FORCE 보다 먼저다 — 사용자가 그 일의 모델을 따로 정한 호출만(템플릿 서식 정리 에이전트 = Opus 5.5:
    2026-11-15 사용자 "opus5.5 가 템플릿의 서식을 직접 조정" — spec_hwpx_웹편집 ② §8-4).
    프롬프트 끝에는 그 에이전트에 사람이 **덧붙여 둔 글**(범용 + 지금 워크플로우 전용)이 붙는다(`agent_notes.attach` — 지금 워크플로우는 맥락 변수: 스레드를 새로 띄우는 곳은 `agent_notes.carry`).
    모델·생각 깊이의 차례(뒤가 이김): env 기본 → 호출이 준 model·effort → NFM_LLM_MODEL_FORCE(pin 이면 건너뜀) → **「에이전트 설정」 에서 그 에이전트에 사람이 정한 값**
    (what 으로 에이전트를 찾는다 — `agent_settings.override`, spec_에이전트 ② §2). 모든 호출은 실행 기록에 한 줄 남는다(`agent_settings.record`).
    images = 글 앞에 실을 그림들 [{data: bytes, media: "image/png" …}](spec_그림 ② §7 — 없으면 전과 같은 길).
    slot = 여러 모델을 함께 부르는 에이전트의 자리 이름(「LLM1」 · 「LLM2」 — 2026-11-25 사용자 「LLM1, LLM2 이런식으로 … 모델을 선택」): 주면 준 model 이 끝 값이다(서버 고정 · 에이전트 설정의 모델을 건너뜀 —
    그 자리의 모델은 부르는 쪽이 `agent_settings.models` 로 이미 골랐다). 모델이 `gpt-…` 이면 Codex CLI 로 부른다(`_codex`)."""
    content, notes = agent_notes.attach(content, what)  # 그 에이전트에 사람이 덧붙여 둔 글(범용 · 지금 워크플로우 전용 — spec_에이전트 ② §6): 프롬프트 맨 끝에
    out = _call(schema, content, what, timeout=timeout, effort=effort, model=model, pin=pin or bool(slot), slot=slot, **({"images": images} if images else {}))
    if slot:
        out["slot"] = slot
    if notes:
        out["notes"] = notes  # 붙인 것의 꼬리표(["all", "job:<워크플로우 키>"]) — 실행 기록에 남는다
    agent_settings.record(what, out)
    return out


def _call(schema, content, what, *, timeout, effort, model, pin, images=None, slot=None):
    cfg = settings()
    if effort in EFFORTS:
        cfg["effort"] = effort
    pinned = bool(pin and model and _MODEL_RE.fullmatch(model))
    if model and _MODEL_RE.fullmatch(model):
        cfg["model"] = model
    if not pinned:
        cfg["model"] = forced() or cfg["model"]
    ov = agent_settings.override(what)  # 사람이 그 에이전트에 정한 모델·생각 깊이 — 맨 먼저
    if ov.get("effort") in EFFORTS:
        cfg["effort"] = ov["effort"]
    if ov.get("model") and _MODEL_RE.fullmatch(ov["model"]) and not (slot and model):
        cfg["model"] = ov["model"]
    out = {"data": None, "backend": None, "ms": 0, "costUsd": None, "error": None, "model": cfg["model"], "effort": cfg["effort"]}
    tries = (["codex"] if codex_path() else []) if is_codex(cfg["model"]) else _tries(cfg)
    if not tries:
        out["error"] = "codex 없음" if is_codex(cfg["model"]) else "off"
        return out
    slots = _slots()
    wait = _env_num("NFM_LLM_WAIT", 900.0, float)
    if not slots.acquire(timeout=min(max(0.0, wait), threading.TIMEOUT_MAX)):
        log.warning("%s: LLM 자리 대기 %g초 초과 — 호출하지 않음", what, wait)
        out["error"] = "busy"
        return out
    errors = []
    try:
        for backend in tries:
            t = time.monotonic()
            try:
                data, cost = {"sdk": _sdk, "cli": _cli, "api": _api, "codex": _codex}[backend](cfg, schema, content, timeout, **({"images": images} if images else {}))
                out.update(data=data, backend=backend, ms=round((time.monotonic() - t) * 1000), costUsd=cost, error=None)
                return out
            except Exception as e:  # 실행 파일·로그인·네트워크·거절·파싱 — 다음 길로
                log.warning("%s: LLM %s 호출 실패: %s", what, backend, e)
                errors.append(f"{backend}: {e}")
                out["ms"] += round((time.monotonic() - t) * 1000)
        out["error"] = "; ".join(errors)[:600]
        return out
    finally:
        slots.release()


def slots_n():
    """동시에 부를 수 있는 호출 수(env NFM_LLM_SLOTS — 기본 SLOTS_DEFAULT) — 자리(_slots)와 같이 도는 일꾼 수를 정하는 곳이 쓴다(자리보다 많은 일꾼은 자리를 기다릴 뿐이다)."""
    return max(1, _env_num("NFM_LLM_SLOTS", SLOTS_DEFAULT, int))


def ask_all(jobs, workers=None, retry_workers=2, progress=None):
    """여러 호출을 병렬로 → jobs 와 같은 순서의 결과 목록. job = call 의 인자 dict {schema, content, what, timeout?, effort?, model?}.
    데이터 없이 실패한 것(off·busy 제외)은 retry_workers 병렬로 한 번 더 — 결과에 "retried": True. 한 job 의 예외가 다른 결과를 버리지 않는다.
    progress(끝난 수, 전체 수) = 첫 바퀴에서 호출 하나가 끝날 때마다(부른 스레드에서 · 예외는 삼킨다) — 큰 문서의 진행 글(「표 판정 호출 7/25」)."""
    jobs = list(jobs)
    if not jobs:
        return []

    def one(job):
        try:
            return call(job["schema"], job["content"], job.get("what", "llm"), timeout=job.get("timeout", 180.0),
                        effort=job.get("effort"), model=job.get("model"))
        except Exception as e:  # call 은 예외를 안 내지만 시험의 가짜 call 등
            return {"data": None, "backend": None, "ms": 0, "costUsd": None, "error": f"예외: {e}"}

    keep = agent_notes.carry(one)  # 일꾼 스레드에도 지금 워크플로우(덧붙이는 글의 전용 범위)를 넘긴다 — 새 스레드는 맥락을 물려받지 않는다

    def run(idx, n, tick=None):
        res = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(n, len(idx)))) as ex:
            futs = {ex.submit(keep, jobs[i]): i for i in idx}
            for f in concurrent.futures.as_completed(futs):
                res[futs[f]] = f.result()
                if tick is not None:
                    try:
                        tick(len(res), len(jobs))
                    except Exception:  # 진행 글이 호출 결과를 버리지 않게
                        log.exception("ask_all progress 실패")
        return res

    n = workers or slots_n()
    out = run(range(len(jobs)), n, progress)
    again = [i for i, r in out.items() if r["data"] is None and r["error"] not in ("off", "busy")]
    if again:
        for i, r in run(again, retry_workers).items():
            out[i] = {**r, "retried": True}
    return [out[i] for i in range(len(jobs))]
