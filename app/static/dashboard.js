"use strict";
// 대시보드(패널 탭 「대시보드」 — spec_작업에이전트 ② §9 · design.md §17): 지금 문서의 TASK 를 **단계 흐름**(워크플로우 등록부 GET /api/workflow 의 묶음 › 단계 — /workflow 의 「단계 흐름」 과 같은 차례)으로 보이고,
// 단계마다 **지금 상태**(끝남 · 지금 · 남음 …)와 **그 단계를 하는 단추**를 둔다. 2026-11-18 사용자(/workflow 의 「단계 흐름」 그림을 보이며) "도구에 이런 플로우가 있으면 좋겠고, 여기서 실행을 다 할 수 있었으면 좋겠어. 탭을 추가해줘".
// **새 실행 길을 만들지 않는다**(spec_작업에이전트 ② §7 ⓒ): 단계의 상태 · 단추는 「작업 내용」 이 그리는 것(이관 taskSteps · 취합 gatherSteps — 같은 함수를 불러 단추를 새로 받음)과
//   에이전트의 상태 · 행동(양식 표준화 · 양식 맞추기 agwStatus · agwExec), 서식 복사의 단계 상태(slStepState)를 쓰고, 묶음의 「한 번에 진행」 은 그 TASK 의 것(divRunAll · taskRunAll · gatherRunAll · styleSaveAuto · headsRunAll · headsPickRun — 2026-11-18 부터 확인 창 없이)을 그대로 부른다.
//   양식 표준화(plan_fit — spec_양식표준화)의 2 · 3단계(헤딩 추출 · 표)는 분석 상태(doc_agent_work.js agwStdSteps — 에이전트와 같은 셈)로 세고, 머리 아래 「이어서 한 번에 N→3단계」 가 묶음의 실행을 차례로 잇는다(dashStdChain).
//   단계의 차례 · 이름 · 누가 · 조건은 등록부(app/workflow.py)가 원본이다 — 여기서 다시 적지 않는다. 도는 것은 agwRunning(에이전트 보기의 진행 카드와 같은 것)으로 본다.
// **TASK 의 단계나 그 단계의 실행 함수를 바꾸면 아래 dash<TASK>Live 의 그 TASK 가지도 함께 본다**(CLAUDE.md — agwStatus · agwExec 와 같은 약속).
// 읽히는 차례: doc_agent_work.js 다음(agwJob · agwFit · agwStatus · agwExec · agwRunning · agwLiveText · agwConfigForm · agwFitApplied · agwStd*). app.js: state · $ · el · hBtn · toast · api · showTab · openWork · dv · div* · task* · TASK_STAGES · heads ·
//   heads_run_all.js(headsRunAll) · heads_run_pick.js(headsPickRun · hrpOff · hrpStep) · tpl_plan_bar.js(tpbApply · tplPlanGo) · doc_status.js(dsTo) ·
//   gather.js(gt · gatherPlan · gatherSteps · gatherActEl · gatherRunAll · gatherUrl · gatherPickFiles · gatherUploadMany · GT_STAGES) · gather_quick.js(gqRun) · style_lib.js(STYLE · styleSave* · slStepState · styleLibOpen) · task_catalog.js(TASK_CATALOG · TASK_STAGE_META).

const DASH = { reg: null, regErr: "", regLoad: null, doc: "", primed: "", open: null, nowKey: "", form: false, busy: null, last: null, sig: "", seq: 0, loadKey: "", projTried: "" };
// open = 편 단계 key(null = 「지금」 단계를 저절로 · "" = 모두 접음 — 「지금」 이 바뀌면 null 로) · nowKey = 마지막으로 그린 「지금」(도는 중) 단계 · form = 프로젝트 구성 입력 폼을 폈나(양식 표준화 · 양식 맞추기) · busy = 이 보기가 부른 행동 {label, t0} · last = 그 끝 {label, ok, text}
// loadKey = 「구성 불러오기」 목록에서 고른 것(양식 표준화 — 다시 그려도 그대로) · projTried = 다른 프로젝트 목록을 읽어 본 문서(divProjectsLoad — 못 읽어도 1초마다 되풀이하지 않게)
const DASH_ST = { done: "끝남", now: "지금", ready: "할 수 있음", todo: "남음", hold: "기관 미지정", run: "진행 중", soon: "준비 중" }; // 글로 구별한다(design.md §11 — 색에만 기대지 않음). 「기관 문서마다」(each) · 따로 안 셈("")은 꼬리표 없음
const DASH_COUNTED = new Set(["done", "now", "ready", "todo", "hold", "run"]);
const dashCounted = (n) => !n.optional && DASH_COUNTED.has(n.state); // 끝난 수에 넣는 단계 — 안 해도 되는 단계 · 따로 세지 않는 단계 · 준비 중은 뺀다(design.md §11)
const DASH_HELP = "이 TASK 의 단계를 워크플로우의 차례대로 보이고, 단계마다 지금 상태와 그 단계를 하는 단추를 둡니다. 단계를 누르면 펴지고, 펴면 지금 상태 · 단추 · 「하는 일 · 조건」 이 보입니다.\n"
  + "단추는 패널 「작업 내용」 · 에이전트와 같은 기능을 부릅니다 — 누르면 확인 창 없이 바로 합니다(문서를 바꾼 것은 실행 취소로 되돌리고, 유료 LLM 을 부르는 단추는 풍선 도움말에 그렇게 적습니다).\n"
  + "묶음 머리의 「한 번에 진행」 은 그 묶음의 남은 단계를 차례로 합니다(사람이 봐야 할 곳에서는 멈추거나 넣지 않고 남김).\n"
  + "머리 아래 「이어서 한 번에」 는 남은 묶음을 차례로 잇습니다(앞 묶음이 끝나지 않으면 뒤 묶음은 시작하지 않고 한 것 · 멈춘 까닭 · 남은 것을 머리에 적음).\n"
  + "꼬리표 아이콘 — 사람(파랑) · 스크립트(</>) · LLM(보라 반짝임) · 문서 바뀜(주황 문서+연필) — 마우스를 올리면 이름이 보입니다. 「필수」 는 해야 다음으로 가는 단계, 「자동」 은 누르지 않아도 도는 단계입니다.\n"
  + "점선 단계(「선택」)는 안 해도 되는 단계, 「준비 중」 은 아직 없는 단계입니다. 값 입력 · 목록 보기처럼 넓은 일은 「작업 내용」 이나 문서 옆 열에서 합니다.";

