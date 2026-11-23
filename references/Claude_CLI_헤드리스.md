# Claude Code CLI — 헤드리스(print) 호출로 구조화 출력 받기

출처: FileMergeManager `references/Claude_CLI_헤드리스.md`(2026-10-29~31 확인)를 옮기고 이 PC 실측을 더함. 사용처: `app/llm.py` `_cli`(spec_헤딩_추출 ② §5·§6).
2026-11-09 부터 첫 길은 Claude Agent SDK — [Claude_Agent_SDK.md](Claude_Agent_SDK.md)(이 문서의 CLI 길은 대체 길).

## 호출

```
claude -p --model claude-opus-5-5 --effort low --output-format json --json-schema '<JSON schema>' \
       --tools "" --setting-sources "" --no-session-persistence      # 프롬프트는 stdin
```

- `-p` 에 프롬프트 인자가 없으면 **stdin** 을 프롬프트로 읽는다 — 긴 프롬프트도 명령줄 길이 제한(Windows 32K)에 안 걸린다. 단 `--json-schema` 는 명령줄이라 스키마는 작게.
- `--json-schema`: 결과 객체(`--output-format json`)의 **`structured_output`** 에 파싱된 dict, `result` 에는 같은 내용의 JSON 문자열.
- `--tools ""` = 도구 끔, `--setting-sources ""` = user·project·local 설정 안 읽음, `--no-session-persistence` = 세션 저장 안 함. 작업 폴더의 CLAUDE.md 는 읽으므로
  **빈 임시 폴더에서** 실행한다(`tempfile.TemporaryDirectory()` — TEMP 가 가리키는 드라이브).
- 인증 = 그 PC 사용자의 Claude Code 로그인(구독). `ANTHROPIC_API_KEY` 없이도 된다. Claude Code 세션 안에서 다시 불러도 동작.
  단 **자식 env 에 `ANTHROPIC_API_KEY` 가 있으면 구독보다 키가 먼저**다(아래 「도구를 쓰는 헤드리스 에이전트」 — `--setting-sources ""` 여도 env 는 그대로). 이 PC 는 2026-11-12부터 `~\.claude\settings.json` env 에 키가 있어
  Claude Code 세션의 Bash 에도 키가 들어 있다 — 구독으로 부르려면 `env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN claude -p …`.
- 2026-11-16 실측(2.1.321): 키를 뺀 구독 로그인으로 `--model claude-fable-5-2` 가 된다(작은 스키마 4.4초 · `modelUsage` 의 `costBasis: "list"` — `total_cost_usd` 는 정가로 셈한 값이지 키 청구가 아니다).
  같은 날 8114 서버를 이 길로(`NFM_LLM_BACKEND=cli`) 바꿔 서식 LLM 검토 호출 3번이 18.8초에 통과.
- 성공 판정: 종료 코드 0, `is_error: false`, `subtype: "success"`, `structured_output` 이 dict. 구조화 출력은 도구 호출로 구현돼 `stop_reason` 이 `"tool_use"`, `num_turns` 2 —
  `stop_reason` 으로 판정하지 않는다. 그 밖에 `total_cost_usd`, `duration_ms`, `modelUsage`.

## 그림 입력 — stream-json (2026-11-23 실측 · 2.1.321 · 구독 로그인)

- 글 프롬프트(stdin)에는 그림을 실을 수 없다 → **`--input-format stream-json --output-format stream-json --verbose`** 로 부르고 stdin 에 사용자 메시지 **한 줄**(JSON + 줄바꿈)을 준다:
  `{"type":"user","session_id":"","parent_tool_use_id":null,"message":{"role":"user","content":[{"type":"image","source":{"type":"base64","media_type":"image/png","data":"<base64>"}},{"type":"text","text":"<프롬프트>"}]}}`.
  `--input-format stream-json` 은 `--output-format stream-json`(+ `--verbose`) 과만 된다. `--json-schema` · `--tools ""` · `--setting-sources ""` · `--no-session-persistence` 는 그대로 함께 쓴다.
- 출력 = 줄마다 메시지(`system`/`init` → `assistant` … → 끝의 **`type: result`**). result 줄의 꼴은 `--output-format json` 의 결과 객체와 같다(`structured_output` · `total_cost_usd` · `is_error` · `subtype`).
  stdin 이 끝나면(EOF) 한 턴 돌고 끝난다. init 줄의 `apiKeySource` 가 `"none"` 이면 구독으로 청구.
