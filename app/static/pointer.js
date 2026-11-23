"use strict";
/* 포인터 — 같은 문서를 보는 다른 화면에 내 마우스 자리와 「클릭」 을 보인다(spec_포인터 ② §1~§3 · design.md §26). app.js · peer_follow.js · share.js 다음에 읽는다.
   하는 일: ① 상단 바 「포인터」 단추(문서를 열었을 때만 · 눌림 = 켬 · 이 브라우저에 기억 nfm.pointer — 기본 끔) ② 켜면 문서 위에서 움직이는 내 마우스 자리를 WebSocket 으로 보낸다(초당 16번 안)
   ③ 같은 문서를 연 화면은 단추를 켜지 않아도 남의 포인터(색 화살표 + 이름표)를 본다 — 내 포인터는 내 화면에 그리지 않는다 ④ 켠 채로 문서를 누르면 그 자리에 「클릭」 표시(남의 화면 + 내 화면에 짧게).
   **누른 것은 원래대로 작동한다** — 이 파일은 preventDefault 하지 않고(단추의 오른쪽 누름 메뉴만 뺀다) 듣기만 한다(passive).
   ⑤ 단추를 오른쪽 단추로 누르면 떠 있는 작은 창(모달 아님 — ✕/Esc/바깥 누름): 내 이름 · 같이 보는 화면 · 켜기/끄기.
   자리는 화면 좌표가 아니라 **문서 안의 자리**로 오간다(창 크기 · 확대 · 스크롤이 화면마다 다르다): 포인터 아래의 가장 안쪽 블록(#doc 안의 [data-id] · td[data-cell] · table.tbl[data-tbl] — peer_follow.js followIds · followShow 와 같은 표식)
   안의 비율, 블록이 없으면 그 쪽(#doc .sheet 의 몇째) 안의 비율. 받는 쪽은 같은 요소를 찾아 그 비율 자리에 그리고, 못 찾으면 그리지 않는다(문서 창의 위 · 아래로 벗어나 있으면 가장자리에 「↑ 이름」 · 「↓ 이름」).
   서버 = app/pointer_api.py(WebSocket /api/docs/{id}/pointer — 방 = 문서 id · 저장 없음 · 문서를 안 바꾼다). 둘째 면 화면(PEEK)은 단추도 연결도 없다.
   app.js 에서 기대는 것(이름 · 뜻이 바뀌면 여기도): state.id(지금 문서 — 닫으면 null) · $ · el · toast · PEEK · 문서의 꼴(#scroller 가 스크롤 상자 · #doc 아래 .sheet 쪽 상자 · 블록의 data-id · 표 칸의 data-cell · 표의 data-tbl) ·
   상단 바의 #downloadBtn, share.js 의 #shareBtn(있으면 그 앞에 단추를 끼운다 — 없으면 #downloadBtn 앞). */
