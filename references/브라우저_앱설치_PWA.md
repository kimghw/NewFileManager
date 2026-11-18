# 브라우저 「앱으로 설치」(PWA) — Chromium(Edge·Chrome)

2026-11-18 실측(이 PC · Edge 157.0.4341.60 · Chrome 157.0.8103.79 · Playwright 1.55 · 서버 `http://127.0.0.1:8114`). 이 앱에 쓴 곳 = [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ② §9 「앱으로 설치」.

## 설치 조건 (이것만으로 오류 0)

- 페이지 `<head>` 의 `<link rel="manifest" href="…">` + 설명 파일에 `name`(또는 `short_name`) · `start_url` · `display`(`standalone`·`minimal-ui`·`fullscreen`) · **192px 와 512px PNG 아이콘**.
- **서비스 워커는 필요 없다** — 서비스 워커 없이 `Page.getInstallabilityErrors` 가 `[]` 이고 `beforeinstallprompt` 가 온다(옛 조건 「오프라인에서 도는 fetch 처리기」 는 없어짐).
- `http://127.0.0.1` · `http://localhost` 는 안전한 출처로 쳐서 HTTPS 없이 설치된다. 다른 PC 에서 IP 로 들어오는 `http://` 는 안전한 출처가 아니라 설치가 안 된다(HTTPS 필요).
- 설명 파일이 `/static/` 아래에 있으면 `scope` 기본값이 `/static/` 이 된다 — 앱 전체를 앱 창에 담으려면 `"scope": "/"` · `"start_url": "/"` 를 적는다(`id` 도 `/` 로 두면 주소가 바뀌어도 같은 앱).
- 설명 파일의 형식: Python 3.12 `mimetypes` 가 `.webmanifest` → `application/manifest+json` 을 안다(Starlette `StaticFiles` 가 그대로 보냄).

## 페이지 안의 설치 단추

- 브라우저가 설치할 수 있다고 보면 `window` 에 `beforeinstallprompt` 를 보낸다 — `e.preventDefault()` 로 브라우저 자체 안내를 막고 붙들어 두었다가, 사람이 누를 때 `e.prompt()` → `await e.userChoice`(`{outcome: "accepted" | "dismissed"}`).
  `prompt()` 는 그 이벤트로 **한 번만** 부를 수 있다. 설치를 마치면 `appinstalled`.
- 이미 설치한 브라우저 · 앱 창 안(`matchMedia("(display-mode: standalone)")` 등) · Firefox(데스크톱 PWA 설치 없음)에서는 `beforeinstallprompt` 가 오지 않는다 — 단추는 그 이벤트가 왔을 때만 보이는 것이 맞다.
- 수동 길: Edge `…` → 앱 → 이 사이트를 앱으로 설치 · Chrome `⋮` → 전송, 저장, 공유 → 페이지를 앱으로 설치. 설치 없이 앱 창만: `msedge --app=<주소>`.

## 머리 없는 브라우저로 확인하기

- CDP `Page.getInstallabilityErrors`(→ `installabilityErrors: []` 이면 설치 가능) · `Page.getAppManifest`(→ `url` · `errors`).
- Playwright 의 보통 컨텍스트는 시크릿 창이라 「in-incognito」 로 막힌다 — **`launch_persistent_context(임시 폴더, channel="msedge" | "chrome", headless=True)`** 로 띄운다. 그러면 머리 없는 상태에서도 `beforeinstallprompt` 가 실제로 온다.
- 파일을 고치기 전에 확인하려면 `page.route("<주소>/", …)` 로 받은 HTML 에 `<link rel="manifest">` 를 끼워 `route.fulfill(response=r, body=…)` — 설치 판정은 그 응답으로 한다.
