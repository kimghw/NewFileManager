"use strict";
// 표 구조 편집 모듈(spec_owpml_편집 ② §2 「자리」·② §4 「표 칸 고르기」, spec_헤딩_추출 ② §10 「모듈」) — 본문(app.js)·표 도구(tables.js)와 따로, 표의 칸 고르기와 행·열 넣기·지우기만 다룬다
// (사용자 2026-11-10 "본문 수정이랑 테이블 수정이랑은 좀 달리 관리" — astra 협의: 트랜잭션 structOp/_edit·실행 취소는 본문과 공유, 코드·init·사양·시험만 따로).
// app.js 가 주는 것: state·$·el·toast·readText·LS·paraEl·refreshToolbar·structOp·ctxOpen·ctxClose·divCtxItems(구분 기준 메뉴 항목). app.js 가 부르는 것(typeof 검사 뒤): tselClear(renderDoc) ·
// tselActive(refreshToolbar) · tableOpLabel(기록 탭). index.html 이 app.js·tables.js 다음에 읽고, 파일 끝의 tableEditInit() 이 이벤트·도구 줄 단추를 한 번 묶는다(bind 시점 typeof 로 건너뛰면 영구 미등록 — astra P1).

// ---------------------------------------------------------------- 표 칸 고르기 (spec_owpml_편집 ② §4 「표 칸 고르기」)
// 표 칸을 끌어 다른 칸에 닿으면 글 선택 대신 칸 묶음(직사각형 — 병합 칸은 통째)을 고른다. 고른 묶음은 복사(Ctrl+C: 탭 구분 글 + HTML 표),
// 행·열 넣기·지우기(도구 막대·오른쪽 단추 메뉴 — 고른 행·열 수만큼), Shift+누름·Shift+화살표로 늘리기, Esc·다른 곳 누름으로 품.
// 격자 좌표는 renderTable 이 칸에 둔 data-r·data-c(블록 row·col)·rowSpan·colSpan, 표 조각은 data-tbl 로 묶는다(쪽마다 나뉜 조각도 같은 표).
const tsel = { tbl: null, anchor: null, focus: null, cells: [], rect: null, press: null, hinted: false }; // 메뉴 상자는 app.js ctx.menu(공용)
const ARROW_STEP = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };

const tselActive = () => tsel.cells.length > 0 && !!tsel.anchor && tsel.anchor.isConnected;
const cellBox = (td) => { const r = +td.dataset.r, c = +td.dataset.c; return { r0: r, c0: c, r1: r + td.rowSpan - 1, c1: c + td.colSpan - 1 }; };
const tableOfCell = (td) => td.closest("table.tbl");
const tableCells = (tbl) => [...document.querySelectorAll(`#doc table.tbl[data-tbl="${CSS.escape(tbl)}"] > tbody > tr > td`)];
const cellParas = (td) => [...td.querySelectorAll(".para")].filter((p) => p.closest("td") === td); // 칸 바로 안 문단(안쪽 표의 칸 제외)

function cellOf(node, tbl = null) {
  // node 를 품은 표 칸 — tbl(표 id)이 있으면 그 표의 칸(안쪽 표 안이면 바깥 표 칸으로 올라감), 없으면 가장 안쪽 칸
  let td = node && (node.nodeType === 1 ? node : node.parentElement);
  td = td && td.closest ? td.closest("#doc td") : null;
  if (!td || !td.dataset.r) return null;
  if (tbl == null) return td;
  while (td) {
    const t = tableOfCell(td);
    if (t && t.dataset.tbl === tbl) return td;
    td = t && t.parentElement ? t.parentElement.closest("td") : null;
  }
  return null;
}

function cellAt(tbl, r, c) { return tableCells(tbl).find((td) => { const b = cellBox(td); return b.r0 <= r && r <= b.r1 && b.c0 <= c && c <= b.c1; }) || null; }

