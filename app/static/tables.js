"use strict";
// 표 모듈(spec_헤딩_추출 ② §10 「모듈」) — 본문(app.js)과 따로, 문서의 표만 다룬다(사용자 2026-11-10 "본문 따로, 테이블 따로"):
// 표 식별 표지(.tbl-mark) · 엑셀식 보기(2열 kind "xl" · 문서 자리 .xl-wrap — A1 격자 · 수식 엔진 · 문서에 반영) · 표 지침(2열 kind "tableAgent", 표 에이전트 입력) · 「표」 탭(#paneTables).
// app.js 가 주는 것: state·heads(view·tbl·xl·dlg·seq)·$·el·api·toast·hBtn·hTable·hCell·hFoot·headsDlg·headsColClose·headsGo·headsShow·headsStart·headsLlmTables·headsTables·headsParaLink·
// headsCard3·colLetter·basisNames·ownerLabel·short·oneLine·nf·hasBlock·renderPara·applyServer·refreshSaveState·updateEdits·fmtWhen·H_JSON·LS·gutterSync·sheetMarginPx·
// dvKeyOf·dvTag·dvOfDivision(구분 라벨의 색 = 그 구분의 「구분 기준 자리」 색).
// app.js 가 부르는 것(typeof 검사 뒤): tblMarksDraw(paginate 끝·headsRender 끝·setTwoUp) · tblMarksPlace(tplMarksDraw 끝 — 「TN Lk」 표를 피해 자리 다시) ·
// tblMarksOn/tblMarksToggle(3단계 카드) · tblAgentView·xlColumn(표 보기 격자) · tblAgentLeave·xlColumnClosed(headsColClose) · tablesShow(탭 열 때)·tablesReset(문서 열고 닫을 때).
// 서버 짝은 app/tables_api.py(끝점)·app/table_agent.py(저장·묶음 글)·heading_tables.table_notes(작성요령). index.html 이 app.js 다음에 읽는다.

// ---------------------------------------------------------------- 표 도구(spec_헤딩_추출 ② §10) — 표 식별 표지 · 엑셀식 보기(A1 격자 · 수식 엔진 · 문서에 반영) · 표 지침(표 에이전트 입력)
// 표지(.tbl-mark)는 문서 표(table.tbl[data-tbl] 첫 조각 · 엑셀식 보기 .xl-wrap)의 위끝 높이로 **쪽 안 왼쪽 여백**(종이 왼끝 ~ 표 왼쪽 — 「TN Lk」 .tpl-mark·손잡이와 같은 여백)에 .sheet 절대 위치.
// 가로 자리·폭은 style.css 가 --mgl(그 쪽 왼쪽 여백 폭, 화면 px — app.js sheetMarginPx)로 잡는다: 항목은 늘 다 보이고, 여백 폭에 한 줄로 안 들어가면 여백 안에서 다음 줄로 접힌다
// (보통 「⊞ ✎ 표 id」 / 「소속 Σ」 2줄 — 2026-11-10 사용자 「마우스 대야 보이게 하지 말고 그냥 보이게」: 옛 「들어가는 항목까지만 + 올리면 펼침」 없앰).
// .tpl-mark 와 같이 zoom 1/z 로 화면 크기를 고정하고, 「TN Lk」 표(표 첫 행 칸의 라벨 등)·손잡이·먼저 놓인 표지와 세로로 겹치면(표지 높이 = 줄 수만큼) 그 아래로 비켜 선다(tblMarksPlace).
// 이력: 표 위 오른쪽에 겹쳐 그리던 것 → 2026-11-10 「문서 여백에 둘 수 있잖아」 로 쪽 바깥 여백 열 → 같은 날 「문서 페이지 여백에」 로 쪽 안 여백(스크롤 상자 여백 .gutter 없앰, 2쪽 보기도 쪽마다 제 왼쪽 여백).
// 엑셀식 보기는 첫 조각을 .xl-wrap 으로 바꾸고 나머지 조각(.cont)을 숨긴다; 쪽을 다시 나누면(paginate) 조각이 새로 생기므로 tblMarksDraw → xlApply 가 heads.xl.open 의 표를 다시 격자로.
// 격자의 값은 지금 문서 칸 글(state.texts)이고, 수식·고친 값은 「문서에 반영」 을 눌러야 PATCH /blocks 로 문서에 쓰인다(보통 글 고침과 같은 길 — 되돌리기·실행 취소·기록 그대로).
const TBL_MARKS_KEY = "nfm.tblMarks";
const XL_ICON = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="M1.5 2h13v12h-13zM3 3.5v2.2h4v-2.2zm5.2 0v2.2H13V3.5zM3 6.9v2.2h4V6.9zm5.2 0v2.2H13V6.9zM3 10.3v2.2h4v-2.2zm5.2 0v2.2H13v-2.2z"/></svg>';
const XL_ROLE = { colhead: "열헤더", rowhead: "행헤더", corner: "귀퉁이", field: "필드", title: "제목", note: "안내", spacer: "간격" };
const XL_UNIT = /\s*(?:%|％|원|천원|백만원|억원|명|건|개|회|년|개월|시간|점|㎡|kg|t)\s*$/i;
function xlStripCode(t) { // 값 뒤 코드 「(A)」「(A/E)」「(M=K+L)」「(L/(N+B))」 를 뗀다 — 끝의 괄호 묶음을 짝 맞춰 찾아(안쪽 괄호 포함) 코드·수·연산 글자뿐이면. heading_calc._strip_codes 와 같은 뜻
  const s = String(t).trimEnd();
  if (!s.endsWith(")") && !s.endsWith("）")) return t;
  let depth = 0, i = s.length - 1;
  for (; i >= 0; i -= 1) {
    if (s[i] === ")" || s[i] === "）") depth += 1;
    else if (s[i] === "(" || s[i] === "（") { depth -= 1; if (!depth) break; }
  }
  if (i < 0) return t;
  const inner = s.slice(i + 1, -1);
  return /[A-Z]/.test(inner) && /^[A-Z0-9+\-*/×÷＋－＝=().（）%\s]+$/.test(inner) ? s.slice(0, i) : t; // 「(1,234)」 괄호 음수는 영문 대문자가 없어 그대로
}
const XL_REF = /^\$?([A-Z]{1,3})\$?([1-9]\d{0,3})$/i;
const XL_PH = /^0{1,3}(?:,0{3})+$|^0{2,}$|^[0○◯]{2,}$/; // 숫자 자리표시 — heading_calc._PH 와 같다(「000,000」 도)
function xlIsPh(s) { // 칸 글이 숫자 자리표시인가(뒤 코드·단위·% 를 뗀 뒤) — 수식 엔진은 빈 값으로 본다(0 도 글도 아님)
  const t = xlStripCode(oneLine(String(s ?? "")).trim()).trim().replace(/[%％]\s*$/, "").replace(XL_UNIT, "").trim();
  return !!t && XL_PH.test(t);
}
const xlRefOf = (row, col) => `${colLetter(col)}${row + 1}`;
function tblMarksOn() { return quickGet(TBL_MARKS_KEY) !== "off"; } // 문서마다 따로 기억(app.js quickKey — 원본 · 목적 문서: spec_작업 ② §12 「도구는 문서마다」)
function tblMarksToggle() {
  quickSet(TBL_MARKS_KEY, tblMarksOn() ? "off" : "on");
  tblMarksDraw();
  if (heads.view) headsCard3(heads.view, !!(heads.view.job && heads.view.job.status === "running")); // 단추 글(표시/끄기) 바꿈
}
const tblAgentUrl = (tid) => `/api/docs/${encodeURIComponent(state.id)}/headings/tables/${encodeURIComponent(tid)}/agent`;

async function xlStore(force = false) { // 저장된 표 지침·사용자 수식(작업마다 — spec ② §10) · 문서(epoch)마다 한 번 읽는다
  const key = `${state.id}|${state.epoch}`;
  if (!force && heads.xl.store && heads.xl.storeKey === key) return heads.xl.store;
  let r = null;
  try { r = await api(`/api/docs/${encodeURIComponent(state.id)}/headings/tables/agents`); } catch { r = null; }
  if (key !== `${state.id}|${state.epoch}`) return null;
  heads.xl.store = r || heads.xl.store || { common: { instructions: "", version: 0 }, tables: {} };
  heads.xl.storeKey = key;
  return heads.xl.store;
}

async function xlFull() { // 3단계 전체(칸 역할·§9 수식) — 「표 보기」(heads.tbl) 와 같은 캐시
  const s3 = heads.view && heads.view.stage3;
  if (!s3 || !s3.meta) return null;
  const key = `${s3.meta.run}|${s3.meta.at}`;
  if (heads.tbl.data && heads.tbl.key === key) return heads.tbl.data;
  const epoch = state.epoch;
  try {
    const data = await api(`/api/docs/${state.id}/headings/tables`);
    if (epoch !== state.epoch) return null;
    heads.tbl = { key, data, id: heads.tbl.id };
    return data;
  } catch { return null; }
}

// ---- 표 식별 표지 --------------------------------------------------------------------------------------------
const TBL_MARK_H = 17; // 한 줄짜리 표지·「TN Lk」 표·손잡이의 높이(화면 px — app.js TPL_MARK_H 와 같아야 같은 여백에서 서로 비켜 선다). 여러 줄 표지의 높이는 tblMarksPlace 가 잰다(data-h)
function tblMarksDraw() {
  // 읽기 단계(모든 표의 자리) → 쓰기 단계(표지 붙이기) — 표마다 재고 붙이기를 번갈아 하면 표 수만큼 강제 배치가 되어 큰 문서에서 10~27 s 멈춘다
  // (2026-11-10 실측 — 연구개발계획서 양식 표 145개: 번갈아 13~27 s → 나눠서 0.1 s 이하, spec_owpml_편집 ③). 표지가 꺼져 있어도 xlApply·xlColumnSync·tablesDraw 는 돈다.
  for (const e of document.querySelectorAll(".tbl-mark")) e.remove();
  xlApply(); // 열어 둔 엑셀식 보기를 되살린다(쪽을 다시 나누면 표 조각이 새로 생김)
  tblRolesApply(); // 문서에서 표 구조 보기 — 새로 생긴 표 조각의 칸에 역할 색을 다시(꺼져 있으면 걷기만)
  const sc = $("scroller");
  const shown = typeof gutterSync === "function" ? gutterSync() : !sc.hidden; // 문서가 보이고 쪽 보기가 켜져 있는가(쪽 여백이 있어야 그린다)
  if (state.id && shown && tblMarksOn()) {
    const s3 = heads.view && heads.view.stage3;
    const byId = new Map(((s3 && s3.tables) || []).map((t) => [t.id, t]));
    const store = (heads.xl.store && heads.xl.store.tables) || {};
    const jobs = [];
    for (const sheet of document.querySelectorAll("#doc .sheet")) { // 읽기 단계 — DOM 을 바꾸지 않는다
      const sr = sheet.getBoundingClientRect();
      const z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1;
      const mgl = sheetMarginPx(sheet, z); // 그 쪽 왼쪽 여백 폭(화면 px) — style.css 가 표지를 그 안에 둔다
      for (const t of sheet.querySelectorAll("table.tbl[data-tbl]:not(.cont), .xl-wrap[data-tbl]")) {
        if (t.hidden) continue;
        jobs.push({ sheet, tid: t.dataset.tbl, z, mgl, top: Math.round(t.getBoundingClientRect().top - sr.top) });
      }
    }
    for (const j of jobs) { // 쓰기 단계
      const m = tblMark(j.tid, byId.get(j.tid), store[j.tid], heads.xl.open.has(j.tid), !!s3);
      m.style.zoom = String(1 / j.z);
      m.style.setProperty("--mgl", `${j.mgl}px`);
      m.dataset.top = String(j.top); // 제자리(표 위끝) — tblMarksPlace 가 겹침을 피해 내려 놓는다
      m.style.top = `${j.top}px`;
      j.sheet.append(m);
    }
    tblMarksPlace();
  }
  xlColumnSync();
  if (typeof tablesDraw === "function") tablesDraw(); // 「표」 탭 목록(소속·계산식·지침)도 같은 자료를 따른다
  if (typeof tblMenuSync === "function") tblMenuSync(); // 표 메뉴(table_menu.js — spec ② §16): 쪽을 다시 나누면 표 조각이 새로 생긴다 — 고른 표의 모서리 손잡이를 다시 놓는다
  if (typeof docQuickSync === "function") docQuickSync(); // 이름 줄의 「표 라벨 표시」 아이콘(doc_quick.js #nameTblMarks) — 켜짐·표가 있는 문서인지가 여기서 바뀐다(2026-11-16)
}
function tblMarksPlace() { // 표지 자리 — 표 위끝(data-top)에 두되, 같은 쪽 여백의 「TN Lk」 표(.tpl-mark)·손잡이(.ol-grip)나 먼저 놓인 표지와 세로로 겹치면 가장 가까운 빈 자리(위·아래)로 옮긴다
  // 표지는 항목이 다음 줄로 접혀 높이가 줄 수만큼이다(style.css) — 처음 한 번만 모두 재서 data-h 에 두고(읽기 단계: 강제 배치 1회), 그 뒤로는 style.top·data-h 만 읽는다(쓰기 단계).
  // 아래로만 내리면 칸 줄마다 「TN Lk」 가 붙은 표에서 2줄 표지(32px)가 표 끝까지 밀린다(실측 400px+) — 빈 자리 후보 = 막는 것 바로 아래·바로 위, 제자리에서 가까운 순(같으면 아래).
  // 가까운 자리(표지 높이 + 2px 안)가 없으면: ① 바로 앞 표지(칸 안 표의 바깥 표)와 위아래 한 묶음으로 다시 놓아 보고, ② 그래도 없으면 한 줄(.wide — 여백에서 표 위로 펼침)로 줄여
  // 한 줄 자리를 찾고, ③ 그것도 멀면(작은 배율 — 「TN Lk」 가 여백을 다 채움) 여백을 떠나 표 왼쪽 위 모서리 위(.onto)에 제 높이로 둔다 — 어느 경우든 항목은 다 보인다
  const fresh = [...document.querySelectorAll("#doc .sheet > .tbl-mark:not([data-h])")];
  const hs = fresh.map((m) => m.getBoundingClientRect().height); // 화면 px(표지는 zoom 1/z — top 과 같은 단위)
  fresh.forEach((m, i) => { m.dataset.h = String(Math.max(TBL_MARK_H, Math.round(hs[i]))); }); // 안 보이는 쪽(0)은 한 줄로
  const near = (h, y0, obst) => { // 높이 h 가 obst 와 안 겹치는, y0 에서 가장 가까운 자리
    const want = Math.max(0, y0), free = (y) => y >= 0 && !obst.some((t) => y < t.y + t.h && t.y < y + h);
    if (free(want)) return want;
    const hit = obst.flatMap((t) => [t.y + t.h, t.y - h]).sort((a, b) => Math.abs(a - want) - Math.abs(b - want) || b - a).find(free);
    return hit === undefined ? want : hit; // 맨 아래 것의 바로 아래는 늘 비어 있다
  };
  for (const sheet of document.querySelectorAll("#doc .sheet")) {
    const ms = [...sheet.querySelectorAll(":scope > .tbl-mark")].sort((a, b) => +a.dataset.top - +b.dataset.top);
    if (!ms.length) continue;
    const taken = [...sheet.querySelectorAll(":scope > .tpl-mark, :scope > .ol-grip")].map((e) => ({ y: parseFloat(e.style.top) || 0, h: TBL_MARK_H }));
    const spread = []; // 표 위로 펼친 한 줄 표지(.wide)들의 자리 — 여백 밖에서는 서로만 피하면 된다
    let prev = null; // 바로 앞 표지의 자리
    for (const m of ms) {
      m.classList.remove("wide", "onto");
      let h = +m.dataset.h || TBL_MARK_H, wide = false, onto = false;
      const y0 = +m.dataset.top || 0;
      let top = near(h, y0, taken);
      if (Math.abs(top - y0) > h + 2) {
        const rest = prev && !prev.wide ? taken.filter((t) => t !== prev) : null;
        const bt = rest ? near(prev.h + h, y0 - prev.h, rest) : 0; // 묶음(앞 표지 + 이 표지) 위끝 — 이 표지가 제자리에 오는 곳부터 찾는다
        if (rest && Math.abs(bt - prev.y0) <= prev.h + 2 && Math.abs(bt + prev.h - y0) <= h + 2) {
          prev.y = bt;
          prev.m.style.top = `${Math.round(bt)}px`;
          top = bt + prev.h;
        } else {
          wide = true;
          h = TBL_MARK_H;
          top = near(h, y0, taken.concat(spread));
          if (Math.abs(top - y0) > h + 2) { onto = true; top = near(h, y0, spread); }
          m.classList.add("wide");
          m.classList.toggle("onto", onto);
          spread.push({ y: top, h });
        }
      }
      prev = { y: top, h, y0, m, wide };
      if (!onto) taken.push(prev);
      m.style.top = `${Math.round(top)}px`;
    }
  }
}
window.addEventListener("resize", () => { if (state.id && document.querySelector(".tbl-mark, .xl-wrap")) tblMarksDraw(); });

