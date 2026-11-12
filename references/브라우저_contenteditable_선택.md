# 브라우저 — 따로 떨어진 contenteditable 사이의 글 선택 (2026-11-10 실측, Chromium · Playwright)

문단마다 `contenteditable`(또는 `plaintext-only`) 상자를 따로 두고 그 부모는 편집 불가인 화면(이 프로젝트 문서 보기 `.para`)에서 확인한 것.

- **마우스로 끌어도 글 선택은 시작한 편집 상자를 넘지 못한다.** 첫 문단에서 누르고 셋째 문단까지 끌면 선택은 첫 문단 안에서만 늘어난다(`getSelection().toString()` = 첫 문단의 일부,
  `Range.intersectsNode(둘째 문단)` = false).
- **Shift+누름도 같다** — 다른 편집 상자를 Shift+누르면 선택이 원래 상자의 끝까지만 늘고 그 상자를 넘지 않는다.
- **오른쪽 단추**를 다른 편집 상자에서 누르면 커서가 그 상자로 옮겨 가고 선택은 접힌다(여러 상자에 걸친 선택을 메뉴로 넘길 수 없다).
- 스크립트로는 넘길 수 있다 — `Selection.addRange` 뒤 `Selection.extend(다른 상자의 노드, offset)` 은 상자를 넘는 선택을 만든다(app.js `outlineReselect` 가 쓰는 길). 사용자의 손짓으로는 안 된다는 뜻.
- 그래서 「여러 문단을 고른다」 는 직접 만들어야 한다: `mousedown` 에서 시작 상자를 기억하고 `mousemove`(`buttons & 1`)의 `e.target.closest(상자)` 가 **다른 상자**가 되는 순간 브라우저 선택을 걷고
  (`removeAllRanges` + 활성 상자 `blur`) 제 묶음 선택으로 바꾼다. 끄는 동안 브라우저가 글 선택을 다시 만들므로 `selectionchange` 에서 계속 걷는다. `mousedown` 의 `preventDefault` 는 Shift+누름에만
  (보통 누름을 막으면 커서가 안 들어간다). 표 칸 고르기(table_edit.js)와 문단 묶음 고르기(table_make.js `tpk`)가 이 방식.
- 묶음 표시를 요소의 class 로 두면 화면을 다시 그릴 때(쪽 나눔 등 요소를 새로 만드는 경우) 사라진다 — `<style>` 한 장에 `[data-id="…"]` 선택자 목록으로 칠하면 요소가 바뀌어도 남는다
  (문단 3,000개 선택자까지 써 봄 — 그리기 지연 없음).
- 부드러운 스크롤(`scrollIntoView({behavior: "smooth"})`)은 수백 ms 동안 `scroll` 이벤트를 낸다 — 「스크롤하면 닫히는」 메뉴는 그동안 열자마자 닫힌다(자동 시험은 스크롤이 멎은 뒤 메뉴를 열 것).

사용처: [spec/spec_헤딩_추출.md](../spec/spec_헤딩_추출.md) ② §11 「문단 묶음 고르기」. 관련: [CSS_zoom_중첩.md](CSS_zoom_중첩.md).
