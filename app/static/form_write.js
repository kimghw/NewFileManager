// 워크플로우 「양식 작성」 의 화면(spec_양식작성 ② §6) — 대시보드의 단계 상태(formWriteLive) · 2열 「자료 가져오기」(fwTakeOpen — 문서 라이브러리 서버의 추출 MD 를 이 문서의 자료로) ·
// 2열 「지침 작성」(fwWriteOpen — 자리마다 작성 지침 + 자료 → 문서 에이전트의 제안: 문서는 제안 카드의 「문서에 반영」 을 눌러야 바뀐다).
// 문서 라이브러리 · 자료 추출은 **따로 선 서버**(doclib/ — 새 탭으로 연다)이고, 여기는 그 서버를 8114 의 끝점(/api/doclib)으로만 읽는다. 두 열은 어느 hwpx 문서에서나 열 수 있다(공통 도구 — 워크플로우에 묶지 않는다).
// 기대는 app.js 의 이름: api · el · $ · state · H_JSON · hBtn · hHelp(panel_help.js) · toast · headsDlg · heads · scrollToBlock · showTab · toolShown / dashboard.js: dashBtn · dashDraw / doc_agent.js: AGENT · agentLoad.
const FW = { key: "", at: 0, lib: null, gw: null, loading: null, err: "", picks: new Set(), mats: null, note: "", onlyGuided: true, poll: 0, seen: "" };
const fwKey = () => `${state.id || ""}`;
document.addEventListener("nfm:work-reset", (e) => { // 작업 내용 초기화(same_file.js workReset) — 같은 문서 id 라 키로는 못 가린다: 그 문서의 기억(작성 지침 모음 · 자료 · 검토 · 실행)을 버린다
  if (!e.detail || e.detail.id !== state.id || FW.key !== fwKey()) return;
  clearTimeout(FW.poll); clearTimeout(FW.rpoll);
  FW.gen = (FW.gen || 0) + 1; FW.loading = null; // 초기화 전에 떠난 읽기는 결과를 버린다(fwRead 의 gen)
  FW.key = ""; FW.at = 0; // 다음 fwRead 가 처음 연 것처럼 다시 읽는다(fgAsked · mats · picks · note 도 비움)
});
const fwRunning = () => !!(FW.gw && FW.gw.run && FW.gw.run.state === "running");
const fwReviewing = () => !!(FW.fr && FW.fr.run && FW.fr.run.state === "running"); // 양식 검토(form_review_api)가 도는 중

async function fwRead(force = false) { // 문서 라이브러리의 목록 + 이 문서의 자리 · 자료 · 실행 — 10초(도는 동안 2초) 안의 것은 다시 읽지 않는다
  if (FW.key !== fwKey()) Object.assign(FW, { key: fwKey(), at: 0, lib: null, gw: null, fg: null, fgAsked: false, fr: null, err: "", picks: new Set(), mats: null, note: "", seen: "" });
  if (!state.id) return FW;
  const age = Date.now() - FW.at;
  if (!force && FW.gw && age < (fwRunning() || fwReviewing() ? 2000 : 10000)) return FW;
  if (FW.loading) return FW.loading;
  const key = FW.key, gen = FW.gen;
  const mine = (FW.loading = (async () => {
    try {
      const [lib, gw, fg, fr] = await Promise.all([api("/api/doclib").catch((e) => ({ alive: false, why: e.message, docs: [], url: "" })), api(`/api/docs/${state.id}/guide-write`),
        api(`/api/docs/${state.id}/form-guides`).catch(() => null), // 저장한 작성 지침(form_guides_api — 「헤딩 · 표 분석 · 작성 지침」 줄)
        api(`/api/docs/${state.id}/form-review`).catch(() => null)]); // 양식 검토 · 정한 것(form_review_api — 「지침 작성」 열 위)
      if (key !== fwKey() || gen !== FW.gen) return FW;
      Object.assign(FW, { lib, gw, fg: fg && fg.saved ? fg : FW.fg && FW.fg.saved ? FW.fg : fg, fr, at: Date.now(), err: "" }); // 저장본은 비지 않는다(keep 이 지우지 않음) — 저장(POST) 전에 떠난 읽기가 뒤늦게 와도 저장본을 빈 것으로 덮지 않는다
      if (FW.mats === null) FW.mats = new Set(gw.materials.map((m) => m.id)); // 처음에는 자료를 모두 고른다
      else for (const id of [...FW.mats]) if (!gw.materials.some((m) => m.id === id)) FW.mats.delete(id);
      const run = gw.run;
      if (run && run.state !== "running" && FW.seen !== run.id && FW.watch === run.id) { // 지켜보던 실행이 끝남 — 에이전트 보기의 대화를 다시 읽어 제안 카드를 보인다
        FW.seen = run.id;
        if (typeof agentLoad === "function") agentLoad();
      }
    } catch (e) { if (key === fwKey() && gen === FW.gen) FW.err = e.message || String(e); }
    if (FW.loading === mine) FW.loading = null;
    return FW;
  })());
  return mine;
}
function fwLibOpen(hash = "") { // 문서 라이브러리(따로 선 서버)를 새 탭으로
  const url = (FW.lib && FW.lib.url) || "";
  if (!url) return toast("문서 라이브러리 서버의 주소를 모릅니다", true);
  window.open(url + (hash ? `/#${hash}` : "/"), "_blank", "noopener");
}
const fwDoneExtracts = () => ((FW.lib && FW.lib.docs) || []).reduce((n, d) => n + d.extracts.length, 0);
const FW_LIB_DOWN = "문서 라이브러리 서버가 꺼져 있습니다 — tools/start_doclib.ps1 로 띄웁니다(자료 추출 · 「자료 가져오기」 를 할 수 없습니다)";

