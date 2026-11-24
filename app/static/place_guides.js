"use strict";
// 자리마다의 작성 지침 — 화면(spec_병합 ② §5-11 「자리마다의 작성 지침」 — 2026-11-23 사용자 "3단계에서 문서나 사용자가 각 헤딩 및 테이블에 들어갈 작성요령이 이 단계에서 저장되고 관리되고 …
// 표나 각 헤딩별로 그걸 확인할 수 있도록 지침 아이콘을 추가해줘"). 서버 짝 = app/place_guides_api.py(끝점) · app/place_guides.py(순수 — 3단계 LLM 셋이 같은 색인을 읽는다).
//   · 문서 — 지침이 있는 헤딩마다 쪽 **오른쪽 여백**에 「지침」 단추(아이콘 + 수 · 사람이 적은 지침이 있으면 파란 바탕 + 점) — 「문서 표시」(tplMarksOn) 와 따로 늘 보인다.
//     지침이 없는 헤딩(개요 줄 · 본문)은 글쓰기 자리(캐럿)가 그 줄에 있을 때만 옅은 「지침 적기」. 오른쪽 여백의 다른 표시(편집 구역 이름표 .gz-tag · 고친 곳 꼬리표 .dd-tag · 서식 꼬리표 .fm-tag)와
//     같은 높이면 그 아래로 내려 놓는다(design.md §4 「작성 지침 단추」).
//   · 누르면 2열(kind "placeGuides" — 팝업 아님) 「작성 지침 — 이 자리」: ① 문서의 작성 지침(읽기만) ② 내가 적은 지침(저장 · 지우기 — 판 version 으로 묶음: 409 면 다시 읽고 적던 글은 남긴다)
//     ③ 양식의 매칭 지침(읽기만 — 고치는 곳은 link_guides.js 「매칭 지침」) ④ 누가 이 글을 읽는가.
//   · 표의 지침은 이미 있는 표 모서리 연필 「작성요령 · 표 지침」(tables.js tblAgentView — 「저장해 둔 문서 지침」 절)이 맡는다 — 여기서 표에 단추를 따로 두지 않는다.
// 다시 읽는 때: 문서를 열 때 · 문서 차례(state.serverRev)가 바뀐 뒤 잠시(묶어서 한 번) · 개요 오버레이(heads.outline)가 새로 온 뒤(헤딩 분석이 다시 돈 뒤) — app.js 에 끼어들지 않고 지켜본다(share.js 와 같은 방식).
// 다시 그리는 때: app.js tplMarksDraw 첫 줄(배율 · 창 크기 · 쪽 다시 나눔 · 오버레이) · 쪽이 새로 서거나 오른쪽 여백의 다른 표시가 생기고 없어질 때(#doc 지켜보기) · 문서 차례가 바뀐 뒤.
// app.js 가 주는 것: state · heads · $ · el · api · toast · hBtn · headsDlg · headsColClose · headsGo · gutterSync · outlineLine · paraEl · short · nf · fmtWhen · H_JSON · PEEK · DEFAULT_PAGE · PX_PER_MM
// (+ link_guides.js linkGuidesOpen · form_guides.js formGuidesList · tables.js tblAgentLeave · app.js headsGuideLeave — 모두 typeof 검사 뒤). index.html 이 app.js 다음에 읽는다. 화면 검사: tools/smoke_place_guides_ui.py.

const PLG = { key: "", rev: null, version: 0, heads: new Map(), loose: 0, busy: false, again: false, timer: 0, raf: 0, drawTimer: 0, caret: null, caretRaf: 0, open: null,
  seenRev: null, seenOutline: null, view: null, ta: null, saved: "" };
