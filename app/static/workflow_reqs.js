// 「요구사항」 — 도구 · 단계 · 워크플로우마다 사용자가 말한 요구사항을 보고 적는 열(spec_워크플로우 ② §18-20 · design.md §24 —
// 2026-11-21 사용자 "도구, 단계, 워크플로우 에 대한 사용자 요구사항을 관리 할 수 있고 웹에서 도구에서 볼 수 있게 해줘,, 우클릭이나 아이콘을 넣고 선택하면 될듯."):
// - 여는 길 셋: ① **오른쪽 단추(우클릭)** — 줄 카드 · 목차의 워크플로우 도구 · 목차와 본문의 워크플로우 · 단계 · 도구 링크 · 단계 줄 · 절 머리 → 작은 메뉴 「요구사항 보기」 · 「요구사항 적기…」
//   ② **아이콘** — 워크플로우 · 단계 · 도구 절의 머리 · 「도구 설명」 열의 머리(지금 보는 도구) · 요구사항이 있는 줄 카드(수가 함께) ③ 상단 바의 「요구사항」(모든 요구사항 — 대상마다 묶음).
// - 보이는 곳 = 페이지 오른쪽의 열(팝업이 아니다). 그 대상의 요구사항(말한 날 · 상태 · 사용자가 한 말 · 정리 · 사양서 자리)을 보고, 새로 적고, 고치고, 상태(요청 · 반영 · 보류)를 바꾼다.
//   조립 폼이 펴져 있으면(그 폼의 오른쪽에 제 열 — 도구 설명 · 에이전트 — 이 있다) 본문을 더 좁히지 않고 그 열 위에 겹쳐 선다(닫으면 그 열이 다시 보인다) · 아니면 본문 옆의 열(목차 | 본문 | 요구사항).
// - 원본은 저장소 파일 reqs/requirements.json(서버 GET · POST /api/reqs · PUT · DELETE /api/reqs/{id} — app/user_reqs_api.py). 요구사항은 기록이다 — 적어도 스크립트 · LLM 의 동작은 바뀌지 않는다.
// 이 파일은 workflow.js 없이 혼자 선다(제 도우미 · 문서에 건 위임 · 본문을 지켜봐서 아이콘을 붙인다) — workflow.js 의 훅은 하나: helpWrap 의 `WfReqs.mount(cols, { family })`(그 폼의 틀 — 줄 카드의 도구 키에 쓴다 · 없으면 relay).
// 대상의 키 = "tool:<틀>.<줄 key>" · "common:<등록부 id>" · "stage:<워크플로우 키>.<묶음 id>" · "flow:<워크플로우 키>"(이름이 아니라 키 — 도구 이름은 사람이 고칠 수 있다).
// 다른 기능이 우클릭 메뉴에 항목을 얹는 문: `WfReqs.menu((info) => [{ label, run, off?, title? }])` — info = { target, kind, key, family, unit, name, el }.
(() => {
  "use strict";
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const $ = (id) => document.getElementById(id);
  const KIND = { tool: "도구", stage: "단계", flow: "워크플로우" };
  const PREFIX = { tool: "도구", common: "도구", stage: "단계", flow: "워크플로우" }; // 등록부에서 못 찾은 대상의 종류(키의 머리로)
  const STATES = { open: "요청", done: "반영", hold: "보류" };
  const SRC = { chat: "대화에서 받음", web: "화면에서 적음" };
  const NARROW = "(max-width: 1100px)";
  const ICON = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 4h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8z"/><path d="M8 4v4H4"/><path d="m8.5 13.5 2 2 4.5-4.5"/></svg>';
  const S = { data: null, names: {}, err: "", loading: null, on: false, target: "", name: "", edit: "", ask: "", draft: new Map(), pick: "", busy: false, note: "" }; // 페이지에 하나
  const forms = new Map(); // 폼의 칸 상자(.wf-compose-cols) → { family() } — workflow.js 의 훅이 건다
  const extra = []; // 우클릭 메뉴에 얹은 항목들(다른 기능)
  let aside = null, menu = null, topBtn = null, seen = null;

  async function call(url, opts) { // → 답(JSON) | 예외(e.status · 서버의 글 그대로)
    const r = await fetch(url, { headers: { Accept: "application/json", ...(opts && opts.body ? { "Content-Type": "application/json" } : {}) }, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error((typeof data.detail === "string" && data.detail) || `HTTP ${r.status}`); e.status = r.status; throw e; }
    return data;
  }
  function load(force) { // 요구사항 + 사람이 고친 도구 이름(있으면 — 이름을 그 이름으로 보인다)
    if (S.loading && !force) return S.loading;
    const p = (async () => {
      try {
        const [data, names] = await Promise.all([call("/api/reqs"), call("/api/tool-names").catch(() => null)]);
        S.data = data; S.err = "";
        S.names = names && names.names && typeof names.names === "object" ? names.names : {};
      } catch (e) { S.err = e.status === 404 ? "서버를 다시 켠 뒤에 볼 수 있습니다(이 서버는 아직 요구사항을 모릅니다)." : `요구사항을 읽지 못했습니다 — ${e.message}`; }
      if (S.loading !== p) return; // 더 새로 읽는 중
      decorate();
      if (S.on) draw();
    })();
    S.loading = p;
    return p;
  }
  const info = (target) => (S.data && S.data.targets && S.data.targets[target]) || null;
  const countOf = (target) => (S.data && S.data.counts && S.data.counts[target]) || { n: 0, open: 0 };
  const recent = (list) => list.map((it, i) => [it, i]).sort((a, b) => (b[0].date || "").localeCompare(a[0].date || "") || b[1] - a[1]).map((x) => x[0]); // 새로 말한 것부터(같은 날은 뒤에 적은 것부터)
  const itemsOf = (target) => (S.data ? recent(S.data.items.filter((it) => it.targets.includes(target))) : []);
  const kindOf = (target) => { const i = info(target); return i ? KIND[i.kind] || "" : PREFIX[target.slice(0, target.indexOf(":"))] || ""; };
  const nameOf = (target) => {
    if (target.startsWith("tool:")) { const n = S.names[target.slice(5)]; if (typeof n === "string" && n) return n; } // 사람이 고친 도구 이름
    return (info(target) || {}).name || target.slice(target.indexOf(":") + 1);
  };
  const stateName = (s) => (S.data && S.data.states && S.data.states[s]) || STATES[s] || s;
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

  // ---- 누른 곳 → 대상
  function formFamily(el) { // 그 줄 카드가 선 폼의 틀 — 훅이 건 것(없으면 지금 붙어 있는 폼: 조립 폼 → 단계 폼 · 그것도 없으면 relay — 목차의 도구 목록이 따르는 폼과 같은 차례)
    const cols = el && el.closest ? el.closest(".wf-compose-cols") : null, own = cols && forms.get(cols);
    if (own) return own.family();
    let pick = null;
    for (const [box, ctx] of forms) { if (!box.isConnected) { forms.delete(box); continue; } if (!pick || box.closest("#wfCompose")) pick = ctx; }
    return pick ? pick.family() : "relay";
  }
  function fromId(id) { // 절 · 묶음 · 단계 줄의 주소(# 뒤) → 대상 | ""
    id = String(id || "");
    try { id = decodeURIComponent(id); } catch { /* 그대로 */ }
    if (!id) return "";
    const steps = (S.data && S.data.steps) || {};
    if (steps[id]) return steps[id]; // 단계 줄 = 조립에 놓는 도구와 같은 줄 → 그 도구
    const ok = (t) => (S.data ? (info(t) ? t : "") : t);
    if (id.startsWith("common-")) return ok(`common:${id.slice(7).split("--")[0]}`);
    const [job, stage] = id.split("--");
    if (!/^[a-z][a-z0-9_]*$/.test(job)) return "";
    if (!S.data && !(typeof TASK_CATALOG !== "undefined" && TASK_CATALOG[job])) return "";
    return ok(stage ? `stage:${job}.${stage}` : `flow:${job}`);
  }
  const hrefId = (a) => { const v = a ? a.getAttribute("href") || "" : ""; return v.startsWith("#") ? v.slice(1) : ""; };
  function targetAt(el) { // → { target, name, family?, unit? } | null
    if (!(el instanceof Element) || el.closest(".wf-reqs, .wf-req-menu")) return null;
    const own = el.closest("[data-req]");
    if (own) return { target: own.dataset.req, name: own.dataset.reqName || "" };
    if (el.closest("input, textarea, select, [contenteditable]")) return null; // 글 칸의 메뉴(붙여넣기 …)는 그대로
    const tool = (unit, name, at) => { const family = formFamily(at); return unit && unit !== "hand" ? { target: `tool:${family}.${unit}`, name, family, unit } : null; }; // 「사람이 하는 일」 은 줄마다 사람이 적는 글이 따로 있다
    const plain = (t) => (t ? { target: t, name: "" } : null);
    const cell = el.closest(".wf-line-cell"), li = el.closest("li.wf-line");
    if (cell && li) { // 줄 카드(쌍 줄은 행의 키)
      const unit = cell.dataset.unit || (li.dataset.role === "pair" || li.dataset.role === "none" ? li.dataset.unit : ""), b = cell.querySelector(".wf-line-name > b");
      return unit ? tool(unit, b ? b.textContent : "", cell) : null;
    }
    const nav = el.closest("button.wf-nav-tool[data-tool]");
    if (nav) { const nm = nav.querySelector(".wf-nav-tool-name"); return tool(nav.dataset.tool, nm ? nm.textContent : "", null); }
    const item = el.closest("button.wf-help-item[data-help-go]");
    if (item) { const b = item.querySelector("b"); return tool(item.dataset.helpGo, b ? b.textContent : "", item); }
    const help = el.closest(".wf-help-name"), unitBox = help && help.closest(".wf-help-unit[data-unit]");
    if (unitBox) return tool(unitBox.dataset.unit, "", unitBox);
    if (el.closest(".wf-help, .wf-agents")) return null; // 설명 · 에이전트 열의 글(골라서 복사 …)은 브라우저의 메뉴 그대로
    const a = el.closest("a[href]");
    if (a) return plain(fromId(hrefId(a)));
    const sum = el.closest("details.wf-step > summary");
    if (sum) return plain(fromId(sum.parentElement.dataset.wfPath));
    const stage = el.closest(".wf-stage-head"), sli = stage && stage.closest("li.wf-stage[id]");
    if (sli) return plain(fromId(sli.id));
    const h2 = el.closest(".wf-sec > h2"), sec = h2 && h2.parentElement;
    if (sec && sec.id && (sec.classList.contains("wf-task") || sec.classList.contains("wf-common"))) return plain(fromId(sec.id));
    const dh = el.closest(".wf-diagram-head h2");
    if (dh) return plain(diagramTarget());
    return null;
  }
  function diagramTarget() { // 다이어그램 보기가 지금 보이는 워크플로우 · 단계 · 도구
    const dg = $("wfDiagram"), a = dg && dg.querySelector("a.wf-stage-link[href], a.wf-node[href]");
    return fromId((a ? hrefId(a) : decodeURIComponent(location.hash.slice(1))).split("--")[0]);
  }

  // ---- 우클릭 메뉴
  function menuClose() { if (menu) { menu.remove(); menu = null; } }
  function menuOpen(x, y, at, el) {
    menuClose();
    const cut = at.target.indexOf(":"), kind = at.target.slice(0, cut), key = at.target.slice(cut + 1), known = info(at.target), c = countOf(at.target);
    const name = at.name || nameOf(at.target), what = kindOf(at.target), back = document.activeElement;
    menu = h("div", "wf-req-menu");
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", `${what} 「${name}」`);
    menu.append(h("div", "wf-req-menu-head", `${what} · ${name}`));
    const add = (label, run, off, title) => { const b = h("button", "", label); b.type = "button"; b.setAttribute("role", "menuitem"); b.disabled = !!off; if (title) b.title = title; b.addEventListener("click", () => { menuClose(); run(); }); menu.append(b); return b; };
    add(`요구사항 보기${c.n ? ` — ${c.n}건${c.open ? ` · 요청 ${c.open}` : ""}` : ""}`, () => open(at.target, name));
    const off = S.err || (S.data && !known ? "등록부에 없는 대상입니다" : "");
    add("요구사항 적기…", () => open(at.target, name, true), !!off, off);
    for (const fn of extra) { // 다른 기능이 얹은 항목
      let more = [];
      try { more = fn({ target: at.target, kind, key, family: at.family || "", unit: at.unit || "", name, el }) || []; } catch { more = []; }
      for (const m of more) if (m && typeof m.label === "string" && typeof m.run === "function") add(m.label, m.run, m.off, m.title);
    }
    menu.append(h("div", "wf-req-menu-foot", "Shift + 오른쪽 단추 = 브라우저의 메뉴"));
    menu.back = back instanceof HTMLElement ? back : null;
    menu.at = performance.now();
    document.body.append(menu);
    const r = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(4, Math.min(x, window.innerWidth - r.width - 4))}px`;
    menu.style.top = `${Math.max(4, Math.min(y, window.innerHeight - r.height - 4))}px`;
    const first = menu.querySelector("button:not(:disabled)");
    if (first) first.focus({ preventScroll: true });
  }
  document.addEventListener("contextmenu", (e) => {
    if (e.shiftKey) return; // Shift + 오른쪽 단추 = 브라우저의 메뉴 그대로
    const at = targetAt(e.target);
    if (!at) { menuClose(); return; }
    e.preventDefault();
    menuOpen(e.clientX, e.clientY, at, e.target);
  });
  document.addEventListener("pointerdown", (e) => { if (menu && !menu.contains(e.target)) menuClose(); }, true);
  document.addEventListener("keydown", (e) => {
    if (menu) {
      if (e.key === "Escape") { e.preventDefault(); const back = menu.back; menuClose(); if (back && back.isConnected) back.focus({ preventScroll: true }); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const list = [...menu.querySelectorAll("button:not(:disabled)")], i = list.indexOf(document.activeElement);
      if (!list.length) return;
      e.preventDefault();
      list[(i + (e.key === "ArrowDown" ? 1 : list.length - 1)) % list.length].focus();
      return;
    }
    if (e.key === "Escape" && S.on && aside && aside.contains(document.activeElement) && !S.edit && !S.ask) { e.preventDefault(); close(); } // 열 안에서 Esc = 닫기(고치는 중 · 지울지 묻는 중이면 그것부터 — 아래 itemEl)
  });
  window.addEventListener("blur", menuClose);
  window.addEventListener("resize", () => { menuClose(); place(); });
  document.addEventListener("scroll", () => { if (menu && performance.now() - menu.at > 250) menuClose(); }, true); // 스크롤하면 닫는다 — 막 띄운 때의 것(누른 줄을 화면에 들이느라 난 스크롤이 늦게 온다)은 빼고

  // ---- 아이콘 — 본문 · 목차를 다시 그릴 때마다 붙인다(지켜보기). 단추(절 머리 · 「도구 설명」 열의 머리 · 요구사항이 있는 줄 카드) · 링크 안에서는 단추 구실의 span(다이어그램의 묶음 머리)
  function iconEl(target, name, tag) {
    const b = h(tag || "button", "wf-req-ico");
    if (b.tagName === "BUTTON") b.type = "button"; else { b.setAttribute("role", "button"); b.tabIndex = 0; b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); open(target, name); } }); }
    b.dataset.req = target;
    if (name) b.dataset.reqName = name;
    b.innerHTML = ICON;
    b.append(h("span", "wf-req-n"));
    b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); open(target, name); });
    mark(b);
    return b;
  }
  function mark(b) { // 수 · 풍선 글 · 지금 열에 보이는 대상인가
    const c = countOf(b.dataset.req), n = b.querySelector(".wf-req-n");
    if (n) n.textContent = c.n ? String(c.n) : "";
    b.dataset.n = String(c.n);
    if (c.open) b.dataset.open = "1"; else delete b.dataset.open;
    b.title = c.n ? `요구사항 ${c.n}건${c.open ? ` · 요청 ${c.open}건` : ""} — 눌러서 보기` : "요구사항 — 눌러서 보고 적기";
    b.setAttribute("aria-label", b.title);
    b.setAttribute("aria-pressed", S.on && S.target === b.dataset.req ? "true" : "false");
  }
  function marks() {
    for (const b of document.querySelectorAll(".wf-req-ico")) mark(b);
    if (!topBtn) return;
    const n = S.data ? S.data.items.length : 0, o = S.data ? S.data.items.filter((it) => it.state === "open").length : 0;
    topBtn.querySelector(".wf-req-n").textContent = n ? String(n) : "";
    topBtn.title = `모든 요구사항${n ? ` ${n}건${o ? ` · 요청 ${o}건` : ""}` : ""} — 도구 · 단계 · 워크플로우마다`;
    topBtn.setAttribute("aria-pressed", S.on && !S.target ? "true" : "false");
  }
  const iconIn = (host) => [...host.children].find((x) => x.classList.contains("wf-req-ico")) || null;
  function put(host, target, name, before, tag) { // 그 머리에 아이콘 하나(같은 대상이면 그대로)
    if (!host) return;
    const old = iconIn(host);
    if (old && old.dataset.req === target) return;
    if (old) old.remove();
    if (!target) return;
    const b = iconEl(target, name, tag);
    if (before && before.parentElement === host) host.insertBefore(b, before); else host.append(b);
  }
  const putIf = (host, target, name) => put(host, target && countOf(target).n ? target : "", name); // 요구사항이 있을 때만 서는 아이콘(줄 카드 — 자리가 좁다: 없으면 오른쪽 단추로)
  function decorate() {
    const main = $("wfMain"), nav = $("wfNav");
    if (!main) return;
    for (const sec of main.querySelectorAll("section.wf-task[id], section.wf-common[id]")) put(sec.querySelector(":scope > h2"), fromId(sec.id), ""); // 목록 보기 — 워크플로우 · 단계 · 도구 절의 머리
    for (const li of main.querySelectorAll("li.wf-stage[id]")) put(li.querySelector(".wf-stage-head > h3"), fromId(li.id), ""); // 그 워크플로우의 단계 묶음
    const dg = $("wfDiagram");
    if (dg) { // 다이어그램 보기 — 머리 · 묶음 머리(링크 안) · 지금 보는 단계 줄(조립에 놓는 도구와 같은 줄일 때)
      put(dg.querySelector(".wf-diagram-head h2"), diagramTarget(), "");
      for (const a of dg.querySelectorAll("a.wf-stage-link[href]")) put(a, fromId(hrefId(a)), "", a.querySelector("small"), "span");
      const cur = dg.querySelector("a.wf-node[aria-current='step']"), id = cur ? hrefId(cur) : "", t = S.data && S.data.steps ? S.data.steps[id] || "" : "";
      put(dg.querySelector("#wfDetail > .wf-badges"), t, "");
    }
    for (const box of main.querySelectorAll("aside.wf-help")) { // 「도구 설명」 열의 머리 — 지금 보는 도구
      const head = box.querySelector(":scope > .wf-help-head"), unit = box.dataset.unit || "";
      put(head, unit && unit !== "hand" ? `tool:${formFamily(box)}.${unit}` : "", "", head && head.querySelector(".wf-help-back"));
    }
    for (const cell of main.querySelectorAll("li.wf-line .wf-line-cell")) { // 줄 카드 — 요구사항이 있는 도구만
      const li = cell.closest("li.wf-line"), unit = cell.dataset.unit || (li.dataset.role === "pair" || li.dataset.role === "none" ? li.dataset.unit : ""), tags = cell.querySelector(".wf-line-name > .wf-badges");
      if (tags) putIf(tags, unit && unit !== "hand" ? `tool:${formFamily(cell)}.${unit}` : "", "");
    }
    if (nav) for (const b of nav.querySelectorAll("button.wf-nav-tool[data-tool]")) { // 목차의 워크플로우 도구 — 요구사항이 있으면 수(단추 안이라 누르는 것은 오른쪽 단추로)
      const tags = b.querySelector(".wf-nav-tool-tags"), unit = b.dataset.tool, c = unit && unit !== "hand" ? countOf(`tool:${formFamily(null)}.${unit}`) : { n: 0, open: 0 };
      let dot = tags ? tags.querySelector(".wf-req-dot") : null;
      if (!tags) continue;
      if (!c.n) { if (dot) dot.remove(); continue; }
      if (!dot) { dot = h("span", "wf-req-dot"); tags.append(dot); }
      if (dot.textContent !== String(c.n)) dot.textContent = String(c.n);
      if (c.open) dot.dataset.open = "1"; else delete dot.dataset.open;
      dot.title = `요구사항 ${c.n}건${c.open ? ` · 요청 ${c.open}건` : ""} — 오른쪽 단추로 눌러 봅니다`;
    }
    marks();
    place();
  }
  function watch() {
    if (seen) return;
    let due = 0;
    seen = new MutationObserver(() => { if (!due) due = requestAnimationFrame(() => { due = 0; decorate(); }); });
    for (const id of ["wfMain", "wfNav"]) { const el = $(id); if (el) seen.observe(el, { childList: true, subtree: true }); }
    decorate();
  }
  function topMount() { // 상단 바의 「요구사항」 — 모든 요구사항
    const top = document.querySelector(".wf-top"), view = top && top.querySelector(".wf-view");
    if (!top || topBtn) return;
    topBtn = h("button", "btn sm wf-req-top");
    topBtn.type = "button";
    topBtn.innerHTML = ICON;
    topBtn.append(document.createTextNode("요구사항"), h("span", "wf-req-n"));
    topBtn.addEventListener("click", () => (S.on && !S.target ? close() : open("", "")));
    if (view) top.insertBefore(topBtn, view); else top.append(topBtn);
    marks();
  }

  // ---- 열
  function ensure() {
    if (aside && aside.isConnected) return aside;
    const wrap = document.querySelector(".wf-wrap");
    if (!wrap) return null;
    aside = h("aside", "wf-reqs");
    aside.id = "wfReqs";
    aside.setAttribute("aria-label", "요구사항");
    aside.hidden = true;
    wrap.append(aside);
    return aside;
  }
  function place() { // 조립 폼(오른쪽에 제 열이 있다)이 보이거나 창이 좁으면 겹쳐 서고, 아니면 본문 옆의 열
    if (!aside) return;
    const wrap = document.querySelector(".wf-wrap"), over = matchMedia(NARROW).matches || [...document.querySelectorAll("#wfMain .wf-compose-cols")].some((x) => x.getClientRects().length > 0);
    document.body.classList.toggle("wf-reqs-over", S.on && over);
    if (wrap && S.on) aside.style.setProperty("--wf-reqs-top", `${Math.round(wrap.getBoundingClientRect().top)}px`);
  }
  function open(target, name, write) {
    if (!ensure()) return;
    S.on = true; S.target = target || ""; S.name = name || ""; S.edit = ""; S.ask = ""; S.note = "";
    aside.hidden = false;
    document.body.classList.add("wf-reqs-on");
    place();
    draw();
    const focus = () => { const t = aside.querySelector(write ? ".wf-reqs-add textarea" : ".wf-reqs-head h3"); if (t) t.focus({ preventScroll: true }); };
    focus();
    if (write) load(true).then(() => { if (S.on && S.target === (target || "") && (document.activeElement === document.body || aside.contains(document.activeElement))) focus(); });
    else load(true);
  }
  function close() {
    S.on = false;
    if (aside) aside.hidden = true;
    document.body.classList.remove("wf-reqs-on", "wf-reqs-over");
    marks();
  }
  async function act(fn, done) { // 저장 — 끝나면 다시 읽는다
    if (S.busy) return;
    S.busy = true; S.note = "";
    try { await fn(); if (done) done(); }
    catch (e) { S.note = `저장하지 못했습니다 — ${e.message}`; }
    S.busy = false;
    await load(true);
    if (S.on) draw();
  }
  function field(label, el) { const l = h("label", "wf-reqs-field"); l.append(h("span", "", label), el); return l; }
  function stateSel(value, onChange) {
    const sel = h("select", "wf-reqs-state-sel");
    for (const k of Object.keys((S.data && S.data.states) || STATES)) { const o = h("option", "", stateName(k)); o.value = k; sel.append(o); }
    sel.value = value;
    sel.setAttribute("aria-label", "상태");
    if (onChange) sel.addEventListener("change", () => onChange(sel.value));
    return sel;
  }
  function chipTo(target, text) { // 다른 대상으로 가는 칩
    const i = info(target), b = h("button", "wf-chip wf-reqs-to", text || `${i ? KIND[i.kind] || "" : "없어진 대상"} · ${nameOf(target)}`);
    b.type = "button";
    b.dataset.to = target;
    if (i && i.group) b.title = i.group;
    b.addEventListener("click", () => open(target, ""));
    return b;
  }
  function editEl(it) { // 항목 고치기 — 그 자리에서
    const box = h("li", "wf-reqs-item wf-reqs-editing"), said = h("textarea"), note = h("textarea"), spec = h("input"), date = h("input"), state = stateSel(it.state), acts = h("div", "wf-reqs-acts");
    const max = (S.data && S.data.max) || {};
    said.value = it.said; said.rows = 4; said.maxLength = max.said || 2000;
    note.value = it.note; note.rows = 3; note.maxLength = max.note || 2000; note.placeholder = "어떻게 정했는지 · 어디에 반영했는지";
    spec.value = it.spec; spec.maxLength = max.spec || 200; spec.placeholder = "예: spec_워크플로우 ② §18-17";
    date.type = "date"; date.value = it.date;
    const save = h("button", "btn sm primary", "저장"), cancel = h("button", "btn sm", "취소");
    save.type = cancel.type = "button";
    save.addEventListener("click", () => act(() => call(`/api/reqs/${encodeURIComponent(it.id)}`, { method: "PUT", body: JSON.stringify({ said: said.value, note: note.value, spec: spec.value, date: date.value, state: state.value }) }), () => { S.edit = ""; }));
    cancel.addEventListener("click", () => { S.edit = ""; draw(); });
    box.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel.click(); } });
    acts.append(save, cancel);
    box.dataset.id = it.id;
    box.append(field("사용자가 한 말", said), field("정리", note), field("사양서 자리", spec), field("말한 날", date), field("상태", state), acts);
    return box;
  }
  function itemEl(it, here) { // 항목 하나 — 말한 날 · 상태 · 한 말 · 정리 · 사양서 자리 · 함께 가리키는 곳
    if (S.edit === it.id) return editEl(it);
    const li = h("li", "wf-reqs-item"), top = h("div", "wf-reqs-item-top"), acts = h("div", "wf-reqs-acts");
    li.dataset.id = it.id; li.dataset.state = it.state;
    top.append(h("span", "wf-reqs-date", it.date || "날짜 없음"), h("span", `wf-reqs-state wf-reqs-${STATES[it.state] ? it.state : "open"}`, stateName(it.state)), h("span", "wf-reqs-src", SRC[it.src] || ""));
    li.append(top, h("blockquote", "wf-reqs-said", it.said));
    if (it.note) { const p = h("p", "wf-reqs-note"); p.append(h("b", "", "정리"), document.createTextNode(it.note)); li.append(p); }
    if (it.spec) { const p = h("p", "wf-reqs-spec"); p.append(h("b", "", "사양서"), document.createTextNode(it.spec)); li.append(p); }
    const others = it.targets.filter((t) => t !== here);
    if (others.length) { const p = h("div", "wf-reqs-others"); p.append(h("b", "", here ? "함께 가리키는 곳" : "대상"), ...others.map((t) => chipTo(t))); li.append(p); }
    if (S.ask === it.id) { // 지우기 — 그 자리에서 한 번 더 묻는다
      const yes = h("button", "btn sm danger", "지우기"), no = h("button", "btn sm", "취소");
      yes.type = no.type = "button";
      yes.addEventListener("click", () => act(() => call(`/api/reqs/${encodeURIComponent(it.id)}`, { method: "DELETE" }), () => { S.ask = ""; }));
      no.addEventListener("click", () => { S.ask = ""; draw(); });
      acts.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); no.click(); } });
      acts.append(h("span", "wf-reqs-ask", "이 요구사항을 지울까요?"), yes, no);
    } else {
      const sel = stateSel(it.state, (v) => act(() => call(`/api/reqs/${encodeURIComponent(it.id)}`, { method: "PUT", body: JSON.stringify({ state: v }) })));
      const ed = h("button", "btn sm", "고치기"), del = h("button", "btn sm", "지우기");
      ed.type = del.type = "button";
      ed.addEventListener("click", () => { S.edit = it.id; S.ask = ""; draw(); const t = aside.querySelector(".wf-reqs-editing textarea"); if (t) t.focus(); });
      del.addEventListener("click", () => { S.ask = it.id; S.edit = ""; draw(); const t = aside.querySelector(".wf-reqs-ask ~ .btn"); if (t) t.focus(); });
      acts.append(sel, ed, del);
    }
    li.append(acts);
    return li;
  }
  function addEl(target) { // 새 요구사항 — target 이 있으면 그 대상에 · 없으면(모든 요구사항) 대상을 골라서
    const box = h("div", "wf-reqs-add"), ta = h("textarea"), btn = h("button", "btn sm primary", "적기"), key = target || "*";
    let sel = null;
    if (!target) { // 대상 고르기 — 등록부의 차례(워크플로우 › 단계 › 도구)
      sel = h("select", "wf-reqs-pick");
      sel.setAttribute("aria-label", "요구사항을 적을 대상");
      sel.append(new Option("대상을 고르세요 — 워크플로우 · 단계 · 도구", ""));
      const groups = new Map();
      for (const [t, i] of Object.entries(S.data.targets)) { if (!groups.has(i.group)) { const og = h("optgroup"); og.label = i.group; groups.set(i.group, og); sel.append(og); } groups.get(i.group).append(new Option(nameOf(t), t)); }
      sel.value = S.pick && S.data.targets[S.pick] ? S.pick : "";
      sel.addEventListener("change", () => { S.pick = sel.value; sync(); });
      box.append(sel);
    }
    const sync = () => { btn.disabled = !ta.value.trim() || (!!sel && !sel.value); };
    ta.rows = 3; ta.maxLength = (S.data && S.data.max && S.data.max.said) || 2000;
    ta.placeholder = target ? `이 ${kindOf(target) || "대상"}에 바라는 것을 적으세요` : "바라는 것을 적으세요";
    ta.value = S.draft.get(key) || "";
    ta.setAttribute("aria-label", "새 요구사항");
    ta.addEventListener("input", () => { S.draft.set(key, ta.value); sync(); });
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !btn.disabled) btn.click(); });
    btn.type = "button"; btn.title = "Ctrl + Enter";
    btn.addEventListener("click", () => act(() => call("/api/reqs", { method: "POST", body: JSON.stringify({ targets: [target || sel.value], said: ta.value, date: today() }) }), () => { S.draft.delete(key); }));
    sync();
    box.append(ta, btn);
    return box;
  }
  function draw() {
    if (!aside) return;
    const keep = aside.querySelector(".wf-reqs-body"), top = keep ? keep.scrollTop : 0, was = aside.dataset.target, inside = aside.contains(document.activeElement);
    const head = h("div", "wf-reqs-head"), title = h("h3", "", "요구사항"), x = h("button", "btn sm wf-reqs-close", "닫기"), body = h("div", "wf-reqs-body");
    title.tabIndex = -1;
    x.type = "button";
    x.title = "요구사항 열 닫기 (Esc)";
    x.addEventListener("click", close);
    head.append(title, x);
    aside.dataset.target = S.target;
    const kids = [head], warn = () => { if (S.note) { const p = h("p", "wf-reqs-warn", S.note); p.setAttribute("role", "alert"); kids.push(p); } };
    if (!S.data) { const p = h("p", S.err ? "wf-reqs-off" : "wf-reqs-hint", S.err || "요구사항을 읽는 중…"); p.setAttribute("role", "status"); aside.replaceChildren(head, p); marks(); return; }
    if (S.target) { // 대상 하나
      const i = info(S.target), who = h("div", "wf-reqs-who"), list = itemsOf(S.target), all = h("button", "btn sm wf-reqs-all", "모든 요구사항");
      all.type = "button";
      all.addEventListener("click", () => open("", ""));
      who.append(h("span", "wf-reqs-kind", i ? KIND[i.kind] || "" : "없어진 대상"), h("b", "", S.name || nameOf(S.target)), ...(i && i.group && i.group !== KIND[i.kind] ? [h("span", "wf-reqs-group", i.group)] : []), all); // 묶음 이름 = 그 단계의 워크플로우 · 그 도구의 틀(종류와 같은 말이면 두 번 적지 않는다)
      kids.push(who);
      if (!list.length) body.append(h("p", "wf-reqs-hint", i ? `아직 적힌 요구사항이 없습니다. 아래에 적으면 이 ${KIND[i.kind] || "대상"}의 요구사항으로 남습니다.` : "등록부에 없는 대상입니다 — 요구사항을 적을 수 없습니다."));
      else { const ul = h("ul", "wf-reqs-list"); for (const it of list) ul.append(itemEl(it, S.target)); body.append(ul); }
      if (i && i.kind === "flow") { // 그 워크플로우의 단계에 적힌 것 — 칩으로
        const pre = `stage:${S.target.slice(5)}.`, more = Object.keys(S.data.targets).filter((t) => t.startsWith(pre) && countOf(t).n);
        if (more.length) { const p = h("div", "wf-reqs-others wf-reqs-more"); p.append(h("b", "", "이 워크플로우의 단계에 적힌 것"), ...more.map((t) => chipTo(t, `${nameOf(t)} ${countOf(t).n}건`))); body.append(p); }
      }
      kids.push(body);
      warn();
      if (i) kids.push(addEl(S.target));
      kids.push(h("p", "wf-reqs-foot", "요구사항은 기록입니다 — 적어도 도구의 동작은 바뀌지 않습니다. 저장소의 reqs/requirements.json 에 남습니다."));
    } else { // 모든 요구사항 — 위: 아직 반영 안 된 것(요청 · 보류)의 글 · 아래: 대상마다 몇 건인지(누르면 그 대상) — 같은 요구사항을 대상마다 되풀이해 보이지 않는다
      const bar = h("div", "wf-reqs-who"), all = S.data.items, left = recent(all.filter((it) => it.state !== "done"));
      bar.append(h("b", "", "모든 요구사항"), h("span", "wf-reqs-group", `${all.length}건${all.length ? ` · 반영 안 된 것 ${left.length}건` : ""}`));
      kids.push(bar);
      if (!all.length) body.append(h("p", "wf-reqs-hint", "아직 적힌 요구사항이 없습니다. 도구 · 단계 · 워크플로우를 오른쪽 단추로 눌러 「요구사항 적기…」 를 고르거나 아래에서 대상을 골라 적으세요."));
      if (left.length) {
        const sec = h("section", "wf-reqs-group-sec wf-reqs-left"), ul = h("ul", "wf-reqs-list");
        for (const it of left) ul.append(itemEl(it, ""));
        sec.append(h("h4", "", "아직 반영 안 된 것"), ul);
        body.append(sec);
      }
      const groups = new Map(), gone = [];
      for (const t of Object.keys(S.data.targets)) { // 등록부의 차례(워크플로우 › 그 워크플로우의 단계 › 단계 › 도구 › 워크플로우 도구)
        if (!countOf(t).n) continue;
        const g = info(t).group || "";
        if (!groups.has(g)) groups.set(g, []);
        groups.get(g).push(t);
      }
      for (const t of Object.keys(S.data.counts || {})) if (!info(t)) gone.push(t);
      if (gone.length) groups.set("없어진 대상", gone);
      if (groups.size) {
        const sec = h("section", "wf-reqs-group-sec wf-reqs-index");
        sec.append(h("h4", "", "대상마다"));
        for (const [g, list] of groups) {
          const ul = h("ul", "wf-reqs-rows");
          for (const t of list) {
            const c = countOf(t), li = h("li"), go = h("button", "wf-reqs-go"), n = h("span", "wf-reqs-count", `${c.n}건`);
            go.type = "button";
            go.dataset.to = t;
            go.title = "이 대상의 요구사항 보기";
            go.addEventListener("click", () => open(t, ""));
            if (c.open) { n.dataset.open = "1"; n.textContent = `${c.n}건 · 요청 ${c.open}`; }
            go.append(h("span", "wf-reqs-go-name", nameOf(t)), n);
            li.append(go); ul.append(li);
          }
          sec.append(h("h5", "", g), ul);
        }
        body.append(sec);
      }
      kids.push(body);
      warn();
      kids.push(addEl(""));
      kids.push(h("p", "wf-reqs-foot", "도구 · 단계 · 워크플로우를 오른쪽 단추로 누르거나 머리의 아이콘을 눌러도 그 대상의 요구사항이 열립니다."));
    }
    aside.replaceChildren(...kids);
    body.scrollTop = was === S.target ? top : 0;
    if (inside && !aside.contains(document.activeElement)) title.focus({ preventScroll: true }); // 다시 그려서 초점이 사라졌으면 열의 머리로
    marks();
  }

  window.WfReqs = {
    open, close,
    mount(cols, ctx) { if (cols && ctx && typeof ctx.family === "function") forms.set(cols, ctx); }, // workflow.js helpWrap — 그 폼의 틀
    menu(fn) { if (typeof fn === "function") extra.push(fn); }, // 우클릭 메뉴에 항목을 얹는다
    count: (target) => countOf(target).n,
    reload: () => load(true),
  };
  const start = () => { topMount(); watch(); load(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
