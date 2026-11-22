"use strict";
// 그림 도구(spec_그림 ② §1~§6) — 문서의 그림을 누르면 고르고(파란 테두리 · Ctrl/Shift+누름 = 둘째 그림) 그림 위에 「그림 도구」 띠를 띄운다:
// 표로 바꾸기(LLM) · 캡션 넣기(LLM) · 선명하게 · 가운데 · (둘이면) 한 줄에. 오른쪽 단추 메뉴에도 같은 항목. LLM 두 기능과 선명하게는 2열(kind "picTools" — 팝업 아님)에서 미리 보고 「넣기」·「바꾸기」.
// app.js 가 주는 것: state · $ · el · api · toast · hBtn · structOp · ctxOpen · ctxClose · headsDlg · heads · IMG_OK · scrollHow. tables.js: xlBlocks · xlBlock.
// 서버 짝 = app/pic_tools_api.py(끝점) · app/pic_tools.py(순수) · app/hwpx_pic.py(문서 바꾸기). index.html 이 app.js · tables.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const PIC_MAX = 2;
const pic = { ids: [], bar: null, raf: 0, view: null, seq: 0 }; // view = 2열의 지금 화면 {kind, id, …}
const picUrl = (tail) => `/api/docs/${encodeURIComponent(state.id)}/pics/${tail}`;
const picOn = () => heads.dlg === "picTools" && !!state.id;

// ---- 블록 읽기 --------------------------------------------------------------------------------------------------------
function picWalk(blocks, fn, parent = null) { // 모든 블록(칸 안 포함) — fn(b, 형제 목록)
  for (const b of blocks || []) {
    fn(b, blocks);
    for (const c of b.cells || []) picWalk(c.blocks || [], fn, b);
  }
}
function picBlock(id) {
  let hit = null;
  picWalk(state.blocks, (b) => { if (!hit && b.id === id && b.type === "image") hit = b; });
  return hit;
}
function picHasObjCaption(id) {
  let has = false;
  picWalk(state.blocks, (b) => { if (b.captionOf === id && (b.text || "").trim()) has = true; });
  return has;
}
const picExt = (b) => ((b && b.media) || "").split(".").pop().toLowerCase();
const picRaster = (b) => !!(b && b.media && ["png", "jpg", "jpeg", "gif", "bmp", "webp"].includes(picExt(b)));
const picEl = (id) => document.querySelector(`#doc [data-img="${CSS.escape(id)}"]`);
function picTarget(t) { // 누른 곳의 그림 블록 요소(글 속 그림 아이콘 · 빈 자리 표시는 아님) | null
  const n = t && t.closest ? t.closest("#doc img.img[data-img], #doc .img-ph[data-img]") : null;
  return n && !n.classList.contains("pic-held") ? n : null;
}

// ---- 고르기 · 표시 -------------------------------------------------------------------------------------------------------
function picPaint() {
  let css = document.getElementById("picSelCss");
  const ids = pic.ids.filter((i) => /^[\w.-]+$/.test(i));
  if (!ids.length) { if (css) css.textContent = ""; picBarDraw(); return; }
  if (!css) { css = el("style"); css.id = "picSelCss"; document.head.append(css); }
  css.textContent = `${ids.map((i) => `#doc [data-img="${i}"]`).join(",")}{outline:2px solid var(--accent,#2458d6);outline-offset:2px}`;
  picBarDraw();
}
function picSet(ids) { pic.ids = ids.slice(-PIC_MAX); picPaint(); }
function picClear() { if (pic.ids.length) { pic.ids = []; picPaint(); } }

