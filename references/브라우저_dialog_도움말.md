# modal dialog 안의 도움말과 popover

- 확인: 2026-11-12, Playwright Chromium 140.0.7339.16, 독립 HTML fixture.
- `dialog.showModal()`로 연 창의 노트에서 `body` 아래 `popover="manual"` 요소를 `showPopover()`로 띄우면, 요소가 보이고 `:popover-open`이어도 마우스 입력 대상이 되지 않았다. 도움말 좌표의 `document.elementFromPoint()`는 dialog를 반환했다.
- modal dialog 밖은 비활성(inert) 범위이므로 **그 창에서 여는 도움말은 dialog의 DOM 자식으로 둔다**. popover의 top layer 표시만으로 입력 가능한 범위가 바뀌지는 않는다.
- 같은 popover 요소를 dialog 아래로 옮긴 뒤 열면 해당 좌표의 입력 대상은 도움말 자신이었고, 마우스를 도움말 위로 옮겨 읽을 수 있었다.
- 공용 도움말 요소를 재사용할 때는 연 버튼의 `closest("dialog[open]") || document.body`를 부모로 선택한다. 다른 부모로 옮기기 전에 열린 popover를 닫고 다시 연다.
- 검증은 `is_visible()`만으로 부족하다. 도움말 좌표의 hit test, 실제 도움말 위 hover 유지, Escape로 도움말만 닫히는지, dialog를 닫은 뒤 일반 화면에서 다시 열리는지까지 확인한다.

프로젝트 적용과 검사 상태는 [작업 사양서](../spec/spec_작업.md)에 기록한다.
