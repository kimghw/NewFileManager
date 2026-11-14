// 시작 화면의 문서 목록(spec_작업 ② §15-1 — 2026-11-13 사용자 "나는 파일을 파일선택에 넣거나 드래그 하면 내가 올린 파일명이 현재 페이지에 올라가 있고 계속 올리고,
// 이중 목적 문서를 선택하고 필요하면 파일의 별칭을 수정할 수 있고 그리고 task 를 선택해서 작업환경으로 넘어 갔으면 좋겠는데").
// 파일을 바로 열지 않고 파일 놓는 카드(#drop) 안 목록(#homeFiles)에 모은다 — 이 화면(브라우저 메모리)에만, 서버에는 TASK 카드를 누를 때 올린다(사용자 답 「TASK 고를 때 올림」).
// 목적 문서 라디오 · 별칭(목적 문서 줄 — 서버가 보이는 이름 뒤에 「(별칭)」: ② §10) · 프로젝트 · 자동 진행(사업계획서 취합 — 사용자 답 「목록에 「자동 진행」 체크」) → TASK 카드 = 그 TASK 로 시작.
// app.js(bind 의 「파일 선택」·창 놓기 · homeTasksDraw·homeTaskFiles) 와 gather_quick.js(gatherQuickRun · gqConfirmText) 를 쓴다 — 그 둘 다음에 읽는다(index.html).

