"use strict";
// 워크플로우 실행의 화면 쪽 — 서버 쪽 실행기(app/workflow_exec.py)의 상태 읽기 · 실행 · 멈춤(spec_워크플로우 ② §17-9 「화면 · 대시보드 · 에이전트」 · 끝점은 ② §17-5 「끝점」).
// **첫 화면의 대시보드**(home_dash.js — spec_작업에이전트 ② §10 「첫 화면의 대시보드」)와 **문서 화면**(작업 개요 · 대시보드)이 같이 쓴다 — 두 보기가 같은 서버 상태 · 같은 실행 id 를 본다(따로 세지 않는다).
// 여기는 끝점을 부르고 답의 꼴을 맞추는 일만 한다(그리기 · 단추는 그 보기의 몫). app.js 의 이름: api · H_JSON 둘뿐.
//
// wid = 그 묶음(프로젝트 · 워크플로우 · 라운드)의 **어느 문서든** — 서버가 목적 문서를 찾는다.
// - flowGet(wid) → 지금 상태 {job, sig, docs{target, source}, ready, why, stages[{id, no, name, does, server, steps[…] | null, total, done, left, can, why, paid, change}], run, last} | null(옛 서버 · 그런 작업 없음)
// - flowLive(wid) → 도는 실행의 요약 | null(메모리만 — 확인 폴링) · flowActive(run) = 그 요약이 도는 중인가
// - flowStart(wid, body) → {ok: true, run} | {ok: false, reason, message, run?}(409 — 화면에 message 를 그대로 · busy 면 이미 도는 실행) — body = {from, to?, only?, redo?, where, …}
// - flowStop(wid, n) → 멈춤을 걸었나 · flowSkip(wid, doc, on) → 건너뛴 문서 id 들 | null
// - flowRecord(wid, n) → 실행 기록 하나 | null · flowWatch(wid, n, tick) → 그 실행이 끝날 때까지 1초마다 읽고(tick(요약)) 끝난 기록을 돌려준다
// - flowWord(step) → 단계 상태의 화면 글(끝남 · 건너뜀 · 지금 · 남음 · 진행 중 …) · flowEnd(rec) → {ok, text}(지난 실행의 끝 글 — 「끝남 — …」 · 「남김 — …」 · 「멈춤 — …」 · 「끊김 — …」)
const FLOW_SCREEN = Math.random().toString(36).slice(2, 10); // 이 화면(탭)의 id — 실행 기록의 origin.screen(누가 시작했나: 「다른 화면에서 진행 중」)
const FLOW_WORD = { done: "끝남", now: "지금", todo: "남음", run: "진행 중", blocked: "막힘", failed: "실패" }; // 서버의 st → 화면 글(대시보드 DASH_ST 와 같은 말 — 색에만 기대지 않는다)
const flowUrl = (wid, tail = "") => `/api/works/${encodeURIComponent(wid)}/flow${tail}`;

async function flowGet(wid) {
  try { return await api(flowUrl(wid)); } catch (e) { if (e.status === 404) return null; throw e; }
}

async function flowLive(wid) {
  try { return (await api(flowUrl(wid, "/live"))).run || null; } catch { return null; } // 확인 폴링 — 못 읽으면 도는 것이 없는 것으로(다음 읽기가 바로잡는다)
}

const flowActive = (run) => !!run && run.status === "running";

async function flowStart(wid, body) {
  try {
    const r = await api(flowUrl(wid, "/runs"), { method: "POST", headers: H_JSON, body: JSON.stringify({ screen: FLOW_SCREEN, by: "human", ...body }) });
    if (!r.run) return { ok: false, reason: r.reason || "client", message: r.message || "이 묶음은 아직 문서 화면에서 진행합니다", run: null }; // 서버가 맡지 않는 묶음(200 {run: null}) — 화면이 돈다
    return { ok: true, run: r.run };
  } catch (e) {
    const b = e.body || {};
    if (e.status === 409 && b.reason) return { ok: false, reason: b.reason, message: b.message || e.message, run: b.run || null };
    return { ok: false, reason: e.status === 404 ? "old" : "error", message: e.status === 404 ? "서버가 옛 판입니다 — 서버를 다시 켜야 합니다" : e.message, run: null };
  }
}

async function flowStop(wid, n) {
  try { await api(flowUrl(wid, `/runs/${n}/stop`), { method: "POST" }); return true; } catch { return false; } // 409 = 이미 끝남
}

