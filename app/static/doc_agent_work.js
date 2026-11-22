"use strict";
// 작업 진행 에이전트의 화면(spec_작업에이전트 ② §1·§3·§5) — 에이전트 보기(doc_agent.js #paneAgent)에 **진행 턴**을 더하고, 첫 화면 오른쪽에 같은 대화창(#homeAgent)을 둔다.
// 사용자 2026-11-15 "첫 화면 우측에 에이전트 대화할 수 있는 대화창 … 파일 올리면 작업절차를 확인하고 직접 작업을 진행하고 필요한 경우 질문형식으로" ·
//   "task 를 클릭하고 문서를 로드 했을 때 사전준비가 필요한 부분이나 작업진행 사항을 에이전트가 설명하고 진행 … 다음 스테이지도 에이전트가 제안하고 실행".
// 나눔: 에이전트(서버 app/work_guide.py — LLM 또는 스크립트 답)는 **설명하고 고른다**. 단계의 상태(steps)와 지금 할 수 있는 행동(actions)은 이 파일이 화면의 기존 상태에서 계산해 보내고(agwStatus),
//   고른 행동도 이 파일이 기존 함수로 실행한다(agwExec — divPlan · divApply · taskRunAll · gatherRunStage · headsPickRun · tpbApply …: 새 실행 길을 만들지 않는다).
//   양식 표준화(plan_fit)의 2 · 3단계(헤딩 추출 · 표) 상태는 agwStdSteps — 대시보드(dashboard.js)와 같이 쓴다(spec_양식표준화 ② §2·§5).
// 한 번의 연쇄: 턴(POST …/agent/guide) → 행동이 있으면 ⓐ 문서가 안 바뀌고 무료면 바로 실행 → 결과 턴 ⓑ 문서가 바뀌거나 유료면 실행 카드의 「진행」 을 기다림. 질문 카드는 답을 기다린다. 6턴까지.
// 어느 쪽이든 실행 직전에 상태를 다시 세어 행동이 달라졌으면(key · 글 · 저절로 하던 것이 유료 · 문서 바뀜이 됨) 실행하지 않고 다시 묻는다(agentWorkRun).
// 질문 카드에서 고른 행동도 같다 — 유료이거나 문서를 바꾸는 행동이면 고른 것을 승인으로 보지 않고 실행 카드로 묻는다(선택지에는 유료 꼬리표 · 부를 문서 · 문서 바뀜이 안 보인다: agentWorkAnswer).
// doc_agent.js 다음에 읽힌다(AGENT · agentUrl · agentErr · agentDraw* · agentSend · agentTurnOf · agentWhen · agentIcon). app.js: state · dv · div* · task* · showTab · toolShown · api · el · hBtn · toast · nf · H_JSON · homeTaskStart · heads · headsRender · headsPoll.
// 부를 때 찾는 것(양식 표준화 2 · 3단계): doc_status.js(dsState · dsDraw · dsRunning) · heads_run_all.js(hraLeft · hraUnseen · headsAllRunning) · heads_run_pick.js(headsPickRun · headsPickRunning) · tpl_plan_bar.js(tpbApply).

const AGW_STATE = { done: "끝남", now: "지금", todo: "남음", soon: "준비 중" };
const AGW_CHAIN_MAX = 6;
const AGW_EVENT = { start: "작업 절차를 확인하는 중", say: "글을 읽는 중", answer: "답을 읽는 중", result: "다음 단계를 정하는 중" };
let agwCarry = null; // 첫 화면 대화창에서 TASK 를 시작했을 때 넘겨 줄 말 {job, talk[{who, text}]} — 그 작업의 시작 턴이 가져간다
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { agentGuide: "에이전트 작업 진행" }); // 「기록」 탭의 이름

const agw = () => (AGENT.work || (AGENT.work = { chain: 0, running: null, readTried: false, form: null })); // 문서마다(AGENT 와 함께 새로) — running = 도는 행동 {turn, name, t0, timer}
const agwJob = () => (state.task && state.task.job) || "";
const agwFit = (job) => job === "plan_fit" || job === "report_fit";
// 진행 에이전트가 맡는 TASK — 단계가 있고 화면이 상태·행동을 계산할 수 있는 것(양식 표준화 · 양식 맞추기 · 이관 · 취합). 일반 편집은 단계가 없고, 서식 복사는 2열 「서식 복사」 가 그 진행을 맡는다(④)
// 목록에 없는 조립한 워크플로우(지워짐 · 저장 파일을 못 읽음 — task_catalog.js taskLostWhy)는 맡지 않는다(HEAD 처럼 — 입력 칸의 글 · 표 요청은 바로 편집 에이전트로: 진행 에이전트가 받으면 할 행동도 넘길 행동도 없다).
// 그 까닭 한 줄은 작업 개요 · 대시보드가 보이고, 맡던 때 낸 카드를 누르면 agwStatusOf 가 행동 없이 그 까닭으로 실행하지 않는다
const agwGuided = (job = agwJob()) => agwFit(job) || taskIsRelay(job) || taskIsGather(job) || taskIsSingle(job); // taskIsGather = 취합형(붙박이 취합 · 취합형으로 조립한 것) // taskIsRelay = 이관형(붙박이 이관 · 화면에서 조립한 TASK — task_catalog.js) // taskIsSingle = 문서 하나로 조립한 것(서버가 센 상태로 — agwSingleStatus)
const agwAsk = (a) => !!a && (a.change === "doc" || !!a.paid || a.name === "open:target"); // 카드로 물어야 하는 행동(문서가 바뀜 · 유료 LLM · 다른 문서로 옮겨 감 — 원본 문서를 보려고 연 사람을 저절로 목적 문서로 데려가지 않는다)

// ---------------------------------------------------------------- 지금 도는 「한 번에 진행」 — 누가 시작했든(에이전트 카드 · 「작업 개요」 의 단추 · 첫 화면 간단 모드) 에이전트 보기가 한 꼴로 본다(spec ② §7)
// 실행은 TASK 마다 제 상태에 있다(이관 taskRun · 취합 gatherRun · 간단 모드 gqRun · 양식 표준화 · 양식 맞추기 dv.auto · 서식 복사 STYLE.save.auto) — 여기서는 **읽기만** 한다(새 실행 길 · 새 상태를 만들지 않는다).
// 간단 모드(gqRun)와 그 안에서 도는 묶음(gatherRun)은 같은 실행의 부모·자식이다 — 부모를 먼저 본다. 「멈춤」 은 어느 것이든 「지금 하는 일이 끝나면」 이다(바로 끊지 못한다).
function agwRunning() { // → {kind, label, note, t0(Date.now 기준 ms — 0 = 모름), stopping, stop() | null} | null
  if (!state.id) return null;
  if (typeof DWF !== "undefined" && DWF.busy) return { kind: "workflow", label: "워크플로우 선택", note: "목록·진행 기록 저장 중", t0: 0, stopping: false, stop: null };
  const stage = (list, id) => { const g = list.find((x) => x.id === id); return g ? `${g.no} ${g.name}` : ""; };
  const Q = typeof gqRun !== "undefined" ? gqRun : null, G = typeof gatherRun !== "undefined" ? gatherRun : null, T = typeof taskRun !== "undefined" ? taskRun : null;
  if (Q && Q.busy) return { kind: "quick", label: Q.uploadOnly ? "기관 문서 올리기 · 등록" : "간단 모드 — 끝까지 한 번에 진행", note: Q.note || "진행 중", t0: Q.t0, stopping: !!Q.stop,
    stop: () => { Q.stop = true; if (typeof gatherRun !== "undefined" && gatherRun) gatherRun.stop = true; if (typeof gqDraw === "function") gqDraw(); } };
  if (G) return { kind: "gather", label: `${stage(GT_STAGES, G.stage)} — 한 번에 진행`, note: G.note || "진행 중", t0: G.t0, stopping: !!G.stop, stop: () => { G.stop = true; gatherStageSync(); } };
  if (T && (T.single || T.flow)) { // 문서 하나로 조립한 워크플로우의 서버 실행(workflow_exec.js singleRunFollow 의 거울 — 이관의 거울과 같은 변수) — 묶음은 그 정의의 것(g1 …: 이관의 묶음 TASK_STAGES 가 아니다). 멈춤은 거울이 서버에 건다(1초 안)
    // flow = 줄 목록으로 조립한 이관형의 서버 실행(relayFlowFollow 의 거울 — 그 정의의 묶음도 g1 …: 같은 꼴 · kind 만 다르다)
    const g = agwSingleStage(T.stage), name = g ? `${g.no || ""} ${g.name || ""}`.trim() : "";
    return { kind: T.single ? "single" : "flow", label: `${name || "워크플로우"} — ${T.only ? "이 단계만 진행" : T.role ? `${T.role === "source" ? "원본 문서" : "목적 문서"}만` : "한 번에 진행"}`, /* role = 한 문서만으로 시작한 실행(그 문서의 줄만 — spec_워크플로우 ② §18-21) */ note: [T.by, T.note || "진행 중"].filter(Boolean).join(" · "), t0: T.t0, stopping: !!T.stop, stop: () => { T.stop = true; } };
  }
  if (T) return { kind: "relay", label: `${stage(TASK_STAGES, T.stage)} — 한 번에 진행`, note: T.note || "진행 중", t0: T.t0, stopping: !!T.stop, stop: () => { T.stop = true; taskStageSync(); } };
  if (typeof dv !== "undefined" && dv && dv.auto) return { kind: "fit", label: "프로젝트 구성 반영 — 한 번에 진행", note: "변경 계획 → 반영", t0: 0, stopping: false, stop: null };
  const S = typeof STYLE !== "undefined" && STYLE.save && STYLE.save.auto ? STYLE.save : null; // 서식 복사(2열 「서식 복사」 의 「한 번에 진행」 — 문서는 안 바뀐다)
  if (S) return { kind: "style", label: "서식 복사 — 한 번에 진행", note: S.llm ? "② LLM 검토" : S.busy ? `③ 저장 ${S.busy.i + 1}/${S.busy.n}` : "④ PDF 검증을 기다리는 중", t0: Date.now() - (performance.now() - S.auto.t0),
    stopping: !!S.auto.stop, stop: () => { S.auto.stop = true; if (typeof styleSaveDraw === "function") styleSaveDraw(); } };
  const F = typeof headsAllRunning === "function" ? headsAllRunning() : null; // 헤딩 추출 「전체 실행」(heads_run_all.js — 남은 LLM 단계 → 조정까지: spec_헤딩_추출 ② §7 「전체 실행」) — 그 안에서 도는 LLM 검증·보완보다 먼저
  if (F) return { kind: "headsAll", ...F };
  const P = typeof headsPickRunning === "function" ? headsPickRunning() : null; // 헤딩 추출 「단계별 실행」 — 고른 단계를 차례로(heads_run_pick.js: spec_헤딩_추출 ② §7 「실행 메뉴는 머리에」) — 그 안에서 도는 헤딩 판정 → 서식 계획보다 먼저
  if (P) return { kind: "headsPick", ...P };
  const A = typeof dsRunning === "function" ? dsRunning() : null; // 분석의 「LLM 검증·보완」(doc_status.js — spec_작업 ② §20) — 어느 TASK 에서나
  if (A) return { kind: "analysis", ...A };
  return null;
}
const agwLiveText = (R) => `${R.note}${R.t0 ? ` · ${typeof fmtDur === "function" ? fmtDur((Date.now() - R.t0) / 1000) : `${Math.round((Date.now() - R.t0) / 1000)}초`}` : ""}${R.stopping ? " · 이 일이 끝나면 멈춥니다" : ""}`;
// 문서 하나로 조립한 워크플로우의 묶음(id g1 …) → {no, name} | null — 대시보드가 읽어 둔 서버 상태(dashboard.js DASH.flow) → 등록부(DASH.reg)에서(둘 다 없으면 이름 없이 보인다)
function agwSingleStage(gid) {
  const D = typeof DASH !== "undefined" ? DASH : null, V = D && D.flow && D.flow.id === state.id ? D.flow.view : null, reg = D && D.reg ? D.reg.tasks.find((t) => t.job === agwJob()) : null;
  return ((V && V.stages) || []).find((g) => g.id === gid) || ((reg && reg.stages) || []).find((g) => g.id === gid) || null;
}

// 첫 화면의 문서 목록이 TASK 를 시작하는 동안(목적 문서 열기 → 원본·기관 문서 올리기 → 간단 모드: home_files.js homeFilesGo) 시작 턴을 **붙들어 둔다** — 준비가 끝난 상태로 한 번만 낸다.
// 전에는 문서를 열자마자 시작 턴이 따로 돌아, 원본 문서가 붙기 전의 상태(「두 칸에 문서를 골라야 합니다」)를 설명하거나 간단 모드가 도는 중에 「다음 단계」 를 제안·실행했다(astra 11-16 P1 · 확인 probe_overlap.py).
let agwHold = 0;    // 붙든 수(homeFilesGo 가 올리고 내린다)
let agwWait = null; // 붙들어 둔 시작 {id 작업, job}
function agentWorkHold(on) {
  agwHold = Math.max(0, agwHold + (on ? 1 : -1));
  if (agwHold || !agwWait) return;
  const w = agwWait;
  agwWait = null;
  if (w.id === state.id && w.job === agwJob() && AGENT.loaded) agwBegin();
}
function agwQuickText(Q) { // 간단 모드의 끝 → 결과 글: 끝남/멈춤 + 기관 문서마다 한 줄(반영할 기관 · 결과 · 남긴 것 — 취합 카드의 간단 모드 줄과 같은 글)
  const rows = Q.items.filter((it) => it.pid || it.err).map((it) => { const [org, res] = gqRowText(Q, it); return `· ${it.name}${org ? ` → ${org}` : ""}: ${res || "넣을 것 없음"}`; });
  return [`간단 모드(끝까지 한 번에 진행) ${Q.end.ok ? "끝남" : "멈춤"} — ${Q.end.text}`, ...rows.slice(0, 8), rows.length > 8 ? `· 외 ${rows.length - 8}개 문서` : ""].filter(Boolean).join("\n").slice(0, 1900);
}
function agwBegin() { // 시작 턴을 낼 때 — 방금 첫 화면의 간단 모드가 돌았으면 시작 턴 대신 **그 결과를 보고하는 턴**(무엇을 넣었고 무엇을 남겼나 → 다음 행동)
  const Q = typeof gqRun !== "undefined" ? gqRun : null;
  if (Q && Q.plan === state.id && Q.end && !Q.busy && !Q.uploadOnly && !Q.told && agwGuided()) {
    Q.told = true;
    agwCarry = null;
    agw().chain = 0;
    agentWorkTurn("result", { text: agwQuickText(Q), ok: !!Q.end.ok, act: "quick" });
    return;
  }
  agentWorkStart();
}

// ---------------------------------------------------------------- 상태 · 행동(TASK 마다) → {steps, actions, facts}
function agwCommon(out) { // 어느 TASK 든 — 작업 개요 열기 · 편집 턴으로 넘기기
  out.actions.push({ name: "open:div", label: "패널 「작업 개요」 열기", does: "이 워크플로우의 단계 목록과 세부 단추를 직접 봅니다 — 단계마다 확인하며 하거나, 한 번에 진행이 남긴 것을 보정합니다", change: "none" });
  if (AGENT.enabled && AGENT.policy.apply !== false) out.actions.push({ name: "edit", label: "편집 에이전트에 넘기기", does: "글·표를 쓰거나 고쳐 달라는 요청을 편집 에이전트가 받아 제안을 냅니다", change: "none" });
  out.facts.llm = !!AGENT.enabled;
  return out;
}