- 잰 것: 420×140 표 그림(3행 2열 + 제목 줄) → 격자 · 캡션을 정확히 읽음 · Opus 5.5 effort low 약 6초 · `total_cost_usd` 0.03~0.05(정가 셈).
- Agent SDK 길도 같은 메시지 dict 를 `query(prompt=<async iterable>)` 로 주면 된다(SDK 가 이터러블이 끝나면 stdin 을 닫는다 — `claude_agent_sdk` 0.2.172 `Query.stream_input`). 사용처 `app/llm.py` `_user_line`(spec_그림 ② §7).

## 실패 결과 — 종료 코드 1 + 결과 JSON (2026-11-22 실측 · 구독 로그인)

- 모델 사용 한도: 종료 코드 **1**, stdout 은 결과 JSON 그대로 — `is_error: true` · `subtype: "success"`(!) · `api_error_status: 429` · `terminal_reason: "api_error"` · `duration_api_ms: 0` ·
  `result: "You've reached your Fable limit. Switch to another model, or manage usage credits at https://claude.ai/settings/usage?from=cc_cli_limit_message, to continue."`.
  한도는 **모델마다**다 — 같은 구독에서 Fable 이 한도일 때 `--model claude-opus-5-5` 는 정상(2초). 한도가 언제 풀리는지는 결과에 없다.
- 키 크레딧 없음(env 에 `ANTHROPIC_API_KEY`): 같은 꼴에 `api_error_status: 400` · `result: "Credit balance is too low"`.
- 까닭은 stderr 가 아니라 stdout JSON 의 `result` 에 있다 — `app/llm.py` `cli_why` 가 그것을 읽는다(전에는 stdout 끝 300자를 그대로 실어 화면 글이 JSON 조각이 됐다).

## 구조화 출력 스키마 제약(API 와 같음)

- 모든 object 에 `additionalProperties: false`, 재귀 스키마·숫자/길이 제약 불가 → 트리·그래프는 **평면 목록 + 부모 id** 로 받는다.
- 선택 칸 대신 모든 키를 required 로 두고 해당 없음은 `""`·`0`·`[]`·`false` 로 받는 것이 안정적(FileMergeManager 관례, 이 프로젝트도 같음).

## 실측

- FileMergeManager(effort low, 짧은 입력): 약칭 추출 4.8 s($0.055), 연결 확인 6.5 s, 파일명 정리 4.7~5.4 s.
- 이 PC 2026-11-09(Claude Code 2.1.286, `C:\Users\SSCB\.local\bin\claude.EXE`): 짧은 판정 1.9 s($0.058), 연결 확인 4.1 s($0.054) — 짧은 호출도 비용 바닥이 약 $0.05(CLI 시스템 프롬프트).

## 동시 실행 한계(FileMergeManager 2026-10-31 실측)

- Windows 에서 `claude -p` 13개를 한꺼번에 띄우자 4개가 비정상 종료 — 종료 코드 3221226505(`0xC0000409`, STATUS_STACK_BUFFER_OVERRUN), stderr 없음, 입력 크기와 무관.
  같은 묶음을 병렬 4 로 다시 부르면 모두 성공 → 이 프로젝트는 서버 전체 동시 4(`NFM_LLM_SLOTS`), 실패분만 병렬 2 로 한 번 더(`llm.ask_all`).
- **다시 잼(이 PC 2026-11-17 — Claude Code 2.1.321 · NewFileManager `app/llm._call` 의 cli 길 · 작은 프롬프트 · `--model claude-haiku-5-5` · 구조화 출력)**: 한꺼번에 **8개** × 5바퀴(40호출) 모두 성공(바퀴마다 4.4~7.4초),
  **12개** × 2바퀴(24호출)도 모두 성공(8.8초 · 12.0초 — 12개째부터는 호출마다 시간이 늘기도 한다). 위의 13개 비정상 종료는 재현되지 않았다(CLI 판이 달라졌을 수 있다 — 그때 판은 기록에 없다).
  → 이 프로젝트의 기본 자리 수를 **8** 로 올림(`llm.SLOTS_DEFAULT` — 12 에서 성공했지만 여유를 둠 · env `NFM_LLM_SLOTS` 로 바꾼다). 잰 것은 **프로세스가 죽는지**뿐이다 —
  큰 프롬프트 · Fable 8개를 한꺼번에 불렀을 때의 구독 사용 한도(429)는 재지 않았다(실패한 호출은 `llm.ask_all` 이 병렬 2 로 한 번 더 부른다).

## 도구를 쓰는 헤드리스 에이전트를 API 키로 (2026-11-13 실측 — Claude Code 2.1.321 · Windows)

fable 스킬의 「키 에이전트」(`~/.claude/skills/fable/scripts/fable_agent.py` — 원본 `E:\dev\globalize_skill\.claude\skills\fable`)가 쓰는 사실.

