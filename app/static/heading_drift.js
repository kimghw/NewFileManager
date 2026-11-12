"use strict";
// 뼈대 유지(spec_헤딩_추출 ② §17, 2026-11-10 사용자 "문서가 바뀔 때마다 헤딩을 다시 추출하라고 하면 어쩌냐? 한번 하면 그 구조는 그냥 그 뼈대로 그냥 두고 .. 새로운 레터나 서식이 추가되면
// 알람이나 표시만 해줘") — 2단계(헤딩 그래프·템플릿)·3단계(표 구조) 결과는 한 번 만들면 그 문서의 뼈대다. 문서를 고쳐도 「재확인 필요」·「다시 만드세요」 를 띄우지 않고,
// 뼈대를 만든 뒤 문서에 생긴 것만 알린다: 새 레터 · 새 서식(2단계) · 새 표 · 헤더(열헤더·행헤더)가 바뀐 표(3단계 — 행·열 수만 달라진 표는 같은 표).
// 견주기는 서버 스크립트(app/heading_drift.py — LLM 없음 · 실행으로 저장 안 함), 여기는 언제 견줄지와 보이기:
//   · 견주는 때 — 문서를 고친 뒤 DRIFT_IDLE_MS 동안 더 고치지 않았을 때(driftTouch — app.js headsMarkStale) · 헤딩 상태를 그릴 때 결과·문서 차례가 달라졌으면(driftSync — headsRender) ·
//     문서를 연 직후 읽은 요약으로도(driftSeed — app.js headsPeek: 이어 연 작업은 헤딩 탭을 열지 않아도 견준다)
//   · 상태 줄 꼬리표(driftChip — headsResultsSummary) · 단계 탭 점(headsStageStale 이 driftCount 를 본다) · 2·3단계 카드 줄(driftCardRow) · 「표」 탭 상태(tables.js tablesDraw)
//   · 문서 표시 — 쪽 왼쪽 여백 「새 레터」·「새 서식」(driftMarkOf — app.js tplMarksDraw) · 뼈대 밖 목록(2열 kind "drift" — driftView) · 새 묶음이 생기면 알림(toast)
// app.js 가 주는 것: state·heads·$·el·api·toast·hBtn·hTable·hCell·hFoot·headsDlg·headsParaLink·headsGo·headsRunOpen·headsResultsSummary·headsStageStale·showTab·tplMarksDraw·nf·short·
// hasBlock·H_STAGE_TITLE·H_STAGE_STATE(+ panel_help.js 의 hHelp · tables.js 의 tablesDraw). app.js·tables.js 가 부르는 것은 모두 typeof 검사 뒤. 서버 짝은 app/heading_drift_api.py.
// index.html 이 app.js·tables.js 다음에 읽는다. 화면 게이트: tools/smoke_heading_drift_ui.py(임시 서버) · artifacts/ui_heads_panel_2026-11-10/check_heads_panel.py 1-2절.
const driftFresh = () => ({ key: null, data: null, loading: null, failed: null, error: "", off: false, timer: null, editedAt: 0, marks: new Map(), seen: null, drawn: null, tab3: "", sum: null });
const DRIFT = driftFresh(); // key = 견준 대상(driftIdent) · seen = 앞서 본 묶음(새로 생긴 것만 알림) · drawn/tab3 = 문서 표시·「표」 탭을 그린 때의 답 · sum = 문서를 열 때 읽어 둔 요약(heads.view 가 생기기 전)
const DRIFT_HEAD = { colhead: "열헤더", rowhead: "행헤더", corner: "귀퉁이" };
const driftSum = () => heads.view || DRIFT.sum; // 헤딩 요약 — 헤딩 탭을 연 뒤에는 그것, 그 전에는 문서를 열 때 읽어 둔 것
const DRIFT_IDLE_MS = 4000; // 문서를 고친 뒤 이만큼 더 고치지 않으면 견준다(큰 문서는 서버가 문서를 다시 읽는 1~2초 동안 편집 응답이 밀린다 — 타자 중에는 돌리지 않는다)
const DRIFT_SOON_MS = 300; // 결과가 바뀐 뒤(실행이 끝남 · 문서를 엶)
const DRIFT_SCOPE = { body: "본문", cell: "표 칸" };
const DRIFT_KIND = { marker: "레터", label: "괄호 줄", outline: "개요 번호", title: "제목 꼴" };
const driftUrl = () => `/api/docs/${encodeURIComponent(state.id)}/headings/drift`;

