"use strict";
// HWPX·DOCX 웹 편집 화면 (spec/spec_hwpx_웹편집.md ② §2~§4, docx 는 spec_docx_웹편집.md). astra UI/UX 검토(2026-11-08) 반영:
// 로컬 수정 번호(localRev)로 미저장·미검증 판정, 문서 전환 시 이전 요청 격리(epoch), 다운로드 성공 확인 뒤에만 「내려받음」.

const $ = (id) => document.getElementById(id);
const IMG_OK = new Set(["png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"]);
const ICON = { ok: "✓", warn: "!", fail: "✕", skip: "–", wait: "", run: "" };
const LS = "\u2028";
const PLAIN = (() => { const d = document.createElement("div"); d.contentEditable = "plaintext-only"; return d.contentEditable === "plaintext-only"; })();

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
});
const state = { ...fresh(), zoom: 1, fit: "width", twoUp: false, wheelFlip: true, tool: "page", epoch: 0, enterHinted: false, polling: false, compare: null };

// ---------------------------------------------------------------- 공통
async function api(url, opts = {}) {
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
function toast(msg, err = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), err ? 7000 : 3500);
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

async function openFile(file) {
  if (!file) return;
  if (!/\.(hwpx|docx)$/i.test(file.name)) { toast("hwpx·docx 파일만 열 수 있습니다", true); return; }
  if (!confirmDiscard()) return;
  const fd = new FormData();
  fd.append("file", file);
  setSaveState("busy", `${file.name} 여는 중…`);
  try { await load((await api("/api/docs", { method: "POST", body: fd })).docId); }
  catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); }
}

async function openSample(name) {
  if (!confirmDiscard()) return;
  setSaveState("busy", `${name} 여는 중…`);
  try { await load((await api(`/api/samples/${encodeURIComponent(name)}`, { method: "POST" })).docId); }
  catch (e) { setSaveState("err", "열지 못함"); toast(e.message, true); }
}

async function load(id) {
  const d = await api(`/api/docs/${id}`);
  for (const t of state.timers.values()) clearTimeout(t); // 이전 문서의 대기 중 반영은 버린다(epoch 로 응답도 무시)
  state.epoch += 1;
  Object.assign(state, fresh(), { id, name: d.name, blocks: d.blocks, edited: new Set(d.edited), unrestored: new Set(d.unrestored || []), pristine: d.pristine,
    kinds: d.kinds || {}, undo: d.undo || 0, owpml: d.owpml || null, format: d.format || "hwpx",
    stored: !!(d.work && d.work.stored), serverRev: d.rev || 0, created: d.work ? d.work.created : null, persistError: d.persistError || null });
  history.replaceState(null, "", `#w=${id}`); // 새로 고치거나 주소를 다시 열어도 이 작업(spec_작업 ② §7)
  $("downloadBtn").textContent = `${EXT()} 저장`;
  $("downloadBtn").title = `${EXT()} 로 내려받기 (Ctrl+S)`;
  $("verifyBtn").title = `저장본을 ${APP()} PDF 로 찍어 원본과 쪽마다 비교`;
  setDocFonts(d.webFonts);
  walkParas(d.blocks, (b) => { state.texts[b.id] = b.text || ""; state.original[b.id] = b.text || ""; state.byId.set(b.id, b); state.byIdOrig.set(b.id, b); });
  Object.assign(state.original, d.original || {});
  refreshToolbar();
  $("fileName").textContent = d.name;
  $("fileName").title = d.name;
  $("fileMeta").textContent = fmtSize(d.size) + (state.stored && state.created ? ` · 작업 ${fmtWhen(state.created)}` : "");
  $("fileMeta").title = state.stored ? "편집·검증 기록이 이 작업에 저장됩니다 — 「기록」 탭" : "작업 저장이 꺼져 있어 서버를 끄면 사라집니다";
  $("logOriginal").href = `/api/works/${id}/file/original`;
  $("tabLog").hidden = !state.stored;
  $("fileInfo").hidden = false;
  $("workspaceNav").hidden = false;
  $("empty").hidden = true;
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
  headsReset();
  divReset();
  if (typeof tablesReset === "function") tablesReset(); // 표 탭(tables.js)
  if (typeof compareReset === "function") compareReset();
  showTab("Verify");
  renderVerify({});
  poll();
  loadWorks();
  outlineLoad();
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
  renderRecentWorks($("workList"), list.slice(0, 4));
  renderWorks($("workListDlg"), list);
  $("recent").hidden = !list.length;
  $("recentCount").textContent = `전체 ${list.length}개`;
}

function renderRecentWorks(ul, list) {
  ul.textContent = "";
  for (const w of list) {
    const format = (w.format || "").toLowerCase(), li = el("li", "recent-work" + (w.id === state.id ? " current" : ""));
    const open = el("button", "recent-work-open"), icon = el("span", `recent-file-icon ${format === "docx" ? "docx" : "hwpx"}`, format.toUpperCase() || "문서");
    open.type = "button";
    open.title = `${w.name} · 작업 ${w.id}`;
    open.setAttribute("aria-label", `${w.name} · ${fmtWhen(w.created)} 시작 · 작업 ${w.id} 이어서 열기`);
    icon.setAttribute("aria-hidden", "true");
    const main = el("span", "recent-work-main");
    main.append(el("span", "recent-work-name", w.name), el("span", "recent-work-meta",
      `${fmtSize(w.size || 0)} · 시작 ${fmtWhen(w.created)} · ${w.edited ? `고친 문단 ${w.edited}개` : `편집 ${w.rev || 0}회`}`));
    const tags = el("span", "recent-work-status");
    for (const kind of ["import", "edit"]) {
      const v = (w.verify || {})[kind];
      if (!v || !v.status) continue;
      const tag = verifyTag(kind, v);
      if (kind === "edit" && (v.rev == null || v.rev !== w.rev)) {
        tag.textContent = v.rev == null ? "출력파일 기록 확인" : "출력파일 재검증 필요";
        tag.className = `vtag ${v.rev == null ? "none" : "warn"}`;
        tag.title += v.rev == null ? " · 현재 편집본과 같은지 기록에서 확인하세요." : " · 이 검증 뒤에 문서가 수정되었습니다.";
      }
      tags.append(tag);
    }
    if (!tags.childElementCount) tags.append(el("span", "vtag none", "검증 전"));
    main.append(tags);
    const end = el("span", "recent-work-end"), time = el("span", "recent-work-time", fmtWhen(w.updated));
    time.title = `마지막 작업 ${fmtWhen(w.updated)}`;
    end.append(time, el("span", "recent-work-arrow", "이어서 열기 →"));
    open.append(icon, main, end);
    open.onclick = () => openWork(w.id);
    li.append(open);
    ul.append(li);
  }
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
    open.append(top, el("span", "work-meta", `${(w.format || "").toUpperCase()} · ${fmtSize(w.size || 0)} · 만듦 ${fmtWhen(w.created)} · 바뀜 ${fmtWhen(w.updated)}`
      + (w.edited ? ` · 고친 문단 ${w.edited}개` : "") + (w.source === "sample" ? " · 예제" : "")));
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
  if ($("worksDlg").open) $("worksDlg").close();
  if (id === state.id) return;
  if (!confirmDiscard()) return;
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

function closeDoc() {
  for (const t of state.timers.values()) clearTimeout(t);
  state.epoch += 1;
  Object.assign(state, fresh());
  headsReset();
  divReset();
  if (typeof tablesReset === "function") tablesReset(); // 표 탭(tables.js)
  if (typeof compareReset === "function") compareReset();
  $("workspaceNav").hidden = true;
  document.querySelector(".workspace").classList.remove("compare-mode");
  $("docBar").hidden = $("scroller").hidden = $("panel").hidden = $("fileInfo").hidden = $("panelBtn").hidden = true;
  $("empty").hidden = false;
  $("downloadBtn").disabled = $("verifyBtn").disabled = true;
  $("doc").textContent = "";
  setSaveState("", "");
  history.replaceState(null, "", location.pathname);
}

let logTimer = null;
function logTouched() { // 기록 탭이 보이면 잠시 뒤 다시 읽는다(편집마다 부르지 않게)
  if ($("paneLog").hidden || !state.id) return;
  clearTimeout(logTimer);
  logTimer = setTimeout(drawLog, 1200);
}

const LOG_KIND = { create: "작업 만듦", text: "글 고침", revert: "되돌리기", split: "문단 나누기", merge: "문단 합치기", chars: "글자 모양",
  para: "문단 모양", table: "표 행·열", rejected: "표준 검사로 되돌림", undo: "실행 취소", verify: "검증 시작", verified: "검증 끝",
  download: "내려받기", reopen: "작업 다시 엶", headings: "헤딩 추출", outline: "개요 편집" };
const OUTLINE_OP = { enter: "하위 레벨 줄(Enter)", sibling: "같은 레벨 트리(Alt+Enter)", level: "개요 레벨 바꾸기(Alt+↑/↓)", move: "줄 옮기기(끌기)", remove: "빈 레터 줄 지우기" };
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
    case "headings": // 헤딩 추출 실행(spec_헤딩_추출 ② §7) — 단계 · LLM 여부 · 끝남/실패
      box.textContent = `${e.stage}단계 · ${e.llm ? "LLM" : "스크립트만"} · ${e.status === "done" ? "끝남" : e.status === "failed" ? "실패" : e.status}`
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
      const total = tops.slice(i, j).reduce((a, [x]) => a + objWidth(x), 0);
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
      flow.push({ kind: "table", id: b.id, tpl: t, rows: [...t.tBodies[0].rows], sec: s, pageStart: !!b.pageStart });
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
  doc.textContent = "";
  const m = state.mapping;
  const brk = new Map();
  if (m && m.breaks) for (const x of m.breaks) brk.set(x.kind === "rows" ? `r:${x.id}:${x.row}` : `b:${x.id}`, x.page);
  const many = state.sections.length > 1;
  let body = null, num = 0, sec = -1;
  const open = (n, s) => {
    if (m) for (let k = num + 1; k < n; k++) doc.append(gapPage(k));
    const g = state.sections[s] || DEFAULT_PAGE, mm = g.marginsMm;
    const sheet = el("div", "sheet");
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
    if (m && m.pageStatus && m.pageStatus[n] === "split") {
      const note = el("div", "cont-note", "↑ PDF 에서는 앞 쪽의 문단·표 행이 이 쪽 위까지 이어집니다(웹은 문단·행 안에서 나누지 않아 앞 쪽에 함께 보임)");
      sheet.append(note);
    }
    doc.append(sheet);
    num = n;
    sec = s;
  };
  const startsAt = (it, key, first) => {
    if (m) { const p = brk.get(key); return p && p > num ? p : 0; }
    return first && (it.pageStart || it.sec !== sec) ? num + 1 : 0;
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
      else if (p) { open(p, it.sec); seg = null; }
      if (!seg) {
        seg = it.tpl.cloneNode(false);
        seg.append(it.tpl.querySelector("colgroup").cloneNode(true), el("tbody"));
        if (r > 0) seg.classList.add("cont");
        body.append(seg);
      }
      seg.tBodies[0].append(tr);
    });
  }
  if (m) for (let k = num + 1; k <= m.pageCount; k++) doc.append(gapPage(k));
  if (m) {
    overflowPush(doc);
    const epoch = state.paginateEpoch = (state.paginateEpoch || 0) + 1;
    document.fonts.ready.then(() => { // url() 웹 글꼴이 늦게 오면 줄 수·높이가 바뀐다 — 그때 다시 밀고 표시를 다시 그린다(그 사이 다시 나눴으면 생략)
      if (epoch !== state.paginateEpoch || !state.mapping || !doc.isConnected) return;
      const pushed = overflowPush(doc), split = overflowSplit(doc); // 밀기 뒤 넘침 나눔도 다시(새 블록 쪽 — a4 세션, astra 11-10 ③)
      if (!pushed && !split) return; // 옮긴 게 없으면 다시 그리지 않음(표시 다시 그리기가 느림 — 61 세션)
      refit();
      if (typeof tplMarksDraw === "function" && heads.marks) tplMarksDraw();
      if (typeof tblMarksDraw === "function") tblMarksDraw();
    });
  }
  overflowSplit(doc); // 쪽 자리 정보가 없는 새 블록(구분 기준 반영 사본 등)으로 길어진 쪽은 용지 높이로 어림해 나눈다(② §3-1 「넘침 나눔」)
  markUnmapped();
  refit();
  $("scroller").scrollTop = keep;
  if (act && act.isConnected && document.activeElement !== act) {
    act.focus({ preventScroll: true });
    if (actSel) setCaret(act, actSel.start, actSel.end);
  }
  if (typeof tplMarksDraw === "function" && heads.marks) tplMarksDraw(); // 헤딩 템플릿 표시(쪽을 다시 나누면 표가 사라지므로)
  if (typeof tblMarksDraw === "function") tblMarksDraw(); // 표 도구 표지 · 엑셀식 보기 되살림(spec_헤딩_추출 ② §10)
  if (typeof divMarksDraw === "function") divMarksDraw(); // 구분 기준 문서 표시(문서를 다시 읽으면 문단 요소가 새것, spec_구분_기준 ② §11)
}

// 쪽 상자가 용지 본문을 넘치고 그 끝이 PDF 자리를 모르는 문단(빈 줄 — 매핑 없음)이나 짧은 글(5자 이하 — 「가까운 자리」 매핑이라 쪽이 틀릴 수 있음, ④)이면
// 다음 쪽 맨 위로 보낸다(② §3-1 「넘침 밀기」): 쪽 머리 줄이 빈 줄·한 글자면 매핑이 그 쪽 나눔을 못 잡아 앞 쪽이 길어진다(연구개발계획서 양식 28쪽 「o」「-」, 14쪽 빈 줄).
// 다음 쪽이 빈 쪽 표지(gap-page — 앞 쪽 문단·행이 이어지는 쪽)이거나 없으면 그대로 둔다. 표·그림·자리 아는 문단에서 멈춘다.
// 끝이 표 조각이면 뒤 행부터 다음 쪽 머리의 이어짐 조각(.cont)으로 옮긴다 — 한글이 그 표를 쪽 경계의 행에서 나눴는데 그 쪽 맨 위 줄이 짧은 칸 글(「20××년」)이라
// 매핑이 나눔을 못 잡은 경우(43·65쪽). 세로 병합 칸이 걸친 행은 못 옮긴다 — 웹 조각이 병합 칸을 못 나누는 제한이지 한글은 나눈다(43→44쪽, astra 11-10 지적 — ④).
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
// 그대로 쌓여 그 상자가 용지의 몇 배로 길어진다(2026-11-10 사용자 "왜 다 페이지가 안맞냐" — 2-2 기관 사본·(3)(4) 참여기관 절 사본). 새 블록이 든 쪽 상자가 용지
// 본문보다 길면 용지 높이로 어림해 뒤를 잘라 「≈n쪽 +k」 조각 상자로 잇는다 — 새 블록이 없는 쪽은 웹 글꼴·표 높이 차이로 길어진 것이라 그대로(쪽 번호 = PDF 쪽).
// 조각은 같은 쪽 번호(PDF 자리가 없으니 뒤 쪽 번호를 밀지 않는다 — 출력파일 검증을 돌려야 실제 쪽을 안다). 나눔 단위 = 최상위 문단·그림·표 행 — 위 행의 세로 병합 칸이 덮는 행
// 앞에서는 못 자르므로 그 행 묶음(안전한 경계 사이)을 **한 덩이로 재어** 들어가는지 본다(astra 11-10: 남은 100px 에 150px 묶음이면 첫 행만 보고 넣지 않음). 조각마다 한 덩이는 남긴다.
// 높이는 쪽마다 한 번에 다 읽고(강제 배치 1회) 그다음 DOM 을 옮긴다(61 세션 부탁 — 읽기·쓰기를 번갈지 않음). 웹 글꼴이 늦게 와 높이가 바뀌면(paginate 의 fonts.ready) 조각도
// 다시 재어 더 나누고 같은 쪽의 조각 번호를 DOM 차례로 다시 매긴다. -> 나눈 게 있으면 true.
const SPLIT_TOL = 1.08; // 넘침 나눔 문턱 — 용지 본문의 8% 까지는 웹·한글 높이 차이로 보고 안 나눈다(새 블록 두세 줄로 조각 하나를 만들지 않게)

