// 워크플로우 「양식 작성」 의 화면(spec_양식작성 ② §6) — 대시보드의 단계 상태(formWriteLive) · 2열 「자료 가져오기」(fwTakeOpen — 문서 라이브러리 서버의 추출 MD 를 이 문서의 자료로) ·
// 2열 「지침 작성」(fwWriteOpen — 자리마다 작성 지침 + 자료 → 문서 에이전트의 초안(제안 카드): 문서는 제안 카드의 「문서에 반영」 을 눌러야 바뀐다).
// 2026-11-24 더함(사용자 「작성은 어디서 하는거야?」 · 「제안받는것도 뭔지 모르겠는데」 · 「여기서 작성 테마/키워드를 추출해줘」 — spec_양식작성 ② §5-2 · §5-3 · astra 협의): 화면 말 「초안」(단추 「작성 초안 받기」) ·
// 대시보드의 줄 둘(review 「양식 검토 · 찾을 테마」 — 자료 준비 앞 · plan 「작성 계획 · 확인할 것」) · 절 「자료에서 찾을 테마 · 키워드」(fwTopicsEl — 고른 것을 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사) ·
// 상자 자리의 「쓸 자리 고르기」(fwChunksEl — 같은 이름의 자리는 하나만: 실행 요청의 chunks).
// 문서 라이브러리 · 자료 추출은 **따로 선 서버**(doclib/ — 새 탭으로 연다)이고, 여기는 그 서버를 8114 의 끝점(/api/doclib)으로만 읽는다. 두 열은 어느 hwpx 문서에서나 열 수 있다(공통 도구 — 워크플로우에 묶지 않는다).
// 기대는 app.js 의 이름: api · el · $ · state · H_JSON · hBtn · hHelp(panel_help.js) · toast · headsDlg · heads · scrollToBlock · showTab · toolShown / dashboard.js: dashBtn · dashDraw / doc_agent.js: AGENT · agentLoad.
const FW = { key: "", at: 0, lib: null, gw: null, loading: null, err: "", picks: new Set(), mats: null, note: "", onlyGuided: null, poll: 0, seen: "", // onlyGuided null = 아직 안 정함(fwRead 가 자리 수로 처음 값을 정한다)
  chunks: {}, chunkOpen: new Set(), lead: "", topicOn: new Set() }; // chunks = {상자 id: Set(고른 쓸 자리의 key)} · chunkOpen = 사람이 펴 둔 상자 · lead = 범위 앞에 붙일 말 · topicOn = 복사하려고 고른 테마의 key
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
  if (FW.key !== fwKey()) Object.assign(FW, { key: fwKey(), at: 0, lib: null, gw: null, fg: null, fgAsked: false, fr: null, err: "", picks: new Set(), mats: null, note: "", seen: "", onlyGuided: null, chunks: {}, chunkOpen: new Set(), lead: "", topicOn: new Set() });
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
      // 「작성 지침이 있는 자리만」 의 처음 값 — 자리가 한 번에 돌릴 수 있는 수를 넘는 긴 양식에서만 켠다. 짧은 양식에서 켜 두면 지침이 붙은 한두 곳만 보여 나머지 헤딩을 못 고른다
      // (2026-11-24 사용자의 양식: 자리 6곳 가운데 표 하나만 보였다 — spec_양식작성 ② §6)
      if (FW.onlyGuided === null) FW.onlyGuided = (gw.places || []).length > ((gw.limits && gw.limits.places) || 40) && gw.places.some((p) => p.n);
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
  const text = !A.base ? "헤딩 · 표 분석이 끝나야 합니다" : !four.length ? "" : doneN === four.length ? "LLM 검증·보완을 거쳤습니다" : bad ? "LLM 판정이 실패한 항목이 있습니다 — 앞 결과는 그대로입니다" : doneN ? `LLM 칸 ${doneN}/${four.length} 끝남` : "LLM 검증·보완 안 함 — 스크립트 결과로도 초안 작성을 할 수 있습니다";
  return { state: doneN === four.length && four.length ? "done" : "", text,
    acts: typeof dsLlmRun === "function" ? [dashBtn("LLM 검증·보완", () => dsLlmRun().then(() => typeof dashDraw === "function" && dashDraw(true)), { disabled: !A.base || A.busy || A.llmBusy, title: "헤딩 · 템플릿 · 표를 LLM 이 검증 · 보완하고 서식 정리 계획을 받습니다(유료 · 몇 분 · 문서는 안 바뀜) — 판정할 때 그 자리의 작성 지침을 함께 읽습니다", focus: "act:headsLlm" })] : [] };
}

// 초안이 0개인 까닭을 가른다(서버가 자리마다 준 why — guide_write_api._one): 에이전트가 행동 없이 답함(자료에 해당 내용 없음) ↔ 검사에서 버림 ↔ 쓸 자리를 안 고른 상자 ↔ 이미 채운 줄.
const FW_WHY = { noaction: "자료에 해당 내용 없음", dropped: "검사에서 제외", noslot: "쓸 자리를 고르지 않음", filled: "이미 채운 줄", boxed: "쓸 자리는 아래 상자에" };
function fwRunWhy(run) { // 「자료에 해당 내용 없음 1곳 · 검사에서 제외 1곳 · 실패 1곳」 | ""
  const items = (run && run.items) || [], out = [];
  for (const [k, word] of Object.entries(FW_WHY)) { const n = items.filter((i) => i.state === "none" && (i.why || "noaction") === k).length; if (n) out.push(`${word} ${n}곳`); }
  const failed = items.filter((i) => i.state === "failed").length;
  if (failed) out.push(`실패 ${failed}곳`);
  return out.join(" · ");
}
function fwAppliedN(run) { // 반영한 초안 수 — **이번 실행의 턴**만 센다(문서의 모든 에이전트 턴이 아니다: 전에 에이전트 보기에서 따로 반영한 카드가 「반영함」 으로 세어지지 않게 — astra 2차 G13).
  if (typeof AGENT !== "object" || !AGENT.turns) return 0; // 실행 기록이 없으면(서버를 다시 켠 뒤 — 실행 상태는 메모리뿐) 지침 작성이 낸 턴(요청 글이 「[지침 작성]」 으로 시작)으로 센다
  const ids = new Set(((run && run.items) || []).map((i) => i.turn).filter(Boolean));
  const mine = AGENT.turns.filter((t) => (run ? ids.has(t.id) : String(t.text || "").startsWith("[지침 작성]")));
  return mine.reduce((n, t) => n + (t.proposals || []).filter((p) => p.state === "applied").length, 0);
}

