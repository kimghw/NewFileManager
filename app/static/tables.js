"use strict";
// 표 모듈(spec_헤딩_추출 ② §10 「모듈」) — 본문(app.js)과 따로, 문서의 표만 다룬다(사용자 2026-11-10 "본문 따로, 테이블 따로"):
// 표 식별 표지(.tbl-mark) · 엑셀식 보기(2열 kind "xl" · 문서 자리 .xl-wrap — A1 격자 · 수식 엔진 · 문서에 반영) · 표 지침(2열 kind "tableAgent", 표 에이전트 입력) · 「표」 탭(#paneTables).
// app.js 가 주는 것: state·heads(view·tbl·xl·dlg·seq)·$·el·api·toast·hBtn·hTable·hCell·hFoot·headsDlg·headsColClose·headsGo·headsShow·headsStart·headsLlmTables·headsTables·headsParaLink·
// headsCard3·colLetter·basisNames·ownerLabel·short·oneLine·nf·hasBlock·renderPara·applyServer·refreshSaveState·updateEdits·fmtWhen·H_JSON·LS.
// app.js 가 부르는 것(typeof 검사 뒤): tblMarksDraw(paginate 끝·headsRender 끝) · tblMarksOn/tblMarksToggle(3단계 카드) · tblAgentView·xlColumn(표 보기 격자) · tblAgentLeave·xlColumnClosed(headsColClose) ·
// tablesShow(탭 열 때)·tablesReset(문서 열고 닫을 때). 서버 짝은 app/tables_api.py(끝점)·app/table_agent.py(저장·묶음 글)·heading_tables.table_notes(작성요령). index.html 이 app.js 다음에 읽는다.

