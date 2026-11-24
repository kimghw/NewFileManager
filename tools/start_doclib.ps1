# 문서 라이브러리 서버(doclib/ — 자료 문서 보관 · 자료 추출(MD)) 띄우기 — 포트 8121. 8114 와 따로 선 서버다(spec_양식작성 ② §2 — 2026-11-24 사용자
# 「이 문서 관리 라이브러리는 별도 서버에서 관리해도 될거 같은데? … 자료추출도 같이 좀분리하고」).
# LLM = Claude CLI(구독 로그인) · Opus 5.5 — 8114 의 띄우개와 같은 까닭으로 키를 넣지 않고 물려받은 것도 지운다(references/Claude_CLI_헤드리스.md).
# 띄우는 법(세션과 떨어진 프로세스로): Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'powershell -NoProfile -ExecutionPolicy Bypass -File E:\dev\NewFileManager\tools\start_doclib.ps1'; CurrentDirectory = 'E:\dev\NewFileManager' }
# 확인: GET http://127.0.0.1:8121/api/health → ok true · llm.available true. 끄기 전에 도는 추출이 없는지 본다(GET /api/docs 의 extracts[].state running — 끄면 「끊김」 이 된다).
$ErrorActionPreference = 'Stop'
Set-Location 'E:\dev\NewFileManager'
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
$cli = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
if (Test-Path $cli) { $env:NFM_CLAUDE_CLI = $cli }
New-Item -ItemType Directory -Force 'artifacts\5b_server' | Out-Null
cmd /c "python -X utf8 -m uvicorn doclib.server:app --host 127.0.0.1 --port 8121 >> artifacts\5b_server\server-doclib.log 2>&1"