function overflowSplit(doc) {
  const isNew = (p) => state.kinds[p.dataset.id] === "new";
  const sheets = [...doc.querySelectorAll(".sheet")].filter((s) => [...s.querySelectorAll(".para")].some(isNew));
  if (!sheets.length) return false;
  const jobs = []; // 읽기만: [{s, units, cuts}]
  for (const s of sheets) {
    const g = state.sections[+s.dataset.sec] || DEFAULT_PAGE;
    const room = (g.heightMm - g.marginsMm.t - g.marginsMm.b) * PX_PER_MM + 1; // 본문 높이(px, 배율 전)
    const body = s.querySelector(".sheet-body");
    if (body.offsetHeight <= room * SPLIT_TOL) continue; // 웹 글꼴·표 높이 차이만큼(④ 「웹 표가 한글보다 길다」)은 PDF 쪽과 같은 상자로 두고 그보다 길 때만 나눈다
    const z = s.offsetWidth ? s.getBoundingClientRect().width / s.offsetWidth : 1; // #doc 의 CSS zoom — 화면 px → 배율 전 px
    const b0 = body.getBoundingClientRect().top;
    const units = []; // 나눔 단위 {el, seg(표 조각이면), row, safe(이 단위 앞에서 자를 수 있나), top, bottom} — 본문 위끝 기준 px
    for (const c of body.children) {
      if (c.tagName === "TABLE" && c.tBodies[0]) {
        let reach = -1; // 위 행의 세로 병합 칸이 닿는 마지막 행 — 그 안의 행 앞에서는 못 자른다
        [...c.tBodies[0].rows].forEach((tr, r) => {
          const rc = tr.getBoundingClientRect();
          units.push({ el: tr, seg: c, row: r, safe: reach < r, top: (rc.top - b0) / z, bottom: (rc.bottom - b0) / z });
          for (const td of tr.cells) reach = Math.max(reach, r + td.rowSpan - 1);
        });
      } else {
        const rc = c.getBoundingClientRect();
        units.push({ el: c, safe: true, top: (rc.top - b0) / z, bottom: (rc.bottom - b0) / z });
      }
    }
    // 덩이 = 안전한 경계에서 다음 안전한 경계 앞까지(병합 칸이 걸친 행 묶음 — 문단·그림은 저 혼자 한 덩이). 덩이의 아래끝으로 들어가는지 본다
    const chunkBottom = new Array(units.length);
    for (let i = units.length - 1, last = units.length ? units[units.length - 1].bottom : 0; i >= 0; i--) {
      chunkBottom[i] = last;
      if (units[i].safe && i > 0) last = units[i - 1].bottom;
    }
    const cuts = [];
    let start = 0;
    for (let i = 1; i < units.length; i++) {
      const u = units[i];
      if (u.safe && chunkBottom[i] - start > room) { cuts.push(i); start = u.top; }
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
    cuts.forEach((ci, k) => {
      const ns = s.cloneNode(false); // 같은 용지·여백·구역(style·data-*) — 안은 비움(조각을 또 나누면 그 조각의 사본)
      ns.classList.add("over");
      const label = el("button", "sheet-label", `≈${n}쪽`); // 「+k」는 아래에서 DOM 차례로 매긴다
      label.type = "button";
      label.title = `새 문단·표(구분 기준 반영 등)는 ${APP()} PDF 자리가 없어 ${n}쪽 상자가 용지보다 길어졌습니다 — 용지 높이로 어림해 나눈 조각(쪽 번호는 밀지 않음). `
        + `실제 쪽은 「출력파일 검증」 뒤 PDF 탭에서 확인하세요.${m ? ` 누르면 ${APP()} PDF ${n}쪽.` : ""}`;
      label.onclick = () => { if (m) { state.pdfWhich = "original"; syncSeg(); state.pdfPage = sheetNo || n; showTab("Pdf"); setPanel(true); } };
      const nb = el("div", "sheet-body");
      ns.append(label, nb);
      prev.after(ns);
      prev = ns;
      const end = k + 1 < cuts.length ? cuts[k + 1] : units.length;
      let whole = null; // 행 0 부터 옮기는 표는 조각째(빈 껍데기를 남기지 않음) — 그 뒤 행 단위는 건너뜀
      for (let i = ci; i < end; i++) {
        const u = units[i];
        if (!u.seg) { nb.append(u.el); continue; }
        if (u.seg === whole) continue;
        if (u.row === 0) { whole = u.seg; nb.append(u.seg); continue; }
        let cont = nb.lastElementChild;
        if (!cont || cont.tagName !== "TABLE" || cont.dataset.tbl !== u.seg.dataset.tbl || !cont.classList.contains("cont")) {
          cont = u.seg.cloneNode(false);
          cont.append(u.seg.querySelector("colgroup").cloneNode(true), el("tbody"));
          cont.classList.add("cont");
          nb.append(cont);
        }
        cont.tBodies[0].append(u.el);
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

function gapPage(n) {
  // 이 쪽에서 시작하는 문단·표 행이 없음 — 앞 쪽의 긴 문단·표 행이 이어지거나 그림만 있는 쪽(웹은 문단·행 안에서 나누지 않음)
  const d = el("div", "gap-page");
  d.dataset.page = n;
  const b = el("button", null, `${n}쪽 — 앞 쪽의 문단·표 행이 이어지는 쪽(웹에서는 나누지 않음) · PDF 로 보기`);
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
      const rid = b.inlineRow, items = new Map();
      node = el("div", `inline-row ${b.align || ""}`);
      for (; i < blocks.length; i++) {
        const x = blocks[i];
        if (x.inlineRow === rid) {
          const it = el("div", "inline-item");
          it.append(renderBlock(x));
          items.set(x.id, it);
          node.append(it);
        } else if (x.captionOf && items.has(x.captionOf)) {
          items.get(x.captionOf).append(renderBlock(x));
        } else break;
      }
      i -= 1;
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
  p.contentEditable = PLAIN ? "plaintext-only" : "true";
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
  for (const r of runs) {
    const s = el("span", null, disp(r.text));
    if (r.format) charLook(s, r.format, f, small);
    else if (f.script) scriptLook(s, f, f); // 문단 전체가 첨자 — 줄 높이는 문단 크기로 두고 글만 윗·아래로
    p.append(s);
  }
  if (state.edited.has(b.id)) p.classList.add("edited");
  return p;
}

// 장평(글자 가로 배율, spec_hwpx_웹편집 ② §3-3): 문단 상자를 1/장평 배 넓게 잡고 scaleX(장평)로 줄여 그린다 — 글자가 가로로 줄고 줄 나눔도 한글과 같은 폭에서.
// 한글 글자 간격 = 글자 폭 × 장평 × (1 + 자간) — 자간은 장평을 적용한 폭 기준(PDF 실측: 장평 80%·자간 −18% = 0.652em, 0.8×0.82 = 0.656)이라
// 줄인 상자 안의 자간은 그대로(전각 글자 1em 기준 letter-spacing), 들여쓰기·여백만 1/장평 배로 준다.
const ratioOf = (f) => (f.ratioPct > 0 ? f.ratioPct / 100 : 1);

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
  st.textAlign = { justify: "justify", distribute: "justify", center: "center", right: "right" }[f.align] || "left";
  if (f.lineSpacingPct) st.lineHeight = String(Math.max(0.8, f.lineSpacingPct / 100));
  const left = f.indentLeftMm || 0, first = f.firstLineMm || 0;
  // 한글 내어쓰기(음수)는 첫 줄을 왼쪽 여백에 두고 나머지 줄을 더 들인다 — CSS 로는 padding-left = left + |intent|, text-indent = intent
  st.paddingLeft = `${(left + (first < 0 && state.format !== "docx" ? -first : 0)) / k}mm`; // Word 내어쓰기: 첫 줄 = left − hanging(spec_docx_웹편집 ② §2, newfilemanager-6e 부탁)
  if (first) st.textIndent = `${first / k}mm`;
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
  const b = blocks[blocks.length - 1];
  if (!b || b.type !== "paragraph" || b.inlineRow) return;
  const p = td.lastElementChild;
  if (!p || !p.classList.contains("para")) return;
  const f = b.format || {};
  const ls = f.lineSpacingPct ? Math.max(0.8, f.lineSpacingPct / 100) : 1.35; // 1.35 = style.css 「table.tbl td .para」 기본 줄 간격
  const s = Math.max(f.sizePt || 10, b.endSizePt || 0, ...(b.runs || []).map((r) => (r.format && !r.format.script && r.format.sizePt) || 0));
  const extra = (s * (ls - 1) * 25.4) / 72; // 글꼴 높이 = 크기(1em): 1쪽 10pt 1줄 칸 저장 4.33 = 3.53 + 여백 0.4×2, 3쪽 4.52 = 3.53 + 0.5×2 — 11-10 실측
  if (extra > 0) p.style.marginBottom = `${(-extra).toFixed(2)}mm`;
}

function renderImage(b) {
  const ext = (b.media || "").split(".").pop().toLowerCase();
  const w = b.widthMm || 30, h = b.heightMm || 20;
  if (!b.widthMm && !b.heightMm && b.media) return el("span");
  const ph = () => {
    const d = el("div", `img img-ph ${b.align || ""}`, b.media ? `그림 (${ext.toUpperCase()} — 브라우저가 못 그림, PDF 탭에서 확인)` : "그림 (연결 그림)");
    d.style.width = `${w}mm`;
    d.style.height = `${h}mm`;
    return d;
  };
  if (!b.media || !IMG_OK.has(ext)) return ph();
  const img = new Image();
  img.className = `img ${b.align || ""}`;
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
  if (r.rev != null) state.serverRev = r.rev;
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
  state.editsDirty = true;
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
  if (state.pristine) return setSaveState("ok", n ? "글은 고쳤으나 파일은 원본과 같음" : "원본과 바이트 동일", "지금 저장하면 원본 파일과 바이트가 같습니다");
  const notDownloaded = state.localRev !== state.downloadedRev || !state.downloadedAt; // 다시 연 작업은 이 화면에서 아직 안 받음
  if (notDownloaded && state.stored && state.persistError)
    return setSaveState("err", `고친 문단 ${n}개 · 작업 저장 실패 — ${EXT()} 저장으로 받아 두세요`, `서버가 작업 폴더에 쓰지 못했습니다(다음 편집 때 다시 시도): ${state.persistError}`);
  if (notDownloaded && state.stored)
    return setSaveState("ok", `고친 문단 ${n}개 · 작업에 자동 저장`, `편집은 이 작업에 저장되어 서버를 다시 켜도 「작업」 목록에서 이어집니다(서버가 1.5초 안에 작업 폴더에 씀). 파일은 이 화면에서 아직 내려받지 않았습니다 — 「${EXT()} 저장」(지난 내려받기는 「기록」 탭)`);
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
    } else if (e.key === "Escape") {
      p.blur();
    }
  });
  doc.addEventListener("input", (e) => { const p = e.target.closest(".para"); if (p) scheduleSave(p); });
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
  let q = step < 0 ? p.previousElementSibling : p.nextElementSibling;
  while (q && !q.classList.contains("para")) q = step < 0 ? q.previousElementSibling : q.nextElementSibling;
  return !!q;
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
  for (const b of document.querySelectorAll("#docBar [data-char], #docBar [data-align], #docBar [data-indent]")) b.disabled = !on || state.busy;
  for (const x of [$("tbSize"), $("tbColor"), $("tbFirst"), $("tbLine")]) x.disabled = !on || state.busy;
  const inCell = (on && !!p.closest("td")) || (typeof tselActive === "function" && tselActive()); // 칸 안 문단에 있거나 칸을 끌어 골랐을 때(표 모듈)
  $("tbTable").setAttribute("aria-disabled", String(!inCell));
  for (const b of document.querySelectorAll("#tbTable button")) b.disabled = !inCell || state.busy;
  $("undoBtn").disabled = !state.undo || state.busy;
  $("undoBtn").textContent = state.undo ? `↶ 실행 취소 (${state.undo})` : "↶ 실행 취소";
  const o = state.owpml, st = $("owpmlState");
  st.className = "owpml-state" + (o ? ` ${o.status}` : "");
  const std = STD();
  st.textContent = !o ? `${std} 검사 대기` : o.status === "fail" ? `${std} ✕ 거절` : o.status === "warn" ? `${std} ! 물려받은 위반` : `${std} ✓ 새 위반 없음`;
  st.title = o ? o.summary : state.format === "docx" ? "구조·서식 편집마다 OOXML 참조 규칙(관계·스타일·번호·표 구조·자식 순서)으로 검사 — 원본에 없던 종류의 위반이면 그 편집을 되돌린다"
    : "구조·서식 편집마다 OWPML(KS X 6101) 2024 스키마·참조 규칙으로 검사 — 원본에 없던 종류의 위반이면 그 편집을 되돌린다";
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

async function structOp(path, body) {
  // 구조·서식 편집 한 번: 대기 중 글 반영을 끝내고 → 서버 편집(OWPML 검사) → 바뀐 최상위 블록만 바꿔 끼운다
  if (state.busy || !state.id) return null;
  const epoch = state.epoch;
  state.busy = true;
  document.body.classList.add("busy-edit");
  refreshToolbar();
  try {
    await flushAll();
    if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 먼저 다시 반영해야 합니다 — 「고친 문단」 탭", true); return null; }
    const r = await api(`/api/docs/${state.id}/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return null;
    state.localRev += 1;
    state.structRev = state.localRev;
    applyEditState(r);
    applyTops(r);
    if (r.outline) outlineApply(r.outline);
    if (r.focus) focusAt(r.focus);
    if (r.owpml && r.owpml.status === "warn") toast(`${STD()}: ${r.owpml.summary}`);
    return r;
  } catch (e) {
    if (epoch !== state.epoch) return null;
    if (e.status === 422 && e.body && e.body.owpml) state.owpml = { status: "fail", summary: e.message };
    toast(e.message, true);
    return null;
  } finally {
    if (epoch === state.epoch) {
      state.busy = false;
      document.body.classList.remove("busy-edit");
      refreshToolbar();
      refreshSaveState();
    }
  }
}

function applyEditState(r) {
  if (r.rev != null) state.serverRev = r.rev;
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
}

function applyTops(r) {
  // 서버가 준 「바뀐 최상위 블록」으로 쪽 흐름의 그 항목들만 바꾼다(문단 나누기면 문단 둘, 칸 안 편집이면 그 표를 품은 본문 문단의 블록 전부)
  const drop = new Set(r.tops.drop);
  const hit = [];
  state.flow.forEach((it, k) => { if ((it.kind === "table" ? [it.id] : it.ids).some((i) => drop.has(i))) hit.push(k); });
  walkParas(r.tops.blocks, (b) => { state.texts[b.id] = b.text || ""; state.byId.set(b.id, b); if (!(b.id in state.original)) state.original[b.id] = ""; });
  // 최상위 블록 목록(state.blocks)도 같은 자리에서 바꿔 끼운다 — 표 모듈(tables.js xlBlocks·「표」 탭)이 이걸 읽으므로 표 행·열 편집 뒤 옛 구조를 보지 않게(astra P1, 2026-11-10)
  const at = state.blocks.map((b, i) => (drop.has(b.id) ? i : -1)).filter((i) => i >= 0);
  if (at.length) state.blocks.splice(at[0], at[at.length - 1] - at[0] + 1, ...r.tops.blocks);
  if (!hit.length) { reloadDoc(); return; }
  const a = hit[0], z = hit[hit.length - 1];
  const items = buildFlow(r.tops.blocks.map((b) => [b, state.flow[a].sec]));
  if (items.length) items[0].pageStart = state.flow[a].pageStart;
  state.flow.splice(a, z - a + 1, ...items);
  paginate();
  updateEdits();
  renderSummary(state.verify || {});
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
  const d = await api(`/api/docs/${state.id}`);
  applyDoc(d);
}

function applyDoc(d) {
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
  await flushAll();
  if (state.localRev > state.structRev && !confirm("실행 취소하면 마지막 구조·서식 편집 뒤에 고친 글도 함께 되돌아갑니다. 계속할까요?")) return;
  const epoch = state.epoch;
  state.busy = true;
  refreshToolbar();
  try {
    const d = await api(`/api/docs/${state.id}/undo`, { method: "POST" });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    state.structRev = state.localRev;
    applyDoc(d);
    toast(d.pristine ? "실행 취소 — 원본과 바이트가 같은 상태로 돌아왔습니다" : "실행 취소했습니다");
  } catch (e) { toast(e.message, true); }
  finally { state.busy = false; refreshToolbar(); refreshSaveState(); }
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
  $("scroller").addEventListener("scroll", ctxClose, { passive: true });
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
  $("editNav").hidden = !n;
  $("editCount").textContent = `고친 문단 ${n}개`;
  $("verifyBtn").disabled = !canVerify();
  state.editsDirty = true;
  if (!$("paneEdits").hidden) drawEdits();
  refreshSaveState();
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
  const gone = Object.values(state.kinds).filter((k) => k === "removed").length;
  if (gone) list.append(el("li", "note-line", `지운 문단 ${gone}개(문단 합치기·표 행/열 지우기) — 되돌리려면 위 막대의 「실행 취소」`));
  if (!ids.length && !state.failed.size && !gone) {
    list.append(el("li", "none", "아직 고친 문단이 없습니다. 문서에서 글을 누르고 고치면 여기에 모입니다. 원래 글로 되돌리면 원본 XML(줄 배치 포함)까지 되돌려 목록에서 빠집니다."));
  }
  const KINDS = { text: "글", format: "모양", struct: "나누기·합치기", new: "새 문단" };
  for (const id of ids) {
    const kind = state.kinds[id] || "text";
    const li = el("li", "edit-item");
    const go = el("button", "edit-go");
    go.type = "button";
    go.setAttribute("aria-label", `고친 문단으로 이동: ${short(state.texts[id], 40)}`);
    go.append(diffView(state.original[id] || "", state.texts[id] || ""));
    go.onclick = () => scrollToBlock(id, true);
    li.append(go);
    const row = el("div", "row");
    const pg = pagesOf(id);
    row.append(el("span", "kind", KINDS[kind] || kind));
    row.append(el("span", null, pg ? pg.label : ""));
    if (state.unrestored.has(id)) row.append(el("span", "warn-text", `글은 원래대로 · 줄 배치는 ${APP()}가 다시 계산`));
    row.append(el("span", "spacer"));
    if (kind === "text" || kind === "format") {
      const rv = el("button", "btn sm", "원본으로 되돌리기");
      rv.type = "button";
      rv.onclick = () => revert(id);
      row.append(rv);
    } else {
      row.append(el("span", "muted", "실행 취소로 되돌림"));
    }
    li.append(row);
    list.append(li);
  }
}

function diffView(a, b) {
  // 앞뒤 같은 부분을 빼고 바뀐 곳만 <del>/<ins> — 줄 바꿈 ↵, 탭 ⇥ 표시
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  let j = 0;
  while (j < a.length - i && j < b.length - i && a[a.length - 1 - j] === b[b.length - 1 - j]) j++;
  const mark = (s) => s.replaceAll(LS, "↵\n").replaceAll("\t", "⇥\t");
  const box = el("div", "diff");
  const pre = a.slice(0, i), post = a.slice(a.length - j);
  const CTX = 40;
  box.append(el("span", "ctx", (pre.length > CTX ? "…" : "") + mark(pre.slice(-CTX))));
  if (a.length - j > i) box.append(el("del", null, mark(a.slice(i, a.length - j))));
  if (b.length - j > i) box.append(el("ins", null, mark(b.slice(i, b.length - j))));
  box.append(el("span", "ctx", mark(post.slice(0, CTX)) + (post.length > CTX ? "…" : "")));
  return box;
}

function orderedEdits() {
  return [...document.querySelectorAll(".para.edited")].map((p) => p.dataset.id).filter((id) => state.edited.has(id));
}

async function revert(id) {
  const p = paraEl(id);
  if (!p) return;
  const epoch = state.epoch;
  clearTimeout(state.timers.get(id));
  state.timers.delete(id);
  await (state.chains.get(id) || Promise.resolve());
  try {
    const r = await api(`/api/docs/${state.id}/blocks/${id}/revert`, { method: "POST" });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    applyServer(id, r);
    state.kinds = r.kinds || state.kinds;
    if (r.restored && state.byIdOrig.has(id)) state.byId.set(id, state.byIdOrig.get(id)); // 모양까지 원본 — 처음 연 블록으로 다시 그린다
    const b = state.byId.get(id);
    const again = r.restored ? renderPara(b) : renderPara(b, r.text);
    again.classList.toggle("edited", r.edited);
    p.replaceChildren(...again.childNodes); // 같은 요소를 둔다 — 쪽 상자 흐름(state.flow)이 이 노드를 가리킨다
    p.className = again.className;
    updateEdits();
    markUnmapped();
    renderSummary(state.verify || {});
    toast(r.restored ? "원본 문단(글·줄 배치)으로 되돌렸습니다" : `글은 되돌렸으나 원본 XML 로는 못 되돌렸습니다 — 줄 배치는 ${APP()}가 다시 계산합니다`, !r.restored);
  } catch (e) { toast(e.message, true); }
}

function scrollToBlock(id, focus = false) {
  const p = paraEl(id);
  if (!p) return;
  p.scrollIntoView({ block: "center", behavior: "smooth" });
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

// ---------------------------------------------------------------- 검증
async function poll() {
  if (state.polling || !state.id) return;
  state.polling = true;
  const id = state.id, epoch = state.epoch;
  state.pollError = null;
  try {
    for (;;) {
      const v = await api(`/api/docs/${id}/verify`);
      if (epoch !== state.epoch) break;
      renderVerify(v);
      if (!Object.values(v).some((j) => j && j.running)) break;
      await new Promise((r) => setTimeout(r, 1000));
    }
  } catch (e) {
    if (epoch === state.epoch) { state.pollError = e; renderSummary(state.verify || {}); }
  } finally { state.polling = false; }
}

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
  if (v.mapping && !state.mapping) {
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
  if ((v.import || v.edit) && !Object.values(v).some((j) => j && j.running)) logTouched(); // 검증 끝 — 기록 탭에 새 줄
}

function stageSummary(box, sum, job) {
  if (!job) { sum.textContent = ""; return; }
  const c = { ok: 0, warn: 0, fail: 0, skip: 0 };
  job.steps.forEach((s) => { if (s.status in c) c[s.status] += 1; });
  sum.textContent = job.running ? "진행 중" : [c.ok && `통과 ${c.ok}`, c.warn && `주의 ${c.warn}`, c.fail && `실패 ${c.fail}`, c.skip && `건너뜀 ${c.skip}`].filter(Boolean).join(" · ");
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
  if (box) box.scrollIntoView({ block: "start", behavior: "smooth" });
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
  return miniTable(`레터 꼴별 PDF 실측 ${patterns.length}개 보기`, ["자리", "꼴", "문단", "앞 공백", "레터 뒤", "둘째 줄 / 서식"],
    patterns.map((p) => ({
      cells: [PLACE[p.place] || p.place, p.full, p.count, mm(p.leadMm), mm(p.gapMm),
        `${p.line2Count ? mm(p.line2Mm) : "—"} / ${mm(p.hangMm) ?? "—"}${p.line2Count ? ` (${p.line2Count})` : ""}`],
      title: `${p.full} — ${APP()} PDF 에서 잰 가운데 값(mm). 둘째 줄 = 둘째 줄이 첫 줄보다 들어간 폭 / 서식 = 문단 서식의 내어쓰기(괄호 = 잰 문단 수)`,
    })),
    "mm · 꼴: _n = 반각 공백 n칸, ＿n = 전각, ⇥n = 탭, N = 숫자, list: = 자동 번호·글머리", [5]);
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
  input.max = count;
  input.value = state.pdfPage;
  $("pdfOf").textContent = `/ ${count}${state.unit}`;
  $("pdfPrev").disabled = state.pdfPage <= 1;
  $("pdfNext").disabled = state.pdfPage >= count;
  img.hidden = false;
  img.alt = `${which === "original" ? "원본" : "수정본"} PDF ${state.pdfPage}${state.unit}`;
  img.src = `/api/docs/${state.id}/pdf/${which}/${state.pdfPage}.png?v=${which === "edited" ? state.pdfVer : 0}`;
}

const TOOL_TABS = ["Verify", "Edits", "Pdf", "Log", "Heads", "Tables", "Div", "Compare"]; // Tables = 표 모듈(tables.js, spec_헤딩_추출 ② §10)
const TOOL_INFO = {
  Verify: ["검증", "파일·출력", "원본을 읽고 저장한 결과와 출력파일을 확인합니다."],
  Edits: ["고친 문단", "변경 내용", "고친 부분을 찾아보고 원래 내용과 비교하거나 되돌립니다."],
  Pdf: ["PDF", "출력 미리보기", "원본과 수정본의 실제 출력 모양을 확인합니다. 문단을 누르면 해당 쪽으로 이동합니다."],
  Log: ["기록", "작업 이력", "편집·추출·검증·내려받기를 시간순으로 확인합니다."],
  Heads: ["헤딩 추출", "구조 분석", "문서와 나란히 보며 라벨, 템플릿과 판단 근거를 확인합니다."],
  Tables: ["표", "표 관리", "문서의 표만 따로 — 소속 헤딩·계산식·엑셀식 보기·표 지침을 다룹니다."],
  Div: ["구분 기준", "양식 구성", "단계·차년도·기관에 맞춰 되풀이되는 자리를 구성합니다."],
  Compare: ["문서 비교", "병합 전 확인", "문서별 라벨과 템플릿을 나란히 비교하고 확인한 문서를 표시합니다."]
};

// ---- 도구 탭 띠 접기 (spec_hwpx_웹편집 ② §9 — 2026-11-10 사용자 "이건 한줄로 … 접었다 폈다 할 수 있게")
// 접으면 지금 탭 이름만 남고(그 이름을 누르면 다시 편다 — bind), 이 브라우저에 기억(localStorage nfm.navFold — 못 쓰면 기억만 안 함).
const NAV_FOLD_KEY = "nfm.navFold";
function navFolded() { return $("workspaceNav").classList.contains("folded"); }
function navFold(on, remember = true) {
  $("workspaceNav").classList.toggle("folded", on);
  const b = $("navFold");
  b.setAttribute("aria-expanded", !on);
  b.title = on ? "도구 탭 펴기" : "도구 탭 접기";
  b.textContent = on ? "펴기 ▾" : "접기 ▴";
  if (remember) { try { localStorage.setItem(NAV_FOLD_KEY, on ? "1" : "0"); } catch { /* 기억만 안 함 */ } }
}
function navFoldLoad() { try { return localStorage.getItem(NAV_FOLD_KEY) === "1"; } catch { return false; } }

function showTab(name) {
  if (!TOOL_INFO[name] || $(`tab${name}`).hidden) return;
  if (!["Heads", "Div", "Tables"].includes(name) && !headsColClose()) return;
  const workspace = document.querySelector(".workspace");
  workspace.classList.toggle("compare-mode", name === "Compare");
  for (const n of TOOL_TABS) {
    const on = n === name, tab = $(`tab${n}`);
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", on);
    tab.tabIndex = on ? 0 : -1;
    $(`pane${n}`).hidden = !on;
  }
  const [title, tag, description] = TOOL_INFO[name];
  $("toolTitle").textContent = title;
  $("toolTag").textContent = tag;
  $("toolDescription").textContent = description;
  $("toolSource").textContent = name === "Compare" ? "여러 문서 · 저장된 분석 결과" : state.name;
  $("toolSource").title = name === "Compare" ? "작업 목록에서 비교할 문서를 선택하세요" : state.name;
  setPanel(true);
  colsApply();
  if (name === "Pdf") showPdf();
  if (name === "Edits" && state.editsDirty) drawEdits();
  if (name === "Log") drawLog();
  if (name === "Heads") headsShow();
  if (name === "Div") divShow(); // 구분 기준(spec_구분_기준 ② §8)
  if (name === "Tables" && typeof tablesShow === "function") tablesShow(); // 표 모듈(tables.js, spec_헤딩_추출 ② §10)
  if (name === "Compare" && typeof compareShow === "function") compareShow();
}

function setPanel(open) {
  $("panel").hidden = !open || !state.id;
  $("panelBtn").setAttribute("aria-expanded", open);
  $("panelBtn").hidden = !state.id;
  $("panelBtn").textContent = open ? "도구 닫기" : "문서 도구";
  if (!open) document.querySelector(".workspace").classList.remove("compare-mode");
  else if ($("tabCompare").getAttribute("aria-selected") === "true") document.querySelector(".workspace").classList.add("compare-mode");
}

// 열 폭 조절 — 패널(3열)·헤딩 열(2열, #headsDlg). 왼쪽 가장자리를 끌기 · ←/→ 20px(Shift 80px) · Home/End 최소·최대 · 두 번 누르면 기본 폭(CSS 변수).
// 고른 폭은 이 브라우저에 기억(localStorage — 못 쓰면 기억만 안 함). 문서 보기는 늘 VIEW_KEEP px 남긴다 — 다른 열이 보이면 그 폭도 뺀 나머지가 최대라
// 창을 줄이면 패널 → 헤딩 열 차례로 줄어들고, 헤딩 열을 열고 닫을 때도 colsApply() 로 다시 맞춘다.
const VIEW_KEEP = 360;
const colSizers = []; // makeColSizer 로 만든 열들
const colsApply = () => { for (const c of colSizers) c.apply(); };

function makeColSizer({ box, handle, cssVar, key, min, fallback }) {
  const c = { w: null }; // w = 사용자가 고른 폭(px) — null = 기본(CSS 변수)
  const h = $(handle);
  const others = () => colSizers.reduce((s, o) => (o === c ? s : s + $(o.box).getBoundingClientRect().width), 0); // 숨은 열은 0
  c.box = box;
  c.max = () => Math.max(min, document.querySelector(".workspace").clientWidth - VIEW_KEEP - others());
  c.clamp = (w) => Math.round(Math.min(c.max(), Math.max(min, w)));
  c.apply = () => {
    const root = document.documentElement.style;
    root.removeProperty(cssVar); // 기본값(CSS 변수 — 창 폭 미디어 쿼리로 달라짐)을 읽으려고 먼저 지운다
    const def = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(cssVar)) || fallback;
    const now = c.clamp(c.w == null ? def : c.w); // 기본 폭도 문서 보기 몫 안으로(두 열이 다 보이면 기본값끼리도 넘칠 수 있다)
    if (now !== def) root.setProperty(cssVar, `${now}px`);
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
    body.append(fig(`원본 ${d.page}${u}`, `/api/docs/${state.id}/pdf/original/${d.page}.png?dpi=${dpi}`));
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
  $("doc").style.zoom = state.zoom;
  $("zoomVal").textContent = `${Math.round(state.zoom * 100)}%`;
  const w = mode === "width", h = mode === "height" || mode === "body";
  $("zoomFit").setAttribute("aria-pressed", w);
  $("zoomFit").classList.toggle("on", w);
  $("zoomHeight").setAttribute("aria-pressed", h);
  $("zoomHeight").classList.toggle("on", h);
  $("zoomHeight").textContent = mode === "body" ? "여백 빼고 맞춤" : "높이 맞춤";
}

function refit(align = false) {
  if (state.fit === "width") fitWidth();
  else if (state.fit) fitHeight(state.fit, align);
}

function keepCenter(fn) {
  // 단추로 배율을 바꿀 때 창 가운데 있던 자리를 그대로 둔다 — #doc 안은 배율만큼 커지고 스크롤 상자 padding 은 그대로
  const sc = $("scroller"), z0 = state.zoom, pad = parseFloat(getComputedStyle(sc).paddingTop) || 0;
  const y = sc.scrollTop + sc.clientHeight / 2 - pad;
  fn();
  sc.scrollTop = (y * state.zoom) / z0 - sc.clientHeight / 2 + pad;
}

function fitWidth() {
  const sheets = [...document.querySelectorAll(".sheet")];
  if (!sheets.length || $("scroller").hidden) return;
  $("doc").style.zoom = 1; // 확대 전 폭으로 잰다
  const widest = Math.max(...sheets.map((s) => s.offsetWidth));
  const need = state.twoUp ? widest * 2 + TWO_UP_GAP : widest; // 2쪽 보기 — 두 쪽과 사이 간격이 창 폭에
  const sc = $("scroller"), cs = getComputedStyle(sc);
  const avail = sc.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0) - 12; // 좌우 padding(템플릿 표시 여백 .gutter 포함) + 여유 12
  setZoom(Math.min(1.25, avail / need), "width");
}

const PX_PER_MM = 96 / 25.4;
const TWO_UP_GAP = 24; // 2쪽 보기 두 쪽 사이(px, 배율 전) — style.css .doc.two-up 의 column-gap 과 같아야 한다

function fitHeight(mode, align = false) {
  // 높이 맞춤 = 지금 보는 쪽(창 가운데 줄이 지나는 쪽)의 웹 쪽 상자가 창 높이에 다 들어가게 · 여백 빼고 맞춤 = 그 상자에서 위·아래 쪽 여백을 뺀 높이를 창 높이에(여백은 창 밖).
  // 쪽 높이는 웹에 그려진 상자(종이보다 작으면 종이) — 웹은 문단·표 행 안에서 쪽을 나누지 않고 표 행이 한글보다 높을 때가 있어 상자가 종이보다 길다
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
  try { localStorage.setItem(VIEW_KEY, JSON.stringify({ twoUp: state.twoUp, wheelFlip: state.wheelFlip, tool: state.tool })); } catch { /* 기억만 안 함 */ }
}

// ---- 도구 줄 한 줄 (spec_hwpx_웹편집 ② §2 「도구 줄」 — 2026-11-10 사용자 "2줄 중 상단의 줄을 … 체크 하면 그것만 하나의 줄에 보이게")
// 「페이지 보기·폰트 수정·문단 수정·테이블 수정」 단추 중 하나만 켜지고(.tool-modes), 그 묶음(.tool-set[data-tool-set])만 펼친다. 고른 묶음은 nfm.view 에 기억(기본 페이지 보기).
const TOOL_SETS = ["page", "font", "para", "table"];

function setToolSet(name) {
  state.tool = TOOL_SETS.includes(name) ? name : "page";
  const bar = $("docBar"), h0 = bar.offsetHeight;
  for (const s of bar.querySelectorAll(".tool-set")) s.hidden = s.dataset.toolSet !== state.tool;
  for (const s of bar.querySelectorAll("[data-tool-for]")) s.hidden = s.dataset.toolFor !== state.tool; // 묶음 밖에 둔 딸림 항목(키 안내)
  for (const b of document.querySelectorAll("#toolModes [data-tool]")) {
    const on = b.dataset.tool === state.tool;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", String(on));
  }
  viewPrefSave();
  if (state.id && !$("scroller").hidden && bar.offsetHeight !== h0) refit(); // 좁은 창에서 묶음에 따라 줄이 꺾이면 문서 보기 높이가 바뀐다 — 맞춤 배율 다시
}

function setTwoUp(on) {
  // 2쪽 보기 — #doc 을 두 열 격자로(style.css .two-up). 맞춤 배율은 다시 맞추고(폭 맞춤은 두 쪽 폭으로) 보던 쪽을 창 맨 위에 둔다
  state.twoUp = !!on;
  $("doc").classList.toggle("two-up", state.twoUp);
  const b = $("twoUp");
  b.setAttribute("aria-pressed", state.twoUp);
  b.classList.toggle("on", state.twoUp);
  viewPrefSave();
  const sc = $("scroller"), sheets = [...document.querySelectorAll(".sheet")];
  if (!state.id || sc.hidden || !sheets.length) return;
  const cur = viewSheet(sc, sheets);
  refit();
  sc.scrollTop += cur.getBoundingClientRect().top - sc.getBoundingClientRect().top - 24;
  if (heads.marks || heads.outline) tplMarksDraw(); // 2쪽 보기면 오른쪽 쪽의 템플릿 표시는 오른쪽 여백으로
}

function setWheelFlip(on) {
  state.wheelFlip = !!on;
  $("wheelFlip").checked = state.wheelFlip;
  viewPrefSave();
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
  else if (i - 1 >= 0) { const s = start(rows[i - 1]), e = end(rows[i - 1]); to = e - s > SLACK ? e : s; } // 앞 줄 — 창보다 길면 그 아래끝부터
  else to = 0;
  to = Math.max(0, Math.min(sc.scrollHeight - h, Math.round(to)));
  flip = { at: now, to };
  sc.scrollTo({ top: to, behavior: "smooth" });
}

function bindWheelFlip() {
  const sc = $("scroller");
  let acc = 0, lastEvt = 0, lastFlip = 0, locked = false;
  sc.addEventListener("wheel", (e) => {
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
    toast(r.headers.get("x-same-as-original") === "1" ? `「${name}」 — 원본과 바이트가 같은 파일입니다` : `「${name}」 내려받기를 요청했습니다(${fmtSize(blob.size)})`);
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
const H_KIND = { marker: "레터", label: "라벨", note: "안내(※)", footnote: "각주(*)", data: "값", placeholder: "자리표시", plain: "보통 글",
  empty: "빈 문단", object: "개체", toc: "목차", caption: "캡션" };
const H_AREA = { body: "본문", cell: "표 칸", box: "글상자", shape: "도형 글", caption: "캡션", header: "머리말", footer: "꼬리말", footnote: "각주", endnote: "미주" };
const H_VERDICT = { saved: "저장", rejected: "거절", kept: "그대로", unsure: "모름", duplicate: "중복" };
const H_STEP = { running: "run", ok: "ok", failed: "fail" };
const H_JOB = { running: "진행 중", done: "끝남", failed: "실패" };
const H_ROLE = { label: "라벨", title: "제목", note: "안내" };
const H_TPL = { main: "주 사슬", branch: "가지 템플릿", label: "라벨 템플릿", sub: "서브 템플릿", cell: "표 칸" };
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

async function headsStart(stage, useLlm) {
  if (!state.id) return;
  const id = state.id, epoch = state.epoch;
  await flushAll(); // 아직 반영 안 된 글부터 — 추출은 서버 문서를 읽는다
  if (epoch !== state.epoch) return;
  try {
    const job = await api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ stage, llm: useLlm }) });
    if (epoch !== state.epoch) return;
    heads.expect = job.started; // 이보다 앞선 작업의 늦은 응답은 건너뛴다
    headsRender({ ...(heads.view || { rev: state.serverRev, runs: [], stage1: null, stage2: null, stage3: null }), job });
  } catch (e) {
    if (epoch !== state.epoch) return;
    toast(e.status === 409 ? "헤딩 추출이 이미 돌고 있습니다 — 끝난 뒤 다시 누르세요" : `헤딩 추출을 시작하지 못했습니다: ${e.message}`, e.status !== 409);
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
    if (job && job.stage === k) box.append(headsJob(job));
  }
  headsMore1(r);
  headsMore2(r);
  headsMore3(r);
  headsResultsSummary(r);
  if (typeof tblMarksDraw === "function") tblMarksDraw(); // 표 식별 표지(소속)는 3단계 결과를 따라간다(spec ② §10)
}

const HEAD_VIEWS = ["Tree", "Labels", "Templates", "Tables", "Review", "Run"];
function headsResultView(name) {
  heads.resultView = name;
  for (const key of HEAD_VIEWS) {
    const on = name === key, b = $(`headsTab${key}`);
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
    $(`headsView${key}`).hidden = !on;
  }
}

function headsEmptyResult(target, title, message, stage) {
  const box = $(target);
  const empty = el("div", "result-empty");
  empty.append(el("strong", null, title), el("p", null, message));
  empty.append(hBtn("추출·설정 열기", () => headsResultView("Run"), { cls: "btn sm primary" }));
  if (stage) empty.append(el("span", "hnote", `${stage}단계 결과를 사용합니다.`));
  box.replaceChildren(empty);
}

function headsResultsSummary(r) {
  const renderKey = JSON.stringify([r.rev, [1, 2, 3].map((k) => {
    const s = r[`stage${k}`]; return s && [s.meta?.run, s.meta?.at, s.stale];
  }), r.job && [r.job.stage, r.job.status, r.job.started], !!heads.graph]);
  if (heads.summaryKey === renderKey) return;
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
  overview.append(metrics);
  const stages = [s1, s2, s3].filter(Boolean);
  const stale = stages.some((s) => s.stale) || (s1 && s2 && s2.meta?.stage1Run != null && s2.meta.stage1Run !== s1.meta?.run);
  const meta = el("div", "result-meta");
  if (job && job.status === "running") {
    meta.append(el("span", "analysis-state running", `${job.stage}단계 분석 중`), hBtn("진행 보기", () => headsResultView("Run")));
  } else if (job && job.status === "failed") {
    meta.append(el("span", "analysis-state stale", `${job.stage}단계 실행 실패`), hBtn("실행 내역 보기", () => headsResultView("Run")));
  } else {
    meta.append(el("span", `analysis-state${stale ? " stale" : ""}`, stale ? "이전 분석 · 다시 확인 필요" : stages.length ? "추출 결과" : "분석 준비"));
  }
  if (stages.length) meta.append(el("span", null, stages.map((s, i) => {
    const stage = s === s1 ? 1 : s === s2 ? 2 : 3;
    return `${stage}단계 #${s.meta?.run ?? "–"}`;
  }).join(" · ")));
  overview.append(meta);
  if (stale) overview.append(el("p", "hwarn", "문서 또는 라벨 분석이 바뀌었습니다. 이전 결과를 보고 있으므로 추출·설정에서 해당 단계를 다시 실행하세요."));

  if (!s2) {
    headsEmptyResult("heads2More", "문서 구조를 확인하세요", "문단 추출 후 2단계를 실행하면 헤딩을 따라 원문을 찾아볼 수 있습니다.", 2);
    headsEmptyResult("headsTemplatesResult", "아직 템플릿이 없습니다", "헤딩 그래프를 만들면 레터 사슬과 레벨별 서식을 여기서 확인할 수 있습니다.", 2);
  }
  const labels = $("headsLabelsResult");
  labels.textContent = "";
  if (!s1) headsEmptyResult("headsLabelsResult", "서식 라벨을 준비하고 있습니다", "1단계에서 문단의 서식을 묶어 라벨을 만듭니다.", 1);
  else {
    const top = el("div", "result-toolbar");
    top.append(el("strong", null, `서식 라벨 ${nf(sm.labels)}개`), hBtn("전체 라벨·문단 보기", () => headsLabels()));
    labels.append(top, el("p", "result-help", "라벨을 누르면 해당 문단 목록을 원문 옆에 엽니다. S 번호는 이 문서 안에서 사용하는 번호입니다."));
    const list = el("ul", "label-results");
    for (const l of s1.labelsTop || []) {
      const li = el("li"), b = hBtn("", () => headsParas({ fmt: l.id }), { cls: "label-result" });
      b.append(el("span", "label-code", l.id), el("span", "label-name", l.name), el("span", "label-count", `${nf(l.count)}문단`));
      li.append(b);
      list.append(li);
    }
    labels.append(list, el("p", "hnote", `문단 수가 많은 라벨 ${Math.min(30, (s1.labelsTop || []).length)}개 표시 · 전체 목록에서 모든 라벨을 확인할 수 있습니다.`));
  }
  const tables = $("headsTablesResult");
  tables.textContent = "";
  if (!s3) headsEmptyResult("headsTablesResult", "표의 헤더와 필드를 확인하세요", "3단계를 실행하면 표마다 칸의 역할과 서브 테이블을 확인할 수 있습니다.", 3);
  else {
    tables.append(el("p", "result-help", "표를 선택하면 원문 옆에 헤더·필드와 서브 테이블 경계를 표시합니다."));
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
  review.append(el("strong", null, "판단이 필요한 부분"), el("p", "result-help", "미판정·규칙 충돌·서식 조정의 근거를 원문과 대조하세요. 추출 완료는 사용자 확인 완료를 뜻하지 않습니다."));
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
      li.append(b, el("span", "hnote", n.reason || "판정되지 않아 초안을 유지한 문단"));
      list.append(li);
    }
    review.append(list);
    if (nodes.length > 50) review.append(el("p", "hnote", `미판정 ${nf(nodes.length)}개 중 앞 50개 표시`));
  }
}

