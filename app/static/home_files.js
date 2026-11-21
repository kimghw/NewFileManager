// 시작 화면의 문서 목록(spec_작업 ② §15-1 — 2026-11-13 사용자 "나는 파일을 파일선택에 넣거나 드래그 하면 내가 올린 파일명이 현재 페이지에 올라가 있고 계속 올리고,
// 이중 목적 문서를 선택하고 필요하면 파일의 별칭을 수정할 수 있고 그리고 task 를 선택해서 작업환경으로 넘어 갔으면 좋겠는데").
// 파일을 바로 열지 않고 파일 놓는 카드(#drop) 안 목록(#homeFiles)에 모은다 — 이 화면(브라우저 메모리)에만, 서버에는 TASK 카드를 누를 때 올린다(사용자 답 「TASK 고를 때 올림」).
// 파일 카드마다 목적 문서 라디오 · 약칭(저장 키 alias — 보이는 이름 뒤에 「(약칭)」: ② §10) · 프로젝트 · 자동 진행 → TASK 카드 = 그 TASK 로 시작.
// app.js(bind 의 「파일 선택」·창 놓기 · homeTasksDraw·homeTaskFiles) 와 gather_quick.js(gatherQuickRun · gqConfirmText) 를 쓴다 — 그 둘 다음에 읽는다(index.html).

const HF_OK = /\.(hwpx?|docx)$/i, HF_TASK = /\.hwpx?$/i;
const hf = { files: [], target: -1, aliases: new WeakMap(), project: "", auto: false, llm: true, zones: null, busy: "", err: "",
  get alias() { return this.aliases.get(this.files[hfTarget()]) || ""; },
  set alias(value) { const file = this.files[hfTarget()]; if (file) this.aliases.set(file, value); },
}; // 약칭은 File 에 붙인다 — 목적 문서를 바꾸거나 앞 파일을 빼도 다른 문서로 옮겨 가지 않는다.
// hf.zones = 편집 구역에서 가려 볼 기준(TASK 옵션 — spec_구역 ② §1): null = 손대지 않음(그 TASK 의 기본값 — task_catalog.js zones) · 목록 = 사람이 고른 것(빈 목록 = 끔).
const HF_ZONES = [["org", "기관"], ["stage", "단계"], ["year", "차년도"]]; // 서버 app/zones.py DIMS 의 차례 · 이름
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { taskOptions: "편집 구역 기준 정함", flowHand: "사람이 하는 일 확인", sourceForm: "원본 문서를 저장한 양식으로", targetForm: "목적 문서를 저장한 양식으로" }); // 「기록」 탭의 이름 — 편집 구역에서 가려 볼 기준을 사람이 정함(서버 task_options_api 의 작업 기록 `taskOptions`: 이 목록 · 「작업 개요」 의 「편집 구역」 줄) · 사람이 하는 일의 「했음」 · 취소(flow_hands_api 의 `flowHand`) · 원본 문서 칸을 저장한 양식으로 채움(form_files_api 의 `sourceForm` — spec_워크플로우 ② §18-9)
const hfZoneNames = (dims) => HF_ZONES.filter(([d]) => dims.includes(d)).map(([, name]) => name).join(" · ");
const hfZonesDefaults = () => Object.keys(TASK_CATALOG).filter((job) => taskZonesDefault(job).length) // 기본으로 켜는 TASK 들 — 「사업계획서 취합 = 기관」(task_catalog.js zones)
  .map((job) => `${TASK_CATALOG[job].name} = ${hfZoneNames(taskZonesDefault(job))}`).join(" · ");