// ---- 문서에서 표 구조 보기(spec_헤딩_추출 ② §10) — 문서 표 칸에 3단계 칸 역할 색 · 서브 테이블 경계 · 도움말 ---------------------------------
// 켜면 #doc.tbl-roles + 칸(td[data-cell])마다 data-trole(역할) · data-tsb(서브 테이블이 다시 시작하는 위 t · 왼쪽 l) · title. 색은 style.css — 칸의 background-image 로만 그려
// 한글 칸 음영(인라인 background-color)·고른 칸 표시(td.sel 의 box-shadow)·구분 기준 표시(.para 바탕)와 겹쳐도 다 보인다. 문서 글·저장에는 영향 없음(화면 표시만).
// 자료 = 3단계 전체 결과(xlFull — 「표 보기」 와 같은 캐시). 3단계 뒤 문서가 바뀌어도 **칸 id 가 같은 칸은 그 판정 그대로** 칠한다(줄이 지워져 당겨진 칸 · 값이 들어온 칸 — 2026-11-23
// 「LLM 판정이 되면 그게 유지되어야지」: spec_테이블매니저 ② §2 「판정 이어 쓰기」 · 전에는 격자 자리(행·열)까지 같아야 칠했다). 판정 뒤에 생긴 칸은 안 칠한다.
// 켜고 끄기 = 단추 하나(모든 표 — 이 브라우저에 기억, 기본 끔). 표지(.tbl-mark)에는 단추를 두지 않는다(여백 폭에 첫 줄 「⊞ ✎ 표 id」 가 꽉 참 — style.css 주석).
const TBL_ROLES_KEY = "nfm.tblRoles";
const tblRoles = { on: (() => { try { return localStorage.getItem(TBL_ROLES_KEY) === "on"; } catch { return false; } })(), key: null, map: null, wait: null, failed: null };
function tblRolesOn() { return tblRoles.on; }
function tblRolesToggle() {
  tblRoles.on = !tblRoles.on;
  tblRoles.failed = null; // 다시 켜면 다시 읽어 본다
  try { localStorage.setItem(TBL_ROLES_KEY, tblRoles.on ? "on" : "off"); } catch { /* 기억만 안 함 */ }
  tblRolesApply();
  tblRolesBtnSync();
}
function tblRolesBtn(brief = false) { // 켜고 끄는 단추 — 2열 「표 구조」 도구 줄(brief: 범례 옆)·3단계 카드·「표」 탭
  const b = hBtn("", () => tblRolesToggle(), { cls: "btn sm tbl-roles-btn" });
  if (brief) b.dataset.brief = "1";
  tblRolesBtnSet(b);
  return b;
}
function tblRolesBtnSet(b) {
  const s3 = heads.view && heads.view.stage3, on = tblRolesOn();
  if (!b.dataset.keep) b.textContent = b.dataset.brief ? "문서에 표시" : on ? "문서 표 구조 끄기" : "문서에 표 구조 표시"; // data-keep = 제 글·아이콘을 가진 단추(도구 줄) — 눌림·꺼짐·도움말만 맞춘다
  b.classList.toggle("on", on);
  b.setAttribute("aria-pressed", String(on));
  const unread = !heads.view && state.format !== "docx"; // 헤딩 요약을 아직 안 읽음(다시 연 작업 — 이때 보이는 단추는 도구 줄 것뿐): 누를 수 있게 두고, 누르면 읽는다(app.js tbRolesClick)
  b.disabled = !on && !unread && (!s3 || state.format === "docx"); // 켜져 있으면 늘 끌 수 있게
  b.title = unread ? "문서의 표 칸에 칸 역할 색(열헤더·행헤더·귀퉁이·제목·안내)을 겹쳐 보입니다 — 누르면 표 구조(3단계) 결과를 읽어 옵니다"
    : !s3 ? "표 구조(3단계)를 만들면 문서의 표 칸에 칸 역할 색을 보일 수 있습니다"
    : "문서의 표 칸에 칸 역할 색을 겹쳐 보입니다 — 열헤더 파랑 · 행헤더 초록 · 귀퉁이 보라 · 제목 주황 · 안내 회색 · 간격 빗금 · 필드는 그대로\n굵은 선 = 서브 테이블 경계 · 칸에 마우스를 올리면 역할과 헤더 경로"
      + (s3.stale ? "\n문서가 바뀜 — 판정 때 있던 칸은 그 역할 그대로 칠합니다(그 뒤에 생긴 칸은 칠하지 않습니다)" : "") + "\n화면 표시만 — 문서 글·저장에는 영향 없음(이 브라우저에 기억)";
}
function tblRolesBtnSync() { for (const b of document.querySelectorAll(".tbl-roles-btn")) tblRolesBtnSet(b); }
function tblRolesUnset(td) { td.removeAttribute("data-trole"); td.removeAttribute("data-tsb"); td.removeAttribute("title"); }
function tblRolesIndex(full, key) { // 표 id → Map(칸 id → {row, col, role, sb, title}) — 3단계 결과(실행)마다 한 번
  if (tblRoles.key === key && tblRoles.map) return tblRoles.map;
  const map = new Map();
  for (const t of full.tables || []) {
    const byId = new Map((t.cells || []).map((c) => [c.id, c]));
    const nameOf = (cid) => { const c = byId.get(cid); return c ? short(c.text, 30).replace("(빈 문단)", "(빈 칸)") : cid; };
    const subs = t.subtables || [];
    const tops = subs.filter((s) => s.rows[0] > 0), lefts = subs.filter((s) => s.cols[0] > 0); // 격자(headsTableGrid)의 굵은 선과 같은 자리
    const cells = new Map();
    for (const c of t.cells || []) {
      const sb = [tops.some((s) => s.rows[0] === c.row && s.cols[0] <= c.col && c.col < s.cols[1]) ? "t" : "", lefts.some((s) => s.cols[0] === c.col && s.rows[0] <= c.row && c.row < s.rows[1]) ? "l" : ""]
        .filter(Boolean).join(" ");
      const lines = [`${XL_ROLE[c.role] || c.role}${c.sub && subs.length > 1 ? ` · 서브 테이블 ${c.sub}` : ""}${c.basis && c.basis.length ? ` · 구분 헤더 ${basisNames(c.basis) || c.basis.join("·")}` : ""}`
        + `${c.changed ? " · LLM 이 초안을 바꿈" : ""}`];
      if (c.role === "field") {
        if ((c.rowPath || []).length) lines.push(`행헤더: ${c.rowPath.map(nameOf).join(" › ")}`);
        if ((c.colPath || []).length) lines.push(`열헤더: ${c.colPath.map(nameOf).join(" › ")}`);
        if (c.div && Object.keys(c.div).length) lines.push(`구분 값: ${Object.entries(c.div).map(([b, v]) => `${basisNames([b]) || b} ${v}`).join(" · ")}`);
      } else if (c.parent) lines.push(`위 헤더: ${nameOf(c.parent)}`);
      cells.set(c.id, { row: String(c.row), col: String(c.col), role: c.role, sb, title: lines.join("\n") });
    }
    map.set(t.id, cells);
  }
  tblRoles.key = key;
  tblRoles.map = map;
  return map;
}
function tblRolesApply() { // tblMarksDraw(쪽을 다시 나눔 · 3단계 결과가 바뀜 · 문서를 엶)와 켜고 끌 때 — 칸마다 바뀐 것만 쓴다(쓰기만, 배치를 읽지 않음)
  const doc = $("doc");
  if (!doc) return;
  const s3 = heads.view && heads.view.stage3;
  const on = tblRoles.on && !!state.id && state.format !== "docx" && !!(s3 && s3.meta);
  doc.classList.toggle("tbl-roles", on);
  tblRolesBtnSync(); // 3단계가 생기거나 없어지면 단추의 꺼짐·도움말도
  if (!on) { for (const td of doc.querySelectorAll("td[data-trole]")) tblRolesUnset(td); return; }
  const key = `${state.id}|${s3.meta.run}|${s3.meta.at}`;
  const full = heads.tbl.data && heads.tbl.key === `${s3.meta.run}|${s3.meta.at}` ? heads.tbl.data : null;
  if (!full) { // 3단계 전체 결과를 아직 안 읽음 — 읽고 나서 한 번 더(읽는 중·실패한 실행은 다시 안 부른다)
    if (tblRoles.wait !== key && tblRoles.failed !== key) {
      tblRoles.wait = key;
      xlFull().then((d) => {
        if (tblRoles.wait === key) tblRoles.wait = null;
        if (d) tblRolesApply();
        else if (tblRoles.on) { tblRoles.failed = key; toast("표 구조를 읽지 못해 문서에 표시하지 못했습니다 — 단추를 껐다 켜면 다시 읽습니다"); }
      });
    }
    return;
  }
  const map = tblRolesIndex(full, key);
  for (const t of doc.querySelectorAll("table.tbl[data-tbl]")) { // 쪽 조각(.cont)·칸 안 표도 — t.rows 는 그 표의 행만(안쪽 표의 행은 안쪽 표에서)
    const cells = map.get(t.dataset.tbl);
    for (const tr of t.rows) {
      for (const td of tr.cells) {
        const c = cells && cells.get(td.dataset.cell);
        if (c) { // 칸 id 가 같으면 그 판정 그대로 — 줄이 지워지거나 늘어 자리가 옮겨져도 칸은 제 역할을 지닌다(2026-11-23 「LLM 판정이 되면 그게 유지되어야지」 — 전에는 자리까지 같아야 칠했다)
          if (td.dataset.trole !== c.role) td.dataset.trole = c.role;
          if ((td.dataset.tsb || "") !== c.sb) { if (c.sb) td.dataset.tsb = c.sb; else td.removeAttribute("data-tsb"); }
          if (td.title !== c.title) td.title = c.title;
        } else if (td.dataset.trole !== undefined) tblRolesUnset(td);
      }
    }
  }
}

// ---- 엑셀식 보기 — 2열(kind "xl") : 문서는 그대로 두고 옆 열에 격자(사용자 2026-11-10 「열을 하나 만들어서 거기에 엑셀표」) ----------------------------------------
const xlStageKey = () => { const s3 = heads.view && heads.view.stage3; return s3 && s3.meta ? `${s3.meta.run}|${s3.meta.at}` : "none"; };
const xlRangeKey = (rg) => (rg ? `${rg.r0},${rg.c0},${rg.r1},${rg.c1}` : "all");
const xlRangeName = (rg) => (rg ? `${xlRefOf(rg.r0, rg.c0)}:${xlRefOf(rg.r1, rg.c1)}` : "");
const xlColKey = (tid, rg = null) => { // 2열 격자를 다시 만들 조건 — 3단계 결과 · 구조 편집 차례(행·열 넣기/지우기·나누기·합치기 뒤 state.structRev) · 표 블록 크기 · 범위
  const b = xlBlock(tid);
  return `${xlStageKey()}|${state.structRev}|${b ? `${b.nRows}x${b.nCols}x${(b.cells || []).length}` : "-"}|${xlRangeKey(rg)}`;
};
function xlClampRange(rg, b) { // 끌어 고른 범위(격자 좌표) → 표 안으로 · 표 전체면 null
  if (!rg || !b) return null;
  const R = (b.nRows || 1) - 1, C = (b.nCols || 1) - 1;
  const out = { r0: Math.max(0, Math.min(rg.r0, R)), c0: Math.max(0, Math.min(rg.c0, C)), r1: Math.max(0, Math.min(rg.r1, R)), c1: Math.max(0, Math.min(rg.c1, C)) };
  if (out.r0 > out.r1 || out.c0 > out.c1) return null;
  return out.r0 === 0 && out.c0 === 0 && out.r1 === R && out.c1 === C ? null : out;
}
function xlSelRange(tid) { // 문서 표에서 끌어 고른 칸 묶음(table_edit.js tsel)이 이 표의 2칸 이상이면 그 범위
  if (typeof tselActive !== "function" || !tselActive() || tsel.tbl !== tid || tsel.cells.length < 2 || !tsel.rect) return null;
  return { ...tsel.rect };
}
function xlCellItems(tbl) { // 표 칸 오른쪽 단추 메뉴(table_edit.js tselContextMenu) — 고른 칸만 엑셀식 보기
  const rg = xlSelRange(tbl);
  return [[rg ? `고른 칸 엑셀식 보기(${xlRangeName(rg)}) — 수식 판정` : "이 표 엑셀식 보기 — 수식 판정", "", () => xlColumn(tbl, rg)], null];
}

// 수식 판정(spec ② §14) — 지금 문서의 그 표(또는 범위)만 서버가 스크립트로: 칸 역할 · 합계/비율/코드 수식 · 숫자 칸. 문서·구조 편집 차례마다 캐시(heads.xl.judge)
const xlJudgeKey = (tid, rg) => `${state.id}|${state.epoch}|${state.structRev}|${tid}|${xlRangeKey(rg)}`;
async function xlJudge(tid, rg, force = false) {
  if (state.format === "docx") return null;
  heads.xl.judge = heads.xl.judge || new Map();
  const key = xlJudgeKey(tid, rg);
  if (!force && heads.xl.judge.has(key)) return heads.xl.judge.get(key);
  const epoch = state.epoch;
  let r = null;
  try { r = await api(`/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/excel`, { method: "POST", headers: H_JSON, body: JSON.stringify(rg ? { range: rg } : {}) }); }
  catch (e) { if (epoch === state.epoch) toast(`수식 판정을 못 했습니다: ${e.message}`, true); return null; }
  if (epoch !== state.epoch) return null;
  if (heads.xl.judge.size > 40) heads.xl.judge.clear();
  heads.xl.judge.set(key, r);
  return r;
}

