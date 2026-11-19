"use strict";
// 표 만들기 · 서식 변환(spec_헤딩_추출 ② §11) — 표 모듈의 한 조각: 표 양식(문서의 표 하나)을 고르고, 원본(고른 글 · 붙여 넣은 표/글 · 문서의 표)을
// LLM 으로(또는 그대로) 격자로 정리해 미리 본 뒤, 양식의 서식으로 문서에 넣거나(뒤에 넣기 · 바꾸기) 문서의 표에 서식만 입힌다. 2열(kind "tableMake" — 팝업 아님).
// app.js 가 주는 것: state·heads·$·el·api·toast·hBtn·headsDlg·structOp·flushAll·paraEl·readText·short·oneLine·nf·H_JSON·scrollToBlock.
// tables.js 가 주는 것: xlBlocks(문서 순 표 목록)·xlBlock(표 블록). 부르는 곳(typeof 검사 뒤): tables.js tablesDraw(「표」 탭 단추) · table_edit.js tselContextMenu(tmkCellItems) ·
// app.js divContextMenu(tmkParaItems). 서버 짝은 app/tables_api.py(끝점)·app/table_make.py(격자·구역)·app/table_llm.py(LLM 계약)·app/hwpx_table_make.py(hwpx 어댑터).
// index.html 이 app.js·tables.js·table_edit.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TMK_KEY = "nfm.tblMake"; // {문서 id: {tpl, roles, at}} — 고른 표 양식과 그 구역 수를 이 브라우저에 문서마다
const TMK_PLACE = { paras: "after", paste: "caret", table: "restyle" };
const TMK_ROLE = [["headerRows", "머리행", "위쪽 열 제목 행 수"], ["headerCols", "머리열", "왼쪽 행 제목 열 수"], ["footRows", "합계행", "아래쪽 합계·소계 행 수"]];
const tmkFresh = () => ({ doc: null, tpl: null, tplRoles: null, tplSize: null, rolesSeq: 0, rolesErr: "", kind: "paras", paras: [], table: null, paste: "", pasteGrid: null, extra: "",
  grid: null, gridFor: null, note: "", check: null, call: null, mode: null, busy: false, started: 0, timer: null, seq: 0, place: { ...TMK_PLACE }, llm: null, msg: "" });
let tmk = tmkFresh();
const tmkUrl = (tail) => `/api/docs/${encodeURIComponent(state.id)}/tables/${tail}`;
const tmkOn = () => heads.dlg === "tableMake" && !!state.id;

// ---- 기억(이 브라우저) ---------------------------------------------------------------------------------------------
function tmkRecall() {
  try {
    const r = JSON.parse(localStorage.getItem(TMK_KEY) || "{}")[state.id];
    if (r && r.tpl && xlBlock(r.tpl)) { tmk.tpl = r.tpl; tmk.tplRoles = r.roles || null; }
  } catch { /* 기억만 안 함 */ }
}
function tmkRemember() {
  try {
    const all = JSON.parse(localStorage.getItem(TMK_KEY) || "{}");
    all[state.id] = { tpl: tmk.tpl, roles: tmk.tplRoles, at: Date.now() };
    for (const k of Object.keys(all).sort((a, b) => (all[b].at || 0) - (all[a].at || 0)).slice(40)) delete all[k];
    localStorage.setItem(TMK_KEY, JSON.stringify(all));
  } catch { /* 기억만 안 함 */ }
}

// ---- 문서에서 읽기 — 고른 문단 · 커서 자리 · 표 이름 ------------------------------------------------------------------------
const tmkAlive = (ids) => ids.filter((id) => paraEl(id));
function tmkSelParas() { // 지금 고른 문단 id — 끌어 고른 문단 묶음(아래 「문단 묶음 고르기」), 없으면 커서 문단
  const pick = tmkAlive(tpk.ids);
  if (pick.length) return pick;
  return state.cur && paraEl(state.cur.id) ? [state.cur.id] : [];
}

