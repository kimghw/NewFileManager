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
// 문서 화면이 서버 실행을 따라가는 거울 · 3초 확인(고치던 글 보고 · 울타리 알림)은 틀마다 아래 절에: 이관형(taskRunServer · taskRunFollow) · 취합형(gatherRunServer · gatherRunFollow) · 문서 하나로 조립한 것(singleRunServer · singleRunFollow — 맨 아래)
const FLOW_SCREEN = Math.random().toString(36).slice(2, 10); // 이 화면(탭)의 id — 실행 기록의 origin.screen(누가 시작했나: 「다른 화면에서 진행 중」)
const FLOW_WORD = { done: "끝남", now: "지금", todo: "남음", run: "진행 중", blocked: "막힘", failed: "실패" }; // 서버의 st → 화면 글(대시보드 DASH_ST 와 같은 말 — 색에만 기대지 않는다)
const flowUrl = (wid, tail = "") => `/api/works/${encodeURIComponent(wid)}/flow${tail}`;

async function flowGet(wid) {
  try { return await api(flowUrl(wid)); } catch (e) { if (e.status === 404) return null; throw e; }
}

async function flowLive(wid) { // 확인 폴링 — 못 읽으면 도는 것이 없는 것으로(다음 읽기가 바로잡는다). 이 화면이 연 문서면 고치던 글 수를 싣고 울타리 알림을 받는다(spec_워크플로우 ② §17-8)
  const mine = typeof state !== "undefined" && state.id === wid, epoch = mine ? state.epoch : null;
  const ack = mine && flowFence && flowFence.id === wid && flowFence.ready ? flowFence.key : ""; // 받았음 — 입력을 막고 고친 글을 보낸 뒤에만(서버는 이 key 를 되돌린 보고만 센다)
  let r = null;
  try { r = await api(flowUrl(wid, `/live${mine ? `?screen=${FLOW_SCREEN}&dirty=${flowDirty()}${ack ? `&ack=${encodeURIComponent(ack)}` : ""}` : ""}`)); } catch { return null; }
  if (mine && state.id === wid && state.epoch === epoch) flowNoticeSync(wid, r); // 그 사이 다른 문서를 열었으면 그 문서에 띠를 세우지 않는다
  return (r && r.run) || null;
}

// ---------------------------------------------------------------- 울타리(spec_워크플로우 ② §17-8) — 서버 실행이 이 문서를 바꾸는 동안(구조 반영 · 내용 반영 · 작성요령 삭제의 몇 초~20초)
// 알림을 받으면 ① 고치던 글을 보내고(flushAll — 남은 수는 다음 확인에 보고) ② 읽기 전용 띠를 보이고 입력을 막는다 → 알림이 내리면 띠를 걷고, 고치던 글이 없으면 문서를 다시 읽는다(있으면 다시 읽지 않고 알림).
// 서버는 보고한 화면이 모두 0 이 된 뒤에야 울타리를 올리고(사람 편집 409) 문서를 바꾼다 — 10초 안에 0 이 안 되면 문서를 바꾸기 전에 멈춘다.
const flowDirty = () => (typeof state === "undefined" || !state.id ? 0 : (state.timers ? state.timers.size : 0) + (state.inflight || 0) + (state.failed ? state.failed.size : 0)); // 서버에 아직 반영하지 못한 글(보낼 차례 · 보내는 중 · 반영 실패)
let flowFence = null; // 이 화면이 받은 알림 {id(문서), key}
function flowBand(on) { // 읽기 전용 띠(design.md §21) — 문서 위에 한 줄
  let band = document.getElementById("flowFenceBand");
  if (!on) { if (band) band.remove(); document.body.classList.remove("flow-fenced"); return; }
  if (!band) {
    band = document.createElement("div");
    band.id = "flowFenceBand";
    band.className = "flow-fence-band";
    band.setAttribute("role", "status");
    band.textContent = "워크플로우가 이 문서를 바꿉니다 — 고친 글을 반영하는 중 · 끝나면 문서를 다시 읽습니다(그동안 글을 고칠 수 없습니다)";
    document.body.append(band);
  }
  document.body.classList.add("flow-fenced");
}
const flowLastRun = {}; // 문서 id → 이 화면이 본 마지막 실행 번호(그 문서가 목적 문서인 것) — 실행을 통째로 놓쳤는지(숨긴 탭)
function flowNoticeSync(id, r) {
  const n = r && r.notice;
  if (flowFence && flowFence.id !== id) { flowFence = null; flowBand(false); } // 다른 문서의 띠 — 걷는다
  if (n && (!flowFence || flowFence.key !== n.key)) {
    const fence = (flowFence = { id, key: n.key, ready: false });
    flowBand(true); // 입력부터 막는다
    const sent = typeof flushAll === "function" ? flushAll().catch(() => {}) : Promise.resolve();
    sent.finally(() => { fence.ready = true; }); // 고친 글을 보낸 뒤에야 「받았음」 — 다음 확인(1초)이 그 key 와 남은 수를 보고한다
    return;
  }
  const seen = r ? r.lastRun : undefined, missed = seen != null && flowLastRun[id] !== undefined && flowLastRun[id] !== seen; // 이 화면이 모르는 사이 끝난 실행
  if (r && seen !== undefined) flowLastRun[id] = seen;
  if (!n && (flowFence || missed)) {
    const was = flowFence;
    flowFence = null;
    if (typeof state === "undefined" || state.id !== id) { flowBand(false); return; }
    // 문서 하나로 조립한 워크플로우(아래 「문서 하나」 절) — 통째로 놓친 실행(숨긴 탭)은 문서 차례를 안 올리는 것도 바꿨을 수 있다(분석 · LLM 결과 · 확인만 한 반영 기록 · 계획 교체): 끝난 뒤 그것도 다시 읽는다.
    // 도는 실행이 있으면 그 거울(singleRunFollow)이 끝에서 읽는다 — 여기서 겹쳐 읽지 않는다
    const after = () => { if (missed && !(r && r.run && r.run.status === "running") && singleOn() && state.id === id && !(typeof taskRun !== "undefined" && taskRun)) singleAfter(id); };
    if (flowDirty()) { flowBand(false); if (was) toast("워크플로우가 이 문서를 바꿨지만 고치던 글이 있어 문서를 다시 읽지 않았습니다 — 「고친 문단」 탭에서 다시 반영한 뒤 새로 고치세요", true); after(); return; }
    if (r && r.rev != null && r.rev !== state.serverRev) flowReload(id).finally(() => { if (!flowFence) flowBand(false); after(); }); // 다시 읽는 동안에도 띠(입력 막음)는 그대로 — 그 사이 친 글이 새 문서에 덮이지 않게
    else { flowBand(false); after(); }
  }
}
async function flowReload(id) { // 서버 실행이 바꾼 문서를 다시 읽는다(구조 반영 뒤 — divApply 의 reloadDoc 과 같은 길) · 프로젝트 구성 상태도
  try {
    if (state.id !== id || flowDirty()) return; // 읽기 직전에도 — 고치던 글이 있으면 덮지 않는다
    await reloadDoc();
    if (state.id !== id) return;
    if (typeof dv !== "undefined" && dv.plan && dv.plan.baseRev !== state.serverRev) { dv.plan = null; dv.result = null; } // 서버가 반영한 뒤의 옛 계획 — 화면의 계획은 버린다
    if (typeof divShow === "function") await divShow();
    if (typeof taskSlots === "function" && taskSlots() && typeof taskFlowLoad === "function") taskFlowLoad();
  } catch (e) { console.warn(e); }
}
function flowFenceKeys(e) { // 울타리 동안 문서의 입력을 막는다(읽기 · 옮겨 다니기는 그대로) — 서버도 409 로 막는다(이 화면이 그 사이 보낸 글이 「반영 실패」 로 남지 않게 먼저 막는다)
  if (!flowFence || !e.target || !e.target.closest || !e.target.closest("#doc")) return;
  if (e.type === "keydown") {
    const nav = !e.altKey && ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", "Escape", "Shift", "Control", "Alt", "Meta"].includes(e.key); // Alt+↑/↓ 는 개요 레벨을 바꾼다 — 막는다
    const copy = (e.ctrlKey || e.metaKey) && ["c", "a", "f"].includes((e.key || "").toLowerCase());
    if (nav || copy) return;
  }
  e.preventDefault();
  e.stopImmediatePropagation();
}
for (const t of ["beforeinput", "keydown", "paste", "cut", "drop"]) document.addEventListener(t, flowFenceKeys, true);

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