async function formWriteLive() { // 대시보드(dashboard.js dashLive)의 「양식 작성」 가지 — 단계마다 지금 상태와 그 일을 하는 곳을 여는 단추
  await fwRead();
  const lib = FW.lib || { alive: false, docs: [] }, gw = FW.gw || { places: [], materials: [], run: null, enabled: false }, run = gw.run;
  const libBtn = (focus) => [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다" : FW_LIB_DOWN, focus })];
  const docs = lib.docs.length, done = fwDoneExtracts(), going = lib.docs.reduce((n, d) => n + (d.running || 0), 0), mats = gw.materials.length, guided = gw.places.filter((p) => p.n).length, heads = gw.places.filter((p) => p.kind === "head").length;
  const items = (run && run.items) || [], got = items.reduce((n, i) => n + (i.proposals || 0), 0), applied = fwAppliedN(run);
  const rv = FW.fr && FW.fr.review, topics = rv && rv.topics;
  const next = !mats ? "take" : "ask";
  let A = fwAnalysis();
  if (!A.view && state.id && typeof dsRefresh === "function") { await dsRefresh(); A = fwAnalysis(); } // 이름 줄의 분석 상태를 아직 못 읽음 — 한 번 읽고 그린다
  if (A.base && FW.fg && !FW.fg.saved && !FW.fgAsked) await fwGuidesKeep(); // 분석이 끝났는데 저장한 작성 지침이 없다 — 한 번 모아 저장(스크립트)
  const S = {
    open: { state: "done", text: "" },
    heads: fwHeadsStep(A),
    headsLlm: fwLlmStep(A),
    // 줄의 차례 = 등록부의 차례(「지금」 은 차례상 첫 줄 하나): 준비(… · 작성 지침 확인 · 양식 검토 · 찾을 테마) → 자료 준비 → 작성(작성 계획 · 확인할 것 → 양식 초안 작성 → 검사 → 반영)
    guides: { state: "", text: gw.hwpx === false ? "hwpx 문서만 됩니다" : `헤딩 ${heads}곳 · 작성 지침이 있는 자리 ${guided}곳`,
      acts: [dashBtn("지침 작성 열기", () => fwWriteOpen(), { title: "자리마다의 작성 지침을 보고, 채울 자리와 자료를 골라 초안을 받습니다(문서 옆 열)", focus: "act:guides" }),
        ...(topics && topics.length ? [dashBtn("테마 · 키워드 보기", () => fwWriteOpen("topics"), { title: "양식 검토가 뽑은 「자료에서 찾을 테마 · 키워드」 — 골라서 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사합니다", focus: "act:guides:topics" })] : [])] },
    review: fwReviewStep(gw),
    keep: { state: docs ? "done" : lib.alive ? "now" : "hold", text: lib.alive ? (docs ? `자료 문서 ${docs}개` : "아직 자료 문서가 없습니다") : FW_LIB_DOWN, acts: libBtn("act:keep") },
    extract: { state: going ? "run" : done ? "done" : docs ? "now" : "todo", text: lib.alive ? [done ? `끝난 추출 ${done}개` : "아직 추출한 것이 없습니다", going ? `추출 중 ${going}개` : ""].filter(Boolean).join(" · ") : "", acts: libBtn("act:extract") },
    take: { state: mats ? "done" : next === "take" ? "now" : "todo", text: mats ? `이 문서의 자료 ${mats}개` : "자료가 없습니다 — 추출한 MD 를 가져오거나 에이전트 보기에서 파일 · 글을 자료로 줍니다",
      acts: [dashBtn("자료 가져오기", () => fwTakeOpen(), { primary: !mats, title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로 가져옵니다(문서 옆 열)", focus: "act:take" })] },
    plan: fwPlanStep(gw),
    // 끝남 = 초안을 하나라도 받았을 때(등록부의 「끝난 것으로 보는 때」) — 돌렸지만 초안이 0개면 끝난 것이 아니다(2026-11-24: 0개인데 「끝남」 으로 보여 사용자가 「작성은 어디서 하는거야?」)
    ask: { state: run && run.state === "running" ? "run" : got ? "done" : mats && fwReviewReady() ? "now" : "todo",
      text: run ? (run.state === "running" ? `자리 ${items.filter((i) => i.state !== "queued" && i.state !== "running").length}/${items.length} 받는 중` : `마지막 실행 — 자리 ${items.length}곳 · 초안 ${got}개${fwRunWhy(run) ? ` · ${fwRunWhy(run)}` : ""}${got ? "" : " — 문서에 넣을 것이 없습니다. 자리를 다시 골라 받습니다"}`)
        : !gw.enabled ? "LLM 을 쓸 수 없습니다" : !mats ? "자료를 먼저 가져옵니다" : fwReviewWhy(),
      acts: [dashBtn("지침 작성 열기", () => fwWriteOpen(), { primary: !!mats && !got && !fwRunning() && fwReviewReady(), title: "채울 자리와 자료를 고르고 「작성 초안 받기」 를 누릅니다 — LLM 이 자리마다 초안을 써서 제안 카드로 보입니다(유료 LLM · 문서는 아직 바뀌지 않습니다)", focus: "act:ask" })] },
    check: { state: "", text: "초안마다 저절로 돕니다" },
    apply: { state: applied ? "done" : got ? "now" : "todo", text: applied ? `반영한 초안 ${applied}개` : "제안 카드의 「문서에 반영」 을 누른 초안만 들어갑니다 — 양식에 글이 써지는 곳입니다",
      acts: toolShown("Agent") ? [dashBtn("에이전트 보기 열기", () => showTab("Agent"), { primary: !!got && !applied, title: "받은 초안(제안 카드)을 보고 「문서에 반영」 을 누릅니다", focus: "act:apply" })] : [] },
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
const FW_HELP_WRITE = "문서의 자리(본문 헤딩 · 쓸 자리가 있는 상자 · 지침이 붙은 표)마다 작성 지침과 받은 자료를 에이전트에 주고, 그 자리에 넣을 초안(글 쓰기 · 상자 안 자리 채우기 · 표 채우기)을 받습니다(유료 LLM — 자리마다 호출 1번 이상).\n"
  + "초안 = LLM 이 쓴 글입니다. 에이전트 보기의 제안 카드로 나오고, 카드에서 「문서에 반영」 을 누른 것만 문서에 들어갑니다 — 여기서는 문서가 바뀌지 않습니다.\n"
  + "작성 지침 = 양식이 적어 둔 것(작성 요령 · ※ 안내 · 각주 항목)과 사람이 그 헤딩에 적은 것(문서의 「지침」 단추). 아래 「이번 작성의 지침」 은 이번 실행의 모든 자리에 함께 갑니다.\n"
  + "차례 = ① 「양식 검토」 — 양식 전체를 읽고 어떻게 쓸지(요약 · 자리마다 작성 방향)를 검토하고 자료에서 찾을 테마 · 키워드를 뽑습니다(자료가 없어도 됩니다) → ② 「작성 계획 세우기」 — 쓸 자료를 고르고 누르면 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획합니다(자료를 고른 채 ① 을 누르면 한 번에) → ③ 확인할 것(범위 · 기준 · 우선순위)에 답합니다(「자료대로」 = 따로 정하지 않음 · 자료에서 찾은 답 후보는 근거와 함께). 「작성 초안 받기」 는 ①②③ 이 끝나야 눌리고, 답과 계획이 자리마다의 요청에 함께 갑니다. 계획을 세운 자료와 다른 자료를 고르거나 검토 뒤에 고른 자리가 바뀌었으면 계획을 다시 세웁니다.\n"
  + "상자(1칸 표) 자리는 그 안의 쓸 자리(빈 줄 · 글머리 줄 · 같은 줄 뒤)를 골라 씁니다 — 같은 이름의 자리가 여럿이면 하나를 골라야 하고, 양식에 있던 글을 바꾸는 줄과 상자 안의 표 · 그림 자리는 쓰지 않습니다.\n"
  + "자료에 없는 내용은 만들지 않으며, 에이전트가 지은 글과 자료에 없는 수가 든 초안은 처음부터 고르지 않은 채로 보입니다.";
const FW_HELP_TOPICS = "양식 검토가 양식 전체를 읽고 뽑은 것입니다 — 이 양식을 쓰려면 자료 문서에서 무엇을 찾아야 하는지.\n"
  + "테마 = 찾을 내용의 이름 · 키워드 = 자료에서 그 내용을 부르는 표현(같은 뜻의 다른 말을 찾는 단서) · 맥락 = 어느 자리에 무엇이 어떤 꼴로 필요한가.\n"
  + "쓰는 법 = 「범위 앞에 붙일 말」 에 누구의 것인지(기관 · 연구 · 기간)를 적고, 찾을 테마를 골라 「고른 것 복사」 → 문서 라이브러리의 「뽑을 범위」 에 붙여 넣습니다(줄마다 범위 하나 = MD 하나 · 한 번에 8개까지 · 줄마다 600자까지).\n"
  + "테마마다 기간이 다르면(당해연도 ↔ 다음 연도) 한꺼번에 복사하지 말고 앞에 붙일 말을 바꿔 나눠 복사하거나, 붙여 넣은 뒤 그 줄을 고칩니다. 아래 미리보기가 복사될 글 그대로입니다. 문서 라이브러리의 추출은 그 화면에서 시작합니다(여기서는 복사까지).";
async function fwWriteOpen(at = "") { // at = "topics" → 「자료에서 찾을 테마 · 키워드」 절로 굴린다(대시보드의 「테마 · 키워드 보기」)
  fwClearWay();
  const { tools, body } = headsDlg("fwWrite", "지침 작성", "자리마다 작성 지침 + 자료 → 초안 · 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  tools.append(hBtn("자료 가져오기", () => fwTakeOpen(), { title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로" }), hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("지침 작성 안내", FW_HELP_WRITE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await fwRead(true);
  fwWriteDraw();
  if (at === "topics") { const sec = body.querySelector(".fw-topics"); if (sec) body.scrollTop = Math.max(0, sec.offsetTop - body.offsetTop - 6); }
  fwReviewPoll(); // 검토가 도는 중이면 끝날 때까지 따라간다
}
// ---- 양식 검토 — 양식 전체를 읽고 어떻게 쓸지 · 쓰기 전에 사람이 확인할 것을 묻는다(form_review_api — spec_양식작성 ② §5-1) -----------------------
// 2026-11-24 사용자 "양식을 전부 읽고 어떻게 작성해야할지 검토한다, 그리고 사용자가 문서를 제공하면 작성하는데,, 이전에 사용자가 정해줄 내용을 물어 본다". 「작성 초안 받기」 는 검토가 있고 물음에 모두 답해야 돈다(서버도 409).
const FW_SKIP = "자료대로"; // form_review.SKIP — 「따로 정하지 않음 · 자료에 있는 대로」
const fwPlanned = () => !!(FW.fr && FW.fr.review && FW.fr.planned); // 작성 계획 = 자료를 주고 한 검토(자리마다 자료에서 쓸 것 · 자료에 없는 것)
const fwReviewReady = () => fwPlanned() && !(FW.fr.open || []).length;
function fwReviewWhy() {
  const fr = FW.fr;
  if (!fr || !fr.review) return fwReviewing() ? "양식 검토 중 — 끝나면 확인할 것을 묻습니다" : "먼저 「양식 검토」 를 하세요";
  if (!fr.planned) return fwReviewing() ? "작성 계획을 세우는 중 — 끝나면 확인할 것을 묻습니다" : "자료를 고르고 「작성 계획 세우기」 를 하세요";
  return (fr.open || []).length ? `쓰기 전에 확인할 것 ${fr.open.length}개에 답하세요` : "";
}
function fwReviewStep(gw) { // 대시보드 「양식 검토 · 찾을 테마」 줄(준비 묶음의 끝 — 자료 준비 앞: 자료 없이 된다) — 양식 검토가 있으면 끝남
  const fr = FW.fr, rv = fr && fr.review, run = fr && fr.run;
  const going = !!(run && run.state === "running"), topics = rv && rv.topics;
  if (gw.hwpx === false) return { state: "", text: "hwpx 문서만 됩니다" };
  if (!rv) {
    const btn = [dashBtn("양식 검토", () => fwWriteOpen(), { primary: !going, title: "「지침 작성」 열 위의 「양식 검토」 — 양식 전체를 읽어 어떻게 쓸지 검토하고 자료에서 찾을 테마 · 키워드를 뽑습니다(유료 LLM 한 번 · 자료 없이 됩니다 · 문서는 안 바뀜)", focus: "act:review" })];
    if (going) return { state: "run", text: "양식 전체를 읽는 중(1~3분)", acts: btn };
    return { state: "now", text: run && run.state === "failed" ? `검토 실패 — ${run.error || "까닭 모름"}` : "아직 검토하지 않았습니다 — 양식 전체를 읽고 쓸 방향 · 자료에서 찾을 테마 · 확인할 것을 정리합니다(자료 없이 됩니다)", acts: btn };
  }
  const n = Object.keys(rv.places || {}).length;
  return { state: "done", text: `양식 검토 끝 — 자리 ${n}곳의 작성 방향 · ${topics ? `찾을 테마 ${topics.length}개` : "찾을 테마는 아직 뽑지 않았습니다(「다시 검토」 로 뽑습니다)"}${fr.stale ? " · 검토 뒤 양식이 바뀌었습니다" : ""}`,
    acts: [dashBtn("테마 · 키워드 보기", () => fwWriteOpen("topics"), { title: "「지침 작성」 열의 「자료에서 찾을 테마 · 키워드」 — 골라서 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사합니다", focus: "act:review" })] };
}
function fwPlanStep(gw) { // 대시보드 「작성 계획 · 확인할 것」 줄(작성 묶음의 처음) — 자료로 세운 작성 계획 → 확인할 것에 답
  const fr = FW.fr, rv = fr && fr.review, run = fr && fr.run, open = (fr && fr.open) || [];
  const planned = !!(fr && fr.planned), mats = ((FW.gw && FW.gw.materials) || []).length;
  if (gw.hwpx === false) return { state: "", text: "" };
  const btn = [dashBtn(!planned ? "작성 계획 세우기" : "계획 · 물음 보기", () => fwWriteOpen(), { primary: !!rv && ((!planned && !!mats) || !!open.length), title: "「지침 작성」 열 위의 「양식 검토 · 작성 계획」 — 쓸 자료를 고르고 자리마다 자료의 무엇을 쓸지 계획을 세우고, 확인할 것에 답합니다(유료 LLM · 문서는 안 바뀜)", focus: "act:plan" })];
  if (run && run.state === "running" && (rv || (run.materials || []).length)) return { state: "run", text: "양식과 자료를 읽고 작성 계획을 세우는 중(1~3분)", acts: btn };
  if (!rv) return { state: "todo", text: "양식 검토 뒤에 세웁니다", acts: btn };
  const n = rv.questions.length, pl = Object.values(rv.places || {});
  if (!planned) return { state: mats ? "now" : "todo", text: mats ? "작성 계획 전 — 쓸 자료를 고르고 「작성 계획 세우기」 를 누릅니다" : "자료를 가져오면 계획을 세웁니다", acts: btn };
  return { state: open.length ? "now" : "done", text: `작성 계획 — 자료에서 쓸 자리 ${pl.filter((x) => x.use).length}곳 · 자료에 없는 것이 있는 자리 ${pl.filter((x) => x.gap).length}곳 · ${open.length ? `확인할 것 ${open.length}개가 남았습니다` : n ? `확인할 것 ${n}개 모두 답함` : "확인할 것이 없습니다"}`, acts: btn };
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
  const qs = (FW.fr && FW.fr.review && FW.fr.review.questions) || []; // 물음 번호(key)와 함께 그 물음의 글도 보낸다 — 다시 검토해 같은 번호가 다른 물음이 됐으면 서버가 409(옛 화면의 답이 다른 물음에 저장되지 않게: astra 3차)
  answers = answers.map((x) => { const q = x.key && qs.find((y) => y.key === x.key); return q && x.q === undefined ? { ...x, q: q.text } : x; });
  try { FW.fr = await api(`/api/docs/${state.id}/form-review/answers`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ answers }) }); }
  catch (e) { toast(e.message || String(e), true); if (/검토가 바뀌었습니다/.test(e.message || "")) await fwRead(true); }
  fwWriteDraw();
  if (typeof dashDraw === "function") dashDraw();
}
function fwReviewEl() { // 「지침 작성」 열의 「양식 검토 · 작성 계획」 절 — 양식 검토(요약) → 작성 계획(자료를 주면) → 확인할 것(물음마다 답) · 앞서 정한 것
  const fr = FW.fr || {}, rv = fr.review, run = fr.run, dec = fr.decided || [], sec = el("section", "fw-doc fw-review"), h = el("h3", "fw-places-head");
  const going = run && run.state === "running", planned = !!fr.planned;
  const sr = (s) => el("span", "fw-sr", s);
  const steps = el("span", "fw-steps"); // 어디까지 했나 — 양식 검토 ✓ → 작성 계획 ✓ → 확인할 것 n/m
  const qn = rv ? (rv.questions || []).length : 0, on = (fr.open || []).length;
  const s1 = el("span", `fw-tag${rv ? " user" : ""}`, rv ? "양식 검토 ✓" : "양식 검토");
  const s2 = el("span", `fw-tag${planned ? " user" : ""}`, planned ? "작성 계획 ✓" : "작성 계획");
  const s3 = el("span", `fw-tag${planned && !on ? " user" : planned ? " warn" : ""}`, planned ? (qn ? `확인할 것 ${qn - on}/${qn}` : "확인할 것 없음") : "확인할 것");
  s1.dataset.step = "1"; s2.dataset.step = "2"; s3.dataset.step = "3";
  if (!rv) s1.dataset.now = "1";
  else if (!planned) s2.dataset.now = "1";
  steps.append(s1, s2, s3);
  const actBtn = hBtn(going ? ((run.materials || []).length ? "계획 세우는 중…" : "검토 중…") : !rv ? "양식 검토" : !planned ? "작성 계획 세우기" : "다시 검토", () => fwReviewRun(), {
    cls: `btn sm fw-rev-act${rv && planned ? "" : " primary"}${going ? " is-going" : ""}`,
    disabled: going || !fr.enabled,
    title: !fr.enabled ? "LLM 을 쓸 수 없습니다" : "양식 전체(헤딩 · 안내 글 · 표 · 작성 지침)를 읽어 어떻게 쓸지 검토하고, 쓸 자료를 골라 두었으면 자리마다 자료의 무엇을 쓸지 작성 계획을 세우고 확인할 것을 묻습니다 — 유료 LLM 한 번 · 문서는 바뀌지 않습니다. 다시 해도 답한 것은 남습니다",
  });
  h.append(el("span", "fw-rev-title", "양식 검토 · 작성 계획"), actBtn, steps);
  sec.append(h);
  if (going) sec.append(el("div", "fw-muted fw-pad fw-rev-msg is-going", (run.materials || []).length ? "양식과 자료를 읽고 작성 계획을 세우는 중입니다(1~3분)." : "양식 전체를 읽는 중입니다(1~3분)."));
  else if (run && run.state === "failed") sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-fail", `검토 실패 — ${run.error || "까닭 모름"}${rv ? "(앞 검토는 그대로입니다)" : ""}`));
  if (!rv) {
    if (!going) sec.append(el("div", "fw-muted fw-pad fw-rev-msg is-idle", "아직 검토하지 않았습니다."));
    return sec;
  }
  if (fr.stale) sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-warn", "검토 뒤에 양식(자리 · 작성 지침)이 바뀌었습니다 — 바뀐 곳이 많으면 「다시 검토」 합니다(정한 것은 남습니다)."));
  if (!planned && !going) sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-warn", "양식만 검토했습니다 — 쓸 자료를 고르고 「작성 계획 세우기」 를 누르세요."));
  if (rv.summary) { const d = el("details", "fw-guides fw-pad fw-rev-sum"); d.open = !dec.length; d.append(el("summary", null, "검토 요약 — 이 양식을 어떻게 쓰나"), el("div", "fw-guide", rv.summary)); sec.append(d); }
  const qs = rv.questions || [], left = new Set(fr.open || []);
  if (planned) {
    const pl = Object.values(rv.places || {}), matN = (rv.materials || []).length, useN = pl.filter((x) => x.use).length, gapN = pl.filter((x) => x.gap).length;
    const plan = el("div", "fw-muted fw-pad fw-plan");
    const stat = (pre, n, post, cls = "") => { const sp = el("span", `fw-plan-stat${cls ? " " + cls : ""}`); sp.append(pre, el("strong", null, String(n)), post); return sp; };
    plan.append(
      el("span", "fw-plan-label", "작성 계획"), sr(" — "),
      stat("자료 ", matN, "개로 세움"), sr(" · "),
      stat("자료에서 쓸 자리 ", useN, "곳", useN ? "is-use" : ""), sr(" · "),
      stat("자료에 없는 것이 있는 자리 ", gapN, "곳", gapN ? "is-gap" : ""),
      el("span", "fw-plan-note", "(자리마다의 계획은 아래 자리 줄에)"),
    );
    sec.append(plan);
  }
  const doneN = qs.length - left.size;
  const qHead = el("div", `fw-q-head${!qs.length ? " is-empty" : !left.size ? " is-done" : ""}`);
  if (qs.length) {
    const row = el("div", "fw-q-head-row"), cnt = el("span", "fw-q-head-count");
    cnt.append(`${qs.length}개 중 `, el("strong", null, String(doneN)), "개 답함");
    row.append(el("span", "fw-q-head-title", "쓰기 전에 확인할 것"), sr(" — "), cnt);
    const bar = el("div", "fw-q-bar"), fill = el("div", "fw-q-bar-fill");
    bar.setAttribute("aria-hidden", "true");
    fill.style.width = `${Math.round((doneN / qs.length) * 100)}%`;
    bar.append(fill);
    qHead.append(row, bar);
  } else {
    qHead.textContent = "쓰기 전에 확인할 것이 없습니다";
  }
  sec.append(qHead);
  const names = new Map(((FW.gw && FW.gw.places) || []).map((p) => [p.id, p.text]));
  let qi = 0;
  for (const q of qs) {
    qi += 1;
    const d = dec.find((x) => x.key === q.key || x.q === q.text), isOpen = left.has(q.key);
    const choices = q.choices || [], places = q.places || [];
    const sugOnlyOn = !!(q.suggest && d && d.a === q.suggest && !choices.includes(q.suggest));
    const chipHit = !!(d && d.a && (choices.includes(d.a) || d.a === FW_SKIP || sugOnlyOn));
    const box = el("div", `fw-q${isOpen ? " is-open" : " is-done"}${!isOpen && d && d.a ? (chipHit ? " is-chip" : " is-custom") : ""}`), input = el("input", "fw-q-input");
    const qText = el("div", "fw-q-text", q.text);
    qText.dataset.num = String(qi);
    box.append(qText);
    if (q.why) box.append(el("div", "fw-muted fw-q-why", q.why));
    if (places.length) {
      const plRow = el("div", "fw-muted fw-q-places"), shown = places.map((i) => names.get(i) || i).slice(0, 4);
      plRow.append(el("span", "fw-q-places-lbl", "닿는 자리"), sr(": "));
      shown.forEach((nm, idx) => {
        if (idx) plRow.append(sr(" · "));
        const pill = el("span", "fw-q-place", nm);
        pill.title = nm;
        plRow.append(pill);
      });
      if (places.length > 4) plRow.append(el("span", "fw-q-place is-more", ` 외 ${places.length - 4}곳`));
      box.append(plRow);
    }
    const ans = el("div", "fw-q-ans");
    if (q.suggest) {
      const sugRow = el("div", "fw-q-sug-row");
      const b = hBtn(`자료에서: ${q.suggest}`, () => fwAnswer([{ key: q.key, a: q.suggest }]), { cls: `btn sm fw-q-sug${sugOnlyOn ? " is-on" : ""}`, title: q.source ? `근거: ${q.source}` : "자료에서 찾은 답 후보" });
      sugRow.append(b);
      ans.append(sugRow);
    }
    const chips = el("div", "fw-q-chips");
    for (const c of choices) chips.append(hBtn(c, () => fwAnswer([{ key: q.key, a: c }]), { cls: `btn sm${d && d.a === c ? " is-on" : ""}` }));
    chips.append(hBtn(FW_SKIP, () => fwAnswer([{ key: q.key, a: FW_SKIP }]), { cls: `btn sm fw-q-skip${d && d.a === FW_SKIP ? " is-on" : ""}`, title: "따로 정하지 않습니다 — 에이전트가 자료에 있는 대로 씁니다" }));
    ans.append(chips);
    input.type = "text"; input.maxLength = 500; input.value = d ? d.a : ""; input.placeholder = "답을 적고 Enter(또는 위에서 고름)";
    input.setAttribute("aria-label", q.text);
    const save = () => { const a = input.value.trim(); if (a !== (d ? d.a : "")) fwAnswer([{ key: q.key, a }]); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } });
    input.addEventListener("change", save);
    ans.append(input);
    box.append(ans);
    sec.append(box);
  }
  const lostQ = new Set(fr.lost || []), old = dec.filter((x) => !qs.some((q) => q.key === x.key || q.text === x.q)); // lost = 자리를 잃은 답(서버 form_review.lost — 어느 자리의 것인지 몰라 어느 자리에도 싣지 않는다)
  for (const [list, title, cls] of [[old.filter((x) => !lostQ.has(x.q)), (n) => `앞서 정한 것 ${n}개 — 모든 자리의 요청에 함께 갑니다`, ""], [old.filter((x) => lostQ.has(x.q)), (n) => `자리를 못 찾은 답 ${n}개 — 어느 자리에도 쓰지 않습니다`, " fw-rev-lost"]]) {
    if (!list.length) continue;
    const d = el("details", `fw-guides fw-pad fw-rev-free${cls}`); d.append(el("summary", null, title(list.length)));
    for (const x of list) { const li = el("div", "fw-guide"); li.append(el("span", null, `${x.q} → ${x.a}`), hBtn("지우기", () => fwAnswer([{ q: x.q, a: "" }]), { cls: "btn sm fw-rev-del" })); d.append(li); }
    sec.append(d);
  }
  return sec;
}
// ---- 자료에서 찾을 테마 · 키워드(spec_양식작성 ② §5-2) — 양식 검토가 뽑은 것을 골라, 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사한다 ------------------------------
// 2026-11-24 사용자 "여기서 작성 테마/키워드를 추출해줘 … 그럼 내가 라이브러리에서 이 테마나 키워드로 추출하게.. 테마/키워드 그리고 맥락을 함께 추출하도록 해줘". 8114 는 문서 라이브러리를 읽기만 한다 — 복사까지만.
const FW_SCOPES = 8, FW_SCOPE_MAX = 600; // 문서 라이브러리가 한 번에 받는 범위 수 · 범위 한 줄의 길이(doclib/extract.py)
const fwLead = () => String(FW.lead || "").replace(/\s+/g, " ").trim();
function fwTopicLine(i) { // 복사될 한 줄 — 「<앞말>, <서버가 지은 범위 글>」(앞말이 비면 쉼표 없이 · 줄 나눔 없음)
  const t = ((FW.fr && FW.fr.review && FW.fr.review.topics) || [])[i] || {};
  const base = String(((FW.fr && FW.fr.topicLines) || [])[i] || t.scope || t.name || "").replace(/\s+/g, " ").trim(), lead = fwLead();
  return lead && base ? `${lead}, ${base}` : base;
}
async function fwCopy(text, done) {
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch { // 클립보드 권한이 없을 때 — 가려 둔 글 칸으로
    const ta = el("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
    document.body.append(ta); ta.select();
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
  }
  toast(ok ? done : "복사하지 못했습니다 — 미리보기의 글을 골라 직접 복사하세요", !ok);
}
function fwTopicsEl() { // 「양식 검토 · 작성 계획」 절 바로 아래 — 양식 검토가 없으면 그리지 않는다
  const fr = FW.fr || {}, rv = fr.review;
  if (!rv) return null;
  const topics = rv.topics, lib = FW.lib || { alive: false }, sec = el("section", "fw-doc fw-topics"), h = el("h3", "fw-places-head");
  h.append(el("span", "fw-top-title", "자료에서 찾을 테마 · 키워드"), hHelp("자료에서 찾을 테마 · 키워드 안내", FW_HELP_TOPICS, { note: true }));
  if (topics && topics.length) h.append(el("span", "fw-tag", `${topics.length}개`));
  sec.append(h);
  if (!topics) { sec.append(el("div", "fw-muted fw-pad fw-top-msg", "아직 뽑지 않았습니다 — 「다시 검토」 로 뽑습니다")); return sec; } // 오늘 전에 저장한 검토(topics 없음) — 「0개」 가 아니다
  if (!topics.length) { sec.append(el("div", "fw-muted fw-pad fw-top-msg", "찾을 테마가 없습니다")); return sec; }
  for (const k of [...FW.topicOn]) if (!topics.some((t) => t.key === k)) FW.topicOn.delete(k);
  const lead = el("input", "fw-top-lead"), prev = el("div", "fw-top-prev"), names = new Map(((FW.gw && FW.gw.places) || []).map((p) => [p.id, p.text]));
  lead.type = "text"; lead.maxLength = 200; lead.value = FW.lead || ""; lead.placeholder = "범위 앞에 붙일 말(기관 · 연구 · 기간) — 예: 한국선급, 2차년도";
  lead.setAttribute("aria-label", "범위 앞에 붙일 말(기관 · 연구 · 기간)");
  const copyAll = hBtn("고른 것 복사", () => { const ls = chosen(); if (ls.length) fwCopy(ls.join("\n"), `범위 ${ls.length}줄을 복사했습니다 — 문서 라이브러리의 「뽑을 범위」 에 붙여 넣으세요`); }, { cls: "btn sm primary fw-top-copy" });
  const rows = [];
  const chosen = () => topics.map((t, i) => [t, fwTopicLine(i)]).filter(([t, line]) => FW.topicOn.has(t.key) && line && line.length <= FW_SCOPE_MAX).map(([, line]) => line);
  const sync = () => { // 고른 것 · 앞말이 바뀔 때 — 미리보기 · 단추 · 줄마다의 넘침 표시만 고친다(목록을 다시 그리지 않는다: 쓰던 글 · 굴린 자리)
    const ls = chosen(), on = topics.filter((t) => FW.topicOn.has(t.key)).length;
    prev.replaceChildren(...(ls.length ? ls.map((l) => el("div", "fw-top-line", l)) : [el("div", "fw-top-line is-none", on ? "복사할 수 있는 줄이 없습니다" : "테마를 고르면 복사될 줄이 여기 보입니다")]));
    copyAll.textContent = `고른 것 복사${ls.length ? ` (${ls.length})` : ""}`;
    copyAll.disabled = !ls.length;
    copyAll.title = ls.length ? `미리보기의 ${ls.length}줄을 복사합니다 — 문서 라이브러리의 「뽑을 범위」 에 붙여 넣으면 줄마다 범위 하나(= MD 하나)가 됩니다` : "테마를 고르세요";
    rows.forEach(([row, i]) => row.classList.toggle("is-long", fwTopicLine(i).length > FW_SCOPE_MAX));
  };
  lead.addEventListener("input", () => { FW.lead = lead.value; sync(); });
  const leadRow = el("div", "fw-pad fw-top-leadrow"); leadRow.append(lead);
  sec.append(leadRow);
  topics.forEach((t, i) => {
    const row = el("div", "fw-top"), cb = el("input"), main = el("div", "fw-top-main"), head = el("div", "fw-top-head"), kws = el("div", "fw-top-kws");
    cb.type = "checkbox"; cb.checked = FW.topicOn.has(t.key); cb.setAttribute("aria-label", `${t.name} 고르기`);
    cb.addEventListener("change", () => {
      if (cb.checked && FW.topicOn.size >= FW_SCOPES) { cb.checked = false; return toast(`한 번에 ${FW_SCOPES}개까지 고릅니다 — 문서 라이브러리가 범위를 ${FW_SCOPES}개까지 받습니다`, true); }
      if (cb.checked) FW.topicOn.add(t.key); else FW.topicOn.delete(t.key);
      sync();
    });
    head.append(el("strong", "fw-top-name", t.name), el("span", "fw-tag warn fw-top-long", `${FW_SCOPE_MAX}자 넘음 — 복사하지 않습니다`),
      hBtn("복사", () => { const line = fwTopicLine(i); if (line.length > FW_SCOPE_MAX) return toast(`범위 한 줄은 ${FW_SCOPE_MAX}자까지입니다 — 앞에 붙일 말을 줄이세요`, true); fwCopy(line, `「${t.name}」 의 범위 한 줄을 복사했습니다`); }, { cls: "btn sm fw-top-one", title: "이 테마의 범위 한 줄만 복사합니다" }));
    for (const k of t.keywords || []) kws.append(el("span", "fw-top-kw", k));
    main.append(head);
    if ((t.keywords || []).length) main.append(kws);
    if (t.context) main.append(el("div", "fw-top-ctx", t.context));
    if ((t.places || []).length) {
      const pl = el("div", "fw-muted fw-q-places fw-top-places"), shown = t.places.slice(0, 4);
      pl.append(el("span", "fw-q-places-lbl", "닿는 자리"));
      for (const id of shown) { const pill = el("span", "fw-q-place", names.get(id) || id); pill.title = names.get(id) || id; pl.append(pill); }
      if (t.places.length > 4) pl.append(el("span", "fw-q-place is-more", ` 외 ${t.places.length - 4}곳`));
      main.append(pl);
    }
    row.append(cb, main);
    rows.push([row, i]);
    sec.append(row);
  });
  const act = el("div", "fw-pad fw-top-acts");
  act.append(copyAll, hBtn("문서 라이브러리 열기", () => fwLibOpen(), { cls: "btn sm", disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다(복사한 줄을 「뽑을 범위」 에 붙여 넣습니다)" : FW_LIB_DOWN }));
  const prevBox = el("div", "fw-pad"); prevBox.append(prev);
  sec.append(prevBox, act);
  sync();
  return sec;
}
function fwRedraw() { fwTakeDraw(); fwWriteDraw(); }
function fwShown() { const ps = (FW.gw && FW.gw.places) || []; return FW.onlyGuided ? ps.filter((p) => p.n || FW.picks.has(p.id)) : ps; }
function fwWriteDraw() {
  if (heads.dlg !== "fwWrite") return;
  const body = $("headsDlgBody"), foot = $("headsDlgFoot"), gw = FW.gw;
  const keep = body.scrollTop, noteEl = body.querySelector(".fw-note");
  if (noteEl && document.activeElement === noteEl) return void fwFootDraw(foot); // 지침을 적는 동안에는 목록을 다시 그리지 않는다(쓰던 글 · 커서)
  if (document.activeElement && (document.activeElement.classList.contains("fw-q-input") || document.activeElement.classList.contains("fw-top-lead")) && body.contains(document.activeElement)) return void fwFootDraw(foot); // 물음의 답 · 범위 앞에 붙일 말을 적는 동안에도
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
  const all = hBtn("모두 고르기", () => { for (const p of fwShown()) if (p.slot !== "filled" && !(p.kind === "head" && p.boxed && !p.slot)) FW.picks.add(p.id); fwWriteDraw(); }, { title: "보이는 자리를 모두 고릅니다(이미 채운 줄 · 쓸 자리가 아래 상자에 있는 헤딩은 빼고)" }), none = hBtn("모두 해제", () => { FW.picks.clear(); fwWriteDraw(); });
  head.append(el("span", null, `채울 자리 — ${shown.length}곳`), only, all, none);
  plSec.append(head);
  if (!shown.length) plSec.append(el("div", "fw-empty", gw.places.length ? "작성 지침이 붙은 자리가 없습니다 — 「작성 지침이 있는 자리만」 을 끄면 모든 헤딩이 보입니다. 헤딩에 지침을 적으려면 문서에서 그 헤딩의 「지침」 단추를 씁니다." : "본문 헤딩이 없습니다 — 헤딩 추출(기본 분석)이 끝났는지 확인하세요."));
  const ran = new Map(((gw.run && gw.run.items) || []).map((i) => [i.id, i]));
  for (const p of shown) plSec.append(fwPlaceEl(p, ran.get(p.id), foot));
  body.append(...[matSec, fwReviewEl(), fwTopicsEl(), noteSec, plSec].filter(Boolean));
  body.scrollTop = keep;
  fwFootDraw(foot);
}
const FW_ITEM = { queued: ["기다림", ""], running: ["받는 중", "run"], done: ["초안", "ok"], none: ["자료에 없음", ""], failed: ["실패", "fail"], skipped: ["안 함", ""] };
const FW_NONE = { dropped: "검사에서 제외", noslot: "쓸 자리 안 고름", filled: "채운 줄" }; // 초안이 0개인 자리의 꼬리표(까닭 — 그 밖 = 「자료에 없음」)
// 상자 자리의 쓸 자리 — 처음에는 같은 이름이 하나뿐인 자리를 모두 고르고, 같은 이름이 여럿인 자리(「공동(기업명 작성) :」 두 곳)는 사람이 하나를 고른다(서버도 둘을 보내면 둘 다 뺀다 — guide_write.chunk_paras)
function fwChunkSet(p) {
  const keys = new Set((p.chunks || []).map((c) => c.key));
  if (!FW.chunks[p.id]) FW.chunks[p.id] = new Set((p.chunks || []).filter((c) => (c.dup || [1, 1])[1] === 1).map((c) => c.key));
  for (const k of [...FW.chunks[p.id]]) if (!keys.has(k)) FW.chunks[p.id].delete(k);
  return FW.chunks[p.id];
}
function fwChunksEl(p, foot) { // 「쓸 자리 고르기」 — 상자를 골랐거나 사람이 펴 두었으면 펴진다
  const set = fwChunkSet(p), det = el("details", "fw-guides fw-chunks"), sum = el("summary", null, `쓸 자리 고르기 — ${p.chunks.length}곳 가운데 ${set.size}곳`);
  det.open = FW.picks.has(p.id) || FW.chunkOpen.has(p.id);
  det.addEventListener("toggle", () => { if (det.open) FW.chunkOpen.add(p.id); else FW.chunkOpen.delete(p.id); });
  det.append(sum);
  for (const c of p.chunks) {
    const lab = el("label", "fw-chunk"), cb = el("input"), dup = c.dup || [1, 1];
    cb.type = "checkbox"; cb.checked = set.has(c.key); cb.dataset.chunk = c.key;
    cb.addEventListener("change", () => {
      if (cb.checked) { // 같은 이름의 자리는 하나만 — 켜면 같은 이름의 다른 자리를 끈다
        if (dup[1] > 1) for (const o of p.chunks) if (o !== c && o.head === c.head && o.under === c.under) set.delete(o.key);
        set.add(c.key);
      } else set.delete(c.key);
      FW.chunkOpen.add(p.id);
      fwWriteDraw();
    });
    lab.append(cb, el("span", "fw-chunk-name", `${c.under ? `${c.under} › ` : ""}${c.head}`), el("span", "fw-muted", `줄 ${c.slots}`));
    if (dup[1] > 1) lab.append(el("span", "fw-tag warn", `같은 이름 ${dup[1]}곳 — 하나를 고릅니다(위에서 ${dup[0]}번째)`));
    det.append(lab);
  }
  return det;
}
function fwPlaceEl(p, item, foot) {
  const row = el("div", `fw-place${p.kind === "table" ? " is-table" : p.kind === "box" ? " is-box" : ""}`), cb = el("input"), main = el("div", "fw-place-main"), name = el("button", "fw-place-name", p.text || (p.kind === "table" ? "표" : p.kind === "box" ? "상자" : "(빈 헤딩)")), tags = el("span", "fw-tags");
  cb.type = "checkbox"; cb.checked = FW.picks.has(p.id); cb.setAttribute("aria-label", `${p.text} 고르기`);
  cb.addEventListener("change", () => { if (cb.checked) FW.picks.add(p.id); else FW.picks.delete(p.id); if (p.kind === "box") fwWriteDraw(); else fwFootDraw(foot); });
  name.type = "button"; name.title = "문서의 그 자리로";
  name.addEventListener("click", () => scrollToBlock(p.id));
  row.style.setProperty("--fw-depth", String(Math.max(0, Math.min(5, (p.depth || 1) - 1))));
  if (p.kind === "table") tags.append(el("span", "fw-tag", "표"));
  if (p.kind === "box") tags.append(el("span", "fw-tag", "상자"), el("span", "fw-tag guide", `쓸 자리 ${(p.chunks || []).length}`));
  if (p.slot === "label") tags.append(el("span", "fw-tag guide", "같은 줄 뒤에 씀"));
  if (p.slot === "check") tags.append(el("span", "fw-tag guide", "표시 줄"));
  if (p.slot === "filled") tags.append(el("span", "fw-tag user", "채움"));
  if (p.boxed) tags.append(el("span", "fw-tag", "아래 상자는 따로"));
  if (p.n) tags.append(el("span", "fw-tag guide", `지침 ${p.n}`));
  if (p.user) tags.append(el("span", "fw-tag user", "사람 지침"));
  if (p.filled) tags.append(el("span", "fw-tag", "글 있음"));
  if (item) { const [word, cls] = FW_ITEM[item.state] || [item.state, ""]; const t = el("span", `fw-tag ${cls}`, item.state === "done" ? `초안 ${item.proposals}` : item.state === "none" ? FW_NONE[item.why] || word : word); t.title = item.error || item.note || item.reply || ""; tags.append(t); }
  main.append(name, tags);
  if (p.kind === "box" && (p.chunks || []).length) main.append(fwChunksEl(p, foot));
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
    foot.append(el("span", "fw-muted", `초안 받는 중 — 자리 ${done}/${run.items.length}`), hBtn("멈춤", async () => { try { await api(`/api/docs/${state.id}/guide-write/stop`, { method: "POST" }); toast("남은 자리는 돌리지 않습니다"); } catch (e) { toast(e.message, true); } }, { title: "도는 자리는 끝까지 받고, 남은 자리는 돌리지 않습니다" }));
    return;
  }
  const why = !gw.enabled ? "LLM 을 쓸 수 없습니다" : !mats ? "쓸 자료를 고르세요" : fwReviewWhy() || (!n ? "채울 자리를 고르세요" : n > most ? `한 번에 ${most}곳까지입니다` : "");
  if (run) {
    const got = run.items.reduce((s, i) => s + (i.proposals || 0), 0), why0 = fwRunWhy(run); // 초안 = LLM 이 쓴 글(제안 카드) — 문서에 넣는 것은 에이전트 보기의 카드에서
    foot.append(el("span", "fw-muted", `마지막 실행 — 초안 ${got}개${got ? " · 제안 카드에서 보기" : ""}${why0 ? ` · ${why0}` : ""}`));
    if (got && toolShown("Agent")) foot.append(hBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "받은 초안(제안 카드)을 보고 「문서에 반영」 을 누릅니다 — 양식에 글이 써지는 곳입니다" }));
  }
  foot.append(el("span", "fw-grow"), hBtn(`작성 초안 받기${n ? ` (${n}곳)` : ""}`, () => fwRun(), { cls: "btn sm primary", disabled: !!why, title: why || `고른 자리 ${n}곳의 초안을 받습니다 — LLM 이 쓴 글이 제안 카드로 나옵니다(유료 LLM · 자리마다 호출 1번 이상 · 문서는 아직 바뀌지 않습니다)` }));
}
async function fwRun() {
  const places = [...FW.picks], materials = [...(FW.mats || [])], chunks = {};
  for (const p of (FW.gw && FW.gw.places) || []) if (p.kind === "box" && FW.picks.has(p.id)) chunks[p.id] = [...fwChunkSet(p)]; // 상자마다 사람이 고른 쓸 자리(서버는 이 안의 문단에만 쓰게 한다)
  if (!window.confirm(`유료 LLM 으로 자리 ${places.length}곳의 초안을 받습니다(자리마다 호출 1번 이상 · 수십 초씩). 초안은 제안 카드로 나오고 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/guide-write/run`, { method: "POST", headers: H_JSON, body: JSON.stringify({ places, materials, note: FW.note, chunks }) });
    FW.watch = got.run.id;
    if (FW.gw) FW.gw.run = got.run;
    toast(`초안 작성을 시작했습니다 — 자리 ${got.run.items.length}곳`);
  } catch (e) { return toast(e.message || String(e), true); }
  fwRedraw();
  fwPoll();
  if (typeof dashDraw === "function") dashDraw();
}
function fwPoll() { // 도는 동안 2초마다 — 끝나면 에이전트 보기의 대화를 다시 읽는다(fwRead)
  clearTimeout(FW.poll);
  if (!fwRunning()) return;
  FW.poll = setTimeout(async () => { await fwRead(true); fwRedraw(); if (typeof dashDraw === "function") dashDraw(); fwPoll(); if (!fwRunning()) { const g = ((FW.gw && FW.gw.run && FW.gw.run.items) || []).reduce((s, i) => s + (i.proposals || 0), 0); toast(g ? `초안 ${g}개를 받았습니다 — 에이전트 보기의 제안 카드에서 「문서에 반영」 을 누르면 문서에 들어갑니다` : "초안 0개 — 받은 것이 없습니다(자리 줄의 꼬리표에 까닭이 있습니다)", !g); } }, 2000);
}
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { guideWrite: "지침 작성" }); // 작업 기록의 표시 이름(app.js LOG_KIND — doc_agent.js 가 에이전트 기록의 이름을 더하는 것과 같은 방식)
