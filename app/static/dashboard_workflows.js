"use strict";
// 문서별 워크플로우 목록·마지막 진행 요약. 실행 상태는 dashboard.js의 기존 단계 셈이 원본이다.
// spec_작업에이전트 ② §9 「워크플로우 목록」. 목록 추가는 실행/선택과 분리한다.
const DWF = { doc: "", items: [], loaded: false, loading: null, pending: null, saved: {}, open: false, library: false, busy: false, error: "", failed: "", model: null, retry: null };
const dwfStamp = (r) => JSON.stringify([r.job, r.status, r.done, r.total]);
function dwfBlocked() {
  const agent = typeof AGENT !== "undefined" ? AGENT : null, style = typeof STYLE !== "undefined" ? STYLE.save : null;
  const gather = typeof gatherState !== "undefined" ? gatherState : null, relay = typeof taskFlow !== "undefined" ? taskFlow : null;
  const flags = (value) => value && Object.entries(value).some(([key, on]) => key.endsWith("Busy") && !!on);
  return !!(DWF.busy || DASH.busy || agwRunning() || (typeof projectBusy === "function" && projectBusy())
    || (typeof dv !== "undefined" && dv.busy) || (typeof taskResetting !== "undefined" && taskResetting)
    || (agent && (agent.busy || agent.applying || agent.matBusy || agent.work?.running))
    || (style && (style.loading || style.busy || style.llm || style.auto))
    || flags(gather) || (gather && Object.values(gather.links || {}).some((link) => link.busy))
    || flags(relay) || relay?.fill?.busy || relay?.guide?.busy);
}

function dwfReset() {
  if (DWF.doc === dashKey()) return;
  Object.assign(DWF, { doc: dashKey(), items: [], loaded: false, loading: null, pending: null, saved: {}, open: false, library: false, busy: false, error: "", failed: "", model: null, retry: null });
}

async function dwfLoad(force = false) {
  dwfReset();
  if (DWF.loading) return DWF.loading;
  if (DWF.loaded && !force) return;
  const doc = DWF.doc, id = state.id;
  const request = (async () => {
    try {
      const data = state.stored ? await api(`/api/works/${id}/workflows`) : { items: agwJob() ? [{ job: agwJob(), status: "ready", done: 0, total: 0 }] : [] };
      if (doc !== dashKey() || DWF.doc !== doc) return;
      DWF.items = data.items; DWF.loaded = true; DWF.error = ""; DWF.failed = "";
      DWF.saved = Object.fromEntries(data.items.map((r) => [r.job, dwfStamp(r)]));
    } catch (e) {
      if (doc === dashKey() && DWF.doc === doc) DWF.error = `워크플로우 목록을 읽지 못했습니다: ${e.message}`;
    }
  })();
  DWF.loading = request;
  try { await request; } finally { if (DWF.loading === request) DWF.loading = null; }
}

function dwfSnapshot(M) {
  const nodes = M.groups.flatMap((g) => g.nodes), counted = nodes.filter(dashCounted);
  if (!M.reg || !counted.length) return null;
  // 서식 복사는 후보 화면을 열기 전에는 실시간 상태가 없다. 그때의 'todo'로 저장한 이력을 덮지 않는다.
  if (M.job === "style_copy") {
    const source = typeof STYLE !== "undefined" ? STYLE.save : null;
    if (!source || source.key !== `doc|${state.id}|${state.epoch}` || source.loading || source.err || !styleSaveOn()) return null;
  }
  // 일반 편집은 요청→반영을 반복한다. 자동 '문서 열기' 1/1을 완료로 세지 않는다.
  const repeat = M.job === "doc_edit", parts = M.job === "plan_merge" ? M.groups.flatMap((g) => g.parts?.rows || []) : [];
  // 취합은 기관 문서 줄마다 별도 실행이다. 기준본만 만든 상태/기관 문서가 아직 없는 상태는 완료가 아니다.
  const partTotal = M.job === "plan_merge" ? Math.max(1, parts.length) : 0;
  const total = repeat ? 0 : counted.length + partTotal, done = repeat ? 0 : counted.filter((n) => n.state === "done").length + parts.filter((r) => r.state === "done").length;
  const started = nodes.some((n) => n.key !== "open" && n.state === "done") || parts.some((r) => r.state === "done" || r.state === "run") || !!M.R || !!DASH.busy;
  return { job: M.job, status: !repeat && total && done === total ? "done" : started || repeat ? "progress" : "ready", done, total };
}

