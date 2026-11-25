/* 패널 설명: 마우스·키보드·터치로 같은 내용을 읽는 단일 도움말. */
let panelHelpOwner = null, panelHelpTip = null, panelHelpTimer = null, panelHelpPinned = false;
// 고치는 중(panelHelpEdit — 풍선 안에 폼): 마우스가 떠나거나 · 초점이 옮거나 · 밖을 누르거나 · 굴려도 닫지 않는다(고치던 글을 잃지 않게). Esc · 폼의 「취소」 · 저장이 닫는다
let panelHelpEditing = false;

function panelHelpClose() {
  clearTimeout(panelHelpTimer);
  if (panelHelpOwner) {
    const ids = (panelHelpOwner.getAttribute("aria-describedby") || "").split(/\s+/).filter(id => id && id !== "panelHelpTooltip");
    if (ids.length) panelHelpOwner.setAttribute("aria-describedby", ids.join(" "));
    else panelHelpOwner.removeAttribute("aria-describedby");
  }
  panelHelpOwner = null;
  panelHelpPinned = false;
  panelHelpEditing = false;
  if (panelHelpTip) {
    panelHelpTip.setAttribute("role", "tooltip");
    panelHelpTip.classList.remove("is-editing");
    if (panelHelpTip.hasAttribute("popover") && panelHelpTip.matches(":popover-open")) panelHelpTip.hidePopover();
    panelHelpTip.hidden = true;
  }
}

function panelHelpShow(button) {
  clearTimeout(panelHelpTimer);
  if (!button.isConnected || panelHelpEditing) return; // 고치는 중에는 다른 도움말이 그 폼을 덮지 않는다
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
  const raw = button.dataset.help || "";
  if (button.dataset.helpKind) panelHelpTip.dataset.helpKind = button.dataset.helpKind;
  else delete panelHelpTip.dataset.helpKind;
  if (button.dataset.helpRows) {
    // 2026-11-23 사용자 「메모 설명이나 이런게 좀 정리되어 있지 않고 읽기도 어려움」 — Antigravity
    panelHelpTip.classList.add("is-rows");
    if (button.dataset.helpTitle) panelHelpTip.dataset.helpTitle = button.dataset.helpTitle;
    else delete panelHelpTip.dataset.helpTitle;
    const frag = document.createDocumentFragment(), lines = raw.split("\n");
    let sawCore = false, condStarted = false;
    for (let i = 0; i < lines.length; i++) {
      if (i > 0) frag.append(document.createTextNode("\n"));
      const line = lines[i], at = line.indexOf(" — "), row = document.createElement("div");
      row.className = "panel-help-row";
      if (at > 0) {
        const key = line.slice(0, at), val = line.slice(at + 3), core = key === "하는 일" || key === "나오는 것";
        row.dataset.helpKey = key;
        if (core) { row.classList.add("is-core"); sawCore = true; }
        else {
          row.classList.add("is-cond");
          if (sawCore && !condStarted) { row.classList.add("is-cond-start"); condStarted = true; }
        }
        const k = document.createElement("span"), sep = document.createElement("span"), v = document.createElement("span");
        k.className = "panel-help-k"; k.textContent = key;
        sep.className = "panel-help-sep"; sep.textContent = " — ";
        v.className = "panel-help-v"; v.textContent = val;
        row.append(k, sep, v);
      } else {
        const v = document.createElement("span");
        v.className = "panel-help-v"; v.textContent = line;
        row.append(v);
      }
      frag.append(row);
    }
    if (typeof button._helpEdit === "function") { // 고칠 수 있는 설명(hHelp 의 edit — 대시보드 단계 메모: dashboard.js dashMemoEdit) — 풍선 맨 아래 「고치기」
      const foot = document.createElement("div"), go = document.createElement("button");
      foot.className = "panel-help-foot";
      go.type = "button"; go.className = "panel-help-edit"; go.textContent = "고치기";
      go.onclick = (e) => { e.preventDefault(); e.stopPropagation(); button._helpEdit(); };
      foot.append(go);
      frag.append(foot);
    }
    panelHelpTip.replaceChildren(frag);
  } else {
    panelHelpTip.classList.remove("is-rows");
    delete panelHelpTip.dataset.helpTitle;
    panelHelpTip.textContent = raw;
  }
  // modal dialog 밖의 DOM 은 top layer 에 보여도 inert 하다. 설명도 같은 dialog 안에 둬야 마우스로 읽을 수 있다.
  const host = button.closest("dialog[open]") || document.body;
  if (panelHelpTip.parentElement !== host) host.append(panelHelpTip);
  panelHelpTip.hidden = false;
  panelHelpTip.scrollTop = 0;
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
  if (panelHelpEditing) return;
  panelHelpTimer = setTimeout(() => {
    if (!panelHelpPinned && document.activeElement !== panelHelpOwner && !panelHelpTip?.matches(":hover")) panelHelpClose();
  }, 150);
}

