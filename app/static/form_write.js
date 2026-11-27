// 워크플로우 「양식 작성」 의 화면(spec_양식작성 ② §6) — 대시보드의 단계 상태(formWriteLive) · 2열 「자료 가져오기」(fwTakeOpen — 문서 라이브러리 서버의 추출 MD 를 이 문서의 자료로) ·
// 2열 「지침 작성」(fwWriteOpen — 자리마다 작성 지침 + 자료 → 문서 에이전트의 초안(제안 카드): 문서는 제안 카드의 「문서에 반영」 을 눌러야 바뀐다).
// 2026-11-24 더함(사용자 「작성은 어디서 하는거야?」 · 「제안받는것도 뭔지 모르겠는데」 · 「여기서 작성 테마/키워드를 추출해줘」 — spec_양식작성 ② §5-2 · §5-3 · astra 협의): 화면 말 「초안」(단추 「작성 초안 받기」) ·
// 대시보드의 줄 둘(review 「문서 작성 요령 생성 · 찾을 테마」 — 자료 준비 앞 · plan 「작성 계획 · 확인할 것」) · 절 「자료에서 찾을 테마 · 키워드」(fwTopicsEl — 고른 것을 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사) ·
// 상자 자리의 「쓸 자리 고르기」(fwChunksEl — 같은 이름의 자리는 하나만: 실행 요청의 chunks).
// 문서 라이브러리 · 자료 추출은 **따로 선 서버**(doclib/ — 새 탭으로 연다)이고, 여기는 그 서버를 8114 의 끝점(/api/doclib)으로만 읽는다. 두 열은 어느 hwpx 문서에서나 열 수 있다(공통 도구 — 워크플로우에 묶지 않는다).
// 기대는 app.js 의 이름: api · el · $ · state · H_JSON · hBtn · hHelp(panel_help.js) · toast · headsDlg · heads · scrollToBlock · showTab · toolShown / dashboard.js: dashBtn · dashDraw / doc_agent.js: AGENT · agentLoad.
const FW = { key: "", at: 0, lib: null, gw: null, loading: null, err: "", picks: new Set(), mats: null, note: "", planNote: "", onlyGuided: null, poll: 0, seen: "", // onlyGuided null = 아직 안 정함(fwRead 가 자리 수로 처음 값을 정한다)
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
  if (FW.key !== fwKey()) Object.assign(FW, { key: fwKey(), at: 0, lib: null, gw: null, fg: null, fgAsked: false, fr: null, guidance: null, examples: [], changingExamples: false, err: "", picks: new Set(), pickBy: "", pickPlan: "", mats: null, note: "", noteSeeded: false, planNote: "", planNoteSeeded: false, seen: "", onlyGuided: null, chunks: {}, chunkOpen: new Set(), lead: "", topicOn: new Set(), rs: "", duo: undefined, cov: null, wide: new Set() });
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
      FW.gf = await api(`/api/docs/${state.id}/guide-fix`).catch(() => null); // 「지침 검토 · 수정」 — 서버 guide_fix_api: 검토 결과(계획) · 반영 기록 · 이 문서의 양식(spec_양식작성 ② §5-9)
      let cov = null;
      [FW.rt, FW.cl, cov] = await Promise.all([api(`/api/docs/${state.id}/merge-retidy`).catch(() => null), // 「반영한 뒤 서식 정리」(14) — 서버 merge_retidy_api: 넣은 줄 = 반영한 초안의 문단(spec_양식작성 ② §5-5)
        api(`/api/docs/${state.id}/form-cleanup`).catch(() => null),
        api(`/api/docs/${state.id}/guide-write/coverage`).catch(() => null)]); // 덮임 — 자리마다 어디까지 됐나(서버가 턴 기록에서 센다: spec_양식작성 ② §5-12 9)
      FW.cov = cov && cov.counts && Array.isArray(cov.rows) ? cov : null; // 못 읽었으면(옛 서버) 덮임 없이 — 대시보드는 전의 셈으로
      FW.sh = await api(`/api/docs/${state.id}/form-shapes`).catch(() => null); // 「이상한 서식 줄」(04) — 서버 form_shapes_api: 상자 안에서 레터가 안 찍히는 줄 · 레터를 글로 친 줄(spec_양식작성 ② §5-11) // 「작성 지침 · 샘플 지우기」(15) — 서버 merge_api …/form-cleanup(양식 작성이면 작성 샘플도: ② §5-6)
      if (key !== fwKey() || gen !== FW.gen) return FW;
      FW.guidance = guidance; FW.examples = examples.files || []; FW.examplesError = examples.error || "";
      Object.assign(FW, { lib, gw, fg: fg && fg.saved ? fg : FW.fg && FW.fg.saved ? FW.fg : fg, fr, at: Date.now(), err: "" }); // 저장본은 비지 않는다(keep 이 지우지 않음) — 저장(POST) 전에 떠난 읽기가 뒤늦게 와도 저장본을 빈 것으로 덮지 않는다
      if (!FW.noteSeeded) { FW.noteSeeded = true; if (!FW.note && fr && fr.review && fr.review.request) FW.note = fr.review.request; } // 「이번 작성의 지침」 은 화면 메모리뿐 — 다시 열면 양식 검토가 본 요청으로 처음 값을 채운다(한 번만)
      if (!FW.planNoteSeeded) { FW.planNoteSeeded = true; if (!FW.planNote && fr && fr.review && fr.review.planRequest) FW.planNote = fr.review.planRequest; } // 「작성 계획에 줄 요청」 도 같이 — 마지막 계획이 본 요청으로
      if (FW.mats === null) FW.mats = new Set(gw.materials.filter(fwMatOk).map((m) => m.id)); // 처음에는 쓸 수 있는 자료를 모두 고른다(이 프로젝트의 참조 문서가 아닌 문서의 자료는 빼고)
      else for (const id of [...FW.mats]) if (!gw.materials.some((m) => m.id === id && fwMatOk(m))) FW.mats.delete(id);
      // 「작성 지침이 있는 자리만」 의 처음 값 — 자리가 한 번에 돌릴 수 있는 수를 넘는 긴 양식에서만 켠다. 짧은 양식에서 켜 두면 지침이 붙은 한두 곳만 보여 나머지 헤딩을 못 고른다
      // (2026-11-24 사용자의 양식: 자리 6곳 가운데 표 하나만 보였다 — spec_양식작성 ② §6)
      if (FW.onlyGuided === null) FW.onlyGuided = (gw.places || []).length > ((gw.limits && gw.limits.places) || 40) && gw.places.some((p) => p.n);
      fwPickSeed();
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
  toast(`${file.name} — 목적 문서로 넣었습니다(문서 구조 분석을 겁니다). 앞 문서는 작업 리스트에 남습니다`);
}
async function fwRefUpload(files) {
  const ok = [], same = [], bad = [];
  for (const f of files) {
    if (!/\.(pdf|hwpx|hwp|docx|pptx|ppt)$/i.test(f.name)) { bad.push(`${f.name}(받지 않는 형식)`); continue; }
    toast(`${f.name} — 문서 라이브러리에 올리는 중…`);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api("/api/doclib/docs", { method: "POST", body: fd });
      (r.created ? ok : same).push(f.name);
      const did = r.doc && r.doc.id;
      if (did && fwRefs().only && !fwRefs().ids.has(did)) await fwRefSet(did, true, f.name, true); // 여기서 올린 문서는 이 프로젝트의 참조 문서로 넣는다(이미 라이브러리에 있던 문서도)
    }
    catch (e) {
      if (e.status === 404 && e.message === "Not Found") { bad.push(`${f.name}(8114 서버가 옛 판입니다 — 서버를 다시 켠 뒤에 됩니다 · 그때까지는 「문서 라이브러리 열기」 로)`); break; } // 끝점이 없는 옛 서버
      bad.push(`${f.name}(${e.message})`);
    }
  }
  if (same.length && !ok.length && !fwRefs().only && fwMark("keep") !== "done") await fwStepMark("keep", "done"); // 이미 라이브러리에 있던 문서 — 올린 때가 그 문서의 처음 때라 「이 문서의 몫」 으로 안 세어진다: 「있는 문서 쓰기」 와 같게 둔다
  const say = [ok.length ? `참조 문서 ${ok.length}개를 올렸습니다${fwRefs().only ? "(이 프로젝트의 참조 문서로 넣음)" : ""}` : "", same.length ? `이미 라이브러리에 있는 문서 ${same.length}개(${fwRefs().only ? "이 프로젝트에 넣었습니다" : "그것을 씁니다"})` : "", bad.length ? `못 올림: ${bad.join(" · ")}` : ""].filter(Boolean).join(" · ");
  toast(`${say}${ok.length || same.length ? " — 자료 추출은 2단계 「자료 추출(MD)」 에서" : ""}`, !!bad.length);
  await fwRead(true);
  fwRefsDraw(); // 2열 「참조 문서」 가 열려 있으면 그 목록도
  fwAutoRedraw(); // 대시보드 + 「작업 개요」(문서 카드의 「참조 문서 올리기…」 를 누른 화면도 다시 그린다)
}
const fwDoneExtracts = () => ((FW.lib && FW.lib.docs) || []).reduce((n, d) => n + d.extracts.length, 0);
// ---- 이 프로젝트의 참조 문서(spec_양식작성 ② §2-1 — 2026-11-26 사용자 「있는 추출할때 전부 참조할 수 있지만 사용자가 선택한 문서만 사용할 수 있게 해줘, 선택된.
//      이 프로젝트의 참고 문헌은 문서 라이브러리랑 탭이든 뭐든 구분이 되어야함」): 문서 라이브러리는 모두 보이고(탭 「문서 라이브러리」 — 보기 · 「이 프로젝트에 넣기」),
//      자료로 가져오고 쓰는 것은 고른 문서의 것만(탭 「이 프로젝트」). 저장 = 서버 프로젝트 기록(GET guide-write 의 refs · PUT …/refs) — 서버도 고르지 않은 문서의 자료를 409 로 막는다.
//      refs.only 가 거짓(프로젝트가 없는 문서)이면 전과 같이 라이브러리 전체를 쓴다(탭 없음).
const fwRefs = () => { const r = (FW.gw && FW.gw.refs) || {}; return { project: r.project || "", order: r.docs || [], ids: new Set(r.docs || []), only: !!r.only }; };
const fwRefIn = (did) => { const r = fwRefs(); return !r.only || r.ids.has(did); }; // 쓸 수 있는 문서인가
const fwMatOk = (m) => !m.outside; // 쓸 수 있는 자료인가(서버가 센 것 — 고르지 않은 문서에서 온 자료는 outside)
async function fwRefSet(did, on, name = "", quiet = false) { // 참조 문서 하나를 이 프로젝트에 넣거나 뺀다 → 다시 그림
  if (!state.id) return;
  const id = state.id;
  try {
    const r = await api(`/api/docs/${id}/refs`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ doc: did, on }) });
    if (state.id === id && FW.gw) FW.gw.refs = r.refs;
    if (!quiet) toast(on ? `「${name || did}」 — 이 프로젝트의 참조 문서로 넣었습니다` : `「${name || did}」 — 이 프로젝트에서 뺐습니다(라이브러리에는 남고, 이미 가져온 자료는 쓰지 않습니다)`);
  } catch (e) { toast(`참조 문서를 ${on ? "넣지" : "빼지"} 못했습니다: ${e.message}`, true); }
  if (quiet) return;
  await fwRead(true);
  fwRedraw();
  if (typeof dashDraw === "function") dashDraw();
}
function fwRefTabsEl(redraw) { // 「이 프로젝트 (n)」 | 「문서 라이브러리 (m)」 — 두 열(참조 문서 · 자료 가져오기)이 같은 탭 값(FW.refTab)을 쓴다
  const r = fwRefs(), all = ((FW.lib && FW.lib.docs) || []).length, inLib = ((FW.lib && FW.lib.docs) || []).filter((d) => r.ids.has(d.id)).length;
  if (FW.refTab !== "lib") FW.refTab = "project";
  const tabs = el("div", "fw-tabs fw-ref-tabs");
  tabs.setAttribute("role", "tablist");
  for (const [key, word, tip] of [["project", `이 프로젝트 (${inLib})`, `프로젝트 「${r.project}」 의 참조 문서 — 자료로 가져오고 쓰는 것은 여기 문서의 것만입니다`],
    ["lib", `문서 라이브러리 (${all})`, "문서 라이브러리(따로 선 서버)의 모든 문서 — 보기만 합니다. 쓰려면 「이 프로젝트에 넣기」"]]) {
    const b = hBtn(word, () => { if (FW.refTab === key) return; FW.refTab = key; redraw(); }, { cls: `fw-tab${key === FW.refTab ? " is-on" : ""}`, title: tip });
    b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(key === FW.refTab)); b.dataset.tab = key;
    tabs.append(b);
  }
  return tabs;
}
function fwRefBtn(d) { // 문서 라이브러리 탭의 「이 프로젝트에 넣기」 · 이 프로젝트 탭의 「빼기」
  const inP = fwRefs().ids.has(d.id);
  return hBtn(inP ? (FW.refTab === "lib" ? "넣음 · 빼기" : "빼기") : "이 프로젝트에 넣기", () => fwRefSet(d.id, !inP, d.name), { cls: `btn sm fw-ref-pick${inP ? "" : " primary"}`,
    title: inP ? "이 프로젝트의 참조 문서에서 뺍니다 — 라이브러리의 문서 · 추출은 그대로이고, 이 문서로 이미 가져온 자료는 「프로젝트 밖」 으로 남아 쓰지 않습니다" : "이 문서를 이 프로젝트의 참조 문서로 넣습니다 — 그 추출을 자료로 가져올 수 있게 됩니다" });
}
const FW_LIB_DOWN = "문서 라이브러리 서버가 꺼져 있습니다 — tools/start_doclib.ps1 로 띄웁니다(자료 추출 · 「자료 가져오기」 를 할 수 없습니다)";

