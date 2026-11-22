"use strict";
// 대시보드(패널 탭 「대시보드」 — spec_작업에이전트 ② §9 · design.md §17): 지금 문서의 TASK 를 **단계 흐름**(워크플로우 등록부 GET /api/workflow 의 묶음 › 단계 — /workflow 의 「단계 흐름」 과 같은 차례)으로 보이고,
// 단계마다 **지금 상태**(끝남 · 지금 · 남음 …)와 **그 단계를 하는 단추**를 둔다. 2026-11-18 사용자(/workflow 의 「단계 흐름」 그림을 보이며) "도구에 이런 플로우가 있으면 좋겠고, 여기서 실행을 다 할 수 있었으면 좋겠어. 탭을 추가해줘".
// **새 실행 길을 만들지 않는다**(spec_작업에이전트 ② §7 ⓒ): 단계의 상태 · 단추는 「작업 개요」 가 그리는 것(이관 taskSteps · 취합 gatherSteps — 같은 함수를 불러 단추를 새로 받음)과
//   에이전트의 상태 · 행동(양식 표준화 · 양식 맞추기 agwStatus · agwExec), 서식 복사의 단계 상태(slStepState)를 쓰고, 묶음의 「한 번에 진행」 은 그 TASK 의 것(divRunAll · taskRunAll · gatherRunAll · styleSaveAuto · headsRunAll · headsPickRun — 2026-11-18 부터 확인 창 없이)을 그대로 부른다.
//   양식 표준화(plan_fit — spec_양식표준화)의 2 · 3단계(헤딩 추출 · 표)는 분석 상태(doc_agent_work.js agwStdSteps — 에이전트와 같은 셈)로 세고, 머리 아래 「이어서 한 번에 N→3단계」 가 묶음의 실행을 차례로 잇는다(dashStdChain).
//   단계의 차례 · 이름 · 누가 · 조건은 등록부(app/workflow.py)가 원본이다 — 여기서 다시 적지 않는다. 도는 것은 agwRunning(에이전트 보기의 진행 카드와 같은 것)으로 본다.
//   문서 하나로 조립한 워크플로우(task_catalog.js taskIsSingle — 2026-11-20)만은 화면이 세지 않는다: 서버가 센 상태(GET /api/works/{wid}/flow)로 그리고 서버 쪽 실행기로 돌린다(dashSingleLive — workflow_exec.js flowGet · singleRunServer).
// **TASK 의 단계나 그 단계의 실행 함수를 바꾸면 아래 dash<TASK>Live 의 그 TASK 가지도 함께 본다**(CLAUDE.md — agwStatus · agwExec 와 같은 약속).
// 읽히는 차례: doc_agent_work.js 다음(agwJob · agwFit · agwStatus · agwExec · agwRunning · agwLiveText · agwConfigForm · agwFitApplied · agwStd*). app.js: state · $ · el · hBtn · toast · api · showTab · openWork · dv · div* · task* · TASK_STAGES · heads ·
//   heads_run_all.js(headsRunAll) · heads_run_pick.js(headsPickRun · hrpOff · hrpStep) · tpl_plan_bar.js(tpbApply · tplPlanGo) · doc_status.js(dsTo) ·
//   gather.js(gt · gatherPlan · gatherSteps · gatherActEl · gatherRunAll · gatherUrl · gatherPickFiles · gatherUploadMany · GT_STAGES) · gather_quick.js(gqRun) · style_lib.js(STYLE · styleSave* · slStepState · styleLibOpen) · task_catalog.js(TASK_CATALOG · TASK_STAGE_META — 취합의 묶음 이름. 이관의 묶음 이름은 등록부의 no·name 으로 온다: RELAY_STAGE_META 와 같은 값).

const DASH = { reg: null, regErr: "", regLoad: null, doc: "", primed: "", open: null, nowKey: "", form: false, busy: null, last: null, sig: "", seq: 0, loadKey: "", projTried: "" };
// open = 편 단계 key(null = 「지금」 단계를 저절로 · "" = 모두 접음 — 「지금」 이 바뀌면 null 로) · nowKey = 마지막으로 그린 「지금」(도는 중) 단계 · form = 프로젝트 구성 입력 폼을 폈나(양식 표준화 · 양식 맞추기) · busy = 이 보기가 부른 행동 {label, t0} · last = 그 끝 {label, ok, text}
// loadKey = 「구성 불러오기」 목록에서 고른 것(양식 표준화 — 다시 그려도 그대로) · projTried = 다른 프로젝트 목록을 읽어 본 문서(divProjectsLoad — 못 읽어도 1초마다 되풀이하지 않게)
// (그때그때 붙는 것: hands = 사람이 하는 일 줄의 판 · 끝남(dashHands) · flow = 문서 하나로 조립한 워크플로우의 읽어 둔 서버 상태(dashFlow) · sigTried = 정의가 바뀐 것을 보고 목록을 다시 읽어 본 지문)
const DASH_ST = { done: "끝남", now: "지금", ready: "할 수 있음", todo: "남음", hold: "기관 미지정", run: "진행 중", soon: "준비 중" }; // 글로 구별한다(design.md §11 — 색에만 기대지 않음). 「기관 문서마다」(each) · 따로 안 셈("")은 꼬리표 없음
const DASH_COUNTED = new Set(["done", "now", "ready", "todo", "hold", "run"]);
const dashCounted = (n) => !n.optional && DASH_COUNTED.has(n.state); // 끝난 수에 넣는 단계 — 안 해도 되는 단계 · 따로 세지 않는 단계 · 준비 중은 뺀다(design.md §11)
const DASH_HELP = "이 워크플로우의 단계를 차례대로 보이고, 단계마다 지금 상태와 그 단계를 하는 단추를 둡니다. 단계를 누르면 펴지고, 펴면 지금 상태 · 단추가 보입니다. 단계 이름 옆 메모 아이콘에 그 단계의 「하는 일 · 조건」 이 있습니다.\n"
  + "단추는 패널 「작업 개요」 · 에이전트와 같은 기능을 부릅니다 — 누르면 확인 창 없이 바로 합니다(단계 하나가 문서를 바꾼 것은 실행 취소로 되돌리고, 유료 LLM 을 부르는 단추는 풍선 도움말에 그렇게 적습니다).\n"
  + "묶음 머리의 「한 번에 진행」 은 그 묶음의 남은 단계를 차례로 합니다(사람이 봐야 할 곳에서는 멈추거나 넣지 않고 남김) — 끝나면(멈춤이 아니면) 바뀐 문서의 고친 문단을 확정합니다(실행 취소 기록은 비고, 앞 상태는 「고친 문단」 탭 확정 기록의 복원).\n"
  + "머리 아래 「이어서 한 번에」 는 남은 묶음을 차례로 잇습니다(앞 묶음이 끝나지 않으면 뒤 묶음은 시작하지 않고 한 것 · 멈춘 까닭 · 남은 것을 머리에 적음).\n"
  + "꼬리표 아이콘 — 사람(파랑) · 스크립트(</>) · LLM(보라 반짝임) · 문서 바뀜(주황 문서+연필) — 마우스를 올리면 이름이 보입니다. 「필수」 는 해야 다음으로 가는 단계, 「자동」 은 누르지 않아도 도는 단계입니다.\n"
  + "점선 단계(「선택」)는 안 해도 되는 단계, 「준비 중」 은 아직 없는 단계입니다. 값 입력 · 목록 보기처럼 넓은 일은 「작업 개요」 나 문서 옆 열에서 합니다.";

// 탭은 문서가 열려 있으면 늘 보인다(app.js toolShown("Dash")) — 2026-11-18 사용자 "내가 단계 흐름에서 자동 실행할 수 있도록, 여기 탭에 넣어 달라고 했는데 보이질 않아"(TASK 없이 연 문서라 탭이 감춰져 있었다: 전에는 TASK 가 적힌 문서만).
// TASK 가 없으면 이 문서에 맞는 TASK 를 고르는 카드(dashPickEl) — 고르면 그 자리에서 단계 흐름
const dashShown = () => !!state.id;
const dashHasTask = (job = agwJob()) => typeof TASK_CATALOG === "object" && !!TASK_CATALOG[job];
const DASH_PICK_HELP = "이 문서에는 워크플로우가 적혀 있지 않습니다. 워크플로우를 고르면 그 워크플로우의 단계 흐름이 여기 보이고, 단계마다 지금 상태와 실행 단추 · 묶음의 「한 번에 진행」 이 생깁니다.\n"
  + "고르는 것은 패널 「작업 개요」 의 워크플로우 칸과 같습니다(이 문서에 워크플로우를 적음 — 문서는 바뀌지 않습니다). 이 문서의 형식(hwpx · docx)으로 할 수 있는 워크플로우만 보입니다.";
const dashKey = () => `${state.id}|${state.epoch}`;
const dashHere = (t) => String(t || "").replace(/위 칸에서/g, "「작업 개요」 의 칸에서").replace(/아래 「/g, "「작업 개요」 의 「").replace(/아래 입력 칸/g, "「작업 개요」 의 입력 칸"); // 「작업 개요」 의 단계 글은 그 패널 안의 자리를 가리킨다 — 여기서는 그 패널 이름으로

function dashBtn(label, run, { primary = false, disabled = false, title = "", focus = "" } = {}) {
  const b = hBtn(label, run, { cls: "btn sm" + (primary ? " primary" : ""), disabled, title });
  if (focus) b.dataset.dashFocus = focus;
  return b;
}

function dashRegLoad() { // 워크플로우 등록부 — 페이지에 한 번 읽는다(서버를 다시 켜야 바뀐다 · 조립한 워크플로우의 정의가 바뀌면 dashCatalogChanged 가 다시 읽게 한다)
  if (DASH.reg) return Promise.resolve(DASH.reg);
  if (!DASH.regLoad) DASH.regLoad = api("/api/workflow").then((d) => { DASH.reg = d; DASH.regErr = ""; return d; }, (e) => { DASH.regErr = e.message || String(e); return null; }).finally(() => { DASH.regLoad = null; });
  return DASH.regLoad;
}
// 조립한 워크플로우의 정의를 다시 읽었더니 바뀌었거나 없어졌다(app.js taskCatalogRefresh — spec_워크플로우 ② §15 「실행」): 단계 흐름은 등록부(GET /api/workflow — 조립한 정의가 든다)에서 그리므로
// 그것을 다시 읽고 다시 그린다(옛 등록부로 바뀌기 전의 묶음 · 단계를 그리지 않게)
function dashCatalogChanged() {
  DASH.reg = null;
  DASH.sig = "";
  dashRegLoad().then(() => { if (state.id && $("paneDash") && !$("paneDash").hidden) dashDraw(true); });
}

async function dashPrime() { // 그 TASK 의 상태를 문서마다 처음 한 번 읽는다 — 그 뒤는 화면이 들고 있는 값으로 센다(1초마다 서버를 다시 읽지 않는다)
  const job = agwJob(), key = `${dashKey()}|${job}`;
  if (DASH.primed === key) return;
  if (DASH.primeLoad && DASH.primeLoad.key === key) return DASH.primeLoad.promise;
  DASH.primed = "";
  const prime = { key, promise: null };
  DASH.primeLoad = prime;
  prime.promise = (async () => { try {
    const single = taskIsSingle(job) || taskIsRelayFlow(job); // 문서 하나로 조립한 것 · 줄 목록으로 조립한 이관형(task_catalog.js) — 상태는 서버가 센다(dashSingleLive · dashFlowLive): 프로젝트 구성 상태(사람이 하는 줄의 단추) + 서버 상태를 읽는다
    if (agwFit(job) || taskIsRelay(job) || taskIsGather(job) || single) { if (!dv.view) await divShow(); } // taskIsGather = 취합형(붙박이 취합 · 취합형으로 조립한 것 — task_catalog.js)
    if (job === "plan_fit") { await agwHeadsView(); if (!agwStdView()) await agwStdFresh(); } // 양식 표준화 2 · 3단계 — 헤딩 요약(단계별 실행이 1단계 결과를 본다 · 추출을 저절로 시작하지 않음) · 분석 상태
    if (taskIsRelay(job) && !Object.keys(taskFlow.div || {}).length) await taskFlowLoad();
    if (taskIsGather(job) && typeof gt === "function" && !gt().view) await gatherLoad();
    if (single && key === `${dashKey()}|${agwJob()}` && !dashFlow().view) await dashFlowRead();
    if (key !== `${dashKey()}|${agwJob()}`) return;
    if ((agwFit(job) || taskIsRelay(job) || taskIsGather(job) || single) && !dv.view) return;
    if (job === "plan_fit" && !agwStdView()) return;
    if (taskIsGather(job) && !gt().view) return;
    if (single && !dashFlow().view) return; // 서버 상태를 못 읽었다 — 빈 값으로 진행 요약을 저장하지 않는다
    DASH.primed = key; // 읽기가 끝난 뒤에만 진행 요약을 저장한다(로딩 중 빈 값으로 완료 기록을 덮지 않음).
  } catch (e) { console.error(e); } finally { if (DASH.primeLoad === prime) DASH.primeLoad = null; } })();
  return prime.promise;
}

async function dashShow() { // app.js showTab("Dash")
  if (!state.id) return;
  const doc = dashKey(), job = agwJob();
  dwfReset();
  if (DASH.doc !== dashKey()) Object.assign(DASH, { doc: dashKey(), open: null, nowKey: "", form: false, last: null, busy: null });
  DASH.sig = "";
  await dashDraw(true);
  await dashRegLoad();
  if (doc !== dashKey() || job !== agwJob()) return;
  await dwfLoad();
  if (doc !== dashKey() || job !== agwJob()) return;
  await dashPrime();
  if (doc === dashKey() && job === agwJob()) await dashDraw(true);
}

// over = 도는 것이 있어도 시작한다 — 도는 것이 **다른 문서만 잡은 서버 실행**일 때만 부르는 쪽이 준다(문서마다 따로 도는 실행: spec_워크플로우 ② §18-22 — 그 밖에는 전처럼 겹치지 않는다)
async function dashExec(label, fn, { over = false } = {}) { // 이 보기가 부르는 행동 하나(에이전트의 행동 · 기존 함수) → 끝 글을 머리 아래 한 줄에 남긴다. fn → {ok, text} | null(그만둠 — 남기지 않음)
  if (DASH.busy || DWF.busy) return;
  if (!over && agwRunning()) { toast("지금 진행 중인 작업이 끝난 뒤에 누르세요", true); return; } // 같은 문서에 두 실행을 겹치지 않는다(에이전트 카드와 같은 약속)
  const doc = dashKey();
  DASH.busy = { label, t0: Date.now() };
  DASH.last = null;
  dashDraw(true);
  let res = null;
  try { res = await fn(); } catch (e) { console.error(e); res = { ok: false, text: `오류 — ${e.message}` }; }
  DASH.busy = null;
  if (DASH.doc !== doc) return;
  if (res && res.text) DASH.last = { label, ok: res.ok !== false, text: res.text };
  dashDraw(true);
}

async function dashOpen(id) { // 목적 문서로 — 그 문서에서도 대시보드를 본다
  await openWork(id);
  if (state.id === id && dashShown()) showTab("Dash");
}

// ---------------------------------------------------------------- TASK 마다의 지금 상태 → L = {steps: {등록부 단계 key: {state, text, lines, acts[요소], via}}, runs: {묶음 id: 단추}, parts?: [기관 문서 줄]}
// M = 그릴 것 전체(notes 알림 · top 머리 아래 단추) — 가지가 더한다

function dashReviewSum(r) { // 마지막 구분 기준 LLM 검토(dv.marks.review — server divisions_review 의 답) → {text 무엇이 나왔나, left 「자리로 추가」 를 기다리는 문단 후보 수, bad 답을 못 받은 검토가 있나}
  const parts = [r.review ? `재검토 반영 ${(r.review.applied || []).length}` : "", r.missing ? `빠진 자리 후보 ${(r.missing.missing || []).length}` : ""].filter(Boolean);
  const errs = Object.entries(r.errors || {}).map(([k, v]) => `${k === "review" ? "재검토" : "빠진 자리 검토"} — ${v}`);
  return { text: (parts.join(" · ") || `돌릴 검토가 없었습니다(${Object.values(r.why || {}).join(" · ") || "까닭 모름"})`) + (errs.length ? ` · 답을 못 받은 검토: ${errs.join(" · ")}` : ""),
    left: (r.items || []).filter((x) => divCandAdd(x) && !divHintOf(x.id)).length, bad: errs.length > 0 }; // 문단 후보 · 추가했나 = 검토 결과 목록의 「자리로 추가」 단추와 같은 셈(app.js divCandAdd · divHintOf)
}

async function dashReview() { // 양식 표준화 · 양식 맞추기의 「구분 기준 자리 확인」 단계의 「LLM 검토 실행」 — 검토 결과 목록의 그 단추와 같은 함수(app.js divReview: 새 실행 길이 아니다 — 끝나면 목록이 문서 옆 열에 열린다). 유료지만 확인 창 없이(2026-11-18). → dashExec 의 끝 글 | null(그만둠)
  const m = dv.marks, before = m.review ? m.review.at : 0;
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 유료 · 수십 초 · 문서는 안 바뀜: design.md §18 「확인 창」)
  await divReview(); // 못 하면 알림 글(toast)만 남기고 결과는 그대로다
  const r = m.review;
  if (!r || r.at === before) return { ok: false, text: "LLM 검토를 하지 못했습니다(알림 글 참고)" };
  const sum = dashReviewSum(r);
  return { ok: !sum.bad, text: `${sum.text} — ${sum.left ? `문단 후보 ${sum.left}곳은 문서 옆 목록에서 「자리로 추가」 해야 자리가 됩니다` : "결과 목록은 문서 옆 열에 있습니다"}` };
}

async function dashFitLive(M) { // 연차보고서 양식 맞추기 — 에이전트가 보는 상태 · 행동 그대로(agwFitStatus): 준비 › 프로젝트 구성 값 › (구분 기준 자리 확인) › 변경 계획 › 반영
  const st = await agwStatus(), L = { steps: {}, runs: {} };
  L.runs.frame = dashFitStage1(M, st, L, "frame");
  return L;
}

// 프로젝트 구성 값 › (구분 기준 자리 확인) › 변경 계획 › 반영 — 양식 맞추기(묶음 frame)와 양식 표준화 1단계(묶음 config)가 같이 쓴다. 에이전트가 보는 상태 · 행동 그대로(agwFitStatus).
// gid = 「한 번에 진행」 · 멈춘 글이 붙는 묶음 · std = 양식 표준화(「구성 읽기」 는 따로 단계 — dashStdRead) → 그 묶음의 「한 번에 진행」 단추
function dashFitStage1(M, st, L, gid, std = false) {
  const by = {};
  for (const s of st.steps) by[s.key] = s;
  const step = (k) => L.steps[k] || (L.steps[k] = { state: (by[k] || {}).state || "todo", text: (by[k] || {}).text || "", acts: [] });
  for (const k of ["open", "values", "plan", "apply"]) step(k);
  if (st.facts.why) M.notes.push({ text: st.facts.why });
  if (st.facts.moved) M.notes.push({ text: st.facts.moved, warn: true });
  for (const a of st.actions) {
    const opt = { primary: !!a.primary, title: a.does, focus: `act:${a.name}` };
    if (a.name === "config_read") { if (!std) step("values").acts.push(dashBtn(a.label, () => dashExec(a.label, async () => { const r = await agwExec("config_read"); agw().form = null; return r; }),
      { ...opt, primary: opt.primary && !DASH.form })); } // 폼이 열려 있으면 읽은 값으로 다시 채운다(폼의 「문서에서 보기」 와 같은 끝) · 폼을 편 동안 파란 단추는 폼의 「확정」 하나
    else if (a.name === "config_set") { if (!DASH.form) step("values").acts.push(dashBtn(`${a.label}…`, () => { DASH.form = true; dashDraw(true); }, opt)); } // 폼을 편 동안은 폼의 단추 줄에 「닫기」(agwConfigForm on.close — 「확정」 · 「문서에서 보기」 와 한 줄: 2026-11-18 사용자)
    else if (a.name === "plan") step("plan").acts.push(dashBtn(a.label, () => dashExec(a.label, () => agwExec("plan")), opt));
    else if (a.name === "open:plan") step("plan").acts.push(dashBtn(a.label, () => divList(), opt));
    else if (a.name === "apply") step("apply").acts.push(dashBtn(a.label, () => dashExec(a.label, async () => { // 「작업 개요」 의 「② 반영」 과 같은 길(2026-11-18 부터 확인 창 없이 — 실행 취소 한 번)
      if (!(await divApply())) return null; // 그만둠 · 못 함(까닭은 알림 글)
      const left = dv.result && dv.result.unresolved.length;
      return { ok: true, text: `문서에 반영했습니다 — 절 · 표 행 · 표 열을 프로젝트 구성에 맞췄습니다${left ? ` · 미해결 ${left}곳은 손으로 맞춰야 합니다` : ""}(실행 취소로 되돌릴 수 있습니다)` };
    }), opt));
  }
  // 구분 기준 자리 확인(안 해도 됨) — 「LLM 검토 실행」 을 이 단계에서 바로(2026-11-18 사용자 「LLM 검토할 수 있도록 해야 하는데 그 기능이 없잖아」 — 전에는 「검토 목록 열기」 뿐이라 문서 옆 목록을 열어야 돌릴 수 있었다).
  // 끝남은 검토했고 「자리로 추가」 를 기다리는 문단 후보가 없을 때만(답을 못 받은 검토가 있으면 아님 — 이름 줄의 「일부만」 과 같게). 남은 후보는 수와 보정할 곳을 글로(② §7 ⓐ)
  const m = dv.marks || {}, rv = m.review || null, sum = rv ? dashReviewSum(rv) : null, noRun = m.reviewing ? "LLM 검토가 돌고 있습니다" : dv.busy ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : "";
  L.steps.review = { state: m.reviewing ? "run" : sum && !sum.left && !sum.bad ? "done" : "", acts: [],
    text: m.reviewing ? "LLM 검토 중 — 수십 초 걸립니다" : !sum ? "LLM 검토는 아직 하지 않았습니다 — 스크립트가 찾지 못한 자리(묶음 밖의 표 · 문단)를 LLM 이 찾습니다. 하지 않아도 다음 단계로 갈 수 있습니다"
      : `LLM 검토함(${fmtWhen(rv.at)}) — ${sum.text}${sum.left ? ` · 문단 후보 ${sum.left}곳은 「검토 결과 보기」 의 목록에서 「자리로 추가」 해야 자리가 됩니다` : ""}${sum.bad ? " · 다 본 것이 아닙니다 — 「다시 검토」" : ""}`
        + (rv.rev !== state.serverRev ? " · 검토한 뒤 문서가 바뀌었습니다 — 「다시 검토」 할 수 있습니다" : "") };
  L.steps.review.acts.push(dashBtn(m.reviewing ? "LLM 검토 중…" : rv ? "다시 검토" : "LLM 검토 실행", () => dashExec("구분 기준 LLM 검토", dashReview), { disabled: !!noRun, focus: "act:reviewRun",
    title: noRun || "구분 기준 자리를 LLM 이 검토합니다(유료 · 수십 초): 표시한 자리의 재검토와 빠진 자리 검토를 함께 돌리고 결과 목록을 문서 옆 열에 엽니다. 문서는 바뀌지 않습니다" }));
  if (rv) L.steps.review.acts.push(dashBtn("검토 결과 보기", () => divReviewList(), { primary: !!sum.left && !m.reviewing, focus: "act:review",
    title: "문서 옆 열에 구분 기준 LLM 검토 결과 목록을 엽니다 — 줄을 누르면 그 자리로 · 문단 후보는 「자리로 추가」 해야 자리가 됩니다" }));
  if (dv.msg && dv.msg.kind === "halt") L.ends = { [gid]: { ok: false, text: dv.msg.text } }; // 「한 번에 진행」 · 반영이 멈춘 까닭(「작업 개요」 의 상태 줄과 같은 글)
  const why = divRunWhy(), locked = !!dv.busy || divRunLocked() || !!DASH.busy || !!agwRunning(), applied = L.steps.apply.state === "done"; // 같은 문서에 두 실행을 겹치지 않는다(헤딩 판정 · 전체 실행 · 대시보드가 부른 행동이 도는 동안)
  const no = !st.facts.confirmed ? "프로젝트 구성 값을 먼저 확정하세요" : applied ? "남은 단계가 없습니다" : why || (locked ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : "");
  return dashBtn("한 번에 진행", () => divRunAll(), { disabled: !!no, focus: `run:${gid}`,
    title: no || "변경 계획 → 반영을 한 번에 — 계획 오류 · 미해결 자리가 있거나 기관의 차례가 마지막 반영과 다르면 반영하지 않고 멈춥니다. 끝나면 고친 문단을 확정합니다(앞 상태는 「고친 문단」 탭 확정 기록의 복원)" });
}

