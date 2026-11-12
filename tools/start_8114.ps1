# 8114 웹서버 띄우기 — LLM = API 키 · Fable (2026-11-12 사용자 「api 키로 해서 fable로 해줘」 → 물어서 받은 답 「API 키 · Fable, 재시작」).
# 키는 Claude Code 사용자 설정(%USERPROFILE%\.claude\settings.json 의 env.ANTHROPIC_API_KEY)에서 읽어 이 프로세스의 env 에만 둔다 — 명령 줄·파일에 안 남긴다.
# 띄우는 법(CLAUDE.md 「웹서버」): Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'powershell -NoProfile -ExecutionPolicy Bypass -File E:\dev\NewFileManager\tools\start_8114.ps1'; CurrentDirectory = 'E:\dev\NewFileManager' }
$ErrorActionPreference = 'Stop'
Set-Location 'E:\dev\NewFileManager'
$settings = Join-Path $env:USERPROFILE '.claude\settings.json'
if (-not $env:ANTHROPIC_API_KEY -and (Test-Path $settings)) {
    $env:ANTHROPIC_API_KEY = (Get-Content -Raw -Encoding UTF8 $settings | ConvertFrom-Json).env.ANTHROPIC_API_KEY
}
if (-not $env:ANTHROPIC_API_KEY) {
    cmd /c "echo [start_8114] ANTHROPIC_API_KEY not found - LLM calls will fail >> artifacts\5b_server\server-8114.log"
}
$env:NFM_LLM_BACKEND = 'api'
$env:NFM_LLM_MODEL_FORCE = 'claude-fable-5-2'
cmd /c "python -m uvicorn app.server:app --host 127.0.0.1 --port 8114 >> artifacts\5b_server\server-8114.log 2>&1"
