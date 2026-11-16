"use strict";
// hwpx 공유의 손님 화면(spec_공유 ② §6) — 공유 포트의 /s/<공유 id> 에서만 돈다. 주인 화면의 app.js 를 읽지 않는다: 제 그리기(종이 한 장 폭의 이어진 글) · 제 편집.
// 서버(app/share_api.py guest)와의 계약: GET /doc(블록) · GET /changes(남의 변경 + 사람들 — 1.2초마다, 내가 커서를 둔 문단을 같이 알린다) ·
// PATCH /blocks/{id}(글) · POST /split · /merge(줄 나누기·합치기 — 응답 {drop, blocks} = 바뀐 최상위 블록). 바꾸는 요청에는 머리말 X-Share: 1.
// 한 문단은 한 사람(② §5): 남이 작성 중인 문단은 못 고친다(색 띠 + 이름). 차례가 어긋난 블록 바꿔 끼우기는 하지 않고 문서를 다시 읽는다(② §4).
const SID = (location.pathname.match(/^\/s\/([0-9a-f]{16})\/?$/) || [])[1] || "";
const BASE = `/s/${SID}`;
const LS = " ";                 // 문단 안 줄 바꿈(서버의 글에서) — 화면에서는 \n
const POLL = 1200, POLL_HIDDEN = 5000, SAVE_DELAY = 450;
const IDLE = 60000;                 // 커서만 두고 이만큼 아무것도 안 하면 그 문단을 놓는다(작성 중 — ② §5)
const NAME_KEY = "nfm.share.name";
const EDIT = (() => { const d = document.createElement("div"); d.contentEditable = "plaintext-only"; return d.contentEditable === "plaintext-only" ? "plaintext-only" : "true"; })();
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const paraEl = (id) => document.querySelector(`.para[data-id="${CSS.escape(id)}"]`);
const disp = (t) => (t || "").replaceAll(LS, "\n");

const S = {
  me: null, since: -1, seen: -1, epoch: "", blocks: [], byId: new Map(), nodes: new Map(), texts: {},
  timers: new Map(), chains: new Map(), failed: new Set(), inflight: 0, busy: false, cur: null,
  on: false, offline: false, pollTimer: null, queue: Promise.resolve(), people: [], act: 0,
};
const serial = (fn) => (S.queue = S.queue.then(fn, fn)); // 화면을 바꾸는 일(남의 변경 반영 · 줄 나누기/합치기 · 다시 읽기)은 한 번에 하나

// ---------------------------------------------------------------- 공통
async function api(path, opts = {}) {
  const write = opts.method && opts.method !== "GET";
  const r = await fetch(BASE + path, { credentials: "same-origin", cache: "no-store", ...opts,
    headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(write ? { "X-Share": "1" } : {}) } });
  let body = null;
  try { body = await r.json(); } catch { /* 본문 없음 */ }
  if (!r.ok) {
    const e = new Error((body && typeof body.detail === "string" && body.detail) || `${r.status} ${r.statusText}`);
    e.status = r.status; e.body = body;
    throw e;
  }
  return body;
}

let toastTimer;
function toast(msg, err = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), err ? 6000 : 3000);
}

function show(which) { // "gate" | "closed" | "doc"
  $("gate").hidden = which !== "gate";
  $("closed").hidden = which !== "closed";
  $("scroller").hidden = $("bar").hidden = which !== "doc";
}

function stop() { S.on = false; clearTimeout(S.pollTimer); for (const t of S.timers.values()) clearTimeout(t); S.timers.clear(); }
function showClosed(title, note) {
  stop();
  if (title) $("closedTitle").textContent = title;
  if (note) $("closedNote").textContent = note;
  show("closed");
}
function showGate(note) {
  stop();
  $("gateNote").textContent = note || "링크와 함께 받은 키를 넣어 주세요.";
  $("gateErr").hidden = true;
  try { if (!$("nameIn").value) $("nameIn").value = localStorage.getItem(NAME_KEY) || ""; } catch { /* 저장소 없음 */ }
  show("gate");
  ($("nameIn").value ? $("keyIn") : $("nameIn")).focus();
}
function lost(e) { // 서버가 나를 모른다(401) → 키 넣기 · 공유가 끝났다(410) → 끝. 404 는 「그 문단이 없어짐」 이라 여기서 잡지 않는다
  if (e.status === 401) { showGate("세션이 끝났거나 키가 바뀌었습니다 — 키를 다시 넣어 주세요."); return true; }
  if (e.status === 410) { showClosed(); return true; }
  return false;
}

