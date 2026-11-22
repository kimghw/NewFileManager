"use strict";
// HWPX·DOCX 웹 편집 화면 (spec/spec_hwpx_웹편집.md ② §2~§4, docx 는 spec_docx_웹편집.md). astra UI/UX 검토(2026-11-08) 반영:
// 로컬 수정 번호(localRev)로 미저장·미검증 판정, 문서 전환 시 이전 요청 격리(epoch), 다운로드 성공 확인 뒤에만 「내려받음」.

const $ = (id) => document.getElementById(id);
const IMG_OK = new Set(["png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"]);
const ICON = { ok: "✓", warn: "!", fail: "✕", skip: "–", wait: "", run: "" };
const LS = "\u2028";
const PLAIN = (() => { const d = document.createElement("div"); d.contentEditable = "plaintext-only"; return d.contentEditable === "plaintext-only"; })();
// 옆 문서 화면(spec_작업 ② §12 「같이 보기」) — 다른 창의 옆 열(iframe)에 /?peek=<작업 id> 로 뜬 화면: 문서만 보이고(style.css body.peek) 문단을 못 고치고(renderPara) GET 밖 요청을 안 보낸다(api)
const PEEK = new URLSearchParams(location.search).has("peek");
if (PEEK) document.body.classList.add("peek");

const fresh = () => ({
  id: null, name: "", blocks: [], byId: new Map(), texts: {}, original: {}, edited: new Set(), unrestored: new Set(), pristine: true,
  mapping: null, mappingEdited: null, verify: null, unit: "쪽", selected: null,
  pdfWhich: "original", pdfPage: 1, pdfVer: 0, lastEditStarted: null,
  timers: new Map(), chains: new Map(), inflight: 0, failed: new Set(),
  localRev: 0, downloadedRev: 0, downloadedAt: null, editsDirty: true, pollError: null,
  // 구조·서식 편집(spec_owpml_편집 ② §4): 고친 문단 종류, 실행 취소 수, 처음 연 블록(되돌리기 다시 그림), 지금 편집 자리, 마지막 OWPML 판정
  kinds: {}, undo: 0, byIdOrig: new Map(), cur: null, busy: false, owpml: null, structRev: 0,
  // 작업(spec_작업 ② §7): 작업 폴더에 저장되는지, 서버 편집 차례(출력파일 검증의 rev 와 견줌), 만든 때
  stored: false, serverRev: 0, created: null, persistError: null,
  task: null, // 작업 종류·첨부 파일·할 일·과제 {kind, file, job, project}(spec_작업 ② §10)
  // 확정(spec_작업 ② §8): 기준 확정 번호(0 = 올린 원본 — 고친 문단·원래 글 state.original·byIdOrig 는 이 기준 대비), 확정 기록, 확정/복원 중,
  // 옛 기준의 쪽 매핑을 새 매핑이 올 때까지 두는 중, 검증 읽기 차례(기준이 바뀌면 옛 응답을 버림)
  base: 0, commits: null, commitBusy: false, mappingStale: false, pollSeq: 0,
});
const state = { ...fresh(), zoom: 1, fit: "width", twoUp: false, wheelFlip: true, tool: "page", epoch: 0, enterHinted: false, polling: false, compare: null };

// ---------------------------------------------------------------- 공통
async function api(url, opts = {}) {
  if (PEEK && (opts.method || "GET") !== "GET") throw new Error("같이 보기는 읽기 전용입니다"); // 옆 문서 화면은 어느 길로도 문서·작업을 안 바꾼다(② §12)
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`, body = null;
    try { body = await r.json(); msg = (typeof body.detail === "string" ? body.detail : null) || msg; } catch { /* 본문 없음 */ }
    const e = new Error(msg);
    e.status = r.status;
    e.body = body; // 422 = OWPML 거절 — body.owpml 에 위반 목록
    throw e;
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}

let toastTimer;
function toast(msg, err = false, action = null) {
  const t = $("toast");
  t.textContent = msg;
  if (action) { // 알림 안 단추 하나(예: 「새 작업으로 열기」) — 누르면 알림을 닫고 실행
    const b = el("button", "toast-act", action.label);
    b.type = "button";
    b.onclick = () => { t.hidden = true; action.run(); };
    t.append(" ", b);
  }
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), action ? 12000 : err ? 7000 : 3500);
}

const fmtSize = (n) => (n >= 2 ** 20 ? `${(n / 2 ** 20).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const oneLine = (s) => (s || "").replaceAll(LS, " ").replace(/[\n\t]/g, " ").trim();
const short = (s, n = 60) => { s = oneLine(s); return s.length > n ? s.slice(0, n) + "…" : s || "(빈 문단)"; };
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const paraEl = (id) => document.querySelector(`.para[data-id="${CSS.escape(id)}"]`);
const hhmm = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

// 문서 형식별 이름(spec_docx_웹편집 ② §5) — docx 는 한글 대신 Word 가 PDF·다시 저장을 맡고, 표준 검사는 OWPML 대신 OOXML 참조 규칙
const APP = () => (state.format === "docx" ? "Word" : "한글");
const EXT = () => (state.format === "docx" ? "DOCX" : "HWPX");
const STD = () => (state.format === "docx" ? "OOXML" : "OWPML");

// ---------------------------------------------------------------- 시작 화면
async function init() {
  try {
    const st = await api("/api/status");
    const note = $("envNote");
    note.className = "env " + (st.hangul || st.word ? "ok" : "no");
    const apps = [st.hangul && "한글", st.word && "Word"].filter(Boolean);
    note.textContent = apps.length ? `PDF 출력 확인 가능 · ${apps.join(" · ")}` + (apps.length < 2 ? ` · ${st.hangul ? "DOCX" : "HWPX"}는 PDF 검증 건너뜀` : "")
      : "PDF 출력 도구 없음 · PDF 검증은 건너뛰고 파일 왕복을 검사합니다.";
  } catch {
    $("envNote").className = "env no";
    $("envNote").textContent = "PDF 출력 환경을 확인하지 못했습니다. 연결 상태를 확인하고 새로고침해 주세요.";
  }
  try {
    const list = await api("/api/samples");
    const box = $("samples");
    box.textContent = "";
    for (const s of list) {
      const format = /\.docx$/i.test(s.name) ? "DOCX" : /\.hwpx$/i.test(s.name) ? "HWPX" : "문서";
      const b = el("button", "sample");
      b.type = "button";
      b.title = `${s.name} · ${fmtSize(s.size)}`;
      b.setAttribute("aria-label", `예제 ${s.name} 열기`);
      b.append(el("span", "sample-format", format), el("span", "sample-name", s.name.replace(/\.(hwpx|docx)$/i, "")));
      b.onclick = () => openSample(s.name);
      box.append(b);
    }
    $("sampleSection").hidden = !list.length;
  } catch (e) { toast(`예제를 불러오지 못했습니다: ${e.message}`, true); }
  await loadWorks();
  const m = location.hash.match(/^#w=([0-9a-f]{12})$/); // 주소의 작업(새로 고침·즐겨찾기)
  if (m && !state.id) {
    setSaveState("busy", "작업 여는 중…");
    try { await load(m[1]); }
    catch (e) { setSaveState("", ""); history.replaceState(null, "", location.pathname); toast(`작업을 열지 못했습니다: ${e.message}`, true); }
  }
}

function hasUnsaved() {
  if (!state.id) return false;
  if (state.timers.size || state.inflight || state.failed.size) return true;
  if (state.stored) return false; // 서버에 반영된 편집은 작업 폴더에 저장된다 — 다른 작업을 열어도 작업 목록에서 이어짐
  return !state.pristine && state.localRev !== state.downloadedRev;
}

function confirmDiscard() {
  return !hasUnsaved() || confirm(state.stored
    ? "서버에 아직 반영되지 않은 수정(반영 중·반영 실패)이 있습니다. 다른 작업을 열면 그 수정은 사라집니다. 계속할까요?"
    : "내려받지 않은 수정(또는 반영 중·반영 실패한 수정)이 있습니다. 다른 파일을 열면 사라집니다. 계속할까요?");
}

// 같은 파일(이름·형식·바이트)로 하던 작업이 있으면 — 올리기는 열기 전에 묻고(same_file.js — spec_작업 ② §1 「같은 파일은 묻고 연다」) 예제 열기는 서버가 이어 연다(reused) — 알림에서 새 작업으로 다시 열 수 있다
async function opened(r, again) {
  await load(r.docId);
  if (r.reset) { firstRun(); toast("작업 내용을 초기화했습니다 — 올린 원본부터 다시 시작합니다"); return; } // 「초기화하고 열기」(② §3-1) — 새 작업과 같이 첫 분석
  if (!r.reused) { firstRun(); return; } // 새 작업 — 첫 분석(헤딩 2·3단계 스크립트 — spec_작업 ② §9 · 구분 기준 LLM 검토는 2026-11-15 부터 저절로 안 돈다: ② §20)
  const w = r.work || {};
  const done = [w.commits ? `확정 ${w.commits}` : "", w.edited ? `고친 문단 ${w.edited}개` : ""].filter(Boolean).join(" · ");
  if (r.picked) { toast(`하던 작업을 이어서 엽니다 — ${fmtWhen(w.created)} 시작${done ? " · " + done : ""}`); return; } // 「같은 파일 고르기」 에서 골랐다 — 다시 묻지 않는다
  toast(`같은 파일로 하던 작업을 이어서 엽니다 — ${fmtWhen(w.created)} 시작${done ? " · " + done : ""}`, false,
    { label: "새 작업으로 열기", run: again });
}

async function openFile(file, fresh = false) {
  if (!file) return;
  if (!/\.(hwpx?|docx)$/i.test(file.name)) { toast("hwp·hwpx·docx 파일만 열 수 있습니다", true); return; } // hwp 는 서버가 한글로 hwpx 로 바꿔 받는다
  if (!confirmDiscard()) return;
  setSaveState("busy", `${file.name} 여는 중…`);
  try {
    if (fresh) { const fd = new FormData(); fd.append("file", file); await opened(await api("/api/docs?new=1", { method: "POST", body: fd })); return; }
    const got = await sameFileUpload(file); // 같은 파일로 하던 작업이 있으면 묻는다(TASK 없이 — 줄은 모두 「이어서」 · 「초기화하고 열기」)
    if (!got) { refreshSaveState(); return; } // 창을 닫음 — 아무것도 열지 않는다
    await opened(got.r, () => openFile(file, true));
  } catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); }
}

async function openSample(name, fresh = false) {
  if (!confirmDiscard()) return;
  setSaveState("busy", `${name} 여는 중…`);
  try { await opened(await api(`/api/samples/${encodeURIComponent(name)}${fresh ? "?new=1" : ""}`, { method: "POST" }), () => openSample(name, true)); }
  catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); }
}

// ---- 시작 화면의 TASK 카드(spec_작업 ② §15, 2026-11-12 사용자 "여기에 할 일 : TASK 라고 하자 TASK 를 카드로 줘라 그리고 각 task 아이콘/로고를 만들어줘")
// TASK = 할 일(task.job — ② §10). 카드 한 장 = 그 TASK 로 문서를 올려 시작: 누르면 파일 고르기(카드에 파일을 놓아도 됨) → 올린 작업에 작업 종류 연구개발과제 + 그 할 일을 적고 작업 개요(#paneDiv)을 연다.
// 이름·차례·문서 조합의 원본은 task_catalog.js TASK_CATALOG — act 동작 낱말(이름의 끝 — 카드는 「문서 / 동작」 두 줄) · doc 로고 바탕색(landing.css .task-logo[data-doc]) ·
// file 양식 판정이 종류를 못 정했을 때 그 문서의 첨부 파일 종류("" = 안 정함) · up 처음 올릴 문서 · soon 아직 없는 기능(카드는 보이되 시작하지 않는다). 로고 그림은 index.html <symbol id="taskIcon-<키>">
const HOME_TASKS = TASK_CATALOG; // 카드와 문서 조합이 같은 정의를 읽는다.
let homeTaskBusy = false; // 카드로 올리는 중 — 그동안 다른 카드는 받지 않는다

function homeTasksDraw() { // 한 번(bind) — WORK_TASK.job 차례(= 일의 흐름)대로 카드 한 장씩
  const ul = $("taskCards"), files = (e) => !!e.dataTransfer && [...e.dataTransfer.types].includes("Files");
  ul.textContent = "";
  for (const [key, name] of WORK_TASK.job) {
    const t = HOME_TASKS[key];
    if (!t) continue;
    const li = el("li"), b = el("button", "task-card"), logo = el("span", "task-logo"), go = el("span", "task-card-go", t.soon ? "준비 중" : `${t.upMany || t.up} 올려 시작 `); // upMany = 여러 개를 올리는 TASK(취합 간단 모드 — spec_취합 ② §8-1)
    const doc = name.endsWith(t.act) ? name.slice(0, -t.act.length).trim() : ""; // 「사업계획서 양식 표준화」 → 「사업계획서」 + 「양식 표준화」 — 이름이 그 꼴이 아니면 이름 한 줄
    b.type = "button";
    b.dataset.task = key;
    logo.dataset.doc = t.doc;
    logo.setAttribute("aria-hidden", "true");
    logo.innerHTML = `<svg viewBox="0 0 32 32" width="30" height="30" focusable="false"><use href="#taskIcon-${(TASK_CATALOG[key] || {}).icon || key}"/></svg>`;
    if (!t.soon) { const arrow = el("span", null, "→"); arrow.setAttribute("aria-hidden", "true"); go.append(arrow); }
    b.append(logo, el("span", "task-card-doc", doc), el("strong", "task-card-name", doc ? t.act : name), go);
    if (t.soon) b.setAttribute("aria-disabled", "true");
    b.title = t.soon ? `워크플로우 「${name}」 — 준비 중인 기능입니다`
      : `워크플로우 「${name}」 — ${t.quick ? "문서를 여러 개" : t.up}(${taskAcceptOf(key).join("·")}) 올려 시작 · 파일을 이 카드에 놓아도 됩니다${t.hint ? "\n" + t.hint : ""}`; // 받는 확장자 = task_catalog.js accept(없으면 hwp·hwpx)
    // 시작 화면의 문서 목록(home_files.js — ② §15-1)이 있으면 카드 = 그 목록으로 시작, 없으면 전처럼 파일 고르기
    b.onclick = () => (t.soon ? toast(`워크플로우 「${name}」 — 준비 중입니다`) : typeof hfHas === "function" && hfHas() ? homeFilesGo(key) : homeTaskPick(key));
    // 카드에 놓은 파일은 그 TASK 로 연다 — 창의 파일 놓기(bind — 그냥 열기)보다 먼저 받는다
    b.addEventListener("dragover", (e) => { if (!files(e)) return; e.preventDefault(); e.stopPropagation(); $("drop").classList.remove("over"); if (t.soon) e.dataTransfer.dropEffect = "none"; else b.classList.add("over"); });
    b.addEventListener("dragleave", (e) => { if (!b.contains(e.relatedTarget)) b.classList.remove("over"); });
    b.addEventListener("drop", (e) => { if (!files(e)) return; e.preventDefault(); e.stopPropagation(); b.classList.remove("over"); if (!t.soon) homeTaskFiles(key, e.dataTransfer.files); });
    const note = hHelp(`${name} 안내`, t.desc + (t.hint ? "\n" + t.hint : ""), { note: true });
    note.classList.add("task-card-help"); // 카드(button) 안에 또 button을 넣지 않는다.
    li.append(b, note);
    ul.append(li);
  }
}

function homeTaskPick(job) { // 카드 누름 — 그 TASK 로 열 파일을 고른다(보통 hwp·hwpx — 첨부 파일 칸의 올리기 단추와 같은 형식 · 「문서 서식 복사」 는 docx·pdf 도: task_catalog.js taskAcceptOf)
  const inp = el("input");
  inp.type = "file";
  inp.accept = taskAcceptOf(job).map((x) => `.${x}`).join(",");
  inp.multiple = true; // 여러 개면 시작 화면의 문서 목록으로(목적 문서를 고른 뒤 카드를 다시 누름 — ② §15-1), 하나면 지금처럼 바로
  inp.onchange = () => homeTaskFiles(job, inp.files);
  inp.click();
}

function homeTaskFiles(job, files) { // 카드로 고르거나 놓은 파일들 — 목록이 이미 있거나 둘 이상이면 시작 화면의 문서 목록에 더함(home_files.js), 아니면 그 파일로 바로 시작
  const list = [...(files || [])];
  // PDF 하나(「문서 서식 복사」 카드 — spec_서식복사 ② §1)는 문서 목록이 있어도 목록에 넣지 않고 바로: 작업을 만들지 않고 서식 관리자의 파일 후보로 간다
  if (list.length === 1 && /\.pdf$/i.test(list[0].name) && taskAcceptOf(job).includes("pdf")) { homeTaskStart(job, list[0]); return; }
  if (typeof homeFilesAdd === "function" && (hfHas() || list.length > 1)) homeFilesAdd(list, job);
  else homeTaskStart(job, list[0]);
}

async function homeTaskStart(job, file, fresh = false) { // 올림(같은 파일로 하던 작업이 있으면 「같은 파일 고르기」 로 묻는다 — same_file.js) → 그 TASK 로 적음 → 첫 분석 → 작업 개요
  const t = HOME_TASKS[job];
  if (!file || !t || t.soon || homeTaskBusy) return;
  const accept = taskAcceptOf(job), ext = ((file.name.match(/\.(\w+)$/) || [])[1] || "").toLowerCase(); // 받는 확장자 = task_catalog.js accept(없으면 hwp·hwpx — hwp 는 서버가 한글로 hwpx 로 바꿔 받는다)
  if (!accept.includes(ext)) { toast(`워크플로우는 ${accept.join("·")} 문서로 시작합니다`, true); return; }
  if (ext === "pdf") { // 작업을 만들지 않는다(spec_서식복사 ② §1) — 서식 관리자의 파일 추출: 시작 화면 옆 2열에 「서식 복사」 보기(style_lib.js styleFileExtract)
    if (typeof styleFileExtract === "function") styleFileExtract(file); else toast("서식 관리자를 읽지 못했습니다 — 새로 고친 뒤 다시 놓으세요", true);
    return;
  }
  if (!confirmDiscard()) return;
  const fd = new FormData(), card = document.querySelector(`#taskCards [data-task="${job}"]`);
  fd.append("file", file);
  homeTaskBusy = true;
  if (card) card.classList.add("busy");
  setSaveState("busy", `${file.name} 여는 중…`);
  try {
    // 같은 파일로 하던 작업이 있으면 묻는다(same_file.js — ② §1 「같은 파일은 묻고 연다」, 2026-11-18 사용자): 줄 차례 = 그 TASK 의 작업 → TASK 가 빈 작업 → 그 밖(?job=).
    // 다른 TASK 를 하던 작업은 「그대로 열기」 만 — 그 작업의 TASK 를 바꾸지 않는다(② §15 · §19, 2026-11-13 사용자 "사업 계획서 양식 맞추기 했는데 task 에서는 이관 으로 되어 있음").
    // 전(11-13~11-17)에는 그런 작업이면 묻지 않고 새 작업으로 열었다 — 이제 새 작업은 창의 「새 작업으로 시작」 으로.
    const got = fresh ? { act: "new", r: await api("/api/docs?new=1", { method: "POST", body: fd }), project: "" }
      : await sameFileUpload(file, { job, fit: (w) => (!(w.task || {}).job || w.task.job === job ? true : `다른 워크플로우(「${taskName("job", w.task.job) || w.task.job}」)`) });
    if (!got) { refreshSaveState(); return; } // 창을 닫음 — 아무것도 열지 않는다
    if (got.act === "open") { // 「그대로 열기」 — 그 작업을 그 TASK 그대로 연다
      await (typeof projectOpen === "function" ? projectOpen(got.id) : openWork(got.id));
      toast("하던 작업을 그 워크플로우 그대로 엽니다 — 이 워크플로우로 시작하려면 다시 올려 「새 작업으로 시작」 을 고르세요");
      return;
    }
    const r = got.r;
    await load(r.docId);
    let kept = true;
    homeTaskTemp = "";
    if (got.act === "new" && got.project && state.stored) { // 창의 프로젝트 칸 — 그 프로젝트의 이 TASK 다음 라운드(② §17 start-task)
      const role = (state.task && state.task.file) || t.file || "";
      const res = await api(`/api/works/${r.docId}/start-task`, { method: "POST", headers: H_JSON, body: JSON.stringify({ project: got.project, job, file: role }) });
      if (state.id === r.docId) { state.task = res.task; taskDraw(); await loadWorks(); }
    } else kept = await homeTaskApply(job);
    if (state.id !== r.docId) return; // 그 사이 다른 문서를 열었다
    if (!r.reused) firstRun(); // 새 작업 · 초기화한 작업 — 첫 분석(② §9)
    taskEnter(kept ? job : state.task.job); // 그 TASK 가 처음 여는 보기(task_catalog.js entry — 보통 작업 개요 · 문서 일반 편집은 에이전트 · 문서 서식 복사는 2열 「서식 복사」)
    const temp = kept && homeTaskTemp ? `\n프로젝트 이름이 없어 임시 이름 「${homeTaskTemp}」 로 묶었습니다 — 「작업 개요」 의 프로젝트 칸(또는 작업 리스트의 「이름 정하기」)에 이름을 적으면 바뀝니다` : ""; // ② §17 「임시 프로젝트」
    const named = taskProject();
    if (!kept) toast(`이 문서는 하던 작업입니다(워크플로우 「${taskName("job", state.task.job)}」) — 워크플로우를 바꾸지 않고 이어서 엽니다`); // 작업 목록이 낡아 TASK 를 미리 못 본 때만 남는 길
    else if (got.act === "reset") toast(`작업 내용을 초기화했습니다 — 워크플로우 「${taskName("job", job)}」 ${typeof taskJosa === "function" ? taskJosa(taskName("job", job), "을", "를") : "를"} 올린 원본부터 다시 시작합니다${temp}`);
    else if (got.act === "use") toast(`같은 파일로 하던 작업을 이어서 엽니다 — 워크플로우 「${taskName("job", job)}」${temp}`);
    else if (got.act === "new") toast(`같은 파일로 하던 작업은 그대로 두고 새 작업으로 열었습니다 — 워크플로우 「${taskName("job", job)}」 · ${named ? `프로젝트 「${named}」` : "프로젝트 미지정"}${temp}`);
    else if (temp) toast(temp.trim());
  } catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); }
  finally { homeTaskBusy = false; if (card) card.classList.remove("busy"); }
}

// 방금 연 작업에 그 TASK 를 적는다(작업 종류 = 연구개발과제 · 할 일 = job · 첨부 파일 = 양식 판정이 정한 것, 없으면 그 TASK 의 문서) → 적었나.
// false = 이어 연 작업에 다른 TASK 가 이미 있다 — 바꾸지 않는다(하던 작업의 TASK 는 그 작업 것이다). 2026-11-13 부터 homeTaskStart 가 그런 작업은 미리 새 작업으로 올리므로(② §15) 여기까지 오는 것은 작업 목록을 못 읽었을 때뿐
let homeTaskTemp = ""; // 마지막 homeTaskApply 가 붙인 임시 프로젝트 이름(알림 — homeTaskStart) · 없으면 ""
async function homeTaskApply(job) {
  const id = state.id, epoch = state.epoch, cur = { kind: "", file: "", job: "", project: "", ...state.task };
  homeTaskTemp = "";
  if (cur.job && cur.job !== job) return false;
  state.task = { ...cur, kind: taskKindOf(job), job, file: cur.file || HOME_TASKS[job].file }; // 작업 종류는 TASK 가 정한다(task_catalog.js kind — 서버 TASK_KIND 와 같게)
  taskDraw();
  if (!state.stored) return true; // 작업 저장이 꺼져 있으면 이 화면에서만(taskSet 과 같다)
  try {
    let r = null;
    if (!cur.project) { // 이름 없이 TASK 를 시작 — 서버가 임시 이름(「임시 프로젝트 N」 — spec_작업 ② §17 「임시 프로젝트」, 2026-11-18: 전에는 프로젝트 없이). 새로 올린 문서가 아닌 작업이면(409) 전처럼 프로젝트 없이
      try {
        r = await api(`/api/works/${id}/start-task`, { method: "POST", headers: H_JSON, body: JSON.stringify({ project: "", temp: true, job, file: state.task.file }) });
        if (r.temp) homeTaskTemp = (r.task || {}).project || "";
      } catch (e) { if (e.status !== 409) throw e; }
    }
    if (!r) r = await api(`/api/works/${id}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify(state.task) });
    if (epoch !== state.epoch) return true;
    state.task = r.task;
    taskDraw();
    await loadWorks();
  } catch (e) { toast(`워크플로우를 저장하지 못했습니다: ${e.message}`, true); }
  return true;
}

async function load(id) {
  const d = await api(`/api/docs/${id}`);
  for (const t of state.timers.values()) clearTimeout(t); // 이전 문서의 대기 중 반영은 버린다(epoch 로 응답도 무시)
  state.epoch += 1;
  Object.assign(state, fresh(), { id, name: d.name, blocks: d.blocks, edited: new Set(d.edited), unrestored: new Set(d.unrestored || []), pristine: d.pristine,
    kinds: d.kinds || {}, undo: d.undo || 0, owpml: d.owpml || null, format: d.format || "hwpx",
    stored: !!(d.work && d.work.stored), serverRev: d.rev || 0, created: d.work ? d.work.created : null, persistError: d.persistError || null,
    task: (d.work && d.work.task) || { kind: "rnd", file: "", job: "", project: "" }, // 옛 서버(task 없음)면 전처럼 구분 기준(연구개발과제 내용)을 열 수 있게
    base: d.base || 0 });
  history.replaceState(null, "", `#w=${id}`); // 새로 고치거나 주소를 다시 열어도 이 작업(spec_작업 ② §7)
  $("downloadBtn").textContent = `${EXT()} 저장`;
  $("downloadBtn").title = `${EXT()} 로 내려받기 (Ctrl+S)`;
  $("verifyBtn").title = `저장본을 ${APP()} PDF 로 찍어 원본과 쪽마다 비교`;
  setDocFonts(d.webFonts);
  // byIdOrig = 기준 그대로인 블록만(되돌리기가 이걸로 다시 그림) — 다시 연 작업에서 이미 고친 문단의 블록은 기준이 아니다
  walkParas(d.blocks, (b) => { state.texts[b.id] = b.text || ""; state.original[b.id] = b.text || ""; state.byId.set(b.id, b); if (!state.edited.has(b.id)) state.byIdOrig.set(b.id, b); });
  Object.assign(state.original, d.original || {});
  refreshToolbar();
  $("fileName").textContent = d.name;
  $("fileName").title = d.name;
  $("fileMeta").textContent = fmtSize(d.size) + (state.stored && state.created ? ` · 작업 ${fmtWhen(state.created)}` : "");
  $("fileMeta").title = state.stored ? "편집·검증 기록이 이 작업에 저장됩니다 — 「기록」 탭" : "작업 저장이 꺼져 있어 서버를 끄면 사라집니다";
  $("docSwitch").hidden = true; $("fileName").hidden = false; // 문서 목록은 loadWorks 가 다시 채운다(spec_작업 ② §10) — 그때까지 이름만
  taskDraw(); // 작업 종류 · 패널 머리 탭 「작업 개요」
  $("logOriginal").href = `/api/works/${id}/file/original`;
  $("tabLog").hidden = !state.stored;
  $("fileInfo").hidden = $("barCtl").hidden = false; // 상단 바 가운데 줄 접기·바꾸기 묶음도 문서가 있을 때만
  $("workspaceNav").hidden = false;
  $("empty").hidden = true;
  document.body.classList.remove("no-doc"); // 시작 화면 상단 바 모양(landing.css `body.no-doc …`)을 걷는다 — #empty 를 감추는 곳과 늘 함께(index.html <body> 주석)
  $("docBar").hidden = $("scroller").hidden = $("panel").hidden = false;
  $("downloadBtn").disabled = false;
  $("importSteps").textContent = "";
  $("editSteps").textContent = "";
  renderDoc(d.blocks);
  updateEdits();
  setPanel(window.innerWidth > 820);
  if (!state.fit) state.fit = "width"; // 고른 맞춤(폭·높이·여백 빼고)은 다음 문서에도 — 손으로 정한 배율이면 폭 맞춤으로
  refit();
  $("scroller").scrollTop = 0;
  if (PEEK) { try { parent.peerViewSync(); } catch { /* 바깥이 아직 준비 전 */ } } // 둘째 면 화면: 문서를 다 그렸다 — 바깥(첫째 면)의 보기를 따른다(spec_작업 ② §12 「두 면」)
  headsReset();
  divReset();
  if (typeof tablesReset === "function") tablesReset(); // 표 탭(tables.js)
  if (typeof compareReset === "function") compareReset();
  if (typeof agentReset === "function") agentReset(); // 에이전트 보기(doc_agent.js — spec_일반편집 ② §12)
  const agentFirst = !PEEK && taskGeneral() && toolShown("Agent");
  showTab(agentFirst && !agentFloatOn() ? "Agent" : "Verify"); // 「일반 문서」 작업은 에이전트 보기부터(② §12) — 그 밖에는 검증
  if (agentFirst && agentFloatOn()) showTab("Agent"); // 에이전트가 떠 있는 창 자리면 패널은 검증 · 에이전트는 그 창에(agent_float.js)
  colFold("panel", colFoldLoad("panel"), false); // » 로 접어 둔 3열은 새 문서도 접힌 채(기억한 대로 — 도구 탭을 고르면 펴짐)
  renderVerify({});
  poll();
  loadWorks();
  outlineLoad();
  commitsLoad(); // 확정 기록(spec_작업 ② §8)
  headsPeek(); // 헤딩 요약을 읽기만(GET — 추출을 시작하지 않는다): 뼈대 유지 견주기 · 도는 작업 이어 읽기(spec_헤딩_추출 ② §17)
  // TASK 「문서 서식 복사」 의 작업을 다시 열면 2열에 「서식 복사」 보기(spec_서식복사 ② §1 — 둘째 면은 아님). 새 작업은 TASK 를 적은 뒤 taskEnter 가 연다(여기서는 아직 TASK 가 비어 있다)
  if (!PEEK && taskEntryOf((state.task || {}).job) === "Style" && typeof styleSaveOpen === "function") styleSaveOpen();
}

// ---------------------------------------------------------------- 작업 목록·기록 (spec_작업 ② §7)
const fmtWhen = (t) => {
  if (!t) return "";
  const d = new Date(t * 1000);
  return (d.toDateString() === new Date().toDateString() ? "오늘" : `${d.getMonth() + 1}/${d.getDate()}`) + " " + hhmm(d);
};
const VSTAT = { ok: "통과", warn: "주의", fail: "실패", run: "진행 중", skip: "건너뜀" };
const VKIND = { import: "가져오기", edit: "출력파일" };

function verifyTag(kind, v) {
  const label = VKIND[kind] || kind;
  const s = el("span", `vtag ${v ? v.status : "none"}`, `${label} ${v ? VSTAT[v.status] || v.status : "—"}`);
  s.title = v ? `${label} 검증 ${VSTAT[v.status] || v.status}${v.at ? " · " + fmtWhen(v.at) : ""}` : `${label} 검증 기록 없음`;
  return s;
}

async function loadWorks() {
  let list = [];
  try { list = await api("/api/works"); }
  catch {
    const ul = $("workList"), error = ul.querySelector(".recent-work-error") || el("li", "recent-work-error");
    error.textContent = "최근 작업을 불러오지 못했습니다. ";
    error.setAttribute("role", "status");
    const retry = el("button", "btn sm", "다시 시도");
    retry.type = "button";
    retry.onclick = loadWorks;
    error.append(retry);
    ul.append(error);
    $("recent").hidden = false;
    return; // 연결 오류는 빈 작업 목록이 아니다. 이미 표시한 작업은 그대로 둔다.
  }
  const rows = recentRows(list); // 최근 작업 = TASK 하나가 한 줄(② §7) — 전체 작업 보기는 파일 하나가 한 줄 그대로
  recentShown = rows.slice(0, 4);
  renderRecentWorks($("workList"), recentShown);
  renderWorks($("workListDlg"), list);
  docSwitchDraw(list); // 상단 바 「다른 문서」(② §10)
  if (typeof projectListDraw === "function") projectListDraw();
  $("recent").hidden = !list.length;
  $("recentCount").textContent = rows.length === list.length ? `전체 ${list.length}개` : `전체 ${rows.length}개 · 문서 ${list.length}개`;
}

// 작업 줄의 「무슨 일의 어느 작업」(spec_작업 ② §7, 2026-11-12 사용자 "이관이냐 취합이냐. 그리고 작업이름이 뭐냐 이런게 있어야지") — GET /api/works 의 task 를 읽기만.
// TASK = 할 일(task.job — 작업 종류가 연구개발과제일 때만: kind 를 비워도 job 은 남는다 ② §10) · 작업 이름 = 과제 이름(project) · 역할 = 이 문서의 첨부 파일 종류(취합이면 취합본 · 기관 문서)
function workTaskInfo(w) {
  const t = w.task || {}, cat = (t.kind && t.kind === taskKindOf(t.job) && TASK_CATALOG[t.job]) || null, g = cat && cat.gather; // 작업 종류가 그 TASK 의 것일 때만(연구개발 프로젝트의 TASK · 일반 문서의 「문서 일반 편집」)
  const role = !t.file ? "" : g && t.file === g.base ? "취합본" : taskName("file", t.file);
  const what = cat ? `${t.project ? `프로젝트 「${t.project}」` : "프로젝트 미지정"} · 워크플로우 「${cat.name}」 · Round ${taskRound(t)}${role ? ` · ${role}` : ""}` : "워크플로우 없음";
  return { job: cat ? t.job : "", name: cat ? cat.name : "", doc: cat ? cat.doc : "", project: (cat && t.project) || "", role, what };
}
function taskLogoEl(key, doc) { // TASK 로고(시작 화면 카드와 같은 그림·색 — design.md §12)
  const logo = el("span", "task-logo");
  logo.dataset.doc = doc;
  logo.setAttribute("aria-hidden", "true");
  logo.innerHTML = `<svg viewBox="0 0 32 32" width="30" height="30" focusable="false"><use href="#taskIcon-${(TASK_CATALOG[key] || {}).icon || key}"/></svg>`;
  return logo;
}
function taskChipEl(T) { // TASK 이름 표지 — 글자·바탕은 로고와 같은 문서 색, TASK 가 없으면 흐린 「TASK 없음」
  const c = el("span", "recent-task" + (T.job ? "" : " none"), T.job ? T.name : "워크플로우 없음");
  if (T.job) c.dataset.doc = T.doc;
  return c;
}

// 최근 작업의 줄(spec_작업 ② §7, 2026-11-13 사용자 "동일한 프로젝트에서 동일한 task 인데 왜 동일한게 있냐.. 여긴 task 별로 나와야지") — (프로젝트, TASK) 하나가 한 줄,
// 그 TASK 의 최신 라운드 문서들만(이전 라운드는 작업 리스트 · 전체 작업 보기에서). 프로젝트 이름이 없거나 TASK 가 없는 작업은 전처럼 파일 하나가 한 줄(서로 관계없는 작업 — /api/projects 도 안 묶는다).
// docs[0] = 가장 늦게 바뀐 문서 = 줄을 누르면 여는 문서(대표 문서가 아니라 하던 문서 — 사용자 2026-11-13 「진행」).
function recentRows(list) {
  const groups = new Map(), rows = [];
  for (const w of list) {
    const T = workTaskInfo(w), round = taskRound(w.task || {});
    if (!T.job || !T.project) { rows.push({ round, docs: [w] }); continue; }
    const key = JSON.stringify([T.project, T.job]);
    let g = groups.get(key);
    if (!g) { g = { round, docs: [] }; groups.set(key, g); rows.push(g); }
    if (round > g.round) { g.round = round; g.docs = []; }
    if (round === g.round) g.docs.push(w);
  }
  for (const r of rows) {
    r.docs.sort((a, b) => (b.updated || 0) - (a.updated || 0));
    r.updated = r.docs[0].updated || 0;
  }
  return rows.sort((a, b) => b.updated - a.updated);
}

// 문서 하나의 검증 표지 + 나쁜 순위(묶음 줄은 종류마다 가장 나쁜 것 하나만 보인다 — 실패가 통과에 가리지 않게)
function recentVerifyTag(w, kind) {
  const v = (w.verify || {})[kind];
  if (!v || !v.status) return null;
  const tag = verifyTag(kind, v);
  let rank = v.status === "fail" ? 3 : v.status === "warn" ? 2 : 1;
  if (kind === "edit" && (v.rev == null || v.rev !== w.rev)) {
    tag.textContent = v.rev == null ? "출력파일 기록 확인" : "출력파일 재검증 필요";
    tag.className = `vtag ${v.rev == null ? "none" : "warn"}`;
    tag.title += v.rev == null ? " · 현재 편집본과 같은지 기록에서 확인하세요." : " · 이 검증 뒤에 문서가 수정되었습니다.";
    rank = v.rev == null ? 0 : 2;
  }
  return { tag, rank };
}

function renderRecentWorks(ul, rows) {
  ul.textContent = "";
  for (const r of rows) {
    const docs = r.docs, w = docs[0], many = docs.length > 1, T = workTaskInfo(w); // w = 누르면 여는 문서
    const format = (w.format || "").toLowerCase(), sum = (k) => docs.reduce((n, d) => n + (d[k] || 0), 0);
    const li = el("li", "recent-work" + (many ? " recent-group" : "") + (docs.some((d) => d.id === state.id) ? " current" : "")); // 「group」 은 안 됨 — style.css 의 전역 .group(flex)
    li.dataset.works = docs.map((d) => d.id).join(" "); // 이 줄에 든 작업 id 들 — 화면 검사가 [data-works~='<id>'] 로 찾는다
    const open = el("button", "recent-work-open"), icon = T.job ? taskLogoEl(T.job, T.doc) : el("span", `recent-file-icon ${format === "docx" ? "docx" : "hwpx"}`, format.toUpperCase() || "문서");
    const note = many ? `이 워크플로우의 문서 ${docs.length}개 중 마지막에 고친 문서` : "";
    open.type = "button";
    open.title = `${T.what}\n${many ? note + "\n" : ""}${w.name} · 작업 ${w.id}`; // 끝 「작업 <id>」 = 이 줄을 누르면 여는 문서 — 화면 검사가 이것으로 찾는다
    open.setAttribute("aria-label", `${T.what} · ${many ? note + " · " : ""}${w.name} · ${fmtWhen(w.created)} 시작 · 작업 ${w.id} 이어서 열기`);
    icon.setAttribute("aria-hidden", "true");
    const main = el("span", "recent-work-main"), head = el("span", "recent-work-head");
    // 첫 줄 = 프로젝트 이름 + TASK 표지(+ Round 2 부터 Round 표지) · 둘째 줄 = 누르면 여는 문서의 역할 + 파일 이름 · 셋째 줄 = 형식·크기(묶음이면 문서 수)·때 + 검증 표지.
    // TASK 가 없으면 첫 줄이 파일 이름(둘째 줄 없음). 문서가 여럿이면 줄 아래에 나머지 문서로 바로 가는 단추(넷째 줄 — 단추 안에 단추를 둘 수 없어 따로).
    head.append(el("span", "recent-work-title" + (T.job && !T.project ? " none" : ""), T.job ? T.project || "프로젝트 이름 없음" : w.name), taskChipEl(T));
    if (T.job && r.round > 1) head.append(el("span", "recent-work-round", `Round ${r.round}`));
    main.append(head);
    if (T.job) {
      const file = el("span", "recent-work-file");
      if (T.role) file.append(el("span", "recent-work-role", T.role));
      file.append(el("span", "recent-work-name", w.name));
      main.append(file);
    }
    const foot = el("span", "recent-work-foot"), tags = el("span", "recent-work-status");
    const commits = sum("commits"), edited = sum("edited"), first = docs.reduce((m, d) => (d.created && (!m.created || d.created < m.created) ? d : m), w);
    foot.append(el("span", "recent-work-meta",
      `${many ? `문서 ${docs.length}개` : `${format.toUpperCase() || "문서"} · ${fmtSize(w.size || 0)}`} · 시작 ${fmtWhen(first.created)} · ${commits ? `확정 ${commits} · ` : ""}${edited ? `고친 문단 ${edited}개` : `편집 ${sum("rev")}회`}`), tags);
    main.append(foot);
    for (const kind of ["import", "edit"]) {
      const found = docs.map((d) => ({ d, t: recentVerifyTag(d, kind) })).filter((x) => x.t);
      if (!found.length) continue;
      const worst = Math.max(...found.map((x) => x.t.rank)), same = found.filter((x) => x.t.rank === worst), tag = same[0].t.tag;
      if (many) {
        tag.textContent += ` · 문서 ${same.length}/${docs.length}`;
        tag.title = `문서 ${docs.length}개 중 ${same.length}개(가장 나쁜 상태를 보입니다)\n${same.map((x) => `· ${x.d.name}`).join("\n")}`;
      }
      tags.append(tag);
    }
    if (!tags.childElementCount) tags.append(el("span", "vtag none", "검증 전"));
    const end = el("span", "recent-work-end"), time = el("span", "recent-work-time", fmtWhen(w.updated));
    time.title = `마지막 작업 ${fmtWhen(w.updated)}`;
    end.append(time, el("span", "recent-work-arrow", "이어서 열기 →"));
    open.append(icon, main, end);
    open.onclick = () => openWork(w.id);
    // 줄 끝 × = 이 줄에 든 문서 지우기(② §7 「작업 지우기」) — 단추 안에 단추를 둘 수 없어 여는 단추 위에 겹쳐 놓는다(.recent-work-row). 누르면 줄 아래 확인 줄(창 없음)
    const key = li.dataset.works, dropOn = !!recentDrop && recentDrop.key === key, row = el("div", "recent-work-row"), del = el("button", "icon recent-work-del", "×");
    del.type = "button";
    del.title = many ? `이 워크플로우의 문서 ${docs.length}개 지우기` : "이 작업 지우기";
    del.setAttribute("aria-label", `${T.job && T.project ? `${T.project} · ${T.name}${many ? ` · 문서 ${docs.length}개` : ""}` : w.name} 지우기`);
    del.setAttribute("aria-expanded", String(dropOn));
    del.disabled = !!recentDrop && recentDrop.busy;
    del.onclick = () => recentDropSet(dropOn ? "" : key, dropOn ? "del" : "cancel");
    row.append(open, del);
    li.append(row);
    if (many) {
      const more = el("div", "recent-work-docs");
      more.append(el("span", "recent-work-docs-label", "다른 문서"));
      for (const d of docs.slice(1, 4)) {
        const D = workTaskInfo(d), b = el("button", "recent-work-doc");
        b.type = "button";
        b.title = `${D.what}\n${d.name} · 작업 ${d.id}`;
        b.setAttribute("aria-label", `${D.role || "역할 없음"} · ${d.name} · 작업 ${d.id} 열기`);
        if (D.role) b.append(el("span", "recent-work-role", D.role));
        b.append(el("span", "recent-work-name", d.name));
        b.onclick = () => openWork(d.id);
        more.append(b);
      }
      if (docs.length > 4) more.append(el("span", "recent-work-more", `외 ${docs.length - 4}개 — 전체 작업 보기에서`));
      li.append(more);
    }
    if (dropOn) { li.classList.add("dropping"); li.append(recentDropEl(r)); }
    ul.append(li);
  }
}

// ---- 작업 지우기(spec_작업 ② §7 「작업 지우기」, 2026-11-16 사용자 "작업 삭제 기능이 없네.") — 시작 화면 최근 작업 줄 · 작업 리스트의 TASK 줄·문서 줄(project_workspace.js)이 같이 쓰는 몸통.
// 확인은 부르는 쪽이 줄 아래 인라인 확인 줄로 받는다(창 없음 — 작업 목록 창의 × 만 전처럼 브라우저 확인 창: deleteWork). 서버는 문서마다 DELETE /api/works/{id}.
const DROP_WARN = "올린 원본·편집 상태·검증 기록이 모두 지워지고 되살릴 수 없습니다";
function worksDropText(docs, what) { // 확인 줄의 글 — 문서 하나면 그 이름, 여럿이면 「<무엇> 의 문서 N개」
  return docs.length === 1 ? `문서 「${docs[0].name}」을(를) 지울까요? ${DROP_WARN}` : `${what} 의 문서 ${docs.length}개를 지울까요? ${DROP_WARN}`;
}
function worksDropNames(docs) { // 여럿일 때 지울 문서 이름(5개까지 · 넘으면 「외 n개」) — 하나면 null(글에 이름이 있다)
  if (docs.length < 2) return null;
  const ul = el("ul", "work-drop-names");
  for (const d of docs.slice(0, 5)) ul.append(el("li", null, d.name));
  if (docs.length > 5) ul.append(el("li", "more", `외 ${docs.length - 5}개`));
  return ul;
}
function worksOlderRounds(docs) { // 그 문서들과 같은 프로젝트 · TASK 의 더 낮은 라운드 수 — 이름 없는 작업은 서로 관계없으므로 0
  const t = docs[0].task || {};
  if (!t.project || !t.job) return 0;
  return new Set(worksList.filter((w) => w.task && w.task.project === t.project && w.task.job === t.job && taskRound(w.task) < taskRound(t)).map((w) => taskRound(w.task))).size;
}
function worksDropNotes(docs, round) { // 확인 줄에 덧붙이는 글 — round = 그 라운드를 통째로 지우는가(이전 라운드가 남는다는 글은 그때만)
  const notes = [], older = round ? worksOlderRounds(docs) : 0;
  if (state.id && docs.some((d) => d.id === state.id)) notes.push("지금 연 문서가 들어 있어 시작 화면으로 돌아갑니다");
  if (older) notes.push(`이전 라운드 ${older}개는 남습니다`);
  return notes.join(" · ");
}
// 지금 연 문서는 맨 뒤에(중간에 실패해도 화면이 남게) · 이미 없는 작업(404)은 지운 것으로 → {done: [지운 id], fail: {id, message} | null}. 지금 문서를 지웠으면 화면을 닫는다
async function worksDelete(ids) {
  const order = [...ids].sort((a, b) => (a === state.id) - (b === state.id)), done = [];
  let fail = null;
  for (const id of order) {
    try { await api(`/api/works/${id}`, { method: "DELETE" }); done.push(id); }
    catch (e) { if (e.status === 404) done.push(id); else { fail = { id, message: e.message }; break; } }
  }
  if (state.id && done.includes(state.id)) closeDoc();
  return { done, fail };
}
function worksDropToast(docs, result, what) { // 지운 뒤 알림 — 다 지웠나 · 몇 개만 지웠나(지운 것은 되돌리지 못한다)
  const n = docs.length, m = result.done.length, name = (id) => (docs.find((d) => d.id === id) || {}).name || id;
  if (!result.fail) toast(n === 1 ? `문서 「${docs[0].name}」을(를) 지웠습니다` : `${what} 의 문서 ${n}개를 지웠습니다`);
  else if (n === 1) toast(`문서 「${docs[0].name}」을(를) 지우지 못했습니다: ${result.fail.message}`, true);
  else toast(`문서 ${n}개 가운데 ${m}개만 지웠습니다 — 「${name(result.fail.id)}」: ${result.fail.message}`, true);
}

let recentShown = [], recentDrop = null; // 최근 작업에 그린 줄(다시 그릴 때 쓴다) · 지우기 확인 줄을 편 줄 하나: {key: 그 줄에 든 작업 id 들(li.dataset.works), busy}
function recentDropSet(key, focus = "") { // key "" = 닫기 · focus: "cancel" = 확인 줄의 「취소」 로, "del" = 그 줄의 × 로
  if (recentDrop && recentDrop.busy) return;
  const at = key || (recentDrop && recentDrop.key);
  recentDrop = key ? { key, busy: false } : null;
  renderRecentWorks($("workList"), recentShown);
  const li = at && [...$("workList").children].find((x) => x.dataset.works === at);
  const sel = focus === "cancel" ? '[data-recent-drop="cancel"]' : focus === "del" ? ".recent-work-del" : "";
  const to = li && sel && li.querySelector(sel);
  if (to) to.focus();
}
function recentDropEl(r) { // 그 줄 아래 확인 줄 — 무엇을 몇 개 · 되살릴 수 없음 · 「지우기」·「취소」(Esc = 취소)
  const docs = r.docs, T = workTaskInfo(docs[0]), busy = recentDrop.busy, box = el("div", "recent-work-drop");
  const what = `프로젝트 「${T.project}」 · 워크플로우 「${T.name}」 · Round ${r.round}`, notes = worksDropNotes(docs, true), names = worksDropNames(docs);
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "지우기 확인");
  box.append(el("p", "work-drop-text", worksDropText(docs, what) + (notes ? ` — ${notes}` : "")));
  if (names) box.append(names);
  const ok = hBtn(busy ? "지우는 중…" : "지우기", () => recentDropRun(r, what), { cls: "btn sm project-danger", disabled: busy }), cancel = hBtn("취소", () => recentDropSet("", "del"), { disabled: busy });
  ok.dataset.recentDrop = "ok";
  cancel.dataset.recentDrop = "cancel";
  const acts = el("div", "work-drop-acts");
  acts.append(ok, cancel);
  box.append(acts);
  box.onkeydown = (e) => { if (e.key === "Escape") { e.preventDefault(); recentDropSet("", "del"); } };
  return box;
}
async function recentDropRun(r, what) {
  const d = recentDrop;
  if (!d || d.busy) return;
  d.busy = true;
  renderRecentWorks($("workList"), recentShown);
  const result = await worksDelete(r.docs.map((x) => x.id));
  recentDrop = null;
  recentShown = recentShown.map((row) => ({ ...row, docs: row.docs.filter((x) => !result.done.includes(x.id)) })).filter((row) => row.docs.length); // 목록을 다시 못 읽어도 지운 줄은 걷는다
  renderRecentWorks($("workList"), recentShown);
  worksDropToast(r.docs, result, what);
  await loadWorks();
}

function renderWorks(ul, list) {
  ul.textContent = "";
  if (!list.length) { ul.append(el("li", "none", "아직 작업이 없습니다 — 파일을 올리면 작업이 생깁니다.")); return; }
  for (const w of list) {
    const li = el("li", "work" + (w.id === state.id ? " current" : ""));
    const open = el("button", "work-open");
    open.type = "button";
    open.title = w.id === state.id ? "지금 보는 작업" : "이 작업 열기";
    const top = el("span", "work-top");
    top.append(el("span", "work-name", w.name));
    if (w.id === state.id) top.append(el("span", "work-now", "지금"));
    const T = workTaskInfo(w), task = el("span", "work-task"); // 최근 작업 줄과 같은 TASK · 과제 · 역할(② §7)
    if (T.job) task.append(el("span", "work-task-text", `${T.project ? `프로젝트 「${T.project}」` : "프로젝트 미지정"}`));
    task.append(taskChipEl(T));
    if (T.job) task.append(el("span", "work-task-text", `Round ${taskRound(w.task)}${T.role ? ` · ${T.role}` : ""}`));
    open.title += `\n${T.what}`;
    open.append(top, task, el("span", "work-meta", `${(w.format || "").toUpperCase()} · ${fmtSize(w.size || 0)} · 만듦 ${fmtWhen(w.created)} · 바뀜 ${fmtWhen(w.updated)}`
      + (w.commits ? ` · 확정 ${w.commits}` : "") + (w.edited ? ` · 고친 문단 ${w.edited}개` : "") + (w.source === "sample" ? " · 예제" : "")));
    const tags = el("span", "work-tags");
    tags.append(verifyTag("import", (w.verify || {}).import), verifyTag("edit", (w.verify || {}).edit));
    open.append(tags);
    open.onclick = () => openWork(w.id);
    const del = el("button", "icon work-del", "×");
    del.type = "button";
    del.title = "작업 지우기";
    del.setAttribute("aria-label", `작업 「${w.name}」 지우기`);
    del.onclick = () => deleteWork(w);
    li.append(open, del);
    ul.append(li);
  }
}

async function openWork(id) {
  if (taskSaveCount) await taskSetPending;
  if ($("worksDlg").open) $("worksDlg").close();
  if (id === state.id) return;
  if (!confirmDiscard()) return;
  await divSettingsFlush();
  setSaveState("busy", "작업 여는 중…");
  try { await load(id); } catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); loadWorks(); }
}

async function deleteWork(w) {
  if (!confirm(`작업 「${w.name}」을(를) 지울까요?\n올린 원본·편집 상태·검증 기록이 모두 지워지고 되살릴 수 없습니다.`)) return;
  try {
    await api(`/api/works/${w.id}`, { method: "DELETE" });
    if (w.id === state.id) closeDoc();
    toast(`작업 「${w.name}」을(를) 지웠습니다`);
  } catch (e) { toast(e.message, true); }
  loadWorks();
}

// ---- 작업 종류 · 첨부 파일 · 할 일 · 문서 목록(spec_작업 ② §10, 2026-11-11 사용자) — 고르면 작업(work.json task)에 저장. 값은 server.py TASK 와 같게.
// 상단 바: 문서 목록(파일 이름 자리 — #docSwitch). 작업 종류는 패널 머리(#panelTask — 상단 바의 옛 #taskKind 는 같은 날 없앰: 사용자 "이건 이제 필요 없지 않냐?").
// 「연구개발과제」 일 때만 그 내용(#paneDiv — 탭 띠에 탭은 없다: 2026-11-12 없앰, 패널 머리의 목록·탭 「작업 개요」 로 연다)이 열리고 그 패널 첫 카드(taskRow)에 할 일 / 과제·첨부 파일, 아래에 구분 기준.
const WORK_TASK = {
  kind: [["", "작업 종류 선택"], ["rnd", "연구개발 프로젝트"], ["general", "일반 문서"]], // general = TASK 「문서 일반 편집」 의 작업 종류(spec_일반편집 ② §11)
  file: [["", "선택 안 함"], ["plan", "사업계획서"], ["report", "연차보고서"], ["part", "기관 문서"]], // part = 취합에 들어온 기관 문서(spec_취합 ② §2 — 취합본은 plan)
  job: [["", "선택 안 함"], ...Object.entries(TASK_CATALOG).map(([key, task]) => [key, task.name])],
};
const taskRnd = () => !state.task || state.task.kind === "rnd"; // task 가 없으면(시험용 화면 등) 전처럼 연구개발과제로 본다
const taskGeneral = () => !!state.task && state.task.kind === "general"; // 「일반 문서」 — 처음 여는 보기가 「에이전트」 · 「작업 개요」(Div) 탭은 없다(spec_일반편집 ② §12)
const taskName = (key, v) => (v && (WORK_TASK[key].find((o) => o[0] === v) || [])[1]) || "";

function taskSelect(sel, key) { // select 하나를 선택지로 채우고 지금 값으로 — 바꾸면 저장
  for (const [v, name] of WORK_TASK[key]) sel.append(new Option(name, v));
  sel.dataset.task = key; // 화면 검사가 칸을 키로 찾는다(차례에 기대지 않게)
  sel.value = (state.task && state.task[key]) || "";
  sel.onchange = () => key === "job" && typeof projectTaskPick === "function" ? projectTaskPick(sel.value) : taskSet(key, sel.value);
  return sel;
}

function taskDraw() { // 문서를 열 때 · 고른 뒤 — 패널 머리 「작업」(② §10 「패널 머리」) · 탭 「작업 개요」
  const sel = $("panelTask");
  if (sel.options.length) sel.value = (state.task && state.task.kind) || "";
  else { taskSelect(sel, "kind"); sel.onchange = () => panelTaskPick(sel.value); } // 여기서 고르면 그 내용까지 연다
  toolTabsDraw();
  docRoleDraw();
  if (typeof docStatusLoad === "function") docStatusLoad(); // 이름 줄의 분석 상태(doc_status.js — spec_작업 ② §20): 문서를 열 때 · 닫을 때 · 작업 종류가 바뀐 뒤
}
// 목적 문서 표시(spec_작업 ② §10 「목적 문서 표시」, 2026-11-13 사용자 "여기 목적문서 인지 아닌지 간단하 표시가 있으면 좋겠는데") — 첫째 면 이름 줄(#docRole) · 둘째 면 탭(data-role — peerTabsDraw).
// 목적 문서 = TASK 의 target 종류(task_catalog.js = server works.TARGET_FILE: 이관의 연차보고서 · 취합의 취합본), 같은 TASK 의 다른 종류 = 원본. 목적 문서가 없는 TASK·종류를 안 고른 문서는 표시 없음.
const DOC_ROLE = { target: ["목적 문서", "목적", "이 워크플로우에서 내용을 받아 고치는 문서"], source: ["원본 문서", "원본", "이 워크플로우에서 내용을 가져오는 문서(바뀌지 않음)"] };
function taskDocRole(t, job) { // "target" | "source" | "" — job = 작업에 할 일이 안 적혀 있을 때 쓸 값(둘째 면 탭: 지금 문서의 할 일). 원본 = 그 TASK 의 문서 종류 가운데 목적 문서 아닌 것(취합에 든 연차보고서 같은 남의 종류는 표시 없음)
  const c = TASK_CATALOG[(t && t.job) || job || ""] || {}, file = (t && t.file) || "";
  if (!c.target || !file) return "";
  return file === c.target ? "target" : [c.file, ...(c.files || []), ...Object.values(c.gather || {})].includes(file) ? "source" : "";
}
function docRoleDraw() { // taskDraw 끝(문서를 열 때 · 닫을 때 · 프로젝트·TASK·첨부 파일을 고른 뒤)
  const b = $("docRole"), role = state.id ? taskDocRole(state.task) : "", d = DOC_ROLE[role];
  b.hidden = !d;
  b.dataset.role = role;
  b.textContent = d ? d[0] : "";
  b.title = d ? `${d[0]} — ${d[2]}\n워크플로우 「${taskName("job", state.task.job)}」 · ${taskName("file", state.task.file)}` : "";
}
// 표시 켜고 끄기의 기억 — 문서마다 따로(spec_작업 ② §12 「도구는 문서마다」, 2026-11-19 사용자 "원본, 목적문서가 따로면 도구도,, 따로 따로 적용하ㄹ수 있게 해야지"):
// 이름 줄의 표시 아이콘(doc_quick.js — 템플릿 · 서식 라벨 · 표 라벨 · 구분 기준 자리 · 편집 구역)은 TASK 의 원본 · 목적 문서가 저마다 제 값을 기억한다(키 뒤에 「@source」 · 「@target」 —
// 둘째 면에서 켜도 첫째 면은 그대로, 도구를 쓸 문서를 바꿔도 값은 문서를 따라간다). 역할이 없는 문서는 공통 키(둘째 면에 뜬 역할 없는 문서는 「@peek」 — 첫째 면의 값을 바꾸지 않게).
// 제 값이 아직 없으면 공통 키의 값을 쓴다(처음엔 전과 같게 보인다). 부르는 곳: tplMarksOn · tplFmtOn · divMarksOn(이 파일) · tblMarksOn(tables.js) · zonesOn(zones.js)과 그 켜고 끄기
function quickKey(base) { const r = state.id ? taskDocRole(state.task) || (PEEK ? "peek" : "") : ""; return r ? `${base}@${r}` : base; }
function quickGet(base) { // 기억한 값 | null — 제 키에 없으면 공통 키
  try { const k = quickKey(base), v = localStorage.getItem(k); return v != null || k === base ? v : localStorage.getItem(base); } catch { return null; }
}
function quickSet(base, v) { try { localStorage.setItem(quickKey(base), v); } catch { /* 기억만 안 함 */ } }
// 패널 머리 둘째 줄의 탭 「작업 개요」 · 「<도구>」(#toolTabs — ② §10 「패널 머리」, 2026-11-12 사용자 "작업내용, 검증 탭으로 줘라 그냥 구지 이상하게 하지 말고": 전의 「↩ 작업 내용」 단추 #taskHome 을 바꿈).
// 2026-11-15 사용자 「검증, 기록, PDF 사이드 패널에 있으니깐 여기에 필요 없어 보이거든」: 검증 · PDF · 기록은 이 줄의 고정 탭(#tabVerify·#tabPdf·#tabLog — 문서 위 탭 띠에서 옮김) →
// 2026-11-16 사용자 「왜 탭에 에이전트가 없고 작업 내용이란 곳에 있나? 검증/PDF/기록/작업리스트는 우측에 접어두고 클릭하면 펼치기 … 다른 task 랑 구조가 같아야 하는데 다름」 →
// 줄 = 왼쪽 「대시보드」(#tabDash — 첫 탭: 2026-11-18 사용자 「에이전트 보다 대시보드를 앞부분에 놔줘」) · 「에이전트」(#tabAgent — hwpx 면 어느 TASK 든 · 문서 위 탭 띠에서 옮김: 전에는 「일반 문서」 만 「작업 개요」 가 에이전트 보기였다) · 「작업 개요」(연구개발 TASK 의 Div 만) ·
// 「<도구>」(탭 띠에서 마지막으로 고른 도구 — 고른 적이 없으면 감춤) / 오른쪽 접는 묶음 = 검증 · PDF · 기록 + 펼치기 단추(#toolMore). 접힌 동안은 그 묶음에서 고른 탭 하나만 보인다.
// 같은 날 사용자 「작업리스트는 우측 상단에 아이콘으로 넣어줘라」: 「작업 리스트」 는 묶음의 넷째 탭(#toolTabList)에서 상단 바 아이콘 #taskListBtn 으로 — 아래 taskListBtnDraw · taskListToggle.
// 같은 날 사용자 「기본적으로 헤딩추출이나 표 는 탭에 에이전트에 넣어줘야지」 → 답 「띠에서 뺌」: 「헤딩 추출」·「표」(#tabHeads·#tabTables)는 「작업 개요」 다음의 고정 탭(늘 보임 — 보임은 headsReset·tablesReset 이 정한다) ·
// 「<도구>」 는 이제 탭 띠의 고친 문단 · 문서 비교만(spec_작업 ② §10 「둘째 줄」).
// 부르는 곳: taskDraw · showTab · divReset · toolMoreSet
const PANEL_TOOLS = ["Verify", "Pdf", "Log"]; // 패널 머리 오른쪽 접는 묶음의 고정 탭(id tab<이름> — showTab·toolShown 이 그대로 찾는다)
const PANEL_MAIN = ["Heads", "Tables"]; // 패널 머리 왼쪽의 고정 탭(에이전트 · 작업 개요 다음 — 2026-11-16 탭 띠에서 옮김)
let toolLast = null; // 탭 띠(고친 문단 · 문서 비교)에서 마지막으로 본 도구
let toolMoreOpen = (() => { try { return localStorage.getItem("nfm.toolMore") === "1"; } catch { return false; } })(); // 오른쪽 묶음을 펼쳤나 — 처음엔 접힘 · 이 브라우저에 기억
function toolMoreSet(open) {
  toolMoreOpen = open;
  try { localStorage.setItem("nfm.toolMore", open ? "1" : "0"); } catch { /* 기억만 안 함 */ }
  toolTabsDraw();
}
function toolTabsDraw() {
  const cur = $("panel").dataset.tool || "Verify", on = !!state.id;
  if (!["Agent", "Dash", "Div", "Tasks", ...PANEL_MAIN, ...PANEL_TOOLS].includes(cur) && TOOL_INFO[cur]) toolLast = cur;
  if (typeof agentFloatSync === "function") agentFloatSync(); // 상단 바 에이전트 아이콘의 눌림 · 다른 문서를 열거나 닫았을 때의 에이전트 창(agent_float.js)
  $("toolTabs").hidden = $("toolMore").hidden = !on;
  $("toolTitle").hidden = $("toolTag").hidden = on; // 값은 그대로 채운다(접힌 띠 이름 — colRailName)
  if (!on) return;
  const a = $("tabAgent"), t = $("toolTabTask"), u = $("toolTabTool");
  a.hidden = !toolShown("Agent") || agentFloatOn(); // hwpx 만(docx 는 에이전트 보기가 없다) · 에이전트가 떠 있는 창 자리면 탭이 없다(상단 바 아이콘으로 엶 — 2026-11-18 사용자: agent_float.js)
  const d = $("tabDash"); // 대시보드(dashboard.js — spec_작업에이전트 ② §9): 문서가 열려 있으면 늘(TASK 가 없으면 TASK 고르기) · 첫 탭(2026-11-18 사용자 「에이전트 보다 대시보드를 앞부분에 놔줘」)
  d.hidden = !toolShown("Dash");
  t.hidden = !taskRnd(); // 연구개발 TASK 의 내용(Div) — 「일반 문서」 는 에이전트 보기가 그 TASK 의 일이라 이 탭이 없다
  u.hidden = !toolLast || !toolShown(toolLast);
  if (toolLast) { u.textContent = TOOL_INFO[toolLast][0]; u.setAttribute("aria-controls", `pane${toolLast}`); }
  const rows = [[d, cur === "Dash"], [a, cur === "Agent"], [t, cur === "Div"], ...PANEL_MAIN.map((n) => [$(`tab${n}`), cur === n]), [u, !u.hidden && cur === toolLast], ...PANEL_TOOLS.map((n) => [$(`tab${n}`), cur === n])]; // 작업 리스트(Tasks)는 이 줄에 없다 — 상단 바 아이콘(taskListBtnDraw)
  for (const [b, sel] of rows) { b.classList.toggle("active", sel); b.setAttribute("aria-selected", sel); b.tabIndex = sel ? 0 : -1; }
  $("toolTabs").classList.toggle("more-folded", !toolMoreOpen); // 접힘 — 묶음(.tool-more)에서 고르지 않은 탭은 CSS 가 감춘다
  const m = $("toolMore"), what = "검증 · PDF · 기록";
  m.setAttribute("aria-expanded", String(toolMoreOpen));
  m.title = toolMoreOpen ? `${what} 접기 — 고른 탭 하나만 남김` : `${what} 펼치기`;
  m.setAttribute("aria-label", toolMoreOpen ? `${what} 접기` : `${what} 펼치기`);
  const shown = (b) => !b.hidden && (toolMoreOpen || !b.classList.contains("tool-more") || b.classList.contains("active"));
  if (!rows.some(([b, sel]) => sel && shown(b))) { const first = rows.find(([b]) => shown(b)); if (first) first[0].tabIndex = 0; } // 고른 탭이 안 보여도 Tab 키가 이 줄에 들어오게
}
// 상단 바 「작업 리스트」 아이콘(#taskListBtn — spec_작업 ② §10 「둘째 줄」, 2026-11-16): 문서를 연 동안만 보임 · 눌림 = 패널이 펴진 채 작업 리스트를 보임.
// 다시 누르면 그 전에 보던 도구로(taskListPrev — 못 보는 도구면 검증) · 패널이 닫혔거나 접혔으면 작업 리스트를 펴서 보인다. 부르는 곳: showTab(toolTabsDraw 뒤) · setPanel · colFold · 단추
let taskListPrev = null;
const taskListOn = () => !!state.id && !$("panel").hidden && !colFolded("panel") && $("panel").dataset.tool === "Tasks";
function taskListBtnDraw() {
  const b = $("taskListBtn");
  b.hidden = !state.id;
  b.setAttribute("aria-pressed", String(taskListOn()));
  if (typeof agentFloatSync === "function") agentFloatSync(true); // 패널 탭 자리의 에이전트도 패널이 닫히거나 접히면 「안 보임」 — 상단 바 에이전트 아이콘의 눌림(agent_float.js)
}
function taskListToggle() {
  if (!taskListOn()) {
    const cur = $("panel").dataset.tool;
    if (cur && cur !== "Tasks") taskListPrev = cur;
    showTab("Tasks");
  } else showTab(taskListPrev && toolShown(taskListPrev) ? taskListPrev : "Verify");
}

let worksList = []; // 마지막으로 읽은 작업 목록(loadWorks) — 프로젝트 이름 고르기 · 같은 프로젝트의 문서
const taskProject = () => (state.task && state.task.project) || "";
const taskRound = (t = state.task) => Math.max(1, Number(t && t.round) || 1);
const taskScopeKey = (t = state.task) => JSON.stringify([t && t.project || "", t && t.job || "", taskRound(t)]);
const taskSameScope = (w, t = state.task) => !!(t && t.project && w.task && w.task.project) && taskScopeKey(w.task) === taskScopeKey(t);
const taskMates = (list = worksList) => list.filter((w) => w.id !== state.id && taskSameScope(w));

function taskRow() { // 「연구개발과제」 패널 첫 카드 — 할 일 · 과제 · 첨부 파일. 「작업」 칸은 여기 없다 — 패널 머리의 목록 하나뿐(2026-11-12 사용자 답 「뺌」: 처음엔 첫 줄 = 작업 · 할 일 — 11-11 "작업이랑 할일")
  const row = el("section", "dv-task");
  const field = (name, title, control) => { const lab = el("label", "dv-task-field"); lab.title = title; lab.append(el("span", null, name), control); row.append(lab); };
  // 프로젝트 = 같은 이름으로 묶인 문서들 — 새 이름을 쓰거나 있는 이름을 고른다. 고르기 목록은 자체 목록(project_workspace.js projectComboAttach — spec_작업 ② §19, 2026-11-13:
  // 브라우저 datalist 는 지금 적힌 글자와 맞는 이름만 보여, 프로젝트가 적혀 있으면 다른 프로젝트가 안 보였다)
  const inp = el("input");
  inp.type = "text"; inp.maxLength = 60; inp.value = taskProject(); inp.placeholder = "프로젝트 이름"; inp.dataset.task = "project";
  inp.disabled = (typeof projectBusy === "function" && projectBusy()) || dv.busy; // TASK 실행·저장·취합이 도는 동안은 꺼 둔다(② §19 — 끝나면 projectControlsSync 가 켠다)
  let sent = null; // 이 칸에서 이미 보낸 이름 — Enter 로 정한 뒤 포커스가 나가며(change) 같은 이름을 한 번 더 보내지 않게(저장하면 칸은 새로 만들어진다)
  // 임시 프로젝트(「임시 프로젝트 N」 — spec_작업 ② §17 「임시 프로젝트」)에 이름을 적으면 이 문서만 옮기지 않고 임시 프로젝트의 이름을 바꾼다(문서 모두 · 이미 있는 이름이면 그 프로젝트로 옮김: project_workspace.js projectTempName). 비우면 전처럼 이 문서만 프로젝트에서 뺀다
  const temp = typeof projectIsTemp === "function" && projectIsTemp(taskProject());
  const commit = () => { // 고름 · Enter · 포커스를 옮김 — 지금 프로젝트와 같으면 다시 저장하지 않는다
    const name = inp.value.trim().replace(/\s+/g, " ");
    if (name === taskProject() || name === sent) return;
    sent = name;
    const run = temp && name && state.stored ? projectTempName(taskProject(), name).then((ok) => { if (!ok) taskDraw(); return ok; }) : taskSet("project", name);
    run.then((ok) => { if (!ok) sent = null; }, () => { sent = null; });
  };
  inp.onchange = commit;
  if (typeof projectComboAttach === "function") projectComboAttach(inp, { list: "taskProjectList", commit });
  else inp.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) inp.blur(); };
  if (temp) inp.addEventListener("focus", () => requestAnimationFrame(() => { if (document.activeElement === inp && inp.value === taskProject()) inp.select(); })); // 임시 이름은 고쳐 쓰는 것이 아니라 새로 적는 것 — 칸에 들어가면 통째로 고름
  field("프로젝트", temp ? `임시 이름입니다 — 프로젝트 이름을 적으면 이 임시 프로젝트(문서 ${projectDocCount(taskProject()) || 1}개)의 이름이 그 이름으로 바뀝니다 · 이미 있는 프로젝트를 고르면 그 프로젝트로 문서를 모두 옮깁니다`
    : "같은 프로젝트의 워크플로우들이 프로젝트 구성을 공유합니다 — 칸을 누르면 모든 프로젝트가 보입니다", inp);
  if (temp) { const tag = el("span", "dv-tag is-temp", "임시 이름"); tag.title = "이름 없이 시작해 붙은 임시 이름입니다 — 칸에 프로젝트 이름을 적으세요"; row.lastChild.append(tag); }
  field("워크플로우", "프로젝트 안의 워크플로우를 선택합니다 — 새 워크플로우는 작업 리스트에서 파일을 올려 시작합니다", taskSelect(el("select"), "job"));
  const lost = taskLostWhy((state.task || {}).job); // 조립한 워크플로우가 목록에 없음(지워짐 · 저장 파일을 못 읽음 — spec_워크플로우 ② §15 「실행」): 빈 칸 · 사라진 단계로 두지 않고 워크플로우 칸 아래 한 줄(job 값은 다른 워크플로우를 고를 때까지 그대로)
  if (lost) { const p = el("p", "dv-caption dv-task-lost"); p.setAttribute("role", "status"); p.append(el("span", "dv-tag is-warning", "확인 필요"), " ", lost); row.append(p); }
  if (typeof projectRoundRow === "function") row.append(projectRoundRow());
  const slots = taskSlots(), gather = gatherOn(), inSlot = new Set(gather ? gatherDocIds() : (slots || []).map((k) => (taskSlotDoc(k) || {}).id)); // 이관이면 첨부 파일 칸 둘 + 단계(② §11) — 그 밖에는 이 문서의 종류 하나
  if (!gather && !slots) field("첨부 파일", "이 문서가 어떤 첨부 파일인지 — 처음에는 양식 판정으로 채웁니다 · 작업에 저장", taskSelect(el("select"), "file"));
  if (typeof projectConfigurationRow === "function" && taskProject() && !taskGeneral()) row.append(projectConfigurationRow());
  if (gather) row.append(gatherFlowEl()); // 취합(plan_merge) — 취합본 칸 + 기관 문서 줄 + 묶음 둘은 gather.js 가 그린다(spec_취합 ② §5)
  else if (slots) row.append(taskFlowEl());
  const mates = taskMates().filter((w) => !inSlot.has(w.id)), mate = (w) => { const f = taskName("file", (w.task || {}).file); return f ? `${w.name}(${f})` : w.name; };
  if (mates.length) row.append(el("p", "dv-caption dv-task-mates", `이 라운드의 참고 문서 ${mates.length}개 — ${mates.map(mate).join(" · ")}`));
  return row;
}

let taskSaveCount = 0, taskSetPending = Promise.resolve();
function taskSet(key, value) {
  const id = state.id, epoch = state.epoch;
  taskSaveCount += 1;
  const run = taskSetPending.catch(() => {}).then(() => id === state.id && epoch === state.epoch ? taskSetNow(key, value) : false);
  taskSetPending = run.finally(() => { taskSaveCount -= 1; if (typeof projectControlsSync === "function") projectControlsSync(); });
  return taskSetPending;
}
async function taskSetNow(key, value) {
  if (typeof projectBusy === "function" && projectBusy(false)) { taskDraw(); if (dv.view) divRender(); toast("진행 중인 작업이 끝난 뒤 프로젝트나 워크플로우를 바꿀 수 있습니다"); return false; }
  const id = state.id, epoch = state.epoch;
  await divSettingsFlush();
  if (epoch !== state.epoch) return;
  if (key === "job" && value && value !== (state.task || {}).job) { // 조립한 워크플로우를 고르면 그 정의를 서버에서 다시 읽는다(taskCatalogRefresh — 붙박이는 안 읽음): 지워졌으면 고르지 않고, 바뀌었으면 새 정의로 그린다
    const R = await taskCatalogRefresh(value);
    if (epoch !== state.epoch) return;
    if (R && R.gone) { taskDraw(); if (dv.view) divRender(); toast(R.why, true); return false; }
    if (R && R.changed) toast(TASK_DEF_PICKED);
  }
  const previous = state.task;
  // 프로젝트·TASK 를 바꿀 때는 round 를 보내지 않는다 — 서버가 새 묶음의 최신 라운드로 둔다(spec_작업 ② §10·§19, 2026-11-13: 전에는 늘 1 을 보내 최신 라운드가 2 이상인 프로젝트에 들어가면
  // 이전 라운드가 되어 구분 기준이 공유되지 않았다). 화면의 값은 응답(r.task)이 올 때까지 1 로 본다(저장이 꺼진 화면은 그대로 1)
  const regroup = key === "project" || key === "job";
  state.task = { kind: "", file: "", job: "", project: "", ...state.task, [key]: value, ...(regroup ? { round: 1 } : {}) };
  // 작업 종류 ↔ 할 일의 조합(server.py TASK_KIND — 어긋나면 400: spec_일반편집 ② §11): 종류를 바꾸면 다른 종류의 할 일은 비우고, 할 일을 고르면 종류가 그 할 일을 따른다
  // (작업 종류가 정해진 할 일 — 문서 일반 편집 = general — 은 종류를 비워도 어긋난다. 그 밖의 할 일은 연구개발이고 종류를 비운 채로도 된다)
  const jobKind = state.task.job ? taskKindOf(state.task.job) : "";
  if (state.task.job && (jobKind !== "rnd" ? state.task.kind !== jobKind : state.task.kind && state.task.kind !== "rnd")) state.task = key === "kind" ? { ...state.task, job: "" } : { ...state.task, kind: jobKind };
  taskDraw();
  if (!taskRnd() && $("panel").dataset.tool === "Div") showTab(taskGeneral() && toolShown("Agent") ? "Agent" : "Verify");
  divMarksDraw(); // 연구개발과제가 아니면 문서의 구분 기준 표시도 걷는다
  if (!state.stored) return true; // 작업 저장이 꺼져 있으면 이 화면에서만
  try {
    const { round: sentRound, ...noRound } = state.task; // regroup 이면 round 칸 없이
    const r = await api(`/api/works/${id}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify(regroup ? noRound : state.task) });
    if (epoch !== state.epoch) return;
    state.task = r.task; // 라운드는 서버가 정한 값(taskRound 가 읽는다 — 번호가 없으면 1)
    if (key === "project" || key === "job") {
      divReset(); peerPick = null;
      if (typeof gatherState !== "undefined") gatherState = null;
      if (typeof compareReset === "function") compareReset();
    }
    await loadWorks();
    if (key === "project" && typeof projectInfoLoad === "function") projectInfoLoad(true); // 프로젝트를 옮겼다 — 문서가 다 빠져나간 프로젝트(문서 없는 프로젝트: ② §17)가 작업 리스트·고르기 목록에 보이게
    if (epoch === state.epoch && !$("paneDiv").hidden && (key === "project" || key === "job")) await divShow();
    if (r.division && epoch === state.epoch && typeof projectEnterNote === "function") projectEnterNote(r.division); // 프로젝트에 들어간 직후 알림 — 갈래는 서버가 알려 준다(adopted · seeded · none: ② §19). 칸이 없으면 알림도 없다
    if (epoch === state.epoch && typeof agentStylesRefresh === "function") agentStylesRefresh(); // 에이전트 보기의 반영 정책(원본 문서는 보기만 — spec_일반편집 ② §8)은 TASK·첨부 파일 종류를 따른다: 바꾼 뒤 다시 읽는다
    return true;
  } catch (e) { if (epoch === state.epoch) { state.task = previous; taskDraw(); if (dv.view) divRender(); } toast(`프로젝트·워크플로우를 저장하지 못했습니다: ${e.message}`, true); return false; }
}

// ---- 할 일의 차례(spec_작업 ② §11, 2026-11-11 사용자 "할일이 정해지면 순차적으로 작업이 진행되어야") — 이관을 고르면 첫 카드에 첨부 파일 칸 둘(사업계획서 = 기준 · 연차보고서)과 단계(준비 → ① 구분 기준 확인 → ② 자리 연결 → … — 공통 차례는 spec_병합 ② §0-1).
// 새 API 없음: 다른 문서의 구분 기준은 GET …/divisions(+ …/read), 두 문서의 분석 준비는 GET …/headings(요약). 지금 문서의 구분 기준은 화면 값(dv).
// 이관의 칸 차례(앞이 기준)는 TASK_CATALOG[job].files 를 그때그때 읽는다(taskSlots — 전에는 읽을 때 한 번 만든 표 TASK_FILES): 조립한 워크플로우는 정의를 다시 읽으면(taskCatalogRefresh) 목록이 바뀐다 —
// 지워진 정의가 표에 남아 붙박이 이관의 묶음 넷으로 그려지지 않게(spec_워크플로우 ② §15 「실행」)
// 취합(spec_취합 ② §5)은 칸의 꼴이 다르다 — 취합본 하나(base) + 기관 문서 여럿(parts): 첫 카드·단계·한 번에 진행·둘째 면을 gather.js 가 그린다. 아래 이관의 함수(taskFlowLoad·taskSteps·taskRun*·links*·fill*)는
// 두 칸([사업계획서, 연차보고서])을 전제하므로 취합에서는 부르지 않는다 — 가지마다 gatherOn() 으로 가른다(taskSlots() 는 취합에서 null)
const TASK_GATHER = Object.fromEntries(Object.entries(TASK_CATALOG).filter(([, task]) => task.gather).map(([key, task]) => [key, task.gather]));
const gatherOn = () => !!(state.stored && state.task && taskGatherOf(state.task.job) && typeof gatherFlowEl === "function"); // 취합형인가는 목록에서 그때그때(taskGatherOf — 취합형으로 조립한 워크플로우도: TASK_GATHER 는 읽을 때의 붙박이 것)
const taskFlowFresh = () => ({ seq: 0, div: {}, heads: {}, err: "" }); // 읽어 둔 것: div[작업 id] = {values | null, applied} · heads[작업 id] = 헤딩 요약 {stage2, stage3, …}
let taskFlow = taskFlowFresh();
const taskSlots = () => (state.stored && state.task && (TASK_CATALOG[state.task.job] || {}).files) || null;
const taskDocs = () => [{ ...(worksList.find((w) => w.id === state.id) || { id: state.id, name: state.name }), task: state.task }, ...worksList.filter((w) => w.id !== state.id)]; // 지금 문서가 맨 앞 — 그 task 는 화면 것
function taskSlotDoc(kind, docs = taskDocs()) { // 그 칸의 문서 — 지금 문서가 그 종류면 지금 문서, 아니면 같은 프로젝트의 그 종류 첫 문서
  const P = taskProject();
  return docs.find((w) => (w.task || {}).file === kind && (w.id === state.id || (P && taskSameScope(w)))) || null;
}
const taskFlowKey = () => taskScopeKey() + "|" + (taskSlots() || []).map((k) => (taskSlotDoc(k) || {}).id || "").join(",") + "|" + worksList.length;

function taskSlot(kind) { // 첨부 파일 칸 하나 — 고를 수 있는 문서 = 지금 문서 + 같은 프로젝트 문서 + 프로젝트 이름 없는 문서(프로젝트 이름이 비면 지금 문서뿐)
  const sel = el("select"), P = taskProject(), docs = taskDocs(), cur = taskSlotDoc(kind, docs), proj = (w) => (w.task || {}).project || "";
  sel.dataset.taskFile = kind;
  sel.append(new Option("선택 안 함", ""));
  for (const w of docs.filter((w) => w.id === state.id || (P && (!proj(w) || taskSameScope(w))))) {
    const k = (w.task || {}).file;
    sel.append(new Option(w.name + (w.id === state.id ? " — 지금 문서" : "") + (k && k !== kind ? ` (${taskName("file", k)})` : ""), w.id));
  }
  sel.value = cur ? cur.id : "";
  sel.title = (cur ? cur.name + "\n" : "") + `이 프로젝트의 ${taskName("file", kind)} — 고른 문서가 프로젝트에 들어오고, 이 칸에 있던 문서는 빠집니다`
    + (P ? "" : "\n프로젝트 이름을 적으면 다른 문서를 고를 수 있습니다");
  sel.onchange = () => taskSlotSet(kind, sel.value);
  return sel;
}

async function taskSlotSet(kind, wid) { // 칸에 문서를 고름(wid "" = 선택 안 함) — 고른 문서는 이 프로젝트의 그 종류가 되고, 칸에 있던 다른 문서는 프로젝트에서 나온다
  // 지금 문서가 그 칸에 있었으면: 다른 문서가 들어올 때 **그 문서를 연다**(화면 = 칸의 문서) · 지금 문서도 다른 문서처럼 과제에서 나온다 —
  // 2026-11-12 사용자 "연차보고서는 빈건데 왜 화면에 보이는 것은 1단계가 진행된 문서로 나오냐?"(연차보고서를 보며 빈 서식을 다시 올렸는데 화면은 옛 문서, 단계는 새 문서를 말함).
  // 「선택 안 함」 이거나 열지 않았으면(반영 안 된 수정을 두고 그만둠 · 못 엶) 전처럼 종류만 비운다(과제에는 남음 — 보고 있는 문서의 과제 칸이 비지 않게)
  const id = state.id, epoch = state.epoch, P = taskProject(), docs = taskDocs(), neu = docs.find((w) => w.id === wid);
  const put = (w, t) => api(`/api/works/${w.id}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ kind: "", file: "", job: "", project: "", ...(w.task || {}), ...t }) });
  const me = docs.find((w) => w.id === id && w.id !== wid && (w.task || {}).file === kind) || null; // 그 칸에 있던 지금 문서
  const swap = !!(me && neu) && confirmDiscard(); // 그 자리에 다른 문서가 들어온다 → 그 문서로 화면을 바꾼다(반영 안 된 수정이 있으면 먼저 묻는다)
  let moved = false; // 새 문서를 실제로 열었나
  try {
    if (neu && neu.id !== id && neu.task && neu.task.project && !taskSameScope(neu)) throw new Error("다른 프로젝트·워크플로우·라운드의 문서는 첨부할 수 없습니다");
    for (const w of docs.filter((w) => w.id !== wid && w.id !== id && (w.task || {}).file === kind && P && taskSameScope(w))) await put(w, { project: "", round: 1 });
    if (neu) {
      const r = await put(neu, { kind: "rnd", file: kind, project: P, job: state.task.job, round: taskRound() });
      if (wid === id && epoch === state.epoch) state.task = r.task;
    }
    if (swap && epoch === state.epoch) {
      setSaveState("busy", "작업 여는 중…");
      try { await load(wid); moved = true; } catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); }
    }
    if (me) {
      const r = await put(me, moved ? { project: "" } : { file: "" });
      if (!moved && epoch === state.epoch) state.task = r.task;
    }
  } catch (e) { toast(`첨부 파일을 바꾸지 못했습니다: ${e.message}`, true); }
  if (moved) { // 새 문서가 열렸다 — 옛 문서가 빠진 목록으로 다시 그리고 작업 개요(칸·단계)을 연다
    if (state.id !== wid) return;
    await loadWorks();
    if (state.id === wid) showTab("Div");
    return;
  }
  if (epoch !== state.epoch) return;
  await loadWorks();
  if (epoch !== state.epoch) return;
  if (!$("paneDiv").hidden && dv.view) divRender();
  taskFlowLoad();
}

function taskSlotUp(kind) { // 칸 오른쪽의 폴더 단추 — 그 자리에서 파일을 올려 이 칸에 넣는다(2026-11-11 사용자 "사업계획서 올리는 버튼이 없어" · "우측에 … 폴더 모양으로"). 지금 보는 문서는 그대로 — 지금 문서가 이 칸의 문서일 때만 올린 문서로 바뀐다(taskSlotSet)
  const b = el("button", "icon dv-flow-up"), name = taskName("file", kind), P = taskProject(), mine = (state.task || {}).file === kind;
  b.type = "button";
  b.dataset.taskUp = kind;
  b.disabled = !P;
  b.title = P ? `${name} 올리기 — hwp·hwpx 파일을 올려 이 칸에 넣습니다(hwp 는 hwpx 로 바꿔 받음 · ${mine ? `지금 보는 문서가 이 칸의 문서라 올린 문서로 화면이 바뀌고, 지금 문서는 프로젝트에서 나옵니다` : "지금 보는 문서는 그대로"})` : "프로젝트 이름을 먼저 적으세요 — 올린 문서를 그 프로젝트에 넣습니다";
  b.setAttribute("aria-label", `${name} 올리기`);
  b.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7.5a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
  b.onclick = (e) => {
    e.preventDefault(); // label 안이라 — 누름이 select 로 넘어가지 않게
    const inp = el("input");
    inp.type = "file";
    inp.accept = ".hwp,.hwpx";
    inp.onchange = () => taskSlotUpload(kind, inp.files[0]);
    inp.click();
  };
  return b;
}

async function taskSlotUpload(kind, file) { // 새 작업으로 올리고(?new=1) 그 칸에 넣는다 — 지금 문서가 그 칸의 문서였을 때만 올린 문서를 연다(taskSlotSet), 아니면 열지 않는다. 헤딩·표 분석(스크립트)은 바로 걸어 둔다(단계 「자리 연결」 이 그 결과를 본다)
  if (!file) return;
  if (!/\.hwpx?$/i.test(file.name)) { toast("hwp·hwpx 파일만 올릴 수 있습니다", true); return; } // hwp 는 서버가 hwpx 로 바꿔 받는다
  const epoch = state.epoch, fd = new FormData();
  fd.append("file", file);
  toast(/\.hwp$/i.test(file.name) ? `${file.name} — hwpx 로 바꿔 올리는 중…(한글이 변환)` : `${file.name} 올리는 중…`);
  let d;
  try { d = await api("/api/docs?new=1", { method: "POST", body: fd }); }
  catch (e) { toast(`올리지 못했습니다: ${e.message}`, true); return; }
  api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 못 걸어도 단계가 「없음 — 추출」 로 안내한다
  if (epoch !== state.epoch) return;
  await loadWorks();
  if (epoch !== state.epoch) return;
  await taskSlotSet(kind, d.docId);
  toast(`${file.name} — ${taskName("file", kind)} 칸에 넣었습니다`);
}

function taskReadValues(got) { // 문서에서 읽은 값(…/divisions/read) → 구분 값 — 단계나 기관 이름이 읽혔을 때만(자리표시뿐인 빈 양식은 null)
  const o = (got && got.orgs) || {};
  if (!got || !(got.stages || o.lead || (o.joint || []).some(Boolean))) return null;
  return { ...divDefault(), ...got, orgs: { ...divDefault().orgs, ...o } };
}

async function taskFlowLoad() { // 단계 ①② 에 쓸 다른 문서 쪽 자료를 읽는다 — 두 칸이 다 찼을 때만(지금 문서 쪽은 화면 값이라 안 읽음). 끝나면 단계 목록만 다시 그림
  if (gatherOn()) return gatherLoad(); // 취합 — 취합 상태(GET …/gather)를 읽는다(gather.js)
  const slots = taskSlots();
  if (!slots) return;
  const epoch = state.epoch, flow = taskFlow, seq = ++flow.seq, [plan, report] = slots.map((k) => taskSlotDoc(k)), div = {}, heads = {};
  let err = "";
  if (plan && report) {
    try {
      await Promise.all([plan, report].map(async (w) => {
        const hv = api(`/api/docs/${w.id}/headings`).catch(() => ({})); // 요약만(가벼움 — 추출을 시작하지 않는다). 못 읽으면 「없음」 으로
        const r = w.id === state.id ? null : await api(`/api/docs/${w.id}/divisions`); // 닫힌 문서는 서버가 연다(spec_작업 ② §3)
        heads[w.id] = await hv;
        if (!r) return;
        // 기준 문서(사업계획서)의 값 = 반영 값 → 입력 값(자리 연결 API merge_api._read 와 같은 차례 — 문서가 실제로 맞춰진 값이 먼저), 견줄 문서는 입력 값 → 반영 값
        let values = ((w === plan ? r.applied || r.settings : r.settings || r.applied) || {}).values || null, read = false;
        if (!values && w === plan && r.profile.form) { values = taskReadValues((await api(`/api/docs/${w.id}/divisions/read`)).read); read = !!values; } // 저장된 값이 없으면 문서에 적힌 값 — 사람이 확인해 저장해야 기준이 된다
        div[w.id] = { values, applied: r.applied, read, input: (r.settings || {}).values || null, confirmed: r.confirmed || null, sharing: r.projectSharing || null }; // input·confirmed = 1단계 「프로젝트 구성 추출」(spec_작업 ② §18)
      }));
    } catch (e) { err = e.message; }
  }
  if (epoch !== state.epoch || flow !== taskFlow || seq !== flow.seq) return;
  Object.assign(flow, { div, heads, err });
  taskStepsDraw();
  if (plan && report && !err) linksCall(report); // ② 자리 연결 — 연결 목록(또는 문서별 까닭)을 읽는다. 큰 문서는 처음 몇 초(서버가 요약을 기억)
  if (plan && report && !err) taskCleanupLoad(report); // ⑥ 작성요령 삭제 — 지울 안내 수(지금 문서에서 스크립트로 셈 — 1초 안팎)
  if (plan && report && !err) { taskGuidesLoad(report); taskHeadsWatch(); taskLlmLoad(); } // 저장한 작성 지침 · 분석이 도는 중이면 요약을 5초마다 · LLM 을 쓸 수 있나(한 번만) — spec_작업 ② §21
}

function taskDivOf(w, basis = false) { // 문서의 구분 기준 {values | null(값 없음), applied, read?} — 지금 문서는 화면 값, 다른 문서는 읽어 둔 것. undefined = 아직 못 읽음. basis = 기준 문서(반영 값이 먼저)
  if (w.id !== state.id) return taskFlow.div[w.id];
  if (!dv.view || !dv.values) return undefined;
  if (basis && dv.view.applied) return { values: dv.view.applied.values, applied: dv.view.applied };
  return { values: dv.view.settings || dv.view.applied || dv.dirty ? divValues() : null, applied: dv.view.applied };
}
function taskConfigOf(w) { // 1단계 「프로젝트 구성 추출」(spec_작업 ② §18) — 기준 문서(사업계획서)의 {values(입력 값 | null), confirmed, sharing, read(값이 없어 문서에서 읽은 값 | null)}. undefined = 아직 못 읽음
  if (w.id === state.id) return dv.view && dv.values ? { values: dv.view.settings || dv.dirty ? divValues() : null, confirmed: dv.view.confirmed || null, sharing: dv.view.projectSharing || null, read: null } : undefined;
  const D = taskFlow.div[w.id];
  return D && { values: D.input, confirmed: D.confirmed, sharing: D.sharing, read: !D.input && D.read ? D.values : null };
}
async function taskConfigConfirm(plan, values) { // 「프로젝트에 저장」(1단계 확정) — 지금 문서가 이관의 칸 문서면 그 입력 칸 값(같은 프로젝트면 같은 확정), 아니면 사업계획서 작업에 바로
  if (state.id && (taskSlots() || []).some((k) => (taskSlotDoc(k) || {}).id === state.id) && dv.view) {
    if (values && divCanon(values) !== divCanon(divValues())) { dv.values = structuredClone(values); divTouched(); divRender(); } // 문서에서 읽은 사업계획서 값 — 입력 칸에 넣고 확정
    return divConfirm();
  }
  const epoch = state.epoch;
  try { await api(`/api/docs/${plan.id}/divisions/confirm`, { method: "POST", headers: H_JSON, body: JSON.stringify(values ? { values } : {}) }); }
  catch (e) { toast(`프로젝트 구성을 확정하지 못했습니다: ${e.message}`, true); return false; }
  if (epoch === state.epoch) taskFlowLoad();
  return true;
}

async function taskPlanValuesSave(plan, values) { // 문서에서 읽은 값을 사업계획서(다른 문서)의 구분 기준 값으로 저장 — 저장만(문서는 그대로). 그 뒤 다시 읽어 견준다
  const epoch = state.epoch;
  try { await api(`/api/docs/${plan.id}/divisions/settings`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ values }) }); }
  catch (e) { toast(`사업계획서 값을 저장하지 못했습니다: ${e.message}`, true); return; }
  if (epoch === state.epoch) taskFlowLoad();
}

function taskDivDiff(a, b) { // 기준 값 a(사업계획서)와 b(연차보고서)가 다른 곳 → 글 목록(같으면 []) — 당해 차년도는 안 견준다(「맞추기」 가 사업계획서 값을 가져오고, 다른 해의 보고서를 만들 때만 연차보고서 입력에서 바꾼다 — 다르면 단계 글에 보임)
  const A = JSON.parse(divCanon(a)), B = JSON.parse(divCanon(b)), s = JSON.stringify, out = [];
  if (s(A.stages) !== s(B.stages)) out.push(`단계·차년도(${A.stages.join("+")}년 ↔ ${B.stages.join("+")}년)`);
  if (s(A.orgs) !== s(B.orgs)) out.push(A.orgs.joint.length !== B.orgs.joint.length ? `공동 기관(${A.orgs.joint.length}곳 ↔ ${B.orgs.joint.length}곳)` : "기관 이름·구분");
  if (s(A.period || null) !== s(B.period || null)) out.push("사업기간");
  if (s(A.subs) !== s(B.subs)) out.push("세부과제");
  return out;
}

function taskDivFit(values) { // 연차보고서(지금 문서)의 입력 값을 사업계획서 값으로 — 당해 차년도도(2026-11-11 사용자: 값은 모두 계획서에서 온다. 계획서 값에 당해 차년도가 없을 때만 지금 것을 둠) → 바로 계획 보기. 문서는 계획을 확인하고 「반영」 을 눌러야 바뀐다
  const cur = dv.values && dv.values.current;
  dv.values = structuredClone(values);
  if (!dv.values.current && cur) dv.values.current = cur;
  divTouched();
  divRender();
  divPlan();
}

function taskSteps() { // 이관의 단계 → [{key, name, done, soon?, text, acts[단추]}] — 앞 단계가 끝나야 다음이 「지금」(그리는 쪽이 정함)
  const [plan, report] = taskSlots().map((k) => taskSlotDoc(k)), me = (w) => w.id === state.id, both = plan && report;
  const open = (w, name) => hBtn(`${name} 열기`, async () => { await openWork(w.id); if (state.id === w.id) showTab("Div"); }, { title: `${w.name} — 그 문서를 열어 이어 합니다` });
  // 연차보고서에서 하는 일(맞추기·변경 계획·넣기 계획)의 단추 — 연차보고서가 고치는 문서가 아니면 먼저 그 문서를 고치는 문서로 바꾸고 이어서 한다. 두 문서의 자리는 그대로(peerLeft).
  // 2026-11-11 사용자 "이미 보고 있는데?": 옆에 보이는 문서를 또 「연차보고서 열기」 하라는 단추를 없앰
  const onReport = (label, run, opt = {}) => hBtn(label, async () => {
    if (!me(report)) {
      await openWork(report.id);
      if (state.id !== report.id) return; // 바꾸지 않음(저장 안 한 글을 두고 그만둠) · 못 엶
      showTab("Div");
      await divShow();
      if (state.id !== report.id || !dv.view) return;
    }
    run();
  }, { ...opt, title: (opt.title || "") + (me(report) ? "" : "\n연차보고서를 고치는 문서로 바꾼 뒤 이어서 합니다 — 두 문서의 자리는 그대로이고 사업계획서는 읽기 전용이 됩니다") });
  const lack = [[plan, "사업계획서"], [report, "연차보고서"]].filter((x) => !x[0]).map((x) => x[1]);
  const files = { key: "files", no: "", name: "준비", done: !lack.length, acts: [], // 단계 이름·번호 = 공통 차례(spec_병합 ② §0-1, 2026-11-11 사용자 확정): 준비 → ① 구분 기준 확인 → ② 자리 연결 → …
    text: lack.length ? `${lack.join(" · ")}를 위 칸에서 고르세요` + (taskProject() ? "" : " — 프로젝트 이름을 적으면 다른 문서를 고를 수 있습니다") : "사업계획서 · 연차보고서" };

  // 1단계 「문서 검토」 — 헤딩 · 표 분석(spec_작업 ② §21, 2026-11-19 사용자 "문서 검토 … 단계가 있어야 하겠구나 헤딩/테이불 분석, 그 다음에 문서구성 그다음에 매핑"): 두 문서에 헤딩 그래프·표 구조(기본 분석 — 올릴 때 저절로)가 있는가.
  // 저장된 분석이 있으면 됨 — 문서가 그 뒤 바뀌었어도 다시 하라고 하지 않는다(뼈대 유지, spec_헤딩_추출 ② §17). LLM 검증·보완은 선택(이 줄의 단추 — 「한 번에 진행」 은 안 부른다)
  const got = (w) => { const h = taskFlow.heads[w.id]; return h ? !!(h.stage2 && h.stage3) : null; }; // 읽어 둔 요약(GET …/headings) — 2·3단계 결과가 있나
  const hp = both ? got(plan) : null, hr = both ? got(report) : null, word = (x) => (x ? "있음" : "없음");
  // 문서 검토를 할 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — taskReviewOf): 붙박이 이관 = 헤딩 · 표 분석 두 문서 · LLM 검증·보완 원본(전과 같다) · 화면에서 조립한 TASK = 문서마다 고른 대로
  const RV = taskReviewOf(plan, report), docsH = RV.heads, docsL = RV.llm, hOf = (w) => (w === plan ? hp : hr); // [[문서, 이름]…] · hOf = 그 문서의 분석이 있나(못 읽었으면 null)
  // LLM 검증·보완 줄(§21 — 2026-11-19 사용자 "1단계 문서 검토에서 LLM 도 들어 가야지"): 그 문서(w)의 헤딩 · 템플릿 → 표 → 서식 정리 계획을 LLM 이 검증·보완(공통 모듈의 이어 돌리기 — 문서 안 바뀜 · 유료).
  // 끝남 = 그 문서의 헤딩 · 표가 LLM 을 거침 | LLM 을 쓸 수 없음 | 사람이 건너뜀(뒤 둘은 「건너뜀」 — 스크립트 분석만으로 간다: 막다른 길을 만들지 않는다). ready = 앞의 스크립트 분석이 끝났나 · tag = 단추 이름 앞의 문서 이름(줄 하나에 문서 여럿 — llmMany)
  const llmStep = (key, name, w, who, ready, tag = "") => {
    const s = { key, no: "", name, done: false, keep: true, skipWord: "건너뜀", acts: [], text: "" };
    if (!both || !ready) return s;
    const J = taskHeadsJob(w), run = taskHeadsRunning(w) && !!J.chain, did = taskLlmDone(w), off = taskLlmOk === false, skip = taskLlmSkipped(w);
    s.done = !run && (did || off || skip);
    s.skipped = s.done && !did;
    s.busy = run;
    s.text = run ? `${who} — LLM 검증·보완 중…(헤딩 · 템플릿 → 표 → 서식 정리 계획 · 몇 분)` : did ? `${who} — LLM 검증·보완을 거쳤습니다` : off ? "LLM 을 쓸 수 없어 건너뜁니다 — 스크립트 분석만으로 진행합니다"
      : skip ? `건너뜀 — ${who}는 스크립트 분석만으로 진행합니다` : taskLlmOk == null ? "LLM 을 쓸 수 있는지 확인하는 중…"
      : `${who}의 헤딩 · 템플릿 → 표 → 서식 정리 계획을 LLM 이 검증·보완합니다 — 유료 · 몇 분 · 문서는 바뀌지 않습니다` + (J.chain && J.error ? ` · 지난 실행 실패 — ${J.error}` : "");
    s.acts = did || off || taskLlmOk == null ? [] : skip ? [hBtn(`${tag}건너뛰기 취소`, () => taskLlmSkip(w, false), { title: "이 문서의 LLM 검증·보완을 다시 이 단계의 할 일로 둡니다" })]
      : [hBtn(`${tag}LLM 검증·보완`, () => taskHeadsLlm(w), { cls: "btn sm primary", disabled: !!taskRun || taskHeadsRunning(w) || PEEK, title: `${who}의 헤딩 · 템플릿 → 표 → 서식 정리 계획을 LLM 이 차례로 검증 · 보완합니다 — 유료 · 몇 분 · 문서는 바뀌지 않습니다(묶음의 「한 번에 진행」 도 이것을 합니다)` }),
        hBtn(`${tag}건너뛰기`, () => taskLlmSkip(w, true), { disabled: !!taskRun || run, title: `${who}는 LLM 검증·보완 없이 스크립트 분석만으로 진행합니다(이 브라우저에 기억 — 「건너뛰기 취소」 로 되돌립니다)` })];
    return s;
  };
  // 문서 여럿의 LLM 검증·보완 — 화면에서 조립한 TASK 에서 원본 · 목적 문서가 함께 「문서 검토」 를 고르고 목적 문서는 「구성 맞추기」 를 안 고른 때(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」).
  // 줄 하나에 문서마다의 상태 · 단추(이름을 붙임 · 강조는 앞 문서의 것 하나). 끝남 = 모든 문서가 거침 · 건너뜀(「건너뛰기」 기억은 문서마다 — taskLlmSkip) · per = 문서 id → 그 문서의 몫(「한 번에 진행」 의 llmPart 가 문서마다 본다)
  const llmMany = (key, name, list) => {
    const per = list.map(([w, who]) => llmStep(key, name, w, who, !!hOf(w), `${who} `)), acts = per.flatMap((x) => x.acts);
    acts.filter((b) => b.classList.contains("primary")).slice(1).forEach((b) => b.classList.remove("primary"));
    return { key, no: "", name, done: per.every((x) => x.done), skipped: per.every((x) => x.skipped), busy: per.some((x) => x.busy), keep: true, skipWord: "건너뜀", acts,
      text: [...new Set(per.map((x) => x.text).filter(Boolean))].join(" · "), per: Object.fromEntries(list.flatMap(([w], i) => (w ? [[w.id, per[i]]] : []))) }; // 빈 칸(준비 전)의 문서는 몫이 없다
  };
  // 헤딩 · 표 분석 — 「문서 검토」 를 할 문서(docsH)만 본다(붙박이 이관은 두 문서 — 전과 같은 글)
  const heads = { key: "heads", no: "", name: "헤딩 · 표 분석", done: !!both && docsH.every(([w]) => got(w)), keep: true, acts: [], text: "" };
  if (!both) { /* 준비가 먼저 */ }
  else if (docsH.some(([w]) => got(w) == null)) heads.text = "분석 결과를 읽는 중…";
  else {
    const run = docsH.filter(([w]) => taskHeadsRunning(w)), fail = docsH.find(([w]) => !got(w) && taskHeadsJob(w).error);
    const GS = (taskFlow.guides || {}).saved, gc = GS && GS.counts; // 저장한 작성 지침(연차보고서 — spec_작업 ② §21 「작성 지침 저장」)
    heads.busy = !heads.done && !!run.length; // 첫 분석이 도는 중 — LLM 검증·보완이 도는 것은 이 묶음을 막지 않는다(글로만 보인다)
    heads.text = `헤딩 그래프·표 구조: ${docsH.map(([w, n]) => `${n} ${word(got(w))}`).join(" · ")}`
      + (run.length ? ` · ${run.map(([w, n]) => `${n} ${taskHeadsJob(w).chain ? "LLM 검증·보완" : "분석"} 중…`).join(" · ")}` : fail ? ` · ${fail[1]} 분석 실패 — ${taskHeadsJob(fail[0]).error}` : "")
      + (gc && (gc.items || gc.marks) ? ` · 작성 지침 ${nf(gc.items)}개 저장(헤딩 ${nf(gc.headings)} · 표 ${nf(gc.tables)}${gc.marks ? ` · 각주 번호 ${nf(gc.marksLinked)}/${nf(gc.marks)}` : ""})` : "");
    heads.acts = [...(heads.done ? [] : [hBtn("분석", () => taskRunAll("review", "review", false, "", "heads"), { cls: "btn sm primary", disabled: !!taskRun || !!run.length, title: `헤딩 그래프·표 구조가 없는 문서만 스크립트로 분석합니다 — LLM 호출 없음 · 문서는 바뀌지 않습니다(이 단계만${docsL.length ? " — LLM 검증·보완은 다음 줄" : ""})` })]),
      ...(gc && (gc.items || gc.marks) && typeof formGuidesList === "function" ? [hBtn("작성 지침", () => formGuidesList(report), { title: "저장한 작성 지침(작성 요령 표 · <참고 N> 자료 · ※ 안내 · 각주 번호의 항목)을 헤딩별 · 표별로 문서 옆 열에 보입니다 — 4단계가 문서에서 지운 뒤에도 남습니다" })] : [])];
  }

  // 1단계의 LLM 검증·보완 = 원본 문서(사업계획서 — 이 TASK 에서 안 바뀌는 문서). 목적 문서(연차보고서)는 구조를 맞춘 뒤 2단계의 「다시 문서 검토(LLM)」 가 한다 — 구조 반영 전에 받은 판정은 반영 뒤 옛것이 된다(같은 문서에 두 번 물지 않는다)
  // 화면에서 조립한 TASK 는 docsL(taskReviewOf — 저장된 배정의 llm): 목적 문서가 들어 있으면 목적 문서도 여기서 · 할 문서가 없으면 이 줄은 그 TASK 에 서지 않는다(빈 줄 — taskStepsOf 가 뺀다)
  const [lw, lwho] = docsL[0] || [plan, "사업계획서"];
  const headsLlm = docsL.length > 1 ? llmMany("headsLlm", "LLM 검증·보완", docsL) : llmStep("headsLlm", "LLM 검증·보완", lw, lwho, !!docsL.length && !!hOf(lw));

  // 「프로젝트 구성 추출」(spec_작업 ② §18 — 2026-11-13 사용자 "구분 기준만 추출하는 단계를 1" · §21 부터 2단계 「구성 맞추기」 의 첫 단계): 기준 = 사업계획서. 구성만 추출해 프로젝트에 저장(확정) — 문서는 안 바뀐다
  const config = { key: "config", no: "", name: "프로젝트 구성 추출", done: false, early: !!both, keep: true, text: "", acts: [] }, CF = both ? taskConfigOf(me(report) ? report : plan) : undefined; // 지금 문서가 칸 문서면 그 입력 칸(같은 프로젝트 구성 — 고치면 바로 「확정 뒤 바뀜」) · early = 분석이 도는 동안에도 확정할 수 있다(값 확정은 분석과 무관)
  const csum = (v) => `${v.stages.length}단계 · 전체 ${divTotalYears(v)}년 · 기관 ${((v.orgs || {}).joint || []).length + 1}곳`, where = divConfirmWhere(CF && CF.sharing);
  const confirmBtn = (values) => { const b = hBtn(`${where}에 저장`, () => taskConfigConfirm(plan, values), { cls: "btn sm primary", disabled: dv.busy,
    title: `${values ? "사업계획서에서 읽은" : "지금 입력"} 값(단계·차년도·기관)을 ${divConfirmWhat(where)}으로 확정합니다 — 문서는 바뀌지 않습니다. 확정해야 「프로젝트 구성 반영」 으로 갑니다` }); b.dataset.taskConfirm = "1"; return b; };
  if (!both) { /* 준비가 먼저 */ }
  else if (taskFlow.err) config.text = `다른 문서를 읽지 못했습니다: ${taskFlow.err}`;
  else if (!CF) config.text = "사업계획서의 프로젝트 구성을 읽는 중…";
  else if (divConfirmValid(CF.values, CF.confirmed)) Object.assign(config, { done: true, text: `${where}에 확정함(${fmtWhen(CF.confirmed.at)}) — ${csum(CF.values)}` });
  else if (!CF.values && CF.read) Object.assign(config, { text: `사업계획서에 저장된 값이 없어 문서에서 읽었습니다(${csum(CF.read)}) — 맞으면 ${where}에 저장(확정)하세요(틀리면 아래 입력 칸에서 고칩니다)`, acts: [confirmBtn(CF.read)] });
  else if (!CF.values) Object.assign(config, { text: "프로젝트 구성(단계·차년도·기관)이 없습니다 — 사업계획서에서 추출하거나 아래 「프로젝트 구성 불러오기」 · 입력 칸에서 정하세요",
    acts: [hBtn("사업계획서에서 추출", () => divRead({ id: plan.id, name: plan.name }), { cls: "btn sm primary", disabled: dv.busy, title: "사업계획서에 적힌 단계·차년도·기관을 읽어 입력 칸에 채웁니다 — 문서는 안 바뀌고, 확인한 뒤 확정합니다" })] });
  else if (CF.confirmed) Object.assign(config, { text: `확정한 뒤 값이 바뀌었습니다 — 다시 저장하거나 확정본으로 되돌리세요(지금: ${csum(CF.values)})`,
    acts: [confirmBtn(null), ...(dv.view ? [hBtn("확정본으로 되돌리기", () => divConfirmRevert(CF.confirmed), { disabled: dv.busy, title: `입력 칸을 확정한 값(${csum(CF.confirmed.values)})으로 되돌립니다` })] : [])] });
  else Object.assign(config, { text: `${csum(CF.values)} — 확인한 뒤 ${where}에 저장(확정)하세요`, acts: [confirmBtn(null)] });
  // 「구성 불러오기」(선택 — §21: 2026-11-19 사용자 "2단계는 구성 불러오기(선택), 파일에서 아니면 저장된 곳에서"): 구성 입력 칸의 「프로젝트 구성 불러오기」 목록(문서에서 추출 · 파일 올려 추출 / 이 프로젝트의 확정본 · 다른 프로젝트 · 저장한 구성 — §18)으로 간다.
  // 불러오면 입력 칸만 바뀐다(문서 · 확정은 그대로) — 확인한 뒤 「…에 저장」 으로 확정한다. 등록부의 선택 단계 configLoad 는 이 줄의 이 단추다(대시보드: 「그 단계로」)
  if (both && CF && !taskFlow.err) config.acts = [...config.acts, hBtn("구성 불러오기", () => { const box = document.getElementById("taskStage"); showTab("Div"); if (box) taskFrameEdit(box); }, { disabled: !!taskRun || PEEK,
    title: "프로젝트 구성을 불러옵니다 — 파일에서(이 프로젝트의 문서에서 추출 · 파일 올려 추출) 또는 저장된 곳에서(이 프로젝트의 확정본 · 다른 프로젝트 · 저장한 구성). 입력 칸만 바뀌고 문서 · 확정은 그대로입니다(선택 — 안 해도 됩니다)" })];

  const division = { key: "division", no: "①", name: "프로젝트 구성 반영", done: false, early: !!both && config.done, text: "", acts: [] }, A = both && taskDivOf(plan, true), B = both && taskDivOf(report); // early = 확정만 끝났으면 분석(1단계)이 도는 동안에도 단계별로 누를 수 있다(구조 반영은 분석과 무관 — 묶음의 「한 번에 진행」 은 차례대로)
  if (!both || !config.done) { /* 준비 · 프로젝트 구성 추출이 먼저 */ }
  else if (taskFlow.err) Object.assign(division, { text: `다른 문서를 읽지 못했습니다: ${taskFlow.err}`, acts: [hBtn("다시 읽기", () => { taskFlow.err = ""; taskStepsDraw(); taskFlowLoad(); })] });
  else if (!A || !B) division.text = "두 문서의 프로젝트 구성을 읽는 중…";
  else if (!A.values) Object.assign(division, { text: "사업계획서(기준)에 프로젝트 구성 값이 없습니다 — 사업계획서에서 값을 넣거나 문서에서 읽으세요",
    acts: [me(plan) ? hBtn("문서에서 읽기", () => divRead(), { disabled: dv.busy }) : open(plan, "사업계획서")] });
  else {
    const diff = B.values ? taskDivDiff(A.values, B.values) : ["연차보고서에 값 없음"];
    const sum = `${A.values.stages.length}단계 · 전체 ${divTotalYears(A.values)}년 · 기관 ${(A.values.orgs.joint || []).length + 1}곳`;
    const cur = (v) => JSON.parse(divCanon(v)).current, [ya, yb] = [cur(A.values), B.values ? cur(B.values) : 0]; // 당해 차년도 — 안 견주지만 사업계획서와 다르면 글로 보인다
    const year = yb && ya !== yb ? ` · 당해 차년도는 연차보고서 ${yb}차년도(사업계획서 ${ya}차년도)` : "";
    if (A.read) Object.assign(division, { text: `사업계획서에 저장된 값이 없어 문서에서 읽었습니다(${sum}) — 맞으면 사업계획서의 값으로 저장하세요(틀리면 사업계획서를 열어 고칩니다)`,
      acts: [hBtn("사업계획서 값으로 저장", () => taskPlanValuesSave(plan, A.values), { cls: "btn sm primary", title: "읽은 값을 사업계획서 작업의 프로젝트 구성 값으로 저장합니다 — 문서는 바뀌지 않습니다" }), open(plan, "사업계획서")] });
    else if (diff.length) Object.assign(division, { text: `사업계획서(${sum})와 다름 — ${diff.join(" · ")}`,
      acts: [onReport("사업계획서 기준으로 맞추기", () => taskDivFit(A.values), { cls: "btn sm primary", disabled: dv.busy,
        title: "연차보고서의 프로젝트 구성 값을 사업계획서 값으로 바꾸고(당해 차년도 포함) 변경 계획을 엽니다 — 문서는 계획을 확인하고 「반영」 을 눌러야 바뀝니다 · 괄호 안은 사업계획서 ↔ 연차보고서" })] });
    else if (!(B.applied && divCanon(B.applied.values) === divCanon(B.values))) Object.assign(division, { text: `값은 사업계획서와 같음(${sum}) · 연차보고서에 아직 반영 전${year}`,
      acts: [onReport("변경 계획 보기", () => divPlan(), { cls: "btn sm primary", disabled: dv.busy, title: "연차보고서에서 바뀔 자리를 확인한 뒤 반영합니다" })] });
    else Object.assign(division, { done: true, text: `사업계획서와 같음 · 연차보고서에 반영됨 — ${sum}${year}` });
  }

  // 「다시 문서 검토」(2단계 「구성 맞추기」 의 끝 — spec_작업 ② §21, 2026-11-19 사용자 "프로젝트 구성 및 프레임 작성을 하고 다시 헤딩추출/테이블 작업을 하고 그 다음에 매핑" · "연차보고서 가 아니라 그냥 다시 문서 검토"):
  // 구조 반영으로 바뀐 문서(목적 문서)를 1단계와 같이 다시 검토한다 — 이 줄 = 헤딩·표 다시 분석(스크립트), 다음 줄 = LLM 검증·보완.
  // 끝남 = 구조 반영이 끝났고 그 문서의 분석이 그 반영 뒤의 것(taskHeadsStale 이 거짓 — 구조 반영 밖의 편집은 따지지 않는다). 구조 반영 전의 분석이 LLM 판정을 거친 결과(taskHeadsKept)여도
  // 다시 분석한다(다음 줄이 LLM 검증·보완을 다시 받는다) — LLM 을 쓸 수 없을 때만 그 결과를 그대로 둔다(끝난 것으로 보고 글로 알림 · 「다시 분석」 을 누르면 스크립트 분석으로 바뀐다)
  const reheads = { key: "reheads", no: "", name: "다시 문서 검토", done: false, keep: true, acts: [], text: "" };
  let rehFresh = false; // 목적 문서의 분석이 구조 반영 뒤의 것인가 — 다음 줄(LLM)의 앞 조건
  if (both && division.done && hr != null) {
    const stale = hr ? taskHeadsStale(report) : true, kept = !!hr && taskHeadsKept(report), keep = kept && taskLlmOk === false, run = taskHeadsRunning(report) && !taskHeadsJob(report).chain;
    rehFresh = !!hr && !stale;
    reheads.done = rehFresh || keep;
    reheads.busy = run && !reheads.done;
    reheads.text = run ? "연차보고서 헤딩·표 분석 중…" : !hr ? "구조를 맞춘 문서(연차보고서)의 헤딩·표 분석이 없습니다 — 다시 분석(스크립트)"
      : keep ? "구조 반영 전 분석(LLM 판정을 거친 결과 — LLM 을 쓸 수 없어 그대로 둠 · 늘어난 절·표는 못 이을 수 있음)"
      : stale ? `구조를 맞춘 문서(연차보고서)의 분석이 구조 반영 전 것입니다 — 늘어난 절·표가 분석에 없습니다(다시 분석 — 스크립트${kept ? " · LLM 판정은 다음 줄에서 다시 받습니다" : ""})`
      : "헤딩 그래프·표 구조가 구조 반영 뒤의 것입니다";
    reheads.acts = rehFresh ? [] : [onReport("다시 분석", () => taskRunAll("frame", "frame", false, keep ? "reheads" : "", "reheads"), { cls: "btn sm" + (reheads.done ? "" : " primary"), disabled: !!taskRun || taskHeadsRunning(report),
      title: "구조를 맞춘 문서(연차보고서)의 헤딩 그래프 → 표 구조를 스크립트로 다시 분석합니다 — LLM 호출 없음 · 문서는 바뀌지 않습니다(이 단계만)" + (kept ? "\nLLM 판정을 거친 지금 결과는 스크립트 분석으로 바뀝니다" : "") })];
  }
  const reheadsLlm = llmStep("reheadsLlm", "다시 문서 검토(LLM)", report, "연차보고서", !!(both && division.done && (rehFresh || reheads.done)));

  // ② 자리 연결(spec_병합 ② §0-1 — API …/merge-links). 그 앞에 필요한 헤딩 그래프·표 구조는 1단계 「문서 검토」 의 몫이다(§21 — 없으면 그 줄을 가리킨다)
  const L = taskFlow.links;
  const link = { key: "link", no: "②", name: "자리 연결", done: false, keep: true, acts: [], text: "" }, again = () => hBtn("다시 읽기", () => taskFlowLoad(), { disabled: !!taskFlow.linkBusy });
  if (!both) { /* 준비가 먼저 */ }
  else if (hp == null || hr == null) link.text = "분석 결과를 읽는 중…";
  else if (!(hp && hr)) { // 빠진 분석을 1단계가 하나 — 「문서 검토」 는 그 TASK 가 고른 문서만 한다(docsH — spec_워크플로우 ② §15). 아니면 이 묶음 「한 번에 진행」 의 안전망(taskRunMap)이 스크립트로
    const byReview = taskHasStage("review") && [[plan, hp], [report, hr]].every(([w, h]) => h || docsH.some(([x]) => x === w));
    link.text = (byReview ? `먼저 ${taskStageName("review")} 의 헤딩·표 분석` : taskHasStage("review") ? "헤딩·표 분석이 없습니다(이 워크플로우의 「문서 검토」 는 그 문서를 검토하지 않아 「한 번에 진행」 이 스크립트로 분석합니다)"
      : "헤딩·표 분석이 없습니다(이 워크플로우에는 「문서 검토」 가 없어 「한 번에 진행」 이 스크립트로 분석합니다)") + ` — 헤딩 그래프·표 구조: 사업계획서 ${word(hp)} · 연차보고서 ${word(hr)}`;
  }
  else if (!L) link.text = "연결 목록을 만드는 중…";
  else if (L.error) Object.assign(link, L.missing ? { text: "자리 연결은 서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" } : { text: `연결 목록을 읽지 못했습니다: ${L.error}`, acts: [again()] });
  else {
    const why = [[L.from, "사업계획서"], [L.to, "연차보고서"]].filter(([s]) => !s || s.reasons.length)
      .map(([s, name]) => `${name}: ${s ? s.reasons.map((r) => LINK_REASON[r] || r).join(", ") : "같은 프로젝트에서 찾지 못함"}`);
    if (why.length) Object.assign(link, { text: `연결 목록을 낼 수 없습니다 — ${why.join(" · ")}`, acts: [again()] }); // ① 이 끝났는데도 남는 까닭(서버가 본 것) — 그대로 보인다
    else {
      // 강조 단추 = 다음 할 일(2026-11-11 사용자 "이 다음이 LLM 검토라는걸 내가 어떻게 아냐?"): 확인 필요가 있고 LLM 검토를 아직 안 했으면 「LLM 검토」 가 앞·강조.
      // LLM 검토를 한 번 했으면 확인 필요가 남아도 ② 는 끝난 것(같은 날 사용자 "다 매칭될 필요는 없고 … 각 기관들이 또 작성을 할거야" — 남은 자리는 안 넣고 비워 둔다) — 강조는 ③ 「넣기 계획」 몫(카드에 강조 단추 하나)
      const first = !!L.counts.ambiguous && !L.llm, busy = taskFlow.llmBusy || taskFlow.linkBusy, openT = linksOpenTables(L); // openT = 스크립트가 같은 표인지 못 정한 표(후보가 없어도 — LLM 검토가 본다: spec_병합 ② §5-1 「표 짝 검토」)
      const list = hBtn("연결 목록", () => linksList(), { title: "문서 옆 열에 연결 목록을 엽니다 — 확인 필요한 자리의 원본을 후보에서 고를 수 있습니다(안 골라도 됩니다)" });
      const hint = busy ? "" : first ? " — 다음: 「LLM 검토」 로 확인 필요한 자리를 정리합니다" : L.counts.ambiguous ? ` — 남은 확인 필요 ${L.counts.ambiguous}곳은 넣지 않고 비워 둡니다(각 기관이 작성 · 고르려면 「연결 목록」)` : openT && !L.llm ? ` — 같은 표인지 못 정한 표 ${openT}개(「LLM 검토」 가 기관·차년도를 가려 봅니다)` : "";
      const old = !busy && taskHeadsOld(report) ? ` · 구조 반영으로 늘어난 절·표는 헤딩·표 분석에 아직 없습니다(${taskHasStage("frame") ? `${taskStageName("frame")} 의 ` : ""}「다시 문서 검토」)` : ""; // 새 표가 있다는 알림만(다시 하라고 다그치지 않는다 — 그 줄이 맡는다: §21)
      const guide = PEEK ? [] : [llmGuideBtn("merge-links", report.id), // 이 LLM 검토에 보내는 지침·TASK 프롬프트·마지막 프롬프트 보기(2026-11-12 사용자 — 목록이 나온 뒤면 늘 보인다 · 강조 아님)
        hBtn("매칭 지침", () => linkGuidesOpen(report), { title: "표 · 본문 자리마다 사업계획서의 어디와 어떻게 이을지 적어 둔 지침을 보고 고칩니다 — 연차보고서 양식 정보의 「자리 연결」 절에 저장되고 LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 그 자리를 볼 때 읽습니다(문서 옆 열 · 연결 코멘트도 거기)" })]; // 매칭 지침(spec_병합 ② §5-6 — 2026-11-22 사용자 "테이블, 본문별로 어떻게 매칭해야하는지 지침을 관리하고" · 전의 「연결 코멘트」 단추: 2026-11-12 "어디어디 테이블이나 단락을 연결해 주라고 코멘트를")
      // LLM 을 쓸 수 없으면 「건너뜀」 으로 끝(남은 확인 필요는 비워 둔다 — 서버 실행기의 상태 식 workflow_units._link 과 같다: 막다른 길을 만들지 않는다)
      const off = !!L.counts.ambiguous && !L.llm && taskLlmOk === false;
      Object.assign(link, { done: !L.counts.ambiguous || !!L.llm || off, skipped: off, skipWord: "건너뜀", text: linksCountText(L) + linksLlmText(L) + (taskFlow.llmBusy ? " · LLM 검토 중…" : taskFlow.linkBusy ? " · 읽는 중…" : "")
        + (off ? ` — LLM 을 쓸 수 없어 확인 필요 ${L.counts.ambiguous}곳은 넣지 않고 비워 둡니다(고르려면 「연결 목록」)` : hint) + old,
        acts: first ? [linksLlmBtn(L, true), list, ...guide] : [list, ...(L.counts.ambiguous || L.counts.toOnly || openT ? [linksLlmBtn(L)] : []), ...guide] }); // 못 정한 자리가 있을 때만 LLM 검토(사람이 누를 때만 돈다 — 비용)
    }
  }

  // ③ 넣기 계획 → ④ 내용 반영(spec_병합 ② §0-1 · §6 — API …/merge-links/plan · …/apply). 이어진 자리가 하나라도 있으면 ② 에 확인 필요가 남아 있어도 계획을 세울 수 있다(early — 못 정한 자리는 안 넣을 뿐)
  const targets = !!(L && !L.error && L.counts && (L.counts.paired || linksFixedN(L) || linksFixedErr(L))); // 넣을 자리 = 이어진 묶음 + 같은 이름 자리(고정 자리 — spec_병합 ② §5-1)
  const F = taskFlow.fill || {}, ready = !!(targets && L.from && !L.from.reasons.length && !L.to.reasons.length);
  // 정상 0건 — 서버가 전제를 확인한 빈 연결 목록(linksNone). 구성 맞추기 · 자리 연결 줄의 끝남과 따로 본다 — 전에는 division.done 까지 보아 구성 맞추기를 뺀 TASK 는 「한 번에 진행」 이 「넣을 내용이 없습니다」 로
  // 성공해도 이 둘이 끝나지 않아 「문서 정리」 로 못 갔다(astra P1 ⓒ). 「한 번에 진행」(taskRunMap)과 같은 판정이 되게 그것이 판정 전에 하는 일까지 본다 — 두 문서의 분석이 있음(hp · hr) ·
  // 목적 문서의 분석이 구조 반영 전 것(스크립트만 — taskHeadsOld)이 아님(그러면 실행이 다시 분석한 뒤의 목록으로 판정한다)
  const noTargets = !!(both && hp && hr) && !taskHeadsOld(report) && linksNone(L);
  const K = (L && !L.error && L.kept) || {}, prior = !F.done && !F.plan && ((K.applied || 0) > 0 || !!K.filled); // 지난 반영 — 넣은 기록 · 마지막 반영 표식이 지금 문서에 남아 있다(서버 merge.json · 다시 열어도 — 이 화면의 F 는 메모리만 · 서버 실행기가 넣은 것도)
  const planStep = { key: "plan", no: "③", name: "표 안 연결 · 넣기 계획", done: !!(F.plan || F.done || noTargets || prior), skipped: noTargets, early: ready, keep: true, busy: !!F.busy && F.busyStep === "plan", acts: [], text: noTargets ? "이어진 자리가 없어 계획할 내용이 없습니다" : "" };
  // 표 대응(spec_병합 ② §5-3 — 2026-11-12 사용자 "그 테이블을 저테이블에 매핑해주는 에이전트를 하나 호출해서"): 같은 표로 이었는데 두 서식의 행·열 구성이 달라 칸을 못 맞춘 표 수. 계획이 있으면 그 수(표 묶음 쪽 포함), 없으면 연결 목록의 수
  const mapOpen = (F.plan && F.plan.maps ? F.plan.maps.counts.open : linksMapOpen(L)) || 0, mapN = (F.plan && F.plan.maps ? F.plan.maps.counts.tables : linksMapN(L)) || 0;
  const mapActs = !ready || PEEK ? [] : [...(mapOpen ? [onReport(taskFlow.mapBusy ? "표 대응 중…" : "표 대응(LLM)", () => fillMap(), { cls: "btn sm", disabled: !!(F.busy || taskFlow.mapBusy),
    title: "같은 표로 이었지만 두 서식의 행·열 구성이 달라 칸을 못 맞춘 표를 표마다 LLM(Opus)에 물어 행·열을 맞춥니다 — 표마다 십수 초 · 유료. 글은 LLM 이 쓰지 않고 사업계획서 칸의 글을 옮깁니다. 문서는 「반영」 을 눌러야 바뀝니다" })] : []),
    ...(mapOpen || mapN ? [llmGuideBtn("table-map", report.id)] : [])];
  // 빈 자리 검토(spec_병합 ② §5-4 — 2026-11-12 사용자 "여기 들어가지 않은 것들은 LLM 이 검토하고 넣어주는 기능 없나?"): 다른 길이 못 채운 빈 표·빈 칸·빈 라벨 줄 가운데 아직 안 물은 수(넣기 계획이 센다)
  const GC = (F.plan && F.plan.gaps && F.plan.gaps.counts) || {}, gapOpen = GC.open || 0, gapN = (GC.cells || 0) + (GC.lines || 0) + (GC.tables || 0);
  const gapActs = !ready || PEEK || !F.plan ? [] : [...(gapOpen || gapN ? [onReport(taskFlow.gapBusy ? "빈 자리 검토 중…" : gapOpen ? "빈 자리 검토(LLM)" : "빈 자리 검토 다시", () => fillGaps({ again: !gapOpen }), { cls: "btn sm", disabled: !!(F.busy || taskFlow.gapBusy || taskFlow.mapBusy),
    title: "내용 넣기가 못 채운 자리(빈 표 · 글머리만 있는 칸 · 라벨만 있는 줄)를 모아 사업계획서의 어디에서 가져올지 LLM(Opus)에 묻습니다 — 수십 초 · 유료. 글은 LLM 이 쓰지 않고 고른 자리의 글을 그대로 옮깁니다. 문서는 「반영」 을 눌러야 바뀝니다" }),
    llmGuideBtn("gaps", report.id)] : [])];
  if (ready) Object.assign(planStep, { text: (F.plan ? fillCountText(F.plan) : F.done ? "" : prior ? `${K.applied > 0 ? `지난 반영으로 넣은 자리 ${K.applied}곳` : "지난 반영이 끝나 있습니다"} — 더 넣을 것은 「넣기 계획 다시」 가 셉니다` : "이어진 자리에 넣을 본문·표 칸·행을 셉니다 — 문서는 안 바뀝니다") // 넣은 자리 수(kept.applied)는 본문 자리의 것 — 표 칸만 채운 반영 · 확인된 「넣을 것 0」(표식 kept.filled)에 「0곳」 이라 적지 않는다
      + (taskFlow.mapBusy ? " · 표 대응 중…" : mapOpen ? ` · 칸을 못 맞춘 표 ${mapOpen}개 — 「표 대응(LLM)」 이 행·열을 맞춥니다` : "")
      + (taskFlow.gapBusy ? " · 빈 자리 검토 중…" : gapOpen ? ` · 아직 빈 자리 ${gapOpen}곳 — 「빈 자리 검토(LLM)」 가 사업계획서에서 찾습니다` : ""),
    acts: [onReport(planStep.busy ? "계획 중…" : F.plan || F.done || prior ? "넣기 계획 다시" : "넣기 계획", () => fillPlan(), { cls: "btn sm" + (F.plan || F.done || prior || !link.done ? "" : " primary"), disabled: !!F.busy, // 강조 단추는 카드에 하나 — ② 에 확인 필요가 남았으면 「연결 목록」 쪽
      title: "이어진(연결됨) 자리마다 넣을 본문 블록·표 칸·늘릴 행과 못 넣는 까닭을 셉니다 — 문서는 「반영」 을 눌러야 바뀝니다" }), ...mapActs, ...gapActs] });
  const nothing = !!(noTargets || (F.plan && F.plan.todo === 0));
  const applyStep = { key: "apply", no: "④", name: "내용 반영", done: !!F.done || nothing || prior, skipped: !F.done && nothing && !prior, early: !!F.plan, keep: true, busy: !!F.busy && F.busyStep === "apply",
    acts: F.plan ? [hBtn("계획 보기", () => fillList(), { cls: "btn sm" + (F.plan.todo && link.done ? " primary" : ""), disabled: !!F.busy })] : [],
    text: F.done ? fillDoneText(F.done) : nothing ? "넣을 것이 없습니다(이미 넣었거나 넣을 자리가 없음)" : F.plan ? "「계획 보기」 에서 확인하고 「반영」 을 누르세요" : prior ? (K.applied > 0 ? `지난 반영 — 넣은 자리 ${K.applied}곳` : "지난 반영이 끝나 있습니다 — 본문 자리에 넣은 것은 없습니다(표 칸을 채웠거나 넣을 것이 없었음)") : "" };
  division.busy = !!dv.busy && !!report && state.id === report.id;
  link.busy = !!(taskFlow.llmBusy || (division.done && hp && hr && taskFlow.linkBusy));

  // ⑥ 작성요령 삭제 — 3단계 「문서 정리」(spec_작업 ② §14 「3단계」, 2026-11-12 사용자 "3단계에 작성요령 삭제 기능을 넣어줘" → "그냥 위 첨자, 작성요령이 테이블 첫번째 줄에 있는 경우,
  // ※ 2page 이내 요약 작성.. 당구장 표시랑 색이랑 폰트가 같은 경우 정도만 삭제해도 되겠고만"): 위첨자 각주 번호 · 첫 줄이 「작성 요령」 인 표 · 안내 색 ※ 글(app/form_cleanup.py).
  // 목록은 지금 문서에서 스크립트로 센다(GET …/form-cleanup — 읽어 둔 것: taskFlow.cleanup) → 끝남 = 내용 반영(④)이 끝났고 남은 것이 없음
  const C = both ? taskFlow.cleanup : undefined, GD = taskFlow.guide || {};
  const guide = { key: "guide", no: "⑥", name: "작성요령 삭제", done: false, keep: true, busy: !!GD.busy, acts: [], text: "" };
  if (!both) { /* 준비가 먼저 */ }
  else if (C === undefined) guide.text = "지울 안내를 세는 중…";
  else if (C.error) Object.assign(guide, { text: `지울 안내를 세지 못했습니다: ${C.error}`, acts: [hBtn("다시 읽기", () => taskCleanupLoad(report))] });
  else {
    const n = C.counts || {};
    guide.done = (applyStep.done || !taskHasStage("map")) && !n.total; // 「내용 넣기」 가 없는 TASK(조립한 TASK)는 지울 안내가 없으면 끝
    guide.text = GD.busy ? "지우는 중…" : n.total ? `${taskCleanupText(n)} — 내용과 쓸 자리는 남깁니다(본문 색 ※ 줄은 내용으로 봄)`
      : GD.done ? `${taskCleanupText(GD.done, true)} · 남은 안내 없음` : "지울 안내가 없습니다";
    const list = hBtn("목록 보기", () => taskCleanupList(), { title: "지우는 패턴 목록과 지울 자리를 문서 옆 열에 보입니다 — 줄을 누르면 문서의 그 자리로" });
    guide.acts = n.total ? [onReport(GD.busy ? "지우는 중…" : "작성요령 삭제", () => taskCleanup(), { cls: "btn sm primary", disabled: !!GD.busy,
      title: `지우는 패턴(${cleanupNames()})에 걸린 양식 안내를 한 번에 지웁니다(확인 창 없이) — 편집 하나 · 실행 취소 한 번` }), list] : [list];
  }
  return [files, heads, headsLlm, config, division, reheads, reheadsLlm, link, planStep, applyStep, // 차례 = 묶음 넷(TASK_STAGES — §21): 문서 검토(files · heads · headsLlm) → 구성 맞추기(config · division · reheads · reheadsLlm) → 내용 넣기(link …) → 문서 정리(guide)
    { key: "later", no: "⑤", name: "합계 계산 → 결과 확인", done: false, soon: true, acts: [], // 2026-11-12 사용자 "합계 계산은 … 어디서 표시하는건지" — 아직 없는 단계라는 것과 지금 계산 칸이 어떻게 되는지를 줄에 적는다
      text: "아직 없는 단계입니다 — 넣은 값으로 합계·소계·비율 칸을 다시 세고 결과를 검사할 자리. 지금은 원본과 줄이 같은 합계 칸만 옮기고 나머지 계산 칸은 비워 둡니다(넣기 계획의 「계산 칸」)" },
    guide];
}

// ---- ② 자리 연결 — 연결 목록(spec_병합 ② §0·§0-1·§8 · API app/merge_api.py: GET/POST /api/docs/{연차보고서}/merge-links · PUT …/{묶음}). 화면 말은 「자리 연결」·「연결 목록」(「매칭」·「짝」 안 씀)
const LINK_STATUS = { paired: "연결됨", ambiguous: "확인 필요", toOnly: "후보 없음", fromOnly: "원본에만" }; // 묶음 상태 → 화면 말(원본 = 사업계획서)
const LINK_BADGE = { paired: "applied", ambiguous: "unsupported", toOnly: "already", fromOnly: "already" }; // 색은 구분 기준 목록의 꼬리표(.dv-badge)를 같이 쓴다
const LINK_REASON = { noHeadings: "헤딩·표 분석 없음", noValues: "프로젝트 구성 값 없음", notApplied: "프로젝트 구성 반영 전", unsupportedForm: "hwpx 문서가 아님", valuesDiffer: "프로젝트 구성 값이 사업계획서와 다름" };
const LINK_KIND = { paragraph: "본문", rows: "표 행", cols: "표 열", list: "목록 행" };
const linksFixedErr = (L) => ((L && L.fixed) || {}).error || ""; // 서버가 같은 이름 자리를 못 셈 — 「0」 이 아니라 「모름」: 넣기 계획은 세울 수 있게 둔다(거기서 까닭이 드러난다)
const linksFixedN = (L) => ((L && L.fixed) || {}).todo || 0; // 같은 이름 자리(구분 기준이 안 걸린 표지·요약문 칸 · 「[최종목표]」 같은 라벨)에 넣을 수 — 묶음 수와 따로 센다
// 「정상 0건」(spec_워크플로우 ② §15 — astra P1 ⓒ): 서버가 두 문서의 전제를 확인하고(막는 까닭 없음) 낸 연결 목록에 넣을 자리(이어진 묶음 · 같은 이름 자리)가 하나도 없다 — 「내용 넣기」 의 넣기 계획 · 내용 반영은
// 이것으로 끝난다(「대상 없음」 — 구성 맞추기 묶음이 이 TASK 에 있든 없든: 구조가 맞았는지는 서버의 까닭 notApplied · valuesDiffer 가 본다). 전제 없음(까닭이 있음 · 같은 프로젝트에서 문서를 못 찾음)과
// 판정 실패(목록을 못 읽음 · 같은 이름 자리를 못 셈 — linksFixedErr)는 0건이 아니다. 화면의 단계 셈(taskSteps 의 noTargets)과 「한 번에 진행」 의 성공 반환(taskRunMap)이 이것 하나를 쓴다
const linksNone = (L) => !!(L && !L.error && L.counts && L.from && L.to && !L.from.reasons.length && !L.to.reasons.length && !L.counts.paired && !linksFixedN(L) && !linksFixedErr(L));
const linksSameTables = (L) => { // 같은 표로 이은 표 짝(fixed.counts.tables — 그 가운데 LLM 이 이은 수 tablesLlm) → 「 · 같은 표 T(LLM t)」 | ""(없음 · 못 셈)
  const c = ((L && L.fixed) || {}).counts || {};
  return c.tables ? ` · 같은 표 ${c.tables}${c.tablesLlm ? `(LLM ${c.tablesLlm})` : ""}` : "";
};
const linksOpenTables = (L) => (((L && L.fixed) || {}).counts || {}).tablesOpen || 0; // 스크립트가 같은 표로 못 정한 목적 표 수(후보가 없는 표도 — LLM 검토가 원본 표를 모두 읽고 정한다: spec_병합 ② §5-1 「표 짝 검토」 2026-11-22)
const linksMapOpen = (L) => (((L && L.fixed) || {}).counts || {}).mapOpen || 0; // 같은 표로 이었는데 행·열 머리가 달라 칸을 못 맞춘 표 수 — 표 대응(LLM)이 맞춘다(spec_병합 ② §5-3)
const linksMapN = (L) => (((L && L.fixed) || {}).counts || {}).maps || 0; // 표 대응이 맡은 표 수
const linksCountText = (L) => Object.keys(LINK_STATUS).map((k) => `${LINK_STATUS[k]} ${L.counts[k] || 0}`).join(" · ") + (L.fixed ? ` · 같은 이름 자리 ${linksFixedErr(L) ? "못 셈" : linksFixedN(L)}` : "") + linksSameTables(L);

async function linksCall(report, opts = null, path = "") { // 읽기(opts 없음) · 다시 내기({method: "POST"}) · 사람 고침({method: "PUT", body}, "/묶음 id") → taskFlow.links. 끝나면 ② 줄과 열려 있는 목록을 다시 그린다
  const epoch = state.epoch, flow = taskFlow, seq = (flow.linkSeq = (flow.linkSeq || 0) + 1);
  flow.linkBusy = true;
  if (opts) linksRedraw();
  let got;
  try { got = await api(`/api/docs/${report.id}/merge-links${path}`, opts ? { method: opts.method, headers: H_JSON, body: JSON.stringify(opts.body || {}) } : {}); }
  catch (e) {
    if (opts) toast(`자리 연결을 바꾸지 못했습니다: ${e.message}`, true);
    got = opts && flow.links && !flow.links.error ? flow.links : { error: e.message, missing: e.status === 404 && e.message === "Not Found" }; // 고침이 실패하면 보던 목록 그대로 · 끝점이 없으면(서버 재시작 전) missing
  }
  if (epoch !== state.epoch || flow !== taskFlow || seq !== flow.linkSeq) return;
  flow.linkBusy = false;
  flow.links = got;
  linksRedraw();
}
function linksRedraw() { taskStepsDraw(); if (heads.dlg === "links") linksList(true); }

function linksList(keep = false) { // 2열 「자리 연결 — 연결 목록」(kind "links") — 묶음마다 한 줄: 상태 · 구분 · 연차보고서 자리 ← 사업계획서 자리(후보에서 고름) · 항목. 줄을 누르면 항목이 펴지고 문서의 그 자리로
  const L = taskFlow.links, report = taskSlotDoc("report"), plan = taskSlotDoc("plan");
  if (!L || L.error || !L.from || !report) { if (heads.dlg === "links") headsColClose(); else toast("연결 목록이 아직 없습니다"); return; }
  const mine = report.id === state.id ? "to" : plan && plan.id === state.id ? "from" : null; // 지금 문서가 어느 쪽인가 — 누르면 그쪽 자리로 간다
  const top = keep ? $("headsDlgBody").scrollTop : 0, busy = !!taskFlow.linkBusy, c = L.counts;
  if (keep) heads.keepFold = true; // 배경에서 다시 그릴 때 접어 둔 열은 그대로
  const { tools, body, foot } = headsDlg("links", "자리 연결 — 연결 목록", `${L.from.name} → ${L.to.name} · 줄을 누르면 항목이 펴지고 문서의 그 자리로`);
  heads.keepFold = false;
  if (!taskFlow.linkFilter) taskFlow.linkFilter = c.ambiguous ? "ambiguous" : "all"; // 처음에는 확인이 필요한 것부터
  const filt = el("span", "dv-filter");
  for (const k of ["all", ...Object.keys(LINK_STATUS)]) filt.append(hBtn(k === "all" ? `모두 ${L.groups.length}` : `${LINK_STATUS[k]} ${c[k] || 0}`,
    () => { taskFlow.linkFilter = k; linksList(); }, { cls: "btn sm" + (taskFlow.linkFilter === k ? " on" : "") }));
  tools.append(filt);
  const put = (g, bodyJson) => linksCall(report, { method: "PUT", body: bodyJson }, "/" + encodeURIComponent(g.id));
  const tail = (x) => (x.path || []).slice(-2).join(" › "), kind = (g) => LINK_KIND[g.kind] || g.kind;
  const place = (x, sample) => [tail(x), sample || x.label].filter(Boolean).join(" · ") || "(제목 없는 자리)";
  const go = (it) => { const id = mine && it && it[mine] && it[mine].id; if (id) divGo({ key: id }); if (it) { peerGo(plan, it.from && it.from.id); peerGo(report, it.to && it.to.id); } }; // 옆에 같이 보는 문서(② §12)도 이어진 자리로
  const open = (taskFlow.linkOpen ||= new Set());
  const [tbl, tb] = hTable(["상태", "구분", "연차보고서 자리 ← 사업계획서 자리", "항목"]);
  tbl.classList.add("lk-table");
  const rows = L.groups.filter((g) => taskFlow.linkFilter === "all" || g.status === taskFlow.linkFilter);
  for (const g of rows) {
    const tr = el("tr", "go"), tds = el("td"), tdp = el("td", "lk-place"), first = g.items[0], linked = g.items.filter((it) => it.status === "paired").length;
    tr.tabIndex = 0;
    tr.dataset.link = g.id;
    tr.dataset.status = g.status;
    tds.append(el("span", `dv-badge ${LINK_BADGE[g.status] || ""}`, LINK_STATUS[g.status] || (g.status === "outside" ? "범위 밖" : g.status))); // outside = 「넣을 구성 선택」 에서 고르지 않은 기관 · 단계 · 차년도의 묶음(spec_병합 ② §4-1 — 넣지 않는다 · 셈 글에는 넣지 않는다)
    if (g.source === "user") tds.append(" ", el("span", "dv-badge hinted", "고름")); // 사람이 고르거나 끊은 것 — 다시 내도 유지
    if (g.source === "llm") tds.append(" ", el("span", "dv-badge hinted", "LLM")); // LLM 검토가 이은 것 — 까닭은 도움말(reason), 사람이 바꿀 수 있다
    if (g.reason) tds.title = g.reason;
    tr.append(tds);
    hCell(tr, `${g.dimName} · ${kind(g)}`);
    if (g.to) {
      const toLine = el("div", "lk-to", place(g.to, first && first.to && first.to.text)), fromLine = el("div", "lk-from");
      toLine.title = (g.to.path || []).join(" › ");
      const sel = el("select");
      sel.setAttribute("aria-label", "사업계획서 자리 고르기");
      sel.append(new Option(g.candidates.length ? "(연결 안 함)" : "(후보 없음)", ""));
      const cands = g.from && !g.candidates.some((x) => x.key === g.from.key) ? [g.from, ...g.candidates] : g.candidates;
      for (const x of cands) { const o = new Option(place(x) + (x.score != null ? ` — 닮음 ${Math.round(x.score * 100)}` : ""), x.key); o.title = (x.path || []).join(" › "); sel.append(o); }
      sel.value = g.from ? g.from.key : "";
      sel.disabled = busy || !cands.length;
      sel.onclick = (e) => e.stopPropagation();
      sel.onchange = () => put(g, { from: sel.value || null });
      fromLine.append(el("span", "lk-arrow", "←"), sel);
      if (g.source === "user") { const b = hBtn("되돌리기", (e) => { e.stopPropagation(); put(g, { reset: true }); }, { disabled: busy, title: "사람이 고른 것을 지우고 스크립트가 낸 결과로" }); fromLine.append(b); }
      tdp.append(toLine, fromLine);
    } else {
      const only = el("div", "lk-to muted", "(연차보고서에 맞는 자리 없음)"), fromLine = el("div", "lk-from");
      fromLine.append(el("span", "lk-arrow", "←"), el("span", null, place(g.from)));
      fromLine.title = (g.from.path || []).join(" › ");
      tdp.append(only, fromLine);
    }
    tr.append(tdp);
    hCell(tr, g.items.length ? `${linked}/${g.items.length}` : "—", "dv-num", g.items.length ? `구분 값 항목 ${g.items.length}개 가운데 원본과 이어진 것 ${linked}개` : "");
    const toggle = () => { if (open.has(g.id)) open.delete(g.id); else open.add(g.id); go(first || { from: { id: g.from && g.from.key }, to: { id: g.to && g.to.key } }); linksList(true); };
    tr.onclick = toggle;
    tr.onkeydown = (e) => { if (e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); toggle(); } };
    tb.append(tr);
    if (open.has(g.id) && g.items.length) { // 펼친 항목 — 구분 값마다 한 줄(연차보고서 글 ← 사업계획서 글)
      const tr2 = el("tr", "lk-items"), td = el("td"), ul = el("ul");
      td.colSpan = 4;
      for (const it of g.items) {
        const li = el("li", it.status === "paired" ? null : "muted");
        li.append(el("strong", null, it.value), ` ${it.to ? it.to.text : "—"} ← ${it.from ? it.from.text : "(원본 없음)"}`);
        if (mine && it[mine]) { li.classList.add("go"); li.tabIndex = 0; li.onclick = () => go(it); li.onkeydown = (e) => { if (e.key === "Enter") go(it); }; }
        ul.append(li);
      }
      td.append(ul); tr2.append(td); tb.append(tr2);
    }
  }
  if (!rows.length) { const tr = el("tr"); const td = hCell(tr, "해당하는 묶음이 없습니다"); td.colSpan = 4; tb.append(tr); }
  body.append(tbl);
  $("headsDlgBody").scrollTop = top;
  foot.append(el("span", "muted", linksCountText(L) + linksLlmText(L)));
  if (c.ambiguous || c.toOnly) foot.append(linksLlmBtn(L));
  if (L.stale) foot.append(el("span", "hd-msg note", "고른 뒤 문서가 바뀌었습니다 — 고른 연결은 그대로입니다"));
  if (L.diff && L.diff.length) foot.append(el("span", "hd-msg", "두 문서의 프로젝트 구성 값이 다릅니다"));
  foot.append(hBtn(busy ? "읽는 중…" : "다시 내기", () => linksCall(report, { method: "POST" }), { disabled: busy, title: "두 문서의 자리 묶음을 다시 읽어 연결 목록을 새로 냅니다 — 사람이 고른 것은 유지" }), hBtn("닫기", () => headsColClose()));
}

// ---- ② LLM 검토(spec_병합 ② §4 — POST …/merge-links/llm): 못 정한 자리를 연차보고서의 챕터별(20쪽 이내)로 나눠 병렬로 Opus 에 묻는다. 사람이 누를 때만 돈다
const linksLlmText = (L) => (!L.llm ? "" : ` · LLM 검토함(${L.llm.units.filter((u) => u.call).length}단위${L.llm.units.some((u) => u.call && u.call.error) ? " — 일부 실패" : ""}${L.llm.tables && (L.llm.tables.paired || L.llm.tables.none) ? ` · 표 ${L.llm.tables.paired}개 이음 · ${L.llm.tables.none}개 비움` : ""}${L.llm.job ? " · 워크플로우 프롬프트 함께 보냄" : ""})`); // job = 함께 보낸 TASK 프롬프트(jobs/<할 일 키>.md — spec_작업 ② §13)
function linksLlmBtn(L, primary = false) { // primary = 지금 할 일(확인 필요가 있고 아직 검토 전 — taskSteps ②)
  return hBtn(taskFlow.llmBusy ? "LLM 검토 중…" : L.llm ? "LLM 다시 검토" : "LLM 검토", () => linksLlm(), { cls: "btn sm" + (primary ? " primary" : ""), disabled: !!(taskFlow.llmBusy || taskFlow.linkBusy),
    title: "못 정한 자리(확인 필요·후보 없음)와 표(같은 표인지 · 어느 기관·차년도의 표인지 — 두 문서의 표를 모두 읽고 정합니다)를 연차보고서의 챕터별(20쪽 이내)로 나눠 LLM(Opus)에 묻습니다 — 수십 초~1·2분. 사람이 고른 연결은 안 바꾸고, LLM 이 이은 것은 「LLM」 꼬리표로 보입니다. 판단 기준은 「지침」 에서 봅니다" });
}
async function linksLlm() {
  const report = taskSlotDoc("report"), flow = taskFlow;
  if (!report || flow.llmBusy) return;
  flow.llmBusy = true;
  toast("LLM 검토 — 못 정한 자리를 챕터별로 나눠 묻습니다(수십 초)");
  await linksCall(report, { method: "POST" }, "/llm");
  flow.llmBusy = false;
  if (flow !== taskFlow) return;
  if (flow.links && flow.links.llm) toast(`LLM 검토 끝 — ${linksCountText(flow.links)}`);
  linksRedraw();
}

// 표 대응(LLM) — spec_병합 ② §5-3: 같은 표로 이었는데 두 서식의 행·열 구성이 달라 칸을 못 맞춘 표를 표마다 LLM 에 물어 행 짝·열 짝을 받는다(POST …/merge-links/table-map — merge.json tableMaps 에 저장, 문서는 안 바뀜).
// 끝나면 연결 목록을 다시 읽고, 계획이 있었으면 다시 계획한다(대응이 맡은 표의 칸이 계획에 든다). quiet = 「한 번에 진행」 안에서(알림 글 없이). → 응답 | null(못 함).
async function fillMap({ quiet = false } = {}) {
  const report = taskSlotDoc("report"), flow = taskFlow, epoch = state.epoch;
  if (!report || report.id !== state.id || flow.mapBusy || (flow.fill || {}).busy) return null;
  flow.mapBusy = true;
  taskStepsDraw();
  if (!quiet) toast("표 대응 — 칸을 못 맞춘 표를 표마다 LLM 에 묻습니다(표마다 십수 초)");
  let res = null;
  try {
    await flushAll();
    res = await api(`/api/docs/${report.id}/merge-links/table-map`, JSON_POST({}));
  } catch (e) {
    if (flow === taskFlow) toast(`표 대응을 하지 못했습니다: ${e.message}`, true);
  }
  flow.mapBusy = false;
  if (epoch !== state.epoch || flow !== taskFlow) return res;
  if (res) {
    const bad = (res.tables || []).filter((t) => t.error);
    if (!quiet) toast(res.asked ? `표 대응 끝 — 표 ${res.mapped}/${(res.tables || []).length}개의 행·열을 맞췄습니다${bad.length ? ` · 못 맞춤 ${bad.length}(${bad[0].error})` : ""} — 「넣기 계획」 에 들어갑니다` : "표 대응이 필요한 표가 없습니다", !!(res.asked && !res.mapped));
    await linksCall(report); // mapOpen·maps 수를 지금 것으로
    if ((flow.fill || {}).plan && !quiet) await fillPlan(); // 열려 있던 계획은 대응 전 것 — 다시 센다
  }
  taskStepsDraw();
  return res;
}

// 빈 자리 검토(LLM) — spec_병합 ② §5-4: 묶음 짝·같은 이름 자리·표 대응이 못 채운 목적 자리(빈 표 · 글머리만 있는 칸 · 라벨만 있는 줄)를 모아 사업계획서의 어디에서 가져올지 묻는다
// (POST …/merge-links/gaps — merge.json gaps 에 저장, 빈 표에 고른 원본 표는 표 짝으로도. 문서는 안 바뀜). 끝나면 다시 계획한다. again = 이미 답이 있는 자리도 다시. quiet = 「한 번에 진행」 안에서. → 응답 | null.
async function fillGaps({ quiet = false, again = false } = {}) {
  const report = taskSlotDoc("report"), flow = taskFlow, epoch = state.epoch;
  if (!report || report.id !== state.id || flow.gapBusy || flow.mapBusy || (flow.fill || {}).busy) return null;
  flow.gapBusy = true;
  taskStepsDraw();
  if (!quiet) toast("빈 자리 검토 — 아직 빈 자리를 사업계획서에서 찾습니다(수십 초)");
  let res = null;
  try {
    await flushAll();
    res = await api(`/api/docs/${report.id}/merge-links/gaps`, JSON_POST({ again }));
  } catch (e) {
    if (flow === taskFlow) toast(`빈 자리 검토를 하지 못했습니다: ${e.message}`, true);
  }
  flow.gapBusy = false;
  if (epoch !== state.epoch || flow !== taskFlow) return res;
  if (res) {
    const got = (res.tables.paired || 0) + (res.slots.filled || 0), all = (res.found.tables || 0) + (res.found.slots || 0);
    if (!quiet) toast(all ? `빈 자리 검토 끝 — 빈 자리 ${all}곳 가운데 ${got}곳의 원본을 찾았습니다(표 ${res.tables.paired || 0} · 칸·줄 ${res.slots.filled || 0}) — 나머지는 비워 둡니다` : "빈 자리가 없습니다");
    await linksCall(report); // 표 짝이 늘었다(mapOpen·kept 를 지금 것으로)
    if (!quiet) await fillPlan(); // 찾은 자리를 넣기 계획에
  }
  taskStepsDraw();
  return res;
}
const fillGapNote = (res) => (res ? ` · 빈 자리 검토 ${(res.tables.paired || 0) + (res.slots.filled || 0)}/${(res.found.tables || 0) + (res.found.slots || 0)}` : " · 빈 자리 검토는 못 함(그 자리는 비워 둠)");

// ---- LLM 지침·프롬프트 보기(2열 kind "llmGuide" — spec_작업 ② §13, 2026-11-12 사용자 "각 LLM이 검토나 작업할때 '지침' 이나 프롬프트를 확인할 수 있으면 좋겠어"). 읽기만 한다(문서·작업은 안 바뀜).
// GET /api/docs/{문서}/llm-guide/{step} → {step, name, model(null = 기본 모델), parts[{key: contract|guide|job|form, title, text, source(저장소 기준 파일 경로 | ""), note}],
//   last: null | {at, units[{n, title, pages[a, b] | null, targets, chars, error, has(프롬프트가 저장돼 있나)}]}} · GET …/llm-guide/{step}/prompt?unit=N → {at, title, prompt, answer}.
// step = merge-links(자리 연결 LLM 검토 — 문서 = 연차보고서) · division-review(구분 기준 LLM 재검토) · division-missing(빠진 자리 검토). 끝점이 없으면(서버 재시작 전) 그렇게 알린다.
const LLM_GUIDE_STEPS = { "merge-links": "자리 연결 LLM 검토", "division-review": "구분 기준 LLM 재검토", "division-missing": "빠진 자리 검토", gather: "기관 작성 내용 LLM 검토", "table-map": "표 대응(LLM)", gaps: "빈 자리 검토(LLM)" }; // gather = 취합(문서 = 취합본 · ?part=<기관 문서> — spec_취합 ② §4-3)
const LLM_GUIDE_SWAP = { "division-review": "division-missing", "division-missing": "division-review" }; // 「구분 기준 자리 표시」 줄의 「지침」 하나로 두 검토의 지침을 오간다
const LLM_GUIDE_OPEN = new Set(["guide", "job"]); // 처음부터 펴 두는 절 — 사람이 관리하는 글(판단 지침 · TASK 프롬프트). 계약·양식 정보는 접어 둔다
function llmGuideBtn(step, docId, q = "") { // 「지침」 — 보통 단추(강조 아님: 강조 단추는 카드에 하나). q = 끝점에 붙일 질의(취합 「part=<기관 문서 id>」 — 기관 문서마다 다른 프롬프트)
  const b = hBtn("지침", () => llmGuideOpen(step, docId, q), { title: "이 LLM 검토에 함께 보내는 지침·워크플로우 프롬프트·양식 정보와 마지막으로 보낸 프롬프트를 봅니다" });
  b.dataset.llmGuide = step;
  return b;
}
async function llmGuideOpen(step, docId, q = "") {
  if (!docId) return;
  const { tools, body } = headsDlg("llmGuide", "LLM 지침 — " + (LLM_GUIDE_STEPS[step] || step), "이 LLM 검토에 함께 보내는 글과 마지막으로 보낸 프롬프트 · 보기만(문서는 안 바뀜)");
  const seq = heads.seq, epoch = state.epoch, alive = () => seq === heads.seq && epoch === state.epoch && heads.dlg === "llmGuide";
  const url = `/api/docs/${docId}/llm-guide/${step}`, swap = LLM_GUIDE_SWAP[step];
  const again = () => hBtn("다시 읽기", () => llmGuideOpen(step, docId, q), { title: "지침 파일을 고쳤거나 LLM 검토를 다시 돌린 뒤 — 지금 글로 다시 읽습니다" });
  if (swap) tools.append(hBtn(`「${LLM_GUIDE_STEPS[swap]}」 지침`, () => llmGuideOpen(swap, docId), { title: `${LLM_GUIDE_STEPS[swap]}에 보내는 지침·프롬프트로 바꿉니다` }));
  body.append(el("p", "hnote lg-msg", "읽는 중…"));
  let g;
  try { g = await api(url + (q ? `?${q}` : "")); }
  catch (e) {
    if (!alive()) return;
    body.replaceChildren(el("p", "hwarn lg-msg" + (e.status === 404 && e.message === "Not Found" ? "" : " fail"),
      e.status === 404 && e.message === "Not Found" ? "서버를 다시 시작한 뒤에 볼 수 있습니다(새 기능)" : `지침을 읽지 못했습니다: ${e.message}`));
    tools.append(again());
    return;
  }
  if (!alive()) return;
  $("headsDlgTitle").textContent = "LLM 지침 — " + (g.name || LLM_GUIDE_STEPS[step] || step);
  tools.append(el("span", "muted", `모델 ${g.model || "기본 모델"}`), again());
  body.textContent = "";
  const parts = g.parts || [];
  body.append(el("div", "lk-cap", `함께 보내는 글 ${parts.length}개 — 이 차례로 프롬프트에 들어갑니다(뒤에 그 실행의 자료가 붙음)`));
  if (!parts.length) body.append(el("p", "hnote lg-msg", "함께 보내는 글이 없습니다"));
  for (const p of parts) {
    const d = el("details", "lg-part"), s = el("summary");
    d.dataset.part = p.key || "";
    d.open = LLM_GUIDE_OPEN.has(p.key);
    s.append(el("strong", null, p.title || p.key || ""), el("span", "lg-src", p.source || "코드에 든 글"));
    d.append(s);
    const note = [p.note, p.source && LLM_GUIDE_OPEN.has(p.key) ? "이 파일을 고치면 다음 실행부터 적용됩니다" : ""].filter(Boolean).join(" · ");
    if (note) d.append(el("p", "lg-note", note));
    d.append(el("pre", "lg-text", p.text || "(빈 글)"));
    body.append(d);
  }
  const last = g.last, units = (last && last.units) || [];
  body.append(el("div", "lk-cap", "마지막으로 보낸 프롬프트" + (last && last.at ? ` — ${fmtWhen(Date.parse(last.at) / 1000)}` : "")));
  if (!last) { body.append(el("p", "hnote lg-msg", "아직 실행한 적 없음")); return; }
  if (!units.length) body.append(el("p", "hnote lg-msg", "보낸 단위가 없습니다"));
  for (const u of units) {
    const box = el("div", "lg-unit"), head = el("button", "lg-unit-head"), out = el("div", "lg-unit-body");
    const pages = Array.isArray(u.pages) ? `${u.pages[0] === u.pages[1] ? u.pages[0] : `${u.pages[0]}–${u.pages[1]}`}쪽 · ` : "";
    head.type = "button";
    head.dataset.unit = u.n;
    head.disabled = !u.has;
    head.setAttribute("aria-expanded", "false");
    head.title = u.has ? "누르면 이 단위에 보낸 프롬프트 전체와 답을 폅니다(다시 누르면 접음)" : "이 단위의 프롬프트는 저장돼 있지 않습니다(대상이 없어 부르지 않았거나 옛 실행)";
    head.append(el("strong", null, u.title || `단위 ${u.n}`), el("span", "lg-src", `${pages}대상 ${nf(u.targets || 0)}${u.chars ? ` · ${nf(u.chars)}자` : ""}${u.has ? "" : " · 보낸 글 없음"}`));
    if (u.error) head.append(el("span", "lg-err", `오류 — ${u.error}`));
    out.hidden = true;
    head.onclick = async () => {
      if (!out.hidden) { out.hidden = true; head.setAttribute("aria-expanded", "false"); return; }
      out.hidden = false;
      head.setAttribute("aria-expanded", "true");
      if (out.dataset.loaded) return;
      out.replaceChildren(el("p", "hnote lg-msg", "읽는 중…"));
      try {
        const r = await api(`${url}/prompt?unit=${encodeURIComponent(u.n)}${q ? `&${q}` : ""}`);
        if (!alive()) return;
        out.replaceChildren(el("p", "lg-note", `프롬프트 ${nf((r.prompt || "").length)}자`), el("pre", "lg-text", r.prompt || "(빈 글)"),
          el("p", "lg-note", "답"), el("pre", "lg-text", r.answer == null ? "(답 없음)" : JSON.stringify(r.answer, null, 2)));
        out.dataset.loaded = "1";
      } catch (e) {
        if (alive()) out.replaceChildren(el("p", "hwarn fail lg-msg", e.status === 404 ? "이 단위의 프롬프트가 저장돼 있지 않습니다" : `프롬프트를 읽지 못했습니다: ${e.message}`));
      }
    };
    box.append(head, out);
    body.append(box);
  }
}

// ---- ③ 넣기 계획 → ④ 내용 반영(spec_병합 ② §0-1 · §6 — POST …/merge-links/plan · …/apply). 계획은 문서를 안 바꾸고(2열 「넣기 계획」 에서 확인), 반영은 편집 하나(실행 취소 1)
const FILL_SKIP = { outside: "고르지 않은 구성", noSource: "원본 없음", occupied: "이미 글이 있음", tables: "양식 표가 있는 자리 — 표 칸으로", applied: "이미 넣음", changed: "넣은 뒤 원본이 바뀜", shape: "자리를 못 찾음", ambiguous: "기관 이름이 안 맞음", calc: "계산 칸(비워 둠)" };
const FILL_MODE = { fixed: "정해진 자리", append: "이어 넣기" };
const fillFixedText = (c) => (c ? ` · 같은 이름 자리 — 칸 ${c.cells || 0} · 라벨 내용 ${c.labels || 0}${c.pictures ? `(그림 ${c.pictures})` : ""}${c.flow ? ` · 표 쪽 나눔 맞춤 ${c.flow}` : ""}` : ""); // 고정 자리(spec_병합 ② §5-1) — 서버가 fixed 를 줄 때만
const fillMapText = (c) => (c && c.tables ? ` · 표 대응 — 표 ${c.tables} · 칸 ${c.cells || 0}${c.lines ? ` · 일정 선 ${c.lines}` : ""}${c.rows ? ` · 행 추가 ${c.rows}` : ""}` : ""); // 표 대응(spec_병합 ② §5-3)이 맡은 표의 몫
const fillGapText = (c) => (c && (c.cells || c.lines || c.blocks) ? ` · 빈 자리 — 칸 ${c.cells || 0} · 줄 ${c.lines || 0}${c.blocks ? ` · 라벨 아래 내용 ${c.blocks}` : ""}` : ""); // 빈 자리 검토(spec_병합 ② §5-4)가 원본 줄을 찾은 자리 · blocks = 라벨 줄 아래에 넣는 내용(② §5-6)
const fillSchedText = (c) => (c && c.tables ? ` · 일정 표 — 항목 ${(c.write || 0) + (c.rows || 0)}${c.rows ? `(행 추가 ${c.rows})` : ""}${c.done ? ` · 이미 있음 ${c.done}` : ""}` : ""); // 월별 일정 표(spec_병합 ② §5-7 — 스크립트): 그 차년도의 일정 표들에서 넣을 항목
const fillCountText = (p) => `본문 ${p.body.counts.todo || 0}항목 · 표 칸 ${p.tables.counts.cells || 0} · 행 추가 ${p.tables.counts.rows || 0}` + fillFixedText(p.fixed && p.fixed.counts) + fillMapText(p.maps && p.maps.counts) + fillSchedText(p.sched && p.sched.counts) + fillGapText(p.gaps && p.gaps.counts) + (p.todo ? "" : " — 넣을 것 없음");
const fillDoneText = (r) => `본문 블록 ${(r.body || {}).blocks || 0} · 표 칸 ${(r.tables || {}).filled || 0} · 행 추가 ${(r.tables || {}).rowsAdded || 0} · 템플릿 변환 ${(r.converted || {}).converted || 0}줄`
  + ((r.converted || {}).over ? ` · 넘친 레벨 ${r.converted.over}줄` : "") // 자리 템플릿보다 깊어 넘친 개요 줄(덮은 템플릿 그대로면 원본 모양 — spec_병합 ② §5-5)
  + (r.fixed ? ` · 같은 이름 자리 — 칸 ${r.fixed.filled || 0} · 라벨 내용 ${(r.fixed.labels || {}).items || 0}(블록 ${(r.fixed.labels || {}).blocks || 0})` : "")
  + ((r.maps || {}).filled || (r.maps || {}).lines || (r.maps || {}).rowsAdded ? ` · 표 대응 — 칸 ${r.maps.filled || 0}${r.maps.lines ? ` · 일정 선 ${r.maps.lines}` : ""}${r.maps.rowsAdded ? ` · 행 추가 ${r.maps.rowsAdded}` : ""}` : "")
  + ((r.sched || {}).filled || (r.sched || {}).rowsAdded ? ` · 일정 표 — 칸 ${r.sched.filled || 0} · 일정 선 ${r.sched.lines || 0}${r.sched.rowsAdded ? ` · 행 추가 ${r.sched.rowsAdded}` : ""}` : "") // 월별 일정 표(② §5-7)
  + ((r.gaps || {}).cells || (r.gaps || {}).lines || (r.gaps || {}).blocks ? ` · 빈 자리 — 칸 ${r.gaps.cells || 0} · 줄 ${r.gaps.lines || 0}${r.gaps.blocks ? ` · 라벨 아래 내용 ${r.gaps.blocks}` : ""}` : "")
  + ((r.tables || {}).shaped || (r.fixed || {}).shaped || (r.maps || {}).shaped ? ` · 칸 서식 맞춤 ${((r.tables || {}).shaped || 0) + ((r.fixed || {}).shaped || 0) + ((r.maps || {}).shaped || 0)}칸` : "") // 원본 칸의 글자 모양·문단 모양을 입힌 칸(spec_병합 ② §5 「칸 서식」)
  + ((r.fixed || {}).flowed ? ` · 표 쪽 나눔 맞춤 ${r.fixed.flowed}` : "") + (((r.fixed || {}).fitted || 0) + ((r.body || {}).fitted || 0) ? ` · 그림 폭 맞춤 ${((r.fixed || {}).fitted || 0) + ((r.body || {}).fitted || 0)}` : "")
  + (((r.tables || {}).skipped || 0) + ((r.fixed || {}).skipped || 0) ? ` · 반영 때 건너뜀 ${((r.tables || {}).skipped || 0) + ((r.fixed || {}).skipped || 0)}(계획 뒤 글이 생긴 칸 등)` : "")
  + ((r.dropped || []).length ? ` · 못 옮긴 것 ${r.dropped.length}(쪽 설정 등)` : "");
const fillConvertText = (c) => (c && (c.converted || c.over) ? `${c.converted ? ` · 템플릿 변환 ${c.converted}줄` : ""}${c.over ? ` · 넘친 줄 ${c.over}` : ""}` : ""); // 본문 항목의 템플릿 변환 미리보기(서버가 줄 때만 — spec_병합 ② §5-5 6)

async function fillPlan() {
  const report = taskSlotDoc("report"), flow = taskFlow, epoch = state.epoch;
  if (!report || report.id !== state.id || (flow.fill || {}).busy) return;
  flow.fill = { ...(flow.fill || {}), busy: true, busyStep: "plan" };
  taskStepsDraw();
  try {
    await flushAll(); // 고치던 글을 먼저 서버에 — 계획은 서버의 문서로 센다
    const p = await api(`/api/docs/${report.id}/merge-links/plan`, { method: "POST" });
    if (epoch !== state.epoch || flow !== taskFlow) return;
    flow.fill = { plan: p, done: null };
    fillList();
  } catch (e) {
    if (flow === taskFlow) flow.fill = { ...(flow.fill || {}), busy: false };
    toast(`넣기 계획을 세우지 못했습니다: ${e.message}`, true);
  }
  if (epoch === state.epoch) taskStepsDraw();
}

function fillList() { // 2열 「넣기 계획」(kind "fill") — 본문 항목(값 · 넣을 자리 · 넣을 것 · 상태) + 표(방식 · 칸 · 행 · 못 넣음). 줄을 누르면 문서의 그 자리로. 꼬리말의 「반영」 이 문서를 바꾼다
  const F = taskFlow.fill || {}, p = F.plan, L = taskFlow.links;
  if (!p) { if (heads.dlg === "fill") headsColClose(); else toast("넣기 계획이 아직 없습니다"); return; }
  const { tools, body, foot } = headsDlg("fill", "넣기 계획", `${L && L.from ? `${L.from.name} → ${L.to.name} · ` : ""}문서는 「반영」 을 눌러야 바뀝니다`);
  tools.append(el("span", "muted", fillCountText(p)));
  const byId = new Map(((L && L.groups) || []).map((g) => [g.id, g]));
  const where = (gid) => { const g = byId.get(gid), x = g && g.to; return x ? [(x.path || []).slice(-2).join(" › "), x.label].filter(Boolean).join(" · ") || "(제목 없는 자리)" : String(gid); }; // 묶음 id → 연차보고서 자리 글(연결 목록과 같은 꼴)
  const row = (tb, cells, key, muted) => { const tr = el("tr", key ? "go" : null); for (const [t, cls, title] of cells) hCell(tr, t, cls || null, title || ""); if (muted) tr.classList.add("muted"); if (key) { tr.tabIndex = 0; tr.onclick = () => divGo({ key }); } tb.append(tr); };
  const [t1, b1] = hTable(["값", "넣을 자리", "넣을 것", "상태"]);
  t1.classList.add("lk-table");
  for (const it of p.body.items) row(b1, [[it.value, "lk-nw"], [it.anchorText || "(라벨 바로 뒤)", null, where(it.group)],
    [it.skip ? "—" : `블록 ${it.blocks} — 문단 ${it.paragraphs} · 표 ${it.tables} · 그림 ${it.pictures}` + fillConvertText(it.convert)], [it.skip ? FILL_SKIP[it.skip] || it.skip : "넣음", null, it.detail || ""]], it.to, !!it.skip);
  if (!p.body.items.length) row(b1, [["이어진 본문 자리가 없습니다"]], null, true);
  const overEl = typeof mergeOverSection === "function" ? mergeOverSection({ docId: state.id, over: p.over, disabled: !!F.busy, go: (c) => { if (c.at) divGo({ key: c.at }); }, // 넘친 개요 레벨(spec_병합 ② §5-5 — merge_over.js): 처리를 고르면 계획을 다시 센다
    onChange: async () => { const top = $("headsDlgBody").scrollTop; await fillPlan(); if (heads.dlg === "fill") $("headsDlgBody").scrollTop = top; } }) : null;
  const [t2, b2] = hTable(["표 자리", "방식", "칸", "행 추가", "못 넣음"]);
  t2.classList.add("lk-table");
  for (const t of p.tables.tables) row(b2, [[where(t.group)], [FILL_MODE[t.mode] || t.mode || "", "lk-nw"], [String(t.cells || 0), "dv-num"], [String(t.rows || 0), "dv-num"], [String(t.skipped || 0), "dv-num"]], t.group, !(t.cells || t.rows));
  if (!p.tables.tables.length) row(b2, [["이어진 표 자리가 없습니다"]], null, true);
  const why = Object.entries(p.tables.counts.skipped || {}).filter(([, n]) => n).map(([k, n]) => `${FILL_SKIP[k] || k} ${n}`).join(" · ");
  body.append(el("div", "lk-cap", `본문 — 넣을 항목 ${p.body.counts.todo || 0}`), t1, ...(overEl ? [overEl] : []), el("div", "lk-cap", `표 — 칸 ${p.tables.counts.cells || 0}(계산 칸 ${p.tables.counts.calc || 0}) · 행 추가 ${p.tables.counts.rows || 0}${why ? ` · 못 넣음: ${why}` : ""}`), t2);
  if (p.fixed) { // 같은 이름 자리(고정 자리 — spec_병합 ② §5-1): 구분 기준이 안 걸린 표의 칸(머리 글이 같은 칸끼리) + 같은 제목 라벨의 내용(그림 포함). 못 넣은 칸은 까닭과 함께 아래 줄로
    const SK = { ...FILL_SKIP, ambiguous: "머리 글이 같은 칸이 여럿", tables: "양식 표가 있는 자리 — 넣지 않음", org: "기관이 다른 표", year: "차년도가 다른 표", shape: "행·열 머리가 달라 칸을 못 맞춤" }; // 묶음 쪽의 「기관 이름이 안 맞음」·「표 칸으로」 와 뜻이 다르다
    const c = p.fixed.counts, why3 = Object.entries(c.skipped || {}).filter(([, n]) => n).map(([k, n]) => `${SK[k] || k} ${n}`).join(" · ");
    const [t3, b3] = hTable(["같은 이름 자리", "넣을 것", "상태"]);
    t3.classList.add("lk-table");
    const scope = (x) => { const c = x.ctx || {}; return [c.org, c.year ? c.year + "차년도" : ""].filter(Boolean).join(" · "); }; // 그 표의 맥락 — 어느 기관·어느 차년도의 표인가(없으면 과제 전체)
    for (const t of p.fixed.tables) if (t.status === "paired" || t.status === "ambiguous" || t.why) row(b3, [[`표 — ${t.title || "(제목 없는 표)"}` + (scope(t) ? ` [${scope(t)}]` : "") + (t.source === "llm" ? " · LLM" : t.source === "user" ? " · 사람" : "")],
      [t.status === "paired" ? `칸 ${t.cells}` : "—", "lk-nw"],
      [t.status === "paired" ? (t.cells ? "넣음" : "넣을 것 없음") + (t.skipped ? ` · 못 넣음 ${t.skipped}` : "") + (t.flow ? " · 쪽 나눔 맞춤" : "") + (t.format ? " · 서식 확인" : "") : t.why ? `${SK[t.why]} — 비워 둠` : "같은 꼴 표가 여럿 — 비워 둠", null,
        (t.status === "paired" ? `원본 표: ${t.fromTitle || t.from} · 머리 글 겹침 ${Math.round(t.score * 100)}%` : t.reason || "") + (t.source !== "script" && t.reason ? `\n${t.source === "llm" ? "LLM" : "사람"}: ${t.reason}` : "")
        + (t.format ? `\n서식: ${t.format}` : "") + (t.flow ? "\n이 표는 쪽을 넘어 나뉘지 않아 긴 내용이 잘립니다 — 계획서 표처럼 나뉘게 바꿉니다" : "")]], t.to, !(t.status === "paired" && (t.cells || t.flow)));
    for (const it of p.fixed.labels) row(b3, [[`라벨 — ${it.title}`], [it.skip ? "—" : `블록 ${it.blocks} — 문단 ${it.paragraphs} · 표 ${it.tables} · 그림 ${it.pictures}`], [it.skip ? SK[it.skip] || it.skip : "넣음", null, it.detail || ""]], it.to, !!it.skip);
    for (const s of (p.fixed.skipped || []).filter((x) => x.why === "occupied").slice(0, 40)) row(b3, [["칸", "muted"], [s.detail], [SK[s.why] || s.why]], s.to, true);
    if (!b3.children.length) row(b3, [["같은 이름으로 이어진 자리가 없습니다"]], null, true);
    body.append(el("div", "lk-cap", `같은 이름 자리 — 표 ${c.tables || 0} · 칸 ${c.cells || 0}(서식 틀 채움 ${c.form || 0}) · 라벨 내용 ${c.labels || 0}${why3 ? ` · 못 넣음: ${why3}` : ""}`), t3);
  }
  if (p.maps && (p.maps.tables.length || p.maps.counts.open)) { // 표 대응(spec_병합 ② §5-3) — 서식이 달라 LLM 이 행·열을 맞춘 표: 「같은 표로 이음」 과 「내용이 들어감」 을 가른다(대응한 항목 · 칸 · 표시 · 늘릴 행 · 못 넣은 것)
    const MK = { occupied: "이미 글이 있음", name: "항목 이름이 안 맞음", calc: "계산 칸(비워 둠)", shape: "자리를 못 찾음", stale: "표가 바뀌어 대응이 낡음", org: "기관이 다름", example: "서식 예시가 아님" };
    const c = p.maps.counts, why4 = Object.entries(c.skipped || {}).filter(([, n]) => n).map(([k, n]) => `${MK[k] || k} ${n}`).join(" · ");
    const [t4, b4] = hTable(["표 대응(LLM)", "넣을 것", "상태"]);
    t4.classList.add("lk-table");
    for (const t of p.maps.tables) {
      const n = (t.cells || 0) + (t.lines || 0) + (t.rows || 0);
      row(b4, [[`표 — ${t.title || t.to}`], [t.stale ? "—" : `항목 ${t.records || 0} · 칸 ${t.cells || 0}${t.lines ? ` · 일정 선 ${t.lines}` : ""}${t.rows ? ` · 행 추가 ${t.rows}` : ""}`, "lk-nw"],
        [t.stale ? "표가 바뀌어 대응이 낡음 — 「표 대응(LLM)」 다시" : (n ? "넣음" : "넣을 것 없음(이미 넣었거나 빈 칸이 없음)") + (t.skipped ? ` · 못 넣음 ${t.skipped}` : ""), null, `원본 표: ${t.fromTitle || t.from || ""}`]], t.to, !n);
    }
    for (const id of p.maps.open || []) row(b4, [[`표 — ${id}`], ["—"], ["같은 표로 이었지만 행·열 구성이 달라 칸을 못 맞춤 — 「표 대응(LLM)」 이 맞춥니다"]], id, true);
    body.append(el("div", "lk-cap", `표 대응 — 표 ${c.tables || 0} · 칸 ${c.cells || 0}${c.lines ? ` · 일정 선 ${c.lines}` : ""}${c.rows ? ` · 행 추가 ${c.rows}` : ""}${c.open ? ` · 대응이 필요한 표 ${c.open}` : ""}${why4 ? ` · 못 넣음: ${why4}` : ""}`), t4);
  }
  if (p.sched && p.sched.tables.length) { // 일정 표(spec_병합 ② §5-7) — 월별 일정 표를 스크립트로: 그 차년도의 원본 일정 표들(기관마다) → 항목 · 계획 선 · 실적 선(LLM 없음)
    const c = p.sched.counts, [t6, b6] = hTable(["일정 표(스크립트)", "사업계획서의 표", "넣을 것", "상태"]);
    t6.classList.add("lk-table");
    for (const t of p.sched.tables) {
      const n = (t.write || 0) + (t.grow || 0);
      row(b6, [[`표 — ${t.title || t.to}`, null, `${t.year}차년도의 일정 — 「${t.plan}」 선${t.result ? ` · 「${t.result}」 선도 같게` : ""}`],
        [t.sources.map((x) => `${x.org || x.title} ${x.items}`).join(" · "), null, t.sources.map((x) => `${x.title} — 항목 ${x.items}${x.note ? `\n  ${x.note}` : ""}`).join("\n")],
        [`항목 ${t.items}${t.grow ? ` · 행 추가 ${t.grow}` : ""}`, "lk-nw"],
        [(n ? `넣음 ${n}` : "넣을 것 없음") + (t.done ? ` · 이미 있음 ${t.done}` : "") + (t.cleared ? ` · 예시 지움 ${t.cleared}` : "") + (t.skipped ? ` · 못 넣음 ${t.skipped}` : ""), null, "이름이 이미 있는 항목은 건드리지 않습니다(사람이 고친 선 · 달성도를 덮지 않음)"]], t.to, !n);
    }
    for (const s of p.sched.skipped || []) row(b6, [["표", "muted"], [""], ["—"], [s.detail]], s.table || null, true);
    body.append(el("div", "lk-cap", `일정 표 — 표 ${c.tables || 0} · 항목 ${c.items || 0}${c.rows ? ` · 행 추가 ${c.rows}` : ""}${c.done ? ` · 이미 있음 ${c.done}` : ""}${p.sched.error ? ` · 읽지 못함: ${p.sched.error}` : ""}`), t6);
  }
  if (p.gaps && (p.gaps.items.length || p.gaps.counts.open)) { // 빈 자리(spec_병합 ② §5-4) — 다른 길이 못 채운 칸·라벨 줄에 LLM 이 고른 사업계획서 줄의 글(그대로). 빈 표에 고른 원본 표는 위 「같은 이름 자리」·「표 대응」 줄에 든다
    const GK = { occupied: "이미 글이 있음", noSource: "원본 줄에 옮길 글이 없음", long: "내용이 길다 — 기관이 작성", object: "표·그림이 든 내용 — 기관이 작성", year: "차년도가 다른 내용", org: "기관이 다른 내용", done: "이미 넣음" };
    const c = p.gaps.counts, [t5, b5] = hTable(["빈 자리", "사업계획서의 자리", "넣을 것", "상태"]);
    t5.classList.add("lk-table");
    for (const it of p.gaps.items) row(b5, [[`${it.kind === "cell" ? "칸" : "줄"} — ${it.label || it.to}`], [it.fromText || it.from || "", null, "줄을 누르면 연차보고서의 그 자리로 갑니다"], [it.skip ? "—" : `${it.lines}줄`, "lk-nw"], [it.skip ? GK[it.skip] || it.skip : "넣음", null, it.detail || ""]], it.to, !!it.skip);
    if (!p.gaps.items.length) row(b5, [[c.open ? "아직 묻지 않았습니다 — 「빈 자리 검토(LLM)」" : "원본을 찾은 빈 자리가 없습니다"]], null, true);
    body.append(el("div", "lk-cap", `빈 자리 — 칸 ${c.cells || 0} · 줄 ${c.lines || 0}${c.blocks ? ` · 라벨 아래 내용 ${c.blocks}` : ""}${c.tables ? ` · 원본 표를 찾은 빈 표 ${c.tables}(위 표 줄에)` : ""}${c.open ? ` · 아직 안 물은 빈 자리 ${c.open}` : ""}`), t5);
  }
  foot.append(el("span", "muted", p.todo ? "실행 취소 한 번으로 되돌릴 수 있습니다" : "넣을 것이 없습니다"),
    hBtn(F.busy ? "반영 중…" : "반영", () => fillApply(), { cls: "btn sm primary", disabled: !p.todo || !!F.busy, title: "이 계획대로 연차보고서에 넣습니다 — 사업계획서는 안 바뀝니다" }), hBtn("닫기", () => headsColClose()));
}

async function fillApply({ quiet = false } = {}) { // quiet = 옛 인자(2026-11-18 부터 확인 창이 없다 — 「한 번에 진행」 이 그대로 넘긴다)
  const report = taskSlotDoc("report"), flow = taskFlow, F = flow.fill || {}, p = F.plan, epoch = state.epoch;
  if (!p || !p.todo || F.busy || !report || report.id !== state.id) return;
  // 확인 창 없이 바로 넣는다(2026-11-18 사용자 「이런 알람좀 주지마」 — 실행 취소 한 번으로 되돌림: design.md §18 「확인 창」)
  flow.fill = { ...F, busy: true, busyStep: "apply" };
  state.busy = true;
  refreshToolbar();
  taskStepsDraw();
  fillList();
  try {
    await flushAll();
    const r = await api(`/api/docs/${report.id}/merge-links/apply`, { method: "POST", headers: H_JSON, body: JSON.stringify({ planId: p.planId }) });
    if (epoch !== state.epoch) return;
    if (r.nothing) { toast("넣을 것이 없습니다"); flow.fill = {}; return; }
    applyEditState(r);
    flow.fill = { done: r };
    toast(`반영 — ${fillDoneText(r)}`);
    if (heads.dlg === "fill") headsColClose();
    await reloadDoc(); // 떨어진 자리 여러 곳이 바뀌어 문서를 다시 읽는다(구분 기준 반영과 같은 길)
  } catch (e) {
    if (flow === taskFlow) flow.fill = e.status === 409 ? {} : { ...F, busy: false }; // 409 = 계획 뒤 문서가 바뀜 — 계획을 버린다
    toast(e.status === 422 ? `표준 검사에 걸려 되돌렸습니다: ${e.message}` : `반영하지 못했습니다: ${e.message}`, true);
  } finally {
    state.busy = false;
    refreshToolbar();
    if (epoch === state.epoch) { taskStepsDraw(); if (heads.dlg === "fill") fillList(); }
  }
}

function taskStepsOf() { // 이 TASK 에 서는 단계와 그 상태 — 첫 안 끝난 단계가 「지금」(묶음을 넘어 하나). 저장하지 않는다(대시보드 dashRelayLive 가 이것으로 따로 센다 — 단추도 새로 받은 것)
  let open = true;
  taskStagesSync();
  const mine = new Set(TASK_STAGES.flatMap((g) => g.keys)), R = taskReviewDocs(); // 이 TASK 의 묶음에 든 단계만 — 조립한 TASK 에서 뺀 묶음의 단계가 「지금」 을 막지 않게
  if (!R.heads.length) mine.delete("heads"); // 할 문서가 없는 단계도 뺀다(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 등록부 custom() 이 그 단계를 안 세우는 것과 같게)
  if (!R.llm.length) mine.delete("headsLlm");
  return taskSteps().filter((s) => mine.has(s.key)).map((s) => {
    const st = s.soon ? "soon" : s.done ? "done" : open ? "now" : s.early ? "ready" : "todo"; // early = 앞 단계가 덜 끝나도 진행 가능, 다음 작업과 구별
    if (!s.done && !s.soon) open = false;
    return { ...s, st };
  });
}
function taskStepsCalc() { // 단계와 그 상태 — 두 묶음(1단계·2단계)이 같이 쓴다: 첫 안 끝난 단계가 「지금」(묶음을 넘어 하나)
  taskStepsLast = taskStepsOf(); // 셈한 단계는 묶음 머리(taskStageSync)도 쓴다
  return taskStepsLast;
}
function taskStepsEl(stage) { // 묶음 하나의 세부 목록. 순서 번호는 완료 뒤에도 유지 — 이름·명시적 상태 / 설명 / 단추를 나눠 정렬한다
  const ol = el("ol", "dv-flow-steps");
  ol.setAttribute("aria-label", `${stage.name} 세부 순서`);
  (taskStepsLast || taskStepsCalc()).filter((s) => stage.keys.includes(s.key)).forEach((s) => {
    const st = s.st, li = el("li");
    li.dataset.step = s.key;
    li.dataset.state = st;
    const body = el("div", "dv-flow-body"), title = el("div", "dv-flow-title");
    title.append(el("strong", null, s.name), el("span", "dv-flow-status"));
    body.append(title);
    if (st !== "todo" && s.text) body.append(el("div", "dv-flow-text", s.text));
    li.append(el("span", "dv-flow-no", s.no || "·"), body);
    if ((st === "now" || st === "ready" || (s.keep && st === "done")) && s.acts.length) { const acts = el("div", "dv-flow-acts"); acts.append(...s.acts); li.append(acts); } // keep = 완료 뒤에도 결과 확인·재계획 가능
    ol.append(li);
  });
  return ol;
}
function taskStepsDraw() { // 두 묶음의 세부 목록을 다시 그린다 — 묶음 머리(끝난 수 · 상태 줄 · 「한 번에 진행」)도 함께
  if (gatherOn()) return gatherStepsDraw(); // 취합 — 제 묶음 둘(gather.js)
  if (!document.getElementById("taskSteps") || !taskSlots()) return;
  taskStepsCalc();
  for (const stage of TASK_STAGES) { const box = document.getElementById(stage.dom), old = box && box.querySelector("ol.dv-flow-steps"); if (old) old.replaceWith(taskStepsEl(stage)); }
  taskStageSync();
}

// TASK의 길 찾기만 담당한다. 실행/완료 판정은 이관(taskSteps)·취합(gatherSteps)이 소유한다.
// items: {id, label, state: now|done|todo|run|halt, target: 요소|요소 id, note?}.
// 갱신할 때 버튼을 보존해 진행 중에도 키보드 초점이 사라지지 않는다.
function taskJourneyEl() {
  const nav = el("nav", "dv-journey");
  nav.setAttribute("aria-label", "워크플로우 진행 순서");
  nav.append(el("ol"));
  return nav;
}
function taskJourneySync(host, items) {
  if (!host) return;
  const list = host.querySelector("ol"), states = { now: "현재", done: "완료", todo: "대기", run: "진행 중", halt: "확인 필요" };
  const ids = items.map((item) => item.id).join(",");
  if (host.dataset.items !== ids) {
    list.replaceChildren(...items.map((item) => {
      const li = el("li"), b = el("button");
      b.type = "button";
      b.dataset.journey = item.id;
      b.append(el("span", "dv-journey-label"), el("span", "dv-journey-status"));
      li.append(b);
      return li;
    }));
    host.dataset.items = ids;
  }
  const current = ["run", "halt", "now"].map((state) => items.findIndex((item) => item.state === state)).find((i) => i >= 0);
  items.forEach((item, i) => {
    const b = list.children[i].firstChild, status = states[item.state] || states.todo;
    b.dataset.state = item.state;
    b.firstChild.textContent = item.label;
    b.lastChild.textContent = status;
    b.title = item.note || `${item.label} 위치로 이동`;
    if (i === current) b.setAttribute("aria-current", "step");
    else b.removeAttribute("aria-current");
    b.onclick = () => {
      const to = typeof item.target === "string" ? document.getElementById(item.target) : item.target;
      if (!to) return;
      if (to.tagName === "DETAILS") to.open = true;
      const focus = to.tagName === "DETAILS" ? to.querySelector("summary") : to.querySelector("select:not(:disabled), input:not(:disabled), button:not(:disabled)");
      to.scrollIntoView({ block: "nearest" });
      focus?.focus({ preventScroll: true });
    };
  });
}
function taskJourneyDraw(host = document.getElementById("taskFlow")) {
  if (!host || !taskStepsLast) return;
  const files = taskStepsLast.find((s) => s.key === "files"), prepared = !!files?.done;
  let available = prepared;
  const items = [{ id: "prepare", label: "준비", state: prepared ? "done" : "now", target: host.querySelector(".dv-flow-files"), note: "사업계획서와 연차보고서를 고르는 곳으로 이동합니다." }];
  for (const stage of TASK_STAGES) {
    const work = taskStageWork(stage), done = work.length > 0 && work.every((s) => s.done), box = host.querySelector(`#${stage.dom}`);
    const phaseState = box?.querySelector(".dv-phase-state")?.dataset.kind;
    const status = phaseState === "run" ? "run" : !available ? "todo" : phaseState === "halt" ? "halt" : done ? "done" : "now";
    items.push({ id: stage.id, label: `${stage.no} ${stage.short || stage.name}`, state: status, target: stage.dom,
      note: `${stage.name} — ${stage.does}. 눌러서 세부 순서를 확인합니다.` });
    available = available && done;
  }
  taskJourneySync(host.querySelector(".dv-journey"), items);
}

function taskFlowEl() { // 첫 카드 안 — 첨부 파일 칸(종류마다 한 줄) + 단계 목록. taskRow 가 넣는다
  const box = el("div", "dv-flow"), files = el("div", "dv-flow-files");
  box.id = "taskFlow";
  box.dataset.key = taskFlowKey();
  files.title = "첨부 파일 — 이 할 일에 드는 문서(앞의 것이 기준)";
  taskSlots().forEach((k, i) => { const lab = el("label"); lab.append(el("span", null, taskName("file", k) + (i ? "" : "(기준)")), taskSlot(k), taskSlotUp(k), taskSlotPeer(k)); files.append(lab); }); // 이름 · 문서 고르기 · 폴더(올리기) · 같이 보기(② §12)
  const stages = el("div", "dv-phases"); // 묶음 둘(1단계 · 2단계) — id 는 전의 단계 목록 것 그대로(「#taskSteps li」 가 두 묶음의 줄을 문서 차례로 준다)
  stages.id = "taskSteps";
  taskStepsCalc();
  stages.append(...TASK_STAGES.map((stage) => taskStageEl(stage)));
  const chain = taskChainEl(); // 여러 묶음 이어서 한 번에 — 첨부 파일 칸과 묶음 사이 한 줄
  box.append(taskJourneyEl(), files, chain, stages);
  taskJourneyDraw(box);
  taskChainSync(chain);
  return box;
}

// ---- 1단계 「문서 프레임 작성」 — 단계 묶음 · 한 번에 진행(spec_작업 ② §14, 2026-11-12 사용자 "이게 1단계로.. 문서 프레임 작성 하고 싶고, 한번에 모든 단계를 진행할 수 있는 버튼을 주고
// 내부에는 세부적으로 진행할 수 있는 세부 목록도 줘. 접었다 폈다 하면 나오게"). 묶음 = 접는 상자(details#taskStage): 머리 줄 「1단계 문서 프레임 작성 · 끝난 수 · [한 번에 진행]」 +
// 상태 줄(다음 할 일 · 도는 중 = 동그라미 + 지금 하는 일 + 지난 시간 · 멈춘 까닭) — 펴면 세부 목록(ol#taskSteps — 단계·단추는 전과 같다). 기본 접힘, 펴짐은 이 브라우저에 기억.
// 한 번에 진행(taskRunAll): 확인 창 없이(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 시작할 때 한 번: 11-12 사용자 답 「시작할 때 한 번만」) → 안 끝난 단계를 차례로 — 구분 기준 맞추기·반영 → 헤딩·표 분석(없는 문서만, 스크립트) → 자리 연결
// (확인 필요가 있고 검토 전이면 LLM 검토 한 번 — 사용자 답 「넣음」) → 넣기 계획 → 내용 반영. 사람 손이 필요한 곳·실패에서는 멈추고 세부 목록을 편다. 단계의 판정은 taskSteps() 그대로.
// **묶음은 둘**(같은 날 사용자 — 한 번에 진행한 결과를 보고 "지금 문서 프레임 작업인데 왜 내용을 넣지?" → 물어서 받은 답 「구조까지만」 · "2단계는 내용 넣고, 서식도 맞춰서 … 헤딩추출, 테이블
// 정보 추출등을 해서 매핑하는거야. 2단계는 내용 매핑이겠지"): 1단계 「문서 프레임 작성」 = 준비 + ① 구분 기준 확인·반영(구조), 2단계 「내용 매핑」 = ② 자리 연결(앞에 헤딩·표 분석) → ③ 넣기 계획 →
// ④ 내용 반영(서식 맞춤 포함). 묶음마다 「한 번에 진행」 — 2단계 것은 1단계가 끝나야 켜진다. 단계 번호·key 는 그대로(공통 차례 — spec_병합 ② §0-1).
// 2026-11-13(spec_작업 ② §18 — 사용자 "구분 기준만 추출하는 단계를 1, 프레임 작성 2, 내용 매핑 3"): 맨 앞에 1단계 「구분 기준」(준비 + 프로젝트 구성 추출 — 문서를 안 바꿈)을 더하고 번호를 하나씩 민다. 있던 묶음의 id·dom·store 는 그대로
// 2026-11-19(spec_작업 ② §21 — 사용자 "내용을 먼저 헤딩이랑 테이블 검토 작업을 하고, 프로젝트 구성 및 프레임 작성을 하고 다시 헤딩추출/테이블 작업을 하고 그 다음에 매핑 … 단계로 하면 구성 맞추기, 내용 넣기" ·
// "문서 검토 … 단계가 있어야 하겠구나"): **묶음 넷** — 1단계 「문서 검토」(준비 + 헤딩·표 분석) · 2단계 「구성 맞추기」(프로젝트 구성 추출 + ① 반영 + 헤딩·표 다시 분석) · 3단계 「내용 넣기」 · 4단계 「문서 정리」.
// 이름의 원본 = task_catalog.js RELAY_STAGE_META(취합은 TASK_STAGE_META 그대로). 전의 config 묶음(#taskStage0)은 없어지고 그 구성 입력 칸은 frame 묶음(#taskStage) 안으로 — frame·map·clean 의 id·dom·store 는 그대로
const RELAY_STAGES = [
  { id: "review", ...RELAY_STAGE_META.review, keys: ["files", "heads", "headsLlm"], dom: "taskStageR", store: "nfm.taskStageOpenR", short: "문서 검토", noReset: true,
    does: "두 문서의 헤딩·표 분석(없는 문서만 — 스크립트) → 양식의 작성 지침을 헤딩/표별로 저장 → 원본 문서(사업계획서)의 LLM 검증·보완(유료 · 몇 분 — LLM 을 쓸 수 없으면 건너뜀) · 문서는 안 바뀜" },
  { id: "frame", ...RELAY_STAGE_META.frame, keys: ["config", "division", "reheads", "reheadsLlm"], dom: "taskStage", store: "nfm.taskStageOpen", short: "구성 맞추기",
    does: "프로젝트 구성 추출(사업계획서에서 추출하거나 불러와 프로젝트에 저장 — 「구성 불러오기」 는 선택) → 프로젝트 구성 반영(절·표 행·열 — 구조만) → 다시 문서 검토(구조를 맞춘 문서의 헤딩·표 다시 분석 → LLM 검증·보완)" },
  { id: "map", ...RELAY_STAGE_META.map, keys: ["link", "plan", "apply", "later"], dom: "taskStage2", store: "nfm.taskStageOpen2", short: "내용 넣기", does: "자리 연결(LLM 검토 포함) → 넣기 계획 → 내용 반영(서식 맞춤)" },
  // 4단계 「문서 정리」(2026-11-12 사용자 "3단계에 작성요령 삭제 기능을 넣어줘" — 11-13 번호 4): ⑥ 작성요령 삭제 하나 — 초기화 단추는 없다(지운 작성요령은 구성 맞추기·내용 넣기 초기화가 원본으로 되돌린다)
  { id: "clean", ...RELAY_STAGE_META.clean, keys: ["guide"], dom: "taskStage3", store: "nfm.taskStageOpen3", short: "문서 정리", get does() { return `작성요령 삭제(지우는 패턴 — ${cleanupNames()} · 내용은 남김 · 지우기 전에 작성 지침을 저장)`; }, noReset: true },
];
// 지금 TASK 의 묶음 — 붙박이 이관은 넷 모두, **화면에서 조립한 TASK**(task_catalog.js taskCatalogCustom — spec_워크플로우 ② §14: 2026-11-19 사용자 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」)는
// 고른 묶음만 선다(번호는 1부터 다시 · 맨 앞 묶음이 「준비」 를 가진다). 배열 하나의 내용을 갈아 끼운다 — TASK_STAGES 를 읽는 곳은 그대로다. 단계를 셈할 때마다 맞춘다(taskStepsCalc · taskRunAll · 대시보드)
const TASK_STAGES = RELAY_STAGES.slice();
let taskStagesFor = ""; // TASK_STAGES 가 맞춰진 TASK 키
function taskStagesSync() {
  const job = (state.task || {}).job || "", cat = TASK_CATALOG[job] || {};
  if (taskStagesFor === job) return;
  taskStagesFor = job;
  const pick = cat.custom ? RELAY_STAGES.filter((g) => (cat.groups || []).includes(g.id)) : RELAY_STAGES;
  // 조립한 워크플로우의 묶음 설명 = 서버가 실제 배정에서 만든 글(cat.does[묶음 id] — 등록부 custom() 과 같은 글: spec_워크플로우 ② §15) · 옛 서버(does 를 안 보냄)면 「문서 검토」 만 문서마다 고른 대로(taskReviewDoes) · 그 밖은 붙박이의 글
  const does = (g) => { const d = (cat.does || {})[g.id]; return typeof d === "string" && d.trim() ? d : g.id === "review" && cat.assign ? taskReviewDoes(job) : ""; };
  TASK_STAGES.length = 0;
  TASK_STAGES.push(...(cat.custom ? pick.map((g, i) => { const d = does(g); return Object.create(g, { no: { value: `${i + 1}단계`, enumerable: true },
    keys: { value: i === 0 && !g.keys.includes("files") ? ["files", ...g.keys] : g.keys, enumerable: true }, ...(d ? { does: { value: d, enumerable: true } } : {}) }); }) : pick));
}
// 조립한 워크플로우의 정의를 서버에서 다시 읽는다(spec_워크플로우 ② §15 「실행」 — 열어 둔 화면의 정의가 그 사이 바뀌거나 지워졌을 수 있다: 다른 탭의 「워크플로우 조립」).
// 부르는 때: ① 그 키를 지금 워크플로우로 고를 때(taskSetNow · 대시보드 dwfSelect) ② 사람이 실행을 시작할 때(taskRunAll) ③ 에이전트 턴(doc_agent_work.js agwStatus 의 fresh). 붙박이 워크플로우는 다시 읽지 않는다.
// GET /api/tasks 로 목록을 다시 담고(taskCatalogCustom — broken 도) 그 키의 단계 표지(task_catalog.js taskSigSame — 서버의 sig, 없으면 배정 · 단계로 지은 것)를 전의 것과 견준다.
// → null(다시 읽지 않음 · 못 읽음 — 옛 서버 · 끊김: 지금처럼 돈다) | {gone(목록에 없음), changed(있는데 단계가 바뀜), moved(이번에 읽어 달라짐 — 전부터 없던 것은 아님), why}.
// 바뀌었거나 없어졌으면 그 자리에서 다시 그린다(묶음 · 「작업 개요」 · 대시보드의 단계 흐름) — 실행을 막는 것은 부른 쪽이다
const TASK_DEF_CHANGED = "이 워크플로우의 단계가 바뀌어 다시 읽었습니다 — 바뀐 단계를 보고 다시 누르세요"; // 실행을 누른 뒤 알았다 — 실행하지 않는다
const TASK_DEF_PICKED = "이 워크플로우의 단계가 바뀌어 다시 읽었습니다 — 바뀐 단계를 보고 진행하세요"; // 고를 때 알았다 — 고르는 것은 그대로(새 정의로 그린다)
const TASK_DEF_GONE = "이 워크플로우는 지워졌습니다 — 다른 워크플로우를 고르세요";
let taskRunChecking = false; // taskRunAll 이 시작하기 전에 정의를 다시 읽는 중 — 그동안 또 눌러 둘이 시작하지 않게
async function taskCatalogRefresh(job) {
  if (!taskCustomKey(job) || taskRun) return null; // 도는 실행은 시작할 때의 정의로 끝까지 간다(도중에 묶음을 갈아 끼우지 않는다)
  let data = null;
  try { data = await api("/api/tasks?v=2"); } catch (e) { console.warn("조립한 워크플로우 목록을 다시 읽지 못했습니다", e); return null; } // v=2 = 줄 목록 정의(조립 v2)까지 — 판 없이 읽으면 표준 정의만(옛 탭용: spec_워크플로우 ② §18-12 ⑤)
  if (!data || !Array.isArray(data.tasks) || taskRun) return null;
  const was = TASK_CATALOG[job] || null;
  taskCatalogCustom(data.tasks, { broken: !!data.broken });
  const now = TASK_CATALOG[job] || null, moved = !was !== !now || (!!was && !!now && !taskSigSame(was, now));
  if (moved) {
    if (job === ((state.task || {}).job || "")) { taskStagesFor = ""; taskStagesSync(); taskStepsLast = null; if (dv.view) { divRender(); taskFlowLoad(); } } // 지금 워크플로우 — 묶음 · 「작업 개요」 를 새 정의로(없어졌으면 칸 · 묶음 없이 까닭 한 줄)
    if (typeof dashCatalogChanged === "function") dashCatalogChanged(); // 대시보드의 단계 흐름(등록부 GET /api/workflow — 조립한 정의가 든다)도 다시 읽는다
  }
  return { gone: !now, changed: !!now && moved, moved, why: !now ? (taskCatalogBroken ? taskLostWhy(job) : TASK_DEF_GONE) : moved ? TASK_DEF_CHANGED : "" };
}
const taskHasStage = (id) => TASK_STAGES.some((g) => g.id === id); // 이 TASK 에 그 묶음이 있나(조립한 TASK 는 고른 것만)
const taskStageName = (id) => { const g = TASK_STAGES.find((x) => x.id === id); return g ? `${g.no} 「${g.name}」` : `「${RELAY_STAGE_META[id].name}」`; }; // 묶음을 가리키는 글 — 이 TASK 에 없는 묶음은 번호 없이
// 「문서 검토」 의 단계마다 할 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 2026-11-19 사용자 "워크플로우에서 task 정할때 목적문서랑 원본문서에 대해서 각각 task 를 할당할 수 있도록"):
// → {heads: [칸 키…], llm: [칸 키…]} — 칸 키 = 첨부 파일 칸(그 TASK 의 files: 앞 = 원본 문서 · 뒤 = 목적 문서). 문서마다의 셈은 이 함수 하나다(단계 셈 taskStepsOf · 「한 번에 진행」 · 대시보드 · 에이전트가 같이 쓴다).
// 붙박이 이관(assign 없음) = 「헤딩 · 표 분석」 두 문서 · 「LLM 검증·보완」 원본(전과 같다). 화면에서 조립한 TASK(TASK_CATALOG[job].assign — task_catalog.js) = 「헤딩 · 표 분석」 은 「문서 검토」 를 고른 문서만 ·
// 「LLM 검증·보완」 은 저장된 배정의 llm(문서 역할 — 서버 app/custom_tasks.py 가 정한다: 옛 정의는 원본만 · 배정을 고쳐 저장하면 원본(골랐으면) + 목적(「문서 검토」 를 골랐고 「구성 맞추기」 는 안 골랐을 때) — astra P1 ⓐ)
// 가운데 「문서 검토」 를 고른 문서. llm 을 안 보내는 옛 서버면 그 규칙을 여기서 셈한다. 할 문서가 없는 단계는 그 TASK 에 서지 않는다(taskStepsOf)
function taskReviewDocs(job = (state.task || {}).job || "") {
  const cat = TASK_CATALOG[job] || {}, [S, T] = cat.files || ["plan", "report"], A = cat.assign, has = (list, id) => Array.isArray(list) && list.includes(id);
  if (!A) return { heads: [S, T], llm: [S] };
  const src = has(A.source, "stage_review"), tgt = has(A.target, "stage_review");
  const llm = Array.isArray(A.llm) ? [...(src && A.llm.includes("source") ? [S] : []), ...(tgt && A.llm.includes("target") ? [T] : [])]
    : [...(src ? [S] : []), ...(tgt && !has(A.target, "stage_fit") ? [T] : [])];
  return { heads: [...(src ? [S] : []), ...(tgt ? [T] : [])], llm };
}
const taskReviewOf = (plan, report) => { // taskReviewDocs → 이관의 함수들(taskSteps · taskRunSteps)이 쓰는 꼴 {heads: [[문서, 이름]…], llm: […]} — plan · report = 두 칸의 문서(taskSlots 의 차례)
  const R = taskReviewDocs(), slots = taskSlots() || [], duo = [[plan, "사업계획서"], [report, "연차보고서"]], pick = (ks) => duo.filter((x, i) => ks.includes(slots[i]));
  return { heads: pick(R.heads), llm: pick(R.llm) };
};
function taskReviewDoes(job) { // 조립한 TASK 의 「문서 검토」 묶음 설명(묶음 머리 · 「한 번에 진행」 의 풍선 도움말 · 에이전트의 실행 카드) — 문서마다 고른 대로. 두 문서 분석 + 원본 LLM 이면 붙박이 이관의 글(RELAY_STAGES)과 같다
  const [S, T] = (TASK_CATALOG[job] || {}).files || ["plan", "report"], R = taskReviewDocs(job);
  const who = (ks) => (ks.length > 1 ? "두 문서" : ks[0] === T ? `목적 문서(${taskName("file", T)})` : `원본 문서(${taskName("file", S)})`);
  return `${who(R.heads)}의 헤딩·표 분석(없는 문서만 — 스크립트)${R.heads.includes(T) ? " → 양식의 작성 지침을 헤딩/표별로 저장" : ""}`
    + `${R.llm.length ? ` → ${who(R.llm)}의 LLM 검증·보완(유료 · 몇 분 — LLM 을 쓸 수 없으면 건너뜀)` : ""} · 문서는 안 바뀜`;
}
let taskStepsLast = null; // 마지막으로 셈한 단계(taskStepsCalc — 상태 st 포함) — 묶음 머리가 다시 세지 않게
let taskRun = null; // 한 번에 진행 — 도는 중 {stage 지금 도는 묶음 id(이어 진행이면 묶음마다 바뀜), report 연차보고서 id, key 지금 단계, note 지금 하는 일, t0 그 묶음을 시작한 때, stop 멈춤 요청, timer, chain 이어 진행이면 {to 끝 묶음 id, label 「1→3단계」} · 아니면 null}
let taskRunLast = null; // 마지막 실행의 끝 {stage, report, ok, key, text, done 그때 그 묶음의 끝난 단계 수} — 마지막으로 돈 묶음의 것(화면 검사가 읽는다)
let taskRunEnds = {}; // 묶음 id → 그 묶음의 끝(taskRunLast 와 같은 꼴) — 상태 줄에 남긴다(이어 진행의 앞 묶음 끝 글도 · 그 뒤 단계가 더 나아가면 안 보임)
class TaskHalt extends Error {} // 멈춤(사람 손이 필요함 · 실패) — 글이 상태 줄에 그대로 보인다
const taskHalt = (msg) => { throw new TaskHalt(msg); };
const taskWait = async (ok, ms = 60000, every = 200) => { for (const t0 = Date.now(); !ok();) { if (Date.now() - t0 > ms) return false; await new Promise((r) => setTimeout(r, every)); } return true; };
const taskStageOpen = (stage) => { try { return localStorage.getItem(stage.store) === "1"; } catch { return false; } };
const taskStepName = (s) => (s ? `${s.no ? s.no + " " : ""}${s.name}` : "");

function taskStageEl(stage) { // 묶음 상자 하나 — taskFlowEl 이 넣는다(1단계 #taskStage · 2단계 #taskStage2). 머리 줄·상태 줄의 내용은 taskStageSync
  const box = el("details", "dv-phase"), sum = el("summary"), st = el("span", "dv-phase-state"), spin = el("i", "dv-phase-spin"), run = el("button", "btn sm", "한 번에 진행"), progress = el("progress", "dv-phase-progress"); // 클래스는 dv-phase-*(dv-stage-* 는 구분 기준의 「단계」 줄이 쓴다)
  box.id = stage.dom;
  box.dataset.stage = stage.id;
  box.open = taskStageOpen(stage);
  box.ontoggle = () => { try { localStorage.setItem(stage.store, box.open ? "1" : "0"); } catch { /* 기억만 안 함 */ } taskStageSync(); };
  run.type = "button";
  run.dataset.taskRun = stage.id;
  run.onclick = (e) => { e.preventDefault(); e.stopPropagation(); if (taskRun) { if (taskRun.stage === stage.id) { taskRun.stop = true; taskStageSync(); } } else taskRunAll(stage.id); }; // summary 안이라 — 누름이 접기·펴기로 넘어가지 않게
  const reset = stage.noReset ? null : el("button", "btn sm dv-phase-reset", "초기화"); // 묶음을 처음으로(taskReset) — 연차보고서는 올린 원본이 있다
  if (reset) {
    reset.type = "button";
    reset.dataset.taskReset = stage.id;
    reset.onclick = (e) => { e.preventDefault(); e.stopPropagation(); taskReset(stage.id); };
  }
  spin.style.animationDelay = `-${Date.now() % 800}ms`; // 카드를 다시 그려도 동그라미가 처음부터 다시 돌지 않게(각도를 시계에 맞춤 — design.md §7)
  spin.hidden = true;
  st.append(spin, el("span")); // role=status 를 달지 않는다 — 도는 동안 1초마다 글이 바뀌어 화면 낭독이 초마다 읽는다(시작·끝·멈춤은 알림 글 toast 가 알린다)
  sum.title = "세부 목록 펴기·접기 — 단계마다 따로 진행할 수 있습니다";
  progress.setAttribute("aria-label", "세부 작업 완료");
  sum.append(el("span", "dv-phase-no", stage.no), el("strong", null, stage.name), hHelp(`${stage.name} 안내`, stage.does + ". 세부 목록을 펴서 단계마다 진행할 수 있습니다.", { note: true }), el("span", "dv-phase-count"), run, ...(reset ? [reset] : []), progress, st);
  box.append(sum, taskStepsEl(stage));
  if (stage.id === "frame") { // 2단계 「구성 맞추기」: 머리에 프로젝트 구성(단계·차년도 · 기관) 값 요약 한 줄(접혀 있어도 보임) + 펴면 세부 목록 아래에 구성 입력(divRender 가 만든 #taskFrameForm — spec_작업 ② §18 · §21: 전에는 1단계 「프로젝트 구성」 묶음 안)
    const frame = el("span", "dv-phase-frame"), edit = el("button", "btn sm", "프로젝트 구성 고치기");
    frame.hidden = true;
    edit.type = "button";
    edit.dataset.taskFrameEdit = "1";
    edit.title = "이 묶음을 펴고 프로젝트 구성 입력(불러오기·확정 · 단계·차년도 · 기관 구성)으로 갑니다";
    edit.onclick = (e) => { e.preventDefault(); e.stopPropagation(); taskFrameEdit(box); }; // summary 안이라 — 누름이 접기·펴기로 넘어가지 않게
    frame.append(el("span", "dv-phase-frame-text"), edit);
    sum.append(frame);
    if (taskFrameForm && taskFrameForm.isConnected) box.append(taskFrameForm); // 칸만 다시 그릴 때(loadWorks) — 입력 중인 폼 노드를 그대로 옮긴다(다시 만들지 않음)
  }
  if (stage.id === "frame" && taskFrameApply && taskFrameApply.isConnected) box.append(taskFrameApply); // 구성 입력 아래 = 문서 반영 상태 · 변경 계획 보기(+ 자리 표시 · 지원 양식) — 같은 까닭으로 그대로 옮긴다
  taskStageSync(stage, box);
  return box;
}

// 1단계 묶음 안의 과제 구성 입력(spec_작업 ② §14, 2026-11-12 사용자 "1단계에서는 단계, 차년도, 기관구성이 들어가야 하지 … 저장하고 관리할 수 있어야 하는데 UI가 너무 떨어져 있네"):
// 이관이면 divRender 가 만든 입력 묶음(저장한 프로젝트 구성 · 단계·차년도 · 기관 구성 · 추가 설정 · 문서 반영 상태 · 변경 계획 보기)을 1단계 묶음(#taskStage)의 세부 목록 아래 #taskFrameForm 에 둔다.
// taskStepsDraw 는 ol 만 바꾸므로 이 노드는 입력 중에도 그대로다(포커스 유지). 이관이 아니면 전처럼 패널(#divBox)에 바로.
let taskFrameForm = null; // 지금 패널의 #taskFrameForm(divRender 가 정함 — 없으면 null) — 1단계 「구분 기준」 묶음 안의 구성 입력
let taskFrameApply = null; // 지금 패널의 #taskFrameApply — 2단계 「문서 프레임 작성」 묶음 안의 문서 반영 상태 · 변경 계획 보기(spec_작업 ② §18)
function taskFrameHost(box) { // divRender 가 부른다 — 구성 입력을 붙일 곳(이관·취합 = 1단계 묶음 안의 새 칸, 아니면 box 그대로)
  const stage = taskSlots() ? box.querySelector("#taskStage") : gatherOn() ? box.querySelector("#gatherStage0") : null; // 이관 = 2단계 「구성 맞추기」 묶음 안(§21 — 반영 상태·변경 계획 #taskFrameApply 가 그 아래) · 취합 = 1단계 묶음 안(gather.js 의 #gatherStage0)
  if (!stage) return box;
  const host = el("div", "dv-phase-form"), head = el("div", "dv-phase-form-head"), mine = (taskSlots() || []).find((k) => (taskSlotDoc(k) || {}).id === state.id);
  host.id = "taskFrameForm";
  head.append(el("strong", null, "프로젝트 구성 — 단계·차년도 · 기관"),
    hHelp("프로젝트 구성 안내",`지금 문서${mine ? `(${taskName("file", mine)}${mine === "plan" ? " — 기준" : ""})` : ""}의 프로젝트 구성(단계·차년도 · 기관)입니다. 같은 프로젝트의 워크플로우들이 같이 쓰고, 「프로젝트에 저장」 으로 확정해야 ${taskSlots() ? "프로젝트 구성 반영으로" : "2단계(문서 프레임 작성)로"} 갑니다.\n「프로젝트 구성 불러오기」 — 이 프로젝트에 확정한 구성 · 문서에서 추출(이 프로젝트 문서 · 파일 올리기) · 다른 프로젝트 · 저장한 프로젝트 구성.`, { note: true }));
  host.append(head);
  stage.append(host);
  taskFrameForm = host;
  return host;
}
function taskFrameApplyHost(box) { // divRender 가 부른다 — 문서 반영 상태 · 변경 계획 보기를 붙일 곳(2단계 묶음 안) | null(묶음이 없음 — box 에 그대로)
  const stage = taskSlots() ? box.querySelector("#taskStage") : gatherOn() ? box.querySelector("#gatherStage") : null;
  if (!stage) return null;
  const host = el("div", "dv-phase-form"), head = el("div", "dv-phase-form-head");
  host.id = "taskFrameApply";
  head.append(el("strong", null, "구조 반영 — 확정한 프로젝트 구성으로"), hHelp("구조 반영 안내", `${taskSlots() ? "위에서" : "1단계에서"} 확정한 프로젝트 구성(단계·차년도·기관)에 맞춰 이 문서의 절·표 행·열을 늘리고 줄입니다. 변경 계획을 보고 「반영」 을 눌러야 문서가 바뀝니다.`, { note: true }));
  host.append(head);
  stage.append(host);
  taskFrameApply = host;
  return host;
}
function taskFrameEdit(box) { // 「프로젝트 구성 고치기」 — 1단계를 펴고 첫 입력(저장한 프로젝트 구성 고르기, 없으면 첫 단계의 차년도 수)으로
  box.open = true;
  const to = taskFrameForm && taskFrameForm.isConnected && (taskFrameForm.querySelector(".dv-presets select:not(:disabled)") || taskFrameForm.querySelector(".dv-year-field input"));
  if (!to) return;
  to.scrollIntoView({ block: "center" });
  to.focus({ preventScroll: true });
}
function taskFrameText() { // 프레임 값 요약 — 기준 값(사업계획서 값, 아직 없으면 연차보고서 값) → {text, title} · 값이 없으면 text ""
  const [plan, report] = (taskSlots() || []).map((k) => taskSlotDoc(k));
  const A = plan ? taskDivOf(plan, true) : null, B = report ? taskDivOf(report) : null;
  const from = A && A.values ? (A.read ? "사업계획서 — 문서에서 읽음" : "사업계획서 — 기준") : B && B.values ? "연차보고서 입력 값" : "", v = from ? (A && A.values) || B.values : null;
  if (!v) return { text: "", title: "" };
  let start = 1;
  const stages = (v.stages || []).map((n, i) => { const y = Number(n) || 1, s = `${i + 1}단계(${y === 1 ? start : `${start}–${start + y - 1}`}차년도)`; start += y; return s; });
  const orgs = v.orgs || {}, joint = (orgs.joint || []).map((n, i) => n || `참여기관${i + 1}`);
  const text = `${stages.join(" · ")} · 주관 ${orgs.lead || "미입력"} · 공동 ${joint.length}${joint.length ? `(${joint.join(" · ")})` : ""}`;
  return { text, title: `문서 프레임 값(${from})\n${text}` };
}

const taskStageWork = (stage) => (taskStepsLast || []).filter((s) => stage.keys.includes(s.key) && !s.soon && s.key !== "files"); // 묶음의 세는 단계 — 준비(문서 고르기)와 준비 중인 ⑤ 는 안 센다
function taskStageSync(only = null, el0 = null) { // 묶음 머리 — 끝난 수 · 상태 줄 · 단추. 단계 목록을 다시 그릴 때마다(taskStepsDraw) · 도는 동안 1초마다(글만 바꾼다). only = 그 묶음만(el0 = 아직 문서에 안 붙은 상자)
  if (!taskStepsLast) return;
  const files = taskStepsLast.find((s) => s.key === "files"), current = TASK_STAGES.find((g) => taskStageWork(g).some((s) => !s.done)); // current = 할 일이 남은 첫 묶음(강조 단추는 카드에 하나)
  for (const stage of TASK_STAGES) if (!only || only === stage) taskStageSync1(stage, el0 || document.getElementById(stage.dom), files, current);
  if (!only) { taskJourneyDraw(); taskChainSync(); }
}
function taskStageSync1(stage, box, files, current) {
  if (!box) return;
  const steps = taskStepsLast.filter((s) => stage.keys.includes(s.key) && !s.soon), work = taskStageWork(stage), completed = work.filter((s) => s.done).length; // ⑤ 합계 계산 …(준비 중)은 세지 않는다
  const next = steps.find((s) => !s.done), R = taskRun && taskRun.stage === stage.id ? taskRun : null, busy = steps.find((s) => s.busy);
  const before = TASK_STAGES.slice(0, TASK_STAGES.indexOf(stage)).find((g) => taskStageWork(g).some((s) => !s.done)); // 덜 끝난 앞 묶음 — 그 뒤에야 이 묶음의 「한 번에 진행」 이 켜진다
  const report = taskSlotDoc("report"), plan0 = taskSlotDoc("plan"); // 마지막 실행의 끝 글은 그 쌍(사업계획서·연차보고서)·그 묶음의 것일 때만
  const end = taskRunEnds[stage.id]; // 끝 기록은 묶음마다 하나(이어 진행 — 앞 묶음의 끝 글이 뒤 묶음이 도는 동안에도 남는다)
  const last = end && report && end.report === report.id && plan0 && end.plan === plan0.id && end.done === completed ? end : null;
  box.querySelector(".dv-phase-count").textContent = `${completed}/${work.length} 완료`;
  const progress = box.querySelector(".dv-phase-progress");
  progress.max = work.length;
  progress.value = completed;
  progress.setAttribute("aria-valuetext", `세부 작업 ${work.length}개 중 ${completed}개 완료`);
  const st = box.querySelector(".dv-phase-state"), key = (k) => taskStepName(steps.find((s) => s.key === k));
  let kind = "next", msg = "";
  if (taskResetting && stage.id !== "review" && (taskResetting === stage.id || taskResetting === "frame")) { kind = "run"; msg = taskResetting === "frame" ? "초기화 — 연차보고서를 올린 원본으로 되돌리는 중" : "초기화 — 원본으로 되돌리고 구조를 다시 반영하는 중"; } // 구성 맞추기 초기화는 뒤 묶음도 함께(문서 검토의 분석은 그대로 — §21)
  else if (R) { kind = "run"; msg = `${key(R.key)}${R.note ? ` — ${R.note}` : ""} · ${fmtDur((Date.now() - R.t0) / 1000)}${R.stop ? " · 이 일이 끝나면 멈춥니다" : ""}`; }
  else if (busy) { kind = "run"; msg = `${taskStepName(busy)} — 진행 중`; }
  else if (before) msg = `${before.no} 「${before.name}」 완료 후 진행`; // 이전 결과가 남아 있어도 지금 선행 조건이 먼저다.
  else if (last && !last.ok) { kind = "halt"; msg = `멈춤 — ${key(last.key)}: ${last.text}`; }
  else if (last && !next) { kind = "done"; msg = `끝남 — ${last.text}`; } // 끝남은 남은 단계로 정한다 — 「분석」 처럼 단계 하나만 돈 실행이 성공해도 남은 단계가 있으면 아래 「다음」(astra 11-19: 마지막 성공 기록이 먼저 보이지 않게)
  else if (!next) { kind = "done"; msg = "모두 끝남"; }
  else msg = `다음: ${taskStepName(next)}${!box.open && next.text ? ` — ${next.text}` : ""}`;
  st.dataset.kind = kind;
  st.firstChild.hidden = kind !== "run";
  if (st.lastChild.textContent !== msg) st.lastChild.textContent = msg;
  const frame = box.querySelector(".dv-phase-frame"); // 1단계만 — 프레임 값 요약(단계·차년도 · 기관). 글이 같으면 안 건드린다(도는 동안 1초마다 온다)
  if (frame) {
    const f = taskFrameText(), t = frame.firstChild;
    frame.hidden = !f.text;
    if (t.textContent !== f.text) t.textContent = f.text;
    if (t.title !== f.title) t.title = f.title; // 글이 같아도 출처(사업계획서 기준 · 연차보고서 입력 값)는 바뀔 수 있다
  }
  const b = box.querySelector("[data-task-run]"), ready = !!files && files.done && !before; // 준비(두 칸에 문서)와 앞 묶음이 끝나야 누를 수 있다
  b.textContent = R ? (R.stop ? "멈추는 중…" : "멈춤") : "한 번에 진행";
  b.disabled = R ? R.stop : !!taskRun || !!taskResetting || !!busy || !next || !ready;
  const rb = box.querySelector("[data-task-reset]"), can = rb ? taskResetCan(stage) : null; // 초기화 — 도는 일이 없고 되돌릴 것이 있을 때(3단계는 단추 없음)
  if (rb) {
    rb.textContent = taskResetting === stage.id ? "초기화 중…" : "초기화";
    rb.disabled = !!taskRun || !!taskResetting || !!busy || !can.ok;
    rb.title = taskRun ? "한 번에 진행이 끝난 뒤 쓸 수 있습니다" : busy ? "지금 진행 중인 작업이 끝나면 사용할 수 있습니다" : !can.ok ? `초기화할 것이 없습니다 — ${can.why}`
      : stage.id === "frame" ? "구성 맞추기·내용 넣기 초기화 — 연차보고서를 올린 원본으로 되돌리고 내용 넣기 기록(자리 연결 · LLM 검토 · 넣은 기록)을 지웁니다(문서 정리에서 지운 작성요령도 돌아옴 · 확정한 프로젝트 구성과 헤딩·표 분석은 그대로). 누를 때 한 번 확인합니다"
      : "내용 넣기 초기화 — 연차보고서를 원본으로 되돌린 뒤 구조를 같은 프로젝트 구성 값으로 다시 반영하고 내용 넣기 기록을 지웁니다(문서 정리에서 지운 작성요령도 돌아옴). 누를 때 한 번 확인합니다";
  }
  b.className = "btn sm" + (!taskRun && next && ready && !box.open && current === stage ? " primary" : ""); // 강조 단추는 카드에 하나 — 할 일이 남은 첫 묶음의 것, 그 세부 목록을 펴면 그 안의 「다음 할 일」 단추가 강조
  b.title = R ? "지금 하는 일이 끝나면 멈춥니다 — 끝난 단계는 그대로 남습니다" : taskRun ? "다른 묶음이 진행 중입니다" : busy ? "지금 진행 중인 작업이 끝나면 사용할 수 있습니다"
    : !(files && files.done) ? "두 칸(사업계획서 · 연차보고서)에 문서를 먼저 고르세요" : before ? `${before.no} 「${before.name}」 ${typeof taskJosa === "function" ? taskJosa(before.name, "을", "를") : "을"} 먼저 끝내세요` : !next ? "남은 단계가 없습니다"
    : `이 묶음의 남은 단계를 차례로 한 번에 — ${stage.does}. 사람 손이 필요한 곳에서는 멈춥니다`;
  // 실행 단계가 바뀔 때·멈출 때에도 상세 줄을 함께 갱신한다. 매초 DOM을 다시 만들지 않아 포커스를 유지한다.
  const active = R ? R.key : busy && busy.key;
  for (const li of box.querySelectorAll("ol.dv-flow-steps > li")) {
    const s = taskStepsLast.find((x) => x.key === li.dataset.step);
    let status = li.dataset.state;
    if (!s.soon && active === s.key) status = "run";
    else if (!active && last && !last.ok && last.key === s.key) status = "halt";
    else if (active && status === "now") status = "todo";
    li.dataset.status = status;
    li.querySelector(".dv-flow-status").textContent = status === "done" && s.skipped ? (s.skipWord || "대상 없음") : { done: "완료", now: "다음 작업", todo: "대기", soon: "준비 중", ready: "진행 가능", run: "진행 중", halt: "멈춤" }[status];
    if (active ? active === s.key : status === "now" || status === "halt") li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  }
}

// ---- 여러 묶음 이어서 한 번에(spec_작업 ② §14 「이어서 한 번에」 — 2026-11-12 사용자 "1,2,3 단계도 한번에 할 수 있는 기능도 넣어줘, 1,2 만 할 수도 있고 3까지 할 수도 있고") — 이관만.
// 첨부 파일 칸 아래 한 줄 「이어서 한 번에 [1→2단계] [1→3단계]」. 시작 = 할 일이 남은 첫 묶음, 끝 = 고른 묶음. 실행은 taskRunAll(시작, 끝) — 확인 창 없이(2026-11-18 — 전에는 누를 때 한 번: 설계 Fable 답)
const taskChain = (toId) => { // 이어 돌 묶음 = 처음 ~ toId 가운데 할 일이 남은 것. 둘 이상이고 끝 묶음에 할 일이 남았을 때만(아니면 [] — 그 묶음의 「한 번에 진행」 과 같다)
  const c = TASK_STAGES.slice(0, TASK_STAGES.findIndex((g) => g.id === toId) + 1).filter((g) => taskStageWork(g).some((s) => !s.done));
  return c.length > 1 && c[c.length - 1].id === toId ? c : [];
};
const taskChainLabel = (c) => `${c[0].no.replace(/단계$/, "")}→${c[c.length - 1].no}`; // 「1→3단계」 — 실제로 도는 범위
function taskChainEl() { // 줄 하나 — 글·보임·켜짐은 taskChainSync
  const box = el("div", "dv-chain");
  box.id = "taskChain";
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "여러 단계 이어서 한 번에 진행");
  box.append(el("span", "dv-chain-label", "이어서 한 번에"));
  for (const g of TASK_STAGES.slice(1)) { // 끝 묶음마다 단추 하나(2단계까지 · 3단계까지) — 보통 단추(강조 단추는 카드에 하나)
    const b = el("button", "btn sm");
    b.type = "button";
    b.dataset.taskChain = g.id;
    b.onclick = () => taskRunChain(g.id);
    box.append(b);
  }
  box.append(hHelp("이어서 한 번에 안내", "할 일이 남은 첫 묶음부터 고른 묶음까지 차례로 진행합니다. 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다(끝난 묶음은 그대로). 남은 묶음이 하나뿐이면 그 묶음의 「한 번에 진행」 을 쓰세요.", { note: true }),
    el("span", "dv-chain-state"));
  return box;
}
function taskChainSync(host = document.getElementById("taskChain")) { // taskStageSync 가 부른다(도는 동안 1초마다 — 글이 같으면 안 건드린다)
  if (!host || !taskStepsLast) return;
  const files = taskStepsLast.find((s) => s.key === "files"), ready = !!files && files.done, busy = taskStepsLast.some((s) => s.busy), C = taskRun && taskRun.chain;
  let shown = 0;
  for (const b of host.querySelectorAll("[data-task-chain]")) {
    const c = taskChain(b.dataset.taskChain), mine = !!C && C.to === b.dataset.taskChain;
    const text = mine ? C.label : c.length ? taskChainLabel(c) : ""; // 도는 동안 제 단추의 글은 시작할 때의 범위 그대로
    b.hidden = !text; // 범위가 묶음 하나 이하 — 숨김
    if (text) shown++;
    if (text && b.textContent !== text) b.textContent = text;
    b.disabled = !!taskRun || !!taskResetting || busy || !ready;
    b.title = mine ? "이어 진행 중 — 멈추려면 지금 도는 묶음의 「멈춤」" : taskRun ? "지금 진행이 끝난 뒤 쓸 수 있습니다" : taskResetting ? "초기화가 끝난 뒤 쓸 수 있습니다"
      : busy ? "지금 진행 중인 작업이 끝나면 사용할 수 있습니다" : !ready ? "두 칸(사업계획서 · 연차보고서)에 문서를 먼저 고르세요"
      : `${c.map((g) => `${g.no} 「${g.name}」`).join(" → ")} 을 이어서 한 번에 — 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다`;
  }
  const cur = C && TASK_STAGES.find((g) => g.id === taskRun.stage), st = host.querySelector(".dv-chain-state");
  const msg = cur ? `${C.label} 이어 진행 중 — 지금 ${cur.no} 「${cur.name}」${taskRun.stop ? " · 이 일이 끝나면 멈춥니다(뒤 묶음은 진행 안 함)" : ""}` : "";
  if (st.textContent !== msg) st.textContent = msg;
  host.hidden = !shown;
}
function taskRunChain(toId) { // 이어 진행 단추 — 시작 묶음은 할 일이 남은 첫 묶음
  const c = taskChain(toId);
  if (c.length) taskRunAll(c[0].id, toId);
  else toast("이어서 진행할 묶음이 둘 이상 남아 있지 않습니다");
}

// 연차보고서의 헤딩·표 분석이 구분 기준 반영(구조) **전** 문서의 것인가 — 그러면 반영으로 늘어난 절·표가 분석에 없어 자리 연결이 그 자리를 못 본다(spec_작업 ④ ⓑ).
// 스크립트만 돈 분석일 때만 참(LLM 을 돌린 결과는 덮지 않는다 — 유료). 2단계 「한 번에 진행」 이 이때 다시 분석한다(2026-11-12 사용자 "헤딩추출, 테이블 정보 추출등을 해서 매핑하는거야")
function taskHeadsOld(report) {
  const h = taskFlow.heads[report.id], B = taskDivOf(report), rev = B && B.applied && B.applied.rev;
  const parts = h ? [h.stage2, h.stage3].filter(Boolean) : [];
  if (!parts.length || rev == null) return false; // 분석이 아예 없으면 첫 분석 몫(taskRunAnalyze)
  return parts.some((x) => ((x.meta || {}).rev ?? rev) < rev) && !parts.some((x) => (x.llm || {}).requested); // 있는 단계가 하나라도 구조 반영 전 것(2단계만 있고 3단계가 없는 문서도 — 첫 분석은 있는 단계를 건너뛴다)
}
const taskHeadsKept = (report) => { // 구조 반영 전의 분석인데 LLM 을 돌린 결과라 다시 안 돌림 — 끝 글에 알린다(늘어난 절·표를 못 이었을 수 있다)
  const h = taskFlow.heads[report.id], B = taskDivOf(report), rev = B && B.applied && B.applied.rev, parts = h ? [h.stage2, h.stage3].filter(Boolean) : [];
  return rev != null && parts.some((x) => ((x.meta || {}).rev ?? rev) < rev) && parts.some((x) => (x.llm || {}).requested);
};

const taskHeadsStale = (report) => { // 목적 문서의 분석이 마지막 구조 반영 전 것인가(스크립트 결과든 LLM 결과든) — 「다시 문서 검토」 의 끝남(§21)
  const h = taskFlow.heads[report.id], B = taskDivOf(report), rev = B && B.applied && B.applied.rev, parts = h ? [h.stage2, h.stage3].filter(Boolean) : [];
  return rev != null && parts.some((x) => ((x.meta || {}).rev ?? rev) < rev);
};

// ---- 문서 검토의 도우미(spec_작업 ② §21) — 그 문서의 헤딩 작업이 도는가 · 도는 동안 요약만 다시 읽기 · LLM 검증·보완 걸기 · 작성 지침 저장
const taskHeadsJob = (w) => (taskFlow.heads[w.id] || {}).job || {}; // 그 문서의 마지막 헤딩 작업(요약 GET …/headings 의 job — 없으면 {}) · chain = 이어 돌리기(「LLM 검증·보완」)
const taskHeadsRunning = (w) => taskHeadsJob(w).status === "running";
const taskLlmDone = (w) => { // 그 문서의 헤딩 · 표가 LLM 검증·보완을 거쳤나 — 분석 상태(app/analysis.py _llm)의 「done」 과 같은 기준: LLM 을 불렀고 스크립트로 대신하지 않은 결과
  const h = taskFlow.heads[w.id] || {}, ok = (x) => !!(x && (x.llm || {}).requested && !(x.llm || {}).fallback);
  return ok(h.stage2) && ok(h.stage3);
};
let taskLlmOk = null, taskLlmAsked = false, taskLlmAsk = null; // 서버의 LLM 을 쓸 수 있나(GET /api/headings/llm 의 available — null = 아직 모름). 못 쓰면 LLM 단계는 「건너뜀」 으로 끝난 것으로 본다 · taskLlmAsk = 그 물음의 약속
function taskLlmLoad() { // 한 번만 묻는다 → 약속(끝나면 taskLlmOk 가 정해져 있다 — 못 읽으면 false). 에이전트가 유료로 부를 문서를 세기 전에 기다린다(doc_agent_work.js agwRelayStatus)
  if (taskLlmAsked) return taskLlmAsk || Promise.resolve();
  taskLlmAsked = true;
  taskLlmAsk = api("/api/headings/llm").then((st) => { taskLlmOk = !!st.available; }).catch(() => { taskLlmOk = false; }).finally(() => { if (taskSlots() && !gatherOn()) taskStepsDraw(); });
  return taskLlmAsk;
}
const TASK_LLM_SKIP = "nfm.relayLlmSkip"; // 사람이 LLM 검증·보완을 건너뛴 문서 id 들(이 브라우저에 기억 — 「건너뛰기 취소」 로 되돌림)
function taskLlmSkips() { try { const v = JSON.parse(localStorage.getItem(TASK_LLM_SKIP) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } }
const taskLlmSkipped = (w) => taskLlmSkips().includes(w.id);
function taskLlmSkip(w, on) {
  const ids = taskLlmSkips().filter((x) => x !== w.id);
  if (on) ids.push(w.id);
  try { localStorage.setItem(TASK_LLM_SKIP, JSON.stringify(ids.slice(-200))); } catch { /* 기억만 안 함 */ }
  const target = typeof flowSkip === "function" && taskSlots() ? taskSlotDoc(taskSlots()[1]) : null; // 서버 쪽 실행기 · 첫 화면의 대시보드도 같이 보게 — 워크플로우 옵션에도 적는다(spec_워크플로우 ② §17-6 「건너뛰기」)
  if (target) flowSkip(target.id, w.id, on);
  taskStepsDraw();
}
// 그 묶음의 「한 번에 진행」 이 유료 LLM 검증·보완을 부를 문서(spec_워크플로우 ② §15 — astra P1 ⓑ) → [[문서, 이름]…](칸 차례). steps = 셈한 단계(taskStepsOf — 이 TASK 에 서는 단계만).
// 1단계 「LLM 검증·보완」(headsLlm) = 그 줄의 문서(taskReviewOf) 가운데 아직 거치지 않았고 사람이 건너뛰지 않은 문서 — 스크립트 분석이 아직 없어도 센다(실행이 분석한 뒤 부른다).
// 2단계 「다시 문서 검토(LLM)」(reheadsLlm) = 그 줄이 끝나지 않았고 건너뛰지 않은 목적 문서(구조 반영 · 다시 분석으로 지금의 LLM 결과가 옛것이 되는 것까지 그 줄이 본다). LLM 을 쓸 수 없으면 없음(아직 모르면 쓸 수 있는 것으로 센다).
// 3단계 「내용 넣기」 의 LLM(자리 연결 검토 · 표 대응 · 빈 자리 검토)은 문서마다의 단계가 아니라 여기 없다(묶음째 유료 — 전과 같다). 에이전트의 실행 카드(doc_agent_work.js agwRelayStatus)가
// 이 문서를 카드 글 · 행동 key 에 적고, 카드에서 시작한 실행은 이 문서에만 유료 호출을 건다(taskRunAll 의 paid → taskRunSteps llmPart)
function taskPaidDocs(stageId, steps = taskStepsLast || taskStepsCalc()) {
  const [plan, report] = (taskSlots() || []).map((k) => taskSlotDoc(k)), step = (key) => steps.find((s) => s.key === key);
  if (!plan || !report || taskLlmOk === false) return [];
  if (stageId === "review") return step("headsLlm") ? taskReviewOf(plan, report).llm.filter(([w]) => !taskLlmSkipped(w) && !taskLlmDone(w)) : [];
  if (stageId === "frame") { const s = step("reheadsLlm"); return s && !s.done && !taskLlmSkipped(report) ? [[report, "연차보고서"]] : []; }
  return [];
}
async function taskRunLlm(id, run) { // 「한 번에 진행」 안의 LLM 검증·보완 — 그 문서로 걸고(POST …/analysis/llm: 이미 거친 것은 서버가 건너뜀) 끝날 때까지 2초마다 읽는다 → "" | 못 끝낸 까닭(글). 문서는 안 바뀐다
  const url = `/api/docs/${id}/analysis/llm`, post = () => api(url, { method: "POST", headers: H_JSON, body: JSON.stringify({ skill: typeof tpaSkillKey === "function" ? tpaSkillKey() : "tidy" }) });
  let mine = true; // 409(이미 도는 다른 헤딩 작업)면 그 작업이 끝난 뒤 한 번 더 건다(taskRunAnalyze 와 같은 길)
  try { await post(); } catch (e) { if (e.status !== 409) return e.message || "LLM 검증·보완을 시작하지 못했습니다"; mine = false; }
  for (let i = 0; i < 2700; i++) { // 90분까지
    await new Promise((r) => setTimeout(r, 2000));
    if (taskRun !== run) return "멈췄습니다";
    if (run.stop) { try { await api(url, { method: "DELETE" }); } catch { /* 이미 끝남 */ } return "눌러서 멈췄습니다 — 서버는 지금 하는 LLM 일이 끝나면 멈춥니다"; }
    const job = (await api(`/api/docs/${id}/headings`)).job;
    if (job && job.status === "running") continue;
    if (!mine) { try { await post(); mine = true; } catch (e) { if (e.status !== 409) return e.message || "LLM 검증·보완을 시작하지 못했습니다"; } continue; }
    return job && job.error ? job.error : "";
  }
  return "LLM 검증·보완이 끝나지 않습니다 — 「헤딩 추출」 탭에서 확인하세요";
}
let taskHeadsTimer = 0;
async function taskHeadsWatch(now = false) { // 두 문서의 헤딩 요약만 다시 읽는다(가벼움 — 연결 목록은 안 읽음): 분석 · LLM 검증·보완이 도는 동안 5초마다. 끝나면 이관 자료를 한 번 다시 읽는다(연결 목록 · 작성 지침)
  clearTimeout(taskHeadsTimer);
  const slots = gatherOn() ? null : taskSlots(), docs = (slots || []).map((k) => taskSlotDoc(k)).filter(Boolean);
  if (docs.length < 2 || taskRun) return; // 「한 번에 진행」 이 도는 동안은 그 몸통이 스스로 읽는다(taskRunAnalyze · flowRead) — 여기서 같이 읽으면 그 읽기가 밀린다(flow.seq)
  const flow = taskFlow, epoch = state.epoch, was = docs.some((w) => taskHeadsRunning(w));
  if (now || was) {
    const got = await Promise.all(docs.map((w) => api(`/api/docs/${w.id}/headings`).catch(() => null)));
    if (epoch !== state.epoch || flow !== taskFlow || taskRun) return;
    docs.forEach((w, i) => { if (got[i]) flow.heads[w.id] = got[i]; });
  }
  if (docs.some((w) => taskHeadsRunning(w))) { taskStepsDraw(); taskHeadsTimer = setTimeout(() => taskHeadsWatch(), 5000); }
  else if (now || was) taskFlowLoad(); // 끝났다(또는 방금 건 일이 벌써 끝남) — 연결 목록 · 작성 지침까지 새로
}
async function taskHeadsLlm(w) { // 헤딩 · 표의 「LLM 검증·보완」 을 그 문서로 — 공통 모듈의 이어 돌리기(spec_작업 ② §20: 헤딩 · 템플릿 → 표 → 서식 정리 계획만 · 문서는 안 바뀜 · 유료). 누르면 바로(단추가 확인 — design.md §18)
  const epoch = state.epoch;
  if (w.id === state.id && typeof dsLlmRun === "function") await dsLlmRun(); // 지금 문서 — 이름 줄 · 진행표 · 헤딩 탭이 같이 따라온다(doc_status.js)
  else {
    try {
      await api(`/api/docs/${w.id}/analysis/llm`, { method: "POST", headers: H_JSON, body: JSON.stringify({ skill: typeof tpaSkillKey === "function" ? tpaSkillKey() : "tidy" }) });
      toast(`${w.name} — LLM 검증·보완을 시작했습니다(몇 분 — 진행은 「헤딩 · 표 분석」 줄에 보입니다)`);
    } catch (e) { toast(e.status === 409 ? "그 문서의 헤딩 작업이 이미 돌고 있습니다 — 끝난 뒤 다시 누르세요" : `LLM 검증·보완을 시작하지 못했습니다: ${e.message}`, true); }
  }
  if (epoch === state.epoch) taskHeadsWatch(true);
}
async function taskGuidesLoad(report, collect = false) { // 저장한 작성 지침(spec_작업 ② §21 「작성 지침 저장」) → taskFlow.guides. 분석은 있는데 저장본이 없으면 한 번 모아 저장한다(스크립트 — 1초 안팎) · collect = 지금 문서에서 다시 모아 저장
  const flow = taskFlow, h = flow.heads[report.id], url = `/api/docs/${report.id}/form-guides`;
  try {
    let g = collect ? null : await api(url);
    if (collect || (!g.saved && h && h.stage2 && h.stage3 && !flow.guidesAsked)) { flow.guidesAsked = true; g = await api(url, { method: "POST" }); }
    flow.guides = g;
  } catch (e) { flow.guides = { error: e.message }; } // 못 읽어도 단계는 그대로(글에 안 적는다) — 「작성요령 삭제」 가 지우기 바로 전에 다시 남긴다
  if (flow === taskFlow) taskStepsDraw();
  return flow.guides;
}

async function taskRunReanalyze(id, run) { // 다시 분석(구조 반영 전의 분석 — taskHeadsOld): 2단계(헤딩 그래프 — 1단계는 스스로 뽑는다) → 3단계(표 구조), 스크립트만
  for (const stage of [2, 3]) {
    await taskRunAnalyze(id, run, { stage, llm: false });
    if (taskRun !== run || run.stop) return;
  }
}

async function taskRunAnalyze(id, run, body = { first: true }) { // 헤딩 그래프·표 구조가 없는 문서 — 첫 분석과 같은 끝점(스크립트만 · 있는 단계는 건너뜀), 끝날 때까지 2초마다 읽는다(문서 비교의 「함께 추출」 과 같은 길)
  let mine = true; // 우리가 건 작업인가 — 409(이미 도는 다른 헤딩 작업)면 그 작업이 끝난 뒤 한 번 더 건다(그 작업이 우리가 바란 분석이라는 보장이 없다)
  try { await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify(body) }); }
  catch (e) { if (e.status !== 409) throw e; mine = false; }
  for (let i = 0; i < 900; i++) { // 30분까지
    await new Promise((r) => setTimeout(r, 2000));
    if (taskRun !== run || run.stop) return;
    const job = (await api(`/api/docs/${id}/headings`)).job;
    if (job && job.status === "running") continue;
    if (!mine) { // 다른 작업이 끝남 — 이제 우리 것을
      try { await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify(body) }); mine = true; } catch (e) { if (e.status !== 409) throw e; }
      continue;
    }
    if (job && job.error) taskHalt(`헤딩·표 분석 실패 — ${job.error}`);
    return;
  }
  taskHalt("헤딩·표 분석이 끝나지 않습니다 — 「헤딩 추출」 탭에서 확인하세요");
}

async function taskRunSteps(run, plan, report) { // 그 묶음(run.stage)의 안 끝난 단계를 차례로 — 끝나면 결과 글, 멈출 곳에서는 TaskHalt. 단계마다 반환값이 아니라 상태(taskSteps·taskFlow)를 본다
  const at = (key, note) => { // 일 하나를 시작하기 전 — 멈춤 요청·문서 바뀜을 보고, 상태 줄을 바꾼다
    if (run.stop) taskHalt("눌러서 멈췄습니다 — 끝난 단계는 그대로입니다");
    if (key !== "open" && state.id !== report.id) taskHalt("다른 문서를 열어 멈췄습니다");
    const [p1, r1] = (taskSlots() || []).map((k) => taskSlotDoc(k)); // 누를 때의 쌍 그대로인가 — 도는 중 칸의 문서를 바꾸면 다른 계획서의 내용이 들어갈 수 있다
    if (!p1 || !r1 || p1.id !== plan.id || r1.id !== report.id) taskHalt("도는 중에 사업계획서·연차보고서 칸의 문서가 바뀌어 멈췄습니다 — 다시 누르세요");
    if (key !== "open") run.key = key;
    run.note = note;
    taskStageSync();
  };
  const step = (key) => taskSteps().find((s) => s.key === key);
  const flowRead = async () => { // 다른 문서 쪽 자료(구분 기준 · 헤딩 요약)를 다시 읽고 다 올 때까지
    await taskFlowLoad();
    if (!(await taskWait(() => !!taskFlow.err || (taskDivOf(plan, true) !== undefined && taskDivOf(report) !== undefined && !!taskFlow.heads[plan.id] && !!taskFlow.heads[report.id]), 120000)))
      taskHalt("다른 문서를 읽는 데 너무 오래 걸립니다 — 잠시 뒤 다시 누르세요");
    if (taskFlow.err) taskHalt(`다른 문서를 읽지 못했습니다: ${taskFlow.err}`);
  };

  // 연차보고서를 고치는 문서로(taskSteps 의 onReport 와 같은 길 — 두 문서의 자리는 그대로)
  run.key = run.stage === "review" ? "heads" : run.stage === "frame" ? (run.redo || "config") : run.stage === "clean" ? "guide" : "link";
  const SN = taskStageName; // 묶음 이름 — 지금 TASK 의 번호로(조립한 TASK 는 번호가 다르다 · 없는 묶음은 번호 없이)
  const got = (w) => { const h = taskFlow.heads[w.id]; return !!(h && h.stage2 && h.stage3); }; // 그 문서에 헤딩 그래프 · 표 구조가 있나
  const llmPart = async (key, w, who) => { // LLM 검증·보완 단계(§21 — headsLlm · reheadsLlm): 이미 끝난 것으로 보면(거침 · LLM 을 쓸 수 없음 · 사람이 건너뜀) 글만 낸다. 못 끝내면 멈춘다 — 그 줄의 「건너뛰기」 로 스크립트 분석만으로 갈 수 있다(막다른 길 없음)
    if (taskLlmOk == null) await taskWait(() => taskLlmOk != null, 10000);
    const one = (s) => (s.per && s.per[w.id]) || s; // 줄 하나에 문서 여럿이면(taskSteps llmMany — 조립한 TASK: spec_워크플로우 ② §15) 그 문서의 몫
    const s0 = one(step(key));
    if (s0.done) return s0.skipped ? ` · ${who} LLM 검증·보완은 건너뜀(${taskLlmOk === false ? "LLM 을 쓸 수 없음" : "건너뛰기"})` : "";
    // 에이전트의 실행 카드가 시작한 실행은 카드가 승인한 문서에만 유료 호출을 건다(run.paid — taskPaidDocs · astra P1 ⓑ: 도는 사이 다른 탭에서 「건너뛰기」 를 풀어도) — 그 밖의 문서는 하지 않고 남긴다(다음 카드가 다시 묻는다)
    if (run.paid && !run.paid.has(w.id)) return ` · ${who} LLM 검증·보완은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)`;
    at(key, `${who} LLM 검증·보완 — 헤딩 · 템플릿 → 표 → 서식 정리 계획(유료 · 몇 분)`);
    const why = await taskRunLlm(w.id, run);
    if (w.id === state.id) headsPeek(); // 지금 문서면 쪽 여백 표시·헤딩 탭도 새 결과로
    at(key, "검증 결과 읽기"); // 멈춤을 눌렀으면 여기서 멈춘다
    await flowRead();
    if (!one(step(key)).done) taskHalt(`${who}의 LLM 검증·보완을 끝내지 못했습니다${why ? ` — ${why}` : ""} · 다시 누르거나 그 줄의 「건너뛰기」 로 스크립트 분석만으로 진행하세요`);
    return ` · ${who} LLM 검증·보완을 거쳤습니다`;
  };
  const guidesKeep = async () => { try { await taskGuidesLoad(report, true); } catch (e) { console.warn(e); } }; // 작성 지침을 헤딩/표별로 저장(스크립트 — 못 해도 멈추지 않는다: 「작성요령 삭제」 가 지우기 전에 다시 남긴다)
  at("open", "연차보고서 여는 중");
  if (state.id !== report.id) {
    await openWork(report.id);
    if (state.id !== report.id) taskHalt("연차보고서를 열지 못했습니다(고치던 글을 두고 그만뒀거나 열리지 않음)");
  }
  taskPaneShow(); // 보통 패널 「작업 개요」 — 에이전트 보기가 이 TASK 를 이끌고 있으면 그대로(진행 카드가 거기 있다)
  await divShow();
  if (state.id !== report.id || !dv.view) taskHalt("연차보고서의 프로젝트 구성을 읽지 못했습니다");
  await flowRead();

  if (run.stage === "clean") { // 4단계 「문서 정리」 — 내용 반영(3단계)이 끝난 문서에서만
    if (!step("apply").done) await taskWait(() => !taskFlow.linkBusy, 180000); // 「지난 반영」(연결 목록의 kept.applied)은 flowRead 뒤 연결 목록이 와야 보인다
    const s = step("apply");
    if (taskHasStage("map") && !s.done) taskHalt(`${SN("map")} 이 먼저입니다 — ${s.text || "④ 내용 반영 전"}`);
    at("guide", `양식 안내 지우기 — ${cleanupNames()}`);
    const cleaned = await taskCleanupRun({ quiet: true, run }); // null = 지우지 않고 그만둠(멈춤 요청 · 다른 문서) — 「지울 안내가 없습니다」 와 다르다(astra 11-16: 멈춘 것을 끝난 것으로 보고하지 않는다)
    if (cleaned == null) taskHalt("양식 안내를 지우지 않고 멈췄습니다(멈춤을 눌렀거나 다른 문서를 열었습니다)");
    return cleaned;
  }
  if (run.stage === "map") { // 3단계 「내용 넣기」 — 구조(2단계)가 끝난 문서에서만
    const s = step("division");
    if (taskHasStage("frame") && !s.done) taskHalt(`${SN("frame")} 이 먼저입니다 — ${s.text || step("config").text}`);
    return taskRunMap(run, plan, report, at, step, flowRead);
  }
  if (run.stage === "review") { // 1단계 「문서 검토」 — 두 문서의 헤딩·표 분석(없는 문서만 · 스크립트) → 작성 지침을 헤딩/표별로 저장. 문서는 안 바뀐다(spec_작업 ② §21)
    // 할 문서 = 「문서 검토」 를 고른 문서(taskReviewOf — spec_워크플로우 ② §15 「문서마다 단위문서 TASK」: 붙박이 이관 = 분석 두 문서 · LLM 원본). 할 문서가 없는 단계는 건너뛴다(그 TASK 에 서지 않는 단계 — taskStepsOf)
    const RV = taskReviewOf(plan, report), mine = RV.heads.map(([w]) => w);
    at("heads", "헤딩·표 분석 확인");
    const lack = mine.filter((w) => !got(w));
    if (lack.length) {
      at("heads", `헤딩·표 분석(스크립트) — ${lack.map((w) => (w.id === plan.id ? "사업계획서" : "연차보고서")).join(" · ")}`);
      await Promise.all(lack.map((w) => taskRunAnalyze(w.id, run)));
      if (lack.some((w) => w.id === state.id)) headsPeek(); // 지금 문서면 쪽 여백 표시·헤딩 탭도 새 결과로
      at("heads", "분석 결과 읽기");
      await flowRead();
      if (mine.some((w) => !got(w))) taskHalt("헤딩·표 분석 결과가 생기지 않았습니다 — 「헤딩 추출」 탭에서 확인하세요");
    }
    if (mine.includes(report)) { // 작성 지침(목적 문서의 양식 — 연차보고서)은 목적 문서를 검토할 때 저장한다(붙박이 이관은 늘 · 목적 문서가 「문서 검토」 를 안 고른 조립한 TASK 는 「다시 문서 검토」 · 「작성요령 삭제」 가 남긴다)
      at("heads", "작성 지침 저장(헤딩/표별)");
      await guidesKeep();
    }
    const gc = ((taskFlow.guides || {}).saved || {}).counts;
    const base = `${RV.heads.length === 1 ? RV.heads[0][1] : "두 문서"}의 헤딩 그래프·표 구조가 있습니다${gc && (gc.items || gc.marks) ? ` · 작성 지침 ${nf(gc.items)}개 저장(헤딩 ${nf(gc.headings)} · 표 ${nf(gc.tables)})` : ""}`;
    if (run.only === "heads") return RV.llm.length ? `${base} — 다음은 「LLM 검증·보완」 입니다` : base; // 「분석」 단추 — 이 단계만
    let llm = "";
    for (const [w, who] of RV.llm) llm += await llmPart("headsLlm", w, who); // 원본 문서의 LLM 검증·보완(목적 문서는 구조를 맞춘 뒤 2단계의 「다시 문서 검토(LLM)」 — 조립한 TASK 에서 목적 문서가 「구성 맞추기」 를 안 골랐으면 여기서 이어서)
    return `${base}${llm}${taskHasStage("frame") ? ` — 구성은 ${SN("frame")} 에서 맞춥니다` : ""}`;
  }

  // 2단계 「구성 맞추기」(§21) = 프로젝트 구성 추출 → ① 프로젝트 구성 반영 → 헤딩·표 다시 분석. 내용은 넣지 않는다(3단계)
  // 프로젝트 구성 추출 — 사업계획서의 구성을(값이 없으면 문서에서 읽어) 프로젝트에 확정. 문서는 안 바뀐다(spec_작업 ② §18 — 전에는 따로 선 1단계)
  at("config", "사업계획서의 프로젝트 구성 확인");
  if (!step("config").done) {
    const CF = taskConfigOf(plan);
    let values = CF && (CF.values || CF.read);
    if (!values) { // 저장한 값도 읽어 둔 값도 없음 — 사업계획서에 적힌 값
      at("config", "사업계획서에서 단계·차년도·기관 읽기");
      try { values = taskReadValues((await api(`/api/docs/${plan.id}/divisions/read`)).read); } catch (e) { console.warn(e); }
      if (!values) taskHalt(`사업계획서에서 단계·차년도·기관을 읽지 못했습니다 — ${SN("frame")} 의 프로젝트 구성 입력 칸에 넣거나 「프로젝트 구성 불러오기」 로 불러온 뒤 다시 누르세요`);
    }
    at("config", "프로젝트에 저장(확정)");
    if (!(await taskConfigConfirm(plan, values))) taskHalt("프로젝트 구성을 확정하지 못했습니다(알림 글 참고)");
    await flowRead();
    const s = step("config");
    if (!s.done) taskHalt(`프로젝트 구성이 확정되지 않았습니다 — ${s.text}`);
  }

  // ① 프로젝트 구성 반영 — 기준은 사업계획서(위에서 확정한 프로젝트 구성): 값을 맞추고(당해 차년도도 — taskDivFit 과 같은 값) 계획 → 반영. 반영은 편집 하나(실행 취소 1)
  at("division", "사업계획서 값과 견주기");
  if (!step("division").done) {
    let A = taskDivOf(plan, true);
    if (!A || !A.values) taskHalt("사업계획서(기준)에 프로젝트 구성 값이 없습니다 — 사업계획서에서 값을 넣거나 문서에서 읽은 뒤 다시 누르세요");
    if (A.read) { // 저장된 값이 없어 문서에서 읽은 값(2026-11-18 부터 확인 창 없이 — 끝 글 · 1단계 단계 글에 그 값이 보인다) — 사업계획서 작업의 값으로 저장한다(문서는 그대로)
      at("division", "문서에서 읽은 값을 사업계획서 값으로 저장");
      await api(`/api/docs/${plan.id}/divisions/settings`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ values: A.values }) });
      await flowRead();
      A = taskDivOf(plan, true);
      if (!A || !A.values) taskHalt("사업계획서 값을 저장하지 못했습니다");
    }
    const B = taskDivOf(report);
    if (!B || !B.values || taskDivDiff(A.values, B.values).length) {
      const cur = dv.values && dv.values.current;
      dv.values = structuredClone(A.values);
      if (!dv.values.current && cur) dv.values.current = cur;
      divTouched();
      divRender();
    }
    at("division", "변경 계획");
    if (!(await divPlan()) || !dv.plan) taskHalt("프로젝트 구성 변경 계획을 세우지 못했습니다(알림 글 참고)"); // divPlan 의 반환값을 본다 — 못 세워도 전의 계획이 dv.plan 에 남아 있을 수 있다
    const stops = divAutoStops(); // 양식 맞추기의 「한 번에 진행」 과 같은 검사(계획 오류 · 미해결 · 기관 차례) — 사람이 봐야 할 계획은 저절로 반영하지 않는다
    if (stops) taskHalt(`${stops} — 저절로 반영하지 않습니다. ${SN("frame")} 의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요`);
    at("division", "연차보고서에 반영");
    await divApply({ quiet: true });
    await divShow();
    await flowRead();
    const s = step("division");
    if (!s.done) taskHalt(`프로젝트 구성이 반영되지 않았습니다 — ${s.text}`);
  }

  // 다시 문서 검토 — 구조 반영으로 늘어난 절·표가 분석에 들어가게(§21 — 전에는 3단계 「한 번에 진행」 안에 숨어 있었다). 먼저 스크립트: 2단계(헤딩 그래프) → 3단계(표 구조), 이어서 LLM 검증·보완(llmPart).
  // 구조 반영 전의 분석이 LLM 판정을 거친 결과(taskHeadsKept)여도 다시 분석한다(LLM 을 다시 받는다) — LLM 을 쓸 수 없을 때만 그대로 둔다(keep · run.redo = 「다시 분석」 을 사람이 누르면 그때도 다시)
  at("reheads", "헤딩·표 분석 확인(구조 반영 뒤)");
  let again = "";
  if (taskLlmOk == null) await taskWait(() => taskLlmOk != null, 10000); // LLM 을 쓸 수 있나 — 아래 keep 판단에 쓴다(못 알아내면 쓸 수 있는 것으로 보고 다시 분석)
  const keep = taskHeadsKept(report) && taskLlmOk === false;
  if (!got(report) || (taskHeadsStale(report) && !keep) || run.redo === "reheads") {
    at("reheads", "연차보고서 헤딩·표 다시 분석(스크립트)");
    await (got(report) ? taskRunReanalyze(report.id, run) : taskRunAnalyze(report.id, run));
    if (taskRun !== run || run.stop) taskHalt("눌러서 멈췄습니다 — 끝난 단계는 그대로입니다");
    headsPeek(); // 쪽 여백 표시·헤딩 탭도 새 결과로
    at("reheads", "분석 결과 읽기");
    await flowRead();
    const s = step("reheads");
    if (!s.done) taskHalt(`연차보고서를 다시 분석하지 못했습니다 — ${s.text || "「헤딩 추출」 탭에서 확인하세요"}`);
    again = " · 연차보고서를 다시 분석했습니다";
    at("reheads", "작성 지침 저장(헤딩/표별)");
    await guidesKeep(); // 구조 반영으로 자리가 바뀌었다 — 새 분석으로 다시 저장
  } else if (keep) again = " · 연차보고서의 분석은 구조 반영 전 것(LLM 결과 — LLM 을 쓸 수 없어 그대로 둠 · 늘어난 절·표는 못 이을 수 있음: 「다시 분석」)";
  if (run.only === "reheads") return `구조를 맞춘 문서의 헤딩·표${again ? again.replace(/^ · /, " — ") : " 분석은 구조 반영 뒤의 것입니다"} — 다음은 「다시 문서 검토(LLM)」 입니다`; // 「다시 분석」 단추 — 이 단계만
  const llm = await llmPart("reheadsLlm", report, "연차보고서");
  return `구조를 맞췄습니다 — ${step("division").text}${again}${llm} · 내용은 ${SN("map")} 에서 넣습니다`;
}

async function taskRunMap(run, plan, report, at, step, flowRead) { // 3단계 「내용 넣기」 — (안전망: 헤딩·표 분석) → ② 자리 연결(LLM 검토) → ③ 넣기 계획 → ④ 내용 반영
  // ② 자리 연결 — 앞 조건(두 문서의 헤딩 그래프·표 구조)은 1단계 「문서 검토」 · 2단계의 「다시 분석」 이 끝내 둔다(§21). 그래도 없거나 구조 반영 전 것이면 여기서 분석한다(안전망 — 스크립트):
  // 이미 있는 분석은 다시 돌리지 않는다(뼈대 유지 — spec_헤딩_추출 ② §17). 연차보고서의 분석이 구조 반영 전 것이고 스크립트만 돈 것이면 다시 분석한다(taskHeadsOld — 늘어난 절·표가 분석에 없으면 그 자리를 못 잇는다)
  at("link", "헤딩·표 분석 확인");
  const got = (w) => { const h = taskFlow.heads[w.id]; return !!(h && h.stage2 && h.stage3); };
  const old = taskHeadsOld(report), lack = [plan, report].filter((w) => !got(w) && !(old && w.id === report.id)); // 구조 반영 전의 분석이 하나라도 있으면 2단계부터 다시(첫 분석은 있는 단계를 건너뛴다)
  if (lack.length || old) {
    at("link", `헤딩·표 분석(스크립트) — ${[...lack.map((w) => (w.id === plan.id ? "사업계획서" : "연차보고서")), ...(old ? ["연차보고서(구조 반영 뒤 다시)"] : [])].join(" · ")}`);
    await Promise.all([...lack.map((w) => taskRunAnalyze(w.id, run)), ...(old ? [taskRunReanalyze(report.id, run)] : [])]);
    if (old || lack.some((w) => w.id === state.id)) headsPeek(); // 지금 문서면 쪽 여백 표시·헤딩 탭도 새 결과로
    at("link", "분석 결과 읽기");
    await flowRead();
    if (!got(plan) || !got(report)) taskHalt("헤딩·표 분석 결과가 생기지 않았습니다 — 「헤딩 추출」 탭에서 확인하세요");
  }
  at("link", "연결 목록");
  await linksCall(report);
  await taskWait(() => !taskFlow.linkBusy, 180000);
  const linkBad = () => { const L = taskFlow.links; return !L || L.error || !L.counts || !L.from || !L.to || L.from.reasons.length || L.to.reasons.length; };
  if (linkBad()) taskHalt(step("link").text || "연결 목록을 읽지 못했습니다");
  let llm = "";
  if ((taskFlow.links.counts.ambiguous || linksOpenTables(taskFlow.links)) && !taskFlow.links.llm) { // 확인 필요(묶음)나 못 정한 표가 있고 아직 검토 전일 때만 한 번(유료) — 사람이 고른 연결은 안 바뀐다
    at("link", `LLM 검토 — 확인 필요 ${taskFlow.links.counts.ambiguous || 0}곳 · 못 정한 표 ${linksOpenTables(taskFlow.links)}개(수십 초)`);
    await linksLlm();
    await linksCall(report); // LLM 답이 다른 읽기에 밀려 화면에서 빠질 수 있다(linkSeq) — 서버에 저장된 것을 한 번 더 읽는다
    await taskWait(() => !taskFlow.linkBusy, 180000);
    if (linkBad()) taskHalt(step("link").text || "연결 목록을 읽지 못했습니다");
    if (!taskFlow.links.llm) llm = " · LLM 검토는 못 함(확인 필요한 자리는 비워 둠)"; // 실패해도 멈추지 않는다 — 이어진 자리만 넣는다
  }
  const L = taskFlow.links, linked = `연결됨 ${L.counts.paired || 0}${L.counts.ambiguous ? ` · 확인 필요 ${L.counts.ambiguous}(비워 둠)` : ""}${llm}${taskHeadsKept(report) ? " · 헤딩·표 분석은 구조 반영 전 것(LLM 결과라 다시 안 돌림 — 늘어난 절·표는 못 이었을 수 있음)" : ""}`; // 같은 이름 자리의 수는 넣은 결과 글(fillDoneText)에 있다
  if (linksNone(L)) return `이어진 자리가 없어 넣을 내용이 없습니다(${linked})`; // 정상 0건(linksNone — 화면의 넣기 계획 · 내용 반영도 같은 판정으로 끝난다: 위 linkBad 가 전제 없음 · 판정 실패를 먼저 멈춘다)

  // ③ 넣기 계획 → ④ 내용 반영 — 계획 뒤 곧바로 반영(사이에 문서가 바뀌면 409: 계획을 한 번만 다시). 반영은 편집 하나(실행 취소 1)
  let gapped = false, gapNote = "";
  let mapped = false, mapNote = ""; // 표 대응(spec_병합 ② §5-3 10) — 같은 표로 이었는데 칸을 못 맞춘 표가 계획에 있으면 한 번만 LLM 에 묻고 다시 계획한다(유료 · 표마다 십수 초 — 「한 번에 진행」 을 누른 범위)
  for (let tries = 0; ; tries++) {
    at("plan", "넣기 계획");
    await fillPlan();
    let p = (taskFlow.fill || {}).plan;
    if (!p) taskHalt("넣기 계획을 세우지 못했습니다(알림 글 참고)");
    const gapOpen = ((p.gaps || {}).counts || {}).open || 0;
    if (gapOpen && !gapped) { // 빈 자리 검토(spec_병합 ② §5-4 8) — 아직 안 물은 빈 자리가 있으면 한 번만(유료 · 수십 초). 빈 표에 고른 원본 표는 아래 표 대응의 대상이 된다
      gapped = true;
      at("plan", `빈 자리 검토(LLM) — 아직 빈 자리 ${gapOpen}곳(수십 초)`);
      gapNote = fillGapNote(await fillGaps({ quiet: true })); // 실패해도 멈추지 않는다 — 그 자리는 비워 둔다
      at("plan", "넣기 계획(빈 자리 검토 뒤)");
      await fillPlan();
      p = (taskFlow.fill || {}).plan;
      if (!p) taskHalt("넣기 계획을 세우지 못했습니다(알림 글 참고)");
    }
    const open = ((p.maps || {}).counts || {}).open || 0;
    if (open && !mapped) {
      mapped = true;
      at("plan", `표 대응(LLM) — 행·열 구성이 다른 표 ${open}개(표마다 십수 초)`);
      const got = await fillMap({ quiet: true });
      mapNote = got ? ` · 표 대응 ${got.mapped}/${(got.tables || []).length}` : " · 표 대응은 못 함(그 표는 비워 둠)"; // 실패해도 멈추지 않는다 — 맞춘 표만 넣는다
      at("plan", "넣기 계획(표 대응 뒤)");
      await fillPlan();
      p = (taskFlow.fill || {}).plan;
      if (!p) taskHalt("넣기 계획을 세우지 못했습니다(알림 글 참고)");
    }
    if (!p.todo) { if (heads.dlg === "fill") headsColClose(); return `${linked}${gapNote}${mapNote} · 넣을 것이 없습니다(이미 넣었거나 넣을 자리가 없음)`; } // 실패가 아니다 — 이미 넣은 문서에서 다시 누른 경우
    at("apply", "내용 반영");
    await fillApply({ quiet: true });
    const F = taskFlow.fill || {};
    if (F.done) return `${linked}${gapNote}${mapNote} · ${fillDoneText(F.done)}`;
    if (!F.plan && !tries) continue; // 계획을 버렸다(409 — 계획 뒤 문서가 바뀜 · 넣을 것 없음) → 한 번만 다시 계획
    taskHalt("내용을 반영하지 못했습니다(알림 글 참고)");
  }
}

function taskRunKeep(stage, plan, report, run, end) { // 그 묶음의 끝을 상태 줄에 남긴다(taskRunEnds — 묶음마다 하나) · taskRunLast = 마지막 것. 끝난 수는 방금 셈한 것(taskStepsLast)
  taskRunLast = taskRunEnds[stage.id] = { ...end, stage: stage.id, report: report.id, plan: plan.id, key: run.key, done: taskStageWork(stage).filter((s) => s.done).length };
}

// 그 묶음의 「한 번에 진행」 — 확인 창 없이(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 누를 때 한 번: 11-12 「시작할 때 한 번만」): 중간 계획 확인 없이 반영한다.
// toId 가 뒤 묶음이면 stageId 부터 거기까지 이어서(taskRunChain — 「이어서 한 번에」) — 확인은 그때도 한 번, 묶음 경계마다 단계를 다시 셈하고 멈춤 요청·실패에서 전체가 멈춘다
async function taskRunAll(stageId = "frame", toId = stageId, sure = false, redo = "", only = "", paid = null) { // sure = 확인 창 없이 — 작업 진행 에이전트의 실행 카드 「진행」 이 그 확인이다(doc_agent_work.js) · redo = 끝난 단계를 다시(지금은 "reheads" — 「다시 분석」: §21)
  // paid = 유료 LLM 검증·보완을 걸어도 되는 문서 id 들(에이전트의 실행 카드가 승인한 것 — taskPaidDocs: 그 밖의 문서는 llmPart 가 하지 않고 남긴다) · null = 제한 없음(사람이 「한 번에 진행」 을 직접 누름 — 전과 같다)
  // → 시작하지 않은 까닭 {ok: false, text}(정의가 바뀜 · 지워짐 — 에이전트의 agwExec 가 그 글로 끝낸다) | undefined(그 밖 — 끝은 taskRunLast)
  if (taskRun || taskRunChecking) return;
  const job = (state.task || {}).job || "", epoch = state.epoch;
  if (taskCustomKey(job)) { // 조립한 워크플로우 — 시작하기 전에 그 정의를 서버에서 다시 읽는다(taskCatalogRefresh · 붙박이는 안 읽음): 바뀌었거나 지워졌으면 실행하지 않는다(다시 그린 단계를 보고 다시 누른다)
    taskRunChecking = true;
    let R = null;
    try { R = await taskCatalogRefresh(job); } finally { taskRunChecking = false; }
    if (taskRun || epoch !== state.epoch) return { ok: false, text: "그 사이 다른 진행이 시작됐거나 다른 문서를 열어 시작하지 않았습니다" };
    const why = R && (R.gone || R.changed) ? R.why : taskLostWhy(job); // 못 읽었으면(R null) 지금 목록으로 — 목록에 없는 키면 그 까닭
    if (why) { toast(why, true); return { ok: false, text: why }; }
  }
  taskStagesSync();
  const i0 = TASK_STAGES.findIndex((g) => g.id === stageId), i1 = TASK_STAGES.findIndex((g) => g.id === toId), slots = taskSlots(), [plan, report] = (slots || []).map((k) => taskSlotDoc(k));
  if (i0 < 0 || i1 < i0 || !plan || !report) { toast("두 칸(사업계획서 · 연차보고서)에 문서를 먼저 고르세요", true); return; }
  if (!taskStepsLast) taskStepsCalc();
  const leftOf = (g) => taskStageWork(g).filter((s) => !s.done), again = (g) => !!redo && g.id === stageId; // again = 남은 단계가 없어도 도는 묶음(redo 의 단계가 든 것)
  const stages = TASK_STAGES.slice(i0, i1 + 1).filter((g) => leftOf(g).length || again(g)); // 할 일이 남은 묶음만
  if (!stages.length) { toast("남은 단계가 없습니다"); return; }
  const chain = stages.length > 1 ? { to: toId, label: taskChainLabel(stages) } : null;
  // 묶음 하나만 도는 실행은 먼저 서버 쪽 실행기에 맡긴다(workflow_exec.js taskRunServer — spec_워크플로우 ② §18-10 걸음 1: 지금 서버가 맡는 묶음 = 「문서 검토」). 서버가 돌면 창을 닫아도 이어지고
  // 다른 화면 · 첫 화면의 대시보드가 같은 실행을 본다 — 이 화면의 taskRun 은 그 실행의 거울이다. 서버가 맡지 않는 묶음 · 옛 서버 · 끄는 스위치면(null) 아래 화면 실행 그대로.
  // 묶음 연쇄(「이어서 한 번에」 — 걸음 3)도 서버에 from → to 로 맡긴다: 경계마다 최신 상태로 그 묶음을 할지 서버가 정한다(spec_워크플로우 ② §18-4 「범위의 세 진입」) — workflow_exec.js 가 연쇄를 받을 때만(FLOW_CHAIN)
  if ((!chain || typeof FLOW_CHAIN !== "undefined") && typeof taskRunServer === "function") {
    taskRunChecking = true; // 시작 요청이 돌아올 때까지 — 그동안 또 눌러 둘이 시작하지 않게
    let served = null;
    // 서버에는 요청한 끝(toId)까지 — 지금 남은 묶음이 하나여도: 앞 묶음이 뒤 묶음에 일을 만들면 서버가 경계에서 그 묶음도 한다(astra 결과 검토 · ② §18-4)
    const span = typeof FLOW_CHAIN !== "undefined" && toId !== stages[0].id && i1 > TASK_STAGES.indexOf(stages[0]) ? { to: toId, chain: chain || { to: toId, label: taskChainLabel(TASK_STAGES.slice(TASK_STAGES.indexOf(stages[0]), i1 + 1)) } } : {};
    try { served = await taskRunServer(stages[0], plan, report, { redo, only, paid, ...span }); } finally { taskRunChecking = false; }
    if (served && served.follow) return taskRun ? { ok: false, text: "그 사이 다른 진행이 시작됐습니다" } : served.follow();
    if (served) return served; // 서버가 거절(남은 단계 없음 · 문서 칸이 다름 · 정의가 바뀜 …) — 그 글이 알림으로 나갔다
    if (taskRun || epoch !== state.epoch) return { ok: false, text: "그 사이 다른 진행이 시작됐거나 다른 문서를 열어 시작하지 않았습니다" };
  }
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 남은 단계 · 바뀌는 것 · 유료 호출을 적은 확인 창: design.md §18 「확인 창」). sure 는 부르는 쪽 호환으로만 남김
  const run = (taskRun = { stage: stages[0].id, report: report.id, key: (leftOf(stages[0])[0] || { key: redo }).key, note: "", t0: Date.now(), stop: false, chain, redo, only, // only = 그 단계만 하고 끝(줄의 「분석」 · 「다시 분석」 단추 — 뒤의 LLM 단계는 안 돈다)
    paid: Array.isArray(paid) ? new Set(paid) : null });
  taskRunLast = null;
  taskRunEnds = {};
  if (typeof projectControlsSync === "function") projectControlsSync(); // 도는 동안 프로젝트 칸·라운드·구분 기준 버전 줄을 끈다(② §19)
  run.timer = setInterval(() => taskStageSync(), 1000); // 지난 시간 — 글만 바꾼다
  let stage = null, end = null, skip = "", slow = ""; // stage·end = 마지막으로 돈 묶음과 그 끝 · skip = 다음 묶음으로 안 넘어간 까닭 · slow = 묶음 경계에서 자리 연결 목록을 다시 읽지 못함
  for (const g of stages) {
    if (stage) { // 묶음 경계 — 앞 묶음의 결과를 다시 셈해 끝 글을 남기고, 넘어가도 되는지 본다(taskRun 은 그대로 — 초기화·다른 단추는 계속 꺼져 있다)
      // 앞 묶음의 LLM 검증·보완이 분석을 바꿨을 수 있다 — 다른 문서 쪽 자료를 다시 읽고(taskFlowLoad — 자리 연결 목록 다시 읽기를 건다) 그 다시 읽기가 끝나기를 기다린 뒤(상한 3분) 그 목록으로 센다.
      // 전에는 다시 읽기 전의 목록으로 세어, 그 목록이 「정상 0건」(linksNone)이면 「내용 넣기」 의 넣기 계획 · 내용 반영을 끝난 것으로 보고 그 묶음을 건너뛰었다(HEAD 부터 — 2차의 정상 0건 판정으로 넓어짐)
      if (!run.stop && state.id === report.id) {
        run.note = "다음 묶음 셈 — 자리 연결 목록 다시 읽기";
        taskStageSync();
        await taskFlowLoad();
        if (!(await taskWait(() => !taskFlow.linkBusy || run.stop, 180000))) slow = "자리 연결 목록을 다시 읽는 데 너무 오래 걸립니다 — 잠시 뒤 다시 누르세요"; // 「멈춤」 을 누르면 기다리지 않고 아래에서 멈춘다
      }
      taskStepsDraw();
      if (!document.getElementById("taskSteps")) taskStepsCalc(); // 「작업 개요」 가 그려져 있지 않아도 셈은 지금 것으로(leftOf 가 읽는 taskStepsLast)
      taskRunKeep(stage, plan, report, run, end);
      const before = TASK_STAGES.slice(0, TASK_STAGES.indexOf(g)).find((p) => leftOf(p).length);
      if (run.stop) skip = "눌러서 멈췄습니다";
      else if (slow) skip = slow;
      else if (before) skip = `${before.no} 「${before.name}」 이 덜 끝났습니다`;
      if (skip) break;
    }
    const left = leftOf(g);
    if (!left.length && !again(g)) continue; // 앞 묶음을 도는 사이 이미 끝난 묶음
    stage = g;
    Object.assign(run, { stage: g.id, key: (left[0] || { key: redo }).key, note: "", t0: Date.now() });
    taskStageSync();
    try { end = { ok: true, text: await taskRunSteps(run, plan, report) }; }
    catch (e) { end = { ok: false, text: e instanceof TaskHalt ? e.message : `오류 — ${e.message}` }; if (!(e instanceof TaskHalt)) console.error(e); }
    if (!end.ok) break; // 멈춤·실패 — 뒤 묶음은 진행하지 않는다
  }
  clearInterval(run.timer);
  taskRun = null;
  if (typeof projectControlsSync === "function") projectControlsSync(); // 끝났다 — 도는 동안 꺼 둔 프로젝트 칸·버전 줄을 다시 켠다
  taskStepsDraw(); // 끝난 수를 지금 것으로(taskStepsLast)
  taskRunKeep(stage, plan, report, run, end); // 마지막으로 돈 묶음 — 전과 같은 차례(셈한 뒤 남김)
  const box = document.getElementById(stage.dom);
  if (box && !end.ok) box.open = true; // 멈춘 곳이 보이게 세부 목록을 편다
  taskStageSync();
  if (!chain) toast(end.ok ? `${stage.name} — ${end.text}` : `${stage.name}이 멈췄습니다 — ${end.text}`, !end.ok);
  else if (!end.ok) toast(`${chain.label} 이어 진행이 ${stage.no} 「${stage.name}」 에서 멈췄습니다 — ${end.text}`, true);
  else if (skip) toast(`${chain.label} 이어 진행을 ${stage.no}까지만 했습니다 — ${skip}`, true);
  else toast(`${chain.label} 이어 진행 끝 — ${stage.name}: ${end.text}`);
}

// ---- 묶음 「초기화」(spec_작업 ② §14, 2026-11-12 사용자 "새로운 작업을 할려고 했는데 로드되는 파일이 같으니깐 이전 작업이 그대로 들어옴 … 어차피 연차보고서는 원본이 있으니깐 작업 1,2 단계 초기화 할 수 있도록 해줘"):
// 1단계 = 연차보고서를 올린 원본으로 + 2단계 기록 지움(1·2단계 모두 처음으로) · 2단계 = 원본으로 되돌린 뒤 지금 반영된 과제 구성 값으로 구조를 다시 반영 + 2단계 기록 지움 — POST …/merge-links/reset.
// 사업계획서·과제 구성 입력 값·헤딩·표 분석·확정 기록은 그대로. 실행 취소로 못 되돌린다(확정 복원과 같은 길) — 누를 때 한 번 확인.
let taskResetting = null; // 초기화 도는 중인 묶음 id
function taskResetCan(stage) { // → {ok, why} — 되돌릴 것이 있는가(읽어 둔 상태로 셈 — 서버는 할 일이 없으면 그대로 둔다)
  const report = taskSlotDoc("report");
  if (!report) return { ok: false, why: "연차보고서 칸이 비어 있습니다" };
  const B = taskDivOf(report), K = (taskFlow.links && taskFlow.links.kept) || {}, F = taskFlow.fill || {};
  const framed = !!(B && B.applied), mapped = !!(K.links || K.tables || K.maps || K.applied || K.llm || F.plan || F.done);
  if (stage.id === "map") return framed ? (mapped ? { ok: true } : { ok: false, why: "내용 넣기 기록(자리 연결에서 고른 것 · LLM 검토 · 넣은 내용)이 없습니다" }) : { ok: false, why: "구조 반영 전입니다" };
  const edited = report.id === state.id ? !!(state.base || isDirty()) : !!(report.edited || report.commits);
  return framed || mapped || edited ? { ok: true } : { ok: false, why: "연차보고서가 올린 원본 그대로이고 내용 넣기 기록도 없습니다" };
}
const TASK_RESET_KEEP = "그대로 남는 것: 사업계획서 · 프로젝트 구성 입력 값 · 헤딩·표 분석 · 확정 기록";
async function taskReset(stageId) {
  const stage = TASK_STAGES.find((g) => g.id === stageId), report = taskSlotDoc("report");
  if (!stage || !report || taskRun || taskResetting) return;
  const RN = taskStageName; // 묶음 이름(§21 — 전의 글은 「1단계 · 2단계 · 3단계」 로 박혀 있었다 · 조립한 TASK 는 제 번호로)
  const gone = `· ${RELAY_STAGE_META.map.name} 기록(자리 연결에서 고른 것 · LLM 검토 결과 · 표 짝 · 표 대응 · 넣은 기록)을 지웁니다.\n`;
  const ask = stageId === "frame"
    ? `${RN("frame")} · ${RN("map")} 를 처음으로 되돌릴까요?\n\n· 연차보고서 「${report.name}」 를 올린 원본으로 되돌립니다 — 구조 반영 · 넣은 내용 · 직접 고친 글이 모두 없어지고, ${RELAY_STAGE_META.clean.name}에서 지운 작성요령은 돌아옵니다.\n${gone}`
    : `${RN("map")} 를 처음으로 되돌릴까요?\n\n· 연차보고서 「${report.name}」 를 올린 원본으로 되돌린 뒤 구조를 지금 반영된 프로젝트 구성 값으로 다시 반영합니다 — 넣은 내용 · 직접 고친 글이 없어지고, ${RELAY_STAGE_META.clean.name}에서 지운 작성요령은 돌아옵니다.\n${gone}`;
  if (!confirm(`${ask}\n${TASK_RESET_KEEP}\n\n실행 취소로 되돌릴 수 없습니다 — 지금 상태가 필요하면 취소하고 먼저 「저장」으로 받아 두거나 「고친 문단」 탭에서 확정하세요.`)) return;
  if (state.id !== report.id) { // 연차보고서를 고치는 문서로(「한 번에 진행」·onReport 와 같은 길 — 두 문서의 자리는 그대로)
    await openWork(report.id);
    if (state.id !== report.id) return; // 바꾸지 않음(저장 안 한 글을 두고 그만둠) · 못 엶
    showTab("Div");
  }
  if (state.busy) { toast("편집을 반영하는 중입니다 — 잠시 뒤 다시 눌러 주세요"); return; }
  const id = state.id, epoch = state.epoch;
  await flushAll();
  if (epoch !== state.epoch) return;
  taskResetting = stageId;
  taskStageSync();
  setSaveState("busy", stageId === "frame" ? "연차보고서를 올린 원본으로 되돌리는 중…" : "원본으로 되돌리고 구조를 다시 반영하는 중…");
  try {
    const d = await api(`/api/docs/${id}/merge-links/reset`, JSON_POST({ stage: stageId }));
    if (epoch !== state.epoch) return;
    const r = d.reset || {}, reframe = r.reframe || {};
    taskRunLast = null;
    taskRunEnds = {};
    if (heads.dlg === "links" || heads.dlg === "fill") headsColClose(true); // 지운 연결 목록 · 넣기 계획
    adoptBase(d, true); // 문서·기준·구분 기준 적용 상태가 바뀜 — 다시 그리고 이관 자료(taskFlow)를 새로 읽는다(divReset)
    const FR = RN("frame"), MP = RN("map");
    if (reframe.error) toast(`원본으로 되돌렸지만 구조를 다시 반영하지 못했습니다: ${reframe.error} — ${FR}부터 다시 진행하세요`, true);
    else if (!r.restored && !(r.cleared || []).length) toast("이미 처음 상태입니다 — 바뀐 것이 없습니다");
    else toast(stageId === "frame" ? `${FR}·${MP}를 처음으로 되돌렸습니다 — 연차보고서는 올린 원본입니다(확정한 프로젝트 구성 · 헤딩·표 분석은 그대로)` : `${MP}를 처음으로 되돌렸습니다 — 연차보고서는 구조만 반영된 상태입니다(${FR} 의 「헤딩 · 표 다시 분석」 이 남습니다)`);
  } catch (e) {
    if (epoch === state.epoch) toast(`초기화하지 못했습니다: ${e.message}`, true);
  } finally {
    taskResetting = null;
    if (epoch === state.epoch) {
      commitBar(); refreshSaveState(); commitsLoad(); loadWorks(); logTouched();
      if (!$("paneDiv").hidden) divShow(); else taskStageSync();
    }
  }
}

// ---- 3단계 「문서 정리」 ⑥ 작성요령 삭제(spec_작업 ② §14 「3단계」 — 2026-11-12 사용자 "3단계에 작성요령 삭제 기능을 넣어줘" → "그냥 위 첨자, 작성요령이 테이블 첫번째 줄에 있는 경우,
// ※ 2page 이내 요약 작성.. 당구장 표시랑 색이랑 폰트가 같은 경우 정도만 삭제해도 되겠고만"): 양식 안내 지우기(app/form_cleanup.py · API GET/POST …/form-cleanup — 한 구조 편집 · 실행 취소 1).
// 지우는 패턴 목록(2026-11-12 사용자 "문서 정리에는 어떤 패턴을 삭제해야하는지 목록이 있어야함") — 원본은 서버 app/form_cleanup.py PATTERNS(GET …/form-cleanup 의 patterns:
// 작성 요령 표 · <참고 N> 자료 · ※ 안내 · 위첨자 각주 번호). 목록은 지금 문서에서 스크립트로 센다(헤딩 추출 결과에 기대지 않음 — 문서가 바뀌어도 다시 하라고 할 일이 없다)
const CLEANUP_NAMES = [["tables", "작성 요령 표"], ["refs", "<참고 N> 자료"], ["notes", "※ 안내"], ["marks", "위첨자 각주 번호"]]; // 목록을 읽기 전(단계 안내 글)에만 — 읽으면 서버 것
const cleanupPatterns = () => (taskFlow.cleanup || {}).patterns || CLEANUP_NAMES.map(([key, name]) => ({ key, name }));
const cleanupNames = () => cleanupPatterns().map((p) => p.name).join(" · ");
const taskCleanupText = (n, done = false) => cleanupPatterns()
  .filter((p) => n[p.key]).map((p) => `${p.name} ${nf(n[p.key])}`).join(" · ") + (done ? "을(를) 지웠습니다" : "");
async function taskCleanupLoad(report) { // 지울 안내 수를 읽어 둔다(taskFlow.cleanup) — 단계 목록만 다시 그림
  const flow = taskFlow;
  try { flow.cleanup = await api(`/api/docs/${report.id}/form-cleanup`); }
  catch (e) { flow.cleanup = { error: e.message }; }
  if (flow === taskFlow) taskStepsDraw();
  return flow.cleanup;
}
async function taskCleanupRun({ quiet = false, run = null } = {}) { // ⑥ — 지금 문서로 다시 셈 → (확인) → 한 번에 지움. 연차보고서가 지금 문서일 때(onReport · 한 번에 진행). → 끝 글 | null(그만둠). 실패는 예외
  const report = taskSlotDoc("report"), flow = taskFlow, epoch = state.epoch;
  if (!report || report.id !== state.id) throw new Error("연차보고서가 지금 문서가 아닙니다");
  await flushAll(); // 고치던 글을 먼저 서버에 — 서버 문서로 센다
  const C = await taskCleanupLoad(report);
  if (C.error) throw new Error(C.error);
  if (epoch !== state.epoch || flow !== taskFlow || (run && (taskRun !== run || run.stop))) return null;
  if (!C.counts.total) return "지울 안내가 없습니다";
  // 확인 창 없이 바로 지운다(2026-11-18 사용자 「이런 알람좀 주지마」 — 실행 취소 한 번으로 되돌림: design.md §18 「확인 창」)
  flow.guide = { busy: true };
  taskStepsDraw();
  state.busy = true;
  refreshToolbar();
  let r;
  try { r = await api(`/api/docs/${report.id}/form-cleanup`, JSON_POST({ expectRev: C.rev })); }
  finally { state.busy = false; refreshToolbar(); }
  if (epoch !== state.epoch) return null;
  if (r.nothing) { flow.guide = {}; await taskCleanupLoad(report); return "지울 안내가 없습니다"; }
  state.localRev += 1;
  state.structRev = state.localRev; // 표 판정 캐시(tables.js)도 새로
  applyEditState(r);
  await reloadDoc(); // 떨어진 자리 여러 곳이 바뀌어 문서를 다시 읽는다
  if (heads.dlg === "cleanup") headsColClose(true);
  flow.guide = { done: r.done };
  await taskCleanupLoad(report);
  const left = (flow.cleanup && flow.cleanup.counts && flow.cleanup.counts.total) || 0;
  return `${taskCleanupText(r.done, true)}${(r.done.skipped || []).length ? ` · 건너뜀 ${nf(r.done.skipped.length)}` : ""}${left ? ` · 남은 안내 ${nf(left)}` : ""}`;
}
async function taskCleanup() { // ⑥ 단추 「작성요령 삭제」
  const flow = taskFlow;
  if ((flow.guide || {}).busy || taskRun) return;
  try {
    const text = await taskCleanupRun();
    if (text) toast(`작성요령 삭제 — ${text} · 실행 취소 한 번으로 되돌릴 수 있습니다`);
  } catch (e) {
    toast(e.status === 422 ? `표준 검사에 걸려 되돌렸습니다: ${e.message}` : e.status === 409 ? `${e.message}` : `지우지 못했습니다: ${e.message}`, true);
  } finally {
    if (flow === taskFlow && flow.guide) flow.guide.busy = false;
    taskStepsDraw();
  }
}
function taskCleanupList() { // ⑥ 「목록 보기」 — 2열 「작성요령 삭제 — 지울 안내」(kind "cleanup"): 지우는 패턴(패턴 · 찾는 것 · 처리 · 보기 · 찾은 수) + 지울 자리(종류 · 글 · 처리 — 줄을 누르면 문서의 그 자리로, ↑/↓ 로 다음 줄 — hRowKeys)
  const C = taskFlow.cleanup, report = taskSlotDoc("report");
  if (!C || C.error || !C.counts || !report) return;
  const mine = report.id === state.id;
  const { tools, body, foot } = headsDlg("cleanup", "작성요령 삭제 — 지울 안내", `${report.name} · ${mine ? "줄을 누르면 문서의 그 자리로" : "연차보고서를 열면 줄을 눌러 그 자리로 갑니다"}`);
  tools.append(el("span", "muted", C.counts.total ? taskCleanupText(C.counts) : "지울 안내가 없습니다"));
  body.append(el("div", "lk-cap", "지우는 패턴 — 이 목록에 있는 것만 지웁니다(없는 안내 · 본문 색 ※ 줄 · 쓸 자리는 남김)"));
  const [ptbl, ptb] = hTable(["패턴", "찾는 것 → 처리", "찾은 수"]); // 좁은 열 — 칸 셋(이름 아래 보기 · 찾는 것 아래 처리)
  ptbl.classList.add("lk-table");
  for (const p of cleanupPatterns()) {
    const tr = el("tr"), name = el("td"), rule = el("td");
    name.append(el("strong", null, p.name), el("div", "muted", `보기: ${p.example}`));
    rule.append(el("div", null, p.rule), el("div", "muted", `→ ${p.how}`));
    tr.append(name, rule);
    hCell(tr, nf(C.counts[p.key] || 0), "lk-nw");
    ptb.append(tr);
  }
  body.append(ptbl);
  if (!C.counts.total) { foot.append(hBtn("닫기", () => headsColClose())); return; }
  body.append(el("div", "lk-cap", "지울 자리"));
  const [tbl, tb] = hTable(["종류", "글", "처리"]);
  tbl.classList.add("lk-table");
  const row = (kind, text, how, id) => {
    const tr = el("tr", mine ? "go" : null);
    hCell(tr, kind, "lk-nw");
    hCell(tr, text);
    hCell(tr, how); // 줄바꿈 허용 — 「※ 앞 「…」 은 남김」 이 길면 글 칸이 한 글자 폭으로 눌렸다(좁은 열)
    if (mine) { tr.tabIndex = 0; tr.onclick = () => { for (const x of tb.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); divGo({ key: id }, false); tr.focus({ preventScroll: true }); }; }
    tb.append(tr);
  };
  for (const t of C.tables) row("작성 요령 표", t.label, `표째(${t.rows}행)`, t.id);
  for (const r of C.refs || []) row("<참고 N> 자료", r.label, `제목 줄과 표 ${r.tables}개째`, r.id);
  for (const n of C.notes) row("※ 안내", n.guide, n.whole ? "문단째" : `※ 앞 「${short(n.text.slice(0, n.text.indexOf("※")).trim(), 24)}」 은 남김`, n.id);
  for (const m of C.marks) row("위첨자", m.text, "글자만", m.id);
  hRowKeys(tb);
  body.append(tbl);
  foot.append(el("span", "muted", "한 번의 편집으로 지우고 실행 취소 한 번으로 되돌립니다"),
    hBtn("작성요령 삭제", () => { headsColClose(); taskCleanup(); }, { cls: "btn sm primary", disabled: !mine || !!(taskFlow.guide || {}).busy, title: mine ? "" : "연차보고서를 고치는 문서로 연 뒤에" }),
    hBtn("닫기", () => headsColClose()));
}

function docNameSync(name) { // 지금 문서의 보이는 이름(spec_작업 ② §10)이 바뀌었으면 상단 바·패널 머리의 이름도 함께 → 바뀌었는가
  if (!name || name === state.name) return false;
  state.name = name;
  $("fileName").textContent = $("fileName").title = name;
  toolDocDraw(); // 패널 머리 「작업」 옆 문서 자리(도움말 = 이 이름)
  return true;
}

function docSwitchDraw(list) { // 상단 바 문서 목록 — 파일 이름 자리가 목록이 된다(지금 문서가 고른 것): 과제로 묶인 문서면 그 프로젝트의 문서만, 아니면 올린 문서 전부. 이름 뒤에 첨부 파일 종류·할 일
  worksList = list;
  const sel = $("docSwitch"), cur = list.find((w) => w.id === state.id), others = taskProject() ? taskMates(list) : list.filter((w) => w.id !== state.id);
  if (cur) docNameSync(cur.name); // 지금 문서의 보이는 이름이 바뀜(목적 문서는 프로젝트 이름이 뒤에 붙는다 — spec_작업 ② §10: 프로젝트 이름·칸을 바꾼 바로 뒤)
  const tag = (w) => [w.name, taskName("file", (w.task || {}).file) || taskName("kind", (w.task || {}).kind), taskName("job", (w.task || {}).job)].filter(Boolean).join(" · ");
  sel.replaceChildren(...(cur ? [new Option(cur.name, cur.id)] : []), ...others.map((w) => new Option(tag(w), w.id)));
  sel.value = state.id || "";
  sel.title = (cur ? `${cur.name}\n` : "") + (taskProject() ? `프로젝트 「${taskProject()}」 의 문서 목록 — 고르면 그 문서를 엽니다(다른 문서는 「작업」 단추)` : "올린 문서(작업) 목록 — 고르면 그 문서를 엽니다"); // 첫 줄 = 지금 문서의 전체 이름(칸이 210px 라 잘린다 — document_header.css)
  sel.hidden = !cur || !others.length;
  $("fileName").hidden = !sel.hidden;
  sel.onchange = () => { const id = sel.value; sel.value = state.id; if (id !== state.id) { if (id === peerShown()) toolDocSet(id); else openWork(id); } }; // 못 열면(취소 등) 지금 문서 그대로 · 옆에 떠 있는 문서면 「도구」 로 고른 것과 같게(두 면이 바꿈 — 보던 곳 그대로)
  const flow = document.getElementById("taskFlow"); // 이관의 칸(② §11) — 목록이 늦게 왔거나 칸의 문서가 달라졌으면 다시 그리고 읽는다
  if (flow && taskSlots() && flow.dataset.key !== taskFlowKey()) { flow.replaceWith(taskFlowEl()); taskFlowLoad(); }
  if (gatherOn()) gatherWorks(); // 취합 — 문서를 열었거나 취합본 칸의 문서가 달라졌으면 취합 상태를 다시 읽는다(둘째 면의 탭이 그것을 본다 — gather.js)
  peerSync(); // 같이 보기 열(② §12) — 문서·칸·할 일이 바뀌면 옆 문서도 따라
}

// ---- 같이 보기(spec_작업 ② §12, 2026-11-11 사용자 "이 상태에서 사업계획서랑 같이 봐야") — 이관의 다른 칸 문서를 문서 열 옆(#peerCol)에 읽기 전용으로.
// 옆 문서 = 같은 앱을 /?peek=<작업 id>#w=<작업 id> 로 연 iframe(PEEK — 맨 위). 켜고 끈 것은 이 브라우저에 기억(nfm.peer — 기본 켬), 고른 칸은 이 화면에서만(peerKind).
const PEER_KEY = "nfm.peer";
let peerKind = null; // 칸 단추로 고른 칸(plan|report) — 지금 문서가 어느 칸에도 없을 때 어느 문서를 띄울지
let peerPick = null; // 문서 이름 탭으로 고른 작업 id(이 화면에서만) — 칸 단추를 누르면 비운다
const peerOn = () => { try { return localStorage.getItem(PEER_KEY) !== "off"; } catch { return true; } };
const peerShown = () => ($("peerCol").hidden ? "" : $("peerFrame").dataset.w || ""); // 옆에 떠 있는 작업 id("" = 없음)
function peerDocs() { // 둘째 면에 띄울 수 있는 문서(문서 이름 탭의 차례) — 이관의 칸 문서(칸 차례) 다음에 같은 프로젝트의 다른 문서. 지금 문서는 뺀다 · 이관이 아니면 없음
  if (gatherOn()) return gatherPeerDocs(); // 취합 — 그 취합에 든 기관 문서(들어온 차례 · 기관 문서를 열어 보는 중이면 취합본이 맨 앞 — gather.js, spec_취합 ② §5 「둘째 면」)
  const slots = taskSlots(), P = taskProject(), out = [];
  if (!slots) return out;
  const add = (w) => { if (w && w.id !== state.id && !out.some((x) => x.id === w.id)) out.push(w); };
  for (const k of slots) add(taskSlotDoc(k));
  if (P) for (const w of worksList) if (taskSameScope(w)) add(w);
  return out;
}
function peerDoc(docs = peerDocs()) { // 그 가운데 띄울 문서 — 탭으로 고른 것 → 칸 단추로 고른 칸의 것 → 맨 앞
  const slot = peerKind && taskSlots() ? taskSlotDoc(peerKind) : null;
  return docs.find((w) => w.id === peerPick) || (slot && docs.find((w) => w.id === slot.id)) || docs[0] || null;
}
function peerSync() { // 옆 열을 지금 상태에 맞춘다 — 작업 목록을 읽은 뒤(docSwitchDraw) · 칸 단추 · 문서 이름 탭 · ✕ · 문서를 닫을 때
  const col = $("peerCol"), f = $("peerFrame"), docs = !PEEK && state.id && peerOn() ? peerDocs() : [], w = peerDoc(docs), id = w ? w.id : "";
  if ((f.dataset.w || "") !== id) { f.dataset.w = id; f.src = id ? `/?peek=${id}#w=${id}` : "about:blank"; } // peek 값이 달라야 iframe 이 새로 읽는다(# 뒤만 바뀌면 안 읽음)
  if (w) { $("peerName").textContent = peerLabel(w); peerTabsDraw(docs, id); if (colFolded("peer")) colRailName("peer"); }
  if (typeof docStatusPeer === "function") docStatusPeer(id); // 둘째 면 머리의 분석 상태(doc_status.js — spec_작업 ② §20)
  if (col.hidden === !!w) { col.hidden = !w; if (!w) col.classList.remove("folded"); colsApply(); } // 열이 생기거나 없어진 만큼 다른 열 폭을 문서 보기 몫 안으로
  peerOpenMark();
  for (const b of document.querySelectorAll("[data-task-peer]")) peerBtn(b);
  if (typeof gatherPeerMark === "function") gatherPeerMark(); // 취합의 같이 보기 단추 · 둘째 면의 문서가 바뀌면 끌어 넣기 표시를 걷는다(gather.js)
  if (typeof peerQuickSync === "function") peerQuickSync(); // 둘째 면 이름 줄의 표시 아이콘(doc_quick.js — 그 면의 문서가 바뀌면 그 화면이 다 그린 뒤 다시 알린다)
}
function peerSet(on) { // 켜고 끔(기억) — 켤 때는 접힌 열도 편다
  try { localStorage.setItem(PEER_KEY, on ? "on" : "off"); } catch { /* 기억만 안 함 */ }
  if (on) colFold("peer", false);
  peerSync();
}
function peerBtn(b) { // 칸 단추의 켜짐·눌림·도움말 — 만들 때 · peerSync
  const k = b.dataset.taskPeer, w = taskSlotDoc(k), name = taskName("file", k), on = !!w && w.id === peerShown();
  b.disabled = !w || w.id === state.id;
  b.setAttribute("aria-pressed", on);
  b.title = !w ? `${name} 칸이 비어 있습니다` : w.id === state.id ? "지금 보는 문서입니다 — 다른 칸의 문서를 옆에 같이 볼 수 있습니다"
    : on ? `${name} 같이 보기 닫기` : `${name} 같이 보기 — 문서 옆 열에 읽기 전용으로 엽니다\n${w.name}`;
}
function taskSlotPeer(kind) { // 첨부 파일 칸 오른쪽(폴더 단추 다음)의 「같이 보기」 단추 — 그 칸의 문서를 문서 열 옆에 띄우거나 닫는다
  const b = el("button", "icon dv-flow-up dv-flow-peer");
  b.type = "button";
  b.dataset.taskPeer = kind;
  b.setAttribute("aria-label", `${taskName("file", kind)} 같이 보기`);
  b.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/></svg>';
  b.onclick = (e) => {
    e.preventDefault(); // label 안이라 — 누름이 select 로 넘어가지 않게
    const w = taskSlotDoc(kind), on = !!w && w.id === peerShown();
    peerKind = kind;
    peerPick = null; // 칸 단추가 문서 이름 탭으로 고른 것을 이긴다
    peerSet(!on);
  };
  peerBtn(b);
  return b;
}
// ---- 두 면(② §12 「두 면」, 2026-11-11 사용자 "첫째 둘째 높이가 안맞아 2행을 같이 써야" → 「줄은 위에 한 번, 이름 줄 없이」 · "두번째 면은 여러 문서가 들어 갈 수 있으니깐 문서 이름을 탭으로" ·
// "도구는 하나로 둘다 선택할 수 있게" · "두 면이 같은 크기로 항상 보였으면 좋겠는데") — 탭 줄·편집 도구 줄은 두 문서 위에 한 번(style.css workspace 절), 둘째 면의 머리는 문서 이름 탭 줄(peerTabsDraw).
// 두 면은 **늘 같은 크기**: 폭은 반반(style.css — .peer-open 이면 문서 칸·둘째 면 칸이 모두 1fr), 보기는 첫째 면의 것을 둘째 면이 그대로 따른다(peerViewSync → 그 화면의 viewFollow:
// 배율·2쪽 보기·쪽 번호·휠 쪽 넘김). 도구 줄은 하나 — 「페이지 보기」 묶음은 두 문서에 함께 듣고, 글자·문단·표 묶음과 도구 탭(패널)은 첫째 면(고치는 문서)의 것.
const peerLabel = (w) => (gatherOn() && typeof gatherPeerLabel === "function" && gatherPeerLabel(w)) || w.name; // 탭 글 — 취합의 기관 문서는 반영할 기관 이름(spec_취합 ② §5 「둘째 면」), 그 밖은 파일 이름
function peerTabsDraw(docs, id) { // 둘째 면 머리의 문서 이름 탭 — 띄울 수 있는 문서마다 하나, 고른 탭 = 떠 있는 문서. 누르면 그 문서로 바꾼다
  const job = (state.task || {}).job, role = (w) => taskDocRole(w.task, job); // 목적 문서 표시(docRoleDraw 위) — 탭 글은 peerLabel, 꼬리표는 data-role → CSS ::before
  const seen = {}, labels = docs.map((w) => { const t = peerLabel(w); if (t === w.name) return t; const n = (seen[t] = (seen[t] || 0) + 1); return n > 1 ? `${t} (${n})` : t; }); // 같은 기관 문서가 둘이면 (2) · (3) — 파일 이름 탭은 그대로
  const box = $("peerTabs"), key = docs.map((w, i) => `${w.id}:${w.name}:${labels[i]}:${(w.task || {}).file || ""}:${role(w)}`).join("|") + "#" + id;
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.textContent = "";
  for (const [i, w] of docs.entries()) {
    const on = w.id === id, kind = (w.task || {}).file, r = role(w), label = labels[i], b = el("button", "tab" + (on ? " active" : ""));
    b.type = "button";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
    b.dataset.peerDoc = w.id;
    if (r) b.dataset.role = r;
    if (label !== w.name) b.dataset.peerOrg = label; // 반영할 기관 이름을 단 탭(화면 검사가 본다)
    b.title = (r ? `[${DOC_ROLE[r][0]}] ` : "") + (label !== w.name ? `반영할 기관 ${label}\n` : "") + w.name + (kind ? ` — ${taskName("file", kind)}` : "") + (on ? "\n둘째 면에 떠 있는 문서(읽기 전용 — 고치려면 편집 문서 위 파일명 목록에서 이 문서를 엽니다)" : "\n누르면 둘째 면에 이 문서를 띄웁니다");
    b.append(el("span", null, label));
    b.onclick = () => { peerPick = w.id; peerKind = null; peerSync(); };
    box.append(b);
  }
}
function peerOpenMark() { // 둘째 면이 펴져 있는지를 .workspace 에 적는다(.peer-open — 두 면 폭 반반 · 편집 도구 줄이 두 문서 위에 걸침) — peerSync · colFold("peer")
  const col = $("peerCol"), ws = document.querySelector(".workspace"), open = !col.hidden && !col.classList.contains("folded");
  ws.classList.toggle("peer-open", open);
  ws.classList.toggle("peer-left", open && peerLeft()); // 두 면의 좌우 = 이관의 칸 차례(style.css .peer-left) — 어느 문서를 고치고 있든 사업계획서 왼쪽 · 연차보고서 오른쪽
  toolDocDraw(); // 상단 바 「도구」 · 패널 머리의 문서 자리 — 두 문서가 나란히 보일 때만 단추 둘(② §12 「도구는 문서마다」)
}
function peerLeft() { // 둘째 면이 왼쪽에 올 때 = 떠 있는 문서가 지금 문서보다 앞 칸(사업계획서)일 때(2026-11-11 사용자 "구지 순서를 바꿀 필요가 있을까?" — 고치는 문서를 바꿔도 두 문서의 자리는 그대로). 둘 다 칸의 문서일 때만
  if (gatherOn()) return gatherPeerLeft(); // 취합 — 취합본이 늘 왼쪽(둘째 면에 뜬 것이 취합본일 때만 둘째 면이 왼쪽 — gather.js)
  const slots = taskSlots(), id = peerShown();
  if (!slots || !id) return false;
  const at = (wid) => slots.findIndex((k) => (taskSlotDoc(k) || {}).id === wid), a = at(id), b = at(state.id);
  return a >= 0 && b >= 0 && a < b;
}
function peerViewSync() { // 둘째 면의 보기 = 첫째 면의 보기(같은 크기) — 배율이 바뀐 뒤(setZoom 끝) · 2쪽 보기·쪽 번호·휠 쪽 넘김을 바꾼 뒤 · 둘째 면 화면이 문서를 다 그린 뒤(그 화면이 parent 로 부름)
  if (PEEK || $("peerCol").hidden || !state.id) return;
  const view = { zoom: state.zoom, twoUp: state.twoUp, pages: !$("doc").classList.contains("hide-pages"), wheel: state.wheelFlip };
  let fw = null;
  try { fw = $("peerFrame").contentWindow; fw.viewFollow(view); } catch { return; /* 아직 여는 중 — 다 그리면 그 화면이 다시 부른다 */ }
  const want = peerSpotWant; // 도구를 쓸 문서를 바꾼 뒤(toolDocSet) — 둘째 면이 옛 첫째 면의 문서를 다 그렸으면 그 보던 곳으로
  if (want && want.w === peerShown()) { try { if (fw.peekId() === want.w) { peerSpotWant = null; fw.spotHold(want.at); } } catch { /* 다음 부름에 */ } }
}
function viewFollow(v) { // 둘째 면 화면(PEEK)에서만: 바깥(첫째 면)의 보기를 그대로 — 배율은 맞춤 없이 그 값(제 폭으로 다시 맞추지 않는다 — 두 면의 쪽 크기가 같게). 맨 위에 있었으면 맨 위 그대로
  if (!PEEK || !state.id || $("scroller").hidden) return;
  const doc = $("doc"), sc = $("scroller"), z0 = state.zoom, top = sc.scrollTop < 1;
  const two = state.twoUp !== !!v.twoUp, pages = doc.classList.contains("hide-pages") === !!v.pages;
  state.wheelFlip = !!v.wheel;
  if (two) { state.twoUp = !!v.twoUp; doc.classList.toggle("two-up", state.twoUp); }
  if (pages) doc.classList.toggle("hide-pages", !v.pages);
  if (state.zoom !== v.zoom || state.fit !== null) { keepCenter(() => setZoom(v.zoom, null)); if (top) sc.scrollTop = 0; }
  if (two || pages || state.zoom !== z0) zoomMarksDraw(); // 쪽 여백 표시는 배율·쪽 표시에 맞춰 다시(배율을 뒤에서 바꾸는 중이면 끝난 뒤 한 번)
}
function peerGo(w, id) { // 옆 문서가 w 면 그 자리(문단·칸 id)로 — 연결 목록에서. 아직 여는 중이면 지나간다
  if (!w || !id || peerShown() !== w.id) return;
  try { $("peerFrame").contentWindow.divGo({ key: id }); } catch { /* 아직 여는 중 */ }
}
function peekId() { return state.id || ""; } // 둘째 면 화면이 지금 그린 문서(바깥이 묻는다 — iframe 이 다른 문서로 넘어가는 동안 옛 화면에 말하지 않게)

// ---- 도구를 쓸 문서(② §12 「도구는 문서마다」 — 2026-11-19 사용자 "원본, 목적문서가 따로면 도구도,, 따로 따로 적용하ㄹ수 있게 해야지" →
// "어차피 task 옆에 문서 넣을 수 있는 곳이 있지.. 구지 꼭풀 네임을 넣을 필요 없어. 그리고 여기 상단에 도구를 문서별로 돌릴 수 있는 기능도 넣어주면 될듯" · 이름 줄 "이 행도 … 요청사항과 맞게"):
// 두 면에 문서가 떠 있으면 상단 바 「도구」(#toolDocBar — 줄 접기 묶음 옆)와 패널 머리 「작업」 옆(#toolSource — 전의 긴 파일 이름 자리)에 두 문서의 짧은 이름 단추(「원본」 · 「목적」 — 화면 차례).
// 눌린 문서 = 도구(편집 도구 줄 · 패널 탭 · 진행표)를 쓰는 문서 = 고치는 문서(첫째 면). 다른 문서를 누르면 두 면이 문서를 바꾼다(toolDocSet) — 좌우 자리 · 두 문서의 보던 곳 · 패널에서 보던 탭은 그대로.
// 두 곳은 늘 같은 값이다(toolDocDraw 한 함수가 함께 그린다 — design.md §10 「같은 것을 두 곳에」 의 예외: 사용자가 두 자리를 다 말함). 이름 줄의 표시 아이콘은 면마다 그 문서에 듣는다(doc_quick.js · quickKey)
let toolDocBusy = false; // 바꾸는 중(두 문서를 다시 읽는 동안 단추를 끈다)
let peerSpotWant = null; // {w, at} — 문서를 바꾼 뒤 둘째 면이 w 를 다 그리면 갈 자리(viewSpot — 바꾸기 전 첫째 면에서 보던 곳)
function toolDocList() { // [{id, short, title, on}] — 두 면의 문서(화면 왼쪽 → 오른쪽). 둘째 면이 없거나 띠로 접혀 있으면 [](두 문서가 나란히 보일 때만)
  const pid = peerShown();
  if (PEEK || !state.id || !pid || pid === state.id || $("peerCol").classList.contains("folded")) return []; // pid === state.id = 막 바꾼 사이(둘째 면이 아직 옛 문서 — 곧 peerSync)
  const job = (state.task || {}).job, pw = worksList.find((w) => w.id === pid) || { id: pid, name: $("peerName").textContent || "", task: null };
  const one = (id, name, t, on, label = "") => {
    const r = taskDocRole(t, job), d = DOC_ROLE[r];
    return { id, on, short: label || (d ? d[1] : name), title: `${d ? `${d[0]} — ` : ""}${name}\n` + (on ? "지금 도구(편집 도구 줄 · 패널 · 진행표)를 쓰는 문서입니다(고치는 문서)"
      : "누르면 도구(편집 도구 줄 · 패널 · 진행표)를 이 문서에 씁니다 — 이 문서가 고치는 문서가 되고, 지금 문서는 옆에 읽기 전용으로. 두 문서의 자리 · 보던 곳 · 패널 탭은 그대로") };
  };
  const plabel = peerLabel(pw), mine = one(state.id, state.name, state.task, true), peer = one(pid, pw.name, pw.task, false, plabel !== pw.name ? plabel : ""); // 취합의 기관 문서는 반영할 기관 이름(peerLabel)
  return document.querySelector(".workspace").classList.contains("peer-left") ? [peer, mine] : [mine, peer];
}
function toolDocBtns(list) { // 단추 묶음 — 상단 바 · 패널 머리가 같은 꼴
  return list.map((d) => {
    const b = el("button", "btn sm tool-doc-btn" + (d.on ? " on" : ""), d.short);
    b.type = "button";
    b.dataset.toolDoc = d.id;
    b.title = d.title;
    b.setAttribute("aria-pressed", String(d.on));
    b.disabled = toolDocBusy;
    b.onclick = () => toolDocSet(d.id);
    return b;
  });
}
function toolDocDraw() { // 상단 바 「도구」 · 패널 머리의 문서 자리 — peerOpenMark(peerSync · 둘째 면 접기) · showTab · docNameSync · 바꾸는 동안
  if (PEEK) return;
  const bar = $("toolDocBar"), src = $("toolSource");
  if (!state.id) { bar.hidden = true; src.replaceChildren(); src.removeAttribute("data-key"); return; } // 문서를 닫음(시작 화면) — 이 줄 아래의 let 들보다 먼저 불릴 수 있다(스크립트를 읽는 동안)
  const list = toolDocList(), cmp = $("panel").dataset.tool === "Compare";
  const role = state.id ? taskDocRole(state.task) : "", key = JSON.stringify([list, toolDocBusy, cmp, state.id, state.name, role]);
  if (src.dataset.key === key) return;
  src.dataset.key = key;
  bar.hidden = !list.length;
  bar.replaceChildren(el("span", "tool-doc-name", "도구"), ...toolDocBtns(list));
  src.replaceChildren();
  src.classList.toggle("tool-doc", !cmp && list.length > 0);
  if (!cmp && list.length) { src.title = ""; src.setAttribute("role", "group"); src.setAttribute("aria-label", "도구를 쓸 문서"); src.append(...toolDocBtns(list)); return; }
  src.removeAttribute("role"); src.removeAttribute("aria-label");
  const d = DOC_ROLE[role]; // 문서 하나 — TASK 의 원본 · 목적 문서면 그 이름(「목적 문서」 — 긴 파일 이름은 문서 위 이름 줄에 있다), 아니면 파일 이름
  src.textContent = cmp ? "여러 문서 · 저장된 분석 결과" : d ? d[0] : state.name || "";
  src.title = cmp ? "작업 목록에서 비교할 문서를 선택하세요" : state.name || "";
}
async function toolDocSet(id, then = null) { // 도구를 쓸 문서를 둘째 면의 문서 id 로 — 두 면이 문서를 바꾼다. then = 바꾼 뒤 할 일(둘째 면 이름 줄의 분석 상태를 누른 것 — doc_status.js)
  if (PEEK || toolDocBusy || !state.id || !id) return;
  if (id === state.id) { if (then) then(); return; }
  if (id !== peerShown()) return;
  let atPeer = null;
  try { const fw = $("peerFrame").contentWindow; if (fw.peekId() === id) atPeer = fw.viewSpot(); } catch { /* 아직 여는 중 — 맨 위부터 */ }
  const was = state.id, atMine = viewSpot(), tool = $("panel").dataset.tool, pick0 = peerPick, kind0 = peerKind, z0 = state.zoom, fit0 = state.fit; // 배율도 그대로(문서를 열면 손으로 정한 배율은 폭 맞춤으로 간다 — load)
  const ds = typeof docStatusSnap === "function" ? docStatusSnap() : null;
  toolDocBusy = true;
  toolDocDraw();
  try {
    peerPick = was; peerKind = null; // 둘째 면 = 지금 문서(문서 이름 탭으로 고른 것처럼)
    peerSpotWant = { w: was, at: atMine };
    await openWork(id);
    if (state.id !== id) { peerSpotWant = null; peerPick = pick0; peerKind = kind0; return; } // 못 엶(묻는 창에서 취소 · 오류) — 그대로
    peerSync(); // 작업 목록을 다시 읽기 전에 — 둘째 면이 곧 옛 문서를 읽는다
    if (ds && typeof docStatusCarry === "function") docStatusCarry(ds); // 이름 줄의 분석 상태도 면을 바꿔 바로(다시 읽는 동안 비지 않게)
    if (tool && tool !== $("panel").dataset.tool && toolShown(tool)) showTab(tool); // 패널에서 보던 탭 그대로(문서를 열면 검증으로 간다 — load)
    if (fit0 === null && state.zoom !== z0) setZoom(z0, null); // 손으로 정한 배율 그대로(맞춤 배율은 load 의 refit 이 같은 폭으로 다시 잰다) — 둘째 면도 따라온다(setZoom → peerViewSync)
    spotHold(atPeer);
    if (then) then();
  } finally { toolDocBusy = false; toolDocDraw(); }
}
// 보던 곳 — 창 가운데 줄에 놓인 블록(data-id — 같은 문서를 다시 그려도 찾는다: 쪽을 넘는 표·문단은 몇째 조각인지)과 그 안의 높이 비율, 블록이 없으면 쪽 번호와 비율
function viewSpot() {
  const sc = $("scroller"), kids = sc.hidden ? [] : [...$("doc").children];
  if (!kids.length) return null;
  const at = viewAnchor(sc, kids), o = sc.getBoundingClientRect(), y = o.top + o.height / 2;
  let b = at.el.closest("[data-id]");
  if (!b || b === at.sheet || !at.sheet.contains(b)) { // 가운데 줄이 블록에 안 걸림(쪽 여백 · 블록 사이 · 떠 있는 상자 밑) — 그 쪽에서 가운데 줄에 가장 가까운 블록(같은 문서를 다시 그려도 같은 블록이 잡히게)
    let gap = Infinity;
    b = null;
    for (const c of at.sheet.querySelectorAll("[data-id]")) {
      const r = c.getBoundingClientRect();
      if (!r.height) continue;
      const d = r.top <= y && y <= r.bottom ? 0 : Math.min(Math.abs(r.top - y), Math.abs(r.bottom - y));
      if (d < gap || (d === gap && b && r.height < b.getBoundingClientRect().height)) { gap = d; b = c; } // 같은 거리면 작은 것(바깥 표보다 그 안의 문단)
    }
  }
  if (b) {
    const r = b.getBoundingClientRect(), nth = [...$("doc").querySelectorAll(`[data-id="${CSS.escape(b.dataset.id)}"]`)].indexOf(b);
    return { id: b.dataset.id, nth: Math.max(0, nth), f: r.height ? (y - r.top) / r.height : 0 };
  }
  const sheets = [...$("doc").querySelectorAll(":scope > .sheet")];
  return { page: Math.max(0, sheets.indexOf(at.sheet)), f: at.f }; // 블록이 없는 쪽(빈 쪽 · 그림만)
}
function viewSpotGo(s) { // viewSpot 의 자리를 창 가운데 줄에 — 그 블록이 없으면 그대로
  const sc = $("scroller");
  if (!s || sc.hidden) return;
  const all = s.id ? $("doc").querySelectorAll(`[data-id="${CSS.escape(s.id)}"]`) : null, e = all ? all[s.nth] || all[0] : $("doc").querySelectorAll(":scope > .sheet")[s.page];
  if (e) viewHold(sc, { el: e, f: s.f });
}
let spotKeep = null; // {s, until} — 문서를 바꾼 뒤 잠깐 쪽을 다시 나눠도(글꼴 · 쪽 나눔 자료가 늦게 옴 — paginate 끝) 보던 곳을 지킨다
function spotHold(s) { // 그 자리로 가고 6초 동안 지킨다 — 사람이 굴리거나 누르거나 키를 치면 그만(둘째 면 화면도 바깥이 이것을 부른다 — peerViewSync)
  spotKeep = s ? { s, until: Date.now() + 6000 } : null;
  if (!s) return;
  viewSpotGo(s);
  const stop = () => { spotKeep = null; };
  $("scroller").addEventListener("wheel", stop, { once: true, passive: true });
  $("scroller").addEventListener("pointerdown", stop, { once: true, passive: true });
  window.addEventListener("keydown", stop, { once: true });
}

function closeDoc() {
  for (const t of state.timers.values()) clearTimeout(t);
  state.epoch += 1;
  Object.assign(state, fresh());
  headsReset();
  divReset();
  if (typeof tablesReset === "function") tablesReset(); // 표 탭(tables.js)
  if (typeof compareReset === "function") compareReset();
  if (typeof agentReset === "function") agentReset(); // 에이전트 보기(doc_agent.js)
  $("workspaceNav").hidden = true;
  document.querySelector(".workspace").classList.remove("compare-mode");
  $("docBar").hidden = $("scroller").hidden = $("panel").hidden = $("fileInfo").hidden = $("panelBtn").hidden = $("taskListBtn").hidden = $("barCtl").hidden = true;
  $("empty").hidden = false;
  document.body.classList.add("no-doc"); // 시작 화면 상단 바 모양(landing.css `body.no-doc …`) — #empty 를 보이는 곳과 늘 함께
  $("downloadBtn").disabled = $("verifyBtn").disabled = true;
  $("doc").textContent = "";
  setSaveState("", "");
  history.replaceState(null, "", location.pathname);
  peerSync(); // 같이 보기 열도 닫는다(② §12)
}

// 상단 로고(#homeLink) = 시작 화면으로(spec_작업 ② §7 「시작 화면으로」, 2026-11-12 사용자) — 연 작업을 화면에서만 닫는다(작업은 그대로 — 최근 작업에서 다시 연다).
// closeDoc 이 주소의 #w= 도 걷어 그 뒤 새로 고쳐도 시작 화면. 묻는 것은 둘: 서버에 아직 반영 안 된 수정 · 2열에 저장 안 한 글(headsColClose — 「취소」 면 아무것도 안 닫는다)
function goHome() {
  if (PEEK || !state.id) return;
  if (hasUnsaved() && !confirm(state.stored
    ? "서버에 아직 반영되지 않은 수정(반영 중·반영 실패)이 있습니다. 시작 화면으로 가면 그 수정은 사라집니다. 계속할까요?"
    : "내려받지 않은 수정(또는 반영 중·반영 실패한 수정)이 있습니다. 시작 화면으로 가면 사라집니다. 계속할까요?")) return;
  if (!headsColClose()) return;
  closeDoc();
  loadWorks(); // 최근 작업을 지금 상태로(방금 닫은 작업의 바뀐 때·고친 문단 수)
}

let logTimer = null;
function logTouched() { // 기록 탭이 보이면 잠시 뒤 다시 읽는다(편집마다 부르지 않게)
  if ($("paneLog").hidden || !state.id) return;
  clearTimeout(logTimer);
  logTimer = setTimeout(drawLog, 1200);
}

const LOG_KIND = { create: "작업 만듦", text: "글 고침", revert: "되돌리기", split: "문단 나누기", merge: "문단 합치기", chars: "글자 모양",
  para: "문단 모양", table: "표 행·열", rejected: "표준 검사로 되돌림", undo: "실행 취소", verify: "검증 시작", verified: "검증 끝",
  download: "내려받기", reopen: "작업 다시 엶", headings: "헤딩 추출", outline: "개요 편집",
  outlineFormat: "개요 줄 자리 수정", outlineAlign: "개요 줄 둘째 줄 맞춤", // 템플릿 레벨의 자리 규칙 적용 · 글을 고쳐 둔 줄 맞춤(spec_hwpx_웹편집 ② §8-1)
  outlineRep: "레벨 대표 정하기", outlineMatch: "대표에 맞추기", outlineMerge: "종속 템플릿 만들기", outlineUnmerge: "종속 템플릿 떼기", // spec_hwpx_웹편집 ② §8-2
  captionRep: "캡션 템플릿 대표 정하기", captionMatch: "캡션을 대표에 맞추기", // 캡션 템플릿 「CN」(spec_hwpx_웹편집 ② §8-10)
  commit: "확정", restore: "확정 복원", discard: "모두 되돌리기" }; // 확정(spec_작업 ② §8)
const OUTLINE_OP = { enter: "하위 레벨 줄(Enter)", sibling: "같은 레벨 트리(Alt+Enter)", level: "개요 레벨 바꾸기(Alt+↑/↓)", move: "줄 옮기기(끌기)", remove: "빈 레터 줄 지우기",
  letter: "레터 넣기(문단 묶음의 단추 — 레터만 · 개요 레벨로 · 레터 빼기)" }; // letter = para_letter_api(spec_hwpx_웹편집 ② §8-9)
const CHANGE = { bold: "굵게", italic: "기울임", underline: "밑줄", sizePt: "크기(pt)", color: "색", align: "정렬", indentLeftMm: "왼쪽 여백(mm)",
  indentRightMm: "오른쪽 여백(mm)", firstLineMm: "첫 줄(mm)", lineSpacingPct: "줄 간격(%)", spaceBeforePt: "위 간격(pt)", spaceAfterPt: "아래 간격(pt)" };
const ALIGN = { left: "왼쪽", center: "가운데", right: "오른쪽", justify: "양쪽" };

function changesText(c) {
  return Object.entries(c || {}).map(([k, v]) => `${CHANGE[k] || k} ${v === "toggle" ? "켜고 끔" : v === true ? "켬" : v === false ? "끔" : ALIGN[v] || v}`).join(", ");
}

function groupTexts(events) { // 같은 문단의 잇단 글 고침은 한 줄로(처음 글 → 마지막 글)
  const out = [];
  for (const e of events) {
    const last = out[out.length - 1];
    if (e.kind === "text" && last && last.kind === "text" && last.id === e.id) Object.assign(last, { after: e.after, t: e.t, rev: e.rev, n: (last.n || 1) + 1, restored: e.restored });
    else out.push({ ...e });
  }
  return out;
}

function blockLink(id) {
  const b = el("button", "linkish", `문단 ${id}`);
  b.type = "button";
  b.title = "문서에서 그 문단으로";
  b.onclick = () => (paraEl(id) ? scrollToBlock(id) : toast("그 문단이 지금 문서에 없습니다(지웠거나 합쳐짐)"));
  return b;
}

function logDetail(e, wid) {
  const box = el("div", "log-det");
  const req = e.req || {};
  const owpml = e.owpml ? ` · ${STD()} ${VSTAT[e.owpml.status] || e.owpml.status}` : "";
  switch (e.kind) {
    case "create":
      box.textContent = `${e.name} · ${fmtSize(e.size || 0)} · ${e.source === "sample" ? "예제" : "올린 파일"} · SHA-256 ${(e.sha256 || "").slice(0, 12)}…`;
      break;
    case "text":
      box.append(blockLink(e.id), e.n > 1 ? el("span", "muted", ` · ${e.n}번에 나눠 고침`) : "",
        e.restored === true ? el("span", "muted", " · 원래 글로 돌아와 원본 XML 복원") : "", diffView(e.before || "", e.after || ""));
      break;
    case "revert":
      box.append(blockLink(e.id), el("span", "muted", e.restored ? " · 원본 문단 XML 로 복원" : " · 글만 원래대로(줄 배치는 한글·Word 가 다시 계산)"),
        diffView(e.before || "", e.after || ""));
      break;
    case "split":
      box.append(blockLink(req.id), el("span", null, ` 의 ${req.offset}번째 글자 뒤를 새 문단으로${owpml}`));
      break;
    case "merge":
      box.append(blockLink(req.id), el("span", null, ` 을 ${req.dir === "prev" ? "앞" : "뒤"} 문단과 합침${owpml}`));
      break;
    case "chars":
      box.append(blockLink(req.id), el("span", null, ` · ${changesText(req.changes)}${req.end > req.start ? ` (${req.start}~${req.end}번째 글자)` : " (문단 전체)"}${owpml}`));
      break;
    case "para":
      box.append(...(req.ids || [req.id]).slice(0, 3).map(blockLink), el("span", null, ` · ${changesText(req.changes)}${owpml}`));
      break;
    case "table":
      box.append(blockLink(req.id), el("span", null, ` · ${typeof tableOpLabel === "function" ? tableOpLabel(req.op) : req.op}${owpml}`)); // 표 모듈(table_edit.js)
      break;
    case "outline":
      box.append(...(e.ids || [req.id]).filter(Boolean).slice(0, 3).map(blockLink),
        el("span", null, ` · ${OUTLINE_OP[e.op || req.op] || e.op || req.op}${(e.new || []).length ? ` · 새 문단 ${e.new.length}` : ""}${(e.removed || []).length ? ` · 지움 ${e.removed.length}` : ""}${owpml}`));
      break;
    case "rejected":
      box.textContent = `${LOG_KIND[e.op] || e.op} — ${e.summary || ""}`;
      break;
    case "verify":
      box.textContent = `${VKIND[e.verify] || e.verify} 검증`;
      break;
    case "verified": {
      const d = el("details", "log-run");
      const s = el("summary");
      s.append(verifyTag(e.verify, { status: e.status }), el("span", "muted", ` ${e.seconds}s · 기록 ${e.n}번` + (e.outputSha ? ` · 검사한 파일 ${e.outputSha.slice(0, 12)}…` : "")));
      const ol = el("ol", "steps brief");
      d.append(s, ol);
      d.addEventListener("toggle", async () => {
        if (!d.open || ol.childElementCount) return;
        try { briefSteps(ol, (await api(`/api/works/${wid}/runs/${e.n}`)).job); } catch (err) { ol.append(el("li", "muted", `읽지 못함: ${err.message}`)); }
      });
      box.append(d);
      break;
    }
    case "download":
      box.textContent = `${e.name} · ${fmtSize(e.size || 0)} · ` + (e.same ? "원본과 같은 바이트" : e.verified ? "출력파일 검증한 파일과 같음 ✓" : "출력파일 검증을 거치지 않은 파일");
      if (!e.same) box.classList.add(e.verified ? "good" : "warn");
      break;
    case "reopen":
      box.textContent = e.ok ? "서버를 다시 켰거나 메모리에서 비운 뒤 다시 엶 — 편집 상태 이어짐(실행 취소 기록은 비움)" : `편집 상태를 붙이지 못해 원본으로 엶 — ${e.reason || ""}`;
      if (!e.ok) box.classList.add("warn");
      break;
    case "commit": // 확정(spec_작업 ② §8) — 번호 · 메시지 · 종류별 수
      box.textContent = `확정 ${e.n}${e.message ? ` 「${e.message}」` : ""} · ${kindCounts(e.counts) || "글은 그대로"} — 이 상태가 새 기준`;
      box.classList.add("good");
      break;
    case "restore":
      box.textContent = `${baseName(e.of)} 상태로 되돌려 확정 ${e.n} 로 남김` + (e.discarded ? ` · 확정하지 않은 고친 문단 ${nf(e.discarded)}개는 버림` : "");
      break;
    case "discard":
      box.textContent = `확정하지 않은 고친 문단 ${nf(e.count || 0)}개를 버리고 ${baseName(e.base)} 상태로`;
      break;
    case "headings": // 헤딩 추출 실행(spec_헤딩_추출 ② §7) — 단계 · LLM 여부 · 끝남/실패
      box.textContent = `${e.stage}단계${e.first ? "(첫 분석)" : ""} · ${e.llm ? "LLM" : "스크립트만"} · ${e.status === "done" ? "끝남" : e.status === "failed" ? "실패" : e.status}`
        + (e.n ? ` · 실행 ${e.n}번` : "") + (e.saved === false ? " · 저장 안 됨" : "") + (e.error ? ` — ${e.error}` : "");
      if (e.status === "failed") box.classList.add("warn");
      break;
    case "tableGuide": // 표 지침 저장(spec_헤딩_추출 ② §10) — 표 id · 글자 수 · 사용자 수식 수
      box.textContent = `${e.table === "_common" ? "공통 표 지침" : `표 ${e.table} 지침`} 저장 · ${nf(e.chars || 0)}자${e.formulas ? ` · 사용자 수식 ${e.formulas}` : ""} · v${e.version}`;
      break;
    default:
      return null;
  }
  return box;
}

function briefSteps(ol, job) { // 지난 검증 기록 — 상태·이름·결과 글만(쪽 비교 단추는 지금 PDF 기준이라 뺌)
  ol.textContent = "";
  for (const s of job.steps || []) {
    const li = el("li", `step ${s.status}`);
    li.append(el("span", "st", ICON[s.status]), el("span", "ttl", s.title), el("span", "sec", s.seconds != null ? `${s.seconds}s` : ""),
      el("div", "det", s.detail || ""));
    ol.append(li);
  }
}

async function drawLog() {
  if (!state.id || !state.stored) return;
  const id = state.id, epoch = state.epoch, ol = $("logList");
  let r;
  try { r = await api(`/api/works/${id}/log`); }
  catch (e) { if (epoch === state.epoch) { ol.textContent = ""; ol.append(el("li", "none", `기록을 읽지 못했습니다: ${e.message}`)); } return; }
  if (epoch !== state.epoch) return;
  const w = r.work;
  $("logSum").textContent = `만듦 ${fmtWhen(w.created)} · 편집 ${w.rev || 0}번 · 검증 ${r.runs.length}번`;
  const open = new Set([...ol.querySelectorAll("details[open]")].map((d) => d.dataset.n)); // 펼친 검증 기록은 다시 그려도 펼친 채
  ol.textContent = "";
  for (const e of groupTexts(r.events).reverse()) { // 최근 것이 위
    const li = el("li", `log-item k-${e.kind}`);
    const head = el("div", "log-head");
    head.append(el("span", "log-kind", LOG_KIND[e.kind] || e.kind), el("time", "log-time", fmtWhen(e.t)));
    li.append(head);
    const det = logDetail(e, id);
    if (det) li.append(det);
    const d = li.querySelector("details");
    if (d) { d.dataset.n = e.n; if (open.has(String(e.n))) d.open = true; }
    ol.append(li);
  }
}

function walkParas(blocks, fn) {
  for (const b of blocks) {
    if (b.type === "paragraph") fn(b);
    for (const c of b.cells || []) walkParas(c.blocks || [], fn);
  }
}

// ---------------------------------------------------------------- 문서 그리기
const DEFAULT_PAGE = { widthMm: 210, heightMm: 297, marginsMm: { l: 20, r: 20, t: 20, b: 15 } };

function renderDoc(blocks) {
  // 문서 흐름(최상위 단위 목록)을 한 번 그려 두고, 쪽 상자로 나누는 일은 paginate() 가 한다 — 매핑이 오면 같은 노드를 다시 나눈다
  if (typeof tselClear === "function") tselClear(); // 다시 그리면 고른 표 칸(옛 노드)도 품 — #doc 의 cellsel 표시가 남지 않게(표 모듈 table_edit.js)
  state.sections = [];
  let sec = -1;
  const tops = [];
  for (const b of blocks) {
    if (b.page || sec < 0) { sec += 1; state.sections.push(b.page || DEFAULT_PAGE); }
    tops.push([b, sec]);
  }
  state.flow = buildFlow(tops);
  paginate();
}

function buildFlow(tops) {
  // [[최상위 블록, 구역 번호]] → 쪽 흐름 항목들(문단·그림 = node, 최상위 표 = table) — 구조 편집은 바뀐 블록만 이걸로 다시 만들어 끼운다
  const flow = [];
  const objWidth = (x) => (x.type === "table" ? colWidths(x, x.nCols || Math.max(1, ...x.cells.map((c) => c.col + c.colSpan))).reduce((a, w) => a + w, 0)
    : x.type === "image" ? x.widthMm || 0 : 0);
  let loose = -1; // 나란히 안 들어가 따로 둔 글자처럼 개체 묶음의 끝 — 그 안 나머지 개체도 묶지 않는다
  for (let i = 0; i < tops.length; i++) {
    const [b, s] = tops[i];
    if (b.inlineRow && i >= loose) {
      let j = i;
      const group = [];
      while (j < tops.length && (tops[j][0].inlineRow === b.inlineRow || (tops[j][0].captionOf && group.includes(tops[j][0].captionOf)))) {
        group.push(tops[j][0].id);
        j++;
      }
      const g = state.sections[s] || DEFAULT_PAGE;
      const room = g.widthMm - g.marginsMm.l - g.marginsMm.r;
      const row = tops.slice(i, j).filter(([x]) => x.inlineRow === b.inlineRow).map(([x]) => x);
      const total = row.every((x) => x.rowAtMm != null) ? Math.max(...row.map((x) => x.rowAtMm + objWidth(x))) // 나란히 뜬 그림 — 가장 오른쪽 그림의 오른끝 자리
        : tops.slice(i, j).reduce((a, [x]) => a + objWidth(x), 0);
      if (total <= room + 1) { // 한글처럼 한 줄에 나란히 — 들어갈 때만. 넘치면 한글도 줄을 바꾸므로 따로따로(표는 쪽마다 나눌 수 있게)
        const holder = el("div");
        renderList(holder, tops.slice(i, j).map((x) => x[0]));
        flow.push({ kind: "node", el: holder.firstElementChild, ids: group, sec: s, pageStart: !!b.pageStart });
        i = j - 1;
        continue;
      }
      loose = j;
    }
    if (b.type === "table" && b.cells && b.cells.length) {
      const t = renderTable(b);
      const rows = [...t.tBodies[0].rows];
      rows.forEach((tr, r) => { tr.dataset.row = r; }); // 표 행 번호 — 쪽 조각 안에서도 그 행이 표의 몇째 행인지(행 안 나눔 rowCutPlan)
      flow.push({ kind: "table", id: b.id, tpl: t, rows, sec: s, pageStart: !!b.pageStart });
    } else {
      flow.push({ kind: "node", el: renderBlock(b), ids: [b.id], sec: s, pageStart: !!b.pageStart });
    }
  }
  return flow;
}

function paginate() {
  // 쪽 상자로 나눈다: 매핑이 있으면 서버가 PDF 쪽 맨 위 줄로 맞춘 나눔(breaks — 최상위 블록 또는 표 행), 없으면 한글이 저장한 줄 배치로 추정한 나눔
  const doc = $("doc");
  const keep = $("scroller").scrollTop;
  // 다시 나누면 노드가 떼어졌다 붙어 브라우저가 포커스를 뺀다 — 쓰는 중이던 문단과 커서를 기억해 되살린다(매핑이 타자 중에 와도 글이 안 사라짐)
  const act = document.activeElement && document.activeElement.classList && document.activeElement.classList.contains("para") ? document.activeElement : null;
  const actSel = act && selOffsets(act);
  rowHeal(); // 지난번 행 안 나눔(이어짐 칸)을 되돌리고 처음부터 다시 나눈다
  doc.textContent = "";
  const m = state.mapping;
  const brk = new Map();
  if (m && m.breaks) for (const x of m.breaks) brk.set(x.kind === "rows" ? `r:${x.id}:${x.row}` : `b:${x.id}`, x.page);
  const many = state.sections.length > 1, wide = wideSecs();
  let body = null, num = 0, sec = -1;
  const sheetAt = (n, s) => {
    const g = state.sections[s] || DEFAULT_PAGE, mm = g.marginsMm;
    const sheet = el("div", wide.has(s) ? "sheet span2" : "sheet"); // span2 = 2쪽 보기에서 한 줄을 통째로 쓰는 넓은 쪽(wideSecs — 넘침 나눔 조각은 이 상자의 사본이라 물려받는다)
    sheet.style.zoom = state.zoom; // 배율은 쪽 상자마다(「확대」 절 zoomApply) — 넘침 나눔 조각(overflowSplit)은 이 상자의 사본이라 그대로 물려받는다
    sheet.style.width = `${g.widthMm}mm`;
    sheet.style.minHeight = `${g.heightMm}mm`;
    // 아래 여백은 padding 이 아니라 min-height(용지) 가 남긴다 — 본문이 넘치면 한글처럼 아래 여백 안으로 먼저 들어가고(2쪽 작성 요령 표: 한글도 286.6mm 까지), 여백을 다 쓴 뒤에야
    // 상자가 길어진다(② §3-1). 높이 맞춤·밀기는 g.marginsMm 로 재므로 영향 없음.
    sheet.style.padding = `${mm.t}mm ${mm.r}mm 0 ${mm.l}mm`;
    sheet.dataset.page = n;
    sheet.dataset.sec = s; // 높이 맞춤이 이 쪽의 크기·여백(구역)을 찾는다
    const sheetNo = m && m.sheets ? m.sheets[n - 1] : null;
    const label = el("button", "sheet-label", `${m ? "" : "≈"}${n}쪽${sheetNo && m.twoUp ? ` · PDF ${sheetNo}장` : ""}${many ? ` · 구역 ${s + 1}${g.widthMm > g.heightMm ? " 가로" : ""}` : ""}`);
    label.type = "button";
    label.title = m ? `${APP()} PDF 의 이 쪽 보기` : `${APP()}가 저장한 ${state.format === "docx" ? "쪽 나눔 캐시" : "줄 배치"}로 추정한 쪽 — PDF 매핑이 끝나면 PDF 쪽에 맞춥니다`;
    label.onclick = () => { if (m) { state.pdfWhich = "original"; syncSeg(); state.pdfPage = sheetNo || n; showTab("Pdf"); setPanel(true); } };
    body = el("div", "sheet-body");
    sheet.append(label, body);
    doc.append(sheet);
    num = n;
    sec = s;
    return sheet;
  };
  const between = (to, carry) => { // num+1 … to−1 쪽 = 시작하는 단위가 없는 쪽: 앞 쪽 표 행에서 넘어온 조각이 있으면 쪽 상자, 없으면 빈 쪽 표지
    const s0 = sec;
    for (let k = num + 1; k < to; k++) {
      if (carry.has(k)) { sheetAt(k, s0); body.append(carry.get(k)); } else doc.append(gapPage(k));
    }
  };
  const open = (n, s) => {
    // 앞 쪽 끝의 표 행이 이 쪽(들)까지 이어지면 쪽마다 조각으로 나눠 온다(② §3-1 「행 안 나눔」) — n 쪽 몫은 새 쪽 상자 맨 위에(이 쪽에서 시작하는 단위보다 앞)
    const carry = m && body ? rowCarry(body, num, n, m) : new Map();
    if (m) between(n, carry);
    const sheet = sheetAt(n, s);
    if (carry.has(n)) body.append(carry.get(n));
    else if (m && m.pageStatus && m.pageStatus[n] === "split") {
      sheet.append(el("div", "cont-note", "↑ PDF 에서는 앞 쪽의 문단이 이 쪽 위까지 이어집니다(웹은 문단·칸 안 표 안에서 나누지 않아 앞 쪽에 함께 보임)"));
    }
  };
  // 구역이 바뀌면 새 쪽 — 한글의 구역은 늘 새 쪽, Word 는 「이어서」 구역(page.continuous)이고 용지가 같을 때만 같은 쪽. 매핑이 있어도: 가로 구역의 첫 블록이 빈 줄·그림뿐이면
  // PDF 쪽 나눔(breaks)에 없어 앞 세로 쪽 상자에 들어가 그림이 쪽 밖으로 넘쳤다(2026-11-18 사용자 "와이드페이지도 동일하게 볼 수 있도록" — 69쪽 가로 체계도)
  const newSec = (it) => {
    if (sec < 0 || it.sec === sec) return false;
    const a = state.sections[sec] || DEFAULT_PAGE, b = state.sections[it.sec] || DEFAULT_PAGE;
    return !(b.continuous && a.widthMm === b.widthMm && a.heightMm === b.heightMm);
  };
  const startsAt = (it, key, first) => {
    if (m) { const p = brk.get(key); return p && p > num ? p : first && newSec(it) ? num + 1 : 0; }
    return first && (it.pageStart || newSec(it)) ? num + 1 : 0;
  };
  for (const it of state.flow) {
    if (it.kind === "node") {
      const p = it.ids.map((id) => startsAt(it, `b:${id}`, true)).find(Boolean) || 0;
      if (!body) open(p || 1, it.sec);
      else if (p) open(p, it.sec);
      body.append(it.el);
      continue;
    }
    let seg = null;
    it.rows.forEach((tr, r) => {
      const p = startsAt(it, `r:${it.id}:${r}`, r === 0);
      if (!body) open(p || 1, it.sec);
      else if (p) { // 새 쪽 — 앞 쪽에서 넘어온 이 표의 이어짐 조각이 머리에 있으면(행 안 나눔) 거기에 잇는다
        open(p, it.sec);
        seg = body.lastElementChild;
        if (seg && seg.dataset.tbl !== it.id) seg = null;
      }
      if (!seg) {
        seg = it.tpl.cloneNode(false);
        seg.append(it.tpl.querySelector("colgroup").cloneNode(true), el("tbody"));
        if (r > 0) seg.classList.add("cont");
        body.append(seg);
      }
      seg.tBodies[0].append(tr);
    });
  }
  if (m && num < m.pageCount) between(m.pageCount + 1, body ? rowCarry(body, num, m.pageCount + 1, m) : new Map()); // 문서 끝에 남은 쪽
  if (m) overflowPush(doc);
  const epoch = state.paginateEpoch = (state.paginateEpoch || 0) + 1;
  document.fonts.ready.then(() => { // url() 웹 글꼴이 늦게 오면 줄 수·높이가 바뀐다 — 그때 다시 밀고·나누고 표시를 다시 그린다(그 사이 다시 나눴으면 생략)
    spaceRemeasure(); // 빈칸 폭도 온 글꼴로 다시 잰다(② §3-4 「빈칸 폭」) — 아래 다시 밀기가 그 폭으로 본다
    if (epoch !== state.paginateEpoch || !doc.isConnected) return;
    const pushed = state.mapping ? overflowPush(doc) : 0, split = overflowSplit(doc); // 밀기 뒤 넘침 나눔도 다시(새 블록 쪽 — a4 세션, astra 11-10 ③ · 매핑이 없으면 넘친 쪽 모두)
    if (!pushed && !split) return; // 옮긴 게 없으면 다시 그리지 않음(표시 다시 그리기가 느림 — 61 세션)
    refit();
    if (typeof tplMarksDraw === "function" && heads.marks) tplMarksDraw();
    if (typeof tblMarksDraw === "function") tblMarksDraw();
    if (typeof ddDraw === "function") ddDraw();
  });
  overflowSplit(doc); // 쪽 자리 정보가 없는 새 블록(구분 기준 반영 사본 등)이나 고친 문단(서식·글)으로 길어진 쪽 · 매핑 전 어림 나눔에서 용지보다 긴 쪽은 용지 높이로 어림해 나눈다(② §3-1 「넘침 나눔」)
  markUnmapped();
  refit();
  $("scroller").scrollTop = keep;
  if (spotKeep) { if (Date.now() < spotKeep.until) viewSpotGo(spotKeep.s); else spotKeep = null; } // 도구를 쓸 문서를 바꾼 직후 — 다시 나눈 쪽에서도 보던 곳(toolDocSet · spotHold)
  if (act && act.isConnected && document.activeElement !== act) {
    act.focus({ preventScroll: true });
    if (actSel) setCaret(act, actSel.start, actSel.end);
  }
  if (typeof tplMarksDraw === "function" && heads.marks) tplMarksDraw(); // 헤딩 템플릿 표시(쪽을 다시 나누면 표가 사라지므로)
  if (typeof tblMarksDraw === "function") tblMarksDraw(); // 표 도구 표지 · 엑셀식 보기 되살림(spec_헤딩_추출 ② §10)
  if (typeof divMarksDraw === "function") divMarksDraw(); // 구분 기준 문서 표시(문서를 다시 읽으면 문단 요소가 새것, spec_구분_기준 ② §11)
  if (typeof fmtFocusDraw === "function") fmtFocusDraw(); // 서식 라벨만 또렷이(fmt_focus.js — 같은 까닭: spec_헤딩_추출 ② §7)
  if (typeof ddDraw === "function") ddDraw(); // 고친 곳 보기(doc_diff.js — 문단을 옮기면 글자 범위가 풀리고 꼬리표 자리가 바뀐다: spec_작업 ② §8)
}

// 쪽 상자가 용지 본문을 넘치고 그 끝이 PDF 자리를 모르는 문단(빈 줄 — 매핑 없음)이나 짧은 글(5자 이하 — 「가까운 자리」 매핑이라 쪽이 틀릴 수 있음, ④)이면
// 다음 쪽 맨 위로 보낸다(② §3-1 「넘침 밀기」): 쪽 머리 줄이 빈 줄·한 글자면 매핑이 그 쪽 나눔을 못 잡아 앞 쪽이 길어진다(연구개발계획서 양식 28쪽 「o」「-」, 14쪽 빈 줄).
// 다음 쪽이 빈 쪽 표지(gap-page — 앞 쪽 문단·행이 이어지는 쪽)이거나 없으면 그대로 둔다. 표·그림·자리 아는 문단에서 멈춘다.
// 끝이 표 조각이면 뒤 행부터 다음 쪽 머리의 이어짐 조각(.cont)으로 옮긴다 — 한글이 그 표를 쪽 경계의 행에서 나눴는데 그 쪽 맨 위 줄이 짧은 칸 글(「20××년」)이라
// 매핑이 나눔을 못 잡은 경우(43·65쪽). 세로 병합 칸이 걸친 행은 여기서는 못 옮긴다(높이로 미는 것은 병합 칸을 안 나눔) — PDF 로 확인되는 쪽 넘김(43→44쪽 등)은 「행 안 나눔」(rowCarry)이
// 쪽을 열 때 병합 칸째 나눈다. 행 안에서 나눈 앞부분 행은 행째 밀지 않고 끝의 자리 모르는 블록만(pushTail).
// 웹 글꼴(url)이 늦게 오면 높이가 바뀌므로 fonts.ready 뒤 한 번 더(paginate). 임시 처방이다 — 용지 고정·내용 흘려보내기 설계는 ④(astra 협의).
function overflowPush(doc) {
  const m = state.mapping;
  const sheets = [...doc.querySelectorAll(".sheet")];
  let moved = 0;
  for (let i = 0; i < sheets.length - 1; i++) {
    const s = sheets[i], next = s.nextElementSibling;
    if (!next || !next.classList.contains("sheet") || +next.dataset.page !== +s.dataset.page + 1) continue;
    const bodyMm = (x) => { const g = state.sections[+x.dataset.sec] || DEFAULT_PAGE; return (g.heightMm - g.marginsMm.t - g.marginsMm.b) * PX_PER_MM + 1; }; // 본문 높이(px, 배율 전)
    const room = bodyMm(s), nextRoom = bodyMm(next); // 다음 쪽은 제 구역의 용지로(astra 11-10)
    const body = s.querySelector(".sheet-body"), nextBody = next.querySelector(".sheet-body");
    while (body.offsetHeight > room) {
      const last = body.lastElementChild;
      if (!last) break;
      if (last.classList.contains("para")) {
        const t = (state.texts[last.dataset.id] ?? state.original[last.dataset.id] ?? "").trim(); // 지금 글(고친 뒤 길어졌을 수 있음)
        if (m.pages[last.dataset.id] && t.length > 5) break;
        nextBody.prepend(last);
        moved += 1;
        continue;
      }
      if (last.tagName !== "TABLE" || !pushRow(last, nextBody, nextRoom)) break;
      moved += 1;
    }
  }
  return moved;
}

function pushRow(seg, nextBody, room) {
  // 표 조각의 마지막 행을 다음 쪽 머리의 같은 표 이어짐 조각으로(없으면 만든다). 옮긴 행이 위 행의 세로 병합 칸에 덮이면(웹 조각의 제한)·행이 하나뿐이면·
  // 다음 쪽(room = 그 쪽 본문 높이)에 그 행이 들어갈 자리가 없으면(2쪽 작성 요령 249mm 행·11쪽 318mm 행 — 한글은 행 안에서 나누거나 아래 여백으로 넘침) false.
  const rows = [...seg.tBodies[0].rows], L = rows.length - 1;
  if (L >= 0 && rows[L].dataset.cut) return pushTail(rows[L]); // 행 안에서 나눈 앞부분 행 — 행째가 아니라 끝의 자리 모르는 블록만(② §3-1 「행 안 나눔」)
  if (L < 1 || nextBody.offsetHeight + rows[L].offsetHeight > room) return false;
  for (let r = 0; r < L; r++) for (const td of rows[r].cells) if (r + td.rowSpan > L) return false;
  let cont = nextBody.firstElementChild;
  if (!cont || cont.tagName !== "TABLE" || cont.dataset.tbl !== seg.dataset.tbl || !cont.classList.contains("cont")) {
    cont = seg.cloneNode(false);
    cont.append(seg.querySelector("colgroup").cloneNode(true), el("tbody"));
    cont.classList.add("cont");
    nextBody.prepend(cont);
  }
  cont.tBodies[0].prepend(rows[L]);
  return true;
}

// 넘침 나눔(② §3-1): 쪽 자리 정보가 없는 **새 블록**(구분 기준 반영·구조 편집으로 생긴 사본 — 한글 줄 배치(pageStart)도 PDF 매핑도 없다)은 앞 블록의 쪽 상자에
// 그대로 쌓여 그 상자가 용지의 몇 배로 길어진다(2026-11-10 사용자 "왜 다 페이지가 안맞냐" — 2-2 기관 사본·(3)(4) 참여기관 절 사본). 고친 문단(새 블록 · 서식·글이 바뀐 문단 — 2026-11-17)이 든 쪽 상자가 용지
// 본문보다 길면 용지 높이로 어림해 뒤를 잘라 「≈n쪽 +k」 조각 상자로 잇는다 — 고친 문단이 없는 쪽은 웹 글꼴·표 높이 차이로 길어진 것이라 그대로(쪽 번호 = PDF 쪽).
// 매핑이 없으면(어림 나눔 — 2026-11-17) 새 블록이 없어도 넘친 쪽은 모두 나눈다: 어림 나눔은 표 행을 쪽마다 못 나눠 여러 쪽짜리 표가 한 상자가 된다.
// 조각은 같은 쪽 번호(PDF 자리가 없으니 뒤 쪽 번호를 밀지 않는다 — 출력파일 검증을 돌려야 실제 쪽을 안다). 나눔 단위 = 최상위 문단·그림·표 행 — 위 행의 세로 병합 칸이 덮는 행
// 앞에서도 자르고 그 칸은 이어짐 칸으로 나눈다(2026-11-10 — 전에는 그 행 묶음을 한 덩이로 재어, 묶음 제목이 표 전체에 걸치면 못 잘랐다). 조각마다 한 단위는 남긴다.
// 높이는 쪽마다 한 번에 다 읽고(강제 배치 1회) 그다음 DOM 을 옮긴다(61 세션 부탁 — 읽기·쓰기를 번갈지 않음). 웹 글꼴이 늦게 와 높이가 바뀌면(paginate 의 fonts.ready) 조각도
// 다시 재어 더 나누고 같은 쪽의 조각 번호를 DOM 차례로 다시 매긴다. -> 나눈 게 있으면 true.
const SPLIT_TOL = 1.08; // 넘침 나눔 문턱 — 용지 본문의 8% 까지는 웹·한글 높이 차이로 보고 안 나눈다(새 블록 두세 줄로 조각 하나를 만들지 않게)

function overflowSplit(doc) {
  // 고친 문단(새 문단 · 서식 · 글 · 구조 — kinds 가 있는 것)이 든 쪽: PDF 쪽(원본)과 내용이 달라 한글도 다시 흘린다. 2026-11-17 사용자 "페이지 잘림" — 「모두 반영」 이 표 칸 줄을 8pt → 10pt 로 바꿔
  // 105쪽(표 t15456 이어짐)이 용지 1.4배가 되고 표 끝이 종이 아래끝에 붙었다: 전에는 새 블록이 든 쪽만 쟀다
  const isEdited = (p) => !!state.kinds[p.dataset.id];
  // 매핑이 없으면(PDF 매핑 전 · 「≈n쪽」 어림 나눔) 넘친 쪽 모두 — 어림 나눔은 최상위 블록의 쪽 시작만 알아 여러 쪽에 걸친 표가 한 상자에 쌓인다(2026-11-17 사용자 "이거 페이지 별로 해봐, 1페이지에
  // 안들어 가잖아" — 요약문 표가 용지 5.5배인 「≈2쪽」). 지킬 PDF 쪽 번호가 없으니 새 블록 쪽만 나눌 까닭이 없다. 매핑이 있으면 고친 문단이 든 쪽만(나머지는 「행 안 나눔」 이 PDF 쪽대로 —
  // 고치지 않은 쪽이 길면 웹·한글 높이 차이거나 매핑이 쪽 나눔을 못 잡은 것이라 그대로)
  const sheets = [...doc.querySelectorAll(".sheet")].filter((s) => !state.mapping || [...s.querySelectorAll(".para")].some(isEdited));
  if (!sheets.length) return false;
  const jobs = []; // 읽기만: [{s, units, cuts}]
  for (const s of sheets) {
    const g = state.sections[+s.dataset.sec] || DEFAULT_PAGE;
    const room = (g.heightMm - g.marginsMm.t - g.marginsMm.b) * PX_PER_MM + 1; // 본문 높이(px, 배율 전)
    const body = s.querySelector(".sheet-body");
    if (body.offsetHeight <= room * SPLIT_TOL) continue; // 웹 글꼴·표 높이 차이만큼(④ 「웹 표가 한글보다 길다」)은 PDF 쪽과 같은 상자로 두고 그보다 길 때만 나눈다
    const z = s.offsetWidth ? s.getBoundingClientRect().width / s.offsetWidth : 1; // #doc 의 CSS zoom — 화면 px → 배율 전 px
    const b0 = body.getBoundingClientRect().top;
    const units = []; // 나눔 단위 {el, seg(표 조각이면), top, bottom} — 본문 위끝 기준 px. 표는 행마다 한 단위: 위 행의 세로 병합 칸(묶음 제목)이 덮는 행 앞에서도 자른다 —
    // 그 칸은 이어짐 칸으로 나눈다(아래 쓰기 단계 rowCutApply, 한글도 병합 칸째 쪽을 넘긴다). 2026-11-10 사용자 "테이블이 길어진다고 페이지가 길어지면 어쩌냐 페이지가 넘어가야지" — 전에는
    // 병합 칸이 걸친 행 묶음을 한 덩이로 재어, 맨 왼쪽 묶음 제목이 표 전체에 걸친 표는 자를 곳이 없어 쪽 상자가 길어졌다(spec_owpml_편집 ② §5-6).
    for (const c of body.children) {
      if (c.tagName === "TABLE" && c.tBodies[0]) {
        for (const tr of c.tBodies[0].rows) {
          const rc = tr.getBoundingClientRect();
          units.push({ el: tr, seg: c, top: (rc.top - b0) / z, bottom: (rc.bottom - b0) / z });
        }
      } else {
        const rc = c.getBoundingClientRect();
        units.push({ el: c, top: (rc.top - b0) / z, bottom: (rc.bottom - b0) / z });
      }
    }
    // 자를 곳 {i, firsts}: firsts 가 없으면 i 단위 **앞에서**, 있으면 i 행 **안에서**(firsts = 칸마다 뒤 조각으로 보낼 첫 블록). 표 행이 남은 자리에 안 들어가면 행째 넘기지 않고 칸 안 블록
    // (문단·그림·칸 안 표) 경계에서 잘라 앞부분을 이 조각에 남긴다 — 한글도 「셀 단위로 나눔」 표의 행은 그 쪽에서 이어 찍고 줄에서 나눈다(2026-11-12 사용자 "이건 왜 페이지를 넘겨 버리냐
    // 테이블이?" — 요약문 표의 933px 행이 행째 다음 조각으로 가 쪽 절반이 비고, 2,513px 행은 용지 2.5배 조각으로 남았다). 용지보다 긴 행은 조각마다 또 자른다(rowFitCuts).
    const cuts = [];
    let start = 0, head = 0; // 지금 조각의 위끝(본문 위끝 기준 px) · 그 조각의 첫 단위 번호
    for (let i = 0; i < units.length; i++) {
      const u = units[i];
      if (u.bottom - start <= room) continue;
      const cells = u.seg && !u.el.dataset.cut ? rowBlocks(u.el, b0, z) : []; // 이미 나눈 앞부분 행(data-cut)은 다시 안 나눈다 — 이어짐 칸의 차례가 꼬인다
      const fit = cells.length ? rowFitCuts(cells, u.bottom - u.top, start + room - u.top, room, i > head) : null;
      if (fit && fit.cuts.length) {
        for (const firsts of fit.cuts) cuts.push(firsts ? { i, firsts } : { i });
        head = i;
        start = u.bottom - fit.rem;
      } else if (i > head) { cuts.push({ i }); start = u.top; head = i; } // 문단·그림 · 안에서 못 나누는 행 — 단위 앞에서(조각의 첫 단위면 그대로 길게 둔다)
    }
    if (cuts.length) jobs.push({ s, units, cuts });
  }
  if (!jobs.length) return false;
  const m = state.mapping;
  const pages = new Set();
  for (const { s, units, cuts } of jobs) { // 쓰기만
    const n = +s.dataset.page, sheetNo = m && m.sheets ? m.sheets[n - 1] : null;
    pages.add(n);
    let prev = s;
    const tail = new Map(); // 표 조각 → 거기서 잘라 낸 지금 꼬리 조각(같은 조각을 또 자를 때는 꼬리 안에서)
    cuts.forEach((cut, k) => {
      const ns = s.cloneNode(false); // 같은 용지·여백·구역(style·data-*) — 안은 비움(조각을 또 나누면 그 조각의 사본)
      ns.classList.add("over");
      const label = el("button", "sheet-label", `≈${n}쪽`); // 「+k」는 아래에서 DOM 차례로 매긴다
      label.type = "button";
      label.title = m ? `고친 내용(새 문단·표 · 글자 크기나 글이 바뀐 문단)이 ${APP()} PDF 쪽보다 길어 ${n}쪽 상자가 용지보다 길어졌습니다 — 용지 높이로 어림해 나눈 조각(쪽 번호는 밀지 않음). `
        + `실제 쪽은 「출력파일 검증」 뒤 PDF 탭에서 확인하세요. 누르면 ${APP()} PDF ${n}쪽.`
        : `${APP()} PDF 쪽 매핑이 아직 없어 ${n}쪽 상자가 용지보다 길어졌습니다(여러 쪽에 걸친 표 등) — 용지 높이로 어림해 나눈 조각(쪽 번호는 밀지 않음). `
        + `PDF 매핑이 오면 ${APP()} PDF 쪽에 맞춰 다시 나눕니다.`;
      label.onclick = () => { if (m) { state.pdfWhich = "original"; syncSeg(); state.pdfPage = sheetNo || n; showTab("Pdf"); setPanel(true); } };
      const nb = el("div", "sheet-body");
      ns.append(label, nb);
      prev.after(ns);
      prev = ns;
      const nx = cuts[k + 1]; // 다음에 자를 곳이 행 안이면 그 행까지 이 조각으로 옮겨 둔다(그 행의 앞부분이 여기 남는다)
      const end = nx ? nx.i + (nx.firsts ? 1 : 0) : units.length;
      let whole = null, i = cut.i; // whole = 이 조각 상자로 통째 옮긴 표 조각 — 그 안의 뒤 행 단위는 건너뜀
      if (cut.firsts) {
        // 행 안에서 자른다 — 앞부분은 앞 조각에 남고 이어짐 행(tr.row-cont)부터 이 조각으로. 그 행을 지나는 칸 모두에 이어짐 칸: 제 칸은 firsts 의 블록부터, 그 밖(다 들어간 칸·세로 병합 칸·
        // 위에서 내려오는 칸)은 글을 앞 조각에 남긴 빈 이어짐 칸. 블록 요소로 자리를 찾으므로 같은 행을 또 자를 때(용지보다 긴 행)는 앞서 만든 이어짐 칸 안에서 잘린다
        const u = units[i], seg = tail.get(u.seg) || u.seg, R = +u.el.dataset.row;
        const trs = [...seg.tBodies[0].rows], at = trs.findIndex((tr) => +tr.dataset.row === R);
        if (at >= 0) {
          const plan = [];
          for (let j = 0; j <= at; j++) for (const td of trs[j].cells) {
            if (j + td.rowSpan <= at) continue;
            const x = j < at ? -1 : [...td.children].findIndex((b) => cut.firsts.has(b));
            plan.push([td, x < 0 ? td.children.length : x]);
          }
          whole = rowCutApply(seg, { R, inner: true, at: plan });
          tail.set(u.seg, whole);
          nb.append(whole);
          i += 1;
        }
      }
      for (; i < end; i++) {
        const u = units[i];
        if (!u.seg) { nb.append(u.el); continue; }
        const seg = tail.get(u.seg) || u.seg;
        if (seg === whole) continue;
        const trs = [...seg.tBodies[0].rows], at = trs.indexOf(u.el);
        if (at <= 0) { whole = seg; nb.append(seg); continue; } // 조각의 첫 행부터 — 조각째(빈 껍데기를 남기지 않음)
        // 행 앞에서 자른다: 위 행의 세로 병합 칸이 이 행까지 내려오면 그 칸을 이어짐 칸(td.cell-cont — 글은 앞 조각에 남김)으로 나눈다. 「행 안 나눔」 과 같은 조각이라
        // 다음 paginate 의 rowHeal 이 되돌리고, 표 칸 고르기·표 메뉴는 모델 rowSpan(data-rs)을 본다
        const cross = [];
        for (let j = 0; j < at; j++) for (const td of trs[j].cells) if (j + td.rowSpan > at) cross.push([td, td.children.length]);
        const next = rowCutApply(seg, { R: +u.el.dataset.row, inner: false, at: cross });
        tail.set(u.seg, next);
        whole = next;
        nb.append(next);
      }
    });
  }
  for (const n of pages) { // 같은 쪽의 조각 번호를 DOM 차례로(조각을 또 나눠도 +1, +2 … 차례가 지켜지게)
    doc.querySelectorAll(`.sheet.over[data-page="${n}"]`).forEach((p, k) => {
      p.dataset.over = k + 1;
      p.querySelector(".sheet-label").textContent = `≈${n}쪽 +${k + 1}`;
    });
  }
  return true;
}

// 넘침 나눔 — 행 안에서 자를 수 있는 칸(그 행에서 시작해 그 행에서 끝나는 칸)마다 칸 안 블록의 자리 [{el, top, bottom}](본문 위끝 기준 px, 배율 전 · 높이 없는 블록은 뺌). 읽기만.
// 세로 병합 칸은 넣지 않는다 — 그 글은 앞 조각에 남긴다(행 앞에서 자를 때와 같음).
function rowBlocks(tr, b0, z) {
  const cells = [];
  for (const td of tr.cells) {
    if (td.rowSpan > 1) continue;
    const c = [];
    for (const b of td.children) {
      const rc = b.getBoundingClientRect();
      if (rc.height) c.push({ el: b, top: (rc.top - b0) / z, bottom: (rc.bottom - b0) / z });
    }
    if (c.length) cells.push(c);
  }
  return cells;
}

// 넘침 나눔 — 표 행 하나를 어디서 자를지(셈만). cells = rowBlocks, rowH = 행 높이, avail = 지금 조각에서 이 행에 남은 높이, room = 용지 본문 높이, canPush = 행이 조각의 첫 단위가 아님
// (행 앞에서 자를 수 있음) -> {cuts: [null(행 앞에서) | Set(칸마다 뒤 조각으로 보낼 첫 블록 요소)], rem: 마지막 조각에 남는 이 행의 높이}.
// 칸마다 위에서부터 들어가는 블록까지 앞 조각에 남긴다 — 다 들어가는 칸(세로 가운데 맞춘 제목 칸)은 통째로 남는다. 한 블록도 못 남기면 행 앞에서 자르고 새 조각에서 다시 재며,
// 조각 맨 위인데도 첫 블록이 안 들어가면(용지보다 긴 그림·문단 하나·칸 안 표 하나 — 그 안에서는 못 나눈다) 칸마다 한 블록은 남긴다. 칸 여백·괘선(extra)은 가장 긴 칸으로 어림한다 —
// 저장 높이가 내용보다 큰 행은 그만큼이 extra 라 안에서 안 잘리고 행째 넘어간다.
function rowFitCuts(cells, rowH, avail, room, canPush) {
  const tall = (c, f) => (f < c.length ? c[c.length - 1].bottom - (f ? c[f - 1].bottom : c[0].top) : 0); // f 번째 블록부터 남은 높이(앞 블록과의 사이 포함)
  const extra = Math.max(0, rowH - Math.max(...cells.map((c) => tall(c, 0))));
  const cuts = [];
  let f = cells.map(() => 0), first = true; // f = 칸마다 지금 조각의 첫 블록 번호
  for (;;) {
    const n = cells.map((c, x) => {
      const base = f[x] ? c[f[x] - 1].bottom : c[0].top;
      let k = f[x];
      while (k < c.length && c[k].bottom - base + extra <= avail) k++;
      return k;
    });
    const done = () => n.every((k, x) => k >= cells[x].length);
    if (done()) break; // 남은 것이 다 들어간다
    if (!n.some((k, x) => k > f[x])) {
      if (first && canPush) { cuts.push(null); first = false; avail = room; continue; }
      n.forEach((k, x) => { if (k < cells[x].length) n[x] = k + 1; });
      if (done()) break;
    }
    cuts.push(new Set(cells.map((c, x) => c[n[x]]).filter(Boolean).map((b) => b.el)));
    f = n;
    first = false;
    avail = room;
  }
  return { cuts, rem: Math.max(...cells.map((c, x) => tall(c, f[x]))) + extra };
}

// 행 안 나눔(spec_hwpx_웹편집 ② §3-1, 2026-11-10 사용자 "표가 이어지면 … 페이지 별로 나눠줘"): 표 행이 PDF 에서 쪽에 걸치면 웹도 그 행을 쪽마다 나눈다.
// 서버 나눔(breaks)은 단위(행 묶음)의 첫머리뿐이라 단위 안에서 넘어가는 쪽은 「시작하는 단위가 없는 쪽」(옛 빈 쪽 표지)이나 split·repeat 쪽으로만 드러난다 — 그때 앞 쪽 상자의
// 마지막 표 조각을 칸 블록의 PDF 쪽(mapping.pages)으로 잘라 뒤를 그 쪽 머리의 이어짐 조각으로 보낸다. 문단 요소는 옮길 뿐 복제하지 않는다(같은 문단이 두 곳에 없다 — 편집·저장 그대로).
// 나뉜 칸의 뒷부분 = 이어짐 칸(td.cell-cont — 원래 칸의 빈 사본에 뒤 블록을 옮김, 화면 rowSpan 은 조각 안 행 수·모델 값은 data-rs), 행 안에서 나눈 행의 뒷부분 = 이어짐 행(tr.row-cont),
// 앞부분 행 = tr[data-cut]. 쪽을 다시 나누기 전에 rowHeal 이 모두 되돌린다(흐름 state.flow 의 행·칸 요소는 그대로).
let rowParts = { ghosts: [], saved: new Map(), heads: [] };

function rowHeal() {
  for (const g of rowParts.ghosts) { // 만든 차례대로 — 여러 쪽에 걸친 칸도 블록 차례가 지켜진다
    g._src.append(...g.childNodes);
    g.remove();
  }
  for (const [td, o] of rowParts.saved) { td.rowSpan = o.rs; td.style.height = o.h; delete td.dataset.rs; td._next = null; }
  for (const tr of rowParts.heads) delete tr.dataset.cut;
  rowParts = { ghosts: [], saved: new Map(), heads: [] };
}

function rowCarry(body, from, to, m) {
  // 앞 쪽 상자(body = from 쪽)의 마지막 표 조각에서 from+1 … to 쪽 몫을 잘라낸다 -> Map(쪽 → 그 쪽 머리에 둘 이어짐 조각). to 쪽 몫은 그 쪽이 split·repeat 일 때만
  // (ok·moved 는 서버가 그 쪽 머리를 단위의 첫머리로 확인한 쪽 — 앞 단위에 뒤 쪽으로 잡힌 글은 되풀이 글의 잘못 잡힘으로 본다). 문서 끝은 to = 쪽 수 + 1.
  const out = new Map();
  let seg = body.lastElementChild, at = 0; // at = seg 를 둘 쪽(0 = 아직 앞 쪽 상자 안)
  if (!seg || seg.tagName !== "TABLE" || !seg.classList.contains("tbl") || !seg.tBodies[0]) return out;
  const st = (m.pageStatus || {})[to];
  const end = Math.min(st === "split" || st === "repeat" ? to : to - 1, m.pageCount);
  for (let k = from + 1; k <= end; k++) {
    const plan = rowCutPlan(seg, k, m.pages || {});
    if (!plan) continue;
    if (plan.whole) { if (at) out.delete(at); else seg.remove(); } // 조각 전체가 k 쪽 이후 — 조각째 옮긴다
    else seg = rowCutApply(seg, plan);
    out.set(k, seg);
    at = k;
  }
  return out;
}

function rowCutPlan(seg, k, pages) {
  // 표 조각에서 k 쪽 이후 몫이 시작하는 자리 -> null(없음) | {whole}(조각 전체) | {R, inner, at: [[칸, 뒤로 보낼 첫 블록 번호]]} — inner = R 행 안에서, 아니면 R 행 앞에서.
  // 블록마다 PDF 시작 쪽으로 앞(−)·뒤(+)·모름(0)을 매기고 어긋남(R 위 칸의 뒤 블록 + R 아래 칸의 앞 블록)이 가장 적은 행을 고른다 — R 을 지나는 칸은 칸마다 따로 나누므로 안 센다.
  // 같으면 아래 행(자리 모르는 빈 행은 앞 쪽에 남김), 안 나누는 것보다 나을 때만(짧은 칸 글 하나가 뒤 쪽으로 잘못 잡힌 것으로 나누지 않게).
  // 무게: 긴 글 3 · 짧은 글(5자 이하 — 「가까운 자리」 매핑이라 쪽이 틀릴 수 있음, 넘침 밀기와 같은 기준) 1. 짧은 글은 여럿이 모여 **행**을 고르는 데만 쓰고(양식 43→44쪽 「20××년」 행들),
  // **칸 안**에서 블록을 나누거나 행 안 나눔을 정하는 데는 긴 글만 쓴다(양식 65→66쪽 병합 칸의 「7」 하나가 뒤 쪽으로 잡혔다고 그 글을 옮기지 않게).
  const trs = [...seg.tBodies[0].rows];
  if (!trs.length) return null;
  const first = +trs[0].dataset.row, last = +trs[trs.length - 1].dataset.row;
  const vote = (b) => { // 칸 안 표·나란한 묶음은 안 문단들 가운데 가장 앞 쪽(긴 글이 있으면 긴 글만으로)
    let q = 0, w = 0;
    for (const p of b.classList.contains("para") ? [b] : b.querySelectorAll(".para")) {
      const x = pages[p.dataset.id];
      if (!x || !x.length) continue;
      const pw = (state.texts[p.dataset.id] ?? state.original[p.dataset.id] ?? "").trim().length > 5 ? 3 : 1;
      if (pw > w || (pw === w && x[0] < q)) { q = x[0]; w = pw; }
    }
    return q >= k ? w : -w;
  };
  const sum = (v, sign) => v.reduce((a, x) => a + (x * sign > 0 ? x * sign : 0), 0);
  const parts = []; // 조각의 칸(이어짐 칸 포함) — r = 놓인 행, r1 = 이 조각 안에서 닿는 마지막 행
  for (const tr of trs) for (const td of tr.cells) {
    const votes = [...td.children].map(vote);
    parts.push({ td, r: +tr.dataset.row, r1: Math.min(last, +td.dataset.r + (+td.dataset.rs || td.rowSpan) - 1), votes, after: sum(votes, 1), before: sum(votes, -1) });
  }
  let R = -1, best = parts.reduce((a, p) => a + p.after, 0); // 처음 = 안 나눌 때의 어긋남(뒤 블록 전부)
  if (!best) return null;
  for (let r = first; r <= last; r++) {
    let cost = 0, has = false;
    for (const p of parts) {
      if (p.r1 < r) cost += p.after;
      else if (p.r > r) cost += p.before;
      else if (p.after) has = true;
    }
    if (has && (cost < best || (cost === best && R >= 0))) { best = cost; R = r; }
  }
  if (R < 0) return null;
  const cutAt = (votes) => { // 칸 안: 뒤로 보낼 첫 블록 — 「앞에 남는 뒤 블록 + 뒤로 가는 앞 블록」(긴 글만)이 가장 적은 자리(같으면 뒤쪽 — 자리 모르는 빈 줄·짧은 글은 앞 쪽에 남김)
    const v = votes.map((x) => (x >= 3) - (x <= -3));
    let cost = v.filter((x) => x < 0).length, low = cost, at = 0;
    for (let i = 1; i <= v.length; i++) {
      cost += v[i - 1];
      if (cost <= low) { low = cost; at = i; }
    }
    return at;
  };
  if (parts.some((p) => p.r === R && p.votes.some((x) => x <= -3))) { // R 행의 제 칸에 앞 쪽 블록(긴 글)이 있다 — 행 안에서 나눈다(R 을 지나는 칸 모두에 이어짐 칸)
    const at = parts.filter((p) => p.r <= R && R <= p.r1).map((p) => [p.td, cutAt(p.votes)]);
    if (at.some(([td, i]) => i < td.children.length)) return { R, inner: true, at };
    if (R === last) return null;
    R += 1; // 옮길 긴 글이 없다(R 행의 뒤 쪽 표는 짧은 글뿐) — R 행은 앞 쪽에 두고 다음 행부터
  }
  if (R === first) return { whole: true };
  return { R, inner: false, at: parts.filter((p) => p.r < R && R <= p.r1).map((p) => [p.td, cutAt(p.votes)]) }; // R 행부터 통째로 — 위에서 내려오는 병합 칸만 이어짐 칸
}

function rowCutApply(seg, plan) {
  // 표 조각을 plan 자리에서 잘라 뒤를 새 이어짐 조각으로(아직 어디에도 안 붙임) -> 그 조각
  const trs = [...seg.tBodies[0].rows];
  const first = +trs[0].dataset.row, last = +trs[trs.length - 1].dataset.row;
  const { R, inner } = plan, i = trs.findIndex((tr) => +tr.dataset.row === R);
  const next = seg.cloneNode(false);
  next.classList.add("cont");
  next.append(seg.querySelector("colgroup").cloneNode(true), el("tbody"));
  let head = trs[i]; // 이어짐 칸을 둘 행 — 행 앞 나눔이면 R 행, 행 안 나눔이면 새 이어짐 행
  if (inner) {
    trs[i].dataset.cut = "1";
    rowParts.heads.push(trs[i]);
    head = el("tr", "row-cont");
    head.dataset.row = R;
    next.tBodies[0].append(head, ...trs.slice(i + 1));
  } else next.tBodies[0].append(...trs.slice(i));
  for (const [td, n] of [...plan.at].sort((a, b) => +a[0].dataset.c - +b[0].dataset.c)) {
    const cr = +td.dataset.r, rs = +td.dataset.rs || td.rowSpan;
    const g = td.cloneNode(false);
    g.classList.add("cell-cont");
    g.classList.remove("sel");
    if (!td._src && !rowParts.saved.has(td)) rowParts.saved.set(td, { rs: td.rowSpan, h: td.style.height });
    td.dataset.rs = g.dataset.rs = rs; // 모델 rowSpan — 표 칸 고르기(table_edit.js cellBox)·표 메뉴가 화면 rowSpan 대신 본다
    td.rowSpan = R - Math.max(cr, first) + (inner ? 1 : 0);
    g.rowSpan = Math.min(cr + rs - 1, last) - R + 1;
    if (inner) td.style.height = g.style.height = ""; // 저장 높이는 두 쪽 몫 — 나눈 칸은 내용 높이로
    g.append(...[...td.children].slice(n));
    g._src = td._src || td;
    td._next = g;
    rowParts.ghosts.push(g);
    head.insertBefore(g, (inner ? null : [...head.cells].find((x) => +x.dataset.c > +g.dataset.c)) || null);
  }
  return next;
}

function pushTail(tr) {
  // 넘침 밀기 — 행 안에서 나눈 앞부분 행(PDF 로 이 쪽이라 행째 밀지 않는다): 가장 아래까지 내려온 칸의 마지막 블록이 자리 모르는 문단·짧은 글(5자 이하)이면
  // 그 블록만 이어짐 칸 맨 앞으로. 그 밖(자리 아는 글·표·그림, 이어짐 칸 없는 칸)이면 false.
  let low = null, y = -Infinity;
  for (const td of tr.cells) {
    const b = td.lastElementChild, bottom = b ? b.getBoundingClientRect().bottom : -Infinity;
    if (bottom > y) { y = bottom; low = td; }
  }
  const b = low && low._next && low._next.isConnected ? low.lastElementChild : null;
  if (!b || !b.classList.contains("para")) return false;
  const t = (state.texts[b.dataset.id] ?? state.original[b.dataset.id] ?? "").trim();
  if (state.mapping.pages[b.dataset.id] && t.length > 5) return false;
  low._next.prepend(b);
  return true;
}

function gapPage(n) {
  // 이 쪽에서 시작하는 문단·표 행도, 앞 쪽 표 행에서 넘어온 칸 블록(행 안 나눔)도 없음 — 앞 쪽의 긴 문단·칸 안 표가 이어지거나 그림만 있는 쪽(웹은 문단·칸 안 표 안에서 나누지 않음)
  const d = el("div", "gap-page");
  d.style.zoom = state.zoom; // 배율은 쪽 상자·빈 쪽 표지마다(「확대」 절 zoomApply)
  d.dataset.page = n;
  const b = el("button", null, `${n}쪽 — 앞 쪽의 긴 문단·칸 안 표가 이어지는 쪽(웹에서는 그 안에서 나누지 않음) · PDF 로 보기`);
  b.type = "button";
  b.onclick = () => { const s = state.mapping && state.mapping.sheets ? state.mapping.sheets[n - 1] : n; state.pdfWhich = "original"; syncSeg(); state.pdfPage = s; showTab("Pdf"); setPanel(true); };
  d.append(b);
  return d;
}

function markUnmapped() {
  const m = state.mapping;
  if (!m) return;
  for (const p of document.querySelectorAll(".para")) {
    const t = state.original[p.dataset.id];
    const miss = t && !m.pages[p.dataset.id] && /[\p{L}\p{N}]/u.test(t);
    p.classList.toggle("unmapped", !!miss);
    if (miss) p.title = `${APP()} PDF 에서 이 문단의 위치를 찾지 못했습니다(파일에는 그대로 있음)`;
  }
}

function renderList(box, blocks) {
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    let node;
    if (b.inlineRow) {
      const rid = b.inlineRow, items = new Map(), at = [];
      node = el("div", `inline-row ${b.align || ""}`);
      for (; i < blocks.length; i++) {
        const x = blocks[i];
        if (x.inlineRow === rid) {
          const it = el("div", "inline-item");
          it.append(renderBlock(x));
          items.set(x.id, it);
          node.append(it);
          if (x.rowAtMm != null) at.push([x.rowAtMm, x.widthMm || 0, it]);
        } else if (x.captionOf && items.has(x.captionOf)) {
          items.get(x.captionOf).append(renderBlock(x));
        } else break;
      }
      i -= 1;
      if (at.length && at.length === items.size) { // 나란히 뜬 그림(hwpx_doc._side_pics) — 한글의 가로 자리 차례·간격 그대로(단 왼끝에서 mm)
        node.className = "inline-row at";
        let end = 0;
        for (const [x, w, it] of at.sort((p, q) => p[0] - q[0])) {
          it.style.marginLeft = `${Math.max(0, x - end)}mm`;
          node.append(it);
          end = Math.max(end, x) + w;
        }
      }
    } else {
      node = renderBlock(b);
    }
    box.append(node);
  }
}

function renderBlock(b) {
  if (b.type === "paragraph") return renderPara(b);
  if (b.type === "table") return renderTable(b);
  if (b.type === "image") return renderImage(b);
  return el("div");
}

const disp = (t) => (t || "").replaceAll(LS, "\n");
// 문서 글꼴(spec_hwpx_웹편집 ② §3-3 — app/fonts.py): 서버가 언어별 글꼴마다 @font-face 별칭을 준다(webFonts). 영문·한자·일어 별칭은
// unicode-range 로 그 글자만 그리고, 나머지는 한글 글꼴 별칭 → 웹 기본. 별칭이 없는 글꼴은 이름 그대로(브라우저가 못 찾으면 웹 기본).
const FALLBACK = `"HCR Dotum", "함초롬돋움", "Malgun Gothic", sans-serif`;
const LANG_FONT = [["LATIN", "fontLatin"], ["HANJA", "fontHanja"], ["JAPANESE", "fontJapanese"], ["SYMBOL", "fontSymbol"]];
const SCRIPT_SIZE = 0.64, SUP_RISE = 0.44, SUB_DROP = 0.15; // 한글 윗·아래첨자(app/fonts.py — 윗첨자는 한글 2020 PDF 실측, 아래첨자 내림은 미실측)
const qf = (s) => `"${String(s).replace(/"/g, "")}"`;
function fontStack(f) {
  const a = (state.webFonts && state.webFonts.alias) || {};
  const out = [];
  for (const [lang, key] of LANG_FONT) if (f[key] && a[lang] && a[lang][f[key]]) out.push(qf(a[lang][f[key]]));
  if (f.font) out.push(qf((a.HANGUL && a.HANGUL[f.font]) || f.font));
  return [...out, FALLBACK].join(", ");
}

function setDocFonts(w) {
  state.webFonts = w || {};
  let st = $("docFonts");
  if (!st) { st = el("style"); st.id = "docFonts"; document.head.append(st); }
  st.textContent = state.webFonts.css || "";
}

function scriptLook(s, r, f) {
  const size = r.sizePt || f.sizePt || 10;
  s.style.fontSize = `${(size * SCRIPT_SIZE).toFixed(2)}pt`;
  // 올림·내림은 position: relative 로 — vertical-align 은 올린 만큼 줄 상자를 키워 칸·문단이 한글보다 높아진다(한글은 첨자가 줄 높이를 안 바꿈, ② §3-5)
  s.style.position = "relative";
  s.style.top = `${(r.script === "sup" ? -size * SUP_RISE : size * SUB_DROP).toFixed(2)}pt`;
}

function renderPara(b, text = null) {
  const p = el("div", "para");
  p.dataset.id = b.id;
  p.contentEditable = PEEK ? "false" : PLAIN ? "plaintext-only" : "true"; // 옆 문서 화면은 보기만(spec_작업 ② §12)
  p.spellcheck = false;
  p.setAttribute("role", "textbox");
  p.setAttribute("aria-multiline", "true");
  p.setAttribute("aria-label", b.captionOf ? "캡션 문단" : "문단");
  const f = b.format || {};
  paraLook(p, f);
  if (b.list && b.list.label) p.dataset.label = b.list.label;
  // 문단 끝 빈 런이 글보다 크면 한글은 마지막 줄을 그 크기로 높인다 — 끝에 보이지 않는 글자(::after)를 그 크기로(② §3-4)
  if (b.endSizePt) { p.classList.add("end-size"); p.style.setProperty("--end-size", `${b.endSizePt}pt`); }
  leadShift(p, b, f);
  const runs = text == null ? b.runs || [{ text: b.text, format: null }] : [{ text, format: null }];
  // 한글은 줄마다 그 줄의 가장 큰 글자로 줄 높이를 잡는다(13pt 라벨 + 11pt 설명 문단의 둘째 줄 = 11pt × 줄 간격, ② §3-5). 문단 글자 크기를 런 최소 크기로 두고
  // 런마다 크기를 주면 CSS 줄 상자도 줄마다 그 줄 런으로 정해진다. 라벨(::before)은 문단 크기 그대로(--para-size). 크기 없는 런이 있으면(docx) 안 한다.
  const base = f.sizePt || 10, sized = runs.filter((r) => r.format && !r.format.script && /\S/.test(r.text || ""));
  const small = sized.every((r) => r.format.sizePt) ? Math.min(base, ...sized.map((r) => r.format.sizePt)) : base;
  if (small < base) { p.style.fontSize = `${small}pt`; p.style.setProperty("--para-size", `${base}pt`); }
  let lead = leadOn(p); // 문단 첫머리 빈칸을 늘어나지 않는 조각으로(② §3-4 「줄 앞 공백」) — 빈칸 아닌 글자가 나올 때까지
  for (const r of runs) {
    const t = disp(r.text), m = lead ? leadLen(t) : 0, s = el("span", null, m ? null : t);
    if (m) { s.append(el("span", "lead-sp", t.slice(0, m))); if (m < t.length) s.append(t.slice(m)); }
    if (m < t.length) lead = false;
    if (t.includes("\u2002") && ((r.format || f).spacingPct || 0)) nbWrap(s); // 묶음 빈칸 — 자간이 있는 글에서만 자간 0 조각으로(② §8-8)
    if (r.format) charLook(s, r.format, f, small);
    else if (f.script) scriptLook(s, f, f); // 문단 전체가 첨자 — 줄 높이는 문단 크기로 두고 글만 윗·아래로
    p.append(s);
  }
  if (b.pics && b.pics.length) picsPlace(p, b.pics); // 글 속 그림 — 글과 같은 줄의 그 자리에(② §3-6)
  if (state.edited.has(b.id)) p.classList.add("edited");
  return p;
}

// 글 속 그림(spec_hwpx_웹편집 ② §3-6): 글이 있는 문단에 글자처럼 취급으로 놓인 그림 — 한글은 글과 같은 줄의 그 자리에 놓는다(글머리 아이콘 「▶ 제목」).
// 서버가 문단 블록에 pics [{id, at(그 그림 앞까지의 글자 수 — readText 단위), media, widthMm, heightMm}] 를 싣고 그 그림 블록에는 inlineOf(문단 id)를 단다.
// 그림 블록은 전처럼 문단 뒤에 있고(renderImage 가 빈 자리 표시로 — 흐름 항목·칸 자식 수는 블록과 같다) 그림은 문단 안에 인라인으로 그린다.
// 그림은 그리기용일 뿐 글 구조가 아니다 — readText·offsetIn·pointAt 은 글 노드만 본다.
function picNode(x) {
  const ext = (x.media || "").split(".").pop().toLowerCase();
  const dress = (n) => { n.dataset.pic = x.id; n.contentEditable = "false"; n.style.width = `${x.widthMm || 4}mm`; n.style.height = `${x.heightMm || 4}mm`; return n; };
  const ph = () => { // 브라우저가 못 그리는 그림(wmf·emf …)·연결 그림 — 크기만 맞춘 자리 표시
    const s = el("span", "pic-in pic-ph");
    s.title = x.media ? `그림 (${ext.toUpperCase()} — 브라우저가 못 그림, PDF 탭에서 확인)` : "그림 (연결 그림)";
    return dress(s);
  };
  if (!x.media || !IMG_OK.has(ext)) return ph();
  const img = new Image();
  img.className = "pic-in";
  img.alt = "";
  img.loading = "lazy";
  img.draggable = false; // 편집 상자 안에서 끌어 옮기지 못하게 — 그림의 자리는 파일이 정한다
  img.onerror = () => img.replaceWith(ph());
  img.src = `/api/docs/${state.id}/media?name=${encodeURIComponent(x.media)}`;
  return dress(img);
}

function picsPlace(p, pics) {
  // 뒤 자리부터 · 같은 자리는 뒤 그림부터 넣고, 늘 그 자리에 이미 놓인 그림들의 앞에 둔다 — 그림의 차례가 문서와 같다
  for (const x of [...pics].sort((a, z) => a.at - z.at).reverse()) {
    const pic = picNode(x);
    let [n, k] = pointAt(p, x.at);
    if (n === p) { p.prepend(pic); continue; } // 글 노드가 없다(빈 글)
    if (k > 0 && k < n.data.length) { n = n.splitText(k); k = 0; }
    let at = n;
    if (k === 0) { // 글 노드의 앞 — 조각(런 · 첫머리 빈칸 조각)의 맨 앞이면 조각 밖에
      while (at.parentNode !== p && !at.previousSibling) at = at.parentNode;
      while (at.previousSibling && at.previousSibling.nodeType === Node.ELEMENT_NODE && at.previousSibling.classList.contains("pic-in")) at = at.previousSibling;
      at.before(pic);
    } else { // 글 노드의 뒤 — 조각의 맨 뒤면 조각 밖에
      while (at.parentNode !== p && !at.nextSibling) at = at.parentNode;
      at.after(pic);
    }
  }
}

// 글을 고친 뒤(input · 조합 끝) 글 속 그림을 제자리에 — 그림은 글 편집으로 지워지거나 옮겨지지 않는다(글만 서버로 간다 — 파일의 그림은 그대로라 화면만 어긋난다):
// 지워진 그림은 다시 넣고, 문단 맨 앞 그림(at 0) 앞에 친 글은 그림 뒤로 보낸다(파일에서도 그 글은 그림 뒤다). 커서는 글자 자리로 되살린다.
function picsFix(p) {
  const b = state.byId.get(p.dataset.id);
  if (!b || !b.pics || !b.pics.length) return;
  const have = new Map([...p.querySelectorAll(".pic-in")].map((n) => [n.dataset.pic, n]));
  const lead = (n) => { const r = document.createRange(); r.setStart(p, 0); r.setEndBefore(n); return r.toString().length; }; // 그 그림 앞의 글자 수
  const bad = b.pics.filter((x) => { const n = have.get(x.id); return !n || (x.at === 0 && lead(n) > 0); });
  if (!bad.length) return;
  const redo = bad.some((x) => x.at === 0) ? b.pics.filter((x) => x.at === 0 || bad.includes(x)) : bad; // 맨 앞 그림은 함께 다시(차례)
  const o = document.activeElement === p ? selOffsets(p) : null;
  for (const x of redo) { const n = have.get(x.id); if (n) n.remove(); }
  picsPlace(p, redo);
  if (o) setCaret(p, o.start, o.end);
}

// 묶음 빈칸(U+2002 — hwpx 의 hp:nbSpace, spec_hwpx_웹편집 ② §8-8 「묶음 빈칸」): 한글은 0.5em × 장평으로 찍고 자간을 곱하지 않으며 양쪽 정렬로 늘리지 않는다(레터 뒤 빈칸이 이것이면
// 첫 줄의 글 시작이 줄마다 밀리지 않는다). 글꼴의 EN SPACE 가 0.5em 이고 브라우저도 이 글자는 양쪽 정렬로 늘리지 않으므로 그대로 맞는다 — 자간이 있는 글에서만 그 글자를 자간 0 조각(.nb-sp — 인라인)으로 감싼다.
// 조각은 그리기용이다(글 구조가 아니다 — readText·offsetIn 은 글 노드만 본다).
function nbWrap(s) {
  for (const n of [...s.childNodes]) {
    if (n.nodeType !== Node.TEXT_NODE || !n.data.includes("\u2002")) continue;
    n.replaceWith(...n.data.split(/(\u2002+)/).filter(Boolean).map((x) => (x[0] === "\u2002" ? el("span", "nb-sp", x) : document.createTextNode(x))));
  }
}

// 장평(글자 가로 배율, spec_hwpx_웹편집 ② §3-3): 문단 상자를 1/장평 배 넓게 잡고 scaleX(장평)로 줄여 그린다 — 글자가 가로로 줄고 줄 나눔도 한글과 같은 폭에서.
// 한글 글자 간격 = 글자 폭 × 장평 × (1 + 자간) — 자간은 장평을 적용한 폭 기준(PDF 실측: 장평 80%·자간 −18% = 0.652em, 0.8×0.82 = 0.656)이라
// 줄인 상자 안의 자간은 그대로(전각 글자 1em 기준 letter-spacing), 들여쓰기·여백만 1/장평 배로 준다.
const ratioOf = (f) => (f.ratioPct > 0 ? f.ratioPct / 100 : 1);

// 빈칸 폭(spec_hwpx_웹편집 ② §3-4 「빈칸 폭」): 한글은 「글꼴에 어울리는 빈칸」 을 끈 글자 모양(halfSpace — 대부분)의 빈칸을 글꼴과 무관하게 0.5em × 장평 × (1 + 자간)으로 찍는다
// (한글 PDF 실측 — references/한글_문단모양_줄나눔.md 「글자 폭」). 브라우저는 글꼴의 빈칸 폭(함초롬바탕 0.30em · 돋움 0.33em · 맑은 고딕 0.35em)으로 그려서, 개요 줄의 글 시작이 한글보다
// 왼쪽에 놓여 둘째 줄(내어쓰기 자리 — 한글 폭으로 맞춘 값)과 어긋나 보였고(「 ㅇ 」 14pt 에서 2mm) 줄마다 낱말이 한글보다 더 들어갔다. → 빈칸마다 모자란 폭을 더한다.
// 값은 CSS 가 셈한다(style.css `.para.hsp`): 빈칸 = word-spacing(--hs-w − --hs-f), 첫머리 조각(.lead-sp)은 letter-spacing(--hs-l − --hs-f) — em 은 쓰는 요소의 글자 크기로 풀리므로
// 크기가 다른 런·첨자도 제 크기로 맞는다. --hs-f = 그 글꼴의 빈칸 폭(브라우저가 실제로 그리는 글꼴을 캔버스로 잰 값 — :root 의 --nfm-sp-N), q = 글자 간격 배(1 + 자간 · 런 장평이
// 문단과 다르면 kr(1+s)/k — charLook): 한글 빈칸 = 0.5q em · 웹 빈칸 = 글꼴 빈칸 + 자간 (q − 1)em + word-spacing 이므로 --hs-w = (1 − 0.5q)em · --hs-l = 0.5q em.
// halfSpace 가 아닌 글자(글꼴에 어울리는 빈칸 켬)는 더하는 값이 0 이다. Word(docx)는 글꼴 빈칸 그대로라 안 건다.
const SPACE = { keys: new Map(), cv: null }; // 글꼴 열쇠(기울임·굵기·글꼴 차례 — 캔버스 font 글) → { n, em }
function spaceMeasure(font) { // -> 그 글꼴 차례가 그리는 빈칸의 폭(em). 못 재면 0.5 = 더하는 값 0(예전 그대로)
  const cv = SPACE.cv || (SPACE.cv = document.createElement("canvas").getContext("2d"));
  cv.font = "10px serif";
  cv.font = font;
  if (cv.font === "10px serif") return 0.5; // 캔버스가 그 글꼴 글을 못 읽음
  const em = cv.measureText(" ").width / 200;
  return em > 0 && em < 2 ? Math.round(em * 1000) / 1000 : 0.5;
}
function spaceVar(stack, bold, italic) { // -> 그 글꼴의 빈칸 폭을 담은 :root 변수(처음 보는 글꼴이면 재서 적는다)
  const font = `${italic ? "italic " : ""}${bold ? 700 : 400} 200px ${stack}`;
  let k = SPACE.keys.get(font);
  if (!k) {
    k = { n: SPACE.keys.size, em: spaceMeasure(font) };
    SPACE.keys.set(font, k);
    document.documentElement.style.setProperty(`--nfm-sp-${k.n}`, `${k.em}em`);
  }
  return `var(--nfm-sp-${k.n})`;
}
// 웹 글꼴(url)이 늦게 오면 그 전에 잰 폭은 대신 그린 글꼴의 것이다 — 글꼴이 다 온 뒤 다시 재서 바뀐 것만 :root 에 다시 적는다(문단은 변수를 따라 저절로 바뀐다). -> 바뀐 것이 있는가
function spaceRemeasure() {
  let changed = false;
  for (const [font, k] of SPACE.keys) {
    const em = spaceMeasure(font);
    if (em === k.em) continue;
    k.em = em;
    document.documentElement.style.setProperty(`--nfm-sp-${k.n}`, `${em}em`);
    changed = true;
  }
  return changed;
}
document.fonts.addEventListener("loadingdone", spaceRemeasure);
// 문단·런 하나의 빈칸 값 셋 [--hs-f, --hs-w, --hs-l] — c = 그 글자 모양(문단 서식 f 또는 런 서식 r), q = 글자 간격 배
function spaceVars(c, q) {
  const r4 = (v) => Math.round(v * 10000) / 10000;
  return c.halfSpace ? [spaceVar(fontStack(c), c.bold, c.italic), `${r4(1 - q / 2)}em`, `${r4(q / 2)}em`] : ["0.5em", "0.5em", `${r4(q - 0.5)}em`];
}
function spaceLook(st, v) {
  st.setProperty("--hs-f", v[0]);
  st.setProperty("--hs-w", v[1]);
  st.setProperty("--hs-l", v[2]);
}

// 왼쪽 여백·첫 줄 — paraLook 과, 서버가 문단 여백만 바꿨을 때(글 고침 응답 applyServer · 개요 줄 자리 규칙 outline_format.js — spec_hwpx_웹편집 ② §8-1)가 같이 쓴다.
function indentLook(st, f) {
  const k = ratioOf(f), left = f.indentLeftMm || 0, first = f.firstLineMm || 0;
  // 한글 내어쓰기(음수)는 첫 줄을 왼쪽 여백에 두고 나머지 줄을 더 들인다 — CSS 로는 padding-left = left + |intent|, text-indent = intent
  st.paddingLeft = `${(left + (first < 0 && state.format !== "docx" ? -first : 0)) / k}mm`; // Word 내어쓰기: 첫 줄 = left − hanging(spec_docx_웹편집 ② §2, newfilemanager-6e 부탁)
  st.textIndent = first ? `${first / k}mm` : "";
}

function paraLook(p, f) {
  const st = p.style;
  const k = ratioOf(f);
  if (f.sizePt) st.fontSize = `${f.sizePt}pt`;
  if (f.font) st.fontFamily = fontStack(f);
  if (f.bold) st.fontWeight = "700";
  if (f.italic) st.fontStyle = "italic";
  if (f.underline) st.textDecoration = "underline";
  if (f.color && f.color !== "#000000") st.color = f.color;
  if (f.spacingPct) st.letterSpacing = `${f.spacingPct / 100}em`;
  if (state.format !== "docx") { p.classList.add("hsp"); spaceLook(st, spaceVars(f, 1 + (f.spacingPct || 0) / 100)); } // 빈칸 폭(② §3-4 「빈칸 폭」)
  st.textAlign = { justify: "justify", distribute: "justify", center: "center", right: "right" }[f.align] || "left";
  if (f.lineSpacingPct) st.lineHeight = String(Math.max(0.8, f.lineSpacingPct / 100));
  indentLook(st, f);
  if (f.indentRightMm) st.paddingRight = `${f.indentRightMm / k}mm`;
  if (k !== 1) {
    p.classList.add("ratio");
    st.width = `calc(100% / ${k})`;
    st.marginRight = `calc(100% - 100% / ${k})`; // 넓힌 만큼 오른쪽 여백을 빼서 자리(레이아웃 폭)는 그대로
    st.transform = `scaleX(${k})`;
    st.transformOrigin = "0 0";
  }
  // 문단 위·아래 간격: 한글은 앞 문단 아래 간격 + 뒤 문단 위 간격을 더한다(PDF 실측 — CSS margin 은 겹쳐 큰 쪽만 남음) → padding 으로(② §3-4).
  // Word(docx)는 아직 안 재서 예전대로 margin.
  const pad = state.format !== "docx";
  if (f.spaceBeforePt) st[pad ? "paddingTop" : "marginTop"] = `${f.spaceBeforePt}pt`;
  if (f.spaceAfterPt) st[pad ? "paddingBottom" : "marginBottom"] = `${f.spaceAfterPt}pt`;
  if (f.wordBreak !== "word") p.classList.add("char-break");
}

// 한글 줄 모형(② §3-4): 줄 = 글자 높이(크기 s, 기준선 = 줄 위 + 0.85 s) + 줄 간격 여분(아래). CSS 는 여분을 위아래 반씩 두니 글자를 (줄 높이 − s)/2 만큼
// 올린다 — position: relative 의 top 이라 배치(문단 높이·다음 문단 자리)는 그대로. s = 문단에서 가장 큰 글자(끝 빈 런 포함 — 첫 줄 기준 근사). docx 는 안 잼.
function leadShift(p, b, f) {
  if (state.format === "docx" || !f.lineSpacingPct) return;
  const s = Math.max(f.sizePt || 0, b.endSizePt || 0, ...(b.runs || []).map((r) => (r.format && !r.format.script && r.format.sizePt) || 0));
  const dy = ((Math.max(0.8, f.lineSpacingPct / 100) - 1) * s) / 2;
  if (dy) p.style.top = `${(-dy).toFixed(2)}pt`;
}

// 줄 앞 공백(② §3-4 「줄 앞 공백」): 한글의 양쪽 정렬은 줄 안 빈칸만 늘리고 문단 첫머리의 들여쓰기용 빈칸은 그대로 둔다(한글 PDF 실측 — references/HWPX_포맷.md).
// 브라우저는 pre-wrap 의 줄 앞 빈칸까지 같이 늘려서, 글이 둘째 줄로 넘어간 문단만 레터가 오른쪽으로 밀려 보였다(같은 서식인데 한 줄짜리 문단과 레터 자리가 다름 —
// 「    - …」 13pt 두 줄 문단에서 4.8mm). 첫머리 빈칸을 늘어나지 않는 조각(.lead-sp — style.css 의 inline-block)으로 감싼다.
// 조각은 그리기용일 뿐 글 구조가 아니다 — readText·offsetIn·pointAt 은 글 노드만 본다. Word(docx)는 안 쟀으니 예전대로, 문단 번호(::before 라벨)가 앞에 붙는 문단도 예전대로.
// 양쪽 정렬이 아닌 hwpx 문단(.hsp)에도 건다 — 브라우저는 문단 맨 첫 글자인 빈칸에 word-spacing 을 주지 않아서, 첫머리 빈칸의 한글 폭은 조각의 자간으로 준다(② §3-4 「빈칸 폭」).
const leadOn = (p) => state.format !== "docx" && (p.style.textAlign === "justify" || p.classList.contains("hsp")) && !p.dataset.label;
const leadLen = (t) => { let m = 0; while (t.charCodeAt(m) === 32) m += 1; return m; };

// 글을 고친 뒤의 문단을 그 꼴로 다시 맞춘다 — 조각 안에 들어온 글자는 조각 뒤로, 조각 뒤에 붙은 첫머리 빈칸은 조각 안으로, 빈 조각은 지운다.
// dry = 고칠 것이 있는지만 본다(문서는 그대로). -> 고쳤는가(고칠 것이 있는가)
function leadWrap(p, dry = false) {
  if (!leadOn(p)) return false;
  const texts = [], w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) texts.push(n);
  let changed = false, lead = true;
  for (const t of texts) {
    const len = t.data.length, m = lead ? leadLen(t.data) : 0, sp = t.parentElement.closest(".lead-sp");
    if (sp ? m < len : m > 0) {
      if (dry) return true;
      changed = true;
      if (sp) { // 조각 안의 빈칸 아닌 글자부터 조각 끝까지 — 조각 뒤로
        const r = document.createRange();
        r.setStart(t, m);
        r.setEndAfter(sp.lastChild);
        sp.after(r.extractContents());
      } else { // 조각 밖의 첫머리 빈칸 — 바로 앞이 조각이면 거기에, 아니면 새 조각에
        if (m < len) t.splitText(m);
        const prev = t.previousSibling;
        if (prev && prev.nodeType === Node.ELEMENT_NODE && prev.classList.contains("lead-sp")) prev.append(t);
        else { const s = el("span", "lead-sp"); t.before(s); s.append(t); }
      }
    }
    if (m < len) lead = false;
  }
  for (const s of p.querySelectorAll(".lead-sp")) {
    if (s.textContent) continue;
    if (dry) return true;
    s.remove();
    changed = true;
  }
  return changed;
}

function leadFix(p) { // 글이 바뀐 뒤(input · 조합 끝) — 고칠 것이 있을 때만 커서 자리를 적어 두고 맞춘 뒤 되돌린다
  if (!leadWrap(p, true)) return;
  const o = document.activeElement === p ? selOffsets(p) : null;
  leadWrap(p);
  if (o) setCaret(p, o.start, o.end);
}

// End 키 — 커서가 첫머리 빈칸 조각 안이면 조각 뒤 글의 첫 글자 뒤로 먼저 옮긴다: 조각은 제 줄 상자라 그 안에서는 End 가 조각 끝에 멈춘다.
// 뒤 글의 「처음」(조각 끝과 같은 자리)에 두면 브라우저가 그 자리를 다시 조각 안으로 보아 그대로 멈춘다 — 한 글자 안으로 들어가야 그 줄의 끝으로 간다.
function leadLeave(p, extend) {
  const s = getSelection(), f = s.focusNode, sp = f && (f.nodeType === Node.ELEMENT_NODE ? f : f.parentElement).closest(".lead-sp");
  if (!sp || !p.contains(sp)) return;
  const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) {
    if (sp.contains(n) || !(sp.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) || !n.data.length) continue;
    if (n.data[0] === "\n") return; // 첫 줄에 빈칸뿐(바로 줄 바꿈) — 조각 끝이 곧 줄 끝
    if (extend) s.extend(n, 1); else s.collapse(n, 1);
    return;
  }
}

function charLook(s, r, f, pSize = f.sizePt) {
  const st = s.style;
  if (r.script) scriptLook(s, r, f);
  else if (r.sizePt && r.sizePt !== pSize) st.fontSize = `${r.sizePt}pt`; // pSize = 문단 요소에 준 크기(런 최소 크기일 수 있음 — renderPara)
  if (r.font && fontStack(r) !== fontStack(f)) st.fontFamily = fontStack(r);
  if (!!r.bold !== !!f.bold) st.fontWeight = r.bold ? "700" : "400";
  if (!!r.italic !== !!f.italic) st.fontStyle = r.italic ? "italic" : "normal";
  if (!!r.underline !== !!f.underline) st.textDecoration = r.underline ? "underline" : "none";
  if ((r.color || "#000000") !== (f.color || "#000000")) st.color = r.color || "#000000";
  // 자간. 런 장평이 문단과 다르면 글꼴 모양은 문단 장평(상자 scaleX) 그대로 두고 전각 글자 간격만 kr(1+s)/k 로 맞춘다(근사 — 두 예제엔 없음)
  const k = ratioOf(f), kr = ratioOf(r);
  if ((r.spacingPct || 0) !== (f.spacingPct || 0) || kr !== k) st.letterSpacing = `${kr * (1 + (r.spacingPct || 0) / 100) / k - 1}em`;
  if (state.format !== "docx") { // 빈칸 폭(② §3-4 「빈칸 폭」) — 글꼴·굵기·자간·「글꼴에 어울리는 빈칸」 이 문단과 다른 런만 제 값을 적는다(같으면 문단 것을 물려받는다)
    const v = spaceVars(r, kr * (1 + (r.spacingPct || 0) / 100) / k);
    if (v.join() !== spaceVars(f, 1 + (f.spacingPct || 0) / 100).join()) spaceLook(st, v);
  }
}

const BORDER = { SOLID: "solid", DASH: "dashed", DOT: "dotted", DASH_DOT: "dashed", DASH_DOT_DOT: "dashed", LONG_DASH: "dashed",
  CIRCLE: "dotted", DOUBLE_SLIM: "double", SLIM_THICK: "double", THICK_SLIM: "double", SLIM_THICK_SLIM: "double" };

function colWidths(b, n) {
  // 열 폭 = hwpx 칸 폭을 행마다 아는 경계부터 더해(왼쪽→오른쪽, 오른쪽→왼쪽) 만든 열 경계의 차 — 한글은 칸을 제 폭대로 놓으므로 PDF 괘선과 일치한다
  // (3쪽 요약문 표 경계 11곳, spec_hwpx_웹편집 ② §3-5). 옛 추정(1칸짜리 칸 폭 → 병합 칸 나머지 균등 분할 → 평균)은 18열 중 4열만 1칸짜리라 14열을 균등 분할해
  // 레이블 열이 좁아져 네 행이 줄 바뀌었다. 경계를 못 정한 열(폭 없는 칸)만 옛 추정으로.
  const nR = b.nRows || Math.max(1, ...b.cells.map((c) => c.row + c.rowSpan));
  const occ = new Map();
  for (const c of b.cells) for (let r = c.row; r < c.row + c.rowSpan; r++) for (let k = c.col; k < c.col + c.colSpan; k++) occ.set(r * n + k, c);
  const bound = new Map([[0, 0]]);
  for (let pass = 0, grew = true; grew && pass <= n; pass++) {
    grew = false;
    for (let r = 0; r < nR; r++) {
      for (let k = 0; k < n;) {
        const c = occ.get(r * n + k), end = c ? Math.min(n, c.col + c.colSpan) : 0;
        if (!c || end <= k) break; // 빈 자리·어긋난 격자 — 이 행은 여기까지
        if (c.widthMm) {
          if (bound.has(c.col) && !bound.has(end)) { bound.set(end, bound.get(c.col) + c.widthMm); grew = true; }
          else if (bound.has(end) && !bound.has(c.col)) { bound.set(c.col, bound.get(end) - c.widthMm); grew = true; }
        }
        k = end;
      }
    }
  }
  const w = Array(n).fill(null);
  for (let k = 0; k < n; k++) if (bound.has(k) && bound.has(k + 1)) w[k] = Math.max(0.5, bound.get(k + 1) - bound.get(k));
  if (w.every((x) => x != null)) return w;
  for (const c of b.cells) if (c.colSpan === 1 && c.widthMm && w[c.col] == null) w[c.col] = c.widthMm;
  for (const c of b.cells) {
    if (c.colSpan <= 1 || !c.widthMm) continue;
    const idx = [...Array(c.colSpan).keys()].map((k) => c.col + k).filter((k) => k < n);
    const unknown = idx.filter((k) => w[k] == null);
    if (!unknown.length) continue;
    const known = idx.reduce((s, k) => s + (w[k] || 0), 0);
    unknown.forEach((k) => (w[k] = Math.max(1, (c.widthMm - known) / unknown.length)));
  }
  const ks = w.filter((x) => x != null);
  const avg = ks.length ? ks.reduce((a, x) => a + x, 0) / ks.length : 20;
  return w.map((x) => x ?? avg);
}

function renderTable(b) {
  const t = el("table", `tbl ${b.align || ""}`);
  t.dataset.tbl = b.id; // 표 도구(spec_헤딩_추출 ② §10) — 쪽 조각(cloneNode)도 같은 표 id 를 갖는다
  const nC = b.nCols || Math.max(1, ...b.cells.map((c) => c.col + c.colSpan));
  const nR = b.nRows || Math.max(1, ...b.cells.map((c) => c.row + c.rowSpan));
  const widths = colWidths(b, nC);
  const cg = el("colgroup");
  for (const w of widths) { const col = el("col"); col.style.width = `${w}mm`; cg.append(col); }
  t.append(cg);
  t.style.width = `${widths.reduce((a, x) => a + x, 0)}mm`;
  const om = b.outMarginMm; // 한글 표 바깥 여백(hp:outMargin) → style.css table.tbl 의 margin 변수(없으면 1mm — docx). 쪽 조각(.cont)은 CSS 가 위 여백 0
  if (om) { t.style.setProperty("--tbl-mt", `${om.t}mm`); t.style.setProperty("--tbl-mb", `${om.b}mm`); }
  const body = el("tbody");
  const rows = Array.from({ length: nR }, () => el("tr"));
  const lines = b.borderFills || {};
  for (const c of [...b.cells].sort((a, z) => a.row - z.row || a.col - z.col)) {
    const td = el("td", c.valign === "top" ? "top" : c.valign === "bottom" ? "bottom" : "");
    td.dataset.r = c.row; td.dataset.c = c.col; td.dataset.cell = c.id; // 표 칸 고르기(spec_owpml_편집 ② §4) — 격자 좌표·칸 id
    if (c.rowSpan > 1) td.rowSpan = c.rowSpan;
    if (c.colSpan > 1) td.colSpan = c.colSpan;
    const m = c.marginsMm || { t: 0.5, r: 1.8, b: 0.5, l: 1.8 };
    // 한글은 괘선을 저장한 칸 크기 안에 긋지만 CSS 모인 괘선(border-collapse) 1px 은 칸 네 변에 반씩 더해진다(행 높이 +1px, 글 폭 −1px) → 안쪽 여백에서 반 px 씩 뺀다(② §3-5)
    td.style.padding = `calc(${m.t}mm - 0.5px) calc(${m.r}mm - 0.5px) calc(${m.b}mm - 0.5px) calc(${m.l}mm - 0.5px)`;
    if (c.rowSpan === 1 && c.heightMm) td.style.height = `${c.heightMm}mm`; // style.css td box-sizing: border-box — 저장 높이 = 행 높이(여백·괘선 포함, 한글과 같음)
    if (c.fill) td.style.background = c.fill;
    const ln = lines[c.bf] || {};
    for (const [k, side] of [["t", "Top"], ["r", "Right"], ["b", "Bottom"], ["l", "Left"]]) {
      const x = ln[k];
      td.style[`border${side}`] = x ? `${Math.max(0.1, x.widthMm)}mm ${BORDER[x.type] || "solid"} ${x.color}` : "none";
    }
    renderList(td, c.blocks || []);
    cellLastLine(td, c.blocks || []);
    (rows[c.row] || rows[rows.length - 1]).append(td);
  }
  rows.forEach((r) => body.append(r));
  t.append(body);
  return t;
}

// 한글 칸 높이 모형(spec_hwpx_웹편집 ② §3-5): 칸 내용 = 글자 크기 + (줄 수 − 1) × 크기 × 줄 간격 + 위아래 칸 여백 — 마지막 줄엔 줄 간격 여분이 없다
// (문단이 여럿이어도 줄 사이 거리는 같음). CSS 는 마지막 줄도 크기 × 줄 간격이라 칸의 마지막 문단 아래를 그 여분(크기 × (줄 간격 − 1))만큼 당긴다
// (음수 margin — 글자 자리·줄 사이 거리는 그대로, 칸 높이만 한글처럼). docx 는 안 잼.
function cellLastLine(td, blocks) {
  if (state.format === "docx") return;
  let k = blocks.length - 1, p = td.lastElementChild;
  while (k >= 0 && blocks[k].inlineOf && p && p.classList.contains("pic-held")) { k -= 1; p = p.previousElementSibling; } // 글 속 그림의 빈 자리 표시는 건너뛴다 — 칸의 마지막 줄은 그 문단(② §3-6)
  const b = blocks[k];
  if (!b || b.type !== "paragraph" || b.inlineRow) return;
  if (!p || !p.classList.contains("para")) return;
  const f = b.format || {};
  const ls = f.lineSpacingPct ? Math.max(0.8, f.lineSpacingPct / 100) : 1.35; // 1.35 = style.css 「table.tbl td .para」 기본 줄 간격
  const s = Math.max(f.sizePt || 10, b.endSizePt || 0, ...(b.runs || []).map((r) => (r.format && !r.format.script && r.format.sizePt) || 0));
  const extra = (s * (ls - 1) * 25.4) / 72; // 글꼴 높이 = 크기(1em): 1쪽 10pt 1줄 칸 저장 4.33 = 3.53 + 여백 0.4×2, 3쪽 4.52 = 3.53 + 0.5×2 — 11-10 실측
  if (extra > 0) p.style.marginBottom = `${(-extra).toFixed(2)}mm`;
}

function renderImage(b) {
  if (b.inlineOf) return el("span", "pic-held"); // 글 속 그림 — 그 문단이 글 속 제자리에 그린다(renderPara → picsPlace). 블록 자리에는 빈 자리 표시만(② §3-6)
  const ext = (b.media || "").split(".").pop().toLowerCase();
  const w = b.widthMm || 30, h = b.heightMm || 20;
  if (!b.widthMm && !b.heightMm && b.media) return el("span");
  const ph = () => {
    const d = el("div", `img img-ph ${b.align || ""}`, b.media ? `그림 (${ext.toUpperCase()} — 브라우저가 못 그림, PDF 탭에서 확인)` : "그림 (연결 그림)");
    d.dataset.img = b.id; // 그림 블록 id — 블록 단위로 표시하는 것(편집 구역 zones.js zonesDraw)이 그림을 찾는다. data-id 는 문단 몫이라 쓰지 않는다
    d.style.width = `${w}mm`;
    d.style.height = `${h}mm`;
    return d;
  };
  if (!b.media || !IMG_OK.has(ext)) return ph();
  const img = new Image();
  img.className = `img ${b.align || ""}`;
  img.dataset.img = b.id;
  img.alt = "";
  img.loading = "lazy";
  img.style.width = `${w}mm`;
  img.style.height = `${h}mm`;
  img.onerror = () => img.replaceWith(ph());
  img.src = `/api/docs/${state.id}/media?name=${encodeURIComponent(b.media)}`;
  return img;
}

// ---------------------------------------------------------------- 편집
function readText(p) {
  let s = "";
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === Node.TEXT_NODE) s += c.data;
      else if (c.nodeName === "BR") s += "\n";
      else { if ((c.nodeName === "DIV" || c.nodeName === "P") && s && !s.endsWith("\n")) s += "\n"; walk(c); }
    }
  };
  walk(p);
  if (p.lastChild && p.lastChild.nodeName === "BR") s = s.replace(/\n$/, ""); // 빈 편집 상자에 브라우저가 남기는 끝 <br>
  return s.replace(/\r/g, "").replace(/\n/g, LS);
}

function scheduleSave(p) {
  const id = p.dataset.id;
  state.localRev += 1;
  clearTimeout(state.timers.get(id));
  state.timers.set(id, setTimeout(() => save(p), 450));
  refreshSaveState();
  renderSummary(state.verify || {});
}

function save(p) {
  const id = p.dataset.id, doc = state.id, epoch = state.epoch;
  clearTimeout(state.timers.get(id));
  state.timers.delete(id);
  const prev = state.chains.get(id) || Promise.resolve();
  const next = prev.then(async () => {
    if (epoch !== state.epoch) return;
    const text = readText(p);
    if (text === state.texts[id] && !state.failed.has(id)) { refreshSaveState(); return; }
    state.inflight += 1;
    p.classList.add("saving");
    try {
      const r = await api(`/api/docs/${doc}/blocks/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      });
      if (epoch !== state.epoch) return;
      applyServer(id, r);
      p.classList.remove("error");
      p.removeAttribute("title");
    } catch (e) {
      if (epoch !== state.epoch) return;
      state.failed.add(id);
      p.classList.add("error");
      p.title = `반영 실패: ${e.message} — 글을 다시 고치거나 「고친 문단」 탭에서 다시 반영`;
      state.editsDirty = true;
      toast(`문단을 서버에 반영하지 못했습니다: ${e.message}`, true);
    } finally {
      if (epoch === state.epoch) {
        state.inflight -= 1;
        p.classList.remove("saving");
        refreshSaveState();
        updateEdits();
      }
    }
  });
  state.chains.set(id, next.catch(() => {}));
  return next;
}

function applyServer(id, r) {
  if (r.rev != null) { if (r.rev !== state.serverRev) { fmtsRefreshSoon(); if (typeof captSoon === "function") captSoon(); if (typeof zonesInvalidate === "function") zonesInvalidate("edit"); } state.serverRev = r.rev; }
  headsMarkStale();
  if ("persistError" in r) state.persistError = r.persistError;
  logTouched();
  state.texts[id] = r.text;
  state.failed.delete(id);
  r.edited ? state.edited.add(id) : state.edited.delete(id);
  state.unrestored = new Set(r.unrestored || []);
  state.pristine = r.pristine;
  if (r.kinds) state.kinds = r.kinds;
  if (r.undo != null) state.undo = r.undo;
  const p = paraEl(id);
  if (p) p.classList.toggle("edited", r.edited);
  if (r.format) { // 서버가 문단 여백을 바꿨다(개요 줄 둘째 줄 = 글 시작 · 원래 글로 돌아와 원본 모양 — spec_hwpx_웹편집 ② §8-1): 글·커서는 그대로 두고 여백만 다시
    const b = state.byId.get(id);
    if (b) state.byId.set(id, { ...b, format: r.format }); // 새 사전으로 — 같은 블록을 기준 블록(byIdOrig)도 가리키므로 그 자리에서 고치지 않는다
    if (p) indentLook(p.style, r.format);
  }
  if (r.fmts && heads.outline) outlineApply({ fmts: r.fmts }); // 글을 고쳐 첫머리가 대표와 달라졌거나 같아진 개요 줄 — 여백의 서식 라벨을 그 자리에서(대표와 달라지면 「≠」)
  state.editsDirty = true;
  if (dv.plan) { divRunSync(); divFootSync(); } // 글을 고쳐 문서 차례가 올랐다 — 세워 둔 프로젝트 구성 계획은 낡는다(spec_구분_기준 ② §22)
}

async function flushAll() {
  for (const id of [...state.timers.keys()]) {
    const p = paraEl(id);
    if (p) save(p);
  }
  await Promise.all([...state.chains.values()]);
}

function setSaveState(cls, text, title = "") {
  const s = $("saveState");
  s.className = "save-state " + cls;
  s.textContent = text;
  s.title = title;
}

function refreshSaveState() {
  if (!state.id) return;
  const n = state.edited.size;
  if (state.inflight || state.timers.size) return setSaveState("busy", "서버에 반영 중…");
  if (state.failed.size) return setSaveState("err", `반영 실패 ${state.failed.size}개`, "「고친 문단」 탭에서 다시 반영하세요");
  if (state.pristine && state.base) // 기준이 확정본(spec_작업 ② §8) — 올린 원본과는 다른 파일
    return setSaveState("ok", n ? `글은 고쳤으나 파일은 확정 ${state.base} 와 같음` : `확정 ${state.base} · 고친 것 없음`,
      `지금 저장하면 확정 ${state.base} 의 파일과 바이트가 같습니다(올린 원본과는 다른 파일 — 「고친 문단」 탭의 확정 기록)`);
  if (state.pristine) return setSaveState("ok", n ? "글은 고쳤으나 파일은 원본과 같음" : "원본과 바이트 동일", "지금 저장하면 원본 파일과 바이트가 같습니다");
  const notDownloaded = state.localRev !== state.downloadedRev || !state.downloadedAt; // 다시 연 작업은 이 화면에서 아직 안 받음
  if (notDownloaded && state.stored && state.persistError)
    return setSaveState("err", `고친 문단 ${n}개 · 작업 저장 실패 — ${EXT()} 저장으로 받아 두세요`, `서버가 작업 폴더에 쓰지 못했습니다(다음 편집 때 다시 시도): ${state.persistError}`);
  if (notDownloaded && state.stored) return setSaveState("", ""); // 작업에 저장되는 문서는 글을 두지 않는다(2026-11-11 사용자 — 고친 수는 「고친 문단」 탭 배지에). 저장 실패만 위에서 알린다
  if (notDownloaded)
    return setSaveState("warn", `고친 문단 ${n}개 · 서버에만 임시 반영 — ${EXT()} 저장 필요`, `서버를 끄면 사라집니다. 「${EXT()} 저장」으로 내려받으세요`);
  setSaveState("ok", `고친 문단 ${n}개 · ${hhmm(state.downloadedAt)} 내려받음`, "브라우저가 파일을 저장했는지는 다운로드 목록에서 확인하세요");
}

function insertText(t) { document.execCommand("insertText", false, t); }

function bindEditing() {
  const doc = $("doc");
  doc.addEventListener("beforeinput", (e) => { if (state.busy) e.preventDefault(); }); // 구조 편집 응답을 기다리는 동안 — 그 문단이 바뀌어 끼워진다
  doc.addEventListener("keydown", (e) => {
    const p = e.target.closest && e.target.closest(".para");
    if (!p) return;
    if (state.busy && !["Escape", "Shift", "Control", "Alt"].includes(e.key)) { e.preventDefault(); return; }
    const composing = e.isComposing || e.keyCode === 229;
    const mod = (e.ctrlKey || e.metaKey) && !e.altKey;
    if (e.key === "Enter") {
      e.preventDefault(); // IME 조합 중 Enter 는 조합만 확정 — 한글 IME 는 조합이 끝난 뒤 Enter 를 한 번 더 보낸다
      if (composing) return;
      if (e.shiftKey) insertText("\n");
      else if (e.altKey) outlineKey("sibling", p); // Alt+Enter = 같은 레벨 트리(뼈대) — 개요 줄에서만(spec_hwpx_웹편집 ② §8)
      else if (outlineLine(p)) outlineKey("enter", p); // 개요 줄 Enter = 하위 레벨 새 줄
      else splitHere(p);
    } else if (e.altKey && !mod && !e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      if (composing) return;
      e.preventDefault();
      outlineLevel(p, e.key === "ArrowUp" ? -1 : 1);
    } else if (e.key === "Backspace" && !composing && !mod && outlineEmpty(p)) {
      e.preventDefault(); // 글 없는 레터 줄 — 줄(과 앞 간격 줄)을 지운다
      outlineKey("remove", p);
    } else if (e.key === "Backspace" && !composing && !mod && caretAt(p) === 0) {
      if (!neighbor(p, -1)) return; // 칸의 첫 문단 — 합칠 앞 문단 없음(그냥 아무 일 없음)
      e.preventDefault();
      structOp("merge", { id: p.dataset.id, dir: "prev" });
    } else if (e.key === "Delete" && !composing && !mod && caretAt(p) === readText(p).length) {
      if (!neighbor(p, +1)) return;
      e.preventDefault();
      structOp("merge", { id: p.dataset.id, dir: "next" });
    } else if (mod && !e.shiftKey && ["b", "i", "u"].includes(e.key.toLowerCase())) {
      e.preventDefault();
      formatChars({ [{ b: "bold", i: "italic", u: "underline" }[e.key.toLowerCase()]]: "toggle" });
    } else if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      insertText("\t");
    } else if (e.key === "End" && !mod && !e.altKey && !composing) {
      leadLeave(p, e.shiftKey); // 막지 않는다 — 조각 밖으로 옮긴 자리에서 브라우저가 줄 끝으로 간다
    } else if (e.key === "Escape") {
      p.blur();
    }
  });
  let imePara = null; // 한글 조합 중인 문단 — 조합 중에는 문단 안 노드를 옮기지 않는다(조합이 끊긴다)
  doc.addEventListener("compositionstart", (e) => { imePara = e.target.closest && e.target.closest(".para"); });
  doc.addEventListener("compositionend", (e) => {
    const p = e.target.closest && e.target.closest(".para");
    imePara = null;
    if (p) setTimeout(() => { if (!imePara && p.isConnected) { leadFix(p); picsFix(p); } }, 0); // 이어 치는 한글은 조합이 끝나자마자 다음 조합이 시작된다 — 그때는 건너뛰고 다음 input·조합 끝에(② §3-4 「줄 앞 공백」)
  });
  doc.addEventListener("input", (e) => { const p = e.target.closest(".para"); if (p) { if (!e.isComposing && !imePara) { leadFix(p); picsFix(p); } scheduleSave(p); } });
  doc.addEventListener("focusout", (e) => { const p = e.target.closest && e.target.closest(".para"); if (p && state.timers.has(p.dataset.id)) save(p); });
  doc.addEventListener("focusin", (e) => { const p = e.target.closest && e.target.closest(".para"); if (p) { select(p.dataset.id); trackCaret(); } });
  document.addEventListener("selectionchange", trackCaret);
  doc.addEventListener("paste", (e) => {
    if (PLAIN) return;
    e.preventDefault();
    insertText((e.clipboardData || window.clipboardData).getData("text/plain"));
  });
  bindCtxMenu(); // 공용 오른쪽 단추 메뉴 닫기 — 표 칸 끌어 고르기·표 메뉴는 table_edit.js 가 제 init 에서 묶는다(app.js 다음에 읽힘)
}

// ---------------------------------------------------------------- 구조·서식 편집 (spec_owpml_편집 ② §2~§4)
function offsetIn(p, node, off) {
  // 편집 상자 처음부터 (node, off) 까지의 글자 수 — readText 단위(줄 바꿈·탭 한 글자) = 서버 _text 단위
  const r = document.createRange();
  r.setStart(p, 0);
  r.setEnd(node, off);
  const d = el("div");
  d.append(r.cloneContents());
  return readText(d).length;
}

function selOffsets(p) {
  const s = getSelection();
  if (!s.rangeCount) return null;
  const r = s.getRangeAt(0);
  if (!p.contains(r.startContainer) || !p.contains(r.endContainer)) return null;
  return { start: offsetIn(p, r.startContainer, r.startOffset), end: offsetIn(p, r.endContainer, r.endOffset) };
}

function caretAt(p) {
  const o = selOffsets(p);
  return o && o.start === o.end ? o.start : -1;
}

function pointAt(p, k) {
  const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
  let n, last = null;
  while ((n = w.nextNode())) {
    if (k <= n.data.length) return [n, k];
    k -= n.data.length;
    last = n;
  }
  return last ? [last, last.data.length] : [p, p.childNodes.length];
}

function setCaret(p, start, end = start) {
  const r = document.createRange();
  r.setStart(...pointAt(p, start));
  r.setEnd(...pointAt(p, end));
  const s = getSelection();
  s.removeAllRanges();
  s.addRange(r);
}

function neighbor(p, step) {
  // 표 칸 안이면 같은 칸의 이웃 문단이 있는지(없으면 합치기 안 함), 본문이면 서버가 판단
  if (!p.parentElement.closest("td")) return true;
  const para = (q) => { while (q && !q.classList.contains("para")) q = step < 0 ? q.previousElementSibling : q.nextElementSibling; return q; };
  let q = para(step < 0 ? p.previousElementSibling : p.nextElementSibling);
  // 쪽에 걸쳐 나뉜 칸(행 안 나눔 — 이어짐 칸 td.cell-cont)이면 앞·뒤 조각의 문단도 같은 칸의 이웃이다
  for (let td = p.parentElement; !q && td && td.tagName === "TD" && (td = cellPart(td, step));) q = para(step < 0 ? td.lastElementChild : td.firstElementChild);
  return !!q;
}

function cellPart(td, step) {
  // 쪽에 걸쳐 나뉜 칸의 앞(step < 0)·뒤 조각 — 없으면 null(rowCutApply 가 조각마다 _next = 뒤 조각, 이어짐 칸에 _src = 원래 칸을 둔다)
  if (step > 0) return td._next && td._next.isConnected ? td._next : null;
  let x = td._src || null;
  while (x && x._next !== td) x = x._next;
  return x;
}

function trackCaret() {
  const s = getSelection();
  const node = s.rangeCount ? s.getRangeAt(0).startContainer : null;
  const p = node && (node.nodeType === 1 ? node : node.parentElement).closest(".para");
  if (!p || !$("doc").contains(p)) return;
  const o = selOffsets(p);
  if (!o) return;
  state.cur = { id: p.dataset.id, ...o };
  refreshToolbar(p, node.nodeType === 1 ? node : node.parentElement);
}

function refreshToolbar(p = null, at = null) {
  if (!p && state.cur) p = paraEl(state.cur.id);
  const on = !!p && !!state.id;
  for (const b of document.querySelectorAll("#docBar [data-char], #docBar [data-align], #docBar [data-indent], #tbLetter")) b.disabled = !on || state.busy; // #tbLetter = 레터 넣기(para_letter.js — spec_hwpx_웹편집 ② §8-9)
  for (const x of [$("tbSize"), $("tbColor"), $("tbFirst"), $("tbLine")]) x.disabled = !on || state.busy;
  const inCell = (on && !!p.closest("td")) || (typeof tselActive === "function" && tselActive()); // 칸 안 문단에 있거나 칸을 끌어 골랐을 때(표 모듈)
  $("tbTable").setAttribute("aria-disabled", String(!inCell));
  for (const b of document.querySelectorAll("#tbTable button")) b.disabled = !inCell || state.busy;
  $("undoBtn").disabled = !state.undo || state.busy;
  $("undoBtn").textContent = state.undo ? `↶ 실행 취소 (${state.undo})` : "↶ 실행 취소";
  $("tbTableMake").disabled = !state.id || state.format === "docx"; // 표 만들기 · 서식 변환은 hwpx 만 — 칸 밖에서도 켜져 있다(고른 글·붙여 넣은 표가 원본)
  // OWPML 상태 — 도구 줄에는 아이콘 하나만(2026-11-10 사용자): 방패 안 표시·색이 상태(index.html #owpmlState · style.css .owpml-state), 글은 도움말과 화면 낭독용 #owpmlText 에
  const o = state.owpml, st = $("owpmlState"), txt = $("owpmlText");
  st.className = "owpml-state" + (o ? ` ${o.status}` : "");
  const std = STD();
  const label = !o ? `${std} 검사 대기` : o.status === "fail" ? `${std} ✕ 거절` : o.status === "warn" ? `${std} ! 물려받은 위반` : `${std} ✓ 새 위반 없음`;
  if (txt.textContent !== label) txt.textContent = label; // 같은 글을 다시 쓰지 않는다(aria-live 가 되풀이해 읽지 않게)
  st.title = `${label}\n` + (o ? o.summary : state.format === "docx" ? "구조·서식 편집마다 OOXML 참조 규칙(관계·스타일·번호·표 구조·자식 순서)으로 검사 — 원본에 없던 종류의 위반이면 그 편집을 되돌린다"
    : "구조·서식 편집마다 OWPML(KS X 6101) 2024 스키마·참조 규칙으로 검사 — 원본에 없던 종류의 위반이면 그 편집을 되돌린다");
  if (!on) return;
  const cs = getComputedStyle(at && p.contains(at) ? at : p);
  const set = (k, v) => { const b = document.querySelector(`#docBar [data-char="${k}"]`); b.setAttribute("aria-pressed", String(v)); };
  set("bold", parseInt(cs.fontWeight, 10) >= 600);
  set("italic", cs.fontStyle === "italic");
  set("underline", (cs.textDecorationLine || cs.textDecoration || "").includes("underline"));
  if (document.activeElement !== $("tbSize")) $("tbSize").value = Math.round(parseFloat(cs.fontSize) * 0.75 * 2) / 2; // px → pt
  const f = (state.byId.get(p.dataset.id) || {}).format || {};
  for (const b of document.querySelectorAll("#docBar [data-align]")) b.setAttribute("aria-pressed", String((f.align === "distribute" ? "justify" : f.align) === b.dataset.align));
  if (document.activeElement !== $("tbFirst")) $("tbFirst").value = f.firstLineMm != null ? Math.round(f.firstLineMm) : "";
  if (document.activeElement !== $("tbLine")) $("tbLine").value = [100, 130, 150, 160, 180, 200].includes(f.lineSpacingPct) ? String(f.lineSpacingPct) : "";
}

// 편집 응답을 기다리는 동안의 표시. body 에 클래스를 달면 그 아래 문단 전부의 스타일을 다시 계산한다 — 연구개발계획서(문단 12,700개 · 요소 41,780개)에서 켤 때 0.2초 + 끌 때 0.35초가
// 편집마다 들었다(2026-11-11 개요 줄 Enter 3초). #doc 에 달아도 **물려받는 속성**이면 같다: `caret-color` 는 켜고 끄는 데 0.2 + 0.39초, `cursor` 는 0.06 + 0.06초(실측 — references/브라우저_강제배치_비용.md §3).
// 그래서 ① 글 커서 감춤은 지금 커서가 든 문단 하나에만(`.para.busy-caret` — 0초) ② 진행 커서(`#doc.busy-edit` — cursor 만)는 0.8초 넘게 걸릴 때만 단다 — 금방 끝나는 편집은 문서의 스타일을 하나도 안 건드린다.
// 입력 막기는 표시와 무관하게 state.busy(bindEditing).
let busyTimer = null, busyPara = null;
function busyMark(on) {
  clearTimeout(busyTimer);
  busyTimer = on ? setTimeout(() => $("doc").classList.add("busy-edit"), 800) : null;
  if (!on) $("doc").classList.remove("busy-edit");
  if (busyPara) busyPara.classList.remove("busy-caret");
  const a = on ? document.activeElement : null;
  busyPara = a && a.classList && a.classList.contains("para") ? a : null;
  if (busyPara) busyPara.classList.add("busy-caret");
}

async function structOp(path, body) {
  // 구조·서식 편집 한 번: 대기 중 글 반영을 끝내고 → 서버 편집(OWPML 검사) → 바뀐 최상위 블록만 바꿔 끼운다
  if (state.busy || !state.id) return null;
  const epoch = state.epoch, id = state.id; // 문서는 기다리기 전에 잡는다 — 부른 쪽이 만든 body(rev …)는 이 문서의 것이다
  state.busy = true;
  busyMark(true);
  refreshToolbar();
  try {
    await flushAll();
    // 글 반영을 기다리는 사이 다른 문서를 열었으면 보내지 않는다 — 전에는 주소를 기다린 뒤의 state.id 로 만들어, 앞 문서의 편집(「모두 반영」 의 {rev} 처럼 문서를 안 가리는 몸)이 새로 연 문서로 갔다(2026-11-16 astra — spec_헤딩_추출 ④)
    if (epoch !== state.epoch) return null;
    if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 먼저 다시 반영해야 합니다 — 「고친 문단」 탭", true); return null; }
    const r = await api(`/api/docs/${id}/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return null;
    // 같은 요청을 다시 보낸 답(에이전트 반영의 requestId — replayed)이나 화면이 아는 것보다 앞선 차례의 답은 문서 조각을 끼우지 않는다 — 실행 취소한 문단이 화면에 되살아난다(2026-11-13 astra). 지금 문서를 다시 읽는다
    if (r.replayed || (r.rev != null && r.rev < state.serverRev)) { reloadDoc(); return r; }
    state.localRev += 1;
    state.structRev = state.localRev;
    if (r.webFonts) setDocFonts(r.webFonts); // 편집이 새 글꼴 정의를 들여옴(다른 문서의 서식을 입힘) — 블록을 그리기 전에 @font-face 계획부터
    applyEditState(r);
    if (r.paged || !r.tops) reloadDoc(); // 쪽 설정이 바뀐 편집(서식 관리자 「이 문서에 입히기」 — 응답의 paged: spec_서식복사 ② §9)은 바뀐 블록만 끼우지 않고 문서를 통째로 다시 읽어 그린다(쪽 크기·여백이 바뀐다)
    else applyTops(r);
    if (r.outline) outlineApply(r.outline);
    if (r.fmts && heads.outline) outlineApply({ fmts: r.fmts }); // 서식을 바꾼 개요 줄의 새 서식 라벨(서버 outline_match.labels_now — 대표와 달라진 줄은 「≠」): 여백 표시를 그 자리에서
    if (r.focus) focusAt(r.focus);
    if (r.owpml && r.owpml.status === "warn") toast(`${STD()}: ${r.owpml.summary}`);
    return r;
  } catch (e) {
    if (epoch !== state.epoch) return null;
    structOp.lastError = e; // 부른 쪽이 상태 코드를 읽는다(doc_agent.js 의 반영 — 409 = 제안이 낡음 · 403 = 원본 문서): 부르기 전에 null 로 비우고 쓴다
    if (e.status === 422 && e.body && e.body.owpml) state.owpml = { status: "fail", summary: e.message };
    toast(e.message, true);
    return null;
  } finally {
    if (epoch === state.epoch) {
      state.busy = false;
      busyMark(false);
      refreshToolbar();
      refreshSaveState();
    }
  }
}

function applyEditState(r) {
  if (r.rev != null) { if (r.rev !== state.serverRev) { fmtsRefreshSoon(); if (typeof captSoon === "function") captSoon(); if (typeof zonesInvalidate === "function") zonesInvalidate("edit"); } state.serverRev = r.rev; }
  headsMarkStale();
  if ("persistError" in r) state.persistError = r.persistError;
  logTouched();
  state.edited = new Set(r.edited || []);
  state.kinds = r.kinds || {};
  state.unrestored = new Set(r.unrestored || []);
  state.pristine = r.pristine;
  state.undo = r.undo || 0;
  state.owpml = r.owpml || state.owpml;
  for (const [i, t] of Object.entries(r.original || {})) if (!(i in state.original)) state.original[i] = t;
  if (dv.plan) { divRunSync(); divFootSync(); } // 문서 차례가 바뀌면 세워 둔 프로젝트 구성 계획은 낡는다 — 실행 묶음의 「반영」 을 끄고 발의 글도(spec_구분_기준 ② §22)
}

function applyTops(r) {
  // 서버가 준 「바뀐 최상위 블록」으로 쪽 흐름의 그 항목들만 바꾼다(문단 나누기면 문단 둘, 칸 안 편집이면 그 표를 품은 본문 문단의 블록 전부).
  // 옛 구간 = 최상위 블록 목록(state.blocks)에서 drop 과 **응답에 든 블록의 id** 가 걸친 첫 자리 ~ 끝 자리 — 응답 블록이 그 자리를 통째로 대신한다. 응답의 id 는 drop 에 없어도 「바꿀 것」이다:
  // 개요 편집은 닿은 구간에 이웃을 하나씩 더하고(② §8) 번호 다시 매김·레벨·부분 트리 뒤 새 줄은 멀리 있는 줄까지 실어 보낸다 — drop 만 빼고 끼우면 그 이웃(앞 줄 · 뒤 표)이 화면에 두 번 그려졌다(2026-11-11).
  // 화면은 그 가운데 **실제로 바뀐 토막만** 건드린다(② §11): 옛 구간과 응답을 차례대로 맞춰, 값이 그대로인 블록(옛 블록과 JSON 이 같음) 사이사이의 바뀐·새·지운 블록 묶음마다 따로 갈아 끼운다
  // (Enter 한 번 = 그 줄과 새 줄 — 사이·뒤에 표가 있어도 표는 안 건드린다).
  const all = r.tops.blocks, ids = new Set([...r.tops.drop, ...all.map((b) => b.id)]);
  const at = [];
  state.blocks.forEach((b, i) => { if (ids.has(b.id)) at.push(i); });
  if (!at.length) { reloadDoc(); return; }
  const lo = at[0], old = state.blocks.slice(lo, at[at.length - 1] + 1), top = lo > 0 ? state.blocks[lo - 1].id : null;
  if (old.some((b) => !ids.has(b.id))) { reloadDoc(); return; } // 응답이 옛 구간을 다 덮지 않는다(사이에 낀 블록이 응답에도 drop 에도 없음) — 잃지 않게 통째로 다시 읽는다
  const same = (o, b) => !b.inlineRow && !b.captionOf && JSON.stringify(o) === JSON.stringify(b); // 나란히 놓인 개체 묶음(흐름 항목 하나에 블록 여럿)은 쪼개지 않는다
  const inOld = new Set(old.map((b) => b.id)), inNew = new Set(all.map((b) => b.id));
  let parts = [], cur = null, prev = top, i = 0, j = 0; // parts = [{gone: 옛 블록, blocks: 새 블록, after: 바로 앞의 그대로인 블록 id(넣기만 할 때의 닻)}]
  const part = () => { if (!cur) parts.push(cur = { gone: [], blocks: [], after: prev }); return cur; };
  while (i < old.length || j < all.length) {
    const o = old[i], b = all[j];
    if (o && b && o.id === b.id) {
      if (same(o, b)) { cur = null; prev = o.id; } else { part().gone.push(o); cur.blocks.push(b); }
      i += 1; j += 1;
    } else if (o && !inNew.has(o.id)) { part().gone.push(o); i += 1; } // 지운 블록
    else if (b && !inOld.has(b.id)) { part().blocks.push(b); j += 1; } // 새 블록
    else { parts = [{ gone: old, blocks: all, after: top }]; break; } // 차례가 바뀜(옮기기) — 구간을 통째로
  }
  // 최상위 블록 목록(state.blocks)도 같은 자리에서 바꿔 끼운다 — 표 모듈(tables.js xlBlocks·「표」 탭)이 이걸 읽으므로 표 행·열 편집 뒤 옛 구조를 보지 않게(astra P1, 2026-11-10)
  state.blocks.splice(lo, old.length, ...all);
  let inPlace = true; // 토막을 모두 그 자리에서 바꿨는가 — 하나라도 못 하면 흐름만 고쳐 두고 끝에 문서 전체를 다시 나눈다
  for (const p of parts) {
    const ins = !p.gone.length, drop = new Set(ins ? [p.after] : p.gone.map((b) => b.id));
    const hit = [];
    state.flow.forEach((it, k) => { if ((it.kind === "table" ? [it.id] : it.ids).some((x) => drop.has(x))) hit.push(k); });
    if (!hit.length) { reloadDoc(); return; }
    walkParas(p.blocks, (b) => { state.texts[b.id] = b.text || ""; state.byId.set(b.id, b); if (!(b.id in state.original)) state.original[b.id] = ""; });
    const a = ins ? hit[hit.length - 1] + 1 : hit[0], z = ins ? a - 1 : hit[hit.length - 1]; // 넣기만이면 닻 항목 다음 자리에 끼운다(바꿀 옛 항목 없음)
    const items = buildFlow(p.blocks.map((b) => [b, state.flow[hit[0]].sec]));
    if (items.length && !ins) items[0].pageStart = state.flow[a].pageStart;
    if (inPlace) inPlace = flowSwap(state.flow.slice(a, z + 1), items, ins ? state.flow[a - 1] : null);
    state.flow.splice(a, z - a + 1, ...items);
  }
  if (parts.length) { if (inPlace) flowSettle(); else paginate(); } // 바뀐 것이 없으면(응답이 다 그대로) 화면은 그대로
  updateEdits();
  renderSummary(state.verify || {});
}

function flowSwap(old, items, after = null) {
  // 쪽 흐름 항목 몇 개를 **그 자리에서** 바꿔 끼운다 → true(못 하면 false — 부르는 쪽이 paginate() 로 처음부터 다시 나눈다).
  // paginate() 는 #doc 을 비우고 모든 항목을 다시 붙여 문서 전체의 스타일·배치를 다시 계산시킨다(연구개발계획서 100쪽: 0.6~0.7초 — 2026-11-11 개요 줄 Enter 3초).
  // 문단 몇 줄을 바꾸는 편집은 옛 요소들이 한 쪽 상자 안에 나란히 있으면 그 자리에 새 요소를 두는 것과 결과가 같다: 남는 id 는 제 쪽에 남고, 새 id 는 쪽 자리 정보가
  // 없어 앞 항목의 쪽 상자에 이어 붙는다(paginate 의 startsAt). 표(행이 쪽마다 조각으로 나뉨) · 쪽을 새로 시작하는 새 항목 · 쪽 경계에 걸친 묶음 ·
  // 쪽 머리 항목 앞에 새 줄이 끼는 경우(paginate 는 그 줄을 앞 쪽 끝에 둔다)는 여기서 하지 않는다. 견줌 = tools/smoke_edit_speed_ui.py(그 자리 결과 = paginate() 결과).
  // old 가 비면 넣기만 — after(그대로인 앞 항목)의 마지막 요소 뒤에(표면 그 표의 마지막 쪽 조각 뒤). items 가 비면 지우기만(빈 줄 Backspace).
  if ((!old.length && !(after && items.length)) || [...old, ...items].some((it) => it.kind !== "node")) return false;
  const first = old.length ? old[0].el : after.kind === "table" ? [...$("doc").querySelectorAll(`.sheet-body > table.tbl[data-tbl="${after.id}"]`)].pop() : after.el;
  const body = first && first.parentElement;
  if (!first || !first.isConnected || !body || !body.classList.contains("sheet-body")) return false;
  // 넘침 나눔(overflowSplit)으로 조각난 쪽이면 조각(「≈n쪽 +k」)을 도로 합쳐 둔다 — flowSettle 의 overflowSplit 이 그 쪽을 다시 나눈다(조각에 줄을 보태기만 하면 조각이 잘게 쪼개진다).
  // 표를 행에서 잘라 넘긴 조각은 여기서 못 합친다(rowHeal 몫).
  const group = [...$("doc").querySelectorAll(`.sheet[data-page="${body.parentElement.dataset.page}"]`)];
  if (old.some((it) => !it.el.isConnected || !group.includes(it.el.parentElement.parentElement))) return false;
  if (group.length > 1) {
    const bodies = group.map((s) => s.querySelector(".sheet-body"));
    if (bodies.slice(1).some((b) => { const c = b.firstElementChild; return c && c.tagName === "TABLE" && c.classList.contains("cont"); })) return false;
    for (const b of bodies.slice(1)) { bodies[0].append(...b.children); b.parentElement.remove(); }
  }
  for (let k = 1; k < old.length; k++) if (old[k].el.previousElementSibling !== old[k - 1].el) return false;
  if (!state.mapping && items.slice(old.length ? 1 : 0).some((it) => it.pageStart)) return false; // 매핑이 없을 때만 줄 배치의 쪽 시작을 쓴다(paginate startsAt)
  if (!old.length) { first.after(...items.map((it) => it.el)); return true; }
  if (items.length && !first.previousElementSibling && !items[0].ids.some((id) => old[0].ids.includes(id))) return false;
  first.before(...items.map((it) => it.el));
  for (const it of old) it.el.remove();
  return true;
}

function flowSettle() {
  // 그 자리에서 바꿔 끼운 뒤 — paginate() 의 뒷부분만(웹 글꼴이 늦게 왔을 때 다시 미는 것과 같은 길): 넘친 쪽 밀기·나누기 · 자리 모르는 문단 표시 · 맞춤 · 문서 표시
  const doc = $("doc");
  if (state.mapping) overflowPush(doc);
  overflowSplit(doc);
  markUnmapped();
  refit();
  if (typeof tplMarksDraw === "function" && heads.marks) tplMarksDraw();
  if (typeof tblMarksDraw === "function") tblMarksDraw();
  if (typeof divMarksDraw === "function") divMarksDraw();
  if (typeof fmtFocusDraw === "function") fmtFocusDraw();
  if (typeof ddDraw === "function") ddDraw();
}

function focusAt(f) {
  const p = paraEl(f.id);
  if (!p) return;
  p.focus({ preventScroll: true });
  setCaret(p, f.offset || 0, f.end != null ? f.end : f.offset || 0);
  p.scrollIntoView({ block: "nearest" });
  trackCaret();
}

async function reloadDoc() {
  // 문서 전체를 다시 읽어 그린다(실행 취소 뒤, 바꿀 자리를 못 찾았을 때) — 검증·매핑·수정 번호는 그대로
  const id = state.id, epoch = state.epoch;
  const d = await api(`/api/docs/${id}`);
  if (id !== state.id || epoch !== state.epoch) return; // 읽는 사이 다른 문서를 열었다 — 옛 문서로 새 화면을 덮지 않는다(2026-11-13 astra P1)
  applyDoc(d);
}

function applyDoc(d) {
  if (docNameSync(d.name)) loadWorks(); // 프로젝트 구성을 반영하면 프레임 이름으로, 그 반영을 실행 취소하면 올린 이름으로(spec_작업 ② §10 「프레임 이름」) — 문서 목록·작업 목록의 이름도 다시
  state.blocks = d.blocks;
  if (d.webFonts) setDocFonts(d.webFonts);
  state.byId = new Map();
  walkParas(d.blocks, (b) => { state.texts[b.id] = b.text || ""; state.byId.set(b.id, b); if (!(b.id in state.original)) state.original[b.id] = ""; });
  applyEditState(d);
  renderDoc(d.blocks);
  updateEdits();
  renderSummary(state.verify || {});
  refreshToolbar();
}

async function splitHere(p) {
  let o = selOffsets(p);
  if (!o) return;
  if (o.start !== o.end) { document.execCommand("delete"); o = selOffsets(p); } // 고른 글을 지우고 그 자리에서 나눈다
  await structOp("split", { id: p.dataset.id, offset: o.start });
}

function formatChars(changes) {
  const c = state.cur;
  if (!c || !paraEl(c.id)) { toast("글자 모양을 바꿀 문단(글자)을 먼저 고르세요"); return; }
  return structOp("format/chars", { id: c.id, start: c.start, end: c.end, changes });
}

function formatPara(changes) {
  const c = state.cur;
  if (!c || !paraEl(c.id)) { toast("문단 모양을 바꿀 문단을 먼저 누르세요"); return; }
  return structOp("format/para", { ids: [c.id], changes, offset: c.start });
}

async function undoStruct() {
  if (!state.undo || state.busy) return;
  const epoch = state.epoch, id = state.id; // 문서는 기다리기 전에 잡는다(structOp 와 같은 까닭 — 글 반영을 기다리는 사이 다른 문서를 열면 그 문서의 편집을 되돌리게 된다: 2026-11-16 astra)
  await flushAll();
  if (epoch !== state.epoch) return;
  if (state.localRev > state.structRev && !confirm("실행 취소하면 마지막 구조·서식 편집 뒤에 고친 글도 함께 되돌아갑니다. 계속할까요?")) return;
  state.busy = true;
  refreshToolbar();
  try {
    const d = await api(`/api/docs/${id}/undo`, { method: "POST" });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    state.structRev = state.localRev;
    applyDoc(d);
    outlineLoad(true); // 서버는 개요 오버레이(줄·레벨 자리 규칙)도 그 편집 앞으로 되돌렸다 — 화면 것도 다시 읽는다(spec_hwpx_웹편집 ② §8-1)
    toast(d.pristine ? `실행 취소 —${state.base ? `확정 ${state.base}` : "원본"}과 바이트가 같은 상태로 돌아왔습니다` : "실행 취소했습니다");
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); }
  finally { if (epoch === state.epoch) { state.busy = false; refreshToolbar(); refreshSaveState(); } } // 그 사이 연 다른 문서의 「바쁨」 을 건드리지 않는다
}

function bindToolbar() {
  const bar = $("docBar"); // 2026-11-10 부터 한 줄 도구 줄 전체(묶음 단추·확대 포함) — 「폰트 수정」을 누르고 「굵게」를 눌러도 선택 범위가 남아야 한다
  bar.addEventListener("mousedown", (e) => { if (e.target.closest("button")) e.preventDefault(); }); // 단추를 눌러도 문서의 선택 범위를 지킨다
  for (const b of bar.querySelectorAll("[data-char]")) b.onclick = () => formatChars({ [b.dataset.char]: "toggle" });
  for (const b of bar.querySelectorAll("[data-align]")) b.onclick = () => formatPara({ align: b.dataset.align });
  for (const b of bar.querySelectorAll("[data-indent]")) b.onclick = () => {
    const f = (state.cur && (state.byId.get(state.cur.id) || {}).format) || {};
    formatPara({ indentLeftMm: Math.max(0, Math.round((f.indentLeftMm || 0) + Number(b.dataset.indent))) });
  };
  $("tbSize").onchange = (e) => { const v = parseFloat(e.target.value); if (v >= 1) formatChars({ sizePt: v }); };
  $("tbColor").onchange = (e) => formatChars({ color: e.target.value.toUpperCase() });
  $("tbFirst").onchange = (e) => { if (e.target.value !== "") formatPara({ firstLineMm: Number(e.target.value) }); };
  $("tbLine").onchange = (e) => { if (e.target.value) formatPara({ lineSpacingPct: Number(e.target.value) }); };
  $("undoBtn").onclick = undoStruct;
  // 「테이블 수정」 묶음의 딸림 단추(2026-11-10 사용자 「표 만들기 서식 변환은 테이블 바에 … 표 구조 보기 옵션도」) — 표 모듈은 app.js 뒤에 읽히므로 누를 때 찾는다
  $("tbTableMake").onclick = () => { if (typeof tmkOpen === "function") tmkOpen(); }; // 2열 「표 만들기 · 서식 변환」(table_make.js) — 글을 골라 두었으면 그 문단들이 원본(위 mousedown 이 선택 범위를 지킨다)
  $("tbTblRoles").onclick = () => tbRolesClick();
}

async function tbRolesClick() { // 도구 줄 「표 구조 보기」 — 문서 표 칸에 칸 역할 색(tables.js tblRolesToggle, spec_헤딩_추출 ② §10). 눌림·꺼짐·도움말은 tblRolesBtnSync 가 맞춘다
  if (typeof tblRolesToggle !== "function" || !state.id || state.format === "docx") return;
  if (!heads.view) { // 다시 연 작업은 헤딩 요약을 아직 안 읽었다 — 먼저 읽는다(「표」 탭을 열 때와 같음: tablesShow)
    const epoch = state.epoch;
    await headsShow();
    if (epoch !== state.epoch) return;
    if (!heads.view) { toast("표 구조(3단계) 결과를 읽지 못했습니다 — 잠시 뒤 다시 누르세요", true); return; }
    if (!heads.view.stage3) { toast("표 구조(3단계)가 아직 없습니다 — 「테이블」 탭의 「표 구조 만들기」 로 먼저 만드세요"); return; }
    if (tblRolesOn()) return; // 켜 둔 채 다시 연 작업 — 읽자마자 칠해졌다(headsRender → tblMarksDraw → tblRolesApply)
  }
  tblRolesToggle();
}

// ---------------------------------------------------------------- 공용 오른쪽 단추 메뉴 (표 칸 메뉴 table_edit.js tselContextMenu · 문단 메뉴 divContextMenu 가 항목을 준다)
// 메뉴 상자는 하나(ctx.menu) — 2026-11-10 표 구조 편집을 table_edit.js 로 옮기며 표 선택 상태(tsel)에서 떼어 냄(astra P2 「공용 메뉴는 공통 UI 가 소유」).
const ctx = { menu: null };

function ctxMenu() {
  if (ctx.menu) return ctx.menu;
  const m = el("div", "ctx-menu");
  m.setAttribute("role", "menu");
  m.hidden = true;
  m.addEventListener("keydown", (e) => {
    const items = [...m.querySelectorAll("button:not([disabled])")];
    const i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); ctxClose(); }
  });
  document.body.append(m);
  ctx.menu = m; // 하나만 두고 닫는다 — 빠져 있어 열 때마다 새 메뉴가 쌓이고 ctxClose 가 아무것도 못 닫던 것(2026-11-10, 구분 기준 자리 메뉴 붙이며 발견)
  return m;
}

function ctxClose() { if (ctx.menu && !ctx.menu.hidden) { ctx.menu.hidden = true; ctx.menu.textContent = ""; } }

function ctxOpen(e, items) {
  const m = ctxMenu();
  m.textContent = "";
  for (const it of items) {
    if (!it) { m.append(el("hr")); continue; }
    const [label, key, run, disabled] = it;
    const b = el("button", null, label);
    b.type = "button";
    b.setAttribute("role", "menuitem");
    if (key) b.append(el("kbd", null, key));
    if (disabled) b.disabled = true;
    b.onclick = () => { ctxClose(); run(); };
    m.append(b);
  }
  m.hidden = false;
  m.style.left = `${Math.min(e.clientX, innerWidth - m.offsetWidth - 8)}px`;
  m.style.top = `${Math.min(e.clientY, innerHeight - m.offsetHeight - 8)}px`;
  const first = m.querySelector("button:not([disabled])");
  if (first) first.focus({ preventScroll: true });
}

function bindCtxMenu() { // 바깥 누름·스크롤·창 크기·포커스 잃음 → 닫기
  document.addEventListener("mousedown", (e) => { if (ctx.menu && !ctx.menu.hidden && !ctx.menu.contains(e.target)) ctxClose(); }, true);
  $("scroller").addEventListener("scroll", () => { if (!zoomQuiet()) ctxClose(); }, { passive: true }); // 배율을 뒤에서 바꾸며 자리를 지킨 scroll(보이는 것은 안 움직임)로는 안 닫는다
  window.addEventListener("resize", ctxClose);
  window.addEventListener("blur", ctxClose);
}

// ---------------------------------------------------------------- 고친 문단 목록
function updateEdits() {
  const n = state.edited.size;
  const badge = $("editsBadge");
  badge.textContent = n + state.failed.size;
  badge.classList.toggle("on", n > 0);
  badge.classList.toggle("err", state.failed.size > 0);
  $("editNav").hidden = !n; // 도구 줄에는 ↑↓ 만 — 수는 도구 탭 「고친 문단」 배지(위 #editsBadge)에 있다(2026-11-10 사용자), 여기선 도움말로만
  $("prevEdit").title = `이전 고친 문단으로 (고친 문단 ${n}개)`;
  $("nextEdit").title = `다음 고친 문단으로 (고친 문단 ${n}개)`;
  $("verifyBtn").disabled = !canVerify();
  state.editsDirty = true;
  if (!$("paneEdits").hidden) drawEdits();
  refreshSaveState();
  commitBar(); // 확정 줄(기준·고친 수·단추) — spec_작업 ② §8
  if (typeof ddSync === "function") ddSync(); // 문서의 「고친 곳 보기」(doc_diff.js — 넣은 글·지운 자리·꼬리표: ② §8 「문서에서 — 고친 곳 보기」)
}

function drawEdits() {
  state.editsDirty = false;
  const list = $("editsList");
  list.textContent = "";
  for (const id of state.failed) {
    const li = el("li", "edit-item failed");
    li.append(el("div", "fail-label", "서버에 반영하지 못함"));
    li.append(el("div", "new", short(readText(paraEl(id) || el("div")), 200)));
    const row = el("div", "row");
    row.append(el("span", "spacer"));
    const again = el("button", "btn sm", "다시 반영");
    again.type = "button";
    again.onclick = () => { const p = paraEl(id); if (p) save(p); };
    row.append(again);
    li.append(row);
    list.append(li);
  }
  const ids = orderedEdits();
  const goneIds = Object.keys(state.kinds).filter((i) => state.kinds[i] === "removed");
  const gone = goneIds.length;
  if (!ids.length && !state.failed.size && !gone) {
    list.append(el("li", "none", state.base
      ? `확정 ${state.base} 뒤로 고친 문단이 없습니다. 문서에서 글을 고치면 여기에 다시 모입니다(확정본과 견줌 — 지난 변경은 위 「확정 기록」).`
      : "아직 고친 문단이 없습니다. 문서에서 글을 누르고 고치면 여기에 모입니다. 원래 글로 되돌리면 원본 XML(줄 배치 포함)까지 되돌려 목록에서 빠집니다."));
  }
  const det = EDET.epoch === state.epoch ? EDET.data : null; // 지난 차례의 값도 새로 읽을 때까지는 보인다(글을 칠 때마다 「견주는 중」 으로 깜박이지 않게)
  if (ids.some((id) => EDET_KINDS.has(state.kinds[id])) && !edetFresh()) edetNeed(); // 모양 값은 서버가 견준다 — 읽으면 다시 그린다
  const KINDS = { text: "글", format: "모양", struct: "나누기·합치기", new: "새 문단" };
  for (const id of ids) {
    const kind = state.kinds[id] || "text", g = kind === "new" ? "A" : "M";
    const li = el("li", `edit-item g-${g}`);
    li.dataset.id = id; // 문서의 꼬리표를 누르면 이 항목으로 온다(doc_diff.js ddGo)
    const go = el("button", "edit-go");
    go.type = "button";
    go.setAttribute("aria-label", `고친 문단으로 이동: ${short(state.texts[id], 40)}`);
    go.append(gitView(kind, state.original[id] || "", state.texts[id] || ""));
    go.onclick = () => scrollToBlock(id, true);
    li.append(go);
    const fm = EDET_KINDS.has(kind) ? gitFmt(det, id, kind) : null;
    if (fm) li.append(fm);
    const row = el("div", "row");
    const pg = pagesOf(id);
    const gk = el("span", `gk gk-${g}`, g);
    gk.title = GIT_LETTER[g];
    row.append(gk, el("span", "kind", KINDS[kind] || kind));
    row.append(el("span", null, pg ? pg.label : ""));
    if (state.unrestored.has(id)) row.append(el("span", "warn-text", `글은 원래대로 · 줄 배치는 ${APP()}가 다시 계산`));
    row.append(el("span", "spacer"));
    if (kind === "text" || kind === "format") {
      const rv = el("button", "btn sm", state.base ? "확정본으로 되돌리기" : "원본으로 되돌리기"); // 기준 = 마지막 확정(spec_작업 ② §8)
      rv.type = "button";
      rv.onclick = () => revert(id);
      row.append(rv);
    } else {
      row.append(el("span", "muted", "실행 취소로 되돌림"));
    }
    li.append(row);
    list.append(li);
  }
  if (gone) list.append(gitGone(goneIds));
}

// ---- 깃 diff 처럼(spec_작업 ② §8 「화면」 — 2026-11-16 사용자 「고친문단은 깃처럼 표기해줘야지」·「어떻게 변경되었는지. 정보는 주길 바람」)
// 항목마다 깃 상태 글자(M 고침 · A 새 문단 · D 지움 — 항목 왼쪽 띠도 그 색: M = 문서의 주황 띠) + − 원본 줄(빨강) · + 지금 줄(초록) — 글은 지운 글·넣은 글을 진하게(앞뒤 같은 글 40자까지),
// 모양(format · struct)은 「항목 · 원본 값 · 지금 값」 표(값마다 이름 — 열 머리가 어느 쪽인지). 모양 값은 서버가 기준 블록과 지금 블록을 견줘 준다(GET …/edits/detail —
// 편집 차례·기준이 바뀌면 0.5초 모아 다시 읽고 다시 그림). 「원본」 = 기준(확정했으면 「확정 n」).
const GIT_LETTER = { M: "M — 고친 문단(깃의 modified)", A: "A — 새 문단(깃의 added)", D: "D — 지운 문단(깃의 deleted)" };
const EDET_KINDS = new Set(["format", "struct"]); // 모양 값을 서버에 묻는 종류(server.DETAIL_KINDS) — 글만 고친 문단은 원래 글로 그린다
const EDET = { data: null, epoch: null, rev: null, base: null, timer: null, busy: false }; // rev·base = 물을 때 화면의 편집 차례·기준(응답의 rev 로 견주면 화면이 모르는 차례가 있을 때 끝없이 다시 묻는다)
const baseWho = () => (state.base ? `확정 ${state.base}` : "원본");

function edetFresh() {
  return !!EDET.data && EDET.epoch === state.epoch && EDET.rev === state.serverRev && EDET.base === (state.base || 0);
}

function edetNeed() { // 모양 값 읽기 — 0.5초 모아서 한 번(편집이 잇달아도), 읽으면 목록을 다시 그린다
  if (EDET.timer || EDET.busy || !state.id) return;
  EDET.timer = setTimeout(async () => {
    EDET.timer = null;
    const id = state.id, epoch = state.epoch, rev = state.serverRev, base = state.base || 0;
    let data;
    EDET.busy = true;
    try {
      data = await api(`/api/docs/${id}/edits/detail`);
    } catch (e) {
      data = { items: {}, more: 0, error: e.message }; // 같은 차례에 되풀이해 묻지 않는다 — 다음 편집 때 다시
    } finally {
      EDET.busy = false;
    }
    if (epoch !== state.epoch) return;
    Object.assign(EDET, { data, epoch, rev, base });
    if (!$("paneEdits").hidden) drawEdits();
  }, 500);
}

function diffParts(a, b) { // 앞뒤 같은 부분을 빼고 바뀐 곳 — { pre, del, ins, post }
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  let j = 0;
  while (j < a.length - i && j < b.length - i && a[a.length - 1 - j] === b[b.length - 1 - j]) j++;
  return { pre: a.slice(0, i), del: a.slice(i, a.length - j), ins: b.slice(i, b.length - j), post: a.slice(a.length - j) };
}
const diffMark = (s) => s.replaceAll(LS, "↵\n").replaceAll("\t", "⇥\t"); // 줄 바꿈 ↵, 탭 ⇥ 표시

function diffView(a, b) { // 한 줄 안에 <del>/<ins>(기록 탭 · 확정 기록의 변경 목록)
  const { pre, del, ins, post } = diffParts(a, b);
  const box = el("div", "diff");
  const CTX = 40;
  box.append(el("span", "ctx", (pre.length > CTX ? "…" : "") + diffMark(pre.slice(-CTX))));
  if (del) box.append(el("del", null, diffMark(del)));
  if (ins) box.append(el("ins", null, diffMark(ins)));
  box.append(el("span", "ctx", diffMark(post.slice(0, CTX)) + (post.length > CTX ? "…" : "")));
  return box;
}

function gdLine(sign, cls, who, parts) { // 깃 diff 한 줄 — 부호(−·+·빈칸) · 이름표(원본·지금) · 내용
  const ln = el("div", `gd-line ${cls}`);
  const s = el("span", "gd-sign", sign);
  s.setAttribute("aria-hidden", "true");
  ln.append(s, el("span", "gd-who", who || ""));
  const body = el("span", "gd-body");
  body.append(...parts);
  ln.append(body);
  return ln;
}

function gitView(kind, a, b) { // 글의 다름 — 같으면 맥락 한 줄, 다르면 − 원본(지운 글 진하게) · + 지금(넣은 글 진하게), 새 문단은 + 한 줄
  const box = el("div", "gd");
  if (kind === "new") { box.append(gdLine("+", "ins", "새 문단", [short(b, 200)])); return box; } // short — 빈 글은 「(빈 문단)」
  if (a === b) { box.append(gdLine("", "ctx", "글 같음", [short(a, 120)])); return box; }
  const { pre, del, ins, post } = diffParts(a, b), CTX = 40;
  const head = () => (pre.length > CTX ? "…" : "") + diffMark(pre.slice(-CTX));
  const tail = () => diffMark(post.slice(0, CTX)) + (post.length > CTX ? "…" : "");
  box.append(gdLine("−", "del", baseWho(), a ? [head(), del ? el("del", null, diffMark(del)) : "", tail()] : [el("span", "muted", "(빈 문단)")]));
  box.append(gdLine("+", "ins", "지금", b ? [head(), ins ? el("ins", null, diffMark(ins)) : "", tail()] : [el("span", "muted", "(빈 문단)")]));
  return box;
}

function gitFmt(det, id, kind) { // 모양의 다름 — 「항목 · 원본 값 · 지금 값」 표(서버 edits/detail), 읽는 중·못 읽음·견줄 값 없음은 한 줄 · 나누기·합치기는 모양이 같으면 null
  const fmt = kind === "format";
  if (!det) return fmt ? el("div", "gd-note", "모양 값 견주는 중…") : null;
  if (det.error) return el("div", "gd-note warn-text", `모양 값을 읽지 못함 — ${det.error}`);
  const ch = det.items[id];
  if (ch === undefined) return fmt ? el("div", "gd-note", det.more ? "모양 값은 문서 앞쪽 고친 문단까지만 견줍니다" : "모양 값 견주는 중…") : null;
  if (ch === null) return fmt ? el("div", "gd-note", "원본에 같은 문단이 없어 모양을 견주지 않음") : null;
  if (!ch.length) return fmt ? el("div", "gd-note", "견주는 모양 값(글자·문단)은 같음 — 그 밖의 모양 속성이 바뀜") : null;
  const t = el("table", "gd-fmt");
  const hr = el("tr");
  hr.append(el("th", null, "모양"), el("th", "del", `− ${baseWho()}`), el("th", "ins", "+ 지금"));
  t.append(hr);
  for (const c of ch) {
    const tr = el("tr");
    const k = el("td", "k", c.label);
    if (c.part) { k.append(el("span", "gd-part", "일부 글자")); k.title = "문단 안에서 글자마다 값이 다릅니다 — 값을 문단 차례대로 「·」 로 이음"; }
    else if (c.hint) k.title = c.hint; // 줄의 자리 값(앞 여백 · 2번째 줄)의 뜻 — 문단 모양에서 센 자리이지 빈칸을 잰 폭이 아니다(edit_detail.HINTS)
    tr.append(k, el("td", "del", c.before), el("td", "ins", c.after));
    t.append(tr);
  }
  return t;
}

function gitGone(ids) { // 지운 문단(D) — 문서에 자리가 없어 이동은 없고 원본 글만(앞 200개), 되돌리기는 실행 취소
  const li = el("li", "edit-item g-D");
  const d = el("details", "gd-gone");
  const sm = el("summary");
  const gk = el("span", "gk gk-D", "D");
  gk.title = GIT_LETTER.D;
  sm.append(gk, ` 지운 문단 ${nf(ids.length)}개 `, el("span", "muted", "(문단 합치기·표 행/열 지우기 — 되돌리려면 위 막대의 「실행 취소」)"));
  d.append(sm);
  const box = el("div", "gd");
  for (const id of ids.slice(0, 200)) box.append(gdLine("−", "del", baseWho(), [short(state.original[id] || "", 160)]));
  if (ids.length > 200) box.append(el("div", "gd-note", `… 그 밖에 ${nf(ids.length - 200)}개`));
  d.append(box);
  li.append(d);
  return li;
}

function orderedEdits() {
  return [...document.querySelectorAll(".para.edited")].map((p) => p.dataset.id).filter((id) => state.edited.has(id));
}

async function revert(id) {
  const p = paraEl(id);
  if (!p) return;
  const epoch = state.epoch, was = state.kinds[id];
  clearTimeout(state.timers.get(id));
  state.timers.delete(id);
  await (state.chains.get(id) || Promise.resolve());
  try {
    const r = await api(`/api/docs/${state.id}/blocks/${id}/revert`, { method: "POST" });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    applyServer(id, r);
    state.kinds = r.kinds || state.kinds;
    const known = state.byIdOrig.has(id); // 기준 블록을 아는 문단 — 다시 연 작업에서 이미 고쳐져 있던 문단은 모른다(load)
    if (r.restored && !known && was === "format") { // 모양까지 되돌렸는데 기준 블록이 없음 — 문서를 다시 읽어 그린다(드묾)
      await reloadDoc();
      toast(`${state.base ? "확정본" : "원본"} 문단(글·모양·줄 배치)으로 되돌렸습니다`);
      return;
    }
    if (r.restored && known) state.byId.set(id, state.byIdOrig.get(id)); // 모양까지 기준 — 기준 블록으로 다시 그린다
    const b = state.byId.get(id);
    const again = r.restored && known ? renderPara(b) : renderPara(b, r.text);
    again.classList.toggle("edited", r.edited);
    p.replaceChildren(...again.childNodes); // 같은 요소를 둔다 — 쪽 상자 흐름(state.flow)이 이 노드를 가리킨다
    p.className = again.className;
    if (r.restored && known) indentLook(p.style, b.format || {}); // 모양까지 기준으로 — 문단 요소의 왼쪽 여백·첫 줄도(개요 줄 자리 규칙·문단 수정으로 바뀐 것이 화면에 남지 않게)
    updateEdits();
    markUnmapped();
    renderSummary(state.verify || {});
    toast(r.restored ? `${state.base ? "확정본" : "원본"} 문단(글·줄 배치)으로 되돌렸습니다` : `글은 되돌렸으나 ${state.base ? "확정본" : "원본"} XML 로는 못 되돌렸습니다 — 줄 배치는 ${APP()}가 다시 계산합니다`, !r.restored);
  } catch (e) { toast(e.message, true); }
}

function scrollToBlock(id, focus = false) {
  const p = paraEl(id);
  if (!p) return;
  p.scrollIntoView({ block: "center", behavior: scrollHow() });
  p.classList.remove("flash");
  void p.offsetWidth;
  p.classList.add("flash");
  if (focus) p.focus({ preventScroll: true });
  select(id);
}

function stepEdit(dir) {
  const ids = orderedEdits();
  if (!ids.length) return;
  const sc = $("scroller").getBoundingClientRect();
  const mid = sc.top + sc.height / 2;
  const tops = ids.map((id) => paraEl(id).getBoundingClientRect().top);
  let k = dir > 0 ? tops.findIndex((t) => t > mid + 4) : tops.map((t) => t < mid - 4).lastIndexOf(true);
  if (k < 0) k = dir > 0 ? 0 : ids.length - 1;
  scrollToBlock(ids[k], true);
}

// ---------------------------------------------------------------- 확정 (spec_작업 ② §8 — 고친 문단을 깃처럼)
// 「고친 문단」 탭 맨 위(#commitBox, 모양 commits.css): 기준·고친 수 한 줄 + [메시지][확정][모두 되돌리기] + 접힌 확정 기록.
// 기준 = 마지막 확정(state.base, 0 = 올린 원본) — 확정하면 지금 상태가 새 기준이 되어 고친 문단이 0 부터 다시 모인다.
// 깃에 견주면: 고친 문단 = 작업 트리 변경 · 확정 = commit · 확정 기록 = log · 모두 되돌리기 = 변경 모두 버림(코드 이름 discard) ·「이 확정으로 복원」 = 그 시점으로 되돌리는 새 확정.
const KIND_KO = { text: "글", format: "모양", struct: "나누기·합치기", new: "새 문단", removed: "지움" };
const baseName = (n = state.base) => (n ? `확정 ${n}` : "올린 원본");
const kindCounts = (c) => Object.keys(KIND_KO).filter((k) => c && c[k]).map((k) => `${KIND_KO[k]} ${nf(c[k])}`).join(" · ");
const isDirty = () => state.edited.size > 0 || !state.pristine; // 확정하지 않은 변경이 있는지(글은 같아도 파일이 기준과 다르면 변경)

function commitBar() { // 기준·고친 수 한 줄과 단추 상태 — updateEdits() 가 부른다(싸다)
  commitQuickSync(); // 헤딩 추출 탭 · 「테이블」 탭 · 표 서식 점검 열의 「고친 부분 적용하기」 줄도 같은 때(② §8 「고친 부분 적용하기」)
  const box = $("commitBox");
  if (!box) return;
  box.hidden = !state.id || !state.stored; // 작업 저장이 꺼져 있으면 확정 기능 없음
  if (box.hidden) return;
  if (!box.dataset.bound) { // 단추 연결은 처음 한 번
    box.dataset.bound = "1";
    $("commitBtn").onclick = commitDo;
    $("discardBtn").onclick = () => commitRestore(state.base);
    $("resetWorkBtn").onclick = () => workResetAsk(); // 작업 내용 초기화(same_file.js — spec_작업 ② §3-1)
    $("commitMsg").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); commitDo(); } });
  }
  const n = state.edited.size, c = {}, dirty = isDirty();
  for (const k of Object.values(state.kinds)) c[k] = (c[k] || 0) + 1;
  const sum = $("commitSum");
  sum.textContent = "";
  sum.append("기준 ", el("b", null, baseName()), " · ");
  if (n) sum.append(el("span", "n", `고친 문단 ${nf(n)}`), ` (${kindCounts(c)})`);
  else sum.append(dirty ? `글은 같으나 파일이 기준과 다름(줄 배치를 ${APP()}가 다시 계산할 문단)` : "고친 것 없음");
  $("commitBtn").disabled = $("discardBtn").disabled = $("commitMsg").disabled = !dirty || !!state.commitBusy;
  $("resetWorkBtn").disabled = !!state.commitBusy; // 초기화는 고친 것이 없어도 된다(분석 · LLM 결과 · 대화도 비운다)
  $("resetWorkBtn").textContent = state.commitBusy === "reset" ? "초기화 중…" : "초기화…";
  $("commitBtn").textContent = state.commitBusy === "commit" ? "확정 중…" : "확정";
  $("discardBtn").textContent = state.commitBusy === "discard" ? "되돌리는 중…" : "모두 되돌리기";
  const ob = document.querySelector('#pdfSeg [data-which="original"]'); // PDF 탭 왼쪽 단추 = 기준 PDF
  if (ob) ob.textContent = state.base ? `확정 ${state.base}` : "원본";
}

async function commitsLoad() { // 확정 기록 읽기 — 문서를 열 때 · 확정/버리기/복원 뒤
  if (!state.id || !state.stored) return;
  const id = state.id, epoch = state.epoch;
  let r = null;
  try { r = await api(`/api/docs/${id}/commits`); } catch { /* 못 읽음 — 목록에 알림만 */ }
  if (epoch !== state.epoch) return;
  state.commits = r ? r.commits : null;
  commitLogDraw();
}

function commitLogDraw() {
  const list = $("commitList"), cs = state.commits;
  const open = new Set([...list.querySelectorAll("details[open]")].map((d) => d.dataset.n)); // 펼친 확정은 다시 그려도 펼친 채
  list.textContent = "";
  $("commitCount").textContent = cs ? Math.max(0, cs.length - 1) : "–"; // 올린 원본(확정 0)은 빼고 센다
  if (!cs) { list.append(el("li", "none", "확정 기록을 읽지 못했습니다 — 탭을 다시 열어 주세요.")); return; }
  for (const c of cs) {
    const li = el("li"), d = el("details", "commit-item"), s = el("summary"), body = el("div", "commit-body");
    d.dataset.n = c.n;
    s.append(el("span", "c-n", `#${c.n}`), el("span", "c-msg" + (c.message ? "" : " dim"), c.message || "(메시지 없음)"));
    if (c.n === state.base) s.append(el("span", "c-base", "기준"));
    s.append(el("span", "c-meta", [c.counts && c.counts.total ? `${nf(c.counts.total)}문단` : "", fmtWhen(c.at)].filter(Boolean).join(" · ")));
    s.title = `${baseName(c.n)}${c.message && c.n ? ` 「${c.message}」` : ""}${c.counts ? ` · ${kindCounts(c.counts)}` : ""} — 눌러서 파일 받기·복원·변경 목록`;
    d.append(s, body);
    d.addEventListener("toggle", () => { if (d.open && !body.childElementCount) commitBodyDraw(c, body); });
    if (open.has(String(c.n))) d.open = true;
    li.append(d);
    list.append(li);
  }
}

async function commitBodyDraw(c, body) { // 확정 하나를 펼침 — [파일 받기][이 확정으로 복원] + 변경 목록(앞 200개)
  const id = state.id, epoch = state.epoch;
  const acts = el("div", "commit-acts"), file = el("a", "btn sm", "파일 받기"), rs = el("button", "btn sm", c.n === state.base ? "지금 기준" : "이 확정으로 복원");
  file.href = `/api/works/${id}/commits/${c.n}/file`;
  file.setAttribute("download", "");
  file.title = `${baseName(c.n)} 의 ${EXT()} 파일`;
  rs.type = "button";
  rs.disabled = c.n === state.base;
  rs.title = c.n === state.base ? "지금 고친 문단을 견주는 기준입니다 — 이 상태로 돌아가려면 위 「모두 되돌리기」" : `문서를 ${baseName(c.n)} 상태로 되돌리고 새 확정으로 남깁니다(지금 기준으로도 다시 돌아올 수 있음)`;
  rs.onclick = () => commitRestore(c.n);
  acts.append(file, rs, el("span", "c-sha", `${fmtSize(c.size || 0)} · ${(c.sha256 || "").slice(0, 12)}…`));
  body.append(acts);
  const ul = el("ul", "commit-changes");
  body.append(ul);
  if (!c.n) { ul.append(el("li", "note", "이 작업에 처음 올린 파일입니다.")); return; }
  if (c.restoreOf != null) { ul.append(el("li", "note", `${baseName(c.restoreOf)} 과 같은 파일입니다(그 상태로 되돌린 확정).`)); return; }
  ul.append(el("li", "note", "변경 목록 읽는 중…"));
  try {
    const r = await api(`/api/works/${id}/commits/${c.n}`);
    if (epoch !== state.epoch) return;
    ul.textContent = "";
    for (const x of r.changes) {
      const li = el("li");
      li.append(el("span", "kind", KIND_KO[x.kind] || x.kind), blockLink(x.id), diffView(x.before || "", x.after || ""));
      ul.append(li);
    }
    if (r.more) ul.append(el("li", "note", `… 그 밖에 ${nf(r.more)}개(앞 ${nf(r.changes.length)}개만 보임)`));
    if (!r.changes.length) ul.append(el("li", "note", "글이 바뀐 문단 없음(줄 배치 등 파일만 다름)."));
  } catch (e) {
    if (epoch !== state.epoch) return;
    ul.textContent = "";
    ul.append(el("li", "note", `변경 목록을 읽지 못했습니다: ${e.message}`));
  }
}

async function commitReady(what) { // 확정·버리기·복원 앞 — 대기 중 글 반영을 끝낸다. 못 하면 false
  if (!state.id || state.commitBusy) return false;
  if (state.busy) { toast("편집을 반영하는 중입니다 — 잠시 뒤 다시 눌러 주세요"); return false; }
  await flushAll();
  if (what === "commit" && state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 확정할 수 없습니다 — 아래 목록에서 다시 반영하세요", true); return false; }
  return true;
}

const JSON_POST = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

async function commitDo(msg, opt = {}) { // 확정 — 지금 상태가 새 기준. 문서는 그대로라 다시 그리지 않는다. msg = 메시지 칸이 비었을 때 쓸 글(「고친 부분 적용하기」 가 준다 — 단추의 onclick 으로 불리면 사건 객체라 안 쓴다) → 확정 {n, count} | null
  // opt.field = false — 「고친 문단」 탭의 메시지 칸을 쓰지도 비우지도 않는다(묶음째 실행의 끝 확정 commitAfterRun — 사람이 적던 글을 가져가지 않게: spec_워크플로우 ② §18-24) · opt.quiet = 알림을 내지 않는다(부르는 쪽이 끝 글에 적는다)
  const field = !opt || opt.field !== false, quiet = !!(opt && opt.quiet);
  if (!(await commitReady("commit"))) return null;
  if (!isDirty()) { if (!quiet) toast("확정할 변경이 없습니다"); return null; }
  const id = state.id, epoch = state.epoch, count = state.edited.size, base0 = state.base;
  state.commitBusy = "commit";
  commitBar();
  try {
    const d = await api(`/api/docs/${id}/commits`, JSON_POST({ message: (field ? $("commitMsg").value.trim() : "") || (typeof msg === "string" ? msg : "") }));
    if (epoch !== state.epoch) return null;
    if (field) $("commitMsg").value = "";
    state.commitBusy = false;
    adoptBase(d, false);
    if (!quiet) toast(`확정 ${d.commit.n} — 고친 문단 ${nf(count)}개를 확정했습니다. 이제 이 상태가 기준입니다`);
    return { n: d.commit.n, count, parent: base0 };
  } catch (e) {
    if (epoch === state.epoch) toast(e.message, true);
    return null;
  } finally {
    if (epoch === state.epoch) { state.commitBusy = false; commitBar(); commitsLoad(); loadWorks(); logTouched(); }
  }
}

// 고친 부분 적용하기(spec_작업 ② §8 「고친 부분 적용하기」 — 2026-11-18 사용자 "헤딩 추출 및 표 점검 할 때.. 고친 부분 적용하기 버튼 넣어줘" → 답 「고친 문단 확정」):
// 헤딩 추출(조정의 「모두 반영」 · 템플릿 관계에서 맞추기)과 표 점검(서식 맞추기 · 빈 필드 지우기)을 하면 고친 문단이 쌓이는데, 확정은 「고친 문단」 탭까지 가야 했다 — 그 일을 하는 화면에
// 같은 확정을 부르는 단추를 둔다(새 확정 길이 아니다 — commitDo 그대로: 지금 상태가 새 기준 · 가져오기 검증을 새 기준으로 다시 · 실행 취소 기록은 비고 「확정 기록」 의 복원으로 돌아감).
// 줄(.commit-quick[data-cq=<어디>])은 **고친 것이 있을 때만** 보인다: 「고친 문단 n(모양 n · 글 n)」 + 단추. 자리 = 헤딩 추출 탭(진행 줄 아래) · 「테이블」 탭 맨 위(index.html) · 표 서식 점검 열(table_style.js) ·
// 대시보드의 양식 표준화 「조정」 · 「템플릿 관계」 · 「표 점검」 단계(dashboard.js — commitQuick). 확정 메시지는 「<어디> — 고친 부분 적용」(「고친 문단」 탭의 메시지 칸에 적어 둔 글이 있으면 그 글).
const CQ_LABEL = "고친 부분 적용하기";
const cqTitle = (n) => `고친 문단 ${nf(n)}개를 확정합니다 — 지금 상태가 새 기준이 되고 고친 문단이 0 부터 다시 모입니다(「고친 문단」 탭의 「확정」 과 같음).\n쪽 나눔도 고친 문서로 다시 맞춥니다(가져오기 검증을 새 기준으로 다시 — 배경). 실행 취소 기록은 비워지고, 앞 상태로는 「고친 문단」 탭 「확정 기록」 의 「복원」 으로 돌아갑니다`;

function commitQuickEl(where) { // 줄 하나(빈 채로 — commitQuickSync 가 채우고 보인다). where = 확정 메시지에 적을 곳 이름
  const box = el("div", "commit-quick");
  box.dataset.cq = where;
  box.hidden = true;
  return box;
}

function commitQuickSync() {
  const boxes = document.querySelectorAll(".commit-quick");
  if (!boxes.length) return;
  const n = state.edited.size, dirty = !!state.id && !!state.stored && isDirty(), c = {};
  if (dirty) for (const k of Object.values(state.kinds)) c[k] = (c[k] || 0) + 1;
  for (const box of boxes) {
    box.hidden = !dirty;
    if (!dirty) continue;
    if (!box.firstChild) { // 처음 한 번 — 글 + 단추
      const b = el("button", "btn sm primary cq-btn", CQ_LABEL);
      b.type = "button";
      b.onclick = () => commitQuick(box.dataset.cq);
      box.setAttribute("role", "group");
      box.setAttribute("aria-label", CQ_LABEL);
      box.append(el("span", "cq-sum"), b);
    }
    const sum = box.querySelector(".cq-sum"), b = box.querySelector(".cq-btn");
    sum.textContent = "";
    if (n) sum.append(el("b", "n", `고친 문단 ${nf(n)}`), ` (${kindCounts(c)})`); else sum.append("글은 같으나 파일이 기준과 다름");
    b.disabled = !!state.commitBusy;
    b.textContent = state.commitBusy === "commit" ? "적용하는 중…" : CQ_LABEL;
    b.title = cqTitle(n);
  }
}

async function commitQuick(where) { // 「고친 부분 적용하기」 — 확정 한 번 → {ok, text}(대시보드의 끝 글 — 알림은 commitDo 가 낸다)
  if (!state.id || !state.stored) return { ok: false, text: "이 작업은 저장이 꺼져 있어 확정할 수 없습니다" };
  if (!isDirty()) return { ok: false, text: "고친 것이 없습니다" };
  const r = await commitDo(`${where || "문서"} — 고친 부분 적용`);
  return r ? { ok: true, text: `확정 ${r.n} — 고친 문단 ${nf(r.count)}개를 적용했습니다. 이제 이 상태가 기준입니다` } : { ok: false, text: "적용하지 못했습니다 — 알림 글을 확인하세요" };
}

// 묶음째 실행의 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」 — 2026-11-22 사용자 「대쉬보드에서 이어서 하기나 하넌에 진행하는 경우, 고친문단을 자동으로 확정해줘,」):
// 화면이 도는 붙박이 문서 하나(양식 표준화 · 양식 맞추기 — 서버 실행기가 맡지 않는 틀)의 「한 번에 진행」(divRunAll) · 대시보드 2단계 「한 번에 진행」(headsRunAll({commit: true})) · 「이어서 한 번에」(dashStdChain)가 끝에 한 번 부른다.
// 새 확정 길이 아니다 — 「고친 문단」 탭의 확정과 같은 함수(commitDo — 메시지 칸의 글은 쓰지도 비우지도 않는다). what = 확정 메시지(「1단계 「프로젝트 구성」 한 번에 진행」 …) · opt.quiet = 확정 알림을 내지 않음(부르는 쪽이 끝 글에 적는다).
// → 끝 글에 붙일 한 줄(「확정 n(고친 문단 n · 앞 상태 = 확정 k)」 · 「확정하지 않음 — 까닭 …」) | ""(고친 것이 없음 · 작업 저장이 꺼짐 — 서버의 끝 확정과 같은 말: workflow_exec._commit_tail)
async function commitAfterRun(what, opt = {}) {
  if (!state.id || !state.stored || !isDirty()) return "";
  const undo = "반영은 「실행 취소」 로 되돌릴 수 있습니다 — 「고친 문단」 탭에서 확정";
  if (state.failed.size) return `확정하지 않음(서버에 반영하지 못한 문단이 있음) · ${undo}`;
  const r = await commitDo(what, { field: false, quiet: !!opt.quiet });
  return r ? `확정 ${r.n}(고친 문단 ${nf(r.count)} · 앞 상태 = ${baseName(r.parent)})` : `확정하지 않음(알림 글 참고) · ${undo}`;
}

async function commitRestore(n) { // n = 지금 기준이면 「모두 되돌리기」(확정이 안 생김), 아니면 그 확정 상태로 되돌려 새 확정으로 남김
  if (!(await commitReady("restore"))) return;
  const discard = n === state.base, dirty = isDirty() || state.failed.size > 0, count = state.edited.size + state.failed.size;
  if (discard && !dirty) { toast("되돌릴 변경이 없습니다"); return; }
  const ask = discard
    ? `확정하지 않은 변경(고친 문단 ${nf(count)}개)을 모두 ${baseName()} 상태로 되돌릴까요?\n되돌린 고침은 되살릴 수 없습니다.`
    : `문서를 ${baseName(n)} 상태로 되돌릴까요?\n새 확정으로 남으므로 지금 기준(${baseName()})으로도 다시 돌아올 수 있습니다.`
      + (dirty ? `\n\n확정하지 않은 변경(고친 문단 ${nf(count)}개)은 버립니다 — 남기려면 취소하고 먼저 「확정」하세요.` : "");
  if (!confirm(ask)) return;
  const id = state.id, epoch = state.epoch;
  state.commitBusy = discard ? "discard" : "restore";
  commitBar();
  setSaveState("busy", discard ? "모두 되돌리는 중…" :`${baseName(n)} 상태로 되돌리는 중…`);
  try {
    // 「모두 되돌리기」 는 이 화면이 아는 기준(base)을 함께 보낸다 — 워크플로우의 끝 확정(spec_워크플로우 ② §18-24)이 그 사이 기준을 옮겼으면 서버가 409 {base} 로 거절한다
    // (옛 기준 번호 그대로면 「그 확정으로 복원」 이 되어 실행 결과를 통째로 버린다: 2026-11-22 검토)
    const d = await api(`/api/docs/${id}/commits/${n}/restore`, JSON_POST(discard ? { discard: dirty, base: n } : { discard: dirty }));
    if (epoch !== state.epoch) return;
    state.commitBusy = false;
    adoptBase(d, true);
    toast(discard ? `모두 되돌렸습니다 — ${baseName()} 상태` : `${baseName(n)} 상태로 되돌려 ${baseName()} 로 남겼습니다`);
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (discard && e.status === 409 && e.body && typeof e.body.base === "number" && e.body.base !== n) { // 기준이 바뀜 — 되돌리지 않았다: 새 기준으로 맞추고 사람이 다시 누르게(확인 창의 수가 새 기준의 것이 되게)
      const ok = await commitBaseAdopt(id, epoch);
      toast(`되돌리지 않았습니다 — 기준이 ${e.body.base ? `확정 ${e.body.base} 로` : "올린 원본으로"} 바뀌었습니다(워크플로우가 고친 문단을 확정했을 수 있습니다). ${ok ? "화면을 새 기준으로 맞췄습니다 — 남은 변경이 있으면 다시 누르세요" : "문서를 다시 연 뒤 다시 누르세요"}`, true);
    } else toast(e.message, true);
  } finally {
    if (epoch === state.epoch) { state.commitBusy = false; commitBar(); refreshSaveState(); commitsLoad(); loadWorks(); logTouched(); }
  }
}

// 서버의 기준이 이 화면 몰래 바뀌었다(「모두 되돌리기」 의 409 {base} — 워크플로우의 끝 확정 · 다른 탭의 확정) — 문서를 한 번 읽어 새 기준으로(workflow_exec.js flowBaseSync 와 같은 검사:
// 읽는 사이 이 화면이 글을 보냈거나 차례가 바뀌었으면 그 읽은 문서는 옛것이라 쓰지 않는다) → 바꿨나
async function commitBaseAdopt(id, epoch) {
  const lr = state.localRev, sr = state.serverRev;
  try {
    const d = await api(`/api/docs/${id}`);
    if (epoch !== state.epoch || state.id !== id || state.localRev !== lr || state.serverRev !== sr || state.timers.size || state.inflight || state.busy) return false;
    if (d.rev != null && d.rev !== state.serverRev) applyDoc(d); // 차례도 바뀌었다(반영의 알림을 놓친 화면) — 먼저 다시 그린다
    adoptBase(d, false);
    return true;
  } catch (e) { console.warn(e); return false; }
}

function adoptBase(d, redraw) {
  // 기준이 바뀐 문서(확정·버리기·복원 응답 = GET /api/docs/{id} 꼴)를 화면 상태로. 확정은 문서가 그대로라 다시 그리지 않고(redraw false)
  // 블록 표·원래 글·고친 표시만 새 기준으로 바꾼다. 검증 결과·PDF 는 옛 기준의 것이라 내리고 서버가 다시 도는 가져오기 검증을 따라간다.
  const edited = new Set(d.edited || []);
  const same = (d.base || 0) === state.base; // 버리기 — 기준은 그대로라 기준 쪽 검증 결과·PDF·쪽 매핑도 그대로 쓴다(서버도 다시 돌리지 않음)
  state.base = d.base || 0;
  state.blocks = d.blocks;
  if (d.webFonts) setDocFonts(d.webFonts);
  state.texts = {};
  state.original = {};
  state.byId = new Map();
  state.byIdOrig = new Map();
  walkParas(d.blocks, (b) => { state.texts[b.id] = b.text || ""; state.original[b.id] = b.text || ""; state.byId.set(b.id, b); if (!edited.has(b.id)) state.byIdOrig.set(b.id, b); });
  Object.assign(state.original, d.original || {});
  applyEditState(d);
  state.owpml = d.owpml || null;
  if (redraw) { // 문서가 바뀜 — 반영 못 한 글·고른 자리는 사라진다
    state.failed.clear();
    state.localRev += 1;
    state.structRev = state.localRev;
    state.cur = null;
    state.selected = null;
  }
  if (!same) { // 기준이 바뀜 — 옛 기준의 검증 결과·PDF 는 내린다
    if (redraw) state.mapping = null; // 다른 문서 상태 — 옛 쪽 나눔을 쓰지 않는다(새 매핑이 오면 다시 나눔)
    state.mappingStale = !!state.mapping; // 확정(문서 그대로) — 새 기준의 쪽 매핑이 올 때까지 지금 쪽 나눔을 둔다(renderVerify 가 바꿔 끼움)
    state.verify = null;
    state.mappingEdited = null;
    state.lastEditStarted = null;
    state.pdfWhich = "original";
    state.pdfVer += 1;
    state.pollSeq += 1; // 읽는 중이던 옛 기준의 검증 응답은 버린다(poll)
    $("importSteps").textContent = "";
    $("editSteps").textContent = "";
  }
  if (redraw) renderDoc(d.blocks);
  else for (const p of document.querySelectorAll("#doc .para.edited")) p.classList.toggle("edited", state.edited.has(p.dataset.id));
  updateEdits();
  refreshToolbar();
  syncSeg();
  renderVerify(same ? state.verify || {} : {});
  poll();
  dv.plan = null; // 구분 기준 계획은 옛 기준 위의 것 — 서버도 버렸다(다시 계획)
  dv.result = null;
  if (redraw) { // 되돌린 문서 — 구분 기준 적용 상태·개요 오버레이도 그때 것으로
    if (heads.dlg === "divisions") headsColClose(true);
    divReset();
    outlineLoad(true);
  }
}

// ---------------------------------------------------------------- 검증
async function poll() {
  // 「이미 읽는 중」 은 지금 연 문서(epoch)의 읽기일 때만 — 앞서 연 문서의 읽기는 응답을 버리고 끝나므로 그것을 보고 돌아가면 이 문서는 검증·쪽 매핑을 끝내 못 받는다
  // (2026-11-17: 문서 열기가 겹치면(큰 문서를 여는 몇 초 사이 다시 누름 — GET 이 셋) 마지막 화면에 매핑이 없어 쪽이 「≈n쪽」 어림 나눔으로 남고 표가 쪽마다 안 나뉘었다)
  if (!state.id || state.polling === state.epoch) return;
  const id = state.id, epoch = state.epoch;
  state.polling = epoch;
  state.pollError = null;
  try {
    for (;;) {
      const seq = state.pollSeq;
      const v = await api(`/api/docs/${id}/verify`);
      if (epoch !== state.epoch) break;
      if (seq !== state.pollSeq) continue; // 읽는 사이 기준이 바뀜(확정·복원, adoptBase) — 옛 기준의 응답은 버리고 다시 읽는다
      renderVerify(v);
      if (!verifyBusy(v)) break; // 스크립트 단계(running) · LLM 검토(reviewing — spec_hwpx_웹편집 ② §4-1)가 모두 끝날 때까지 다시 읽는다
      await new Promise((r) => setTimeout(r, 1000));
    }
  } catch (e) {
    if (epoch === state.epoch) { state.pollError = e; renderSummary(state.verify || {}); }
  } finally { if (state.polling === epoch) state.polling = false; } // 뒤에 연 문서의 읽기가 돌고 있으면 그 표시는 둔다
}

const verifyBusy = (v) => Object.values(v || {}).some((j) => j && (j.running || j.reviewing));

function canVerify() {
  const v = state.verify;
  return !!state.id && !!v && !!v.import && !v.import.running && !(v.edit && v.edit.running) && !state.failed.size;
}

async function startEditVerify() {
  await flushAll();
  if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 검증할 수 없습니다 — 「고친 문단」 탭에서 다시 반영하세요", true); return; }
  try {
    renderVerify(await api(`/api/docs/${state.id}/verify`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: "edit", revision: state.localRev }),
    }));
    showTab("Verify");
    poll();
  } catch (e) { toast(e.message, true); }
}

// 출력파일 검증이 지금 수정을 검사한 것인지 — 서버 편집 차례(rev)로 견준다(다시 연 작업·새로 고친 화면에서도 맞게, spec_작업 ② §7).
// 서버가 rev 를 안 주면(옛 응답) 예전대로 로컬 수정 번호로.
const editFresh = () => {
  const ed = state.verify && state.verify.edit;
  if (!ed) return false;
  if (ed.rev == null) return ed.revision === state.localRev;
  return ed.rev === state.serverRev && !state.timers.size && !state.inflight && !state.failed.size;
};

function renderVerify(v) {
  state.verify = v;
  if (v.mapping && (!state.mapping || state.mappingStale)) { // mappingStale = 확정 뒤 옛 기준의 쪽 나눔을 두고 있던 중 — 새 기준의 매핑으로 바꿔 끼운다
    state.mappingStale = false;
    state.mapping = v.mapping;
    state.unit = v.mapping.unit || "쪽";
    paginate();
    state.editsDirty = true;
  }
  state.mappingEdited = v.mappingEdited || null;
  if (v.edit && !v.edit.running && state.lastEditStarted !== v.edit.started) {
    state.lastEditStarted = v.edit.started;
    state.pdfVer += 1;
  }
  const segEdited = document.querySelector('#pdfSeg [data-which="edited"]');
  segEdited.disabled = !(v.pdfs || []).includes("edited");
  const imp = $("importSteps"), eds = $("editSteps");
  if (v.import) fillSteps(imp, v.import);
  if (v.edit) fillSteps(eds, v.edit);
  else eds.innerHTML = `<li class="muted">글을 고친 뒤 「출력파일 검증」을 누르면 저장본을 ${APP()} PDF 로 찍어 원본과 비교합니다.</li>`;
  stageSummary($("importBox"), $("importSum"), v.import);
  stageSummary($("editBox"), $("editSum"), v.edit);
  renderSummary(v);
  const b = $("verifyBtn");
  b.disabled = !canVerify();
  b.textContent = v.edit && v.edit.running ? "검증 중…" : "출력파일 검증";
  if (!$("panePdf").hidden) showPdf();
  if (state.editsDirty && !$("paneEdits").hidden) drawEdits();
  if ((v.import || v.edit) && !verifyBusy(v)) logTouched(); // 검증 끝 — 기록 탭에 새 줄
}

function stageSummary(box, sum, job) {
  if (!job) { sum.textContent = ""; return; }
  const c = { ok: 0, warn: 0, fail: 0, skip: 0 };
  job.steps.forEach((s) => { if (s.key !== "llm" && s.status in c) c[s.status] += 1; }); // LLM 검토 단계 자체는 셈에서 뺀다(그 판정은 단계 상태에 이미 들어감)
  sum.textContent = job.running ? "진행 중" : [c.ok && `통과 ${c.ok}`, c.warn && `주의 ${c.warn}`, c.fail && `실패 ${c.fail}`, c.skip && `건너뜀 ${c.skip}`,
    job.reviewing && "LLM 검토 중"].filter(Boolean).join(" · ");
  sum.className = `stage-sum ${job.running ? "run" : job.status}`;
  if (!box.dataset.touched) box.open = job.running || job.status !== "ok" || box.id === "editBox";
}

function renderSummary(v) {
  const box = $("summary");
  const imp = v.import, ed = v.edit;
  const done = (j) => j.steps.filter((x) => !["wait", "run"].includes(x.status)).length;
  const lines = [];
  let s;
  if (state.pollError) s = { cls: "fail", big: "✕", title: "검증 상태를 읽지 못함", text: state.pollError.message, retry: true };
  else if (!imp) s = { cls: "run", big: "…", title: "검증 준비 중", text: "" };
  else if (imp.running) s = { cls: "run", big: "⟳", title: "가져오기 검증 중", text: `${done(imp)}/${imp.steps.length} 단계 · ${APP()} PDF 출력은 문서 크기에 따라 수십 초~수 분 걸립니다.` };
  else if (ed && ed.running) s = { cls: "run", big: "⟳", title: "출력파일 검증 중", text: `${done(ed)}/${ed.steps.length} 단계 · 저장본을 ${APP()}로 PDF 출력하고 원본과 비교합니다.` };
  else if (state.edited.size && !editFresh()) {
    s = { cls: "pending", big: "●", title: "지금 수정은 아직 검증 전",
      text: ed ? "마지막 출력파일 검증 뒤에 글을 더 고쳤습니다. 「출력파일 검증」을 다시 누르세요." : `고친 문단 ${state.edited.size}개 — 「출력파일 검증」으로 ${APP()} PDF 를 비교하세요.`, verify: true };
  } else if (ed && editFresh()) {
    const st = (k) => ed.steps.find((x) => x.key === k);
    const fail = ed.steps.find((x) => x.status === "fail"), warn = ed.steps.find((x) => x.status === "warn");
    const pdfSkipped = st("epdf").status === "skip";
    if (fail) s = { cls: "fail", big: "✕", title: "출력파일 검증 — 문제 있음", text: `${fail.title}: ${fail.detail}` };
    else if (pdfSkipped) s = { cls: "ok", big: "✓", title: "저장본 확인(PDF 비교 없음)", text: `저장본에서 바뀐 것은 고친 문단뿐입니다. ${APP()} PDF 가 없어 출력 비교는 하지 않았습니다.` };
    else if (warn) s = { cls: "warn", big: "!", title: "출력파일 검증 — 눈으로 확인할 것", text: `${warn.title}: ${warn.detail}` };
    else s = { cls: "ok", big: "✓", title: "출력파일 검증 통과", text: "달라진 출력이 고친 문단이 있는 곳뿐이고, 고친 글이 기호까지 PDF 에 있습니다." };
    const ep = st("epages");
    if (ep && ep.status !== "skip" && ep.diffPages && ep.diffPages.length) s.compare = ep;
  } else {
    const st = (k) => imp.steps.find((x) => x.key === k);
    const fail = imp.steps.find((x) => x.status === "fail");
    if (fail) s = { cls: "fail", big: "✕", title: "가져오기 검증 — 문제 있음", text: `${fail.title}: ${fail.detail}` };
    else {
      s = { cls: imp.status === "warn" ? "warn" : "ok", big: imp.status === "warn" ? "!" : "✓", title: "가져오기 확인", text: "" };
      const pdf = st("pdf"), map = st("map"), render = st("render");
      lines.push(["파일 왕복", st("package").status === "ok" ? "그대로 저장하면 원본과 바이트 동일" : st("package").detail]);
      if (pdf.status === "skip") lines.push([`${APP()} 출력`, `${APP()}가 없어 비교 안 함`]);
      else {
        lines.push([`${APP()} 출력`, render.status === "ok" ? `다시 쓴 파일의 ${APP()} PDF 가 원본과 픽셀 동일(${pdf.pages}${state.unit})` : render.detail]);
        lines.push(["PDF 위치", `${map.detail.replace(/ — .*$/, "")}${state.mapping && state.mapping.ratio < 1 ? " — 못 찾은 문단도 파일엔 그대로 있음" : ""}`]);
      }
      lines.push(["웹 화면", "편집용 보기 — 출력 배치는 PDF 탭에서 확인"]);
    }
  }
  const rv = [imp, ed].find((j) => j && j.reviewing);
  if (rv && s.cls !== "run") s.text = `${s.text ? `${s.text} ` : ""}LLM 이 주의·실패 단계를 다시 보는 중 — 판정이 바뀔 수 있습니다.`;
  box.className = `summary ${s.cls}`;
  box.textContent = "";
  box.append(el("div", "big", s.big));
  const d = el("div", "sum-body");
  d.append(el("b", null, s.title));
  if (s.text) d.append(el("p", null, s.text));
  if (lines.length) {
    const dl = el("dl");
    for (const [k, x] of lines) { dl.append(el("dt", null, k)); dl.append(el("dd", null, x)); }
    d.append(dl);
  }
  const acts = el("div", "sum-acts");
  if (s.verify && canVerify()) { const b = el("button", "btn sm primary", "출력파일 검증"); b.type = "button"; b.onclick = startEditVerify; acts.append(b); }
  if (s.compare) { const b = el("button", "btn sm", "달라진 곳 비교"); b.type = "button"; b.onclick = () => openCompare(s.compare, 0); acts.append(b); }
  if (s.retry) { const b = el("button", "btn sm", "다시 연결"); b.type = "button"; b.onclick = poll; acts.append(b); }
  if (acts.childNodes.length) d.append(acts);
  box.append(d);
}

function fillSteps(ol, job) {
  ol.textContent = "";
  for (const s of job.steps) {
    const li = el("li", `step ${s.status}`);
    li.append(el("span", "st", ICON[s.status]));
    li.append(el("span", "ttl", s.title));
    li.append(el("span", "sec", s.seconds != null ? `${s.seconds}s` : s.status === "run" ? "진행 중" : ""));
    li.append(el("div", "det", s.detail || (s.status === "wait" ? s.about : "")));
    li.querySelector(".ttl").title = s.about;
    if (s.llm) { // 검증 LLM 검토가 바꾼 판정 — 스크립트의 원래 판정을 함께(spec_hwpx_웹편집 ② §4-1)
      const VERD = { real: "실제 문제", reference: "기준 쪽 사정", mixed: "섞임", unclear: "판단 못 함" };
      const KO = { ok: "통과", warn: "주의", fail: "실패", skip: "건너뜀" };
      const was = s.script && s.script.status !== s.status ? ` · 스크립트 판정 ${KO[s.script.status] || s.script.status} → LLM 판정 ${KO[s.status] || s.status}` : "";
      li.append(el("div", "det", `LLM — ${VERD[s.llm.verdict] || s.llm.verdict}${was}: ${s.llm.reason || ""}`));
    }
    if (s.diffPages && s.diffPages.length) li.append(pageChips(s));
    const miss = s.missing || (s.blocks && s.blocks.map((id) => ({ id, text: state.texts[id] || id })));
    if (miss && miss.length) li.append(blockList(miss, s.key === "map" ? `PDF 위치를 못 찾은 문단 ${s.missingCount || miss.length}개` : `확인할 문단 ${miss.length}개`));
    if (s.extra && s.extra.length) li.append(blockList(s.extra.map((id) => ({ id, text: state.texts[id] || id })), `예상 밖으로 바뀐 문단 ${s.extra.length}개`));
    if (s.checks && s.checks.length) li.append(pageCheckList(s.checks));
    if (s.heads && s.heads.patterns && s.heads.patterns.length) li.append(headTable(s.heads.patterns));
    if (s.fonts && (s.fonts.faces || []).length) li.append(fontTable(s.fonts));
    ol.append(li);
  }
}

const KIND = {
  expected: ["고친 곳", "고친 문단이 있는 곳"],
  shifted: ["이후 차이", "고친 곳 이후에 달라진 곳 — 밀림으로 추정하지만 원인은 확인하지 않음"],
  minor: ["미세", "글자·기호·줄 위치·그림이 같고 글자 가장자리 픽셀만 다름(선·도형 변화는 이 판정으로 모름)"],
  unexpected: ["예상 밖", "고친 곳보다 앞에서 글이나 위치가 달라짐"],
};

function chipKind(s, page) {
  for (const k of ["expected", "shifted", "minor", "unexpected"]) if ((s[k] || []).includes(page)) return k;
  return "unexpected";
}

function pageChips(s) {
  const wrap = el("div", "chips-wrap");
  const groups = {};
  s.diffPages.forEach((d, i) => { (groups[chipKind(s, d.page)] ||= []).push([d, i]); });
  for (const k of ["unexpected", "expected", "shifted", "minor"]) {
    const g = groups[k];
    if (!g) continue;
    const row = el("div", "chips");
    row.append(el("span", `chip-label ${k}`, `${KIND[k][0]} ${g.length}`));
    row.title = KIND[k][1];
    g.slice(0, 40).forEach(([d, i]) => {
      const c = el("button", `chip ${k}`, `${d.page}`);
      c.type = "button";
      c.setAttribute("aria-label", `${d.page}${state.unit} 비교 — ${KIND[k][1]}`);
      c.title = `${d.page}${state.unit} · ${KIND[k][1]} · 다른 픽셀 ${(d.ratio * 100).toFixed(3)}%`;
      c.onclick = () => openCompare(s, i);
      row.append(c);
    });
    if (g.length > 40) row.append(el("span", "chip-more", `외 ${g.length - 40}`));
    wrap.append(row);
  }
  return wrap;
}

const CHECK = { moved: "PDF 맨 위 줄로 나눔을 옮김", split: "앞 쪽에서 이어진 문단·표 행", short: "맨 위 줄이 짧아 확인 못 함",
  blank: "글 없는 쪽", miss: "맨 위 줄을 못 찾음(매핑 나눔 그대로)", none: "이 쪽에서 시작하는 단위 없음" };

function pageCheckList(checks) {
  const d = el("details", "more");
  d.append(el("summary", null, `쪽별 확인 ${checks.length}개 보기`));
  const ul = el("ul");
  for (const c of checks) {
    const li = el("li");
    const b = el("button", null, `${c.page}쪽 · ${CHECK[c.status] || c.status} · PDF 맨 위 「${short(c.top, 28)}」`);
    b.type = "button";
    b.title = `PDF ${c.page}쪽 맨 위: ${c.top}
웹 ${c.page}쪽 첫 단위: ${c.unit || "(없음)"}`;
    b.onclick = () => goPage(c.page);
    li.append(b);
    ul.append(li);
  }
  d.append(ul);
  return d;
}

function goPage(n) {
  const box = document.querySelector(`#doc [data-page="${n}"]`);
  if (box) box.scrollIntoView({ block: "start", behavior: scrollHow() });
  const m = state.mapping;
  state.pdfWhich = "original";
  syncSeg();
  state.pdfPage = m && m.sheets ? m.sheets[n - 1] || n : n;
  $("pdfNote").textContent = `웹 ${n}쪽 ↔ ${APP()} PDF${m && m.twoUp ? ` ${state.pdfPage}장(${n}쪽이 든 장)` : ` ${n}쪽`}`;
  showTab("Pdf");
  setPanel(true);
}

function blockList(items, label) {
  const d = el("details", "more");
  d.append(el("summary", null, label));
  const ul = el("ul");
  for (const it of items) {
    const li = el("li");
    const b = el("button", null, short(it.text, 70));
    b.type = "button";
    b.title = oneLine(it.text);
    b.onclick = () => scrollToBlock(it.id, true);
    li.append(b);
    ul.append(li);
  }
  d.append(ul);
  return d;
}

// 레터·글꼴 대조 자료 표(spec_hwpx_웹편집 ② §3-2) — 검증 단계의 heads.patterns · fonts.faces/latin
function miniTable(label, head, rows, note, wrapCols = []) {
  const d = el("details", "more");
  d.append(el("summary", null, label));
  const wrap = el("div", "mini-wrap");
  const t = el("table", "mini");
  const tr = el("tr");
  for (const h of head) tr.append(el("th", null, h));
  t.append(tr);
  for (const r of rows) {
    const row = el("tr", r.cls || null);
    r.cells.forEach((c, i) => row.append(el("td", wrapCols.includes(i) ? "wrap" : null, c == null ? "—" : String(c))));
    if (r.title) row.title = r.title;
    t.append(row);
  }
  wrap.append(t);
  d.append(wrap);
  if (note) d.append(el("div", "mini-note", note));
  return d;
}

const PLACE = { body: "본문", box: "글상자", cell: "표 칸" };
const mm = (v) => (v == null ? null : `${v.toFixed(1)}`);

function headTable(patterns) {
  return miniTable(`레터 꼴별 PDF 실측 ${patterns.length}개 보기`, ["자리", "꼴", "문단", "레터 앞 빈칸", "레터 뒤", "둘째 줄 / 서식"],
    patterns.map((p) => ({
      cells: [PLACE[p.place] || p.place, p.full, p.count, mm(p.leadMm), mm(p.gapMm),
        `${p.line2Count ? mm(p.line2Mm) : "—"} / ${mm(p.hangMm) ?? "—"}${p.line2Count ? ` (${p.line2Count})` : ""}`],
      title: `${p.full} — ${APP()} PDF 에서 잰 가운데 값(mm). 둘째 줄 = 둘째 줄이 첫 줄보다 들어간 폭 / 서식 = 문단 서식의 내어쓰기(괄호 = 잰 문단 수)`,
    })),
    "mm · 꼴: _n = 반각 빈칸 n칸, ＿n = 전각, ⇥n = 탭, N = 숫자, list: = 자동 번호·글머리", [5]);
}

const FONT_VERDICT = { same: ["같음", "ok"], subst: ["둘 다 대체", "ok"], equiv: ["같은 디자인", "ok"], differ: ["웹이 다른 글꼴", "warn"],
  hangul: ["한글 전용 글꼴", "warn"], unknown: ["모름", ""] };
const FONT_HOW = { equiv: "한컴 대응표", subst: "문서 대체 글꼴", fallback: "웹 기본" };
const FONT_LANG = { LATIN: "영문", HANJA: "한자", JAPANESE: "일어", SYMBOL: "기호" };

function fontTable(f) {
  const rows = [];
  for (const [kind, list] of [["한글", f.faces || []], ["영문·숫자", f.latin || []]]) {
    for (const x of list) {
      const [v, cls] = FONT_VERDICT[x.verdict] || [x.verdict, ""];
      const pdf = Object.entries(x.pdf).map(([n, c]) => `${n} ${c}`).join(", ");
      const how = x.how && x.how !== "same" ? x.how : null;
      const lang = FONT_LANG[x.lang] ? `${FONT_LANG[x.lang]} ` : "";
      const web = how ? `${lang}${x.web} → ${x.via || x.uses || "기본"}` : `${lang}${x.web}`;
      rows.push({ cls, cells: [kind, web, v, pdf],
        title: `${x.chars}자 · ` + (how ? `「${x.web}」${x.type === "HFT" ? "(한글 전용 HFT)" : ""} 대신 웹은 ${FONT_HOW[how]}의 「${x.via || x.uses || "기본 글꼴"}」로 그림`
          : `웹은 「${x.web}」 그대로 그림`) });
    }
  }
  return miniTable(`글꼴 판정 ${rows.length}개 보기`, ["글자", "웹 글꼴(→ 대체)", "판정", `${APP()} PDF 글꼴(글자 수)`], rows,
    "웹은 글자마다 문서의 언어별 글꼴(영문·숫자 = 영문 글꼴)로 그린다 · 없는 글꼴은 한글처럼 문서 대체 글꼴·한컴 대응표(HFT → 같은 디자인 TTF)로", [1, 3]);
}

function syncSeg() {
  document.querySelectorAll("#pdfSeg button").forEach((x) => { const on = x.dataset.which === state.pdfWhich; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on); });
}

// ---------------------------------------------------------------- PDF 보기
function pagesOf(id) {
  const ed = state.pdfWhich === "edited";
  const m = ed && state.mappingEdited && editFresh() ? state.mappingEdited : state.mapping;
  if (!m) return null;
  const pg = m.pages[id];
  if (!pg) return { page: null, label: "PDF 위치 모름", exact: false };
  const approx = ed && m === state.mapping;
  const sheet = m.sheets ? m.sheets[pg[0] - 1] || pg[0] : pg[0];
  return { page: sheet, label: `${approx ? "원본 기준 " : ""}${pg.join("·")}쪽${m.twoUp ? ` (PDF ${sheet}장)` : ""}`, exact: !approx };
}

function select(id) {
  state.selected = id;
  const note = $("pdfNote");
  if (!state.mapping) { note.textContent = `PDF 매핑이 끝나면 문단이 있는 ${APP()} PDF 자리를 보여 줍니다.`; return; }
  const pg = pagesOf(id);
  if (pg && pg.page) {
    state.pdfPage = pg.page;
    note.textContent = `선택한 문단 → ${pg.label}${pg.exact ? "" : " (수정본에서의 위치는 확인 안 됨 — 출력파일 검증을 다시 하세요)"} · ${short(state.texts[id], 40)}`;
  } else {
    note.textContent = `선택한 문단을 PDF 에서 찾지 못했습니다(빈 글·숨은 글·PDF 에 다르게 찍힌 글). · ${short(state.texts[id], 40)}`;
  }
  if (!$("panePdf").hidden) showPdf();
}

function pdfCount(which) {
  if (which === "edited") {
    const ep = state.verify && state.verify.edit && state.verify.edit.steps.find((s) => s.key === "epdf");
    return ep && ep.pages ? ep.pages : 0;
  }
  const st = state.verify && state.verify.import && state.verify.import.steps.find((s) => s.key === "pdf");
  return st && st.pages ? st.pages : 0; // PDF 장 수(2쪽 모아 찍기면 문서 쪽의 반)
}

function showPdf() {
  const which = state.pdfWhich;
  const count = pdfCount(which);
  const img = $("pdfImg"), input = $("pdfPageInput");
  if (!count) {
    img.hidden = true;
    $("pdfOf").textContent = "/ –";
    const imp = state.verify && state.verify.import;
    if (!state.mapping) $("pdfNote").textContent = imp && !imp.running ? `${APP()} PDF 가 없습니다(${APP()} 미설치 또는 출력 실패).` : `가져오기 검증에서 ${APP()} PDF 를 찍는 중입니다…`;
    return;
  }
  state.pdfPage = Math.min(Math.max(1, state.pdfPage), count);
  if (!state.selected) $("pdfNote").textContent = `문단을 누르면 ${APP()} PDF 에서 그 문단이 있는 자리를 보여 줍니다.`; // 「PDF 를 찍는 중…」 안내가 PDF 가 온 뒤에도 남지 않게
  input.max = count;
  input.value = state.pdfPage;
  $("pdfOf").textContent = `/ ${count}${state.unit}`;
  $("pdfPrev").disabled = state.pdfPage <= 1;
  $("pdfNext").disabled = state.pdfPage >= count;
  img.hidden = false;
  img.alt = `${which === "original" ? "원본" : "수정본"} PDF ${state.pdfPage}${state.unit}`;
  img.src = `/api/docs/${state.id}/pdf/${which}/${state.pdfPage}.png?v=${which === "edited" ? state.pdfVer : `b${state.base}`}`; // 기준 PDF 는 확정마다 다른 파일 — 주소도 다르게(브라우저 캐시)
}

const TOOL_TABS = ["Verify", "Edits", "Pdf", "Log", "Heads", "Tables", "Agent", "Dash", "Div", "Compare", "Tasks"];
const TOOL_INFO = {
  Verify: ["검증", "파일·출력", "원본을 읽고 저장한 결과와 출력파일을 확인합니다."],
  Edits: ["고친 문단", "변경·확정", "고친 부분을 기준(마지막 확정)과 비교하고, 확정하거나 되돌립니다."],
  Pdf: ["PDF", "출력 미리보기", "원본과 수정본의 실제 출력 모양을 확인합니다. 문단을 누르면 해당 쪽으로 이동합니다."],
  Log: ["기록", "작업 이력", "편집·추출·검증·내려받기를 시간순으로 확인합니다."],
  Heads: ["헤딩 추출", "구조 분석", "문서와 나란히 보며 라벨, 템플릿과 판단 근거를 확인합니다."],
  Tables: ["테이블", "표 관리", "문서의 표만 따로 — 소속 헤딩·계산식·엑셀식 보기·표 지침을 다룹니다."], // 탭 이름은 「테이블」(2026-11-16 사용자 「표 아니고 테이블로」 — 전의 「표」 · spec_작업 ② §10 「둘째 줄」)
  Agent: ["에이전트", "요청 · 제안", "문서에서 자리를 고르고 요청하면 글·표·표 채우기·서식 입히기를 제안합니다. 제안은 「문서에 반영」 을 눌러야 들어가고, 서식 관리자에서 서식을 저장해 다시 씁니다."], // doc_agent.js(spec_일반편집 ② §12 · 「서식 관리자」 = spec_서식복사 ② §2)
  Dash: ["대시보드", "워크플로우 단계 흐름", "이 워크플로우의 단계를 차례대로 보이고, 단계마다 지금 상태와 그 단계를 하는 단추를 둡니다 — 묶음의 「한 번에 진행」 도 여기서 누릅니다."], // dashboard.js(spec_작업에이전트 ② §9 — 2026-11-18 사용자)
  Div: ["작업 개요", "프로젝트 · 워크플로우", "프로젝트 구성과 워크플로우 라운드의 첨부 파일·진행 단계를 관리합니다."],
  Tasks: ["작업 리스트", "프로젝트 · 워크플로우 · 라운드", "프로젝트별 워크플로우와 이전 라운드를 열고, 새 워크플로우나 라운드를 시작합니다."],
  Compare: ["문서 비교", "병합 전 확인", "문서별 라벨과 템플릿을 나란히 비교하고 확인한 문서를 표시합니다."]
};

// ---- 아래 줄 접기·바꾸기 (spec_hwpx_웹편집 ② §9 「줄 접기·바꾸기」 — 2026-11-10 사용자 "접었다 폈다", "펴기 이런건 상단에 넣어줘. 그 줄 자체가 안보이게",
// "세번째 편집 툴도 동일하게", "상단에 아이콘 하나 가운데 주고 거기 누르면 바가 변경")
// 상단 바 [탭 ▴][⇅][편집 ▴][파일명 ▴]: 탭·편집은 공용 도구 행 안의 묶음, 파일명은 각 문서 위의 독립 행을 함께 접는다.
// ⇅ = 탭/편집 묶음 중 하나만 표시. 세 접힘 상태는 이 브라우저에 기억(localStorage nfm.navFold·nfm.barFold·nfm.fileFold).
const FOLD_ROWS = { nav: ["workspaceNav", "navFold", "nfm.navFold", "도구 탭 띠", "탭"], bar: ["docBar", "barFold", "nfm.barFold", "편집 도구 줄", "편집"], file: ["fileInfo", "fileFold", "nfm.fileFold", "파일명 줄", "파일명"] };
function rowFolded(which) { return $(FOLD_ROWS[which][0]).classList.contains("folded"); }
function rowFold(which, on, remember = true) {
  const [rowId, btnId, key, label, short] = FOLD_ROWS[which];
  $(rowId).classList.toggle("folded", on);
  if (which === "file") document.querySelector(".workspace").classList.toggle("file-names-folded", on);
  $("workspaceTools").classList.toggle("folded", rowFolded("nav") && rowFolded("bar"));
  const b = $(btnId);
  b.setAttribute("aria-pressed", String(!on));
  b.classList.toggle("on", !on);
  b.title = `${label} ${on ? "펴기" : "접기"}`;
  b.textContent = `${short} ${on ? "▾" : "▴"}`;
  if (remember) { try { localStorage.setItem(key, on ? "1" : "0"); } catch { /* 기억만 안 함 */ } }
  // 줄이 사라지거나 생겨 문서 보기 높이가 바뀌면 맞춤 배율은 #scroller ResizeObserver(bind 끝)가 한 번만 다시 잰다 — 여기서 또 재면 ⇅(두 줄을 잇달아 바꿈)가
  // 중간 높이까지 세 번 재고, 잴 때마다 74쪽 문서 전체를 다시 배치해 1~2초 걸렸다(2026-11-10 사용자 "왜 전환이 느려?").
}
function rowFoldLoad(which) { try { return localStorage.getItem(FOLD_ROWS[which][2]) === "1"; } catch { return false; } }
// ⇅ — 탭 띠만 보이면 편집 도구 줄만으로, 그 밖(편집 줄만 · 둘 다 · 둘 다 없음)이면 탭 띠만으로
function barSwap() {
  const navOnly = !rowFolded("nav") && rowFolded("bar");
  rowFold("nav", navOnly);
  rowFold("bar", !navOnly);
}

// ---- 패널 머리(spec_작업 ② §10 「패널 머리」, 2026-11-11 사용자 "이 쪽에 작업 목록을 선택할 수 있는 리스트를 넣어주고 …" → "사이드 패널 상단에 저 탭은 중복이잖아" · "그냥 작업에서 연구개발과제를 택하면 지금 내용이 나오는거지")
// 패널 머리 = 「작업」 목록 줄(#panelTask — taskDraw) + 도구 이름 줄(#toolTitle·#toolTag — showTab). 패널에 도구 탭 줄은 두지 않는다(문서 위 탭 띠와 겹침 — 한때 넣었던 #panelTabs·panelTabsDraw 는 같은 날 걷어냄).
async function panelTaskPick(v) {
  const id = state.id;
  if (await taskSet("kind", v) && state.id === id && (v === "rnd" || v === "general")) showTab(v === "general" ? "Agent" : "Div"); // 「일반 문서」 = 에이전트 보기(hwpx 만 — docx 면 그대로)
}

// 탭 띠에 단추가 없는 도구 = 「연구개발과제」(Div — 2026-11-12 탭을 없앰): 작업 종류가 연구개발과제일 때만 열린다(전의 탭 보임 조건 그대로)
// 에이전트(Agent — spec_일반편집 ② §12)는 탭(패널 머리 탭 #tabAgent — 대시보드 다음)의 보임과 상관없이 hwpx 문서면 열린다 — 탭의 보임은 toolTabsDraw 가 이 값으로 정한다
const toolShown = (n) => { if (n === "Agent") return !!state.id && state.format !== "docx" && typeof agentShow === "function"; if (n === "Dash") return typeof dashShown === "function" && dashShown(); const t = $(`tab${n}`); return t ? !t.hidden : !!state.id && (n === "Tasks" || n === "Div" && taskRnd()); };
// 에이전트 보기의 자리(2026-11-18 사용자 「대시보드 옆 에이전트는 워크플로우 아이콘 옆 에이전트아이콘으로 … 팝업으로 … 대시보드 옆으로 들어 갈 수 있도록」 — agent_float.js):
// 떠 있는 창(기본)이면 showTab("Agent") 은 패널을 바꾸지 않고 그 창을 연다 — 부르는 쪽(대시보드 · 작업 진행 에이전트 · TASK 들어가기)은 그대로 「에이전트 보기를 연다」 로 쓴다
function agentFloatOn() { return typeof agentFloating === "function" && agentFloating(); } // 함수 선언 — toolTabsDraw(위)가 이 줄보다 먼저 불려도 되게
const PANEL_BACK = ["Dash", "Div", "Heads", "Tables", "Verify"]; // 패널이 에이전트를 보이다 그 자리를 잃을 때(창으로 띄움) 갈 도구 — 앞의 넷은 2열을 닫지 않는다(showTab 의 headsColClose)
function showTab(name) {
  if (!TOOL_INFO[name] || !toolShown(name)) return;
  if (name === "Agent" && agentFloatOn()) {
    agentFloatOpen();
    const cur = $("panel").dataset.tool, back = PANEL_BACK.find((n) => toolShown(n));
    if ((!cur || cur === "Agent" || !toolShown(cur)) && back) showTab(back); // 패널이 볼 것이 없으면(처음 · 에이전트를 보이던 패널) 대시보드부터
    return;
  }
  if (!["Heads", "Div", "Tables", "Agent", "Dash"].includes(name) && !headsColClose()) return; // 대시보드도 문서 옆 열(변경 계획 목록 · 서식 복사 …)을 닫지 않는다 — 그 단추가 그 열을 연다
  panelHelpClose();
  $("panel").dataset.tool = name;
  const workspace = document.querySelector(".workspace");
  workspace.classList.toggle("compare-mode", name === "Compare");
  for (const n of TOOL_TABS) {
    const on = n === name, tab = $(`tab${n}`);
    if (tab) { // 「연구개발과제」(Div)는 탭이 없다 — 검증·PDF·기록(패널 머리 탭 — tabIndex 는 toolTabsDraw 가)처럼 그 내용을 보는 동안 탭 띠에는 활성 탭이 없다
      tab.classList.toggle("active", on);
      tab.setAttribute("aria-selected", on);
      if (tab.closest("#workspaceNav")) tab.tabIndex = on ? 0 : -1;
    }
    const pane = $(`pane${n}`);
    if (pane && !(n === "Agent" && agentFloatOn())) pane.hidden = !on; // 떠 있는 창의 에이전트 보기는 패널 도구와 따로 — 창을 여닫을 때만(agent_float.js)
  }
  toolTabsDraw(); // 패널 머리 둘째 줄 탭 — 에이전트 · 작업 개요 · <도구> | 접는 묶음 검증 · PDF · 기록(작업 리스트는 상단 바 아이콘 — 아래 setPanel 이 그 눌림을 그린다)
  const strip = [...$("workspaceNav").querySelectorAll('[role="tab"]')].filter((b) => !b.hidden);
  if (strip[0] && !strip.some((b) => b.tabIndex === 0)) strip[0].tabIndex = 0; // 탭 띠에 활성 탭이 없으면 Tab 키는 보이는 첫 탭이 받는다
  const [title, tag, description] = TOOL_INFO[name];
  $("toolTitle").textContent = title; // 패널 머리 둘째 줄(도구 이름 + 꼬리표) · 접힌 띠 이름(colRailName)
  $("toolTag").textContent = tag;
  $("toolDescription").textContent = description; // 설명 줄은 없앰(2026-11-11 패널 머리 — 값만) — 어느 도구든 ? 도움말로
  $("toolHelp").replaceChildren(hHelp(`${title} 도움말`, `${title} — ${tag}\n${description}`
    + (name === "Heads" ? " 결과 탭에서 문서 구조·라벨·템플릿을 확인하고, 추출·설정에서 다시 분석할 수 있습니다." : name === "Tables" ? " 표 목록에서 소속을 대조하고, 각 표의 격자와 지침을 열 수 있습니다." : "")));
  toolDocDraw(); // 「작업」 옆 문서 자리 — 두 문서가 나란히면 도구를 쓸 문서 단추(원본 · 목적), 하나면 「목적 문서」 같은 짧은 이름(② §12 「도구는 문서마다」 — 긴 파일 이름은 문서 위 이름 줄에)
  setPanel(true);
  colsApply();
  if (name === "Pdf") showPdf();
  if (name === "Edits" && state.editsDirty) drawEdits();
  if (name === "Log") drawLog();
  if (name === "Heads") headsShow();
  if (name === "Div") divShow(); // 구분 기준(spec_구분_기준 ② §8)
  if (name === "Tables" && typeof tablesShow === "function") tablesShow(); // 표 모듈(tables.js, spec_헤딩_추출 ② §10)
  if (name === "Agent" && typeof agentShow === "function") agentShow(); // 에이전트 보기(doc_agent.js, spec_일반편집 ② §12)
  if (name === "Dash" && typeof dashShow === "function") dashShow(); // 대시보드(dashboard.js, spec_작업에이전트 ② §9)
  if (name === "Compare" && typeof compareShow === "function") compareShow();
  if (name === "Tasks" && typeof projectListShow === "function") projectListShow();
}

// 그 TASK 로 들어가기(spec_서식복사 ② §1 — task_catalog.js entry): 보통은 그 패널 도구(작업 개요 Div · 에이전트 Agent). entry 가 "Style"(문서 서식 복사)이면 패널 = hwpx 면 에이전트 보기 · docx 면 검증,
// 그리고 2열에 서식 관리자의 「서식 복사」 보기(style_lib.js styleSaveOpen). 차례: 패널 도구가 먼저다 — showTab 은 Heads·Div·Tables·Agent 가 아닌 도구로 갈 때 2열을 닫는다.
// 부르는 곳: TASK 카드(homeTaskStart) · 시작 화면 문서 목록(home_files.js) · 작업 리스트(project_workspace.js). 이 TASK 의 작업을 다시 열 때는 load 끝이 같은 열을 연다
// 「한 번에 진행」 이 도는 자리(spec_작업에이전트 ② §7): 보통 패널 「작업 개요」(묶음 상태 줄). 에이전트 보기가 그 TASK 를 이끌고 있으면(패널이 「에이전트」 — 진행 카드가 거기 있다) 바꾸지 않는다 —
// 전에는 실행 몸통(이관 taskRunSteps · 취합 gatherToPlan · 간단 모드 gqGo)이 늘 「작업 개요」 로 바꿔 에이전트의 진행 표시가 가려졌다(astra 11-16).
function taskPaneShow() {
  const tool = $("panel").dataset.tool;
  if (tool === "Div" || tool === "Dash" || (tool === "Agent" && typeof agwGuided === "function" && agwGuided())) return; // 대시보드에서 누른 「한 번에 진행」 도 그 자리에서 본다(대시보드의 진행 줄)
  showTab("Div");
}

function taskEnter(job) {
  const entry = taskEntryOf(job);
  if (entry !== "Style") { showTab(entry); if (typeof agentWorkEnter === "function") agentWorkEnter(job, entry); return; } // 단계가 있는 TASK — LLM 을 쓸 수 있으면 에이전트 보기로 옮겨 시작 턴(spec_작업에이전트 ② §1)
  showTab(toolShown("Agent") ? "Agent" : "Verify");
  if (typeof styleSaveOpen === "function") styleSaveOpen();
}

function setPanel(open) {
  if (open) colFold("panel", false, false); // 패널을 여는 동작(도구 탭·쪽 번호 …)은 접힌 패널도 편다 — 기억한 접힘은 그대로
  $("panel").hidden = !open || !state.id;
  $("panelBtn").setAttribute("aria-expanded", open);
  $("panelBtn").hidden = !state.id;
  $("panelBtn").setAttribute("aria-label", open ? "도구 닫기" : "문서 도구"); // 글 없는 아이콘 단추(2026-11-16 — design.md §9): 이름은 낭독·도움말로, 열림은 눌림 바탕(aria-expanded)
  $("panelBtn").title = open ? "도구 닫기 — 문서 도구 패널(오른쪽 열)을 닫습니다" : "문서 도구 — 문서 도구 패널(오른쪽 열)을 엽니다";
  taskListBtnDraw(); // 상단 바 「작업 리스트」 — 보임(문서를 연 동안) · 눌림(패널이 작업 리스트를 보임)
  if (!open) document.querySelector(".workspace").classList.remove("compare-mode");
  else if ($("tabCompare").getAttribute("aria-selected") === "true") document.querySelector(".workspace").classList.add("compare-mode");
}

// ---- 열 접기 (spec_hwpx_웹편집 ② §9 「열 접기」 — 2026-11-10 사용자 "각각 접어서 우측에 접히도록")
// 2열(#headsDlg)·3열(#panel) 머리의 » 를 누르면 그 열이 오른쪽으로 접혀 폭 28px 띠(.col-rail — « + 세로로 쓴 열 이름)만 남는다(.folded). 안의 것은 지우지 않고 감추기만 해서
// 펴면 펼친 트리·스크롤·쓰던 글이 그대로다. 띠를 누르거나 그 열을 여는 동작(도구 탭·배지·단추 → setPanel(true)·headsDlg())이 다시 편다. » · 띠로 정한 3열 접힘만 이 브라우저에
// 기억(nfm.panelFold — 다음 문서도 접힌 채로 열림 · 못 쓰면 기억만 안 함), 2열은 열 때마다 펴진 채. 문서 보기 폭이 바뀐 뒤의 맞춤 배율은 bind() 끝 #scroller ResizeObserver 가
// 한 번만 다시 잰다 — 여기서 refit() 을 부르지 않는다(rowFold 와 같음).
const FOLD_COLS = { heads: ["headsDlg", "headsFold", "headsRail", "headsDlgTitle", null], panel: ["panel", "panelFold", "panelRail", "toolTitle", "nfm.panelFold"],
  peer: ["peerCol", "peerFold", "peerRail", "peerName", null] }; // 같이 보기 열(spec_작업 ② §12)
function colFolded(which) { return $(FOLD_COLS[which][0]).classList.contains("folded"); }
function colRailName(which) { // 접힌 띠의 이름·도움말 = 지금 그 열의 제목(「템플릿 관계」·「헤딩 추출」 …)
  const [, , railId, titleId] = FOLD_COLS[which];
  const rail = $(railId), name = $(titleId).textContent.trim();
  rail.querySelector(".col-rail-name").textContent = name;
  rail.title = `${name} 펴기`;
  rail.setAttribute("aria-label", `${name} 펴기`);
}
function colFold(which, on, remember = true) {
  const [boxId, btnId, railId, , key] = FOLD_COLS[which];
  const box = $(boxId);
  if (remember && key) { try { localStorage.setItem(key, on ? "1" : "0"); } catch { /* 기억만 안 함 */ } }
  if (on) colRailName(which);
  if (box.classList.contains("folded") === on) return;
  const had = box.contains(document.activeElement); // 초점이 열 안에 있었으면 접힌 띠 ↔ 접기 단추로 옮긴다(감춘 요소에 남지 않게)
  box.classList.toggle("folded", on);
  if (which === "peer") peerOpenMark(); // 둘째 면이 접히면 편집 도구 줄은 문서 열 위로만(spec_작업 ② §12 「두 면」)
  if (which === "panel") taskListBtnDraw(); // 접힌 패널의 작업 리스트는 「보이는 중」 이 아니다(상단 바 아이콘의 눌림)
  colsApply(); // 접힌 열은 28px — 다른 열 폭을 문서 보기 몫 안으로 다시
  if (had) $(on ? railId : btnId).focus({ preventScroll: true });
}
function colFoldLoad(which) { try { return localStorage.getItem(FOLD_COLS[which][4]) === "1"; } catch { return false; } }

// 열 폭 조절 — 패널(3열)·헤딩 열(2열, #headsDlg). 왼쪽 가장자리를 끌기 · ←/→ 20px(Shift 80px) · Home/End 최소·최대 · 두 번 누르면 기본 폭(CSS 변수).
// 고른 폭은 이 브라우저에 기억(localStorage — 못 쓰면 기억만 안 함). 문서 보기는 늘 VIEW_KEEP px 남긴다 — 다른 열이 보이면 그 폭도 뺀 나머지가 최대라
// 창을 줄이면 패널 → 헤딩 열 차례로 줄어들고, 헤딩 열을 열고 닫을 때도 colsApply() 로 다시 맞춘다.
const VIEW_KEEP = 360;
const viewKeep = () => { const p = $("peerCol"); return p.hidden ? VIEW_KEEP : p.classList.contains("folded") ? VIEW_KEEP + 28 : VIEW_KEEP * 2; }; // 둘째 면이 펴져 있으면 두 면 몫(폭 반반 — spec_작업 ② §12 「두 면」), 접혀 있으면 띠 28px 더
const colSizers = []; // makeColSizer 로 만든 열들
const colsApply = () => { for (const c of colSizers) c.apply(); };

function makeColSizer({ box, handle, cssVar, key, min, fallback }) {
  const c = { w: null }; // w = 사용자가 고른 폭(px) — null = 기본(CSS 변수)
  const h = $(handle);
  const others = () => colSizers.reduce((s, o) => (o === c ? s : s + $(o.box).getBoundingClientRect().width), 0); // 숨은 열은 0
  c.box = box;
  c.max = () => Math.max(min, document.querySelector(".workspace").clientWidth - viewKeep() - others());
  c.clamp = (w) => Math.round(Math.min(c.max(), Math.max(min, w)));
  c.apply = () => {
    // 고른 폭은 :root 가 아니라 그 열 요소의 inline 변수로 — :root 변수를 바꾸면(지웠다 다시 써도) 상속 때문에 문서 전체(3.8만 요소)의 스타일을 다시 계산해
    // 열 접기·닫기마다 수백 ms 가 더 들었다(2026-11-10). 기본값은 :root(CSS — 창 폭 미디어 쿼리로 달라짐)에서 그대로 읽고, 값이 바뀔 때만 쓴다.
    const own = $(box).style;
    const def = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(cssVar)) || fallback;
    const now = c.clamp(c.w == null ? def : c.w); // 기본 폭도 문서 보기 몫 안으로(두 열이 다 보이면 기본값끼리도 넘칠 수 있다)
    const want = now !== def ? `${now}px` : "";
    if (own.getPropertyValue(cssVar) !== want) { if (want) own.setProperty(cssVar, want); else own.removeProperty(cssVar); }
    h.setAttribute("aria-valuemin", min);
    h.setAttribute("aria-valuemax", c.max());
    h.setAttribute("aria-valuenow", now);
  };
  const save = () => {
    try {
      if (c.w == null) localStorage.removeItem(key);
      else localStorage.setItem(key, String(c.clamp(c.w)));
    } catch { /* 저장소를 못 씀(비공개 창 등) — 기억만 안 함 */ }
  };
  try {
    const v = parseInt(localStorage.getItem(key), 10);
    if (v > 0) c.w = v;
  } catch { /* 기본 폭 */ }
  h.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    h.setPointerCapture(e.pointerId);
    document.body.classList.add("resizing");
    const right = $(box).getBoundingClientRect().right;
    const move = (ev) => { c.w = c.clamp(right - ev.clientX); c.apply(); };
    const up = () => {
      h.removeEventListener("pointermove", move);
      h.removeEventListener("pointerup", up);
      h.removeEventListener("pointercancel", up);
      document.body.classList.remove("resizing");
      save();
    };
    h.addEventListener("pointermove", move);
    h.addEventListener("pointerup", up);
    h.addEventListener("pointercancel", up);
  });
  h.addEventListener("dblclick", () => { c.w = null; c.apply(); save(); });
  h.addEventListener("keydown", (e) => {
    const cur = $(box).getBoundingClientRect().width, step = e.shiftKey ? 80 : 20;
    if (e.key === "ArrowLeft") c.w = c.clamp(cur + step); // 손잡이를 왼쪽으로 = 열이 넓어짐
    else if (e.key === "ArrowRight") c.w = c.clamp(cur - step);
    else if (e.key === "Home") c.w = min;
    else if (e.key === "End") c.w = c.max();
    else return;
    e.preventDefault();
    c.apply();
    save();
  });
  colSizers.push(c);
  c.apply();
  return c;
}

function bindPanelResize() { // 패널(3열) + 헤딩 열(2열) — 헤딩 열은 열려 있을 때만 폭을 차지한다
  makeColSizer({ box: "panel", handle: "panelResizer", cssVar: "--panel", key: "nfm.panelWidth", min: 280, fallback: 380 });
  makeColSizer({ box: "headsDlg", handle: "headsResizer", cssVar: "--heads-col", key: "nfm.headsColWidth", min: 320, fallback: 620 });
  // 둘째 면(같이 보기)은 폭 손잡이가 없다 — 문서 열과 늘 반반(spec_작업 ② §12 「두 면」): 패널·2열이 넓어지면 두 면이 함께 줄고, 두 면 몫(viewKeep)은 늘 남긴다
  window.addEventListener("resize", colsApply); // 창이 좁아져도 문서 보기 몫을 남기고, 다시 넓어지면 고른 폭으로
}

// ---------------------------------------------------------------- 쪽 비교 창
function openCompare(step, index) {
  state.compare = { step, which: step.compare, pages: step.diffPages, index, mode: state.compare ? state.compare.mode : "side", size: state.compare ? state.compare.size : "fit" };
  drawCompare();
  const dlg = $("compare");
  if (!dlg.open) dlg.showModal();
}

function drawCompare() {
  const c = state.compare;
  const d = c.pages[c.index];
  const kind = chipKind(c.step, d.page);
  const other = c.which === "rebuilt" ? "다시 쓴 파일" : "수정본";
  const u = state.unit;
  $("cmpTitle").textContent = `원본 ↔ ${other} · ${d.page}${u}`;
  $("cmpKind").textContent = `${KIND[kind][0]} — ${KIND[kind][1]} · 다른 픽셀 ${(d.ratio * 100).toFixed(3)}%`;
  $("cmpKind").className = `cmp-kind ${kind}`;
  $("cmpPos").textContent = `${c.index + 1} / ${c.pages.length}`;
  $("cmpPrev").disabled = c.index <= 0;
  $("cmpNext").disabled = c.index >= c.pages.length - 1;
  document.querySelectorAll("#compare [data-mode]").forEach((b) => { b.classList.toggle("on", b.dataset.mode === c.mode); b.setAttribute("aria-pressed", b.dataset.mode === c.mode); });
  document.querySelectorAll("#compare [data-size]").forEach((b) => { b.classList.toggle("on", b.dataset.size === c.size); b.setAttribute("aria-pressed", b.dataset.size === c.size); });
  const body = $("cmpBody");
  body.textContent = "";
  body.className = `cmp-body ${c.mode === "diff" ? "single" : ""} ${c.size}`;
  const v = c.which === "edited" ? state.pdfVer : 0;
  const dpi = c.size === "big" ? 170 : 110;
  const fig = (title, src) => {
    const f = el("figure");
    f.append(el("figcaption", null, title));
    const img = new Image();
    img.alt = title;
    img.onerror = async () => {
      let why = "불러오지 못했습니다";
      try { await api(src); } catch (e) { why = e.status === 404 ? `이 ${u}가 없습니다(${u} 수가 다름)` : `서버 연결 문제: ${e.message}`; }
      img.replaceWith(el("div", "pdf-note pad", why));
    };
    img.src = src;
    f.append(img);
    return f;
  };
  if (c.mode === "side") {
    body.append(fig(`원본 ${d.page}${u}`, `/api/docs/${state.id}/pdf/original/${d.page}.png?dpi=${dpi}&b=${state.base}`));
    body.append(fig(`${other} ${d.page}${u}`, `/api/docs/${state.id}/pdf/${c.which}/${d.page}.png?dpi=${dpi}&v=${v}`));
  } else {
    body.append(fig(`차이 ${d.page}${u}`, `/api/docs/${state.id}/diff/${c.which}/${d.page}.png?dpi=${dpi}&v=${v}`));
  }
  $("cmpLegend").hidden = c.mode !== "diff";
}

// ---------------------------------------------------------------- 확대
// state.fit: "width" 폭 맞춤 · "height" 높이 맞춤 · "body" 여백 빼고 맞춤 · null 손으로 정한 배율 — 맞춤이면 창 크기·쪽 나눔이 바뀔 때 다시 맞춘다
function setZoom(z, mode = null) {
  state.fit = mode;
  state.zoom = Math.min(3, Math.max(0.3, Math.round(z * 100) / 100));
  zoomApply();
  zoomPaint();
  peerViewSync(); // 두 면은 같은 크기(spec_작업 ② §12 「두 면」) — 둘째 면이 이 배율을 따른다
}

// ---- 배율은 쪽 상자마다 · 보이는 쪽부터 (spec_hwpx_웹편집 ② §2 「배율 — 쪽 상자마다 · 보이는 쪽부터」 — 2026-11-12 사용자 "서식 사이드 패널 뜨는데 너무 느림")
// CSS zoom 을 #doc 한 곳이 아니라 그 자식(쪽 상자 .sheet · 빈 쪽 표지 .gap-page)마다 같은 값으로 둔다. #doc 의 zoom 을 바꾸면 그 아래 전체의 스타일·배치를 한 번에 다시 해
// 204쪽 문서(요소 5.5만)에서 옆 열을 열고 닫을 때마다 1.5~2.1초 멈췄다. 쪽마다 두면 그린 결과는 같고(쪽·문단·칸·표지 자리 차이 0px 실측) 보기에 걸친 쪽만 바로(0.02초),
// 나머지는 뒤에서 조금씩 바꿀 수 있다. state.zoom = 목표 배율 — 바꾸는 동안에는 쪽마다 값이 다를 수 있어 쪽 배율은 전처럼 쪽마다 잰다(getBoundingClientRect().width / offsetWidth).
const DOC_GAP = 30, DOC_PAD_TOP = 6; // 쪽 사이 · #doc 위 여백(px, 배율 전) — style.css .doc 의 gap·padding-top 과 같아야 한다(#doc 자신은 배율이 없어 여기서 배율을 곱해 inline 으로 둔다 — 열 사이는 TWO_UP_GAP)
const ZOOM_ALL = 24;   // 바꿀 쪽 상자가 이 수 이하면 한 번에(작은 문서는 전과 같다)
const ZOOM_NEAR = 300; // 보기 위·아래 이만큼(화면 px)까지는 바로 바꾼다
const ZOOM_SLICE = 16; // 뒤에서 한 번에 쓰는 시간(ms)
const zoomJob = { on: false, timer: 0, carry: 0, dirty: false, at: null, until: 0, hint: null }; // on = 뒤에서 바꾸는 중 · dirty = 표시를 그린 뒤에 바꾼 쪽이 있다(끝나면 다시 그림) · at = 보는 쪽과 그 자리(zoomSeen)
// 문서(#scroller)를 「그 자리로」 옮기는 스크롤의 방식 — 배율을 뒤에서 바꾸는 중에는 바로("instant"). 부드러운 스크롤은 그동안의 자리 지키기(zoomStep·zoomCover 의 scrollTop 쓰기)가 끊어 가다 만다:
// 옆 열을 연 직후(쪽 맞춤 배율이 바뀜) 목록 줄을 누르면 강조는 붙는데 문서는 제자리였다. 바로 간 자리는 그 뒤의 자리 지키기가 그대로 둔다. 「그 자리로」 를 새로 만들 때 behavior 를 이것으로 준다
// (spec_hwpx_웹편집 ② §2 「배율 — 쪽 상자마다 · 보이는 쪽부터」 「그 자리로」)
const scrollHow = () => (zoomJob.on ? "instant" : "smooth");

function zoomPut(k, z) { // 쪽 상자 하나의 배율 → 바꿨으면 true
  const z0 = +k.style.zoom;
  if (z0 === z) return false;
  k.style.zoom = z;
  if (!z0) return true;
  // 그 쪽 여백의 표시(「TN Lk」·손잡이·표 표지 — zoom 1/z 로 화면 크기 고정, 자리·여백 폭은 화면 px)는 셈으로 맞춰 둔다: 크기 그대로 · 자리는 배율 비만큼.
  // 다시 그리기(tplMarksDraw·tblMarksDraw)는 문서 전체를 훑으므로 쪽마다 부르지 않는다 — 부르는 쪽이 바로 그리거나 다 끝난 뒤 한 번(zoomEnd)
  const r = z / z0;
  for (const m of k.children) {
    const mz = +m.style.zoom;
    if (!mz) continue;
    m.style.zoom = String(mz / r);
    const top = parseFloat(m.style.top), mgl = parseFloat(m.style.getPropertyValue("--mgl")), mgr = parseFloat(m.style.getPropertyValue("--mgr"));
    if (top === top) m.style.top = `${Math.round(top * r)}px`;
    if (mgl === mgl) m.style.setProperty("--mgl", `${Math.round(mgl * r * 10) / 10}px`);
    if (mgr === mgr) m.style.setProperty("--mgr", `${Math.round(mgr * r * 10) / 10}px`); // 오른쪽 여백 폭(화면 px — 편집 구역의 세로선 · 이름표 zones.js · 고친 곳 꼬리표 doc_diff.js · 서식 꼬리표 fmt_focus.js: 전에는 안 맞춰 늦게 배율을 바꾼 쪽에서 안쪽으로 밀렸다)
    if (m.dataset.span) { const h = parseFloat(m.style.height); if (h === h) m.style.height = `${Math.max(2, Math.round(h * r))}px`; } // 높이가 쪽 내용의 길이인 표시(편집 구역의 세로선)는 높이도 배율 비만큼
    if (m.dataset.top) m.dataset.top = String(Math.round(+m.dataset.top * r));
  }
  return true;
}

function zoomApply() { // state.zoom 을 쪽 상자들에 — 보기에 걸친 쪽은 지금, 나머지는 뒤에서(zoomStep)
  const doc = $("doc"), sc = $("scroller"), z = state.zoom, kids = [...doc.children];
  let pend = 0, widest = 0;
  for (const k of kids) if (+k.style.zoom !== z) pend += 1;
  const lazy = pend > ZOOM_ALL && !state.twoUp && !sc.hidden; // 2쪽 보기는 격자 열 폭이 쪽마다의 배율에 걸려 섞어 둘 수 없다
  if (lazy) for (const k of kids) if (k.classList.contains("sheet")) widest = Math.max(widest, k.offsetWidth); // 읽기 먼저(배율 전 px)
  const at = lazy ? zoomJob.hint || viewAnchor(sc, kids) : null; // 보던 자리도 쓰기 전에(keepCenter 가 적어 둔 것이 있으면 그것) — 쪽 사이 간격을 바꾸면 아래 쪽들이 그만큼 바로 밀린다(위에 쪽이 100개면 1,000px)
  if (doc.style.zoom) doc.style.zoom = ""; // 배율은 쪽 상자에만(#doc 에 남은 값이 있으면 걷는다)
  const gap = `${Math.round(DOC_GAP * z * 100) / 100}px`;
  if (doc.style.rowGap !== gap) {
    doc.style.rowGap = gap;
    doc.style.columnGap = `${Math.round(TWO_UP_GAP * z * 100) / 100}px`;
    doc.style.paddingTop = `${Math.round(DOC_PAD_TOP * z * 100) / 100}px`;
  }
  if (!pend) return;
  if (!lazy) { for (const k of kids) zoomPut(k, z); zoomEnd(zoomJob.dirty); return; } // 뒤에서 돌던 것이 있었으면 여기서 끝 — 미뤄 둔 표시 다시 그리기가 있으면 지금
  // 끝 폭이 보기에 들어가면 바꾸는 동안 가로 스크롤 막대를 숨긴다(아직 옛 배율인 넓은 쪽이 넘쳐 막대가 생겼다 없어지지 않게). #doc 폭은 묶지 않는다 — #doc 은 창 폭이고 넓은 쪽은
  // 넘칠 뿐 다른 쪽을 밀지 않는다(style.css .doc safe center — 2026-11-19). 전에는 #doc 이 max-content 라 끝 폭으로 묶었는데, 지금 묶으면 세로 쪽이 넓은 폭의 가운데로 밀렸다가 끝나면 돌아온다
  const cs = getComputedStyle(sc), avail = sc.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0);
  sc.style.overflowX = widest * z <= avail ? "hidden" : "";
  zoomJob.on = true;
  zoomJob.carry = 0;
  zoomCover(at);
  zoomJob.dirty = false; // 여기까지는 부르는 쪽이 이어서 표시를 다시 그린다
  zoomSeen();
  if (!zoomJob.timer) zoomJob.timer = setTimeout(zoomStep, 0);
}

function zoomCover(anchor = null) {
  // 보기에 걸친(위·아래 ZOOM_NEAR 여유) 쪽 가운데 아직 옛 배율인 것을 지금 바꾼다 → 바꾼 쪽 수. 창 가운데 자리(가운데 줄에 놓인 문단·칸의 그 높이 비율 — viewAnchor)는 그대로 둔다 —
  // 가운데 쪽과 그 위쪽 쪽은 크기가 바뀌면 아래를 밀므로 바꿀 때마다 그 점을 다시 가운데로. 쪽 하나를 바꾸고 자리를 읽으면 그 쪽만 다시 배치된다(다른 쪽은 그대로).
  // anchor = 부르는 쪽이 미리 적어 둔 자리(zoomApply — 쪽 사이 간격을 바꾸기 전의 것)
  if (!zoomJob.on) return 0;
  const sc = $("scroller"), z = state.zoom, kids = [...$("doc").children];
  if (!kids.length || sc.hidden) return 0;
  const o = sc.getBoundingClientRect();
  if (!anchor) {
    // 대개는 바꿀 것이 없다(뒤에서 도는 조각마다 · 스크롤마다 불린다) — 보던 자리 적기(viewAnchor 의 elementFromPoint 는 그리기 준비까지 강제해 한 번에 수십 ms)는 바꿀 쪽이 있을 때만
    let any = false;
    for (const k of kids) {
      const b = k.getBoundingClientRect();
      if (b.bottom < o.top - ZOOM_NEAR) continue;
      if (b.top > o.bottom + ZOOM_NEAR) break;
      if (+k.style.zoom !== z) { any = true; break; }
    }
    if (!any) return 0;
  }
  const at = anchor && anchor.el.isConnected ? anchor : viewAnchor(sc, kids), ci = Math.max(0, kids.indexOf(at.sheet));
  const hold = () => viewHold(sc, at);
  let n = 0, lo = ci, hi = ci;
  if (anchor) hold();
  if (zoomPut(kids[ci], z)) { n += 1; hold(); }
  for (let guard = 0; guard < 2 * kids.length; guard++) {
    let more = false;
    if (lo > 0 && kids[lo].getBoundingClientRect().top > o.top - ZOOM_NEAR) { lo -= 1; more = true; if (zoomPut(kids[lo], z)) { n += 1; hold(); } }
    if (hi < kids.length - 1 && kids[hi].getBoundingClientRect().bottom < o.bottom + ZOOM_NEAR) { hi += 1; more = true; if (zoomPut(kids[hi], z)) n += 1; }
    if (!more) break;
  }
  return n;
}

function zoomSeen() { // 지금 보는 쪽과 그 자리를 적어 둔다 — 다음 scroll 이 「자리 지키기」 때문인지(보이는 것은 안 움직임) 가리는 기준(zoomQuiet)
  const sc = $("scroller"), kids = [...$("doc").children];
  if (!kids.length || sc.hidden) { zoomJob.at = null; return; }
  const e = viewSheet(sc, kids);
  zoomJob.at = { el: e, top: e.getBoundingClientRect().top };
}

function zoomQuiet() { // 방금의 scroll 이 배율을 뒤에서 바꾸며 자리를 지킨 것뿐인가(보는 쪽이 화면에서 안 움직였다) — 그러면 오른쪽 단추 메뉴·도움말을 닫지 않는다
  const a = zoomJob.at;
  if (!a || !(zoomJob.on || performance.now() < zoomJob.until) || !a.el.isConnected) return false;
  return Math.abs(a.el.getBoundingClientRect().top - a.top) < 1.5;
}

function zoomStep() { // 뒤에서 — 아직 옛 배율인 쪽을 보는 쪽에서 가까운 차례로, 한 번에 ZOOM_SLICE ms 만(그 사이 입력·그리기가 끼어든다)
  zoomJob.timer = 0;
  if (!zoomJob.on) return;
  const sc = $("scroller"), z = state.zoom, kids = [...$("doc").children];
  if (sc.hidden || state.twoUp || !kids.length) { for (const k of kids) zoomPut(k, z); zoomEnd(zoomJob.dirty); return; } // 문서를 닫았거나 2쪽 보기로 바꿈 — 한 번에
  if (zoomCover()) zoomJob.dirty = true; // 그 사이 보기에 들어온 쪽 먼저
  const a = viewSheet(sc, kids), ai = kids.indexOf(a), rest = [];
  kids.forEach((k, i) => { if (+k.style.zoom !== z) rest.push(i); });
  if (!rest.length) { zoomEnd(zoomJob.dirty); return; }
  rest.sort((x, y) => Math.abs(x - ai) - Math.abs(y - ai));
  const t0 = performance.now();
  let top = a.getBoundingClientRect().top;
  for (const i of rest) {
    zoomPut(kids[i], z);
    const t = a.getBoundingClientRect().top; // 그 쪽의 배치를 지금 한다(걸린 시간을 잰다) · 위쪽 쪽이면 보는 쪽이 밀린 만큼 스크롤을 옮겨 보이는 것은 그대로
    if (t !== top) {
      zoomJob.carry += t - top; // scrollTop 은 정수 px — 남은 몫은 다음에 얹는다
      const mv = Math.round(zoomJob.carry);
      if (mv) { sc.scrollTop += mv; zoomJob.carry -= mv; }
      top = a.getBoundingClientRect().top;
    }
    if (performance.now() - t0 > ZOOM_SLICE) break;
  }
  zoomJob.dirty = true;
  zoomSeen();
  zoomJob.timer = setTimeout(zoomStep, 0);
}

function zoomMarksDraw() {
  // 배율이 바뀐 뒤의 쪽 여백 표시 다시 그리기(「TN Lk」·손잡이·표 표지 — 문서 전체를 훑는다: 204쪽 0.1초, 표시가 많으면 더). 배율을 뒤에서 바꾸는 중이면 끝날 때 한 번(zoomEnd)으로 미룬다 —
  // 그동안은 zoomPut 이 셈으로 맞춰 둔 것이 보인다(크기·자리는 맞고, 서로 비켜 서기만 끝난 뒤에)
  if (zoomJob.on) { zoomJob.dirty = true; return; }
  tplMarksDraw();
  if (typeof tblMarksDraw === "function") tblMarksDraw();
}

function zoomEnd(redraw) { // 다 바꿨다 — 묶어 둔 #doc 폭·가로 스크롤을 풀고, 표시를 그린 뒤에 바꾼 쪽이 있었으면 쪽 여백 표시를 한 번 다시 그린다(셈으로 맞춰 둔 것을 제대로)
  clearTimeout(zoomJob.timer);
  zoomJob.timer = 0;
  if (!zoomJob.on) return;
  zoomJob.on = zoomJob.dirty = false;
  zoomJob.until = performance.now() + 300; // 마지막 자리 지키기의 scroll 이 아직 안 왔을 수 있다
  $("doc").style.width = "";
  $("scroller").style.overflowX = "";
  if (redraw && state.id) { tplMarksDraw(); if (typeof tblMarksDraw === "function") tblMarksDraw(); }
}
function zoomPaint() { // 도구 줄의 배율 글·맞춤 단추를 이 문서의 상태(state.zoom·state.fit)로
  const mode = state.fit;
  $("zoomVal").textContent = `${Math.round(state.zoom * 100)}%`;
  const w = mode === "width", h = mode === "height" || mode === "body";
  $("zoomFit").setAttribute("aria-pressed", w);
  $("zoomFit").classList.toggle("on", w);
  $("zoomHeight").setAttribute("aria-pressed", h);
  $("zoomHeight").classList.toggle("on", h);
  // 단추는 아이콘뿐(2026-11-10) — 지금 방식은 아이콘(style.css #zoomHeight[data-mode])과 이름(도움말·aria-label)으로
  const hb = $("zoomHeight"), bodyFit = mode === "body";
  hb.dataset.mode = bodyFit ? "body" : "height";
  hb.setAttribute("aria-label", bodyFit ? "여백 빼고 맞춤" : "높이 맞춤");
  hb.title = bodyFit ? "여백 빼고 맞춤 — 위·아래 쪽 여백을 뺀 본문 높이를 창에 · 한 번 더 누르면 「높이 맞춤」"
    : "높이 맞춤 — 쪽 한 장이 창 높이에 다 들어가게 · 한 번 더 누르면 「여백 빼고 맞춤」";
}

function refit(align = false) {
  if (state.fit === "width") fitWidth();
  else if (state.fit) fitHeight(state.fit, align);
}

function viewAnchor(sc, kids, dy = 0) {
  // 창 가운데 줄(+dy)에 놓인 것과 그 안의 높이 비율 — 배율을 바꾼 뒤 그 점을 다시 가운데로(viewHold). 그 줄이 지나는 쪽 상자(없으면 가장 가까운 쪽)의 가로 가운데에서
  // 그 줄에 걸린 문단·칸을 고르고, 없으면(문단 사이·그림) 그 쪽 본문의 가장 가까운 블록, 그것도 없으면 쪽 상자. 쪽 상자만으로 잡으면 배율마다 줄 나눔이 달라 쪽 안의 비율이 조금씩 어긋난다.
  // dy = 보기 크기가 방금 바뀌었을 때 「바뀌기 전의 가운데」 가 지금 가운데에서 떨어진 거리(keepCenter)
  const o = sc.getBoundingClientRect(), y = o.top + o.height / 2 + dy;
  let sheet = kids[0], far = Infinity;
  for (const k of kids) {
    const b = k.getBoundingClientRect(), d = b.top <= y && y <= b.bottom ? 0 : Math.min(Math.abs(b.top - y), Math.abs(b.bottom - y));
    if (d < far) { far = d; sheet = k; }
    if (!d || b.top > y) break;
  }
  const sb = sheet.getBoundingClientRect();
  let e = null;
  if (sb.top <= y && y <= sb.bottom) {
    const hit = y > o.top && y < o.bottom ? document.elementFromPoint(Math.min(o.right - 4, Math.max(o.left + 4, (sb.left + sb.right) / 2)), y) : null;
    // 문단, 아니면 칸(td — 행(tr)으로 잡으면 안 된다: 세로로 합친 칸은 행 상자가 첫 줄 높이뿐이라 비율이 10 을 넘고, 그만큼 작은 높이 차이가 부풀어 열고 닫을 때마다 20px 씩 밀린다)
    e = hit && sheet.contains(hit) ? hit.closest(".para, td") : null;
    if (!e || !sheet.contains(e)) { // 문단 사이·그림 — 그 쪽 본문의 블록 가운데 그 줄에 가장 가까운 것
      const body = sheet.querySelector(":scope > .sheet-body");
      let gap = Infinity;
      for (const c of body ? body.children : []) {
        const b = c.getBoundingClientRect();
        if (!b.height) continue;
        const d = b.top <= y && y <= b.bottom ? 0 : Math.min(Math.abs(b.top - y), Math.abs(b.bottom - y));
        if (d < gap) { gap = d; e = c; }
        if (b.top > y) break; // 문서 차례 = 위에서 아래
      }
    }
  }
  if (!e || !sheet.contains(e)) e = sheet;
  const b = e.getBoundingClientRect();
  return { sheet, el: e, f: b.height ? (y - b.top) / b.height : 0 };
}
function viewHold(sc, at) { // viewAnchor 로 적어 둔 점을 창 가운데 줄에(그 요소가 문서에서 빠졌으면 그대로 둔다)
  if (!at.el.isConnected) return;
  const o = sc.getBoundingClientRect(), b = at.el.getBoundingClientRect(), d = b.top + at.f * b.height - (o.top + o.height / 2);
  if (Math.abs(d) >= 0.5) sc.scrollTop += d;
}

function keepCenter(fn, dy = 0) {
  // 배율을 바꿀 때 창 가운데 있던 자리를 그대로 둔다 — 가운데 줄에 놓인 문단·칸(없으면 가까운 블록·쪽 상자)과 그 안의 높이 비율을 적어 두었다가 그 점을 다시 가운데로.
  // (처음엔 문서 맨 위에서의 거리에 배율 비를 곱했다 — 배율을 보이는 쪽부터 바꾸면 위쪽 쪽들이 아직 옛 크기라 그 셈이 틀린다, 위 zoomApply)
  // dy = 보기 높이가 방금 바뀐 뒤에 부를 때(크기 감시) 「바뀌기 전의 가운데」 가 지금 가운데에서 떨어진 거리 = (옛 높이 − 새 높이) / 2. 옆 열을 열면 도구 줄이 두 줄로 꺾여 보기가 32px 줄어든다 —
  // 지금 가운데를 기준으로 삼으면 열 때 16px 위, 닫을 때 16px 아래의 것을 붙잡아 열고 닫을 때마다 보던 자리가 20px 씩 밀렸다(2026-11-12 실측 — 옛 셈도 같았다)
  const sc = $("scroller"), kids = sc.hidden ? [] : [...$("doc").children];
  if (!kids.length) { fn(); return; }
  const at = viewAnchor(sc, kids, dy);
  zoomJob.hint = at; // zoomApply 가 같은 자리를 기준으로 보이는 쪽을 고른다
  try { fn(); } finally { zoomJob.hint = null; }
  viewHold(sc, at);
  zoomCover(); // 가운데를 맞추느라 보기에 새로 들어온 쪽
}

// 2쪽 보기의 넓은 쪽(spec_hwpx_웹편집 ② §2 「2쪽 보기」 — 2026-11-18 사용자 「2페이지 보기면 최대한 가운데가 붙어 있고 … 왼쪽 공간을 최대한 줄여야지」): 격자의 열 폭은 그 열에서 가장 넓은
// 쪽 상자를 따른다 — 가로 구역이 하나라도 있으면(연구계획서 69쪽) 모든 줄의 세로 쪽이 가로 폭의 열 안에서 왼쪽에 붙어, 두 쪽 사이가 용지 폭의 0.4배만큼 벌어지고 오른쪽 쪽이 창 밖으로 밀렸다.
// 문서에서 가장 좁은 용지보다 넓은(10% 넘게) 구역의 쪽은 두 열을 통째로 쓰는 한 줄로 둔다(style.css .sheet.span2) — 열 폭 = 좁은 용지 폭이라 나란한 두 쪽이 늘 붙는다. -> Set(넓은 구역 번호)
function wideSecs() {
  const ws = state.sections.map((g) => (g || DEFAULT_PAGE).widthMm), base = Math.min(...ws);
  return new Set(ws.map((w, i) => (w > base * 1.1 ? i : -1)).filter((i) => i >= 0));
}

function fitWidth() {
  const sheets = document.querySelectorAll(".sheet");
  if (!sheets.length || $("scroller").hidden) return;
  // 쪽 폭은 배율 전 크기(offsetWidth — 쪽 상자의 CSS zoom 과 무관)로 잰다. 예전처럼 배율을 1 로 돌려 재면 그때마다 문서 전체(연구개발계획서 7,500문단·3.8만 요소)의
  // 스타일·배치를 두 번 다시 해서 열 접기·닫기 한 번에 1~1.5초 걸렸다(2026-11-10 사용자 "표구조 접거나 제거할때 엄청 느림"). 배율이 그대로면 setZoom 도 건너뛴다.
  let widest = 0, col = 0; // col = 2쪽 보기의 열에 드는 쪽(넓은 쪽 .span2 는 한 줄을 통째로 쓴다) 가운데 가장 넓은 것
  for (const s of sheets) { widest = Math.max(widest, s.offsetWidth); if (!s.classList.contains("span2")) col = Math.max(col, s.offsetWidth); }
  const need = state.twoUp ? Math.max(col * 2 + TWO_UP_GAP, widest) : widest; // 2쪽 보기 — 나란한 두 쪽과 사이 간격이 창 폭에(넓은 쪽 한 줄이 그보다 넓으면 그 폭)
  const sc = $("scroller"), cs = getComputedStyle(sc);
  const avail = sc.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0) - 12; // 좌우 padding + 여유 12
  const z = Math.min(1.25, avail / need);
  if (state.fit === "width" && Math.min(3, Math.max(0.3, Math.round(z * 100) / 100)) === state.zoom) return; // setZoom 과 같은 반올림
  setZoom(z, "width");
}

const PX_PER_MM = 96 / 25.4;
const TWO_UP_GAP = 8; // 2쪽 보기 두 쪽 사이(px, 배율 전) — style.css .doc.two-up 의 column-gap 과 같아야 한다(2026-11-18 사용자 「최대한 가운데가 붙어 있고」 — 전에는 24)

function fitHeight(mode, align = false) {
  // 높이 맞춤 = 지금 보는 쪽(창 가운데 줄이 지나는 쪽)의 웹 쪽 상자가 창 높이에 다 들어가게 · 여백 빼고 맞춤 = 그 상자에서 위·아래 쪽 여백을 뺀 높이를 창 높이에(여백은 창 밖).
  // 쪽 높이는 웹에 그려진 상자(종이보다 작으면 종이) — 웹은 문단 안에서 쪽을 나누지 않고(표 행은 매핑이 있으면 나눔 — 행 안 나눔) 표 행이 한글보다 높을 때가 있어 상자가 종이보다 길다
  // (연구개발계획서 양식 74쪽 중 22쪽, 1쪽 1.26배·11쪽 1.68배). 종이로 재면 그런 쪽은 창에 안 들어간다(2026-11-09 사용자 "안맞음"). 가장 긴 쪽으로 재면 모든 쪽이 작아져 지금 쪽.
  const sc = $("scroller");
  const sheets = [...document.querySelectorAll(".sheet")];
  if (!sheets.length || sc.hidden) return;
  const body = mode === "body";
  const geo = (s) => state.sections[+s.dataset.sec] || DEFAULT_PAGE;
  const view = viewSheet(sc, sheets), g = geo(view);
  const cur = align ? view : null;
  // 2쪽 보기면 같은 줄의 짝(위끝이 같은 쪽)까지 — 가운데 줄은 왼쪽 쪽을 고르는데 오른쪽이 더 길면 넘치므로 둘 중 긴 상자로 잰다
  const row = () => { const t = view.getBoundingClientRect().top; return state.twoUp ? sheets.filter((s) => Math.abs(s.getBoundingClientRect().top - t) < 2) : [view]; };
  // offsetHeight: 가로 스크롤 막대가 생겼다 없어져도 배율이 흔들리지 않게(막대 몫은 위·아래 남김에 둔다) — 위 24px 은 쪽 번호 자리
  const TOP = body ? 4 : 24, room = sc.offsetHeight - TOP - 24;
  // 상자 높이(offsetHeight — 배율 전 크기)가 배율 따라 조금 바뀐다(표 칸 글 줄 나눔 — 11쪽 67% 1871px · 75% 1924px). 맞춘 배율에서 다시 재어
  // 넘치면 더 낮춘다(올리지는 않음 — 오가지 않게). 내림 — 반올림하면 긴 쪽은 1% 에 19px 이 넘친다.
  let z = Infinity;
  for (let i = 0; i < 4; i++) {
    const sheetPx = Math.max(...row().map((s) => s.offsetHeight), g.heightMm * PX_PER_MM);
    const tallPx = body ? sheetPx - (g.marginsMm.t + g.marginsMm.b) * PX_PER_MM : sheetPx;
    const nz = Math.floor((room / tallPx) * 100) / 100;
    if (nz >= z) break;
    z = nz;
    setZoom(z, mode);
  }
  if (cur) {
    const lift = body ? geo(cur).marginsMm.t * PX_PER_MM * state.zoom : 0; // 여백 빼고: 위 여백을 창 위로 올려 본문 첫 줄이 창 맨 위에
    sc.scrollTop += cur.getBoundingClientRect().top + lift - sc.getBoundingClientRect().top - TOP;
  }
  zoomCover(); // 맞춘 자리의 보기에 새로 들어온 쪽(배율을 보이는 쪽부터 바꾸는 중이면)
}

function viewSheet(sc, sheets) {
  // 지금 보는 쪽 = 창 가운데 줄이 지나는 쪽(없으면 가장 가까운 쪽)
  const r = sc.getBoundingClientRect(), mid = r.top + r.height / 2;
  let best = sheets[0], gap = Infinity;
  for (const s of sheets) {
    const b = s.getBoundingClientRect();
    const d = b.top <= mid && mid <= b.bottom ? 0 : Math.min(Math.abs(b.top - mid), Math.abs(b.bottom - mid));
    if (d < gap) { gap = d; best = s; }
    if (!d) break;
  }
  return best;
}

// ---- 2쪽 보기 · 휠 쪽 넘김 (spec_hwpx_웹편집 ② §2 — 2026-11-09 사용자 "마우스 휠로 움직일때 페이지 넘김으로 … 한페이지씩 … 2페이지씩 보는 것도")
// 둘 다 이 브라우저에 기억(localStorage nfm.view — 못 쓰면 기본값: 2쪽 끔 · 휠 쪽 넘김 켬).
const VIEW_KEY = "nfm.view";

function viewPrefLoad() {
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) || "{}");
    if (typeof v.twoUp === "boolean") state.twoUp = v.twoUp;
    if (typeof v.wheelFlip === "boolean") state.wheelFlip = v.wheelFlip;
    if (TOOL_SETS.includes(v.tool)) state.tool = v.tool;
  } catch { /* 기본값 */ }
}

function viewPrefSave() {
  if (PEEK) return; // 둘째 면 화면은 기억을 안 쓴다 — 저장소가 바깥과 같아 바깥 설정이 바뀐다(도구 줄이 둘째 면의 2쪽·휠 넘김도 바꾸므로)
  try { localStorage.setItem(VIEW_KEY, JSON.stringify({ twoUp: state.twoUp, wheelFlip: state.wheelFlip, tool: state.tool })); } catch { /* 기억만 안 함 */ }
}

// ---- 도구 줄 한 줄 (spec_hwpx_웹편집 ② §2 「도구 줄」 — 2026-11-10 사용자 "2줄 중 상단의 줄을 … 체크 하면 그것만 하나의 줄에 보이게")
// 「페이지 보기·폰트 수정·문단 수정·테이블 수정」 단추 중 하나만 켜지고(.tool-modes), 그 묶음(.tool-set[data-tool-set])만 펼친다. 고른 묶음은 nfm.view 에 기억(기본 페이지 보기).
const TOOL_SETS = ["page", "font", "para", "table", "style"]; // style = 「서식」 묶음(spec_서식복사 ② §3 — 서식 관리자 · 이 문서에서 복사 · 파일에서 복사: 단추는 style_lib.js 가 잇는다)

function toolSetShow(name) { // 그 묶음만 펼친다 — state.tool·기억은 안 건드린다(setToolSet 이 부른다)
  const bar = $("docBar");
  for (const s of bar.querySelectorAll(".tool-set")) s.hidden = s.dataset.toolSet !== name;
  for (const s of bar.querySelectorAll("[data-tool-for]")) s.hidden = s.dataset.toolFor !== name; // 묶음 밖에 둔 딸림 항목(확대·쪽 번호 …)
  for (const b of document.querySelectorAll("#toolModes [data-tool]")) {
    const on = b.dataset.tool === name;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", String(on));
  }
}

function setToolSet(name) {
  state.tool = TOOL_SETS.includes(name) ? name : "page";
  toolSetShow(state.tool);
  viewPrefSave(); // 좁은 창에서 묶음에 따라 줄이 꺾여 문서 보기 높이가 바뀌면 맞춤 배율은 #scroller ResizeObserver(bind 끝)가 다시 잰다
}

function setTwoUp(on) {
  // 2쪽 보기 — #doc 을 두 열 격자로(style.css .two-up). 맞춤 배율은 다시 맞추고(폭 맞춤은 두 쪽 폭으로) 보던 쪽을 창 맨 위에 둔다
  state.twoUp = !!on;
  $("doc").classList.toggle("two-up", state.twoUp);
  const b = $("twoUp");
  b.setAttribute("aria-pressed", state.twoUp);
  b.classList.toggle("on", state.twoUp);
  viewPrefSave();
  peerViewSync(); // 둘째 면도 2쪽 보기로(spec_작업 ② §12 「두 면」) — 배율이 바뀌면 setZoom 이 한 번 더 알린다
  const sc = $("scroller"), sheets = [...document.querySelectorAll(".sheet")];
  if (!state.id || sc.hidden || !sheets.length) return;
  const cur = viewSheet(sc, sheets);
  refit();
  sc.scrollTop += cur.getBoundingClientRect().top - sc.getBoundingClientRect().top - 24;
  if (heads.marks || heads.outline) tplMarksDraw(); // 배율이 바뀌었다 — 템플릿 표시의 화면 크기(zoom 1/z)·쪽 여백 폭(--mgl)을 다시
  if (typeof tblMarksDraw === "function") tblMarksDraw(); // 표 표지도 같이(tables.js)
}

function setWheelFlip(on) {
  state.wheelFlip = !!on;
  $("wheelFlip").checked = state.wheelFlip;
  viewPrefSave();
  peerViewSync(); // 둘째 면도 같이(spec_작업 ② §12 「두 면」)
}

function flipRows(sc) {
  // 쪽 줄 — 위끝이 같은 상자(2쪽 보기면 나란한 두 쪽)끼리 한 줄. 좌표는 스크롤 좌표(scrollTop 기준). lift = 위 쪽 여백(여백 빼고 맞춤 때 본문 첫 줄 자리)
  const base = sc.getBoundingClientRect().top - sc.scrollTop;
  const rows = [];
  for (const b of document.querySelectorAll("#doc .sheet, #doc .gap-page")) {
    const r = b.getBoundingClientRect(), top = r.top - base, bottom = r.bottom - base;
    const last = rows[rows.length - 1];
    if (last && Math.abs(last.top - top) < 2) last.bottom = Math.max(last.bottom, bottom);
    else {
      const g = b.classList.contains("sheet") ? state.sections[+b.dataset.sec] || DEFAULT_PAGE : null;
      rows.push({ top, bottom, lift: g ? g.marginsMm.t * PX_PER_MM * state.zoom : 0 });
    }
  }
  return rows;
}

let flip = { at: 0, to: null }; // 마지막 넘김 — 부드러운 스크롤이 끝나기 전에 또 넘기면 목표 자리를 기준으로 잇는다

function flipPage(dir) {
  // 휠 한 칸 = 한 줄(쪽): 쪽 위끝을 창 맨 위(쪽 번호 자리 아래)에, 「여백 빼고 맞춤」이면 본문 첫 줄을 창 맨 위에(fitHeight 와 같은 자리).
  // 줄이 창보다 길면 그 안에서 창 높이만큼 먼저 움직이고 끝에 닿으면 넘긴다(거꾸로 올라갈 때 긴 줄은 아래끝부터).
  const sc = $("scroller"), rows = flipRows(sc);
  if (!rows.length) return;
  const body = state.fit === "body", TOP = body ? 4 : 24, h = sc.clientHeight, step = Math.max(40, h - 60);
  const start = (r) => Math.round(r.top + (body ? r.lift : 0) - TOP); // 줄 위끝이 창 위에 오는 scrollTop
  const end = (r) => Math.round(r.bottom + 24 - h); // 줄 아래끝이 창 아래에 오는 scrollTop(짧은 줄이면 start 보다 작다)
  // 남은 부분이 이만큼보다 작으면 줄 안에서 몇 px 만 밀지 않고 바로 넘긴다 — 맞춘 쪽과 높이가 거의 같은 쪽이 휠 한 칸을 3px 에 쓰던 것
  const SLACK = Math.max(48, h * 0.15);
  const now = performance.now();
  const y = flip.to != null && now - flip.at < 600 ? flip.to : sc.scrollTop;
  let i = -1; // 지금 줄 = 위끝이 창 위(또는 그 조금 아래 SLACK 안)에 온 마지막 줄 · −1 = 첫 줄보다 훨씬 위
  for (let k = 0; k < rows.length; k++) if (start(rows[k]) <= y + SLACK) i = k; else break;
  let to;
  if (dir > 0) {
    if (i >= 0 && end(rows[i]) > y + SLACK) to = Math.min(y + step, end(rows[i])); // 긴 줄 안에서 내려감
    else if (i + 1 < rows.length) to = start(rows[i + 1]);
    else to = sc.scrollHeight - h;
  } else if (i >= 0 && start(rows[i]) < y - SLACK) to = Math.max(y - step, start(rows[i])); // 줄 안에서 올라감(줄 위끝까지)
  else {
    // 앞 줄 — 창보다 길면 그 아래끝부터. 그 자리가 지금 자리보다 위가 아니면 한 줄 더 앞으로: 빈 쪽 표지(gap-page)는 SLACK 보다 짧아 거기 서 있으면 다음 쪽이
    // 「지금 줄」 로 잡히고(위 y + SLACK) 앞 줄 = 서 있는 그 표지라 제자리였다(2026-11-12 사용자 "휠이 더이상 위로 올라가지 않음")
    to = 0;
    for (let k = i - 1; k >= 0; k--) {
      const s = start(rows[k]), e = end(rows[k]), t = e - s > SLACK ? e : s;
      if (t < y - 4) { to = t; break; }
    }
  }
  to = Math.max(0, Math.min(sc.scrollHeight - h, Math.round(to)));
  flip = { at: now, to };
  sc.scrollTo({ top: to, behavior: scrollHow() });
}

function bindWheelFlip() {
  const sc = $("scroller");
  let acc = 0, lastEvt = 0, lastFlip = 0, locked = false;
  sc.addEventListener("wheel", (e) => {
    if (typeof fmNavWheel === "function" && fmNavWheel(e)) return; // 서식·템플릿만 또렷이가 켜진 동안은 쪽 대신 다음·앞 자리로(fmt_focus.js 「자리 옮기기」 — spec_헤딩_추출 ② §7)
    if (!state.wheelFlip || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return; // Ctrl+휠 확대 · Shift+휠 가로는 브라우저대로
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return; // 가로 휠은 그대로
    e.preventDefault();
    const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? sc.clientHeight : 1);
    const now = performance.now(), pause = now - lastEvt;
    lastEvt = now;
    if (Math.abs(dy) >= 50) { // 마우스 휠 한 칸(Chrome 100px) — 칸마다 한 쪽, 80ms 에 한 번까지
      acc = 0;
      locked = true; // 칸 뒤에 따라오는 작은 관성 값은 버림
      if (now - lastFlip >= 80) { lastFlip = now; flipPage(dy > 0 ? 1 : -1); }
      return;
    }
    if (pause > 150) { acc = 0; locked = false; } // 트랙패드 — 손짓이 끊겼다 다시 시작
    if (locked) return;
    acc += dy;
    if (Math.abs(acc) >= 60) { locked = true; lastFlip = now; flipPage(acc > 0 ? 1 : -1); acc = 0; } // 손짓 하나에 한 쪽
  }, { passive: false });
}

// ---------------------------------------------------------------- 저장
async function download() {
  await flushAll();
  if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있습니다 — 「고친 문단」 탭에서 다시 반영하세요", true); return; }
  const rev = state.localRev, epoch = state.epoch, btn = $("downloadBtn");
  btn.disabled = true;
  setSaveState("busy", `${EXT()} 만드는 중…`);
  try {
    const r = await fetch(`/api/docs/${state.id}/download`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
    const blob = await r.blob();
    if (epoch !== state.epoch) return;
    const cd = r.headers.get("content-disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const name = m ? decodeURIComponent(m[1]) : state.name;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    state.downloadedRev = rev;
    state.downloadedAt = new Date();
    logTouched();
    toast(r.headers.get("x-same-as-original") === "1" ? `「${name}」 — ${state.base ? `확정 ${state.base}` : "원본"}과 바이트가 같은 파일입니다` : `「${name}」 내려받기를 요청했습니다(${fmtSize(blob.size)})`);
  } catch (e) {
    toast(`${EXT()} 를 만들지 못했습니다: ${e.message}`, true);
  } finally {
    btn.disabled = false;
    refreshSaveState();
  }
}

// ---- 헤딩 추출(spec_헤딩_추출 ② §7)
// 패널 탭 「헤딩 추출」 — 통과/실패 판정이 아니라 분석. 탭을 열면 1단계(스크립트, 1~2 s)를 자동으로 돌리고, 작업이 도는 동안 1초마다
// 상태를 읽는다(검증 poll 과 따로). 큰 표(문단 목록·서식 라벨·규칙·지침)는 문서와 패널 사이 2열 #headsDlg 하나를 바꿔 쓴다(팝업 아님 — 문서와
// 나란히 보며 문단으로 찾아감 · 옛 대화창이라 id 는 그대로). 문서 글은 모두 textContent 로.
const H_KIND = { marker: "레터", label: "괄호 표기", note: "안내(※)", footnote: "각주(*)", data: "값", placeholder: "자리표시", plain: "보통 글",
  empty: "빈 문단", object: "개체", toc: "목차", caption: "캡션", band: "별첨·부록 표 제목" };
const H_AREA = { body: "본문", cell: "표 칸", box: "글상자", shape: "도형 글", caption: "캡션", header: "머리말", footer: "꼬리말", footnote: "각주", endnote: "미주" };
const H_VERDICT = { saved: "저장", rejected: "거절", kept: "그대로", unsure: "모름", duplicate: "중복" };
const H_STEP = { running: "run", ok: "ok", failed: "fail" };
const H_JOB = { running: "진행 중", done: "끝남", failed: "실패" };
const H_ROLE = { label: "구분 라벨", subtitle: "괄호 소제목", title: "제목", note: "안내" }; // 구분 라벨 = 구분 기준(단계·차년도·기관 …) 값이 든 괄호 줄, 그 밖의 괄호 줄 = 괄호 소제목
const H_TPL = { main: "주 사슬", branch: "가지 템플릿", label: "구분 라벨 템플릿", sub: "서브 템플릿", cell: "표 칸", band: "별첨·부록 표 제목 템플릿(「별첨N | 제목」 처럼 이름 칸 + 제목 칸으로 된 표)" }; // band = 코드·사양서의 「띠 표 템플릿」(spec_헤딩_추출 ② §6 「띠 표 줄」) — 화면에는 그 말을 쓰지 않는다
const H_ROOT = { label: " · 뿌리 = 구분 라벨", subtitle: " · 뿌리 = 괄호 소제목" }; // 템플릿 rootRole → 설명 글
const isRooted = (role) => role === "label" || role === "subtitle"; // 괄호 줄 — 그 줄부터 새 템플릿(L1), 개요 편집은 Enter 만
const H_DECISION = { adjust: "조정", keep: "다름 유지", undecided: "미판정" };
const H_STATUS = { candidate: "후보", global: "전역" };
const H_TROLE = { colhead: "열헤더", rowhead: "행헤더", corner: "귀퉁이", field: "필드", title: "제목", note: "안내", spacer: "간격" }; // 3단계 표 구조(spec ② §8)
const H_TKIND = { matrix: "매트릭스", form: "키-값", list: "한 열", title: "제목", note: "안내", spacer: "간격", plain: "헤더 없음" };
const H_BASIS = { stage: "단계", year: "차년도", org: "기관", period: "연도", total: "합계", ratio: "비율" }; // 표 의미(spec ② §9) 구분 헤더
const H_FSTAT = { ok: "일치", mismatch: "불일치", missing: "미기입", incomplete: "미검증(일부 빈 칸)", blank: "미검증(빈 칸)", nonnumeric: "수가 아님" };
const colLetter = (c) => { let s = ""; c += 1; while (c) { const r = (c - 1) % 26; s = String.fromCharCode(65 + r) + s; c = Math.floor((c - 1) / 26); } return s; };
const basisNames = (bs) => (bs || []).filter((b) => H_BASIS[b]).map((b) => H_BASIS[b]).join("·");
const ownerLabel = (o) => (!o ? "" : o.root ? "(문서 뿌리)" : `${o.text || "(제목 없음)"}${o.tplNo ? ` · T${o.tplNo} L${o.level}` : ""}${o.source === "stage1" ? " · 어림" : ""}`);
const H_JSON = { "Content-Type": "application/json" };
const nf = (v) => (v == null ? "–" : Number(v).toLocaleString("ko-KR"));
const hasBlock = (id) => /^p/.test(id || ""); // 웹 블록이 있는 문단 — x<구역>.<순번> 레코드는 화면에 없음
const llmName = (st) => (/opus-5-5/.test(st.model || "") ? `Claude Opus 5.5(${st.model})` : st.model || "LLM");
const headsFresh = () => ({ view: null, autoRev: null, pollEpoch: null, expect: null, moreKey: null, graphKey: null, tablesKey: null, dlg: null, seq: 0,
  paras: { kind: "", area: "", rule: "", fmt: "", q: "", offset: 0 }, rules: null, guide: null, guideName: "rules", gEl: null, marks: null, outline: null, drag: null,
  resultView: "Tree", graph: null,
  runStage: null, jobSeen: null, nowEl: null, // 추출·설정의 고른 단계 탭 · 마지막으로 본 작업(started) · 요약 줄의 「지금 하는 일」 꼬리표(② §7 「단계 탭」·「진행 표시」)
  xl: { open: new Set(), col: null, store: null, storeKey: null, agent: null, saveTimer: null, saving: new Map() }, // 표 도구(spec ② §10) — 문서 자리 격자(open) · 2열 격자(col) · 저장된 지침/수식 · 지침 열
  tbl: { key: null, data: null, id: null } }); // tbl = 3단계 표 보기(2열)의 읽어 둔 결과 · 고른 표
let heads = headsFresh();

function headsReset() { // 문서를 열거나 닫을 때(load·closeDoc) — 늦게 온 응답은 epoch 로 버린다
  heads = headsFresh();
  $("tabHeads").hidden = !state.id || state.format === "docx"; // 지금은 hwpx 만(spec ④)
  for (const id of ["headsPersist", "heads1", "heads1Job", "heads1More", "heads2", "heads2Job", "heads2More", "heads3", "heads3Job", "heads3More",
    "headsOverview", "headsLabelsResult", "headsTemplatesResult", "headsTablesResult", "headsReviewResult", "headsAdjustResult"]) $(id).textContent = "";
  $("headsPersist").hidden = true;
  headsColClose(true);
  headsResultView("Tree");
  headsStageShow(1);
  if (typeof tempReset === "function") tempReset(); // TEMP 라벨(heading_temp.js — spec_헤딩_추출 ② §15)
  if (typeof driftReset === "function") driftReset(); // 뼈대 유지(heading_drift.js — spec_헤딩_추출 ② §17)
  if (typeof fmtFocusReset === "function") fmtFocusReset(); // 서식 라벨만 또렷이(fmt_focus.js — 다른 문서로 가면 풀린다: #doc 의 표시 클래스가 남으면 새 문서가 통째로 흐리다)
  if (typeof ddReset === "function") ddReset(); // 고친 곳 보기(doc_diff.js — 지켜보던 문단·글자 표시·꼬리표를 버린다)
  tplMarksDraw();
}

function hBtn(text, fn, { disabled = false, title = "", cls = "btn sm" } = {}) {
  const b = el("button", cls, text);
  b.type = "button";
  b.disabled = disabled;
  if (title) b.title = title;
  b.onclick = fn;
  return b;
}

async function headsShow() {
  if (!state.id || state.format === "docx") return;
  const id = state.id, epoch = state.epoch;
  let r;
  try { r = await api(`/api/docs/${id}/headings`); }
  catch (e) { if (epoch === state.epoch) headsFailed(e); return; }
  if (epoch !== state.epoch) return;
  headsRender(r);
  if (r.job && r.job.status === "running") headsPoll();
  else if ((!r.stage1 || r.stage1.stale) && heads.autoRev !== r.rev) { // 결과가 없거나 문서가 바뀜 — 문서 차례마다 한 번만 자동으로(스크립트만)
    heads.autoRev = r.rev;
    headsStart(1, false);
  }
}

function headsFailed(e) {
  const box = $("heads1");
  box.textContent = "";
  box.append(el("p", "hwarn fail", `헤딩 추출 상태를 읽지 못했습니다: ${e.message}`), hBtn("다시 읽기", () => headsShow()));
  $("headsOverview").replaceChildren(el("p", "hwarn fail", `분석 상태를 읽지 못했습니다: ${e.message}`), hBtn("다시 읽기", () => headsShow()));
}

async function headsStart(stage, useLlm) { // → 시작한 작업 | null(못 시작함 · 그 사이 다른 문서) — 고른 단계를 차례로 돌리는 「단계별 실행」(heads_run_pick.js)이 그 작업이 끝나기를 기다린다
  if (!state.id) return null;
  const id = state.id, epoch = state.epoch;
  let started = null;
  await flushAll(); // 아직 반영 안 된 글부터 — 추출은 서버 문서를 읽는다
  if (epoch !== state.epoch) return null;
  try {
    const skill = stage === 2 && useLlm && typeof tpaSkillKey === "function" ? { skill: tpaSkillKey() } : {}; // 헤딩 그래프(LLM)는 서식 정리 계획까지 이어 받는다 — 그 스킬(tpl_agent.js)
    const job = await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ stage, llm: useLlm, ...skill }) });
    if (epoch !== state.epoch) return null;
    heads.expect = job.started; // 이보다 앞선 작업의 늦은 응답은 건너뛴다
    headsRender({ ...(heads.view || { rev: state.serverRev, runs: [], stage1: null, stage2: null, stage3: null }), job });
    started = job;
  } catch (e) {
    if (epoch !== state.epoch) return null;
    toast(e.status === 409 ? "헤딩 추출이 이미 돌고 있습니다 — 끝난 뒤 다시 누르세요" : `헤딩 추출을 시작하지 못했습니다: ${e.message}`, e.status !== 409);
  }
  headsPoll();
  return started;
}

// 첫 분석(spec_작업 ② §9, 2026-11-10 사용자) — 새 작업을 처음 열었을 때 한 번(opened: 올리기·예제 열기 응답이 reused 가 아닐 때): 헤딩 2단계 → 3단계(스크립트만 — 서버가 한 작업으로,
// 이미 결과가 있는 단계는 건너뜀)를 시작한다 — **어느 TASK 든 같다**(기본 분석). 이어 연 작업·작업 목록·주소로 연 작업에서는 안 돈다. 실패는 알림 없이 콘솔에(이름 줄의 분석 상태에 「없음」·「실패」 + 「분석」 단추로 보인다).
// 2026-11-15(② §20 — 사용자 "구분 기준은 옵션" · 답 「저절로 안 돌림」): 구분 기준 LLM 검토(divReview(true))는 여기서 **부르지 않는다** — 올릴 때 유료 호출 없음. 사람이 단추로(이름 줄 「구분 기준」 표시 → 검토 결과 열의 「LLM 검토 실행」).
// 어디까지 됐는지는 문서 이름 줄이 보인다(doc_status.js — 헤딩 · 표 · LLM · 구분 기준).
function firstRun() {
  if (!state.id) return;
  if (state.format !== "docx") { headsFirst(); toast("첫 분석 — 헤딩 그래프·표 구조를 만드는 중(스크립트)"); }
}

async function headsFirst() { // 헤딩 탭을 열지 않아도 결과·쪽 여백 표시·개요 편집 키가 생긴다 — 끝날 때까지 headsPoll 이 읽어 headsRender(→ headsMore2 → outlineLoad)
  if (!state.id || state.format === "docx") return;
  const id = state.id, epoch = state.epoch;
  heads.autoRev = state.serverRev; // POST 를 보내기 전에 — 그 사이 누가 headsShow 를 불러도(탭 열기 등) 1단계 자동 실행이 먼저 끼어들어 첫 분석이 409 로 밀리지 않게. 이 편집 차례는 첫 분석이 뽑는다
  try {
    const job = await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) });
    if (epoch !== state.epoch) return;
    heads.expect = job.started;
    headsRender({ ...(heads.view || { rev: state.serverRev, runs: [], stage1: null, stage2: null, stage3: null }), job });
  } catch (e) {
    if (epoch === state.epoch) { heads.autoRev = null; console.warn("첫 분석(헤딩)을 시작하지 못했습니다:", e.message); } // 못 돌렸으면 탭을 열 때의 자동 실행에 맡긴다
    return;
  }
  headsPoll();
}

async function headsPoll() {
  if (!state.id || heads.pollEpoch === state.epoch) return;
  const id = state.id, epoch = state.epoch;
  heads.pollEpoch = epoch;
  try {
    for (;;) {
      const sent = heads.expect; // 보낼 때 기대값 — 지금과 같으면 이 GET 은 POST 응답을 받은 뒤에 보낸 것
      const r = await api(`/api/docs/${id}/headings`);
      if (epoch !== state.epoch) break;
      // 앞선 작업의 늦은 응답은 건너뜀: 앞선 작업이거나, POST 전에 보낸 GET 의 「작업 없음」. POST 뒤에 보낸 GET 이 작업 없음이면
      // 서버가 세션을 잃은 것(재시작·밀려남) — 기다려도 안 오니 그대로 그리고 끝낸다
      const old = heads.expect && (r.job ? r.job.started < heads.expect : sent !== heads.expect);
      if (!old) {
        heads.expect = null;
        headsRender(r);
        if (!(r.job && r.job.status === "running")) { logTouched(); break; } // 끝남 — 기록 탭에 새 줄
      }
      await new Promise((res) => setTimeout(res, 1000));
      if (epoch !== state.epoch) break;
    }
  } catch (e) {
    if (epoch === state.epoch) headsFailed(e);
  } finally {
    if (heads.pollEpoch === epoch) heads.pollEpoch = null;
  }
}

function headsRender(r) {
  heads.view = r;
  if (typeof docStatusPing === "function") docStatusPing(); // 이름 줄의 분석 상태도 다시 읽는다(doc_status.js — 헤딩 작업의 시작·끝)
  const pe = $("headsPersist");
  pe.textContent = r.persistError || "";
  pe.hidden = !r.persistError;
  const job = r.job, busy = !!(job && job.status === "running");
  headsCard1(r, busy);
  headsCard2(r, busy);
  headsCard3(r, busy);
  for (const k of [1, 2, 3]) {
    const box = $(`heads${k}Job`);
    box.textContent = "";
    if (job && job.stage === k) box.append(headsJob(job, r));
  }
  headsStageSync(r); // 단계 탭 — 고른 단계 · 탭마다 도는 중/오래됨 표시
  if (typeof zonesHeadsSeen === "function") zonesHeadsSeen([r.stage2, r.stage3].map((s) => (s && s.meta ? `${s.meta.run}|${s.meta.at}` : "")).join("#")); // 편집 구역(zones.js) — 헤딩 그래프(윗 제목)·표 구조(표의 머리)가 바뀌면 구역도 다시 읽는다
  divHeadsSeen(r.stage3 && r.stage3.meta ? `${r.stage3.meta.run}|${r.stage3.meta.at}` : ""); // 구분 기준 자리 표시 — 표 구조가 바뀌면 다시 읽는다(같은 rev 에서 끝나도: spec_구분_기준 ② §25)
  headsMore1(r);
  headsMore2(r);
  headsMore3(r);
  headsResultsSummary(r);
  headsNowDraw(r); // 요약 줄의 「지금 하는 일 · 지난 시간」 — 읽을 때마다(요약은 바뀔 때만 다시 그린다)
  if (typeof tblMarksDraw === "function") tblMarksDraw(); // 표 식별 표지(소속)는 3단계 결과를 따라간다(spec ② §10)
  if (typeof tempSync === "function") tempSync(r); // TEMP 라벨이 바뀌었으면 다시 읽어 문서 표시·목록을 맞춘다(heading_temp.js — spec ② §15)
  if (typeof driftSync === "function") driftSync(r); // 뼈대 유지 — 결과·문서 차례가 달라졌으면 지금 문서를 뼈대와 다시 견준다(heading_drift.js — spec ② §17)
}

// ---- LLM 표시(spec_헤딩_추출 ② §7 「LLM 표시」, 2026-11-10 사용자 "LLM 이 작업한 결과 임을 표시 … 각 자리에서 LLM 작업 시간을 명시")
// 2·3단계의 지금 결과가 LLM 이 판정한 것인지 스크립트 것인지, LLM 이면 끝난 때·걸린 시간을 결과가 보이는 자리마다 같은 꼬리표(.src-chip)로:
// 헤딩 탭 위 요약 · 「표」 탭 · 2열 「템플릿 관계」·「표 구조」 · 추출·설정 카드 머리(걸린 시간). 자료는 GET …/headings 요약의 stageN {meta.at, llm{requested, fallback, calls, seconds, costUsd, replay}}.
const fmtDur = (s) => { s = Math.round(s || 0); return s < 60 ? `${s}초` : `${Math.floor(s / 60)}분${s % 60 ? ` ${s % 60}초` : ""}`; };
const H_STAGE_NAME = { 2: "헤딩 그래프", 3: "표 구조" };
function headsSource(r, k) { // k = 2|3 → null(결과 없음) | {llm, at, seconds, text, title}
  const s = r && r[`stage${k}`];
  if (!s) return null;
  const lm = s.llm || {}, meta = s.meta || {}, rep = lm.replay || null; // replay = 2단계 「다시 셈」 — 앞 LLM 실행의 판정을 이어 씀(새 호출 없음)
  const llm = !!rep || (!!lm.requested && !lm.fallback && !!lm.calls);
  const run = `실행 ${meta.run ?? "–"}`, stale = s.stale ? " · 만든 뒤 문서가 바뀜(뼈대는 그대로 씀)" : ""; // 문서가 바뀌어도 다시 만들라고 하지 않는다(② §17 뼈대 유지)
  if (rep) {
    const n = meta.base ?? rep.from, base = (r.runs || []).find((x) => x.n === n), when = base ? fmtWhen(base.at) : "";
    return { llm, at: base ? base.at : null, seconds: null, text: `LLM ${when} · 실행 ${n} 판정 이어 씀`.replace("  ", " "),
      title: `LLM 실행 ${n}${when ? `(${when})` : ""}의 판정을 이어 쓴 결과 — 구분 라벨·TEMP 지정을 반영해 다시 셈한 ${run}(${fmtWhen(meta.at)}) · 새 LLM 호출 없음${stale}` };
  }
  if (llm) {
    const dur = lm.seconds ? fmtDur(lm.seconds) : "";
    return { llm, at: meta.at, seconds: lm.seconds || null, text: `LLM ${fmtWhen(meta.at)}${dur ? ` · ${dur}` : ""}`,
      title: `LLM 이 판정한 결과 — ${run} · ${fmtWhen(meta.at)} 에 끝남${dur ? ` · ${dur} 걸림` : ""} · 호출 ${nf(lm.calls)}번(실패 ${nf(lm.failed || 0)})${lm.costUsd ? ` · $${lm.costUsd}` : ""}${stale}` };
  }
  return { llm, at: meta.at, seconds: null, text: `스크립트 ${fmtWhen(meta.at)}`,
    title: `LLM 없이 스크립트가 만든 결과 — ${run} · ${fmtWhen(meta.at)}${lm.requested ? (lm.fallback ? " · LLM 을 불렀지만 실패해 스크립트 대체 판정" : " · LLM 에 보낼 것이 없어 초안 그대로") : ""}${stale}` };
}
function headsSourceChip(r, k, named = true) { // 꼬리표 하나 — named 면 앞에 단계 이름(「헤딩 그래프」·「표 구조」)
  const i = headsSource(r, k);
  if (!i) return null;
  const c = el("span", `src-chip ${i.llm ? "llm" : "script"}`);
  if (named) c.append(el("b", null, H_STAGE_NAME[k]));
  const t = el("span"), cut = i.text.indexOf("오늘 "); // 「오늘 」 만 따로 싼다 — 좁은 패널의 요약 줄에서는 감춰(시각만) 꼬리표 둘을 한 줄에 넣는다(heading-panels.css @container)
  if (cut < 0) t.textContent = i.text;
  else t.append(i.text.slice(0, cut), el("i", "today", "오늘 "), i.text.slice(cut + 3));
  c.append(t);
  c.title = i.title;
  return c;
}
function headsSourceLine(r, ks = [2, 3]) { // 꼬리표 줄 — 결과가 하나도 없으면 null
  const chips = ks.map((k) => headsSourceChip(r, k)).filter(Boolean);
  if (!chips.length) return null;
  const line = el("div", "src-line");
  line.append(...chips);
  return line;
}

// ---- 진행 줄(spec_헤딩_추출 ② §7 「진행 줄」, 2026-11-16 사용자 "스크립트 추출 완료, 그리고 LLM 규칙 보강 이 있어야지 … 추출/설정 안에 들어 있으니깐 어디 까지 작업을 했는지 알 수 없잖아")
// 헤딩 탭 위 요약의 둘째 줄(전의 LLM 꼬리표 줄 자리) — 분석을 두 층 × 세 단계로: 스크립트(문단·라벨 · 헤딩 그래프 · 표 구조) / LLM(규칙 보강 · 헤딩 판정 · 표 판정).
// LLM 칸은 그 아래 스크립트 칸의 단계에 붙는다(규칙 보강 = 1단계 · 헤딩 판정 = 2단계 · 표 판정 = 3단계). 칸마다 표시(✓·○·돌아가는 동그라미·!·–) + 짧은 글, 누르면 추출·설정의 그 단계 탭.
// 실행 번호·시각·수는 title. LLM 판정의 기준은 「LLM 표시」(headsSource)와 같고, 규칙 보강은 요약의 rules(heading_runs.rules_view — 마지막 LLM 1단계 실행)를 본다.
const H_PROG_STATE = { done: "끝남", llm: "LLM 끝남", none: "안 함", running: "도는 중", failed: "실패", stale: "뼈대에 없는 새 항목이 있음", skip: "할 것 없음" };
const H_PROG_NAME = { 1: "문단·라벨", 2: "헤딩 그래프", 3: "표 구조" };
// 이어 돌리기(job.chain — app/analysis_llm.py CHAINS)의 화면 이름 · 서버 analysis.CHAIN_NAMES 와 같은 글: llm = 이름 줄 진행표의 「LLM 검증·보완」(doc_status.js · spec_작업 ② §20) ·
// heads = 「헤딩 그래프(LLM)」(헤딩 판정 → 서식 정리 계획) · formats = 서식 정리 계획만(tpl_plan_bar.js 「계획 받기」)
const H_CHAIN = { llm: "LLM 검증·보완", heads: "헤딩 LLM 판정 · 서식 계획", formats: "서식 정리 계획" };
const H_CHAIN_LONG = { llm: "LLM 검증·보완(헤딩 · 표 판정 같이 → 서식 계획)", heads: "헤딩 그래프(LLM) → 서식 정리 계획", formats: "서식 정리 계획(템플릿마다)" };
const headsChainName = (job, long = false) => (long ? H_CHAIN_LONG : H_CHAIN)[job.chain] || H_CHAIN.llm;
const headsFmtStep = (s) => /^서식 정리 계획/.test((s && s.name) || ""); // 서식 정리 계획 단계(app/analysis_llm.py FORMATS_STEP) — 진행 줄의 스크립트 · LLM 칸이 아니라 셋째 층 「조정」(tpl_plan_bar.js)이 보인다
const hhmmShort = (t) => { // 진행 줄 칸의 시각 — 오늘이면 「13:47」, 아니면 「11/14」(전체는 title)
  if (!t) return "";
  const d = new Date(t * 1000);
  return d.toDateString() === new Date().toDateString() ? hhmm(d) : `${d.getMonth() + 1}/${d.getDate()}`;
};
function headsStepCell(n, job) { // 작업 단계 줄의 이름 → 진행 줄의 칸 {llm, k} | null(칸에 안 드는 단계)
  if (n.includes("규칙 보강") || (n === "다시 추출" && job.llm)) return { llm: true, k: 1 }; // 「LLM 규칙 보강」 · 2단계 LLM 의 「1단계 다시 — … LLM 규칙 보강」 · 보강 뒤 다시 추출
  const m = /^(헤딩 그래프|표 구조) — (LLM|스크립트)$/.exec(n);
  if (m) return { llm: m[2] === "LLM", k: m[1] === "표 구조" ? 3 : 2 };
  if (/^(추출|후보 규칙 시험|1단계)/.test(n)) return { llm: false, k: 1 };
  return null;
}
// 도는 작업이 지금 하는 칸 → {llm, k, more?} | null — 작업 steps 의 마지막 「진행 중」 단계 이름으로. more = 같이 도는 다른 칸(「LLM 검증·보완」 은 헤딩 판정이 도는 동안
// 표 판정 호출을 같이 돌린다 — heading_runs.TablesAhead: spec_헤딩_추출 ② §8 「헤딩 판정과 같이」). 칸이 도는지는 headsNowAt 으로 묻는다
function headsProgNow(r) {
  const job = r.job;
  if (!(job && job.status === "running")) return null;
  const steps = job.steps || [], run = steps.filter((s) => s.status === "running"), cur = run.filter((s) => !headsFmtStep(s)).pop();
  if (!cur && (run.some(headsFmtStep) || headsFmtStep(steps.at(-1)))) return { llm: true, k: 0, fmt: true }; // 서식 정리 계획만 도는 중(또는 그것으로 끝남) — 진행 줄에는 도는 칸이 없다
  const n = (cur || steps.filter((s) => !headsFmtStep(s)).pop() || {}).name || "";
  const at = headsStepCell(n, job) || (job.first ? { llm: false, k: r.stage2 ? 3 : 2 } : { llm: !!job.llm, k: job.stage });
  const more = run.filter((s) => s !== cur && !headsFmtStep(s)).map((s) => headsStepCell(s.name || "", job)).filter((c) => c && !(c.llm === at.llm && c.k === at.k));
  return more.length ? { ...at, more } : at;
}
const headsNowAt = (now, llm, k) => !!now && ((!!now.llm === llm && now.k === k) || (now.more || []).some((c) => c.llm === llm && c.k === k)); // 그 칸(층 · 단계)이 지금 도는가 — 같이 도는 칸도
function headsRulesFrom(r) { // 규칙 보강 기록 — 요약의 rules(서버), 없으면(옛 서버) 지금 1단계 결과 · 실행 목록(끝 20개)으로 어림
  if (r.rules !== undefined) return r.rules;
  const s1 = r.stage1, lm = s1 && s1.llm;
  if (lm) return { run: s1.meta && s1.meta.run, at: s1.meta && s1.meta.at, groups: lm.groups || 0, asked: !!(lm.items || []).length,
    saved: (lm.saved || []).length, kept: (lm.kept || []).length, error: lm.error, costUsd: lm.costUsd };
  const run = [...(r.runs || [])].reverse().find((x) => x.stage === 1 && x.llm);
  return run ? { run: run.n, at: run.at, costUsd: run.costUsd, asked: null, ...(run.rules || {}) } : null;
}
function headsProgScript(r, k, now) { // 스크립트 칸 → {state, text, title}
  const s = r[`stage${k}`], name = H_PROG_NAME[k], job = r.job, meta = (s && s.meta) || {};
  if (headsNowAt(now, false, k)) return { state: "running", text: name, title: `${name} — 스크립트로 뽑는 중 · 누르면 진행을 봅니다` };
  if (!s && job && job.status === "failed" && (job.first || (!job.llm && job.stage === k))) return { state: "failed", text: name, title: `${name} — 실행 실패: ${job.error || "까닭 모름"}` };
  if (!s) return { state: "none", text: name, title: `${name} — 아직 없음(${k}단계를 실행하면 만듭니다)` };
  const when = `실행 ${meta.run ?? "–"} · ${fmtWhen(meta.at)}`;
  if (k === 1) {
    const sm = s.summary || {};
    return { state: "done", text: name, title: `문단·서식 라벨 추출(스크립트) 끝남 — ${when}\n문단 ${nf(sm.paragraphs)} · 서식 라벨 ${nf(sm.labels)} · 못 맞춤 ${nf(sm.unmatchedGroups || 0)}묶음 · 충돌 ${nf(sm.conflicts || 0)}묶음`
      + (s.stale ? "\n그 뒤 문서가 바뀜 — 헤딩 추출 탭을 열 때 저절로 다시 뽑습니다" : "") };
  }
  const drift = headsStageStale(r, k), src = headsSource(r, k);
  return { state: drift ? "stale" : "done", text: name,
    title: `${name} 있음 — ${when}${src && src.llm ? " · LLM 판정까지 거친 결과" : " · 스크립트 결과"}${drift ? "\n뼈대에 없는 새 레터·서식·표가 문서에 생김(상태 줄의 주황 꼬리표)" : ""}` };
}
function headsProgRules(r, now) { // LLM 규칙 보강 칸(1단계) → {state, text, title}
  const s1 = r.stage1, sm = (s1 && s1.summary) || {}, job = r.job, rv = headsRulesFrom(r);
  const left = (sm.unmatchedGroups || 0) + (sm.conflicts || 0), leftText = `못 맞춤 ${nf(sm.unmatchedGroups || 0)}묶음 · 충돌 ${nf(sm.conflicts || 0)}묶음`;
  const how = "1단계 「LLM 규칙 보강」 으로 하거나, 2단계 「헤딩 그래프(LLM)」 을 누르면 그래프보다 먼저 저절로 합니다(유료)";
  if (headsNowAt(now, true, 1)) return { state: "running", text: "규칙 보강", title: "LLM 규칙 보강 중 — 스크립트가 판정하지 못한 첫머리 묶음의 규칙식을 LLM 에 묻는 중(유료 · 묶음이 많으면 여러 호출이 같이 돕니다) · 누르면 진행을 봅니다" };
  if (!s1) return { state: "none", text: "규칙 보강", title: "LLM 규칙 보강 — 1단계(문단·라벨)를 뽑은 뒤에 합니다" };
  if (job && job.status === "failed" && job.llm && job.stage === 1) return { state: "failed", text: "규칙 보강", title: `LLM 규칙 보강 실행 실패 — ${job.error || "까닭 모름"}\n${how}` };
  const at = rv ? `실행 ${rv.run ?? "–"} · ${fmtWhen(rv.at)}` : "";
  if (rv && rv.asked === false && rv.groups > 0) return { state: "failed", text: "규칙 보강", title: `LLM 규칙 보강 — ${at} 에 LLM 답을 못 받음: ${rv.error || "까닭 모름"}\n${how}` };
  if (rv) {
    const got = rv.asked == null ? "" : rv.groups ? `\n물은 묶음 ${nf(rv.groups)} → 규칙 저장 ${nf(rv.saved || 0)} · 그대로 ${nf(rv.kept || 0)} · 거절 ${nf(rv.rejected || 0)} · 모름 ${nf(rv.unsure || 0)}` : "\n그때 물을 묶음이 없었음";
    const same = s1.meta && s1.meta.run === rv.run; // 지금 1단계 결과가 그 실행 — 남은 묶음은 LLM 이 모르겠다고 했거나 검증에 떨어진 것
    const rest = !left ? "\n지금 판정하지 못한 묶음 없음"
      : same ? `\n지금 남은 ${leftText} — LLM 이 모르겠다고 했거나 검증에 떨어진 것(다시 물으려면 1단계 「LLM 규칙 보강」)`
        : `\n지금 남은 ${leftText} — 그 뒤 다시 뽑은 결과의 것(다음 「헤딩 그래프(LLM)」 이 먼저 다시 묻습니다 · 1단계 「LLM 규칙 보강」 으로도)`;
    return { state: "llm", text: "규칙 보강", ...(left ? { count: `남은 ${nf(left)}`, unit: "묶음" } : {}), title: `LLM 규칙 보강 끝남 — ${at}${rv.costUsd ? ` · $${rv.costUsd}` : ""}${got}${rest}` };
  }
  if (!left) return { state: "skip", text: "규칙 보강 · 할 것 없음", title: "LLM 규칙 보강 — 할 것 없음: 스크립트가 모든 첫머리를 판정했습니다(못 맞춤·충돌 묶음 없음)" };
  return { state: "none", text: "규칙 보강", count: nf(left), unit: "묶음", title: `LLM 규칙 보강 안 함 — 스크립트가 판정하지 못한 첫머리 ${leftText}\n${how}` };
}
// 칸의 글 = 이름(좁으면 줄임표) + 수(count — 줄지 않음 · 단위는 좁은 패널에서 감춤): 「규칙 보강 · 27묶음」 → 좁으면 「규칙 보… 27」. 수가 없는 칸은 이름뿐
function headsProgJudge(r, k, now) { // LLM 판정 칸(2 헤딩 · 3 표) → {state, text, count?, title}
  const s = r[`stage${k}`], name = k === 2 ? "헤딩 판정" : "표 판정", job = r.job, src = headsSource(r, k), lm = (s && s.llm) || {};
  const btn = k === 2 ? "「헤딩 그래프(LLM)」" : "「표 구조(LLM)」";
  if (headsNowAt(now, true, k)) { // 도는 중 — 표 판정은 헤딩 판정과 같이 돌 수 있다(그때는 단계 줄의 글 「표 판정 호출 7/25 끝남 — 헤딩 판정과 같이」 을 덧붙인다)
    const step = ((job && job.steps) || []).find((x) => x.status === "running" && (headsStepCell(x.name || "", job) || {}).k === k && x.msg);
    return { state: "running", text: name, title: `${name} — LLM 이 판정하는 중(유료 · 몇 분)${step ? `\n${step.msg}` : ""} · 누르면 진행을 봅니다` };
  }
  if (job && job.status === "failed" && job.llm && !job.first && job.stage === k && !(src && src.llm)) return { state: "failed", text: name, title: `${name} — LLM 실행 실패: ${job.error || "까닭 모름"} · 앞 결과는 그대로` };
  if (src && src.llm) return { state: "llm", text: name, count: hhmmShort(src.at), title: src.title }; // 끝난 때(② §7 「LLM 표시」 — 전체 시각·걸린 시간은 title)
  if (s && lm.requested && lm.fallback) return { state: "failed", text: name, title: src ? src.title : `${name} — LLM 을 불렀지만 실패해 스크립트로 대신함` };
  return { state: "none", text: name, title: s ? `${name}(LLM) 안 함 — 지금 결과는 스크립트(${fmtWhen((s.meta || {}).at)}) · 추출·설정 ${k}단계의 ${btn}(유료)` : `${name}(LLM) — ${k}단계 결과가 없습니다` };
}
// opt(2026-11-16 「표」 탭도 같은 그리기 — spec_헤딩_추출 ② §10 「꼴은 헤딩 추출과 같은 틀」): stages = 보일 단계(「표」 탭은 [3] — 한 칸이면 .hprog-one) ·
// open(k) = 칸을 누르면(기본 = 헤딩 추출 「추출·설정」 의 그 단계 탭) · where(k) = title 끝의 「누르면 …」
// LLM 층의 끝난 칸(✓ — state "llm")만은 어느 자리에서든 「LLM 이 바꾼 것」(heading_llm_diff.js — 문서 옆 열의 그 단계 절)을 연다(2026-11-16 사용자 「LLM 작업하고 뭐가 수정되었는지를 모르겠다」 → 답 「문서 옆 열」).
// 안 돈 칸·실패한 칸·스크립트 층은 전처럼 open(k) — 실행할 자리.
function headsProgLine(r, opt = {}) { // 진행 줄 — 두 층(스크립트 · LLM) × 세 단계, 누르면 추출·설정의 그 단계 탭(LLM ✓ 칸은 LLM 이 바꾼 것)
  const now = headsProgNow(r), box = el("div", "hprog"), stages = opt.stages || H_STAGES, open = opt.open || headsRunOpen, where = opt.where || ((k) => `추출·설정 ${k}단계`);
  if (typeof llmDiffSync === "function") llmDiffSync(r); // 열려 있는 「LLM 이 바꾼 것」 — 그 사이 실행이 바뀌었으면 다시 읽는다
  box.classList.toggle("hprog-one", stages.length === 1);
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "분석 진행 — 스크립트와 LLM");
  const rows = [["스크립트", (k) => headsProgScript(r, k, now)], ["LLM", (k) => (k === 1 ? headsProgRules(r, now) : headsProgJudge(r, k, now))]];
  for (const [label, info] of rows) {
    box.append(el("span", "hprog-layer", label));
    for (const k of stages) {
      const i = info(k), diff = label === "LLM" && i.state === "llm" && typeof llmDiffOpen === "function";
      const b = hBtn("", diff ? () => llmDiffOpen(k) : () => open(k), { cls: "hprog-step" });
      b.dataset.state = i.state;
      b.append(el("span", "hprog-mark"), el("span", "hprog-text", i.text));
      if (i.count) {
        const n = el("span", "hprog-count", i.count);
        if (i.unit) n.append(el("span", "hprog-unit", i.unit));
        b.append(n);
      }
      b.title = `${i.title}\n— ${H_PROG_STATE[i.state]} · 누르면 ${diff ? "LLM 이 바꾼 것(문서 옆 열)" : where(k)}`;
      b.setAttribute("aria-label", `${label} ${i.text}${i.count ? ` ${i.count}${i.unit || ""}` : ""} — ${H_PROG_STATE[i.state]}`);
      box.append(b);
    }
  }
  // 셋째 층 「조정」 — 템플릿 조정 · 서식 조정 · 모두 반영(tpl_plan_bar.js — LLM 판정 뒤의 일: 2026-11-16 사용자 「여기 밑에 템플릿 조정, 서식 조정 이 들어 가야함」). 세 단계를 다 보이는 진행 줄(헤딩 추출 탭)에만
  if (stages.length === H_STAGES.length && typeof tplPlanRow === "function") box.append(...tplPlanRow());
  if (typeof headsPickMarks === "function") headsPickMarks(box); // 「단계별 실행」 이 고른 단계 가운데 차례를 기다리는 칸(heads_run_pick.js — 점선 동그라미)
  return box;
}

// ---- 실행 메뉴(spec_헤딩_추출 ② §7 「실행 메뉴는 머리에」, 2026-11-16 사용자 「규칙보강 실행 메뉴를 상단에 넣어야지. 표도 딱같음」) — 요약 상태 줄 끝 「단계별 실행 ▾」.
// 이름은 같은 날 사용자 「지금 실행은 단계별 실행, 그리고 추가로 전체 실행(조정까지) 로 변경해줘」 — 전의 「실행 ▾」. 돌릴 단계를 **골라** 돌리는 메뉴이고, 남은 단계를 조정까지 한 번에 돌리는 것은
// 그 앞의 「전체 실행」 단추다(heads_run_all.js headsRunAllBtn — 헤딩 추출 탭에만: ② §7 「전체 실행」).
// 전에는 실행이 「추출·설정」 의 단계 카드 안에만 있어 진행 줄에서 ○ 를 보고도 거기까지 들어가야 했다. 항목 = 진행 줄과 같은 차례(스크립트 → LLM · 유료) · 단계 카드 단추와 같은 꺼짐 조건.
// 2026-11-17 사용자 「여기에서 클릭한 다음에 클릭한 것들만 실행 … 불필요하게 한개씩 하지 말고」: 메뉴는 **고르기 목록**이다 — 항목을 눌러 표시하고 「고른 n개 실행」 을 누르면 고른 것만 차례로 돈다
// (확인 창은 한 번). 메뉴 · 차례 실행 · 멈추기는 heads_run_pick.js(headsPickBind) — 여기는 단추만 만든다.
// opt.stages = 보일 단계(「표」 탭은 [3]) · opt.detail = 「추출·설정에서 자세히」(기본 = 헤딩 추출의 추출·설정). 부르는 곳: headsResultsSummary · tables.js tablesDraw
function headsRunMenu(r, opt = {}) {
  const stages = opt.stages || H_STAGES, detail = opt.detail || (() => headsResultView("Run"));
  const b = hBtn("", null, { cls: "btn sm hrun-menu", title: "단계별 실행 — 돌릴 단계를 골라 고른 것만 차례로 돌립니다(스크립트 무료 · LLM 유료)" });
  b.append("단계별", el("span", "hrun-word", " 실행"), " ▾"); // 「단계별 실행 ▾」 — 좁은 패널(370px 아래)에서는 「실행」 을 감춰 「단계별 ▾」(heading-panels.css — 옆 「전체 실행」 과 한 줄에 들게)
  b.setAttribute("aria-label", "단계별 실행");
  b.setAttribute("aria-haspopup", "menu");
  if (typeof headsPickBind === "function") headsPickBind(b, { stages, detail }); // 누르면 고르기 목록 · 도는 동안은 「단계별 실행 2/3 ▾」(heads_run_pick.js)
  return b;
}

const HEAD_VIEWS = ["Tree", "Labels", "Templates", "Tables", "Review", "Run"];
function headsResultView(name) {
  panelHelpClose();
  if (name === "Run" && heads.resultView !== "Run" && heads.view) { // 추출·설정에 들어올 때: 도는 작업이 있으면 그 단계 탭, 처음이면 손볼 단계(② §7 「단계 탭」)
    const job = heads.view.job;
    if (job && job.status === "running") heads.runStage = job.stage;
    else if (heads.runStage == null) heads.runStage = headsStageAuto(heads.view);
    headsStageShow(heads.runStage);
  }
  heads.resultView = name;
  for (const key of HEAD_VIEWS) {
    const on = name === key, b = $(`headsTab${key}`);
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
    $(`headsView${key}`).hidden = !on;
    if (on) {
      const nav = b.parentElement, nr = nav.getBoundingClientRect(), br = b.getBoundingClientRect();
      if (br.right > nr.right) nav.scrollLeft += br.right - nr.right;
      else if (br.left < nr.left) nav.scrollLeft -= nr.left - br.left;
    }
  }
}

// ---- 단계 탭(spec_헤딩_추출 ② §7 「단계 탭」, 2026-11-10 사용자 "추출설정에서 1,2,3,단계들이 있는데 이거 탭으로 해주고. 높이를 많이 갖어 가지 말고")
// 「추출·설정」 의 1·2·3단계 카드를 한 번에 하나만 보인다. 고른 단계 heads.runStage = 사람이 누른 탭. 저절로 바뀌는 때는 둘뿐 — 추출·설정에 들어올 때 도는 작업이 있으면 그 단계,
// 추출·설정을 보는 중에 새 작업이 돌기 시작하면 그 단계(진행이 그 카드에 보인다). 한 번도 안 골랐으면 headsStageAuto(도는 단계 · 손볼 단계 · 1).
// 탭마다 data-state 로 도는 중(돌아가는 동그라미)·실패·오래됨(점)을 보여, 탭을 안 열어도 어느 단계가 어떤지 안다.
const H_STAGES = [1, 2, 3];
const H_STAGE_TITLE = { 1: "1단계 — 문단·규칙식·서식 라벨", 2: "2단계 — 헤딩 그래프·템플릿", 3: "3단계 — 표 구조(행헤더·열헤더·필드·서브 테이블)" };
const H_STAGE_STATE = { running: "분석 중", failed: "실행 실패", stale: "뼈대에 없는 새 항목이 있음", none: "결과 없음" };
// 그 단계에 손볼 것이 있음 = 뼈대(2·3단계 결과)에 없는 새 레터·새 서식·새 표가 문서에 생김(heading_drift.js — ② §17 뼈대 유지, 2026-11-10 사용자 "문서가 바뀔 때마다 헤딩을 다시
// 추출하라고 하면 어쩌냐 … 새로운 레터나 서식이 추가되면 알람이나 표시만"). 문서가 바뀐 것(stale)·1단계를 다시 뽑은 것만으로는 오래된 결과가 아니다 — 1단계는 탭을 열 때 저절로 다시 뽑는다.
function headsStageStale(r, k) {
  return k > 1 && !!r[`stage${k}`] && typeof driftCount === "function" && driftCount(k) > 0;
}
function headsStageShow(k) { // 탭·카드 표시만
  for (const s of H_STAGES) {
    const on = s === k, b = $(`headsStageTab${s}`);
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
    $(`headsStage${s}`).hidden = !on;
  }
}
function headsStagePick(k) { // 사람이 고름
  panelHelpClose();
  heads.runStage = k;
  headsStageShow(k);
}
function headsStageAuto(r) { // 고른 적 없을 때 보일 단계 — 도는 작업의 단계 · 없으면 손볼 단계(결과 없음·오래됨) · 다 있으면 1
  const job = r.job;
  if (job && job.status === "running") return job.stage;
  return H_STAGES.find((k) => !r[`stage${k}`] || headsStageStale(r, k)) || 1;
}
function headsRunOpen(k) { // 「추출·설정」 을 열고 그 단계 탭으로(진행 보기 · 실행 내역 보기 · 재확인 · 빈 결과의 「추출·설정 열기」)
  headsResultView("Run");
  if (k) headsStagePick(k);
}
function headsStageSync(r) { // headsRender 마다
  const job = r.job, running = !!(job && job.status === "running");
  if (job && job.started !== heads.jobSeen) { // 새로 본 작업 — 추출·설정을 보는 중에 돌기 시작했으면 그 단계 탭으로
    heads.jobSeen = job.started;
    if (running && heads.resultView === "Run") heads.runStage = job.stage;
  }
  headsStageShow(heads.runStage ?? headsStageAuto(r));
  for (const k of H_STAGES) {
    const s = r[`stage${k}`], b = $(`headsStageTab${k}`);
    const st = running && job.stage === k ? "running" : job && job.status === "failed" && job.stage === k ? "failed" : !s ? "none" : headsStageStale(r, k) ? "stale" : "";
    b.dataset.state = st;
    b.title = H_STAGE_TITLE[k] + (st ? ` · ${H_STAGE_STATE[st]}` : "");
  }
}

// ---- 진행 표시(spec_헤딩_추출 ② §7 「진행 표시」, 2026-11-10 사용자 "추출중이면 동그라미 돌아가는거. 라도 넣어주고.. 뭘 하는 지 모르잖아. 분석중이라고만 하면")
// 도는 작업이 지금 하는 일 = 작업 steps 의 마지막 「진행 중」 단계 이름(「표 구조 — LLM」·「추출」·「LLM 규칙 보강」 …) + 시작부터 지난 시간. 요약 줄 꼬리표(돌아가는 동그라미)와
// 단계 카드의 작업 줄에 같은 글. 서버 변경 없음(작업 보기 steps·started 에 이미 있는 값) — LLM 호출이 몇 번째인지는 서버가 아직 안 알려 준다(④).
function headsJobNow(job, r) { // → {what, secs, prev, title}
  const steps = job.steps || [], cur = steps.filter((s) => s.status === "running").pop() || steps.at(-1);
  const src = job.llm && !job.first && job.stage > 1 && r ? headsSource(r, job.stage) : null; // 같은 단계의 앞 LLM 실행이 걸린 시간 — 얼마나 걸릴지 어림
  const prev = src && src.seconds ? fmtDur(src.seconds) : "";
  return { what: `${job.first ? "첫 분석" : job.chain ? headsChainName(job) : `${job.stage}단계`} · ${cur ? cur.name : "준비 중"}`, // job.chain = 이어 돌리기(H_CHAIN)
    secs: Math.max(0, Date.now() / 1000 - (job.started || 0)), prev,
    title: `${job.llm ? "LLM" : "스크립트"} 실행 · ${fmtWhen(job.started)} 시작${prev ? ` · 지난번 LLM 실행은 ${prev} 걸림` : ""} — 누르면 추출·설정에서 단계별 진행을 봅니다` };
}
function headsNowDraw(r) { // 요약 줄 꼬리표의 글 — 읽을 때마다(약 1초)
  const e = heads.nowEl, job = r.job;
  if (!e || !e.isConnected || !(job && job.status === "running")) return;
  const now = headsJobNow(job, r);
  e.firstChild.textContent = now.what;
  e.lastChild.textContent = fmtDur(now.secs);
  e.title = now.title;
}

// ---- 문서를 연 직후 헤딩 요약 한 번 읽기(GET 만). 상단 바 LLM 단계 동그라미는 없앴다(2026-11-11 사용자 — spec_헤딩_추출 ① 같은 날). 남은 일은 둘:
// 작업이 도는 중에 열었으면 끝날 때까지 이어 읽고(headsPoll), 아니면 읽은 요약을 뼈대 유지(② §17)에 넘긴다.
async function headsPeek() { // headsShow 와 달리 추출을 시작하지 않고, 도는 작업이 없으면 heads.view 도 건드리지 않는다(첫 분석 POST 와 안 겹침)
  if (!state.id || state.format === "docx") return;
  const id = state.id, epoch = state.epoch;
  let r = null;
  try { r = await api(`/api/docs/${id}/headings`); }
  catch { return; } // 헤딩 탭을 열면 다시 읽는다
  if (epoch !== state.epoch || heads.view) return; // 그 사이 헤딩 요약을 읽었으면(첫 분석·탭) headsRender 가 이미 처리했다
  if (r.job && r.job.status === "running") headsPoll(); // 작업이 도는 중에 열었으면(LLM 실행 중 새로 고침) 끝날 때까지 읽는다(GET 만 — headsRender)
  else if (typeof driftSeed === "function") driftSeed(r); // 뼈대 유지(② §17) — 이어 연 작업은 헤딩 탭을 열지 않아도 새 레터·새 서식·새 표를 견준다(GET 만, heads.view 는 안 건드림)
}

function headsEmptyResult(target, title, message, stage) {
  const box = $(target);
  const empty = el("div", "result-empty");
  const head = el("div", "result-empty-head");
  head.append(el("strong", null, title), hHelp("결과 준비 안내", message + (stage ? ` ${stage}단계 결과를 사용합니다.` : "")));
  empty.append(head);
  empty.append(hBtn("추출·설정 열기", () => headsRunOpen(stage), { cls: "btn sm primary" }));
  box.replaceChildren(empty);
}

function headsResultsSummary(r) {
  const renderKey = JSON.stringify([r.rev, [1, 2, 3].map((k) => {
    const s = r[`stage${k}`]; return s && [s.meta?.run, s.meta?.at, s.stale];
  }), r.job && [r.job.stage, r.job.status, r.job.started], !!heads.graph, r.temp && r.temp.key, typeof driftStamp === "function" ? driftStamp() : null,
  JSON.stringify(headsProgNow(r)), r.rules && [r.rules.run, r.rules.asked]]); // 진행 줄 — 도는 작업이 다른 칸(스크립트 → 규칙 보강 → 헤딩 판정)으로 넘어가면 다시 그린다
  if (heads.summaryKey === renderKey) return;
  panelHelpClose();
  heads.summaryKey = renderKey;
  const s1 = r.stage1, s2 = r.stage2, s3 = r.stage3, job = r.job;
  const sm = s1 ? s1.summary : {}, c = s2 ? s2.counts || {} : {};
  const overview = $("headsOverview");
  overview.textContent = "";
  const metrics = el("div", "result-metrics");
  for (const [name, value, view] of [["서식 라벨", sm.labels, "Labels"], ["템플릿", c.templates, "Templates"], ["표", s3 && s3.counts.tables, "Tables"]]) {
    const b = hBtn("", () => headsResultView(view), { cls: "result-metric" });
    b.append(el("span", null, name), el("strong", null, value == null ? "미추출" : nf(value)));
    metrics.append(b);
  }
  const tm = typeof tempMetric === "function" ? tempMetric(r) : null; // TEMP 항목 수 — 누르면 TEMP 목록(heading_temp.js, spec ② §15)
  if (tm) metrics.append(tm);
  overview.append(metrics);
  overview.append(headsProgLine(r)); // 진행 줄(② §7 「진행 줄」) — 스크립트 · LLM 두 층에서 어디까지 했나(전의 LLM 꼬리표 줄 자리 — LLM 판정의 끝난 때·걸린 시간은 칸의 글·title)
  const stages = [s1, s2, s3].filter(Boolean);
  // 문서가 바뀐 것만으로는 「재확인 필요」 가 아니다(② §17 뼈대 유지) — 뼈대에 없는 새 레터·새 서식·새 표가 생겼을 때만 주황 꼬리표(누르면 목록 — heading_drift.js driftChip)
  const drift = typeof driftChip === "function" ? driftChip() : null;
  const meta = el("div", "result-meta"), running = !!(job && job.status === "running");
  heads.nowEl = null;
  if (running) { // 돌아가는 동그라미 + 지금 하는 일 · 지난 시간 — 글은 headsNowDraw 가 읽을 때마다 채운다(② §7 「진행 표시」)
    const now = hBtn("", () => headsRunOpen(job.stage), { cls: "analysis-state running" });
    now.append(el("span", "now-what", job.first ? "첫 분석(2·3단계)" : job.chain ? `${headsChainName(job)} 중` : `${job.stage}단계 분석 중`), el("span", "now-secs"));
    heads.nowEl = now;
    meta.append(now, hBtn("진행 보기", () => headsRunOpen(job.stage), { cls: "btn sm now-open" }));
  } else if (job && job.status === "failed") {
    meta.append(el("span", "analysis-state stale", `${job.stage}단계 실행 실패`), hBtn("실행 내역 보기", () => headsRunOpen(job.stage)));
  } else {
    meta.append(drift || el("span", "analysis-state", stages.length ? "추출 결과" : "분석 준비"));
  }
  if (stages.length) meta.append(hHelp("분석 실행 기록", stages.map((s) => {
    const stage = s === s1 ? 1 : s === s2 ? 2 : 3;
    return `${stage}단계 #${s.meta?.run ?? "–"}`;
  }).join(" · "), { note: true }));
  if (typeof headsRunAllBtn === "function") meta.append(headsRunAllBtn()); // 「전체 실행」 — 남은 단계를 조정까지 한 번에(heads_run_all.js — ② §7 「전체 실행」 · 조정 층이 있는 이 탭에만)
  meta.append(headsRunMenu(r)); // 상태 줄 끝 「단계별 실행 ▾」(② §7 「실행 메뉴는 머리에」 — 「표」 탭도 같은 함수)
  overview.append(meta);
  headsNowDraw(r);
  $("headsRunHelp").replaceChildren(hHelp("추출·설정 도움말", "단계 탭을 골라 분석을 실행하거나 기준을 바꿉니다. 탭의 돌아가는 동그라미 = 그 단계가 도는 중, 점 = 뼈대에 없는 새 레터·서식·표가 문서에 생김(또는 실패). 헤딩 그래프·표 구조는 한 번 만들면 문서를 고쳐도 그대로 씁니다(뼈대). 추출 결과는 문서 구조·서식 라벨·템플릿 등의 탭에서 원문과 대조하세요."));

  if (!s2) {
    headsEmptyResult("heads2More", "문서 구조를 확인하세요", "문단 추출 후 2단계를 실행하면 헤딩을 따라 원문을 찾아볼 수 있습니다.", 2);
    headsEmptyResult("headsTemplatesResult", "아직 템플릿이 없습니다", "헤딩 그래프를 만들면 레터 사슬과 레벨별 서식을 여기서 확인할 수 있습니다.", 2);
  }
  const labels = $("headsLabelsResult");
  labels.textContent = "";
  if (!s1) headsEmptyResult("headsLabelsResult", "서식 라벨을 준비하고 있습니다", "1단계에서 문단의 서식을 묶어 라벨을 만듭니다.", 1);
  else {
    const top = el("div", "result-toolbar");
    top.append(el("strong", null, `서식 라벨 ${nf(sm.labels)}개`), hHelp("서식 라벨 도움말", "라벨을 누르면 해당 문단 목록을 원문 옆에 엽니다. S 번호는 이 문서 안에서 사용하는 번호입니다. 문단 수가 많은 라벨부터 최대 30개를 표시하며 전체 목록에서 모든 라벨을 확인할 수 있습니다."), hBtn("전체 라벨·문단 보기", () => headsLabels()));
    if ((s1.labelsTop || []).length < sm.labels) top.insertBefore(el("span", "result-range", `상위 ${(s1.labelsTop || []).length}개`), top.lastChild);
    labels.append(top);
    const list = el("ul", "label-results");
    for (const l of s1.labelsTop || []) {
      const li = el("li"), b = hBtn("", () => headsParas({ fmt: l.id }), { cls: "label-result" });
      b.append(el("span", "label-code", l.id), el("span", "label-name", l.name), el("span", "label-count", `${nf(l.count)}문단`));
      li.append(b);
      list.append(li);
    }
    labels.append(list);
  }
  const tables = $("headsTablesResult");
  tables.textContent = "";
  if (!s3) headsEmptyResult("headsTablesResult", "표의 헤더와 필드를 확인하세요", "3단계를 실행하면 표마다 칸의 역할과 서브 테이블을 확인할 수 있습니다.", 3);
  else {
    const tableHead = el("div", "result-toolbar");
    tableHead.append(el("strong", null, "표 구조"), hHelp("표 구조 도움말", "표를 선택하면 원문 옆에 헤더·필드와 서브 테이블 경계를 표시합니다."));
    tables.append(tableHead);
    const list = el("ul", "label-results");
    for (const t of s3.tables || []) {
      const li = el("li"), b = hBtn("", () => headsTables(t.id), { cls: "label-result" });
      b.append(el("span", "label-code", t.id), el("span", "label-name", t.before || `${t.rows}행 × ${t.cols}열`),
        el("span", "label-count", `${t.subtables?.length || 0}개 구역${t.issues ? ` · 확인 ${t.issues}` : ""}`));
      li.append(b); list.append(li);
    }
    tables.append(list);
    if (!(s3.tables || []).length) tables.append(el("p", "hnote", "분석 결과에 표가 없습니다. 1칸 표·글상자는 제외합니다."));
  }
  const review = $("headsReviewResult");
  review.textContent = "";
  const reviewHead = el("div", "result-toolbar");
  reviewHead.append(el("strong", null, "판단이 필요한 부분"), hHelp("확인할 항목 도움말", "미판정·규칙 충돌·서식 조정의 근거를 원문과 대조하세요. 추출 완료는 사용자 확인 완료를 뜻하지 않습니다."));
  review.append(reviewHead);
  const reviewStats = el("div", "review-counts");
  for (const [name, v] of [["못 맞춘 묶음", sm.unmatchedGroups], ["규칙 충돌", sm.conflicts], ["미판정 노드", c.undecided], ["재검토 불일치", c.disagreed]]) {
    reviewStats.append(el("span", v ? "needs-review" : "muted", `${name} ${v == null ? "미추출" : nf(v)}`));
  }
  review.append(reviewStats);
  const nodes = (heads.graph?.nodes || []).filter((n) => n.undecided);
  if (nodes.length) {
    const list = el("ul", "review-nodes");
    for (const n of nodes.slice(0, 50)) {
      const li = el("li");
      const b = hBtn(short(`${n.letter || ""} ${n.text || ""}`, 90), () => headsGo(n.para), { disabled: !hasBlock(n.para), cls: "review-node" });
      li.append(b, hHelp("미판정 근거", n.reason || "판정되지 않아 초안을 유지한 문단", { warning: true }));
      list.append(li);
    }
    review.append(list);
    if (nodes.length > 50) review.append(el("p", "hnote", `미판정 ${nf(nodes.length)}개 중 앞 50개 표시`));
  }
}

function headsMarkStale() {
  if (heads.view) {
    let changed = false;
    for (const k of [1, 2, 3]) {
      const result = heads.view[`stage${k}`];
      if (result && !result.stale && result.meta?.rev !== state.serverRev) { result.stale = true; changed = true; }
    }
    if (changed) headsResultsSummary(heads.view);
  }
  // 뼈대 유지 — 더 고치지 않으면 잠시 뒤 지금 문서를 뼈대와 견준다(새 레터·새 서식·새 표만 알림 — heading_drift.js, ② §17). 헤딩 탭을 아직 안 연 이어 연 작업도(문서를 열 때 읽어 둔 요약으로)
  if (typeof driftTouch === "function") driftTouch();
}

function headsJob(job, r = null) {
  const box = el("details", "hjob");
  box.open = job.status !== "done";
  const now = job.status === "running" ? headsJobNow(job, r) : null; // 도는 동안: 지난 시간 · 지난번 LLM 실행이 걸린 시간(② §7 「진행 표시」)
  const secs = job.ended && job.started ? ` · ${(job.ended - job.started).toFixed(1)}s` : now ? ` · ${fmtDur(now.secs)} 지남${now.prev ? `(지난번 ${now.prev})` : ""}` : "";
  box.append(el("summary", `hjob-head ${job.status}`,
    `${job.first ? "첫 분석(2·3단계)" : job.chain ? headsChainName(job, true) : `${job.stage}단계`} · ${job.llm ? "LLM" : "스크립트만"} · ${H_JOB[job.status] || job.status}${job.run ? ` · 실행 ${job.run}번` : ""}${secs}`));
  const ol = el("ol", "steps brief");
  const phase = `-${Date.now() % 800}ms`; // 읽을 때마다(약 1초) 이 상자를 다시 만든다 — 돌아가는 동그라미가 처음 각도로 튀지 않게 시계에 맞춘다(spin .8s)
  for (const s of job.steps || []) {
    const cls = H_STEP[s.status] || s.status;
    const li = el("li", `step ${cls}`);
    li.append(el("span", "st", ICON[cls] || ""), el("span", "ttl", s.name), el("span", "sec", s.status === "running" ? "진행 중" : `${s.seconds}s`),
      el("div", "det", s.msg || ""));
    if (cls === "run") li.firstChild.style.animationDelay = phase;
    ol.append(li);
  }
  box.append(ol);
  if (job.error && !(job.steps || []).some((s) => s.status === "failed")) box.append(el("p", "hwarn fail", job.error));
  return box;
}

// 단계 설정은 제목·상태·결과·실행 순으로. 긴 설명과 실행 근거는 공용 도움말에서 읽는다.
function headsCardHeader(box, r, stage, title, help) {
  const head = el("div", "hcard-head"), result = r[`stage${stage}`];
  head.append(el("b", null, title), hHelp(`${title} 도움말`, help));
  if (result) {
    const lm = result.llm || {}, meta = result.meta || {}, run = (r.runs || []).find(x => x.n === meta.run);
    const lines = [`실행 ${meta.run ?? "–"} · ${fmtWhen(meta.at)}`];
    const src = stage > 1 ? headsSource(r, stage) : null;
    if (src) lines.push(src.text);
    else if (run) lines.push(run.llm ? "LLM 분석" : "스크립트 분석");
    if (lm.summary) lines.push(lm.summary);
    if (lm.fallback) lines.push(stage === 2 ? "스크립트 대체 판정: 같은 레터는 형제, 새 레터는 자식으로 봅니다." : "LLM 판정 없이 스크립트 초안을 사용합니다.");
    if (meta.derivedFrom != null) lines.push(`${meta.what === "TEMP 지정" ? "TEMP 지정" : "구분 라벨 지정"} 반영 — 실행 ${meta.base ?? meta.derivedFrom}을 다시 셈` + (lm.replay ? `\n기존 LLM 판정 ${nf(lm.replay.calls)}회·조정 ${nf(lm.carried)}쌍을 이어받음. 슬롯이 바뀐 쌍은 미판정. 새 LLM 호출 없음.` : ""));
    if (lm.calls) {
      lines.push(`LLM 호출 ${nf(lm.calls)}회 · 실패 ${nf(lm.failed || 0)}회 · ${lm.seconds ?? "–"}초 · $${lm.costUsd ?? "–"}`);
      if (stage === 2) lines.push(`구간 ${nf(lm.sections)} · 실패 구간 ${nf(lm.failedSections || 0)}${lm.formatPairs != null ? ` · 서식 쌍 ${nf(lm.formatPairs)}` : ""}`);
      if (stage === 3) lines.push(`보낸 표 ${nf(lm.sent)} · 건너뜀 ${nf(lm.skipped)}`);
    }
    head.append(hHelp("분석 기록과 판단 요약", lines.filter(Boolean).join("\n\n"), { note: true }));
  }
  box.append(head);
}

function headsCardNotice(box, label, detail = "", warning = false) {
  const line = el("div", `stage-notice${warning ? " is-warning" : ""}`);
  line.append(el("span", null, label));
  if (detail) line.append(hHelp(`${label} 상세`, detail, { warning }));
  box.append(line);
}

function headsCard1(r, busy) {
  const box = $("heads1"), s1 = r.stage1;
  box.textContent = "";
  headsCardHeader(box, r, 1, "문단·서식 라벨", "문서의 모든 문단을 추출하고 규칙식과 서식 라벨을 붙입니다. 다시 추출은 스크립트로 실행합니다. LLM 규칙 보강은 못 맞춤·충돌 묶음의 규칙식을 제안받는 유료 작업입니다.");
  let groups = 0;
  if (!s1) headsCardNotice(box, busy ? "추출 결과 대기 중" : "추출 전", "다시 추출을 누르면 문단과 서식 라벨을 만듭니다.");
  else {
    // 경고가 아니라 안내(② §17 뼈대 유지 — 문서가 바뀔 때마다 다시 하라고 하지 않는다): 1단계는 이 탭을 열 때 저절로 다시 뽑는다
    if (s1.stale) headsCardNotice(box, "문서 변경됨 · 탭을 열 때 다시 추출", "문서가 바뀌었습니다. 아래 결과는 수정 전 문서 기준이며, 헤딩 추출 탭을 열 때 스크립트로 저절로 다시 추출합니다. 바로 맞추려면 다시 추출을 누르세요.");
    const sm = s1.summary, dl = el("dl", "hdl");
    groups = (sm.unmatchedGroups || 0) + (sm.conflicts || 0);
    const row = (k, v, cls = null, title = "") => {
      dl.append(el("dt", null, k));
      const dd = el("dd", cls, v);
      if (title) dd.title = title;
      dl.append(dd);
    };
    row("문단", `${nf(sm.paragraphs)} · XML ${sm.check ? "일치 ✓" : "불일치 ✕"}`, sm.check ? "good" : "bad",
      `추출 레코드 ${nf(sm.paragraphs)} / XML 문단 ${nf(sm.xml)} — 표 칸·글상자·머리말·각주 안 문단까지 모두 비교합니다.`);
    row("서식 라벨", `${nf(sm.labels)} · 정밀 서식 ${nf(sm.formats)}`, null, "정밀 서식(F) = 원본 값 그대로의 문단·글자 모양 지문 · 서식 라벨 = 오차 기준으로 F 를 묶은 것");
    row("못 맞춤", sm.unmatchedGroups ? `${nf(sm.unmatchedGroups)}묶음 · ${nf(sm.unmatched)}문단` : "없음", sm.unmatchedGroups ? "warnc" : null,
      "보통 글로 판정됐지만 앞머리에 기호·짧은 토큰이 있는 문단");
    row("충돌", sm.conflicts ? `${nf(sm.conflicts)}묶음` : "없음", sm.conflicts ? "warnc" : null, "첫머리에 종류가 다른 규칙이 둘 이상 맞는 문단(먼저 온 규칙이 이김)");
    const ri = headsProgRules(r, headsProgNow(r)), rv = headsRulesFrom(r); // 요약 진행 줄의 「규칙 보강」 칸과 같은 판정(② §7 「진행 줄」)
    row("LLM 규칙 보강", ri.state === "llm" ? `함 · 실행 ${rv.run ?? "–"} · ${fmtWhen(rv.at)}` : ri.state === "none" ? "안 함" : H_PROG_STATE[ri.state],
      ri.state === "failed" ? "bad" : ri.state === "llm" ? "llmc" : null, ri.title);
    box.append(dl);
    const chips = el("div", "hkinds");
    for (const [k, v] of Object.entries(sm.kinds || {})) {
      const c = el("button", "chip", `${H_KIND[k] || k} ${nf(v)}`);
      c.type = "button";
      c.title = `${k} — 누르면 이 종류의 문단 목록`;
      c.onclick = () => headsParas({ kind: k });
      chips.append(c);
    }
    box.append(chips);
    const warns = s1.warnings || [];
    if (warns.length) headsCardNotice(box, `경고 ${warns.length}개`, warns.map(String).join("\n"), true);
  }
  const a1 = el("div", "hacts stage-actions");
  a1.append(hBtn("다시 추출", () => headsStart(1, false), { disabled: busy, cls: "btn sm primary", title: "스크립트로 1단계를 다시 뽑습니다(LLM 없음, 1~2 s)" }),
    hBtn("LLM 규칙 보강", () => headsLlmRules(), { disabled: busy || !groups,
      title: groups ? "못 맞춤·충돌 묶음을 LLM 에 보내 규칙식을 제안받고 검증을 통과한 것만 저장합니다(유료)" : "보강할 묶음(못 맞춤·충돌)이 없습니다" }));
  const a2 = el("div", "hacts stage-tools");
  a2.append(hBtn("문단 목록", () => headsParas(), { disabled: !s1 }), hBtn("서식 라벨", () => headsLabels(), { disabled: !s1 }),
    hBtn("규칙", () => headsRules()), hBtn("지침", () => headsGuides()));
  if (typeof headsFormBtn === "function") a2.append(headsFormBtn(r)); // 양식 정보(heading_forms.js — 일반 지침과 따로, spec_헤딩_추출 ② §12)
  box.append(a1, a2);
  if (typeof tempCardRow === "function") box.append(tempCardRow(r)); // TEMP 라벨 — 표 안 작성요령·쓸 자리를 2·3단계에서 뺌(heading_temp.js, spec ② §15)
}

async function headsLlmReady() {
  try {
    const st = await api("/api/headings/llm");
    if (st.available) return st;
    toast(`LLM 연결이 없습니다(설정 ${st.backend}) — 스크립트만 쓸 수 있습니다`, true);
  } catch (e) { toast(`LLM 연결 상태를 읽지 못했습니다: ${e.message}`, true); }
  return null;
}

async function headsLlmRules() {
  const s1 = heads.view && heads.view.stage1;
  if (!s1) return;
  const st = await headsLlmReady();
  if (!st) return; // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 유료 · 보통 $0.2~0.3 · 40초 안팎: design.md §18 「확인 창」)
  headsStart(1, true);
}

async function headsLlmGraph() {
  const st = await headsLlmReady();
  // LLM 판정은 스크립트가 판정하지 못한 것(못 맞춤·충돌)까지 본다(spec_헤딩_추출 ② §3, 2026-11-16) — 그래프 전에 규칙 보강을 먼저(이미 답을 받은 묶음은 서버가 다시 묻지 않는다)
  if (!st) return; // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 유료 · 연구개발계획서 양식 기준 약 4분 · $3 안팎 + 서식 계획: design.md §18 「확인 창」)
  headsStart(2, true);
}

function headsMore1(r) { // LLM 표·못 맞춤·충돌 목록 — 결과(실행)가 바뀔 때만 다시 그린다(펼친 상태 유지)
  const s1 = r.stage1, key = s1 && s1.meta ? `${s1.meta.run}|${s1.meta.at}` : null;
  if (key === heads.moreKey) return;
  heads.moreKey = key;
  const box = $("heads1More");
  box.textContent = "";
  if (!s1) return;
  if (s1.llm) box.append(headsLlmTable(s1.llm));
  const rv = s1.review || {};
  if ((rv.unmatched || []).length) box.append(headsReview(rv.unmatched, `못 맞춤 ${rv.unmatched.length}묶음 보기`, false));
  if ((rv.conflicts || []).length) box.append(headsReview(rv.conflicts, `충돌 ${rv.conflicts.length}묶음 보기`, true));
}

function headsLlmTable(lm) {
  const items = lm.items || [];
  const cnt = (v) => items.filter((i) => i.verdict === v).length;
  const rows = items.map((it) => ({ cls: it.verdict === "rejected" ? "warn" : null,
    cells: [`${H_VERDICT[it.verdict] || it.verdict}${it.rule ? ` · ${H_KIND[it.rule.kind] || it.rule.kind}` : ""}`, it.group, it.rule ? it.rule.pattern : null, it.why || it.reason || ""],
    title: [it.rule && `${it.rule.name} (${it.rule.scope === "whole" ? "글 전체" : "첫머리"}${it.rule.first ? " · 앞선 규칙" : ""})`, it.reason, it.id && `규칙 ${it.id}`]
      .filter(Boolean).join(" — ") }));
  const d = miniTable(`LLM 규칙 보강 — 저장 ${cnt("saved")} · 거절 ${cnt("rejected")} · 그대로 ${cnt("kept")} · 모름 ${cnt("unsure")}`
    + (cnt("duplicate") ? ` · 중복 ${cnt("duplicate")}` : "") + " 보기", ["판정 · 종류", "묶음", "정규식", "까닭"], rows,
    `묶음 ${lm.groups} · ${lm.seconds}s · $${lm.costUsd}` + (lm.error ? ` · 오류: ${lm.error}` : ""), [1, 2, 3]);
  d.classList.add("hllm");
  return d;
}

function headsParaLink(id, text, n = 60, extra = "") {
  const t = short(text, n);
  if (!hasBlock(id)) {
    const s = el("span", "hlink-no", t);
    s.title = `웹 블록이 없는 문단(${id})${extra ? ` · ${extra}` : ""}`;
    return s;
  }
  const b = el("button", "hlink", t);
  b.type = "button";
  b.title = `문서에서 그 문단으로 · ${id}${extra ? ` · ${extra}` : ""}`;
  b.onclick = () => headsGo(id);
  return b;
}

function headsGo(id) { // 문서에서 그 문단으로 — 헤딩 열은 그대로 둔다(나란히 보기)
  if (!hasBlock(id) || !paraEl(id)) { toast("그 문단이 지금 문서에 없습니다(웹 블록 없음·지웠거나 합쳐짐)"); return; }
  scrollToBlock(id, true);
}

function headsReview(groups, label, conflict) {
  const d = el("details", "more hreview");
  d.append(el("summary", null, label));
  const ul = el("ul", "hgroups");
  for (const g of groups) {
    const li = el("li");
    const top = el("div", "hg-top");
    top.append(el("code", "hg-shape", g.shape || "—"), el("span", "hg-count", `${nf(g.count)}문단`));
    if (conflict && g.rules) {
      const rs = el("span", "hg-rules", g.rules.join(" › "));
      rs.title = `${g.rules[0]} 이 이김 · ${g.rules.slice(1).join(", ")} 도 맞음`;
      top.append(rs);
    }
    li.append(top);
    const ex = (g.examples || [])[0];
    if (ex) li.append(headsParaLink(ex.id, ex.text, 60, `${H_AREA[ex.area] || ex.area} · 서식 ${ex.fmt || "—"}`));
    li.title = (g.examples || []).map((x) => short(x.text, 80)).join("\n");
    ul.append(li);
  }
  d.append(ul);
  return d;
}

function headsCard2(r, busy) {
  const box = $("heads2"), s1 = r.stage1, s2 = r.stage2;
  box.textContent = "";
  headsCardHeader(box, r, 2, "헤딩 그래프·템플릿", "1단계 결과에서 헤딩의 역할·템플릿·레벨을 정합니다. LLM 분석은 유형·본문 구간·서식 쌍을 판정하는 유료 작업입니다. 스크립트 분석은 같은 레터를 형제, 새 레터를 자식으로 보는 초안을 만듭니다.");
  if (!s2) {
    headsCardNotice(box, s1 ? "분석 전" : "1단계 추출 필요", s1 ? "아래에서 분석 방법을 선택하세요." : "1단계에서 문단을 추출하면 헤딩 그래프를 만들 수 있습니다.");
  } else {
    // 문서가 바뀌어도 다시 분석하라고 하지 않는다 — 이 결과는 뼈대(② §17, 2026-11-10 사용자): 「뼈대 유지」 한 줄 + 뼈대에 없는 새 레터·새 서식이 생겼을 때만 그 수(heading_drift.js)
    if (typeof driftCardRow === "function") box.append(driftCardRow(r, 2));
    const c = s2.counts || {}, lm = s2.llm || {};
    const stats = el("div", "hstats");
    const stat = (v, k, title = "") => {
      const s = el("span");
      s.append(el("span", "stage-stat-label", k), el("b", null, nf(v)));
      if (title) s.title = title;
      stats.append(s);
    };
    stat(c.nodes, "노드", `본문 ${nf(c.body)} · 표 칸 ${nf(c.cell)}`);
    stat(c.types, "유형", "헤딩 유형 = (자리, 레터 변형군, 굵게, 크기)");
    stat(c.templates, "템플릿");
    stat(c.instances, "인스턴스", "서브 템플릿 인스턴스(실제 부분 트리)");
    stat(c.repeats, "되풀이", "같은 부모 아래 같은 꼴 부분 트리가 2번 이상");
    stat(c.heterogeneous, "이종 형제", "같은 부모 아래 레터 계열이 다른 형제");
    stat(c.adjust, "조정", "같은 템플릿 슬롯의 다른 서식 라벨을 대표 서식으로 보는 것");
    if (lm.calls) {
      stat(lm.applied, "LLM 변경", "B 호출이 초안과 다르게 정한 노드");
      stat(lm.rejected, "거절", "검증에서 버린 LLM 변경");
      stat(c.undecided, "미판정", "LLM 이 판정하지 못한 구간의 노드 — 초안 그대로");
      if (lm.reviewPairs != null) stat(c.disagreed, "재검토 불일치", `조정 판정을 새 호출(재검토)이 다르게 본 문단 — 미판정으로 둠 · 재검토 쌍 ${nf(lm.reviewPairs)}${lm.reviewFailed ? ` · 재검토 못 함 ${nf(lm.reviewFailed)}` : ""}`);
    }
    box.append(stats);
    if (lm.error) headsCardNotice(box, lm.fallback ? "LLM 실패 · 스크립트 결과" : "LLM 실패", lm.error, true);
  }
  const acts = el("div", "hacts");
  acts.classList.add("stage-actions");
  acts.append(hBtn("LLM 분석", () => headsLlmGraph(), { disabled: busy || !s1, cls: "btn sm primary", title: "유형·본문 구간·서식 쌍을 LLM 이 판정(유료, 수 분) — 끝나면 이어서 템플릿마다 서식 정리 계획을 받습니다(계획만 · 반영은 진행 줄 「조정」 의 「모두 반영」)" }),
    hBtn("스크립트 분석", () => headsStart(2, false), { disabled: busy || !s1, title: "LLM 없이 레터 스택으로(몇 초)" }));
  box.append(acts);
}

async function headsMore2(r) { // 트리·템플릿·조정 — 그래프(실행)가 바뀔 때만 GET /graph 로 다시 그린다
  const s2 = r.stage2, key = s2 && s2.meta ? `${s2.meta.run}|${s2.meta.at}` : null;
  if (key === heads.graphKey) return;
  heads.graphKey = key;
  const box = $("heads2More");
  box.textContent = "";
  heads.graph = null;
  $("headsTemplatesResult").textContent = "";
  $("headsAdjustResult").textContent = "";
  if (!s2) return;
  const id = state.id, epoch = state.epoch;
  box.append(el("p", "hnote", "그래프를 읽는 중…"));
  let g;
  try { g = await api(`/api/docs/${id}/headings/graph`); }
  catch (e) {
    if (epoch !== state.epoch || heads.graphKey !== key) return;
    heads.graphKey = null; // 다음 그리기 때 다시 읽게
    box.textContent = "";
    box.append(el("p", "hwarn", `그래프를 읽지 못했습니다: ${e.message}`), hBtn("다시 읽기", () => heads.view && headsMore2(heads.view)));
    return;
  }
  if (epoch !== state.epoch || heads.graphKey !== key) return;
  box.textContent = "";
  heads.graph = g;
  box.append(headsTree(g));
  $("headsTemplatesResult").replaceChildren(headsTemplates(g));
  $("headsAdjustResult").replaceChildren(headsAdjust(g));
  if (heads.dlg === "templates") { // 열려 있던 템플릿 관계 보기(2열)도 새 그래프로 — 접어 둔 열은 접힌 채(keepFold)
    heads.keepFold = true;
    try { headsTplView(); } finally { heads.keepFold = false; }
  }
  headsResultsSummary(heads.view || r);
  heads.marks = tplMarksBuild(g); // 문서 안 문단별 「#템플릿 L줄」 표시
  outlineLoad(true); // 2단계가 새로 돌았으면 오버레이도 새로(표시는 outlineLoad 가 합쳐 그림)
}

function headsTree(g) {
  const wrap = el("div", "htree-box");
  const body = (g.nodes || []).filter((x) => x.flow === "body");
  const byId = new Map(body.map((x) => [x.id, x]));
  const kids = new Map();
  for (const x of body) {
    if (!x.parent || !byId.has(x.parent)) continue;
    if (!kids.has(x.parent)) kids.set(x.parent, []);
    kids.get(x.parent).push(x);
  }
  const shown = (x) => x.role !== "not_heading" || kids.has(x.id); // 헤딩 아님은 숨김(자식이 있으면 흐리게)
  const roots = body.filter((x) => shown(x) && !(x.parent && byId.has(x.parent)) && (x.parent || kids.has(x.id)));
  const hidden = body.filter((x) => !shown(x)).length;
  const het = new Map((g.heterogeneous || []).map((h) => [h.parent, h]));
  const hetText = (h) => h.letters.map((l) => `「${l.shape || l.key}」 ${l.count}`).join(" · ");
  const head = el("div", "htree-head");
  const ttl = el("span", null);
  ttl.append(el("b", null, "본문 트리"), el("span", "muted", ` 노드 ${nf(body.length - hidden)}${hidden ? ` · 헤딩 아님 ${nf(hidden)} 숨김` : ""}`));
  ttl.title = "본문 흐름(본문·1칸 상자)의 노드만 — 표 칸 노드는 칸마다 따로 쌓여 여기엔 안 보임 · 누르면 문서에서 그 문단으로";
  const ul = el("ul", "htree");
  const expandAll = () => {
    for (let k = 0; k < 40; k += 1) {
      const todo = [...ul.querySelectorAll('button.htog[aria-expanded="false"]')];
      if (!todo.length) break;
      todo.forEach((b) => b.click());
    }
  };
  head.append(ttl, el("span", "spacer"), hBtn("모두 펼치기", expandAll), hBtn("처음대로", () => wrap.replaceWith(headsTree(g))));
  wrap.append(head);
  if (het.has("root")) wrap.append(el("p", "hnote", `최상위의 이종 형제: ${hetText(het.get("root"))}`));
  const make = (x, depth) => {
    const ch = kids.get(x.id) || [];
    const li = el("li", "hnode" + (x.role === "label" ? " label" : "") + (x.role === "not_heading" ? " dim" : ""));
    const row = el("div", "hrow");
    const tog = el("button", "htog", ch.length ? "▸" : "");
    tog.type = "button";
    let sub = null;
    const setOpen = (on) => {
      if (on && !sub) { // 접힌 가지는 펼칠 때 만든다(노드 수천 개)
        sub = el("ul");
        ch.forEach((c) => sub.append(make(c, depth + 1)));
        li.append(sub);
      }
      if (sub) sub.hidden = !on;
      tog.textContent = on ? "▾" : "▸";
      tog.setAttribute("aria-expanded", on);
    };
    if (ch.length) {
      tog.setAttribute("aria-label", `하위 ${ch.length}개 펼치기·접기`);
      tog.title = `하위 ${ch.length}개`;
      tog.onclick = () => setOpen(!sub || sub.hidden);
    } else {
      tog.disabled = true;
      tog.tabIndex = -1;
      tog.setAttribute("aria-hidden", "true");
    }
    const link = hasBlock(x.para);
    const txt = el(link ? "button" : "span", "htext" + (link ? "" : " nolink"));
    const letter = (x.letter || "").trim(), t = oneLine(x.text);
    if (letter) txt.append(el("span", "lt", letter));
    if (t) txt.append(t.length > 40 ? t.slice(0, 40) + "…" : t);
    else if (!letter) txt.append("(빈 글)");
    txt.title = `${oneLine(`${x.letter || ""}${x.text || ""}`)}\n${x.id} · 유형 ${x.type} · ${x.kind}${link ? " · 누르면 문서에서 그 문단으로" : " · 웹 블록 없음"}`;
    if (link) {
      txt.type = "button";
      txt.onclick = () => {
        wrap.querySelectorAll(".hrow.selected").forEach((r) => r.classList.remove("selected"));
        row.classList.add("selected");
        headsGo(x.para);
      };
    }
    row.append(tog, txt);
    const badge = (cls, text, title, onclick = null) => {
      const b = el(onclick ? "button" : "span", `hb ${cls}`, text);
      if (title) b.title = title;
      if (onclick) { b.type = "button"; b.onclick = onclick; }
      row.append(b);
    };
    if (H_ROLE[x.role]) badge("role", H_ROLE[x.role], `역할: ${x.role}`);
    if (x.role === "not_heading") badge("role", "헤딩 아님", "역할: not_heading");
    if (x.template && x.level) { // 「TN Lk」 = 템플릿 N 의 k번째 줄(레벨) · 라벨 노드는 라벨 식별자(정규 키 「[기관]」)까지 · 누르면 템플릿 관계 보기(그 템플릿을 펼침)
      const lab = x.role === "label" ? tplLabelId(x) : "";
      badge("tpl", `${tplRef(x.tplNo, x.template)} L${x.level}${lab ? ` ${lab}` : ""}`,
        `템플릿 ${tplRef(x.tplNo, x.template)} ${x.template} · ${x.level}번째 줄(레벨 ${x.level})${lab ? ` · 구분 라벨 ${lab}` : ""}${x.tplNo ? " · 누르면 템플릿 관계 보기" : ""}`,
        x.tplNo ? () => headsTplView(x.tplNo) : null);
    }
    if (het.has(x.id)) badge("het", "이종", `이종 형제: ${hetText(het.get(x.id))}`);
    if (x.changed) badge("chg", "변경", x.reason || "LLM 이 초안을 바꿈");
    if (x.undecided) badge("und", "미판정", "LLM 이 이 구간을 판정하지 못함 — 초안 그대로");
    const pd = x.parent && byId.has(x.parent) ? byId.get(x.parent).division : null;
    if (x.division && x.division !== pd) { // 구분 소속 — 부모와 같은 구분이면 되풀이하지 않는다
      const dv = byId.get(x.division);
      const lab = dv ? oneLine(`${dv.letter || ""}${dv.text ? ` ${dv.text}` : ""}`) : x.division;
      badge("div", `⟂ ${lab.length > 16 ? lab.slice(0, 16) + "…" : lab}`, `구분 소속: ${lab}`);
    }
    li.append(row);
    if (ch.length) setOpen(depth < 3);
    return li;
  };
  for (const x of roots) ul.append(make(x, 1));
  if (!roots.length) wrap.append(el("p", "hnote", "본문 흐름에 헤딩 노드가 없습니다."));
  wrap.append(ul);
  return wrap;
}

function headsTemplates(g) { // 「템플릿」 탭 — 「템플릿 관계」(2열)와 **같은 트리**(tplTreeDraw: 템플릿 줄 · 개요 레벨 그림 · 레벨 줄의 자리·서식 갈래 · 하위로 · 서식 정리 에이전트)
  // 2026-11-15 사용자 「템플릿관계랑 헤딩 추출 안에 템플릿은 똑같은 내용이니깐 똑같은UI로」 — 옛 카드 목록(번호 · 레벨 한 줄 · 원문 보기)은 없앰(spec_헤딩_추출 ② §7 「템플릿 관계」)
  const v2 = (g.version || 1) >= 2; // 2026-11-09 템플릿 가지 규칙 — 템플릿 = 사슬 하나(앵커), id = 번호 N(표기 「TN」), 인스턴스는 id 로 가리킴
  const d = el("div", "tpl-tab"); // 접는 목록(details.more — 그 안의 ul·li·button 규칙이 트리를 망가뜨린다)이 아니라 민짜 그릇
  const head = el("div", "htree-head"), sum = el("b", null, `템플릿 ${(g.templates || []).length}개`);
  sum.title = v2 ? "번호 TN 은 문서 안 문단 표시 「TN L줄」 의 N — 주 사슬 T1 → 가지(문서 순 첫 등장) → 라벨 → 표 칸 차례. 템플릿 = 레터 사슬 하나(앵커 = scope:사슬), 같은 사슬은 어디에 매달려도 같은 TN(유형 번호 「유형 T28」 과는 다른 것 — 템플릿 표기엔 늘 L줄이 붙음)"
    : "번호 TN 은 문서 안 문단 표시 「TN L줄」 의 N — 개요템플릿 → 서브 템플릿 → 표 칸 차례";
  head.append(sum, hHelp("템플릿 번호 도움말", TPL_TREE_HELP));
  d.append(head);
  const box = el("div", "tpl-tree-box");
  const tools = el("div", "hacts tpl-tree-tools");
  tools.append(...tplTreeTools(box));
  const links = el("div", "hacts tpl-tree-links");
  links.append(hBtn("템플릿 관계", () => headsTplView(), { title: "템플릿 관계 — 같은 트리를 문서 옆 열(2열)에 넓게 봅니다" }),
    hBtn("다른 문서와 비교", () => showTab("Compare")));
  d.append(tools, links, box);
  box._tplCount = (n) => { sum.textContent = `템플릿 ${n}개`; };
  tplTreeDraw(box, g, null, "tab");
  return d;
}

// 문서 안 문단별 템플릿 표시 — **쪽 안 왼쪽 여백**(종이 왼끝 ~ 본문 왼끝)에 「TN Lk」(그래프 노드 → 문단; 구분 라벨 노드는 「TN L1 [기관]」 처럼 라벨 식별자까지). 문단 요소(contentEditable) 안에는
// 아무것도 넣지 않고 .sheet 에 절대 위치 표(.tpl-mark)를 얹는다 — 끌기 손잡이(.ol-grip, 본문 왼끝 바로 옆) 바깥쪽에 오른끝 맞춤, 쪽 배율과 무관하게 화면 크기 고정(zoom 1/z).
// 가로 자리는 style.css 가 --mgl(그 쪽 왼쪽 여백 폭, 화면 px — sheetMarginPx)로 잡는다: 여백 폭을 넘는 글은 줄임표(올리면 다 보임). 2쪽 보기도 쪽마다 제 왼쪽 여백.
// 종이 밖(스크롤 상자)에 따로 여백을 두지 않는다(2026-11-10 사용자 「문서 페이지 여백에」 — 옛 .scroller.gutter 없앰). 표 표지(tables.js .tbl-mark)도 같은 여백.
// paginate()·refit() 끝과 창 크기 바뀜 때 다시 그린다(spec_헤딩_추출 ② §7 화면 「문서 표시」). 표를 누르면 템플릿 관계 보기(2열)에서 그 템플릿을 펼친다.
const TPL_MARKS_KEY = "nfm.headsMarks";
const TPL_MARK_H = 17; // 표 한 줄 높이(화면 px — style.css .tpl-mark 15px + 테두리)
const tplRef = (no, name) => (no ? `T${no}` : String(name || "").slice(0, 12)); // 템플릿 표기 「TN」(번호 없는 옛 결과는 이름 앞부분) — 유형 번호 「T28」 과 달리 늘 L줄이 뒤따름
const tplLabelId = (x) => (x.key || "").trim() || "[라벨]"; // 구분 라벨의 식별자 = 정규 라벨 키 「[기관]」(A 호출 basis) — 값(「[한국선급]」)이 아니라 구분 기준
// 구분 라벨 표시의 색 = 그 구분의 「구분 기준 자리」 색(divisions.css 의 [data-dv] — 단계 파랑 · 차년도 초록 · 기관 주황 …: 2026-11-18 사용자 「라벨링이랑 구분 기준 자리 색상좀 매칭해 주고」 —
// 전에는 라벨 표시가 어느 구분이든 청록 하나라 「[기관]」 이 초록인 「차년도」 자리처럼 보였다 · spec_구분_기준 ② §11 「라벨 표시의 색」). x = 라벨 키 「[기관]」 · 구분 기준 이름 「단계-차년도」 ·
// 표 소속의 구분 목록 ["stage", "year"] -> 구분 키(stage · stageYear · year · sub · org · other = 사용자가 더한 이름) | ""(구분 기준을 모름 — 전의 청록 그대로).
// 겹친 이름은 「단계-차년도」 만 제 색, 그 밖은 가장 안쪽 구분의 색(구분 기준 자리의 바탕색과 같은 규칙 — divMembersIndex)
const DV_NAME_KEY = { 단계: "stage", 차년도: "year", 기관: "org", 세부과제: "sub" };
function dvKeyOf(x) {
  const ks = (Array.isArray(x) ? x : String(x || "").replace(/^\[|\]$/g, "").split("-")).map((s) => String(s).trim())
    .filter((s) => s && !["라벨", "…", "N", "가", "period", "total", "ratio"].includes(s)).map((s) => DV_NAME_KEY[s] || (DV_KEY_ORDER.includes(s) ? s : "other")); // 「[라벨]」(기준 모름) · 괄호 소제목 「[…]」 · 번호 레터 「[N]」「[가]」 · 표 머리의 합계·비율은 구분이 아니다
  if (!ks.length) return "";
  if (ks.length === 2 && ks.includes("stage") && ks.includes("year")) return "stageYear";
  return ks.reduce((a, k) => (DV_KEY_ORDER.indexOf(k) > DV_KEY_ORDER.indexOf(a) ? k : a));
}
const dvTag = (e, x) => { const k = dvKeyOf(x); if (k) e.dataset.dv = k; return e; }; // 구분 라벨을 보이는 요소(여백 표 · 표 표지 · 패널 배지 .hb.div)에 그 구분의 색 키
const dvOfDivision = (d) => (d ? ((d.basis || []).length ? d.basis : d.key) : ""); // 표 소속의 구분 라벨(heading_calc _node_owner 의 division) → dvKeyOf 의 입력
function tplMarkText(box, text, m) { // 표기 글 「TN Lk [기관]」 을 box 에 — 구분 라벨 식별자는 그 구분의 색 글(.tm-lab[data-dv]: 한 표에 라벨 아닌 줄이 섞여도 식별자만은 제 색)
  const i = m && m.lab && m.dv ? text.indexOf(m.lab) : -1;
  if (i < 0) { box.append(text); return box; }
  const s = el("span", "tm-lab", m.lab);
  s.dataset.dv = m.dv;
  box.append(text.slice(0, i), s, text.slice(i + m.lab.length));
  return box;
}
function tplMarksOn() { return quickGet(TPL_MARKS_KEY) !== "off"; } // 문서마다 따로 기억(quickKey — 원본 · 목적 문서)
function tplMarksToggle() {
  quickSet(TPL_MARKS_KEY, tplMarksOn() ? "off" : "on");
  tplMarksDraw();
  tplMarkBtnSync();
}
// 서식 라벨 표시(2026-11-15 사용자 「템플릿 아래 서식 라벨도 볼 수 있게」) — 템플릿 표 「TN Lk」 **아래**에 그 문단의 서식 라벨(1단계가 매긴 「S41」 — 그래프 노드의 fmt)을 한 줄 더.
// 아래에 한 줄 자리가 없으면(촘촘한 줄 · 표 칸) 같은 줄 뒤에 붙인다. 기본은 끔(이 브라우저에 기억). 누르면 그 라벨의 문단 목록(2열).
// 2026-11-16 사용자 「이 2개 아이콘을 이걸 봤다 안봤다 하는 용도로」 — 템플릿 표시와 **따로** 켜고 끈다(전에는 템플릿 표시를 끄면 같이 안 보였다): 템플릿 표시를 끄고 이것만 켜면
// 그 줄 자리에 서식 라벨만 보인다. 이름 줄의 아이콘 둘(doc_quick.js)과 「템플릿 관계」 열 위의 「문서 표시」·「서식 라벨」 단추가 같은 값을 켜고 끈다.
const TPL_FMT_KEY = "nfm.headsMarksFmt";
function tplFmtOn() { return quickGet(TPL_FMT_KEY) === "on"; } // 문서마다 따로 기억(quickKey)
function tplFmtToggle() {
  quickSet(TPL_FMT_KEY, tplFmtOn() ? "off" : "on");
  tplMarkBtnSync();
  tplMarksDraw();
  tplFmtGraph();
  fmtsRefreshSoon(true); // 꺼 둔 동안 문서가 바뀌었을 수 있다 — 켤 때 지금 라벨을 다시 읽는다
}
function tplFmtGraph() { // 서식 라벨은 그래프 노드에 있다 — 헤딩 탭을 안 연 작업(오버레이 표시만)이면 그래프를 한 번 읽어 표시를 다시 그린다. -> 읽기 시작했는가
  if (!tplFmtOn() || heads.marks || !heads.outline || !state.id || state.format !== "hwpx" || heads.fmtBusy) return false;
  const id = state.id, epoch = state.epoch;
  heads.fmtBusy = true;
  api(`/api/docs/${id}/headings/graph`).then((g) => {
    if (epoch !== state.epoch) return;
    if (!heads.graph) heads.graph = g; // 그 사이 헤딩 탭이 읽었으면 그것
    if (!heads.marks) heads.marks = tplMarksBuild(heads.graph);
  }).catch(() => { /* 2단계 결과 없음·일시 오류 — 표시는 「TN Lk」 만 */ }).finally(() => { heads.fmtBusy = false; if (epoch === state.epoch) tplMarksDraw(); });
  return true;
}
function tplMarkBtnSync(list = document.querySelectorAll(".tpl-tg-marks, .tpl-tg-fmt")) { // 「문서 표시」·「서식 라벨」 단추의 글·눌림 — 탭과 열 두 곳의 단추를 함께
  for (const b of list) {
    const fmt = b.classList.contains("tpl-tg-fmt"), on = fmt ? tplFmtOn() : tplMarksOn(); // 둘은 따로 켜고 끈다(2026-11-16 — 전에는 「문서 표시」 를 끄면 「서식 라벨」 이 꺼진 단추가 됐다)
    b.textContent = fmt ? "서식 라벨" : "문서 표시"; // 이름·폭은 고정, 실제 표시 상태는 체크·눌림으로
    b.setAttribute("aria-pressed", String(on));
  }
  if (typeof docQuickSync === "function") docQuickSync(); // 이름 줄의 아이콘 둘도 같은 값(doc_quick.js)
}

function tplMarksBuild(g) { // 그래프 → Map(문단 id → {text, title, no, und, lbl}) — 같은 문단의 구간(#1·#2 …) 노드는 하나로 합친다
  const marks = new Map();
  const tplName = new Map((g.templates || []).map((t) => [t.name, t]));
  const instOf = new Map(); // 노드 id → 「인스턴스 n」
  for (const i of g.instances || []) {
    const lab = `${typeof i.template === "number" ? `T${i.template}` : i.template} 인스턴스 ${i.no ?? "?"}${i.text ? ` 「${oneLine(i.text).slice(0, 24)}」` : ""}`;
    instOf.set(i.root, lab);
    for (const m of i.members || []) if (!instOf.has(m)) instOf.set(m, lab);
  }
  for (const x of g.nodes || []) {
    if (!x.template || !x.level || !hasBlock(x.para) || (x.role !== "heading" && x.role !== "title" && !isRooted(x.role))) continue; // 구분 라벨·괄호 소제목도 제 템플릿의 L1(가지 규칙)
    const t = tplName.get(x.template) || {};
    const no = x.tplNo || t.no;
    const lab = x.role === "label" ? tplLabelId(x) : ""; // 식별자 「[기관]」 과 구분의 색(dvKeyOf)은 구분 라벨만 — 괄호 소제목은 보통 색 「TN L1」
    const text = `${tplRef(no, x.template)} L${x.level}${lab ? ` ${lab}` : ""}`;
    const slot = (t.slots || []).find((s) => s.level === x.level);
    const title = `템플릿 ${tplRef(no, x.template)} ${x.template}(${H_TPL[t.kind] || t.kind || "?"}) · ${x.level}번째 줄(레벨 ${x.level})`
      + (slot ? ` 「${((slot.types || [])[0] || {}).shape || "?"}」 ×${nf(slot.count)}` : "")
      + (lab ? `\n구분 라벨 · 기준 ${lab}${x.letter ? ` · 값 「${oneLine(x.letter).slice(0, 30)}」` : ""}` : x.role === "subtitle" ? "\n괄호 소제목(구분 기준 값이 아닌 괄호 글)" : "")
      + (instOf.has(x.id) ? `\n${instOf.get(x.id)}` : "")
      + `\n${x.id} · 유형 ${x.type}${x.undecided ? " · 미판정" : ""}${x.changed ? " · LLM 변경" : ""}` + (no ? "\n누르면 템플릿 관계 보기" : "");
    const was = marks.get(x.para);
    if (was) {
      if (!was.text.includes(text)) { was.text += ` ${text}`; was.title += `\n—\n${title}`; }
      if (x.fmt && !was.fmt.includes(x.fmt)) was.fmt.push(x.fmt);
    } else marks.set(x.para, { text, title, no, und: !!x.undecided, lbl: !!lab, lab, dv: lab ? dvKeyOf(x.basis || lab) : "", fmt: x.fmt ? [x.fmt] : [] }); // fmt = 서식 라벨(「S41」) — 「서식 라벨 보기」 가 템플릿 표 아래에 그린다 · dv = 구분 라벨의 구분 키(색)
  }
  return marks;
}

function olMark(pid, ol, gm) { // 개요 오버레이 줄 → 「TN Lk」 표(spec_hwpx_웹편집 ② §8-2) — 그래프 표(gm)는 미판정 표지만 물려받는다
  const t = heads.outline && heads.outline.templates ? heads.outline.templates[String(ol.tpl)] || {} : {};
  const sl = t.slots ? t.slots[String(ol.level)] || {} : {};
  const lab = ol.role === "label" ? tplLabelId(ol) : "";
  const text = `T${ol.no} L${ol.level}${lab ? ` ${lab}` : ""}`;
  const title = `템플릿 T${ol.no} ${(t.chain || []).join(" › ")} · ${ol.level}번째 줄(레벨 ${ol.level}) 「${oneLine(ol.letter || ol.name || "").slice(0, 30)}」`
    + (t.comp ? `\n종속 템플릿 — T${t.comp.parentNo} L${t.comp.at} 아래 T${t.comp.childNo}` : t.vari ? `\n서식 종속 템플릿 — T${t.vari.ofNo} L${t.vari.level} 의 다른 서식` : "") + (sl.rep === pid ? "\n이 레벨의 대표 줄" : "")
    + (lab ? `\n구분 라벨 · 기준 ${lab}` : ol.role === "subtitle" ? "\n괄호 소제목(구분 기준 값이 아닌 괄호 글)" : ol.role === "table" && t.kind === "band" ? `\n별첨·부록 표 제목 줄 — 「${oneLine(ol.name || "").slice(0, 20)}」 칸과 제목 칸으로 된 표를 헤딩 추출이 스스로 줄로 잡았습니다(문서 맨 위의 줄 · 그 아래 줄은 다음 별첨·부록 표나 장이 올 때까지 이 줄의 것)`
      : ol.role === "table" ? `\n표 제목 줄 — 제목 표를 이 템플릿의 L${ol.level} 로 넣었습니다(Enter = 표 아래에 새 줄)` : "")
    + `\n${pid}\n누르면 문서에서 이 템플릿·레벨의 줄만 또렷이(나머지는 흐리게 · 대표와 여백·서식이 다른 줄 표시) · 다시 누르면 풀림\n켜진 동안 문서에서 휠을 굴리면 다음·앞의 이 템플릿 자리로 — 문서 창 오른쪽 위·아래에 남은 자리 수\n두 번 누르면 「템플릿 관계」 — 이 레벨의 서식 목록에서 이 줄의 서식(대표 정하기 · 대표에 맞추기 · 다른 템플릿으로)`;
  // 서식 라벨(「S41」 — spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」, 2026-11-16 사용자 「대표템플릿인경우 템플릿 클릭하면 서식이 나오니깐 별도 서식번호가 필요 없을거 같은데」):
  // 오버레이 줄은 그 줄의 **지금** 라벨(heads.outline.fmts — 대표에 맞추면 대표의 라벨이 된다: 서버 outline_edit.fmt_view)이고, 그 레벨 대표의 라벨과 같으면 그리지 않는다 — 번호는 대표와 서식이 다른 줄에만 남는다.
  // 서버가 옛 판이면(fmts 없음) 전처럼 그래프 노드의 라벨.
  const fmts = heads.outline.fmts || {};
  const repFmt = sl.rep ? fmts[sl.rep] || "" : "";
  const own = fmts[pid] ? [fmts[pid]] : gm && gm.fmt ? gm.fmt : [];
  const fmt = repFmt && own.length === 1 && own[0] === repFmt ? [] : own;
  return { text, title, no: ol.no, tpl: ol.tpl, level: ol.level, para: pid, und: !!(gm && gm.und), lbl: !!lab, lab, dv: lab ? dvKeyOf(lab) : "", fmt, focus: /^\d+$/.test(String(ol.tpl)) ? +ol.tpl : String(ol.tpl) };
}

// 「템플릿 관계」 열을 연다 — 그래프(2단계)를 아직 안 읽었으면(헤딩 탭을 안 연 작업 · TASK 와 무관) 그때 읽는다. at = {tpl, level, para}: 그 레벨을 펴고 그 줄의 서식 갈래를 표시(outline_match.js)
async function tplRelOpen(focus = null, at = null) {
  if (!state.id || state.format !== "hwpx") { toast("템플릿 관계는 HWPX 문서에서만 볼 수 있습니다"); return; }
  if (!heads.graph) {
    const id = state.id, epoch = state.epoch;
    let g;
    try { g = await api(`/api/docs/${id}/headings/graph`); }
    catch (e) { if (epoch === state.epoch) toast(e.status === 404 ? "헤딩 추출 2단계(헤딩 그래프) 결과가 없습니다 — 헤딩 추출 탭에서 그래프를 만드세요" : `그래프를 읽지 못했습니다: ${e.message}`, true); return; }
    if (epoch !== state.epoch) return;
    if (!heads.graph) heads.graph = g; // 그 사이 헤딩 탭이 읽었으면 그것
  }
  headsTplView(focus);
  if (at && typeof olmFocus === "function") olmFocus(at);
}

// 쪽 여백 표시(템플릿 표시·끌기 손잡이 — 여기, 표 표지 — tables.js)를 그릴 수 있는가 = 문서가 보이고 쪽 보기가 켜져 있는가. 두 그리기 모두 자리를 재기 전에 묻는다.
// 표시는 쪽 **안** 여백에 놓이므로 스크롤 상자 여백·맞춤 배율은 건드리지 않는다(이름은 옛 .scroller.gutter 를 켜고 끄던 때의 것 — tables.js 도 부른다).
function gutterSync() {
  return !$("scroller").hidden && !$("doc").classList.contains("hide-pages");
}
// 그 쪽의 왼쪽 여백 폭(화면 px, z = 쪽 배율) — 표시·손잡이·표지마다 --mgl 로 두면 style.css 가 종이 왼끝 ~ 본문 왼끝 사이에 자리를 잡는다.
// 쪽(.sheet)이 아니라 표시 요소마다 두는 까닭: 상속되는 변수를 쪽에 쓰면 그 쪽의 문단 전부가 스타일을 다시 계산한다
const sheetMarginPx = (sheet, z) => Math.round(((state.sections[+sheet.dataset.sec] || DEFAULT_PAGE).marginsMm.l || 0) * PX_PER_MM * z * 10) / 10;

function tplMarksDraw() {
  if (typeof pgDraw === "function") pgDraw(); // 오른쪽 여백의 「지침」 단추(place_guides.js — 다음 프레임에 한 번: 배율 · 창 크기 · 쪽 다시 나눔 · 오버레이 · 쪽 보기 — 아래의 이른 return 과 무관하게)
  for (const e of document.querySelectorAll(".tpl-mark, .ol-grip")) e.remove();
  if (typeof docQuickSync === "function") docQuickSync(); // 이름 줄의 표시 아이콘 둘(doc_quick.js) — 표시할 것이 있는 문서인지가 여기서 바뀐다(오버레이·그래프를 읽은 뒤)
  if (typeof ddDraw === "function") ddDraw(); // 고친 곳 보기의 꼬리표(doc_diff.js) — 여기는 배율·창 크기가 바뀔 때도 불린다(꼬리표는 화면 크기 고정 — 자리를 다시): 다음 프레임에 한 번
  const tplOn = tplMarksOn(), fmtOn = tplFmtOn(); // 템플릿 표시 「TN Lk」 와 서식 라벨 「S41」 — 따로 켜고 끈다(2026-11-16): 서식 라벨만 켜면 그 줄 자리에 라벨만
  const marks = heads.marks && (tplOn || fmtOn) ? heads.marks : new Map();
  const tmpOf = typeof tempMarkOf === "function" && tplOn && tempMarkCount() ? tempMarkOf : null; // TEMP 문단·칸(heading_temp.js — spec ② §15): 「TN Lk」 가 없는 줄에 회색 「TEMP」
  const drOf = typeof driftMarkOf === "function" && tplOn && driftMarkCount() ? driftMarkOf : null; // 뼈대에 없는 새 레터·새 서식 문단(heading_drift.js — spec ② §17): 주황 「새 레터」·「새 서식」
  const capOf = typeof captMarkOf === "function" && tplOn && captMarkCount() ? captMarkOf : null; // 캡션 줄(caption_tpl.js — spec_hwpx_웹편집 ② §8-10): 「TN Lk」·TEMP 가 없는 캡션 줄에 보라 「C1」
  const shown = gutterSync();
  const tblPlace = () => { if (typeof tblMarksPlace === "function") tblMarksPlace(); }; // 같은 여백의 표 표지(tables.js)는 「TN Lk」 표·손잡이를 피해 자리를 다시 잡는다
  if (!shown || !(marks.size || heads.outline || tmpOf || drOf || capOf)) { tblPlace(); return; }
  // 읽기 단계(쪽·문단 자리를 모두 먼저) → 쓰기 단계(표·손잡이 붙이기). 쪽마다 재고 붙이기를 번갈아 하면 쪽 수(65)만큼, 손잡이는 문단마다 강제 배치가 되어
  // 연구개발계획서 양식에서 28 s 멈췄다(2026-11-10 실측 → 나눠서 0.03 s, spec_owpml_편집 ③). 표·손잡이가 필요한 문단만 잰다(outlineLine 은 자료 조회뿐).
  const jobs = [];
  for (const sheet of document.querySelectorAll("#doc .sheet")) {
    const sr = sheet.getBoundingClientRect();
    const z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1; // 쪽 배율 — 표·손잡이는 zoom 1/z 로 되돌려 화면 크기를 고정하고, 자리는 화면 px 로 둔다
    const found = [], grips = [];
    for (const p of sheet.querySelectorAll(".para[data-id]")) {
      const ol = outlineLine(p);
      // 개요 오버레이 줄이면 그 「TN Lk」 가 먼저(문서를 열 때 바로 — 헤딩 탭을 안 열어도 · 종속·레벨 바꿈이 바로 보임: spec_hwpx_웹편집 ② §8-2), 아니면 그래프 표
      let m = (ol && (tplOn || fmtOn) ? olMark(p.dataset.id, ol, marks.get(p.dataset.id)) : null) || marks.get(p.dataset.id) || (tmpOf && tmpOf(p.dataset.id)) || (capOf && capOf(p.dataset.id));
      if (drOf) m = drOf(p.dataset.id, m) || m; // 그 문단의 표시 앞에 「새 레터」·「새 서식」 을 얹는다(「TN Lk」 가 없으면 그것만)
      if (m && !tplOn && !(m.fmt && m.fmt.length)) m = null; // 서식 라벨만 보는 중 — 라벨이 없는 줄에는 그릴 것이 없다
      if (!m && !ol) continue;
      const top = p.getBoundingClientRect().top - sr.top;
      if (m) found.push({ top, m });
      if (ol && !p.closest("td")) grips.push({ p, ol, top }); // 본문 개요 줄마다 끌기 손잡이(쪽 안 왼쪽 여백 — 본문 왼끝 바로 옆)
    }
    jobs.push({ sheet, z, mgl: sheetMarginPx(sheet, z), found, grips });
  }
  for (const { sheet, z, mgl, found, grips } of jobs) {
    const place = (e, top) => { e.style.zoom = String(1 / z); e.style.setProperty("--mgl", `${mgl}px`); e.style.top = `${Math.round(top)}px`; sheet.append(e); };
    for (const g of grips) place(outlineGrip(g.p, g.ol, g.top), g.top);
    found.sort((a, b) => a.top - b.top);
    const rows = []; // 같은 높이(표 한 행의 칸들)·표 한 줄 높이(TPL_MARK_H) 안에 붙은 줄들은 한 표에 모아 겹치지 않게
    for (const f of found) {
      const r = rows[rows.length - 1];
      if (r && f.top - r.top < TPL_MARK_H) { r.items.push(f.m); r.und = r.und || f.m.und; r.lbl = r.lbl && f.m.lbl; r.temp = r.temp && !!f.m.temp; }
      else rows.push({ top: f.top, items: [f.m], und: !!f.m.und, lbl: !!f.m.lbl, temp: !!f.m.temp });
    }
    for (const [k, r] of rows.entries()) {
      const dr = r.items.some((m) => m.drift); // 뼈대 밖 문단이 든 줄 — 주황, 누르면 뼈대 밖 목록(② §17)
      const cm = r.items.find((m) => m.cap); // 캡션 줄 「C1」(caption_tpl.js) — 그 줄뿐인 표는 보라, 누르면 「템플릿 관계」 의 캡션 템플릿
      const s = el("span", "tpl-mark" + (r.und ? " und" : "") + (r.lbl ? " lbl" : "") + (r.temp ? " temp" : "") + (dr ? " drift" : "") + (cm && r.items.every((m) => m.cap) ? " cap" : ""));
      const dvs = r.lbl ? new Set(r.items.map((m) => m.dv || "")) : null; // 구분 라벨 줄뿐인 표 — 줄들의 구분이 하나면 표의 테두리·바탕도 그 구분의 색(dvKeyOf)
      if (dvs && dvs.size === 1 && !dvs.has("")) s.dataset.dv = [...dvs][0];
      const cnt = new Map(); // 같은 표기(표 한 행의 같은 템플릿·레벨 칸들)는 「T11 L2 ×2」 로 모은다 — 표기 → {n, m(그 표기의 첫 줄)}
      for (const m of r.items) { const c = cnt.get(m.text); if (c) c.n += 1; else cnt.set(m.text, { n: 1, m }); }
      const texts = [...cnt].map(([t, c]) => ({ text: c.n > 1 ? `${t} ×${c.n}` : t, m: c.m }));
      // 누르면 그 템플릿·레벨의 줄만 또렷이(fmt_focus.js tplFocusToggle — spec_헤딩_추출 ② §7 「템플릿만 또렷이」, 2026-11-15 사용자 「템플릿도 클릭하면 똑같이 동일한 템플릿만」): 개요 오버레이 줄의 표기마다 눌리는 글(.tm-t —
      // 한 표에 여럿이면 누른 그 표기). 전에 누르면 열리던 「템플릿 관계」 는 이름 줄 설명의 단추가 연다. 오버레이 줄이 아닌 표(그래프만 · 뼈대 밖 · TEMP)는 전과 같다
      const focusable = !dr && typeof tplFocusToggle === "function";
      // 두 번 누르면 「템플릿 관계」 의 그 레벨 · 이 줄의 서식으로(2026-11-17 사용자 「T1 L3 더블클릭하면 템플릿 관계로 가줘야 하는거 아냐?」 — spec_헤딩_추출 ② §7 「템플릿만 또렷이」).
      // 한 번 누름(또렷이 켜고 끄기)은 그대로 · 둘째 누름(detail 2)은 켜고 끄지 않고, 두 번 누름은 또렷이를 켠 채 둔다(첫 누름이 껐으면 다시 켬). 열이 열려 있으면 다시 짓지 않고 그 줄로(outline_match.js olmLookFrom)
      const relGo = (m) => {
        if (typeof tplFocusIs === "function" && !tplFocusIs(m.tpl, m.level)) tplFocusOn(m);
        const at = m.para ? { tpl: m.tpl, level: m.level, para: m.para } : null;
        if (at && typeof olmLookFrom === "function") olmLookFrom(at, m.focus ?? m.no); else tplRelOpen(m.focus ?? m.no, at);
      };
      texts.slice(0, 3).forEach((x, i) => { // 글은 전과 같다 — 「A · B · C +n」
        if (i) s.append(" · ");
        if (!focusable || x.m.tpl == null) { tplMarkText(s, x.text, x.m); return; }
        const b = tplMarkText(el("span", "tm-t"), x.text, x.m);
        b.dataset.tpl = String(x.m.tpl);
        b.dataset.level = String(x.m.level);
        b.setAttribute("role", "button");
        b.onclick = (e) => { e.stopPropagation(); if (e.detail < 2) tplFocusToggle(x.m); };
        b.ondblclick = (e) => { e.stopPropagation(); relGo(x.m); };
        s.append(b);
      });
      if (texts.length > 3) s.append(` +${texts.length - 3}`);
      s.title = r.items.map((m) => m.title).join("\n═══\n");
      const hit = r.items.find((m) => m.no) || {}, no = hit.no;
      if (dr && typeof driftView === "function") { s.setAttribute("role", "button"); s.onclick = () => driftView(); }
      else if (no && focusable && hit.tpl != null) { s.setAttribute("role", "button"); s.onclick = (e) => { if (e.detail < 2) tplFocusToggle(hit); }; s.ondblclick = () => relGo(hit); } // 글 사이·「+n」 을 눌러도 첫 표기
      else if (no) { s.setAttribute("role", "button"); s.onclick = () => tplRelOpen(hit.focus ?? no, hit.para ? { tpl: hit.tpl, level: hit.level, para: hit.para } : null); }
      else if (cm && typeof captOpen === "function") { s.setAttribute("role", "button"); s.onclick = () => captOpen(cm.cap, cm.para); } // 캡션 줄 — 누르면 그 캡션 템플릿의 서식 목록
      else if (r.temp && typeof tempView === "function") { s.setAttribute("role", "button"); s.onclick = () => tempView(); } // TEMP 줄 — 누르면 TEMP 목록
      const fm = fmtOn ? [...new Set(r.items.flatMap((m) => m.fmt || []))] : []; // 서식 라벨(「S41」) — 템플릿 표 아래 한 줄(자리가 없으면 같은 줄 뒤에)
      if (fm.length) {
        // 누르면 그 서식만 또렷이(fmt_focus.js — spec_헤딩_추출 ② §7 「서식 라벨만 또렷이」, 2026-11-15 사용자 「요 서식을 클릭하면 문서에서 이 부분만 잘 보이고」): 라벨마다 눌리는 글(.tm-f — 여럿이면 누른 그 라벨).
        // 전에 누르면 열리던 그 라벨의 문단 목록은 이름 줄 설명의 「목록」 단추가 연다(그 스크립트가 없으면 전처럼 바로 목록)
        // 「≠」 = 대표의 서식이던 줄이 손으로 바뀌어 대표와 달라진 것(번호는 다시 추출해야 안다 — 서버 outline_match.OFF): 그 서식을 또렷이 볼 수 없으니 「템플릿 관계」 의 그 줄 갈래로(다른 값이 거기 보인다)
        // 「≈」 = 그런 줄 가운데 대표와 거의 같은 줄(레터가 같고 값 차이가 오차 안 — 서버 outline_match.NEAR · 2026-11-16 사용자 「≠ 이거는 유사한 의미가 아니라 ≈ 이걸로」): 「≠」 는 레터가 다르거나 오차 밖일 때만. 둘 다 번호가 아니라 누르면 같은 곳으로
        const OFFS = { "≈": "≈ — 대표와 거의 같음: 레터가 같고 값 차이가 오차 안입니다(추출이 대표와 같은 서식 번호로 묶는 줄)\n누르면 「템플릿 관계」 에서 무엇이 다른지 보입니다 · 「대표에 맞추기」 로 맞춥니다",
          "≠": "≠ — 대표와 다름: 레터가 다르거나 값 차이가 오차 밖인데 제 서식 번호가 없습니다(추출한 뒤에 바뀐 줄)\n누르면 「템플릿 관계」 에서 무엇이 다른지 보입니다" };
        const pick = (id) => (OFFS[id] ? tplRelOpen(hit.focus ?? no, hit.para ? { tpl: hit.tpl, level: hit.level, para: hit.para } : null)
          : typeof fmtFocusToggle === "function" ? fmtFocusToggle(id) : headsParas({ fmt: id }));
        const nums = fm.filter((id) => !OFFS[id]); // 번호 라벨(「S41」)과 번호 아닌 표시(「≈」·「≠」)의 도움말은 따로
        const tip = [...fm.filter((id) => OFFS[id]).map((id) => OFFS[id]),
          ...(nums.length ? [`서식 라벨 ${nums.join(" · ")} — 1단계가 서식이 같은 문단끼리 묶어 매긴 이름\n누르면 문서에서 그 서식의 문단만 또렷이(나머지는 흐리게) · 다시 누르면 풀림 · 켜진 동안 휠을 굴리면 다음·앞의 그 서식 자리로`] : [])].join("\n");
        const fill = (f) => { // 글은 전과 같다 — 「S30 S32」 · 넷부터 「+n」
          fm.slice(0, 3).forEach((id, i) => {
            const b = el("span", "tm-f", id);
            b.dataset.fmt = id;
            b.setAttribute("role", "button");
            b.onclick = (e) => { e.stopPropagation(); pick(id); };
            if (i) f.append(" ");
            f.append(b);
          });
          if (fm.length > 3) f.append(` +${fm.length - 3}`);
          f.title = tip;
          f.onclick = (e) => { e.stopPropagation(); pick(fm[0]); }; // 글 사이·「+n」 을 눌러도 첫 라벨
          return f;
        };
        const next = rows[k + 1];
        if (!tplOn) place(fill(el("span", "tpl-mark fmt")), r.top); // 템플릿 표시를 끈 채 서식 라벨만 — 「TN Lk」 가 있던 그 줄 자리에 라벨만
        else if (!next || next.top - r.top >= TPL_MARK_H * 2 - 3) place(fill(el("span", "tpl-mark fmt")), r.top + TPL_MARK_H - 2);
        else {
          s.append(" ", fill(el("span", "tm-fmt")));
          s.title += `\n${tip.split("\n")[0]}`;
        }
      }
      if (tplOn) place(s, r.top);
    }
  }
  if (typeof fmtFocusMarks === "function") fmtFocusMarks(); // 고른 서식 라벨·템플릿 표기(「서식 라벨만 또렷이」·「템플릿만 또렷이」 — fmt_focus.js)의 눌림을 새로 그린 표에도
  if (typeof tblMarksPlace === "function") tblMarksPlace(); // 표 표지가 먼저 그려져 있으면 새 「TN Lk」 표와 겹치지 않게 내려 놓는다
}
window.addEventListener("resize", () => { if (heads.marks || heads.outline || (typeof tempMarkCount === "function" && tempMarkCount()) || (typeof driftMarkCount === "function" && driftMarkCount()) || (typeof captMarkCount === "function" && captMarkCount())) tplMarksDraw(); });

// ---------------------------------------------------------------- 템플릿 관계 보기(2열 kind "templates", spec_헤딩_추출 ② §7 「템플릿 관계」)
// 템플릿을 매달린 자리(부모 템플릿·레벨)로 이은 트리 — 인스턴스의 parent 노드가 (TN, Lk) 이면 그 템플릿은 TN 의 k번째 줄 아래 가지. 「TN」 을 누르면 레벨(줄)마다 레터·문단 수와
// 그 줄에 매달린 가지 템플릿이 펼쳐지고, 「인스턴스」 를 펼치면 자리마다 문서로 갈 수 있다. 되돌이(제 조상과 같은 템플릿)는 표시만 하고 더 펼치지 않는다.
function tplRel(g) { // 그래프 → {tpl: Map(id → 템플릿), node: Map(노드 id → 노드), under: Map("부모 id|레벨" → Map(자식 id → 인스턴스 수)), at: Map(자식 id → Map(자리 → 수)), inst: Map(id → [인스턴스])}
  const byName = new Map((g.templates || []).map((t) => [t.name, t]));
  const idOf = (ref) => (typeof ref === "number" ? ref : ((byName.get(ref) || {}).id ?? (byName.get(ref) || {}).no ?? null)); // v1 결과는 이름으로 가리킴
  const tpl = new Map((g.templates || []).map((t) => [t.id ?? t.no, t]));
  const node = new Map((g.nodes || []).map((x) => [x.id, x]));
  const under = new Map(), at = new Map(), inst = new Map();
  const add = (m, k, c) => { const v = m.get(k) || new Map(); v.set(c, (v.get(c) || 0) + 1); m.set(k, v); };
  for (const i of g.instances || []) {
    const id = idOf(i.template);
    if (id == null) continue;
    const p = node.get(i.parent);
    const where = p && p.tplNo && p.level ? `${p.tplNo}|${p.level}` : p ? "other" : (!i.parent || i.parent === "root" ? "root" : "cell");
    add(under, where, id);
    add(at, id, where);
    if (!inst.has(id)) inst.set(id, []);
    inst.get(id).push(i);
  }
  return { tpl, node, under, at, inst };
}

const TPL_TREE_HELP = "TN 은 이 문서의 템플릿 번호, Lk 는 템플릿 안 레벨입니다(문서 왼쪽 여백의 「TN Lk」 와 같은 번호). 템플릿마다 개요 레벨 그림 — 레벨마다 레터 · 글꼴·크기·굵기 · 들여쓰기(그 레벨 대표 줄의 서식) — 이 먼저 보이고, "
  + "T번호나 화살표를 누르면 레벨 줄(자리 · 서식 목록 · 대표에 맞추기)과 그 레벨에 매달린 하위 템플릿이 펼쳐집니다. 「대표 맞추기」 는 이 템플릿의 레벨마다 대표와 서식이 다른 줄을 한 번에 대표 모양으로 맞추고, 「다른 서식 보기」 는 그 다른 서식을 레벨마다 그림 아래에 펴 보입니다(견본 글 · 지금 값 → 대표 값 · 서식마다 맞추기). 「하위로」 는 템플릿을 다른 템플릿 레벨 아래의 종속 템플릿(「T1T3」)으로 넣어 그 줄들만 따로 맞추게 하고, "
  + "별 모양 단추는 서식 정리 에이전트(Opus 5.5)를 엽니다. 인스턴스를 펼치면 원문으로 이동합니다. 되돌이는 상위에 이미 나온 템플릿이므로 반복해서 펼치지 않습니다. "
  + "「종속 템플릿」 절은 본문 템플릿의 레벨 아래에 매달린 템플릿을 하나씩 따로 보입니다(부모 템플릿을 펼친 레벨 아래에도 보입니다).";
const TPL_SUB_HELP = "본문 템플릿의 레벨 아래에 매달린 템플릿입니다 — 그 레벨 아래로 갈라진 다른 레터의 템플릿(「T1 L2 아래」 — 매달린 자리), 「하위로」 로 넣어 만든 종속 템플릿(「T1T3」), 서식이 달라 뗀 서식 종속 템플릿(「T1L3a」). "
  + "부모 템플릿을 펼치지 않아도 템플릿마다 그림 · 단추가 따로 보입니다. 부모 템플릿을 펼친 레벨 아래에도 그대로 보입니다. 줄을 모두 종속 템플릿으로 넣은 템플릿은 여기서 빠집니다(그 줄은 종속 템플릿에 있습니다).";

function tplTreeTools(root) { // 트리 위 공용 단추 — 문서 표시 · 서식 라벨 · 모두 펼치기 · 모두 접기(「템플릿」 탭과 「템플릿 관계」 열이 같이 쓴다)
  const tg = hBtn("", () => tplMarksToggle(), { cls: "btn sm tpl-tg-marks",
    title: "문서의 문단마다 「T템플릿 L줄」 표시를 쪽 왼쪽 여백에 보입니다(이 브라우저에 기억) · 라벨 문단은 「T5 L1 [기관]」 처럼 라벨 식별자까지" });
  const fg = hBtn("", () => tplFmtToggle(), { cls: "btn sm tpl-tg-fmt",
    title: "문서의 템플릿 표시 아래에 그 문단의 서식 라벨(「S41」 — 1단계가 서식이 같은 문단끼리 묶어 매긴 이름)도 보입니다(이 브라우저에 기억) · 서식 라벨을 누르면 문서에서 그 서식의 문단만 또렷이 보입니다(나머지는 흐리게 · 다시 누르면 풀림)" });
  tplMarkBtnSync([tg, fg]);
  const display = el("div", "tpl-tool-group tpl-display-tools"), tree = el("div", "tpl-tool-group tpl-expand-tools");
  display.setAttribute("role", "group");
  display.setAttribute("aria-label", "문서 표시 옵션");
  tree.setAttribute("role", "group");
  tree.setAttribute("aria-label", "템플릿 펼침·접기");
  display.append(tg, fg);
  tree.append(
    hBtn("모두 펼치기", () => { for (let k = 0; k < 30; k += 1) { const todo = [...root.querySelectorAll('.trel-row > .htog[aria-expanded="false"]')]; if (!todo.length) break; todo.forEach((b) => b.click()); } }),
    hBtn("모두 접기", () => root.querySelectorAll('.trel-row > .htog[aria-expanded="true"]').forEach((b) => b.click())));
  return [display, tree];
}

function headsTplView(focus = null) { // 「템플릿 관계」(2열 kind "templates") — focus = 펼쳐 보일 템플릿 id(문서 표시·배지·번호를 눌렀을 때). 몸은 「템플릿」 탭과 같은 트리(tplTreeDraw)
  const g = heads.graph;
  if (!g) { toast("헤딩 그래프(2단계)가 아직 없습니다 — 헤딩 추출 탭에서 그래프를 만들거나 읽은 뒤에 볼 수 있습니다"); return; }
  const { tools, body } = headsDlg("templates", "템플릿 관계", "");
  $("headsDlgHelp").append(hHelp("템플릿 관계 도움말", TPL_TREE_HELP));
  const root = el("div", "tpl-tree");
  const tplSrc = headsSourceChip(heads.view, 2, false); // 이 그래프가 LLM 것인지 스크립트 것인지 · 끝난 때 · 걸린 시간(② §7 「LLM 표시」)
  if (tplSrc) {
    const source = el("div", "tpl-tools-source");
    source.append(tplSrc);
    tools.append(source);
  }
  tools.append(...tplTreeTools(root));
  body.append(root);
  root._tplCount = (n) => { if (root.isConnected) $("headsDlgNote").textContent = `템플릿 ${n}개 · 인스턴스 ${nf(((heads.graph || g).instances || []).length)}`; };
  if (!heads.keepFold && heads.tplOpen) delete heads.tplOpen.col; // 열을 여는 동작(단추 · 문서 표 · 도구 줄)은 접힌 트리에서 focus 까지만 편다 — 펼친 것의 기억은 배경에서 다시 그릴 때(keepFold · tplTreeRefresh)만 쓴다
  tplTreeDraw(root, g, focus, "col");
}

// 템플릿 트리 — 「템플릿 관계」(2열 · where "col")와 헤딩 추출 「템플릿」 탭(where "tab")이 같이 쓰는 그리기(같은 내용 = 같은 UI: 2026-11-15 사용자).
// 템플릿을 매달린 자리로 이은 트리: 템플릿 줄 [▸][TN] 사슬 · 수 · 정리 에이전트 · 정보 + 종속 표지·하위로·대표 맞추기·다른 서식 보기(outline_match.js · outline_odd.js) → 개요 레벨 그림(olmPic — 서식 복사의 서식 견본과 같은 그림) · 다른 서식 묶음(olmOddBox — 펼친 것만)
// · 원문 보기 → 펼치면 레벨 줄(자리 줄 olfRow · 서식 갈래 olmRow · 괄호 글 목록 · 그 레벨의 가지 템플릿) · 인스턴스. 펼친 템플릿은 자리(where)마다 기억해 다시 그려도 펼친 채다.
// -> 템플릿 수(종속 템플릿 포함)
function tplTreeDraw(root, g, focus = null, where = "tab") {
  const keep = heads.tplOpen || (heads.tplOpen = {});
  if (!keep[where] || keep[where].epoch !== state.epoch) keep[where] = { epoch: state.epoch, set: new Set() }; // 다른 문서를 열었으면 비운다
  const openSet = keep[where].set;
  root.classList.add("tpl-tree");
  root.dataset.where = where;
  root.dataset.ov = tplOvKey(); // 그릴 때의 오버레이(없음 · 실행 · 템플릿 목록) — 그 뒤 오버레이가 바뀌면(처음 읽음 · 2단계 다시 · 종속 넣기·떼기·실행 취소) 다시 그린다(tplTreeRefresh)
  root._tplRedraw = (f = null) => tplTreeDraw(root, heads.graph || g, f, where);
  root.replaceChildren();
  const rel = tplRel(g);
  if (typeof olmRel === "function") olmRel(rel); // 종속 템플릿 「T1T3」(개요 오버레이 — outline_match.js, spec_hwpx_웹편집 ② §8-2)을 (A, at) 아래 가지로
  const idOf = (t) => t.id ?? t.no;
  const byNo = (a, b) => String(a.no ?? "").localeCompare(String(b.no ?? ""), "en", { numeric: true }); // 「T1T3」 같은 글 번호도
  const tpls = [...rel.tpl.values()].sort(byNo);
  const tplNoOf = (raw) => { const t = rel.tpl.get(/^\d+$/.test(raw) ? +raw : raw); return t && t.no != null ? t.no : raw; }; // 자리 키의 템플릿 id → 표기 번호(종속 템플릿 「1~4b」 → 「1L4b」)
  const placeName = (k) => (k === "root" ? "문서 최상위" : k === "cell" ? "표 칸" : k === "other" ? "템플릿 밖 노드" : `T${tplNoOf(k.split("|")[0])} L${k.split("|")[1]}`);
  const levels = (t, id, path) => { // 펼친 몸통 — 매달린 자리 · 줄(레벨)마다 레터·수·그 줄의 가지 템플릿 · 인스턴스 목록(문서로)
    const box = el("div", "trel-body");
    const slots = t.slots || [];
    const kidLevels = [...rel.under.keys()].filter((k) => k.split("|")[0] === String(id)).map((k) => +k.split("|")[1]);
    const ot = heads.outline && heads.outline.templates ? heads.outline.templates[String(id)] : null; // 개요 오버레이(종속으로 늘어난 레벨 — spec_hwpx_웹편집 ② §8-2)
    const sh = ot && ot.lift ? ot.lift.depth || 1 : 0; // 표 제목을 표 레벨로 넣은 템플릿(spec_hwpx_웹편집 ② §8-7) — 오버레이 레벨 = 그래프 레벨 + 표 레벨 수(그래프의 슬롯·가지 템플릿은 L − sh 로 읽는다)
    const maxL = Math.max(slots.length ? Math.max(...slots.map((s) => s.level)) + sh : 0, (t.chain || []).length + sh, kidLevels.length ? Math.max(...kidLevels) + sh : 0, ot ? ot.max || 0 : 0);
    const ol = el("ol", "trel-levels");
    const base = ot && ot.base ? ot.base : 0; // 종속 템플릿 — L1~L base 는 부모 템플릿의 레벨(그 줄은 부모 것)
    if (base && ot.comp) box.append(el("p", "hnote olm-shared", `L1~L${base} = T${ot.comp.parentNo} 의 레벨 「${(ot.chain || []).slice(0, base).join(" › ")}」 — 이 템플릿의 줄은 L${base + 1} 부터`));
    else if (base && ot.vari) box.append(el("p", "hnote olm-shared", `L1${base > 1 ? `~L${base}` : ""} = T${ot.vari.ofNo} 의 레벨 「${(ot.chain || []).slice(0, base).join(" › ")}」 — 이 템플릿의 줄은 L${base + 1} 부터(T${ot.vari.ofNo} L${ot.vari.level} 에서 서식이 달라 뗀 템플릿)`)); // 서식 종속 템플릿 「T1L3a」(spec_hwpx_웹편집 ② §8-5)
    for (let L = base + 1; L <= maxL; L += 1) {
      const s = slots.find((x) => x.level === L - sh) || {};
      const os = ot && ot.slots ? ot.slots[String(L)] : null;
      const li = el("li");
      li.value = L;
      const head = el("div", "trel-level");
      const ltr = os && os.table ? (os.name ? `표 제목 · ${os.name}` : "표 제목") : (base ? os && os.letter : s.letter) || (os && os.letter) || (ot && ot.chain || [])[L - 1] || (t.chain || [])[L - 1 - sh] || "?"; // os.name = 띠 표 템플릿의 이름표 꼴(「별첨N」 — spec_헤딩_추출 ② §6 「띠 표 줄」)
      head.append(el("b", null, `L${L}`), " ", el("span", "trel-let", `「${ltr}」`),
        el("span", "muted trel-cnt", os ? ` ×${nf(os.lines)}` : s.count != null ? ` ×${nf(s.count)}` : " (이 문서엔 없음)"));
      if (s.format) head.append(el("span", "slot-format", `서식 ${s.format}`)); // 그 레벨의 대표 서식 라벨(2단계 — 문서 표시의 「서식 라벨」 과 같은 이름)
      head.title = `${L}번째 줄(레벨 ${L})${s.format ? ` · 대표 서식 ${s.format}${s.formats ? `(${Object.entries(s.formats).map(([k, n]) => `${k} ${n}`).join(" · ")})` : ""}` : ""}${(os && os.rep) || s.rep ? ` · 대표 문단 ${(os && os.rep) || s.rep}` : ""}`;
      li.append(head);
      const place = typeof olfRow === "function" ? olfRow(id, L) : null; // 개요 줄 자리 — 레터 위치·글 시작·둘째 줄 + 고치기(outline_format.js, spec_hwpx_웹편집 ② §8-1)
      if (place) li.append(place);
      const fmts = typeof olmRow === "function" ? olmRow(id, L) : null; // 서식 갈래 · 대표 정하기 · 대표에 맞추기(outline_match.js, spec_hwpx_웹편집 ② §8-2)
      if (fmts) li.append(fmts);
      if (L - sh === 1 && typeof divLabelsList === "function") { // 괄호 줄이 뿌리인 템플릿 — 그 괄호 글 목록 + 구분 라벨 지정(heading_labels.js, spec ② §13)
        const list = divLabelsList(g, t);
        if (list) li.append(list);
      }
      const kids = rel.under.get(`${id}|${L - sh}`);
      const shown = kids ? [...kids].filter(([cid]) => !(typeof olmHidden === "function" && olmHidden(cid, id, L))) : []; // 이 레벨 아래로 다 넣은 템플릿은 레벨로 보인다(② §8-2)
      if (shown.length) {
        const ul = el("ul", "trel");
        for (const [cid, n] of shown.sort((a, b) => byNo(rel.tpl.get(a[0]) || {}, rel.tpl.get(b[0]) || {}))) ul.append(make(cid, path, n));
        li.append(ul);
      }
      ol.append(li);
    }
    box.append(maxL ? ol : el("p", "hnote", "줄(레벨) 정보 없음"));
    const ins = rel.inst.get(id) || [];
    if (ins.length) {
      const d = el("details", "trel-inst");
      d.append(el("summary", null, `인스턴스 ${nf(ins.length)}`));
      const ul = el("ul", "hlist");
      for (const i of ins.slice(0, 300)) {
        const li = el("li");
        const node = rel.node.get(i.root) || {};
        li.append(`${i.no ?? "?"}. `, headsParaLink(node.para || i.root, `${(node.letter || "").trim()} ${i.text || node.text || ""}`.trim() || "(빈 글)", 36, i.path ? `자리 ${i.path}` : ""));
        if (i.basis) li.append(" ", dvTag(el("span", "hb div", i.basis), i.basis));
        if (i.deviates) li.append(" ", el("span", "hb und", `빠진 줄 ${(i.missing || []).map((L) => `L${L}`).join("·") || "있음"}`));
        ul.append(li);
      }
      if (ins.length > 300) ul.append(el("li", "muted", `… ${nf(ins.length - 300)}개 더`));
      d.append(ul);
      box.append(d);
    }
    return box;
  };
  const make = (id, path, here = null, hang = false) => { // 템플릿 한 줄 — [▸] [TN] 사슬 · 구실 · 인스턴스 수(여기 매달린 수) + 개요 레벨 그림. hang = 매달린 자리 「T1 L2 아래」 도(「종속 템플릿」 절)
    const t = rel.tpl.get(id) || { no: id, chain: [], kind: "?" };
    const li = el("li", `trel-node k-${t.kind || "x"}`);
    li.dataset.tpl = id;
    const row = el("div", "trel-row");
    const tog = el("button", "htog", "▸");
    tog.type = "button";
    tog.setAttribute("aria-label", `T${t.no ?? id} 펼치기·접기`);
    tog.setAttribute("aria-expanded", "false");
    const num = el("button", "hb tplno", `T${t.no ?? id}`);
    num.type = "button";
    if (t.kind === "label") dvTag(num, (t.chain || [])[0]); // 구분 라벨 템플릿의 번호 배지 = 그 구분의 「구분 기준 자리」 색(문서 여백의 「TN L1 [기관]」 과 같은 색 — spec_구분_기준 ② §11 「라벨 표시의 색」)
    num.title = `앵커 ${t.anchor || t.name || "—"} · 누르면 레벨(줄) 펼치기·접기`;
    const ins = rel.inst.get(id) || [];
    const name = el("span", "trel-name", t.displayName || (t.chain || []).join(" › ") || t.name || "");
    const meta = el("span", "trel-meta", `${nf(ins.length)}곳${here != null && here !== ins.length ? ` · 여기 ${nf(here)}` : ""}`);
    const places = [...(rel.at.get(id) || new Map())].map(([k, n]) => `${placeName(k)} ×${nf(n)}`);
    const info = `${H_TPL[t.kind] || t.kind || "?"}${H_ROOT[t.rootRole] || ""} · 인스턴스 ${nf(ins.length)}개\n연결 위치: ${places.join(" · ") || "알 수 없음"}\n앵커: ${t.anchor || t.name || "—"}`;
    const cyc = path.includes(id);
    const agent = !cyc && typeof tplAgentIcon === "function" ? tplAgentIcon(id) : null; // 서식 정리 에이전트(tpl_agent.js — spec_hwpx_웹편집 ② §8-4)
    const ot0 = hang && typeof olmTpl === "function" ? olmTpl(id) : null;
    const ups = hang && !(ot0 && (ot0.comp || ot0.vari)) ? [...(rel.at.get(id) || new Map())].filter(([k]) => k.includes("|")).sort((a, b) => b[1] - a[1]) : []; // 종속 표지가 있는 템플릿은 표지가 자리를 말한다
    const up = ups.length ? el("span", "trel-hang", `${ups.slice(0, 3).map(([k]) => placeName(k)).join(" · ")}${ups.length > 3 ? ` +${ups.length - 3}` : ""} 아래`) : null;
    if (up) up.title = `매달린 자리 — ${ups.map(([k, n]) => `${placeName(k)} 아래 ${nf(n)}곳`).join(" · ")}`;
    row.append(tog, num, name, meta, ...(up ? [up] : []), ...(agent ? [agent] : []), hHelp(`T${t.no ?? id} 템플릿 정보`, info, { note: true }));
    li.append(row);
    if (typeof olmTplTools === "function") olmTplTools(li, row, id); // 종속 표지 · 하위로 넣기 · 떼기 · 대표 맞추기 · 다른 서식 보기(outline_match.js · outline_odd.js, spec_hwpx_웹편집 ② §8-2)
    if (typeof olLiftTools === "function") olLiftTools(li, row, id); // 「표를 L1 으로」 — 첫 레벨 줄 위의 1칸 제목 표를 이 템플릿의 L1 로(outline_lift.js, spec_hwpx_웹편집 ② §8-7)
    if (!cyc) {
      const pic = typeof olmPic === "function" ? olmPic(id) : null; // 개요 레벨 그림 — 서식 복사의 내용 서식 견본과 같은 그림(레벨마다 레터 · 견본 글 · 들여쓰기)
      if (pic) li.append(pic);
      if (typeof olmOddBox === "function") li.append(olmOddBox(id)); // 「다른 서식 보기」 의 펼침 자리 — 그림 바로 아래(접혀 있으면 숨김: outline_odd.js, spec_hwpx_웹편집 ② §8-2)
      const first = ins[0], node = first ? rel.node.get(first.root) || {} : {}, para = first ? node.para || first.root : null;
      if (para && hasBlock(para)) li.append(hBtn(`원문 보기 · ${short(`${(node.letter || "").trim()} ${first.text || node.text || ""}`.trim() || "(빈 글)", 34)}`, () => headsGo(para), { cls: "template-source", title: "이 템플릿의 첫 자리로(문서)" }));
    }
    let sub = null;
    const key = [...path, id].join(">");
    const open = (on) => {
      if (on && !sub) {
        sub = cyc ? el("p", "hnote trel-cyc", "되돌이 ") : levels(t, id, [...path, id]);
        if (cyc) sub.append(hHelp("되돌이 도움말", "상위에 이미 펼친 같은 템플릿입니다. 레벨과 가지는 상위 템플릿에서 확인하세요."));
        li.append(sub);
      }
      if (sub) sub.hidden = !on;
      tog.textContent = on ? "▾" : "▸";
      tog.setAttribute("aria-expanded", on);
      if (on) openSet.add(key); else openSet.delete(key);
    };
    tog.onclick = num.onclick = () => open(!sub || sub.hidden);
    li._open = open;
    if (openSet.has(key)) open(true); // 다시 그려도 펼친 채
    return li;
  };
  // 뿌리: 문서 최상위에 매달린 템플릿(주 사슬 먼저) · 표 칸 템플릿 · 그 밖(어느 트리에서도 닿지 않는 것)
  const attached = (t) => rel.at.get(idOf(t)) || new Map();
  const reach = new Set();
  const walk = (id) => { if (reach.has(id)) return; reach.add(id); for (const [k, kids] of rel.under) if (k.split("|")[0] === String(id)) for (const c of kids.keys()) walk(c); };
  const roots = tpls.filter((t) => t.kind === "main" || attached(t).has("root"));
  roots.forEach((t) => walk(idOf(t)));
  // 종속 템플릿 — 본문 템플릿의 레벨 아래에 매달려 그 템플릿을 펼쳐야만 보이던 템플릿(가지 템플릿 · 「T1T3」 · 「T1L3a」)을 본문 템플릿 다음에 하나씩 따로(2026-11-17 사용자 「개별적으로」 — spec_헤딩_추출 ② 「템플릿 관계」).
  // 부모 레벨의 가지 목록에도 전처럼 보인다. 줄을 다 종속 템플릿으로 넣은 템플릿(「줄을 다 넣음」)은 뺀다 — 그 줄은 종속 템플릿 쪽에 있다
  const isRoot = new Set(roots.map(idOf));
  const subs = tpls.filter((t) => reach.has(idOf(t)) && !isRoot.has(idOf(t)) && !(typeof olmTpl === "function" && (olmTpl(idOf(t)) || {}).all));
  const cells = tpls.filter((t) => !reach.has(idOf(t)) && (t.kind === "cell" || t.scope === "cell" || attached(t).has("cell")));
  cells.forEach((t) => walk(idOf(t)));
  const rest = tpls.filter((t) => !reach.has(idOf(t)));
  const section = (title, list, opt = {}) => {
    if (!list.length) return;
    const h = el("h3", null, title);
    if (opt.help) h.append(hHelp(`${opt.name} 도움말`, opt.help));
    root.append(h);
    const ul = el("ul", "trel");
    list.forEach((t) => ul.append(make(idOf(t), [], null, !!opt.hang)));
    root.append(ul);
  };
  section(`본문 템플릿 ${roots.length}`, roots);
  section(`종속 템플릿 ${subs.length}`, subs, { name: "종속 템플릿", hang: true, help: TPL_SUB_HELP });
  section(`표 칸 템플릿 ${cells.length}`, cells);
  section(`기타 템플릿 ${rest.length}`, rest);
  if (typeof captSection === "function") root.append(captSection()); // 캡션 템플릿 「CN」(그림 아래 · 표 위 캡션 — caption_tpl.js, spec_hwpx_웹편집 ② §8-10): 개요 템플릿과 따로 선 절
  if (!tpls.length) root.append(el("p", "hnote pad", "템플릿이 없습니다."));
  if (focus == null && where === "col" && typeof divLabelsPending === "function") focus = divLabelsPending(g); // 방금 지정을 바꾼 괄호 글이 든 템플릿을 다시 펼친다
  if (focus != null) tplFocus(root, rel, focus);
  if (typeof root._tplCount === "function") root._tplCount(tpls.length); // 머리의 「템플릿 N개」(탭의 요약 줄 · 열의 머리 글)
  return tpls.length;
}

const tplOvKey = () => (heads.outline ? `${JSON.stringify(heads.outline.run || "")}|${Object.entries(heads.outline.templates || {}).map(([k, t]) => `${k}:${t.max ?? ""}`).join(",")}` : ""); // 레벨 수(max)도 — 레벨을 더하면(② §8-6) 트리를 다시 그린다
function tplTreeRefresh(focus = null, force = false) { // 오버레이를 (다시) 읽은 뒤 — 다른 오버레이로 그려 둔 트리(자리 줄·서식 갈래·레벨 그림·종속 템플릿이 다름)는 통째로 다시 그린다. 펼친 템플릿은 그대로(tplTreeDraw 의 기억)
  for (const root of document.querySelectorAll(".tpl-tree")) {
    if ((!force && root.dataset.ov === tplOvKey()) || typeof root._tplRedraw !== "function") continue;
    const box = root.closest(".hd-body, #panel .pane, #paneHeads") || root, top = box.scrollTop;
    root._tplRedraw(focus);
    if (focus == null) box.scrollTop = top;
  }
}

function tplFocus(body, rel, id) { // 템플릿 id 까지 펼쳐 보이기 — 절에 따로 선 줄(본문 · 종속 · 표 칸 · 기타 템플릿)이 있으면 그 줄을, 없으면 매달린 자리를 따라 뿌리까지 올라간 길(첫 자리만)을 위에서부터 연다
  let li = [...body.querySelectorAll(":scope > .trel > li.trel-node")].find((x) => x.dataset.tpl === String(id)) || null;
  if (li) li._open(true);
  else {
    const path = [id], seen = new Set([id]);
    for (let k = 0; k < 20; k += 1) {
      const at = rel.at.get(path[0]);
      const up = at ? [...at.keys()].find((w) => w.includes("|")) : null;
      if (!up) break;
      const raw = up.split("|")[0], pid = /^\d+$/.test(raw) ? +raw : raw; // 종속 템플릿(「1+3」)은 글 키
      if (seen.has(pid)) break;
      seen.add(pid);
      path.unshift(pid);
    }
    let scope = body;
    for (const tid of path) {
      li = [...scope.querySelectorAll("li.trel-node")].find((x) => x.dataset.tpl === String(tid)) || null;
      if (!li) break;
      li._open(true);
      scope = li;
    }
  }
  if (li && li.dataset.tpl === String(id)) {
    li.classList.add("sel");
    li.scrollIntoView({ block: "center" });
    setTimeout(() => li.classList.remove("sel"), 3000);
  }
}

function headsAdjust(g) {
  const all = g.adjustments || [];
  if (!all.length) return el("p", "hnote", "조정할 서식 차이가 없습니다(슬롯마다 서식 라벨이 하나).");
  const groups = new Map();
  for (const a of all) {
    const k = `${a.decision}|${(a.review || {}).verdict || ""}|${a.from}|${a.to}`; // 재검토 결과가 다른 것은 다른 묶음
    const v = groups.get(k) || { ...a, n: 0 };
    v.n += 1;
    groups.set(k, v);
  }
  const list = [...groups.values()].sort((a, b) => b.n - a.n);
  const by = (d) => all.filter((x) => x.decision === d).length;
  const rv = (x) => x.review || {};
  const reviewed = all.filter((x) => rv(x).verdict === "agree" || rv(x).verdict === "disagree").length;
  const disagreed = all.filter((x) => rv(x).verdict === "disagree").length;
  const failed = all.filter((x) => rv(x).verdict === "failed").length;
  const judge = (x) => { // 판단 칸 — 재검토가 다르게 봤으면 「미판정(재검토 불일치)」, 동의면 ✓
    const v = rv(x).verdict;
    if (v === "disagree") return `미판정 · 재검토 불일치(1차 ${H_DECISION[x.first] || x.first || "?"})`;
    return (H_DECISION[x.decision] || x.decision) + (v === "agree" ? " ✓" : v === "failed" ? " (재검토 못 함)" : "");
  };
  const why = (x) => (rv(x).verdict === "disagree" ? `1차: ${x.reason || "—"} / 재검토: ${rv(x).reason || "—"}` : x.reason || "");
  const asked = !((g.llm || {}).requested && !(g.llm || {}).fallback && (g.llm || {}).pairs === false); // 서식 쌍 판정(C·D)은 기본 실행에서 뺐다(spec_헤딩_추출 ② §6) — 안 한 실행의 「미판정」 은 실패가 아니다
  return miniTable((asked ? `조정 ${all.length}건 — 조정 ${by("adjust")} · 다름 유지 ${by("keep")} · 미판정 ${by("undecided")}` : `대표와 서식 라벨이 다른 문단 ${all.length}건 — 서식 쌍 판정은 하지 않음(서식은 조정 층의 서식 정리 계획이 정함)`)
    + (reviewed ? ` · 재검토 ${reviewed}(불일치 ${disagreed}${failed ? ` · 못 함 ${failed}` : ""})` : "") + " 보기", ["판단", "문단", "서식 → 대표", "까닭"],
    list.slice(0, 40).map((x) => ({ cls: x.decision === "undecided" ? "warn" : null, cells: [judge(x), x.n, `${x.from} → ${x.to}`, why(x)],
      title: `${x.fromName || x.from}\n→ ${x.toName || x.to}\n템플릿 ${x.tplNo ? `T${x.tplNo} ` : ""}${x.template} L${x.level}`
        + (rv(x).verdict ? `\n재검토: ${rv(x).verdict === "agree" ? "동의" : rv(x).verdict === "disagree" ? "불일치 — 미판정으로 둠(사람이 정함)" : "못 함(1차 판정 그대로)"}` : "") })),
    (list.length > 40 ? `묶음 ${list.length}개 중 40개 · ` : "") + "서식 라벨 쌍별 묶음 — 줄에 마우스를 올리면 서식 이름 · ✓ = 재검토(새 호출)가 1차 판정에 동의", [3]);
}

// ---------------------------------------------------------------- 개요(템플릿) 편집(spec_hwpx_웹편집 ② §8)
// 서버 오버레이(GET /outline: 문단 → 템플릿 번호 N(표기 「TN」)·레벨·레터)로 개요 줄을 알고, Enter(하위 줄)·Alt+Enter(같은 레벨 뼈대)·Alt+↑/↓(레벨, 범위 선택이면 모두)·
// 끌기(같은 템플릿·레벨 줄끼리, 손잡이 .ol-grip)·빈 레터 줄 Backspace(지움)를 POST /outline 한 번(_edit 트랜잭션)으로. 2단계 결과가 없으면 Enter 는 종전 나누기.
function outlineLine(p) { return heads.outline && p ? heads.outline.lines[p.dataset.id] || null : null; }
function outlineLoad(refresh = false) { // 문서를 열 때·2단계가 새로 돌았을 때 — 2단계 결과가 없으면 서버가 {off: true}(200) → 개요 편집 꺼짐
  if (!state.id || state.format !== "hwpx") { heads.outline = null; if (typeof olmToolSync === "function") olmToolSync(); return; } // hwpx → docx 로 바꿔 열면 「템플릿 관계」 단추(도구 줄 · 이름 줄)가 켜진 채 남았다
  const id = state.id, epoch = state.epoch;
  api(`/api/docs/${id}/outline`).then((o) => {
    if (epoch !== state.epoch) return;
    heads.outline = o && !o.off && o.lines ? o : null;
    outlineHint();
    tplMarksDraw();
    tplFmtGraph(); // 서식 라벨 표시가 켜져 있고 그래프를 아직 안 읽었으면(헤딩 탭을 안 연 작업) 읽은 뒤 한 번 더 그린다
    tplTreeRefresh(); // 다른 오버레이로 그려 둔 템플릿 트리(탭·열)는 통째로 다시 — 아래 두 줄은 그대로인 트리의 줄만 새 값으로
    if (typeof olfRefresh === "function") olfRefresh(); // 열려 있는 「템플릿 관계」 의 자리 줄도 새 값으로(outline_format.js)
    if (typeof olmRefresh === "function") olmRefresh(); // 서식 갈래·도구 줄 「템플릿 관계」 단추도(outline_match.js)
    if (typeof captRefresh === "function") captRefresh(true); // 캡션 템플릿 「CN」 — 여백의 「C1」 · 열려 있는 「캡션 템플릿」 절(caption_tpl.js)
  }).catch(() => { if (epoch === state.epoch && (refresh || !heads.outline)) { heads.outline = null; outlineHint(); tplMarksDraw(); if (typeof olmRefresh === "function") olmRefresh(); } });
}
function outlineHint() { // 개요 편집 키가 켜졌는지(heads.outline)를 도구 줄 「단축키」 단추와 열려 있는 2열 단축키 설명에 — 키 목록·설명 글의 원본은 shortcuts.js(옛 도구 줄 키 안내 #editHint 는 없앰)
  if (typeof shortcutsSync === "function") shortcutsSync();
}
function outlineEmpty(p) { // 글 없는 레터 줄(라벨 제외) — Backspace 로 지울 수 있는 줄
  const ol = outlineLine(p);
  if (!ol || isRooted(ol.role) || ol.role === "table") return false; // 표 제목 줄(spec_hwpx_웹편집 ② §8-7)은 레터가 없다 — 빈 제목의 Backspace 는 종전 글 지우기
  const t = readText(p), i = t.indexOf(ol.letter);
  return i >= 0 && !t.slice(0, i).trim() && !t.slice(i + ol.letter.length).trim();
}
// 문서가 바뀌었다 — 여백의 서식 라벨(대표와 서식이 다른 줄에만 · 달라진 줄은 「≠」)을 서버의 지금 비교로 다시 읽는다(GET …/outline/fmts — spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」).
// 서식을 바꾸는 길이 여럿이라(서식 도구 · 붙여넣기 · 되돌리기 · 넣기 …) 편집마다가 아니라 문서 차례가 바뀔 때 한 번에(1.5초 모아서 · 「서식 라벨 표시」 가 켜져 있을 때만). 옛 서버면 그대로 둔다.
let fmtsTimer = null;
function fmtsRefreshSoon(now = false) {
  if (!state.id || !heads.outline || typeof tplFmtOn !== "function" || !tplFmtOn()) return;
  clearTimeout(fmtsTimer);
  const id = state.id, epoch = state.epoch;
  fmtsTimer = setTimeout(async () => {
    try {
      const r = await api(`/api/docs/${id}/outline/fmts`);
      if (epoch !== state.epoch || !heads.outline) return;
      heads.outline.fmts = r.fmts || {};
      tplMarksDraw();
    } catch { /* 옛 서버(끝점 없음) · 일시 오류 — 가진 라벨 그대로 */ }
  }, now ? 0 : 1500);
}

function outlineApply(o) { // 응답의 바뀐·새 줄·지운 줄을 오버레이에
  if (!heads.outline || !o) return;
  for (const [pid, line] of Object.entries(o.lines || {})) heads.outline.lines[pid] = line;
  for (const pid of o.removed || []) delete heads.outline.lines[pid];
  if (o.fmts) heads.outline.fmts = { ...(heads.outline.fmts || {}), ...o.fmts }; // 맞춘 줄의 서식 라벨(대표의 라벨이 됐다) — 여백의 번호가 그 자리에서 바뀐다(olMark)
  tplMarksDraw();
}
async function outlineKey(op, p) {
  if (!heads.outline) { toast("헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하면 개요 편집 키가 켜집니다"); return; }
  if (!outlineLine(p)) { toast(op === "sibling" ? "개요 줄이 아닙니다 — 템플릿이 매겨진 문단에서 Alt+Enter" : "개요 줄이 아닙니다"); return; }
  const s = getSelection();
  if (s.rangeCount && !p.contains(s.getRangeAt(0).startContainer) || s.rangeCount && !p.contains(s.getRangeAt(0).endContainer)) { toast("여러 문단에 걸친 선택에서는 Enter·Alt+Enter 를 쓸 수 없습니다"); return; }
  const o = selOffsets(p) || { start: readText(p).length, end: readText(p).length };
  const body = { op, id: p.dataset.id, offset: o.start };
  if (op === "enter" && o.end > o.start) body.end = o.end; // 고른 글은 서버가 같은 트랜잭션에서 지운다
  await structOp("outline", body);
}
function outlineSelected(p) { // 선택이 걸친 문단들(같은 그릇) — 다음 문단 맨 앞(offset 0)에서 끝난 선택은 그 문단 제외
  const s = getSelection();
  if (!s.rangeCount || s.isCollapsed) return [p];
  const r = s.getRangeAt(0);
  const paras = [...$("doc").querySelectorAll(".para[data-id]")].filter((q) => r.intersectsNode(q));
  if (paras.length > 1) {
    const last = paras[paras.length - 1];
    if (r.endContainer === last || last.contains(r.endContainer)) { const o = selOffsets(last) || offsetIn(last, r.endContainer, r.endOffset); if ((o.end != null ? o.end : o) === 0) paras.pop(); }
  }
  return paras.length ? paras : [p];
}
async function outlineLevel(p, delta) {
  if (!heads.outline) { toast("헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하면 개요 편집 키가 켜집니다"); return; }
  const paras = outlineSelected(p);
  const lines = paras.filter((q) => outlineLine(q));
  if (!lines.length) { toast("개요 줄이 아닙니다 — 템플릿이 매겨진 문단(「TN Lk」)에서 Alt+↑/↓"); return; }
  if (new Set(lines.map((q) => q.parentElement)).size > 1) { toast("같은 구역·칸 안의 줄들만 함께 바꿀 수 있습니다"); return; }
  // 템플릿의 마지막 레벨에서 내리기 — 더 깊은 레벨이 없다: 새 개요 레벨의 후보(레터 · 앞 공백 · 둘째 줄)를 열어 템플릿에 레벨을 더한다(outline_grow.js — spec_hwpx_웹편집 ② §8-6, 2026-11-16 사용자)
  if (delta > 0 && typeof outlineGrowAt === "function" && outlineGrowAt(lines)) { outlineGrowOpen(p, lines); return; }
  const s = getSelection();
  const keep = s.rangeCount && !s.isCollapsed ? { a: s.anchorNode, ao: s.anchorOffset, f: s.focusNode, fo: s.focusOffset,
    ap: s.anchorNode && (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement).closest(".para"), fp: s.focusNode && (s.focusNode.nodeType === 1 ? s.focusNode : s.focusNode.parentElement).closest(".para") } : null;
  const sel = keep && keep.ap && keep.fp ? { a: keep.ap.dataset.id, ao: offsetIn(keep.ap, keep.a, keep.ao), f: keep.fp.dataset.id, fo: offsetIn(keep.fp, keep.f, keep.fo) } : null;
  const r = await structOp("outline", { op: "level", ids: lines.map((q) => q.dataset.id), delta });
  if (r && sel && lines.length > 1) outlineReselect(sel, (r.outline && r.outline.focuses) || []);
}
function outlineReselect(sel, focuses) { // 블록 Alt+↑/↓ 뒤 — 양 끝 문단·offset(접두 길이 변화만큼 밀어)·방향 복원
  const shift = (id) => { const f = focuses.find((x) => x.id === id); return f ? f.shift || 0 : 0; };
  const a = paraEl(sel.a), f = paraEl(sel.f);
  if (!a || !f) return;
  const rng = document.createRange();
  const [an, ao] = pointAt(a, Math.max(0, sel.ao + shift(sel.a))), [fn, fo] = pointAt(f, Math.max(0, sel.fo + shift(sel.f)));
  const s = getSelection();
  s.removeAllRanges();
  rng.setStart(an, ao); rng.collapse(true);
  s.addRange(rng);
  s.extend(fn, fo);
}
// 끌기 — 손잡이(.ol-grip, 쪽 왼쪽 여백)를 잡아 같은 (템플릿, 레벨) 줄에 놓는다. 출발은 문단 id 로 좇고(DOM 이 다시 그려져 못 찾으면 취소), 놓을 자리는 위/아래 반.
function outlineGrip(p, ol, top) {
  const g = el("span", "ol-grip", "⋮⋮");
  g.draggable = true;
  g.dataset.para = p.dataset.id;
  g.title = `템플릿 T${ol.no} 레벨 ${ol.level} 「${ol.letter}」 — 끌어서 같은 템플릿·같은 레벨 줄 앞/뒤로 옮김(부분 트리째)`;
  g.style.top = `${Math.round(top)}px`;
  g.addEventListener("dragstart", (e) => {
    if (PEEK && typeof gatherGripStart === "function" && gatherGripStart(e, p.dataset.id)) return; // 취합의 둘째 면(기관 문서) — 끌어 넣기 출발: 전용 형식만 싣는다(같은 문서 안 옮기기는 안 건다 — gather.js, spec_취합 ② §4-6)
    heads.drag = { id: p.dataset.id, tpl: ol.tpl, level: ol.level };
    e.dataTransfer.setData("text/plain", p.dataset.id);
    e.dataTransfer.effectAllowed = "move";
    document.body.classList.add("ol-dragging");
  });
  g.addEventListener("dragend", () => { heads.drag = null; document.body.classList.remove("ol-dragging"); outlineDropClear(); });
  return g;
}
function outlineDropClear() { for (const q of document.querySelectorAll(".para.ol-before, .para.ol-after")) q.classList.remove("ol-before", "ol-after"); }
function outlineDropTarget(e) {
  const d = heads.drag;
  if (!d) return null;
  const q = e.target.closest && e.target.closest(".para[data-id]");
  const ol = q && outlineLine(q);
  if (!ol || q.dataset.id === d.id || ol.tpl !== d.tpl || ol.level !== d.level) return null;
  const src = paraEl(d.id);
  if (!src || src.parentElement !== q.parentElement) return null; // 같은 그릇(구역·칸)만
  const r = q.getBoundingClientRect();
  return { q, where: e.clientY < r.top + r.height / 2 ? "before" : "after" };
}
function bindOutlineDrag() {
  const doc = $("doc");
  doc.addEventListener("dragover", (e) => {
    const t = outlineDropTarget(e);
    outlineDropClear();
    if (!t) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    t.q.classList.add(t.where === "before" ? "ol-before" : "ol-after");
  });
  doc.addEventListener("dragleave", (e) => { if (!doc.contains(e.relatedTarget)) outlineDropClear(); });
  doc.addEventListener("drop", (e) => {
    const t = outlineDropTarget(e);
    const d = heads.drag;
    outlineDropClear();
    if (!t || !d) return;
    e.preventDefault();
    e.stopPropagation();
    heads.drag = null;
    document.body.classList.remove("ol-dragging");
    structOp("outline", { op: "move", id: d.id, target: t.q.dataset.id, where: t.where });
  }, true);
}

// 헤딩 열(2열 #headsDlg) — 문단 목록 · 서식 라벨 · 규칙 · 지침. 문서(1열)와 패널(3열) 사이에 나란히 보이고 ✕ 로 닫는다.
function headsDlg(kind, title, note = "") {
  const col = $("headsDlg");
  panelHelpClose();
  col.dataset.kind = kind;
  heads.dlg = kind;
  heads.seq += 1;
  if (kind !== "guides") heads.gEl = null;
  $("headsDlgTitle").textContent = title;
  $("headsDlgNote").textContent = note;
  $("headsDlgHelp").replaceChildren();
  for (const id of ["headsDlgTools", "headsDlgBody", "headsDlgFoot"]) $(id).textContent = "";
  if (!heads.keepFold) colFold("heads", false); // 열을 여는 동작은 접힌 열도 편다(열 접기 — setPanel 아래) · 배경에서 새로 그릴 때(keepFold)만 접힌 채 두고 띠 이름만 맞춘다
  else if (colFolded("heads")) colRailName("heads");
  if (col.hidden) {
    col.hidden = false;
    colsApply(); // 열이 생긴 만큼 패널·열 폭을 문서 보기 몫 안으로
    col.focus({ preventScroll: true }); // 단추로 열었을 때 초점을 열로(대화창 때와 같이) — 이미 열려 있으면 안 옮김
  }
  return { tools: $("headsDlgTools"), body: $("headsDlgBody"), foot: $("headsDlgFoot") };
}

function headsColClose(force = false) { // ✕ · 문서를 열고 닫을 때(force) — 저장 안 한 지침 글은 묻는다
  const col = $("headsDlg");
  if (col.hidden) return true;
  if (!force && (!headsGuideLeave() || (typeof tblAgentLeave === "function" && !tblAgentLeave()))) return false; // 표 지침 글도 묻는다(tables.js, spec_헤딩_추출 ② §10)
  if (!force && typeof headsFormLeave === "function" && !headsFormLeave()) return false; // 양식 정보 글도(heading_forms.js, ② §12)
  col.hidden = true;
  col.classList.remove("folded"); // 닫은 열은 다음에 펴진 채로 열린다
  heads.dlg = null;
  if (typeof xlColumnClosed === "function") xlColumnClosed(); // 2열 엑셀식 보기(spec ② §10)
  heads.gEl = null;
  heads.seq += 1;
  colsApply(); // 패널이 고른 폭으로 돌아감
  return true;
}

function hTable(head) {
  const t = el("table", "mini");
  const thead = el("thead"), tr = el("tr"), tb = el("tbody");
  for (const h of head) tr.append(el("th", null, h));
  thead.append(tr);
  t.append(thead, tb);
  return [t, tb];
}

function hRowKeys(tb) { // 2열 표의 줄 이동 — 줄(tr.go)에 초점이 있을 때 ↑/↓ = 앞·뒤 줄을 누른 것과 같다(고름 · 문서의 그 자리). 줄 안의 체크 상자·입력에서는 그대로. 맨 끝에서는 멈춘다
  tb.addEventListener("keydown", (e) => {
    if ((e.key !== "ArrowDown" && e.key !== "ArrowUp") || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || !e.target.matches || !e.target.matches("tr.go")) return;
    e.preventDefault();
    const rows = [...tb.querySelectorAll(":scope > tr.go")], next = rows[rows.indexOf(e.target) + (e.key === "ArrowDown" ? 1 : -1)];
    if (!next) return;
    next.scrollIntoView({ block: "nearest" }); // 머리 줄(sticky)에 가리지 않게 — .hd-body tr.go scroll-margin
    next.click();
  });
}

function hCell(tr, text, cls = null, title = "") {
  const td = el("td", cls, text == null || text === "" ? "—" : String(text));
  if (title) td.title = title;
  tr.append(td);
  return td;
}

function hFoot(msg, err = true) {
  const foot = $("headsDlgFoot");
  foot.textContent = "";
  foot.append(el("span", err ? "hd-msg" : "muted", msg));
}

function headsParas(filter = null) {
  const f = heads.paras;
  if (filter) Object.assign(f, { kind: "", area: "", rule: "", fmt: "", q: "", offset: 0 }, filter);
  const { tools } = headsDlg("paras", "문단 목록", "1단계 레코드 · 누르면 문서에서 그 문단으로");
  const c = (heads.view && heads.view.stage1 && heads.view.stage1.counts) || {};
  const sel = (label, key, opts) => {
    const l = el("label", "hd-field"), s = el("select");
    s.append(new Option("모두", ""));
    for (const [v, t] of opts) s.append(new Option(t, v));
    if (f[key] && ![...s.options].some((o) => o.value === f[key])) s.append(new Option(f[key], f[key]));
    s.value = f[key];
    s.onchange = () => { f[key] = s.value; f.offset = 0; headsParasLoad(); };
    l.append(el("span", null, label), s);
    return l;
  };
  const inp = (label, key, ph, size, up = false) => {
    const l = el("label", "hd-field"), i = el("input");
    i.type = "search";
    i.placeholder = ph;
    i.size = size;
    i.value = f[key];
    let tm;
    i.oninput = () => {
      clearTimeout(tm);
      tm = setTimeout(() => {
        const v = up ? i.value.trim().toUpperCase() : i.value.trim();
        if (v !== f[key]) { f[key] = v; f.offset = 0; headsParasLoad(); }
      }, 350);
    };
    l.append(el("span", null, label), i);
    return l;
  };
  tools.append(sel("종류", "kind", Object.entries(c.kinds || {}).map(([k, v]) => [k, `${H_KIND[k] || k} ${nf(v)}`])),
    sel("자리", "area", Object.entries(c.areas || {}).map(([k, v]) => [k, `${H_AREA[k] || k} ${nf(v)}`])),
    sel("규칙", "rule", (c.rules || []).map(([k, v]) => [k, `${k} ${nf(v)}`])),
    inp("서식 라벨", "fmt", "S12", 6, true), inp("글", "q", "찾을 글", 16));
  headsParasLoad();
}

async function headsParasLoad() {
  const f = heads.paras, id = state.id, epoch = state.epoch, seq = ++heads.seq;
  const qs = new URLSearchParams({ offset: f.offset, limit: 100 });
  for (const k of ["kind", "area", "rule", "fmt", "q"]) if (f[k]) qs.set(k, f[k]);
  hFoot("읽는 중…", false);
  let r;
  try { r = await api(`/api/docs/${id}/headings/paras?${qs}`); }
  catch (e) { if (seq === heads.seq && epoch === state.epoch) hFoot(`문단 목록을 읽지 못했습니다: ${e.message}`); return; }
  if (seq !== heads.seq || epoch !== state.epoch || heads.dlg !== "paras") return;
  const body = $("headsDlgBody"), foot = $("headsDlgFoot"), off = r.offset || 0;
  body.textContent = "";
  const [t, tb] = hTable(["#", "자리", "종류", "레터·꼴", "서식", "글"]);
  for (const p of r.items) {
    const tr = el("tr", hasBlock(p.id) ? "go" : "nogo");
    const ch = (p.char && p.char.text) || {}, pa = p.para || {}, ls = pa.lineSpacing;
    hCell(tr, p.n);
    hCell(tr, H_AREA[p.area] || p.area);
    hCell(tr, H_KIND[p.kind] || p.kind, null, p.rule ? `규칙 ${p.rule}${p.family ? ` · ${p.family}` : ""}` : "");
    hCell(tr, p.form || p.letter, "code");
    hCell(tr, p.fmt, null, p.fp ? `정밀 서식 ${p.fp}` : "");
    hCell(tr, short(p.text, 60), "txt");
    tr.title = `${p.id} · 규칙 ${p.rule || "—"} · 레터 앞 빈칸 ${p.leadSpaces ?? 0}칸${p.leadMm != null ? ` ${p.leadMm}mm` : ""}${p.blank ? " · 제목 없음(쓸 자리)" : ""}\n`
      + `${ch.font || "?"} ${ch.sizePt ?? "?"}pt${ch.bold ? " 굵게" : ""} · ${ALIGN[String(pa.align || "").toLowerCase()] || pa.align || "—"} · 왼 ${pa.indentLeftMm ?? "–"}mm`
      + ` · 첫 줄 ${pa.firstLineMm ?? "–"}mm · 위 ${pa.spaceBeforePt ?? "–"} 아래 ${pa.spaceAfterPt ?? "–"}pt`
      + ` · 줄 간격 ${ls ? `${ls.value ?? "?"}${ls.type === "PERCENT" ? "%" : "pt"}` : "—"}${hasBlock(p.id) ? "" : "\n웹 블록 없음 — 문서에서 찾아갈 수 없음"}`;
    if (hasBlock(p.id)) {
      tr.tabIndex = 0;
      const go = () => { // 찾아간 줄을 표시해 두면 문서와 나란히 볼 때 어느 줄인지 보인다
        const was = tb.querySelector("tr.sel");
        if (was) was.classList.remove("sel");
        tr.classList.add("sel");
        headsGo(p.id);
      };
      tr.onclick = go;
      tr.onkeydown = (e) => { if (e.key === "Enter") go(); };
    }
    tb.append(tr);
  }
  body.append(r.items.length ? t : el("p", "hnote pad", "맞는 문단이 없습니다."));
  body.scrollTop = 0;
  foot.textContent = "";
  const to = off + r.items.length;
  foot.append(hBtn("‹ 앞", () => { f.offset = Math.max(0, f.offset - 100); headsParasLoad(); }, { disabled: off <= 0 }),
    el("span", null, `${nf(r.total ? off + 1 : 0)}–${nf(to)} / ${nf(r.total)}`),
    hBtn("뒤 ›", () => { f.offset += 100; headsParasLoad(); }, { disabled: to >= r.total }),
    el("span", "spacer"), el("span", "muted", "흐린 줄 = 웹 블록이 없는 문단(개체만 품은 문단 등) · 줄에 마우스를 올리면 서식 자세히"));
}

async function headsLabels() {
  headsDlg("labels", "서식 라벨", "오차 기준으로 묶은 정밀 서식(F) · 누르면 그 라벨의 문단 목록");
  const id = state.id, epoch = state.epoch, seq = heads.seq;
  hFoot("읽는 중…", false);
  let r;
  try { r = await api(`/api/docs/${id}/headings/labels`); }
  catch (e) { if (seq === heads.seq) hFoot(`서식 라벨을 읽지 못했습니다: ${e.message}`); return; }
  if (seq !== heads.seq || epoch !== state.epoch) return;
  const list = [...r.labels].sort((a, b) => b.count - a.count);
  const [t, tb] = hTable(["라벨", "문단", "이름", "종류", "변형 F"]);
  for (const l of list) {
    const tr = el("tr", "go");
    hCell(tr, l.id);
    hCell(tr, nf(l.count));
    hCell(tr, l.name, "txt");
    hCell(tr, Object.entries(l.kinds || {}).map(([k, v]) => `${H_KIND[k] || k} ${v}`).join(" · "), "wrap");
    hCell(tr, Object.keys(l.variants || {}).length, null, Object.entries(l.variants || {}).map(([k, v]) => `${k} ${v}`).join(" · "));
    tr.tabIndex = 0;
    tr.title = `대표 문단 ${l.sample || "—"} · 레터 앞 빈칸 꼴 ${l.leadCode || "—"} · 레터 뒤 ${l.gapCode || "—"}${l.spacer ? " · 간격 장치(빈 문단)" : ""} · 누르면 문단 목록`;
    tr.onclick = () => headsParas({ fmt: l.id });
    tr.onkeydown = (e) => { if (e.key === "Enter") headsParas({ fmt: l.id }); };
    tb.append(tr);
  }
  $("headsDlgBody").append(t);
  hFoot(`서식 라벨 ${nf(list.length)}개 · 정밀 서식 F ${nf(r.formats)}개`, false);
}

async function headsRules(msg = "") {
  if (heads.dlg !== "rules") headsDlg("rules", "규칙식", "판정 순서: 빈 문단 → 목차·캡션 → 앞선 배운 규칙 → 글 전체 규칙 → 첫머리 규칙(내장 → 배운) → 보통 글");
  const seq = heads.seq;
  let r;
  try { r = await api("/api/headings/rules"); }
  catch (e) { if (seq === heads.seq) hFoot(`규칙을 읽지 못했습니다: ${e.message}`); return; }
  if (seq === heads.seq) headsRulesDraw(r, msg);
}

function headsRuleToggle(x) {
  const td = el("td"), cb = el("input");
  cb.type = "checkbox";
  cb.checked = x.enabled !== false;
  cb.setAttribute("aria-label", `규칙 ${x.name} 켜기`);
  cb.onchange = () => headsRuleCall(`/api/headings/rules/${encodeURIComponent(x.id)}`, { method: "PATCH", headers: H_JSON,
    body: JSON.stringify({ enabled: cb.checked, version: heads.rules.version }) });
  td.append(cb);
  return td;
}

async function headsRuleCall(url, opts) {
  const seq = heads.seq;
  try {
    const r = await api(url, opts);
    if (seq === heads.seq) headsRulesDraw(r, "바뀐 규칙은 「다시 추출」 때 반영됩니다.");
  } catch (e) {
    if (seq !== heads.seq) return;
    const msg = e.status === 409 ? "다른 곳에서 규칙이 먼저 바뀌어 새로 읽었습니다 — 다시 해 보세요." : `바꾸지 못했습니다: ${e.message}`;
    toast(msg, true);
    headsRules(msg);
  }
}

function headsRulesDraw(r, msg = "") {
  heads.rules = r;
  const body = $("headsDlgBody"), top = body.scrollTop;
  body.textContent = "";
  body.append(el("h3", null, `배운 규칙 ${r.learned.length}개 — 후보는 검증한 문서에만, 서로 다른 문서 2개에서 통과하면 전역`));
  if (!r.learned.length) body.append(el("p", "hnote pad", "아직 없습니다 — 1단계 카드의 「LLM 규칙 보강」이 검증을 통과한 규칙을 여기에 저장합니다."));
  else {
    const [t, tb] = hTable(["켬", "상태", "이름", "종류", "정규식", "문서", "출처", ""]);
    for (const x of r.learned) {
      const tr = el("tr", x.enabled === false ? "off" : null);
      tr.append(headsRuleToggle(x));
      hCell(tr, H_STATUS[x.status] || x.status, x.status === "global" ? "good" : null);
      const nm = hCell(tr, x.name, "wrap", x.note || "");
      if (x.first) nm.append(" ", el("span", "hb", "앞선"));
      hCell(tr, `${H_KIND[x.kind] || x.kind}${x.scope === "whole" ? " · 글 전체" : ""}`);
      hCell(tr, x.pattern, "code", (x.examples || []).map((s) => short(s, 80)).join("\n"));
      hCell(tr, nf((x.docs || []).length), null, "이 규칙이 검증을 통과한 문서 수");
      const pv = x.provenance || {};
      hCell(tr, `${x.source === "user" ? "사용자" : "LLM"}${pv.doc ? ` · ${pv.doc}` : ""}${pv.model ? ` · ${pv.model}` : ""}`, "wrap", x.created ? `만듦 ${fmtWhen(x.created)}` : "");
      const act = el("td", "acts");
      const url = `/api/headings/rules/${encodeURIComponent(x.id)}`;
      act.append(hBtn(x.status === "global" ? "후보로" : "전역으로", () => headsRuleCall(url, { method: "PATCH", headers: H_JSON,
        body: JSON.stringify({ status: x.status === "global" ? "candidate" : "global", version: heads.rules.version }) }),
        { title: x.status === "global" ? "검증한 문서에만 걸리게" : "모든 문서에 걸리게" }),
      hBtn("지우기", () => {
        if (confirm(`배운 규칙 「${x.name}」(${x.pattern})을(를) 지울까요?\n지운 기록은 이력에 남습니다.`)) headsRuleCall(`${url}?version=${heads.rules.version}`, { method: "DELETE" });
      }, { cls: "btn sm danger" }));
      tr.append(act);
      tb.append(tr);
    }
    body.append(t);
  }
  body.append(el("h3", null, `내장 규칙 ${r.builtin.length}개 — 켜고 끄기만(코드 개선은 계속 반영)`));
  const [t2, tb2] = hTable(["켬", "이름", "종류", "계열", "정규식", "범위"]);
  for (const x of r.builtin) {
    const tr = el("tr", x.enabled === false ? "off" : null);
    tr.append(headsRuleToggle(x));
    hCell(tr, x.name, "wrap");
    hCell(tr, H_KIND[x.kind] || x.kind);
    hCell(tr, x.family);
    hCell(tr, x.pattern, "code");
    hCell(tr, x.scope === "whole" ? "글 전체" : "첫머리");
    tb2.append(tr);
  }
  body.append(t2);
  body.scrollTop = top;
  const foot = $("headsDlgFoot");
  foot.textContent = "";
  if (msg) foot.append(el("span", "hd-msg note", msg));
  foot.append(el("span", "spacer"), el("span", "muted", `저장소 ${r.store === "off" ? "끔(메모리만)" : r.store} · ${r.version}판`
    + ((r.keeps || []).length ? ` · 그대로 둔 충돌 ${r.keeps.length}` : "")));
}

function headsGuideDirty() {
  const E = heads.gEl, g = heads.guide;
  return !!(heads.dlg === "guides" && E && g && E.ta.value !== g.text);
}
const headsGuideLeave = () => !headsGuideDirty() || confirm("저장하지 않은 지침 글이 있습니다. 버릴까요?");

async function headsGuides() {
  const { tools, body, foot } = headsDlg("guides", "지침", "LLM 에 주는 판단 기준 — 고치면 사용자 사본으로 저장(기본본은 그대로)");
  const seq = heads.seq;
  const sel = el("select"), lab = el("label", "hd-field"), info = el("span", "muted");
  sel.setAttribute("aria-label", "지침 고르기");
  lab.append(el("span", null, "지침"), sel);
  tools.append(lab, info);
  const notice = el("div", "hwarn hd-notice"), msg = el("div", "hd-msg"), ta = el("textarea"), def = el("textarea");
  const defCap = el("div", "hnote", "아래 = 지금 기본본(읽기만) — 위 사본과 견주어 보세요");
  notice.hidden = def.hidden = defCap.hidden = true;
  ta.spellcheck = def.spellcheck = false;
  def.readOnly = true;
  ta.setAttribute("aria-label", "지침 글");
  def.setAttribute("aria-label", "기본본 글(읽기만)");
  const wrap = el("div", "hd-guide");
  wrap.append(notice, msg, ta, defCap, def);
  body.append(wrap);
  const save = hBtn("저장", () => headsGuideSave(), { cls: "btn sm primary", disabled: true });
  const reset = hBtn("기본본으로", () => headsGuideReset(), { disabled: true, title: "사용자 사본을 지우고 기본본으로(사본은 이력에 남음)" });
  const llmNote = el("span", "muted");
  foot.append(save, reset, el("span", "spacer"), llmNote);
  heads.gEl = { sel, info, notice, msg, ta, def, defCap, save, reset };
  ta.oninput = () => { save.disabled = !headsGuideDirty(); };
  sel.onchange = () => {
    if (!headsGuideLeave()) { sel.value = heads.guideName; return; }
    heads.guideName = sel.value;
    headsGuideLoad();
  };
  api("/api/headings/llm").then((st) => {
    if (seq === heads.seq || heads.dlg === "guides") {
      llmNote.textContent = `LLM 연결: ${st.active === "cli" ? "CLI" : st.active === "api" ? "API" : "없음"}${st.model ? ` · ${st.model}` : ""}`
        + (st.backend && st.backend !== "auto" ? ` · 설정 ${st.backend}` : "");
      llmNote.title = st.cli ? `CLI: ${st.cli}` : "";
    }
  }).catch(() => { llmNote.textContent = "LLM 연결 상태 모름"; });
  try {
    const list = await api("/api/headings/guides");
    if (heads.gEl === null || heads.gEl.sel !== sel) return;
    for (const g of list) sel.append(new Option(`${g.title}${g.custom ? " · 고침" : ""}${g.defaultChanged ? " · 기본본 바뀜" : ""}`, g.name));
  } catch (e) { msg.textContent = `지침 목록을 읽지 못했습니다: ${e.message}`; return; }
  sel.value = heads.guideName;
  headsGuideLoad();
}

async function headsGuideLoad(keepText = false) {
  const E = heads.gEl, name = heads.guideName;
  if (!E) return;
  E.msg.textContent = "";
  let g;
  try { g = await api(`/api/headings/guides/${encodeURIComponent(name)}`); }
  catch (e) { if (heads.gEl === E) E.msg.textContent = `지침을 읽지 못했습니다: ${e.message}`; return; }
  if (heads.gEl === E && name === heads.guideName) headsGuideShow(g, keepText);
}

function headsGuideShow(g, keepText = false) {
  const E = heads.gEl;
  if (!E) return;
  heads.guide = g;
  if (!keepText) E.ta.value = g.text;
  E.def.value = g.default || "";
  E.def.hidden = E.defCap.hidden = true;
  E.info.textContent = g.custom ? `사용자 사본 ${g.version}판${g.updated ? ` · ${fmtWhen(g.updated)} 고침` : ""}` : "기본본 그대로";
  E.reset.disabled = !g.custom;
  const opt = [...E.sel.options].find((o) => o.value === g.name);
  if (opt) opt.textContent = `${g.title}${g.custom ? " · 고침" : ""}${g.defaultChanged ? " · 기본본 바뀜" : ""}`;
  E.notice.textContent = "";
  E.notice.hidden = !g.defaultChanged;
  if (g.defaultChanged) {
    E.notice.append(el("span", null, "기본본이 바뀌었습니다 — 이 사본을 고친 뒤 기본본(코드에 든 지침)이 새로 나왔습니다. 견주어 보고 필요하면 옮겨 적으세요. "));
    const show = hBtn("기본본 보기", () => {
      E.def.hidden = E.defCap.hidden = !E.def.hidden;
      show.textContent = E.def.hidden ? "기본본 보기" : "기본본 숨기기";
    });
    E.notice.append(show, " ", hBtn("확인", () => headsGuideRebase(), { title: "바뀐 기본본을 봤다고 표시합니다(사본 글은 그대로)" }));
  }
  E.save.disabled = !headsGuideDirty();
}

async function headsGuideSave() {
  const E = heads.gEl, g = heads.guide;
  if (!E || !g) return;
  E.msg.textContent = "";
  E.save.disabled = true;
  try {
    const r = await api(`/api/headings/guides/${encodeURIComponent(g.name)}`, { method: "PUT", headers: H_JSON,
      body: JSON.stringify({ text: E.ta.value, version: g.version, reason: "화면" }) });
    if (heads.gEl !== E) return;
    headsGuideShow(r);
    toast(`지침 「${r.title}」을(를) 저장했습니다(${r.version}판) — 다음 LLM 실행부터 씁니다`);
  } catch (e) {
    if (heads.gEl !== E) return;
    if (e.status === 409) {
      E.msg.textContent = "다른 곳에서 이 지침을 먼저 고쳤습니다 — 새 판을 읽었습니다(내 글은 그대로). 그 위에 저장하려면 「저장」을 한 번 더 누르세요.";
      await headsGuideLoad(true);
    } else E.msg.textContent = `저장하지 못했습니다: ${e.message}`;
    E.save.disabled = !headsGuideDirty();
  }
}

async function headsGuideReset() {
  const E = heads.gEl, g = heads.guide;
  if (!E || !g || !confirm(`지침 「${g.title}」의 사용자 사본을 지우고 기본본으로 되돌릴까요?\n지운 사본은 이력 폴더에 남습니다.`)) return;
  try {
    const r = await api(`/api/headings/guides/${encodeURIComponent(g.name)}`, { method: "DELETE" });
    if (heads.gEl === E) { headsGuideShow(r); toast(`지침 「${r.title}」을(를) 기본본으로 되돌렸습니다`); }
  } catch (e) { if (heads.gEl === E) E.msg.textContent = `되돌리지 못했습니다: ${e.message}`; }
}

async function headsGuideRebase() {
  const E = heads.gEl, g = heads.guide;
  if (!E || !g) return;
  try {
    const r = await api(`/api/headings/guides/${encodeURIComponent(g.name)}`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ rebase: true }) });
    if (heads.gEl === E) headsGuideShow(r, headsGuideDirty());
  } catch (e) { if (heads.gEl === E) E.msg.textContent = `확인 표시를 못 했습니다: ${e.message}`; }
}

// ---- 3단계 표 구조(spec_헤딩_추출 ② §8) — 카드 3 + 2열 「표 보기」(표 목록 → 칸 역할 격자, 칸을 누르면 문서의 그 문단으로)
function headsCard3(r, busy) {
  const box = $("heads3"), s1 = r.stage1, s3 = r.stage3;
  box.textContent = "";
  headsCardHeader(box, r, 3, "표 구조", "표의 칸을 열헤더·행헤더·귀퉁이·필드·제목·안내로 구분하고, 헤더 구조가 다시 시작하는 곳에서 서브 테이블로 나눕니다. LLM 분석은 칸의 값을 보고 판정하는 유료 작업입니다. 스크립트 분석은 음영·굵게·값 꼴을 기준으로 초안을 만듭니다.");
  if (!s3) {
    headsCardNotice(box, s1 ? "분석 전" : "1단계 추출 필요", s1 ? "아래에서 분석 방법을 선택하세요." : "1단계에서 문단을 추출하면 표 구조를 만들 수 있습니다.");
  } else {
    if (typeof driftCardRow === "function") box.append(driftCardRow(r, 3)); // 문서가 바뀌어도 다시 분석하라고 하지 않는다(② §17 뼈대 유지) — 새 표·모양이 바뀐 표가 생겼을 때만 알림
    if (s3.ownerStale) headsCardNotice(box, "소속 재확인 필요", "2단계 결과가 바뀌어 표의 소속 헤딩·구분 라벨이 이전 결과를 가리킵니다. 표 구조를 다시 분석하면 맞춰집니다.", true);
    const c = s3.counts || {}, ro = c.roles || {}, lm = s3.llm || {};
    const stats = el("div", "hstats");
    const stat = (v, k, title = "") => {
      const s = el("span");
      s.append(el("span", "stage-stat-label", k), el("b", null, nf(v)));
      if (title) s.title = title;
      stats.append(s);
    };
    stat(c.tables, "표", `칸 ${nf(c.cells)}${c.nested ? ` · 표 안 표 ${nf(c.nested)}` : ""} — 1칸 표(글상자)는 표로 세지 않음`);
    stat(c.subtables, "서브 테이블", `둘 이상으로 나뉜 표 ${nf(c.split)}`);
    stat(ro.colhead || 0, "열헤더", "아래 칸들의 이름");
    stat(ro.rowhead || 0, "행헤더", "오른쪽 칸들의 이름(키-값 양식의 키 포함)");
    stat(ro.corner || 0, "귀퉁이", "헤더 행과 헤더 열이 겹치는 칸");
    stat(ro.field || 0, "필드", "채우는 값 칸");
    if (ro.title || ro.note || ro.spacer) stat((ro.title || 0) + (ro.note || 0) + (ro.spacer || 0), "제목·안내·간격");
    stat(c.repeats, "되풀이", "같은 헤더 구조가 둘 이상의 표(서브 테이블)에 되풀이");
    if (lm.calls) {
      stat(c.changed, "LLM 변경", "T 호출이 초안과 다르게 정한 칸");
      stat(lm.rejected, "거절", "검증에서 버린 LLM 답(영역·칸)");
      stat(lm.undecided, "미판정", "LLM 이 판정하지 못한 표 — 초안 그대로");
    }
    if (c.issues) stat(c.issues, "문제", "헤더 없는 필드 · 거느린 칸 없는 헤더");
    if (c.basisTables != null) { // 표 의미(spec ② §9 — 결과 version 2)
      const b = c.basis || {}, k = c.calc || {}, ow = c.owners || {};
      stat(c.basisTables, "구분 헤더 표", `단계 ${nf(b.stage)} · 차년도 ${nf(b.year)} · 기관 ${nf(b.org)} · 연도 ${nf(b.period)} 표 — 열헤더·행헤더·칸 안 라벨`);
      stat(k.tables, "계산식 표", `수식 ${nf(k.formulas)} — 일치 ${nf(k.ok)} · 미검증 ${nf((k.blank || 0) + (k.incomplete || 0))}(빈 칸)`);
      if (k.mismatch) { const w = el("span", "warn"); w.append(el("b", null, nf(k.mismatch)), " 불일치"); w.title = "엑셀 수식으로 다시 계산한 값과 문서 값이 다른 칸"; stats.append(w); }
      if (k.missing) stat(k.missing, "미기입", "피연산자는 있는데 합계 칸이 비어 있음");
      stat((ow.stage2 || 0) + (ow.stage1 || 0), "소속", `헤딩에 매달린 표 — 2단계 그래프 ${nf(ow.stage2 || 0)} · 1단계 어림 ${nf(ow.stage1 || 0)} · 없음 ${nf(ow.none || 0)}`);
    }
    box.append(stats);
    if (lm.error) headsCardNotice(box, lm.fallback ? "LLM 실패 · 초안 유지" : "LLM 실패", lm.error, true);
    else if (lm.requested && !lm.calls) headsCardNotice(box, "스크립트 초안", "모든 표가 1~3칸이어서 LLM에 보낼 표가 없습니다. 스크립트 초안을 그대로 사용합니다.");
  }
  const acts = el("div", "hacts");
  acts.classList.add("stage-actions");
  acts.append(hBtn("LLM 분석", () => headsLlmTables(), { disabled: busy || !s1, cls: "btn sm primary", title: "표 묶음마다 서브 테이블·헤더 행/열·칸 역할을 LLM 이 칸의 값을 보고 판정(유료, 수 분)" }),
    hBtn("스크립트 분석", () => headsStart(3, false), { disabled: busy || !s1, title: "LLM 없이 음영·굵게·값 꼴로 초안만(1초 안팎)" }));
  const tools = el("div", "hacts stage-tools");
  tools.append(hBtn("표 구조 보기", () => headsTables(), { disabled: !s3, title: "표 목록과 칸 역할 격자를 문서 옆 2열에" }),
    hBtn("표 관리", () => showTab("Tables"), { title: "표 목록·엑셀식 보기·지침·문서 표시 도구" }));
  box.append(acts, tools);
}

async function headsLlmTables() {
  const st = await headsLlmReady();
  if (!st) return; // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 유료 · 연구개발계획서 양식 기준 10여 번 · 수 분: design.md §18 「확인 창」)
  headsStart(3, true);
}

function headsMore3(r) { // 되풀이(같은 헤더 구조) 목록 — 결과(실행)가 바뀔 때만 다시 그린다
  const s3 = r.stage3, key = s3 && s3.meta ? `${s3.meta.run}|${s3.meta.at}` : null;
  if (key === heads.tablesKey) return;
  heads.tablesKey = key;
  const box = $("heads3More");
  box.textContent = "";
  if (!s3) return;
  const reps = s3.repeats || [];
  if (!reps.length) return;
  const d = el("details", "more hblock");
  d.append(el("summary", null, `되풀이 ${reps.length}묶음 보기 — 같은 헤더 구조의 표(서브 테이블)`));
  const ul = el("ul", "hlist");
  for (const rp of reps) {
    const li = el("li");
    li.append(el("div", "hl-top", `×${rp.count}`));
    const sub = el("div", "hl-sub");
    for (const w of rp.where || []) {
      const b = hBtn(`${w.table}/${w.sub}`, () => headsTables(w.table), { cls: "btn sm", title: "표 보기로" });
      sub.append(b, " ");
    }
    li.append(sub);
    ul.append(li);
  }
  d.append(ul);
  box.append(d);
}

async function headsTables(tableId = null) {
  const s3 = heads.view && heads.view.stage3;
  if (!s3) return;
  const { tools, body } = headsDlg("tables", "표 구조", "표마다 칸 역할(열헤더·행헤더·귀퉁이·필드)과 서브 테이블 · 칸을 누르면 문서에서 그 문단으로");
  const seq = heads.seq, id = state.id, epoch = state.epoch;
  let data = heads.tbl.data;
  if (!data || heads.tbl.key !== `${s3.meta.run}|${s3.meta.at}`) { // 결과(실행)가 바뀌었으면 다시 읽는다
    hFoot("읽는 중…", false);
    try { data = await api(`/api/docs/${id}/headings/tables`); }
    catch (e) { if (seq === heads.seq) hFoot(`표 구조를 읽지 못했습니다: ${e.message}`); return; }
    if (seq !== heads.seq || epoch !== state.epoch) return;
    heads.tbl = { key: `${s3.meta.run}|${s3.meta.at}`, data, id: null };
  }
  heads.tbl.id = tableId;
  const sel = el("select"), lab = el("label", "hd-field");
  sel.setAttribute("aria-label", "표 고르기");
  sel.append(new Option("표 목록", ""));
  for (const t of data.tables || []) sel.append(new Option(`${t.id} · ${t.rows}×${t.cols}${t.subtables.length > 1 ? ` · 서브 ${t.subtables.length}` : ""}${t.before ? ` · ${short(t.before, 18)}` : ""}`, t.id));
  sel.value = tableId || "";
  sel.onchange = () => headsTablesDraw(data, sel.value || null);
  lab.append(el("span", null, "표"), sel);
  const legend = el("span", "hlegend");
  for (const [k, v] of Object.entries(H_TROLE)) legend.append(el("span", k, v));
  const tblSrc = headsSourceChip(heads.view, 3, false); // 이 표 구조가 LLM 것인지 스크립트 것인지 · 끝난 때 · 걸린 시간(② §7 「LLM 표시」)
  tools.append(lab, ...(tblSrc ? [tblSrc] : []), legend);
  if (typeof tblRolesBtn === "function") tools.append(tblRolesBtn(true)); // 범례 옆 「문서에 표시」 — 문서의 표 칸에 같은 역할 색(tables.js, spec ② §10)
  headsTablesDraw(data, tableId);
}

function headsTablesDraw(data, tableId) {
  const body = $("headsDlgBody");
  body.textContent = "";
  heads.tbl.id = tableId;
  const sel = $("headsDlgTools").querySelector("select");
  if (sel && sel.value !== (tableId || "")) sel.value = tableId || "";
  const tables = data.tables || [];
  if (!tableId) {
    const [t, tb] = hTable(["#", "표", "크기", "앞 문단", "소속", "구분", "계산식", "서브", "열헤더 · 행헤더 · 필드", "LLM"]);
    tables.forEach((x, i) => {
      const tr = el("tr", "go"), c = x.counts || {};
      hCell(tr, i + 1);
      hCell(tr, `${x.id}${x.depth > 1 ? " (표 안 표)" : ""}`);
      hCell(tr, `${x.rows}×${x.cols} · ${nf(x.cells.length)}칸`);
      hCell(tr, short(x.before || "", 30), "txt");
      hCell(tr, x.owner ? short(ownerLabel(x.owner), 34) : "—", "txt", x.owner && x.owner.path && x.owner.path.length ? x.owner.path.join(" › ") : "");
      hCell(tr, basisNames(x.basis) || "—");
      const k = x.calc || {};
      hCell(tr, k.is ? `수식 ${nf(k.formulas)}${k.mismatch ? ` · 불일치 ${nf(k.mismatch)}` : ""}${k.missing ? ` · 미기입 ${nf(k.missing)}` : ""}` : "—", k.mismatch || k.missing ? "warn" : null);
      hCell(tr, x.subtables.map((s) => `${s.id} ${H_TKIND[s.kind] || s.kind}`).join(" · "), "wrap");
      hCell(tr, `${nf(c.colhead || 0)} · ${nf(c.rowhead || 0)} · ${nf(c.field || 0)}`);
      const lm = x.llm || {};
      hCell(tr, lm.undecided ? "미판정" : lm.sent ? `변경 ${lm.changed || 0}` : "—", lm.undecided ? "warn" : null);
      tr.tabIndex = 0;
      tr.title = `${x.id} · 칸 ${x.cells.length} · 서브 테이블 ${x.subtables.length}${x.issues.length ? ` · 문제 ${x.issues.length}` : ""} · 누르면 격자`;
      tr.onclick = () => headsTablesDraw(data, x.id);
      tr.onkeydown = (e) => { if (e.key === "Enter") headsTablesDraw(data, x.id); };
      tb.append(tr);
    });
    body.append(tables.length ? t : el("p", "hnote pad", "표가 없습니다(1칸 표·글상자는 표로 세지 않음)."));
    hFoot(`표 ${nf(tables.length)}개 · 칸 ${nf((data.counts || {}).cells)} · 서브 테이블 ${nf((data.counts || {}).subtables)}`, false);
    return;
  }
  const t = tables.find((x) => x.id === tableId);
  if (!t) { body.append(el("p", "hnote pad", "그 표가 없습니다.")); return; }
  body.append(headsTableGrid(t));
  body.scrollTop = 0;
  const foot = $("headsDlgFoot");
  foot.textContent = "";
  foot.append(hBtn("‹ 표 목록", () => headsTablesDraw(data, null)), el("span", "spacer"),
    el("span", "muted", "굵은 선 = 서브 테이블 경계 · 파란 테두리 = LLM 이 초안을 바꾼 칸 · 칸에 마우스를 올리면 헤더 경로"));
}

function headsTableGrid(t) {
  const wrap = el("div", "hgrid-wrap");
  const byId = new Map((t.cells || []).map((c) => [c.id, c]));
  const nameOf = (cid) => { const c = byId.get(cid); return c ? (oneLine(c.text) || "(빈 칸)") : cid; };
  const info = el("div", "hgrid-info");
  info.append(el("b", null, t.id), ` ${t.rows}×${t.cols} · 칸 ${nf(t.cells.length)}${t.depth > 1 ? " · 표 안 표" : ""}${t.before ? ` · 앞 문단 「${short(t.before, 36)}」` : ""}`);
  if (t.host && hasBlock(t.host)) info.append(" ", hBtn("표 자리로", () => headsGo(t.host), { title: "문서에서 이 표를 품은 문단으로" }));
  const xl = el("a", "btn sm", "엑셀로 받기");
  xl.href = `/api/docs/${encodeURIComponent(state.id)}/headings/tables/${encodeURIComponent(t.id)}/xlsx`;
  xl.setAttribute("download", "");
  xl.title = "시트 「표」(격자 — 합계·비율 칸은 엑셀 수식) · 「검증」 · 「필드」(긴 꼴) · 「정보」 .xlsx";
  info.append(" ", xl, " ", hBtn("표 지침", () => { if (typeof tblAgentView === "function") tblAgentView(t.id); }, { title: "작성요령 · 사용자 지침(표 에이전트 입력)" }),
    " ", hBtn("엑셀식 보기", () => { if (typeof xlColumn === "function") xlColumn(t.id); }, { title: "이 열에 A1 격자(수식 계산 · 문서에 반영)" }));
  wrap.append(info);
  const o = t.owner; // 표 의미(spec ② §9) — 소속·구분 라벨·구분·단위
  const own = el("div", "hgrid-owner");
  if (o && !o.root) {
    own.append(el("span", "muted", "소속"), o.para && hasBlock(o.para) ? hBtn(ownerLabel(o), () => headsGo(o.para), { title: (o.path || []).concat([o.text]).join(" › ") || "문서의 그 헤딩으로" })
      : el("b", null, ownerLabel(o)));
    if (o.path && o.path.length) own.append(el("span", "muted", `(${o.path.join(" › ")})`));
    if (o.division) own.append(dvTag(el("span", "hb div", `구분 라벨 ${o.division.text}`), dvOfDivision(o.division)));
  } else own.append(el("span", "muted", o && o.root ? "소속: 문서 뿌리(위에 헤딩 없음)" : "소속: 모름(2단계 그래프 없음)"));
  if ((t.basis || []).length) own.append(el("span", "hb", `구분 ${basisNames(t.basis)}`));
  if (t.unit) own.append(el("span", "hb", `단위 ${t.unit}`));
  if ((t.labels || []).length) { const lb = el("span", "hb", `칸 안 라벨 ${t.labels.length}`); lb.title = t.labels.map((l) => l.text).join("\n"); own.append(lb); }
  wrap.append(own);
  const fById = new Map((t.formulas || []).map((f) => [f.id, f]));
  const subs = t.subtables || [];
  const ul = el("ul", "hsubs");
  for (const s of subs) {
    const li = el("li");
    li.append(el("b", null, s.id), ` ${H_TKIND[s.kind] || s.kind} · 행 ${s.rows[0] + 1}–${s.rows[1]} · 열 ${s.cols[0] + 1}–${s.cols[1]}`
      + (s.kind === "matrix" || s.kind === "form" || s.kind === "plain" ? ` · 헤더 행 ${s.headerRows} 열 ${s.headerCols}` : "") + (s.source === "llm" ? " · LLM" : ""));
    if (s.note) li.title = s.note;
    ul.append(li);
  }
  wrap.append(ul);
  if ((t.llm || {}).summary) wrap.append(el("p", "hsum", t.llm.summary));
  const occ = new Map();
  for (const c of t.cells || []) {
    for (let r = c.row; r < c.row + c.rs; r += 1) for (let k = c.col; k < c.col + c.cs; k += 1) if (!occ.has(`${r},${k}`)) occ.set(`${r},${k}`, c);
  }
  const subTop = new Set(subs.filter((s) => s.rows[0] > 0).map((s) => `${s.rows[0]}|${s.cols[0]}|${s.cols[1]}`));
  const subLeft = new Set(subs.filter((s) => s.cols[0] > 0).map((s) => `${s.cols[0]}|${s.rows[0]}|${s.rows[1]}`));
  const onTop = (r, k) => [...subTop].some((x) => { const [rr, c0, c1] = x.split("|").map(Number); return rr === r && c0 <= k && k < c1; });
  const onLeft = (r, k) => [...subLeft].some((x) => { const [cc, r0, r1] = x.split("|").map(Number); return cc === k && r0 <= r && r < r1; });
  const table = el("table", "hgrid");
  table.setAttribute("aria-label", `${t.id} 칸 역할 격자`);
  for (let r = 0; r < t.rows; r += 1) {
    const tr = el("tr");
    for (let k = 0; k < t.cols; k += 1) {
      const c = occ.get(`${r},${k}`);
      if (!c) { tr.append(el("td", "none" + (onTop(r, k) ? " sb-top" : "") + (onLeft(r, k) ? " sb-left" : ""))); continue; }
      if (c.row !== r || c.col !== k) continue;
      const td = el("td", `${c.role}${c.changed ? " chg" : ""}${onTop(r, k) ? " sb-top" : ""}${onLeft(r, k) ? " sb-left" : ""}`);
      if (c.rs > 1) td.rowSpan = c.rs;
      if (c.cs > 1) td.colSpan = c.cs;
      const txt = oneLine(c.text);
      td.textContent = txt ? (txt.length > 24 ? txt.slice(0, 24) + "…" : txt) : (c.nested && c.nested.length ? `〔표 ${c.nested.join(", ")}〕` : "");
      const paths = [];
      if (c.role === "field") {
        paths.push(`행헤더: ${(c.rowPath || []).map(nameOf).join(" › ") || "—"}`, `열헤더: ${(c.colPath || []).map(nameOf).join(" › ") || "—"}`);
        if (c.div) paths.push(`구분 값: ${Object.entries(c.div).map(([b, v]) => `${H_BASIS[b] || b} ${v}`).join(" · ")}`);
      } else if (c.parent) paths.push(`부모: ${nameOf(c.parent)}`);
      if (c.basis && c.basis.length) { // 구분 헤더 표지(spec ② §9)
        td.dataset.basis = basisNames(c.basis) || c.basis.join("·");
        td.classList.add("hb-basis");
        paths.push(`구분 헤더: ${basisNames(c.basis) || c.basis.join("·")}(${{ name: "이름", value: "값", total: "합계", ratio: "비율" }[c.basisKind] || c.basisKind})${c.code ? ` · 코드 ${c.code}` : ""}${c.expr ? ` · 식 ${c.expr}` : ""}`);
      } else if (c.code || c.expr) paths.push(`${c.code ? `코드 ${c.code}` : ""}${c.expr ? ` 식 ${c.expr}` : ""}`.trim());
      const fs = (c.formulas || []).map((id) => fById.get(id)).filter(Boolean);
      if (fs.length) {
        const worst = fs.find((f) => f.status === "mismatch" || f.status === "nonnumeric") || fs.find((f) => f.status === "missing") || fs.find((f) => f.status === "ok") || fs[0];
        td.classList.add("fx", `fx-${worst.status}`);
        for (const f of fs) paths.push(`수식(${f.axis === "col" ? "열" : "행"}) ${f.ref}: ${f.formula} → 기대 ${f.expected ?? "—"} · 문서 ${f.actual ?? "—"} · ${H_FSTAT[f.status] || f.status}${f.diff ? ` · 차이 ${f.diff}` : ""}`);
      }
      td.title = [`${c.id} · ${H_TROLE[c.role] || c.role}${c.draft && c.draft !== c.role ? ` (초안 ${H_TROLE[c.draft] || c.draft})` : ""} · 서브 ${c.sub || "—"} · ${c.rs}×${c.cs}`
        + `${c.shaded ? " · 음영" : ""}${c.bold ? " · 굵게" : ""}`, txt, ...paths, c.reason || ""].filter(Boolean).join("\n");
      const go = (c.paras || []).find(hasBlock);
      if (go) {
        td.classList.add("go");
        td.tabIndex = 0;
        td.onclick = () => headsGo(go);
        td.onkeydown = (e) => { if (e.key === "Enter") headsGo(go); };
      }
      tr.append(td);
    }
    table.append(tr);
  }
  const scroll = el("div", "hgrid-scroll");
  scroll.append(table);
  wrap.append(scroll);
  if ((t.issues || []).length) {
    wrap.append(el("p", "hnote", `문제 ${t.issues.length}건 — ${t.issues.slice(0, 3).map((i) => `${nameOf(i.cell)}: ${i.why}`).join(" · ")}${t.issues.length > 3 ? " …" : ""}`));
  }
  const goRow = (tr, c) => { const go = (c.paras || []).find(hasBlock); if (!go) return; tr.classList.add("go"); tr.tabIndex = 0; tr.onclick = () => headsGo(go); tr.onkeydown = (e) => { if (e.key === "Enter") headsGo(go); }; };
  if ((t.formulas || []).length) { // 수식 검증(spec ② §9) — 주소·엑셀 수식·기대값·문서 값·상태, 누르면 그 칸 문단
    const k = t.calc || {}, d = el("details", "more hblock");
    d.open = !!(k.mismatch || k.missing || k.nonnumeric);
    d.append(el("summary", null, `수식 검증 ${nf(t.formulas.length)}개 — 일치 ${nf(k.ok)} · 불일치 ${nf(k.mismatch)} · 미기입 ${nf(k.missing)} · 미검증 ${nf((k.blank || 0) + (k.incomplete || 0))}${k.nonnumeric ? ` · 수 아님 ${nf(k.nonnumeric)}` : ""}`));
    const [ft, fb] = hTable(["주소", "축", "엑셀 수식", "기대값", "문서 값", "상태", "행헤더", "열헤더", "설명"]);
    for (const f of t.formulas) {
      const c = byId.get(f.cell) || {}, tr = el("tr");
      hCell(tr, f.ref); hCell(tr, f.axis === "col" ? "열" : "행"); hCell(tr, f.formula, "mono"); hCell(tr, f.expected ?? "—"); hCell(tr, f.actual ?? (oneLine(c.text) || "—"));
      hCell(tr, H_FSTAT[f.status] || f.status, f.status === "mismatch" || f.status === "nonnumeric" || f.status === "missing" ? "warn" : f.status === "ok" ? "ok" : null, f.diff != null ? `차이 ${f.diff}` : "");
      hCell(tr, (c.rowPath || []).map(nameOf).join(" › ") || "—", "txt"); hCell(tr, (c.colPath || []).map(nameOf).join(" › ") || "—", "txt"); hCell(tr, f.note || "", "txt");
      goRow(tr, c);
      fb.append(tr);
    }
    d.append(ft);
    wrap.append(d);
  }
  const fields = (t.cells || []).filter((c) => c.role === "field");
  if (fields.length) { // 필드 목록(긴 꼴) — 어느 필드가 어느 행헤더·열헤더에 종속되는가 + 구분 값
    const d = el("details", "more hblock");
    d.append(el("summary", null, `필드 목록 ${nf(fields.length)}개 — 행헤더 경로 · 열헤더 경로 · 단계·차년도·기관·연도 · 값`));
    const [ft, fb] = hTable(["주소", "서브", "행헤더 경로", "열헤더 경로", "단계", "차년도", "기관", "연도", "값", "수식"]);
    for (const c of fields) {
      const dv = c.div || {}, tr = el("tr");
      hCell(tr, `${colLetter(c.col)}${c.row + 1}`); hCell(tr, c.sub || ""); hCell(tr, (c.rowPath || []).map(nameOf).join(" › ") || "—", "txt"); hCell(tr, (c.colPath || []).map(nameOf).join(" › ") || "—", "txt");
      hCell(tr, dv.stage || ""); hCell(tr, dv.year || ""); hCell(tr, dv.org || ""); hCell(tr, dv.period || ""); hCell(tr, oneLine(c.text) || "", "txt"); hCell(tr, (c.formulas || []).join(", "));
      goRow(tr, c);
      fb.append(tr);
    }
    d.append(ft);
    wrap.append(d);
  }
  return wrap;
}

function headsBind() {
  $("headsDlgClose").onclick = () => headsColClose(); // 고친 지침 글이 있으면 묻는다
  $("headsFold").onclick = () => colFold("heads", true); // » 2열을 오른쪽 띠로 접기 · 띠 = 펴기(열 접기 — setPanel 아래)
  $("headsRail").onclick = () => colFold("heads", false);
  document.querySelectorAll("[data-head-view]").forEach((b) => {
    b.onclick = () => headsResultView(b.dataset.headView);
    b.onkeydown = (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d && !["Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const i = HEAD_VIEWS.indexOf(b.dataset.headView);
      const next = e.key === "Home" ? HEAD_VIEWS[0] : e.key === "End" ? HEAD_VIEWS.at(-1) : HEAD_VIEWS[(i + d + HEAD_VIEWS.length) % HEAD_VIEWS.length];
      headsResultView(next);
      $(`headsTab${next}`).focus();
    };
  });
  document.querySelectorAll("#headsStageTabs [data-stage]").forEach((b) => { // 추출·설정의 단계 탭(② §7 「단계 탭」)
    b.onclick = () => headsStagePick(Number(b.dataset.stage));
    b.onkeydown = (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d && !["Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const i = H_STAGES.indexOf(Number(b.dataset.stage));
      const next = e.key === "Home" ? H_STAGES[0] : e.key === "End" ? H_STAGES.at(-1) : H_STAGES[(i + d + H_STAGES.length) % H_STAGES.length];
      headsStagePick(next);
      $(`headsStageTab${next}`).focus();
    };
  });
}
headsBind();

// ---------------------------------------------------------------- 연결
function bind() {
  const input = $("fileInput");
  $("openBtn").onclick = () => input.click();
  $("pickBtn").onclick = () => (typeof homeFilesPick === "function" ? homeFilesPick() : input.click()); // 시작 화면 「파일 선택」 = 문서 목록에 더함(여러 개 — ② §15-1). 상단 「열기」 는 전처럼 바로 연다
  input.onchange = () => { openFile(input.files[0]); input.value = ""; };
  $("downloadBtn").onclick = download;
  $("verifyBtn").onclick = startEditVerify;
  $("panelBtn").onclick = () => setPanel($("panel").hidden);
  $("panelFold").onclick = () => colFold("panel", true); // » 3열을 오른쪽 띠로 접기 · 띠 = 펴기 — 이 둘로 정한 접힘만 기억
  $("panelRail").onclick = () => colFold("panel", false);
  $("peerFold").onclick = () => colFold("peer", true); // 같이 보기 열(spec_작업 ② §12) — » 접기 · 띠 = 펴기 · ✕ = 끄기(기억)
  $("peerRail").onclick = () => colFold("peer", false);
  $("peerClose").onclick = () => peerSet(false);
  bindPanelResize();
  $("zoomIn").onclick = () => keepCenter(() => setZoom(state.zoom + 0.1));
  $("zoomOut").onclick = () => keepCenter(() => setZoom(state.zoom - 0.1));
  $("zoomVal").onclick = () => keepCenter(() => setZoom(1));
  $("zoomFit").onclick = () => keepCenter(fitWidth);
  // 높이 맞춤 ↔ 여백 빼고 맞춤 — 누를 때마다 바뀌고, 지금 보는 쪽을 창 맨 위에 맞춘다
  $("zoomHeight").onclick = () => fitHeight(state.fit === "height" ? "body" : "height", true);
  viewPrefLoad(); // 2쪽 보기 · 휠 쪽 넘김 — 기억한 값으로 단추·#doc 클래스를 맞춘다(문서 전이라 배율은 안 건드림)
  $("twoUp").onclick = () => setTwoUp(!state.twoUp);
  $("wheelFlip").onchange = (e) => setWheelFlip(e.target.checked);
  setTwoUp(state.twoUp);
  setWheelFlip(state.wheelFlip);
  for (const b of document.querySelectorAll("#toolModes [data-tool]")) b.onclick = () => { // 도구 줄 묶음 고르기(한 줄)
    setToolSet(b.dataset.tool);
    // 「서식」 묶음은 사람이 누를 때만 서식 관리자(2열)도 연다 — 닫혀 있거나 다른 보기일 때(spec_서식복사 ② §3). 아래 setToolSet(state.tool) 처럼 기억한 묶음을 되살릴 때는 열지 않는다
    if (b.dataset.tool === "style" && typeof styleLibOpen === "function" && !["styleLib", "styleSave"].includes(heads.dlg)) styleLibOpen();
  };
  setToolSet(state.tool);
  bindWheelFlip();
  $("prevEdit").onclick = () => stepEdit(-1);
  $("nextEdit").onclick = () => stepEdit(1);
  $("showPages").onchange = (e) => { $("doc").classList.toggle("hide-pages", !e.target.checked); tplMarksDraw(); peerViewSync(); }; // 쪽 표시를 끄면 템플릿 표시·여백도 함께 · 둘째 면도 같이(spec_작업 ② §12)
  $("doc").addEventListener("click", (e) => { if (e.target.closest(".sheet-label")) e.stopPropagation(); });
  const tabs = TOOL_TABS.filter((n) => $(`tab${n}`) && $(`tab${n}`).closest("#workspaceNav")); // 탭 띠에 단추가 있는 도구만 — 에이전트·작업 개요(Div)·검증·PDF·기록은 패널 머리에서 연다(spec_작업 ② §10)
  for (const n of [...PANEL_TOOLS, ...PANEL_MAIN, "Agent", "Dash"]) $(`tab${n}`).onclick = () => showTab(n); // 패널 머리 탭 — 화살표 키는 아래 #toolTabs 의 키 처리가 맡는다
  $("toolTabTask").onclick = () => showTab("Div"); // 패널 머리 탭(toolTabsDraw) — 연구개발 TASK 의 작업 개요
  $("toolTabTool").onclick = () => showTab(toolShown(toolLast) ? toolLast : "Verify");
  $("taskListBtn").onclick = taskListToggle; // 상단 바 「작업 리스트」 아이콘(2026-11-16 — 패널 머리 탭에서 옮김)
  $("toolMore").onclick = () => toolMoreSet(!toolMoreOpen); // 오른쪽 묶음(검증 · PDF · 기록) 펼치기·접기
  $("toolTabs").onkeydown = (e) => {
    const buttons = [...$("toolTabs").querySelectorAll('button[role="tab"]')].filter((b) => !b.hidden && b.getClientRects().length), i = buttons.indexOf(e.target); // 접힌 묶음의 탭은 건너뛴다
    if (i < 0 || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next].click(); buttons[next].focus();
  };
  tabs.forEach((n) => {
    const t = $(`tab${n}`);
    t.onclick = () => showTab(n);
    t.onkeydown = (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d && !["Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const shown = tabs.filter((x) => !$(`tab${x}`).hidden); // 숨은 탭(헤딩 추출·표·에이전트 — 문서 형식·작업 종류에 따라)은 건너뛴다
      const nx = e.key === "Home" ? shown[0] : e.key === "End" ? shown[shown.length - 1] : shown[(shown.indexOf(n) + d + shown.length) % shown.length];
      showTab(nx);
      $(`tab${nx}`).focus();
    };
  });
  $("navFold").onclick = () => rowFold("nav", !rowFolded("nav")); // 상단 바 가운데 [탭 ▴][⇅][편집 ▴]
  $("barFold").onclick = () => rowFold("bar", !rowFolded("bar"));
  $("fileFold").onclick = () => rowFold("file", !rowFolded("file"));
  $("barSwap").onclick = barSwap;
  rowFold("nav", rowFoldLoad("nav"), false); // 기억한 접힘 상태로(문서 전이라 줄은 아직 숨김)
  rowFold("bar", rowFoldLoad("bar"), false);
  rowFold("file", rowFoldLoad("file"), false);
  $("worksBtn").onclick = async () => { await loadWorks(); $("worksDlg").showModal(); };
  $("recentAll").onclick = () => $("worksBtn").click();
  $("homeLink").onclick = (e) => { if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return; e.preventDefault(); goHome(); }; // 로고 = 시작 화면으로(② §7) — Ctrl·Shift 누름은 링크대로(새 탭·새 창)
  homeTasksDraw(); // 시작 화면의 TASK 카드(② §15)
  $("worksClose").onclick = () => $("worksDlg").close();
  $("worksNew").onclick = () => { $("worksDlg").close(); input.click(); };
  $("logRefresh").onclick = () => drawLog();
  for (const id of ["importBox", "editBox"]) $(id).addEventListener("toggle", (e) => { if (e.isTrusted) e.target.dataset.touched = "1"; });
  $("pdfPrev").onclick = () => { state.pdfPage -= 1; showPdf(); };
  $("pdfNext").onclick = () => { state.pdfPage += 1; showPdf(); };
  $("pdfPageInput").onchange = (e) => { state.pdfPage = parseInt(e.target.value, 10) || 1; showPdf(); };
  document.querySelectorAll("#pdfSeg button").forEach((b) => (b.onclick = () => {
    if (b.disabled) return;
    state.pdfWhich = b.dataset.which;
    document.querySelectorAll("#pdfSeg button").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", x === b); });
    if (state.selected) select(state.selected);
    showPdf();
  }));
  document.querySelectorAll("#compare [data-mode]").forEach((b) => (b.onclick = () => { state.compare.mode = b.dataset.mode; drawCompare(); }));
  document.querySelectorAll("#compare [data-size]").forEach((b) => (b.onclick = () => { state.compare.size = b.dataset.size; drawCompare(); }));
  $("cmpPrev").onclick = () => { state.compare.index -= 1; drawCompare(); };
  $("cmpNext").onclick = () => { state.compare.index += 1; drawCompare(); };
  $("cmpClose").onclick = () => $("compare").close();
  $("compare").addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" && state.compare.index > 0) { state.compare.index -= 1; drawCompare(); }
    if (e.key === "ArrowRight" && state.compare.index < state.compare.pages.length - 1) { state.compare.index += 1; drawCompare(); }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && state.id) { e.preventDefault(); (PEEK ? parent : window).download(); } // 옆 문서 화면에서 눌러도 바깥(지금 문서)을 저장
  });
  const drop = $("drop");
  const own = (e) => !!heads.drag || (typeof gatherDragIs === "function" && gatherDragIs(e)) || (typeof gatherPartDragIs === "function" && gatherPartDragIs(e)); // 앱 안에서 끄는 것(개요 줄 옮기기 · 취합의 끌어 넣기 · 기관 문서 줄을 기관 폴더로 — gather.js)은 파일 놓기가 아니다
  window.addEventListener("dragover", (e) => { e.preventDefault(); if (!own(e)) drop.classList.add("over"); });
  window.addEventListener("dragleave", (e) => { if (!e.relatedTarget) drop.classList.remove("over"); });
  window.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("over"); if (own(e)) return;
    if (!state.id && !PEEK && typeof homeFilesAdd === "function") { homeFilesAdd(e.dataTransfer.files); return; } // 시작 화면 — 문서 목록에 더함(② §15-1). 문서를 연 뒤에는 전처럼 그 파일을 연다
    const f = e.dataTransfer.files[0]; if (f) openFile(f);
  });
  window.addEventListener("beforeunload", (e) => { if (hasUnsaved()) { e.preventDefault(); e.returnValue = ""; } });
  // 창·패널 크기가 바뀌어 다시 맞춰도 보던 자리 그대로. 폭 맞춤은 폭(content — 여백 padding·세로 스크롤 막대 뺀 폭)이 그대로면 건너뛴다 — 줄 접기처럼 높이만
  // 바뀌면 배율이 같은데도 fitWidth 가 배율을 1 로 돌려 재느라 문서 전체를 두 번 다시 배치한다(74쪽 0.6초)
  // 맞춤 배율이 바뀌었으면 쪽 여백 표시(「TN Lk」·손잡이·표 표지·표 모서리 손잡이)를 다시 그린다 — zoom 1/z 로 화면 크기를 고정한 것들이라 옛 배율로 그려 둔 채면 새 배율만큼 커지거나 작아진다
  // (2026-11-10 — 엑셀식 보기 2열을 닫으면 표 표지가 2.7배로 남던 것: 닫을 때의 다시 그리기가 이 다시 맞춤보다 먼저 돌았다. 창 크기도 같다 — resize 이벤트가 먼저).
  let fitW = -1, fitH = -1;
  new ResizeObserver(([e]) => {
    const w = e.contentRect.width, h = e.contentRect.height, same = w === fitW;
    const dy = fitH > 0 && h > 0 ? Math.max(-h / 2, Math.min(h / 2, (fitH - h) / 2)) : 0; // 바뀌기 전의 가운데 — 열을 열면 도구 줄이 꺾여 높이도 바뀐다(keepCenter)
    fitW = w;
    fitH = h;
    if (state.fit === "width" && same) return;
    const z0 = state.zoom;
    keepCenter(() => refit(), dy);
    if (state.id && state.zoom !== z0) zoomMarksDraw(); // 큰 문서(배율을 뒤에서 바꾸는 중)면 다 바뀐 뒤에 한 번
  }).observe($("scroller"));
  // 배율을 뒤에서 바꾸는 동안(zoomStep) 스크롤로 보기에 들어온 옛 배율 쪽은 그리기 전에 바꾼다. 자리를 적는 것(zoomSeen)은 이 프레임의 scroll 처리가 다 끝난 뒤 —
  // 같은 scroll 을 보는 다른 처리(오른쪽 단추 메뉴 닫기)가 「사용자가 굴렸다」 를 옛 자리로 가린다
  $("scroller").addEventListener("scroll", () => {
    if (!zoomJob.on || zoomQuiet()) return;
    if (zoomCover()) zoomJob.dirty = true;
    requestAnimationFrame(zoomSeen);
  }, { passive: true });
  bindEditing();
  bindOutlineDrag();
  bindToolbar();
}

bind();
init();

// ---------------------------------------------------------------- 구분 기준(spec_구분_기준 ② §8) — 3열 탭 「구분 기준」(프로파일·저장한 과제 구성·값·적용 상태) + 2열 「바꿀 자리」(headsDlg kind "divisions")
const DV_STATUS = { applied: "맞춤", already: "이미 맞음", excluded: "제외", unsupported: "지원 안 됨", unresolved: "미해결" };
const DV_EXTRA = { outside: "연구개발기관 외 기관", overseas: "국외기관", entrust: "위탁연구개발기관" };
const divFresh = () => ({ view: null, values: null, plan: null, result: null, busy: false, dirty: false, filter: "all", skip: new Set(), showDrop: true, seq: 0,
  msg: null, auto: false, keepFocus: false, // 실행 묶음(② §22): 상태 줄에 남길 글 {kind: note|halt|done, text}(다음 계획·반영·입력 때까지) · 「한 번에 진행」 도는 중 · 끝나면 묶음의 다음 단추로 초점
  ui: { advanced: false, runMore: false }, // runMore = 실행 묶음의 「세부」 를 이 문서에서 프로그램이 폄(divRunReveal — 브라우저에 기억한 펴짐은 따로)
  comment: { draft: "", busy: false, msg: "", err: false, open: false }, // 양식별 코멘트 줄(② §18, 2026-11-11): 쓰던 글 · 보내는 중 · 상태 한 줄(실패 여부) · 목록 펼침 — divRender 가 다시 그려도 남는다
  preset: { source: "", from: "", loaded: null, more: false, naming: false, nameDraft: null, confirming: "" }, // 프로젝트 구성 불러오기·확정(spec_작업 ② §18 — 전의 저장한 프로젝트 구분 기준 ② §8): 목록에서 고른 곳(confirmed|doc:id|file|project:이름|preset:id) · 마지막으로 채운 곳(글) · 저장한 프로젝트 구성 {id, name, values(divCanon)} · ⋯ 펼침 · 이름 줄 · 삭제 확인
  projects: undefined, projectsAt: 0, projectsBusy: false, // 다른 프로젝트의 구성(GET /api/projects — 「프로젝트 구성 불러오기」 목록)
  savedKey: null, // 작업에 마지막으로 저장한 설정(divCanon) — 자동 저장(② §8)
  marks: { data: null, index: null, loading: false, seq: 0, err: null, llm: false, llmLast: null, missing: false, missingLast: null, // 문서 표시·추가한 자리(spec_구분_기준 ② §11) · 빠진 자리 검토(§13)
    reviewing: false, reviewOwn: false, review: null, // LLM 검토(두 검토를 함께 — ② §14): 도는 중 · 이 화면이 부른 것 · 마지막 취합 결과
    only: null } }); // 「그 구분만 또렷이」 — 색 설명(문서 위에 떠 있는 상자 #divKey)의 칩으로 고른 구분 키(divOnlySet · ② §11) · 문서를 열거나 닫으면 풀림
let dv = divFresh();

function divReset() { // 문서를 열거나 닫을 때(load·closeDoc)
  dv = divFresh();
  taskFlow = taskFlowFresh(); // 이관 단계에 읽어 둔 다른 문서 자료(spec_작업 ② §11)
  clearTimeout(divSaveTimer); divSaveTimer = null; divSavePending = null; // 옛 문서의 설정 저장은 끊는다(② §8 자동 저장 — 도는 것은 epoch 로 버려짐)
  toolTabsDraw(); // 패널 머리 탭 「작업 개요」 · 「<도구>」 — 작업 종류가 연구개발과제일 때만(spec_작업 ② §10)
  if (typeof projectComboClose === "function") projectComboClose(); // 프로젝트 고르기 목록(② §19)은 body 에 떠 있다 — 칸이 사라지면 함께 닫는다
  $("divBox").textContent = "";
  taskFrameForm = null; taskFrameApply = null; // 1·2단계 묶음 안의 입력 칸도 함께 사라졌다
  if (typeof zonesReset === "function") zonesReset(); // 편집 구역(zones.js) — 읽어 둔 구역을 버리고, 문서가 열려 있으면 새 문서·새 TASK 의 것으로 곧 다시 읽는다(문서를 열 때 · 닫을 때 · TASK 를 바꾼 뒤)
  divMarksDraw(); // 옛 문서의 구분 기준 표시 지움(② §11)
  // 표시가 켜져 있으면(nfm.divMarks — 기억) 문서를 연 뒤 곧 자리를 읽는다(② §11 「색 설명」, 2026-11-19): 전에는 「작업 개요」 를 열어야(divShow) 읽어서, 다시 연 문서는 이름 줄 아이콘이 눌려 있는데도
  // 색도 떠 있는 설명도 없었다(아이콘을 껐다 켜야 보임). 편집 구역(zones.js zonesReset)과 같은 꼴 — load() 가 끝난 뒤에.
  // 둘째 면(같이 보기)도 읽는다(2026-11-19 ② §12 「도구는 문서마다」 — 그 면의 이름 줄 아이콘으로 그 문서에 켠 것: 읽기만 · GET)
  if (state.id) {
    const view = dv, epoch = state.epoch;
    setTimeout(() => { if (view === dv && epoch === state.epoch && divMarksOn() && !dv.marks.data && !dv.marks.loading) divMembersLoad(); }, 0);
  }
}

const divDefault = () => ({ stages: [1], orgs: { lead: "", joint: [], nonprofit: [false] } });
const divTotalYears = (v) => (v.stages || []).reduce((s, n) => s + (Number(n) || 0), 0);

function divDemand(orgs) { // 수요기업으로 고른 기관(spec_구분_기준 ② §24 — 2026-11-21 사용자 "수요기업 으로 선택할 수 있게 해줘. 주관기관, 참여기관 처럼") → [주관(늘 false), 공동1, …] | null(고른 것이 없음 — 서버 norm_values 처럼 그 열쇠를 두지 않는다)
  const o = orgs || {}, d = Array.isArray(o.demand) ? o.demand : [];
  const out = Array.from({ length: (o.joint || []).length + 1 }, (_, i) => i > 0 && !!d[i]);
  return out.some(Boolean) ? out : null;
}
function divValues() { // 서버에 보낼 값(빈 선택 항목은 뺀다)
  const v = dv.values || divDefault();
  const orgs = { lead: v.orgs.lead || "", joint: [...(v.orgs.joint || [])], nonprofit: [...(v.orgs.nonprofit || [])] }, demand = divDemand(v.orgs);
  if (demand) orgs.demand = demand;
  for (const k of Object.keys(DV_EXTRA)) if ((v.orgs[k] || []).length) orgs[k] = [...v.orgs[k]];
  const out = { stages: v.stages.map((n) => Number(n) || 1), orgs };
  if (v.period && (v.period.start || v.period.end)) out.period = { start: v.period.start || "", end: v.period.end || "" };
  if ((v.subs || []).length) out.subs = [...v.subs];
  if (v.current && v.current > 1) out.current = Math.min(v.current, divTotalYears(v));
  return out;
}

async function divShow() {
  if (!state.id) return;
  const id = state.id, epoch = state.epoch, view = dv, seq = ++dv.seq;
  const inputKey = dv.values ? divCanon(divValues()) : null, savedKey = dv.savedKey;
  let r;
  try { r = await api(`/api/docs/${id}/divisions`); }
  catch (e) {
    if (epoch !== state.epoch || view !== dv) return;
    $("divBox").textContent = "";
    $("divBox").append(el("p", "hwarn fail", `프로젝트 구성 상태를 읽지 못했습니다: ${e.message}`), hBtn("다시 읽기", () => divShow()));
    return;
  }
  if (epoch !== state.epoch || view !== dv || seq !== dv.seq) return;
  if (inputKey !== (dv.values ? divCanon(divValues()) : null) || savedKey !== dv.savedKey) return;
  dv.view = r;
  divReviewSeen(r); // 작업에 남은 마지막 LLM 검토·도는 중 표시(② §14 — 다시 연 작업 · 다른 화면이 돌린 것)
  if (divMarksOn()) divMembersLoad(); // 문서 표시가 켜져 있으면 편집 차례가 바뀐 자료를 다시(② §11)
  if (!dv.values || dv.savedKey === divCanon(divValues())) {
    dv.values = r.settings ? structuredClone(r.settings.values) : (r.applied ? structuredClone(r.applied.values) : divDefault());
    dv.savedKey = r.settings ? divCanon(r.settings.values) : null; // 작업에 있는 설정과 같으면 자동 저장이 바로 안 돈다
  }
  divRender();
  taskFlowLoad(); // 이관이면 다른 문서의 구분 기준·분석 준비를 읽어 단계 목록을 채운다(spec_작업 ② §11)
}

function divRender() {
  const box = $("divBox"), r = dv.view;
  const panelKeep = typeof projectPanelKeep === "function" ? projectPanelKeep(box) : null; // 프로젝트 칸·버전 이름 줄에 쓰던 글·포커스·열린 고르기 목록 — 다 그린 뒤 새 칸으로 옮긴다(spec_작업 ② §19)
  box.textContent = "";
  taskFrameForm = null; // 1단계 묶음 안의 입력 칸 — 아래 taskFrameHost 가 다시 정한다
  if (!r) return;
  const v = dv.values, ok = r.profile.supported;
  v.orgs.joint ||= [];
  v.orgs.nonprofit ||= [];
  v.orgs.demand = Array.from({ length: v.orgs.joint.length + 1 }, (_, i) => i > 0 && !!(v.orgs.demand || [])[i]); // 수요기업으로 고른 기관 — 기관 수에 맞춘다(보낼 때는 고른 것이 있을 때만: divDemand)
  v.period ||= { start: "", end: "" };
  box.setAttribute("aria-busy", String(dv.busy));

  box.append(taskRow()); // 첫 줄: 첨부 파일 · 할 일(spec_작업 ② §10)
  box.append(divMarksBar()); // 그 아래: 문서 표시 보기/감추기 · 범례 · 추가한 자리 · LLM 재검토(② §11 — 2026-11-10 사용자)
  if (typeof zonesBarEl === "function" && !gatherOn()) box.append(zonesBarEl()); // 그 아래: 「편집 구역」 줄(zones.js — spec_구역 ② §6 「화면」) — 취합은 취합 카드 안에 같은 줄이 있다(gather.js gatherZonesEl)
  const profile = el("section", "dv-profile");
  const profileText = el("div", "dv-profile-copy");
  const profileTitle = el("div", "dv-profile-title");
  profileTitle.append(el("span", "dv-tag" + (ok ? " is-ready" : " is-warning"), ok ? "지원 양식" : "양식 확인 필요"),
    el("strong", null, r.profile.form || "인식된 양식 없음"));
  profileTitle.append(hHelp("지원 양식 안내", ok ? r.profile.name : "지원 양식: " + (r.profile.supportedForms || []).join(", "), { note: true }));
  profileText.append(profileTitle);
  profile.title = ok ? "프로파일 " + r.profile.id + " v" + r.profile.version : "";
  const read = hBtn("문서에서 읽기", () => divRead(), { cls: "btn dv-read", disabled: dv.busy || !r.profile.form,
    title: "문서의 단계·기관 정보를 읽어 입력칸에 채웁니다. 읽히지 않은 값은 유지합니다." });
  const profileActs = el("div", "dv-profile-acts"), fi = r.formInfo; // 양식 정보 — 양식마다 관리하는 사실·요청(② §16 · 편집기는 헤딩 추출과 같은 2열, heading_forms.js)
  if (typeof headsForm === "function") profileActs.append(hBtn(fi ? "양식 정보" : "양식 정보 없음", () => divFormOpen(), { cls: "btn dv-read", // 이름은 도움말에(좁은 패널 — design.md §1)
    title: (fi ? "이 문서의 양식 정보: " + fi.name + "\n" : "이 문서에 맞는 양식 정보가 없습니다 — 눌러서 만들거나 고릅니다\n")
      + "이 양식에 대한 요청(「구분 기준 자리」 절 — 어디가 자리이고 제목·칸에 무엇을 넣는지)을 적어 두면 구분 기준 LLM 검토에 함께 갑니다 · 헤딩 추출·표 요청도 같은 파일" }));
  profileActs.append(read);
  profile.append(profileText, profileActs);
  box.append(profile);
  box.append(divCommentRow()); // 양식별 코멘트 줄 — 양식 줄 바로 아래(② §18)
  if (!ok) box.append(el("p", "dv-notice", "이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다." + (state.format === "docx" ? "" : " 헤딩 추출에서 문서 구조를 확인할 수 있습니다.")));

  const config = el("fieldset", "dv-config");
  config.disabled = dv.busy;
  config.append(divPresetBlock(r, v)); // 저장한 프로젝트 구분 기준 — 설정 맨 위 두 줄(② §8, 2026-11-11)
  const sectionHead = (number, title, note, badgeId) => {
    const head = el("div", "dv-section-head");
    const copy = el("div", "dv-section-copy");
    const heading = el("div", "dv-note-heading");
    heading.append(el("h3", null, title), hHelp(`${title} 안내`, note, { note: true }));
    copy.append(heading);
    head.append(el("span", "dv-step", number), copy);
    if (badgeId) { const badge = el("span", "dv-count"); badge.id = badgeId; head.append(badge); }
    return head;
  };
  const stages = el("section", "dv-card");
  stages.dataset.dv = "stage";
  stages.append(sectionHead("1", "단계·차년도", "각 단계가 몇 년 동안 진행되는지 정하세요.", "divYearCount"));
  const stageList = el("div", "dv-stage-list");
  v.stages.forEach((n, i) => {
    const row = el("div", "dv-stage-row");
    const title = el("div", "dv-stage-copy");
    const range = el("span", "dv-stage-range"); range.dataset.stageRange = i;
    title.append(el("strong", null, (i + 1) + "단계"), range);
    const field = el("label", "dv-year-field");
    const inp = el("input"); inp.type = "number"; inp.min = 1; inp.max = 10; inp.step = 1; inp.value = n;
    inp.setAttribute("aria-label", (i + 1) + "단계 차년도 수");
    const update = () => { v.stages[i] = Math.max(1, Math.min(10, Math.floor(Number(inp.value)) || 1)); divTouched(); };
    inp.oninput = update;
    inp.onchange = () => { update(); inp.value = v.stages[i]; };
    field.append(inp, el("span", null, "년"));
    row.append(title, field);
    if (v.stages.length > 1) row.append(hBtn("×", () => {
      v.stages.splice(i, 1); divTouched(); divRender();
      $("divBox").querySelectorAll(".dv-year-field input")[Math.min(i, v.stages.length - 1)]?.focus();
    }, { cls: "dv-remove", title: (i + 1) + "단계 삭제" }));
    stageList.append(row);
  });
  stages.append(stageList);
  if (v.stages.length < 10) stages.append(hBtn("+ 단계 추가", () => {
    v.stages.push(1); divTouched(); divRender();
    $("divBox").querySelectorAll(".dv-year-field input")[v.stages.length - 1]?.focus();
  }, { cls: "btn dv-add" }));
  const yearError = el("p", "dv-field-error"); yearError.id = "divYearError"; yearError.setAttribute("role", "status");
  stages.append(yearError);
  config.append(stages);

  const orgs = el("section", "dv-card");
  orgs.dataset.dv = "org";
  orgs.append(sectionHead("2", "기관 구성", "참여 기관과 비영리 여부를 입력하세요.\n이름을 쓰고 Enter 를 치면 바로 아래에 공동기관이 추가됩니다. 이름을 비우면 ‘주관기관(미입력)’, ‘참여기관1’처럼 표시됩니다.\n수요기업으로 참여하는 공동기관은 「수요기업」 에 체크하세요 — 그 기관의 제목은 「공동연구개발기관N-수요기업(이름)」, 표지의 「역할」 칸은 「수요」 로 적습니다.", "divOrgCount"));
  const orgList = el("div", "dv-org-list");
  const orgLine = (index, name) => {
    const role = index === 0 ? "주관기관" : "공동기관 " + index;
    const row = el("div", "dv-org-row");
    const label = el("label", "dv-org-field");
    label.append(el("span", "dv-org-role" + (index === 0 ? " is-lead" : ""), index === 0 ? "주관" : "공동"));
    const inp = el("input"); inp.type = "text"; inp.value = name || ""; inp.placeholder = index === 0 ? "주관기관 이름" : "참여기관" + index;
    inp.setAttribute("aria-label", index === 0 ? "주관기관 이름" : "공동연구개발기관" + index + " 이름");
    inp.oninput = () => { if (index === 0) v.orgs.lead = inp.value.trim(); else v.orgs.joint[index - 1] = inp.value.trim(); divTouched(); };
    inp.onkeydown = (e) => { // Enter → 바로 아래에 공동기관 줄을 넣고 포커스(2026-11-10 사용자). 아래 줄이 비어 있거나 이 줄이 비었으면 추가 없이 아래로만 이동
      if (e.key !== "Enter" || e.isComposing || e.keyCode === 229) return; // 한글 조합 중 Enter 는 조합 확정에 맡긴다
      e.preventDefault();
      const next = $("divBox").querySelectorAll(".dv-org-field input")[index + 1];
      if ((next && !next.value.trim()) || !inp.value.trim() || v.orgs.joint.length >= 20) { next?.focus(); return; }
      while (v.orgs.nonprofit.length <= index) v.orgs.nonprofit.push(false);
      v.orgs.joint.splice(index, 0, ""); v.orgs.nonprofit.splice(index + 1, 0, false); v.orgs.demand.splice(index + 1, 0, false); divTouched(); divRender();
      $("divBox").querySelectorAll(".dv-org-field input")[index + 1]?.focus();
    };
    label.append(inp);
    const lab = el("label", "dv-nonprofit"), cb = el("input"); cb.type = "checkbox"; cb.checked = !!v.orgs.nonprofit[index];
    cb.setAttribute("aria-label", role + " 비영리");
    cb.onchange = () => { v.orgs.nonprofit[index] = cb.checked; divTouched(); };
    lab.append(cb, "비영리"); lab.title = "비영리기관 현황에 포함하고 기업 현황에서는 제외합니다.";
    // 「수요기업」 체크(spec_구분_기준 ② §24 — 2026-11-21 사용자 "구분기준.. 기관넣을때. 수요기업 체크하도록 하면되잖아"): 공동기관 줄에만 · 「비영리」 앞. 주관 줄에는 같은 폭의 빈 자리만 둔다(이름 칸의 오른끝이 줄마다 같게)
    const dlab = el("label", "dv-demand" + (v.orgs.demand[index] ? " is-on" : "")), dcb = el("input"); dcb.type = "checkbox"; dcb.checked = !!v.orgs.demand[index];
    dcb.setAttribute("aria-label", role + " 수요기업");
    dcb.onchange = () => { v.orgs.demand[index] = dcb.checked; dlab.classList.toggle("is-on", dcb.checked); divTouched(); };
    dlab.append(dcb, "수요기업");
    dlab.title = "수요기업으로 참여하는 공동기관이면 체크하세요.\n제목을 「공동연구개발기관" + (index || "N") + "-수요기업(이름)」 으로, 표지의 「역할」 칸을 「수요」 로 적습니다 — 문서에 그렇게 적힌 기관은 「문서에서 추출」 이 저절로 체크합니다.";
    if (index === 0) { dlab.classList.add("is-none"); dlab.setAttribute("aria-hidden", "true"); dcb.disabled = true; dcb.tabIndex = -1; }
    const flags = el("span", "dv-org-flags"); flags.append(dlab, lab);
    row.append(label, flags);
    if (index > 0) row.append(hBtn("×", () => {
      v.orgs.joint.splice(index - 1, 1); v.orgs.nonprofit.splice(index, 1); v.orgs.demand.splice(index, 1); divTouched(); divRender();
      $("divBox").querySelectorAll(".dv-org-field input")[Math.min(index, v.orgs.joint.length)]?.focus();
    }, { cls: "dv-remove", title: role + " 삭제" }));
    return row;
  };
  orgList.append(orgLine(0, v.orgs.lead));
  v.orgs.joint.forEach((name, i) => orgList.append(orgLine(i + 1, name)));
  orgs.append(orgList);
  if (v.orgs.joint.length < 20) orgs.append(hBtn("+ 공동기관 추가", () => {
    v.orgs.joint.push(""); v.orgs.nonprofit[v.orgs.joint.length] = false; divTouched(); divRender();
    $("divBox").querySelectorAll(".dv-org-field input")[v.orgs.joint.length]?.focus();
  }, { cls: "btn dv-add" }));
  config.append(orgs);

  const disclosure = (key, title, note) => {
    const detail = el("details", "dv-disclosure"); detail.open = dv.ui[key]; detail.dataset.divDisclosure = key;
    detail.ontoggle = () => { if (detail.isConnected) dv.ui[key] = detail.open; };
    const summary = el("summary");
    summary.append(el("strong", null, title), hHelp(`${title} 안내`, note, { note: true }), el("span", "dv-chevron", "⌄"));
    detail.append(summary);
    return detail;
  };
  const more = disclosure("advanced", "추가 설정", "사업기간·당해 차년도·기타 기관");
  const extra = el("div", "dv-extra-fields");
  const dates = el("div", "dv-date-fields");
  const monthEdge = (key, ymd) => { // 고른 날짜를 시작일은 그 달 1일, 종료일은 그 달 말일로 맞춤(2026-11-10 사용자)
    const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(ymd || ""); if (!m) return ymd || "";
    const last = new Date(Number(m[1]), Number(m[2]), 0).getDate();
    return m[1] + "-" + m[2] + "-" + (key === "start" ? "01" : String(last).padStart(2, "0"));
  };
  for (const [key, label] of [["start", "사업 시작일"], ["end", "사업 종료일"]]) {
    const lab = el("label", "dv-field"); lab.append(el("span", null, label));
    const inp = el("input"); inp.type = "date"; inp.value = v.period[key] || ""; inp.setAttribute("aria-label", label);
    inp.onchange = () => { v.period[key] = monthEdge(key, inp.value); inp.value = v.period[key]; divTouched(); }; lab.append(inp); dates.append(lab);
  }
  extra.append(dates);
  const currentLabel = el("div", "dv-field"), currentHead = el("div", "dv-field-label"), currentName = el("label", null, "당해 차년도");
  currentLabel.dataset.dv = "year";
  currentName.htmlFor = "divCurrentYear";
  currentHead.append(currentName, hHelp("당해 차년도 안내", "신청·협약 대상 연도입니다. 전체 차년도 순서로 선택하세요.", { note: true }));
  currentLabel.append(currentHead);
  const current = el("select"); current.id = "divCurrentYear"; current.setAttribute("aria-label", "당해 차년도");
  current.onchange = () => { v.current = Number(current.value); divTouched(); };
  currentLabel.append(current);
  extra.append(currentLabel);
  for (const [key, name] of Object.entries({ ...DV_EXTRA, subs: "세부과제 주관기관" })) {
    const lab = el("div", "dv-field"), heading = el("div", "dv-field-label"), label = el("label", null, name);
    label.htmlFor = `divExtra-${key}`;
    heading.append(label);
    heading.append(hHelp(`${name} 안내`, "기관 이름을 쉼표로 구분해 입력하세요.\n" + (key === "subs"
      ? "비워 두면 세부과제 자리를 유지합니다."
      : "비워 두면 해당 기관 자리를 삭제하는 계획을 만듭니다."), { note: true }));
    lab.append(heading);
    const inp = el("input"); inp.id = label.htmlFor; inp.type = "text"; inp.placeholder = "기관명, 기관명"; inp.setAttribute("aria-label", name);
    inp.value = (key === "subs" ? (v.subs || []) : (v.orgs[key] || [])).join(", ");
    inp.oninput = () => {
      const names = inp.value.split(",").map(s => s.trim()).filter(Boolean);
      if (key === "subs") v.subs = names; else v.orgs[key] = names;
      divTouched();
    };
    lab.append(inp);
    extra.append(lab);
  }
  more.append(extra); config.append(more);

  config.querySelectorAll(".dv-remove").forEach(button => button.setAttribute("aria-label", button.title));
  taskFrameApply = null;
  const host = taskFrameHost(box), staged = host !== box; // 이관·취합이면 구성 입력은 1단계 「구분 기준」 묶음 안(#taskFrameForm), 반영 상태·변경 계획은 2단계 「문서 프레임 작성」 묶음 안(#taskFrameApply — spec_작업 ② §18), 아니면 패널 그대로
  const ahost = (staged && taskFrameApplyHost(box)) || host;

  // 실행 묶음(변경 계획 보기 → 반영 · 계획 다시 열기 · 한 번에 진행 — spec_구분_기준 ② §22) + 그 아래 「문서 반영 상태」. 묶음 없는 TASK(양식 맞추기)는 패널 맨 위 — 첫 카드 바로 다음, 이관·취합은 2단계 묶음 안.
  // 묶음 없는 TASK 는 구성 입력(불러오기·확정 · 단계·차년도 · 기관)도 그 카드 안 — 「한 번에 진행」 · 「불러오기」 만 보이고 나머지는 접어 둔 「세부」(divRunFold — ② §22 「카드 하나」)
  const applied = el("section", "dv-applied"); applied.id = "divAppliedState"; applied.setAttribute("aria-live", "polite");
  const run = divRunBar(staged);
  if (staged) { host.append(config); ahost.append(run, applied); }
  else { divRunFold(run, config); box.firstElementChild.after(run, applied); }
  // 이관이면 구분 기준 자리 표시 · 지원 양식 줄 · 양식별 코멘트도 프레임 묶음 안 — 변경 계획 아래(2026-11-12 사용자 "구분기준 자리 표시가 있네" → 물어서 받은 답 「1단계 안으로 옮김」 — 11-13 그 묶음이 2단계:
  // 구조(구분 기준) 확인용이라 그 묶음에 둔다 · design.md §11 「묶음이 쓰는 입력·결과 값은 그 묶음 안에」). 취합(gather.js)은 그쪽 몫이라 전처럼 패널에
  if (staged && taskSlots()) ahost.append(...[...box.querySelectorAll(":scope > #divMarksBar, :scope > .dv-profile, :scope > #divComments, :scope > .dv-notice")]);
  divRefreshDerived();
  if (panelKeep) panelKeep();
  if (dv.keepFocus && !dv.busy) { // 실행 묶음의 단추를 눌러 돌린 일이 끝났다 — 다시 그리며 잃은 초점을 다음 단추로(그 사이 다른 곳을 눌렀으면 그대로 둔다)
    dv.keepFocus = false;
    const at = document.activeElement;
    if (!at || at === document.body) (run.querySelector("button.primary:not(:disabled)") || run.querySelector("button:not(:disabled)"))?.focus({ preventScroll: true });
  }
}

function divRefreshDerived() {
  if (!dv.values || !dv.view || !$("divYearCount")) return;
  const v = dv.values, total = divTotalYears(v);
  $("divYearCount").textContent = "전체 " + total + "년";
  $("divYearCount").classList.toggle("is-warning", total > 20);
  $("divOrgCount").textContent = "주관 1 · 공동 " + v.orgs.joint.length;
  let start = 1;
  document.querySelectorAll("#divBox [data-stage-range]").forEach(node => {
    const years = v.stages[Number(node.dataset.stageRange)];
    node.textContent = (years === 1 ? start : start + "–" + (start + years - 1)) + "차년도";
    start += years;
  });
  $("divYearError").textContent = total > 20 ? "전체 차년도는 20년 이하여야 합니다. 단계별 기간을 줄여 주세요." : "";
  $("divYearError").hidden = total <= 20;
  const current = $("divCurrentYear"), max = Math.min(total, 20);
  if ((v.current || 1) > max) v.current = max; // 차년도 합을 줄이면 당해 차년도도 그 안으로 — 표시만 자르면 다시 늘릴 때 옛 값이 되살아남(2026-11-11 astra P2)
  if (current.options.length !== max) {
    current.textContent = "";
    for (let year = 1; year <= max; year++) current.append(new Option(year + "차년도", year));
  }
  current.value = String(Math.min(v.current || 1, max));
  $("divReviewSummary").textContent = v.stages.length + "단계 · 전체 " + total + "년 · 기관 " + (v.orgs.joint.length + 1) + "곳";
  $("divReviewSummary").title = `지금 입력 값 — ${divValuesText(divValues())}`; // 입력이 접혀 있어도(실행 묶음의 「세부」) 불러온 값을 올려서 확인
  divRunSync(); // 실행 묶음의 단추·상태 줄(② §22) — TASK 묶음 안이면 1단계(프로젝트 구성 추출)가 끝나야 변경 계획(spec_작업 ② §18: divRunWhy)
  divPresetRefresh(); // 「X」 수정됨 · 「저장」 켜짐(② §8)
  divRenderApplied();
  taskStepsDraw(); // 이관 단계 ① 구분 기준 확인 — 지금 문서의 입력 값으로 다시 견준다(spec_작업 ② §11)
}

function divRenderApplied() {
  const target = $("divAppliedState"); if (!target || !dv.view) return;
  target.textContent = "";
  const a = dv.view.applied;
  const head = el("div", "dv-applied-head");
  head.append(el("h3", null, "문서 반영 상태"));
  if (!a) {
    head.append(el("span", "dv-tag", "아직 미반영"), hHelp("문서 반영 순서", "기준을 설정한 뒤 변경 계획을 확인하고 문서에 반영하세요.", { note: true }));
    target.append(head);
  } else {
    const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object"
      ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
    const same = JSON.stringify(canonical(a.values)) === JSON.stringify(canonical(divValuesNormalized()));
    const edited = a.rev !== state.serverRev;
    const issues = (a.summary?.unresolved || 0) + (a.summary?.unsupported || 0) + (a.summary?.excluded || 0);
    const ruled = a.profileVersion != null && a.profileVersion !== dv.view.profile.version; // 반영 뒤 구분 기준 규칙(프로파일 판)이 바뀜 — 그때 없던 자리가 새로 잡힐 수 있다(② §16)
    head.append(el("span", "dv-tag" + (!same || edited || issues || ruled ? " is-warning" : " is-ready"),
      !same ? "입력값 변경" : ruled ? "새 규칙 — 계획 확인" : edited ? "반영 후 문서 수정" : issues ? "반영 결과 확인 필요" : "마지막 반영값과 같음"));
    target.append(head, el("p", "dv-applied-values", a.values.stages.length + "단계 · 전체 " + divTotalYears(a.values) + "년 · 주관 " + (a.values.orgs.lead || "미입력") + " · 공동 " + a.values.orgs.joint.length + "곳"),
      el("p", "dv-caption", "마지막 반영 " + fmtWhen(a.at) + (edited ? " · 이후 문서가 수정되어 새 계획으로 확인이 필요합니다." : !same ? " · 현재 입력값은 아직 반영하지 않았습니다." : ruled ? "" : " · 현재 입력값이 마지막 반영 기록과 일치합니다.")
        + (ruled ? " · 반영한 뒤 구분 기준 규칙이 늘었습니다 — 「변경 계획 보기」 로 새로 잡힌 자리를 확인하세요." : "")));
    const rv = dv.marks.review; // 마지막 LLM 검토 때 스크립트가 센 「값과 아직 안 맞는 자리」(② §16) — 그 뒤 문서가 안 바뀌었을 때만
    if (rv && Array.isArray(rv.pending) && rv.pending.length && rv.rev === state.serverRev)
      target.append(el("p", "dv-plan-note", "값과 안 맞는 자리 " + rv.pending.length + "곳(마지막 검토 기준) — 「변경 계획 보기」 로 확인하고 반영하세요."));
    if (a.summary) target.append(divSummary(a.summary));
    if (state.undo) target.append(hBtn("↶ 마지막 구조 편집 실행 취소", () => divUndo(), { cls: "btn dv-undo", disabled: dv.busy,
      title: "마지막 구조 편집 직전으로 되돌립니다. 그 뒤 고친 글도 함께 돌아갑니다." }));
  }
  // 계획의 상태(없음 · 준비됨 · 입력·문서가 바뀜 · 반영 완료)는 바로 위 실행 묶음의 상태 줄에(divRunSync — ② §22). 여기는 마지막 반영 기록만
}

function divValuesNormalized() { // applied.values(서버가 정리한 꼴)와 견줄 입력 값 — 서버 정리 규칙의 핵심만(빈 이름·목록 기본값)
  const o = divValues();
  const n = o.orgs.joint.length + 1;
  o.orgs.nonprofit = Array.from({ length: n }, (_, i) => !!o.orgs.nonprofit[i]);
  for (const k of Object.keys(DV_EXTRA)) o.orgs[k] = o.orgs[k] || [];
  o.subs = o.subs || [];
  o.current = o.current || 1;
  return o;
}

function divSummary(s) {
  const row = el("div", "dv-sum");
  for (const k of ["applied", "already", "excluded", "unsupported", "unresolved"]) if (s[k]) row.append(el("span", `dv-badge ${k}`, `${DV_STATUS[k]} ${s[k]}`));
  row.append(el("span", "muted", `추가 ${s.added} · 지움 ${s.removed} · 글 바꿈 ${s.changes}${s.deleted != null ? ` · 지워지는 글 문단 ${s.deleted}` : ""}`));
  return row;
}

function divTouched() {
  const hadPlan = !!dv.plan;
  dv.plan = null; dv.result = null; dv.skip = new Set(); dv.dirty = true;
  dv.msg = hadPlan ? { kind: "note", text: "입력값이 바뀌었습니다 · 다시 계획하세요" } : dv.msg && dv.msg.kind === "note" ? dv.msg : null; // 멈춤·끝 글은 값이 바뀌면 지난 일
  divSettingsSchedule(); // 입력값은 작업에도 — 0.7초 뒤 PUT …/settings(② §8 자동 저장)
  divRefreshDerived();
  divFootSync(); // 열려 있는 2열 목록의 발 — 그 계획은 더 반영할 수 없다(다시 계획은 패널의 실행 묶음에서 — ② §22)
}

async function divUndo() { // 실행 취소(마지막 구조 편집 = 보통 이 반영) 뒤 계획·결과를 버리고 3열·2열을 새로
  const epoch = state.epoch, before = state.localRev;
  await undoStruct();
  if (epoch !== state.epoch || state.localRev === before) return; // 되돌리지 않았으면(확인 창에서 그만둠 · 실패) 계획·결과는 그대로
  dv.plan = null;
  dv.result = null;
  dv.msg = null;
  if (heads.dlg === "divisions") headsColClose();
  divShow();
}

async function divRead(src = null) { // 문서에 적힌 구성 읽기 — src 없음 = 지금 문서, {id, name} = 이 프로젝트의 다른 문서(그 문서를 서버가 연다 — 읽기만). 입력 칸만 바뀐다(문서·확정은 그대로 — spec_작업 ② §18)
  if (!state.id) return;
  const epoch = state.epoch, id = (src && src.id) || state.id, name = src && src.id !== state.id ? src.name : "";
  try {
    const r = await api(`/api/docs/${id}/divisions/read`);
    if (epoch !== state.epoch) return;
    divReadApply(r.read, name ? `「${name}」` : "문서");
  } catch (e) { if (epoch === state.epoch) toast(`${name ? `「${name}」 에서` : "문서에서"} 읽지 못했습니다: ${e.message}`, true); }
}
function divReadFile() { // 「파일 올려 추출…」 — 파일 고르기 → POST /api/divisions/read-file(작업을 만들지 않음) → 입력 칸
  const inp = el("input");
  inp.type = "file";
  inp.accept = ".hwp,.hwpx";
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f || !state.id) return;
    if (!/\.hwpx?$/i.test(f.name)) { toast("hwp·hwpx 파일만 읽을 수 있습니다", true); return; }
    const epoch = state.epoch, fd = new FormData();
    fd.append("file", f);
    toast(`${f.name} — 프로젝트 구성 읽는 중…${/\.hwp$/i.test(f.name) ? "(한글이 hwpx 로 바꿈)" : ""}`);
    try {
      const r = await api("/api/divisions/read-file", { method: "POST", body: fd });
      if (epoch === state.epoch) divReadApply(r.read, `「${f.name}」`);
    } catch (e) { if (epoch === state.epoch) toast(`「${f.name}」 에서 읽지 못했습니다: ${e.message}`, true); }
  };
  inp.click();
}
function divReadApply(got, from) { // 읽은 값(…/divisions/read 꼴) → 입력 칸(읽은 키만 바꿈 — 못 읽은 값은 둔다)
  got = got || {};
  const v = dv.values, names = [];
  if (got.stages) { v.stages = got.stages; names.push("단계·차년도"); }
  if (got.period) { v.period = got.period; names.push("사업기간"); }
  if (got.current) { v.current = got.current; names.push("당해 차년도"); }
  if (got.subs && got.subs.length) { v.subs = got.subs; names.push("세부과제"); }
  const o = got.orgs || {};
  if (o.lead != null) { v.orgs.lead = o.lead; names.push("주관"); }
  if (o.joint) { // 공동 목록이 바뀌면 수요기업 표시도 읽은 것으로(없으면 비움 — 옛 목록의 자리에 남지 않게: spec_구분_기준 ② §24)
    v.orgs.joint = o.joint; v.orgs.demand = Array.isArray(o.demand) ? o.demand : [];
    const dm = v.orgs.demand.filter(Boolean).length;
    names.push(`공동 ${o.joint.length}곳${dm ? `(수요기업 ${dm}곳)` : ""}`);
  }
  if (o.nonprofit) { v.orgs.nonprofit = o.nonprofit; names.push("비영리"); }
  for (const k of Object.keys(DV_EXTRA)) if (o[k] && o[k].length) { v.orgs[k] = o[k]; names.push(`${DV_EXTRA[k]} ${o[k].length}곳`); }
  if (names.length) dv.preset.from = `${from}에서 추출`;
  divTouched();
  divRender();
  toast(names.length ? `${from}에서 읽음: ${names.join(" · ")} — 확인한 뒤 「${divConfirmWhere(dv.view && dv.view.projectSharing)}에 저장」` : `${from}에서 읽을 수 있는 값이 없습니다(자리표시뿐)`);
}

// ---- 프로젝트 구성 추출(spec_작업 ② §18 — 2026-11-13 사용자 "현재 프로젝트에 구성을 저장하고 사용할 수 있도록"): 1단계 「구분 기준」 의 끝 = 입력 값이 확정한 값과 같음.
// 확정은 프로젝트에 하나(공유 중인 작업) · 프로젝트가 없거나 이전 라운드면 그 작업에. 입력은 전처럼 자동 공유되고, 바꾸면 확정이 풀린다(valid 아님).
const divConfirmKey = (v) => { const o = JSON.parse(divCanon(v)); delete o.current; return JSON.stringify(o); }; // 확정 비교 — 당해 차년도는 안 견준다(보고서마다 다를 수 있음 — taskDivDiff 와 같은 규칙)
const divConfirmValid = (values, cf) => !!(values && cf && cf.values && divConfirmKey(cf.values) === divConfirmKey(values));
const divConfirmWhere = (sharing) => (sharing && sharing.shared && sharing.project ? `프로젝트 「${sharing.project}」` : "이 문서");
const divConfirmWhat = (where) => (where === "이 문서" ? "이 문서의 프로젝트 구성" : `${where} 구성`); // 값 묶음의 화면 이름은 「프로젝트 구성」(spec_작업 ② §19 「화면 말」) — 프로젝트 이름이 앞에 있으면 「프로젝트 「X」 구성」, 프로젝트가 없는 작업이면 「이 문서의 프로젝트 구성」
function divValuesText(v) { // 「1단계(1–4차년도) · 주관 한국선급 · 공동 3(씨드로닉스 · 유엔젤 · 랩오투원)」
  if (!v) return "";
  let start = 1;
  const stages = (v.stages || []).map((n, i) => { const y = Number(n) || 1, s = `${i + 1}단계(${y === 1 ? start : `${start}–${start + y - 1}`}차년도)`; start += y; return s; });
  const orgs = v.orgs || {}, dm = orgs.demand || [], joint = (orgs.joint || []).map((n, i) => (n || `참여기관${i + 1}`) + (dm[i + 1] ? "(수요기업)" : "")); // 수요기업으로 고른 기관은 이름 뒤에 적는다(spec_구분_기준 ② §24)
  return `${stages.join(" · ")} · 주관 ${orgs.lead || "미입력"} · 공동 ${joint.length}${joint.length ? `(${joint.join(" · ")})` : ""}`;
}
async function divConfirm(opt = {}) { // 지금 입력 값을 확정(POST …/divisions/confirm) → 됐으면 true
  if (!state.id || !dv.values || !dv.view) return false;
  const id = state.id, epoch = state.epoch, values = divValues(), where = divConfirmWhere(dv.view.projectSharing);
  await divSettingsFlush();
  if (epoch !== state.epoch) return false;
  try {
    const r = await api(`/api/docs/${id}/divisions/confirm`, { method: "POST", headers: H_JSON, body: JSON.stringify({ values }) });
    if (epoch !== state.epoch || !dv.view) return false;
    Object.assign(dv.view, { settings: r.settings, dimensions: r.dimensions, plan: r.plan, stale: r.stale, projectSharing: r.projectSharing, confirmed: r.confirmed || null, ...("versions" in r ? { versions: r.versions } : {}) }); // versions = 구분 기준 버전(② §19 — 옛 서버면 없음: 건드리지 않는다)
    dv.savedKey = divCanon(values);
    divRender();
    if (typeof taskFlowLoad === "function") taskFlowLoad(); // 이관 — 다른 칸 문서의 확정 상태도 다시(같은 프로젝트면 같은 확정)
    if (!opt.quiet) toast(`프로젝트 구성을 ${where}에 확정했습니다 — ${divValuesText(values)}`);
    return true;
  } catch (e) { if (epoch === state.epoch) toast(`프로젝트 구성을 확정하지 못했습니다: ${e.message}`, true); return false; }
}
function divConfirmRevert(cf) { // 「확정본으로 되돌리기」 — 입력 칸만(문서·확정 그대로)
  if (!cf || !cf.values || !dv.values) return;
  const cur = dv.values.current;
  dv.values = structuredClone(cf.values);
  if (!dv.values.current && cur) dv.values.current = cur;
  dv.preset.from = "확정본";
  divTouched();
  divRender();
  toast("확정한 프로젝트 구성으로 되돌렸습니다");
}

// ---- 저장한 과제 구성(spec_구분_기준 ② §0 용어 · §7 presets · §8 「저장한 과제 구성」, 2026-11-11 astra 안 1) — 설정 맨 위 두 줄 + ⋯ 셋째 줄 · 이름·삭제 확인은 인라인(모달 금지)
const DV_CANON_KEYS = ["current", "demand", "end", "entrust", "joint", "lead", "nonprofit", "orgs", "outside", "overseas", "period", "stages", "start", "subs"]; // JSON.stringify 의 키 목록 = 키 차례 고정
function divCanon(v) { // 서버 norm_values 가 내는 꼴과 같게 정리해 글로 — 저장본(프로젝트 구분 기준)·작업 설정과 견준다(키 정렬·빈칸 정리·비영리 수 맞춤·기본값)
  v = v || {};
  const o = v.orgs || {}, names = (xs) => (Array.isArray(xs) ? xs : []).map((s) => String(s ?? "").trim());
  const stages = (v.stages || []).map((n) => Number(n) || 1), joint = names(o.joint), total = stages.reduce((a, b) => a + b, 0);
  const nonprofit = (Array.isArray(o.nonprofit) ? o.nonprofit : []).map(Boolean).concat(Array(joint.length + 1).fill(false)).slice(0, joint.length + 1);
  const demand = divDemand({ joint, demand: o.demand }); // 수요기업으로 고른 기관 — 고른 것이 있을 때만(서버 norm_values 와 같게: 옛 값의 글이 달라지지 않는다)
  const out = { stages, orgs: { lead: String(o.lead || "").trim(), joint, nonprofit, ...(demand ? { demand } : {}), outside: names(o.outside), overseas: names(o.overseas), entrust: names(o.entrust) },
    subs: names(v.subs), current: Math.max(1, Math.min(Number(v.current) || 1, total || 1)) };
  if (v.period && (v.period.start || v.period.end)) out.period = { start: v.period.start || "", end: v.period.end || "" };
  return JSON.stringify(out, DV_CANON_KEYS);
}
const divPresetName = (s) => String(s || "").trim().replace(/\s+/g, " "); // 서버 _name 과 같게
const divPresetSummary = (p) => `${p.name} · ${p.values.stages.join("+")}년 · 공동 ${p.values.orgs.joint.length}`;

// ---- 프로젝트 구성 불러오기·확정(spec_작업 ② §18 — 2026-11-13 전의 「저장한 프로젝트 구분 기준」 두 줄을 바꿈): 첫 줄 = 고르기 목록 「프로젝트 구성 불러오기」(이 프로젝트 · 문서에서 추출 · 다른 프로젝트 · 저장한 프로젝트 구성) + 「불러오기」,
// 둘째 줄 = 확정 상태 + 「프로젝트에 저장」(확정) + ⋯(이름 붙여 저장 · 삭제 — 저장한 프로젝트 구성 목록). 불러오기는 입력 칸만 바꾼다(문서·확정은 그대로). 모달 없음
function divSourceDocs() { // 「문서에서 추출」 목록 — 지금 문서 + 같은 프로젝트·TASK·라운드 문서 + 취합의 기관 문서(미소속이어도). 기준 문서(취합본·사업계획서)가 앞
  const seen = new Set(), out = [], add = (w) => { if (w && w.id && !seen.has(w.id)) { seen.add(w.id); out.push(w); } };
  const basis = gatherOn() ? gatherPlan() : taskSlots() ? taskSlotDoc("plan") : null;
  add(basis);
  add(worksList.find((w) => w.id === state.id) || (state.id ? { id: state.id, name: state.name || "지금 문서", task: state.task } : null));
  for (const w of taskMates()) add(w);
  if (gatherOn()) for (const p of ((gt().view || {}).parts || [])) add(worksList.find((w) => w.id === p.work) || { id: p.work, name: p.name, task: { file: "part" } });
  return out;
}
function divSourceFill(sel, r) { // 고르기 목록의 항목 — 다른 프로젝트 목록은 늦게 와서(GET /api/projects) 이 목록만 다시 채운다(입력 중 포커스 그대로)
  const keep = sel.value, sharing = r.projectSharing, me = sharing && sharing.project, cf = r.confirmed, group = (label) => { const g = el("optgroup"); g.label = label; sel.append(g); return g; };
  sel.textContent = "";
  sel.append(new Option("프로젝트 구성 불러오기 — 고르세요", ""));
  // 구분 기준 버전은 여기 넣지 않는다(spec_작업 ② §19) — 이 목록은 입력 칸만 바꾸고 버전 적용은 확정까지 한다: 버전은 프로젝트 칸 아래의 버전 줄(.project-versions)에서만
  if (cf && cf.values) group(me && cf.scope === "project" ? `이 프로젝트 「${me}」` : "이 문서").append(new Option(`확정한 프로젝트 구성 — ${divValuesText(cf.values)}`, "confirmed"));
  const docs = group("문서에서 추출");
  for (const w of divSourceDocs()) { const f = taskName("file", (w.task || {}).file); docs.append(new Option(`${w.name}${f ? `(${f})` : ""}${w.id === state.id ? " — 지금 문서" : ""}`, `doc:${w.id}`)); }
  docs.append(new Option("파일 올려 추출…", "file"));
  const others = (dv.projects || []).filter((p) => p.name !== me && ((p.confirmed && p.confirmed.values) || (p.settings && p.settings.values)));
  if (others.length) { const g = group("다른 프로젝트"); for (const p of others) g.append(new Option(`${p.name} — ${divValuesText((p.confirmed && p.confirmed.values) || p.settings.values)}${p.confirmed ? " · 확정" : ""}`, `project:${p.name}`)); }
  const ps = r.presets || [];
  if (ps.length) { const g = group("저장한 프로젝트 구성"); for (const p of ps) g.append(new Option(divPresetSummary(p), `preset:${p.id}`)); }
  sel.value = [...sel.options].some((o) => o.value === keep) ? keep : "";
}
async function divProjectsLoad() { // 다른 프로젝트의 구성(GET /api/projects — 프로젝트마다 settings · confirmed) — 패널을 그릴 때 한 번(30초 안이면 다시 안 읽음)
  if (dv.projectsBusy || (dv.projectsAt && Date.now() - dv.projectsAt < 30000)) return;
  dv.projectsBusy = true;
  const epoch = state.epoch;
  try { const r = await api("/api/projects"); if (epoch !== state.epoch) return; dv.projects = r.projects || []; dv.projectsAt = Date.now(); }
  catch { dv.projects = dv.projects || []; }
  finally { dv.projectsBusy = false; }
  const sel = document.getElementById("divSourceSel");
  if (sel && dv.view) divSourceFill(sel, dv.view);
}
async function divSourceLoad(key) { // 「불러오기」 — 고른 곳의 값으로 입력 칸을 채운다(확정은 「프로젝트에 저장」)
  if (!key || !dv.view) return;
  const [kind, ...rest] = key.split(":"), arg = rest.join(":");
  if (kind === "confirmed") { divConfirmRevert(dv.view.confirmed); return; }
  if (kind === "file") { divReadFile(); return; }
  if (kind === "doc") { const w = divSourceDocs().find((x) => x.id === arg); await divRead(w ? { id: w.id, name: w.name } : { id: arg, name: arg }); return; }
  if (kind === "preset") { await divPresetLoad(arg); return; }
  if (kind === "project") {
    const p = (dv.projects || []).find((x) => x.name === arg), v = p && ((p.confirmed && p.confirmed.values) || (p.settings && p.settings.values));
    if (!v) { toast("그 프로젝트의 구성을 읽지 못했습니다", true); return; }
    const cur = dv.values && dv.values.current;
    dv.values = structuredClone(v);
    if (!dv.values.current && cur) dv.values.current = cur;
    dv.preset.from = `프로젝트 「${p.name}」에서 불러옴`;
    divTouched(); divRender();
    toast(`프로젝트 「${p.name}」 의 구성을 불러왔습니다 — 확인한 뒤 「${divConfirmWhere(dv.view.projectSharing)}에 저장」`);
  }
}

function divPresetBlock(r, v) {
  const ps = r.presets || [], st = dv.preset, box = el("section", "dv-presets");
  box.setAttribute("aria-label", "프로젝트 구성 불러오기·확정");
  if (!st.loaded) { // 입력값이 어느 저장 항목과 똑같으면 그 항목을 불러온 것으로(다시 연 작업 등) — ⋯ 의 덮어쓰기·삭제 대상
    const same = ps.find((p) => divCanon(p.values) === divCanon(v));
    if (same) st.loaded = { id: same.id, name: same.name, values: divCanon(same.values) };
  }
  const row1 = el("div", "dv-preset-row");
  const sel = el("select"); sel.id = "divSourceSel"; sel.setAttribute("aria-label", "프로젝트 구성 불러오기 — 이 프로젝트 확정본 · 문서에서 추출 · 다른 프로젝트 · 저장한 프로젝트 구성");
  divSourceFill(sel, r);
  if (st.source && [...sel.options].some((o) => o.value === st.source)) sel.value = st.source;
  const load = hBtn("불러오기", () => divSourceLoad(sel.value), { cls: "btn", disabled: !sel.value,
    title: "고른 곳의 프로젝트 구성(단계·차년도·기관)을 입력 칸에 채웁니다 — 문서와 확정은 그대로, 확인한 뒤 「프로젝트에 저장」 으로 확정합니다" });
  load.id = "divSourceLoad";
  sel.onchange = () => { st.source = sel.value; load.disabled = !sel.value; st.confirming = ""; };
  row1.append(sel, load);
  const row2 = el("div", "dv-preset-row dv-preset-save");
  const status = el("div", "dv-preset-status"); status.id = "divPresetStatus";
  const save = hBtn("프로젝트에 저장", () => divConfirm(), { cls: "btn" }); save.id = "divConfirmBtn";
  const more = hBtn("⋯", () => { st.more = !st.more; st.confirming = ""; divRender(); }, { cls: "btn dv-more" + (st.more ? " on" : ""), title: "이름 붙여 저장 · 저장한 프로젝트 구성 삭제" });
  more.setAttribute("aria-expanded", String(st.more)); more.setAttribute("aria-label", "더 보기 — 이름 붙여 저장, 저장한 프로젝트 구성 삭제");
  row2.append(save, more);
  box.append(row1, status, row2);
  if (dv.projects === undefined || !dv.projectsAt) divProjectsLoad();
  if (st.more) { // 셋째 줄 — 덜 쓰는 조작(이름 붙여 저장한 프로젝트 구성 — 모든 프로젝트 공용 목록). 삭제 대상 = 목록에서 고른 저장한 프로젝트 구성, 없으면 지금 값과 같은 것
    const row3 = el("div", "dv-preset-row dv-preset-extra");
    const del = hBtn("삭제", () => { const t = divPresetTarget(); st.confirming = t ? t.id : ""; st.naming = false; divRender(); }, { cls: "btn dv-delete" }); del.id = "divPresetDelBtn";
    const over = st.loaded && divCanon(v) !== st.loaded.values ? hBtn(`「${st.loaded.name}」 덮어쓰기`, () => divPresetSave(), { cls: "btn", title: "그 저장한 프로젝트 구성을 지금 값으로 덮어씁니다" }) : null;
    if (over) over.id = "divPresetSaveBtn";
    row3.append(hBtn("이름 붙여 저장…", () => divPresetNaming(true), { cls: "btn", title: "지금 값을 이름 붙여 「저장한 프로젝트 구성」 에 둡니다(다른 프로젝트에서도 불러올 수 있음)" }), ...(over ? [over] : []), del);
    box.append(row3);
  }
  if (st.naming) { // 이름 줄(인라인) — Enter 저장 · Esc 취소
    const row = el("div", "dv-preset-row"), note = el("span", "dv-preset-note");
    const inp = el("input"); inp.type = "text"; inp.maxLength = 60; inp.placeholder = "저장할 이름(예: 2026 ○○ 과제)"; inp.setAttribute("aria-label", "저장할 이름");
    inp.value = st.nameDraft ?? (st.loaded ? st.loaded.name : "");
    const check = () => { st.nameDraft = inp.value; const n = divPresetName(inp.value), same = n && ps.find((p) => p.name === n); note.textContent = same ? `같은 이름 「${same.name}」 을 덮어씁니다` : ""; };
    inp.oninput = check; check();
    inp.onkeydown = (e) => { if (e.isComposing || e.keyCode === 229) return; if (e.key === "Enter") { e.preventDefault(); divPresetSaveAs(inp.value); } else if (e.key === "Escape") { e.preventDefault(); divPresetNaming(false); } };
    row.append(inp, hBtn("저장", () => divPresetSaveAs(inp.value), { cls: "btn primary" }), hBtn("취소", () => divPresetNaming(false), { cls: "btn" }));
    box.append(row, note);
    queueMicrotask(() => { if (inp.isConnected) inp.focus(); });
  }
  if (st.confirming) { // 삭제 확인 줄(인라인)
    const p = ps.find((x) => x.id === st.confirming), row = el("div", "dv-preset-row");
    row.append(el("span", "dv-preset-status", p ? `「${p.name}」 을 지울까요?` : "지울 항목이 없습니다"),
      hBtn("지움", () => divPresetDelete(st.confirming), { cls: "btn dv-delete", disabled: !p }), hBtn("취소", () => { st.confirming = ""; divRender(); }, { cls: "btn" }));
    box.append(row);
  }
  return box;
}

function divPresetTarget() { // 삭제 대상 = 목록에서 고른 저장한 프로젝트 구성, 없으면 지금 값과 같은 것(불러온 것)
  const st = dv.preset, ps = dv.view?.presets || [], pick = String(st.source || "").startsWith("preset:") ? st.source.slice(7) : "";
  return ps.find((p) => p.id === pick) || (st.loaded && ps.find((p) => p.id === st.loaded.id)) || null;
}

function divPresetRefresh() { // 상태 줄(확정 — spec_작업 ② §18)·「프로젝트에 저장」·「삭제」 — 입력·고른 것이 바뀔 때마다(divRefreshDerived)
  const status = $("divPresetStatus"), save = $("divConfirmBtn"); if (!status || !save || !dv.view) return;
  const st = dv.preset, cf = dv.view.confirmed, where = divConfirmWhere(dv.view.projectSharing), valid = divConfirmValid(dv.values, cf);
  const del = $("divPresetDelBtn");
  if (del) { const t = divPresetTarget(); del.disabled = !t; del.title = t ? `저장한 프로젝트 구성 「${t.name}」 삭제` : "지울 저장한 프로젝트 구성을 위 목록에서 고르세요"; }
  status.textContent = ""; status.title = "";
  if (dv.view.presetsBroken) {
    const t = el("span", "dv-tag is-warning", "저장 파일 손상"); t.title = "저장한 프로젝트 구성 파일이 손상되어 비어 보입니다(.broken 사본) — 파일을 고치거나 옮긴 뒤 다시"; status.append(t);
  }
  const name = el("span", "dv-preset-name", `${divConfirmWhat(where)}`); name.title = `${divConfirmWhat(where)} — 같은 프로젝트의 워크플로우들이 같이 씁니다`; status.append(name);
  const tag = valid ? el("span", "dv-tag is-ready", "확정함") : cf ? el("span", "dv-tag is-warning", "확정 뒤 바뀜") : el("span", "dv-tag", "확정 전");
  tag.dataset.confirm = valid ? "valid" : cf ? "changed" : "none";
  if (cf && cf.at) tag.title = `확정 ${fmtWhen(cf.at)} — ${divValuesText(cf.values)}`;
  status.append(tag);
  const sharing = dv.view.projectSharing, key = dv.values ? divCanon(divValues()) : "";
  const ver = ((sharing && sharing.shared && dv.view.versions) || []).find((x) => divCanon(x.values) === key); // 지금 입력과 같은 구분 기준 버전(② §19 — 당해 차년도까지 같음)
  if (ver) { const t = el("span", "dv-tag", `버전 「${ver.name}」`); t.dataset.versionTag = ver.id; t.title = `지금 입력 값이 프로젝트 구성 버전 「${ver.name}」 과 같습니다`; status.append(t); }
  if (typeof projectSharingSync === "function") projectSharingSync(); // 프로젝트 칸 아래의 구분 기준 있음/없음 줄 · 버전 줄도 입력에 맞춘다
  if (st.from) { const f = el("span", "dv-caption", st.from); f.title = "마지막으로 입력 칸을 채운 곳(이 화면에서만)"; status.append(f); }
  save.textContent = `${dv.view.projectSharing && dv.view.projectSharing.shared ? "프로젝트" : "이 문서"}에 저장`;
  save.disabled = dv.busy || valid;
  save.title = valid ? `지금 값이 ${where}에 확정한 구성과 같습니다` : `지금 입력 값(단계·차년도·기관)을 ${divConfirmWhat(where)}으로 확정합니다 — 문서는 바뀌지 않습니다(${taskSlots() ? "「프로젝트 구성 추출」" : "1단계 「프로젝트 구성」"} 의 끝)`;
}

function divPresetNaming(on) { dv.preset.naming = on; dv.preset.confirming = ""; if (!on) dv.preset.nameDraft = null; divRender(); }

async function divPresetLoad(pid) {
  const p = (dv.view?.presets || []).find((x) => x.id === pid); if (!p) return;
  dv.values = structuredClone(p.values);
  Object.assign(dv.preset, { loaded: { id: p.id, name: p.name, values: divCanon(p.values) }, source: `preset:${p.id}`, from: `저장한 프로젝트 구성 「${p.name}」에서 불러옴`, naming: false, nameDraft: null, confirming: "" });
  divTouched(); divRender();
  await divSettingsSave(); // 작업에 바로(② §8 자동 저장)
  toast(`저장한 프로젝트 구성 「${p.name}」 을 불러왔습니다 — 확인한 뒤 「${divConfirmWhere(dv.view && dv.view.projectSharing)}에 저장」`);
}

async function divPresetSave() { // 불러온 항목을 id 로 덮어씀 — 없으면 이름 줄
  const st = dv.preset;
  if (!st.loaded) { divPresetNaming(true); return; }
  await divPresetPut(st.loaded.id, st.loaded.name);
}

async function divPresetSaveAs(raw) { // 새 항목 — 같은 이름이 있으면 그 항목을 덮어씀(이름 줄에 미리 알림)
  const name = divPresetName(raw);
  if (!name) { toast("이름을 넣으세요", true); return; }
  const same = (dv.view?.presets || []).find((p) => p.name === name);
  await divPresetPut(same ? same.id : "new", name);
}

async function divPresetPut(pid, name) {
  const epoch = state.epoch;
  try {
    const p = await api(`/api/divisions/presets/${pid}`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ name, values: divValues() }) });
    if (epoch !== state.epoch) return;
    Object.assign(dv.preset, { loaded: { id: p.id, name: p.name, values: divCanon(p.values) }, source: `preset:${p.id}`, naming: false, nameDraft: null, more: false, confirming: "" });
    toast(`「${p.name}」 저장(저장한 프로젝트 구성)`);
    divShow();
  } catch (e) { toast(`저장하지 못했습니다: ${e.message}`, true); }
}

async function divPresetDelete(pid) {
  const p = (dv.view?.presets || []).find((x) => x.id === pid);
  if (!p) { dv.preset.confirming = ""; divRender(); return; }
  const epoch = state.epoch;
  try {
    await api(`/api/divisions/presets/${pid}`, { method: "DELETE" });
    if (epoch !== state.epoch) return;
    const st = dv.preset;
    st.confirming = ""; st.more = false;
    if (st.source === `preset:${pid}`) st.source = "";
    if (st.loaded && st.loaded.id === pid) st.loaded = null; // 입력값은 그대로
    toast(`「${p.name}」 지움`);
    divShow();
  } catch (e) { toast(`지우지 못했습니다: ${e.message}`, true); }
}

// ---- 입력값 자동 저장(② §8, 2026-11-11 astra P1) — 전에는 화면이 PUT …/settings 를 부르지 않아 입력만 한 값이 다시 열면 사라졌다
let divSaveTimer = null, divSavePending = null;
function divSettingsSchedule() { clearTimeout(divSaveTimer); divSaveTimer = setTimeout(() => { divSaveTimer = null; divSettingsSave(); }, 700); }
async function divSettingsSave() { // 차례대로 하나씩 · 틀린 값(400)은 조용히 건너뜀(고치는 중) · 값이 달라졌으면 문서 표시 자료는 다시(서버 설정 값으로 찾으므로)
  clearTimeout(divSaveTimer); divSaveTimer = null;
  if (!state.id || !dv.values) return;
  const id = state.id, epoch = state.epoch, view = dv, scope = taskScopeKey(), prev = divSavePending;
  const run = (async () => {
    if (prev) { try { await prev; } catch { /* 앞 저장의 실패는 거기서 알림 */ } }
    if (epoch !== state.epoch || view !== dv || scope !== taskScopeKey()) return;
    const values = divValues(), key = divCanon(values);
    if (key === dv.savedKey) return;
    try {
      const r = await api(`/api/docs/${id}/divisions/settings`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ values }) });
      if (epoch !== state.epoch || view !== dv || scope !== taskScopeKey()) return;
      dv.savedKey = key;
      if (dv.view) Object.assign(dv.view, { settings: r.settings, dimensions: r.dimensions, plan: r.plan, stale: r.stale, projectSharing: r.projectSharing, ...("confirmed" in r ? { confirmed: r.confirmed } : {}), ...("versions" in r ? { versions: r.versions } : {}) });
      if (typeof projectSharingSync === "function") projectSharingSync(); // 구분 기준 있음/없음 줄 · 버전 줄(② §19) — 처음 저장되면 「없음」 → 「있음」
      dv.marks.data = null;
      if (divMarksOn()) { if (dv.marks.loading) dv.marks.again = true; else divMembersLoad(); }
    } catch (e) { if (epoch === state.epoch && e.status !== 400) toast(`구분 값을 작업에 저장하지 못했습니다: ${e.message}`, true); }
  })();
  divSavePending = run;
  try { await run; } finally { if (divSavePending === run) divSavePending = null; }
}
async function divSettingsFlush() { if (divSaveTimer) await divSettingsSave(); else if (divSavePending) await divSavePending; }

// ---- 실행 묶음 #divRunBar(spec_구분_기준 ② §22 — 2026-11-13 사용자 "이 메뉴를 순차적으로 누를 수 있게 붙어 있어야지 … 상단에는 모든 작업 한번에 자동으로 처리 하는 버튼을 넣어줘야지. 이 4개가 하나로 묶여 있어도되고" · astra 협의):
// 「① 변경 계획 보기 › ② 반영 · 계획 다시 열기」 + (묶음 없는 TASK 만) 「한 번에 진행」 + 상태 한 줄. **반영 단추는 여기 하나뿐** — 2열 목록의 발에는 요약 글과 「… 단추로 이동」 만(design.md §10).
// 단추 노드는 divRender 가 만들고(divRunBar), 글·켜짐·강조·상태 줄은 divRunSync 가 맞춘다 — 입력·뺄 자리·문서 차례가 바뀔 때마다 부르고 노드는 그대로다(초점 유지).
function divPlanState() { // 지금 계획의 상태 — 묶음·2열 발·실행 함수가 같이 본다. kind: none 계획 없음 | ready 반영할 수 있음 | same 바꿀 것 없음 | stale 문서가 바뀜 | skip 뺄 자리를 바꿈 | done 반영함
  const plan = dv.plan;
  if (!plan) return { kind: "none", plan: null };
  if (dv.result) return { kind: "done", plan };
  if (plan.baseRev !== state.serverRev) return { kind: "stale", plan };
  const key = (a) => JSON.stringify([...(a || [])].sort());
  if (key(dv.skip) !== key(plan.skip)) return { kind: "skip", plan };
  const s = plan.summary;
  return { kind: (s.groups != null ? s.groups || s.changes : s.applied) ? "ready" : "same", plan }; // 서버의 「할 일 없음」 과 같은 식(바뀔 묶음·글 — 후보 상태 수가 아니라)
}
const divPlanIssues = (s, all = true) => [s.errors ? `계획 오류 ${s.errors}건` : "", s.unresolved ? `미해결 ${s.unresolved}곳` : "", all && s.unsupported ? `지원 안 됨 ${s.unsupported}곳` : ""].filter(Boolean).join(" · "); // 사람이 봐야 할 것("" = 없음). all false = 「한 번에 진행」 이 멈추는 것만(계획 오류 · 미해결) — 지원 안 되는 자리는 미리 아는 자리라 그대로 두고 간다(빈 양식에도 있다)
function divSameText(s) { // 바꿀 것이 없는 계획의 글 → {ok, text} — 「이미 맞음」 과 「못 맞춤」 을 같은 글로 보이지 않는다
  const stops = divPlanIssues(s, false), rest = s.unsupported ? ` · 지원 안 됨 ${s.unsupported}곳은 그대로` : "";
  if (stops) return { ok: false, text: `바꿀 수 있는 자리가 없습니다 · ${stops}${rest}` };
  if (s.already) return { ok: true, text: `현재 구성과 맞습니다 — 바꿀 자리가 없습니다${rest}` };
  return { ok: false, text: s.unsupported ? `맞출 수 있는 자리가 없습니다 · 지원 안 됨 ${s.unsupported}곳` : "맞출 자리를 찾지 못했습니다" };
}
function divRunWhy() { // 계획·반영을 할 수 없는 까닭("" = 할 수 있음) — 단추와 「한 번에 진행」 이 같이 본다
  const v = dv.values, view = dv.view;
  if (!v || !view) return "프로젝트 구성을 읽는 중입니다";
  if (!view.profile.supported) return "이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다";
  if (divTotalYears(v) > 20) return "전체 차년도는 20년 이하여야 합니다";
  if (taskFrameApply && !divConfirmValid(v, view.confirmed)) return `${taskSlots() ? "「프로젝트 구성 추출」 이" : "1단계 「프로젝트 구성」 이"} 먼저입니다 —${divConfirmWhere(view.projectSharing)}에 저장(확정)한 뒤 변경 계획을 봅니다`; // TASK 묶음 안(spec_작업 ② §18)
  return "";
}
const divRunLocked = () => !!dv.auto || !!taskRun || !!taskResetting || (typeof gatherRun !== "undefined" && !!gatherRun) || (typeof gqRun !== "undefined" && !!gqRun && gqRun.busy); // 다른 실행이 도는 동안(이 묶음의 한 번에 진행 · TASK 묶음의 한 번에 진행 · 초기화 · 취합 간단 모드 — 묶음 사이의 틈도) — 단추만 끈다(그 실행이 부르는 divPlan·divApply 는 그대로 돈다)
// 「한 번에 진행」 류가 지금 계획을 사람 확인 없이 반영해도 되는가 → 멈출 까닭 글 | ""(spec_작업에이전트 ② §7 — astra 11-16: 같은 「구조 반영」 인데 TASK 마다 검사가 달랐다).
// 양식 맞추기(divRunAll) · 이관 2단계(taskRunSteps) · 취합 2단계(gather.js gatherRunFrame)가 같이 본다: 계획 오류 · 미해결 자리 · 기관의 차례가 마지막 반영과 다름. 지원 안 되는 자리는 그대로 두고 간다(빈 양식에도 있다 — divPlanIssues)
// 판정은 서버 한 곳(app/division_plan.py auto_stops — spec_워크플로우 ② §17-7 「같은 검사」: 서버 쪽 실행기도 그것으로 멈춘다)이 계획의 응답에 싣는 값(autoStops · autoStopsKind)을 읽는다 — 옛 서버(그 키 없음)일 때만 아래 식으로 센다
const divAutoStopsOf = (plan) => (plan && typeof plan.autoStops === "string" ? { text: plan.autoStops, kind: plan.autoStopsKind || (plan.autoStops ? "issues" : "") } : null);
function divAutoStops() {
  const st = divPlanState(), s = st.plan && st.plan.summary;
  if (!s || st.kind !== "ready") return "";
  const srv = divAutoStopsOf(st.plan);
  return srv ? srv.text : divPlanIssues(s, false) || divOrgsMoved();
}
function divOrgsMoved() { // 마지막 반영 때 이름이 있던 기관의 차례가 달라졌는가 → 까닭 글 | "". 엔진은 남는 항목에 자리 차례대로 이름을 쓴다(② §5·§19) — 차례가 바뀌거나 가운데가 빠지면 쓴 내용이 다른 이름 아래에 남을 수 있다
  // 견줄 반영 = 마지막 전체 반영 + 그 뒤의 「한 자리만 반영」(표 메뉴 「프로젝트 구성에 맞추기」 — spec_테이블매니저 ② §9 「한 자리만 반영한 기록」: 전체 반영이 없던 문서에서 한 표만 맞춘 뒤 차례를 바꿔도 그 표의 값은 다른 이름 아래에 남는다)
  const st = divPlanState(), srv = st.kind === "ready" ? divAutoStopsOf(st.plan) : null; // 반영할 수 있는 지금 계획이 있으면 서버가 그 계획의 값으로 센 것(같은 검사)
  if (srv) return srv.kind === "orgs" ? srv.text : "";
  const a = dv.view && dv.view.applied, parts = (dv.view && dv.view.partial) || [];
  const names = (v) => [v.orgs.lead || "", ...(v.orgs.joint || [])].map((n) => String(n).trim()), now = names(divValues()), role = (i) => (i ? `공동 ${i}` : "주관");
  for (const [v, what] of [[a && a.values, "마지막 반영"], ...parts.map((p) => [p.values, "표 하나만 맞춘 반영"])]) {
    if (!v || !v.orgs) continue;
    const was = names(v);
    for (let i = 0; i < was.length; i++) {
      if (now[i] === was[i]) continue; // 같은 자리에 같은 이름 — 같은 이름이 둘 있어도 첫 자리로 견주지 않는다(서버 division_plan.orgs_moved 와 같다)
      const j = was[i] ? now.indexOf(was[i]) : -1;
      if (j >= 0 && j !== i) return `기관 「${was[i]}」 의 차례가 ${what}과 다릅니다(${role(i)} → ${role(j)})`;
    }
  }
  return "";
}

function divRunBar(staged) { // 묶음 상자 — staged = TASK 묶음 안(이관·취합의 2단계 #taskFrameApply): 「한 번에 진행」 은 그 묶음 머리에 있어 여기 안 두고, 번호(①②)도 안 붙인다(TASK 의 단계 번호와 겹침)
  const bar = el("section", "dv-run"), head = el("div", "dv-run-head"), steps = el("div", "dv-run-steps"), st = el("p", "dv-run-state"), spin = el("i", "dv-phase-spin"), text = el("span"), totals = el("span", "dv-run-values");
  bar.id = "divRunBar";
  bar.dataset.staged = staged ? "1" : "0";
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", "프로젝트 구성 반영");
  totals.id = "divReviewSummary"; // 지금 입력 값 요약(「1단계 · 전체 4년 · 기관 4곳」 — divRefreshDerived)
  const press = (run) => () => { if (dv.busy || divRunLocked()) return; dv.keepFocus = true; run(); };
  const btn = (id, label, run, cls = "btn") => { const b = hBtn(label, run, { cls }); b.id = id; b.setAttribute("aria-describedby", "divRunState"); return b; };
  const help = hHelp("프로젝트 구성 반영 안내", `${staged ? "" : "① "}변경 계획 보기 — 바뀔 자리와 지워질 글을 문서 옆 목록으로 봅니다(문서는 안 바뀜).\n${staged ? "" : "② "}반영 — 그 계획대로 이 문서의 구조(절·표 행·열)를 바꿉니다. 실행 취소 한 번으로 되돌립니다.\n계획 다시 열기 — 닫은 목록을 다시 엽니다(다시 계산하지 않음).`
    + (staged ? "" : "\n한 번에 진행 — 계획을 세우고 바로 반영합니다. 미해결 자리나 계획 오류가 있으면 반영하지 않고 멈춥니다(지원 안 되는 자리는 그대로 둡니다)."
      + (typeof taskIsSingle === "function" && taskIsSingle((state.task || {}).job) ? "" : " 끝나면 고친 문단을 확정합니다(앞 상태는 「고친 문단」 탭 확정 기록의 복원).") // 끝 확정(spec_워크플로우 ② §18-24) — 문서 하나로 조립한 것은 서버의 줄 하나(반영)라 확정하지 않는다
      + "\n불러오기 — 고른 곳(이 프로젝트 · 문서 · 다른 프로젝트 · 저장한 프로젝트 구성)의 값으로 입력 칸을 채웁니다(문서는 안 바뀜).\n세부 — ①·② 단추와 프로젝트 구성 값(단계·차년도 · 기관) 입력 · 「프로젝트에 저장」 은 접어 둔 「세부」 안에 있습니다."), { note: true });
  if (staged) head.append(totals, help);
  else head.append(el("strong", null, "프로젝트 구성 반영"), help, btn("divRunAll", "한 번에 진행", press(() => divRunAll())), totals);
  const arrow = el("span", "dv-run-arrow", "›");
  arrow.setAttribute("aria-hidden", "true");
  steps.append(btn("divPlanButton", `${staged ? "" : "① "}변경 계획 보기`, press(() => divPlan()), "btn dv-plan-button"), arrow, btn("divApplyButton", `${staged ? "" : "② "}반영`, press(() => divApply())),
    btn("divReopenPlan", "계획 다시 열기", () => divList(), "btn dv-run-reopen"));
  spin.hidden = true;
  spin.style.animationDelay = `-${Date.now() % 800}ms`; // 다시 그려도 동그라미가 처음부터 다시 돌지 않게(design.md §7)
  text.setAttribute("role", "status"); // 바뀌는 상태 글만 알린다(단추·동그라미는 밖)
  st.id = "divRunState";
  st.append(spin, text);
  bar.append(head, steps, st);
  return bar;
}

// 묶음 없는 TASK(양식 맞추기 …)의 카드 하나(spec_구분_기준 ② §22 「카드 하나」 — 2026-11-14 사용자 "이거 합치고 현재 프로젝트 구성 반영 위치에 합쳐서 같이 있어야지 … 한번에 진행, 불러오기 2개 메뉴가 있고, 다른 것은 접혀있어야 하고"):
// 늘 보이는 것 = 윗줄 「한 번에 진행」 · 「프로젝트 구성 불러오기」 줄 · 상태 한 줄. 나머지(① 변경 계획 보기 › ② 반영 · 계획 다시 열기 / 확정 상태 · 「프로젝트에 저장」 · ⋯ / 단계·차년도 · 기관 구성 · 추가 설정)는
// 접어 둔 「세부」(details#divRunMore — 기본 접힘 · 펴짐은 브라우저에 기억) 안. 노드의 id·클래스는 그대로다(자리만 옮김) — 다른 코드·검사가 id 로 찾는다.
const DIV_RUN_MORE = "nfm.divRunMore";
const divRunMoreOpen = () => { try { return localStorage.getItem(DIV_RUN_MORE) === "1"; } catch { return false; } };
function divRunFold(bar, config) {
  const more = el("details", "dv-run-more"), sum = el("summary"), body = el("div", "dv-phase-form dv-run-more-body"), load = config.querySelector(".dv-presets > .dv-preset-row");
  more.id = "divRunMore";
  let known = more.open = divRunMoreOpen() || !!dv.ui.runMore; // 기억해 둔 펴짐, 또는 이 문서에서 프로그램이 편 것(멈춤 · 「… 단추로 이동」 — divRunReveal)
  more.ontoggle = () => {
    if (!more.isConnected) return;
    if (more.dataset.auto) { delete more.dataset.auto; known = more.open; } // 프로그램이 폄 — 브라우저에 기억하지 않는다
    else if (more.open !== known) { known = dv.ui.runMore = more.open; try { localStorage.setItem(DIV_RUN_MORE, more.open ? "1" : "0"); } catch { /* 기억만 안 함 */ } } // 사람이 접거나 폄
    divRunSync(); // 강조 단추가 옮겨 간다(접힘 = 「한 번에 진행」 · 펴짐 = 다음 할 일)
  };
  sum.title = "세부 펴기·접기 — 변경 계획을 먼저 보고 반영하거나, 프로젝트 구성 값을 고치고 저장합니다";
  sum.append(el("strong", null, "세부"), el("span", "dv-caption", "단계별 반영 · 값 고치기 · 저장"));
  body.append(bar.querySelector(".dv-run-steps"), config); // 차례 줄(① › ② · 다시 열기) 다음에 구성 입력(확정·저장 · 단계·차년도 · 기관 · 추가 설정)
  more.append(sum, body);
  if (load) { // 「프로젝트 구성 불러오기」 줄(고르기 목록 + 「불러오기」)만 밖으로 — fieldset(도는 동안 꺼짐) 밖이라 여기서 끈다
    load.classList.add("dv-run-load");
    if (dv.busy) for (const c of load.querySelectorAll("select, button")) c.disabled = true;
    bar.querySelector(".dv-run-state").before(load);
  }
  bar.append(more);
}
function divRunReveal() { // 접어 둔 「세부」 를 편다 — 그 안의 단추·입력으로 보낼 때(멈춤 · 「… 단추로 이동」 · 「새로 만들기」). 이 문서를 보는 동안만(다시 그려도 펴짐 — dv.ui.runMore), 브라우저에는 기억하지 않는다
  dv.ui.runMore = true;
  const more = $("divRunMore");
  if (more && !more.open) { more.dataset.auto = "1"; more.open = true; }
}

function divRunSync() { // 묶음의 단추(켜짐 · 강조 · 도움말)와 상태 줄 — 노드는 그대로 두고 글·속성만
  const bar = $("divRunBar");
  if (!bar || !dv.view || !dv.values) return;
  const staged = bar.dataset.staged === "1", st = divPlanState(), s = st.plan && st.plan.summary, why = divRunWhy(), locked = divRunLocked(), off = dv.busy || locked, wait = "지금 진행 중인 작업이 끝나면 쓸 수 있습니다";
  const plan = $("divPlanButton"), apply = $("divApplyButton"), reopen = $("divReopenPlan"), all = $("divRunAll");
  const noApply = why || { none: "먼저 변경 계획을 확인하세요", stale: "문서가 바뀌었습니다 — 다시 계획하세요", skip: "뺄 자리를 바꿨습니다 — 다시 계획하세요", same: "바꿀 자리가 없습니다", done: "이미 반영했습니다 — 값을 바꾸면 다시 계획합니다" }[st.kind] || "";
  plan.disabled = off || !!why;
  plan.title = off ? wait : why || "바뀔 자리와 지워질 글을 문서 옆 목록으로 미리 봅니다 — 문서는 바뀌지 않습니다";
  apply.disabled = off || !!noApply;
  apply.title = off ? wait : noApply || "계획대로 문서를 고칩니다 — 한 번에, 표준 검사에 걸리면 전부 되돌림. 반영 뒤 「실행 취소」 로 되돌릴 수 있음";
  reopen.disabled = dv.busy || !dv.plan; // 열어 보기만 — 다른 실행이 도는 동안에도
  reopen.textContent = st.kind === "done" ? "반영 결과 열기" : "계획 다시 열기";
  reopen.title = dv.plan ? "닫은 목록을 문서 옆에 다시 엽니다 — 다시 계산하지 않습니다" : "이 화면에 열 수 있는 계획이 없습니다 — 「변경 계획 보기」 를 누르세요";
  if (all) {
    all.disabled = off || !!why;
    all.title = off ? wait : why || "변경 계획을 세우고 바로 반영합니다 — 사람이 봐야 할 자리가 있으면 반영하지 않고 멈춥니다";
  }
  // 강조 단추는 하나 — 다음 할 일(계획이 준비됐으면 반영, 아니면 계획). TASK 묶음 안에서는 강조하지 않는다(강조는 그 묶음의 「다음 할 일」 · 「한 번에 진행」 — design.md §11).
  // 묶음 없는 TASK 의 「세부」 가 접혀 있으면 차례 단추가 안 보이므로 강조는 「한 번에 진행」(§11 「접혀 있으면 묶음의 단추, 펴면 세부 목록의 다음 할 일」)
  const more = $("divRunMore"), folded = !!more && !more.open;
  plan.classList.toggle("primary", !staged && !folded && st.kind !== "ready" && st.kind !== "done");
  apply.classList.toggle("primary", !staged && !folded && st.kind === "ready");
  if (all) all.classList.toggle("primary", folded && st.kind !== "done");
  const issues = s ? divPlanIssues(s) : "";
  let kind = "next", text;
  if (dv.busy) { kind = "run"; text = state.busy ? "문서에 반영 중…" : "변경 계획 계산 중…"; }
  else if (why) text = why;
  else if (st.kind === "stale") text = "문서가 바뀌었습니다 · 다시 계획하세요";
  else if (st.kind === "skip") text = "뺄 자리가 바뀌었습니다 · 다시 계획하세요";
  else if (dv.msg) { kind = dv.msg.kind === "note" ? "next" : dv.msg.kind; text = dv.msg.text; }
  else if (st.kind === "none") text = folded ? "「한 번에 진행」 — 변경 계획을 세우고 바로 반영합니다 · 바뀔 자리를 먼저 보려면 「세부」" : "먼저 변경 계획을 확인하세요";
  else if (st.kind === "ready") text = `계획 준비됨 · 맞출 자리 ${s.applied}곳 · 지워지는 글 문단 ${s.deleted}${issues ? ` · ${issues}` : ""}`;
  else if (st.kind === "same") text = divSameText(s).text;
  else { kind = "done"; text = `반영 완료 · 편집 차례 ${dv.result.rev}${dv.result.unresolved.length ? ` · 미해결 ${dv.result.unresolved.length}곳은 손으로 맞추세요` : ""}${s.unsupported ? ` · 지원 안 됨 ${s.unsupported}곳은 그대로` : ""}`; }
  const line = $("divRunState");
  line.dataset.kind = kind;
  line.firstChild.hidden = kind !== "run";
  if (line.lastChild.textContent !== text) line.lastChild.textContent = text;
}

async function divRunFocus() { // 2열 발의 「… 단추로 이동」 — 패널의 실행 묶음을 보이고(접힌 TASK 묶음은 펴서) 다음 단추에 초점. 문서는 안 바뀐다
  if ($("panel").dataset.tool !== "Div") { showTab("Div"); await divShow(); }
  const bar = $("divRunBar");
  if (!bar) return;
  const fold = bar.closest("details");
  if (fold) fold.open = true;
  divRunReveal(); // 묶음 없는 TASK — 차례 단추는 접어 둔 「세부」 안
  bar.scrollIntoView({ block: "center" });
  (bar.querySelector("#divApplyButton:not(:disabled)") || bar.querySelector("#divPlanButton:not(:disabled)") || bar.querySelector("button:not(:disabled)"))?.focus({ preventScroll: true });
  bar.classList.remove("dv-run-flash");
  void bar.offsetWidth; // 같은 묶음을 다시 가리켜도 깜빡임이 처음부터
  bar.classList.add("dv-run-flash");
}

// 「한 번에 진행」(묶음 없는 TASK — 양식 맞추기): 변경 계획 → 반영. 확인 창 없이(2026-11-18 — design.md §18 「확인 창」 · 이관 묶음과 같게) —
// 대신 사람이 봐야 할 계획(미해결 · 계획 오류 · 기관 차례가 마지막 반영과 다름)이면 반영하지 않고 목록을 연 채 멈춘다(astra P1 — 수만 보인 확인 창은 검토가 아니다).
// opt.asked = 옛 인자 — 2026-11-18 사용자 「이런 알람좀 주지마」 부터 확인 창이 없어 쓰지 않는다(부르는 쪽 호환으로 받기만 함 · LLM 연결 · 멈추는 검사는 그대로)
async function divRunAll(opt = {}) {
  if (!state.id || dv.busy || divRunLocked()) return;
  // 문서 하나로 조립한 워크플로우(task_catalog.js taskIsSingle — 붙박이 양식 표준화 · 양식 맞추기는 아니다)는 화면이 돌리지 않는다 — 그 정의의 구조 반영 줄을 서버 쪽 실행기로(workflow_exec.js singleRunAll: spec_워크플로우 ② §18-12 ⑤)
  if (typeof taskIsSingle === "function" && taskIsSingle((state.task || {}).job) && typeof singleRunAll === "function") return singleRunAll();
  const why = divRunWhy();
  if (why) { toast(why, true); return; }
  const id = state.id, epoch = state.epoch, view = dv, st0 = divPlanState(), s0 = st0.kind === "ready" && st0.plan.only == null ? st0.plan.summary : null; // 한 자리만의 계획(표 메뉴 「프로젝트 구성에 맞추기…」 — divPlan 의 opt.only)은 이어 쓰지 않는다 — 문서 전체로 다시 계획한다
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 값 · 계획 수를 적은 확인 창: design.md §18 「확인 창」) — 멈추는 검사(미해결 · 계획 오류 · 기관 차례)는 아래 그대로
  const mine =() => epoch === state.epoch && id === state.id && view === dv;
  const halt = (text) => { view.msg = { kind: "halt", text: `멈춤 — ${text}` }; toast(`한 번에 진행이 멈췄습니다 — ${text}`, true); if (mine()) divRunReveal(); }; // 멈추면 「세부」 를 펴서 다음 단추(② 반영 · 다시 계획)를 보인다(design.md §11)
  view.auto = true;
  view.keepFocus = true;
  divRunSync();
  let ended = false; // 끝남(반영함 · 「이미 맞음」) — 끝에 고친 문단을 확정한다(opt.commit 이 false 가 아니면 — 「이어서 한 번에」 는 끄고 끝에 한 번: spec_워크플로우 ② §18-24) · 멈춤이면 안 한다(계획이 남는다 — 확정은 그 계획을 비운다)
  try {
    if (!s0 && !(await divPlan())) { if (mine() && !view.msg) halt("변경 계획을 세우지 못했습니다(알림 글 참고)"); return; }
    if (!mine()) return;
    const st = divPlanState(), s = st.plan && st.plan.summary;
    if (st.kind === "same") { // 바꿀 것이 없다 — 「이미 맞음」 과 「못 맞춤」 을 가른다
      const same = divSameText(s);
      if (same.ok) { view.msg = { kind: "done", text: same.text }; toast(same.text); ended = true; } else halt(same.text);
      return;
    }
    if (st.kind !== "ready") { halt(st.kind === "skip" ? "뺄 자리가 바뀌었습니다 · 다시 계획하세요" : "계획을 세우는 사이 문서가 바뀌었습니다 · 다시 계획하세요"); return; }
    const stops = divAutoStops(), moved = stops && stops === divOrgsMoved(); // 같은 검사(서버가 계획에 실은 값 — divAutoStops) · moved = 그 까닭이 기관의 차례
    if (stops && !moved) { halt(`${stops} — 목록에서 확인한 뒤 「② 반영」 을 누르세요`); return; }
    if (moved) { halt(`${stops} — 쓴 내용이 다른 기관 이름 아래에 남을 수 있습니다. 목록에서 확인한 뒤 「② 반영」 을 누르세요`); return; }
    if (await divApply({ quiet: true })) ended = true;
    else if (mine() && !view.msg) halt("반영하지 못했습니다(알림 글 참고)");
  } finally {
    if (ended && opt.commit !== false && mine()) { // 끝 확정 — 「고친 문단」 탭의 확정과 같은 함수(commitAfterRun → commitDo).
      // 확정이 끝날 때까지 「한 번에 진행」 은 도는 중(view.auto 그대로 — 단추 · 에이전트의 진행 카드가 그 사이 새 실행을 받아 확정과 겹치지 않게: 2026-11-22 검토)
      const was = view.msg;
      divRunSync();
      const line = $("divRunState"), shown = line && line.lastChild ? line.lastChild.textContent : ""; // 확정 전의 상태 줄(「반영 완료 · 편집 차례 n …」) — 확정이 반영 결과(dv.result)를 비우면 다시 셀 수 없다
      view.msg = { kind: "run", text: "고친 문단 확정 중…" };
      divRunSync();
      let tail = "";
      try { tail = await commitAfterRun("「프로젝트 구성 반영」 한 번에 진행"); } catch (e) { console.warn(e); } finally { if (view.msg && view.msg.kind === "run") view.msg = was; }
      if (tail) view.msg = { kind: (was && was.kind) || "done", text: `${(was && was.text) || shown || "반영했습니다"} · ${tail}` };
    }
    view.auto = false;
    if (mine()) { divRunSync(); divFootSync(); }
  }
}

// opt(안 주면 전과 같다 — 문서 전체 계획): only = 묶음 key — 그 자리와 그 안쪽 자리만의 계획(서버 끝점의 `only` — spec_구분_기준 ② §7) · table = {id, ids(그 표와 그 안의 표 · 칸 id Set)} — 목록을 그 표의 자리로 좁혀 연다(divList).
// 표 메뉴 「프로젝트 구성에 맞추기…」(table_menu.js tmnDivision — spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」)만 넘긴다. 계획 → 확인 → 반영의 길 · 멈추는 조건은 그대로다(새 길이 아니라 입구)
async function divPlan(opt = {}) { // → true(계획을 세워 2열에 엶) | false(못 세움 — 전의 계획이 남아 있을 수 있다: 부른 쪽은 dv.plan 이 아니라 이 값을 본다)
  if (!state.id || dv.busy) return false;
  const id = state.id, epoch = state.epoch, view = dv;
  await flushAll(); // 아직 반영 안 된 글부터 — 계획은 서버 문서 차례(rev)에 묶인다
  if (epoch !== state.epoch) return false;
  if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 계획을 세우지 않았습니다 — 「고친 문단」 탭에서 먼저 다시 반영하세요", true); return false; } // flushAll 은 실패를 삼킨다 — 옛 글로 계획·반영하면 화면에만 있는 글을 잃는다(astra P1 · structOp 과 같은 검사)
  await divSettingsFlush(); // 입력값도 작업에(② §8 자동 저장)
  if (epoch !== state.epoch) return false;
  dv.busy = true;
  dv.msg = null;
  divRender();
  let ok = false;
  try {
    const r = await api(`/api/docs/${id}/divisions/plan`, { method: "POST", headers: H_JSON, body: JSON.stringify({ values: divValues(), skip: [...dv.skip], ...(opt.only ? { only: opt.only } : {}) }) });
    if (epoch !== state.epoch) return false;
    if (opt.table) r.table = opt.table; // 화면만의 표시(서버의 계획에는 없다) — 목록이 그 표의 자리만 보인다
    dv.plan = r;
    dv.dirty = false;
    dv.result = null;
    dv.busy = false; // 실행 묶음의 「반영」 단추가 바로 켜지게(finally 보다 먼저)
    const s = r.summary;
    toast(`계획 — 맞출 자리 ${s.applied} · 이미 맞음 ${s.already} · 지원 안 됨 ${s.unsupported} · 미해결 ${s.unresolved} (${s.seconds}s)`, s.unresolved > 0);
    divList();
    ok = true;
  } catch (e) {
    if (epoch !== state.epoch) return false;
    dv.msg = { kind: "halt", text: `계획을 세우지 못했습니다 — ${e.message}` };
    toast(`계획을 세우지 못했습니다: ${e.message}`, true);
  } finally {
    view.busy = false; // 이 요청이 켠 것만 끈다(그 사이 다른 문서를 열었으면 dv 는 새 것)
    if (epoch === state.epoch) divShow();
  }
  return ok;
}

function divGo(c, focus = true) { // 후보 자리의 첫 라벨(문단 또는 칸)로 — 칸이면 그 칸의 첫 문단. focus false = 문서로 가서 보이기만(키보드 초점은 부른 목록에 — ↑/↓ 로 이어 고르기)
  const id = c.key === "period" ? null : c.key;
  if (!id) return;
  if (paraEl(id)) { scrollToBlock(id, focus); return; }
  // 표 칸은 td[data-cell](renderTable) — 쪽에 걸쳐 나뉜 칸(행 안 나눔)은 조각이 여럿이고 앞 조각이 비었을 수 있어 문단이 든 첫 조각을 본다
  let p = null;
  for (const cell of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(id)}"], #doc [data-id="${CSS.escape(id)}"]`)) if ((p = cell.querySelector(".para"))) break;
  if (p) { scrollToBlock(p.dataset.id, focus); return; }
  const tb = document.querySelector(`#doc table[data-tbl="${CSS.escape(id)}"]`); // 표 id(넣기 계획의 표 줄 · 일정 표 줄 · 매칭 지침의 표 자리) — 표는 data-tbl 로 그려진다(renderTable): 그 표의 첫 문단으로, 문단이 없으면 표로
  if (tb) { const q = tb.querySelector(".para"); if (q) scrollToBlock(q.dataset.id, focus); else tb.scrollIntoView({ block: "center" }); return; }
  toast("그 자리가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)");
}

let divListPlan = null; // 2열 목록이 지금 그려 둔 계획 — 발을 다시 그릴 때(divFootSync) 그 계획이 아직 지금 계획인지 본다
function divFootSync() { if (heads.dlg === "divisions" && divListPlan) divFoot($("headsDlgFoot"), divListPlan); } // 열려 있는 목록의 발을 지금 상태로(입력·문서 차례·반영 결과가 바뀐 뒤)

function divList() {
  const plan = dv.plan;
  if (!plan) { toast("먼저 「변경 계획 보기」를 누르세요"); return; }
  divListPlan = plan;
  const res = dv.result;
  // 표 메뉴 「프로젝트 구성에 맞추기…」 로 세운 계획(divPlan 의 opt.table — spec_테이블매니저 ② §9 「표 하나만 프로젝트 구성에 맞추기」)은 그 표(와 그 안의 표 · 칸)의 자리만 보인다 — 도구 줄의 단추로 모든 자리와 오간다(계획은 그대로)
  const narrow = plan.table && !plan.tableAll ? plan.table : null;
  const { tools, body, foot } = headsDlg("divisions", res ? "프로젝트 구성 — 반영 결과" : "프로젝트 구성 — 바꿀 자리",
    `${res ? `편집 차례 ${res.rev} 에 반영` : `편집 차례 ${plan.baseRev} 기준 계획`}${plan.only ? " · 고른 자리와 그 안쪽 자리만의 계획" : ""} · 누르면 문서의 그 자리로`);
  const statusOf = (c) => (res && res.status[c.key]) || c.status;
  const filt = el("span", "dv-filter");
  for (const [k, label] of [["all", "모두"], ["work", "바꿀 자리"], ["issue", "지원 안 됨·미해결"], ["already", "이미 맞음"]]) {
    filt.append(hBtn(label, () => { dv.filter = k; divList(); }, { cls: "btn sm" + (dv.filter === k ? " on" : "") }));
  }
  tools.append(filt);
  if (plan.table) {
    const only = hBtn(`표 ${plan.table.id} 의 자리만`, () => { plan.tableAll = !plan.tableAll; divList(); },
      { cls: "btn sm" + (narrow ? " on" : ""), title: "표 메뉴 「프로젝트 구성에 맞추기…」 로 연 계획입니다 — 누르면 이 표의 자리만 보기 ↔ 문서의 모든 자리 보기(계획은 그대로)" });
    only.id = "divListTable";
    only.setAttribute("aria-pressed", String(!!narrow));
    tools.append(only);
  }
  const cbL = el("label", "hd-field"); const cb = el("input"); cb.type = "checkbox"; cb.checked = dv.showDrop; cb.onchange = () => { dv.showDrop = cb.checked; divList(); };
  cbL.append(cb, "지워질 글 보기"); tools.append(cbL);
  tools.append(divSummary(plan.summary));
  const [tbl, tb] = hTable(["", "상태", "구분", "종류", "라벨(처음 3)", "수→목표", "자리"]);
  const rows = plan.candidates.filter((c) => {
    if (narrow && !(c.where && (narrow.ids.has(c.where.table) || narrow.ids.has(c.where.cell)))) return false;
    const st = statusOf(c);
    return dv.filter === "all" || (dv.filter === "work" && (st === "applied" || st === "excluded")) || (dv.filter === "issue" && (st === "unsupported" || st === "unresolved")) || (dv.filter === "already" && st === "already");
  });
  for (const c of rows) {
    const st = statusOf(c), tr = el("tr", "go" + (st === "excluded" ? " dv-excluded" : ""));
    tr.tabIndex = 0;
    const tdc = el("td");
    if (!res && c.key !== "period") {
      const x = el("input"); x.type = "checkbox"; x.checked = dv.skip.has(c.key); x.title = "이 자리는 반영에서 빼기(다시 계획해야 반영됨)";
      x.setAttribute("aria-label", "반영에서 빼기");
      x.onclick = (ev) => { ev.stopPropagation(); if (x.checked) dv.skip.add(c.key); else dv.skip.delete(c.key); divFoot(foot, plan); };
      tdc.append(x);
    }
    tr.append(tdc);
    const tds = el("td"); tds.append(el("span", `dv-badge ${st}`, DV_STATUS[st] || st));
    if (c.hinted) tds.append(" ", el("span", "dv-badge hinted", "추가")); // 추가한 자리의 꼴로 잡은 묶음(② §11)
    if ((res ? (res.message[c.key] || "") : c.statusMessage) && st !== "applied") tds.title = res ? res.message[c.key] : c.statusMessage;
    tr.append(tds);
    hCell(tr, c.dimName || c.dim);
    hCell(tr, c.kindName || c.kind);
    const tdl = el("td", "dv-labels");
    tdl.append((c.labels || []).slice(0, 3).join(" · ") + ((c.labels || []).length > 3 ? ` … (${c.labels.length})` : ""));
    if (st === "unsupported" || st === "unresolved") tdl.append(el("div", "muted", c.statusMessage || ""));
    if (dv.showDrop && c.drop && c.drop.length && st !== "already") {
      const ul = el("ul", "dv-drop");
      for (const d of c.drop) {
        const li = el("li"); li.append(el("span", null, `지움 「${d.text}」`), d.texts && d.texts.length > 1 ? ` — ${d.texts.slice(1).join(" / ")}` : "");
        ul.append(li);
      }
      tdl.append(ul);
    }
    if (c.copies) tdl.append(el("div", "muted", `사본 ${c.copies}개(본뜬 항목의 글을 그대로 가져옴 — 반영 뒤 고쳐 쓰세요)`));
    tr.append(tdl);
    hCell(tr, c.target == null ? `${c.count}→?` : `${c.count}→${c.target}`, "dv-num");
    hCell(tr, c.where && c.where.table ? "표 안" : "본문", null, c.where && c.where.table ? `표 ${c.where.table}` : "");
    tr.onclick = () => { for (const x of tb.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); divGo(c, false); tr.focus({ preventScroll: true }); }; // 초점은 목록에 — ↑/↓ 로 다음 자리(hRowKeys)
    tr.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); } };
    tb.append(tr);
  }
  if (!rows.length) { const tr = el("tr"); hCell(tr, "해당하는 자리가 없습니다"); tb.append(tr); }
  hRowKeys(tb); // 2026-11-12 사용자 "이거 키보드 방향키 하면 위아래로 움직이게 해줘"
  body.append(tbl);
  if (plan.deleted && plan.deleted.length && !res) {
    const det = el("details", "dv-detail"); det.style.margin = "8px 14px 14px";
    det.append(el("summary", null, `지워질 글 문단 ${plan.summary.deleted}개 전체 보기${plan.deleted.length < plan.summary.deleted ? ` (처음 ${plan.deleted.length}개)` : ""}`));
    const ul = el("ul", "dv-drop");
    for (const d of plan.deleted) { const li = el("li"); li.textContent = d.text; li.title = d.id; ul.append(li); }
    det.append(ul);
    body.append(det);
  }
  divFoot(foot, plan);
}

function divFoot(foot, plan) { // 2열 발 — 그 계획의 요약 글 + 「… 단추로 이동」 + 「닫기」. 반영·다시 계획·실행 취소는 패널의 실행 묶음과 그 아래 「문서 반영 상태」 에서만(같은 조작을 두 곳에 두지 않는다 — design.md §10 · ② §22)
  foot.textContent = "";
  const st = divPlanState(), s = plan.summary, issues = divPlanIssues(s), res = dv.result;
  let cls = "muted", text, go = "변경 계획 단추로 이동";
  if (dv.plan !== plan) { cls = "hd-msg note"; text = "이 목록의 계획은 더 반영할 수 없습니다(입력값이 바뀌었거나 계획을 버림) — 「변경 계획 보기」 로 다시 확인하세요"; }
  else if (st.kind === "done") { text = `반영 끝 — 편집 차례 ${res.rev}. 사본은 본뜬 항목의 글을 그대로 가져왔으니 고쳐 쓰세요. 되돌리려면 「문서 반영 상태」 의 실행 취소.`; go = ""; }
  else if (st.kind === "stale") { cls = "hd-msg"; text = "문서가 바뀌어 이 계획은 반영할 수 없습니다 — 「변경 계획 보기」 로 다시 계획하세요"; }
  else if (st.kind === "skip") { cls = "hd-msg note"; text = "뺄 자리를 바꿨습니다 — 「변경 계획 보기」 로 다시 계획해야 반영됩니다"; }
  else if (st.kind === "same") { text = divSameText(s).text; go = ""; }
  else { text = `맞출 자리 ${s.applied}곳 · 추가 ${s.added} · 지움 ${s.removed} · 지워지는 글 문단 ${s.deleted}${issues ? ` · ${issues}` : ""}`; go = "반영 단추로 이동"; }
  foot.append(el("span", cls, text));
  if (st.kind === "done" && dv.plan === plan && res.unresolved && res.unresolved.length) foot.append(el("span", "hd-msg", `미해결 ${res.unresolved.length}곳 — 손으로 맞추세요`));
  if (go) {
    const b = hBtn(go, () => divRunFocus(), { title: "패널의 「프로젝트 구성 반영」 묶음으로 갑니다(접힌 묶음은 폅니다) — 반영·다시 계획은 그 묶음의 단추로 합니다. 이 단추는 문서를 바꾸지 않습니다" });
    b.dataset.divGo = "1";
    foot.append(b);
  }
  foot.append(hBtn("닫기", () => headsColClose()));
  divRunSync(); // 뺄 자리를 바꾸면 묶음의 「반영」 도 함께 꺼진다
}

async function divApply({ quiet = false } = {}) { // quiet = 옛 인자(2026-11-18 부터 확인 창이 없다). → true(문서에 반영함) | false
  const plan = dv.plan;
  if (!plan || dv.busy || !state.id) return false;
  const s = plan.summary, at = divPlanState();
  if (at.kind === "done") return false;
  if (at.kind === "skip") { toast("뺄 자리를 바꿨습니다 — 다시 계획해야 반영됩니다", true); return false; } // 단추가 꺼져 있어도 함수에서 다시 본다(계획을 세우는 사이 체크를 바꾼 경우 — astra)
  // 확인 창 없이 바로 반영한다(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 맞출 자리 · 지워지는 글 문단 수를 적은 확인 창: design.md §18 「확인 창」 · 실행 취소 한 번 · 표준 검사에 걸리면 전부 되돌림)
  const id = state.id, epoch = state.epoch, view = dv;
  await flushAll();
  if (epoch !== state.epoch) return false;
  if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 반영하지 않았습니다 — 「고친 문단」 탭에서 먼저 다시 반영하세요", true); return false; } // 반영 뒤 문서를 다시 읽으면 화면에만 있는 글을 잃는다(astra P1)
  if (dv.plan !== plan) return false; // 기다리는 사이 입력이 바뀌어 계획을 버렸다
  if (plan.baseRev !== state.serverRev) { toast("문서가 바뀌어 다시 계획해야 합니다", true); divRunSync(); divFootSync(); return false; }
  dv.busy = true;
  dv.msg = null;
  state.busy = true;
  refreshToolbar();
  divRender();
  let ok = false;
  try {
    const r = await api(`/api/docs/${id}/divisions/apply`, { method: "POST", headers: H_JSON, body: JSON.stringify({ planId: plan.planId, expectRev: plan.baseRev }) });
    if (epoch !== state.epoch) return false;
    if (r.nothing) { toast("할 일이 없습니다 — 이미 그 값에 맞습니다"); dv.plan = null; dv.msg = { kind: "done", text: divSameText(s).ok ? divSameText(s).text : "바꿀 자리가 없습니다" }; return false; }
    dv.result = { rev: r.rev, unresolved: r.unresolved || [], status: Object.fromEntries((r.candidates || []).map((c) => [c.key, c.status])),
      message: Object.fromEntries((r.candidates || []).map((c) => [c.key, c.statusMessage])) };
    state.localRev += 1; // 구조 편집 하나(structOp 과 같게) — 내려받은 뒤 반영했으면 「안 받은 변경」 으로 잡힌다
    state.structRev = state.localRev;
    applyEditState(r);
    toast(`반영 — 추가 ${r.summary.added} · 지움 ${r.summary.removed} · 글 바꿈 ${r.summary.changes}${r.owpml ? ` · ${STD()} ${r.owpml.status === "ok" ? "통과" : r.owpml.summary}` : ""}`);
    ok = true;
    await reloadDoc(); // 떨어진 자리 여러 곳이 바뀌어 부분 갱신 대신 문서를 다시 읽는다(spec_구분_기준 ② §4)
    if (epoch !== state.epoch) return true;
    divList();
  } catch (e) {
    if (epoch !== state.epoch) return ok;
    if (ok) toast(`반영했지만 문서를 다시 읽지 못했습니다: ${e.message} — 새로 고쳐 주세요`, true);
    else if (e.status === 409) { toast(`${e.message}`, true); dv.plan = null; dv.msg = { kind: "note", text: "계획이 낡았습니다 · 다시 계획하세요" }; }
    else if (e.status === 422) { toast(`표준 검사에 걸려 되돌렸습니다: ${e.message}`, true); dv.msg = { kind: "halt", text: "표준 검사에 걸려 반영하지 않았습니다(전부 되돌림) — 알림 글 참고" }; }
    else { toast(`반영하지 못했습니다: ${e.message}`, true); dv.msg = { kind: "halt", text: `반영하지 못했습니다 — ${e.message}` }; }
  } finally {
    view.busy = false; // 이 요청이 켠 것만 끈다(그 사이 다른 문서를 열었으면 dv·state.busy 는 새 문서의 것)
    if (epoch === state.epoch) {
      state.busy = false;
      refreshToolbar();
      divFootSync(); // 열린 목록의 발 — 409·422·할 일 없음 뒤에도 지금 상태로
      divShow();
    }
  }
  return ok;
}

// ---------------------------------------------------------------- 구분 기준 — 문서 표시 · 추가한 자리 · LLM 재검토(spec_구분_기준 ② §11, 2026-11-10 사용자)
// 문서 표시: GET …/divisions/members(계획 없이 find 만) → 문단마다 가장 안쪽 구분의 색(.dv-in[data-dv]), 라벨 문단은 .dv-lab, 추가한 자리는 .dv-hint(사용자)/.dv-hint-llm.
// 추가한 자리: 문서의 문단에서 오른쪽 단추 → 「구분 기준 자리로 추가…」(작은 떠 있는 입력 — 모달 아님) → POST …/divisions/hints. 2열 목록(kind "divisions-hints") · LLM 재검토.
const DV_MARKS_KEY = "nfm.divMarks";
const DV_DIM_RANK = { stage: 0, stageYear: 0, year: 1, sub: 2, org: 3 }; // 구분 순서(바깥 → 안, core.RANK) — 기타(사용자 이름)는 가장 안쪽
const DV_DIM_NAME = { stage: "단계", year: "차년도", stageYear: "단계-차년도", sub: "세부과제", org: "기관" };
const DV_KEY_ORDER = ["stage", "stageYear", "year", "sub", "org", "other"]; // 색 설명의 칩 차례(겉 → 안)
const DV_KEY_HELP = "바탕색 = 그 글이 드는 구분 기준 자리 — 파랑 단계 · 청록 단계-차년도 · 초록 차년도 · 보라 세부과제 · 주황 기관 · 자주 기타.\n" + // ② §11 「색 설명」 — 카드의 노트와 색 설명(문서 위에 떠 있는 상자 #divKey)의 노트가 같은 글
  "진한 색 + 왼쪽 띠 = 그 자리의 라벨 줄(「[1단계]」·「(1) 1차년도」·「[주관연구개발기관]」), 옅은 색 = 그 자리 안의 글·표 칸.\n" +
  "여러 자리에 겹치면 바탕은 가장 안쪽 것의 색이고, 왼쪽 띠가 든 자리마다 하나씩 겉에서 안 차례로 붙습니다(단계 › 차년도 › 기관 — 2줄·3줄). 문단에 마우스를 올리면 겉에서 안으로 소속을 보입니다.\n" +
  "가는 띠(바탕 없음) = 구분 기준 판독만 한 자리 — 표 안의 기관·차년도, 괄호 줄 글 꼴, 기관 이름만 적은 줄(「o 기관 이름」 이 기관마다 되풀이되는 곳)처럼 엔진 묶음 밖이라 반영(늘리고 줄이기) 대상이 아닙니다.\n" +
  "점선 테 = 추가한 자리(갈색 사용자 · 보라 LLM). 화면 표시일 뿐 문서·저장·PDF 는 그대로입니다.";
function divMarksOn() { return taskRnd() && quickGet(DV_MARKS_KEY) === "on"; } // 연구개발과제가 아닌 작업에는 표시 없음(spec_작업 ② §10) · 문서마다 따로 기억(quickKey — ② §12 「도구는 문서마다」)
function divMarksSet(on) { quickSet(DV_MARKS_KEY, on ? "on" : "off"); }
function divMarksToggle() { // 보기/감추기 — 「작업 개요」 카드 단추 · 문서 오른쪽 단추 메뉴 · 이름 줄 아이콘 #nameDivMarks(doc_quick.js)가 함께 쓴다(값 하나 nfm.divMarks)
  const on = divMarksOn();
  divMarksSet(!on);
  if (!on) divMembersLoad(); else divMarksDraw();
  divMarksBarRefresh();
}

function divMarksBar() { // 탭 맨 위 줄 — 보기/감추기 · 범례(구분별 색·묶음 수) · 다시 읽기 · 추가한 자리 N · LLM 재검토
  const m = dv.marks, on = divMarksOn(), d = m.data;
  const bar = el("section", "dv-marks" + (on ? " on" : "")); bar.id = "divMarksBar";
  const head = el("div", "dv-marks-head");
  const copy = el("div", "dv-marks-copy");
  copy.append(el("strong", null, "구분 기준 자리 표시")); // 2026-11-12 사용자 "문서표지는 뭘 이야기 하는지 모르겠다" — 처음 이름 「문서 표시」
  copy.append(hHelp("구분 기준 자리 표시 안내", "문서에서 단계·차년도·기관이 걸린 자리를 색으로 보여 줍니다.\n" + DV_KEY_HELP, { note: true }));
  const tg = hBtn(on ? "감추기" : "보기", () => divMarksToggle(),
    { cls: "btn sm dv-marks-toggle" + (on ? " on" : ""), title: "문서의 문단에 구분 기준 자리 색 보이기/감추기(이 브라우저에 기억) · 라벨 문단은 왼쪽 띠, 마우스를 올리면 겉→안 소속" });
  tg.setAttribute("aria-pressed", String(on));
  head.append(copy, tg);
  bar.append(head);
  const hints = (d && d.hints) || (dv.view && dv.view.hints) || [];
  if (on) {
    if (m.loading) bar.append(el("p", "dv-caption", "자리를 읽는 중…"));
    else if (m.err) bar.append(el("p", "dv-field-error", `자리를 읽지 못했습니다: ${m.err}`));
    else if (d) {
      const leg = el("div", "dv-legend");
      const byDim = new Map();
      for (const g of d.groups || []) { const k = g.dim in DV_DIM_NAME ? g.dim : "other"; const e = byDim.get(k) || { n: 0, paras: 0, name: DV_DIM_NAME[k] || g.dimName || "기타" }; e.n += 1; for (const it of g.items || []) e.paras += (it.paras || []).length; byDim.set(k, e); }
      const order = (k) => (k in DV_DIM_RANK ? DV_DIM_RANK[k] : 4);
      for (const [k, e] of [...byDim].sort((a, b) => order(a[0]) - order(b[0]))) {
        const chip = el("span", "dv-chip", `${e.name} ${e.n}`); chip.dataset.dv = k; chip.title = `${e.name} 묶음 ${e.n}개 · 그 안 문단 ${nf(e.paras)}개`; leg.append(chip);
      }
      const users = hints.filter((h) => h.by !== "llm").length, llms = hints.length - users;
      if (users) { const c = el("span", "dv-chip hint", `추가(사용자) ${users}`); leg.append(c); }
      if (llms) { const c = el("span", "dv-chip hint-llm", `추가(LLM) ${llms}`); leg.append(c); }
      if (!byDim.size && !hints.length && !(d.reads || []).length) leg.append(el("span", "dv-caption", "찾은 구분 기준 자리가 없습니다")); // 판독만인 자리(가는 띠)만 있어도 「없다」 고 하지 않는다(② §25)
      bar.append(leg);
      const stale = d.rev !== state.serverRev;
      if (stale) bar.append(el("p", "dv-caption dv-marks-note", "문서 변경됨 · 다시 읽기 필요"));
    }
  }
  const acts = el("div", "dv-marks-acts"), lists = el("div", "dv-marks-lists");
  acts.append(hBtn(m.reviewing ? "LLM 검토 중…" : m.review ? `검토 결과 ${(m.review.items || []).length}` : "LLM 검토", () => divReviewList(), { cls: "btn sm" + (taskSlots() ? "" : " primary"), // 이관이면 1단계 묶음 안 — 강조 단추는 카드에 하나(단계의 「다음 할 일」·「한 번에 진행」)
    title: "LLM 검토 — 재검토(표시한 자리가 있을 때: 형제 자리 찾기·구분 고침)와 빠진 자리 검토를 함께 돌려 한 목록으로(2열에서 실행 · 수십 초) · 하나만 다시 돌리려면 「추가한 자리」·「빠진 자리 검토」 목록에서" })); // ② §14
  if (!PEEK) acts.append(llmGuideBtn("division-review", state.id)); // 검토 단추 바로 옆에서 두 검토의 지침을 오간다.
  if (on) acts.append(hBtn("다시 읽기", () => divMembersLoad(true), { cls: "btn sm dv-marks-reload", disabled: m.loading, title: "지금 문서(편집 차례)로 자리를 다시 찾음" }));
  lists.append(hBtn(`추가한 자리 ${hints.length}`, () => divHintsList(), { title: "문서에서 표시한 라벨 문단 목록(2열) — 출처·구분·값·엔진 반영 여부·지우기" }));
  lists.append(hBtn(m.missing ? "빠진 자리 검토 중…" : m.missingLast ? `빠진 자리 후보 ${m.missingLast.missing.length}` : "빠진 자리 검토", () => divMissingList(),
    { title: "어느 묶음에도 안 든 표·문단 중 구분 기준 자리로 보이는 곳을 LLM 이 찾습니다 — 2열 목록에서 실행(판정만, 문서는 그대로)" })); // ② §13
  bar.append(acts, lists);
  return bar;
}
function divMarksBarRefresh() {
  const old = document.getElementById("divMarksBar");
  if (old) old.replaceWith(divMarksBar());
  if (typeof docQuickSync === "function") docQuickSync(); // 이름 줄 아이콘 「구분 기준 자리 표시」(doc_quick.js #nameDivMarks)의 눌림 — 카드·메뉴로 켜고 꺼도 따라온다
}

async function divMembersLoad(force = false) { // 표시 자료 읽기 — 같은 편집 차례면 다시 안 읽음
  if (!state.id) return;
  const m = dv.marks;
  if (m.loading) return;
  if (!force && m.data && m.data.rev === state.serverRev) { divMarksDraw(); divMarksBarRefresh(); return; }
  const id = state.id, epoch = state.epoch, seq = ++m.seq;
  m.loading = true; m.err = null; divMarksBarRefresh();
  try {
    await divSettingsFlush(); // 표시는 서버의 설정 값으로 찾는다(② §8 자동 저장)
    if (epoch !== state.epoch || seq !== m.seq) return;
    const r = await api(`/api/docs/${id}/divisions/members`);
    if (epoch !== state.epoch || seq !== m.seq) return;
    m.data = r; m.index = divMembersIndex(r);
    if (dv.view) dv.view.hints = r.hints || [];
    divMarksDraw();
  } catch (e) { if (epoch === state.epoch && seq === m.seq) m.err = e.message; }
  finally { if (epoch === state.epoch && seq === m.seq) { m.loading = false; divMarksBarRefresh(); if (heads.dlg === "divisions-hints") divHintsList(); else if (heads.dlg === "divisions-missing") divMissingList(); if (m.again) { m.again = false; divMembersLoad(true); } } }
}

function divHeadsSeen(key) { // 표 구조(3단계)의 실행이 바뀌었다(spec_구분_기준 ② §25 — 표시의 보탬이 그 결과를 읽는다: 문서 rev 가 같아도 다시 읽게 · astra P1)
  const m = dv.marks, was = m.s3;
  m.s3 = key;
  if (was === undefined || was === key || !m.data) return; // 처음 본 값 — 읽어 둔 자료가 이미 그때의 것
  m.data = null;
  if (divMarksOn()) divMembersLoad(true);
}

function divMembersIndex(r) { // 문단 id →{dim(가장 안쪽 — 바탕), dims[든 구분 — 겉→안 · 띠 차례], thin(판독만인 구분), readOnly(판독만인 문단), lab, hint, lines[겉→안 소속 글]}
  const idx = new Map();
  const rank = (dim) => (dim in DV_DIM_RANK ? DV_DIM_RANK[dim] : 4);
  const key = (dim) => (dim in DV_DIM_NAME ? dim : "other");
  const entry = (pid, dim, rk, lab) => { let e = idx.get(pid); if (!e) { e = { dim, rank: rk, size: Infinity, lab: !!lab, hint: null, dims: [], outer: {}, solid: new Set(), lines: [] }; idx.set(pid, e); } return e; };
  const add = (e, dim, sz, solid) => { const k = key(dim); if (!e.dims.includes(k)) e.dims.push(k); e.outer[k] = Math.max(e.outer[k] || 0, sz); if (solid) e.solid.add(k); };
  for (const g of r.groups || []) {
    for (const it of g.items || []) {
      const line = `${g.dimName} 「${it.value || "?"}」 — ${g.kindName}${g.where && g.where.table ? ` · 표 ${g.where.table}` : ""} · 항목 ${g.count}개${g.hinted ? " · 추가한 자리 꼴" : ""}${it.text ? ` · 라벨 「${it.text}」` : ""}`;
      const rk = rank(g.dim), sz = (it.paras || []).length, labs = it.labelParas || [it.label]; // 라벨이 칸이면 그 칸의 문단(2026-11-18 astra P2)
      for (const pid of it.paras || []) {
        const e = entry(pid, g.dim, -1);
        e.lines.push({ rank: rk, line });
        add(e, g.dim, sz, true);
        if (rk > e.rank || (rk === e.rank && sz < e.size)) { e.rank = rk; e.size = sz; e.dim = g.dim; }
        if (labs.includes(pid)) e.lab = true;
      }
    }
  }
  for (const h of r.hints || []) {
    if (!h.exists) continue;
    const e = entry(h.para, h.dim, 4, true);
    e.lab = true; e.hint = h.by === "llm" ? "llm" : "user";
    add(e, h.dim, 1, true);
    e.lines.push({ rank: 9, line: `추가한 자리(${h.by === "llm" ? "LLM" : "사용자"}) — ${h.dimName || h.dim} 「${h.value || "?"}」${h.engine ? " · 묶음의 라벨" : " · 표시만(아직 묶음 아님)"}${h.reason ? ` · ${h.reason}` : ""}${h.note ? ` · 메모 ${h.note}` : ""}` });
  }
  // 구분 기준 판독의 보탬(spec_구분_기준 ② §23 — 엔진 묶음 밖): 괄호 줄 글 꼴 · 표 안의 기관·차년도. 반영 대상이 아니라 「판독만」 — 가는 띠 · 바탕 없음(같은 구분의 엔진 자리 안이면 엔진 자리대로)
  const SRC = { pattern: "괄호 줄 글 꼴", name: "기관 이름", nameLine: "기관 이름 줄", table: "표 안 판독", struct: "표 구조(헤딩 추출 3단계)의 구분 값 머리", series: "같은 헤딩 아래 같은 꼴 표 — 값마다 표 하나" }; // struct · series = 표 구조 보탬(spec_구분_기준 ② §25) // nameLine = 「o 랩오투원」 처럼 이름만 적은 줄이 기관마다 되풀이되는 자리(spec_구분_기준 ② §23 「기관 이름 줄」 — 그 줄은 label · 그 아래 내용은 scope)
  for (const x of r.reads || []) {
    for (const pid of x.paras || []) {
      const e = entry(pid, x.dim, 5);
      add(e, x.dim, (x.paras || []).length, x.inGroup);
      if (x.kind === "label") e.lab = true;
      if (e.dim == null || !e.solid.size) e.dim = x.dim;
      e.lines.push({ rank: 8, line: `${x.inGroup ? "구분 기준 판독" : "판독만(반영 대상 아님)"} — ${x.dimName} 「${x.value || "?"}」 · ${SRC[x.src] || x.src}${x.table ? ` · 표 ${x.table}` : ""}${x.text ? ` · 「${x.text}」` : ""}` });
    }
  }
  for (const e of idx.values()) {
    e.lines.sort((a, b) => a.rank - b.rank);
    // 겉 → 안 — 실제로 품은 차례(그 구분의 항목이 클수록 바깥 · 2026-11-18 astra P2: 기관 절 안에 차년도 절이 있는 문서), 같으면 기준 순서(단계 › 차년도 › 세부과제 › 기관 › 기타)
    e.dims.sort((a, b) => (e.outer[b] || 0) - (e.outer[a] || 0) || DV_KEY_ORDER.indexOf(a) - DV_KEY_ORDER.indexOf(b));
    e.thin = new Set(e.dims.filter((k) => !e.solid.has(k)));
    e.readOnly = !e.solid.size;
  }
  return idx;
}

// 왼쪽 띠(사용자 2026-11-18 "구분기준이 2개 이상이면 줄을 하나만 표시하지말고 모든 색을 반영해서 넣어줘, 2줄이건 3줄이건 상관없잖아"): 문단이 든 구분마다 띠 하나(겉 → 안, 3px씩) —
// 라벨 줄은 늘(구분이 하나여도), 내용 줄은 든 구분이 둘 이상일 때 · 판독만인 문단은 늘(바탕이 없으니). 판독만인 구분(thin)은 가는 띠(1px — Fable 협의: 점선은 이미 「추가한 자리」).
// 색은 divisions.css 의 --dvc-<구분>(구분별 색과 같은 값).
const DV_STRIPE = 3;
function divStripes(dims, thin) {
  const stops = dims.map((k, i) => { const a = i * DV_STRIPE, b = (i + 1) * DV_STRIPE; return thin && thin.has(k) ? `var(--dvc-${k}) ${a}px ${a + 1}px, transparent ${a + 1}px ${b}px` : `var(--dvc-${k}) ${a}px ${b}px`; });
  return `linear-gradient(to right, ${stops.join(", ")}, transparent ${dims.length * DV_STRIPE}px)`;
}

function divMarksDraw() { // 문서의 문단 요소에 표시 클래스 — paginate 끝·자료 바뀜·토글 때
  const doc = $("doc");
  if (!doc) return;
  if (typeof zonesDraw === "function") zonesDraw(); // 편집 구역 표시(zones.js — spec_구역 ② §6 「화면」: 취합본의 기관 구역도 이것)도 같은 때 다시 단다(쪽을 다시 나누면 요소가 새것)
  for (const p of doc.querySelectorAll(".para.dv-in")) {
    p.classList.remove("dv-in", "dv-lab", "dv-multi", "dv-read", "dv-hint", "dv-hint-llm"); delete p.dataset.dv; delete p.dataset.dvs;
    p.style.removeProperty("--dv-stripes");
    if (p.dataset.dvTitle) { p.removeAttribute("title"); delete p.dataset.dvTitle; }
  }
  const on = typeof dv !== "undefined" && divMarksOn() && dv.marks.data && dv.marks.index;
  if (!on && typeof dv !== "undefined") dv.marks.only = null; // 색을 감추면 「그 구분만 또렷이」 도 푼다
  doc.classList.toggle("dv-marks", !!on);
  divKeyDraw(!!on);
  if (!on) { divOnlyDraw(); return; }
  for (const p of doc.querySelectorAll(".para[data-id]")) {
    const e = dv.marks.index.get(p.dataset.id);
    if (!e) continue;
    p.classList.add("dv-in"); p.dataset.dv = e.dim in DV_DIM_NAME ? e.dim : "other";
    if (e.lab) p.classList.add("dv-lab");
    if (e.dims.length > 1) p.classList.add("dv-multi");
    if (e.readOnly) p.classList.add("dv-read"); // 판독만 — 바탕 없음(바탕 = 엔진 자리)
    if (e.lab || e.dims.length > 1 || e.readOnly) { p.dataset.dvs = e.dims.join(" "); p.style.setProperty("--dv-stripes", divStripes(e.dims, e.thin)); } // 띠 — 든 구분마다(겉 → 안)
    if (e.hint) p.classList.add(e.hint === "llm" ? "dv-hint-llm" : "dv-hint");
    if (!p.title) { p.title = "구분 기준 자리(겉 → 안)\n" + e.lines.map((x) => x.line).join("\n"); p.dataset.dvTitle = "1"; }
  }
  divOnlyDraw(); // 쪽을 다시 나누거나 문서를 다시 읽으면 문단 요소가 새것 — 「그 구분만 또렷이」 표지도 다시
}

// 그 구분만 또렷이(② §11 「그 구분만 또렷이」, 2026-11-18 사용자 "이거 단계/차년도/기관 클릭하면 화면에 그 부분만 볼 수 있도록 해줘"): 색 설명(문서 위에 떠 있는 상자 — 2026-11-19 전에는 이름 줄)의 칩을 누르면 그 구분에 든 문단(겉 → 안 어느 자리든 —
// 띠·바탕이 그 구분인 문단)은 그대로 두고 나머지 문단을 흐리게(#doc.dv-only · .dv-hit — divisions.css). 감추지 않는다(design.md §1 「한 가지만 골라 볼 때는 나머지를 흐리게」 · 편집 구역의
// 「식별이지 거르기가 아니다」 — 둘 다 사용자 말) · 보기만(문서·쪽 나눔·내보내기 그대로). 자리 = 표시 자료(divMembersIndex 의 dims) — 다시 계산하지 않는다.
function divOnlyDraw() {
  const doc = $("doc");
  if (!doc) return;
  const k = typeof dv !== "undefined" && doc.classList.contains("dv-marks") && dv.marks.index ? dv.marks.only : null;
  for (const p of doc.querySelectorAll(".para.dv-hit")) p.classList.remove("dv-hit");
  doc.classList.toggle("dv-only", !!k);
  if (!k) return;
  for (const p of doc.querySelectorAll(".para.dv-in")) { const e = dv.marks.index.get(p.dataset.id); if (e && e.dims.includes(k)) p.classList.add("dv-hit"); }
}

function divOnlySet(k) { // k = 구분 키(그 구분만 또렷이) | null(풂). 켰는데 창에 그 구분의 문단이 없으면 지금 자리 뒤의 첫 문단(없으면 앞의 마지막)으로
  k = k || null;
  if (dv.marks.only === k) return;
  dv.marks.only = k;
  divOnlyDraw();
  divKeyPress();
  const sc = $("scroller");
  if (!k || sc.hidden) return;
  const o = sc.getBoundingClientRect();
  let before = null, after = null;
  for (const p of $("doc").querySelectorAll(".para.dv-hit")) { // 문서 차례 = 위에서 아래
    const r = p.getBoundingClientRect();
    if (!r.height) continue;
    if (r.bottom > o.top && r.top < o.bottom) return; // 창에 이미 있음 — 그대로
    if (r.top >= o.bottom) { after = p; break; }
    before = p;
  }
  const to = after || before;
  if (to) sc.scrollTop += to.getBoundingClientRect().top - o.top - 40;
}

function divKeyPress() { // 색 설명(#divKey — 문서 위에 떠 있는 상자) 칩의 눌림(「그 구분만 또렷이」) — 칩을 다시 만들지 않고 상태·풍선 도움말만
  const k = typeof dv !== "undefined" ? dv.marks.only : null;
  for (const c of document.querySelectorAll("#divKey .dv-chip")) {
    const on = c.dataset.dv === k, name = c.textContent;
    c.classList.toggle("on", on);
    c.setAttribute("aria-pressed", on ? "true" : "false");
    c.title = on ? `「${name}」 자리만 또렷이 보는 중 — 다시 누르면 풀림`
      : `「${name}」 자리만 또렷이 — 그 구분에 든 문단은 그대로, 나머지 문단은 흐리게(감추지 않음 · 문서는 그대로 · 다시 누르면 풀림)`;
  }
}

// 색 설명(② §11 「색 설명」, 2026-11-13 사용자 "색상에 대한 설명이 필요해보여"): 표시는 어느 탭을 보든 문서에 남는데 범례는 「작업 개요」 의 카드에만 있었다 →
// 색이 입혀져 있는 동안 「구분 기준 자리」 + 그 문서에 있는 구분의 칩(겉 → 안) + 「진한 줄 = 라벨」 + 노트를 보인다(#divKey). 색칠할 자리가 없으면 설명도 없다.
// 2026-11-19 사용자 "구분자리, 편집구역은 각각 아이콘으로 두고 클릭 하면 문서 상단에 플로팅으로 띄어줘, 움직일 수 있게": 설명은 문서 이름 줄이 아니라 **문서 위에 떠 있는 상자**다(#viewer 안 — 자리 · 끌어 옮기기 · 기억은 key_float.js).
// 이름 줄에는 켜고 끄는 아이콘(#nameDivMarks)만 남는다 — 그 아이콘으로 켜면 뜨고 끄면 사라진다.
function divKeyDraw(on) {
  if (typeof docQuickSync === "function") docQuickSync(); // 이름 줄 아이콘(doc_quick.js) — 문서·TASK 가 바뀌면 「구분 기준 자리 표시」·「편집 구역 표시」 를 세울지가 여기서 바뀐다(쪽을 다시 나눌 때마다 불림)
  const box = $("divKey");
  if (!box) return;
  const dims = new Map(); // 구분 키 → 이름
  if (on) {
    const d = dv.marks.data, put = (dim, name) => { const k = dim in DV_DIM_NAME ? dim : "other"; if (!dims.has(k)) dims.set(k, DV_DIM_NAME[k] || name || "기타"); };
    for (const g of d.groups || []) put(g.dim, g.dimName);
    for (const h of d.hints || []) if (h.exists) put(h.dim, h.dimName);
    for (const x of d.reads || []) put(x.dim, x.dimName);
  }
  const keys = [...dims.keys()].sort((a, b) => DV_KEY_ORDER.indexOf(a) - DV_KEY_ORDER.indexOf(b));
  if (on && dv.marks.only && !dims.has(dv.marks.only)) dv.marks.only = null; // 고른 구분의 자리가 문서에서 없어졌다 — 문서 전체로(divMarksDraw 끝의 divOnlyDraw 가 푼다)
  const sig = keys.map((k) => k + "=" + dims.get(k)).join("|");
  if (box.dataset.sig === sig && box.hidden === !sig) { divKeyPress(); return; } // 쪽을 다시 나눌 때마다 불린다 — 같으면 그대로(열어 둔 노트가 닫히지 않게 · 옮긴 자리도 그대로) · 칩의 눌림만
  box.dataset.sig = sig; box.hidden = !sig; box.textContent = "";
  const place = () => { if (typeof keyFloatPlace === "function") keyFloatPlace(); }; // 떠 있는 상자의 자리(key_float.js) — 이 설명이 사라지면 옆 상자(편집 구역)가 가운데로 온다
  if (!sig) { place(); return; }
  if (typeof keyFloatGrip === "function") box.append(keyFloatGrip()); // 손잡이(끌어서 옮기기)
  box.append(el("span", "dv-key-name", "구분 기준 자리"));
  for (const k of keys) { // 칩 = 「그 구분만 또렷이」 단추(② §11 — 다시 누르면 풀림)
    const chip = el("button", "dv-chip", dims.get(k));
    chip.type = "button"; chip.dataset.dv = k;
    chip.onclick = () => divOnlySet(dv.marks.only === k ? null : k);
    box.append(chip);
  }
  divKeyPress();
  box.append(el("span", "dv-key-tone", "진한 줄 = 라벨")); // 「가는 띠 = 판독만」(구분 기준 판독 — spec_구분_기준 ② §23)은 노트 도움말에만(상자의 글을 늘리지 않는다 — design.md §1)
  // 감추기 · 다시 보기 = 문서 이름 줄의 아이콘 #nameDivMarks(doc_quick.js — 2026-11-18 사용자 "구분자리 표기 … 아이콘 … 활성화"). 설명 안에 「감추기」 단추는 없다 — 같은 일을 하는 아이콘이 있다(design.md §10)
  const again = "감추거나 다시 보려면 문서 이름 줄의 「구분 기준 자리 표시」 아이콘을 누르세요(「작업 개요」 의 「구분 기준 자리 표시」 「보기/감추기」 · 문단의 오른쪽 단추 메뉴에도 있음)";
  const move = "이 상자는 끌어서 옮길 수 있습니다(자리는 이 브라우저에 기억 · 두 번 누르면 제자리).";
  box.append(hHelp("구분 기준 자리 색 안내", DV_KEY_HELP + "\n이 상자의 칩(단계·차년도·기관 …)을 누르면 그 구분의 자리만 또렷이 — 나머지 문단은 흐리게(다시 누르면 풀림).\n" + again + ".\n" + move, { note: true }));
  place();
}

// ---- 추가한 자리(hint) — 문서에서 오른쪽 단추
function divHintOf(pid) { const d = dv.marks.data; return ((d && d.hints) || (dv.view && dv.view.hints) || []).find((h) => h.para === pid) || null; }
function divCtxItems(e) { // 오른쪽 단추 메뉴 항목(앞에 구분선) — 표 칸 메뉴(tselContextMenu)와 문단 메뉴(divContextMenu) 공용
  const p = e.target.closest && e.target.closest(".para[data-id]");
  const zone = typeof zonesCtxItems === "function" ? zonesCtxItems(e) : []; // 편집 구역의 「구역 지정…」·「구역 지정 고치기…」·「지정 해제」(zones.js — spec_구역 ② §3 「지정 — 사람이 고른 블록」) — 문단이 아닌 곳(표 칸의 여백)에서도
  if (!p || !state.id || !taskRnd()) return zone;
  const h = divHintOf(p.dataset.id);
  const items = [null, [h ? "구분 기준 자리 표시 고치기…" : "구분 기준 자리로 추가…", "", () => divHintPop(p, e, h)]];
  if (h) items.push(["이 자리 표시 지우기", "", () => divHintDelete(h.id)]);
  items.push([divMarksOn() ? "구분 기준 표시 감추기" : "구분 기준 표시 보기", "", () => divMarksToggle()]);
  return [...items, ...zone];
}
function divContextMenu(e) { // 표 밖 문단 — 표 칸은 tselContextMenu 가 맡는다
  if (!state.id || (typeof cellOf === "function" && cellOf(e.target))) return;
  const items = divCtxItems(e).slice(1);
  if (!items.length) return;
  if (typeof tmkParaItems === "function") items.push(...tmkParaItems(e)); // 표 모듈(table_make.js) — 「고른 글로 표 만들기…」(spec_헤딩_추출 ② §11)
  if (typeof tempCtxItems === "function") items.push(...tempCtxItems(e)); // TEMP 로 지정·해제(heading_temp.js — spec_헤딩_추출 ② §15)
  e.preventDefault();
  ctxOpen(e, items);
}
function divDimGuess(text) { // 글에서 구분 기준 짐작(서버 core._key 와 같은 낱말 — 값은 서버가 읽음)
  const t = text || "";
  const st = /(?:\d+|[Nnx])\s*단계/.test(t), yr = /(?:\d+|[Nnx])\s*(?:차\s*년도|년차)/.test(t);
  if (st && yr) return "stageYear";
  if (st) return "stage";
  if (yr) return "year";
  if (/\(\s*세부\s*(?:\d+|[Nn])\s*\)/.test(t)) return "sub";
  if (/(주관|공동)연구개발기관|기관/.test(t)) return "org";
  return "";
}
function divPopClose() { const o = document.getElementById("divHintPop"); if (o) o.remove(); }
function divHintPop(p, e, cur = null) { // 작은 떠 있는 입력(모달 아님) — 구분·값·메모 → 추가/고치기
  divPopClose();
  ctxClose();
  const text = oneLine(readText(p)).slice(0, 60);
  const pop = el("div", "dv-pop"); pop.id = "divHintPop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", "구분 기준 자리로 추가");
  pop.append(el("strong", null, cur ? "구분 기준 자리 표시 고치기" : "구분 기준 자리로 추가"), el("p", "dv-pop-text", `「${text}」`));
  const row1 = el("label", "dv-field"); row1.append(el("span", null, "구분 기준"));
  const sel = el("select");
  for (const [k, name] of [["", "고르세요"], ...Object.entries(DV_DIM_NAME), ["other", "기타(이름 직접)"]]) sel.append(new Option(name, k));
  const curDim = cur ? (cur.dim in DV_DIM_NAME ? cur.dim : "other") : divDimGuess(text);
  sel.value = curDim;
  row1.append(sel);
  const rowN = el("label", "dv-field"); rowN.hidden = sel.value !== "other"; rowN.append(el("span", null, "구분 기준 이름"));
  const name = el("input"); name.type = "text"; name.placeholder = "예: 분야 · 권역"; name.value = cur && !(cur.dim in DV_DIM_NAME) ? cur.dim : ""; rowN.append(name);
  sel.onchange = () => { rowN.hidden = sel.value !== "other"; if (!rowN.hidden) name.focus(); };
  const row2 = el("label", "dv-field"); row2.append(el("span", null, "값(비우면 글에서 읽음)"));
  const val = el("input"); val.type = "text"; val.placeholder = "예: 1차년도 · 1단계 · 주관 · 공동2"; val.value = cur ? cur.value || "" : ""; row2.append(val);
  const row3 = el("label", "dv-field"); row3.append(el("span", null, "메모(선택)"));
  const note = el("input"); note.type = "text"; note.placeholder = "LLM 재검토에 함께 보냄"; note.value = cur ? cur.note || "" : ""; row3.append(note);
  const acts = el("div", "dv-pop-acts");
  const ok = hBtn(cur ? "고치기" : "추가", async () => {
    const dim = sel.value === "other" ? name.value.trim() : sel.value;
    if (!dim) { toast("구분 기준을 고르세요(기타면 이름을 쓰세요)"); (sel.value === "other" ? name : sel).focus(); return; }
    ok.disabled = true;
    await divHintSave({ id: cur ? cur.id : undefined, para: p.dataset.id, dim, value: val.value.trim(), note: note.value.trim() });
    divPopClose();
  }, { cls: "btn sm primary" });
  acts.append(ok, hBtn("취소", () => divPopClose()), hHelp("구분 기준 자리 추가 안내", "라벨 문단(되풀이 항목의 머리) 하나를 표시합니다. 혼자면 묶음이 안 되니 형제를 더 표시하거나 「LLM 재검토」로 찾으세요.", { note: true }));
  pop.append(row1, rowN, row2, row3, acts);
  pop.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { ev.preventDefault(); divPopClose(); } else if (ev.key === "Enter" && ev.target.tagName !== "BUTTON") { ev.preventDefault(); ok.click(); } });
  document.body.append(pop);
  pop.style.left = `${Math.max(8, Math.min(e.clientX, innerWidth - pop.offsetWidth - 8))}px`;
  pop.style.top = `${Math.max(8, Math.min(e.clientY, innerHeight - pop.offsetHeight - 8))}px`;
  sel.focus();
}
document.addEventListener("mousedown", (e) => { const o = document.getElementById("divHintPop"); if (o && !o.contains(e.target)) divPopClose(); }, true);

async function divHintSave(body) {
  if (!state.id) return;
  const epoch = state.epoch;
  try {
    const r = await api(`/api/docs/${state.id}/divisions/hints`, { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return;
    divHintsChanged(r.hints, `표시 ${body.id ? "고침" : "추가"} — ${r.hint.dim in DV_DIM_NAME ? DV_DIM_NAME[r.hint.dim] : r.hint.dim} 「${r.hint.value || "값 없음"}」${r.hints.length === 1 ? " · 형제를 더 표시하거나 「LLM 재검토」" : ""}`);
  } catch (e) { if (epoch === state.epoch) toast(`표시하지 못했습니다: ${e.message}`, true); }
}
async function divHintDelete(hid) {
  if (!state.id) return;
  const epoch = state.epoch;
  try {
    const r = await api(`/api/docs/${state.id}/divisions/hints/${encodeURIComponent(hid)}`, { method: "DELETE" });
    if (epoch !== state.epoch) return;
    divHintsChanged(r.hints, "표시 지움");
  } catch (e) { if (epoch === state.epoch) toast(`지우지 못했습니다: ${e.message}`, true); }
}
function divHintsChanged(hints, msg) { // 서버가 계획을 버렸으니 화면도 — 표시는 켜서 다시 읽음
  if (dv.view) dv.view.hints = hints || [];
  dv.plan = null; dv.result = null;
  if (!divMarksOn()) divMarksSet(true);
  if (dv.view && $("divBox").childElementCount) divRender(); else divMarksBarRefresh();
  divMembersLoad(true);
  if (heads.dlg === "divisions") headsColClose();
  if (msg) toast(msg);
}

async function divHintsList() { // 2열 「구분 기준 — 추가한 자리」
  if (!state.id) return;
  if (!dv.marks.data || dv.marks.data.rev !== state.serverRev) { if (!dv.marks.loading) await divMembersLoad(true); if (!dv.marks.data) { toast("자리를 읽지 못했습니다"); return; } }
  const d = dv.marks.data, hints = d.hints || [], last = dv.marks.llmLast;
  const { tools, body, foot } = headsDlg("divisions-hints", "구분 기준 — 추가한 자리", "문서에서 오른쪽 단추로 표시한 라벨 문단 · 줄을 누르면 그 문단으로 · LLM 재검토는 이 목록만 고칩니다(자동 묶음은 그대로)");
  const users = hints.filter((h) => h.by !== "llm").length;
  tools.append(el("span", "muted", `사용자 ${users} · LLM ${hints.length - users} · 묶음의 라벨이 된 것 ${hints.filter((h) => h.engine).length}`),
    hBtn("다시 읽기", () => divMembersLoad(true), { disabled: dv.marks.loading }));
  if (last) {
    const box = el("div", "dv-llm-last");
    box.append(el("strong", null, `LLM 재검토 ${fmtWhen(last.at)} — 반영 ${last.applied.length} · 건너뜀 ${last.skipped.length}${last.call && last.call.ms ? ` · ${Math.round(last.call.ms / 1000)}s` : ""}${last.call && last.call.model ? ` · ${last.call.model}` : ""}`));
    if (last.summary) box.append(el("p", null, last.summary));
    if (last.skipped.length) { const ul = el("ul", "dv-drop"); for (const x of last.skipped) { const li = el("li"); li.textContent = `${x.action} ${x.para || x.hintId || ""} — ${x.why}${x.reason ? ` (${x.reason})` : ""}`; ul.append(li); } box.append(ul); }
    body.append(box);
  }
  const [tbl, tb] = hTable(["출처", "구분", "값", "문단 · 까닭 · 메모", "상태", ""]);
  for (const h of hints) {
    const tr = el("tr", "go"); tr.tabIndex = 0;
    hCell(tr, h.by === "llm" ? "LLM" : "사용자", "dv-num");
    const dimName = h.dimName || h.dim;
    hCell(tr, dimName + (h.read && h.read.dim !== h.dim && h.dim in DV_DIM_NAME ? ` (글에서는 ${h.read.dimName})` : ""), null, h.read && h.read.dim !== h.dim ? "표시한 구분과 글에서 읽은 구분이 다름 — 엔진은 글을 따릅니다" : "");
    hCell(tr, h.value || (h.read ? h.read.value : ""), null, h.read && h.value && h.read.value !== h.value ? `글에서 읽은 값: ${h.read.value}` : "");
    const tdt = el("td", "dv-labels"); tdt.append(h.exists ? h.text : "(문단이 지워짐)");
    const why = [h.reason, h.note ? `메모 ${h.note}` : "", h.llmNote ? `LLM 제안: ${h.llmNote}` : ""].filter(Boolean).join(" · ");
    if (why) tdt.append(el("div", "muted", why));
    tr.append(tdt);
    const st = !h.exists ? ["unresolved", "문단 없음"] : h.engine ? ["applied", "묶음의 라벨"] : h.read ? ["already", "표시만 — 형제가 없음"] : ["unsupported", "표시만 — 글에 값 낱말 없음"];
    const tds = el("td"); tds.append(el("span", `dv-badge ${st[0]}`, st[1]));
    tds.title = h.engine ? "같은 꼴·같은 구분의 문단들과 묶음이 되어 변경 계획에 듭니다" : h.read ? "값 차례가 이어지는 같은 꼴 라벨이 2개 이상이어야 묶음 — 형제를 표시하거나 LLM 재검토" : "단계·차년도·기관 같은 값 낱말이 글에 없어 엔진이 사본 이름을 못 바꿉니다(구분 기준 자리 표시에만 보임)";
    tr.append(tds);
    const tdx = el("td");
    tdx.append(hBtn("지우기", () => divHintDelete(h.id), { title: "이 표시를 지움(문서는 그대로)" }));
    tdx.onclick = (ev) => ev.stopPropagation();
    tr.append(tdx);
    tr.onclick = () => { for (const x of tb.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); if (paraEl(h.para)) scrollToBlock(h.para, true); else toast("그 문단이 지금 문서에 없습니다"); };
    tr.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); tr.click(); } };
    tb.append(tr);
  }
  if (!hints.length) { const tr = el("tr"); hCell(tr, "아직 표시한 자리가 없습니다 — 문서의 라벨 문단에서 오른쪽 단추 → 「구분 기준 자리로 추가…」"); tb.append(tr); }
  body.append(tbl);
  foot.append(el("span", "muted", hints.length ? "LLM 재검토: 표시한 자리의 형제(값만 다른 같은 꼴 라벨)를 찾아 더하고, 구분·값이 글과 다르면 고칩니다" : "문서에서 자리를 표시한 뒤 LLM 재검토"),
    hBtn(dv.marks.llm ? "LLM 재검토 중…" : "LLM 재검토", () => divLlmReview(), { cls: "btn sm primary", disabled: dv.marks.llm || !hints.length || dv.busy }),
    hBtn("닫기", () => headsColClose()));
}

async function divLlmReview() {
  if (!state.id || dv.marks.llm) return;
  const id = state.id, epoch = state.epoch;
  await flushAll();
  if (epoch !== state.epoch) return;
  await divSettingsFlush(); // 검토는 서버의 설정 값을 쓴다(② §8 자동 저장)
  if (epoch !== state.epoch) return;
  dv.marks.llm = true; divMarksBarRefresh(); if (heads.dlg === "divisions-hints") divHintsList();
  toast("LLM 재검토 중… 수십 초 걸립니다");
  try {
    const r = await api(`/api/docs/${id}/divisions/llm_review`, { method: "POST", headers: H_JSON, body: JSON.stringify({}) });
    if (epoch !== state.epoch) return;
    dv.marks.llmLast = { at: Date.now() / 1000, applied: r.applied || [], skipped: r.skipped || [], summary: r.summary || "", call: r.call || null };
    dv.marks.llm = false;
    divHintsChanged(r.hints, `LLM 재검토 — 반영 ${(r.applied || []).length} · 건너뜀 ${(r.skipped || []).length}${r.summary ? ` · ${r.summary.slice(0, 80)}` : ""}`);
    divHintsList();
  } catch (e) {
    if (epoch !== state.epoch) return;
    toast(`LLM 재검토를 못 했습니다: ${e.message}`, true);
  } finally {
    if (epoch === state.epoch) { dv.marks.llm = false; divMarksBarRefresh(); if (heads.dlg === "divisions-hints") divHintsList(); }
  }
}

// ---- 빠진 자리 검토(spec_구분_기준 ② §13, 2026-11-10 사용자) — 어느 묶음에도 안 든 표·문단 중 구분 기준 자리로 보이는 곳을 LLM 이 판정(판정만 — 문서·묶음은 그대로).
// 2열 「구분 기준 — 빠진 자리 후보」(kind "divisions-missing"): 「LLM 검토 실행」 → POST …/divisions/llm_missing → 결과 표. 문단 후보는 「자리로 추가」(추가한 자리), 표 후보는 표시만.
const DV_CONF = { high: ["applied", "높음"], medium: ["already", "중간"], low: ["unsupported", "낮음"] };
function divMissingGo(x) { // 후보의 문단, 또는 표(쪽 조각이면 첫 조각)로
  if (x.kind !== "table") { if (paraEl(x.id)) scrollToBlock(x.id, true); else toast("그 문단이 지금 문서에 없습니다"); return; }
  const t = document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(x.id)}"]`);
  if (t) t.scrollIntoView({ block: "center", behavior: scrollHow() }); else toast("그 표가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)");
}
// LLM 후보 목록을 볼 차례로(spec_구분_기준 ② §13·§14 「후보 줄 차례」, 2026-11-11 사용자 「자리로 추가 버튼이 어디있냐?」 — 표 후보 41줄 아래 5,000px 에 묻혀 있었다):
// 「자리로 추가」 할 수 있는 문단 후보가 맨 위(이미 추가한 것은 그 다음), 재검토 줄, 나머지 문단, 표 후보 차례. 같은 꼴 표 후보(구분 + 제목 첫 마디가 같음 —
// 「시약·재료구입 및 활용계획서」 36개)는 한 줄로 묶어 「× 36곳」 — 누를 때마다 다음 곳으로 간다. -> [{x(대표 후보), all[같은 꼴 전부]}]
const divCandAdd = (x) => x.kind === "paragraph" && x.dim in DV_DIM_NAME && !(x.sources || []).includes("review");
function divCandRows(items) {
  const rank = (x) => (divCandAdd(x) ? (divHintOf(x.id) ? 1 : 0) : (x.sources || []).includes("review") ? 2 : x.kind === "table" ? 4 : 3);
  const out = [], by = new Map();
  for (const x of [...items].sort((a, b) => rank(a) - rank(b))) { // 같은 차례끼리는 서버가 준 차례 그대로(sort 는 안정)
    const key = x.kind === "table" ? `${x.dim}|${String(x.title || x.text || x.id).split(" · ")[0].trim()}` : null;
    const row = key && by.get(key);
    if (row) row.all.push(x);
    else { const r = { x, all: [x] }; if (key) by.set(key, r); out.push(r); }
  }
  return out;
}
function divCandGo(tr, tb, row) { // 줄을 누르면 문서의 그 자리로 — 묶인 줄은 누를 때마다 다음 곳
  for (const y of tb.querySelectorAll("tr.sel")) y.classList.remove("sel");
  tr.classList.add("sel");
  const i = (+tr.dataset.at || 0) % row.all.length;
  tr.dataset.at = i + 1;
  divMissingGo(row.all[i]);
}
function divCandNote(rows) { // 목록 위 한 줄 — 누를 것이 몇 개이고 어디 있는지
  const add = rows.filter((r) => divCandAdd(r.x)), left = add.filter((r) => !divHintOf(r.x.id)).length, tables = rows.filter((r) => r.x.kind === "table");
  const n = tables.reduce((s, r) => s + r.all.length, 0);
  return el("div", "dv-cand-note", `문단 후보 ${add.length}개${add.length ? ` — 맨 위에 있음 · 오른쪽 끝 「자리로 추가」(남은 것 ${left})` : ""} · 표 후보 ${n}개${tables.length !== n ? `(같은 꼴끼리 ${tables.length}줄)` : ""} — 표시만`);
}
function divCandMore(td, tr, row) { // 묶인 표 후보 줄의 「× N곳」 표시
  if (row.all.length < 2) return;
  td.append(" ", el("span", "dv-badge already", `× ${row.all.length}곳`));
  tr.title = `같은 꼴 표 ${row.all.length}곳 — 누를 때마다 다음 곳으로`;
}
function divMissingList() {
  if (!state.id) return;
  const m = dv.marks, last = m.missingLast;
  const { tools, body, foot } = headsDlg("divisions-missing", "구분 기준 — 빠진 자리 후보",
    "어느 묶음에도 안 든 표·문단 중 구분 기준 자리로 보이는 곳을 LLM 이 찾습니다 · 판정만(문서·묶음은 그대로) · 줄을 누르면 그 자리로");
  if (last) {
    tools.append(el("span", "muted", `후보 ${last.missing.length} · 보낸 표 ${last.sent.tables} · 문단 ${last.sent.paragraphs} · ${fmtWhen(last.at)}${last.call && last.call.ms ? ` · ${Math.round(last.call.ms / 1000)}s` : ""}${last.call && last.call.model ? ` · ${last.call.model}` : ""}`));
    if (last.rev !== state.serverRev) tools.append(el("span", "hd-msg note", "문서가 바뀜 — 다시 검토"));
    if (last.summary) { const box = el("div", "dv-llm-last"); box.append(el("strong", null, "LLM 판단"), el("p", null, last.summary)); body.append(box); }
  }
  const [tbl, tb] = hTable(["확신", "구분", "종류", "자리", "되풀이 꼴 · 까닭", ""]);
  const rows = divCandRows(last ? last.missing : []);
  if (rows.length) body.append(divCandNote(rows));
  for (const row of rows) {
    const x = row.x, tr = el("tr", "go"); tr.tabIndex = 0;
    const [cls, name] = DV_CONF[x.confidence] || DV_CONF.low;
    const tdc = el("td"); tdc.append(el("span", `dv-badge ${cls}`, name)); tr.append(tdc);
    hCell(tr, x.dimName || x.dim);
    hCell(tr, x.kind === "table" ? `표 ${x.size || ""}`.trim() : "문단", null, x.id);
    const tdw = el("td", "dv-labels"); tdw.append(x.kind === "table" ? (x.title || x.text || x.id) : x.text);
    divCandMore(tdw, tr, row);
    const sub = x.kind === "table" && x.title ? x.text : (x.path || []).join(" › ");
    if (sub) tdw.append(el("div", "muted", sub));
    tr.append(tdw);
    const tdr = el("td", "dv-labels"); tdr.append(x.pattern || "—"); if (x.reason) tdr.append(el("div", "muted", x.reason)); tr.append(tdr);
    const tdx = el("td");
    if (x.kind === "paragraph" && x.dim in DV_DIM_NAME) {
      const has = !!divHintOf(x.id);
      tdx.append(hBtn(has ? "추가됨" : "자리로 추가", () => divHintSave({ para: x.id, dim: x.dim, note: "빠진 자리 검토" }),
        { disabled: has, title: "이 문단을 「추가한 자리」로 표시 — 같은 꼴·같은 구분의 문단과 묶음이 되면 변경 계획에 듭니다" }));
    } else tdx.append(el("span", "muted", x.kind === "table" ? "표시만" : ""));
    tdx.onclick = (ev) => ev.stopPropagation();
    tr.append(tdx);
    tr.onclick = () => divCandGo(tr, tb, row);
    tr.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); tr.click(); } };
    tb.append(tr);
  }
  if (!last || !last.missing.length) { const tr = el("tr"); hCell(tr, m.missing ? "검토 중… 수십 초 걸립니다" : last ? "빠진 자리로 보이는 곳이 없습니다" : "아직 검토하지 않았습니다 — 아래 「LLM 검토 실행」(수십 초)"); tb.append(tr); }
  body.append(tbl);
  foot.append(el("span", "muted", "표 후보는 표시만(엔진 규칙은 따로 넣음) · 문단 후보는 「자리로 추가」"),
    hBtn(m.missing ? "검토 중…" : last ? "다시 검토" : "LLM 검토 실행", () => divLlmMissing(), { cls: "btn sm primary", disabled: m.missing || dv.busy }),
    hBtn("닫기", () => headsColClose()));
}
async function divLlmMissing() {
  if (!state.id || dv.marks.missing) return;
  const id = state.id, epoch = state.epoch;
  await flushAll();
  if (epoch !== state.epoch) return;
  await divSettingsFlush(); // 검토는 서버의 설정 값을 쓴다(② §8 자동 저장)
  if (epoch !== state.epoch) return;
  dv.marks.missing = true; divMarksBarRefresh(); if (heads.dlg === "divisions-missing") divMissingList();
  toast("빠진 자리 검토 중… 수십 초 걸립니다");
  try {
    const r = await api(`/api/docs/${id}/divisions/llm_missing`, { method: "POST", headers: H_JSON, body: JSON.stringify({}) });
    if (epoch !== state.epoch) return;
    dv.marks.missingLast = { at: Date.now() / 1000, rev: r.rev, missing: r.missing || [], skipped: r.skipped || [], summary: r.summary || "", sent: r.sent || { tables: 0, paragraphs: 0 }, call: r.call || null };
    toast(`빠진 자리 검토 — 후보 ${(r.missing || []).length}곳`);
  } catch (e) {
    if (epoch !== state.epoch) return;
    toast(`빠진 자리 검토를 못 했습니다: ${e.message}`, true);
  } finally {
    if (epoch === state.epoch) { dv.marks.missing = false; divMarksBarRefresh(); if (heads.dlg === "divisions-missing") divMissingList(); }
  }
}

// ---- LLM 검토 — 두 검토를 함께 돌려 한 목록으로(spec_구분_기준 ② §14, 2026-11-10 사용자 「검토만 2가지는 일단 병렬로 해서 최종 취합」)
// POST …/divisions/review: 서버가 재검토(표시한 자리가 있을 때만)와 빠진 자리 검토를 동시에 돌려 items 로 합친다. 마지막 결과는 작업에 남아 GET …/divisions 의 review 로 다시 온다.
// 2열 「구분 기준 — LLM 검토 결과」(kind "divisions-review"). auto(안 돌 까닭이 있으면 서버가 {skipped}, 실패는 조용히)는 전에 새 작업의 첫 분석이 불렀다 — 2026-11-15 부터 첫 분석은 부르지 않는다
// (spec_작업 ② §9·§20 「구분 기준은 옵션」): 지금 이 화면에서 auto 로 부르는 곳은 없고 사람이 「LLM 검토 실행」 으로 돌린다. 이름 줄의 「구분 기준」 표시(doc_status.js)가 이 열을 연다.
const DV_SRC = { review: "재검토", missing: "빠진 자리" };
const DV_ACT = { add: "자리 추가", change: "구분·값 고침", remove: "지움" };
function divReviewAdopt(r) { // 취합 결과를 화면 상태로 — 두 낱개 목록(추가한 자리의 재검토 요약 · 빠진 자리 후보)에도 같은 결과가 보이게
  const m = dv.marks;
  m.review = r;
  if (r.review) m.llmLast = { at: r.at, applied: r.review.applied || [], skipped: r.review.skipped || [], summary: r.review.summary || "", call: r.review.call || null };
  if (r.missing) m.missingLast = { at: r.at, rev: r.rev, missing: r.missing.missing || [], skipped: r.missing.skipped || [], summary: r.missing.summary || "",
    sent: r.missing.sent || { tables: 0, paragraphs: 0 }, call: r.missing.call || null };
  divRenderApplied(); // 「문서 반영 상태」 의 「값과 안 맞는 자리 N곳」 줄(② §16) — 탭이 안 그려져 있으면 아무 일도 안 함
}
function divReviewSeen(r) { // GET …/divisions 의 review·reviewing → 화면 상태. 다른 화면(새로 고치기 전)이 시작한 검토가 도는 중이면 5초마다 상태만 다시 읽는다(입력 폼은 그대로)
  const m = dv.marks;
  if (r.review && (!m.review || m.review.at < r.review.at)) divReviewAdopt(r.review);
  if (m.reviewOwn) return;
  m.reviewing = !!r.reviewing;
  if (r.reviewing) setTimeout(divReviewPeek, 5000);
  divMarksBarRefresh();
  if (heads.dlg === "divisions-review") divReviewList();
}
async function divReviewPeek() {
  if (!state.id || dv.marks.reviewOwn) return;
  const id = state.id, epoch = state.epoch;
  let r;
  try { r = await api(`/api/docs/${id}/divisions`); } catch { return; }
  if (epoch === state.epoch) divReviewSeen(r);
}
function divReviewList() {
  if (!state.id) return;
  const m = dv.marks, last = m.review;
  const { tools, body, foot } = headsDlg("divisions-review", "구분 기준 — LLM 검토 결과",
    "재검토(표시한 자리의 형제 찾기·구분 고침)와 빠진 자리 검토(묶음 밖 표·문단)를 함께 돌려 한 목록으로 · 줄을 누르면 그 자리로");
  if (last) {
    const rv = last.review, ms = last.missing, why = last.why || {}, errs = last.errors || {};
    const parts = [rv ? `재검토 반영 ${rv.applied.length} · 건너뜀 ${rv.skipped.length}` : `재검토 안 함 — ${errs.review || why.review || "까닭 모름"}`,
      ms ? `빠진 자리 후보 ${ms.missing.length}(보낸 표 ${ms.sent.tables} · 문단 ${ms.sent.paragraphs})` : `빠진 자리 검토 안 함 — ${errs.missing || why.missing || "까닭 모름"}`];
    tools.append(el("span", "muted", `${parts.join(" · ")} · ${fmtWhen(last.at)}${last.ms ? ` · ${Math.round(last.ms / 1000)}s` : ""}${last.costUsd ? ` · $${last.costUsd}` : ""}`));
    if (last.rev !== state.serverRev) tools.append(el("span", "hd-msg note", "문서가 바뀜 — 다시 검토"));
    if (last.form) tools.append(el("span", "muted", `양식 정보 「${last.form.name || last.form.key}」 를 함께 보냄`)); // ② §16 — 양식마다 관리하는 요청
    const pend = Array.isArray(last.pending) && last.rev === state.serverRev ? last.pending : []; // 검토한 뒤 문서가 바뀌었으면(반영 등) 낡은 수라 안 보인다 — 「문서 반영 상태」 줄과 같은 조건
    if (pend.length) { // 이미 찾은 묶음 가운데 구분 값이 아직 안 들어간 곳(스크립트가 셈 — LLM 의 「빠진 자리」 와 다르다, ② §16 「검토에 보이게」)
      const box = el("div", "dv-llm-last dv-pending");
      box.append(el("strong", null, `값과 안 맞는 자리 ${pend.length}곳 — 찾아 둔 자리인데 아직 반영하지 않았습니다`));
      const ul = el("ul"), kinds = new Map(); // 같은 꼴(구분·종류·라벨·수)은 한 줄로 — 빈 양식은 같은 기관 절이 수십 곳
      for (const p of pend) {
        const text = `${p.dimName} · ${p.kindName} · ${(p.labels || []).join(" / ") || p.key}${p.count !== p.target ? ` (${p.count} → ${p.target})` : ""}`;
        const k = kinds.get(text); if (k) k.n += 1; else kinds.set(text, { n: 1, first: p });
      }
      for (const [text, k] of [...kinds].slice(0, 8)) {
        const li = el("li", "go", text + (k.n > 1 ? ` × ${k.n}곳` : ""));
        li.tabIndex = 0; li.title = k.n > 1 ? "문서의 그 자리(첫 곳)로" : "문서의 그 자리로"; li.onclick = () => divGo(k.first);
        li.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); divGo(k.first); } };
        ul.append(li);
      }
      if (kinds.size > 8) ul.append(el("li", "muted", `… ${kinds.size - 8}가지 더`));
      box.append(ul, hBtn("변경 계획 보기", () => divPlan(), { cls: "btn sm primary", disabled: dv.busy, title: "지금 입력한 구분 값으로 계획을 세워 바꿀 자리를 봅니다(10~20초) — 반영은 그 목록에서" }));
      body.append(box);
    }
    for (const [name, part] of [["재검토", rv], ["빠진 자리 검토", ms]]) {
      if (!part || !part.summary) continue;
      const box = el("div", "dv-llm-last"); box.append(el("strong", null, `LLM 판단 — ${name}`), el("p", null, part.summary)); body.append(box);
    }
  }
  const items = last ? last.items || [] : [];
  const [tbl, tb] = hTable(["출처 · 확신", "구분", "자리", "되풀이 꼴 · 까닭", ""]); // 2열 폭(480~620px)에 들어가게 5칸 — 확신은 출처 칸, 종류(표·문단)는 자리 칸의 둘째 줄(design.md §1)
  const rows = divCandRows(items);
  if (rows.length) body.append(divCandNote(rows));
  for (const row of rows) {
    const x = row.x, tr = el("tr", "go"); tr.tabIndex = 0;
    const src = x.sources || [];
    const tds = el("td", "wrap"); tds.append(src.map((k) => DV_SRC[k] || k).join(" + ") || "—"); // .wrap = 최소 7em(.dv-labels 는 14em — 셋이면 열 폭을 넘는다)
    if (x.confidence) { const [cls, name] = DV_CONF[x.confidence] || DV_CONF.low; const d = el("div"); d.append(el("span", `dv-badge ${cls}`, name)); tds.append(d); }
    tr.append(tds);
    hCell(tr, (x.dimName || x.dim) + (x.value ? ` · ${x.value}` : ""));
    const tdw = el("td", "dv-labels"); tdw.title = x.id;
    tdw.append(x.kind === "table" ? (x.title || x.text || x.id) : x.text || x.id);
    divCandMore(tdw, tr, row);
    const sub = [x.kind === "table" ? `표 ${x.size || ""}`.trim() : "", x.kind === "table" && x.title ? x.text : (x.path || []).join(" › ")].filter(Boolean).join(" · ");
    if (sub) tdw.append(el("div", "muted", sub));
    tr.append(tdw);
    const tdr = el("td", "wrap"); tdr.append(x.pattern || (x.action ? DV_ACT[x.action] || x.action : "—"));
    const why = [x.pattern && x.action ? DV_ACT[x.action] || x.action : "", x.reason, x.note].filter(Boolean).join(" · ");
    if (why) tdr.append(el("div", "muted", why));
    tr.append(tdr);
    const tdx = el("td");
    if (src.includes("review")) tdx.append(el("span", "muted", x.note ? "제안만" : "반영됨"));
    else if (x.kind === "paragraph" && x.dim in DV_DIM_NAME) {
      const has = !!divHintOf(x.id);
      tdx.append(hBtn(has ? "추가됨" : "자리로 추가", () => divHintSave({ para: x.id, dim: x.dim, note: "LLM 검토" }),
        { disabled: has, title: "이 문단을 「추가한 자리」로 표시 — 같은 꼴·같은 구분의 문단과 묶음이 되면 변경 계획에 듭니다" }));
    } else tdx.append(el("span", "muted", x.kind === "table" ? "표시만" : ""));
    tdx.onclick = (ev) => ev.stopPropagation();
    tr.append(tdx);
    tr.onclick = () => divCandGo(tr, tb, row);
    tr.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); tr.click(); } };
    tb.append(tr);
  }
  if (!items.length) { const tr = el("tr"); hCell(tr, m.reviewing ? "검토 중… 수십 초 걸립니다" : last ? "고치거나 더할 자리가 없습니다" : "아직 검토하지 않았습니다 — 아래 「LLM 검토 실행」(수십 초)"); tb.append(tr); }
  body.append(tbl);
  foot.append(el("span", "muted", "재검토 줄은 추가한 자리에 이미 반영 · 빠진 자리의 문단 후보는 「자리로 추가」, 표 후보는 표시만"),
    hBtn(m.reviewing ? "검토 중…" : last ? "다시 검토" : "LLM 검토 실행", () => divReview(), { cls: "btn sm primary", disabled: m.reviewing || dv.busy }),
    hBtn("닫기", () => headsColClose()));
}
async function divReview(auto = false) {
  if (!state.id || dv.marks.reviewing) return;
  const id = state.id, epoch = state.epoch, m = dv.marks;
  if (!auto) { await flushAll(); if (epoch !== state.epoch) return; await divSettingsFlush(); if (epoch !== state.epoch) return; } // 검토는 서버의 설정 값을 쓴다(② §8 자동 저장)
  m.reviewing = m.reviewOwn = true; divMarksBarRefresh(); if (heads.dlg === "divisions-review") divReviewList();
  if (typeof docStatusPing === "function") docStatusPing(); // 이름 줄의 분석 상태 — 「구분 기준 검토 중」(doc_status.js)
  if (!auto) toast("LLM 검토 중… 수십 초 걸립니다");
  try {
    const r = await api(`/api/docs/${id}/divisions/review`, { method: "POST", headers: H_JSON, body: JSON.stringify({ auto }) });
    if (epoch !== state.epoch) return;
    m.reviewing = m.reviewOwn = false;
    if (r.skipped) { if (r.review && !m.review) divReviewAdopt(r.review); return; } // auto 로 불렀는데 안 돈 것(이미 검토함 · 지원 양식 아님 · LLM 연결 없음) — 지금 화면은 auto 로 부르지 않는다(위)
    divReviewAdopt(r);
    if (r.review) divHintsChanged(r.hints, null); // 추가한 자리 층이 바뀜 — 문서 표시·계획을 다시
    const msg = "구분 기준 LLM 검토 — " + ([r.review ? `재검토 반영 ${r.review.applied.length}` : "", r.missing ? `빠진 자리 후보 ${r.missing.missing.length}` : ""].filter(Boolean).join(" · ") || "돌릴 검토가 없습니다");
    if (!auto) { toast(msg); divReviewList(); }
    else if ((r.items || []).length) toast(msg, false, { label: "보기", run: () => { showTab("Div"); divReviewList(); } });
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (auto) console.warn("구분 기준 LLM 검토(auto)를 못 했습니다:", e.message);
    else toast(`LLM 검토를 못 했습니다: ${e.message}`, true);
  } finally {
    if (epoch === state.epoch) { m.reviewing = m.reviewOwn = false; divMarksBarRefresh(); if (heads.dlg === "divisions-review") divReviewList(); }
    if (typeof docStatusPing === "function") docStatusPing(); // 이름 줄의 분석 상태 — 검토가 끝남(후보 수)
  }
}
function divFormOpen() { // 양식 정보 편집기(2열 — heading_forms.js `headsForm`, spec_헤딩_추출 ② §12)를 「구분 기준」·「표」 탭에서 열기 — 열에서 고치던 지침·표 지침 글이 있으면 먼저 묻는다
  if (typeof headsForm !== "function") return;
  if (heads.dlg !== "form" && (!headsGuideLeave() || (typeof tblAgentLeave === "function" && !tblAgentLeave()))) return;
  headsForm();
}
function divFormChanged() { if (state.id && dv.view && !$("paneDiv").hidden) divShow(); } // 양식 정보를 고르거나 저장한 뒤(heading_forms.js) — 양식 줄 단추의 이름을 새로

// ---- 양식별 코멘트 줄(spec_구분_기준 ② §18, 2026-11-11) — 양식 줄 바로 아래: 입력 칸(2줄) · 「코멘트 남기기」(Ctrl+Enter) · 상태 한 줄 · 「코멘트 N건」 접이식 목록. 쓰던 글·펼침은 dv.comment
function divCommentRow() {
  const st = dv.comment, box = el("section", "dv-comments"), row = el("div", "dv-comment-row"), ta = el("textarea");
  box.id = "divComments"; box.setAttribute("aria-label", "양식별 코멘트");
  ta.id = "divCommentText"; ta.rows = 2; ta.maxLength = 500; ta.value = st.draft;
  const label = el("label", "dv-comment-label", "양식 코멘트"); label.htmlFor = ta.id;
  ta.placeholder = "예: 2-2는 해당 차년도만 구분해 주세요"; ta.setAttribute("aria-label", "구분 기준 결과에 대한 코멘트");
  ta.oninput = () => { st.draft = ta.value; if (!st.busy) { st.msg = ""; st.err = false; } divCommentSync(box); };
  ta.onkeydown = (e) => { // Ctrl+Enter — 한글 조합 중이면 key 가 "Process" 라 code 도 본다(조합 중인 글자도 value 에 있다)
    if ((e.ctrlKey || e.metaKey) && (e.key === "Enter" || e.code === "Enter" || e.code === "NumpadEnter")) { e.preventDefault(); divCommentSave(); }
  };
  const send = hBtn("코멘트 남기기", () => divCommentSave(), { cls: "btn",
    title: "이 양식의 양식 정보(「구분 기준 자리」 절)에 날짜와 함께 쌓이고 구분 기준 LLM 검토가 읽습니다 · Ctrl+Enter" }); send.id = "divCommentBtn";
  const status = el("p", "dv-comment-status"); status.id = "divCommentStatus"; status.setAttribute("role", "status");
  row.append(ta, send); box.append(label, row, status);
  divCommentSync(box); divCommentList(box);
  return box;
}

function divCommentSync(box = $("divComments")) { // 단추·상태 한 줄·(비운) 글만 맞춘다 — 입력 칸을 다시 만들지 않는다(포커스·한글 조합을 안 끊음)
  if (!box) return;
  const st = dv.comment, ta = box.querySelector("textarea"), status = box.querySelector(".dv-comment-status");
  if (ta.value !== st.draft) ta.value = st.draft;
  box.querySelector(".dv-comment-row .btn").disabled = st.busy || !st.draft.trim();
  status.textContent = status.title = st.msg; status.classList.toggle("fail", st.err);
}

function divCommentList(box = $("divComments")) { // 「코멘트 N건」 접이식 목록(날짜 · 글, 새 것이 아래) — 없으면 줄도 없다
  if (!box || !dv.view) return;
  const st = dv.comment, cs = dv.view.comments || []; // 서버를 다시 켜기 전에는 comments 가 없다
  box.querySelector("details")?.remove();
  if (!cs.length) return;
  const det = el("details", "dv-comment-list"), ul = el("ul"); det.open = st.open;
  det.ontoggle = () => { if (!det.isConnected) return; st.open = det.open; if (det.open) ul.scrollTop = ul.scrollHeight; }; // 펼치면 새 것(맨 아래)이 보이게
  for (const c of cs) { const li = el("li"); li.append(el("time", null, c.date || ""), " · ", c.text || ""); ul.append(li); }
  det.append(el("summary", null, `코멘트 ${cs.length}건`), ul);
  if (typeof headsForm === "function") det.append(hBtn("양식 정보에서 고치기", () => divFormOpen(), { cls: "linkish", title: "코멘트를 고치거나 지우려면 양식 정보 편집기에서 — 「구분 기준 자리」 절 끝의 코멘트 줄" }));
  box.append(det);
}

async function divCommentSave() { // POST …/divisions/comments — 실패해도 쓴 글은 그대로 두고 까닭을 상태 한 줄에
  const st = dv.comment, text = st.draft.trim();
  if (!state.id || !dv.view || !text || st.busy) return;
  const epoch = state.epoch;
  Object.assign(st, { busy: true, msg: "코멘트 남기는 중…", err: false }); divCommentSync();
  let r;
  try { r = await api(`/api/docs/${state.id}/divisions/comments`, { method: "POST", headers: H_JSON, body: JSON.stringify({ text }) }); }
  catch (e) {
    if (epoch !== state.epoch) return;
    const why = [404, 405].includes(e.status) && !/[가-힣]/.test(e.message) ? "서버에 코멘트 기능이 아직 없습니다 — 서버를 다시 켠 뒤 남기세요" : e.message; // 옛 서버 = 경로 없음
    Object.assign(st, { busy: false, msg: `코멘트를 남기지 못했습니다: ${why}`, err: true }); divCommentSync();
    return;
  }
  if (epoch !== state.epoch || !dv.view) return;
  const was = dv.view.formInfo, fi = r.formInfo || null, name = fi ? `양식 정보 「${fi.name}」` : "양식 정보";
  Object.assign(dv.view, { formInfo: fi, comments: r.comments || [] });
  Object.assign(st, { busy: false, err: false, draft: st.draft.trim() === text ? "" : st.draft, // 보내는 동안 더 쓴 글은 남긴다
    msg: r.created ? `코멘트를 남겼습니다 — ${name} 새로 만듦 · 다음 LLM 검토부터 읽음` : `코멘트를 남겼습니다 — ${name} · 다음 LLM 검토부터 읽음` });
  const back = document.activeElement === document.body || !!$("divComments")?.contains(document.activeElement); // 다른 칸에서 쓰는 중이면 포커스를 안 뺏는다
  if ((was && was.key) !== (fi && fi.key) || (was && was.name) !== (fi && fi.name)) divRender(); // 양식 정보가 새로 생김 — 양식 줄 단추 이름도(입력값·펼침은 dv 에 있어 그대로)
  else { divCommentSync(); divCommentList(); }
  if (back) $("divCommentText")?.focus();
  if (heads.dlg === "form" && typeof formLoad === "function" && !headsFormDirty()) formLoad(fi && fi.key); // 열려 있는 양식 정보 편집기(안 고친 글)도 새 판으로 — 옛 판 위에 저장하지 않게
}

$("doc").addEventListener("contextmenu", divContextMenu); // 표 칸은 tselContextMenu(먼저 묶임)가 맡고 preventDefault 하므로 여기서는 표 밖 문단만

