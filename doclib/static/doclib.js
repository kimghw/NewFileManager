// 문서 라이브러리 서버의 관리 화면(doclib/static) — 문서 목록 · 올리기 · 자료 추출 · 결과(MD · 그림) 보기 · 스킬 글. 문서 편집 서버(app/static)의 스크립트를 읽지 않는다.
// 주소의 #d=<문서 id> · #x=<추출 id> 로 그 문서 · 그 추출을 연다(문서 편집 화면이 이 화면을 새 탭으로 열 때 쓴다).
const $ = (id) => document.getElementById(id);
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
async function api(path, opt = {}) {
  const r = await fetch(path, { ...opt, headers: opt.body && !(opt.body instanceof FormData) ? { "Content-Type": "application/json" } : undefined });
  let data = null;
  try { data = (r.headers.get("content-type") || "").includes("json") ? await r.json() : await r.text(); } catch { /* 빈 응답 */ }
  if (!r.ok) throw new Error((data && data.detail) || `요청 실패(${r.status})`);
  return data;
}
let toastTimer = 0;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 4500);
}
const S = { docs: [], doc: "", ext: "", health: null, timer: 0, md: {} };
const STATE = { queued: ["기다림", "llm"], running: ["추출 중", "llm"], done: ["끝남", "ok"], failed: ["실패", "fail"], stopped: ["멈춤", "warn"], cut: ["끊김", "warn"] };
const bytes = (n) => (n >= 2 ** 20 ? `${(n / 2 ** 20).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const when = (t) => (t ? new Date(t * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "");
const docOf = (id) => S.docs.find((d) => d.id === id) || null;
const live = (e) => e && (e.state === "queued" || e.state === "running");

async function loadHealth() {
  try {
    S.health = await api("/api/health");
    const c = $("llmChip"), ok = S.health.llm.available;
    c.textContent = ok ? `LLM ${S.health.llm.model}` : "LLM 꺼짐";
    c.className = `chip ${ok ? "ok" : "fail"}`;
    c.title = ok ? `Claude CLI · 동시에 ${S.health.llm.slots}개 · 한 묶음 ${S.health.size}쪽까지` : "Claude CLI 를 찾지 못했거나 꺼져 있습니다 — 자료 추출을 할 수 없습니다";
  } catch (e) { toast(e.message); }
}
async function loadDocs() {
  S.docs = (await api("/api/docs")).docs;
  renderDocs();
  renderWork();
  clearTimeout(S.timer);
  if (S.docs.some((d) => d.extracts.some(live))) S.timer = setTimeout(() => loadDocs().catch(() => {}), 2500);
}
function renderDocs() {
  const ul = $("docList");
  ul.replaceChildren();
  $("docCount").textContent = S.docs.length ? `${S.docs.length}개` : "";
  for (const d of S.docs) {
    const li = el("li", d.id === S.doc ? "on" : "");
    const meta = el("div", "doc-meta");
    meta.append(el("span", "chip", d.ext), el("span", null, d.pages ? `${d.pages}쪽` : "쪽 수 모름"), el("span", null, bytes(d.bytes)));
    if (d.org) meta.append(el("span", "chip", d.org));
    const n = d.extracts.filter((e) => e.state === "done").length, run = d.extracts.filter(live).length;
    if (run) meta.append(el("span", "chip llm", `추출 중 ${run}`));
    else if (n) meta.append(el("span", "chip ok", `추출 ${n}`));
    li.append(el("div", "doc-name", d.name), meta);
    li.addEventListener("click", () => pick(d.id));
    ul.append(li);
  }
  if (!S.docs.length) ul.append(el("li", "muted", "아직 문서가 없습니다 — 문서를 올리세요."));
}
function pick(did, eid = "") {
  S.doc = did;
  S.ext = eid;
  history.replaceState(null, "", did ? `#d=${did}${eid ? `&x=${eid}` : ""}` : "#");
  renderDocs();
  renderWork();
}
async function upload(files) {
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    try {
      const got = await api("/api/docs", { method: "POST", body: fd });
      toast(got.created ? `올림: ${got.doc.name}` : `이미 있는 문서입니다: ${got.doc.name}`);
      S.doc = got.doc.id;
    } catch (e) { toast(`${f.name}: ${e.message}`); }
  }
  await loadDocs();
}
function field(label, input) {
  const w = el("label", "field");
  w.append(el("span", null, label), input);
  return w;
}
function textIn(value, ph) {
  const i = el("input");
  i.type = "text";
  i.value = value || "";
  i.placeholder = ph || "";
  return i;
}
function renderWork() {
  const box = $("work"), d = docOf(S.doc);
  // 쓰던 글을 지키려고 추출 폼은 문서가 바뀔 때만 다시 그린다
  if (!d) { box.replaceChildren(el("div", "empty", "왼쪽에서 문서를 고르면 자료 추출을 시작할 수 있습니다.")); box.dataset.doc = ""; return; }
  if (box.dataset.doc !== d.id) {
    box.dataset.doc = d.id;
    box.replaceChildren(docSec(d), runSec(d), el("div", "sec", ""), el("div", "sec", ""));
    box.children[2].id = "xSec";
    box.children[3].id = "mdSec";
  }
  renderExtracts(d);
}
function docSec(d) {
  const sec = el("div", "sec"), h = el("h3");
  h.append(el("span", null, d.name));
  const org = textIn(d.org, "예: 한국선급"), topic = textIn(d.topic, "예: 자율운항 선박 실증"), note = textIn(d.note, "메모");
  const save = async () => { try { await api(`/api/docs/${d.id}`, { method: "PATCH", body: JSON.stringify({ org: org.value, topic: topic.value, note: note.value }) }); await loadDocs(); } catch (e) { toast(e.message); } };
  for (const i of [org, topic, note]) i.addEventListener("change", save);
  const row = el("div", "row"), tools = el("div", "row");
  row.append(field("기관", org), field("연구 · 과제", topic), field("메모", note));
  const pdf = el("a", "btn small", "PDF 로 보기"), file = el("a", "btn small", "올린 파일 내려받기"), del = el("button", "btn small danger", "문서 지우기");
  pdf.href = `/api/docs/${d.id}/pdf`; pdf.target = "_blank"; pdf.rel = "noopener";
  file.href = `/api/docs/${d.id}/file`;
  del.type = "button";
  del.addEventListener("click", async () => {
    if (!confirm(`「${d.name}」 과 그 추출 결과를 모두 지웁니다. 되돌릴 수 없습니다.`)) return;
    try { await api(`/api/docs/${d.id}`, { method: "DELETE" }); S.doc = ""; await loadDocs(); } catch (e) { toast(e.message); }
  });
  tools.append(el("span", "muted", `${d.ext} · ${d.pages ? `${d.pages}쪽` : "쪽 수는 처음 추출할 때 셉니다"} · ${bytes(d.bytes)} · ${when(d.at)}`), el("span", "grow"), pdf, file, del);
  sec.append(h, row, tools);
  tools.style.marginTop = "8px";
  return sec;
}
function runSec(d) {
  const sec = el("div", "sec"), h = el("h3");
  const help = el("button", "note", "i");
  help.type = "button"; help.title = "자료 추출 안내"; help.addEventListener("click", () => $("helpDlg").showModal());
  h.append(el("span", null, "자료 추출 (MD)"), help);
  const focus = el("textarea");
  focus.placeholder = "뽑을 범위 — 예: 한국선급이 맡은 연구 내용 / 자율운항 실증 과제의 2차년도 실적 (비우면 문서 전체)";
  focus.value = [d.org, d.topic].filter(Boolean).join(" · ");
  const first = el("input"), last = el("input");
  for (const i of [first, last]) { i.type = "number"; i.min = "1"; if (d.pages) i.max = String(d.pages); }
  first.placeholder = "1"; last.placeholder = d.pages ? String(d.pages) : "끝";
  const go = el("button", "btn primary", "추출 시작");
  go.type = "button";
  go.addEventListener("click", async () => {
    const body = { focus: focus.value };
    if (first.value || last.value) { body.first = Number(first.value || 1); body.last = Number(last.value || d.pages || first.value || 1); }
    const pages = body.first ? body.last - body.first + 1 : d.pages, size = (S.health && S.health.size) || 20;
    if (!confirm(`유료 LLM(${(S.health && S.health.llm.model) || "Claude"})으로 추출합니다${pages ? ` — ${pages}쪽 · 쪽 묶음 ${Math.ceil(pages / size)}개` : ""}. 진행할까요?`)) return;
    go.disabled = true;
    try { const got = await api(`/api/docs/${d.id}/extracts`, { method: "POST", body: JSON.stringify(body) }); S.ext = got.extract.id; await loadDocs(); } catch (e) { toast(e.message); }
    go.disabled = false;
  });
  const row = el("div", "row");
  row.append(field("쪽 범위(비우면 전체)", (() => { const w = el("div", "row"); w.append(first, el("span", "muted", "~"), last); return w; })()), el("span", "grow"), go);
  row.style.marginTop = "8px"; row.style.alignItems = "end";
  sec.append(h, field("뽑을 범위(특정 기관 · 특정 연구)", focus), row);
  return sec;
}
function renderExtracts(d) {
  const sec = $("xSec");
  if (!sec) return;
  const h = el("h3"), list = el("div", "x-list");
  h.append(el("span", null, "추출 결과"), el("span", "count", d.extracts.length ? `${d.extracts.length}개` : ""));
  if (!d.extracts.length) list.append(el("div", "muted", "아직 추출한 것이 없습니다."));
  if (!S.ext || !d.extracts.some((e) => e.id === S.ext)) S.ext = (d.extracts.find((e) => e.state === "done") || d.extracts[0] || {}).id || "";
  for (const e of d.extracts) list.append(extCard(d, e));
  sec.replaceChildren(h, list);
  renderMd(d);
}
function extCard(d, e) {
  const card = el("div", `x-card${e.id === S.ext ? " on" : ""}`), [name, cls] = STATE[e.state] || [e.state, ""];
  const top = el("div", "row"), meta = el("div", "doc-meta"), tools = el("div", "row");
  top.append(el("span", `chip ${cls}`, name), el("span", "x-focus", e.focus || "문서 전체"));
  const span = e.span ? `쪽 ${e.span[0]}–${e.span[1]}` : "";
  meta.append(el("span", null, [span, when(e.at), e.model].filter(Boolean).join(" · ")));
  if (e.state === "done") {
    meta.append(el("span", "chip", `그림 ${e.figures}`), el("span", "chip", `수식 ${e.formulas}`), el("span", "chip", `${(e.chars || 0).toLocaleString()}자`));
    if (e.open) meta.append(el("span", "chip warn", `확인 필요 ${e.open}`));
    if (typeof e.costUsd === "number") meta.append(el("span", "muted", `정가 셈 $${e.costUsd.toFixed(2)}`));
  }
  card.append(top, meta);
  if (live(e)) {
    const bar = el("div", "bar"), fill = el("i"), p = e.progress || {};
    fill.style.width = `${p.total ? Math.round((p.done / p.total) * 100) : 4}%`;
    bar.append(fill);
    card.append(bar, el("div", "muted", p.text || ""));
    const stop = el("button", "btn small", "멈춤");
    stop.type = "button";
    stop.addEventListener("click", async () => { try { await api(`/api/extracts/${e.id}/stop`, { method: "POST" }); toast("멈추는 중입니다"); } catch (err) { toast(err.message); } });
    tools.append(stop);
  } else {
    if (e.error) card.append(el("div", "muted", e.error));
    if (e.state === "done") {
      const view = el("button", "btn small", "MD 보기"), zip = el("a", "btn small", "내려받기(zip)");
      view.type = "button";
      view.addEventListener("click", () => pick(d.id, e.id));
      zip.href = `/api/extracts/${e.id}/zip`;
      tools.append(view, zip);
    }
    const del = el("button", "btn small danger", "지우기");
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!confirm("이 추출 결과를 지웁니다.")) return;
      try { await api(`/api/extracts/${e.id}`, { method: "DELETE" }); delete S.md[e.id]; await loadDocs(); } catch (err) { toast(err.message); }
    });
    tools.append(el("span", "grow"), del);
  }
  card.append(tools);
  return card;
}
async function renderMd(d) {
  const sec = $("mdSec"), e = d.extracts.find((x) => x.id === S.ext);
  if (!sec) return;
  if (!e || e.state !== "done") { sec.replaceChildren(); sec.dataset.ext = ""; return; }
  if (sec.dataset.ext === e.id) return;
  sec.dataset.ext = e.id;
  const h = el("h3"), view = el("div", "md-view"), pre = el("pre"), figs = el("div", "figs");
  h.append(el("span", null, "MD"), el("span", "count", e.focus || "문서 전체"));
  view.append(pre);
  sec.replaceChildren(h, view, figs);
  try {
    const text = S.md[e.id] || (S.md[e.id] = await api(`/api/extracts/${e.id}/md`));
    if (sec.dataset.ext !== e.id) return;
    pre.textContent = text;
    const lines = text.split("\n");
    lines.forEach((ln, i) => {
      const m = /!\[(.*?)\]\(images\/([^)]+)\)/.exec(ln);
      if (!m) return;
      const fig = el("figure"), img = el("img"), warn = /확인 필요/.test(lines[i + 1] || "");
      img.src = `/api/extracts/${e.id}/images/${encodeURIComponent(m[2])}`;
      img.alt = m[1]; img.loading = "lazy";
      if (warn) fig.className = "warn";
      fig.append(img, el("figcaption", null, (warn ? "확인 필요 — " : "") + (m[1] || m[2])));
      figs.append(fig);
    });
  } catch (err) { pre.textContent = err.message; }
}
// ---- 스킬 글 ----
const K = { list: [], contracts: {}, name: "" };
async function skillOpen() {
  try {
    const got = await api("/api/prompts");
    K.list = got.prompts; K.contracts = got.contracts;
    K.name = K.name || K.list[0].name;
    skillShow();
    $("skillDlg").show(); // 가리는 창이 아니라 오른쪽 열로(문서 · 추출 결과를 보면서)
  } catch (e) { toast(e.message); }
}
function skillShow() {
  const tabs = $("skillTabs"), p = K.list.find((x) => x.name === K.name);
  tabs.replaceChildren(...K.list.map((x) => {
    const b = el("button", `btn small${x.name === K.name ? " on" : ""}`, x.title + (x.custom ? " · 고침" : ""));
    b.type = "button";
    b.addEventListener("click", () => { K.name = x.name; skillShow(); });
    return b;
  }));
  $("skillText").value = p.text;
  $("skillNote").textContent = p.custom ? "내가 고친 글입니다 — 「기본본으로」 를 누르면 되돌립니다. 다음 추출부터 쓰입니다." : "기본본입니다 — 고쳐 저장하면 다음 추출부터 쓰입니다. 제목 줄과 <!-- 주석 --> 은 LLM 에 보내지 않습니다.";
  $("skillContract").textContent = K.contracts[p.name] || "";
  $("skillReset").disabled = !p.custom;
}
async function skillSave(text) {
  try {
    const got = await api(`/api/prompts/${K.name}`, { method: "PUT", body: JSON.stringify({ text }) });
    K.list = K.list.map((x) => (x.name === K.name ? got.prompt : x));
    skillShow();
    toast("저장했습니다");
  } catch (e) { toast(e.message); }
}
// ---- 시작 ----
function fromHash() {
  const q = new URLSearchParams(location.hash.slice(1));
  S.doc = q.get("d") || S.doc;
  S.ext = q.get("x") || S.ext;
}
$("helpBtn").addEventListener("click", () => $("helpDlg").showModal());
$("skillBtn").addEventListener("click", skillOpen);
$("skillClose").addEventListener("click", () => $("skillDlg").close());
$("skillSave").addEventListener("click", () => skillSave($("skillText").value));
$("skillReset").addEventListener("click", () => skillSave(""));
$("fileIn").addEventListener("change", (ev) => { upload([...ev.target.files]); ev.target.value = ""; });
const drop = $("drop");
for (const t of ["dragenter", "dragover"]) drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.add("over"); });
for (const t of ["dragleave", "drop"]) drop.addEventListener(t, (ev) => { ev.preventDefault(); drop.classList.remove("over"); });
drop.addEventListener("drop", (ev) => upload([...(ev.dataTransfer ? ev.dataTransfer.files : [])]));
window.addEventListener("hashchange", () => { fromHash(); renderDocs(); renderWork(); });
fromHash();
loadHealth();
loadDocs().catch((e) => toast(e.message));