// 표 하나만의 계획(plan.only — 표 메뉴 「프로젝트 구성에 맞추기…」: spec_테이블매니저 ② §9)은 TASK 의 「문서 전체 계획」 이 아니다 — 에이전트 · 대시보드는 그것을 「다시 계획해야 하는 계획」(skip 과 같은 꼴)으로 본다:
// 그 계획으로 「문서에 반영」 카드를 내거나 그 반영을 1단계의 끝남으로 세지 않는다(반영은 그 표의 메뉴 → 패널 「반영」 에서 사람이 한다).
function agwTaskPlan(st = divPlanState()) { return st.plan && st.plan.only != null ? { kind: st.kind === "none" ? "none" : "skip", plan: st.plan } : st; }
// 묶음째 실행의 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」) — 문서를 바꾸는 묶음의 실행 카드 「…한 번에 진행」 에 붙는 글(서버 실행이 끝에 확정한다 · 확정 뒤 가져오기 검증의 LLM 검토는 그 카드가 유료로 승인한 문서만)
const AGW_COMMIT_NOTE = " · 끝나면(멈춤이 아니면) 바뀐 문서의 고친 문단을 확정합니다 — 앞 상태는 「고친 문단」 탭 확정 기록의 복원 · 확정 뒤 검증의 LLM 검토는 이 카드가 유료로 승인한 문서만";
function agwFitApplied(st = divPlanState(), v = dv.view) { // 1단계 「적용(반영)」 이 끝났나 → {applied, same} — 반영함 · 이미 구성에 맞음 · 마지막으로 반영한 값이 지금 값과 같음(agwFitStatus · 대시보드 「이어서 한 번에」 가 같이 본다)
  st = agwTaskPlan(st);
  const s = st.plan && st.plan.summary, same = st.kind === "same" && divSameText(s).ok, values = dv.values ? divValues() : null;
  // 전체 반영 뒤에 다른 값으로 「한 자리만 반영」 한 문서는 더는 그 값 그대로가 아니다(v.partial — spec_테이블매니저 ② §9 「한 자리만 반영한 기록」: 전체 반영이 그 기록을 지운다) — 「마지막 반영 = 지금 값」 만으로 끝남으로 세지 않는다
  const mixed = !!v && !!v.applied && (v.partial || []).some((p) => p.values && divConfirmKey(p.values) !== divConfirmKey(v.applied.values));
  return { same, applied: st.kind === "done" || same || (st.kind === "none" && !mixed && !!v && !!v.applied && !!v.applied.values && !!values && divConfirmKey(v.applied.values) === divConfirmKey(values)) };
}

// 양식 맞추기(report_fit) · 양식 표준화(plan_fit — spec_양식표준화: 1단계 프로젝트 구성 + 2 · 3단계 헤딩 추출 · 표는 agwStdStatus) — 프로젝트 구성 값(확정) → ① 변경 계획 → ② 반영.
// opt.fresh = 분석 상태(헤딩 · 표)를 지금 다시 읽는다 — 에이전트 턴이 부를 때(대시보드는 1초마다 부르므로 화면이 들고 있는 값으로)
async function agwFitStatus(opt = {}) {
  if (!dv.view || !dv.values) await divShow();
  const std = agwJob() === "plan_fit", g1 = std ? { open: AGW_STD.config, config: AGW_STD.config, frame: AGW_STD.config } : { open: "준비", config: "프로젝트 구성", frame: "구조 반영" }; // 진행 줄의 묶음 이름(등록부 _std · _fit 의 묶음)
  const out = { steps: [{ stage: g1.open, key: "open", name: "문서 올리기 · 기본 분석", state: "done", text: "" }], actions: [], facts: {} }, v = dv.view;
  if (!v || !dv.values) { out.facts.why = "프로젝트 구성 상태를 읽지 못했습니다"; return agwCommon(out); }
  const values = divValues(), text = divValuesText(values), confirmed = divConfirmValid(dv.values, v.confirmed), why = divRunWhy(), st = agwTaskPlan(divPlanState()), s = st.plan && st.plan.summary;
  const has = !!(values.orgs.lead || values.orgs.joint.length || values.stages.length > 1 || values.stages[0] > 1);
  const { same, applied } = agwFitApplied(st, v);
  const issues = s && (st.kind === "ready" || st.kind === "same") ? divPlanIssues(s, false) : "";
  const planText = !s ? "" : st.kind === "stale" || st.kind === "skip" ? "계획이 낡았습니다 — 다시 계획해야 합니다"
    : st.kind === "same" ? divSameText(s).text : `맞출 자리 ${s.applied}곳 · 항목 추가 ${s.added} · 지움 ${s.removed} · 글 바꿈 ${s.changes} · 지워지는 글 문단 ${s.deleted}${issues ? ` · ${issues}` : ""}`;
  const planned = st.kind === "ready" || st.kind === "same" || st.kind === "done";
  out.steps.push({ stage: g1.config, key: "values", name: std ? "프로젝트 구성 추출" :"프로젝트 구성 값 정하기 · 확정", state: confirmed ? "done" : "now", text: confirmed ? text : has ? `입력됨(확정 전) — ${text}` : "아직 값이 없습니다" },
    { stage: g1.frame, key: "plan", name: "① 변경 계획 보기", state: applied || (confirmed && planned) ? "done" : confirmed ? "now" : "todo", text: planText },
    { stage: g1.frame, key: "apply", name: std ? "② 적용(문서에 반영)" : "② 반영", state: applied ? "done" : confirmed && st.kind === "ready" ? "now" : "todo", text: applied ? (same ? "이미 프로젝트 구성에 맞습니다" : "문서 구조를 프로젝트 구성에 맞췄습니다") : "" });
  Object.assign(out.facts, { config: has ? text : "", confirmed, plan: planText, supported: !!v.profile.supported });
  if (why) out.facts.why = why;
  if (!confirmed) {
    out.actions.push({ name: "config_read", label: "구성 읽기", does: "문서에 적힌 단계 · 차년도 · 기관을 읽어 입력 값으로 가져옵니다(확정은 따로)", change: "none", primary: !has && !agw().readTried });
    out.actions.push({ name: "config_set", label: "프로젝트 구성 입력 · 확정", does: "단계 · 차년도 · 기관을 입력받아 저장(확정)합니다 — 문서는 바뀌지 않습니다", change: "store", primary: has || agw().readTried });
  } else {
    if (!why && !applied) {
      const moved = st.kind === "ready" ? divOrgsMoved() : ""; // 기관의 차례가 마지막 반영과 다름 — 쓴 내용이 다른 기관 이름 아래에 남을 수 있다(「한 번에 진행」 이 멈추는 조건과 같다: app.js divAutoStops)
      if (moved) out.facts.moved = moved;
      // key = 이 카드가 가리키는 계획 — 「진행」 을 누를 때 지금 계획과 견준다(다르면 실행하지 않고 새 계획으로 다시 묻는다: agentWorkRun · astra 11-16 P1)
      if (st.kind === "ready") out.actions.push({ name: "apply", label: "문서에 반영", does: `변경 계획대로 절 · 표 행 · 표 열을 늘리고 줄입니다(${planText}) — 줄어드는 항목은 그 안의 글과 함께 지워지고, 실행 취소 한 번으로 되돌립니다${moved ? ` · ${moved}` : ""}`,
        change: "doc", primary: !issues && !moved, key: `plan:${st.plan.planId || ""}:${st.plan.baseRev}` });
      if (st.kind === "ready" && (issues || moved || s.deleted || s.removed)) out.actions.push({ name: "open:plan", label: "변경 계획 목록 보기", does: `문서 옆 열에 바뀔 자리 목록을 엽니다 — ${[issues, moved, s.deleted ? `지워지는 글 문단 ${s.deleted}` : ""].filter(Boolean).join(" · ") || `지워지는 항목 ${s.removed}`}을 확인합니다`, change: "none" });
      out.actions.push({ name: "plan", label: st.kind === "ready" ? "변경 계획 다시 세우기" : "변경 계획 보기", does: "프로젝트 구성에 맞추면 바뀔 자리를 셉니다 — 문서는 바뀌지 않고, 목록이 문서 옆 열에 열립니다", change: "none", primary: st.kind !== "ready" });
    }
    out.actions.push({ name: "config_set", label: "프로젝트 구성 고치기", does: "단계 · 차년도 · 기관을 다시 입력해 확정합니다 — 문서는 바뀌지 않습니다", change: "store" });
  }
  if (std) await agwStdStatus(out, { open: applied || !v.profile.supported, fresh: !!opt.fresh }); // 2 · 3단계 행동은 1단계가 「적용」 까지 끝난 뒤(지원 안 되는 양식이면 1단계를 할 수 없으니 바로 — 등록부 _std 「지원 양식인가」)
  return agwCommon(out);
}

// ---------------------------------------------------------------- 양식 표준화(plan_fit)의 2 · 3단계 — 헤딩 추출 · 표(spec_양식표준화 ② §2·§5)
// 상태는 **분석 상태**(dsState.main — GET …/analysis: 이름 줄 · 진행표와 같은 값)와 헤딩 쪽에서 도는 것(헤딩 작업 · 전체 실행 · 단계별 실행 · LLM 검증·보완)으로 센다 — 새 상태를 만들지 않는다.
// 에이전트(agwStdStatus — steps · 행동)와 대시보드(dashboard.js dashStdLive)가 agwStdSteps 를 같이 쓴다. 단계 key 는 등록부(app/workflow.py _std)의 것 — 바꾸면 여기와 대시보드를 함께 본다.
// 실행은 기존 함수다: 헤딩 · 표 LLM 판정 = 「단계별 실행」(heads_run_pick.js headsPickRun) · 조정 = 진행 줄 「조정」 의 「모두 반영」(tpl_plan_bar.js tpbApply) · 남은 것 = heads_run_all.js hraLeft · hraUnseen.
const AGW_STD = { config: "1단계 프로젝트 구성", heads: "2단계 헤딩 추출", tables: "3단계 표" }; // 진행 줄의 묶음 이름 — 등록부 _std 의 묶음(no · name)과 같게
const AGW_STD_KEYS = ["heads", "headsLlm", "adjust", "tables", "tablesLlm"]; // 세는 단계(안 해도 되는 tree · tableTools 는 대시보드만)
const AGW_STD_NAMES = { heads: "헤딩 · 템플릿 추출", headsLlm: "헤딩 LLM 판정 · 서식 계획", adjust: "조정 — 템플릿 조정 · 서식 조정", tables: "표 구조 — 칸 역할 라벨", tablesLlm: "표 판정(LLM) — 라벨 검증 · 보완" };
const agwStdView = () => (typeof dsState === "object" && state.id && dsState.mainId === state.id ? dsState.main : null);
const agwHash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) | 0; return (h >>> 0).toString(36); }; // 행동 key 를 짧게(서버 KEY_MAX)
// 조정이 반영할 것 한 줄 — 받아 둔 계획(맞출 줄 · 뗄 줄 · 대표 변경) · 스크립트가 맞출 것(자리 맞춤 · 확실한 종속). P = hraLeft
const agwStdApplyText = (P) => [P.plans ? `받아 둔 서식 정리 계획 ${nf(P.plans)}개(템플릿)` : "", P.change ? `대표에 맞출 줄 ${nf(P.change)}` : "", P.moved ? `서식 종속 템플릿으로 뗄 줄 ${nf(P.moved)}` : "",
  P.reps ? `대표를 바꿀 레벨 ${nf(P.reps)}` : "", P.place ? `자리 맞춤 ${nf(P.place)}줄` : "", P.sure ? `확실한 종속 ${nf(P.sure)}개` : ""].filter(Boolean).join(" · ") || "반영할 것";

async function agwStdFresh() { // 분석 상태를 지금 다시 읽는다(행동이 끝난 뒤 · 에이전트 턴) — 이름 줄도 같은 자료로(doc_agent_next.js agnReport 와 같은 길) → 분석 상태 | null
  const id = state.id, epoch = state.epoch;
  if (!id) return null;
  let v = null;
  try { v = await api(`/api/docs/${id}/analysis`); } catch { return null; }
  if (epoch !== state.epoch || id !== state.id) return null;
  if (typeof dsState === "object" && dsState.mainId === id) { dsState.main = v; if (typeof dsDraw === "function") dsDraw("main"); }
  return v;
}

async function agwHeadsView() { // 헤딩 요약(heads.view)이 없으면 한 번 읽어 그린다 — 단계별 실행 · 전체 실행이 1단계 결과를 본다(heads_run_pick.js hrpOff).
  // headsShow(탭 열기)와 달리 추출을 저절로 시작하지 않는다(GET 만 — 도는 작업이 있으면 끝날 때까지 읽음: headsPeek 와 같은 몫 + heads.view)
  if (!state.id || state.format === "docx" || heads.view) return;
  const id = state.id, epoch = state.epoch;
  let r = null;
  try { r = await api(`/api/docs/${id}/headings`); } catch { return; }
  if (epoch !== state.epoch || heads.view) return;
  headsRender(r);
  if (r.job && r.job.status === "running") headsPoll();
}

function agwStdBusy(v = agwStdView()) { // 헤딩 쪽에서 도는 것의 이름 | "" — 전체 실행 · 단계별 실행 · LLM 검증·보완(에이전트 진행 카드와 같은 것) · 그 밖의 헤딩 작업(첫 분석 · 탭의 단계 하나)
  const R = (typeof headsAllRunning === "function" && headsAllRunning()) || (typeof headsPickRunning === "function" && headsPickRunning()) || (typeof dsRunning === "function" && dsRunning()) || null;
  if (R) return R.label;
  const job = heads.view ? heads.view.job : null;
  return (job && job.status === "running") || (v && v.busy) ? "헤딩 작업이 도는 중" : "";
}

