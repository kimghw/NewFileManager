"use strict";
/* 문서 이름 줄의 표시 아이콘(index.html #nameQuick — spec_작업 ② §17 「이름 줄 표시 아이콘」 — 여백 표시 셋 + 문단 색 표시 둘: 아래 DOC_QUICK).
   2026-11-16 사용자 "템플릿, 서식 보여주고 있는데 이걸 안볼려면 어떻게 해야 하냐? 나는 애초에 이 2개 아이콘을 이걸 봤다 안봤다 하는 용도로 쓰고 싶었거든" —
   #nameTplMarks = 문서 왼쪽 여백의 **템플릿 표시** 「T1 L2」(+ 「TEMP」·「새 레터」 표시) 켜기/끄기(app.js tplMarksToggle) ·
   #nameFmtMarks = **서식 라벨** 「S41」 켜기/끄기(app.js tplFmtToggle). 둘은 따로다 — 템플릿 표시를 끄고 서식 라벨만 볼 수도 있다(app.js tplMarksDraw).
   눌림(aria-pressed) = 켜짐. 값은 이 브라우저에 기억하고 「템플릿 관계」 열·「템플릿」 탭 위의 「문서 표시」·「서식 라벨」 단추와 같은 값이다(어느 쪽을 눌러도 함께 바뀐다 — app.js tplMarkBtnSync 가 docQuickSync 를 부른다).
   표시할 것이 없는 문서(헤딩 추출 2단계 결과가 없는 hwpx · docx)에서는 꺼져 있고 까닭을 이름(title)에 적는다 — 문서를 열고 오버레이·그래프를 읽을 때마다 app.js tplMarksDraw 가 docQuickSync 를 부른다.
   (2026-11-15 에 만든 처음 것은 「템플릿 관계」·「서식 관리자」 열을 여는 대리 단추였다 — 사용자가 뜻한 것이 아니었다. 그 두 열은 도구 줄 「서식」 묶음의 #tbTplRel · #tbStyleLib 로 연다.)
   2026-11-16 셋째 #nameTblMarks = **표 라벨**(표 옆 여백의 「⊞ ✎ t43 / 소속」 — tables.js .tbl-mark) 켜기/끄기 — 사용자 "테이블에 있는 라벨도 보였다 안보였다 하게 해줘"(spec_헤딩_추출 ② §10 「표 라벨 켜기/끄기」).
   app.js 다음에 읽힌다($ · heads · state · taskRnd · tplMarksOn · tplFmtOn · tempMarkCount · driftMarkCount · divMarksOn · divMarksToggle · tables.js 의 tblMarksOn · tblMarksToggle ·
   zones.js 의 zonesOn · zonesToggle · zonesOffered · zonesDims 를 쓴다 · 둘째 면 아이콘은 PEEK · peerShown · #peerFrame 도).
   2026-11-19 둘째 면(같이 보기) 이름 줄에도 같은 다섯(#peerQuick — 아래 「둘째 면」 절) · 값은 문서마다(app.js quickKey — spec_작업 ② §12 「도구는 문서마다」). */