const HF_OK = /\.(hwpx?|docx)$/i, HF_TASK = /\.hwpx?$/i;
const hf = { files: [], target: -1, alias: "", project: "", auto: false, llm: true, busy: "", err: "" }; // files = [File] — 목록 차례(취합이면 기관 문서 차례)
const hfHas = () => hf.files.length > 0;
const hfTarget = () => (hf.files.length === 1 ? 0 : hf.target); // 하나면 그것이 목적 문서 — 둘 이상이면 고르기 전에는 없음(잘못 고르면 다른 문서가 바뀐다)
const hfNorm = (s, n) => String(s || "").split(/\s+/).filter(Boolean).join(" ").slice(0, n); // 서버와 같게: 앞뒤를 떼고 빈칸을 하나로(별칭 40 · 프로젝트 60자)
const hfExt = (f) => ((f.name.match(/\.(\w+)$/) || [])[1] || "").toLowerCase();
const hfShown = (f, alias) => { const m = f.name.match(/^(.*?)(\.\w+)?$/), stem = m[1] || f.name, ext = /\.hwp$/i.test(f.name) ? ".hwpx" : m[2] || ""; return `${stem}${alias ? `(${alias.replace(/[\\/:*?"<>|]+/g, "_")})` : ""}${ext}`; };
const hfProjects = () => [...new Set((typeof worksList !== "undefined" ? worksList : []).map((w) => (w.task || {}).project).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ko"));

function homeFilesAdd(files, job) { // 「파일 선택」 · 놓기 · 목록이 있을 때 카드에 놓기 · 카드로 여럿을 고름 — hwp·hwpx·docx 만, 같은 이름·크기는 한 번
  if (hf.busy) return;
  const list = [...(files || [])], ok = list.filter((f) => HF_OK.test(f.name)), bad = list.filter((f) => !HF_OK.test(f.name));
  if (bad.length) toast(`hwp·hwpx·docx 문서만 목록에 올릴 수 있습니다 — 뺀 파일: ${bad.map((f) => f.name).join(" · ")}`, true);
  let added = 0;
  for (const f of ok) if (!hf.files.some((x) => x.name === f.name && x.size === f.size)) { hf.files.push(f); added += 1; }
  if (!added) return;
  hf.err = "";
  homeFilesDraw();
  const t = job && TASK_CATALOG[job];
  if (t && hfTarget() < 0) toast(`문서 ${hf.files.length}개를 목록에 올렸습니다 — 목적 문서를 고르고 TASK 「${t.name}」 카드를 누르세요`);
  const box = $("homeFiles");
  if (box) box.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function homeFilesPick() { // 「파일 선택」 · 「파일 더하기」 — 여러 개
  const inp = el("input");
  inp.type = "file";
  inp.multiple = true;
  inp.accept = ".hwp,.hwpx,.docx";
  inp.onchange = () => homeFilesAdd(inp.files);
  inp.click();
}

function hfCardsSync() { // TASK 카드 아래 글 — 목록이 있으면 「목록으로 시작 →」(누르면 이 목록으로), 없으면 전처럼 「<문서> 올려 시작 →」
  const has = hfHas();
  $("homeTasks").classList.toggle("has-files", has);
  for (const b of document.querySelectorAll("#taskCards .task-card")) {
    if (b.getAttribute("aria-disabled") === "true") continue;
    const go = b.querySelector(".task-card-go"), txt = go && go.firstChild;
    if (!txt || txt.nodeType !== 3) continue;
    if (b.dataset.up == null) { b.dataset.up = txt.textContent; b.dataset.tip = b.title; }
    txt.textContent = has ? "목록으로 시작 " : b.dataset.up;
    b.title = has ? `TASK 「${(TASK_CATALOG[b.dataset.task] || {}).name}」 — 위 목록의 목적 문서로 시작합니다(파일을 이 카드에 놓으면 목록에 더함)` : b.dataset.tip;
  }
}

function homeFilesDraw() {
  const drop = $("drop"), box = $("homeFiles"), has = hfHas();
  drop.classList.toggle("has-files", has);
  box.hidden = !has;
  hfCardsSync();
  if (!has) { box.textContent = ""; hf.target = -1; hf.alias = ""; return; }
  const busy = !!hf.busy, ti = hfTarget(), focus = box.contains(document.activeElement) ? document.activeElement.dataset.hfFocus || "" : "";
  box.textContent = "";
  box.setAttribute("aria-busy", busy);
  const head = el("header", "hf-head"), h = el("h3", null, `올린 문서 ${hf.files.length}개`), clear = el("button", "btn sm hf-clear", "비우기");
  h.id = "homeFilesTitle";
  clear.type = "button";
  clear.disabled = busy;
  clear.title = "목록을 비웁니다(아직 서버에 올린 것은 없습니다)";
  clear.onclick = () => { hf.files = []; hf.target = -1; hf.alias = ""; hf.err = ""; homeFilesDraw(); $("pickBtn").focus(); };
  head.append(h, hHelp("문서 목록 안내", "파일을 고르거나 놓으면 여기에 모입니다(아직 서버에 올리지 않음 — 새로 고치면 사라집니다).\n"
    + "목적 문서(내용을 받는 문서 — 이관 = 연차보고서 · 취합 = 취합본 · 양식 맞추기 = 맞출 문서)를 고르고, 필요하면 별칭을 적은 뒤 아래 TASK 카드를 누르면 그 TASK 의 작업 화면으로 갑니다.\n"
    + "별칭은 목적 문서 이름 뒤에 「(별칭)」 으로 붙습니다(작업 화면 · 최근 작업 · 저장 파일 이름). 프로젝트 이름을 적으면 그 프로젝트의 TASK 다음 라운드로 시작합니다."), clear);
  const tgt = hf.files[ti], n = hf.files.length - (tgt ? 1 : 0);
  const cap = el("p", "hf-cap", tgt ? `목적 문서 「${tgt.name}」${n ? ` · 원본 문서 ${n}개` : ""} — 아래 TASK 카드를 누르면 시작합니다` : "목적 문서(내용을 받는 문서)를 하나 고르세요 — 그 뒤 아래 TASK 카드를 누릅니다.");
  const rows = el("div", "hf-rows");
  rows.setAttribute("role", "radiogroup");
  rows.setAttribute("aria-label", "목적 문서 고르기");
  hf.files.forEach((f, i) => {
    const on = i === ti, row = el("div", "hf-row" + (on ? " on" : "")), lab = el("label", "hf-pick"), r = el("input"), ext = el("span", "hf-ext", hfExt(f).toUpperCase()), name = el("span", "hf-name", f.name), del = el("button", "icon hf-del", "×");
    const tag = el("span", "hf-tag", [on ? "목적 문서" : ti >= 0 ? "원본 문서" : "", /\.hwp$/i.test(f.name) ? "hwpx 로 바꿔 올림" : "", /\.docx$/i.test(f.name) ? "TASK 없이 열기만" : ""].filter(Boolean).join(" · "));
    row.dataset.hfFile = String(i);
    ext.dataset.ext = hfExt(f);
    r.type = "radio";
    r.name = "homeFileTarget";
    r.value = String(i);
    r.checked = on;
    r.disabled = busy;
    r.dataset.hfFocus = `pick:${i}`;
    r.onchange = () => { hf.target = i; homeFilesDraw(); };
    name.title = f.name;
    del.type = "button";
    del.disabled = busy;
    del.title = "목록에서 빼기";
    del.setAttribute("aria-label", `${f.name} 빼기`);
    del.dataset.hfFocus = `del:${i}`;
    del.onclick = () => {
      hf.files.splice(i, 1);
      if (hf.target === i) { hf.target = -1; hf.alias = ""; } else if (hf.target > i) hf.target -= 1;
      homeFilesDraw();
    };
    lab.append(r, ext, name);
    row.append(lab, tag, del);
    rows.append(row);
    if (!on) return;
    const line = el("div", "hf-alias"), al = el("label"), inp = el("input"), shown = el("span", "hf-shown");
    const preview = () => { const a = hfNorm(inp.value, 40); shown.textContent = a ? `보일 이름 ${hfShown(f, a)}` : "별칭을 적으면 이름 뒤에 「(별칭)」 이 붙습니다"; };
    inp.type = "text";
    inp.maxLength = 40;
    inp.value = hf.alias;
    inp.placeholder = "별칭(선택) — 예: 1차 제출";
    inp.disabled = busy;
    inp.dataset.hfFocus = "alias";
    inp.setAttribute("aria-label", `「${f.name}」 별칭`);
    inp.oninput = () => { hf.alias = inp.value; preview(); };
    al.append(el("span", null, "별칭"), inp);
    preview();
    line.append(al, shown);
    rows.append(line);
  });
  const opts = el("div", "hf-opts"), pl = el("label", "hf-project"), pin = el("input"), dl = el("datalist");
  dl.id = "homeFilesProjects";
  for (const p of hfProjects()) dl.append(new Option(p));
  pin.type = "text";
  pin.maxLength = 60;
  pin.value = hf.project;
  pin.placeholder = "프로젝트 이름(선택)";
  pin.setAttribute("list", dl.id);
  pin.disabled = busy;
  pin.dataset.hfFocus = "project";
  pin.title = "적으면 목적 문서가 그 프로젝트의 TASK 다음 라운드로 시작합니다 — 이관에 사업계획서까지 함께 시작하려면 필요(두 문서를 같은 프로젝트로 묶음)";
  pin.oninput = () => { hf.project = pin.value; };
  pl.append(el("span", null, "프로젝트"), pin, dl);
  const check = (text, key, title, off) => {
    const lab = el("label", "hf-check"), cb = el("input");
    cb.type = "checkbox";
    cb.checked = hf[key];
    cb.disabled = busy || !!off;
    cb.dataset.hfFocus = key;
    cb.onchange = () => { hf[key] = cb.checked; if (key === "auto") homeFilesDraw(); };
    lab.title = title;
    lab.append(cb, el("span", null, text));
    return lab;
  };
  opts.append(pl, check("자동 진행", "auto", "사업계획서 취합 — 켜고 카드를 누르면 확인 한 번 뒤 끝까지 자동으로 취합합니다(간단 모드). 끄면 올리고 등록만 해서 세부 작업 모드로 엽니다"),
    check("LLM 검토", "llm", "자동 진행 때 넣을 수 있다고 본 내용을 LLM 이 한 번 더 봅니다(문서마다 수십 초 · 유료) — 넣을 것을 줄이기만 합니다", !hf.auto));
  const foot = el("div", "hf-foot"), more = el("button", "btn sm", "파일 더하기"), plain = el("button", "btn sm", "TASK 없이 열기");
  more.type = plain.type = "button";
  more.disabled = busy;
  more.dataset.hfFocus = "more";
  more.title = "hwp·hwpx·docx 문서를 더 고릅니다 — 이 카드에 놓아도 됩니다";
  more.onclick = homeFilesPick;
  plain.disabled = busy || !tgt;
  plain.dataset.hfPlain = "1";
  plain.title = tgt ? `「${tgt.name}」 을 TASK 없이 그냥 엽니다(편집 · 검증 — docx 도)` : "목적 문서를 먼저 고르세요";
  plain.onclick = homeFilesPlain;
  foot.append(more, plain, el("span", "hf-next", "↓ 아래 TASK 카드를 누르면 시작합니다"));
  box.append(head, cap, rows, opts, foot);
  if (hf.busy || hf.err) {
    const st = el("p", "hf-status" + (hf.err ? " err" : ""));
    st.setAttribute("role", hf.err ? "alert" : "status");
    if (hf.busy) st.append(el("i", "hf-spin"));
    st.append(el("span", null, hf.err || hf.busy));
    box.append(st);
  }
  if (focus) { const to = box.querySelector(`[data-hf-focus="${CSS.escape(focus)}"]`); if (to && !to.disabled) to.focus({ preventScroll: true }); }
}

function hfBusy(text) { hf.busy = text; if (text) hf.err = ""; homeFilesDraw(); }
function hfFail(text) { hf.busy = ""; hf.err = text; homeFilesDraw(); }
function hfUsed(files) { // 올린 문서는 목록에서 뺀다 — 안 쓴 문서는 남는다(시작 화면에 돌아오면 보임)
  hf.files = hf.files.filter((f) => !files.includes(f));
  Object.assign(hf, { target: -1, alias: "", busy: "", err: "" });
  homeFilesDraw();
}

async function homeFilesPlain() { // 「TASK 없이 열기」 — 목적 문서를 그냥 연다(전의 「파일 선택」 과 같다: openFile) + 별칭
  const f = hf.files[hfTarget()], alias = hfNorm(hf.alias, 40);
  if (!f || hf.busy || homeTaskBusy || !confirmDiscard()) return;
  hfBusy(`「${f.name}」 여는 중…`);
  try {
    const fd = new FormData();
    fd.append("file", f);
    const r = await api("/api/docs", { method: "POST", body: fd });
    await opened(r, () => openFile(f, true));
    hfUsed([f]);
    if (alias && state.stored && state.id === r.docId) {
      try { await api(`/api/works/${r.docId}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias }) }); await loadWorks(); }
      catch (e) { toast(`별칭을 저장하지 못했습니다: ${e.message}`, true); }
    }
  } catch (e) { setSaveState("err", "열지 못함"); hfFail(`열지 못했습니다: ${e.message}`); }
}

// 목적 문서를 올려 열고 그 TASK 로 적는다 → {id, task, note}. 같은 파일로 하던 작업은 이어 연다(② §1) — 다른 TASK · 다른 프로젝트 · 기관 문서 · 다른 역할이었으면 묻지 않고 새 작업으로(목록에서 TASK 를 골랐다).
async function hfOpenTarget(job, file, { project, alias }) {
  const cat = TASK_CATALOG[job], blank = { kind: "", file: "", job: "", project: "" };
  const up = async (fresh) => { const fd = new FormData(); fd.append("file", file); const r = await api(`/api/docs${fresh ? "?new=1" : ""}`, { method: "POST", body: fd }); await load(r.docId); return r; };
  let r = await up(false), note = "", fresh = !r.reused;
  if (r.reused) {
    const t = { ...blank, ...state.task };
    const other = (t.job && t.job !== job) || t.file === "part" || (cat.target && t.job === job && t.file && t.file !== cat.target) || (project && t.project && t.project !== project);
    if (other) {
      const was = [t.project ? `프로젝트 「${t.project}」` : "", t.job ? `TASK 「${taskName("job", t.job)}」` : "", t.file ? taskName("file", t.file) : ""].filter(Boolean).join(" · ");
      r = await up(true);
      fresh = true;
      note = `같은 파일로 하던 작업(${was || "다른 작업"})은 그대로 두고 새 작업으로 열었습니다`;
    } else note = "같은 파일로 하던 작업을 이어서 엽니다";
  }
  if (state.id !== r.docId) throw new Error("그 사이 다른 문서를 열었습니다");
  const cur = { ...blank, ...state.task }, role = cat.target || cur.file || cat.file; // 목적 문서 종류: 이관 = 연차보고서 · 취합 = 취합본 · 양식 맞추기 = 양식 판정(못 정하면 그 TASK 의 문서)
  if (state.stored) {
    const res = project && !cur.project
      ? await api(`/api/works/${r.docId}/start-task`, { method: "POST", headers: H_JSON, body: JSON.stringify({ project, job, file: role }) }) // 그 프로젝트의 그 TASK 다음 라운드(② §17)
      : await api(`/api/works/${r.docId}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ ...cur, kind: taskKindOf(job), job, file: role }) }); // 작업 종류는 TASK 가 정한다(task_catalog.js — 「문서 일반 편집」 = 일반 문서)
    if (state.id === r.docId) state.task = res.task;
    if (alias) { // 별칭을 못 적어도 TASK 는 시작한다(서버가 별칭 끝점을 모르는 옛 서버일 때 등) — 알림만
      try { await api(`/api/works/${r.docId}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias }) }); }
      catch (e) { toast(`별칭을 저장하지 못했습니다: ${e.message}`, true); }
    }
  } else state.task = { ...cur, kind: taskKindOf(job), job, file: role, project: project || cur.project }; // 작업 저장이 꺼져 있으면 이 화면에서만(② §10)
  taskDraw();
  await loadWorks(); // 보이는 이름(프로젝트 꼬리 · 별칭)도 여기서 맞춘다(docSwitchDraw)
  if (state.id !== r.docId) throw new Error("그 사이 다른 문서를 열었습니다");
  if (fresh) firstRun(); // 새 작업 — 첫 분석(② §9)
  showTab(taskEntryOf(job)); // 그 TASK 가 처음 여는 보기(보통 작업 내용 · 문서 일반 편집은 에이전트)
  return { id: r.docId, task: state.task, note };
}

async function hfAddSource(main, file, role) { // 이관의 원본 문서(사업계획서) — 늘 새 작업으로 올려 같은 프로젝트·TASK·라운드의 그 종류로 적는다(첨부 파일 칸이 저절로 잇는다 — ② §11)
  const t = main.task || {}, name = taskName("file", role);
  toast(`${file.name} — ${name}로 올리는 중…${/\.hwp$/i.test(file.name) ? "(한글이 hwpx 로 바꿈)" : ""}`);
  try {
    const fd = new FormData();
    fd.append("file", file);
    const d = await api("/api/docs?new=1", { method: "POST", body: fd });
    await api(`/api/works/${d.docId}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ kind: taskKindOf(t.job), file: role, job: t.job, project: t.project, ...(t.round ? { round: t.round } : {}) }) });
    api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 2단계 자리 연결이 그 결과를 본다
    if (state.id === main.id) await loadWorks();
    toast(`${file.name} — ${name} 칸에 넣었습니다`);
  } catch (e) { toast(`${name}를 올리지 못했습니다: ${e.message} — 작업 내용의 ${name} 칸에서 다시 올리세요`, true); }
}

async function homeFilesGo(job) { // 목록이 있을 때 TASK 카드 — 그 TASK 로 시작(② §15-1 표)
  const t = TASK_CATALOG[job];
  if (!t || hf.busy || homeTaskBusy) return;
  if (t.soon) { toast(`TASK 「${t.name}」 — 준비 중입니다`); return; }
  const ti = hfTarget(), target = hf.files[ti];
  const ask = (msg, sel) => { toast(msg, true); const to = sel && $("homeFiles").querySelector(sel); if (to) to.focus(); };
  if (!target) { ask("목적 문서를 먼저 고르세요 — 내용을 받는 문서(이관 = 연차보고서 · 취합 = 취합본 · 양식 맞추기 = 맞출 문서)", "input[type=radio]"); return; }
  if (!HF_TASK.test(target.name)) { ask("TASK 는 hwp·hwpx 문서로 시작합니다 — docx 는 「TASK 없이 열기」 로 엽니다", "[data-hf-plain]"); return; }
  const others = hf.files.filter((_, i) => i !== ti), project = hfNorm(hf.project, 60), alias = hfNorm(hf.alias, 40), auto = hf.auto, llm = hf.llm;
  const sourceRole = (t.files || []).find((k) => k !== t.target) || "";
  let use = [];
  if (t.gather) {
    if (others.some((f) => !HF_TASK.test(f.name))) { ask("기관 문서도 hwp·hwpx 여야 합니다 — docx 는 목록에서 빼 주세요"); return; }
    if (auto && !others.length) { ask("자동 진행에는 기관 문서가 하나 이상 있어야 합니다 — 「파일 더하기」 로 더하거나 「자동 진행」 을 끄세요", "[data-hf-focus=more]"); return; }
    if (auto && !confirm(gqConfirmText(target, others, llm))) return;
    use = others;
  } else if (t.files) {
    if (others.length > 1) { ask(`이관은 연차보고서(목적 문서) 하나와 ${taskName("file", sourceRole)} 하나로 합니다 — 목록에 문서가 ${hf.files.length}개입니다. 남길 둘만 두세요`); return; }
    if (others.length && !HF_TASK.test(others[0].name)) { ask(`${taskName("file", sourceRole)}도 hwp·hwpx 여야 합니다`); return; }
    if (others.length && !project) { ask(`${taskName("file", sourceRole)}까지 함께 시작하려면 프로젝트 이름이 필요합니다 — 두 문서를 같은 프로젝트로 묶습니다`, "[data-hf-focus=project]"); return; }
    use = others;
  } else if (others.length && !confirm(`TASK 「${t.name}」 은 목적 문서 하나로 합니다.\n\n「${target.name}」 만 올리고 나머지 ${others.length}개는 목록에 남깁니다. 계속할까요?`)) return;
  if (!confirmDiscard()) return;
  const card = document.querySelector(`#taskCards [data-task="${job}"]`);
  hfBusy(`TASK 「${t.name}」 — 목적 문서 「${target.name}」 올리는 중…${/\.hwp$/i.test(target.name) ? "(한글이 hwpx 로 바꿈 — 수십 초)" : ""}`);
  homeTaskBusy = true;
  if (card) card.classList.add("busy");
  setSaveState("busy", `${target.name} 여는 중…`);
  let main;
  try { main = await hfOpenTarget(job, target, { project, alias }); }
  catch (e) { // 문서는 열렸는데 TASK·별칭 저장에서 실패했을 수도 있다 — 시작 화면의 까닭 줄은 그때 안 보이므로 알림도
    setSaveState("err", "열지 못함");
    hfFail(`목적 문서를 TASK 「${t.name}」 로 열지 못했습니다: ${e.message}`);
    toast(hf.err, true);
    return;
  } finally { homeTaskBusy = false; if (card) card.classList.remove("busy"); }
  hfUsed([target, ...use]);
  if (main.note) toast(main.note);
  if (t.gather && use.length) await gatherQuickRun(main.id, target.name, use, { llm, uploadOnly: !auto }); // 취합 — 기관 문서 올리기·등록(+ 자동 진행이면 끝까지): gather_quick.js
  else if (sourceRole && use.length) await hfAddSource(main, use[0], sourceRole);
}