// ---------------------------------------------------------------- 들어가기
async function start() {
  if (!SID) return showClosed("없는 링크입니다", "주소를 다시 확인해 주세요.");
  let info;
  try { info = await api("/info"); } catch { return showClosed("서버에 닿지 못했습니다", "잠시 뒤 새로 고쳐 주세요."); }
  if (!info.active) return showClosed();
  if (info.joined) return open();
  showGate();
}

let waitTimer;
function gateWait(sec) { // 잠긴 동안 「들어가기」 를 끄고 남은 초를 보인다
  const b = $("joinBtn");
  clearInterval(waitTimer);
  const tick = () => { b.disabled = sec > 0; b.textContent = sec > 0 ? `${sec}초 뒤에 다시` : "들어가기"; if (sec-- <= 0) clearInterval(waitTimer); };
  tick();
  if (sec >= 0) waitTimer = setInterval(tick, 1000);
}

async function join(ev) {
  ev.preventDefault();
  const name = $("nameIn").value.trim(), key = $("keyIn").value.trim();
  if (!name || !key) return;
  $("joinBtn").disabled = true;
  try {
    await api("/join", { method: "POST", body: JSON.stringify({ name, key }) });
    try { localStorage.setItem(NAME_KEY, name); } catch { /* 저장소 없음 */ }
    $("keyIn").value = "";
    $("joinBtn").disabled = false;
    await open();
  } catch (e) {
    $("joinBtn").disabled = false;
    if (e.status === 410) return showClosed();
    $("gateErr").textContent = e.message;
    $("gateErr").hidden = false;
    if (e.body && e.body.wait > 0) gateWait(e.body.wait);
  }
}

async function open() {
  let d;
  try { d = await api("/doc"); } catch (e) { if (!lost(e)) showClosed("문서를 열지 못했습니다", e.message); return; }
  setDoc(d);
  show("doc");
  $("scroller").scrollTop = 0;
  S.on = true;
  pollSoon(POLL);
}

async function leave() {
  await flushAll();
  try { await api("/leave", { method: "POST", body: "{}" }); } catch { /* 이미 나감 */ }
  showGate("나갔습니다 — 다시 들어오려면 키를 넣어 주세요.");
}

// ---------------------------------------------------------------- 문서 그리기
function walkParas(blocks, fn) {
  for (const b of blocks || []) {
    if (b.type === "paragraph") fn(b);
    for (const c of b.cells || []) walkParas(c.blocks, fn);
  }
}

function setDoc(d) {
  for (const t of S.timers.values()) clearTimeout(t);
  S.timers.clear(); S.failed.clear();
  Object.assign(S, { me: d.me, since: d.rev, seen: d.rev, epoch: d.epoch, blocks: d.blocks, byId: new Map(), nodes: new Map(), texts: {} });
  document.title = `${d.name} — 같이 쓰기`;
  $("docName").textContent = $("docName").title = d.name;
  $("hostName").textContent = `주인 ${d.host}`;
  const doc = $("doc"), page = (d.blocks.find((b) => b.page) || {}).page || {}, m = page.marginsMm || { l: 20, r: 20, t: 20, b: 15 };
  doc.textContent = "";
  doc.style.width = `${page.widthMm || 210}mm`;
  doc.style.padding = `${m.t}mm ${m.r}mm ${m.b}mm ${m.l}mm`;
  for (const b of d.blocks) { const n = renderBlock(b); S.nodes.set(b.id, n); doc.append(n); }
  walkParas(d.blocks, index);
  drawPeople(d.people || []);
  saveState();
}
function index(b) { S.byId.set(b.id, b); S.texts[b.id] = b.text || ""; }

function renderList(box, blocks) { for (const b of blocks || []) box.append(renderBlock(b)); }
function renderBlock(b) {
  if (b.type === "paragraph") return renderPara(b);
  if (b.type === "table") return renderTable(b);
  if (b.type === "image") return renderImage(b);
  return el("div");
}

