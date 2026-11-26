"use strict";
// 패널 「작업 개요」 의 **「단계」 절** — 줄 목록(정의 v2)으로 조립한 이관형(task_catalog.js taskIsRelayFlow — 같은 양식 취합 taskIsCollect 도 든다)의 묶음 › 줄 · 실행 단추.
// 2026-11-25 사용자 "양식작성 워크플로우와 연차보고서 배포안 작성 워크플로우가 UIUX 가 동일한지 검토해줘 … 일관성이 있어야햐" → 검토(spec_양식작성 ④ 맨 위)의 첫 항목:
// 양식 작성은 「작업 개요」 에 묶음 셋과 실행 단추가 서는데, 줄 목록으로 조립한 이관형은 대시보드에 있는 묶음 넷이 「작업 개요」 에서 모두 빠졌다 — 까닭: app.js taskStagesSync 가 조립한 것의 묶음을
// 화면의 표준 네 묶음(review · frame · map · clean)에서 거르는데 그 정의의 묶음 id 는 g1 … 이다(TASK_STAGES 가 빈다 · 그 정의는 화면의 이관 실행 taskRunAll 로 돌지도 않는다).
// **새로 세지 않고 새 실행 길도 만들지 않는다** — 패널 대시보드와 같은 것이다(첫 화면의 대시보드 home_dash.js 가 그러듯):
// - 셈 = dashModel()(dashboard.js — 서버가 센 상태 GET …/flow 로 지은 묶음 M.groups · 머리 단추 M.top 「이어서 한 번에 N→M단계」 · 도는 실행 M.lives · 지난 실행의 끝 M.lasts · 알림 M.notes).
// - 그리기 = 대시보드의 함수(dashGroupsEl · dashNodeEl · dashDetailEl · dashMemoEl · dashLiveEl · dashEndEl)를 **제 그리기 문맥**(fovCtx — 펼친 세부의 id 머리만 다르다)으로.
// - 단추 = 대시보드의 단추 그대로(묶음의 「한 번에 진행」 · 「한 문서만」 · 줄(문서 카드)의 「이 단계만 진행」 · 보기 단추 · 고르기 칩 — 누르면 dashExec · dashFlowRun: 서버 쪽 실행기).
// - 편 카드 · 「지금」 을 따라 펴는 것은 대시보드와 **같은 값**(DASH.open · DASH.nowKey · DASH.pin)을 쓴다 — 두 탭을 오가도 같은 카드가 펴져 있다(카드 안의 것 — 「했음」 · 「기관 문서」 목록 — 이 그 값을 건드린다).
// 따라가기(대시보드 탭이 숨어 있어도): ① 1초마다(보이는 동안만 — 상태 · 글 · 단추가 같으면 도는 글만 바꾼다: dashSig) ② 대시보드가 다시 그려질 때(#dashBox 의 바뀜 — 이 절의 단추가 부른 dashExec 의 시작 · 끝이 dashDraw 를 부른다)
// ③ 읽는 중이던 서버 상태 · 고르기 값이 왔을 때(그 읽기는 대시보드가 보일 때만 dashDraw 를 부른다). 다시 그려도 초점은 그 단추에(data-dash-focus — dashDraw 와 같은 방식).
// 자리 = app.js taskFlowEl 이 붙박이 이관의 묶음 상자(#taskSteps) 아래에 flowOverviewEl() 을 넣는다 — 같은 문서 · 같은 워크플로우면 그린 것을 그대로 옮긴다(「작업 개요」 가 다시 그려져도 깜박이지 않게).
// 길 찾기 줄(.dv-journey)도 이 절이 채운다(준비 + 묶음마다 — app.js taskJourneySync: 붙박이의 taskJourneyDraw 는 이 워크플로우에서 그리지 않는다).
// 붙박이 이관 · 표준 차례로 조립한 것(v2 아님) · 취합 · 양식 작성의 「작업 개요」 는 이 파일과 무관하다(flowOverviewOn 거짓).
// 읽히는 차례: dashboard.js · workflow_exec.js 다음. 기대는 이름 — app.js: state · $ · el · showTab · taskJourneySync / panel_help.js: hHelp · panelHelpOwner · panelHelpClose / task_catalog.js: taskIsRelayFlow /
//   doc_agent_work.js: agwJob · agwLiveText / dashboard.js: DASH(reg · regErr · doc · open · nowKey · pin · busy · last · flow · take · cap) · DASH_HELP · dashKey · dashRegLoad · dashModel · dashSig · dashCounted · dashBtn ·
//   dashGroupsEl · dashLiveEl · dashEndEl · dashOneLine · dashFlow · 초점 이름 「act:files:div」 · 「act:config:input」 · 「act:configLoad:open」(FOV_HERE) / dashboard_workflows.js: DWF(busy).
//   **dashboard.js 의 그 이름 · 인자 · 초점 이름을 바꾸면 이 파일도 본다**(화면 검사 run_ui_gates 이름 relay_flow 의 「작업 개요」 줄).