// key = 지금 문서(id|epoch) · heads = 지침이 있는 헤딩 {id → {n, user, text}} · caret = 「지침 적기」 를 보일 헤딩 id · open = 2열에 연 헤딩 id · view = 2열의 지금 답 · ta/saved = 「내가 적은 지침」 입력과 저장된 글
const PLG_H = 18; // 단추 높이(화면 px)
const PLG_WATCH_MS = 700, PLG_AFTER_EDIT_MS = 2500; // 지켜보기 · 고친 뒤 다시 읽기까지(더 고치면 미룬다 — 문서 차례마다 한 번)
const PLG_ICON = '<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="2.5" width="10" height="11.5" rx="1.5"/><path d="M6 2.5v-1h4v1M5.5 6.5h5M5.5 9h5M5.5 11.5h3"/></svg>';
const PLG_LINK_KIND = { table: "표", body: "본문" };
const PLG_READERS = "자리 연결 · 표 대응 · 빈 자리 검토(LLM)가 이 지침을 그 자리의 자료로 읽습니다 — 넣을 내용과 수는 원본에서만 가져옵니다. 「내용 반영」 은 스크립트라 이 글로 바뀌지 않습니다.";

const pgOk = () => !PEEK && !!state.id && state.format === "hwpx";
const pgKey = () => (pgOk() ? `${state.id}|${state.epoch}` : ""); // 지금 문서 — 가진 목록이 이 문서의 것인가(PLG.key)
const pgUrl = (tail = "") => `/api/docs/${encodeURIComponent(state.id)}/place-guides${tail}`;
const pgColOpen = () => heads.dlg === "placeGuides" && !$("headsDlg").hidden;

// ---- 목록 읽기 ------------------------------------------------------------------------------------------------------------------
function pgReset() { // 다른 문서 — 가진 것을 버린다
  clearTimeout(PLG.timer);
  PLG.timer = 0;
  Object.assign(PLG, { rev: null, version: 0, heads: new Map(), loose: 0, caret: null, open: null, seenRev: state.serverRev, seenOutline: heads.outline || null, view: null, ta: null, saved: "" });
  pgPaint();
}
function pgSoon(ms) { clearTimeout(PLG.timer); PLG.timer = setTimeout(pgLoad, ms); }
async function pgLoad() {
  clearTimeout(PLG.timer);
  PLG.timer = 0;
  if (!pgOk()) return;
  if (PLG.busy) { PLG.again = true; return; }
  const id = state.id, epoch = state.epoch;
  PLG.busy = true;
  try {
    const r = await api(pgUrl());
    if (id !== state.id || epoch !== state.epoch) return;
    pgTake(r);
  } catch { /* 옛 서버(끝점 없음) · 일시 오류 — 가진 것 그대로 */ }
  finally {
    PLG.busy = false;
    if (PLG.again) { PLG.again = false; pgSoon(300); }
  }
}
function pgTake(r) { // 목록 답 → 색인(헤딩 id → 항목) — 답마다 한 번
  PLG.rev = r.rev;
  PLG.version = r.version || 0;
  PLG.loose = r.loose || 0;
  PLG.heads = new Map((r.heads || []).filter((h) => h && h.id && h.n > 0).map((h) => [h.id, { n: h.n, user: !!h.user, text: h.text || "" }]));
  if (PLG.caret && PLG.heads.has(PLG.caret)) PLG.caret = null; // 이제 지침이 있는 헤딩 — 늘 보이는 단추가 맡는다
  pgPaint();
}
function pgWatch() { // 문서 · 문서 차례 · 개요 오버레이가 바뀌었나 — 화면 값만 본다(서버는 바뀔 때만 읽는다)
  if (document.hidden) return;
  const key = pgKey();
  if (key !== PLG.key) {
    PLG.key = key;
    pgReset();
    if (key) pgSoon(300);
    return;
  }
  if (!key) return;
  if (state.serverRev !== PLG.seenRev) { PLG.seenRev = state.serverRev; pgDraw(); pgSoon(PLG_AFTER_EDIT_MS); } // 고친 뒤 — 자리는 곧바로 다시 재고, 목록은 더 고치지 않으면
  const ol = heads.outline || null;
  if (ol !== PLG.seenOutline) { PLG.seenOutline = ol; pgSoon(400); pgCaretSync(); } // 헤딩 분석이 다시 돈 뒤(작성 지침 저장도 그때) · 개요 줄이 생기면 「지침 적기」 도
}