const fontOf = (name) => `"${String(name).replace(/"/g, "")}", "Malgun Gothic", "맑은 고딕", sans-serif`;
function paraLook(p, f) {
  const st = p.style, left = f.indentLeftMm || 0, first = f.firstLineMm || 0;
  if (f.sizePt) st.fontSize = `${f.sizePt}pt`;
  if (f.font) st.fontFamily = fontOf(f.font);
  if (f.bold) st.fontWeight = "700";
  if (f.italic) st.fontStyle = "italic";
  if (f.underline) st.textDecoration = "underline";
  if (f.color && f.color !== "#000000") st.color = f.color;
  st.textAlign = { justify: "justify", distribute: "justify", center: "center", right: "right" }[f.align] || "left";
  if (f.lineSpacingPct) st.lineHeight = String(Math.max(0.8, f.lineSpacingPct / 100));
  if (left || first < 0) st.paddingLeft = `${left + (first < 0 ? -first : 0)}mm`; // 내어쓰기(음수) = 첫 줄은 왼쪽 여백에, 나머지 줄을 더 들인다
  if (first) st.textIndent = `${first}mm`;
  if (f.indentRightMm) st.paddingRight = `${f.indentRightMm}mm`;
  if (f.spaceBeforePt) st.paddingTop = `${f.spaceBeforePt}pt`;
  if (f.spaceAfterPt) st.paddingBottom = `${f.spaceAfterPt}pt`;
  if (f.wordBreak !== "word") p.classList.add("char-break");
}
function charLook(s, r, f) {
  const st = s.style, size = r.sizePt || f.sizePt || 10;
  if (r.script) { st.fontSize = `${(size * 0.64).toFixed(2)}pt`; st.position = "relative"; st.top = `${(r.script === "sup" ? -size * 0.44 : size * 0.15).toFixed(2)}pt`; }
  else if (r.sizePt && r.sizePt !== f.sizePt) st.fontSize = `${r.sizePt}pt`;
  if (r.font && r.font !== f.font) st.fontFamily = fontOf(r.font);
  if (!!r.bold !== !!f.bold) st.fontWeight = r.bold ? "700" : "400";
  if (!!r.italic !== !!f.italic) st.fontStyle = r.italic ? "italic" : "normal";
  if (!!r.underline !== !!f.underline) st.textDecoration = r.underline ? "underline" : "none";
  if ((r.color || "#000000") !== (f.color || "#000000")) st.color = r.color || "#000000";
}

function renderPara(b) {
  const p = el("div", "para");
  p.dataset.id = b.id;
  p.contentEditable = EDIT;
  p.spellcheck = false;
  p.setAttribute("role", "textbox");
  p.setAttribute("aria-multiline", "true");
  p.setAttribute("aria-label", b.captionOf ? "캡션 문단" : "문단");
  paraLook(p, b.format || {});
  if (b.label) p.dataset.label = b.label;
  fillText(p, b);
  return p;
}
function fillText(p, b, text = null) { // text 를 주면 그 글 한 덩이(남이 고친 글 — 문단 안 글자 모양은 한 가지로 보인다: ② §4)
  const f = b.format || {};
  p.textContent = "";
  for (const r of text == null && b.runs ? b.runs : [{ text: text == null ? b.text : text, format: null }]) {
    const s = el("span", null, disp(r.text));
    if (r.format) charLook(s, r.format, f);
    p.append(s);
  }
}

const BORDER = { SOLID: "solid", DASH: "dashed", DOT: "dotted", DASH_DOT: "dashed", DASH_DOT_DOT: "dashed", LONG_DASH: "dashed", CIRCLE: "dotted",
  DOUBLE_SLIM: "double", SLIM_THICK: "double", THICK_SLIM: "double", SLIM_THICK_SLIM: "double" };