// ---------------------------------------------------------------- 사업계획서 양식 표준화(plan_fit — spec_양식표준화 ② §1~§4): 1단계 프로젝트 구성 › 2단계 헤딩 추출 › 3단계 표
// 1단계 = 양식 맞추기와 같은 몫(dashFitStage1) + 구성 읽기 · 불러오기(dashStdRead). 2 · 3단계 = 분석 상태(doc_agent_work.js agwStdSteps — 에이전트와 같은 셈 · dashStdHeads).
// 머리 아래 「이어서 한 번에 N→3단계」(dashStdTop · dashStdChain). 단추는 기존 함수만(② §3): divRunAll · headsPickRun(s1·s2 · l2 · s3 · l3) · headsRunAll · tpbApply · tplPlanGo · tplRelOpen · showTab.
// 문서를 바꾸거나 유료 LLM 을 부르는 단추도 확인 창 없이 바로 한다(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 그 함수의 확인 창: headsPickRun · headsRunAll · divRunAll). 조정 「모두 반영」 은 그 전부터 묻지 않았다(사용자 2026-11-18 「팝업 알림 확인 받지마」 — 진행 줄의 그 단추와 같게).
async function dashStdLive(M) {
  const st = await agwStatus(), L = { steps: {}, runs: {} }, S = st.std || agwStdSteps();
  L.runs.config = dashFitStage1(M, st, L, "config", true);
  dashStdRead(L, st);
  const groups = (M.reg ? M.reg.stages : []).map((g) => ({ id: g.id, no: g.no || "", name: g.name, keys: g.steps.filter((s) => !s.optional && !s.soon).map((s) => s.key) })); // 묶음마다 세는 단계(등록부가 원본)
  dashStdHeads(L, S, groups);
  dashStdTop(M, L, st, S, groups);
  return L;
}

function dashStdRead(L, st) { // 1단계의 「구성 읽기」 · 「구성 불러오기」(안 해도 됨 — ② §2·§3): 읽기 = 에이전트 행동 config_read(divRead) · 불러오기 = 「작업 개요」 의 「프로젝트 구성 불러오기」 와 같은 목록 · 함수(divSourceFill · divSourceLoad)
  const W = agw(), confirmed = !!st.facts.confirmed, off = dv.busy ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : "";
  L.steps.read = { state: W.readTried ? "done" : confirmed ? "" : "ready", acts: [], // 읽어 봤으면 끝남 + 읽은 값 한 줄 · 확정했으면 상태 없이 · 그 밖은 할 수 있음
    text: W.readTried ? W.readText || "이 문서에서 읽어 봤습니다" : confirmed ? "" : "문서(빈 사업계획서 포함)에 적힌 단계 · 차년도 · 기관을 읽어 입력 칸에 채웁니다 — 확정은 「프로젝트 구성 추출」 에서 합니다" };
  L.steps.read.acts.push(dashBtn("구성 읽기", () => dashExec("구성 읽기", async () => { const r = await agwExec("config_read"); W.form = null; return r; }), { // 폼이 열려 있으면 읽은 값으로 다시 채운다
    primary: !confirmed && !st.facts.config && !W.readTried && !DASH.form, disabled: !!off, focus: "act:config_read",
    title: off || "문서에 적힌 단계 · 차년도 · 기관을 읽어 입력 값으로 가져옵니다 — 문서와 확정은 그대로(확정은 「프로젝트 구성 추출」)" }));
  const v = dv.view, from = dv.preset && dv.preset.from;
  L.steps.load = { state: "", text: from ? `불러온 곳: ${from} — 확인한 뒤 「프로젝트 구성 추출」 에서 확정합니다` : "", acts: [] };
  if (!v) return;
  if ((dv.projects === undefined || !dv.projectsAt) && DASH.projTried !== dashKey()) { DASH.projTried = dashKey(); divProjectsLoad(); } // 다른 프로젝트 목록 — 늦게 오면 다음 그리기에 든다
  const sel = el("select", "dash-load-sel");
  sel.setAttribute("aria-label", "프로젝트 구성 불러오기 — 이 프로젝트 확정본 · 문서에서 추출 · 다른 프로젝트 · 저장한 프로젝트 구성");
  sel.dataset.dashFocus = "act:loadSel";
  divSourceFill(sel, v);
  if (DASH.loadKey && [...sel.options].some((o) => o.value === DASH.loadKey)) sel.value = DASH.loadKey; else DASH.loadKey = "";
  const go = dashBtn("불러오기", () => { const key = sel.value; if (key) dashExec("구성 불러오기", () => dashStdLoad(key)); }, { disabled: !sel.value || !!off, focus: "act:load",
    title: off || "고른 곳의 프로젝트 구성(단계 · 차년도 · 기관)을 입력 칸에 채웁니다 — 문서와 확정은 그대로, 확인한 뒤 「프로젝트 구성 추출」 에서 확정합니다" });
  sel.onchange = () => { DASH.loadKey = sel.value; go.disabled = !sel.value || !!off; };
  L.steps.load.acts.push(sel, go);
}

async function dashStdLoad(key) { // 「불러오기」 → 입력 칸만(문서 · 확정은 그대로 — 묻지 않는다). 값이 바뀌었으면 끝 글, 아니면 남기지 않음(「파일 올려 추출…」 은 파일 고르기 창이 따로 — 그 끝은 알림 글)
  const before = dv.values ? divCanon(divValues()) : "";
  await divSourceLoad(key);
  agw().form = null; // 폼이 열려 있으면 불러온 값으로
  return dv.values && divCanon(divValues()) !== before ? { ok: true, text: `입력 칸을 채웠습니다(아직 확정 전) — ${divValuesText(divValues())} · 「프로젝트 구성 추출」 에서 확인해 확정합니다` } : null;
}

const dashStdTableKeys = (S) => [S.steps.tables.state === "done" ? "" : "s3", S.steps.tablesLlm.state === "done" ? "" : "l3"].filter(Boolean); // 3단계에서 남은 단계(단계별 실행의 키)

function dashStdHeads(L, S, groups) { // 2 · 3단계의 상태 · 단추. 「지금」 은 묶음 차례로 넘어온다 — 앞 묶음이 남았으면 할 수 있는 단계는 「할 수 있음」(헤딩 · 표 분석은 프로젝트 구성에 기대지 않는다: ② §1)
  const R = agwRunning();
  const off = DASH.busy ? `「${DASH.busy.label}」 이 끝나면 쓸 수 있습니다` : R ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : S && S.busy ? `${S.busy} — 끝나면 쓸 수 있습니다` : ""; // 같은 문서에 두 실행을 겹치지 않는다(② §3)
  const raw = (k) => (S ? S.steps[k] || { state: "todo", text: "" } : { state: "todo", text: "분석 상태를 읽는 중…" }); // 모르는 key(서버의 등록부가 옛 판 — 다시 켜기 전)여도 그리기를 깨지 않는다
  const doneOf = (k) => (L.steps[k] ? L.steps[k].state === "done" : raw(k).state === "done");
  const supported = !!(dv.view && dv.view.profile && dv.view.profile.supported); // 지원 안 되는 양식은 1단계를 적용할 수 없다 — 「지금」 이 1단계에 묶여 있지 않게(에이전트 agwFitStatus · dashStdTop 과 같게)
  const cur = groups.find((g) => (g.id !== "config" || supported) && g.keys.some((k) => !doneOf(k)));
  for (const g of groups) {
    if (g.id === "config") continue;
    let first = true;
    for (const k of g.keys) {
      const r = raw(k);
      let state = r.state === "done" ? "done" : r.state === "run" ? "run" : "";
      if (state !== "done") {
        if (!state) state = k === "adjust" && !(S && S.judged) ? "todo" : g === cur ? (first ? "now" : "todo") : "ready"; // 조정은 헤딩 판정(LLM) 뒤의 일 — 그 전에는 남음
        first = false;
      }
      L.steps[k] = { state, text: r.text || "", acts: [] };
    }
  }
  // 고친 부분 적용하기(spec_작업 ② §8 — 2026-11-18 사용자 「헤딩 추출 및 표 점검 할 때.. 고친 부분 적용하기 버튼 넣어줘」 → 답 「고친 문단 확정」): 문서가 바뀌는 단계(조정 · 템플릿 관계 · 표 점검)에
  // 고친 문단을 확정하는 단추 — 「고친 문단」 탭의 「확정」 과 같은 함수(app.js commitQuick → commitDo). 고친 것이 없으면 꺼진 채 까닭
  const noCq = off || (!state.stored ? "이 작업은 저장이 꺼져 있어 확정할 수 없습니다" : !isDirty() ? "고친 것이 없습니다 — 조정의 「모두 반영」 이나 맞추기로 문서를 고친 뒤에 켜집니다" : state.commitBusy ? "적용하는 중입니다" : "");
  const cq = (where, key) => dashBtn(CQ_LABEL, () => dashExec(CQ_LABEL, () => commitQuick(where)), { disabled: !!noCq, focus: `act:${key}Commit`, title: noCq || cqTitle(state.edited.size) });
  L.steps.tree = { state: "", text: "", acts: [dashBtn("템플릿 관계 열기", () => tplRelOpen(), { focus: "act:tree",
    title: "문서 옆 열에 「템플릿 관계」 를 엽니다 — 남긴 줄 · 애매한 종속 제안 · 대표가 없는 레벨을 손으로 맞추거나 뗍니다(누른 단추에 따라 문서가 바뀜)" }), cq("헤딩 추출", "tree")] };
  L.steps.tableTools = { state: "", text: "", acts: [dashBtn("테이블 탭 열기", () => showTab(typeof dsTo === "function" ? dsTo("Tables") : "Tables"), { focus: "act:tableTools",
    title: "패널 「테이블」 — 표 하나씩 수식 판정 · 검산, 같은 자리(머리행 · 머리열 · 합계행)의 칸 서식 맞추기, 빈 필드 지우기" }), cq("표 점검", "tableTools")] };
  if (!S || S.none) return;
  const st = (k) => L.steps[k].state, open = (k) => raw(k).state === "todo" || raw(k).state === "fail"; // 단추를 보이는 때 — 결과가 없거나 실패(끝났거나 도는 중이면 없음)
  const hOff = (key) => (heads.view && typeof hrpOff === "function" && typeof hrpStep === "function" ? hrpOff(hrpStep(key)) : ""); // 단계별 실행이 못 돌리는 까닭(문단·라벨 결과 없음 …)
  const pick = (label, keys, focus, title) => { const no = off || hOff(dashStdKeys(keys)[0]); return dashBtn(label, () => dashExec(label, () => dashStdPick(keys)), { primary: st(focus.split(":")[1]) === "now" && !no, disabled: !!no, focus, title: no || title }); };
  if (open("heads")) L.steps.heads.acts.push(pick("헤딩 추출(스크립트)", ["s1", "s2"], "act:heads", "문단 · 라벨 → 헤딩 그래프를 스크립트로 다시 뽑습니다(무료 · 몇 초 · 문서는 안 바뀜)"));
  if (open("headsLlm")) L.steps.headsLlm.acts.push(pick("LLM 판정", ["l2"], "act:headsLlm", "스크립트가 판정하지 못한 첫머리의 규칙 보강 → 헤딩 판정 → 서식 정리 계획을 차례로 받습니다(유료 · 몇 분 · 문서는 안 바뀜)"));
  const noApply = off || (!S.judged ? "헤딩 LLM 판정 뒤에 합니다" : S.undecided ? `헤딩 판정에 미판정 ${nf(S.undecided)}곳이 있어 반영하지 않습니다 — 헤딩 판정을 다시 돌리거나 「계획 보기」 에서 확인합니다` : !S.can ? "반영할 계획 · 자리 맞춤이 없습니다" : "");
  if (st("adjust") !== "done" || S.can) L.steps.adjust.acts.push(dashBtn("모두 반영", () => dashExec("조정 — 모두 반영", dashStdApply), { primary: st("adjust") === "now" && !noApply, disabled: !!noApply, focus: "act:adjustApply",
    title: noApply || `받아 둔 서식 정리 계획을 에이전트가 고른 그대로 한 번에 반영합니다 — ${agwStdApplyText(S.P)}. 묻지 않고 바로 반영합니다(문서가 바뀜 · 실행 취소 한 번 · 계획은 「계획 보기」 에서 먼저)` }));
  L.steps.adjust.acts.push(dashBtn("계획 보기", () => tplPlanGo(), { focus: "act:adjustPlan",
    title: "헤딩 추출 탭 진행 줄의 「조정」 으로 — 「템플릿 조정」 · 「서식 조정」 칸을 누르면 템플릿 · 레벨마다 맞출 줄 · 뗄 줄 · 남긴 줄이 보입니다(문서는 안 바뀜)" }), cq("헤딩 추출", "adjust"));
  if (open("tables")) L.steps.tables.acts.push(pick("표 구조(스크립트)", ["s3"], "act:tables", "표마다 칸 역할(열헤더 · 행헤더 · 필드)을 스크립트로 다시 뽑습니다(무료 · 1초 안팎 · 문서는 안 바뀜)"));
  if (open("tablesLlm")) L.steps.tablesLlm.acts.push(pick("표 판정(LLM)", ["l3"], "act:tablesLlm", "표 묶음마다 서브 테이블 · 헤더 행/열 · 칸 역할을 LLM 이 칸의 값을 보고 판정합니다(유료 · 수 분 · 문서는 안 바뀜)"));
  const left = (gid) => (groups.find((g) => g.id === gid) || { keys: [] }).keys.some((k) => L.steps[k] && L.steps[k].state !== "done");
  const noH = off || (!left("heads") ? "남은 단계가 없습니다" : "");
  L.runs.heads = dashBtn("한 번에 진행", () => dashExec("2단계 헤딩 추출 — 한 번에 진행", () => headsRunAll({ commit: true })), { disabled: !!noH, focus: "run:heads", // commit = 끝에 고친 문단을 확정(spec_워크플로우 ② §18-24)
    title: noH || "헤딩 추출 탭의 「전체 실행」 — 남은 LLM 판정(헤딩 · 템플릿 — 표 판정(LLM)도 같이 돎 → 서식 정리 계획) → 조정(모두 반영)까지 차례로 합니다. 유료 LLM · 문서가 바뀜 · 끝나면 고친 문단을 확정(앞 상태는 「고친 문단」 탭 확정 기록의 복원)" });
  const tk = dashStdTableKeys(S), noT = off || (!tk.length ? "남은 단계가 없습니다" : "");
  L.runs.tables = dashBtn("한 번에 진행", () => dashExec("3단계 표 — 한 번에 진행", () => dashStdPick(tk)), { disabled: !!noT, focus: "run:tables",
    title: noT || `남은 표 단계를 차례로 — ${tk.map((k) => (k === "s3" ? "표 구조(스크립트)" : "표 판정(LLM)")).join(" → ")}(표 판정은 유료 LLM · 문서는 안 바뀜)` });
}

// 단계별 실행의 키 — 1단계(문단·라벨) 결과가 없으면 s1 을 앞에 붙인다(뒤 단계가 그 결과를 본다: heads_run_pick.js hrpOff — 검토 11-18: 전에는 「헤딩 추출(스크립트)」 가 s1 만 돌았다)
const dashStdKeys = (keys) => (heads.view && heads.view.stage1) || keys.includes("s1") ? keys : ["s1", ...keys];
async function dashStdPick(keys) { // 「단계별 실행」(headsPickRun — 유료 단계가 있으면 제 확인 창) → dashExec 의 끝 글 | null(그만둠 · 시작하지 않음 — 까닭은 알림 글)
  const id = state.id, epoch = state.epoch;
  await agwHeadsView(); // 헤딩 요약이 없으면 읽기만(추출을 시작하지 않음) — 단계별 실행이 1단계 결과를 본다
  if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 시작하지 않았습니다" };
  return (await headsPickRun(dashStdKeys(keys))) || null;
}

async function dashStdApply() { // 조정 「모두 반영」 — 진행 줄 「조정」 의 그 단추와 같은 함수(tpl_plan_bar.js tpbApply). **묻지 않는다** — 2026-11-18 사용자 「모두 반영할때... 팝업 알림 확인 받지마」(spec_hwpx_웹편집 ② §8-4) · 되돌림은 실행 취소 한 번 → dashExec 의 끝 글
  const id = state.id, epoch = state.epoch;
  const v = await agwStdFresh(); // 받아 둔 계획을 지금 것으로 — 지금 계획의 표시를 실어 보낸다(그 사이 다시 받은 계획이면 서버가 막는다)
  if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 반영하지 않았습니다" }; // 그 사이 연 문서의 계획을 묻지 않고 반영하지 않는다(검토 11-18)
  if (!v) return { ok: false, text: "분석 상태를 읽지 못했습니다 — 잠시 뒤 다시 누르세요" };
  const S = agwStdSteps(v);
  if (!S || !S.can) return { ok: false, text: S && S.judged && S.undecided ? S.steps.adjust.text : "반영할 계획 · 자리 맞춤이 없습니다 — 「계획 보기」 에서 확인합니다" };
  const r = await tpbApply(Object.keys(S.P.at).length ? { plans: S.P.at } : {});
  await agwStdFresh();
  return agwStdApplied(r);
}

function dashStdTop(M, L, st, S, groups) { // 머리 아래 「이어서 한 번에 N→3단계」(② §4 — 이관의 「이어서 한 번에」 와 같은 자리 · 같은 꼴). 남은 묶음이 둘 이상일 때. 1단계는 지원 양식일 때만 남은 것으로 센다(지원 안 되면 적용할 수 없다 — 2 · 3단계는 그대로)
  if (!S || S.none) return;
  const supported = !!(dv.view && dv.view.profile && dv.view.profile.supported);
  const left = (g) => (g.id === "config" ? supported && !!L.steps.apply && L.steps.apply.state !== "done" : g.keys.some((k) => L.steps[k] && L.steps[k].state !== "done"));
  const rest = groups.filter(left);
  if (rest.length < 2) return;
  const label = `이어서 한 번에 ${(rest[0].no || "").replace(/단계$/, "")}→${rest[rest.length - 1].no}`, one = rest[0].id === "config";
  const no = one && !st.facts.confirmed ? "프로젝트 구성 값을 먼저 확정하세요" // 값을 지어내지 않는다
    : DASH.busy || agwRunning() || (S && S.busy) || dv.busy || divRunLocked() ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : one ? divRunWhy() : "";
  M.top.push(dashBtn(label, () => dashStdChain(rest, label), { disabled: !!no, focus: "run:chain",
    title: no || `이어서 한 번에(누르면 바로 시작) — 앞 묶음이 끝나지 않으면 뒤 묶음은 시작하지 않습니다\n${rest.map((g) => `· ${DASH_STD_DOES[g.id] || `${g.no} ${g.name}`}`).join("\n")}\n${DASH_STD_DOES.end}` }));
  if (no) M.top.push(el("span", "dash-top-why", no)); // 꺼진 까닭을 글로(단추 title 만으로는 안 보인다)
}

// 묶음마다 할 일 — 「이어서 한 번에」 단추의 풍선 도움말(전에는 확인 창의 글)
const DASH_STD_DOES = { config: "1단계 프로젝트 구성 — 변경 계획 → 적용(문서가 바뀜). 계획 오류 · 미해결 자리가 있거나 기관의 차례가 마지막 반영과 다르면 적용하지 않고 멈춥니다.",
    heads: "2단계 헤딩 추출 — 전체 실행: 헤딩 LLM 판정(표 판정(LLM)도 같이) → 서식 정리 계획 → 조정 모두 반영(유료 LLM · 몇 분 · 문서가 바뀜). 헤딩 판정에 미판정이 있으면 반영하지 않고 멈춥니다.",
    tables: "3단계 표 — 남은 표 판정(LLM)(유료 · 수 분 · 문서는 안 바뀜).",
    end: "끝나면 고친 문단을 한 번 확정합니다(1단계에서 멈췄으면 하지 않음 · 앞 상태는 「고친 문단」 탭 확정 기록의 복원)." }; // end = 끝 확정(spec_워크플로우 ② §18-24)
// 「이어서 한 번에」 — 누르면 바로(확인 창 없음 — 2026-11-18) 묶음마다 그 묶음의 실행을 차례로(멈추는 검사 · LLM 연결 확인은 그 함수 그대로): 1단계 divRunAll → 2단계 headsRunAll → 3단계(표 판정이 남았으면) headsPickRun(["l3"]).
// 앞 묶음이 끝나지 않으면(멈춤 · 실패 · 계획 오류 · 미해결 — 1단계가 「적용」 까지 안 감) 뒤 묶음을 시작하지 않고, 머리 아래 끝 글에 한 것 · 멈춘 까닭 · 남은 것(② §4 · spec_작업에이전트 ② §7 ⓐ)
async function dashStdChain(rest, label) {
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 묶음마다 할 일(does)을 적은 확인 창: design.md §18 「확인 창」). 묶음마다 할 일(DASH_STD_DOES)은 단추의 풍선 도움말(dashStdTop)
  // 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」) — 묶음 함수에는 확정을 끄고(commit: false) 끝에 한 번: 끝까지 감 · 2 · 3단계에서 남김 같은 까닭(한도 · 미판정 · 남은 단계)으로 멈췄을 때만 ·
  // 1단계에서 멈췄으면 하지 않는다(계획이 남는다 — 확정은 그 계획을 비운다) · 다른 문서 · 시작 못 함 · 오류도 안 한다
  await dashExec(label, async () => {
    const id = state.id, epoch = state.epoch, here = () => state.id === id && state.epoch === epoch, did = [], gone = "다른 문서를 열어 멈췄습니다";
    let at = -1, soft = false; // 멈춘 묶음의 차례 · 그 까닭이 남김 같은 것인가(끝 확정을 한다)
    const stop = (i, why, left = false) => { at = i; soft = !!left; return { ok: false, text: `멈춤 — ${rest[i].no} ${rest[i].name}: ${why}${did.length ? ` · 한 것: ${did.join(" / ")}` : ""}`
      + `${i + 1 < rest.length ? ` · 시작하지 않은 것: ${rest.slice(i + 1).map((g) => `${g.no} ${g.name}`).join(" · ")}` : ""}` }; };
    const res = await (async () => { for (const [i, g] of rest.entries()) {
      if (!here()) return stop(i, gone);
      if (DASH.busy) { DASH.busy.label = `${label} — ${g.no} ${g.name}`; dashDraw(true); }
      if (g.id === "config") {
        const msg0 = dv.msg; // divRunAll 이 시작하지 못하고 돌아오면(도는 일 · 잠김 · 까닭) dv.msg 는 그대로다 — 앞서 남은 옛 멈춤 글을 이번 까닭으로 보이지 않게(검토 11-18)
        await divRunAll({ asked: true, commit: false });
        if (!here()) return stop(i, gone);
        if (!agwFitApplied().applied) return stop(i, `${dv.msg && dv.msg !== msg0 && dv.msg.kind === "halt" ? dv.msg.text.replace(/^멈춤 — /, "") : "「적용」 까지 가지 않았습니다(알림 글 참고)"} — 「작업 개요」 의 ① 변경 계획 보기 › ② 반영에서 보정합니다`);
        did.push(`${g.no} 적용함`);
      } else if (g.id === "heads") {
        const r = await headsRunAll({ asked: true }); // 확정은 이 고리의 끝에서 한 번(headsRunAll 의 commit 은 끔)
        const v = await agwStdFresh();
        if (!here()) return stop(i, gone);
        if (r && !r.ok) return stop(i, r.text, !!r.left);
        const S = v ? agwStdSteps(v) : null;
        if (!S) return stop(i, `${r ? `${r.text} — ` : ""}분석 상태를 읽지 못해 끝났는지 셀 수 없습니다(헤딩 추출 탭의 진행 줄을 보세요)`);
        // 전체 실행이 「끝까지 감」 이어도 2단계가 끝난 것은 아니다 — 서식 정리 계획을 일부 못 받았거나 같은 것이 남으면 그 까닭 없이 돌아온다(검토 11-18). 단계의 셈으로 다시 본다
        const left = ["heads", "headsLlm", "adjust"].find((k) => S.steps[k].state !== "done");
        if (left) return stop(i, `${r ? "" : "시작하지 못했습니다 — "}${AGW_STD_NAMES[left]}: ${S.steps[left].text || "남음"}${r ? "" : "(알림 글 참고)"}`, !!r);
        did.push(`${g.no} ${r ? r.text : "남은 것 없음"}`);
      } else if (g.id === "tables") {
        const S = agwStdSteps();
        if (S && S.steps.tablesLlm.state === "done") { did.push(`${g.no} 표 판정은 앞 묶음에서 같이 끝남`); continue; } // 2단계 전체 실행이 표 판정도 같이 돌린다
        await agwHeadsView();
        if (!here()) return stop(i, gone); // 그 사이 연 문서에 유료 실행을 걸지 않는다(검토 11-18)
        const r = await headsPickRun(dashStdKeys(["l3"]), { asked: true });
        await agwStdFresh();
        if (!here()) return stop(i, gone);
        if (!r) return stop(i, "시작하지 못했습니다 — 알림 글을 보세요(LLM 연결 · 다른 헤딩 작업)");
        if (!r.ok) return stop(i, r.text, true); // 표 판정이 답을 못 냄 — 스크립트 결과로 남긴다(남김 같은 끝)
        did.push(`${g.no} ${r.text}`);
      } else return stop(i, "모르는 묶음입니다 — 페이지를 새로 고치세요(서버의 등록부와 화면이 다른 판)"); // 모르는 묶음을 조용히 「끝남」 으로 넘기지 않는다
    }
    return { ok: true, text: `끝남 — ${did.join(" / ")}` }; })();
    if (here() && (res.ok || (soft && at >= 0 && rest[at].id !== "config"))) { // 끝 확정 — 1단계에서 멈춘 고리는 하지 않는다
      const tail = await commitAfterRun(label, { quiet: true });
      if (tail) res.text = `${res.text} · ${tail}`;
    }
    return res;
  });
}