// 「1 준비」 의 「헤딩 · 표 분석 · 작성 지침」 · 「LLM 검증·보완」 줄(2026-11-24 사용자 "여기 문서의 헤딩이랑 테이블 분석하는 단계가 없네 1준비에 있어야지." · "이걸 하면서,,, 테이블이나 본문이 지침을 가지고 와야지").
// 분석 상태는 문서 이름 줄과 같은 값(doc_status.js dsState.main — GET /api/docs/{id}/analysis)을 읽고, 분석이 끝났는데 저장한 작성 지침이 없으면 한 번 모아 저장한다(POST …/form-guides — 스크립트 · 문서 안 바뀜:
// 이관의 「헤딩 · 표 분석」 이 하는 것과 같은 끝점 — app.js taskGuidesLoad). 분석 · LLM 실행은 이름 줄의 것을 그대로 부른다(headsFirst · dsLlmRun — 새 실행 길이 아니다).
function fwAnalysis() { // → {view(없으면 null — 아직 못 읽음), heads, tables, base(둘 다 끝남), busy, bad, hwpx}
  const v = typeof dsState === "object" && dsState.mainId === state.id ? dsState.main : null;
  if (!v) return { view: null };
  const by = Object.fromEntries((v.items || []).map((i) => [i.key, i])), hd = by.heads, tb = by.tables, two = [hd, tb].filter(Boolean);
  return { view: v, heads: hd, tables: tb, hwpx: !!(hd || tb), base: !!(hd && tb && hd.state === "done" && tb.state === "done"),
    busy: v.base === "running" || two.some((i) => i.state === "running" || i.state === "wait"), // 스크립트 분석(헤딩 · 표)이 도는 중 — LLM 검증·보완이 도는 것은 03 줄의 일(02 를 「진행 중」 으로 셈하지 않는다)
    llmBusy: typeof dsBusy === "function" && dsBusy(v), bad: two.some((i) => i.state === "failed") };
}
async function fwGuidesKeep(force = false) { // 지금 문서에서 작성 지침을 모아 저장(스크립트 · 1초 안팎) — 분석이 끝났는데 저장본이 없을 때 한 번 · force = 「다시 모으기」
  if (!state.id) return;
  const key = fwKey();
  FW.fgAsked = true;
  try { const fg = await api(`/api/docs/${state.id}/form-guides`, { method: "POST" }); if (key === fwKey()) FW.fg = fg; if (force) toast("작성 지침을 다시 모아 저장했습니다"); }
  catch (e) { if (force) toast(`작성 지침을 모으지 못했습니다: ${e.message}`, true); else console.warn("작성 지침 저장:", e.message); }
}
function fwHeadsStep(A) { // 「헤딩 · 표 분석 · 작성 지침」 줄의 상태
  const fg = FW.fg && FW.fg.saved, c = (fg && fg.counts) || null;
  const guideBtn = c && typeof formGuidesList === "function" ? [dashBtn("작성 지침", () => formGuidesList({ id: state.id, name: state.name }), { title: "저장한 작성 지침(작성 요령 표 · <참고 N> 자료 · ※ 안내 · 각주 번호의 항목)을 헤딩별 · 표별로 문서 옆 열에 보입니다", focus: "act:heads:guides" })] : [];
  const headsBtn = toolShown("Heads") ? [dashBtn("헤딩 추출 열기", () => showTab("Heads"), { title: "헤딩 그래프 · 표 구조 결과를 봅니다", focus: "act:heads:open" })] : [];
  if (!A.view) return { state: "todo", text: "분석 상태를 읽는 중…" };
  if (!A.hwpx) return { state: "", text: "헤딩 · 표 분석은 hwpx 문서만 됩니다" };
  if (A.busy) return { state: "run", text: "헤딩 · 표 분석 중(스크립트) — 끝나면 작성 지침을 모아 저장합니다", acts: headsBtn };
  if (!A.base) return { state: "now", text: A.bad ? `분석 실패 — ${[A.heads, A.tables].map((i) => i && i.error).filter(Boolean)[0] || "까닭 모름"}` : "분석 결과가 없습니다",
    acts: [dashBtn("분석", () => { Promise.resolve(headsFirst()).finally(() => typeof docStatusPing === "function" && docStatusPing()); toast("헤딩 · 표 분석을 겁니다(스크립트) — 진행은 이 줄과 문서 이름 줄에 보입니다"); }, { primary: true, title: "헤딩 그래프 · 표 구조를 스크립트로 뽑습니다(무료 · 문서는 안 바뀜)", focus: "act:heads" }), ...headsBtn] };
  const tail = c ? `작성 지침 ${c.items + c.marks}건 — 헤딩 ${c.headings}곳 · 표 ${c.tables}곳` : FW.fg && FW.fg.error ? "작성 지침을 읽지 못했습니다" : "작성 지침을 모으는 중…";
  return { state: c ? "done" : "run", text: `헤딩 ✓ · 표 ✓ · ${tail}${c && !(c.items + c.marks) ? "(양식에 적힌 지침이 없습니다 — 「작성 지침 확인 · 적기」 에서 적습니다)" : ""}`,
    acts: [...guideBtn, ...(c ? [dashBtn("다시 모으기", () => fwGuidesKeep(true).then(() => typeof dashDraw === "function" && dashDraw(true)), { title: "지금 문서에서 작성 지침을 다시 모아 저장합니다(스크립트 · 문서는 안 바뀜) — 문서에서 지운 지침은 저장본에 남습니다", focus: "act:heads:keep" })] : []), ...headsBtn] };
}
function fwLlmStep(A) { // 「LLM 검증·보완」 줄(선택)
  if (!A.view || !A.hwpx) return { state: "", text: "" };
  const v = A.view, chain = !!(v.job && v.job.chain && v.job.status === "running"), four = (v.items || []).filter((i) => ["heads", "templates", "formats", "tables"].includes(i.key) && i.llm);
  const doneN = four.filter((i) => i.llm.state === "done").length, bad = four.some((i) => i.llm.state === "failed");
  if (chain) return { state: "run", text: "LLM 검증·보완 중(유료) — 진행은 문서 이름 줄의 진행표에 보입니다",
    acts: typeof dsLlmStop === "function" ? [dashBtn("멈춤", () => dsLlmStop(), { title: "지금 하는 일이 끝나면 멈춥니다", focus: "act:headsLlm:stop" })] : [] };
  const text = !A.base ? "헤딩 · 표 분석이 끝나야 합니다" : !four.length ? "" : doneN === four.length ? "LLM 검증·보완을 거쳤습니다" : bad ? "LLM 판정이 실패한 항목이 있습니다 — 앞 결과는 그대로입니다" : doneN ? `LLM 칸 ${doneN}/${four.length} 끝남` : "LLM 검증·보완 안 함 — 스크립트 결과로도 지침 작성을 할 수 있습니다";
  return { state: doneN === four.length && four.length ? "done" : "", text,
    acts: typeof dsLlmRun === "function" ? [dashBtn("LLM 검증·보완", () => dsLlmRun().then(() => typeof dashDraw === "function" && dashDraw(true)), { disabled: !A.base || A.busy || A.llmBusy, title: "헤딩 · 템플릿 · 표를 LLM 이 검증 · 보완하고 서식 정리 계획을 받습니다(유료 · 몇 분 · 문서는 안 바뀜) — 판정할 때 그 자리의 작성 지침을 함께 읽습니다", focus: "act:headsLlm" })] : [] };
}