function headsMarkStale() {
  if (!heads.view) return;
  let changed = false;
  for (const k of [1, 2, 3]) {
    const result = heads.view[`stage${k}`];
    if (result && !result.stale && result.meta?.rev !== state.serverRev) { result.stale = true; changed = true; }
  }
  if (changed) headsResultsSummary(heads.view);
}

function headsJob(job) {
  const box = el("details", "hjob");
  box.open = job.status !== "done";
  const secs = job.ended && job.started ? ` · ${(job.ended - job.started).toFixed(1)}s` : "";
  box.append(el("summary", `hjob-head ${job.status}`,
    `${job.stage}단계 · ${job.llm ? "LLM" : "스크립트만"} · ${H_JOB[job.status] || job.status}${job.run ? ` · 실행 ${job.run}번` : ""}${secs}`));
  const ol = el("ol", "steps brief");
  for (const s of job.steps || []) {
    const cls = H_STEP[s.status] || s.status;
    const li = el("li", `step ${cls}`);
    li.append(el("span", "st", ICON[cls] || ""), el("span", "ttl", s.name), el("span", "sec", s.status === "running" ? "진행 중" : `${s.seconds}s`),
      el("div", "det", s.msg || ""));
    ol.append(li);
  }
  box.append(ol);
  if (job.error && !(job.steps || []).some((s) => s.status === "failed")) box.append(el("p", "hwarn fail", job.error));
  return box;
}