// 붙박이 이관 · 표준 차례로 조립한 이관형의 「한 문서만」(② §18-21) — 이 가지는 단계를 화면이 세지만(taskSteps), 한 문서만의 몫(남은 수 · 켜짐 · 까닭)은 서버가 센다: 그 묶음의 서버 상태에서 stages 만 읽어 둔다
// (10초 안의 것은 다시 읽지 않는다 · 읽으면 다시 그린다 · DASH.flow — 줄 목록 가지의 읽어 둔 상태 — 와 따로). → 묶음들 | null(아직 못 읽음)
function dashSoloRead(wid) {
  const key = `${state.id}|${wid}`;
  if (!DASH.solo || DASH.solo.key !== key) DASH.solo = { key, at: 0, stages: null, loading: false };
  const S = DASH.solo;
  if (!S.loading && Date.now() - S.at >= 10000) {
    S.loading = true;
    flowGet(wid).then((v) => v, () => null).then((v) => {
      S.loading = false;
      if (DASH.solo !== S) return;
      const was = JSON.stringify(S.stages && S.stages.map((g) => g.solo));
      Object.assign(S, { at: Date.now(), stages: v && v.stages ? v.stages : null });
      const pane = $("paneDash");
      if (pane && !pane.hidden && JSON.stringify(S.stages && S.stages.map((g) => g.solo)) !== was) dashDraw();
    });
  }
  return S.stages;
}
// 도는 서버 실행의 거울(taskRun)이 **다른 문서만 잡은 실행**인가 — 그러면 이 문서(role)의 실행은 같이 돈다(문서마다 따로 도는 실행: spec_워크플로우 ② §18-22). 거울이 없으면 거짓(그냥 시작한다)
const dashBeside = (role) => !!(typeof taskRun !== "undefined" && taskRun && taskRun.server && taskRun.lane && role && taskRun.lane !== role);
async function dashRelaySolo(g, role, label = "") { // 그 묶음을 한 문서만 서버 실행으로(「작업 개요」 의 서버 실행 길 그대로 — workflow_exec.js taskRunServer: 거울 · 끝 글은 그 길의 것) → dashExec 의 끝 글 | null
  const [plan, report] = taskSlots().map((k) => taskSlotDoc(k));
  if (!plan || !report) return { ok: false, text: "두 칸(사업계획서 · 연차보고서)에 문서를 먼저 고르세요" };
  const side = dashBeside(role); // 다른 문서의 실행이 도는 중 — 이 문서의 실행을 같이 시작한다(거울은 그대로 두고 곁에서 지켜본다)
  if (taskRun && !side) return { ok: false, text: "지금 진행 중인 작업이 끝난 뒤에 누르세요" };
  const r = await taskRunServer(g, plan, report, { role, side });
  if (DASH.solo) DASH.solo.at = 0; // 끝난 뒤의 남은 수를 다시 읽게
  if (r === null) return { ok: false, text: "이 묶음은 아직 서버가 맡지 않습니다 — 한 문서만 진행은 서버 실행에서만 합니다" };
  if (r.side) { flowSideWatch(report.id, r.side, label); return { ok: true, text: `${label || "한 문서만"} — 시작했습니다(서버에서 진행 · 다른 문서의 실행과 같이 돕니다)` }; }
  if (r.follow) { r.follow().then(() => { if (DASH.solo) DASH.solo.at = 0; dashDraw(true); }, (e) => console.warn(e)); return null; } // 시작까지만 기다린다 — 따라가는 동안 다른 문서의 「한 문서만」 을 누를 수 있게(거울이 그 밖의 단추를 끈다) · 끝 글은 그 묶음의 끝 글 줄에(taskRunFollow)
  return r.ok === false ? { ok: false, text: r.text || "시작하지 못했습니다" } : null;
}

function dashRelayLive(M) { // 이관 — 「작업 개요」 의 단계(taskSteps)와 묶음(TASK_STAGES)
  const L = { steps: {}, runs: {} };
  if (!taskSlots()) { M.notes.push({ text: "이 작업에는 이관의 첨부 파일 칸이 없습니다" }); return L; }
  // 셈은 app.js taskStepsCalc 와 같은 함수(taskStepsOf — 이 TASK 의 묶음 · 문서마다 고른 대로 할 문서가 있는 단계만: spec_워크플로우 ② §15) — 그쪽의 taskStepsLast 를 건드리지 않으려고 따로 센다(단추도 새로 받은 것)
  const steps = taskStepsOf();
  const active = taskRun ? taskRun.key : (steps.find((s) => s.busy) || {}).key;
  for (const s of steps) {
    const acts = s.st === "now" || s.st === "ready" || (s.keep && s.st === "done") ? s.acts : []; // 단추를 보이는 때 — taskStepsEl 과 같다
    acts.forEach((b, i) => { b.dataset.dashFocus = `act:${s.key}:${i}`; });
    L.steps[s.key] = { state: active === s.key ? "run" : s.st, text: s.st === "todo" ? "" : dashHere(s.text), acts: [...acts] };
  }
  // 등록부의 선택 단계 — 「작업 개요」 는 그 줄의 단추로 함께 한다: 구성 불러오기 = 「프로젝트 구성 추출」 줄(spec_작업 ② §21) · 자리 연결 LLM 검토 = ② · 표 대응 · 빈 자리 검토 = ③.
  // 헤딩 · 표의 LLM 검증·보완(headsLlm · reheadsLlm)은 제 줄이 있는 단계다(위 taskSteps 의 줄 그대로)
  Object.assign(L.steps, { configLoad: { via: "config" }, llm: { via: "link" }, tableMap: { via: "plan" }, gaps: { via: "plan" } });
  const files = steps.find((s) => s.key === "files");
  if (files && !files.done) L.steps.files.acts.push(dashBtn("「작업 개요」 의 칸 열기", () => showTab("Div"), { primary: true, title: "첨부 파일 칸에서 사업계획서 · 연차보고서를 고르거나 올립니다", focus: "act:files" }));
  const config = steps.find((s) => s.key === "config");
  if (config && !config.done && files && files.done) L.steps.config.acts.push(dashBtn("입력 칸 열기", () => showTab("Div"), { title: "「작업 개요」 의 프로젝트 구성 입력 칸 · 불러오기 — 값을 고칠 때", focus: "act:configInput" }));
  const report = taskSlotDoc("report"), left = steps.some((s) => !s.done && !s.soon && s.key !== "files");
  if (report && report.id !== state.id && left) M.notes.push({ text: "이 문서는 원본 문서(사업계획서)입니다 — 이관은 연차보고서(목적 문서)에서 진행합니다", act: dashBtn(`연차보고서 「${report.name}」 열기`, () => dashOpen(report.id), { focus: "act:target" }) });
  const work = (g) => steps.filter((s) => g.keys.includes(s.key) && !s.soon && s.key !== "files"); // 묶음의 세는 단계(app.js taskStageWork 와 같다)
  TASK_STAGES.forEach((g, i) => { // 묶음 머리의 「한 번에 진행」 — 켜는 조건은 「작업 개요」 의 묶음 머리와 같다(taskStageSync1)
    const next = work(g).find((s) => !s.done), before = TASK_STAGES.slice(0, i).find((x) => work(x).some((s) => !s.done)), busy = steps.some((s) => g.keys.includes(s.key) && s.busy);
    const no = taskRun ? "다른 진행이 끝난 뒤 쓸 수 있습니다" : taskResetting ? "초기화가 끝난 뒤 쓸 수 있습니다" : busy ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다"
      : !(files && files.done) ? "두 칸(사업계획서 · 연차보고서)에 문서를 먼저 고르세요" : before ? `${before.no} 「${before.name}」 ${typeof taskJosa === "function" ? taskJosa(before.name, "을", "를") : "을"} 먼저 끝내세요` : !next ? "남은 단계가 없습니다" : "";
    L.runs[g.id] = dashBtn("한 번에 진행", () => taskRunAll(g.id), { disabled: !!no, focus: `run:${g.id}`, title: no || `이 묶음의 남은 단계를 차례로 한 번에 — ${g.does}. 사람 손이 필요한 곳에서는 멈춥니다` });
    // 한 문서만 진행(spec_워크플로우 ② §18-21) — 그 묶음에서 그 문서의 줄만: 남은 수 · 켜짐은 서버가 센 것(dashSoloRead — 이 가지의 단계 셈은 전처럼 화면의 것). 서버가 맡은 묶음에만 선다
    const sv = report && files && files.done ? (dashSoloRead(report.id) || []).find((x) => x.id === g.id && x.server) : null;
    // 도는 실행이 다른 문서만 잡았으면 이 문서의 단추는 켜 둔다(같이 돈다 — ② §18-22: 켜짐 · 까닭은 서버가 센 solo 의 것)
    if (sv) (L.subs ||= {})[g.id] = dashSoloEl(sv, `${g.no} ${g.name}`, {
      busyOf: (role) => (taskRun && !dashBeside(role) ? "다른 진행이 끝난 뒤 쓸 수 있습니다" : taskResetting ? "초기화가 끝난 뒤 쓸 수 있습니다" : DASH.busy ? `「${DASH.busy.label}」 이 끝나면 쓸 수 있습니다` : flowSideOf(report.id, role) ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : ""),
      run: (role, label) => dashExec(label, () => dashRelaySolo(g, role, label), { over: dashBeside(role) }) });
  });
  const plan0 = taskSlotDoc("plan");
  L.ends = {};
  for (const g of TASK_STAGES) { // 묶음의 마지막 「한 번에 진행」 의 끝 — 그 뒤 더 나아가지 않았을 때만 · 「끝남」 은 남은 단계가 없을 때만(「분석」 처럼 단계 하나만 돈 실행 뒤 — taskStageSync1 과 같은 조건)
    const end = taskRunEnds[g.id];
    if (end && !taskRun && report && end.report === report.id && plan0 && end.plan === plan0.id && end.done === work(g).filter((s) => s.done).length && (!end.ok || work(g).every((s) => s.done))) L.ends[g.id] = { ok: !!end.ok, text: end.text };
  }
  const rest = TASK_STAGES.filter((g) => work(g).some((s) => !s.done)); // 이어서 한 번에(「작업 개요」 의 이어 진행 줄과 같은 범위 — 할 일이 남은 첫 묶음 → 끝 묶음)
  if (rest.length > 1 && files && files.done) {
    const label = `${rest[0].no.replace(/단계$/, "")}→${rest[rest.length - 1].no}`, busy = steps.some((s) => s.busy);
    M.top.push(dashBtn(`이어서 한 번에 ${label}`, () => taskRunAll(rest[0].id, rest[rest.length - 1].id), { disabled: !!taskRun || !!taskResetting || busy, focus: "run:chain",
      title: `${rest.map((g) => `${g.no} 「${g.name}」`).join(" → ")} 을 이어서 한 번에 — 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다` }));
  }
  return L;
}

function dashGatherLive(M) { // 취합 — 「작업 개요」 의 단계(gatherSteps)와 묶음(GT_STAGES). 3단계는 기관 문서마다 되풀이 — 등록부의 단계는 차례만, 상태 · 단추는 기관 문서 줄에
  const L = { steps: {}, runs: {}, parts: [] }, plan = gatherPlan(), V = plan ? gt().view : null, Q = typeof gqRun !== "undefined" && gqRun && plan && gqRun.plan === plan.id ? gqRun : null;
  let open = true;
  const steps = gatherSteps().map((s) => { // 셈은 gather.js gatherCalc 와 같다(그쪽의 gatherStepsLast 를 건드리지 않는다)
    const st = s.done ? "done" : open ? "now" : s.early ? "ready" : s.hold ? "hold" : "todo";
    if (!s.done) open = false;
    return { ...s, st };
  });
  const active = gatherRun ? gatherRun.key : "";
  const actsOf = (s) => (s.st === "now" || s.st === "ready" || s.st === "hold" || (s.keep && s.st === "done") ? s.acts : []).map((a, i) => { const b = gatherActEl(a, s.st === "now"); b.dataset.dashFocus = `act:${s.key}:${i}`; return b; });
  const lines = (s) => (s.st === "todo" ? [] : s.lines.map(([n, t]) => [n, dashHere(t)]));
  for (const s of steps.filter((x) => x.step !== "part")) L.steps[s.key] = { state: active === s.key || s.busy ? "run" : s.st, lines: lines(s), acts: actsOf(s) };
  if (L.steps.files && L.steps.files.state !== "done") L.steps.files.acts.push(dashBtn("「작업 개요」 의 칸 열기", () => showTab("Div"), { primary: true, title: "취합본 칸에서 사업계획서(취합본)를 고르거나 올립니다", focus: "act:files" }));
  if (L.steps.config && L.steps.config.state !== "done" && plan) L.steps.config.acts.push(dashBtn("입력 칸 열기", () => showTab("Div"), { title: "「작업 개요」 의 프로젝트 구성 입력 칸 · 불러오기 — 값을 고칠 때", focus: "act:configInput" }));
  const F = V && V.frame, hand = { state: "", text: "앱 밖의 일 — 배포 기준본을 내려받아 기관에 나눠 주고, 기관이 채워 돌려준 문서를 아래 「기관 문서」 로 올립니다", acts: [] };
  if (F) { const a = el("a", "btn sm", "기준본 내려받기"); a.href = gatherUrl("/frame/file"); a.setAttribute("download", ""); a.dataset.dashFocus = "act:handFile"; a.title = "고정해 둔 기준본 파일(hwpx) — 기관에 나눠 주는 파일" + (F.stale ? "(낡은 판)" : ""); hand.acts.push(a); }
  L.steps.hand = hand;
  for (const k of ["part", "heads", "link", "llm", "plan", "apply", "drop"]) L.steps[k] = { state: "each" };
  for (const s of steps.filter((x) => x.step === "part")) L.parts.push({ key: s.key, no: s.no, name: s.name, state: active === s.key || s.busy ? "run" : s.st, lines: lines(s), acts: actsOf(s) });
  const frameOk = !!(F && !F.stale);
  L.partsAdd = dashBtn("기관 문서 올리기…", () => gatherPickFiles((fs) => gatherUploadMany(fs)), { disabled: !plan || !frameOk || !!gatherRun || !!(Q && Q.busy), focus: "act:partsAdd",
    title: !plan ? "사업계획서(취합본)를 먼저 고르세요" : !frameOk ? "배포 기준본을 먼저 만드세요 — 기관 문서는 기준본과 견줍니다" : "기관이 채워 돌려준 문서(hwp · hwpx)를 올려 이 취합에 넣습니다 — 반영할 기관은 줄마다 「작업 개요」 의 기관 문서 줄에서 고릅니다" });
  if (plan && plan.id !== state.id && steps.some((s) => !s.done && s.step !== "files")) M.notes.push({ text: "이 문서는 기관 문서(원본)입니다 — 취합은 취합본(목적 문서)에서 진행합니다", act: dashBtn(`취합본 「${plan.name}」 열기`, () => dashOpen(plan.id), { focus: "act:target" }) });
  const lost = Q ? Q.items.filter((it) => !it.pid && it.err && !it.skip).length : 0; // 간단 모드가 멈췄거나 못 올린 문서가 남았다 — 에이전트의 「간단 모드 이어서」 와 같은 행동
  if (Q && !Q.busy && Q.end && !Q.uploadOnly && (!Q.end.ok || lost)) {
    const does = `멈춘 곳부터 남은 일을 끝까지 이어서 합니다${lost ? ` — 못 올린 문서 ${lost}개를 다시 올리고` : ""}(앞서 넣은 것은 다시 넣지 않음 · 기관 문서마다 편집 한 번${Q.llm ? " · 유료 LLM 검토 포함" : ""})`;
    M.notes.push({ text: `간단 모드 ${Q.end.ok ? "끝남" : "멈춤"} — ${Q.end.text}`, warn: !Q.end.ok, act: dashBtn("간단 모드 이어서", () => dashExec("간단 모드 이어서", () => agwExec("quick:resume")), { title: `${does} — 취합본이 바뀝니다(묶음째 실행이 끝나면 고친 문단을 확정 — 앞 상태는 「고친 문단」 탭 확정 기록의 복원)`, focus: "act:quick" }) }); // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」)
  }
  const E = typeof gatherRunLast !== "undefined" ? gatherRunLast : null; // 마지막 「한 번에 진행」 의 끝 — 그 뒤 더 나아가지 않았을 때만(gather.js 상태 줄과 같은 조건)
  if (E && !gatherRun && plan && E.plan === plan.id && E.done === steps.filter((s) => s.stage === E.stage && s.step !== "files" && s.done).length) // 조립 도구의 줄(DASH_GATHER_SERVER)을 돈 실행이면 그 줄이 든 정의 묶음에(화면의 묶음 map 으로 따라갔다)
    L.ends = { [(DASH_GATHER_SERVER.has(E.key) && gatherDefStage(E.stage, agwJob(), E.key)) || gatherDefStage(E.stage, agwJob()) || E.stage]: { ok: !!E.ok, text: E.text } };
  const srv = dashGatherServer(M, L, plan, Q); // 화면의 셈에 없는 조립 도구(서버가 센 상태 · 서버 실행) — 그 줄이 정의에 없으면 null
  const linked = new Set();
  GT_STAGES.forEach((g, i) => { // 묶음 머리의 「한 번에 진행」 — gatherRunAll(확인 창 없이)
    const left = (x) => steps.filter((s) => s.stage === x.id && !s.done && s.step !== "files"), before = GT_STAGES.slice(0, i).find((x) => left(x).length);
    const gid = gatherDefStage(g.id, agwJob()); // 그 묶음의 등록부 id — 붙박이는 그대로 · 취합형으로 조립한 것은 그 일을 하는 줄이 든 묶음(없으면 단추를 달지 않는다)
    const rest = srv && gid ? srv.left(gid) : []; // 그 묶음에 함께 놓은 조립 도구 가운데 안 끝난 줄(화면의 셈이 다 끝나도 서버 실행으로 그 줄을 한다)
    const no = gatherRun ? "다른 묶음이 진행 중입니다" : Q && Q.busy ? "간단 모드가 도는 중입니다" : !plan ? "사업계획서(취합본)를 먼저 고르세요" : before ? `${before.no} 「${before.name}」 ${typeof taskJosa === "function" ? taskJosa(before.name, "을", "를") : "을"} 먼저 끝내세요` : !left(g).length && !rest.length ? "남은 단계가 없습니다"
      : !left(g).length ? srv.why(gid) : ""; // 조립 도구의 줄만 남음 — 묶음째 서버 실행이라 서버가 센 그 묶음의 can · why 를 따른다(srv.runs 와 같다)
    if (gid) linked.add(gid);
    // 화면의 줄이 다 끝나 조립 도구의 줄만 남았어도 묶음째 서버 실행(from = 그 정의 묶음 · only 없음 — 끝난 줄 · 넣을 것이 없는 기관 문서는 서버가 건너뛰고, 끝나면 고친 문단을 확정: spec_병합 ② §5-9 9 ⓒ · spec_워크플로우 ② §18-24).
    // 그 줄 하나만(only — 확정 없음)은 그 줄의 「이 단계만 진행」 이다
    if (gid) L.runs[gid] = dashBtn("한 번에 진행", () => (left(g).length || !rest.length ? gatherRunAll(g.id) : srv.run(gid, rest[0], `${g.no} ${g.name} — 한 번에 진행`, {})), { disabled: !!no, focus: `run:${gid}`, title: no || `이 묶음의 남은 단계를 차례로 한 번에 — ${g.does}. 사람 손이 필요한 곳에서는 멈춥니다` });
  });
  if (srv) srv.runs(linked); // 화면의 묶음에 잇지 않은 정의 묶음(그 도구 · 사람이 하는 일만 든 묶음)의 「한 번에 진행」
  return L;
}

// 서버가 센 상태로 그리는 취합의 줄 — 화면의 취합 셈(gather.js gatherSteps · GT_STAGES)에 없는 조립 도구(「넣은 뒤 템플릿 · 서식 정리」 retidy — spec_병합 ② §5-9 9 · 붙박이 취합의 차례에는 없다).
// 상태 = 서버(GET …/flow — dashFlow · 첫 화면의 대시보드와 같은 값) · 실행 = 서버 실행기(workflow_exec.js gatherRunServer — 줄 하나는 only). **서버가 취합 가족에 이런 줄을 더하면 이 표도 함께 본다**(그림만 있고 누를 수 없는 줄을 두지 않는다)
// gather.js(gatherServerView · gatherServerRest — 「한 번에 진행」 · 간단 모드 · 에이전트가 화면의 줄만 보고 묶음을 끝난 것으로 보지 않게)도 이 표를 읽는다
const DASH_GATHER_SERVER = new Set(["retidy"]);