async function dwfObserve(M, retry = false) {
  DWF.model = M;
  if (!DWF.loaded || DWF.doc !== dashKey() || DASH.primed !== `${dashKey()}|${M.job}` || M.job !== agwJob()) return;
  const row = dwfSnapshot(M);
  if (!row) return;
  const stamp = dwfStamp(row);
  if (DWF.saved[row.job] === stamp || (!retry && DWF.failed === stamp)) return;
  if (DWF.pending) { if (retry) { await DWF.pending; return dwfObserve(M, true); } return; }
  const doc = dashKey(), id = state.id;
  const request = (async () => {
    try {
      const data = state.stored ? await api(`/api/works/${id}/workflows`, { method: "PUT", headers: H_JSON, body: JSON.stringify(row) })
        : { items: [...DWF.items.filter((r) => r.job !== row.job), row] };
      if (doc !== dashKey() || DWF.doc !== doc) return;
      DWF.items = data.items; DWF.saved[row.job] = stamp; DWF.failed = ""; DWF.error = "";
    } catch (e) {
      if (doc === dashKey() && DWF.doc === doc) { DWF.failed = stamp; DWF.error = `진행 기록을 저장하지 못했습니다: ${e.message}`; }
      if (retry) throw e;
    }
  })();
  DWF.pending = request;
  try { await request; } finally { if (DWF.pending === request) DWF.pending = null; }
}

async function dwfAdd(job) {
  if (dwfBlocked() || !DWF.loaded || DWF.items.some((r) => r.job === job)) return;
  const doc = dashKey(), id = state.id;
  DWF.busy = true; DWF.error = ""; DWF.retry = null; projectControlsSync(); dashDraw(true);
  try {
    if (DWF.pending) await DWF.pending;
    if (doc !== dashKey()) return;
    const data = state.stored ? await api(`/api/works/${id}/workflows`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ job }) })
      : { items: [...DWF.items, { job, status: "ready", done: 0, total: 0 }] };
    if (doc !== dashKey()) return;
    DWF.items = data.items;
    toast(`「${TASK_CATALOG[job].name}」${dwfEul(TASK_CATALOG[job].name)} 목록에 추가했습니다`);
  } catch (e) { if (doc === dashKey()) { DWF.error = `워크플로우를 추가하지 못했습니다: ${e.message}`; DWF.retry = () => dwfAdd(job); } }
  finally { if (doc === dashKey()) { DWF.busy = false; projectControlsSync(); dashDraw(true); } }
}

// 목록의 워크플로우 이름 — 목록(TASK_CATALOG)에 없는 조립한 것은 키 대신 그 까닭(지워짐 · 저장 파일을 못 읽음 — task_catalog.js taskLostWhy 와 같은 갈림)
const dwfName = (job) => (TASK_CATALOG[job] || {}).name || (taskCustomKey(job) ? (taskCatalogBroken ? "조립한 워크플로우 — 저장 파일을 읽지 못함" : "조립한 워크플로우 — 지워짐") : job);
// 이름 뒤 조사 「을」 · 「를」 — 끝 글자에 받침이 있으면 「을」(한글 · 숫자로 가린다 — 그 밖의 글자는 「를」: 서버 app/custom_tasks.py _eun 과 같은 규칙). 「… 이관」 → 을 · 「… 표준화」 → 를
const dwfEul = (word) => { const c = String(word || "").slice(-1); return c >= "가" && c <= "힣" ? ((c.charCodeAt(0) - 0xac00) % 28 ? "을" : "를") : c && "013678".includes(c) ? "을" : "를"; };