// → {v, busy, judged, undecided, P(hraLeft), can(조정 「모두 반영」 을 할 수 있나), applyKey, items{heads, tables, formats}, steps{heads, headsLlm, adjust, tables, tablesLlm: {state: done|run|fail|todo, text}}} | null(분석 상태를 아직 못 읽음)
function agwStdSteps(v = agwStdView()) {
  if (!v) return null;
  const by = Object.fromEntries((v.items || []).map((i) => [i.key, i])), H = by.heads, T = by.tables, F = by.formats, busy = agwStdBusy(v);
  if (!H || !T) return { v, busy, none: true, steps: Object.fromEntries(AGW_STD_KEYS.map((k) => [k, { state: "todo", text: "헤딩 · 표 분석은 hwpx 문서에서만 됩니다" }])) };
  const base = (it) => (it.state === "done" ? { state: "done", text: it.short || it.text || "" } : it.state === "running" || it.state === "wait" ? { state: "run", text: `${it.name} 분석 중(스크립트)` }
    : it.state === "failed" ? { state: "fail", text: `${it.name} 분석 실패 — ${it.error || "까닭 모름"}` } : { state: "todo", text: `${it.name} 분석 결과가 없습니다` });
  const llm = (it) => { const L = it.llm || {}; return { state: L.state === "done" ? "done" : L.state === "running" || L.state === "wait" ? "run" : L.state === "failed" ? "fail" : "todo", text: `${L.text || "LLM 판정 안 함"}${L.error ? ` — ${L.error}` : ""}` }; };
  const judged = (H.llm || {}).state === "done", undecided = judged ? H.undecided || 0 : 0, P = typeof hraLeft === "function" ? hraLeft(v) : null, fl = (F && F.llm) || {}, ap = (F && F.apply) || {};
  let adjust; // 조정 — 헤딩 판정(LLM) 전이면 남음 · 판정 뒤 반영할 것(계획 · 자리 맞춤 · 확실한 종속 · 받을 계획)이 남지 않았으면 끝남(등록부 「반영할 계획 · 자리 맞춤이 남지 않았을 때」).
  // 차례가 중요하다 — 서식 항목의 반영 칸(ap)이 ✓ 여도 판정 전이거나 확실한 종속 · 대표 변경이 남았으면 끝남이 아니다(검토 11-18: 전에는 반영 칸을 먼저 봐 「이어서 한 번에」 가 종속을 건너뜀)
  if (!F || H.state !== "done") adjust = { state: "todo", text: "헤딩 그래프가 있어야 셉니다" };
  else if (!judged) adjust = { state: "todo", text: `헤딩 LLM 판정 뒤에 합니다${ap.text ? ` — 지금 ${ap.text}` : ""}` };
  else if (fl.state === "running" || fl.state === "wait") adjust = { state: "run", text: fl.text || "서식 정리 계획을 받는 중" };
  else if (P && P.apply) adjust = { state: "todo", text: undecided ? `헤딩 판정에 미판정 ${nf(undecided)}곳이 있어 반영하지 않습니다 — 헤딩 판정을 다시 돌리거나 「계획 보기」 에서 확인합니다` : `반영할 것 — ${agwStdApplyText(P)}` };
  else if (P && P.need.length) adjust = { state: "todo", text: `서식 정리 계획을 받지 않은 템플릿 ${nf(P.need.length)}개 — 「계획 보기」 의 「계획 받기」(유료)` };
  else if (!P && ap.state !== "done") adjust = { state: "todo", text: ap.text || "반영할 것이 남았는지 셀 수 없습니다 — 헤딩 추출 탭의 「조정」 줄을 보세요" };
  else { const left = P && typeof hraUnseen === "function" ? hraUnseen(P, true) : []; adjust = { state: "done", text: `반영할 것이 남지 않았습니다${ap.text ? ` — ${ap.text}` : ""}${left.length ? ` · 남긴 것: ${left.join(" / ")}` : ""}` }; } // 남긴 줄은 실패도 「다 맞음」 도 아니다 — 무엇이 몇 줄 · 어디서 보정하는지(spec_작업에이전트 ② §7 ⓐ)
  const hl = llm(H);
  if (judged && fl.text) hl.text += ` · ${fl.text}`;
  return { v, busy, judged, undecided, P, can: judged && !undecided && !!P && !!P.apply, items: { heads: H, tables: T, formats: F },
    applyKey: P ? `fmt:${agwHash(JSON.stringify([P.at, P.change, P.moved, P.reps, P.place, P.sure]))}` : "", // 카드가 가리키는 계획 — 「진행」 을 누를 때 지금 계획과 견준다(agentWorkRun)
    steps: { heads: base(H), headsLlm: hl, adjust, tables: base(T), tablesLlm: llm(T) } };
}

async function agwStdStatus(out, o = {}) { // 2 · 3단계 → out.steps · out.actions · out.facts 에 더한다. o.open = 1단계가 끝났나(그 전에는 2 · 3단계 행동을 내지 않는다) · o.fresh = 분석 상태를 지금 다시 읽는다
  const W = agw();
  if (o.fresh || (!agwStdView() && W.stdTried !== state.epoch)) { W.stdTried = state.epoch; await agwStdFresh(); } // 대시보드(1초마다)는 처음 한 번만 — 못 읽어도 되풀이하지 않는다
  const S = agwStdSteps();
  out.std = S; // 대시보드가 쓰는 자세한 상태(서버에는 보내지 않는다 — agentWorkTurn 은 steps · actions · facts 만)
  const now = o.open && S ? AGW_STD_KEYS.find((k) => S.steps[k].state !== "done") : null, llmOff = !AGENT.enabled;
  for (const k of AGW_STD_KEYS) {
    const s = S ? S.steps[k] : { state: "todo", text: "분석 상태를 읽지 못했습니다" };
    out.steps.push({ stage: k.startsWith("tables") ? AGW_STD.tables : AGW_STD.heads, key: k, name: AGW_STD_NAMES[k], state: s.state === "done" ? "done" : k === now ? "now" : "todo",
      text: s.text + (k === now && llmOff && (k === "headsLlm" || k === "tablesLlm") ? " · LLM 을 쓸 수 없어 지금은 할 수 없습니다" : "") });
  }
  if (!S || S.none) return;
  if (S.busy) { out.facts.headsBusy = `${S.busy} — 끝나면 2 · 3단계를 이어 갑니다`; return; } // 도는 동안은 2 · 3단계 행동을 내지 않는다(같은 문서에 두 실행을 겹치지 않는다)
  if (!o.open) return;
  const H = S.items.heads, T = S.items.tables, acts = [];
  if (llmOff && (S.steps.headsLlm.state !== "done" || S.steps.tablesLlm.state !== "done")) out.facts.llmOff = "LLM 을 쓸 수 없어 헤딩 · 표 LLM 판정을 할 수 없습니다 — 2 · 3단계는 스크립트 결과로 남습니다(LLM 을 켠 뒤 이어서 합니다)";
  if (H.state !== "done" || T.state !== "done") out.facts.analysis = "헤딩 · 표 기본 분석(스크립트)이 없거나 실패했습니다 — 대시보드의 「헤딩 추출(스크립트)」 · 「표 구조(스크립트)」 또는 이름 줄의 「분석」 으로 다시 뽑습니다(무료)";
  if (!llmOff && S.steps.headsLlm.state !== "done" && H.state === "done") acts.push({ name: "heads_llm", label: "헤딩 LLM 판정 · 서식 계획", change: "store", paid: true,
    does: "스크립트가 판정하지 못한 첫머리의 규칙 보강 → 헤딩 판정 → 서식이 여러 가지인 템플릿마다 서식 정리 계획을 차례로 받습니다(유료 · 몇 분) — 문서는 바뀌지 않고, 반영은 다음 「조정」" });
  if (S.can) acts.push({ name: "heads_apply", label: "조정 — 모두 반영", change: "doc", key: S.applyKey,
    does: `받아 둔 서식 정리 계획을 에이전트가 고른 그대로 한 번에 반영합니다 — ${agwStdApplyText(S.P)} · 「그대로」 로 남긴 줄은 안 바뀌고, 실행 취소 한 번으로 되돌립니다` });
  else if (S.judged && S.undecided && S.P && S.P.apply) out.facts.adjust = S.steps.adjust.text;
  if (!llmOff && S.steps.tablesLlm.state !== "done" && T.state === "done") acts.push({ name: "tables_llm", label: "표 판정(LLM)", change: "store", paid: true,
    does: "표 묶음마다 서브 테이블 · 헤더 행/열 · 칸 역할을 LLM 이 칸의 값을 보고 판정합니다(유료 · 수 분) — 문서는 바뀌지 않습니다" });
  if (acts.length && !out.actions.some((a) => a.primary)) acts[0].primary = true; // 남은 것 가운데 첫째(헤딩 판정 → 조정 → 표 판정)
  out.actions.push(...acts);
}

function agwStdApplied(r) { // tpbApply 의 결과 → 끝 글 {ok, text}(에이전트 · 대시보드가 같이 씀)
  if (!r) return { ok: false, text: "조정을 반영하지 못했습니다 — 알림 글을 보세요(그 사이 계획이 바뀌었거나 표준 검사에 걸림)" };
  if (r.nothing) return { ok: true, text: "바꿀 줄이 없습니다 — 계획이 모두 「그대로」 입니다" };
  const ts = r.templates || [], n = (r.changed || []).length, mg = (r.merged || []).length, splits = ts.reduce((a, t) => a + (t.splits || []).length, 0);
  return { ok: true, text: `조정을 반영했습니다 — ${[ts.length ? `템플릿 ${nf(ts.length)}개` : "", n ? `바뀐 줄 ${nf(n)}` : "", splits ? `서식 종속 템플릿 ${nf(splits)}개` : "", mg ? `템플릿 종속 ${nf(mg)}` : ""].filter(Boolean).join(" · ") || "대표만 바뀜"}(「실행 취소」 한 번으로 되돌립니다)` };
}

async function agwRelayStatus() { // 이관 — 묶음(1~4단계)의 단계와 「한 번에 진행」
  if (!dv.view) await divShow();
  try { await taskFlowLoad(); } catch { /* 못 읽은 것은 단계 글에 */ }
  // LLM 을 쓸 수 있는지 아직 모르면(taskLlmOk null) 단계와 유료로 부를 문서를 세기 전에 물음이 끝나기를 기다린다(상한 5초 — 넘으면 쓸 수 있는 것으로 센다: 카드로 묻는 쪽).
  // 모른 채 세면 쓸 수 없는 LLM 을 유료로 적어 카드로 묻고, 알게 된 뒤 key 가 달라져 그 카드를 실행하지 않고 다시 묻는다(app.js taskLlmLoad 가 그 약속을 돌려준다)
  if (taskLlmOk == null && typeof taskLlmLoad === "function") {
    const ask = taskLlmLoad();
    if (ask && typeof ask.then === "function") await Promise.race([ask, new Promise((r) => setTimeout(r, 5000))]);
  }
  const out = { steps: [], actions: [], facts: {} }, slots = taskSlots(), docs = (slots || []).map((k) => taskSlotDoc(k));
  if (!slots || docs.some((d) => !d)) {
    out.steps.push({ stage: `${TASK_STAGES[0].no} ${TASK_STAGES[0].name}`, key: "files", name: "준비 — 사업계획서 · 연차보고서 고르기", state: "now", text: "두 칸(사업계획서 · 연차보고서)에 문서를 골라야 합니다 — 패널 「작업 개요」 의 첨부 파일 칸" });
    out.facts.why = "사업계획서와 연차보고서가 둘 다 있어야 합니다";
    out.actions.push({ name: "open:div", label: "패널 「작업 개요」 열기", does: "첨부 파일 칸에서 사업계획서와 연차보고서를 고르거나 올립니다", change: "none", primary: true });
    out.facts.llm = !!AGENT.enabled;
    return out;
  }
  const calc = taskStepsCalc();
  for (const g of TASK_STAGES) for (const s of calc.filter((x) => g.keys.includes(x.key))) out.steps.push({ stage: `${g.no} ${g.name}`, key: s.key, name: taskStepName(s), state: s.st === "ready" ? "todo" : s.st, text: s.text || "" });
  const g = TASK_STAGES.find((x) => taskStageWork(x).some((s) => !s.done)), report = taskSlotDoc("report");
  out.facts.docs = docs.map((d) => d.name).join(" · ");
  if (g && report && report.id !== state.id) { // 이 문서는 원본(사업계획서) — 이관은 목적 문서에서 진행한다(실행 몸통이 그 문서를 열면 이 대화가 닫혀 결과를 보고하지 못한다: astra 11-16)
    out.facts.why = "이 문서는 원본 문서입니다 — 이관은 연차보고서(목적 문서)에서 진행합니다";
    out.actions.push({ name: "open:target", label: `연차보고서 「${report.name}」 열기`, does: "이관은 연차보고서(목적 문서)에서 진행합니다 — 그 문서를 열면 에이전트가 이어서 안내합니다(이 문서는 바뀌지 않습니다)", change: "none", primary: true });
    return agwCommon(out);
  }
  // key = 이 카드가 가리키는 일(그 묶음의 남은 단계 + 유료로 부를 문서) — 「진행」 을 누를 때 · 무료 행동을 저절로 하기 직전에 지금과 견준다(agentWorkRun)
  // 꼬리표 — 1단계 「문서 검토」 는 문서를 안 바꾼다(「저장만」). 유료 = 그 묶음의 LLM 검증·보완(1단계 headsLlm · 2단계 reheadsLlm)이 실제로 부를 문서가 있을 때(taskPaidDocs — 아직 거치지 않았고
  // 사람이 건너뛰지 않은 문서 · LLM 을 쓸 수 있을 때: spec_워크플로우 ② §15 · astra P1 ⓑ)와 3단계 「내용 넣기」(묶음째 — 전과 같다) — 유료면 카드로 묻는다(agwAsk): spec_작업 ② §21.
  // 부를 문서가 없으면(모두 거침 · 건너뜀 · LLM 을 쓸 수 없음) 1단계는 카드 없이 바로 한다. 카드 글 머리에 「유료 — 사업계획서 · 연차보고서 (2개)」 를 적고 key 에 그 문서 id 를 넣는다 —
  // 카드를 낸 뒤 다른 탭에서 「건너뛰기」 를 풀면 key 가 달라져 실행하지 않고 다시 묻는다(무료였던 행동이 유료가 되면 저절로 하지 않음). 실행은 그 문서에만 유료 호출을 건다(paidIds → taskRunAll 의 paid)
  const left = g ? taskStageWork(g).filter((s) => !s.done) : [], P = g ? taskPaidDocs(g.id, calc) : [], ids = P.map(([w]) => w.id);
  const paidText = P.length ? `유료 — ${P.map(([, n]) => n).join(" · ")} (${P.length}개)` : "", bind = g && (g.id === "review" || g.id === "frame"); // bind = 유료로 부를 문서를 문서마다 셈하는 묶음
  // 조립한 워크플로우는 key 에 그 정의의 단계 표지(task_catalog.js taskCatalogSig — 서버의 sig 또는 이 화면이 지은 것)를 넣는다 — 정의가 바뀌기 전에 낸 카드는 실행하지 않고 다시 묻는다(spec_워크플로우 ② §15 「실행」 · 서버 KEY_MAX 160 안). 붙박이는 그대로
  const cat = TASK_CATALOG[agwJob()] || {}, sig = cat.custom ? taskCatalogSig(cat) : "";
  if (g && !taskRun) out.actions.push({ name: `run:${g.id}`, label: `${g.no} ${g.name} — 한 번에 진행`, does: (paidText ? `${paidText} · ${g.does}` : g.does) + (g.id === "review" ? "" : AGW_COMMIT_NOTE), change: g.id === "review" ? "store" : "doc",
    paid: g.id === "map" || !!P.length, primary: true, paidIds: ids, // paidIds = 화면만 쓴다(서버는 안 받음 — work_guide.actions_in)
    key: `${docs.map((d) => d.id).join(">")}:${g.id}:${left.map((s) => s.key).join(",")}${bind ? `:paid=${ids.join(",")}` : ""}${sig ? `:sig=${sig}` : ""}` });
  return agwCommon(out);
}