function dashGatherServer(M, L, plan, Q) { // → {left(gid) → [안 끝난 그 줄 key], run(gid, key, label, opt), runs(linked), why(gid) → 묶음째 실행을 못 하는 까닭 | ""} | null(그 줄이 정의에 없음) — L.steps[key] 에 상태 · 「이 단계만 진행」 을 채운다
  const regs = M.reg ? M.reg.stages : [];
  if (!regs.some((g) => g.steps.some((s) => DASH_GATHER_SERVER.has(s.key)))) return null;
  const F = dashFlow(), V = F.view, last = GT_STAGES[GT_STAGES.length - 1];
  const moving = !!gatherRun || (!!V && (flowActive(V.run) || V.stages.some((g) => (g.steps || []).some((s) => s.busy || s.st === "run"))));
  if (!F.loading && (F.stale || Date.now() - F.at >= (moving ? 3000 : 10000))) dashFlowRead(); // 기다리지 않는다 — 읽으면 다시 그린다
  const busy = typeof gatherRunStarting !== "undefined" && gatherRunStarting;
  const off = gatherRun || busy ? "다른 묶음이 진행 중입니다" : Q && Q.busy ? "간단 모드가 도는 중입니다" : !plan ? "사업계획서(취합본)를 먼저 고르세요" : DASH.busy ? `「${DASH.busy.label}」 이 끝나면 쓸 수 있습니다` : V && !V.ready ? V.why || "문서 칸이 비었습니다" : "";
  const at = (gid, key) => { const g = V && (V.stages || []).find((x) => x.id === gid); return g ? (g.steps || []).find((y) => y.key === key) || null : null; };
  const run = (gid, key, label, opt) => dashExec(label, async () => { // 서버 실행을 시작하고 끝까지 따라간다(끝 글은 gatherRunEnd 가 상태 줄 · 알림에) → 읽어 둔 서버 상태를 다시
    gatherRunStarting = true;
    let r = null;
    try { r = await gatherRunServer(last, plan, { ...opt, from: gid }, key); } finally { gatherRunStarting = false; } // from = 그 줄이 든 정의 묶음(같은 도구를 두 묶음에 놓았어도 누른 묶음에서)
    dashFlowTouch(state.id);
    return r;
  });
  for (const g of regs) for (const s of g.steps) {
    if (!DASH_GATHER_SERVER.has(s.key) || L.steps[s.key]) continue;
    const x = at(g.id, s.key);
    if (!x) { L.steps[s.key] = { state: "", text: F.err ? `상태를 읽지 못했습니다: ${F.err}` : V ? "" : "상태를 읽는 중…", acts: [] }; continue; }
    const runs = x.st === "run" || (!!gatherRun && gatherRun.key === s.key), st = runs ? "run" : x.done ? "done" : x.st === "blocked" || x.st === "failed" ? "hold" : x.st === "now" ? "now" : "todo";
    const acts = x.done || runs ? [] : [dashBtn(DASH_SINGLE_ONE, () => run(g.id, s.key, `${s.name} — ${DASH_SINGLE_ONE}`, { only: s.key }), { primary: st === "now" && !off, disabled: !!off, focus: `act:${s.key}:only`,
      title: off || ["이 단계만 진행합니다 — 서버에서 진행합니다(창을 닫아도 이어집니다). 넣은 내용이 없으면 건너뜁니다.", s.change === "doc" ? "취합본이 바뀝니다(취합본에 있던 줄은 그대로)" : "문서는 바뀌지 않습니다"].join("\n") })];
    L.steps[s.key] = { state: st, text: dashHere(x.text || ""), acts, word: runs ? DASH_ST.run : x.done ? (x.skipped ? "건너뜀" : DASH_ST.done) : FLOW_WORD[x.st] || "", ...(x.done && x.skipped ? { skipped: true } : {}) };
  }
  const left = (gid) => ((regs.find((g) => g.id === gid) || { steps: [] }).steps).filter((s) => DASH_GATHER_SERVER.has(s.key) && !(at(gid, s.key) || {}).done).map((s) => s.key);
  // 그 정의 묶음의 묶음째 서버 실행을 못 하는 까닭 | "" — 서버가 센 그 묶음의 can · why 를 따른다(취합형은 앞 묶음이 모두 끝나야 돈다 — workflow_state._feeds: 안 그러면 누르면 「남김 — … 이 덜 끝났습니다」 로만 끝난다) · 그 줄 하나는 줄의 「이 단계만 진행」(only — 앞 묶음을 기다리지 않음)
  const why = (gid) => {
    const row = V && (V.stages || []).find((x) => x.id === gid), early = !!row && (row.after || []).some((id) => ((V.stages || []).find((x) => x.id === id) || {}).left);
    return off || (!row ? (F.err ? `상태를 읽지 못했습니다: ${F.err}` : "상태를 읽는 중…") : !row.can ? (row.why || "지금은 이 묶음을 시작할 수 없습니다") + (early ? ` — 이 줄만은 그 줄의 「${DASH_SINGLE_ONE}」 으로 할 수 있습니다` : "") : "");
  };
  const runs = (linked) => { // 화면의 묶음에 잇지 않은 정의 묶음 — 그 도구 · 사람이 하는 일만 든 묶음(다른 줄이 섞였으면 그 줄을 화면이 모른다: 단추를 달지 않는다)
    for (const g of regs) {
      if (linked.has(g.id) || L.runs[g.id] || !g.steps.some((s) => DASH_GATHER_SERVER.has(s.key)) || !g.steps.every((s) => DASH_GATHER_SERVER.has(s.key) || s.key === "files" || dashHandKey(s.key))) continue;
      const rest = left(g.id), name = `${g.no || ""} ${g.name || ""}`.trim();
      const no = !rest.length ? off || "남은 단계가 없습니다" : why(g.id);
      L.runs[g.id] = dashBtn("한 번에 진행", () => run(g.id, rest[0], `${name} — 한 번에 진행`, {}), { disabled: !!no, focus: `run:${g.id}`,
        title: no || `이 묶음의 남은 단계를 차례로 한 번에 — ${g.does || name}. 사람 손이 필요한 곳에서는 멈춥니다(서버에서 진행 · 창을 닫아도 이어집니다)` });
    }
  };
  return { left, run, runs, why };
}

function dashStyleLive() { // 서식 복사 — 문서 옆 「서식 복사」 열의 단계(slStepState: ① 후보 찾기 ② LLM 검토 ③ 저장 ④ PDF 검증). 후보를 고르는 일은 그 열에서
  const L = { steps: { open: { state: "done", text: "" } }, runs: {} }, S = STYLE.save, on = !!S && styleSaveOn(), st = on ? slStepState(S) : null;
  const pairs = [["find", "find"], ["review", "name"], ["save", "save"], ["verify", "verify"]];
  let open = true;
  for (const [k, x] of pairs) {
    const v = st ? st[x] : "todo", state = v === "run" ? "run" : v === "done" ? "done" : open ? "now" : "todo";
    if (v !== "done" && k !== "review") open = false; // ② LLM 검토는 안 해도 된다 — 「지금」 을 붙들지 않는다
    L.steps[k] = { state: k === "review" && v !== "done" && v !== "run" ? "" : state, text: "", acts: [] };
  }
  const openBtn = (label, primary) => dashBtn(label, () => styleSaveOpen(), { primary, title: "문서 옆에 「서식 복사」 열을 열고 이 문서의 서식 후보를 찾습니다(문서는 바뀌지 않습니다)", focus: `act:styleOpen:${label}` });
  if (!on) { L.steps.find.text = "문서 옆 「서식 복사」 열을 열면 서식 후보를 찾습니다"; L.steps.find.acts.push(openBtn("「서식 복사」 열 열기", true)); }
  else {
    if (S.err) L.steps.find.text = S.err;
    const can = S.rows.some((r) => r.kind !== "paras" && r.state !== "done"), busy = !!(S.auto || S.busy || S.llm || S.loading);
    L.steps.review.text = S.llm ? "LLM 이 후보를 검토하는 중" : S.named ? "검토함" : "안 해도 사람이 골라 저장할 수 있습니다";
    L.steps.review.acts.push(dashBtn("LLM 검토", () => styleSaveName(), { disabled: busy || !can, focus: "act:styleReview", title: "후보마다 저장할 만한가 · 이름 · 역할을 LLM(유료 · 수십 초)이 검토합니다 — 서식 값은 만들지 않고, 확신이 없으면 의심으로 표시합니다" }));
    L.steps.save.text = "후보는 문서 옆 「서식 복사」 열에서 골라 「고른 n개 저장」 합니다";
  }
  L.steps.verify.acts.push(dashBtn("서식 관리자 열기", () => styleLibOpen(), { title: "저장한 서식과 형식마다의 PDF 검증 기록을 봅니다", focus: "act:styleLib" }));
  L.steps.use = { state: "", text: "", acts: [dashBtn("서식 관리자 열기", () => styleLibOpen(), { title: "저장한 서식을 다른 문서에 적용합니다(그 워크플로우의 원본 문서에는 적용하지 않음)", focus: "act:styleUse" })] };
  const busy = on && !!(S.auto || S.busy || S.llm || S.loading);
  L.runs.copy = on ? dashBtn("한 번에 진행", () => styleSaveAuto(), { disabled: busy || !!S.err, focus: "run:copy", title: S.err ? "후보를 찾지 못했습니다 — 열의 글을 보세요" : "② LLM 검토 → ③ 저장 → ④ PDF 검증을 잇습니다(문서는 바뀌지 않음) — 의심 · 고침이 없는 추천만 저장하고 나머지는 남깁니다" })
    : openBtn("「서식 복사」 열 열기", false);
  return L;
}

function dashEditLive() { // 문서 일반 편집 — 단계의 끝을 세지 않는다(요청 → 제안 → 반영의 되풀이). 단추는 그 일을 하는 곳을 연다
  const agent = (focus) => (toolShown("Agent") ? [dashBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "에이전트 창(상단 바의 에이전트 아이콘과 같음) — 자료를 주고 글로 요청하면 제안이 나옵니다", focus })] : []);
  return { runs: {}, steps: { open: { state: "done", text: "" }, material: { state: "", acts: agent("act:material") }, turn: { state: "", acts: agent("act:turn") }, check: { state: "", text: "제안마다 저절로 돕니다" },
    apply: { state: "", text: "제안 카드의 「문서에 반영」 을 누른 제안만 들어갑니다", acts: agent("act:apply") },
    styleSave: { state: "", acts: [dashBtn("서식 관리자 열기", () => styleLibOpen(), { title: "반영한 표나 이 문서의 서식을 저장해 다시 씁니다", focus: "act:styleSave" })] },
    tables: { state: "", text: "표 손잡이(표 오른쪽 여백)의 메뉴에서 엽니다" } } };
}

// 사람이 하는 일(정의 v2 의 hand 줄 — spec_워크플로우 ② §18-7 · §18-12 ⑦): 상태 · 판은 서버(GET /api/works/{wid}/flow/hand — 3초 안의 것은 다시 읽지 않는다) · 「했음」 · 「했음 취소」 는 사람의 단추만(에이전트 행동에는 없다).
// 끝남 = 그 줄이 지금 판(정의 지문 + 줄의 글)으로 「했음」 — 글을 고치면 다시 눌러야 한다. 실행은 그 줄에서 멈추고(「사람이 할 일 — …」) 「했음」 뒤 「이어서」 로 지나간다(서버 실행기).
const dashHandKey = (k) => /^hand[1-9][0-9]?$/.test(k);
async function dashHands(M, L) {
  if (!state.id || !M.reg || !M.reg.stages.some((g) => g.steps.some((s) => dashHandKey(s.key)))) return;
  const H = DASH.hands;
  if (!H || H.id !== state.id || Date.now() - H.at > 3000) {
    try { DASH.hands = { id: state.id, at: Date.now(), lines: (await api(`/api/works/${state.id}/flow/hand`)).lines || [] }; } catch { DASH.hands = { id: state.id, at: Date.now(), lines: [] }; }
  }
  for (const ln of DASH.hands.lines) {
    const act = ln.done ? dashBtn("했음 취소", () => dashHand(ln, false), { focus: `hand:${ln.key}`, title: "「했음」 을 되돌립니다 — 다음 실행이 이 줄에서 다시 멈춥니다" })
      : dashBtn("했음", () => dashHand(ln, true), { primary: true, focus: `hand:${ln.key}`, title: "이 일을 마쳤으면 누릅니다 — 묶음의 「한 번에 진행」(이어서)이 이 줄을 지나 다음 줄로 갑니다" });
    L.steps[ln.key] = { state: ln.done ? "done" : "now", text: ln.done ? `${ln.name} — 사람이 확인함` : `사람이 할 일 — ${ln.does}`, acts: [act] };
  }
}
async function dashHand(ln, on) {
  DASH.hands = null; // 누른 뒤 다시 읽는다
  Object.assign(DASH, { open: ln.key, pin: true }); // 누른 카드는 그 누름으로 「지금」 이 넘어가도 그 한 번은 접지 않는다(「했음 취소」 가 보이게 — 첫 화면의 대시보드 HD.pin 과 같은 약속: dashDraw)
  return dashExec(on ? `「${ln.name}」 했음` : `「${ln.name}」 했음 취소`, async () => {
    try { await api(`/api/works/${state.id}/flow/hand/${encodeURIComponent(ln.key)}`, on ? { method: "POST", headers: H_JSON, body: JSON.stringify({ ver: ln.ver }) } : { method: "DELETE" }); }
    catch (e) { return { ok: false, text: `${on ? "「했음」" : "「했음 취소」"}을 적지 못했습니다 — ${e.message}` }; }
    dashFlowTouch(state.id); // 문서 하나로 조립한 것 — 읽어 둔 서버 상태(그 줄의 끝남 · 묶음의 「한 번에 진행」)를 다시 읽게(그 밖의 워크플로우에는 읽어 둔 것이 없다)
    return { ok: true, text: on ? `「${ln.name}」 — 했음(이어서 진행하면 다음 줄로 갑니다)` : `「${ln.name}」 — 했음을 취소했습니다` };
  });
}

// ---------------------------------------------------------------- 문서 하나로 조립한 워크플로우(task_catalog.js taskIsSingle — spec_워크플로우 ② §18-13 걸음 6의 화면 · 2026-11-20 사용자 "그리고 문서 하나는 왜 안되냐?" → 답 「조립한 것만 서버로」)
// **서버가 센 상태**로 그리고 **서버 쪽 실행기**로 돌린다: 상태 = GET /api/works/{wid}/flow(workflow_exec.js flowGet — 첫 화면의 대시보드와 같은 서버 상태: 화면이 단계를 따로 세지 않는다) ·
// 실행 = singleRunServer(묶음의 「한 번에 진행」 · 줄 하나 「이 단계만 진행」 · 「이어서 한 번에」 — 화면 실행으로 가지 않는다: 서버가 못 맡으면 그 까닭). 사람이 하는 줄(값 확정 · 변경 계획 보기 · 자리 LLM 검토 · 템플릿 관계 · 표 점검)의
// 단추는 그 일을 하는 곳을 연다(붙박이 가지의 그 단추와 같은 함수 · 같은 글). **붙박이 양식 표준화 · 양식 맞추기의 가지(dashStdLive · dashFitLive)는 그대로다** — 여기는 조립한 것만 온다(dashLive).
// 읽어 둔 서버 상태로 그린다(1초마다 서버를 읽지 않는다) — 낡으면 다시 읽고 다시 그린다: 도는 것이 있으면 3초 · 그 밖에는 10초 · 실행의 줄이 넘어갈 때와 끝날 때(dashFlowTouch — workflow_exec.js 의 거울이 부른다) · 이 보기가 돌린 뒤
function dashFlow() { // 이 문서의 읽어 둔 서버 상태 {key 문서, id, view(flowGet 의 값) | null, err, at 읽은 때, stale 다시 읽을 것, loading 읽는 약속}
  if (!DASH.flow || DASH.flow.key !== dashKey()) DASH.flow = { key: dashKey(), id: state.id, view: null, err: "", at: 0, stale: true, loading: null };
  return DASH.flow;
}
function dashFlowRead() { // 서버 상태를 다시 읽는다 → 약속(읽는 중이면 그 약속) — 읽으면 다시 그린다(이 보기가 보이는 동안만 · 같은 내용이면 그대로: dashSig)
  const F = dashFlow();
  if (F.loading) return F.loading;
  F.stale = false;
  F.loading = (async () => {
    let view = null, err = "";
    try { view = await flowGet(F.id); if (!view) err = "이 작업의 워크플로우 상태를 찾지 못했습니다"; } catch (e) { err = e.message || String(e); }
    F.loading = null;
    if (DASH.flow !== F) return; // 그 사이 다른 문서를 열었다
    Object.assign(F, { at: Date.now(), err, ...(view ? { view } : {}) }); // 못 읽었으면 지난 상태를 둔 채 알림 한 줄(다음 읽기가 바로잡는다)
    const pane = $("paneDash");
    if (pane && !pane.hidden && state.id === F.id) dashDraw();
  })();
  return F.loading;
}
function dashFlowTouch(id) { const F = DASH.flow; if (F && F.id === id) F.stale = true; } // 서버 상태가 바뀌었을 수 있다(workflow_exec.js 의 거울 — 줄이 넘어감 · 실행이 끝남 · 놓친 실행) — 다음 그리기가 다시 읽는다

// 서버 실행기가 일을 하는 줄(서버 app/workflow_exec.py FAMILY_HANDLERS["single"] 의 줄 — 관문 「프로젝트 구성 추출」(values)은 뺀다: 확정은 사람이 하고 실행은 지나가거나 멈춘다) — 그 줄에만 「이 단계만 진행」 을 둔다.
// 사람이 보는 · 고르는 줄(open · load · review · plan · tree · tableTools)은 서버 실행이 지나간다 — 그 일을 하는 곳을 여는 단추를 둔다. **서버가 그 가족의 줄을 더하거나 바꾸면 여기도 함께 본다**
const DASH_SINGLE_RUN = new Set(["read", "apply", "heads", "headsLlm", "adjust", "tables", "tablesLlm"]);
const DASH_SINGLE_ONE = "이 단계만 진행"; // 줄 하나만 서버 실행으로(시작 요청의 only — 이관의 줄 단추 「분석」 · 첫 화면 대시보드의 차례 번호와 같은 길)

function dashSingleReview(off) { // 「구분 기준 자리 확인」 줄(선택 — 사람이 단추로만: 서버는 이 줄의 상태를 세지 않는다) → {state, text, acts} — 붙박이 가지(dashFitStage1)의 그 줄과 같은 셈 · 같은 함수(divReview · divReviewList) · 같은 글
  const m = dv.marks || {}, rv = m.review || null, sum = rv ? dashReviewSum(rv) : null, noRun = m.reviewing ? "LLM 검토가 돌고 있습니다" : dv.busy || off ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : "";
  const acts = [dashBtn(m.reviewing ? "LLM 검토 중…" : rv ? "다시 검토" : "LLM 검토 실행", () => dashExec("구분 기준 LLM 검토", dashReview), { disabled: !!noRun, focus: "act:reviewRun",
    title: noRun || "구분 기준 자리를 LLM 이 검토합니다(유료 · 수십 초): 표시한 자리의 재검토와 빠진 자리 검토를 함께 돌리고 결과 목록을 문서 옆 열에 엽니다. 문서는 바뀌지 않습니다" })];
  if (rv) acts.push(dashBtn("검토 결과 보기", () => divReviewList(), { primary: !!sum.left && !m.reviewing, focus: "act:review",
    title: "문서 옆 열에 구분 기준 LLM 검토 결과 목록을 엽니다 — 줄을 누르면 그 자리로 · 문단 후보는 「자리로 추가」 해야 자리가 됩니다" }));
  return { state: m.reviewing ? "run" : sum && !sum.left && !sum.bad ? "done" : "", acts,
    text: m.reviewing ? "LLM 검토 중 — 수십 초 걸립니다" : !sum ? "LLM 검토는 아직 하지 않았습니다 — 스크립트가 찾지 못한 자리(묶음 밖의 표 · 문단)를 LLM 이 찾습니다. 하지 않아도 다음 단계로 갈 수 있습니다"
      : `LLM 검토함(${fmtWhen(rv.at)}) — ${sum.text}${sum.left ? ` · 문단 후보 ${sum.left}곳은 「검토 결과 보기」 의 목록에서 「자리로 추가」 해야 자리가 됩니다` : ""}${sum.bad ? " · 다 본 것이 아닙니다 — 「다시 검토」" : ""}`
        + (rv.rev !== state.serverRev ? " · 검토한 뒤 문서가 바뀌었습니다 — 「다시 검토」 할 수 있습니다" : "") };
}

