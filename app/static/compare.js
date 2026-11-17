"use strict";

// 저장된 분석을 나란히 읽는 병합 준비 화면. 문서를 열거나 추출·병합하지 않는다.
// S/F/# 번호는 문서 안 번호다. 문서 사이 후보는 scope + 사슬로만 찾는다.
const MC_LIMIT = 6;
const MC_REVIEW_KEY = "nfm.compareReviews.v1";
const MC_READY = { ready: "최신 분석", stale: "다시 추출 필요", missing: "분석 전", invalid: "결과 읽기 실패", unsupported: "지원 예정" };
let mergeCompare = { epoch: null, seq: 0, works: null, selected: new Set(), snapshots: [], mode: "templates", query: "", busy: false, error: "", notice: "" };

function compareReset() {
  mergeCompare = { epoch: state.epoch, seq: mergeCompare.seq + 1, works: null, selected: new Set(), snapshots: [], mode: "templates", query: "", busy: false, error: "", notice: "" };
  if ($("paneCompare")) $("paneCompare").replaceChildren();
}

async function compareShow() {
  if (!state.id || !$("paneCompare")) return;
  if (mergeCompare.epoch !== state.epoch) compareReset();
  if (mergeCompare.works) { mcDraw(); return; }
  await mcLoadWorks();
}

async function mcLoadWorks() {
  const m = mergeCompare, seq = ++m.seq, epoch = state.epoch;
  m.busy = true;
  m.error = "";
  mcDraw();
  try {
    const works = await api("/api/works");
    if (mergeCompare !== m || seq !== m.seq || epoch !== state.epoch) return;
    const first = m.works === null;
    m.works = works;
    const previous = [...m.selected];
    m.selected = new Set(previous.filter((id) => works.some((w) => w.id === id)));
    if (previous.length !== m.selected.size) { m.snapshots = []; m.notice = "작업 목록이 바뀌었습니다. 비교할 문서를 다시 선택하세요."; }
    if (first && works.some((w) => w.id === state.id && w.format === "hwpx")) m.selected.add(state.id);
    const project = (state.task || {}).project; // 과제로 묶인 문서(spec_작업 ② §10)는 처음부터 함께 고른다
    if (first && project) for (const w of works) if (w.format === "hwpx" && taskSameScope(w) && m.selected.size < MC_LIMIT) m.selected.add(w.id);
  } catch (e) {
    if (mergeCompare !== m || seq !== m.seq || epoch !== state.epoch) return;
    m.error = `작업 목록을 읽지 못했습니다: ${e.message}`;
  } finally {
    if (mergeCompare === m && seq === m.seq && epoch === state.epoch) { m.busy = false; mcDraw(); }
  }
}

async function mcLoadSnapshots() {
  const m = mergeCompare;
  if (m.busy || m.selected.size < 2 || m.selected.size > MC_LIMIT) return;
  const seq = ++m.seq, epoch = state.epoch, ids = [...m.selected];
  m.busy = true;
  m.error = "";
  m.notice = "";
  mcDraw();
  const results = await Promise.allSettled(ids.map((id) => api(`/api/works/${encodeURIComponent(id)}/headings-preview`)));
  if (mergeCompare !== m || seq !== m.seq || epoch !== state.epoch) return;
  m.snapshots = results.map((r, i) => r.status === "fulfilled" ? r.value : {
    work: m.works.find((w) => w.id === ids[i]) || { id: ids[i], name: ids[i] },
    supported: true, summary: {}, labels: { labels: [] }, graph: null,
    readiness: { stage1: "invalid", stage2: "invalid", stage3: "invalid" }, errors: [{ message: r.reason.message }]
  });
  m.busy = false;
  mcDraw();
}

// 함께 추출(spec_작업 ② §10 「문서 비교에서 함께 추출」, 2026-11-11): 고른 문서 가운데 헤딩 그래프·표 구조 분석이 없는 것을 한 번에 돌린다 — 스크립트만,
// 첫 분석(② §9)과 같은 끝점(`POST …/headings {first: true}` — 있는 단계는 건너뜀). 다 끝나면 비교를 다시 읽는다. 닫힌 문서는 서버가 작업 폴더에서 연다.
function mcMissing() {
  return mergeCompare.snapshots.filter((s) => s.supported !== false && !(s.errors || []).length && ["stage2", "stage3"].some((k) => mcReadiness(s, k) === "missing"));
}