function colWidths(b, n, nR) { // 열 폭 = 칸 폭을 아는 경계부터 더해 만든 열 경계의 차(병합 칸이 많아도 맞는다) — 못 정한 열은 1칸짜리 칸 폭 · 나머지는 평균
  const occ = new Map(), bound = new Map([[0, 0]]);
  for (const c of b.cells) for (let r = c.row; r < c.row + c.rowSpan; r++) for (let k = c.col; k < c.col + c.colSpan; k++) occ.set(r * n + k, c);
  for (let pass = 0, grew = true; grew && pass <= n; pass++) {
    grew = false;
    for (let r = 0; r < nR; r++) for (let k = 0; k < n;) {
      const c = occ.get(r * n + k), end = c ? Math.min(n, c.col + c.colSpan) : 0;
      if (!c || end <= k) break;
      if (c.widthMm) {
        if (bound.has(c.col) && !bound.has(end)) { bound.set(end, bound.get(c.col) + c.widthMm); grew = true; }
        else if (bound.has(end) && !bound.has(c.col)) { bound.set(c.col, bound.get(end) - c.widthMm); grew = true; }
      }
      k = end;
    }
  }
  const w = Array(n).fill(null);
  for (let k = 0; k < n; k++) if (bound.has(k) && bound.has(k + 1)) w[k] = Math.max(0.5, bound.get(k + 1) - bound.get(k));
  for (const c of b.cells) if (c.colSpan === 1 && c.widthMm && w[c.col] == null) w[c.col] = c.widthMm;
  const known = w.filter((x) => x != null), avg = known.length ? known.reduce((a, x) => a + x, 0) / known.length : 20;
  return w.map((x) => x ?? avg);
}

function renderTable(b) {
  const t = el("table", `tbl ${b.align || ""}${b.inlineRow ? " inline" : ""}`), cells = (b.cells || []).map((c) => ({ rowSpan: 1, colSpan: 1, ...c }));
  t.dataset.tbl = b.id;
  const nC = b.nCols || Math.max(1, ...cells.map((c) => c.col + c.colSpan)), nR = b.nRows || Math.max(1, ...cells.map((c) => c.row + c.rowSpan));
  const widths = colWidths({ cells }, nC, nR), cg = el("colgroup"), body = el("tbody"), rows = Array.from({ length: nR }, () => el("tr")), lines = b.borderFills || {};
  for (const w of widths) { const col = el("col"); col.style.width = `${w}mm`; cg.append(col); }
  t.style.width = `${widths.reduce((a, x) => a + x, 0)}mm`;
  for (const c of [...cells].sort((a, z) => a.row - z.row || a.col - z.col)) {
    const td = el("td", c.valign === "top" ? "top" : c.valign === "bottom" ? "bottom" : ""), m = c.marginsMm || { t: 0.5, r: 1.8, b: 0.5, l: 1.8 }, ln = lines[c.bf] || {};
    if (c.rowSpan > 1) td.rowSpan = c.rowSpan;
    if (c.colSpan > 1) td.colSpan = c.colSpan;
    td.style.padding = `${m.t}mm ${m.r}mm ${m.b}mm ${m.l}mm`;
    if (c.rowSpan === 1 && c.heightMm) td.style.height = `${c.heightMm}mm`;
    if (c.fill) td.style.background = c.fill;
    for (const [k, side] of [["t", "Top"], ["r", "Right"], ["b", "Bottom"], ["l", "Left"]]) {
      const x = ln[k];
      td.style[`border${side}`] = x ? `${Math.max(0.1, x.widthMm)}mm ${BORDER[x.type] || "solid"} ${x.color}` : "none";
    }
    renderList(td, c.blocks);
    (rows[c.row] || rows[rows.length - 1]).append(td);
  }
  rows.forEach((r) => body.append(r));
  t.append(cg, body);
  return t;
}

function renderImage(b) {
  const w = b.widthMm || 30, h = b.heightMm || 20, ext = (b.media || "").split(".").pop().toLowerCase();
  const ph = () => { const d = el("div", `img img-ph ${b.align || ""}`, "그림"); d.style.width = `${w}mm`; d.style.height = `${h}mm`; return d; };
  if (!b.media || !["png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"].includes(ext)) return ph();
  const img = new Image();
  img.className = `img ${b.align || ""}`;
  img.alt = "";
  img.loading = "lazy";
  img.style.width = `${w}mm`;
  img.style.height = `${h}mm`;
  img.onerror = () => img.replaceWith(ph());
  img.src = `${BASE}/media?name=${encodeURIComponent(b.media)}`;
  return img;
}

// ---------------------------------------------------------------- 글 읽기 · 커서
function readText(p) {
  let s = "";
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === Node.TEXT_NODE) s += c.data;
      else if (c.nodeName === "BR") s += "\n";
      else { if ((c.nodeName === "DIV" || c.nodeName === "P") && s && !s.endsWith("\n")) s += "\n"; walk(c); }
    }
  };
  walk(p);
  if (p.lastChild && p.lastChild.nodeName === "BR") s = s.replace(/\n$/, ""); // 빈 편집 상자에 브라우저가 남기는 끝 <br>
  return s.replace(/\r/g, "").replace(/\n/g, LS);
}