async function agwGatherStatus() { // 취합 — 묶음(1~3단계)의 단계와 「한 번에 진행」
  if (!dv.view) await divShow();
  try { await gatherLoad(); } catch { /* 못 읽은 것은 단계 글에 */ }
  const out = { steps: [], actions: [], facts: {} }, plan = gatherPlan();
  if (!plan) {
    out.steps.push({ stage: `${GT_STAGES[0].no} ${GT_STAGES[0].name}`, key: "files", name: "준비 — 취합본 고르기", state: "now", text: "사업계획서(취합본)를 골라야 합니다 — 패널 「작업 개요」" });
    out.actions.push({ name: "open:div", label: "패널 「작업 개요」 열기", does: "취합본을 고르거나 올립니다", change: "none", primary: true });
    out.facts.llm = !!AGENT.enabled;
    return out;
  }
  const calc = gatherCalc(), V = await gatherServerView(plan), srv = {}; // srv = 화면의 묶음마다 같은 정의 묶음에 놓은 서버만 아는 줄(넣은 뒤 정리 — 서버가 센 상태: gather.js gatherServerRest · 조립한 취합만)
  for (const g of GT_STAGES) {
    srv[g.id] = gatherServerRest(g.id, V);
    for (const s of calc.filter((x) => x.stage === g.id)) out.steps.push({ stage: `${g.no} ${g.name}`, key: s.key, name: gatherStepName(s), state: s.st === "done" || s.st === "now" ? s.st : "todo", text: ((s.lines || [])[0] || [])[1] || "" });
    for (const s of srv[g.id] ? srv[g.id].steps : []) out.steps.push({ stage: `${g.no} ${g.name}`, key: s.key, name: s.name, state: s.done ? "done" : "todo", text: s.text || "" });
  }
  // 다음에 돌릴 묶음 — 남은 단계가 있는 첫 묶음(취합형으로 조립한 워크플로우는 그 정의에 그 줄이 든 묶음만: 없는 묶음은 세부 단추로 — task_catalog.js gatherDefStage).
  // 화면의 줄이 다 끝나도 같은 정의 묶음에 서버만 아는 줄이 남았으면 그 묶음이다(「한 번에 진행」 = gatherRunStage 가 그 정의 묶음째 서버로 돈다 · 끝나면 확정)
  const leftOf = (x) => calc.filter((s) => s.stage === x.id && !s.done && s.step !== "files"), more = (x) => (srv[x.id] ? srv[x.id].left : []);
  const g = GT_STAGES.find((x) => { const left = leftOf(x); return left.length ? !!gatherDefStage(x.id, agwJob(), left[0].key) : more(x).length > 0; });
  const tail = g && !leftOf(g).length ? more(g) : []; // 서버만 아는 줄만 남은 묶음 — 그 줄이 「지금」
  if (tail.length) { const row = out.steps.find((x) => x.stage === `${g.no} ${g.name}` && x.key === tail[0].key); if (row) row.state = "now"; }
  out.facts.plan = plan.name;
  if (plan.id !== state.id) { // 이 문서는 기관 문서(원본) — 취합은 취합본에서 진행한다(이관의 원본 문서와 같은 까닭)
    out.facts.why = "이 문서는 기관 문서입니다 — 취합은 취합본(목적 문서)에서 진행합니다";
    out.actions.push({ name: "open:target", label: `취합본 「${plan.name}」 열기`, does: "취합은 취합본(목적 문서)에서 진행합니다 — 그 문서를 열면 에이전트가 이어서 안내합니다(이 문서는 바뀌지 않습니다)", change: "none", primary: true });
    return agwCommon(out);
  }
  const Q = typeof gqRun !== "undefined" && gqRun && gqRun.plan === plan.id ? gqRun : null, parts = (gt().view || {}).parts || [];
  const lost = Q ? Q.items.filter((it) => !it.pid && it.err && !it.skip).length : 0; // 간단 모드가 못 올린 문서 — 「이어서」 가 다시 올린다
  if (Q && !Q.busy && Q.end && !Q.uploadOnly && (!Q.end.ok || lost)) { // 간단 모드가 멈췄거나 못 올린 문서가 남았다 — 이어서(남은 올리기 → 남은 묶음)
    out.facts.quick = `간단 모드 ${Q.end.ok ? "끝남" : "멈춤"} — ${Q.end.text}`;
    out.actions.push({ name: "quick:resume", label: "간단 모드 이어서", does: `멈춘 곳부터 남은 일을 끝까지 이어서 합니다${lost ? ` — 못 올린 문서 ${lost}개를 다시 올리고` : ""}(앞서 넣은 것은 다시 넣지 않음 · 기관 문서마다 편집 한 번)`, change: "doc", paid: !!Q.llm, primary: true,
      key: `quick:${plan.id}:${Q.items.filter((it) => it.pid).length}:${calc.filter((s) => s.done).length}` });
  }
  const last = tail.length ? tail[tail.length - 1].name : "", rest = tail.length ? ` — 이 묶음의 다른 단계는 끝났고 ${tail.map((s) => `「${s.name}」`).join(" · ")} ${typeof taskJosa === "function" ? taskJosa(last, "이", "가") : "이"} 남았습니다(서버에서 이 묶음을 다시 돌며 끝난 단계 · 넣을 것이 없는 기관 문서는 건너뜁니다)` : "";
  if (g && !gatherRun && !(Q && Q.busy)) out.actions.push({ name: `run:${g.id}`, label: `${g.no} ${g.name} — 한 번에 진행`, does: g.does + rest + (g.id === "config" ? "" : AGW_COMMIT_NOTE), change: g.id === "config" ? "store" : "doc", paid: g.id === "map", primary: !out.actions.length,
    key: `${plan.id}:${g.id}:${[...calc.filter((s) => s.stage === g.id && !s.done).map((s) => s.key), ...more(g).map((s) => s.key)].join(",")}` }); // 서버만 아는 줄도 key 에 — 그 줄이 끝나거나 다시 남으면 카드를 다시 묻는다
  let shown = 0;
  for (const p of parts) { // 넣지 않고 남긴 것(겹침 · 확인 필요 · 표 구조 다름) — 그 기관 문서의 목록을 바로 연다(「세부 단계로 보기」 만으로는 어디를 볼지 모른다: astra 11-16)
    const c = p.counts || {}, left = [c.overlap ? `겹침 ${nf(c.overlap)}` : "", c.unknownPlace ? `확인 필요 ${nf(c.unknownPlace)}` : "", c.structure ? `표 구조 다름 ${nf(c.structure)}` : ""].filter(Boolean).join(" · ");
    if (!left || shown >= 3) continue;
    shown += 1;
    out.actions.push({ name: `list:${p.work}`, label: `「${p.name}」 남긴 것 보기`, does: `${left} — 넣지 않고 남긴 내용을 문서 옆 목록에서 보고 고르거나, 기관 문서를 옆에 띄워 끌어 넣습니다`, change: "none" });
  }
  const leftAll = parts.reduce((n, p) => n + ((p.counts || {}).overlap || 0) + ((p.counts || {}).unknownPlace || 0) + ((p.counts || {}).structure || 0), 0);
  if (leftAll) out.facts.left = `넣지 않고 남긴 것 ${nf(leftAll)}곳(겹침 · 확인 필요 · 표 구조 다름) — 기관 문서마다 목록에서 보정합니다`;
  return agwCommon(out);
}

// 문서 하나로 조립한 워크플로우(task_catalog.js taskIsSingle — spec_워크플로우 ② §18-13 걸음 6의 화면 · 2026-11-20 사용자 「조립한 것만 서버로」) — **서버가 센 상태** 그대로
// (GET /api/works/{wid}/flow — workflow_exec.js flowGet: 대시보드와 같은 것): 묶음 › 줄의 상태와 다음 묶음의 「한 번에 진행」(서버 쪽 실행기 — agwExec 의 run: → singleRunServer). 화면이 단계를 세지 않고 화면 실행으로 가지 않는다
// (붙박이 양식 표준화 · 양식 맞추기의 agwFitStatus 와 다른 가지 — 그쪽은 그대로: 조립한 것을 이관 · 취합 · 붙박이 문서 하나로 읽지 않는다).
// 실행 카드는 그 묶음에 묶는다 — 행동의 key = 문서 · 묶음 · 남은 줄 · 유료로 부를 문서 · 정의의 지문 · 「반영에서 빼기」 자리: 그 사이 달라지면 실행하지 않고 다시 묻는다(agentWorkRun).
// 특정 계획(planId)을 승인하는 카드는 내지 않는다 — 서버 실행의 구조 반영은 울타리 안에서 제 계획을 세우고 같은 검사(계획 오류 · 미해결 · 기관 차례)로 멈춘다(본 계획과 다른 계획을 「승인한 것」 으로 반영하지 않게)
async function agwSingleStatus() {
  const out = { steps: [], actions: [], facts: {} }, id = state.id;
  let V = null;
  try { V = typeof flowGet === "function" ? await flowGet(id) : null; } catch (e) { out.facts.why = `단계 상태를 읽지 못했습니다: ${e.message}`; return agwCommon(out); }
  if (state.id !== id) return agwCommon(out);
  if (!V || !(V.stages || []).length) { out.facts.why = (V && V.why) || "이 작업의 워크플로우 상태를 읽지 못했습니다"; return agwCommon(out); }
  for (const g of V.stages) for (const s of g.steps || []) out.steps.push({ stage: `${g.no || ""} ${g.name || ""}`.trim(), key: s.key, name: s.name, state: s.done ? "done" : s.st === "now" || s.st === "run" ? "now" : "todo",
    text: `${s.done && s.skipped ? "건너뜀 — " : s.st === "blocked" ? "막힘 — " : s.st === "failed" ? "실패 — " : ""}${s.text || ""}` });
  const served = V.stages.filter((g) => g.server && g.steps), active = flowActive(V.run);
  if (!served.length) { out.facts.why = SINGLE_NOT_SERVED; return agwCommon(out); } // 조립한 것은 화면이 돌리지 않는다 — 서버가 못 맡으면 행동을 내지 않고 그 까닭만
  if (!V.ready && V.why) out.facts.why = V.why;
  const E = active ? null : flowEnd(V.last);
  if (E && E.text && (!E.ok || E.left)) out.facts.lastRun = E.text; // 지난 실행이 멈춤 · 남김 · 끊김으로 끝났다 — 무엇이 · 어디서(서버가 지은 글 그대로)
  const g = served.find((x) => x.left > 0); // 다음에 돌릴 묶음 — 남은 줄이 있는 첫 묶음
  if (g && g.can && !active && !taskRun) {
    const left = g.steps.filter((s) => !s.done && !s.optional).map((s) => s.key), ids = g.paid || [], name = `${g.no || ""} ${g.name || ""}`.trim();
    const skip = g.change && dv.skip && dv.skip.size ? `:skip=${agwHash([...dv.skip].sort().join(","))}` : ""; // 「반영에서 빼기」 로 뺀 자리(화면에만 있는 입력 — 시작할 때 서버에 싣는다)
    out.actions.push({ name: `run:${g.id}`, label: `${name} — 한 번에 진행`, does: `${ids.length ? `유료 LLM — 문서 ${ids.length}개 · ` : ""}${g.does || ""}${g.change ? AGW_COMMIT_NOTE : ""}`, change: g.change ? "doc" : "store", paid: !!ids.length, primary: true,
      paidIds: ids, sig: V.sig || "", // paidIds · sig = 화면만 쓴다(서버는 안 받음 — work_guide.actions_in): 실행은 그 문서에만 유료 호출을 걸고 그 정의일 때만 시작한다
      key: `${id}:${g.id}:${agwHash(left.join(","))}:paid=${ids.join(",")}:sig=${V.sig || ""}${skip}` });
  } else if (g && !g.can && g.why && !active) out.facts.next = `${g.no || ""} ${g.name || ""} — ${g.why}`.trim(); // 다음 묶음을 지금 못 하는 까닭(서버의 글 — 앞 묶음이 먼저 · 문서 칸이 빔)
  return agwCommon(out);
}

async function agwStatusOf(job, opt = {}) {
  // 목록에 없는 조립한 워크플로우(지워짐 · 저장 파일을 못 읽음 — task_catalog.js taskLostWhy): 행동 없이 그 까닭 한 줄만(아무 실행도 내지 않는다 · job 값은 그대로).
  // 진행 에이전트는 그런 문서를 맡지 않지만(agwGuided) 맡던 때 낸 실행 카드 · 질문 카드를 누르면 여기서 다시 센다(agentWorkRun · agentWorkAnswer — 그 까닭으로 실행하지 않음).
  // 단계 칸에도 같은 글을 둔다 — LLM 없이 답할 때(work_guide.fallback)도 그 줄이 「지금 차례」 로 읽힌다
  const lost = taskLostWhy(job);
  if (lost) return { steps: [{ stage: "준비", key: "workflow", name: "워크플로우 다시 고르기", state: "now", text: lost }], actions: [], facts: { why: lost, llm: !!AGENT.enabled } };
  try {
    if (taskIsSingle(job)) return await agwSingleStatus(); // 문서 하나로 조립한 것 — 서버가 센 상태(이관 · 취합 · 붙박이 문서 하나의 가지로 읽지 않는다)
    if (taskIsRelayFlow(job)) return await agwSingleStatus(); // 줄 목록(v2)으로 조립한 이관형 — 같은 길(서버가 센 상태: 그 정의의 묶음 g1 … 은 화면의 이관 묶음 셈 agwRelayStatus 에 안 잡힌다 — 2026-11-21) · 실행은 agwExec 의 run: → relayFlowRun
    if (agwFit(job)) return await agwFitStatus(opt);
    if (taskIsRelay(job)) return await agwRelayStatus();
    if (taskIsGather(job)) return await agwGatherStatus();
  } catch (e) { console.error(e); return agwCommon({ steps: [], actions: [], facts: { why: `단계 상태를 읽지 못했습니다: ${e.message}` } }); }
  return agwCommon({ steps: [], actions: [], facts: {} });
}
async function agwStatus(opt = {}) { // 도는 것이 있는 동안에는 보기만 — 실행·저장하는 행동을 내지 않는다(같은 문서에 두 실행이 겹치지 않게: 에이전트의 무료 행동은 바로 실행된다). opt.fresh = 에이전트 턴(분석 상태를 다시 읽음 — agwFitStatus)
  // 에이전트 턴이면(fresh) 조립한 워크플로우의 정의를 서버에서 다시 읽는다(app.js taskCatalogRefresh — 붙박이 · 도는 실행이 있으면 안 읽음): 바뀌었으면 새 정의로 세고(행동 key 의 단계 표지가 달라져
  // 그 전에 낸 카드는 실행하지 않고 다시 묻는다 — agentWorkRun) facts.reread 에 그 까닭을 적는다(이번에 읽어 달라졌을 때만 — 전부터 목록에 없던 것은 facts.why: agwStatusOf)
  const reread = opt.fresh && !agwRunning() && typeof taskCatalogRefresh === "function" ? await taskCatalogRefresh(agwJob()) : null;
  const out = await agwStatusOf(agwJob(), opt), R = agwRunning();
  if (reread && reread.moved) out.facts.reread = reread.gone ? reread.why : "이 워크플로우의 단계가 바뀌어 다시 읽었습니다";
  if (R) {
    out.actions = out.actions.filter((a) => a.name === "open:div" || a.name.startsWith("list:"));
    out.facts.running = `${R.label} — ${R.note}`;
  }
  return out;
}

// ---------------------------------------------------------------- 행동 실행 → {ok, text, silent?(결과 턴을 부르지 않음)}
function agwConfigApply(x) { // 질문 카드(config)의 값 → 입력 값(dv.values) — 단계마다 차년도 수 · 주관 · 공동(비영리 표시는 있던 것을 그 길이에 맞춘다) · 당해 차년도
  const v = dv.values, joint = x.joint.slice(0, 30), np = v.orgs.nonprofit || [];
  const dm = new Set((v.orgs.joint || []).filter((n, i) => n && (v.orgs.demand || [])[i + 1])); // 수요기업으로 고른 기관(spec_구분_기준 ② §24) — 카드는 이름만 받으니 **이름으로** 잇는다(차례가 바뀌어도 그 기관에 남게)
  v.stages = x.stages.map((n) => Math.max(1, Math.min(20, Number(n) || 1)));
  v.orgs.lead = x.lead;
  v.orgs.joint = joint;
  v.orgs.demand = [false, ...joint.map((n) => dm.has(n))];
  v.orgs.nonprofit = Array.from({ length: joint.length + 1 }, (_, i) => !!np[i]);
  if (x.current > 1) v.current = x.current; else delete v.current;
  divTouched();
  divRender();
}

