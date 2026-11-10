# CSS `zoom` 중첩 — 배율 된 문서 안에서 화면 크기 고정 요소 두기

2026-11-09 NewFileManager 문서 표시(「TN Lk」, 쪽 왼쪽 여백)에서 실측(Chromium 1234 헤드리스, Playwright). 사용처 [spec/spec_헤딩_추출.md](../spec/spec_헤딩_추출.md) ② §7 「문서 표시」.

- Chromium·Firefox(126+)·WebKit 의 `zoom` 은 **유효 배율 = 조상 배율의 곱**이다. `zoom: z` 인 조상(`#doc`) 안에서 자식에 `zoom: calc(1/z)`(실제로는 JS 로 `1/z` 수치)를 주면
  그 자식의 유효 배율은 1 — `top`·`margin`·`font-size` 같은 px 길이가 **화면 px** 로 그려진다(쪽이 0.43배로 줄어도 글자 10.5px 그대로).
- 그 자식의 **퍼센트**는 그대로 조상(포함 블록)의 실제 상자에 대해 풀린다: `position:absolute; right:100%` 는 배율과 무관하게 포함 블록의 왼쪽 가장자리에 붙는다
  (실측: 표 오른끝 = 쪽 왼쪽 −32px(margin-right 32px), 배율 1.11·0.43 모두).
- 자리는 **화면 px** 로 준다: `top = 문단.getBoundingClientRect().top − 쪽.getBoundingClientRect().top`(둘 다 화면 좌표) — 종전처럼 `/ z` 로 쪽 px 로 바꾸면 안 된다.
- `sheet.offsetWidth`(배율 전 레이아웃 px) 와 `getBoundingClientRect().width`(화면 px) 의 비로 z 를 재면 CSS 변수 없이도 된다.
- 주의: 화면 크기를 고정하면 배율이 작을수록 문단 간격(화면 px)이 좁아져 한 줄 높이(17px) 안에 여러 문단이 들어온다 — 같은 줄에 모아 「T11 L1 · T11 L2 +3」 으로 줄여야 겹치지 않는다.
