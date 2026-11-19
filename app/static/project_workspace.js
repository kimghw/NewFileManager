// 프로젝트 → TASK → 라운드 탐색. 문서 처리·저장은 기존 작업 API를 사용한다.
let projectStarting = false;
let projectDraft = null;
let projectEdit = null; // 펼친 프로젝트 하나: {name, mode: "menu"|"rename"|"delete", draft, busy}
let projectFocusWant = "", projectComposing = null, projectRedrawLater = false; // 다시 그린 뒤 포커스 줄 곳 · 한글 조합 중인 입력칸 · 미룬 다시 그리기
const PROJECT_WAIT = "진행 중인 작업이 끝난 뒤 프로젝트를 바꿀 수 있습니다";
const projectNameOf = (v) => (v || "").trim().replace(/\s+/g, " ").slice(0, 60); // 서버 normalize_name 과 같게
// 임시 프로젝트(spec_작업 ② §17 「임시 프로젝트」 — 2026-11-18): 이름 없이 TASK 를 시작하면 서버가 붙이는 「임시 프로젝트 N」(서버 app/projects.py TEMP_RE 와 같은 꼴 — 이름이 곧 표시다).
// 이름을 적으면 그 임시 프로젝트의 이름이 바뀐다(문서 모두) — 이미 있는 이름이면 그 프로젝트로 문서를 모두 옮긴다(PUT /api/projects/{임시 이름} — 응답 join)
const PROJECT_TEMP_RE = /^임시 프로젝트 [1-9][0-9]{0,8}$/;
const projectIsTemp = (name) => PROJECT_TEMP_RE.test(projectNameOf(name));
const projectDocCount = (name) => worksList.filter((w) => ((w.task || {}).project || "") === name).length;
let projectMake = null; // 「새 프로젝트」 이름 줄: {draft, busy} | null(닫힘)
const projectNameTaken = (n, except) => !!n && n !== except && (worksList.some((w) => ((w.task || {}).project || "") === n) || !!(projectInfo.map && projectInfo.map.has(n))); // 문서 없는 프로젝트(기록만 남음)의 이름도 쓰는 이름이다(서버 409)
const projectBusy = (includeTaskSave = true) => projectStarting || (includeTaskSave && taskSaveCount > 0) || state.busy || !!taskRun || (typeof gatherRun !== "undefined" && !!gatherRun) || (typeof DWF !== "undefined" && DWF.busy);

function projectControlsSync() {
  const disabled = !taskProject() || !(state.task || {}).job || projectBusy();
  for (const control of document.querySelectorAll('.project-round-label select, [data-new-round]')) control.disabled = disabled;
  const busy = projectBusy();
  for (const b of document.querySelectorAll("#projectList [data-project-act]")) b.disabled = busy || b.dataset.projectAct === "off";
  const off = busy || dv.busy; // 프로젝트 칸 · 구분 기준 줄의 「새로 만들기」 · 버전 줄도 진행 중에는 끈다(② §19)
  for (const c of document.querySelectorAll('#divBox input[data-task="project"], #divBox [data-division-new]')) c.disabled = off;
  if (off && projectCombo && projectCombo.inp.disabled) projectComboClose();
  projectVersionsSync();
  if (typeof divRunSync === "function") divRunSync(); // 프로젝트 구성 실행 묶음(변경 계획 보기 · 반영)의 단추도 TASK 실행이 시작·끝날 때 함께 끄고 켠다(spec_구분_기준 ② §22)
}

function projectGroups() {
  const groups = new Map();
  for (const w of worksList) {
    const t = w.task || {}, project = t.project || "", job = t.job || "";
    // 이름 없는 문서는 서로 관계없는 작업이므로 각각 표시한다.
    const key = project ? taskScopeKey(t) : `work:${w.id}`;
    if (!groups.has(key)) groups.set(key, { key, project, job, round: taskRound(t), docs: [], latest: true });
    groups.get(key).docs.push(w);
  }
  const result = [...groups.values()];
  for (const g of result) {
    g.latest = !g.project || !result.some((x) => x.project === g.project && x.job === g.job && x.round > g.round);
    const target = taskIsRelay(g.job) ? (TASK_CATALOG[g.job] || {}).target : (TASK_CATALOG[g.job] || {}).file; // 이관형(붙박이 이관 · 조립한 TASK) = 그 TASK 의 목적 문서
    g.main = g.docs.find((w) => (w.task || {}).file === target) || g.docs[0];
    g.current = g.docs.some((w) => w.id === state.id);
  }
  return result;
}

async function projectOpen(id) {
  if (projectBusy()) { toast("진행 중인 작업이 끝난 뒤 이동할 수 있습니다"); return; }
  await divSettingsFlush();
  await openWork(id);
  if (state.id === id) showTab(taskRnd() ? "Div" : taskGeneral() ? "Agent" : "Verify"); // 「일반 문서」 작업은 에이전트 보기부터(spec_일반편집 ② §12)
}

function projectRoundRow() {
  const row = el("div", "project-round-row"), t = state.task || {}, groups = projectGroups();
  const rounds = groups.filter((g) => g.project === taskProject() && g.job === t.job).sort((a, b) => b.round - a.round);
  const label = el("label", "project-round-label"), select = el("select");
  label.append(el("span", null, "라운드"));
  select.setAttribute("aria-label", "워크플로우 라운드");
  if (!rounds.some((g) => g.round === taskRound())) select.append(new Option(`Round ${taskRound()}`, String(taskRound())));
  for (const g of rounds) select.append(new Option(`Round ${g.round}${g.latest ? " · 최신" : " · 이전"}`, String(g.round)));
  select.value = String(taskRound());
  select.disabled = !taskProject() || !t.job || projectBusy();
  select.onchange = () => { const g = rounds.find((x) => x.round === Number(select.value)); select.value = String(taskRound()); if (g) projectOpen(g.main.id); };
  label.append(select);
  const add = hBtn("새 라운드", () => { showTab("Tasks"); projectRoundFormShow(); }, { cls: "btn sm", disabled: !taskProject() || !t.job || projectBusy(), title: "지금 라운드의 문서를 복사해 새 작업을 시작합니다" });
  add.dataset.newRound = "1";
  row.append(label, add);
  return row;
}

function projectConfigurationRow() { // 입력 항목 아래의 구성 요약·버전 관리 — 라운드 입력과 분리한다.
  const row = el("div", "project-configuration");
  if (taskProject() && !taskGeneral()) { // 구분 기준의 있음/없음 한 줄 + (공유 중이면) 구분 기준 버전 한 줄 — spec_작업 ② §19. 「일반 문서」 작업에는 없다(구분 기준이 없는 작업 — 이 카드 자체가 연구개발 프로젝트일 때만 그려진다: showTab 의 Div 조건)
    const sharing = el("div", "project-sharing"), versions = projectVersionsEl();
    projectSharingFill(sharing);
    row.append(sharing);
    if (versions) row.append(versions);
  }
  return row;
}

// ---- 구분 기준의 있음/없음(spec_작업 ② §19, 2026-11-13 사용자 "구분기준이 있다면 있다고 표기 하고 없으면 없다고 새로 하라고 하면됨") — 프로젝트 칸 아래 한 줄(.project-sharing).
// 공유 중(그 TASK 의 최신 라운드): 표지 「구분 기준 확정」/「구분 기준 있음」 + 요약 + 「프로젝트 공유」 · 없으면 표지 「구분 기준 없음」 + 「새로 만들기」. 이전 라운드: 「구분 기준 · 이전 라운드 보관」 + 그 작업의 값 요약.
// 표지의 뜻은 고르기 목록과 같은 함수(projectDivisionTag): 없음 = 프로젝트에 구성 값이 없음(서버에 저장된 입력 설정 dv.view.settings 가 없음) · 확정 = 확정 기록의 값이 지금 값과 같음(당해 차년도 빼고) · 있음 = 그 밖
function projectSharingFill(box) {
  const v = dv.view, sh = v && v.projectSharing, now = projectDivisionNow(), values = now && now.values, text = values ? divValuesText(values) : "";
  const kind = !v || !sh ? "" : !sh.shared ? "previous" : projectDivisionTag(now)[0], sig = `${kind}|${text}|${projectBusy() || dv.busy ? 1 : 0}`;
  if (box.dataset.sig === sig) return; // 입력할 때마다 불린다(projectSharingSync) — 달라진 때만 다시 그린다
  box.dataset.sig = sig; box.dataset.division = kind; box.textContent = "";
  const part = (cls, s, title = "") => { const e = el("span", cls, s); if (title) e.title = title; box.append(e); return e; };
  if (!kind) { part("project-sharing-note", "프로젝트 구성 · 프로젝트 공유"); return; } // 아직 읽기 전(옛 서버 포함)
  if (kind === "previous") { part("project-sharing-note", "프로젝트 구성 · 이전 라운드 보관"); if (text) part("project-sharing-text", text, `이 라운드에 보관한 프로젝트 구성\n${text}`); return; }
  if (kind === "none") {
    part("dv-tag is-warning", "프로젝트 구성 없음");
    part("project-sharing-text is-wrap", "이 프로젝트에 구성이 없습니다 — 새로 만드세요");
    const make = hBtn("새로 만들기", () => projectDivisionNew(), { cls: "btn sm", disabled: projectBusy() || dv.busy, title: "프로젝트 구성 입력 칸(불러오기 · 단계·차년도 · 기관 구성)으로 갑니다 — 문서에서 추출하거나 직접 입력한 뒤 「프로젝트에 저장」" });
    make.dataset.divisionNew = "1";
    box.append(make);
    return;
  }
  part("dv-tag" + (kind === "confirmed" ? " is-ready" : ""), kind === "confirmed" ? "프로젝트 구성 확정" : "프로젝트 구성 있음",
    kind === "confirmed" ? "지금 값이 이 프로젝트에 확정한 구성과 같습니다" : "이 프로젝트에 구성이 있습니다 — 아직 확정 전이거나 확정한 뒤 값이 바뀌었습니다(「프로젝트에 저장」 으로 확정)");
  part("project-sharing-text", text, `프로젝트 「${sh.project}」 의 구성\n${text}`);
  part("project-sharing-note", "프로젝트 공유", "같은 프로젝트의 워크플로우들(최신 라운드)이 이 프로젝트 구성을 같이 씁니다");
}

function projectSharingSync() { // 입력이 바뀌거나(divPresetRefresh) 입력 설정이 저장된 뒤(divSettingsSave) — 있음/없음 줄과 버전 줄만 맞춘다(칸·포커스는 그대로)
  const box = document.querySelector("#divBox .project-sharing");
  if (box && dv.view) projectSharingFill(box);
  projectVersionsSync();
}

function projectDivisionNew() { // 「새로 만들기」 — 구성 입력 칸으로: 이관·취합은 1단계 묶음을 펴고 「구성 고치기」 와 같은 곳(taskFrameEdit), 양식 맞추기는 패널의 구성 입력 칸
  const stage = (taskFrameForm && taskFrameForm.isConnected && taskFrameForm.closest("details")) || document.getElementById("gatherStage0"); // 구성 입력 칸이 든 묶음 — 이관 = 2단계 「구성 맞추기」(#taskStage: spec_작업 ② §21) · 취합 = 1단계(#gatherStage0)
  if (stage) { taskFrameEdit(stage); return; }
  if (typeof divRunReveal === "function") divRunReveal(); // 양식 맞추기 — 구성 입력은 실행 묶음의 접어 둔 「세부」 안(spec_구분_기준 ② §22 「카드 하나」): 펴고 「불러오기」 고르기 목록으로
  const config = document.querySelector("#divBox fieldset.dv-config"), to = document.querySelector("#divBox #divSourceSel:not(:disabled)") || (config && config.querySelector(".dv-year-field input"));
  if (!to) return;
  to.scrollIntoView({ block: "center" });
  to.focus({ preventScroll: true });
}

