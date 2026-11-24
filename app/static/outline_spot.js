"use strict";
/* 줄 오른쪽의 서식 아이콘(spec_hwpx_웹편집 ② §8-14) — 도구 줄의 「서식」 묶음을 켜 둔 동안, 문서에서 헤딩 · 본문 줄을 누르면 그 줄 높이의 쪽 **오른쪽 여백**에 뜨는 작은 아이콘 띠(.os-bar).
   2026-11-24 사용자 "서식에 도그를 켜놓고 문서상에서 레터나, 템플릿 변환할 수 있는 아이콘을 헤딩/본문을 클릭하면 우측에 아이콘이 뜨고 거기서 작업을 수행할 수 있도록 해줘".
   · 새 기능이 아니라 **입구**다 — 누르면 이미 있는 창 · 메뉴를 그 줄로 연다:
       헤딩 줄(개요 줄)   「헤딩 고치기」        = outline_tune.js outlineTuneOpen(그 줄 아래 창 — 레터 · 빈칸 · 앞 여백 · 2번째 줄 + 범위)
                          「템플릿 나누기 · 합치기」 = outline_cut.js olcOpen(왼쪽 여백 라벨 「T1 L4」 의 오른쪽 단추 메뉴와 같은 메뉴 — 여기서만 · 모두 · 레벨 범위 · 합치기 · 템플릿 관계에서 보기)
       본문 줄(개요 줄 아님) 「레터 넣기」          = para_letter.js plOpenAt(레터나 이 문서의 개요 레벨을 골라 이 문단을 헤딩으로 — 「문단 수정」 묶음의 단추와 같은 메뉴)
     괄호 줄 · 표 제목 줄처럼 「헤딩 고치기」 를 못 하는 개요 줄에는 템플릿 메뉴만 뜬다(못 하는 단추를 꺼 두지 않고 그 줄이 할 수 있는 것만).
   · 어느 줄인가 = 글쓰기 자리(커서)가 든 문단. 띠의 단추를 눌러도 커서는 그 줄에 남는다(mousedown 기본 동작을 막는다). 초점이 문서 밖(창 · 메뉴 · 옆 열)으로 가도 띠는 마지막 줄에 남는다.
   · 「서식」 묶음이 꺼져 있으면 없다(다른 묶음에서는 전처럼 레터 누르기 · 오른쪽 단추 메뉴 · 라벨 메뉴). 쪽 보기를 끄거나 인쇄하면 없다 · 둘째 면(같이 보기)에는 없다.
   · 자리(design.md §4 「줄 오른쪽의 서식 아이콘」): .sheet 에 절대 위치(문단 요소 밖 — 글 · 쪽 나눔은 안 바뀐다) · 화면 크기 고정(zoom 1/z) · 본문 오른끝에서 8px(여백이 좁으면 2px 까지 당김).
     같은 높이의 오른쪽 여백 표시(편집 구역 이름표 · 고친 곳 꼬리표 · 서식 꼬리표)는 피해 그 아래로. 「지침」 단추(place_guides.js)는 이 띠를 피해 그 아래에 선다(그 파일의 busy 목록에 .os-bar).
   다시 그리는 때: 커서가 다른 문단으로 감 · 「서식」 묶음을 켜고 끔 · 쪽이 새로 섬 · 여백 표시가 바뀜 · 문서 차례 · 개요 오버레이가 바뀜(지켜보기) · 창 크기. 배율은 app.js zoomPut 이 자리 · 여백 폭을 셈으로 맞춘다.
   app.js 가 주는 것: state · heads · $ · el · paraEl · outlineLine · gutterSync · PEEK · DEFAULT_PAGE · PX_PER_MM · oneLine.
   부르는 것(모두 typeof 검사 뒤): outline_tune.js oltLineOk · outlineTuneOpen / outline_cut.js olcOpen / para_letter.js plOpenAt. index.html 이 그 셋 다음 · place_guides.js 앞에 읽는다
   (같은 프레임에 이 띠가 먼저 서야 「지침 적기」 가 겹치지 않고 그 아래에 선다). 화면 검사: tools/smoke_outline_spot_ui.py(run_ui_gates 이름 outline_spot). */
const OSP = { key: "", pid: null, raf: 0, selRaf: 0, timer: 0, seen: "" };
const OSP_H = 22, OSP_BTN = 24; // 띠 높이 · 단추 하나의 폭(화면 px)
const OSP_ICON = {
  tune: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="1.8" y="3" width="4.2" height="4.2" rx=".7"/><path d="M1.8 11h3.4"/><path d="M8.2 13.4l.5-2.5 4.6-4.6a1.3 1.3 0 0 1 1.9 1.9l-4.6 4.6z"/></svg>',
  cut: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M1.8 8h3.4M5.2 8c2.6 0 1.8-4.2 4.8-4.2M5.2 8c2.6 0 1.8 4.2 4.8 4.2"/><rect x="10.4" y="2" width="4" height="3.6" rx=".8"/><rect x="10.4" y="10.4" width="4" height="3.6" rx=".8"/></svg>',
  letter: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="5.5" cy="6" r="2.6"/><rect x="3.2" y="10" width="4.6" height="4.6" rx=".8"/><path d="M3.4 18.5h4.2M11.5 6h9M11.5 12.3h9M11.5 18.5h9"/></svg>',
};