// ---- 문단 묶음 고르기 — 문단마다 따로 편집 상자라 브라우저 글 선택은 한 문단을 못 넘는다. 표 칸 고르기(table_edit.js)와 같은 손짓으로:
// 문단을 끌어 **다른 문단에 닿으면** 글 선택 대신 그 사이 문단들(같은 그릇 — 본문 또는 한 칸)을 묶음으로 고르고, Shift+누름은 커서 문단부터 그 문단까지.
// 고른 묶음은 오른쪽 단추 「고른 글로 표 만들기…」 · 2열 「지금 선택으로」 가 쓰고 Ctrl+C 는 글을 복사한다. Esc·다른 곳 누름으로 푼다.
// 표시는 문단 요소가 아니라 규칙(<style id="tmkPickCss">)으로 — 쪽을 다시 나눠 요소가 새로 생겨도 남는다. 2열이 열려 있으면 원본 문단(tmk.paras)도 같은 표시.
const tpk = { ids: [], press: null, anchor: null, last: null, hinted: false };
const tpkActive = () => tpk.ids.length > 0;
const tpkBox = (p) => { const td = p.closest("td"); return td ? td._src || td : null; }; // 쪽에 걸쳐 나뉜 칸(app.js 행 안 나눔 — 이어짐 칸의 _src = 원래 칸)은 조각이 달라도 한 그릇
function tpkRange(a, b) { // 같은 그릇의 문단 a..b(문서 순) id
  const box = tpkBox(a);
  const all = [...$("doc").querySelectorAll(".para[data-id]")].filter((q) => tpkBox(q) === box);
  let i = all.indexOf(a), j = all.indexOf(b);
  if (i < 0 || j < 0) return [];
  if (i > j) [i, j] = [j, i];
  return all.slice(i, j + 1).map((q) => q.dataset.id);
}
function tmkPickPaint() {
  let css = document.getElementById("tmkPickCss");
  const ids = (tpk.ids.length ? tpk.ids : tmkOn() && tmk.kind === "paras" ? tmk.paras : []).filter((i) => /^[\w.-]+$/.test(i)).slice(0, 3000);
  if (!ids.length) { if (css) css.textContent = ""; return; }
  if (!css) { css = el("style"); css.id = "tmkPickCss"; document.head.append(css); }
  css.textContent = `${ids.map((i) => `#doc .para[data-id="${i}"]`).join(",")}{background-color:rgba(36,88,214,.13)!important;box-shadow:0 0 0 1px rgba(36,88,214,.3)}`;
}
function tpkSet(ids) { tpk.ids = ids; tmkPickPaint(); }
function tpkClear() { if (tpk.ids.length) { tpk.ids = []; tmkPickPaint(); } }
function tpkEnter() { // 글 선택 → 문단 묶음으로: 브라우저 글 선택을 걷고 편집 상자 포커스를 뺀다(고르는 중 타자가 문단에 들어가지 않게 — 고치던 글은 focusout 이 반영)
  getSelection().removeAllRanges();
  const a = document.activeElement;
  if (a && a.classList && a.classList.contains("para")) a.blur();
}
function tpkHint() {
  if (tpk.hinted || tpk.ids.length < 2 || state.format === "docx") return;
  tpk.hinted = true;
  toast(`문단 ${tpk.ids.length}개를 골랐습니다 — 오른쪽 단추 → 「고른 글로 표 만들기…」 · Ctrl+C 글 복사 · Esc 풀기`);
}
function tpkBind() {
  const doc = $("doc");
  doc.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const p = e.target.closest ? e.target.closest(".para[data-id]") : null;
    if (!p) { tpkClear(); tpk.press = null; return; }
    if (e.shiftKey) { // Shift+누름 = 앞서 누른 문단(없으면 커서 문단)부터 이 문단까지
      const a = tpk.anchor && tpk.anchor.isConnected ? tpk.anchor : state.cur ? paraEl(state.cur.id) : null;
      if (a && a !== p && tpkBox(a) === tpkBox(p)) { e.preventDefault(); tpkEnter(); tpkSet(tpkRange(a, p)); tpkHint(); return; }
    }
    tpkClear();
    Object.assign(tpk, { press: p, anchor: p, last: p });
  });
  doc.addEventListener("mousemove", (e) => {
    const a = tpk.press;
    if (!a) return;
    if (!(e.buttons & 1) || !a.isConnected) { tpk.press = null; return; }
    const q = e.target.closest ? e.target.closest(".para[data-id]") : null;
    if (!q || q === tpk.last) return;
    tpk.last = q;
    if (tpkBox(q) !== tpkBox(a) || (typeof tselActive === "function" && tselActive())) { tpkClear(); return; } // 다른 칸으로 넘어가면 표 칸 고르기가 맡는다
    if (!tpkActive()) tpkEnter();
    tpkSet(tpkRange(a, q));
  });
  document.addEventListener("mouseup", () => { if (tpk.press && tpkActive()) { getSelection().removeAllRanges(); tpkHint(); } tpk.press = null; });
  document.addEventListener("selectionchange", () => { const s = getSelection(); if (tpk.press && tpkActive() && s.rangeCount && !s.isCollapsed) s.removeAllRanges(); }); // 끄는 동안 브라우저가 다시 만드는 글 선택
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && tpkActive() && !(e.target.closest && e.target.closest("input, textarea, select, dialog, .ctx-menu"))) tpkClear(); });
  document.addEventListener("copy", (e) => {
    if (!tpkActive() || !getSelection().isCollapsed || (e.target.closest && e.target.closest("input, textarea")) || (typeof tselActive === "function" && tselActive())) return;
    const text = tmkAlive(tpk.ids).map((id) => readText(paraEl(id)).replaceAll(LS, "\n")).join("\n");
    if (!text || !e.clipboardData) return;
    e.clipboardData.setData("text/plain", text);
    e.preventDefault();
    toast(`문단 ${tpk.ids.length}개의 글을 복사했습니다`);
  });
  // 2열이 닫히거나 다른 보기로 바뀌면 원본 문단 표시를 걷는다(headsDlg·headsColClose 에 고리를 더하지 않고 열 요소를 지켜본다)
  const col = $("headsDlg"), title = $("headsDlgTitle");
  if (col && title && typeof MutationObserver === "function") {
    const mo = new MutationObserver(() => tmkPickPaint());
    mo.observe(col, { attributes: true, attributeFilter: ["hidden"] });
    mo.observe(title, { childList: true, characterData: true, subtree: true });
  }
}
function tmkOuterTable(p) { // 문단을 품은 가장 바깥 표 id(본문 문단이면 null)
  let t = p && p.closest("table.tbl"), out = null;
  while (t) { out = t.dataset.tbl; t = t.parentElement ? t.parentElement.closest("table.tbl") : null; }
  return out;
}
function tmkCaret() { // 붙여 넣기 원본의 넣을 자리 — 커서 문단 {id, text, table: 바깥 표 id | null} | null
  const p = state.cur && paraEl(state.cur.id);
  return p ? { id: p.dataset.id, text: short(readText(p), 24), table: tmkOuterTable(p) } : null;
}
function tmkTableName(b) { // 「t12 · 4×3 · 첫 칸 글」
  const blk = xlBlock(b.id);
  const first = blk ? [...(blk.cells || [])].sort((x, y) => x.row - y.row || x.col - y.col).map((c) => oneLine(c.text)).find((t) => t) : "";
  return `${b.id} · ${b.rows}×${b.cols}${b.depth > 1 ? " · 칸 안" : ""}${first ? ` · ${first.length > 22 ? first.slice(0, 22) + "…" : first}` : ""}`;
}
function tmkGoTable(tid) {
  const t = document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"], #doc .xl-wrap[data-tbl="${CSS.escape(tid)}"]`);
  if (t) t.scrollIntoView({ block: "center", behavior: scrollHow() }); else toast("그 표가 지금 문서에 없습니다");
}

