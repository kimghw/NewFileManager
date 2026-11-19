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
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { taskOptions: "편집 구역 기준 정함" }); // 「기록」 탭의 이름 — 편집 구역에서 가려 볼 기준을 사람이 정함(서버 task_options_api 의 작업 기록 `taskOptions`: 이 목록 · 「작업 개요」 의 「편집 구역」 줄)
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
    const unsupported = target && !taskAcceptOf(b.dataset.task).includes(hfExt(target));
    b.disabled = busy || (has && (!target || unsupported));
    b.setAttribute("aria-disabled", String(b.disabled));
    const quick = !!task.gather && hf.auto && hf.files.length > 1; // 취합 + 「자동 진행」 + 기관 문서 — 이 카드가 끝까지 한 번에 한다(간단 모드)
    txt.textContent = busy ? "문서 여는 중 " : has && !target ? "목적 문서를 선택하세요 " : unsupported ? "지원하지 않는 파일 형식 " : quick ? "끝까지 자동 진행 " : has ? "목록으로 시작 " : b.dataset.up;
    b.title = busy ? "문서를 여는 중입니다" : has && !target ? "위 파일 카드에서 목적 문서를 하나 고르세요"
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
  const tgt = hf.files[ti], n = hf.files.length - (tgt ? 1 : 0);
  const cap = el("p", "hf-cap", tgt ? `목적 문서 「${tgt.name}」${n ? ` · 원본 문서 ${n}개` : ""} — 아래 워크플로우 카드를 누르면 시작합니다` : "목적 문서(내용을 받는 문서)를 하나 고르세요 — 그 뒤 아래 워크플로우 카드를 누릅니다.");
  const rows = el("div", "hf-rows");
  rows.setAttribute("role", "radiogroup");
  rows.setAttribute("aria-label", "목적 문서 고르기");
  hf.files.forEach((f, i) => {
    const on = i === ti, row = el("div", "hf-row" + (on ? " on" : "")), lab = el("label", "hf-pick"), r = el("input"), icon = el("span", "hf-file-icon"), ext = el("span", "hf-ext", hfExt(f).toUpperCase()), name = el("span", "hf-name", f.name), del = el("button", "icon hf-del", "×");
    const tag = el("span", "hf-tag", [on ? "목적 문서" : ti >= 0 ? "원본 문서" : "목적 문서로 선택", /\.hwp$/i.test(f.name) ? "hwpx 로 변환" : "", /\.docx$/i.test(f.name) ? "워크플로우 없이 열기 · 서식 복사" : ""].filter(Boolean).join(" · "));
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
    r.onchange = () => { hf.target = i; homeFilesDraw(); };
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
  plain.disabled = busy || !tgt;
  plain.dataset.hfPlain = "1";
  plain.title = tgt ? `「${tgt.name}」 을 워크플로우 없이 그냥 엽니다(편집 · 검증 — docx 도)` : "목적 문서를 먼저 고르세요";
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
  } catch (e) { toast(`${name}를 올리지 못했습니다: ${e.message} — 작업 개요의 ${name} 칸에서 다시 올리세요`, true); }
}

async function homeFilesGo(job) { // 목록이 있을 때 TASK 카드 — 그 TASK 로 시작(② §15-1 표)
  const t = TASK_CATALOG[job];
  if (!t || hf.busy || homeTaskBusy) return;
  if (t.soon) { toast(`워크플로우 「${t.name}」 — 준비 중입니다`); return; }
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
    return true; // 시작함(첫 화면 대화창이 본다 — doc_agent_work.js homeAgentAct)
  }
  catch (e) { // 문서는 열렸는데 TASK·별칭 저장에서 실패했을 수도 있다 — 시작 화면의 까닭 줄은 그때 안 보이므로 알림도
    setSaveState("err", "열지 못함");
    hfFail(main ? `워크플로우 「${t.name}」의 원본 문서를 준비하지 못했습니다: ${e.message}` : `${hfDocName(job)}를 워크플로우 「${t.name}」 ${hfJosa(t.name, "으로", "로", "로")} 열지 못했습니다: ${e.message}`);
    toast(hf.err, true);
    return !!main; // 목적 문서는 열렸다(원본 문서만 못 올림) — 시작한 것으로 본다
  } finally { homeTaskBusy = false; if (card) card.classList.remove("busy"); homeFilesDraw(); if (typeof agentWorkHold === "function") agentWorkHold(false); }
}
