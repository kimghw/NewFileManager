# CSS flex 줄 — 「폭이 모자라면 간격부터 줄이고, 그 뒤에 이름을 줄임표로」

2026-11-16 패널 머리 탭 줄(`#toolTabs` — spec_작업 ② §10 「둘째 줄」)의 탭 사이 간격을 넓히다가 확인한 것. Chromium 140(Playwright) 실측.

## 줄어드는 것은 content box 뿐이다

- flex 항목이 줄어들 때(`flex-shrink`) 줄어드는 것은 **내용 상자**다 — `padding` · `border` · `margin` · 부모의 `gap` 은 줄지 않는다.
- 그래서 탭 사이 간격을 `padding`·`gap` 고정 값으로 주면, 폭이 모자랄 때 간격은 그대로 쥔 채 **이름부터** 줄임표가 된다
  (실측: 안 여백 10px + gap 2px 인 탭 다섯이 패널 380px 에서 글 사이 22px 를 지킨 채 이름 셋이 「작업 내…」 로).
- 간격이 먼저 줄게 하려면 간격이 **내용 상자 안의 여유**여야 한다: 탭 폭(flex-basis) = 글 폭 + 여유, 바닥(min-width) = 글 폭.

## 「내용 폭 + N px」 은 `calc-size()` 로

- `flex-basis: calc-size(max-content, size + 14px)` — 내용 폭(안 여백 포함)에 14px 를 더한 값이 탭의 처음 폭이 된다. `flex-basis` 에서도 된다(실측).
  `calc(max-content + 14px)` 는 문법 오류(`calc()` 안에 내용 크기 낱말을 못 쓴다).
- 바닥은 `min-width: max-content`(= 글 + 안 여백 — `box-sizing: border-box` 인 단추에서 테두리 상자 기준). 줄임표를 허락할 탭만 `min-width: 0`.
- 글은 탭 가운데(`text-align: center` — 단추는 기본값)라 여유가 좌우로 반씩 보이고, 여유가 탭 상자 안이라 고른 탭의 바탕·밑줄도 같이 넓어진다.
- 지원: Chromium 129 부터(실측은 140). 다른 엔진은 여기서 확인하지 못했다 — `@supports (flex-basis: calc-size(max-content, size + 14px)) { … }` 로 감싸고 밖에 고정 값을 남긴다.

## 고르게 줄이려면 flex-shrink 를 폭에 반비례로

- 모자란 폭은 항목마다 `flex-shrink × 처음 폭` 에 비례해 나뉜다 — `flex-shrink` 가 같으면 **넓은 탭이 더 많이** 준다(여유 14px 를 넓은 탭이 먼저 다 쓰고 줄임표가 되는데 좁은 탭은 간격이 남는다).
- 탭마다 같은 px 씩 줄게 하려면 `flex-shrink ∝ 1 / 처음 폭`. 실측 값(13px 굵은 글 — 처음 폭 78.6px 인 탭을 1 로): 74px → 1.05 · 61px → 1.3 · 48px 안팎 → 1.65.
  이렇게 두면 글 사이가 13 · 13 · 13 … 처럼 같은 값으로 준다.
- 바닥(min-width)에 닿은 항목은 얼고 남은 모자람은 나머지가 나눈다 — 줄지 않는 탭이 여유를 다 내놓은 뒤에 줄임표 탭이 이름을 줄이기 시작한다.

## 안 되는 길(실측)

- **단추를 flex 로 만들고 안에 빈 `::before`·`::after`(`flex: 0 1000 6px`)를 간격으로**: Chromium 은 flex 컨테이너의 내용 폭(max-content)을 셀 때 항목의 `flex-basis` 를 보지 않는다 —
  빈 가짜 요소는 0 으로 세어져 단추 폭이 「글 + 안 여백」 이 되고 간격은 늘 0 이다. `width: 6px` 로 주면 max-content 에는 들지만 min-content 에도 들어 바닥(`min-width: min-content`)이 간격까지 지킨다.
  또 단추가 flex 컨테이너면 글(이름 없는 flex 항목)에 `text-overflow: ellipsis` 가 안 걸려 `<span>` 으로 감싸야 한다.
- **부모에 빈 요소를 끼워 간격으로**(`flex: 0 1000000 14px`): 간격이 고르게 줄지만, 감춘 탭(`hidden`) 옆의 빈 요소를 같이 감춰야 하고(앞 형제는 CSS 로 못 고른다 — `:has()` 나 스크립트) 고른 탭의 바탕은 넓어지지 않는다.
- **컨테이너 쿼리 문턱**: 보이는 탭 수(넷~여덟)와 이름 길이에 따라 맞는 문턱이 달라 한 값으로는 어느 쪽에서 붙거나 잘린다.