function driftReset() { // 문서를 열거나 닫을 때(app.js headsReset)
  clearTimeout(DRIFT.timer);
  Object.assign(DRIFT, driftFresh());
}

function driftIdent(r = driftSum()) { // 견준 답이 맞는 대상 = (문서 차례, 1·2·3단계 실행, TEMP) — 2·3단계 결과가 없으면 null(견줄 뼈대가 없다)
  if (!state.id || state.format === "docx" || !r || !(r.stage2 || r.stage3)) return null;
  const run = (s) => (s && s.meta ? `${s.meta.run}@${s.meta.at}` : "-");
  return [state.serverRev, run(r.stage1), run(r.stage2), run(r.stage3), r.temp ? r.temp.key : ""].join("|");
}
const driftCurrent = (r = driftSum()) => !!DRIFT.key && DRIFT.key === driftIdent(r); // 지금 문서·결과와 견준 답인가
const driftStamp = () => `${DRIFT.key}|${DRIFT.loading ? 1 : 0}|${DRIFT.error}|${driftCount()}`; // 요약을 다시 그릴 때를 아는 값(app.js headsResultsSummary 의 renderKey)

function driftPlan(ms) { // 견줄 때를 잡는다 — 방금 고친 문서는 DRIFT_IDLE_MS 가 지난 뒤에
  clearTimeout(DRIFT.timer);
  DRIFT.timer = setTimeout(driftLoad, Math.max(ms, DRIFT.editedAt + DRIFT_IDLE_MS - Date.now()));
}

function driftTouch() { // 문서를 고칠 때마다(app.js headsMarkStale — 편집 응답)
  if (!driftIdent()) return;
  if (!DRIFT.off) {
    DRIFT.editedAt = Date.now();
    DRIFT.failed = null;
    driftPlan(DRIFT_IDLE_MS);
  }
  driftCards(); // 카드 줄은 바로 「뼈대 유지 · 견주는 중…」
}

function driftSeed(r) { // 문서를 연 직후 읽은 요약(app.js headsPeek — heads.view 는 안 건드린다): 이어 연 작업은 헤딩 탭을 열지 않아도 견주고, 고칠 때마다(driftTouch) 다시 견준다
  if (heads.view || !r) return; // 그 사이 헤딩 요약을 읽었으면(첫 분석·탭) 그쪽이 맡는다
  DRIFT.sum = r;
  driftSync(r);
}

function driftSync(r) { // 헤딩 상태를 그릴 때마다(app.js headsRender) — 결과(실행)·문서 차례가 견준 것과 다르면 다시 견준다
  const key = driftIdent(r);
  if (!key) { if (DRIFT.key || DRIFT.data) { driftReset(); driftRedraw(); } return; }
  if (key === DRIFT.key || key === DRIFT.loading || key === DRIFT.failed || DRIFT.timer || DRIFT.off) return;
  if (r.job && r.job.status === "running") return; // 끝나면 다시 그린다 — 그때
  driftPlan(DRIFT_SOON_MS);
}

async function driftLoad() {
  DRIFT.timer = null;
  const r = driftSum(), key = driftIdent(r);
  if (!key || key === DRIFT.key || DRIFT.loading) return; // 읽는 중이면 그 답이 온 뒤 다시 본다(finally)
  if (r.job && r.job.status === "running") return;
  const epoch = state.epoch;
  DRIFT.loading = key;
  driftRedraw();
  try {
    const d = await api(driftUrl());
    if (epoch !== state.epoch) return;
    DRIFT.error = "";
    if (d.rev === state.serverRev && key === driftIdent()) driftSet(key, d); // 그 사이 문서를 고쳤으면 버린다 — 고친 쪽(driftTouch)이 다시 잡아 두었다
  } catch (e) {
    if (epoch !== state.epoch) return;
    DRIFT.error = e.status === 404 ? "" : e.message || "읽지 못함";
    DRIFT.off = e.status === 404; // 견주기 끝점이 없는 옛 서버(다시 켜기 전) — 이 문서를 다시 열 때까지 묻지 않고 조용히 「뼈대 유지」 만 보인다
    DRIFT.failed = key; // 같은 대상을 저절로 다시 묻지 않는다(「다시 견주기」·다음 편집 때)
  } finally {
    if (epoch === state.epoch) {
      DRIFT.loading = null;
      driftRedraw();
      const now = driftIdent();
      if (now && now !== DRIFT.key && now !== DRIFT.failed && !DRIFT.timer && !DRIFT.off) driftPlan(DRIFT_IDLE_MS);
    }
  }
}