const FOV = { host: null, key: "", sig: "", seq: 0, reg: null, drawing: 0, ctx: null, regWait: false };
// host = 「단계」 절의 자리(#flowOverview) · key = 그 자리의 문서 · 워크플로우 · sig = 마지막으로 그린 것(dashSig) · reg = 그릴 때의 등록부(설명을 고치면 바뀐다) · drawing = 그리는 중인 수
const FOV_SEEN = new WeakSet(); // 끝나면 다시 그리기로 한 읽기(약속)
const fovKey = () => `${dashKey()}|${agwJob()}`;
const flowOverviewOn = () => typeof state !== "undefined" && !!state.id && !!state.task && typeof taskIsRelayFlow === "function" && taskIsRelayFlow(state.task.job) && typeof dashModel === "function";
function flowOverviewShown() { // 「작업 개요」 가 보이고 그 안에 이 절이 붙어 있나
  const h = FOV.host, panel = $("panel"), pane = $("paneDiv");
  return flowOverviewOn() && !!h && h.isConnected && !!panel && !panel.hidden && panel.dataset.tool === "Div" && !!pane && !pane.hidden && !document.hidden;
}
// 그리기 문맥(dashboard.js DASH_CTX 와 같은 꼴 — 다른 것은 펼친 세부의 id 머리와 다시 그리는 함수뿐): 초점 이름은 대시보드와 같은 data-dash-focus(단추가 그 이름을 달고 온다 — dashBtn)
function fovCtx() {
  return FOV.ctx || (FOV.ctx = { focus: "dashFocus", id: "fovD", panel: true, counted: dashCounted, job: () => agwJob(),
    toggle: (key, open) => { DASH.open = open ? "" : key; flowOverviewDraw(true); }, go: (key) => { DASH.open = key; flowOverviewDraw(true); } });
}

function flowOverviewEl() { // app.js taskFlowEl 이 부른다 → 「단계」 절의 자리. 붙은 뒤에 그린다
  const key = fovKey();
  if (!FOV.host || FOV.key !== key) {
    const host = el("div", "flow-ov");
    host.id = "flowOverview";
    host.append(el("p", "dash-text muted", "단계 흐름을 읽는 중…"));
    Object.assign(FOV, { host, key, sig: "", reg: null });
  }
  setTimeout(() => flowOverviewDraw(), 0);
  return FOV.host;
}

// 대시보드의 단추 가운데 「작업 개요」 탭을 여는 것(showTab("Div")) — 여기서는 이미 그 탭이다: 같은 탭 안의 그 자리로 간다(자리를 못 찾으면 단추의 본디 동작 그대로)
const FOV_HERE = { "act:files:div": "files", "act:config:input": "config", "act:configLoad:open": "config" };
function flowOverviewGo(where) { // → 갔나
  const box = $("divBox"), flow = document.getElementById("taskFlow");
  const to = where === "files" ? flow && flow.querySelector(".dv-flow-files select:not(:disabled), .dv-flow-files button:not(:disabled)")
    : box && (box.querySelector(".dv-presets select:not(:disabled)") || box.querySelector(".dv-year-field input:not(:disabled)"));
  if (!to) return false;
  to.scrollIntoView({ block: "center" });
  to.focus({ preventScroll: true });
  return true;
}