async function formWriteLive() { // 대시보드(dashboard.js dashLive)의 「양식 작성」 가지 — 단계마다 지금 상태와 그 일을 하는 곳을 여는 단추
  await fwRead();
  const lib = FW.lib || { alive: false, docs: [] }, gw = FW.gw || { places: [], materials: [], run: null, enabled: false }, run = gw.run;
  const libBtn = (focus) => [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다" : FW_LIB_DOWN, focus })];
  const docs = lib.docs.length, done = fwDoneExtracts(), going = lib.docs.reduce((n, d) => n + (d.running || 0), 0), mats = gw.materials.length, guided = gw.places.filter((p) => p.n).length, heads = gw.places.filter((p) => p.kind === "head").length;
  const items = (run && run.items) || [], got = items.reduce((n, i) => n + (i.proposals || 0), 0), applied = typeof AGENT === "object" && AGENT.turns ? AGENT.turns.reduce((n, t) => n + (t.proposals || []).filter((p) => p.state === "applied").length, 0) : 0;
  const next = !mats ? "take" : "ask";
  let A = fwAnalysis();
  if (!A.view && state.id && typeof dsRefresh === "function") { await dsRefresh(); A = fwAnalysis(); } // 이름 줄의 분석 상태를 아직 못 읽음 — 한 번 읽고 그린다
  if (A.base && FW.fg && !FW.fg.saved && !FW.fgAsked) await fwGuidesKeep(); // 분석이 끝났는데 저장한 작성 지침이 없다 — 한 번 모아 저장(스크립트)
  const S = {
    open: { state: "done", text: "" },
    heads: fwHeadsStep(A),
    headsLlm: fwLlmStep(A),
    keep: { state: docs ? "done" : lib.alive ? "now" : "hold", text: lib.alive ? (docs ? `자료 문서 ${docs}개` : "아직 자료 문서가 없습니다") : FW_LIB_DOWN, acts: libBtn("act:keep") },
    extract: { state: going ? "run" : done ? "done" : docs ? "now" : "todo", text: lib.alive ? [done ? `끝난 추출 ${done}개` : "아직 추출한 것이 없습니다", going ? `추출 중 ${going}개` : ""].filter(Boolean).join(" · ") : "", acts: libBtn("act:extract") },
    take: { state: mats ? "done" : next === "take" ? "now" : "todo", text: mats ? `이 문서의 자료 ${mats}개` : "자료가 없습니다 — 추출한 MD 를 가져오거나 에이전트 보기에서 파일 · 글을 자료로 줍니다",
      acts: [dashBtn("자료 가져오기", () => fwTakeOpen(), { primary: !mats, title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로 가져옵니다(문서 옆 열)", focus: "act:take" })] },
    guides: { state: "", text: gw.hwpx === false ? "hwpx 문서만 됩니다" : `헤딩 ${heads}곳 · 작성 지침이 있는 자리 ${guided}곳`, acts: [dashBtn("지침 작성 열기", () => fwWriteOpen(), { title: "자리마다의 작성 지침을 보고, 채울 자리와 자료를 골라 제안을 받습니다(문서 옆 열)", focus: "act:guides" })] },
    review: fwReviewStep(gw),
    ask: { state: run && run.state === "running" ? "run" : run ? "done" : mats && fwReviewReady() ? "now" : "todo",
      text: run ? (run.state === "running" ? `자리 ${items.filter((i) => i.state !== "queued" && i.state !== "running").length}/${items.length} 받는 중` : `마지막 실행 — 자리 ${items.length}곳 · 제안 ${got}개${items.some((i) => i.state === "failed") ? ` · 실패 ${items.filter((i) => i.state === "failed").length}곳` : ""}`)
        : !gw.enabled ? "LLM 을 쓸 수 없습니다" : !mats ? "자료를 먼저 가져옵니다" : fwReviewWhy(),
      acts: [dashBtn("지침 작성 열기", () => fwWriteOpen(), { primary: !!mats && !run && fwReviewReady(), title: "채울 자리와 자료를 고르고 「제안 받기」 를 누릅니다 — 유료 LLM · 문서는 바뀌지 않습니다", focus: "act:ask" })] },
    check: { state: "", text: "제안마다 저절로 돕니다" },
    apply: { state: applied ? "done" : got ? "now" : "todo", text: applied ? `반영한 제안 ${applied}개` : "제안 카드의 「문서에 반영」 을 누른 제안만 들어갑니다",
      acts: toolShown("Agent") ? [dashBtn("에이전트 보기 열기", () => showTab("Agent"), { primary: !!got && !applied, title: "받은 제안 카드를 보고 「문서에 반영」 을 누릅니다", focus: "act:apply" })] : [] },
  };
  if (FW.err) S.take.text = `읽지 못했습니다 — ${FW.err}`;
  let nowSeen = false; // 「지금」 은 차례상 첫 줄 하나 — 뒤의 줄은 할 수 있어도 「할 수 있음」(단추는 그대로 보인다): 줄마다 따로 셈해 「지금」 이 여럿 서던 것(2026-11-24 사용자 「지금은 긴 몇개냐」)
  for (const s of Object.values(S)) { if (s.state === "now") { if (nowSeen) s.state = "ready"; nowSeen = true; } }
  if (fwRunning() || fwReviewing() || going || A.busy ||(A.view && A.view.job && A.view.job.status === "running")) { clearTimeout(FW.poll); FW.poll = setTimeout(() => { fwRead(true).then(() => { if (typeof dashDraw === "function") dashDraw(); fwRedraw(); }); }, 2500); }
  return { runs: {}, steps: S };
}

// ---- 2열 「자료 가져오기」 -------------------------------------------------------------------------------------------------
const FW_HELP_TAKE = "문서 라이브러리(따로 선 서버)에서 끝난 자료 추출의 MD 를 이 문서의 자료로 가져옵니다. 가져온 자료는 에이전트 보기의 자료와 같은 곳에 놓여 「지침 작성」 과 에이전트 요청이 함께 씁니다.\n"
  + "자료 문서를 올리거나 새로 추출하려면 「문서 라이브러리 열기」 로 그 서버의 화면을 엽니다(새 탭). 문서는 바뀌지 않습니다.";
function fwClearWay() { // 떠 있는 에이전트 창이 문서 옆 열(2열)을 가린다(창의 처음 자리 = 패널 바로 왼쪽) — 이 열을 열 때는 창을 닫는다(대화는 남는다 · 상단 바의 에이전트 아이콘 · 「에이전트 보기 열기」 로 다시 연다)
  if (typeof agentFloating === "function" && agentFloating() && typeof agentFloatClose === "function") agentFloatClose();
}
async function fwTakeOpen() {
  fwClearWay();
  const { tools, body } = headsDlg("fwTake", "자료 가져오기", "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로 · 문서는 안 바뀜");
  tools.append(hBtn("문서 라이브러리 열기", () => fwLibOpen(), { title: "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭" }), hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("자료 가져오기 안내", FW_HELP_TAKE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await fwRead(true);
  fwTakeDraw();
}
function fwTakeDraw() {
  if (heads.dlg !== "fwTake") return;
  const body = $("headsDlgBody"), lib = FW.lib || { alive: false, docs: [] }, docs = lib.docs || [], mats = (FW.gw && FW.gw.materials) || [];
  body.replaceChildren();
  const sr = (s) => el("span", "fw-t-sr", s);
  const matsCard = () => {
    const sec = el("section", "fw-t-mats"), h = el("h3", "fw-t-mats-head");
    h.append(el("span", "fw-t-mats-title", `이 문서의 자료 ${mats.length}개`));
    sec.append(h);
    const ul = el("ul", "fw-t-mat-list");
    const libEids = new Set(docs.flatMap((d) => (d.extracts || []).map((e) => e.id)));
    for (const m of mats) {
      const fromLib = [...libEids].some((eid) => (m.note || "").includes(`(${eid})`));
      const li = el("li", `fw-t-mat${fromLib ? " is-lib" : ""}${m.cut ? " is-cut" : ""}`);
      li.title = m.note || m.head || m.name || "";
      const meta = el("div", "fw-t-mat-meta");
      meta.append(el("strong", "fw-t-mat-name", m.name));
      const info = el("span", "fw-t-mat-info");
      info.append(el("span", "fw-t-mat-chars", `${(m.chars || 0).toLocaleString()}자`));
      if (m.cut) info.append(sr(" · "), el("span", "fw-tag warn", "잘림"));
      meta.append(info);
      li.append(meta);
      ul.append(li);
    }
    sec.append(ul);
    return sec;
  };
  const stateBox = (kind, msg) => {
    const box = el("div", `fw-t-state ${kind}`), ico = el("span", "fw-t-state-ico");
    ico.setAttribute("aria-hidden", "true");
    box.append(ico, el("div", "fw-empty", msg));
    return box;
  };
  if (!lib.alive) {
    body.append(stateBox("is-down", lib.why || FW_LIB_DOWN));
    if (mats.length) body.append(matsCard());
    return;
  }
  if (mats.length) body.append(matsCard());
  const have = (eid) => mats.some((m) => (m.note || "").includes(`(${eid})`));
  const withX = docs.filter((d) => (d.extracts || []).length);
  if (!withX.length) {
    body.append(stateBox(
      docs.length ? "is-noext" : "is-empty",
      docs.length
        ? "끝난 자료 추출이 없습니다 — 문서 라이브러리에서 뽑을 범위를 적고 추출하세요."
        : "문서 라이브러리에 자료 문서가 없습니다 — 「문서 라이브러리 열기」 로 문서를 올리세요.",
    ));
    return;
  }
  for (const d of withX) {
    const gotN = d.extracts.filter((e) => have(e.id)).length, allGot = gotN === d.extracts.length;
    const sec = el("section", `fw-doc${allGot ? " is-all-got" : ""}`), h = el("h3", "fw-t-doc-head");
    const name = el("span", "fw-t-doc-name", d.name);
    name.title = d.name;
    const cnt = el("span", `fw-t-doc-cnt${allGot ? " is-all" : gotN ? " is-part" : ""}`, gotN ? `${gotN}/${d.extracts.length} 가져옴` : `${d.extracts.length}개`);
    h.append(name, cnt);
    sec.append(h);
    for (const e of d.extracts) {
      const got = have(e.id), figs = e.figures || 0, forms = e.formulas || 0;
      const row = el("div", `fw-x${got ? " is-got" : ""}${e.open ? " is-warn" : ""}`);
      const head = el("div", "fw-x-head"), title = el("strong", "fw-t-focus", e.focus || "문서 전체");
      head.append(title);
      const meta = el("div", "fw-x-meta");
      const parts = [];
      if (e.span) parts.push(el("span", "fw-t-stat is-page", `쪽 ${e.span[0]}–${e.span[1]}`));
      parts.push(el("span", "fw-t-stat", `${(e.chars || 0).toLocaleString()}자`));
      parts.push(el("span", `fw-t-stat${figs ? "" : " is-zero"}`, `그림 ${figs}`));
      parts.push(el("span", `fw-t-stat${forms ? "" : " is-zero"}`, `수식 ${forms}`));
      if (e.open) parts.push(el("span", "fw-tag warn", `확인 필요 ${e.open}`));
      meta.append(sr(" "));
      parts.forEach((p, i) => { if (i) meta.append(sr(" · ")); meta.append(p); });
      const acts = el("div", "fw-t-acts");
      const view = hBtn("보기", () => fwLibOpen(`d=${d.id}&x=${e.id}`), { cls: "btn sm fw-t-view", title: "문서 라이브러리에서 이 추출의 MD 와 그림을 봅니다(새 탭)" });
      const take = hBtn(got ? "가져옴" : "가져오기", () => fwTake(e.id), { disabled: got, cls: "btn sm fw-t-take" + (got ? " is-got" : " primary"), title: got ? "이미 이 문서의 자료입니다" : "이 추출의 MD 를 이 문서의 자료로 가져옵니다" });
      acts.append(view, take);
      row.append(head, meta, acts);
      sec.append(row);
    }
    body.append(sec);
  }
}
async function fwTake(eid) {
  try {
    const got = await api(`/api/docs/${state.id}/agent/material/library`, { method: "POST", headers: H_JSON, body: JSON.stringify({ extract: eid }) });
    toast(got.reused ? "이미 있는 자료입니다" : `자료로 가져왔습니다 — ${got.name}`);
    if (FW.mats) FW.mats.add(got.id);
    if (typeof agentLoad === "function" && typeof AGENT === "object" && AGENT.loaded) agentLoad(true);
  } catch (e) { toast(e.message || String(e), true); }
  await fwRead(true);
  fwRedraw();
  if (typeof dashDraw === "function") dashDraw();
}

// ---- 2열 「지침 작성」 ---------------------------------------------------------------------------------------------------
const FW_HELP_WRITE = "문서의 자리(본문 헤딩 · 지침이 붙은 표)마다 작성 지침과 받은 자료를 에이전트에 주고, 그 자리에 넣을 글 · 표 채우기 제안을 받습니다(유료 LLM — 자리마다 호출 1번 이상).\n"
  + "작성 지침 = 양식이 적어 둔 것(작성 요령 · ※ 안내 · 각주 항목)과 사람이 그 헤딩에 적은 것(문서의 「지침」 단추). 아래 「이번 작성의 지침」 은 이번 실행의 모든 자리에 함께 갑니다.\n"
  + "차례 = ① 「양식 검토」 — 양식 전체를 읽고 어떻게 쓸지(요약 · 자리마다 작성 방향)를 검토합니다(자료가 없어도 됩니다) → ② 「작성 계획 세우기」 — 쓸 자료를 고르고 누르면 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획합니다(자료를 고른 채 ① 을 누르면 한 번에) → ③ 확인할 것(범위 · 기준 · 우선순위)에 답합니다(「자료대로」 = 따로 정하지 않음 · 자료에서 찾은 답 후보는 근거와 함께). 「제안 받기」 는 ①②③ 이 끝나야 눌리고, 답과 계획이 자리마다의 요청에 함께 갑니다.\n"
  + "문서는 여기서 바뀌지 않습니다 — 제안은 에이전트 보기의 제안 카드로 나오고 「문서에 반영」 을 누른 것만 들어갑니다. 자료에 없는 내용은 만들지 않으며, 에이전트가 지은 글과 자료에 없는 수가 든 제안은 처음부터 고르지 않은 채로 보입니다.";
async function fwWriteOpen() {
  fwClearWay();
  const { tools, body } = headsDlg("fwWrite", "지침 작성", "자리마다 작성 지침 + 자료 → 제안 · 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  tools.append(hBtn("자료 가져오기", () => fwTakeOpen(), { title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로" }), hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("지침 작성 안내", FW_HELP_WRITE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await fwRead(true);
  fwWriteDraw();
  fwReviewPoll(); // 검토가 도는 중이면 끝날 때까지 따라간다
}
// ---- 양식 검토 — 양식 전체를 읽고 어떻게 쓸지 · 쓰기 전에 사람이 확인할 것을 묻는다(form_review_api — spec_양식작성 ② §5-1) -----------------------
// 2026-11-24 사용자 "양식을 전부 읽고 어떻게 작성해야할지 검토한다, 그리고 사용자가 문서를 제공하면 작성하는데,, 이전에 사용자가 정해줄 내용을 물어 본다". 「제안 받기」 는 검토가 있고 물음에 모두 답해야 돈다(서버도 409).
const FW_SKIP = "자료대로"; // form_review.SKIP — 「따로 정하지 않음 · 자료에 있는 대로」
const fwPlanned = () => !!(FW.fr && FW.fr.review && FW.fr.planned); // 작성 계획 = 자료를 주고 한 검토(자리마다 자료에서 쓸 것 · 자료에 없는 것)
const fwReviewReady = () => fwPlanned() && !(FW.fr.open || []).length;
function fwReviewWhy() {
  const fr = FW.fr;
  if (!fr || !fr.review) return fwReviewing() ? "양식 검토 중 — 끝나면 확인할 것을 묻습니다" : "먼저 「양식 검토」 를 하세요";
  if (!fr.planned) return fwReviewing() ? "작성 계획을 세우는 중 — 끝나면 확인할 것을 묻습니다" : "자료를 고르고 「작성 계획 세우기」 를 하세요";
  return (fr.open || []).length ? `쓰기 전에 확인할 것 ${fr.open.length}개에 답하세요` : "";
}
function fwReviewStep(gw) { // 대시보드 「양식 검토 · 작성 계획」 줄 — 양식 검토 → (자료를 주면) 작성 계획 → 확인할 것에 답
  const fr = FW.fr, rv = fr && fr.review, run = fr && fr.run, open = (fr && fr.open) || [];
  const planned = !!(fr && fr.planned), mats = ((FW.gw && FW.gw.materials) || []).length;
  const btn = [dashBtn(!rv ? "양식 검토" : !planned ? "작성 계획 세우기" : "계획 · 물음 보기", () => fwWriteOpen(), { primary: !rv || (!planned && !!mats) || !!open.length, title: "「지침 작성」 열 위의 「양식 검토 · 작성 계획」 — 양식 전체를 읽어 어떻게 쓸지 검토하고, 자료를 주면 자리마다 무엇을 쓸지 계획을 세우고, 확인할 것을 묻습니다(유료 LLM · 문서는 안 바뀜)", focus: "act:review" })];
  if (gw.hwpx === false) return { state: "", text: "hwpx 문서만 됩니다" };
  if (run && run.state === "running") return { state: "run", text: (run.materials || []).length ? "양식과 자료를 읽고 작성 계획을 세우는 중(1~3분)" : "양식 전체를 읽는 중(1~3분)", acts: btn };
  if (!rv) return { state: "now", text: run && run.state === "failed" ? `검토 실패 — ${run.error || "까닭 모름"}` : "아직 검토하지 않았습니다 — 양식 전체를 읽고 쓸 방향과 확인할 것을 정리합니다", acts: btn };
  const n = rv.questions.length, pl = Object.values(rv.places || {});
  if (!planned) return { state: mats ? "now" : "todo", text: `양식 검토 끝(자리 ${pl.length}곳의 작성 방향) · 작성 계획 전 — ${mats ? "자료를 고르고 「작성 계획 세우기」 를 누릅니다" : "자료를 가져오면 계획을 세웁니다"}`, acts: btn };
  return { state: open.length ? "now" : "done", text: `작성 계획 — 자료에서 쓸 자리 ${pl.filter((x) => x.use).length}곳 · 자료에 없는 것이 있는 자리 ${pl.filter((x) => x.gap).length}곳 · ${open.length ? `확인할 것 ${open.length}개가 남았습니다` : n ? `확인할 것 ${n}개 모두 답함` : "확인할 것이 없습니다"}${fr.stale ? " · 검토 뒤 양식이 바뀌었습니다" : ""}`, acts: btn };
}
async function fwReviewRun() {
  const materials = [...(FW.mats || [])], had = !!(FW.fr && FW.fr.review);
  if (had && !fwPlanned() && !materials.length) return toast("쓸 자료를 고르세요 — 작성 계획은 자료로 세웁니다", true);
  const what = materials.length ? `양식 전체와 고른 자료 ${materials.length}개를 읽고, 자리마다 자료의 무엇을 어떻게 쓸지 작성 계획을 세우고 확인할 것을 묻습니다` : "양식 전체를 읽고 어떻게 쓸지 검토합니다(자료가 없어 작성 계획은 자료를 고른 뒤에 세웁니다)";
  if (!window.confirm(`유료 LLM 한 번(1~3분) — ${what}. 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/form-review`, { method: "POST", headers: H_JSON, body: JSON.stringify({ materials }) });
    FW.fr = { ...(FW.fr || {}), run: got.run };
    toast(materials.length ? "작성 계획을 세웁니다 — 끝나면 확인할 것을 묻습니다" : "양식 검토를 시작했습니다");
  } catch (e) { return toast(e.message || String(e), true); }
  fwRedraw();
  fwReviewPoll();
  if (typeof dashDraw === "function") dashDraw();
}
function fwReviewPoll() {
  clearTimeout(FW.rpoll);
  if (!fwReviewing()) return;
  FW.rpoll = setTimeout(async () => {
    await fwRead(true); fwRedraw(); if (typeof dashDraw === "function") dashDraw(); fwReviewPoll();
    if (!fwReviewing() && FW.fr && FW.fr.run) toast(FW.fr.run.state === "failed" ? `양식 검토 실패 — ${FW.fr.run.error || ""}` : !FW.fr.planned ? "양식 검토가 끝났습니다 — 자료를 고르고 「작성 계획 세우기」 를 누르세요" : (FW.fr.open || []).length ? `작성 계획을 세웠습니다 — 쓰기 전에 확인할 것 ${FW.fr.open.length}개에 답하세요` : "작성 계획을 세웠습니다", FW.fr.run.state === "failed");
  }, 2500);
}
async function fwAnswer(answers) { // [{key?, q?, a}] — 빈 a = 지움
  try { FW.fr = await api(`/api/docs/${state.id}/form-review/answers`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ answers }) }); }
  catch (e) { toast(e.message || String(e), true); }
  fwWriteDraw();
  if (typeof dashDraw === "function") dashDraw();
}
function fwReviewEl() { // 「지침 작성」 열의 「양식 검토 · 작성 계획」 절 — 양식 검토(요약) → 작성 계획(자료를 주면) → 확인할 것(물음마다 답) · 앞서 정한 것
  const fr = FW.fr || {}, rv = fr.review, run = fr.run, dec = fr.decided || [], sec = el("section", "fw-doc fw-review"), h = el("h3", "fw-places-head");
  const going = run && run.state === "running", planned = !!fr.planned;
  const steps = el("span", "fw-steps"); // 어디까지 했나 — 양식 검토 ✓ → 작성 계획 ✓ → 확인할 것 n/m
  const qn = rv ? (rv.questions || []).length : 0, on = (fr.open || []).length;
  steps.append(el("span", `fw-tag${rv ? " user" : ""}`, rv ? "양식 검토 ✓" : "양식 검토"), el("span", `fw-tag${planned ? " user" : ""}`, planned ? "작성 계획 ✓" : "작성 계획"), el("span", `fw-tag${planned && !on ? " user" : planned ? " warn" : ""}`, planned ? (qn ? `확인할 것 ${qn - on}/${qn}` : "확인할 것 없음") : "확인할 것"));
  h.append(el("span", null, "양식 검토 · 작성 계획"), steps, hBtn(going ? ((run.materials || []).length ? "계획 세우는 중…" : "검토 중…") : !rv ? "양식 검토" : !planned ? "작성 계획 세우기" : "다시 검토", () => fwReviewRun(), { cls: `btn sm${rv && planned ? "" : " primary"}`, disabled: going || !fr.enabled,
    title: !fr.enabled ? "LLM 을 쓸 수 없습니다" : "양식 전체(헤딩 · 안내 글 · 표 · 작성 지침)를 읽어 어떻게 쓸지 검토하고, 쓸 자료를 골라 두었으면 자리마다 자료의 무엇을 쓸지 작성 계획을 세우고 확인할 것을 묻습니다 — 유료 LLM 한 번 · 문서는 바뀌지 않습니다. 다시 해도 답한 것은 남습니다" }));
  sec.append(h);
  if (going) sec.append(el("div", "fw-muted fw-pad", (run.materials || []).length ? "양식과 자료를 읽고 작성 계획을 세우는 중입니다(1~3분)." : "양식 전체를 읽는 중입니다(1~3분)."));
  else if (run && run.state === "failed") sec.append(el("div", "fw-muted fw-pad fw-bad", `검토 실패 — ${run.error || "까닭 모름"}${rv ? "(앞 검토는 그대로입니다)" : ""}`));
  if (!rv) {
    if (!going) sec.append(el("div", "fw-muted fw-pad", "아직 검토하지 않았습니다."));
    return sec;
  }
  if (fr.stale) sec.append(el("div", "fw-muted fw-pad fw-bad", "검토 뒤에 양식(자리 · 작성 지침)이 바뀌었습니다 — 바뀐 곳이 많으면 「다시 검토」 합니다(정한 것은 남습니다)."));
  if (!planned && !going) sec.append(el("div", "fw-muted fw-pad fw-bad", "양식만 검토했습니다 — 쓸 자료를 고르고 「작성 계획 세우기」 를 누르세요."));
  if (rv.summary) { const d = el("details", "fw-guides fw-pad"); d.open = !dec.length; d.append(el("summary", null, "검토 요약 — 이 양식을 어떻게 쓰나"), el("div", "fw-guide", rv.summary)); sec.append(d); }
  const qs = rv.questions || [], left = new Set(fr.open || []);
  if (planned) { const pl = Object.values(rv.places || {}); sec.append(el("div", "fw-muted fw-pad fw-plan", `작성 계획 — 자료 ${(rv.materials || []).length}개로 세움 · 자료에서 쓸 자리 ${pl.filter((x) => x.use).length}곳 · 자료에 없는 것이 있는 자리 ${pl.filter((x) => x.gap).length}곳(자리마다의 계획은 아래 자리 줄에)`)); }
  sec.append(el("div", "fw-q-head", qs.length ? `쓰기 전에 확인할 것 — ${qs.length}개 중 ${qs.length - left.size}개 답함` : "쓰기 전에 확인할 것이 없습니다"));
  const names = new Map(((FW.gw && FW.gw.places) || []).map((p) => [p.id, p.text]));
  for (const q of qs) {
    const d = dec.find((x) => x.key === q.key || x.q === q.text), box = el("div", `fw-q${left.has(q.key) ? " is-open" : ""}`), input = el("input", "fw-q-input");
    box.append(el("div", "fw-q-text", q.text));
    if (q.why) box.append(el("div", "fw-muted", q.why));
    if (q.places.length) box.append(el("div", "fw-muted", `닿는 자리: ${q.places.map((i) => names.get(i) || i).slice(0, 4).join(" · ")}${q.places.length > 4 ? ` 외 ${q.places.length - 4}곳` : ""}`));
    const chips = el("div", "fw-q-chips");
    if (q.suggest) { const b = hBtn(`자료에서: ${q.suggest}`, () => fwAnswer([{ key: q.key, a: q.suggest }]), { cls: "btn sm fw-q-sug", title: q.source ? `근거: ${q.source}` : "자료에서 찾은 답 후보" }); chips.append(b); }
    for (const c of q.choices) chips.append(hBtn(c, () => fwAnswer([{ key: q.key, a: c }]), { cls: `btn sm${d && d.a === c ? " is-on" : ""}` }));
    chips.append(hBtn(FW_SKIP, () => fwAnswer([{ key: q.key, a: FW_SKIP }]), { cls: `btn sm${d && d.a === FW_SKIP ? " is-on" : ""}`, title: "따로 정하지 않습니다 — 에이전트가 자료에 있는 대로 씁니다" }));
    box.append(chips);
    input.type = "text"; input.maxLength = 500; input.value = d ? d.a : ""; input.placeholder = "답을 적고 Enter(또는 위에서 고름)";
    input.setAttribute("aria-label", q.text);
    const save = () => { const a = input.value.trim(); if (a !== (d ? d.a : "")) fwAnswer([{ key: q.key, a }]); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } });
    input.addEventListener("change", save);
    box.append(input);
    sec.append(box);
  }
  const free = dec.filter((x) => !qs.some((q) => q.key === x.key || q.text === x.q));
  if (free.length) {
    const d = el("details", "fw-guides fw-pad"); d.append(el("summary", null, `앞서 정한 것 ${free.length}개 — 모든 자리의 요청에 함께 갑니다`));
    for (const x of free) { const li = el("div", "fw-guide"); li.append(el("span", null, `${x.q} → ${x.a}`), hBtn("지우기", () => fwAnswer([{ q: x.q, a: "" }]), { cls: "btn sm" })); d.append(li); }
    sec.append(d);
  }
  return sec;
}
function fwRedraw() { fwTakeDraw(); fwWriteDraw(); }
function fwShown() { const ps = (FW.gw && FW.gw.places) || []; return FW.onlyGuided ? ps.filter((p) => p.n || FW.picks.has(p.id)) : ps; }
function fwWriteDraw() {
  if (heads.dlg !== "fwWrite") return;
  const body = $("headsDlgBody"), foot = $("headsDlgFoot"), gw = FW.gw;
  const keep = body.scrollTop, noteEl = body.querySelector(".fw-note");
  if (noteEl && document.activeElement === noteEl) return void fwFootDraw(foot); // 지침을 적는 동안에는 목록을 다시 그리지 않는다(쓰던 글 · 커서)
  if (document.activeElement && document.activeElement.classList.contains("fw-q-input") && body.contains(document.activeElement)) return void fwFootDraw(foot); // 물음의 답을 적는 동안에도
  body.replaceChildren();
  if (!gw) return void body.append(el("div", "fw-empty", FW.err || "읽는 중…"));
  if (gw.hwpx === false) return void body.append(el("div", "fw-empty", "지침 작성은 hwpx 문서만 됩니다."));
  // 자료
  const matSec = el("section", "fw-doc"), matBox = el("div", "fw-mats");
  matSec.append(el("h3", null, "쓸 자료"));
  if (!gw.materials.length) matBox.append(el("span", "fw-muted", "자료가 없습니다 — 「자료 가져오기」 로 추출한 MD 를 가져오거나 에이전트 보기에서 파일 · 글을 자료로 주세요."));
  for (const m of gw.materials) {
    const lab = el("label", "fw-mat"), cb = el("input");
    cb.type = "checkbox"; cb.checked = FW.mats.has(m.id);
    cb.addEventListener("change", () => { if (cb.checked) FW.mats.add(m.id); else FW.mats.delete(m.id); fwFootDraw(foot); });
    lab.append(cb, el("span", null, m.name), el("span", "fw-muted", `${(m.chars || 0).toLocaleString()}자`));
    lab.title = m.note || m.head || "";
    matBox.append(lab);
  }
  matSec.append(matBox);
  // 이번 작성의 지침
  const noteSec = el("section", "fw-doc"), note = el("textarea", "fw-note");
  note.rows = 3; note.maxLength = (gw.limits && gw.limits.note) || 1000; note.value = FW.note;
  note.placeholder = "이번 작성의 지침(선택) — 예: 한국선급이 맡은 내용만, 개조식으로 3~5줄, 2차년도 실적 위주로";
  note.addEventListener("input", () => { FW.note = note.value; });
  noteSec.append(el("h3", null, "이번 작성의 지침"), note);
  // 자리
  const plSec = el("section", "fw-doc"), head = el("h3", "fw-places-head"), only = el("label", "fw-mat"), onlyCb = el("input"), shown = fwShown();
  onlyCb.type = "checkbox"; onlyCb.checked = FW.onlyGuided;
  onlyCb.addEventListener("change", () => { FW.onlyGuided = onlyCb.checked; fwWriteDraw(); });
  only.append(onlyCb, el("span", null, "작성 지침이 있는 자리만"));
  const all = hBtn("모두 고르기", () => { for (const p of fwShown()) FW.picks.add(p.id); fwWriteDraw(); }, { title: "보이는 자리를 모두 고릅니다" }), none = hBtn("모두 해제", () => { FW.picks.clear(); fwWriteDraw(); });
  head.append(el("span", null, `채울 자리 — ${shown.length}곳`), only, all, none);
  plSec.append(head);
  if (!shown.length) plSec.append(el("div", "fw-empty", gw.places.length ? "작성 지침이 붙은 자리가 없습니다 — 「작성 지침이 있는 자리만」 을 끄면 모든 헤딩이 보입니다. 헤딩에 지침을 적으려면 문서에서 그 헤딩의 「지침」 단추를 씁니다." : "본문 헤딩이 없습니다 — 헤딩 추출(기본 분석)이 끝났는지 확인하세요."));
  const ran = new Map(((gw.run && gw.run.items) || []).map((i) => [i.id, i]));
  for (const p of shown) plSec.append(fwPlaceEl(p, ran.get(p.id), foot));
  body.append(matSec, fwReviewEl(), noteSec, plSec);
  body.scrollTop = keep;
  fwFootDraw(foot);
}
const FW_ITEM = { queued: ["기다림", ""], running: ["받는 중", "run"], done: ["제안", "ok"], none: ["자료에 없음", ""], failed: ["실패", "fail"], skipped: ["안 함", ""] };
function fwPlaceEl(p, item, foot) {
  const row = el("div", `fw-place${p.kind === "table" ? " is-table" : ""}`), cb = el("input"), main = el("div", "fw-place-main"), name = el("button", "fw-place-name", p.text || (p.kind === "table" ? "표" : "(빈 헤딩)")), tags = el("span", "fw-tags");
  cb.type = "checkbox"; cb.checked = FW.picks.has(p.id); cb.setAttribute("aria-label", `${p.text} 고르기`);
  cb.addEventListener("change", () => { if (cb.checked) FW.picks.add(p.id); else FW.picks.delete(p.id); fwFootDraw(foot); });
  name.type = "button"; name.title = "문서의 그 자리로";
  name.addEventListener("click", () => scrollToBlock(p.id));
  row.style.setProperty("--fw-depth", String(Math.max(0, Math.min(5, (p.depth || 1) - 1))));
  if (p.kind === "table") tags.append(el("span", "fw-tag", "표"));
  if (p.n) tags.append(el("span", "fw-tag guide", `지침 ${p.n}`));
  if (p.user) tags.append(el("span", "fw-tag user", "사람 지침"));
  if (p.filled) tags.append(el("span", "fw-tag", "글 있음"));
  if (item) { const [word, cls] = FW_ITEM[item.state] || [item.state, ""]; const t = el("span", `fw-tag ${cls}`, item.state === "done" ? `제안 ${item.proposals}` : word); t.title = item.error || item.reply || ""; tags.append(t); }
  main.append(name, tags);
  const how = FW.fr && FW.fr.review && (FW.fr.review.places || {})[p.id];
  if (how && how.how) { const h = el("div", "fw-how", `작성 방향: ${how.how}`); if (how.needs) h.title = `필요한 정보: ${how.needs}`; main.append(h); }
  if (how && how.use) main.append(el("div", "fw-how fw-use", `자료에서 쓸 것: ${how.use}`)); // 작성 계획(자료를 주고 한 검토)
  if (how && how.gap) main.append(el("div", "fw-how fw-gap", `자료에 없는 것: ${how.gap}`));
  if (p.guides.length) {
    const det = el("details", "fw-guides"), sum = el("summary", null, "작성 지침 보기");
    det.append(sum);
    for (const g of p.guides) { const li = el("div", "fw-guide"); li.append(el("span", `fw-tag ${g.src === "user" ? "user" : "guide"}`, g.src === "user" ? "사람" : g.kind || "양식"), el("span", null, g.text)); det.append(li); }
    main.append(det);
  }
  row.append(cb, main);
  return row;
}
function fwFootDraw(foot) {
  if (!foot || heads.dlg !== "fwWrite") return;
  const gw = FW.gw || {}, run = gw.run, n = FW.picks.size, mats = FW.mats ? FW.mats.size : 0, most = (gw.limits && gw.limits.places) || 40;
  foot.replaceChildren();
  if (run && run.state === "running") {
    const done = run.items.filter((i) => i.state !== "queued" && i.state !== "running").length;
    foot.append(el("span", "fw-muted", `제안 받는 중 — 자리 ${done}/${run.items.length}`), hBtn("멈춤", async () => { try { await api(`/api/docs/${state.id}/guide-write/stop`, { method: "POST" }); toast("남은 자리는 돌리지 않습니다"); } catch (e) { toast(e.message, true); } }, { title: "도는 자리는 끝까지 받고, 남은 자리는 돌리지 않습니다" }));
    return;
  }
  const why = !gw.enabled ? "LLM 을 쓸 수 없습니다" : !mats ? "쓸 자료를 고르세요" : fwReviewWhy() || (!n ? "채울 자리를 고르세요" : n > most ? `한 번에 ${most}곳까지입니다` : "");
  if (run) {
    const got = run.items.reduce((s, i) => s + (i.proposals || 0), 0), failed = run.items.filter((i) => i.state === "failed").length, none = run.items.filter((i) => i.state === "none").length;
    foot.append(el("span", "fw-muted", `마지막 실행 — 제안 ${got}개${none ? ` · 자료에 없음 ${none}곳` : ""}${failed ? ` · 실패 ${failed}곳` : ""}`));
    if (got && toolShown("Agent")) foot.append(hBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "받은 제안 카드를 보고 「문서에 반영」 을 누릅니다" }));
  }
  foot.append(el("span", "fw-grow"), hBtn(`제안 받기${n ? ` (${n}곳)` : ""}`, () => fwRun(), { cls: "btn sm primary", disabled: !!why, title: why || `고른 자리 ${n}곳의 제안을 받습니다 — 유료 LLM(자리마다 호출 1번 이상) · 문서는 바뀌지 않습니다` }));
}
async function fwRun() {
  const places = [...FW.picks], materials = [...(FW.mats || [])];
  if (!window.confirm(`유료 LLM 으로 자리 ${places.length}곳의 제안을 받습니다(자리마다 호출 1번 이상 · 수십 초씩). 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/guide-write/run`, { method: "POST", headers: H_JSON, body: JSON.stringify({ places, materials, note: FW.note }) });
    FW.watch = got.run.id;
    if (FW.gw) FW.gw.run = got.run;
    toast(`지침 작성을 시작했습니다 — 자리 ${got.run.items.length}곳`);
  } catch (e) { return toast(e.message || String(e), true); }
  fwRedraw();
  fwPoll();
  if (typeof dashDraw === "function") dashDraw();
}
function fwPoll() { // 도는 동안 2초마다 — 끝나면 에이전트 보기의 대화를 다시 읽는다(fwRead)
  clearTimeout(FW.poll);
  if (!fwRunning()) return;
  FW.poll = setTimeout(async () => { await fwRead(true); fwRedraw(); if (typeof dashDraw === "function") dashDraw(); fwPoll(); if (!fwRunning()) toast("지침 작성이 끝났습니다 — 에이전트 보기의 제안 카드를 확인하세요"); }, 2000);
}
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { guideWrite: "지침 작성" }); // 작업 기록의 표시 이름(app.js LOG_KIND — doc_agent.js 가 에이전트 기록의 이름을 더하는 것과 같은 방식)