function tselSet(anchor, focus) {
  const tbl = tableOfCell(anchor).dataset.tbl;
  const all = tableCells(tbl);
  const a = cellBox(anchor), f = cellBox(focus);
  const rect = { r0: Math.min(a.r0, f.r0), c0: Math.min(a.c0, f.c0), r1: Math.max(a.r1, f.r1), c1: Math.max(a.c1, f.c1) };
  for (let grown = true; grown;) { // 병합 칸이 범위에 걸치면 그 칸 전부가 들어가게 넓힌다(직사각형 유지)
    grown = false;
    for (const td of all) {
      const b = cellBox(td);
      if (b.r1 < rect.r0 || b.r0 > rect.r1 || b.c1 < rect.c0 || b.c0 > rect.c1) continue;
      const n = { r0: Math.min(rect.r0, b.r0), c0: Math.min(rect.c0, b.c0), r1: Math.max(rect.r1, b.r1), c1: Math.max(rect.c1, b.c1) };
      if (n.r0 !== rect.r0 || n.c0 !== rect.c0 || n.r1 !== rect.r1 || n.c1 !== rect.c1) { Object.assign(rect, n); grown = true; }
    }
  }
  const cells = all.filter((td) => { const b = cellBox(td); return b.r0 >= rect.r0 && b.r1 <= rect.r1 && b.c0 >= rect.c0 && b.c1 <= rect.c1; });
  tselPaint(false);
  Object.assign(tsel, { tbl, anchor, focus, cells, rect });
  tselPaint(true);
  $("doc").classList.add("cellsel");
  tselSync();
  if (!tsel.hinted && cells.length > 1) { tsel.hinted = true; toast("표 칸을 골랐습니다 — Ctrl+C 복사 · 도구 막대/오른쪽 단추로 행·열 넣기·지우기 · Esc 풀기"); }
}

function tselPaint(on) { for (const td of tsel.cells) td.classList.toggle("sel", on); }

function tselClear() {
  if (!tsel.tbl && !tsel.cells.length) return;
  tselPaint(false);
  Object.assign(tsel, { tbl: null, anchor: null, focus: null, cells: [], rect: null });
  $("doc").classList.remove("cellsel");
  tselSync();
}

function tselCounts() { const r = tsel.rect; return r ? { rows: r.r1 - r.r0 + 1, cols: r.c1 - r.c0 + 1 } : { rows: 1, cols: 1 }; }

function tselSync() {
  // 도구 막대 표 단추 — 고른 행·열 수를 이름에(「행↑ 2개 넣기」), 아니면 원래 이름
  const { rows, cols } = tselActive() ? tselCounts() : { rows: 1, cols: 1 };
  for (const b of document.querySelectorAll("#tbTable button")) {
    if (!b.dataset.base) b.dataset.base = b.textContent;
    const n = b.dataset.table.startsWith("row") ? rows : cols;
    b.textContent = n > 1 ? b.dataset.base.replace(" ", ` ${n}개 `) : b.dataset.base;
  }
  refreshToolbar();
}

function tselEnter() {
  // 글 선택 → 칸 선택으로: 브라우저 글 선택을 걷고 편집 상자 포커스를 뺀다(칸 선택 중 타자가 문단에 들어가지 않게)
  getSelection().removeAllRanges();
  const a = document.activeElement;
  if (a && a.classList && a.classList.contains("para")) a.blur();
}

function tselStep([dr, dc]) {
  const f = cellBox(tsel.focus);
  const r = dr < 0 ? f.r0 - 1 : dr > 0 ? f.r1 + 1 : f.r0;
  const c = dc < 0 ? f.c0 - 1 : dc > 0 ? f.c1 + 1 : f.c0;
  const td = r >= 0 && c >= 0 ? cellAt(tsel.tbl, r, c) : null;
  if (td) tselSet(tsel.anchor, td);
}

function tselAnchorId() {
  // 서버에 보낼 기준 블록 — 앵커 칸의 첫 문단, 문단이 없는 칸(안쪽 표만)이면 칸 id
  const p = cellParas(tsel.anchor)[0];
  return p ? p.dataset.id : tsel.anchor.dataset.cell || null;
}

