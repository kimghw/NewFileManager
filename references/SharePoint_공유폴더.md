# SharePoint 공유폴더 — OneDrive 로 동기화한 폴더에 쓰기

hwpx 공유([spec/spec_공유.md](../spec/spec_공유.md))를 만들며 확인한 외부 시스템의 동작. 「이 PC 실측」 과 「문서에서 읽음(실측 아님)」 을 갈라 적는다.
같이 확인한 다른 것: [uvicorn_둘째_서버.md](uvicorn_둘째_서버.md)(한 프로세스 안의 둘째 웹서버) · [브라우저_CSP_스타일.md](브라우저_CSP_스타일.md)(CSP 아래의 스타일).

## 1. 동기화 폴더를 찾는 법 (Windows)

- **이 PC 실측(2026-11-16, Windows 11 · 회사 OneDrive 로그인)**:
  - env `OneDrive` = `C:\Users\<사용자>\OneDrive`(회사 계정 하나뿐일 때 회사 폴더가 여기 든다) · `OneDriveCommercial` · `OneDriveConsumer` 는 비어 있었다 — **env 하나만 믿지 않는다**.
  - 레지스트리 `HKCU\Software\Microsoft\OneDrive\Accounts\<Business1 | Personal>` 의 값 `UserFolder` = 그 계정의 동기화 폴더(Business1 → 위 폴더, Personal 은 빈 값).
  - 레지스트리 `HKCU\Software\SyncEngines\Providers\OneDrive` 는 **없었다**(SharePoint 문서 라이브러리를 따로 「동기화」 한 것이 없는 PC).
- 문서에서 읽음(실측 아님): SharePoint 라이브러리를 「동기화」 하면 `HKCU\Software\SyncEngines\Providers\OneDrive\<id>` 아래 `MountPoint`(이 PC 의 폴더) · `UrlNamespace`(사이트 주소)가 생긴다.
  「OneDrive 에 바로 가기 추가」 로 건 SharePoint 폴더는 따로 뿌리가 생기지 않고 OneDrive 폴더(`UserFolder`) 안에 든다.
- 적용: `app/share_api.py` `sync_roots()` — env 셋 + 위 두 레지스트리. 고른 폴더가 그 안이 아니면 **알리기만** 한다(못 찾는 꼴이 있을 수 있어 막지는 않는다).

## 2. 동기화 폴더에 파일을 쓸 때

- 문서에서 읽음(Microsoft 「OneDrive 및 SharePoint 의 제한 사항」 — 실측 아님): **`~$` 로 시작하는 이름과 `.tmp` 임시 파일은 동기화하지 않는다.**
  → 바꿔 넣기용 임시 파일을 `~$<이름>.tmp` 로 두면 SharePoint 에 올라갔다 지워지는 일이 없다(`share.write_file`).
- 문서에서 읽음: 파일·폴더 이름에 못 쓰는 글자 `" * : < > ? / \ |` · 앞뒤 공백 · 예약 이름(`CON`·`PRN`·`AUX`·`NUL`·`COM0~9`·`LPT0~9`·`.lock`·`desktop.ini`·`_vti_` 가 든 이름).
  → `share.safe_stem` 이 그 글자를 빼고 끝의 점·공백을 정리한다.
- 바꿔 넣기(`os.replace`)는 동기화 프로그램이 그 파일을 잠깐 잡고 있으면 거절된다 — [Windows_파일_바꿔넣기.md](Windows_파일_바꿔넣기.md) 와 같은 대응(몇 번 다시).
- **SharePoint 는 올린 파일을 서버에서 고쳐 되돌려 줄 수 있다**(문서에서 읽음 — Office 문서의 속성 반영 등). hwpx 는 SharePoint 가 모르는 형식이라 그대로일 것으로 보이지만 **실측하지 않았다** —
  공유의 「밖에서 바뀐 파일은 덮지 않는다」(우리가 쓴 것의 sha256 과 견줌)가 이것을 「밖에서 바뀜」 으로 볼 수 있다. 실제 SharePoint 폴더에서 저절로 「밖에서 바뀜」 이 뜨면 이 항목부터 본다.
- 「파일 온디맨드」(자리 표시 파일)인 파일을 읽으면 그때 내려받는다 — 저장 전에 폴더의 파일을 읽어 견주는 길이 느려질 수 있다(실측 아님).
- **동기화 폴더의 파일은 그 SharePoint 폴더의 권한대로 읽힌다** — 앱의 키와는 다른 층이다(공유의 키는 손님 화면으로 들어와 쓰는 것만 막는다: spec_공유 ② §0).

## 3. 링크 바로가기(.url)

- 인터넷 바로가기 = INI 꼴 텍스트 `[InternetShortcut]` + `URL=<주소>`(줄 끝 CRLF). Windows 탐색기에서 누르면 기본 브라우저가 그 주소를 연다.
- 문서에서 읽음(실측 아님): SharePoint Online 의 「새로 만들기 › 링크」 가 만드는 것도 `.url` 파일이고, 웹의 문서 라이브러리에서 누르면 그 주소로 간다.
- 적용: 공유를 켜면 `<저장본 이름> 같이 쓰기.url` 을 공유폴더에 둔다(키는 넣지 않는다) — `share.url_file`.
