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
    const ext = el("span", "doc-ext", (d.ext || "").toUpperCase());
    ext.dataset.ext = (d.ext || "").toLowerCase();
    const body = el("div", "doc-body");
    const meta = el("div", "doc-meta");
    meta.append(el("span", "doc-info", `${d.pages ? `${d.pages}쪽` : "쪽 수 모름"} · ${bytes(d.bytes)}`));
    if (d.org) meta.append(el("span", "doc-org", d.org));
    const n = d.extracts.filter((e) => e.state === "done").length, run = d.extracts.filter(live).length;
    if (run) meta.append(el("span", "chip llm", `추출 중 ${run}`));
    else if (n) meta.append(el("span", "chip ok", `추출 ${n}`));
    const name = el("div", "doc-name", d.name);
    name.title = d.name;
    body.append(name, meta);
    li.append(ext, body);
    li.addEventListener("click", () => pick(d.id));
    ul.append(li);
  }
  if (!S.docs.length) ul.append(el("li", "doc-empty", "아직 문서가 없습니다 — 문서를 올리세요."));
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
  if (!d) {
    const empty = el("div", "empty"), hasDocs = S.docs.length > 0;
    empty.id = "workEmpty";
    empty.append(el("div", "empty-lead", hasDocs ? "왼쪽에서 문서를 고르면 자료 추출을 시작할 수 있습니다." : "왼쪽에서 문서를 올리면 자료 추출을 시작할 수 있습니다."));
    const steps = el("ol", "steps"), cur = hasDocs ? 1 : 0;
    ["문서 올리기", "문서 고르기", "뽑을 범위 · 추출 시작", "MD · 그림 확인"].forEach((label, idx) => {
      const li = el("li", `step${idx === cur ? " cur" : ""}`);
      li.append(el("span", "step-n", String(idx + 1)), el("span", null, label));
      steps.append(li);
    });
    empty.append(steps);
    box.replaceChildren(empty);
    box.dataset.doc = "";
    return;
  }
  if (box.dataset.doc !== d.id) {
    box.dataset.doc = d.id;
    box.replaceChildren(docSec(d), runSec(d), el("div", "sec x-sec", ""), el("div", "sec md-sec", ""));
    box.children[2].id = "xSec";
    box.children[3].id = "mdSec";
  }
  renderExtracts(d);
}
function docSec(d) {
  const sec = el("div", "sec doc-head");
  const top = el("div", "doc-head-top"), main = el("div", "doc-head-main"), titleRow = el("div", "doc-title-row");
  const ext = el("span", "doc-ext-tag", (d.ext || "").toUpperCase());
  ext.dataset.ext = (d.ext || "").toLowerCase();
  const title = el("h2", "doc-title", d.name);
  title.title = d.name;
  titleRow.append(ext, title);
  const sub = el("div", "doc-sub", `${d.pages ? `${d.pages}쪽` : "쪽 수는 처음 추출할 때 셉니다"} · ${bytes(d.bytes)} · ${when(d.at)}`);
  main.append(titleRow, sub);
  const acts = el("div", "doc-head-acts");
  const pdf = el("a", "btn small btn-pdf", "PDF 로 보기"), file = el("a", "btn small btn-dl", "올린 파일 내려받기"), del = el("button", "btn small danger btn-del", "문서 지우기");
  pdf.href = `/api/docs/${d.id}/pdf`; pdf.target = "_blank"; pdf.rel = "noopener";
  file.href = `/api/docs/${d.id}/file`;
  del.type = "button";
  del.addEventListener("click", async () => {
    if (!confirm(`「${d.name}」 과 그 추출 결과를 모두 지웁니다. 되돌릴 수 없습니다.`)) return;
    try { await api(`/api/docs/${d.id}`, { method: "DELETE" }); S.doc = ""; await loadDocs(); } catch (e) { toast(e.message); }
  });
  acts.append(pdf, file, del);
  top.append(main, acts);
  const org = textIn(d.org, "예: 한국선급"), topic = textIn(d.topic, "예: 자율운항 선박 실증"), note = textIn(d.note, "메모");
  const save = async () => { try { await api(`/api/docs/${d.id}`, { method: "PATCH", body: JSON.stringify({ org: org.value, topic: topic.value, note: note.value }) }); await loadDocs(); } catch (e) { toast(e.message); } };
  for (const i of [org, topic, note]) i.addEventListener("change", save);
  const fields = el("div", "doc-fields");
  fields.append(field("기관", org), field("연구 · 과제", topic), field("메모", note));
  sec.append(top, fields);
  return sec;
}
function runSec(d) {
  const sec = el("div", "sec run-sec"), h = el("h3");
  const help = el("button", "note", "i");
  help.type = "button"; help.title = "자료 추출 안내"; help.addEventListener("click", () => $("helpDlg").showModal());
  h.append(el("span", null, "자료 추출 (MD)"), help);
  const focus = el("textarea");
  focus.placeholder = "뽑을 범위 — 예: 한국선급이 맡은 연구 내용 / 자율운항 실증 과제의 2차년도 실적 (비우면 문서 전체)";
  focus.value = [d.org, d.topic].filter(Boolean).join(" · ");
  const first = el("input"), last = el("input");
  for (const i of [first, last]) { i.type = "number"; i.min = "1"; if (d.pages) i.max = String(d.pages); }
  first.placeholder = "1"; last.placeholder = d.pages ? String(d.pages) : "끝";
  const go = el("button", "btn primary btn-go", "추출 시작");
  go.type = "button";
  go.addEventListener("click", () => {
    const body = { focus: focus.value };
    if (first.value || last.value) { body.first = Number(first.value || 1); body.last = Number(last.value || d.pages || first.value || 1); }
    startExtract(d, body, go);
  });
  const bar = el("div", "run-bar"), range = el("div", "page-range"), act = el("div", "run-act"), hint = el("span", "run-hint");
  const updateHint = () => {
    const size = (S.health && S.health.size) || 20, slots = (S.health && S.health.llm && S.health.llm.slots) || 0;
    const fVal = first.value.trim(), lVal = last.value.trim();
    hint.className = "run-hint";
    let pages = d.pages || 0;
    if (fVal || lVal) {
      const a = Number(fVal || 1), b = Number(lVal || d.pages || a || 1);
      if (!Number.isFinite(a) || !Number.isFinite(b) || a < 1 || b < a) {
        hint.textContent = a < 1 ? "쪽 번호는 1부터입니다" : "시작 쪽이 끝 쪽보다 큽니다";
        hint.classList.add("is-warn");
        return;
      }
      if (d.pages && (a > d.pages || b > d.pages)) {
        hint.textContent = `끝 쪽은 ${d.pages}쪽까지입니다`;
        hint.classList.add("is-warn");
        return;
      }
      pages = b - a + 1;
    }
    const parts = pages ? [`${pages}쪽`, `쪽 묶음 ${Math.ceil(pages / size)}개`] : [`한 묶음 ${size}쪽`];
    if (slots) parts.push(`동시에 ${slots}개`);
    hint.textContent = parts.join(" · ");
  };
  for (const i of [first, last]) { i.addEventListener("input", updateHint); i.addEventListener("change", updateHint); }
  updateHint();
  if (!S.health && $("llmChip")) {
    const mo = new MutationObserver(() => {
      if (!sec.isConnected) { mo.disconnect(); return; }
      if (S.health) { updateHint(); mo.disconnect(); }
    });
    mo.observe($("llmChip"), { childList: true, characterData: true, attributes: true });
  }
  range.append(el("span", "range-lbl", "쪽 범위(비우면 전체)"), first, el("span", "muted", "~"), last);
  act.append(hint, go);
  bar.append(range, act);
  sec.append(h, field("뽑을 범위(특정 기관 · 특정 연구)", focus), bar);
  return sec;
}
// 추출 시작(새로 · 「다시 추출」 같이) — 유료 LLM 이라 쪽 수 · 묶음 수를 보이고 묻는다
async function startExtract(d, body, btn) {
  const pages = body.first ? body.last - body.first + 1 : d.pages, size = (S.health && S.health.size) || 20;
  if (!confirm(`유료 LLM(${(S.health && S.health.llm.model) || "Claude"})으로 추출합니다${pages ? ` — ${pages}쪽 · 쪽 묶음 ${Math.ceil(pages / size)}개` : ""}. 진행할까요?`)) return;
  btn.disabled = true;
  try { const got = await api(`/api/docs/${d.id}/extracts`, { method: "POST", body: JSON.stringify(body) }); S.ext = got.extract.id; await loadDocs(); } catch (e) { toast(e.message); }
  btn.disabled = false;
}
// 시작부터 지난 시간 — 「12분째」 · 「1시간 5분째」(진행 글이 오래 안 바뀌면 멈춘 것인지 가늠하게)
function elapsed(t) {
  const m = Math.max(0, Math.floor((Date.now() / 1000 - t) / 60));
  return m < 1 ? "방금 시작" : m < 60 ? `${m}분째` : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}째`;
}
function renderExtracts(d) {
  const sec = $("xSec");
  if (!sec) return;
  const h = el("h3"), list = el("div", d.extracts.length > 1 ? "x-list multi" : "x-list single");
  h.append(el("span", null, "추출 결과"), el("span", "count", d.extracts.length ? `${d.extracts.length}개` : ""));
  if (!d.extracts.length) {
    const empty = el("div", "x-empty");
    empty.append(
      el("div", "x-empty-lead", "아직 추출한 것이 없습니다."),
      el("div", "x-empty-sub", "위에서 뽑을 범위를 적고 「추출 시작」을 누르면 이곳에 진행 상태와 결과가 쌓입니다.")
    );
    list.append(empty);
  }
  if (!S.ext || !d.extracts.some((e) => e.id === S.ext)) S.ext = (d.extracts.find((e) => e.state === "done") || d.extracts[0] || {}).id || "";
  for (const e of d.extracts) list.append(extCard(d, e));
  sec.replaceChildren(h, list);
  renderMd(d);
}
function extCard(d, e) {
  const isOn = e.id === S.ext, isLive = live(e);
  const card = el("div", `x-card state-${e.state}${isOn ? " on" : ""}${isLive ? " live" : ""}`), [name, cls] = STATE[e.state] || [e.state, ""];
  const top = el("div", "x-top"), title = el("div", "x-title"), acts = el("div", "x-acts");
  title.append(el("span", `chip ${cls}`, name), el("span", "x-focus", e.focus || "문서 전체"));
  if (e.state === "done" && e.open) title.append(el("span", "chip warn", `확인 필요 ${e.open}`));
  if (isLive) {
    const stop = el("button", "btn small btn-stop", "멈춤");
    stop.type = "button";
    stop.addEventListener("click", async () => { try { await api(`/api/extracts/${e.id}/stop`, { method: "POST" }); toast("멈추는 중입니다"); } catch (err) { toast(err.message); } });
    const drop = el("button", "btn small danger btn-del", "지우기");   // 도는 것도 — 멈추고 끝나는 대로 지운다
    drop.type = "button";
    drop.addEventListener("click", async () => {
      if (!confirm("이 추출을 멈추고 지웁니다(도는 LLM 호출이 끊기는 대로 — 몇 초).")) return;
      try { await api(`/api/extracts/${e.id}`, { method: "DELETE" }); delete S.md[e.id]; toast("멈추고 지우는 중입니다"); await loadDocs(); } catch (err) { toast(err.message); }
    });
    acts.append(stop, drop);
  } else {
    if (e.state === "done") {
      const view = el("button", `btn small btn-md${isOn ? " on" : ""}`, "MD 보기"), zip = el("a", "btn small btn-zip", "내려받기(zip)");
      view.type = "button";
      view.addEventListener("click", () => pick(d.id, e.id));
      zip.href = `/api/extracts/${e.id}/zip`;
      acts.append(view, zip);
    } else {   // 끊김 · 실패 · 멈춤 — 같은 범위 · 같은 쪽으로 다시
      const again = el("button", "btn small btn-again", "다시 추출");
      again.type = "button";
      again.addEventListener("click", () => startExtract(d, { focus: e.focus || "", ...(e.span ? { first: e.span[0], last: e.span[1] } : {}) }, again));
      acts.append(again);
    }
    const del = el("button", "btn small danger btn-del", "지우기");
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!confirm("이 추출 결과를 지웁니다.")) return;
      try { await api(`/api/extracts/${e.id}`, { method: "DELETE" }); delete S.md[e.id]; await loadDocs(); } catch (err) { toast(err.message); }
    });
    acts.append(del);
  }
  top.append(title, acts);
  const metaRow = el("div", "x-meta-row");
  const span = e.span ? `쪽 ${e.span[0]}–${e.span[1]}` : "";
  metaRow.append(el("span", "x-when", [span, when(e.at), e.model].filter(Boolean).join(" · ")));
  if (e.state === "done") {
    const stats = el("div", "x-stats");
    const addStat = (k, v, after) => {
      const s = el("span", "x-stat");
      if (after) s.append(el("b", null, v), el("span", "k", k));
      else s.append(el("span", "k", k), el("b", null, v));
      stats.append(s);
    };
    addStat("그림", String(e.figures));
    addStat("수식", String(e.formulas));
    addStat("자", (e.chars || 0).toLocaleString(), true);
    if (typeof e.costUsd === "number") addStat("정가 셈", `$${e.costUsd.toFixed(2)}`);
    metaRow.append(stats);
  }
  card.append(top, metaRow);
  if (isLive) {
    const prog = el("div", "x-prog"), p = e.progress || {}, pct = p.total ? Math.round((p.done / p.total) * 100) : 0;
    const bar = el("div", `bar${p.total ? "" : " indet"}`), fill = el("i");
    fill.style.width = `${p.total ? Math.max(4, pct) : 28}%`;
    bar.append(fill);
    const progMeta = el("div", "x-prog-meta"), progStat = el("span", "x-prog-stat");
    if (p.total) progStat.append(el("span", "x-prog-pct", `${pct}%`));
    progStat.append(el("span", "x-elapsed", elapsed(e.at)));
    progMeta.append(el("span", "x-prog-text", p.text || "준비 중"), progStat);
    prog.append(bar, progMeta);
    card.append(prog);
  } else if (e.error) {
    card.append(el("div", "x-err", e.error));
  }
  return card;
}
async function renderMd(d) {
  const sec = $("mdSec"), e = d.extracts.find((x) => x.id === S.ext);
  if (!sec) return;
  if (!e || e.state !== "done") { sec.replaceChildren(); sec.dataset.ext = ""; sec.hidden = true; return; }
  sec.hidden = false;
  if (sec.dataset.ext === e.id) return;
  sec.dataset.ext = e.id;
  const h = el("h3", "md-head"), split = el("div", "md-split"), view = el("div", "md-view"), pre = el("pre"), figs = el("div", "figs");
  h.append(el("span", null, "MD"), el("span", "count", e.focus || "문서 전체"));
  view.append(pre);
  split.append(view, figs);
  sec.replaceChildren(h, split);
  try {
    const text = S.md[e.id] || (S.md[e.id] = await api(`/api/extracts/${e.id}/md`));
    if (sec.dataset.ext !== e.id) return;
    const frag = document.createDocumentFragment(), lines = text.split("\n");
    let inMath = false, warnCount = 0;
    lines.forEach((ln, i) => {
      const t = ln.trim();
      let cls = "";
      if (inMath) {
        cls = "md-math";
        if (t === "$$" || (t.endsWith("$$") && t.length > 2)) inMath = false;
      } else if (t === "$$") {
        cls = "md-math";
        inMath = true;
      } else if (t.startsWith("$$") && t.endsWith("$$") && t.length > 2) {
        cls = "md-math";
      } else if (t.startsWith("$$")) {
        cls = "md-math";
        inMath = true;
      } else if (/^#{1,6}\s/.test(t)) {
        cls = /^#\s/.test(t) ? "md-h md-h1" : "md-h";
      } else if (t.startsWith("<!--")) {
        cls = /확인 필요/.test(ln) ? "md-com md-warn" : "md-com";
      } else if (t.startsWith(">")) {
        cls = "md-quote";
      } else if (/^!\[.*?\]\(images\/[^)]+\)/.test(t)) {
        cls = "md-img";
      }
      if (cls) frag.append(el("span", cls, ln));
      else if (ln) frag.append(document.createTextNode(ln));
      if (i < lines.length - 1) frag.append(document.createTextNode("\n"));
      const m = /!\[(.*?)\]\(images\/([^)]+)\)/.exec(ln);
      if (!m) return;
      const fig = el("figure"), img = el("img"), warn = /확인 필요/.test(lines[i + 1] || "");
      img.src = `/api/extracts/${e.id}/images/${encodeURIComponent(m[2])}`;
      img.alt = m[1]; img.loading = "lazy";
      if (warn) { fig.className = "warn"; warnCount += 1; }
      fig.append(img, el("figcaption", null, (warn ? "확인 필요 — " : "") + (m[1] || m[2])));
      figs.append(fig);
    });
    pre.replaceChildren(frag);
    if (figs.children.length) {
      split.classList.add("has-figs");
      figs.dataset.label = `그림 ${figs.children.length}`;
      h.append(el("span", "grow"), el("span", "count", `그림 ${figs.children.length}`));
      if (warnCount) h.append(el("span", "chip warn", `확인 필요 ${warnCount}`));
    }
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
  const note = $("skillNote");
  note.textContent = p.custom ? "내가 고친 글입니다 — 「기본본으로」 를 누르면 되돌립니다. 다음 추출부터 쓰입니다." : "기본본입니다 — 고쳐 저장하면 다음 추출부터 쓰입니다. 제목 줄과 <!-- 주석 --> 은 LLM 에 보내지 않습니다.";
  note.className = p.custom ? "skill-note is-custom" : "skill-note";
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