async function agwExec(name, args, cur = null) { // cur = 실행 직전에 다시 센 이 행동(agentWorkRun — 이관의 run: 은 그 paidIds 로 유료 호출을 묶는다) · 다른 곳(대시보드)이 부를 때는 없음
  if (name === "open:div") { showTab("Div"); return { ok: true, text: "패널 「작업 개요」 를 열었습니다", silent: true }; }
  if (name === "open:plan") { divList(); return { ok: true, text: "문서 옆 열에 변경 계획 목록을 열었습니다", silent: true }; }
  if (name.startsWith("list:")) { await gatherListOpen(name.slice(5)); return { ok: true, text: "문서 옆 열에 그 기관 문서의 목록을 열었습니다", silent: true }; }
  if (name === "open:target") { // 원본 문서에서 — 목적 문서를 열고 그 문서의 에이전트로 넘긴다(이 대화는 그 문서로 넘어가지 않는다)
    const job = agwJob(), to = taskIsGather(job) ? gatherPlan() : taskSlotDoc("report");
    if (!to) return { ok: false, text: "목적 문서를 찾지 못했습니다" };
    await openWork(to.id);
    if (state.id === to.id) taskEnter(job);
    return { ok: state.id === to.id, text: state.id === to.id ? "목적 문서를 열었습니다" : "목적 문서를 열지 못했습니다(고치던 글을 두고 그만뒀거나 열리지 않음)", silent: state.id === to.id };
  }
  if (name === "quick:resume") { // 간단 모드 이어서 — 취합 카드의 「이어서」 와 같은 몸통(gather_quick.js gqGo). 실행 카드의 「진행」 이 그 확인이다
    const Q = typeof gqRun !== "undefined" ? gqRun : null;
    if (!Q || Q.busy || Q.plan !== state.id) return { ok: false, text: "이어서 할 간단 모드가 없습니다" };
    await gqGo(Q);
    Q.told = true;
    return Q.end ? { ok: !!Q.end.ok, text: agwQuickText(Q) } : { ok: false, text: "이어서 하지 못했습니다" };
  }
  if (name === "config_read") {
    const before = divCanon(divValues());
    await divRead();
    const W = agw(), got = divCanon(divValues()) !== before;
    W.readTried = true;
    W.readText = got ? `읽은 값(확정 전) — ${divValuesText(divValues())}` : "읽을 수 있는 값이 없었습니다(자리표시뿐인 양식이거나 이미 같은 값)"; // 대시보드 「구성 읽기」 카드의 한 줄(spec_양식표준화 ② §2)
    return got ? { ok: true, text: `문서에서 프로젝트 구성을 읽었습니다(아직 확정 전) — ${divValuesText(divValues())}` }
      : { ok: true, text: "문서에서 읽을 수 있는 프로젝트 구성 값이 없습니다(자리표시뿐인 양식이거나 이미 같은 값) — 값을 입력해야 합니다" };
  }
  if (name === "heads_llm" || name === "tables_llm") { // 양식 표준화 2 · 3단계의 LLM 판정 — 헤딩 추출 「단계별 실행」 과 같은 함수(headsPickRun: l2 = 규칙 보강 → 헤딩 판정 → 서식 계획 · l3 = 표 판정). 실행 카드의 「진행」 이 그 확인이다(opt.asked)
    const id = state.id, epoch = state.epoch;
    await agwHeadsView(); // 단계별 실행이 1단계 결과를 본다(hrpOff)
    if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 시작하지 않았습니다" }; // 그 사이 연 문서에 유료 실행을 걸지 않는다(검토 11-18)
    const r = await headsPickRun([name === "heads_llm" ? "l2" : "l3"], { asked: true });
    await agwStdFresh(); // 다음 턴이 끝난 상태로 센다
    return r ? { ok: !!r.ok, text: r.text } : { ok: false, text: "시작하지 못했습니다 — 알림 글을 보세요(LLM 연결 · 다른 헤딩 작업 · 문단·라벨 결과)" };
  }
  if (name === "heads_apply") { // 조정 「모두 반영」 — 진행 줄 「조정」 의 그 단추와 같은 함수(tpbApply). 카드가 보인 계획의 표시(P.at)를 실어 보낸다 — 그 사이 다시 받은 계획이면 서버가 막는다(409)
    const S = agwStdSteps();
    if (!S || !S.can) return { ok: false, text: "반영할 계획 · 자리 맞춤이 없습니다" };
    const r = await tpbApply(Object.keys(S.P.at).length ? { plans: S.P.at } : {});
    await agwStdFresh();
    return agwStdApplied(r);
  }
  if (name === "config_set") {
    if (!args) return { ok: false, text: "입력한 값이 없습니다" };
    agwConfigApply(args);
    return (await divConfirm({ quiet: true })) ? { ok: true, text: `프로젝트 구성을 확정했습니다 — ${divValuesText(divValues())}` } : { ok: false, text: "프로젝트 구성을 확정하지 못했습니다(알림 글 참고)" };
  }
  if (name === "plan") {
    const ok = await divPlan(), st = divPlanState(), s = st.plan && st.plan.summary;
    if (!ok || !s) return { ok: false, text: (dv.msg && dv.msg.text) || "변경 계획을 세우지 못했습니다(알림 글 참고)" };
    if (st.kind === "same") { const same = divSameText(s); return { ok: same.ok, text: same.text }; }
    const issues = divPlanIssues(s, false);
    return { ok: !issues, text: `변경 계획 — 맞출 자리 ${s.applied}곳 · 항목 추가 ${s.added} · 지움 ${s.removed} · 글 바꿈 ${s.changes} · 지워지는 글 문단 ${s.deleted}${issues ? ` · ${issues}(문서 옆 목록에서 확인이 필요합니다)` : ""}` };
  }
  if (name === "apply") {
    if (!(await divApply({ quiet: true }))) return { ok: false, text: (dv.msg && dv.msg.text) || "반영하지 못했습니다(알림 글 참고)" };
    const left = dv.result && dv.result.unresolved.length;
    return { ok: true, text: `문서에 반영했습니다 — 절 · 표 행 · 표 열을 프로젝트 구성에 맞췄습니다${left ? ` · 미해결 ${left}곳은 손으로 맞춰야 합니다` : ""}(실행 취소로 되돌릴 수 있습니다)` };
  }
  if (name.startsWith("run:")) {
    const id = name.slice(4);
    if (taskIsSingle(agwJob())) { // 문서 하나로 조립한 것 — 서버 쪽 실행기만(workflow_exec.js singleRunServer: 화면 실행으로 가지 않는다). 유료 줄은 카드가 승인한 문서에만(by agent · paid) · 카드가 본 정의일 때만(sig)
      const r = await singleRunServer(id, { paid: (cur && cur.paidIds) || [], sig: (cur && cur.sig) || "", quiet: true });
      return { ok: !!r.ok, text: (r.run && r.full) || r.text };
    }
    if (taskIsRelayFlow(agwJob())) { // 줄 목록으로 조립한 이관형 — 서버 쪽 실행기만(workflow_exec.js relayFlowRun: 화면의 이관 실행 taskRunAll 로 가지 않는다 — 그 정의의 묶음은 거기 없다). 유료 줄 · 정의의 지문은 위와 같다
      const r = await relayFlowRun(id, { paid: (cur && cur.paidIds) || [], sig: (cur && cur.sig) || "", quiet: true });
      return { ok: !!r.ok, text: (r.run && r.full) || r.text };
    }
    if (taskIsGather(agwJob())) {
      const g = GT_STAGES.find((x) => x.id === id), r = await gatherRunStage(id, gatherPlan());
      return { ok: !!r.ok, text: `${g ? g.name : id} — ${r.text}` };
    }
    const not = await taskRunAll(id, id, true, "", "", (cur && cur.paidIds) || []); // true = 확인 창 없이(실행 카드의 「진행」 이 그 확인이다) · 유료 LLM 검증·보완은 카드가 승인한 문서에만(cur = 실행 직전에 다시 센 이 행동 — agentWorkRun)
    if (not && not.ok === false) return { ok: false, text: not.text }; // 시작하지 않음(조립한 워크플로우의 정의가 그 사이 바뀜 · 지워짐 — taskRunAll 이 다시 읽었다): 지난 실행의 끝 글을 이번 것으로 보고하지 않는다
    const g = TASK_STAGES.find((x) => x.id === id), end = taskRunLast;
    return end ? { ok: !!end.ok, text: `${g ? g.name : id} — ${end.text}` } : { ok: false, text: "진행하지 못했습니다(알림 글 참고)" };
  }
  return { ok: false, text: `모르는 행동입니다: ${name}` };
}

// ---------------------------------------------------------------- 턴 · 연쇄
function agwDrawAll(toEnd = false) { agentDrawStatus(); agentDrawTalk(toEnd); agentDrawInput(); }

async function agentWorkTurn(event, x = {}) { // 진행 턴 하나 — 상태를 계산해 보내고 답(턴)을 대화에 더한다 → 턴 | null
  const A = AGENT, epoch = state.epoch;
  if (A.busy || !A.loaded || !A.hwpx || !state.id) return null;
  A.busy = { text: x.show || "", t0: performance.now(), timer: 0, label: AGW_EVENT[event] };
  A.lost = null;
  agwDrawAll(true);
  A.busy.timer = setInterval(() => { if (A !== AGENT || !A.busy || !A.el) return; for (const e of A.el.root.querySelectorAll(".ag-run-text.live")) e.textContent = agentBusyText(A.busy); }, 1000);
  let turn = null, err = null, st = null;
  try {
    st = await agwStatus({ fresh: true });
    if (A === AGENT && epoch === state.epoch) {
      const body = { event, text: x.text || "", steps: st.steps, actions: st.actions, facts: st.facts };
      if (event === "result") Object.assign(body, { ok: x.ok !== false, act: x.act || "" });
      if (x.carry) body.carry = x.carry;
      turn = (await api(agentUrl("/guide"), { method: "POST", headers: H_JSON, body: JSON.stringify(body) })).turn;
    }
  } catch (e) { err = e; }
  clearInterval(A.busy.timer);
  if (A !== AGENT || epoch !== state.epoch) return null;
  A.busy = null;
  if (turn && turn.act && !turn.act.key) { const a = st.actions.find((y) => y.name === turn.act.name); if (a && a.key) turn.act.key = a.key; } // 카드가 가리키는 계획(옛 서버는 key 를 안 돌려준다 — 화면이 붙여 둔다)
  if (turn && turn.ask && Array.isArray(turn.ask.options)) { // 질문 카드의 선택지가 행동이면 카드를 보일 때의 그 행동(key · 유료 · 문서 바뀜)을 적어 둔다 — 고를 때 지금 행동과 견준다(agentWorkAnswer).
    const seen = {}; // 이 화면에만 있다(서버에 안 적음) — 다시 읽은 대화의 카드는 「적어 둔 것이 없는 옛 카드」 다
    for (const o of turn.ask.options) { const a = o && st.actions.find((y) => y.name === o.value); if (a) seen[a.name] = { key: a.key || "", paid: !!a.paid, change: a.change || "none" }; }
    turn.askSeen = seen;
  }
  if (turn) A.turns.push(turn);
  else { A.lost = { text: x.show || "(작업 진행)", error: agentErr(err || new Error("서버가 턴을 돌려주지 않았습니다")) }; if (event === "say" && !A.draft.trim()) A.draft = x.text || ""; }
  agwDrawAll(true);
  if (turn && A.el) { const last = A.el.talk.querySelector(".ag-turn:last-child"); if (last) A.el.talk.scrollTop += last.getBoundingClientRect().top - A.el.talk.getBoundingClientRect().top - 8; }
  if (turn && $("paneAgent").hidden && (turn.ask || agwAsk(turn.act))) toast(`에이전트가 답을 기다립니다 — ${typeof agentFloatOn === "function" && agentFloatOn() ? "상단 바의 에이전트 아이콘을 눌러" : "패널 「에이전트」 에서"} 확인하세요`);
  if (turn && turn.act && !agwAsk(turn.act)) { // 문서가 안 바뀌고 무료인 행동은 바로 실행(연쇄 한도 안에서)
    if (agw().chain < AGW_CHAIN_MAX) agentWorkRun(turn.id);
    else toast("에이전트가 여러 단계를 이어서 했습니다 — 계속하려면 카드의 「진행」 을 누르세요");
  }
  return turn;
}

async function agwClose(t, state_, outcome) { // 카드의 끝(실행함 · 건너뜀 · 답함)을 서버에 적는다 — 못 적어도 화면은 그대로 간다
  Object.assign(t, { state: state_, outcome });
  try { await api(agentUrl(`/guide/${encodeURIComponent(t.id)}`), { method: "PUT", headers: H_JSON, body: JSON.stringify({ state: state_, outcome }) }); } catch { /* 다음에 읽으면 열린 카드로 보인다 */ }
}

async function agentWorkRun(tid, args, fresh = false) { // 턴의 행동을 실행 → 결과 턴. fresh = 사람이 「진행」 을 눌렀다(연쇄를 새로 센다). args = 질문 카드의 값(config_set)
  const A = AGENT, W = agw(), t = agentTurnOf(tid), epoch = state.epoch;
  if (!t || !t.act || t.state !== "open" || W.running || A.busy) return;
  const name = t.act.name;
  if (name === "edit") { await agwClose(t, "done", "편집 에이전트에 넘김"); A.draft = t.text || A.draft; agwDrawAll(); agentSend(true); return; }
  if (agwRunning()) { toast("지금 진행 중인 작업이 끝난 뒤에 누르세요", true); return; } // 같은 문서에 두 실행을 겹치지 않는다(「작업 개요」 의 한 번에 진행 · 간단 모드)
  let cur = null; // 실행 직전에 다시 센 이 행동 — 이관의 「한 번에 진행」 은 그 paidIds(카드가 승인한 유료 호출의 문서)에만 유료 호출을 건다(agwExec)
  if (!args) { // 실행 직전에 다시 센다 — 사람이 누른 카드(fresh)든 저절로 하는 무료 행동이든: 카드를 낸 뒤 상태(계획 · 유료로 부를 문서)가 바뀌었으면 실행하지 않는다.
    // 확인은 그 카드가 보인 계획에 대한 것이다(astra 11-16 P1 — 계획 A 의 카드로 계획 B 를 반영하지 않게) · 답을 기다리는 사이 다른 탭에서 「건너뛰기」 를 풀면 무료였던 행동이 유료 LLM 을 부른다 —
    // 행동 key 에 유료로 부를 문서가 들어 있어(agwRelayStatus) key 가 달라지고, 저절로 하려던 행동이 그 사이 카드로 물을 행동(agwAsk)이 됐으면 저절로 하지 않는다(astra 11-19 P1 ⓑ)
    if (W.checking) return;
    W.checking = true;
    let st = null;
    try { st = await agwStatus({ fresh: true }); cur = st.actions.find((a) => a.name === name) || null; } finally { W.checking = false; }
    if (A !== AGENT || epoch !== state.epoch || t.state !== "open" || W.running || A.busy) return;
    const moved = !cur ? "지금은 할 수 없는 행동입니다(그 사이 상태가 바뀌었습니다)"
      : !fresh && agwAsk(cur) ? "그 사이 유료 LLM 을 부르거나 문서를 바꾸는 일이 되어 카드로 묻습니다"
      : (t.act.key && cur.key ? t.act.key !== cur.key : agwLine(cur.does) !== agwLine(t.act.does)) ? "카드를 낸 뒤 계획이 바뀌었습니다" : "";
    const why = !moved ? "" : (st && st.facts && st.facts.reread) || taskLostWhy(agwJob()) || moved; // 조립한 워크플로우의 정의를 방금 다시 읽었더니 바뀜 · 지워짐(agwStatus) · 전부터 목록에 없음 — 그 까닭으로 말한다
    if (why) {
      await agwClose(t, "skipped", `실행하지 않음 — ${why}`);
      if (A !== AGENT || epoch !== state.epoch) return;
      W.chain = fresh ? 0 : W.chain + 1; // 저절로 하려던 것 — 연쇄 한도 안에서만 다시 묻는다(상태가 자꾸 바뀌어도 되풀이가 끝나게)
      agwDrawAll();
      agentWorkTurn("result", { text: `「${t.act.label}」 ${fresh ? "카드는" : "은 저절로"} 실행하지 않았습니다 — ${why}. 지금 상태로 다시 확인합니다.`, ok: true, act: "" });
      return;
    }
  }
  W.chain = fresh ? 1 : W.chain + 1;
  W.running = { turn: tid, name, t0: performance.now(), timer: setInterval(() => { const e = A.el && A.el.root.querySelector(".agw-run-text"); if (e && W.running) e.textContent = agwRunText(t.act, W.running); }, 1000) };
  agwDrawAll();
  let res;
  try { res = await agwExec(name, args, cur); } catch (e) { console.error(e); res = { ok: false, text: `오류 — ${e.message}` }; }
  clearInterval(W.running.timer);
  W.running = null;
  if (A !== AGENT || epoch !== state.epoch) return;
  await agwClose(t, "done", res.ok ? res.text : `${AGW_HALT}${res.text}`); // 못 끝낸 것을 「실행함」 으로 적지 않는다(카드가 주황 「멈춤」 으로 보인다)
  if (A !== AGENT || epoch !== state.epoch) return;
  agwDrawAll();
  if (!res.silent) agentWorkTurn("result", { text: res.text, ok: res.ok, act: name });
}
const AGW_HALT = "멈춤 — "; // 실행 카드의 끝 글 머리 — 끝까지 못 간 실행(멈춤 · 실패). 저장 값(state)은 done 그대로다(서버 꼴을 바꾸지 않는다)
const agwLine = (s) => { const x = String(s || "").split(/\s+/).filter(Boolean).join(" "); return x.length <= 240 ? x : x.slice(0, 239) + "…"; }; // 서버가 행동 글을 줄이는 꼴과 같게(work_guide._line 240자) — 저장된 카드의 글과 지금 글을 견줄 때
const agwRunText = (a, r) => { // 실행 카드의 도는 글 — 지금 하는 일(그 실행의 note)과 지난 시간
  const R = agwRunning();
  return `${R && R.note && R.note !== "진행 중" ? R.note : `${a.label} — 하는 중`} · ${Math.round((performance.now() - r.t0) / 1000)}초${R && R.stopping ? " · 이 일이 끝나면 멈춥니다" : ""}`;
};

