# 8114 웹서버 띄우기 — LLM = Claude CLI(구독 로그인) · Fable (2026-11-16 사용자 「cli로 해줘.. 왜 api 로 만 할필요가 없는데」 — API 키 계정의 크레딧이 다 떨어져서.
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
$env:NFM_LLM_BACKEND = 'cli'
# 2026-11-22 구독의 Fable 사용 한도(429)에 닿아 사용자 답 「Opus 5.5로 재시작」 — 한도가 풀리면 사용자가 말할 때 'claude-fable-5-2' 로 되돌린다.
$env:NFM_LLM_MODEL_FORCE = 'claude-opus-5-5'
cmd /c "python -m uvicorn app.server:app --host 127.0.0.1 --port 8114 >> artifacts\5b_server\server-8114.log 2>&1"
