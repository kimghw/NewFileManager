// 엑셀(xlsx) 시트 편집기(spec_엑셀편집 ② §3 · §4 — 끝점 app/xlsx_api.py · 꼴 design.md §34). app.js 를 읽지 않는다.
// 칸 고르기 · 고치기(늘 초점을 쥔 편집 상자 하나 — 한글 입력기가 첫 글자부터 들어가게) · 붙여 넣기 · 복사 · 행 넣기 / 지우기 · 실행 취소 · 내려받기.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const S = { id: "", name: "", rev: 0, undo: 0, sheets: [], cur: 0, view: null, cells: new Map(), merges: new Map(), covered: new Map(),
    maxR: 0, maxC: 0, sel: { r0: 1, c0: 1, r1: 1, c1: 1 }, act: [1, 1], editing: false, origin: "", busy: 0, extraR: 0, hidR: new Set(), hidC: new Set() };
  const key = (r, c) => `${r},${c}`;

  // ---- 서버 ----
  async function api(url, opt = {}) {
    const r = await fetch(url, opt);
    const ct = r.headers.get("content-type") || "";
    const body = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) {
      const e = new Error((body && body.detail) || `요청 실패(${r.status})`);
      e.status = r.status;
      throw e;
    }
    return body;
  }
  const J = (obj) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) });

  function toast(msg, err = false) {
    const t = $("shToast");
    t.textContent = msg;
    t.className = "sh-toast" + (err ? " err" : "");
    t.hidden = false;
    clearTimeout(toast.t);
    toast.t = setTimeout(() => { t.hidden = true; }, err ? 6000 : 3000);
  }
  function state(text, err = false) { const s = $("shState"); s.textContent = text; s.className = "sh-state" + (err ? " err" : ""); }

  async function load(sheet = S.cur) {
    const d = await api(`/api/sheets/${S.id}?sheet=${sheet}`);
    take(d);
  }
  function take(d) {
    Object.assign(S, { name: d.name, rev: d.rev, undo: d.undo, sheets: d.sheets, cur: d.sheet.index, view: d.sheet });
    document.title = `${d.name} — 시트 편집`;
    $("shName").textContent = d.name;
    $("shDownload").href = `/api/sheets/${S.id}/download`;
    $("shUndo").disabled = !d.undo;
    state(d.edited ? "저장됨 — 작업 폴더" : "");
    tabs();
    draw();
  }

  async function send(fn, label) { // 편집 요청 하나 — 차례가 어긋나면(409) 다시 읽는다
    S.busy += 1;
    state(label || "저장 중…");
    try {
      const r = await fn();
      state("저장됨 — 작업 폴더");
      return r;
    } catch (e) {
      if (e.status === 409 && !/되돌릴/.test(e.message)) { toast(e.message, true); await load(); }
      else { toast(e.message, true); state("저장 못 함", true); }
      return null;
    } finally { S.busy -= 1; }
  }

  // ---- 그리기 ----
  function tabs() {
    const box = $("shTabs");
    box.textContent = "";
    S.sheets.forEach((s, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sh-tab" + (s.hidden ? " hid" : "");
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(i === S.cur));
      b.textContent = s.name;
      if (s.hidden) b.title = "숨긴 시트(엑셀에서 숨김)";
      b.onclick = () => { ed.focus({ preventScroll: true }); if (i !== S.cur) { commit(); S.extraR = 0; S.sel = { r0: 1, c0: 1, r1: 1, c1: 1 }; S.act = [1, 1]; load(i).catch((e) => toast(e.message, true)); } };
      box.append(b);
    });
  }

  function draw() {
    const v = S.view, grid = $("shGrid");
    S.cells = new Map();
    for (const it of v.cells) S.cells.set(key(it[0], it[1]), { shown: it[2], edit: it[3], s: it[4], kind: it[5], stale: !!it[6] });
    S.merges = new Map();
    S.covered = new Map();
    for (const [r0, c0, r1, c1] of v.merges) {
      S.merges.set(key(r0, c0), [r1, c1]);
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) if (r !== r0 || c !== c0) S.covered.set(key(r, c), [r0, c0]);
    }
    S.hidR = new Set(v.hiddenRows);
    S.hidC = new Set(v.hiddenCols);
    S.maxR = Math.min(Math.max(v.rows + 30, 60) + S.extraR, 1048576);
    S.maxC = Math.min(Math.max(v.cols + 3, 12), 16384);
    const note = $("shNote");
    note.hidden = !v.truncated;
    if (v.truncated) note.textContent = `이 시트는 ${v.used[0]}행 · ${v.used[1]}열까지 있어 앞 2,000행 · 200열만 보입니다 — 파일의 나머지는 그대로 남습니다`;
    const colW = (c) => (c <= v.colW.length ? v.colW[c - 1] : 64);
    grid.textContent = "";
    const cg = document.createElement("colgroup");
    const c0 = document.createElement("col");
    c0.style.width = `${Math.max(36, String(S.maxR).length * 9 + 10)}px`;
    cg.append(c0);
    for (let c = 1; c <= S.maxC; c++) {
      if (S.hidC.has(c)) continue;
      const col = document.createElement("col");
      col.style.width = `${colW(c)}px`;
      cg.append(col);
    }
    grid.append(cg);
    const head = document.createElement("thead"), hr = document.createElement("tr"), corner = document.createElement("th");
    corner.className = "sh-corner";
    corner.title = "시트 전체 고르기";
    corner.onmousedown = (e) => { e.preventDefault(); commit(); select(1, 1, S.maxR, S.maxC, [1, 1]); };
    hr.append(corner);
    for (let c = 1; c <= S.maxC; c++) {
      if (S.hidC.has(c)) continue;
      const th = document.createElement("th");
      th.textContent = colName(c);
      th.dataset.c = c;
      th.onmousedown = (e) => { e.preventDefault(); commit(); select(1, c, S.maxR, e.shiftKey ? S.act[1] : c, [1, c]); };
      hr.append(th);
    }
    head.append(hr);
    grid.append(head);
    const body = document.createElement("tbody"), styles = v.styles;
    for (let r = 1; r <= S.maxR; r++) {
      if (S.hidR.has(r)) continue;
      const tr = document.createElement("tr");
      tr.dataset.r = r;
      const h = v.rowH[r] || v.defaultRowH;
      tr.style.height = `${h}px`;
      const th = document.createElement("th");
      th.textContent = r;
      th.dataset.r = r;
      th.onmousedown = (e) => { e.preventDefault(); commit(); const a = e.shiftKey ? S.act[0] : r; select(Math.min(a, r), 1, Math.max(a, r), S.maxC, [r, 1]); rowDrag(r); };
      th.oncontextmenu = (e) => { e.preventDefault(); if (!(S.sel.c0 === 1 && S.sel.c1 === S.maxC && r >= S.sel.r0 && r <= S.sel.r1)) select(r, 1, r, S.maxC, [r, 1]); menu(e.clientX, e.clientY); };
      tr.append(th);
      for (let c = 1; c <= S.maxC; c++) {
        if (S.hidC.has(c) || S.covered.has(key(r, c))) continue;
        const td = document.createElement("td");
        td.dataset.r = r;
        td.dataset.c = c;
        const m = S.merges.get(key(r, c));
        if (m) {
          let rs = 0, cs = 0;
          for (let k = r; k <= m[0]; k++) if (!S.hidR.has(k)) rs++;
          for (let k = c; k <= m[1]; k++) if (!S.hidC.has(k)) cs++;
          if (rs > 1) td.rowSpan = rs;
          if (cs > 1) td.colSpan = cs;
        }
        paint(td, S.cells.get(key(r, c)), styles);
        tr.append(td);
      }
      body.append(tr);
    }
    grid.append(body);
    spill();
    frozen();
    const more = document.querySelector(".sh-more") || Object.assign(document.createElement("button"), { type: "button", className: "btn sm sh-more", textContent: "행 50개 더 보기" });
    more.onclick = () => { S.extraR += 50; draw(); };
    $("shInner").append(more);
    marks();
    placeEditor();
  }

  function paint(td, cell, styles) {
    td.className = "";
    td.removeAttribute("style");
    td.removeAttribute("title");
    td.textContent = cell ? cell.shown || (cell.kind === "f" ? cell.edit : "") : "";
    if (!cell) return;
    const css = typeof cell.s === "number" ? styles[cell.s] || {} : cell.s || {};
    Object.assign(td.style, css);
    if (css.whiteSpace === "pre-wrap") td.classList.add("wrap");
    if (!css.textAlign && (cell.kind === "n" || cell.kind === "d" || (cell.kind === "f" && /^-?[\d,.]+%?$/.test(cell.shown)))) td.classList.add("num");
    if (cell.kind === "e") td.classList.add("err");
    if (cell.stale) { td.classList.add("stale"); td.title = "수식 — 엑셀에서 열면 다시 계산됩니다(이 화면은 마지막으로 계산된 값을 보입니다)"; }
  }

  function spill() { // 줄 바꿈 없는 왼쪽 맞춤 글은 오른쪽 칸이 비었으면 넘쳐 보이게(엑셀처럼)
    for (const td of $("shGrid").querySelectorAll("td")) {
      td.classList.remove("spill");
      if (!td.textContent || td.classList.contains("wrap") || td.classList.contains("num") || (td.style.textAlign && td.style.textAlign !== "left")) continue;
      const r = +td.dataset.r, c = +td.dataset.c + (td.colSpan || 1), right = S.cells.get(key(r, c));
      if (!right || !(right.shown || right.edit)) td.classList.add("spill");
    }
  }

  function frozen() { // 틀 고정 — 위 · 왼쪽 행 · 열을 머리처럼 붙여 둔다
    const f = S.view.frozen || {}, grid = $("shGrid");
    if (!f.rows && !f.cols) return;
    const headH = grid.tHead.offsetHeight, rowHW = grid.querySelector("tbody th") ? grid.querySelector("tbody th").offsetWidth : 0;
    let top = headH;
    for (const tr of grid.tBodies[0].rows) {
      const r = +tr.dataset.r;
      if (r > f.rows) break;
      for (const cell of tr.cells) { cell.style.position = "sticky"; cell.style.top = `${top}px`; cell.style.zIndex = cell.tagName === "TH" ? 4 : 2; if (cell.tagName === "TD" && !cell.style.background) cell.style.background = "#fff"; }
      top += tr.offsetHeight;
    }
    if (f.cols) {
      const lefts = new Map();
      let left = rowHW;
      for (const th of grid.tHead.rows[0].cells) {
        const c = +th.dataset.c;
        if (!c) continue;
        if (c > f.cols) break;
        lefts.set(c, left);
        th.style.left = `${left}px`;
        th.style.zIndex = 4;
        left += th.offsetWidth;
      }
      for (const td of grid.querySelectorAll("td")) {
        const l = lefts.get(+td.dataset.c);
        if (l === undefined) continue;
        td.style.position = "sticky";
        td.style.left = `${l}px`;
        td.style.zIndex = td.style.top ? 3 : 1;
        if (!td.style.background) td.style.background = "#fff";
      }
    }
  }

  // ---- 고르기 ----
  const tdAt = (r, c) => $("shGrid").querySelector(`td[data-r="${r}"][data-c="${c}"]`);
  function norm(r, c) { const cov = S.covered.get(key(r, c)); return cov || [r, c]; }
  function select(r0, c0, r1, c1, act) {
    S.sel = { r0: Math.min(r0, r1), c0: Math.min(c0, c1), r1: Math.max(r0, r1), c1: Math.max(c0, c1) };
    S.act = act ? norm(act[0], act[1]) : norm(r0, c0);
    marks();
    placeEditor();
  }
  function marks() {
    const grid = $("shGrid"), { r0, c0, r1, c1 } = S.sel, many = r0 !== r1 || c0 !== c1;
    for (const td of grid.querySelectorAll("td.sel, td.act")) td.classList.remove("sel", "act");
    for (const th of grid.querySelectorAll("th.on")) th.classList.remove("on");
    if (many) {
      for (const tr of grid.tBodies[0].rows) {
        const r = +tr.dataset.r;
        if (r < r0) continue;
        if (r > r1) break;
        for (const td of tr.cells) if (td.tagName === "TD" && +td.dataset.c >= c0 && +td.dataset.c <= c1) td.classList.add("sel");
      }
    }
    const a = tdAt(S.act[0], S.act[1]);
    if (a) a.classList.add("act");
    for (const th of grid.querySelectorAll("thead th[data-c]")) if (+th.dataset.c >= c0 && +th.dataset.c <= c1) th.classList.add("on");
    for (const th of grid.querySelectorAll("tbody th[data-r]")) if (+th.dataset.r >= r0 && +th.dataset.r <= r1) th.classList.add("on");
    $("shAddr").textContent = many ? `${colName(c0)}${r0}:${colName(c1)}${r1}` : `${colName(S.act[1])}${S.act[0]}`;
    const cell = S.cells.get(key(S.act[0], S.act[1]));
    if (document.activeElement !== $("shFx")) $("shFx").value = cell ? cell.edit : "";
  }

  function step(r, c, dr, dc) { // 한 칸 옮김 — 숨긴 행 · 열과 병합을 건너뛴다
    const m = S.merges.get(key(r, c));
    if (m && dr > 0) r = m[0];
    if (m && dc > 0) c = m[1];
    do { r += dr; c += dc; } while ((S.hidR.has(r) && dr) || (S.hidC.has(c) && dc));
    r = Math.max(1, r);
    c = Math.max(1, Math.min(S.maxC, c));
    if (r > S.maxR) { S.extraR += 50; draw(); }
    return norm(r, c);
  }
  function move(dr, dc, extend = false) {
    if (extend) {
      const [r, c] = step(dr ? (dr > 0 ? S.sel.r1 : S.sel.r0) : S.act[0], dc ? (dc > 0 ? S.sel.c1 : S.sel.c0) : S.act[1], dr, dc);
      const r0 = dr ? Math.min(S.act[0], r) : S.sel.r0, r1 = dr ? Math.max(S.act[0], r) : S.sel.r1;
      const c0 = dc ? Math.min(S.act[1], c) : S.sel.c0, c1 = dc ? Math.max(S.act[1], c) : S.sel.c1;
      S.sel = { r0, c0, r1, c1 };
      marks();
      return;
    }
    const [r, c] = step(S.act[0], S.act[1], dr, dc);
    select(r, c, r, c);
    reveal();
  }
  function reveal() {
    const td = tdAt(S.act[0], S.act[1]);
    if (td) td.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  let dragFrom = null;
  $("shGrid").addEventListener("mousedown", (e) => {
    const td = e.target.closest("td");
    if (!td || e.button !== 0) return;
    e.preventDefault();
    commit();
    const r = +td.dataset.r, c = +td.dataset.c;
    if (e.shiftKey) { select(S.act[0], S.act[1], r, c, S.act); return; }
    select(r, c, r, c);
    dragFrom = [r, c];
    $("shEd").focus();
  });
  document.addEventListener("mouseover", (e) => {
    if (!dragFrom || !(e.buttons & 1)) { dragFrom = null; return; }
    const td = e.target.closest && e.target.closest("#shGrid td");
    if (!td) return;
    const r = +td.dataset.r, c = +td.dataset.c, m = S.merges.get(key(r, c)) || [r, c];
    select(dragFrom[0], dragFrom[1], Math.max(r, m[0]), Math.max(c, m[1]), dragFrom);
  });
  document.addEventListener("mouseup", () => { dragFrom = null; rowFrom = null; });
  let rowFrom = null;
  function rowDrag(r) { rowFrom = r; }
  document.addEventListener("mouseover", (e) => {
    if (!rowFrom || !(e.buttons & 1)) return;
    const th = e.target.closest && e.target.closest("#shGrid tbody th");
    if (th) select(Math.min(rowFrom, +th.dataset.r), 1, Math.max(rowFrom, +th.dataset.r), S.maxC, [rowFrom, 1]);
  });
  $("shGrid").addEventListener("dblclick", (e) => { if (e.target.closest("td")) edit(true); });
  $("shGrid").addEventListener("contextmenu", (e) => {
    const td = e.target.closest("td");
    if (!td) return;
    e.preventDefault();
    const r = +td.dataset.r, c = +td.dataset.c;
    if (!(r >= S.sel.r0 && r <= S.sel.r1 && c >= S.sel.c0 && c <= S.sel.c1)) select(r, c, r, c);
    menu(e.clientX, e.clientY);
  });

  // ---- 고치기 — 편집 상자는 늘 고른 칸 위에 있고 초점을 쥔다(안 보일 뿐). 글이 들어오면 그때 보인다 ----
  const ed = $("shEd");
  function placeEditor() {
    const td = tdAt(S.act[0], S.act[1]);
    if (!td) return;
    ed.style.left = `${td.offsetLeft}px`;
    ed.style.top = `${td.offsetTop}px`;
    ed.style.width = `${Math.max(td.offsetWidth, 40)}px`;
    ed.style.minHeight = `${td.offsetHeight}px`;
    ed.style.height = `${td.offsetHeight}px`;
    if (!S.editing) { ed.value = ""; if (document.activeElement !== $("shFx")) ed.focus({ preventScroll: true }); }
  }
  function grow() {
    if (!S.editing) return;
    const td = tdAt(S.act[0], S.act[1]);
    ed.style.height = "auto";
    ed.style.height = `${Math.max(ed.scrollHeight + 4, td ? td.offsetHeight : 20)}px`;
    if (td) ed.style.width = `${Math.max(td.offsetWidth, Math.min(480, ed.value.split("\n").reduce((m, l) => Math.max(m, l.length), 0) * 9 + 16))}px`;
  }
  function edit(keep) { // keep = 칸의 글을 이어 고침(F2 · 두 번 누름) · 아니면 새로 씀(바로 친 글)
    const cell = S.cells.get(key(S.act[0], S.act[1]));
    if (cell && cell.kind === "e") { /* 오류 값도 고칠 수 있다 */ }
    S.editing = true;
    S.origin = cell ? cell.edit : "";
    if (keep) ed.value = S.origin;
    ed.classList.add("on");
    const td = tdAt(S.act[0], S.act[1]);
    if (td) { const cs = getComputedStyle(td); ed.style.fontWeight = cs.fontWeight; ed.style.fontStyle = cs.fontStyle; ed.style.textAlign = cs.textAlign === "right" ? "right" : "left"; }
    ed.focus({ preventScroll: true });
    if (keep) ed.setSelectionRange(ed.value.length, ed.value.length);
    grow();
    $("shFx").value = ed.value;
  }
  function stop() { S.editing = false; ed.classList.remove("on"); ed.value = ""; ed.style.fontWeight = ed.style.fontStyle = ed.style.textAlign = ""; }
  function commit() {
    if (!S.editing) return false;
    const text = ed.value, [r, c] = S.act;
    stop();
    if (text !== S.origin) put([{ r, c, text }]);
    return true;
  }
  ed.addEventListener("input", () => { if (!S.editing) { const v = ed.value; edit(false); ed.value = v; } grow(); $("shFx").value = ed.value; });
  ed.addEventListener("compositionstart", () => { if (!S.editing) edit(false); });
  ed.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    const k = e.key, mod = e.ctrlKey || e.metaKey;
    if (mod && (k === "s" || k === "S")) { e.preventDefault(); commit(); download(); return; }
    if (S.editing) {
      if (k === "Enter" && e.altKey) { e.preventDefault(); const p = ed.selectionStart; ed.setRangeText("\n", p, ed.selectionEnd, "end"); grow(); return; }
      if (k === "Enter") { e.preventDefault(); commit(); move(e.shiftKey ? -1 : 1, 0); return; }
      if (k === "Tab") { e.preventDefault(); commit(); move(0, e.shiftKey ? -1 : 1); return; }
      if (k === "Escape") { e.preventDefault(); stop(); marks(); placeEditor(); return; }
      return;
    }
    const arrows = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    if (arrows[k]) { e.preventDefault(); move(...arrows[k], e.shiftKey); return; }
    if (k === "Enter") { e.preventDefault(); move(e.shiftKey ? -1 : 1, 0); return; }
    if (k === "Tab") { e.preventDefault(); move(0, e.shiftKey ? -1 : 1); return; }
    if (k === "F2") { e.preventDefault(); edit(true); return; }
    if (k === "Delete") { e.preventDefault(); clearSel(); return; }
    if (k === "Backspace") { e.preventDefault(); edit(false); return; }
    if (mod && (k === "z" || k === "Z")) { e.preventDefault(); undo(); return; }
    if (mod && (k === "a" || k === "A")) { e.preventDefault(); select(1, 1, S.maxR, S.maxC, S.act); return; }
    if (k === "Home") { e.preventDefault(); const r = mod ? 1 : S.act[0]; select(r, 1, r, 1); reveal(); return; }
  });
  ed.addEventListener("copy", (e) => {
    if (S.editing) return;
    e.preventDefault();
    e.clipboardData.setData("text/plain", tsvOf(S.sel));
    toast(`${(S.sel.r1 - S.sel.r0 + 1) * (S.sel.c1 - S.sel.c0 + 1)}칸을 복사했습니다`);
  });
  ed.addEventListener("cut", (e) => { if (S.editing) return; e.preventDefault(); e.clipboardData.setData("text/plain", tsvOf(S.sel)); clearSel(); });
  ed.addEventListener("paste", (e) => {
    if (S.editing) return;
    e.preventDefault();
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;
    const rows = parseTsv(text), out = [];
    const one = rows.length === 1 && rows[0].length === 1, { r0, c0, r1, c1 } = S.sel;
    if (one && (r1 > r0 || c1 > c0)) { // 칸 하나를 여러 칸에 — 고른 칸 모두에
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) if (!S.covered.has(key(r, c)) && !S.hidR.has(r) && !S.hidC.has(c)) out.push({ r, c, text: rows[0][0] });
    } else {
      rows.forEach((row, i) => row.forEach((text, j) => { const r = S.act[0] + i, c = S.act[1] + j; if (!S.covered.has(key(r, c))) out.push({ r, c, text }); }));
      select(S.act[0], S.act[1], S.act[0] + rows.length - 1, S.act[1] + Math.max(...rows.map((x) => x.length)) - 1, S.act);
    }
    if (out.length) put(out, `${out.length}칸 붙여 넣는 중…`);
  });

  $("shFx").addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter") { e.preventDefault(); const [r, c] = S.act, cell = S.cells.get(key(r, c)), text = $("shFx").value; if (text !== (cell ? cell.edit : "")) put([{ r, c, text }]); ed.focus(); move(1, 0); }
    if (e.key === "Escape") { e.preventDefault(); marks(); ed.focus(); }
  });
  $("shFx").addEventListener("focus", () => { if (S.editing) commit(); });

  async function put(cells, label) {
    const r = await send(() => api(`/api/sheets/${S.id}/cells`, { method: "PUT", ...J({ sheet: S.cur, rev: S.rev, cells }) }), label);
    if (!r) { marks(); return; }
    S.rev = r.rev;
    S.undo = r.undo;
    $("shUndo").disabled = !r.undo;
    let grow_ = false;
    for (const [rr, cc, shown, edit_, css, kind, stale] of r.cells) {
      S.cells.set(key(rr, cc), { shown, edit: edit_, s: css, kind, stale: !!stale });
      const td = tdAt(rr, cc);
      if (td) paint(td, S.cells.get(key(rr, cc)), S.view.styles);
      if (rr > S.view.rows - 0) grow_ = grow_ || rr + 30 > S.maxR;
      if (cc + 3 > S.maxC) grow_ = true;
    }
    if (grow_) { S.view.rows = Math.max(S.view.rows, ...r.cells.map((x) => x[0])); S.view.cols = Math.max(S.view.cols, ...r.cells.map((x) => x[1])); keepCells(); draw(); } else spill();
    marks();
  }
  function keepCells() { // 다시 그리기 전에 지금 칸들을 보기에 되적는다
    S.view.cells = [...S.cells.entries()].map(([k, v]) => { const [r, c] = k.split(",").map(Number); return [r, c, v.shown, v.edit, v.s, v.kind, v.stale ? 1 : 0]; });
  }
  function clearSel() {
    const { r0, c0, r1, c1 } = S.sel, out = [];
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) {
      const cell = S.cells.get(key(r, c));
      if (cell && (cell.shown || cell.edit)) out.push({ r, c, text: "" });
    }
    if (out.length) put(out, `${out.length}칸 비우는 중…`);
  }

  // ---- 행 · 실행 취소 · 내려받기 ----
  async function rows(op) {
    commit();
    const { r0, r1 } = S.sel, n = r1 - r0 + 1;
    const body = op === "up" ? { op: "insert", at: r0, n } : op === "down" ? { op: "insert", at: r1 + 1, n } : { op: "delete", r0, r1 };
    if (op === "del" && n > 1 && !confirm(`${r0}~${r1}행(${n}행)을 지울까요? 실행 취소로 되돌릴 수 있습니다.`)) return;
    const d = await send(() => api(`/api/sheets/${S.id}/rows`, { method: "POST", ...J({ sheet: S.cur, rev: S.rev, ...body }) }), op === "del" ? "행 지우는 중…" : "행 넣는 중…");
    if (!d) return;
    take(d);
    const at = op === "down" ? r1 + 1 : r0;
    select(at, 1, op === "del" ? at : at + n - 1, S.maxC, [at, S.act[1]]);
    toast(op === "del" ? `${n}행을 지웠습니다` : `${n}행을 넣었습니다`);
  }
  async function undo() {
    commit();
    const d = await send(() => api(`/api/sheets/${S.id}/undo`, { method: "POST", ...J({ sheet: S.cur }) }), "되돌리는 중…");
    if (d) { take(d); toast("되돌렸습니다"); }
  }
  function download() { $("shDownload").click(); }
  $("shUndo").onclick = undo;
  $("shRowUp").onclick = () => rows("up");
  $("shRowDown").onclick = () => rows("down");
  $("shRowDel").onclick = () => rows("del");
  $("shDownload").addEventListener("click", (e) => { if (S.busy) { e.preventDefault(); toast("저장이 끝난 뒤 다시 누르세요"); } });

  function menu(x, y) {
    const m = $("shMenu"), { r0, r1 } = S.sel, n = r1 - r0 + 1, rows_ = n > 1 ? `${n}행` : "행";
    m.textContent = "";
    const item = (label, fn, cls) => { const b = document.createElement("button"); b.type = "button"; b.textContent = label; if (cls) b.className = cls; b.onclick = () => { hide(); fn(); }; m.append(b); };
    item(`위에 ${rows_} 넣기`, () => rows("up"));
    item(`아래에 ${rows_} 넣기`, () => rows("down"));
    item(n > 1 ? `${r0}~${r1}행 지우기` : `${r0}행 지우기`, () => rows("del"), "danger");
    item("고른 칸 비우기", clearSel);
    m.hidden = false;
    m.style.left = `${Math.min(x, innerWidth - m.offsetWidth - 8)}px`;
    m.style.top = `${Math.min(y, innerHeight - m.offsetHeight - 8)}px`;
    m.querySelector("button").focus();
    const hide = () => { m.hidden = true; document.removeEventListener("mousedown", away, true); ed.focus({ preventScroll: true }); };
    const away = (e) => { if (!m.contains(e.target)) hide(); };
    document.addEventListener("mousedown", away, true);
    m.onkeydown = (e) => { if (e.key === "Escape") hide(); };
  }

  // ---- 글 ↔ 칸 ----
  function colName(c) { let s = ""; while (c > 0) { const m = (c - 1) % 26; s = String.fromCharCode(65 + m) + s; c = Math.floor((c - 1) / 26); } return s; }
  function tsvOf({ r0, c0, r1, c1 }) {
    const lines = [];
    for (let r = r0; r <= Math.min(r1, S.maxR); r++) {
      if (S.hidR.has(r)) continue;
      const row = [];
      for (let c = c0; c <= Math.min(c1, S.maxC); c++) {
        if (S.hidC.has(c)) continue;
        const cell = S.cells.get(key(r, c)), v = cell ? cell.shown : "";
        row.push(/[\t\n"]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
      }
      lines.push(row.join("\t"));
    }
    while (lines.length > 1 && !lines[lines.length - 1].replace(/\t/g, "")) lines.pop();
    return lines.join("\r\n");
  }
  function parseTsv(text) { // 엑셀이 쓰는 꼴 — 탭 · 줄 나눔 · 큰따옴표로 감싼 칸(안의 줄 나눔 · "")
    const rows = [[]];
    let cur = "", i = 0, quoted = false;
    text = text.replace(/\r\n?/g, "\n");
    if (text.endsWith("\n")) text = text.slice(0, -1);
    while (i < text.length) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { cur += '"'; i += 2; continue; }
        if (ch === '"') { quoted = false; i++; continue; }
        cur += ch; i++; continue;
      }
      if (ch === '"' && cur === "") { quoted = true; i++; continue; }
      if (ch === "\t") { rows[rows.length - 1].push(cur); cur = ""; i++; continue; }
      if (ch === "\n") { rows[rows.length - 1].push(cur); rows.push([]); cur = ""; i++; continue; }
      cur += ch; i++;
    }
    rows[rows.length - 1].push(cur);
    return rows;
  }

  addEventListener("beforeunload", (e) => { if (S.editing && ed.value !== S.origin) { e.preventDefault(); e.returnValue = ""; } });
  addEventListener("resize", () => placeEditor());

  // ---- 시작 ----
  const m = location.hash.match(/^#w=([0-9a-f]{12})/);
  if (!m) { state("주소에 작업이 없습니다 — 시작 화면에서 xlsx 파일을 여세요", true); return; }
  S.id = m[1];
  state("여는 중…");
  load(0).then(() => ed.focus({ preventScroll: true })).catch((e) => { state("열지 못함", true); toast(e.message, true); });
})();
