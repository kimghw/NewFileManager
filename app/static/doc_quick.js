"use strict";
/* 문서 이름 줄의 바로 열기 아이콘(index.html #nameQuick — spec_작업 ② §17 「이름 줄 바로 열기」, 2026-11-15 사용자 "여기에 템플릿, 서식 뷰어를 클릭하면 바로 볼 수 있게 간단한 아이콘을 넣어줘").
   #nameTplRel = 「템플릿 관계」 · #nameStyleLib = 「서식 관리자」 — 둘 다 도구 줄 「서식」 묶음의 같은 단추(#tbTplRel — outline_match.js · #tbStyleLib — style_lib.js)의 **대리**다:
   누르면 그 단추를 누르고(열려 있으면 닫힘 · 접혀 있으면 폄 — 동작은 그쪽 것 하나), 눌림(aria-pressed)·꺼짐(disabled)·도움말(title)은 그 단추를 지켜보며 따라 그린다.
   「서식」 묶음을 펴지 않아도(도구 줄을 접어 두어도) 한 번에 열린다. 여는 규칙을 여기 다시 적지 않는다 — 그쪽이 바뀌면 같이 바뀐다.
   outline_match.js · style_lib.js 다음에 읽힌다($ 를 쓴다). */
(() => {
  for (const [mine, src] of [["nameTplRel", "tbTplRel"], ["nameStyleLib", "tbStyleLib"]]) {
    const b = $(mine), s = $(src);
    if (!b || !s) continue;
    const sync = () => {
      b.disabled = s.disabled;
      b.setAttribute("aria-pressed", s.getAttribute("aria-pressed") === "true" ? "true" : "false");
      if (s.title) b.title = s.title;
    };
    b.onclick = () => s.click();
    if (typeof MutationObserver === "function") new MutationObserver(sync).observe(s, { attributes: true, attributeFilter: ["disabled", "aria-pressed", "title"] });
    sync();
  }
})();
