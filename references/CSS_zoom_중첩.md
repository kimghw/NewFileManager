# CSS `zoom` 중첩 — 배율 된 문서 안에서 화면 크기 고정 요소 두기

2026-11-09 NewFileManager 문서 표시(「TN Lk」, 쪽 왼쪽 여백)에서 실측(Chromium 1234 헤드리스, Playwright). 사용처 [spec/spec_헤딩_추출.md](../spec/spec_헤딩_추출.md) ② §7 「문서 표시」.

- Chromium·Firefox(126+)·WebKit 의 `zoom` 은 **유효 배율 = 조상 배율의 곱**이다. `zoom: z` 인 조상(`#doc`) 안에서 자식에 `zoom: calc(1/z)`(실제로는 JS 로 `1/z` 수치)를 주면
  그 자식의 유효 배율은 1 — `top`·`margin`·`font-size` 같은 px 길이가 **화면 px** 로 그려진다(쪽이 0.43배로 줄어도 글자 10.5px 그대로).
- 그 자식의 **퍼센트**는 그대로 조상(포함 블록)의 실제 상자에 대해 풀린다: `position:absolute; right:100%` 는 배율과 무관하게 포함 블록의 왼쪽 가장자리에 붙는다
  (실측: 표 오른끝 = 쪽 왼쪽 −32px(margin-right 32px), 배율 1.11·0.43 모두).
- 자리는 **화면 px** 로 준다: `top = 문단.getBoundingClientRect().top − 쪽.getBoundingClientRect().top`(둘 다 화면 좌표) — 종전처럼 `/ z` 로 쪽 px 로 바꾸면 안 된다.
- `sheet.offsetWidth`(배율 전 레이아웃 px) 와 `getBoundingClientRect().width`(화면 px) 의 비로 z 를 재면 CSS 변수 없이도 된다.
- 주의: 화면 크기를 고정하면 배율이 작을수록 문단 간격(화면 px)이 좁아져 한 줄 높이(17px) 안에 여러 문단이 들어온다 — 같은 줄에 모아 「T11 L1 · T11 L2 +3」 으로 줄여야 겹치지 않는다.

## `zoom` 을 바꾸는 비용 · ResizeObserver (2026-11-10 실측)

Chromium 헤드리스(Playwright), 74쪽·문단 7,498개·노드 2.6만 문서(`#doc` 에 `zoom`). 사용처 [spec/spec_hwpx_웹편집.md](../spec/spec_hwpx_웹편집.md) ③ 「줄 접기·바꾸기 속도」.

- 컨테이너의 `zoom` 값을 바꾸면 **그 아래 전체를 다시 배치**한다 — 위 문서에서 한 번에 0.3~0.45초(바꾼 뒤 처음 `offsetWidth`·`getBoundingClientRect` 를 읽을 때 또는 다음 프레임에 든다).
  같은 값을 다시 넣는 것은 공짜다.
- 「재려고 `zoom = 1` 로 돌렸다가 원래 값으로 되돌리기」는 최종 값이 같아도 재배치 **두 번**이다. `offsetWidth`·`offsetHeight` 는 배율 전 px 이라(위) 고정 폭 상자는 돌리지 않고도 잴 수 있다.
- `display:none` 을 켜고 끄는 것만으로는(스크롤 상자 높이만 바뀜) 같은 문서에서 다음 그리기까지 0.1초 안팎.
- (2026-11-10 추가 실측, 같은 문서 노드 3.8만) 배율 변경 한 번의 몫은 **스타일 재계산이 배치보다 크다**(재계산 0.2~0.5초 + 배치 0.15~0.25초 — CDP `Performance.getMetrics` 의
  `RecalcStyleDuration`·`LayoutDuration` 차이로 나눠 봄). `zoom` 은 상속되는 유효 배율이라 아래 요소 모두의 계산값이 바뀐다.
- **`:root`(documentElement) inline 스타일의 사용자 정의 속성(`--x`)을 바꾸면** — 지웠다 같은 값으로 다시 써도 — 상속 때문에 문서 전체 스타일을 다시 계산한다(이어서 `getComputedStyle`·
  `getBoundingClientRect` 를 읽으면 그 자리에서 강제). 열 폭처럼 한 상자만 쓰는 변수는 그 상자 요소의 inline 에 두면 그 아래만 다시 계산한다(`var()` 는 가장 가까운 조상 값).
