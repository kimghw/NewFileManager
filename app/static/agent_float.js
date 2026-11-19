"use strict";
// 에이전트 창(spec_일반편집 ② §12 「에이전트 창」 · design.md §9 「상단 바 오른쪽 끝」) — 2026-11-18 사용자
// 「대시보드 옆 에이전트는 워크플로우 아이콘 옆 에이전트아이콘으로 하고 지금 그 아이콘 내부 내용은 거기서 설정창 아이콘을 누르면 그게 볼 수 있도록 해줘,
//  에이전트 아이콘을 누르면 팝업으로 지금과 같은 대시보드 옆 에이전트 사이드패널 크기를 띄어줘, .. 그리고 아이콘 넣어서 지금 처럼 대시보드 옆으로 들어 갈 수 있도록 해줘」.
// 에이전트 보기(#paneAgent — doc_agent.js)가 놓이는 자리는 둘이다:
//   · 떠 있는 창(기본 — #agentFloat): 상단 바의 에이전트 아이콘(#agentBtn — 워크플로우 다음 · 전의 「에이전트 설정」 링크 자리)으로 여닫는다. 모달 아님 — 문서·패널은 그대로 쓴다.
//     처음 자리 = 패널(또는 2열) 바로 왼쪽 · 패널과 같은 폭 · 편집 도구 줄 · 파일명 줄 아래부터 패널 아래 끝까지(도구 줄의 실행 취소를 가리지 않게). 머리를 끌어 옮기고 오른쪽 아래 모서리로 크기를 바꾼다(이 브라우저에 기억 nfm.agentFloat · 머리를 두 번 누르면 처음 자리로).
//   · 패널 탭(전처럼 — 「대시보드」 옆 #tabAgent): 창 머리의 「패널에 넣기」 로 고른다 · 다시 띄우기는 에이전트 상태 줄의 「창으로 띄우기」. 고른 자리는 이 브라우저에 기억(nfm.agentDock).
// 「에이전트 설정」(/agents — 새 탭)은 창 머리 · (패널 탭일 때) 상태 줄의 톱니 아이콘이 연다.
// 같은 #paneAgent 노드를 옮길 뿐이다 — 대화 · 쓰던 요청 · 자료는 그대로(AGENT 상태는 DOM 밖).
// app.js 와의 약속: showTab("Agent") · toolShown("Agent") 은 그대로 「에이전트 보기를 연다 / 열 수 있나」 다 — 창 자리면 showTab 이 agentFloatOpen 으로 보내고(app.js agentFloatOn),
// 패널 도구를 바꿀 때 #paneAgent 를 건드리지 않는다. toolTabsDraw · taskListBtnDraw 가 agentFloatSync 를 불러 아이콘의 눌림과 문서가 바뀐 뒤의 창을 맞춘다.
// app.js 가 주는 것: $ · state · PEEK · toolShown · showTab · toolTabsDraw · colFolded · PANEL_BACK. doc_agent.js: agentShow · AGENT(대화 칸 굴림).

const AGF_DOCK_KEY = "nfm.agentDock", AGF_AT_KEY = "nfm.agentFloat";
const AGF = { el: null, body: null, note: null, doc: null, open: false, forDoc: null, at: null, set: null, home: null, prev: null };
// open = 창이 보이나 · forDoc = 창을 열 때의 문서(다른 문서를 열거나 닫으면 맞춘다) · at = 사람이 옮기거나 늘린 자리 {x, y, w, h}(없으면 패널 옆) · set = 마지막으로 정한 크기(사람이 모서리로 바꿨나 가리기)
// home = #paneAgent 의 패널 안 원래 자리 · prev = 패널 탭 자리에서 아이콘으로 에이전트를 열기 전의 패널 도구(다시 누르면 그리로)
let agfDock = (() => { try { return localStorage.getItem(AGF_DOCK_KEY) === "panel"; } catch { return false; } })(); // true = 패널 탭 · false = 떠 있는 창(기본)
try { const v = JSON.parse(localStorage.getItem(AGF_AT_KEY) || "null"); if (v && [v.x, v.y, v.w, v.h].every(Number.isFinite)) AGF.at = v; } catch { /* 패널 옆 */ }