const FLOW_CHAIN = true; // 묶음 연쇄(「이어서 한 번에」)를 서버에 from → to 로 맡길 수 있다(app.js taskRunAll 이 본다 — spec_워크플로우 ② §18-4 「범위의 세 진입」)

async function taskRunFollow(g, plan, report, n, { quiet = false, redo = "", only = "", chain = null } = {}) { // 그 실행을 끝까지 따라간다(거울) → {ok, text, run} — 끝나면 단계를 다시 읽고 묶음 상태 줄에 끝 글을 남긴다 · chain = 연쇄({to, label})
  const first = { review: "heads", frame: redo || "config", map: "link", clean: "guide" }[g.id] || ""; // 첫 확인 전의 단계(화면 taskRunSteps 의 run.key 와 같다) — 다음 확인이 서버의 지금 단계로 바꾼다
  const run = (taskRun = { stage: g.id, report: report.id, key: only || first, note: "", t0: Date.now(), stop: false, chain, redo, only, paid: null, server: true, n, by: "" });
  taskRunLast = null;
  taskRunEnds = {};
  if (typeof projectControlsSync === "function") projectControlsSync();
  run.timer = setInterval(() => taskStageSync(), 1000); // 지난 시간 — 글만 바꾼다
  taskStageSync();
  let rec = null;
  try {
    rec = await flowWatch(report.id, n, (live) => {
      const now = live.now || {};
      const moved = (now.stage || run.stage) !== run.stage || (now.key || run.key) !== run.key || (now.note || "") !== run.note;
      Object.assign(run, { stage: now.stage || run.stage, key: now.key || run.key, note: now.note || "", by: flowBy(live), ...(live.started ? { t0: live.started * 1000 } : {}) });
      if (moved) taskStageSync(); // 단계가 바뀌면 바로 — 상태 줄 · 「진행 중」 표시(화면 실행의 at() 과 같다)
      if (run.stop && !run.stopSent) { run.stopSent = true; flowStop(report.id, n); } // 「멈춤」 — 지금 하는 일이 끝나면(서버가 멈춘다)
    });
  } finally {
    clearInterval(run.timer);
  }
  // 거울(taskRun)은 끝 글을 남기는 그 순간까지 둔다 — 다시 읽기 · 단계 재료 읽기를 기다리는 동안 「!taskRun」 을 보는 쪽(검사 · 에이전트 agwRunning)이 끝 글 없이 끝난 것으로 보지 않게(단추는 그동안 꺼진 채)
  try {
    if (state.id === report.id && !flowDirty()) { // 서버 실행이 이 문서를 바꿨는데(구조 반영 …) 알림을 놓쳤으면 — 끝난 뒤 한 번 견줘 다시 읽는다
      const now = await api(flowUrl(report.id, "/live")).catch(() => null);
      if (now && now.rev != null && now.rev !== state.serverRev && !now.notice) await flowReload(report.id);
    }
    const same = () => { const s = taskSlots(), now = (s || []).map((k) => taskSlotDoc(k)); return !!s && !gatherOn() && now[0] && now[1] && now[0].id === plan.id && now[1].id === report.id; };
    if (same()) { try { await taskFlowLoad(); if (typeof taskGuidesLoad === "function") await taskGuidesLoad(report); } catch (e) { console.warn(e); } } // 「문서 검토」 의 분석 · LLM 은 문서의 차례를 안 올린다 — 단계 셈의 재료(분석 요약 · 저장한 작성 지침)를 다시 읽는다
    if (!same()) return { ok: false, text: "그 사이 문서 칸이 바뀌었습니다", run: rec };
    const E = flowEnd(rec), stage = TASK_STAGES.find((x) => x.id === g.id) || g;
    const end = E ? { ok: E.ok, text: E.text.replace(/^(끝남|남김|멈춤|오류|끊김) — /, "") } : { ok: false, text: "실행 기록을 읽지 못했습니다" };
    if (rec && rec.halt && rec.halt.key) run.key = rec.halt.key; // 멈춘 단계 — 그 줄에 「멈춤」 을 보인다(확인 사이에 끝난 짧은 실행도)
    if (taskRun === run) taskRun = null; // 끝 글과 같은 틈(동기)에 — 사이에 보는 쪽이 없다
    taskStepsDraw();
    if (chain) { // 연쇄 — 서버가 돈 묶음마다 상태 줄에 끝 글을 남긴다(화면 실행 taskRunAll 이 경계마다 남기던 것) · 마지막 묶음이 끝 글 · 알림의 주인
      const done = ((rec && rec.stages) || []).filter((x) => TASK_STAGES.some((y) => y.id === x.id));
      for (const x of done) taskRunKeep(TASK_STAGES.find((y) => y.id === x.id), plan, report, run, { ok: x.status === "done" || x.status === "left", text: x.text || "" });
      const lastG = done.length ? done[done.length - 1] : null, lastStage = lastG ? TASK_STAGES.find((y) => y.id === lastG.id) : stage;
      const steps = (rec && rec.steps) || [], cut = steps.length && steps[steps.length - 1].key === "" && steps[steps.length - 1].status === "left" ? steps[steps.length - 1].text : ""; // 경계에서 앞 묶음이 덜 끝나 멈춘 까닭
      const box = lastStage.dom && document.getElementById(lastStage.dom);
      if (box && !end.ok) box.open = true;
      taskStageSync();
      const lastText = lastG ? lastG.text || "" : end.text;
      if (!quiet) {
        if (!end.ok) toast(`${chain.label} 이어 진행이 ${lastStage.no} 「${lastStage.name}」 에서 멈췄습니다 — ${rec && rec.halt ? rec.halt.text : end.text}`, true);
        else if (cut) toast(`${chain.label} 이어 진행을 ${lastStage.no}까지만 했습니다 — ${cut}`, true);
        else toast(`${chain.label} 이어 진행 끝 — ${lastStage.name}: ${lastText}`);
      }
      return { ok: end.ok, text: lastText, run: rec };
    }
    taskRunKeep(stage, plan, report, run, end);
    const box = stage.dom && document.getElementById(stage.dom);
    if (box && !end.ok) box.open = true; // 멈춘 곳이 보이게 세부 목록을 편다(화면 실행 taskRunAll 과 같다)
    taskStageSync();
    if (!quiet) toast(end.ok ? `${stage.name} — ${end.text}` : `${stage.name}이 멈췄습니다 — ${end.text}`, !end.ok);
    return { ...end, run: rec };
  } finally {
    if (taskRun === run) taskRun = null;
    if (typeof projectControlsSync === "function") projectControlsSync();
  }
}