function headsCard1(r, busy) {
  const box = $("heads1"), s1 = r.stage1;
  box.textContent = "";
  const head = el("div", "hcard-head");
  head.append(el("b", null, "1단계 — 문단·규칙식·서식 라벨"));
  if (s1 && s1.meta) head.append(el("span", "muted", `실행 ${s1.meta.run ?? "–"} · ${fmtWhen(s1.meta.at)}`));
  box.append(head);
  let groups = 0;
  if (!s1) box.append(el("p", "hnote", busy ? "문단을 뽑는 중…" : "결과가 없습니다 — 「다시 추출」을 누르세요."));
  else {
    if (s1.stale) box.append(el("p", "hwarn", "문서가 바뀜 — 다시 추출하세요(이 결과는 고치기 전 문서 기준)"));
    const sm = s1.summary, dl = el("dl", "hdl");
    groups = (sm.unmatchedGroups || 0) + (sm.conflicts || 0);
    const row = (k, v, cls = null, title = "") => {
      dl.append(el("dt", null, k));
      const dd = el("dd", cls, v);
      if (title) dd.title = title;
      dl.append(dd);
    };
    row("문단", `레코드 ${nf(sm.paragraphs)} ${sm.check ? "=" : "≠"} XML ${nf(sm.xml)} ${sm.check ? "✓" : "✕"}`, sm.check ? "good" : "bad",
      "구역 XML 의 문단(hp:p) 수와 뽑은 레코드 수 — 표 칸·글상자·머리말·각주 안 문단까지 모두");
    row("서식 라벨", `${nf(sm.labels)}개 (정밀 서식 F ${nf(sm.formats)}개)`, null, "정밀 서식(F) = 원본 값 그대로의 문단·글자 모양 지문 · 서식 라벨 = 오차 기준으로 F 를 묶은 것");
    row("못 맞춤", sm.unmatchedGroups ? `${nf(sm.unmatchedGroups)}묶음 · ${nf(sm.unmatched)}문단` : "없음", sm.unmatchedGroups ? "warnc" : null,
      "보통 글로 판정됐지만 앞머리에 기호·짧은 토큰이 있는 문단");
    row("충돌", sm.conflicts ? `${nf(sm.conflicts)}묶음` : "없음", sm.conflicts ? "warnc" : null, "첫머리에 종류가 다른 규칙이 둘 이상 맞는 문단(먼저 온 규칙이 이김)");
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
    if (warns.length) box.append(el("p", "hnote", `경고 ${warns.length}개 — ${warns.slice(0, 2).map(String).join(" · ")}`));
  }
  const a1 = el("div", "hacts");
  a1.append(hBtn("다시 추출", () => headsStart(1, false), { disabled: busy, title: "스크립트로 1단계를 다시 뽑습니다(LLM 없음, 1~2 s)" }),
    hBtn("LLM 규칙 보강", () => headsLlmRules(), { disabled: busy || !groups,
      title: groups ? "못 맞춤·충돌 묶음을 LLM 에 보내 규칙식을 제안받고 검증을 통과한 것만 저장합니다(유료)" : "보강할 묶음(못 맞춤·충돌)이 없습니다" }));
  const a2 = el("div", "hacts");
  a2.append(hBtn("문단 목록", () => headsParas(), { disabled: !s1 }), hBtn("서식 라벨", () => headsLabels(), { disabled: !s1 }),
    hBtn("규칙", () => headsRules()), hBtn("지침", () => headsGuides()));
  box.append(a1, a2);
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
  if (!st || !confirm(`LLM 규칙 보강 — 못 맞춤 ${s1.summary.unmatchedGroups}묶음·충돌 ${s1.summary.conflicts}묶음을 ${llmName(st)} 에 보내 규칙식을 제안받고, `
    + "검증을 통과한 것만 후보 규칙으로 저장합니다.\n유료 호출입니다(보통 $0.2~0.3 · 40초 안팎). 계속할까요?")) return;
  headsStart(1, true);
}