- 호출: `claude -p --model claude-fable-5-2 --effort high --output-format stream-json --verbose --permission-mode acceptEdits --permission-prompts none [--allowedTools "<규칙>" …] [--max-budget-usd N] [--resume <세션 id>] [--append-system-prompt …]` — 프롬프트는 stdin, 작업 폴더 = cwd(그 폴더의 CLAUDE.md·사용자 설정은 평소처럼 읽는다).
- **청구**: 자식 프로세스 env 에 `ANTHROPIC_API_KEY` 가 있으면 그 키로 청구된다 — `stream-json` 의 첫 메시지(`type: system`, `subtype: init`)의 `apiKeySource` 가 `"ANTHROPIC_API_KEY"`. 구독 로그인이 있어도 키가 먼저다(stderr 에 「claude.ai connectors are disabled because ANTHROPIC_API_KEY … takes precedence」).
  `--output-format json`(결과 하나)에는 init 이 없어 키 출처를 못 본다 — 확인하려면 `stream-json --verbose`.
- **사용자 설정의 env 가 자식 env 를 덮는다**(2026-11-23 실측 · 2.1.321): `~\.claude\settings.json` 의 `env.ANTHROPIC_API_KEY` 가 있으면 CLI 가 그 값을 적용해, 띄울 때 자식 env 에 넣은 다른 키를 덮어쓴다.
  init 의 `apiKeySource` 는 어느 쪽이든 `"ANTHROPIC_API_KEY"` 라 구별되지 않는다. 이 PC 에서 settings 의 키(끝 VAAA — 크레딧 없음)가 Fable 키(끝 qgAA)를 덮어 첫 요청이 `billing_error` 400 「Credit balance is too low」(작은 일감도 같음)였고,
  같은 키로 SDK 를 직접 부르면 됐다. `--setting-sources project,local`(사용자 설정을 안 읽음)을 주면 자식 env 의 키로 청구되어 통과($0.25 — 한 낱말 답). 대신 사용자 설정의 `permissions.allow` · 훅도 빠진다.
- init 메시지: `apiKeySource` · `model` · `permissionMode` · `cwd` · `session_id` · `tools`(82개). 끝 메시지(`type: result`): `subtype`(success …) · `is_error` · `num_turns` · `duration_ms` · `total_cost_usd` · `usage` · `modelUsage`(claude-haiku-5-5 도 함께 쓰인다) · `session_id` · **`permission_denials`**(거절된 도구 호출 목록 — `tool_name`·`tool_input`).
- **권한**: `--permission-mode` = acceptEdits · auto · bypassPermissions · manual · dontAsk · plan. `--permission-prompts none` = 물어야 하는 것은 자동 거절(권한 방식이 정하는 나머지는 그대로).
  `acceptEdits` + `none`: 파일 읽기·쓰기(cwd 안)는 되고 `PowerShell python --version` 은 거절되어 `permission_denials` 에 남는다. `--allowedTools "PowerShell(python --version)"` 를 주면 그 명령만 돈다(설정 파일의 `permissions.allow` 도 같은 효과).
  Windows 에서 에이전트는 명령을 Bash 가 아니라 **PowerShell 도구**로 돌리려 했다 — 허용 규칙은 `PowerShell(…)` 꼴도 함께.
- `--resume <session_id>` + 새 프롬프트: 앞 대화를 기억한 채 이어 간다(같은 cwd 에서).
- 비용: 한 줄짜리 일에도 $0.14~0.20(시스템 프롬프트·도구 정의 몫 — 캐시가 잡히면 덜 든다).
- 부른 세션에 묶인 env(`CLAUDECODE` · `CLAUDE_CODE_ENTRYPOINT` · `CLAUDE_CODE_SSE_PORT` · `CLAUDE_CODE_SESSION_ID` · `CLAUDE_CODE_CHILD_SESSION` · `CLAUDE_CODE_MESSAGING_SOCKET` · `CLAUDE_PID` …)를 빼고 띄웠다 — 뺀 채로 정상 동작(안 뺐을 때는 시험하지 않음).
- **부른 세션이 auto 권한 방식이면**: 자식을 `--permission-mode auto`·`bypassPermissions` 로 띄우는 Bash 호출 자체가 분류기에 거절된다(「Undermining Oversight」 — 자식은 부른 세션의 권한 검사를 받지 않는 프로세스라서). `acceptEdits` + 좁은 `--allowedTools` 로 띄우는 것은 통과했다.

## 디스크

- CLI 와 임시 폴더는 `%TEMP%`(보통 C:)를 쓴다. 2026-11-09 C: 가 가득 찼을 때 TEMP·TMP 를 다른 드라이브로 돌린 프로세스에서 호출은 정상(4.1 s).
