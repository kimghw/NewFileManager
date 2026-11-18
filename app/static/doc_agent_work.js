"use strict";
// 작업 진행 에이전트의 화면(spec_작업에이전트 ② §1·§3·§5) — 에이전트 보기(doc_agent.js #paneAgent)에 **진행 턴**을 더하고, 첫 화면 오른쪽에 같은 대화창(#homeAgent)을 둔다.
// 사용자 2026-11-15 "첫 화면 우측에 에이전트 대화할 수 있는 대화창 … 파일 올리면 작업절차를 확인하고 직접 작업을 진행하고 필요한 경우 질문형식으로" ·
//   "task 를 클릭하고 문서를 로드 했을 때 사전준비가 필요한 부분이나 작업진행 사항을 에이전트가 설명하고 진행 … 다음 스테이지도 에이전트가 제안하고 실행".
// 나눔: 에이전트(서버 app/work_guide.py — LLM 또는 스크립트 답)는 **설명하고 고른다**. 단계의 상태(steps)와 지금 할 수 있는 행동(actions)은 이 파일이 화면의 기존 상태에서 계산해 보내고(agwStatus),
//   고른 행동도 이 파일이 기존 함수로 실행한다(agwExec — divPlan · divApply · taskRunAll · gatherRunStage …: 새 실행 길을 만들지 않는다).
// 한 번의 연쇄: 턴(POST …/agent/guide) → 행동이 있으면 ⓐ 문서가 안 바뀌고 무료면 바로 실행 → 결과 턴 ⓑ 문서가 바뀌거나 유료면 실행 카드의 「진행」 을 기다림. 질문 카드는 답을 기다린다. 6턴까지.
// doc_agent.js 다음에 읽힌다(AGENT · agentUrl · agentErr · agentDraw* · agentSend · agentTurnOf · agentWhen · agentIcon). app.js: state · dv · div* · task* · showTab · toolShown · api · el · hBtn · toast · nf · H_JSON · homeTaskStart.

const AGW_STATE = { done: "끝남", now: "지금", todo: "남음", soon: "준비 중" };
const AGW_CHAIN_MAX = 6;
const AGW_EVENT = { start: "작업 절차를 확인하는 중", say: "글을 읽는 중", answer: "답을 읽는 중", result: "다음 단계를 정하는 중" };
let agwCarry = null; // 첫 화면 대화창에서 TASK 를 시작했을 때 넘겨 줄 말 {job, talk[{who, text}]} — 그 작업의 시작 턴이 가져간다
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { agentGuide: "에이전트 작업 진행" }); // 「기록」 탭의 이름

const agw = () => (AGENT.work || (AGENT.work = { chain: 0, running: null, readTried: false, form: null })); // 문서마다(AGENT 와 함께 새로) — running = 도는 행동 {turn, name, t0, timer}
const agwJob = () => (state.task && state.task.job) || "";
const agwFit = (job) => job === "plan_fit" || job === "report_fit";
// 진행 에이전트가 맡는 TASK — 단계가 있고 화면이 상태·행동을 계산할 수 있는 것(양식 맞추기 · 이관 · 취합). 일반 편집은 단계가 없고, 서식 복사는 2열 「서식 복사」 가 그 진행을 맡는다(④)
const agwGuided = (job = agwJob()) => agwFit(job) || job === "plan_to_report" || job === "plan_merge";
const agwAsk = (a) => !!a && (a.change === "doc" || !!a.paid || a.name === "open:target"); // 카드로 물어야 하는 행동(문서가 바뀜 · 유료 LLM · 다른 문서로 옮겨 감 — 원본 문서를 보려고 연 사람을 저절로 목적 문서로 데려가지 않는다)