async function flowSkip(wid, doc, on) {
  try { return (await api(flowUrl(wid, "/skip"), { method: "PUT", headers: H_JSON, body: JSON.stringify({ doc, on: !!on }) })).llmSkip; } catch { return null; }
}

async function flowRecord(wid, n) {
  try { return await api(flowUrl(wid, `/runs/${n}`)); } catch { return null; }
}

async function flowWatch(wid, n, tick = null, every = 1000) { // 끝날 때까지 — 창을 닫아도 서버에서 이어지므로 이 기다림은 보기만이다
  for (;;) {
    const run = await flowLive(wid);
    if (!flowActive(run) || run.n !== n) break;
    if (tick) tick(run);
    await new Promise((r) => setTimeout(r, every));
  }
  return flowRecord(wid, n);
}

function flowWord(step) { // 단계 한 줄의 상태 글 — 「건너뜀」 은 끝난 것이다(LLM 을 쓸 수 없음 · 사람이 건너뜀)
  if (!step) return "";
  if (step.done && step.skipped) return "건너뜀";
  return FLOW_WORD[step.st] || "";
}

function flowEnd(rec) { // 지난 실행의 끝 → {ok, text} | null — 서버가 지은 글 그대로(화면이 다시 짓지 않는다)
  if (!rec || !rec.end) return null;
  return { ok: !!rec.end.ok && rec.status !== "left" ? true : !!rec.end.ok, left: rec.status === "left", text: rec.end.text || "" };
}

const flowBy = (run) => (!run ? "" : (run.origin || {}).screen === FLOW_SCREEN ? "" : (run.origin || {}).by === "agent" ? "에이전트가 시작함" : "다른 화면에서 진행 중"); // 이 화면이 시작하지 않은 실행의 꼬리표

// ---------------------------------------------------------------- 문서 화면 — 「작업 개요」 · 대시보드의 「한 번에 진행」 이 서버 실행을 쓴다(이관형: spec_워크플로우 ② §17-9 「거울」)
// 서버 실행이 돌면 app.js 의 `taskRun` 을 그 실행의 **거울**로 채운다(지금 꼴 stage · report · key · note · t0 · chain + server · n · by) — 단추를 끄는 곳(divRunLocked · projectControlsSync) · 진행 줄(taskStageSync) ·
// 대시보드 · 에이전트의 진행 카드(agwRunning)가 고치지 않아도 따라온다. 멈춤은 거울의 `stop` 을 참으로 두면(지금 단추들이 하는 것) 여기서 서버에 한 번 건다.
// app.js 의 이름: state · taskRun · taskRunLast · taskRunEnds · taskRunKeep · taskStageSync · taskStepsDraw · taskFlowLoad · taskSlots · taskSlotDoc · TASK_STAGES · taskStagesSync · gatherOn · projectControlsSync · toast · TASK_CATALOG · taskCatalogSig.
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { flowRun: "워크플로우 실행" }); // 「기록」 탭의 이름 — 서버가 돈 「한 번에 진행」 의 시작 · 묶음 · 끝(작업 기록 `flowRun`)

async function taskRunFollow(g, plan, report, n, { quiet = false, redo = "", only = "" } = {}) { // 그 실행을 끝까지 따라간다(거울) → {ok, text, run} — 끝나면 단계를 다시 읽고 묶음 상태 줄에 끝 글을 남긴다
  const run = (taskRun = { stage: g.id, report: report.id, key: only || "heads", note: "", t0: Date.now(), stop: false, chain: null, redo, only, paid: null, server: true, n, by: "" });
  taskRunLast = null;
  taskRunEnds = {};
  if (typeof projectControlsSync === "function") projectControlsSync();
  run.timer = setInterval(() => taskStageSync(), 1000); // 지난 시간 — 글만 바꾼다
  taskStageSync();
  let rec = null;
  try {
    rec = await flowWatch(report.id, n, (live) => {
      const now = live.now || {};
      Object.assign(run, { stage: now.stage || run.stage, key: now.key || run.key, note: now.note || "", by: flowBy(live), ...(live.started ? { t0: live.started * 1000 } : {}) });
      if (run.stop && !run.stopSent) { run.stopSent = true; flowStop(report.id, n); } // 「멈춤」 — 지금 하는 일이 끝나면(서버가 멈춘다)
    });
  } finally {
    clearInterval(run.timer);
    if (taskRun === run) taskRun = null;
    if (typeof projectControlsSync === "function") projectControlsSync();
  }
  const same = () => { const s = taskSlots(), now = (s || []).map((k) => taskSlotDoc(k)); return !!s && !gatherOn() && now[0] && now[1] && now[0].id === plan.id && now[1].id === report.id; };
  if (same()) { try { await taskFlowLoad(); if (typeof taskGuidesLoad === "function") await taskGuidesLoad(report); } catch (e) { console.warn(e); } } // 「문서 검토」 의 분석 · LLM 은 문서의 차례를 안 올린다 — 단계 셈의 재료(분석 요약 · 저장한 작성 지침)를 다시 읽는다
  if (!same()) return { ok: false, text: "그 사이 문서 칸이 바뀌었습니다", run: rec };
  taskStepsDraw();
  const E = flowEnd(rec), stage = TASK_STAGES.find((x) => x.id === g.id) || g;
  const end = E ? { ok: E.ok, text: E.text.replace(/^(끝남|남김|멈춤|오류|끊김) — /, "") } : { ok: false, text: "실행 기록을 읽지 못했습니다" };
  taskRunKeep(stage, plan, report, run, end);
  taskStageSync();
  if (!quiet) toast(end.ok ? `${stage.name} — ${end.text}` : `${stage.name}이 멈췄습니다 — ${end.text}`, !end.ok);
  return { ...end, run: rec };
}