- `content-visibility: auto` 를 쪽 상자에 걸면 화면 밖 쪽의 스타일·배치를 건너뛰어 배율 변경이 0.5~0.8초 → 0.02~0.08초. 단 이 값은 layout·style·**paint 격리를 늘** 켜서
  상자 밖으로 그려지는 것(위로 띄운 쪽 번호, 넘치는 표)을 잘라 내고, 한 번도 그리지 않은 상자는 `contain-intrinsic-size` 자리 크기로 잡힌다(`auto` 는 한 번 그려진 뒤의 크기를 기억).
- (2026-11-12) 그릇이 아니라 **자식 상자마다 같은 `zoom`** 을 두면 그린 결과가 같고 상자별로 나눠 바꿀 수 있다 — 방법·비용·`contain: paint` 는
  [브라우저_강제배치_비용.md](브라우저_강제배치_비용.md) §4(원본).
- `ResizeObserver` 는 기본이 **content-box** — padding 만 바뀌어도(또는 세로 스크롤 막대가 생겨도) 폭이 바뀐 것으로 알린다. 콜백은 배치 뒤·그리기 전에 **프레임당 한 번**, 그 프레임의
  최종 크기로 온다: 한 작업 안에서 두 번 바꿔도 한 번만 오고, 최종 크기가 같으면 안 온다. 그래서 크기 변화에 따른 다시 맞추기는 여기 한 곳에만 두면 되고, 바꾸는 쪽에서 또 부르면 중복이다.

## 배율 된 상자 **안쪽**의 화면 px 자리 — `calc(% − px)` · 변수 · 넘치는 항목 가리기 (2026-11-10 실측)

Chromium 헤드리스(Playwright), 쪽(`.sheet`, 조상 `zoom` 1.08·1.0·0.7·0.53) 안 왼쪽 여백에 `zoom: 1/z` 표시를 둘 때. 사용처 [spec/spec_헤딩_추출.md](../spec/spec_헤딩_추출.md) ② §7 「문서 표시」·§10 「표 식별」.

- `zoom: 1/z` 자식에서 `right: calc(100% - Xpx)` 는 **% 는 포함 블록의 실제 상자**, **px 는 화면 px** 로 풀린다 — 포함 블록 왼끝에서 화면 X px 안쪽에 오른끝이 놓인다
  (X = 여백 폭(mm × 96/25.4 × z) − 22 로 주면 본문 왼끝에서 22px, 네 배율 모두). 다시 안 그리고 조상 배율만 바꿔도(1.0 → 1.2) 자리가 따라간다(자식의 유효 배율이 z₂/z₁ 이 되어 px 가 함께 커짐).
- 그 px 를 **변수**로 줄 때는 자식 자신에 둔다(`el.style.setProperty("--mgl", "81.6px")`): 변수는 쓰이는 요소의 배율로 풀려 화면 px 이 된다. `max(calc(var(--mgl) - 25px), 44px)` 같은 `max()`·중첩 `calc()` 도 된다.
  변수는 기본이 **상속**이라 큰 컨테이너(쪽)에 쓰면 그 아래 전체의 스타일 계산 대상이 된다 — 표시 요소마다 두는 편이 안전(비용은 재지 않음).
- **다 들어가는 항목까지만 보이기**(잘린 반쪽 글 없이): `display: inline-flex; flex-wrap: wrap; align-content: flex-start; height: 한 줄; overflow: hidden; max-width: W` — 폭을 넘는 항목부터는 둘째 줄로
  꺾여 가려진다(DOM 순서 = 보일 차례). `:hover { flex-wrap: nowrap; max-width: none }` 이면 한 줄로 펼쳐진다. `left` 로 붙인 절대 위치 상자는 오른쪽으로 늘어난다(`right` 로 붙이면 왼쪽으로).
- `:has(:focus-visible)` 로 「글쇠 초점일 때만 펼침」 이 된다 — Tab 으로 옮긴 초점은 맞고, 스크립트 `focus()`(직전 입력이 글쇠가 아닐 때)는 `focus({ focusVisible: true })` 를 줘도 이 Chromium 에서는 안 맞았다.
- Playwright: `overflow: hidden` 으로 가려진 단추는 `click()` 이 시간 초과 — 먼저 `hover()` 로 펼친 뒤 누른다.
