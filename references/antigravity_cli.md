# Google Antigravity — winget 설치(Windows)

2026-11-15 이 PC 에 CLI 를 설치하며 확인한 것.

- winget 패키지(출처 `winget`): `Google.Antigravity`(2.32.1) · `Google.AntigravityCLI`(1.5.9) · `Google.AntigravityIDE`(2.7.0). `winget search antigravity` 에는 이름에 antigravity 꼬리표만 단 남의 도구도 여럿 나온다 — id 로 정확히 고른다(`-e --id`).
- CLI 설치: `winget install --id Google.AntigravityCLI -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity`
  — 설치 파일은 `storage.googleapis.com/antigravity-public/antigravity-cli/<판>/windows-x64/cli_windows_x64.exe`, winget 이 해시를 검증한다.
- 명령 이름은 **`agy`**(winget 이 명령 줄 별칭으로 더한다): `%LOCALAPPDATA%\Microsoft\WinGet\Links\agy.exe`. `agy --version` → `1.5.9`.
- 이미 열려 있던 터미널은 PATH 를 다시 읽지 않는다 — 새 터미널에서 잡힌다. 처음 실행하면 Google 계정 로그인이 필요하다(사람이 한다).
