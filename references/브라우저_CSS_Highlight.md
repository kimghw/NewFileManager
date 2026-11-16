# 브라우저 — CSS Custom Highlight(글자 범위에 표시, DOM 은 그대로)

편집 상자(contenteditable) 안의 글자 일부에 색·밑줄을 입히되 **요소를 끼워 넣지 않는** 방법. 쓰는 곳: 문서의 「고친 곳 보기」(`app/static/doc_diff.js` — [spec/spec_작업.md](../spec/spec_작업.md) ② §8).

## 쓰는 법

```js
const h = new Highlight();            // 범위 묶음
CSS.highlights.set("nfm-dd-ins", h);  // 이름으로 등록(문서 전체에 하나)
const r = document.createRange(); r.setStart(textNode, 3); r.setEnd(textNode, 7);
h.add(r);                             // 그 범위가 칠해진다 — h.delete(r) · h.clear()
```
```css
::highlight(nfm-dd-ins) { background-color: #b9ecc8; color: #14532d; }
::highlight(nfm-dd-del) { text-decoration: underline wavy #dc2626; }
```

## 확인한 것(2026-11-17 — Playwright 의 Chromium, 이 저장소 화면)

- **문단 DOM 이 안 바뀐다** — 글 노드·자식 요소 그대로라 글 읽기(`readText`)·서버 글과의 대조가 영향을 받지 않는다(편집 상자 여섯 문단에 표시를 건 채 화면 글 = 서버 글).
- 편집 상자에서 글을 치는 동안에도 걸린다 — `input` 마다 그 문단의 범위를 새로 만들면 친 글이 바로 칠해진다(서버 반영 전).
- 배율을 바꾸거나 쪽을 다시 나눈 뒤 범위를 새로 만들면 그대로 보인다(이 저장소는 그때마다 새로 만든다 — 아래 「노드를 떼면」 때문).
- 한 화면의 문단 17개(범위 17개 · 여백 꼬리표 17개)를 전부 다시 만드는 데 14 ms.

## 표준이 정한 것(직접 재 보지 않음)

- **범위는 살아 있다**(live Range) — 범위 안에서 글이 늘고 줄면 경계가 따라 움직인다. **노드를 떼면 풀린다**: 범위가 가리키던 노드가 문서에서 떨어지면(문단 요소를 다른 쪽 상자로 옮기기 = 떼기 → 붙이기 · `replaceChildren`) 경계가 부모 쪽으로 접혀 표시가 사라진다 →
  문단을 옮기거나 새로 그린 뒤에는 옛 범위를 `delete` 하고 다시 만든다(안 지우면 `Highlight` 가 떨어진 노드를 붙들고 있다).
- `::highlight()` 에 쓸 수 있는 속성은 몇 가지뿐이다 — `color` · `background-color` · `text-decoration` 계열 · `text-shadow`(· `-webkit-text-stroke`/`-webkit-text-fill-color`). **테두리 · 여백 · `::before` 내용 · 도움말(title)은 못 준다** → 빈 자리(글자를 지우기만 한 곳)는 직접 칠할 수 없어 앞뒤 글자에 밑줄을 준다.
- 접힌 범위(시작 = 끝)는 아무것도 칠하지 않는다.
- 겹치는 표시는 `Highlight.priority`(큰 쪽이 위) → 같으면 등록 차례.
- 지원: Chrome·Edge 105+ · Safari 17.2+ · Firefox 는 뒤늦게(140 무렵). 없는 브라우저는 `typeof Highlight !== "function"` 으로 가려 다른 표시(띠 · 꼬리표)만 남긴다.

## 같이 알아 둘 것 — IntersectionObserver

- 지켜보던 요소가 문서에서 떨어지면 「안 보임」 으로 한 번 알려 온다(그때 `unobserve` 하지 않으면 관찰자가 떨어진 요소를 붙들고 있다).
- `rootMargin` 으로 창 위아래 여유를 주면 창에 들어오기 전에 미리 표시를 만들 수 있다(스크롤 중 깜박임 없음).