async function agentWorkSkip(tid) { const t = agentTurnOf(tid); if (!t || t.state !== "open" || agw().running) return; await agwClose(t, "skipped", "건너뜀"); agwDrawAll(); }

const AGW_ASK_MOVED = "고른 뒤 계획이 바뀌어 다시 묻습니다"; // 질문 카드에서 고른 행동이 카드를 보일 때와 달라졌다(key · 유료 · 문서 바뀜) — 실행 카드로
const AGW_ASK_PAID = "고른 일은 문서를 바꾸거나 유료 LLM 을 불러 실행 카드로 확인합니다"; // 고른 행동이 유료이거나 문서를 바꾼다 — 선택지에는 유료 꼬리표 · 부를 문서 · 문서 바뀜이 안 보여 고른 것을 승인으로 보지 않는다(실행 카드의 「진행」 이 그 확인)
const AGW_ASK_OLD = "문서를 바꾸거나 유료 LLM 을 부르는 일이라 실행 카드로 다시 묻습니다"; // 같은 까닭 — 카드를 보일 때의 행동을 적어 두지 않은 옛 카드(다시 읽은 대화)
async function agentWorkAnswer(tid, value, label) { // 질문 카드의 답 — 선택지의 값이 행동 이름이면 그 행동을 턴의 행동으로 삼아(유료 · 문서 바뀜 · 카드를 보인 뒤 바뀐 것은 실행 카드로 묻고, 그 밖은 바로 실행), 아니면 답 턴
  const A = AGENT, W = agw(), t = agentTurnOf(tid);
  if (!t || !t.ask || t.state !== "open" || A.busy || W.running || W.checking) return;
  W.checking = true; // 지금 상태를 세는 동안 또 고르거나 「진행」 을 눌러 둘이 돌지 않게
  let st = null;
  try { st = await agwStatus({ fresh: true }); } finally { W.checking = false; }
  if (A !== AGENT || t.state !== "open" || !t.ask) return;
  const act = st ? st.actions.find((a) => a.name === value) : null;
  if (act && act.name === "config_set") { t.ask = { kind: "config", text: "프로젝트 구성을 입력해 주세요", options: [] }; agw().form = null; agwDrawAll(); return; } // 값이 필요한 행동 — 폼으로 바꿔 묻는다
  // 고른 행동을 실행 카드(「진행」 을 눌러야 하는 카드 — agwAsk 의 길)로 묻는 때:
  // ⓐ 카드를 보일 때의 그 행동이 아니다 — 적어 둔 것(agentWorkTurn 의 askSeen: key · 유료 · 문서 바뀜)과 지금 상태로 다시 지은 행동을 견줘
  //    key 가 다르거나(계획 · 유료로 부를 문서 · 조립한 워크플로우의 정의가 바뀜) 그 사이 유료 · 문서를 바꾸는 일이 됐다(AGW_ASK_MOVED)
  // ⓑ 유료이거나 문서를 바꾸는 행동이다 — 적어 둔 것과 같아도(선택지에는 유료 꼬리표 · 부를 문서 · 문서 바뀜이 안 보인다: AGW_ASK_PAID · 적어 둔 것이 없는 옛 카드는 AGW_ASK_OLD).
  // 무료 · 읽기만 · 저장만인 행동은 고른 것이 곧 확인이다 — 바로 한다(그때도 agentWorkRun 이 실행 직전에 다시 센다)
  const seen = act && t.askSeen ? t.askSeen[act.name] : null;
  const moved = !!seen && (seen.key !== (act.key || "") || (!seen.paid && !!act.paid) || (seen.change !== "doc" && act.change === "doc"));
  const ask = !act ? "" : moved ? AGW_ASK_MOVED : act.paid || act.change === "doc" ? (seen ? AGW_ASK_PAID : AGW_ASK_OLD) : "";
  await agwClose(t, "done", ask ? `${label || value} — ${ask}` : label || value);
  if (A !== AGENT) return;
  if (act) { // 사람이 고른 행동 — 그 턴의 행동으로 삼는다: 물을 것이면 실행 카드로만(「진행」 을 누르면 그때 다시 견주고 실행 — agentWorkRun) · 아니면 바로 실행
    const run = { id: t.id, act: { name: act.name, label: act.label, does: act.does, change: act.change, paid: !!act.paid, key: act.key }, state: "open" };
    Object.assign(t, { act: run.act, state: "open", ask: null, outcome: "", ...(ask ? { notes: [...(t.notes || []), ask] } : {}) });
    agwDrawAll();
    if (ask) return;
    return agentWorkRun(t.id, undefined, true);
  }
  agw().chain = 0;
  agwDrawAll();
  agentWorkTurn("answer", { text: label || value, show: label || value });
}

async function agentWorkConfig(tid, values) { // 질문 카드(config)의 「확정」 — 행동 config_set 을 그 값으로 실행
  const t = agentTurnOf(tid);
  if (!t || t.state !== "open" || AGENT.busy || agw().running) return;
  Object.assign(t, { act: { name: "config_set", label: "프로젝트 구성 입력 · 확정", does: "", change: "store", paid: false }, ask: null });
  agw().form = null;
  agentWorkRun(tid, values, true);
}

function agentWorkStart(again = false) { // 시작 턴 — TASK 를 막 시작했거나 「작업 설명」 을 눌렀다. again 이 아니면 같은 TASK 의 진행 턴이 있을 때 다시 부르지 않는다
  const A = AGENT, job = agwJob();
  if (!A.loaded || A.busy || !agwGuided(job)) return;
  if (!again && A.turns.some((t) => t.kind === "guide" && t.job === job)) { agwCarry = null; return; }
  const carry = agwCarry && agwCarry.job === job ? agwCarry.talk : null;
  agwCarry = null;
  agw().chain = 0;
  agentWorkTurn("start", carry ? { carry } : {});
}

function agentWorkSay(text) { // 입력 칸의 글 — 단계가 있는 TASK 에서는 진행 에이전트가 먼저 읽는다(글·표 요청이면 편집 턴으로 넘긴다) → 맡았나
  const A = AGENT;
  if (!agwGuided() || !A.enabled) return false;
  A.draft = "";
  agw().chain = 0;
  agentWorkTurn("say", { text, show: text });
  return true;
}

async function agentWorkEnter(job, entry) { // TASK 를 시작했다(app.js taskEnter) — LLM 을 쓸 수 있거나 첫 화면 대화창에서 시작했으면 에이전트 보기를 열고 시작 턴
  if (!agwGuided(job) || !toolShown("Agent")) { agwCarry = null; return; }
  const id = state.id, epoch = state.epoch;
  let lead = !!(agwCarry && agwCarry.job === job);
  if (!lead) { try { lead = !!(await api("/api/headings/llm")).available; } catch { lead = false; } } // LLM 이 꺼져 있으면 전처럼 그 TASK 의 보기(작업 개요)로 — 에이전트 보기의 「작업 설명」 으로 스크립트 설명을 볼 수 있다
  if (!lead || state.id !== id || state.epoch !== epoch || $("panel").dataset.tool !== entry) return;
  showTab("Agent");
  for (let i = 0; i < 100 && state.epoch === epoch && !(AGENT.loaded && !AGENT.loading); i++) await new Promise((r) => setTimeout(r, 100)); // 에이전트 상태(대화)를 읽을 때까지
  if (state.epoch !== epoch || !AGENT.loaded) return;
  if (agwHold) { agwWait = { id, job }; agwDrawAll(); return; } // 첫 화면의 문서 목록이 아직 준비하는 중(원본·기관 문서 올리기 · 간단 모드) — 끝나면 agentWorkHold(false) 가 시작한다
  agwBegin();
}

// ---------------------------------------------------------------- 그리기(진행 턴)
function agwStepsEl(steps) { // 진행 줄 — 묶음마다 칩 하나(끝남 ✓ · 지금 ● · 남음 ○) + 글
  const ul = el("ul", "agw-steps"), stages = [];
  for (const s of steps || []) { let g = stages.find((x) => x.name === s.stage); if (!g) stages.push((g = { name: s.stage, steps: [] })); g.steps.push(s); }
  for (const g of stages) {
    const real = g.steps.filter((s) => s.state !== "soon"), st = !real.length ? "soon" : real.every((s) => s.state === "done") ? "done" : real.some((s) => s.state === "now") ? "now" : "todo";
    const li = el("li", "agw-step"), now = real.find((s) => s.state === "now");
    li.dataset.state = st;
    li.append(el("span", "agw-mark", st === "done" ? "✓" : st === "now" ? "●" : "○"), el("b", null, g.name || "단계"), el("span", "agw-st", AGW_STATE[st]));
    li.title = g.steps.map((s) => `${AGW_STATE[s.state] || s.state} — ${s.name}${s.text ? ` · ${s.text}` : ""}`).join("\n");
    if (now) li.append(el("span", "agw-now", now.name));
    ul.append(li);
  }
  return ul;
}

function agwTags(a) {
  const box = el("span", "agw-tags");
  box.append(el("span", `agw-tag ${a.change}`, a.change === "doc" ? "문서 바뀜" : a.change === "store" ? "저장만" : "문서 안 바뀜"));
  if (a.paid) box.append(el("span", "agw-tag paid", "LLM 유료"));
  return box;
}

function agwConfigForm(t, on = {}) { // 질문 카드 — 프로젝트 구성 폼(단계 수 · 단계마다 차년도 수 · 주관 · 공동 · 당해 차년도). 처음 값 = 지금 입력 값(dv.values — 문서에서 읽었으면 그 값)
  // on = 다른 보기가 같은 폼을 쓸 때(대시보드 dashboard.js — t.id "dash"): draw() 다시 그리기 · ok(값) 확정. 없으면 에이전트 대화(agentDrawTalk · agentWorkConfig)
  const draw = on.draw || (() => agentDrawTalk()), done = on.ok || ((x) => agentWorkConfig(t.id, x));
  const W = agw(), v =dv.values ? divValues() : { stages: [1], orgs: { lead: "", joint: [] } };
  // 2026-11-18 사용자 「단계, 차년도, 당해년도는 1줄로 되겠지? 공동기관도 , 로 구분하면 될듯 , 확정/문서에서보기,닫기는 한줄로」: 수 셋은 한 줄(.agw-nums — 좁으면 접힘) · 공동기관은 한 줄 칸에 쉼표로(전의 한 줄에 하나 — 줄바꿈 · 「、」 도 받음)
  if (!W.form || W.form.turn !== t.id) W.form = { turn: t.id, stages: [...v.stages], lead: v.orgs.lead || "", joint: (v.orgs.joint || []).join(", "), current: v.current || 1 };
  const F = W.form, box = el("div", "agw-form"), row = (label, ...kids) => { const r = el("label", "agw-row"); r.append(el("span", "agw-lab", label), ...kids); box.append(r); return r; };
  const num = (value, min, max, aria, on) => { const i = el("input"); i.type = "number"; i.min = min; i.max = max; i.value = value; i.setAttribute("aria-label", aria); i.oninput = () => on(Math.max(min, Math.min(max, Number(i.value) || min))); return i; };
  const nums = el("div", "agw-nums"), part = (tag, label, ...kids) => { const g = el(tag, "agw-num"); g.append(el("span", "agw-lab", label), ...kids); nums.append(g); return g; };
  const stages = num(F.stages.length, 1, 10, "단계 수", (n) => { F.stages = Array.from({ length: n }, (_, i) => F.stages[i] || 1); draw(); });
  stages.dataset.agw = "stages";
  stages.onchange = stages.oninput; stages.oninput = null; // 단계 수를 바꾸면 차년도 칸이 다시 그려진다 — 타자 중에는 그리지 않는다
  part("label", "단계 수", stages);
  const years = el("span", "agw-years");
  F.stages.forEach((n, i) => { const y = num(n, 1, 20, `${i + 1}단계 차년도 수`, (x) => { F.stages[i] = x; }); y.dataset.agw = `years${i}`; if (F.stages.length > 1) years.append(el("span", "agw-ylab", `${i + 1}단계`)); years.append(y, el("span", "agw-ylab", "년")); }); // 한 단계면 「1단계」 를 빼 한 줄에 들게
  part("div", "차년도 수", years);
  const cur = num(F.current, 1, 20, "당해 차년도", (x) => { F.current = x; }); cur.dataset.agw = "current";
  part("label", "당해", cur, el("span", "agw-ylab", "차년도"));
  box.append(nums);
  const lead = el("input"); lead.type = "text"; lead.maxLength = 80; lead.value = F.lead; lead.placeholder = "주관연구개발기관 이름"; lead.dataset.agw = "lead"; lead.oninput = () => { F.lead = lead.value; };
  row("주관기관", lead);
  const joint = el("input"); joint.type = "text"; joint.maxLength = 400; joint.value = F.joint; joint.placeholder = "공동연구개발기관 — 쉼표(,)로 나눔 · 없으면 비움"; joint.dataset.agw = "joint"; joint.oninput = () => { F.joint = joint.value; };
  row("공동기관", joint);
  const acts = el("div", "ag-acts agw-form-acts");
  // 단추 글·아이콘 — 2026-11-18 사용자 「확정/문서에서보기,닫기는 한줄로 · 문서에서 보기는 문서 아이콘에 안경이나 눈알… 닫기는 X · 확정도 아이콘」: textContent 는 시험용으로 그대로(.sr-only)
  const read = hBtn("문서에서 보기", async () => { read.disabled = true; await agwExec("config_read"); W.form = null; draw(); }, { title: "문서에 적힌 단계 · 차년도 · 기관을 읽어 이 폼에 채웁니다 — 저장은 「확정」 을 눌러야 합니다" });
  read.dataset.agw = "read";
  read.setAttribute("aria-label", "문서에서 보기");
  read.replaceChildren(agentIcon("read", 15), el("span", "sr-only", "문서에서 보기"));
  const ok = hBtn("확정", () => {
    const total = F.stages.reduce((s, n) => s + n, 0);
    if (!F.lead.trim()) { toast("주관기관 이름을 적어 주세요", true); lead.focus(); return; }
    done({ stages: [...F.stages], lead: F.lead.trim(), joint: F.joint.split(/[,，、\n]/).map((x) => x.trim()).filter(Boolean), current: Math.min(F.current, total) });
  }, { cls: "btn sm primary", title: "이 값을 프로젝트 구성으로 저장(확정)합니다 — 문서는 바뀌지 않습니다" });
  ok.dataset.agw = "confirm";
  ok.prepend(agentIcon("check", 15));
  acts.append(ok, read);
  if (on.close) { // 폼을 닫는 단추도 같은 줄 오른쪽 끝에(대시보드 — 전에는 단계의 단추 줄에 따로 「닫기」)
    const close = hBtn("닫기", () => on.close(), { title: "프로젝트 구성 입력 칸을 닫습니다 — 적던 값은 확정하지 않습니다" });
    close.dataset.agw = "close";
    close.setAttribute("aria-label", "닫기");
    close.replaceChildren(agentIcon("close", 15), el("span", "sr-only", "닫기"));
    acts.append(close);
  }
  box.append(acts);
  return box;
}

