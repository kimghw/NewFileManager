# display:none 으로 감췄다 다시 보일 때 남는 것 (Chrome)

패널·열을 「닫기」가 아니라 「접기」로 만들 때(DOM 은 두고 `display: none` 만) 무엇이 그대로인지. 스크롤 위치·DOM 상태·선택자 특이도는 2026-11-10 Playwright
Chromium(헤드리스)으로 확인(열 접기 — `artifacts/ui_colfold_2026-11-10/check_colfold.py`), 초점·세로쓰기 항목은 재지 않은 표준 동작이다.

- **스크롤 위치가 남는다**: `overflow: auto` 상자를 `display: none` 으로 감췄다가 다시 보이면 `scrollTop` 이 그대로다(600 → 600, 400 → 400 — 상자 자신이
  감춰지는 경우). 접기 전에 `scrollTop` 을 따로 적어 둘 필요가 없다.
- DOM 상태(펼친 `<details>`·`hidden` 속성·입력 중인 `<textarea>` 값·`aria-expanded`)는 당연히 그대로 — 지우고 다시 그리는 「닫기 → 열기」와 다른 점.
- 감춰진 동안 `scrollIntoView()`·`focus()` 는 아무 일도 하지 않는다(오류 없음). 초점이 감춰지는 요소 안에 있었으면 `document.activeElement` 가 `body` 로
  떨어지므로, 감추기 전에 보이는 요소(접힌 띠 단추 등)로 옮긴다.
- 부모 선택자로 한꺼번에 감출 때 `.box.folded > :not(.rail) { display: none }` 의 특이도는 (0,3,0) — `.box > header { display: flex }` (0,1,1) 같은 규칙을 이긴다.
  `[hidden] { display: none !important }` 를 쓰는 프로젝트라면 `hidden` 인 자식은 어차피 감춰져 있어 충돌하지 않는다.
- `writing-mode: vertical-rl` 인 글은 한글은 글자가 바로 선 채 위에서 아래로, 라틴 글자·숫자는 90° 돌아간다(「T1 L2」 같은 글이면 `text-orientation: upright` 검토).