function driftGroups(d) { // 묶음마다 이름표 — 앞서 본 것과 견줘 새로 생긴 묶음만 알린다
  const out = new Map();
  const s2 = (d && d.stage2) || {}, s3 = (d && d.stage3) || {};
  for (const it of s2.letters || []) out.set(`L|${it.scope}|${it.kind}|${it.shape}`, `새 레터 「${short(it.letter || it.shape, 16)}」`);
  for (const it of s2.formats || []) out.set(`F|${it.scope}|${it.kind}|${it.shape}|${it.name}`, `「${short(it.letter || it.shape, 16)}」 의 새 서식`);
  for (const t of s3.new || []) out.set(`T|${t.id}`, `새 표 ${t.rows}×${t.cols}`);
  for (const t of s3.changed || []) out.set(`C|${t.id}|${JSON.stringify(t.heads || {})}`, `헤더가 바뀐 표 ${t.id}`);
  return out;
}

function driftSet(key, d) {
  DRIFT.key = key;
  DRIFT.data = d;
  DRIFT.marks = new Map();
  const s2 = d.stage2 || {};
  for (const [what, list] of [["format", s2.formats || []], ["letter", s2.letters || []]]) { // 새 레터가 새 서식보다 앞선다(같은 문단이면 「새 레터」)
    for (const it of list) for (const pid of it.paras || []) DRIFT.marks.set(pid, { what, it });
  }
  const groups = driftGroups(d);
  if (DRIFT.seen) { // 문서를 열 때 이미 있던 것은 알리지 않는다 — 고치다가 생긴 것만
    const fresh = [...groups].filter(([k]) => !DRIFT.seen.has(k)).map(([, v]) => v);
    if (fresh.length) {
      toast(`뼈대에 없는 ${fresh[0]}${fresh.length > 1 ? ` 외 ${nf(fresh.length - 1)}` : ""} — 뼈대(헤딩·표 구조)는 그대로 씁니다`, false,
        { label: "보기", run: () => { if (typeof showTab === "function") showTab("Heads"); driftView(); } });
    }
  }
  DRIFT.seen = new Set(groups.keys());
}

// ---- 수 · 글 -----------------------------------------------------------------------------------------------------
function driftCount(k = 0) { // k = 2(새 레터 + 새 서식 묶음) · 3(새 표 + 헤더가 바뀐 표) · 0(모두)
  const d = DRIFT.data;
  if (!d) return 0;
  const c2 = (d.stage2 && d.stage2.counts) || {}, c3 = (d.stage3 && d.stage3.counts) || {};
  const n2 = (c2.letters || 0) + (c2.formats || 0), n3 = (c3.new || 0) + (c3.changed || 0);
  return k === 2 ? n2 : k === 3 ? n3 : n2 + n3;
}

function driftText(k = 0) { // 「새 레터 2 · 새 서식 1 · 새 표 1」
  const d = DRIFT.data || {}, c2 = (d.stage2 && d.stage2.counts) || {}, c3 = (d.stage3 && d.stage3.counts) || {};
  const parts = [];
  if (k !== 3) { if (c2.letters) parts.push(`새 레터 ${nf(c2.letters)}`); if (c2.formats) parts.push(`새 서식 ${nf(c2.formats)}`); }
  if (k !== 2) { if (c3.new) parts.push(`새 표 ${nf(c3.new)}`); if (c3.changed) parts.push(`헤더가 바뀐 표 ${nf(c3.changed)}`); }
  return parts.join(" · ");
}