// ---- 문서의 단추 ---------------------------------------------------------------------------------------------------------------
function pgDraw() { // 다시 그리기를 잡는다(한 프레임에 한 번) — app.js tplMarksDraw 첫 줄 · 지켜보기가 부른다
  if (PLG.raf) return;
  PLG.raf = requestAnimationFrame(() => { PLG.raf = 0; pgPaint(); });
}
function pgMgr(sheet, z) { // 그 쪽 오른쪽 여백 폭(화면 px — doc_diff.js 와 같은 셈)
  const sec = (state.sections && state.sections[+sheet.dataset.sec]) || DEFAULT_PAGE;
  return Math.round(((sec.marginsMm && sec.marginsMm.r) || 0) * PX_PER_MM * z * 10) / 10;
}
function pgSheetGeo(sheet, geo) { // 쪽의 자리 · 배율 · 오른쪽 여백 폭 · 그 여백의 다른 표시가 차지한 높이들(쪽 위끝에서 · 화면 px) — 읽기만
  let g = geo.get(sheet);
  if (g) return g;
  const sr = sheet.getBoundingClientRect(), z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1;
  const busy = [];
  for (const e of sheet.querySelectorAll(":scope > .gz-tag, :scope > .dd-tag, :scope > .fm-tag, :scope > .os-bar")) { // .os-bar = 줄 오른쪽의 서식 아이콘(outline_spot.js — 「서식」 묶음을 켠 동안 커서 줄에: 그 아래로)
    const b = e.getBoundingClientRect();
    if (b.height) busy.push([b.top - sr.top, b.bottom - sr.top]);
  }
  g = { sr, z, mgr: pgMgr(sheet, z), busy, items: [] };
  geo.set(sheet, g);
  return g;
}
function pgFree(top, busy, last) { // 다른 표시와 앞 단추를 피한 높이 — 겹치면 그 아래로
  let t = Math.max(Math.round(top), last);
  for (let moved = true, n = 0; moved && n < 20; n += 1) {
    moved = false;
    for (const [a, b] of busy) if (t < b && t + PLG_H > a) { t = Math.ceil(b) + 2; moved = true; }
  }
  return t;
}
function pgWidth(h, caret, brief) { // 단추 폭 어림(화면 px — 재지 않는다: 붙인 뒤 재면 단추마다 배치를 다시 한다) — 여백 안 자리를 고를 때만 쓴다
  return caret ? (brief ? 34 : 70) : 27 + 6.5 * nf(h.n).length + (h.user ? 9 : 0);
}
function pgButton(id, h, caret, brief = false) { // brief = 좁은 여백의 「지침 적기」 — 글 대신 「＋」(이름은 풍선 도움말)
  const b = el("button", "pg-btn" + (caret ? " caret" : h.user ? " user" : "") + (PLG.open === id && pgColOpen() ? " on" : ""));
  b.type = "button";
  b.dataset.pg = id;
  b.innerHTML = PLG_ICON;
  if (caret) {
    b.append(el("span", "pg-t", brief ? "＋" : "지침 적기"));
    b.title = "이 헤딩에 작성 지침 적기 — 오른쪽 열에서 적고 저장하면 3단계 LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 이 자리를 볼 때 읽습니다";
    b.setAttribute("aria-label", "이 헤딩에 작성 지침 적기");
  } else {
    b.append(el("span", "pg-n", nf(h.n)));
    if (h.user) b.append(el("span", "pg-dot"));
    const docN = h.n - (h.user ? 1 : 0);
    b.title = `작성 지침 ${nf(h.n)}개 — ${[docN ? `문서의 지침 ${nf(docN)}개` : "", h.user ? "내가 적은 지침 있음" : ""].filter(Boolean).join(" · ")}`
      + (h.text ? `\n「${short(h.text, 40)}」` : "") + "\n누르면 오른쪽 열에서 보고 적습니다";
    b.setAttribute("aria-label", `작성 지침 ${h.n}개${h.user ? " · 내가 적은 지침 있음" : ""}`);
  }
  b.onmousedown = (e) => e.preventDefault(); // 글쓰기 자리를 그 헤딩에 둔 채로(「지침 적기」 가 누르는 사이 사라지지 않게)
  b.onclick = (e) => { e.stopPropagation(); pgOpen(id); };
  return b;
}
function pgPaint() { // 지침이 있는 헤딩 + 「지침 적기」 줄만 잰다 — 읽기(자리 모두) → 쓰기(단추 붙이기)
  clearTimeout(PLG.drawTimer);
  for (const e of document.querySelectorAll("#doc .sheet > .pg-btn")) e.remove();
  if (!pgOk() || PLG.key !== pgKey() || !(PLG.heads.size || PLG.caret) || !gutterSync()) return; // 다른 문서를 막 열었다 — 지켜보기가 비우고 다시 읽을 때까지 옛 목록으로 그리지 않는다(문단 id 는 문서마다 겹친다)
  const geo = new Map();
  const want = [...PLG.heads].map(([id, h]) => ({ id, h, caret: false }));
  if (PLG.caret && !PLG.heads.has(PLG.caret)) want.push({ id: PLG.caret, h: { n: 0, user: false, text: "" }, caret: true });
  for (const w of want) {
    const p = paraEl(w.id);
    const sheet = p && p.closest("#doc .sheet");
    if (!sheet) continue;
    const r = p.getBoundingClientRect();
    if (!r.height) continue; // 감춘 요소(엑셀식 보기로 바꾼 표 안 등)
    const g = pgSheetGeo(sheet, geo);
    g.items.push({ ...w, top: r.top - g.sr.top });
  }
  for (const [sheet, g] of geo) {
    g.items.sort((a, b) => a.top - b.top);
    let last = -1e9;
    for (const it of g.items) {
      const top = pgFree(it.top, g.busy, last);
      last = top + PLG_H + 2;
      const brief = it.caret && g.mgr < pgWidth(it.h, true, false) + 10;
      const b = pgButton(it.id, it.h, it.caret, brief);
      b.style.zoom = String(1 / g.z); // 화면 크기 고정 · 자리는 화면 px(app.js zoomPut 이 배율을 뒤에서 바꿀 때 자리 · 여백 폭을 같이 맞춘다)
      b.style.setProperty("--mgr", `${g.mgr}px`);
      b.style.setProperty("--pgx", `${Math.max(2, Math.min(8, Math.floor(g.mgr - pgWidth(it.h, it.caret, brief) - 3)))}px`); // 본문 오른끝에서 — 넓으면 8px, 좁으면 종이 안에 들게 당기되 본문에서 2px 은 띄운다(그래도 안 들면 종이 밖으로 조금)
      b.style.top = `${top}px`;
      sheet.append(b);
    }
  }
}