// 「1 준비」 의 「문서 구조 분석 및 작성 지침 추출」 · 「에이전트 기반 문서 구조 및 작성 지침 보완」 줄(2026-11-27 사용자가 고친 이름 — 전의 「헤딩 · 표 분석 · 작성 지침」 · 「LLM 검증·보완」 · 2026-11-24 사용자 "여기 문서의 헤딩이랑 테이블 분석하는 단계가 없네 1준비에 있어야지." · "이걸 하면서,,, 테이블이나 본문이 지침을 가지고 와야지").
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
function fwHeadsStep(A) { // 「문서 구조 분석 및 작성 지침 추출」 줄의 상태
  const fg = FW.fg && FW.fg.saved, c = (fg && fg.counts) || null;
  const guideBtn = c && typeof formGuidesList === "function" ? [dashBtn("작성 지침", () => formGuidesList({ id: state.id, name: state.name }), { title: "저장한 작성 지침(작성 요령 표 · <참고 N> 자료 · ※ 안내 · 각주 번호의 항목)을 헤딩별 · 표별로 문서 옆 열에 보입니다", focus: "act:heads:guides" })] : [];
  const headsBtn = toolShown("Heads") ? [dashBtn("헤딩 추출 열기", () => showTab("Heads"), { title: "헤딩 그래프 · 표 구조 결과를 봅니다", focus: "act:heads:open" })] : [];
  // 글은 이관의 「헤딩 · 표 분석」 줄과 같은 꼴(app.js taskSteps heads · workflow_units._heads — 2026-11-25 사용자 "연차보고서 이관 보고 스크립트 동작방식으로 표기해줘")
  const HG = "헤딩 그래프·표 구조: 양식";
  if (!A.view) return { state: "todo", text: "분석 결과를 읽는 중…" };
  if (!A.hwpx) return { state: "", text: "문서 구조 분석은 hwpx 문서만 됩니다" };
  if (A.busy) return { state: "run", text: `${HG} 없음 · 양식 분석 중… — 끝나면 작성 지침을 모아 저장합니다`, acts: headsBtn };
  if (!A.base) return { state: "now", text: `${HG} 없음` + (A.bad ? ` · 양식 분석 실패 — ${[A.heads, A.tables].map((i) => i && i.error).filter(Boolean)[0] || "까닭 모름"}` : ""),
    acts: [dashBtn("분석", () => { Promise.resolve(headsFirst()).finally(() => typeof docStatusPing === "function" && docStatusPing()); toast("문서 구조 분석을 겁니다(스크립트) — 진행은 이 줄과 문서 이름 줄에 보입니다"); }, { primary: true, title: "헤딩 그래프·표 구조를 스크립트로 분석합니다 — LLM 호출 없음 · 문서는 바뀌지 않습니다(이 단계만 — 에이전트 기반 보완은 다음 줄)", focus: "act:heads" }), ...headsBtn] };
  // 지침 수 = 지침(items)만 — 각주 번호는 괄호 안에 따로(공통 상세 form_guides.js 「지침 n개 · 각주 번호 a/b」 · 이관의 「작성 지침 n개 저장」 과 같은 셈: 전에는 지침 + 각주 번호를 더해 3개가 「5개」 로 보였다 — 2026-11-25 r202)
  const tail = c ? `작성 지침 ${c.items || 0}개 저장(헤딩 ${c.headings} · 표 ${c.tables}${c.marks ? ` · 각주 번호 ${c.marksLinked || 0}/${c.marks}` : ""})` : FW.fg && FW.fg.error ? "작성 지침을 읽지 못했습니다" : "작성 지침을 모으는 중…";
  return { state: c ? "done" : "run", text: `${HG} 있음 · ${tail}${c && !(c.items || c.marks) ? "(양식에 적힌 지침이 없습니다 — 「작성 지침 확인 · 적기」 에서 적습니다)" : ""}`,
    acts: [...guideBtn, ...(c ? [dashBtn("다시 모으기", () => fwGuidesKeep(true).then(() => fwAutoRedraw()), { title: "지금 문서에서 작성 지침을 다시 모아 저장합니다(스크립트 · 문서는 안 바뀜) — 문서에서 지운 지침은 저장본에 남습니다", focus: "act:heads:keep" })] : []), ...headsBtn] };
}
// 선택 줄(「에이전트 기반 문서 구조 및 작성 지침 보완」 · 「작성 지침 확인 · 적기」)도 차례에 선다 — 2026-11-24 사용자 「전체 초기화를 했는데 1,2 번은 끝났다고 했는데 3,4번이 지나가지 않았는데 왜 5로 오냐 순서가 안맞음」:
// 전에는 선택 줄의 상태가 비어(「선택」) 「지금」 · 「다음: …」 이 05 로 건너뛰었다. 이제 앞 줄이 끝나면 선택 줄이 「지금」 이 되고, 하거나 「건너뛰기」 · 「확인함」 을 눌러야 지나간다
// (표시 = 작업 폴더 — PUT …/form-write/step: 작업 내용 초기화 · 준비 초기화가 함께 비운다 · spec_양식작성 ② §6 「선택 줄도 차례에」).
const fwMark = (key) => ((FW.gw && FW.gw.steps) || {})[key] || "";
function fwStepMark(key, mark, say) { // 표시를 남기거나(skip · done) 지운다(null) → 다시 그림
  if (!state.id) return;
  const id = state.id;
  return api(`/api/docs/${id}/form-write/step`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ key, mark }) })
    .then((r) => { if (state.id === id && FW.gw) FW.gw.steps = r.steps || {}; if (say) toast(say); })
    .catch((e) => toast(`표시를 남기지 못했습니다: ${e.message}`, true))
    .finally(() => fwAutoRedraw()); // 대시보드 + 「작업 개요」(그 줄의 단추를 누른 화면도 다시 그린다)
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
  const R = fwRefs();
  const ref = !o.lib.alive ? "문서 라이브러리 서버가 꺼져 있습니다 — tools/start_doclib.ps1 로 띄웁니다"
    : R.only ? (o.refN ? `이 프로젝트의 참조 문서 ${o.refN}개(라이브러리 전체 ${o.docs}개)` : o.docs ? `이 프로젝트의 참조 문서가 없습니다 — 「참조 문서 목록」 의 「문서 라이브러리」 탭에서 고르거나(라이브러리 ${o.docs}개) 「참조 문서 올리기…」` : "아직 없습니다 — 「참조 문서 올리기…」 로 올립니다(이 프로젝트의 참조 문서로 들어갑니다)")
    : o.keepOk ? (o.newDocs ? `이 문서의 몫 ${o.newDocs}개(라이브러리 전체 ${o.docs}개)` : `라이브러리에 있는 문서를 씁니다(${o.docs}개)`)
    : o.docs ? `라이브러리에 ${o.docs}개 — 이 문서의 몫은 아직 없습니다(「참조 문서 올리기…」 로 올리거나 2단계 「있는 문서 쓰기」)` : "아직 없습니다 — 「참조 문서 올리기…」 로 문서 라이브러리에 올립니다";
  // 접어도 보이는 줄(dashNodeEl 의 n.always) — 참조 문서 수 + 「참조 문서 목록」(문서 옆 2열: fwRefsOpen) · 2026-11-26 사용자 「참고 문서 갯수를 상단에 표기 … 참고문헌 리스트만 왼쪽열에서 볼수 있는 버튼」
  const cnt = el("span", "fw-ref-count", !o.lib.alive ? "참조 문서 — 서버 꺼짐" : R.only ? `이 프로젝트의 참조 문서 ${o.refN}개 · 라이브러리 ${o.docs}개` : `참조 문서 ${o.docs}개${o.newDocs ? ` · 이 문서의 몫 ${o.newDocs}` : ""}`);
  cnt.title = !o.lib.alive ? FW_LIB_DOWN : R.only ? "이 프로젝트에 고른 참조 문서의 수(자료로 쓰는 것은 이것만) · 문서 라이브러리 전체의 수(보기만)" : "문서 라이브러리에 있는 참조 문서(자료 문서)의 수 — 「이 문서의 몫」 = 이 작업을 만들거나 초기화한 뒤에 올린 것";
  const always = [cnt, dashBtn("참조 문서 목록", () => fwRefsOpen(), { title: "참조 문서 목록만 문서 옆 열에 보입니다(이름 · 형식 · 쪽 · 올린 때 · 자료 추출)", focus: "act:open:refs" })];
  return { state: state.id ? "done" : "now", text: "", always, lines: [
    ["목적 문서(채울 양식)", state.name || "—"],
    ["참조 문서(자료 문서)", `${ref}${o.mats ? ` · 이 문서의 자료 ${o.mats}개` : ""}`]],
    acts: [dashBtn("목적 문서 올리기…", () => fwPick(".hwp,.hwpx", false, (fs) => fwTargetUpload(fs[0])), { title: "채울 양식(hwp · hwpx)을 다른 파일로 바꿉니다 — 새 작업으로 올려 이 워크플로우에 넣고 그 문서를 엽니다(헤딩 · 표 분석을 바로 겁니다). 지금 문서는 묶음에서 나오고 작업 리스트에 남습니다", focus: "act:open:target" }),
      dashBtn("참조 문서 올리기…", () => fwPick(".pdf,.hwpx,.hwp,.docx,.pptx,.ppt", true, fwRefUpload), { primary: !!o.lib.alive && !(R.only ? o.refN : o.keepOk), disabled: !o.lib.alive, title: o.lib.alive ? "참조 문서(pdf · hwpx · hwp · docx · ppt · pptx — 여럿 가능)를 문서 라이브러리에 바로 올립니다(새 탭 없이) — 자료 추출은 2단계에서" : FW_LIB_DOWN, focus: "act:open:ref" }),
      ...(o.lib.alive ? [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { title: "올린 참조 문서를 보거나 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다", focus: "act:open:lib" })] : [])] };
}
// 2열 「참조 문서」 — 문서 라이브러리의 참조 문서 목록만(올리기 · 라이브러리 열기 · 새로 고침). 자료로 가져오기는 「자료 가져오기」 열의 일이다(여기는 보기만 · 문서는 안 바뀜).
async function fwRefsOpen() {
  fwClearWay();
  const { tools, body } = headsDlg("fwRefs", "참조 문서", fwRefs().only ? "이 프로젝트의 참조 문서(쓰는 것) · 문서 라이브러리(모든 문서 — 보기만) · 문서는 안 바뀜" : "문서 라이브러리(따로 선 서버)에 있는 자료 문서 · 문서는 안 바뀜");
  tools.append(hBtn("참조 문서 올리기…", () => fwPick(".pdf,.hwpx,.hwp,.docx,.pptx,.ppt", true, fwRefUpload), { cls: "btn sm primary", title: "참조 문서(pdf · hwpx · hwp · docx · ppt · pptx — 여럿 가능)를 문서 라이브러리에 바로 올립니다" }),
    hBtn("문서 라이브러리 열기", () => fwLibOpen(), { cls: "btn sm", title: "자료 추출을 하는 따로 선 서버 — 새 탭" }), hBtn("새로 고침", () => fwRead(true).then(fwRedraw), { cls: "btn sm" }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await fwRead(true);
  fwRefsDraw();
}
function fwRefsDraw() {
  if (heads.dlg !== "fwRefs") return;
  const body = $("headsDlgBody"), lib = FW.lib || { alive: false, docs: [] }, all = lib.docs || [], from = (FW.gw && FW.gw.libFrom) || 0, R = fwRefs();
  body.replaceChildren();
  if (!lib.alive) return body.append(el("p", "hwarn", lib.why || FW_LIB_DOWN));
  const sr = (s) => el("span", "fw-ref-sr", s);
  if (R.only) body.append(fwRefTabsEl(fwRefsDraw));
  const onP = R.only && FW.refTab !== "lib", docs = onP ? all.filter((d) => R.ids.has(d.id)) : all;
  const mine = R.only ? 0 : docs.filter((d) => (d.at || 0) > from).length;
  const head = el("p", "hnote fw-refs-head");
  head.append(el("strong", "fw-refs-total", onP ? `이 프로젝트의 참조 문서 ${docs.length}개` : R.only ? `문서 라이브러리 ${docs.length}개` : `참조 문서 ${docs.length}개`));
  if (R.only) head.append(el("span", "fw-refs-mine-note", onP ? " — 자료로 가져오고 쓰는 것은 이 문서들의 것만입니다" : " — 모든 문서(보기만) · 쓰려면 「이 프로젝트에 넣기」"));
  if (mine) {
    head.append(sr(" · "), el("span", "fw-refs-mine", `이 문서의 몫 ${mine}개`), el("span", "fw-refs-mine-note", "(이 작업을 만들거나 초기화한 뒤에 올린 것)"));
  }
  body.append(head);
  const gone = onP ? R.order.filter((id) => !all.some((d) => d.id === id)) : [];
  if (gone.length) { // 고른 뒤 라이브러리에서 지운 문서 — 빼기만
    const p = el("p", "hnote fw-ref-out", `라이브러리에 없는 문서 ${gone.length}개(지워졌습니다) `);
    p.append(hBtn("목록에서 빼기", async () => { for (const id of gone) await fwRefSet(id, false, id, true); await fwRead(true); fwRedraw(); if (typeof dashDraw === "function") dashDraw(); }, { cls: "btn sm" }));
    body.append(p);
  }
  if (!docs.length) return body.append(el("p", "hnote fw-refs-empty", onP ? (all.length ? "아직 고른 문서가 없습니다 — 「문서 라이브러리」 탭에서 「이 프로젝트에 넣기」 를 누르거나 「참조 문서 올리기…」 로 올립니다" : "아직 없습니다 — 「참조 문서 올리기…」 로 올립니다(이 프로젝트의 참조 문서로 들어갑니다)") : "아직 없습니다 — 「참조 문서 올리기…」 로 올립니다"));
  const ul = el("ul", "fw-refs");
  for (const d of docs) {
    const isMine = R.only ? R.ids.has(d.id) && !onP : (d.at || 0) > from;
    const li = el("li", "fw-ref" + (isMine ? " is-mine" : ""));
    const extText = String(d.ext || "").toUpperCase();
    const ext = el("span", "fw-ref-ext", extText);
    ext.dataset.ext = extText.replace(/^\./, "").toLowerCase();
    if (extText) ext.append(sr(" "));
    const top = el("div", "fw-ref-top"), name = el("strong", "fw-ref-name", d.name || d.id);
    name.title = d.name || d.id || "";
    top.append(name, sr(" "));
    const x = (d.extracts || []).length;
    const meta = el("div", "fw-ref-meta");
    meta.append(el("span", `fw-ref-status ${x ? "is-done" : "is-none"}`, x ? `추출 ${x}개` : "추출 전"));
    if (d.running) meta.append(sr(" · "), el("span", "fw-ref-status is-run", `추출 중 ${d.running}`));
    if (isMine) meta.append(sr(" · "), el("span", "fw-tag ok", R.only ? "이 프로젝트" : "이 문서의 몫"));
    const specs = [d.pages ? `${d.pages}쪽` : "", d.bytes ? `${Math.max(1, Math.round(d.bytes / 1024)).toLocaleString()} KB` : ""].filter(Boolean);
    const when = d.at ? `올림 ${new Date(d.at * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "";
    if (specs.length || when) {
      const facts = el("span", "fw-ref-facts");
      facts.append(sr(" · "));
      if (specs.length) {
        const specEl = el("span", "fw-ref-specs");
        specs.forEach((s, i) => {
          if (i) specEl.append(el("span", "fw-ref-sep", " · "));
          specEl.append(el("span", "fw-ref-fact", s));
        });
        facts.append(specEl);
      }
      if (when) {
        if (specs.length) facts.append(sr(" · "));
        facts.append(el("span", "fw-ref-when", when));
      }
      meta.append(facts);
    }
    const acts = el("div", "fw-ref-acts");
    acts.append(sr(" "), hBtn("보기", () => fwLibOpen(`d=${d.id}`), { cls: "btn sm fw-ref-view", title: "문서 라이브러리에서 이 문서를 봅니다(새 탭)" }));
    if (R.only) acts.append(fwRefBtn(d));
    li.append(ext, top, meta, acts);
    ul.append(li);
  }
  body.append(ul);
}
function fwLibStep(key, o) { // 06 「자료 문서 올리기」(keep) · 07 「자료 추출(MD)」(extract) — 이 문서의 몫으로 센다(o.fresh = 기준 시각 뒤의 것 · o.all = 라이브러리 전체)
  if (fwRefs().only) return fwRefStep(key, o);
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
function fwRefStep(key, o) { // 양식 작성(프로젝트가 있는 문서)의 07 · 08 — 끝남 = 이 프로젝트에 고른 참조 문서가 있음(keep) · 고른 문서에 끝난 추출이 있음(extract). 라이브러리 전체는 세지 않는다
  const isKeep = key === "keep", mine = isKeep ? o.refN : o.refDone, acts = [...o.libBtn(`act:${key}`)];
  acts.unshift(dashBtn(isKeep ? "참조 문서 고르기" : "참조 문서 목록", () => { FW.refTab = isKeep && !o.refN ? "lib" : "project"; fwRefsOpen(); },
    { primary: !mine && !!o.alive && (isKeep ? !!o.all : !!o.refN), disabled: !o.alive, title: o.alive ? "문서 옆 열 — 「이 프로젝트」 탭(자료로 쓰는 문서) · 「문서 라이브러리」 탭(모든 문서 — 「이 프로젝트에 넣기」 로 고름)" : FW_LIB_DOWN, focus: `act:${key}:refs` }));
  if (o.going && !isKeep) return { state: "run", text: `추출 중 ${o.going}개${o.refDone ? ` · 이 프로젝트의 끝난 추출 ${o.refDone}개` : ""}`, acts };
  if (mine) return { state: "done", text: isKeep ? `이 프로젝트의 참조 문서 ${o.refN}개${o.all > o.refN ? `(라이브러리 전체 ${o.all}개 — 고르지 않은 문서는 쓰지 않습니다)` : ""}` : `이 프로젝트의 참조 문서에서 끝난 추출 ${o.refDone}개${o.all > o.refDone ? `(라이브러리 전체 ${o.all}개 — 고르지 않은 문서의 추출은 쓰지 않습니다)` : ""}`, acts };
  const text = !o.alive ? FW_LIB_DOWN : isKeep ? (o.all ? `이 프로젝트에 고른 참조 문서가 없습니다 — 「참조 문서 고르기」 의 「문서 라이브러리」 탭에서 넣거나(라이브러리 ${o.all}개) 「참조 문서 올리기…」` : "아직 참조 문서가 없습니다 — 「참조 문서 올리기…」")
    : o.refN ? `이 프로젝트의 참조 문서 ${o.refN}개에 끝난 추출이 없습니다 — 문서 라이브러리에서 뽑을 범위를 적고 추출합니다` : "먼저 이 프로젝트의 참조 문서를 고릅니다";
  const state = o.mats ? (o.alive ? "ready" : "hold") : isKeep || o.prev ? "now" : "todo";
  return { state, ...(!o.alive && (state === "hold" || state === "now") ? { word: "서버 꺼짐" } : {}), text, acts };
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
  // 화면 말 「작성 지침 생성 기준」 — 2026-11-27 사용자 "판단이라고 하니 좀 연결이 안되서 이름을 뭘로 하는게 좋을까 carbon/ astra 랑 협의해봐" → astra · carbon 이 같이 고른 이름 → 같은 날 사용자 확정 "작성지침 생성기준이라고 하자"(개념으로는 메타 프롬프트 — spec_양식작성 ① 11-27 · ② §0).
  // 전의 「판단 지침」(같은 날 사용자 "판단지침 이라고 해줘야지") · 「추출 프롬프트」. 갈래 이름 「판단 지침」(/guides 의 탭 · merge_guides_default/*.md)은 그대로다 — 이 글은 그 갈래의 한 글(제목 = 이 이름)이다.
  const { tools, body } = headsDlg("fwCriteria", "작성 지침 생성 기준", "04 에이전트(「에이전트 기반 문서 구조 및 작성 지침 보완」)가 양식 · 샘플을 대조해 자리별 「작성 지침」 을 만들고 보완할 때 따르는 기준과 함께 받는 글입니다 — 작성 지침 자체가 아닙니다(지침 설정 › 판단 지침 에서도 봅니다).");
  const seq = heads.seq, epoch = state.epoch;
  const alive = () => heads.dlg === "fwCriteria" && heads.seq === seq && state.epoch === epoch;
  tools.append(hBtn("다시 읽기", fwCriteriaOpen, { title: "현재 설정된 작성 지침 생성 기준을 다시 읽습니다" }));
  body.append(el("p", "hnote lg-msg", "작성 지침 생성 기준을 읽고 있습니다…"));
  try {
    const agent = await api("/api/agents/writing_guidance");
    if (!alive()) return;
    const guide = agent.prompt.find((p) => p.kind === "merge" && p.name === "writing_guidance");
    const contract = agent.prompt.find((p) => p.kind === "contract");
    body.replaceChildren(guide?.text ? llmGuidePart({ ...guide, key: "guide", note: guide.custom ? "LLM 아이콘에서 저장한 작성 지침 생성 기준을 사용합니다." : "" })
      : el("p", "hnote lg-msg", "현재 설정된 작성 지침 생성 기준이 없습니다."));
    if (contract?.text) body.append(llmGuidePart({ ...contract, key: "contract", title: "입력과 판정 결과 작성 규칙" }));
    const themes = el("section", "fw-themes");
    body.append(themes);
    fwThemesDraw(themes, alive); // 04 가 함께 받는 미리 적어 둔 테마(테이블 타입 · 구분 기준 타입 · 템플릿)
  } catch (e) {
    if (alive()) body.replaceChildren(el("p", "hwarn lg-msg fail", `작성 지침 생성 기준을 읽지 못했습니다 — ${e.message}`));
  }
}
// ---- 이상한 서식 줄(spec_양식작성 ② §5-11 — 2026-11-27 사용자 「여기에 이상한 서식들을 삭제 제안하는 기능이 있어야 할거 같아. 레터가 없거나 이런건 서식을 수정해야 하고,」) ----
// 서버 form_shapes_api(스크립트만): 양식의 상자 안에서 레터가 안 찍히는 줄 · 레터를 글로 친 줄을 찾는다(문서는 그대로). 여기서 줄마다 「서식 수정」 · 「삭제」 · 「그대로」 를 고르고 고른 것만 반영한다(편집 하나 · 실행 취소 1).
// 처음부터 고른 것 = 서버의 pre(글을 쓴 줄 · 레터를 친 줄의 서식 수정) — 레터 없는 빈 줄(여백일 수 있다)과 삭제 제안은 사람이 고른다.
const FW_SHAPE_HELP = "양식의 상자 안에서 서식이 이웃 줄과 다른 줄을 스크립트가 찾은 목록입니다(문서는 그대로 — LLM 을 부르지 않습니다).\n"
  + "· 레터 없는 줄 = 앞뒤 줄은 한글이 레터(「○」 · 「-」)를 찍는데 이 줄만 레터가 안 찍히는 서식인 줄\n· 친 레터 줄 = 레터를 글로 친 줄(「    - 」 · 「  : 」)\n"
  + "· 서식 수정 = 그 줄을 「맞출 줄」 의 서식으로 바꿉니다(한글이 레터를 찍습니다 · 쓴 글은 그대로 · 친 레터는 지웁니다)\n· 삭제 = 그 줄을 지웁니다(글을 쓴 줄은 지우지 않습니다)\n· 그대로 = 건드리지 않습니다\n"
  + "처음에는 글을 쓴 줄과 레터를 친 줄의 「서식 수정」 만 골라 둡니다 — 레터 없는 빈 줄은 여백일 수 있어 직접 고릅니다. 반영하면 문서가 바뀌고 실행 취소 한 번으로 되돌립니다.\n"
  + "줄을 누르면 문서에서 그 줄로 갑니다. 양식 검토(06)보다 먼저 하세요 — 뒤에 하면 양식 검토를 다시 해야 합니다.";
const FW_SHAPE_DO = { restyle: "서식 수정", delete: "삭제" };
const FW_SHAPE_KIND = { bare: "레터 없는 줄", typed: "친 레터 줄" };
function fwShapeCountText(sh) {
  const c = (sh && sh.counts) || {};
  return `${c.total || 0}줄 — 서식 수정 제안 ${c.restyle || 0} · 삭제 제안 ${c.delete || 0}`;
}
function fwShapePicks() { // 줄마다 고른 일 {문단 id: "restyle" | "delete"} — 문서가 바뀌면(rev) 서버의 처음 값으로 다시
  const sh = FW.sh;
  if (!sh) return new Map();
  if (FW.shRev !== sh.rev || !FW.shPick) { FW.shRev = sh.rev; FW.shPick = new Map(sh.items.filter((it) => it.pre).map((it) => [it.id, it.propose])); }
  for (const id of [...FW.shPick.keys()]) if (!sh.items.some((it) => it.id === id)) FW.shPick.delete(id);
  return FW.shPick;
}
function fwShapesOpen() {
  fwClearWay();
  const { tools } = headsDlg("fwShapes", "이상한 서식 줄", "양식의 상자 안 — 줄마다 고르고 반영합니다");
  if (typeof hHelp === "function") $("headsDlgHelp").replaceChildren(hHelp("이상한 서식 줄이란", FW_SHAPE_HELP, { note: true }));
  tools.append(hBtn("다시 읽기", async () => { await fwRead(true); if (heads.dlg === "fwShapes") fwShapesDraw(); }, { title: "지금 문서에서 다시 찾습니다" }));
  fwShapesDraw();
}
function fwShapesDraw() {
  if (heads.dlg !== "fwShapes") return;
  const body = $("headsDlgBody"), foot = $("headsDlgFoot"), sh = FW.sh, keep = body.scrollTop;
  body.textContent = ""; foot.textContent = "";
  if (!sh) { body.append(el("p", "hnote lg-msg", "목록을 읽지 못했습니다 — 「다시 읽기」")); return; }
  if (!sh.items.length) { body.append(el("p", "hnote lg-msg", "양식의 상자 안에서 이상한 서식의 줄을 찾지 못했습니다.")); return; }
  const picks = fwShapePicks(), busy = !!FW.shaping;
  body.append(el("p", "fw-muted fw-pad fw-shape-sum", fwShapeCountText(sh)));
  for (const it of sh.items) {
    const row = el("div", "fw-top fw-shape"), main = el("div", "fw-top-main"), head = el("div", "fw-top-head");
    row.dataset.para = it.id;
    const name = el("button", "fw-place-name", it.raw.trim() ? `「${it.raw}」` : "(빈 줄)");
    name.type = "button";
    name.title = "문서에서 이 줄로";
    name.addEventListener("click", () => scrollToBlock(it.id, false));
    head.append(name, fwThemeTag(FW_SHAPE_KIND[it.kind] || it.kind, it.kind === "bare" ? "warn" : ""), ...(it.filled ? [fwThemeTag("글을 쓴 줄", "ok", "초안을 반영해 글이 든 줄 — 지우지 않습니다")] : []));
    const sel = el("select", "fw-shape-do");
    for (const [v, t] of [["", "그대로"], ...it.options.map((o) => [o, o === "restyle" ? `서식 수정 — 「${it.likeNum || ""}」 줄처럼` : FW_SHAPE_DO[o]])]) { const o = el("option", "", t); o.value = v; sel.append(o); }
    sel.value = picks.get(it.id) || "";
    sel.disabled = busy;
    sel.setAttribute("aria-label", "이 줄에 할 일");
    sel.addEventListener("change", () => { if (sel.value) picks.set(it.id, sel.value); else picks.delete(it.id); fwShapesDraw(); });
    const where = el("div", "fw-muted", `「${it.head}」 아래 · 지금 서식 「${it.style || "?"}」${it.like ? ` → 맞출 줄의 서식 「${it.likeStyle || "?"}」(레터 「${it.likeNum || ""}」)` : " · 맞출 줄 없음"}${it.propose === "delete" ? " · 삭제 제안" : ""}`);
    where.append(hHelp("이 줄을 찾은 까닭", it.why + (it.text != null && it.raw.trim() !== it.text ? `\n서식 수정 뒤의 글: 「${it.text}」(친 레터를 지움)` : ""), { note: true }));
    main.append(head, where);
    row.append(main, sel);
    if (picks.get(it.id)) row.classList.add("is-picked");
    body.append(row);
  }
  body.scrollTop = keep;
  const n = picks.size, dels = [...picks.values()].filter((v) => v === "delete").length;
  const go = hBtn(busy ? "반영하는 중…" : `고른 ${n}줄 반영`, fwShapesApply, { disabled: busy || !n, cls: "btn sm primary", title: n ? `서식 수정 ${n - dels}줄 · 삭제 ${dels}줄 — 문서가 바뀝니다(실행 취소 한 번)` : "줄마다 할 일을 고르세요" });
  foot.append(el("span", "muted", n ? `서식 수정 ${n - dels} · 삭제 ${dels}` : "고른 줄이 없습니다"), go);
}
async function fwShapesApply() {
  const sh = FW.sh, picks = fwShapePicks();
  if (FW.shaping || !sh || !picks.size || !state.id) return;
  FW.shaping = true;
  fwShapesDraw();
  let why = "";
  try {
    structOp.lastError = null;
    const body = { expectRev: sh.rev, picks: Object.fromEntries([...picks].map(([id, d]) => [id, { do: d, sig: (sh.items.find((it) => it.id === id) || {}).sig }])) };
    const r = await structOp("form-shapes", body);
    if (!r) why = (structOp.lastError && structOp.lastError.message) || "반영하지 못했습니다";
    else { const d = r.done || {}; toast(`이상한 서식 줄 — 서식 수정 ${(d.restyled || []).length}줄 · 삭제 ${(d.deleted || []).length}줄${(d.skipped || []).length ? ` · 건너뜀 ${d.skipped.length}줄(그 사이 바뀐 줄)` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`); }
  } finally { FW.shaping = false; }
  if (why) toast(`이상한 서식 줄 — ${why}`, true);
  await fwRead(true);
  fwShapesDraw();
  fwAutoRedraw();
}
// ---- 미리 적어 둔 테마(spec_양식작성 ② §5-7 — 2026-11-26 사용자 「테이블 타입 및 작성방법 을 저장하고 관리 … 구분기준 타입 도 … 템플릿도 사전에 정의 … yaml 파일로 관리하면 어떨까? 테마마다」) ----
// 테마마다 YAML 하나(서버 app/form_themes.py — 기본본 + 이 PC 의 사본 · LLM 이 새로 정의한 항목은 사본의 added 에). 여기는 보기 + 「YAML 고치기」(글상자 · 저장 · 기본으로) — 문서는 안 바뀐다.
const FW_THEME_OPEN = new Set(); // 사람이 펴 둔 테마
const FW_THEME_HELP = "04 「에이전트 기반 문서 구조 및 작성 지침 보완」 이 작성 지침을 뽑을 때 함께 받는 목록입니다 — 테마마다 YAML 파일 하나.\n· 구분 기준 타입 = 그 종류의 문서에서 중요하게 볼 항목(연구개발과제: 참여기관 · 연차 · 연구목표 · 예산 …)\n· 템플릿 = 개요 템플릿(레벨마다 레터)\n· 테이블 타입 = 표가 무엇을 담는 꼴인지와 작성 방법(본문 · 헤딩 · 그림 · 값 테이블 …)\nLLM 은 문서의 테마 · 문서가 쓰는 템플릿 · 표마다의 테이블 타입을 이 목록에서 밝히고, 해당하는 것이 없으면 새로 정의해 목록에 더합니다(「LLM 이 정의함」).\n「YAML 고치기」 로 고치면 이 PC 에 저장되고 기본본보다 먼저 읽습니다 — 항목을 지우려면 그 줄을 지우고 저장합니다. 다음 04 실행부터 읽습니다(문서는 안 바뀜).";
const FW_THEME_SRC = { llm: ["LLM 이 정의함", "ok", "04 의 LLM 이 새로 정의해 더한 항목 — 「YAML 고치기」 에서 고치거나 지울 수 있습니다"], user: ["사람이 고침", "user", "이 PC 에서 사람이 고치거나 더한 항목"] };
function fwThemeTag(text, cls, title) { const t = el("span", `fw-tag ${cls}`.trim(), text); if (title) t.title = title; return t; }
async function fwThemesDraw(box, alive) {
  box.replaceChildren(el("p", "hnote lg-msg", "테마를 읽고 있습니다…"));
  let got;
  try { got = await api("/api/form-themes"); }
  catch (e) { if (alive()) box.replaceChildren(el("p", "hwarn lg-msg fail", `테마를 읽지 못했습니다 — ${e.message}`)); return; }
  if (!alive()) return;
  const head = el("h3", "fw-th-head", "미리 적어 둔 테마"), g = FW.guidance || {};
  head.append(hHelp("테마 안내", FW_THEME_HELP, { note: true }));
  box.replaceChildren(head);
  if (!(got.themes || []).length) box.append(el("p", "hnote lg-msg", "테마가 없습니다."));
  const used = new Set((g.ready ? g.templates || [] : []).map((t) => t.id));
  for (const t of got.themes || []) box.append(fwThemeEl(t, { mine: !!(g.ready && g.theme && g.theme.id === t.id), used, max: got.max, redraw: () => fwThemesDraw(box, alive) }));
}
function fwThemeEl(t, o) {
  const det = el("details", "fw-th"), sum = el("summary"), body = el("div", "fw-th-body"), url = `/api/form-themes/${encodeURIComponent(t.id)}/yaml`;
  det.dataset.theme = t.id;
  det.open = FW_THEME_OPEN.has(t.id);
  det.addEventListener("toggle", () => { if (det.open) FW_THEME_OPEN.add(t.id); else FW_THEME_OPEN.delete(t.id); });
  sum.append(el("strong", null, t.name), el("span", "fw-muted", `구분 기준 타입 ${t.division.length} · 템플릿 ${t.templates.length} · 테이블 타입 ${t.tables.length}`));
  if (o.mine) sum.append(fwThemeTag("이 문서의 테마", "ok", "04 가 이 문서의 테마로 밝혔습니다"));
  if (t.src === "llm") sum.append(fwThemeTag(...FW_THEME_SRC.llm));
  if (t.custom && t.src !== "llm") sum.append(fwThemeTag("사람이 고침", "user", "이 PC 에 저장한 사본을 씁니다(기본본보다 먼저)"));
  if (t.docs.length || t.signs) body.append(el("p", "fw-muted fw-th-docs", [t.docs.join(" · "), t.signs].filter(Boolean).join(" — ")));
  const sec = (kind, title, items, text, mark, tip) => {
    if (!items.length) return;
    body.append(el("h4", "fw-th-kind", title));
    for (const x of items) {
      const row = el("div", "fw-guide fw-th-item"), name = el("span", "fw-tag guide", x.name), m = mark ? mark(x) : "";
      row.dataset.item = `${kind}:${t.id}.${x.id}`;
      if (tip && tip(x)) name.title = tip(x);
      row.append(name);
      if (m) row.append(fwThemeTag(m, "ok", "04 가 이 문서가 쓰는 것으로 밝혔습니다"));
      if (FW_THEME_SRC[x.src]) row.append(fwThemeTag(FW_THEME_SRC[x.src][0], FW_THEME_SRC[x.src][1], [FW_THEME_SRC[x.src][2], x.at ? `더한 날 ${x.at}` : ""].filter(Boolean).join("\n")));
      row.append(el("span", null, text(x) || "(작성 방법 없음)"));
      body.append(row);
    }
  };
  sec("division", "구분 기준 타입", t.division, (x) => x.how);
  sec("templates", "템플릿", t.templates, (x) => `${x.levels.join(" › ")}${x.how ? ` — ${x.how}` : ""}`, (x) => (o.used.has(`${t.id}.${x.id}`) ? "이 문서가 씀" : ""));
  sec("tables", "테이블 타입", t.tables, (x) => x.how, null, (x) => (x.signs ? `판별 단서: ${x.signs}` : ""));
  const changed = t.custom || !!t.src || [...t.division, ...t.templates, ...t.tables].some((x) => x.src !== "default");
  const tools = el("div", "fw-th-tools");
  tools.append(hBtn("YAML 고치기", async () => {
    if (body.querySelector(".fw-th-edit")) return;
    let y;
    try { y = await api(url); } catch (e) { return toast(e.message || String(e), true); }
    if (!body.isConnected || body.querySelector(".fw-th-edit")) return;
    const box = el("div", "fw-th-edit"), ta = el("textarea", "fw-th-yaml"), row = el("div", "fw-th-tools");
    ta.value = y.text; ta.rows = 18; ta.spellcheck = false; ta.maxLength = o.max || 20000;
    ta.setAttribute("aria-label", `${t.name} 테마의 YAML`);
    row.append(hBtn("저장", async () => {
      try { await api(url, { method: "PUT", headers: H_JSON, body: JSON.stringify({ text: ta.value }) }); }
      catch (e) { return toast(e.message || String(e), true); }
      toast(`「${t.name}」 테마를 이 PC 에 저장했습니다 — 다음 04 실행부터 읽습니다`);
      FW_THEME_OPEN.add(t.id);
      o.redraw();
    }, { cls: "btn sm primary", title: "이 글을 이 PC 의 사본에 저장합니다 — 기본본보다 먼저 읽습니다(틀린 YAML 은 저장하지 않고 알립니다 · 문서는 안 바뀜)" }),
    hBtn("기본으로", async () => {
      if (!window.confirm(t.default ? `「${t.name}」 테마를 기본본으로 되돌립니다 — 이 PC 에서 고친 것과 LLM 이 정의해 더한 항목이 지워집니다. 진행할까요?` : `「${t.name}」 테마는 기본본이 없습니다 — 되돌리면 이 테마가 없어집니다. 진행할까요?`)) return;
      try { await api(url, { method: "DELETE" }); } catch (e) { return toast(e.message || String(e), true); }
      toast(t.default ? `「${t.name}」 테마를 기본본으로 되돌렸습니다` : `「${t.name}」 테마를 지웠습니다`);
      o.redraw();
    }, { disabled: !changed, title: changed ? "이 PC 의 사본을 지웁니다(고친 것 · LLM 이 더한 항목 포함)" : "기본본 그대로입니다" }),
    hBtn("닫기", () => box.remove(), { title: "저장하지 않고 글상자를 닫습니다" }));
    box.append(ta, row);
    body.append(box);
    ta.focus();
  }, { title: "이 테마의 YAML 글을 열어 고칩니다 — 저장하면 이 PC 에 남고 기본본보다 먼저 읽습니다(항목을 지우려면 그 줄을 지우고 저장)" }));
  body.append(tools);
  det.append(sum, body);
  return det;
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
    const th = [g.theme ? `문서의 테마 「${g.theme.name}」` : "", (g.templates || []).length ? `템플릿 ${g.templates.map((t) => t.name).join(" · ")}` : "", g.tableTypeCount ? `표 ${g.tableTypeCount}개의 테이블 타입` : "",
      (g.defined || []).length ? `새로 정의 ${g.defined.map((d) => d.name).join(" · ")}` : ""].filter(Boolean); // 테마 · 템플릿 · 테이블 타입의 판정(② §5-7)
    if (th.length) lines.push(["테마 · 테이블 타입", th.join(" · ")]);
  }
  const odd = (FW.sh && FW.sh.items) || []; // 이상한 서식 줄(② §5-11) — 스크립트가 찾은 것: 사람이 골라 서식 수정 · 삭제
  if (odd.length) lines.push(["이상한 서식", fwShapeCountText(FW.sh)]);
  const shapes = dashBtn(`이상한 서식 보기${odd.length ? ` (${odd.length})` : ""}`, fwShapesOpen,
    { disabled: !FW.sh, title: odd.length ? "양식의 상자 안에서 레터가 안 찍히는 줄 · 레터를 글로 친 줄을 보고, 줄마다 서식 수정 · 삭제를 골라 반영합니다(문서가 바뀜 · 실행 취소 한 번)" : "양식의 상자 안에서 이상한 서식의 줄을 찾지 못했습니다", focus: "act:headsLlm:shapes" });
  const criteria = dashBtn("지침 생성 기준 보기", fwCriteriaOpen, // 열 머리 = 「작성 지침 생성 기준」 — 이 카드 안에서는 「작성」 을 줄인다(옆 단추 「작성 지침 보기」 와 짝)
    { title: "이 단계의 에이전트가 자리별 작성 지침을 만들고 보완할 때 따르는 기준과, 함께 받는 답의 규칙 · 미리 적어 둔 테마를 봅니다 — 작성 지침 자체가 아닙니다.", focus: "act:headsLlm:criteria" });
  const attach = dashBtn("샘플·추가 서식 첨부…", () => fwPick(".hwp,.hwpx,.docx,.pdf,.txt,.md,.png,.jpg,.jpeg,.webp", true, fwChangeExamples),
    { disabled: busy, title: "작성 예시나 함께 비교할 서식을 올립니다. 이 작업의 자리별 작성 방법을 추출할 때 읽습니다.", focus: "act:headsLlm:attach" });
  const guideActions = [criteria, attach, shapes, ...files.map((f) => dashBtn(`${f.name} 빼기`, () => fwChangeExamples([], f.id),
    { disabled: busy, title: "이 작업의 작성 지침 참고 파일에서 뺍니다", focus: `act:headsLlm:remove:${f.id}` }))];
  if (chain || extracting) return { state: "run", text: extracting ? "목적 문서의 예시와 첨부 서식을 읽고 자리별 작성 지침을 추출하고 있습니다" : "헤딩 · 표 · 서식을 검증하고 있습니다", lines,
    acts: chain && !extracting ? [dashBtn("멈춤", () => dsLlmStop(), { title: "진행 중인 구조 판정이 끝나면 멈춥니다", focus: "act:headsLlm:stop" }), ...guideActions] : guideActions };
  const run = [dashBtn("보완 실행", fwStartGuidance, { primary: !all && !skip && A.base && llmOn, disabled: !A.base || A.busy || A.llmBusy || busy || !llmOn,
    title: "헤딩·표를 검증한 뒤 목적 문서 속 예시와 추가 서식에서 자리별 작성 지침을 추출합니다(유료 LLM).", focus: "act:headsLlm" }), ...guideActions];
  if (all && g.run?.state !== "failed") {
    const j = g.judgmentCounts;
    const text = j ? `LLM이 ${g.placeCount}곳을 판정했습니다 · 지침 적용 ${j.apply}곳 · 해당 없음 ${j.not_applicable}곳 · 근거 부족 ${j.insufficient}곳` : `자리 ${g.count}곳의 작성 지침을 추출했습니다`;
    return { state: "done", text, lines, acts: [...run, dashBtn("작성 지침 보기", () => fwWriteOpen("guides"), { title: "04가 뽑은 자리별 작성 지침을 봅니다 — 글을 쓰는 LLM이 읽습니다.", focus: "act:headsLlm:view" })] };
  }
  if (skip) return { state: "done", skipped: true, word: "건너뜀", text: "건너뜀 — 스크립트 분석 결과로 진행합니다(「보완 실행」 은 지금이라도 할 수 있습니다)", lines,
    acts: [...run, dashBtn("건너뛰기 취소", () => fwStepMark("headsLlm", null, "에이전트 기반 문서 구조 및 작성 지침 보완을 다시 할 일로 둡니다"), { title: "이 줄을 다시 할 일로 둡니다", focus: "act:headsLlm:unskip" })] };
  if (!A.base) return { state: "todo", text: "문서 구조 분석이 끝나야 합니다", lines, acts: run };
  if (!llmOn) return { state: "done", skipped: true, word: "건너뜀", text: "LLM 을 쓸 수 없어 건너뜁니다 — 스크립트 분석 결과로 진행합니다", lines, acts: run };
  const failure = g.run?.state === "failed" ? g.run.error : v.job?.status === "failed" ? v.job.error : g.error;
  const text = failure || (bad ? "구조 판정이 실패했습니다. 다시 실행하거나 건너뛸 수 있습니다." : g.refStale ? `규정 · 문서 목적이 판정 뒤에 바뀌었습니다 — 그 글이 닿는 자리 ${g.refStale}곳만 다시 판정합니다(다른 자리의 판정은 이어 씁니다).` : g.stale ? "입력이 바뀌었습니다. 현재 양식과 첨부로 작성 지침을 다시 추출하세요." : doneN ? `구조 판정 ${doneN}/${four.length} · 자리별 작성 지침 추출 전` : "목적 문서의 작성 예시를 읽습니다. 함께 비교할 샘플·서식이 있으면 실행 전에 첨부하세요.");
  return { state: "now", text, lines, acts: [...run, dashBtn("건너뛰기", () => fwStepMark("headsLlm", "skip", "에이전트 기반 문서 구조 및 작성 지침 보완을 건너뜁니다 — 스크립트 분석 결과로 진행합니다"), { title: "스크립트 분석 결과로 다음 줄로 넘어갑니다", focus: "act:headsLlm:skip" })] };
}
function fwGuidesStep(gw, A, heads, guided) { // 04의 자리별 판정이 있으면 05는 추가 메모용이다.
  const topics = FW.fr && FW.fr.review && FW.fr.review.topics, mark = fwMark("guides");
  // 2026-11-24 사용자 "작성 지침 확인/적기가.. 지침작성 자리가 맞냐? 지침 작성 자리에는 양식검토, 채울자리 이렇게 있던데?" — 열의 맨 위(자료 · 양식 검토)가 아니라 「채울 자리」 로 바로 가서 지침을 펼치고 그 자리에서 적는다(fwWriteOpen("guides"))
  const open = (primary) => dashBtn("작성 지침 보기 · 적기", () => fwWriteOpen("guides"), { primary, title: "글을 쓰는 LLM이 읽는 자리별 작성 지침을 보고, 헤딩 자리에 직접 적습니다 — 「지침 작성」 열의 「채울 자리」로 갑니다(문서는 안 바뀜)", focus: "act:guides" });
  const more = topics && topics.length ? [dashBtn("테마 · 키워드 보기", () => fwWriteOpen("topics"), { title: "양식 검토가 뽑은 「자료에서 찾을 테마 · 키워드」 — 골라서 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사합니다", focus: "act:guides:topics" })] : [];
  if (gw.hwpx === false) return { state: "", text: "hwpx 문서만 됩니다", acts: [open(false), ...more] };
  const base = `헤딩 ${heads}곳 · 작성 지침이 있는 자리 ${guided}곳`;
  if (mark) return { state: "done", ...(mark === "skip" ? { skipped: true, word: "건너뜀" } : { word: "확인함" }), text: `${mark === "skip" ? "건너뜀" : "확인함"} — ${base}`,
    acts: [open(false), ...more, dashBtn(mark === "skip" ? "건너뛰기 취소" : "확인 취소", () => fwStepMark("guides", null, "작성 지침 확인을 다시 할 일로 둡니다"), { title: "이 줄을 다시 할 일로 둡니다", focus: "act:guides:undo" })] };
  if (A.base && FW.guidance?.ready && FW.guidance.audited) return { state: "done", word: "자동 판정",
    text: "양식 검토와 초안 작성에 LLM의 자리별 판정을 사용합니다. 필요할 때 추가 지침을 적을 수 있습니다.", acts: [open(false), ...more] };
  if (!A.base) return { state: "todo", text: `${base} — 문서 구조 분석이 끝나야 합니다`, acts: [open(false), ...more] };
  return { state: "now", text: `선택 — ${base}. 지침을 보고 없는 자리에 적은 뒤 「확인함」, 볼 것이 없으면 「건너뛰기」`,
    acts: [open(true), ...more, dashBtn("확인함", () => fwStepMark("guides", "done", "작성 지침을 확인했습니다"), { title: "작성 지침을 확인했습니다 — 다음 줄로 넘어갑니다(「확인 취소」 로 되돌립니다)", focus: "act:guides:done" }),
      dashBtn("건너뛰기", () => fwStepMark("guides", "skip", "작성 지침 확인을 건너뜁니다"), { title: "확인하지 않고 다음 줄로 넘어갑니다(「건너뛰기 취소」 로 되돌립니다)", focus: "act:guides:skip" })] };
}

// 초안이 0개인 까닭을 가른다(서버가 자리마다 준 why — guide_write_api._one): 에이전트가 행동 없이 답함(자료에 해당 내용 없음) ↔ 검사에서 버림 ↔ 쓸 자리를 안 고른 상자 ↔ 이미 채운 줄.
// 2026-11-27(spec_양식작성 ② §5-12 8): ask = 그 자리에 닿는 「확인할 것」 에 답하지 않음(LLM 을 안 부름) · nomat = 작성 계획도 자료에서 쓸 것을 못 찾은 자리 · noaction = 계획은 쓸 것을 적었는데 에이전트가 행동 없이 답함
// (까닭은 답 글 — 「자료에 없음」 으로 단정하지 않는다: 근거 절을 잘못 골랐을 수 있다 → 「자료 전체로 다시 받기」).
const FW_WHY = { ask: "확인할 것에 답하지 않음", nomat: "자료에 해당 내용 없음", noaction: "초안 없음(답 글에 까닭)", dropped: "검사에서 제외", noslot: "쓸 자리를 고르지 않음", filled: "이미 채운 줄", boxed: "쓸 자리는 아래 상자에" };
function fwRunWhy(run) { // 「자료에 해당 내용 없음 1곳 · 검사에서 제외 1곳 · 실패 1곳」 | ""
  const items = (run && run.items) || [], out = [];
  for (const [k, word] of Object.entries(FW_WHY)) { const n = items.filter((i) => i.state === "none" && (i.why || "noaction") === k).length; if (n) out.push(`${word} ${n}곳`); }
  const failed = items.filter((i) => i.state === "failed").length;
  if (failed) out.push(`실패 ${failed}곳`);
  const cut = items.filter((i) => i.state === "cut").length; // 서버를 다시 켜 끊긴 실행의 자리(받던 · 기다리던 자리)
  if (cut) out.push(`끊김 ${cut}곳`);
  const unpicked = items.filter((i) => (i.unpicked || []).length).length; // 같은 이름의 자리를 안 골라 그 자리를 안 쓴 상자(guide_write_api._one 의 unpicked)
  if (unpicked) out.push(`같은 이름 자리를 안 골라 일부를 안 쓴 상자 ${unpicked}곳`);
  return out.join(" · ");
}
function fwAppliedN(run) { // 반영한 초안 수 — **이번 실행의 턴**만 센다(문서의 모든 에이전트 턴이 아니다: 전에 에이전트 보기에서 따로 반영한 카드가 「반영함」 으로 세어지지 않게 — astra 2차 G13).
  if (typeof AGENT !== "object" || !AGENT.turns) return 0; // 실행 기록이 없으면(초기화한 뒤 · 실행 상태 파일이 없는 옛 작업) 지침 작성이 낸 턴(요청 글이 「[지침 작성]」 으로 시작)으로 센다
  const ids = new Set(((run && run.items) || []).map((i) => i.turn).filter(Boolean));
  const mine = AGENT.turns.filter((t) => (run ? ids.has(t.id) : String(t.text || "").startsWith("[지침 작성]")));
  return mine.reduce((n, t) => n + (t.proposals || []).filter((p) => p.state === "applied").length, 0);
}
// ---- 「모두 반영」(대시보드 13 — 2026-11-25 사용자 「여기서는 모두 적용하기를 실행하는 버튼을 넣어줘」 · spec_양식작성 ② §5-5) -------------------------------------------
// 새 반영 길이 아니다 — 에이전트 보기의 「문서에 반영」 과 같은 함수(doc_agent.js agentApply)를 이번 실행의 열린 초안마다 차례로 부른다: 카드마다 처음 고른 줄 · 칸만(경고가 있어 고르지 않은 줄은 안 넣는다) ·
// 카드 하나 = 실행 취소 하나. 후보 묶음(choiceGroup — 하나만 반영)과 고른 줄이 없는 카드는 사람이 고르게 남긴다.
function fwOpenDrafts(run) { // → {go[{tid, pid}], held(남길 카드 수)}
  const out = { go: [], held: 0 };
  if (typeof AGENT !== "object" || !AGENT.turns) return out;
  const ids = new Set(((run && run.items) || []).map((i) => i.turn).filter(Boolean));
  // 이전 계획의 초안(그 턴을 받은 뒤 작성 계획을 다시 세웠거나 그 자리의 답을 고쳤다 — 서버 덮임의 old)은 넣지 않고 남긴다: 옛 기관 · 옛 자료로 쓴 초안이 그대로 들어가지 않게(astra R2 P1)
  const oldTurns = new Set(((FW.cov && FW.cov.rows) || []).filter((r) => r.old && r.turn).map((r) => r.turn));
  for (const t of AGENT.turns.filter((x) => (run ? ids.has(x.id) : String(x.text || "").startsWith("[지침 작성]")))) {
    for (const p of t.proposals || []) {
      if ((p.state || "open") !== "open" || p.type === "styleCopy") continue;
      if (oldTurns.has(t.id)) { out.held += 1; continue; }
      const rows = (p.type === "fill" || p.type === "tableFill") && typeof agentFillPicks === "function" ? agentFillRows(p).map(agentFillKey).filter((k) => agentFillPicks(p).has(k)) : null;
      // 처음부터 고르지 않은 카드(경고가 있는 글 쓰기 · 에이전트가 지은 글 — preselect false)도 남긴다: 전에는 줄을 고르는 카드(자리 · 표 채우기)만 보고 글 쓰기 카드는 그대로 넣었다(2026-11-27 astra P2)
      if (p.choiceGroup || (rows && !rows.length) || (!rows && p.preselect === false)) out.held += 1;
      else out.go.push({ tid: t.id, pid: p.id });
    }
  }
  return out;
}
function fwApplyStep(got, applied) { // 대시보드 13 「고른 초안을 문서에 반영」 — 에이전트 보기 열기 + 「모두 반영」(열린 초안이 있을 때)
  const open = fwOpenDrafts(FW.gw && FW.gw.run), n = open.go.length, busy = !!FW.applyingAll;
  const acts = [dashBtn(busy ? "반영하는 중…" : `모두 반영${n ? ` (${n})` : ""}`, () => fwApplyAll(), { primary: !!n && !busy, disabled: !n || busy, focus: "act:applyAll",
    title: n ? `열린 초안 ${n}개를 차례로 문서에 반영합니다 — 카드마다 처음 고른 줄 · 칸만(경고가 있어 고르지 않은 줄은 안 넣음) · 카드 하나마다 실행 취소 한 번${open.held ? ` · 후보를 골라야 하거나 고른 줄이 없는 ${open.held}개는 남김` : ""}` : "반영할 열린 초안이 없습니다" })];
  if (toolShown("Agent")) acts.push(dashBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "받은 초안(제안 카드)을 하나씩 보고 「문서에 반영」 을 누릅니다", focus: "act:apply" }));
  if (applied) acts.push(dashBtn("근거 보기", () => fsrcOpen(), { title: "문서 옆 열 「참조한 자료」 — 반영한 문단을 누르면 그 줄이 참조한 자료의 자리(쪽 · 절 · 앞뒤 글)를 보입니다", focus: "act:source" }));
  const left = n ? ` · 남은 초안 ${n}개` : "";
  // 덮임(서버가 턴 기록에서 센 것 — ② §5-12 9): 끝남 = 반영한 것이 있고 「모두 반영」 이 넣을 초안이 안 남음. 안 고른 줄(경고 · 같은 줄 뒤의 값)은 「남음」 으로 글에 — 끝남을 막지 않는다(사람이 일부러 안 넣을 수 있다)
  const c = FW.cov && FW.cov.counts, cov = c ? ` — 자리 ${c.applied}곳 · ${c.appliedLines}줄${c.leftLines ? ` · 안 고른 채 남은 줄 ${c.leftLines}(자리 ${c.left}곳 — 에이전트 보기에서 고릅니다)` : ""}` : "";
  const openN = n || (c ? c.open : 0); // 반영할 것이 남았나 — 이번 실행의 카드(n) + 서버가 센 모든 자리의 열린 초안(다른 실행에서 받아 둔 것 · 최근 20턴 밖의 것까지: astra R2)
  return { state: busy ? "run" : applied && !openN ? "done" : got || openN || applied ? "now" : "todo",
    text: busy ? "초안을 차례로 반영하는 중" : applied ? `반영한 초안 ${applied}개${cov}${left}${open.held ? ` · 고를 것 ${open.held}개` : ""}` : "제안 카드의 「문서에 반영」 이나 「모두 반영」 을 누른 초안만 들어갑니다 — 양식에 글이 써지는 곳입니다", acts };
}
async function fwApplyAll() {
  if (FW.applyingAll || !state.id) return;
  if (typeof agentApply !== "function") return toast("에이전트 보기를 읽지 못했습니다 — 문서를 다시 여세요", true);
  if (typeof agentLoad === "function") await agentLoad(); // 서버에 저장한 제안 상태로(다른 창에서 반영했을 수 있다)
  const id = state.id, { go, held } = fwOpenDrafts(FW.gw && FW.gw.run);
  if (!go.length) return toast(held ? `반영할 초안이 없습니다 — 남은 ${held}개는 후보를 고르거나 줄을 골라야 합니다(에이전트 보기)` : "반영할 초안이 없습니다", true);
  if (!window.confirm(`초안 ${go.length}개를 차례로 문서에 반영합니다 — 카드마다 처음 고른 줄 · 칸만 넣습니다(경고가 있어 고르지 않은 줄은 넣지 않습니다)${held ? `. 후보를 골라야 하거나 고른 줄이 없는 ${held}개는 남깁니다` : ""}. 카드 하나마다 실행 취소 한 번으로 되돌릴 수 있습니다. 진행할까요?`)) return;
  FW.applyingAll = true;
  fwAutoRedraw();
  let ok = 0;
  const bad = [];
  try {
    for (const x of go) {
      if (state.id !== id) break;
      await agentApply(x.tid, x.pid);
      const p = typeof agentPropOf === "function" ? agentPropOf(agentTurnOf(x.tid), x.pid) : null;
      if (p && p.state === "applied") ok += 1; else bad.push((p && p.why) || "반영하지 못함");
    }
  } finally { FW.applyingAll = false; }
  if (state.id !== id) return;
  toast(`모두 반영 — ${ok}개 반영${bad.length ? ` · 못 함 ${bad.length}(${bad[0]})` : ""}${held ? ` · 남김 ${held}` : ""}${ok ? " — 다음은 「반영한 뒤 서식 정리」" : ""}`, !ok && !!bad.length);
  await fwRead(true);
  fwAutoRedraw();
}
// ---- 「반영한 뒤 서식 정리」(대시보드 14 — 2026-11-25 사용자 「지금 서식이 안맞는데 13 다음에 서식 정리하는 기능 넣어줘」 · spec_양식작성 ② §5-5) ---------------------------------
// 새 정리 길이 아니다 — 이관 · 취합의 「넣은 뒤 템플릿 · 서식 정리」(POST …/merge-retidy · merge_retidy_api)를 그대로 부른다: 넣은 줄 = 반영한 초안의 문단(서버의 양식 작성 어댑터 agent_filled) ·
// 헤딩을 스크립트로 다시 분석한 뒤 양식의 줄이 있는 레벨은 그 줄의 서식으로, 양식에 없는 깊은 레벨은 넣은 줄 가운데 가장 많은 서식으로(레터 뒤 묶음 빈칸 · 둘째 줄 맞춤 · 실행 취소 1)
function fwRetidyStep() {
  const rt = FW.rt, busy = !!FW.retidying;
  if (!rt) return { state: "todo", text: "정리 상태를 읽지 못했습니다" };
  const btn = (primary) => [dashBtn(busy ? "정리하는 중…" : "서식 정리", () => fwRetidyRun(), { primary, disabled: busy || !rt.fill, focus: "act:retidy",
    title: rt.fill ? "반영한 초안의 줄을 양식의 템플릿 · 서식으로 맞춥니다 — 헤딩을 스크립트로 다시 분석한 뒤(몇 초) 양식의 줄이 있는 레벨은 그 서식으로, 양식보다 깊은 줄은 넣은 줄 가운데 가장 많은 서식으로(문서가 바뀜 · 실행 취소 한 번)" : rt.why || "반영한 초안이 없습니다" })];
  if (busy) return { state: "run", text: "헤딩을 다시 분석하고 반영한 줄의 서식을 맞추는 중", acts: btn(false) };
  if (!rt.fill) return { state: "todo", text: rt.why || "초안을 반영한 뒤에 합니다", acts: btn(false) };
  const a = rt.applied, c = (a && a.counts) || {};
  if (a && (a.fill || 0) >= rt.fill) return { state: "done", text: `정리함 — 맞춘 줄 ${c.changed || 0}개 · 레벨 ${c.levels || 0}개${c.left ? ` · 못 맞춘 줄 ${c.left}개` : ""}`, acts: btn(false) };
  return { state: "now", text: `반영한 초안의 줄 ${rt.inserted || 0}개 — 양식의 템플릿 · 서식으로 맞춥니다${a ? "(앞 정리 뒤에 초안을 더 반영했습니다)" : ""}`, acts: btn(true) };
}
// ---- 「지침 검토 · 수정」(2026-11-26 사용자 「템플릿이 선택되고 목적문서가 작성될 경우 템플릿 작성지침에 따라 작성되었는지 검토 후 수정하는 도구」 · spec_양식작성 ② §5-9) ---------------------------------
// 새 LLM 길이 아니다 — 이관형 「지침 보정(LLM)」 의 끝점(…/guide-fix · 에이전트 22)이 조립된 작성 지침(문서 · 사람 · 양식 지침 · 규정 · 문서 목적)으로 묻는다. 검토(유료 · 문서 안 바뀜) → 결과를 문서 옆 열에서 보고
// (자리마다 맞음 · 고침 제안 · 못 고침) → 사람이 고른 고침만 반영(실행 취소 1). 양식(템플릿)이 정해지지 않은 문서는 까닭을 보이고 건너뜀.
const FW_FIX_SRC = { doc: "양식의 작성요령", user: "사람", form: "양식 지침", rule: "규정", purpose: "문서 목적", struct: "표 구조" };
const FW_FIX_STATE = { ok: "맞음", fix: "고침 제안", left: "못 고침", none: "답 없음" };
function fwGuideFixOpenN() { // 아직 반영하지 않은 검토의 고침 제안 수
  const gf = FW.gf, p = gf && gf.plan, a = gf && gf.applied;
  return p && !(a && a.planId === p.planId) ? (p.fixes || []).length : 0;
}
function fwGuideFixStep(applied) {
  const gf = FW.gf, busy = FW.fixing || "";
  if (!gf) return { state: "todo", text: "검토 상태를 읽지 못했습니다" };
  if (!gf.form) return { state: applied ? "done" : "todo", text: "건너뜀 — 이 문서에 정해진 양식(템플릿)이 없습니다. 헤딩 추출의 「양식」 에서 고르면 그 양식의 작성 지침으로 검토합니다" };
  const n = (gf.guides || {}).total || 0, p = gf.plan, a = gf.applied, open = fwGuideFixOpenN();
  const cnt = (k) => ((p && p.places) || []).filter((x) => x.state === k).length;
  const ask = dashBtn(busy === "ask" ? "검토하는 중…" : p ? "다시 검토" : "지침 검토", () => fwGuideFixAsk(), { primary: !!applied && !!n && !p && !busy, disabled: !!busy || !n || !applied, focus: "act:guideFix",
    title: !applied ? "초안을 반영한 뒤에 검토합니다" : n ? `양식 「${gf.form.name}」 — 작성 지침이 붙은 자리 ${n}곳의 글이 지침에 맞는지 LLM 이 검토합니다(유료 LLM · 수십 초 · 문서는 아직 바뀌지 않습니다)` : "이 문서에 닿는 작성 지침이 없습니다" });
  const view = p && !p.nothing ? [dashBtn(open ? `검토 결과 보기 (고침 제안 ${open})` : "검토 결과 보기", () => fwGuideFixOpen(), { primary: !!open && !busy, disabled: !!busy, focus: "act:guideFix:view",
    title: "자리마다의 검토 결과(맞음 · 고침 제안 · 못 고침)를 문서 옆 열에 보입니다 — 고른 고침만 반영합니다(실행 취소 한 번)" })] : [];
  const acts = [...view, ask];
  if (busy) return { state: "run", text: busy === "ask" ? "자리마다 작성 지침에 맞게 썼는지 검토하는 중(유료 LLM)" : "고른 고침을 반영하는 중", acts };
  if (!applied) return { state: "todo", text: "초안을 반영한 뒤에 검토합니다", acts };
  if (!n) return { state: "done", text: "건너뜀 — 이 문서에 닿는 작성 지침(문서의 작성요령 · 양식 지침 · 규정 · 사람이 적은 것)이 없습니다", acts };
  if (!p) return { state: "now", text: `양식 「${gf.form.name}」 — 작성 지침이 붙은 자리 ${n}곳을 검토합니다`, acts };
  if (p.nothing) return { state: "done", text: `검토함 — ${p.nothing}`, acts };
  const sum = `맞음 ${cnt("ok")} · 고침 제안 ${cnt("fix")} · 못 고침 ${cnt("left")}${cnt("none") ? ` · 답 없음 ${cnt("none")}` : ""}`;
  if (open) return { state: "now", text: `검토함 — 자리 ${(p.places || []).length}곳: ${sum}. 결과를 보고 고른 고침을 반영합니다`, acts };
  const done = a && a.planId === p.planId ? ` · 반영한 고침 ${(a.done || []).length}건` : "";
  return { state: "done", text: `검토함 — ${sum}${done}`, acts };
}
async function fwGuideFixAsk(auto = false) { // → "" | 못 한 까닭. 문서는 안 바뀐다(검토 결과만 저장)
  if (FW.fixing || !state.id) return "다른 검토가 도는 중입니다";
  FW.fixing = "ask";
  fwAutoRedraw();
  let why = "";
  try {
    const r = await api(`/api/docs/${state.id}/guide-fix/ask`, { method: "POST" });
    if (!auto) toast(r.nothing ? `지침 검토 — ${r.why}` : `지침 검토 — 고침 제안 ${(r.fixes || []).length}건 · 못 고침 ${(r.left || []).length}건 · 맞는 자리 ${(r.ok || []).length}곳`);
  } catch (e) { why = e.message || String(e); }
  finally { FW.fixing = ""; }
  if (why && !auto) toast(`지침 검토 — ${why}`, true);
  await fwRead(true);
  fwAutoRedraw();
  if (!why && !auto && fwGuideFixOpenN()) fwGuideFixOpen();
  return why;
}
function fwGuideFixOpen() { // 문서 옆 열 — 자리마다의 검토 결과 + 고침 제안(고르기) + 못 고침 + 맞음
  const gf = FW.gf, p = gf && gf.plan;
  if (!p || typeof headsDlg !== "function") return;
  const { body } = headsDlg("guideFix", "지침 검토 · 수정", gf.form ? `양식 「${gf.form.name}」` : "");
  const tools = $("headsDlgTools"), foot = $("headsDlgFoot");
  for (const x of [tools, body, foot]) x.textContent = "";
  if (typeof hHelp === "function") $("headsDlgHelp").replaceChildren(hHelp("지침 검토 · 수정이란",
    "글이 들어간 자리마다 그 자리의 작성 지침(문서의 작성요령 · 사람이 적은 지침 · 양식 지침 · 규정 · 문서 목적 — 「지침」 열이 보이는 것과 같은 조립)에 맞게 썼는지 LLM 이 검토한 결과입니다. " +
    "「고침 제안」 은 지금 글과 고친 글, 따른 지침과 그 출처를 함께 보입니다 — 고른 것만 한 번에 반영하고 실행 취소 한 번으로 되돌립니다. 새 사실 · 수는 짓지 않습니다(스크립트가 고침마다 검사해 어긴 것은 버립니다). " +
    "「못 고침」 은 문서에 없는 정보가 있어야 고칠 수 있는 곳이라 사람이 고칩니다. 검토한 뒤 글이 바뀐 문단의 고침은 건너뜁니다."));
  const wrap = el("div", "pg-col fwx-col");
  body.append(wrap);
  const done = gf.applied && gf.applied.planId === p.planId;
  const places = p.places || [], fixes = p.fixes || [], left = p.left || [];
  tools.append(el("span", "muted pg-total", `자리 ${nf(places.length)}곳 — ${Object.keys(FW_FIX_STATE).map((k) => `${FW_FIX_STATE[k]} ${nf(places.filter((x) => x.state === k).length)}`).join(" · ")}`));
  const picked = new Set(done ? [] : fixes.map((f) => f.id));
  const go = hBtn("고른 것 반영", () => fwGuideFixApply([...picked], go), { cls: "btn sm primary", disabled: done || !picked.size, title: "고른 고침을 한 번에 문서에 반영합니다(문서가 바뀜 · 실행 취소 한 번) — 검토한 뒤 글이 바뀐 문단은 건너뜁니다" });
  const sync = () => { go.disabled = done || !picked.size; go.textContent = picked.size ? `고른 것 반영 (${nf(picked.size)})` : "고른 것 반영"; };
  const sec = (title, n) => { const s = el("section", "pg-sec fwx-sec"); s.append(el("h3", "pg-h", `${title} ${nf(n)}`)); return s; };
  if (fixes.length) {
    const s = sec(done ? "고침 제안(반영함)" : "고침 제안", fixes.length), ul = el("ul", "pg-list fwx-list");
    for (const f of fixes) {
      const li = el("li", "pg-item fwx-fix");
      const cb = el("input");
      cb.type = "checkbox"; cb.checked = picked.has(f.id); cb.disabled = done;
      cb.onchange = () => { cb.checked ? picked.add(f.id) : picked.delete(f.id); sync(); };
      const lab = el("label", "fgy-cand-row");
      lab.append(cb, el("span", "hb pg-kind", FW_FIX_SRC[f.src] || "작성 지침"), el("b", "pg-title", short(f.where || "", 60)));
      const go2 = hBtn("문서에서", () => headsGo(f.id), { cls: "btn sm pg-tbtn", title: "문서의 그 문단으로" });
      li.append(lab, go2, el("div", "fwx-old", `지금 글: ${f.old}`), el("div", "fwx-new", f.new ? `고친 글: ${f.new}` : "고친 글: (이 문단의 글을 지움)"),
        el("div", "muted fwx-why", `따른 지침: ${f.rule || "—"}${f.why ? ` — ${f.why}` : ""}`));
      ul.append(li);
    }
    s.append(ul);
    wrap.append(s);
  }
  if (left.length) {
    const s = sec("못 고침", left.length), ul = el("ul", "pg-list fwx-list");
    for (const x of left) { const li = pgItem("못 고침", short(x.where || "", 60), x.why || ""); if (x.id) li.querySelector(".pg-item-head").append(hBtn("문서에서", () => headsGo(x.id), { cls: "btn sm pg-tbtn" })); ul.append(li); }
    s.append(ul);
    wrap.append(s);
  }
  const oks = places.filter((x) => x.state === "ok"), none = places.filter((x) => x.state === "none");
  if (oks.length) {
    const s = sec("맞음", oks.length), ul = el("ul", "pg-list fwx-list");
    for (const x of oks) ul.append(pgItem("맞음", short(x.where || "", 60), x.why || "지침에 맞습니다"));
    s.append(ul);
    wrap.append(s);
  }
  if (none.length) {
    const s = sec("답 없음", none.length), ul = el("ul", "pg-list fwx-list");
    for (const x of none) ul.append(pgItem("답 없음", short(x.where || "", 60), x.why || "LLM 이 이 자리의 판정을 적지 않았습니다 — 「다시 검토」 로 다시 묻습니다"));
    s.append(ul);
    wrap.append(s);
  }
  if ((p.rejected || []).length) wrap.append(el("p", "hnote", `스크립트 검사에서 버린 고침 ${nf(p.rejected.length)}건(지은 수 · 너무 늘어난 글 · 고칠 수 없는 줄) — 반영하지 않습니다.`));
  if (!fixes.length && !left.length && !oks.length && !none.length) wrap.append(el("p", "hnote", p.nothing || "검토한 자리가 없습니다."));
  foot.append(go, hBtn("닫기", () => headsColClose(), { cls: "btn sm" }));
  sync();
}
async function fwGuideFixApply(ids, btn) {
  const p = FW.gf && FW.gf.plan;
  if (!p || !ids.length || FW.fixing) return;
  FW.fixing = "apply";
  if (btn) btn.disabled = true;
  fwAutoRedraw();
  let why = "";
  try {
    structOp.lastError = null;
    const r = await structOp("guide-fix/apply", { planId: p.planId, ids });
    if (!r) why = (structOp.lastError && structOp.lastError.message) || "반영하지 못했습니다";
    else toast(r.nothing ? "지침 검토 · 수정 — 반영할 고침이 없습니다(검토한 뒤 글이 바뀌었습니다)" : `지침 검토 · 수정 — 고침 ${(r.done || []).length}건을 반영했습니다${(r.skipped || []).filter((x) => x.skip !== "고르지 않음").length ? ` · 건너뜀 ${(r.skipped || []).filter((x) => x.skip !== "고르지 않음").length}` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
  } finally { FW.fixing = ""; }
  if (why) toast(`지침 검토 · 수정 — ${why}`, true);
  await fwRead(true);
  fwAutoRedraw();
  if (!why && typeof headsColClose === "function") headsColClose();
}
// ---- 「작성 지침 · 샘플 지우기」(대시보드 15 —2026-11-25 사용자 「마지막에 작성 지침 및 샘플 ,, 본문에서 삭제하는 기능도 넣어줘, 이관 테스트에도 있지?」 · spec_양식작성 ② §5-6) ----------------
// 새 지우기 길이 아니다 — 이관 4단계의 「작성요령 삭제」 와 같은 끝점(…/form-cleanup — 지우기 전에 작성 지침을 헤딩 · 표별로 저장 · 실행 취소 1)이고, 양식 작성 문서면 서버가 「작성 샘플」(예시 제목이 붙은 표 · 예문)도 함께 찾는다.
// 확인 창 없이 지운다(이관의 그 줄과 같다 — 2026-11-18 사용자 「이런 알람좀 주지마」 · 실행 취소 한 번)
const fwCleanupText = (cl, done = false) => (cl.patterns || []).filter((p) => (done ? (cl.done || {})[p.key] : p.count)).map((p) => `${p.name} ${done ? cl.done[p.key] : p.count}`).join(" · ");
function fwCleanupStep(applied) {
  const cl = FW.cl, busy = !!FW.cleaning, n = (cl && cl.counts && cl.counts.total) || 0;
  if (!cl) return { state: "todo", text: "지울 것을 읽지 못했습니다" };
  const btn = [dashBtn(busy ? "지우는 중…" : `작성 지침 · 샘플 지우기${n ? ` (${n})` : ""}`, () => fwCleanupRun(), { primary: !!applied && !!n && !busy, disabled: busy || !n, focus: "act:cleanup",
    title: n ? `본문에서 지웁니다 — ${fwCleanupText(cl)}. 지우기 직전에 작성 지침을 헤딩 · 표별로 저장합니다(문서가 바뀜 · 실행 취소 한 번)` : "지울 작성 지침 · 샘플이 없습니다" })];
  if (busy) return { state: "run", text: "작성 지침 · 샘플을 지우는 중", acts: btn };
  if (!n) return { state: applied ? "done" : "todo", text: applied ? "지울 작성 지침 · 샘플이 남지 않았습니다" : "초안을 반영한 뒤 마지막에 지웁니다", acts: btn };
  return { state: applied ? "now" : "todo", text: `${applied ? "" : "초안을 반영한 뒤 마지막에 — "}지울 것: ${fwCleanupText(cl)}`, acts: btn };
}
async function fwCleanupRun() { // → "" | 못 한 까닭
  if (FW.cleaning || !state.id) return "다른 지우기가 도는 중입니다";
  FW.cleaning = true;
  fwAutoRedraw();
  let why = "";
  try {
    structOp.lastError = null;
    const r = await structOp("form-cleanup", { expectRev: state.serverRev });
    if (!r) why = (structOp.lastError && structOp.lastError.message) || "지우지 못했습니다";
    else toast(r.nothing ? "작성 지침 · 샘플 지우기 — 지울 것이 없습니다" : `작성 지침 · 샘플 지우기 — ${fwCleanupText({ patterns: (FW.cl || {}).patterns, done: r.done }, true) || "지웠습니다"}${(r.done.skipped || []).length ? ` · 건너뜀 ${r.done.skipped.length}` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
  } finally { FW.cleaning = false; }
  if (why) toast(`작성 지침 · 샘플 지우기 — ${why}`, true);
  await fwRead(true);
  fwAutoRedraw();
  return why;
}
async function fwRetidyRun(auto = false) { // → "" | 못 한 까닭
  if (FW.retidying || !state.id) return "다른 정리가 도는 중입니다";
  if (!auto && !window.confirm("반영한 초안의 줄을 양식의 템플릿 · 서식으로 맞춥니다 — 헤딩을 스크립트로 다시 분석한 뒤(몇 초) 맞춥니다. 문서가 바뀌고, 실행 취소 한 번으로 되돌릴 수 있습니다. 진행할까요?")) return "취소";
  FW.retidying = true;
  fwAutoRedraw();
  let why = "";
  try {
    structOp.lastError = null;
    const r = await structOp("merge-retidy", { expectRev: state.serverRev });
    if (!r) why = (structOp.lastError && structOp.lastError.message) || "정리하지 못했습니다";
    else if (!auto) { const c = (r.done && r.done.counts) || {}; toast(r.nothing ? `서식 정리 — ${r.why || "맞출 줄이 없습니다"}` : `서식 정리 — ${c.changed || 0}줄을 맞췄습니다${c.left ? ` · 못 맞춘 줄 ${c.left}` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`); }
  } finally { FW.retidying = false; }
  if (why && !auto) toast(`서식 정리 — ${why}`, true);
  await fwRead(true);
  fwAutoRedraw();
  return why;
}

async function formWriteLive(M = null) { // 대시보드(dashboard.js dashLive)의 「양식 작성」 가지 — 단계마다 지금 상태와 그 일을 하는 곳을 여는 단추 · M = 대시보드 모델(머리 아래 「전체 실행」 을 M.top 에) · 「작업 개요」(fwOverviewDraw)도 같은 셈을 쓴다
  await fwRead();
  const lib = FW.lib || { alive: false, docs: [] }, gw = FW.gw || { places: [], materials: [], run: null, enabled: false }, run = gw.run;
  const libBtn = (focus) => [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다" : FW_LIB_DOWN, focus })];
  const docs = lib.docs.length, done = fwDoneExtracts(), going = lib.docs.reduce((n, d) => n + (d.running || 0), 0), mats = gw.materials.length, guided = gw.places.filter((p) => p.n).length, heads = gw.places.filter((p) => p.kind === "head").length;
  const from = gw.libFrom || 0, newDocs = lib.docs.filter((d) => (d.at || 0) > from).length, newDone = lib.docs.reduce((n, d) => n + (d.extracts || []).filter((e) => e.state === "done" && (e.ended || 0) > from).length, 0);
  const RF = fwRefs(), refN = lib.docs.filter((d) => RF.ids.has(d.id)).length, refDone = lib.docs.filter((d) => RF.ids.has(d.id)).reduce((n, d) => n + (d.extracts || []).length, 0);
  const keepOk = RF.only ? !!refN : !!newDocs || fwMark("keep") === "done";
  const items = (run && run.items) || [], got = items.reduce((n, i) => n + (i.proposals || 0), 0), applied = fwAppliedN(run);
  const rv = FW.fr && FW.fr.review, topics = rv && rv.topics;
  const next = !mats ? "take" : "ask";
  let A = fwAnalysis();
  if (!A.view && state.id && typeof dsRefresh === "function") { await dsRefresh(); A = fwAnalysis(); } // 이름 줄의 분석 상태를 아직 못 읽음 — 한 번 읽고 그린다
  if (A.base && FW.fg && !FW.fg.saved && !FW.fgAsked) await fwGuidesKeep(); // 분석이 끝났는데 저장한 작성 지침이 없다 — 한 번 모아 저장(스크립트)
  const S = {
    overview: fwOverviewStep(),
    open: fwOpenStep({ lib, docs, newDocs, mats, keepOk, libBtn, refN }),
    heads: fwHeadsStep(A),
    headsLlm: fwLlmStep(A),
    // 줄의 차례 = 등록부의 차례(「지금」 은 차례상 첫 줄 하나): 준비(… · 작성 지침 확인 · 문서 작성 요령 생성 · 찾을 테마) → 자료 준비 → 작성(작성 계획 · 확인할 것 → 양식 초안 작성 → 검사 → 반영)
    guides: fwGuidesStep(gw, A, heads, guided),
    review: fwReviewStep(gw),
    // 서버가 꺼져 「hold」 일 때 상태 글은 「서버 꺼짐」 — 대시보드의 공용 글 DASH_ST.hold 는 취합의 「기관 미지정」 이라 이 줄에 맞지 않았다(2026-11-24 화면 검사 그림 · 사용자 「진행해줘」)
    // 자료가 아직 없으면 06 이 「지금」 자리를 차지한다(서버가 꺼져도 — 글자만 「서버 꺼짐」): 전에는 꺼지면 「hold」 라 자리를 안 차지해 05 → 08 로 건너뛰었다(2026-11-24 사용자 「한번에 5번에서 8번으로 가버리냐?」).
    // 자료를 이미 다른 길(에이전트 보기의 파일 · 글)로 받았으면 06 · 07 은 자리를 차지하지 않는다(할 수 있음 · 꺼졌으면 「서버 꺼짐」).
    // 06 · 07 의 「끝남」 은 이 문서의 몫으로 센다(2026-11-24 사용자 「초기화 할때 5,6 도 아직 안했다고 나와야지」): 문서 라이브러리는 모든 작업이 같이 쓰는 서버라 그 서버에 있는 것만으로 세면 초기화해도 끝남이 남았다 —
    // 기준 시각(gw.libFrom — 작업을 만든 때 · 마지막 초기화 · 「2단계 초기화」) 뒤에 올린 문서 · 끝난 추출이 있거나, 있는 것을 쓰겠다고 누른 때(「있는 문서 쓰기」 · 「있는 추출 쓰기」)만 끝남.
    keep: fwLibStep("keep", { alive: lib.alive, all: docs, fresh: newDocs, mats, prev: null, libBtn, refN, refDone }),
    extract: fwLibStep("extract", { alive: lib.alive, all: done, fresh: newDone, mats, going, prev: keepOk, libBtn, refN, refDone }),
    take: { state: mats ? "done" : next === "take" ? "now" : "todo", text: mats ? `이 문서의 자료 ${mats}개` : "자료가 없습니다 — 추출한 MD 를 가져오거나 에이전트 보기에서 파일 · 글을 자료로 줍니다",
      acts: [dashBtn("자료 가져오기", () => fwTakeOpen(), { primary: !mats, title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로 가져옵니다(문서 옆 열)", focus: "act:take" })] },
    plan: fwPlanStep(gw),
    // 끝남 = 초안을 하나라도 받았고 작성 계획이 고른 자리 가운데 안 돌린 자리가 없을 때(아래 덮임 — 등록부의 「끝난 것으로 보는 때」) — 돌렸지만 초안이 0개면 끝난 것이 아니다(2026-11-24: 0개인데 「끝남」 으로 보여 사용자가 「작성은 어디서 하는거야?」)
    // 2026-11-27 덮임(② §5-12 9): 끝남 = 초안이 있고 **작성 계획이 고른 자리 가운데 안 돌린 자리가 없음**(FW.cov.counts.idle — 서버가 턴 기록에서 센다 · 못 읽었으면 전의 셈)
    ask: { state: run && run.state === "running" ? "run" : got && !fwIdleN() ? "done" : mats && fwReviewReady() ? "now" : "todo",
      text: run ? (run.state === "running" ? `자리 ${items.filter((i) => i.state !== "queued" && i.state !== "running").length}/${items.length} 받는 중` : `${run.state === "cut" ? "끊긴 실행(서버를 다시 켬)" : "마지막 실행"} — 자리 ${items.length}곳 · 초안 ${got}개${fwRunWhy(run) ? ` · ${fwRunWhy(run)}` : ""}${fwIdleN() ? ` · 작성 계획이 고른 자리 가운데 안 돌린 자리 ${fwIdleN()}곳` : ""}${got ? "" : " — 문서에 넣을 것이 없습니다. 자리를 다시 골라 받습니다"}`)
        : !gw.enabled ? "LLM 을 쓸 수 없습니다" : !mats ? "자료를 먼저 가져옵니다" : fwReviewWhy(),
      acts: [dashBtn("채울 자리 확인 · 초안 받기", () => fwWriteOpen("write"), { primary: !!mats && !got && !fwRunning() && fwReviewReady(), title: "「지침 작성」 열의 「초안 작성」 탭 — 채울 자리는 작성 계획이 골라 둡니다(바꾸려면 체크를 고칩니다). 「작성 초안 받기」 를 누르면 LLM 이 자리마다 초안을 써서 제안 카드로 보입니다(유료 LLM · 문서는 아직 바뀌지 않습니다)", focus: "act:ask" })] },
    check: { state: "", text: "초안마다 저절로 돕니다" },
    apply: fwApplyStep(got, applied),
    retidy: fwRetidyStep(),
    guideFix: fwGuideFixStep(applied),
    cleanup: fwCleanupStep(applied),
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
    // 「N단계 초기화」 는 fwAutoRedraw(대시보드 + 「작업 개요」)로 다시 그린다 — 누른 화면에 확인 줄이 선다(전에는 dashDraw 만: 작업 개요에서 누르면 숨은 대시보드에만 떴다 — 2026-11-25 r202)
    box.append(fwAutoBtn(S, [st]), dashBtn(`${fwStageWord(st)} 초기화`, () => { FW.rs = FW.rs === st ? "" : st; fwAutoRedraw(); }, { disabled: !!off || !!FW.rsBusy, focus: `fwreset:${st}`,
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
const FW_AUTO_KEYS = { open: ["heads", "headsLlm", "guides", "review"], material: ["keep", "extract", "take"], write: ["plan", "ask", "apply", "retidy", "guideFix", "cleanup"] };
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
  open: "문서 구조 분석 및 작성 지침 추출(스크립트) → 에이전트 기반 문서 구조 및 작성 지침 보완 — 자리별 자동 판정(유료) → 문서 작성 요령 생성 · 찾을 테마(유료). 지침을 직접 보거나 적는 작업은 선택입니다.",
  material: "자료 문서 · 추출 · 자료가 있는지 봅니다 — 올리기 · 추출 · 가져오기는 사람이 하는 일이라 없으면 그 줄에서 멈춥니다(추출이 도는 중이면 끝날 때까지 기다립니다)",
  write: "작성 계획 세우기(유료 LLM 한 번 — 고른 자료) → 확인할 것이 남으면 멈춤 → 초안 받기(유료 LLM — 고른 자리, 없으면 작성 계획이 자료에서 쓸 것이 있다고 한 자리) → 「문서에 반영」 은 사람이 제안 카드나 「모두 반영」 으로(멈춤) → 반영한 뒤면 서식 정리(스크립트 — 반영한 줄을 양식의 템플릿 · 서식으로) → 작성 지침 · 샘플 지우기(스크립트 — 지우기 전에 작성 지침 저장)",
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
      const w = await wait(() => { const X = fwAnalysis(); return X.base || X.bad; }, "문서 구조 분석");
      if (w) return w;
      if (fwAnalysis().bad) return `멈춤 — ${name}: 분석이 실패했습니다(「헤딩 추출」 탭에서 확인합니다)`;
      if (!(FW.fg && FW.fg.saved)) await fwGuidesKeep();
      return "";
    }
    if (k === "headsLlm") {
      if (!An.llmBusy && !fwExtractingGuides() && !(await fwStartGuidance())) return `멈춤 — ${name}: 보완을 시작하지 못했습니다`;
      const w = await wait(() => { const X = fwAnalysis(); return !fwExtractingGuides() && !X.llmBusy && !(X.view && X.view.job && X.view.job.chain && X.view.job.status === "running"); }, "문서 구조 검증과 작성 지침 보완");
      if (w) return w;
      const T = fwLlmStep(fwAnalysis());
      if (T.state !== "done") return `멈춤 — ${name}: ${T.text}`;
      return "";
    }
    if (k === "guides") { left.push(`${name} — 사람이 지침을 보고 「확인함」 · 「건너뛰기」 를 누르는 줄입니다`); return ""; }
    if (k === "review" || k === "plan") {
      if (k === "plan" && !mats) return `멈춤 — ${name}: 이 문서의 자료가 없습니다(「자료 가져오기」)`;
      if (k === "plan" && !(FW.fr && FW.fr.review)) return `멈춤 — ${name}: 먼저 「${fwStepRef("review") || "양식 검토"}」 를 하세요(작성 계획은 양식 검토 뒤 — 서버도 409)`;
      if (k === "plan" && fwPlanned() && (FW.fr.open || []).length) { fwWriteOpen("plan"); return `멈춤 — ${name}: 쓰기 전에 확인할 것 ${FW.fr.open.length}개에 답하세요(「지침 작성」 열의 「작성 계획」 탭 — 답한 뒤 다시 「한 번에 진행」)`; }
      if (FW.gw && FW.gw.enabled === false) return `멈춤 — ${name}: LLM 을 쓸 수 없습니다`;
      if (!fwReviewing()) {
        const materials = k === "plan" ? [...(FW.mats && FW.mats.size ? FW.mats : new Set(FW.gw.materials.filter(fwMatOk).map((m) => m.id)))] : [];
        try { const got = await api(`/api/docs/${id}/form-review`, { method: "POST", headers: H_JSON, body: JSON.stringify({ materials, note: FW.note, duo: fwDuoOn(), ...(k === "plan" ? { planNote: FW.planNote } : {}) }) }); FW.fr = { ...(FW.fr || {}), run: got.run }; }
        catch (e) { return `멈춤 — ${name}: ${e.message || e}`; }
      }
      const w = await wait(() => !fwReviewing(), k === "plan" ? "작성 계획" : "양식 검토");
      if (w) return w;
      if (FW.fr && FW.fr.run && FW.fr.run.state === "failed") return `멈춤 — ${name}: ${FW.fr.run.error || "LLM 이 답하지 못했습니다"}`;
      if (k === "plan" && (FW.fr.open || []).length) { fwWriteOpen("plan"); return `멈춤 — ${name}: 작성 계획을 세웠습니다 — 쓰기 전에 확인할 것 ${FW.fr.open.length}개에 답하세요(「지침 작성」 열의 「작성 계획」 탭 — 답한 뒤 다시 「한 번에 진행」)`; }
      return "";
    }
    if (k === "keep" || k === "extract") {
      if (k === "extract" && s.state === "run") { const w = await wait((X) => X.extract.state !== "run", "자료 추출"); if (w) return w; return ""; }
      if (mats) return ""; // 이 문서의 자료가 이미 있다(에이전트 보기에서 준 파일 · 글 포함) — 올리기 · 추출 없이 넘어간다(줄은 「할 수 있음」 그대로)
      if (fwRefs().only) return `멈춤 — ${name}: ${k === "keep" ? "이 프로젝트의 참조 문서를 고르세요(「참조 문서 고르기」 의 「문서 라이브러리」 탭에서 「이 프로젝트에 넣기」 · 또는 「참조 문서 올리기…」)" : "이 프로젝트의 참조 문서를 문서 라이브러리에서 추출하세요(이 서버는 추출을 시작하지 않습니다)"}`;
      return `멈춤 — ${name}: ${k === "keep" ? "참조 문서를 「참조 문서 올리기…」 로 올리거나 「있는 문서 쓰기」 를 누르세요" : "문서 라이브러리에서 뽑을 범위를 적고 추출하거나 「있는 추출 쓰기」 를 누르세요(이 서버는 추출을 시작하지 않습니다)"}`;
    }
    if (k === "take") { if (mats) return ""; fwTakeOpen(); return `멈춤 — ${name}: 추출한 MD 를 이 문서의 자료로 고르세요(문서 옆 열 「자료 가져오기」)`; }
    if (k === "ask") {
      if (!fwReviewReady()) return `멈춤 — ${name}: ${fwReviewWhy() || "작성 계획이 먼저입니다"}`;
      const places = fwAutoPlaces();
      if (!places.length) { fwWriteOpen("write"); return `멈춤 — ${name}: 채울 자리를 고르세요(「지침 작성」 열의 「초안 작성」 탭 —작성 계획에 자료에서 쓸 것이 있는 자리가 없습니다)`; }
      const materials = [...(FW.mats && FW.mats.size ? FW.mats : new Set(FW.gw.materials.filter(fwMatOk).map((m) => m.id)))], chunks = {};
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
    if (k === "apply") return `멈춤 — ${fwStepRef("apply") || "반영"}: 받은 초안을 에이전트 보기의 제안 카드에서 보고 「문서에 반영」 이나 이 줄의 「모두 반영」 을 누르세요(문서에 넣는 것은 사람이 누를 때만입니다)`;
    if (k === "retidy") { const w = await fwRetidyRun(true); return w ? `멈춤 — ${name}: ${w}` : ""; }
    if (k === "guideFix") { // 검토(유료 LLM)까지는 하고, 고침 제안이 있으면 멈춘다 — 반영은 사람이 고른 것만(양식이 없거나 닿는 지침이 없으면 지나간다)
      const gf = FW.gf;
      if (!gf || !gf.form || !((gf.guides || {}).total)) return "";
      if (!fwGuideFixOpenN()) { const w = await fwGuideFixAsk(true); if (w) return `멈춤 — ${name}: ${w}`; }
      return fwGuideFixOpenN() ? `멈춤 — ${name}: 고침 제안 ${fwGuideFixOpenN()}건 — 이 줄의 「검토 결과 보기」 에서 고른 것을 반영하세요(문서에 넣는 것은 사람이 고른 것만입니다)` : "";
    }
    if (k === "cleanup") { const w = await fwCleanupRun(); return w ? `멈춤 — ${name}: ${w}` : ""; } // 반영 · 정리 뒤에만 여기 온다(앞 줄들이 끝남) — 스크립트 · 실행 취소 1 // 반영한 초안이 있을 때만 여기 온다(앞 줄 apply 가 끝남) — 스크립트 · 실행 취소 1
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
function fwPlanPlaces() { // 작성 계획(LLM)이 고른 자리 — 계획이 「자료에서 쓸 것」 을 적은 자리(이미 채운 줄 · 쓸 자리가 아래 상자에 있는 헤딩은 뺌 — 「모두 고르기」 와 같은 걸름)
  const ps = (FW.gw && FW.gw.places) || [], most = (FW.gw && FW.gw.limits && FW.gw.limits.places) || 40, ok = (p) => p.slot !== "filled" && !(p.kind === "head" && p.boxed && !p.slot);
  const plan = (fwPlanned() && FW.fr.review.places) || {};
  const all = ps.filter((p) => ok(p) && plan[p.id] && plan[p.id].use).map((p) => p.id);
  if (all.length <= most) return all;
  // 한 번에 돌릴 수 있는 수를 넘는 긴 양식 — 아직 안 돌린 자리부터(전에는 늘 앞의 n곳이라 뒤의 자리가 영영 「안 돌린 자리」 로 남았다: astra R2) · 문서 차례는 그대로
  const tried = new Set(((FW.cov && FW.cov.rows) || []).filter((r) => r.tried).map((r) => r.id)), first = all.filter((i) => !tried.has(i)), pick = new Set([...first, ...all.filter((i) => tried.has(i))].slice(0, most));
  return all.filter((i) => pick.has(i));
}
function fwAutoPlaces() { // 초안을 받을 자리 — 「지침 작성」 열에 골라져 있는 자리(작성 계획이 고른 것 · 사람이 고친 것), 없으면 작성 계획이 고른 자리
  const ps = (FW.gw && FW.gw.places) || [], most = (FW.gw && FW.gw.limits && FW.gw.limits.places) || 40;
  if (FW.picks.size) return ps.filter((p) => FW.picks.has(p.id)).map((p) => p.id).slice(0, most);
  return fwPlanPlaces();
}
// 채울 자리의 처음 값 = 작성 계획(LLM)이 고른 자리(2026-11-27 사용자 「초안 작성할 때도 LLM 이 선택해야 하는거 아니냐?」 — 전에는 사람이 체크해야만 초안을 받았다 · spec_양식작성 ② §6-4 「채울 자리 — 작성 계획이 고름」).
// 계획마다 한 번(pickPlan = 그 계획의 때) · 사람이 체크를 고친 뒤(pickBy "human")에는 덮지 않는다 — 「작성 계획대로」 단추가 되돌린다.
function fwPickSeed(force = false) {
  if (!fwPlanned() || !FW.gw) return false;
  const rv = FW.fr.review, sig = String(rv.at || rv.sig || "plan");
  if (!force && (FW.pickBy === "human" || FW.pickPlan === sig)) return false;
  FW.picks = new Set(fwPlanPlaces()); FW.pickBy = "plan"; FW.pickPlan = sig;
  return true;
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
  if (S.open.always) { const top = el("div", "dash-acts"); top.append(...S.open.always); docs.append(top); } // 참조 문서 수 + 「참조 문서 목록」(대시보드 카드의 접어도 보이는 줄과 같은 것)
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
    det.open = open.has(g.id) || (here && !nowSeen) || !!L.subs[g.id]; // 확인 줄(「N단계 초기화」 를 누른 묶음)은 접힌 묶음에서도 보이게 편다
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
    lose: "문서 구조 분석 · 04에 첨부한 샘플·추가 서식 · 04의 보완 결과(구조 판정 · 자리별 작성 지침) · 작성 지침 저장본 · 양식 검토(찾을 테마 · 확인할 것의 답) · 작성 계획 · 받은 초안 · 문서에 반영한 글과 고친 문단", keep: "올린 원본 · 이 문서의 자료 · 확정 기록 · 작업 기록 · 문서 라이브러리의 문서와 추출" },
  material: { name: "자료 준비", head: "이 문서의 자료를 모두 비웁니다",
    lose: "이 문서로 가져온 자료(추출한 MD · 에이전트 보기에서 준 파일 · 글)", keep: "이 프로젝트에 고른 참조 문서(프로젝트의 것 — 빼려면 「참조 문서 목록」 에서 「빼기」) · 문서 라이브러리의 문서와 추출(그 서버의 것 — 다시 가져올 수 있습니다) · 분석 · 양식 검토 · 받은 초안 · 문서. 자료가 바뀌니 「작성 계획 세우기」 는 다시 해야 합니다" },
  write: { name: "작성", head: "초안 · 작성 계획을 비우고 문서를 올린 원본으로 되돌립니다",
    lose: "작성 계획 · 받은 초안(에이전트 대화 · 제안 카드) · 문서에 반영한 글 · 반영한 뒤 서식 정리 · 지침 검토 · 수정의 검토 결과와 반영한 고침 · 작성 지침 · 샘플 지우기와 그 밖에 고친 문단(확정한 것이 있으면 「올린 원본으로 복원」 확정을 하나 더합니다)", keep: "문서 구조 분석 · 작성 지침 · 양식 검토(찾을 테마) · 확인할 것에 정한 답 · 이 문서의 자료" },
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
  acts.append(dashBtn("취소", () => { FW.rs = ""; fwAutoRedraw(); }, { disabled: !!FW.rsBusy, title: "초기화하지 않고 닫습니다", focus: "fwreset:close" }));
  box.append(acts);
  return box;
}
async function fwStageReset(st) { // st = open(준비 — 자료만 남기고 올린 직후로) · material · write (전체 = 대시보드 맨 아래 「전체 초기화…」 — 여기를 지나지 않는다)
  if (FW.rsBusy || !state.id) return;
  const id = state.id, name = fwStageName(st), T = FW_STAGE_RESET[st];
  if (st === "open") { // 작업 내용 초기화와 같은 길(dashResetRun → workReset → 다시 열고 첫 분석: dashResetDone) — 자료만 남긴다(keep) · 글은 이 단계의 이름으로(say)
    FW.rs = "";
    return dashResetRun(dashResetState(), [{ id, label: name, name: state.name || "", opt: { keep: "materials" } }], { redraw: () => fwAutoRedraw(), done: dashResetDone,
      say: { name: `${name} 초기화`, ok: () => `${name} 초기화 — ${T.head.replace("되돌립니다", "되돌렸습니다")}`, bad: (bad) => `초기화하지 못했습니다 — ${bad.join(" / ")}` } });
  }
  FW.rsBusy = st;
  fwAutoRedraw(); // 「초기화 중…」 — 대시보드 + 「작업 개요」
  try {
    if (st === "write") await flushAll(); // 치던 글을 먼저 보낸다(되돌린 뒤에 늦게 닿지 않게)
    const r = await api(`/api/docs/${id}/form-write/reset`, { method: "POST", headers: H_JSON, body: JSON.stringify({ stage: st }) });
    FW.rs = "";
    if (st === "write" && state.id === id) await load(id, { tab: $("panel").dataset.tool || "Dash" }); // 문서가 올린 원본으로 — 다시 연다(보던 탭에 머문다)
    toast(st === "material" ? `${name} 초기화 — 자료 ${r.materials}개를 비웠습니다` : `${name} 초기화 — 초안 ${r.turns}개${r.plan ? " · 작성 계획" : ""}을 비우고${r.reverted ? " 문서를 올린 원본으로 되돌렸습니다" : " 문서는 올린 원본 그대로입니다"}`);
  } catch (e) { toast(`${name} — 초기화하지 못했습니다: ${e.message}`, true); }
  FW.rsBusy = "";
  if (state.id === id) { FW.at = 0; FW.picks = new Set(); FW.pickBy = ""; FW.pickPlan = ""; FW.mats = null; await fwRead(true); if (typeof agentLoad === "function") agentLoad(); fwRedraw(); dashDraw(true); } // fwRedraw 가 「작업 개요」 도 다시 그린다(fwOvSync)
  else fwAutoRedraw(); // 도는 사이 다른 문서를 열었다 — 그 문서의 두 보기에서 꺼 둔 단추(FW.rsBusy)를 푼다
}

// ---- 2열 「자료 가져오기」 -------------------------------------------------------------------------------------------------
const FW_HELP_TAKE = "문서 라이브러리(따로 선 서버)에서 끝난 자료 추출의 MD 를 이 문서의 자료로 가져옵니다. 가져온 자료는 에이전트 보기의 자료와 같은 곳에 놓여 「지침 작성」 과 에이전트 요청이 함께 씁니다.\n"
  + "탭 「이 프로젝트」 = 이 프로젝트에 고른 참조 문서의 추출만 — 가져오고 쓰는 것은 이것뿐입니다. 탭 「문서 라이브러리」 = 모든 문서의 추출(보기만) — 쓰려면 문서 이름 옆 「이 프로젝트에 넣기」.\n"
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
      if (m.outside) { const t = el("span", "fw-tag warn", "프로젝트 밖 — 쓰지 않음"); t.title = "이 프로젝트의 참조 문서가 아닌 문서에서 가져온 자료입니다 — 작성 계획 · 초안에 쓰지 않습니다(그 문서를 「이 프로젝트에 넣기」 하면 다시 씁니다)"; info.append(sr(" · "), t); }
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
  const R = fwRefs();
  if (R.only) body.append(fwRefTabsEl(fwTakeDraw));
  const onP = R.only && FW.refTab !== "lib";
  const have = (eid) => mats.some((m) => (m.note || "").includes(`(${eid})`));
  const withX = docs.filter((d) => (d.extracts || []).length && (!onP || R.ids.has(d.id)));
  if (!withX.length) {
    const inP = docs.filter((d) => R.ids.has(d.id)).length;
    body.append(stateBox(
      onP ? (inP ? "is-noext" : "is-empty") : docs.length ? "is-noext" : "is-empty",
      onP ? (inP ? `이 프로젝트의 참조 문서 ${inP}개에 끝난 자료 추출이 없습니다 — 문서 라이브러리에서 뽑을 범위를 적고 추출하세요.` : "이 프로젝트에 고른 참조 문서가 없습니다 — 「문서 라이브러리」 탭에서 「이 프로젝트에 넣기」 를 누르세요.")
      : docs.length
        ? "끝난 자료 추출이 없습니다 — 문서 라이브러리에서 뽑을 범위를 적고 추출하세요."
        : "문서 라이브러리에 자료 문서가 없습니다 — 「문서 라이브러리 열기」 로 문서를 올리세요.",
    ));
    return;
  }
  // 「모두 가져오기」(2026-11-27 — spec_양식작성 ② §5-12 11): 쓸 수 있는 문서(이 프로젝트의 참조 문서)의 끝난 추출 가운데 아직 안 가져온 것을 **추출 id 로** 차례로 가져온다(「가장 최근」 으로 고르지 않는다)
  const fresh = withX.filter((d) => fwRefIn(d.id)).flatMap((d) => d.extracts.filter((e) => !have(e.id)).map((e) => e.id));
  if (fresh.length > 1) {
    const bar = el("div", "fw-pad fw-t-all");
    bar.append(hBtn(FW.takingAll ? "가져오는 중…" : `${R.only ? "이 프로젝트의 " : ""}새 추출 ${fresh.length}개 모두 가져오기`, () => fwTakeAll(fresh), { cls: "btn sm primary fw-t-takeall", disabled: !!FW.takingAll,
      title: "아직 안 가져온 끝난 추출의 MD 를 차례로 이 문서의 자료로 가져옵니다(자료는 30개까지 — 넘으면 멈추고 알립니다)" }));
    body.append(bar);
  }
  for (const d of withX) {
    const gotN = d.extracts.filter((e) => have(e.id)).length, allGot = gotN === d.extracts.length;
    const sec = el("section", `fw-doc${allGot ? " is-all-got" : ""}`), h = el("h3", "fw-t-doc-head");
    const name = el("span", "fw-t-doc-name", d.name);
    name.title = d.name;
    const cnt = el("span", `fw-t-doc-cnt${allGot ? " is-all" : gotN ? " is-part" : ""}`, gotN ? `${gotN}/${d.extracts.length} 가져옴` : `${d.extracts.length}개`);
    h.append(name, cnt);
    const usable = fwRefIn(d.id);
    if (R.only && !onP) { h.append(fwRefBtn(d)); if (!usable) sec.classList.add("fw-ref-out"); }
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
      const take = hBtn(got ? "가져옴" : "가져오기", () => fwTake(e.id), { disabled: got || !usable, cls: "btn sm fw-t-take" + (got ? " is-got" : usable ? " primary" : ""),
        title: got ? "이미 이 문서의 자료입니다" : usable ? "이 추출의 MD 를 이 문서의 자료로 가져옵니다" : "이 프로젝트의 참조 문서가 아닙니다 — 문서 이름 옆 「이 프로젝트에 넣기」 를 누른 뒤 가져옵니다" });
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
async function fwTakeAll(eids) { // 고른 추출 id 들을 차례로 — 하나라도 못 가져오면 거기서 멈추고 알린다(자료 한도 · 그 서버가 꺼짐)
  if (FW.takingAll || !state.id) return;
  FW.takingAll = true; fwTakeDraw();
  const id = state.id;
  let ok = 0, bad = "";
  try {
    for (const eid of eids) {
      if (state.id !== id) break;
      try {
        const got = await api(`/api/docs/${id}/agent/material/library`, { method: "POST", headers: H_JSON, body: JSON.stringify({ extract: eid }) });
        if (FW.mats) FW.mats.add(got.id);
        ok += 1;
      } catch (e) { bad = e.message || String(e); break; }
    }
  } finally { FW.takingAll = false; }
  if (state.id !== id) return;
  toast(`자료 ${ok}개를 가져왔습니다${bad ? ` — 멈춤: ${bad}` : ""}`, !!bad && !ok);
  if (typeof agentLoad === "function" && typeof AGENT === "object" && AGENT.loaded) agentLoad(true);
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
// ---- 「지침 작성」 열의 탭 — 대시보드 단계마다 하나 ------------------------------------------------------------------------------------------
// 2026-11-26 사용자(대시보드 11 「지침 작성 열기」 를 보며) 「사이드패널에서 뭔가 열리고 선택하라는데 각 도구가 뭘 정확히 어딜 선택하라는건지 알 수가 없어. 탭으로 분리해서 탭을 열어주던가」:
// 전에는 한 열에 05 · 06 · 10 · 11 의 절이 위아래로 섰다 — 탭 하나 = 그 단계의 절만 + 맨 위 「이 탭에서 할 일」(차례 · 끝남 ✓ · 누르면 그 자리로) · 발치의 「작성 초안 받기」 는 초안 작성 탭에만.
// 대시보드의 단추는 제 탭을 연다(fwWriteOpen(탭)). 번호 · 이름은 등록부 차례(fwStepNo — 글에 박지 않는다).
const FW_WTABS = [ // [탭, 대시보드 줄 key, 탭 이름]
  ["guides", "guides", "작성 지침"], ["review", "review", "양식 검토"], ["topics", "review", "찾을 테마"], ["plan", "plan", "작성 계획"], ["write", "ask", "초안 작성"],
];
const fwWGot = () => (((FW.gw && FW.gw.run && FW.gw.run.items) || []).reduce((n, i) => n + (i.proposals || 0), 0));
function fwWTabNow() { // 지금 할 탭 — 양식 검토 → 작성 계획 · 확인할 것 → 초안 작성
  if (!(FW.fr && FW.fr.review)) return "review";
  if (!fwAllAnswered()) return "plan";
  return "write";
}
function fwWTabGo(tab) { // 탭 바꾸기 — 작성 지침 탭은 자리마다 지침을 펼친 채로(전의 fwWriteOpen("guides"))
  FW.wTab = tab;
  FW.guideMode = tab === "guides";
  fwWriteDraw();
  const body = $("headsDlgBody");
  if (body) body.scrollTop = 0;
}
function fwWTabsEl() {
  const fr = FW.fr || {}, rv = fr.review, open = (fr.open || []).length, now = fwWTabNow();
  const tabs = el("div", "fw-tabs fw-w-tabs");
  tabs.setAttribute("role", "tablist");
  for (const [key, step, word] of FW_WTABS) {
    const s = fwStepNo(step), on = key === FW.wTab;
    const mark = key === "review" ? (rv ? ["✓", "is-ok", "양식 검토를 했습니다"] : null)
      : key === "topics" ? (rv && rv.topics && rv.topics.length ? [String(rv.topics.length), "", `찾을 테마 ${rv.topics.length}개`] : null)
      : key === "plan" ? (fwAllAnswered() ? ["✓", "is-ok", "작성 계획을 세우고 확인할 것에 모두 답했습니다"] : fwPlanned() && open ? [`답 ${open}`, "is-warn", `확인할 것 ${open}개에 답해야 합니다`] : null)
      : key === "write" ? (fwWGot() ? ["✓", "is-ok", `초안 ${fwWGot()}개를 받았습니다`] : null) : null;
    const b = hBtn("", () => { if (FW.wTab !== key) fwWTabGo(key); }, { cls: `fw-tab fw-w-tab${on ? " is-on" : ""}${key === now ? " is-now" : ""}`,
      title: `${s ? `대시보드 「${s.no} ${s.name}」 — ` : ""}${FW_WTAB_SAY[key]}${key === now ? "\n← 지금 할 탭" : ""}` });
    if (s) b.append(el("span", "fw-wt-no", s.no));
    b.append(el("span", null, word));
    if (mark) { const m = el("span", `fw-wt-mark ${mark[1]}`.trim(), mark[0]); m.title = mark[2]; b.append(m); }
    b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(on)); b.dataset.tab = key;
    tabs.append(b);
  }
  return tabs;
}
const FW_WTAB_SAY = {
  guides: "자리마다 글을 쓰는 LLM 이 읽는 작성 지침을 보고, 모자란 헤딩에 지침을 적습니다(선택 · 문서는 안 바뀜)",
  review: "양식 전체를 읽고 무엇을 써야 하는지 검토합니다(자료는 읽지 않음 · 유료 LLM · 문서는 안 바뀜)",
  topics: "양식 검토가 뽑은 「자료에서 찾을 테마 · 키워드」 를 골라 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사합니다",
  plan: "자료(MD)를 고르고 작성 계획을 세운 뒤 확인할 것에 답합니다(유료 LLM · 문서는 안 바뀜)",
  write: "채울 자리는 작성 계획이 골라 둡니다(바꾸려면 체크) · 「작성 초안 받기」 — 초안은 에이전트 보기의 제안 카드로 나오고 「문서에 반영」 을 눌러야 문서가 바뀝니다",
};
function fwFlash(sel) { // 「할 일」 줄을 누르면 — 그 자리로 굴리고 잠깐 테두리
  const body = $("headsDlgBody"), t = typeof sel === "string" ? document.querySelector(sel) : sel;
  if (!t) return;
  if (body && body.contains(t)) body.scrollTop = Math.max(0, t.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop - 44); // 44 = 붙어 있는 탭 줄
  else t.scrollIntoView({ block: "nearest" });
  t.classList.add("fw-flash");
  setTimeout(() => t.classList.remove("fw-flash"), 1400);
  if (t.matches("textarea, input[type=text]")) t.focus();
}
function fwTodoEl(items, next) { // 「이 탭에서 할 일」 — items = [{t, done, opt, st, go}] · 지금 = 끝나지 않은 첫 필수 줄 · next = [탭, 글] — 다 했을 때 다음 탭 단추
  const box = el("div", "fw-todo"), head = el("div", "fw-todo-head", "이 탭에서 할 일");
  box.append(head);
  const nowAt = items.findIndex((x) => !x.done && !x.opt);
  items.forEach((x, i) => {
    const b = el("button", `fw-todo-i${x.done ? " is-done" : ""}${i === nowAt ? " is-now" : ""}${x.opt ? " is-opt" : ""}`);
    b.type = "button";
    b.append(el("span", "fw-todo-n", x.done ? "✓" : String(i + 1)), el("span", "fw-todo-t", x.t), el("span", "fw-todo-st", x.st || (x.done ? "" : i === nowAt ? "← 지금" : x.opt ? "선택" : "")));
    if (x.go) b.addEventListener("click", x.go); else b.disabled = true;
    box.append(b);
  });
  if (next && nowAt < 0) {
    const s = fwStepNo((FW_WTABS.find((w) => w[0] === next[0]) || [])[1] || "");
    box.append(hBtn(`다음 — ${s ? `${s.no} ` : ""}${next[1]} 탭으로 →`, () => fwWTabGo(next[0]), { cls: "btn sm primary fw-todo-next" }));
  }
  return box;
}
function fwWTodo(tab) {
  const fr = FW.fr || {}, rv = fr.review, gw = FW.gw || {}, open = (fr.open || []).length, n = FW.picks.size, got = fwWGot();
  const mats = FW.mats ? FW.mats.size : 0, hasMats = !!(gw.materials || []).length;
  const goPlan = () => fwWTabGo("plan");
  if (tab === "review") return fwTodoEl([
    { t: "이번 작성의 지침 적기 — 사람의 요청", opt: true, done: !!String(FW.note || "").trim(), go: () => fwFlash("#headsDlgBody .fw-note") },
    { t: "「양식 검토」 누르기", done: !!rv, st: fwReviewing() && fwRunKind(fr.run) === "review" ? "검토 중…" : "", go: () => fwFlash("#headsDlgBody .fw-review-sec .fw-rev-act") },
  ], ["plan", "작성 계획"]);
  if (tab === "topics") return fwTodoEl([
    { t: "찾을 테마 고르기(줄 앞 체크)", done: !!FW.topicOn.size, go: () => fwFlash("#headsDlgBody .fw-topics .fw-top") },
    { t: "범위 앞에 붙일 말 적기 — 기관 · 연구 · 기간", opt: true, done: !!fwLead(), go: () => fwFlash("#headsDlgBody .fw-top-lead") },
    { t: "「고른 것 복사」 → 문서 라이브러리의 「뽑을 범위」 에 붙여 넣기", done: false, opt: true, go: () => fwFlash("#headsDlgBody .fw-top-copy-top") },
  ]);
  if (tab === "plan") return fwTodoEl([
    { t: hasMats ? `양식에 넣을 자료(MD) 고르기 — ${mats}개 고름` : "자료 가져오기 — 이 문서에 자료(MD)가 없습니다", done: !!mats, go: () => hasMats ? fwFlash("#headsDlgBody .fw-mats") : fwTakeOpen() },
    { t: "「작성 계획 세우기」 누르기", done: fwPlanned(), st: fwReviewing() && fwRunKind(fr.run) === "plan" ? "세우는 중…" : "", go: () => fwFlash("#headsDlgBody .fw-plan-sec .fw-rev-act") },
    { t: fwPlanned() && open ? `확인할 것에 답하기 — ${open}개 남음` : "확인할 것에 답하기", done: fwAllAnswered(), go: () => fwFlash("#headsDlgBody .fw-plan-sec .fw-q.is-open, #headsDlgBody .fw-plan-sec .fw-q-head") },
  ], ["write", "초안 작성"]);
  if (tab === "guides") return fwTodoEl([
    { t: "자리마다 「작성 지침」 보기(펼쳐 둠)", opt: true, done: false, go: () => fwFlash("#headsDlgBody .fw-places-sec") },
    { t: "지침이 없거나 모자란 헤딩에 그 자리의 칸에 적기 · 표는 문서에서 그 표의 「지침」 단추", opt: true, done: false, go: () => fwFlash("#headsDlgBody .fw-gnote") },
  ], null);
  const box = [...FW.picks].map((id) => ((gw.places || []).find((p) => p.id === id) || {})).filter((p) => p.kind === "box");
  return fwTodoEl([
    { t: fwAllAnswered() ? `작성 계획 · 확인할 것 — 자료 ${mats}개` : fwReviewReady() ? `작성 계획 · 확인할 것 — 답하지 않은 물음이 닿는 자리는 초안을 받지 않습니다(「작성 계획」 탭)` : "작성 계획 · 확인할 것 — 「작성 계획」 탭에서 먼저", done: fwAllAnswered(), go: goPlan },
    // 자리는 작성 계획(LLM)이 골라 둔다(fwPickSeed) — 사람은 바꿀 때만 체크를 고친다
    { t: n && FW.pickBy === "plan" ? `채울 자리 — 작성 계획이 ${n}곳 고름(바꾸려면 아래 체크)` : n ? `채울 자리 — ${n}곳 고름` : fwPlanned() ? "채울 자리 고르기 — 작성 계획에 자료에서 쓸 것이 있는 자리가 없습니다 · 아래 목록에서 체크" : "채울 자리 — 작성 계획을 세우면 계획이 고릅니다",
      done: !!n, go: () => fwFlash("#headsDlgBody .fw-places-sec .fw-place") },
    ...(box.length ? [{ t: `상자 자리는 「쓸 자리 고르기」 에서 쓸 덩이 확인 — ${box.length}곳`, opt: true, done: false, go: () => fwFlash("#headsDlgBody .fw-places-sec .fw-chunks") }] : []),
    { t: "맨 아래 「작성 초안 받기」 누르기", done: !!got, st: fwRunning() ? "받는 중…" : "", go: () => fwFlash("#headsDlgFoot button:last-child") },
    { t: "에이전트 보기의 제안 카드에서 「문서에 반영」", done: !!fwAppliedN(gw.run), go: () => toolShown("Agent") && showTab("Agent") },
  ]);
}
async function fwWriteOpen(at = "") { // at = 탭(guides · review · topics · plan · write — FW_WTABS) · 없으면 지금 할 탭(fwWTabNow)
  fwClearWay();
  FW.wTab = FW_WTABS.some((w) => w[0] === at) ? at : "";
  FW.guideMode = at === "guides";
  const { tools, body } = headsDlg("fwWrite", "지침 작성", "자리마다 작성 지침 + 자료 → 초안 · 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  const take = hBtn("자료 가져오기", () => fwTakeOpen(), { title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로" });
  take.dataset.fwTake = "1"; // 자료가 없으면 fwWriteDraw 가 파란 단추로(대시보드의 「지금」 = 자료 가져오기와 같은 단추)
  tools.append(take, hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("지침 작성 안내", FW_HELP_WRITE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await Promise.all([fwRead(true), typeof dashRegLoad === "function" ? dashRegLoad() : null]); // 등록부 = 탭 · 절마다의 단계 번호(fwStepNo — 대시보드와 같은 셈)
  if (!FW.wTab) FW.wTab = fwWTabNow();
  fwWriteDraw();
  body.scrollTop = 0;
  fwReviewPoll(); // 검토가 도는 중이면 끝날 때까지 따라간다
}
// ---- 양식 검토 — 양식 전체를 읽고 어떻게 쓸지 · 쓰기 전에 사람이 확인할 것을 묻는다(form_review_api — spec_양식작성 ② §5-1) -----------------------
// 2026-11-24 사용자 "양식을 전부 읽고 어떻게 작성해야할지 검토한다, 그리고 사용자가 문서를 제공하면 작성하는데,, 이전에 사용자가 정해줄 내용을 물어 본다". 「작성 초안 받기」 는 검토 · 작성 계획이 있어야 돈다(서버도 409) — 2026-11-27 부터 답하지 않은 물음은 그 물음이 닿는 자리만 막는다(spec ② §5-12 6 · 「한 번에 진행」 은 답이 남으면 멈춘다).
const FW_SKIP = "자료대로"; // form_review.SKIP — 「따로 정하지 않음 · 자료에 있는 대로」
const fwPlanned = () => !!(FW.fr && FW.fr.review && FW.fr.planned); // 작성 계획 = 자료를 주고 한 검토(자리마다 자료에서 쓸 것 · 자료에 없는 것)
// 답하지 않은 「확인할 것」 은 **그 물음이 닿는 자리만** 막는다(2026-11-27 — spec_양식작성 ② §5-12 6: 전에는 물음 하나가 모든 자리의 초안을 막았다). 서버의 held = {자리 id: [물음 글]} — 못 읽었으면(옛 서버) 전처럼 물음이 남으면 모두 막힌 것으로
const fwHeld = () => (FW.fr && FW.fr.held && typeof FW.fr.held === "object" ? FW.fr.held : null);
const fwHeldAll = (ids) => { const h = fwHeld(), open = (FW.fr && FW.fr.open) || []; return h ? !!ids.length && ids.every((i) => (h[i] || []).length) : !!open.length; };
const fwIdleN = () => (FW.cov && FW.cov.counts && FW.cov.planned ? FW.cov.counts.idle || 0 : 0); // 작성 계획이 고른 자리 가운데 아직 안 돌린 자리(덮임 — 서버가 턴 기록에서 센다)
const fwReviewReady = () => fwPlanned() && !fwHeldAll(fwAutoPlaces()); // 초안을 받을 수 있나(고른 자리가 모두 막히지는 않음)
const fwAllAnswered = () => fwPlanned() && !((FW.fr && FW.fr.open) || []).length; // 작성 계획이 있고 확인할 것에 모두 답했나(탭의 ✓ · 할 일 목록 — 「받을 수 있나」 와 다르다)
function fwReviewWhy() {
  const fr = FW.fr;
  if (!fr || !fr.review) return fwReviewing() ? "양식 검토 중 — 끝나면 확인할 것을 묻습니다" : "먼저 「양식 검토」 를 하세요";
  if (!fr.planned) return fwReviewing() ? "작성 계획을 세우는 중 — 끝나면 확인할 것을 묻습니다" : "자료를 고르고 「작성 계획 세우기」 를 하세요";
  return fwHeldAll(fwAutoPlaces()) && (fr.open || []).length ? `쓰기 전에 확인할 것 ${fr.open.length}개에 답하세요` : "";
}
function fwReviewStep(gw) { // 대시보드 「문서 작성 요령 생성 · 찾을 테마」 줄(준비 묶음의 끝 — 자료 준비 앞: 자료 없이 된다) — 양식 검토가 있으면 끝남
  const fr = FW.fr, rv = fr && fr.review, run = fr && fr.run;
  const going = !!(run && run.state === "running"), topics = rv && rv.topics;
  if (gw.hwpx === false) return { state: "", text: "hwpx 문서만 됩니다" };
  if (rv && fr.stale && FW.guidance?.ready) {
    return { state: going ? "run" : "now", text: going ? "바뀐 작성 지침으로 양식을 검토하고 있습니다" : "작성 지침이 바뀌었습니다. 현재 지침으로 양식을 다시 검토하세요.",
      acts: [dashBtn(going ? "검토 중 — 보기" : "다시 검토", () => fwReviewFromDash(going), { primary: !going, focus: "act:review" })] };
  }
  if (!rv) {
    const btn = [dashBtn(going ? "검토 중 — 보기" : "양식 검토", () => fwReviewFromDash(going), { primary: !going, title: "「지침 작성」 열의 「양식 검토」 — 목적 문서의 양식에 무엇을 써야 하는지 · 어떤 작성 지침이 있는지 · 사람의 요청을 검토하고 자료에서 찾을 테마 · 키워드를 뽑습니다(유료 LLM 한 번 · 자료는 읽지 않음 · 문서는 안 바뀜)", focus: "act:review" })];
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
  // 2026-11-25 사용자 「왜 작성 계획 세우기랑 초안 받기가 같이 활성화가 되어 있냐? … 계획 세우기 단계였는데 안맞으면 안됨」 — 계획이 도는 동안 이 줄의 단추가 파란 「작성 계획 세우기」 로 남아 있었다:
  // 도는 동안은 「계획 세우는 중」 (회색 · 열을 열어 진행을 볼 뿐)이고, 「지침 작성」 열 아래 「작성 초안 받기」 도 꺼진 동안은 회색이다(fwFootDraw)
  const going = !!(run && run.state === "running" && (run.materials || []).length); // 양식 검토가 도는 것(자료 없음)은 이 줄의 일이 아니다
  const btn = [going ? dashBtn("계획 세우는 중 — 보기", () => fwWriteOpen("plan"), { title: "「지침 작성」 열의 「작성 계획 · 확인할 것」 — 고른 자료를 읽고 작성 계획을 세우는 중입니다. 끝나면 확인할 것을 묻습니다", focus: "act:plan" })
    : dashBtn(!planned ? "작성 계획 세우기" : "계획 · 물음 보기", () => fwWriteOpen("plan"), { primary: !!rv && ((!planned && !!mats) || !!open.length), title: "「지침 작성」 열의 「작성 계획 · 확인할 것」 —양식에 넣을 내용의 자료(MD)를 고르고 자리마다 자료의 무엇을 쓸지 계획을 세우고, 확인할 것에 답합니다(유료 LLM · 문서는 안 바뀜)", focus: "act:plan" })];
  if (going) return { state: "run", text: "고른 자료를 읽고 작성 계획을 세우는 중(1~3분)", acts: btn };
  if (!rv) return { state: "todo", text: "양식 검토 뒤에 세웁니다", acts: btn };
  const n = rv.questions.length, pl = Object.values(rv.places || {});
  if (!planned) return { state: mats ? "now" : "todo", text: mats ? "작성 계획 전 — 양식에 넣을 내용의 자료(MD)를 고르고(LLM 에 줄 요청은 그 절의 「작성 계획에 줄 요청」 칸에) 「작성 계획 세우기」 를 누릅니다" : "자료를 가져오면 계획을 세웁니다", acts: btn };
  return { state: open.length ? "now" : "done", text: `작성 계획 — 자료에서 쓸 자리 ${pl.filter((x) => x.use).length}곳 · 자료에 없는 것이 있는 자리 ${pl.filter((x) => x.gap).length}곳 · ${open.length ? `확인할 것 ${open.length}개가 남았습니다` : n ? `확인할 것 ${n}개 모두 답함` : "확인할 것이 없습니다"}${rv.planRequest ? " · 사람의 요청을 넣어 세움" : ""}`, acts: btn };
}
// 대시보드 06 의 단추 — 열을 열고(진행 · 결과를 보이려고) 바로 양식 검토를 시작한다(확인 창 하나). 2026-11-26 사용자 「양식 검토를 누르면 바로 실행이 안되고 옆에 사이드 패널이 뜨고 사이드 패널에서 다시 클릭해야 실행이 되냐?」 —
// 전에는 열만 열고 열 안의 「양식 검토」 를 또 눌러야 했다. 도는 중이면 열만 연다. 열을 먼저 여는 까닭 = 「이번 작성의 지침」 의 처음 값을 fwRead 가 채운 뒤에 보낸다
async function fwReviewFromDash(going) {
  await fwWriteOpen("review");
  if (!going && !fwReviewing()) fwReviewRun("review");
}
// kind = "review"(양식 검토 — 양식 · 작성 지침 · 사람의 요청만 · 자료는 안 보냄) | "plan"(작성 계획 — 고른 자료 · 양식 검토가 먼저). 한 단추가 두 걸음을 함께 돌리지 않는다
// (2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려 ... 목적문서의 양식에 뭘 작성해야하는지, 어떤 지침이 있는지 사용자가 요청하는건 뭔지를 봐야지」 — 전에는 자료를 고른 채 「양식 검토」 를 누르면 계획까지 했다).
// 두 모델로 협의 — **옵션**(2026-11-27 사용자 「양식 검토의 두 모델 협의 는 옵션으로 둘 수 있고」 — 기본 한 모델 LLM1: spec_양식작성 ② §5-12 1). 처음 값 = 이 문서에 마지막으로 쓴 값(서버 opts.duo) · 둘째 모델이 설정에 없으면 못 켠다(llm2)
const fwDuoOn = () => !!(FW.fr && FW.fr.llm2 && (FW.duo === undefined ? FW.fr.opts && FW.fr.opts.duo : FW.duo));
function fwDuoEl() {
  const fr = FW.fr || {}, lab = el("label", "fw-mat fw-duo"), cb = el("input");
  cb.type = "checkbox"; cb.checked = fwDuoOn(); cb.disabled = !fr.llm2 || fwReviewing();
  cb.addEventListener("change", () => { FW.duo = cb.checked; });
  lab.append(cb, el("span", null, "두 모델로 협의"));
  lab.title = !fr.llm2 ? "둘째 모델(LLM2)이 설정에 없습니다 — LLM 칩에서 「두 모델로」 를 고르면 켤 수 있습니다"
    : "끄면(기본) LLM1 한 모델로 한 번 검토합니다. 켜면 LLM1 · LLM2 가 따로 검토하고 LLM1 이 협의해 하나로 냅니다 — 호출 세 번 · 시간이 두세 배. 양식 검토와 작성 계획이 같이 씁니다(이 문서에 기억)";
  return lab;
}
async function fwReviewRun(kind = "review") {
  const plan = kind === "plan", materials = plan ? [...(FW.mats || [])] : [], duo = fwDuoOn();
  if (plan && !(FW.fr && FW.fr.review)) return toast("먼저 「양식 검토」 를 하세요 — 작성 계획은 양식 검토 뒤에 세웁니다", true);
  if (plan && !materials.length) return toast("양식에 넣을 내용의 자료(MD)를 고르세요 — 작성 계획은 자료로 세웁니다", true);
  const what = plan ? `고른 자료 ${materials.length}개${FW.planNote.trim() ? "와 「작성 계획에 줄 요청」" : ""}을 읽고 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획하고 확인할 것을 묻습니다(양식 검토의 결과는 그대로 둡니다)`
    : `목적 문서의 양식 · 작성 지침 · 사람의 요청(「이번 작성의 지침」${FW.note.trim() ? "" : " — 비어 있음"})을 읽고 무엇을 써야 하는지 검토합니다. 자료는 읽지 않습니다${fwPlanned() ? ". 세워 둔 작성 계획은 다시 세워야 합니다(답한 것은 남습니다)" : ""}`;
  if (!window.confirm(`유료 LLM ${duo ? "세 번(두 모델 + 협의 · 2~6분)" : "한 번(1~3분)"} — ${what}. 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/form-review`, { method: "POST", headers: H_JSON, body: JSON.stringify({ materials, note: FW.note, duo, ...(plan ? { planNote: FW.planNote } : {}) }) });
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
  fwOvSync(); // 「작업 개요」 의 「작성 계획 · 확인할 것」 줄도(열려 있을 때만)
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
  h.append(el("span", "fw-rev-title", "양식 검토"), actBtn, fwDuoEl());
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
  // 추출 전에 정할 것 — 양식 검토는 **범위 물음**(무엇을 추출할지를 바꾸는 물음)만 낸다(2026-11-27 spec_양식작성 ② §5-12 6): 답을 보고 자료 문서에서 뽑을 범위를 정한다. 그 밖의 물음은 자료를 읽은 뒤 「작성 계획」 에서
  const scope = (rv.questions || []).filter((q) => q.kind === "scope");
  if (scope.length || rv.deferred) {
    const qh = el("div", "fw-q-head fw-q-head-scope");
    qh.textContent = scope.length ? `자료를 뽑기 전에 정할 것 ${scope.length}개 — 이 답으로 뽑을 범위(기관 · 차년도 · 계획/실적)를 정합니다` : "자료를 뽑기 전에 정할 것이 없습니다";
    sec.append(qh);
    scope.forEach((q, i) => sec.append(fwQBox(q, i + 1, fr)));
    if (rv.deferred) sec.append(el("div", "fw-muted fw-pad fw-rev-msg", `자료를 읽어야 물을 수 있는 것 ${rv.deferred}개는 자료를 가져온 뒤 「작성 계획」 에서 묻습니다.`));
  }
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
    title: !fr.enabled ? "LLM 을 쓸 수 없습니다" : !rv ? "먼저 「양식 검토」 탭에서 양식 검토를 하세요 — 작성 계획은 양식 검토 뒤에 세웁니다" : !hasMats ? "작성 계획은 자료로 세웁니다 — 먼저 열 머리의 「자료 가져오기」 로 이 문서의 자료를 가져오세요"
      : "고른 자료(MD)를 읽고 자리마다 자료의 무엇을 쓸지 · 자료에 없는 것을 계획하고 확인할 것을 묻습니다 — 양식 검토의 결과는 그대로 둡니다 · 유료 LLM 한 번 · 문서는 바뀌지 않습니다. 다시 해도 답한 것은 남습니다",
  });
  h.append(el("span", "fw-rev-title", "작성 계획 · 확인할 것"), actBtn, fwDuoEl());
  fwHead(h, [["run", "plan"]]);
  h.append(steps);
  sec.append(h);
  // 이 단계(LLM)에만 줄 요청 — 2026-11-25 사용자(대시보드 10 을 보며) 「왜 이건 LLM 프롬프트 입력하는게 없냐」: 06 양식 검토는 맨 위 「이번 작성의 지침」 을 읽지만 작성 계획에는 제 칸이 없었다.
  // 보내는 것 = 작성 계획 실행의 planNote(서버 form_review_api — 프롬프트의 planRequest · 검토에 planRequest 로 남아 다시 열면 처음 값). 맨 위 「이번 작성의 지침」 도 전처럼 함께 간다
  const pn = el("textarea", "fw-note fw-plan-note");
  pn.rows = 2; pn.maxLength = (FW.gw && FW.gw.limits && FW.gw.limits.note) || 1000; pn.value = FW.planNote;
  pn.placeholder = "작성 계획에 줄 요청(선택) — 예: 2차년도 실적 위주로 · 표는 기관별로 나눠 · 자료가 서로 다르면 최신 자료를 따름";
  pn.setAttribute("aria-label", "작성 계획에 줄 요청");
  pn.disabled = going;
  pn.addEventListener("input", () => { FW.planNote = pn.value; });
  const pnBox = el("div", "fw-plan-req");
  const norm = (t) => String(t || "").split("\n").map((x) => x.split(/\s+/).filter(Boolean).join(" ")).join("\n").trim(); // 서버 form_review.request_text 와 같은 정리
  if (planned && norm(rv.planRequest) !== norm(FW.planNote)) pnBox.append(el("div", "fw-muted", rv.planRequest ? "지금 계획은 다른 요청으로 세웠습니다 — 바꾼 요청은 「다시 세우기」 를 눌러야 반영됩니다" : "지금 계획은 요청 없이 세웠습니다 — 요청은 「다시 세우기」 를 눌러야 반영됩니다"));
  pnBox.prepend(pn);
  sec.append(pnBox);
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
  let qi = 0;
  for (const q of qs) { qi += 1; sec.append(fwQBox(q, qi, fr)); }
  // 같은 이름의 자리가 여럿인 상자 — 「어느 자리에 쓰나」 도 여기서 한 번 묻는다(스크립트가 만든 줄 — 답은 전처럼 그 상자의 「쓸 자리 고르기」: 2026-11-27 spec_양식작성 ② §5-12 6). 작성 계획이 쓸 것을 적었거나 사람이 고른 상자만
  if (planned) for (const p of ((FW.gw && FW.gw.places) || []).filter((x) => x.kind === "box" && (((rv.places || {})[x.id] || {}).use || FW.picks.has(x.id)))) {
    const un = fwUnpicked(p);
    if (!un.length) continue;
    const box = el("div", "fw-q is-open fw-q-slot");
    box.dataset.slotBox = p.id;
    box.append(el("div", "fw-q-text", `쓸 자리 고르기 — 상자 「${p.text}」: ${un.join(" · ")}`),
      el("div", "fw-muted fw-q-why", "같은 이름의 자리가 여럿입니다 — 누구의 자리인지 스크립트가 정하지 않습니다. 고르지 않으면 그 자리는 쓰지 않고 남깁니다."),
      hBtn("쓸 자리 고르기", () => { FW.chunkOpen.add(p.id); fwWTabGo("write"); setTimeout(() => fwFlash(`.fw-chunks input[data-chunk]`), 60); }, { cls: "btn sm", title: "「초안 작성」 탭의 그 상자 줄 — 「쓸 자리 고르기」 에서 같은 이름의 자리 가운데 하나를 고릅니다" }));
    sec.append(box);
  }
  const lostQ = new Set(fr.lost || []), old = dec.filter((x) => !x.stale && !qs.some((q) => q.key === x.key || q.text === x.q)); // lost = 자리를 잃은 답(서버 form_review.lost — 어느 자리의 것인지 몰라 어느 자리에도 싣지 않는다)
  for (const [list, title, cls] of [[old.filter((x) => !lostQ.has(x.q)), (n) => `앞서 정한 것 ${n}개 — 그 답이 닿는 자리의 요청에 함께 갑니다`, ""], [old.filter((x) => lostQ.has(x.q)), (n) => `자리를 못 찾은 답 ${n}개 — 어느 자리에도 쓰지 않습니다`, " fw-rev-lost"]]) {
    if (!list.length) continue;
    const d = el("details", `fw-guides fw-pad fw-rev-free${cls}`); d.append(el("summary", null, title(list.length)));
    for (const x of list) { const li = el("div", "fw-guide"); li.append(el("span", null, `${x.q} → ${x.a}`), hBtn("지우기", () => fwAnswer([{ q: x.q, a: "" }]), { cls: "btn sm fw-rev-del" })); d.append(li); }
    sec.append(d);
  }
  // 이전 답 — 다른 자료로 물었을 때의 답(서버 form_review.mark_stale): 쓰지 않는다. 같은 물음이 지금도 있으면 그 물음의 답 칸에 후보로 보이고(fwQBox), 물음이 없어진 것은 여기에
  const gone = dec.filter((x) => x.stale && !qs.some((q) => q.text === x.q));
  if (gone.length) {
    const d = el("details", "fw-guides fw-pad fw-rev-free fw-rev-stale"); d.append(el("summary", null, `이전 답 ${gone.length}개 — 자료가 바뀌어 쓰지 않습니다`));
    for (const x of gone) { const li = el("div", "fw-guide"); li.append(el("span", null, `${x.q} → ${x.a}`), hBtn("다시 씀", () => fwAnswer([{ q: x.q, a: x.a }]), { cls: "btn sm", title: "이 답을 지금 자료에서도 그대로 씁니다" }), hBtn("지우기", () => fwAnswer([{ q: x.q, a: "" }]), { cls: "btn sm fw-rev-del" })); d.append(li); }
    sec.append(d);
  }
  return sec;
}
const FW_QKIND = { scope: ["범위", "무엇을 추출할지를 바꾸는 물음 — 이 답을 보고 자료 문서에서 뽑을 범위를 정합니다(자료 추출 전에 답합니다)"], content: ["내용", "자료를 읽은 뒤에 묻는 물음 — 기준 · 단위 · 분량 · 자료가 서로 다를 때"] };
function fwQBox(q, qi, fr) { // 물음 하나(답 칸 · 고를 답 · 자료에서 찾은 답 후보 · 이전 답) — 「양식 검토」 절(범위 물음)과 「작성 계획 · 확인할 것」 절이 같이 쓴다
  const dec = fr.decided || [], left = new Set(fr.open || []), sr = (s) => el("span", "fw-sr", s);
  const names = new Map(((FW.gw && FW.gw.places) || []).map((p) => [p.id, p.text]));
  {
    const d = dec.find((x) => !x.stale && (x.key === q.key || x.q === q.text)), isOpen = left.has(q.key); // 이전 답(stale — 다른 자료로 물은 답)은 답이 아니다
    const choices = q.choices || [], places = q.places || [];
    const sugOnlyOn = !!(q.suggest && d && d.a === q.suggest && !choices.includes(q.suggest));
    const chipHit = !!(d && d.a && (choices.includes(d.a) || d.a === FW_SKIP || sugOnlyOn));
    const box = el("div", `fw-q${isOpen ? " is-open" : " is-done"}${!isOpen && d && d.a ? (chipHit ? " is-chip" : " is-custom") : ""}`), input = el("input", "fw-q-input");
    const qText = el("div", "fw-q-text", q.text);
    qText.dataset.num = String(qi);
    box.append(qText);
    if (FW_QKIND[q.kind]) { box.dataset.qkind = q.kind; const k = el("span", `fw-tag fw-q-kind${q.kind === "scope" ? " guide" : ""}`, FW_QKIND[q.kind][0]); k.title = FW_QKIND[q.kind][1]; box.append(k); }
    if (q.why) box.append(el("div", "fw-muted fw-q-why", q.why));
    const prev = isOpen ? (fr.prev || {})[q.key] : ""; // 이전 답 — 다른 자료로 물었을 때의 답(후보로만: 눌러야 답)
    if (prev) {
      const pr = el("div", "fw-q-prev");
      pr.append(el("span", "fw-muted", `이전 답(다른 자료로 물었을 때): ${prev}`), hBtn("그대로 씀", () => fwAnswer([{ key: q.key, a: prev }]), { cls: "btn sm", title: "자료가 바뀌어 다시 묻습니다 — 이전 답을 지금 자료에서도 그대로 쓰려면 누릅니다" }));
      box.append(pr);
    }
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
    return box;
  }
}
// ---- 자료에서 찾을 테마 · 키워드(spec_양식작성 ② §5-2) — 양식 검토가 뽑은 것을 골라, 문서 라이브러리의 「뽑을 범위」 에 붙일 줄로 복사한다 ------------------------------
// 2026-11-24 사용자 "여기서 작성 테마/키워드를 추출해줘 … 그럼 내가 라이브러리에서 이 테마나 키워드로 추출하게.. 테마/키워드 그리고 맥락을 함께 추출하도록 해줘". 8114 는 문서 라이브러리를 읽기만 한다 — 복사 · 범위를 실은 주소로 그 화면 열기까지만(2026-11-27 — 추출은 시작하지 않는다: spec ② §5-12 11).
const FW_SCOPES = 8, FW_SCOPE_MAX = 600; // 문서 라이브러리가 한 번에 받는 범위 수 · 범위 한 줄의 길이(doclib/extract.py)
const fwLead = () => String(FW.lead || "").replace(/\s+/g, " ").trim();
// 탭 둘(2026-11-26 사용자 「작성계획 세우기에서 나온 결과 인지 6번에서 나온 결과 인지 모르잖아. 탭으로 해서 구분하면 좋을듯」): review = 양식 검토가 양식만 읽고 뽑은 것(review.topics) ·
// plan = 작성 계획이 자료까지 읽고 뽑은 것(review.planTopics — 서버 form_review_api._go 가 따로 남긴다). 고른 것(topicOn)은 탭을 바꾸면 비운다(복사는 한 탭에서).
const fwTopicSrc = (tab = FW.topicTab) => { const rv = (FW.fr && FW.fr.review) || {}; return tab === "plan" ? { topics: rv.planTopics, lines: (FW.fr && FW.fr.planTopicLines) || [] } : { topics: rv.topics, lines: (FW.fr && FW.fr.topicLines) || [] }; };
function fwTopicLine(i) { // 복사될 한 줄 — 「<앞말>, <서버가 지은 범위 글>」(앞말이 비면 쉼표 없이 · 줄 나눔 없음)
  const src = fwTopicSrc(), t = (src.topics || [])[i] || {};
  const base = String(src.lines[i] || t.scope || t.name || "").replace(/\s+/g, " ").trim(), lead = fwLead();
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
  if (FW.topicTab !== "plan") FW.topicTab = "review";
  const tab = FW.topicTab, topics = fwTopicSrc().topics, lib = FW.lib || { alive: false }, sec = el("section", "fw-doc fw-topics"), h = el("h3", "fw-places-head");
  h.append(el("span", "fw-top-title", "자료에서 찾을 테마 · 키워드"), hHelp("자료에서 찾을 테마 · 키워드 안내", FW_HELP_TOPICS, { note: true }));
  sec.append(fwHead(h, [["result", tab], ["prep", "extract"]]));
  const tabs = el("div", "fw-pad fw-tabs fw-top-tabs");
  tabs.setAttribute("role", "tablist");
  for (const [key, word, tip] of [["review", fwStepRef("review") || "양식 검토", "양식 검토가 양식만 읽고 뽑은 테마(자료는 안 읽음)"], ["plan", fwStepRef("plan") || "작성 계획", "작성 계획 세우기가 고른 자료까지 읽고 뽑은 테마"]]) {
    const list = fwTopicSrc(key).topics, b = hBtn(`${word}${list && list.length ? ` (${list.length})` : ""}`, () => { if (FW.topicTab === key) return; FW.topicTab = key; FW.topicOn.clear(); fwWriteDraw(); },
      { cls: `fw-tab fw-top-tab${key === tab ? " is-on" : ""}`, title: tip });
    b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(key === tab)); b.dataset.tab = key;
    tabs.append(b);
  }
  sec.append(tabs);
  const none = (msg) => { sec.append(el("div", "fw-muted fw-pad fw-top-msg", msg)); return sec; };
  if (tab === "plan" && !topics) return none(rv.materials && rv.materials.length ? "이 작성 계획은 테마를 따로 남기기 전에 세운 것입니다 — 「작성 계획 세우기」 를 다시 하면 보입니다" : "아직 작성 계획을 세우지 않았습니다 — 자료를 고르고 「작성 계획 세우기」 를 누르면 자료까지 읽고 뽑은 테마가 여기 보입니다");
  if (!topics) return none("아직 뽑지 않았습니다 — 「다시 검토」 로 뽑습니다"); // 오늘 전에 저장한 검토(topics 없음) — 「0개」 가 아니다
  if (!topics.length) return none(tab === "plan" ? "작성 계획이 따로 뽑은 테마가 없습니다" : "찾을 테마가 없습니다");
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
  // 「문서 라이브러리에서 이 범위로 열기」(2026-11-27 — spec_양식작성 ② §5-12 11): 고른 범위 줄을 주소에 실어 그 서버를 연다 — 그 화면이 「뽑을 범위」 칸을 채운다. **추출은 시작하지 않는다**(사람이 그 화면에서 범위를 보고 「추출 시작」 — 8114 는 여전히 읽기 · 올리기뿐)
  const prevBox = el("div", "fw-pad"); prevBox.append(prev);
  const RF = fwRefs(), docs = (lib.docs || []).filter((d) => !RF.only || RF.ids.has(d.id));
  if (lib.alive && docs.length) {
    const sel = el("select", "fw-top-doc");
    sel.setAttribute("aria-label", "범위를 넘길 참조 문서");
    for (const d of docs) { const o = el("option", null, d.name); o.value = d.id; sel.append(o); }
    if (FW.topicDoc && docs.some((d) => d.id === FW.topicDoc)) sel.value = FW.topicDoc;
    sel.addEventListener("change", () => { FW.topicDoc = sel.value; });
    const go = hBtn("문서 라이브러리에서 이 범위로 열기", () => {
      const ls = chosen();
      if (!ls.length) return toast("넘길 테마를 고르세요", true);
      fwLibOpen(`d=${encodeURIComponent(sel.value)}&scope=${encodeURIComponent(ls.join("\n"))}`);
    }, { cls: "btn sm fw-top-open", title: "고른 범위 줄을 실어 문서 라이브러리의 그 문서를 엽니다 — 「뽑을 범위」 칸이 채워집니다. 추출은 그 화면에서 범위를 확인하고 「추출 시작」 을 눌러야 시작됩니다(유료 LLM)" });
    const openRow = el("div", "fw-pad fw-top-openrow");
    openRow.append(el("span", "fw-muted", RF.only ? "이 프로젝트의 참조 문서" : "참조 문서"), sel, go);
    sec.append(prevBox, act, openRow);
  } else sec.append(prevBox, act);
  sync();
  return sec;
}
function fwRedraw() { fwTakeDraw(); fwWriteDraw(); fwRefsDraw(); fwOvSync(); } // fwOvSync = 패널 「작업 개요」(열려 있을 때만)
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
function fwStepRef(key) { const s = fwStepNo(key); return s ? `${s.no} ${s.name}` : ""; } // "05 문서 작성 요령 생성 · 찾을 테마" | ""
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
  ttype:  { word: "테이블 타입", cls: "ok", step: "headsLlm", say: "04 가 이 자리의 표에 밝힌 테이블 타입(본문 · 헤딩 · 그림 · 값 테이블 …) — 타입의 작성 방법은 「작성 지침 보기」 에 있습니다" },
  user:   { word: "사람 지침", cls: "user", step: "guides", say: "사람이 이 자리에 적은 작성 지침이 있음" },
  text:   { word: "글 있음", cls: "", step: "", say: "헤딩 아래에 이미 본문 글이 있음(지금 문서)" },
  draft:  { word: "초안 n", cls: "ok", step: "ask", say: "이 자리에 받은 초안의 수 · 받는 중 · 초안이 없는 까닭(자료에 없음 · 확인할 것 남음 · 검사에서 제외 …)" },
  evid:   { word: "근거 n절", cls: "guide", step: "plan", say: "작성 계획이 이 자리의 근거로 고른 자료의 절 수 — 초안은 그 절과 앞뒤 절만 받아 씁니다(「자료 전체로 다시 받기」 로 넓힙니다)" },
  applied: { word: "반영 n줄", cls: "user", step: "apply", say: "이 자리의 초안 가운데 문서에 반영한 줄(칸) 수" },
  open:   { word: "반영할 줄 n", cls: "ok", step: "apply", say: "열린 초안에서 처음부터 골라진 줄 — 「모두 반영」 이 넣습니다" },
  left:   { word: "남은 줄 n", cls: "warn", step: "apply", say: "초안은 났지만 안 넣은 줄(경고가 있는 줄 · 같은 줄 뒤의 값 · 표시 줄 · 되돌린 줄) — 열린 카드는 에이전트 보기에서 읽고 고르고, 이미 반영한 카드의 남은 줄은 그 자리를 다시 받습니다" },
  old:    { word: "이전 계획의 초안", cls: "warn", step: "plan", say: "이 초안을 받은 뒤 작성 계획을 다시 세웠거나 이 자리에 닿는 답을 고쳤습니다 — 「모두 반영」 에 넣지 않습니다(카드에서 읽고 넣거나 이 자리를 다시 받습니다)" },
  ask:    { word: "확인할 것 n", cls: "warn", step: "plan", say: "이 자리에 닿는 물음에 답하지 않았습니다 — 답할 때까지 이 자리의 초안은 받지 않습니다(다른 자리는 받습니다)" },
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
  if (document.activeElement && ["fw-q-input", "fw-top-lead", "fw-gnote", "fw-plan-note"].some((c) => document.activeElement.classList.contains(c)) && body.contains(document.activeElement)) return void fwFootDraw(foot); // 물음의 답 · 범위 앞에 붙일 말 · 자리 지침을 적는 동안에도
  body.replaceChildren();
  if (!gw) return void body.append(el("div", "fw-empty", FW.err || "읽는 중…"));
  if (gw.hwpx === false) return void body.append(el("div", "fw-empty", "지침 작성은 hwpx 문서만 됩니다."));
  if (!FW_WTABS.some((w) => w[0] === FW.wTab)) FW.wTab = fwWTabNow();
  const tab = FW.wTab;
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
  const all = hBtn("모두 고르기", () => { for (const p of fwShown()) if (p.slot !== "filled" && !(p.kind === "head" && p.boxed && !p.slot)) FW.picks.add(p.id); FW.pickBy = "human"; fwWriteDraw(); }, { title: "보이는 자리를 모두 고릅니다(이미 채운 줄 · 쓸 자리가 아래 상자에 있는 헤딩은 빼고)" }), none = hBtn("모두 해제", () => { FW.picks.clear(); FW.pickBy = "human"; fwWriteDraw(); });
  head.append(el("span", null, `채울 자리 — ${shown.length}곳`), only, all, none);
  if (fwPlanned()) { // 작성 계획(LLM)이 고른 자리로 되돌리기 — 처음 값이 그것이다(fwPickSeed). 사람이 체크를 고친 뒤에만 켜진다
    const planN = fwPlanPlaces().length;
    head.append(hBtn(`작성 계획대로 (${planN})`, () => { fwPickSeed(true); fwWriteDraw(); }, { cls: "btn sm fw-pick-plan", disabled: FW.pickBy !== "human",
      title: FW.pickBy === "human" ? `작성 계획이 「자료에서 쓸 것」 을 적은 자리 ${planN}곳으로 되돌립니다` : `지금 고른 자리가 작성 계획이 고른 것입니다 — 작성 계획이 「자료에서 쓸 것」 을 적은 자리 ${planN}곳(이미 채운 줄은 빼고)` }));
  }
  plSec.append(fwHead(head, [["run", "guides"], ["prep", "ask"]]));
  if (tab === "guides") { // 「작성 지침」 탭(대시보드 「작성 지침 확인 · 적기」) — 자리마다 지침을 펼친 채로
    const tip = el("div", "fw-pad fw-gmode");
    tip.append(el("span", null, FW.guideMode ? "자리마다 「작성 지침」 을 펼쳤습니다 — 양식의 지침을 보고, 없거나 모자란 헤딩에는 그 자리의 칸에 적습니다. 표의 지침은 문서에서 그 표의 「지침」 단추로 적습니다." : "작성 지침을 접었습니다."),
      hBtn(FW.guideMode ? "지침 접기" : "지침 펼치기", () => { FW.guideMode = !FW.guideMode; fwWriteDraw(); }, { cls: "btn sm" }));
    plSec.append(tip);
  }
  if (!shown.length) plSec.append(el("div", "fw-empty", gw.places.length ? "작성 지침이 붙은 자리가 없습니다 — 「작성 지침이 있는 자리만」 을 끄면 모든 헤딩이 보입니다. 헤딩에 지침을 적으려면 문서에서 그 헤딩의 「지침」 단추를 씁니다." : "본문 헤딩이 없습니다 — 헤딩 추출(기본 분석)이 끝났는지 확인하세요."));
  const ran = new Map(((gw.run && gw.run.items) || []).map((i) => [i.id, i]));
  for (const p of shown) plSec.append(fwPlaceEl(p, ran.get(p.id), foot));
  const legend = fwLegendEl(new Set([...plSec.querySelectorAll(".fw-place-main > .fw-tags > [data-tag]")].map((t) => t.dataset.tag))); // 보이는 꼬리표의 뜻 · 나온 단계
  if (legend) plSec.append(legend);
  // 탭마다 그 단계의 절만(fwWTabsEl — 2026-11-26): 「이번 작성의 지침」 은 양식 검토가 읽고 초안 요청에도 함께 가서 두 탭에 같은 값으로 선다 · 자료 고르기는 작성 계획 탭에만(초안은 계획 때의 자료로만 받는다 — form_review_api.fresh)
  const topics = tab === "topics" ? fwTopicsEl() || el("div", "fw-empty", "양식 검토를 하면 찾을 테마가 여기 보입니다 — 「양식 검토」 탭") : null;
  const parts = { review: [noteSec, fwReviewEl()], topics: [topics], plan: [matSec, fwPlanEl()], guides: [plSec], write: [noteSec, plSec] }[tab];
  body.append(fwWTabsEl(), fwWTodo(tab), ...parts.filter(Boolean));
  body.scrollTop = keep;
  fwFootDraw(foot);
}
const FW_ITEM = { queued: ["기다림", ""], running: ["받는 중", "run"], done: ["초안", "ok"], none: ["초안 없음", ""], failed: ["실패", "fail"], skipped: ["안 함", ""], cut: ["끊김", "fail"] }; // cut = 서버를 다시 켜 끊긴 실행의 자리
const FW_NONE = { dropped: "검사에서 제외", noslot: "쓸 자리 안 고름", filled: "채운 줄", ask: "확인할 것 남음", nomat: "자료에 없음", noaction: "초안 없음" }; // 초안이 0개인 자리의 꼬리표(까닭 — FW_WHY 의 짧은 꼴)
const fwCovOf = (id) => ((FW.cov && FW.cov.rows) || []).find((r) => r.id === id) || null; // 그 자리의 덮임(서버 guide_write_api.coverage)
// 상자 자리의 쓸 자리 — 처음에는 같은 이름이 하나뿐인 자리를 모두 고르고, 같은 이름이 여럿인 자리(「공동(기업명 작성) :」 두 곳)는 사람이 하나를 고른다(서버도 둘을 보내면 둘 다 뺀다 — guide_write.chunk_paras)
function fwChunkSet(p) {
  const keys = new Set((p.chunks || []).map((c) => c.key));
  if (!FW.chunks[p.id]) FW.chunks[p.id] = new Set((p.chunks || []).filter((c) => (c.dup || [1, 1])[1] === 1).map((c) => c.key));
  for (const k of [...FW.chunks[p.id]]) if (!keys.has(k)) FW.chunks[p.id].delete(k);
  return FW.chunks[p.id];
}
function fwUnpicked(p) { // 같은 이름의 자리(윗 제목까지 같은 덩이)가 여럿인데 하나도 안 고른 이름들 [「공동(기업명 작성) : 2곳」] — 서버 guide_write.unpicked 와 같은 셈(그쪽은 group 으로 가린다)
  const set = fwChunkSet(p), out = [], seen = new Set();
  for (const c of p.chunks || []) {
    const dup = c.dup || [1, 1], g = `${c.group || c.head}\u0000${c.under || ""}`;
    if (dup[1] <= 1 || seen.has(g)) continue;
    seen.add(g);
    if (!(p.chunks || []).some((o) => `${o.group || o.head}\u0000${o.under || ""}` === g && set.has(o.key))) out.push(`${c.group || c.head} ${dup[1]}곳`);
  }
  return out;
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
  cb.addEventListener("change", () => { if (cb.checked) FW.picks.add(p.id); else FW.picks.delete(p.id); FW.pickBy = "human"; if (p.kind === "box") fwWriteDraw(); else fwFootDraw(foot); });
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
  const types = new Map(); // 그 자리의 표에 밝힌 테이블 타입(이름마다 표의 수 — 서버 writing_guidance_api.attach 의 tableTypes)
  for (const t of p.tableTypes || []) types.set(t.name, (types.get(t.name) || 0) + 1);
  for (const [name, n] of types) tags.append(fwTagEl("ttype", n > 1 ? `${name} ${n}` : name));
  if (p.user) tags.append(fwTagEl("user", "사람 지침"));
  if (p.filled) tags.append(fwTagEl("text", "글 있음"));
  if (item) { const [word, cls] = FW_ITEM[item.state] || [item.state, ""]; const t = fwTagEl("draft", item.state === "done" ? `초안 ${item.proposals}` : item.state === "none" ? FW_NONE[item.why] || word : word, cls); const why = item.error || item.note || item.reply || ""; if (why) t.title = `${why}\n${t.title}`; tags.append(t); }
  // 덮임(② §5-12 9 — 서버가 턴 기록에서 센 것): 근거 절 · 반영한 줄 · 「모두 반영」 이 넣을 줄 · 안 고른 채 남은 줄 · 이 자리를 막는 「확인할 것」
  const cv = fwCovOf(p.id), heldQ = ((fwHeld() || {})[p.id] || []);
  if (cv && cv.evidence) tags.append(fwTagEl("evid", `근거 ${cv.evidence}절`));
  if (cv && cv.applied) tags.append(fwTagEl("applied", `반영 ${cv.applied}줄`));
  if (cv && cv.picked) tags.append(fwTagEl("open", `반영할 줄 ${cv.picked}`));
  if (cv && cv.left) tags.append(fwTagEl("left", `남은 줄 ${cv.left}`));
  if (cv && cv.old) tags.append(fwTagEl("old", "이전 계획의 초안"));
  if (heldQ.length) { const t = fwTagEl("ask", `확인할 것 ${heldQ.length}`); t.title = `이 자리에 닿는 물음에 답하지 않아 초안을 받지 않습니다:\n· ${heldQ.join("\n· ")}\n${t.title}`; tags.append(t); }
  const unpicked = p.kind === "box" ? fwUnpicked(p) : []; // 같은 이름의 자리를 하나도 안 골랐다 — 그 자리는 이번에 안 쓴다(2026-11-26 사용자: 공동기관 자료인데 공동 자리를 안 골라 상자가 빈 채로 남았다)
  if (unpicked.length) { const t = fwTagEl("unpicked", `안 쓸 자리: ${unpicked.join(" · ")}`, "warn"); t.title = "같은 이름의 자리가 여럿이라 누구의 자리인지 스크립트가 정하지 않습니다 — 아래 「쓸 자리 고르기」 에서 하나를 고르면 씁니다"; tags.append(t); }
  else if (item && (item.unpicked || []).length) { const t = fwTagEl("unpicked", `안 쓴 자리: ${item.unpicked.join(" · ")}`, "warn"); t.title = "지난 실행에서 같은 이름의 자리를 고르지 않아 쓰지 않았습니다 — 「쓸 자리 고르기」 에서 고른 뒤 다시 받습니다"; tags.append(t); }
  main.append(name, tags);
  // 「자료 전체로 다시 받기」 — 지난 실행에서 이 자리가 근거 절만 받았을 때(item.narrowed): 작성 계획이 절을 잘못 골랐으면 자료 전체를 실어 이 자리만 다시 받는다(② §5-12 4)
  if (item && item.narrowed && ["done", "none"].includes(item.state) && !fwRunning()) {
    main.append(hBtn("자료 전체로 다시 받기", () => fwRun({ only: [p.id], wide: [p.id] }), { cls: "btn sm fw-wide", title: `이 자리의 초안은 작성 계획이 고른 근거 절과 그 앞뒤(모두 ${item.narrowed}절)만 받아 썼습니다 — 필요한 내용이 다른 절에 있으면 자료 전체를 실어 이 자리만 다시 받습니다(유료 LLM · 문서는 안 바뀜)` }));
  }
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
  const todo = document.querySelector("#headsDlgBody > .fw-todo"); // 자리를 고르면 목록은 그대로 두고 발치만 다시 그린다 — 「이 탭에서 할 일」 의 셈도 따라오게
  if (todo && FW.gw) todo.replaceWith(fwWTodo(FW.wTab));
  const gw = FW.gw || {}, run = gw.run, n = FW.picks.size, mats = FW.mats ? FW.mats.size : 0, most = (gw.limits && gw.limits.places) || 40;
  foot.replaceChildren();
  if (run && run.state === "running") {
    const done = run.items.filter((i) => i.state !== "queued" && i.state !== "running").length;
    foot.append(el("span", "fw-muted", `초안 받는 중 — 자리 ${done}/${run.items.length}`), hBtn("멈춤", async () => { try { await api(`/api/docs/${state.id}/guide-write/stop`, { method: "POST" }); toast("남은 자리는 돌리지 않습니다"); } catch (e) { toast(e.message, true); } }, { title: "도는 자리는 끝까지 받고, 남은 자리는 돌리지 않습니다" }));
    return;
  }
  if (FW.wTab !== "write") { // 「작성 초안 받기」 는 초안 작성 탭에만(2026-11-26 — 탭마다 그 단계의 단추만)
    const s = fwStepNo("ask");
    foot.append(el("span", "fw-muted", `초안은 「${s ? `${s.no} ` : ""}초안 작성」 탭에서 받습니다`));
    return;
  }
  // 꺼진 까닭은 차례대로 첫째 것 — 양식 검토(자료 없이 됨) → 자료 → 작성 계획 · 확인할 것 → 자리. 2026-11-25 사용자 「왜 작성 초안 받기 버튼이 활성화가 안되냐?」 — 까닭이 풍선에만 있어 못 봤다: 단추 앞에 글로도 보인다
  const why = !gw.enabled ? "LLM 을 쓸 수 없습니다" : !(FW.fr && FW.fr.review) ? fwReviewWhy() : !mats ? "양식에 넣을 내용의 자료(MD)를 고르세요(「작성 계획」 탭)" : fwReviewWhy() || (!n ? "채울 자리를 고르세요" : n > most ? `한 번에 ${most}곳까지입니다` : "");
  if (run) {
    const got = run.items.reduce((s, i) => s + (i.proposals || 0), 0), why0 = fwRunWhy(run); // 초안 = LLM 이 쓴 글(제안 카드) — 문서에 넣는 것은 에이전트 보기의 카드에서
    foot.append(el("span", "fw-muted", `마지막 실행 — 초안 ${got}개${got ? " · 제안 카드에서 보기" : ""}${why0 ? ` · ${why0}` : ""}`));
    if (got && toolShown("Agent")) foot.append(hBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "받은 초안(제안 카드)을 보고 「문서에 반영」 을 누릅니다 — 양식에 글이 써지는 곳입니다" }));
  }
  foot.append(el("span", "fw-grow"));
  if (why) foot.append(el("span", "fw-muted", why));
  const heldN = why ? 0 : [...FW.picks].filter((i) => ((fwHeld() || {})[i] || []).length).length; // 확인할 것이 남은 자리 — 그 자리만 초안을 받지 않는다(나머지는 받는다: ② §5-12 6)
  if (heldN) foot.append(el("span", "fw-muted fw-held-note", `확인할 것이 남은 자리 ${heldN}곳은 초안을 받지 않습니다`));
  // 꺼진 동안은 파란 단추로 두지 않는다(옅은 파랑이 켜진 단추로 읽혔다 — 2026-11-25 사용자 「작성 계획 세우기랑 초안 받기가 같이 활성화」): 앞 걸음이 끝나야 파랗게
  foot.append(hBtn(`작성 초안 받기${n ? ` (${n}곳)` : ""}`, () => fwRun(), { cls: "btn sm" + (why ? "" : " primary"), disabled: !!why, title: why || `고른 자리 ${n}곳의 초안을 받습니다 — LLM 이 쓴 글이 제안 카드로 나옵니다(유료 LLM · 자리마다 호출 1번 이상 · 문서는 아직 바뀌지 않습니다)` }));
}
async function fwRun(opts = {}) { // opts.only = 이 자리들만(없으면 고른 자리) · opts.wide = 근거 절로 좁히지 않고 자료 전체를 실을 자리(「자료 전체로 다시 받기」)
  const places = opts.only || [...FW.picks], materials = [...(FW.mats || [])], chunks = {}, wide = opts.wide || [];
  for (const p of (FW.gw && FW.gw.places) || []) if (p.kind === "box" && places.includes(p.id)) chunks[p.id] = [...fwChunkSet(p)]; // 상자마다 사람이 고른 쓸 자리(서버는 이 안의 문단에만 쓰게 한다)
  if (!window.confirm(`유료 LLM 으로 자리 ${places.length}곳의 초안을 받습니다(자리마다 호출 1번 이상 · 수십 초씩${wide.length ? " · 자료 전체를 실어" : ""}). 초안은 제안 카드로 나오고 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/guide-write/run`, { method: "POST", headers: H_JSON, body: JSON.stringify({ places, materials, note: FW.note, chunks, ...(wide.length ? { wide } : {}) }) });
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

// ---- 2열 「참조한 자료」 — 초안 줄 · 반영한 문단의 근거를 문서 옆에서(spec_양식작성 ② §5-12 3) -------------------------------------------------------------
// 2026-11-25 사용자 "내용 클릭하면 참조했던 부분 은 바로 옆 열에서 같이 볼 수 있도록 해줘". 근거 = 줄마다의 근거 구절이 든 자료의 자리(서버 doc_agent._evid 의 at — 자료 id · 글자 자리 · 쪽 · 절 제목).
// 여는 곳: 제안 카드의 줄에 선 「근거 p.N」 단추(doc_agent.js agentSrcBtn) · 대시보드 「고른 초안을 문서에 반영」 줄의 「근거 보기」. 열이 열려 있는 동안 문서에서 반영된 문단 · 칸을 누르면 그 근거를 보인다
// (GET …/guide-write/sources — 반영 기록에서: 서버를 다시 켜도 같다). 읽기만 — 문서도 자료도 안 바뀐다. 글자 대조로 찾은 자리일 뿐이다(그 구절이 그 값을 뒷받침하는지는 사람이 읽는다).
const FSRC = { map: null, at: null, quote: "", seq: 0 };
const FW_HELP_SOURCE = "초안의 줄마다 LLM 이 적은 근거 구절을 자료에서 찾은 자리입니다(글자 대조 — 공백은 접고). 구절이 든 절의 제목 · 쪽과 앞뒤 글을 보입니다.\n"
  + "· 「같은 구절 n곳」 = 자료의 여러 곳에 같은 구절이 있습니다 — 보이는 곳이 그 값의 근거인지 확인하세요(작성 계획이 고른 절 → 그 자리와 차년도 · 단계가 어긋나지 않는 절 → 첫 곳 차례로 보입니다).\n"
  + "· 이 열이 열려 있는 동안 문서에서 반영된 문단 · 표 칸을 누르면 그 줄의 근거로 바뀝니다.\n"
  + "· 그 구절이 그 값을 뒷받침하는지(같은 수가 다른 기관 · 다른 항목의 것은 아닌지)는 사람이 읽고 확인합니다.";
async function fsrcOpen(at = null, quote = "") { // at = {mat, start, end, page, title, path, name, hits} | null(열만 — 문단을 눌러 고른다)
  if (!state.id) return;
  fwClearWay();
  const { tools } = headsDlg("fwSource", "참조한 자료", "초안 · 반영한 문단의 근거(자료의 그 자리) · 문서는 안 바뀜");
  tools.append(hHelp("참조한 자료 안내", FW_HELP_SOURCE, { note: true }));
  FSRC.at = at; FSRC.quote = quote || "";
  try { FSRC.map = await api(`/api/docs/${state.id}/guide-write/sources`); } catch { FSRC.map = { paras: {}, cells: {} }; }
  fsrcDraw();
}
async function fsrcDraw() {
  if (heads.dlg !== "fwSource") return;
  const body = $("headsDlgBody"), at = FSRC.at, seq = (FSRC.seq += 1), n = Object.keys((FSRC.map && FSRC.map.paras) || {}).length + Object.keys((FSRC.map && FSRC.map.cells) || {}).length;
  body.replaceChildren(el("div", "fw-muted fw-pad fsrc-tip", n ? `반영한 문단 · 칸 ${n}곳에 근거가 있습니다 — 문서에서 그 문단을 누르면 여기에 근거가 보입니다.` : "반영한 문단의 근거가 아직 없습니다 — 제안 카드의 「근거」 단추를 누르면 여기에 보입니다."));
  if (!at) return;
  if (!at.mat) { body.append(el("div", "fw-empty fsrc-none", at.none || "이 문단에는 반영 기록의 근거가 없습니다(사람이 쓴 글이거나 근거 구절을 자료에서 찾지 못한 줄).")); return; }
  let ex;
  try { ex = await api(`/api/docs/${state.id}/agent/material/${encodeURIComponent(at.mat)}/at?start=${at.start | 0}&end=${at.end | 0}`); }
  catch (e) { if (seq === FSRC.seq && heads.dlg === "fwSource") body.append(el("div", "fw-empty", e.message || String(e))); return; }
  if (seq !== FSRC.seq || heads.dlg !== "fwSource") return;
  const sec = ex.sec || {}, head = el("div", "fw-pad fsrc-head"), where = [...(sec.path || []), sec.title].filter(Boolean).join(" › ");
  head.append(el("strong", "fsrc-name", ex.name || at.name || "자료"));
  if (sec.page !== null && sec.page !== undefined) head.append(el("span", "fw-tag guide fsrc-page", `p.${sec.page}`));
  if (where) head.append(el("span", "fsrc-where", where));
  if ((at.hits || 1) > 1) { const t = el("span", "fw-tag warn fsrc-hits", `같은 구절 ${at.hits}곳`); t.title = "자료의 여러 곳에 같은 구절이 있습니다 — 보이는 곳이 그 값의 근거인지 확인하세요"; head.append(t); }
  const pre = el("div", "fsrc-text"), mark = el("mark", "fsrc-hit", ex.hit || "");
  pre.append(ex.from > 0 ? "… " : "", ex.before || "", mark, ex.after || "", ex.to < ex.chars ? " …" : "");
  body.append(head, pre);
  mark.scrollIntoView({ block: "center" });
}
document.addEventListener("click", (e) => { // 열이 열려 있는 동안 — 문서의 문단 · 표 칸을 누르면 그 줄의 근거로
  if (heads.dlg !== "fwSource" || !FSRC.map || !e.target.closest) return;
  const p = e.target.closest("#doc .para"), cell = e.target.closest("#doc [data-cell]"); // 표 칸은 data-cell(app.js 의 칸 그리기) — 문단 없이 칸의 여백을 눌러도 그 칸의 근거를 보인다
  if (!p && !cell) return;
  const src = (p && (FSRC.map.paras || {})[p.dataset.id]) || (cell && (FSRC.map.cells || {})[cell.dataset.cell]) || null;
  FSRC.at = src || { none: "이 문단에는 반영 기록의 근거가 없습니다(사람이 쓴 글이거나 근거 구절을 자료에서 찾지 못한 줄)." };
  FSRC.quote = src ? src.quote || "" : "";
  fsrcDraw();
});