// ---- 상태 줄 · 단계 탭 · 카드 줄 --------------------------------------------------------------------------------------------
function driftChip() { // 헤딩 탭 위 요약의 상태 줄(app.js headsResultsSummary) — 뼈대에 없는 것이 있을 때만(없으면 null → 「추출 결과」)
  if (!driftCount()) return null;
  const b = hBtn("", () => driftView(), { cls: "analysis-state stale drift-chip" });
  b.append(el("span", "drift-what", driftText()));
  b.title = `뼈대(헤딩 그래프·표 구조)를 만든 뒤 문서에 생긴 것 — ${driftText()}\n뼈대는 그대로 씁니다(다시 만들지 않아도 됩니다) · 누르면 목록`;
  return b;
}

function driftTabs(r = heads.view) { // 「추출·설정」 단계 탭의 점 — 고른 탭은 건드리지 않고 2·3단계의 「새 항목 있음」 표시만 맞춘다
  if (!r) return;
  for (const k of [2, 3]) {
    const b = $(`headsStageTab${k}`);
    if (!b || (b.dataset.state && b.dataset.state !== "stale")) continue; // 도는 중·실패·결과 없음은 그대로
    const st = headsStageStale(r, k) ? "stale" : "";
    b.dataset.state = st;
    b.title = H_STAGE_TITLE[k] + (st ? ` · ${H_STAGE_STATE[st]}` : "");
  }
}

const DRIFT_KEEP = { // 카드 줄의 도움말 — 단계마다
  2: "헤딩 그래프(템플릿·레벨)는 한 번 만들면 이 문서의 뼈대입니다. 만든 뒤 문서가 바뀌었거나 1단계를 다시 뽑았지만 이 구조를 그대로 씁니다 — 다시 분석하지 않아도 됩니다.\n뼈대를 만들 때 문서에 없던 레터, 그 레터가 쓰지 않던 서식이 문서에 생기면 여기와 문서 여백에 알립니다. 그것까지 뼈대에 넣으려면 아래에서 다시 분석하세요.",
  3: "표 구조는 한 번 만들면 이 문서의 뼈대입니다. 만든 뒤 문서가 바뀌었거나 1단계를 다시 뽑았지만 이 표 구조를 그대로 씁니다 — 다시 분석하지 않아도 됩니다.\n뼈대를 만들 때 문서에 없던 표, 열헤더·행헤더가 바뀐 표가 생기면 여기에 알립니다(자료 행을 더하거나 지워 행·열 수만 달라진 표는 같은 표로 봅니다). 그것까지 뼈대에 넣으려면 아래에서 다시 분석하세요.\n"
    + "주의: 문서를 고친 뒤 표 구조만 다시 만들면 표의 소속(헤딩·구분 라벨)은 헤딩 그래프가 아니라 1단계 어림으로 정해지고 「소속 재확인 필요」 가 남습니다 — 그래프 소속까지 맞추려면 헤딩 그래프(2단계)부터 다시 만들어야 합니다.",
};

function driftCardRow(r, k) { // 「추출·설정」 2·3단계 카드(app.js headsCard2·headsCard3) — 문서가 바뀐 뒤에만 줄이 생긴다. 꼴은 카드의 다른 알림과 같은 한 줄(.stage-notice + 도움말)
  const box = el("div", "hdrift");
  box.dataset.stage = k;
  const s = r && r[`stage${k}`];
  if (!s) return box;
  const d = driftCurrent(r) && DRIFT.data ? DRIFT.data[`stage${k}`] : null, n = d ? driftCount(k) : 0;
  if (!s.stale && !(d && d.moved)) return box;
  const failed = !d && !!DRIFT.error && !DRIFT.loading;
  const quiet = !d && !failed && (DRIFT.off || (!DRIFT.loading && !DRIFT.timer)); // 견줄 수 없음(옛 서버) — 안내만
  const line = el("div", `stage-notice${n || failed ? " is-warning" : ""}`);
  const label = n ? driftText(k)
    : d ? `뼈대 유지 · 새 ${k === 2 ? "레터·서식" : "표"} 없음${k === 2 && d.formatsChecked === false ? "(레터만 견줌)" : ""}`
      : failed ? "뼈대 유지 · 견주지 못함" : quiet ? "뼈대 유지" : "뼈대 유지 · 지금 문서와 견주는 중…";
  line.append(el("span", null, label));
  const detail = DRIFT_KEEP[k] + (failed ? `\n\n지금 문서와 견주지 못했습니다: ${DRIFT.error}` : "")
    + (k === 2 && d && d.formatsChecked === false ? "\n\n이 뼈대를 만든 때의 1단계 결과를 찾지 못해 서식은 견주지 못했습니다(레터만)." : "");
  line.append(hHelp(`${label} 상세`, detail, { warning: !!n || failed }));
  if (n) line.append(hBtn("목록", () => driftView(), { cls: "stage-notice-act", title: "문서 옆 열에 — 누르면 문서의 그 문단·표로" }));
  else if (failed) line.append(hBtn("다시", () => driftForce(), { cls: "stage-notice-act", title: "지금 문서를 뼈대와 다시 견줍니다" }));
  box.append(line);
  return box;
}