// 「지침 적기」 — 글쓰기 자리가 지침 없는 헤딩(본문의 개요 줄 · 헤딩 역할)에 있을 때만. 줄이 바뀔 때만 다시 그린다(치는 동안은 그대로)
function pgCaretOf() {
  if (!pgOk() || !heads.outline) return null;
  const s = getSelection();
  const n = s && s.rangeCount ? s.anchorNode : null;
  const e = n && (n.nodeType === 1 ? n : n.parentElement);
  const p = e && e.closest ? e.closest("#doc .para[data-id]") : null;
  if (!p || p.closest("td")) return null;
  const ol = outlineLine(p);
  if (!ol || (ol.role || "heading") !== "heading" || (ol.flow || "body") !== "body") return null; // 3단계 LLM 이 읽는 헤딩 = 본문 헤딩 줄(place_guides.heading_finder)
  return PLG.heads.has(p.dataset.id) ? null : p.dataset.id;
}
function pgCaretSync() {
  PLG.caretRaf = 0;
  const pid = pgCaretOf();
  if (pid === PLG.caret) return;
  if (!pid && PLG.caret && PLG.caret === PLG.open && pgColOpen()) return; // 열에 연 헤딩 — 열에서 적는 동안 문서의 단추를 남긴다(어느 줄인지)
  PLG.caret = pid;
  pgPaint();
}