// ---- 그림 위의 띠 ---------------------------------------------------------------------------------------------------------
function picItems() { // [이름, 할 일, 꺼짐 까닭 | ""] — 띠와 오른쪽 단추 메뉴가 같이 쓴다
  const ids = pic.ids, blks = ids.map(picBlock);
  if (!ids.length || blks.some((b) => !b)) return [];
  if (state.format === "docx") return [["그림 도구", null, "그림 도구는 지금 hwpx 문서만 됩니다"]];
  if (ids.length === 2) return [["한 줄에", () => picRow(), ""], ["가운데", () => picCenter(), ""]];
  const b = blks[0], raster = picRaster(b) ? "" : "그림 파일을 읽을 수 없는 그림입니다(연결 그림 · wmf · emf) — 가운데 · 한 줄에만 됩니다";
  return [["표로 바꾸기", () => picOpen("table", b.id), raster],
    ["캡션 넣기", () => picOpen("caption", b.id), raster || (picHasObjCaption(b.id) ? "이미 캡션이 있습니다" : "")],
    ["선명하게", () => picOpen("sharpen", b.id), raster],
    ["가운데", () => picCenter(), ""]];
}
function picBarDraw() {
  if (!pic.bar) {
    pic.bar = el("div", "pic-bar");
    pic.bar.setAttribute("role", "toolbar");
    pic.bar.setAttribute("aria-label", "그림 도구");
    pic.bar.hidden = true;
    pic.bar.addEventListener("mousedown", (e) => e.preventDefault()); // 누를 때 문서의 고르기 · 글 커서가 안 바뀌게
    document.body.append(pic.bar);
  }
  const items = picItems();
  pic.bar.textContent = "";
  if (!items.length) { pic.bar.hidden = true; return; }
  pic.bar.append(el("span", "pic-bar-name", pic.ids.length === 2 ? "그림 둘" : "그림"));
  for (const [name, run, off] of items) {
    const b = el("button", "pic-bar-btn", name);
    b.type = "button";
    if (off || !run) { b.disabled = true; b.title = off; } else b.onclick = () => run();
    pic.bar.append(b);
  }
  pic.bar.hidden = false;
  picBarPlace();
}
function picBarPlace() {
  if (!pic.bar || pic.bar.hidden) return;
  const n = pic.ids.length ? picEl(pic.ids[pic.ids.length - 1]) : null;
  if (!n) { pic.bar.style.visibility = "hidden"; return; }
  const r = n.getBoundingClientRect(), sc = $("scroller").getBoundingClientRect();
  const off = r.bottom < sc.top + 8 || r.top > sc.bottom - 8;
  pic.bar.style.visibility = off ? "hidden" : "";
  const h = pic.bar.offsetHeight, w = pic.bar.offsetWidth;
  const top = Math.max(sc.top + 4, r.top - h - 6);
  pic.bar.style.top = `${Math.min(top, sc.bottom - h - 4)}px`;
  pic.bar.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`;
}
function picBarSoon() { cancelAnimationFrame(pic.raf); pic.raf = requestAnimationFrame(picBarPlace); }

// ---- 고르기 손짓 · 메뉴 ------------------------------------------------------------------------------------------------------
function picBind() {
  document.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || !state.id) return;
    if (pic.bar && pic.bar.contains(e.target)) return;
    const n = picTarget(e.target);
    if (!n) { if (e.target.closest && (e.target.closest("#doc") || e.target.closest("#scroller"))) picClear(); return; }
    const id = n.dataset.img;
    if (e.ctrlKey || e.shiftKey || e.metaKey) picSet(pic.ids.includes(id) ? pic.ids.filter((i) => i !== id) : [...pic.ids, id]);
    else picSet([id]);
  }, true);
  document.addEventListener("contextmenu", (e) => { // 그림 위 — 표 칸 메뉴(tselContextMenu) · 문단 메뉴보다 먼저(잡는 단계)
    const n = state.id ? picTarget(e.target) : null;
    if (!n) return;
    if (!pic.ids.includes(n.dataset.img)) picSet([n.dataset.img]);
    const items = picItems();
    if (!items.length) return;
    e.preventDefault();
    e.stopPropagation();
    ctxOpen(e, items.map(([name, run, off]) => [name, "", run || (() => {}), !!off || !run]));
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && pic.ids.length && !(e.target.closest && e.target.closest("input, textarea, select, dialog, .ctx-menu"))) picClear();
  });
  const sc = $("scroller");
  if (sc) sc.addEventListener("scroll", picBarSoon, { passive: true });
  window.addEventListener("resize", picBarSoon);
  if (typeof MutationObserver === "function" && $("doc")) { // 쪽을 다시 그리면 그림 요소가 새로 생긴다 — 띠 자리를 다시 · 없어진 그림은 고르기에서 뺀다
    new MutationObserver(() => {
      const keep = pic.ids.filter((i) => picBlock(i));
      if (keep.length !== pic.ids.length) { pic.ids = keep; picPaint(); } else picBarSoon();
    }).observe($("doc"), { childList: true, subtree: true });
  }
}

// ---- 바로 하는 일 — 가운데 · 한 줄에 -----------------------------------------------------------------------------------------
async function picCenter() {
  const ids = pic.ids.slice();
  if (!ids.length) return;
  const r = await structOp("pics/center", { ids });
  if (!r) return;
  toast(r.same ? "이미 가운데입니다" : `그림 ${ids.length}개를 가운데로 놓았습니다 — 실행 취소로 되돌릴 수 있습니다`);
}
async function picRow() {
  const ids = pic.ids.slice();
  if (ids.length !== 2) return;
  const r = await structOp("pics/row", { ids });
  if (!r || !r.made) return;
  toast(`두 그림을 한 줄에 놓았습니다${r.made.scaled ? ` — 글 폭에 맞게 ${Math.round(r.made.scaled * 100)}%로 줄임` : ""} · 실행 취소로 되돌릴 수 있습니다`);
  picSet([r.made.first, r.made.second]);
}

// ---- 2열 ---------------------------------------------------------------------------------------------------------------
const PIC_TITLE = { table: "그림 → 표", caption: "캡션 넣기", sharpen: "선명하게" };
const PIC_NOTE = { table: "LLM 이 그림 안의 표와 글을 읽습니다 — 보고 고친 뒤 「문서에 넣기」", caption: "그림과 소속 헤딩을 읽고 캡션을 짓습니다", sharpen: "작은 그림을 키우고 또렷하게 — 표시 크기는 그대로" };
async function picOpen(kind, id) {
  if (!state.id || !picBlock(id)) return;
  ctxClose();
  pic.seq += 1;
  const seq = pic.seq;
  pic.view = { kind, id, info: null, busy: false, started: 0, res: null, err: "", level: "normal", place: "replace", tpl: null, caption: "" };
  headsDlg("picTools", PIC_TITLE[kind], PIC_NOTE[kind]);
  picDraw();
  try {
    const info = await api(picUrl(encodeURIComponent(id)));
    if (seq !== pic.seq) return;
    pic.view.info = info;
    pic.view.tpl = info.template;
  } catch (e) { if (seq === pic.seq) pic.view.err = e.message; }
  if (picOn()) picDraw();
}
function picImg(id, cls = "pic-col-img") {
  const b = picBlock(id), img = new Image();
  img.className = cls;
  img.alt = "";
  if (b && b.media) img.src = `/api/docs/${state.id}/media?name=${encodeURIComponent(b.media)}`;
  return img;
}
function picDraw() {
  if (!picOn() || !pic.view) return;
  const v = pic.view, body = $("headsDlgBody"), foot = $("headsDlgFoot"), tools = $("headsDlgTools");
  body.textContent = "";
  foot.textContent = "";
  tools.textContent = "";
  const b = picBlock(v.id);
  if (!b) { body.append(el("p", "pic-col-msg err", "그 그림이 지금 문서에 없습니다(지워졌거나 바뀜) — 그림을 다시 누르세요")); return; }
  tools.append(hBtn("문서에서 보기", () => { const n = picEl(v.id); if (n) n.scrollIntoView({ block: "center", behavior: typeof scrollHow === "function" ? scrollHow() : "auto" }); }));
  const top = el("div", "pic-col-top");
  top.append(picImg(v.id));
  const meta = el("div", "pic-col-meta");
  meta.append(el("span", null, `${b.widthMm || "?"}×${b.heightMm || "?"}mm · ${picExt(b).toUpperCase()}`));
  if (v.info && v.info.heading && v.info.heading.length) {
    const h = el("div", "pic-col-head");
    h.append(el("span", "pic-col-label", "소속 헤딩"), el("span", null, v.info.heading.join(" › ")));
    meta.append(h);
  }
  top.append(meta);
  body.append(top);
  if (v.err) body.append(el("p", "pic-col-msg err", v.err));
  if (v.kind === "table") picDrawTable(body, foot);
  else if (v.kind === "caption") picDrawCaption(body, foot);
  else picDrawSharpen(body, foot);
}
function picBusy(body, what) {
  const v = pic.view, s = el("p", "pic-col-msg busy");
  const tick = () => { s.textContent = `${what} … ${Math.round((Date.now() - v.started) / 1000)}초`; };
  tick();
  const t = setInterval(() => { if (!s.isConnected || !v.busy) { clearInterval(t); return; } tick(); }, 1000);
  body.append(s);
}
async function picCall(what, fn) {
  const v = pic.view, seq = pic.seq;
  v.busy = true; v.err = ""; v.started = Date.now();
  picDraw();
  try { const r = await fn(); if (seq === pic.seq) return r; } catch (e) { if (seq === pic.seq) v.err = `${what}: ${e.message}`; } finally { if (seq === pic.seq) { v.busy = false; picDraw(); } }
  return null;
}
function picCallNote(call) {
  if (!call) return "";
  const s = [call.model, call.ms != null ? `${(call.ms / 1000).toFixed(1)}초` : "", call.costUsd != null ? `$${Number(call.costUsd).toFixed(3)}` : ""].filter(Boolean);
  return s.join(" · ");
}

// -- 그림 → 표
function picTplSelect(cur, set) {
  const sel = el("select", "pic-col-tpl");
  const tabs = typeof xlBlocks === "function" ? xlBlocks().filter((t) => t.rows >= 2 && t.cols >= 2) : [];
  if (!tabs.length) sel.append(new Option("문서에 표가 없습니다", ""));
  for (const t of tabs) {
    const blk = typeof xlBlock === "function" ? xlBlock(t.id) : null;
    const first = blk ? [...(blk.cells || [])].sort((x, y) => x.row - y.row || x.col - y.col).map((c) => (c.text || "").replace(/\s+/g, " ").trim()).find((x) => x) : "";
    sel.append(new Option(`${t.id} · ${t.rows}×${t.cols}${t.depth > 1 ? " · 칸 안" : ""}${first ? ` · ${first.slice(0, 22)}` : ""}`, t.id));
  }
  sel.value = cur || "";
  sel.onchange = () => set(sel.value || null);
  return sel;
}
function picGridEl(g, k) { // 격자(행 꼴) → 고칠 수 있는 표(칸 글 contenteditable)
  const t = el("table", "pic-grid");
  t.dataset.k = k;
  (g.rows || []).forEach((row, r) => {
    const tr = el("tr");
    (row.cells || []).forEach((c, i) => {
      const head = r < (g.headerRows || 0) || i < (g.headerCols || 0);
      const td = el(head ? "th" : "td", null, c.text || "");
      if ((c.rowSpan || 1) > 1) td.rowSpan = c.rowSpan;
      if ((c.colSpan || 1) > 1) td.colSpan = c.colSpan;
      td.contentEditable = "true";
      td.dataset.r = r;
      td.dataset.i = i;
      tr.append(td);
    });
    t.append(tr);
  });
  return t;
}
function picGridRead(t, g) { // 화면에서 고친 칸 글을 격자에 되읽는다
  const out = JSON.parse(JSON.stringify(g));
  for (const td of t.querySelectorAll("[data-r]")) {
    const c = out.rows[+td.dataset.r].cells[+td.dataset.i];
    c.text = td.innerText.replace(/\r/g, "").replace(/\n+$/, "");
  }
  return out;
}
function picDrawTable(body, foot) {
  const v = pic.view;
  const row = el("div", "pic-col-row");
  row.append(el("span", "pic-col-label", "표 양식"), picTplSelect(v.tpl, (x) => { v.tpl = x; }));
  body.append(row);
  body.append(el("p", "pic-col-hint", "표의 괘선 · 음영 · 글자 모양은 고른 표 양식에서 옵니다. LLM 은 칸 글과 구조만 읽습니다."));
  if (v.busy) picBusy(body, "LLM 이 그림을 읽는 중");
  const read = hBtn(v.res ? "다시 읽기(LLM)" : "그림 읽기(LLM)", async () => {
    const r = await picCall("그림 읽기", () => api(picUrl(`${encodeURIComponent(v.id)}/read-table`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ template: v.tpl || undefined }) }));
    if (r) { v.res = r; v.caption = (r.caption || []).join("\n"); if (r.template && !v.tpl) v.tpl = r.template; picDraw(); }
  }, { cls: v.res ? "btn sm" : "btn sm primary", disabled: v.busy });
  if (!v.res) { foot.append(read); return; }
  const r = v.res;
  const sum = el("p", "pic-col-msg", `표 ${r.tables.length}개${r.dropped && r.dropped.length ? ` · 못 쓴 표 ${r.dropped.length}개` : ""}${r.note ? ` — ${r.note}` : ""}`);
  body.append(sum);
  if (r.dropped && r.dropped.length) body.append(el("p", "pic-col-msg warn", r.dropped.join(" · ")));
  const grids = [];
  r.tables.forEach((g, k) => {
    body.append(el("div", "pic-col-label", `표 ${k + 1} · ${(g.rows || []).length}행`));
    const t = picGridEl(g, k);
    const wrap = el("div", "pic-grid-wrap");
    wrap.append(t);
    body.append(wrap);
    grids.push([t, g]);
  });
  const capL = el("label", "pic-col-field");
  capL.append(el("span", "pic-col-label", "캡션(첫 표 위 · 줄마다 문단)"));
  const cap = el("textarea", "pic-col-cap");
  cap.rows = Math.max(2, Math.min(5, (v.caption.match(/\n/g) || []).length + 1));
  cap.value = v.caption;
  cap.oninput = () => { v.caption = cap.value; };
  capL.append(cap);
  body.append(capL);
  const place = el("div", "pic-col-row");
  for (const [k, name] of [["replace", "그림을 표로 바꾸기"], ["after", "그림은 두고 뒤에 넣기"]]) {
    const l = el("label", "pic-col-radio"), i = el("input");
    i.type = "radio"; i.name = "picPlace"; i.checked = v.place === k; i.onchange = () => { v.place = k; };
    l.append(i, el("span", null, name));
    place.append(l);
  }
  body.append(place);
  if (r.call) body.append(el("p", "pic-col-hint", picCallNote(r.call)));
  const go = hBtn("문서에 넣기", async () => {
    if (!v.tpl) { toast("표 양식(서식을 따올 문서의 표)을 고르세요", true); return; }
    const tables = grids.map(([t, g]) => picGridRead(t, g));
    if (!tables.length) { toast("넣을 표가 없습니다", true); return; }
    const res = await structOp(`pics/${encodeURIComponent(v.id)}/table`, { template: v.tpl, tables, caption: v.caption.split("\n").map((x) => x.trim()).filter(Boolean), replace: v.place === "replace" });
    if (!res || !res.made) return;
    toast(`표 ${res.made.tables.length}개를 넣었습니다${res.made.caption.length ? " · 캡션" : ""}${v.place === "replace" ? " · 그림은 지움" : ""} — 실행 취소로 되돌릴 수 있습니다`);
    picClear();
    const first = res.made.tables[0];
    requestAnimationFrame(() => { const t = document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(first)}"]`); if (t) t.scrollIntoView({ block: "center" }); });
    if (v.place === "replace") { pic.view = null; $("headsDlgBody").textContent = ""; $("headsDlgFoot").textContent = ""; $("headsDlgBody").append(el("p", "pic-col-msg", `그림을 표 ${res.made.tables.length}개로 바꿨습니다.`)); }
    else picDraw();
  }, { cls: "btn sm primary", disabled: v.busy || !r.tables.length });
  foot.append(go, read);
}