async function headsLlmGraph() {
  const st = await headsLlmReady();
  if (!st || !confirm(`헤딩 그래프(LLM) — 유형 판정·본문 구간별 판정·서식 쌍 판정을 ${llmName(st)} 에 여러 번 묻습니다.\n`
    + "유료 호출입니다(연구개발계획서 양식 기준 약 4분 · $3 안팎). 계속할까요?")) return;
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
  const head = el("div", "hcard-head");
  head.append(el("b", null, "2단계 — 헤딩 그래프·템플릿"));
  if (s2 && s2.meta) {
    const run = (r.runs || []).find((x) => x.n === s2.meta.run);
    head.append(el("span", "muted", `실행 ${s2.meta.run ?? "–"} · ${run ? (run.llm ? "LLM · " : "스크립트만 · ") : ""}${fmtWhen(s2.meta.at)}`));
  }
  box.append(head);
  if (!s2) {
    box.append(el("p", "hnote", "1단계 결과로 헤딩 그래프를 만듭니다 — 유형마다 역할·템플릿·레벨을 정하고(LLM) 본문을 구간별로 다듬습니다. "
      + "「그래프(스크립트만)」은 LLM 없이 레터 스택(같은 레터 = 형제, 새 레터 = 자식)으로 몇 초."));
  } else {
    if (s2.stale) box.append(el("p", "hwarn", "문서가 바뀜 — 그래프를 다시 만드세요(이 결과는 고치기 전 문서 기준)"));
    const c = s2.counts || {}, lm = s2.llm || {};
    const stats = el("div", "hstats");
    const stat = (v, k, title = "") => {
      const s = el("span");
      s.append(el("b", null, nf(v)), ` ${k}`);
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
    if (lm.summary) box.append(el("p", "hsum", lm.summary));
    if (lm.error) box.append(el("p", "hwarn", `LLM 실패${lm.fallback ? " — 스크립트 대체 판정" : ""}: ${lm.error}`));
    else if (lm.fallback) box.append(el("p", "hnote", "LLM 없이 스크립트 대체 판정(같은 레터 = 형제, 새 레터 = 자식)"));
    if (lm.calls) {
      box.append(el("p", "hnote", `LLM 호출 ${lm.calls}번(실패 ${lm.failed}) · 구간 ${lm.sections}${lm.failedSections ? `(실패 ${lm.failedSections})` : ""}`
        + (lm.formatPairs != null ? ` · 서식 쌍 ${lm.formatPairs}` : "") + ` · ${lm.seconds}s · $${lm.costUsd}`));
    }
  }
  const acts = el("div", "hacts");
  acts.append(hBtn("헤딩 그래프(LLM)", () => headsLlmGraph(), { disabled: busy || !s1, cls: "btn sm primary", title: "유형·본문 구간·서식 쌍을 LLM 이 판정(유료, 수 분)" }),
    hBtn("그래프(스크립트만)", () => headsStart(2, false), { disabled: busy || !s1, title: "LLM 없이 레터 스택으로(몇 초)" }));
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
  if (heads.dlg === "templates") headsTplView(); // 열려 있던 템플릿 관계 보기(2열)도 새 그래프로
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

function headsTemplates(g) {
  const shapeOf = new Map((g.types || []).map((t) => [t.type, t.shape]));
  const ins = new Map();
  for (const i of g.instances || []) {
    const v = ins.get(i.template) || { n: 0, dev: 0 };
    v.n += 1;
    if (i.deviates) v.dev += 1;
    ins.set(i.template, v);
  }
  const tpls = g.templates || [];
  const v2 = (g.version || 1) >= 2; // 2026-11-09 템플릿 가지 규칙 — 템플릿 = 사슬 하나(앵커), id = 번호 N(표기 「TN」), 인스턴스는 id 로 가리킴
  const d = el("details", "more hblock");
  d.open = true;
  const sum = el("summary", null, `템플릿 ${tpls.length}개`);
  sum.title = v2 ? "번호 TN 은 문서 안 문단 표시 「TN L줄」 의 N — 주 사슬 T1 → 가지(문서 순 첫 등장) → 라벨 → 표 칸 차례. 템플릿 = 레터 사슬 하나(앵커 = scope:사슬), 같은 사슬은 어디에 매달려도 같은 TN(유형 번호 「유형 T28」 과는 다른 것 — 템플릿 표기엔 늘 L줄이 붙음)"
    : "번호 TN 은 문서 안 문단 표시 「TN L줄」 의 N — 개요템플릿 → 서브 템플릿 → 표 칸 차례";
  d.append(sum);
  const tools = el("div", "hacts");
  const tgText = () => (tplMarksOn() ? "문서 표시 끄기" : "문서에 표시");
  const tg = hBtn(tgText(), () => { tplMarksToggle(); tg.textContent = tgText(); tg.setAttribute("aria-pressed", tplMarksOn()); },
    { title: "문서의 문단마다 「T템플릿 L줄」 표시를 쪽 왼쪽 여백에 보입니다(이 브라우저에 기억) · 라벨 문단은 「T5 L1 [기관]」 처럼 라벨 식별자까지" });
  tg.setAttribute("aria-pressed", tplMarksOn());
  tools.append(tg, hBtn("템플릿 관계", () => headsTplView(), { title: "템플릿을 매달린 자리(부모 템플릿·레벨)로 이은 트리 — 2열에 열립니다. T번호를 누르면 레벨(줄)과 가지가 펼쳐짐" }),
    hBtn("다른 문서와 비교", () => showTab("Compare")), el("span", "muted", "TN = 이 문서의 템플릿 번호(쪽 왼쪽 여백의 「TN Lk」) · Lk = 템플릿 안 레벨 · 번호를 누르면 템플릿 관계"));
  d.append(tools);
  const ul = el("ul", "hlist");
  for (const t of tpls) {
    const li = el("li");
    const iv = ins.get(v2 ? t.id : t.name);
    const top = el("div", "hl-top");
    if (t.no) { // 「TN」 — 누르면 템플릿 관계 보기(2열)에서 그 템플릿을 펼친다
      const nb = el("button", "hb tplno", `T${t.no}`);
      nb.type = "button";
      nb.title = "템플릿 관계 보기(2열)에서 이 템플릿을 펼침";
      nb.onclick = () => headsTplView(t.id ?? t.no);
      top.append(nb, " ");
    }
    if (v2) {
      const chain = (t.chain || []).join(" › ");
      top.append(`${t.displayName || chain} · ${H_TPL[t.kind] || t.kind}${t.scope === "cell" ? "" : ""}`
        + (t.rootRole === "label" ? " · 뿌리 = 구분 라벨" : "") + (iv ? ` · 인스턴스 ${iv.n}${iv.dev ? `(편차 ${iv.dev})` : ""}` : ""));
      top.title = `앵커 ${t.anchor}` + ((t.where || []).length ? `\n매달린 부모: ${t.where.map((w) => `「${w.parent}」 ${w.count}`).join(" · ")}` : "");
    } else {
      top.append(`${t.name} · ${H_TPL[t.kind] || t.kind}${t.root ? ` · 뿌리 「${shapeOf.get(t.root) || t.root}」` : ""}`
        + (iv ? ` · 인스턴스 ${iv.n}${iv.dev ? `(편차 ${iv.dev})` : ""}` : ""));
    }
    li.append(top);
    const lines = el("ol", "hl-lines"); // 줄 = 레벨 — 문서 표시 「TN Lk」 의 k
    for (const s of t.slots || []) {
      const ty = s.types || [];
      const line = el("li");
      line.value = s.level;
      line.append(el("b", null, `L${s.level}`), ` 「${s.letter || (ty[0] || {}).shape || "?"}」${ty.length > 1 ? `+${ty.length - 1}` : ""} ×${nf(s.count)}`);
      if (s.format) line.append(el("span", "slot-format", `서식 ${s.format}`));
      line.title = `${s.level}번째 줄(레벨 ${s.level}): ${ty.map((y) => `${y.shape} ${y.count}`).join(", ")} · 대표 서식 ${s.format || "—"}`;
      lines.append(line);
    }
    li.append(lines.childElementCount ? lines : el("div", "hl-sub", "슬롯 없음"));
    const sample = (g.nodes || []).find((n) => ((t.no != null && n.tplNo === t.no) || (t.name && n.template === t.name) || (t.anchor && n.template === t.anchor)) && n.level === 1 && hasBlock(n.para));
    if (sample) li.append(hBtn(`원문 보기 · ${short(`${sample.letter || ""} ${sample.text || ""}`, 34)}`, () => headsGo(sample.para), { cls: "template-source" }));
    if (t.note) li.title = t.note;
    ul.append(li);
  }
  d.append(ul);
  return d;
}

// 문서 안 문단별 템플릿 표시 — 쪽 왼쪽 여백에 「TN Lk」(그래프 노드 → 문단; 구분 라벨 노드는 「TN L1 [기관]」 처럼 라벨 식별자까지). 문단 요소(contentEditable) 안에는
// 아무것도 넣지 않고 .sheet 에 절대 위치 표(.tpl-mark)를 얹는다 — 끌기 손잡이(.ol-grip, 쪽 바로 옆) 바깥쪽에 오른끝 맞춤, 쪽 배율과 무관하게 화면 크기 고정(zoom 1/z),
// 2쪽 보기의 오른쪽 쪽은 오른쪽 여백. 표시·손잡이가 있으면 스크롤 상자에 여백(.gutter)을 두고 맞춤 배율을 다시 잰다. paginate()·refit() 끝과 창 크기 바뀜 때 다시 그린다
// (spec_헤딩_추출 ② §7 화면 「문서 표시」). 표를 누르면 템플릿 관계 보기(2열)에서 그 템플릿을 펼친다.
const TPL_MARKS_KEY = "nfm.headsMarks";
const TPL_MARK_H = 17; // 표 한 줄 높이(화면 px — style.css .tpl-mark 15px + 테두리)
const tplRef = (no, name) => (no ? `T${no}` : String(name || "").slice(0, 12)); // 템플릿 표기 「TN」(번호 없는 옛 결과는 이름 앞부분) — 유형 번호 「T28」 과 달리 늘 L줄이 뒤따름
const tplLabelId = (x) => (x.key || "").trim() || "[라벨]"; // 구분 라벨의 식별자 = 정규 라벨 키 「[기관]」(A 호출 basis) — 값(「[한국선급]」)이 아니라 구분 기준
function tplMarksOn() { try { return localStorage.getItem(TPL_MARKS_KEY) !== "off"; } catch { return true; } }
function tplMarksToggle() {
  try { localStorage.setItem(TPL_MARKS_KEY, tplMarksOn() ? "off" : "on"); } catch { /* 기억만 안 함 */ }
  tplMarksDraw();
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
    if (!x.template || !x.level || !hasBlock(x.para) || (x.role !== "heading" && x.role !== "title" && x.role !== "label")) continue; // 라벨도 제 템플릿의 L1(가지 규칙)
    const t = tplName.get(x.template) || {};
    const no = x.tplNo || t.no;
    const lab = x.role === "label" ? tplLabelId(x) : "";
    const text = `${tplRef(no, x.template)} L${x.level}${lab ? ` ${lab}` : ""}`;
    const slot = (t.slots || []).find((s) => s.level === x.level);
    const title = `템플릿 ${tplRef(no, x.template)} ${x.template}(${H_TPL[t.kind] || t.kind || "?"}) · ${x.level}번째 줄(레벨 ${x.level})`
      + (slot ? ` 「${((slot.types || [])[0] || {}).shape || "?"}」 ×${nf(slot.count)}` : "")
      + (lab ? `\n구분 라벨 ${lab}${x.letter ? ` 「${oneLine(x.letter).slice(0, 30)}」` : ""}` : "") + (instOf.has(x.id) ? `\n${instOf.get(x.id)}` : "")
      + `\n${x.id} · 유형 ${x.type}${x.undecided ? " · 미판정" : ""}${x.changed ? " · LLM 변경" : ""}` + (no ? "\n누르면 템플릿 관계 보기" : "");
    const was = marks.get(x.para);
    if (was) { if (!was.text.includes(text)) { was.text += ` ${text}`; was.title += `\n—\n${title}`; } }
    else marks.set(x.para, { text, title, no, und: !!x.undecided, lbl: !!lab });
  }
  return marks;
}

function tplMarksDraw() {
  for (const e of document.querySelectorAll(".tpl-mark, .ol-grip")) e.remove();
  const marks = heads.marks && tplMarksOn() ? heads.marks : new Map();
  const sc = $("scroller");
  const on = !!(marks.size || heads.outline) && !sc.hidden && !$("doc").classList.contains("hide-pages");
  const two = on && state.twoUp;
  if (sc.classList.contains("gutter") !== on || sc.classList.contains("gutter-r") !== two) { // 왼쪽(2쪽 보기면 오른쪽도) 여백이 생기고 없어지면 맞춤 배율을 다시 잰다
    sc.classList.toggle("gutter", on);
    sc.classList.toggle("gutter-r", two);
    if (state.fit) refit();
  }
  if (!on) return;
  // 읽기 단계(쪽·문단 자리를 모두 먼저) → 쓰기 단계(표·손잡이 붙이기). 쪽마다 재고 붙이기를 번갈아 하면 쪽 수(65)만큼, 손잡이는 문단마다 강제 배치가 되어
  // 연구개발계획서 양식에서 28 s 멈췄다(2026-11-10 실측 → 나눠서 0.03 s, spec_owpml_편집 ③). 표·손잡이가 필요한 문단만 잰다(outlineLine 은 자료 조회뿐).
  const dr = $("doc").getBoundingClientRect();
  const jobs = [];
  for (const sheet of document.querySelectorAll("#doc .sheet")) {
    const sr = sheet.getBoundingClientRect();
    const z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1; // 쪽 배율 — 표·손잡이는 zoom 1/z 로 되돌려 화면 크기를 고정하고, 자리는 화면 px 로 둔다
    const right = two && sr.left + sr.width / 2 > dr.left + dr.width / 2; // 2쪽 보기의 오른쪽 쪽 — 왼쪽 쪽과 겹치지 않게 오른쪽 여백에
    const found = [], grips = [];
    for (const p of sheet.querySelectorAll(".para[data-id]")) {
      const m = marks.get(p.dataset.id);
      const ol = outlineLine(p);
      if (!m && !ol) continue;
      const top = p.getBoundingClientRect().top - sr.top;
      if (m) found.push({ top, m });
      if (ol && !p.closest("td")) grips.push({ p, ol, top }); // 본문 개요 줄마다 끌기 손잡이(쪽 바로 옆 왼쪽 여백)
    }
    jobs.push({ sheet, z, right, found, grips });
  }
  for (const { sheet, z, right, found, grips } of jobs) {
    const place = (e, top) => { e.style.zoom = String(1 / z); e.style.top = `${Math.round(top)}px`; sheet.append(e); };
    for (const g of grips) place(outlineGrip(g.p, g.ol, g.top), g.top);
    found.sort((a, b) => a.top - b.top);
    const rows = []; // 같은 높이(표 한 행의 칸들)·표 한 줄 높이(TPL_MARK_H) 안에 붙은 줄들은 한 표에 모아 겹치지 않게
    for (const f of found) {
      const r = rows[rows.length - 1];
      if (r && f.top - r.top < TPL_MARK_H) { r.items.push(f.m); r.und = r.und || f.m.und; r.lbl = r.lbl && f.m.lbl; }
      else rows.push({ top: f.top, items: [f.m], und: !!f.m.und, lbl: !!f.m.lbl });
    }
    for (const r of rows) {
      const s = el("span", "tpl-mark" + (r.und ? " und" : "") + (r.lbl ? " lbl" : "") + (right ? " r" : ""));
      const cnt = new Map(); // 같은 표기(표 한 행의 같은 템플릿·레벨 칸들)는 「T11 L2 ×2」 로 모은다
      for (const m of r.items) cnt.set(m.text, (cnt.get(m.text) || 0) + 1);
      const texts = [...cnt].map(([t, n]) => (n > 1 ? `${t} ×${n}` : t));
      s.textContent = texts.length > 3 ? `${texts.slice(0, 3).join(" · ")} +${texts.length - 3}` : texts.join(" · ");
      s.title = r.items.map((m) => m.title).join("\n═══\n");
      const no = (r.items.find((m) => m.no) || {}).no;
      if (no) { s.setAttribute("role", "button"); s.onclick = () => headsTplView(no); }
      place(s, r.top);
    }
  }
}
window.addEventListener("resize", () => { if (heads.marks || heads.outline) tplMarksDraw(); });

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

function headsTplView(focus = null) { // focus = 펼쳐 보일 템플릿 id(문서 표시·배지·번호를 눌렀을 때)
  const g = heads.graph;
  if (!g) { toast("헤딩 그래프(2단계)가 아직 없습니다 — 헤딩 추출 탭에서 그래프를 만들거나 읽은 뒤에 볼 수 있습니다"); return; }
  const rel = tplRel(g);
  const idOf = (t) => t.id ?? t.no;
  const tpls = [...rel.tpl.values()].sort((a, b) => (a.no || 0) - (b.no || 0));
  const { tools, body } = headsDlg("templates", "템플릿 관계", `템플릿 ${tpls.length}개 · 인스턴스 ${nf((g.instances || []).length)}`);
  tools.append(el("span", "muted", "「TN」 을 누르면 그 템플릿의 레벨(줄)과 줄마다 매달린 가지 템플릿이 펼쳐집니다 · 되돌이(제 조상과 같은 템플릿)는 표시만"), el("span", "spacer"),
    hBtn("모두 펼치기", () => { for (let k = 0; k < 30; k += 1) { const todo = [...body.querySelectorAll('.trel-row > .htog[aria-expanded="false"]')]; if (!todo.length) break; todo.forEach((b) => b.click()); } }),
    hBtn("모두 접기", () => body.querySelectorAll('.trel-row > .htog[aria-expanded="true"]').forEach((b) => b.click())));
  const placeName = (k) => (k === "root" ? "문서 최상위" : k === "cell" ? "표 칸" : k === "other" ? "템플릿 밖 노드" : `T${k.split("|")[0]} L${k.split("|")[1]}`);
  const levels = (t, id, path) => { // 펼친 몸통 — 매달린 자리 · 줄(레벨)마다 레터·수·그 줄의 가지 템플릿 · 인스턴스 목록(문서로)
    const box = el("div", "trel-body");
    const places = [...(rel.at.get(id) || new Map())].map(([k, n]) => `${placeName(k)} ×${nf(n)}`);
    if (places.length) box.append(el("p", "hnote trel-at", `매달린 자리: ${places.join(" · ")}`));
    const slots = t.slots || [];
    const kidLevels = [...rel.under.keys()].filter((k) => k.split("|")[0] === String(id)).map((k) => +k.split("|")[1]);
    const maxL = Math.max(slots.length ? Math.max(...slots.map((s) => s.level)) : 0, (t.chain || []).length, kidLevels.length ? Math.max(...kidLevels) : 0);
    const ol = el("ol", "trel-levels");
    for (let L = 1; L <= maxL; L += 1) {
      const s = slots.find((x) => x.level === L) || {};
      const li = el("li");
      li.value = L;
      const head = el("div", "trel-level");
      head.append(el("b", null, `L${L}`), ` 「${s.letter || (t.chain || [])[L - 1] || "?"}」`, el("span", "muted", s.count != null ? ` ×${nf(s.count)}` : " (이 문서엔 없음)"));
      head.title = `${L}번째 줄(레벨 ${L})${s.format ? ` · 대표 서식 ${s.format}` : ""}${s.rep ? ` · 대표 문단 ${s.rep}` : ""}`;
      li.append(head);
      const kids = rel.under.get(`${id}|${L}`);
      if (kids && kids.size) {
        const ul = el("ul", "trel");
        for (const [cid, n] of [...kids].sort((a, b) => ((rel.tpl.get(a[0]) || {}).no || 0) - ((rel.tpl.get(b[0]) || {}).no || 0))) ul.append(make(cid, path, n));
        li.append(ul);
      }
      ol.append(li);
    }
    box.append(maxL ? ol : el("p", "hnote", "줄(레벨) 정보 없음"));
    const ins = rel.inst.get(id) || [];
    if (ins.length) {
      const d = el("details", "trel-inst");
      d.append(el("summary", null, `인스턴스 ${nf(ins.length)} — 자리마다 문서로`));
      const ul = el("ul", "hlist");
      for (const i of ins.slice(0, 300)) {
        const li = el("li");
        const root = rel.node.get(i.root) || {};
        li.append(`${i.no ?? "?"}. `, headsParaLink(root.para || i.root, `${(root.letter || "").trim()} ${i.text || root.text || ""}`.trim() || "(빈 글)", 36, i.path ? `자리 ${i.path}` : ""));
        if (i.basis) li.append(" ", el("span", "hb div", i.basis));
        if (i.deviates) li.append(" ", el("span", "hb und", `빠진 줄 ${(i.missing || []).map((L) => `L${L}`).join("·") || "있음"}`));
        ul.append(li);
      }
      if (ins.length > 300) ul.append(el("li", "muted", `… ${nf(ins.length - 300)}개 더`));
      d.append(ul);
      box.append(d);
    }
    return box;
  };
  const make = (id, path, here = null) => { // 템플릿 한 줄 — [▸] [TN] 사슬 · 구실 · 인스턴스 수(여기 매달린 수)
    const t = rel.tpl.get(id) || { no: id, chain: [], kind: "?" };
    const li = el("li", `trel-node k-${t.kind || "x"}`);
    li.dataset.tpl = id;
    const row = el("div", "trel-row");
    const tog = el("button", "htog", "▸");
    tog.type = "button";
    tog.setAttribute("aria-expanded", "false");
    const num = el("button", "hb tplno", `T${t.no ?? id}`);
    num.type = "button";
    num.title = `앵커 ${t.anchor || t.name || "—"} · 누르면 레벨(줄) 펼치기·접기`;
    const ins = rel.inst.get(id) || [];
    const name = el("span", "trel-name", t.displayName || (t.chain || []).join(" › ") || t.name || "");
    const meta = el("span", "muted trel-meta", ` · ${H_TPL[t.kind] || t.kind || "?"}${t.rootRole === "label" ? " · 뿌리 = 구분 라벨" : ""} · 인스턴스 ${nf(ins.length)}${here != null && here !== ins.length ? `(여기 ${nf(here)})` : ""}`);
    row.append(tog, num, " ", name, meta);
    li.append(row);
    let sub = null;
    const cyc = path.includes(id);
    const open = (on) => {
      if (on && !sub) { sub = cyc ? el("p", "hnote trel-cyc", "되돌이 — 위에 펼친 제 조상과 같은 템플릿(레벨·가지는 거기서)") : levels(t, id, [...path, id]); li.append(sub); }
      if (sub) sub.hidden = !on;
      tog.textContent = on ? "▾" : "▸";
      tog.setAttribute("aria-expanded", on);
    };
    tog.onclick = num.onclick = () => open(!sub || sub.hidden);
    li._open = open;
    return li;
  };
  // 뿌리: 문서 최상위에 매달린 템플릿(주 사슬 먼저) · 표 칸 템플릿 · 그 밖(어느 트리에서도 닿지 않는 것)
  const attached = (t) => rel.at.get(idOf(t)) || new Map();
  const reach = new Set();
  const walk = (id) => { if (reach.has(id)) return; reach.add(id); for (const [k, kids] of rel.under) if (k.split("|")[0] === String(id)) for (const c of kids.keys()) walk(c); };
  const roots = tpls.filter((t) => t.kind === "main" || attached(t).has("root"));
  roots.forEach((t) => walk(idOf(t)));
  const cells = tpls.filter((t) => !reach.has(idOf(t)) && (t.kind === "cell" || t.scope === "cell" || attached(t).has("cell")));
  cells.forEach((t) => walk(idOf(t)));
  const rest = tpls.filter((t) => !reach.has(idOf(t)));
  const section = (title, list) => {
    if (!list.length) return;
    body.append(el("h3", null, title));
    const ul = el("ul", "trel");
    list.forEach((t) => ul.append(make(idOf(t), [])));
    body.append(ul);
  };
  section(`본문 — 문서 최상위에 매달린 템플릿 ${roots.length}`, roots);
  section(`표 칸 템플릿 ${cells.length}`, cells);
  section(`그 밖(매달린 자리를 모름) ${rest.length}`, rest);
  if (!tpls.length) body.append(el("p", "hnote pad", "템플릿이 없습니다."));
  if (focus != null) tplFocus(body, rel, focus);
}

function tplFocus(body, rel, id) { // 템플릿 id 까지 펼쳐 보이기 — 매달린 자리를 따라 뿌리까지 올라간 길(첫 자리만)을 위에서부터 연다
  const path = [id], seen = new Set([id]);
  for (let k = 0; k < 20; k += 1) {
    const at = rel.at.get(path[0]);
    const up = at ? [...at.keys()].find((w) => w.includes("|")) : null;
    if (!up) break;
    const pid = +up.split("|")[0];
    if (seen.has(pid)) break;
    seen.add(pid);
    path.unshift(pid);
  }
  let scope = body, li = null;
  for (const tid of path) {
    li = [...scope.querySelectorAll("li.trel-node")].find((x) => x.dataset.tpl === String(tid)) || null;
    if (!li) break;
    li._open(true);
    scope = li;
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
  return miniTable(`조정 ${all.length}건 — 조정 ${by("adjust")} · 다름 유지 ${by("keep")} · 미판정 ${by("undecided")}`
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
  if (!state.id || state.format !== "hwpx") { heads.outline = null; return; }
  const id = state.id, epoch = state.epoch;
  api(`/api/docs/${id}/outline`).then((o) => {
    if (epoch !== state.epoch) return;
    heads.outline = o && !o.off && o.lines ? o : null;
    outlineHint();
    tplMarksDraw();
  }).catch(() => { if (epoch === state.epoch && (refresh || !heads.outline)) { heads.outline = null; outlineHint(); tplMarksDraw(); } });
}
function outlineHint() {
  const h = $("editHint");
  if (!h) return;
  const on = !!heads.outline;
  h.textContent = on ? "개요 줄: Enter 하위 줄 · Alt+Enter 같은 레벨 트리 · Alt+↑/↓ 레벨(블록이면 모두) · 손잡이 끌기 옮김 · 빈 레터 줄 Backspace 지움 · Shift+Enter 줄 바꿈 · Ctrl+B/I/U"
    : "Enter 나누기 · Shift+Enter 줄 바꿈 · 맨 앞 Backspace·맨 끝 Delete 합치기 · Ctrl+B/I/U";
  h.title = on ? "헤딩 추출 2단계가 매긴 개요 줄(쪽 왼쪽 여백의 「TN Lk」)에서는 Enter 가 바로 아래 하위 레벨 줄을, Alt+Enter 가 부분 트리 끝 뒤에 같은 레벨의 템플릿 뼈대(그 레벨부터 마지막 레벨까지)를 만듭니다. "
    + "Alt+↑/↓ 는 그 줄(여러 문단을 블록으로 잡으면 걸친 개요 줄 모두)의 개요 레벨을 한 단계 올리고 내립니다(자식은 안 따라감, 하나라도 못 바꾸면 전부 거절). "
    + "왼쪽 여백의 손잡이(⋮⋮)를 같은 템플릿·같은 레벨 줄에 끌어 놓으면 부분 트리째 옮깁니다. 글 없는 레터 줄에서 Backspace 는 그 줄을 지웁니다. 개요 줄이 아닌 문단은 종전과 같습니다."
    : "편집용 보기(출력 배치는 PDF 탭) · Enter 문단 나누기 · Shift+Enter 줄 바꿈 · 문단 맨 앞 Backspace·맨 끝 Delete 합치기 · Ctrl+B/I/U 글자 모양 · Esc 편집 끝 · 헤딩 추출 2단계를 돌리면 개요 편집 키가 켜집니다";
}
function outlineEmpty(p) { // 글 없는 레터 줄(라벨 제외) — Backspace 로 지울 수 있는 줄
  const ol = outlineLine(p);
  if (!ol || ol.role === "label") return false;
  const t = readText(p), i = t.indexOf(ol.letter);
  return i >= 0 && !t.slice(0, i).trim() && !t.slice(i + ol.letter.length).trim();
}
function outlineApply(o) { // 응답의 바뀐·새 줄·지운 줄을 오버레이에
  if (!heads.outline || !o) return;
  for (const [pid, line] of Object.entries(o.lines || {})) heads.outline.lines[pid] = line;
  for (const pid of o.removed || []) delete heads.outline.lines[pid];
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
  heads.dlg = kind;
  heads.seq += 1;
  if (kind !== "guides") heads.gEl = null;
  $("headsDlgTitle").textContent = title;
  $("headsDlgNote").textContent = note;
  for (const id of ["headsDlgTools", "headsDlgBody", "headsDlgFoot"]) $(id).textContent = "";
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
  col.hidden = true;
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
    tr.title = `${p.id} · 규칙 ${p.rule || "—"} · 앞 공백 ${p.leadSpaces ?? 0}칸${p.leadMm != null ? ` ${p.leadMm}mm` : ""}${p.blank ? " · 제목 없음(쓸 자리)" : ""}\n`
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
    tr.title = `대표 문단 ${l.sample || "—"} · 앞 공백 꼴 ${l.leadCode || "—"} · 레터 뒤 ${l.gapCode || "—"}${l.spacer ? " · 간격 장치(빈 문단)" : ""} · 누르면 문단 목록`;
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
  const head = el("div", "hcard-head");
  head.append(el("b", null, "3단계 — 표 구조(행헤더·열헤더·필드·서브 테이블)"));
  if (s3 && s3.meta) {
    const run = (r.runs || []).find((x) => x.n === s3.meta.run);
    head.append(el("span", "muted", `실행 ${s3.meta.run ?? "–"} · ${run ? (run.llm ? "LLM · " : "스크립트만 · ") : ""}${fmtWhen(s3.meta.at)}`));
  }
  box.append(head);
  if (!s3) {
    box.append(el("p", "hnote", "표마다 칸을 열헤더·행헤더·귀퉁이·필드(·제목·안내)로 나누고, 헤더 구조가 다시 시작하는 곳에서 서브 테이블로 가릅니다. "
      + "「표 구조(LLM)」은 칸의 값을 보고 판정(유료), 「스크립트만」은 음영·굵게·값 꼴로 초안만(1초 안팎)."));
  } else {
    if (s3.stale) box.append(el("p", "hwarn", "문서가 바뀜 — 표 구조를 다시 만드세요(이 결과는 고치기 전 문서 기준)"));
    const c = s3.counts || {}, ro = c.roles || {}, lm = s3.llm || {};
    const stats = el("div", "hstats");
    const stat = (v, k, title = "") => {
      const s = el("span");
      s.append(el("b", null, nf(v)), ` ${k}`);
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
    if (lm.summary) box.append(el("p", "hsum", lm.summary));
    if (lm.error) box.append(el("p", "hwarn", `LLM 실패${lm.fallback ? " — 초안 그대로" : ""}: ${lm.error}`));
    else if (lm.requested && !lm.calls) box.append(el("p", "hnote", "LLM 에 보낼 표가 없습니다(모두 1~3칸) — 초안 그대로"));
    if (lm.calls) box.append(el("p", "hnote", `LLM 호출 ${lm.calls}번(실패 ${lm.failed}) · 보낸 표 ${lm.sent}(건너뜀 ${lm.skipped}) · ${lm.seconds}s · $${lm.costUsd}`));
  }
  const acts = el("div", "hacts");
  acts.append(hBtn("표 구조(LLM)", () => headsLlmTables(), { disabled: busy || !s1, cls: "btn sm primary", title: "표 묶음마다 서브 테이블·헤더 행/열·칸 역할을 LLM 이 칸의 값을 보고 판정(유료, 수 분)" }),
    hBtn("표 구조(스크립트만)", () => headsStart(3, false), { disabled: busy || !s1, title: "LLM 없이 음영·굵게·값 꼴로 초안만(1초 안팎)" }),
    hBtn("표 보기", () => headsTables(), { disabled: !s3, title: "표 목록과 칸 역할 격자를 문서 옆 2열에" }),
    hBtn(typeof tblMarksOn !== "function" || tblMarksOn() ? "표 도구 끄기" : "표 도구 표시", () => { if (typeof tblMarksToggle === "function") tblMarksToggle(); },
      { title: "문서의 표마다 위 오른쪽 표지 — 표 id · 소속 헤딩/라벨 · ⊞ 엑셀식 보기 · ✎ 표 지침" }));
  box.append(acts);
}

async function headsLlmTables() {
  const st = await headsLlmReady();
  if (!st || !confirm(`표 구조(LLM) — 표를 묶음(칸 500개 안팎)마다 ${llmName(st)} 에 보내 서브 테이블·헤더 행/열·칸 역할을 판정받습니다.\n`
    + "유료 호출입니다(연구개발계획서 양식 기준 10여 번 · 수 분). 계속할까요?")) return;
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
  tools.append(lab, legend);
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
    if (o.division) own.append(el("span", "hb div", `구분 라벨 ${o.division.text}`));
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
}
headsBind();

// ---------------------------------------------------------------- 연결
function bind() {
  const input = $("fileInput");
  $("openBtn").onclick = $("pickBtn").onclick = () => input.click();
  input.onchange = () => { openFile(input.files[0]); input.value = ""; };
  $("downloadBtn").onclick = download;
  $("verifyBtn").onclick = startEditVerify;
  $("panelBtn").onclick = () => setPanel($("panel").hidden);
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
  for (const b of document.querySelectorAll("#toolModes [data-tool]")) b.onclick = () => setToolSet(b.dataset.tool); // 도구 줄 묶음 고르기(한 줄)
  setToolSet(state.tool);
  bindWheelFlip();
  $("prevEdit").onclick = () => stepEdit(-1);
  $("nextEdit").onclick = () => stepEdit(1);
  $("showPages").onchange = (e) => { $("doc").classList.toggle("hide-pages", !e.target.checked); tplMarksDraw(); }; // 쪽 표시를 끄면 템플릿 표시·여백도 함께
  $("doc").addEventListener("click", (e) => { if (e.target.closest(".sheet-label")) e.stopPropagation(); });
  const tabs = TOOL_TABS;
  tabs.forEach((n) => {
    const t = $(`tab${n}`);
    t.onclick = () => { if (navFolded()) navFold(false); showTab(n); }; // 접힌 띠에 남은 탭 이름을 누르면 편다
    t.onkeydown = (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d && !["Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const shown = tabs.filter((x) => !$(`tab${x}`).hidden); // 작업 저장이 꺼지면 「기록」 탭은 숨김
      const nx = e.key === "Home" ? shown[0] : e.key === "End" ? shown[shown.length - 1] : shown[(shown.indexOf(n) + d + shown.length) % shown.length];
      showTab(nx);
      $(`tab${nx}`).focus();
    };
  });
  $("navFold").onclick = () => navFold(!navFolded());
  navFold(navFoldLoad(), false); // 기억한 접힘 상태로(문서 전이라 띠는 아직 숨김)
  $("worksBtn").onclick = async () => { await loadWorks(); $("worksDlg").showModal(); };
  $("recentAll").onclick = () => $("worksBtn").click();
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
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && state.id) { e.preventDefault(); download(); }
  });
  const drop = $("drop");
  window.addEventListener("dragover", (e) => { e.preventDefault(); if (!heads.drag) drop.classList.add("over"); });
  window.addEventListener("dragleave", (e) => { if (!e.relatedTarget) drop.classList.remove("over"); });
  window.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (heads.drag) return; const f = e.dataTransfer.files[0]; if (f) openFile(f); });
  window.addEventListener("beforeunload", (e) => { if (hasUnsaved()) { e.preventDefault(); e.returnValue = ""; } });
  new ResizeObserver(() => keepCenter(() => refit())).observe($("scroller")); // 창·패널 크기가 바뀌어 다시 맞춰도 보던 자리 그대로
  bindEditing();
  bindOutlineDrag();
  bindToolbar();
}