function flowOverviewWait() { // 읽는 중인 서버 상태 · 고르기 값(대시보드가 숨어 있으면 그 읽기가 아무것도 다시 그리지 않는다) — 오면 이 절을 다시 그린다
  const list = [DASH.flow && DASH.flow.loading, DASH.take && DASH.take.loading, ...Object.values((DASH.cap && DASH.cap.by) || {}).map((c) => c && c.loading)];
  for (const p of list) {
    if (!p || typeof p.then !== "function" || FOV_SEEN.has(p)) continue;
    FOV_SEEN.add(p);
    p.then(() => flowOverviewDraw(), () => {});
  }
}

function flowOverviewJourney(M, box) { // 길 찾기 줄 — 준비 + 묶음마다(붙박이 이관의 taskJourneyDraw 와 같은 꼴 · 같은 상태 말: 끝남은 서버가 센 그 묶음의 남은 수로)
  const flow = document.getElementById("taskFlow"), nav = flow && flow.querySelector(".dv-journey");
  if (!nav || typeof taskJourneySync !== "function" || !M.groups.length) return;
  const V = DASH.flow && DASH.flow.id === state.id ? DASH.flow.view : null, files = M.groups.flatMap((g) => g.nodes).find((n) => n.key === "files");
  const prepared = V ? !!V.ready : !files || files.state === "done";
  let available = prepared;
  const items = [{ id: "prepare", label: "준비", state: prepared ? "done" : "now", target: flow.querySelector(".dv-flow-files"), note: "문서를 고르는 곳으로 이동합니다." }];
  for (const g of M.groups) {
    const sv = V && (V.stages || []).find((x) => x.id === g.id), cnt = g.nodes.filter(dashCounted);
    const done = sv && typeof sv.left === "number" ? sv.left === 0 : cnt.length > 0 && cnt.every((n) => n.state === "done");
    const st = g.nodes.some((n) => n.state === "run") ? "run" : !available ? "todo" : (g.end && !g.end.ok) || g.nodes.some((n) => n.state === "hold") ? "halt" : done ? "done" : "now";
    items.push({ id: g.id, label: `${g.label.no} ${g.label.name}`.trim(), state: st, target: box.querySelector(`.dash-group[data-group="${g.id}"]`), note: `${g.label.name} — ${g.does}. 눌러서 세부 순서를 확인합니다.` });
    available = available && done;
  }
  taskJourneySync(nav, items);
}