// kind = 풍선의 갈래(opt-in — 풍선에 data-help-kind 로 실린다: "end" = 대시보드 끝 글 띠의 「줄 이름 — 글」 · dashboard.js dashEndEl). 없으면 전과 같다
// edit = 고칠 수 있는 설명(rows 일 때 — 풍선 맨 아래 「고치기」 를 누르면 부른다: 그 함수가 panelHelpEdit(폼) 으로 풍선을 폼으로 바꾼다)
function hHelp(label, text, { warning = false, note = !warning, rows = false, title = "", kind = "", edit = null } = {}) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "panel-help" + (warning ? " is-warning" : "");
  b.setAttribute("aria-label", label);
  b.dataset.help = text;
  if (rows) b.dataset.helpRows = "1";
  if (title) b.dataset.helpTitle = title;
  if (kind) b.dataset.helpKind = kind;
  if (edit) b._helpEdit = edit;
  const shape = note
    ? '<path d="M5 2h8l3 3v13H4V3a1 1 0 0 1 1-1Z"/><path d="M12 2v4h4M7 9h6M7 12h6M7 15h4"/>'
    : '<circle cx="10" cy="10" r="7.5"/>' + (warning ? '<path d="M10 6v5M10 14h.01"/>' : '<path d="M10 9v5M10 6h.01"/>');
  b.innerHTML = '<svg viewBox="0 0 20 20" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + shape + '</svg>';
  b.onpointerenter = b.onfocus = () => panelHelpShow(b);
  b.onpointerleave = panelHelpLater;
  b.onblur = () => { if (panelHelpEditing) return; panelHelpPinned = false; panelHelpLater(); };
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
// 풍선을 고치는 폼으로 바꾼다(지금 뜬 풍선 — hHelp 의 edit 가 부른다). 닫기는 panelHelpClose(취소 · 저장 뒤)
function panelHelpEdit(form) {
  if (!panelHelpTip || !panelHelpOwner) return;
  clearTimeout(panelHelpTimer);
  panelHelpEditing = true;
  panelHelpPinned = true;
  panelHelpTip.setAttribute("role", "dialog");
  panelHelpTip.classList.add("is-editing");
  panelHelpTip.replaceChildren(form);
  const r = panelHelpTip.getBoundingClientRect(), edge = 10; // 폼이 넓어지거나 길어져 화면 밖으로 나가면 안으로 들인다
  if (r.right > innerWidth - edge) panelHelpTip.style.left = Math.max(edge, innerWidth - edge - r.width) + "px";
  if (r.bottom > innerHeight - edge) panelHelpTip.style.top = Math.max(edge, innerHeight - edge - r.height) + "px";
  const first = form.querySelector("textarea, input");
  if (first) first.focus();
}

document.addEventListener("pointerdown", e => {
  if (panelHelpEditing) return;
  if (panelHelpOwner && !panelHelpOwner.contains(e.target) && !panelHelpTip.contains(e.target)) panelHelpClose();
}, true);
document.addEventListener("scroll", e => {
  if (!panelHelpOwner || panelHelpEditing || panelHelpTip.contains(e.target)) return;
  if (e.target.id === "scroller" && typeof zoomQuiet === "function" && zoomQuiet()) return; // 배율을 뒤에서 바꾸며 자리를 지킨 scroll(app.js zoomStep — 보이는 것은 안 움직임)로는 안 닫는다
  panelHelpClose();
}, true);
window.addEventListener("resize", panelHelpClose);