// 프로젝트 칸으로 프로젝트에 들어간 직후의 알림 셋(spec_작업 ② §19). 갈래는 서버가 알려 준다 — PUT …/task 응답의 division: adopted(프로젝트의 구분 기준을 받음) · seeded(이 문서의 값을 프로젝트에 올림) ·
// none(둘 다 없음). 칸이 없으면(이전 라운드로 들어감 · 일반 문서 · 옛 서버) 부르지 않는다(taskSetNow). 요약은 들어간 뒤 읽은 값(divShow → dv.view.settings)
function projectEnterNote(division) {
  const name = taskProject(), values = dv.view && dv.view.settings && dv.view.settings.values;
  if (!name || taskGeneral()) return;
  if (division === "adopted") toast(`프로젝트 「${name}」 의 구성을 가져왔습니다${values ? ` — ${divValuesText(values)}` : ""}`);
  else if (division === "seeded") toast(`프로젝트 「${name}」 에 구성이 없어 이 문서의 구성을 올렸습니다 — 확인한 뒤 「프로젝트에 저장」`);
  else if (division === "none") toast(`프로젝트 「${name}」 에 구성이 없습니다 — 새로 만드세요`);
}

function projectListShow() {
  projectListEnsure();
  projectListDraw();
  loadWorks();
  projectInfoLoad(true); // 문서 없는 프로젝트(기록만 남은 것 — ② §17)도 보이게: 프로젝트 정보(GET /api/projects)를 함께 읽는다 — 오면 목록을 다시 그린다
}

function projectListEnsure() {
  const box = $("projectWorkspace");
  if (box.childElementCount) return;
  const head = el("div", "project-list-head"), title = el("strong", null, "프로젝트별 워크플로우");
  const refresh = hBtn("새로고침", () => { loadWorks(); projectInfoLoad(true); }, { cls: "btn sm" });
  refresh.id = "projectRefresh";
  // 「새 프로젝트」(② §17 「새 프로젝트」) — 머리 아래 인라인 이름 줄(모달 없음 · Enter 만들기 · Esc 닫기) → 문서 없는 프로젝트로 목록에 들어가고, 그 줄의 「파일 올려 시작」 으로 첫 TASK
  const make = hBtn("새 프로젝트", () => projectMakeSet(projectMake ? null : { draft: "", busy: false }), { cls: "btn sm", title: "이름만 정해 프로젝트를 만듭니다 — 파일은 그 뒤에 올려 워크플로우를 시작합니다" });
  make.id = "projectMakeBtn";
  const tools = el("span", "project-list-tools"); tools.append(make, refresh);
  head.append(title, tools);
  const makeBox = el("div", "project-make"); makeBox.id = "projectMake"; makeBox.hidden = true;
  const filter = el("input", "project-search"); filter.type = "search"; filter.placeholder = "프로젝트·워크플로우·파일 찾기"; filter.setAttribute("aria-label", filter.placeholder);
  filter.id = "projectSearch"; filter.oninput = projectListDraw;
  const list = el("div", "project-list"); list.id = "projectList";
  const create = el("details", "project-create"); create.id = "projectCreate";
  create.append(el("summary", null, "+ 새 워크플로우 시작"));
  const form = el("form", "project-start-form");
  const project = el("input"); project.id = "projectStartName"; project.maxLength = 60; project.placeholder = "프로젝트 이름(비우면 임시 이름)"; // 비우면 서버가 임시 이름(② §17 「임시 프로젝트」)
  projectComboAttach(project, { list: "projectStartList" }); // 고르기 목록 — 작업 개요의 프로젝트 칸과 같은 도우미(② §19: 지금 프로젝트가 미리 적혀 있어 datalist 로는 다른 프로젝트가 안 보였다)
  const job = el("select"); job.id = "projectStartTask";
  for (const [key, cat] of Object.entries(TASK_CATALOG)) if (!cat.soon) job.append(new Option(cat.name, key));
  for (const [text, input] of [["프로젝트", project], ["워크플로우", job]]) { const label = el("label", null, text); label.append(input); form.append(label); }
  const start = el("button", "btn", "파일 올려 시작"); start.type = "submit"; start.id = "projectStartUpload";
  form.append(start, el("p", "project-note", "기존 작업을 남기고 새 파일로 시작합니다. 같은 워크플로우가 있으면 다음 라운드가 됩니다."));
  form.onsubmit = (e) => {
    e.preventDefault();
    const name = project.value.trim().replace(/\s+/g, " ");
    if (projectBusy()) return;
    const picker = el("input"); picker.type = "file"; picker.accept = taskAcceptOf(job.value).filter((x) => x !== "pdf").map((x) => `.${x}`).join(","); // 그 TASK 가 받는 문서(task_catalog.js — 보통 hwp·hwpx · 문서 서식 복사는 docx 도). PDF 는 작업을 만들지 않으므로 여기서는 뺀다
    picker.onchange = () => projectUpload(name, job.value, picker.files[0]); picker.click();
  };
  create.append(form);
  const round = el("section", "project-new-round"); round.id = "projectNewRound"; round.hidden = true;
  box.append(head, makeBox, filter, list, create, round);
}

// ---- 새 프로젝트(spec_작업 ② §17 「새 프로젝트」, 2026-11-18 사용자 "새로운 프로젝트 만들기 기능을 추가 해줘") — 머리 아래 인라인 이름 줄. POST /api/projects {name}
function projectMakeSet(next, focus = true) {
  if (projectMake && projectMake.busy) return;
  projectMake = next;
  projectMakeDraw(focus);
}

function projectMakeDraw(focus = false) {
  const box = $("projectMake"), m = projectMake, btn = $("projectMakeBtn");
  if (!box) return;
  if (btn) { btn.setAttribute("aria-expanded", String(!!m)); btn.classList.toggle("on", !!m); }
  box.hidden = !m; box.textContent = "";
  if (!m) return;
  const row = el("div", "project-edit-row"), inp = el("input"), note = el("p", "project-note project-edit-note");
  inp.type = "text"; inp.maxLength = 60; inp.value = m.draft; inp.placeholder = "새 프로젝트 이름"; inp.id = "projectMakeName"; inp.setAttribute("aria-label", "새 프로젝트 이름"); inp.disabled = m.busy;
  note.setAttribute("role", "status");
  const save = hBtn("만들기", () => projectMakeRun(), { cls: "btn sm primary" }); save.id = "projectMakeSave";
  const cancel = hBtn("취소", () => { projectMakeSet(null); const b = $("projectMakeBtn"); if (b) b.focus(); }, { cls: "btn sm", disabled: m.busy });
  const check = () => { // 이미 쓰는 이름 · 임시 이름 꼴은 만들지 않는다(서버 409 · 400)
    m.draft = inp.value;
    const n = projectNameOf(inp.value), why = projectNameTaken(n) ? "같은 이름의 프로젝트가 이미 있습니다" : projectIsTemp(n) ? "「임시 프로젝트 N」 은 이름 없이 올린 문서에 붙이는 임시 이름입니다 — 다른 이름을 넣으세요" : "";
    note.textContent = why; note.hidden = !why;
    save.disabled = m.busy || !n || !!why;
  };
  inp.oninput = check;
  inp.onkeydown = (e) => { if (e.isComposing || e.keyCode === 229) return; if (e.key === "Enter") { e.preventDefault(); projectMakeRun(); } else if (e.key === "Escape") { e.preventDefault(); cancel.click(); } };
  check();
  row.append(inp, save, cancel);
  box.append(row, note, el("p", "project-note", "이름만 정해 둡니다 — 만든 뒤 그 프로젝트 줄의 「파일 올려 시작」 으로 첫 워크플로우를 시작합니다."));
  if (focus) inp.focus();
}

async function projectMakeRun() {
  const m = projectMake, name = m && projectNameOf(m.draft);
  if (!m || m.busy || !name || projectNameTaken(name) || projectIsTemp(name)) return;
  m.busy = true; projectMakeDraw();
  try {
    const r = await api("/api/projects", { method: "POST", headers: H_JSON, body: JSON.stringify({ name }) });
    m.busy = false; projectMake = null; projectMakeDraw();
    toast(`프로젝트 「${r.name}」 을(를) 만들었습니다 — 「파일 올려 시작」 으로 첫 워크플로우를 시작하세요`);
    projectFocusWant = `start:${r.name}`;
    if (!projectInfo.map) projectInfo.map = new Map(); // 읽는 중이면 projectInfoLoad 가 건너뛴다 — 만든 것은 바로 보이게 먼저 넣는다(서버 listing 과 같은 꼴)
    projectInfo.map.set(r.name, { name: r.name, temp: false, settings: null, confirmed: null, versions: [], works: [], tasks: [] });
    projectListDraw();
    await projectInfoLoad(true);
  } catch (e) { m.busy = false; projectMakeDraw(true); toast(`프로젝트를 만들지 못했습니다: ${e.message}`, true); }
}

function projectStartIn(name) { // 「파일 올려 시작」 — 그 프로젝트 이름을 넣고 「새 TASK 시작」 을 펴서 TASK 고르기로
  const create = $("projectCreate");
  if (!create) return;
  create.open = true;
  $("projectStartName").value = name;
  projectDraft = taskScopeKey(); // 다시 그려도 넣은 이름을 지금 프로젝트로 되돌리지 않게
  create.scrollIntoView({ block: "nearest" });
  $("projectStartTask").focus();
}

