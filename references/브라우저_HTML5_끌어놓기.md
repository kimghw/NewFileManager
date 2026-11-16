# 브라우저 HTML5 끌어 놓기(drag and drop) — dragstart 안의 모양 바꿈 · Playwright `drag_to`

2026-11-16 확인(「템플릿 관계」 서식 갈래 카드를 대표 카드에 끌어 놓는 기능 — spec_hwpx_웹편집 ② §8-2 「대표 미리보기」). Playwright 1.55.0 · Chromium(헤드리스).

## 본 것

- `li draggable=true` 카드의 `dragstart` 처리기가 **그 자리에서 곧바로** 목록(`ul`)에 클래스를 달아 놓을 곳(카드 위쪽)에 흐름 안 안내 줄(`display: block`)을 보이게 하자,
  끄는 카드가 약 25px 아래로 밀렸다. 이때 Playwright 의 `Locator.drag_to(target, timeout=15000)` 가 **돌아오지 않았다** — 정한 시간이 지나도 안 끝나고 약 6분 뒤
  `Connection closed while reading from the driver` 로 끝났다(그 사이 `page.evaluate` 도 못 부름). 같은 화면에서 끌기 대신 단추 누름(`click`)은 바로 됐다.
- 두 가지를 같이 바꾸자 `drag_to` 가 1초 안에 끝나고 `drop` 처리기가 돌았다:
  1. `dragstart` 안에서는 `dataTransfer` 만 채우고, 클래스 달기(끄는 카드 흐리게 · 목록에 「끄는 중」)는 `setTimeout(…, 0)` 으로 다음 차례에.
  2. 놓을 곳 안내를 흐름 밖으로 — 놓을 카드에 `position: relative`, 안내는 `position: absolute; inset: 0; pointer-events: none` 으로 **겹쳐** 그림(자리가 안 밀림).
  둘 가운데 어느 쪽이 결정적이었는지는 따로 가르지 않았다.

## 일반 지식(브라우저)

- Chrome 은 `dragstart` 처리기 안에서 끄는 요소를 감추거나 옮기면 끌기를 곧바로 끝낼 수 있다(`dragend` 가 바로 옴) — 널리 쓰는 처방은 그런 바꿈을 다음 차례(`setTimeout 0` · `requestAnimationFrame`)로 미루는 것.
- `dragover`·`dragenter` 에서 `preventDefault()` 를 해야 그 요소가 놓을 곳이 된다. `dragover` 안에서는 `dataTransfer.getData` 를 못 읽으므로(보호 모드) 무엇을 끄는지는 처리기 밖의 변수에 둔다.
- 놓은 뒤(`drop`) 끄던 요소를 다시 그려 DOM 에서 떼어도 `dragend` 는 떼어진 그 요소에 온다 — 정리는 문서 전체에서 클래스로 찾아 지운다.
- 터치 화면에서는 HTML5 끌어 놓기가 안 된다 — 누름으로도 되는 길을 같이 둔다.