// 그 묶음을 서버 쪽 실행기로 시작한다 → {follow()}(서버가 돈다 — follow 가 끝까지 따라가 {ok, text, run} 을 돌려준다) | {ok: false, text}(서버가 거절 — 까닭) |
// null(서버가 맡지 않는 묶음 · 옛 서버 · 끄는 스위치 — 부르는 쪽이 화면 실행으로 간다). paid = 에이전트의 실행 카드가 승인한 문서 id 들(있으면 by agent). 시작(POST)까지만 기다린다 — app.js taskRunAll 이 그동안 겹쳐 누르지 못하게 막는다
async function taskRunServer(g, plan, report, { redo = "", only = "", paid = null } = {}) {
  const cat = TASK_CATALOG[(state.task || {}).job] || {};
  for (const w of [plan, report]) if (typeof taskLlmSkipped === "function" && taskLlmSkipped(w)) await flowSkip(report.id, w.id, true); // 이 브라우저에 기억해 둔 「건너뛰기」 — 서버가 같이 보게(워크플로우 옵션)
  const r = await flowStart(report.id, { from: g.id, only, redo, where: "panel", docs: { target: report.id, source: plan.id }, ...(Array.isArray(paid) ? { by: "agent", paid } : {}),
    ...(cat.custom && typeof taskCatalogSig === "function" && cat.sig ? { sig: cat.sig } : {}) });
  if (!r.ok && (r.reason === "client" || r.reason === "old" || r.reason === "error")) return null; // 화면이 돈다(전과 같다)
  if (!r.ok && r.reason === "busy" && r.run) { toast("다른 화면에서 진행 중입니다 — 그 실행을 따라 보입니다"); return { follow: () => taskRunFollow(g, plan, report, r.run.n, { quiet: true }) }; }
  if (!r.ok) { toast(r.message, true); return { ok: false, text: r.message, run: null }; }
  return { follow: () => taskRunFollow(g, plan, report, r.run.n, { redo, only }) };
}

setInterval(async () => { // 다른 화면 · 첫 화면의 대시보드 · 에이전트가 시작한 서버 실행 — 이 문서가 그 묶음에 들었으면 거울로 따라간다(3초마다 · 메모리만 읽는 확인)
  if (typeof state === "undefined" || !state.id || document.hidden || typeof taskRun === "undefined" || taskRun || (typeof taskRunChecking !== "undefined" && taskRunChecking)) return;
  if (typeof taskSlots !== "function" || !taskSlots() || (typeof gatherOn === "function" && gatherOn()) || (typeof PEEK !== "undefined" && PEEK)) return;
  const id = state.id, live = await flowLive(id);
  if (!flowActive(live) || taskRun || state.id !== id) return;
  const [plan, report] = taskSlots().map((k) => taskSlotDoc(k));
  if (!plan || !report || ((live.docs || {}).target || {}).id !== report.id) return;
  if (typeof taskStagesSync === "function") taskStagesSync();
  const g = TASK_STAGES.find((x) => x.id === ((live.now || {}).stage || (live.range || {}).from));
  if (g) taskRunFollow(g, plan, report, live.n, { quiet: true });
}, 3000);