function projectListDraw() {
  if (projectCombo) projectComboFill(); // 작업 목록을 다시 읽었다(loadWorks) — 열린 프로젝트 고르기 목록의 이름도 새로
  if (!$("projectWorkspace").childElementCount) return;
  if (projectComposing && projectComposing.isConnected) { projectRedrawLater = true; return; } // 한글 조합 중에는 입력칸을 새로 만들지 않는다
  const list = $("projectList"), open = new Set([...list.querySelectorAll("details[open]")].map((d) => d.dataset.group));
  const refocus = projectFocusKeep(list);
  const query = $("projectSearch").value.trim().toLocaleLowerCase(), all = projectGroups(), empties = projectEmptyNames(), names = [...new Set(all.map((g) => g.project).filter(Boolean)), ...empties];
  if (projectEdit && !projectEdit.busy && !names.includes(projectEdit.name)) projectEdit = null; // 다른 곳에서 없어진 프로젝트
  if (projectDrop && !projectDrop.busy && !projectDropTarget(all)) projectDrop = null; // 다른 곳에서 없어진 TASK·문서(지우기 확인 줄 — ② §7 「작업 지우기」)
  const drop = projectDropTarget(all);
  const draftKey = taskScopeKey();
  if ($("projectNewRound").dataset.work !== state.id) $("projectNewRound").hidden = true;
  if (projectDraft !== draftKey) { projectDraft = draftKey; $("projectStartName").value = taskProject(); if (TASK_CATALOG[(state.task || {}).job] && !TASK_CATALOG[state.task.job].soon) $("projectStartTask").value = state.task.job; }
  const groups = all.filter((g) => !query || [g.project, (TASK_CATALOG[g.job] || {}).name || "", ...g.docs.map((w) => w.name)].join(" ").toLocaleLowerCase().includes(query));
  list.textContent = "";
  const projects = [...new Set(groups.map((g) => g.project))].sort((a, b) => a === taskProject() ? -1 : b === taskProject() ? 1 : a.localeCompare(b, "ko"));
  for (const name of projects) {
    const section = el("section", "project-group"), items = groups.filter((g) => g.project === name), head = el("div", "project-group-title");
    head.append(el("strong", null, name || "프로젝트 미지정"));
    if (projectIsTemp(name)) head.append(projectTempTag());
    head.append(el("span", null, `진행 워크플로우 ${items.filter((g) => g.latest).length}`)); section.append(head);
    if (name && projectIsTemp(name)) head.append(projectNameBtn(name)); // 임시 프로젝트 — 「이름 정하기」 를 머리 줄에 바로(⋯ 의 「이름 변경」 과 같은 줄을 연다)
    if (name) { head.append(projectMenuBtn(name, false)); if (projectEdit && projectEdit.name === name) section.append(projectEditEl(name, all, false)); }
    const active = items.filter((g) => g.latest), previous = items.filter((g) => !g.latest).sort((a, b) => b.round - a.round);
    for (const g of active) section.append(projectGroupEl(g, open, drop));
    if (previous.length) {
      const past = el("details", "project-previous"); past.dataset.group = `past:${name}`; past.open = open.has(past.dataset.group) || previous.some((g) => g.current);
      past.append(el("summary", null, `이전 라운드 ${previous.length}개`));
      for (const g of previous) past.append(projectGroupEl(g, open, drop));
      section.append(past);
    }
    list.append(section);
  }
  // 문서 없는 프로젝트(spec_작업 ② §17, 2026-11-13) — 문서가 모두 빠져나가 프로젝트 구성 기록만 남은 것: 문서 있는 프로젝트들 뒤에 한 덩이씩(이름 + 「문서 없음」 + ⋯ = 이름 변경·삭제). 전에는 안 보여 지울 길이 없었다
  const shownEmpty = empties.filter((name) => !query || `${name} 문서 없음`.toLocaleLowerCase().includes(query));
  for (const name of shownEmpty) {
    const section = el("section", "project-group project-empty"), head = el("div", "project-group-title"), info = projectInfo.map.get(name) || {}, vers = (info.versions || []).length;
    section.dataset.projectEmpty = name;
    head.append(el("strong", null, name), el("span", "project-empty-tag", "문서 없음"), projectMenuBtn(name, true));
    section.append(head);
    if (projectEdit && projectEdit.name === name) section.append(projectEditEl(name, all, true));
    const fresh = !info.settings && !vers; // 구성도 버전도 없음 — 「새 프로젝트」 로 만들고 아직 파일을 안 올린 것(② §17 「새 프로젝트」)
    section.append(el("p", "project-note", fresh ? "아직 문서가 없습니다 — 파일을 올려 첫 워크플로우를 시작하세요" : `문서가 없는 프로젝트입니다 — 프로젝트 구성${vers ? `(버전 ${vers}개)` : ""}만 남아 있습니다`));
    const go = hBtn("파일 올려 시작", () => projectStartIn(name), { cls: "btn sm", disabled: projectBusy(), title: `「${name}」 에 워크플로우를 고르고 파일을 올려 시작합니다(아래 「새 워크플로우 시작」)` });
    go.dataset.projectEdit = `start:${name}`; go.dataset.projectAct = "on"; go.dataset.projectStart = name;
    section.append(go);
    list.append(section);
  }
  if (!groups.length && !shownEmpty.length) list.append(el("p", "project-note", query ? "찾는 작업이 없습니다." : "파일을 올려 프로젝트의 첫 워크플로우를 시작하세요."));
  refocus();
}

function projectEmptyNames() { // 문서 없는 프로젝트의 이름들(GET /api/projects 의 works: [] — 읽어 둔 것이 없으면 []). 작업 목록에 그 이름의 문서가 보이면(정보가 낡음) 뺀다
  if (!projectInfo.map) return [];
  const used = new Set(worksList.map((w) => (w.task || {}).project).filter(Boolean));
  return [...projectInfo.map.values()].filter((p) => !(p.works || []).length && !used.has(p.name)).map((p) => p.name).sort((a, b) => a.localeCompare(b, "ko"));
}

function projectGroupEl(g, open, target) { // target = 지우기 확인 줄을 편 곳(projectDropTarget — 없으면 null)
  const row = el("div", "project-task-item" + (g.current ? " current" : ""));
  const button = el("button", "project-task-open"); button.type = "button"; button.dataset.projectWork = g.main.id;
  const label = `${g.project || "프로젝트 미지정"} · ${(TASK_CATALOG[g.job] || {}).name || "워크플로우 미지정"} · Round ${g.round}`;
  button.setAttribute("aria-label", `${label} 열기`);
  if (g.current) button.setAttribute("aria-current", "true");
  const title = el("span", "project-task-name", (TASK_CATALOG[g.job] || {}).name || "워크플로우 미지정");
  const meta = el("span", "project-task-meta", `Round ${g.round} · ${g.docs.length}개 문서${g.current ? " · 현재 작업" : g.latest ? " · 진행 작업" : " · 이전 라운드"}`);
  button.append(title, meta); button.onclick = () => projectOpen(g.main.id);
  // 줄 끝 「지우기」 = 그 라운드의 문서 전부 · 문서 줄 끝 × = 그 문서 하나(문서가 둘 이상인 묶음에만) — 누르면 그 아래 확인 줄(창 없음 · spec_작업 ② §7 「작업 지우기」)
  const head = el("div", "project-task-head"), mine = !!target && target.g.key === g.key;
  head.append(button, projectDropBtn(`round:${g.key}`, "지우기", "btn sm project-task-del", `이 라운드의 문서 ${g.docs.length}개를 지웁니다 — 누르면 아래에서 확인합니다`, `${label} 지우기`));
  row.append(head);
  if (mine && target.round) row.append(projectDropEl(target));
  const files = el("details", "project-task-files"); files.dataset.group = g.key; files.open = open.has(g.key) || (mine && !target.round);
  files.append(el("summary", null, `첨부·참고 파일 ${g.docs.length}개`));
  for (const w of g.docs) {
    const file = hBtn(w.name, () => projectOpen(w.id), { cls: "project-file", title: `${taskName("file", (w.task || {}).file)} · ${w.name}` }); file.dataset.projectFile = w.id;
    if (g.docs.length < 2) { files.append(file); continue; } // 하나뿐이면 줄 끝 「지우기」 와 같은 일
    const line = el("div", "project-file-row");
    line.append(file, projectDropBtn(`file:${w.id}`, "×", "icon project-file-del", "이 문서를 지웁니다 — 누르면 아래에서 확인합니다", `문서 ${w.name} 지우기`));
    files.append(line);
    if (mine && !target.round && target.docs[0].id === w.id) files.append(projectDropEl(target));
  }
  row.append(files);
  return row;
}

// ---- TASK · 문서 지우기(spec_작업 ② §7 「작업 지우기」 · §17, 2026-11-16 사용자 "작업 삭제 기능이 없네.") — TASK 줄 끝 「지우기」(그 라운드의 문서 전부) · 문서 줄 끝 ×(그 문서 하나) → 그 아래 인라인 확인 줄(창 없음).
// 글·지우기 몸통·알림은 시작 화면 최근 작업 줄과 같은 것(app.js worksDropText · worksDelete · worksDropToast). 프로젝트를 통째로 지우는 것은 머리 줄 ⋯ → 삭제(위 projectDelete — 프로젝트 구성 기록도 지운다)
let projectDrop = null; // 확인 줄을 편 곳 하나: {key: "round:<묶음 키>" | "file:<작업 id>", busy}
const projectDropWhat = (g) => `${g.project ? `프로젝트 「${g.project}」 · ` : ""}워크플로우 「${(TASK_CATALOG[g.job] || {}).name || "워크플로우 미지정"}」 · Round ${g.round}`;

function projectDropTarget(groups = projectGroups()) { // 확인 줄을 편 곳 → {g: 묶음, docs: 지울 문서, round: 라운드를 통째로 지우나} · 그 사이 없어졌으면 null
  const d = projectDrop;
  if (!d) return null;
  if (d.key.startsWith("file:")) {
    const id = d.key.slice(5), g = groups.find((x) => x.docs.some((w) => w.id === id));
    return g ? { g, docs: g.docs.filter((w) => w.id === id), round: false } : null;
  }
  const g = groups.find((x) => `round:${x.key}` === d.key);
  return g ? { g, docs: g.docs, round: true } : null;
}

function projectDropBtn(key, text, cls, title, label) { // 확인 줄을 여닫는 단추 — 펼친 것은 진행 중에도 닫을 수 있게 둔다(projectMenuBtn 과 같게)
  const on = !!projectDrop && projectDrop.key === key;
  const b = hBtn(text, () => projectDropSet(on ? "" : key), { cls: cls + (on ? " on" : ""), disabled: (!on && projectBusy()) || (!!projectDrop && projectDrop.busy), title });
  b.setAttribute("aria-expanded", String(on)); b.setAttribute("aria-label", label);
  b.dataset.projectDrop = key; b.dataset.projectEdit = `drop:${key}`;
  if (!on) b.dataset.projectAct = "on";
  return b;
}

function projectDropSet(key) { // key "" = 닫기. 확인 줄은 한 번에 하나 — 프로젝트 ⋯ 줄도 닫는다
  if (projectDrop && projectDrop.busy) return;
  if (key && projectBusy()) { toast(PROJECT_WAIT); return; }
  const was = projectDrop && projectDrop.key;
  projectDrop = key ? { key, busy: false } : null;
  if (key && projectEdit && !projectEdit.busy) projectEdit = null;
  projectFocusWant = key ? "drop-cancel" : was ? `drop:${was}` : "";
  projectListDraw();
}

function projectDropEl(t) { // 줄 아래 확인 줄 — 무엇을 몇 개 · 되살릴 수 없음 · 「지우기」·「취소」(Esc = 취소)
  const busy = projectDrop.busy, box = el("div", "project-edit project-drop"), notes = worksDropNotes(t.docs, t.round), names = worksDropNames(t.docs);
  box.setAttribute("role", "group"); box.setAttribute("aria-label", "지우기 확인");
  box.append(el("p", "project-edit-text", worksDropText(t.docs, projectDropWhat(t.g)) + (notes ? ` — ${notes}` : "")));
  if (names) box.append(names);
  const row = el("div", "project-edit-row");
  const ok = hBtn(busy ? "지우는 중…" : "지우기", () => projectDropRun(), { cls: "btn sm project-danger", disabled: busy, title: DROP_WARN }); ok.dataset.projectEdit = "drop-ok";
  const cancel = hBtn("취소", () => projectDropSet(""), { disabled: busy }); cancel.dataset.projectEdit = "drop-cancel";
  row.append(ok, cancel); box.append(row);
  box.onkeydown = (e) => { if (e.key === "Escape") { e.preventDefault(); projectDropSet(""); } };
  return box;
}