async function mcExtract() {
  const m = mergeCompare, ids = mcMissing().map((s) => s.work.id);
  if (m.busy || !ids.length) return;
  const seq = ++m.seq, epoch = state.epoch, live = () => mergeCompare === m && seq === m.seq && epoch === state.epoch;
  m.busy = true;
  m.error = "";
  m.notice = `문서 ${ids.length}개의 헤딩 그래프·표 구조를 추출하는 중…(스크립트)`;
  mcDraw();
  const one = async (id) => {
    await api(`/api/docs/${encodeURIComponent(id)}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) });
    for (;;) { // 끝날 때까지 2초마다 읽는다
      await new Promise((done) => setTimeout(done, 2000));
      if (!live()) return;
      const job = (await api(`/api/docs/${encodeURIComponent(id)}/headings`)).job;
      if (job && job.status === "running") continue;
      if (job && job.error) throw new Error(job.error);
      return;
    }
  };
  const failed = (await Promise.allSettled(ids.map(one))).filter((r) => r.status === "rejected");
  if (!live()) return;
  m.busy = false;
  await mcLoadSnapshots();
  if (mergeCompare !== m || epoch !== state.epoch) return;
  if (failed.length) { m.error = `추출하지 못한 문서 ${failed.length}개: ${failed.map((r) => r.reason.message).join(" · ")}`; mcDraw(); }
  if (ids.includes(state.id) && typeof headsPeek === "function") headsPeek(); // 지금 문서면 헤딩 탭·쪽 여백 표시도 새 결과로
}

function mcDraw() {
  const m = mergeCompare, pane = $("paneCompare");
  if (!pane) return;
  const shell = el("div", "mc-shell");
  const intro = el("div", "mc-intro");
  intro.append(el("h2", null, "라벨과 템플릿, 문서별로 나란히"), el("p", null, "라벨과 템플릿을 나란히 확인하세요. 병합 전 비교 · 실제 병합은 지원 예정"));
  shell.append(intro);
  const picker = el("details", "mc-picker");
  picker.open = !m.snapshots.length;
  picker.append(el("summary", null, `비교할 문서 ${m.selected.size}개 선택 · 최대 ${MC_LIMIT}개`));
  const list = el("div", "mc-work-list");
  for (const w of m.works || []) {
    const row = el("label", "mc-work-option"), cb = el("input"), text = el("span", "mc-work-text");
    cb.type = "checkbox";
    cb.checked = m.selected.has(w.id);
    cb.disabled = m.busy || w.format !== "hwpx";
    cb.setAttribute("aria-label", `${w.name} 비교 선택`);
    text.append(el("strong", null, w.name), el("small", null,
      `${w.id === state.id ? "현재 문서 · " : ""}${(w.task || {}).project ? `프로젝트 ${w.task.project} · Round ${taskRound(w.task)} · ` : ""}${typeof taskName === "function" && taskName("file", (w.task || {}).file) ? taskName("file", w.task.file) + " · " : ""}${String(w.format || "").toUpperCase()} · 작업 ${w.id} · 수정 ${w.rev || 0}회${w.format !== "hwpx" ? " · 구조 비교 지원 예정" : ""}`));
    cb.onchange = () => {
      if (cb.checked && m.selected.size >= MC_LIMIT) {
        cb.checked = false;
        m.notice = `한 번에 ${MC_LIMIT}개까지 비교할 수 있습니다. 선택을 줄인 뒤 추가하세요.`;
      } else {
        if (cb.checked) m.selected.add(w.id); else m.selected.delete(w.id);
        m.snapshots = [];
        m.notice = "";
      }
      mcDraw();
    };
    row.append(cb, text);
    list.append(row);
  }
  if (!m.works) list.append(el("p", "mc-empty", m.busy ? "저장된 작업을 읽는 중…" : "작업 목록을 불러오세요."));
  else if (!m.works.length) list.append(el("p", "mc-empty", "저장된 작업이 없습니다. 문서를 열어 작업을 저장한 뒤 비교할 수 있습니다."));
  picker.append(list);
  shell.append(picker);
  const actions = el("div", "mc-actions");
  actions.append(hBtn(m.busy ? "읽는 중…" : m.snapshots.length ? "비교 새로고침" : "선택 문서 비교", mcLoadSnapshots,
    { cls: "btn sm primary", disabled: m.busy || m.selected.size < 2 }),
    hBtn("목록 새로고침", mcLoadWorks, { disabled: m.busy }));
  const missing = mcMissing().length;
  if (missing) actions.append(hBtn(`분석 없는 문서 ${missing}개 추출`, mcExtract, { disabled: m.busy,
    title: "고른 문서 가운데 헤딩 그래프·표 구조 분석이 없는 것을 함께 추출합니다 — 스크립트만(LLM 호출 없음), 이미 있는 단계는 건너뜀 · 끝나면 비교를 다시 읽습니다" }));
  actions.append(el("span", "muted", "2개 이상 선택 · 저장된 분석만 조회"));
  shell.append(actions);
  if (m.error) shell.append(el("p", "mc-error", m.error));
  if (m.notice) {
    const notice = el("p", "mc-notice", m.notice);
    notice.setAttribute("role", "status");
    shell.append(notice);
  }
  if (m.snapshots.length) {
    const tools = el("div", "mc-toolbar"), seg = el("div", "seg");
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", "문서 비교 항목");
    for (const [key, label] of [["templates", "템플릿"], ["labels", "서식 라벨"], ["review", "확인할 항목"]]) {
      const b = hBtn(label, () => { m.mode = key; mcDrawResults(); });
      b.dataset.mcMode = key;
      b.classList.toggle("on", key === m.mode);
      b.setAttribute("aria-pressed", key === m.mode);
      seg.append(b);
    }
    const search = el("input", "mc-search");
    search.type = "search";
    search.placeholder = "사슬·라벨·문단 검색";
    search.setAttribute("aria-label", "비교 결과 검색");
    search.value = m.query;
    search.oninput = () => { m.query = search.value; mcDrawResults(); };
    tools.append(seg, search);
    shell.append(tools, el("p", "mc-notice", "서식 라벨·템플릿 번호는 각 문서 안에서만 유효합니다. 같은 사슬 표시는 대응 후보이며, 내용과 서식은 직접 확인해야 합니다."));
    const result = el("div", "mc-results");
    result.id = "mcResults";
    shell.append(result);
  } else if (!m.busy && !m.error) {
    shell.append(el("div", "mc-empty", "비교할 문서를 고르면 문서별 출처, 분석 시점, 라벨과 템플릿이 여기에 나란히 표시됩니다."));
  }
  pane.replaceChildren(shell);
  if (m.snapshots.length) mcDrawResults();
}

function mcReadiness(s, stage) {
  if (s.supported === false) return "unsupported";
  if (s.readiness && s.readiness[stage]) return s.readiness[stage];
  const result = (s.summary || {})[stage];
  return !result ? "missing" : result.stale ? "stale" : "ready";
}

function mcCurrentChanged(s) {
  return s.work.id === state.id && (Number(s.work.rev) !== Number(state.serverRev) || state.timers.size > 0 || state.inflight || state.failed.size > 0);
}

function mcReviewKey(s) {
  const sm = s.summary || {};
  return JSON.stringify([s.work.id, s.work.rev, ...["stage1", "stage2"].flatMap((k) => {
    const meta = (sm[k] || {}).meta || {};
    return [meta.run, meta.at, meta.rev];
  })]);
}

function mcReviewStore() {
  try { const v = JSON.parse(localStorage.getItem(MC_REVIEW_KEY) || "{}"); return v && typeof v === "object" && !Array.isArray(v) ? v : {}; }
  catch { return {}; }
}

function mcReviewed(s) { return mcReviewStore()[mcReviewKey(s)] === true; }

function mcSetReviewed(s, value) {
  const store = mcReviewStore();
  // 같은 문서의 이전 분석에 대한 표시는 남기지 않는다.
  for (const key of Object.keys(store)) {
    try { if (JSON.parse(key)[0] === s.work.id) delete store[key]; } catch { delete store[key]; }
  }
  if (value) store[mcReviewKey(s)] = true;
  const entries = Object.entries(store).slice(-100);
  try { localStorage.setItem(MC_REVIEW_KEY, JSON.stringify(Object.fromEntries(entries))); return true; }
  catch { return false; }
}

function mcCanReview(s) {
  return !mergeCompare.busy && mcReadiness(s, "stage1") === "ready" && mcReadiness(s, "stage2") === "ready" && !mcCurrentChanged(s) && !(s.errors || []).length;
}

function mcTemplateKey(t) {
  if (t.scope && Array.isArray(t.chain) && t.chain.length) return JSON.stringify([t.scope, t.chain]);
  // 옛 결과의 번호·표시 이름은 문서 사이 대응 키로 쓰지 않는다.
  return typeof t.anchor === "string" && /^(body|cell):/.test(t.anchor) ? t.anchor : null;
}

function mcCandidates() {
  const candidates = new Map();
  for (const s of mergeCompare.snapshots) {
    if (mcReadiness(s, "stage2") !== "ready" || mcCurrentChanged(s)) continue;
    for (const t of (s.graph || {}).templates || []) {
      const key = mcTemplateKey(t);
      if (!key) continue;
      if (!candidates.has(key)) candidates.set(key, new Set());
      candidates.get(key).add(s.work.id);
    }
  }
  return candidates;
}

function mcDrawResults() {
  const box = $("mcResults"), m = mergeCompare;
  if (!box) return;
  for (const b of $("paneCompare").querySelectorAll("[data-mc-mode]")) {
    b.classList.toggle("on", b.dataset.mcMode === m.mode);
    b.setAttribute("aria-pressed", b.dataset.mcMode === m.mode);
  }
  const scroll = el("div", "mc-scroll"), grid = el("div", "mc-grid"), candidates = mcCandidates();
  grid.style.setProperty("--mc-columns", m.snapshots.length);
  for (const s of m.snapshots) {
    const column = el("section", "mc-column");
    column.setAttribute("aria-label", `${s.work.name} 비교 결과`);
    column.append(mcDocHead(s));
    const body = el("div", "mc-doc-body");
    if ((s.errors || []).length) body.append(el("p", "mc-error", s.errors.map((e) => typeof e === "string" ? e : e.message).join(" · ")));
    if (mcCurrentChanged(s)) body.append(el("p", "mc-warning", "현재 문서가 비교 결과보다 바뀌었습니다. 반영이 끝난 뒤 비교를 새로고침하세요."));
    const ready = mcReadiness(s, m.mode === "labels" ? "stage1" : "stage2");
    if (ready === "unsupported") body.append(el("p", "mc-empty", "이 형식의 헤딩·서식 비교는 지원 예정입니다."));
    else if (m.mode === "review") mcReviewItems(body, s);
    else if (ready === "missing" || ready === "invalid") {
      body.append(el("p", "mc-empty", ready === "invalid" ? "저장된 분석을 읽지 못했습니다. 이 문서의 분석을 확인해 주세요." : `이 문서의 ${m.mode === "labels" ? "서식 라벨" : "템플릿"} 분석이 없습니다. 문서를 열고 헤딩 추출에서 분석을 실행하세요.`));
    } else {
      if (ready === "stale") body.append(el("p", "mc-warning", "추출 후 문서가 바뀐 결과입니다. 다시 추출한 뒤 비교하세요."));
      if (m.mode === "templates") mcTemplates(body, s, candidates); else mcLabels(body, s);
    }
    column.append(body);
    grid.append(column);
  }
  scroll.append(grid);
  box.replaceChildren(scroll, el("p", "mc-notice", "사용자 확인 표시는 이 브라우저에만 저장됩니다. 분석 완료나 병합 가능 여부를 뜻하지 않으며, 문서·분석이 바뀌면 다시 확인해야 합니다."));
}

function mcDocHead(s) {
  const header = el("header", "mc-doc-head"), sm = s.summary || {};
  header.append(el("strong", null, s.work.name), el("div", "mc-source", `${s.work.id === state.id ? "현재 문서 · " : ""}작업 ${s.work.id} · 수정 ${s.work.rev || 0}회`));
  for (const [key, name] of [["stage1", "라벨"], ["stage2", "템플릿"]]) {
    const meta = (sm[key] || {}).meta, status = mcReadiness(s, key);
    header.append(el("div", "mc-doc-meta" + (status === "stale" || status === "invalid" ? " mc-warning" : ""),
      `${name} · ${MC_READY[status] || status}${meta ? ` · 실행 ${meta.run ?? "–"} · ${fmtWhen(meta.at)}` : ""}`));
  }
  const label = el("label", "mc-review"), cb = el("input"), caption = el("span", null, "이 문서 확인");
  cb.type = "checkbox";
  cb.checked = mcCanReview(s) && mcReviewed(s);
  cb.disabled = !mcCanReview(s);
  cb.setAttribute("aria-label", `${s.work.name} 분석 결과 사용자 확인`);
  label.title = cb.disabled ? "최신 라벨·템플릿 분석을 불러온 뒤 확인할 수 있습니다." : "현재 분석을 직접 살펴봤다는 사용자 표시";
  cb.onchange = async () => {
    if (!cb.checked) { mcSetReviewed(s, false); return; }
    const m = mergeCompare, seq = m.seq, epoch = state.epoch;
    cb.disabled = true;
    caption.textContent = "분석 시점 확인 중…";
    try {
      const latest = await api(`/api/works/${encodeURIComponent(s.work.id)}/headings-preview`);
      if (mergeCompare !== m || seq !== m.seq || epoch !== state.epoch) return;
      const at = m.snapshots.indexOf(s);
      if (at < 0) return;
      m.snapshots[at] = latest;
      if (mcReviewKey(latest) !== mcReviewKey(s) || !mcCanReview(latest)) {
        mcSetReviewed(s, false);
        m.notice = "문서 또는 분석이 바뀌어 최신 결과를 다시 불러왔습니다. 내용을 다시 확인해 주세요.";
      } else if (!mcSetReviewed(latest, true)) m.notice = "브라우저 저장소를 사용할 수 없어 확인 표시를 저장하지 못했습니다.";
      else m.notice = `${latest.work.name}의 현재 분석을 확인 표시했습니다.`;
      mcDraw();
    } catch (e) {
      if (mergeCompare !== m || seq !== m.seq || epoch !== state.epoch) return;
      m.notice = `최신 분석을 확인하지 못해 표시를 저장하지 않았습니다: ${e.message}`;
      mcDraw();
    }
  };
  label.append(cb, caption);
  header.append(label);
  return header;
}

function mcMatches(...values) {
  const q = mergeCompare.query.trim().toLocaleLowerCase("ko-KR");
  return !q || values.filter((x) => x != null).join(" ").toLocaleLowerCase("ko-KR").includes(q);
}

function mcAppendPaged(body, items, make, empty) {
  if (!items.length) { body.append(el("p", "mc-empty", empty)); return; }
  const list = el("div", "mc-items");
  let count = 0;
  const more = hBtn("", () => append(), { cls: "btn sm mc-more" });
  const append = () => {
    for (const item of items.slice(count, count + 40)) list.append(make(item));
    count = Math.min(count + 40, items.length);
    more.textContent = `${nf(items.length - count)}개 더 보기`;
    more.hidden = count === items.length;
  };
  append();
  body.append(list, more);
}

function mcTemplates(body, s, candidates) {
  const graph = s.graph || {}, firstMeta = ((s.summary || {}).stage1 || {}).meta || {};
  const sameRun = firstMeta.run != null && (graph.meta || {}).stage1Run === firstMeta.run;
  const all = graph.templates || [], labels = new Map((sameRun ? (s.labels || {}).labels || [] : []).map((l) => [l.id, l]));
  if (!sameRun) body.append(el("p", "mc-warning", "그래프와 현재 라벨의 기준 실행이 달라 대표 서식 번호만 표시합니다. 최신 라벨 설명과 연결하지 않습니다."));
  const matches = all.filter((t) => mcMatches(t.displayName, t.name, (t.chain || []).join(" › "),
    ...(t.slots || []).map((slot) => (labels.get(slot.format) || {}).name)));
  matches.sort((a, b) => {
    const ac = (candidates.get(mcTemplateKey(a)) || new Set()).size > 1, bc = (candidates.get(mcTemplateKey(b)) || new Set()).size > 1;
    return Number(bc) - Number(ac) || String(mcTemplateKey(a) || a.name).localeCompare(String(mcTemplateKey(b) || b.name), "ko");
  });
  body.append(el("p", "mc-doc-meta", `템플릿 ${nf(matches.length)} / ${nf(all.length)}개`));
  mcAppendPaged(body, matches, (t) => {
    const item = el("article", "mc-item"), head = el("div", "mc-item-head");
    const ref = typeof tplRef === "function" ? tplRef(t.no || t.id, t.name) : `#${t.no || t.id || "–"}`;
    head.append(el("strong", null, `${ref} · ${H_TPL[t.kind] || t.kind || "템플릿"}`));
    const candidate = candidates.get(mcTemplateKey(t));
    if (candidate && candidate.size > 1 && candidate.has(s.work.id)) {
      head.append(el("span", "mc-chip candidate", `${candidate.size}개 문서에 같은 사슬`));
    }
    item.append(head, el("p", "mc-chain", (t.chain || []).join(" › ") || t.displayName || t.name || "사슬 정보 없음"),
      el("p", "mc-doc-meta", t.scope === "cell" ? "표 칸" : t.scope === "body" ? "본문" : "범위 정보 없음"));
    const slots = el("ul", "mc-slots");
    for (const slot of t.slots || []) {
      const li = el("li"), label = labels.get(slot.format);
      li.append(el("b", null, `L${slot.level} · ${slot.letter || "–"}`), el("div", null,
        label ? `${slot.format} · ${label.name}` : slot.format ? `${slot.format} · 대표 서식 설명 없음` : "대표 서식 없음"));
      if (label) li.append(mcFormat(label));
      if (slot.rep) li.append(mcSource(s, slot.rep, "대표 문단"));
      slots.append(li);
    }
    item.append(slots);
    if (!slots.childElementCount) item.append(el("p", "muted", "레벨별 서식 정보가 없습니다."));
    return item;
  }, all.length ? "검색에 맞는 템플릿이 없습니다." : "추출된 템플릿이 0개입니다.");
}