function dashSingleActs(s, g, C) { // 줄 하나의 단추 → [요소]. C = {V 서버 상태, off 지금 누를 수 없는 까닭, reg{줄 key: 등록부의 줄}, ref 그 줄의 이름(초점)}
  const acts = [], k = s.key, now = s.st === "now" && !C.off, paid = (s.paid || []).length, wait = "지금 진행 중인 작업이 끝나면 쓸 수 있습니다";
  if (DASH_SINGLE_RUN.has(k) && !s.done) { // 서버가 도는 줄 — 그 줄 하나만(앞 줄이 남았으면 서버의 처리 함수가 하지 않고 그 까닭으로 멈춘다: 끝 글 한 줄 — 화면이 차례를 따로 따지지 않는다)
    const no = C.off || (!C.V.ready ? C.V.why || "문서 칸이 비었습니다" : "");
    acts.push(dashBtn(DASH_SINGLE_ONE, () => dashSingleRun(`${s.name} — ${DASH_SINGLE_ONE}`, g.id, { only: k, sig: C.V.sig || "" }), { primary: now && !no, disabled: !!no, focus: `act:${C.ref}:only`,
      title: no || ["이 단계만 진행합니다 — 서버에서 진행합니다(창을 닫아도 이어집니다). 앞 단계가 남았으면 진행하지 않고 그 까닭을 알립니다.",
        paid ? `유료 LLM — 문서 ${paid}개` : "", (C.reg[k] || {}).change === "doc" ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") }));
  }
  if (k === "values" || k === "load") acts.push(dashBtn("입력 칸 열기", () => showTab("Div"), { primary: k === "values" && now, focus: `act:${C.ref}:input`, title: "「작업 개요」 의 프로젝트 구성 입력 칸 · 불러오기 — 값을 고칠 때" }));
  if (k === "plan") { // 변경 계획 보기 — 사람이 목록으로 보는 줄(에이전트 행동 plan 과 같은 함수 — divPlan: 문서는 안 바뀐다). 서버 실행의 「반영」 줄은 울타리 안에서 제 계획을 세운다
    const no = C.off || (dv.busy ? wait : divRunWhy());
    acts.push(dashBtn("변경 계획 보기", () => dashExec("변경 계획 보기", () => agwExec("plan")), { primary: now && !no, disabled: !!no, focus: `act:${C.ref}:plan`,
      title: no || "프로젝트 구성에 맞추면 바뀔 자리를 셉니다 — 문서는 바뀌지 않고, 목록이 문서 옆 열에 열립니다" }));
    if (dv.plan) acts.push(dashBtn("변경 계획 목록 보기", () => divList(), { focus: `act:${C.ref}:planList`, title: "문서 옆 열에 바뀔 자리 목록을 엽니다" }));
  }
  if (k === "adjust") acts.push(dashBtn("계획 보기", () => tplPlanGo(), { focus: `act:${C.ref}:adjustPlan`,
    title: "헤딩 추출 탭 진행 줄의 「조정」 으로 — 「템플릿 조정」 · 「서식 조정」 칸을 누르면 템플릿 · 레벨마다 맞출 줄 · 뗄 줄 · 남긴 줄이 보입니다(문서는 안 바뀜)" }));
  if (k === "tree") acts.push(dashBtn("템플릿 관계 열기", () => tplRelOpen(), { focus: `act:${C.ref}:tree`,
    title: "문서 옆 열에 「템플릿 관계」 를 엽니다 — 남긴 줄 · 애매한 종속 제안 · 대표가 없는 레벨을 손으로 맞추거나 뗍니다(누른 단추에 따라 문서가 바뀜)" }));
  if (k === "tableTools") acts.push(dashBtn("테이블 탭 열기", () => showTab(typeof dsTo === "function" ? dsTo("Tables") : "Tables"), { focus: `act:${C.ref}:tableTools`,
    title: "패널 「테이블」 — 표 하나씩 수식 판정 · 검산, 같은 자리(머리행 · 머리열 · 합계행)의 칸 서식 맞추기, 빈 필드 지우기" }));
  return acts;
}

function dashSingleRun(label, from, opt = {}) { // 서버 쪽 실행기에 시작을 청하고 끝까지 따라간다(workflow_exec.js singleRunServer — 확인 창 없이 바로: 유료 LLM · 문서 바뀜은 단추의 풍선 도움말에).
  // 끝 글은 서버 상태의 「지난 실행」 한 줄로 보인다(dashSingleLive — 다시 연 뒤에도 · 다른 화면이 돌린 것도): 머리 아래 끝 글 칸에는 시작하지 못한 까닭만 남긴다(같은 글을 두 번 보이지 않는다)
  return dashExec(label, async () => {
    const r = await singleRunServer(from, opt);
    if (!r || !r.run) return r;
    if (!taskIsSingle(agwJob())) return null; // 그 사이 다른 문서를 열었다
    await dashFlowRead(); // 끝난 실행을 서버 상태에서 다시 읽은 뒤에 진행 줄을 걷는다(끝 글이 바로 보이게)
    if (dashFlow().stale) await dashFlowRead(); // 읽는 중이던 것은 끝나기 전의 상태일 수 있다 — 그 사이 낡았으면 한 번 더
    return null;
  });
}

async function dashSingleLive(M) {
  const L = { steps: {}, runs: {}, ends: {}, at: {} }, F = dashFlow(), V = F.view, cat = TASK_CATALOG[M.job] || {};
  const mirror = typeof taskRun !== "undefined" && taskRun && taskRun.single ? taskRun : null; // 도는 서버 실행의 거울(workflow_exec.js singleRunFollow)
  const moving = !!V && (flowActive(V.run) || !!mirror || V.stages.some((g) => (g.steps || []).some((s) => s.busy || s.st === "run")));
  if (!F.loading && (F.stale || Date.now() - F.at >= (moving ? 3000 : 10000))) dashFlowRead(); // 기다리지 않는다 — 읽으면 다시 그린다
  if (!V) { M.notes.push(F.err ? { text: `상태를 읽지 못했습니다: ${F.err}`, warn: true } : { text: "상태를 읽는 중…" }); return L; }
  // 그 사이 정의가 바뀌었다(다른 탭의 「워크플로우 조립」) — 목록과 단계 흐름(등록부)을 새 정의로 다시 읽는다(지문마다 한 번 · 도는 실행이 있으면 끝난 뒤: app.js taskCatalogRefresh)
  if (V.sig && cat.sig && V.sig !== cat.sig && DASH.sigTried !== V.sig && !mirror && typeof taskCatalogRefresh === "function") { DASH.sigTried = V.sig; taskCatalogRefresh(M.job); }
  const active = flowActive(V.run) || !!mirror;
  const off = DASH.busy ? `「${DASH.busy.label}」 이 끝나면 쓸 수 있습니다` : active || singleStarting || agwRunning() ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : ""; // 같은 문서에 두 실행을 겹치지 않는다
  if (F.err) M.notes.push({ text: `상태를 읽지 못했습니다: ${F.err}`, warn: true });
  if (V.why && (!V.stages.length || !V.ready)) M.notes.push({ text: V.why, warn: true }); // 문서 칸이 비었음 · 모르는 워크플로우(서버의 글)
  const E = active ? null : flowEnd(V.last);
  if (E && E.text) M.last = { ok: E.ok && !E.left, text: E.text }; // 지난 실행의 끝 — 서버가 지은 글 그대로(「끝남 — …」 초록 · 「남김 — …」 · 「멈춤 — …」 · 「끊김 — …」 주황: 첫 화면의 대시보드와 같은 줄 — 다시 연 뒤에도 · 다른 화면이 돌린 것도)
  const served = V.stages.filter((g) => g.server && g.steps);
  if (V.stages.length && served.length < V.stages.length) M.notes.push({ text: SINGLE_NOT_SERVED, warn: true }); // 조립한 것은 화면이 돌리지 않는다 — 서버가 안 맡은 묶음은 누를 수 없다
  const reg = Object.fromEntries((M.reg ? M.reg.stages : []).flatMap((g) => g.steps).map((s) => [s.key, s])), seen = {};
  for (const g of V.stages) {
    const srv = !!(g.server && g.steps);
    L.at[g.id] = (g.steps || []).map((s) => { // 줄마다(서버의 차례 = 등록부의 차례 — 같은 정의에서 지은 것)
      const n = (seen[s.key] = (seen[s.key] || 0) + 1), ref = n > 1 ? `${s.key}#${n}` : s.key; // 같은 줄을 두 번 놓은 정의 — 둘째부터 이름을 따로(펴고 접기 · 초점)
      const run = s.st === "run" || (!!mirror && mirror.stage === g.id && mirror.key === s.key), st = run ? "run" : s.done ? "done" : s.st === "blocked" || s.st === "failed" ? "hold" : s.st === "now" ? "now" : "todo";
      const x = { key: s.key, ...(n > 1 ? { ref } : {}), state: st, skipped: st === "done" && !!s.skipped, text: dashHere(s.text || ""), acts: [],
        word: st === "run" ? DASH_ST.run : st === "done" ? (s.skipped ? "건너뜀" : DASH_ST.done) : FLOW_WORD[s.st] || "" }; // 상태의 글 = 서버의 것(막힘 · 실패 · 건너뜀 — 첫 화면의 대시보드와 같은 말)
      if (s.key === "review") Object.assign(x, dashSingleReview(off), { word: undefined, skipped: false }); // 화면이 아는 줄(서버는 세지 않는다)
      else x.acts = dashSingleActs(s, g, { V, off, reg, ref });
      if (x.word === undefined) delete x.word;
      if (!(s.key in L.steps)) L.steps[s.key] = x; // key 로 찾는 쪽(사람이 하는 일 줄 · 등록부가 낡았을 때)
      return dashHandKey(s.key) ? null : x; // 사람이 하는 일 줄 = dashHands 가 「했음」 과 함께 그린다(L.steps)
    });
    const paid = (g.paid || []).length, no = !srv ? SINGLE_NOT_SERVED : off || (!g.can ? g.why || "지금은 진행할 수 없습니다" : ""), name = `${g.no || ""} ${g.name || ""}`.trim();
    L.runs[g.id] = dashBtn("한 번에 진행", () => dashSingleRun(`${name} — 한 번에 진행`, g.id, { sig: V.sig || "" }), { disabled: !!no, focus: `run:${g.id}`,
      title: no || [`이 묶음의 남은 단계를 차례로 한 번에 — ${g.does}. 사람 손이 필요한 곳에서는 멈춥니다(서버에서 진행 · 창을 닫아도 이어집니다)`,
        paid ? `유료 LLM — 문서 ${paid}개` : "", g.change ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") });
  }
  // 「이어서 한 번에 N→M단계」 — 할 일이 남은 첫 묶음 → 끝 묶음(그 사이를 모두 서버가 맡을 때 — 서버가 from → to 로 돈다: 경계마다 최신 상태로 그 묶음을 할지 정하고 안 끝난 묶음에서 멈춘다)
  const rest = served.filter((g) => g.left > 0);
  if (rest.length > 1) {
    const a = rest[0], z = rest[rest.length - 1], span = V.stages.slice(V.stages.indexOf(a), V.stages.indexOf(z) + 1);
    if (span.every((g) => g.server && g.steps)) {
      const label = `이어서 한 번에 ${(a.no || "").replace(/단계$/, "")}→${z.no}`, no = off || (!a.can ? a.why || "지금은 진행할 수 없습니다" : ""), paid = new Set(span.flatMap((g) => g.paid || [])).size;
      M.top.push(dashBtn(label, () => dashSingleRun(label, a.id, { to: z.id, sig: V.sig || "" }), { disabled: !!no, focus: "run:chain",
        title: no || [`${rest.map((g) => `${g.no} 「${g.name}」`).join(" → ")} 을 이어서 한 번에 — 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다(서버에서 진행 · 창을 닫아도 이어집니다)`,
          paid ? `유료 LLM — 문서 ${paid}개` : "", span.some((g) => g.change) ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") }));
      if (no && !off) M.top.push(el("span", "dash-top-why", no)); // 꺼진 까닭이 서버의 것이면(앞 묶음이 먼저 · 문서 칸이 빔) 글로
    }
  }
  if (!active && V.last && (V.last.stages || []).length > 1) for (const x of V.last.stages) if (x.text) L.ends[x.id] = { ok: x.status === "done" || x.status === "left", text: x.text }; // 여러 묶음을 돈 지난 실행 — 묶음마다 그 끝 글
  await dashHands(M, L); // 사람이 하는 일 줄(정의 v2 의 hand) — 「했음」 · 「했음 취소」
  return L;
}

// ---------------------------------------------------------------- 줄 목록(정의 v2)으로 조립한 이관형(task_catalog.js taskIsRelayFlow — spec_워크플로우 ② §18-13 「줄 목록으로 조립한 이관형의 문서 화면」 · spec_작업에이전트 ② §9)
// 2026-11-21 사용자(조립한 「연차보고서 배포(안) 작성」 의 이 보기에 상태 · 단추가 하나도 없는 것을 「사업계획서 양식 표준화」 의 보기와 나란히 보이며) "안에 기능이 하나도 없냐? 목적문서/원본문서 로 구분해서 워크플로우가 작성되어있고
// 각 단계별로 실행하고 하는 내용이 없어? … 각 도구마다 실행 및 결과내용을 보여주는게 있어야 하고 한번에 진행, 다 진행 이런게 있어야 하는데 사업계획서 양식 표준화를 참고해줘".
// 까닭: 이관 가지(dashRelayLive)는 화면의 표준 네 묶음(TASK_STAGES — review · frame · map · clean)으로 센다 — 줄 목록 정의의 묶음(g1 …)은 거기 없어 상태도 단추도 안 붙었다(등록부의 그림만).
// 여기는 문서 하나로 조립한 것(dashSingleLive)과 같은 길이다 — **서버가 센 상태**(dashFlow — GET …/flow: 첫 화면의 대시보드와 같은 값)로 그리고 **서버 쪽 실행기**로 돌린다(workflow_exec.js relayFlowRun — 화면 실행으로 가지 않는다):
// - 줄마다 **문서 카드**(원본 문서 · 목적 문서 — 두 문서에 하는 줄은 카드 둘 · 「원본 → 목적」 · 「워크플로우 전체」 줄은 카드 하나: 첫 화면의 대시보드 hdCards 와 같은 가름) — 상태 · 결과 글은 서버가 준 문서마다의 몫(per).
// - 줄의 「이 단계만 진행」(서버가 도는 줄 — only: 앞 단계가 남았으면 서버가 하지 않고 그 까닭으로 멈춘다) · 묶음의 「한 번에 진행」 · 머리 아래 「이어서 한 번에 N→M단계」(= 끝까지 다 진행).
// - 「준비」 = 문서 칸 둘(원본 · 목적): 빈 칸은 올리기 · **올리지 않으면 워크플로우 설정의 저장한 양식**(같은 날 사용자 "사업계획서를 사용자가 올려야 하고,, 목적문서인 연차보고서를 올려야 하고 올리지 않으면 저장된 파일을 사용해야" —
//   기본값 · 고정으로 건 칸: 「저장한 양식으로」 단추 · 실행 단추를 누르면 먼저 그 양식으로 채운 뒤 진행한다 — POST /api/workflow-start/target · …/source).
// - 사람이 보는 것(입력 칸 · 연결 목록 · 지울 안내 목록 · 작성 지침)은 그 일을 하는 곳을 연다(이관 가지의 그 단추와 같은 함수). 등록부의 설명은 본문에 넣지 않는다(이름 옆 메모에만).
// 「지금」 은 할 일이 남은 첫 묶음에만(서버의 st 는 묶음마다 첫 남은 줄 — 이관형은 묶음이 차례라 뒤 묶음의 것은 「남음」 으로 보인다). **서버가 이관 가족의 줄을 더하거나 바꾸면 DASH_FLOW_VIEW 와 아래 단추도 함께 본다.**
const DASH_FLOW_ROLE = { source: "원본 문서", target: "목적 문서", pair: "원본 → 목적", flow: "워크플로우 전체" }; // 등록부를 못 읽었을 때의 문서 꼬리표(읽었으면 등록부의 말 — 첫 화면의 대시보드 HD_ON 과 같다)
const DASH_FLOW_LLM = new Set(["headsLlm", "reheadsLlm"]); // 문서마다 「건너뛰기」 를 두는 줄(LLM 검증·보완 — 유료 · 몇 분: PUT …/flow/skip — 모든 화면 · 실행이 같이 본다)

function dashFlowRoleEl(role, r, s) { // 카드 머리의 문서 꼬리표(첫 화면의 대시보드 hdRoleEl 과 같은 꼴 · 같은 클래스)
  const doc = role === "source" || role === "target", head = doc ? (r ? r.title : DASH_FLOW_ROLE[role]) : (s.onText || "").split(" — ")[0] || DASH_FLOW_ROLE[role] || "";
  if (!head) return null;
  const t = el("span", "hd-role", head);
  t.dataset.role = role;
  t.title = doc ? (r ? `${r.title} — ${r.name}` : head) : s.onText || head;
  return t;
}

// 빈 문서 칸을 그 워크플로우 설정의 저장한 양식(기본값 · 고정)으로 채운다 → null(채울 칸이 없음 · 건 양식이 없음) | {ok, text}. 목적 칸 = POST /api/workflow-start/target(지금 묶음 그대로 — 새 라운드를 만들지 않는다) ·
// 원본 칸 = POST /api/workflow-start/source(첫 화면의 시작이 쓰는 것). 채운 문서는 올린 문서처럼 첫 분석(스크립트)을 걸어 둔다. 양식 설정은 home_files.js 가 읽어 둔 것(hfSlot — 누르기 직전에 다시 읽는다)
async function dashFlowFill() {
  const job = agwJob(), id = state.id, [src, tgt] = relayFlowPair();
  if ((src && tgt) || typeof hfFormsLoad !== "function" || typeof hfSlot !== "function") return null;
  const role = !tgt ? "target" : "source", main = !tgt ? src : tgt;
  await hfFormsLoad(true);
  if (state.id !== id) return { ok: false, text: "다른 문서를 열어 채우지 않았습니다" };
  const s = hfSlot(job, role);
  if (!s || !s.form) return null; // 건 양식이 없다 — 사람이 올린다(서버의 글 「… 칸이 비었습니다」 가 그대로 보인다)
  const word = role === "target" ? "목적 문서" : "원본 문서";
  if (!main) return { ok: false, text: "이 문서의 문서 종류(원본 문서 · 목적 문서)가 정해지지 않았습니다 — 「작업 개요」 의 문서 칸에서 먼저 고르세요" };
  if (!taskProject()) return { ok: false, text: "프로젝트 이름을 먼저 적으세요 — 채운 문서를 그 프로젝트에 넣습니다(「작업 개요」)" };
  const P = DASH.fillReq && DASH.fillReq.main === main.id && DASH.fillReq.form === s.form.id ? DASH.fillReq : null; // 답을 못 받은 요청 — 같은 열쇠로(서버가 같은 작업을 돌려준다)
  const key = P ? P.key : `df${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  DASH.fillReq = { main: main.id, form: s.form.id, key };
  let r = null;
  try { r = await api(`/api/workflow-start/${role}`, { method: "POST", headers: H_JSON, body: JSON.stringify({ job, main: main.id, request: key, [role]: { form: s.form.id, sha256: s.form.sha256, rev: s.rev } }) }); }
  catch (e) {
    if (e.status) DASH.fillReq = null;
    if (e.status === 409) hfFormsLoad(true);
    const old = e.status === 404 && e.message === "Not Found"; // 끝점이 없는 옛 서버
    return { ok: false, text: old ? `${word} 칸을 저장한 양식으로 채우지 못했습니다 — 서버가 옛 판입니다(서버를 다시 켠 뒤에 됩니다 · 그때까지는 「올리기…」 로 넣으세요)` : `${word} 칸을 ${hfFormLabel(s.form)}으로 채우지 못했습니다: ${(e.body && e.body.message) || e.message}` };
  }
  DASH.fillReq = null;
  api(`/api/docs/${r.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 올린 문서와 같게
  if (state.id !== id) return { ok: true, text: `${word} 칸을 ${hfFormLabel(s.form)}으로 채웠습니다` };
  await loadWorks();
  if (state.id === id) { try { await taskFlowLoad(); } catch (e) { console.warn(e); } }
  dashFlowTouch(id);
  return { ok: true, text: `${word} 칸을 ${hfFormLabel(s.form)}으로 채웠습니다(양식: ${HF_FORM_MODE[s.mode]})` };
}

function dashFlowUp(kind, name, focus, off) { // 「○○ 올리기…」 — 「작업 개요」 의 문서 칸 폴더 단추와 같은 함수(app.js taskSlotUpload: 새 작업으로 올려 그 칸에 넣고 첫 분석을 걸어 둔다)
  const no = off || (taskProject() ? "" : "프로젝트 이름을 먼저 적으세요 — 올린 문서를 그 프로젝트에 넣습니다(「작업 개요」)");
  return dashBtn(`${name} 올리기…`, () => {
    const inp = el("input");
    inp.type = "file";
    inp.accept = ".hwp,.hwpx";
    inp.onchange = () => dashExec(`${name} 올리기`, async () => { const id = state.id; await taskSlotUpload(kind, inp.files[0]); if (state.id === id) dashFlowTouch(id); await dashFlowRead(); return null; });
    inp.click();
  }, { disabled: !!no, focus, title: no || `${name} 파일(hwp · hwpx)을 올려 이 워크플로우의 문서 칸에 넣습니다 — hwp 는 hwpx 로 바꿔 받고, 헤딩 · 표 분석(스크립트)을 바로 걸어 둡니다. 지금 보는 문서는 그대로입니다` });
}

function dashFlowFiles(C) { // 「준비」 카드 — 문서 칸 둘(원본 · 목적)의 문서 · 빈 칸의 올리기 · 저장한 양식 → {lines, acts, fill(빈 칸을 채울 양식이 있나 — 실행 단추가 먼저 채운다)}
  const job = agwJob(), kinds = taskSlots() || [], out = { lines: [], acts: [], fill: "" };
  [["source", C.src, kinds[0]], ["target", C.tgt, kinds[1]]].forEach(([role, w, kind]) => {
    const r = C.roles.find((x) => x.role === role) || { title: DASH_FLOW_ROLE[role], name: taskName("file", kind) || "" }, s = typeof hfSlot === "function" ? hfSlot(job, role) : null, form = s && s.form ? s : null;
    const here = w && w.id === state.id ? " — 지금 문서" : "";
    out.lines.push([`${r.title} — ${r.name}`, w ? `${w.name}${here}` : form ? `없음 — 올리지 않으면 저장한 ${hfFormLabel(form.form)}을 씁니다(양식: ${HF_FORM_MODE[form.mode]})` : "없음 — 올려 주세요"]);
    if (w) return;
    if (!(form && form.mode === "fixed")) out.acts.push(dashFlowUp(kind, r.name, `act:files:up:${role}`, C.off)); // 고정이면 올린 파일을 그 칸에 넣을 수 없다(서버 409)
    if (form) {
      out.fill = out.fill || `${r.title} 칸이 비어 저장한 ${hfFormLabel(form.form)}으로 먼저 채웁니다`;
      out.acts.push(dashBtn("저장한 양식으로", () => dashExec(`${r.title} — 저장한 양식으로`, async () => (await dashFlowFill()) || { ok: false, text: "채울 칸이 없습니다" }), { disabled: !!C.off, primary: !C.off, focus: `act:files:form:${role}`,
        title: C.off || `${r.title} 칸을 저장한 ${hfFormLabel(form.form)}으로 채웁니다 — 그 양식으로 새 작업을 만들어 이 묶음(프로젝트 · 워크플로우 · 라운드)에 넣습니다. 다른 파일로 하려면 「${r.name} 올리기…」` }));
    }
  });
  out.acts.push(dashBtn("「작업 개요」 의 칸 열기", () => showTab("Div"), { focus: "act:files:div", title: "「작업 개요」 의 문서 칸 — 이 프로젝트의 다른 문서로 바꾸거나 고릅니다" }));
  return out;
}

// 사람이 보는 것 — 그 줄의 결과 · 입력을 여는 단추(이관 가지 app.js taskSteps 의 그 단추와 같은 함수). 목록은 목적 문서의 화면에서 연다(그 문서의 것) — 원본 문서를 보고 있으면 카드의 「목적 문서 열기」 로 간 뒤에
const DASH_FLOW_VIEW = {
  config: () => [dashBtn("입력 칸 열기", () => showTab("Div"), { focus: "act:config:input", title: "「작업 개요」 의 프로젝트 구성 입력 칸 · 불러오기 — 값을 보거나 고칠 때" })],
  configLoad: () => [dashBtn("구성 불러오기", () => showTab("Div"), { focus: "act:configLoad:open", title: "「작업 개요」 의 「프로젝트 구성 불러오기」 — 파일에서(이 프로젝트의 문서에서 추출 · 파일 올려 추출) 또는 저장된 곳에서. 입력 칸만 바뀌고 문서 · 확정은 그대로입니다(선택 — 안 해도 됩니다)" })],
  heads: (C, role) => (role === "target" && C.onTarget && ((((taskFlow.guides || {}).saved || {}).counts || {}).items || (((taskFlow.guides || {}).saved || {}).counts || {}).marks) && typeof formGuidesList === "function"
    ? [dashBtn("작성 지침", () => formGuidesList(C.tgt), { focus: "act:heads:guides", title: "저장한 작성 지침(작성 요령 표 · <참고 N> 자료 · ※ 안내 · 각주 번호의 항목)을 헤딩별 · 표별로 문서 옆 열에 보입니다" })] : []),
  link: (C) => (C.onTarget && taskFlow.links && !taskFlow.links.error && taskFlow.links.counts ? [dashBtn("연결 목록", () => linksList(), { focus: "act:link:list", title: "문서 옆 열에 연결 목록을 엽니다 — 확인 필요한 자리의 원본을 후보에서 고를 수 있습니다(안 골라도 됩니다)" })] : []),
  guide: (C) => (C.onTarget && taskFlow.cleanup && !taskFlow.cleanup.error ? [dashBtn("목록 보기", () => taskCleanupList(), { focus: "act:guide:list", title: "지우는 패턴 목록과 지울 자리를 문서 옆 열에 보입니다 — 줄을 누르면 문서의 그 자리로" })] : []),
};

// 「넣을 구성 선택」 줄(조립에 놓는 도구 — spec_병합 ② §4-1: 2026-11-21 사용자 "이관, 병합을 할떄는 어떤 구성을 추출해서 넣을건지에 대한 것이 매칭하기 전에 결정되어야 하는데.. 이걸 선택하는 도구가 있었으면 좋겠어" ·
// "연차보고서는 몇 차년도를 내보낼 지가 핵심이야") — 사람이 고르는 줄(서버 실행은 지나간다): 카드에 **대상 차년도**(몇 차년도 문서를 내나 — 하나 고름: 목적 문서의 당해 차년도로 적힌다)와
// **넣을 구성**(기관 · 단계 · 차년도 — 눌린 것 = 넣음 · 모두 눌려 있으면 전부)의 고르기 단추. 값 = GET …/flow/take(읽어 둔 것 — 낡으면 다시 읽는다) · 누르면 바로 저장(PUT — 문서는 안 바뀐다).
function dashTake() { // 이 문서의 읽어 둔 값 {key, id, view | null, err, at, loading}
  if (!DASH.take || DASH.take.key !== dashKey()) DASH.take = { key: dashKey(), id: state.id, view: null, err: "", at: 0, loading: null };
  return DASH.take;
}
function dashTakeRead(force = false) {
  const T = dashTake();
  if (T.loading || (!force && T.view && Date.now() - T.at < 10000)) return T.loading;
  T.loading = (async () => {
    let view = null, err = "";
    try { view = await api(`/api/works/${T.id}/flow/take`); } catch (e) { err = e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켠 뒤에 고를 수 있습니다" : e.message || String(e); }
    T.loading = null;
    if (DASH.take !== T) return;
    Object.assign(T, { at: Date.now(), err, ...(view ? { view } : {}) });
    const pane = $("paneDash");
    if (pane && !pane.hidden && state.id === T.id) dashDraw();
  })();
  return T.loading;
}
function dashTakePut(label, body) { // 고른 것을 적는다 → 읽어 둔 값 · 서버 상태 · 연결 목록 · (이 문서의) 구성 입력을 다시 읽는다
  return dashExec(label, async () => {
    const T = dashTake(), id = state.id;
    let view = null;
    try { view = await api(`/api/works/${id}/flow/take`, { method: "PUT", headers: H_JSON, body: JSON.stringify(body) }); }
    catch (e) { return { ok: false, text: `적지 못했습니다 — ${e.message}` }; }
    if (state.id !== id) return null;
    Object.assign(T, { view, at: Date.now(), err: "" });
    dashFlowTouch(id);
    if (typeof singleAfter === "function") await singleAfter(id); // 대상 차년도 = 이 묶음 목적 문서의 구성 입력 값 — 「작업 개요」 의 입력 칸 · 분석 상태를 다시 읽는다
    if (state.id === id && typeof taskFlowLoad === "function") { try { await taskFlowLoad(); } catch (e) { console.warn(e); } } // 연결 목록(범위 밖 표시)
    await dashFlowRead();
    return null; // 결과는 그 줄의 상태 글로 보인다(같은 글을 두 번 적지 않는다)
  });
}
function dashFlowTake(card, off) { // 그 카드의 고르기 단추
  const T = dashTake(), V = T.view;
  if (!T.loading && (!V || Date.now() - T.at >= 10000)) dashTakeRead();
  if (!V) { if (T.err) card.lines = [["", T.err]]; return; }
  if (!V.ready) return; // 고를 값이 없다 — 까닭은 서버의 상태 글에
  const C = V.choices || {}, take = V.take || {}, acts = [], chip = (text, on, run, title, focus) => {
    const b = dashBtn(text, run, { disabled: !!off, title: off || title, focus });
    b.classList.add("dash-chip");
    b.setAttribute("aria-pressed", String(!!on));
    return b;
  }, row = (label, chips, cls = "") => {
    const r = el("div", "dash-take-row" + (cls ? ` ${cls}` : "")), box = el("div", "dash-take-chips");
    box.append(...chips);
    r.append(el("span", "dash-chip-name", label), box);
    return r;
  };
  acts.push(row("대상 차년도", (C.year || []).map((y) => chip(y.name, V.year === y.n, () => dashTakePut(`대상 차년도 — ${y.name}`, { year: y.n }),
    `${y.name} 문서를 냅니다 — 목적 문서의 「당해 차년도」 를 ${y.n}차년도로 적습니다(문서는 바뀌지 않습니다 · 구조를 이미 반영했으면 「프로젝트 구성 반영」 을 다시 해야 합니다)`, `act:take:target:${y.n}`)), "dash-take-target")); // 초점 이름 = target(「넣을 차년도」 칩 act:take:year:N 과 겹치지 않게)
  const dims = [["org", "넣을 기관", (C.org || []).map((o) => [o.name, o.role === "수요기업" ? `${o.name}(수요기업)` : o.name])], // 수요기업으로 고른 기관은 이름 뒤에 적는다(spec_구분_기준 ② §24)
    ["stage", "넣을 단계", (C.stage || []).map((s) => [s.n, s.name])], ["year", "넣을 차년도", (C.year || []).map((y) => [y.n, y.name])]];
  for (const [d, title, all] of dims) {
    if (all.length < 2) continue; // 값이 하나뿐인 기준은 고를 것이 없다
    const cur = new Set(take[d] || all.map((x) => x[0]));
    acts.push(row(title, all.map(([v, text]) => chip(text, cur.has(v), () => {
      const next = new Set(cur);
      if (next.has(v)) next.delete(v); else next.add(v);
      if (!next.size) { toast(`${title.replace("넣을 ", "")}를 하나는 남겨야 합니다 — 모두 넣으려면 모두 눌러 두세요`, true); return; }
      return dashTakePut(`넣을 구성 — ${title.replace("넣을 ", "")}`, { take: { ...take, [d]: all.map((x) => x[0]).filter((x) => next.has(x)) } });
    }, cur.has(v) ? `「${text}」 의 내용을 넣습니다 — 누르면 뺍니다(그 자리는 자리 연결 · 넣기에서 빠집니다)` : `「${text}」 의 내용을 넣지 않습니다 — 누르면 다시 넣습니다`, `act:take:${d}:${v}`)), "dash-take-multi"));
  }
  if (V.active) {
    const foot = el("div", "dash-take-foot");
    foot.append(dashBtn("전부 넣기", () => dashTakePut("넣을 구성 — 전부", { take: null }), { disabled: !!off, title: off || "고른 것을 풀어 맞는 자리는 모두 넣습니다(대상 차년도는 그대로)", focus: "act:take:all" }));
    acts.push(foot);
  }
  if (off) acts.push(el("p", "dash-text dash-why dash-take-why", off));
  card.acts = acts;
}

function dashFlowRun(label, from, opt = {}) { // 서버 쪽 실행기에 시작을 청한다(workflow_exec.js relayFlowRun — 확인 창 없이 바로: 유료 LLM · 문서 바뀜은 단추의 풍선 도움말에).
  // 빈 문서 칸에 건 저장한 양식이 있으면 먼저 그 양식으로 채운다(「올리지 않으면 저장된 파일」). 끝 글은 서버 상태의 「지난 실행」 줄로 보인다 — 머리 아래 끝 글 칸에는 시작하지 못한 까닭만 남긴다.
  // **시작까지만 기다린다**(detach — 문서마다 따로 도는 실행: spec_워크플로우 ② §18-22): 그 실행을 따라가는 동안 이 보기를 「하는 중」 으로 잡아 두지 않는다 — 다른 문서의 단추를 누를 수 있게. 끄는 것은 서버 상태(도는 실행이 잡은 문서)가 한다.
  // opt.lane = 이 실행이 잡을 문서의 귀띔(한 문서만 · 문서 하나의 줄뿐인 묶음 · 문서 하나의 줄) — 도는 것이 다른 문서만 잡은 서버 실행이면 같이 시작한다
  const want = opt.role || opt.lane || "";
  return dashExec(label, async () => {
    const fill = await dashFlowFill();
    if (fill && !fill.ok) return fill;
    if (fill) toast(fill.text);
    const r = await relayFlowRun(from, { ...opt, detach: true });
    if (!r || !r.started) return r || null; // 시작하지 못한 까닭 · 「남은 단계가 없습니다」
    const after = async () => { // 끝난 실행을 서버 상태에서 다시 읽는다(끝 글이 바로 보이게)
      if (!taskIsRelayFlow(agwJob())) return; // 그 사이 다른 문서를 열었다
      await dashFlowRead();
      if (dashFlow().stale) await dashFlowRead();
    };
    if (r.done) r.done.then(after, (e) => console.warn(e));
    dashFlowTouch(state.id);
    await dashFlowRead(); // 방금 시작한 실행이 진행 줄에 서게
    return null;
  }, { over: dashBeside(want) });
}

function dashFlowSkip(doc, on, who) { // LLM 검증·보완의 「건너뛰기」 · 「건너뛰기 취소」(그 문서만 — 워크플로우 옵션: 모든 화면 · 실행이 같이 본다)
  return dashExec(`${who} — ${on ? "건너뛰기" : "건너뛰기 취소"}`, async () => {
    const got = await flowSkip(state.id, doc, on);
    dashFlowTouch(state.id);
    await dashFlowRead();
    return got ? { ok: true, text: on ? `${who}의 LLM 검증·보완을 건너뜁니다 — 스크립트 분석만으로 진행합니다` : `${who}의 LLM 검증·보완을 다시 할 일로 둡니다` } : { ok: false, text: "건너뛰기를 적지 못했습니다 — 지금 도는 실행이 끝난 뒤 다시 누르세요" };
  });
}

// 묶음 머리 아래의 「한 문서만」 줄(spec_워크플로우 ② §18-21 — 2026-11-21 사용자 「목적문서 따로 원본 문서 작업 따로 할 수 있는 것들은 단계 에서 한 번에 진행할때 각각 따로 진행할 수 있도록 … 하나의 문서만 작업」):
// 서버가 센 그 묶음의 solo(문서마다 — 그 문서만 따로 돌 수 있는 몫 · 남은 수 · 누를 수 있나 · 까닭)마다 단추 「원본 문서만」 · 「목적 문서만」. 묶음 전체와 같은 묶음(문서 하나의 줄뿐)은 solo 가 없어 줄도 없다.
// 첫 화면의 대시보드(home_dash.js)와 같은 함수 — 보기마다 다른 것(끄는 까닭 · 실행 길 · 초점 이름)만 opt 로. → 요소 | null
// busyOf(역할) = 그 문서의 단추를 끄는 까닭(보기마다 — 문서마다 따로 도는 실행은 다른 문서의 단추를 끄지 않는다: ② §18-22) · busy = 두 단추를 다 끄는 까닭(busyOf 가 없을 때)
function dashSoloEl(g, name, { busy = "", busyOf = null, fill = "", run, focusAttr = "dashFocus", sending = "" } = {}) {
  const solo = g.solo || [];
  if (!solo.length) return null;
  const box = el("p", "dash-solo");
  box.append(el("span", "dash-solo-name", "한 문서만"));
  for (const x of solo) {
    const title = x.title || DASH_FLOW_ROLE[x.role] || x.role, label = `${title}만`, why = (busyOf ? busyOf(x.role) : busy) || (x.can ? "" : x.why || "지금은 진행할 수 없습니다");
    const b = hBtn(sending === x.role ? "시작하는 중…" : label, () => run(x.role, `${name} — ${label}`), { cls: "btn sm", disabled: !!why,
      title: why || [fill, `이 묶음에서 ${title}(${x.name})의 남은 단계만 차례로 진행합니다 — 다른 문서의 단계 · 워크플로우 전체 줄 · 원본 → 목적 줄은 하지 않습니다(서버에서 진행 · 창을 닫아도 이어집니다).`,
        `${title}의 단계 ${x.total}개 가운데 ${x.left}개 남음`, (x.paid || []).length ? `유료 LLM — 문서 ${x.paid.length}개` : "", x.change ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") });
    b.dataset[focusAttr] = `solo:${g.id}:${x.role}`;
    b.dataset.left = String(x.left);
    box.append(b);
  }
  return box;
}

async function dashFlowLive(M) {
  const L = { steps: {}, runs: {}, ends: {}, at: {}, subs: {} }, F = dashFlow(), V = F.view, cat = TASK_CATALOG[M.job] || {};
  const mirror = typeof taskRun !== "undefined" && taskRun && taskRun.flow ? taskRun : null; // 도는 서버 실행의 거울(workflow_exec.js relayFlowFollow)
  const moving = !!V && (flowActive(V.run) || !!mirror || V.stages.some((g) => (g.steps || []).some((s) => s.busy || s.st === "run")));
  if (!F.loading && (F.stale || Date.now() - F.at >= (moving ? 3000 : 10000))) dashFlowRead(); // 기다리지 않는다 — 읽으면 다시 그린다
  if (!V) { M.notes.push(F.err ? { text: `상태를 읽지 못했습니다: ${F.err}`, warn: true } : { text: "상태를 읽는 중…" }); return L; }
  if (V.sig && cat.sig && V.sig !== cat.sig && DASH.sigTried !== V.sig && !mirror && typeof taskCatalogRefresh === "function") { DASH.sigTried = V.sig; taskCatalogRefresh(M.job); } // 그 사이 정의가 바뀌었다 — 새 정의로 다시 읽는다(지문마다 한 번)
  if (typeof hfFormsLoad === "function") hfFormsLoad(); // 문서 칸의 저장한 양식 설정(10초 안의 것은 다시 읽지 않는다 — 기다리지 않는다)
  const [src, tgt] = relayFlowPair(), roles = (M.reg && M.reg.roles) || [];
  // 문서마다 따로 도는 실행(spec_워크플로우 ② §18-22 — 2026-11-21 사용자 「원본문서랑, 목적문서를 따로따로 실행해서 처리할 수 있잖아? 매칭은 1개 실행이 같이 해야하고」):
  // 도는 실행(서버의 runs — 문서 하나만 잡은 실행은 둘까지)이 **잡은 문서의 단추만** 끈다. offFor(잡을 문서) = 그 단추를 끄는 까닭 — "source" | "target" = 그 문서 하나의 일 · "" = 두 문서를 함께 쓰는 일(워크플로우 전체 줄 · 원본 → 목적 줄 · 두 문서의 묶음: 도는 실행이 하나라도 있으면 끈다).
  // 서버 상태를 읽기 전의 틈은 이 화면이 아는 것(거울 · 곁에서 지켜보는 실행 · 시작 요청 중)으로 메운다
  const runs = (V.runs || (V.run ? [V.run] : [])).filter(flowActive), held = V.held || {}, WAIT = "지금 진행 중인 작업이 끝나면 쓸 수 있습니다";
  const active = runs.length > 0 || !!mirror, R0 = agwRunning(), foreign = !!R0 && R0.kind !== "flow"; // foreign = 서버 실행의 거울이 아닌 다른 진행(헤딩 추출 · 분석의 LLM 검증·보완 …) — 그동안은 모두 끈다
  const takes = (lane) => (lane ? held[lane] != null || runs.some((r) => !r.lane || r.lane === lane) || (!!mirror && (!mirror.lane || mirror.lane === lane)) || (!!tgt && flowSideOf(tgt.id, lane)) : active || (!!tgt && (flowSideOf(tgt.id, "source") || flowSideOf(tgt.id, "target"))));
  const offFor = (lane = "") => (DASH.busy ? `「${DASH.busy.label}」 이 끝나면 쓸 수 있습니다` : relayFlowStarting || foreign || takes(lane) ? WAIT : "");
  const off = offFor(""); // 두 문서를 함께 쓰는 일의 까닭
  if (F.err) M.notes.push({ text: `상태를 읽지 못했습니다: ${F.err}`, warn: true });
  // 지난 실행의 끝 — 서버가 지은 글(「끝남 — …」 · 「남김 — …」 · 「멈춤 — …」 · 「끊김 — …」: 다시 연 뒤에도 · 다른 화면이 돌린 것도 — 「아래 「…」」 같은 자리 말만 「작업 개요」 의 것으로). 같이 돌던 다른 문서의 실행도(끝난 차례 — 그 실행이 아직 도는 동안에도 끝난 쪽의 글은 보인다)
  M.lasts = (V.lasts || (V.last && !active ? [V.last] : [])).map((x) => flowEnd(x)).filter((E) => E && E.text).map((E) => ({ ok: E.ok && !E.left, text: dashHere(E.text) }));
  // 도는 실행마다 진행 줄 하나(멈춤은 그 실행에만 — 번호로)
  const stageOf = (id) => { const g = V.stages.find((x) => x.id === id); return g ? `${g.no || ""} ${g.name || ""}`.trim() : ""; };
  const roleOf = (role) => { const q = roles.find((x) => x.role === role); return (q && q.title) || DASH_FLOW_ROLE[role] || ""; };
  const lineOf = (key) => { for (const g of V.stages) for (const s of g.steps || []) if (s.key === key) return s.name; return ""; };
  M.lives = runs.map((r) => {
    const Rg = r.range || {}, now = r.now || {}, st = stageOf(now.stage || Rg.from) || "워크플로우", who = Rg.role ? roleOf(Rg.role) : "";
    const what = Rg.only ? `${lineOf(Rg.only) || "이 단계"}${who ? `(${who})` : ""} — 이 단계만 진행` : who ? `${who}만` : Rg.to && Rg.to !== Rg.from ? "이어서 한 번에" : "한 번에 진행";
    const stopping = !!r.stopping || (!!mirror && mirror.n === r.n && !!mirror.stop);
    return { n: r.n, lane: r.lane || "", label: Rg.only ? `${st} · ${what}` : `${st} — ${what}`, note: [flowBy(r), now.note || "진행 중"].filter(Boolean).join(" · "), t0: r.started ? r.started * 1000 : 0, stopping,
      stop: () => { if (mirror && mirror.n === r.n) mirror.stop = true; else flowStop(state.id, r.n); dashFlowTouch(state.id); } };
  });
  const served = V.stages.filter((g) => g.server && g.steps), cur = served.find((g) => g.left > 0) || null; // cur = 할 일이 남은 첫 묶음(「지금」 은 여기에만)
  if (V.stages.length && served.length < V.stages.length) M.notes.push({ text: SINGLE_NOT_SERVED, warn: true }); // 조립한 것은 화면이 돌리지 않는다 — 서버가 안 맡은 묶음은 누를 수 없다
  const reg = Object.fromEntries((M.reg ? M.reg.stages : []).flatMap((g) => g.steps).map((s) => [s.key, s])), seen = {};
  const C = { V, off, src, tgt, roles, onTarget: !!tgt && tgt.id === state.id }, files = dashFlowFiles(C), skips = new Set(V.llmSkip || []);
  const lack = !V.ready ? (files.fill ? "" : V.why || "문서 칸이 비었습니다") : ""; // 실행 단추를 끄는 까닭 — 빈 칸을 저장한 양식으로 채울 수 있으면 끄지 않는다(누르면 먼저 채운다)
  if (!V.ready && V.why) M.notes.push({ text: files.fill ? `${V.why.split(" — ")[0]} — 올리지 않으면 저장한 양식을 씁니다(「준비」)` : V.why, warn: !files.fill });
  for (const g of V.stages) {
    const srv = !!(g.server && g.steps), mine = g === cur;
    L.at[g.id] = (g.steps || []).map((s) => {
      const n = (seen[s.key] = (seen[s.key] || 0) + 1), tag = n > 1 ? `#${n}` : "", R = reg[s.key] || s; // 같은 줄을 두 번 놓은 정의 — 둘째부터 이름을 따로(펴고 접기 · 초점)
      const run = s.st === "run" || (!!mirror && mirror.stage === g.id && mirror.key === s.key);
      const hold = (x) => (x === "blocked" || x === "failed") && mine; // 막힘 · 실패도 할 일이 남은 첫 묶음에서만 — 뒤 묶음의 「막힘」 은 앞 묶음이 끝나면 풀리는 것이라 「남음」 으로 보인다
      const st = run ? "run" : s.done ? "done" : hold(s.st) ? "hold" : s.st === "now" && mine ? "now" : "todo";
      const word = (x, raw, skipped) => (x === "run" ? DASH_ST.run : x === "done" ? (skipped ? "건너뜀" : DASH_ST.done) : x === "hold" ? FLOW_WORD[raw] || "막힘" : DASH_ST[x] || "");
      const line = { key: s.key, ...(tag ? { ref: `${s.key}${tag}` } : {}), state: st, skipped: st === "done" && !!s.skipped, word: word(st, s.st, s.skipped), text: dashHere(s.text || ""), acts: [] };
      if (!(s.key in L.steps)) L.steps[s.key] = line; // key 로 찾는 쪽(사람이 하는 일 줄 — dashHands 가 「했음」 과 함께 그린다)
      if (dashHandKey(s.key)) return null;
      const parts = s.on === "both" ? ["source", "target"] : [s.on || ""], paid = (s.paid || []).length;
      const cards = parts.map((role) => {
        const doc = role === "source" || role === "target", p = doc ? (s.per || []).find((q) => q.role === role) || null : null, w = role === "source" ? src : role === "target" ? tgt : null;
        const cst = !p ? st : p.st === "done" ? "done" : p.st === "busy" ? "run" : hold(p.st) ? "hold" : st === "run" || st === "now" ? "now" : "todo", skipped = cst === "done" && !!(p ? p.skipped : s.skipped);
        return { ref: `${s.key}@${role}${tag}`, role, state: cst, skipped, word: word(cst, p ? p.st : s.st, skipped), text: dashHere((p && p.text) || s.text || (cst !== "done" && s.wait) || ""), lines: [], acts: [],   // 기다리는 줄(구성 값이 아직 없음 — 서버의 wait)은 그 까닭을 글로
          lead: dashFlowRoleEl(role, roles.find((q) => q.role === role) || null, R), same: false, doc: w, per: p };
      });
      cards.slice(1).forEach((c) => { c.same = true; });
      if (s.key === "files") { cards[0].lines = files.lines; cards[0].acts = files.acts; if (!V.ready) cards[0].text = ""; } // 준비 — 문서 칸 둘(빈 칸의 글은 줄마다 — 서버의 한 줄을 겹쳐 적지 않는다)
      else if (s.key === "take") dashFlowTake(cards[0], off || (!V.ready ? V.why || "문서 칸이 비었습니다" : "")); // 넣을 구성 선택 — 대상 차년도 · 넣을 기관 · 단계 · 차년도의 고르기
      else {
        // 「이 단계만 진행」 — 두 문서에 하는 줄은 **문서 카드마다 그 문서만**(안 끝난 카드마다 · 시작 요청의 only + role — spec_워크플로우 ② §18-21: 2026-11-21 사용자 「1번 오케이. 진행해줘.」 — 전에는 안 끝난 첫 카드의 단추 하나가 두 문서 모두를 돌았다).
        // 카드가 하나인 줄(문서 하나의 줄 · 워크플로우 전체 줄 · 원본 → 목적 줄)은 전처럼 그 줄 하나(only). 유료 수 · 강조(「지금」)도 두 문서의 줄은 그 문서의 것으로(카드의 상태 = 서버가 센 문서마다의 몫 per)
        const each = parts.length > 1, open = srv && s.kind === "auto" && !s.done ? cards.filter((c) => c.state !== "done") : [];
        for (const c of each ? open : open.slice(0, 1)) {
          // 끄는 까닭 — 그 카드의 문서를 잡은 실행이 돌 때만(문서 하나의 줄 · 두 문서에 하는 줄의 문서 카드: 다른 문서의 실행은 같이 돈다 — ② §18-22) · 두 문서를 함께 쓰는 줄은 도는 실행이 하나라도 있으면 ·
          // 구성 값을 기다리는 줄(서버의 wait — 「프로젝트 구성 추출」 이 먼저)은 그 값이 확정될 때까지
          const laneOf = c.role === "source" || c.role === "target" ? c.role : "";
          const no = offFor(laneOf) || lack || s.wait || "", rr = each ? roles.find((q) => q.role === c.role) || null : null, who = each ? (rr && rr.title) || DASH_FLOW_ROLE[c.role] : "";
          const pays = each ? (s.paid || []).filter((d) => c.doc && d === c.doc.id).length : paid;
          c.acts.push(dashBtn(DASH_SINGLE_ONE, () => dashFlowRun(`${s.name}${each ? `(${who})` : ""} — ${DASH_SINGLE_ONE}`, g.id, { only: s.key, ...(each ? { role: c.role } : laneOf ? { lane: laneOf } : {}), sig: V.sig || "" }),
            { primary: (each ? c.state : st) === "now" && !no, disabled: !!no, focus: `act:${c.ref}:only`,
              title: no || [files.fill && !V.ready ? `${files.fill}.` : "",
                each ? `이 단계를 ${who}${rr && rr.name ? `(${rr.name})` : ""}에만 진행합니다 — 다른 문서의 몫은 그 문서의 카드에서 따로 합니다. 서버에서 진행합니다(창을 닫아도 이어집니다). 앞 단계가 남았으면 진행하지 않고 그 까닭을 알립니다.`
                  : "이 단계만 진행합니다 — 서버에서 진행합니다(창을 닫아도 이어집니다). 앞 단계가 남았으면 진행하지 않고 그 까닭을 알립니다.",
                pays ? `유료 LLM — 문서 ${pays}개` : "", R.change === "doc" ? `${each ? `${who}가` : "문서가"} 바뀝니다` : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") }));
        }
        for (const c of cards) {
          if (DASH_FLOW_LLM.has(s.key) && c.per && c.per.doc && c.doc) { // 그 문서의 LLM 검증·보완 — 건너뛰기 · 건너뛰기 취소(사람이 건너뛴 문서에만 「취소」 — LLM 을 못 써서 건너뛴 것은 단추 없음)
            const who = c.doc.name || DASH_FLOW_ROLE[c.role], skipped = skips.has(c.per.doc), offSkip = offFor(c.role); // 그 문서를 잡은 실행이 돌 때만 끈다(다른 문서의 실행과 무관)
            if (skipped) c.acts.push(dashBtn("건너뛰기 취소", () => dashFlowSkip(c.per.doc, false, who), { disabled: !!offSkip, focus: `act:${c.ref}:unskip`, title: offSkip || "이 문서의 LLM 검증·보완을 다시 이 단계의 할 일로 둡니다" }));
            else if (c.state !== "done" && c.state !== "run") c.acts.push(dashBtn("건너뛰기", () => dashFlowSkip(c.per.doc, true, who), { disabled: !!offSkip, focus: `act:${c.ref}:skip`, title: offSkip || "이 문서는 LLM 검증·보완 없이 스크립트 분석만으로 진행합니다(「건너뛰기 취소」 로 되돌립니다)" }));
          }
          const view = DASH_FLOW_VIEW[s.key];
          if (view) c.acts.push(...view(C, c.role));
          if (c.doc && c.doc.id !== state.id) c.acts.push(dashBtn(`${DASH_FLOW_ROLE[c.role]} 열기`, () => dashOpen(c.doc.id), { focus: `act:${c.ref}:open`, title: `${c.doc.name} — 그 문서를 열어 이 단계의 결과를 봅니다(이 대시보드는 그 문서에서도 같습니다)` }));
        }
      }
      return { ...line, cards };
    });
    // g.lane = 이 묶음을 도는 실행이 잡는 문서(서버 — 문서 하나의 줄뿐인 묶음은 그 문서만: 다른 문서의 실행과 같이 돈다 · "" = 두 문서를 함께 쓴다). 서버의 can · why 는 도는 실행을 이미 본 것이다
    const gl = g.lane || "", paid = (g.paid || []).length, no = !srv ? SINGLE_NOT_SERVED : (V.ready && !g.can && runs.length ? g.why : "") || offFor(gl) || lack || (V.ready && !g.can ? g.why || "지금은 진행할 수 없습니다" : ""), name = `${g.no || ""} ${g.name || ""}`.trim();
    const first = !V.ready && !lack ? g === served[0] : true; // 문서 칸을 채운 뒤에야 서버가 차례를 센다 — 그 전에는 첫 묶음만 켠다
    const why = no || (first ? "" : `${served[0].no} 「${served[0].name}」 이 먼저입니다`);
    L.runs[g.id] = dashBtn("한 번에 진행", () => dashFlowRun(`${name} — 한 번에 진행`, g.id, { ...(gl ? { lane: gl } : {}), sig: V.sig || "" }), { disabled: !!why, primary: !why && mine, focus: `run:${g.id}`,
      title: why || [files.fill && !V.ready ? `${files.fill}.` : "", `이 묶음의 남은 단계를 차례로 한 번에 — ${g.does}. 사람 손이 필요한 곳에서는 멈춥니다(서버에서 진행 · 창을 닫아도 이어집니다)`,
        gl ? `${roleOf(gl)}만 쓰는 묶음입니다 — 다른 문서의 실행과 같이 돌 수 있습니다` : "", paid ? `유료 LLM — 문서 ${paid}개` : "", g.change ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") });
    if (srv) L.subs[g.id] = dashSoloEl(g, name, { busyOf: (role) => offFor(role) || lack, fill: files.fill && !V.ready ? `${files.fill}.` : "", run: (role, label) => dashFlowRun(label, g.id, { role, sig: V.sig || "" }) }); // 한 문서만 진행(서버가 센 solo — 없으면 줄 없음 · 그 문서를 잡은 실행이 돌 때만 끈다)
  }
  // 「이어서 한 번에 N→M단계」 — 할 일이 남은 첫 묶음 → 끝 묶음(= 끝까지 다 진행: 그 사이를 모두 서버가 맡을 때 — 서버가 from → to 로 돈다: 경계마다 최신 상태로 그 묶음을 할지 정하고 안 끝난 묶음에서 멈춘다)
  const rest = served.filter((g) => g.left > 0);
  if (rest.length > 1) {
    const a = rest[0], z = rest[rest.length - 1], span = V.stages.slice(V.stages.indexOf(a), V.stages.indexOf(z) + 1);
    if (span.every((g) => g.server && g.steps)) {
      const label = `이어서 한 번에 ${(a.no || "").replace(/단계$/, "")}→${z.no}`, no = off || lack || (V.ready && !a.can ? a.why || "지금은 진행할 수 없습니다" : ""), paid = new Set(span.flatMap((g) => g.paid || [])).size;
      M.top.push(dashBtn(label, () => dashFlowRun(label, a.id, { to: z.id, sig: V.sig || "" }), { disabled: !!no, focus: "run:chain",
        title: no || [files.fill && !V.ready ? `${files.fill}.` : "", `${rest.map((g) => `${g.no} 「${g.name}」`).join(" → ")} 을 이어서 한 번에 — 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다(서버에서 진행 · 창을 닫아도 이어집니다)`,
          paid ? `유료 LLM — 문서 ${paid}개` : "", span.some((g) => g.change) ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") }));
      if (no && !off) M.top.push(el("span", "dash-top-why", no)); // 꺼진 까닭이 서버의 것이면(앞 묶음이 먼저 · 문서 칸이 빔) 글로
    }
  }
  if (!active && V.last && (V.last.stages || []).length > 1) for (const x of V.last.stages) if (x.text) L.ends[x.id] = { ok: x.status === "done" || x.status === "left", text: x.text }; // 여러 묶음을 돈 지난 실행 — 묶음마다 그 끝 글
  await dashHands(M, L); // 사람이 하는 일 줄(정의 v2 의 hand) — 「했음」 · 「했음 취소」
  return L;
}

async function dashLive(job, M) {
  if (taskIsSingle(job)) return dashSingleLive(M); // 문서 하나로 조립한 것 — 서버가 센 상태 · 서버 쪽 실행기(붙박이 양식 표준화 · 양식 맞추기는 아래 가지 그대로)
  if (taskIsRelayFlow(job)) return dashFlowLive(M); // 줄 목록(v2)으로 조립한 이관형 — 서버가 센 상태 · 서버 쪽 실행기 · 문서 카드(표준 차례로 조립한 것 · 붙박이 이관은 아래 dashRelayLive 그대로)
  if (job === "plan_fit") return dashStdLive(M);
  if (agwFit(job)) return dashFitLive(M);
  if (taskIsRelay(job)) { const L = dashRelayLive(M); await dashHands(M, L); return L; } // 이관형 — 붙박이 이관 · 화면에서 조립한 TASK(spec_워크플로우 ② §14) · 조립한 것의 「사람이 하는 일」 줄(정의 v2)
  if (taskIsGather(job)) return dashGatherLive(M); // 취합형 — 붙박이 취합 · 취합형으로 조립한 것(같은 줄 key · 묶음은 그 정의의 것: dashGatherLive 가 줄이 든 묶음으로 잇는다)
  if (job === "style_copy") return dashStyleLive();
  if (job === "doc_edit") return dashEditLive();
  return { steps: {}, runs: {} };
}

async function dashModel() {
  const job = agwJob(), cat = (typeof TASK_CATALOG === "object" && TASK_CATALOG[job]) || {}, reg = DASH.reg && DASH.reg.tasks.find((t) => t.job === job);
  const M = { job, name: cat.name || job || "워크플로우 없음", reg, notes: [], top: [], groups: [], R: agwRunning() };
  if (!reg || !reg.stages.length) return M;
  const L = await dashLive(job, M), meta = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META;
  let i = 0;
  M.groups = reg.stages.map((g, gi) => ({
    id: g.id, label: g.meta && meta[g.meta] ? { no: meta[g.meta].no, name: meta[g.meta].name } : { no: g.no || String(gi + 1), name: g.name }, does: g.does, run: L.runs[g.id] || null, end: (L.ends || {})[g.id] || null, sub: (L.subs || {})[g.id] || null, parts: g.id === "map" && L.parts ? { rows: L.parts, add: L.partsAdd } : null, // 번호 = 등록부의 no(양식 표준화 「1단계」) · 없으면 차례
    nodes: g.steps.map((s, si) => {
      // L.at = 묶음마다 줄 차례대로의 상태(문서 하나로 조립한 것 — dashSingleLive: 같은 줄을 두 번 놓은 정의는 key 가 겹쳐 차례로 잇는다 · 그 자리의 key 가 다르면(등록부가 낡음) key 로) · 그 밖의 가지는 L.steps[key] 그대로
      const at = L.at && L.at[g.id] && L.at[g.id][si], live = (at && at.key === s.key ? at : null) || L.steps[s.key] || {}, via = live.via ? reg.stages.flatMap((x) => x.steps).find((x) => x.key === live.via) : null;
      const idx = ++i;
      // cards = 그 줄의 문서 카드들(줄 목록으로 조립한 이관형 — dashFlowLive: 두 문서에 하는 줄은 원본 · 목적 카드 둘). 줄(이 노드)은 끝난 수 · 「다음: …」 을 세고, 그리는 것은 카드다(dashGroupsEl) — 번호는 첫 카드에만
      const cards = live.cards ? live.cards.map((c, ci) => ({ ...s, ...c, idx: ci ? null : idx, lines: c.lines || [], acts: c.acts || [], via: null })) : null;
      return { ...s, idx, state: s.soon ? "soon" : live.state || "", text: live.text || "", lines: live.lines || [], acts: live.acts || [], via: via ? { key: via.key, name: via.name } : null,
        ...(live.word !== undefined ? { word: live.word } : {}), ...(live.skipped ? { skipped: true } : {}), ...(live.ref ? { ref: live.ref } : {}), ...(cards ? { cards } : {}) }; // word = 서버가 센 상태의 글(막힘 · 실패 · 건너뜀 …) · ref = 펴고 접는 이름(key 가 겹치는 줄)
    }),
  }));
  return M;
}

// ---------------------------------------------------------------- 그리기
function dashTags(s) { // 누가(스크립트 · LLM · 사람) · 문서 바뀜 · 자동 · 필수 · 선택 — 워크플로우 페이지의 꼬리표와 같은 말(2026-11-18 사용자 「안해도됨은 '선택' 으로 하고 저절로는 '자동' 으로」 · 「꼭 해야하는건 필수 라고 적어줘」 · 「사람, 스크립트, LLM, 문서바뀜 아이콘으로 넣어달라해」: 넷은 아이콘 + .sr-only 글)
  const box = el("span", "dash-tags"), by = (DASH.reg && DASH.reg.by) || {};
  const icon = (cls, text, name) => { const t = el("span", "dash-tag" + (cls ? ` dash-t-${cls}` : "")); t.title = text; t.append(agentIcon(name, 12), el("span", "sr-only", text)); return t; }; // 꾸밈 클래스는 dash-t- 로 — style.css 의 .doc 등과 안 겹치게
  for (const b of s.by) box.append(icon(b === "script" ? "" : b, by[b] || b, b));
  if (s.change === "doc") box.append(icon("doc", "문서 바뀜", "doc"));
  if (s.auto) box.append(el("span", "dash-tag dash-t-soft", "자동"));
  if (!s.optional && !s.soon && !s.auto) box.append(el("span", "dash-tag dash-t-must", "필수")); // 사람이 해야 다음으로 가는 단계(자동은 저절로 돌아 붙이지 않음)
  if (s.optional) box.append(el("span", "dash-tag dash-t-soft", "선택"));
  return box;
}

// 그리기 문맥 — **패널 대시보드와 첫 화면의 대시보드(home_dash.js HD_CTX)가 같은 그리기를 쓴다**(dashGroupsEl · dashNodeEl · dashDetailEl · dashMemoEl — 2026-11-20 사용자 "여기 dashboard 에는 여기 대쉬보드가 들어 가야지":
// 첫 화면의 것을 따로 그린 간단한 꼴로 두지 않는다). 보기마다 다른 것만 여기 둔다: focus = 다시 그린 뒤 초점을 되찾는 data- 이름(dataset 키) · id = 펼친 세부의 id 머리(두 보기가 한 문서에 같이 있다) ·
// toggle(key, open) = 단계 카드를 펴고 접는다 · go(key) = 「그 단계로」 · counted(n) = 끝난 수에 넣는 단계 · panel = 문서 화면의 보기(값 입력 폼은 문서가 열려 있어야 한다)
const DASH_CTX = { focus: "dashFocus", id: "dashD", panel: true, counted: dashCounted, toggle: (key, open) => { DASH.open = open ? "" : key; dashDraw(true); }, go: (key) => { DASH.open = key; dashDraw(true); } };

function dashDetailEl(n, id, C = DASH_CTX) {
  const d = el("div", "dash-detail");
  d.id = id;
  if (n.via) {
    const p = el("p", "dash-text muted", `이 단계는 「${n.via.name}」 의 단추로 함께 합니다.`), go = dashBtn("그 단계로", () => C.go(n.via.key));
    go.dataset[C.focus] = `via:${n.key}`;
    d.append(p, el("div", "dash-acts")); d.lastChild.append(go);
  }
  if (n.state === "each") d.append(el("p", "dash-text muted", "기관 문서마다 되풀이합니다 — 아래 「기관 문서」 줄에서 문서마다 진행합니다."));
  if (n.text) d.append(el("p", "dash-text", n.text));
  for (const [name, text] of n.lines) { const p = el("p", "dash-text"); if (name) p.append(el("span", "dash-sub", name), " "); p.append(text); d.append(p); }
  // 등록부의 설명(하는 일 · 하려면 · 조건)은 본문에 넣지 않는다 — 이름 옆 메모(dashMemoEl)에만(2026-11-21 사용자 「설명문은 노트에 넣도록 했잖아. 왜 여기에 다 넣는거야」 · 11-18 「메모 아이콘 해서 제목 쪽에」):
  // 전에는 차례가 아닌 단계의 본문에 「하려면 …」 을 적었다(메모와 같은 글 두 번). 본문 = 지금 상태 글 · 단추 · 꺼진 단추의 까닭뿐 — 그것이 없으면 본문을 달지 않는다(고른 테두리만 — dashNodeEl)
  if (C.panel && n.key === "values" && DASH.form && agwFit(agwJob())) { // 양식 표준화 · 양식 맞추기의 값 입력 — 에이전트 질문 카드와 같은 폼(doc_agent_work.js agwConfigForm)
    d.append(agwConfigForm({ id: "dash" }, { draw: () => dashDraw(true), ok: (x) => { DASH.form = false; dashExec("프로젝트 구성 추출", () => agwExec("config_set", x)); }, close: () => { DASH.form = false; dashDraw(true); } }));
  }
  if (n.acts.length) { const acts = el("div", "dash-acts"); acts.append(...n.acts); d.append(acts); }
  const off = n.acts.find((b) => b.tagName === "BUTTON" && b.disabled && b.title); // 꺼진 단추의 까닭을 글로(title 만으로는 안 보인다 — 2026-11-18 사용자: 「모두 반영」 이 왜 꺼졌는지 안 보였다 · dashStdTop 의 .dash-top-why 와 같은 생각)
  if (off) d.append(el("p", "dash-text dash-why", `「${off.textContent.trim()}」 — ${off.title}`));
  return d;
}

function dashMemoEl(n, C = DASH_CTX) { // 「하는 일 · 조건」 — 카드 머리 이름 옆 메모 아이콘(노트 도움말 · design.md §1-6). 2026-11-18 사용자 「하는 일 조건은 이렇게 줄을 넣지 말고 메모 아이콘 해서 제목 쪽에 넣어줘」(전에는 펼친 카드 맨 아래 접은 줄)
  const rows = [["하는 일", n.does], ...(n.out ? [["나오는 것", n.out]] : []), ...(n.cond || []).map((c) => [c.name, c.text])].filter(([, v]) => v);
  if (!rows.length) return null; // 등록부에 없는 줄(첫 화면 — 정의가 방금 바뀌어 서버가 낸 줄만 있을 때): 적을 글이 없다
  const b = hHelp(`${n.name} — 하는 일 · 조건`, rows.map(([k, v]) => `${k} — ${v}`).join("\n"));
  b.classList.add("dash-memo");
  b.dataset[C.focus] = `memo:${n.ref || n.key}`; // 다시 그려도 초점이 메모로 돌아온다(dashDraw · homeDashDraw)
  b.title = ""; // 카드 머리 줄의 풍선(title)이 메모 위에서 겹쳐 뜨지 않게
  return b;
}

// 단계 카드 — 머리 줄(.dash-node-top) = 번호 · 이름(펴고 접는 단추) + 꼬리표 + 메모 · 상태 글. 줄 어디를 눌러도 펴고 접는다(메모는 제 풍선만 — hHelp 가 누름을 멈춘다).
// n.word = 상태 글을 그 보기가 정할 때(첫 화면 — 서버의 글: 「막힘」 · 「실패」 · 「건너뜀」) · n.skipped = 「건너뜀」 으로 끝남(✓ 를 붙이지 않는다) ·
// 첫 화면의 문서 카드(home_dash.js hdCards — 번호는 왼쪽 차례 열에 있다): n.idx 없음 = 번호 동그라미를 그리지 않는다 · n.lead = 이름 앞의 꼬리표(「원본 문서」 · 「목적 문서」) · n.ref = 펴고 접는 이름(한 줄의 카드가 문서마다 — 없으면 key)
function dashNodeEl(n, gid, openKey, C = DASH_CTX) {
  const ref = n.ref || n.key, id = `${C.id}-${gid}-${ref.replace(/[^\w-]/g, "_")}`;
  // 고른 카드(open — 테두리 강조 · 「그 단계로」 가 가는 곳)라도 펼 것(상태 글 · 단추)이 없으면 본문을 달지 않는다 — 설명은 메모에만(시작 전 첫 화면의 카드 · 상태 글 없는 「남음」): shown = 본문을 달았나(aria-expanded)
  const open = ref === openKey, det = open ? dashDetailEl(n, id, C) : null, shown = !!(det && det.firstChild);
  const li = el("li", "dash-node" + (n.optional ? " opt" : "") + (n.soon ? " soon" : "") + (open ? " open" : "") + (n.same ? " same" : "")), top = el("div", "dash-node-top"), head = el("button", "dash-node-head"); // same = 앞 카드와 같은 줄의 다른 문서 카드(화살표 없이 붙여 그린다 — dashboard.css)
  li.dataset.key = n.key;
  li.dataset.state = n.state || "none";
  head.type = "button";
  head.dataset[C.focus] = `node:${ref}`;
  head.setAttribute("aria-expanded", String(shown));
  if (shown) head.setAttribute("aria-controls", id);
  if (n.state === "now" || n.state === "run") head.setAttribute("aria-current", "step");
  const main = el("span", "dash-node-main"), st = n.word !== undefined ? n.word : DASH_ST[n.state] || "", memo = dashMemoEl(n, C);
  head.append(el("b", null, n.name));
  main.append(...(n.lead ? [n.lead] : []), head, dashTags(n), ...(memo ? [memo] : []));
  if (n.idx != null) top.append(el("span", "dash-no", String(n.idx).padStart(2, "0")));
  top.append(main);
  if (st) { const s = el("span", "dash-st", n.state === "done" && !n.skipped ? `✓ ${st}` : st); s.id = `${id}-st`; head.setAttribute("aria-describedby", s.id); top.append(s); }
  top.title = `${n.name}${st ? ` — ${st}` : ""}${n.text ? `\n${n.text}` : ""}`;
  top.onclick = (e) => { if (e.target.closest(".panel-help")) return; C.toggle(ref, open); }; // 단추의 누름(Enter · Space 포함)도 여기로 올라온다
  li.append(top);
  if (shown) li.append(det);
  return li;
}

// 묶음 › 단계 — 묶음 머리(번호 · 이름 · 끝난 수 · (꼬리표) · 「한 번에 진행」) + (끝 글) + (머리 아래 한 줄) + 단계 카드의 세로 흐름(↓) + (취합의 기관 문서 줄).
// groups = [{id, label{no, name}, does, run 단추 | null, end{ok, text} | null, parts | null, nodes[…], tags?[머리의 꼬리표], sub?(머리 아래 한 줄), served?(첫 화면 — 서버가 센 묶음인가),
//   flowEl?(단계 흐름을 그 보기가 따로 그린 것 — 첫 화면의 「차례 번호 열 + 문서 카드」: 끝난 수는 그래도 nodes 로 센다)}]
function dashGroupsEl(groups, openKey, C = DASH_CTX) {
  const ol = el("ol", "dash-groups");
  ol.setAttribute("aria-label", "워크플로우 단계 묶음과 단계");
  for (const g of groups) {
    const li = el("li", "dash-group"), gh = el("div", "dash-ghead"), cnt = g.nodes.filter(C.counted), flow = el("ol", "dash-flow");
    li.dataset.group = g.id;
    if (g.served !== undefined) li.dataset.served = g.served ? "1" : "0";
    gh.append(el("span", "dash-gno", g.label.no), el("b", "dash-gname", g.label.name), el("span", "dash-gcount", cnt.length ? `${cnt.filter((n) => n.state === "done").length}/${cnt.length}` : `${g.nodes.length}개 단계`));
    if (g.tags) gh.append(...g.tags);
    if (g.run) gh.append(g.run);
    gh.title = g.does || "";
    flow.setAttribute("aria-label", `${g.label.name}의 단계`);
    if (!g.flowEl) for (const n of g.nodes) for (const c of n.cards || [n]) flow.append(dashNodeEl(c, g.id, openKey, C)); // cards = 그 줄의 문서 카드들(줄 목록으로 조립한 이관형 — 없으면 줄이 곧 카드)
    li.append(gh);
    if (g.end) li.append(el("p", "dash-gend" + (g.end.ok ? "" : " halt"), `${g.end.ok ? "끝남" : "멈춤"} — ${g.end.text}`)); // 「한 번에 진행」 의 끝(「작업 개요」 의 묶음 상태 줄과 같은 글)
    if (g.sub) li.append(g.sub);
    li.append(g.flowEl || flow);
    if (g.parts) li.append(dashPartsEl(g.parts));
    ol.append(li);
  }
  return ol;
}

function dashPartsEl(P) { // 취합 3단계 — 기관 문서마다 한 줄(들어온 차례): 이름 · 상태 · 글 · 단추(「작업 개요」 의 기관 문서 줄과 같은 단추)
  const box = el("div", "dash-parts"), head = el("div", "dash-parts-head"), ul = el("ul", "dash-part-list");
  head.append(el("b", null, `기관 문서 ${P.rows.length}개`), P.add);
  for (const r of P.rows) {
    const li = el("li", "dash-part"), top = el("div", "dash-part-top"), st = DASH_ST[r.state] || "";
    li.dataset.state = r.state;
    li.dataset.key = r.key;
    top.append(el("span", "dash-no", r.no), el("b", null, r.name), ...(st ? [el("span", "dash-st", r.state === "done" ? `✓ ${st}` : st)] : []));
    li.append(top);
    for (const [name, text] of r.lines) { const p = el("p", "dash-text"); if (name) p.append(el("span", "dash-sub", name), " "); p.append(text); li.append(p); }
    if (r.acts.length) { const acts = el("div", "dash-acts"); acts.append(...r.acts); li.append(acts); }
    ul.append(li);
  }
  if (!P.rows.length) ul.append(el("li", "dash-part muted", "기관 문서가 아직 없습니다 — 배포 기준본을 나눠 주고, 돌려받은 문서를 「기관 문서 올리기…」 로 넣습니다"));
  box.append(head, ul);
  return box;
}

function dashLiveEl(M) { // 지금 도는 것 — 에이전트 보기의 진행 카드와 같은 것(agwRunning) · 이 보기가 부른 행동
  const R = M.R, B = DASH.busy;
  if (M.lives && M.lives.length) { // 서버 실행들(줄 목록으로 조립한 이관형 — dashFlowLive 가 서버 상태의 runs 로 짓는다) — 실행마다 진행 줄 하나 · 「멈춤」 은 그 실행에만(문서마다 따로 도는 실행은 둘: spec_워크플로우 ② §18-22)
    const wrap = document.createDocumentFragment(), many = M.lives.length > 1;
    for (const X of M.lives) {
      const box = el("div", "dash-live"), text = el("span", "dash-live-text", agwLiveText(X));
      text.setAttribute("role", "status");
      text.dataset.run = box.dataset.run = String(X.n);
      if (X.lane) box.dataset.lane = X.lane;
      box.append(el("span", "ag-spin"), el("b", null, X.label), text,
        dashBtn(X.stopping ? "멈추는 중…" : "멈춤", () => { X.stop(); dashDraw(true); }, { disabled: X.stopping, title: `${many ? "이 실행만 멈춥니다 — " : ""}지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다`, focus: many ? `stop:${X.n}` : "stop" }));
      wrap.append(box);
    }
    return wrap;
  }
  if (!R && !B) return null;
  const box = el("div", "dash-live"), text = el("span", "dash-live-text", R ? agwLiveText(R) : `${B.label} — 하는 중 · ${fmtDur((Date.now() - B.t0) / 1000)}`);
  text.setAttribute("role", "status");
  box.append(el("span", "ag-spin"), el("b", null, R ? R.label : B.label), text);
  if (R && R.stop) box.append(dashBtn(R.stopping ? "멈추는 중…" : "멈춤", () => { R.stop(); dashDraw(true); }, { disabled: R.stopping, title: "지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다", focus: "stop" }));
  return box;
}

async function dashPick(job) { // TASK 고르기 — 「작업 개요」 의 TASK 칸과 같은 길(project_workspace.js projectTaskPick → taskSet) · 고른 뒤 그 자리에서 단계 흐름
  if (agwRunning()) { toast("지금 진행 중인 작업이 끝난 뒤에 고르세요", true); return; }
  const doc = dashKey();
  if (typeof projectTaskPick === "function") await projectTaskPick(job); else await taskSet("job", job);
  if (DASH.doc !== doc || !dashHasTask()) return;
  Object.assign(DASH, { open: null, nowKey: "", form: false, last: null, sig: "" });
  if (typeof $ === "function" && !$("paneDash").hidden) await dashShow();
}

function dashPickEl() { // TASK 가 없는 문서 — 이 문서의 형식으로 할 수 있는 TASK 마다 카드: 이름 · 하는 일 · 묶음 차례 · 「이 TASK 로」
  const root = el("section", "dash"), head = el("header", "dash-head"), title = el("div", "dash-title"), meta = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META;
  root.setAttribute("aria-label", "대시보드");
  const wf = el("a", "dash-wf", "워크플로우 ↗");
  wf.href = "/workflow#overview"; wf.target = "_blank"; wf.rel = "noopener"; wf.title = "워크플로우 페이지에서 워크플로우마다의 과정 보기(새 탭)";
  title.append(el("b", null, "워크플로우 고르기"), hHelp("대시보드 도움말", DASH_PICK_HELP), wf);
  // 작업의 워크플로우가 목록에 없는 조립한 것이면(지워짐 · 저장 파일을 못 읽음 — task_catalog.js taskLostWhy) 「TASK 가 없다」 가 아니라 그 까닭 한 줄(주황 띠 — 실행 단추 없이 · job 값은 그대로)
  const lost = taskLostWhy(agwJob());
  const next = el("p", "dash-next", lost ? "아래에서 다른 워크플로우를 고르면 그 단계 흐름이 보입니다" : "이 문서에는 워크플로우가 없습니다 — 워크플로우를 고르면 단계 흐름이 보입니다");
  next.setAttribute("role", "status");
  head.append(title, next);
  root.append(head);
  if (lost) { const n = el("div", "dash-note warn"); n.dataset.lost = "1"; n.append(el("span", null, lost)); root.append(n); }
  if (DASH.regErr && !DASH.reg) { root.append(el("p", "dash-note warn", `워크플로우를 읽지 못했습니다: ${DASH.regErr}`), dashBtn("다시 읽기", () => { DASH.regErr = ""; dashShow(); })); return root; }
  const fmt = state.format || "hwpx", ul = el("ul", "dash-picks");
  ul.setAttribute("aria-label", "이 문서로 할 수 있는 워크플로우");
  for (const [job, cat] of Object.entries(TASK_CATALOG)) {
    if (cat.soon || !taskAcceptOf(job).includes(fmt)) continue;
    const reg = DASH.reg && DASH.reg.tasks.find((t) => t.job === job), li = el("li", "dash-pick"), top = el("div", "dash-pick-top");
    li.dataset.job = job;
    top.append(el("b", null, cat.name));
    if (reg && reg.stages.length) top.append(el("span", "dash-gcount", `단계 ${reg.stages.reduce((s, g) => s + g.steps.length, 0)}개`));
    li.append(top, el("p", "dash-text", cat.desc || ""));
    if (reg && reg.stages.length) li.append(el("p", "dash-text muted", reg.stages.map((g) => (g.meta && meta[g.meta] ? meta[g.meta].name : g.name)).join(" › ")));
    const acts = el("div", "dash-acts");
    acts.append(dashBtn("이 워크플로우로", () => dashPick(job), { title: `이 문서의 워크플로우를 「${cat.name}」 로 적고 단계 흐름을 봅니다(문서는 바뀌지 않습니다)`, focus: `pick:${job}` }));
    li.append(acts);
    ul.append(li);
  }
  if (!ul.children.length) ul.append(el("li", "dash-pick muted", `이 문서 형식(${fmt})으로 할 수 있는 워크플로우가 없습니다`));
  root.append(ul);
  return root;
}

// ---------------------------------------------------------------- 작업 내용 초기화(2026-11-22 사용자 "작업내용을 초기화 하는게 없어, 대시보드에 그게 들어 가면 좋겠는데" — spec_작업에이전트 ② §9 「작업 내용 초기화」)
// 새 길이 아니다 — 「고친 문단」 탭의 「초기화…」 와 같은 기능(same_file.js workReset → POST /api/works/{id}/reset: 그 문서를 올린 직후로 — spec_작업 ② §3-1). 두 대시보드(이 패널 · 첫 화면 home_dash.js)가 같이 쓴다.
// 단추 「작업 내용 초기화…」 → 그 자리에 펴지는 작은 상자(모달 아님 — design.md §16): 비우는 것 · 남는 것 + 문서마다 단추(그 워크플로우의 문서 칸 — 서버 상태 GET …/flow 의 docs) + 「모든 문서」(둘 이상일 때) + 「닫기」.
// 문서를 고르는 것이 확인이다(펴기 → 고르기 두 걸음 — 되돌릴 수 없는 일이라 확인을 거치되(design.md §18) 창이 아니라 그 자리의 인라인 확인: 「작업 지우기」 와 같은 꼴 · 초점은 「취소」 에서 · Esc = 취소).
// 문서마다 따로 · 모두 같이(「한 문서만」 과 같은 갈래). 도는 실행이 있으면 꺼 둔다(서버도 거절 — _flow_busy).
// R = 그 보기의 상태 {open, docs[{role, label, name, id}] | null, err, busy} · opt = {wid 그 묶음의 문서 하나, off 누를 수 없는 까닭, redraw(), done(초기화한 id 목록) → 약속, focusAttr}
const DASH_RESET_TIP = "작업 내용 초기화 — 고른 문서를 올린 직후로 되돌립니다(누르면 문서를 고르는 칸이 펴집니다 · 고르기 전에는 아무것도 안 바뀝니다)";
const dashResetFresh = () => ({ open: false, docs: null, err: "", busy: "" });
function dashResetDocs(V) { // 서버 상태(GET …/flow)의 문서 칸 → [{role, label, name, id}] — 원본 문서(취합은 기관 문서마다) → 목적 문서
  const D = (V && V.docs) || {}, out = [], add = (role, d, title) => { if (d && d.id && !out.some((x) => x.id === d.id)) out.push({ role, label: title, name: d.name || "", id: d.id }); };
  const many = D.sources || [];
  if (many.length) many.forEach((d, i) => add("source", d, many.length > 1 ? `원본 문서 ${i + 1}` : "원본 문서"));
  else add("source", D.source, "원본 문서");
  add("target", D.target, "목적 문서");
  return out;
}
async function dashResetOpen(R, wid, redraw, focus = () => {}) { // focus = 편 뒤 초점을 「취소」 로(그 보기의 초점 함수)
  Object.assign(R, { open: true, docs: null, err: "" });
  await redraw(); // 패널의 그리기(dashDraw)는 약속이다 — 그린 뒤에 초점을 옮긴다(다시 그릴 때는 그 단추에 초점이 남는다)
  focus();
  try { R.docs = dashResetDocs(await api(`/api/works/${wid}/flow`)); if (!R.docs.length) R.err = "이 워크플로우의 문서 칸이 비어 있습니다"; }
  catch (e) { R.err = `문서 칸을 읽지 못했습니다: ${e.message}`; }
  await redraw();
}
async function dashResetRun(R, list, { redraw, done }) {
  if (R.busy || !list.length) return;
  R.busy = list.map((d) => d.label).join(" · ");
  const mine = list.some((d) => d.id === state.id), ok = [], bad = [];
  if (mine) { state.commitBusy = "reset"; if (typeof commitBar === "function") commitBar(); setSaveState("busy", "작업 내용 초기화 중…"); } // 「초기화…」(workResetAsk)와 같이 — 도는 동안 편집 · 확정을 막는다
  redraw();
  for (const d of list) { try { await workReset(d.id); ok.push(d); } catch (e) { bad.push(`${d.label}(「${d.name}」): ${e.message}`); } } // 차례로 — 한 문서가 안 돼도 다른 문서는 한다
  if (mine) {
    state.commitBusy = false;
    if (!ok.some((d) => d.id === state.id)) { setSaveState("err", "초기화하지 못함"); if (typeof commitBar === "function") commitBar(); }
  }
  Object.assign(R, { busy: "", open: !!bad.length && !ok.length });
  if (ok.length) { try { await done(ok.map((d) => d.id)); } catch (e) { console.error(e); } }
  if (ok.length) toast(`작업 내용을 초기화했습니다 — ${ok.map((d) => d.label).join(" · ")}: 올린 원본부터 다시 시작합니다`);
  if (bad.length) toast(`작업 내용을 초기화하지 못했습니다 — ${bad.join(" / ")}`, true);
  if (typeof loadWorks === "function") loadWorks();
  redraw();
}
function dashResetParts(R, { wid, off = "", redraw, done, focusAttr = "dashFocus" }) { // → [요소] — 닫혀 있으면 단추 하나 · 펴면 상자 하나(그 안에 「취소」)
  const mark = (b, key) => { b.dataset[focusAttr] = key; return b; };
  const toCancel = () => { const c = [...document.querySelectorAll(".dash-reset button")].find((x) => x.dataset[focusAttr] === "reset:close"); if (c) c.focus({ preventScroll: true }); }; // 다시 그린 뒤의 새 「취소」
  if (!R.open) return [mark(hBtn(R.busy ? "초기화 중…" : "작업 내용 초기화…", () => dashResetOpen(R, wid, redraw, toCancel), { cls: "btn sm", disabled: !!off || !!R.busy || !wid, title: off || DASH_RESET_TIP }), "reset")];
  const box = el("div", "dash-reset");
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "작업 내용 초기화");
  box.append(el("p", "dash-reset-head", "작업 내용 초기화 — 고른 문서를 올린 직후로 되돌립니다"),
    el("p", "dash-reset-text", `비우는 것: ${SF_RESET_LOSE}\n남는 것: ${SF_RESET_KEEP}\n비운 것은 문서마다 작업 폴더의 reset/ 에 옮겨 두고 화면에서는 되살리지 않습니다.`));
  if (!R.docs) box.append(el("p", "dash-text muted", R.err || "문서 칸을 읽는 중…"));
  else {
    if (R.err) box.append(el("p", "dash-note warn", R.err));
    const lines = el("ul", "dash-reset-docs");
    for (const d of R.docs) { const li = el("li"); li.append(el("span", "dash-reset-role", `${d.label}${d.id === state.id ? " — 지금 문서" : ""}`), el("span", "dash-reset-name", d.name)); lines.append(li); }
    box.append(lines);
  }
  const acts = el("div", "dash-reset-acts"), stop = off || (R.busy ? "초기화하는 중입니다" : "");
  if (R.busy) acts.append(el("span", "dash-text muted", `초기화 중… — ${R.busy}`));
  for (const d of R.docs || []) acts.append(mark(hBtn(`${d.label} 초기화`, () => dashResetRun(R, [d], { redraw, done }), { cls: "btn sm danger", disabled: !!stop, title: stop || `「${d.name}」 을(를) 올린 직후로 되돌립니다 — 다른 문서는 그대로입니다` }), `reset:${d.id}`));
  if ((R.docs || []).length > 1) acts.append(mark(hBtn("모든 문서 초기화", () => dashResetRun(R, R.docs, { redraw, done }), { cls: "btn sm danger", disabled: !!stop, title: stop || `이 워크플로우의 문서 ${R.docs.length}개(${R.docs.map((d) => d.label).join(" · ")})를 모두 올린 직후로 되돌립니다` }), "reset:all"));
  const cancel = () => { if (R.busy) return; Object.assign(R, dashResetFresh()); redraw(); };
  acts.append(mark(hBtn("취소", cancel, { cls: "btn sm", disabled: !!R.busy, title: "초기화하지 않고 닫습니다(Esc)" }), "reset:close"));
  box.append(acts);
  box.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); } });
  return [box];
}
const dashResetState = () => (DASH.reset && DASH.reset.key === state.id ? DASH.reset : (DASH.reset = { key: state.id, ...dashResetFresh() })); // 이 패널의 상태 — 문서마다(load 로 차례가 바뀌어도 그 문서면 그대로: 초기화한 뒤 다시 여는 동안)
async function dashResetDone(ids) { // 패널 — 지금 문서를 초기화했으면 다시 열고 첫 분석(workResetAsk 와 같다) · 둘째 면의 문서를 초기화했으면 그 면을 다시 읽는다
  const shown = typeof peerShown === "function" ? peerShown() : "";
  if (shown && ids.includes(shown)) { try { $("peerFrame").contentWindow.location.reload(); } catch { /* 여는 중 */ } }
  if (state.id && ids.includes(state.id)) { await load(state.id); firstRun(); }
  if (DASH.flow) DASH.flow.stale = true;
}
function dashResetEl(M) { // 패널 대시보드 맨 아래 — 도는 일이 있으면 꺼 둔다(에이전트 · 한 번에 진행 · 서버 실행)
  if (!state.id || !state.stored) return null;
  const off = M.R || (M.lives && M.lives.length) || DASH.busy ? "지금 진행 중인 작업이 끝난 뒤에 초기화하세요 — 「멈춤」 으로 멈출 수 있습니다" : state.commitBusy && state.commitBusy !== "reset" ? "확정하는 중입니다 — 끝난 뒤에 초기화하세요" : "";
  const wrap = el("div", "dash-reset-row");
  wrap.append(...dashResetParts(dashResetState(), { wid: state.id, off, redraw: () => dashDraw(true), done: dashResetDone }));
  return wrap;
}

function dashEl(M) {
  if (!dashHasTask(M.job)) return dashPickEl();
  const root = el("section", "dash"), head = el("header", "dash-head"), title = el("div", "dash-title");
  root.setAttribute("aria-label", "대시보드");
  const nodes = M.groups.flatMap((g) => g.nodes), counted = nodes.filter(dashCounted), summary = taskIsGather(M.job) ? dwfSnapshot(M) : null;
  const done = summary ? summary.done : counted.filter((n) => n.state === "done").length, total = summary ? summary.total : counted.length;
  const wf = el("a", "dash-wf", "워크플로우 ↗");
  wf.href = `/workflow#${encodeURIComponent(M.job)}`; wf.target = "_blank"; wf.rel = "noopener"; wf.title = "워크플로우 페이지에서 이 워크플로우의 과정 보기(새 탭)";
  title.append(dwfToggleEl(M), ...(total && M.job !== "doc_edit" ? [el("span", "dash-count", `끝남 ${done}/${total}`)] : []), hHelp("대시보드 도움말", DASH_HELP), wf);
  const run = nodes.find((n) => n.state === "run"), now = nodes.find((n) => n.state === "now"), next = el("p", "dash-next");
  next.setAttribute("role", "status");
  next.textContent = M.lives && M.lives.length ? `진행 중 — ${M.lives.map((x) => x.label).join(" · ")}` : M.R ? `진행 중 — ${M.R.label}` : run ? `진행 중 — ${String(run.idx).padStart(2, "0")} ${run.name}` : now ? `다음: ${String(now.idx).padStart(2, "0")} ${now.name}`
    : M.job !== "doc_edit" && total && done === total ? "모두 끝남" : taskIsGather(M.job) && summary ? "기관 문서별 진행 상태를 확인하세요" : "";
  head.append(title);
  if (next.textContent) head.append(next);
  root.append(head);
  const workflows = dwfListEl(M);
  if (workflows) root.append(workflows);
  const live = dashLiveEl(M);
  if (live) root.append(live);
  if (DASH.last) { const p = el("p", "dash-last" + (DASH.last.ok ? "" : " halt")); p.append(el("b", null, DASH.last.label), ` — ${DASH.last.text}`); root.append(p); }
  for (const x of [...(M.last ? [M.last] : []), ...(M.lasts || [])]) { const p = el("p", "dash-last" + (x.ok ? "" : " halt"), x.text); p.dataset.flowLast = "1"; root.append(p); } // 서버 실행의 지난 끝(서버가 지은 글 그대로 — 문서 하나로 조립한 것 dashSingleLive 는 하나 · 줄 목록으로 조립한 이관형 dashFlowLive 는 같이 돌던 다른 문서의 실행까지: 끝난 차례)
  for (const n of M.notes) { const p = el("div", "dash-note" + (n.warn ? " warn" : "")); p.append(el("span", null, n.text)); if (n.act) p.append(n.act); root.append(p); }
  if (M.top.length) { const top = el("div", "dash-top"); top.append(...M.top); root.append(top); }
  if (DASH.regErr && !M.reg) { root.append(el("p", "dash-note warn", `워크플로우를 읽지 못했습니다: ${DASH.regErr}`), dashBtn("다시 읽기", () => { DASH.regErr = ""; dashShow(); })); return root; }
  if (!M.reg) { root.append(el("p", "dash-text muted", M.job ? "단계 흐름을 읽는 중…" : "워크플로우가 적히지 않은 문서입니다 — 단계 흐름이 없습니다")); return root; }
  if (!M.groups.length) { root.append(el("p", "dash-text muted", M.reg.soon ? "준비 중인 워크플로우입니다 — 아직 등록된 단계가 없습니다" : "등록된 단계가 없습니다")); return root; }
  const cardOf = (n) => (n && n.cards ? n.cards.find((c) => c.state === "run") || n.cards.find((c) => c.state === "now") || n.cards.find((c) => c.state !== "done") || n.cards[0] : n); // 문서 카드가 있는 줄 — 도는(없으면 「지금」 · 안 끝난) 카드
  const cur = cardOf(run || now), asked = DASH.open ? nodes.find((n) => n.cards && (n.ref || n.key) === DASH.open) : null; // asked = 줄의 key 로 편 것(첫 화면의 「문서 화면에서 열기」) — 그 줄의 문서 카드로
  const openKey = DASH.open === null ? (cur ? cur.ref || cur.key : "") : asked ? cardOf(asked).ref : DASH.open; // ref = key 가 겹치는 줄 · 문서 카드의 펴고 접는 이름(없으면 key — dashNodeEl 과 같은 셈)
  root.append(dashGroupsEl(M.groups, openKey)); // 묶음 › 단계 — 첫 화면의 대시보드와 같은 그리기(home_dash.js)
  const reset = dashResetEl(M); // 맨 아래 — 작업 내용 초기화(문서마다 · 모두)
  if (reset) root.append(reset);
  return root;
}

function dashSig(M) { // 다시 그릴지 — 상태 · 글 · 단추(글 · 켜짐 · 강조)가 같으면 도는 글만 바꾼다(1초마다 · 초점 유지)
  const b = (x) => (x ? `${x.textContent}|${x.disabled ? 1 : 0}|${x.className}|${x.title}|${(x.getAttribute && x.getAttribute("aria-pressed")) || ""}` : ""); // 눌림(고르기 칩 — 「넣을 구성 선택」)도
  // busy 이름 — 「이어서 한 번에」 가 묶음을 넘어갈 때 바뀐다
  return JSON.stringify([M.job, !!M.reg, !!DASH.reg, state.format, DWF.open, DWF.library, DWF.items, DWF.loaded, DWF.busy, DWF.error, dwfBlocked(), DASH.regErr, DASH.open, DASH.form, DASH.busy ? DASH.busy.label : "", DASH.last, M.R ? `${M.R.kind}|${M.R.label}|${M.R.stopping}|${!!M.R.stop}` : "",
    DASH.reset && DASH.reset.key === state.id ? [DASH.reset.open, DASH.reset.busy, DASH.reset.err, DASH.reset.docs] : 0, state.stored, state.commitBusy, // 작업 내용 초기화(dashResetEl)
    M.notes.map((n) => [n.text, b(n.act)]), M.last || 0, M.lasts || 0, (M.lives || []).map((x) => [x.n, x.label, x.stopping]), M.top.map(b),
    M.groups.map((g) => [b(g.run), g.sub ? [...g.sub.querySelectorAll("button")].map(b) : 0, g.end, g.parts ? [b(g.parts.add), g.parts.rows.map((r) => [r.state, r.lines, r.acts.map(b)])] : 0, g.nodes.map((n) => [n.state, n.word || "", n.text, n.lines, n.acts.map(b), n.cards ? n.cards.map((c) => [c.ref, c.state, c.word || "", c.text, c.lines, c.acts.map(b)]) : 0])])]);
}

async function dashDraw(force = false) {
  const box = $("dashBox");
  if (!box || !state.id) return;
  const seq = ++DASH.seq, doc = dashKey(), job = agwJob();
  let M;
  try { M = await dashModel(); } catch (e) { console.error(e); M = { job: agwJob(), name: "대시보드", reg: null, notes: [{ text: `상태를 읽지 못했습니다: ${e.message}`, warn: true }], top: [], groups: [], R: null }; }
  if (seq !== DASH.seq || doc !== dashKey() || job !== agwJob()) return;
  if (!DWF.busy) dwfObserve(M);
  const nowNode = M.groups.flatMap((g) => g.nodes).find((n) => !n.optional && (n.state === "run" || n.state === "now")), nowKey = nowNode ? nowNode.ref || nowNode.key : ""; // 안 해도 되는 단계가 도는 것은 차례가 아니다 — 그 카드를 펴고 돌린 LLM 검토가 끝나도 카드가 그대로(결과 단추가 보이게)
  if (nowKey !== DASH.nowKey) { if (DASH.nowKey && !DASH.pin) DASH.open = null; DASH.pin = false; DASH.nowKey = nowKey; } // 차례가 나아가면 펼친 카드도 새 「지금」 으로(사람이 편 카드는 차례가 그대로인 동안만) · 방금 「했음」 을 누른 카드는 그 한 번은 그대로(DASH.pin — dashHand)
  const sig = dashSig(M);
  if (!force && sig === DASH.sig) { // 그대로 — 도는 글만
    if (M.lives && M.lives.length) { // 서버 실행마다의 진행 줄
      for (const X of M.lives) { const t = box.querySelector(`.dash-live-text[data-run="${X.n}"]`), s = agwLiveText(X); if (t && t.textContent !== s) t.textContent = s; }
      return;
    }
    const t = box.querySelector(".dash-live-text"), s = M.R ? agwLiveText(M.R) : DASH.busy ? `${DASH.busy.label} — 하는 중 · ${fmtDur((Date.now() - DASH.busy.t0) / 1000)}` : "";
    if (t && s && t.textContent !== s) t.textContent = s;
    return;
  }
  DASH.sig = sig;
  const a = document.activeElement, focus = a && box.contains(a) ? a.dataset.dashFocus || "" : "", ring = !!(focus && a.matches(":focus-visible")); // 키보드로 온 초점이었나
  if (typeof panelHelpOwner !== "undefined" && panelHelpOwner && box.contains(panelHelpOwner)) panelHelpClose(); // 떼어 낼 메모 · 도움말의 풍선이 주인 없이 남지 않게
  box.replaceChildren(dashEl(M));
  if (DWF.busy) for (const control of box.querySelectorAll(".dash-groups button, .dash-groups input, .dash-groups select, .dash-top button")) control.disabled = true;
  // 다시 그려도 초점은 그 단추에 — 초점 테두리는 키보드로 온 초점일 때만(2026-11-18 사용자 「왜 계획 보기는 위치가 그렇냐」: 마우스로 누른 단추가 다시 그릴 때 테두리(2px · 2px 밖)를 얻어 커지고 어긋나 보였다)
  if (focus) { const f = [...box.querySelectorAll("[data-dash-focus]")].find((x) => x.dataset.dashFocus === focus && !x.disabled); if (f) f.focus({ preventScroll: true, focusVisible: ring }); }
}

setInterval(() => { // 1초 — 보이는 동안만: 다른 보기 · 에이전트 · 「한 번에 진행」 이 바꾼 상태를 따라간다(서버는 읽지 않는다 — 화면이 들고 있는 값으로 셈)
  const pane = $("paneDash");
  if (!pane || pane.hidden || $("panel").hidden || document.hidden || !state.id) return;
  if (DASH.doc !== dashKey()) { dashShow(); return; } // 다른 문서를 열었다
  const a = document.activeElement;
  if (DASH.form && a && a.closest && a.closest("#paneDash .agw-form")) return; // 값을 적는 동안은 다시 그리지 않는다
  if (a && a.tagName === "SELECT" && a.closest("#paneDash")) return; // 고르기 목록(「구성 불러오기」)에 초점이 있는 동안도 — 다시 그리면 펼친 목록이 닫힌다
  dashDraw();
}, 1000);
