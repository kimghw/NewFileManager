# 같은 앱을 같은 출처 iframe 으로 한 번 더 띄울 때 (Chrome)

한 화면에 문서 둘을 나란히 보이려고, 문서 하나만 다루게 짜인 단일 페이지 앱을 `<iframe src="/?peek=<id>#w=<id>">` 로 한 번 더 띄운 경우.
2026-11-11 Playwright Chromium(헤드리스)으로 확인한 것과 표준 동작(재지 않음)을 나눠 적는다.

확인한 것:
- **바깥에서 안쪽 함수를 바로 부를 수 있다**: 일반 스크립트(모듈 아님) 최상위의 `function` 선언은 그 창의 속성이라 `iframe.contentWindow.fn(…)` 으로 부른다. 메시지 주고받기(postMessage)가 필요 없다.
  안쪽이 아직 읽는 중이면 `fn` 이 없어 예외 — `try/catch` 로 지나가게 한다.
- **안쪽의 `scrollIntoView({ block: "center" })` 는 바깥을 밀지 않는다** — 바깥 문서가 넘치지 않을 때(body `overflow: hidden`, 열이 창 높이에 맞음): 바깥 `scrollTop` 0 그대로.
- **`display: none` 으로 접은 iframe 은 살아 있다**: 다시 보이면 그려 둔 문서가 그대로이고 새로 읽지 않는다(Playwright 의 Frame 객체도 그대로 유효 — 스크롤 위치는 재지 않음).
- **비용**: 안쪽도 같은 스레드에서 그린다 — 204쪽·16,842문단 문서를 옆에 하나 더 띄우는 데 +4.0~4.6초, 그동안 바깥도 멈칫한다.
- **읽기 전용으로 만들기**: 문단의 `contentEditable` 을 끄는 것만으로는 모자란다(표 메뉴·끌기·단축키 같은 다른 길이 남음) — 요청을 보내는 공용 함수 한 곳에서 GET 밖 메서드를 막으면
  어느 길로도 서버가 안 바뀐다(검사: 안쪽 프레임이 보낸 요청을 `request.frame.url` 로 갈라 GET 밖 0건).
- **`@media (max-width …)` 는 iframe 의 폭으로 판정한다**(2026-11-11 실측): 바깥 창이 1760px 이어도 폭 640px iframe 안에서는 앱의 「좁은 창」 규칙(≤ 820px)이 적용된다 — 문서 보기 위 여백이 바깥 28px · 안쪽 16px 이라
  두 문서의 첫 쪽 위끝이 12px 어긋났다. 나란히 맞춰야 하는 값은 안쪽 전용 규칙(`body.peek …`)으로 바깥과 같게 덮는다.
- **최상위 `const` 값은 `contentWindow.eval('state.zoom')` 으로 읽는다**(2026-11-11 — 검사 스크립트에서. 아래 「최상위 const 는 창의 속성이 아니다」 의 우회).
- **바깥 줄과 iframe 열의 높이 맞추기**(2026-11-11 실측 — 두 가지를 해 봄): ⓐ `ResizeObserver` 로 바깥 줄을 `{ box: "border-box" }` 로 지켜보다가 높이를 CSS 변수로 적는 길 — `display: none` 으로 접힐 때 0 으로 알려 주고,
  콜백에서 `borderBoxSize[0].blockSize`(소수 px)를 적으면 같은 화면 갱신 안에서 다시 배치돼 어긋난 프레임이 없다(위끝 차 0px). 처음 지켜볼 때 0×0 이면 알림이 안 오니 한 번 직접 적용한다.
  ⓑ **CSS subgrid** — 열을 바깥 격자의 여러 행에 걸치고 `display: grid; grid-template-rows: subgrid` 로 두면 열 안의 머리·iframe 이 바깥 행에 그대로 맞는다(스크립트 없음 · Chromium 에서 위끝·아래끝 차 0px).
  iframe 은 `height: 100%` 로 그 행을 채운다. 같은 격자에서 다른 줄을 그 열 위까지 걸치게(`grid-column: 1 / 3`) 겹쳐 놓을 수 있고, 뒤에 그려지는 열보다 위로 올리려면 격자 항목에 `z-index` 만 주면 된다(position 없이도 먹는다).
  이 프로젝트는 ⓑ 로 정함(사용자가 ⓐ 식의 「높이 따라가기」 를 물림).
- **바깥 도구 줄로 안쪽 화면 조작하기**(2026-11-11 실측): 안쪽도 같은 앱이라 같은 id 의 단추가 (감춰진 채) 있다 — 바깥 단추의 누름을 캡처 단계에서 막고 `iframe.contentDocument.getElementById(id).click()` 으로 넘기면
  안쪽 처리기가 안쪽 상태로 그대로 돈다(`display: none` 인 단추·체크 상자도 `click()` 은 먹는다). 눌림·글은 안쪽 요소의 속성을 바깥에 베껴 칠한다. 체크 상자의 누름을 `preventDefault()` 로 막으면
  브라우저가 처리 뒤에 `checked` 를 되돌리므로, 베껴 칠하기는 `setTimeout(…, 0)` 으로 그 뒤에 한다(같은 처리기 안이나 microtask 에서 칠하면 되돌려진다). 안쪽이 누른 것을 바깥에 알릴 때는 안쪽에서 `parent.fn()`.
  안쪽의 설정 저장(`localStorage`)은 막아야 한다 — 아래 「같은 저장소」.

표준 동작(이번에 재지 않음):
- 열 폭을 마우스로 끄는 동안 마우스가 iframe 위로 들어가면 바깥의 `pointermove` 가 끊길 수 있다 — 끄는 동안 iframe 에 `pointer-events: none`(포인터 캡처를 쓰면 괜찮지만 함께 둔다).
- `iframe.src` 를 **`#` 뒤만 다른 주소**로 바꾸면 새로 읽지 않는다(같은 문서 안 이동 — 앱이 `hashchange` 를 안 들으면 내용이 안 바뀐다). 문서를 바꿔 띄울 때는 `?` 뒤(query)를 다르게 한다.
  같은 일을 `page.goto()` 로는 2026-11-10 에 겪었다(주소의 `#w=` 만 바꾸면 작업이 안 열림).
- 최상위 `const`·`let` 은 창의 속성이 아니다 — `contentWindow.state` 는 `undefined`(함수만 건너 부를 수 있다).
- `localStorage` 는 바깥과 같은 저장소다 — 안쪽 화면이 보기 설정(접힘·확대 기억)을 쓰면 바깥 설정이 바뀐다. 안쪽에서는 기억하는 조작을 감춘다.
- `history.replaceState(null, "", "#…")` 처럼 상대 주소로 `#` 만 바꾸면 query(`?peek=…`)는 남는다.
