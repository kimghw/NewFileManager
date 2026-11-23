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
// 쪽에 걸쳐 나뉜 칸(app.js 「행 안 나눔」 — 이어짐 칸 td.cell-cont 가 같은 data-cell·data-r·data-c 로 쪽마다 하나씩)은 화면 rowSpan 이 그 조각의 행 수라 모델 값 data-rs 를 먼저 본다
const cellBox = (td) => { const r = +td.dataset.r, c = +td.dataset.c; return { r0: r, c0: c, r1: r + (+td.dataset.rs || td.rowSpan) - 1, c1: c + td.colSpan - 1 }; };
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
  if (!tsel.hinted && cells.length > 1) { tsel.hinted = true; toast("표 칸을 골랐습니다 — Ctrl+C 복사 · M 합치기 · S 나누기 · 오른쪽 단추로 칸·행·열 넣기·지우기 · Esc 풀기"); }
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
    if (td.classList.contains("cell-cont")) continue; // 쪽에 걸쳐 나뉜 칸의 뒷부분 — 원래 칸에서 조각 글을 모아 한 번만
    const b = cellBox(td), rs = b.r1 - b.r0 + 1;
    const parts = td.dataset.rs ? tsel.cells.filter((x) => x.dataset.cell === td.dataset.cell) : [td]; // 문서 차례(원래 칸 → 이어짐 칸)
    const text = parts.flatMap(cellParas).map((p) => readText(p).replaceAll(LS, "\n")).join("\n");
    grid[b.r0 - r.r0][b.c0 - r.c0] = /[\t\n"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    const span = `${rs > 1 ? ` rowspan="${rs}"` : ""}${td.colSpan > 1 ? ` colspan="${td.colSpan}"` : ""}`;
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

// ---------------------------------------------------------------- 칸 메뉴 상자 · 문서 미리보기 (spec_owpml_편집 ② §5-5)
// 공용 오른쪽 단추 메뉴(app.js ctxOpen — 하나뿐)를 빌려 항목마다 도움말·분류·미리보기를 얹는다(table_menu.js tmnOpen 과 같은 방식 — 상자에 data-by="tsel").
// 하위 목록(▸)은 같은 자리에서 내용만 바꾸고 맨 위 「‹ …」 로 돌아간다(design.md §8). 항목에 마우스를 올리거나 키로 옮기면 그 동작이 닿는 칸을 문서에 칠한다(tprev).
const tmenu = { anchor: null, ev: null, watching: false, seq: 0, live: 0 };
const tNoop = () => {};
const tHwpx = () => state.format !== "docx";
const TP_CLASSES = ["tp", "tp-del", "tp-part", "tp-ins-b", "tp-ins-t", "tp-ins-l", "tp-ins-r", "tp-merge", "tp-split", "tp-fit", "tp-move"];
const tctxMine = () => !!ctx.menu && !ctx.menu.hidden && ctx.menu.dataset.by === "tsel";

function tctxOpen(items, anchor = null) { // items: [글, 꼬리, 실행, 꺼짐, {title, cls, enter}] | null(구분선) — enter = 마우스를 올리거나 포커스가 갈 때(문서 미리보기)
  if (anchor) tmenu.anchor = { clientX: anchor.clientX, clientY: anchor.clientY };
  if (!tmenu.anchor) return;
  const m = ctxMenu();
  if (!tmenu.watching) { // 메뉴가 닫히면(바깥 누름·스크롤·Esc — app.js ctxClose) 미리보기를 걷는다. 하위 목록으로 바꾸는 동안은 닫혔다 바로 열린다 — 지금 상태로 본다
    tmenu.watching = true;
    new MutationObserver(() => { if (m.hidden && m.dataset.by === "tsel") { delete m.dataset.by; tprev(null); } }).observe(m, { attributes: true, attributeFilter: ["hidden"] });
  }
  tprev(null);
  m.dataset.by = "tsel"; // 자리 잡기 전에 — table-menu.css 의 최대 높이·폭이 걸린 크기로 잰다
  ctxOpen(tmenu.anchor, items.map((it) => (it ? it.slice(0, 4) : null)));
  const btns = [...m.querySelectorAll("button")];
  let k = 0;
  for (const it of items) {
    if (!it) continue;
    const b = btns[k++], o = it[4];
    if (!b || !o) continue;
    if (o.title) b.title = o.title;
    if (o.cls) b.classList.add(...o.cls.split(" "));
    if (o.enter) {
      b.addEventListener("mouseenter", o.enter);
      b.addEventListener("focus", o.enter);
      b.addEventListener("mouseleave", () => tprev(null));
      b.addEventListener("blur", () => tprev(null));
    }
  }
}

function tprev(marks) { // marks = null(걷기) | [[칸, 클래스, {rows, cols}?]…] — 한 칸에 표시 하나(먼저 온 것)
  if (!marks) tmenu.live = 0; // 올려 둔 항목이 없다 — 늦게 온 layout 으로 다시 칠하지 않는다(tprevOp)
  for (const td of document.querySelectorAll("#doc td.tp")) {
    td.classList.remove(...TP_CLASSES);
    for (const v of ["--tp-rows", "--tp-cols", "--tp-rl", "--tp-cl"]) td.style.removeProperty(v);
  }
  const seen = new Set();
  for (const [td, cls, o] of marks || []) {
    if (seen.has(td)) continue;
    seen.add(td);
    td.classList.add("tp", cls);
    if (o) {
      td.style.setProperty("--tp-rows", o.rows || 1);
      td.style.setProperty("--tp-cols", o.cols || 1);
      if ((o.rows || 1) > 1) td.style.setProperty("--tp-rl", "#2458d6");
      if ((o.cols || 1) > 1) td.style.setProperty("--tp-cl", "#2458d6");
    }
  }
}

function tcolKeep(flags, nc, c0, c1, add) { // 폭을 나눠 가질 열 범위 [a, b] — 서버 table_ops.col_keep 과 같은 규칙(② §5-1). 판정(flags)이 없으면 null
  if (!flags || flags.length !== nc) return null;
  let a = c0, b = c1;
  for (let c = c0; c <= c1; c++) if (!flags[c]) { a = 0; b = nc - 1; break; }
  if (a === c0 && b === c1) {
    while (a > 0 && flags[a - 1]) a -= 1;
    while (b < nc - 1 && flags[b + 1]) b += 1;
    if (!add && b - a === c1 - c0) { a = 0; b = nc - 1; }
  }
  return add || b - a > c1 - c0 ? [a, b] : null;
}

function tprevPlan(op, tbl, rect, opts = {}) {
  // 그 동작이 닿는 칸 → [[칸, 클래스, 값?]…]. 서버 격자 규칙(table_grid — clone·drop_band·drop_cols·col_widths)과 같은 판정을 화면 칸 좌표(data-r/c·rowSpan/colSpan)로:
  // tp-del 지워짐 · tp-part 늘어나거나 줄어듦(합친 칸) · tp-ins-* 새 칸이 들어갈 변 · tp-merge 합쳐짐 · tp-split 나뉠 자리 · tp-fit 폭이 바뀌는 필드 열 · tp-move 뒤 표로 갈 열
  const out = [], cells = tableCells(tbl).map((td) => [td, cellBox(td)]);
  if (op === "tsplit") { for (const [td, b] of cells) if (b.c0 >= opts.cut) out.push([td, "tp-move"]); return out; }
  const { r0, c0, r1, c1 } = rect;
  const inR = (b) => b.r0 >= r0 && b.r1 <= r1, inC = (b) => b.c0 >= c0 && b.c1 <= c1;
  const hitR = (b) => b.r0 <= r1 && b.r1 >= r0, hitC = (b) => b.c0 <= c1 && b.c1 >= c0;
  const fit = (add) => { // 폭이 바뀌는 열(필드 열 묶음 — layout 을 읽은 뒤에만)
    const lay = opts.lay, run = lay ? tcolKeep(lay.fieldCols, lay.cols, c0, c1, add) : null;
    if (run) for (const [td, b] of cells) if (b.c0 >= run[0] && b.c1 <= run[1] && !(hitC(b) && !add)) out.push([td, "tp-fit"]);
  };
  if (op === "row_delete" || op === "cells_delete") {
    for (const [td, b] of cells) if (hitR(b)) out.push([td, inR(b) ? "tp-del" : "tp-part"]);
  } else if (op === "row_above" || op === "row_below" || op === "cells_above" || op === "cells_below" || op === "cells_copy") {
    const above = op.endsWith("above"), band = op.startsWith("cells"), edge = above ? r0 : r1;
    if (band && r1 > r0) { // 나뉜 필드에 맞춰(② §5-2 — 서버 table_grid.clone_inside 와 같은 판정): 고른 칸이 r0..r1 을 다 덮는 한 줄이고 열 밖 칸이 그 사이에서 나뉘면 새 칸은 고른 칸 안의 나뉜 줄로 — 늘어나는 칸 없음
      const inBand = cells.filter(([, b]) => hitR(b) && hitC(b));
      const fits = inBand.length && inBand.every(([, b]) => inC(b) && b.r0 === r0 && b.r1 === r1)
        && cells.some(([, b]) => !hitC(b) && b.r0 > r0 && b.r0 <= r1);
      if (fits) { for (const [td] of inBand) out.push([td, above ? "tp-ins-t" : "tp-ins-b"]); return out; }
    }
    for (const [td, b] of cells) {
      if (!hitR(b)) continue;
      if ((!band || inC(b)) && inR(b)) { if (above ? b.r0 === r0 : b.r1 === r1) out.push([td, above ? "tp-ins-t" : "tp-ins-b"]); }
      else if (b.r0 <= edge && edge <= b.r1) out.push([td, "tp-part"]);
    }
  } else if (op === "col_delete") {
    for (const [td, b] of cells) if (hitC(b)) out.push([td, inC(b) ? "tp-del" : "tp-part"]);
    fit(false);
  } else if (op === "col_left" || op === "col_right") {
    const left = op === "col_left";
    for (const [td, b] of cells) {
      if (!hitC(b)) continue;
      if (!inC(b)) out.push([td, "tp-part"]);
      else if (left ? b.c0 === c0 : b.c1 === c1) out.push([td, left ? "tp-ins-l" : "tp-ins-r"]);
    }
    fit(true);
  } else if (op === "cols_even") { // 열 폭 같게 — 고른 열들, 하나면 그 열을 품은 필드 열 묶음(layout 을 읽은 뒤)
    let a = c0, b = c1;
    const f = opts.lay ? opts.lay.fieldCols : null;
    if (a === b && f && f[a]) { while (a > 0 && f[a - 1]) a -= 1; while (b < f.length - 1 && f[b + 1]) b += 1; }
    if (b > a) for (const [td, x] of cells) if (x.c0 >= a && x.c1 <= b) out.push([td, "tp-fit"]);
  } else if (op === "merge") {
    for (const [td, b] of cells) if (inR(b) && inC(b)) out.push([td, "tp-merge"]);
  } else if (op === "unmerge") {
    for (const [td, b] of cells) if (inR(b) && inC(b) && (b.r1 > b.r0 || b.c1 > b.c0)) out.push([td, "tp-split", { rows: b.r1 - b.r0 + 1, cols: b.c1 - b.c0 + 1 }]);
  } else if (op === "split") {
    for (const [td, b] of cells) {
      if (inR(b) && inC(b)) out.push([td, "tp-split", { rows: opts.rows || 1, cols: opts.cols || 1 }]);
      else if (opts.keep === "cell" && (opts.rows || 1) > 1 && hitR(b)) out.push([td, "tp-part"]); // 새 행이 들어가 그 행의 다른 칸이 늘어난다(표가 늘어남)
    }
  }
  return out;
}

function tprevTarget() { // 미리보기·동작의 대상 — 끌어 고른 칸 묶음, 없으면 커서가 있는 칸
  if (tselActive()) return { tbl: tsel.tbl, rect: tsel.rect };
  const p = state.cur && paraEl(state.cur.id), td = p ? p.closest("td") : null;
  return td && td.dataset.r ? { tbl: tableOfCell(td).dataset.tbl, rect: cellBox(td) } : null;
}

function tprevOp(op, opts = {}) { // 메뉴 항목·도구 줄 단추에 올렸을 때 — 열 동작은 layout(필드 열)을 읽어 폭이 바뀌는 열도 칠한다(늦게 오면 그때 다시)
  const t = tprevTarget();
  if (!t) return;
  const seq = ++tmenu.seq;
  const lay = op.startsWith("col") && tHwpx() ? tlayCached(t.tbl) : null;
  tprev(tprevPlan(op, t.tbl, t.rect, { ...opts, lay }));
  tmenu.live = seq; // 이 항목에 올려 둔 동안(떠나면 tprev(null) 이 0 으로)
  if (op.startsWith("col") && tHwpx() && !lay) {
    tlayLoad(t.tbl).then((l) => { if (l && tmenu.live === seq) { tprev(tprevPlan(op, t.tbl, t.rect, { ...opts, lay: l })); tmenu.live = seq; } }).catch(tNoop);
  }
}

// ---- 한 표의 판정(layout — 필드 열·헤더 열·필드 열 단위·이어진 표): 서버 `GET …/tables/{tid}/layout`. 구조 편집·헤더 지정이 바뀌면 다시 읽는다
const tlay = { key: null, data: null, pending: null, ver: 0 };
const tlayKey = (tid) => `${state.id}|${state.epoch}|${tid}|${state.structRev}|${state.localRev}|${tlay.ver}`;
const tlayCached = (tid) => (tlay.key === tlayKey(tid) ? tlay.data : null);
function tlayLoad(tid) {
  const key = tlayKey(tid);
  if (tlay.key === key && tlay.data) return Promise.resolve(tlay.data);
  if (tlay.pending && tlay.pending.key === key) return tlay.pending.p;
  const p = api(`/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/layout`).then((d) => {
    if (tlayKey(tid) === key) { tlay.key = key; tlay.data = d; }
    return d;
  }).finally(() => { if (tlay.pending && tlay.pending.key === key) tlay.pending = null; });
  tlay.pending = { key, p };
  return p;
}
const tErr = (e, what) => (e && e.status === 404 && e.message === "Not Found" ? `서버가 옛 판입니다 — 서버를 다시 켜야 「${what}」 를 쓸 수 있습니다` : e.message);

// ---------------------------------------------------------------- 칸 오른쪽 단추 메뉴
function tselContextMenu(e) {
  const td = cellOf(e.target);
  if (!td || !state.id) return; // 표 밖은 브라우저 메뉴 그대로
  e.preventDefault();
  const tbl = tableOfCell(td).dataset.tbl;
  const inSel = tselActive() && tsel.tbl === tbl && tsel.cells.includes(cellOf(e.target, tbl));
  if (!inSel) { tselEnter(); tselSet(td, td); } // 고른 범위 밖 칸을 오른쪽 단추 — 그 칸 하나를 고른다
  tmenu.ev = e;
  tselMenu(e);
}

function tselMenu(anchor = null) { // 맨 위 목록 — 고른 칸(칸 단위) · 행·열 전체 · 헤더 지정 ▸ · 표 나누기 ▸ · 다른 모듈의 항목
  if (!tselActive()) return;
  const e = tmenu.ev, tbl = tsel.tbl;
  const { rows, cols } = tselCounts();
  const n = (k) => (k > 1 ? `${k}개 ` : "");
  const busy = state.busy, hwpx = tHwpx(), only = hwpx ? "" : "\n지금 hwpx 문서만 됩니다";
  const many = tsel.cells.filter((td) => !td.classList.contains("cell-cont")).length > 1;
  const merged = tsel.cells.some((td) => { const b = cellBox(td); return b.r1 > b.r0 || b.c1 > b.c0; });
  const it = (label, key, op, title, opts) => [label, key, () => tableOp(op, opts), busy, { title, enter: () => tprevOp(op, opts) }];
  const grow = "고른 열 밖에서 그 자리를 덮는 칸(왼쪽 헤더)은 복사하지 않고 늘어납니다\n고른 칸이 옆 열에서 나뉜 줄에 걸쳐 있으면 그 나뉜 줄에 맞춰 고른 칸 안에 넣습니다 — 표 크기·옆 칸 높이는 그대로";
  const items = [
    [`칸 ${tsel.cells.length}개 복사`, "Ctrl+C", () => tselCopy()],
    null,
    [`고른 칸 — ${rows}행 × ${cols}열`, "", tNoop, true, { cls: "tmn-sec" }],
    it("고른 칸만 아래에 넣기", "", "cells_below", `고른 칸과 같은 구조의 빈 칸을 바로 아래에 — ${grow}`),
    it("고른 칸만 아래에 복사", "", "cells_copy", `고른 칸을 글째 바로 아래에 복사 — 나뉜 칸·합친 칸 구조 그대로 · ${grow}`),
    it("고른 칸만 위에 넣기", "", "cells_above", `고른 칸과 같은 구조의 빈 칸을 바로 위에 — ${grow}`),
    it("고른 칸 줄 지우기", "", "cells_delete", "고른 칸의 줄을 없앱니다 — 그 줄을 지나는 합친 칸(왼쪽 헤더)은 줄어들고, 그 줄에 통째로 든 칸은 함께 지워집니다(빨강)"),
  ];
  if (many) items.push(it("칸 합치기", "M", "merge", "고른 칸을 한 칸으로 — 글은 위→아래·왼쪽→오른쪽 차례로 이어 붙습니다"));
  else if (merged) items.push(it("합친 칸 풀기", "", "unmerge", "합친 칸을 원래 격자 칸으로 — 글은 왼쪽 위 칸에 남습니다"));
  items.push(
    ["칸 나누기", "S ▸", () => tsplitCellMenu(), busy, { title: "고른 칸마다 위아래·좌우로 나눕니다 — 표 크기 그대로 / 칸 크기 그대로(표가 늘어남)" }],
    null,
    ["행·열 전체", "", tNoop, true, { cls: "tmn-sec" }],
    it(`행 ${n(rows)}위에 넣기`, "", "row_above", "고른 행과 같은 구조의 빈 행을 위에 — 그 행에 일부만 걸친 합친 칸(바깥 묶음 제목)은 늘어납니다"),
    it(`행 ${n(rows)}아래에 넣기`, "", "row_below", "고른 행과 같은 구조의 빈 행을 아래에 — 그 행에 일부만 걸친 합친 칸(바깥 묶음 제목)은 늘어납니다"),
    it(`행 ${n(rows)}지우기`, "", "row_delete", "고른 행을 지웁니다 — 그 행을 지나는 합친 칸은 글째 남아 줄어듭니다"),
    it(`열 ${n(cols)}왼쪽에 넣기`, "", "col_left", "빈 열을 왼쪽에 — 표 폭·헤더 열 폭은 그대로, 필드 열들이 비율대로 좁아집니다"),
    it(`열 ${n(cols)}오른쪽에 넣기`, "", "col_right", "빈 열을 오른쪽에 — 표 폭·헤더 열 폭은 그대로, 필드 열들이 비율대로 좁아집니다"),
    it(`열 ${n(cols)}지우기`, "", "col_delete", "고른 열을 지웁니다 — 표 폭·헤더 열 폭은 그대로, 남은 필드 열들이 비율대로 넓어집니다"),
    it(cols > 1 ? `열 ${cols}개 폭 같게` : "필드 열 폭 같게", "", "cols_even",
      cols > 1 ? "고른 열들이 지금 합계 폭을 똑같이 나눠 갖습니다 — 표 폭·다른 열은 그대로" : `이 열과 이어진 필드 열들이 합계 폭을 똑같이 나눠 갖습니다 — 표 폭·헤더 열 폭은 그대로${hwpx ? "" : "\ndocx 는 열을 둘 이상 끌어 고르세요"}`),
    null,
    ["헤더 지정", "▸", () => theadsMenu(), !hwpx, { title: `고른 칸을 행헤더·열헤더·필드로 직접 지정 · 구분 라벨로 지정${only}` }],
    ["표 나누기", "▸", () => tsplitMenu(tbl, () => tselMenu(), null, tsel.rect ? tsel.rect.c0 : null), !hwpx || busy,
      { title: `필드 열을 나눠 표 2개로(헤더 열은 두 표에 똑같이) · 나눈 표를 다시 나누기 · 다시 합치기${only}` }],
    ...(e ? divCtxItems(e) : []), // 구분 기준 자리로 추가(spec_구분_기준 ② §11)
    ...(typeof xlCellItems === "function" ? xlCellItems(tbl) : []), // 고른 칸 엑셀식 보기 — 수식 판정(tables.js — spec_헤딩_추출 ② §14)
    ...(typeof tmkCellItems === "function" ? tmkCellItems(tbl) : []), // 표 만들기 · 서식 변환(table_make.js — spec_헤딩_추출 ② §11): 「이 표를 표 양식으로」·「양식 서식으로 변환…」
    ...(e && typeof tempCtxItems === "function" ? tempCtxItems(e) : []), // TEMP 로 지정·해제(heading_temp.js — spec_헤딩_추출 ② §15)
    ...(e && typeof oltCtxItems === "function" ? oltCtxItems(e) : []), // 표 칸 안 개요 줄의 「레터 고치기…」(outline_tune.js — spec_hwpx_웹편집 ② §8-12)
    ["선택 풀기", "Esc", () => tselClear()],
  );
  tctxOpen(items, anchor);
}

function tselAnchorAt() { // 키로 연 메뉴의 자리 — 포커스 칸의 왼쪽 아래(화면 밖이면 보기 안으로)
  const r = (tsel.focus || tsel.anchor).getBoundingClientRect();
  return { clientX: Math.max(8, Math.min(r.left + 12, innerWidth - 60)), clientY: Math.max(8, Math.min(r.bottom - 4, innerHeight - 60)) };
}

function tsplitCellMenu(anchor = null) { // 「칸 나누기 ▸」 — 위아래(표 크기 그대로 | 칸 크기 그대로) · 좌우(표 폭 그대로)
  if (!tselActive()) return;
  const busy = state.busy, hwpx = tHwpx();
  const k = tsel.cells.filter((td) => !td.classList.contains("cell-cont")).length;
  const it = (label, opts, title, off = false) => [label, "", () => tableOp("split", opts), busy || off, { title, enter: () => tprevOp("split", opts) }];
  const same = (r) => `고른 칸마다 위아래 ${r}칸 — 그 칸의 높이를 나눠 갖습니다(행 높이·표 높이 그대로)`;
  const tall = (r) => `고른 칸마다 위아래 ${r}칸 — 조각마다 원래 칸 높이: 새 행이 들어가 표가 늘어나고, 그 행의 다른 칸은 늘어나 걸칩니다${hwpx ? "" : "\n지금 hwpx 문서만 됩니다"}`;
  const items = [
    [`‹ 칸 나누기 — 고른 칸 ${k}개`, "", () => tselMenu(), false, { cls: "tmn-back", title: "칸 메뉴로" }],
    null,
    ["위아래로", "", tNoop, true, { cls: "tmn-sec" }],
    it("2칸 — 표 크기 그대로", { rows: 2, cols: 1, keep: "table" }, same(2)),
    it("2칸 — 칸 크기 그대로(표가 늘어남)", { rows: 2, cols: 1, keep: "cell" }, tall(2), !hwpx),
    it("3칸 — 표 크기 그대로", { rows: 3, cols: 1, keep: "table" }, same(3)),
    it("3칸 — 칸 크기 그대로(표가 늘어남)", { rows: 3, cols: 1, keep: "cell" }, tall(3), !hwpx),
    ["좌우로 — 표 폭 그대로", "", tNoop, true, { cls: "tmn-sec" }],
    it("2칸", { rows: 1, cols: 2, keep: "table" }, "고른 칸마다 좌우 2칸 — 그 칸의 폭을 나눠 갖습니다"),
    it("3칸", { rows: 1, cols: 3, keep: "table" }, "고른 칸마다 좌우 3칸 — 그 칸의 폭을 나눠 갖습니다"),
    it("위아래 2 × 좌우 2", { rows: 2, cols: 2, keep: "table" }, "고른 칸마다 4칸 — 높이·폭을 나눠 갖습니다"),
  ];
  if (tsel.cells.some((td) => { const b = cellBox(td); return b.r1 > b.r0 || b.c1 > b.c0; })) {
    items.push(null, ["합친 칸 풀기", "", () => tableOp("unmerge"), busy, { title: "합친 칸을 원래 격자 칸으로 — 여러 줄에 걸친 칸은 먼저 풀어야 고르게 나뉩니다", enter: () => tprevOp("unmerge") }]);
  }
  tctxOpen(items, anchor);
}

// ---------------------------------------------------------------- 헤더 지정 (spec_owpml_편집 ② §5-4) — 고른 칸을 행헤더·열헤더·필드로, 구분 라벨로
// 지정은 작업 폴더에 따로 저장된다(문서는 안 바뀜). 쓰는 곳: 열 폭 규칙·표 나누기의 헤더 열 판정 · 엑셀식 보기 수식 판정 · 빈 필드 제거 · 다음 3단계 실행.
const theads = { doc: null, tables: {}, loading: null };
const THD = { rowhead: ["행헤더", "hd-row"], colhead: ["열헤더", "hd-col"], field: ["필드", "hd-field"] };
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tableSplit: "표 나누기", tableHeads: "헤더 지정" }); // 「기록」 탭의 이름