function agwAskEl(t) {
  const card = el("div", "ag-card agw-card agw-ask"), a = t.ask, open = t.state === "open" && !AGENT.busy && !agw().running;
  card.dataset.state = t.state;
  card.dataset.ask = a.kind;
  card.append(el("p", "agw-q", a.text));
  if (t.state !== "open") { card.append(el("p", "ag-state", t.state === "skipped" ? "건너뜀" : `답 — ${t.outcome || ""}`)); return card; }
  if (a.kind === "choice") {
    const list = el("div", "agw-opts");
    for (const o of a.options || []) {
      const b = el("button", "agw-opt");
      b.type = "button"; b.disabled = !open; b.dataset.value = o.value;
      b.append(el("b", null, o.label), ...(o.desc ? [el("span", null, o.desc)] : []));
      b.onclick = () => agentWorkAnswer(t.id, o.value, o.label);
      list.append(b);
    }
    card.append(list);
  } else if (a.kind === "text") {
    const row = el("div", "agw-textrow"), inp = el("input"), go = hBtn("답하기", () => { if (inp.value.trim()) agentWorkAnswer(t.id, inp.value.trim(), inp.value.trim()); }, { cls: "btn sm primary", disabled: !open });
    inp.type = "text"; inp.maxLength = 400; inp.disabled = !open; inp.setAttribute("aria-label", a.text);
    inp.onkeydown = (ev) => { if (ev.key === "Enter" && !ev.isComposing && ev.keyCode !== 229) { ev.preventDefault(); go.click(); } };
    row.append(inp, go);
    card.append(row);
  } else card.append(agwConfigForm(t));
  const skip = hBtn("건너뛰기", () => agentWorkSkip(t.id), { title: "이 질문에 답하지 않고 둡니다 — 아래 입력 칸으로 다른 것을 요청할 수 있습니다", disabled: !open });
  skip.classList.add("agw-skip");
  card.append(skip);
  return card;
}

function agwActEl(t) {
  const card = el("div", "ag-card agw-card agw-act"), a = t.act, W = agw(), running = W.running && W.running.turn === t.id, head = el("div", "ag-card-head");
  card.dataset.state = running ? "running" : t.state;
  card.dataset.act = a.name;
  head.append(el("b", null, a.label), agwTags(a));
  card.append(head);
  if (a.does) card.append(el("p", "agw-does", a.does));
  if (running) { // 도는 동안 — 지금 하는 일 · 지난 시간 + (멈출 수 있는 실행이면) 「멈춤」
    const run = el("div", "ag-run"), R = agwRunning();
    run.append(el("span", "ag-spin"), el("span", "agw-run-text", agwRunText(a, W.running)));
    card.append(run);
    if (R && R.stop) { const acts = el("div", "ag-acts"), stop = hBtn(R.stopping ? "멈추는 중…" : "멈춤", () => { R.stop(); agentDrawTalk(); }, { disabled: R.stopping, title: "지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다" }); stop.dataset.agw = "stop"; acts.append(stop); card.append(acts); }
    return card;
  }
  if (t.state === "done") { // 끝까지 못 간 실행(멈춤 · 실패)은 「실행함」 이 아니다 — 주황 「멈춤 — 까닭」
    const bad = String(t.outcome || "").startsWith(AGW_HALT);
    if (bad) card.dataset.state = "halt";
    card.append(el("p", bad ? "ag-state stale" : "ag-state ok", bad ? t.outcome : `실행함 — ${t.outcome || ""}`));
    return card;
  }
  if (t.state === "skipped") { card.append(el("p", "ag-state", t.outcome && t.outcome !== "건너뜀" ? t.outcome : "건너뜀")); return card; }
  const acts = el("div", "ag-acts"), R = agwRunning(), busy = !!AGENT.busy || !!W.running || !!R;
  const go = hBtn("진행", () => agentWorkRun(t.id, undefined, true), { cls: "btn sm primary", disabled: busy,
    title: R ? `지금 진행 중인 작업(${R.label})이 끝나면 누를 수 있습니다` : a.change === "doc" ? (String(a.does || "").includes(AGW_COMMIT_NOTE) // 끝에 확정하는 묶음째 실행(spec_워크플로우 ② §18-24) — 실행 취소 기록은 비고 앞 상태는 확정 기록의 복원
      ? "누르면 문서가 바뀝니다 — 끝나면(멈춤이 아니면) 고친 문단을 확정합니다(앞 상태는 「고친 문단」 탭 확정 기록의 복원)" : "누르면 문서가 바뀝니다 — 실행 취소로 되돌릴 수 있습니다") : a.paid ? "누르면 유료 LLM 호출이 들어갑니다" : "이 행동을 실행합니다" });
  go.dataset.agw = "go";
  const skip = hBtn("건너뛰기", () => agentWorkSkip(t.id), { disabled: !!AGENT.busy || !!W.running });
  skip.dataset.agw = "skip";
  acts.append(go, skip);
  if (a.name === "apply") { const list = hBtn("계획 목록 보기", () => divList(), { title: "문서 옆 열에 바뀔 자리와 지워질 글의 목록을 엽니다 — 「진행」 전에 확인합니다(문서는 안 바뀜)" }); list.dataset.agw = "list"; acts.append(list); }
  card.append(acts);
  return card;
}

// ---------------------------------------------------------------- 진행 카드 — 지금 도는 실행을 에이전트 보기에 보인다(대화의 맨 아래 한 곳 · 저장하지 않는다 — 도는 것의 상태는 화면의 실행 객체가 원본: spec ② §7)
// 에이전트 카드가 시작한 실행은 그 실행 카드가 보인다 — 여기는 그 밖의 실행(첫 화면의 간단 모드 · 「작업 개요」 의 한 번에 진행 · 서식 복사)과, 첫 화면의 문서 목록이 문서를 준비하는 동안. doc_agent.js agentDrawTalk 이 부른다
function agwLiveEl() {
  const R = agwRunning(), wait = !!agwHold && !!agwWait && agwWait.id === state.id;
  if ((AGENT.work && AGENT.work.running) || (!R && !wait)) return null;
  const box = el("section", "ag-turn agw-live"), card = el("div", "ag-card agw-card agw-act"), head = el("div", "ag-card-head"), run = el("div", "ag-run");
  const text = el("span", "agw-live-text", R ? agwLiveText(R) : "문서를 준비하는 중 — 끝나면 설명을 시작합니다");
  card.dataset.state = "running";
  card.dataset.live = R ? R.kind : "prepare";
  head.append(el("b", null, R ? R.label : "워크플로우 준비"));
  text.setAttribute("role", "status");
  run.append(el("span", "ag-spin"), text);
  card.append(head, run);
  if (R) {
    const acts = el("div", "ag-acts");
    if (R.stop) { const stop = hBtn(R.stopping ? "멈추는 중…" : "멈춤", () => { R.stop(); agentDrawTalk(); }, { disabled: R.stopping, title: "지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다" }); stop.dataset.agw = "stop"; acts.append(stop); }
    if (R.kind === "single" || R.kind === "flow") { // 문서 하나로 조립한 워크플로우 · 줄 목록으로 조립한 이관형 — 묶음 › 줄의 진행은 패널 「대시보드」 에 있다(「작업 개요」 에는 그 정의의 묶음이 없다)
      if (toolShown("Dash")) { const d = hBtn("대시보드에서 보기", () => showTab("Dash"), { title: "패널 「대시보드」 의 단계 흐름과 진행 줄을 봅니다 — 에이전트 보기로 돌아오면 이 카드가 이어집니다" }); d.dataset.agw = "detail"; acts.append(d); }
    } else if (R.kind !== "style" && toolShown("Div")) { const div = hBtn("작업 개요에서 보기", () => showTab("Div"), { title: "패널 「작업 개요」 의 단계 목록과 묶음 상태 줄을 봅니다 — 에이전트 보기로 돌아오면 이 카드가 이어집니다" }); div.dataset.agw = "detail"; acts.append(div); }
    if (acts.childNodes.length) card.append(acts);
    if (R.kind === "quick" && !(gqRun && gqRun.uploadOnly)) card.append(el("p", "ag-state", "끝나면 무엇을 넣었고 무엇을 남겼는지 여기서 보고합니다."));
  }
  box.append(card);
  return box;
}
let agwLiveKey = "";
setInterval(() => { // 1초 — 도는 것의 시작·끝을 에이전트 보기가 알아챈다: 시작·끝에서만 다시 그리고, 도는 동안은 글만 바꾼다
  const A = typeof AGENT === "object" ? AGENT : null, E = A && A.el;
  if (!E || !E.root.isConnected || !state.id) { agwLiveKey = ""; return; }
  const R = agwRunning(), key = A.work && A.work.running ? "" : R ? `${R.kind}|${R.label}|${R.stopping}` : agwHold && agwWait ? "prepare" : "";
  if (key !== agwLiveKey) { agwLiveKey = key; agentDrawStatus(); agentDrawTalk(!!key); agentDrawInput(); return; }
  if (!key || !R) return;
  const e = E.root.querySelector(".agw-live-text"), s = agwLiveText(R);
  if (e && e.textContent !== s) e.textContent = s;
}, 1000);

function agentWorkTurnEl(t) { // 진행 턴 — (첫 화면에서 이어 온 말) · 사람의 글 · 에이전트의 말 · 진행 줄 · 질문 카드 | 실행 카드
  const box = el("section", "ag-turn agw-turn"), c = t.call || {}, last = [...AGENT.turns].reverse().find((x) => x.kind === "guide");
  box.dataset.turn = t.id;
  box.dataset.event = t.event;
  for (const m of t.carry || []) box.append(el("p", m.who === "me" ? "ag-q" : "ag-a agw-say", m.text));
  if (t.text) box.append(el("p", "ag-q", t.text));
  if (t.reply) box.append(el("p", "ag-a agw-say agw-reply", t.reply));
  for (const n of t.notes || []) box.append(el("p", "ag-note", n));
  if ((t.steps || []).length && (t.event === "start" || t === last)) { // 진행 줄은 그 턴 때의 것이다 — 지금 상태는 마지막 진행 턴의 줄(앞 턴의 줄에는 「그때」 라고 적는다: astra 11-16 — 저장된 줄을 지금 상태로 읽지 않게)
    const ul = agwStepsEl(t.steps);
    if (t !== last) { ul.classList.add("then"); ul.setAttribute("aria-label", "이 턴 때의 진행 상황"); box.append(el("p", "agw-then", "이 턴 때의 진행 상황")); }
    box.append(ul);
  }
  if (t.ask) box.append(agwAskEl(t)); else if (t.act) box.append(agwActEl(t));
  const meta = el("div", "ag-meta");
  meta.append(el("span", null, [agentWhen(t.at), t.llm ? "" : "스크립트 답(LLM 안 씀)", c.ms != null ? `${(c.ms / 1000).toFixed(1)}초` : "", c.costUsd != null ? `$${Number(c.costUsd).toFixed(3)}` : "", c.model || ""].filter(Boolean).join(" · ")));
  if (t.llm) { const g = hBtn("지침", () => agentGuideOpen(t.id), { title: "이 턴에 보낸 글(계약 · 워크플로우 전체 지도 · 할 일 프롬프트 · 자료)과 LLM 의 답을 문서 옆 열에서 봅니다" }); g.dataset.agGuide = t.id; meta.append(g); }
  box.append(meta);
  return box;
}

function agentWorkEmptyEl() { // 빈 대화 — 단계가 있는 TASK: 설명을 청하는 단추(목록에 없는 조립한 워크플로우의 문서는 진행 에이전트가 맡지 않아 여기 오지 않는다 — agwGuided)
  const box = el("section", "ag-empty agw-empty"), heading = el("div", "ag-empty-heading"), name = (TASK_CATALOG[agwJob()] || {}).name || "이 워크플로우";
  heading.append(agentIcon("document"), el("h2", null, `「${name}」 진행`));
  box.append(heading, el("p", "ag-empty-intro", "에이전트가 이 워크플로우의 사전 준비와 진행 상황을 설명하고, 다음 단계를 제안하고 실행합니다. 문서를 바꾸는 단계는 카드의 「진행」 을 눌러야 실행됩니다."));
  const b = hBtn("작업 설명 듣기", () => agentWorkStart(true), { cls: "btn sm primary", title: "지금 상태로 이 워크플로우의 준비 · 진행 상황 · 다음 단계를 설명합니다" });
  b.dataset.agw = "start";
  box.append(b, el("p", "ag-empty-note", "글·표를 써 달라는 요청은 아래 입력 칸에 적으면 편집 에이전트가 제안을 냅니다."));
  return box;
}

// ---------------------------------------------------------------- 첫 화면 오른쪽 대화창(#homeAgent — spec ② §5)
// 파일은 **왼쪽 문서 목록 하나**(home_files.js hf.files)에만 있다 — 대화창에 놓거나 고른 파일도 그 목록에 든다(2026-11-16: 전에는 대화창이 제 파일을 따로 들어, 대화창에 파일이 있는데 왼쪽은 「문서를 놓아주세요」 였다 — astra).
// 대화창은 그 목록의 안내자다: 목록(파일 · 목적 문서 · 프로젝트)을 보고 TASK 를 정하고, 모자란 것(목적 문서 …)은 목록에서 고르라고 알린다.
// 2026-11-20(spec ② §10 「첫 화면의 대시보드」): 같은 열의 다른 탭에 **대시보드**(#homeDash — home_dash.js)가 있다(처음엔 대화 위 · 같은 날 탭으로 가름 — homeAgentTab). 에이전트가 정한 워크플로우(start:<job>)는 그 대시보드에 고르고(homeAgentAct),
// 문서 준비 · 실행은 대시보드의 단추가 한다(문서 화면으로 넘어가지 않는다) — 전에는 워크플로우 카드와 같은 길(homeFilesGo)로 그 작업을 열었다.
const AGH ={ el: null, talk: [], busy: false, ask: null, gen: 0 }; // gen = 대화 세대(「새 대화」 · 시작) — 늦게 온 답을 버린다
const aghFiles = () => (typeof hf === "object" ? hf.files : []);
const aghSig = () => `${aghFiles().map((f) => `${f.name}:${f.size}`).join("|")}#${typeof hfTarget === "function" ? hfTarget() : -1}`; // 목록의 모습 — 답을 기다리는 사이 목록이 바뀌면 그 답의 행동은 쓰지 않는다(A 를 보고 낸 답으로 B 를 열지 않게)