function driftCards() { // 카드 줄만 다시(가볍다 — 문서를 고칠 때마다)
  for (const box of document.querySelectorAll(".hdrift")) box.replaceWith(driftCardRow(heads.view || {}, Number(box.dataset.stage))); // 카드는 헤딩 탭을 연 뒤에만 있다
}

function driftRedraw() { // 문서 표시 · 열려 있는 목록 · 카드 줄 · 단계 탭 점 · 상태 줄 · 「표」 탭 — 문서 표시와 「표」 탭은 견준 답이 달라졌을 때만 다시 그린다
  if (DRIFT.drawn !== DRIFT.key && typeof tplMarksDraw === "function") { DRIFT.drawn = DRIFT.key; tplMarksDraw(); }
  if (heads.dlg === "drift") { heads.keepFold = true; try { driftView(); } finally { heads.keepFold = false; } }
  driftCards();
  if (!heads.view) return;
  driftTabs(heads.view);
  if (typeof headsResultsSummary === "function") headsResultsSummary(heads.view);
  const t3 = driftText(3);
  if (t3 !== DRIFT.tab3 && typeof tablesDraw === "function") { DRIFT.tab3 = t3; tablesDraw(); }
}

function driftForce() { // 「다시 견주기」
  DRIFT.key = null;
  DRIFT.failed = null;
  DRIFT.off = false;
  DRIFT.editedAt = 0;
  driftPlan(0);
}

// ---- 문서 표시 ---------------------------------------------------------------------------------------------------
const driftMarkCount = () => DRIFT.marks.size;
function driftMarkOf(pid, m) { // app.js tplMarksDraw — 그 문단의 여백 표시 m(「TN Lk」 · 없으면 null)에 「새 레터」·「새 서식」 을 얹는다. 뼈대 밖 문단이 아니면 null
  const x = DRIFT.marks.get(pid);
  if (!x) return null;
  const it = x.it, text = x.what === "letter" ? "새 레터" : "새 서식";
  const title = (x.what === "letter"
    ? `새 레터 「${it.letter || it.shape}」 — 뼈대(헤딩 그래프)를 만들 때 ${DRIFT_SCOPE[it.scope] || it.scope}에 없던 ${DRIFT_KIND[it.kind] || it.kind}`
    : `새 서식 — 「${it.letter || it.shape}」 가 쓰지 않던 서식\n지금: ${it.name}${(it.known || []).length ? `\n쓰던 서식: ${it.known.join(" / ")}` : ""}`)
    + "\n뼈대는 그대로 씁니다 · 누르면 뼈대 밖 목록";
  // 새 서식은 그 줄의 「TN Lk」 앞에 붙인다. 새 레터는 그것만 — 레터가 바뀐 줄에 남아 있는 옛 「TN Lk」(뼈대는 고치기 전 문서 기준)는 그 줄의 것이 아니다(도움말에만)
  if (m && !m.temp && x.what === "format") return { ...m, text: `${text} ${m.text}`, title: `${title}\n—\n${m.title}`, drift: true };
  return { text, title: m && !m.temp ? `${title}\n—\n(레터를 바꾸기 전) ${m.title}` : title, no: null, und: false, lbl: false, drift: true };
}