// 탭은 문서가 열려 있으면 늘 보인다(app.js toolShown("Dash")) — 2026-11-18 사용자 "내가 단계 흐름에서 자동 실행할 수 있도록, 여기 탭에 넣어 달라고 했는데 보이질 않아"(TASK 없이 연 문서라 탭이 감춰져 있었다: 전에는 TASK 가 적힌 문서만).
// TASK 가 없으면 이 문서에 맞는 TASK 를 고르는 카드(dashPickEl) — 고르면 그 자리에서 단계 흐름
const dashShown = () => !!state.id;
const dashHasTask = (job = agwJob()) => typeof TASK_CATALOG === "object" && !!TASK_CATALOG[job];
const DASH_PICK_HELP = "이 문서에는 TASK 가 적혀 있지 않습니다. TASK 를 고르면 그 TASK 의 단계 흐름이 여기 보이고, 단계마다 지금 상태와 실행 단추 · 묶음의 「한 번에 진행」 이 생깁니다.\n"
  + "고르는 것은 패널 「작업 내용」 의 TASK 칸과 같습니다(이 문서에 TASK 를 적음 — 문서는 바뀌지 않습니다). 이 문서의 형식(hwpx · docx)으로 할 수 있는 TASK 만 보입니다.";
const dashKey = () => `${state.id}|${state.epoch}`;
const dashHere = (t) => String(t || "").replace(/위 칸에서/g, "「작업 내용」 의 칸에서").replace(/아래 「/g, "「작업 내용」 의 「").replace(/아래 입력 칸/g, "「작업 내용」 의 입력 칸"); // 「작업 내용」 의 단계 글은 그 패널 안의 자리를 가리킨다 — 여기서는 그 패널 이름으로

function dashBtn(label, run, { primary = false, disabled = false, title = "", focus = "" } = {}) {
  const b = hBtn(label, run, { cls: "btn sm" + (primary ? " primary" : ""), disabled, title });
  if (focus) b.dataset.dashFocus = focus;
  return b;
}

function dashRegLoad() { // 워크플로우 등록부 — 페이지에 한 번 읽는다(서버를 다시 켜야 바뀐다)
  if (DASH.reg) return Promise.resolve(DASH.reg);
  if (!DASH.regLoad) DASH.regLoad = api("/api/workflow").then((d) => { DASH.reg = d; DASH.regErr = ""; return d; }, (e) => { DASH.regErr = e.message || String(e); return null; }).finally(() => { DASH.regLoad = null; });
  return DASH.regLoad;
}

async function dashPrime() { // 그 TASK 의 상태를 문서마다 처음 한 번 읽는다 — 그 뒤는 화면이 들고 있는 값으로 센다(1초마다 서버를 다시 읽지 않는다)
  const job = agwJob(), key = `${dashKey()}|${job}`;
  if (DASH.primed === key) return;
  DASH.primed = key;
  try {
    if (agwFit(job) || job === "plan_to_report" || job === "plan_merge") { if (!dv.view) await divShow(); }
    if (job === "plan_fit") { await agwHeadsView(); if (!agwStdView()) await agwStdFresh(); } // 양식 표준화 2 · 3단계 — 헤딩 요약(단계별 실행이 1단계 결과를 본다 · 추출을 저절로 시작하지 않음) · 분석 상태
    if (job === "plan_to_report" && !Object.keys(taskFlow.div || {}).length) await taskFlowLoad();
    if (job === "plan_merge" && typeof gt === "function" && !gt().view) await gatherLoad();
  } catch (e) { console.error(e); }
}

async function dashShow() { // app.js showTab("Dash")
  if (!state.id) return;
  if (DASH.doc !== dashKey()) Object.assign(DASH, { doc: dashKey(), open: null, nowKey: "", form: false, last: null, busy: null });
  DASH.sig = "";
  await dashDraw(true);
  await dashRegLoad();
  if (DASH.doc !== dashKey()) return;
  await dashPrime();
  if (DASH.doc === dashKey()) await dashDraw(true);
}