function offsetAt(p, node, off) { // 문단 안의 DOM 자리 → 글에서 몇째 글자
  const r = document.createRange(), d = document.createElement("div");
  r.selectNodeContents(p);
  try { r.setEnd(node, off); } catch { return 0; }
  d.append(r.cloneContents());
  let n = 0;
  const walk = (x) => { for (const c of x.childNodes) { if (c.nodeType === Node.TEXT_NODE) n += c.data.length; else if (c.nodeName === "BR") n += 1; else walk(c); } };
  walk(d);
  return n;
}
function selOffsets(p) {
  const sel = getSelection();
  if (!sel.rangeCount) return null;
  const r = sel.getRangeAt(0);
  if (!p.contains(r.startContainer) || !p.contains(r.endContainer)) return null;
  return { start: offsetAt(p, r.startContainer, r.startOffset), end: offsetAt(p, r.endContainer, r.endOffset) };
}
function setCaret(p, off) {
  const r = document.createRange();
  let left = Math.max(0, off), done = false;
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (done) return;
      if (c.nodeType === Node.TEXT_NODE) { if (left <= c.data.length) { r.setStart(c, left); done = true; return; } left -= c.data.length; }
      else if (c.nodeName === "BR") { if (left === 0) { r.setStartBefore(c); done = true; return; } left -= 1; }
      else walk(c);
    }
  };
  walk(p);
  if (!done) r.selectNodeContents(p);
  r.collapse(done);
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(r);
}
function focusAt(f) {
  const p = f && paraEl(f.id);
  if (!p || p.classList.contains("held")) return;
  p.focus({ preventScroll: true });
  setCaret(p, f.offset || 0);
  p.scrollIntoView({ block: "nearest" });
}
const focused = () => { const a = document.activeElement; return a && a.classList && a.classList.contains("para") ? a : null; };

// ---------------------------------------------------------------- 글 반영
function saveState() {
  const s = $("saveState");
  const [cls, text, title] = S.offline ? ["err", "연결 끊김 — 다시 잇는 중…", ""]
    : S.inflight || S.timers.size ? ["busy", "반영 중…", ""]
      : S.failed.size ? ["err", `반영 실패 ${S.failed.size}개 — 눌러서 다시`, "붉게 표시된 문단을 서버에 다시 보냅니다"]
        : ["ok", "모두 반영됨", ""];
  s.className = "save " + cls;
  s.textContent = text;
  s.title = title;
}

function schedule(p) {
  const id = p.dataset.id;
  clearTimeout(S.timers.get(id));
  S.timers.set(id, setTimeout(() => save(p), SAVE_DELAY));
  saveState();
}

function save(p) {
  const id = p.dataset.id;
  clearTimeout(S.timers.get(id));
  S.timers.delete(id);
  const next = (S.chains.get(id) || Promise.resolve()).then(async () => {
    const now = paraEl(id) || p; // 그 사이 블록이 다시 그려졌으면 새 요소
    if (!S.on || !(id in S.texts)) return;
    const text = readText(now);
    if (text === S.texts[id] && !S.failed.has(id)) { saveState(); return; }
    S.inflight += 1;
    now.classList.add("saving");
    try {
      const r = await api(`/blocks/${id}`, { method: "PATCH", body: JSON.stringify({ text }) });
      S.texts[id] = r.text;
      S.seen = Math.max(S.seen, r.rev || 0);
      S.failed.delete(id);
      now.classList.remove("error");
      now.removeAttribute("title");
    } catch (e) {
      if (lost(e)) return;
      if (e.status === 409) { // 남이 먼저 잡은 문단 — 내가 친 글을 걷고 서버의 글로(그 사람의 글은 곧 읽어 온다)
        const b = S.byId.get(id);
        if (document.activeElement === now) now.blur();
        if (b) fillText(now, b, S.texts[id]);
        S.failed.delete(id);
        toast(`${e.message} — 방금 친 글은 반영되지 않았습니다`, true);
      } else if (e.status === 404) { // 그 사이 남이 그 문단을 없앴다(합치기 · 주인의 실행 취소) — 문서를 다시 읽는다
        S.failed.delete(id);
        toast("쓰던 문단이 없어졌습니다 — 문서를 다시 읽습니다", true);
        serial(reload);
      } else {
        S.failed.add(id);
        now.classList.add("error");
        now.title = `반영 실패: ${e.message}`;
        toast(`문단을 반영하지 못했습니다: ${e.message}`, true);
      }
    } finally {
      S.inflight -= 1;
      now.classList.remove("saving");
      saveState();
    }
  });
  S.chains.set(id, next.catch(() => {}));
  return next;
}