function theadsPaint() { // 지정한 칸의 왼쪽 위 귀퉁이 표시(td.hd-user + 역할 클래스) — 쪽을 다시 나누면(새 칸 요소) 다시 입힌다
  for (const td of document.querySelectorAll("#doc td.hd-user")) td.classList.remove("hd-user", "hd-row", "hd-col", "hd-field");
  for (const cells of Object.values(theads.tables)) {
    for (const [cid, role] of Object.entries(cells)) {
      if (!THD[role]) continue;
      for (const td of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(cid)}"]`)) td.classList.add("hd-user", THD[role][1]);
    }
  }
}

function tblHeadsSync() { // table_menu.js tblMenuSync 끝에서(쪽을 다시 나눔 · 문서를 엶) — 다른 문서면 지정을 다시 읽고, 아니면 표시만 다시 입힌다
  const key = state.id && tHwpx() ? `${state.id}|${state.epoch}` : null;
  if (theads.doc !== key) {
    theads.doc = key;
    theads.tables = {};
    theads.loading = null;
    if (key) {
      const p = theads.loading = api(`/api/docs/${encodeURIComponent(state.id)}/tables/heads`).then((d) => {
        if (theads.doc === key && theads.loading === p) { theads.tables = (d && d.tables) || {}; theadsPaint(); }
      }).catch(tNoop); // 옛 서버(끝점 없음) — 지정 없이 돈다
    }
  }
  theadsPaint();
}