async function xlColumn(tid, range = null) {
  const b0 = xlBlock(tid);
  if (!state.id || !b0) { toast("그 표가 지금 문서에 없습니다"); return; }
  const rg = xlClampRange(range, b0);
  const { tools, body } = headsDlg("xl", `엑셀식 보기 · ${tid}${rg ? ` ${xlRangeName(rg)}` : ""}`, "A1 격자 · 수식 자리 판정 · 계산 — 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  const seq = heads.seq, epoch = state.epoch;
  hFoot("수식 자리를 판정하는 중…", false);
  heads.xl.col = { tid, key: xlColKey(tid, rg), range: rg, busy: true };
  await xlStore();
  await xlFull();
  const judge = await xlJudge(tid, rg);
  if (seq !== heads.seq || epoch !== state.epoch) return;
  const wrap = xlBuild(tid, [], { range: rg, judge });
  if (!wrap) { hFoot("표 블록을 찾지 못했습니다"); return; }
  wrap.classList.add("col");
  heads.xl.col = { tid, key: xlColKey(tid, rg), range: rg };
  body.textContent = "";
  body.append(wrap);
  const b = xlBlock(tid), s3 = heads.view && heads.view.stage3, t = s3 && (s3.tables || []).find((x) => x.id === tid);
  tools.textContent = "";
  if (t && t.owner && !t.owner.root && hasBlock(t.owner.para)) tools.append(el("span", "muted", "소속"), hBtn(ownerLabel(t.owner), () => headsGo(t.owner.para), { title: "문서의 그 헤딩으로" }));
  if (t && t.host && hasBlock(t.host)) tools.append(hBtn("표 자리로", () => headsGo(t.host), { title: "문서에서 이 표를 품은 문단으로" }));
  if (rg) tools.append(el("span", "hb", `범위 ${xlRangeName(rg)}`), hBtn("표 전체", () => xlColumn(tid), { title: "범위를 풀고 표 전체를 격자로" }));
  tools.append(el("span", "spacer"), el("span", "muted", rg ? `${rg.r1 - rg.r0 + 1}×${rg.c1 - rg.c0 + 1} / ${b.nRows || "?"}×${b.nCols || "?"}` : `${b.nRows || "?"}×${b.nCols || "?"}`));
  const foot = $("headsDlgFoot");
  foot.textContent = "";
  foot.append(el("span", "muted", `표 ${tid}${rg ? ` 범위 ${xlRangeName(rg)}` : ""} · 수식은 이 작업에 저장 · 문서는 「문서에 반영」 을 눌러야 바뀜 · 문서에서 칸을 끌어 고른 뒤 ⊞ 를 누르면 그 범위만`));
  wrap.focus({ preventScroll: true });
  tblMarksDraw(); // 표지의 ⊞ 눌림
}
function xlColumnClosed() { // headsColClose 에서 — 2열 격자가 닫히면 표지의 ⊞ 를 푼다
  if (!heads.xl.col) return;
  heads.xl.col = null;
  if (state.id && document.querySelector(".tbl-mark")) tblMarksDraw();
}
function xlColumnSync() { // 3단계 결과(표 구조 만들기 뒤)·표 구조 편집(행·열 넣기/지우기 뒤 applyTops → paginate)이 바뀌었으면 열린 2열 격자를 다시 만든다
  const c = heads.xl.col;
  if (!c) return;
  if (heads.dlg !== "xl") { heads.xl.col = null; return; }
  if (!xlBlock(c.tid)) { headsColClose(true); return; } // 표가 지워짐(마지막 행/열 지우기)
  if (c.key !== xlColKey(c.tid, c.range) && !c.busy) { c.busy = true; xlColumn(c.tid, c.range); } // 범위는 구조 편집 뒤 표 안으로 줄여 다시
}

function tblMark(tid, t, rec, inplace, hasStage3) { // 표지 하나 — ⊞ 엑셀식 보기(2열) · ✎ 표 지침 · 표 id · 소속(헤딩 「TN Lk」·구분 라벨 — 누르면 문서의 그 문단) · Σ수식 수
  // 쪽 안 여백(20mm 면 75~95px)에 들어가야 하므로 글은 짧게(소속은 「TN Lk」 만, 수식은 「Σn」) — 헤딩 글·경로·일치/불일치 수는 title(도움말)에.
  // 여백 폭에 한 줄로 못 들어간 항목(보통 소속부터)은 다음 줄로 접혀 늘 보인다(style.css .tbl-mark) — 순서 = 줄 차례(⊞ ✎ id 가 첫 줄)
  const inCol = !!(heads.xl.col && heads.xl.col.tid === tid && heads.dlg === "xl"), open = inplace || inCol;
  const m = el("div", "tbl-mark" + (open ? " open" : ""));
  m.dataset.for = tid;
  const xl = el("button", "tm-btn xl");
  xl.type = "button";
  xl.innerHTML = XL_ICON;
  xl.setAttribute("aria-pressed", String(open));
  xl.setAttribute("aria-label", "엑셀식 보기");
  xl.title = (inplace ? "문서 보기로(원래 표)" : inCol ? "엑셀식 보기 열 닫기" : "엑셀식 보기 — 문서 옆 열에 A1 격자(수식 자리 판정 · 계산 · 숫자 칸 · 정렬 · 엑셀로 받기)")
    + "\n표 칸을 끌어 고른 뒤 누르면 그 범위만";
  xl.onclick = (e) => {
    e.stopPropagation();
    const rg = xlSelRange(tid); // 끌어 고른 칸이 있으면 그 범위만(열려 있어도 범위로 다시)
    if (rg) xlColumn(tid, rg);
    else if (inplace) xlClose(tid); else if (inCol) headsColClose(); else xlColumn(tid);
  };
  const g = el("button", "tm-btn guide" + (rec && rec.instructions ? " has" : ""), "✎");
  g.type = "button";
  g.setAttribute("aria-label", "표 지침");
  g.title = "표 지침 — 작성요령 · 사용자 지침(표 에이전트 입력)" + (rec && rec.instructions ? " · 지침 있음" : "") + (rec && Object.keys(rec.formulas || {}).length ? ` · 사용자 수식 ${Object.keys(rec.formulas).length}` : "");
  g.onclick = (e) => { e.stopPropagation(); tblAgentView(tid); };
  m.append(xl, g, el("span", "tm-id", tid));
  if (state.format === "docx") return m; // 3단계는 hwpx 만 — 소속 없음
  const tmp = typeof tempTableTag === "function" ? tempTableTag(tid) : null; // TEMP 표(작성 요령 표·안내 상자 — heading_temp.js, spec ② §15): 표 구조에서 빠지므로 소속·Σ 대신 「TEMP」
  if (tmp) { m.classList.add("temp"); m.append(tmp); return m; } // 소속 자리에(⊞ ✎ 표 id 다음 — 여백이 좁으면 둘째 줄. 옛 「가려지지 않게 맨 앞」 은 항목이 늘 다 보이므로 필요 없음)
  if (t) {
    const o = t.owner;
    if (o && !o.root) {
      const isLbl = o.role === "label";
      const b = el("button", "tm-owner" + (isLbl ? " lbl" : ""), o.tplNo ? `T${o.tplNo} L${o.level}` : short(o.text || "(제목 없음)", 8));
      b.type = "button";
      b.title = [`소속 ${oneLine(o.text || "(제목 없음)")}${o.tplNo ? ` · 템플릿 T${o.tplNo} ${o.level}번째 줄` : ""}${isLbl ? " · 구분 라벨" : ""}`,
        (o.path || []).length ? `경로 ${o.path.join(" › ")}` : "", o.division && !isLbl ? `구분 라벨 ${oneLine(o.division.text)}` : "",
        (t.basis || []).length ? `구분 ${basisNames(t.basis)}` : "", t.unit ? `단위 ${t.unit}` : "",
        `출처 ${o.source === "stage2" ? "2단계 그래프" : "1단계 어림(2단계 그래프 없음)"}`, hasBlock(o.para) ? "누르면 문서의 그 헤딩으로" : ""].filter(Boolean).join("\n");
      b.onclick = (e) => { e.stopPropagation(); headsGo(o.para); };
      const dvk = dvKeyOf(dvOfDivision(o.division)); // 구분 라벨의 색 = 그 구분의 「구분 기준 자리」 색(app.js dvKeyOf — 단계 파랑 · 차년도 초록 · 기관 주황)
      if (isLbl && dvk) b.dataset.dv = dvk;
      m.append(b);
      if (o.division && !isLbl) {
        const d = el("span", "tm-div", (o.division.basis || []).length ? `[${basisNames(o.division.basis)}]` : short(o.division.text, 12));
        d.title = `구분 라벨 ${oneLine(o.division.text)}`;
        if (dvk) d.dataset.dv = dvk;
        m.append(d);
      }
    } else {
      const s = el("span", "tm-owner muted", o && o.root ? "뿌리" : "소속 없음");
      s.title = o && o.root ? "위에 헤딩이 없는 표(문서 뿌리)" : "소속 헤딩·라벨을 찾지 못함";
      m.append(s);
    }
    if (t.calc && t.calc.is) {
      const k = el("span", "tm-calc" + (t.calc.mismatch ? " bad" : ""), `Σ${nf(t.calc.formulas)}${t.calc.mismatch ? `·✗${nf(t.calc.mismatch)}` : ""}`);
      k.title = `계산식 표 — 수식 ${nf(t.calc.formulas)} · 일치 ${nf(t.calc.ok)} · 불일치 ${nf(t.calc.mismatch)} · 미기입 ${nf(t.calc.missing)} · 미검증 ${nf((t.calc.blank || 0) + (t.calc.incomplete || 0))}`;
      m.append(k);
      if (t.calc.mismatch) m.classList.add("bad"); // 불일치는 Σ 글과 함께 표지 테두리로도 보인다
    }
  } else if (hasStage3) {
    // 표 구조(3단계 결과)에 없는 표 — 옛 글 「구조에 없음」 은 뜻을 알기 어려웠다(2026-11-10 사용자 「무슨 의미인지 모르겠다」). 까닭은 둘뿐이라 그대로 적는다:
    // 칸이 하나인 표(글상자 — 표 구조를 만들지 않음) = 「1칸 표」 · 표 구조를 만든 뒤 문서에 생긴 표 = 「새 표」(뼈대 유지 — spec ② §17).
    // 「새 표」 를 눌러도 표 구조를 저절로 다시 만들지 않는다(LLM 결과가 스크립트 결과로 덮이던 것) — 뼈대 밖 목록을 연다(heading_drift.js)
    const blk = xlBlock(tid), one = !!blk && (blk.cells || []).length === 1;
    const b = el(one ? "span" : "button", `tm-owner ${one ? "muted" : "tm-new"}`, one ? "1칸 표" : "새 표");
    if (one) b.title = "칸이 하나인 표(글상자) — 표 구조(헤더·필드·소속)를 만들지 않는 표입니다";
    else {
      b.type = "button";
      b.title = "표 구조(3단계)를 만든 뒤 문서에 생긴 표 — 헤더·필드·소속을 아직 모릅니다\n표 구조는 그대로 쓰고, 이 표까지 넣으려면 「테이블」 탭의 「표 구조 만들기」 로 다시 만드세요 · 누르면 뼈대 밖 목록";
      b.onclick = (e) => { e.stopPropagation(); if (typeof driftView === "function") driftView(); };
    }
    m.append(b);
  } else {
    const b = el("button", "tm-owner muted", "소속 모름");
    b.type = "button";
    b.title = "표 구조(3단계)를 만들면 소속 헤딩·라벨이 표시됩니다 — 누르면 스크립트로 만들기(1초 안팎)";
    b.onclick = (e) => { e.stopPropagation(); headsStart(3, false); };
    m.append(b);
  }
  return m;
}

// ---- 엑셀식 보기 — 모형 -------------------------------------------------------------------------------------------
function xlNum(s) { // 문서 칸 글 → {v, pct} | null — §9 parse_num 과 같이: 뒤 코드·단위·% 를 떼고 쉼표 수, 괄호 음수, 「-」 홀로 = 0, 자리표시(0,000 · 00) = 없음
  if (s == null) return null;
  let t = oneLine(String(s)).trim();
  if (!t) return null;
  if (/^[-–—－]$/.test(t)) return { v: 0, pct: false, dash: true };
  t = xlStripCode(t).trim();
  const pct = /[%％]\s*$/.test(t);
  t = t.replace(/[%％]\s*$/, "").replace(XL_UNIT, "").replace(/[%％]\s*$/, "").trim();
  let neg = false;
  if (/^\(.*\)$/.test(t)) { neg = true; t = t.slice(1, -1).trim(); }
  if (/^[-−–]/.test(t)) { neg = !neg; t = t.slice(1).trim(); } else if (t.startsWith("+")) t = t.slice(1).trim();
  if (!/^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$|^\.\d+$/.test(t)) return null;
  if (XL_PH.test(t)) return null; // 자리표시 「0,000,000」「000,000」「00」
  const v = parseFloat(t.replace(/,/g, ""));
  return Number.isFinite(v) ? { v: neg ? -v : v, pct } : null;
}

function xlDocText(cell) { // 칸의 지금 문서 글 — 문서에 붙어 있는 문단은 타자 중인 글(DOM)을, 떼어진 문단(문서 자리 격자)은 서버에 반영된 글(state.texts)을
  return cell.paras.map((id) => { const el2 = paraEl(id); return el2 && typeof readText === "function" ? readText(el2) : (id in state.texts ? state.texts[id] : ""); })
    .map(oneLine).filter(Boolean).join(" ");
}
let xlLiveTimer = null;
document.addEventListener("input", (e) => { // 문서의 칸 글을 고치면 열린 2열 격자의 값·수식을 바로 다시 계산한다(PATCH 는 structRev 를 안 올리므로 따로)
  const col = heads.xl && heads.xl.col, p = e.target && e.target.closest ? e.target.closest("#doc .para[data-id]") : null;
  if (!col || !p || heads.dlg !== "xl") return;
  const wrap = document.querySelector(`.heads-col .xl-wrap.col[data-tbl="${CSS.escape(col.tid)}"]`);
  if (!wrap || !wrap._model || !wrap._model.cells.some((c) => c.paras.includes(p.dataset.id))) return;
  clearTimeout(xlLiveTimer);
  xlLiveTimer = setTimeout(() => { if (wrap.isConnected) xlRefresh(wrap); }, 300);
});

function xlModel(tid, b, t3, rec, judge = null, range = null) {
  // judge(수식 판정 — 지금 문서의 표·범위, spec ② §14)가 있으면 칸 역할·수식은 그것을, 없으면(docx·판정 실패) 3단계 결과(t3)를 쓴다.
  // range 가 있으면 격자는 그 범위만 보이고, 모형은 표 전체(범위 밖 칸을 가리키는 사용자 수식도 계산되게).
  const cells = [], occ = new Map();
  let nR = b.nRows || 0, nC = b.nCols || 0;
  const src = judge && (judge.cells || []).length ? judge : t3;
  const roles = new Map(((src && src.cells) || []).map((c) => [`${c.row},${c.col}`, c]));
  for (const c of b.cells || []) {
    const rs = c.rowSpan || 1, cs = c.colSpan || 1;
    const cell = { row: c.row, col: c.col, rs, cs, ref: xlRefOf(c.row, c.col), paras: (c.blocks || []).filter((x) => x.type === "paragraph").map((x) => x.id),
      nested: (c.blocks || []).some((x) => x.type === "table"), s3: roles.get(`${c.row},${c.col}`) || null };
    cell.role = cell.s3 ? cell.s3.role : null;
    cells.push(cell);
    nR = Math.max(nR, c.row + rs);
    nC = Math.max(nC, c.col + cs);
    for (let r = c.row; r < c.row + rs; r += 1) for (let k = c.col; k < c.col + cs; k += 1) if (!occ.has(`${r},${k}`)) occ.set(`${r},${k}`, cell);
  }
  const base = new Map(); // 판정(§14)·§9 가 만든 엑셀 수식(세로 합 하나 — excel: true)
  const fById = new Map();
  for (const f of (src && src.formulas) || []) { if (f.excel && f.formula) base.set(f.ref, f.formula); fById.set(f.ref, f); }
  const formulas = new Map(base);
  for (const [k, v] of Object.entries((rec && rec.formulas) || {})) { if (v) formulas.set(k, v); else formulas.delete(k); } // "" = §9 수식 끄기
  const inputs = new Set(cells.filter((c) => c.s3 && c.s3.input).map((c) => c.ref)); // 숫자 칸(넣을 자리 — 판정의 input)
  const rg = range || { r0: 0, c0: 0, r1: nR - 1, c1: nC - 1 };
  const inView = (c) => c.row >= rg.r0 && c.row + c.rs - 1 <= rg.r1 && c.col >= rg.c0 && c.col + c.cs - 1 <= rg.c1;
  return { tid, rows: nR, cols: nC, cells, occ, base, fById, formulas, values: new Map(), rec: rec || { instructions: "", formulas: {}, version: 0 }, t3: src, sel: null,
    res: new Map(), status: new Map(), inputs, range: range || null, view: rg, inView, judge, undo: null, llm: new Map(), llmInfo: null };
}

// ---- 수식 엔진 — 토큰 · 재귀 하강 · 칸 값(수식이면 계산, 아니면 문서 글의 수) · 함수 ----------------------------------------
const XL_ERR = (code) => ({ err: code });
const xlIsErr = (v) => v && typeof v === "object" && "err" in v;
function xlTokenize(src) {
  const out = [];
  let i = 0;
  const s = src.trim().replace(/^=/, "");
  while (i < s.length) {
    const ch = s[i];
    if (/\s/.test(ch)) { i += 1; continue; }
    if (/[0-9.]/.test(ch)) {
      const m = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.exec(s.slice(i));
      out.push({ t: "num", v: parseFloat(m[0]) });
      i += m[0].length;
      continue;
    }
    if (ch === '"') {
      let j = i + 1, str = "";
      for (; j < s.length; j += 1) { if (s[j] === '"') { if (s[j + 1] === '"') { str += '"'; j += 1; } else break; } else str += s[j]; }
      if (j >= s.length) throw XL_ERR("#VALUE!");
      out.push({ t: "str", v: str });
      i = j + 1;
      continue;
    }
    if (/[A-Za-z_$ㄱ-힝]/.test(ch)) {
      const m = /^[A-Za-z_$ㄱ-힝][\w$.ㄱ-힝]*/.exec(s.slice(i));
      out.push({ t: "id", v: m[0] });
      i += m[0].length;
      continue;
    }
    const two = s.slice(i, i + 2);
    if (two === "<>" || two === "<=" || two === ">=") { out.push({ t: "op", v: two }); i += 2; continue; }
    if ("+-*/^%(),:=<>&".includes(ch)) { out.push({ t: "op", v: ch }); i += 1; continue; }
    throw XL_ERR("#NAME?");
  }
  return out;
}

function xlParse(src) { // → 트리 {k: num|str|ref|range|fn|bin|un|pct, …}
  const tk = xlTokenize(src);
  let p = 0;
  const peek = () => tk[p], next = () => tk[p++];
  const isOp = (v) => peek() && peek().t === "op" && peek().v === v;
  const expect = (v) => { if (!isOp(v)) throw XL_ERR("#VALUE!"); p += 1; };
  function primary() {
    const t = next();
    if (!t) throw XL_ERR("#VALUE!");
    if (t.t === "num") return { k: "num", v: t.v };
    if (t.t === "str") return { k: "str", v: t.v };
    if (t.t === "op" && t.v === "(") { const e = cmp(); expect(")"); return e; }
    if (t.t === "op" && (t.v === "-" || t.v === "+")) return { k: "un", op: t.v, a: unary() };
    if (t.t === "id") {
      const up = t.v.toUpperCase();
      if (isOp("(")) {
        p += 1;
        const args = [];
        if (!isOp(")")) { for (;;) { args.push(cmp()); if (isOp(",")) { p += 1; continue; } break; } }
        expect(")");
        return { k: "fn", name: up, args };
      }
      if (up === "TRUE" || up === "FALSE") return { k: "bool", v: up === "TRUE" };
      const m = XL_REF.exec(up);
      if (!m) throw XL_ERR("#NAME?");
      if (isOp(":")) {
        p += 1;
        const t2 = next();
        const m2 = t2 && t2.t === "id" ? XL_REF.exec(t2.v.toUpperCase()) : null;
        if (!m2) throw XL_ERR("#REF!");
        return { k: "range", a: m[1] + m[2], b: m2[1] + m2[2] };
      }
      return { k: "ref", ref: m[1] + m[2] };
    }
    throw XL_ERR("#VALUE!");
  }
  function postfix() { let e = primary(); while (isOp("%")) { p += 1; e = { k: "pct", a: e }; } return e; }
  function unary() { if (isOp("-") || isOp("+")) { const op = next().v; return { k: "un", op, a: unary() }; } return postfix(); }
  function pow() { const a = unary(); if (isOp("^")) { p += 1; return { k: "bin", op: "^", a, b: pow() }; } return a; }
  function mul() { let a = pow(); while (isOp("*") || isOp("/")) { const op = next().v; a = { k: "bin", op, a, b: pow() }; } return a; }
  function add() { let a = mul(); while (isOp("+") || isOp("-") || isOp("&")) { const op = next().v; a = { k: "bin", op, a, b: mul() }; } return a; }
  function cmp() { let a = add(); while (peek() && peek().t === "op" && ["=", "<>", "<", ">", "<=", ">="].includes(peek().v)) { const op = next().v; a = { k: "bin", op, a, b: add() }; } return a; }
  const e = cmp();
  if (p < tk.length) throw XL_ERR("#VALUE!");
  return e;
}

function xlRefPos(ref) { const m = XL_REF.exec(ref); if (!m) return null; let c = 0; for (const ch of m[1]) c = c * 26 + (ch.charCodeAt(0) - 64); return { row: +m[2] - 1, col: c - 1 }; }

function xlEval(model) { // 모든 수식 칸의 값 → Map(주소 → 값 | {err}) · 순환은 #CYCLE!
  const memo = new Map(), visiting = new Set();
  const cellAt = (ref) => { const pos = xlRefPos(ref); return pos ? model.occ.get(`${pos.row},${pos.col}`) || null : null; };
  const rawValue = (cell) => { // 수식 없는 칸 — 고친 값 · 문서 글 → 수 | 글 | null(빈 값)
    const raw = model.values.has(cell.ref) ? model.values.get(cell.ref) : xlDocText(cell);
    const n = xlNum(raw);
    if (n) return n.v;
    const s = oneLine(raw).trim();
    return s && !xlIsPh(s) ? s : null; // 자리표시 「0,000,000」 = 빈 값(#VALUE! 가 아니라 미검증)
  };
  const value = (ref) => {
    const cell = cellAt(ref);
    if (!cell) return XL_ERR("#REF!");
    const key = cell.ref;
    if (model.formulas.has(key)) {
      if (memo.has(key)) return memo.get(key);
      if (visiting.has(key)) return XL_ERR("#CYCLE!");
      visiting.add(key);
      let v;
      try { v = ev(xlParse(model.formulas.get(key))); } catch (e) { v = xlIsErr(e) ? e : XL_ERR("#VALUE!"); }
      if (Array.isArray(v)) v = v.length ? v[0] : null;
      visiting.delete(key);
      memo.set(key, v);
      return v;
    }
    return rawValue(cell);
  };
  const num = (v) => { // 산술용 수 — 빈 값 0 · 참거짓 1/0 · 수 꼴 글은 수 · 아니면 #VALUE!
    if (xlIsErr(v)) return v;
    if (v == null || v === "") return 0;
    if (typeof v === "number") return v;
    if (typeof v === "boolean") return v ? 1 : 0;
    const n = xlNum(v);
    return n ? n.v : XL_ERR("#VALUE!");
  };
  const flat = (args) => { const out = []; for (const a of args) { const v = ev(a); if (Array.isArray(v)) out.push(...v); else out.push(v); } return out; };
  const nums = (vals) => { const out = []; for (const v of vals) { if (xlIsErr(v)) return v; if (typeof v === "number") out.push(v); else if (typeof v === "boolean") out.push(v ? 1 : 0); } return out; };
  const fin = (x) => (Number.isFinite(x) ? x : XL_ERR("#NUM!"));
  const round = (x, d, fn) => { const m = 10 ** (d || 0); return fn(x * m) / m; };
  const blank = (v) => v == null || v === ""; // 빈 칸(§9 「미검증」) — 0 이 아니라 빈 값으로 전파한다(빈 양식에서 합계 칸이 0 으로 차지 않게)
  const one = (v, f) => { if (blank(v[0])) return null; const x = num(v[0]); return xlIsErr(x) ? x : f(x); };
  const two = (v, f) => { if (blank(v[0]) || blank(v[1])) return null; const a = num(v[0]), b = num(v[1]); return xlIsErr(a) ? a : xlIsErr(b) ? b : f(a, b); };
  const fns = {
    SUM: (v) => { const n = nums(v); return xlIsErr(n) ? n : n.length ? n.reduce((a, x) => a + x, 0) : null; },
    AVERAGE: (v) => { const n = nums(v); return xlIsErr(n) ? n : n.length ? n.reduce((a, x) => a + x, 0) / n.length : null; },
    MIN: (v) => { const n = nums(v); return xlIsErr(n) ? n : n.length ? Math.min(...n) : null; },
    MAX: (v) => { const n = nums(v); return xlIsErr(n) ? n : n.length ? Math.max(...n) : null; },
    COUNT: (v) => { const n = nums(v); return xlIsErr(n) ? n : n.length; },
    COUNTA: (v) => v.filter((x) => !blank(x)).length,
    ABS: (v) => one(v, Math.abs),
    INT: (v) => one(v, Math.floor),
    SQRT: (v) => one(v, (x) => (x < 0 ? XL_ERR("#NUM!") : Math.sqrt(x))),
    ROUND: (v) => { if (blank(v[0])) return null; const x = num(v[0]), d = num(v[1] ?? 0); return xlIsErr(x) ? x : xlIsErr(d) ? d : round(x, d, Math.round); },
    ROUNDUP: (v) => { if (blank(v[0])) return null; const x = num(v[0]), d = num(v[1] ?? 0); return xlIsErr(x) ? x : xlIsErr(d) ? d : round(x, d, (y) => Math.sign(y) * Math.ceil(Math.abs(y))); },
    ROUNDDOWN: (v) => { if (blank(v[0])) return null; const x = num(v[0]), d = num(v[1] ?? 0); return xlIsErr(x) ? x : xlIsErr(d) ? d : round(x, d, (y) => Math.sign(y) * Math.floor(Math.abs(y))); },
    MOD: (v) => two(v, (a, b) => (b === 0 ? XL_ERR("#DIV/0!") : a - b * Math.floor(a / b))),
    POWER: (v) => two(v, (a, b) => fin(a ** b)),
    AND: (v) => { for (const x of v) { if (xlIsErr(x)) return x; if (!truthy(x)) return false; } return true; },
    OR: (v) => { for (const x of v) { if (xlIsErr(x)) return x; if (truthy(x)) return true; } return false; },
    NOT: (v) => (xlIsErr(v[0]) ? v[0] : !truthy(v[0])),
  };
  const truthy = (x) => (typeof x === "number" ? x !== 0 : typeof x === "boolean" ? x : x != null && x !== "");
  function ev(e) {
    switch (e.k) {
      case "num": case "str": case "bool": return e.v;
      case "ref": return value(e.ref);
      case "range": {
        const a = xlRefPos(e.a), b = xlRefPos(e.b);
        if (!a || !b) return XL_ERR("#REF!");
        const out = [], seen = new Set();
        for (let r = Math.min(a.row, b.row); r <= Math.max(a.row, b.row); r += 1) for (let k = Math.min(a.col, b.col); k <= Math.max(a.col, b.col); k += 1) {
          const cell = model.occ.get(`${r},${k}`);
          if (!cell || seen.has(cell.ref)) continue; // 병합 칸은 한 번
          seen.add(cell.ref);
          out.push(value(cell.ref));
        }
        return out;
      }
      case "pct": { const a = ev(e.a); if (blank(a)) return null; const x = num(a); return xlIsErr(x) ? x : x / 100; }
      case "un": { const a = ev(e.a); if (blank(a)) return null; const x = num(a); return xlIsErr(x) ? x : e.op === "-" ? -x : x; }
      case "fn": {
        if (e.name === "IF") {
          const c = ev(e.args[0]);
          if (xlIsErr(c)) return c;
          return truthy(c) ? (e.args[1] ? ev(e.args[1]) : true) : (e.args[2] ? ev(e.args[2]) : false);
        }
        const f = fns[e.name];
        if (!f) return XL_ERR("#NAME?");
        return f(flat(e.args));
      }
      case "bin": {
        let a = ev(e.a), b = ev(e.b);
        if (Array.isArray(a)) a = a.length ? a[0] : null;
        if (Array.isArray(b)) b = b.length ? b[0] : null;
        if (xlIsErr(a)) return a;
        if (xlIsErr(b)) return b;
        if (e.op === "&") return `${a ?? ""}${b ?? ""}`;
        if (["=", "<>", "<", ">", "<=", ">="].includes(e.op)) {
          const na = typeof a === "string" ? xlNum(a) : null, nb = typeof b === "string" ? xlNum(b) : null;
          const x = na ? na.v : a ?? "", y = nb ? nb.v : b ?? "";
          if (typeof x === typeof y) return e.op === "=" ? x === y : e.op === "<>" ? x !== y : e.op === "<" ? x < y : e.op === ">" ? x > y : e.op === "<=" ? x <= y : x >= y;
          return e.op === "<>";
        }
        if (blank(a) && blank(b)) return null; // 빈 칸끼리 — 빈 값
        if ((blank(a) || blank(b)) && e.op !== "+" && e.op !== "-") return null; // 빈 칸이 낀 곱·나눗셈·거듭제곱 — 빈 값(「(E5/K5)*100」 이 0 이 되지 않게)
        const x = num(a), y = num(b);
        if (xlIsErr(x)) return x;
        if (xlIsErr(y)) return y;
        if (e.op === "+") return x + y;
        if (e.op === "-") return x - y;
        if (e.op === "*") return x * y;
        if (e.op === "/") return y === 0 ? XL_ERR("#DIV/0!") : x / y;
        return fin(x ** y);
      }
      default: return XL_ERR("#VALUE!");
    }
  }
  const res = new Map();
  for (const ref of model.formulas.keys()) res.set(ref, value(ref));
  return res;
}

function xlFmt(v, like = "") { // 계산값 → 문서에 쓸 글 — 문서 글의 꼴을 따름(쉼표가 있었거나 1,000 이상이면 쉼표 · 끝 % 유지 · 소수는 문서 자릿수, 없으면 2자리까지)
  if (typeof v !== "number" || !Number.isFinite(v)) return v == null ? "" : String(v);
  const n = xlNum(like);
  const dec = like && /\.(\d+)/.test(oneLine(like)) ? RegExp.$1.length : (Number.isInteger(v) ? 0 : 2);
  let s = Math.abs(v).toFixed(dec);
  if (dec > 0 && !(like && /\.\d+/.test(like))) s = s.replace(/\.?0+$/, "");
  const grouping = /\d,\d{3}/.test(like || "") || (!like && Math.abs(v) >= 1000) || (like && !xlNum(like) && Math.abs(v) >= 1000) || (n && Math.abs(n.v) >= 1000 && /,/.test(like));
  if (grouping) s = s.replace(/^(\d+)/, (m) => m.replace(/\B(?=(\d{3})+(?!\d))/g, ","));
  if (v < 0) s = `-${s}`;
  if (n && n.pct) s += "%";
  return s;
}

const xlShow = (v) => (xlIsErr(v) ? v.err : v == null ? "" : typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString("ko-KR") : v.toLocaleString("ko-KR", { maximumFractionDigits: 4 }))
  : typeof v === "boolean" ? (v ? "TRUE" : "FALSE") : String(v));