// ---- 2열 「작성 지침 — 이 자리」 -------------------------------------------------------------------------------------------------
const pgDirty = () => !!(PLG.ta && PLG.ta.isConnected && pgColOpen() && PLG.ta.value.trim() !== PLG.saved.trim());
function pgOnSync() { for (const b of document.querySelectorAll("#doc .sheet > .pg-btn")) b.classList.toggle("on", pgColOpen() && b.dataset.pg === PLG.open); }

async function pgOpen(pid, { keep = null } = {}) { // keep = 409 뒤 다시 읽을 때 적던 글(버리지 않는다)
  if (!pgOk()) return;
  if (pgColOpen() && PLG.open !== pid && pgDirty() && !confirm("저장하지 않은 지침 글이 있습니다. 버릴까요?")) return;
  if (!pgColOpen() && ((typeof headsGuideLeave === "function" && !headsGuideLeave()) || (typeof tblAgentLeave === "function" && !tblAgentLeave()))) return; // 다른 열의 저장 안 한 글
  PLG.open = pid;
  const h = PLG.heads.get(pid);
  const { body } = headsDlg("placeGuides", "작성 지침 — 이 자리", h && h.text ? `「${short(h.text, 50)}」` : "읽는 중…");
  body.append(el("div", "lk-cap", "읽는 중…"));
  pgOnSync();
  const seq = heads.seq, id = state.id, epoch = state.epoch;
  let v;
  try { v = await api(pgUrl(`/heads/${encodeURIComponent(pid)}`)); }
  catch (e) {
    if (seq === heads.seq && epoch === state.epoch) { body.textContent = ""; body.append(el("div", "lk-cap", `지침을 읽지 못했습니다: ${e.message}`)); }
    return;
  }
  if (seq !== heads.seq || epoch !== state.epoch || id !== state.id) return;
  pgRender(v, keep);
}

const PG_FOLD_CHARS = 260, PG_FOLD_LINES = 6;
function pgKindKey(kind) {
  if (/^\d+\./.test(kind)) return "match";
  if (kind.includes("※") || kind.includes("안내")) return "warn";
  if (kind.includes("요령") || kind.includes("표")) return "table";
  if (kind.includes("참고")) return "ref";
  return "note";
}
function pgFormatText(text) {
  const box = el("div", "pg-text");
  const lines = text.split("\n");
  const pipeCount = lines.filter((l) => l.includes(" | ")).length;
  if (!pipeCount) {
    box.append(document.createTextNode(text));
    return box;
  }
  box.classList.add("has-rows");
  let headDone = false;
  lines.forEach((line, i) => {
    if (i > 0) box.append(document.createTextNode("\n"));
    if (line.includes(" | ")) {
      const cells = line.split(" | ");
      const isHead = !headDone && pipeCount >= 2 && cells.every((c) => c.trim().length <= 20);
      if (isHead) headDone = true;
      const isKv2 = cells.length === 2 && cells[0].trim().length > 0 && cells[0].trim().length <= 18;
      const row = el("div", "pg-ln pg-kv" + (isKv2 ? " kv2" : cells.length >= 3 ? " kv3" : "") + (isHead ? " pg-kv-head" : ""));
      cells.forEach((cell, j) => {
        if (j > 0) row.append(el("span", "pg-pipe", " | "));
        row.append(el("span", `pg-cell pg-c${Math.min(j, 2)}`, cell));
      });
      box.append(row);
    } else if (i === 0 && pipeCount >= 2 && line.trim()) {
      box.append(el("div", "pg-ln pg-ln-title", line));
    } else {
      box.append(el("div", "pg-ln pg-ln-sub", line));
    }
  });
  return box;
}