function theadsIds() { return [...new Set(tsel.cells.map((td) => td.dataset.cell).filter(Boolean))]; }

function theadsMenu() {
  if (!tselActive()) return;
  const tid = tsel.tbl, ids = theadsIds(), cur = theads.tables[tid] || {};
  const mine = ids.filter((i) => cur[i]);
  const on = (role) => ids.length > 0 && ids.every((i) => cur[i] === role);
  const set = (role, label, title) => [`${on(role) ? "✓ " : ""}${label}`, "", () => theadsSet(tid, ids, role), state.busy, { title, cls: on(role) ? "tmn-on" : "" }];
  const e = tmenu.ev, dv = e && typeof divCtxItems === "function" ? divCtxItems(e).find((x) => x && /구분 기준 자리/.test(x[0])) : null;
  const lay = tlayCached(tid);
  const span = (flag) => { // 「A~C」 꼴 — 왼쪽부터 이어진 묶음들
    const runs = [];
    (lay ? lay.fieldCols : []).forEach((f, c) => { if (f === flag) { const last = runs[runs.length - 1]; if (last && last[1] === c - 1) last[1] = c; else runs.push([c, c]); } });
    return runs.map(([a, b]) => (a === b ? colLetter(a) : `${colLetter(a)}~${colLetter(b)}`)).join(" · ") || "없음";
  };
  const items = [
    [`‹ 헤더 지정 — 고른 칸 ${ids.length}개`, "", () => tselMenu(), false, { cls: "tmn-back", title: "칸 메뉴로" }],
    null,
    set("rowhead", "행헤더로 지정", "행을 이름 짓는 칸(왼쪽 헤더) — 열을 넣고 지워도 폭이 그대로이고, 표를 나누면 두 표에 똑같이 남습니다"),
    set("colhead", "열헤더로 지정", "열을 이름 짓는 칸(위 헤더)"),
    set("field", "필드(값 칸)로 지정", "값을 채우는 칸 — 그 열은 필드 열: 열을 넣고 지우면 비율대로 폭이 바뀌고, 표 나누기에서 나뉘는 열입니다"),
  ];
  if (mine.length) items.push([`지정 풀기 — 자동 판정으로(${mine.length}칸)`, "", () => theadsSet(tid, mine, null), state.busy, { title: "직접 지정한 역할을 지우고 스크립트 판정으로 돌아갑니다" }]);
  items.push(null, [dv ? dv[0].replace("구분 기준 자리", "구분 라벨(구분 기준 자리)") : "구분 라벨로 지정…", "", dv ? dv[2] : tNoop, !dv,
    { title: dv ? "이 칸의 글을 구분 기준 값(기관·단계·차년도 …)의 라벨로 표시합니다 — 「연구개발과제」 패널의 추가한 자리" : "칸 안의 글(문단)을 오른쪽 단추로 누른 뒤 여세요" }]);
  items.push(null, [lay ? `지금 판정 — 헤더 열 ${span(false)} · 필드 열 ${span(true)}` : "지금 판정을 읽는 중…", "", tNoop, true,
    { cls: "tmn-note", title: "필드 열 = 필드 칸이 걸친 열(스크립트 판정 + 직접 지정). 열 폭 규칙과 표 나누기가 이 판정을 씁니다" }]);
  tctxOpen(items);
  if (!lay) tlayLoad(tid).then(() => { if (tctxMine() && ctx.menu.querySelector(".tmn-back") && /헤더 지정/.test(ctx.menu.firstChild.textContent)) theadsMenu(); }).catch(tNoop);
}