async function flushAll() {
  for (const id of [...S.timers.keys()]) { const p = paraEl(id); if (p) save(p); else { clearTimeout(S.timers.get(id)); S.timers.delete(id); } }
  await Promise.all([...S.chains.values()]);
}

function retryFailed() { for (const id of [...S.failed]) { const p = paraEl(id); if (p) save(p); else S.failed.delete(id); } }

// ---------------------------------------------------------------- 줄 나누기 · 합치기 · 블록 바꿔 끼우기
function setBusy(on) { S.busy = on; $("doc").classList.toggle("busy", on); }

function structOp(path, body) {
  if (S.busy || !S.on) return;
  setBusy(true); // 응답이 올 때까지 입력을 막는다 — 곧 바뀔 문단에 친 글을 잃지 않게
  serial(async () => {
    try {
      await flushAll();
      if (S.failed.size) { toast("반영하지 못한 문단이 있습니다 — 위 줄의 「반영 실패」 를 눌러 먼저 다시 보내 주세요", true); return; }
      const r = await api(path, { method: "POST", body: JSON.stringify(body) });
      S.seen = Math.max(S.seen, r.rev || 0);
      if (r.reload || !applyTops(r.drop, r.blocks)) await reload();
      marks();
      focusAt(r.focus);
    } catch (e) {
      if (lost(e)) return;
      toast(e.status === 404 ? "그 문단이 없어졌습니다 — 문서를 다시 읽습니다" : e.message, true);
      if (e.status === 404) { try { await reload(); } catch (x) { lost(x); } }
    } finally { setBusy(false); }
  });
}

function applyTops(drop, blocks) { // 바뀐 최상위 블록으로 그 자리만 바꿔 끼운다 → false = 자리를 못 찾음(부르는 쪽이 문서를 다시 읽는다)
  const ids = new Set([...drop, ...blocks.map((b) => b.id)]), at = [];
  S.blocks.forEach((b, i) => { if (ids.has(b.id)) at.push(i); });
  if (!at.length) return false;
  const lo = at[0], old = S.blocks.slice(lo, at[at.length - 1] + 1);
  if (old.some((b) => !ids.has(b.id))) return false; // 사이에 낀 블록이 응답에 없다 — 잃지 않게 통째로 다시 읽는다
  const keep = focusKeep(), last = S.nodes.get(old[old.length - 1].id), ref = last ? last.nextSibling : null, doc = $("doc"), gone = new Set();
  walkParas(old, (b) => gone.add(b.id));
  for (const b of old) { const n = S.nodes.get(b.id); if (n) n.remove(); S.nodes.delete(b.id); }
  S.blocks.splice(lo, old.length, ...blocks);
  for (const b of blocks) { const n = renderBlock(b); S.nodes.set(b.id, n); doc.insertBefore(n, ref); }
  walkParas(blocks, (b) => { index(b); gone.delete(b.id); });
  for (const id of gone) { S.byId.delete(id); delete S.texts[id]; S.failed.delete(id); clearTimeout(S.timers.get(id)); S.timers.delete(id); }
  focusBack(keep);
  return true;
}

function focusKeep() { const p = focused(); return p ? { id: p.dataset.id, sel: selOffsets(p) } : null; }
function focusBack(keep) {
  const p = keep && !focused() && paraEl(keep.id);
  if (!p || p.classList.contains("held")) return;
  p.focus({ preventScroll: true });
  if (keep.sel) setCaret(p, keep.sel.start);
}

async function reload() { // 문서를 통째로 다시 읽어 그린다 — 보던 자리·커서는 그대로
  await flushAll();
  const keep = focusKeep(), top = $("scroller").scrollTop;
  const d = await api("/doc");
  setDoc(d);
  $("scroller").scrollTop = top;
  focusBack(keep);
}