function flowOverviewBody(M) { // 대시보드의 몸(dashboard.js dashEl)에서 워크플로우 고르기 · 워크플로우 링크 · 맨 아래 초기화 줄을 뺀 것 — 머리는 이 탭의 절 머리 꼴(제목 + 메모 아이콘)
  const root = el("section", "dash"), head = el("div", "dv-note-heading flow-ov-head");
  root.setAttribute("aria-label", "단계");
  const nodes = M.groups.flatMap((g) => g.nodes), counted = nodes.filter(dashCounted), done = counted.filter((n) => n.state === "done").length, total = counted.length;
  head.append(el("h3", null, "단계"), ...(total ? [el("span", "dash-count", `끝남 ${done}/${total}`)] : []),
    hHelp("단계 안내", `패널 「대시보드」 와 같은 단계 · 같은 상태 · 같은 단추입니다 — 어느 쪽에서 눌러도 같은 실행입니다.\n${DASH_HELP}`, { note: true }));
  root.append(head);
  const run = nodes.find((n) => n.state === "run"), now = nodes.find((n) => n.state === "now"), next = el("p", "dash-next");
  next.setAttribute("role", "status");
  next.textContent = M.lives && M.lives.length ? `진행 중 — ${M.lives.map((x) => x.label).join(" · ")}` : M.R ? `진행 중 — ${M.R.label}` : run ? `진행 중 — ${String(run.idx).padStart(2, "0")} ${run.name}`
    : now ? `다음: ${String(now.idx).padStart(2, "0")} ${now.name}` : total && done === total ? "모두 끝남" : "";
  if (next.textContent) root.append(next);
  const live = dashLiveEl(M);
  if (live) root.append(live);
  if (DASH.last) root.append(dashEndEl("dash-last", DASH.last.ok, DASH.last.text, null, { label: DASH.last.label }));
  for (const x of [...(M.last ? [M.last] : []), ...(M.lasts || [])]) { const p = dashEndEl("dash-last", x.ok, x.text, x.rows, { title: `지난 실행 — ${dashOneLine(x.text).split(" — ")[0]}` }); p.dataset.flowLast = "1"; root.append(p); }
  for (const n of M.notes) { const p = el("div", "dash-note" + (n.warn ? " warn" : "")); p.append(el("span", null, n.text)); if (n.act) p.append(n.act); root.append(p); }
  if (M.top.length) { const top = el("div", "dash-top"); top.append(...M.top); root.append(top); }
  if (DASH.regErr && !M.reg) { root.append(el("p", "dash-note warn", `워크플로우를 읽지 못했습니다: ${DASH.regErr}`), dashBtn("다시 읽기", () => { DASH.regErr = ""; flowOverviewDraw(true); })); return root; }
  if (!M.reg) { root.append(el("p", "dash-text muted", "단계 흐름을 읽는 중…")); return root; }
  if (!M.groups.length) { root.append(el("p", "dash-text muted", "등록된 단계가 없습니다")); return root; }
  const cardOf = (n) => (n && n.cards ? n.cards.find((c) => c.state === "run") || n.cards.find((c) => c.state === "now") || n.cards.find((c) => c.state !== "done") || n.cards[0] : n); // 문서 카드가 있는 줄 — 도는(없으면 「지금」 · 안 끝난) 카드
  const cur = cardOf(run || now), asked = DASH.open ? nodes.find((n) => n.cards && (n.ref || n.key) === DASH.open) : null;
  const openKey = DASH.open === null ? (cur ? cur.ref || cur.key : "") : asked ? cardOf(asked).ref : DASH.open; // 대시보드와 같은 셈(dashEl)
  root.append(dashGroupsEl(M.groups, openKey, fovCtx()));
  return root;
}