async function theadsSet(tid, ids, role) {
  if (!state.id || !ids.length) return;
  const epoch = state.epoch;
  try {
    const r = await api(`/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/heads`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ cells: ids, role }) });
    if (epoch !== state.epoch) return;
    if (Object.keys(r.roles || {}).length) theads.tables[tid] = r.roles; else delete theads.tables[tid];
    tlay.ver += 1; // 판정이 바뀌었다 — layout 을 다시 읽는다
    theadsPaint();
    const lay = r.layout || {};
    toast(`${role ? `고른 칸 ${ids.length}개를 ${THD[role][0]}로 지정했습니다` : `칸 ${ids.length}개의 지정을 풀었습니다`} — 헤더 열 ${lay.headCols ?? "?"}개 · 필드 열 단위 ${(lay.units || []).length}개. 열 폭·표 나누기·엑셀식 보기·빈 필드 제거에 바로 쓰입니다`);
  } catch (e) { if (epoch === state.epoch) toast(tErr(e, "헤더 지정"), true); }
}

// ---------------------------------------------------------------- 표 나누기 (spec_owpml_편집 ② §5-3) — 필드 열을 나눠 표 2개 · 다시 나누기 · 다시 합치기
// 칸 메뉴와 표 손잡이 메뉴(table_menu.js)가 같이 쓴다: back = 맨 위 「‹」 가 돌아갈 곳, anchor = 메뉴 자리(없으면 지금 자리), col = 고른 칸의 첫 열(그 자리의 항목을 굵게).
async function tsplitMenu(tid, back, anchor = null, col = null) {
  const seq = ++tmenu.seq, epoch = state.epoch;
  const head = [`‹ 표 나누기 · ${tid}`, "", back || tNoop, false, { cls: "tmn-back", title: "앞 메뉴로" }];
  tctxOpen([head, null, ["필드 열을 세는 중…", "", tNoop, true]], anchor);
  let lay = null, err = "";
  try { await flushAll(); lay = await tlayLoad(tid); } catch (e) { err = tErr(e, "표 나누기"); }
  if (seq !== tmenu.seq || epoch !== state.epoch || !tctxMine()) return; // 그 사이 메뉴를 닫았거나 다른 목록을 엶
  const items = [head, null];
  if (err) { items.push([err, "", tNoop, true, { cls: "tmn-note" }]); tctxOpen(items); return; }
  const units = lay.units || [], n = units.length, pn = lay.partner || {};
  const name = (u) => { const td = cellAt(tid, 0, u[0]); const t = td ? oneLine(cellParas(td).map((p) => readText(p)).join(" ")).slice(0, 14) : ""; return t ? `「${t}」` : `${colLetter(u[0])}열`; };
  const busy = state.busy;
  const go = (op, first, done) => async () => {
    const r = await structOp(`tables/${encodeURIComponent(tid)}/split`, op === "join" ? { op } : { op, first });
    if (r && r.split) { tselClear(); toast(`${done(r.split)} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`); }
  };
  const pair = pn.next ? { a: n, b: pn.next.units, second: true } : pn.prev ? { a: pn.prev.units, b: n, second: false } : null;
  if (pair) { // 이미 나눈 표 — 다시 나누기 · 다시 합치기
    const total = pair.a + pair.b;
    items.push([`이어진 표와 다시 나누기 — 지금 앞 ${pair.a}열 + 뒤 ${pair.b}열`, "", tNoop, true, { cls: "tmn-sec" }]);
    for (let k = 1; k < total; k++) {
      if (k === pair.a) continue;
      items.push([`앞 ${k}열 + 뒤 ${total - k}열`, "", go("resplit", k, (s) => `표를 다시 나눴습니다 — 앞 표 ${s.units[0]}열 · 뒤 표 ${s.units[1]}열`), busy,
        { title: "두 표를 한 표로 합친 뒤 그 자리에서 다시 나눕니다(실행 취소 1번)" }]);
    }
    items.push(["한 표로 다시 합치기", "", go("join", 0, (s) => `두 표를 한 표로 합쳤습니다 — 필드 열 ${s.units[0]}개`), busy,
      { title: `뒤 표의 필드 열 ${pair.b}개를 앞 표 오른쪽에 붙이고 뒤 표를 지웁니다 — 앞 표의 헤더 열·표 폭은 그대로` }]);
  }
  if (n >= 2) {
    if (pair) items.push(null);
    items.push([`${pair ? "이 표를 또 나누기" : "필드 열을 나눠 표 2개로"} — 필드 열 ${n}개 · 헤더 열 ${lay.headCols}개는 두 표에`, "", tNoop, true, { cls: "tmn-sec" }]);
    for (let k = 1; k < n; k++) {
      const cut = units[k][0];
      items.push([`앞 ${k}열 + 뒤 ${n - k}열 — ${name(units[k])}부터 뒤 표`, "", go("split", k, (s) => `표를 둘로 나눴습니다 — 앞 표 ${s.units[0]}열 · 뒤 표 ${s.units[1]}열(바로 아래)`), busy,
        { cls: col != null && cut === col ? "tmn-on" : "", title: "뒤 표는 바로 아래 새 문단에 — 두 표 모두 원래 표 폭 그대로(필드 열이 넓어짐), 헤더 열·행 구조는 두 표에 똑같이",
          enter: () => tprev(tprevPlan("tsplit", tid, null, { cut })) }]);
    }
  } else if (!pair) {
    items.push([lay.headCols > 0 ? "나눌 필드 열이 하나뿐입니다" : "왼쪽 헤더 열이 없는 표입니다 — 칸을 골라 「헤더 지정 ▸ 행헤더로 지정」 을 하면 나눌 수 있습니다", "", tNoop, true, { cls: "tmn-note" }]);
  }
  tctxOpen(items);
}

