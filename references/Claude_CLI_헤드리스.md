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
- 인증 = 그 PC 사용자의 Claude Code 로그인(구독). `ANTHROPIC_API_KEY` 없이도 된다(이 PC 에는 키 없음 — SDK 길은 안 쓰임). Claude Code 세션 안에서 다시 불러도 동작.
- 성공 판정: 종료 코드 0, `is_error: false`, `subtype: "success"`, `structured_output` 이 dict. 구조화 출력은 도구 호출로 구현돼 `stop_reason` 이 `"tool_use"`, `num_turns` 2 —
  `stop_reason` 으로 판정하지 않는다. 그 밖에 `total_cost_usd`, `duration_ms`, `modelUsage`.

## 구조화 출력 스키마 제약(API 와 같음)

- 모든 object 에 `additionalProperties: false`, 재귀 스키마·숫자/길이 제약 불가 → 트리·그래프는 **평면 목록 + 부모 id** 로 받는다.
- 선택 칸 대신 모든 키를 required 로 두고 해당 없음은 `""`·`0`·`[]`·`false` 로 받는 것이 안정적(FileMergeManager 관례, 이 프로젝트도 같음).

## 실측

- FileMergeManager(effort low, 짧은 입력): 약칭 추출 4.8 s($0.055), 연결 확인 6.5 s, 파일명 정리 4.7~5.4 s.
- 이 PC 2026-11-09(Claude Code 2.1.286, `C:\Users\SSCB\.local\bin\claude.EXE`): 짧은 판정 1.9 s($0.058), 연결 확인 4.1 s($0.054) — 짧은 호출도 비용 바닥이 약 $0.05(CLI 시스템 프롬프트).

## 동시 실행 한계(FileMergeManager 2026-10-31 실측)

- Windows 에서 `claude -p` 13개를 한꺼번에 띄우자 4개가 비정상 종료 — 종료 코드 3221226505(`0xC0000409`, STATUS_STACK_BUFFER_OVERRUN), stderr 없음, 입력 크기와 무관.
  같은 묶음을 병렬 4 로 다시 부르면 모두 성공 → 이 프로젝트는 서버 전체 동시 4(`NFM_LLM_SLOTS`), 실패분만 병렬 2 로 한 번 더(`llm.ask_all`).

## 도구를 쓰는 헤드리스 에이전트를 API 키로 (2026-11-13 실측 — Claude Code 2.1.321 · Windows)

fable 스킬의 「키 에이전트」(`~/.claude/skills/fable/scripts/fable_agent.py` — 원본 `E:\dev\globalize_skill\.claude\skills\fable`)가 쓰는 사실.

- 호출: `claude -p --model claude-fable-5-2 --effort high --output-format stream-json --verbose --permission-mode acceptEdits --permission-prompts none [--allowedTools "<규칙>" …] [--max-budget-usd N] [--resume <세션 id>] [--append-system-prompt …]` — 프롬프트는 stdin, 작업 폴더 = cwd(그 폴더의 CLAUDE.md·사용자 설정은 평소처럼 읽는다).
- **청구**: 자식 프로세스 env 에 `ANTHROPIC_API_KEY` 가 있으면 그 키로 청구된다 — `stream-json` 의 첫 메시지(`type: system`, `subtype: init`)의 `apiKeySource` 가 `"ANTHROPIC_API_KEY"`. 구독 로그인이 있어도 키가 먼저다(stderr 에 「claude.ai connectors are disabled because ANTHROPIC_API_KEY … takes precedence」).
  `--output-format json`(결과 하나)에는 init 이 없어 키 출처를 못 본다 — 확인하려면 `stream-json --verbose`.
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
