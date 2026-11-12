/* 패널 설명: 마우스·키보드·터치로 같은 내용을 읽는 단일 도움말. */
let panelHelpOwner = null, panelHelpTip = null, panelHelpTimer = null, panelHelpPinned = false;

function panelHelpClose() {
  clearTimeout(panelHelpTimer);
  if (panelHelpOwner) {
    const ids = (panelHelpOwner.getAttribute("aria-describedby") || "").split(/\s+/).filter(id => id && id !== "panelHelpTooltip");
    if (ids.length) panelHelpOwner.setAttribute("aria-describedby", ids.join(" "));
    else panelHelpOwner.removeAttribute("aria-describedby");
  }
  panelHelpOwner = null;
  panelHelpPinned = false;
  if (panelHelpTip) {
    if (panelHelpTip.hasAttribute("popover") && panelHelpTip.matches(":popover-open")) panelHelpTip.hidePopover();
    panelHelpTip.hidden = true;
  }
}

function panelHelpShow(button) {
  clearTimeout(panelHelpTimer);
  if (!button.isConnected) return;
  if (!panelHelpTip) {
    panelHelpTip = document.createElement("div");
    panelHelpTip.id = "panelHelpTooltip";
    panelHelpTip.className = "panel-help-tooltip";
    panelHelpTip.setAttribute("role", "tooltip");
    // dialog 위에서도 읽을 수 있도록 브라우저의 top layer 를 쓴다(팝업 창을 여는 동작은 아님).
    if (typeof panelHelpTip.showPopover === "function") panelHelpTip.setAttribute("popover", "manual");
    panelHelpTip.onpointerenter = () => clearTimeout(panelHelpTimer);
    panelHelpTip.onpointerleave = () => panelHelpLater();
    document.body.append(panelHelpTip);
  }
  if (panelHelpOwner !== button) panelHelpClose();
  panelHelpOwner = button;
  panelHelpTip.textContent = button.dataset.help;
  // modal dialog 밖의 DOM 은 top layer 에 보여도 inert 하다. 설명도 같은 dialog 안에 둬야 마우스로 읽을 수 있다.
  const host = button.closest("dialog[open]") || document.body;
  if (panelHelpTip.parentElement !== host) host.append(panelHelpTip);
  panelHelpTip.hidden = false;
  if (panelHelpTip.hasAttribute("popover") && !panelHelpTip.matches(":popover-open")) panelHelpTip.showPopover();
  const ids = new Set((button.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
  ids.add(panelHelpTip.id);
  button.setAttribute("aria-describedby", [...ids].join(" "));
  const b = button.getBoundingClientRect(), tip = panelHelpTip.getBoundingClientRect(), gap = 9, edge = 10;
  const left = Math.max(edge, Math.min(b.left, innerWidth - tip.width - edge));
  const below = b.bottom + gap;
  const top = below + tip.height <= innerHeight - edge ? below : Math.max(edge, b.top - gap - tip.height);
  panelHelpTip.style.left = left + "px";
  panelHelpTip.style.top = top + "px";
}

function panelHelpLater() {
  clearTimeout(panelHelpTimer);
  panelHelpTimer = setTimeout(() => {
    if (!panelHelpPinned && document.activeElement !== panelHelpOwner && !panelHelpTip?.matches(":hover")) panelHelpClose();
  }, 150);
}

function hHelp(label, text, { warning = false, note = !warning } = {}) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "panel-help" + (warning ? " is-warning" : "");
  b.setAttribute("aria-label", label);
  b.dataset.help = text;
  const shape = note
    ? '<path d="M5 2h8l3 3v13H4V3a1 1 0 0 1 1-1Z"/><path d="M12 2v4h4M7 9h6M7 12h6M7 15h4"/>'
    : '<circle cx="10" cy="10" r="7.5"/>' + (warning ? '<path d="M10 6v5M10 14h.01"/>' : '<path d="M10 9v5M10 6h.01"/>');
  b.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + shape + '</svg>';
  b.onpointerenter = b.onfocus = () => panelHelpShow(b);
  b.onpointerleave = panelHelpLater;
  b.onblur = () => { panelHelpPinned = false; panelHelpLater(); };
  b.onclick = (e) => {
    // summary·label 등의 안에 있어도 도움말을 누르는 것만으로 펼침/선택이 바뀌지 않는다.
    e.preventDefault();
    e.stopPropagation();
    if (panelHelpOwner === b && panelHelpPinned) panelHelpClose();
    else { panelHelpShow(b); panelHelpPinned = true; }
  };
  return b;
}

// 고정 설명은 HTML 에 명시한다. 동적 UI 는 hHelp 로 붙인다 — 글꼴/클래스로 상태·오류를 추측해 숨기지 않는다.
function hHelpMount(root = document) {
  const slots = [...root.querySelectorAll("[data-note]")];
  if (root.matches?.("[data-note]")) slots.unshift(root);
  for (const slot of slots) {
    slot.classList.add("panel-help-slot");
    const label = slot.dataset.noteLabel || "설명 노트", text = slot.dataset.note;
    const current = slot.querySelector(":scope > .panel-help");
    if (current) { current.dataset.help = text; current.setAttribute("aria-label", label); }
    else slot.replaceChildren(hHelp(label, text));
  }
}

hHelpMount();

document.addEventListener("keydown", e => {
  if (e.key === "Escape" && panelHelpOwner) { panelHelpClose(); e.preventDefault(); e.stopPropagation(); }
}, true);
document.addEventListener("pointerdown", e => {
  if (panelHelpOwner && !panelHelpOwner.contains(e.target) && !panelHelpTip.contains(e.target)) panelHelpClose();
}, true);
document.addEventListener("scroll", e => {
  if (!panelHelpOwner || panelHelpTip.contains(e.target)) return;
  if (e.target.id === "scroller" && typeof zoomQuiet === "function" && zoomQuiet()) return; // 배율을 뒤에서 바꾸며 자리를 지킨 scroll(app.js zoomStep — 보이는 것은 안 움직임)로는 안 닫는다
  panelHelpClose();
}, true);
window.addEventListener("resize", panelHelpClose);
