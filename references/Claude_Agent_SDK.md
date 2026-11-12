# Claude Agent SDK(Python `claude-agent-sdk`) — 구조화 출력 한 번 부르기

출처: code.claude.com/docs/en/agent-sdk/python · …/agent-sdk/structured-outputs(2026-11-09 읽음) + 설치한 패키지 소스(`_internal/transport/subprocess_cli.py`) + 이 PC 실측.
사용처: `app/llm.py` `_sdk`(첫 길). CLI 를 직접 띄우는 길은 [Claude_CLI_헤드리스.md](Claude_CLI_헤드리스.md).

## 설치

- `pip install claude-agent-sdk==0.2.172`(2026-10-22 판 — 2026-11-09 최신은 0.2.179). **Claude Code CLI 가 패키지에 들어 있다**: `site-packages/claude_agent_sdk/_bundled/claude.exe`
  (297 MB, Windows 휠 129.5 MB). SDK 는 이 번들 CLI 를 먼저 쓰고, 없으면 PATH 의 `claude`(Windows 에서는 .cmd 껍데기 말고 실제 .exe 를 고름). `cli_path` 로 바꿀 수 있다.
- `ResultError`(오류 결과로 끝난 query 의 예외)는 0.2.140 부터. `setting_sources=[]` 가 「설정 안 읽음」 으로 동작하는 것은 0.1.59 뒤부터(그 전은 생략과 같았다).
- 인증 = 그 PC 사용자의 Claude Code 로그인(구독). API 키 없이 됨 — WMI(`Win32_Process.Create`)로 띄운 프로세스에서도 됨(2026-11-09 실측).

## 호출(옵션 → CLI 인자, 소스 확인)

```python
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
opts = ClaudeAgentOptions(model="claude-opus-5-5", effort="low", tools=[], setting_sources=[], cwd=<빈 임시 폴더>,
                          output_format={"type": "json_schema", "schema": schema},
                          extra_args={"no-session-persistence": None}, env={"CLAUDE_AGENT_SDK_CLIENT_APP": "NewFileManager"},
                          stderr=callback)
async for m in query(prompt=text, options=opts):
    if isinstance(m, ResultMessage): res = m
```

- 명령: `claude --output-format stream-json --verbose --system-prompt "" --tools "" --model … --setting-sources= --effort … --json-schema … --input-format stream-json`
  (+ `extra_args` 는 `--이름[ 값]`). **프롬프트는 stdin(stream-json)** 이라 Windows 명령 줄 한도(약 32 KB)에 안 걸린다 — 단 `--json-schema`·문자열 `system_prompt` 는 명령 줄.
- `system_prompt=None` 이면 빈 시스템 프롬프트(`--system-prompt ""`) — Claude Code 기본 시스템 프롬프트가 아니다(쓰려면 `{"type": "preset", "preset": "claude_code"}`).
- `tools=[]` → `--tools ""`(도구 없음). 구조화 출력은 CLI 가 붙이는 `StructuredOutput` 도구 호출로 구현 — 도구를 다 꺼도 된다. 스키마에 안 맞으면 CLI 가 다시 시키고,
  한도를 넘으면 `subtype: "error_max_structured_output_retries"`.
- `setting_sources=[]` → user·project·local 설정과 CLAUDE.md 를 안 읽음. 그래도 작업 폴더는 빈 임시 폴더로(안전).
- `query()` 는 async 제너레이터 — 동기 코드에서는 `asyncio.run(asyncio.wait_for(run(), timeout))`. 작업 스레드마다 `asyncio.run` 이 따로 루프를 만든다(`ask_all` 병렬 OK).

## 결과 판정

- `ResultMessage`: `subtype`(success | error_during_execution | error_max_turns | error_max_budget_usd | error_max_structured_output_retries), `is_error`, `stop_reason`,
  `structured_output`(dict), `result`(마지막 글), `total_cost_usd`, `usage`, `model_usage`, `errors`, `num_turns`, `duration_ms`.
- **성공 = subtype success · is_error False · structured_output 이 dict.** success 인데 structured_output 이 None 인 경우(구조화 출력 없이 끝남)와 거절(`stop_reason`
  "refusal" — subtype 은 success 일 수 있음)은 실패로 본다.
- 오류 결과로 끝나면 결과 메시지를 낸 뒤 `ResultError`(⊂ `ProcessError` ⊂ `ClaudeSDKError`)를 던진다. 그 밖에 `CLINotFoundError`·`CLIConnectionError`·`CLIJSONDecodeError`.

## 실측(이 PC, 2026-11-09, effort low, 짧은 입력)

- 「2+3」 구조화 출력: 4.1 s · $0.036. WMI 로 띄운 프로세스에서 「7*6」: 3.5 s · $0.035. CLI 직접(`claude -p`, Claude Code 시스템 프롬프트) 짧은 호출 바닥 약 $0.05 보다 싸다 —
  SDK 길은 시스템 프롬프트가 비어 있어서로 보인다(추정).
- **겹친 배열 스키마**(2026-11-10, claude-opus-5-5 · effort low · SDK 0.2.172 — `app/table_llm.py` 표 격자): `{rows: [{cells: [{text, rowSpan, colSpan}]}], headerRows, headerCols, footRows, note}`
  (객체 → 배열 → 객체 → 배열 → 객체, 모든 층 `additionalProperties: false`·`required` 전부)가 한 번에 맞게 돌아온다. 프롬프트 약 2,500자(계약 + 양식 표 6×7 격자 + 원본 글 4줄) →
  5행 × 6열 표: 9.8 s · $0.071, 4×4 표를 옮기기만 하는 호출: 7.5 s · $0.041. 재시도 없음.