// ---------------------------------------------------------------- 남의 변경 · 사람들
function pollSoon(ms) { clearTimeout(S.pollTimer); if (S.on) S.pollTimer = setTimeout(() => serial(poll), ms); }

async function poll() {
  if (!S.on) return;
  try {
    const cur = S.cur && Date.now() - S.act < IDLE ? S.cur : ""; // 커서만 두고 오래 쉬면 놓는다 — 다시 치거나 누르면 다시 잡는다
    const r = await api(`/changes?since=${S.since}&epoch=${encodeURIComponent(S.epoch)}&block=${encodeURIComponent(cur)}`);
    S.offline = false;
    if (r.reload) await reload();
    else {
      for (const it of r.items || []) if (await applyItem(it)) break; // 다시 읽었으면 남은 것은 그 안에 이미 있다
      S.since = Math.max(S.since, r.rev);
    }
    S.people = r.people || [];
    drawPeople(S.people);
    marks();
    if (r.denied && cur) { // 내가 잡으려던 문단을 남이 먼저 잡았다
      const p = paraEl(S.cur);
      if (p && document.activeElement === p) p.blur();
      toast(`${r.denied.name} 님이 작성 중인 문단입니다`);
    }
  } catch (e) {
    if (lost(e)) return;
    S.offline = true;
  }
  saveState();
  pollSoon(document.hidden ? POLL_HIDDEN : POLL);
}

async function applyItem(it) { // 남의 편집 하나를 화면에 → true = 문서를 통째로 다시 읽었다
  // 서버가 이미 가려 준다(share.Feed.read — ② §4): 내가 그 뒤 차례에 고친 문단에 닿는 옛 편집은 오지 않는다. 여기서는 **아직 못 보낸 내 글**만 본다.
  if (it.t === "text") {
    const b = S.byId.get(it.id), p = paraEl(it.id);
    if (!b) return false;
    if (S.timers.has(it.id) || (p && document.activeElement === p && readText(p) !== S.texts[it.id])) return false; // 내가 치는 중인 문단 — 내 글을 곧 보낸다
    S.texts[it.id] = it.text;
    b.text = it.text; b.runs = null;
    if (p) { const keep = focusKeep(); fillText(p, b, it.text); if (keep && keep.id === it.id && keep.sel) setCaret(p, keep.sel.start); }
    return false;
  }
  if (it.t !== "tops") return false;
  const mine = new Set([...S.timers.keys(), ...S.failed]); // 아직 못 보낸 내 글이 있는 문단
  await flushAll(); // 곧 바뀔 블록에 치던 글을 먼저 보낸다
  let stale = false; // 그 문단이 이 블록 안에 있으면 옛 블록으로 덮지 않고 다시 읽는다
  if (mine.size) walkParas(it.blocks, (b) => { if (mine.has(b.id)) stale = true; });
  if (!stale && applyTops(it.drop, it.blocks)) { S.seen = Math.max(S.seen, it.rev); return false; }
  await reload();
  return true;
}

function drawPeople(list) {
  const box = $("people");
  box.textContent = "";
  for (const p of list) {
    const me = S.me && p.id === S.me.id, chip = el("span", "who" + (me ? " me" : "") + (p.block && !me ? " busy" : ""));
    const dot = el("i");
    chip.style.setProperty("--c", p.color);
    chip.setAttribute("role", "listitem");
    chip.append(dot, `${p.name}${p.host ? " · 주인" : ""}${me ? " (나)" : ""}`);
    if (p.block && !me) { chip.title = "작성 중인 문단으로"; chip.onclick = () => { const x = paraEl(p.block); if (x) x.scrollIntoView({ block: "center", behavior: "smooth" }); }; }
    box.append(chip);
  }
}

function marks() { // 남이 작성 중인 문단 — 색 띠 + 이름, 못 고치게
  const held = new Map();
  for (const p of S.people) if (p.block && !(S.me && p.id === S.me.id)) held.set(p.block, p);
  for (const p of document.querySelectorAll(".para.held")) {
    if (held.has(p.dataset.id)) continue;
    p.classList.remove("held");
    delete p.dataset.who;
    p.style.removeProperty("--who");
    p.contentEditable = EDIT;
  }
  for (const [id, who] of held) {
    const p = paraEl(id);
    if (!p) continue;
    p.classList.add("held");
    p.dataset.who = who.name;
    p.style.setProperty("--who", who.color);
    p.contentEditable = "false";
    if (document.activeElement === p) p.blur();
  }
}

