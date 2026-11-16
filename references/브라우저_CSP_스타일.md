# 브라우저 — 엄격한 CSP 아래에서 스크립트가 주는 스타일

hwpx 공유의 손님 화면([spec/spec_공유.md](../spec/spec_공유.md) ② §3·§6 — `app/static/share/`)을 만들며 확인한 것. 2026-11-16 Chromium(Playwright).

## 사실

- **실측**: 응답 머리말 `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'`(`'unsafe-inline'` 없음) 아래에서도
  스크립트가 `el.style.x = …` · `el.style.setProperty(…)` 로 주는 스타일은 **막히지 않는다** — 콘솔에 CSP 위반 0(문단마다 글꼴 크기·여백, 표 칸마다 괘선을 이 길로 준다).
- 알려진 것(실측 아님 — 이 화면에서는 쓰지 않아 부딪치지 않았다): 막히는 것은 HTML 의 `style="…"` 속성, `<style>` 요소, `setAttribute("style", …)`·`cssText` 로 넣는 것.
- 알려진 것(실측 아님 — 처음부터 파일로만 두었다): `script-src 'self'` 면 HTML 안에 직접 적은 `<script>…</script>` 는 돌지 않는다 — 화면의 스크립트·스타일은 모두 같은 출처의 파일로 둔다.
- `contenteditable="plaintext-only"` 는 지원 여부를 요소에 넣어 보고 되읽어 가린다(주인 화면 `app.js` 의 `PLAIN` 과 같은 법 — 관련 [브라우저_contenteditable_선택.md](브라우저_contenteditable_선택.md)).

## 대응

- 사용자 데이터로 화면을 그리는 공개 화면은 `'unsafe-inline'` 없이 둔다 — 모양은 CSSOM(`el.style`)으로, 글은 `textContent` 로만.
- 화면이 아닌 응답(JSON · 그림)에는 `default-src 'none'; frame-ancestors 'none'; sandbox` — 문서 안의 SVG 그림을 주소로 직접 열어도 그 출처에서 스크립트가 돌지 않게.
- 적용: `app/share_api.py` `_PAGE_CSP` · `_DATA_CSP` · `_Guard`, `app/static/share/guest.js`(스타일은 모두 `el.style`).