// ---- 뼈대 밖 목록(2열 kind "drift") ------------------------------------------------------------------------------------------
function driftParas(it) { // 예문(첫 문단으로) + 나머지 문단 번호 단추
  const td = el("td", "txt");
  const ids = it.paras || [];
  td.append(headsParaLink(ids[0], it.text || it.letter || "(글 없음)", 40));
  const more = ids.slice(1, 7);
  more.forEach((pid, i) => {
    if (!hasBlock(pid)) return;
    const b = el("button", "hlink drift-n", String(i + 2));
    b.type = "button";
    b.title = `문서에서 ${i + 2}번째 문단으로 · ${pid}`;
    b.onclick = () => headsGo(pid);
    td.append(" ", b);
  });
  if (it.count > 1 + more.length) td.append(" ", el("span", "muted", `+${nf(it.count - 1 - more.length)}`));
  return td;
}

function driftLetterName(it) {
  if (it.kind === "label") return it.shape === "[…]" ? "괄호 소제목" : `구분 라벨 ${it.shape}`;
  return DRIFT_KIND[it.kind] || it.kind;
}

function driftView() {
  if (!state.id) return;
  const { tools, body } = headsDlg("drift", "뼈대 밖 목록", "뼈대를 만든 뒤 문서에 생긴 레터·서식·표");
  const d = DRIFT.data, cur = driftCurrent();
  tools.append(el("span", "muted", !d ? (DRIFT.loading ? "지금 문서와 견주는 중…" : DRIFT.error ? `견주지 못했습니다: ${DRIFT.error}` : "아직 견주지 않았습니다")
    : driftCount() ? `${driftText()} — 뼈대는 그대로 씁니다` : "뼈대에 없는 레터·서식·표가 없습니다"));
  if (!DRIFT.loading) tools.append(hBtn("다시 견주기", () => driftForce(), { title: "지금 문서를 뼈대와 다시 견줍니다(스크립트 — LLM 호출 없음)" }));
  const wrap = el("div", "temp-wrap drift-wrap"); // 배치는 TEMP 목록과 같은 꼴(style.css .temp-wrap·.temp-head·table.temp-list)
  wrap.append(el("p", "hnote", "헤딩 그래프(2단계)와 표 구조(3단계)는 한 번 만들면 이 문서의 뼈대입니다 — 문서를 고쳐도 다시 만들지 않습니다. "
    + "아래는 뼈대를 만들 때 문서에 없던 것입니다. 뼈대에 넣으려면 「추출·설정」 에서 그 단계를 다시 만드세요."));
  if (d && !cur) wrap.append(el("p", "hnote", DRIFT.loading ? "문서가 바뀌어 다시 견주는 중 — 아래는 앞서 견준 것입니다." : "문서가 바뀌었습니다 — 잠시 뒤 다시 견줍니다(아래는 앞서 견준 것)."));
  const s2 = (d && d.stage2) || null, s3 = (d && d.stage3) || null;
  const head = (name, note, stage) => {
    const h = el("div", "temp-head");
    h.append(el("b", null, name), el("span", "muted", note), hBtn(`${stage}단계 열기`, () => { if (typeof showTab === "function") showTab("Heads"); headsRunOpen(stage); },
      { title: `「추출·설정」 의 ${stage}단계 — 다시 만들면 뼈대에 들어갑니다` }));
    wrap.append(h);
  };
  if (s2 && (s2.letters || []).length) {
    head("새 레터", `${nf(s2.counts.letters)}가지 · 문단 ${nf(s2.counts.letterParas)} — 그 자리에 없던 레터`, 2);
    const [tbl, tb] = hTable(["레터", "자리", "종류", "문단", "예문"]);
    tbl.classList.add("temp-list", "drift-list");
    for (const it of s2.letters) {
      const tr = el("tr");
      hCell(tr, short(it.letter || it.shape, 24), "drift-letter", it.shape !== it.letter ? `정규 꼴 ${it.shape}` : "");
      hCell(tr, DRIFT_SCOPE[it.scope] || it.scope);
      hCell(tr, driftLetterName(it));
      hCell(tr, nf(it.count));
      tr.append(driftParas(it));
      tb.append(tr);
    }
    wrap.append(tbl);
  }
  if (s2 && (s2.formats || []).length) {
    head("새 서식", `${nf(s2.counts.formats)}가지 · 문단 ${nf(s2.counts.formatParas)} — 그 레터가 쓰지 않던 서식(오차 밖)`, 2);
    const [tbl, tb] = hTable(["레터", "자리", "지금 서식", "문단", "예문"]);
    tbl.classList.add("temp-list", "drift-list");
    for (const it of s2.formats) {
      const tr = el("tr");
      hCell(tr, short(it.kind === "marker" ? it.letter || it.shape : it.shape, 24), "drift-letter", it.kind === "label" ? `괄호 줄 「${it.letter}」` : "");
      hCell(tr, DRIFT_SCOPE[it.scope] || it.scope);
      const f = hCell(tr, it.name, "drift-fmt", `지금 서식${it.fmt ? `(${it.fmt})` : ""}: ${it.name}${(it.known || []).length ? `\n그 레터가 쓰던 서식:\n· ${it.known.join("\n· ")}` : ""}`);
      if ((it.known || []).length) f.append(el("span", "muted drift-known", `쓰던 서식 — ${it.known[0]}`));
      hCell(tr, nf(it.count));
      tr.append(driftParas(it));
      tb.append(tr);
    }
    wrap.append(tbl);
  }
  if (s2 && s2.moved && s2.formatsChecked === false) wrap.append(el("p", "hnote", "서식은 견주지 못했습니다 — 이 뼈대를 만든 때의 1단계 결과를 찾지 못해 레터만 견줬습니다."));
  if (s3 && ((s3.new || []).length || (s3.changed || []).length)) {
    head("표", `새 표 ${nf(s3.counts.new)} · 헤더가 바뀐 표 ${nf(s3.counts.changed)}${s3.gone ? ` · 없어진 표 ${nf(s3.gone)}` : ""}${s3.resized ? ` · 행·열 수만 달라진 표 ${nf(s3.resized)}(같은 표로 봄)` : ""}`, 3);
    const [tbl, tb] = hTable(["표", "무엇", "크기", "바뀐 헤더"]);
    tbl.classList.add("temp-list", "drift-list");
    const row = (t, what, detail, title = "") => {
      const tr = el("tr"), td = el("td", "txt");
      td.append(headsParaLink(t.host, `표 ${t.id}`, 30, "표가 든 문단"));
      tr.append(td);
      hCell(tr, what);
      hCell(tr, `${t.rows}행 × ${t.cols}열${t.was && (t.was[0] !== t.rows || t.was[1] !== t.cols) ? ` (앞 ${t.was[0]}×${t.was[1]})` : ""}`);
      hCell(tr, detail, "drift-fmt", title);
      tb.append(tr);
    };
    for (const t of s3.new || []) row(t, "새 표", "", "표 구조(3단계)를 만든 뒤 문서에 생긴 표 — 헤더·필드·소속이 아직 없습니다");
    for (const t of s3.changed || []) {
      const h = t.heads || {}, ex = (t.examples || []).map((x) => (x.what === "text" ? `${DRIFT_HEAD[x.role] || x.role} 「${short(x.was, 16)}」 → 「${short(x.now, 16)}」`
        : x.what === "gone" ? `없어진 ${DRIFT_HEAD[x.role] || x.role} 「${short(x.was, 16)}」` : `새 ${DRIFT_HEAD[x.role] || x.role} 「${short(x.now, 16)}」`));
      const n = (h.text || 0) + (h.gone || 0) + (h.new || 0);
      row(t, "헤더가 바뀜", ex.join(" · ") + (n > ex.length ? ` 외 ${nf(n - ex.length)}` : ""), `글이 바뀐 헤더 ${nf(h.text || 0)} · 없어진 헤더 ${nf(h.gone || 0)} · 새 헤더 ${nf(h.new || 0)}`);
    }
    wrap.append(tbl);
  }
  body.append(wrap);
  if (d) hFoot(`문서 차례 ${d.rev} · ${d.extracted ? "문서를 다시 읽어 견줌" : "지금 1단계 결과로 견줌"} · ${d.seconds}s · 스크립트(LLM 호출 없음)`, false);
}
