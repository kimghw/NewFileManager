"use strict";
/* 문서 이름 줄의 표시 아이콘 둘(index.html #nameQuick — spec_작업 ② §17 「이름 줄 표시 아이콘」).
   2026-11-16 사용자 "템플릿, 서식 보여주고 있는데 이걸 안볼려면 어떻게 해야 하냐? 나는 애초에 이 2개 아이콘을 이걸 봤다 안봤다 하는 용도로 쓰고 싶었거든" —
   #nameTplMarks = 문서 왼쪽 여백의 **템플릿 표시** 「T1 L2」(+ 「TEMP」·「새 레터」 표시) 켜기/끄기(app.js tplMarksToggle) ·
   #nameFmtMarks = **서식 라벨** 「S41」 켜기/끄기(app.js tplFmtToggle). 둘은 따로다 — 템플릿 표시를 끄고 서식 라벨만 볼 수도 있다(app.js tplMarksDraw).
   눌림(aria-pressed) = 켜짐. 값은 이 브라우저에 기억하고 「템플릿 관계」 열·「템플릿」 탭 위의 「문서 표시」·「서식 라벨」 단추와 같은 값이다(어느 쪽을 눌러도 함께 바뀐다 — app.js tplMarkBtnSync 가 docQuickSync 를 부른다).
   표시할 것이 없는 문서(헤딩 추출 2단계 결과가 없는 hwpx · docx)에서는 꺼져 있고 까닭을 이름(title)에 적는다 — 문서를 열고 오버레이·그래프를 읽을 때마다 app.js tplMarksDraw 가 docQuickSync 를 부른다.
   (2026-11-15 에 만든 처음 것은 「템플릿 관계」·「서식 관리자」 열을 여는 대리 단추였다 — 사용자가 뜻한 것이 아니었다. 그 두 열은 도구 줄 「서식」 묶음의 #tbTplRel · #tbStyleLib 로 연다.)
   2026-11-16 셋째 #nameTblMarks = **표 라벨**(표 옆 여백의 「⊞ ✎ t43 / 소속」 — tables.js .tbl-mark) 켜기/끄기 — 사용자 "테이블에 있는 라벨도 보였다 안보였다 하게 해줘"(spec_헤딩_추출 ② §10 「표 라벨 켜기/끄기」).
   app.js 다음에 읽힌다($ · heads · tplMarksOn · tplFmtOn · tempMarkCount · driftMarkCount · tables.js 의 tblMarksOn · tblMarksToggle 을 쓴다). */
const DOC_QUICK = [
  { id: "nameTplMarks", name: "템플릿 표시", what: "문서 왼쪽 여백의 「T1 L2」(템플릿 번호 · 개요 레벨)", on: () => tplMarksOn(), toggle: () => tplMarksToggle(),
    have: () => !!(heads.outline || (heads.marks && heads.marks.size) || (typeof tempMarkCount === "function" && tempMarkCount()) || (typeof driftMarkCount === "function" && driftMarkCount())) },
  { id: "nameFmtMarks", name: "서식 라벨 표시", what: "문서 왼쪽 여백의 서식 라벨 「S41」(서식이 같은 문단끼리 묶어 매긴 이름)", on: () => tplFmtOn(), toggle: () => tplFmtToggle(),
    have: () => !!(heads.outline || (heads.marks && heads.marks.size)) },
  // 셋째(2026-11-16 사용자 "테이블에 있는 라벨도 보였다 안보였다 하게 해줘"): 표 옆 여백의 표 라벨(tables.js .tbl-mark — 「⊞ ✎ t43 / 소속」) 켜기/끄기. 값은 「표」 탭의 「표 도구 표시」 와 같다(tblMarksOn · nfm.tblMarks — 기본 켬).
  // 표가 있는 문서면 켤 수 있다(hwpx · docx — 헤딩 추출과 무관). tables.js tblMarksDraw 가 그릴 때마다 docQuickSync 를 부른다
  { id: "nameTblMarks", name: "표 라벨 표시", what: "문서의 표 옆 여백에 붙는 표 라벨(엑셀식 보기 ⊞ · 표 지침 ✎ · 표 id · 소속)", on: () => typeof tblMarksOn === "function" && tblMarksOn(), toggle: () => tblMarksToggle(),
    have: () => typeof tblMarksToggle === "function" && !!document.querySelector("#doc table.tbl[data-tbl], #doc .xl-wrap[data-tbl]"), none: "이 문서에는 표가 없습니다" },
];
function docQuickSync() { // 눌림 · 꺼짐 · 도움말 — 바뀐 것만 쓴다(tplMarksDraw 가 그릴 때마다 부른다)
  for (const q of DOC_QUICK) {
    const b = $(q.id);
    if (!b) continue;
    const have = q.have(), on = have && q.on();
    const title = have ? `${q.name} ${on ? "켜짐" : "꺼짐"} — 누르면 ${q.what} 을 ${on ? "숨깁니다" : "보입니다"}(이 브라우저에 기억)`
      : `${q.name} — ${q.none || "이 문서에는 아직 표시할 것이 없습니다(HWPX 문서에서 헤딩 추출 2단계(헤딩 그래프)까지 돌리면 생깁니다)"}`;
    if (b.disabled !== !have) b.disabled = !have;
    if (b.getAttribute("aria-pressed") !== String(on)) b.setAttribute("aria-pressed", String(on));
    if (b.title !== title) b.title = title;
  }
}
(() => {
  for (const q of DOC_QUICK) {
    const b = $(q.id);
    if (b) b.onclick = () => { q.toggle(); docQuickSync(); };
  }
  docQuickSync();
})();