function agentFloating() { return !agfDock; } // app.js agentFloatOn 이 본다

// 그림(18px 선 1.8 — 상단 바 아이콘과 같은 꼴: design.md §9). agent = 말풍선 + 반짝임(보라 — LLM: §13) · dock/undock = 오른쪽 열이 있는 창 + 그 열로 들어가는/나오는 화살표
const AGF_SVG = {
  agent: '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 3.5V17A2.5 2.5 0 0 1 4 14.5Z"/><path d="M12 7.3l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9Z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  dock: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16M17.3 8.5h1.4M17.3 11.5h1.4"/><path d="M5.5 12h6M9.5 9.5 12 12l-2.5 2.5"/>',
  undock: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16M17.3 8.5h1.4M17.3 11.5h1.4"/><path d="M12.5 12h-6M9 9.5 6.5 12 9 14.5"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>'
};
const agfSvg = (name, size) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${AGF_SVG[name]}</svg>`;
function agfIc(tag, cls, name, label, title, onclick) { // 글 없는 아이콘 단추(이름은 aria-label · 도움말은 title — design.md §9)
  const b = document.createElement(tag);
  b.className = `agf-ic ${cls}`;
  if (tag === "button") b.type = "button";
  b.setAttribute("aria-label", label);
  b.title = title;
  b.innerHTML = agfSvg(name, 16);
  if (onclick) b.onclick = onclick;
  return b;
}
function agfSettingsLink() { // 「에이전트 설정」 — 전에 상단 바 오른쪽 끝에 있던 링크(#agentsLink)와 같은 곳 · 같은 도움말(spec_에이전트 ② §5)
  const a = agfIc("a", "agf-settings", "gear", "에이전트 설정", "에이전트 설정 — 앱이 LLM 에 맡기는 일(에이전트)마다 작업 번호 · 역할 · 모델 · 프롬프트를 새 탭에서 보고 고칩니다");
  a.href = "/agents";
  a.target = "_blank";
  a.rel = "noopener";
  a.draggable = false;
  return a;
}
// 패널 탭 자리일 때 에이전트 상태 줄(.ag-status — doc_agent.js agentFrame)의 오른쪽 끝에 붙는 둘: 「에이전트 설정」 · 「창으로 띄우기」. 창 안에서는 CSS 가 감춘다(창 머리에 같은 것)
function agentFloatTools() {
  const s = document.createElement("span");
  s.className = "agf-pane-tools";
  s.append(agfSettingsLink(), agfIc("button", "agf-undock", "undock", "창으로 띄우기", "창으로 띄우기 — 에이전트를 패널 탭에서 빼 떠 있는 창으로 엽니다(상단 바의 에이전트 아이콘으로 여닫음)", () => agentDockSet(false)));
  return s;
}

function agfBuild() {
  if (AGF.el) return AGF.el;
  const w = document.createElement("section");
  w.className = "agf";
  w.id = "agentFloat";
  w.hidden = true;
  w.setAttribute("role", "dialog");
  w.setAttribute("aria-modal", "false");
  w.setAttribute("aria-labelledby", "agfTitle");
  const head = document.createElement("header");
  head.className = "agf-head";
  head.title = "끌어서 옮기기 · 두 번 누르면 처음 자리(패널 옆)로";
  const mark = document.createElement("span");
  mark.className = "agf-mark";
  mark.innerHTML = agfSvg("agent", 16);
  const title = document.createElement("strong");
  title.className = "agf-title";
  title.id = "agfTitle";
  title.textContent = "에이전트";
  const doc = document.createElement("span");
  doc.className = "agf-doc";
  const settings = agfSettingsLink();
  settings.id = "agentSettings";
  const dock = agfIc("button", "agf-dock", "dock", "패널에 넣기", "패널에 넣기 — 이 창을 오른쪽 패널의 「대시보드」 옆 탭으로 넣습니다(다시 띄우려면 에이전트 상태 줄의 「창으로 띄우기」)", () => agentDockSet(true));
  dock.id = "agentDock";
  const x = agfIc("button", "agf-x", "close", "에이전트 창 닫기", "닫기 — 대화 · 쓰던 요청 · 자료는 그대로 남습니다(상단 바의 에이전트 아이콘으로 다시 엶)", () => agentFloatClose());
  x.id = "agentFloatClose";
  head.append(mark, title, doc, settings, dock, x);
  const body = document.createElement("div");
  body.className = "agf-body";
  const note = document.createElement("p");
  note.className = "agf-note";
  note.hidden = true;
  body.append(note);
  w.append(head, body);
  agfDrag(w, head);
  head.addEventListener("dblclick", (e) => { if (e.target.closest("button, a")) return; AGF.at = null; agfSave(); agfPlace(); });
  document.body.append(w);
  if (typeof ResizeObserver === "function") new ResizeObserver(agfResized).observe(w);
  Object.assign(AGF, { el: w, body, note, doc });
  return w;
}

// #paneAgent 를 창 몸 ↔ 패널의 원래 자리로 옮긴다 — 옮겼으면 true(옮기면 대화 칸 굴림이 처음으로 가므로 부르는 쪽이 끝으로 내린다)
function agfPaneTo(float) {
  const pane = $("paneAgent");
  if (!pane) return false;
  if (!AGF.home) AGF.home = { parent: pane.parentNode, next: pane.nextSibling };
  if (float) {
    agfBuild();
    if (pane.parentNode === AGF.body) return false;
    AGF.body.prepend(pane);
    return true;
  }
  const { parent, next } = AGF.home;
  if (pane.parentNode === parent) return false;
  parent.insertBefore(pane, next && next.parentNode === parent ? next : null);
  return true;
}
function agfTalkEnd() { if (typeof AGENT === "object" && AGENT.el && AGENT.el.talk) AGENT.el.talk.scrollTop = AGENT.el.talk.scrollHeight; }

function agentFloatOpen() {
  if (typeof PEEK !== "undefined" && PEEK) return;
  const w = agfBuild(), can = toolShown("Agent"), pane = $("paneAgent"), was = AGF.open;
  let moved = false;
  if (can) { moved = agfPaneTo(true); pane.hidden = false; }
  else if (pane && pane.parentNode === AGF.body) pane.hidden = true;
  AGF.note.hidden = can;
  if (!can) AGF.note.textContent = state.id
    ? "DOCX 문서에는 에이전트 보기가 없습니다 — HWPX 문서를 열면 이 창에서 요청합니다."
    : "문서를 열면 이 창에서 에이전트에게 요청합니다. 시작 화면에서는 오른쪽 「에이전트」 대화창에 파일을 올리거나 하려는 일을 적으세요.";
  AGF.doc.textContent = can ? state.name || "" : "";
  AGF.doc.title = AGF.doc.textContent;
  AGF.forDoc = state.id || null;
  w.hidden = false;
  AGF.open = true;
  if (!was) agfPlace();
  agentFloatSync(true);
  if (can && typeof agentShow === "function") agentShow();
  if (moved) agfTalkEnd();
}

function agentFloatClose() {
  if (!AGF.el || !AGF.open) return;
  const had = AGF.el.contains(document.activeElement); // 초점이 창 안에 있었으면 아이콘으로(감춘 요소에 남지 않게)
  AGF.el.hidden = true;
  AGF.open = false;
  const pane = $("paneAgent");
  if (pane && pane.parentNode === AGF.body) pane.hidden = true;
  agentFloatSync(true);
  if (had && $("agentBtn")) $("agentBtn").focus({ preventScroll: true });
}

// 자리 바꾸기 — true = 패널 탭(「대시보드」 옆) · false = 떠 있는 창. 이 브라우저에 기억
function agentDockSet(panel) {
  agfDock = !!panel;
  try { localStorage.setItem(AGF_DOCK_KEY, agfDock ? "panel" : "float"); } catch { /* 기억만 안 함 */ }
  const pane = $("paneAgent"), had = !!(document.activeElement && document.activeElement.closest && document.activeElement.closest("#agentFloat, #paneAgent")); // 누른 단추가 옮겨지거나 감춰진다 — 초점을 새 자리의 짝으로
  if (agfDock) {
    if (AGF.el) { AGF.el.hidden = true; AGF.open = false; }
    const moved = agfPaneTo(false);
    if (toolShown("Agent")) { const cur = $("panel").dataset.tool; if (cur && cur !== "Agent") AGF.prev = cur; showTab("Agent"); if (moved) agfTalkEnd(); } // prev — 아이콘을 다시 누르면 패널이 보이던 도구로
    else { if (pane) pane.hidden = true; toolTabsDraw(); }
    if (had) { const t = $("tabAgent"); (t && !t.hidden ? t : $("agentBtn")).focus({ preventScroll: true }); }
    return;
  }
  if (state.id && $("panel").dataset.tool === "Agent") { const back = PANEL_BACK.find((n) => toolShown(n)); if (back) showTab(back); } // 패널은 대시보드부터 — 이제 탭이 없다
  else toolTabsDraw();
  agentFloatOpen();
  if (had && $("agentDock")) $("agentDock").focus({ preventScroll: true });
}

// 상단 바 에이전트 아이콘 — 떠 있는 창이면 여닫기 · 패널 탭이면 그 탭 ↔ 그 전 도구(작업 리스트 아이콘과 같은 꼴) · 에이전트 보기가 없는 화면(시작 화면 · docx)이면 안내 창(설정 톱니가 있다)
function agentBtnClick() {
  if (!toolShown("Agent")) { if (AGF.open) agentFloatClose(); else agentFloatOpen(); return; }
  if (!agfDock) { if (AGF.open) agentFloatClose(); else showTab("Agent"); return; }
  if (agentVisible()) showTab(AGF.prev && AGF.prev !== "Agent" && toolShown(AGF.prev) ? AGF.prev : PANEL_BACK.find((n) => toolShown(n)) || "Verify");
  else { const cur = $("panel").dataset.tool; if (cur && cur !== "Agent") AGF.prev = cur; showTab("Agent"); }
}
function agentVisible() { // 아이콘의 눌림 = 지금 에이전트(또는 안내 창)가 보이나
  if (!agfDock || !toolShown("Agent")) return AGF.open;
  return !$("panel").hidden && !colFolded("panel") && $("panel").dataset.tool === "Agent";
}

// 아이콘의 눌림 · 도움말을 맞춘다. quick 이 아니면(toolTabsDraw) 문서가 바뀐 뒤의 창도 — 문서를 닫으면 닫고, 다른 문서를 열면 그 문서의 에이전트로(패널 탭 자리의 안내 창은 닫음)
function agentFloatSync(quick) {
  const b = $("agentBtn");
  if (!b) return;
  if (typeof PEEK !== "undefined" && PEEK) { b.hidden = true; return; }
  if (!quick && AGF.open && AGF.forDoc !== (state.id || null)) {
    AGF.forDoc = state.id || null;
    if (!state.id || agfDock) agentFloatClose();
    else { const id = state.id; setTimeout(() => { if (AGF.open && state.id === id) agentFloatOpen(); }, 0); } // load 가 끝난 뒤(이 줄은 load 의 showTab 안에서 불린다)
  }
  b.setAttribute("aria-pressed", String(agentVisible()));
  b.title = `에이전트 — 문서에서 자리를 고르고 요청하면 글·표·서식을 제안하고, 워크플로우의 진행을 안내합니다 · ${agfDock ? "패널 「대시보드」 옆 탭" : "떠 있는 창"}으로 엽니다(창 머리에서 자리 바꾸기 · 톱니 = 에이전트 설정)`;
}

// ---- 자리 · 크기 ---------------------------------------------------------------------------------------------------------------
function agfPlace() { // 사람이 정한 자리가 있으면 그것(화면 안으로) · 없으면 패널(또는 2열) 바로 왼쪽에 패널과 같은 폭 · 패널 높이
  const w = AGF.el, vw = window.innerWidth, vh = window.innerHeight;
  if (!w) return;
  let x, y, wd, ht;
  if (AGF.at) ({ x, y, w: wd, h: ht } = AGF.at);
  else {
    const ws = document.querySelector(".workspace"), wr = ws ? ws.getBoundingClientRect() : null;
    const pan = $("panel"), col = $("headsDlg");
    const shown = (e) => e && !e.hidden && e.offsetWidth > 0;
    const pr = shown(pan) ? pan.getBoundingClientRect() : null, cr = shown(col) ? col.getBoundingClientRect() : null;
    const right = cr ? cr.left : pr ? pr.left : vw;
    wd = pr && pr.width > 120 ? pr.width : parseFloat(getComputedStyle(pan || document.documentElement).getPropertyValue("--panel")) || 380; // 접힌 패널(28px 띠)·닫힌 패널이면 패널의 펴진 폭
    if (vw <= 820) wd = Math.min(wd, 520); // 좁은 창(style.css 820px 아래)은 패널이 문서 아래로 내려가 창 폭 전체가 된다 — 그때는 패널 기본 폭의 한도(design.md §1 — 320~520px)까지
    const sc = $("scroller"), sr = shown(sc) ? sc.getBoundingClientRect() : null; // 문서 보기의 위 끝 — 편집 도구 줄 · 파일명 줄(오른쪽 끝의 실행 취소 · 분석 상태)은 가리지 않는다(outline_preview.js olpPlace 와 같은 까닭)
    y = (sr ? sr.top : wr && wr.height > 240 ? wr.top : 48) + 6;
    ht = (wr && wr.height > 240 ? wr.bottom : vh) - y - 6;
    x = right - wd - 6;
  }
  wd = Math.min(Math.max(300, wd), vw - 16);
  y = Math.min(Math.max(0, y), vh - 120);
  ht = Math.min(Math.max(260, ht), vh - y - 8);
  x = Math.min(Math.max(8, x), vw - wd - 8);
  Object.assign(w.style, { left: `${Math.round(x)}px`, top: `${Math.round(y)}px`, width: `${Math.round(wd)}px`, height: `${Math.round(ht)}px` });
  AGF.set = { w: Math.round(wd), h: Math.round(ht) };
}
function agfSave() { try { if (AGF.at) localStorage.setItem(AGF_AT_KEY, JSON.stringify(AGF.at)); else localStorage.removeItem(AGF_AT_KEY); } catch { /* 기억만 안 함 */ } }
function agfKeep() { const r = AGF.el.getBoundingClientRect(); AGF.at = { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; agfSave(); }
let agfSaveTimer = 0;
function agfResized() { // 오른쪽 아래 모서리로 크기를 바꿨다(CSS resize) — 정한 크기와 다르면 기억
  const w = AGF.el;
  if (!w || w.hidden || !AGF.set) return;
  const r = w.getBoundingClientRect();
  if (!r.width || (Math.abs(r.width - AGF.set.w) < 2 && Math.abs(r.height - AGF.set.h) < 2)) return;
  AGF.set = { w: Math.round(r.width), h: Math.round(r.height) };
  clearTimeout(agfSaveTimer);
  agfSaveTimer = setTimeout(() => { if (AGF.open) agfKeep(); }, 250);
}
function agfDrag(w, head) { // 머리를 끌어 옮긴다 — 화면 안에 머물게(outline_preview.js olpDrag 와 같은 꼴) · 3px 넘게 움직였을 때만 자리를 기억
  head.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button, a")) return;
    e.preventDefault();
    const r = w.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top, x0 = e.clientX, y0 = e.clientY;
    let moved = false;
    head.setPointerCapture(e.pointerId);
    document.body.classList.add("agf-moving");
    const move = (ev) => {
      if (!moved && Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 3) return;
      moved = true;
      w.style.left = `${Math.round(Math.min(Math.max(80 - r.width, ev.clientX - dx), window.innerWidth - 80))}px`;
      w.style.top = `${Math.round(Math.min(Math.max(0, ev.clientY - dy), window.innerHeight - 40))}px`;
    };
    const up = () => {
      head.removeEventListener("pointermove", move);
      head.removeEventListener("pointerup", up);
      head.removeEventListener("pointercancel", up);
      document.body.classList.remove("agf-moving");
      if (moved) agfKeep();
    };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", up);
    head.addEventListener("pointercancel", up);
  });
}

// ---- 묶기 -------------------------------------------------------------------------------------------------------------------------
(function agfBind() {
  const b = $("agentBtn");
  if (b) b.onclick = agentBtnClick;
  window.addEventListener("resize", () => { if (AGF.open) agfPlace(); }); // 창이 줄면 화면 안으로(사람이 정한 자리가 없으면 패널 옆으로 다시)
  agentFloatSync(true);
})();