const DOC_QUICK = [
  { id: "nameTplMarks", name: "템플릿 표시", what: "문서 왼쪽 여백의 「T1 L2」(템플릿 번호 · 개요 레벨)", on: () => tplMarksOn(), toggle: () => tplMarksToggle(),
    have: () => !!(heads.outline || (heads.marks && heads.marks.size) || (typeof tempMarkCount === "function" && tempMarkCount()) || (typeof driftMarkCount === "function" && driftMarkCount())) },
  { id: "nameFmtMarks", name: "서식 라벨 표시", what: "문서 왼쪽 여백의 서식 라벨 「S41」(서식이 같은 문단끼리 묶어 매긴 이름)", on: () => tplFmtOn(), toggle: () => tplFmtToggle(),
    have: () => !!(heads.outline || (heads.marks && heads.marks.size)) },
  // 셋째(2026-11-16 사용자 "테이블에 있는 라벨도 보였다 안보였다 하게 해줘"): 표 옆 여백의 표 라벨(tables.js .tbl-mark — 「⊞ ✎ t43 / 소속」) 켜기/끄기. 값은 「표」 탭의 「표 도구 표시」 와 같다(tblMarksOn · nfm.tblMarks — 기본 켬).
  // 표가 있는 문서면 켤 수 있다(hwpx · docx — 헤딩 추출과 무관). tables.js tblMarksDraw 가 그릴 때마다 docQuickSync 를 부른다
  { id: "nameTblMarks", name: "표 라벨 표시", what: "문서의 표 옆 여백에 붙는 표 라벨(엑셀식 보기 ⊞ · 표 지침 ✎ · 표 id · 소속)", on: () => typeof tblMarksOn === "function" && tblMarksOn(), toggle: () => tblMarksToggle(),
    have: () => typeof tblMarksToggle === "function" && !!document.querySelector("#doc table.tbl[data-tbl], #doc .xl-wrap[data-tbl]"), none: "이 문서에는 표가 없습니다" },
  // 넷째 · 다섯째(2026-11-18 사용자 "구분자리 표기, 편집구역 아이콘 각각 넣어 주고, 활성화 하고 마웃 갖어다 대면 어떤 건지 보이게 해줘"): 문단에 입히는 색 표시 둘.
  // 값은 하나다 — 「구분 기준 자리 표시」 = 「작업 개요」 카드의 「보기/감추기」 · 문서 오른쪽 단추 메뉴와 같은 nfm.divMarks(기본 끔 — app.js divMarksOn · divMarksToggle) ·
  // 「편집 구역 표시」 = 「편집 구역」 줄의 「보기/감추기」 와 같은 nfm.zones(기본 켬 — zones.js zonesOn · zonesToggle). 둘 다 연구개발과제 TASK 의 것이라 다른 TASK 에서는 세우지 않는다(show — design.md §9 「해당 없는 항목은 세우지 않는다」).
  // app.js divKeyDraw · divMarksBarRefresh 와 zones.js zonesKeyDraw 가 그릴 때마다 docQuickSync 를 부른다(다른 곳에서 켜고 꺼도 눌림이 따라온다)
  // 2026-11-19 사용자 "구분자리, 편집구역은 각각 아이콘으로 두고 클릭 하면 문서 상단에 플로팅으로 띄어줘, 움직일 수 있게": 이 둘을 켜면 그 색의 설명이 문서 위에 떠 있는 상자로 뜬다(key_float.js — 전에는 이 줄 안의 설명이라 줄이 꺾였다)
  { id: "nameDivMarks", name: "구분 기준 자리 표시", what: "문단의 구분 기준 자리 색(단계 · 차년도 · 기관이 걸린 글의 바탕색과 왼쪽 띠)과 문서 위에 뜨는 색 설명(끌어서 옮김)",
    show: () => !!state.id && taskRnd(), on: () => divMarksOn(), toggle: () => divMarksToggle(), have: () => !!state.id && taskRnd() },
  { id: "nameZones", name: "편집 구역 표시", what: "편집 구역(어느 기관 · 단계 · 차년도의 것인지 — 블록 옆 색 띠와 쪽 오른쪽 여백의 이름표 「한국선급 · 2차년도」)과 문서 위에 뜨는 색 설명(끌어서 옮김)",
    show: () => !!state.id && taskRnd() && typeof zonesToggle === "function", on: () => zonesOn(), toggle: () => zonesToggle(), have: () => zonesOffered() && zonesDims().length > 0,
    none: () => (!zonesOffered() ? "편집 구역은 저장된 HWPX 문서에서만 씁니다" : "보일 기준(기관 · 단계 · 차년도)이 하나도 켜져 있지 않습니다 — 「작업 개요」 의 「편집 구역」 에서 고르세요") },
];
function dqView(q) { // 아이콘 하나의 지금 상태 → {id, show(세울지), have(켤 수 있나), on(눌림), title}
  const show = !q.show || q.show();
  if (!show) return { id: q.id, show, have: false, on: false, title: "" };
  const have = q.have(), on = have && q.on(), none = typeof q.none === "function" ? q.none() : q.none;
  const title = have ? `${q.name} ${on ? "켜짐" : "꺼짐"} — 누르면 ${q.what} 을 ${on ? "숨깁니다" : "보입니다"}(문서마다 따로 — 이 브라우저에 기억)`
    : `${q.name} — ${none || "이 문서에는 아직 표시할 것이 없습니다(HWPX 문서에서 헤딩 추출 2단계(헤딩 그래프)까지 돌리면 생깁니다)"}`;
  return { id: q.id, show, have, on, title };
}
function dqPaint(b, v) { // 단추에 상태를 — 바뀐 것만 쓴다
  if (b.hidden !== !v.show) b.hidden = !v.show;
  if (!v.show) return;
  if (b.disabled !== !v.have) b.disabled = !v.have;
  if (b.getAttribute("aria-pressed") !== String(v.on)) b.setAttribute("aria-pressed", String(v.on));
  if (b.title !== v.title) b.title = v.title;
}
function docQuickSync() { // 눌림 · 꺼짐 · 도움말 — 바뀐 것만 쓴다(tplMarksDraw 가 그릴 때마다 부른다)
  for (const q of DOC_QUICK) { const b = $(q.id); if (b) dqPaint(b, dqView(q)); }
  if (PEEK) dqPeerPing(); // 둘째 면 화면 — 바깥 이름 줄의 이 면 아이콘(#peerQuick)을 맞추게 알린다
}