// 「목록에서 빼기」(지금 워크플로우가 아닌 줄 — spec_워크플로우 ② §15 「실행」): 그 작업의 워크플로우 목록에서 그 줄만 뺀다(DELETE …/workflows/{job} — 문서 · 분석은 그대로이고,
// 그 줄의 진행 요약과 그 워크플로우로 돌아올 때 쓰던 기억 — 줄의 context: 문서 역할 · 라운드(app/workflow_runs.py activate) — 이 없어진다).
// 문서가 안 바뀌어 확인 창은 두지 않는다(design.md §18). 서버가 거절하면(400 지금 워크플로우 · 404 그런 줄 없음) 그 글을 그대로 알린다. 조립한 정의를 지우려면 그 키가 든 목록에서 먼저 빼야 한다(DELETE /api/tasks/{key} 409)
async function dwfDrop(job) {
  if (dwfBlocked() || !DWF.loaded || job === agwJob() || !DWF.items.some((r) => r.job === job)) return;
  const doc = dashKey(), id = state.id, name = dwfName(job);
  DWF.busy = true; DWF.error = ""; DWF.retry = null; projectControlsSync(); dashDraw(true);
  try {
    if (DWF.pending) await DWF.pending;
    if (doc !== dashKey()) return;
    const data = state.stored ? await api(`/api/works/${id}/workflows/${encodeURIComponent(job)}`, { method: "DELETE" }) : { items: DWF.items.filter((r) => r.job !== job) };
    if (doc !== dashKey()) return;
    DWF.items = data.items; delete DWF.saved[job];
    toast(`「${name}」${dwfEul(name)} 이 문서의 워크플로우 목록에서 뺐습니다`);
  } catch (e) {
    if (doc !== dashKey()) return;
    const old = e.status === 404 && e.message === "Not Found"; // 끝점이 없는 옛 서버(그런 줄이 없다는 404 는 서버의 글이 온다)
    toast(old ? "목록에서 빼지 못했습니다 — 서버가 옛 판입니다(서버를 다시 켠 뒤에 뺄 수 있습니다)" : e.message, true);
    if (e.status === 404 && !old) await dwfLoad(true); // 그 사이 다른 화면이 뺐다 — 목록을 지금 것으로
  } finally { if (doc === dashKey()) { DWF.busy = false; projectControlsSync(); dashDraw(true); } }
}

async function dwfSelect(job) {
  if (dwfBlocked() || !DWF.loaded) return;
  if (job === agwJob()) { DWF.open = false; DWF.library = false; dashDraw(true); return; }
  const doc = dashKey(), id = state.id, previousModel = DWF.model;
  DWF.busy = true; DWF.error = ""; DWF.retry = null; projectControlsSync(); dashDraw(true);
  try {
    // 조립한 워크플로우면 그 정의를 서버에서 다시 읽고 고른다(app.js taskCatalogRefresh — 붙박이는 안 읽음: spec_워크플로우 ② §15 「실행」) — 지워졌으면 고르지 않고, 바뀌었으면 새 정의로 그린다
    const R = typeof taskCatalogRefresh === "function" ? await taskCatalogRefresh(job) : null;
    if (doc !== dashKey()) return;
    if (R && R.gone) { toast(R.why, true); return; }
    if (R && R.changed) toast(TASK_DEF_PICKED);
    await flushAll();
    await divSettingsFlush();
    if (doc !== dashKey()) return;
    if (state.failed.size) throw new Error("저장하지 못한 문단이 있습니다. 문단을 다시 저장한 뒤 선택하세요.");
    // 설정 저장은 오류를 알리고 삼킨다. 실패한 입력을 divReset으로 지우지 않도록 저장 키까지 확인한다.
    const configDirty = () => dv.values && (dv.dirty || dv.savedKey !== null) && divCanon(divValues()) !== dv.savedKey;
    if (configDirty()) await divSettingsSave();
    if (doc !== dashKey()) return;
    if (configDirty()) throw new Error("프로젝트 구성 입력을 저장하지 못했습니다. 입력값을 확인하거나 다시 저장한 뒤 선택하세요.");
    if (DWF.pending) await DWF.pending;
    await dwfObserve(previousModel && previousModel.job === agwJob() ? previousModel : await dashModel(), true);
    if (doc !== dashKey()) return;
    const data = state.stored ? await api(`/api/works/${id}/workflows/activate`, { method: "POST", headers: H_JSON, body: JSON.stringify({ job }) })
      : { task: { ...state.task, job, kind: taskKindOf(job) }, items: DWF.items };
    if (doc !== dashKey()) return;
    state.task = data.task; DWF.items = data.items;
    DWF.open = false; DWF.library = false; DWF.model = null;
    divReset(); peerPick = null;
    if (typeof gatherState !== "undefined") gatherState = null;
    if (typeof compareReset === "function") compareReset();
    if (typeof agentReset === "function") agentReset();
    Object.assign(DASH, { open: null, nowKey: "", form: false, last: null, primed: "", sig: "", loadKey: "", projTried: "" });
    taskDraw(); divMarksDraw();
    await loadWorks();
    if (doc !== dashKey()) return;
    if (data.division && typeof projectEnterNote === "function") projectEnterNote(data.division);
    showTab("Dash");
    await dashShow();
  } catch (e) { if (doc === dashKey()) { DWF.error = `워크플로우를 선택하지 못했습니다: ${e.message}`; DWF.retry = () => dwfSelect(job); } }
  finally { if (doc === dashKey()) { DWF.busy = false; projectControlsSync(); dashDraw(true); } }
}