// ---------------------------------------------------------------- 표 도구(spec_헤딩_추출 ② §10) — 표 식별 표지 · 엑셀식 보기(A1 격자 · 수식 엔진 · 문서에 반영) · 표 지침(표 에이전트 입력)
// 표지(.tbl-mark)는 문서 표(table.tbl[data-tbl] 첫 조각 · 엑셀식 보기 .xl-wrap)의 위 오른쪽에 .sheet 절대 위치 — .tpl-mark 와 같이 zoom 1/z 로 화면 크기를 고정한다.
// 엑셀식 보기는 첫 조각을 .xl-wrap 으로 바꾸고 나머지 조각(.cont)을 숨긴다; 쪽을 다시 나누면(paginate) 조각이 새로 생기므로 tblMarksDraw → xlApply 가 heads.xl.open 의 표를 다시 격자로.
// 격자의 값은 지금 문서 칸 글(state.texts)이고, 수식·고친 값은 「문서에 반영」 을 눌러야 PATCH /blocks 로 문서에 쓰인다(보통 글 고침과 같은 길 — 되돌리기·실행 취소·기록 그대로).
const TBL_MARKS_KEY = "nfm.tblMarks";
const XL_ICON = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="M1.5 2h13v12h-13zM3 3.5v2.2h4v-2.2zm5.2 0v2.2H13V3.5zM3 6.9v2.2h4V6.9zm5.2 0v2.2H13V6.9zM3 10.3v2.2h4v-2.2zm5.2 0v2.2H13v-2.2z"/></svg>';
const XL_ROLE = { colhead: "열헤더", rowhead: "행헤더", corner: "귀퉁이", field: "필드", title: "제목", note: "안내", spacer: "간격" };
const XL_UNIT = /\s*(?:%|％|원|천원|백만원|억원|명|건|개|회|년|개월|시간|점|㎡|kg|t)\s*$/i;
const XL_CODE = /\(\s*[A-Z](?:\s*[+\-*/]\s*[A-Z])*\s*\)\s*$/;
const XL_REF = /^\$?([A-Z]{1,3})\$?([1-9]\d{0,3})$/i;
const xlRefOf = (row, col) => `${colLetter(col)}${row + 1}`;
function tblMarksOn() { try { return localStorage.getItem(TBL_MARKS_KEY) !== "off"; } catch { return true; } }
function tblMarksToggle() {
  try { localStorage.setItem(TBL_MARKS_KEY, tblMarksOn() ? "off" : "on"); } catch { /* 기억만 안 함 */ }
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
function tblMarksDraw() {
  // 읽기 단계(모든 표의 자리) → 쓰기 단계(표지 붙이기) — 표마다 재고 붙이기를 번갈아 하면 표 수만큼 강제 배치가 되어 큰 문서에서 10~27 s 멈춘다
  // (2026-11-10 실측 — 연구개발계획서 양식 표 145개: 번갈아 13~27 s → 나눠서 0.1 s 이하, spec_owpml_편집 ③). 표지가 꺼져 있어도 xlApply·xlColumnSync·tablesDraw 는 돈다.
  for (const e of document.querySelectorAll(".tbl-mark")) e.remove();
  xlApply(); // 열어 둔 엑셀식 보기를 되살린다(쪽을 다시 나누면 표 조각이 새로 생김)
  const sc = $("scroller");
  if (state.id && !sc.hidden && tblMarksOn()) {
    const s3 = heads.view && heads.view.stage3;
    const byId = new Map(((s3 && s3.tables) || []).map((t) => [t.id, t]));
    const store = (heads.xl.store && heads.xl.store.tables) || {};
    const jobs = [];
    for (const sheet of document.querySelectorAll("#doc .sheet")) { // 읽기 단계 — DOM 을 바꾸지 않는다
      const sr = sheet.getBoundingClientRect();
      const z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1;
      for (const t of sheet.querySelectorAll("table.tbl[data-tbl]:not(.cont), .xl-wrap[data-tbl]")) {
        if (t.hidden) continue;
        const r = t.getBoundingClientRect();
        jobs.push({ sheet, tid: t.dataset.tbl, z, top: Math.round(r.top - sr.top), left: Math.round(r.right - sr.left) });
      }
    }
    for (const j of jobs) { // 쓰기 단계
      const m = tblMark(j.tid, byId.get(j.tid), store[j.tid], heads.xl.open.has(j.tid), !!s3);
      m.style.zoom = String(1 / j.z);
      m.style.top = `${j.top}px`;
      m.style.left = `${j.left}px`;
      j.sheet.append(m);
    }
  }
  xlColumnSync();
  if (typeof tablesDraw === "function") tablesDraw(); // 「표」 탭 목록(소속·계산식·지침)도 같은 자료를 따른다
}
window.addEventListener("resize", () => { if (state.id && document.querySelector(".tbl-mark, .xl-wrap")) tblMarksDraw(); });

// ---- 엑셀식 보기 — 2열(kind "xl") : 문서는 그대로 두고 옆 열에 격자(사용자 2026-11-10 「열을 하나 만들어서 거기에 엑셀표」) ----------------------------------------
const xlStageKey = () => { const s3 = heads.view && heads.view.stage3; return s3 && s3.meta ? `${s3.meta.run}|${s3.meta.at}` : "none"; };
const xlColKey = (tid) => { // 2열 격자를 다시 만들 조건 — 3단계 결과 · 구조 편집 차례(행·열 넣기/지우기·나누기·합치기 뒤 state.structRev) · 표 블록 크기
  const b = xlBlock(tid);
  return `${xlStageKey()}|${state.structRev}|${b ? `${b.nRows}x${b.nCols}x${(b.cells || []).length}` : "-"}`;
};
async function xlColumn(tid) {
  if (!state.id || !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const { tools, body } = headsDlg("xl", `엑셀식 보기 · ${tid}`, "A1 격자 · 수식 계산 — 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  const seq = heads.seq, epoch = state.epoch;
  hFoot("읽는 중…", false);
  await xlStore();
  await xlFull();
  if (seq !== heads.seq || epoch !== state.epoch) return;
  const wrap = xlBuild(tid, []);
  if (!wrap) { hFoot("표 블록을 찾지 못했습니다"); return; }
  wrap.classList.add("col");
  heads.xl.col = { tid, key: xlColKey(tid) };
  body.textContent = "";
  body.append(wrap);
  const b = xlBlock(tid), s3 = heads.view && heads.view.stage3, t = s3 && (s3.tables || []).find((x) => x.id === tid);
  tools.textContent = "";
  if (t && t.owner && !t.owner.root && hasBlock(t.owner.para)) tools.append(el("span", "muted", "소속"), hBtn(ownerLabel(t.owner), () => headsGo(t.owner.para), { title: "문서의 그 헤딩으로" }));
  if (t && t.host && hasBlock(t.host)) tools.append(hBtn("표 자리로", () => headsGo(t.host), { title: "문서에서 이 표를 품은 문단으로" }));
  tools.append(el("span", "spacer"), el("span", "muted", `${b.nRows || "?"}×${b.nCols || "?"}`));
  const foot = $("headsDlgFoot");
  foot.textContent = "";
  foot.append(el("span", "muted", `표 ${tid} · 수식은 이 작업에 저장 · 문서는 「문서에 반영」 을 눌러야 바뀜`));
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
  if (c.key !== xlColKey(c.tid) && !c.busy) { c.busy = true; xlColumn(c.tid); }
}

function tblMark(tid, t, rec, inplace, hasStage3) { // 표지 하나 — ⊞ 엑셀식 보기(2열) · ✎ 표 지침 · 표 id · 소속(헤딩 「TN Lk」·구분 라벨 — 누르면 문서의 그 문단) · 수식 수
  const inCol = !!(heads.xl.col && heads.xl.col.tid === tid && heads.dlg === "xl"), open = inplace || inCol;
  const m = el("div", "tbl-mark" + (open ? " open" : ""));
  m.dataset.for = tid;
  const xl = el("button", "tm-btn xl");
  xl.type = "button";
  xl.innerHTML = XL_ICON;
  xl.setAttribute("aria-pressed", String(open));
  xl.setAttribute("aria-label", "엑셀식 보기");
  xl.title = inplace ? "문서 보기로(원래 표)" : inCol ? "엑셀식 보기 열 닫기" : "엑셀식 보기 — 문서 옆 열에 A1 격자(수식 계산 · 문서에 반영)";
  xl.onclick = (e) => { e.stopPropagation(); if (inplace) xlClose(tid); else if (inCol) headsColClose(); else xlColumn(tid); };
  const g = el("button", "tm-btn guide" + (rec && rec.instructions ? " has" : ""), "✎");
  g.type = "button";
  g.setAttribute("aria-label", "표 지침");
  g.title = "표 지침 — 작성요령 · 사용자 지침(표 에이전트 입력)" + (rec && rec.instructions ? " · 지침 있음" : "") + (rec && Object.keys(rec.formulas || {}).length ? ` · 사용자 수식 ${Object.keys(rec.formulas).length}` : "");
  g.onclick = (e) => { e.stopPropagation(); tblAgentView(tid); };
  m.append(xl, g, el("span", "tm-id", tid));
  if (state.format === "docx") return m; // 3단계는 hwpx 만 — 소속 없음
  if (t) {
    const o = t.owner;
    if (o && !o.root) {
      const isLbl = o.role === "label";
      const b = el("button", "tm-owner" + (isLbl ? " lbl" : ""), `${o.tplNo ? `T${o.tplNo} L${o.level} ` : ""}${short(o.text || "(제목 없음)", 24)}`);
      b.type = "button";
      b.title = [`소속 ${oneLine(o.text || "(제목 없음)")}${o.tplNo ? ` · 템플릿 T${o.tplNo} ${o.level}번째 줄` : ""}${isLbl ? " · 구분 라벨" : ""}`,
        (o.path || []).length ? `경로 ${o.path.join(" › ")}` : "", o.division && !isLbl ? `구분 라벨 ${oneLine(o.division.text)}` : "",
        (t.basis || []).length ? `구분 ${basisNames(t.basis)}` : "", t.unit ? `단위 ${t.unit}` : "",
        `출처 ${o.source === "stage2" ? "2단계 그래프" : "1단계 어림(2단계 그래프 없음)"}`, hasBlock(o.para) ? "누르면 문서의 그 헤딩으로" : ""].filter(Boolean).join("\n");
      b.onclick = (e) => { e.stopPropagation(); headsGo(o.para); };
      m.append(b);
      if (o.division && !isLbl) {
        const d = el("span", "tm-div", (o.division.basis || []).length ? `[${basisNames(o.division.basis)}]` : short(o.division.text, 12));
        d.title = `구분 라벨 ${oneLine(o.division.text)}`;
        m.append(d);
      }
    } else {
      const s = el("span", "tm-owner muted", o && o.root ? "문서 뿌리" : "소속 없음");
      s.title = o && o.root ? "위에 헤딩이 없는 표(문서 뿌리)" : "소속 헤딩·라벨을 찾지 못함";
      m.append(s);
    }
    if (t.calc && t.calc.is) {
      const k = el("span", "tm-calc" + (t.calc.mismatch ? " bad" : ""), `수식 ${nf(t.calc.formulas)}${t.calc.mismatch ? ` · 불일치 ${nf(t.calc.mismatch)}` : ""}`);
      k.title = `계산식 표 — 일치 ${nf(t.calc.ok)} · 불일치 ${nf(t.calc.mismatch)} · 미기입 ${nf(t.calc.missing)} · 미검증 ${nf((t.calc.blank || 0) + (t.calc.incomplete || 0))}`;
      m.append(k);
    }
  } else {
    const b = el("button", "tm-owner muted", hasStage3 ? "표 구조에 없음" : "소속 모름");
    b.type = "button";
    b.title = hasStage3 ? "3단계 결과에 이 표가 없습니다(1칸 표·결과가 오래됨) — 누르면 표 구조를 다시 만듭니다(스크립트만)"
      : "표 구조(3단계)를 만들면 소속 헤딩·라벨이 표시됩니다 — 누르면 스크립트로 만들기(1초 안팎)";
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
  t = t.replace(XL_CODE, "").trim();
  const pct = /[%％]\s*$/.test(t);
  t = t.replace(/[%％]\s*$/, "").replace(XL_UNIT, "").replace(/[%％]\s*$/, "").trim();
  let neg = false;
  if (/^\(.*\)$/.test(t)) { neg = true; t = t.slice(1, -1).trim(); }
  if (/^[-−–]/.test(t)) { neg = !neg; t = t.slice(1).trim(); } else if (t.startsWith("+")) t = t.slice(1).trim();
  if (!/^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$|^\.\d+$/.test(t)) return null;
  if (/^0(?:,000)+$|^0{2,}$/.test(t)) return null; // 자리표시 「0,000,000」「00」
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

function xlModel(tid, b, t3, rec) {
  const cells = [], occ = new Map();
  let nR = b.nRows || 0, nC = b.nCols || 0;
  const roles = new Map(((t3 && t3.cells) || []).map((c) => [`${c.row},${c.col}`, c]));
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
  const base = new Map(); // §9 가 만든 엑셀 수식(세로 합 하나 — excel: true)
  const fById = new Map();
  for (const f of (t3 && t3.formulas) || []) { if (f.excel && f.formula) base.set(f.ref, f.formula); fById.set(f.ref, f); }
  const formulas = new Map(base);
  for (const [k, v] of Object.entries((rec && rec.formulas) || {})) { if (v) formulas.set(k, v); else formulas.delete(k); } // "" = §9 수식 끄기
  return { tid, rows: nR, cols: nC, cells, occ, base, fById, formulas, values: new Map(), rec: rec || { instructions: "", formulas: {}, version: 0 }, t3, sel: null, res: new Map() };
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
    return s ? s : null;
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
    const wrap = xlBuild(tid, frags);
    if (!wrap) { heads.xl.open.delete(tid); continue; }
    frags[0].replaceWith(wrap);
    for (const f of frags.slice(1)) f.hidden = true;
  }
}

function xlBuild(tid, frags) {
  const b = xlBlock(tid);
  if (!b) return null;
  const full = heads.tbl.data, s3 = heads.view && heads.view.stage3;
  const t3 = full && s3 && s3.meta && heads.tbl.key === `${s3.meta.run}|${s3.meta.at}` ? (full.tables || []).find((x) => x.id === tid) || null : null;
  const rec = ((heads.xl.store || {}).tables || {})[tid] || null;
  const model = xlModel(tid, b, t3, rec);
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
  const write = hBtn("문서에 반영", () => xlWriteBack(wrap), { title: "수식 칸의 계산값과 고친 값을 그 칸의 문단 글로 씁니다(문단이 하나인 칸만 — 기존 글을 바꿈, 되돌리기·실행 취소로 돌릴 수 있음)" });
  write.classList.add("xl-write");
  bar.append(name, fx, write);
  if (t3) {
    const dl = el("a", "btn sm", "엑셀로 받기");
    dl.href = `/api/docs/${encodeURIComponent(state.id)}/headings/tables/${encodeURIComponent(tid)}/xlsx`;
    dl.setAttribute("download", "");
    dl.title = "시트 「표」(격자 — 합계·비율 칸은 엑셀 수식) · 「검증」 · 「필드」 · 「정보」 .xlsx(3단계 결과 기준 — 여기서 고친 수식은 안 들어감)";
    bar.append(dl, hBtn("표 보기", () => headsTables(tid), { title: "2열에서 칸 역할 격자·수식 검증·필드 목록" }));
  } else if (state.format === "docx") bar.append(el("span", "muted xl-note", "3단계 표 구조는 hwpx 만 — 역할·수식 없이 격자만"));
  else bar.append(el("span", "muted xl-note", "3단계 표 구조 없음 — 역할 색·합계/비율 수식 없이 격자만"),
    hBtn("표 구조 만들기", () => headsStart(3, false), { cls: "btn sm primary", title: "3단계 표 구조를 스크립트로 만듭니다(1초 안팎) — 끝나면 열헤더·행헤더 색과 합계·비율·코드 수식이 격자에 들어오고 문서 값과 견줍니다" }));
  bar.append(hBtn("표 지침", () => tblAgentView(tid), { title: "작성요령 · 사용자 지침(표 에이전트 입력)" }), el("span", "spacer"));
  if (frags.length) bar.append(hBtn("문서 보기", () => xlClose(tid), { title: "원래 표로" }));
  else bar.append(hBtn("문서 자리에서 보기", () => xlOpen(tid), { title: "문서의 그 표 자리를 이 격자로 바꿔 보기(다시 누르면 원래 표)" }));
  wrap.append(bar);
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
  hr.append(el("th", "corner"));
  for (let k = 0; k < model.cols; k += 1) hr.append(el("th", null, colLetter(k)));
  thead.append(hr);
  table.append(thead);
  const tb = el("tbody");
  for (let r = 0; r < model.rows; r += 1) {
    const tr = el("tr");
    tr.append(el("th", null, String(r + 1)));
    for (let k = 0; k < model.cols; k += 1) {
      const c = model.occ.get(`${r},${k}`);
      if (!c) { tr.append(el("td", "none")); continue; }
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
  let bad = 0, fill = 0, errs = 0, dirty = 0, blanks = 0;
  for (const c of model.cells) {
    const td = byRef.get(c.ref);
    if (!td) continue;
    const doc = xlDocText(c), f = model.formulas.get(c.ref);
    td.className = c.role || "";
    td.title = "";
    if (td.querySelector("input")) continue; // 고치는 중
    if (f) {
      const v = model.res.get(c.ref), dn = xlNum(doc);
      td.classList.add("fx");
      let st = "";
      if (xlIsErr(v)) { st = "err"; errs += 1; }
      else if (v == null || v === "") { st = "blank"; blanks += 1; } // 피연산자가 빈 칸 — §9 「미검증」
      else if (typeof v === "number") {
        if (dn) { if (Math.abs(dn.v - v) <= 0.5 * 10 ** -(oneLine(doc).match(/\.(\d+)/) ? RegExp.$1.length : 0) + 1e-9) st = "ok"; else { st = "bad"; bad += 1; } }
        else if (!oneLine(doc).trim()) { st = "fill"; fill += 1; }
        else { st = "bad"; bad += 1; }
      }
      if (st) td.classList.add(st);
      if (typeof v === "number") td.classList.add("num");
      const dn0 = xlNum(doc);
      td.textContent = xlShow(v) + (typeof v === "number" && dn0 && dn0.pct ? "%" : "");
      td.title = `${c.ref} ${f}\n계산값 ${st === "blank" ? "(빈 값 — 피연산자가 빈 칸)" : xlShow(v)} · 문서 값 ${doc || "(빈 칸)"}${st === "bad" ? " · 불일치" : st === "fill" ? " · 문서 칸이 비어 있음(미기입)" : st === "ok" ? " · 일치" : st === "blank" ? " · 미검증" : ""}`
        + (model.base.has(c.ref) && model.base.get(c.ref) === f ? "\n3단계가 만든 수식" : "\n사용자 수식") + (c.role && XL_ROLE[c.role] ? `\n${XL_ROLE[c.role]}` : "");
    } else {
      const raw = model.values.has(c.ref) ? model.values.get(c.ref) : doc;
      td.textContent = c.nested && !raw ? "〔표〕" : raw;
      if (xlNum(raw)) td.classList.add("num");
      if (model.values.has(c.ref) && model.values.get(c.ref) !== doc) { td.classList.add("dirty"); dirty += 1; }
      td.title = `${c.ref}${c.role && XL_ROLE[c.role] ? ` · ${XL_ROLE[c.role]}` : ""}${model.values.has(c.ref) ? `\n고친 값(문서에 반영 전) · 문서 값 ${doc || "(빈 칸)"}` : ""}`
        + (c.s3 && c.s3.role === "field" && (c.s3.rowPath || c.s3.colPath) ? `\n행헤더 ${(c.s3.rowPath || []).map((id) => xlNameOf(model, id)).join(" › ") || "—"} · 열헤더 ${(c.s3.colPath || []).map((id) => xlNameOf(model, id)).join(" › ") || "—"}` : "");
    }
    if (model.sel === c.ref) td.classList.add("sel");
  }
  const pending = xlPending(wrap).length;
  const write = wrap.querySelector(".xl-write");
  write.textContent = pending ? `문서에 반영 ${pending}` : "문서에 반영";
  write.disabled = !pending;
  const user = [...model.formulas].filter(([k, v]) => model.base.get(k) !== v).length + [...model.base].filter(([k]) => !model.formulas.has(k)).length;
  const foot = wrap.querySelector(".xl-foot");
  foot.textContent = "";
  foot.append(el("span", null, `${model.rows}×${model.cols} · 칸 ${nf(model.cells.length)} · 수식 ${nf(model.formulas.size)}${user ? `(사용자 ${user})` : ""}`),
    el("span", bad ? "warn" : "", `불일치 ${nf(bad)}`), el("span", null, `미기입 ${nf(fill)}`), blanks ? el("span", null, `미검증(빈 칸) ${nf(blanks)}`) : "", errs ? el("span", "warn", `오류 ${nf(errs)}`) : "",
    dirty ? el("span", null, `고친 값 ${nf(dirty)}`) : "",
    el("span", "muted", "Enter 반영·아래로 · Tab 오른쪽 · F2/두 번 누르기 고침 · Delete 비움 · 「=」 수식(작업에 저장)"));
  if (heads.xl.saving.get(model.tid) === "fail") foot.append(el("span", "warn", "수식 저장 실패 — 다시 고치면 다시 시도"));
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
  for (const [k, v] of model.formulas) if (model.base.get(k) !== v) user[k] = v;
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
  const { tools, body } = headsDlg("tableAgent", isCommon ? "공통 표 지침" : `표 지침 · ${tid}`,
    isCommon ? "이 문서의 모든 표에 함께 주는 지침 — 표 에이전트의 입력(LLM 호출은 아직 없음)" : "작성요령(문서에서) · 공통 지침 · 이 표 지침 — 표 에이전트의 입력(LLM 호출은 아직 없음)");
  const seq = heads.seq, id = state.id, epoch = state.epoch;
  hFoot("읽는 중…", false);
  let a;
  try { a = await api(tblAgentUrl(tid)); }
  catch (e) { if (seq === heads.seq && epoch === state.epoch) hFoot(`표 지침을 읽지 못했습니다: ${e.message}`); return; }
  if (seq !== heads.seq || epoch !== state.epoch) return;
  await xlStore();
  if (seq !== heads.seq || epoch !== state.epoch) return;
  const wrap = el("div", "ta-wrap");
  const ident = el("div", "ta-ident");
  const t = a.ident;
  if (!isCommon) ident.append(el("b", null, tid));
  if (t) {
    ident.append(el("span", null, `${t.rows}×${t.cols} · 칸 ${nf(t.cells)}${t.depth > 1 ? " · 표 안 표" : ""}`));
    const o = t.owner;
    if (o && !o.root) {
      ident.append(el("span", "muted", "소속"), hasBlock(o.para) ? hBtn(ownerLabel(o), () => headsGo(o.para), { title: (o.path || []).concat([o.text]).join(" › ") || "문서의 그 헤딩으로" }) : el("b", null, ownerLabel(o)));
      if ((o.path || []).length) ident.append(el("span", "muted", `(${o.path.join(" › ")})`));
      if (o.division) ident.append(el("span", "hb div", `구분 라벨 ${o.division.text}`));
    } else ident.append(el("span", "muted", o && o.root ? "소속: 문서 뿌리(위에 헤딩 없음)" : "소속: 모름"));
    if ((t.basis || []).length) ident.append(el("span", "hb", `구분 ${basisNames(t.basis)}`));
    if (t.unit) ident.append(el("span", "hb", `단위 ${t.unit}`));
    if (t.calc && t.calc.is) ident.append(el("span", "hb", `수식 ${nf(t.calc.formulas)}${t.calc.mismatch ? ` · 불일치 ${nf(t.calc.mismatch)}` : ""}`));
    if (t.before) ident.append(el("span", "muted", `앞 문단 「${short(t.before, 36)}」`));
  }
  if (!isCommon) wrap.append(ident);
  const acts = el("div", "ta-row");
  if (t && t.host && hasBlock(t.host)) acts.append(hBtn("표 자리로", () => headsGo(t.host), { title: "문서에서 이 표를 품은 문단으로" }));
  if (t) acts.append(hBtn("격자(표 보기)", () => headsTables(tid), { title: "칸 역할 격자 · 수식 검증 · 필드 목록" }));
  if (!isCommon) acts.append(hBtn("엑셀식 보기", () => xlColumn(tid), { title: "이 열에 A1 격자(수식 계산 · 문서에 반영)" }));
  if (!isCommon && !a.stage3 && state.format !== "docx") acts.append(hBtn("표 구조 만들기(스크립트)", () => headsStart(3, false), { title: "3단계 표 구조를 만들면 소속·작성요령·구조·수식이 채워집니다" }));
  if (!isCommon) wrap.append(acts);
  if (!isCommon && !a.stage3) wrap.append(el("p", "hnote", state.format === "docx" ? "3단계 표 구조는 hwpx 만 — 지침만 저장합니다." : "3단계 표 구조 결과에 이 표가 없어 소속·작성요령·구조·수식은 비어 있습니다 — 지침은 저장됩니다."));
  if (!isCommon) wrap.append(el("h3", null, `작성요령(문서에서) ${nf((a.notes || []).length)}`));
  if (isCommon) { /* 공통 — 작성요령 없음 */ } else if ((a.notes || []).length) {
    const ul = el("ul", "ta-notes");
    const WHERE = { before: "표 앞", cell: "표 안", after: "표 뒤" };
    for (const n of a.notes) {
      const li = el("li");
      li.append(el("span", "hb", WHERE[n.where] || n.where));
      if (n.para && hasBlock(n.para)) li.append(headsParaLink(n.para, n.text, 160, n.cell ? `칸 ${n.cell}` : ""));
      else li.append(el("span", null, short(n.text, 160)));
      ul.append(li);
    }
    wrap.append(ul);
  } else wrap.append(el("p", "hnote", "표 안 안내 칸·표 앞뒤의 ※ 안내 문단에서 찾은 작성요령이 없습니다."));
  const area = (title, rec, placeholder) => {
    wrap.append(el("h3", null, title));
    const ta = el("textarea");
    ta.value = rec.instructions || "";
    ta.defaultValue = ta.value;
    ta.placeholder = placeholder;
    ta.rows = title.startsWith("공통") ? 4 : 8;
    const row = el("div", "ta-row"), st = el("span", "muted", rec.updated ? `v${rec.version} · ${fmtWhen(rec.updated)}` : "저장된 지침 없음");
    wrap.append(ta, row);
    return { ta, row, st };
  };
  const common = area("공통 지침 — 이 문서의 모든 표", a.common, "모든 표에 함께 주는 지침(예: 금액은 천원 단위 · 합계는 행·열 모두 검산 · 빈 칸은 「-」 로)");
  const own = isCommon ? null : area("이 표 지침", a.own, "이 표에만 주는 지침(예: 1차년도 열은 2026년 · 기관부담 현물은 인건비만 · 비율은 소수 첫째 자리까지)");
  const pre = el("pre", "ta-prompt", a.prompt || "");
  const save = async (kind) => {
    const which = kind === "common" ? common : own, target = kind === "common" ? "_common" : tid, rec = kind === "common" ? a.common : a.own;
    const text = which.ta.value;
    which.st.textContent = "저장 중…";
    try {
      const r = await api(tblAgentUrl(target), { method: "PUT", headers: H_JSON, body: JSON.stringify({ instructions: text, version: rec.version }) });
      if (seq !== heads.seq || epoch !== state.epoch) return;
      a.common = r.common; a.own = kind === "common" ? a.own : r.own; a.prompt = r.prompt;
      if (kind === "common") a.common = r.common; else a.own = r.own;
      which.ta.defaultValue = which.ta.value;
      const now = kind === "common" ? a.common : a.own;
      which.st.textContent = `v${now.version} · ${fmtWhen(now.updated)} · 저장함`;
      pre.textContent = a.prompt || "";
      await xlStore(true);
      tblMarksDraw();
      toast(kind === "common" ? "공통 표 지침을 저장했습니다" : `표 ${tid} 지침을 저장했습니다`);
    } catch (e) {
      if (seq !== heads.seq || epoch !== state.epoch) return;
      which.st.textContent = e.status === 409 ? "다른 화면이 먼저 저장 — 열을 다시 열어 확인하세요" : `저장 실패: ${e.message}`;
      toast(e.status === 409 ? "표 지침이 다른 곳에서 바뀌었습니다 — 열을 다시 여세요" : `표 지침을 저장하지 못했습니다: ${e.message}`, true);
    }
  };
  for (const [kind, w] of (isCommon ? [["common", common]] : [["common", common], ["own", own]])) {
    w.row.append(hBtn("저장", () => save(kind), { cls: "btn sm primary" }), hBtn("지우기", () => { w.ta.value = ""; save(kind); }, { title: "지침을 빈 글로 저장" }), w.st);
    w.ta.oninput = () => { w.st.textContent = w.ta.value !== w.ta.defaultValue ? "저장 안 함" : (kind === "common" ? a.common : a.own).updated ? `v${(kind === "common" ? a.common : a.own).version}` : ""; };
  }
  const d = el("details", "more hblock");
  d.append(el("summary", null, "에이전트 입력 미리보기 — 표 식별 · 작성요령 · 지침 · 표 구조 · 수식(저장하면 새로)"), pre);
  wrap.append(d);
  body.append(wrap);
  heads.xl.agent = { tid, dirty: () => common.ta.value !== common.ta.defaultValue || (!!own && own.ta.value !== own.ta.defaultValue) };
  tools.append(el("span", "muted", "지침은 이 작업(문서)에 저장됩니다 · 표 에이전트의 LLM 호출은 후속"));
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
}

async function tablesShow() { // 탭을 열 때 — 3단계 요약(heads.view)이 없으면 헤딩 상태를 읽고(1단계 자동 — 헤딩 추출 탭과 같음), 저장된 지침을 읽은 뒤 그린다
  if (!state.id) return;
  const epoch = state.epoch;
  if (state.format !== "docx" && !heads.view) await headsShow();
  if (epoch !== state.epoch) return;
  await xlStore();
  if (epoch !== state.epoch) return;
  tablesDraw();
}

function tablesDraw() {
  const box = $("tablesBox"), pane = $("paneTables");
  if (!box || !pane || pane.hidden || !state.id) return;
  box.textContent = "";
  const s3 = heads.view && heads.view.stage3, byId = new Map(((s3 && s3.tables) || []).map((t) => [t.id, t]));
  const store = (heads.xl.store && heads.xl.store.tables) || {}, common = heads.xl.store && heads.xl.store.common;
  const blocks = xlBlocks();
  const busy = !!(heads.view && heads.view.job && heads.view.job.status === "running");
  const c = (s3 && s3.counts) || {}, k = c.calc || {}, ow = c.owners || {};
  const stats = el("div", "hstats");
  const stat = (v, label, title = "", cls = "") => { const s = el("span", cls); s.append(el("b", null, typeof v === "number" ? nf(v) : v), ` ${label}`); if (title) s.title = title; stats.append(s); };
  stat(blocks.length, "표", `문서의 표 블록(칸 안 표 ${nf(blocks.filter((b) => b.depth > 1).length)} 포함 · 1칸 표도)`);
  if (s3) {
    stat(`실행 ${s3.meta ? s3.meta.run ?? "–" : "–"}`, s3.stale ? "표 구조 · 오래됨" : "표 구조", s3.stale ? "문서가 바뀜 — 표 구조를 다시 만드세요" : `3단계 ${fmtWhen(s3.meta && s3.meta.at)}`, s3.stale ? "warn" : "");
    stat(k.tables || 0, "계산식 표", `수식 ${nf(k.formulas || 0)} — 일치 ${nf(k.ok || 0)} · 미검증 ${nf((k.blank || 0) + (k.incomplete || 0))}`);
    if (k.mismatch) stat(k.mismatch, "불일치", "엑셀 수식으로 다시 계산한 값과 문서 값이 다른 칸", "warn");
    stat((ow.stage2 || 0) + (ow.stage1 || 0), "소속", `헤딩에 매달린 표 — 2단계 그래프 ${nf(ow.stage2 || 0)} · 1단계 어림 ${nf(ow.stage1 || 0)}`);
  } else stat("없음", "표 구조", state.format === "docx" ? "3단계 표 구조는 hwpx 만" : "「표 구조 만들기」 를 누르면 소속·역할·합계/비율 수식이 채워집니다");
  stat(Object.values(store).filter((r) => r && r.instructions).length, "지침 있는 표", "표 지침(표 에이전트 입력)을 적어 둔 표");
  if (common && common.instructions) stat("있음", "공통 지침");
  box.append(stats);
  const acts = el("div", "hacts tb-acts");
  if (state.format !== "docx") {
    acts.append(hBtn("표 구조 만들기(스크립트)", () => headsStart(3, false), { disabled: busy, cls: "btn sm primary", title: "3단계 — 행헤더·열헤더·필드·서브 테이블 + 구분 헤더·계산식·엑셀 수식·소속(1초 안팎, LLM 없음)" }),
      hBtn("표 구조(LLM)", () => headsLlmTables(), { disabled: busy, title: "칸 역할·서브 테이블을 LLM 이 칸의 값을 보고 판정(유료, 수 분)" }),
      hBtn("표 보기(격자)", () => headsTables(), { disabled: !s3, title: "칸 역할 격자 · 수식 검증 · 필드 목록 — 2열" }));
  }
  acts.append(hBtn("공통 지침", () => tblAgentView("_common"), { title: "이 문서의 모든 표에 함께 주는 지침" }),
    hBtn(tblMarksOn() ? "표 도구 끄기" : "표 도구 표시", () => tblMarksToggle(), { title: "문서의 표마다 위 오른쪽 표지(표 id · 소속 · ⊞ · ✎)" }));
  box.append(acts);
  if (heads.view && heads.view.job && heads.view.job.stage === 3 && busy) box.append(el("p", "hnote", "표 구조를 만드는 중…"));
  if (!blocks.length) { box.append(el("p", "hnote", "이 문서에 표가 없습니다.")); return; }
  const [tbl, tb] = hTable(["#", "표", "크기", "소속", "구분", "계산식", "작성요령", "지침", ""]);
  tbl.classList.add("tb-list");
  blocks.forEach((b, i) => {
    const t = byId.get(b.id), rec = store[b.id], tr = el("tr");
    hCell(tr, i + 1);
    hCell(tr, `${b.id}${b.depth > 1 ? " (표 안 표)" : ""}`, null, `칸 ${nf(b.cells)}`);
    hCell(tr, `${b.rows}×${b.cols}`);
    const o = t && t.owner;
    const td = el("td", "txt");
    if (o && !o.root) {
      if (hasBlock(o.para)) td.append(hBtn(short(ownerLabel(o), 40), () => headsGo(o.para), { cls: "btn sm", title: (o.path || []).concat([o.text]).join(" › ") || "문서의 그 헤딩으로" }));
      else td.textContent = short(ownerLabel(o), 40);
      if (o.division && o.role !== "label") td.append(" ", el("span", "hb div", (o.division.basis || []).length ? `[${basisNames(o.division.basis)}]` : short(o.division.text, 14)));
    } else td.textContent = o && o.root ? "문서 뿌리" : t ? "—" : (s3 ? "표 구조에 없음" : "모름");
    tr.append(td);
    hCell(tr, t ? basisNames(t.basis) || "—" : "—");
    const kc = (t && t.calc) || {};
    hCell(tr, kc.is ? `수식 ${nf(kc.formulas)}${kc.mismatch ? ` · 불일치 ${nf(kc.mismatch)}` : ""}` : "—", kc.mismatch ? "warn" : null);
    hCell(tr, t && t.notes != null ? nf(Array.isArray(t.notes) ? t.notes.length : t.notes) : "—"); // 요약은 수, 3단계 전체 결과는 목록
    hCell(tr, rec && rec.instructions ? "있음" : "—", rec && rec.instructions ? "ok" : null, rec && rec.instructions ? short(rec.instructions, 80) : "");
    const act = el("td");
    const xl = hBtn("", () => xlColumn(b.id), { title: "엑셀식 보기 — 2열에 A1 격자" });
    xl.innerHTML = XL_ICON;
    xl.setAttribute("aria-label", "엑셀식 보기");
    act.append(xl, " ", hBtn("✎", () => tblAgentView(b.id), { title: "표 지침" }), " ");
    const host = t && t.host;
    if (host && hasBlock(host)) act.append(hBtn("자리로", () => headsGo(host), { title: "문서에서 이 표를 품은 문단으로" }));
    tr.append(act);
    tb.append(tr);
  });
  box.append(tbl);
}
