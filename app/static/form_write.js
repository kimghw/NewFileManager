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
const fwExtractingGuides = () => FW.guidance?.run?.state === "running";

async function fwRead(force = false) { // 문서 라이브러리의 목록 + 이 문서의 자리 · 자료 · 실행 — 10초(도는 동안 2초) 안의 것은 다시 읽지 않는다
  if (FW.key !== fwKey()) Object.assign(FW, { key: fwKey(), at: 0, lib: null, gw: null, fg: null, fgAsked: false, fr: null, guidance: null, examples: [], changingExamples: false, err: "", picks: new Set(), mats: null, note: "", noteSeeded: false, seen: "", onlyGuided: null, chunks: {}, chunkOpen: new Set(), lead: "", topicOn: new Set(), rs: "" });
  if (!state.id) return FW;
  const age = Date.now() - FW.at;
  if (!force && FW.gw && age < (fwRunning() || fwReviewing() || fwExtractingGuides() ? 2000 : 10000)) return FW;
  if (FW.loading) return FW.loading;
  const key = FW.key, gen = FW.gen;
  const mine = (FW.loading = (async () => {
    try {
      const [lib, gw, fg, fr, guidance, examples] = await Promise.all([api("/api/doclib").catch((e) => ({ alive: false, why: e.message, docs: [], url: "" })), api(`/api/docs/${state.id}/guide-write`),
        api(`/api/docs/${state.id}/form-guides`).catch(() => null), // 저장한 작성 지침(form_guides_api — 「헤딩 · 표 분석 · 작성 지침」 줄)
        api(`/api/docs/${state.id}/form-review`).catch(() => null),
        api(`/api/docs/${key}/writing-guidance`).catch((e) => ({ error: e.message })),
        api(`/api/docs/${key}/form-examples`).catch((e) => ({ error: e.message }))]);
      if (key !== fwKey() || gen !== FW.gen) return FW;
      FW.guidance = guidance; FW.examples = examples.files || []; FW.examplesError = examples.error || "";
      Object.assign(FW, { lib, gw, fg: fg && fg.saved ? fg : FW.fg && FW.fg.saved ? FW.fg : fg, fr, at: Date.now(), err: "" }); // 저장본은 비지 않는다(keep 이 지우지 않음) — 저장(POST) 전에 떠난 읽기가 뒤늦게 와도 저장본을 빈 것으로 덮지 않는다
      if (!FW.noteSeeded) { FW.noteSeeded = true; if (!FW.note && fr && fr.review && fr.review.request) FW.note = fr.review.request; } // 「이번 작성의 지침」 은 화면 메모리뿐 — 다시 열면 양식 검토가 본 요청으로 처음 값을 채운다(한 번만)
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
// 「문서 올리기 · 첫 분석」 줄의 올리기 둘(2026-11-24 사용자 「문서 올리기, 첫분석에서 일단 목적문서 올리기, 참조문서 올리기 기능이 있어야지」 — spec_양식작성 ② §6 「워크플로우 개요 · 문서 칸」).
// 목적 문서 올리기 = 이 워크플로우의 양식을 다른 파일로 바꾼다 — 새 작업으로 올려 같은 묶음(프로젝트 · 워크플로우 · 라운드)에 넣고 그 문서를 연다 · 지금 문서는 묶음에서 나온다(작업 리스트에는 남음 — taskSlotSet 과 같은 규칙).
// 참조 문서 올리기 = 문서 라이브러리 서버에 바로 올린다(POST /api/doclib/docs — 8114 가 건네 줌 · 새 탭 없이). 자료 추출은 2단계(그 서버의 화면)에서.
function fwPick(accept, multiple, fn) { const inp = el("input"); inp.type = "file"; inp.accept = accept; inp.multiple = multiple; inp.onchange = () => inp.files.length && fn([...inp.files]); inp.click(); }
async function fwTargetUpload(file) {
  if (!/\.hwpx?$/i.test(file.name)) return toast("목적 문서(채울 양식)는 hwp · hwpx 만 올릴 수 있습니다", true);
  if (!confirmDiscard()) return;
  const old = { id: state.id, task: { ...(state.task || {}) } }, epoch = state.epoch;
  if (!old.task.job) return toast("이 문서의 워크플로우가 정해지지 않았습니다 — 첫 화면에서 「양식 작성」 으로 시작하세요", true);
  toast(/\.hwp$/i.test(file.name) ? `${file.name} — hwpx 로 바꿔 올리는 중…(한글이 변환)` : `${file.name} 올리는 중…`);
  const fd = new FormData();
  fd.append("file", file);
  let d;
  try {
    d = await api("/api/docs?new=1", { method: "POST", body: fd });
    await api(`/api/works/${d.docId}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ ...old.task }) }); // 같은 묶음(프로젝트 · 워크플로우 · 라운드 · 작업 종류)
  } catch (e) { return toast(`목적 문서를 올리지 못했습니다: ${e.message}`, true); }
  api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 다음 줄 「헤딩 · 표 분석 · 작성 지침」 이 그 결과를 본다
  if (epoch !== state.epoch) return toast(`${file.name} — 올렸습니다(그 사이 다른 문서를 열어 화면은 그대로입니다)`);
  try { await load(d.docId, { tab: "Dash" }); }
  catch (e) { return toast(`${file.name} — 올렸지만 열지 못했습니다: ${e.message}`, true); }
  try { await api(`/api/works/${old.id}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ ...old.task, project: "" }) }); } // 옛 양식은 묶음에서 나온다(지우지 않음)
  catch (e) { toast(`옛 목적 문서를 묶음에서 빼지 못했습니다: ${e.message}`, true); }
  if (typeof loadWorks === "function") await loadWorks();
  toast(`${file.name} — 목적 문서로 넣었습니다(헤딩 · 표 분석을 겁니다). 앞 문서는 작업 리스트에 남습니다`);
}
async function fwRefUpload(files) {
  const ok = [], same = [], bad = [];
  for (const f of files) {
    if (!/\.(pdf|hwpx|hwp|docx)$/i.test(f.name)) { bad.push(`${f.name}(받지 않는 형식)`); continue; }
    toast(`${f.name} — 문서 라이브러리에 올리는 중…`);
    const fd = new FormData();
    fd.append("file", f);
    try { const r = await api("/api/doclib/docs", { method: "POST", body: fd }); (r.created ? ok : same).push(f.name); }
    catch (e) {
      if (e.status === 404 && e.message === "Not Found") { bad.push(`${f.name}(8114 서버가 옛 판입니다 — 서버를 다시 켠 뒤에 됩니다 · 그때까지는 「문서 라이브러리 열기」 로)`); break; } // 끝점이 없는 옛 서버
      bad.push(`${f.name}(${e.message})`);
    }
  }
  if (same.length && !ok.length && fwMark("keep") !== "done") await fwStepMark("keep", "done"); // 이미 라이브러리에 있던 문서 — 올린 때가 그 문서의 처음 때라 「이 문서의 몫」 으로 안 세어진다: 「있는 문서 쓰기」 와 같게 둔다
  const say = [ok.length ? `참조 문서 ${ok.length}개를 올렸습니다` : "", same.length ? `이미 라이브러리에 있는 문서 ${same.length}개(그것을 씁니다)` : "", bad.length ? `못 올림: ${bad.join(" · ")}` : ""].filter(Boolean).join(" · ");
  toast(`${say}${ok.length || same.length ? " — 자료 추출은 2단계 「자료 추출(MD)」 에서" : ""}`, !!bad.length);
  await fwRead(true);
  if (typeof dashDraw === "function") dashDraw(true);
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
  // 글은 이관의 「헤딩 · 표 분석」 줄과 같은 꼴(app.js taskSteps heads · workflow_units._heads — 2026-11-25 사용자 "연차보고서 이관 보고 스크립트 동작방식으로 표기해줘")
  const HG = "헤딩 그래프·표 구조: 양식";
  if (!A.view) return { state: "todo", text: "분석 결과를 읽는 중…" };
  if (!A.hwpx) return { state: "", text: "헤딩 · 표 분석은 hwpx 문서만 됩니다" };
  if (A.busy) return { state: "run", text: `${HG} 없음 · 양식 분석 중… — 끝나면 작성 지침을 모아 저장합니다`, acts: headsBtn };
  if (!A.base) return { state: "now", text: `${HG} 없음` + (A.bad ? ` · 양식 분석 실패 — ${[A.heads, A.tables].map((i) => i && i.error).filter(Boolean)[0] || "까닭 모름"}` : ""),
    acts: [dashBtn("분석", () => { Promise.resolve(headsFirst()).finally(() => typeof docStatusPing === "function" && docStatusPing()); toast("헤딩 · 표 분석을 겁니다(스크립트) — 진행은 이 줄과 문서 이름 줄에 보입니다"); }, { primary: true, title: "헤딩 그래프·표 구조를 스크립트로 분석합니다 — LLM 호출 없음 · 문서는 바뀌지 않습니다(이 단계만 — LLM 검증·보완은 다음 줄)", focus: "act:heads" }), ...headsBtn] };
  const tail = c ? `작성 지침 ${c.items + c.marks}개 저장(헤딩 ${c.headings} · 표 ${c.tables}${c.marks ? ` · 각주 번호 ${c.marksLinked || 0}/${c.marks}` : ""})` : FW.fg && FW.fg.error ? "작성 지침을 읽지 못했습니다" : "작성 지침을 모으는 중…";
  return { state: c ? "done" : "run", text: `${HG} 있음 · ${tail}${c && !(c.items + c.marks) ? "(양식에 적힌 지침이 없습니다 — 「작성 지침 확인 · 적기」 에서 적습니다)" : ""}`,
    acts: [...guideBtn, ...(c ? [dashBtn("다시 모으기", () => fwGuidesKeep(true).then(() => typeof dashDraw === "function" && dashDraw(true)), { title: "지금 문서에서 작성 지침을 다시 모아 저장합니다(스크립트 · 문서는 안 바뀜) — 문서에서 지운 지침은 저장본에 남습니다", focus: "act:heads:keep" })] : []), ...headsBtn] };
}
// 선택 줄(03 「LLM 검증·보완」 · 04 「작성 지침 확인 · 적기」)도 차례에 선다 — 2026-11-24 사용자 「전체 초기화를 했는데 1,2 번은 끝났다고 했는데 3,4번이 지나가지 않았는데 왜 5로 오냐 순서가 안맞음」:
// 전에는 선택 줄의 상태가 비어(「선택」) 「지금」 · 「다음: …」 이 05 로 건너뛰었다. 이제 앞 줄이 끝나면 선택 줄이 「지금」 이 되고, 하거나 「건너뛰기」 · 「확인함」 을 눌러야 지나간다
// (표시 = 작업 폴더 — PUT …/form-write/step: 작업 내용 초기화 · 준비 초기화가 함께 비운다 · spec_양식작성 ② §6 「선택 줄도 차례에」).
const fwMark = (key) => ((FW.gw && FW.gw.steps) || {})[key] || "";
function fwStepMark(key, mark, say) { // 표시를 남기거나(skip · done) 지운다(null) → 다시 그림
  if (!state.id) return;
  const id = state.id;
  return api(`/api/docs/${id}/form-write/step`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ key, mark }) })
    .then((r) => { if (state.id === id && FW.gw) FW.gw.steps = r.steps || {}; if (say) toast(say); })
    .catch((e) => toast(`표시를 남기지 못했습니다: ${e.message}`, true))
    .finally(() => typeof dashDraw === "function" && dashDraw(true));
}
// 「워크플로우 개요」 · 「문서 올리기 · 첫 분석」 의 문서 칸(2026-11-24 사용자 "여기 문서는 목적문서랑, 참조문서 넣는 곳을 넣어줘야지.. 그리고 어떤 tak 인지도 워크플로우 개요 단계가 있어야지 하지 않냐?" — spec_양식작성 ② §6 「워크플로우 개요 · 문서 칸」)
function fwOverviewStep() { // 보기만 하는 줄(상태 꼬리표 없음 · 「지금」 자리를 차지하지 않음) — 이 워크플로우가 받는 것 · 만드는 것 · 단계의 차례
  const reg = typeof DASH === "object" && DASH.reg && (DASH.reg.tasks || []).find((t) => t.job === "form_write");
  const name = (reg && reg.name) || (typeof TASK_CATALOG === "object" && TASK_CATALOG.form_write && TASK_CATALOG.form_write.name) || "양식 작성";
  const order = Object.keys(FW_STAGE_RESET).map((st) => `${fwStageWord(st)} ${FW_STAGE_RESET[st].name}`).join(" → ");
  return { state: "", text: "", lines: [
    ["워크플로우", `${name} — 양식 문서를 참조 문서에서 뽑은 자료로 채웁니다`],
    ["받는 것", "목적 문서(채울 양식 — 지금 문서) · 참조 문서(자료 문서 — 문서 라이브러리에 올려 내용을 뽑습니다)"],
    ["만드는 것", "자료에 있는 내용으로 채운 양식 — 넣을 것은 초안(제안 카드)으로 보이고 「문서에 반영」 을 누른 것만 들어갑니다"],
    ["차례", order]],
    acts: [dashBtn("워크플로우 상세 보기", () => window.open(`/workflow#${encodeURIComponent("form_write")}`, "_blank", "noopener"), { title: "워크플로우 페이지에서 이 워크플로우의 단계 · 조건 보기(새 탭)", focus: "act:overview" })] };
}
function fwOpenStep(o) { // 문서 칸 둘 — 목적 문서(지금 문서) · 참조 문서(문서 라이브러리 — 올리기는 그 서버의 화면에서: 8114 는 읽기만)
  const ref = !o.lib.alive ? "문서 라이브러리 서버가 꺼져 있습니다 — tools/start_doclib.ps1 로 띄웁니다"
    : o.keepOk ? (o.newDocs ? `이 문서의 몫 ${o.newDocs}개(라이브러리 전체 ${o.docs}개)` : `라이브러리에 있는 문서를 씁니다(${o.docs}개)`)
    : o.docs ? `라이브러리에 ${o.docs}개 — 이 문서의 몫은 아직 없습니다(「참조 문서 올리기…」 로 올리거나 2단계 「있는 문서 쓰기」)` : "아직 없습니다 — 「참조 문서 올리기…」 로 문서 라이브러리에 올립니다";
  return { state: state.id ? "done" : "now", text: "", lines: [
    ["목적 문서(채울 양식)", state.name || "—"],
    ["참조 문서(자료 문서)", `${ref}${o.mats ? ` · 이 문서의 자료 ${o.mats}개` : ""}`]],
    acts: [dashBtn("목적 문서 올리기…", () => fwPick(".hwp,.hwpx", false, (fs) => fwTargetUpload(fs[0])), { title: "채울 양식(hwp · hwpx)을 다른 파일로 바꿉니다 — 새 작업으로 올려 이 워크플로우에 넣고 그 문서를 엽니다(헤딩 · 표 분석을 바로 겁니다). 지금 문서는 묶음에서 나오고 작업 리스트에 남습니다", focus: "act:open:target" }),
      dashBtn("참조 문서 올리기…", () => fwPick(".pdf,.hwpx,.hwp,.docx", true, fwRefUpload), { primary: !!o.lib.alive && !o.keepOk, disabled: !o.lib.alive, title: o.lib.alive ? "참조 문서(pdf · hwpx · hwp · docx — 여럿 가능)를 문서 라이브러리에 바로 올립니다(새 탭 없이) — 자료 추출은 2단계에서" : FW_LIB_DOWN, focus: "act:open:ref" }),
      ...(o.lib.alive ? [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { title: "올린 참조 문서를 보거나 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다", focus: "act:open:lib" })] : [])] };
}
function fwLibStep(key, o) { // 06 「자료 문서 올리기」(keep) · 07 「자료 추출(MD)」(extract) — 이 문서의 몫으로 센다(o.fresh = 기준 시각 뒤의 것 · o.all = 라이브러리 전체)
  const isKeep = key === "keep", noun = isKeep ? "자료 문서" : "끝난 추출", mark = fwMark(key) === "done", ok = !!o.fresh || mark;
  const use = isKeep ? "있는 문서 쓰기" : "있는 추출 쓰기";
  const acts = [...o.libBtn(`act:${key}`)];
  if (ok && mark && !o.fresh) acts.push(dashBtn("쓰기 취소", () => fwStepMark(key, null, `${isKeep ? "06" : "07"} 을 다시 할 일로 둡니다`), { title: "이 줄을 다시 할 일로 둡니다", focus: `act:${key}:undo` }));
  if (!ok && o.all) acts.push(dashBtn(use, () => fwStepMark(key, "done", `라이브러리에 있는 ${noun}를 씁니다`), { title: `새로 ${isKeep ? "올리지" : "추출하지"} 않고 문서 라이브러리에 이미 있는 ${noun}를 이 문서에 씁니다 — 이 줄을 끝남으로 둡니다(「쓰기 취소」 로 되돌립니다)`, focus: `act:${key}:use` }));
  if (o.going) return { state: "run", text: `추출 중 ${o.going}개${o.all ? ` · 끝난 추출 ${o.all}개` : ""}`, acts };
  const down = !o.alive ? { word: "서버 꺼짐" } : {};
  if (ok) return { state: "done", ...(mark && !o.fresh ? { word: "있는 것 씀" } : {}), text: o.fresh ? `이 문서의 몫 — ${noun} ${o.fresh}개${o.all > o.fresh ? ` (라이브러리 전체 ${o.all}개)` : ""}` : `라이브러리에 있는 ${noun}를 씁니다(${o.all}개)`, acts };
  const text = !o.alive ? FW_LIB_DOWN : o.all ? `아직 안 했습니다 — 라이브러리에 ${noun} ${o.all}개가 있습니다. 새로 ${isKeep ? "올리거나" : "추출하거나"} 「${use}」` : isKeep ? "아직 자료 문서가 없습니다" : "아직 추출한 것이 없습니다";
  const state = o.mats ? (o.alive ? "ready" : "hold") : isKeep || o.prev ? "now" : "todo";
  return { state, ...(state === "hold" || state === "now" ? down : {}), text, acts };
}
async function fwChangeExamples(files, removeId = "") {
  if (FW.changingExamples) return;
  const id = state.id, epoch = state.epoch, url = `/api/docs/${id}/form-examples`, errors = [];
  const here = () => id === state.id && epoch === state.epoch;
  FW.changingExamples = true;
  fwAutoRedraw();
  try {
    if (removeId) await api(`${url}/${encodeURIComponent(removeId)}`, { method: "DELETE" });
    else for (const file of files) {
      if (!here()) break;
      const form = new FormData(); form.append("file", file);
      try { await api(url, { method: "POST", body: form }); }
      catch (e) { errors.push(`${file.name} — ${e.message}`); }
    }
    if (here() && fwMark("headsLlm") === "skip" && (removeId || files.length > errors.length)) await fwStepMark("headsLlm", null, "바뀐 참고 서식으로 검증·보완할 수 있습니다");
  } catch (e) { errors.push(e.message); }
  finally {
    if (here()) {
      await FW.loading;
      await fwRead(true);
      if (here()) {
        FW.changingExamples = false; fwAutoRedraw();
        if (errors.length) toast(errors.join("\n"), true);
      }
    }
  }
}
async function fwStartGuidance() {
  const id = state.id, epoch = state.epoch;
  if (!(await dsLlmRun(true)) || id !== state.id || epoch !== state.epoch) return false;
  await dsRefresh();
  await FW.loading;
  if (id !== state.id || epoch !== state.epoch) return false;
  await fwRead(true);
  fwAutoRedraw();
  return true;
}
async function fwCriteriaOpen() {
  fwClearWay();
  const { tools, body } = headsDlg("fwCriteria", "검증·보완 지침", "목적 양식과 샘플·추가 서식을 대조할 때 LLM이 따르는 기준입니다.");
  const seq = heads.seq, epoch = state.epoch;
  const alive = () => heads.dlg === "fwCriteria" && heads.seq === seq && state.epoch === epoch;
  tools.append(hBtn("다시 읽기", fwCriteriaOpen, { title: "현재 설정된 지침을 다시 읽습니다" }));
  body.append(el("p", "hnote lg-msg", "지침을 읽고 있습니다…"));
  try {
    const agent = await api("/api/agents/writing_guidance");
    if (!alive()) return;
    const guide = agent.prompt.find((p) => p.kind === "merge" && p.name === "writing_guidance");
    const contract = agent.prompt.find((p) => p.kind === "contract");
    body.replaceChildren(guide?.text ? llmGuidePart({ ...guide, key: "guide", note: guide.custom ? "LLM 아이콘에서 저장한 판정 지침을 사용합니다." : "" })
      : el("p", "hnote lg-msg", "현재 설정된 검증·보완 판정 지침이 없습니다."));
    if (contract?.text) body.append(llmGuidePart({ ...contract, key: "contract", title: "입력과 판정 결과 작성 규칙" }));
  } catch (e) {
    if (alive()) body.replaceChildren(el("p", "hwarn lg-msg fail", `검증·보완 지침을 읽지 못했습니다 — ${e.message}`));
  }
}
function fwLlmStep(A) {
  if (!A.view || !A.hwpx) return { state: "", text: "" };
  const v = A.view, chain = !!(v.job && v.job.chain && v.job.status === "running"), four = (v.items || []).filter((i) => ["heads", "templates", "formats", "tables"].includes(i.key) && i.llm);
  const doneN = four.filter((i) => i.llm.state === "done").length, bad = four.some((i) => i.llm.state === "failed"), skip = fwMark("headsLlm") === "skip", llmOn = !(FW.gw && FW.gw.enabled === false);
  const g = FW.guidance || {}, files = FW.examples || [], extracting = fwExtractingGuides(), busy = chain || extracting || !!FW.changingExamples;
  const all = !!four.length && doneN === four.length && g.ready;
  const lines = [["추가 샘플·서식", FW.examplesError ? `목록을 읽지 못했습니다 — ${FW.examplesError}` : files.map((f) => f.name).join(" · ") || "첨부 없음"]];
  if (g.ready) {
    const refs = g.sourceDetails || [];
    lines.push(["LLM이 읽은 입력", `${refs.length ? `출처 ${g.sources.length}개` : (g.sources || []).join(" · ")} · 그림 ${g.images || 0}장`]);
    for (const r of refs) {
      const parts = [];
      if (r.included === false) parts.push("미첨부");
      else {
        if (r.images) parts.push(`그림 ${r.images}장`);
        if (Number.isInteger(r.citedPlaces)) parts.push(`지침 근거 ${r.citedPlaces}곳`);
      }
      if (r.cut) parts.push("일부 발췌");
      if (parts.length) lines.push([r.name, parts.join(" · ")]);
    }
    if (g.cut) lines.push(["읽은 범위", "일부 입력은 분량 또는 그림 제한으로 줄였습니다."]);
  }
  const criteria = dashBtn("검증·보완 지침 보기", fwCriteriaOpen,
    { title: "목적 양식과 샘플·추가 서식을 대조할 때 LLM이 따르는 판정 기준을 봅니다.", focus: "act:headsLlm:criteria" });
  const attach = dashBtn("샘플·추가 서식 첨부…", () => fwPick(".hwp,.hwpx,.docx,.pdf,.txt,.md,.png,.jpg,.jpeg,.webp", true, fwChangeExamples),
    { disabled: busy, title: "작성 예시나 함께 비교할 서식을 올립니다. 이 작업의 자리별 작성 방법을 추출할 때 읽습니다.", focus: "act:headsLlm:attach" });
  const guideActions = [criteria, attach, ...files.map((f) => dashBtn(`${f.name} 빼기`, () => fwChangeExamples([], f.id),
    { disabled: busy, title: "이 작업의 작성 지침 참고 파일에서 뺍니다", focus: `act:headsLlm:remove:${f.id}` }))];
  if (chain || extracting) return { state: "run", text: extracting ? "목적 문서의 예시와 첨부 서식을 읽고 자리별 작성 지침을 추출하고 있습니다" : "헤딩 · 표 · 서식을 검증하고 있습니다", lines,
    acts: chain && !extracting ? [dashBtn("멈춤", () => dsLlmStop(), { title: "진행 중인 구조 판정이 끝나면 멈춥니다", focus: "act:headsLlm:stop" }), ...guideActions] : guideActions };
  const run = [dashBtn("LLM 검증·보완", fwStartGuidance, { primary: !all && !skip && A.base && llmOn, disabled: !A.base || A.busy || A.llmBusy || busy || !llmOn,
    title: "헤딩·표를 검증한 뒤 목적 문서 속 예시와 추가 서식에서 자리별 작성 지침을 추출합니다(유료 LLM).", focus: "act:headsLlm" }), ...guideActions];
  if (all && g.run?.state !== "failed") {
    const j = g.judgmentCounts;
    const text = j ? `LLM이 ${g.placeCount}곳을 판정했습니다 · 지침 적용 ${j.apply}곳 · 해당 없음 ${j.not_applicable}곳 · 근거 부족 ${j.insufficient}곳` : `자리 ${g.count}곳의 작성 지침을 추출했습니다`;
    return { state: "done", text, lines, acts: [...run, dashBtn("추출 지침 보기", () => fwWriteOpen("guides"), { focus: "act:headsLlm:view" })] };
  }
  if (skip) return { state: "done", skipped: true, word: "건너뜀", text: "건너뜀 — 스크립트 분석 결과로 진행합니다(LLM 검증·보완은 지금이라도 할 수 있습니다)", lines,
    acts: [...run, dashBtn("건너뛰기 취소", () => fwStepMark("headsLlm", null, "LLM 검증·보완을 다시 할 일로 둡니다"), { title: "이 줄을 다시 할 일로 둡니다", focus: "act:headsLlm:unskip" })] };
  if (!A.base) return { state: "todo", text: "헤딩 · 표 분석이 끝나야 합니다", lines, acts: run };
  if (!llmOn) return { state: "done", skipped: true, word: "건너뜀", text: "LLM 을 쓸 수 없어 건너뜁니다 — 스크립트 분석 결과로 진행합니다", lines, acts: run };
  const failure = g.run?.state === "failed" ? g.run.error : v.job?.status === "failed" ? v.job.error : g.error;
  const text = failure || (bad ? "구조 판정이 실패했습니다. 다시 실행하거나 건너뛸 수 있습니다." : g.stale ? "입력이 바뀌었습니다. 현재 양식과 첨부로 작성 지침을 다시 추출하세요." : doneN ? `구조 판정 ${doneN}/${four.length} · 자리별 작성 지침 추출 전` : "목적 문서의 작성 예시를 읽습니다. 함께 비교할 샘플·서식이 있으면 실행 전에 첨부하세요.");
  return { state: "now", text, lines, acts: [...run, dashBtn("건너뛰기", () => fwStepMark("headsLlm", "skip", "LLM 검증·보완을 건너뜁니다 — 스크립트 분석 결과로 진행합니다"), { title: "스크립트 분석 결과로 다음 줄로 넘어갑니다", focus: "act:headsLlm:skip" })] };
}
function fwGuidesStep(gw, A, heads, guided) { // 04의 자리별 판정이 있으면 05는 추가 메모용이다.
  const topics = FW.fr && FW.fr.review && FW.fr.review.topics, mark = fwMark("guides");
  // 2026-11-24 사용자 "작성 지침 확인/적기가.. 지침작성 자리가 맞냐? 지침 작성 자리에는 양식검토, 채울자리 이렇게 있던데?" — 열의 맨 위(자료 · 양식 검토)가 아니라 「채울 자리」 로 바로 가서 지침을 펼치고 그 자리에서 적는다(fwWriteOpen("guides"))
  const open = (primary) => dashBtn("지침 보기 · 적기", () => fwWriteOpen("guides"), { primary, title: "「지침 작성」 열의 「채울 자리」 로 갑니다 — 자리마다 작성 지침이 펼쳐지고, 헤딩 자리에는 그 자리에서 지침을 적습니다(문서는 안 바뀜)", focus: "act:guides" });
  const more = topics && topics.length ? [dashBtn("테마 · 키워드 보기", () => fwWriteOpen("topics"), { title: "양식 검토가 뽑은 「자료에서 찾을 테마 · 키워드」 — 골라서 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사합니다", focus: "act:guides:topics" })] : [];
  if (gw.hwpx === false) return { state: "", text: "hwpx 문서만 됩니다", acts: [open(false), ...more] };
  const base = `헤딩 ${heads}곳 · 작성 지침이 있는 자리 ${guided}곳`;
  if (mark) return { state: "done", ...(mark === "skip" ? { skipped: true, word: "건너뜀" } : { word: "확인함" }), text: `${mark === "skip" ? "건너뜀" : "확인함"} — ${base}`,
    acts: [open(false), ...more, dashBtn(mark === "skip" ? "건너뛰기 취소" : "확인 취소", () => fwStepMark("guides", null, "작성 지침 확인을 다시 할 일로 둡니다"), { title: "이 줄을 다시 할 일로 둡니다", focus: "act:guides:undo" })] };
  if (A.base && FW.guidance?.ready && FW.guidance.audited) return { state: "done", word: "자동 판정",
    text: "양식 검토와 초안 작성에 LLM의 자리별 판정을 사용합니다. 필요할 때 추가 지침을 적을 수 있습니다.", acts: [open(false), ...more] };
  if (!A.base) return { state: "todo", text: `${base} — 헤딩 · 표 분석이 끝나야 합니다`, acts: [open(false), ...more] };
  return { state: "now", text: `선택 — ${base}. 지침을 보고 없는 자리에 적은 뒤 「확인함」, 볼 것이 없으면 「건너뛰기」`,
    acts: [open(true), ...more, dashBtn("확인함", () => fwStepMark("guides", "done", "작성 지침을 확인했습니다"), { title: "작성 지침을 확인했습니다 — 다음 줄로 넘어갑니다(「확인 취소」 로 되돌립니다)", focus: "act:guides:done" }),
      dashBtn("건너뛰기", () => fwStepMark("guides", "skip", "작성 지침 확인을 건너뜁니다"), { title: "확인하지 않고 다음 줄로 넘어갑니다(「건너뛰기 취소」 로 되돌립니다)", focus: "act:guides:skip" })] };
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

async function formWriteLive(M = null) { // 대시보드(dashboard.js dashLive)의 「양식 작성」 가지 — 단계마다 지금 상태와 그 일을 하는 곳을 여는 단추 · M = 대시보드 모델(머리 아래 「전체 실행」 을 M.top 에) · 「작업 개요」(fwOverviewDraw)도 같은 셈을 쓴다
  await fwRead();
  const lib = FW.lib || { alive: false, docs: [] }, gw = FW.gw || { places: [], materials: [], run: null, enabled: false }, run = gw.run;
  const libBtn = (focus) => [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다" : FW_LIB_DOWN, focus })];
  const docs = lib.docs.length, done = fwDoneExtracts(), going = lib.docs.reduce((n, d) => n + (d.running || 0), 0), mats = gw.materials.length, guided = gw.places.filter((p) => p.n).length, heads = gw.places.filter((p) => p.kind === "head").length;
  const from = gw.libFrom || 0, newDocs = lib.docs.filter((d) => (d.at || 0) > from).length, newDone = lib.docs.reduce((n, d) => n + (d.extracts || []).filter((e) => e.state === "done" && (e.ended || 0) > from).length, 0);
  const keepOk = !!newDocs || fwMark("keep") === "done";
  const items = (run && run.items) || [], got = items.reduce((n, i) => n + (i.proposals || 0), 0), applied = fwAppliedN(run);
  const rv = FW.fr && FW.fr.review, topics = rv && rv.topics;
  const next = !mats ? "take" : "ask";
  let A = fwAnalysis();
  if (!A.view && state.id && typeof dsRefresh === "function") { await dsRefresh(); A = fwAnalysis(); } // 이름 줄의 분석 상태를 아직 못 읽음 — 한 번 읽고 그린다
  if (A.base && FW.fg && !FW.fg.saved && !FW.fgAsked) await fwGuidesKeep(); // 분석이 끝났는데 저장한 작성 지침이 없다 — 한 번 모아 저장(스크립트)
  const S = {
    overview: fwOverviewStep(),
    open: fwOpenStep({ lib, docs, newDocs, mats, keepOk, libBtn }),
    heads: fwHeadsStep(A),
    headsLlm: fwLlmStep(A),
    // 줄의 차례 = 등록부의 차례(「지금」 은 차례상 첫 줄 하나): 준비(… · 작성 지침 확인 · 양식 검토 · 찾을 테마) → 자료 준비 → 작성(작성 계획 · 확인할 것 → 양식 초안 작성 → 검사 → 반영)
    guides: fwGuidesStep(gw, A, heads, guided),
    review: fwReviewStep(gw),
    // 서버가 꺼져 「hold」 일 때 상태 글은 「서버 꺼짐」 — 대시보드의 공용 글 DASH_ST.hold 는 취합의 「기관 미지정」 이라 이 줄에 맞지 않았다(2026-11-24 화면 검사 그림 · 사용자 「진행해줘」)
    // 자료가 아직 없으면 06 이 「지금」 자리를 차지한다(서버가 꺼져도 — 글자만 「서버 꺼짐」): 전에는 꺼지면 「hold」 라 자리를 안 차지해 05 → 08 로 건너뛰었다(2026-11-24 사용자 「한번에 5번에서 8번으로 가버리냐?」).
    // 자료를 이미 다른 길(에이전트 보기의 파일 · 글)로 받았으면 06 · 07 은 자리를 차지하지 않는다(할 수 있음 · 꺼졌으면 「서버 꺼짐」).
    // 06 · 07 의 「끝남」 은 이 문서의 몫으로 센다(2026-11-24 사용자 「초기화 할때 5,6 도 아직 안했다고 나와야지」): 문서 라이브러리는 모든 작업이 같이 쓰는 서버라 그 서버에 있는 것만으로 세면 초기화해도 끝남이 남았다 —
    // 기준 시각(gw.libFrom — 작업을 만든 때 · 마지막 초기화 · 「2단계 초기화」) 뒤에 올린 문서 · 끝난 추출이 있거나, 있는 것을 쓰겠다고 누른 때(「있는 문서 쓰기」 · 「있는 추출 쓰기」)만 끝남.
    keep: fwLibStep("keep", { alive: lib.alive, all: docs, fresh: newDocs, mats, prev: null, libBtn }),
    extract: fwLibStep("extract", { alive: lib.alive, all: done, fresh: newDone, mats, going, prev: keepOk, libBtn }),
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
  const AU = fwAuto && fwAuto.id === state.id ? fwAuto : null;
  if (AU && AU.key && S[AU.key] && S[AU.key].state !== "done") S[AU.key].state = "run"; // 「한 번에 진행」 이 지금 하는 줄(fwAutoRun)
  let nowSeen = false; // 「지금」 은 차례상 첫 줄 하나 — 뒤의 줄은 할 수 있어도 「할 수 있음」(단추는 그대로 보인다): 줄마다 따로 셈해 「지금」 이 여럿 서던 것(2026-11-24 사용자 「지금은 긴 몇개냐」)
  // 「진행 중」(run) 인 줄도 그 자리를 차지한다 — 앞 줄이 도는데 뒤 줄에 「지금」 이 같이 서던 것(2026-11-24 사용자 「3번 5번은 왜 동시에 나오냐?」 — 03 LLM 검증·보완 진행 중 + 05 양식 검토 지금)
  for (const s of Object.values(S)) { if (s.state === "run") nowSeen = true; else if (s.state === "now") { if (nowSeen) s.state = "ready"; nowSeen = true; } }
  if (fwRunning() || fwReviewing() || fwExtractingGuides() || going || A.busy || (A.view && A.view.job && A.view.job.status === "running")) { clearTimeout(FW.poll); FW.poll = setTimeout(() => { fwRead(true).then(() => { if (typeof dashDraw === "function") dashDraw(); fwRedraw(); }); }, 2500); }
  const off = fwStageResetOff(A), runs = {}, subs = {}, ends = {};
  for (const st of Object.keys(FW_STAGE_RESET)) { // 묶음 머리마다 「한 번에 진행」(fwAutoRun — 이관의 묶음 머리와 같은 자리) + 「N단계 초기화」(단계별 초기화 — 번호 = 묶음 머리의 번호: fwStageNo) — 초기화를 누르면 그 묶음 머리 아래에 확인 줄(fwStageResetEl)
    const box = el("span", "dash-grun");
    box.append(fwAutoBtn(S, [st]), dashBtn(`${fwStageWord(st)} 초기화`, () => { FW.rs = FW.rs === st ? "" : st; dashDraw(true); }, { disabled: !!off || !!FW.rsBusy, focus: `fwreset:${st}`,
      title: off || `${fwStageName(st)} 초기화 — 누르면 확인 줄이 펴집니다(누르기 전에는 아무것도 안 바뀝니다)` }));
    runs[st] = box;
    if (FW.rs === st) subs[st] = fwStageResetEl(st, off, mats);
    const end = FW_AUTO_END[st];
    if (end && end.id === state.id && !AU) ends[st] = { ok: end.ok, text: end.text }; // 마지막 「한 번에 진행」 의 끝(남긴 것 · 멈춘 까닭) — 다른 문서 · 다시 돌리는 동안에는 안 보임
  }
  const rest = Object.keys(FW_AUTO_KEYS).filter((st) => fwAutoLeft(S, st).length);
  if (M && rest.length) M.top.push(fwAutoBtn(S, rest, true)); // 머리 아래 「전체 실행」(이관의 「이어서 한 번에」 자리) — 할 일이 남은 첫 묶음 → 끝 묶음
  return { runs, subs, ends, steps: S };
}

// ---- 단계별 「한 번에 진행」 · 「전체 실행」(2026-11-25 사용자 "단계 별라 자동실행 기능 넣어주고, , 전체 실행 넣어주고 이것도 연차보고서 이관 task 참조해서" — spec_양식작성 ② §6-2) ----
// 새 실행 길이 아니다 — 줄마다의 단추가 부르는 끝점 · 함수(headsFirst · dsLlmRun · …/form-review · …/guide-write/run)를 차례로 부르고 그 줄의 상태(formWriteLive 의 셈)가 끝남이 될 때까지 기다린다.
// 사람이 해야 하는 줄은 멈추거나 남긴다(spec_작업에이전트 ② §7 ⓐ): 선택 확인 줄(05 작성 지침 확인)은 남기고 지나가고, 할 수 없는 줄(자료 문서 올리기 · 자료 추출 · 자료 가져오기 · 확인할 것의 답 · 문서에 반영)은 그 자리에서 멈춘다.
// **문서에 반영은 하지 않는다** — 초안은 제안 카드로 남고 사람이 「문서에 반영」 을 누른다(CLAUDE.md 「양식을 채우는 길을 넓힐 때 제안 없이 문서에 넣는 길을 따로 만들지 않는다」). 유료 LLM(LLM 검증·보완 · 양식 검토 · 작성 계획 · 초안)은 확인 창 없이 부른다(이관의 「한 번에 진행」 과 같다 — 단추의 풍선에 적음).
// 실행은 시작할 때의 문서로 못 박는다(다른 문서를 열면 멈춤 — ② §7 ⓔ) · 진행은 에이전트 보기의 진행 카드(agwRunning — doc_agent_work.js)와 대시보드 머리에 보인다.
const FW_AUTO_KEYS = { open: ["heads", "headsLlm", "guides", "review"], material: ["keep", "extract", "take"], write: ["plan", "ask", "apply"] };
const FW_AUTO_END = {}; // 묶음 → {id(문서), ok, text} — 마지막 「한 번에 진행」 의 끝
let fwAuto = null; // {id, label, stages, key, note, t0, stop}
function fwAutoRunning() { // agwRunning 의 한 갈래(doc_agent_work.js) — {label, note, t0, stopping, stop} | null
  if (!fwAuto || fwAuto.id !== state.id) return null;
  const A = fwAuto;
  return { label: A.label, note: A.note || "진행 중", t0: A.t0, stopping: !!A.stop, stop: () => { A.stop = true; fwAutoRedraw(); } };
}
function fwAutoLeft(S, st) { // 그 묶음에서 아직 끝나지 않은 줄(상태가 있는 줄만 — 보기 줄 · 검사 줄 · 「hwpx 만」 은 뺌)
  return FW_AUTO_KEYS[st].filter((k) => S[k] && S[k].state && S[k].state !== "done");
}
const fwStageLabel = (st) => `${fwStageWord(st)} 「${FW_STAGE_RESET[st].name}」`;
function fwAutoBtn(S, stages, chain = false) { // 묶음 머리의 「한 번에 진행」 · 머리 아래 「전체 실행 N→M단계」
  const left = stages.flatMap((st) => fwAutoLeft(S, st)), busy = fwAutoRunning() || (typeof agwRunning === "function" ? agwRunning() : null);
  const no = !state.stored ? "작업 저장이 꺼진 문서에서는 할 수 없습니다" : busy ? `「${busy.label}」 이(가) 끝난 뒤에 쓸 수 있습니다` : fwRunning() ? "초안을 받는 중입니다 — 끝난 뒤에 쓸 수 있습니다" : fwReviewing() ? "양식 검토가 도는 중입니다 — 끝난 뒤에 쓸 수 있습니다"
    : fwExtractingGuides() || FW.changingExamples ? "작성 지침과 첨부를 처리하는 중입니다" : FW.rsBusy ? "초기화하는 중입니다" : !left.length ? "남은 단계가 없습니다" : "";
  const range = chain ? `${fwStageNo(stages[0]).replace(/단계$/, "")}→${fwStageWord(stages[stages.length - 1])}` : "";
  const label = chain ? `전체 실행 ${range}` : "한 번에 진행";
  const does = stages.map((st) => `${fwStageLabel(st)} — ${FW_AUTO_DOES[st]}`).join("\n");
  const b = dashBtn(label, () => fwAutoRun(stages, chain ? `전체 실행 ${range}` : `${fwStageLabel(stages[0])} — 한 번에 진행`), { disabled: !!no, focus: chain ? "run:chain" : `run:${stages[0]}`,
    title: no || `${chain ? "남은 묶음을 이어서 한 번에" : "이 묶음의 남은 줄을 차례로 한 번에"} — 사람 손이 필요한 곳에서는 멈춥니다(문서에 반영은 하지 않습니다 — 초안은 제안 카드로 남습니다)\n${does}` });
  b.dataset.run = chain ? "chain" : stages[0];
  return b;
}
const FW_AUTO_DOES = {
  open: "헤딩 · 표 분석 → 작성 지침 저장 → LLM 검증·보완과 자리별 자동 판정(유료) → 양식 검토 · 찾을 테마(유료). 지침을 직접 보거나 적는 작업은 선택입니다.",
  material: "자료 문서 · 추출 · 자료가 있는지 봅니다 — 올리기 · 추출 · 가져오기는 사람이 하는 일이라 없으면 그 줄에서 멈춥니다(추출이 도는 중이면 끝날 때까지 기다립니다)",
  write: "작성 계획 세우기(유료 LLM 한 번 — 고른 자료) → 확인할 것이 남으면 멈춤 → 초안 받기(유료 LLM — 고른 자리, 없으면 작성 계획이 자료에서 쓸 것이 있다고 한 자리) → 「문서에 반영」 은 사람이 제안 카드에서(멈춤)",
};
function fwAutoRedraw() {
  if (typeof dashDraw === "function") dashDraw(true);
  fwOvSync();
}
const fwSleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function fwAutoRun(stages, label) {
  if (fwAuto || !state.id) return;
  const id = state.id, A = (fwAuto = { id, label, stages, key: "", note: "시작", t0: Date.now(), stop: false });
  for (const st of stages) delete FW_AUTO_END[st];
  const gone = () => state.id !== id;
  const fresh = async () => { if (typeof dsRefresh === "function" && !gone()) await dsRefresh(); if (!gone()) await fwRead(true); return gone() ? null : (await formWriteLive()).steps; };
  const wait = async (done, note, most = 40 * 60 * 1000) => { // done(S) → true 면 끝 — 멈춤 · 문서 바뀜 · 시간 넘김이면 그 까닭
    const t = Date.now();
    for (;;) {
      if (A.stop) return "멈춤 — 사람이 멈췄습니다";
      if (gone()) return "멈춤 — 다른 문서를 열었습니다";
      const S = await fresh();
      if (!S) return "멈춤 — 다른 문서를 열었습니다";
      if (await done(S)) return "";
      if (Date.now() - t > most) return `멈춤 — ${note}이(가) ${Math.round(most / 60000)}분 안에 끝나지 않았습니다(도는 일은 그대로 둡니다)`;
      A.note = note; fwAutoRedraw();
      await fwSleep(2500);
    }
  };
  const left = []; let halt = "", stageNow = stages[0];
  const step = async (k) => { // → "" | 멈춤 까닭 — 남긴 것은 left 에
    const S = await fresh();
    if (!S) return "멈춤 — 다른 문서를 열었습니다";
    const s = S[k] || {};
    if (!s.state || s.state === "done") return "";
    A.key = k; A.note = fwStepRef(k) || k; fwAutoRedraw();
    const name = fwStepRef(k) || k, An = fwAnalysis(), mats = ((FW.gw && FW.gw.materials) || []).length;
    if (k === "heads") {
      if (!An.hwpx) return "";
      if (!An.busy) await headsFirst();
      const w = await wait(() => { const X = fwAnalysis(); return X.base || X.bad; }, "헤딩 · 표 분석");
      if (w) return w;
      if (fwAnalysis().bad) return `멈춤 — ${name}: 분석이 실패했습니다(「헤딩 추출」 탭에서 확인합니다)`;
      if (!(FW.fg && FW.fg.saved)) await fwGuidesKeep();
      return "";
    }
    if (k === "headsLlm") {
      if (!An.llmBusy && !fwExtractingGuides() && !(await fwStartGuidance())) return `멈춤 — ${name}: LLM 검증·보완을 시작하지 못했습니다`;
      const w = await wait(() => { const X = fwAnalysis(); return !fwExtractingGuides() && !X.llmBusy && !(X.view && X.view.job && X.view.job.chain && X.view.job.status === "running"); }, "LLM 검증·보완과 작성 지침 추출");
      if (w) return w;
      const T = fwLlmStep(fwAnalysis());
      if (T.state !== "done") return `멈춤 — ${name}: ${T.text}`;
      return "";
    }
    if (k === "guides") { left.push(`${name} — 사람이 지침을 보고 「확인함」 · 「건너뛰기」 를 누르는 줄입니다`); return ""; }
    if (k === "review" || k === "plan") {
      if (k === "plan" && !mats) return `멈춤 — ${name}: 이 문서의 자료가 없습니다(「자료 가져오기」)`;
      if (k === "plan" && !(FW.fr && FW.fr.review)) return `멈춤 — ${name}: 먼저 「${fwStepRef("review") || "양식 검토"}」 를 하세요(작성 계획은 양식 검토 뒤 — 서버도 409)`;
      if (k === "plan" && fwPlanned() && (FW.fr.open || []).length) { fwWriteOpen(); return `멈춤 — ${name}: 쓰기 전에 확인할 것 ${FW.fr.open.length}개에 답하세요(「지침 작성」 열 위 — 답한 뒤 다시 「한 번에 진행」)`; }
      if (FW.gw && FW.gw.enabled === false) return `멈춤 — ${name}: LLM 을 쓸 수 없습니다`;
      if (!fwReviewing()) {
        const materials = k === "plan" ? [...(FW.mats && FW.mats.size ? FW.mats : new Set(FW.gw.materials.map((m) => m.id)))] : [];
        try { const got = await api(`/api/docs/${id}/form-review`, { method: "POST", headers: H_JSON, body: JSON.stringify({ materials, note: FW.note }) }); FW.fr = { ...(FW.fr || {}), run: got.run }; }
        catch (e) { return `멈춤 — ${name}: ${e.message || e}`; }
      }
      const w = await wait(() => !fwReviewing(), k === "plan" ? "작성 계획" : "양식 검토");
      if (w) return w;
      if (FW.fr && FW.fr.run && FW.fr.run.state === "failed") return `멈춤 — ${name}: ${FW.fr.run.error || "LLM 이 답하지 못했습니다"}`;
      if (k === "plan" && (FW.fr.open || []).length) { fwWriteOpen(); return `멈춤 — ${name}: 작성 계획을 세웠습니다 — 쓰기 전에 확인할 것 ${FW.fr.open.length}개에 답하세요(「지침 작성」 열 위 — 답한 뒤 다시 「한 번에 진행」)`; }
      return "";
    }
    if (k === "keep" || k === "extract") {
      if (k === "extract" && s.state === "run") { const w = await wait((X) => X.extract.state !== "run", "자료 추출"); if (w) return w; return ""; }
      if (mats) return ""; // 이 문서의 자료가 이미 있다(에이전트 보기에서 준 파일 · 글 포함) — 올리기 · 추출 없이 넘어간다(줄은 「할 수 있음」 그대로)
      return `멈춤 — ${name}: ${k === "keep" ? "참조 문서를 「참조 문서 올리기…」 로 올리거나 「있는 문서 쓰기」 를 누르세요" : "문서 라이브러리에서 뽑을 범위를 적고 추출하거나 「있는 추출 쓰기」 를 누르세요(이 서버는 추출을 시작하지 않습니다)"}`;
    }
    if (k === "take") { if (mats) return ""; fwTakeOpen(); return `멈춤 — ${name}: 추출한 MD 를 이 문서의 자료로 고르세요(문서 옆 열 「자료 가져오기」)`; }
    if (k === "ask") {
      if (!fwReviewReady()) return `멈춤 — ${name}: ${fwReviewWhy() || "작성 계획이 먼저입니다"}`;
      const places = fwAutoPlaces();
      if (!places.length) { fwWriteOpen("guides"); return `멈춤 — ${name}: 채울 자리를 고르세요(작성 계획에 자료에서 쓸 것이 있는 자리가 없습니다)`; }
      const materials = [...(FW.mats && FW.mats.size ? FW.mats : new Set(FW.gw.materials.map((m) => m.id)))], chunks = {};
      for (const p of FW.gw.places) if (p.kind === "box" && places.includes(p.id)) chunks[p.id] = [...fwChunkSet(p)];
      try { const got = await api(`/api/docs/${id}/guide-write/run`, { method: "POST", headers: H_JSON, body: JSON.stringify({ places, materials, note: FW.note, chunks }) }); FW.watch = got.run.id; if (FW.gw) FW.gw.run = got.run; }
      catch (e) { return `멈춤 — ${name}: ${e.message || e}`; }
      const w = await wait(() => !fwRunning(), `${name}(자리 ${places.length}곳)`);
      if (w) return w;
      if (typeof agentLoad === "function") agentLoad();
      const run = FW.gw && FW.gw.run, got = ((run && run.items) || []).reduce((n, i) => n + (i.proposals || 0), 0);
      if (!got) return `멈춤 — ${name}: 초안 0개${fwRunWhy(run) ? ` — ${fwRunWhy(run)}` : ""}`;
      return "";
    }
    if (k === "apply") return `멈춤 — ${fwStepRef("apply") || "반영"}: 받은 초안을 에이전트 보기의 제안 카드에서 보고 「문서에 반영」 을 누르세요(문서에 넣는 것은 사람이 고른 것만입니다)`;
    return "";
  };
  try {
    await (typeof dashRegLoad === "function" ? dashRegLoad() : null);
    outer: for (const st of stages) {
      stageNow = st;
      for (const k of FW_AUTO_KEYS[st]) { halt = await step(k); if (halt) break outer; }
      if (stages.length > 1) FW_AUTO_END[st] = { id, ok: true, text: "끝남" };
    }
  } catch (e) { halt = `멈춤 — ${e.message || e}`; }
  fwAuto = null;
  const tail = left.length ? ` · 남김 ${left.length}곳: ${left.join(" / ")}` : "";
  const text = halt ? `${halt}${tail}` : `끝남${tail}`;
  if (!gone()) {
    FW_AUTO_END[stageNow] = { id, ok: !halt, text: halt ? text.replace(/^멈춤 — /, "") : text.replace(/^끝남 · /, "끝남 — ") };
    toast(`${label} — ${text}`, !!halt);
    await fwRead(true);
  }
  fwAutoRedraw();
}
function fwAutoPlaces() { // 초안을 받을 자리 — 사람이 「지침 작성」 열에서 고른 자리, 없으면 작성 계획이 「자료에서 쓸 것」 을 적은 자리(이미 채운 줄 · 쓸 자리가 아래 상자에 있는 헤딩은 뺌 — 「모두 고르기」 와 같은 걸름)
  const ps = (FW.gw && FW.gw.places) || [], most = (FW.gw && FW.gw.limits && FW.gw.limits.places) || 40, ok = (p) => p.slot !== "filled" && !(p.kind === "head" && p.boxed && !p.slot);
  if (FW.picks.size) return ps.filter((p) => FW.picks.has(p.id)).map((p) => p.id).slice(0, most);
  const plan = (FW.fr && FW.fr.review && FW.fr.review.places) || {};
  return ps.filter((p) => ok(p) && plan[p.id] && plan[p.id].use).map((p) => p.id).slice(0, most);
}

// ---- 패널 「작업 개요」(2026-11-25 사용자 「작업개요가 없는데 연차보고서 이관에 보면 작업 개요 있을텐데 참조해줘」 — spec_양식작성 ② §6-3) ----
// 이관의 「작업 개요」 처럼 첫 카드(프로젝트 · 워크플로우 · 라운드 — app.js taskRow) + 문서 칸 + 묶음마다 접는 상자(머리 = 번호 · 이름 · 끝난 수 · 「한 번에 진행」 / 펴면 줄 목록과 줄의 단추)
// + 위 「전체 실행」. 상태 · 단추는 대시보드와 같은 셈(formWriteLive) — 따로 세지 않는다. 프로젝트 구성 · 구분 기준 칸은 없다(일반 문서 — 양식에 묶이지 않음).
const FW_OV_OPEN = "nfm.fwOvOpen"; // 펴 둔 묶음(이 브라우저에 기억)
let fwOvSeq = 0;
function fwOvShown() { return !!state.id && (state.task || {}).job === "form_write" && $("panel").dataset.tool === "Div" && !$("paneDiv").hidden; }
function fwOvSync() { if (fwOvShown()) fwOverviewDraw(); }
async function fwOverviewDraw() {
  const box = $("divBox"), seq = ++fwOvSeq, id = state.id;
  if (!box.firstChild) box.append(el("p", "dash-text muted", "읽는 중…"));
  if (typeof dashRegLoad === "function") await dashRegLoad();
  const M = { top: [] }, L = await formWriteLive(M);
  if (seq !== fwOvSeq || id !== state.id || !fwOvShown()) return;
  const reg = typeof DASH === "object" && DASH.reg && (DASH.reg.tasks || []).find((t) => t.job === "form_write"), S = L.steps;
  const keepFocus = document.activeElement && box.contains(document.activeElement) ? document.activeElement.dataset.dashFocus || "" : "";
  let open; try { open = new Set(JSON.parse(localStorage.getItem(FW_OV_OPEN) || "[]")); } catch { open = new Set(); }
  const out = [typeof taskRow === "function" ? taskRow() : el("div")];
  const docs = el("section", "dv-card fw-ov-docs"), dh = el("div", "dv-note-heading");
  dh.append(el("h3", null, "문서"), hHelp("문서 안내", "목적 문서 = 채울 양식(지금 문서) · 참조 문서 = 내용이 나오는 자료 문서(문서 라이브러리 — 따로 선 서버) · 자료 = 참조 문서에서 뽑아 이 문서로 가져온 MD", { note: true }));
  docs.append(dh);
  const dl = el("dl", "fw-ov-lines");
  for (const [k, v] of S.open.lines || []) dl.append(el("dt", null, k), el("dd", null, v));
  dl.append(el("dt", null, "자료"), el("dd", null, S.take.text));
  docs.append(dl);
  const da = el("div", "dash-acts");
  da.append(...(S.open.acts || [])); // 「자료 가져오기」 단추는 아래 그 줄에(같은 단추를 두 곳에 붙이면 뒤로 옮겨 간다)
  docs.append(da);
  out.push(docs);
  const flow = el("section", "dv-card fw-ov-flow"), fh = el("div", "dv-note-heading");
  fh.append(el("h3", null, "단계"), hHelp("단계 안내", "묶음마다 「한 번에 진행」 은 그 묶음의 남은 줄을 차례로 합니다 · 「전체 실행」 은 남은 묶음을 이어서 합니다. 사람이 해야 하는 줄(자료 올리기 · 추출 · 가져오기 · 확인할 것의 답 · 문서에 반영)에서는 멈추고, 선택 확인 줄은 남기고 지나갑니다. 문서에 반영은 하지 않습니다 — 초안은 제안 카드로 남습니다.", { note: true }));
  flow.append(fh);
  if (M.top.length) { const top = el("div", "dash-top"); top.append(...M.top); flow.append(top); }
  const R = fwAutoRunning();
  if (R) { const p = el("p", "dash-text", `진행 중 — ${R.label} · ${R.note}${R.stopping ? " · 이 일이 끝나면 멈춥니다" : ""}`); p.setAttribute("role", "status"); p.append(" ", hBtn("멈춤", R.stop, { cls: "btn sm", disabled: R.stopping })); flow.append(p); }
  let idx = 0, nowSeen = false;
  for (const g of (reg && reg.stages) || []) {
    const det = el("details", "fw-ov-stage"), sum = el("summary", "fw-ov-shead"), steps = g.steps.map((s) => ({ s, live: S[s.key] || {}, idx: ++idx }));
    const counted = steps.filter((x) => x.live.state && !x.s.optional), done = counted.filter((x) => x.live.state === "done").length;
    const here = steps.some((x) => x.live.state === "now" || x.live.state === "run");
    det.dataset.stage = g.id;
    det.open = open.has(g.id) || (here && !nowSeen);
    if (here) nowSeen = true;
    sum.append(el("span", "dash-gno", fwStageWord(g.id)), el("b", "dash-gname", g.name), el("span", "dash-gcount", `${done}/${counted.length}`));
    if (L.runs[g.id]) { const r = L.runs[g.id]; r.addEventListener("click", (e) => e.stopPropagation()); sum.append(r); }
    det.append(sum);
    if (L.ends[g.id]) det.append(el("p", `dash-gend fw-ov-end${L.ends[g.id].ok ? "" : " halt"}`, `${L.ends[g.id].ok ? "" : "멈춤 — "}${L.ends[g.id].text}`));
    if (L.subs[g.id]) det.append(L.subs[g.id]);
    const ol = el("ol", "fw-ov-steps");
    for (const x of steps) {
      const li = el("li", `fw-ov-step is-${x.live.state || "none"}`), head = el("div", "fw-ov-step-h");
      li.dataset.step = x.s.key;
      head.append(el("span", "fw-ov-no", String(x.idx).padStart(2, "0")), el("span", "fw-ov-name", x.s.name), el("span", "fw-ov-st", x.live.word || FW_OV_WORD[x.live.state] || (x.s.optional ? "선택" : "")));
      if (x.s.by.includes("llm")) head.append(dashPromptButton(x.s));
      li.append(head);
      if (x.live.text) li.append(el("p", "fw-ov-text", x.live.text));
      if ((x.live.acts || []).length && x.s.key !== "open") { const a = el("div", "dash-acts"); a.append(...x.live.acts); li.append(a); }
      ol.append(li);
    }
    det.append(ol);
    det.addEventListener("toggle", () => { if (det.open) open.add(g.id); else open.delete(g.id); try { localStorage.setItem(FW_OV_OPEN, JSON.stringify([...open])); } catch { /* 기억만 안 함 */ } });
    flow.append(det);
  }
  out.push(flow);
  box.replaceChildren(...out);
  if (keepFocus) { const b = [...box.querySelectorAll("button")].find((x) => x.dataset.dashFocus === keepFocus); if (b) b.focus({ preventScroll: true }); }
}
const FW_OV_WORD = { done: "✓ 끝남", now: "지금", run: "진행 중", ready: "할 수 있음", todo: "남음", hold: "서버 꺼짐" };

// ---- 단계 초기화(2026-11-24 사용자 "여기도... 초기화 하고 싶을때가 있는데 새로 프로젝트를 올려야 하나? 준비/자료,작성 단계를 따로 두고 단계별로 실행할 수 있거나.. 모두 작업 내용 초기화 할 수 있도록 해줘" — spec_양식작성 ② §6-1) ----
// 묶음(등록부의 open · material · write)마다 그 단계의 것만 비운다. 뒤 단계는 앞 단계에 기댄다 — 준비를 초기화하면 작성도 함께(자료는 남는다).
// 2026-11-24 사용자 "복잡하게 하지 말고,, 전체 초기화 각 단계별 초기화로 해줘, 작성 3단계, 2, 자료준비 단계.. 단계로 해주고": 초기화는 두 가지뿐 —
// **단계별**(묶음 머리의 「N단계 초기화」 → 확인 줄의 「N단계 초기화」 · 「취소」) · **전체**(대시보드 맨 아래 「전체 초기화…」 — dashboard.js DASH_RESET_ALL: 이 워크플로우에서의 「작업 내용 초기화」 이름).
// 전의 준비 확인 줄 「모두 초기화(자료도)」 는 없앴다(「모두」 가 두 곳이었다 — 전체는 맨 아래 하나).
const FW_STAGE_RESET = { // head = 확인 줄 머리의 한 줄(「N단계 「이름」 초기화 — …」 뒤) · lose · keep = 노트 아이콘의 글
  open: { name: "준비", head: "올린 직후로 되돌립니다(「작성」 단계도 함께 비움 · 이 문서의 자료는 남김)",
    lose: "헤딩 · 표 분석 · 04에 첨부한 샘플·추가 서식 · LLM 검증·보완 · 작성 지침 저장본 · 양식 검토(찾을 테마 · 확인할 것의 답) · 작성 계획 · 받은 초안 · 문서에 반영한 글과 고친 문단", keep: "올린 원본 · 이 문서의 자료 · 확정 기록 · 작업 기록 · 문서 라이브러리의 문서와 추출" },
  material: { name: "자료 준비", head: "이 문서의 자료를 모두 비웁니다",
    lose: "이 문서로 가져온 자료(추출한 MD · 에이전트 보기에서 준 파일 · 글) · 자료 문서 올리기 · 자료 추출의 「끝남」(이 문서의 몫으로 다시 셉니다 — 있는 것을 쓰려면 「있는 문서 쓰기」 · 「있는 추출 쓰기」)", keep: "문서 라이브러리의 문서와 추출(그 서버의 것 — 다시 가져올 수 있습니다) · 분석 · 양식 검토 · 받은 초안 · 문서. 자료가 바뀌니 「작성 계획 세우기」 는 다시 해야 합니다" },
  write: { name: "작성", head: "초안 · 작성 계획을 비우고 문서를 올린 원본으로 되돌립니다",
    lose: "작성 계획 · 받은 초안(에이전트 대화 · 제안 카드) · 문서에 반영한 글과 그 밖에 고친 문단(확정한 것이 있으면 「올린 원본으로 복원」 확정을 하나 더합니다)", keep: "헤딩 · 표 분석 · 작성 지침 · 양식 검토(찾을 테마) · 확인할 것에 정한 답 · 이 문서의 자료" },
};
function fwStageNo(st) { // 그 묶음의 단계 번호 — 대시보드 묶음 머리의 번호와 같은 셈(dashboard.js dashModel: 등록부의 no · 없으면 차례) · 등록부를 아직 못 읽었으면 FW_STAGE_RESET 의 차례(글에 번호를 박지 않는다)
  const reg = typeof DASH === "object" && DASH.reg && (DASH.reg.tasks || []).find((t) => t.job === "form_write"), gs = (reg && reg.stages) || [], gi = gs.findIndex((g) => g.id === st);
  return gi >= 0 ? String(gs[gi].no || gi + 1) : String(Object.keys(FW_STAGE_RESET).indexOf(st) + 1);
}
const fwStageWord = (st) => { const no = fwStageNo(st); return /단계$/.test(no) ? no : `${no}단계`; }; // 「1단계」
const fwStageName = (st) => `${fwStageWord(st)} 「${FW_STAGE_RESET[st].name}」`; // 「1단계 「준비」」 — 확인 줄 · 풍선 · 토스트의 이름
function fwStageResetOff(A) { // 초기화를 누를 수 없는 까닭 | "" — 도는 일이 끝난 뒤에
  const run = typeof agwRunning === "function" ? agwRunning() : null;
  return !state.stored ? "작업 저장이 꺼진 문서는 초기화할 수 없습니다" : fwRunning() ? "초안을 받는 중입니다 — 멈추거나 끝난 뒤에 초기화하세요" : fwReviewing() ? "양식 검토가 도는 중입니다 — 끝난 뒤에 초기화하세요"
    : fwExtractingGuides() || FW.changingExamples ? "작성 지침과 첨부를 처리하는 중입니다" : A && A.busy ? "분석이 도는 중입니다 — 끝난 뒤에 초기화하세요" : run ? `「${run.label}」 이(가) 도는 중입니다 — 끝난 뒤에 초기화하세요` : state.commitBusy ? "확정 · 초기화하는 중입니다 — 끝난 뒤에 누르세요" : "";
}
function fwStageResetEl(st, off, mats) { // 묶음 머리 아래의 확인 줄(모달 아님 — 대시보드 맨 아래 초기화 상자와 같은 꼴): 머리 한 줄 + 노트 아이콘(비우는 것 · 남는 것) + 단추 둘(「N단계 초기화」 · 「취소」)뿐
  const T = FW_STAGE_RESET[st], label = fwStageName(st), box = el("div", "dash-reset"), head = el("p", "dash-reset-head", `${label} 초기화 — ${T.head}`), acts = el("div", "dash-reset-acts"), stop = off || (FW.rsBusy ? "초기화하는 중입니다" : "");
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", `${label} 초기화`);
  box.dataset.fwReset = st;
  head.append(hHelp("초기화하면 비우는 것 · 남는 것", `비우는 것 — ${T.lose}
남는 것 — ${T.keep}`, { rows: true, title: `${label} 초기화` }));
  box.append(head);
  if (st === "material" && !mats) box.append(el("p", "dash-text muted", "이 문서의 자료가 없습니다 — 비울 것이 없습니다"));
  if (st === "write" && state.edited && state.edited.size) box.append(el("p", "dash-text", `지금 고친 문단 ${state.edited.size}개가 올린 원본으로 돌아갑니다`));
  const go = (label, run, key, title, disabled = false) => { const b = dashBtn(label, run, { disabled: !!stop || disabled, title: stop || title, focus: `fwreset:${key}` }); b.classList.add("danger"); acts.append(b); };
  go(FW.rsBusy === st ? "초기화 중…" : `${fwStageWord(st)} 초기화`, () => fwStageReset(st), `${st}:go`, `${label} — ${T.head}`, st === "material" && !mats);
  acts.append(dashBtn("취소", () => { FW.rs = ""; dashDraw(true); }, { disabled: !!FW.rsBusy, title: "초기화하지 않고 닫습니다", focus: "fwreset:close" }));
  box.append(acts);
  return box;
}
async function fwStageReset(st) { // st = open(준비 — 자료만 남기고 올린 직후로) · material · write (전체 = 대시보드 맨 아래 「전체 초기화…」 — 여기를 지나지 않는다)
  if (FW.rsBusy || !state.id) return;
  const id = state.id, name = fwStageName(st), T = FW_STAGE_RESET[st];
  if (st === "open") { // 작업 내용 초기화와 같은 길(dashResetRun → workReset → 다시 열고 첫 분석: dashResetDone) — 자료만 남긴다(keep) · 글은 이 단계의 이름으로(say)
    FW.rs = "";
    return dashResetRun(dashResetState(), [{ id, label: name, name: state.name || "", opt: { keep: "materials" } }], { redraw: () => dashDraw(true), done: dashResetDone,
      say: { name: `${name} 초기화`, ok: () => `${name} 초기화 — ${T.head.replace("되돌립니다", "되돌렸습니다")}`, bad: (bad) => `초기화하지 못했습니다 — ${bad.join(" / ")}` } });
  }
  FW.rsBusy = st;
  dashDraw(true);
  try {
    if (st === "write") await flushAll(); // 치던 글을 먼저 보낸다(되돌린 뒤에 늦게 닿지 않게)
    const r = await api(`/api/docs/${id}/form-write/reset`, { method: "POST", headers: H_JSON, body: JSON.stringify({ stage: st }) });
    FW.rs = "";
    if (st === "write" && state.id === id) await load(id, { tab: $("panel").dataset.tool || "Dash" }); // 문서가 올린 원본으로 — 다시 연다(보던 탭에 머문다)
    toast(st === "material" ? `${name} 초기화 — 자료 ${r.materials}개를 비웠습니다` : `${name} 초기화 — 초안 ${r.turns}개${r.plan ? " · 작성 계획" : ""}을 비우고${r.reverted ? " 문서를 올린 원본으로 되돌렸습니다" : " 문서는 올린 원본 그대로입니다"}`);
  } catch (e) { toast(`${name} — 초기화하지 못했습니다: ${e.message}`, true); }
  FW.rsBusy = "";
  if (state.id === id) { FW.at = 0; FW.picks = new Set(); FW.mats = null; await fwRead(true); if (typeof agentLoad === "function") agentLoad(); fwRedraw(); }
  dashDraw(true);
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
  + "작성 지침 = 양식이 적어 둔 것(작성 요령 · ※ 안내 · 각주 항목)과 사람이 그 헤딩에 적은 것(문서의 「지침」 단추). 맨 위 「이번 작성의 지침」(사람의 요청)은 양식 검토와 이번 실행의 모든 자리에 함께 갑니다.\n"
  + "차례 = ① 「양식 검토」 — 목적 문서의 양식에 무엇을 써야 하는지 · 어떤 작성 지침이 있는지 · 사람이 요청한 것을 검토하고 자료에서 찾을 테마 · 키워드를 뽑습니다(자료는 읽지 않습니다) → ② 「작성 계획 세우기」(따로 선 단추) — 양식에 넣을 내용의 자료(MD)를 고르고 누르면 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획합니다(양식 검토의 결과는 그대로) → ③ 확인할 것(범위 · 기준 · 우선순위)에 답합니다(「자료대로」 = 따로 정하지 않음 · 자료에서 찾은 답 후보는 근거와 함께). 「작성 초안 받기」 는 ①②③ 이 끝나야 눌리고, 답과 계획이 자리마다의 요청에 함께 갑니다. 계획을 세운 자료와 다른 자료를 고르거나 검토 뒤에 고른 자리가 바뀌었으면 계획을 다시 세웁니다.\n"
  + "상자(1칸 표) 자리는 그 안의 쓸 자리(빈 줄 · 글머리 줄 · 같은 줄 뒤)를 골라 씁니다 — 같은 이름의 자리가 여럿이면 하나를 골라야 하고, 양식에 있던 글을 바꾸는 줄과 상자 안의 표 · 그림 자리는 쓰지 않습니다.\n"
  + "자료에 없는 내용은 만들지 않으며, 에이전트가 지은 글과 자료에 없는 수가 든 초안은 처음부터 고르지 않은 채로 보입니다.";
const FW_HELP_TOPICS = "양식 검토가 양식 전체를 읽고 뽑은 것입니다 — 이 양식을 쓰려면 자료 문서에서 무엇을 찾아야 하는지.\n"
  + "테마 = 찾을 내용의 이름 · 키워드 = 자료에서 그 내용을 부르는 표현(같은 뜻의 다른 말을 찾는 단서) · 맥락 = 어느 자리에 무엇이 어떤 꼴로 필요한가.\n"
  + "쓰는 법 = 「범위 앞에 붙일 말」 에 누구의 것인지(기관 · 연구 · 기간)를 적고, 찾을 테마를 골라 「고른 것 복사」 → 문서 라이브러리의 「뽑을 범위」 에 붙여 넣습니다(줄마다 범위 하나 = MD 하나 · 한 번에 8개까지 · 줄마다 600자까지).\n"
  + "「모두 선택」 = 복사할 수 있는 테마를 한 번에 고릅니다(8개를 넘으면 앞 8개만 · 다 골라져 있으면 「모두 해제」). 「모두 복사」 = 고른 것과 상관없이 복사할 수 있는 줄을 모두 복사합니다(8줄을 넘으면 나눠 붙여 넣습니다 · 600자를 넘는 줄은 뺍니다).\n"
  + "테마마다 기간이 다르면(당해연도 ↔ 다음 연도) 한꺼번에 복사하지 말고 앞에 붙일 말을 바꿔 나눠 복사하거나, 붙여 넣은 뒤 그 줄을 고칩니다. 아래 미리보기가 「고른 것 복사」 로 복사될 글 그대로입니다. 문서 라이브러리의 추출은 그 화면에서 시작합니다(여기서는 복사까지).";
async function fwWriteOpen(at = "") { // at = "topics" → 「자료에서 찾을 테마 · 키워드」 절로 굴린다(대시보드의 「테마 · 키워드 보기」) · "guides" → 「채울 자리」 로 굴리고 자리마다 지침을 펼친다(대시보드 「작성 지침 확인 · 적기」)
  fwClearWay();
  FW.guideMode = at === "guides";
  const { tools, body } = headsDlg("fwWrite", "지침 작성", "자리마다 작성 지침 + 자료 → 초안 · 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  const take = hBtn("자료 가져오기", () => fwTakeOpen(), { title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로" });
  take.dataset.fwTake = "1"; // 자료가 없으면 fwWriteDraw 가 파란 단추로(대시보드의 「지금」 = 자료 가져오기와 같은 단추)
  tools.append(take, hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("지침 작성 안내", FW_HELP_WRITE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await Promise.all([fwRead(true), typeof dashRegLoad === "function" ? dashRegLoad() : null]); // 등록부 = 절마다의 단계 번호(fwWhereEl — 대시보드와 같은 셈)
  fwWriteDraw();
  const to = body.querySelector({ topics: ".fw-topics", guides: ".fw-places-sec", review: ".fw-review-sec", plan: ".fw-plan-sec" }[at] || ":not(*)"); // review · plan = 대시보드 06 · 10 의 단추
  if (to) body.scrollTop = Math.max(0, to.offsetTop - body.offsetTop - 6);
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
  if (rv && fr.stale && FW.guidance?.ready) {
    return { state: going ? "run" : "now", text: going ? "바뀐 작성 지침으로 양식을 검토하고 있습니다" : "작성 지침이 바뀌었습니다. 현재 지침으로 양식을 다시 검토하세요.",
      acts: [dashBtn("다시 검토", () => fwWriteOpen("review"), { primary: !going, focus: "act:review" })] };
  }
  if (!rv) {
    const btn = [dashBtn("양식 검토", () => fwWriteOpen("review"), { primary: !going, title: "「지침 작성」 열의 「양식 검토」 — 목적 문서의 양식에 무엇을 써야 하는지 · 어떤 작성 지침이 있는지 · 사람의 요청을 검토하고 자료에서 찾을 테마 · 키워드를 뽑습니다(유료 LLM 한 번 · 자료는 읽지 않음 · 문서는 안 바뀜)", focus: "act:review" })];
    if (going) return { state: "run", text: "양식 · 작성 지침 · 사람의 요청을 읽는 중(1~3분)", acts: btn };
    return { state: "now", text: run && run.state === "failed" ? `검토 실패 — ${run.error || "까닭 모름"}` : "아직 검토하지 않았습니다 — 양식에 무엇을 써야 하는지 · 어떤 작성 지침이 있는지 · 사람의 요청을 보고 자료에서 찾을 테마를 뽑습니다(자료는 읽지 않습니다)", acts: btn };
  }
  const n = Object.keys(rv.places || {}).length;
  return { state: "done", text: `양식 검토 끝 — 자리 ${n}곳의 작성 방향 · ${topics ? `찾을 테마 ${topics.length}개` : "찾을 테마는 아직 뽑지 않았습니다(「다시 검토」 로 뽑습니다)"}${fr.stale ? " · 검토 뒤 양식이 바뀌었습니다" : ""}`,
    acts: [dashBtn("테마 · 키워드 보기", () => fwWriteOpen("topics"), { title: "「지침 작성」 열의 「자료에서 찾을 테마 · 키워드」 — 골라서 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사합니다", focus: "act:review" })] };
}
function fwPlanStep(gw) { // 대시보드 「작성 계획 · 확인할 것」 줄(작성 묶음의 처음) — 자료로 세운 작성 계획 → 확인할 것에 답
  const fr = FW.fr, rv = fr && fr.review, run = fr && fr.run, open = (fr && fr.open) || [];
  const planned = !!(fr && fr.planned), mats = ((FW.gw && FW.gw.materials) || []).length;
  if (gw.hwpx === false) return { state: "", text: "" };
  const btn = [dashBtn(!planned ? "작성 계획 세우기" : "계획 · 물음 보기", () => fwWriteOpen("plan"), { primary: !!rv && ((!planned && !!mats) || !!open.length), title: "「지침 작성」 열의 「작성 계획 · 확인할 것」 —양식에 넣을 내용의 자료(MD)를 고르고 자리마다 자료의 무엇을 쓸지 계획을 세우고, 확인할 것에 답합니다(유료 LLM · 문서는 안 바뀜)", focus: "act:plan" })];
  if (run && run.state === "running" && (run.materials || []).length) return { state: "run", text: "고른 자료를 읽고 작성 계획을 세우는 중(1~3분)", acts: btn }; // 양식 검토가 도는 것(자료 없음)은 이 줄의 일이 아니다
  if (!rv) return { state: "todo", text: "양식 검토 뒤에 세웁니다", acts: btn };
  const n = rv.questions.length, pl = Object.values(rv.places || {});
  if (!planned) return { state: mats ? "now" : "todo", text: mats ? "작성 계획 전 — 양식에 넣을 내용의 자료(MD)를 고르고 「작성 계획 세우기」 를 누릅니다" : "자료를 가져오면 계획을 세웁니다", acts: btn };
  return { state: open.length ? "now" : "done", text: `작성 계획 — 자료에서 쓸 자리 ${pl.filter((x) => x.use).length}곳 · 자료에 없는 것이 있는 자리 ${pl.filter((x) => x.gap).length}곳 · ${open.length ? `확인할 것 ${open.length}개가 남았습니다` : n ? `확인할 것 ${n}개 모두 답함` : "확인할 것이 없습니다"}`, acts: btn };
}
// kind = "review"(양식 검토 — 양식 · 작성 지침 · 사람의 요청만 · 자료는 안 보냄) | "plan"(작성 계획 — 고른 자료 · 양식 검토가 먼저). 한 단추가 두 걸음을 함께 돌리지 않는다
// (2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려 ... 목적문서의 양식에 뭘 작성해야하는지, 어떤 지침이 있는지 사용자가 요청하는건 뭔지를 봐야지」 — 전에는 자료를 고른 채 「양식 검토」 를 누르면 계획까지 했다).
async function fwReviewRun(kind = "review") {
  const plan = kind === "plan", materials = plan ? [...(FW.mats || [])] : [];
  if (plan && !(FW.fr && FW.fr.review)) return toast("먼저 「양식 검토」 를 하세요 — 작성 계획은 양식 검토 뒤에 세웁니다", true);
  if (plan && !materials.length) return toast("양식에 넣을 내용의 자료(MD)를 고르세요 — 작성 계획은 자료로 세웁니다", true);
  const what = plan ? `고른 자료 ${materials.length}개를 읽고 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획하고 확인할 것을 묻습니다(양식 검토의 결과는 그대로 둡니다)`
    : `목적 문서의 양식 · 작성 지침 · 사람의 요청(「이번 작성의 지침」${FW.note.trim() ? "" : " — 비어 있음"})을 읽고 무엇을 써야 하는지 검토합니다. 자료는 읽지 않습니다${fwPlanned() ? ". 세워 둔 작성 계획은 다시 세워야 합니다(답한 것은 남습니다)" : ""}`;
  if (!window.confirm(`유료 LLM 한 번(1~3분) — ${what}. 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/form-review`, { method: "POST", headers: H_JSON, body: JSON.stringify({ materials, note: FW.note }) });
    FW.fr = { ...(FW.fr || {}), run: got.run };
    toast(plan ? "작성 계획을 세웁니다 — 끝나면 확인할 것을 묻습니다" : "양식 검토를 시작했습니다");
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
const fwRunKind = (run) => run && ((run.materials || []).length ? "plan" : "review"); // 실행 하나가 양식 검토인가 작성 계획인가(보낸 자료가 있나)
function fwReviewEl() { // 「지침 작성」 열의 「양식 검토」 절(대시보드 06) — 양식 검토만: 무엇을 써야 하나 · 작성 지침 · 사람의 요청. 작성 계획 · 확인할 것은 아래 fwPlanEl(10)
  // 2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려 ... 목적문서의 양식에 뭘 작성해야하는지, 어떤 지침이 있는지 사용자가 요청하는건 뭔지를 봐야지」 — 전에는 한 절 · 한 단추가 06 · 10 을 함께 맡았다
  const fr = FW.fr || {}, rv = fr.review, run = fr.run, sec = el("section", "fw-doc fw-review fw-review-sec"), h = el("h3", "fw-places-head");
  const going = !!(run && run.state === "running" && fwRunKind(run) === "review");
  const actBtn = hBtn(going ? "검토 중…" : rv ? "다시 검토" : "양식 검토", () => fwReviewRun("review"), {
    cls: `btn sm fw-rev-act${rv ? "" : " primary"}${going ? " is-going" : ""}`, disabled: fwReviewing() || !fr.enabled,
    title: !fr.enabled ? "LLM 을 쓸 수 없습니다" : "목적 문서의 양식(헤딩 · 안내 글 · 표 · 상자 안의 자리)과 작성 지침, 위 「이번 작성의 지침」(사람의 요청)을 읽고 무엇을 써야 하는지 검토합니다 — 자료는 읽지 않습니다 · 유료 LLM 한 번 · 문서는 바뀌지 않습니다. 다시 해도 답한 것은 남습니다",
  });
  h.append(el("span", "fw-rev-title", "양식 검토"), actBtn);
  fwHead(h, [["run", "review"]]);
  sec.append(h);
  if (going) sec.append(el("div", "fw-muted fw-pad fw-rev-msg is-going", "양식 · 작성 지침 · 사람의 요청을 읽는 중입니다(1~3분)."));
  else if (run && run.state === "failed" && fwRunKind(run) === "review") sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-fail", `검토 실패 — ${run.error || "까닭 모름"}${rv ? "(앞 검토는 그대로입니다)" : ""}`));
  if (!rv) {
    if (!going) sec.append(el("div", "fw-muted fw-pad fw-rev-msg is-idle", "아직 검토하지 않았습니다 — 양식에 무엇을 써야 하는지 · 어떤 작성 지침이 있는지 · 사람의 요청이 무엇인지를 봅니다(자료는 읽지 않습니다)."));
    return sec;
  }
  if (fr.stale) sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-warn", "검토 뒤에 양식(자리 · 작성 지침)이 바뀌었습니다 — 바뀐 곳이 많으면 「다시 검토」 합니다(정한 것은 남습니다)."));
  const f = rv.fed; // 검토가 본 것(서버 form_review.fed — 옛 검토에는 없음)
  if (f) {
    const llmGuides = f.llmGuides || 0;
    const fed = el("div", "fw-muted fw-pad fw-rev-fed", `검토가 본 것 — 자리 ${f.places}곳 · 작성 지침 ${f.formGuides + f.userGuides + llmGuides}개(양식 ${f.formGuides}${llmGuides ? ` · LLM 보완 ${llmGuides}` : ""} · 사람 ${f.userGuides}) · 사람의 요청 ${f.request ? "있음" : "없음"}`);
    if (rv.request) fed.title = `검토에 넣은 사람의 요청:\n${rv.request}`;
    sec.append(fed);
  }
  const S = rv.sees || {}, sees = el("div", "fw-pad fw-sees");
  for (const [k, t] of [["write", "무엇을 써야 하나"], ["guides", "작성 지침"], ["asks", "사람의 요청"]]) {
    if (!S[k]) continue;
    const r = el("div", "fw-see"); r.dataset.see = k;
    r.append(el("b", null, t), el("span", null, S[k]));
    sees.append(r);
  }
  if (sees.childNodes.length) sec.append(sees);
  if (rv.summary) { const d = el("details", "fw-guides fw-pad fw-rev-sum"); d.open = !sees.childNodes.length; d.append(el("summary", null, "검토 요약 — 이 양식을 어떻게 쓰나"), el("div", "fw-guide", rv.summary)); sec.append(d); }
  return sec;
}
function fwPlanEl() { // 「작성 계획 · 확인할 것」 절(대시보드 10) — 고른 자료로 작성 계획(양식 검토가 먼저) → 확인할 것(물음마다 답) · 앞서 정한 것
  const fr = FW.fr || {}, rv = fr.review, run = fr.run, dec = fr.decided || [], sec = el("section", "fw-doc fw-review fw-plan-sec"), h = el("h3", "fw-places-head");
  const going = !!(run && run.state === "running" && fwRunKind(run) === "plan"), planned = !!fr.planned;
  const sr = (s) => el("span", "fw-sr", s);
  const steps = el("span", "fw-steps"); // 어디까지 했나 — 양식 검토 ✓ → 작성 계획 ✓ → 확인할 것 n/m
  const qn = rv ? (rv.questions || []).length : 0, on = (fr.open || []).length;
  const s1 = el("span", `fw-tag${rv ? " user" : ""}`, rv ? "양식 검토 ✓" : "양식 검토");
  const s2 = el("span", `fw-tag${planned ? " user" : ""}`, planned ? "작성 계획 ✓" : "작성 계획");
  const s3 = el("span", `fw-tag${planned && !on ? " user" : planned ? " warn" : ""}`, planned ? (qn ? `확인할 것 ${qn - on}/${qn}` : "확인할 것 없음") : "확인할 것");
  s1.dataset.step = "1"; s2.dataset.step = "2"; s3.dataset.step = "3";
  // 이 문서에 자료가 하나도 없으면 작성 계획은 아직 못 세운다 — 단추를 끄고 「자료 가져오기」 를 먼저 가리킨다(대시보드의 차례 「자료 가져오기」 → 「작성 계획 · 확인할 것」 과 맞춤 —
  // 2026-11-24 사용자 「자료 가져오기, 작성 계획 세우기 매칭이 안됨」: 자료가 0개인데 이 단추가 파란 단추 · 「양식에 넣을 내용의 자료(MD)를 고르고」 라 했다)
  const hasMats = !!((FW.gw && FW.gw.materials) || []).length, noMats = !!rv && !planned && !hasMats;
  if (!rv) s1.dataset.now = "1";
  else if (!planned && !noMats) s2.dataset.now = "1";
  steps.append(s1, s2, s3);
  const actBtn = hBtn(going ? "계획 세우는 중…" : !planned ? "작성 계획 세우기" : "다시 세우기", () => fwReviewRun("plan"), {
    cls: `btn sm fw-rev-act${rv && !planned && !noMats ? " primary" : ""}${going ? " is-going" : ""}`,
    disabled: fwReviewing() || !fr.enabled || !rv || !hasMats,
    title: !fr.enabled ? "LLM 을 쓸 수 없습니다" : !rv ? "먼저 위 「양식 검토」 를 하세요 — 작성 계획은 양식 검토 뒤에 세웁니다" : !hasMats ? "작성 계획은 자료로 세웁니다 — 먼저 위 「자료 가져오기」 로 이 문서의 자료를 가져오세요"
      : "고른 자료(MD)를 읽고 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획하고 확인할 것을 묻습니다 — 양식 검토의 결과는 그대로 둡니다 · 유료 LLM 한 번 · 문서는 바뀌지 않습니다. 다시 해도 답한 것은 남습니다",
  });
  h.append(el("span", "fw-rev-title", "작성 계획 · 확인할 것"), actBtn);
  fwHead(h, [["run", "plan"]]);
  h.append(steps);
  sec.append(h);
  if (going) sec.append(el("div", "fw-muted fw-pad fw-rev-msg is-going", "고른 자료를 읽고 작성 계획을 세우는 중입니다(1~3분)."));
  else if (run && run.state === "failed" && fwRunKind(run) === "plan") sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-fail", `작성 계획 실패 — ${run.error || "까닭 모름"}(앞 검토 · 계획은 그대로입니다)`));
  if (!rv) {
    if (!going) sec.append(el("div", "fw-muted fw-pad fw-rev-msg is-idle", "양식 검토 뒤에 고른 자료로 세웁니다."));
    return sec;
  }
  if (!planned && !going) sec.append(el("div", "fw-muted fw-pad fw-bad fw-rev-msg is-warn", noMats ? "양식만 검토했습니다 — 작성 계획은 자료로 세웁니다. 먼저 위 「자료 가져오기」 로 이 문서의 자료를 가져오세요(대시보드 「자료 가져오기」 → 「작성 계획 · 확인할 것」)."
    : "양식만 검토했습니다 — 양식에 넣을 내용의 자료(MD)를 고르고 「작성 계획 세우기」 를 누르세요."));
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
  sec.append(fwHead(h, [["result", "review"], ["prep", "extract"]]));
  if (!topics) { sec.append(el("div", "fw-muted fw-pad fw-top-msg", "아직 뽑지 않았습니다 — 「다시 검토」 로 뽑습니다")); return sec; } // 오늘 전에 저장한 검토(topics 없음) — 「0개」 가 아니다
  if (!topics.length) { sec.append(el("div", "fw-muted fw-pad fw-top-msg", "찾을 테마가 없습니다")); return sec; }
  for (const k of [...FW.topicOn]) if (!topics.some((t) => t.key === k)) FW.topicOn.delete(k);
  const lead = el("input", "fw-top-lead"), prev = el("div", "fw-top-prev"), names = new Map(((FW.gw && FW.gw.places) || []).map((p) => [p.id, p.text]));
  lead.type = "text"; lead.maxLength = 200; lead.value = FW.lead || ""; lead.placeholder = "범위 앞에 붙일 말(기관 · 연구 · 기간) — 예: 한국선급, 2차년도";
  lead.setAttribute("aria-label", "범위 앞에 붙일 말(기관 · 연구 · 기간)");
  const copyChosen = () => { const ls = chosen(); if (ls.length) fwCopy(ls.join("\n"), `범위 ${ls.length}줄을 복사했습니다 — 문서 라이브러리의 「뽑을 범위」 에 붙여 넣으세요`); };
  const copyAll = hBtn("고른 것 복사", copyChosen, { cls: "btn sm primary fw-top-copy" });
  const copyTop = hBtn("고른 것 복사", copyChosen, { cls: "btn sm primary fw-top-copy-top" }); // 목록 위의 같은 단추(2026-11-24 — 아래 것은 테마가 많으면 굴려야 보인다)
  const rows = [];
  const chosen = () => topics.map((t, i) => [t, fwTopicLine(i)]).filter(([t, line]) => FW.topicOn.has(t.key) && line && line.length <= FW_SCOPE_MAX).map(([, line]) => line);
  const able = () => topics.filter((t, i) => { const line = fwTopicLine(i); return line && line.length <= FW_SCOPE_MAX; }); // 복사할 수 있는 테마(줄이 비지 않고 한도 안)
  const wanted = () => able().slice(0, FW_SCOPES); // 「모두 선택」 이 고를 것 — 앞에서부터 그 서버가 한 번에 받는 수까지
  const allOn = () => { const w = wanted(); return !!w.length && w.every((t) => FW.topicOn.has(t.key)); };
  const pickAll = hBtn("모두 선택", () => { // 2026-11-24 사용자 "모두 선택하기가 있어야지" — 다 골라져 있으면 「모두 해제」
    if (allOn()) FW.topicOn.clear();
    else {
      const n = able().length, w = wanted();
      FW.topicOn.clear();
      for (const t of w) FW.topicOn.add(t.key);
      if (n > w.length) toast(`문서 라이브러리가 한 번에 ${FW_SCOPES}개까지 받습니다 — 복사할 수 있는 ${n}개 가운데 앞 ${w.length}개를 골랐습니다(나머지는 「모두 복사」 나 나눠 골라 복사)`);
    }
    sync();
  }, { cls: "btn sm fw-top-all" });
  const copyEvery = hBtn("모두 복사", () => { // 고른 것과 상관없이 복사할 수 있는 모든 줄
    const lines = topics.map((t, i) => fwTopicLine(i)), ok = lines.filter((l) => l && l.length <= FW_SCOPE_MAX), over = lines.filter((l) => l.length > FW_SCOPE_MAX).length;
    if (!ok.length) return;
    fwCopy(ok.join("\n"), `범위 ${ok.length}줄을 모두 복사했습니다 — 문서 라이브러리의 「뽑을 범위」 에 붙여 넣으세요`
      + (ok.length > FW_SCOPES ? ` · 문서 라이브러리는 한 번에 ${FW_SCOPES}줄까지 받습니다 — 나눠 붙여 넣으세요` : "")
      + (over ? ` · ${FW_SCOPE_MAX}자를 넘는 ${over}줄은 뺐습니다` : ""));
  }, { cls: "btn sm fw-top-copyall" });
  const sync = () => { // 고른 것 · 앞말이 바뀔 때 — 미리보기 · 단추 · 줄마다의 체크 · 넘침 표시만 고친다(목록을 다시 그리지 않는다: 쓰던 글 · 굴린 자리)
    const ls = chosen(), on = topics.filter((t) => FW.topicOn.has(t.key)).length, all = able().length, full = allOn();
    prev.replaceChildren(...(ls.length ? ls.map((l) => el("div", "fw-top-line", l)) : [el("div", "fw-top-line is-none", on ? "복사할 수 있는 줄이 없습니다" : "테마를 고르면 복사될 줄이 여기 보입니다")]));
    for (const b of [copyAll, copyTop]) {
      b.textContent = `고른 것 복사${ls.length ? ` (${ls.length})` : ""}`;
      b.disabled = !ls.length;
      b.title = ls.length ? `미리보기의 ${ls.length}줄을 복사합니다 — 문서 라이브러리의 「뽑을 범위」 에 붙여 넣으면 줄마다 범위 하나(= MD 하나)가 됩니다` : "테마를 고르세요";
    }
    pickAll.textContent = full ? "모두 해제" : "모두 선택";
    pickAll.disabled = !all && !on;
    pickAll.title = full ? "고른 테마를 모두 풉니다" : !all ? (on ? "복사할 수 있는 줄이 없습니다 — 누르면 고른 것을 풉니다" : "복사할 수 있는 줄이 없습니다")
      : all > FW_SCOPES ? `복사할 수 있는 테마 ${all}개 가운데 앞 ${FW_SCOPES}개를 고릅니다 — 문서 라이브러리가 한 번에 ${FW_SCOPES}개까지 받습니다` : `복사할 수 있는 테마 ${all}개를 모두 고릅니다`;
    copyEvery.textContent = `모두 복사${all ? ` (${all})` : ""}`;
    copyEvery.disabled = !all;
    copyEvery.title = !all ? "복사할 수 있는 줄이 없습니다" : `고른 것과 상관없이 복사할 수 있는 ${all}줄을 모두 복사합니다` + (all > FW_SCOPES ? ` — 문서 라이브러리는 한 번에 ${FW_SCOPES}줄까지 받으니 나눠 붙여 넣습니다` : "");
    rows.forEach(([row, i, cb]) => { row.classList.toggle("is-long", fwTopicLine(i).length > FW_SCOPE_MAX); cb.checked = FW.topicOn.has(topics[i].key); });
  };
  lead.addEventListener("input", () => { FW.lead = lead.value; sync(); });
  const leadRow = el("div", "fw-pad fw-top-leadrow"); leadRow.append(lead);
  const bar = el("div", "fw-pad fw-top-bar"); bar.append(pickAll, copyTop, copyEvery);
  sec.append(leadRow, bar);
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
    rows.push([row, i, cb]);
    sec.append(row);
  });
  const act = el("div", "fw-pad fw-top-acts");
  act.append(copyAll, hBtn("문서 라이브러리 열기", () => fwLibOpen(), { cls: "btn sm", disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다(복사한 줄을 「뽑을 범위」 에 붙여 넣습니다)" : FW_LIB_DOWN }));
  const prevBox = el("div", "fw-pad"); prevBox.append(prev);
  sec.append(prevBox, act);
  sync();
  return sec;
}
function fwRedraw() { fwTakeDraw(); fwWriteDraw(); fwOvSync(); } // fwOvSync = 패널 「작업 개요」(열려 있을 때만)
function fwShown() { const ps = (FW.gw && FW.gw.places) || []; return FW.onlyGuided ? ps.filter((p) => p.n || FW.picks.has(p.id)) : ps; }
// ---- 절마다 「어느 단계의 결과 · 준비인가」(2026-11-24 사용자 「여기서 어떤 것의 결과다. 준비다 이런게 있어야 하는데 구분이 되질 않잖아」 — spec_양식작성 ② §6 「절의 단계 꼬리표」) ----
// 한 열에 여러 단계의 것이 함께 선다: 결과 = 그 단계가 만든 것 · 준비 = 그 단계를 돌리기 전에 여기서 고르고 적는 것 · 실행 = 그 단계를 이 절의 단추로 돌린다.
// 번호와 이름은 대시보드와 같은 셈(등록부 차례 · 고친 도구 이름 — dashboard.js dashModel) — 화면 글에 번호를 박지 않는다(단계가 늘면 어긋난다). 등록부를 못 읽었으면 꼬리표를 그리지 않는다.
const FW_WHERE = { result: "결과", prep: "준비", run: "실행" };
function fwStepNo(key) { // 대시보드 순서 번호 { no: "03", name } | null — 번호는 등록부 차례에서 센다(글에 박지 않는다)
  const reg = typeof DASH === "object" && DASH.reg && (DASH.reg.tasks || []).find((t) => t.job === "form_write");
  let i = 0;
  if (reg) for (const g of reg.stages) for (const s of g.steps) { i += 1; if (s.key === key) return { no: String(i).padStart(2, "0"), name: s.name }; }
  return null;
}
function fwStepRef(key) { const s = fwStepNo(key); return s ? `${s.no} ${s.name}` : ""; } // "05 양식 검토 · 찾을 테마" | ""
// 「채울 자리」 줄의 꼬리표 — 뜻과 어느 단계에서 나오나(등록부 줄 key → 대시보드 순서 번호).
// 2026-11-24 사용자 "채움, 쓸 자리, 지침 의미를 아래에 적어 주고 어디서 추출되었는디 번호를 넣어줘, 순서 번호가 있잖아" — 꼬리표 끝에 번호 · 절 아래에 범례(그 목록에 보이는 꼬리표만).
// 근거: guide_write.places(자리 · slot · boxed · 지침 n — 헤딩 그래프 · form_slots · 저장한 작성 지침) · 사람 지침 = place_guides_api(05) · 초안 = guide_write_api 실행(11).
const FW_TAGS = {
  table:  { word: "표", cls: "", step: "heads", say: "작성 지침이 붙은 표 — 표 채우기로 씁니다" },
  box:    { word: "상자", cls: "", step: "heads", say: "본문의 1칸 표(상자) 안에 쓸 줄이 있는 자리" },
  chunks: { word: "쓸 자리 n", cls: "guide", step: "heads", say: "상자 안에서 글을 쓸 덩이(머리 줄 + 그 아래 줄)의 수 — 「쓸 자리 고르기」 에서 고릅니다" },
  label:  { word: "같은 줄 뒤에 씀", cls: "guide", step: "heads", say: "「이름 :」 처럼 그 줄 뒤에 값을 이어 쓰는 줄" },
  check:  { word: "표시 줄", cls: "guide", step: "heads", say: "□ 선택지 가운데 맞는 것에 표시하는 줄" },
  filled: { word: "채움", cls: "user", step: "heads", say: "올린 양식에서는 쓸 자리였고 지금은 값이 든 줄 — 다시 쓰지 않습니다(고치려면 문서에서 직접)" },
  boxed:  { word: "아래 상자는 따로", cls: "", step: "heads", say: "이 헤딩 아래의 쓸 자리는 상자 안에 있습니다 — 그 상자 줄을 고릅니다" },
  guides: { word: "지침 n", cls: "guide", step: "heads", say: "이 자리에 붙은 작성 지침의 수(양식의 작성 요령 · 참고 · ※ 안내 · 각주) — 「작성 지침 보기」 로 펼칩니다" },
  user:   { word: "사람 지침", cls: "user", step: "guides", say: "사람이 이 자리에 적은 작성 지침이 있음" },
  text:   { word: "글 있음", cls: "", step: "", say: "헤딩 아래에 이미 본문 글이 있음(지금 문서)" },
  draft:  { word: "초안 n", cls: "ok", step: "ask", say: "이 자리에 받은 초안의 수 · 받는 중 · 자료에 없음 같은 결과" },
};
function fwTagEl(key, text, cls, step) { // 꼬리표 하나 — 끝에 그 꼬리표가 나온 단계의 순서 번호(풍선 도움말 = 뜻 + 단계 이름)
  const d = FW_TAGS[key] || {}, s = fwStepNo(step === undefined ? d.step : step), t = el("span", `fw-tag ${cls === undefined ? d.cls || "" : cls}`.trim(), text);
  t.dataset.tag = key;
  if (s) t.dataset.no = s.no; // 번호는 CSS ::after 로(꼬리표 글 = textContent 는 그대로 — 화면 검사 · 다른 코드가 글로 견준다)
  t.title = [d.say, s ? `← ${s.no} ${s.name}` : ""].filter(Boolean).join("\n");
  return t;
}
function fwLegendEl(keys) { // 절 아래의 범례 — 보이는 꼬리표만 · 꼬리표 · 뜻 · 나온 단계(순서 번호 + 이름)
  const box = el("div", "fw-legend");
  for (const k of Object.keys(FW_TAGS)) {
    if (!keys.has(k)) continue;
    const d = FW_TAGS[k], s = fwStepNo(d.step), row = el("div", "fw-legend-row"), chip = el("span", `fw-tag ${d.cls}`.trim(), d.word);
    if (s) chip.dataset.no = s.no;
    row.append(chip, el("span", "fw-legend-say", d.say), el("span", "fw-legend-from", s ? `← ${s.no} ${s.name}` : "지금 문서"));
    box.append(row);
  }
  return box.childNodes.length ? box : null;
}
function fwWhereEl(parts) { // parts = [[결과|준비|실행 의 key, 등록부 줄 key], …] → 절 머리 아래 한 줄의 꼬리표들(없으면 null)
  const box = el("span", "fw-where");
  for (const [kind, key] of parts) {
    const ref = fwStepRef(key);
    if (!ref) continue;
    const t = el("span", `fw-where-tag is-${kind}`);
    t.dataset.where = `${kind}:${key}`;
    t.title = kind === "result" ? `대시보드 「${ref}」 단계가 만든 것` : kind === "prep" ? `대시보드 「${ref}」 단계를 돌리기 전에 여기서 고르고 적는 것` : `대시보드 「${ref}」 단계를 이 절의 단추로 돌립니다`;
    t.append(el("b", null, FW_WHERE[kind]), el("span", null, ref));
    box.append(t);
  }
  return box.childNodes.length ? box : null;
}
function fwHead(h3, parts) { const w = fwWhereEl(parts); if (w) h3.append(w); return h3; }
function fwWriteDraw() {
  if (heads.dlg !== "fwWrite") return;
  const body = $("headsDlgBody"), foot = $("headsDlgFoot"), gw = FW.gw;
  const keep = body.scrollTop, noteEl = body.querySelector(".fw-note");
  if (noteEl && document.activeElement === noteEl) return void fwFootDraw(foot); // 지침을 적는 동안에는 목록을 다시 그리지 않는다(쓰던 글 · 커서)
  if (document.activeElement && ["fw-q-input", "fw-top-lead", "fw-gnote"].some((c) => document.activeElement.classList.contains(c)) && body.contains(document.activeElement)) return void fwFootDraw(foot); // 물음의 답 · 범위 앞에 붙일 말 · 자리 지침을 적는 동안에도
  body.replaceChildren();
  if (!gw) return void body.append(el("div", "fw-empty", FW.err || "읽는 중…"));
  if (gw.hwpx === false) return void body.append(el("div", "fw-empty", "지침 작성은 hwpx 문서만 됩니다."));
  const takeBtn = document.querySelector("#headsDlg [data-fw-take]");
  if (takeBtn) takeBtn.classList.toggle("primary", !gw.materials.length);
  // 자료
  const matSec = el("section", "fw-doc"), matBox = el("div", "fw-mats");
  matSec.append(fwHead(el("h3", null, "양식에 넣을 내용의 자료 (MD)"), [["result", "take"], ["prep", "plan"]]));
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
  noteSec.append(fwHead(el("h3", null, "이번 작성의 지침 — 사람의 요청"), [["prep", "review"], ["prep", "ask"]]), note); // 양식 검토가 읽고(무엇을 요청했나) · 초안 요청에도 함께 간다
  // 자리
  const plSec = el("section", "fw-doc fw-places-sec"), head = el("h3", "fw-places-head"), only = el("label", "fw-mat"), onlyCb = el("input"), shown = fwShown();
  onlyCb.type = "checkbox"; onlyCb.checked = FW.onlyGuided;
  onlyCb.addEventListener("change", () => { FW.onlyGuided = onlyCb.checked; fwWriteDraw(); });
  only.append(onlyCb, el("span", null, "작성 지침이 있는 자리만"));
  const all = hBtn("모두 고르기", () => { for (const p of fwShown()) if (p.slot !== "filled" && !(p.kind === "head" && p.boxed && !p.slot)) FW.picks.add(p.id); fwWriteDraw(); }, { title: "보이는 자리를 모두 고릅니다(이미 채운 줄 · 쓸 자리가 아래 상자에 있는 헤딩은 빼고)" }), none = hBtn("모두 해제", () => { FW.picks.clear(); fwWriteDraw(); });
  head.append(el("span", null, `채울 자리 — ${shown.length}곳`), only, all, none);
  plSec.append(fwHead(head, [["run", "guides"], ["prep", "ask"]]));
  if (FW.guideMode) { // 대시보드 「작성 지침 확인 · 적기」 로 왔다 — 이 절에서 하는 일을 한 줄로(그 밖의 절은 다른 단계의 것)
    const tip = el("div", "fw-pad fw-gmode");
    tip.append(el("span", null, "자리마다 「작성 지침」 을 펼쳤습니다 — 양식의 지침을 보고, 없거나 모자란 헤딩에는 그 자리의 칸에 적습니다. 표의 지침은 문서에서 그 표의 「지침」 단추로 적습니다."),
      hBtn("지침 접기", () => { FW.guideMode = false; fwWriteDraw(); }, { cls: "btn sm" }));
    plSec.append(tip);
  }
  if (!shown.length) plSec.append(el("div", "fw-empty", gw.places.length ? "작성 지침이 붙은 자리가 없습니다 — 「작성 지침이 있는 자리만」 을 끄면 모든 헤딩이 보입니다. 헤딩에 지침을 적으려면 문서에서 그 헤딩의 「지침」 단추를 씁니다." : "본문 헤딩이 없습니다 — 헤딩 추출(기본 분석)이 끝났는지 확인하세요."));
  const ran = new Map(((gw.run && gw.run.items) || []).map((i) => [i.id, i]));
  for (const p of shown) plSec.append(fwPlaceEl(p, ran.get(p.id), foot));
  const legend = fwLegendEl(new Set([...plSec.querySelectorAll(".fw-place-main > .fw-tags > [data-tag]")].map((t) => t.dataset.tag))); // 보이는 꼬리표의 뜻 · 나온 단계
  if (legend) plSec.append(legend);
  body.append(...[noteSec, fwReviewEl(), fwTopicsEl(), matSec, fwPlanEl(), plSec].filter(Boolean)); // 대시보드 차례대로: 사람의 요청 → 06 양식 검토 · 찾을 테마 → 자료 → 10 작성 계획 · 확인할 것 → 채울 자리
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
  if (p.kind === "table") tags.append(fwTagEl("table", "표"));
  if (p.kind === "box") tags.append(fwTagEl("box", "상자"), fwTagEl("chunks", `쓸 자리 ${(p.chunks || []).length}`));
  if (p.slot === "label") tags.append(fwTagEl("label", "같은 줄 뒤에 씀"));
  if (p.slot === "check") tags.append(fwTagEl("check", "표시 줄"));
  if (p.slot === "filled") tags.append(fwTagEl("filled", "채움"));
  if (p.boxed) tags.append(fwTagEl("boxed", "아래 상자는 따로"));
  if (p.n) {
    const step = p.guides.some((g) => g.src === "llm") ? "headsLlm" : p.guides.some((g) => g.src !== "user") ? "heads" : "guides";
    tags.append(fwTagEl("guides", `지침 ${p.n}`, undefined, step));
  }
  if (p.user) tags.append(fwTagEl("user", "사람 지침"));
  if (p.filled) tags.append(fwTagEl("text", "글 있음"));
  if (item) { const [word, cls] = FW_ITEM[item.state] || [item.state, ""]; const t = fwTagEl("draft", item.state === "done" ? `초안 ${item.proposals}` : item.state === "none" ? FW_NONE[item.why] || word : word, cls); const why = item.error || item.note || item.reply || ""; if (why) t.title = `${why}\n${t.title}`; tags.append(t); }
  main.append(name, tags);
  if (p.kind === "box" && (p.chunks || []).length) main.append(fwChunksEl(p, foot));
  const how = FW.fr && FW.fr.review && (FW.fr.review.places || {})[p.id];
  // 자리 줄 안의 회색 글은 앞 단계의 결과다(작성 방향 = 양식 검토 · 쓸 것 · 없는 것 = 작성 계획) — 풍선 도움말에 그 단계를 밝힌다(절의 단계 꼬리표 · fwWhereEl)
  const from = (key) => { const ref = fwStepRef(key); return ref ? `「${ref}」 의 결과` : ""; };
  if (how && how.how) { const h = el("div", "fw-how", `작성 방향: ${how.how}`); h.title = [from("review"), how.needs ? `필요한 정보: ${how.needs}` : ""].filter(Boolean).join("\n"); main.append(h); }
  if (how && how.use) { const u = el("div", "fw-how fw-use", `자료에서 쓸 것: ${how.use}`); u.title = from("plan"); main.append(u); } // 작성 계획(자료를 주고 한 검토)
  if (how && how.gap) { const g = el("div", "fw-how fw-gap", `자료에 없는 것: ${how.gap}`); g.title = from("plan"); main.append(g); }
  const writable = p.kind === "head"; // 사람이 적는 지침은 헤딩 자리에만(place_guides_api PUT …/heads — 표는 「이 표」 지침)
  if (p.guides.length || (FW.guideMode && writable)) {
    const det = el("details", "fw-guides"), sum = el("summary", null, p.guides.length ? "작성 지침 보기" : "작성 지침 적기");
    det.open = !!FW.guideMode;
    det.append(sum);
    for (const g of p.guides) { const li = el("div", "fw-guide"); li.append(el("span", `fw-tag ${g.src === "user" ? "user" : "guide"}`, g.src === "user" ? "사람" : g.kind || "양식"), el("span", null, g.text)); det.append(li); }
    if (FW.guideMode && writable) det.append(fwGuideNoteEl(p));
    main.append(det);
  }
  row.append(cb, main);
  return row;
}
function fwGuideNoteEl(p) { // 헤딩 자리에 사람이 적는 지침 — 문서의 「지침」 단추와 같은 저장(place_guides_api PUT …/heads/{pid} · 작업 폴더 guides_user.json · 빈 글 = 지움)
  const box = el("div", "fw-gwrite"), ta = el("textarea", "fw-gnote"), mine = (p.guides.find((g) => g.src === "user") || {}).text || "";
  ta.rows = 2; ta.maxLength = 2000; ta.value = mine;
  ta.placeholder = "이 헤딩에 쓸 내용 · 분량 · 꼴 — 예: 기관별 역할을 개조식 3줄로, 금액은 천원 단위";
  ta.setAttribute("aria-label", `${p.text} 의 작성 지침`);
  const save = hBtn(mine ? "고쳐 저장" : "저장", async () => {
    const text = ta.value.trim();
    if (text === mine.trim()) return toast("바뀐 것이 없습니다");
    try {
      await api(`/api/docs/${state.id}/place-guides/heads/${encodeURIComponent(p.id)}`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ text }) });
      toast(text ? `「${p.text}」 의 작성 지침을 저장했습니다` : `「${p.text}」 에 적은 지침을 지웠습니다`);
    } catch (e) { return toast(e.message || String(e), true); }
    ta.blur();
    await fwRead(true); fwRedraw();
    if (typeof dashDraw === "function") dashDraw();
  }, { cls: "btn sm primary", title: "이 헤딩에 지침을 저장합니다 — 양식 검토 · 초안 작성이 이 자리의 지침으로 읽습니다(문서는 안 바뀜 · 비우고 저장하면 지움)" });
  box.append(ta, save);
  return box;
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
  // 꺼진 까닭은 차례대로 첫째 것 — 양식 검토(자료 없이 됨) → 자료 → 작성 계획 · 확인할 것 → 자리. 2026-11-25 사용자 「왜 작성 초안 받기 버튼이 활성화가 안되냐?」 — 까닭이 풍선에만 있어 못 봤다: 단추 앞에 글로도 보인다
  const why = !gw.enabled ? "LLM 을 쓸 수 없습니다" : !(FW.fr && FW.fr.review) ? fwReviewWhy() : !mats ? "양식에 넣을 내용의 자료(MD)를 고르세요(위 「자료 가져오기」)" : fwReviewWhy() || (!n ? "채울 자리를 고르세요" : n > most ? `한 번에 ${most}곳까지입니다` : "");
  if (run) {
    const got = run.items.reduce((s, i) => s + (i.proposals || 0), 0), why0 = fwRunWhy(run); // 초안 = LLM 이 쓴 글(제안 카드) — 문서에 넣는 것은 에이전트 보기의 카드에서
    foot.append(el("span", "fw-muted", `마지막 실행 — 초안 ${got}개${got ? " · 제안 카드에서 보기" : ""}${why0 ? ` · ${why0}` : ""}`));
    if (got && toolShown("Agent")) foot.append(hBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "받은 초안(제안 카드)을 보고 「문서에 반영」 을 누릅니다 — 양식에 글이 써지는 곳입니다" }));
  }
  foot.append(el("span", "fw-grow"));
  if (why) foot.append(el("span", "fw-muted", why));
  foot.append(hBtn(`작성 초안 받기${n ? ` (${n}곳)` : ""}`, () => fwRun(), { cls: "btn sm primary", disabled: !!why, title: why || `고른 자리 ${n}곳의 초안을 받습니다 — LLM 이 쓴 글이 제안 카드로 나옵니다(유료 LLM · 자리마다 호출 1번 이상 · 문서는 아직 바뀌지 않습니다)` }));
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