async function projectDropRun() { // 확인 줄의 「지우기」 — 진행 중 저장을 마친 뒤(projectChange 와 같은 차례) 문서마다 DELETE /api/works/{id}(app.js worksDelete)
  const d = projectDrop, t = projectDropTarget();
  if (!d || d.busy || !t) return;
  if (projectBusy(false)) { toast(PROJECT_WAIT); return; }
  const docs = t.docs, what = projectDropWhat(t.g);
  const mates = !!state.id && !docs.some((w) => w.id === state.id) && docs.some((w) => taskSameScope(w)); // 지금 문서는 남고 같은 프로젝트·TASK·라운드의 다른 문서가 지워지나
  let result = null, held = false;
  d.busy = true;
  try {
    while (taskSaveCount) await taskSetPending.catch(() => {});
    if (projectBusy(false)) { toast(PROJECT_WAIT); return; }
    held = projectStarting = true; projectControlsSync(); projectListDraw();
    await divSettingsFlush();
    result = await worksDelete(docs.map((w) => w.id));
  } catch (err) { toast(`지우지 못했습니다: ${err.message}`, true); }
  finally { if (held) projectStarting = false; d.busy = false; projectControlsSync(); }
  if (!result) { projectListDraw(); return; }
  projectDrop = null;
  worksDropToast(docs, result, what);
  const epoch = state.epoch, again = mates && result.done.length > 0;
  if (again) { // 지운 문서에 기대던 화면(취합 상태 · 문서 비교)을 버린다 — 둘째 면은 작업 목록을 다시 읽으면 맞춰진다(docSwitchDraw → peerSync)
    if (typeof gatherState !== "undefined") gatherState = null;
    if (typeof compareReset === "function") compareReset();
  }
  await loadWorks();
  projectInfoLoad(true); // 문서가 다 없어진 프로젝트는 「문서 없음」 줄로(② §17)
  if (again && epoch === state.epoch && !$("paneDiv").hidden) await divShow();
}

function projectRoundFormShow() {
  projectListEnsure();
  const box = $("projectNewRound"); box.hidden = false; box.textContent = "";
  const project = taskProject(), job = (state.task || {}).job, id = state.id;
  box.dataset.work = id;
  box.append(el("strong", null, `${project} · 새 라운드`));
  const label = el("label", null, "시작 문서"), source = el("select"); source.id = "projectRoundSource";
  source.append(new Option("처음 올린 원본 복사", "original"), new Option("현재 수정본 복사", "current")); label.append(source);
  const note = el("p", "project-note", `Round ${taskRound()}의 첨부·참고 문서를 함께 복사합니다. 이전 라운드의 문서와 기록은 남습니다.`);
  const start = hBtn("새 라운드 시작", () => projectNewRound(id, source.value), { cls: "btn primary", disabled: !project || !job || projectBusy() }); start.id = "projectRoundStart";
  const cancel = hBtn("닫기", () => { box.hidden = true; }, { cls: "btn sm" });
  const actions = el("div", "project-round-actions"); actions.append(start, cancel);
  box.append(label, note, actions); box.scrollIntoView({ block: "nearest" }); source.focus();
}

async function projectNewRound(id, source) {
  if (projectBusy() || id !== state.id) return;
  projectStarting = true;
  $("projectRoundStart").disabled = true;
  try {
    await flushAll();
    if (id !== state.id) return;
    if (state.failed.size || state.inflight || state.timers.size) throw new Error("문서 수정 저장을 먼저 마쳐 주세요");
    await divSettingsFlush();
    if (id !== state.id) return;
    const result = await api(`/api/works/${id}/round`, { method: "POST", headers: H_JSON, body: JSON.stringify({ source }) });
    if (state.id !== id) return;
    await load(result.docId);
    await loadWorks();
    $("projectNewRound").hidden = true;
    taskEnter((state.task || {}).job); // 그 TASK 가 처음 여는 보기(app.js taskEnter — task_catalog.js entry)
    toast(`Round ${result.round}를 시작했습니다 — 이전 라운드는 작업 리스트에 보관됩니다`);
  } catch (e) { toast(`새 라운드를 만들지 못했습니다: ${e.message}`, true); }
  finally { projectStarting = false; if ($("projectRoundStart")) $("projectRoundStart").disabled = false; projectControlsSync(); }
}

async function projectUpload(project, job, file) {
  if (!file || projectBusy() || !confirmDiscard()) return;
  const exts = taskAcceptOf(job).filter((x) => x !== "pdf"); // 보통 hwp·hwpx(전과 같다) — 「문서 서식 복사」 는 docx 도(spec_서식복사 ② §1)
  if (!exts.includes(((file.name.match(/\.(\w+)$/) || [])[1] || "").toLowerCase())) { toast(`워크플로우는 ${exts.join("·")} 파일로 시작합니다`, true); return; }
  const epoch = state.epoch;
  projectStarting = true; $("projectStartUpload").disabled = true;
  try {
    await divSettingsFlush();
    if (epoch !== state.epoch) return;
    const fd = new FormData(); fd.append("file", file);
    const result = await api("/api/docs?new=1", { method: "POST", body: fd });
    const doc = await api(`/api/docs/${result.docId}`), guessed = (doc.work && doc.work.task || {}).file;
    const cat = TASK_CATALOG[job], role = cat.file || guessed || "";
    // 이름을 비우면 서버가 임시 이름(「임시 프로젝트 N」 — ② §17 「임시 프로젝트」)을 붙인다
    const started = await api(`/api/works/${result.docId}/start-task`, { method: "POST", headers: H_JSON, body: JSON.stringify(project ? { project, job, file: role } : { project: "", temp: true, job, file: role }) });
    if (epoch !== state.epoch) return;
    await load(result.docId); await loadWorks(); taskEnter(job);
    firstRun();
    const named = (started.task || {}).project || project;
    toast(`${named} · ${cat.name} · Round ${started.round} 시작${started.temp ? " — 임시 이름입니다: 「작업 개요」 의 프로젝트 칸이나 이 목록의 「이름 정하기」 로 이름을 정하세요" : ""}`);
  } catch (e) { toast(`워크플로우를 시작하지 못했습니다: ${e.message}`, true); }
  finally { projectStarting = false; $("projectStartUpload").disabled = false; projectControlsSync(); }
}

async function projectTaskPick(job) {
  const current = (state.task || {}).job;
  if (job === current) return;
  if (!current || !taskProject()) { await taskSet("job", job); return; }
  const selected = document.querySelector('#divBox select[data-task="job"]'); if (selected) selected.value = current;
  if (!job) return;
  const group = projectGroups().find((g) => g.project === taskProject() && g.job === job && g.latest);
  if (group) { await projectOpen(group.main.id); return; }
  showTab("Tasks"); $("projectCreate").open = true; $("projectStartTask").value = job;
  $("projectStartName").value = taskProject(); $("projectStartUpload").focus();
}

// ---- 프로젝트 이름 변경 · 삭제(spec_작업 ② §17, 2026-11-12) — 머리 줄 ⋯ → 인라인 줄(모달 없음)
function projectFocusKeep(list) { // 다시 그리기 전에 부르고, 돌려준 함수를 그린 뒤에 부른다
  const a = document.activeElement, held = a && list.contains(a) ? a.dataset.projectEdit || "" : "";
  const wanted = projectFocusWant, key = wanted || held;
  const range = !wanted && held && a.tagName === "INPUT" ? [a.selectionStart, a.selectionEnd] : null;
  projectFocusWant = "";
  return () => {
    const target = key && [...list.querySelectorAll("[data-project-edit]")].find((x) => x.dataset.projectEdit === key);
    if (!target || target.disabled) return;
    target.focus({ preventScroll: !wanted });
    if (range) target.setSelectionRange(range[0], range[1]); else if (wanted && target.tagName === "INPUT") target.select();
  };
}

function projectEditSet(name, mode, focus = "") { // mode "" = 닫기
  if (projectEdit && projectEdit.busy) return;
  if (mode && projectDrop && !projectDrop.busy) projectDrop = null; // 확인 줄은 한 번에 하나 — TASK·문서 지우기 확인 줄을 닫는다(② §7 「작업 지우기」)
  projectEdit = mode ? { name, mode, draft: projectIsTemp(name) ? "" : name, busy: false } : null; // 임시 프로젝트는 빈 칸에서 — 새 이름을 적는다
  projectFocusWant = focus;
  projectListDraw();
}

function projectEditOpen(name, mode, focus = "") {
  if (projectBusy()) { toast(PROJECT_WAIT); return; }
  if (projectEdit && projectEdit.name === name && projectEdit.mode === mode) return;
  projectEditSet(name, mode, focus);
  projectInfoLoad(true); // 삭제 확인 줄에 쓸 그 프로젝트의 구분 기준 버전 수(② §19) — ⋯ 를 열 때부터 읽어 둔다
}

function projectTempTag() { // 머리 줄 표지 「임시 이름」(색만으로 가르지 않게 글로 — 「문서 없음」 과 같은 꼴)
  const tag = el("span", "project-temp-tag", "임시 이름");
  tag.title = "이름 없이 시작해 붙은 임시 이름입니다 — 「이름 정하기」 나 작업 개요의 프로젝트 칸에 이름을 적으면 바뀝니다(문서 모두 함께)";
  return tag;
}

function projectNameBtn(name) { // 임시 프로젝트 머리 줄의 「이름 정하기」 — ⋯ → 「이름 변경」 과 같은 이름 줄
  const on = !!projectEdit && projectEdit.name === name && projectEdit.mode === "rename";
  const b = hBtn("이름 정하기", () => (on ? projectEditSet(name, "", `name:${name}`) : projectEditOpen(name, "rename", "name")), { cls: "btn sm project-name-set" + (on ? " on" : ""), disabled: !on && projectBusy(), title: `「${name}」 의 이름을 정합니다 — 문서 ${projectDocCount(name)}개가 함께 옮겨 갑니다 · 이미 있는 프로젝트 이름이면 그 프로젝트로 옮깁니다` });
  b.setAttribute("aria-expanded", String(on));
  b.dataset.projectEdit = `name:${name}`; b.dataset.projectNameSet = name;
  if (!on) b.dataset.projectAct = "on";
  return b;
}

function projectMenuBtn(name, empty) { // empty = 문서 없는 프로젝트(이름 변경 · 삭제만 — 초기화는 없다)
  const on = !!projectEdit && projectEdit.name === name;
  const more = hBtn("⋯", () => (on ? projectEditSet(name, "", `menu:${name}`) : projectEditOpen(name, "menu")), { cls: "btn sm project-more" + (on ? " on" : ""), disabled: !on && projectBusy(), title: empty ? "이름 변경 · 삭제" : "이름 변경 · 프로젝트 구성 초기화 · 삭제" });
  more.setAttribute("aria-expanded", String(on)); more.setAttribute("aria-label", `${name} 프로젝트 — 이름 변경, ${empty ? "" : "프로젝트 구성 초기화, "}삭제`);
  more.dataset.projectMenu = name; more.dataset.projectEdit = `menu:${name}`;
  if (!on) more.dataset.projectAct = "on"; // 펼친 것은 진행 중에도 닫을 수 있게 둔다
  return more;
}