function mcLabels(body, s) {
  const all = ((s.labels || {}).labels || []), items = all.filter((l) => mcMatches(l.id, l.name, l.sample));
  items.sort((a, b) => (b.count || 0) - (a.count || 0));
  body.append(el("p", "mc-doc-meta", `서식 라벨 ${nf(items.length)} / ${nf(all.length)}개`));
  mcAppendPaged(body, items, (l) => {
    const item = el("article", "mc-item"), head = el("div", "mc-item-head");
    head.append(el("strong", null, l.id), el("span", "mc-chip", `${nf(l.count)}문단`));
    item.append(head, el("p", "mc-chain", l.name), el("p", "mc-doc-meta",
      Object.entries(l.kinds || {}).map(([k, n]) => `${H_KIND[k] || k} ${nf(n)}`).join(" · ")), mcFormat(l));
    if (l.sample) item.append(mcSource(s, l.sample, "대표 문단"));
    return item;
  }, all.length ? "검색에 맞는 라벨이 없습니다." : "추출된 서식 라벨이 0개입니다.");
}

function mcFormat(l) {
  const d = el("details", "mc-format"), dl = el("dl", "mc-format-grid"), p = l.para || {}, c = (l.char || {}).text || {}, letter = (l.char || {}).letter;
  d.append(el("summary", null, "서식 값 비교"));
  const v = (x, unit = "") => x == null ? "정보 없음" : `${x}${unit}`;
  const row = (k, value) => dl.append(el("dt", null, k), el("dd", null, value));
  row("글꼴 / 크기", `${v(c.font)} / ${v(c.sizePt, "pt")}`);
  row("글자 모양", [c.bold ? "굵게" : "보통", c.italic && "기울임", c.underline && "밑줄"].filter(Boolean).join(" · "));
  row("글자 색", v(c.color));
  row("장평 / 자간", `${v(c.ratioPct, "%")} / ${v(c.spacingPct, "%")}`);
  row("정렬", ({ left: "왼쪽", right: "오른쪽", center: "가운데", justify: "양쪽", distribute: "배분", distribute_space: "나눔" })[p.align] || v(p.align));
  row("왼쪽 / 오른쪽", `${v(p.indentLeftMm, "mm")} / ${v(p.indentRightMm, "mm")}`);
  row("첫 줄", v(p.firstLineMm, "mm"));
  row("문단 위 / 아래", `${v(p.spaceBeforePt, "pt")} / ${v(p.spaceAfterPt, "pt")}`);
  row("줄 간격", p.lineSpacing ? `${v(p.lineSpacing.value, p.lineSpacing.unit || "")} · ${p.lineSpacing.type || ""}` : "정보 없음");
  row("레터 앞 / 뒤 빈칸", `${l.leadCode || "없음"} / ${l.gapCode || "없음"}`);
  if (letter) row("레터 글꼴", `${v(letter.font)} / ${v(letter.sizePt, "pt")}${letter.bold ? " · 굵게" : ""}`);
  d.append(dl);
  return d;
}