bind();
init();

// ---------------------------------------------------------------- 구분 기준(spec_구분_기준 ② §8) — 3열 탭 「구분 기준」(프로파일·값·저장한 기준·적용 상태) + 2열 「바꿀 자리」(headsDlg kind "divisions")
const DV_STATUS = { applied: "맞춤", already: "이미 맞음", excluded: "제외", unsupported: "지원 안 됨", unresolved: "미해결" };
const DV_EXTRA = { outside: "연구개발기관 외 기관", overseas: "국외기관", entrust: "위탁연구개발기관" };
const divFresh = () => ({ view: null, values: null, plan: null, result: null, busy: false, dirty: false, filter: "all", skip: new Set(), showDrop: true, seq: 0,
  ui: { advanced: false, presets: false, presetId: "" },
  marks: { data: null, index: null, loading: false, seq: 0, err: null, llm: false, llmLast: null, missing: false, missingLast: null } }); // 문서 표시·추가한 자리(spec_구분_기준 ② §11) · 빠진 자리 검토(§13)
let dv = divFresh();

function divReset() { // 문서를 열거나 닫을 때(load·closeDoc)
  dv = divFresh();
  $("tabDiv").hidden = !state.id;
  $("divBox").textContent = "";
  divMarksDraw(); // 옛 문서의 구분 기준 표시 지움(② §11)
}

const divDefault = () => ({ stages: [1], orgs: { lead: "", joint: [], nonprofit: [false] } });
const divTotalYears = (v) => (v.stages || []).reduce((s, n) => s + (Number(n) || 0), 0);

function divValues() { // 서버에 보낼 값(빈 선택 항목은 뺀다)
  const v = dv.values || divDefault();
  const orgs = { lead: v.orgs.lead || "", joint: [...(v.orgs.joint || [])], nonprofit: [...(v.orgs.nonprofit || [])] };
  for (const k of Object.keys(DV_EXTRA)) if ((v.orgs[k] || []).length) orgs[k] = [...v.orgs[k]];
  const out = { stages: v.stages.map((n) => Number(n) || 1), orgs };
  if (v.period && (v.period.start || v.period.end)) out.period = { start: v.period.start || "", end: v.period.end || "" };
  if ((v.subs || []).length) out.subs = [...v.subs];
  if (v.current && v.current > 1) out.current = Math.min(v.current, divTotalYears(v));
  return out;
}

async function divShow() {
  if (!state.id) return;
  const id = state.id, epoch = state.epoch, seq = ++dv.seq;
  let r;
  try { r = await api(`/api/docs/${id}/divisions`); }
  catch (e) {
    if (epoch !== state.epoch) return;
    $("divBox").textContent = "";
    $("divBox").append(el("p", "hwarn fail", `구분 기준 상태를 읽지 못했습니다: ${e.message}`), hBtn("다시 읽기", () => divShow()));
    return;
  }
  if (epoch !== state.epoch || seq !== dv.seq) return;
  dv.view = r;
  if (divMarksOn()) divMembersLoad(); // 문서 표시가 켜져 있으면 편집 차례가 바뀐 자료를 다시(② §11)
  if (!dv.values) dv.values = r.settings ? structuredClone(r.settings.values) : (r.applied ? structuredClone(r.applied.values) : divDefault());
  divRender();
}