// ---------------------------------------------------------------- 행·열 넣기·지우기(도구 줄 「테이블 수정」 묶음 · 오른쪽 단추 메뉴 → structOp("table") — 트랜잭션은 본문과 공유)
const TABLE_OP = { row_above: "위에 행 넣기", row_below: "아래에 행 넣기", row_delete: "행 지우기", col_left: "왼쪽에 열 넣기",
  col_right: "오른쪽에 열 넣기", col_delete: "열 지우기", cols_even: "열 폭 같게",
  cells_below: "고른 칸만 아래에 넣기", cells_above: "고른 칸만 위에 넣기", cells_copy: "고른 칸만 아래에 복사", cells_delete: "고른 칸 줄 지우기",
  merge: "칸 합치기", unmerge: "합친 칸 풀기", split: "칸 나누기" }; // 고른 칸만(spec_owpml_편집 ② §5-2)
const tableOpLabel = (op) => TABLE_OP[op] || op; // 기록 탭(app.js)

function tableOp(op, opts = null) {
  // 끌어 고른 칸 묶음(tsel)이 있으면 그 범위(격자 좌표)의 행·열 수만큼, 아니면 커서가 있는 칸이 걸친 행·열. opts = 칸 나누기의 {rows, cols, keep}
  const sel = tselActive() ? tsel : null;
  const c = state.cur;
  const p = sel ? null : c && paraEl(c.id);
  if (!sel && (!p || !p.closest("td"))) { toast("표 칸 안의 문단을 누르거나 칸을 끌어 고른 뒤에 쓰세요"); return; }
  if (op === "merge" && (!sel || sel.cells.filter((td) => !td.classList.contains("cell-cont")).length < 2)) { toast("합칠 칸을 둘 이상 끌어 고르세요"); return; }
  const what = op.startsWith("row") ? "행" : op.startsWith("col") ? "열" : null; // 고른 칸 동작(cells_*·merge·split)은 미리보기 + 실행 취소로 갈음 — 확인 창 없음(② §5-5)
  const n = sel ? (what === "행" ? tselCounts().rows : tselCounts().cols) : 1;
  if (what && op.endsWith("delete") && !confirm(n > 1 ? `고른 ${what} ${n}개를 지울까요?` : `이 칸이 걸친 ${what}을 지울까요?`)) return;
  const id = sel ? tselAnchorId() : c.id;
  if (!id) { toast("고른 칸에 문단이 없습니다"); return; }
  const body = sel ? { id, op, range: { ...sel.rect } } : { id, op };
  if (opts) body.opts = opts;
  tprev(null);
  return structOp("table", body).then((r) => { if (r) tselClear(); return r; });
}