const osOn = () => !PEEK && !!state.id && state.tool === "style" && gutterSync();
const osKey = () => `${state.id || ""}|${state.epoch}`;

function osSelPara() { // 커서가 든 문단 — undefined = 커서가 문서 밖(띠는 마지막 줄에 그대로) · null = 문서 안이지만 문단이 아님
  const s = getSelection();
  const n = s && s.rangeCount ? s.anchorNode : null;
  const e = n && (n.nodeType === 1 ? n : n.parentElement);
  if (!e || !e.closest || !e.closest("#doc")) return undefined;
  return e.closest("#doc .para[data-id]") || null;
}

function osKinds(p) { // 그 줄에 띄울 단추 — 헤딩 줄: 헤딩 고치기 · 템플릿 메뉴 / 본문 줄: 레터 넣기
  const ol = state.format === "hwpx" ? outlineLine(p) : null;
  if (!ol) return typeof plOpenAt === "function" ? [{ kind: "letter" }] : [];
  const out = [];
  if (typeof oltLineOk === "function" && typeof outlineTuneOpen === "function" && oltLineOk(p)) out.push({ kind: "tune", ol });
  if (ol.tpl != null && typeof olcOpen === "function") out.push({ kind: "cut", ol });
  return out;
}

function osButton(pid, k) {
  const b = el("button", `os-b os-${k.kind}`);
  b.type = "button";
  b.dataset.os = k.kind;
  b.innerHTML = OSP_ICON[k.kind];
  const ol = k.ol, name = ol ? `T${ol.no} L${ol.level}` : "";
  const lt = ol && ol.letter ? ` 「${oneLine(ol.letter).slice(0, 8)}」` : "";
  let label, tip;
  if (k.kind === "tune") {
    label = `헤딩 고치기 — ${name}${lt}`;
    tip = "이 줄의 레터 · 레터 앞뒤 빈칸 · 앞 여백 · 2번째 줄을 고치고, 어디까지 걸지(이 문단만 · 서식 전체 변경 · 새 템플릿으로 나누기)를 고릅니다";
  } else if (k.kind === "cut") {
    label = `템플릿 나누기 · 합치기 — ${name}`;
    tip = "이 줄부터 새 템플릿으로 나누기(여기서만 · 이 레벨 모두 · 레벨 범위 고르기) · 합치기 · 템플릿 관계에서 보기 — 왼쪽 여백 라벨의 오른쪽 단추 메뉴와 같습니다(문서는 안 바뀌고 템플릿만)";
    b.setAttribute("aria-haspopup", "menu");
  } else {
    label = "레터 넣기 — 이 문단을 헤딩으로";
    tip = "레터(① 1. □ o - …)나 이 문서의 개요 레벨(레터 + 그 레벨의 서식 — 그 템플릿의 줄이 됩니다)을 고릅니다";
    b.dataset.plAnchor = "1"; // para_letter.js — 이 단추를 다시 누르면 메뉴가 닫힌다
    b.setAttribute("aria-haspopup", "dialog");
  }
  b.title = `${label}\n${tip}`;
  b.setAttribute("aria-label", label);
  b.onmousedown = (e) => e.preventDefault(); // 커서를 그 줄에 둔 채로(누르는 사이 띠가 사라지지 않게)
  b.onclick = (e) => { e.stopPropagation(); osRun(pid, k.kind, b); };
  return b;
}

function osRun(pid, kind, btn) {
  const p = paraEl(pid);
  if (!p || state.busy) return;
  if (kind === "tune") { outlineTuneOpen(p); return; }
  if (kind === "letter") { plOpenAt(btn, p); return; }
  const ol = outlineLine(p);
  if (!ol) return;
  const r = btn.getBoundingClientRect();
  olcOpen({ tpl: String(ol.tpl), level: ol.level, para: pid, paras: [pid] }, { clientX: Math.round(r.left), clientY: Math.round(r.bottom + 4) });
}

function osMgr(sheet, z) { // 그 쪽 오른쪽 여백 폭(화면 px — place_guides.js · doc_diff.js 와 같은 셈)
  const sec = (state.sections && state.sections[+sheet.dataset.sec]) || DEFAULT_PAGE;
  return Math.round(((sec.marginsMm && sec.marginsMm.r) || 0) * PX_PER_MM * z * 10) / 10;
}