// ---- 둘째 면(같이 보기)의 이름 줄 아이콘 #peerQuick(2026-11-19 사용자 "원본, 목적문서가 따로면 도구도,, 따로 따로 적용하ㄹ수 있게 해야지" · 이름 줄 "이 행도 … 요청사항과 맞게" — spec_작업 ② §12 「도구는 문서마다」):
// 위 다섯과 같은 그림(첫째 면 단추를 베낌 — design.md §9 「같은 기능의 아이콘은 한 그림」) · 그 면의 문서에만 듣는다(값도 문서마다 — app.js quickKey: 원본 · 목적 문서의 키가 따로).
// 상태는 둘째 면 화면(iframe — 같은 앱의 PEEK)이 위 DOC_QUICK 으로 계산하고(docQuickState) 누름도 그 화면이 받는다(docQuickPress — 그 화면의 문서에 켜고 끈다) — 바깥은 그리기만(peerQuickSync).
// 둘째 면 화면은 제 표시를 다시 그릴 때마다(docQuickSync) 바깥의 peerQuickSync 를 부른다(한 프레임에 한 번 — dqPeerPing). 구분 기준 자리 · 편집 구역도 그 면에서 읽기만 한다(GET — app.js divReset · zones.js zonesOffered)
function docQuickState() { return { id: state.id || "", list: DOC_QUICK.map(dqView) }; } // 둘째 면 화면에서 바깥이 부른다
function docQuickPress(id) { // 둘째 면 화면에서 바깥이 부른다 — 그 문서의 표시 켜기/끄기
  const q = DOC_QUICK.find((x) => x.id === id), v = q && dqView(q);
  if (!v || !v.show || !v.have) return;
  q.toggle();
  docQuickSync();
}
let dqPing = 0;
function dqPeerPing() {
  if (dqPing) return;
  dqPing = requestAnimationFrame(() => { dqPing = 0; try { if (parent !== window && typeof parent.peerQuickSync === "function") parent.peerQuickSync(); } catch { /* 바깥이 준비 전 */ } });
}
function peerQuickWin() { // 둘째 면 화면 — 지금 떠 있는 문서를 다 그린 화면일 때만(다른 문서로 넘어가는 동안의 옛 화면에 묻지 않는다)
  const pid = typeof peerShown === "function" ? peerShown() : "";
  if (!pid) return null;
  try { const w = $("peerFrame").contentWindow; return w && typeof w.docQuickState === "function" && w.docQuickState().id === pid ? w : null; } catch { return null; }
}
function peerQuickBuild(box) { // 첫째 면 단추를 베껴 만든다(한 번) — id 는 name… → peer…
  if (box.children.length) return;
  for (const q of DOC_QUICK) {
    const src = $(q.id);
    if (!src) continue;
    const b = src.cloneNode(true);
    b.id = "peer" + q.id.slice(4);
    b.dataset.quick = q.id;
    b.hidden = true;
    b.onclick = () => peerQuickPress(q.id);
    box.append(b);
  }
}
function peerQuickSync() { // 바깥 — 둘째 면 이름 줄의 아이콘을 그 면의 문서 상태로(peerSync · 그 화면의 알림 · 누른 뒤)
  if (PEEK) return;
  const box = $("peerQuick");
  if (!box) return;
  peerQuickBuild(box);
  const w = peerQuickWin(), list = w ? w.docQuickState().list : [];
  const any = list.some((v) => v.show);
  if (box.hidden !== !any) box.hidden = !any;
  for (const b of box.children) {
    const v = list.find((x) => x.id === b.dataset.quick) || { show: false };
    dqPaint(b, v.show ? { ...v, title: `${v.title}\n— 이 면의 문서에만 듣습니다(옆 문서의 표시는 따로)` } : v);
  }
}
function peerQuickPress(id) {
  const w = peerQuickWin();
  if (w) { try { w.docQuickPress(id); } catch { /* 아직 여는 중 */ } }
  peerQuickSync();
}
(() => {
  for (const q of DOC_QUICK) {
    const b = $(q.id);
    if (b) b.onclick = () => { q.toggle(); docQuickSync(); };
  }
  docQuickSync();
})();