// -- 캡션 넣기
function picDrawCaption(body, foot) {
  const v = pic.view;
  if (v.busy) picBusy(body, "LLM 이 캡션을 짓는 중");
  const l = el("label", "pic-col-field");
  l.append(el("span", "pic-col-label", "캡션(그림 아래)"));
  const inp = el("input", "pic-col-capone");
  inp.type = "text";
  inp.placeholder = "직접 쓰거나 「캡션 짓기(LLM)」";
  inp.value = v.caption;
  inp.oninput = () => { v.caption = inp.value; put.disabled = v.busy || !v.caption.trim(); };
  l.append(inp);
  body.append(l);
  if (v.res) {
    if (v.res.note) body.append(el("p", "pic-col-hint", v.res.note));
    if (v.res.call) body.append(el("p", "pic-col-hint", picCallNote(v.res.call)));
  }
  body.append(el("p", "pic-col-hint", "모양은 이 문서에서 가장 많이 쓴 그림 캡션의 것을 따릅니다(없으면 그림 문단의 모양)."));
  const ask = hBtn(v.res ? "다시 짓기(LLM)" : "캡션 짓기(LLM)", async () => {
    const r = await picCall("캡션 짓기", () => api(picUrl(`${encodeURIComponent(v.id)}/read-caption`), { method: "POST" }));
    if (r) { v.res = r; v.caption = r.caption; picDraw(); }
  }, { cls: v.caption ? "btn sm" : "btn sm primary", disabled: v.busy });
  const put = hBtn("넣기", async () => {
    const res = await structOp(`pics/${encodeURIComponent(v.id)}/caption`, { caption: v.caption.trim() });
    if (!res || !res.made) return;
    toast("캡션을 넣었습니다 — 실행 취소로 되돌릴 수 있습니다");
    picDraw();
  }, { cls: v.caption ? "btn sm primary" : "btn sm", disabled: v.busy || !v.caption.trim() });
  foot.append(put, ask);
}