// ---------------------------------------------------------------- 입력
const paraOf = (t) => (t && t.closest ? t.closest(".para") : null);
const neighbor = (p, dir) => { const n = dir < 0 ? p.previousElementSibling : p.nextElementSibling; return n && n.classList.contains("para") && !n.classList.contains("held") ? n : null; };

function bind() {
  const doc = $("doc");
  doc.addEventListener("beforeinput", (e) => {
    const p = paraOf(e.target);
    if (!p) return;
    if (S.busy) { e.preventDefault(); return; }
    if (e.inputType === "insertParagraph" && !e.isComposing) { e.preventDefault(); split(p); } // 화면 자판의 Enter(키 이벤트가 안 오는 곳)
  });
  doc.addEventListener("input", (e) => { const p = paraOf(e.target); if (p) { S.act = Date.now(); schedule(p); } });
  doc.addEventListener("pointerdown", () => { S.act = Date.now(); });
  doc.addEventListener("keydown", (e) => {
    const p = paraOf(e.target);
    if (!p) return;
    S.act = Date.now();
    const composing = e.isComposing || e.keyCode === 229;
    if (S.busy) { if (!e.ctrlKey && !e.metaKey && !e.key.startsWith("Arrow")) e.preventDefault(); return; }
    if (e.key === "Enter") { // 주인 화면과 같은 법(app.js bindEditing): 한글 조합 중 Enter 는 조합만 확정 — 한글 IME 는 조합이 끝난 뒤 Enter 를 한 번 더 보낸다
      e.preventDefault();
      if (composing || e.ctrlKey || e.altKey || e.metaKey) return;
      if (e.shiftKey) document.execCommand("insertText", false, "\n"); else split(p);
      return;
    }
    if (composing) return; // 조합 중의 다른 키는 넘긴다
    if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) { e.preventDefault(); document.execCommand("insertText", false, "\t"); return; }
    if (e.key !== "Backspace" && e.key !== "Delete") return;
    const o = selOffsets(p);
    if (!o || o.start !== o.end) return;
    if (e.key === "Backspace" && o.start === 0 && neighbor(p, -1)) { e.preventDefault(); structOp("/merge", { id: p.dataset.id, dir: "prev" }); }
    else if (e.key === "Delete" && o.start >= readText(p).length && neighbor(p, +1)) { e.preventDefault(); structOp("/merge", { id: p.dataset.id, dir: "next" }); }
  });
  doc.addEventListener("paste", (e) => { // 글만 붙인다
    const p = paraOf(e.target);
    if (!p) return;
    e.preventDefault();
    const text = ((e.clipboardData && e.clipboardData.getData("text/plain")) || "").replace(/\r/g, "");
    if (text && !S.busy) document.execCommand("insertText", false, text);
  });
  doc.addEventListener("drop", (e) => e.preventDefault());
  doc.addEventListener("focusin", (e) => { const p = paraOf(e.target); if (p && S.cur !== p.dataset.id) { S.cur = p.dataset.id; S.act = Date.now(); pollSoon(60); } }); // 곧바로 알려 그 문단을 잡는다
  doc.addEventListener("focusout", () => setTimeout(() => { if (!focused() && S.cur) { S.cur = null; pollSoon(200); } }, 0));
  $("joinForm").addEventListener("submit", join);
  $("leaveBtn").addEventListener("click", leave);
  $("saveState").addEventListener("click", () => { if (S.failed.size) retryFailed(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollSoon(100); });
  window.addEventListener("beforeunload", (e) => { if (S.on && (S.timers.size || S.inflight || S.failed.size)) { e.preventDefault(); e.returnValue = ""; } });
}

function split(p) {
  let o = selOffsets(p);
  if (!o) return;
  if (o.start !== o.end) { document.execCommand("delete"); schedule(p); o = selOffsets(p); if (!o) return; } // 고른 글을 지우고 그 자리에서 나눈다
  structOp("/split", { id: p.dataset.id, offset: o.start });
}

bind();
start();