// ---- 엑셀식 보기 — 열기·닫기·되살리기 ---------------------------------------------------------------------------------
function xlBlock(tid, blocks = state.blocks || []) { // 표 블록(칸 안 표 포함) — state.byId 는 문단만 색인한다(walkParas)
  for (const b of blocks) {
    if (b.type === "table" && b.id === tid) return b;
    for (const c of b.cells || []) { const f = xlBlock(tid, c.blocks || []); if (f) return f; }
  }
  return null;
}

async function xlOpen(tid) {
  if (!state.id || !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const epoch = state.epoch;
  heads.xl.open.add(tid);
  await xlStore();
  await xlFull();
  await xlJudge(tid, null); // 캐시에 — xlApply(동기)가 꺼내 쓴다
  if (epoch !== state.epoch) return;
  tblMarksDraw(); // → xlApply
  const wrap = document.querySelector(`#doc .xl-wrap[data-tbl="${CSS.escape(tid)}"]`);
  if (wrap) wrap.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function xlClose(tid) {
  heads.xl.open.delete(tid);
  const wrap = document.querySelector(`#doc .xl-wrap[data-tbl="${CSS.escape(tid)}"]`);
  if (wrap && wrap._frags) {
    wrap.replaceWith(wrap._frags[0]);
    for (const f of wrap._frags.slice(1)) f.hidden = false;
  }
  tblMarksDraw();
}

function xlApply() { // heads.xl.open 의 표마다 — 격자가 없으면(쪽을 다시 나눔) 조각을 찾아 다시 바꾼다
  for (const tid of [...heads.xl.open]) {
    if (document.querySelector(`#doc .xl-wrap[data-tbl="${CSS.escape(tid)}"]`)) continue;
    const frags = [...document.querySelectorAll(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`)];
    if (!frags.length) continue;
    const wrap = xlBuild(tid, frags, { judge: (heads.xl.judge && heads.xl.judge.get(xlJudgeKey(tid, null))) || null });
    if (!wrap) { heads.xl.open.delete(tid); continue; }
    frags[0].replaceWith(wrap);
    for (const f of frags.slice(1)) f.hidden = true;
  }
}

function xlBuild(tid, frags, { range = null, judge = null } = {}) {
  const b = xlBlock(tid);
  if (!b) return null;
  const full = heads.tbl.data, s3 = heads.view && heads.view.stage3;
  const t3 = full && s3 && s3.meta && heads.tbl.key === `${s3.meta.run}|${s3.meta.at}` ? (full.tables || []).find((x) => x.id === tid) || null : null;
  const rec = ((heads.xl.store || {}).tables || {})[tid] || null;
  const model = xlModel(tid, b, t3, rec, judge, range);
  const lr = heads.xl.llm && heads.xl.llm.get(xlJudgeKey(tid, range)); // 받아 둔 LLM 제안(격자를 다시 만들어도 남는다 — 구조가 바뀌면 열쇠가 달라져 버려진다)
  if (lr) { model.llm = new Map((lr.formulas || []).map((f) => [f.ref, f])); model.llmInfo = lr; }
  const wrap = el("div", "xl-wrap");
  wrap.dataset.tbl = tid;
  wrap._frags = frags;
  wrap._model = model;
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", `표 ${tid} 엑셀식 보기`);
  const bar = el("div", "xl-bar");
  const name = el("input", "xl-name");
  name.readOnly = true;
  name.value = "";
  name.setAttribute("aria-label", "칸 주소");
  const fx = el("input", "xl-fx");
  fx.placeholder = "칸을 고르면 값·수식 — 「=」 로 시작하면 수식 · Enter 로 반영";
  fx.setAttribute("aria-label", "수식 줄");
  fx.onkeydown = (e) => {
    if (e.key === "Enter") { e.preventDefault(); if (model.sel) { xlCommit(wrap, model.sel, fx.value); xlSelect(wrap, model.sel); } }
    else if (e.key === "Escape") { e.preventDefault(); xlSelect(wrap, model.sel); }
  };
  fx.oninput = () => { if (model.sel) xlRefsDraw(wrap, fx.value); }; // 치는 동안 참조 칸 색을 따라 바꾼다
  const write = hBtn("문서에 반영", () => xlWriteBack(wrap), { title: "수식 칸의 계산값과 고친 값을 그 칸의 문단 글로 씁니다(문단이 하나인 칸만 — 기존 글을 바꿈, 되돌리기·실행 취소로 돌릴 수 있음)" });
  write.classList.add("xl-write");
  bar.append(name, fx, write);
  const dl = hBtn("엑셀로 받기", () => xlDownload(wrap), { title: "이 격자 그대로 .xlsx — 수식 칸은 엑셀 수식(사용자 수식 포함) · 숫자 칸 연노랑 · 불일치 빨강 · 원문과 다른 칸은 메모에 원문"
    + (range ? " · 범위 왼쪽 위가 A1" : "") });
  const up = hBtn("정렬 ↑", () => xlSort(wrap, 1), { title: "고른 칸의 열을 기준으로 그 자료 행 묶음을 오름차순(작은 수·가나다 먼저, 빈 칸은 끝) — 헤더·합계 행은 그대로, 병합 칸(「1단계」)이 묶은 행 안에서만 · 수식 칸은 자리에서 다시 계산 · 「문서에 반영」 을 눌러야 문서가 바뀜" });
  const down = hBtn("정렬 ↓", () => xlSort(wrap, -1), { title: "고른 칸의 열을 기준으로 내림차순(큰 수 먼저, 빈 칸은 끝)" });
  const undo = hBtn("정렬 되돌리기", () => xlSortUndo(wrap), { title: "마지막 정렬 전 값으로(문서에 반영하기 전)" });
  undo.classList.add("xl-undo");
  undo.hidden = true;
  bar.append(dl, up, down, undo);
  if (judge) {
    const k = judge.counts || {};
    const st = el("span", "muted xl-note", `수식 자리 판정 ${nf(k.excel || 0)} · 숫자 칸 ${nf(k.input || 0)}${judge.scope === "table" && range ? " (표 전체 맥락)" : ""}`);
    st.title = "지금 문서의 이 표" + (range ? "(고른 범위)" : "") + "만 읽어 스크립트로 판정 — 열헤더·행헤더 · 합계(「합계·계·소계·총 …비」)·비율·코드 식(「(A+B)」·「(M=K+L)」·「(I/E2)」) 수식 · 숫자를 넣을 칸"
      + (judge.scope === "table" && range ? "\n고른 범위에 헤더가 없어 표 전체로 판정하고 범위 안 칸의 수식만 씀" : "");
    bar.append(st, hBtn("다시 판정", async () => {
      const j = await xlJudge(tid, range, true);
      if (j && wrap.isConnected) { if (heads.xl.col && heads.xl.col.tid === tid && !frags.length) xlColumn(tid, range); else { const nw = xlBuild(tid, frags, { range, judge: j }); if (nw) wrap.replaceWith(nw); } }
    }, { title: "문서 글을 고친 뒤 — 칸 역할·수식 자리를 지금 글로 다시 판정" }));
    const lb = hBtn("LLM 수식 판정", () => xlLlm(wrap), { title: "누를 때만 LLM 을 부릅니다 — 표와 표 앞뒤 글(제목·단위·각주)·표 지침을 읽고 수식을 제안(위 판정 수식의 확인·고침 포함). 제안은 검사한 뒤 보여 주고, 「적용」 을 눌러야 수식이 됩니다" });
    lb.classList.add("xl-llm-btn");
    bar.append(lb, el("span", "xl-llm"));
  } else if (t3) bar.append(el("span", "muted xl-note", "판정 없음 — 3단계 표 구조의 수식"));
  else bar.append(el("span", "muted xl-note", state.format === "docx" ? "수식 판정은 hwpx 만 — 격자만" : "수식 판정 실패 — 격자만"));
  if (t3) bar.append(hBtn("표 보기", () => headsTables(tid), { title: "2열에서 3단계 표 구조(문서 전체 실행 결과)의 칸 역할 격자·수식 검증·필드 목록" }));
  bar.append(hBtn("표 지침", () => tblAgentView(tid), { title: "작성요령 · 사용자 지침(표 에이전트 입력)" }), el("span", "spacer"));
  if (frags.length) bar.append(hBtn("문서 보기", () => xlClose(tid), { title: "원래 표로" }));
  else if (!range) bar.append(hBtn("문서 자리에서 보기", () => xlOpen(tid), { title: "문서의 그 표 자리를 이 격자로 바꿔 보기(다시 누르면 원래 표)" }));
  wrap.append(bar);
  const refs = el("div", "xl-refs"); // 「참조」 줄 — 고른 수식 칸이 가리키는 칸·범위(xlRefsDraw)
  refs.setAttribute("aria-label", "고른 수식이 참조한 칸");
  refs.addEventListener("wheel", (e) => { // 한 줄로 고정한 줄 — 넘치면 휠로 가로로 굴린다
    if (refs.scrollWidth <= refs.clientWidth) return;
    refs.scrollLeft += e.deltaY || e.deltaX;
    e.preventDefault();
  }, { passive: false });
  wrap.append(refs);
  const scroll = el("div", "xl-scroll");
  scroll.append(xlGrid(wrap));
  wrap.append(scroll);
  const foot = el("div", "xl-foot");
  wrap.append(foot);
  wrap.tabIndex = 0;
  wrap.onkeydown = (e) => xlKey(wrap, e);
  xlRefresh(wrap);
  return wrap;
}

function xlGrid(wrap) {
  const model = wrap._model;
  const table = el("table", "xl");
  table.setAttribute("aria-label", `표 ${model.tid} 격자`);
  const thead = el("thead"), hr = el("tr");
  const v = model.view; // 보일 범위(표 좌표 — 열 글자·행 번호는 표 기준 그대로)
  hr.append(el("th", "corner"));
  for (let k = v.c0; k <= v.c1; k += 1) hr.append(el("th", null, colLetter(k)));
  thead.append(hr);
  table.append(thead);
  const tb = el("tbody");
  for (let r = v.r0; r <= v.r1; r += 1) {
    const tr = el("tr");
    tr.append(el("th", null, String(r + 1)));
    for (let k = v.c0; k <= v.c1; k += 1) {
      const c = model.occ.get(`${r},${k}`);
      if (!c || !model.inView(c)) { tr.append(el("td", "none")); continue; } // 범위에 반만 걸친 병합 칸(구조 편집 뒤 낡은 범위)은 빈 자리로
      if (c.row !== r || c.col !== k) continue;
      const td = el("td", c.role || "");
      if (c.rs > 1) td.rowSpan = c.rs;
      if (c.cs > 1) td.colSpan = c.cs;
      td.dataset.ref = c.ref;
      td.onclick = () => xlSelect(wrap, c.ref);
      td.ondblclick = () => xlEdit(wrap, c.ref);
      tr.append(td);
    }
    tb.append(tr);
  }
  table.append(tb);
  return table;
}

function xlRefresh(wrap) { // 다시 계산하고 칸마다 글·색을 맞춘다
  const model = wrap._model;
  model.res = xlEval(model);
  const byRef = new Map([...wrap.querySelectorAll("td[data-ref]")].map((td) => [td.dataset.ref, td]));
  let bad = 0, fill = 0, errs = 0, dirty = 0, blanks = 0, inps = 0, origs = 0;
  model.status = new Map();
  for (const c of model.cells) {
    const td = byRef.get(c.ref);
    if (!td) continue;
    const doc = xlDocText(c), f = model.formulas.get(c.ref);
    td.className = c.role || "";
    td.title = "";
    if (td.querySelector("input")) continue; // 고치는 중
    const orig = xlOrig(c); // 올린 원본(원문)과 글이 다른 칸 — 문서의 「고친 문단」 표시(.para.edited)와 같은 기준
    if (orig != null) { td.classList.add("orig"); origs += 1; }
    if (!f && model.inputs.has(c.ref)) { td.classList.add("inp"); inps += 1; }
    if (f) {
      const v = model.res.get(c.ref), dn = xlNum(doc);
      td.classList.add("fx");
      let st = "";
      if (xlIsErr(v)) { st = "err"; errs += 1; }
      else if (v == null || v === "") { st = "blank"; blanks += 1; } // 피연산자가 빈 칸 — §9 「미검증」
      else if (typeof v === "number") {
        if (dn) { if (Math.abs(dn.v - v) <= 0.5 * 10 ** -(oneLine(doc).match(/\.(\d+)/) ? RegExp.$1.length : 0) + 1e-9) st = "ok"; else { st = "bad"; bad += 1; } }
        else if (!oneLine(doc).trim() || xlIsPh(doc)) { st = "fill"; fill += 1; } // 문서 칸이 비었거나 자리표시 — 미기입
        else { st = "bad"; bad += 1; }
      }
      if (st) td.classList.add(st);
      model.status.set(c.ref, st);
      if (typeof v === "number") td.classList.add("num");
      const dn0 = xlNum(doc);
      td.textContent = xlShow(v) + (typeof v === "number" && dn0 && dn0.pct ? "%" : "");
      const fb = model.fById.get(c.ref);
      td.title = `${c.ref} ${f}\n계산값 ${st === "blank" ? "(빈 값 — 피연산자가 빈 칸)" : xlShow(v)} · 문서 값 ${doc || "(빈 칸)"}${st === "bad" ? " · 불일치(원문 값과 다름)" : st === "fill" ? " · 문서 칸이 비어 있음(미기입)" : st === "ok" ? " · 일치" : st === "blank" ? " · 미검증" : ""}`
        + (model.base.has(c.ref) && model.base.get(c.ref) === f ? `\n판정한 수식${fb && fb.note ? ` — ${fb.note}` : ""}` : "\n사용자 수식") + (c.role && XL_ROLE[c.role] ? `\n${XL_ROLE[c.role]}` : "")
        + (orig != null ? `\n원문과 다름 — 원문 「${orig || "(빈 칸)"}」` : "");
    } else {
      const raw = model.values.has(c.ref) ? model.values.get(c.ref) : doc;
      td.textContent = c.nested && !raw ? "〔표〕" : raw;
      if (xlNum(raw)) td.classList.add("num");
      if (model.values.has(c.ref) && model.values.get(c.ref) !== doc) { td.classList.add("dirty"); dirty += 1; }
      td.title = `${c.ref}${c.role && XL_ROLE[c.role] ? ` · ${XL_ROLE[c.role]}` : ""}${model.inputs.has(c.ref) ? " · 숫자 칸(숫자를 넣을 자리)" : ""}${model.values.has(c.ref) ? `\n고친 값(문서에 반영 전) · 문서 값 ${doc || "(빈 칸)"}` : ""}`
        + (c.s3 && c.s3.role === "field" && (c.s3.rowPath || c.s3.colPath) ? `\n행헤더 ${(c.s3.rowPath || []).map((id) => xlNameOf(model, id)).join(" › ") || "—"} · 열헤더 ${(c.s3.colPath || []).map((id) => xlNameOf(model, id)).join(" › ") || "—"}` : "")
        + (orig != null ? `\n원문과 다름 — 원문 「${orig || "(빈 칸)"}」` : "");
    }
    const ls = xlLlmState(model, c.ref); // LLM 제안이 걸린 칸 — 새 수식·지금 수식과 다름·끄기(값만 같은 다른 꼴은 표시 안 함)
    if (ls && ls.state !== "equiv") { td.classList.add("llm"); td.title += `\n${XL_LLM_KO[ls.state]}${ls.p.formula ? ` ${ls.p.formula}` : ""}${ls.p.reason ? ` — ${ls.p.reason}` : ""}`; }
    if (model.sel === c.ref) td.classList.add("sel");
  }
  const undo = wrap.querySelector(".xl-undo");
  if (undo) undo.hidden = !model.undo;
  const pending = xlPending(wrap).length;
  const write = wrap.querySelector(".xl-write");
  write.textContent = pending ? `문서에 반영 ${pending}` : "문서에 반영";
  write.disabled = !pending;
  const user = [...model.formulas].filter(([k, v]) => model.base.get(k) !== v).length + [...model.base].filter(([k]) => !model.formulas.has(k)).length;
  const foot = wrap.querySelector(".xl-foot");
  foot.textContent = "";
  const v = model.view, shown = model.cells.filter((c) => byRef.has(c.ref)).length;
  const chip = (cls, text, title) => { const s = el("span", "xl-key"); s.append(el("i", cls), text); s.title = title; return s; };
  foot.append(el("span", null, `${model.range ? `${xlRangeName(v)} · ` : ""}${v.r1 - v.r0 + 1}×${v.c1 - v.c0 + 1} · 칸 ${nf(shown)} · 수식 ${nf([...model.formulas.keys()].filter((k) => byRef.has(k)).length)}${user ? `(사용자 ${user})` : ""}`),
    chip("fx", `수식`, "수식 칸 — 계산값을 보임(초록 테두리 = 문서 값과 일치)"),
    chip("inp", `숫자 칸 ${nf(inps)}`, "숫자를 넣을 자리 — 수식의 피연산자이거나 수·숫자 자리표시(「0,000,000」)인 칸"),
    chip("bad", `불일치 ${nf(bad)}`, "수식 계산값과 문서(원문) 값이 다른 칸"),
    chip("fill", `미기입 ${nf(fill)}`, "수식 칸인데 문서 칸이 비어 있음"),
    chip("orig", `원문과 다름 ${nf(origs)}`, "올린 원본(원문)에서 글을 고친 칸 — 마우스를 올리면 원문"),
    blanks ? el("span", null, `미검증(빈 칸) ${nf(blanks)}`) : "", errs ? el("span", "warn", `오류 ${nf(errs)}`) : "",
    dirty ? el("span", null, `고친 값 ${nf(dirty)}`) : "",
    el("span", "muted", "Enter 반영·아래로 · Tab 오른쪽 · F2/두 번 누르기 고침 · Delete 비움 · 「=」 수식(작업에 저장) · 칸을 누르고 정렬 ↑↓"));
  if (heads.xl.saving.get(model.tid) === "fail") foot.append(el("span", "warn", "수식 저장 실패 — 다시 고치면 다시 시도"));
  xlLlmBar(wrap);
  xlRefsDraw(wrap); // 칸 색을 새로 매겼으니 참조 칸 표시도 다시
}

// ---- LLM 수식 판정 — 단추를 누를 때만 호출 1번(서버가 답을 검사·견줌). 제안은 자동으로 적용하지 않는다: 보라 귀퉁이 표시 → 칸을 골라 「적용」·「무시」, 또는 도구 줄 「모두 적용」 ----------------
const XL_LLM_KO = { new: "LLM 제안", diff: "LLM 제안(지금 수식과 다름)", equiv: "LLM 제안(꼴만 다르고 값은 같음)", off: "LLM 제안: 계산 칸이 아님" };
const xlCanon = (f) => String(f || "").split(/("(?:[^"]|"")*")/).map((p, i) => (i % 2 ? p : p.replace(/\s+/g, "").toUpperCase().replace(/\$/g, ""))).join(""); // table_formula.canon 과 같은 꼴
function xlLlmState(model, ref) { // 그 칸의 제안과 지금 수식의 사이 → null(제안 없음 · 이미 같은 수식) | {p, state: new|diff|equiv|off}
  const p = model.llm.get(ref);
  if (!p) return null;
  const cur = model.formulas.get(ref) || "";
  if (!p.formula) return cur ? { p, state: "off" } : null;
  if (!cur) return { p, state: "new" };
  if (xlCanon(cur) === xlCanon(p.formula)) return null;
  if (p.kind === "equiv" && p.script && xlCanon(p.script) === xlCanon(cur)) return { p, state: "equiv" };
  return { p, state: "diff" };
}

async function xlLlm(wrap) {
  const model = wrap._model, tid = model.tid, rg = model.range, key = xlJudgeKey(tid, rg), id = state.id, epoch = state.epoch;
  heads.xl.llmBusy = heads.xl.llmBusy || new Set();
  if (heads.xl.llmBusy.has(key)) return; // 이미 묻는 중
  heads.xl.llmBusy.add(key);
  xlLlmBar(wrap);
  let r = null, err = null;
  try { r = await api(`/api/docs/${encodeURIComponent(id)}/tables/${encodeURIComponent(tid)}/excel/llm`, { method: "POST", headers: H_JSON, body: JSON.stringify(rg ? { range: rg } : {}) }); }
  catch (e) { err = e; }
  heads.xl.llmBusy.delete(key);
  if (id !== state.id || epoch !== state.epoch) return; // 그 사이 다른 문서
  if (err) toast(`LLM 수식 판정을 못 했습니다: ${err.message}`, true);
  else if (key !== xlJudgeKey(tid, rg)) { toast("LLM 이 판정하는 동안 표의 행·열이 바뀌어 제안을 버렸습니다 — 다시 눌러 주세요", true); r = null; }
  else { heads.xl.llm = heads.xl.llm || new Map(); if (heads.xl.llm.size > 40) heads.xl.llm.clear(); heads.xl.llm.set(key, r); }
  for (const w of document.querySelectorAll(`.xl-wrap[data-tbl="${CSS.escape(tid)}"]`)) { // 그 사이 격자가 다시 만들어졌을 수 있다 — 지금 화면의 격자에 얹는다
    const m = w._model;
    if (!m || xlRangeKey(m.range) !== xlRangeKey(rg)) continue;
    if (r) { m.llm = new Map((r.formulas || []).map((f) => [f.ref, f])); m.llmInfo = r; }
    xlRefresh(w);
  }
  if (r) {
    const k = r.counts || {};
    toast(`LLM 제안 — 새 수식 ${nf(k.new || 0)} · 다름 ${nf(k.diff || 0)}${k.off ? ` · 끄기 ${nf(k.off)}` : ""} · 같음 ${nf((k.same || 0) + (k.equiv || 0))}${k.rejected ? ` · 검사에서 뺌 ${nf(k.rejected)}` : ""}`);
  }
}

function xlLlmBar(wrap) { // 도구 줄 — 단추의 「판정 중」 · 제안 수(지금 수식에 견줘 다시 셈) · 「모두 적용」·「제안 지우기」
  const model = wrap._model, box = wrap.querySelector(".xl-llm"), btn = wrap.querySelector(".xl-llm-btn");
  if (!box) return;
  const busy = !!(heads.xl.llmBusy && heads.xl.llmBusy.has(xlJudgeKey(model.tid, model.range)));
  if (btn) { btn.disabled = busy; btn.textContent = busy ? "LLM 이 판정하는 중…" : "LLM 수식 판정"; }
  box.textContent = "";
  const info = model.llmInfo;
  if (!info) return;
  const n = { new: 0, diff: 0, off: 0, equiv: 0, same: 0 }, todo = [];
  for (const ref of model.llm.keys()) {
    const s = xlLlmState(model, ref);
    n[s ? s.state : "same"] += 1;
    const mine = model.formulas.has(ref) && model.base.get(ref) !== model.formulas.get(ref); // 직접 넣은 수식 — 「모두 적용」 이 덮어쓰지 않는다
    if (s && s.state !== "equiv" && !(mine && s.state !== "new")) todo.push(ref);
  }
  const pend = n.new + n.diff + n.off, call = info.call || {}, rej = info.rejected || [];
  const st = el("span", `xl-note ${pend ? "xl-llm-pend" : "muted"}`, `LLM 제안 새 ${nf(n.new)} · 다름 ${nf(n.diff)}${n.off ? ` · 끄기 ${nf(n.off)}` : ""} · 같음 ${nf(n.same + n.equiv)}`);
  st.title = [info.note ? `LLM: ${info.note}` : "", `새 = 수식이 없던 칸 · 다름 = 지금 수식과 값이 다름 · 같음 = 같은 수식(꼴만 다른 ${nf(n.equiv)}개 포함)`,
    rej.length ? `검사에서 뺀 제안 ${nf((info.counts || {}).rejected || rej.length)}: ${rej.slice(0, 6).map((x) => `${x.ref} ${x.why}`).join(" · ")}${rej.length > 6 ? " …" : ""}` : "",
    `${call.backend || ""} ${call.model || ""}${call.ms != null ? ` · ${(call.ms / 1000).toFixed(1)}초` : ""}${call.costUsd != null ? ` · $${Number(call.costUsd).toFixed(3)}` : ""}`.trim()].filter(Boolean).join("\n");
  box.append(st);
  if (todo.length) box.append(hBtn(`모두 적용 ${nf(todo.length)}`, () => xlLlmApply(wrap, todo), { title: "제안을 한꺼번에 수식으로(작업에 저장) — 직접 넣은 수식과 다른 제안은 빼고, 그런 칸은 골라서 적용하세요" }));
  box.append(hBtn("제안 지우기", () => xlLlmDrop(wrap, null), { title: "LLM 제안을 모두 버립니다(이미 적용한 수식은 그대로)" }));
}

function xlLlmApply(wrap, refs) { // 제안 → 수식(사용자 수식으로 저장 — 판정 수식과 같아지면 저장할 것이 없다). 끄기 제안은 수식만 지우고 칸의 값은 그대로
  const model = wrap._model;
  for (const ref of refs) {
    const p = model.llm.get(ref);
    if (!p) continue;
    if (p.formula) { model.formulas.set(ref, p.formula); model.values.delete(ref); } else model.formulas.delete(ref);
  }
  xlRefresh(wrap);
  xlPersist(wrap);
  wrap.focus({ preventScroll: true });
}

function xlLlmDrop(wrap, refs) { // refs = null 이면 전부
  const model = wrap._model, key = xlJudgeKey(model.tid, model.range), lr = heads.xl.llm && heads.xl.llm.get(key);
  if (!refs) { model.llm = new Map(); model.llmInfo = null; if (heads.xl.llm) heads.xl.llm.delete(key); }
  else { for (const ref of refs) model.llm.delete(ref); if (lr) lr.formulas = (lr.formulas || []).filter((f) => model.llm.has(f.ref)); }
  xlRefresh(wrap);
  wrap.focus({ preventScroll: true });
}

function xlLlmChip(wrap, ref, ls) { // 「참조」 줄 맨 앞 — 고른 칸의 제안 · 「적용」·「무시」
  const box = el("span", "xl-llm-prop");
  box.append(el("b", null, XL_LLM_KO[ls.state]));
  if (ls.p.formula) box.append(el("code", null, short(ls.p.formula, 48)));
  box.title = `${XL_LLM_KO[ls.state]}${ls.p.formula ? ` ${ls.p.formula}` : ""}\n까닭: ${ls.p.reason || "—"}${ls.p.script ? `\n판정한 수식: ${ls.p.script}` : ""}`;
  box.append(hBtn("적용", () => xlLlmApply(wrap, [ref]), { title: ls.p.formula ? "이 제안을 이 칸의 수식으로(작업에 저장)" : "이 칸의 수식을 끕니다(값은 그대로)" }),
    hBtn("무시", () => xlLlmDrop(wrap, [ref]), { title: "이 칸의 제안만 버립니다" }));
  return box;
}

// ---- 참조 칸 표시 — 수식 칸을 고르면(수식을 치는 동안에도) 그 수식이 가리키는 칸·범위를 엑셀처럼 묶음마다 다른 색 테두리로, 도구 줄 아래 「참조」 줄에 같은 색 표지로 ----------------
const XL_REF_COLORS = 6; // style.css .xl-wrap .r0 ~ .r5
const XL_REF_SCAN = /(?<![A-Za-z0-9_$.])\$?([A-Za-z]{1,3})\$?([1-9]\d{0,3})(?::\$?([A-Za-z]{1,3})\$?([1-9]\d{0,3}))?(?![\w(.])/g;
function xlRefGroups(model, formula) { // 수식 글 → [{text: "E3:E4", cells: [칸…]}] — 나온 순서, 같은 주소는 한 번. 치는 중인 반쪽 수식도 읽게 구문 분석 없이 주소만 훑는다
  const out = [], seen = new Set();
  const src = String(formula || "").replace(/"(?:[^"]|"")*"/g, (m) => " ".repeat(m.length)); // 글 상수 안의 「A1」 은 주소가 아님
  for (const m of src.matchAll(XL_REF_SCAN)) {
    const a = xlRefPos(`${m[1]}${m[2]}`.toUpperCase()), b = m[3] ? xlRefPos(`${m[3]}${m[4]}`.toUpperCase()) : a;
    if (!a || !b) continue;
    const text = (m[3] ? `${m[1]}${m[2]}:${m[3]}${m[4]}` : `${m[1]}${m[2]}`).toUpperCase();
    if (seen.has(text)) continue;
    seen.add(text);
    const cells = [], got = new Set();
    const r0 = Math.max(0, Math.min(a.row, b.row)), r1 = Math.min(model.rows - 1, Math.max(a.row, b.row));
    const c0 = Math.max(0, Math.min(a.col, b.col)), c1 = Math.min(model.cols - 1, Math.max(a.col, b.col));
    for (let r = r0; r <= r1; r += 1) for (let k = c0; k <= c1; k += 1) {
      const c = model.occ.get(`${r},${k}`);
      if (c && !got.has(c.ref)) { got.add(c.ref); cells.push(c); } // 병합 칸은 한 번
    }
    out.push({ text, cells });
  }
  return out;
}

function xlRefName(model, cells) { // 참조 칸들의 이름 — 모두가 함께 가진 가장 안쪽 행헤더(없으면 열헤더) 글. 「E3:E4」 → 「내부인건비(A)」, 「E23:J23」 → 「직접비 소계」
  for (const key of ["rowPath", "colPath"]) {
    const paths = cells.map((c) => (c.s3 && c.s3[key]) || []);
    if (!paths.length || paths.some((p) => !p.length)) continue;
    let n = 0;
    while (n < paths[0].length && paths.every((p) => p[n] === paths[0][n])) n += 1;
    if (n) return xlNameOf(model, paths[0][n - 1]);
  }
  return "";
}

function xlRefsDraw(wrap, live) { // live = 치는 중인 글(수식 줄·칸 안 입력) — 없으면 고른 칸에 저장된 수식. 칸 색은 xlRefresh 가 className 을 새로 매기므로 그 끝에서도 부른다
  const model = wrap._model, box = wrap.querySelector(".xl-refs");
  if (!box) return;
  if (live !== undefined) wrap._refLive = live;
  for (const td of wrap.querySelectorAll("td.ref")) {
    td.classList.remove("ref", ...Array.from({ length: XL_REF_COLORS }, (_, i) => `r${i}`));
    for (const p of ["--rt", "--rr", "--rb", "--rl"]) td.style.removeProperty(p);
  }
  const saved = model.sel ? model.formulas.get(model.sel) || "" : "";
  const typing = wrap._refLive != null;
  const ls = model.sel && !typing ? xlLlmState(model, model.sel) : null; // 고른 칸에 걸린 LLM 제안
  const preview = !!ls && ls.state === "new"; // 수식이 없던 칸의 제안 — 제안 수식이 가리키는 칸을 미리 보인다
  const text = typing ? String(wrap._refLive) : preview ? ls.p.formula : saved;
  const groups = text.trim().startsWith("=") ? xlRefGroups(model, text) : [];
  box.textContent = "";
  box.scrollLeft = 0;
  if (ls) box.append(xlLlmChip(wrap, model.sel, ls)); // 맨 앞 — 참조 표지가 많아도 「적용」·「무시」 가 가려지지 않게
  if (!groups.length) {
    if (!ls) box.append(el("span", "muted", text.trim().startsWith("=") ? "이 수식은 다른 칸을 참조하지 않습니다" : "수식 칸을 고르면 참조한 칸을 색으로 표시합니다"));
    return;
  }
  const byRef = new Map([...wrap.querySelectorAll("td[data-ref]")].map((td) => [td.dataset.ref, td]));
  const taken = new Set(); // 두 묶음에 다 든 칸은 먼저 나온 묶음의 색
  box.append(el("span", "xl-refs-h", preview ? `${model.sel} 제안 수식의 참조` : `${model.sel} 참조`));
  groups.forEach((g, i) => {
    const k = i % XL_REF_COLORS, set = new Set(g.cells.map((c) => c.ref));
    const inSet = (r, c) => { const x = model.occ.get(`${r},${c}`); return !!x && set.has(x.ref); };
    for (const c of g.cells) {
      const td = byRef.get(c.ref);
      if (!td || taken.has(c.ref)) continue;
      taken.add(c.ref);
      const cols = Array.from({ length: c.cs }, (_, d) => c.col + d), rows = Array.from({ length: c.rs }, (_, d) => c.row + d);
      td.classList.add("ref", `r${k}`);
      // 묶음 바깥 변에만 테두리 — 이웃 칸이 같은 묶음이면 그 변은 0(범위 하나가 한 테두리로 보이게)
      td.style.setProperty("--rt", cols.every((x) => inSet(c.row - 1, x)) ? "0px" : "2px");
      td.style.setProperty("--rb", cols.every((x) => inSet(c.row + c.rs, x)) ? "0px" : "2px");
      td.style.setProperty("--rl", rows.every((y) => inSet(y, c.col - 1)) ? "0px" : "2px");
      td.style.setProperty("--rr", rows.every((y) => inSet(y, c.col + c.cs)) ? "0px" : "2px");
    }
    const name = xlRefName(model, g.cells), shown = g.cells.some((c) => byRef.has(c.ref));
    const chip = el("button", `xl-ref r${k}${shown ? "" : " out"}`);
    chip.type = "button";
    chip.append(el("i"), el("b", null, g.text));
    if (name) chip.append(el("span", null, short(name, 14)));
    chip.title = `${g.text}${name ? ` — ${name}` : ""} · 칸 ${nf(g.cells.length)}${!g.cells.length ? " · 표에 없는 주소" : shown ? "\n누르면 그 칸으로" : " · 보이는 범위 밖"}`;
    chip.onclick = () => {
      const td = g.cells.map((c) => byRef.get(c.ref)).find(Boolean);
      if (td) td.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
      wrap.focus({ preventScroll: true });
    };
    box.append(chip);
  });
  const fb = model.sel ? model.fById.get(model.sel) : null;
  if (fb && fb.note && text === saved && model.base.get(model.sel) === saved) box.append(el("span", "muted xl-refs-note", `판정 근거 — ${fb.note}`));
  if (!typing && !ls && saved && model.llm.has(model.sel)) box.append(el("span", "muted xl-refs-note", "LLM 도 같은 수식"));
}

const xlNameOf = (model, cid) => { const c = (model.t3 && model.t3.cells || []).find((x) => x.id === cid); return c ? (oneLine(c.text) || "(빈 칸)") : cid; };

function xlSelect(wrap, ref) {
  const model = wrap._model;
  const pos = xlRefPos(ref), c = pos ? model.occ.get(`${pos.row},${pos.col}`) : null;
  if (!c) return;
  model.sel = c.ref;
  for (const td of wrap.querySelectorAll("td.sel")) td.classList.remove("sel");
  const td = wrap.querySelector(`td[data-ref="${c.ref}"]`);
  if (td) td.classList.add("sel");
  wrap.querySelector(".xl-name").value = c.ref;
  const fx = wrap.querySelector(".xl-fx");
  fx.value = model.formulas.get(c.ref) || (model.values.has(c.ref) ? model.values.get(c.ref) : xlDocText(c));
  if (document.activeElement !== fx) wrap.focus({ preventScroll: true });
  xlRefsDraw(wrap, null); // 고른 칸의 수식이 참조한 칸 표시(치던 글은 버림)
}

function xlEdit(wrap, ref, seed = null) { // 칸 안에서 고치기 — Enter 반영(아래로) · Tab 오른쪽 · Esc 취소
  const model = wrap._model;
  xlSelect(wrap, ref);
  const c = model.occ.get(`${xlRefPos(model.sel).row},${xlRefPos(model.sel).col}`);
  const td = wrap.querySelector(`td[data-ref="${c.ref}"]`);
  if (!td || td.querySelector("input")) return;
  const inp = el("input", "xl-edit");
  inp.value = seed != null ? seed : model.formulas.get(c.ref) || (model.values.has(c.ref) ? model.values.get(c.ref) : xlDocText(c));
  inp.setAttribute("aria-label", `${c.ref} 고치기`);
  let closed = false;
  const done = (commit, move) => { // Enter·Tab·Esc·blur — 떼어 내는 중 blur 가 다시 들어와도 한 번만
    if (closed) return;
    closed = true;
    const v = inp.value;
    try { if (inp.parentNode) inp.parentNode.removeChild(inp); } catch { /* 이미 떼어짐 */ }
    if (commit) xlCommit(wrap, c.ref, v); else xlRefresh(wrap);
    const next = move === "down" ? xlStep(model, c, 1, 0) : move === "right" ? xlStep(model, c, 0, 1) : c;
    xlSelect(wrap, next.ref);
  };
  inp.onkeydown = (e) => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); done(true, "down"); }
    else if (e.key === "Tab") { e.preventDefault(); done(true, "right"); }
    else if (e.key === "Escape") { e.preventDefault(); done(false); }
  };
  inp.onblur = () => done(true);
  inp.oninput = () => xlRefsDraw(wrap, inp.value);
  td.textContent = "";
  td.append(inp);
  inp.focus();
  if (seed == null) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length);
}

function xlStep(model, c, dr, dc) { // 이웃 칸(병합 칸은 건너뜀)
  let r = c.row + (dr > 0 ? c.rs : dr), k = c.col + (dc > 0 ? c.cs : dc);
  for (let n = 0; n < 64; n += 1) {
    if (r < 0 || k < 0 || r >= model.rows || k >= model.cols) return c;
    const x = model.occ.get(`${r},${k}`);
    if (x && x !== c) return x;
    r += dr; k += dc;
  }
  return c;
}

function xlKey(wrap, e) {
  const model = wrap._model;
  if (e.target.tagName === "INPUT" || !model.sel) return;
  const c = model.occ.get(`${xlRefPos(model.sel).row},${xlRefPos(model.sel).col}`);
  if (!c) return;
  const mv = { ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1], Enter: [1, 0], Tab: [0, e.shiftKey ? -1 : 1] }[e.key];
  if (mv) { e.preventDefault(); xlSelect(wrap, xlStep(model, c, mv[0], mv[1]).ref); return; }
  if (e.key === "F2") { e.preventDefault(); xlEdit(wrap, c.ref); return; }
  if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); xlCommit(wrap, c.ref, ""); return; }
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); xlEdit(wrap, c.ref, e.key); }
}

function xlCommit(wrap, ref, raw) { // 「=」 수식(작업에 저장) · 아니면 값(반영 전까지 화면만)
  const model = wrap._model;
  raw = String(raw ?? "");
  const t = raw.trim();
  if (t.startsWith("=")) {
    model.formulas.set(ref, t);
    model.values.delete(ref);
  } else {
    model.formulas.delete(ref);
    const c = model.occ.get(`${xlRefPos(ref).row},${xlRefPos(ref).col}`);
    if (c && t === xlDocText(c)) model.values.delete(ref); else model.values.set(ref, t);
  }
  xlRefresh(wrap);
  xlPersist(wrap);
}

function xlPersist(wrap) { // 사용자 수식(§9 수식과 다른 것 · 끈 것 = "")을 작업에 저장 — 0.6초 모아서, version 이 어긋나면 새로 읽고 한 번 더
  const model = wrap._model, tid = model.tid;
  const user = {};
  const inView = (k) => { const p = xlRefPos(k), c = p ? model.occ.get(`${p.row},${p.col}`) : null; return !!c && model.inView(c); };
  if (model.range) for (const [k, v] of Object.entries(model.rec.formulas || {})) if (!inView(k)) user[k] = v; // 범위 보기 — 범위 밖 저장분(끈 수식 "" 포함)은 그대로 둔다(범위 판정의 기준 수식과 견주지 않음)
  for (const [k, v] of model.formulas) if (model.base.get(k) !== v && (!model.range || inView(k))) user[k] = v;
  for (const k of model.base.keys()) if (!model.formulas.has(k)) user[k] = "";
  clearTimeout(heads.xl.saveTimer);
  const id = state.id, epoch = state.epoch;
  heads.xl.saveTimer = setTimeout(async () => {
    const put = (version) => api(tblAgentUrl(tid), { method: "PUT", headers: H_JSON, body: JSON.stringify({ formulas: user, version }) });
    try {
      let r;
      try { r = await put(model.rec.version); }
      catch (e) {
        if (e.status !== 409) throw e;
        const cur = await api(tblAgentUrl(tid)); // 다른 화면이 먼저 저장 — 그 판 위에 쓴다
        r = await put(cur.own.version);
      }
      if (epoch !== state.epoch || id !== state.id) return;
      model.rec = r.own;
      if (heads.xl.store) heads.xl.store.tables[tid] = r.own;
      heads.xl.saving.set(tid, "ok");
    } catch (e) {
      if (epoch !== state.epoch) return;
      heads.xl.saving.set(tid, "fail");
      toast(`사용자 수식을 저장하지 못했습니다: ${e.message}`, true);
    }
    if (wrap.isConnected) xlRefresh(wrap);
  }, 600);
}

function xlPending(wrap) { // 문서에 쓸 것 — 수식 칸의 수 계산값(문서 값과 다른 것) · 고친 값. 문단 없는 칸·문단 둘 이상인 칸은 건너뜀
  const model = wrap._model, out = [];
  for (const c of model.cells) {
    if (!model.inView(c)) continue; // 범위 보기 — 보이는 칸만 쓴다
    const doc = xlDocText(c);
    let text = null;
    if (model.formulas.has(c.ref)) {
      const v = model.res.get(c.ref);
      if (xlIsErr(v) || typeof v !== "number") continue;
      const dn = xlNum(doc);
      if (dn && Math.abs(dn.v - v) <= 0.5 * 10 ** -(oneLine(doc).match(/\.(\d+)/) ? RegExp.$1.length : 0) + 1e-9) continue;
      text = xlFmt(v, doc);
    } else if (model.values.has(c.ref) && model.values.get(c.ref) !== doc) text = model.values.get(c.ref);
    else continue;
    const pids = c.paras.filter((id) => id in state.texts);
    if (pids.length !== 1) { out.push({ cell: c, text, skip: pids.length ? "문단이 둘 이상" : "문단 없음" }); continue; }
    if (oneLine(state.texts[pids[0]]).trim() === text) continue;
    out.push({ cell: c, pid: pids[0], text });
  }
  return out;
}

async function xlWriteBack(wrap) {
  const model = wrap._model, all = xlPending(wrap), todo = all.filter((x) => !x.skip), skip = all.filter((x) => x.skip);
  if (!todo.length) { toast(skip.length ? `쓸 수 있는 칸이 없습니다(${skip.map((x) => `${x.cell.ref} ${x.skip}`).join(", ")})` : "문서에 쓸 값이 없습니다(계산값이 문서 값과 같음)"); return; }
  const list = todo.slice(0, 8).map((x) => `${x.cell.ref}: 「${oneLine(state.texts[x.pid]) || "(빈 칸)"}」 → 「${x.text}」`).join("\n");
  if (!confirm(`${todo.length}개 칸의 글을 문서에 씁니다(기존 글을 바꿈 — 되돌리기·실행 취소로 돌릴 수 있음).\n${list}${todo.length > 8 ? "\n…" : ""}${skip.length ? `\n건너뜀 ${skip.length}(문단 없음·둘 이상)` : ""}\n계속할까요?`)) return;
  const id = state.id, epoch = state.epoch;
  let ok = 0, fail = 0;
  for (const x of todo) {
    try {
      const r = await api(`/api/docs/${id}/blocks/${x.pid}`, { method: "PATCH", headers: H_JSON, body: JSON.stringify({ text: x.text }) });
      if (epoch !== state.epoch) return;
      applyServer(x.pid, r);
      xlParaRefresh(wrap, x.pid, r.text, r.edited);
      model.values.delete(x.cell.ref);
      ok += 1;
    } catch (e) {
      if (epoch !== state.epoch) return;
      fail += 1;
      toast(`${x.cell.ref} 를 문서에 쓰지 못했습니다: ${e.message}`, true);
    }
  }
  state.localRev += 1;
  refreshSaveState();
  updateEdits();
  if (wrap.isConnected) xlRefresh(wrap);
  toast(`문서에 ${ok}개 칸을 썼습니다${fail ? ` · 실패 ${fail}` : ""}${skip.length ? ` · 건너뜀 ${skip.length}` : ""} — 「고친 문단」 탭에서 되돌릴 수 있습니다`, !!fail);
}

// ---- 원문 비교 · 정렬 · 엑셀로 받기(spec ② §14) ------------------------------------------------------------------------
function xlOrig(c) { // 칸의 문단 중 원문(올린 원본·마지막 확정본)과 다른 것이 있으면 원문 글, 없으면 null — app.js state.edited(고친 문단)·state.original
  if (!c.paras.some((id) => state.edited && state.edited.has(id))) return null;
  return c.paras.map((id) => oneLine(state.original[id] || "")).filter(Boolean).join(" ");
}

function xlRaw(model, c) { return model.values.has(c.ref) ? model.values.get(c.ref) : xlDocText(c); }

function xlSortBlock(model, c) {
  // 정렬할 행 묶음 {r0, r1, c0, c1} | {err} — 고른 칸이 든 서브 테이블(판정 띠)의 자료 행 중, 그 칸을 덮는 가장 작은 세로 병합 칸(「1단계」)이 묶은 행,
  // 없으면 헤더·합계·제목 행과 경계를 가르는 병합 칸에서 멈추는 이어진 자료 행. 열 = 띠 열 범위 ∩ 보이는 범위.
  const v = model.view, J = model.judge;
  const sub = J && c.s3 && c.s3.sub ? (J.subtables || []).find((s) => s.id === c.s3.sub) : null;
  const R0 = Math.max(v.r0 + (model.t3 ? 0 : 1), sub ? sub.rows[0] : v.r0), R1 = Math.min(v.r1, sub ? sub.rows[1] - 1 : v.r1); // 역할을 모르면(docx) 첫 행은 헤더로 본다
  const C0 = Math.max(v.c0, sub ? sub.cols[0] : v.c0), C1 = Math.min(v.c1, sub ? sub.cols[1] - 1 : v.c1);
  const inCols = (x) => x.col >= C0 && x.col + x.cs - 1 <= C1;
  const isTotal = (x) => x.s3 && ((x.s3.basis || []).includes("total") || x.s3.basisKind === "total");
  const dataRow = (r) => {
    let field = false;
    for (const x of model.cells) {
      if (!inCols(x) || r < x.row || r > x.row + x.rs - 1) continue;
      if (x.row === r && ["colhead", "corner", "title", "note", "spacer"].includes(x.role)) return false;
      if (x.role === "rowhead" && isTotal(x)) return false; // 합계·소계 행
      if (x.row === r && (x.role === "field" || !x.role)) field = true;
    }
    return field;
  };
  if (c.row < R0 || c.row > R1 || !inCols(c)) return { err: "고른 칸이 정렬할 표 범위 밖입니다" };
  if (!dataRow(c.row)) return { err: "헤더·합계 행은 정렬 기준이 될 수 없습니다 — 자료 칸을 고르세요" };
  let r0 = c.row, r1 = c.row;
  const group = model.cells.filter((x) => inCols(x) && x.rs > 1 && x.row <= c.row && c.row <= x.row + x.rs - 1 && x !== c && x.col < c.col)
    .sort((a, b) => a.rs - b.rs)[0]; // 고른 칸 왼쪽의 가장 작은 세로 병합(「1단계」 가 묶은 1~3차년도)
  if (group) { r0 = Math.max(R0, group.row); r1 = Math.min(R1, group.row + group.rs - 1); }
  else {
    const crosses = (r) => model.cells.some((x) => inCols(x) && x.rs > 1 && x.row < r && r <= x.row + x.rs - 1); // r 위 경계를 가르는 병합 칸
    while (r0 - 1 >= R0 && dataRow(r0 - 1) && !crosses(r0)) r0 -= 1;
    while (r1 + 1 <= R1 && dataRow(r1 + 1) && !crosses(r1 + 1)) r1 += 1;
  }
  for (let r = r0; r <= r1; r += 1) if (!dataRow(r)) { if (r < c.row) r0 = r + 1; else { r1 = r - 1; break; } }
  if (r1 - r0 < 1) return { err: "정렬할 자료 행이 둘 이상 이어져 있지 않습니다" };
  for (const x of model.cells) { // 묶음 안을 가르는 세로 병합 칸은 정렬 불가(엑셀과 같음) — 묶음 전체를 덮는 칸은 제자리
    if (!inCols(x) || x.rs < 2) continue;
    const a = x.row, b = x.row + x.rs - 1;
    if (b < r0 || a > r1) continue;
    if (!(a <= r0 && b >= r1)) return { err: `병합 칸 ${x.ref}(${x.rs}행)이 정렬할 행(${r0 + 1}~${r1 + 1})에 걸쳐 있어 정렬할 수 없습니다` };
  }
  return { r0, r1, c0: C0, c1: C1 };
}

function xlSort(wrap, dir) {
  const model = wrap._model;
  if (!model.sel) { toast("정렬 기준 칸(열)을 먼저 누르세요"); return; }
  const pos = xlRefPos(model.sel), key = pos ? model.occ.get(`${pos.row},${pos.col}`) : null;
  if (!key) return;
  const blk = xlSortBlock(model, key);
  if (blk.err) { toast(blk.err, true); return; }
  const rows = [];
  for (let r = blk.r0; r <= blk.r1; r += 1) {
    const cs = model.cells.filter((x) => x.row === r && x.rs === 1 && x.col >= blk.c0 && x.col + x.cs - 1 <= blk.c1).sort((a, b) => a.col - b.col);
    rows.push({ r, cells: cs, sig: cs.map((x) => `${x.col}:${x.cs}:${model.formulas.has(x.ref) ? "f" : ""}`).join(",") });
  }
  if (rows.some((x) => x.sig !== rows[0].sig)) { toast("행마다 칸 나눔(병합)·수식 자리가 달라 정렬할 수 없습니다", true); return; }
  const k = rows[0].cells.findIndex((x) => x.col <= key.col && key.col <= x.col + x.cs - 1);
  if (k < 0) { toast("정렬 기준 열이 행마다 같은 칸이 아닙니다", true); return; }
  const val = (x) => { // 정렬 값 — 수식 칸은 계산값, 아니면 지금 값(고친 값 · 문서 글)의 수 또는 글, 빈 칸 null
    if (model.formulas.has(x.ref)) { const v = model.res.get(x.ref); return typeof v === "number" ? v : v == null || xlIsErr(v) ? null : String(v); }
    const s = oneLine(xlRaw(model, x)).trim();
    if (!s || xlIsPh(s)) return null;
    const n = xlNum(s);
    return n ? n.v : s;
  };
  const cmp = (a, b) => {
    if (a == null || b == null) return a == null && b == null ? 0 : a == null ? 1 : -1; // 빈 칸은 늘 끝
    if (typeof a === "number" && typeof b === "number") return dir * (a - b);
    if (typeof a === "number") return -1; // 수 먼저, 글 다음(엑셀 오름차순과 같음 — 내림차순이어도 수가 앞)
    if (typeof b === "number") return 1;
    return dir * a.localeCompare(b, "ko", { numeric: true });
  };
  const order = rows.map((x, i) => ({ i, v: val(x.cells[k]) })).sort((a, b) => cmp(a.v, b.v) || a.i - b.i).map((x) => x.i);
  if (order.every((x, i) => x === i)) { toast("이미 그 순서입니다"); return; }
  const texts = rows.map((x) => x.cells.map((y) => (model.formulas.has(y.ref) ? null : xlRaw(model, y))));
  const undo = new Map();
  rows.forEach((row, i) => row.cells.forEach((y, j) => {
    if (model.formulas.has(y.ref)) return; // 수식 칸은 제자리에서 다시 계산(같은 행을 가리키는 행 합계는 그대로 맞음)
    undo.set(y.ref, model.values.has(y.ref) ? model.values.get(y.ref) : undefined);
    const t = texts[order[i]][j];
    if (t === xlDocText(y)) model.values.delete(y.ref); else model.values.set(y.ref, t);
  }));
  model.undo = undo;
  xlRefresh(wrap);
  toast(`${blk.r0 + 1}~${blk.r1 + 1}행(${rows.length}행)을 ${colLetter(key.col)}열 기준 ${dir > 0 ? "오름차순" : "내림차순"}으로 정렬 — 「문서에 반영」 을 눌러야 문서가 바뀝니다`);
}

function xlSortUndo(wrap) {
  const model = wrap._model;
  if (!model.undo) return;
  for (const [ref, v] of model.undo) { if (v === undefined) model.values.delete(ref); else model.values.set(ref, v); }
  model.undo = null;
  xlRefresh(wrap);
}

async function xlDownload(wrap) { // 이 격자 그대로 .xlsx(서버 openpyxl — POST …/excel/xlsx)
  const model = wrap._model, cells = [];
  for (const c of model.cells) {
    if (!model.inView(c)) continue;
    const f = model.formulas.get(c.ref), doc = xlDocText(c), raw = f ? null : xlRaw(model, c), n = raw != null ? xlNum(raw) : null, v = f ? model.res.get(c.ref) : null;
    const orig = xlOrig(c);
    cells.push({ ref: c.ref, row: c.row, col: c.col, rs: c.rs, cs: c.cs, role: c.role || null, value: raw != null ? oneLine(raw) : null,
      num: n && !n.dash ? n.v : n && n.dash ? 0 : null, pct: !!(n && n.pct), grouped: !!(raw && /\d,\d{3}/.test(raw)),
      formula: f || null, calc: typeof v === "number" ? v : null, status: f ? model.status.get(c.ref) || "" : null, doc: f ? doc : null,
      input: model.inputs.has(c.ref), orig: orig != null, origText: orig });
  }
  const body = { range: model.range, rows: model.rows, cols: model.cols, unit: model.judge ? model.judge.unit : null, cells };
  try {
    const r = await fetch(`/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(model.tid)}/excel/xlsx`, { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
    if (!r.ok) { let m = `${r.status}`; try { m = (await r.json()).detail || m; } catch { /* 글 아님 */ } throw new Error(m); }
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "", m = /filename\*=UTF-8''([^;]+)/.exec(cd);
    const a = el("a");
    a.href = URL.createObjectURL(blob);
    a.download = m ? decodeURIComponent(m[1]) : `${model.tid}.xlsx`;
    document.body.append(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  } catch (e) { toast(`엑셀 파일을 만들지 못했습니다: ${e.message}`, true); }
}

function xlParaRefresh(wrap, pid, text, edited) { // 떼어 둔 원래 표(조각)의 그 문단을 새 글로 — 2열 격자면 문서의 살아 있는 문단을
  const roots = (wrap._frags || []).length ? wrap._frags : [$("doc")];
  for (const f of roots) {
    const p = f.querySelector(`.para[data-id="${CSS.escape(pid)}"]`);
    if (!p) continue;
    const b = state.byId.get(pid);
    if (b) p.replaceWith(renderPara(b, text)); else { p.textContent = ""; p.append(el("span", null, text)); }
    const q = f.querySelector(`.para[data-id="${CSS.escape(pid)}"]`);
    if (q) q.classList.toggle("edited", !!edited);
  }
}

// ---- 표 지침(표 에이전트 입력) 2열 --------------------------------------------------------------------------------------
function tblAgentLeave() { // 열을 닫을 때 — 저장 안 한 지침 글이 있으면 묻는다
  const a = heads.xl.agent;
  if (!a || heads.dlg !== "tableAgent" || !a.dirty()) return true;
  return confirm("저장하지 않은 표 지침이 있습니다. 버릴까요?");
}

async function tblAgentView(tid) {
  if (!state.id) return;
  const isCommon = tid === "_common"; // 공통 지침만(「표」 탭의 「공통 지침」)
  // 작성요령의 세 묶음(spec ② §18 — 사용자 2026-11-12 "작성요령에는 문서에서 제공하는 작성요령, 다른 지침에서 제공하는 작성가이드라인도 있지만 셀에 값을 넣는 방식이나 규칙도"):
  // ① 문서의 작성요령(표 안·앞뒤 안내 + 뒤따르는 「작성 요령」 표) ② 지침(양식·공통·이 표 — 무엇을 적는가) ③ 칸 입력 규칙(기본·공통·이 표 — 어떻게 적는가)
  const { tools, body } = headsDlg("tableAgent", isCommon ? "공통 표 지침" : `작성요령 · 표 지침 · ${tid}`,
    isCommon ? "이 문서의 모든 표에 적용하는 작성 기준" : "지침과 입력 규칙을 저장해 표 채우기에 활용합니다");
  const seq = heads.seq, id = state.id, epoch = state.epoch;
  hFoot("읽는 중…", false);
  let a;
  try { a = await api(tblAgentUrl(tid)); }
  catch (e) { if (seq === heads.seq && epoch === state.epoch) hFoot(`표 지침을 읽지 못했습니다: ${e.message}`); return; }
  if (seq !== heads.seq || epoch !== state.epoch) return;
  await xlStore();
  if (seq !== heads.seq || epoch !== state.epoch) return;
  const wrap = el("div", "ta-wrap ta-editor"), context = el("div", "ta-context"), owner = el("div", "ta-owner-row");
  const ident = el("div", "ta-ident");
  const t = a.ident;
  if (!isCommon) ident.append(el("b", null, tid));
  if (t) {
    ident.append(el("span", null, `${t.rows}×${t.cols} · 칸 ${nf(t.cells)}${t.depth > 1 ? " · 표 안 표" : ""}`));
    const o = t.owner;
    if (o && !o.root) {
      owner.append(el("span", "muted", "소속"), hasBlock(o.para) ? hBtn(ownerLabel(o), () => headsGo(o.para), { title: (o.path || []).concat([o.text]).join(" › ") || "문서의 그 헤딩으로" }) : el("b", null, ownerLabel(o)));
      if ((o.path || []).length) { const path = el("span", "ta-owner-path", o.path.join(" › ")); path.title = path.textContent; owner.append(path); }
      if (o.division) owner.append(dvTag(el("span", "hb div", `구분 라벨 ${o.division.text}`), dvOfDivision(o.division)));
    } else owner.append(el("span", "muted", o && o.root ? "소속: 문서 뿌리(위에 헤딩 없음)" : "소속: 모름"));
    if ((t.basis || []).length) ident.append(el("span", "hb", `구분 ${basisNames(t.basis)}`));
    if (t.unit) ident.append(el("span", "hb", `단위 ${t.unit}`));
    if (t.calc && t.calc.is) ident.append(el("span", "hb", `수식 ${nf(t.calc.formulas)}${t.calc.mismatch ? ` · 불일치 ${nf(t.calc.mismatch)}` : ""}`));
    if (t.before) owner.append(hHelp("표 앞 문단", t.before));
  }
  if (!isCommon) { context.append(ident, owner); wrap.append(context); }
  const acts = el("div", "ta-row ta-actions");
  if (t && t.host && hasBlock(t.host)) acts.append(hBtn("표 자리로", () => headsGo(t.host), { title: "문서에서 이 표를 품은 문단으로" }));
  if (t) acts.append(hBtn("격자(표 보기)", () => { if (tblAgentLeave()) headsTables(tid); }, { title: "칸 역할 격자 · 수식 검증 · 필드 목록" }));
  if (!isCommon) acts.append(hBtn("엑셀식 보기", () => { if (tblAgentLeave()) xlColumn(tid); }, { title: "이 열에 A1 격자(수식 계산 · 문서에 반영)" }));
  if (!isCommon && state.format !== "docx" && typeof tblFillView === "function") acts.append(hBtn("에이전트로 표 채우기", () => { if (tblAgentLeave()) tblFillView(tid); /* 저장 안 한 지침·규칙이 있으면 먼저 묻는다 — 채우기에는 저장된 글만 간다 */ }, { cls: "btn sm primary", title: "이 작성요령·지침·칸 입력 규칙에 맞춰 빈 칸에 넣을 값을 LLM 이 제안합니다 — 고른 것만 문서에 들어갑니다" }));
  if (!isCommon && !a.stage3 && state.format !== "docx") acts.append(hBtn("표 구조 만들기(스크립트)", () => { if (tblAgentLeave()) headsStart(3, false); }, { title: "3단계 표 구조를 만들면 소속·작성요령·구조·수식이 채워집니다" }));
  if (!isCommon) context.append(acts);
  if (!isCommon && !a.stage3) context.append(el("p", "hnote", state.format === "docx" ? "DOCX 문서는 지침과 규칙을 저장할 수 있습니다." : "표 구조 분석 전입니다. 작성요령과 지침은 지금도 사용할 수 있습니다."));
  const guideKeep = (n) => { // 「작성 요령」 표의 글을 이 표 지침에 — 작성 요령 표는 제출 전에 지우는 표라, 붙여 두면 표를 지운 뒤에도 남는다(저장은 사람이)
    const add = `[${n.title || "작성 요령"}]\n${n.text || ""}`.trim();
    if (n.text && own.ta.value.includes(n.text)) { toast("이미 이 표 지침에 들어 있습니다"); return; }
    own.ta.value = (own.ta.value.trim() ? `${own.ta.value.trim()}\n\n` : "") + add;
    own.ta.oninput();
    selectSection("instructions");
    own.ta.scrollIntoView({ block: "nearest" });
    own.ta.focus({ preventScroll: true });
    toast("이 표 지침에 붙였습니다 — 「저장」 을 눌러야 남습니다");
  };
  const source = el("details", "ta-source");
  source.open = !!(a.notes || []).length && !(a.notes || []).some((n) => n.where === "guide" || (n.text || "").length > 180) && a.notes.length <= 2;
  if (!isCommon) {
    source.append(el("summary", "ta-group", `① 문서의 작성요령 ${nf((a.notes || []).length)}`));
    wrap.append(source);
  }
  if (isCommon) { /* 공통 — 작성요령 없음 */ } else if ((a.notes || []).length) {
    const ul = el("ul", "ta-notes");
    const WHERE = { before: "표 앞", cell: "표 안", after: "표 뒤", guide: "작성 요령 표" };
    for (const n of a.notes) {
      const li = el("li");
      li.append(el("span", "hb", WHERE[n.where] || n.where));
      if (n.where === "guide") { // 뒤따르는 「작성 요령」 표(spec ② §18) — 항목 줄 그대로
        const box = el("div", "ta-guide"), head = el("div", "ta-row");
        head.append(n.para && hasBlock(n.para) ? headsParaLink(n.para, n.title || "작성 요령", 60, `표 ${n.table}`) : el("b", null, short(n.title || "작성 요령", 60)),
          hBtn("이 표 지침에 붙이기", () => guideKeep(n), { title: "「작성 요령」 표는 제출 전에 지우는 표입니다 — 이 표 지침에 붙여 두면 표를 지운 뒤에도 요령이 남습니다(붙인 뒤 「저장」)" }));
        box.append(head, el("pre", "ta-prompt", n.text || ""));
        li.classList.add("guide");
        li.append(box);
      } else if (n.para && hasBlock(n.para)) li.append(headsParaLink(n.para, n.text, 160, n.cell ? `칸 ${n.cell}` : ""));
      else li.append(el("span", null, short(n.text, 160)));
      ul.append(li);
    }
    source.append(ul);
  } else source.append(el("p", "hnote", "문서에서 찾은 작성요령이 없습니다. 필요한 내용은 「이 표 지침」에 적으세요."));
  if (!isCommon && (a.saved || []).length) { // 저장해 둔 문서 지침(spec_병합 ② §5-11 — 작업에 저장한 작성 지침 가운데 이 표의 것: 4단계 「작성요령 삭제」 뒤에도 남고 3단계 LLM 이 이 표를 볼 때 읽는다) — 읽기만
    const kept = el("details", "ta-source ta-saved"), ul = el("ul", "ta-notes");
    kept.open = a.saved.length <= 2 && !a.saved.some((g) => (g.text || "").length > 180);
    kept.append(el("summary", "ta-group", `저장해 둔 문서 지침 ${nf(a.saved.length)}`));
    for (const g of a.saved) {
      const li = el("li"), text = g.label ? `${short(g.label, 60)} → ${g.text || ""}` : g.text || "", t = el("span", null, text.length > 600 ? text.slice(0, 600) + " …" : text);
      t.style.whiteSpace = "pre-wrap";
      if (text.length > 600) t.title = text;
      li.append(el("span", "hb", g.kind || "지침"), t);
      if (g.cell) li.title = `표 안의 칸(${g.cell})에 든 지침`;
      ul.append(li);
    }
    kept.append(ul, el("p", "hnote", "작업에 저장해 둔 것입니다 — 문서에서 작성요령을 지워도 남고, 3단계 LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 이 표를 볼 때 읽습니다."));
    wrap.append(kept);
  }
  // 두 탭은 같은 DOM을 유지한다 — 탭을 옮겨도 초안·저장 상태가 사라지지 않는다.
  const tabs = el("div", "ta-editor-tabs"), sections = {}, tabButtons = {}, tabDirty = {};
  tabs.setAttribute("role", "tablist"); tabs.setAttribute("aria-label", "표 작성 기준");
  const selectSection = (key, focus = false) => {
    for (const k of Object.keys(sections)) {
      sections[k].hidden = k !== key;
      tabButtons[k].setAttribute("aria-selected", String(k === key));
      tabButtons[k].tabIndex = k === key ? 0 : -1;
    }
    body.scrollTop = 0;
    if (focus) tabButtons[key].focus();
  };
  for (const [key, title] of [["instructions", "작성 지침"], ["rules", "칸 입력 규칙"]]) {
    const section = el("section", "ta-section"), button = el("button"), dirty = el("span", "ta-tab-dirty");
    section.dataset.taSection = button.dataset.taTab = key;
    section.id = `ta-section-${seq}-${key}`; button.id = `ta-tab-${seq}-${key}`;
    section.setAttribute("role", "tabpanel"); section.setAttribute("aria-labelledby", button.id);
    button.type = "button"; button.setAttribute("role", "tab"); button.setAttribute("aria-controls", section.id);
    button.onclick = () => selectSection(key);
    button.onkeydown = (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      selectSection(e.key === "Home" ? "instructions" : e.key === "End" ? "rules" : key === "instructions" ? "rules" : "instructions", true);
    };
    dirty.hidden = true; button.append(el("span", null, title), dirty); tabs.append(button);
    sections[key] = section; tabButtons[key] = button; tabDirty[key] = dirty;
    wrap.append(section);
  }
  const area = (title, rec, placeholder, field, scope) => { // 같은 기록(version 하나)의 instructions/rules를 따로 저장한다.
    const box = el("div", "ta-field"), head = el("div", "ta-field-head"), heading = el("h3"), label = el("label", null, title);
    box.dataset.taScope = scope; box.dataset.taField = field;
    const ta = el("textarea");
    ta.id = `ta-${seq}-${scope}-${field}`; label.htmlFor = ta.id;
    ta.value = rec[field] || "";
    ta.defaultValue = ta.value;
    ta.placeholder = placeholder;
    ta.rows = scope === "own" && field === "instructions" ? 4 : 3;
    const range = el("span", "ta-scope", scope === "common" ? "문서 전체" : "이 표만");
    range.id = `${ta.id}-scope`; range.title = scope === "common" ? "이 문서의 모든 표에 적용합니다" : "지금 선택한 표에만 적용합니다";
    ta.setAttribute("aria-describedby", range.id);
    heading.append(label); head.append(heading, range);
    const row = el("div", "ta-row ta-field-actions"), st = el("span", "ta-save-state");
    st.setAttribute("role", "status");
    box.append(head, ta, row); sections[field].append(box);
    return { box, ta, row, st, field, error: "", saving: false, saved: false };
  };
  sections.instructions.append(el("div", "ta-group", "② 지침 — 무엇을 적는가"));
  { // 양식 지침 — 양식 정보(forms/<양식>.md)의 「표」 절: 이 양식의 모든 문서에 공통(spec_헤딩_추출 ② §12). 여기서는 보기만 — 고치기는 양식 정보 편집기
    const row = el("div", "ta-form-row"), form = el("details", "ta-form-note"), summary = el("summary");
    summary.append(el("h3", null, "양식 지침"), el("span", "ta-scope", "양식 전체"), el("span", "muted", a.form ? "등록됨" : "없음"));
    form.append(summary);
    if (a.form) form.append(el("pre", "ta-prompt", a.form));
    else form.append(el("p", "hnote", "같은 양식의 모든 문서에 쓸 지침은 양식 정보의 「표」 절에 적으세요."));
    row.append(form);
    if (typeof divFormOpen === "function") {
      row.append(hBtn("양식 정보 열기", () => divFormOpen(), { title: "같은 양식의 모든 문서에 쓰는 지침을 보고 고칩니다" }));
    }
    sections.instructions.append(row);
  }
  const common = area("공통 지침", a.common, "예: 금액은 천원 단위, 합계는 행·열 모두 검산", "instructions", "common");
  const own = isCommon ? null : area("이 표 지침", a.own, "예: 1차년도는 2026년, 기관부담 현물은 인건비만", "instructions", "own");
  // ③ 칸 입력 규칙 — 칸에 값을 넣는 방식(spec ② §18): 앱 기본 규칙(늘 함께 감 — 보기만) → 공통 규칙 → 이 표 규칙(어긋나면 뒤의 것이 우선) + 표에서 읽은 칸 꼴
  sections.rules.append(el("div", "ta-group", "③ 칸 입력 규칙 — 칸에 값을 어떻게 넣는가"));
  if (a.forms) {
    const p = el("p", "hnote ta-rules-summary", `표에서 읽은 칸 꼴 — ${a.forms.text || "채우는 필드 없음"} · 채우는 필드 ${nf(a.forms.fields)}개 가운데 빈 자리 ${nf(a.forms.open)}개`);
    p.title = "칸 글에서 읽은 「값을 넣는 방식」 — 체크 = 「[ ]」·「□」 · 날짜 = 「YYYY.MM.DD」·「20  년  월  일」 · 수 = 「0,000」 · 비율 = 「00%」 · 글 자리표시 = 「○○」·「제20xx-xx호」\n빈 자리 = 글 없음 · 자리표시뿐 · 표시 없는 체크 칸 · 숫자가 빠진 날짜(「표 채우기」 가 채우는 칸)";
    sections.rules.append(p);
  }
  {
    const dr = el("details", "more hblock ta-default-rules"), summary = el("summary", null, "기본 규칙(앱)");
    summary.append(hHelp("기본 규칙 적용 범위", "모든 문서의 표 채우기에 함께 적용합니다. 공통 규칙이나 이 표 규칙과 다르면 직접 적은 규칙을 우선합니다."));
    dr.append(summary, el("pre", "ta-prompt", a.rulesDefault || ""));
    sections.rules.append(dr);
  }
  const crule = area("공통 규칙", a.common, "예: 날짜는 YYYY.MM.DD, 해당 없는 칸은 「-」", "rules", "common");
  const orule = isCommon ? null : area("이 표 규칙", a.own, "예: 체크는 「[ √ ]」, 비율은 정수 %로 입력", "rules", "own");
  const pre = el("pre", "ta-prompt", a.prompt || "");
  const WHAT = { instructions: "지침", rules: "칸 입력 규칙" };
  let saving = false;
  const save = async (kind, w) => { // w = area() 가 돌려준 글상자 — w.field 만 보낸다(같은 기록의 다른 글은 그대로)
    if (saving || w.ta.value === w.ta.defaultValue) { syncFields(); return; }
    const target = kind === "common" ? "_common" : tid, rec = kind === "common" ? a.common : a.own, text = w.ta.value;
    saving = w.saving = true; w.error = ""; syncFields();
    try {
      const r = await api(tblAgentUrl(target), { method: "PUT", headers: H_JSON, body: JSON.stringify({ [w.field]: text, version: rec.version }) });
      if (seq !== heads.seq || epoch !== state.epoch) return;
      a.common = r.common; a.own = kind === "common" ? a.own : r.own; a.prompt = r.prompt;
      // 응답을 기다리며 더 적은 글은 초안으로 남긴다. 서버에 보낸 글만 저장된 기준이다.
      w.ta.defaultValue = text; w.saved = true;
      pre.textContent = a.prompt || "";
      await xlStore(true);
      tblMarksDraw();
      toast(kind === "common" ? `공통 표 ${WHAT[w.field]}을 저장했습니다` : `표 ${tid} ${WHAT[w.field]}을 저장했습니다`);
    } catch (e) {
      if (seq !== heads.seq || epoch !== state.epoch) return;
      w.error = e.status === 409 ? "다른 화면이 먼저 저장 — 열을 다시 열어 확인하세요" : `저장 실패: ${e.message}`;
      toast(e.status === 409 ? "표 지침이 다른 곳에서 바뀌었습니다 — 열을 다시 여세요" : `표 ${WHAT[w.field]}을 저장하지 못했습니다: ${e.message}`, true);
    } finally {
      saving = w.saving = false;
      if (seq === heads.seq && epoch === state.epoch) syncFields();
    }
  };
  const boxes = [["common", common], ["common", crule], ...(isCommon ? [] : [["own", own], ["own", orule]])];
  const syncFields = () => {
    for (const [kind, w] of boxes) {
      const rec = kind === "common" ? a.common : a.own, dirty = w.ta.value !== w.ta.defaultValue;
      w.box.dataset.dirty = String(dirty);
      w.save.disabled = saving || !dirty;
      w.clear.disabled = saving || !w.ta.value;
      w.st.dataset.state = w.saving ? "saving" : w.error ? "error" : dirty ? "dirty" : w.saved || (rec.updated && w.ta.defaultValue) ? "saved" : "clean";
      w.st.textContent = w.saving ? "저장 중…" : w.error || (dirty ? "저장 안 함" : w.st.dataset.state === "saved" ? `저장됨 · v${rec.version}` : `저장된 ${w.field === "rules" ? "규칙" : "지침"} 없음`);
      w.st.title = rec.updated ? `마지막 저장 ${fmtWhen(rec.updated)}` : "";
    }
    for (const key of Object.keys(tabDirty)) {
      const n = boxes.filter(([, w]) => w.field === key && w.ta.value !== w.ta.defaultValue).length;
      tabDirty[key].hidden = !n;
      tabDirty[key].textContent = n ? `수정 ${n}` : "";
    }
  };
  for (const [kind, w] of boxes) {
    w.save = hBtn("저장", () => save(kind, w), { cls: "btn sm primary" });
    w.clear = hBtn("지우기", () => { w.ta.value = ""; w.error = ""; save(kind, w); }, { title: `${WHAT[w.field]}을 빈 글로 저장` });
    w.save.dataset.taAction = "save"; w.clear.dataset.taAction = "clear";
    w.row.append(w.save, w.clear, w.st);
    w.ta.oninput = () => { w.error = ""; syncFields(); };
  }
  syncFields(); selectSection("instructions");
  const d = el("details", "more hblock ta-preview");
  d.append(el("summary", null, "에이전트 입력 미리보기"), pre);
  wrap.append(d);
  body.append(wrap);
  heads.xl.agent = { tid, dirty: () => boxes.some(([, w]) => w.ta.value !== w.ta.defaultValue) };
  tools.append(tabs, hHelp("표 지침 안내", "지침과 칸 입력 규칙은 이 작업(문서)에 저장됩니다.\n표 채우기는 작성요령·지침·칸 입력 규칙을 모두 사용하고, LLM 수식 판정과 표 만들기는 지침을 함께 받습니다.\n저장한 내용은 다음 제안부터 적용됩니다."));
  hFoot(isCommon ? `공통 v${a.common.version}` : `표 ${tid}${a.stage3 ? "" : " · 3단계 없음"} · 공통 v${a.common.version} · 이 표 v${a.own.version}`, false);
}

// ---- 「표」 탭(3열 pane #paneTables — spec_헤딩_추출 ② §10 「모듈」) : 문서의 표 목록과 표 도구의 입구. 본문 분석(「헤딩 추출」 탭)과 따로 둔다(사용자 2026-11-10 "본문 따로, 테이블 따로").
function xlBlocks(blocks = state.blocks || [], depth = 1, out = []) { // 문서 순 표 블록(칸 안 표 포함) [{id, rows, cols, depth, cells}]
  for (const b of blocks) {
    if (b.type === "table") {
      out.push({ id: b.id, rows: b.nRows || Math.max(0, ...(b.cells || []).map((c) => c.row + (c.rowSpan || 1))), cols: b.nCols || Math.max(0, ...(b.cells || []).map((c) => c.col + (c.colSpan || 1))),
        depth, cells: (b.cells || []).length });
      for (const c of b.cells || []) xlBlocks(c.blocks || [], depth + 1, out);
    }
  }
  return out;
}

function tablesReset() { // 문서를 열거나 닫을 때(app.js load·closeDoc 의 divReset 옆)
  const tab = $("tabTables");
  if (tab) tab.hidden = !state.id;
  const box = $("tablesBox");
  if (box) box.textContent = "";
  tpView = "List"; // 하위 탭은 문서를 열 때마다 「표 목록」 부터
  tpKinds.key = tpKinds.map = tpKinds.wait = null;
  if (typeof tblTypesReset === "function") tblTypesReset(); // 양식의 표 판정 표지(table_types.js — spec_테이블매니저 ② §10 「양식의 표 판정」)
  if (typeof ftReset === "function") ftReset(); // 양식의 표 등록부 줄 · 「양식 표」 꼬리표(form_tables.js — spec_테이블매니저 ② §11)
}

async function tablesShow() { // 탭을 열 때 — 3단계 요약(heads.view)이 없으면 헤딩 상태를 읽고(1단계 자동 — 헤딩 추출 탭과 같음), 저장된 지침을 읽은 뒤 그린다
  if (!state.id) return;
  const epoch = state.epoch;
  if (state.format !== "docx" && !heads.view) await headsShow();
  if (epoch !== state.epoch) return;
  await xlStore();
  if (epoch !== state.epoch) return;
  tablesDraw();
  tpKindsLoad(true); // 병합 방식 표지 — 탭을 열 때마다 다시 읽는다(편집 구역 · 프로젝트 구성이 그 사이 바뀌었을 수 있다). 그려 둔 목록에 표지만 채운다
  if (typeof tblTypesLoad === "function") tblTypesLoad(true); // 양식의 표 판정 표지 「확정됨」 — 탭을 열 때마다 다시 읽는다(다른 작업에서 확정본이 생기거나 지워졌을 수 있다). 그려 둔 목록에 표지만 채운다
  if (typeof ftLoad === "function") ftLoad(true); // 양식의 표 등록부 — 탭을 열 때마다 다시 읽는다(다른 문서에서 등록부를 다시 지었을 수 있다). 그려 둔 목록에 줄 · 꼬리표만 채운다
}

// ---- 병합 방식 표지(spec_테이블매니저 ② §5 「병합 방식」) — 여러 기관의 문서를 모을 때 그 표(서브 테이블)를 어떻게 모으는 표인지: 표 목록의 줄마다 꼬리표.
// GET /api/docs/{id}/tables/kinds(app/table_kinds_api.py — 연구개발과제 문서만 · 스크립트 · 문서는 안 바뀜). 식별만 한다 — 취합 · 이관의 넣기는 그대로.
// 일반 문서(gate none) · 표 구조 없음(404) · 읽기 실패에서는 아무것도 안 보이고 알림도 띄우지 않는다. 문서가 바뀐 뒤의 낡은 결과(stale)도 그대로 보인다(다시 돌리라고 조르지 않는다 — spec_헤딩_추출 ② §17).
const TP_KIND = { perOrg: "기관마다 작성", byDivision: "구분 기준에 따라 병합", sum: "셀 값 합산", common: "공통" }; // 화면 말 = 사용자의 말 그대로(app/table_kinds.py KIND_KO 와 같다)
const tpKinds = { key: null, map: null, wait: null }; // key = 읽은 것의 열쇠(문서 · 3단계 결과) · map = Map(표 id → {kind, subs[]}) | null(해당 없음) · wait = 읽는 중인 열쇠
const tpKindsKey = () => `${state.id}|${state.epoch}|${xlStageKey()}`;
function tpKindsLoad(force = false) { // 3단계 결과가 바뀐 뒤의 첫 그리기 · 탭을 열 때(force)
  if (!state.id || state.format === "docx") return;
  const key = tpKindsKey();
  if (tpKinds.wait === key || (!force && tpKinds.key === key)) return;
  tpKinds.wait = key;
  api(`/api/docs/${encodeURIComponent(state.id)}/tables/kinds`).catch(() => null).then((v) => {
    if (tpKinds.wait !== key) return; // 그 사이 다른 문서를 열었거나 3단계 결과가 바뀌어 새로 읽는 중
    tpKinds.wait = null;
    if (key !== tpKindsKey()) return;
    tpKinds.key = key;
    tpKinds.map = v && v.gate === "rnd" && Array.isArray(v.tables) ? new Map(v.tables.map((t) => [t.table, t])) : null;
    tpKindsFill();
  });
}
const TP_KIND_QUIET = new Set(["common"]); // 섞인 표에서 표지를 따로 세우지 않는 방식 — 표 수준에서 빼고 보는 띠(app/table_kinds.py QUIET 와 같다). 풍선 도움말에는 적는다
function tpKindTags(tid) { // 표 하나의 표지들 — 표의 방식(서버가 정한 t.kind: 공통인 띠는 빼고 본 것)이 하나로 정해졌으면 표지 하나, 섞였으면(mixed) 공통 말고 방식마다(앞에 서브 테이블 id).
  // 끝의 「?」 = 그 방식의 서브 테이블 가운데 머리글의 꼴만 보고 정한 것이 있다(sure 아님) · 풍선 도움말 = 서브 테이블마다의 방식과 근거(why — 공통인 띠도). 표지가 여럿이어도 도움말은 같다
  const t = tpKinds.map && tpKinds.key === tpKindsKey() ? tpKinds.map.get(tid) : null, out = [];
  if (!t || !Array.isArray(t.subs)) return out;
  const subs = t.subs.filter((s) => TP_KIND[s.kind]);
  if (!subs.length) return out;
  const all = [...new Set(subs.map((s) => s.kind))], varied = all.length > 1;
  let kinds = TP_KIND[t.kind] ? [t.kind] : all.filter((k) => !TP_KIND_QUIET.has(k));
  if (!kinds.length) kinds = all;
  const someSure = subs.some((s) => s.sure) && subs.some((s) => !s.sure); // 같은 방식인데 확실함이 갈리면 어느 서브 테이블이 「?」 인지 적는다
  const title = subs.map((s) => (subs.length > 1
    ? `서브 테이블 ${s.sub}${!varied && someSure && !s.sure ? "(?)" : ""}: ${varied ? `${TP_KIND[s.kind]}${s.sure ? "" : "?"} — ` : ""}${s.why}` : s.why)).join("\n")
    + (subs.some((s) => !s.sure) ? "\n「?」 = 머리글의 꼴만 보고 정했습니다(프로젝트 구성의 값으로는 확인하지 못했습니다)" : "");
  for (const k of kinds) {
    const mine = subs.filter((s) => s.kind === k);
    if (!mine.length) continue;
    const sure = mine.every((s) => s.sure);
    const tag = el("span", "tp-tag tp-kind", `${kinds.length > 1 ? `${mine.map((s) => s.sub).join("·")} ` : ""}${TP_KIND[k]}${sure ? "" : "?"}`);
    tag.dataset.kind = k;
    tag.dataset.sure = sure ? "1" : "0";
    tag.title = title;
    out.push(tag);
  }
  return out;
}
function tpKindsFill() { // 그려 둔 표 목록의 표지 자리(.tp-kinds)만 다시 채운다 — 목록을 통째로 다시 그리지 않는다(스크롤 · 초점 그대로)
  for (const slot of document.querySelectorAll("#tablesBox .tp-row .tp-kinds")) {
    const row = slot.closest(".tp-row");
    slot.replaceChildren(...tpKindTags(row && row.dataset.tableId));
  }
}

// 꼴은 헤딩 추출과 같은 틀(2026-11-16 사용자 「헤딩 추출이랑 표랑 uiux 가 유사했으면 좋겠어」 → 답 「표를 헤딩 추출 꼴로」 — spec_헤딩_추출 ② §10 「「표」 탭」):
// 위에서 ① 요약 수(.result-metric — 누르면 표 목록) ② 진행 줄(app.js headsProgLine — 표 구조 한 칸) ③ 상태 줄(.result-meta) ④ 하위 탭(.heads-view-nav — 헤딩 추출 결과 탭과 같은 꼴) → 그 탭의 내용.
// ①~③ 의 꼴은 헤딩 추출 요약과 같은 CSS(heading-panels.css 의 #tablesOverview) — 표 탭만의 머리 꼴을 따로 두지 않는다.
const TP_VIEWS = [["List", "표 목록"], ["Tools", "보기·도구"], ["Run", "추출·설정"]];
let tpView = "List"; // 고른 하위 탭 — 문서를 열어 둔 동안(tablesReset 이 처음으로 되돌린다)
function tpViewSet(v, focus = false) {
  if (!TP_VIEWS.some(([key]) => key === v)) return;
  tpView = v;
  tablesDraw();
  if (focus) { const b = document.querySelector(`#tablesBox [data-tp-view="${v}"]`); if (b) b.focus(); }
}

function tablesDraw() {
  const box = $("tablesBox"), pane = $("paneTables");
  if (!box || !pane || pane.hidden || !state.id) return;
  tpKindsLoad(); // 병합 방식 표지 — 이 문서 · 이 3단계 결과의 것을 아직 안 읽었으면 읽는다(오면 tpKindsFill 이 표지 자리만 채운다)
  box.textContent = "";
  const s3 = heads.view && heads.view.stage3, byId = new Map(((s3 && s3.tables) || []).map((t) => [t.id, t]));
  const store = (heads.xl.store && heads.xl.store.tables) || {}, common = heads.xl.store && heads.xl.store.common;
  const blocks = xlBlocks(), job = heads.view && heads.view.job;
  const busy = !!(job && job.status === "running"), supported = state.format !== "docx";
  const c = (s3 && s3.counts) || {}, k = c.calc || {}, ow = c.owners || {};
  const overview = el("section", "heads-overview"), metrics = el("div", "result-metrics");
  overview.id = "tablesOverview";
  overview.setAttribute("aria-label", "표 분석 개요");
  const stat = (label, v, cls = "") => { // 헤딩 추출의 수 단추와 같은 꼴 — 누르면 「표 목록」
    const b = hBtn("", () => tpViewSet("List"), { cls: `result-metric${cls ? ` ${cls}` : ""}`, title: `${label} — 누르면 표 목록` });
    b.append(el("span", null, label), el("strong", null, typeof v === "number" ? nf(v) : v));
    metrics.append(b);
  };
  stat("표", blocks.length);
  if (s3) {
    stat("계산식", k.tables || 0);
    if (k.mismatch) stat("불일치", k.mismatch, "is-warning");
    stat("소속", (ow.stage2 || 0) + (ow.stage1 || 0));
  }
  stat("지침", Object.values(store).filter((r) => r && r.instructions).length);
  const summaryHelp = [`문서의 표 ${nf(blocks.length)}개: 표 안 표 ${nf(blocks.filter((b) => b.depth > 1).length)}개와 1칸 표를 포함합니다.`,
    "지침 수는 이 작업에 표별 지침을 저장한 표의 수입니다."];
  if (s3) summaryHelp.push(`표 구조 실행 ${s3.meta?.run ?? "–"} · ${fmtWhen(s3.meta && s3.meta.at)}`,
    `수식 ${nf(k.formulas || 0)}개: 일치 ${nf(k.ok || 0)} · 미검증 ${nf((k.blank || 0) + (k.incomplete || 0))}. 불일치는 계산한 값과 문서 값이 다른 칸입니다.`,
    `소속: 헤딩 그래프 ${nf(ow.stage2 || 0)}개 · 문단 추출 기준 어림 ${nf(ow.stage1 || 0)}개.`);
  const summaryInfo = hHelp("표 집계 기준", summaryHelp.join("\n"), { note: true });
  overview.append(metrics);
  if (supported && heads.view && typeof headsProgLine === "function") // 진행 줄 — 헤딩 추출과 같은 그리기(스크립트 표 구조 / LLM 표 판정) · 누르면 이 탭의 「추출·설정」
    overview.append(headsProgLine(heads.view, { stages: [3], open: () => tpViewSet("Run"), where: () => "「테이블」 탭의 추출·설정" }));
  const meta = el("div", "result-meta"), chip = (text, stale = false) => el("span", `analysis-state${stale ? " stale" : ""}`, text);
  if (!supported) meta.append(chip("DOCX · 표 구조 분석 미지원"));
  else if (busy) { // 도는 동안 — 헤딩 추출 상태 줄과 같은 꼴(돌아가는 동그라미 + 지금 하는 일 · 지난 시간) · 누르면 헤딩 추출 「추출·설정」 의 그 단계(단계마다의 진행은 거기)
    const now = headsJobNow(job, heads.view);
    const progress = hBtn("", () => { showTab("Heads"); headsRunOpen(job.stage); }, { cls: "analysis-state running", title: now.title });
    progress.append(el("span", "now-what", now.what), el("span", "now-secs", fmtDur(now.secs)));
    progress.setAttribute("aria-label", `${now.what} · ${fmtDur(now.secs)} · 진행 보기`);
    meta.append(progress);
  } else if (job && job.status === "failed" && job.stage === 3) {
    meta.append(chip("표 구조 분석 실패", true), hBtn("실행 내역", () => { showTab("Heads"); headsRunOpen(3); }));
  } else if (!s3) meta.append(chip("표 구조 미분석"));
  else {
    // 문서가 바뀐 것만으로는 「재분석 필요」 가 아니다 — 표 구조는 한 번 만들면 뼈대(spec ② §17, 2026-11-10 사용자). 표 구조에 없는 표(새 표·모양이 바뀐 표)가 생겼을 때만 알린다(heading_drift.js)
    const dn = typeof driftCount === "function" ? driftCount(3) : 0;
    if (dn) meta.append(chip(driftText(3), true),
      hHelp("표 구조에 없는 표", "표 구조(뼈대)를 만든 뒤 문서에 생긴 표, 행·열 수가 달라진 표입니다. 표 구조는 그대로 쓰고, 이 표까지 넣으려면 표 구조를 다시 만드세요.\n헤딩 추출 탭 상태 줄의 꼬리표를 누르면 표마다 볼 수 있습니다.", { warning: true }));
    if (s3.ownerStale) meta.append(chip("소속 재확인 필요", true),
      hHelp("표 소속을 다시 확인해야 하는 이유", "헤딩 그래프가 바뀌어 표의 소속 헤딩·구분 라벨이 이전 결과를 가리킵니다. 표 구조를 다시 분석하면 맞춰집니다.", { warning: true }));
    if (s3.tempStale) meta.append(chip("TEMP 반영 필요", true),
      hHelp("표 구조에 TEMP를 반영해야 하는 이유", "표 구조 결과에서 제외한 TEMP 표가 지금 지정과 다릅니다. 표 구조를 다시 만들면 맞춰집니다.\n스크립트로 다시 만들면 이전에 LLM이 판정한 칸 역할도 스크립트 결과로 바뀝니다.", { warning: true }));
    if (!meta.childElementCount) meta.append(chip("표 구조 결과"));
  }
  meta.append(summaryInfo);
  if (supported && heads.view && typeof headsRunMenu === "function") // 상태 줄 끝 「단계별 실행 ▾」 — 헤딩 추출과 같은 함수(표 구조 만들기 · 표 판정 · 이 탭의 추출·설정) — spec ② §7 「실행 메뉴는 머리에」
    meta.append(headsRunMenu(heads.view, { stages: [3], detail: () => tpViewSet("Run") }));
  overview.append(meta);
  box.append(overview);
  const nav = el("div", "heads-view-nav"); // 하위 탭 — 헤딩 추출 결과 탭과 같은 꼴 · ←/→ · Home/End
  nav.setAttribute("role", "tablist");
  nav.setAttribute("aria-label", "표 보기");
  for (const [key, name] of TP_VIEWS) {
    const b = el("button", null, name), on = key === tpView;
    b.type = "button";
    b.id = `tpTab${key}`;
    b.dataset.tpView = key;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(on));
    b.setAttribute("aria-controls", "tpView");
    b.tabIndex = on ? 0 : -1;
    b.onclick = () => tpViewSet(key);
    nav.append(b);
  }
  nav.onkeydown = (e) => {
    const i = TP_VIEWS.findIndex(([key]) => key === tpView), n = TP_VIEWS.length;
    const to = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    tpViewSet(TP_VIEWS[to][0], true);
  };
  box.append(nav);
  const view = el("section", "tp-view");
  view.id = "tpView";
  view.setAttribute("role", "tabpanel");
  view.setAttribute("aria-labelledby", `tpTab${tpView}`);
  box.append(view);
  if (tpView === "Tools") { // 「보기·도구」 — 전의 접는 묶음의 내용 그대로
    const toolButtons = el("div", "tp-tool-buttons");
    if (common && common.instructions) toolButtons.append(el("span", "tp-common-status", "공통 지침 있음"));
    if (supported) {
      toolButtons.append(hBtn("구조 격자 보기", () => headsTables(), { disabled: !s3 }));
      if (typeof tmkOpen === "function") toolButtons.append(hBtn("표 만들기·서식 변환", () => tmkOpen()));
    }
    toolButtons.append(hBtn("공통 지침", () => tblAgentView("_common")));
    if (typeof divFormOpen === "function") toolButtons.append(hBtn("양식 정보", () => divFormOpen(), // 양식마다 관리하는 요청(spec_헤딩_추출 ② §12) — 「표」 절이 표 LLM 에 「양식 표 지침」 으로 간다
      { title: "이 문서의 양식 정보 — 「## 표」 절에 적은 내용은 이 양식의 모든 문서에서 「표 만들기」·「LLM 수식 판정」·표 지침 묶음에 함께 갑니다(공통 지침은 이 문서만)" }));
    toolButtons.append(
      hHelp("표 보기와 공통 지침", "구조 격자에서 칸 역할·수식 검증·필드 목록을 확인합니다.\n표 만들기·서식 변환은 선택한 표의 서식을 활용하는 도구입니다.\n공통 지침은 이 문서의 모든 표에 함께 주는 지침입니다.\n양식 정보의 「표」 절은 같은 양식의 모든 문서에 함께 주는 지침입니다.", { note: true }));
    const display = el("div", "tp-display-tools"), marks = hBtn("표 도구 표시", () => tblMarksToggle());
    marks.classList.toggle("on", tblMarksOn());
    marks.setAttribute("aria-pressed", String(tblMarksOn()));
    display.append(el("span", "tp-tool-label", "문서 표시"), marks);
    if (supported) {
      const roles = tblRolesBtn();
      roles.dataset.keep = "1";
      roles.textContent = "칸 역할 색";
      display.append(roles);
    }
    display.append(hHelp("문서 표시 도움말", "표 도구 표시는 문서의 표 옆에 엑셀식 보기·지침·소속 표지를 보입니다.\n칸 역할 색은 표 구조 결과를 문서의 칸에 겹쳐 보입니다. 문서가 바뀌어도 판정 때 있던 칸은 그 역할 그대로 표시합니다(그 뒤에 생긴 칸은 표시하지 않음).\n화면 표시만 바뀌며 문서 내용은 바뀌지 않습니다."));
    view.append(toolButtons, display);
    return;
  }
  if (tpView === "Run") { // 「추출·설정」 — 표 구조가 누구 것인지 · 실행 단추(헤딩 추출 「추출·설정」 과 같은 자리). 단계마다의 실행 기록은 헤딩 추출 쪽 3단계 카드
    if (!supported) { view.append(el("p", "tp-empty", "DOCX 문서는 표 구조 분석을 지원하지 않습니다.")); return; }
    const srcLine = typeof headsSourceLine === "function" ? headsSourceLine(heads.view, [3]) : null; // 표 구조가 LLM 것인지 스크립트 것인지 · 끝난 때 · 걸린 시간(app.js — spec ② §7 「LLM 표시」)
    view.append(srcLine || el("p", "tp-state", "표 구조가 아직 없습니다 — 「표 구조 만들기」 로 만듭니다(스크립트 · 무료)."));
    const acts = el("div", "tp-actions");
    acts.append(hBtn("표 구조 만들기", () => headsStart(3, false), { disabled: busy, cls: "btn sm primary" }),
      hBtn("LLM 분석 · 유료", () => headsLlmTables(), { disabled: busy }),
      hHelp("표 구조 분석 방법", "표 구조 만들기: 스크립트로 행·열 헤더, 필드, 서브 테이블, 구분, 수식과 소속을 분석합니다. LLM을 호출하지 않습니다.\nLLM 분석: 칸의 값을 보고 역할과 서브 테이블을 판정합니다. 유료 호출이며 수 분 걸릴 수 있습니다."));
    view.append(acts, hBtn("실행 기록 — 헤딩 추출 › 추출·설정 3단계", () => { showTab("Heads"); headsRunOpen(3); },
      { cls: "btn sm tp-run-log", title: "표 구조(3단계) 카드 — 단계마다의 진행 · 실행 기록 · 지침을 헤딩 추출 탭에서 봅니다" }));
    return;
  }
  if (!blocks.length) { view.append(el("p", "tp-empty", "이 문서에 표가 없습니다.")); return; }
  if (typeof ftBar === "function") { const fbar = ftBar(); if (fbar) view.append(fbar); } // 양식의 표 등록부 줄(form_tables.js — spec_테이블매니저 ② §11) — 양식이 정해진 문서에서만
  const list = el("ol", "tp-list");
  list.setAttribute("aria-label", "문서의 표 목록");
  blocks.forEach((b, i) => {
    const t = byId.get(b.id), rec = store[b.id], row = el("li", "tp-row");
    row.dataset.tableId = b.id;
    const top = el("div", "tp-row-head"), name = el("div", "tp-row-name");
    const id = el("strong", "tp-id", b.id);
    id.title = b.id;
    const size = el("span", "tp-size", `${b.rows}×${b.cols}`);
    size.title = `${nf(b.rows)}행 × ${nf(b.cols)}열 · ${nf(b.cells)}칸`;
    name.append(el("span", "tp-index", `${i + 1}.`), id, size);
    const actions = el("div", "tp-row-actions");
    const xl = hBtn("", () => xlColumn(b.id), { title: "엑셀식 보기" });
    xl.innerHTML = XL_ICON;
    xl.append("엑셀");
    xl.setAttribute("aria-label", `${b.id} 엑셀식 보기`);
    const instructions = hBtn("지침", () => tblAgentView(b.id));
    instructions.setAttribute("aria-label", `${b.id} 지침`);
    actions.append(xl, instructions);
    const host = t && t.host;
    if (host && hasBlock(host)) {
      const go = hBtn("↗", () => headsGo(host), { cls: "btn sm tp-go", title: "문서에서 표 위치 보기" });
      go.setAttribute("aria-label", `${b.id} 원문 위치`);
      actions.append(go);
    }
    top.append(name, actions);
    row.append(top);
    const o = t && t.owner, owner = el("div", "tp-owner");
    const tmp = typeof tempTableItem === "function" ? tempTableItem(b.id) : null; // TEMP 표(heading_temp.js — spec ② §15)
    if (tmp) {
      const tg = hBtn("TEMP", () => tempView(tmp.id), { cls: "hb temp", title: "TEMP 표 — 헤딩·템플릿과 표 구조에서 뺍니다 · 누르면 TEMP 목록" });
      owner.append(tg, el("span", "tp-owner-text", TEMP_WHY[tmp.why] || tmp.why));
    } else if (o && !o.root) {
      owner.append(el("span", "tp-meta-label", "소속"));
      const label = ownerLabel(o), path = (o.path || []).concat([o.text]).filter(Boolean).join(" › ") || label;
      const link = hasBlock(o.para) ? hBtn(label, () => headsGo(o.para), { cls: "tp-owner-link", title: path }) : el("span", "tp-owner-text", label);
      link.title = path;
      owner.append(link);
      if (o.division && o.role !== "label") owner.append(dvTag(el("span", "hb div", (o.division.basis || []).length ? `[${basisNames(o.division.basis)}]` : short(o.division.text, 14)), dvOfDivision(o.division)));
    } else owner.append(el("span", "tp-owner-text", o && o.root ? "문서 최상위" : t ? "소속 없음" : !supported ? "표 구조 미지원"
      : s3 ? (b.cells === 1 ? "1칸 표(표 구조 없음)" : "새 표 · 표 구조를 만든 뒤 생김") : "표 구조 미분석")); // 옛 「표 구조에 없음」 — 까닭을 그대로 적는다(문서 표지와 같은 말 — tblMark)
    row.append(owner);
    const meta = el("div", "tp-row-meta");
    const kindSlot = el("span", "tp-kinds"); // 병합 방식 표지 자리(spec_테이블매니저 ② §5 「병합 방식」) — 꼬리표 줄 맨 앞 · 해당 없으면 빈 채로(자리를 차지하지 않는다)
    kindSlot.append(...tpKindTags(b.id));
    meta.append(kindSlot);
    const typeSlot = el("span", "tp-types"); // 양식의 표 판정 표지 자리(spec_테이블매니저 ② §10 「양식의 표 판정」 — table_types.js) — 확정된 표에만 「확정됨」 · 그 밖에는 빈 채로(자리를 차지하지 않는다)
    if (typeof tblTypeTags === "function") typeSlot.append(...tblTypeTags(b.id));
    meta.append(typeSlot);
    const formSlot = el("span", "tp-forms"); // 「양식 표」 꼬리표 자리(spec_테이블매니저 ② §11 — form_tables.js) — 양식의 표 등록부가 있는 문서에서만 · 그 밖에는 빈 채로(자리를 차지하지 않는다)
    if (typeof ftTags === "function") formSlot.append(...ftTags(b.id));
    meta.append(formSlot);
    if (b.depth > 1) meta.append(el("span", "tp-tag", "표 안 표"));
    const basis = t && basisNames(t.basis);
    if (basis) meta.append(el("span", "tp-tag", `구분 ${basis}`));
    const kc = (t && t.calc) || {};
    if (kc.is) meta.append(el("span", "tp-tag", `수식 ${nf(kc.formulas || 0)}`));
    if (kc.mismatch) meta.append(el("span", "tp-tag is-warning", `불일치 ${nf(kc.mismatch)}`));
    if (t && t.notes != null) meta.append(el("span", "tp-detail", `작성요령 ${nf(Array.isArray(t.notes) ? t.notes.length : t.notes)}`)); // 요약은 수, 전체 결과는 목록
    const note = el("span", `tp-detail${rec && rec.instructions ? " has-instructions" : ""}`, rec && rec.instructions ? "지침 있음" : "지침 없음");
    if (rec && rec.instructions) note.title = short(rec.instructions, 120);
    meta.append(note);
    row.append(meta);
    list.append(row);
  });
  view.append(list);
}
