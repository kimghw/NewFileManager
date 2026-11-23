"use strict";
// 표 메뉴(spec_헤딩_추출 ② §16) — 표 모듈의 한 조각. 사용자 2026-11-10 "테이블 자체를 클릭할 수 있게 하고 모서리 클릭하면, 빈필드 제거하기, 엑셀식 보기,
// 서식으로 변환하기(선택하면 템플릿 리스트 보여주기) 이런 기능을 테이블에서 바로".
// 문서의 표를 누르면 그 표가 **고른 표**(옅은 파란 테두리)가 되고, 표 **오른쪽 변 바로 바깥 — 쪽의 오른쪽 여백**(표 위끝 높이)에 손잡이(.tbl-corner)가 선다(마우스를 올린 표에도 —
// 사용자 2026-11-10 "테이블 우측에 여백에 놔도 될거 같아": 처음의 왼쪽 위 모서리는 표 첫 칸과 왼쪽 여백의 표지를 가렸다). 손잡이를 누르면 표 메뉴:
//   빈 필드 제거하기 ▸(입력하는 줄이 통째로 빈 줄 · 빈 서브 테이블 · 표째(· 소속 헤딩) — 서버가 계획을 내고, 누르면 그 계획대로: spec_테이블매니저 ② §12) · 엑셀식 보기(2열 A1 격자 — 칸을 끌어 골랐으면 그 범위) ·
//   서식으로 변환하기 ▸(표 양식 목록 — 누르면 그 표의 서식만 바로 입힘) · 표 나누기 ▸ ·
//   에이전트로 표 채우기…(2열 — table_fill.js tblFillView, ② §18) · 이 표를 표 양식으로 지정 ·
//   프로젝트 구성에 맞추기… ▸(연구개발과제 문서만 — 이 표의 구분 기준 자리를 보이고 고른 자리만 기존 「변경 계획 보기 → 반영」 으로: 아래 tmnDivision, spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」) ·
//   구분 기준 열 넣기…(연구개발과제 문서만 — 기관 · 차년도 · 단계 열 + 줄마다 프로젝트 구성의 값: table_divcol.js, ② §13).
// 손잡이 **바로 아래**에 둘째 아이콘(.tbl-corner-guide — 연필)이 함께 선다: 「작성요령 · 표 지침」(2열 — tables.js tblAgentView) 을 바로 연다.
// 사용자 2026-11-12 "테이블 모서리에 아이콘 있는데 작성요령, 표지침을 꺼내서 아이콘 2개로" — 메뉴 안에 있던 항목을 꺼낸 것이라 메뉴에는 없다.
// 메뉴 상자는 app.js 의 공용 오른쪽 단추 메뉴(ctxOpen — 하나뿐)를 빌려 쓴다: 하위 목록은 같은 자리에서 내용만 바꾸고(‹ 로 돌아감), 항목에 마우스를 올리면 문서에 미리 보인다.
// app.js 가 주는 것: state·heads·$·el·api·toast·structOp·flushAll·ctx·ctxMenu·ctxOpen·ctxClose·headsColClose·colLetter·nf·H_JSON·applyEditState·reloadDoc·refreshToolbar. tables.js: xlBlock·xlBlocks·xlColumn·xlSelRange·xlRangeName.
// table_make.js: tmkOpen·tmkTableName·tmk·tmkRemember(표 양식 기억). 부르는 곳(typeof 검사 뒤): tables.js tblMarksDraw 끝 → tblMenuSync(쪽을 다시 나누면 표 조각이 새로 생긴다).
// 서버 짝은 app/tables_api.py `POST …/tables/{tid}/prune`(app/table_prune.py)·`POST …/tables/restyle`. index.html 이 table_make.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TMN_TPL_KEY = "nfm.tblTpls"; // {문서 id: {ids: [최근 쓴 표 양식 — 앞이 최근], at}} — 이 브라우저에 문서마다
const TMN_TPL_MAX = 6;
const TMN_ICON = '<svg viewBox="0 0 16 16" width="10" height="10" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.7" d="M2 2.8h12v10.4H2zM2 6.5h12M6.3 2.8v10.4"/></svg>';
const TMN_GUIDE_ICON = '<svg viewBox="0 0 16 16" width="10" height="10" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M2.6 13.4l.7-3.1 7.5-7.5 2.4 2.4-7.5 7.5zM9.4 4.2l2.4 2.4"/></svg>'; // 연필 — 여백 표지의 ✎(표 지침)와 같은 뜻
const tmn = { doc: null, active: null, afrag: null, hover: null, frag: null, btn: null, guide: null, hideTimer: null, anchor: null, seq: 0, pressOpen: null, pressAt: 0, watching: false, raf: 0 };
const tmnOk = (tid) => typeof tid === "string" && /^[\w.-]+$/.test(tid);
const tmnNoop = () => {};
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tablePrune: "빈 필드 제거" }); // 「기록」 탭의 이름(heading_temp.js 와 같은 방식 — 서식 입히기 `tableRestyle` 은 §11 것이라 그대로)