function pgItem(kind, title, text, cls = "") { // 읽기만 하는 줄 — 종류 꼬리표 위 · 글 전체 폭 · 긴 지침은 접고 펼치기
  const li = el("li", cls ? `pg-item ${cls}` : "pg-item");
  const head = el("div", "pg-item-head");
  const tag = el("span", "hb pg-kind", kind);
  tag.dataset.kind = pgKindKey(kind);
  head.append(tag);
  if (title) head.append(el("b", "pg-title", title));
  const body = el("div", "pg-body");
  body.append(pgFormatText(text));
  li.append(head, body);
  const lines = text ? text.split("\n").length : 0;
  if (text.length > PG_FOLD_CHARS || lines > PG_FOLD_LINES) {
    li.classList.add("is-long", "is-fold");
    const label = lines > 2 ? `펼쳐 보기 (${nf(lines)}줄)` : "펼쳐 보기";
    const more = el("button", "pg-more", label);
    more.type = "button";
    more.setAttribute("aria-expanded", "false");
    more.onclick = () => {
      const folded = li.classList.toggle("is-fold");
      more.setAttribute("aria-expanded", String(!folded));
      more.textContent = folded ? label : "접기";
    };
    li.append(more);
  }
  return li;
}

function pgRender(v, keep = null) {
  const tools = $("headsDlgTools"), body = $("headsDlgBody"), foot = $("headsDlgFoot");
  for (const x of [tools, body, foot]) x.textContent = "";
  PLG.view = v;
  const note = $("headsDlgNote");
  note.textContent = v.text ? `「${short(v.text, 50)}」${v.alive ? "" : " — 지금 문서에 없음"}` : "(헤딩 글 없음)";
  note.title = v.text ? `${v.text}${v.alive ? "" : " — 지금 문서에 없음"}` : "";
  const docs = v.doc || [], user = v.user || null, match = v.match || [];
  tools.append(hBtn("문서에서 보기", () => headsGo(v.id), { cls: "btn sm pg-tbtn", disabled: !v.alive, title: v.alive ? "문서의 그 헤딩으로" : "그 헤딩이 지금 문서에 없습니다" }));
  if (typeof formGuidesList === "function") tools.append(hBtn("작성 지침 목록", () => { if (!pgDirty() || confirm("저장하지 않은 지침 글이 있습니다. 버릴까요?")) formGuidesList({ id: state.id, name: state.name }); },
    { cls: "btn sm pg-tbtn", title: `이 문서에 저장해 둔 작성 지침 전체(헤딩별 · 표별)${PLG.loose ? ` — 헤딩 · 표를 못 정한 지침 ${nf(PLG.loose)}개도 거기` : ""}` }));
  tools.append(el("span", "muted pg-total", `지침 ${nf(docs.length + (user ? 1 : 0))}개`));
  const wrap = el("div", "pg-col");
  // ① 문서의 작성 지침
  const s1 = el("section", "pg-sec pg-sec-doc");
  s1.dataset.pgSec = "doc";
  const sh1 = el("div", "pg-sec-head");
  sh1.append(el("h3", "pg-h", `문서의 작성 지침 ${nf(docs.length)}`));
  if (docs.length) sh1.append(el("span", "pg-sec-tag", "읽기 전용"));
  s1.append(sh1);
  if (docs.length) {
    const ul = el("ul", "pg-list");
    for (const g of docs) {
      const text = g.text || "";
      ul.append(g.label ? pgItem(g.kind || "각주", short(g.label, 60), `→ ${text}`) : pgItem(g.kind || "지침", "", text));
    }
    s1.append(ul);
  } else s1.append(el("p", "hnote pg-empty", "문서에서 모은 작성 지침이 없습니다 (1단계 「문서 검토」 가 모읍니다)."));
  // ② 내가 적은 지침
  const s2 = el("section", "pg-sec pg-sec-user" + (user ? " has-user" : ""));
  s2.dataset.pgSec = "user";
  const sh2 = el("div", "pg-sec-head");
  const st2 = el("span", "pg-st");
  sh2.append(el("h3", "pg-h", "내가 적은 지침"), st2);
  s2.append(sh2);
  const ta = el("textarea", "pg-ta");
  ta.id = `pg-ta-${heads.seq}`;
  ta.rows = 4;
  ta.placeholder = "이 자리에 넣을 것 · 빼야 할 것을 적으세요 (예: 당해 차년도 실적만 · 2쪽 이내 요약) — 넣을 사실 · 수는 원본에서 가져옵니다";
  ta.setAttribute("aria-label", "내가 적은 지침");
  PLG.saved = user ? user.text || "" : "";
  ta.value = keep != null ? keep : PLG.saved;
  PLG.ta = ta;
  const row = el("div", "pg-row pg-user-acts"), cnt = el("span", "muted pg-cnt"), btns = el("div", "pg-btns");
  const del = hBtn("지우기", () => { if (confirm("내가 적은 지침을 지울까요?")) pgSave(""); }, { cls: "btn sm pg-del", title: "내가 적은 지침을 지웁니다(문서의 작성 지침은 그대로)" });
  const save = hBtn("저장", () => pgSave(ta.value), { cls: "btn sm primary pg-save", title: "이 헤딩의 작성 지침으로 저장합니다(작업에 — 문서는 바뀌지 않습니다) · Ctrl+Enter" });
  const sync = () => {
    const n = ta.value.trim().length, dirty = ta.value.trim() !== PLG.saved.trim();
    save.disabled = !dirty || (!v.alive && !!ta.value.trim()) || n > 4000;
    del.hidden = !user;
    cnt.textContent = `${nf(n)} / 4,000자${dirty ? " · 저장 안 함" : user && user.at ? ` · 저장 ${fmtWhen(user.at)}` : ""}`;
    cnt.classList.toggle("warn", n > 4000);
    cnt.classList.toggle("dirty", dirty && n <= 4000);
    s2.classList.toggle("is-dirty", dirty);
    st2.textContent = !v.alive ? "문서에 없음" : dirty ? "수정 중" : user ? "저장됨" : ""; // 아직 안 적었으면 꼬리표 없음
    st2.className = "pg-st" + (!v.alive ? " off" : dirty ? " dirty" : user ? " saved" : "");
    st2.hidden = !st2.textContent;
  };
  ta.oninput = sync;
  ta.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!save.disabled) save.click(); } };
  if (!v.alive) { ta.readOnly = true; s2.append(el("p", "hnote pg-empty", "이 헤딩이 지금 문서에 없습니다 — 적어 둔 지침은 지우기만 할 수 있습니다.")); }
  btns.append(del, save);
  row.append(cnt, btns);
  s2.append(ta, row);
  sync();
  // ③ 양식의 매칭 지침
  const s3 = el("section", "pg-sec pg-sec-match" + (match.length ? "" : " is-empty"));
  s3.dataset.pgSec = "match";
  const sh3 = el("div", "pg-sec-head");
  sh3.append(el("h3", "pg-h", `양식의 매칭 지침 ${nf(match.length)}`));
  if (typeof linkGuidesOpen === "function") {
    sh3.append(hBtn("매칭 지침 열기", () => { if (!pgDirty() || confirm("저장하지 않은 지침 글이 있습니다. 버릴까요?")) linkGuidesOpen({ id: state.id, name: state.name }); },
      { cls: "btn sm pg-link-btn", title: "양식 전체가 같이 쓰는 매칭 지침(표 · 본문 자리마다 어떻게 잇나)을 보고 고칩니다 — 연차보고서 양식 정보의 「자리 연결」 절" }));
  }
  s3.append(sh3);
  if (match.length) {
    const ul = el("ul", "pg-list");
    for (const m of match) ul.append(pgItem(`${m.n}. ${PLG_LINK_KIND[m.kind] || m.kind || ""}`, short(m.title || "", 60), m.text || ""));
    s3.append(ul);
  }
  wrap.append(s1, s2, s3);
  body.append(wrap);
  // ④ 누가 읽나(발에 고정 — 노트 도움말로 전체 설명)
  const who = el("div", "pg-who");
  if (typeof hHelp === "function") who.append(hHelp("누가 이 지침을 읽는가", `${PLG_READERS}\n\n내가 적은 지침은 작업에 저장됩니다 — 문서는 바뀌지 않습니다.`));
  const whoShort = el("span", "pg-who-short", "3단계 LLM 검토가 읽음 · 문서 변경 없음");
  whoShort.title = PLG_READERS;
  who.append(whoShort, el("span", "sr-only", PLG_READERS));
  foot.append(who, hBtn("닫기", () => { if (!pgDirty() || confirm("저장하지 않은 지침 글이 있습니다. 버릴까요?")) headsColClose(); }, { cls: "btn sm pg-close" }));
  pgOnSync();
}