function tselText() {
  // 고른 칸 → 탭 구분 글(행마다 줄, 병합 칸은 왼쪽 위 자리에만, 줄 바꿈·탭·따옴표가 든 칸은 "…" 로 감쌈) + HTML 표(rowspan·colspan 유지)
  const r = tsel.rect;
  const grid = Array.from({ length: r.r1 - r.r0 + 1 }, () => Array(r.c1 - r.c0 + 1).fill(""));
  const rows = Array.from({ length: r.r1 - r.r0 + 1 }, () => []);
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  for (const td of [...tsel.cells].sort((x, y) => +x.dataset.r - +y.dataset.r || +x.dataset.c - +y.dataset.c)) {
    const b = cellBox(td);
    const text = cellParas(td).map((p) => readText(p).replaceAll(LS, "\n")).join("\n");
    grid[b.r0 - r.r0][b.c0 - r.c0] = /[\t\n"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    const span = `${td.rowSpan > 1 ? ` rowspan="${td.rowSpan}"` : ""}${td.colSpan > 1 ? ` colspan="${td.colSpan}"` : ""}`;
    rows[b.r0 - r.r0].push(`<td${span}>${esc(text).replace(/\n/g, "<br>")}</td>`);
  }
  return { tsv: grid.map((row) => row.join("\t")).join("\n"), html: `<table><tbody>${rows.map((tds) => `<tr>${tds.join("")}</tr>`).join("")}</tbody></table>` };
}

async function tselCopy(e = null) {
  if (!tselActive()) return false;
  const { tsv, html } = tselText();
  if (e && e.clipboardData) {
    e.clipboardData.setData("text/plain", tsv);
    e.clipboardData.setData("text/html", html);
    e.preventDefault();
  } else if (navigator.clipboard && window.ClipboardItem) {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "text/plain": new Blob([tsv], { type: "text/plain" }), "text/html": new Blob([html], { type: "text/html" }) })]);
    } catch {
      try { await navigator.clipboard.writeText(tsv); } catch { toast("복사하지 못했습니다 — 브라우저가 클립보드 쓰기를 막았습니다", true); return true; }
    }
  } else { toast("이 브라우저에서는 칸 복사를 못 합니다(클립보드 API 없음)", true); return true; }
  const { rows, cols } = tselCounts();
  toast(`표 칸 ${tsel.cells.length}개(${rows}행 × ${cols}열) 복사 — 탭 구분 글 + HTML 표`);
  return true;
}

function tselContextMenu(e) {
  const td = cellOf(e.target);
  if (!td || !state.id) return; // 표 밖은 브라우저 메뉴 그대로
  e.preventDefault();
  const tbl = tableOfCell(td).dataset.tbl;
  const inSel = tselActive() && tsel.tbl === tbl && tsel.cells.includes(cellOf(e.target, tbl));
  if (!inSel) { tselEnter(); tselSet(td, td); } // 고른 범위 밖 칸을 오른쪽 단추 — 그 칸 하나를 고른다
  const { rows, cols } = tselCounts();
  const n = (k) => (k > 1 ? `${k}개 ` : "");
  const busy = state.busy;
  ctxOpen(e, [
    [`칸 ${tsel.cells.length}개 복사`, "Ctrl+C", () => tselCopy()],
    null,
    [`행 ${n(rows)}위에 넣기`, "", () => tableOp("row_above"), busy],
    [`행 ${n(rows)}아래에 넣기`, "", () => tableOp("row_below"), busy],
    [`행 ${n(rows)}지우기`, "", () => tableOp("row_delete"), busy],
    null,
    [`열 ${n(cols)}왼쪽에 넣기`, "", () => tableOp("col_left"), busy],
    [`열 ${n(cols)}오른쪽에 넣기`, "", () => tableOp("col_right"), busy],
    [`열 ${n(cols)}지우기`, "", () => tableOp("col_delete"), busy],
    null,
    ...divCtxItems(e), // 구분 기준 자리로 추가(spec_구분_기준 ② §11)
    ["선택 풀기", "Esc", () => tselClear()],
  ]);
}

// ---------------------------------------------------------------- 행·열 넣기·지우기(도구 줄 「테이블 수정」 묶음 · 오른쪽 단추 메뉴 → structOp("table") — 트랜잭션은 본문과 공유)
const TABLE_OP = { row_above: "위에 행 넣기", row_below: "아래에 행 넣기", row_delete: "행 지우기", col_left: "왼쪽에 열 넣기",
  col_right: "오른쪽에 열 넣기", col_delete: "열 지우기" };
const tableOpLabel = (op) => TABLE_OP[op] || op; // 기록 탭(app.js)