// ---- 고른 표 · 모서리 손잡이 ------------------------------------------------------------------------------------------
function tmnFragOf(node) { // 누른·올린 곳을 품은 가장 안쪽 표 조각(문서 자리 엑셀식 보기 .xl-wrap 포함)
  const e = node && (node.nodeType === 1 ? node : node.parentElement);
  return e && e.closest ? e.closest("#doc table.tbl[data-tbl], #doc .xl-wrap[data-tbl]") : null;
}
function tmnFragFor(tid) { // 그 표의 보이는 첫 조각(쪽마다 나뉜 표는 첫 쪽 것)
  return [...document.querySelectorAll(`#doc table.tbl[data-tbl="${tid}"], #doc .xl-wrap[data-tbl="${tid}"]`)].find((f) => !f.hidden) || null;
}
// 손잡이는 쪽(.sheet) 안이 아니라 **body 에 고정 위치(position: fixed)** 로 두고 transform 으로만 옮긴다 — 쪽 안 요소를 옮기면(다른 쪽으로 붙임·left/top) 다음 자리 재기가
// 문서 전체를 다시 배치한다(연구개발계획서 181표·74쪽 실측: 쪽을 바꿔 붙이면 28ms/번 · 같은 쪽 left/top 4ms · body 고정 left/top 2ms · transform 0ms —
// references/브라우저_강제배치_비용.md). 화면 좌표라 쪽 배율(zoom)과 무관하게 16px. 문서가 스크롤되면 따라가고(scroll → rAF), 표 위끝이 보기 밖으로 올라가도
// 표가 보이는 동안은 보기 위끝에 붙어 있다(긴 표에서도 메뉴를 바로). 표가 보기 밖이면 감춘다.
// 감추기는 **hidden 속성이 아니라 style.display** 로, 요소는 처음 한 번만 붙인다 — 주어가 넓은 `:has()` 규칙이 스타일시트에 있으면 body 아래 어디서든 hidden 속성을 바꾸거나
// 요소를 붙이고 뗄 때 브라우저가 문서 전체의 스타일을 다시 셈한다(이 손잡이를 만들 때 landing.css 의 `body:has(#empty:not([hidden]))` 가 그랬다 — 같은 문서 실측 115ms/번;
// 그 규칙은 같은 날 `body.no-doc` 로 바꿨지만, 표에 마우스가 드나들 때마다 도는 자리라 그런 규칙이 다시 생겨도 안 걸리게 둔다).
const tmnShown = () => !!tmn.btn && tmn.btn.style.display !== "none";
const tmnSee = (e, on) => { if ((e.style.display !== "none") !== on) e.style.display = on ? "" : "none"; }; // 바뀔 때만 쓴다
function tmnCornerBtn(cls, icon, label, title) { // 손잡이 자리의 단추 하나(표 메뉴 · 작성요령) — 같은 꼴·같은 마우스 처리
  const b = el("button", cls);
  b.type = "button";
  b.style.display = "none";
  b.tabIndex = -1; // Tab 차례에는 넣지 않는다(문서를 따라다니는 손잡이 — 표 칸 오른쪽 단추 메뉴에도 엑셀식 보기·서식 변환이, 여백 표지에도 ✎ 표 지침이 있다)
  b.innerHTML = icon;
  b.setAttribute("aria-label", label);
  b.title = title;
  b.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); }); // 문서의 커서·고른 칸·글 선택을 지킨다(포커스를 가져가지 않는다)
  b.addEventListener("mouseenter", () => { clearTimeout(tmn.hideTimer); tmn.hideTimer = null; }); // 표에서 손잡이로 건너옴 — 그대로 둔다
  b.addEventListener("mouseleave", () => tmnLeave());
  document.body.append(b);
  return b;
}
function tmnBtn() {
  if (tmn.btn) return tmn.btn;
  const b = tmnCornerBtn("tbl-corner", TMN_ICON, "표 메뉴", "표 메뉴 — 빈 필드 제거 · 엑셀식 보기 · 서식으로 변환 · 표 채우기");
  b.setAttribute("aria-haspopup", "menu");
  // 둘째 아이콘 — 작성요령 · 표 지침(spec_헤딩_추출 ② §16 「손잡이」·§18): 메뉴를 거치지 않고 문서 옆 열을 바로 연다. 클래스 이름은 .tbl-corner 와 겹치지 않게(손잡이 = 하나를 가리키는 선택자가 그대로 듣는다)
  const g = tmnCornerBtn("tbl-corner-guide", TMN_GUIDE_ICON, "작성요령 · 표 지침",
    "작성요령 · 표 지침 — 이 표의 작성요령을 보고 고칩니다(문서 옆 열)\n① 문서의 작성요령(표 안·앞뒤 안내 · 뒤따르는 「작성 요령」 표) ② 지침(양식·공통·이 표) ③ 칸 입력 규칙(칸에 값을 넣는 방식)");
  g.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const tid = g.dataset.for;
    if (!state.id || !tmnOk(tid) || !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
    tmnActivate(tid, tmn.hover === tid ? tmn.frag : null); // 연 표가 고른 표 — 마우스가 떠나도 두 아이콘이 남는다(표 메뉴와 같다)
    if (typeof tblAgentView !== "function") return;
    // 늘 보이는 아이콘이라 잘못 누르기 쉽다 — 열에 저장 안 한 지침·규칙 글이 있으면 지우지 않는다: 같은 표면 열을 그대로 두고(접혀 있으면 펴기만), 다른 표면 먼저 묻는다(tables.js tblAgentLeave)
    const a = heads.dlg === "tableAgent" ? heads.xl.agent : null;
    if (a && a.dirty()) {
      if (a.tid === tid) { if (typeof colFold === "function") colFold("heads", false); return; }
      if (typeof tblAgentLeave === "function" && !tblAgentLeave()) return;
    }
    tblAgentView(tid);
  });
  tmn.guide = g;
  const open = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const tid = b.dataset.for;
    const again = tmn.pressOpen === tid && performance.now() - tmn.pressAt < 1500; // 이 표의 메뉴가 열린 채 손잡이를 다시 누름 = 닫기(누르는 순간 공용 메뉴의 바깥 누름이 이미 닫았다)
    tmn.pressOpen = null;
    if (!again) tmnMenu(tid);
  };
  b.addEventListener("click", open);
  b.addEventListener("contextmenu", open);
  tmn.btn = b;
  return b;
}
function tmnDocCheck() { // 다른 문서를 열었거나 닫았으면 고른 표·올린 표를 푼다(표 id 는 문서마다 같은 꼴이라 남기면 엉뚱한 표에 붙는다)
  const key = state.id ? `${state.id}|${state.epoch}` : null;
  if (tmn.doc === key) return;
  tmn.doc = key;
  tmn.active = tmn.afrag = tmn.hover = tmn.frag = null;
  tmnPaintActive();
  tmnPreview(null);
}
const TMN_SIZE = 16, TMN_GAP = 4, TMN_STEP = 2; // 손잡이 한 변 · 표 오른쪽 변과의 틈(화면 px — 고른 표 테두리 2px 의 바깥) · 두 아이콘 사이 틈(세로)
// 손잡이 자리 — 마우스를 올린 표(없으면 고른 표)의 그 조각 **오른쪽 변 바로 바깥**(쪽 안 오른쪽 여백 — 비어 있는 자리라 표도 왼쪽 여백의 표지도 안 가린다), 표 위끝 높이(화면 좌표).
// 여백에 못 서는 표는 오른쪽 위 모서리 점에 가운데를 맞춰 표에 걸친다: 칸 안 표(바깥이 겉 표의 칸이라, 마우스가 손잡이로 건너가는 사이 올린 표가 겉 표로 바뀐다) · 종이 오른끝까지 찬 표.
// 둘째 아이콘(작성요령 · 표 지침)은 같은 x 로 **손잡이 바로 아래**(틈 2px) — 오른쪽 여백이 좁아도(옆으로 둘은 38px 가 든다) 한 줄 폭이면 서고, 둘 다 표 오른쪽 변에 붙어 있어 표에서 바로 건너간다.
// 읽기(자리 3번) 뒤 transform 만 쓴다.
function tmnPlace() {
  const b = tmnBtn(), g = tmn.guide, sc = $("scroller");
  tmnDocCheck();
  const tid = tmn.hover || tmn.active;
  const keep = tmn.hover ? tmn.frag : tmn.afrag;
  const frag = !tid || !state.id || sc.hidden ? null : keep && keep.isConnected && !keep.hidden && keep.dataset.tbl === tid ? keep : tmnFragFor(tid);
  if (!frag) { tmnSee(b, false); tmnSee(g, false); return; }
  if (tmn.hover) tmn.frag = frag; else tmn.afrag = frag;
  const fr = frag.getBoundingClientRect(), sr = sc.getBoundingClientRect();
  const viewR = sr.left + sc.clientLeft + sc.clientWidth; // 보기 오른끝(세로 스크롤 막대 안쪽)
  const out = fr.height < 4 || fr.bottom < sr.top + TMN_SIZE + 2 || fr.top > sr.bottom - TMN_SIZE - 2 || fr.right < sr.left + 12 || fr.left > viewR - 6; // 표가 보기 밖(스크롤) — 도구 줄·옆 열 위에 뜨지 않게
  tmnSee(b, !out);
  if (out) { tmnSee(g, false); return; }
  const sheet = frag.closest(".sheet");
  const margin = !!sheet && !frag.parentElement.closest("table.tbl") && sheet.getBoundingClientRect().right - fr.right >= TMN_SIZE + TMN_GAP; // 쪽에 바로 놓인 표 + 종이 안에 손잡이 자리
  const x = Math.min(margin ? fr.right + TMN_GAP : fr.right - TMN_SIZE / 2, viewR - TMN_SIZE - 2); // 표 오른쪽 변이 보기 밖(확대해 가로로 굴린 문서)이면 보기 오른끝에 붙는다
  const y = Math.max(margin ? fr.top : fr.top - TMN_SIZE / 2, sr.top + 2); // 위끝이 보기 위로 넘어갔으면 보기 위끝에 붙는다(위 out — 표 아래끝보다 내려가지는 않음)
  b.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  if (b.dataset.for !== tid) b.dataset.for = tid;
  b.classList.toggle("on", tid === tmn.active);
  const gy = Math.round(y) + TMN_SIZE + TMN_STEP;
  tmnSee(g, gy + TMN_SIZE <= sr.bottom - 2); // 표 위끝이 보기 아래끝에 걸려 둘째가 보기 밖으로 나가면 둘째만 감춘다(문서 아래의 줄 위에 뜨지 않게)
  g.style.transform = `translate(${Math.round(x)}px, ${gy}px)`;
  if (g.dataset.for !== tid) g.dataset.for = tid;
  g.classList.toggle("on", tid === tmn.active);
  const st = heads.xl && heads.xl.storeKey === tmn.doc ? heads.xl.store : null; // 이 문서의 것만(표 id 는 문서마다 같은 꼴 — 앞 문서의 기록을 읽지 않는다)
  const rec = st && st.tables ? st.tables[tid] : null; // 저장된 이 표 지침·칸 입력 규칙(tables.js xlStore — 아직 안 읽었으면 표시 없음)
  g.classList.toggle("has", !!(rec && (rec.instructions || rec.rules))); // 여백 표지의 ✎ 와 같은 표시(주황 점) — 적어 둔 글이 있는 표
}
function tmnLater() { // 스크롤·보기 크기·타자 뒤 — 한 프레임에 한 번만 다시 놓는다
  if (tmn.raf || !(tmn.hover || tmn.active || tmnShown())) return;
  tmn.raf = requestAnimationFrame(() => { tmn.raf = 0; tmnPlace(); });
}
function tmnPaintActive() { // 고른 표의 테두리(.tmn-active — 그 표의 조각마다). 쪽을 다시 나누면 조각이 새로 생기므로 tblMenuSync 가 다시 입힌다
  // (<style> 규칙으로 칠하면 조각이 새로 생겨도 남지만, 규칙을 바꿀 때마다 브라우저가 문서 전체의 스타일을 다시 셈할 수 있다 — 표를 누를 때마다 도는 일이라 요소 표시로)
  for (const e of document.querySelectorAll("#doc .tmn-active")) if (e.dataset.tbl !== tmn.active) e.classList.remove("tmn-active");
  if (!tmn.active) return;
  for (const e of document.querySelectorAll(`#doc table.tbl[data-tbl="${tmn.active}"], #doc .xl-wrap[data-tbl="${tmn.active}"]`)) e.classList.add("tmn-active");
}
function tmnActivate(tid, frag = null) {
  if (tmn.active === tid && (!frag || tmn.afrag === frag)) return;
  tmn.active = tid;
  tmn.afrag = frag;
  tmnPaintActive();
  tmnPlace();
}
function tmnLeave() { // 표 밖으로 나감 — 잠깐 뒤(손잡이로 건너가는 동안은 유지) 손잡이를 고른 표로 돌려보낸다
  if (tmn.hideTimer || !tmn.hover) return;
  tmn.hideTimer = setTimeout(() => { tmn.hideTimer = null; tmn.hover = null; tmn.frag = null; tmnPlace(); }, 260);
}
function tblMenuSync() { // tables.js tblMarksDraw 끝에서(쪽을 다시 나눔 · 문서를 엶 · 창 크기·맞춤 배율) — 다른 문서·없어진 표면 풀고 손잡이를 다시 놓는다
  tmnDocCheck();
  if (tmn.active && !xlBlock(tmn.active)) tmn.active = tmn.afrag = null;
  if (tmn.hover && !xlBlock(tmn.hover)) tmn.hover = tmn.frag = null;
  tmnPaintActive(); // 새로 생긴 조각에 고른 표 테두리를 다시
  tmnPlace();
  if (typeof tblHeadsSync === "function") tblHeadsSync(); // 직접 지정한 헤더 칸의 표시(table_edit.js — spec_owpml_편집 ② §5-4)도 새 칸 요소에 다시
}