async function dashExec(label, fn) { // 이 보기가 부르는 행동 하나(에이전트의 행동 · 기존 함수) → 끝 글을 머리 아래 한 줄에 남긴다. fn → {ok, text} | null(그만둠 — 남기지 않음)
  if (DASH.busy) return;
  if (agwRunning()) { toast("지금 진행 중인 작업이 끝난 뒤에 누르세요", true); return; } // 같은 문서에 두 실행을 겹치지 않는다(에이전트 카드와 같은 약속)
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
    else if (a.name === "apply") step("apply").acts.push(dashBtn(a.label, () => dashExec(a.label, async () => { // 「작업 내용」 의 「② 반영」 과 같은 길(2026-11-18 부터 확인 창 없이 — 실행 취소 한 번)
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
  if (dv.msg && dv.msg.kind === "halt") L.ends = { [gid]: { ok: false, text: dv.msg.text } }; // 「한 번에 진행」 · 반영이 멈춘 까닭(「작업 내용」 의 상태 줄과 같은 글)
  const why = divRunWhy(), locked = !!dv.busy || divRunLocked() || !!DASH.busy || !!agwRunning(), applied = L.steps.apply.state === "done"; // 같은 문서에 두 실행을 겹치지 않는다(헤딩 판정 · 전체 실행 · 대시보드가 부른 행동이 도는 동안)
  const no = !st.facts.confirmed ? "프로젝트 구성 값을 먼저 확정하세요" : applied ? "남은 단계가 없습니다" : why || (locked ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : "");
  return dashBtn("한 번에 진행", () => divRunAll(), { disabled: !!no, focus: `run:${gid}`,
    title: no || "변경 계획 → 반영을 한 번에 — 계획 오류 · 미해결 자리가 있거나 기관의 차례가 마지막 반영과 다르면 반영하지 않고 멈춥니다" });
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

function dashStdRead(L, st) { // 1단계의 「구성 읽기」 · 「구성 불러오기」(안 해도 됨 — ② §2·§3): 읽기 = 에이전트 행동 config_read(divRead) · 불러오기 = 「작업 내용」 의 「프로젝트 구성 불러오기」 와 같은 목록 · 함수(divSourceFill · divSourceLoad)
  const W = agw(), confirmed = !!st.facts.confirmed, off = dv.busy ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : "";
  L.steps.read = { state: W.readTried ? "done" : confirmed ? "" : "ready", acts: [], // 읽어 봤으면 끝남 + 읽은 값 한 줄 · 확정했으면 상태 없이 · 그 밖은 할 수 있음
    text: W.readTried ? W.readText || "이 문서에서 읽어 봤습니다" : confirmed ? "" : "문서(빈 사업계획서 포함)에 적힌 단계 · 차년도 · 기관을 읽어 입력 칸에 채웁니다 — 확정은 「프로젝트 구성 확정」 에서 합니다" };
  L.steps.read.acts.push(dashBtn("구성 읽기", () => dashExec("구성 읽기", async () => { const r = await agwExec("config_read"); W.form = null; return r; }), { // 폼이 열려 있으면 읽은 값으로 다시 채운다
    primary: !confirmed && !st.facts.config && !W.readTried && !DASH.form, disabled: !!off, focus: "act:config_read",
    title: off || "문서에 적힌 단계 · 차년도 · 기관을 읽어 입력 값으로 가져옵니다 — 문서와 확정은 그대로(확정은 「프로젝트 구성 확정」)" }));
  const v = dv.view, from = dv.preset && dv.preset.from;
  L.steps.load = { state: "", text: from ? `불러온 곳: ${from} — 확인한 뒤 「프로젝트 구성 확정」 에서 확정합니다` : "", acts: [] };
  if (!v) return;
  if ((dv.projects === undefined || !dv.projectsAt) && DASH.projTried !== dashKey()) { DASH.projTried = dashKey(); divProjectsLoad(); } // 다른 프로젝트 목록 — 늦게 오면 다음 그리기에 든다
  const sel = el("select", "dash-load-sel");
  sel.setAttribute("aria-label", "프로젝트 구성 불러오기 — 이 프로젝트 확정본 · 문서에서 추출 · 다른 프로젝트 · 저장한 프로젝트 구성");
  sel.dataset.dashFocus = "act:loadSel";
  divSourceFill(sel, v);
  if (DASH.loadKey && [...sel.options].some((o) => o.value === DASH.loadKey)) sel.value = DASH.loadKey; else DASH.loadKey = "";
  const go = dashBtn("불러오기", () => { const key = sel.value; if (key) dashExec("구성 불러오기", () => dashStdLoad(key)); }, { disabled: !sel.value || !!off, focus: "act:load",
    title: off || "고른 곳의 프로젝트 구성(단계 · 차년도 · 기관)을 입력 칸에 채웁니다 — 문서와 확정은 그대로, 확인한 뒤 「프로젝트 구성 확정」 에서 확정합니다" });
  sel.onchange = () => { DASH.loadKey = sel.value; go.disabled = !sel.value || !!off; };
  L.steps.load.acts.push(sel, go);
}

async function dashStdLoad(key) { // 「불러오기」 → 입력 칸만(문서 · 확정은 그대로 — 묻지 않는다). 값이 바뀌었으면 끝 글, 아니면 남기지 않음(「파일 올려 추출…」 은 파일 고르기 창이 따로 — 그 끝은 알림 글)
  const before = dv.values ? divCanon(divValues()) : "";
  await divSourceLoad(key);
  agw().form = null; // 폼이 열려 있으면 불러온 값으로
  return dv.values && divCanon(divValues()) !== before ? { ok: true, text: `입력 칸을 채웠습니다(아직 확정 전) — ${divValuesText(divValues())} · 「프로젝트 구성 확정」 에서 확인해 확정합니다` } : null;
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
  L.runs.heads = dashBtn("한 번에 진행", () => dashExec("2단계 헤딩 추출 — 한 번에 진행", () => headsRunAll()), { disabled: !!noH, focus: "run:heads",
    title: noH || "헤딩 추출 탭의 「전체 실행」 — 남은 LLM 판정(헤딩 · 템플릿 — 표 판정(LLM)도 같이 돎 → 서식 정리 계획) → 조정(모두 반영)까지 차례로 합니다. 유료 LLM · 문서가 바뀜(반영마다 실행 취소 한 번)" });
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
    title: no || `이어서 한 번에(누르면 바로 시작) — 앞 묶음이 끝나지 않으면 뒤 묶음은 시작하지 않습니다\n${rest.map((g) => `· ${DASH_STD_DOES[g.id] || `${g.no} ${g.name}`}`).join("\n")}` }));
  if (no) M.top.push(el("span", "dash-top-why", no)); // 꺼진 까닭을 글로(단추 title 만으로는 안 보인다)
}

// 묶음마다 할 일 — 「이어서 한 번에」 단추의 풍선 도움말(전에는 확인 창의 글)
const DASH_STD_DOES = { config: "1단계 프로젝트 구성 — 변경 계획 → 적용(문서가 바뀜 · 실행 취소 한 번). 계획 오류 · 미해결 자리가 있거나 기관의 차례가 마지막 반영과 다르면 적용하지 않고 멈춥니다.",
    heads: "2단계 헤딩 추출 — 전체 실행: 헤딩 LLM 판정(표 판정(LLM)도 같이) → 서식 정리 계획 → 조정 모두 반영(유료 LLM · 몇 분 · 문서가 바뀜 · 반영마다 실행 취소 한 번). 헤딩 판정에 미판정이 있으면 반영하지 않고 멈춥니다.",
    tables: "3단계 표 — 남은 표 판정(LLM)(유료 · 수 분 · 문서는 안 바뀜)." };
// 「이어서 한 번에」 — 누르면 바로(확인 창 없음 — 2026-11-18) 묶음마다 그 묶음의 실행을 차례로(멈추는 검사 · LLM 연결 확인은 그 함수 그대로): 1단계 divRunAll → 2단계 headsRunAll → 3단계(표 판정이 남았으면) headsPickRun(["l3"]).
// 앞 묶음이 끝나지 않으면(멈춤 · 실패 · 계획 오류 · 미해결 — 1단계가 「적용」 까지 안 감) 뒤 묶음을 시작하지 않고, 머리 아래 끝 글에 한 것 · 멈춘 까닭 · 남은 것(② §4 · spec_작업에이전트 ② §7 ⓐ)
async function dashStdChain(rest, label) {
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 묶음마다 할 일(does)을 적은 확인 창: design.md §18 「확인 창」). 묶음마다 할 일(DASH_STD_DOES)은 단추의 풍선 도움말(dashStdTop)
  await dashExec(label, async () => {
    const id = state.id, epoch = state.epoch, here = () => state.id === id && state.epoch === epoch, did = [], gone = "다른 문서를 열어 멈췄습니다";
    const stop = (i, why) => ({ ok: false, text: `멈춤 — ${rest[i].no} ${rest[i].name}: ${why}${did.length ? ` · 한 것: ${did.join(" / ")}` : ""}`
      + `${i + 1 < rest.length ? ` · 시작하지 않은 것: ${rest.slice(i + 1).map((g) => `${g.no} ${g.name}`).join(" · ")}` : ""}` });
    for (const [i, g] of rest.entries()) {
      if (!here()) return stop(i, gone);
      if (DASH.busy) { DASH.busy.label = `${label} — ${g.no} ${g.name}`; dashDraw(true); }
      if (g.id === "config") {
        const msg0 = dv.msg; // divRunAll 이 시작하지 못하고 돌아오면(도는 일 · 잠김 · 까닭) dv.msg 는 그대로다 — 앞서 남은 옛 멈춤 글을 이번 까닭으로 보이지 않게(검토 11-18)
        await divRunAll({ asked: true });
        if (!here()) return stop(i, gone);
        if (!agwFitApplied().applied) return stop(i, `${dv.msg && dv.msg !== msg0 && dv.msg.kind === "halt" ? dv.msg.text.replace(/^멈춤 — /, "") : "「적용」 까지 가지 않았습니다(알림 글 참고)"} — 「작업 내용」 의 ① 변경 계획 보기 › ② 반영에서 보정합니다`);
        did.push(`${g.no} 적용함`);
      } else if (g.id === "heads") {
        const r = await headsRunAll({ asked: true });
        const v = await agwStdFresh();
        if (!here()) return stop(i, gone);
        if (r && !r.ok) return stop(i, r.text);
        const S = v ? agwStdSteps(v) : null;
        if (!S) return stop(i, `${r ? `${r.text} — ` : ""}분석 상태를 읽지 못해 끝났는지 셀 수 없습니다(헤딩 추출 탭의 진행 줄을 보세요)`);
        // 전체 실행이 「끝까지 감」 이어도 2단계가 끝난 것은 아니다 — 서식 정리 계획을 일부 못 받았거나 같은 것이 남으면 그 까닭 없이 돌아온다(검토 11-18). 단계의 셈으로 다시 본다
        const left = ["heads", "headsLlm", "adjust"].find((k) => S.steps[k].state !== "done");
        if (left) return stop(i, `${r ? "" : "시작하지 못했습니다 — "}${AGW_STD_NAMES[left]}: ${S.steps[left].text || "남음"}${r ? "" : "(알림 글 참고)"}`);
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
        if (!r.ok) return stop(i, r.text);
        did.push(`${g.no} ${r.text}`);
      } else return stop(i, "모르는 묶음입니다 — 페이지를 새로 고치세요(서버의 등록부와 화면이 다른 판)"); // 모르는 묶음을 조용히 「끝남」 으로 넘기지 않는다
    }
    return { ok: true, text: `끝남 — ${did.join(" / ")}` };
  });
}

function dashRelayLive(M) { // 이관 — 「작업 내용」 의 단계(taskSteps)와 묶음(TASK_STAGES)
  const L = { steps: {}, runs: {} };
  if (!taskSlots()) { M.notes.push({ text: "이 작업에는 이관의 첨부 파일 칸이 없습니다" }); return L; }
  let open = true;
  const steps = taskSteps().map((s) => { // 셈은 app.js taskStepsCalc 와 같다 — 그쪽의 taskStepsLast 를 건드리지 않으려고 따로 센다(단추도 새로 받은 것)
    const st = s.soon ? "soon" : s.done ? "done" : open ? "now" : s.early ? "ready" : "todo";
    if (!s.done && !s.soon) open = false;
    return { ...s, st };
  });
  const active = taskRun ? taskRun.key : (steps.find((s) => s.busy) || {}).key;
  for (const s of steps) {
    const acts = s.st === "now" || s.st === "ready" || (s.keep && s.st === "done") ? s.acts : []; // 단추를 보이는 때 — taskStepsEl 과 같다
    acts.forEach((b, i) => { b.dataset.dashFocus = `act:${s.key}:${i}`; });
    L.steps[s.key] = { state: active === s.key ? "run" : s.st, text: s.st === "todo" ? "" : dashHere(s.text), acts: [...acts] };
  }
  Object.assign(L.steps, { heads: { via: "link" }, llm: { via: "link" }, tableMap: { via: "plan" }, gaps: { via: "plan" } }); // 등록부의 세부 단계 — 「작업 내용」 은 ②·③ 줄의 단추로 함께 한다
  const files = steps.find((s) => s.key === "files");
  if (files && !files.done) L.steps.files.acts.push(dashBtn("「작업 내용」 의 칸 열기", () => showTab("Div"), { primary: true, title: "첨부 파일 칸에서 사업계획서 · 연차보고서를 고르거나 올립니다", focus: "act:files" }));
  const config = steps.find((s) => s.key === "config");
  if (config && !config.done && files && files.done) L.steps.config.acts.push(dashBtn("입력 칸 열기", () => showTab("Div"), { title: "「작업 내용」 의 프로젝트 구성 입력 칸 · 불러오기 — 값을 고칠 때", focus: "act:configInput" }));
  const report = taskSlotDoc("report"), left = steps.some((s) => !s.done && !s.soon && s.key !== "files");
  if (report && report.id !== state.id && left) M.notes.push({ text: "이 문서는 원본 문서(사업계획서)입니다 — 이관은 연차보고서(목적 문서)에서 진행합니다", act: dashBtn(`연차보고서 「${report.name}」 열기`, () => dashOpen(report.id), { focus: "act:target" }) });
  const work = (g) => steps.filter((s) => g.keys.includes(s.key) && !s.soon && s.key !== "files"); // 묶음의 세는 단계(app.js taskStageWork 와 같다)
  TASK_STAGES.forEach((g, i) => { // 묶음 머리의 「한 번에 진행」 — 켜는 조건은 「작업 내용」 의 묶음 머리와 같다(taskStageSync1)
    const next = work(g).find((s) => !s.done), before = TASK_STAGES.slice(0, i).find((x) => work(x).some((s) => !s.done)), busy = steps.some((s) => g.keys.includes(s.key) && s.busy);
    const no = taskRun ? "다른 진행이 끝난 뒤 쓸 수 있습니다" : taskResetting ? "초기화가 끝난 뒤 쓸 수 있습니다" : busy ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다"
      : !(files && files.done) ? "두 칸(사업계획서 · 연차보고서)에 문서를 먼저 고르세요" : before ? `${before.no} 「${before.name}」 을 먼저 끝내세요` : !next ? "남은 단계가 없습니다" : "";
    L.runs[g.id] = dashBtn("한 번에 진행", () => taskRunAll(g.id), { disabled: !!no, focus: `run:${g.id}`, title: no || `이 묶음의 남은 단계를 차례로 한 번에 — ${g.does}. 사람 손이 필요한 곳에서는 멈춥니다` });
  });
  const plan0 = taskSlotDoc("plan");
  L.ends = {};
  for (const g of TASK_STAGES) { // 묶음의 마지막 「한 번에 진행」 의 끝 — 그 뒤 더 나아가지 않았을 때만(taskStageSync1 과 같은 조건)
    const end = taskRunEnds[g.id];
    if (end && !taskRun && report && end.report === report.id && plan0 && end.plan === plan0.id && end.done === work(g).filter((s) => s.done).length) L.ends[g.id] = { ok: !!end.ok, text: end.text };
  }
  const rest = TASK_STAGES.filter((g) => work(g).some((s) => !s.done)); // 이어서 한 번에(「작업 내용」 의 이어 진행 줄과 같은 범위 — 할 일이 남은 첫 묶음 → 끝 묶음)
  if (rest.length > 1 && files && files.done) {
    const label = `${rest[0].no.replace(/단계$/, "")}→${rest[rest.length - 1].no}`, busy = steps.some((s) => s.busy);
    M.top.push(dashBtn(`이어서 한 번에 ${label}`, () => taskRunAll(rest[0].id, rest[rest.length - 1].id), { disabled: !!taskRun || !!taskResetting || busy, focus: "run:chain",
      title: `${rest.map((g) => `${g.no} 「${g.name}」`).join(" → ")} 을 이어서 한 번에 — 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다` }));
  }
  return L;
}

function dashGatherLive(M) { // 취합 — 「작업 내용」 의 단계(gatherSteps)와 묶음(GT_STAGES). 3단계는 기관 문서마다 되풀이 — 등록부의 단계는 차례만, 상태 · 단추는 기관 문서 줄에
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
  if (L.steps.files && L.steps.files.state !== "done") L.steps.files.acts.push(dashBtn("「작업 내용」 의 칸 열기", () => showTab("Div"), { primary: true, title: "취합본 칸에서 사업계획서(취합본)를 고르거나 올립니다", focus: "act:files" }));
  if (L.steps.config && L.steps.config.state !== "done" && plan) L.steps.config.acts.push(dashBtn("입력 칸 열기", () => showTab("Div"), { title: "「작업 내용」 의 프로젝트 구성 입력 칸 · 불러오기 — 값을 고칠 때", focus: "act:configInput" }));
  const F = V && V.frame, hand = { state: "", text: "앱 밖의 일 — 배포 기준본을 내려받아 기관에 나눠 주고, 기관이 채워 돌려준 문서를 아래 「기관 문서」 로 올립니다", acts: [] };
  if (F) { const a = el("a", "btn sm", "기준본 내려받기"); a.href = gatherUrl("/frame/file"); a.setAttribute("download", ""); a.dataset.dashFocus = "act:handFile"; a.title = "고정해 둔 기준본 파일(hwpx) — 기관에 나눠 주는 파일" + (F.stale ? "(낡은 판)" : ""); hand.acts.push(a); }
  L.steps.hand = hand;
  for (const k of ["part", "heads", "link", "llm", "plan", "apply", "drop"]) L.steps[k] = { state: "each" };
  for (const s of steps.filter((x) => x.step === "part")) L.parts.push({ key: s.key, no: s.no, name: s.name, state: active === s.key || s.busy ? "run" : s.st, lines: lines(s), acts: actsOf(s) });
  const frameOk = !!(F && !F.stale);
  L.partsAdd = dashBtn("기관 문서 올리기…", () => gatherPickFiles((fs) => gatherUploadMany(fs)), { disabled: !plan || !frameOk || !!gatherRun || !!(Q && Q.busy), focus: "act:partsAdd",
    title: !plan ? "사업계획서(취합본)를 먼저 고르세요" : !frameOk ? "배포 기준본을 먼저 만드세요 — 기관 문서는 기준본과 견줍니다" : "기관이 채워 돌려준 문서(hwp · hwpx)를 올려 이 취합에 넣습니다 — 반영할 기관은 줄마다 「작업 내용」 의 기관 문서 줄에서 고릅니다" });
  if (plan && plan.id !== state.id && steps.some((s) => !s.done && s.step !== "files")) M.notes.push({ text: "이 문서는 기관 문서(원본)입니다 — 취합은 취합본(목적 문서)에서 진행합니다", act: dashBtn(`취합본 「${plan.name}」 열기`, () => dashOpen(plan.id), { focus: "act:target" }) });
  const lost = Q ? Q.items.filter((it) => !it.pid && it.err && !it.skip).length : 0; // 간단 모드가 멈췄거나 못 올린 문서가 남았다 — 에이전트의 「간단 모드 이어서」 와 같은 행동
  if (Q && !Q.busy && Q.end && !Q.uploadOnly && (!Q.end.ok || lost)) {
    const does = `멈춘 곳부터 남은 일을 끝까지 이어서 합니다${lost ? ` — 못 올린 문서 ${lost}개를 다시 올리고` : ""}(앞서 넣은 것은 다시 넣지 않음 · 기관 문서마다 편집 한 번${Q.llm ? " · 유료 LLM 검토 포함" : ""})`;
    M.notes.push({ text: `간단 모드 ${Q.end.ok ? "끝남" : "멈춤"} — ${Q.end.text}`, warn: !Q.end.ok, act: dashBtn("간단 모드 이어서", () => dashExec("간단 모드 이어서", () => agwExec("quick:resume")), { title: `${does} — 취합본이 바뀝니다(기관 문서마다 실행 취소 한 번)`, focus: "act:quick" }) }); // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」)
  }
  const E = typeof gatherRunLast !== "undefined" ? gatherRunLast : null; // 마지막 「한 번에 진행」 의 끝 — 그 뒤 더 나아가지 않았을 때만(gather.js 상태 줄과 같은 조건)
  if (E && !gatherRun && plan && E.plan === plan.id && E.done === steps.filter((s) => s.stage === E.stage && s.step !== "files" && s.done).length) L.ends = { [E.stage]: { ok: !!E.ok, text: E.text } };
  GT_STAGES.forEach((g, i) => { // 묶음 머리의 「한 번에 진행」 — gatherRunAll(확인 창 없이)
    const left = (x) => steps.filter((s) => s.stage === x.id && !s.done && s.step !== "files"), before = GT_STAGES.slice(0, i).find((x) => left(x).length);
    const no = gatherRun ? "다른 묶음이 진행 중입니다" : Q && Q.busy ? "간단 모드가 도는 중입니다" : !plan ? "사업계획서(취합본)를 먼저 고르세요" : before ? `${before.no} 「${before.name}」 을 먼저 끝내세요` : !left(g).length ? "남은 단계가 없습니다" : "";
    L.runs[g.id] = dashBtn("한 번에 진행", () => gatherRunAll(g.id), { disabled: !!no, focus: `run:${g.id}`, title: no || `이 묶음의 남은 단계를 차례로 한 번에 — ${g.does}. 사람 손이 필요한 곳에서는 멈춥니다` });
  });
  return L;
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
  L.steps.use = { state: "", text: "", acts: [dashBtn("서식 관리자 열기", () => styleLibOpen(), { title: "저장한 서식을 다른 문서에 적용합니다(그 TASK 의 원본 문서에는 적용하지 않음)", focus: "act:styleUse" })] };
  const busy = on && !!(S.auto || S.busy || S.llm || S.loading);
  L.runs.copy = on ? dashBtn("한 번에 진행", () => styleSaveAuto(), { disabled: busy || !!S.err, focus: "run:copy", title: S.err ? "후보를 찾지 못했습니다 — 열의 글을 보세요" : "② LLM 검토 → ③ 저장 → ④ PDF 검증을 잇습니다(문서는 바뀌지 않음) — 의심 · 고침이 없는 추천만 저장하고 나머지는 남깁니다" })
    : openBtn("「서식 복사」 열 열기", false);
  return L;
}

function dashEditLive() { // 문서 일반 편집 — 단계의 끝을 세지 않는다(요청 → 제안 → 반영의 되풀이). 단추는 그 일을 하는 곳을 연다
  const agent = (focus) => (toolShown("Agent") ? [dashBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "패널 「에이전트」 — 자료를 주고 글로 요청하면 제안이 나옵니다", focus })] : []);
  return { runs: {}, steps: { open: { state: "done", text: "" }, material: { state: "", acts: agent("act:material") }, turn: { state: "", acts: agent("act:turn") }, check: { state: "", text: "제안마다 저절로 돕니다" },
    apply: { state: "", text: "제안 카드의 「문서에 반영」 을 누른 제안만 들어갑니다", acts: agent("act:apply") },
    styleSave: { state: "", acts: [dashBtn("서식 관리자 열기", () => styleLibOpen(), { title: "반영한 표나 이 문서의 서식을 저장해 다시 씁니다", focus: "act:styleSave" })] },
    tables: { state: "", text: "표 손잡이(표 오른쪽 여백)의 메뉴에서 엽니다" } } };
}