function osPaint() {
  clearTimeout(OSP.timer);
  OSP.timer = 0;
  for (const e of document.querySelectorAll("#doc .sheet > .os-bar")) e.remove();
  OSP.seen = osSeen();
  if (!osOn()) return;
  if (OSP.key !== osKey()) { OSP.key = osKey(); const q = osSelPara(); OSP.pid = q ? q.dataset.id : null; } // 다른 문서 — 앞 문서의 줄을 잇지 않는다(문단 id 는 문서마다 겹친다)
  const p = OSP.pid ? paraEl(OSP.pid) : null;
  const sheet = p && p.closest("#doc .sheet");
  if (!sheet) return;
  const kinds = osKinds(p);
  const r = p.getBoundingClientRect();
  if (!kinds.length || !r.height) return; // 감춘 요소(엑셀식 보기로 바꾼 표 안 등)
  const sr = sheet.getBoundingClientRect(), z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1, mgr = osMgr(sheet, z);
  let top = Math.round(r.top - sr.top);
  for (let moved = true, n = 0; moved && n < 20; n += 1) { // 같은 높이의 다른 표시는 피해 그 아래로
    moved = false;
    for (const e of sheet.querySelectorAll(":scope > .gz-tag, :scope > .dd-tag, :scope > .fm-tag")) {
      const b = e.getBoundingClientRect();
      if (b.height && top < b.bottom - sr.top && top + OSP_H > b.top - sr.top) { top = Math.ceil(b.bottom - sr.top) + 2; moved = true; }
    }
  }
  const bar = el("div", "os-bar");
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "이 줄의 서식 도구");
  bar.contentEditable = "false";
  bar.dataset.para = OSP.pid;
  for (const k of kinds) bar.append(osButton(OSP.pid, k));
  const w = kinds.length * OSP_BTN + 6;
  bar.style.zoom = String(1 / z); // 화면 크기 고정 · 자리는 화면 px(app.js zoomPut 이 배율을 뒤에서 바꿀 때 자리 · 여백 폭을 같이 맞춘다)
  bar.style.setProperty("--mgr", `${mgr}px`);
  bar.style.setProperty("--osx", `${Math.max(2, Math.min(8, Math.floor(mgr - w - 3)))}px`);
  bar.style.top = `${top}px`;
  sheet.append(bar);
}

function osDraw() { // 다시 그리기를 잡는다(한 프레임에 한 번)
  if (OSP.raf) return;
  OSP.raf = requestAnimationFrame(() => { OSP.raf = 0; osSync(true); });
}

function osSync(force = false) { // 커서가 든 문단이 바뀌었으면(또는 force) 다시 그린다 — 치는 동안은 그대로
  if (!osOn()) { if (force || document.querySelector("#doc .sheet > .os-bar")) osPaint(); return; }
  const p = osSelPara();
  const pid = p === undefined ? OSP.pid : p ? p.dataset.id : null;
  if (!force && pid === OSP.pid && OSP.key === osKey()) return;
  if (OSP.key === osKey()) OSP.pid = pid; // 다른 문서면 osPaint 가 지금 커서로 다시 정한다
  osPaint();
}

// 지켜보기 — 화면 값만 본다: 문서 · 문서 차례 · 개요 오버레이 · 묶음 · 쪽 보기가 바뀌었으면 다시 그린다(app.js 에 끼어들지 않는다 — place_guides.js 와 같은 방식)
const osSeen = () => `${osKey()}|${state.serverRev}|${state.tool}|${heads.outline ? 1 : 0}|${gutterSync() ? 1 : 0}`;
let osOutline = null;
function osWatch() {
  if (document.hidden || PEEK) return;
  const ol = heads.outline || null;
  if (osSeen() === OSP.seen && ol === osOutline) return;
  osOutline = ol;
  osDraw();
}

(function osBind() {
  if (PEEK) return;
  setInterval(osWatch, 700);
  document.addEventListener("selectionchange", () => { if (!OSP.selRaf && state.tool === "style") OSP.selRaf = requestAnimationFrame(() => { OSP.selRaf = 0; osSync(); }); });
  window.addEventListener("resize", osDraw);
  const set = $("tbStyle"), doc = $("doc");
  if (typeof MutationObserver !== "function") return;
  if (set) new MutationObserver(osDraw).observe(set, { attributes: true, attributeFilter: ["hidden"] }); // 「서식」 묶음을 켜고 끔(app.js toolSetShow) — 바로
  if (doc) { // 쪽이 새로 섬(다시 나눔 · 다시 읽음) · 여백 표시가 생기거나 없어짐 — 자리를 다시(자기 띠 · 「지침」 단추는 무시)
    const OTHER = ["sheet", "tpl-mark", "gz-tag", "dd-tag", "fm-tag"];
    const hit = (nodes) => { for (const x of nodes) if (x.nodeType === 1 && OTHER.some((c) => x.classList.contains(c))) return true; return false; };
    new MutationObserver((recs) => {
      if (state.tool !== "style" || OSP.timer) return;
      for (const m of recs) if (m.target === doc || hit(m.addedNodes) || hit(m.removedNodes)) { OSP.timer = setTimeout(osPaint, 60); return; }
    }).observe(doc, { childList: true, subtree: true });
  }
})();