// ---- 메뉴 상자(공용 ctx 메뉴를 빌림) · 문서 미리보기 ---------------------------------------------------------------------------
const tmnMine = () => !!ctx.menu && !ctx.menu.hidden && ctx.menu.dataset.by === "tmn";
function tmnWatch(m) { // 메뉴가 닫히면(바깥 누름·스크롤·Esc — app.js ctxClose) 미리보기를 걷는다
  if (tmn.watching) return;
  tmn.watching = true;
  new MutationObserver(() => {
    if (!m.hidden || m.dataset.by !== "tmn") return; // 항목을 눌러 하위 목록으로 바꾸는 동안은 닫혔다 바로 열린다 — 지금 상태로 본다
    delete m.dataset.by;
    tmnPreview(null);
  }).observe(m, { attributes: true, attributeFilter: ["hidden"] });
}
function tmnOpen(items) { // items: [글, 꼬리, 실행, 꺼짐, {title, cls, enter}] | null(구분선) — enter = 마우스를 올리거나 포커스가 갈 때(문서 미리보기)
  if (!tmn.anchor) return;
  const m = ctxMenu();
  tmnWatch(m);
  tmnPreview(null);
  m.dataset.by = "tmn"; // 자리 잡기 전에 — style 의 최대 높이·폭이 걸린 크기로 잰다
  ctxOpen(tmn.anchor, items.map((it) => (it ? it.slice(0, 4) : null)));
  const btns = [...m.querySelectorAll("button")];
  let k = 0;
  for (const it of items) {
    if (!it) continue;
    const b = btns[k++], o = it[4];
    if (!b || !o) continue;
    if (o.title) b.title = o.title;
    if (o.cls) b.classList.add(o.cls);
    if (o.enter) {
      b.addEventListener("mouseenter", o.enter);
      b.addEventListener("focus", o.enter);
      b.addEventListener("mouseleave", () => tmnPreview(null));
      b.addEventListener("blur", () => tmnPreview(null));
    }
  }
}
function tmnPreview(v) { // v = null(걷기) | {table, rows, cols}(지울 칸 — 그 줄 안에 통째로 든 칸) | {table}(표 양식으로 쓸 표) | {table, cells}(프로젝트 구성 자리의 항목 머리 칸 — 칸 id 들: tmnDivision)
  for (const e of document.querySelectorAll("#doc .tmn-hit, #doc .tmn-tpl-hit, #doc .tmn-div-hit")) e.classList.remove("tmn-hit", "tmn-tpl-hit", "tmn-div-hit");
  if (!v || !tmnOk(v.table)) return;
  if (v.cells) { for (const id of v.cells) for (const td of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(id)}"]`)) td.classList.add("tmn-div-hit"); return; }
  if (!v.rows && !v.cols) { for (const t of document.querySelectorAll(`#doc table.tbl[data-tbl="${v.table}"]`)) t.classList.add("tmn-tpl-hit"); return; }
  const rows = new Set(v.rows || []), cols = new Set(v.cols || []);
  const inside = (a, n, set) => { for (let i = a; i < a + n; i += 1) if (!set.has(i)) return false; return true; };
  for (const td of document.querySelectorAll(`#doc table.tbl[data-tbl="${v.table}"] > tbody > tr > td`)) {
    // 칸이 걸친 행 수 = 블록의 rowSpan — 쪽에 걸쳐 나뉜 칸(이어짐 칸)은 조각마다 rowSpan 이 줄어 있을 수 있어 data-rs(있으면)를 먼저 본다
    if ((rows.size && inside(+td.dataset.r, +td.dataset.rs || td.rowSpan, rows)) || (cols.size && inside(+td.dataset.c, td.colSpan, cols))) td.classList.add("tmn-hit");
  }
}
const tmnErr = (e, what) => (e && e.status === 404 && e.message === "Not Found" ? `서버가 옛 판입니다 — 서버를 다시 켜야 「${what}」 를 쓸 수 있습니다` : e.message);

// ---- 표 메뉴 ----------------------------------------------------------------------------------------------------------
function tmnMenu(tid) {
  const b = tmnOk(tid) ? xlBlock(tid) : null;
  if (!state.id || !b) { toast("그 표가 지금 문서에 없습니다"); return; }
  tmnActivate(tid, tmn.btn && tmn.btn.dataset.for === tid && tmn.hover === tid ? tmn.frag : null); // 메뉴를 연 표가 고른 표 — 마우스가 떠나도 손잡이가 남는다
  if (tmnShown()) { // 메뉴는 두 아이콘 아래에서 연다(둘째가 감춰져 있으면 손잡이 아래) — 둘째 아이콘(작성요령)을 가리지 않는다
    const low = tmn.guide && tmn.guide.style.display !== "none" ? tmn.guide : tmn.btn, r = low.getBoundingClientRect();
    tmn.anchor = { clientX: Math.round(r.left), clientY: Math.round(r.bottom + 3) };
  }
  const hwpx = state.format !== "docx", only = hwpx ? "" : "\n지금 hwpx 문서만 됩니다";
  const rg = typeof xlSelRange === "function" ? xlSelRange(tid) : null;
  const inCol = !!(heads.xl.col && heads.xl.col.tid === tid && heads.dlg === "xl");
  tmnOpen([
    [`표 ${tid} · ${b.nRows || "?"}×${b.nCols || "?"}`, "", tmnNoop, true, { cls: "tmn-head" }],
    null,
    ["빈 필드 제거하기", "▸", () => tmnPrune(tid), !hwpx || state.busy,
      { title: `입력하는 줄이 통째로 빈 줄을 찾아 지웁니다 — 줄이 하나도 안 남는 서브 테이블은 머리 행까지, 표는 표째(이 표만 있던 헤딩까지 — 먼저 묻습니다) · 값이 든 줄의 빈 칸은 그대로(실행 취소로 되돌림)${only}` }],
    [rg ? `엑셀식 보기 — 고른 칸 ${xlRangeName(rg)}` : inCol ? "엑셀식 보기 닫기" : "엑셀식 보기", "", () => { if (rg) xlColumn(tid, rg); else if (inCol) headsColClose(); else xlColumn(tid); }, false,
      { title: "문서 옆 열에 A1 격자 — 수식 자리 판정 · 계산 · 숫자 칸 · 엑셀로 받기\n표 칸을 끌어 고른 뒤 열면 그 범위만" }],
    ["서식으로 변환하기", "▸", () => tmnTemplates(tid), !hwpx || state.busy,
      { title: `표 양식(서식을 따올 표)을 고르면 이 표에 그 서식만 입힙니다 — 구조·글·칸 크기는 그대로(실행 취소로 되돌림)${only}` }],
    // 표 서식 점검(spec_헤딩_추출 ② §19 — table_style.js): 이 표 안에서 같은 자리(머리행 · 머리열 · 열 · 빈 값)의 칸끼리 서식이 같은지 — 문서 옆 열
    ["표 서식 점검…", "", () => tblStyleView(tid), !hwpx || typeof tblStyleView !== "function",
      { title: `이 표 안에서 머리행 · 머리열 · 열 · 빈 값 칸끼리 글꼴 · 크기 · 정렬 · 줄 간격 · 여백이 같은지 봅니다(문서 옆 열) — 고른 곳만 그 자리의 대표 서식에 맞춥니다(실행 취소로 되돌림)${only}` }],
    ["표 나누기", "▸", () => tsplitMenu(tid, () => tmnMenu(tid), tmn.anchor), !hwpx || state.busy || typeof tsplitMenu !== "function", // table_edit.js — spec_owpml_편집 ② §5-3
      { title: `필드 열을 나눠 표 2개로(헤더 열은 두 표에 똑같이 · 두 표 모두 원래 폭) · 나눈 표를 다시 나누기(4+1 → 2+3) · 다시 합치기${only}` }],
    null,
    // 표 채우기(spec_헤딩_추출 ② §18 — 사용자 2026-11-12 "모서리 버튼에 이 표의 작성 지침도 관리할 수 있도록 작성요령을 볼 수 있게 … 에이전트로 표 테이블 채우기 기능도").
    // 「작성요령 · 표 지침」 은 같은 날 메뉴에서 꺼내 손잡이 아래의 둘째 아이콘이 되었다(tmnBtn 의 .tbl-corner-guide)
    [rg ? `에이전트로 표 채우기 — 고른 칸 ${xlRangeName(rg)}…` : "에이전트로 표 채우기…", "", () => tblFillView(tid, rg), !hwpx || typeof tblFillView !== "function",
      { title: `작성요령 · 지침 · 칸 입력 규칙에 맞춰 빈 칸에 넣을 값을 LLM 이 자료에서 찾아 제안합니다(문서 옆 열) — 고른 제안만 문서에 들어갑니다(실행 취소로 되돌림)\n표 칸을 끌어 고른 뒤 열면 그 범위만${only}` }],
    ["키-값으로 보기 · 매핑…", "", () => tblKvView(tid), !hwpx || typeof tblKvView !== "function", { title: `값 칸마다 어느 머리글 아래의 칸인지(키)와 그 글(값)을 봅니다(문서 옆 열) — 다른 표의 같은 키 칸에서 값을 가져옵니다: 고른 빈 칸만 넣고 겹치면 덮지 않습니다(실행 취소로 되돌림) · 머리글이 다른 표는 매핑 규칙으로${only}` }], // table_kv.js — spec_테이블매니저 ② §7 「키-값 추출과 매핑」
    ["양식의 표 판정…", "", () => tblTypeView(tid), !hwpx || typeof tblTypeView !== "function", { title: `이 표의 판정(모든 칸의 역할)을 보고 양식의 확정본으로 저장합니다(문서 옆 열) — 같은 양식의 문서에서 구조가 꼭 같은 표는 값을 채워도 이 판정으로 읽습니다(문서는 안 바뀜 · 양식이 정해진 문서에서만)${only}` }], // table_types.js — spec_테이블매니저 ② §10 「양식의 표 판정」
    // 연구개발과제 문서(hwpx · 작업 종류 연구개발과제)에서만 — 일반 문서 · docx 에는 항목 자체가 없다(spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」 — 아래 tmnDivision)
    ...(hwpx && typeof taskRnd === "function" && taskRnd() ? [["프로젝트 구성에 맞추기…", "▸", () => tmnDivision(tid), state.busy || typeof divPlan !== "function",
      { title: "이 표에 든 구분 기준 자리(단계 · 차년도 · 기관마다 되풀이되는 행 · 열)를 프로젝트 구성에 맞춰 늘리고 줄입니다 — 자리마다 지금 수 → 프로젝트 구성의 수를 보이고, 고른 자리만 변경 계획을 세워 확인한 뒤 반영합니다(실행 취소로 되돌림)" }],
      // 구분 기준 열 넣기(spec_테이블매니저 ② §13 — table_divcol.js): 기관 · 차년도 · 단계 열을 넣고 값 줄마다 프로젝트 구성의 값을 골라 적는다(문서 옆 열)
      ["구분 기준 열 넣기…", "", () => tblDivColView(tid), state.busy || typeof tblDivColView !== "function",
        { title: "이 표에 기관 · 차년도 · 단계 열을 넣고, 값 줄마다 그 줄이 어느 기관 · 차년도 · 단계의 것인지 프로젝트 구성의 값에서 골라 적습니다(문서 옆 열) — 편집 구역이 읽은 값은 처음부터 골라져 있습니다(실행 취소로 되돌림)" }]] : []),
    null,
    ["이 표를 표 양식으로 지정", "", () => tmnSetTemplate(tid), !hwpx,
      { title: `이 표를 서식을 따올 표(표 양식)로 기억합니다 — 다른 표의 「서식으로 변환하기」 목록 맨 위에 나옵니다${only}` }],
    // 서식 관리자(spec_일반편집 ② §12 · 이름은 spec_서식복사 ② §2 — style_lib.js): 이 표의 서식을 서버 전체 보관함에 저장 — 문서 옆 열(「서식 복사」)이 이 표만 고른 채로 열린다(문서는 안 바뀜)
    ["서식 관리자에 저장…", "", () => styleSaveOpen({ table: tid }), !hwpx || typeof styleSaveOpen !== "function",
      { title: `이 표의 서식(괘선·음영·글자·문단 모양)을 서식 보관함에 저장합니다 — 다른 문서·워크플로우에서 새 표·빈 표·서식 입히기로 다시 씁니다(문서 옆 열에서 이름·띠 수를 정해 저장)${only}` }],
  ]);
}

// ---- 빈 필드 제거하기 ----------------------------------------------------------------------------------------------------
function tmnSpans(lines, name, max = 4) { // [3,4,5,8] → 「4~6 · 9」 — 이어진 묶음으로, 많으면 앞 max 묶음 + …
  const runs = [];
  for (const i of [...lines].sort((a, b) => a - b)) {
    const last = runs[runs.length - 1];
    if (last && last[1] === i - 1) last[1] = i; else runs.push([i, i]);
  }
  return runs.slice(0, max).map(([a, b]) => (a === b ? name(a) : `${name(a)}~${name(b)}`)).join(" · ") + (runs.length > max ? " …" : "");
}
// 빈 것으로 본 까닭(spec_테이블매니저 ② §4 ⓑ — 서버 `why {rows: {줄: [자리표시 글…]}, cols}`): 그 줄의 빈 필드에 든 자리표시 글. 「00%」·「0,000」 은 사람이 쓴 값일 수도 있어 줄 이름 옆에 보인다.
// 글이 없는 칸뿐인 줄(빈 목록)·옛 서버(why 없음)에는 아무것도 더하지 않는다.
const tmnWhyOf = (why, i) => (why && Array.isArray(why[i]) ? why[i].filter((s) => typeof s === "string" && s) : []);
const tmnWhyText = (texts, sep = " · ") => texts.map((s) => `「${s}」`).join(sep);
function tmnLines(lines, names, name, why, max = 24) { // 도움말 — 줄마다 「4행 「연구활동비」」 · 자리표시 글이 든 줄은 「3행 「재료비」 — 자리표시 「00%」」
  const out = lines.slice(0, max).map((i) => {
    const w = tmnWhyOf(why, i);
    return `${name(i)}${names && names[i] ? ` 「${names[i]}」` : ""}${w.length ? ` — 자리표시 ${tmnWhyText(w)}` : ""}`;
  });
  return out.join("\n") + (lines.length > max ? `\n… 외 ${lines.length - max}줄` : "");
}
function tmnWhyNote(rows, cols, why, max = 4) { // 목록의 안내 줄 — 자리표시 글이 든 줄만 「2행 「00%」 · C열 「0,000」」(없으면 "")
  const out = [];
  for (const i of rows) { const w = tmnWhyOf(why && why.rows, i); if (w.length) out.push(`${i + 1}행 ${tmnWhyText(w, " ")}`); }
  for (const i of cols) { const w = tmnWhyOf(why && why.cols, i); if (w.length) out.push(`${colLetter(i)}열 ${tmnWhyText(w, " ")}`); }
  return out.slice(0, max).join(" · ") + (out.length > max ? ` … 외 ${out.length - max}줄` : "");
}
async function tmnPrune(tid) {
  const seq = ++tmn.seq, epoch = state.epoch;
  const head = [`‹ 빈 필드 제거하기 · ${tid}`, "", () => tmnMenu(tid), false, { cls: "tmn-back", title: "표 메뉴로" }];
  tmnOpen([head, null, ["빈 필드를 찾는 중…", "", tmnNoop, true]]);
  let p = null, err = "";
  try {
    await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서의 칸 글로 판정한다
    p = await api(`/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/prune`, { method: "POST", headers: H_JSON, body: JSON.stringify({ dry: true }) });
  } catch (e) { err = tmnErr(e, "빈 필드 제거"); }
  if (seq !== tmn.seq || epoch !== state.epoch || !tmnMine()) return; // 그 사이 메뉴를 닫았거나 다른 목록을 엶
  const items = [head, null];
  if (err) { items.push([err, "", tmnNoop, true]); tmnOpen(items); return; }
  // 빈 필드 = 서브 테이블의 입력하는 줄(레코드)이 통째로 빈 것(사용자 2026-11-22 — spec_테이블매니저 ② §12): 값이 든 줄의 빈 칸 · 빈 열은 그대로다(「빈 열 지우기」 는 없앴다).
  // 서버의 계획(action · planId)이 둘 중 하나를 낸다 — rows(빈 줄 · 빈 서브 테이블 — 누르면 바로 지움) | table(지우면 입력 줄이 안 남는 표 — 표째 · 소속 헤딩까지: 확인 창을 거친다)
  const rows = p.emptyRows || [], bands = p.bands || [];
  const rowName = (i) => `${i + 1}`;
  const why = p.why || {}; // 줄마다 빈 것으로 본 까닭(자리표시 글)
  const held = (p.held || []).length; // 지금 표와 맞지 않아 보류된 헤더 지정(spec_테이블매니저 ② §3 「사람의 헤더 지정」) — 있으면 서버가 지우기를 409 로 막는다: 여기서 미리 끄고 까닭을 보인다
  const off = state.busy || held > 0;
  if (held) {
    items.push([`헤더 지정 ${nf(held)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요`, "", tmnNoop, true,
      { cls: "tmn-note", title: "지정한 칸의 자리나 글이 그 뒤 바뀌었습니다 — 어느 칸의 지정인지 분명하지 않아 쓰지 않고 남겨 두었습니다\n다시 지정하거나 풀 때까지 이 표의 빈 필드 제거는 멈춥니다(아래는 그 지정 없이 본 것)" }]);
  }
  const rule = "\n\n빈 줄 = 입력하는 값 칸이 모두 비었거나 자리표시(0,000 · ○○)뿐인 줄 — 기관 이름 · 연도 · 번호 같은 구분 칸은 입력값으로 세지 않습니다\n값이 하나라도 든 줄의 빈 칸은 그대로 둡니다";
  const bandText = (b) => `「${b.name || `${b.rows[0] + 1}~${b.rows[1] + 1}행`}」${b.how === "orphan" ? "(머리만 남음)" : ""}`;
  if (p.action === "table") {
    const sc = p.scope || {}, h = sc.heading;
    const all = [...Array(p.rows || 0).keys()];
    items.push([h ? `표와 헤딩 「${h.text}」 지우기…` : "표 지우기…", "", () => tmnPruneTable(tid, p), off,
      { title: `이 표는 입력하는 줄이 모두 비었습니다 — 표째 지웁니다${h ? `\n이 표만 있던 헤딩 「${h.text}」 도 함께 지웁니다` : ""}${rule}\n누르면 먼저 묻습니다 · 도구 줄의 실행 취소로 되돌립니다`,
        enter: () => tmnPreview({ table: tid, rows: all }) }]);
    if (!h && sc.why) items.push([`헤딩은 남깁니다 — ${sc.why.replace(/ 헤딩은 남깁니다$/, "")}`, "", tmnNoop, true, { cls: "tmn-note" }]);
  } else if (rows.length) {
    const label = `빈 줄 ${nf(rows.length)}개 지우기 — ${tmnSpans(rows, rowName)}행${bands.length ? ` · 서브 테이블 ${nf(bands.length)}개째` : ""}`;
    const bandLines = bands.length ? `\n\n서브 테이블째(입력하는 줄이 하나도 안 남음 — 머리 행까지): ${bands.map(bandText).join(" · ")}` : "";
    items.push([label, "", () => tmnPruneRun(tid, p), off,
      { title: tmnLines(rows.filter((i) => p.rowNames && p.rowNames[i] != null), p.rowNames, (i) => `${i + 1}행`, why.rows) + bandLines + rule + "\n누르면 바로 지웁니다 · 도구 줄의 실행 취소로 되돌립니다",
        enter: () => tmnPreview({ table: tid, rows }) }]);
  } else {
    items.push([p.scope && p.scope.block ? p.scope.block : p.note || "입력하는 줄이 통째로 빈 줄이 없습니다", "", tmnNoop, true, { cls: "tmn-note", title: rule.trim() }]);
  }
  const whyNote = p.action === "rows" ? tmnWhyNote(rows, [], why) : ""; // 자리표시 글이 든 줄 — 도움말을 안 봐도 지우기 전에 보이게(누르면 바로 지운다)
  if (whyNote) {
    items.push([`자리표시로 보아 빈 칸으로 센 글 — ${whyNote}`, "", tmnNoop, true,
      { cls: "tmn-note", title: "양식의 자리표시 꼴(0,000 · 00% · ○○)인 글은 빈 필드로 셉니다 — 사람이 쓴 값이면 그 줄은 지우지 마세요\n줄마다의 글은 위 항목의 도움말에도 보입니다(「3행 「재료비」 — 자리표시 「00%」」)" }]);
  }
  if ((p.kept || []).length) {
    items.push([`쓴 값이 있어 남긴 줄 — ${tmnSpans(p.kept, rowName)}행`, "", tmnNoop, true,
      { cls: "tmn-note", title: "지우면 함께 없어질 칸에 쓴 값(수 · 글 · 그림)이 있습니다 — 머리로 읽힌 칸의 수(「24,000」)나 합계 칸에 적힌 값도 셉니다" }]);
  }
  const skipR = p.skipRows || [], skipB = p.skipBands || [];
  if (skipR.length || skipB.length) {
    items.push([`합친 칸에 걸려 못 지움 — ${[skipR.length ? `${tmnSpans(skipR, rowName)}행` : "", ...skipB.map(bandText)].filter(Boolean).join(" · ")}`, "", tmnNoop, true,
      { cls: "tmn-note", title: "그 줄에서 시작해 옆 줄로 넘어가는 합친 칸이 있습니다(서브 테이블은 통째로만 지웁니다) — 칸을 끌어 골라 「행·열 지우기」 로 지우세요" }]);
  }
  if (p.fields) items.push(null, [`채우는 필드 ${nf(p.fields)}개 · 빈 필드 ${nf(p.emptyFields)}개${p.keys ? ` · 구분 칸 ${nf(p.keys)}개` : ""}`, "", tmnNoop, true,
    { cls: "tmn-note", title: "채우는 필드 = 칸 역할이 필드인 칸에서 수식으로 셈하는 칸(합계·비율)과 구분 칸을 뺀 것\n구분 칸 = 기관 이름 · 연도 · 차년도 · 단계 · 번호 머리 아래의 칸 — 줄의 이름표라 입력값으로 세지 않습니다" }]);
  tmnOpen(items);
}
async function tmnPruneRun(tid, p) {
  const r = await structOp(`tables/${encodeURIComponent(tid)}/prune`, { action: "rows", planId: p.planId, rev: p.rev }); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
  if (!r || !r.pruned) return;
  const d = r.pruned, bands = d.bands || [];
  const skip = (d.skipRows || []).length + (d.skipBands || []).length;
  toast(`표 ${tid} — 빈 줄 ${nf((d.rows || []).length)}개를 지웠습니다${bands.length ? `(서브 테이블 ${bands.map((b) => `「${b.name}」`).join(" · ")} 째)` : ""}${skip ? ` · 합친 칸에 걸린 ${skip}곳은 그대로` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
}
async function tmnPruneTable(tid, p) { // 표째(· 소속 헤딩까지) — 떨어진 여러 블록이 없어지므로 확인을 받고, 지운 뒤 문서를 다시 읽는다(heading_temp.js 의 TEMP 지우기와 같은 꼴)
  if (state.busy || !state.id) return;
  const sc = p.scope || {}, h = sc.heading;
  if (!confirm(`표 ${tid} 를 지울까요?${h ? `\n이 표만 있던 헤딩 「${h.text}」 도 함께 지웁니다.` : ""}${sc.caption ? `\n표의 캡션 「${sc.caption}」 도 함께 없어집니다.` : ""}\n\n입력하는 줄이 모두 비어 있습니다. 표준 검사에 걸리면 전부 되돌립니다 · 지운 뒤 「실행 취소」 로 되돌릴 수 있습니다.`)) return;
  ctxClose();
  tmnPreview(null);
  const epoch = state.epoch, id = state.id;
  state.busy = true; // 먼저 잡는다(structOp 와 같게) — 글 반영을 기다리는 사이 다른 편집이 끼지 않게
  refreshToolbar();
  let done = false;
  try {
    await flushAll(); // 아직 반영 안 된 글부터 — 서버 문서를 지운다
    if (epoch !== state.epoch) return;
    if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 먼저 다시 반영해야 합니다 — 「고친 문단」 탭", true); return; } // 저장 못 한 글이 있으면 지우지 않는다(astra 2차)
    const r = await api(`/api/docs/${encodeURIComponent(id)}/tables/${encodeURIComponent(tid)}/prune`, { method: "POST", headers: H_JSON, body: JSON.stringify({ action: "table", planId: p.planId, rev: p.rev }) });
    if (epoch !== state.epoch) return;
    done = true;
    state.localRev += 1;
    state.structRev = state.localRev; // 표 판정 캐시(tables.js)도 새로
    applyEditState(r);
    toast(`표 ${tid}${h ? `와 헤딩 「${h.text}」` : ""}를 지웠습니다 — 도구 줄의 「실행 취소」 로 되돌릴 수 있습니다`);
    await reloadDoc(); // 떨어진 블록(헤딩 · 표 · 사이 빈 줄)이 없어져 문서를 다시 읽는다
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (done) { toast(`표는 지웠습니다 — 화면을 다시 읽지 못했습니다(새로 고침하세요): ${e.message}`, true); return; }
    if (epoch !== state.epoch) return;
    toast(e.status === 422 ? `표준 검사에 걸려 되돌렸습니다: ${e.message}` : `지우지 못했습니다: ${e.message}`, true);
  } finally {
    if (epoch === state.epoch) {
      state.busy = false;
      refreshToolbar();
    }
  }
}

// ---- 프로젝트 구성에 맞추기(spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」 — 구성 개선 묶음 · 연구개발과제 문서만) ------------------------------------------
// **입구**일 뿐이다 — 이 표에 든 구분 기준 자리(행 · 열 묶음 · 칸 안의 문단 묶음)를 「지금 n개 → 프로젝트 구성 m개」 로 보이고, 고른 자리는 「프로젝트 구성 반영」 의 기존 길로 간다:
//   divPlan({only, table}) = 「변경 계획 보기」(그 자리와 그 안쪽 자리만 · 문서는 안 바뀜 · 문서 옆 목록은 이 표의 자리만) → 목록 발의 「반영 단추로 이동」 → 패널 실행 묶음의 「반영」(divApply).
// 새 반영 끝점 · 새 계획 계산 · 새 안전 검사를 만들지 않는다 — 할 수 없는 까닭(divRunWhy) · 다른 실행이 도는 동안(divRunLocked) · 계획에 묶인 반영(planId · 문서 차례)은 그 길의 것 그대로다.
// 자리 목록 = GET …/divisions/members?targets=1(읽기 전용): 묶음마다 where.table · where.cell, targets[묶음 key] = {target(프로젝트 구성에 맞춘 수), done, reason, why} · 프로젝트 구성 값이 없으면 targets = null.
// app.js 가 주는 것(파일 머리의 것에 더해): dv · divShow · divRunWhy · divRunLocked · divPlan · divSettingsFlush · showTab · taskRnd.
const TMN_DIV_KIND = { rows: "행", cols: "열", list: "목록 행", paragraph: "문단 묶음(칸 안)" }; // 자리의 종류 — 표 안에서 부르는 이름(「차년도 행」 · 「기관 열」)
const tmnDivCut = (s, n = 12) => { const t = String(s || "").replace(/\s+/g, " ").trim(); return t.length > n ? `${t.slice(0, n)}…` : t; };
function tmnDivIds(tid, deep) { // 그 표의 id + 칸 id(deep = 칸 안 표와 그 칸까지) — 자리의 where.table · where.cell 과 견준다
  const ids = new Set();
  const walk = (t) => {
    ids.add(t.id);
    for (const c of t.cells || []) { ids.add(c.id); if (deep) for (const b of c.blocks || []) if (b.type === "table") walk(b); }
  };
  const b = xlBlock(tid);
  if (b) walk(b);
  return ids;
}
async function tmnDivision(tid) {
  const seq = ++tmn.seq, epoch = state.epoch, what = "프로젝트 구성에 맞추기";
  const head = [`‹ ${what} · ${tid}`, "", () => tmnMenu(tid), false, { cls: "tmn-back", title: "표 메뉴로" }];
  tmnOpen([head, null, ["이 표의 자리를 찾는 중…", "", tmnNoop, true]]);
  let m = null, err = "";
  try {
    await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서에서 자리를 찾는다
    if (typeof divSettingsFlush === "function") await divSettingsFlush(); // 입력 중인 프로젝트 구성 값도 작업에 — 「프로젝트 구성 m개」 는 서버의 값으로 센다
    m = await api(`/api/docs/${encodeURIComponent(state.id)}/divisions/members?targets=1`);
    if (epoch === state.epoch && (!dv.view || !dv.values)) await divShow(); // 프로젝트 구성 화면을 아직 안 열었으면 그 상태부터 읽는다 — 아래 divRunWhy 와 divPlan 이 화면의 값을 쓴다
  } catch (e) { err = tmnErr(e, what); }
  if (seq !== tmn.seq || epoch !== state.epoch || !tmnMine()) return; // 그 사이 메뉴를 닫았거나 다른 목록을 엶
  const items = [head, null], note = (text, title = "") => items.push([text, "", tmnNoop, true, { cls: "tmn-note", title }]);
  if (err) { items.push([err, "", tmnNoop, true]); tmnOpen(items); return; }
  if (!("targets" in m)) { note(`서버가 옛 판입니다 — 서버를 다시 켜야 「${what}」 를 쓸 수 있습니다`); tmnOpen(items); return; }
  if (m.supported === false) { note("이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다"); tmnOpen(items); return; }
  const own = tmnDivIds(tid, false);
  const places = (m.groups || []).filter((g) => g.where && (own.has(g.where.table) || own.has(g.where.cell))); // 이 표의 행 · 열 묶음 + 이 표의 칸 안 문단 묶음(칸 안 표의 자리는 그 표의 메뉴에서)
  if (!places.length) {
    note("이 표에는 프로젝트 구성으로 늘리고 줄일 자리가 없습니다", "단계 · 차년도 · 기관마다 되풀이되는 행 · 열(구분 기준 자리)이 이 표에서 잡히지 않았습니다");
    tmnOpen(items);
    return;
  }
  const targets = m.targets, ready = !!dv.view && !!dv.values; // targets null = 프로젝트 구성 값이 아직 없음
  const why = targets && ready ? divRunWhy() : "", busy = state.busy || dv.busy || divRunLocked();
  const go = ["프로젝트 구성 열기", "", () => showTab("Div"), false, { title: "패널의 프로젝트 구성으로 갑니다 — 단계 · 차년도 · 기관을 정한(확정한) 뒤 이 메뉴를 다시 여세요" }];
  if (!targets) note("프로젝트 구성을 먼저 정하세요", "단계 · 차년도 · 기관을 정해야 이 표의 자리를 몇 개로 맞출지 압니다 — 아래에는 지금 수만 보입니다");
  else if (why) note(`지금은 변경 계획을 세울 수 없습니다 — ${why}`);
  else items.push([`이 표의 자리 ${nf(places.length)}곳 — 누르면 그 자리만 변경 계획을 봅니다`, "", tmnNoop, true, { cls: "tmn-sec" }]);
  const names = places.map((g) => `${g.dimName || g.dim} ${TMN_DIV_KIND[g.kind] || g.kindName || g.kind}`);
  let can = 0;
  places.forEach((g, i) => {
    const labels = (g.items || []).map((it) => tmnDivCut(it.text, 40)).filter(Boolean), cells = (g.items || []).map((it) => it.label).filter(Boolean);
    const twin = names.filter((n) => n === names[i]).length > 1; // 같은 이름의 자리가 이 표에 여럿이면 첫 항목의 글로 가른다
    const name = names[i] + (twin && labels.length ? ` 「${tmnDivCut(labels[0])}」` : ""), now = `지금 ${nf(g.count)}개`;
    const list = labels.length ? `항목 — ${labels.slice(0, 8).map((s) => `「${s}」`).join(" · ")}${labels.length > 8 ? ` … (${nf(labels.length)}개)` : ""}` : "";
    const enter = () => tmnPreview({ table: tid, cells }); // 올리면 문서에서 그 자리의 항목 머리 칸을 칠한다
    const off = (text, title = "") => items.push([`${name} — ${text}`, "", tmnNoop, true, { cls: "tmn-note", title: [list, title].filter(Boolean).join("\n"), enter }]);
    const t = targets ? targets[g.key] : null;
    if (!targets) { off(now); return; }
    if (!t) { off(`${now} · 프로젝트 구성에 맞춘 수를 읽지 못했습니다`); return; }
    if (t.done) { off(`${now} · 이미 프로젝트 구성에 맞습니다`); return; }
    const to = t.target == null ? "" : ` → 프로젝트 구성 ${nf(t.target)}개`;
    if (t.target == null || (t.reason && t.reason !== "nested")) { off(`${now}${to} · 맞추지 못합니다${t.why ? ` — ${t.why}` : ""}`, "이 자리는 지금 자동으로 늘리고 줄이지 못합니다 — 손으로 맞추세요"); return; }
    can += 1;
    items.push([`${name} — ${t.target === g.count ? `${now} · 프로젝트 구성 ${nf(t.target)}개(수는 같음 — 항목의 글 · 꼴을 맞춥니다)` : `${now}${to}`}`, "", () => tmnDivisionPlan(tid, g.key), busy || !!why,
      { title: [list, busy ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : why || "누르면 이 자리와 그 안쪽 자리만의 변경 계획을 세워 문서 옆 목록에 보입니다 — 문서는 바뀌지 않습니다(몇 초)\n반영은 그 목록을 확인한 뒤 패널의 「반영」 단추로 · 실행 취소로 되돌립니다",
        t.reason === "nested" ? "바깥 자리 안에 든 자리입니다 — 바깥 자리를 맞출 때 함께 맞춰집니다" : ""].filter(Boolean).join("\n"), enter }]);
  });
  if (!targets || why) items.push(null, go);
  else if (can) note("반영은 변경 계획 목록을 확인한 뒤 패널의 「반영」 단추로 합니다(목록 아래 「반영 단추로 이동」) · 실행 취소로 되돌립니다");
  tmnOpen(items);
}
async function tmnDivisionPlan(tid, key) { // 그 자리만의 「변경 계획 보기」 — 기존 divPlan 을 부를 뿐이다(계획은 문서를 바꾸지 않는다 · 반영은 패널 실행 묶음의 「반영」)
  const id = state.id, epoch = state.epoch;
  if (!dv.view || !dv.values) await divShow(); // divPlan 은 화면의 값(divValues)을 서버에 보낸다 — 안 읽은 채 부르면 기본값이 간다
  if (epoch !== state.epoch || id !== state.id) return;
  if (!dv.view || !dv.values) { toast("프로젝트 구성 상태를 읽지 못했습니다 — 패널의 프로젝트 구성을 연 뒤 다시 하세요", true); return; }
  const why = divRunWhy(); // 패널의 「변경 계획 보기」 단추와 같은 검사(지원 양식 · 차년도 수 · TASK 의 프로젝트 구성 확정)
  if (why) { toast(why, true); return; }
  if (dv.busy || divRunLocked()) { toast("지금 진행 중인 작업이 끝나면 쓸 수 있습니다", true); return; }
  toast(`표 ${tid} — 고른 자리의 변경 계획을 세우는 중…(문서는 바뀌지 않습니다)`);
  await divPlan({ only: key, table: { id: tid, ids: tmnDivIds(tid, true) } });
}

// ---- 서식으로 변환하기 — 표 양식 목록 ---------------------------------------------------------------------------------------
function tmnTplList() { // 최근 쓴 표 양식(이 문서 · 지금 문서에 있는 표만)
  try {
    const r = JSON.parse(localStorage.getItem(TMN_TPL_KEY) || "{}")[state.id];
    return r && Array.isArray(r.ids) ? r.ids.filter((i) => tmnOk(i) && xlBlock(i)) : [];
  } catch { return []; }
}
function tmnTplRemember(tid) {
  try {
    const all = JSON.parse(localStorage.getItem(TMN_TPL_KEY) || "{}");
    const was = all[state.id] && Array.isArray(all[state.id].ids) ? all[state.id].ids : [];
    all[state.id] = { ids: [tid, ...was.filter((i) => i !== tid)].slice(0, TMN_TPL_MAX), at: Date.now() };
    for (const k of Object.keys(all).sort((a, b) => (all[b].at || 0) - (all[a].at || 0)).slice(40)) delete all[k];
    localStorage.setItem(TMN_TPL_KEY, JSON.stringify(all));
  } catch { /* 기억만 안 함 */ }
}
function tmnDesignated() { // 2열 「표 만들기 · 서식 변환」 에서 고른 표 양식(table_make.js 가 기억한 것)
  try {
    const r = JSON.parse(localStorage.getItem(typeof TMK_KEY === "string" ? TMK_KEY : "nfm.tblMake") || "{}")[state.id];
    return r && tmnOk(r.tpl) && xlBlock(r.tpl) ? r.tpl : null;
  } catch { return null; }
}
function tmnTemplates(tid) {
  const head = [`‹ 서식으로 변환하기 · ${tid}`, "", () => tmnMenu(tid), false, { cls: "tmn-back", title: "표 메뉴로" }];
  const isTemp = (id) => typeof tempTableItem === "function" && !!tempTableItem(id); // TEMP 표(작성 요령 표·안내 상자 — heading_temp.js, ② §15)는 나중에 지울 표라 양식 후보에서 뺀다
  const all = xlBlocks().filter((b) => b.id !== tid && b.rows * b.cols > 1 && !isTemp(b.id)); // 1칸 표(글상자)는 표 양식으로 쓸 구역이 없다
  const byId = new Map(all.map((b) => [b.id, b]));
  const recent = [...new Set([tmnDesignated(), ...tmnTplList()])].filter((i) => i && byId.has(i));
  const name = (b) => (typeof tmkTableName === "function" ? tmkTableName(b) : `${b.id} · ${b.rows}×${b.cols}`);
  const pick = (b) => [name(b), "", () => tmnRestyle(tid, b.id), state.busy,
    { cls: "tmn-tpl", title: `${name(b)}\n누르면 이 표의 괘선·음영·칸 여백·문단/글자 모양을 표 ${tid} 에 입힙니다 — 구조·글·칸 크기는 그대로`, enter: () => tmnPreview({ table: b.id }) }];
  const items = [head, null];
  if (!all.length) items.push(["서식을 따올 다른 표가 없습니다", "", tmnNoop, true, { cls: "tmn-note" }]);
  else {
    if (recent.length) items.push(["최근 쓴 표 양식", "", tmnNoop, true, { cls: "tmn-sec" }], ...recent.map((i) => pick(byId.get(i))), null);
    const rest = all.filter((b) => !recent.includes(b.id));
    if (rest.length) items.push([`문서의 표 ${nf(rest.length)}개 — 누르면 그 표의 서식을 입힙니다`, "", tmnNoop, true, { cls: "tmn-sec" }], ...rest.map(pick));
  }
  items.push(null, ["자세히 — LLM 정리 · 구역 수 · 새 표로 바꾸기…", "", () => { if (typeof tmkOpen === "function") tmkOpen({ table: tid }); }, typeof tmkOpen !== "function",
    { title: "문서 옆 열 「표 만들기 · 서식 변환」 — 머리행·머리열·합계행 수를 고치거나, LLM 으로 표를 다시 정리하거나, 새 표로 바꿉니다" }]);
  tmnOpen(items);
}
async function tmnRestyle(tid, tpl) {
  const r = await structOp("tables/restyle", { table: tid, template: tpl }); // 구역 수는 서버가 두 표 모두 자동 판정(고치려면 「자세히」)
  if (!r || !r.made) return;
  tmnTplRemember(tpl);
  toast(`표 ${tid} 에 표 양식 ${tpl} 의 서식을 입혔습니다 — 문단 ${nf(r.made.formatted)}개 모양 바뀜 · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
}
function tmnSetTemplate(tid) {
  tmnTplRemember(tid);
  // 2열 「표 만들기 · 서식 변환」 의 표 양식도 같은 표로. 그 열을 이 문서에서 연 적이 있으면(tmk 가 이 문서 것) 화면 상태째 맞추고, 아니면 기억(nfm.tblMake)만 고친다 —
  // tmk 는 문서가 바뀌어도 tmkOpen 때까지 앞 문서 것이라, 그대로 tmkRemember 를 부르면 앞 문서의 구역 수가 이 문서에 저장되거나 기억해 둔 구역 수가 지워진다.
  if (typeof tmk === "object" && tmk && tmk.doc === `${state.id}|${state.epoch}` && typeof tmkRemember === "function") {
    if (tmk.tpl !== tid) { tmk.tpl = tid; tmk.tplRoles = null; tmk.tplSize = null; }
    tmkRemember();
    if (typeof tmkOn === "function" && tmkOn()) { tmkDraw(); tmkLoadRoles(); }
  } else {
    try {
      const key = typeof TMK_KEY === "string" ? TMK_KEY : "nfm.tblMake";
      const all = JSON.parse(localStorage.getItem(key) || "{}"), was = all[state.id];
      all[state.id] = { tpl: tid, roles: was && was.tpl === tid ? was.roles || null : null, at: Date.now() }; // 같은 표를 다시 지정하면 고쳐 둔 구역 수는 그대로
      localStorage.setItem(key, JSON.stringify(all));
    } catch { /* 기억만 안 함 */ }
  }
  toast(`표 ${tid} 을 표 양식으로 지정했습니다 — 다른 표의 메뉴 「서식으로 변환하기」 맨 위에 나옵니다`);
}

// ---- 묶기 -------------------------------------------------------------------------------------------------------------
function tmnBind() {
  const doc = $("doc");
  if (!doc) return;
  tmnBtn(); // 손잡이는 지금(문서를 열기 전) 한 번만 붙인다 — 큰 문서가 열린 뒤에 붙이면 문서 전체 스타일을 다시 셈한다(tmnBtn 주석)
  // 누르기 시작할 때 이 표의 메뉴가 열려 있었는가 — 공용 메뉴의 바깥 누름 닫기(document 캡처)보다 먼저(window 캡처) 적어 둔다: 손잡이의 click 이 「다시 누름 = 닫기」 를 가린다
  window.addEventListener("mousedown", () => { tmn.pressOpen = tmnMine() ? tmn.active : null; tmn.pressAt = performance.now(); }, true);
  doc.addEventListener("mouseover", (e) => {
    if (e.buttons) return; // 끄는 중(칸 고르기·문단 묶음 고르기)에는 그대로
    const frag = tmnFragOf(e.target);
    if (!frag || !tmnOk(frag.dataset.tbl)) { tmnLeave(); return; }
    clearTimeout(tmn.hideTimer);
    tmn.hideTimer = null;
    tmn.hover = frag.dataset.tbl;
    tmn.frag = frag;
    tmnPlace(); // 같은 표 안에서도 다시 — 글을 고쳐 표가 밀렸을 수 있다(자리 재기 2번 · 쓰기는 transform 뿐이라 배치를 다시 하지 않는다)
  });
  doc.addEventListener("mouseleave", () => tmnLeave());
  doc.addEventListener("mousedown", (e) => { // 표를 누르면 그 표가 고른 표 · 표 밖(문서)을 누르면 풂. 표지(.tbl-mark)를 눌러도 그 표
    const mark = e.target.closest ? e.target.closest(".tbl-mark") : null;
    const frag = mark ? null : tmnFragOf(e.target);
    const tid = mark ? mark.dataset.for : frag ? frag.dataset.tbl : null;
    tmnActivate(tmnOk(tid) ? tid : null, frag);
  });
  doc.addEventListener("input", tmnLater); // 타자로 줄이 늘어 표가 밀리면 손잡이도 따라간다
  const sc = $("scroller");
  sc.addEventListener("scroll", tmnLater, { passive: true }); // 손잡이는 화면 좌표(고정 위치) — 문서가 스크롤되면 다시 놓는다
  if (typeof ResizeObserver === "function") new ResizeObserver(tmnLater).observe(sc); // 옆 열 여닫기·창 크기로 문서 보기가 옮겨짐(문서를 닫아 감춰질 때도 — 손잡이를 감춘다)
}
tmnBind();