const hfHas = () => hf.files.length > 0;
const hfTarget = () => (hf.files.length === 1 ? 0 : hf.target); // 하나면 그것이 목적 문서 — 둘 이상이면 고르기 전에는 없음(잘못 고르면 다른 문서가 바뀐다)
const hfNorm = (s, n) => String(s || "").split(/\s+/).filter(Boolean).join(" ").slice(0, n); // 서버와 같게: 앞뒤를 떼고 빈칸을 하나로(별칭 40 · 프로젝트 60자)
const hfExt = (f) => ((f.name.match(/\.(\w+)$/) || [])[1] || "").toLowerCase();
const hfShown = (f, alias) => { const m = f.name.match(/^(.*?)(\.\w+)?$/), stem = m[1] || f.name, ext = /\.hwp$/i.test(f.name) ? ".hwpx" : m[2] || ""; return `${stem}${alias ? `(${alias.replace(/[\\/:*?"<>|]+/g, "_")})` : ""}${ext}`; };
const hfProjects = () => [...new Set((typeof worksList !== "undefined" ? worksList : []).map((w) => (w.task || {}).project).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ko"));
// 그 워크플로우에서 고른 문서의 화면 이름(spec_워크플로우 ② §15 「말」 — 등록부 roles 의 title 과 같게): 문서 여럿(취합 · 이관 · 조립한 것) = 목적 문서 · 문서 하나 = 작업 문서 · 서식 복사 = 서식을 가져올 문서.
// 워크플로우를 아는 글(카드의 시작 풍선 도움말 · 나머지 문서 확인 · 올리는 중 · 실패)만 쓴다 — 목록(homeFilesDraw)은 워크플로우를 고르기 전에 그려 고르는 문서를 「목적 문서」 로 부른다
const hfDocName = (job) => { const t = TASK_CATALOG[job]; return !t || t.gather || t.files ? "목적 문서" : job === "style_copy" ? "서식을 가져올 문서" : "작업 문서"; };
const hfJosa = (word, a, b, old) => (typeof taskJosa === "function" ? taskJosa(word, a, b) : old); // 이름 뒤 조사(task_catalog.js taskJosa — 받침이 있으면 a · 없으면 b) · 없으면 옛 글(old)

function homeFilesAdd(files, job) { // 「파일 선택」 · 놓기 · 목록이 있을 때 카드에 놓기 · 카드로 여럿을 고름 — hwp·hwpx·docx 만, 같은 이름·크기는 한 번
  if (hf.busy || homeTaskBusy) return;
  const list = [...(files || [])], ok = list.filter((f) => HF_OK.test(f.name)), bad = list.filter((f) => !HF_OK.test(f.name));
  // PDF 는 목록에 넣지 않는다(spec_서식복사 ② §1) — 작업을 만들지 않는 파일이라 「문서 서식 복사」 카드에 하나씩 놓아 서식 후보만 찾는다(app.js homeTaskFiles)
  if (bad.length && bad.every((f) => /\.pdf$/i.test(f.name))) toast(`PDF 는 「문서 서식 복사」 카드에 하나씩 놓으세요 — 뺀 파일: ${bad.map((f) => f.name).join(" · ")}`, true);
  else if (bad.length) toast(`hwp·hwpx·docx 문서만 목록에 올릴 수 있습니다 — 뺀 파일: ${bad.map((f) => f.name).join(" · ")}${bad.some((f) => /\.pdf$/i.test(f.name)) ? "\nPDF 는 「문서 서식 복사」 카드에 하나씩 놓으세요" : ""}`, true);
  let added = 0;
  for (const f of ok) if (!hf.files.some((x) => x.name === f.name && x.size === f.size)) { hf.files.push(f); added += 1; }
  if (!added) return;
  hf.err = "";
  homeFilesDraw();
  const t = job && TASK_CATALOG[job];
  if (t && hfTarget() < 0) toast(`문서 ${hf.files.length}개를 목록에 올렸습니다 — 목적 문서를 고르고 워크플로우 「${t.name}」 카드를 누르세요`);
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
  const has = hfHas(), target = hf.files[hfTarget()], busy = !!hf.busy || homeTaskBusy;
  if (!$("homeTasks")) return;
  $("homeTasks").classList.toggle("has-files", has);
  const hint = $("homeTasksHint");
  if (hint) hint.textContent = busy ? "문서를 준비하고 있습니다" : has && !target ? "파일 카드에서 목적 문서를 선택하면 워크플로우를 실행할 수 있습니다"
    : target ? `목적 문서: ${target.name} · 실행할 워크플로우를 선택하세요` : "파일 추가 → 목적 문서 선택 → 워크플로우 실행";
  for (const b of document.querySelectorAll("#taskCards .task-card")) {
    const task = TASK_CATALOG[b.dataset.task];
    if (!task || task.soon) continue;
    const go = b.querySelector(".task-card-go"), txt = go && go.firstChild;
    if (!txt || txt.nodeType !== 3) continue;
    if (b.dataset.up == null) { b.dataset.up = txt.textContent; b.dataset.tip = b.title; }
    const formed = has && !task.gather && hfUseForm(b.dataset.task) ? hfSlot(b.dataset.task) : null; // 목적 문서 칸 = 저장한 양식(고정 · 기본값이고 목적 문서를 직접 안 고름 — 목록의 문서는 원본 문서)
    const unsupported = !formed && target && !taskAcceptOf(b.dataset.task).includes(hfExt(target));
    b.disabled = busy || (has && !formed && (!target || unsupported));
    b.setAttribute("aria-disabled", String(b.disabled));
    const quick = !!task.gather && hf.auto && hf.files.length > 1; // 취합 + 「자동 진행」 + 기관 문서 — 이 카드가 끝까지 한 번에 한다(간단 모드)
    txt.textContent = busy ? "문서 여는 중 " : formed ? "양식으로 시작 " : has && !target ? "목적 문서를 선택하세요 " : unsupported ? "지원하지 않는 파일 형식 " : quick ? "끝까지 자동 진행 " : has ? "목록으로 시작 " : b.dataset.up;
    b.title = busy ? "문서를 여는 중입니다" : formed ? `워크플로우 「${task.name}」 — 목적 문서를 ${hfFormLabel(formed.form)}(${HF_FORM_MODE[formed.mode]})으로 만들고 목록의 문서를 원본 문서로 시작합니다`
      : has && !target ? "위 파일 카드에서 목적 문서를 하나 고르세요"
      : unsupported ? `이 워크플로우는 ${taskAcceptOf(b.dataset.task).join("·")} 문서로 시작합니다`
      : quick ? `워크플로우 「${task.name}」 — 목적 문서 「${target.name}」 에 기관 문서 ${hf.files.length - 1}개를 끝까지 한 번에 취합합니다(남긴 것은 연 뒤 단계별로 보정)`
      : has ? `워크플로우 「${task.name}」 — ${hfDocName(b.dataset.task)} 「${target.name}」로 시작합니다(연 뒤 에이전트가 사전 준비 · 다음 단계를 안내합니다)` : b.dataset.tip;
  }
}

function homeFilesDraw() {
  const drop = $("drop"), box = $("homeFiles"), has = hfHas();
  drop.classList.toggle("has-files", has);
  box.hidden = !has;
  hfCardsSync();
  if (!has) { box.textContent = ""; hf.target = -1; if (typeof homeAgentDraw === "function") homeAgentDraw(); return; }
  const busy = !!hf.busy || homeTaskBusy, ti = hfTarget(), focus = box.contains(document.activeElement) ? document.activeElement.dataset.hfFocus || "" : "";
  box.textContent = "";
  box.setAttribute("aria-busy", busy);
  const head = el("header", "hf-head"), h = el("h3", null, `올린 문서 ${hf.files.length}개`), clear = el("button", "btn sm hf-clear", "비우기");
  h.id = "homeFilesTitle";
  clear.type = "button";
  clear.disabled = busy;
  clear.title = "목록을 비웁니다(아직 서버에 올린 것은 없습니다)";
  clear.onclick = () => { hf.files = []; hf.target = -1; hf.aliases = new WeakMap(); hf.err = ""; homeFilesDraw(); $("pickBtn").focus(); };
  head.append(h, hHelp("문서 목록 안내", "파일을 고르거나 놓으면 여기에 모입니다(아직 서버에 올리지 않음 — 새로 고치면 사라집니다).\n"
    + "목적 문서(내용을 받는 문서)를 고르고, 필요하면 문서마다 약칭을 적은 뒤 아래 워크플로우 카드를 누르세요. 파일이 하나면 목적 문서로 자동 선택합니다.\n"
    + "약칭은 문서 이름 뒤에 「(약칭)」 으로 붙습니다. 프로젝트 이름을 적으면 그 프로젝트의 워크플로우 다음 라운드로 시작합니다.\n"
    + "프로젝트 이름을 비우면 임시 이름(임시 프로젝트 N)으로 함께 올린 문서를 묶습니다 — 연 뒤 「작업 개요」 의 프로젝트 칸에 이름을 적으면 바뀝니다."), clear);
  // 오른쪽 대시보드에서 고른 워크플로우의 목적 문서 칸이 저장한 양식이면(home_dash.js hdUseForm — 고정 · 기본값) 목록의 문서는 모두 원본 문서다 — 목록이 그 문서를 「목적 문서」 로 보이지 않게
  const formJob = typeof HD === "object" && HD.job && !HD.wid && typeof hdUseForm === "function" && hdUseForm(HD.job) ? HD.job : "", fslot = formJob ? hfSlot(formJob) : null;
  const tgt = formJob ? null : hf.files[ti], n = hf.files.length - (tgt ? 1 : 0);
  const cap = el("p", "hf-cap", formJob ? `목적 문서 = ${hfFormLabel(fslot.form)}(워크플로우 「${TASK_CATALOG[formJob].name}」 의 양식 · ${HF_FORM_MODE[fslot.mode]}) · 원본 문서 ${n}개 — 오른쪽 대시보드의 「워크플로우 시작」 이나 아래 워크플로우 카드로 시작합니다`
    : tgt ? `목적 문서 「${tgt.name}」${n ? ` · 원본 문서 ${n}개` : ""} — 아래 워크플로우 카드를 누르면 시작합니다` : "목적 문서(내용을 받는 문서)를 하나 고르세요 — 그 뒤 아래 워크플로우 카드를 누릅니다.");
  const rows = el("div", "hf-rows");
  rows.setAttribute("role", "radiogroup");
  rows.setAttribute("aria-label", "목적 문서 고르기");
  hf.files.forEach((f, i) => {
    const on = !formJob && i === ti, row = el("div", "hf-row" + (on ? " on" : "")), lab = el("label", "hf-pick"), r = el("input"), icon = el("span", "hf-file-icon"), ext = el("span", "hf-ext", hfExt(f).toUpperCase()), name = el("span", "hf-name", f.name), del = el("button", "icon hf-del", "×");
    const tag = el("span", "hf-tag", [on ? "목적 문서" : formJob || ti >= 0 ? "원본 문서" : "목적 문서로 선택", /\.hwp$/i.test(f.name) ? "hwpx 로 변환" : "", /\.docx$/i.test(f.name) ? "워크플로우 없이 열기 · 서식 복사" : ""].filter(Boolean).join(" · "));
    if (/\.docx$/i.test(f.name)) tag.title = "docx — 「워크플로우 없이 열기」 로 열거나, 워크플로우 「문서 서식 복사」 의 서식을 가져올 문서로만 시작합니다"; // spec_서식복사 ② §1 — 그 TASK 는 docx 도 된다
    row.dataset.hfFile = String(i);
    icon.dataset.ext = hfExt(f);
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = '<svg viewBox="0 0 64 80" width="64" height="80" fill="none" aria-hidden="true" focusable="false"><path d="M10 2h28l16 16v54a6 6 0 0 1-6 6H10a6 6 0 0 1-6-6V8a6 6 0 0 1 6-6Z" fill="#fff" stroke="currentColor" stroke-width="2"/><path d="M38 2v12a4 4 0 0 0 4 4h12M16 30h26M16 37h20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    icon.append(ext);
    ext.dataset.ext = hfExt(f);
    r.type = "radio";
    r.name = "homeFileTarget";
    r.value = String(i);
    r.checked = on;
    r.disabled = busy;
    r.setAttribute("aria-label", `${f.name} 목적 문서로 선택`);
    r.dataset.hfFocus = `pick:${i}`;
    r.onchange = () => { hf.target = i; if (formJob && fslot.mode !== "fixed") HD.form = false; homeFilesDraw(); }; // 기본값 양식을 쓰던 중 목록에서 목적 문서를 고르면 그 문서로(고정이면 양식 그대로 — 대시보드의 까닭 글)
    name.title = f.name;
    del.type = "button";
    del.disabled = busy;
    del.title = "목록에서 빼기";
    del.setAttribute("aria-label", `${f.name} 빼기`);
    del.dataset.hfFocus = `del:${i}`;
    del.onclick = () => {
      hf.aliases.delete(f);
      hf.files.splice(i, 1);
      if (hf.target === i) hf.target = -1; else if (hf.target > i) hf.target -= 1;
      homeFilesDraw();
    };
    lab.append(r, icon, name);
    row.append(lab, tag, del);
    rows.append(row);
    const line = el("div", "hf-alias"), al = el("label"), inp = el("input"), shown = el("span", "hf-shown");
    const preview = () => { const a = hfNorm(inp.value, 40); shown.textContent = a ? `보일 이름 ${hfShown(f, a)}` : "문서 이름 뒤에 약칭이 붙습니다"; shown.title = shown.textContent; };
    inp.type = "text";
    inp.maxLength = 40;
    inp.value = hf.aliases.get(f) || "";
    inp.placeholder = "예: 계획서, 1차 제출";
    inp.disabled = busy;
    inp.dataset.hfFocus = on ? "alias" : `alias:${i}`;
    inp.setAttribute("aria-label", `「${f.name}」 약칭`);
    inp.oninput = () => { hf.aliases.set(f, inp.value); preview(); };
    al.append(el("span", null, "약칭"), inp);
    preview();
    line.append(al, shown);
    row.append(line);
  });
  const opts = el("div", "hf-opts"), pl = el("label", "hf-project"), pin = el("input");
  pin.type = "text";
  pin.maxLength = 60;
  pin.value = hf.project;
  pin.placeholder = "비우면 임시 이름";
  pin.disabled = busy;
  pin.dataset.hfFocus = "project";
  // 비우면 서버가 임시 이름(「임시 프로젝트 N」)을 붙여 올린 문서들을 한 프로젝트로 묶는다 — 이름은 연 뒤에 정한다(② §17 「임시 프로젝트」, 2026-11-18)
  pin.title = "적으면 목적 문서가 그 프로젝트의 워크플로우 다음 라운드로 시작합니다 — 비우면 임시 이름(임시 프로젝트 N)으로 묶고, 연 뒤 작업 개요의 프로젝트 칸에 이름을 적으면 바뀝니다";
  pin.oninput = () => { hf.project = pin.value; };
  // 고르기 목록 — 작업 개요의 프로젝트 칸과 같은 도우미(project_workspace.js projectComboAttach — 「새 프로젝트」 로 만든 문서 없는 프로젝트도 보인다). 고르면 그 이름을 적어 둔다(저장은 TASK 카드를 누를 때)
  if (typeof projectComboAttach === "function") projectComboAttach(pin, { list: "homeFilesProjectList", commit: () => { hf.project = pin.value; } });
  else { const dl = el("datalist"); dl.id = "homeFilesProjects"; for (const p of hfProjects()) dl.append(new Option(p)); pin.setAttribute("list", dl.id); pl.append(dl); }
  pl.prepend(el("span", null, "프로젝트"), pin);
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
  // 「자동 진행」 · 「LLM 검토」 는 **사업계획서 취합에만** 쓰인다 — 묶음 이름으로 그렇게 보인다(2026-11-16: 전에는 모든 TASK 의 옵션처럼 보였다 — astra). 다른 TASK 는 연 뒤 에이전트가 단계를 안내한다
  const quick = el("span", "hf-group");
  quick.setAttribute("role", "group");
  quick.setAttribute("aria-label", "사업계획서 취합의 진행 방식");
  quick.title = "사업계획서 취합에만 쓰입니다 — 다른 워크플로우는 문서를 연 뒤 에이전트가 사전 준비 · 다음 단계를 안내하고, 문서를 바꾸는 단계는 카드에서 확인받습니다";
  quick.append(el("span", "hf-group-name", "사업계획서 취합"),
    check("자동 진행", "auto", "사업계획서 취합 — 켜고 카드를 누르면 확인 한 번 뒤 끝까지 한 번에 취합합니다(간단 모드 — 넣지 않고 남긴 것은 연 뒤 단계별로 보정). 끄면 올리고 등록만 해서 단계별로 진행합니다(세부 작업 모드)"),
    check("LLM 검토", "llm", "자동 진행 때 넣을 수 있다고 본 내용을 LLM 이 한 번 더 봅니다(문서마다 수십 초 · 유료) — 넣을 것을 줄이기만 합니다", !hf.auto));
  // 「편집 구역」(TASK 옵션 — spec_구역 ② §1): 연구개발 TASK 의 문서에서 가려 볼 기준(기관 · 단계 · 차년도). 손대지 않으면(hf.zones null) 꺼진 채로 보이고 그 TASK 의 기본값으로 시작한다 —
  // 하나라도 누르면 그때부터 사람이 고른 것(모두 끄면 끔)이고 TASK 를 시작한 뒤 한 번 적는다(hfOpenTarget). 손대지 않은 것과 모두 끈 것은 체크가 같아 보여 옆에 글로 가른다(「TASK 기본값대로」 · 「모두 끔」)
  const zg = el("span", "hf-group hf-zones"), znote = el("span", "hf-zones-note");
  const zoneState = () => {
    znote.textContent = hf.zones == null ? "워크플로우 기본값대로" : hf.zones.length ? "" : "모두 끔";
    znote.hidden = !znote.textContent;
    zg.title = "연구개발 워크플로우(양식 표준화 · 양식 맞추기 · 취합 · 이관)에서 문서의 문단·표가 어느 기관·단계·차년도의 것인지 가려 보입니다 — 화면 표시일 뿐 파일은 그대로 · 연 뒤 「작업 개요」 의 「편집 구역」 줄에서 바꿀 수 있습니다.\n"
      + `손대지 않으면 워크플로우의 기본값(${hfZonesDefaults() ? `${hfZonesDefaults()} · 그 밖의 워크플로우는 켠 것 없음` : "어느 워크플로우도 켠 것 없음"})\n`
      + (hf.zones == null ? "지금: 손대지 않음 — 시작하는 워크플로우의 기본값대로 보입니다"
        : hf.zones.length ? `지금 고른 기준: ${hfZoneNames(hf.zones)} — 시작하는 연구개발 워크플로우에 이 기준을 적습니다`
          : "지금: 모두 끔 — 시작하는 연구개발 워크플로우에서 편집 구역을 보이지 않습니다(기본값 대신 끈 것으로 적습니다)");
  };
  const zoneCheck = ([dim, name]) => {
    const lab = el("label", "hf-check"), cb = el("input");
    cb.type = "checkbox";
    cb.checked = !!hf.zones && hf.zones.includes(dim);
    cb.disabled = busy;
    cb.dataset.hfFocus = `zones:${dim}`;
    cb.dataset.hfZone = dim;
    cb.onchange = () => { // 누른 것만 바꾸고 나머지는 지금 보이는 그대로(손대지 않았으면 꺼진 것) — 차례는 늘 기관 · 단계 · 차년도
      hf.zones = HF_ZONES.map(([d]) => d).filter((d) => (d === dim ? cb.checked : !!hf.zones && hf.zones.includes(d)));
      zoneState();
    };
    lab.append(cb, el("span", null, name));
    return lab;
  };
  zg.setAttribute("role", "group");
  zg.setAttribute("aria-label", "편집 구역 — 문서에서 가려 볼 기준");
  zg.append(el("span", "hf-group-name", "편집 구역"), ...HF_ZONES.map(zoneCheck), znote);
  zoneState();
  opts.append(pl, quick, zg);
  const foot = el("div", "hf-foot"), more = el("button", "btn sm", "파일 더하기"), plain = el("button", "btn sm", "워크플로우 없이 열기");
  more.type = plain.type = "button";
  more.disabled = busy;
  more.dataset.hfFocus = "more";
  more.title = "hwp·hwpx·docx 문서를 더 고릅니다 — 이 카드에 놓아도 됩니다";
  more.onclick = homeFilesPick;
  const plainDoc = hf.files[ti]; // 워크플로우 없이 열 문서 — 목록에서 고른 것(대시보드의 양식과 무관)
  plain.disabled = busy || !plainDoc;
  plain.dataset.hfPlain = "1";
  plain.title = plainDoc ? `「${plainDoc.name}」 을 워크플로우 없이 그냥 엽니다(편집 · 검증 — docx 도)` : "목적 문서를 먼저 고르세요";
  plain.onclick = homeFilesPlain;
  foot.append(more, plain, el("span", "hf-next", "↓ 아래 워크플로우 카드를 누르면 시작합니다 — 연 뒤에는 에이전트가 다음 단계를 안내합니다"));
  box.append(head, cap, rows, opts, foot);
  if (hf.busy || hf.err) {
    const st = el("p", "hf-status" + (hf.err ? " err" : ""));
    st.setAttribute("role", hf.err ? "alert" : "status");
    if (hf.busy) st.append(el("i", "hf-spin"));
    st.append(el("span", null, hf.err || hf.busy));
    box.append(st);
  }
  if (focus) { const to = box.querySelector(`[data-hf-focus="${CSS.escape(focus)}"]`); if (to && !to.disabled) to.focus({ preventScroll: true }); }
  if (typeof homeAgentDraw === "function") homeAgentDraw(); // 오른쪽 에이전트 대화창이 같은 목록을 보인다(파일 요약 · 목적 문서 — doc_agent_work.js)
}

function hfBusy(text) { hf.busy = text; if (text) hf.err = ""; homeFilesDraw(); }
function hfFail(text) { hf.busy = ""; hf.err = text; homeFilesDraw(); }
function hfUsed(files) { // 올린 문서는 목록에서 뺀다 — 안 쓴 문서는 남는다(시작 화면에 돌아오면 보임)
  hf.files = hf.files.filter((f) => !files.includes(f));
  for (const file of files) hf.aliases.delete(file);
  Object.assign(hf, { target: -1, busy: "", err: "" });
  homeFilesDraw();
}

async function homeFilesPlain() { // 「TASK 없이 열기」 — 목적 문서를 그냥 연다(전의 「파일 선택」 과 같다: openFile) + 별칭
  const f = hf.files[hfTarget()], alias = hfNorm(hf.alias, 40);
  if (!f || hf.busy || homeTaskBusy || !confirmDiscard()) return;
  hfBusy(`「${f.name}」 여는 중…`);
  try {
    const got = await sameFileUpload(f, { onAsk: () => hfBusy(`「${f.name}」 — 같은 파일로 하던 작업이 있습니다. 떠 있는 창에서 고르세요`) }); // 같은 파일로 하던 작업이 있으면 묻는다(same_file.js — spec_작업 ② §1 「같은 파일은 묻고 연다」)
    if (!got) { hfBusy(""); refreshSaveState(); return; } // 창을 닫음 — 목록 그대로
    const r = got.r;
    await opened(r, () => openFile(f, true));
    hfUsed([f]);
    if (alias && state.stored && state.id === r.docId) {
      try { await api(`/api/works/${r.docId}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias }) }); await loadWorks(); }
      catch (e) { toast(`약칭을 저장하지 못했습니다: ${e.message}`, true); }
    }
  } catch (e) { setSaveState("err", "열지 못함"); hfFail(`열지 못했습니다: ${e.message}`); }
}

// 목적 문서를 올려 열고 그 TASK 로 적는다 → {id, task, note} | {opened: 작업 id}(「그대로 열기」 — TASK 시작은 멈춤) | null(창을 닫음).
// 같은 파일로 하던 작업이 있으면 묻는다(same_file.js — ② §1 「같은 파일은 묻고 연다」, 2026-11-18): 다른 TASK · 다른 프로젝트 · 기관 문서 · 다른 역할이었던 작업의 줄은 「그대로 열기」 만
// (그 작업의 TASK 를 바꾸지 않는다 — 전(11-13~11-17)에는 묻지 않고 새 작업으로 열었다). 창의 「새 작업으로 시작」 은 프로젝트 칸(처음 값 = 이 목록의 프로젝트)의 이름으로 시작한다.
async function hfOpenTarget(job, file, { project, alias, zones = null }) { // zones = 목록에서 고른 편집 구역의 기준(hf.zones — null 이면 손대지 않음)
  const cat = TASK_CATALOG[job], blank = { kind: "", file: "", job: "", project: "" };
  const fit = (w) => {
    const t = { ...blank, ...(w.task || {}) };
    if (t.job && t.job !== job) return `다른 워크플로우(「${taskName("job", t.job) || t.job}」)`;
    if (t.file === "part") return "기관 문서로 쓰던 작업";
    if (cat.target && t.job === job && t.file && t.file !== cat.target) return `다른 역할(${taskName("file", t.file)})`;
    if (project && t.project && t.project !== project) return `다른 프로젝트(「${t.project}」)`;
    return true;
  };
  const got = await sameFileUpload(file, { job, project, fit, onAsk: () => hfBusy(`「${file.name}」 — 같은 파일로 하던 작업이 있습니다. 떠 있는 창에서 고르세요`) });
  if (!got) return null;
  if (got.act === "open") return { opened: got.id };
  if (got.act === "new") project = got.project; // 창의 프로젝트 칸이 목록의 칸보다 먼저(사람이 마지막에 고친 값)
  const r = got.r;
  await load(r.docId);
  const fresh = !r.reused;
  const note = { use: "같은 파일로 하던 작업을 이어서 엽니다", reset: "작업 내용을 초기화했습니다 — 올린 원본부터 다시 시작합니다", new: "같은 파일로 하던 작업은 그대로 두고 새 작업으로 열었습니다" }[got.act] || "";
  if (state.id !== r.docId) throw new Error("그 사이 다른 문서를 열었습니다");
  const cur = { ...blank, ...state.task }, role = cat.target || cur.file || cat.file; // 목적 문서 종류: 이관 = 연차보고서 · 취합 = 취합본 · 양식 표준화 · 양식 맞추기 = 양식 판정(못 정하면 그 TASK 의 문서)
  let temp = "";
  if (state.stored) {
    const put = () => api(`/api/works/${r.docId}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ ...cur, kind: taskKindOf(job), job, file: role }) }); // 작업 종류는 TASK 가 정한다(task_catalog.js — 「문서 일반 편집」 = 일반 문서)
    let res;
    if (cur.project) res = await put(); // 프로젝트에 든 작업을 이어 엶 — 그 프로젝트 그대로
    else {
      // 그 프로젝트의 그 TASK 다음 라운드(② §17) — 이름을 비웠으면 서버가 임시 이름(「임시 프로젝트 N」 — ② §17 「임시 프로젝트」, 2026-11-18: 전에는 프로젝트 없이 문서마다 따로 보였다)
      try { res = await api(`/api/works/${r.docId}/start-task`, { method: "POST", headers: H_JSON, body: JSON.stringify(project ? { project, job, file: role } : { project: "", temp: true, job, file: role }) }); }
      catch (e) { if (project || e.status !== 409) throw e; res = await put(); } // 새로 올린 문서가 아닌 작업(새 라운드로 만든 것 등) — 이름을 안 적었으면 전처럼 프로젝트 없이
      if (res.temp) temp = (res.task || {}).project || "";
    }
    if (state.id === r.docId) state.task = res.task;
    if (alias) { // 별칭을 못 적어도 TASK 는 시작한다(서버가 별칭 끝점을 모르는 옛 서버일 때 등) — 알림만
      try { await api(`/api/works/${r.docId}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias }) }); }
      catch (e) { toast(`약칭을 저장하지 못했습니다: ${e.message}`, true); }
    }
    if (taskKindOf(job) === "rnd" && state.id === r.docId) { // 편집 구역(TASK 옵션 — spec_구역 ② §1)은 연구개발 TASK 에만 — 일반 문서의 TASK 는 고름을 안 쓴다
      // 사람이 고른 기준만 그 TASK 묶음(프로젝트 · TASK · 라운드)에 적는다 — 손대지 않았으면 안 보낸다(기본값 · 이어 여는 작업은 전에 정한 것 그대로). 못 적어도 TASK 는 시작한다 — 알림만
      if (zones != null) {
        try { await api(`/api/works/${r.docId}/task-options`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ zones: { dims: zones } }) }); }
        catch (e) { toast(`편집 구역의 기준을 저장하지 못했습니다: ${(e.body && e.body.detail && e.body.detail.message) || e.message} — 연 뒤 「작업 개요」 의 「편집 구역」 줄에서 다시 고르세요`, true); }
      }
      if (typeof zonesLoad === "function") Promise.resolve().then(() => zonesLoad(true)).catch(() => {}); // TASK 묶음이 정해졌다 — 문서를 열 때 읽은 편집 구역을 그 묶음의 옵션으로 다시 읽는다(zones.js — 못 읽어도 TASK 는 시작한다)
    }
  } else state.task = { ...cur, kind: taskKindOf(job), job, file: role, project: project || cur.project }; // 작업 저장이 꺼져 있으면 이 화면에서만(② §10)
  taskDraw();
  await loadWorks(); // 보이는 이름(프로젝트 꼬리 · 별칭)도 여기서 맞춘다(docSwitchDraw)
  if (state.id !== r.docId) throw new Error("그 사이 다른 문서를 열었습니다");
  if (fresh) firstRun(); // 새 작업 — 첫 분석(② §9)
  taskEnter(job); // 그 TASK 가 처음 여는 보기(app.js — 보통 작업 개요 · 문서 일반 편집은 에이전트 · 문서 서식 복사는 2열 「서식 복사」)
  const named = temp ? `프로젝트 이름이 없어 임시 이름 「${temp}」 로 묶었습니다 — 「작업 개요」 의 프로젝트 칸(또는 작업 리스트의 「이름 정하기」)에 이름을 적으면 바뀝니다` : "";
  return { id: r.docId, task: state.task, note: [note, named].filter(Boolean).join("\n") };
}

async function hfAddSource(main, file, role, alias = "") { // 이관의 원본 문서(사업계획서) — 늘 새 작업으로 올려 같은 프로젝트·TASK·라운드의 그 종류로 적는다(첨부 파일 칸이 저절로 잇는다 — ② §11)
  const t = main.task || {}, name = taskName("file", role);
  toast(`${file.name} — ${name}로 올리는 중…${/\.hwp$/i.test(file.name) ? "(한글이 hwpx 로 바꿈)" : ""}`);
  try {
    const fd = new FormData();
    fd.append("file", file);
    const d = await api("/api/docs?new=1", { method: "POST", body: fd });
    await api(`/api/works/${d.docId}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ kind: taskKindOf(t.job), file: role, job: t.job, project: t.project, ...(t.round ? { round: t.round } : {}) }) });
    let aliasError = "";
    if (alias) {
      try { await api(`/api/works/${d.docId}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias }) }); }
      catch (e) { aliasError = ` · 약칭을 저장하지 못했습니다: ${e.message}`; }
    }
    api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 2단계 자리 연결이 그 결과를 본다
    if (state.id === main.id) await loadWorks();
    toast(`${file.name} — ${name} 칸에 넣었습니다${aliasError}`, !!aliasError);
    return true; // 올렸다(약칭만 못 적은 것도) — 첫 화면의 대시보드 준비 길(homeFilesStart)이 본다 · homeFilesGo 는 전처럼 알림만 쓴다
  } catch (e) { toast(`${name}를 올리지 못했습니다: ${e.message} — 작업 개요의 ${name} 칸에서 다시 올리세요`, true); return false; }
}

async function homeFilesGo(job) { // 목록이 있을 때 TASK 카드 — 그 TASK 로 시작(② §15-1 표)
  const t = TASK_CATALOG[job];
  if (!t || hf.busy || homeTaskBusy) return;
  if (t.soon) { toast(`워크플로우 「${t.name}」 — 준비 중입니다`); return; }
  if (!t.gather && hfUseForm(job)) return hfStartForm(job, { stay: false }); // 목적 문서 칸 = 저장한 양식(고정 · 기본값이고 목적 문서를 직접 안 고름 — spec_워크플로우 ② §18-9) — 시작한 뒤 문서 화면을 연다
  const ti = hfTarget(), target = hf.files[ti];
  const ask = (msg, sel) => { toast(msg, true); const to = sel && $("homeFiles").querySelector(sel); if (to) to.focus(); };
  if (!target) { ask("목적 문서를 먼저 고르세요 — 내용을 받는 문서(이관 = 연차보고서 · 취합 = 취합본 · 양식 표준화 · 양식 맞추기 = 맞출 문서)", "input[type=radio]"); return; }
  const exts = taskAcceptOf(job).filter((x) => x !== "pdf"); // 그 TASK 의 목적 문서 형식(task_catalog.js accept — 보통 hwp·hwpx · 「문서 서식 복사」 는 docx 도: spec_서식복사 ② §1). PDF 는 목록에 없다
  if (!exts.includes(hfExt(target))) { ask(`워크플로우는 ${exts.join("·")} 문서로 시작합니다 — docx 는 「워크플로우 없이 열기」 로 엽니다(워크플로우 「문서 서식 복사」 는 docx 도 됩니다)`, "[data-hf-plain]"); return; }
  const others = hf.files.filter((_, i) => i !== ti), project = hfNorm(hf.project, 60), alias = hfNorm(hf.alias, 40), auto = hf.auto, llm = hf.llm;
  const zones = hf.zones && [...hf.zones]; // 편집 구역의 기준 — 누를 때의 고름(null = 손대지 않음 → 그 TASK 의 기본값)
  const aliases = new Map(hf.files.map((file) => [file, hfNorm(hf.aliases.get(file), 40)]));
  const sourceRole = (t.files || []).find((k) => k !== t.target) || "";
  let use = [];
  if (t.gather) {
    if (others.some((f) => !HF_TASK.test(f.name))) { ask("기관 문서도 hwp·hwpx 여야 합니다 — docx 는 목록에서 빼 주세요"); return; }
    if (auto && !others.length) { ask("자동 진행에는 기관 문서가 하나 이상 있어야 합니다 — 「파일 더하기」 로 더하거나 「자동 진행」 을 끄세요", "[data-hf-focus=more]"); return; }
    use = others; // 자동 진행도 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 간단 모드의 차례를 적은 확인 창: design.md §18 「확인 창」)
  } else if (t.files) {
    if (hfSourceFixedAsk(job, others, ask)) return;
    if (others.length > 1) { ask(`이관은 연차보고서(목적 문서) 하나와 ${taskName("file", sourceRole)} 하나로 합니다 — 목록에 문서가 ${hf.files.length}개입니다. 남길 둘만 두세요`); return; }
    if (others.length && !HF_TASK.test(others[0].name)) { ask(`${taskName("file", sourceRole)}도 hwp·hwpx 여야 합니다`); return; }
    use = others; // 프로젝트 이름을 비워도 된다 — 임시 이름으로 두 문서를 같은 프로젝트에 묶는다(② §17 「임시 프로젝트」 · 2026-11-18 전에는 이름을 적어야 시작했다)
  } else if (others.length && !confirm(`워크플로우 「${t.name}」 ${hfJosa(t.name, "은", "는", "은")} ${hfDocName(job)} 하나로 합니다.\n\n「${target.name}」 만 올리고 나머지 ${others.length}개는 목록에 남깁니다. 계속할까요?`)) return;
  if (!confirmDiscard()) return;
  const card = document.querySelector(`#taskCards [data-task="${job}"]`);
  hfBusy(`워크플로우 「${t.name}」 — ${hfDocName(job)} 「${target.name}」 올리는 중…${/\.hwp$/i.test(target.name) ? "(한글이 hwpx 로 바꿈 — 수십 초)" : ""}`);
  homeTaskBusy = true;
  if (card) card.classList.add("busy");
  setSaveState("busy", `${target.name} 여는 중…`);
  let main;
  // 준비(목적 문서 열기 → 원본·기관 문서 올리기 → 간단 모드)가 끝날 때까지 작업 진행 에이전트의 시작 턴을 붙든다 — 준비가 끝난 상태로 한 번만 설명하고, 간단 모드가 돌았으면 그 결과를 보고한다(doc_agent_work.js agentWorkHold · spec_작업에이전트 ② §7)
  if (typeof agentWorkHold === "function") agentWorkHold(true);
  try {
    main = await hfOpenTarget(job, target, { project, alias, zones });
    if (!main || main.opened) { // 창을 닫음 · 「그대로 열기」 — TASK 시작은 멈추고 목록은 그대로(spec_작업 ② §15-1 「올림」)
      main = null;
      hfBusy("");
      if (!state.id) refreshSaveState();
      return false;
    }
    if (sourceRole && use.length && !(main.task || {}).project) { // 프로젝트로 묶이지 않음(작업 저장이 꺼짐 · 새로 올린 문서가 아닌 작업을 이어 엶) — 원본 문서는 묶을 곳이 없어 목록에 남긴다
      toast(`${taskName("file", sourceRole)} 「${use[0].name}」 은 목록에 남겼습니다 — 목적 문서가 프로젝트에 묶이지 않아 함께 시작하지 못했습니다(작업 개요의 첨부 파일 칸에서 올리세요)`, true);
      use = [];
    }
    hfUsed([target, ...use]);
    if (main.note) toast(main.note);
    if (t.gather && use.length) await gatherQuickRun(main.id, target.name, use, { llm, uploadOnly: !auto, aliases }); // 취합 — 기관 문서 올리기·등록(+ 자동 진행이면 끝까지): gather_quick.js
    else if (sourceRole && use.length) await hfAddSource(main, use[0], sourceRole, aliases.get(use[0]));
    else if (sourceRole && (main.task || {}).project && hfSourceSlot(job) && !(await hfHasSource(job, main.id, main.task))) { // 원본 칸 = 저장한 양식(목록에 원본 파일이 없음 · 고정)
      if (await hfAddSourceForm(main, job, hfSourceSlot(job))) await loadWorks(); // 첨부 파일 칸이 저절로 잇는다(② §11)
    }
    return true; // 시작함(첫 화면 대화창이 본다 — doc_agent_work.js homeAgentAct)
  }
  catch (e) { // 문서는 열렸는데 TASK·별칭 저장에서 실패했을 수도 있다 — 시작 화면의 까닭 줄은 그때 안 보이므로 알림도
    setSaveState("err", "열지 못함");
    hfFail(main ? `워크플로우 「${t.name}」의 원본 문서를 준비하지 못했습니다: ${e.message}` : `${hfDocName(job)}를 워크플로우 「${t.name}」 ${hfJosa(t.name, "으로", "로", "로")} 열지 못했습니다: ${e.message}`);
    toast(hf.err, true);
    return !!main; // 목적 문서는 열렸다(원본 문서만 못 올림) — 시작한 것으로 본다
  } finally { homeTaskBusy = false; if (card) card.classList.remove("busy"); homeFilesDraw(); if (typeof agentWorkHold === "function") agentWorkHold(false); }
}

// 「워크플로우 시작」 — 첫 화면의 대시보드(home_dash.js · spec_작업에이전트 ② §10 「첫 화면의 대시보드」 의 「시작」): **문서 화면을 열지 않고** 이 문서 목록으로 작업을 만든다.
// homeFilesGo 와 같은 검사(그 글 그대로) · 같은 끝점(올리기 · 같은 파일 고르기 · start-task | task · 약칭 · 편집 구역 기준 · 기본 분석 · 원본 문서 올리기)이고, 편집기의 load() · taskEnter · firstRun 만 하지 않는다 —
// 올린(또는 이어 하는) 작업의 지금 task 는 작업 목록(GET /api/works)에서 읽는다(GET /api/docs/{id} 는 문서를 통째로 읽는다 — 부르지 않는다). 준비까지다: 실행은 대시보드에서 묶음의 「한 번에 진행」 을 사람이 누를 때만.
// → {id(목적 문서 작업 id), task, sources[원본 문서 작업 id], failed[못 올린 파일 이름], note} | {opened: 작업 id}(같은 파일 고르기의 「그대로 열기」 — 시작은 멈춤) | null(그만둠 · 거절 — 까닭은 알림).
// 이번 범위 = 이관형(TASK_CATALOG[job].files — 붙박이 이관 · 조립한 것)과 문서 하나인 워크플로우. 취합은 여기서 시작하지 않는다(기관 문서 올리기 · 등록은 문서 화면의 길 — gather_quick.js: 대시보드의 취합 「워크플로우 시작」 은 hdStart 가 워크플로우 카드의 길 homeFilesGo 로 보낸다).
// **homeFilesGo · hfOpenTarget 의 검사 · 글을 고치면 여기도 함께 본다**(두 길이 같은 검사여야 한다 — 검사를 한 함수로 묶는 것은 뒤로 미룸).
// form = 목적 문서 칸을 저장한 양식으로(워크플로우 설정의 기본값 · 고정 — 고정이면 늘 양식: hfStartForm).
async function homeFilesStart(job, { form = false } = {}) {
  const t = TASK_CATALOG[job];
  if (!t || hf.busy || homeTaskBusy) return null;
  if (t.soon) { toast(`워크플로우 「${t.name}」 — 준비 중입니다`); return null; }
  if (t.gather) { toast("취합은 문서 화면을 여는 길(왼쪽 워크플로우 카드 · 대시보드의 「워크플로우 시작」)로 시작합니다", true); return null; } // 대시보드는 취합을 이 함수 앞에서 워크플로우 카드의 길(homeFilesGo)로 보낸다 — 여기는 지켜 둠
  const slot = hfSlot(job);
  if (slot && (form || slot.mode === "fixed")) return hfStartForm(job, { stay: true });
  const ti = hfTarget(), target = hf.files[ti];
  const ask = (msg, sel) => { toast(msg, true); const to = sel && $("homeFiles").querySelector(sel); if (to) to.focus(); };
  if (!target) { ask("목적 문서를 먼저 고르세요 — 내용을 받는 문서(이관 = 연차보고서 · 취합 = 취합본 · 양식 표준화 · 양식 맞추기 = 맞출 문서)", "input[type=radio]"); return null; }
  const exts = taskAcceptOf(job).filter((x) => x !== "pdf");
  if (!exts.includes(hfExt(target))) { ask(`워크플로우는 ${exts.join("·")} 문서로 시작합니다 — docx 는 「워크플로우 없이 열기」 로 엽니다(워크플로우 「문서 서식 복사」 는 docx 도 됩니다)`, "[data-hf-plain]"); return null; }
  const others = hf.files.filter((_, i) => i !== ti), alias = hfNorm(hf.alias, 40), zones = hf.zones && [...hf.zones]; // 누를 때의 고름(약칭 · 편집 구역 기준 — null = 손대지 않음)
  const aliases = new Map(hf.files.map((file) => [file, hfNorm(hf.aliases.get(file), 40)])), sourceRole = (t.files || []).find((k) => k !== t.target) || "";
  let project = hfNorm(hf.project, 60), use = [];
  if (t.files) {
    if (hfSourceFixedAsk(job, others, ask)) return null;
    if (others.length > 1) { ask(`이관은 연차보고서(목적 문서) 하나와 ${taskName("file", sourceRole)} 하나로 합니다 — 목록에 문서가 ${hf.files.length}개입니다. 남길 둘만 두세요`); return null; }
    if (others.length && !HF_TASK.test(others[0].name)) { ask(`${taskName("file", sourceRole)}도 hwp·hwpx 여야 합니다`); return null; }
    use = others; // 프로젝트 이름을 비워도 된다 — 임시 이름으로 두 문서를 같은 프로젝트에 묶는다(② §17 「임시 프로젝트」)
  } else if (others.length && !confirm(`워크플로우 「${t.name}」 ${hfJosa(t.name, "은", "는", "은")} ${hfDocName(job)} 하나로 합니다.\n\n「${target.name}」 만 올리고 나머지 ${others.length}개는 목록에 남깁니다. 계속할까요?`)) return null; // 고른 것과 다른 일을 하게 되는 물음 — 남긴다(design.md §18)
  const blank = { kind: "", file: "", job: "", project: "" };
  const fit = (w) => { // hfOpenTarget 의 fit 과 같다 — 다른 워크플로우 · 기관 문서 · 다른 역할 · 다른 프로젝트였던 작업의 줄은 「그대로 열기」 만
    const x = { ...blank, ...(w.task || {}) };
    if (x.job && x.job !== job) return `다른 워크플로우(「${taskName("job", x.job) || x.job}」)`;
    if (x.file === "part") return "기관 문서로 쓰던 작업";
    if (t.target && x.job === job && x.file && x.file !== t.target) return `다른 역할(${taskName("file", x.file)})`;
    if (project && x.project && x.project !== project) return `다른 프로젝트(「${x.project}」)`;
    return true;
  };
  hfBusy(`워크플로우 「${t.name}」 — ${hfDocName(job)} 「${target.name}」 올리는 중…${/\.hwp$/i.test(target.name) ? "(한글이 hwpx 로 바꿈 — 수십 초)" : ""}`);
  homeTaskBusy = true;
  try {
    const got = await sameFileUpload(target, { job, project, fit, onAsk: () => hfBusy(`「${target.name}」 — 같은 파일로 하던 작업이 있습니다. 떠 있는 창에서 고르세요`) });
    if (!got) { hfBusy(""); return null; } // 창을 닫음 — 목록은 그대로
    if (got.act === "open") { hfBusy(""); return { opened: got.id }; } // 「그대로 열기」 — 이 워크플로우의 시작은 멈춘다(그 작업을 어떻게 보일지는 대시보드가 정한다)
    if (got.act === "new") project = got.project; // 창의 프로젝트 칸이 목록의 칸보다 먼저(사람이 마지막에 고친 값)
    const r = got.r, id = r.docId, fresh = !r.reused;
    const note = { use: "같은 파일로 하던 작업을 이어서 합니다", reset: "작업 내용을 초기화했습니다 — 올린 원본부터 다시 시작합니다", new: "같은 파일로 하던 작업은 그대로 두고 새 작업으로 시작했습니다" }[got.act] || "";
    hfBusy(`워크플로우 「${t.name}」 — ${hfDocName(job)} 「${target.name}」 준비하는 중…`);
    const row = (await api("/api/works")).find((w) => w.id === id); // 그 작업의 지금 task(이어 하는 작업이면 프로젝트 · 라운드가 있다) — 문서는 읽지 않는다
    if (!row) throw new Error("작업 저장이 꺼져 있어 문서 화면을 열지 않고는 시작할 수 없습니다 — 왼쪽 워크플로우 카드로 시작하세요");
    const cur = { ...blank, ...(row.task || {}) }, role = t.target || cur.file || t.file; // 목적 문서 종류: 이관 = 연차보고서 · 그 밖 = 그 작업에 적힌 종류(없으면 그 워크플로우의 문서)
    const put = () => api(`/api/works/${id}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ ...cur, kind: taskKindOf(job), job, file: role }) });
    let res, temp = "";
    // 이미 그 프로젝트의 이 워크플로우 · 이 종류로 적힌 작업을 이어 함 — 적을 것이 없다(같은 값을 다시 보내지 않는다: 그 묶음의 「한 번에 진행」 이 서버에서 도는 동안에는 칸을 못 바꿔 409 — 도는 작업의 대시보드로 돌아오지 못한다)
    if (cur.project && cur.job === job && cur.file === role && cur.kind === taskKindOf(job)) res = { task: row.task };
    else if (cur.project) res = await put(); // 프로젝트에 든 작업을 이어 함 — 그 프로젝트 그대로
    else {
      // 그 프로젝트의 그 워크플로우 다음 라운드(② §17) — 이름을 비웠으면 서버가 임시 이름(「임시 프로젝트 N」)
      try { res = await api(`/api/works/${id}/start-task`, { method: "POST", headers: H_JSON, body: JSON.stringify(project ? { project, job, file: role } : { project: "", temp: true, job, file: role }) }); }
      catch (e) { if (project || e.status !== 409) throw e; res = await put(); } // 새로 올린 문서가 아닌 작업 — 이름을 안 적었으면 전처럼 프로젝트 없이(hfOpenTarget 과 같다)
      if (res.temp) temp = (res.task || {}).project || "";
    }
    const task = res.task || {};
    if (alias) { // 약칭을 못 적어도 시작한다 — 알림만
      try { await api(`/api/works/${id}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias }) }); }
      catch (e) { toast(`약칭을 저장하지 못했습니다: ${e.message}`, true); }
    }
    if (taskKindOf(job) === "rnd" && zones != null) { // 편집 구역의 기준(워크플로우 옵션 — spec_구역 ② §1) — 사람이 고른 것만 그 묶음에 적는다 · 못 적어도 시작한다
      try { await api(`/api/works/${id}/task-options`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ zones: { dims: zones } }) }); }
      catch (e) { toast(`편집 구역의 기준을 저장하지 못했습니다: ${(e.body && e.body.detail && e.body.detail.message) || e.message} — 연 뒤 「작업 개요」 의 「편집 구역」 줄에서 다시 고르세요`, true); }
    }
    if (fresh && !/\.docx$/i.test(target.name)) { // 새 작업 · 초기화한 작업 — 기본 분석(헤딩 · 표: 스크립트만 — app.js firstRun 과 같은 끝점 · docx 는 없다). 이미 도는 분석이 있으면(409) 그대로 둔다
      try { await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }); }
      catch (e) { if (e.status !== 409) console.warn("기본 분석(헤딩 · 표)을 시작하지 못했습니다:", e.message); } // 못 돌려도 시작한다 — 대시보드의 「문서 검토」 가 분석부터 한다
    }
    const failed = [], sform = sourceRole && !use.length && task.project ? hfSourceSlot(job) : null;
    let formSource = "";
    if (sourceRole && use.length && !task.project) { // homeFilesGo 와 같다 — 목적 문서가 프로젝트에 묶이지 않아(새로 올린 문서가 아닌 작업을 이어 함) 원본 문서는 묶을 곳이 없다: 목록에 남긴다
      toast(`${taskName("file", sourceRole)} 「${use[0].name}」 은 목록에 남겼습니다 — 목적 문서가 프로젝트에 묶이지 않아 함께 시작하지 못했습니다(작업 개요의 첨부 파일 칸에서 올리세요)`, true);
      failed.push(use[0].name);
      use = [];
    } else if (sourceRole && use.length) {
      hfBusy(`워크플로우 「${t.name}」 — ${taskName("file", sourceRole)} 「${use[0].name}」 올리는 중…${/\.hwp$/i.test(use[0].name) ? "(한글이 hwpx 로 바꿈 — 수십 초)" : ""}`);
      if (!(await hfAddSource({ id, task }, use[0], sourceRole, aliases.get(use[0])))) { failed.push(use[0].name); use = []; } // 못 올린 원본 문서는 목록에 남는다(까닭은 hfAddSource 의 알림)
    } else if (sform && !(await hfHasSource(job, id, task))) { // 원본 칸 = 저장한 양식(목록에 원본 파일이 없음 · 고정 — 이어 하는 작업에 이미 원본이 있으면 그대로)
      hfBusy(`워크플로우 「${t.name}」 — ${taskName("file", sourceRole)} 칸을 ${hfFormLabel(sform.form)}으로 채우는 중…`);
      formSource = await hfAddSourceForm({ id, task }, job, sform);
      if (!formSource) failed.push(hfFormLabel(sform.form));
    }
    hfUsed([target, ...use]); // 올린 문서는 목록에서 뺀다
    await loadWorks();
    const same = (w) => { const x = w.task || {}; return w.id !== id && x.file === sourceRole && x.job === task.job && x.project === task.project && (x.round || 1) === (task.round || 1); };
    const sources = use.length ? worksList.filter(same).slice(0, 1).map((w) => w.id) : formSource ? [formSource] : []; // 방금 올린 원본 문서(작업 목록은 최근 바뀐 차례 — 같은 묶음의 그 종류 가운데 맨 앞)
    const named = temp ? `프로젝트 이름이 없어 임시 이름 「${temp}」 로 묶었습니다 — 문서를 연 뒤 「작업 개요」 의 프로젝트 칸(또는 작업 리스트의 「이름 정하기」)에 이름을 적으면 바뀝니다` : "";
    return { id, task, sources, failed, note: [note, named].filter(Boolean).join("\n") };
  } catch (e) {
    hfFail(`${hfDocName(job)}를 워크플로우 「${t.name}」 ${hfJosa(t.name, "으로", "로", "로")} 준비하지 못했습니다: ${e.message}`);
    toast(hf.err, true);
    return null;
  } finally { homeTaskBusy = false; if (!state.id) setSaveState("", ""); homeFilesDraw(); } // 같은 파일 고르기가 남긴 「… 여는 중…」(상단 바)을 걷는다 — 문서를 열지 않았다
}