function pgDraft(fallback) { // 열의 「내가 적은 지침」 입력칸의 지금 글(열이 닫혔으면 fallback — 보낸 글)
  const ta = document.querySelector("#headsDlg .pg-ta");
  return ta && heads.dlg === "placeGuides" ? ta.value : fallback;
}

async function pgSave(text) {
  const v = PLG.view;
  if (!v || !pgOk()) return;
  const pid = v.id, seq = heads.seq, epoch = state.epoch;
  let r;
  try { r = await api(pgUrl(`/heads/${encodeURIComponent(pid)}`), { method: "PUT", headers: H_JSON, body: JSON.stringify({ text, version: v.version }) }); }
  catch (e) {
    if (epoch !== state.epoch) return;
    if (e.status === 409) { toast("그 사이 다른 화면에서 지침이 바뀌었습니다 — 다시 읽었습니다(적던 글은 그대로 · 다시 저장하세요)", true); if (seq === heads.seq) pgOpen(pid, { keep: pgDraft(text) }); }
    else if (e.status === 404) toast("그 헤딩이 지금 문서에 없습니다 — 다시 읽어 주세요", true);
    else toast(`지침을 저장하지 못했습니다: ${e.message}`, true);
    return;
  }
  if (epoch !== state.epoch) return;
  PLG.version = r.version || 0;
  const n = (r.doc || []).length + (r.user ? 1 : 0);
  if (n) PLG.heads.set(pid, { n, user: !!r.user, text: r.text || "" }); else PLG.heads.delete(pid);
  if (PLG.caret === pid && n) PLG.caret = null;
  pgPaint();
  if (seq === heads.seq && heads.dlg === "placeGuides") { const now = pgDraft(text); pgRender(r, now !== text ? now : null); } // 보내는 사이 더 친 글은 그대로 둔다(저장 기준 · 판만 새것 — astra 3차)
  toast(text.trim() ? "지침을 저장했습니다 — 3단계 LLM 검토가 이 자리를 볼 때 읽습니다" : "내가 적은 지침을 지웠습니다");
  pgSoon(400); // 목록도 서버 것으로(수 · 판)
}