function projectEditEl(name, all, empty) { // empty = 문서 없는 프로젝트 — 초기화 단추가 없고 삭제 확인 줄의 단추는 「삭제」 하나(② §17)
  const e = projectEdit, busy = projectBusy(), box = el("div", "project-edit");
  const info = projectDivisionOf(name), vers = info ? info.versions.length : 0; // 그 프로젝트의 프로젝트 구성(값·확정·버전 — GET /api/projects · 지금 프로젝트는 화면 값). 읽어 둔 것이 없으면 null(오면 projectInfoLoad 가 이 줄을 다시 그린다)
  const count = all.filter((g) => g.project === name).reduce((n, g) => n + g.docs.length, 0); // 문서 수 — 검색 필터와 무관하게 전체에서 센다
  const act = (text, key, fn, { cls = "btn sm", title = "" } = {}) => { const b = hBtn(text, fn, { cls, title, disabled: busy }); b.dataset.projectEdit = key; b.dataset.projectAct = "on"; return b; };
  const cancel = (focus) => { const b = hBtn("취소", () => projectEditSet(name, "menu", focus)); b.dataset.projectEdit = "cancel"; return b; };
  const menu = el("div", "project-edit-row");
  const rename = act("이름 변경", "rename", () => projectEditOpen(name, "rename", "name")); rename.dataset.projectRename = name;
  const del = act("삭제", "delete", () => projectEditOpen(name, "delete", "cancel")); del.dataset.projectDelete = name;
  menu.append(rename);
  if (!empty) { // 「초기화」 = 프로젝트 구성(값·확정·버전)만 지운다 — 문서는 프로젝트에 그대로. 지울 것이 없으면 꺼 둔다
    const none = !!info && !info.values && !info.confirmed && !vers;
    const reset = act("초기화", "reset", () => projectEditOpen(name, "reset", "cancel"), { title: none ? "지울 프로젝트 구성이 없습니다(구성 값·확정·버전 없음)" : "프로젝트 구성(구성 값·확정·버전)만 지웁니다 — 문서는 프로젝트에 그대로 남습니다" });
    reset.dataset.projectReset = name;
    if (none) { reset.dataset.projectAct = "off"; reset.disabled = true; }
    menu.append(reset);
  }
  menu.append(del); box.append(menu);
  if (e.mode === "rename") { // 이름 줄 — Enter 저장 · Esc 취소
    const row = el("div", "project-edit-row"), note = el("p", "project-note project-edit-note"), inp = el("input"), temp = projectIsTemp(name);
    inp.type = "text"; inp.maxLength = 60; inp.value = e.draft; inp.placeholder = temp ? "프로젝트 이름(정할 이름)" : "새 프로젝트 이름"; inp.setAttribute("aria-label", `${name} 프로젝트의 새 이름`); inp.dataset.projectEdit = "name";
    note.setAttribute("role", "status");
    const save = act("저장", "save", () => projectRename(), { cls: "btn sm primary" });
    const check = () => { // 임시 프로젝트는 이미 있는 이름도 된다 — 그 프로젝트로 문서를 모두 옮긴다(② §17 「임시 프로젝트」). 이름 있는 프로젝트는 전처럼 합치지 않는다
      e.draft = inp.value;
      const n = projectNameOf(inp.value), taken = projectNameTaken(n, name), join = temp && taken, bad = (taken && !temp) || (!taken && projectIsTemp(n) && n !== name);
      note.textContent = join ? `이미 있는 프로젝트입니다 — 「옮기기」 를 누르면 이 임시 프로젝트의 문서 ${projectDocCount(name)}개를 「${n}」 로 옮깁니다`
        : bad ? (taken ? "같은 이름의 프로젝트가 이미 있습니다" : "「임시 프로젝트 N」 은 임시 이름입니다 — 다른 이름을 넣으세요") : "";
      note.hidden = !note.textContent; note.classList.toggle("is-info", join);
      save.textContent = join ? "옮기기" : "저장";
      save.dataset.projectAct = !n || bad ? "off" : "on"; save.disabled = projectBusy() || !n || bad;
    };
    inp.oninput = check; check();
    inp.onkeydown = (ev) => { if (ev.isComposing || ev.keyCode === 229) return; if (ev.key === "Enter") { ev.preventDefault(); projectRename(); } else if (ev.key === "Escape") { ev.preventDefault(); projectEditSet(name, "menu", "rename"); } };
    inp.addEventListener("compositionstart", () => { projectComposing = inp; });
    inp.addEventListener("compositionend", () => { projectComposing = null; if (projectRedrawLater) { projectRedrawLater = false; setTimeout(projectListDraw, 0); } }); // 마지막 input 이벤트 뒤에 그린다
    row.append(inp, save, cancel("rename")); box.append(row, note);
  }
  if (e.mode === "reset" && !empty) { // 초기화 확인 줄(인라인 — 삭제 확인 줄과 같은 방식)
    const row = el("div", "project-edit-row");
    row.append(act("초기화", "reset-ok", () => projectReset(), { cls: "btn sm project-danger", title: "프로젝트 구성(구성 값·확정·버전)을 지웁니다 — 되살릴 수 없습니다" }), cancel("reset"));
    box.append(el("p", "project-edit-text", `「${name}」 의 프로젝트 구성을 초기화할까요? 구성 값·확정${vers ? `·버전 ${vers}개가` : "이"} 지워집니다 — 문서 ${count}개는 프로젝트에 그대로 남고, 문서에 이미 반영한 내용은 바뀌지 않습니다`), row);
  }
  if (e.mode === "delete" && empty) { // 문서 없는 프로젝트 — 지울 것은 프로젝트 구성 기록뿐(요청은 「프로젝트만 해제」 와 같다)
    const row = el("div", "project-edit-row");
    row.append(act("삭제", "remove", () => projectDelete("keep"), { cls: "btn sm project-danger", title: "프로젝트 구성 기록(구성 값·확정·버전)을 지웁니다 — 되살릴 수 없습니다" }), cancel("delete"));
    box.append(el("p", "project-edit-text", `「${name}」 프로젝트를 지울까요? 문서는 없고 프로젝트 구성${vers ? `(버전 ${vers}개)` : ""}만 지워집니다`), row);
  } else if (e.mode === "delete") { // 삭제 확인 줄
    const row = el("div", "project-edit-row");
    row.append(act("프로젝트만 해제", "keep", () => projectDelete("keep"), { title: "문서는 남고 프로젝트 미지정이 됩니다 · 프로젝트 구성(구성 값·확정·버전)은 지워집니다" }),
      act("문서까지 삭제", "purge", () => projectDelete("delete"), { cls: "btn sm project-danger", title: "올린 원본·편집 상태·기록이 모두 지워지고 되살릴 수 없습니다" }), cancel("delete"));
    box.append(el("p", "project-edit-text", `「${name}」 프로젝트를 지울까요? 문서 ${count}개(이전 라운드 포함)${vers ? ` · 프로젝트 구성 버전 ${vers}개도 지워집니다` : ""}`), row); // 버전도 프로젝트 기록과 함께 지워진다(② §19)
  }
  return box;
}

async function projectChange(request, failText, e = projectEdit) { // 진행 중 저장을 마치고 요청 하나를 보낸다. 실패하면 알리고 null — e = 바쁨 표시를 둘 곳(작업 리스트의 펼친 줄 · 작업 개요의 프로젝트 칸은 제 것)
  if (!e || e.busy) return null;
  if (projectBusy(false)) { toast(PROJECT_WAIT); return null; }
  e.busy = true;
  try {
    while (taskSaveCount) await taskSetPending.catch(() => {});
    if (projectBusy(false)) { toast(PROJECT_WAIT); return null; }
    projectStarting = true; projectControlsSync();
    await divSettingsFlush();
    return await request();
  } catch (err) { toast(`${failText}: ${err.message}`, true); loadWorks(); return null; }
  finally { projectStarting = false; e.busy = false; projectControlsSync(); }
}

async function projectApplied(ids, patch, regroup = !patch.project) { // 지금 연 문서가 대상이면 화면의 task 를 맞추고 목록을 다시 읽는다 — regroup = 같은 프로젝트의 문서가 바뀜(떠남 · 임시 프로젝트를 다른 프로젝트로 옮김)
  const mine = ids.includes(state.id), epoch = state.epoch;
  if (mine) {
    state.task = { ...state.task, ...patch };
    taskDraw(); divReset();
    if (regroup) { // 프로젝트를 떠나거나 다른 프로젝트로 옮기면 같은 프로젝트 문서에 기대던 화면도 걷는다(taskSetNow 와 같게)
      if (typeof peerPick !== "undefined") peerPick = null;
      if (typeof gatherState !== "undefined") gatherState = null;
      if (typeof compareReset === "function") compareReset();
    }
  }
  await loadWorks();
  if (mine && epoch === state.epoch) { taskDraw(); if (!$("paneDiv").hidden) await divShow(); }
}

async function projectRename() {
  const e = projectEdit;
  if (!e || e.mode !== "rename") return;
  const name = e.name, next = projectNameOf(e.draft), temp = projectIsTemp(name);
  if (!next || (!temp && projectNameTaken(next, name)) || (projectIsTemp(next) && next !== name && !projectNameTaken(next, name))) return;
  if (next === name) { projectEditSet(name, "menu", "rename"); return; }
  const result = await projectChange(() => projectRenameSend(name, next), temp ? "프로젝트 이름을 정하지 못했습니다" : "프로젝트 이름을 바꾸지 못했습니다");
  if (!result) return;
  projectEdit = null; projectFocusWant = `menu:${result.name}`;
  await projectRenamed(name, result);
}

const projectRenameSend = (name, next) => api(`/api/projects/${encodeURIComponent(name)}`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ name: next }) });

async function projectRenamed(old, result) { // 이름 변경 · 임시 프로젝트 이름 정하기의 뒤처리 — 알림 · 지금 문서의 task(옮겨 가면 라운드도 바뀐다 — 응답 tasks) · 목록
  if (projectInfo.map) projectInfo.map.delete(old); // 옛 이름의 정보는 버린다 — 새 이름은 아래에서 다시 읽는다
  const n = result.works.length;
  toast(result.join ? `임시 프로젝트 「${old}」 의 문서 ${n}개를 프로젝트 「${result.name}」 로 옮겼습니다`
    : projectIsTemp(old) ? `프로젝트 이름을 「${result.name}」 으로 정했습니다 — 문서 ${n}개` : `프로젝트 이름을 「${result.name}」으로 바꿨습니다`);
  const mine = result.tasks && result.tasks[state.id];
  await projectApplied(result.works, mine ? { project: mine.project, round: mine.round || 1 } : { project: result.name }, !!result.join);
  projectInfoLoad(true);
}

// 작업 개요의 프로젝트 칸(app.js taskRow)에서 임시 프로젝트에 이름을 적음 — 이 문서만 옮기지 않고 임시 프로젝트를 통째로(② §17 「임시 프로젝트」). → 했나
async function projectTempName(old, raw) {
  const next = projectNameOf(raw);
  if (!next || next === old || !projectIsTemp(old)) return false;
  if (projectIsTemp(next) && !projectNameTaken(next, old)) { toast("「임시 프로젝트 N」 은 임시 이름입니다 — 다른 이름을 넣으세요", true); return false; }
  const result = await projectChange(() => projectRenameSend(old, next), "프로젝트 이름을 정하지 못했습니다", { busy: false });
  if (!result) return false;
  await projectRenamed(old, result);
  return true;
}