function divRender() {
  const box = $("divBox"), r = dv.view;
  box.textContent = "";
  if (!r) return;
  const v = dv.values, ok = r.profile.supported;
  v.orgs.joint ||= [];
  v.orgs.nonprofit ||= [];
  v.period ||= { start: "", end: "" };
  box.setAttribute("aria-busy", String(dv.busy));

  box.append(divMarksBar()); // 맨 위: 문서 표시 보기/감추기 · 범례 · 추가한 자리 · LLM 재검토(② §11 — 2026-11-10 사용자)
  const profile = el("section", "dv-profile");
  const profileText = el("div", "dv-profile-copy");
  const profileTitle = el("div", "dv-profile-title");
  profileTitle.append(el("span", "dv-tag" + (ok ? " is-ready" : " is-warning"), ok ? "지원 양식" : "양식 확인 필요"),
    el("strong", null, r.profile.form || "인식된 양식 없음"));
  profileText.append(profileTitle, el("p", "dv-caption", ok ? r.profile.name : "지원 양식: " + (r.profile.supportedForms || []).join(", ")));
  profile.title = ok ? "프로파일 " + r.profile.id + " v" + r.profile.version : "";
  const read = hBtn("문서에서 읽기", () => divRead(), { cls: "btn dv-read", disabled: dv.busy || !r.profile.form,
    title: "문서의 단계·기관 정보를 읽어 입력칸에 채웁니다. 읽히지 않은 값은 유지합니다." });
  profile.append(profileText, read);
  box.append(profile);
  if (!ok) box.append(el("p", "dv-notice", "이 양식은 구분 기준 자동 반영을 지원하지 않습니다." + (state.format === "docx" ? "" : " 헤딩 추출에서 문서 구조를 확인할 수 있습니다.")));

  const config = el("fieldset", "dv-config");
  config.disabled = dv.busy;
  const sectionHead = (number, title, note, badgeId) => {
    const head = el("div", "dv-section-head");
    const copy = el("div", "dv-section-copy");
    copy.append(el("h3", null, title), el("p", "dv-caption", note));
    head.append(el("span", "dv-step", number), copy);
    if (badgeId) { const badge = el("span", "dv-count"); badge.id = badgeId; head.append(badge); }
    return head;
  };
  const stages = el("section", "dv-card");
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
  orgs.append(sectionHead("2", "기관 구성", "참여 기관과 비영리 여부를 입력하세요.", "divOrgCount"));
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
      v.orgs.joint.splice(index, 0, ""); v.orgs.nonprofit.splice(index + 1, 0, false); divTouched(); divRender();
      $("divBox").querySelectorAll(".dv-org-field input")[index + 1]?.focus();
    };
    label.append(inp);
    const lab = el("label", "dv-nonprofit"), cb = el("input"); cb.type = "checkbox"; cb.checked = !!v.orgs.nonprofit[index];
    cb.setAttribute("aria-label", role + " 비영리");
    cb.onchange = () => { v.orgs.nonprofit[index] = cb.checked; divTouched(); };
    lab.append(cb, "비영리"); lab.title = "비영리기관 현황에 포함하고 기업 현황에서는 제외합니다.";
    row.append(label, lab);
    if (index > 0) row.append(hBtn("×", () => {
      v.orgs.joint.splice(index - 1, 1); v.orgs.nonprofit.splice(index, 1); divTouched(); divRender();
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
  orgs.append(el("p", "dv-caption dv-hint", "이름을 쓰고 Enter 를 치면 바로 아래에 공동기관이 추가됩니다. 이름을 비우면 ‘주관기관(미입력)’, ‘참여기관1’처럼 표시됩니다."));
  config.append(orgs);

  const disclosure = (key, title, note) => {
    const detail = el("details", "dv-disclosure"); detail.open = dv.ui[key]; detail.dataset.divDisclosure = key;
    detail.ontoggle = () => { if (detail.isConnected) dv.ui[key] = detail.open; };
    const summary = el("summary");
    summary.append(el("strong", null, title), el("span", "dv-caption", note), el("span", "dv-chevron", "⌄"));
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
  const currentLabel = el("label", "dv-field"); currentLabel.append(el("span", null, "당해 차년도"));
  const current = el("select"); current.id = "divCurrentYear"; current.setAttribute("aria-label", "당해 차년도");
  current.onchange = () => { v.current = Number(current.value); divTouched(); };
  currentLabel.append(current, el("small", "dv-caption", "신청·협약 대상 연도입니다. 전체 차년도 순서로 선택하세요."));
  extra.append(currentLabel);
  for (const [key, name] of Object.entries({ ...DV_EXTRA, subs: "세부과제 주관기관" })) {
    const lab = el("label", "dv-field"); lab.append(el("span", null, name));
    const inp = el("input"); inp.type = "text"; inp.placeholder = "기관 이름을 쉼표로 구분"; inp.setAttribute("aria-label", name);
    inp.value = (key === "subs" ? (v.subs || []) : (v.orgs[key] || [])).join(", ");
    inp.oninput = () => {
      const names = inp.value.split(",").map(s => s.trim()).filter(Boolean);
      if (key === "subs") v.subs = names; else v.orgs[key] = names;
      divTouched();
    };
    lab.append(inp, el("small", "dv-caption", key === "subs" ? "비워 두면 세부과제 자리를 유지합니다." : "비워 두면 해당 기관 자리를 삭제하는 계획을 만듭니다."));
    extra.append(lab);
  }
  more.append(extra); config.append(more);

  const presets = disclosure("presets", "저장한 기준", (r.presets || []).length + "개 · 자주 쓰는 설정 불러오기");
  const presetBody = el("div", "dv-preset-body"), presetRow = el("div", "dv-preset-row");
  const sel = el("select"); sel.setAttribute("aria-label", "저장한 구분 기준");
  sel.append(new Option((r.presets || []).length ? "불러올 기준 선택" : "아직 저장한 기준이 없습니다", ""));
  for (const p of r.presets || []) sel.append(new Option(p.name + " · " + p.values.stages.join("+") + "년 · 공동 " + p.values.orgs.joint.length, p.id));
  sel.value = dv.ui.presetId;
  const load = hBtn("불러오기", () => {
    const p = (r.presets || []).find(x => x.id === sel.value); if (!p) return;
    dv.values = structuredClone(p.values); divTouched(); divRender(); toast("「" + p.name + "」을 불러왔습니다. 변경 계획을 확인하세요.");
  }, { disabled: !sel.value });
  const remove = hBtn("삭제", () => divPresetDelete(sel.value), { cls: "btn dv-delete", disabled: !sel.value, title: "선택한 저장 기준 삭제" });
  sel.onchange = () => { dv.ui.presetId = sel.value; load.disabled = remove.disabled = !sel.value; };
  presetRow.append(sel, load);
  const presetActions = el("div", "dv-preset-actions");
  presetActions.append(hBtn("현재 설정 저장…", () => divPresetSave(sel.value)), remove);
  presetBody.append(presetRow, presetActions); presets.append(presetBody); config.append(presets);
  config.querySelectorAll(".dv-remove").forEach(button => button.setAttribute("aria-label", button.title));
  box.append(config);

  const applied = el("section", "dv-applied"); applied.id = "divAppliedState"; applied.setAttribute("aria-live", "polite");
  box.append(applied);
  const review = el("div", "dv-review-bar");
  const reviewText = el("div", "dv-review-copy"), totals = el("strong"); totals.id = "divReviewSummary";
  reviewText.append(totals, el("span", null, "바뀔 자리와 지워질 내용을 먼저 확인하세요."));
  const reviewActions = el("div", "dv-review-actions");
  const planBtn = hBtn(dv.busy ? (state.busy ? "문서에 반영 중…" : "변경 계획 계산 중…") : "변경 계획 보기", () => divPlan(), {
    cls: "btn primary dv-plan-button", disabled: !ok || dv.busy,
    title: "변경할 자리와 지워질 글을 미리 확인합니다. 확인 후 별도로 반영할 수 있습니다."
  }); planBtn.id = "divPlanButton";
  reviewActions.append(planBtn);
  if (dv.plan) {
    const reopen = hBtn("마지막 계획 열기", () => divList(), { disabled: dv.busy }); reopen.id = "divReopenPlan"; reviewActions.append(reopen);
  }
  review.append(reviewText, reviewActions); box.append(review);
  divRefreshDerived();
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
  if (current.options.length !== max) {
    current.textContent = "";
    for (let year = 1; year <= max; year++) current.append(new Option(year + "차년도", year));
  }
  current.value = String(Math.min(v.current || 1, max));
  $("divReviewSummary").textContent = v.stages.length + "단계 · 전체 " + total + "년 · 기관 " + (v.orgs.joint.length + 1) + "곳";
  $("divPlanButton").disabled = !dv.view.profile.supported || dv.busy || total > 20;
  if (!dv.plan) $("divReopenPlan")?.remove();
  divRenderApplied();
}

function divRenderApplied() {
  const target = $("divAppliedState"); if (!target || !dv.view) return;
  target.textContent = "";
  const a = dv.view.applied;
  const head = el("div", "dv-applied-head");
  head.append(el("h3", null, "문서 반영 상태"));
  if (!a) {
    head.append(el("span", "dv-tag", "아직 미반영"));
    target.append(head, el("p", "dv-caption", "기준을 설정한 뒤 변경 계획을 확인하고 문서에 반영하세요."));
  } else {
    const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object"
      ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
    const same = JSON.stringify(canonical(a.values)) === JSON.stringify(canonical(divValuesNormalized()));
    const edited = a.rev !== state.serverRev;
    const issues = (a.summary?.unresolved || 0) + (a.summary?.unsupported || 0) + (a.summary?.excluded || 0);
    head.append(el("span", "dv-tag" + (!same || edited || issues ? " is-warning" : " is-ready"), !same ? "입력값 변경" : edited ? "반영 후 문서 수정" : issues ? "반영 결과 확인 필요" : "마지막 반영값과 같음"));
    target.append(head, el("p", "dv-applied-values", a.values.stages.length + "단계 · 전체 " + divTotalYears(a.values) + "년 · 주관 " + (a.values.orgs.lead || "미입력") + " · 공동 " + a.values.orgs.joint.length + "곳"),
      el("p", "dv-caption", "마지막 반영 " + fmtWhen(a.at) + (edited ? " · 이후 문서가 수정되어 새 계획으로 확인이 필요합니다." : !same ? " · 현재 입력값은 아직 반영하지 않았습니다." : " · 현재 입력값이 마지막 반영 기록과 일치합니다.")));
    if (a.summary) target.append(divSummary(a.summary));
    if (state.undo) target.append(hBtn("↶ 마지막 구조 편집 실행 취소", () => divUndo(), { cls: "btn dv-undo", disabled: dv.busy,
      title: "마지막 구조 편집 직전으로 되돌립니다. 그 뒤 고친 글도 함께 돌아갑니다." }));
  }
  const p = dv.view.plan;
  if (p) target.append(el("p", "dv-plan-note", dv.dirty ? "입력값이 바뀌었습니다. 변경 계획을 다시 확인하세요." :
    p.baseRev !== state.serverRev ? "이전 계획 이후 문서가 수정되었습니다. 변경 계획을 다시 확인하세요." :
    "마지막 계획 " + fmtWhen(p.createdAt) + (dv.plan ? " · 검토할 수 있습니다." : " · 현재 입력값으로 다시 확인하세요.")));
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
  divRefreshDerived();
  if (hadPlan && heads.dlg === "divisions") {
    const foot = $("headsDlgFoot"); foot.textContent = "";
    foot.append(el("span", "hd-msg note", "입력값이 바뀌어 이전 계획을 반영할 수 없습니다. 변경 계획을 다시 확인하세요."),
      hBtn("다시 계획", () => divPlan(), { cls: "btn sm primary", disabled: dv.busy }), hBtn("닫기", () => headsColClose()));
  }
}

async function divUndo() { // 실행 취소(마지막 구조 편집 = 보통 이 반영) 뒤 계획·결과를 버리고 3열·2열을 새로
  const epoch = state.epoch;
  await undoStruct();
  if (epoch !== state.epoch) return;
  dv.plan = null;
  dv.result = null;
  if (heads.dlg === "divisions") headsColClose();
  divShow();
}

async function divRead() {
  if (!state.id) return;
  const epoch = state.epoch;
  try {
    const r = await api(`/api/docs/${state.id}/divisions/read`);
    if (epoch !== state.epoch) return;
    const got = r.read || {}, v = dv.values, names = [];
    if (got.stages) { v.stages = got.stages; names.push("단계·차년도"); }
    if (got.period) { v.period = got.period; names.push("사업기간"); }
    if (got.current) { v.current = got.current; names.push("당해 차년도"); }
    if (got.subs && got.subs.length) { v.subs = got.subs; names.push("세부과제"); }
    const o = got.orgs || {};
    if (o.lead != null) { v.orgs.lead = o.lead; names.push("주관"); }
    if (o.joint) { v.orgs.joint = o.joint; names.push(`공동 ${o.joint.length}곳`); }
    if (o.nonprofit) { v.orgs.nonprofit = o.nonprofit; names.push("비영리"); }
    for (const k of Object.keys(DV_EXTRA)) if (o[k] && o[k].length) { v.orgs[k] = o[k]; names.push(`${DV_EXTRA[k]} ${o[k].length}곳`); }
    divTouched();
    divRender();
    toast(names.length ? `문서에서 읽음: ${names.join(" · ")} — 확인한 뒤 「계획 보기」` : "문서에서 읽을 수 있는 값이 없습니다(자리표시뿐)");
  } catch (e) { if (epoch === state.epoch) toast(`문서에서 읽지 못했습니다: ${e.message}`, true); }
}

async function divPresetSave(pid) {
  const cur = (dv.view.presets || []).find((x) => x.id === pid);
  const name = prompt("저장할 이름(같은 이름이면 덮어씁니다)", cur ? cur.name : "");
  if (name == null || !name.trim()) return;
  const same = (dv.view.presets || []).find((x) => x.name === name.trim());
  try {
    await api(`/api/divisions/presets/${same ? same.id : "new"}`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ name: name.trim(), values: divValues() }) });
    toast(`「${name.trim()}」 저장`);
    divShow();
  } catch (e) { toast(`저장하지 못했습니다: ${e.message}`, true); }
}

async function divPresetDelete(pid) {
  const p = (dv.view.presets || []).find((x) => x.id === pid);
  if (!p) { toast("지울 저장 항목을 고르세요"); return; }
  if (!confirm(`「${p.name}」 을 지울까요?`)) return;
  try { await api(`/api/divisions/presets/${pid}`, { method: "DELETE" }); toast(`「${p.name}」 지움`); divShow(); }
  catch (e) { toast(`지우지 못했습니다: ${e.message}`, true); }
}

async function divPlan() {
  if (!state.id || dv.busy) return;
  const id = state.id, epoch = state.epoch;
  await flushAll(); // 아직 반영 안 된 글부터 — 계획은 서버 문서 차례(rev)에 묶인다
  if (epoch !== state.epoch) return;
  dv.busy = true;
  divRender();
  try {
    const r = await api(`/api/docs/${id}/divisions/plan`, { method: "POST", headers: H_JSON, body: JSON.stringify({ values: divValues(), skip: [...dv.skip] }) });
    if (epoch !== state.epoch) return;
    dv.plan = r;
    dv.dirty = false;
    dv.result = null;
    dv.busy = false; // 2열 발의 「반영」 단추가 바로 켜지게(finally 보다 먼저)
    const s = r.summary;
    toast(`계획 — 맞출 자리 ${s.applied} · 이미 맞음 ${s.already} · 지원 안 됨 ${s.unsupported} · 미해결 ${s.unresolved} (${s.seconds}s)`, s.unresolved > 0);
    divList();
  } catch (e) {
    if (epoch !== state.epoch) return;
    toast(`계획을 세우지 못했습니다: ${e.message}`, true);
  } finally {
    dv.busy = false;
    if (epoch === state.epoch) divShow();
  }
}

function divGo(c) { // 후보 자리의 첫 라벨(문단 또는 칸)로 — 칸이면 그 칸의 첫 문단
  const id = c.key === "period" ? null : c.key;
  if (!id) return;
  if (paraEl(id)) { scrollToBlock(id, true); return; }
  const cell = document.querySelector(`#doc td[data-cell="${CSS.escape(id)}"], #doc [data-id="${CSS.escape(id)}"]`); // 표 칸은 td[data-cell](renderTable)
  const p = cell && cell.querySelector(".para");
  if (p) { scrollToBlock(p.dataset.id, true); return; }
  toast("그 자리가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)");
}

function divList() {
  const plan = dv.plan;
  if (!plan) { toast("먼저 「계획 보기」를 누르세요"); return; }
  const stale = plan.baseRev !== state.serverRev;
  const res = dv.result;
  const { tools, body, foot } = headsDlg("divisions", res ? "구분 기준 — 반영 결과" : "구분 기준 — 바꿀 자리",
    `${res ? `편집 차례 ${res.rev} 에 반영` : `편집 차례 ${plan.baseRev} 기준 계획`} · 누르면 문서의 그 자리로`);
  const statusOf = (c) => (res && res.status[c.key]) || c.status;
  const filt = el("span", "dv-filter");
  for (const [k, label] of [["all", "모두"], ["work", "바꿀 자리"], ["issue", "지원 안 됨·미해결"], ["already", "이미 맞음"]]) {
    filt.append(hBtn(label, () => { dv.filter = k; divList(); }, { cls: "btn sm" + (dv.filter === k ? " on" : "") }));
  }
  tools.append(filt);
  const cbL = el("label", "hd-field"); const cb = el("input"); cb.type = "checkbox"; cb.checked = dv.showDrop; cb.onchange = () => { dv.showDrop = cb.checked; divList(); };
  cbL.append(cb, "지워질 글 보기"); tools.append(cbL);
  tools.append(divSummary(plan.summary));
  const [tbl, tb] = hTable(["", "상태", "구분", "종류", "라벨(처음 3)", "수→목표", "자리"]);
  const rows = plan.candidates.filter((c) => {
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
      x.onclick = (ev) => { ev.stopPropagation(); if (x.checked) dv.skip.add(c.key); else dv.skip.delete(c.key); divFoot(foot, plan, stale); };
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
    tr.onclick = () => { for (const x of tb.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); divGo(c); };
    tr.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); } };
    tb.append(tr);
  }
  if (!rows.length) { const tr = el("tr"); hCell(tr, "해당하는 자리가 없습니다"); tb.append(tr); }
  body.append(tbl);
  if (plan.deleted && plan.deleted.length && !res) {
    const det = el("details", "dv-detail"); det.style.margin = "8px 14px 14px";
    det.append(el("summary", null, `지워질 글 문단 ${plan.summary.deleted}개 전체 보기${plan.deleted.length < plan.summary.deleted ? ` (처음 ${plan.deleted.length}개)` : ""}`));
    const ul = el("ul", "dv-drop");
    for (const d of plan.deleted) { const li = el("li"); li.textContent = d.text; li.title = d.id; ul.append(li); }
    det.append(ul);
    body.append(det);
  }
  divFoot(foot, plan, stale);
}