function mcSource(s, id, label) {
  if (s.work.id === state.id && !mcCurrentChanged(s) && /^p/.test(id)) {
    return hBtn(`${label} ${id} ↗`, () => { showTab("Heads"); headsGo(id); }, { title: `${s.work.name}에서 해당 문단 보기` });
  }
  return el("span", "mc-source", `${label} ${id} · ${s.work.id === state.id ? "비교 새로고침 후 이동" : "해당 문서에서 확인"}`);
}

function mcReviewItems(body, s) {
  const sm = s.summary || {}, first = sm.stage1 || {}, second = sm.stage2 || {}, items = [];
  for (const [stage, name] of [["stage1", "서식 라벨"], ["stage2", "템플릿"]]) {
    const status = mcReadiness(s, stage);
    if (status !== "ready") items.push({ title: `${name} · ${MC_READY[status] || status}`, text: "해당 문서의 헤딩 추출 화면에서 최신 분석을 준비하세요." });
  }
  for (const [key, name] of [["unmatched", "규칙에 맞지 않는 문단"], ["conflicts", "규칙 충돌"]]) {
    for (const g of (first.review || {})[key] || []) {
      items.push({ title: `${name} · ${g.shape || "–"} · ${nf(g.count)}문단`, text: (g.examples || []).map((e) => e.text).join(" / "), para: (g.examples || [])[0]?.id });
    }
  }
  for (const a of (s.graph || {}).adjustments || []) {
    if (a.decision !== "undecided" && (a.review || {}).verdict !== "disagree" && (a.review || {}).verdict !== "failed") continue;
    if (((s.graph || {}).llm || {}).pairs === false && !a.review) continue; // 서식 쌍 판정(C·D)을 하지 않은 실행(기본 — spec_헤딩_추출 ② §6)의 「미판정」 은 확인할 항목이 아니다
    items.push({ title: (a.review || {}).verdict === "disagree" ? "조정 재검토 불일치" : "서식 조정 미확정",
      text: `${a.from || "–"} → ${a.to || "–"} · ${(a.review || {}).reason || a.reason || "판단 근거 없음"}`, para: a.para });
  }
  for (const node of (s.graph || {}).nodes || []) {
    if (node.undecided) items.push({ title: "헤딩 미판정", text: `${node.letter || ""} ${node.text || ""}`, para: node.para });
  }
  for (const message of first.warnings || []) items.push({ title: "추출 안내", text: String(message) });
  if ((second.llm || {}).error) items.push({ title: "템플릿 분석 오류", text: second.llm.error });
  const matches = items.filter((x) => mcMatches(x.title, x.text));
  body.append(el("p", "mc-doc-meta", `확인할 항목 ${nf(matches.length)} / ${nf(items.length)}개`));
  mcAppendPaged(body, matches, (x) => {
    const item = el("article", "mc-item");
    item.append(el("strong", null, x.title), el("p", null, x.text));
    if (x.para) item.append(mcSource(s, x.para, "문단"));
    return item;
  }, items.length ? "검색에 맞는 확인 항목이 없습니다." : "저장된 분석에서 확인할 항목이 보고되지 않았습니다. 라벨과 템플릿의 실제 대응은 직접 확인하세요.");
}