async function dashLive(job, M) {
  if (job === "plan_fit") return dashStdLive(M);
  if (agwFit(job)) return dashFitLive(M);
  if (job === "plan_to_report") return dashRelayLive(M);
  if (job === "plan_merge") return dashGatherLive(M);
  if (job === "style_copy") return dashStyleLive();
  if (job === "doc_edit") return dashEditLive();
  return { steps: {}, runs: {} };
}

async function dashModel() {
  const job = agwJob(), cat = (typeof TASK_CATALOG === "object" && TASK_CATALOG[job]) || {}, reg = DASH.reg && DASH.reg.tasks.find((t) => t.job === job);
  const M = { job, name: cat.name || job || "TASK 없음", reg, notes: [], top: [], groups: [], R: agwRunning() };
  if (!reg || !reg.stages.length) return M;
  const L = await dashLive(job, M), meta = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META;
  let i = 0;
  M.groups = reg.stages.map((g, gi) => ({
    id: g.id, label: g.meta && meta[g.meta] ? { no: meta[g.meta].no, name: meta[g.meta].name } : { no: g.no || String(gi + 1), name: g.name }, does: g.does, run: L.runs[g.id] || null, end: (L.ends || {})[g.id] || null, parts: g.id === "map" && L.parts ? { rows: L.parts, add: L.partsAdd } : null, // 번호 = 등록부의 no(양식 표준화 「1단계」) · 없으면 차례
    nodes: g.steps.map((s) => {
      const live = L.steps[s.key] || {}, via = live.via ? reg.stages.flatMap((x) => x.steps).find((x) => x.key === live.via) : null;
      return { ...s, idx: ++i, state: s.soon ? "soon" : live.state || "", text: live.text || "", lines: live.lines || [], acts: live.acts || [], via: via ? { key: via.key, name: via.name } : null };
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

function dashDetailEl(n, id) {
  const d = el("div", "dash-detail");
  d.id = id;
  if (n.via) {
    const p = el("p", "dash-text muted", `이 단계는 「${n.via.name}」 의 단추로 함께 합니다.`), go = dashBtn("그 단계로", () => { DASH.open = n.via.key; dashDraw(true); }, { focus: `via:${n.key}` });
    d.append(p, el("div", "dash-acts")); d.lastChild.append(go);
  }
  if (n.state === "each") d.append(el("p", "dash-text muted", "기관 문서마다 되풀이합니다 — 아래 「기관 문서」 줄에서 문서마다 진행합니다."));
  if (n.text) d.append(el("p", "dash-text", n.text));
  for (const [name, text] of n.lines) { const p = el("p", "dash-text"); if (name) p.append(el("span", "dash-sub", name), " "); p.append(text); d.append(p); }
  const need = (n.cond || []).find((c) => c.key === "need");
  if (!n.text && !n.lines.length && n.state === "todo" && need) { const p = el("p", "dash-text muted"); p.append(el("span", "dash-sub", "하려면"), " ", need.text); d.append(p); }
  if (n.key === "values" && DASH.form && agwFit(agwJob())) { // 양식 표준화 · 양식 맞추기의 값 입력 — 에이전트 질문 카드와 같은 폼(doc_agent_work.js agwConfigForm)
    d.append(agwConfigForm({ id: "dash" }, { draw: () => dashDraw(true), ok: (x) => { DASH.form = false; dashExec("프로젝트 구성 확정", () => agwExec("config_set", x)); }, close: () => { DASH.form = false; dashDraw(true); } }));
  }
  if (n.acts.length) { const acts = el("div", "dash-acts"); acts.append(...n.acts); d.append(acts); }
  const off = n.acts.find((b) => b.tagName === "BUTTON" && b.disabled && b.title); // 꺼진 단추의 까닭을 글로(title 만으로는 안 보인다 — 2026-11-18 사용자: 「모두 반영」 이 왜 꺼졌는지 안 보였다 · dashStdTop 의 .dash-top-why 와 같은 생각)
  if (off) d.append(el("p", "dash-text dash-why", `「${off.textContent.trim()}」 — ${off.title}`));
  const more = el("details", "dash-more"), dl = el("dl", "dash-cond");
  more.append(el("summary", null, "하는 일 · 조건"));
  dl.append(el("dt", null, "하는 일"), el("dd", null, n.does));
  if (n.out) dl.append(el("dt", null, "나오는 것"), el("dd", null, n.out));
  for (const c of n.cond || []) dl.append(el("dt", null, c.name), el("dd", null, c.text));
  more.append(dl);
  d.append(more);
  return d;
}

function dashNodeEl(n, gid, openKey) {
  const li = el("li", "dash-node" + (n.optional ? " opt" : "") + (n.soon ? " soon" : "") + (n.key === openKey ? " open" : "")), open = n.key === openKey, id = `dashD-${gid}-${n.key}`, head = el("button", "dash-node-head");
  li.dataset.key = n.key;
  li.dataset.state = n.state || "none";
  head.type = "button";
  head.dataset.dashFocus = `node:${n.key}`;
  head.setAttribute("aria-expanded", String(open));
  if (open) head.setAttribute("aria-controls", id);
  if (n.state === "now" || n.state === "run") head.setAttribute("aria-current", "step");
  const main = el("span", "dash-node-main"), st = DASH_ST[n.state] || "";
  main.append(el("b", null, n.name), dashTags(n));
  head.append(el("span", "dash-no", String(n.idx).padStart(2, "0")), main);
  if (st) head.append(el("span", "dash-st", n.state === "done" ? `✓ ${st}` : st));
  head.title = `${n.name}${st ? ` — ${st}` : ""}${n.text ? `\n${n.text}` : ""}`;
  head.onclick = () => { DASH.open = open ? "" : n.key; dashDraw(true); };
  li.append(head);
  if (open) li.append(dashDetailEl(n, id));
  return li;
}

function dashPartsEl(P) { // 취합 3단계 — 기관 문서마다 한 줄(들어온 차례): 이름 · 상태 · 글 · 단추(「작업 내용」 의 기관 문서 줄과 같은 단추)
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
  if (!R && !B) return null;
  const box = el("div", "dash-live"), text = el("span", "dash-live-text", R ? agwLiveText(R) : `${B.label} — 하는 중 · ${fmtDur((Date.now() - B.t0) / 1000)}`);
  text.setAttribute("role", "status");
  box.append(el("span", "ag-spin"), el("b", null, R ? R.label : B.label), text);
  if (R && R.stop) box.append(dashBtn(R.stopping ? "멈추는 중…" : "멈춤", () => { R.stop(); dashDraw(true); }, { disabled: R.stopping, title: "지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다", focus: "stop" }));
  return box;
}

async function dashPick(job) { // TASK 고르기 — 「작업 내용」 의 TASK 칸과 같은 길(project_workspace.js projectTaskPick → taskSet) · 고른 뒤 그 자리에서 단계 흐름
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
  wf.href = "/workflow#overview"; wf.target = "_blank"; wf.rel = "noopener"; wf.title = "워크플로우 페이지에서 TASK 마다의 과정 보기(새 탭)";
  title.append(el("b", null, "TASK 고르기"), hHelp("대시보드 도움말", DASH_PICK_HELP), wf);
  const next = el("p", "dash-next", "이 문서에는 TASK 가 없습니다 — TASK 를 고르면 단계 흐름이 보입니다");
  next.setAttribute("role", "status");
  head.append(title, next);
  root.append(head);
  if (DASH.regErr && !DASH.reg) { root.append(el("p", "dash-note warn", `워크플로우를 읽지 못했습니다: ${DASH.regErr}`), dashBtn("다시 읽기", () => { DASH.regErr = ""; dashShow(); })); return root; }
  const fmt = state.format || "hwpx", ul = el("ul", "dash-picks");
  ul.setAttribute("aria-label", "이 문서로 할 수 있는 TASK");
  for (const [job, cat] of Object.entries(TASK_CATALOG)) {
    if (cat.soon || !taskAcceptOf(job).includes(fmt)) continue;
    const reg = DASH.reg && DASH.reg.tasks.find((t) => t.job === job), li = el("li", "dash-pick"), top = el("div", "dash-pick-top");
    li.dataset.job = job;
    top.append(el("b", null, cat.name));
    if (reg && reg.stages.length) top.append(el("span", "dash-gcount", `단계 ${reg.stages.reduce((s, g) => s + g.steps.length, 0)}개`));
    li.append(top, el("p", "dash-text", cat.desc || ""));
    if (reg && reg.stages.length) li.append(el("p", "dash-text muted", reg.stages.map((g) => (g.meta && meta[g.meta] ? meta[g.meta].name : g.name)).join(" › ")));
    const acts = el("div", "dash-acts");
    acts.append(dashBtn("이 TASK 로", () => dashPick(job), { title: `이 문서의 TASK 를 「${cat.name}」 로 적고 단계 흐름을 봅니다(문서는 바뀌지 않습니다)`, focus: `pick:${job}` }));
    li.append(acts);
    ul.append(li);
  }
  if (!ul.children.length) ul.append(el("li", "dash-pick muted", `이 문서 형식(${fmt})으로 할 수 있는 TASK 가 없습니다`));
  root.append(ul);
  return root;
}

function dashEl(M) {
  if (!dashHasTask(M.job)) return dashPickEl();
  const root = el("section", "dash"), head = el("header", "dash-head"), title = el("div", "dash-title");
  root.setAttribute("aria-label", "대시보드");
  const nodes = M.groups.flatMap((g) => g.nodes), counted = nodes.filter(dashCounted), done = counted.filter((n) => n.state === "done").length;
  const wf = el("a", "dash-wf", "워크플로우 ↗");
  wf.href = `/workflow#${encodeURIComponent(M.job)}`; wf.target = "_blank"; wf.rel = "noopener"; wf.title = "워크플로우 페이지에서 이 TASK 의 과정 보기(새 탭)";
  title.append(el("b", null, M.name), ...(counted.length ? [el("span", "dash-count", `끝남 ${done}/${counted.length}`)] : []), hHelp("대시보드 도움말", DASH_HELP), wf);
  const run = nodes.find((n) => n.state === "run"), now = nodes.find((n) => n.state === "now"), next = el("p", "dash-next");
  next.setAttribute("role", "status");
  next.textContent = M.R ? `진행 중 — ${M.R.label}` : run ? `진행 중 — ${String(run.idx).padStart(2, "0")} ${run.name}` : now ? `다음: ${String(now.idx).padStart(2, "0")} ${now.name}`
    : counted.length && done === counted.length ? "모두 끝남" : "";
  head.append(title);
  if (next.textContent) head.append(next);
  root.append(head);
  const live = dashLiveEl(M);
  if (live) root.append(live);
  if (DASH.last) { const p = el("p", "dash-last" + (DASH.last.ok ? "" : " halt")); p.append(el("b", null, DASH.last.label), ` — ${DASH.last.text}`); root.append(p); }
  for (const n of M.notes) { const p = el("div", "dash-note" + (n.warn ? " warn" : "")); p.append(el("span", null, n.text)); if (n.act) p.append(n.act); root.append(p); }
  if (M.top.length) { const top = el("div", "dash-top"); top.append(...M.top); root.append(top); }
  if (DASH.regErr && !M.reg) { root.append(el("p", "dash-note warn", `워크플로우를 읽지 못했습니다: ${DASH.regErr}`), dashBtn("다시 읽기", () => { DASH.regErr = ""; dashShow(); })); return root; }
  if (!M.reg) { root.append(el("p", "dash-text muted", M.job ? "단계 흐름을 읽는 중…" : "TASK 가 적히지 않은 문서입니다 — 단계 흐름이 없습니다")); return root; }
  if (!M.groups.length) { root.append(el("p", "dash-text muted", M.reg.soon ? "준비 중인 TASK 입니다 — 아직 등록된 단계가 없습니다" : "등록된 단계가 없습니다")); return root; }
  const openKey = DASH.open === null ? (run || now || {}).key || "" : DASH.open, ol = el("ol", "dash-groups");
  ol.setAttribute("aria-label", "TASK 단계 묶음과 단계");
  for (const g of M.groups) {
    const li = el("li", "dash-group"), gh = el("div", "dash-ghead"), cnt = g.nodes.filter(dashCounted), flow = el("ol", "dash-flow");
    li.dataset.group = g.id;
    gh.append(el("span", "dash-gno", g.label.no), el("b", "dash-gname", g.label.name), el("span", "dash-gcount", cnt.length ? `${cnt.filter((n) => n.state === "done").length}/${cnt.length}` : `${g.nodes.length}개 단계`));
    if (g.run) gh.append(g.run);
    gh.title = g.does || "";
    flow.setAttribute("aria-label", `${g.label.name}의 단계`);
    for (const n of g.nodes) flow.append(dashNodeEl(n, g.id, openKey));
    li.append(gh);
    if (g.end) li.append(el("p", "dash-gend" + (g.end.ok ? "" : " halt"), `${g.end.ok ? "끝남" : "멈춤"} — ${g.end.text}`)); // 「한 번에 진행」 의 끝(「작업 내용」 의 묶음 상태 줄과 같은 글)
    li.append(flow);
    if (g.parts) li.append(dashPartsEl(g.parts));
    ol.append(li);
  }
  root.append(ol);
  return root;
}

function dashSig(M) { // 다시 그릴지 — 상태 · 글 · 단추(글 · 켜짐 · 강조)가 같으면 도는 글만 바꾼다(1초마다 · 초점 유지)
  const b = (x) => (x ? `${x.textContent}|${x.disabled ? 1 : 0}|${x.className}|${x.title}` : "");
  // busy 이름 — 「이어서 한 번에」 가 묶음을 넘어갈 때 바뀐다
  return JSON.stringify([M.job, !!M.reg, !!DASH.reg, state.format, DASH.regErr, DASH.open, DASH.form, DASH.busy ? DASH.busy.label : "", DASH.last, M.R ? `${M.R.kind}|${M.R.label}|${M.R.stopping}|${!!M.R.stop}` : "",
    M.notes.map((n) => [n.text, b(n.act)]), M.top.map(b),
    M.groups.map((g) => [b(g.run), g.end, g.parts ? [b(g.parts.add), g.parts.rows.map((r) => [r.state, r.lines, r.acts.map(b)])] : 0, g.nodes.map((n) => [n.state, n.text, n.lines, n.acts.map(b)])])]);
}

async function dashDraw(force = false) {
  const box = $("dashBox");
  if (!box || !state.id) return;
  const seq = ++DASH.seq;
  let M;
  try { M = await dashModel(); } catch (e) { console.error(e); M = { job: agwJob(), name: "대시보드", reg: null, notes: [{ text: `상태를 읽지 못했습니다: ${e.message}`, warn: true }], top: [], groups: [], R: null }; }
  if (seq !== DASH.seq) return;
  const nowKey = (M.groups.flatMap((g) => g.nodes).find((n) => !n.optional && (n.state === "run" || n.state === "now")) || {}).key || ""; // 안 해도 되는 단계가 도는 것은 차례가 아니다 — 그 카드를 펴고 돌린 LLM 검토가 끝나도 카드가 그대로(결과 단추가 보이게)
  if (nowKey !== DASH.nowKey) { if (DASH.nowKey) DASH.open = null; DASH.nowKey = nowKey; } // 차례가 나아가면 펼친 카드도 새 「지금」 으로(사람이 편 카드는 차례가 그대로인 동안만)
  const sig = dashSig(M);
  if (!force && sig === DASH.sig) { // 그대로 — 도는 글만
    const t = box.querySelector(".dash-live-text"), s = M.R ? agwLiveText(M.R) : DASH.busy ? `${DASH.busy.label} — 하는 중 · ${fmtDur((Date.now() - DASH.busy.t0) / 1000)}` : "";
    if (t && s && t.textContent !== s) t.textContent = s;
    return;
  }
  DASH.sig = sig;
  const a = document.activeElement, focus = a && box.contains(a) ? a.dataset.dashFocus || "" : "", ring = !!(focus && a.matches(":focus-visible")); // 키보드로 온 초점이었나
  box.replaceChildren(dashEl(M));
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