async function projectReset() { // 「초기화」 의 확인 — 프로젝트 구성(구성 값·확정·버전)만 지운다: DELETE /api/projects/{이름}?docs=reset(spec_작업 ② §17). 문서·프로젝트 소속·이미 반영한 내용은 그대로
  const e = projectEdit;
  if (!e || e.mode !== "reset") return;
  const name = e.name;
  const result = await projectChange(() => api(`/api/projects/${encodeURIComponent(name)}?docs=reset`, { method: "DELETE" }), "프로젝트 구성을 초기화하지 못했습니다");
  if (!result) return;
  projectEdit = null; projectFocusWant = `menu:${name}`;
  if (projectInfo.map && projectInfo.map.has(name)) projectInfo.map.set(name, { ...projectInfo.map.get(name), settings: null, confirmed: null, versions: [] });
  toast(`프로젝트 「${name}」 의 구성을 초기화했습니다 — 새로 만드세요`);
  const mine = !!state.id && taskProject() === name, epoch = state.epoch;
  if (mine) { // 지금 연 문서가 그 프로젝트 — 화면의 구성 입력·확정·계획을 버리고 다시 읽는다(이관의 다른 칸 자료 · 취합 상태도)
    divReset();
    if (typeof gatherState !== "undefined") gatherState = null;
  }
  await loadWorks();
  projectInfoLoad(true);
  if (mine && epoch === state.epoch && !$("paneDiv").hidden) await divShow();
}

async function projectDelete(docs) {
  const e = projectEdit;
  if (!e || e.mode !== "delete") return;
  const name = e.name;
  const result = await projectChange(() => api(`/api/projects/${encodeURIComponent(name)}?docs=${docs}`, { method: "DELETE" }), "프로젝트를 지우지 못했습니다");
  if (!result) return;
  projectEdit = null;
  if (projectInfo.map) projectInfo.map.delete(name); // 프로젝트 구성 기록도 지워졌다 — 문서 없는 프로젝트 줄·고르기 목록에서 바로 뺀다
  if (docs === "delete") {
    if (result.works.includes(state.id)) closeDoc();
    toast(`프로젝트 「${name}」와 문서 ${result.works.length}개를 지웠습니다`);
    await loadWorks();
  } else if (!result.works.length) { // 문서 없는 프로젝트 — 프로젝트 구성 기록만 지웠다
    toast(`프로젝트 「${name}」을(를) 지웠습니다 — 문서는 없었고 프로젝트 구성만 지웠습니다`);
    await loadWorks();
  } else {
    toast(`프로젝트 「${name}」을(를) 해제했습니다 — 문서 ${result.works.length}개는 프로젝트 미지정으로 남습니다`);
    await projectApplied(result.works, { project: "", round: 1 });
  }
  projectInfoLoad(true);
}

// ---- 프로젝트 고르기 목록(spec_작업 ② §19, 2026-11-13 사용자 "프로젝트에서트 작업리스트 중 에 있는 프로젝트가 리스트에 있어야 하는데 없어") — 브라우저 datalist 대신 쓰는 자체 목록.
// 칸(input[role=combobox])을 누르거나 ↓(Alt+↓) · 글자를 치면(포커스만으로는 열지 않는다) → 작업 리스트의 모든 프로젝트(작업 목록의 이름 ∪ GET /api/projects)를 보인다 — 지금 적힌 값으로 거르지 않고, 글자를 고치기 시작하면 그 글자가 든 이름만.
// 줄 = 이름 + 구분 기준 표지(확정 · 있음 · 없음) + 「버전 N」 + 「지금」 · 어느 이름과도 같지 않은 글이면 끝 줄 「「글」 새 프로젝트로」. ↓↑ 이동 · Enter 고름 · Esc 닫고 값 되돌림 · 바깥 누름·포커스 나감 = 닫음.
// 목록(div[role=listbox])은 body 에 고정 위치로 띄운다(패널의 overflow 에 안 잘리게) — 한 번에 하나. 쓰는 곳: 작업 개요의 프로젝트 칸(app.js taskRow — #taskProjectList) · 작업 리스트 「새 TASK 시작」(#projectStartList)
const projectInfo = { map: null, at: 0, busy: false }; // GET /api/projects — 이름 → {settings, confirmed, versions …}(구분 기준 표지 · 들어가기 전 알림)
const projectComboState = new WeakMap(); // 칸 → {opts, origin 포커스 때의 값(Esc 가 되돌림), sent 정한 뒤(고름·Enter) 아직 글을 안 고침}
let projectCombo = null; // 열린 목록 {inp, opts, list, rows [{key, name, fresh}], active 고른 줄(-1 = 없음), typed 글자를 고치기 시작함}

async function projectInfoLoad(force = false) { // 목록을 열 때마다(2초 안이면 다시 안 읽음 — force 면 읽음) — 온 뒤에 열린 목록의 표지를 채운다
  if (projectInfo.busy || (!force && Date.now() - projectInfo.at < 2000)) return;
  projectInfo.busy = true;
  try { const r = await api("/api/projects"); projectInfo.map = new Map((r.projects || []).map((p) => [p.name, p])); projectInfo.at = Date.now(); }
  catch { /* 표지 없이 이름만 보인다 */ }
  finally { projectInfo.busy = false; }
  projectListDraw(); // 열린 고르기 목록의 표지 · 작업 리스트의 문서 없는 프로젝트 · 확인 줄의 버전 수(작업 리스트를 아직 안 열었으면 고르기 목록만)
}

function projectDivisionNow() { // 지금 문서가 쓰는 구분 기준 {values, confirmed, versions} | null(아직 안 읽음) — values = 저장된 입력 설정이 있으면 지금 입력 값(아직 저장 안 된 입력도 따라간다), 없으면 null
  const v = dv.view, sh = v && v.projectSharing;
  return v ? { values: v.settings && dv.values ? divValues() : null, confirmed: v.confirmed, versions: (sh && sh.shared && v.versions) || [] } : null;
}
function projectDivisionOf(name) { // 그 프로젝트의 구분 기준 {values, confirmed, versions} | null(아직 모름 — 표지를 안 붙인다)
  const v = dv.view, sh = v && v.projectSharing;
  if (sh && sh.shared && sh.project === name) return projectDivisionNow(); // 지금 프로젝트 — 화면이 가진 것이 가장 새것(프로젝트 칸 아래의 구분 기준 줄과 같은 값)
  const p = (projectInfo.map && projectInfo.map.get(name)) || (dv.projects || []).find((x) => x.name === name);
  return p ? { values: p.settings && p.settings.values, confirmed: p.confirmed, versions: p.versions || [] } : null;
}
// 표지의 뜻(spec_작업 ② §19 — 고르기 목록의 줄과 프로젝트 칸 아래 구분 기준 줄이 같이 쓴다): 없음 = 구성 값이 없음 · 확정 = 확정 기록이 있고 그 값이 지금 구성 값과 같음(divConfirmKey — 당해 차년도는 빼고) · 있음 = 값은 있고 확정 전이거나 확정 뒤 바뀜
const projectDivisionTag = (d) => (!d || !d.values ? ["none", "프로젝트 구성 없음"] : divConfirmValid(d.values, d.confirmed) ? ["confirmed", "프로젝트 구성 확정"] : ["has", "프로젝트 구성 있음"]);

function projectComboNames() { // 모든 프로젝트 — 지금 프로젝트가 맨 앞, 나머지는 이름 차례
  const names = new Set(worksList.map((w) => (w.task || {}).project).filter(Boolean)), cur = taskProject();
  for (const n of (projectInfo.map ? projectInfo.map.keys() : [])) names.add(n);
  return [...names].sort((a, b) => (a === cur ? -1 : b === cur ? 1 : a.localeCompare(b, "ko")));
}

function projectComboFill() { // 줄을 다시 채운다 — 열 때 · 글자를 고칠 때 · 작업 목록·프로젝트 목록이 온 뒤
  const c = projectCombo;
  if (!c) return;
  if (!c.inp.isConnected) { projectComboClose(); return; }
  if (c.pressing) { c.refill = true; return; } // 줄을 누르는 중(mousedown ~ mouseup) — 줄을 새로 만들면 그 누름이 사라진다: 뗀 뒤에 채운다(projectComboRelease)
  const keep = c.active >= 0 && c.rows[c.active] ? c.rows[c.active].key : "", cur = taskProject(), empties = new Set(projectEmptyNames()); // empties = 문서 없는 프로젝트(② §17 — 표지 「문서 없음」)
  const text = projectNameOf(c.inp.value), q = c.typed ? text.toLocaleLowerCase() : "", all = projectComboNames();
  c.rows = all.filter((n) => !q || n.toLocaleLowerCase().includes(q)).map((n) => ({ key: `n:${n}`, name: n }));
  if (c.typed && text && !all.includes(text)) c.rows.push({ key: "new", name: text, fresh: true });
  c.list.textContent = "";
  c.rows.forEach((row, i) => {
    const o = el("div", "project-combo-option" + (row.fresh ? " is-new" : ""));
    o.id = `${c.list.id}-opt-${i}`;
    o.setAttribute("role", "option");
    o.dataset.project = row.name;
    if (row.fresh) { o.dataset.projectNew = "1"; o.append(el("span", "project-combo-name", `「${row.name}」 새 프로젝트로`)); }
    else {
      o.append(el("span", "project-combo-name", row.name));
      const d = projectDivisionOf(row.name);
      if (d) {
        const [kind, label] = projectDivisionTag(d), tag = el("span", `project-combo-tag is-${kind}`, label);
        tag.dataset.division = kind;
        if (d.values) tag.title = divValuesText(d.values);
        o.append(tag);
        if (d.versions.length) o.append(el("span", "project-combo-tag", `버전 ${d.versions.length}개`));
      }
      if (empties.has(row.name)) o.append(el("span", "project-combo-tag is-empty", "문서 없음"));
      if (row.name === cur) o.append(el("span", "project-combo-tag is-now", "지금"));
    }
    o.onclick = () => projectComboPick(i);
    c.list.append(o);
  });
  if (!c.rows.length) c.list.append(el("div", "project-combo-empty", all.length ? "맞는 프로젝트가 없습니다" : "아직 프로젝트가 없습니다 — 이름을 적으면 새 프로젝트가 됩니다"));
  c.active = keep ? c.rows.findIndex((r) => r.key === keep) : -1;
  projectComboMark();
  projectComboPlace();
}

function projectComboMark() { // 고른 줄 표시 — aria-activedescendant(포커스는 칸에 그대로)
  const c = projectCombo;
  if (!c) return;
  [...c.list.querySelectorAll('[role="option"]')].forEach((o, i) => {
    o.classList.toggle("active", i === c.active);
    o.setAttribute("aria-selected", String(i === c.active));
    if (i === c.active) o.scrollIntoView({ block: "nearest" });
  });
  if (c.active >= 0) c.inp.setAttribute("aria-activedescendant", `${c.list.id}-opt-${c.active}`); else c.inp.removeAttribute("aria-activedescendant");
}