// ---------------------------------------------------------------- 지금 도는 「한 번에 진행」 — 누가 시작했든(에이전트 카드 · 「작업 내용」 의 단추 · 첫 화면 간단 모드) 에이전트 보기가 한 꼴로 본다(spec ② §7)
// 실행은 TASK 마다 제 상태에 있다(이관 taskRun · 취합 gatherRun · 간단 모드 gqRun · 양식 맞추기 dv.auto · 서식 복사 STYLE.save.auto) — 여기서는 **읽기만** 한다(새 실행 길 · 새 상태를 만들지 않는다).
// 간단 모드(gqRun)와 그 안에서 도는 묶음(gatherRun)은 같은 실행의 부모·자식이다 — 부모를 먼저 본다. 「멈춤」 은 어느 것이든 「지금 하는 일이 끝나면」 이다(바로 끊지 못한다).
function agwRunning() { // → {kind, label, note, t0(Date.now 기준 ms — 0 = 모름), stopping, stop() | null} | null
  if (!state.id) return null;
  const stage = (list, id) => { const g = list.find((x) => x.id === id); return g ? `${g.no} ${g.name}` : ""; };
  const Q = typeof gqRun !== "undefined" ? gqRun : null, G = typeof gatherRun !== "undefined" ? gatherRun : null, T = typeof taskRun !== "undefined" ? taskRun : null;
  if (Q && Q.busy) return { kind: "quick", label: Q.uploadOnly ? "기관 문서 올리기 · 등록" : "간단 모드 — 끝까지 한 번에 진행", note: Q.note || "진행 중", t0: Q.t0, stopping: !!Q.stop,
    stop: () => { Q.stop = true; if (typeof gatherRun !== "undefined" && gatherRun) gatherRun.stop = true; if (typeof gqDraw === "function") gqDraw(); } };
  if (G) return { kind: "gather", label: `${stage(GT_STAGES, G.stage)} — 한 번에 진행`, note: G.note || "진행 중", t0: G.t0, stopping: !!G.stop, stop: () => { G.stop = true; gatherStageSync(); } };
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
function agwCommon(out) { // 어느 TASK 든 — 작업 내용 열기 · 편집 턴으로 넘기기
  out.actions.push({ name: "open:div", label: "패널 「작업 내용」 열기", does: "이 TASK 의 단계 목록과 세부 단추를 직접 봅니다 — 단계마다 확인하며 하거나, 한 번에 진행이 남긴 것을 보정합니다", change: "none" });
  if (AGENT.enabled && AGENT.policy.apply !== false) out.actions.push({ name: "edit", label: "편집 에이전트에 넘기기", does: "글·표를 쓰거나 고쳐 달라는 요청을 편집 에이전트가 받아 제안을 냅니다", change: "none" });
  out.facts.llm = !!AGENT.enabled;
  return out;
}

async function agwFitStatus() { // 양식 맞추기 — 프로젝트 구성 값(확정) → ① 변경 계획 → ② 반영
  if (!dv.view || !dv.values) await divShow();
  const out = { steps: [{ stage: "준비", key: "open", name: "문서 올리기 · 기본 분석", state: "done", text: "" }], actions: [], facts: {} }, v = dv.view;
  if (!v || !dv.values) { out.facts.why = "프로젝트 구성 상태를 읽지 못했습니다"; return agwCommon(out); }
  const values = divValues(), text = divValuesText(values), confirmed = divConfirmValid(dv.values, v.confirmed), why = divRunWhy(), st = divPlanState(), s = st.plan && st.plan.summary;
  const has = !!(values.orgs.lead || values.orgs.joint.length || values.stages.length > 1 || values.stages[0] > 1);
  const same = st.kind === "same" && divSameText(s).ok;
  const applied = st.kind === "done" || same || (st.kind === "none" && !!v.applied && !!v.applied.values && divConfirmKey(v.applied.values) === divConfirmKey(values));
  const issues = s && (st.kind === "ready" || st.kind === "same") ? divPlanIssues(s, false) : "";
  const planText = !s ? "" : st.kind === "stale" || st.kind === "skip" ? "계획이 낡았습니다 — 다시 계획해야 합니다"
    : st.kind === "same" ? divSameText(s).text : `맞출 자리 ${s.applied}곳 · 항목 추가 ${s.added} · 지움 ${s.removed} · 글 바꿈 ${s.changes} · 지워지는 글 문단 ${s.deleted}${issues ? ` · ${issues}` : ""}`;
  const planned = st.kind === "ready" || st.kind === "same" || st.kind === "done";
  out.steps.push({ stage: "프로젝트 구성", key: "values", name: "프로젝트 구성 값 정하기 · 확정", state: confirmed ? "done" : "now", text: confirmed ? text : has ? `입력됨(확정 전) — ${text}` : "아직 값이 없습니다" },
    { stage: "구조 반영", key: "plan", name: "① 변경 계획 보기", state: applied || (confirmed && planned) ? "done" : confirmed ? "now" : "todo", text: planText },
    { stage: "구조 반영", key: "apply", name: "② 반영", state: applied ? "done" : confirmed && st.kind === "ready" ? "now" : "todo", text: applied ? (same ? "이미 프로젝트 구성에 맞습니다" : "문서 구조를 프로젝트 구성에 맞췄습니다") : "" });
  Object.assign(out.facts, { config: has ? text : "", confirmed, plan: planText, supported: !!v.profile.supported });
  if (why) out.facts.why = why;
  if (!confirmed) {
    out.actions.push({ name: "config_read", label: "문서에서 프로젝트 구성 읽기", does: "문서에 적힌 단계 · 차년도 · 기관을 읽어 입력 값으로 가져옵니다(확정은 따로)", change: "none", primary: !has && !agw().readTried });
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
  return agwCommon(out);
}

async function agwRelayStatus() { // 이관 — 묶음(1~4단계)의 단계와 「한 번에 진행」
  if (!dv.view) await divShow();
  try { await taskFlowLoad(); } catch { /* 못 읽은 것은 단계 글에 */ }
  const out = { steps: [], actions: [], facts: {} }, slots = taskSlots(), docs = (slots || []).map((k) => taskSlotDoc(k));
  if (!slots || docs.some((d) => !d)) {
    out.steps.push({ stage: `${TASK_STAGES[0].no} ${TASK_STAGES[0].name}`, key: "files", name: "준비 — 사업계획서 · 연차보고서 고르기", state: "now", text: "두 칸(사업계획서 · 연차보고서)에 문서를 골라야 합니다 — 패널 「작업 내용」 의 첨부 파일 칸" });
    out.facts.why = "사업계획서와 연차보고서가 둘 다 있어야 합니다";
    out.actions.push({ name: "open:div", label: "패널 「작업 내용」 열기", does: "첨부 파일 칸에서 사업계획서와 연차보고서를 고르거나 올립니다", change: "none", primary: true });
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
  // key = 이 카드가 가리키는 일(그 묶음의 남은 단계) — 「진행」 을 누를 때 지금과 견준다(agentWorkRun)
  if (g && !taskRun) out.actions.push({ name: `run:${g.id}`, label: `${g.no} ${g.name} — 한 번에 진행`, does: g.does, change: g.id === "config" ? "store" : "doc", paid: g.id === "map", primary: true,
    key: `${docs.map((d) => d.id).join(">")}:${g.id}:${taskStageWork(g).filter((s) => !s.done).map((s) => s.key).join(",")}` });
  return agwCommon(out);
}

async function agwGatherStatus() { // 취합 — 묶음(1~3단계)의 단계와 「한 번에 진행」
  if (!dv.view) await divShow();
  try { await gatherLoad(); } catch { /* 못 읽은 것은 단계 글에 */ }
  const out = { steps: [], actions: [], facts: {} }, plan = gatherPlan();
  if (!plan) {
    out.steps.push({ stage: `${GT_STAGES[0].no} ${GT_STAGES[0].name}`, key: "files", name: "준비 — 취합본 고르기", state: "now", text: "사업계획서(취합본)를 골라야 합니다 — 패널 「작업 내용」" });
    out.actions.push({ name: "open:div", label: "패널 「작업 내용」 열기", does: "취합본을 고르거나 올립니다", change: "none", primary: true });
    out.facts.llm = !!AGENT.enabled;
    return out;
  }
  const calc = gatherCalc();
  for (const g of GT_STAGES) for (const s of calc.filter((x) => x.stage === g.id)) out.steps.push({ stage: `${g.no} ${g.name}`, key: s.key, name: gatherStepName(s), state: s.st === "done" || s.st === "now" ? s.st : "todo", text: ((s.lines || [])[0] || [])[1] || "" });
  const g = GT_STAGES.find((x) => calc.some((s) => s.stage === x.id && !s.done && s.step !== "files"));
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
  if (g && !gatherRun && !(Q && Q.busy)) out.actions.push({ name: `run:${g.id}`, label: `${g.no} ${g.name} — 한 번에 진행`, does: g.does, change: g.id === "config" ? "store" : "doc", paid: g.id === "map", primary: !out.actions.length,
    key: `${plan.id}:${g.id}:${calc.filter((s) => s.stage === g.id && !s.done).map((s) => s.key).join(",")}` });
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

async function agwStatusOf(job) {
  try {
    if (agwFit(job)) return await agwFitStatus();
    if (job === "plan_to_report") return await agwRelayStatus();
    if (job === "plan_merge") return await agwGatherStatus();
  } catch (e) { console.error(e); return agwCommon({ steps: [], actions: [], facts: { why: `단계 상태를 읽지 못했습니다: ${e.message}` } }); }
  return agwCommon({ steps: [], actions: [], facts: {} });
}
async function agwStatus() { // 도는 것이 있는 동안에는 보기만 — 실행·저장하는 행동을 내지 않는다(같은 문서에 두 실행이 겹치지 않게: 에이전트의 무료 행동은 바로 실행된다)
  const out = await agwStatusOf(agwJob()), R = agwRunning();
  if (R) {
    out.actions = out.actions.filter((a) => a.name === "open:div" || a.name.startsWith("list:"));
    out.facts.running = `${R.label} — ${R.note}`;
  }
  return out;
}

// ---------------------------------------------------------------- 행동 실행 → {ok, text, silent?(결과 턴을 부르지 않음)}
function agwConfigApply(x) { // 질문 카드(config)의 값 → 입력 값(dv.values) — 단계마다 차년도 수 · 주관 · 공동(비영리 표시는 있던 것을 그 길이에 맞춘다) · 당해 차년도
  const v = dv.values, joint = x.joint.slice(0, 30), np = v.orgs.nonprofit || [];
  v.stages = x.stages.map((n) => Math.max(1, Math.min(20, Number(n) || 1)));
  v.orgs.lead = x.lead;
  v.orgs.joint = joint;
  v.orgs.nonprofit = Array.from({ length: joint.length + 1 }, (_, i) => !!np[i]);
  if (x.current > 1) v.current = x.current; else delete v.current;
  divTouched();
  divRender();
}

async function agwExec(name, args) {
  if (name === "open:div") { showTab("Div"); return { ok: true, text: "패널 「작업 내용」 을 열었습니다", silent: true }; }
  if (name === "open:plan") { divList(); return { ok: true, text: "문서 옆 열에 변경 계획 목록을 열었습니다", silent: true }; }
  if (name.startsWith("list:")) { await gatherListOpen(name.slice(5)); return { ok: true, text: "문서 옆 열에 그 기관 문서의 목록을 열었습니다", silent: true }; }
  if (name === "open:target") { // 원본 문서에서 — 목적 문서를 열고 그 문서의 에이전트로 넘긴다(이 대화는 그 문서로 넘어가지 않는다)
    const job = agwJob(), to = job === "plan_merge" ? gatherPlan() : taskSlotDoc("report");
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
    agw().readTried = true;
    return divCanon(divValues()) !== before ? { ok: true, text: `문서에서 프로젝트 구성을 읽었습니다(아직 확정 전) — ${divValuesText(divValues())}` }
      : { ok: true, text: "문서에서 읽을 수 있는 프로젝트 구성 값이 없습니다(자리표시뿐인 양식이거나 이미 같은 값) — 값을 입력해야 합니다" };
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
    if (agwJob() === "plan_merge") {
      const g = GT_STAGES.find((x) => x.id === id), r = await gatherRunStage(id, gatherPlan());
      return { ok: !!r.ok, text: `${g ? g.name : id} — ${r.text}` };
    }
    await taskRunAll(id, id, true); // true = 확인 창 없이(실행 카드의 「진행」 이 그 확인이다)
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
    st = await agwStatus();
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
  if (turn) A.turns.push(turn);
  else { A.lost = { text: x.show || "(작업 진행)", error: agentErr(err || new Error("서버가 턴을 돌려주지 않았습니다")) }; if (event === "say" && !A.draft.trim()) A.draft = x.text || ""; }
  agwDrawAll(true);
  if (turn && A.el) { const last = A.el.talk.querySelector(".ag-turn:last-child"); if (last) A.el.talk.scrollTop += last.getBoundingClientRect().top - A.el.talk.getBoundingClientRect().top - 8; }
  if (turn && $("paneAgent").hidden && (turn.ask || agwAsk(turn.act))) toast("에이전트가 답을 기다립니다 — 패널 「에이전트」 에서 확인하세요");
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
  if (agwRunning()) { toast("지금 진행 중인 작업이 끝난 뒤에 누르세요", true); return; } // 같은 문서에 두 실행을 겹치지 않는다(「작업 내용」 의 한 번에 진행 · 간단 모드)
  if (fresh && !args) { // 사람이 누른 카드 — 카드를 낸 뒤 상태(계획)가 바뀌었으면 실행하지 않는다: 확인은 그 카드가 보인 계획에 대한 것이다(astra 11-16 P1 — 계획 A 의 카드로 계획 B 를 반영하지 않게)
    if (W.checking) return;
    W.checking = true;
    let cur = null;
    try { cur = (await agwStatus()).actions.find((a) => a.name === name) || null; } finally { W.checking = false; }
    if (A !== AGENT || epoch !== state.epoch || t.state !== "open" || W.running || A.busy) return;
    const why = !cur ? "지금은 할 수 없는 행동입니다(그 사이 상태가 바뀌었습니다)"
      : (t.act.key && cur.key ? t.act.key !== cur.key : agwLine(cur.does) !== agwLine(t.act.does)) ? "카드를 낸 뒤 계획이 바뀌었습니다" : "";
    if (why) {
      await agwClose(t, "skipped", `실행하지 않음 — ${why}`);
      if (A !== AGENT || epoch !== state.epoch) return;
      W.chain = 0;
      agwDrawAll();
      agentWorkTurn("result", { text: `「${t.act.label}」 카드는 실행하지 않았습니다 — ${why}. 지금 상태로 다시 확인합니다.`, ok: true, act: "" });
      return;
    }
  }
  W.chain = fresh ? 1 : W.chain + 1;
  W.running = { turn: tid, name, t0: performance.now(), timer: setInterval(() => { const e = A.el && A.el.root.querySelector(".agw-run-text"); if (e && W.running) e.textContent = agwRunText(t.act, W.running); }, 1000) };
  agwDrawAll();
  let res;
  try { res = await agwExec(name, args); } catch (e) { console.error(e); res = { ok: false, text: `오류 — ${e.message}` }; }
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

async function agentWorkAnswer(tid, value, label) { // 질문 카드의 답 — 선택지의 값이 행동 이름이면 그 행동을 실행하고, 아니면 답 턴
  const A = AGENT, t = agentTurnOf(tid);
  if (!t || !t.ask || t.state !== "open" || A.busy || agw().running) return;
  const st = await agwStatus(), act = st.actions.find((a) => a.name === value);
  if (A !== AGENT) return;
  if (act && act.name === "config_set") { t.ask = { kind: "config", text: "프로젝트 구성을 입력해 주세요", options: [] }; agw().form = null; agwDrawAll(); return; } // 값이 필요한 행동 — 폼으로 바꿔 묻는다
  await agwClose(t, "done", label || value);
  if (A !== AGENT) return;
  if (act) { // 사람이 고른 행동 — 그 턴의 행동으로 삼아 바로 실행(고른 것이 곧 확인이다)
    const run = { id: t.id, act: { name: act.name, label: act.label, does: act.does, change: act.change, paid: !!act.paid, key: act.key }, state: "open" };
    Object.assign(t, { act: run.act, state: "open", ask: null, outcome: "" });
    agwDrawAll();
    return agentWorkRun(t.id, undefined, true);
  }
  agw().chain = 0;
  agwDrawAll();
  agentWorkTurn("answer", { text: label || value, show: label || value });
}

async function agentWorkConfig(tid, values) { // 질문 카드(config)의 「이 값으로 확정」 — 행동 config_set 을 그 값으로 실행
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
  if (!lead) { try { lead = !!(await api("/api/headings/llm")).available; } catch { lead = false; } } // LLM 이 꺼져 있으면 전처럼 그 TASK 의 보기(작업 내용)로 — 에이전트 보기의 「작업 설명」 으로 스크립트 설명을 볼 수 있다
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
  if (!W.form || W.form.turn !== t.id) W.form = { turn: t.id, stages: [...v.stages], lead: v.orgs.lead || "", joint: (v.orgs.joint || []).join("\n"), current: v.current || 1 };
  const F = W.form, box = el("div", "agw-form"), row = (label, ...kids) => { const r = el("label", "agw-row"); r.append(el("span", "agw-lab", label), ...kids); box.append(r); return r; };
  const num = (value, min, max, aria, on) => { const i = el("input"); i.type = "number"; i.min = min; i.max = max; i.value = value; i.setAttribute("aria-label", aria); i.oninput = () => on(Math.max(min, Math.min(max, Number(i.value) || min))); return i; };
  const stages = num(F.stages.length, 1, 10, "단계 수", (n) => { F.stages = Array.from({ length: n }, (_, i) => F.stages[i] || 1); draw(); });
  stages.dataset.agw = "stages";
  stages.onchange = stages.oninput; stages.oninput = null; // 단계 수를 바꾸면 차년도 칸이 다시 그려진다 — 타자 중에는 그리지 않는다
  row("단계 수", stages).classList.add("num");
  const years = el("span", "agw-years");
  F.stages.forEach((n, i) => { const y = num(n, 1, 20, `${i + 1}단계 차년도 수`, (x) => { F.stages[i] = x; }); y.dataset.agw = `years${i}`; years.append(el("span", "agw-ylab", `${i + 1}단계`), y, el("span", "agw-ylab", "년")); });
  row("차년도 수", years);
  const lead = el("input"); lead.type = "text"; lead.maxLength = 80; lead.value = F.lead; lead.placeholder = "주관연구개발기관 이름"; lead.dataset.agw = "lead"; lead.oninput = () => { F.lead = lead.value; };
  row("주관기관", lead);
  const joint = el("textarea"); joint.rows = 3; joint.value = F.joint; joint.placeholder = "공동연구개발기관 — 한 줄에 하나(없으면 비움)"; joint.dataset.agw = "joint"; joint.oninput = () => { F.joint = joint.value; };
  row("공동기관", joint);
  const cur = num(F.current, 1, 20, "당해 차년도", (x) => { F.current = x; }); cur.dataset.agw = "current";
  row("당해 차년도", cur, el("span", "agw-ylab", "차년도")).classList.add("num");
  const acts = el("div", "ag-acts");
  const read = hBtn("문서에서 읽기", async () => { read.disabled = true; await agwExec("config_read"); W.form = null; draw(); }, { title: "문서에 적힌 단계 · 차년도 · 기관을 읽어 이 폼에 채웁니다 — 확정은 「이 값으로 확정」" });
  read.dataset.agw = "read";
  const ok = hBtn("이 값으로 확정", () => {
    const total = F.stages.reduce((s, n) => s + n, 0);
    if (!F.lead.trim()) { toast("주관기관 이름을 적어 주세요", true); lead.focus(); return; }
    done({ stages: [...F.stages], lead: F.lead.trim(), joint: F.joint.split("\n").map((x) => x.trim()).filter(Boolean), current: Math.min(F.current, total) });
  }, { cls: "btn sm primary", title: "이 값을 프로젝트 구성으로 저장(확정)합니다 — 문서는 바뀌지 않습니다" });
  ok.dataset.agw = "confirm";
  acts.append(ok, read);
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
    title: R ? `지금 진행 중인 작업(${R.label})이 끝나면 누를 수 있습니다` : a.change === "doc" ? "누르면 문서가 바뀝니다 — 실행 취소로 되돌릴 수 있습니다" : a.paid ? "누르면 유료 LLM 호출이 들어갑니다" : "이 행동을 실행합니다" });
  go.dataset.agw = "go";
  const skip = hBtn("건너뛰기", () => agentWorkSkip(t.id), { disabled: !!AGENT.busy || !!W.running });
  skip.dataset.agw = "skip";
  acts.append(go, skip);
  if (a.name === "apply") { const list = hBtn("계획 목록 보기", () => divList(), { title: "문서 옆 열에 바뀔 자리와 지워질 글의 목록을 엽니다 — 「진행」 전에 확인합니다(문서는 안 바뀜)" }); list.dataset.agw = "list"; acts.append(list); }
  card.append(acts);
  return card;
}

// ---------------------------------------------------------------- 진행 카드 — 지금 도는 실행을 에이전트 보기에 보인다(대화의 맨 아래 한 곳 · 저장하지 않는다 — 도는 것의 상태는 화면의 실행 객체가 원본: spec ② §7)
// 에이전트 카드가 시작한 실행은 그 실행 카드가 보인다 — 여기는 그 밖의 실행(첫 화면의 간단 모드 · 「작업 내용」 의 한 번에 진행 · 서식 복사)과, 첫 화면의 문서 목록이 문서를 준비하는 동안. doc_agent.js agentDrawTalk 이 부른다
function agwLiveEl() {
  const R = agwRunning(), wait = !!agwHold && !!agwWait && agwWait.id === state.id;
  if ((AGENT.work && AGENT.work.running) || (!R && !wait)) return null;
  const box = el("section", "ag-turn agw-live"), card = el("div", "ag-card agw-card agw-act"), head = el("div", "ag-card-head"), run = el("div", "ag-run");
  const text = el("span", "agw-live-text", R ? agwLiveText(R) : "문서를 준비하는 중 — 끝나면 설명을 시작합니다");
  card.dataset.state = "running";
  card.dataset.live = R ? R.kind : "prepare";
  head.append(el("b", null, R ? R.label : "TASK 준비"));
  text.setAttribute("role", "status");
  run.append(el("span", "ag-spin"), text);
  card.append(head, run);
  if (R) {
    const acts = el("div", "ag-acts");
    if (R.stop) { const stop = hBtn(R.stopping ? "멈추는 중…" : "멈춤", () => { R.stop(); agentDrawTalk(); }, { disabled: R.stopping, title: "지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다" }); stop.dataset.agw = "stop"; acts.append(stop); }
    if (R.kind !== "style" && toolShown("Div")) { const div = hBtn("작업 내용에서 보기", () => showTab("Div"), { title: "패널 「작업 내용」 의 단계 목록과 묶음 상태 줄을 봅니다 — 에이전트 보기로 돌아오면 이 카드가 이어집니다" }); div.dataset.agw = "detail"; acts.append(div); }
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
  if (t.llm) { const g = hBtn("지침", () => agentGuideOpen(t.id), { title: "이 턴에 보낸 글(계약 · 워크플로우 · 할 일 프롬프트 · 자료)과 LLM 의 답을 문서 옆 열에서 봅니다" }); g.dataset.agGuide = t.id; meta.append(g); }
  box.append(meta);
  return box;
}

function agentWorkEmptyEl() { // 빈 대화 — 단계가 있는 TASK: 설명을 청하는 단추
  const box = el("section", "ag-empty agw-empty"), heading = el("div", "ag-empty-heading"), name = (TASK_CATALOG[agwJob()] || {}).name || "이 TASK";
  heading.append(agentIcon("document"), el("h2", null, `「${name}」 진행`));
  box.append(heading, el("p", "ag-empty-intro", "에이전트가 이 TASK 의 사전 준비와 진행 상황을 설명하고, 다음 단계를 제안하고 실행합니다. 문서를 바꾸는 단계는 카드의 「진행」 을 눌러야 실행됩니다."));
  const b = hBtn("작업 설명 듣기", () => agentWorkStart(true), { cls: "btn sm primary", title: "지금 상태로 이 TASK 의 준비 · 진행 상황 · 다음 단계를 설명합니다" });
  b.dataset.agw = "start";
  box.append(b, el("p", "ag-empty-note", "글·표를 써 달라는 요청은 아래 입력 칸에 적으면 편집 에이전트가 제안을 냅니다."));
  return box;
}

// ---------------------------------------------------------------- 첫 화면 오른쪽 대화창(#homeAgent — spec ② §5)
// 파일은 **왼쪽 문서 목록 하나**(home_files.js hf.files)에만 있다 — 대화창에 놓거나 고른 파일도 그 목록에 든다(2026-11-16: 전에는 대화창이 제 파일을 따로 들어, 대화창에 파일이 있는데 왼쪽은 「문서를 놓아주세요」 였다 — astra).
// 대화창은 그 목록의 안내자다: 목록(파일 · 목적 문서 · 프로젝트)을 보고 TASK 를 정하고, 모자란 것(목적 문서 …)은 목록에서 고르라고 알린다. 시작은 TASK 카드와 같은 길(homeFilesGo).
const AGH = { el: null, talk: [], busy: false, ask: null, gen: 0 }; // gen = 대화 세대(「새 대화」 · 시작) — 늦게 온 답을 버린다
const aghFiles = () => (typeof hf === "object" ? hf.files : []);
const aghSig = () => `${aghFiles().map((f) => `${f.name}:${f.size}`).join("|")}#${typeof hfTarget === "function" ? hfTarget() : -1}`; // 목록의 모습 — 답을 기다리는 사이 목록이 바뀌면 그 답의 행동은 쓰지 않는다(A 를 보고 낸 답으로 B 를 열지 않게)

function homeAgentDraw() {
  const E = AGH.el;
  if (!E) return;
  E.talk.textContent = "";
  if (!AGH.talk.length) E.talk.append(el("p", "agh-hint", "파일을 올리거나 하려는 일을 적어 주세요 — 예: 「사업계획서 초안으로 양식을 맞추고 싶어」. 에이전트가 왼쪽 문서 목록을 보고 TASK 를 정해 시작하고, 필요한 것은 물어봅니다. "
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
  if (AGH.busy) { const run = el("div", "ag-run"); run.append(el("span", "ag-spin"), el("span", null, "TASK 를 확인하는 중…")); E.talk.append(run); }
  E.talk.scrollTop = E.talk.scrollHeight;
  E.files.textContent = ""; // 문서 목록의 요약(파일은 왼쪽 목록에 있다 — 빼기 · 목적 문서 · 약칭은 거기서)
  const list = aghFiles(), ti = typeof hfTarget === "function" ? hfTarget() : -1;
  for (const [i, f] of list.slice(0, 4).entries()) { const chip = el("span", "agh-file" + (i === ti ? " target" : ""), f.name); chip.title = i === ti ? `${f.name} — 목적 문서` : f.name; E.files.append(chip); }
  if (list.length > 4) E.files.append(el("span", "agh-file more", `외 ${list.length - 4}개`));
  if (list.length > 1) E.files.append(el("span", "agh-list-note", ti >= 0 ? `목적 문서 「${list[ti].name}」` : "목적 문서를 왼쪽 목록에서 고르세요"));
  E.send.disabled = AGH.busy || (!E.text.value.trim() && !list.length);
  E.text.disabled = AGH.busy;
}

function homeAgentAdd(files) { // 대화창에 놓거나 고른 파일 → 왼쪽 문서 목록에(home_files.js — 받는 형식 · 같은 파일 한 번 · PDF 안내는 그쪽 규칙 그대로)
  if (typeof homeFilesAdd === "function") homeFilesAdd(files);
  homeAgentDraw();
}

async function homeAgentAct(act) { // 「start:<job>」 — 그 TASK 로 시작: TASK 카드를 누른 것과 같은 길(homeFilesGo — 목적 문서 · 형식 · 프로젝트 검사도 그쪽 것). 모자란 것은 목록에서 고르라고 알린다
  const job = String(act || "").replace(/^start:/, ""), list = aghFiles(), say = (text) => { AGH.talk.push({ who: "agent", text }); homeAgentDraw(); };
  if (!job || !TASK_CATALOG[job] || TASK_CATALOG[job].soon || typeof homeFilesGo !== "function") { homeAgentDraw(); return; }
  const name = TASK_CATALOG[job].name;
  if (!list.length) { say(`「${name}」 에 쓸 문서를 먼저 올려 주세요 — 이 대화창이나 왼쪽 카드에 놓으면 문서 목록에 듭니다.`); return; }
  if (hfTarget() < 0) { // 둘 이상인데 목적 문서를 안 골랐다 — 잘못 고르면 다른 문서가 바뀌므로 짐작하지 않는다
    say(`문서가 ${list.length}개입니다 — 왼쪽 문서 목록에서 목적 문서(내용을 받는 문서)를 고른 뒤 다시 보내거나 TASK 카드 「${name}」 을 누르면 시작합니다.`);
    const r = document.querySelector("#homeFiles input[type=radio]");
    if (r) r.focus();
    return;
  }
  const gen = (AGH.gen += 1);
  agwCarry = { job, talk: AGH.talk.slice(-12) }; // 첫 화면에서 나눈 말 — 그 작업의 시작 턴이 가져간다(파일이 여럿이어도)
  AGH.ask = null;
  say(`「${name}」 로 시작합니다 — 목적 문서 「${list[hfTarget()].name}」 를 여는 중…`);
  const ok = await homeFilesGo(job);
  if (ok) return;
  if (agwCarry && agwCarry.job === job) agwCarry = null; // 시작하지 못했다(확인 창 취소 · 형식 · 프로젝트 이름 …) — 말은 넘기지 않는다
  if (gen === AGH.gen) say("시작하지 못했습니다 — 왼쪽 문서 목록의 알림을 확인해 주세요(목적 문서 · 파일 형식 · 프로젝트 이름).");
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

function homeAgentReset() { AGH.gen += 1; AGH.talk = []; AGH.ask = null; AGH.busy = false; if (AGH.el) AGH.el.text.value = ""; homeAgentDraw(); } // 대화만 지운다 — 문서 목록은 왼쪽의 「비우기」

function homeAgentBind() {
  const box = $("homeAgent");
  if (!box || AGH.el) return;
  const E = (AGH.el = {}), head = el("header", "agh-head"), title = el("h2", null, "에이전트"), input = el("div", "agh-input"), row = el("div", "agh-send");
  title.prepend(agentIcon("document"));
  const clear = hBtn("새 대화", () => homeAgentReset(), { title: "이 대화를 지우고 처음부터" });
  head.append(title, el("span", "agh-sub", "파일을 올리면 작업 절차를 확인해 진행합니다"), clear);
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
  box.append(head, E.talk, input);
  const files = (e) => !!e.dataTransfer && [...e.dataTransfer.types].includes("Files"); // 대화창에 놓은 파일은 여기서 받는다(창의 파일 놓기 — 그냥 열기 — 보다 먼저)
  box.addEventListener("dragover", (e) => { if (!files(e)) return; e.preventDefault(); e.stopPropagation(); box.classList.add("over"); });
  box.addEventListener("dragleave", (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("over"); });
  box.addEventListener("drop", (e) => { if (!files(e)) return; e.preventDefault(); e.stopPropagation(); box.classList.remove("over"); homeAgentAdd(e.dataTransfer.files); });
  homeAgentDraw();
}
homeAgentBind();