// -- 선명하게
function picDrawSharpen(body, foot) {
  const v = pic.view, b = picBlock(v.id);
  const lv = el("div", "pic-col-row");
  for (const [k, name] of [["normal", "보통"], ["strong", "강하게"]]) {
    const l = el("label", "pic-col-radio"), i = el("input");
    i.type = "radio"; i.name = "picLevel"; i.checked = v.level === k; i.onchange = () => { v.level = k; picDraw(); };
    l.append(i, el("span", null, name));
    lv.append(l);
  }
  lv.prepend(el("span", "pic-col-label", "세기"));
  body.append(lv);
  const two = el("div", "pic-two");
  const fig = (label, img) => { const f = el("figure", "pic-two-fig"); f.append(img, el("figcaption", null, label)); return f; };
  const after = new Image();
  after.className = "pic-col-img";
  after.alt = "";
  const cap = el("figcaption", null, "바꾼 뒤 …");
  const fa = el("figure", "pic-two-fig");
  fa.append(after, cap);
  two.append(fig("지금", picImg(v.id)), fa);
  body.append(two);
  const seq = pic.seq, level = v.level, media = b ? b.media : "";
  const show = (p) => { after.src = p.url; cap.textContent = p.px.length === 2 ? `바꾼 뒤 — 화소 ${p.px[0].replace("x", "×")} → ${p.px[1].replace("x", "×")}` : "바꾼 뒤"; };
  v.prev = v.prev || {};
  const key = `${level}|${media}`; // 미리보기 요청은 세기 · 그림 파일마다 하나 — 2열을 다시 그려도(그림 정보가 늦게 옴) 같은 요청을 기다린다
  if (!v.prev[key]) {
    v.prev[key] = fetch(picUrl(`${encodeURIComponent(v.id)}/sharpen.png?level=${level}`)).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}`);
      return { px: (r.headers.get("X-Pixels") || "").split(">"), url: URL.createObjectURL(await r.blob()) };
    });
  }
  v.prev[key].then((p) => { if (seq === pic.seq && after.isConnected) show(p); })
    .catch((e) => { delete v.prev[key]; if (after.isConnected) cap.textContent = `미리보기를 못 만들었습니다(${e.message})`; });
  body.append(el("p", "pic-col-hint", `표시 크기(${b ? `${b.widthMm}×${b.heightMm}mm` : "?"})는 그대로이고 새 그림 파일로 들어갑니다. 「강하게」 는 대비도 올립니다.`));
  foot.append(hBtn("바꾸기", async () => {
    const res = await structOp(`pics/${encodeURIComponent(v.id)}/sharpen`, { level: v.level });
    if (!res || !res.made) return;
    toast(`그림을 또렷하게 바꿨습니다 — 화소 ${res.made.before.join("×")} → ${res.made.after.join("×")} · 실행 취소로 되돌릴 수 있습니다`);
    picDraw();
  }, { cls: "btn sm primary", disabled: v.busy }));
}

picBind();