// ---- 지켜보기 --------------------------------------------------------------------------------------------------------------------
(function pgBind() {
  setInterval(pgWatch, PLG_WATCH_MS);
  document.addEventListener("selectionchange", () => { if (!PLG.caretRaf) PLG.caretRaf = requestAnimationFrame(pgCaretSync); });
  window.addEventListener("resize", pgDraw);
  const doc = $("doc"), col = $("headsDlg");
  if (doc && typeof MutationObserver === "function") { // 쪽이 새로 섬(다시 나눔 · 다시 읽음) · 오른쪽 여백의 다른 표시가 생기거나 없어짐 — 단추 자리를 다시(자기 단추는 무시)
    const OTHER = ["sheet", "gz-tag", "dd-tag", "fm-tag", "os-bar"];
    const hit = (nodes) => { for (const x of nodes) if (x.nodeType === 1 && OTHER.some((c) => x.classList.contains(c))) return true; return false; };
    new MutationObserver((recs) => {
      if (!PLG.heads.size && !PLG.caret) return;
      for (const m of recs) if (m.target === doc || hit(m.addedNodes) || hit(m.removedNodes)) { clearTimeout(PLG.drawTimer); PLG.drawTimer = setTimeout(pgDraw, 60); return; }
    }).observe(doc, { childList: true, subtree: true });
  }
  if (col && typeof MutationObserver === "function") new MutationObserver(() => { pgOnSync(); pgCaretSync(); }).observe(col, { attributes: true, attributeFilter: ["hidden", "data-kind"] }); // 열을 닫거나 다른 보기로 — 눌림 표시를 걷고 「지침 적기」 도 지금 글쓰기 자리로
})();