// 그 묶음을 서버 쪽 실행기로 시작한다 → {follow()}(서버가 돈다 — follow 가 끝까지 따라가 {ok, text, run} 을 돌려준다) | {ok: false, text}(서버가 거절 — 까닭) |
// null(서버가 맡지 않는 묶음 · 옛 서버 · 끄는 스위치 — 부르는 쪽이 화면 실행으로 간다). paid = 에이전트의 실행 카드가 승인한 문서 id 들(있으면 by agent). 시작(POST)까지만 기다린다 — app.js taskRunAll 이 그동안 겹쳐 누르지 못하게 막는다
async function taskRunServer(g, plan, report, { redo = "", only = "", paid = null, to = "", chain = null } = {}) { // to · chain = 묶음 연쇄(「이어서 한 번에」 — 서버가 경계마다 최신 상태로 그 묶음을 할지 정한다)
  const cat = TASK_CATALOG[(state.task || {}).job] || {};
  for (const w of [plan, report]) if (typeof taskLlmSkipped === "function" && taskLlmSkipped(w)) await flowSkip(report.id, w.id, true); // 이 브라우저에 기억해 둔 「건너뛰기」 — 서버가 같이 보게(워크플로우 옵션)
  const ids = TASK_STAGES.map((x) => x.id), i0 = ids.indexOf(g.id), i1 = to ? ids.indexOf(to) : i0;
  const span = i0 >= 0 && i1 >= i0 ? ids.slice(i0, i1 + 1) : [g.id]; // 범위의 묶음들 — 문서를 바꾸는 묶음이 하나라도 들면 화면의 약속을 지킨다
  const changes = span.some((id) => ["frame", "map", "clean"].includes(id)) && only !== "reheads"; // 문서를 바꾸는 묶음(구조 반영 · 내용 반영 · 작성요령 삭제) — 화면의 약속(spec_워크플로우 ② §17-7 「시작」): 고친 글 · 구성 입력을 먼저 서버에
  let skip = [];
  if (changes && (state.id === report.id || state.id === plan.id)) {
    await flushAll();
    if (state.failed.size) { const why = "서버에 반영하지 못한 문단이 있어 시작하지 않았습니다 — 「고친 문단」 탭에서 먼저 다시 반영하세요"; toast(why, true); return { ok: false, text: why, run: null }; }
    if (typeof divSettingsFlush === "function") await divSettingsFlush();
    if (typeof dv !== "undefined" && dv.values && dv.dirty && typeof divCanon === "function" && divCanon(divValues()) !== dv.savedKey) { // 구성 입력을 저장하지 못함(틀린 값 400 은 저장이 조용히 건너뛴다) — 옛 값으로 문서를 바꾸지 않게(astra 2026-11-20)
      const why = "프로젝트 구성 입력 칸의 값을 저장하지 못해 시작하지 않았습니다 — 입력 칸의 값(사업기간 · 차년도 …)을 확인한 뒤 다시 누르세요"; toast(why, true); return { ok: false, text: why, run: null };
    }
    if (state.id === report.id && typeof dv !== "undefined" && dv.skip) skip = [...dv.skip]; // 「반영에서 빼기」 — 화면에만 있던 입력(② §17-11 ⓙ)
  }
  const skill = typeof tpaSkillKey === "function" ? tpaSkillKey() : ""; // 서식 정리 스킬(LLM 검증·보완의 셋째 — 화면 실행 taskRunLlm 과 같다)
  const r = await flowStart(report.id, { from: g.id, ...(span.length > 1 ? { to: span[span.length - 1] } : {}), only, redo, where: "panel", docs: { target: report.id, source: plan.id }, ...(Array.isArray(paid) ? { by: "agent", paid } : {}), ...(skip.length ? { skip } : {}),
    ...(skill ? { skill } : {}), ...(cat.custom && typeof taskCatalogSig === "function" && cat.sig ? { sig: cat.sig } : {}) });
  if (!r.ok && (r.reason === "client" || r.reason === "old")) return null; // 서버가 맡지 않는 묶음 · 옛 서버 — 화면이 돈다(전과 같다)
  if (!r.ok && r.reason === "error") { // 시작 요청의 답을 못 받음 — 서버가 이미 시작했을 수 있어 화면 실행으로 가지 않는다(같은 문서에 두 실행이 걸리지 않게 — astra 2026-11-20)
    const live = await flowLive(report.id);
    if (flowActive(live)) return { follow: () => taskRunFollow(g, plan, report, live.n, { redo, only }) };
    toast(`시작하지 못했습니다 — ${r.message || "서버 응답 없음"} · 다시 누르세요`, true);
    return { ok: false, text: r.message || "서버 응답 없음", run: null };
  }
  if (!r.ok && r.reason === "busy" && r.run) { toast("다른 화면에서 진행 중입니다 — 그 실행을 따라 보입니다"); return { follow: () => taskRunFollow(g, plan, report, r.run.n, { quiet: true }) }; }
  if (!r.ok) { toast(r.message, true); return { ok: false, text: r.message, run: null }; }
  return { follow: () => taskRunFollow(g, plan, report, r.run.n, { redo, only, chain: span.length > 1 ? chain : null }) };
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

// ---------------------------------------------------------------- 취합(걸음 5 — spec_워크플로우 ② §18-13 갈래 「라」) — 「한 번에 진행」 · 간단 모드의 묶음 실행이 서버 실행을 쓴다
// gather.js gatherRunStage 가 묶음을 돌리기 전에 gatherRunServer 로 먼저 묻는다: 서버가 맡으면 gather.js 의 `gatherRun` 을 그 실행의 **거울**로 채워 끝까지 따라가고(진행 줄 · 멈춤 · 끝 글 — gatherRunEnd),
// 맡지 않으면(null) 화면이 전처럼 돈다. 거울 덕에 단추를 끄는 곳(divRunLocked) · 진행 줄(gatherStageSync) · 대시보드 · 에이전트의 진행 카드(agwRunning)는 고치지 않아도 따라온다.
// 따라가는 동안 1초마다의 확인(flowLive)이 이 화면의 고치던 글 수를 서버에 알리고 울타리 알림을 받는다(취합본을 연 화면 — ② §17-8). 실행은 취합본을 열고 있지 않아도 돈다(기관 문서를 보고 있어도 · 창을 닫아도).
// gather.js 의 이름: gatherRun · gatherRunLast · gatherRunEnd · gatherStageSync · gatherLoad · gatherPlan · gatherOn · GT_STAGES. app.js: state · flushAll · divSettingsFlush · divShow · dv · divCanon · divValues · projectControlsSync · toast.
const gatherRunKey = (now) => (now && now.doc && GATHER_EACH_UNITS.includes(now.key) ? `part:${now.doc}` : (now && now.key) || ""); // 서버의 지금 단계 → 화면의 줄 key(기관 문서마다 도는 줄은 문서마다 한 줄 — 묶음 id 가 아니라 줄로 가른다: 취합형으로 조립한 것은 묶음 id 가 g1 …)
const gatherJobNow = () => (typeof state !== "undefined" && state.task && state.task.job) || ""; // 지금 문서의 워크플로우(취합본 · 기관 문서가 같은 묶음이라 같은 값)
const gatherRunStageOf = (now) => gatherScreenStage(now, gatherJobNow()); // 서버의 지금 단계 → 취합 화면의 묶음 id | ""(task_catalog.js — 조립한 것은 줄로 잇는다)

function gatherRunLog(rec, log) { // 간단 모드의 문서별 결과(gather_quick.js gqRowText 가 읽는 log{기관 문서 id: {done | skip | llm}}) — 서버 실행의 줄 기록(steps[].doc)에서
  for (const s of (rec && rec.steps) || []) {
    if (!s.doc) continue;
    const text = s.text && s.text.includes(" — ") ? s.text.slice(s.text.indexOf(" — ") + 3) : s.text || "";
    const row = (log[s.doc] = log[s.doc] || {});
    if (s.key === "apply" && s.status === "done") row.done = text;
    else if (s.key === "llm" && /LLM 검토는 못 함/.test(text)) row.llm = "LLM 검토 못 함"; // LLM 을 쓸 수 없음 · 답을 못 받음 — 스크립트가 넣을 수 있다고 본 것만 넣었다
    else if (s.status === "left") row.skip = text;
  }
}

async function gatherRunFollow(stage, plan, n, opt = {}, first = "") { // 그 실행을 끝까지 따라간다 → 끝 {ok, text}(gatherRunEnd 가 상태 줄 · 알림까지)
  const run = (gatherRun = { stage: stage.id, plan: plan.id, key: first, note: "", t0: Date.now(), stop: false, server: true, n, by: "" });
  gatherRunLast = null;
  if (typeof projectControlsSync === "function") projectControlsSync();
  run.timer = setInterval(() => gatherStageSync(), 1000); // 지난 시간 — 글만 바꾼다
  gatherStageSync();
  let rec = null;
  try {
    rec = await flowWatch(plan.id, n, (live) => {
      const now = live.now || {}, key = gatherRunKey(now) || run.key, at = gatherRunStageOf(now) || run.stage; // at = 화면의 묶음(조립한 것은 서버의 묶음 id 가 다르다)
      const moved = key !== run.key || (now.note || "") !== run.note || at !== run.stage;
      Object.assign(run, { stage: at, key, note: now.note || "", by: flowBy(live), ...(live.started ? { t0: live.started * 1000 } : {}) });
      if (moved) gatherStageSync(); // 단계가 바뀌면 바로 — 상태 줄 · 「진행 중」 표시
      if (run.stop && !run.stopSent) { run.stopSent = true; flowStop(plan.id, n); } // 「멈춤」 — 지금 하는 일이 끝나면(서버가 멈춘다)
    });
  } finally { clearInterval(run.timer); }
  try { // 서버 실행이 취합본을 바꿨는데 알림을 놓쳤으면 끝난 뒤 한 번 견줘 다시 읽는다 · 구성 상태(확정 · 반영)와 취합 상태를 새로
    if (state.id === plan.id && !flowDirty()) {
      // 서버 실행이 프로젝트 구성을 읽어 저장 · 확정했다 — 손대지 않은 입력 칸(dv.values)은 서버의 값을 따른다(divShow 는 저장한 값과 같은 입력만 새로 받는다: 처음의 기본값은 그대로 두므로 비워 준다)
      const keep = typeof dv !== "undefined" && dv ? dv.values : null, view = typeof dv !== "undefined" ? dv : null;
      if (view && !view.dirty) view.values = null;
      const now = await api(flowUrl(plan.id, "/live")).catch(() => null);
      if (now && now.rev != null && now.rev !== state.serverRev && !now.notice) await flowReload(plan.id);
      else if (typeof divShow === "function") await divShow();
      if (view && view === dv && !view.values) { view.values = keep; if (typeof divRender === "function" && keep) divRender(); } // 못 읽었으면 쥐고 있던 값으로
    }
    const cur = gatherPlan();
    if (cur && cur.id === plan.id) await gatherLoad();
  } catch (e) { console.warn(e); }
  const E = flowEnd(rec), end = E ? { ok: E.ok, text: E.text.replace(/^(끝남|남김|멈춤|오류|끊김) — /, "") } : { ok: false, text: "실행 기록을 읽지 못했습니다" };
  const last = ((rec && rec.steps) || []).slice(-1)[0];
  if (rec && rec.halt && rec.halt.key) run.key = gatherRunKey({ stage: rec.halt.stage, key: rec.halt.key, doc: last && last.doc }) || run.key; // 멈춘 단계 — 그 줄에 보인다
  if (opt.log && rec) gatherRunLog(rec, opt.log);
  run.stage = stage.id; // 끝 글은 누른 묶음의 상태 줄에
  return gatherRunEnd(stage, plan, run, end, opt);
}

// 그 묶음을 서버 쪽 실행기로 시작한다 → 끝 {ok, text, none?}(서버가 돌았다 — 끝까지 따라간 뒤) | null(서버가 맡지 않는 묶음 · 옛 서버 · 끄는 스위치 — 부르는 쪽이 화면 실행으로 간다).
// opt = gatherRunStage 의 것: quick(구조 맞춤에 지움이 있으면 멈춤) · auto(Set — 이번에 올린 문서: 미지정이면 반영할 기관을 자동 지정) · llm(false = LLM 검토 안 함) · log · quiet
async function gatherRunServer(stage, plan, opt = {}, first = "") {
  if (state.id === plan.id) { // 화면의 약속(spec_워크플로우 ② §17-7 「시작」) — 고친 글 · 구성 입력을 먼저 서버에(서버 실행은 서버의 문서 · 값으로 돈다)
    await flushAll();
    if (state.failed.size) { const why = "서버에 반영하지 못한 문단이 있어 시작하지 않았습니다 — 「고친 문단」 탭에서 먼저 다시 반영하세요"; if (!opt.quiet) toast(why, true); return { ok: false, text: why }; }
    if (typeof divSettingsFlush === "function") await divSettingsFlush();
    if (typeof dv !== "undefined" && dv.values && dv.dirty && typeof divCanon === "function" && divCanon(divValues()) !== dv.savedKey) {
      const why = "프로젝트 구성 입력 칸의 값을 저장하지 못해 시작하지 않았습니다 — 입력 칸의 값(사업기간 · 차년도 …)을 확인한 뒤 다시 누르세요"; if (!opt.quiet) toast(why, true); return { ok: false, text: why };
    }
  }
  // 취합형으로 조립한 워크플로우 — 화면의 묶음을 그 정의의 묶음으로(지금 할 줄이 든 묶음: task_catalog.js gatherDefStage) · 서버 실행기만 돌린다(화면의 취합 실행은 붙박이의 차례라 그 정의를 모른다: ② §18-12 ⑤)
  const job = gatherJobNow(), made = !!(TASK_CATALOG[job] || {}).custom, from = gatherDefStage(stage.id, job, first);
  if (!from) { const why = `이 워크플로우에는 「${stage.short || stage.name}」 의 줄이 없습니다 — 워크플로우 페이지의 「워크플로우 조립」 에서 줄을 넣거나, 단계별 단추로 진행하세요`; if (!opt.quiet) toast(why, true); return { ok: false, text: why }; }
  const r = await flowStart(plan.id, { from, where: "panel", docs: { target: plan.id }, ...(opt.quick ? { quick: true } : {}), ...(opt.auto && opt.auto.size ? { auto: [...opt.auto] } : {}), ...(opt.llm === false ? { llm: false } : {}) });
  if (!r.ok && (r.reason === "client" || r.reason === "old")) { // 서버가 맡지 않는 묶음 · 옛 서버 — 화면이 돈다(전과 같다) · 조립한 것은 화면이 돌리지 않는다
    if (!made) return null;
    const why = "이 워크플로우는 서버가 돌립니다 — 서버가 이 묶음을 맡지 못했습니다(서버를 새 판으로 켠 뒤 다시 누르세요)"; if (!opt.quiet) toast(why, true); return { ok: false, text: why };
  }
  if (!r.ok && r.reason === "noWork") return { ok: true, text: "남은 단계가 없습니다", none: true };
  let n = r.ok ? r.run.n : 0, quiet = !!opt.quiet;
  if (!r.ok && r.reason === "busy" && r.run) { toast("다른 화면에서 진행 중입니다 — 그 실행을 따라 보입니다"); n = r.run.n; quiet = true; }
  else if (!r.ok && r.reason === "error") { // 시작 요청의 답을 못 받음 — 서버가 이미 시작했을 수 있어 화면 실행으로 가지 않는다(같은 문서에 두 실행이 걸리지 않게)
    const live = await flowLive(plan.id);
    if (!flowActive(live)) { const why = `시작하지 못했습니다 — ${r.message || "서버 응답 없음"} · 다시 누르세요`; toast(why, true); return { ok: false, text: why }; }
    n = live.n;
  } else if (!r.ok) { if (!opt.quiet) toast(r.message, true); return { ok: false, text: r.message }; }
  return gatherRunFollow(stage, plan, n, { ...opt, quiet }, first);
}

setInterval(async () => { // 다른 화면 · 첫 화면의 대시보드가 시작한 취합의 서버 실행 — 이 화면이 그 취합을 보고 있으면 거울로 따라간다(3초마다 · 메모리만 읽는 확인: 고치던 글 보고 · 울타리 알림도 이 확인이 한다)
  if (typeof state === "undefined" || !state.id || document.hidden || typeof gatherOn !== "function" || !gatherOn() || typeof gatherRun === "undefined" || gatherRun || (typeof PEEK !== "undefined" && PEEK)) return;
  if (typeof gatherRunStarting !== "undefined" && gatherRunStarting) return;
  const id = state.id, live = await flowLive(id);
  if (!flowActive(live) || gatherRun || state.id !== id) return;
  const plan = gatherPlan();
  if (!plan || ((live.docs || {}).target || {}).id !== plan.id) return;
  const job = gatherJobNow(), from = (live.range || {}).from; // 화면의 묶음 — 지금 줄로, 아직 없으면 시작한 묶음으로(조립한 것은 정의의 묶음 id 를 화면의 묶음으로 되짚는다)
  const at = gatherRunStageOf(live.now) || ((TASK_CATALOG[job] || {}).custom ? GT_STAGES.map((x) => x.id).find((id) => gatherDefStage(id, job) === from) : from);
  const stage = GT_STAGES.find((x) => x.id === at) || ((TASK_CATALOG[job] || {}).custom ? GT_STAGES[GT_STAGES.length - 1] : null); // 조립한 것 — 화면의 묶음에 없는 줄(사람이 하는 일)에서 도는 중이어도 따라간다
  if (stage) gatherRunFollow(stage, plan, live.n, { quiet: true }, gatherRunKey(live.now));
}, 3000);

// ---------------------------------------------------------------- 문서 하나로 조립한 워크플로우(조립 폼의 「1」 — spec_워크플로우 ② §18-13 걸음 6의 화면 · 2026-11-20 사용자 "그리고 문서 하나는 왜 안되냐?" → 답 「조립한 것만 서버로」)
// 문서 하나로 조립한 워크플로우(task_catalog.js taskIsSingle)의 문서를 연 화면이 서버 실행을 따라간다. **붙박이 문서 하나(사업계획서 양식 표준화 · 연차보고서 양식 맞추기)는 여기 오지 않는다** — 그것은 전처럼 화면이 돈다(divRunAll · headsRunAll …).
// ① 3초마다의 확인(맨 아래 setInterval — flowLive)이 이 화면의 고치던 글 수를 서버에 알리고 울타리 알림을 받는다(읽기 전용 띠 · 고친 글 보내기 · 「받았음」 — 위 flowNoticeSync 그대로: ② §17-8).
//    이 보고가 빠지면 서버가 이 화면을 기다리지 않고 문서를 바꿔 사람이 고치던 글이 덮인다(이관은 taskSlots() · 취합은 gatherOn() 일 때만 확인이 돈다 — 문서 하나는 둘 다 아니다).
// ② 서버 실행이 돌면 app.js 의 `taskRun` 을 그 실행의 **거울**로 채운다(이관의 거울과 같은 변수 + single: true — stage = 그 정의의 묶음 id(g1 …) · key = 지금 줄 · note · t0 · only · by):
//    단추를 끄는 곳(divRunLocked · projectBusy) · 대시보드의 진행 줄 · 에이전트의 진행 카드(doc_agent_work.js agwRunning 의 single 가지)가 따라온다. 멈춤은 거울의 `stop` 을 참으로 두면 여기서 서버에 한 번 건다.
// ③ 실행이 끝나면 다시 읽는다(singleRefresh) — 문서 차례(rev)가 바뀌었으면 문서부터, **안 바뀐 변화**(분석 · LLM 결과 · 구조가 이미 맞아 확인만 한 반영 기록 · 계획 교체)도:
//    프로젝트 구성 패널(입력 값 · 화면의 계획/결과를 서버의 것에 맞춤 — singlePlanSync) · 문서 이름 줄(분석 상태) · 헤딩 요약 · 대시보드의 서버 상태(astra 검토 「화면 연결 전 계약」).
// 실행은 서버 실행기만 돈다 — 화면 실행으로 가지 않는다(서버가 못 맡으면 그 까닭: ② §18-12 ⑤). 묶음의 「한 번에 진행」 · 줄 하나(only) · 「이어서 한 번에」(to)는 대시보드(dashboard.js dashSingleLive)와
// 에이전트(doc_agent_work.js agwSingleStatus · agwExec)가 singleRunServer 로 시작하고, 「작업 개요」 의 「한 번에 진행」(app.js divRunAll)은 singleRunAll 로 온다. 다른 화면 · 첫 화면의 대시보드가 시작한 실행은 3초 확인이 거울로 따라간다.
// app.js 의 이름: state · taskRun · flushAll · divSettingsFlush · divShow · divRender · divRunSync · divFootSync · dv · divCanon · divValues · headsPoll · projectControlsSync · toast · TASK_CATALOG. doc_status.js: docStatusPing. dashboard.js: dashFlowTouch.
const SINGLE_NOT_SERVED = "이 워크플로우는 서버가 돌립니다 — 서버가 이 묶음을 맡지 못했습니다(서버를 새 판으로 켠 뒤 다시 누르세요)"; // 조립한 것은 화면이 돌리지 않는다(취합형으로 조립한 것 — gatherRunServer 와 같은 글)
function singleOn() { // 지금 문서가 문서 하나로 조립한 워크플로우의 문서인가(작업이 저장되는 문서만 — 서버가 그 묶음을 안다 · 같이 보기의 옆 문서 화면은 아니다)
  return typeof state !== "undefined" && !!state.id && !!state.stored && !!state.task && typeof taskIsSingle === "function" && taskIsSingle(state.task.job) && !(typeof PEEK !== "undefined" && PEEK);
}
let singleStarting = false; // 시작 요청(화면의 약속 → POST)을 보내는 중 — 그동안 또 눌러 둘이 시작하지 않게 · 3초 확인이 그 실행을 먼저 따라가지 않게
let singleRunLast = null;   // 이 화면이 끝까지 따라간 마지막 실행의 끝 {id 문서, n, ok, left, text 서버가 지은 끝 글} — 화면 검사 · 에이전트가 읽는다

function singleSync() { // 거울이 서고 내릴 때 — 단추를 끄고 켠다(프로젝트 칸 · 「작업 개요」 의 실행 묶음: 노드는 그대로 두고 글 · 켜짐만)
  if (typeof projectControlsSync === "function") projectControlsSync();
  if (typeof divRunSync === "function") divRunSync();
}

function singlePlanSync() { // 화면의 계획 · 결과(dv.plan · dv.result)를 서버의 것(GET …/divisions 의 plan · applied)에 맞춘다 → 버렸나.
  // 서버 실행은 같은 문서 차례(rev)에서도 계획을 갈고(planId) 구조가 이미 맞으면 확인만 한 반영 기록을 남긴다 — 화면의 옛 계획으로 「② 반영」 을 누르면 409 이고, 옛 「반영 완료」 는 지금 기록이 아니다
  const v = dv.view, p = dv.plan;
  if (!v || !p) return false;
  const stale = dv.result ? !!v.applied && !!v.applied.planId && v.applied.planId !== p.planId : !v.plan || v.plan.planId !== p.planId;
  if (stale) { dv.plan = null; dv.result = null; }
  return stale;
}

async function singleAfter(id) { // 문서 차례를 안 올리는 변화까지 다시 읽는다 — 프로젝트 구성 패널 · 문서 이름 줄(분석 상태) · 헤딩 요약 · 대시보드의 서버 상태. 문서는 건드리지 않는다(고치던 글이 있어도 된다)
  try {
    if (state.id !== id) return;
    const view = typeof dv !== "undefined" ? dv : null;
    if (view && view.view && typeof divShow === "function") { // 「작업 개요」 를 한 번이라도 읽은 문서만(안 읽었으면 열 때 읽는다)
      const keep = view.values;
      if (!view.dirty) view.values = null; // 손대지 않은 입력 칸은 서버의 값을 따른다(서버 실행의 「구성 읽기」 가 입력 값을 저장했을 수 있다 — divShow 는 처음의 기본값을 그대로 두므로 비워 준다: gatherRunFollow 와 같은 길)
      await divShow();
      if (view === dv && !view.values) { view.values = keep; if (typeof divRender === "function" && keep) divRender(); } // 못 읽었으면 쥐고 있던 값으로
      if (view === dv && singlePlanSync()) { if (typeof divRunSync === "function") divRunSync(); if (typeof divFootSync === "function") divFootSync(); }
    }
    if (state.id !== id) return;
    if (typeof docStatusPing === "function") docStatusPing(); // 문서 이름 줄의 분석 상태(헤딩 · 템플릿 · 서식 · 표 · LLM) — 도는 것이 있으면 그쪽이 2초마다 이어 읽는다
    if (state.format !== "docx" && typeof headsPoll === "function") headsPoll(); // 헤딩 요약(헤딩 추출 탭 · 개요 · 여백 표시) — GET 만(추출을 시작하지 않는다 · 도는 헤딩 작업이 있으면 끝날 때까지)
    if (typeof dashFlowTouch === "function") dashFlowTouch(id); // 대시보드가 읽어 둔 서버 상태 — 다시 읽게
  } catch (e) { console.warn(e); }
}

async function singleRefresh(id) { // 실행이 끝난 뒤 — 서버 실행이 이 문서를 바꿨는데 알림을 놓쳤으면 한 번 견줘 문서를 다시 읽고(고치던 글이 있으면 읽지 않는다), 문서 차례를 안 올리는 변화도 따라간다
  try {
    if (state.id === id && !flowDirty()) {
      const now = await api(flowUrl(id, "/live")).catch(() => null);
      if (state.id === id && now && now.rev != null && now.rev !== state.serverRev && !now.notice) await flowReload(id);
    }
  } catch (e) { console.warn(e); }
  await singleAfter(id);
}

async function singleRunFollow(id, n, { quiet = false, stage = "", only = "" } = {}) { // 그 실행을 끝까지 따라간다(거울) → {ok, left, text(머리말을 뗀 끝 글), full(서버가 지은 끝 글 그대로 — 「끝남 — …」 · 「남김 — …」 · 「멈춤 — …」), run(실행 기록)}
  // stage · only = 첫 확인 전에 보일 묶음 · 줄(시작한 범위 — 다음 확인이 서버의 지금 줄로 바꾼다)
  const run = (taskRun = { stage, report: id, key: only, note: "", t0: Date.now(), stop: false, chain: null, redo: "", only, paid: null, server: true, single: true, n, by: "" });
  let away = false, rec = null, miss = 0;
  singleRunLast = null;
  singleSync();
  try {
    for (;;) { // flowWatch 와 같은 고리 + 다른 문서를 열면 거울을 내린다(이관은 같은 묶음의 두 문서를 오가지만 문서 하나는 그 문서뿐이다 — 실행은 서버에서 이어진다)
      const live = await flowLive(id); // 이 확인이 고치던 글 수를 알리고 울타리 알림을 받는다(1초마다)
      if (taskRun !== run || state.id !== id) { away = true; break; }
      if (!flowActive(live) || live.n !== n) {
        rec = await flowRecord(id, n);
        if (rec && rec.status === "running" && live === null && ++miss <= 5 && taskRun === run && state.id === id) { await new Promise((r) => setTimeout(r, 1000)); continue; } // 확인을 못 읽었을 뿐 실행은 돌고 있다 — 거울을 내리지 않는다(몇 번까지)
        break;
      }
      miss = 0;
      const now = live.now || {}, R = live.range || {}, at = now.stage || run.stage || R.from || "", key = now.key || run.key, moved = at !== run.stage || key !== run.key;
      Object.assign(run, { stage: at, key, note: now.note || "", only: R.only || "", by: flowBy(live), ...(live.started ? { t0: live.started * 1000 } : {}) });
      if (moved) { if (typeof docStatusPing === "function") docStatusPing(); if (typeof dashFlowTouch === "function") dashFlowTouch(id); } // 줄이 넘어갔다 — 분석 상태 줄 · 대시보드의 서버 상태(문서 차례를 안 올리는 변화)
      if (run.stop && !run.stopSent) { run.stopSent = true; flowStop(id, n); } // 「멈춤」 — 지금 하는 일이 끝나면(서버가 멈춘다)
      await new Promise((r) => setTimeout(r, 1000));
    }
    if (away) return { ok: false, left: false, text: "다른 문서를 열어 이 실행을 더 따라가지 않습니다 — 실행은 서버에서 이어집니다", full: "", run: null };
    // 거울(taskRun)은 다시 읽기가 끝날 때까지 둔다 — 그동안 「!taskRun」 을 보는 쪽(단추 · 에이전트 · 화면 검사)이 끝 글 없이 끝난 것으로 보지 않게
    if (state.id === id) await singleRefresh(id);
    const E = flowEnd(rec), full = E ? E.text : "실행 기록을 읽지 못했습니다";
    const end = { ok: !!(E && E.ok), left: !!(E && E.left), text: full.replace(/^(끝남|남김|멈춤|오류|끊김) — /, ""), full, run: rec };
    singleRunLast = { id, n, ok: end.ok, left: end.left, text: full };
    if (taskRun === run) taskRun = null; // 끝 글과 같은 틈(동기)에
    singleSync();
    if (typeof dashFlowTouch === "function") dashFlowTouch(id);
    if (!quiet && state.id === id) toast(full, !end.ok);
    return end;
  } finally {
    if (taskRun === run) { taskRun = null; singleSync(); }
  }
}

// 그 묶음을 서버 쪽 실행기로 시작하고 끝까지 따라간다 → 끝 {ok, text, full?, run?, none?}. from = 그 정의의 묶음 id(g1 …) · to = 묶음 연쇄의 끝 묶음(「이어서 한 번에」 — 서버가 경계마다 최신 상태로 그 묶음을 할지 정한다) ·
// only = 그 줄 하나만 · paid = 에이전트의 실행 카드가 승인한 문서 id 들(있으면 by agent — 유료 줄은 그 문서에만) · sig = 이 화면이 본 정의의 지문(그 사이 정의가 바뀌었으면 서버가 시작하지 않는다).
// 조립한 문서 하나는 **화면이 돌리지 않는다** — 서버가 못 맡으면(옛 서버 · 끄는 스위치) 그 까닭을 돌려준다
async function singleRunServer(from, { to = "", only = "", redo = "", paid = null, sig = "", quiet = false } = {}) {
  if (!singleOn()) return { ok: false, text: "문서 하나로 조립한 워크플로우의 문서가 아닙니다" };
  if ((typeof taskRun !== "undefined" && taskRun) || singleStarting) return { ok: false, text: "지금 진행 중인 작업이 끝난 뒤에 누르세요" };
  const id = state.id, epoch = state.epoch, job = state.task.job, cat = TASK_CATALOG[job] || {};
  const say = (why, warn = true) => { if (!quiet) toast(why, warn); return { ok: false, text: why }; };
  singleStarting = true;
  try {
    await flushAll(); // 화면의 약속(spec_워크플로우 ② §17-7 「시작」) — 고친 글 · 구성 입력을 먼저 서버에(서버 실행은 서버의 문서 · 값으로 돈다)
    if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 시작하지 않았습니다" };
    if (state.failed.size) return say("서버에 반영하지 못한 문단이 있어 시작하지 않았습니다 — 「고친 문단」 탭에서 먼저 다시 반영하세요");
    if (typeof divSettingsFlush === "function") await divSettingsFlush();
    if (typeof dv !== "undefined" && dv.values && dv.dirty && typeof divCanon === "function" && divCanon(divValues()) !== dv.savedKey) // 구성 입력을 저장하지 못함(틀린 값 400 은 저장이 조용히 건너뛴다) — 옛 값으로 문서를 바꾸지 않게
      return say("프로젝트 구성 입력 칸의 값을 저장하지 못해 시작하지 않았습니다 — 입력 칸의 값(사업기간 · 차년도 …)을 확인한 뒤 다시 누르세요");
    if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 시작하지 않았습니다" };
    const skip = typeof dv !== "undefined" && dv.skip ? [...dv.skip] : []; // 「반영에서 빼기」 — 화면에만 있는 입력(② §17-11 ⓙ): 구조 반영 줄이 그 자리를 뺀다
    const skill = typeof tpaSkillKey === "function" ? tpaSkillKey() : ""; // 서식 정리 스킬(헤딩 LLM 판정이 이어서 받는 서식 정리 계획)
    const r = await flowStart(id, { from, ...(to && to !== from ? { to } : {}), ...(only ? { only } : {}), ...(redo ? { redo } : {}), where: "panel", docs: { target: id },
      ...(Array.isArray(paid) ? { by: "agent", paid } : {}), ...(skip.length ? { skip } : {}), ...(skill ? { skill } : {}), ...(sig || cat.sig ? { sig: sig || cat.sig } : {}) });
    if (!r.ok && (r.reason === "client" || r.reason === "old")) return say(SINGLE_NOT_SERVED); // 서버가 맡지 않는 묶음 · 옛 서버 — 화면 실행으로 가지 않는다
    if (!r.ok && r.reason === "noWork") return { ok: true, text: "남은 단계가 없습니다", none: true };
    let n = r.ok ? r.run.n : 0, q = quiet;
    if (!r.ok && r.reason === "busy" && r.run) { toast("다른 화면에서 진행 중입니다 — 그 실행을 따라 보입니다"); n = r.run.n; q = true; }
    else if (!r.ok && r.reason === "error") { // 시작 요청의 답을 못 받음 — 서버가 이미 시작했을 수 있다: 도는 실행이 있으면 그것을 따라간다
      const live = await flowLive(id);
      if (!flowActive(live)) return say(`시작하지 못했습니다 — ${r.message || "서버 응답 없음"} · 다시 누르세요`);
      n = live.n;
    } else if (!r.ok) {
      if (r.reason === "definition" && typeof taskCatalogRefresh === "function") taskCatalogRefresh(job); // 그 사이 정의가 바뀌었다 — 목록 · 단계 흐름을 새 정의로 다시 읽는다(대시보드도)
      return say(r.message || "시작하지 못했습니다");
    }
    if (state.id !== id) return { ok: false, text: "다른 문서를 열었습니다 — 실행은 서버에서 이어집니다" };
    return singleRunFollow(id, n, { quiet: q, stage: from, only }); // 거울(taskRun)이 선 뒤에 singleStarting 을 내린다(아래 finally — 사이에 틈이 없다)
  } finally { singleStarting = false; }
}

// 「작업 개요」 의 「한 번에 진행」(변경 계획 → 반영 — app.js divRunAll)이 문서 하나로 조립한 워크플로우의 문서에서 눌렸다: 화면이 계획 → 반영을 돌지 않고, 그 정의의 그 줄(구조 반영 — 줄 key apply)을
// 서버 쪽 실행기로 돌린다(줄 하나 — 울타리 안에서 계획 → 같은 검사 → 반영). 그 정의에 그 줄이 없으면 돌리지 않고 까닭을 알린다(「세부」 의 ① 변경 계획 보기 › ② 반영은 단계별 보정의 자리로 그대로다).
// 끝 글은 그 묶음의 상태 줄(dv.msg — 다음 계획 · 반영 · 입력 때까지)에 남긴다
async function singleRunAll() {
  if (!singleOn() || (typeof taskRun !== "undefined" && taskRun) || singleStarting) return;
  const id = state.id;
  let V = null;
  try { V = await flowGet(id); } catch { V = null; }
  if (state.id !== id) return;
  if (!V) { toast("이 작업의 워크플로우 상태를 읽지 못했습니다 — 잠시 뒤 다시 누르세요", true); return; }
  const g = V.stages.find((x) => (x.steps || []).some((s) => s.key === "apply")); // 구조 반영 줄이 든 묶음(서버가 맡는 묶음만 줄을 준다)
  if (!g) {
    toast(V.stages.some((x) => x.server && x.steps) ? "이 워크플로우에는 「반영」 의 줄이 없습니다 — 워크플로우 페이지의 「워크플로우 조립」 에서 줄을 넣거나, 「세부」 의 단계별 단추로 진행하세요" : SINGLE_NOT_SERVED, true);
    return;
  }
  const r = await singleRunServer(g.id, { only: "apply", sig: V.sig || "" });
  if (r && r.run && state.id === id && typeof dv !== "undefined" && dv) { dv.msg = { kind: r.ok && !r.left ? "done" : "halt", text: r.full || r.text }; if (typeof divRunSync === "function") divRunSync(); }
  return r;
}

setInterval(async () => { // 문서 하나로 조립한 워크플로우의 문서를 연 화면 — 3초마다 확인(메모리만 읽는 끝점): 이 화면의 고치던 글 수를 알리고 울타리 알림을 받는다(flowLive → flowNoticeSync: 읽기 전용 띠 · 고친 글 보내기 · 「받았음」) ·
  // 다른 화면 · 첫 화면의 대시보드 · 에이전트가 시작한 서버 실행이 돌고 있으면 거울로 따라간다(그 뒤는 거울의 1초 확인이 같은 보고를 한다)
  if (typeof state === "undefined" || !state.id || document.hidden || typeof taskRun === "undefined" || taskRun || singleStarting || !singleOn()) return;
  const id = state.id, live = await flowLive(id);
  if (!flowActive(live) || taskRun || singleStarting || state.id !== id || !singleOn()) return;
  if (((live.docs || {}).target || {}).id !== id) return; // 이 문서가 그 실행의 목적 문서일 때만(문서 하나 — 그 문서가 곧 목적 문서)
  singleRunFollow(id, live.n, { quiet: true, stage: (live.now || {}).stage || (live.range || {}).from || "", only: (live.range || {}).only || "" });
}, 3000);