function homeAgentDraw() {
  const E = AGH.el;
  if (!E) return;
  E.talk.textContent = "";
  if (!AGH.talk.length) E.talk.append(el("p", "agh-hint", "파일을 올리거나 하려는 일을 적어 주세요 — 예: 「사업계획서 초안으로 양식을 맞추고 싶어」. 에이전트가 왼쪽 문서 목록을 보고 워크플로우를 정해 「대시보드」 탭에 고르고, 필요한 것은 물어봅니다. "
    + "문서를 연 뒤에는 사전 준비 · 진행 상황 · 다음 단계를 에이전트가 안내하고, 문서를 바꾸는 단계는 카드에서 확인받습니다."));
  for (const m of AGH.talk) E.talk.append(el("p", m.who === "me" ? "ag-q" : "ag-a agw-say", m.text));
  if (AGH.ask && !AGH.busy) {
    const card = el("div", "ag-card agw-card agw-ask"), list = el("div", "agw-opts");
    card.append(el("p", "agw-q", AGH.ask.text));
    for (const o of AGH.ask.options) {
      const b = el("button", "agw-opt");
      b.type = "button"; b.dataset.value = o.value;
      b.append(el("b", null, o.label), ...(o.desc ? [el("span", null, o.desc)] : []));
      b.onclick = () => { AGH.talk.push({ who: "me", text: o.label }); AGH.ask = null; homeAgentAct(o.value); };
      list.append(b);
    }
    card.append(list);
    E.talk.append(card);
  }
  if (AGH.busy) { const run = el("div", "ag-run"); run.append(el("span", "ag-spin"), el("span", null, "워크플로우를 확인하는 중…")); E.talk.append(run); }
  E.talk.scrollTop = E.talk.scrollHeight;
  E.files.textContent = ""; // 문서 목록의 요약(파일은 왼쪽 목록에 있다 — 빼기 · 목적 문서 · 약칭은 거기서)
  const list = aghFiles(), ti = typeof hfTarget === "function" ? hfTarget() : -1;
  for (const [i, f] of list.slice(0, 4).entries()) { const chip = el("span", "agh-file" + (i === ti ? " target" : ""), f.name); chip.title = i === ti ? `${f.name} — 목적 문서` : f.name; E.files.append(chip); }
  if (list.length > 4) E.files.append(el("span", "agh-file more", `외 ${list.length - 4}개`));
  if (list.length > 1) E.files.append(el("span", "agh-list-note", ti >= 0 ? `목적 문서 「${list[ti].name}」` : "목적 문서를 왼쪽 목록에서 고르세요"));
  E.send.disabled = AGH.busy || (!E.text.value.trim() && !list.length);
  E.text.disabled = AGH.busy;
  if (typeof homeDashDraw === "function") homeDashDraw(); // 탭 「대시보드」 도 같은 문서 목록을 본다(고르기 목록 · 문서 칸 · 「워크플로우 시작」 — home_dash.js: 바뀐 것이 없으면 다시 그리지 않는다)
}

function homeAgentAdd(files) { // 대화창에 놓거나 고른 파일 → 왼쪽 문서 목록에(home_files.js — 받는 형식 · 같은 파일 한 번 · PDF 안내는 그쪽 규칙 그대로)
  if (typeof homeFilesAdd === "function") homeFilesAdd(files);
  homeAgentDraw();
}

// 「start:<job>」 — 그 워크플로우를 **탭 「대시보드」 에 고르고 그 탭을 연다**(home_dash.js homeDashPick — spec ② §10 「첫 화면의 대시보드」 의 「에이전트」, 2026-11-20): 문서 화면으로 넘어가지 않고 아직 아무것도 올리지 않는다.
// 문서 준비는 대시보드의 「워크플로우 시작」(home_files.js homeFilesStart — 검사도 그쪽 것), 문서 화면으로 바로 시작하는 길은 전처럼 왼쪽 워크플로우 카드(homeFilesGo)다. 모자란 것(문서 · 목적 문서)은 목록에서 고르라고 알린다.
// 전(2026-11-15~19)에는 여기서 homeFilesGo 를 불러 그 작업을 문서 화면으로 열었다
async function homeAgentAct(act) {
  const job = String(act || "").replace(/^start:/, ""), list = aghFiles(), say = (text) => { AGH.talk.push({ who: "agent", text }); homeAgentDraw(); };
  if (!job || !TASK_CATALOG[job] || TASK_CATALOG[job].soon || typeof homeDashPick !== "function") { homeAgentDraw(); return; }
  const name = TASK_CATALOG[job].name;
  if (!list.length) { say(`「${name}」 에 쓸 문서를 먼저 올려 주세요 — 이 대화창이나 왼쪽 카드에 놓으면 문서 목록에 듭니다.`); return; }
  if (hfTarget() < 0) { // 둘 이상인데 목적 문서를 안 골랐다 — 잘못 고르면 다른 문서가 바뀌므로 짐작하지 않는다
    say(`문서가 ${list.length}개입니다 — 왼쪽 문서 목록에서 목적 문서(내용을 받는 문서)를 고른 뒤 다시 보내거나 워크플로우 카드 「${name}」 을 누르면 시작합니다.`);
    const r = document.querySelector("#homeFiles input[type=radio]");
    if (r) r.focus();
    return;
  }
  AGH.ask = null;
  if (!homeDashPick(job)) { say("지금은 대시보드에 고르지 못했습니다 — 문서를 준비하는 중이면 끝난 뒤 다시 보내 주세요."); return; } // 대시보드가 「워크플로우 시작」 을 하는 중(그 준비를 다른 워크플로우로 덮지 않는다)
  // 첫 화면에서 나눈 말 — 이 워크플로우를 문서 화면에서 시작할 때(왼쪽 워크플로우 카드 · 연 뒤 에이전트 보기의 「작업 설명 듣기」) 그 시작 턴이 가져간다(파일이 여럿이어도). 「새 대화」 는 이것도 버린다
  agwCarry = { job, talk: AGH.talk.slice(-12) };
  say(`「대시보드」 탭에 「${name}」 ${typeof taskJosa === "function" ? taskJosa(name, "을", "를") : "을"} 골랐습니다 — 그 탭의 「워크플로우 시작」 을 누르면 문서를 준비합니다(문서 화면으로 바로 시작하려면 왼쪽 워크플로우 카드).`); // 이름 뒤 조사는 박아 두지 않는다(task_catalog.js taskJosa)
  homeAgentTab("dash"); // 다음 할 일(「워크플로우 시작」)이 그 탭에 있다 — 이 말은 에이전트 탭에 남는다
}

async function homeAgentSend() {
  const E = AGH.el, text = E.text.value.trim(), list = aghFiles();
  if (AGH.busy || (!text && !list.length)) return;
  const ti = hfTarget(), files = list.map((f, i) => ({ name: f.name, size: f.size, target: i === ti })), history = AGH.talk.slice(-8), gen = AGH.gen, sig = aghSig();
  AGH.talk.push({ who: "me", text: [text, files.length ? `(문서 목록 ${files.map((f) => f.name).join(" · ")})` : ""].filter(Boolean).join(" ") });
  E.text.value = "";
  AGH.busy = true; AGH.ask = null;
  homeAgentDraw();
  let r = null, err = null;
  try { r = await api("/api/agent/guide", { method: "POST", headers: H_JSON, body: JSON.stringify({ text, files, history, list: { target: ti >= 0 ? list[ti].name : "", project: hfNorm(hf.project, 60), auto: !!hf.auto } }) }); } catch (e) { err = e; }
  if (gen !== AGH.gen) return; // 그 사이 「새 대화」 를 했거나 시작했다 — 늦게 온 답은 버린다
  AGH.busy = false;
  if (!r) { AGH.talk.push({ who: "agent", text: `답을 받지 못했습니다: ${err && err.status === 404 && err.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 합니다" : (err && err.message) || "알 수 없는 오류"}` }); homeAgentDraw(); return; }
  if (r.reply) AGH.talk.push({ who: "agent", text: r.reply });
  if (sig !== aghSig()) { AGH.talk.push({ who: "agent", text: "답을 기다리는 사이 문서 목록이 바뀌었습니다 — 지금 목록으로 다시 보내 주세요." }); homeAgentDraw(); return; } // 그 답은 앞 목록을 본 것이다
  AGH.ask = r.ask && r.ask.kind === "choice" ? r.ask : null;
  if (r.act) homeAgentAct(r.act); else homeAgentDraw();
}

function homeAgentReset() { AGH.gen += 1; AGH.talk = []; AGH.ask = null; AGH.busy = false; agwCarry = null; if (AGH.el) AGH.el.text.value = ""; homeAgentDraw(); } // 대화만 지운다(시작 턴에 넘기려던 말도) — 문서 목록은 왼쪽의 「비우기」 · 대시보드는 그 안의 「다른 워크플로우」

// 열의 탭 둘 — 「대시보드」(#homeDash) · 「에이전트」(#homeAgentPane). 2026-11-20 사용자 "워크플로우랑 에이전트는 각각 별도의 탭으로"(전에는 한 열에 위 = 대시보드 · 아래 = 대화로 나눠 둘 다 좁았다).
// 차례 · 이름은 패널 탭과 같다(「대시보드」 가 먼저 — 2026-11-18 「에이전트 보다 대시보드를 앞부분에」). 고른 탭은 이 브라우저에 기억한다(못 쓰면 늘 대시보드부터).
const AGH_TAB_KEY = "nfm.homeTab";
function homeAgentTab(name, focus = false) {
  const E = AGH.el;
  if (!E || !E.tabs[name]) return;
  for (const [k, b] of Object.entries(E.tabs)) { const on = k === name; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; b.classList.toggle("active", on); E.panes[k].hidden = !on; }
  $("homeAgent").dataset.tab = name;
  try { localStorage.setItem(AGH_TAB_KEY, name); } catch { /* 기억만 안 한다 */ }
  if (focus) E.tabs[name].focus();
  if (name === "agent") E.talk.scrollTop = E.talk.scrollHeight;
  else if (typeof homeDashDraw === "function") homeDashDraw();
}

function homeAgentBind() {
  const box = $("homeAgent");
  if (!box || AGH.el) return;
  const E = (AGH.el = {}), bar = el("div", "agh-tabs"), pane = el("div", "agh-pane"), head = el("header", "agh-head"), input = el("div", "agh-input"), row = el("div", "agh-send");
  bar.setAttribute("role", "tablist");
  bar.setAttribute("aria-label", "대시보드 · 에이전트");
  E.tabs = {};
  for (const [k, label, tip] of [["dash", "대시보드", "대시보드 — 워크플로우를 고르고 단계 흐름을 보며 실행"], ["agent", "에이전트", "에이전트 — 파일을 올리거나 하려는 일을 적으면 워크플로우를 정해 줍니다"]]) {
    const b = el("button", null, label);
    b.type = "button"; b.id = k === "dash" ? "homeTabDash" : "homeTabAgent"; b.title = tip;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-controls", k === "dash" ? "homeDash" : "homeAgentPane");
    b.onclick = () => homeAgentTab(k);
    E.tabs[k] = b;
    bar.append(b);
  }
  bar.onkeydown = (ev) => { // 탭 사이 — 왼쪽 · 오른쪽 화살표 · Home · End(초점과 고름이 같이 옮는다)
    const keys = Object.keys(E.tabs), i = keys.findIndex((k) => E.tabs[k] === document.activeElement);
    if (i < 0) return;
    const to = ev.key === "ArrowRight" ? (i + 1) % keys.length : ev.key === "ArrowLeft" ? (i + keys.length - 1) % keys.length : ev.key === "Home" ? 0 : ev.key === "End" ? keys.length - 1 : -1;
    if (to < 0) return;
    ev.preventDefault();
    homeAgentTab(keys[to], true);
  };
  const clear = hBtn("새 대화", () => homeAgentReset(), { title: "이 대화를 지우고 처음부터" });
  head.append(el("span", "agh-sub", "파일을 올리면 작업 절차를 확인해 진행합니다"), clear);
  // 탭 「대시보드」 의 칸(spec ② §10 「첫 화면의 대시보드」 · design.md §20): 여기서는 자리만 만든다 — 그리기 · 실행은 home_dash.js(homeDashDraw: 이 파일보다 뒤에 읽힌다)
  E.dash = el("section", "dash home-dash");
  E.dash.id = "homeDash";
  E.dash.setAttribute("role", "tabpanel");
  E.dash.setAttribute("aria-labelledby", "homeTabDash");
  pane.id = "homeAgentPane";
  pane.setAttribute("role", "tabpanel");
  pane.setAttribute("aria-labelledby", "homeTabAgent");
  E.panes = { dash: E.dash, agent: pane };
  E.talk = el("div", "agh-talk");
  E.talk.setAttribute("role", "log");
  E.talk.setAttribute("aria-label", "에이전트 대화");
  E.files = el("div", "agh-files");
  E.text = el("textarea");
  E.text.rows = 3; E.text.maxLength = 2000; E.text.id = "homeAgentText";
  E.text.placeholder = "하려는 일을 적어 주세요";
  E.text.setAttribute("aria-label", "에이전트에 보낼 글");
  E.text.oninput = () => { E.send.disabled = AGH.busy || (!E.text.value.trim() && !aghFiles().length); };
  E.text.onkeydown = (ev) => { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey) && !ev.isComposing && ev.keyCode !== 229) { ev.preventDefault(); homeAgentSend(); } };
  const pick = hBtn("파일", () => { const i = el("input"); i.type = "file"; i.multiple = true; i.accept = ".hwp,.hwpx,.docx"; i.onchange = () => homeAgentAdd(i.files); i.click(); }, { title: "작업할 문서를 고릅니다(hwp · hwpx · docx) — 왼쪽 문서 목록에 듭니다. 이 대화창에 놓아도 됩니다" });
  pick.dataset.agh = "pick";
  pick.prepend(agentIcon("file"));
  E.send = hBtn("보내기", () => homeAgentSend(), { cls: "btn sm primary", title: "보내기(Ctrl+Enter)" });
  E.send.dataset.agh = "send";
  row.append(pick, el("span", "agh-spacer"), E.send);
  input.append(E.files, E.text, row);
  pane.append(head, E.talk, input);
  box.append(bar, E.dash, pane);
  let tab = "dash";
  try { if (localStorage.getItem(AGH_TAB_KEY) === "agent") tab = "agent"; } catch { /* 늘 대시보드부터 */ }
  homeAgentTab(tab);
  const files = (e) => !!e.dataTransfer && [...e.dataTransfer.types].includes("Files"); // 대화창에 놓은 파일은 여기서 받는다(창의 파일 놓기 — 그냥 열기 — 보다 먼저)
  box.addEventListener("dragover", (e) => { if (!files(e)) return; e.preventDefault(); e.stopPropagation(); box.classList.add("over"); });
  box.addEventListener("dragleave", (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("over"); });
  box.addEventListener("drop", (e) => { if (!files(e)) return; e.preventDefault(); e.stopPropagation(); box.classList.remove("over"); homeAgentAdd(e.dataTransfer.files); });
  homeAgentDraw();
}
homeAgentBind();