function projectComboPlace() { // 칸 바로 아래(자리가 없으면 위) — 창 안에 들어가게
  const c = projectCombo;
  if (!c) return;
  if (!c.inp.isConnected) { projectComboClose(); return; }
  const r = c.inp.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  if (!r.width || r.bottom < 0 || r.top > vh) { projectComboClose(); return; } // 칸이 감춰졌거나 화면 밖으로 굴러 나갔다
  const w = Math.min(Math.max(r.width, 240), vw - 16), below = vh - r.bottom - 8, above = r.top - 8, up = below < 140 && above > below, s = c.list.style;
  s.width = `${w}px`;
  s.left = `${Math.max(8, Math.min(r.left, vw - w - 8))}px`;
  s.maxHeight = `${Math.max(80, Math.min(280, up ? above : below))}px`;
  s.top = up ? "" : `${r.bottom + 2}px`;
  s.bottom = up ? `${vh - r.top + 2}px` : "";
}

const projectComboOutside = (e) => { const c = projectCombo; if (c && (!c.inp.isConnected || (e.target !== c.inp && !c.list.contains(e.target)))) projectComboClose(); };
const projectComboScroll = (e) => { const c = projectCombo; if (c && !(e.target instanceof Node && c.list.contains(e.target))) projectComboPlace(); }; // 목록 안에서 굴리는 것은 그대로
const projectComboRelease = () => { // 목록에서 누른 것을 뗌 — 미뤄 둔 채우기는 그 누름(click)이 처리된 뒤에
  const c = projectCombo;
  if (!c || !c.pressing) return;
  c.pressing = false;
  if (c.refill) { c.refill = false; setTimeout(() => { if (projectCombo === c) projectComboFill(); }, 0); }
};

function projectComboOpen(inp) {
  const st = projectComboState.get(inp);
  if (!st || (projectCombo && projectCombo.inp === inp)) return;
  projectComboClose();
  const list = el("div", "project-combo-list");
  list.id = st.opts.list;
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "프로젝트 고르기");
  list.addEventListener("mousedown", (e) => { e.preventDefault(); if (projectCombo && projectCombo.list === list) projectCombo.pressing = true; }); // 목록을 눌러도 칸의 포커스를 잃지 않게(포커스가 나가면 닫힌다)
  document.body.append(list);
  projectCombo = { inp, opts: st.opts, list, rows: [], active: -1, typed: false, pressing: false, refill: false };
  inp.setAttribute("aria-expanded", "true");
  document.addEventListener("pointerdown", projectComboOutside, true);
  window.addEventListener("mouseup", projectComboRelease, true);
  window.addEventListener("scroll", projectComboScroll, true);
  window.addEventListener("resize", projectComboPlace);
  projectComboFill();
  projectInfoLoad();
}

function projectComboClose() {
  const c = projectCombo;
  if (!c) return;
  projectCombo = null;
  c.list.remove();
  c.inp.setAttribute("aria-expanded", "false");
  c.inp.removeAttribute("aria-activedescendant");
  document.removeEventListener("pointerdown", projectComboOutside, true);
  window.removeEventListener("mouseup", projectComboRelease, true);
  window.removeEventListener("scroll", projectComboScroll, true);
  window.removeEventListener("resize", projectComboPlace);
}

function projectComboPick(i) { // 줄을 고름(누름 · Enter) — 칸에 그 이름을 넣고 닫는다. 저장은 칸 쪽(opts.commit)이 한다
  const c = projectCombo, row = c && c.rows[i];
  if (!row) return;
  const st = projectComboState.get(c.inp);
  c.inp.value = row.name;
  if (st) { st.origin = row.name; st.sent = true; }
  projectComboClose();
  if (c.opts.commit) c.opts.commit();
}

function projectComboAttach(inp, opts) { // opts {list 목록의 id, commit? 고르거나 Enter 로 정한 뒤 부름 — 값은 inp.value}
  const st = { opts, origin: inp.value, sent: false };
  projectComboState.set(inp, st);
  inp.classList.add("project-combo");
  inp.autocomplete = "off";
  for (const [k, v] of [["role", "combobox"], ["aria-autocomplete", "list"], ["aria-haspopup", "listbox"], ["aria-expanded", "false"], ["aria-controls", opts.list]]) inp.setAttribute(k, v);
  const mine = () => (projectCombo && projectCombo.inp === inp ? projectCombo : null);
  inp.addEventListener("focus", () => { st.origin = inp.value; st.sent = false; }); // 포커스만으로는 열지 않는다(창을 다시 활성화하거나 다시 그린 뒤 포커스를 돌려줄 때 저절로 열리지 않게 — ② §19)
  inp.addEventListener("click", () => projectComboOpen(inp)); // 칸을 누름 → 열림(그 밖에 ↓ · Alt+↓ · 글자를 침)
  inp.addEventListener("blur", () => { if (mine()) projectComboClose(); });
  inp.addEventListener("input", () => { // 글자를 고치기 시작 — 그 글자가 든 이름만(한글 조합 중에도 거른다)
    st.sent = false;
    projectComboOpen(inp);
    const c = mine();
    if (!c) return;
    c.typed = true; c.active = -1;
    projectComboFill();
  });
  inp.addEventListener("keydown", (e) => {
    if (e.isComposing || e.keyCode === 229) return; // 한글 조합 중 Enter·화살표는 조합에 맡긴다
    const c = mine();
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!c) { projectComboOpen(inp); return; } // ↓ · Alt+↓ — 목록 열기
      if (e.altKey) { if (e.key === "ArrowUp") projectComboClose(); return; }
      const n = c.rows.length;
      if (!n) return;
      c.active = e.key === "ArrowDown" ? (c.active + 1) % n : c.active <= 0 ? n - 1 : c.active - 1;
      projectComboMark();
    } else if (e.key === "Enter") {
      if (c && c.active >= 0) { e.preventDefault(); projectComboPick(c.active); return; }
      if (c) projectComboClose();
      if (opts.commit) { e.preventDefault(); st.sent = true; opts.commit(); } // 적은 글 그대로 그 이름으로(전과 같다) — commit 이 없는 칸(폼)은 폼의 Enter 에 맡긴다
    } else if (e.key === "Escape") {
      if (c) { e.preventDefault(); e.stopPropagation(); projectComboClose(); }
      if (inp.value !== st.origin) inp.value = st.origin;
    }
  });
}

// 패널을 다시 그리기 전에 부르고(app.js divRender), 돌려준 함수를 다 그린 뒤에 부른다(projectFocusKeep 과 같은 방식) — 프로젝트 칸에 쓰던 글·포커스·열린 고르기 목록, 버전 이름 줄의 포커스를 새로 만든 칸으로 옮긴다.
// 정한 뒤(sent — 고름·Enter)의 글은 옮기지 않는다: 저장이 안 됐으면 칸은 지금 프로젝트 이름으로 돌아간다
function projectPanelKeep(root) {
  const a = document.activeElement;
  if (!a || a.tagName !== "INPUT" || !root.contains(a)) return null;
  const range = [a.selectionStart, a.selectionEnd];
  if (a.dataset.versionName) return () => { const inp = root.querySelector("input[data-version-name]"); if (inp && !inp.disabled) { inp.focus({ preventScroll: true }); try { inp.setSelectionRange(range[0], range[1]); } catch { /* 자리만 못 옮김 */ } } };
  if (a.dataset.task !== "project") return null;
  const st = projectComboState.get(a) || {}, c = projectCombo && projectCombo.inp === a ? projectCombo : null;
  const kept = { text: st.sent ? null : a.value, open: !!c, typed: !!(c && c.typed), active: c && c.active >= 0 && c.rows[c.active] ? c.rows[c.active].key : "" };
  if (c) projectComboClose();
  return () => {
    const inp = root.querySelector('input[data-task="project"]');
    if (!inp || inp.disabled) return;
    inp.focus({ preventScroll: true });
    if (kept.text == null) return;
    inp.value = kept.text;
    try { inp.setSelectionRange(range[0], range[1]); } catch { /* 자리만 못 옮김 */ }
    if (!kept.open) return;
    projectComboOpen(inp);
    if (!projectCombo || projectCombo.inp !== inp) return;
    projectCombo.typed = kept.typed;
    projectComboFill();
    projectCombo.active = kept.active ? projectCombo.rows.findIndex((r) => r.key === kept.active) : -1;
    projectComboMark();
  };
}

// ---- 구분 기준 버전(spec_작업 ② §19, 2026-11-13 사용자 "구분기준 버전을 추가할 수도 있고, .. 차년도 별로 있을 수 있다고 생각함") — 프로젝트의 구분 기준을 이름 붙여 남긴 것.
// 프로젝트가 함께 쓰는 지금 구분 기준(공유 입력 + 확정)은 하나 그대로이고, 버전을 「적용」 하면 지금 구분 기준이 그 값이 된다(입력 + 확정 — 같은 프로젝트의 최신 라운드 TASK 들이 함께 바뀜).
// 화면 = 구분 기준 있음/없음 줄 아래 한 줄(.project-versions — 공유 중일 때만): 고르기 · 「적용」 · 「버전 추가」(인라인 이름 줄) · 「삭제」(인라인 확인 줄). 모달 없음. 자료 = dv.view.versions(옛 서버면 없음 = []).
// 세 요청(POST …/divisions/versions · POST …/versions/{id}/apply · DELETE …/versions/{id})의 응답은 GET …/divisions 와 같은 몸통 — divConfirm 처럼 dv.view 에 얹는다
const PROJECT_VERSION_WAIT = "진행 중인 작업이 끝난 뒤 프로젝트 구성 버전을 바꿀 수 있습니다";
let projectVer = { key: "", pick: "", naming: false, draft: null, deleting: false, busy: false }; // 버전 줄의 화면 상태 — 고른 버전 · 이름 줄(쓰던 글) · 삭제 확인 줄 · 요청 중. 문서·프로젝트가 바뀌면 새로
function projectVerState() {
  const key = `${state.id}|${taskProject()}`;
  if (projectVer.key !== key) projectVer = { key, pick: "", naming: false, draft: null, deleting: false, busy: false };
  return projectVer;
}
const projectVersions = () => { const v = dv.view, sh = v && v.projectSharing; return sh && sh.shared ? v.versions || [] : null; }; // null = 공유 중이 아님(버전 줄 없음)
const projectVersionOff = () => projectBusy() || dv.busy || projectVer.busy;
const projectVersionLabel = (x, cur) => `${x.name} — 당해 ${Math.max(1, Number((x.values || {}).current) || 1)}차년도 · ${divValuesText(x.values)}${divCanon(x.values) === cur ? " · 지금" : ""}`; // 당해 차년도만 다른 버전도 글로 갈리게 · 「 · 지금」 = 지금 입력과 같음(당해 차년도까지)
const projectVersionCan = () => !!(dv.view && (dv.view.settings || dv.dirty)); // 지금 입력 값이 있다(저장된 설정이 있거나 이 화면에서 입력함)

function projectVersionsEl() {
  if (!projectVersions()) return null;
  const box = el("div", "project-versions");
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "프로젝트 구성 버전");
  projectVersionsFill(box);
  return box;
}

