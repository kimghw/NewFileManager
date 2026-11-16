# Google Antigravity — winget 설치(Windows)

2026-11-15 이 PC 에 CLI 를 설치하며 확인한 것.

- winget 패키지(출처 `winget`): `Google.Antigravity`(2.32.1) · `Google.AntigravityCLI`(1.5.9) · `Google.AntigravityIDE`(2.7.0). `winget search antigravity` 에는 이름에 antigravity 꼬리표만 단 남의 도구도 여럿 나온다 — id 로 정확히 고른다(`-e --id`).
- CLI 설치: `winget install --id Google.AntigravityCLI -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity`
  — 설치 파일은 `storage.googleapis.com/antigravity-public/antigravity-cli/<판>/windows-x64/cli_windows_x64.exe`, winget 이 해시를 검증한다.
- 명령 이름은 **`agy`**(winget 이 명령 줄 별칭으로 더한다): `%LOCALAPPDATA%\Microsoft\WinGet\Links\agy.exe`. `agy --version` → `1.5.9`.
- 이미 열려 있던 터미널은 PATH 를 다시 읽지 않는다 — 새 터미널에서 잡힌다. 처음 실행하면 Google 계정 로그인이 필요하다(사람이 한다).

## 로그인(2026-11-16 확인)

- `login` 하위 명령은 **없다**(`agy --help` 의 하위 명령: acp · agent(s) · changelog · help · install · mcp · mic-serve · models · plugin(s) · remote-control · update).
  로그인은 **인자 없이 `agy` 를 띄운 대화형 화면**에서 한다 — 에이전트의 비대화형 셸(stdin 없음)에서는 못 하니 새 콘솔 창으로 띄워 사람이 마친다
  (PowerShell: `Start-Process agy -WorkingDirectory <폴더>`).
- 로그인 여부 확인: `agy models` — 안 됐으면 `Error: Please sign in to view available models. Launch the CLI without arguments to sign in.`, 되면 모델 목록.
- 로그인 전에는 `%USERPROFILE%` · `%APPDATA%` · `%LOCALAPPDATA%` 아래에 agy·antigravity·gemini 이름의 설정 폴더가 없었다(설정은 첫 실행 때 생긴다).
  로그인 뒤 CLI 설정은 `%USERPROFILE%\.gemini\antigravity-cli\settings.json`(처음엔 `trustedWorkspaces` 만 — 기본 모델은 적혀 있지 않다).

## 비대화형 실행 · 음성 받아쓰기(2026-11-16 확인)

- 한 번 묻고 답만 받기: `agy -p "<프롬프트>" [--model <id>] [--effort low|…|max] [--mode accept-edits|auto|plan] [--print-timeout 600s]`.
  작업 폴더 = 띄운 현재 폴더(그 폴더의 파일을 도구로 읽는다). 모델 목록 `agy models` — Gemini 4 Argon·Hydrogen · Gemini 3.8 Flash · Claude Opus/Sonnet 5.5 · GPT-OSS 120B.
- **음성 파일 받아쓰기(STT)가 된다** — 폴더의 오디오를 `read_file` 도구로 읽으면 `audio/wav` 스트림을 모델이 직접 듣는다(따로 STT 엔진·ffmpeg 없음). 시험(기본 모델, 프롬프트 「verbatim · 못 들으면 지어내지 말 것」):
  - 영어 WAV 14.4 s(Windows TTS 로 만든 정답 있는 글) → **낱말 전부 맞음**(숫자는 「2027 · November 20th · 350 million」 처럼 숫자로 바꿔 씀) · 약 32 s.
  - 한국어 WAV 52.7 s(44.1 kHz 스테레오 9.3 MB, 정답 글 없음) → 문장 단위로 자연스러운 한국어 전사(파일 이름에 없는 화자·내용을 알아냄 — 실제로 들은 것) · 약 35 s.
  - 오디오는 Google 쪽으로 올라간다 — 개인 녹음을 보낼 때는 사람에게 먼저 묻는다.
- 참고: 이 PC 의 Windows 음성 합성(SAPI·OneCore)에는 영어 목소리(David·Zira·Mark)만 있고, `edge-tts` 패키지는 서버가 `403`(판이 낡음)으로 막아 한국어 시험 음성은 만들지 못했다.
