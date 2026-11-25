# 8114 웹서버 띄우기 — LLM = API(fable 스킬의 키들) · Fable (2026-11-25 — 아래 NFM_LLM_KEYS 줄). 그 전: Claude CLI(구독 로그인) · Fable (2026-11-16 사용자 「cli로 해줘.. 왜 api 로 만 할필요가 없는데」 — API 키 계정의 크레딧이 다 떨어져서.
# 전: 2026-11-12 「api 키로 해서 fable로 해줘」 → API 키 · Fable). CLI 는 자식 env 에 ANTHROPIC_API_KEY 가 있으면 구독이 아니라 그 키로 청구한다(references/Claude_CLI_헤드리스.md) —
# 그래서 키를 넣지 않고, 물려받은 것도 지운다. 키로 돌리려면 NFM_LLM_BACKEND=api 와 키 읽기를 되살린다(git 기록 fdb0213 의 이 파일).
# 띄우는 법(CLAUDE.md 「웹서버」): Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'powershell -NoProfile -ExecutionPolicy Bypass -File E:\dev\NewFileManager\tools\start_8114.ps1'; CurrentDirectory = 'E:\dev\NewFileManager' }
$ErrorActionPreference = 'Stop'
Set-Location 'E:\dev\NewFileManager'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
$cli = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
if (Test-Path $cli) { $env:NFM_CLAUDE_CLI = $cli }
else { cmd /c "echo [start_8114] claude.exe not found at %USERPROFILE%\.local\bin - falling back to PATH >> artifacts\5b_server\server-8114.log" }
# 2026-11-25 사용자 "fable 키를 사용할 수 있도록 해줘": fable 스킬에 등록한 API 키들(~/.claude/fable/config.json — 차례대로 · 쓸 수 없는 키면 다음 키: app/llm_keys.py)로 Fable 을 부른다.
# 키 글은 이 파일 · env · 명령 줄에 안 넣는다(서버가 그 파일에서 읽는다). 전: 2026-11-22 구독의 Fable 한도(429) → CLI · Opus 5.5, 그 전 2026-11-16 CLI · Fable.
# 구독 CLI 로 되돌리려면: NFM_LLM_BACKEND='cli' · NFM_LLM_KEYS 줄 지우기 · 모델은 사용자가 정한 것.
# Codex CLI(모델 gpt-… — 양식 검토의 LLM2 = astra: 2026-11-25 사용자 「claude fable, 하고 codex astra 모두 추출해서 협의」) — WMI 로 띄우면 사용자 PATH 의 npm 폴더가 안 보일 수 있어 경로를 건다.
$codex = Join-Path $env:APPDATA 'npm\codex.cmd'
if (Test-Path $codex) { $env:NFM_CODEX_CLI = $codex }
$env:NFM_LLM_BACKEND = 'api'
$env:NFM_LLM_KEYS = 'fable'
$env:NFM_LLM_MODEL_FORCE = 'claude-fable-5-2'
# 계정(로그인 · 가입 승인 · 계정마다 작업 폴더 — spec/spec_계정.md): 2026-11-24 사용자 "앱에 계정별로 할 수 있게 해줘. 관리자 모드 sscb/sscb 로 하고 승인할 수 있도록". 이 줄을 빼면 로그인 문이 없다(전과 같은 동작).
$env:NFM_AUTH = '1'
cmd /c "python -m uvicorn app.server:app --host 127.0.0.1 --port 8114 >> artifacts\5b_server\server-8114.log 2>&1"