function projectVersionsFill(box) {
  const vs = projectVersions() || [], st = projectVerState(), off = projectVersionOff(), cur = dv.values ? divCanon(divValues()) : "";
  if (st.pick && !vs.some((x) => x.id === st.pick)) { st.pick = ""; st.deleting = false; }
  const picked = vs.find((x) => x.id === st.pick) || null;
  box.textContent = "";
  const row = el("div", "project-versions-row project-versions-main"), controls = el("div", "project-versions-controls"), act = (text, key, fn, opt) => { const b = hBtn(text, fn, { cls: "btn sm", ...opt }); b.dataset[key] = "1"; return b; };
  row.append(el("span", "project-versions-label", "버전"));
  const add = act("버전 추가", "versionAdd", () => projectVersionNaming(true), { disabled: off || !projectVersionCan(),
    title: "지금 입력 값(단계·차년도·기관 · 당해 차년도)을 이름 붙여 이 프로젝트의 구성 버전으로 남깁니다 — 차년도마다 하나씩 둘 수 있습니다" });
  if (vs.length) {
    const sel = el("select");
    sel.dataset.divisionVersion = "1";
    sel.setAttribute("aria-label", "프로젝트 구성 버전 고르기");
    sel.append(new Option("버전 고르기", ""));
    for (const x of vs) sel.append(new Option(projectVersionLabel(x, cur), x.id));
    sel.value = st.pick;
    sel.disabled = off;
    sel.onchange = () => { st.pick = sel.value; st.deleting = false; projectVersionsDraw("select[data-division-version]"); };
    controls.append(sel,
      act("적용", "versionApply", () => projectVersionApply(st.pick), { disabled: off || !picked,
        title: "고른 버전을 지금 프로젝트 구성으로 — 입력 값이 그 값이 되고 프로젝트에 확정합니다(같은 프로젝트의 최신 라운드 워크플로우들이 함께 바뀜 · 문서는 변경 계획 → 반영으로)" }));
    const actions = el("div", "project-versions-actions");
    actions.append(add,
      act("삭제", "versionDelete", () => { st.deleting = true; st.naming = false; projectVersionsDraw("[data-version-delete-cancel]"); }, { disabled: off || !picked, title: "고른 버전을 지웁니다 — 지금 프로젝트 구성·확정은 그대로" }));
    controls.append(actions);
  } else controls.append(el("span", "project-versions-none", "저장된 버전 없음"), add);
  row.append(controls);
  box.append(row);
  if (st.naming) { // 이름 줄(인라인) — Enter 저장 · Esc 취소 · 같은 이름이면 덮어씀을 미리 알림
    const line = el("div", "project-versions-row"), note = el("span", "project-versions-note"), inp = el("input"), total = dv.values ? divTotalYears(dv.values) : 1;
    inp.type = "text"; inp.maxLength = 40; inp.placeholder = "버전 이름(예: 2차년도)"; inp.dataset.versionName = "1";
    inp.setAttribute("aria-label", "프로젝트 구성 버전 이름");
    inp.value = st.draft ?? `${Math.max(1, Math.min((dv.values && dv.values.current) || 1, total || 1))}차년도`; // 기본값 = 지금 입력의 당해 차년도
    note.setAttribute("role", "status");
    const save = act("저장", "versionSave", () => projectVersionSave(inp.value), { disabled: off });
    const check = () => { // 같은 이름이면 이름 줄을 열 때부터(기본값 「N차년도」 가 이미 있을 때) 덮어씀을 알리고 단추 글도 「덮어쓰기」
      st.draft = inp.value;
      const n = divPresetName(inp.value), same = n && vs.find((x) => x.name === n);
      note.textContent = same ? `같은 이름 「${same.name}」 을 덮어씁니다` : "";
      save.textContent = same ? "덮어쓰기" : "저장";
    };
    inp.oninput = check; check();
    inp.onkeydown = (e) => { if (e.isComposing || e.keyCode === 229) return; if (e.key === "Enter") { e.preventDefault(); projectVersionSave(inp.value); } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); projectVersionNaming(false); } };
    line.append(inp, save, act("취소", "versionCancel", () => projectVersionNaming(false)));
    box.append(line, note);
  }
  if (st.deleting && picked) { // 삭제 확인 줄(인라인)
    const line = el("div", "project-versions-row");
    line.append(el("span", "project-versions-text", `버전 「${picked.name}」 을 지울까요? 지금 프로젝트 구성·확정은 그대로입니다`),
      act("지움", "versionDeleteOk", () => projectVersionDelete(picked.id), { disabled: off }), act("취소", "versionDeleteCancel", () => { st.deleting = false; projectVersionsDraw("[data-version-delete]"); }));
    box.append(line);
  }
}

function projectVersionsDraw(focus = "") { // 버전 줄만 다시 그린다(고름 · 이름 줄 · 확인 줄) — focus = 그린 뒤 포커스 줄 곳(선택자)
  const box = document.querySelector("#divBox .project-versions");
  if (!box || !dv.view) return;
  projectVersionsFill(box);
  const to = focus && box.querySelector(focus);
  if (to && !to.disabled) { to.focus({ preventScroll: true }); if (to.tagName === "INPUT") to.select(); }
}

function projectVersionsSync() { // 입력·진행 상태가 바뀔 때 — 줄을 다시 만들지 않고 글(「 · 지금」)과 단추의 켜짐만 맞춘다(이름 줄의 포커스 그대로)
  const box = document.querySelector("#divBox .project-versions");
  if (!box || !dv.view) return;
  const vs = projectVersions() || [], st = projectVerState(), off = projectVersionOff(), cur = dv.values ? divCanon(divValues()) : "", picked = vs.some((x) => x.id === st.pick);
  const sel = box.querySelector("select[data-division-version]");
  if (sel) {
    sel.disabled = off;
    for (const o of sel.options) { const x = vs.find((y) => y.id === o.value), text = x && projectVersionLabel(x, cur); if (text && o.textContent !== text) o.textContent = text; }
  }
  for (const [key, on] of [["[data-version-apply]", picked], ["[data-version-delete]", picked], ["[data-version-add]", projectVersionCan()], ["[data-version-save]", true], ["[data-version-delete-ok]", true]]) {
    const b = box.querySelector(key);
    if (b) b.disabled = off || !on;
  }
}

function projectVersionNaming(on) {
  const st = projectVerState();
  st.naming = on; st.deleting = false;
  if (!on) st.draft = null;
  projectVersionsDraw(on ? "input[data-version-name]" : "[data-version-add]");
}

async function projectVersionRequest(path, init, failText) { // 요청 하나 → 응답(GET …/divisions 와 같은 몸통) | null(실패는 알림). 진행 중에는 받지 않고, 보내기 전에 입력 설정 저장을 마친다
  const st = projectVerState();
  if (!state.id || !dv.view || st.busy) return null;
  if (projectBusy() || dv.busy) { toast(PROJECT_VERSION_WAIT); return null; }
  const id = state.id, epoch = state.epoch;
  st.busy = true;
  projectVersionsSync();
  try {
    await divSettingsFlush();
    if (epoch !== state.epoch || !dv.view) return null;
    const r = await api(`/api/docs/${id}/divisions/versions${path}`, init());
    return epoch === state.epoch && dv.view ? r : null;
  } catch (e) { if (epoch === state.epoch) toast(`${failText}: ${e.message}`, true); return null; }
  finally { st.busy = false; projectVersionsSync(); }
}

function projectVersionAdopt(r) { // 응답을 화면 상태에 얹는다(divConfirm 과 같은 키 + versions)
  Object.assign(dv.view, { settings: r.settings, dimensions: r.dimensions, plan: r.plan, stale: r.stale, projectSharing: r.projectSharing, confirmed: r.confirmed || null, versions: r.versions || [] });
}

async function projectVersionSave(raw) { // 「버전 추가」 의 저장 — 지금 입력 값을 그 이름의 버전으로(같은 이름은 덮어씀: 이름 줄에 미리 알림)
  const st = projectVerState(), name = divPresetName(raw);
  if (!name) { toast("버전 이름을 넣으세요", true); return; }
  const same = (projectVersions() || []).some((x) => x.name === name);
  let values = null;
  const r = await projectVersionRequest("", () => { values = divValues(); return { method: "POST", headers: H_JSON, body: JSON.stringify({ name, values, replace: same }) }; }, "버전을 저장하지 못했습니다");
  if (!r) return;
  projectVersionAdopt(r);
  dv.savedKey = divCanon(values); // 서버가 그 값을 입력 설정으로도 저장했다
  const made = (r.versions || []).find((x) => x.name === name);
  Object.assign(st, { naming: false, draft: null, deleting: false, pick: made ? made.id : st.pick });
  divRender();
  if (typeof taskFlowLoad === "function") taskFlowLoad();
  projectVersionsDraw(made ? "select[data-division-version]" : "[data-version-add]");
  toast(`버전 「${name}」 을 ${same ? "덮어썼습니다" : "저장했습니다"} — ${divValuesText(values)}`);
}

async function projectVersionApply(vid) { // 「적용」(버전 줄에서만 — 「구성 불러오기」 목록에는 버전을 넣지 않는다) — 그 버전의 값이 지금 구분 기준이 된다(입력 + 확정). 문서는 그대로(변경 계획 → 반영)
  const x = (projectVersions() || []).find((y) => y.id === vid);
  if (!x) { toast("적용할 버전을 고르세요", true); return; }
  const r = await projectVersionRequest(`/${encodeURIComponent(vid)}/apply`, () => ({ method: "POST", headers: H_JSON, body: "{}" }), "버전을 적용하지 못했습니다");
  if (!r) return;
  projectVersionAdopt(r);
  const values = (r.settings && r.settings.values) || x.values, st = projectVerState();
  dv.values = structuredClone(values);
  dv.savedKey = divCanon(values); // 서버가 이미 저장했다 — 아래 divTouched 의 자동 저장은 같은 값이라 안 돈다
  dv.preset.from = `버전 「${x.name}」 적용`;
  Object.assign(st, { pick: vid, deleting: false, naming: false, draft: null });
  divTouched(); // 입력 값이 바뀌었다 — 앞 계획·결과를 버리고 열린 계획 열에 알림(확정본으로 되돌리기와 같은 길)
  dv.marks.data = null; // 문서 표시 자료는 새 설정 값으로 다시(divSettingsSave 와 같게)
  if (divMarksOn()) { if (dv.marks.loading) dv.marks.again = true; else divMembersLoad(); }
  divRender();
  if (typeof taskFlowLoad === "function") taskFlowLoad(); // 이관 — 다른 칸 문서의 값·확정도 다시(같은 프로젝트면 같은 값)
  toast(`버전 「${x.name}」 을 적용했습니다 — ${divValuesText(values)}`);
}

async function projectVersionDelete(vid) { // 「삭제」 의 「지움」 — 버전만 지운다(지금 구분 기준·확정은 그대로)
  const x = (projectVersions() || []).find((y) => y.id === vid);
  if (!x) return;
  const r = await projectVersionRequest(`/${encodeURIComponent(vid)}`, () => ({ method: "DELETE" }), "버전을 지우지 못했습니다");
  if (!r) return;
  projectVersionAdopt(r);
  const st = projectVerState();
  Object.assign(st, { pick: "", deleting: false });
  divRender();
  projectVersionsDraw("[data-version-add]");
  toast(`버전 「${x.name}」 을 지웠습니다`);
}