function dwfToggleEl(M) {
  const b = el("button", "dash-workflow-toggle");
  b.type = "button"; b.dataset.dashFocus = "workflow:toggle";
  b.setAttribute("aria-expanded", String(DWF.open)); b.setAttribute("aria-controls", "dashWorkflowList");
  b.title = "추가한 워크플로우 선택 · 진행 상태 보기";
  b.append(el("b", null, M.name), el("span", "dash-workflow-chevron", DWF.open ? "▴" : "▾"));
  b.onclick = () => { DWF.open = !DWF.open; if (!DWF.open) DWF.library = false; dashDraw(true); };
  return b;
}

function dwfStatus(row, current) {
  return row.status === "done" ? "✓ 완료" : row.status === "progress" ? current ? "진행 중" : "진행함" : "진행 전";
}

function dwfListEl(M) {
  if (!DWF.open && !DWF.error) return null;
  const box = el("div", "dash-workflows");
  box.id = "dashWorkflowList";
  box.setAttribute("role", "region"); box.setAttribute("aria-label", "이 문서의 워크플로우");
  if (DWF.error) {
    const p = el("p", "dash-workflow-error", DWF.error), retry = dashBtn("다시 시도", async () => {
      if (dwfBlocked()) return;
      if (DWF.retry) { await DWF.retry(); return; }
      if (!DWF.loaded) await dwfLoad(true);
      else if (DWF.failed && DWF.model) { try { await dwfObserve(DWF.model, true); } catch (_) {} }
      else DWF.error = "";
      dashDraw(true);
    }, { disabled: dwfBlocked(), focus: "workflow:retry" });
    p.setAttribute("role", "status"); box.append(p, retry);
  }
  if (!DWF.open) return box;
  const top = el("div", "dash-workflow-heading"), list = el("ul", "dash-workflow-list"), live = dwfSnapshot(M), blocked = dwfBlocked();
  top.append(el("b", null, "이 문서의 워크플로우"), el("span", "muted", `${DWF.items.length}개`)); box.append(top);
  list.setAttribute("aria-label", "추가한 워크플로우");
  for (const saved of DWF.items) {
    const current = saved.job === M.job, row = current && live && DASH.primed === `${dashKey()}|${M.job}` ? live : saved;
    const li = el("li"), b = el("button", "dash-workflow-row"), main = el("span", "dash-workflow-main"), status = el("span", "dash-workflow-status", dwfStatus(row, current));
    b.type = "button"; b.dataset.job = row.job; b.dataset.status = row.status; b.dataset.dashFocus = `workflow:${row.job}`; b.disabled = blocked;
    b.setAttribute("aria-current", String(current));
    main.append(el("b", null, dwfName(row.job)));
    const sub = el("span", "dash-workflow-sub");
    if (current) sub.append(el("span", "dash-workflow-current", "선택됨"));
    if (row.total) sub.append(el("span", null, `${row.done}/${row.total} 단계`));
    if (!current && saved.updated) sub.title = "마지막으로 확인한 진행 상태 — 선택하면 갱신됩니다";
    if (sub.childNodes.length) main.append(sub);
    b.append(main, status); b.onclick = () => dwfSelect(row.job); li.append(b);
    if (!current) { // 지금 워크플로우가 아닌 줄 — 「목록에서 빼기」(dwfDrop · 그 목록의 다른 단추와 같은 28px 단추: design.md §1-3 · 줄 단추 밖에 — 단추 안에 단추를 두지 않는다)
      // 풍선 도움말 = 빼면 없어지는 것(진행 요약 + 돌아올 때 쓰던 기억 — 등록부의 대시보드 도구 단계 글과 같은 뜻). 「다시 넣을 수 있음」 은 워크플로우를 두고 하는 말이라
      // 「뺍니다」 바로 뒤에 둔다(다시 넣어도 그 기억은 돌아오지 않는다 — 없어지는 것 뒤에 두면 기억이 돌아오는 것으로 읽힌다)
      const name = dwfName(row.job), drop = dashBtn("목록에서 빼기", () => dwfDrop(row.job), { disabled: blocked, focus: `workflow:drop:${row.job}`,
        title: `「${name}」 ${dwfEul(name)} 이 문서의 워크플로우 목록에서 뺍니다${TASK_CATALOG[row.job] ? "(다시 「＋ 워크플로우 불러오기」 로 넣을 수 있음)" : ""} — 문서와 분석은 그대로이고, 그 줄의 진행 요약과 그 워크플로우로 돌아올 때 쓰던 기억(문서 역할 · 라운드)이 없어집니다` });
      drop.classList.add("dash-workflow-drop"); drop.dataset.job = row.job; drop.setAttribute("aria-label", `「${name}」 목록에서 빼기`);
      li.append(drop);
    }
    list.append(li);
  }
  if (!DWF.loaded) list.append(el("li", "dash-text muted", DWF.loading ? "워크플로우 목록을 읽는 중…" : "목록을 다시 읽어 주세요"));
  box.append(list);
  const load = dashBtn("＋ 워크플로우 불러오기", () => { DWF.library = !DWF.library; dashDraw(true); }, { disabled: blocked || !DWF.loaded, focus: "workflow:load" });
  load.classList.add("dash-workflow-load"); load.setAttribute("aria-expanded", String(DWF.library)); load.setAttribute("aria-controls", "dashWorkflowLibrary"); box.append(load);
  if (blocked) box.append(el("p", "dash-text muted", DWF.busy ? "워크플로우를 저장하는 중…" : "진행 중인 작업이 끝나면 워크플로우를 선택할 수 있습니다"));
  if (DWF.library) {
    const library = el("ul", "dash-workflow-library"); library.id = "dashWorkflowLibrary"; library.setAttribute("aria-label", "불러올 워크플로우");
    for (const [job, cat] of Object.entries(TASK_CATALOG)) {
      if (cat.soon || !taskAcceptOf(job).includes(state.format || "hwpx")) continue;
      const added = DWF.items.some((r) => r.job === job), li = el("li"), name = el("div", "dash-workflow-library-head");
      const add = dashBtn(added ? "추가됨" : "목록에 추가", () => dwfAdd(job), { disabled: added || blocked, focus: `workflow:add:${job}` });
      add.classList.add("dash-workflow-add"); add.dataset.job = job;
      name.append(el("b", null, cat.name), add); li.append(name, el("p", "dash-text muted", cat.desc || "")); library.append(li);
    }
    box.append(library);
  }
  return box;
}

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !DWF.open || !e.target.closest("#paneDash")) return;
  e.preventDefault(); e.stopPropagation(); DWF.open = false; DWF.library = false;
  dashDraw(true).then(() => document.querySelector("#paneDash .dash-workflow-toggle")?.focus());
});