async function flowOverviewDraw(force = false) {
  const box = FOV.host;
  if (!box || !flowOverviewShown()) return;
  if (FOV.key !== fovKey()) Object.assign(FOV, { key: fovKey(), sig: "", reg: null }); // 붙어 있는 자리의 문서 · 워크플로우가 그 사이 바뀌었다(보통은 「작업 개요」 가 다시 그려지며 새 자리가 선다 — flowOverviewEl) — 그 자리에 새로 그린다
  if (FOV.drawing && !force) return; // 그리는 중 — 다음 틈(1초)이 따라간다(늦은 셈이 뒤의 셈을 끝없이 버리지 않게)
  if (DASH.doc !== dashKey()) Object.assign(DASH, { doc: dashKey(), open: null, nowKey: "", form: false, last: null, busy: null }); // 대시보드를 아직 안 연 문서 — dashShow 와 같은 맞춤(안 하면 dashExec 가 끝 글을 남기지 않는다)
  if (!DASH.reg && !DASH.regErr && !FOV.regWait) { FOV.regWait = true; dashRegLoad().then(() => { FOV.regWait = false; flowOverviewDraw(true); }, () => { FOV.regWait = false; }); }
  const seq = ++FOV.seq, key = FOV.key;
  let M;
  FOV.drawing++;
  try { M = await dashModel(); }
  catch (e) { console.error(e); M = { job: agwJob(), name: "단계", reg: null, notes: [{ text: `상태를 읽지 못했습니다: ${e.message}`, warn: true }], top: [], groups: [], R: null }; }
  finally { FOV.drawing--; }
  flowOverviewWait();
  if (seq !== FOV.seq || FOV.host !== box || key !== fovKey() || !flowOverviewShown()) return;
  if (M.reg && M.groups.length) { // 차례가 나아가면 펼친 카드도 새 「지금」 으로 — 대시보드와 같은 값 · 같은 셈(dashDraw)
    const nowNode = M.groups.flatMap((g) => g.nodes).find((n) => !n.optional && (n.state === "run" || n.state === "now")), nowKey = nowNode ? nowNode.ref || nowNode.key : "";
    if (nowKey !== DASH.nowKey) { if (DASH.nowKey && !DASH.pin) DASH.open = null; DASH.pin = false; DASH.nowKey = nowKey; }
  }
  const sig = dashSig(M);
  if (!force && sig === FOV.sig && FOV.reg === DASH.reg) { // 그대로 — 도는 글만(초점 · 스크롤 유지)
    if (M.lives && M.lives.length) { for (const X of M.lives) { const t = box.querySelector(`.dash-live-text[data-run="${X.n}"]`), s = agwLiveText(X); if (t && t.textContent !== s) t.textContent = s; } }
    else {
      const t = box.querySelector(".dash-live-text"), s = M.R ? agwLiveText(M.R) : DASH.busy ? `${DASH.busy.label} — 하는 중 · ${fmtDur((Date.now() - DASH.busy.t0) / 1000)}` : "";
      if (t && s && t.textContent !== s) t.textContent = s;
    }
    flowOverviewJourney(M, box); // 「작업 개요」 가 다시 그려져 길 찾기 줄이 새것일 수 있다(이 절은 그대로 옮겨 왔다) — 단추는 그대로 두고 글 · 갈 곳만 맞춘다
    return;
  }
  FOV.sig = sig; FOV.reg = DASH.reg;
  const a = document.activeElement, focus = a && box.contains(a) ? a.dataset.dashFocus || "" : "", ring = !!(focus && a.matches(":focus-visible")); // 키보드로 온 초점이었나
  if (typeof panelHelpOwner !== "undefined" && panelHelpOwner && box.contains(panelHelpOwner)) panelHelpClose(); // 떼어 낼 메모 · 도움말의 풍선이 주인 없이 남지 않게
  box.replaceChildren(flowOverviewBody(M));
  for (const b of box.querySelectorAll("button[data-dash-focus]")) { // 「작업 개요」 탭을 여는 단추 — 이 탭 안의 그 자리로
    const where = FOV_HERE[b.dataset.dashFocus], was = b.onclick;
    if (where) b.onclick = (e) => { if (!flowOverviewGo(where) && was) was.call(b, e); };
  }
  if (typeof DWF !== "undefined" && DWF.busy) for (const c of box.querySelectorAll(".dash-groups button, .dash-groups input, .dash-groups select, .dash-top button")) c.disabled = true; // 워크플로우를 바꾸는 중(대시보드와 같다)
  if (focus) { const f = [...box.querySelectorAll("[data-dash-focus]")].find((x) => x.dataset.dashFocus === focus && !x.disabled); if (f) f.focus({ preventScroll: true, focusVisible: ring }); }
  flowOverviewJourney(M, box);
}

setInterval(() => { // 1초 — 보이는 동안만: 서버 실행의 진행 · 다른 보기가 바꾼 상태를 따라간다(대시보드의 1초 고리와 같은 약속 — 서버는 dashFlowLive 가 낡았을 때만 읽는다)
  if (!flowOverviewShown()) return;
  const a = document.activeElement;
  if (a && a.tagName === "SELECT" && FOV.host.contains(a)) return; // 고르기 목록에 초점이 있는 동안은 다시 그리지 않는다(펼친 목록이 닫힌다)
  flowOverviewDraw();
}, 1000);

// 대시보드가 다시 그려지면(이 절의 단추가 부른 행동의 시작 · 끝 — dashExec 가 dashDraw 를 부른다 · 「멈춤」 · 「기관 문서」 목록의 바뀜) 이 절도 바로 따라 그린다
if (typeof MutationObserver === "function" && document.getElementById("dashBox")) new MutationObserver(() => flowOverviewDraw()).observe(document.getElementById("dashBox"), { childList: true });