// ---------------------------------------------------------------- 묶기
let tableEditBound = false;
function tableEditInit() { // 한 번만 — 표 칸 끌어 고르기·복사·오른쪽 단추 메뉴·키, 도구 줄 [data-table] 단추
  if (tableEditBound) return;
  tableEditBound = true;
  for (const b of document.querySelectorAll("#docBar [data-table]")) {
    b.onclick = () => tableOp(b.dataset.table);
    b.addEventListener("mouseenter", () => { if (!b.disabled) tprevOp(b.dataset.table); }); // 단추에 올리면 그 동작이 닿는 칸을 문서에 미리 칠한다(② §5-5)
    b.addEventListener("mouseleave", () => tprev(null));
  }
  bindCellSelect();
}

function bindCellSelect() {
  const doc = $("doc");
  doc.addEventListener("mousedown", (e) => {
    ctxClose();
    if (e.button !== 0) return;
    if (e.target.closest && e.target.closest(".tbl-mark")) return; // 표지(⊞ 엑셀식 보기)를 눌러도 고른 칸은 그대로 — ⊞ 가 그 범위만 격자로(tables.js xlSelRange)
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
    // M = 칸 합치기(둘 이상) · S = 칸 나누기 목록(하나 이상) — 한글의 칸 블록 키와 같다(2026-11-10 사용자). 글자판(한/영)과 무관하게 자리(code)로 본다
    if (!mod && !e.shiftKey && !e.altKey && !e.repeat && (e.code === "KeyM" || e.code === "KeyS")) {
      e.preventDefault();
      if (state.busy) return;
      const at = tselAnchorAt();
      tmenu.ev = { target: cellParas(tsel.focus || tsel.anchor)[0] || tsel.anchor, ...at }; // 「‹」 로 칸 메뉴에 돌아갈 때 다른 모듈의 항목(구분 기준·TEMP)이 보는 자리
      if (e.code === "KeyM") tableOp("merge"); else tsplitCellMenu(at);
      return;
    }
    if (!mod && (e.key.length === 1 || ["Backspace", "Delete", "Enter", "Tab"].includes(e.key))) e.preventDefault(); // 칸 선택 중 타자는 무시(글은 칸을 눌러 고침)
  });
}

tableEditInit();
