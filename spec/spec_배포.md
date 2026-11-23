# 배포 · 외부 접속

이 PC(Azure VM sscb)의 NewFileManager 서버(8114)를 바깥에서 HTTPS · 로그인으로 쓰게 여는 것. 서버를 띄우는 법(띄우개 · 8114 하나만)은 [CLAUDE.md](../CLAUDE.md) 「웹서버」 절이 원본이다.
이 PC 의 Caddy · Azure DNS 동작은 옛 프로젝트의 [외부공개_Caddy.md](../../FileMergeManager/references/외부공개_Caddy.md) 가 원본이다.

## ① 질의 · 요청 히스토리

- 2026-11-23 질의 "현재 이거 웹서버 주소가?" → `http://127.0.0.1:8114`(이 PC 안에서만). 이어서 "rndsscb.co.kr 이거" → 그 주소는 DNS 에 없음 · 이 PC 의 도메인은 rndsscb.com 이고 8114 는 어느 하위 도메인에도 이어져 있지 않음(옛 FileMergeManager 만 filemerge.rndsscb.com).
  이어서 "files.rndsscb.com 이걸로 해줘" → ② §1. 인증은 에이전트가 권장한 「Caddy 기본 인증」 으로(앱에 로그인이 없다 — 에이전트 판단 · 사용자 확인 전).
- 2026-11-23 사용자(바깥 주소에서 올리다 413 — 서버 기록 `POST /api/docs?ask=1&job=u_d05846b0 413`: 앱의 파일당 한도 200MB) **"파일 업로드 할때 200MB 제한이 있네 이거 풀어 주고"** → ② §1 「올리기 한도」 · ③ 같은 날.
  「풀어」 를 한도를 없애는 것이 아니라 **크게 올리는 것**(파일 하나 2 GiB)으로 읽은 것은 에이전트 판단(사용자 확인 전 — 올린 파일은 서버 메모리에 통째로 읽는다: RAM 32GB).

## ② 확정 사양

### 1. 공개 주소 · 인증 (Caddy)

- 주소 `https://files.rndsscb.com` → `127.0.0.1:8114`. 앱은 전처럼 127.0.0.1 에만 묶인다 — 바깥 요청은 Caddy 의 TLS 종단 + 기본 인증을 거친다.
- DNS: Azure DNS 영역 `rndsscb.com`(리소스 그룹 `sscb_ontology`) A 레코드 `files` → 20.196.66.231(이 VM).
- 사이트 블록 = [deploy/Caddyfile](../deploy/Caddyfile) — 이 PC 의 중앙 Caddyfile(`C:\Users\SSCB\kakao_stock\scripts\Caddyfile`)이 import 한 줄로 싣는다. 바꾼 뒤 `caddy validate --config <그 파일>` → `caddy reload --config <그 파일>`.
- 계정: `deploy/auth.caddy`(한 줄 `사용자이름 bcrypt해시` · 저장소에 올리지 않음 — `deploy/.gitignore`). 계정 하나 · 비밀번호는 사용자가 정한 것(2026-11-23 — 처음 만든 무작위 비밀번호를 바꿈). 계정 · 비밀번호 값은 저장소에 적지 않는다.
  바꾸려면 `caddy hash-password --plaintext <새 비밀번호>` 로 그 줄을 바꾸고 reload.
- **다른 출처의 변경 요청은 막는다**: 기본 인증은 브라우저가 다른 사이트가 시킨 요청에도 붙인다 — GET · HEAD · OPTIONS 가 아니고 `Origin` 이 `https://files.rndsscb.com` 이 아니면 403.
- **올리기 한도**(2026-11-23 — 전에는 앱 200MB · Caddy 600MB): 앱의 파일 하나 한도 `NFM_MAX_UPLOAD_MB` 기본 **2048 MiB**(`app/server.py` `MAX_MB` — 올리기 · hwp 변환 · 양식 파일 저장이 같이 씀) ·
  Caddy 의 요청 본문 한도 **2600MB**(앱 한도보다 크게 — 여러 부분 본문의 머리) · 그림이 든 hwpx 는 해제 크기가 파일 크기와 비슷해 zip 해제 한도 `FMM_ZIP_MAX_MB` 기본도 **4096 MiB**(`app/zip_guard.py` — 전 1024).
  서식 복사의 「다른 문서에서 가져오기」(`style_api.UPLOAD_MB` 100) · 에이전트 자료(20MB)는 따로이고 그대로다.
- 공유의 손님 포트(8119 — [spec_공유.md](spec_공유.md))는 이 주소에 들지 않는다.

## ③ 구현 상태

- 2026-11-23 구현: `deploy/Caddyfile` · `deploy/.gitignore` · `deploy/auth.caddy` 만듦. Azure DNS A 레코드 `files` 는 사용자가 직접 추가(에이전트의 `az` 실행은 권한 확인에서 막힘) —
  로컬 · 8.8.8.8 모두 20.196.66.231. 중앙 Caddyfile 에 import 한 줄 → `caddy validate` → `caddy reload`.
  확인(curl, 인증서 검증 켬): 로그인 없이 `/` 401 · 틀린 비밀번호 401 · 로그인 `/` · `/workflow` 200 · `/api/headings/llm` 200(`cli` · `claude-opus-5-5` · available) · 정적 파일 200 ·
  다른 출처 POST 403 · 같은 출처 POST 는 앱까지 감(없는 경로 404) · 같은 Caddy 의 filemerge(302) · guidelines(401) 그대로.
- 2026-11-23 **올리기 한도**(② §1 — ① 같은 날): `app/server.py`(`MAX_MB` 기본 2048) · `app/zip_guard.py`(4096) · `deploy/Caddyfile`(`max_size 2600MB`) → `caddy validate` → `caddy reload`(바깥 주소 401 그대로). 8114 다시 켬(같은 날 16:21 — newfilemanager-fa 세션이 사용자 요청으로 · 서버 시작이 고친 파일보다 뒤인 것을 확인).

## ④ 미결 · 후속

- 8114 는 손으로 띄우는 서버다(띄우개 [tools/start_8114.ps1](../tools/start_8114.ps1)) — PC 를 다시 켜면 바깥 주소도 꺼진다. FileMergeManager 처럼 작업 스케줄러로 상시 띄울지는 사용자 결정(한글 COM 때문에 로그온 · 대화형이어야 한다 — 위 참고 글).
- 앱에 사용자 계정이 없다 — 접속한 사람 모두가 같은 작업 · 같은 LLM(구독)을 쓴다. 여러 사람이 따로 쓰려면 앱 로그인이 필요하다.
- 보안: 사용자가 정한 비밀번호는 짧고 짐작하기 쉽다 — 주소가 공개 DNS 에 있어 누구나 로그인 창까지는 온다. 긴 비밀번호로 바꿀지는 사용자 결정.
