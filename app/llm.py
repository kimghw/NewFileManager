"""LLM 관문 — Claude 구조화 출력(JSON schema) 한 번 부르기(spec_헤딩_추출 ② §6).

FileMergeManager `app/llm.py` 의 CLI·SDK 호출부만 옮겨 줄인 것(2026-11-09). 설정 파일·에이전트 등록부·스킬은 안 옮겼다 — LLM 에 줄 지침은
`app/heading_guides.py` 가 맡는다(코드 고정 출력 계약 + 사용자 지침 + 자료).

- 길(2026-11-09 사용자 "claude sdk cli 로 LLM 을 호출"): **Claude Agent SDK 먼저**(`claude_agent_sdk.query` — 패키지에 든 Claude Code CLI 를 SDK 가 띄움,
  도구 없음·설정 안 읽음·빈 임시 폴더·세션 안 남김, `output_format` json_schema → `ResultMessage.structured_output`, references/Claude_Agent_SDK.md),
  안 되면 CLI 헤드리스(`claude -p … --json-schema`, references/Claude_CLI_헤드리스.md), 그다음 Anthropic API SDK(ANTHROPIC_API_KEY·ANTHROPIC_AUTH_TOKEN 이 있을 때만).
  env `NFM_LLM_BACKEND` = auto|sdk|cli|api|off(기본 auto = sdk → cli → api) · `NFM_LLM_MODEL`(기본 claude-opus-5-5) ·
  `NFM_LLM_MODEL_FORCE`(모든 호출의 모델 — 검토마다 코드에 정한 모델(merge_llm.MODEL 등)보다도 먼저. 2026-11-12 사용자 「api 키로 해서 fable로 해줘」) ·
  `NFM_CLAUDE_CLI`(cli 길의 실행 파일 절대 경로 — 없으면 PATH 의 claude. sdk 길은 패키지에 든 CLI).
- 동시 호출: 프로세스 전체 `NFM_LLM_SLOTS`(기본 4) 자리. Windows 에서 `claude -p` 를 13개 한꺼번에 띄우면 일부가 0xC0000409 로 죽은 실측(FileMergeManager)
  — `ask_all` 은 실패한 것만 병렬 2 로 한 번 더 부른다.
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

from app import agent_settings

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
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


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
            "active": tries[0] if tries else None}


def _sdk(cfg, schema, content, timeout):
    """Claude Agent SDK 한 번 — 도구 없음(구조화 출력용 StructuredOutput 만 CLI 가 붙임)·설정 안 읽음·빈 임시 폴더·세션 안 남김.
    프롬프트는 SDK 가 stdin(stream-json)으로 보내 Windows 명령 줄 길이(약 32 KB)에 안 걸린다."""
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    errs = []

    async def run(cwd):
        opts = ClaudeAgentOptions(model=cfg["model"], effort=cfg["effort"], tools=[], setting_sources=[], cwd=cwd,
                                  output_format={"type": "json_schema", "schema": schema},
                                  extra_args={"no-session-persistence": None}, env={"CLAUDE_AGENT_SDK_CLIENT_APP": "NewFileManager"},
                                  stderr=lambda line: errs.append(line) if len(errs) < 50 else None)
        res = None
        async for m in query(prompt=content, options=opts):
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


def _cli(cfg, schema, content, timeout):
    exe = cli_path(cfg)
    if not exe:
        raise RuntimeError("CLI 실행 파일 없음")
    args = [exe, "-p", "--model", cfg["model"], "--effort", cfg["effort"], "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":")), "--tools", "", "--setting-sources", "",
            "--no-session-persistence"]
    with tempfile.TemporaryDirectory(prefix="nfm-llm-") as cwd:
        run = subprocess.run(args, input=content, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if run.returncode:
        raise RuntimeError(f"exit {run.returncode}: {(run.stderr or run.stdout or '')[-300:]}")
    out = json.loads(run.stdout)
    if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
        raise RuntimeError(f"{out.get('subtype')}: {str(out.get('result'))[:300]}")
    return out["structured_output"], out.get("total_cost_usd")


def _api(cfg, schema, content, timeout, max_tokens=32000):
    import anthropic

    client = anthropic.Anthropic(timeout=timeout, max_retries=0)
    kw = {"model": cfg["model"], "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}],
          "output_config": {"effort": cfg["effort"], "format": {"type": "json_schema", "schema": schema}}}
    if cfg["model"] in FALLBACK_MODELS:
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
    else:
        resp = client.messages.create(**kw)
    if resp.stop_reason != "end_turn":  # refusal·max_tokens → 스키마에 안 맞을 수 있음
        raise RuntimeError(f"stop_reason={resp.stop_reason}")
    return json.loads(next(b.text for b in resp.content if b.type == "text")), None


_SLOTS = None
_SLOTS_GUARD = threading.Lock()


def _slots():
    global _SLOTS
    with _SLOTS_GUARD:
        if _SLOTS is None:
            _SLOTS = threading.BoundedSemaphore(max(1, _env_num("NFM_LLM_SLOTS", 4, int)))
        return _SLOTS


def reset_slots():
    """시험용 — 자리 수 env 를 바꾼 뒤 다시 만들게."""
    global _SLOTS
    with _SLOTS_GUARD:
        _SLOTS = None


def call(schema, content, what, *, timeout=180.0, effort=None, model=None, pin=False):
    """구조화 출력 한 번 → {"data", "backend", "ms", "costUsd", "error"}. data 가 None 이면 error 에 까닭(off·busy·길마다 실패 글).
    자리는 NFM_LLM_WAIT초(기본 900) 기다린다 — 기다린 시간은 ms 에 안 넣는다.
    pin=True 면 준 model 이 NFM_LLM_MODEL_FORCE 보다 먼저다 — 사용자가 그 일의 모델을 따로 정한 호출만(템플릿 서식 정리 에이전트 = Opus 5.5:
    2026-11-15 사용자 "opus5.5 가 템플릿의 서식을 직접 조정" — spec_hwpx_웹편집 ② §8-4).
    모델·생각 깊이의 차례(뒤가 이김): env 기본 → 호출이 준 model·effort → NFM_LLM_MODEL_FORCE(pin 이면 건너뜀) → **「에이전트 설정」 에서 그 에이전트에 사람이 정한 값**
    (what 으로 에이전트를 찾는다 — `agent_settings.override`, spec_에이전트 ② §2). 모든 호출은 실행 기록에 한 줄 남는다(`agent_settings.record`)."""
    out = _call(schema, content, what, timeout=timeout, effort=effort, model=model, pin=pin)
    agent_settings.record(what, out)
    return out


def _call(schema, content, what, *, timeout, effort, model, pin):
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
    if ov.get("model") and _MODEL_RE.fullmatch(ov["model"]):
        cfg["model"] = ov["model"]
    out = {"data": None, "backend": None, "ms": 0, "costUsd": None, "error": None, "model": cfg["model"], "effort": cfg["effort"]}
    tries = _tries(cfg)
    if not tries:
        out["error"] = "off"
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
                data, cost = {"sdk": _sdk, "cli": _cli, "api": _api}[backend](cfg, schema, content, timeout)
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


def ask_all(jobs, workers=None, retry_workers=2):
    """여러 호출을 병렬로 → jobs 와 같은 순서의 결과 목록. job = call 의 인자 dict {schema, content, what, timeout?, effort?, model?}.
    데이터 없이 실패한 것(off·busy 제외)은 retry_workers 병렬로 한 번 더 — 결과에 "retried": True. 한 job 의 예외가 다른 결과를 버리지 않는다."""
    jobs = list(jobs)
    if not jobs:
        return []

    def one(job):
        try:
            return call(job["schema"], job["content"], job.get("what", "llm"), timeout=job.get("timeout", 180.0),
                        effort=job.get("effort"), model=job.get("model"))
        except Exception as e:  # call 은 예외를 안 내지만 시험의 가짜 call 등
            return {"data": None, "backend": None, "ms": 0, "costUsd": None, "error": f"예외: {e}"}

    def run(idx, n):
        res = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(n, len(idx)))) as ex:
            futs = {ex.submit(one, jobs[i]): i for i in idx}
            for f in concurrent.futures.as_completed(futs):
                res[futs[f]] = f.result()
        return res

    n = workers or max(1, _env_num("NFM_LLM_SLOTS", 4, int))
    out = run(range(len(jobs)), n)
    again = [i for i, r in out.items() if r["data"] is None and r["error"] not in ("off", "busy")]
    if again:
        for i, r in run(again, retry_workers).items():
            out[i] = {**r, "retried": True}
    return [out[i] for i in range(len(jobs))]