// ---------------------------------------------------------------- 저장한 양식으로 시작(spec_워크플로우 ② §18-9 「양식」 · 고친 규칙 ② §18-12 ⑧)
// 워크플로우 설정(GET /api/form-files 의 slots — 목적 문서 칸에 건 양식: default = 기본값 · fixed = 고정)을 읽어 두고, 시작할 때 목적 문서 칸을 그 양식으로 채운다.
// **고정 · 기본값은 서버의 「워크플로우 시작」(POST /api/workflow-start)이 지킨다** — 화면은 그 요청에 워크플로우 · 양식 id · 해시 · 설정의 판(rev)을 싣고, 서버가 견준 뒤 새 작업을 만든다(올리기 길로 고정을 돌아가지 못한다).
// 같은 시작을 다시 보내면(답을 못 받음 — 네트워크) 같은 request 열쇠로 → 같은 작업. 원본 문서 올리기 · 기본 분석 · 편집 구역 기준은 올리는 길(homeFilesStart)과 같은 끝점이다.
// 화면 말: 「저장한 양식」 · 「양식: 없음 · 기본값 · 고정」(「템플릿」 은 개요 · 서식의 말 — 여기 쓰지 않는다).
const hfForms = { data: null, at: 0, wait: null, err: "", req: null, sreq: null }; // data = GET /api/form-files · req = {job, form, key} 답을 못 받은 시작(같은 열쇠로 다시) · sreq = {main, form, key} 답을 못 받은 원본 칸 채우기
const HF_FORM_MODE = { default: "기본값", fixed: "고정" };
async function hfFormsLoad(force = false) { // → data | null(못 읽음 — 옛 서버면 404: 양식 없이 전처럼). 10초 안의 것은 다시 읽지 않는다(force 면 읽음 — 시작 직전)
  if (!force && hfForms.data && Date.now() - hfForms.at < 10000) return hfForms.data;
  if (hfForms.wait) return hfForms.wait;
  hfForms.wait = (async () => {
    try { const d = await api("/api/form-files"); Object.assign(hfForms, { data: d && typeof d === "object" ? d : null, at: Date.now(), err: "" }); }
    catch (e) { Object.assign(hfForms, { data: e.status === 404 ? { files: [], slots: {}, rev: 0, jobs: [] } : hfForms.data, at: Date.now(), err: e.status === 404 ? "" : e.message }); }
    finally { hfForms.wait = null; }
    if (typeof homeDashDraw === "function") homeDashDraw();
    homeFilesDraw(); // 카드 글 · 목록의 꼬리표(목적 문서 칸이 양식이면 목록의 문서는 원본 문서)
    return hfForms.data;
  })();
  return hfForms.wait;
}
function hfSlot(job, role = "target") { // 그 워크플로우의 그 문서 칸(목적 · 이관의 원본 — 수가 1인 칸: spec_워크플로우 ② §18-9)에 건 양식 → {mode, form, rev} | null(설정 없음 · 아직 못 읽음). form = 저장한 양식(지워졌으면 null)
  const d = hfForms.data, v = d && d.slots && d.slots[job] && d.slots[job][role];
  if (!v || !HF_FORM_MODE[v.mode]) return null;
  return { mode: v.mode, form: (d.files || []).find((f) => f.id === v.file) || null, rev: d.rev || 0 };
}
const hfFormDate = (f) => { const d = new Date((f && f.at ? f.at : 0) * 1000); return f && f.at && Number.isFinite(d.getTime()) ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}` : ""; };
const hfFormLabel = (f) => (f ? `양식 「${f.name}」${hfFormDate(f) ? `(저장한 날 ${hfFormDate(f)})` : ""}` : "지워진 양식"); // 늘 이름 · 저장한 날(② §18-11 ⓔ — 새 해의 양식이 필요할 때 옛 양식으로 조용히 시작하지 않게)
// 목적 문서 칸을 양식으로 채우나 — 고정이면 늘 · 기본값이면 목록에서 목적 문서를 직접 고르지 않았을 때(pick = 대시보드에서 사람이 고른 것: true 양식 · false 목록의 파일 · undefined 저절로)
function hfUseForm(job, pick) {
  const s = hfSlot(job);
  if (!s || !s.form) return false;
  return s.mode === "fixed" || (pick === undefined ? hf.target < 0 : !!pick);
}
// 같은 프로젝트에 이 워크플로우의 목적 문서로 하던 작업 → 작업 줄 | null(② §18-11 ⓕ — 양식으로 시작한 작업은 같은 파일 고르기에 걸리지 않고 늘 새 작업이라, 시작 전에 「이어서」 를 먼저 보인다)
function hfFormResume(job, project = hfNorm(hf.project, 60)) {
  const t = TASK_CATALOG[job];
  if (!t || !project || typeof worksList === "undefined") return null;
  const role = t.target || t.file || "";
  return worksList.find((w) => { const x = w.task || {}; return x.project === project && x.job === job && (!role || x.file === role); }) || null;
}

// 원본 문서 칸에 건 양식(이관형 — 원본 칸이 하나: 2026-11-20 사용자 "각 1이 되는것들은 특정 문서로 지정할 수 있도록, default 로" · spec_워크플로우 ② §18-9) → {mode, form, rev} | null.
// 쓰는 때 = 목적 문서를 만든 뒤(올리기 · 양식 어느 쪽이든) 목록에 원본으로 쓸 파일이 없을 때(기본값) · 늘(고정 — 목록의 파일을 원본 칸에 넣지 않는다: 서버도 PUT …/task 409).
function hfSourceSlot(job) { const t = TASK_CATALOG[job]; if (!t || !t.files) return null; const s = hfSlot(job, "source"); return s && s.form ? s : null; }
function hfSourceFixedAsk(job, files, ask) { // 원본 칸이 고정인데 목록에 원본으로 쓸 파일이 있음 → 물음(true = 멈춤)
  const s = hfSourceSlot(job);
  if (!s || s.mode !== "fixed" || !files.length) return false;
  ask(`원본 문서 칸은 ${hfFormLabel(s.form)}으로 고정돼 있습니다 — 목록에는 목적 문서만 두세요(바꾸려면 워크플로우 페이지의 「문서 칸」)`);
  return true;
}
async function hfHasSource(job, id, task) { // 그 묶음(프로젝트 · 워크플로우 · 라운드)에 원본 문서가 이미 있나 — 이어 하는 작업에 양식을 또 넣지 않게(작업 목록 GET /api/works — 문서는 읽지 않는다)
  const t = TASK_CATALOG[job] || {}, role = (t.files || []).find((k) => k !== t.target) || "";
  if (!role || !task || !task.project) return false;
  try { const rows = await api("/api/works"); return rows.some((w) => { const x = w.task || {}; return w.id !== id && x.file === role && x.job === job && x.project === task.project && (x.round || 1) === (task.round || 1); }); }
  catch { return false; }
}
async function hfAddSourceForm(main, job, s) { // 원본 칸 = 저장한 양식 — POST /api/workflow-start/source(목적 작업의 묶음에 원본 종류로 · 서버가 고정 · 판을 견준다) + 첫 분석(hfAddSource 와 같게) → 원본 작업 id | ""(못 넣음 — 까닭은 알림)
  const t = TASK_CATALOG[job] || {}, role = (t.files || []).find((k) => k !== t.target) || "", name = taskName("file", role) || "원본 문서";
  const r0 = hfForms.sreq && hfForms.sreq.main === main.id && hfForms.sreq.form === s.form.id ? hfForms.sreq : null; // 답을 못 받은 요청 — 같은 열쇠로(서버가 같은 작업을 돌려준다)
  const key = r0 ? r0.key : `hs${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  hfForms.sreq = { main: main.id, form: s.form.id, key };
  try {
    const r = await api("/api/workflow-start/source", { method: "POST", headers: H_JSON, body: JSON.stringify({ job, main: main.id, request: key, source: { form: s.form.id, sha256: s.form.sha256, rev: s.rev } }) });
    hfForms.sreq = null;
    api(`/api/docs/${r.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 올린 원본과 같게
    toast(`${name} 칸을 ${hfFormLabel(s.form)}으로 채웠습니다(양식: ${HF_FORM_MODE[s.mode]})`);
    return r.docId;
  } catch (e) {
    if (e.status) hfForms.sreq = null;
    if (e.status === 409) hfFormsLoad(true);
    toast(`${name}를 ${hfFormLabel(s.form)}으로 넣지 못했습니다: ${(e.body && e.body.message) || e.message} — 작업 개요의 ${name} 칸에서 올리세요`, true);
    return "";
  }
}

// 양식으로 시작 — stay = 첫 화면에 머문다(대시보드 · homeFilesStart 의 돌려줌 꼴) | false = 워크플로우 카드(시작한 뒤 문서 화면을 연다 — homeFilesGo 의 돌려줌 꼴).
// 목적 문서 칸 = 양식 · 목록의 문서는 모두 원본 문서 칸(이관 = 하나까지 · 문서 하나인 워크플로우는 남김).
async function hfStartForm(job, { stay = true } = {}) {
  const t = TASK_CATALOG[job];
  if (!t || hf.busy || homeTaskBusy) return stay ? null : false;
  const was = hfSlot(job), sourceRole = (t.files || []).find((k) => k !== t.target) || "";
  const ask = (msg, sel) => { toast(msg, true); const to = sel && $("homeFiles") && $("homeFiles").querySelector(sel); if (to) to.focus(); };
  if (!was || !was.form) { ask("이 워크플로우의 양식을 찾지 못했습니다 — 워크플로우 페이지 「문서 칸」 에서 다시 거세요"); return stay ? null : false; }
  const project = hfNorm(hf.project, 60), zones = hf.zones && [...hf.zones], aliases = new Map(hf.files.map((file) => [file, hfNorm(hf.aliases.get(file), 40)]));
  let use = [...hf.files];
  if (t.files) {
    if (hfSourceFixedAsk(job, use, ask)) return stay ? null : false;
    if (use.length > 1) { ask(`이관은 목적 문서(${hfFormLabel(was.form)}) 하나와 ${taskName("file", sourceRole)} 하나로 합니다 — 목록에 문서가 ${use.length}개입니다. 원본 문서 하나만 두세요`); return stay ? null : false; }
    if (use.length && !HF_TASK.test(use[0].name)) { ask(`${taskName("file", sourceRole)}도 hwp·hwpx 여야 합니다`); return stay ? null : false; }
  } else {
    if (use.length && !confirm(`워크플로우 「${t.name}」 ${hfJosa(t.name, "을", "를", "를")} ${hfFormLabel(was.form)}으로 시작합니다.\n\n목록의 문서 ${use.length}개는 쓰지 않고 남깁니다 — ${was.mode === "fixed" ? "이 워크플로우는 양식이 고정이라 목적 문서를 바꿀 수 없습니다" : "목록의 문서로 시작하려면 그 문서를 목적 문서로 고르세요"}. 계속할까요?`)) return stay ? null : false; // 고른 것과 다른 일을 하게 되는 물음 — 남긴다(design.md §18)
    use = [];
  }
  if (!confirmDiscard()) return stay ? null : false;
  hfBusy(`워크플로우 「${t.name}」 — ${hfFormLabel(was.form)}으로 목적 문서를 만드는 중…`);
  homeTaskBusy = true;
  try {
    await hfFormsLoad(true); // 시작 직전에 설정을 다시 읽는다 — 읽은 판(rev)과 양식의 해시를 서버가 견준다
    const s = hfSlot(job);
    if (!s || !s.form || s.form.id !== was.form.id || s.mode !== was.mode) throw Object.assign(new Error("워크플로우의 양식 설정이 바뀌었습니다 — 문서 칸을 다시 보고 시작하세요"), { soft: true });
    const r0 = hfForms.req && hfForms.req.job === job && hfForms.req.form === s.form.id ? hfForms.req : null; // 답을 못 받은 시작 — 같은 열쇠로(서버가 같은 작업을 돌려준다)
    const key = r0 ? r0.key : `hf${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
    hfForms.req = { job, form: s.form.id, key };
    let res;
    try {
      res = await api("/api/workflow-start", { method: "POST", headers: H_JSON, body: JSON.stringify({ job, request: key, ...(project ? { project } : { temp: true }), target: { form: s.form.id, sha256: s.form.sha256, rev: s.rev } }) });
    } catch (e) {
      if (e.status) hfForms.req = null; // 서버가 답했다(거절) — 다음 시작은 새 열쇠로 · 답을 못 받았으면 열쇠를 남긴다
      if (e.status === 409) hfFormsLoad(true); // 고정 · 양식 · 설정이 바뀜 — 다시 읽어 문서 칸을 바로잡는다
      throw new Error((e.body && e.body.message) || e.message);
    }
    hfForms.req = null;
    const id = res.docId, task = res.task || {}, temp = res.temp ? task.project || "" : "";
    if (taskKindOf(job) === "rnd" && zones != null) { // 편집 구역의 기준 — homeFilesStart 와 같다(못 적어도 시작한다)
      try { await api(`/api/works/${id}/task-options`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ zones: { dims: zones } }) }); }
      catch (e) { toast(`편집 구역의 기준을 저장하지 못했습니다: ${(e.body && e.body.detail && e.body.detail.message) || e.message} — 연 뒤 「작업 개요」 의 「편집 구역」 줄에서 다시 고르세요`, true); }
    }
    if (s.form.fmt !== "docx") { // 새 작업 — 기본 분석(헤딩 · 표: 스크립트만 — 올리는 길과 같은 끝점)
      try { await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }); }
      catch (e) { if (e.status !== 409) console.warn("기본 분석(헤딩 · 표)을 시작하지 못했습니다:", e.message); }
    }
    const failed = [], sform = sourceRole && !use.length ? hfSourceSlot(job) : null;
    let formSource = "";
    if (sourceRole && use.length) {
      hfBusy(`워크플로우 「${t.name}」 — ${taskName("file", sourceRole)} 「${use[0].name}」 올리는 중…${/\.hwp$/i.test(use[0].name) ? "(한글이 hwpx 로 바꿈 — 수십 초)" : ""}`);
      if (!(await hfAddSource({ id, task }, use[0], sourceRole, aliases.get(use[0])))) { failed.push(use[0].name); use = []; }
    } else if (sform) { // 원본 칸 = 저장한 양식(목록에 원본 파일이 없음 · 고정)
      hfBusy(`워크플로우 「${t.name}」 — ${taskName("file", sourceRole)} 칸을 ${hfFormLabel(sform.form)}으로 채우는 중…`);
      formSource = await hfAddSourceForm({ id, task }, job, sform);
      if (!formSource) failed.push(hfFormLabel(sform.form));
    }
    hfUsed(use);
    await loadWorks();
    const same = (w) => { const x = w.task || {}; return w.id !== id && x.file === sourceRole && x.job === task.job && x.project === task.project && (x.round || 1) === (task.round || 1); };
    const sources = use.length ? worksList.filter(same).slice(0, 1).map((w) => w.id) : formSource ? [formSource] : [];
    const named = temp ? `프로젝트 이름이 없어 임시 이름 「${temp}」 로 묶었습니다 — 문서를 연 뒤 「작업 개요」 의 프로젝트 칸(또는 작업 리스트의 「이름 정하기」)에 이름을 적으면 바뀝니다` : "";
    const note = [`목적 문서를 ${hfFormLabel(s.form)}으로 만들었습니다(양식: ${HF_FORM_MODE[s.mode]})`, named].filter(Boolean).join("\n");
    if (!stay) { // 워크플로우 카드 — 문서 화면을 연다(homeFilesGo 와 같다: 연 뒤 에이전트가 다음 단계를 안내)
      await openWork(id);
      if (state.id === id) taskEnter(job);
      toast(note);
      return true;
    }
    return { id, task, sources, failed, note, form: s.form };
  } catch (e) {
    hfFail(e.soft ? e.message : `워크플로우 「${t.name}」 ${hfJosa(t.name, "을", "를", "를")} 양식으로 시작하지 못했습니다: ${e.message}`);
    toast(hf.err, true);
    return stay ? null : false;
  } finally { homeTaskBusy = false; if (!state.id) setSaveState("", ""); homeFilesDraw(); }
}
if (!(typeof PEEK !== "undefined" && PEEK)) hfFormsLoad(); // 같이 보기의 옆 문서 화면(?peek)은 첫 화면을 보이지 않는다
