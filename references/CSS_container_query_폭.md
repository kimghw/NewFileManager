# CSS 컨테이너 쿼리 — 무엇의 폭을 재나 · 무엇을 못 하나

2026-11-13 문서 이름 줄의 색 설명(spec_구분_기준 ② §11 「색 설명」)을 줄 폭으로 줄이다가 확인한 것. Chromium(Playwright) 실측.

## 재는 폭은 안쪽 폭(content box)

- `@container 이름 (max-width: 560px)` 이 견주는 값은 컨테이너의 **content box 폭**이다 — 테두리 상자(`getBoundingClientRect().width`)에서 좌우 padding·border 를 뺀 값.
- 실측: 줄의 테두리 상자 570px · 좌우 padding 12px씩 → 안쪽 546px → `max-width: 560px` 규칙이 **걸렸다**(570 > 560 인데도).
- 문턱을 정하거나 검사에서 기대값을 셀 때 `clientWidth − paddingLeft − paddingRight` 로 센다.

## 컨테이너 자신은 그 쿼리로 못 꾸민다

- `@container` 규칙은 컨테이너의 **자손**에만 듣는다. 컨테이너 요소 자체의 속성(`flex-wrap` 등)을 제 폭에 따라 바꿀 수는 없다.
- 선택자에 컨테이너의 클래스를 쓰는 것은 된다(`@container row (max-width: 560px) { .row.on > .mode { display: none } }` — 꾸미는 대상은 자손 `.mode`).
- 컨테이너 자체가 좁을 때 달라져야 하면: 쿼리 없이도 맞는 규칙으로 둔다(아래 줄 나눔) · 또는 한 겹 바깥을 컨테이너로 삼는다.

## `container-type: inline-size` 를 걸 때

- 그 요소의 가로 크기가 내용에 기대지 않게 된다(inline-size containment) — 폭을 내용으로 정하는 자리(`width: max-content`, 격자의 `auto` 열에 혼자 든 칸)에 걸면 폭이 0 이 된다.
  격자의 `minmax(0, 1fr)` 열에 늘어나 있는 칸·`display: flex` 줄처럼 **바깥이 폭을 정하는 요소**에 건다.

## flex 줄 나눔은 줄어들기 전 크기로 잰다

- `flex-wrap: wrap` 이 다음 줄로 넘길지는 항목의 **가상 주 크기**(flex-basis 를 min/max 로 자른 값)의 합으로 정한다 — 줄어들 수 있는지(`flex-shrink`)는 그 뒤의 일.
- 그래서 `flex: 1 1 auto` 인 긴 글 항목(파일 이름)이 있으면, 줄임표로 줄 수 있는데도 다른 항목이 다음 줄로 밀린다.
- 「이 항목이 최소 폭까지 줄어든 뒤에야 줄을 나눈다」 = 그 항목에 `flex-basis: <최소 폭>` + `flex-grow: 1`(남는 폭은 그대로 차지).
  실측: 이름 줄에서 파일 이름에 `flex-basis: 6em` 을 주니 600자 이름에도 줄 높이 35px 그대로(이름만 줄임표), 줄 폭 450px 에서만 설명이 다음 줄로.