function tableOp(op) {
  // 끌어 고른 칸 묶음(tsel)이 있으면 그 범위(격자 좌표)의 행·열 수만큼, 아니면 커서가 있는 칸이 걸친 행·열
  const sel = tselActive() ? tsel : null;
  const c = state.cur;
  const p = sel ? null : c && paraEl(c.id);
  if (!sel && (!p || !p.closest("td"))) { toast("표 칸 안의 문단을 누르거나 칸을 끌어 고른 뒤에 쓰세요"); return; }
  const what = op.startsWith("row") ? "행" : "열";
  const n = sel ? (what === "행" ? tselCounts().rows : tselCounts().cols) : 1;
  if (op.endsWith("delete") && !confirm(n > 1 ? `고른 ${what} ${n}개를 지울까요?` : `이 칸이 걸친 ${what}을 지울까요?`)) return;
  const id = sel ? tselAnchorId() : c.id;
  if (!id) { toast("고른 칸에 문단이 없습니다"); return; }
  return structOp("table", sel ? { id, op, range: { ...sel.rect } } : { id, op }).then((r) => { if (r) tselClear(); });
}

// ---------------------------------------------------------------- 묶기
let tableEditBound = false;
function tableEditInit() { // 한 번만 — 표 칸 끌어 고르기·복사·오른쪽 단추 메뉴·키, 도구 줄 [data-table] 단추
  if (tableEditBound) return;
  tableEditBound = true;
  for (const b of document.querySelectorAll("#docBar [data-table]")) b.onclick = () => tableOp(b.dataset.table);
  bindCellSelect();
}

function bindCellSelect() {
  const doc = $("doc");
  doc.addEventListener("mousedown", (e) => {
    ctxClose();
    if (e.button !== 0) return;
    const td = cellOf(e.target);
    if (!td) { tselClear(); return; }
    if (e.shiftKey && tselActive() && tableOfCell(td).dataset.tbl === tsel.tbl) { // Shift+누름 = 앵커부터 이 칸까지
      e.preventDefault();
      tselSet(tsel.anchor, cellOf(e.target, tsel.tbl));
      return;
    }
    tselClear();
    tsel.press = td; // 같은 칸 안에서는 글 선택, 다른 칸에 닿으면 칸 선택(mousemove)
  });
  doc.addEventListener("mousemove", (e) => {
    const start = tsel.press;
    if (!start) return;
    if (!(e.buttons & 1) || !start.isConnected) { tsel.press = null; return; }
    const tbl = tableOfCell(start).dataset.tbl;
    const td = cellOf(e.target, tbl);
    if (!td || (td === start && !tselActive())) return; // 표 밖이면 마지막 칸까지 유지, 같은 칸 안은 글 선택 그대로
    if (!tselActive()) tselEnter();
    if (td !== tsel.focus) tselSet(start, td);
  });
  document.addEventListener("mouseup", () => { tsel.press = null; if (tselActive()) getSelection().removeAllRanges(); });
  document.addEventListener("selectionchange", () => { if (tselActive() && tsel.press && getSelection().rangeCount) getSelection().removeAllRanges(); }); // 끄는 동안 브라우저가 다시 만드는 글 선택
  doc.addEventListener("contextmenu", tselContextMenu);
  doc.addEventListener("beforeinput", (e) => { if (tselActive()) e.preventDefault(); });
  document.addEventListener("copy", (e) => { if (tselActive() && !(e.target.closest && e.target.closest("input, textarea"))) tselCopy(e); });
  document.addEventListener("keydown", (e) => {
    if (!tselActive()) return;
    if (e.target.closest && e.target.closest("input, textarea, select, [contenteditable], dialog, .ctx-menu")) return; // 다른 입력 칸·메뉴의 키는 그대로
    const mod = (e.ctrlKey || e.metaKey) && !e.altKey;
    if (e.key === "Escape") { e.preventDefault(); tselClear(); return; }
    if (mod && !e.shiftKey && e.key.toLowerCase() === "c") {
      if (navigator.clipboard && window.ClipboardItem) { e.preventDefault(); tselCopy(); } // 아니면 copy 이벤트에 맡김
      return;
    }
    if (e.shiftKey && !mod && ARROW_STEP[e.key]) { e.preventDefault(); tselStep(ARROW_STEP[e.key]); return; }
    if (!mod && (e.key.length === 1 || ["Backspace", "Delete", "Enter", "Tab"].includes(e.key))) e.preventDefault(); // 칸 선택 중 타자는 무시(글은 칸을 눌러 고침)
  });
}

tableEditInit();