// ---- 붙여 넣은 표(HTML) → 격자 ----------------------------------------------------------------------------------------
function tmkCellText(td) {
  const c = td.cloneNode(true);
  for (const t of c.querySelectorAll("table")) t.remove(); // 칸 안 표는 글만 못 옮김 — 뺀다
  for (const br of c.querySelectorAll("br")) br.replaceWith("\n");
  for (const p of c.querySelectorAll("p, div, li")) p.append("\n");
  return c.textContent.replace(/ /g, " ").split("\n").map((s) => s.replace(/\s+/g, " ").trim()).filter(Boolean).join("\n");
}
function tmkHtmlGrid(html) { // 클립보드 HTML 의 첫 표 → {rows: [{cells: [{text, rowSpan, colSpan}]}]} | null(표 없음)
  if (!html || !/<table[\s>]/i.test(html)) return null;
  const t = new DOMParser().parseFromString(html, "text/html").querySelector("table");
  if (!t) return null;
  const rows = [];
  for (const tr of t.rows) {
    const cells = [...tr.cells].map((td) => ({ text: tmkCellText(td), rowSpan: Math.max(1, td.rowSpan || 1), colSpan: Math.max(1, td.colSpan || 1) }));
    if (cells.length) rows.push({ cells });
  }
  return rows.length ? { rows } : null;
}
const tmkTsv = (grid) => grid.rows.map((r) => r.cells.map((c) => (/[\t\n"]/.test(c.text) ? `"${c.text.replace(/"/g, '""')}"` : c.text)).join("\t")).join("\n");
function tmkLayout(grid) { // 격자의 칸 자리(HTML 표 규칙 — 서버 table_make.normalize 와 같음) → {cells: [{r, c, rs, cs, cell}], rows, cols}
  const occ = new Set(), out = [];
  let cols = 0;
  grid.rows.forEach((row, r) => {
    let c = 0;
    for (const cell of row.cells) {
      while (occ.has(`${r},${c}`)) c += 1;
      const rs = Math.min(Math.max(1, cell.rowSpan || 1), grid.rows.length - r);
      let cs = Math.max(1, cell.colSpan || 1);
      for (let k = 1; k < cs; k += 1) if (occ.has(`${r},${c + k}`)) { cs = k; break; }
      for (let y = r; y < r + rs; y += 1) for (let x = c; x < c + cs; x += 1) occ.add(`${y},${x}`);
      out.push({ r, c, rs, cs, cell });
      c += cs;
      cols = Math.max(cols, c);
    }
  });
  return { cells: out, rows: grid.rows.length, cols };
}

// ---- 열기 -----------------------------------------------------------------------------------------------------------
function tmkOpen(opts = {}) { // opts: {template, paras: [id], table, kind}
  if (!state.id) return;
  if (state.format === "docx") { toast("표 만들기·서식 변환은 지금 hwpx 문서만 됩니다"); return; }
  const key = `${state.id}|${state.epoch}`;
  if (tmk.doc !== key) { clearInterval(tmk.timer); tmk = { ...tmkFresh(), doc: key }; tmkRecall(); }
  if (opts.template && xlBlock(opts.template) && opts.template !== tmk.tpl) { tmk.tpl = opts.template; tmk.tplRoles = null; tmk.tplSize = null; tmkRemember(); }
  if (opts.paras && opts.paras.length) { tmk.kind = "paras"; tmk.paras = opts.paras; }
  if (opts.table && xlBlock(opts.table)) { tmk.kind = "table"; tmk.table = opts.table; }
  if (opts.kind) tmk.kind = opts.kind;
  if (tmk.kind === "paras" && !tmkAlive(tmk.paras).length) tmk.paras = tmkSelParas();
  tpkClear(); // 고른 묶음은 원본(tmk.paras)으로 넘어갔다 — 표시는 2열이 열려 있는 동안 원본 문단에
  headsDlg("tableMake", "표 만들기 · 서식 변환", "표 양식의 서식으로 — 고른 글 · 붙여 넣은 표 · 문서의 표");
  tmkDraw();
  if (tmk.tpl && !tmk.tplSize) tmkLoadRoles();
  if (!tmk.llm) api("/api/headings/llm").then((st) => { tmk.llm = st; if (tmkOn()) tmkDraw(); }).catch(() => { tmk.llm = { available: false }; if (tmkOn()) tmkDraw(); });
}

async function tmkLoadRoles() { // 양식 표의 구역 수 자동 판정 — 화면에서 고친 값(tplRoles)이 있으면 그대로 두고 크기만
  const tid = tmk.tpl, seq = ++tmk.rolesSeq, epoch = state.epoch;
  if (!tid) return;
  tmk.rolesErr = "";
  try {
    const r = await api(tmkUrl(`${encodeURIComponent(tid)}/roles`));
    if (seq !== tmk.rolesSeq || epoch !== state.epoch) return;
    tmk.tplSize = { rows: r.rows, cols: r.cols, nested: r.nested };
    if (!tmk.tplRoles) tmk.tplRoles = { ...r.roles };
    tmkRemember();
  } catch (e) {
    if (seq !== tmk.rolesSeq || epoch !== state.epoch) return;
    tmk.rolesErr = `표 양식을 읽지 못했습니다: ${tmkErr(e)}`;
  }
  if (tmkOn()) tmkDraw();
}
// 화면 파일은 새로 고침만으로 바뀌지만 끝점은 서버를 다시 켜야 생긴다 — 옛 서버의 「Not Found」 를 알아볼 말로
const tmkErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 이 기능을 쓸 수 있습니다" : e.message);

// ---- 오른쪽 단추 메뉴 항목(앞에 구분선) --------------------------------------------------------------------------------
function tmkParaItems(e) { // 문단 메뉴(app.js divContextMenu) — 누른 문단이 고른 묶음 안이면 그 묶음, 아니면 그 문단 하나
  if (!state.id || state.format === "docx") return [];
  const p = e && e.target && e.target.closest ? e.target.closest(".para[data-id]") : null;
  const pick = tmkAlive(tpk.ids);
  const ids = pick.length && (!p || pick.includes(p.dataset.id)) ? pick : p ? [p.dataset.id] : tmkSelParas();
  if (!ids.length) return [];
  return [null, [ids.length > 1 ? `고른 글(문단 ${ids.length}개)로 표 만들기…` : "이 문단으로 표 만들기…", "", () => tmkOpen({ paras: ids })]];
}
function tmkCellItems(tid) { // 표 칸 메뉴(table_edit.js tselContextMenu) — 칸 안에서 문단 묶음을 골라 두었으면 그것도
  if (!state.id || state.format === "docx" || !tid) return [];
  const pick = tmkAlive(tpk.ids);
  return [null, ...(pick.length > 1 ? [[`고른 글(문단 ${pick.length}개)로 표 만들기…`, "", () => tmkOpen({ paras: pick })]] : []),
    ["이 표를 표 양식으로", "", () => tmkOpen({ template: tid })], ["이 표를 양식 서식으로 변환…", "", () => tmkOpen({ table: tid })]];
}

// ---- 그리기 ---------------------------------------------------------------------------------------------------------
function tmkNum(label, title, value, max, set) {
  const l = el("label", "tm-num", label), i = el("input");
  i.type = "number"; i.min = "0"; i.max = String(Math.max(0, max)); i.value = String(value || 0); i.title = title;
  i.onchange = () => { const v = Math.max(0, Math.min(Math.max(0, max), parseInt(i.value, 10) || 0)); i.value = String(v); set(v); };
  l.append(i);
  return l;
}
function tmkRadio(name, value, cur, text, set, title = "") {
  const l = el("label"), i = el("input");
  i.type = "radio"; i.name = name; i.value = value; i.checked = value === cur;
  i.onchange = () => { if (i.checked) set(value); };
  l.append(i, text);
  if (title) l.title = title;
  return l;
}
function tmkSelect(tables, cur, set, empty) {
  const s = el("select");
  s.append(new Option(empty, ""));
  for (const b of tables) s.append(new Option(tmkTableName(b), b.id));
  s.value = cur && tables.some((b) => b.id === cur) ? cur : "";
  s.onchange = () => set(s.value || null);
  return s;
}

function tmkDraw() {
  if (!tmkOn()) return;
  const body = $("headsDlgBody"), tools = $("headsDlgTools");
  const keep = body.scrollTop, act = document.activeElement, actId = act && body.contains(act) ? act.id : "";
  const tables = xlBlocks();
  if (tmk.tpl && !tables.some((b) => b.id === tmk.tpl)) { tmk.tpl = null; tmk.tplRoles = null; tmk.tplSize = null; }
  if (tmk.table && !tables.some((b) => b.id === tmk.table)) tmk.table = null;
  tmk.paras = tmkAlive(tmk.paras);
  body.textContent = "";
  tools.textContent = "";
  const wrap = el("div", "ta-wrap tm-wrap");
  body.append(wrap);
  tmkPickPaint();
  if (!tables.length) { wrap.append(el("p", "hnote", "이 문서에 표가 없습니다 — 서식을 따올 표(표 양식)가 하나는 있어야 합니다.")); return; }

  // ① 표 양식
  wrap.append(el("h3", null, "표 양식 — 서식을 따올 표"));
  const r1 = el("div", "ta-row");
  r1.append(tmkSelect(tables, tmk.tpl, (v) => { tmk.tpl = v; tmk.tplRoles = null; tmk.tplSize = null; tmkRemember(); tmkDraw(); if (v) tmkLoadRoles(); }, "표 양식을 고르세요"));
  if (tmk.tpl) r1.append(hBtn("자리로", () => tmkGoTable(tmk.tpl), { title: "문서에서 이 표로" }));
  wrap.append(r1);
  if (tmk.tpl && tmk.tplRoles && tmk.tplSize) {
    const r2 = el("div", "ta-row");
    const lim = { headerRows: tmk.tplSize.rows, headerCols: tmk.tplSize.cols, footRows: tmk.tplSize.rows };
    for (const [k, name, title] of TMK_ROLE) r2.append(tmkNum(name, `표 양식의 ${title} — 자동으로 읽은 값, 틀리면 고치세요`, tmk.tplRoles[k], lim[k], (v) => { tmk.tplRoles[k] = v; tmkRemember(); }));
    wrap.append(r2);
  } else if (tmk.tpl) wrap.append(el("p", "hnote", tmk.rolesErr || "표 양식을 읽는 중…"));

  // ② 원본
  wrap.append(el("h3", null, "원본 — 표로 만들 것"));
  const kinds = el("div", "tm-kinds");
  const setKind = (k) => { tmk.kind = k; if (k === "paras" && !tmk.paras.length) tmk.paras = tmkSelParas(); tmkDraw(); };
  kinds.append(tmkRadio("tmkKind", "paras", tmk.kind, "고른 글", setKind, "문서에서 고른 문단들을 표로"),
    tmkRadio("tmkKind", "paste", tmk.kind, "붙여 넣기", setKind, "엑셀·한글·웹에서 복사한 표나 글을 붙여 넣어 표로"),
    tmkRadio("tmkKind", "table", tmk.kind, "문서의 표", setKind, "문서의 표 하나를 표 양식의 서식으로"));
  wrap.append(kinds);
  if (tmk.kind === "paras") {
    const n = tmk.paras.length, row = el("div", "ta-row");
    const a = n ? paraEl(tmk.paras[0]) : null, z = n > 1 ? paraEl(tmk.paras[n - 1]) : null;
    wrap.append(el("p", "tm-src", n ? `문단 ${nf(n)}개 · 「${short(readText(a), 30)}」${z ? ` ~ 「${short(readText(z), 30)}」` : ""}${a.closest("td") ? " · 표 칸 안" : ""}`
      : "고른 글이 없습니다 — 문서에서 첫 문단을 눌러 끝 문단까지 끌어(또는 Shift+누름) 고른 뒤 「지금 선택으로」 를 누르세요."));
    const pick = hBtn("지금 선택으로", () => { const ids = tmkSelParas(); if (!ids.length) { toast("문서에서 문단을 끌어 고르거나 누른 뒤에 쓰세요"); return; } tmk.paras = ids; tpkClear(); tmkDraw(); },
      { title: "문서에서 지금 끌어 고른 문단들(없으면 커서가 있는 문단)을 원본으로" });
    pick.onmousedown = (e) => e.preventDefault(); // 단추를 눌러도 문서의 선택을 지킨다
    row.append(pick);
    if (n) row.append(hBtn("자리로", () => scrollToBlock(tmk.paras[0]), { title: "문서에서 첫 문단으로" }));
    wrap.append(row);
  } else if (tmk.kind === "paste") {
    const ta = el("textarea");
    ta.id = "tmkPaste"; ta.rows = 6; ta.value = tmk.paste; ta.spellcheck = false;
    ta.placeholder = "엑셀·한글·웹의 표를 붙여 넣거나 글을 쓰세요 — 탭으로 나눈 글·마크다운 | 표는 표로 읽습니다";
    const st = el("p", "hnote");
    const stat = () => {
      const g = tmk.pasteGrid, t = tmk.paste;
      st.textContent = g ? `표로 읽음 — ${tmkLayout(g).rows}행 × ${tmkLayout(g).cols}열(칸 합치기 포함) · 칸 글은 그대로 옮깁니다`
        : !t.trim() ? "" : /\t/.test(t) || /^\s*\|.*\|\s*$/m.test(t) ? "표 꼴 글 — 「그대로 표로」 로 칸 글을 그대로 옮길 수 있습니다" : "글 — 「LLM 으로 표 정리」 가 표로 정리합니다";
    };
    ta.onpaste = (e) => {
      const g = tmkHtmlGrid(e.clipboardData && e.clipboardData.getData("text/html"));
      if (!g) return; // 보통 글 — 그대로 붙음(input 이 받음)
      e.preventDefault();
      tmk.pasteGrid = g; tmk.paste = tmkTsv(g); ta.value = tmk.paste;
      stat();
    };
    ta.oninput = () => { tmk.paste = ta.value; tmk.pasteGrid = null; stat(); }; // 손으로 고치면 글에서 다시 읽는다(합치기는 잃음)
    stat();
    wrap.append(ta, st);
  } else {
    const row = el("div", "ta-row");
    row.append(tmkSelect(tables, tmk.table, (v) => { tmk.table = v; tmkDraw(); }, "문서의 표를 고르세요"));
    if (tmk.table) row.append(hBtn("자리로", () => tmkGoTable(tmk.table), { title: "문서에서 이 표로" }));
    wrap.append(row);
    if (tmk.table && tmk.table === tmk.tpl) wrap.append(el("p", "hnote", "표 양식과 같은 표입니다 — 서식을 바꿀 다른 표를 고르세요."));
    const blk = tmk.table && xlBlock(tmk.table);
    if (blk && (blk.cells || []).some((c) => (c.blocks || []).some((x) => x.type !== "paragraph"))) wrap.append(el("p", "hnote", "칸 안에 표·그림이 있습니다 — 「서식만 입히기」 는 그대로 두지만 새 표로 만들면 글만 옮겨집니다."));
  }

  // ③ 지침 · 정리
  wrap.append(el("h3", null, "지침 — 이번 한 번(선택)"));
  const ex = el("textarea");
  ex.id = "tmkExtra"; ex.rows = 2; ex.value = tmk.extra;
  ex.placeholder = "예: 항목 | 내용 | 비고 3열로 · 금액은 천원 단위 · 문장은 명사형으로 짧게  (공통 표 지침·표 양식의 표 지침은 함께 갑니다)";
  ex.oninput = () => { tmk.extra = ex.value; };
  wrap.append(ex);
  const acts = el("div", "ta-row");
  const llmOk = !!(tmk.llm && tmk.llm.available);
  acts.append(hBtn("LLM 으로 표 정리", () => tmkCompose(true), { cls: "btn sm primary", disabled: tmk.busy || !llmOk,
    title: llmOk ? "원본을 LLM 이 표로 정리합니다(유료 — 몇 초에서 수십 초). 붙여 넣은 표·문서의 표는 칸 글을 고치지 않고 구조만 정합니다" : "LLM 을 쓸 수 없습니다(Claude 실행 파일·로그인·API 키 없음)" }),
    hBtn("그대로 표로", () => tmkCompose(false), { disabled: tmk.busy, title: "LLM 없이 — 표 꼴 원본(붙여 넣은 표·탭 구분 글·문서의 표)의 칸 글과 칸 합치기를 그대로 격자로" }));
  const busy = el("span", tmk.busy ? "tm-busy" : "muted");
  busy.id = "tmkBusy";
  busy.textContent = tmk.busy ? "LLM 이 표를 정리하는 중…" : tmk.msg || (tmk.llm && !llmOk ? "LLM 꺼짐 — 「그대로 표로」 만" : "");
  acts.append(busy);
  wrap.append(acts);

  // ④ 미리보기 · 넣기
  if (tmk.grid) tmkPreview(wrap);
  body.scrollTop = keep;
  const again = actId && document.getElementById(actId);
  if (again) again.focus({ preventScroll: true });
}

function tmkPreview(wrap) {
  const g = tmk.grid, lay = tmkLayout(g);
  const stale = tmk.gridFor !== tmkSourceKey();
  wrap.append(el("h3", null, `미리보기 — ${lay.rows}행 × ${lay.cols}열${stale ? " · 원본이 바뀜(다시 정리하세요)" : ""}`));
  const roles = el("div", "ta-row"), box = el("div", "tm-scroll");
  const paint = () => {
    for (const td of box.querySelectorAll("td")) {
      const r = +td.dataset.r, c = +td.dataset.c;
      td.className = r < g.headerRows ? "head" : r >= lay.rows - g.footRows ? "foot" : c < g.headerCols ? "hcol" : "";
    }
  };
  const lim = { headerRows: lay.rows, headerCols: lay.cols, footRows: lay.rows };
  for (const [k, name, title] of TMK_ROLE) roles.append(tmkNum(name, `새 표의 ${title} — 이 구역마다 표 양식의 같은 구역 서식을 입힙니다`, g[k], lim[k], (v) => { g[k] = v; paint(); }));
  roles.append(hHelp("표 미리보기 편집 안내", "칸을 눌러 글을 고칠 수 있습니다. 고친 내용은 아래에서 넣을 자리를 고른 뒤 문서에 반영합니다."));
  wrap.append(roles);
  const t = el("table", "tm-grid"), tb = el("tbody"), trs = g.rows.map(() => el("tr"));
  for (const x of lay.cells) {
    const td = el("td", null, x.cell.text);
    td.dataset.r = x.r; td.dataset.c = x.c;
    if (x.rs > 1) td.rowSpan = x.rs;
    if (x.cs > 1) td.colSpan = x.cs;
    td.contentEditable = PLAIN ? "plaintext-only" : "true";
    td.spellcheck = false;
    td.oninput = () => { x.cell.text = td.innerText.replace(/\r/g, "").replace(/\n+$/, ""); };
    trs[x.r].append(td);
  }
  tb.append(...trs);
  t.append(tb);
  box.append(t);
  paint();
  wrap.append(box);
  if (tmk.note) wrap.append(el("p", "hnote", `LLM: ${tmk.note}`));
  const ck = tmk.check || {}, parts = [];
  const list = (a) => a.slice(0, 8).map((s) => `「${short(s, 24)}」`).join(" ") + (a.length > 8 ? " …" : "");
  if ((ck.lost || []).length) parts.push(`원본에서 빠진 칸 글 ${ck.lost.length}: ${list(ck.lost)}`);
  if ((ck.added || []).length) parts.push(`원본에 없던 칸 글 ${ck.added.length}: ${list(ck.added)}`);
  if ((ck.numbers || []).length) parts.push(`원본에 없는 수 ${ck.numbers.length}: ${ck.numbers.slice(0, 12).join(" · ")}${ck.numbers.length > 12 ? " …" : ""}`);
  if (parts.length) wrap.append(el("p", "tm-check", `검산 — ${parts.join(" / ")}${ck.more ? ` (외 ${ck.more})` : ""} · 넣기 전에 확인하세요`));
  else if (tmk.mode === "convert") wrap.append(el("p", "tm-check ok", "검산 — 원본 칸 글이 모두 그대로 들어 있습니다"));
  else if (tmk.mode === "compose") wrap.append(el("p", "tm-check ok", "검산 — 표의 수는 모두 원본 글에 있는 수입니다(문장은 직접 확인하세요)"));
  if (tmk.call) roles.append(hHelp("표 정리 실행 기록", `LLM ${tmk.call.backend || ""} · ${tmk.call.model || ""} · ${((tmk.call.ms || 0) / 1000).toFixed(1)}초${tmk.call.costUsd != null ? ` · $${Number(tmk.call.costUsd).toFixed(3)}` : ""}`));

  wrap.append(el("h3", null, "넣을 자리"));
  const place = el("div", "tm-place"), kind = tmk.kind, cur = tmk.place[kind];
  const set = (v) => { tmk.place[kind] = v; tmkDraw(); };
  if (kind === "paras") {
    place.append(tmkRadio("tmkPlace", "after", cur, "고른 글 뒤에 넣기", set, "고른 문단은 그대로 두고 마지막 문단 바로 뒤에 새 표"),
      tmkRadio("tmkPlace", "replace", cur, "고른 글을 표로 바꾸기", set, "고른 문단들을 지우고 그 자리에 새 표(실행 취소로 되돌림)"));
  } else if (kind === "paste") {
    const c = tmkCaret();
    const where = el("span");
    where.id = "tmkCaret";
    where.dataset.at = c ? `${c.id}|${c.table || ""}` : "";
    where.textContent = c ? `커서 문단 「${c.text}」 뒤에 넣기${c.table ? "(표 칸 안 — 칸 안 표가 됩니다)" : ""}` : "커서 문단 뒤에 넣기 — 문서에서 넣을 자리의 문단을 누르세요";
    const l = tmkRadio("tmkPlace", "caret", cur, "", set);
    l.append(where);
    place.append(l);
    if (c && c.table) place.append(tmkRadio("tmkPlace", "afterTable", cur, `커서가 있는 표(${c.table}) 뒤에 넣기`, set));
    else if (cur === "afterTable") tmk.place.paste = "caret";
  } else {
    place.append(tmkRadio("tmkPlace", "restyle", cur, "서식만 입히기 — 표의 구조·글·칸 크기는 그대로", set, "칸마다 표 양식의 괘선·음영·여백·문단/글자 모양만 입힙니다(위 격자의 머리행·머리열·합계행 수를 씀 — 고친 칸 글은 안 씀)"),
      tmkRadio("tmkPlace", "replace", cur, "새 표로 바꾸기 — 위 격자대로 다시 만듦", set, "원래 표를 지우고 그 자리에 위 격자의 새 표(칸 안 표·그림·글자 강조는 안 옮겨짐)"),
      tmkRadio("tmkPlace", "after", cur, "원래 표 뒤에 새 표 넣기", set, "원래 표는 그대로 두고 바로 뒤에 새 표"));
  }
  wrap.append(place);
  const go = el("div", "ta-row");
  const restyle = kind === "table" && tmk.place.table === "restyle";
  go.append(hBtn(restyle ? "서식 입히기" : "문서에 넣기", () => tmkInsert(), { cls: "btn sm primary", disabled: tmk.busy || stale || !tmk.tpl || (kind === "table" && (!tmk.table || tmk.table === tmk.tpl)),
    title: stale ? "원본이 바뀌었습니다 — 「LLM 으로 표 정리」 나 「그대로 표로」 로 다시 정리한 뒤에 넣으세요" : "LLM 은 구조와 칸 글만 정하고 서식은 표 양식에서 그대로 따옵니다 — OWPML 검사를 거치고, 도구 줄의 실행 취소로 되돌릴 수 있습니다" }));
  wrap.append(go);
}

// ---- 정리(LLM | 그대로) ------------------------------------------------------------------------------------------------
function tmkSourceKey() { // 미리보기 격자가 어느 원본에서 나왔는지(원본이 바뀌면 「다시 정리」 알림)
  return tmk.kind === "paras" ? `p:${tmk.paras.join(",")}` : tmk.kind === "table" ? `t:${tmk.table}` : `x:${tmk.paste.length}:${tmk.paste.slice(0, 80)}`;
}
function tmkSource() {
  if (tmk.kind === "paras") {
    tmk.paras = tmkAlive(tmk.paras);
    if (!tmk.paras.length) { toast("문서에서 표로 만들 문단들을 고른 뒤 「지금 선택으로」 를 누르세요"); return null; }
    return { kind: "paras", ids: tmk.paras };
  }
  if (tmk.kind === "table") {
    if (!tmk.table) { toast("원본으로 쓸 문서의 표를 고르세요"); return null; }
    return { kind: "table", id: tmk.table };
  }
  if (!tmk.paste.trim()) { toast("표나 글을 붙여 넣으세요"); return null; }
  return tmk.pasteGrid ? { kind: "grid", grid: tmk.pasteGrid } : { kind: "text", text: tmk.paste };
}

async function tmkCompose(useLlm) {
  if (tmk.busy || !state.id) return;
  if (!tmk.tpl) { toast("표 양식(서식을 따올 표)을 먼저 고르세요"); return; }
  const src = tmkSource();
  if (!src) return;
  const seq = ++tmk.seq, epoch = state.epoch, key = tmkSourceKey();
  tmk.busy = true; tmk.msg = ""; tmk.started = Date.now();
  tmkDraw();
  clearInterval(tmk.timer);
  if (useLlm) tmk.timer = setInterval(() => { const b = document.getElementById("tmkBusy"); if (b && tmk.busy) b.textContent = `LLM 이 표를 정리하는 중… ${Math.round((Date.now() - tmk.started) / 1000)}초`; }, 1000);
  try {
    await flushAll(); // 타자 중인 글을 서버에 먼저(원본 문단 글은 서버가 읽는다)
    const r = await api(tmkUrl("compose"), { method: "POST", headers: H_JSON,
      body: JSON.stringify({ template: tmk.tpl, templateRoles: tmk.tplRoles || undefined, source: src, instructions: tmk.extra.trim() || undefined, llm: useLlm }) });
    if (seq !== tmk.seq || epoch !== state.epoch) return;
    Object.assign(tmk, { grid: r.grid, gridFor: key, note: r.note || "", check: r.check || null, call: r.call || null, mode: r.mode });
  } catch (e) {
    if (seq !== tmk.seq || epoch !== state.epoch) return;
    tmk.msg = tmkErr(e);
    toast(tmk.msg, true);
  } finally {
    if (seq === tmk.seq) {
      tmk.busy = false;
      clearInterval(tmk.timer);
      if (epoch === state.epoch && tmkOn()) tmkDraw();
    }
  }
}

// ---- 문서에 넣기 · 서식만 입히기 ----------------------------------------------------------------------------------------
async function tmkInsert() {
  const g = tmk.grid, kind = tmk.kind, place = tmk.place[kind];
  if (!g || !tmk.tpl || tmk.busy) return;
  const roles = { headerRows: g.headerRows, headerCols: g.headerCols, footRows: g.footRows };
  let path = "tables/make", body = { template: tmk.tpl, templateRoles: tmk.tplRoles || undefined, grid: g };
  if (kind === "paras") {
    const ids = tmkAlive(tmk.paras);
    if (!ids.length || ids.length !== tmk.paras.length) { toast("고른 문단이 문서에서 바뀌었습니다 — 「지금 선택으로」 로 다시 고르세요", true); tmk.paras = ids; tmkDraw(); return; }
    body.after = ids[ids.length - 1];
    if (place === "replace") {
      if (!confirm(`고른 문단 ${ids.length}개를 지우고 그 자리에 표를 넣습니다(실행 취소로 되돌릴 수 있음). 계속할까요?`)) return;
      body.replace = { first: ids[0], last: ids[ids.length - 1] };
    }
  } else if (kind === "paste") {
    const c = tmkCaret();
    if (!c) { toast("문서에서 표를 넣을 자리의 문단을 먼저 누르세요"); return; }
    body.after = place === "afterTable" && c.table ? c.table : c.id;
  } else {
    if (!tmk.table || !xlBlock(tmk.table)) { toast("원본 표가 지금 문서에 없습니다 — 다시 고르세요", true); return; }
    if (place === "restyle") { path = "tables/restyle"; body = { table: tmk.table, template: tmk.tpl, roles, templateRoles: tmk.tplRoles || undefined }; }
    else {
      body.after = tmk.table;
      if (place === "replace") {
        if (!confirm(`표 ${tmk.table} 을 지우고 그 자리에 위 격자의 새 표를 넣습니다(칸 안 표·그림·글자 강조는 안 옮겨짐 · 실행 취소로 되돌릴 수 있음). 계속할까요?`)) return;
        body.replace = { table: tmk.table };
      }
    }
  }
  const r = await structOp(path, body); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
  if (!r || !r.made) return;
  const tid = r.made.table;
  if (path === "tables/restyle") toast(`표 ${tid} 에 표 양식 ${tmk.tpl} 의 서식을 입혔습니다 — 문단 ${nf(r.made.formatted)}개 모양 바뀜 · 실행 취소로 되돌릴 수 있습니다`);
  else {
    toast(`표 ${r.made.rows}×${r.made.cols} 을 넣었습니다(${tid}) — 실행 취소로 되돌릴 수 있습니다`);
    if (kind === "paras" && place === "replace") tmk.paras = [];
    if (kind === "table" && place === "replace") { tmk.table = tid; tmk.gridFor = tmkSourceKey(); } // 바꾼 표가 새 원본
  }
  if (tmkOn()) tmkDraw();
  requestAnimationFrame(() => tmkGoTable(tid));
}

// ---- 묶기 — 문단 묶음 고르기 · 붙여 넣기 원본의 「커서 문단」 글을 선택이 바뀔 때 맞춘다 ------------------------------------------------
tpkBind();
let tmkCaretTimer = null;
document.addEventListener("selectionchange", () => {
  if (!tmkOn() || tmk.kind !== "paste" || !tmk.grid) return;
  clearTimeout(tmkCaretTimer);
  tmkCaretTimer = setTimeout(() => {
    const s = document.getElementById("tmkCaret"), c = tmkCaret();
    if (!s || !tmkOn()) return;
    const was = s.dataset.at || "";
    const now = c ? `${c.id}|${c.table || ""}` : "";
    if (was === now) return;
    const body = $("headsDlgBody");
    if (body.contains(document.activeElement)) return; // 2열에서 타자 중이면 건드리지 않는다
    tmkDraw();
    const s2 = document.getElementById("tmkCaret");
    if (s2) s2.dataset.at = now;
  }, 200);
});