function divFoot(foot, plan, stale) {
  foot.textContent = "";
  if (dv.plan !== plan) {
    foot.append(el("span", "hd-msg note", "입력값이 바뀌어 이전 계획을 반영할 수 없습니다. 변경 계획을 다시 확인하세요."),
      hBtn("다시 계획", () => divPlan(), { cls: "btn sm primary", disabled: dv.busy }), hBtn("닫기", () => headsColClose()));
    return;
  }
  const res = dv.result;
  if (res) {
    foot.append(el("span", "muted", `반영 끝 — 편집 차례 ${res.rev}. 사본은 본뜬 항목의 글을 그대로 가져왔으니 고쳐 쓰세요.`));
    if (res.unresolved && res.unresolved.length) foot.append(el("span", "hd-msg", `미해결 ${res.unresolved.length}곳 — 손으로 맞추세요`));
    foot.append(hBtn("↶ 이번 반영 취소", () => divUndo(), { title: "실행 취소 — 그 뒤 고친 글도 함께 돌아감" }), hBtn("닫기", () => headsColClose()));
    return;
  }
  const skipChanged = JSON.stringify([...dv.skip].sort()) !== JSON.stringify([...(plan.skip || [])].sort());
  const s = plan.summary;
  if (stale) foot.append(el("span", "hd-msg", "문서가 바뀌어 이 계획은 반영할 수 없습니다 — 다시 계획하세요"));
  else if (skipChanged) foot.append(el("span", "hd-msg note", "뺄 자리를 바꿨습니다 — 다시 계획해야 반영됩니다"));
  else foot.append(el("span", "muted", s.applied ? `맞출 자리 ${s.applied}곳 · 추가 ${s.added} · 지움 ${s.removed} · 지워지는 글 문단 ${s.deleted}` : "맞출 자리가 없습니다(이미 맞음)"));
  if (stale || skipChanged) foot.append(hBtn("다시 계획", () => divPlan(), { cls: "btn sm primary", disabled: dv.busy }));
  else foot.append(hBtn("반영", () => divApply(), { cls: "btn sm primary", disabled: dv.busy || !s.applied, title: "계획대로 문서를 고칩니다 — 한 번에, 실패하면 전부 되돌림. 반영 뒤 「실행 취소」로 되돌릴 수 있음" }));
  foot.append(hBtn("닫기", () => headsColClose()));
}

async function divApply() {
  const plan = dv.plan;
  if (!plan || dv.busy || !state.id) return;
  const s = plan.summary;
  if (!confirm(`구분 기준을 반영할까요?\n\n맞출 자리 ${s.applied}곳 — 항목 추가 ${s.added} · 지움 ${s.removed} · 글 바꿈 ${s.changes}\n지워지는 글 문단 ${s.deleted}개(2열 「지워질 글 보기」에서 확인)\n\n한 번에 반영하고 표준 검사에 걸리면 전부 되돌립니다. 반영 뒤 「실행 취소」로 되돌릴 수 있습니다.`)) return;
  const id = state.id, epoch = state.epoch;
  await flushAll();
  if (epoch !== state.epoch) return;
  if (plan.baseRev !== state.serverRev) { toast("문서가 바뀌어 다시 계획해야 합니다", true); divList(); return; }
  dv.busy = true;
  state.busy = true;
  refreshToolbar();
  divRender();
  try {
    const r = await api(`/api/docs/${id}/divisions/apply`, { method: "POST", headers: H_JSON, body: JSON.stringify({ planId: plan.planId, expectRev: plan.baseRev }) });
    if (epoch !== state.epoch) return;
    if (r.nothing) { toast("할 일이 없습니다 — 이미 그 값에 맞습니다"); dv.plan = null; return; }
    applyEditState(r);
    dv.result = { rev: r.rev, unresolved: r.unresolved || [], status: Object.fromEntries((r.candidates || []).map((c) => [c.key, c.status])),
      message: Object.fromEntries((r.candidates || []).map((c) => [c.key, c.statusMessage])) };
    toast(`반영 — 추가 ${r.summary.added} · 지움 ${r.summary.removed} · 글 바꿈 ${r.summary.changes}${r.owpml ? ` · ${STD()} ${r.owpml.status === "ok" ? "통과" : r.owpml.summary}` : ""}`);
    await reloadDoc(); // 떨어진 자리 여러 곳이 바뀌어 부분 갱신 대신 문서를 다시 읽는다(spec_구분_기준 ② §4)
    if (epoch !== state.epoch) return;
    divList();
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (e.status === 409) { toast(`${e.message}`, true); dv.plan = null; }
    else if (e.status === 422) toast(`표준 검사에 걸려 되돌렸습니다: ${e.message}`, true);
    else toast(`반영하지 못했습니다: ${e.message}`, true);
  } finally {
    dv.busy = false;
    state.busy = false;
    refreshToolbar();
    if (epoch === state.epoch) divShow();
  }
}

// ---------------------------------------------------------------- 구분 기준 — 문서 표시 · 추가한 자리 · LLM 재검토(spec_구분_기준 ② §11, 2026-11-10 사용자)
// 문서 표시: GET …/divisions/members(계획 없이 find 만) → 문단마다 가장 안쪽 구분의 색(.dv-in[data-dv]), 라벨 문단은 .dv-lab, 추가한 자리는 .dv-hint(사용자)/.dv-hint-llm.
// 추가한 자리: 문서의 문단에서 오른쪽 단추 → 「구분 기준 자리로 추가…」(작은 떠 있는 입력 — 모달 아님) → POST …/divisions/hints. 2열 목록(kind "divisions-hints") · LLM 재검토.
const DV_MARKS_KEY = "nfm.divMarks";
const DV_DIM_RANK = { stage: 0, stageYear: 0, year: 1, sub: 2, org: 3 }; // 구분 순서(바깥 → 안, core.RANK) — 기타(사용자 이름)는 가장 안쪽
const DV_DIM_NAME = { stage: "단계", year: "차년도", stageYear: "단계-차년도", sub: "세부과제", org: "기관" };
function divMarksOn() { try { return localStorage.getItem(DV_MARKS_KEY) === "on"; } catch { return false; } }
function divMarksSet(on) { try { localStorage.setItem(DV_MARKS_KEY, on ? "on" : "off"); } catch { /* 기억만 안 함 */ } }

function divMarksBar() { // 탭 맨 위 줄 — 보기/감추기 · 범례(구분별 색·묶음 수) · 다시 읽기 · 추가한 자리 N · LLM 재검토
  const m = dv.marks, on = divMarksOn(), d = m.data;
  const bar = el("section", "dv-marks" + (on ? " on" : "")); bar.id = "divMarksBar";
  const head = el("div", "dv-marks-head");
  const copy = el("div", "dv-marks-copy");
  copy.append(el("strong", null, "문서 표시"));
  const tg = hBtn(on ? "감추기" : "보기", () => { divMarksSet(!on); if (!on) divMembersLoad(); else divMarksDraw(); divMarksBarRefresh(); },
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
      if (!byDim.size && !hints.length) leg.append(el("span", "dv-caption", "찾은 구분 기준 자리가 없습니다"));
      bar.append(leg);
      const stale = d.rev !== state.serverRev;
      if (stale) bar.append(el("p", "dv-caption dv-marks-note", "문서 변경됨 · 다시 읽기 필요"));
    }
  }
  const acts = el("div", "dv-marks-acts");
  if (on) acts.append(hBtn("다시 읽기", () => divMembersLoad(true), { disabled: m.loading, title: "지금 문서(편집 차례)로 자리를 다시 찾음" }));
  acts.append(hBtn(`추가한 자리 ${hints.length}`, () => divHintsList(), { title: "문서에서 표시한 라벨 문단 목록(2열) — 출처·구분·값·엔진 반영 여부·지우기" }));
  acts.append(hBtn(m.llm ? "LLM 재검토 중…" : "LLM 재검토", () => divLlmReview(), { cls: "btn sm primary", disabled: m.llm || !hints.length || dv.busy,
    title: hints.length ? "추가한 자리·묶음·후보 문단을 LLM 에 보내 형제 자리를 찾고 구분·값을 고칩니다(수십 초) — 결과는 추가한 자리 목록과 문서 표시에" : "먼저 문서에서 자리를 하나 이상 표시하세요" }));
  acts.append(hBtn(m.missing ? "빠진 자리 검토 중…" : m.missingLast ? `빠진 자리 후보 ${m.missingLast.missing.length}` : "빠진 자리 검토", () => divMissingList(),
    { title: "어느 묶음에도 안 든 표·문단 중 구분 기준 자리로 보이는 곳을 LLM 이 찾습니다 — 2열 목록에서 실행(판정만, 문서는 그대로)" })); // ② §13
  bar.append(acts);
  return bar;
}
function divMarksBarRefresh() { const old = document.getElementById("divMarksBar"); if (old) old.replaceWith(divMarksBar()); }

async function divMembersLoad(force = false) { // 표시 자료 읽기 — 같은 편집 차례면 다시 안 읽음
  if (!state.id) return;
  const m = dv.marks;
  if (m.loading) return;
  if (!force && m.data && m.data.rev === state.serverRev) { divMarksDraw(); divMarksBarRefresh(); return; }
  const id = state.id, epoch = state.epoch, seq = ++m.seq;
  m.loading = true; m.err = null; divMarksBarRefresh();
  try {
    const r = await api(`/api/docs/${id}/divisions/members`);
    if (epoch !== state.epoch || seq !== m.seq) return;
    m.data = r; m.index = divMembersIndex(r);
    if (dv.view) dv.view.hints = r.hints || [];
    divMarksDraw();
  } catch (e) { if (epoch === state.epoch && seq === m.seq) m.err = e.message; }
  finally { if (epoch === state.epoch && seq === m.seq) { m.loading = false; divMarksBarRefresh(); if (heads.dlg === "divisions-hints") divHintsList(); else if (heads.dlg === "divisions-missing") divMissingList(); } }
}

function divMembersIndex(r) { // 문단 id → {dim(가장 안쪽), lab, hint, lines[겉→안 소속 글]}
  const idx = new Map();
  const rank = (dim) => (dim in DV_DIM_RANK ? DV_DIM_RANK[dim] : 4);
  for (const g of r.groups || []) {
    for (const it of g.items || []) {
      const line = `${g.dimName} 「${it.value || "?"}」 — ${g.kindName}${g.where && g.where.table ? ` · 표 ${g.where.table}` : ""} · 항목 ${g.count}개${g.hinted ? " · 추가한 자리 꼴" : ""}${it.text ? ` · 라벨 「${it.text}」` : ""}`;
      const rk = rank(g.dim), sz = (it.paras || []).length;
      for (const pid of it.paras || []) {
        let e = idx.get(pid);
        if (!e) { e = { dim: g.dim, rank: -1, size: Infinity, lab: false, hint: null, lines: [] }; idx.set(pid, e); }
        e.lines.push({ rank: rk, line });
        if (rk > e.rank || (rk === e.rank && sz < e.size)) { e.rank = rk; e.size = sz; e.dim = g.dim; }
        if (pid === it.label) e.lab = true;
      }
    }
  }
  for (const h of r.hints || []) {
    if (!h.exists) continue;
    let e = idx.get(h.para);
    if (!e) { e = { dim: h.dim, rank: 4, size: 1, lab: true, hint: null, lines: [] }; idx.set(h.para, e); }
    e.lab = true; e.hint = h.by === "llm" ? "llm" : "user";
    e.lines.push({ rank: 9, line: `추가한 자리(${h.by === "llm" ? "LLM" : "사용자"}) — ${h.dimName || h.dim} 「${h.value || "?"}」${h.engine ? " · 묶음의 라벨" : " · 표시만(아직 묶음 아님)"}${h.reason ? ` · ${h.reason}` : ""}${h.note ? ` · 메모 ${h.note}` : ""}` });
  }
  for (const e of idx.values()) e.lines.sort((a, b) => a.rank - b.rank);
  return idx;
}

function divMarksDraw() { // 문서의 문단 요소에 표시 클래스 — paginate 끝·자료 바뀜·토글 때
  const doc = $("doc");
  if (!doc) return;
  for (const p of doc.querySelectorAll(".para.dv-in")) {
    p.classList.remove("dv-in", "dv-lab", "dv-hint", "dv-hint-llm"); delete p.dataset.dv;
    if (p.dataset.dvTitle) { p.removeAttribute("title"); delete p.dataset.dvTitle; }
  }
  const on = typeof dv !== "undefined" && divMarksOn() && dv.marks.data && dv.marks.index;
  doc.classList.toggle("dv-marks", !!on);
  if (!on) return;
  for (const p of doc.querySelectorAll(".para[data-id]")) {
    const e = dv.marks.index.get(p.dataset.id);
    if (!e) continue;
    p.classList.add("dv-in"); p.dataset.dv = e.dim in DV_DIM_NAME ? e.dim : "other";
    if (e.lab) p.classList.add("dv-lab");
    if (e.hint) p.classList.add(e.hint === "llm" ? "dv-hint-llm" : "dv-hint");
    if (!p.title) { p.title = "구분 기준 자리(겉 → 안)\n" + e.lines.map((x) => x.line).join("\n"); p.dataset.dvTitle = "1"; }
  }
}

// ---- 추가한 자리(hint) — 문서에서 오른쪽 단추
function divHintOf(pid) { const d = dv.marks.data; return ((d && d.hints) || (dv.view && dv.view.hints) || []).find((h) => h.para === pid) || null; }
function divCtxItems(e) { // 오른쪽 단추 메뉴 항목(앞에 구분선) — 표 칸 메뉴(tselContextMenu)와 문단 메뉴(divContextMenu) 공용
  const p = e.target.closest && e.target.closest(".para[data-id]");
  if (!p || !state.id) return [];
  const h = divHintOf(p.dataset.id);
  const items = [null, [h ? "구분 기준 자리 표시 고치기…" : "구분 기준 자리로 추가…", "", () => divHintPop(p, e, h)]];
  if (h) items.push(["이 자리 표시 지우기", "", () => divHintDelete(h.id)]);
  items.push([divMarksOn() ? "구분 기준 표시 감추기" : "구분 기준 표시 보기", "", () => { divMarksSet(!divMarksOn()); if (divMarksOn()) divMembersLoad(); else divMarksDraw(); divMarksBarRefresh(); }]);
  return items;
}
function divContextMenu(e) { // 표 밖 문단 — 표 칸은 tselContextMenu 가 맡는다
  if (!state.id || (typeof cellOf === "function" && cellOf(e.target))) return;
  const items = divCtxItems(e).slice(1);
  if (!items.length) return;
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
  acts.append(ok, hBtn("취소", () => divPopClose()));
  pop.append(row1, rowN, row2, row3, acts, el("p", "dv-caption", "라벨 문단(되풀이 항목의 머리) 하나를 표시합니다. 혼자면 묶음이 안 되니 형제를 더 표시하거나 「LLM 재검토」로 찾으세요."));
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
    tds.title = h.engine ? "같은 꼴·같은 구분의 문단들과 묶음이 되어 변경 계획에 듭니다" : h.read ? "값 차례가 이어지는 같은 꼴 라벨이 2개 이상이어야 묶음 — 형제를 표시하거나 LLM 재검토" : "단계·차년도·기관 같은 값 낱말이 글에 없어 엔진이 사본 이름을 못 바꿉니다(문서 표시에만)";
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
  if (t) t.scrollIntoView({ block: "center", behavior: "smooth" }); else toast("그 표가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)");
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
  for (const x of last ? last.missing : []) {
    const tr = el("tr", "go"); tr.tabIndex = 0;
    const [cls, name] = DV_CONF[x.confidence] || DV_CONF.low;
    const tdc = el("td"); tdc.append(el("span", `dv-badge ${cls}`, name)); tr.append(tdc);
    hCell(tr, x.dimName || x.dim);
    hCell(tr, x.kind === "table" ? `표 ${x.size || ""}`.trim() : "문단", null, x.id);
    const tdw = el("td", "dv-labels"); tdw.append(x.kind === "table" ? (x.title || x.text || x.id) : x.text);
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
    tr.onclick = () => { for (const y of tb.querySelectorAll("tr.sel")) y.classList.remove("sel"); tr.classList.add("sel"); divMissingGo(x); };
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
$("doc").addEventListener("contextmenu", divContextMenu); // 표 칸은 tselContextMenu(먼저 묶임)가 맡고 preventDefault 하므로 여기서는 표 밖 문단만

