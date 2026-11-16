# uvicorn — 한 프로세스 안에 둘째 웹서버를 스레드로

hwpx 공유의 공유 포트([spec/spec_공유.md](../spec/spec_공유.md) ② §3 — 8114 서버 프로세스 안에서 손님 앱을 8119 에 따로 띄움)를 만들며 확인한 것. 2026-11-16 이 PC(uvicorn 0.51 · FastAPI 0.140 · Starlette 1.3.1 · Python 3.12).

## 사실

- **이 PC 실측**: `uvicorn.Server(uvicorn.Config(app, host, port)).run()` 을 **보통 스레드**에서 돌릴 수 있다. 끄기 = `server.should_exit = True` 뒤 스레드 `join`.
  `server.started` 가 켜지면 듣는 중이다. 주 서버(8114)의 요청 처리와 서로 막지 않는다(이벤트 루프가 따로).
- 소스에서 읽음: 신호 처리기(`capture_signals`)는 주 스레드에서만 건다 — 스레드에서 돌려도 Ctrl+C 처리를 가로채지 않는다.
- 소스에서 읽음: 포트를 못 열면 uvicorn 은 오류를 기록하고 `sys.exit(1)` — 스레드 안에서는 그 스레드만 끝나고 **까닭이 돌아오지 않는다**.
- **이 PC 실측**: FastAPI 앱에 `app.router.on_startup.append(fn)` 으로 건 함수는 서버가 뜰 때 돈다(재시작 뒤 켜져 있던 공유의 포트가 다시 열림).
  `TestClient(app)` 를 `with` 없이 쓰면 돌지 않는다(시험에서 포트가 안 열린다).
- **이 PC 실측**: 순수 ASGI 미들웨어(`app.add_middleware(클래스)`)로 응답 본문을 지나가며 읽을 수 있다 — `http.response.body` 의 `more_body` 가 거짓인 조각이 마지막. 응답은 그대로 보낸다.
  미들웨어 안에서 바로 응답을 낼 때(`await Response(...)(scope, receive, send)`)는 머리말을 다는 `send` 감싸개를 거쳐야 그 응답에도 머리말이 붙는다.
- `0.0.0.0` 으로 처음 들으면 Windows 방화벽이 허용을 물을 수 있다(허용 전에는 다른 PC 에서 못 들어온다 — 실측 아님: 이 PC 에서는 127.0.0.1 로만 검사했다).

## 대응

- 띄우기 전에 같은 주소·포트로 소켓을 `bind` 해 보고(되면 닫고) 띄운다 — 못 여는 까닭을 직접 얻는다. 띄운 뒤에는 `server.started` 가 켜지거나 스레드가 끝날 때까지 잠깐 기다려 결과를 정한다.
- 끌 때 바로 닫지 않아야 할 때가 있다 — 접속해 있던 화면이 「끝났다」 는 응답을 받을 틈(공유는 4초).
- 적용: `app/share_api.py` `_Listener`(start · stop · stop_later) · `_boot` · `_Observe` · `_Guard`.