const PTR_ON = "nfm.pointer", PTR_NAME = "nfm.pointerName", PTR_COLOR = "nfm.pointerColor"; // 이 브라우저에 기억: 켬/끔 · 내 이름 · 지난번에 받은 색(같은 색을 다시 바란다)
const PTR_SEND = 60;        // 움직임을 보내는 가장 짧은 사이(ms) — 초당 16번쯤
const PTR_WATCH = 500;      // 문서가 바뀌었나 · 남의 포인터 자리 다시 맞추기(글을 고쳐 줄이 밀린 것)
const PTR_RETRY = 3000, PTR_RETRY_MAX = 30000, PTR_FULL_RETRY = 60000; // 끊기면 다시 잇기(못 붙을수록 길게) · 방이 찼으면 1분 뒤
const PTR_CLICK = 1300, PTR_CLICK_MINE = 700; // 「클릭」 표시가 보이는 동안(남의 것 · 내 것)
const PTR_NAME_MAX = 16;
const PTR_SEL = { // 자리의 기준 → 그 요소를 찾는 선택자(쪽에 걸쳐 나뉜 것은 여럿 — 몇째 조각인지 n)
  p: (q) => `#doc [data-id="${q}"]`,
  c: (q) => `#doc td[data-cell="${q}"]`,
  t: (q) => `#doc table.tbl[data-tbl="${q}"]`,
};
const ptrGet = (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } };
const ptrPut = (k, v) => { try { if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch { /* 기억만 안 함 */ } };
const ptrName = (s) => String(s || "").replace(/\s+/g, " ").trim().slice(0, PTR_NAME_MAX);
const ptrColor = (c) => (/^#[0-9a-f]{6}$/i.test(c || "") ? c : "#2563eb"); // 서버가 준 색만 CSS 에(꼴이 다르면 기본 파랑)
const ptrUnit = (v) => Math.round(Math.min(1, Math.max(0, v)) * 10000) / 10000;
const ptr = { on: ptrGet(PTR_ON) === "on", name: ptrName(ptrGet(PTR_NAME)), doc: null, ws: null, me: null, peers: new Map(), retry: null, fails: 0, full: false,
  x: 0, y: 0, inside: false, dirty: false, shown: false, sent: "", sentAt: 0, timer: null, raf: 0, still: false, layer: null, pop: null };
// me = 서버가 정해 준 나 {id, name, color} · peers = 같은 문서를 보는 다른 화면 {id, name, color, at(지금 자리 | null = 포인터 안 보임), host(그 자리의 요소 — 찾아 둔 것), cur(그린 포인터)}
// x·y·inside = 내 마우스의 마지막 화면 좌표 · 문서 창 안인가 · shown = 남의 화면에 내 포인터가 보이는 중 · sent = 마지막에 보낸 자리(같으면 다시 안 보낸다)
const ptrLive = () => !!(ptr.ws && ptr.ws.readyState === 1 && ptr.me); // 붙었고 서버의 첫 답(hi)을 받았다
const ptrOthers = () => ptr.peers.size;

// ---------------------------------------------------------------- 연결
function ptrUrl(doc) { return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/docs/${encodeURIComponent(doc)}/pointer`; }

function ptrOpen() {
  clearTimeout(ptr.retry);
  const doc = ptr.doc;
  if (!doc || ptr.ws) return;
  let ws;
  try { ws = new WebSocket(ptrUrl(doc)); } catch { ptrRetry(); return; }
  ptr.ws = ws;
  ws.onopen = () => { if (ptr.ws === ws) ws.send(JSON.stringify({ t: "hello", name: ptr.name, color: ptrGet(PTR_COLOR) })); };
  ws.onmessage = (e) => { if (ptr.ws === ws && typeof e.data === "string") ptrGot(e.data); };
  ws.onclose = () => {
    if (ptr.ws !== ws) return; // 내가 닫은 옛 연결
    if (!ptr.me) ptr.fails += 1; // 첫 답도 못 받고 끊김 — 다음은 더 있다가
    ptr.ws = null; ptr.me = null; ptr.shown = false; ptr.sent = "";
    ptrPeersClear();
    ptrBtnDraw();
    ptrPopDraw();
    if (ptr.doc) ptrRetry();
  };
}

function ptrRetry() {
  clearTimeout(ptr.retry);
  const wait = ptr.full ? PTR_FULL_RETRY : Math.min(PTR_RETRY_MAX, PTR_RETRY * 2 ** Math.min(ptr.fails, 4));
  ptr.retry = setTimeout(ptrOpen, wait);
}

function ptrShut() { // 연결을 닫고 남의 포인터를 걷는다 — 문서를 닫았다 · 바꿨다
  clearTimeout(ptr.retry);
  clearTimeout(ptr.timer);
  ptr.timer = null;
  const ws = ptr.ws;
  ptr.ws = null; ptr.me = null; ptr.fails = 0; ptr.full = false; ptr.shown = false; ptr.sent = ""; ptr.inside = false; ptr.dirty = false;
  if (ws) { try { ws.close(); } catch { /* 이미 닫힘 */ } }
  ptrPeersClear();
}

function ptrSay(m) { if (ptrLive()) { try { ptr.ws.send(JSON.stringify(m)); } catch { /* 닫히는 중 — onclose 가 다시 잇는다 */ } } }

function ptrGot(raw) {
  let m;
  try { m = JSON.parse(raw); } catch { return; }
  if (!m || typeof m !== "object") return;
  if (m.t === "hi") {
    ptr.me = { id: String(m.id), name: String(m.name || ""), color: ptrColor(m.color) };
    ptr.fails = 0; ptr.full = false; ptr.shown = false; ptr.sent = "";
    ptrPut(PTR_COLOR, ptr.me.color);
    ptrPeersClear();
    for (const p of Array.isArray(m.peers) ? m.peers : []) ptrPeerSet(p);
    if (ptr.on && ptr.inside) { ptr.dirty = true; ptrSendSoon(); } // 다시 이은 뒤 — 지금 자리를 다시 알린다
  } else if (m.t === "full") ptr.full = true;
  else if (m.t === "join") ptrPeerSet(m);
  else if (m.t === "leave") ptrPeerDrop(String(m.id));
  else if (m.t === "name") {
    if (ptr.me && m.id === ptr.me.id) ptr.me.name = String(m.name || "");
    else { const p = ptr.peers.get(String(m.id)); if (p) { p.name = String(m.name || ""); if (p.cur) p.cur.querySelector(".ptr-name").textContent = p.name; } }
  } else if (m.t === "move" || m.t === "click") {
    const p = ptr.peers.get(String(m.id)), at = ptrAtIn(m);
    if (!p || !at) return;
    if (!p.at || p.at.k !== at.k || p.at.a !== at.a || p.at.n !== at.n) p.host = null; // 다른 요소로 옮겨 갔다 — 다시 찾는다
    p.at = at;
    if (m.t === "click") { const pt = ptrSeen(ptrPoint(p)); if (pt) ptrClickShow(pt.x, pt.y, p.color, false); }
    ptrDrawSoon(false);
    return; // 단추 · 창은 그대로
  } else if (m.t === "off") {
    const p = ptr.peers.get(String(m.id));
    if (p) { p.at = null; p.host = null; ptrDrawSoon(false); }
    return;
  } else return;
  ptrBtnDraw();
  ptrPopDraw();
  ptrDrawSoon(false);
}

function ptrAtIn(m) { // 서버가 준 자리 → 화면이 쓰는 꼴 | null(모르는 꼴 — 그리지 않는다)
  const sheet = m.k === "s";
  if (!(sheet || Object.hasOwn(PTR_SEL, m.k)) || (sheet ? !Number.isInteger(m.a) : typeof m.a !== "string") || !Number.isFinite(m.x) || !Number.isFinite(m.y)) return null;
  return { k: m.k, a: m.a, n: Number.isInteger(m.n) ? m.n : 0, x: ptrUnit(m.x), y: ptrUnit(m.y) };
}

// ---------------------------------------------------------------- 같이 보는 화면(남)
function ptrPeerSet(c) { // 들어옴 · 첫 답의 목록 — {id, name, color, at?}
  if (!c || c.id == null || (ptr.me && c.id === ptr.me.id)) return;
  const id = String(c.id), old = ptr.peers.get(id);
  if (old && old.cur) old.cur.remove();
  ptr.peers.set(id, { id, name: String(c.name || ""), color: ptrColor(c.color), at: c.at && typeof c.at === "object" ? ptrAtIn(c.at) : null, host: null, cur: null });
}
function ptrPeerDrop(id) { const p = ptr.peers.get(id); if (p && p.cur) p.cur.remove(); ptr.peers.delete(id); }
function ptrPeersClear() { for (const p of ptr.peers.values()) if (p.cur) p.cur.remove(); ptr.peers.clear(); }

// ---------------------------------------------------------------- 자리 — 화면 좌표 ↔ 문서 안의 자리
function ptrAt(x, y) { // 화면 좌표 → 문서 안의 자리 {k, a, n, x, y} | null(문서의 쪽 밖)
  const doc = $("doc"), hit = document.elementFromPoint(x, y);
  if (!hit || hit === doc || !doc.contains(hit)) return null;
  for (let n = hit; n && n !== doc; n = n.parentElement) { // 안 → 밖: 처음 만나는 블록 · 칸 · 표
    const d = n.dataset || {};
    const k = d.id ? "p" : d.cell && n.tagName === "TD" ? "c" : d.tbl && n.matches("table.tbl") ? "t" : "";
    if (!k) continue;
    const a = k === "p" ? d.id : k === "c" ? d.cell : d.tbl;
    if (a.length > 80 || /\s/.test(a)) continue; // 서버가 받는 꼴 밖(pointer_api AT_OK) — 바깥 요소로
    const r = n.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const i = [...document.querySelectorAll(PTR_SEL[k](CSS.escape(a)))].indexOf(n);
    if (i < 0) continue;
    return { k, a, n: i, x: ptrUnit((x - r.left) / r.width), y: ptrUnit((y - r.top) / r.height) };
  }
  const sheet = hit.closest(".sheet"), i = sheet ? [...document.querySelectorAll("#doc > .sheet")].indexOf(sheet) : -1; // 블록이 없는 곳(쪽의 여백) — 그 쪽 안의 비율
  if (i < 0) return null;
  const r = sheet.getBoundingClientRect();
  return r.width && r.height ? { k: "s", a: i, n: 0, x: ptrUnit((x - r.left) / r.width), y: ptrUnit((y - r.top) / r.height) } : null;
}

function ptrHost(at) { // 자리 → 이 화면의 그 요소 | null(이 화면에는 없다 — 그리지 않는다)
  if (at.k === "s") return document.querySelectorAll("#doc > .sheet")[at.a] || null;
  return document.querySelectorAll(PTR_SEL[at.k](CSS.escape(at.a)))[at.n] || null;
}

function ptrPoint(p) { // 그 화면의 포인터 → 이 화면의 좌표 {x, y} | null
  const at = p.at;
  if (!at) return null;
  if (!p.host || !p.host.isConnected) p.host = ptrHost(at); // 쪽을 다시 그리면 요소가 새것이 된다 — 그때만 다시 찾는다
  if (!p.host) return null;
  const r = p.host.getBoundingClientRect();
  return r.width || r.height ? { x: r.left + at.x * r.width, y: r.top + at.y * r.height } : null;
}

function ptrBox() { const sc = $("scroller"); return sc && !sc.hidden ? sc.getBoundingClientRect() : null; } // 문서 창(스크롤 상자)
function ptrSeen(pt) { const b = pt && ptrBox(); return b && pt.x >= b.left && pt.x <= b.right && pt.y >= b.top && pt.y <= b.bottom ? pt : null; } // 문서 창 안에 보이는 자리만

// ---------------------------------------------------------------- 그리기 — 남의 포인터 · 「클릭」
function ptrLayer() {
  if (!ptr.layer) {
    ptr.layer = el("div", "ptr-layer");
    ptr.layer.id = "ptrLayer";
    ptr.layer.setAttribute("aria-hidden", "true"); // 눈으로 보는 표시 — 누를 수 없고 화면 낭독에 안 읽힌다
    document.body.append(ptr.layer);
  }
  return ptr.layer;
}

function ptrCur(p) {
  if (p.cur) return p.cur;
  const c = el("div", "ptr-cur");
  c.style.setProperty("--c", p.color);
  c.innerHTML = '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path d="M2 1.5v11.2l3.2-2.9 2.1 4.7 1.9-.9-2.1-4.6h4.4z" fill="var(--c)" stroke="#fff" stroke-width="1" stroke-linejoin="round"/></svg>';
  c.append(el("span", "ptr-name", p.name));
  ptrLayer().append(c);
  p.cur = c;
  return c;
}

function ptrDrawSoon(still) { // still = 문서가 움직인 것(스크롤 · 크기) — 미끄러지지 않고 바로 그 자리에
  if (still) ptr.still = true;
  if (!ptr.raf) ptr.raf = requestAnimationFrame(ptrDraw);
}

function ptrDraw() {
  ptr.raf = 0;
  const still = !!ptr.still, box = ptrBox();
  ptr.still = false;
  if (ptr.layer) ptr.layer.classList.toggle("still", still);
  for (const p of ptr.peers.values()) {
    const pt = box ? ptrPoint(p) : null;
    if (!pt || pt.x < box.left || pt.x > box.right) { if (p.cur) p.cur.hidden = true; continue; }
    const fresh = !p.cur || p.cur.hidden, cur = ptrCur(p), up = pt.y < box.top, down = pt.y > box.bottom; // 위 · 아래로 벗어남 — 가장자리에 「↑ 이름」 · 「↓ 이름」
    if (fresh) cur.style.transition = "none"; // 안 보이다 나타날 때는 옛 자리에서 미끄러져 오지 않게
    cur.hidden = false;
    cur.classList.toggle("up", up);
    cur.classList.toggle("down", down);
    cur.style.transform = `translate(${Math.round(pt.x)}px, ${Math.round(up ? box.top + 4 : down ? box.bottom - 4 : pt.y)}px)`;
    if (fresh) { void cur.offsetWidth; cur.style.transition = ""; }
  }
}

function ptrClickShow(x, y, color, mine) { // 그 자리에 퍼지는 원 + 글 「클릭」 — 잠깐 뒤 사라진다
  const m = el("div", mine ? "ptr-click mine" : "ptr-click");
  m.style.setProperty("--c", color);
  m.style.left = `${Math.round(x)}px`;
  m.style.top = `${Math.round(y)}px`;
  m.append(el("i"), el("span", null, "클릭"));
  ptrLayer().append(m);
  setTimeout(() => m.remove(), mine ? PTR_CLICK_MINE : PTR_CLICK);
}

// ---------------------------------------------------------------- 내 포인터 보내기
function ptrSendSoon() {
  if (ptr.timer || !ptr.dirty) return;
  ptr.timer = setTimeout(ptrFlush, Math.max(0, PTR_SEND - (performance.now() - ptr.sentAt)));
}

function ptrFlush() {
  ptr.timer = null;
  if (!ptr.dirty) return;
  ptr.dirty = false;
  if (!ptrLive()) return;
  if (!ptr.on || !ptr.inside) { // 껐다 · 문서 창 밖으로 나갔다 — 남의 화면에서 내 포인터를 걷는다
    if (ptr.shown) { ptrSay({ t: "off" }); ptr.shown = false; ptr.sent = ""; ptr.sentAt = performance.now(); }
    return;
  }
  const at = ptrAt(ptr.x, ptr.y);
  if (!at) return; // 쪽과 쪽 사이 — 마지막 자리 그대로 둔다(깜빡이지 않게)
  const key = `${at.k}|${at.a}|${at.n}|${at.x}|${at.y}`;
  if (key === ptr.sent) return;
  ptr.sent = key; ptr.shown = true; ptr.sentAt = performance.now();
  ptrSay({ t: "move", ...at });
}

function ptrMoved(e) { ptr.x = e.clientX; ptr.y = e.clientY; ptr.inside = true; if (ptr.on) { ptr.dirty = true; ptrSendSoon(); } }
function ptrLeft() { ptr.inside = false; if (ptr.on || ptr.shown) { ptr.dirty = true; ptrSendSoon(); } }

function ptrPressed(e) { // 켠 채로 문서를 눌렀다 — 「클릭」 을 알린다. 누른 것은 그대로 작동한다(여기서는 듣기만)
  if (!ptr.on || e.button !== 0) return;
  const at = ptrAt(e.clientX, e.clientY);
  if (!at) return;
  ptr.x = e.clientX; ptr.y = e.clientY; ptr.inside = true;
  ptrClickShow(e.clientX, e.clientY, ptr.me ? ptr.me.color : "#2563eb", true); // 내 화면에도 짧게 — 눌렀다는 확인
  if (!ptrLive()) return;
  ptr.sent = `${at.k}|${at.a}|${at.n}|${at.x}|${at.y}`; ptr.shown = true; ptr.sentAt = performance.now();
  ptrSay({ t: "click", ...at });
}

// ---------------------------------------------------------------- 단추 · 켜고 끄기
function ptrBtn() {
  let b = $("pointerBtn");
  if (b) return b;
  b = el("button", "btn");
  b.id = "pointerBtn";
  b.type = "button";
  b.hidden = true;
  b.setAttribute("aria-pressed", "false");
  b.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 3.5v14l3.9-3.6 2.7 6 2.3-1-2.7-6h5.3z"/><path d="M17.5 4.5l1.6-1.6M19.5 8h2.2M14.5 2.8V1"/></svg>';
  b.onclick = () => ptrSet(!ptr.on);
  b.oncontextmenu = (e) => { e.preventDefault(); if (ptr.pop) ptrPopClose(); else ptrPopOpen(); }; // 오른쪽 누름(자판은 메뉴 키 · Shift+F10) = 이름 · 같이 보는 화면
  const before = $("shareBtn") || $("downloadBtn");
  if (before) before.before(b);
  return b;
}

function ptrBtnDraw() {
  const b = ptrBtn(), show = !!state.id, n = ptrOthers(), who = ptr.me ? ptr.me.name : ptr.name;
  b.hidden = !show;
  if (!show) { ptrPopClose(); return; }
  b.setAttribute("aria-pressed", String(ptr.on));
  b.classList.toggle("on", ptr.on);
  b.classList.toggle("wait", ptr.on && !ptrLive());
  if (n) b.dataset.n = String(n); else delete b.dataset.n; // 같이 보는 다른 화면 수(작은 알약)
  b.setAttribute("aria-label", ptr.on ? "포인터 켜짐" : "포인터");
  b.title = (ptr.on
    ? `포인터 켜짐 · 누르면 끕니다${who ? ` — 다른 화면에 보이는 이름: ${who}` : ""}\n문서 위에서 움직이는 내 마우스가 같은 문서를 보는 다른 화면에 보이고, 누르면 그 자리에 「클릭」 이 보입니다(누른 것은 그대로 작동합니다).`
    : "포인터 — 켜면 문서 위에서 움직이는 내 마우스가 같은 문서를 보는 다른 화면에 보이고, 누르면 그 자리에 「클릭」 이 보입니다.\n다른 화면의 포인터는 켜지 않아도 보입니다.")
    + (ptr.full ? "\n이 문서를 보는 화면이 너무 많아 지금은 포인터를 쓸 수 없습니다 — 잠시 뒤 다시 잇습니다." : !ptrLive() ? "\n연결하는 중입니다…" : `\n같이 보는 다른 화면 ${n}개`)
    + "\n오른쪽 단추: 내 이름 · 같이 보는 화면";
}

function ptrSet(on) {
  ptr.on = !!on;
  ptrPut(PTR_ON, ptr.on ? "on" : "");
  ptr.dirty = true; // 켬 = 지금 자리를 알린다 · 끔 = 걷는다
  ptrSendSoon();
  ptrBtnDraw();
  ptrPopDraw();
  const who = ptr.me ? ptr.me.name : ptr.name;
  toast(ptr.on
    ? `포인터 켬 — 같은 문서를 보는 다른 화면에 내 마우스가 보입니다${ptrLive() ? "" : "(연결하는 중)"}${who ? ` · 이름 「${who}」` : ""} · 이름은 단추를 오른쪽 단추로 눌러 바꿉니다`
    : "포인터 끔 — 다른 화면에서 내 포인터가 사라집니다");
}

function ptrDocChanged() { // 다른 문서를 열었다 · 닫았다 → 옛 방에서 나가고 새 방으로
  ptrShut();
  ptr.doc = state.id || null;
  ptrPopClose();
  ptrBtnDraw();
  if (ptr.doc) ptrOpen();
}

// ---------------------------------------------------------------- 떠 있는 작은 창 — 내 이름 · 같이 보는 화면
function ptrPopOpen() { // 뼈대는 여기서 한 번만 짓는다 — 다시 그릴 때(ptrPopDraw) 이름 칸을 갈아 끼우지 않는다(치던 한글 조합이 끊기지 않게)
  if (!state.id) return;
  const pop = el("div", "ptr-pop"), head = el("div", "ptr-pop-head"), x = el("button", "ptr-pop-x", "✕"), row = el("div", "ptr-pop-row");
  const label = el("label", null, "내 이름"), name = el("input"), apply = el("button", "btn", "적용"), people = el("div", "ptr-pop-people"), acts = el("div", "ptr-pop-acts"), toggle = el("button", "btn");
  pop.id = "pointerPop";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", "포인터");
  x.type = apply.type = toggle.type = "button";
  x.setAttribute("aria-label", "닫기");
  x.onclick = ptrPopClose;
  const st = el("span", "ptr-pop-state");
  st.id = "pointerState";
  head.append(el("strong", null, "포인터"), st, x);
  label.htmlFor = name.id = "pointerName";
  name.maxLength = PTR_NAME_MAX; name.spellcheck = false; name.autocomplete = "off";
  name.value = ptr.name;
  name.setAttribute("aria-label", "내 이름");
  name.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) ptrNameApply(); };
  apply.onclick = ptrNameApply;
  row.append(label, name, apply);
  people.id = "pointerPeople";
  toggle.id = "pointerToggle";
  toggle.onclick = () => ptrSet(!ptr.on);
  acts.append(toggle);
  pop.append(head, row, el("div", "ptr-pop-k", "같이 보는 화면"), people,
    el("p", "ptr-pop-note", "켜면 문서 위에서 움직이는 내 마우스가 같은 문서를 보는 다른 화면에 보이고, 누르면 그 자리에 「클릭」 이 보입니다. 누른 것은 그대로 작동합니다. 다른 화면의 포인터는 켜지 않아도 보입니다."), acts);
  document.body.append(pop);
  ptr.pop = pop;
  ptrPopDraw();
  name.focus();
}

function ptrPopClose() { if (ptr.pop) { ptr.pop.remove(); ptr.pop = null; } }

function ptrPopPlace() {
  const pop = ptr.pop, b = $("pointerBtn");
  if (!pop || !b) return;
  const r = b.getBoundingClientRect(), w = pop.offsetWidth;
  pop.style.top = `${Math.round(r.bottom + 6)}px`;
  pop.style.left = `${Math.round(Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)))}px`;
}

function ptrPopDraw() { // 바뀌는 곳만 — 상태 글 · 이름 칸의 흐린 글 · 같이 보는 화면 · 켜기/끄기 단추(이름 칸에 치던 글은 안 건드린다)
  if (!ptr.pop) return;
  const st = $("pointerState"), name = $("pointerName"), people = $("pointerPeople"), toggle = $("pointerToggle");
  st.textContent = ptr.full ? "화면이 너무 많음" : !ptrLive() ? "연결하는 중…" : ptr.on ? "켜짐" : "꺼짐";
  st.classList.toggle("on", ptr.on && ptrLive());
  name.placeholder = ptr.me && !ptr.name ? ptr.me.name : "다른 화면에 보일 이름";
  const chip = (c, text) => { const s = el("span", "ptr-pop-who"), dot = el("i"); s.style.setProperty("--c", c); s.append(dot, text); return s; };
  people.textContent = "";
  if (ptr.me) people.append(chip(ptr.me.color, `${ptr.me.name} · 나`));
  for (const p of ptr.peers.values()) people.append(chip(p.color, p.name));
  if (!ptr.peers.size) people.append(el("span", "ptr-pop-note", ptrLive() ? "지금 이 문서를 보는 다른 화면이 없습니다" : "연결되면 같이 보는 화면이 보입니다"));
  toggle.textContent = ptr.on ? "포인터 끄기" : "포인터 켜기";
  toggle.className = ptr.on ? "btn" : "btn primary";
  ptrPopPlace();
}

function ptrNameApply() {
  const i = $("pointerName");
  if (!i) return;
  ptr.name = ptrName(i.value);
  i.value = ptr.name;
  ptrPut(PTR_NAME, ptr.name);
  ptrSay({ t: "name", name: ptr.name }); // 서버가 다듬은 이름(비웠으면 기본 이름 「사용자 N」)이 name 알림으로 돌아온다
  toast(ptr.name ? `이름을 바꿨습니다 — 다른 화면에 이름표 「${ptr.name}」 이 보입니다` : "이름을 비웠습니다 — 기본 이름(「사용자 N」)으로 보입니다");
  ptrBtnDraw();
}

// ---------------------------------------------------------------- 묶기
if (!PEEK) { // 둘째 면 화면(같이 보기)은 포인터를 다루지 않는다 — 단추도 연결도 없다(spec_포인터 ④)
  ptrBtn();
  setInterval(() => { // app.js 에 끼어들지 않고 문서가 바뀐 것만 본다(share.js 와 같은 방식) + 남의 포인터 자리 다시 맞추기
    if ((state.id || null) !== ptr.doc) ptrDocChanged();
    else if (ptr.peers.size) ptrDrawSoon(true);
  }, PTR_WATCH);
  const sc = $("scroller");
  sc.addEventListener("pointermove", ptrMoved, { passive: true });
  sc.addEventListener("pointerleave", ptrLeft, { passive: true });
  sc.addEventListener("pointerdown", ptrPressed, { capture: true, passive: true }); // 잡는 단계 — 문서의 다른 손잡이가 전파를 끊어도 듣는다(막지는 않는다)
  document.addEventListener("scroll", () => { // 문서가 움직였다 — 남의 포인터를 그 자리에 다시 · 내 마우스 아래의 자리도 달라졌다
    if (ptr.peers.size) ptrDrawSoon(true);
    if (ptr.on && ptr.inside) { ptr.dirty = true; ptrSendSoon(); }
    if (ptr.pop) ptrPopPlace();
  }, { capture: true, passive: true });
  window.addEventListener("resize", () => { if (ptr.peers.size) ptrDrawSoon(true); ptrPopPlace(); });
  window.addEventListener("blur", ptrLeft); // 다른 창으로 갔다 — 내 포인터를 걷는다
  document.addEventListener("pointerdown", (e) => {
    if (!ptr.pop || ptr.pop.contains(e.target) || (e.target.closest && e.target.closest("#pointerBtn"))) return;
    ptrPopClose();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && ptr.pop) { ptrPopClose(); $("pointerBtn").focus(); } });
}
