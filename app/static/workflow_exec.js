"use strict";
// 워크플로우 실행의 화면 쪽 — 서버 쪽 실행기(app/workflow_exec.py)의 상태 읽기 · 실행 · 멈춤(spec_워크플로우 ② §17-9 「화면 · 대시보드 · 에이전트」 · 끝점은 ② §17-5 「끝점」).
// **첫 화면의 대시보드**(home_dash.js — spec_작업에이전트 ② §10 「첫 화면의 대시보드」)와 **문서 화면**(작업 개요 · 대시보드)이 같이 쓴다 — 두 보기가 같은 서버 상태 · 같은 실행 id 를 본다(따로 세지 않는다).
// 여기는 끝점을 부르고 답의 꼴을 맞추는 일만 한다(그리기 · 단추는 그 보기의 몫). app.js 의 이름: api · H_JSON — 끝 확정을 따라오는 flowBaseSync 만 state · adoptBase · applyDoc · commitsLoad · commitBar · toast 도.
//
// wid = 그 묶음(프로젝트 · 워크플로우 · 라운드)의 **어느 문서든** — 서버가 목적 문서를 찾는다.
// - flowGet(wid) → 지금 상태 {job, sig, docs{target, source}, ready, why, stages[{id, no, name, does, server, steps[…] | null, total, done, left, can, why, paid, change}], run, last} | null(옛 서버 · 그런 작업 없음)
// - flowLive(wid) → 도는 실행의 요약 | null(메모리만 — 확인 폴링) · flowActive(run) = 그 요약이 도는 중인가
// - flowStart(wid, body) → {ok: true, run} | {ok: false, reason, message, run?}(409 — 화면에 message 를 그대로 · busy 면 이미 도는 실행) — body = {from, to?, only?, redo?, where, …}
// - flowStop(wid, n) → 멈춤을 걸었나 · flowSkip(wid, doc, on) → 건너뛴 문서 id 들 | null
// - flowRecord(wid, n) → 실행 기록 하나 | null · flowWatch(wid, n, tick) → 그 실행이 끝날 때까지 1초마다 읽고(tick(요약)) 끝난 기록을 돌려준다
// - flowWord(step) → 단계 상태의 화면 글(끝남 · 건너뜀 · 지금 · 남음 · 진행 중 …) · flowEnd(rec) → {ok, text}(지난 실행의 끝 글 — 「끝남 — …」 · 「남김 — …」 · 「멈춤 — …」 · 「끊김 — …」)
// 문서 화면이 서버 실행을 따라가는 거울 · 3초 확인(고치던 글 보고 · 울타리 알림)은 틀마다 아래 절에: 이관형(taskRunServer · taskRunFollow) · 취합형(gatherRunServer · gatherRunFollow) · 문서 하나로 조립한 것(singleRunServer · singleRunFollow) · 줄 목록으로 조립한 이관형(relayFlowRun · relayFlowFollow — 맨 아래)
const FLOW_SCREEN = Math.random().toString(36).slice(2, 10); // 이 화면(탭)의 id — 실행 기록의 origin.screen(누가 시작했나: 「다른 화면에서 진행 중」)
const FLOW_WORD = { done: "끝남", now: "지금", todo: "남음", run: "진행 중", blocked: "막힘", failed: "실패" }; // 서버의 st → 화면 글(대시보드 DASH_ST 와 같은 말 — 색에만 기대지 않는다)
const flowUrl = (wid, tail = "") => `/api/works/${encodeURIComponent(wid)}/flow${tail}`;

async function flowGet(wid) {
  try { return await api(flowUrl(wid)); } catch (e) { if (e.status === 404) return null; throw e; }
}

// n = 그 번호의 실행을 찾는다 — **이 문서를 잡지 않은 실행도**(문서마다 따로 도는 실행: spec_워크플로우 ② §18-22 — 원본 문서만 잡은 실행은 목적 문서의 확인에 run 으로 오지 않는다 · 묶음의 도는 실행들 runs 에 있다).
// 안 주면 이 문서를 잡은 실행(전과 같다 — 3초 확인이 「이 문서에서 도는 것」 을 따라간다)
async function flowLive(wid, n = 0) { // 확인 폴링 — 못 읽으면 도는 것이 없는 것으로(다음 읽기가 바로잡는다). 이 화면이 연 문서면 고치던 글 수를 싣고 울타리 알림을 받는다(spec_워크플로우 ② §17-8)
  const mine = typeof state !== "undefined" && state.id === wid, epoch = mine ? state.epoch : null;
  const ack = mine && flowFence && flowFence.id === wid && flowFence.ready ? flowFence.key : ""; // 받았음 — 입력을 막고 고친 글을 보낸 뒤에만(서버는 이 key 를 되돌린 보고만 센다)
  let r = null;
  try { r = await api(flowUrl(wid, `/live${mine ? `?screen=${FLOW_SCREEN}&dirty=${flowDirty()}${ack ? `&ack=${encodeURIComponent(ack)}` : ""}` : ""}`)); } catch { return null; }
  if (mine && state.id === wid && state.epoch === epoch) flowNoticeSync(wid, r); // 그 사이 다른 문서를 열었으면 그 문서에 띠를 세우지 않는다
  if (n) return (r && (r.runs || []).find((x) => x.n === n)) || (r && r.run && r.run.n === n ? r.run : null);
  return (r && r.run) || null;
}

// ---------------------------------------------------------------- 문서마다 따로 도는 실행(spec_워크플로우 ② §18-22 — 2026-11-21 사용자 「원본문서랑, 목적문서를 따로따로 실행해서 처리할 수 있잖아? 매칭은 1개 실행이 같이 해야하고」)
// 문서 하나만 잡은 실행(요약의 lane = source | target)은 다른 문서의 실행과 같이 돈다. 이 화면의 거울(taskRun)은 하나뿐이라 — 거울이 선 채(다른 문서의 실행을 따라가는 중) 또는 보고 있지 않은 문서의 실행을
// 시작하면 그 실행은 **곁에서 지켜본다**(flowSideWatch): 거울을 세우지 않고 끝날 때까지 2초마다 확인해 끝 글을 알리고 단계 재료 · 대시보드를 다시 읽게 한다. 진행은 대시보드가 서버 상태(runs)로 보인다.
const flowSides = new Map(); // `${목적 문서 id}:${번호}` → {tid, n, lane, label} — 곁에서 지켜보는 실행(대시보드가 그 문서의 단추를 서버 상태를 읽기 전에도 끈다: dashboard.js)
const flowSideOf = (tid, lane) => [...flowSides.values()].some((x) => x.tid === tid && (!x.lane || x.lane === lane)); // 그 문서를 잡은 곁의 실행이 있나
async function flowSideWatch(tid, run, label = "") {
  const key = `${tid}:${run.n}`;
  if (flowSides.has(key)) return;
  flowSides.set(key, { tid, n: run.n, lane: run.lane || "", label });
  let rec = null, miss = 0;
  try {
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      let live = null;
      try { live = ((await api(flowUrl(tid, "/live"))).runs || []).find((x) => x.n === run.n) || null; } catch { live = null; }
      if (flowActive(live)) { miss = 0; continue; }
      rec = await flowRecord(tid, run.n);
      if (rec && rec.status === "running" && ++miss <= 5) continue; // 확인을 못 읽었을 뿐 실행은 돌고 있다
      break;
    }
  } finally { flowSides.delete(key); }
  const E = flowEnd(rec);
  if (E && E.text) toast(E.text, !E.ok);
  if (typeof state === "undefined" || !state.id) return;
  const docs = (rec && rec.docs) || {}, ids = [(docs.target || {}).id, (docs.source || {}).id], held = run.lane === "source" ? ids[1] : run.lane === "target" ? ids[0] : state.id;
  if (!ids.includes(state.id)) return; // 그 사이 다른 문서를 열었다
  try {
    if (state.id === held && typeof singleRefresh === "function") await singleRefresh(state.id); // 그 실행이 이 문서를 바꿨으면 문서부터
    if (typeof taskFlowLoad === "function" && ids.includes(state.id)) await taskFlowLoad(); // 두 문서의 단계 재료(분석 요약 · 연결 목록 …)
  } catch (e) { console.warn(e); }
  if (typeof docStatusPing === "function") docStatusPing();
  if (typeof taskStepsDraw === "function" && typeof taskSlots === "function" && taskSlots() && !(typeof relayFlowOn === "function" && relayFlowOn())) { try { taskStepsDraw(); } catch (e) { console.warn(e); } } // 붙박이 이관의 「작업 개요」 단계 줄
  if (typeof dashFlowTouch === "function") dashFlowTouch(state.id);
  if (typeof DASH !== "undefined" && DASH.solo) DASH.solo.at = 0;
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
    if (r && r.rev != null && r.rev !== state.serverRev) flowReload(id).finally(() => { if (!flowFence) flowBand(false); after(); flowBaseSync(id, r); }); // 다시 읽는 동안에도 띠(입력 막음)는 그대로 — 그 사이 친 글이 새 문서에 덮이지 않게
    else { flowBand(false); after(); flowBaseSync(id, r); }
    return;
  }
  if (!n) flowBaseSync(id, r); // 끝 확정(spec_워크플로우 ② §18-24) — 서버가 이 문서를 확정해 기준이 바뀌었으면 새 기준으로(확인마다 · 기준이 같으면 바로 돌아온다)
}

// 묶음째 실행의 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」) — 서버 실행이 이 문서를 확정하면 문서 차례(rev)는 그대로이고 기준(base)만 바뀐다:
// 확인(GET …/flow/live 의 base)이 지금 기준과 다르면 문서를 한 번 읽어(차례도 바뀌었으면 다시 그린다 — 알림을 놓친 화면) 새 기준으로 바꾸고(adoptBase — 고친 문단 0 · 확정 기록) 알림을 한 번(기준 번호마다).
// 고치던 글이 있거나 · 이 화면이 확정 · 복원 · 구조 편집 중이거나 · 이미 읽는 중이면 하지 않는다(다음 확인이 다시 본다) → 바꿨나
// 읽는 사이 이 화면이 글을 고쳐 보냈으면(수정 번호 localRev · 문서 차례 serverRev 가 움직임 — 큰 문서는 읽기가 몇 초) 그 읽은 문서는 옛것이다 — 그리지도 기준으로 삼지도 않는다(다음 확인이 다시 읽는다):
// 옛 문서로 다시 그리면 방금 친 글이 화면에서 사라지고, 이어 친 글이 옛 글 위에 보내져 서버의 새 글을 덮는다(2026-11-22 검토)
let flowBaseBusy = false;
const flowBaseSaid = {}; // 문서 id → 알린 기준 번호
async function flowBaseSync(id, now) {
  if (flowBaseBusy || typeof state === "undefined" || state.id !== id || !state.stored || !now || now.base == null || now.base === state.base) return false;
  if (flowDirty() || state.commitBusy || state.busy || typeof adoptBase !== "function") return false;
  const epoch = state.epoch, lr = state.localRev, sr = state.serverRev;
  flowBaseBusy = true;
  try {
    const d = await api(`/api/docs/${encodeURIComponent(id)}`);
    if (state.id !== id || state.epoch !== epoch || flowDirty() || state.commitBusy || state.busy || (d.base || 0) === state.base) return false; // 읽는 사이 — 다른 문서 · 고친 글 · 확정 · 구조 편집이 끼었다
    if (state.localRev !== lr || state.serverRev !== sr) return false; // 읽는 사이 고친 글을 보냈거나 다른 응답이 차례를 바꿨다 — 읽은 문서는 옛것이다
    // 여기까지 왔으면 읽는 동안 이 화면은 아무것도 보내지 않았다(보낼 차례 · 보내는 중 · 구조 편집 없음 · 수정 번호 그대로) — 읽은 문서가 서버의 지금 문서다.
    // 차례가 다르면(반영의 알림을 놓친 화면 — 숨긴 탭 · 서버를 다시 켜 차례가 앞으로 돌아간 문서) 먼저 다시 그린다
    if (d.rev != null && d.rev !== state.serverRev && typeof applyDoc === "function") applyDoc(d);
    adoptBase(d, false);
    if (typeof commitsLoad === "function") commitsLoad();
    if (typeof commitBar === "function") commitBar();
    if (flowBaseSaid[id] !== d.base) { flowBaseSaid[id] = d.base; toast(`확정 ${d.base} — 워크플로우가 고친 문단을 확정했습니다(앞 상태는 「고친 문단」 탭 확정 기록의 복원)`); }
    return true;
  } catch (e) { console.warn(e); return false; } finally { flowBaseBusy = false; }
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
    const run = await flowLive(wid, n); // 그 번호의 실행 — wid 를 잡지 않은(다른 문서만 잡은) 실행도 따라간다
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

async function taskRunFollow(g, plan, report, n, { quiet = false, redo = "", only = "", chain = null, lane = "" } = {}) { // 그 실행을 끝까지 따라간다(거울) → {ok, text, run} — 끝나면 단계를 다시 읽고 묶음 상태 줄에 끝 글을 남긴다 · chain = 연쇄({to, label}) · lane = 그 실행이 잡은 문서(source | target | "" 두 문서 — ② §18-22)
  const first = { review: "heads", frame: redo || "config", map: "link", clean: "guide" }[g.id] || ""; // 첫 확인 전의 단계(화면 taskRunSteps 의 run.key 와 같다) — 다음 확인이 서버의 지금 단계로 바꾼다
  const run = (taskRun = { stage: g.id, report: report.id, key: only || first, note: "", t0: Date.now(), stop: false, chain, redo, only, paid: null, server: true, n, by: "", lane });
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
      Object.assign(run, { stage: now.stage || run.stage, key: now.key || run.key, note: now.note || "", by: flowBy(live), lane: live.lane || "", ...(live.started ? { t0: live.started * 1000 } : {}) });
      if (moved) taskStageSync(); // 단계가 바뀌면 바로 — 상태 줄 · 「진행 중」 표시(화면 실행의 at() 과 같다)
      if (run.stop && !run.stopSent) { run.stopSent = true; flowStop(report.id, n); } // 「멈춤」 — 지금 하는 일이 끝나면(서버가 멈춘다)
    });
  } finally {
    clearInterval(run.timer);
  }
  // 거울(taskRun)은 끝 글을 남기는 그 순간까지 둔다 — 다시 읽기 · 단계 재료 읽기를 기다리는 동안 「!taskRun」 을 보는 쪽(검사 · 에이전트 agwRunning)이 끝 글 없이 끝난 것으로 보지 않게(단추는 그동안 꺼진 채)
  try {
    if ((state.id === report.id || state.id === plan.id) && !flowDirty()) { // 서버 실행이 이 문서를 바꿨는데(구조 반영 …) 알림을 놓쳤으면 — 끝난 뒤 한 번 견줘 다시 읽는다 · 끝 확정이 기준을 바꿨으면 새 기준으로(② §18-24)
      const id = state.id, now = await api(flowUrl(id, "/live")).catch(() => null);
      if (id === report.id && now && now.rev != null && now.rev !== state.serverRev && !now.notice) await flowReload(report.id);
      if (now && !now.notice) await flowBaseSync(id, now);
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
// side = 거울을 세우지 않는 시작(→ {side: 실행 요약}) — 다른 문서만 잡은 실행의 거울이 이미 서 있을 때 이 문서의 실행을 같이 돌린다(부르는 쪽이 flowSideWatch 로 곁에서 지켜본다: ② §18-22)
async function taskRunServer(g, plan, report, { redo = "", only = "", paid = null, to = "", chain = null, role = "", side = false } = {}) { // to · chain = 묶음 연쇄(「이어서 한 번에」 — 서버가 경계마다 최신 상태로 그 묶음을 할지 정한다) · role = 한 문서만(source | target — 그 묶음에서 그 문서의 줄만: spec_워크플로우 ② §18-21)
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
  const r = await flowStart(report.id, { from: g.id, ...(span.length > 1 ? { to: span[span.length - 1] } : {}), only, redo, ...(role ? { role } : {}), where: "panel", docs: { target: report.id, source: plan.id }, ...(Array.isArray(paid) ? { by: "agent", paid } : {}), ...(skip.length ? { skip } : {}),
    ...(skill ? { skill } : {}), ...(cat.custom && typeof taskCatalogSig === "function" && cat.sig ? { sig: cat.sig } : {}) });
  if (!r.ok && (r.reason === "client" || r.reason === "old")) return null; // 서버가 맡지 않는 묶음 · 옛 서버 — 화면이 돈다(전과 같다)
  if (!r.ok && r.reason === "error") { // 시작 요청의 답을 못 받음 — 서버가 이미 시작했을 수 있어 화면 실행으로 가지 않는다(같은 문서에 두 실행이 걸리지 않게 — astra 2026-11-20)
    const live = await flowLive(report.id);
    if (flowActive(live)) return { follow: () => taskRunFollow(g, plan, report, live.n, { redo, only }) };
    toast(`시작하지 못했습니다 — ${r.message || "서버 응답 없음"} · 다시 누르세요`, true);
    return { ok: false, text: r.message || "서버 응답 없음", run: null };
  }
  const mate = !r.ok && r.reason === "busy" && r.run && r.run.lane && r.run.lane !== role; // 다른 문서만 잡은 실행 때문에 못 한다(두 문서를 함께 쓰는 실행) — 그 실행을 「다른 화면의 것」 으로 따라가지 않고 까닭을 알린다
  if (!r.ok && r.reason === "busy" && r.run && !mate && !side) { toast("다른 화면에서 진행 중입니다 — 그 실행을 따라 보입니다"); return { follow: () => taskRunFollow(g, plan, report, r.run.n, { quiet: true, lane: r.run.lane || "" }) }; }
  if (!r.ok) { toast(r.message, true); return { ok: false, text: r.message, run: null }; }
  if (side) return { side: r.run };
  return { follow: () => taskRunFollow(g, plan, report, r.run.n, { redo, only, chain: span.length > 1 ? chain : null, lane: r.run.lane || "" }) };
}

setInterval(async () => { // 다른 화면 · 첫 화면의 대시보드 · 에이전트가 시작한 서버 실행 — 이 문서가 그 묶음에 들었으면 거울로 따라간다(3초마다 · 메모리만 읽는 확인)
  if (typeof state === "undefined" || !state.id || document.hidden || typeof taskRun === "undefined" || taskRun || (typeof taskRunChecking !== "undefined" && taskRunChecking)) return;
  if (typeof taskSlots !== "function" || !taskSlots() || (typeof gatherOn === "function" && gatherOn()) || (typeof PEEK !== "undefined" && PEEK)) return;
  const id = state.id, live = await flowLive(id);
  if (!flowActive(live) || taskRun || state.id !== id) return;
  const [plan0, report] = taskSlots().map((k) => taskSlotDoc(k));
  const plan = plan0 || (typeof relayFlowMany === "function" && relayFlowMany() ? report : null); // 같은 양식 취합 — 기관 문서가 아직 없어도 목적 문서의 줄은 돈다(거울은 목적 문서로)
  if (!plan || !report || ((live.docs || {}).target || {}).id !== report.id) return;
  if (typeof taskStagesSync === "function") taskStagesSync();
  const g = TASK_STAGES.find((x) => x.id === ((live.now || {}).stage || (live.range || {}).from));
  if (g) taskRunFollow(g, plan, report, live.n, { quiet: true, lane: live.lane || "" });
  // 줄 목록으로 조립한 이관형(아래 「줄 목록」 절 — 그 정의의 묶음 g1 … 은 TASK_STAGES 에 없다): 그 절의 거울로 따라간다(보고 있는 문서가 원본이든 목적이든 — live = 이 문서를 잡은 실행: 다른 문서만 잡은 실행은 거울 없이 대시보드가 보인다)
  else if (typeof relayFlowOn === "function" && relayFlowOn() && !relayFlowStarting)
    relayFlowFollow(report.id, plan.id, live.n, { quiet: true, stage: (live.now || {}).stage || (live.range || {}).from || "", only: (live.range || {}).only || "", lane: live.lane || "", role: (live.range || {}).role || "" });
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
      if (now && !now.notice) await flowBaseSync(plan.id, now); // 끝 확정이 취합본의 기준을 바꿨으면 새 기준으로(② §18-24)
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
// opt = gatherRunStage 의 것: quick(구조 맞춤에 지움이 있으면 멈춤) · auto(Set — 이번에 올린 문서: 미지정이면 반영할 기관을 자동 지정) · llm(false = LLM 검토 안 함) · log · quiet · only(줄 key — 그 줄 하나만) · from(정의 묶음 id — 주면 그 묶음에서)
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
  const job = gatherJobNow(), made = !!(TASK_CATALOG[job] || {}).custom, from = opt.from || gatherDefStage(stage.id, job, first); // opt.from = 정의 묶음을 부른 쪽이 안다(대시보드의 조립 도구 줄 — 같은 도구를 두 묶음에 놓았을 때)
  if (!from) { const why = `이 워크플로우에는 「${stage.short || stage.name}」 의 줄이 없습니다 — 워크플로우 페이지의 「워크플로우 조립」 에서 줄을 넣거나, 단계별 단추로 진행하세요`; if (!opt.quiet) toast(why, true); return { ok: false, text: why }; }
  const r = await flowStart(plan.id, { from, where: "panel", docs: { target: plan.id }, ...(opt.quick ? { quick: true } : {}), ...(opt.auto && opt.auto.size ? { auto: [...opt.auto] } : {}), ...(opt.llm === false ? { llm: false } : {}),
    ...(opt.only ? { only: opt.only } : {}) }); // only = 줄 하나만(대시보드의 「이 단계만 진행」 — 화면의 묶음에 없는 조립 도구 「넣은 뒤 템플릿 · 서식 정리」: dashboard.js dashGatherLive)
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
      if (state.id === id && now && !now.notice) await flowBaseSync(id, now); // 끝 확정이 기준을 바꿨으면 새 기준으로(② §18-24 — 곁에서 지켜본 실행 · 줄 목록 이관형 · 문서 하나의 거울이 끝에서 여기로 온다)
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
    if (!r.ok && r.reason === "noWork") return { ok: true, text: r.message || "남은 단계가 없습니다", none: true };
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

// ---------------------------------------------------------------- 줄 목록(정의 v2)으로 조립한 이관형(task_catalog.js taskIsRelayFlow — spec_워크플로우 ② §18-13 「줄 목록으로 조립한 이관형의 문서 화면」)
// 2026-11-21 사용자(조립한 「연차보고서 배포(안) 작성」 의 패널 대시보드에 상태 · 단추가 하나도 없는 것을 보며) "안에 기능이 하나도 없냐? … 각 도구마다 실행 및 결과내용을 보여주는게 있어야 하고 한번에 진행, 다 진행 이런게 있어야 하는데".
// 그 정의의 묶음(g1 …)은 화면의 이관 묶음(app.js TASK_STAGES — review · frame · map · clean)에 없다: 위 「문서 화면」 절의 taskRunServer · taskRunFollow(묶음을 TASK_STAGES 에서 찾는다) · 화면 실행(taskRunAll)으로는 못 돈다.
// 문서 하나로 조립한 것(위 절)과 같은 방식으로 간다 — **서버가 센 상태**(GET …/flow — 대시보드 dashboard.js dashFlowLive · 에이전트)로 그리고 **서버 쪽 실행기만** 돌린다(화면 실행으로 가지 않는다 — 서버가 못 맡으면 그 까닭):
// ① 실행 = relayFlowRun(묶음의 「한 번에 진행」 · 줄 하나 only · 같은 차례의 옆 줄까지 row · 「이어서 한 번에」 to) — 화면의 약속(고친 글 · 구성 입력을 먼저 서버에)을 지킨 뒤 시작을 청하고 끝까지 따라간다.
// ② 거울 = relayFlowFollow — app.js 의 `taskRun` 을 그 실행의 거울로 채운다(flow: true · pair = [원본, 목적] 문서 id): 단추를 끄는 곳 · 대시보드의 진행 줄 · 에이전트의 진행 카드(agwRunning)가 따라온다.
//    **보고 있는 문서로 확인한다**(flowLive(지금 문서) — 그 문서의 고치던 글 수를 알리고 울타리 알림을 받는다: 조립한 정의는 원본 문서를 바꾸는 줄도 놓을 수 있다). 그 묶음의 두 문서를 오가도 거울은 그대로이고, 다른 문서를 열면 내린다(실행은 서버에서 이어진다).
// ③ 다른 화면 · 첫 화면의 대시보드 · 에이전트가 시작한 실행은 위 3초 확인(이관형의 것 — taskSlots 가 있는 문서)이 이 거울로 따라간다(그 고리의 줄 목록 가지).
// ④ 끝나면 다시 읽는다 — 보고 있는 문서가 바뀌었으면 문서부터(singleRefresh — 위 절: 문서 차례를 안 올리는 변화도), 그리고 두 문서의 단계 재료(taskFlowLoad — 연결 목록 · 작성 지침 …: 「연결 목록」 같은 보기 단추가 읽는다).
// app.js 의 이름: state · taskRun · taskRunChecking · taskSlots · taskSlotDoc · flushAll · divSettingsFlush · dv · divCanon · divValues · taskFlowLoad · taskCatalogRefresh · projectControlsSync · divRunSync · toast · TASK_CATALOG. dashboard.js: dashFlowTouch.
function relayFlowOn() { // 지금 문서가 줄 목록으로 조립한 이관형 워크플로우의 문서인가(작업이 저장되는 문서만 · 같이 보기의 옆 문서 화면은 아니다)
  return typeof state !== "undefined" && !!state.id && !!state.stored && !!state.task && typeof taskIsRelayFlow === "function" && taskIsRelayFlow(state.task.job) && !(typeof PEEK !== "undefined" && PEEK);
}
const relayFlowPair = () => (relayFlowOn() && typeof taskSlots === "function" && taskSlots() ? taskSlots().map((k) => taskSlotDoc(k)) : [null, null]); // [원본 문서, 목적 문서] — 그 묶음의 칸 문서(빈 칸은 null)
// 같은 양식 취합(task_catalog.js taskIsCollect — 원본 문서 = 기관 문서 여럿: spec_취합 ② §10)의 문서들. relayFlowPair 의 원본 = 그 가운데 하나(지금 문서가 기관 문서면 그것 · 아니면 첫 문서)일 뿐이다 —
// 「그 묶음의 문서를 보고 있나」(거울) · 시작 요청의 docs(서버의 source 는 없다 — 기관 문서들은 서버가 등록한 차례로 못 박는다)는 이것으로 가른다
const relayFlowMany = () => relayFlowOn() && typeof taskIsCollect === "function" && taskIsCollect(state.task.job);
function relayFlowParts() { // 그 묶음의 기관 문서들(작업 목록의 것 — 지금 문서가 기관 문서면 그것도) → [{id, name, …}]
  if (!relayFlowMany() || typeof taskDocs !== "function") return [];
  const kind = taskCollectKind(state.task.job);
  return taskDocs().filter((w) => (w.task || {}).file === kind && (w.id === state.id || taskSameScope(w)));
}
let relayFlowStarting = false; // 시작 요청(화면의 약속 → POST)을 보내는 중 — 그동안 또 눌러 둘이 시작하지 않게 · 3초 확인이 그 실행을 먼저 따라가지 않게
let relayFlowLast = null;      // 이 화면이 끝까지 따라간 마지막 실행의 끝 {id 목적 문서, n, ok, left, text 서버가 지은 끝 글} — 화면 검사 · 에이전트가 읽는다

function relayFlowSync() { // 거울이 서고 내릴 때 — 단추를 끄고 켠다 · 대시보드가 읽어 둔 서버 상태를 다시 읽게
  if (typeof projectControlsSync === "function") projectControlsSync();
  if (typeof divRunSync === "function") divRunSync();
  if (typeof dashFlowTouch === "function" && typeof state !== "undefined" && state.id) dashFlowTouch(state.id);
}

// lane = 그 실행이 잡은 문서(source | target — 그 문서만: 다른 문서의 실행은 같이 돌 수 있다 · "" = 두 문서 — spec_워크플로우 ② §18-22) · role = 한 문서만으로 시작한 실행의 그 문서(진행 줄의 이름)
async function relayFlowFollow(tid, sid, n, { quiet = false, stage = "", only = "", lane = "", role = "" } = {}) { // 그 실행을 끝까지 따라간다(거울) → {ok, left, text(머리말을 뗀 끝 글), full(서버가 지은 끝 글 그대로), run(실행 기록)}
  const run = (taskRun = { stage, report: tid, key: only, note: "", t0: Date.now(), stop: false, chain: null, redo: "", only, paid: null, server: true, flow: true, pair: [sid, tid], n, by: "", lane, role });
  const many = relayFlowMany(); // 같은 양식 취합 — 기관 문서가 여럿: 그 묶음의 어느 기관 문서를 보고 있어도 거울은 그대로(목적 문서가 같은 묶음일 때만)
  const here = () => (state.id === tid || state.id === sid || (many && relayFlowMany() && (relayFlowPair()[1] || {}).id === tid && relayFlowParts().some((w) => w.id === state.id)) ? state.id : ""); // 그 묶음의 문서를 보고 있나
  let away = false, rec = null, miss = 0;
  relayFlowLast = null;
  relayFlowSync();
  try {
    for (;;) {
      const id = here();
      if (taskRun !== run || !id) { away = true; break; }
      const live = await flowLive(id, n); // 보고 있는 문서로 — 그 문서의 고치던 글 수를 알리고 울타리 알림을 받는다(1초마다) · 그 번호의 실행을 찾는다(보고 있는 문서를 잡지 않은 실행이어도)
      if (taskRun !== run || !here()) { away = true; break; }
      if (!flowActive(live) || live.n !== n) {
        rec = await flowRecord(tid, n);
        if (rec && rec.status === "running" && live === null && ++miss <= 5 && taskRun === run && here()) { await new Promise((r) => setTimeout(r, 1000)); continue; } // 확인을 못 읽었을 뿐 실행은 돌고 있다 — 거울을 내리지 않는다(몇 번까지)
        break;
      }
      miss = 0;
      const now = live.now || {}, R = live.range || {}, at = now.stage || run.stage || R.from || "", key = now.key || run.key, moved = at !== run.stage || key !== run.key;
      Object.assign(run, { stage: at, key, note: now.note || "", only: R.only || "", role: R.role || "", lane: live.lane || "", by: flowBy(live), ...(live.started ? { t0: live.started * 1000 } : {}) });
      if (moved) { if (typeof docStatusPing === "function") docStatusPing(); if (typeof dashFlowTouch === "function") dashFlowTouch(state.id); } // 줄이 넘어갔다 — 분석 상태 줄 · 대시보드의 서버 상태
      if (run.stop && !run.stopSent) { run.stopSent = true; flowStop(tid, n); } // 「멈춤」 — 지금 하는 일이 끝나면(서버가 멈춘다)
      await new Promise((r) => setTimeout(r, 1000));
    }
    if (away) return { ok: false, left: false, text: "다른 문서를 열어 이 실행을 더 따라가지 않습니다 — 실행은 서버에서 이어집니다", full: "", run: null };
    // 거울(taskRun)은 다시 읽기가 끝날 때까지 둔다 — 그동안 「!taskRun」 을 보는 쪽(단추 · 에이전트 · 화면 검사)이 끝 글 없이 끝난 것으로 보지 않게
    const id = here();
    if (id) {
      await singleRefresh(id); // 이 문서가 바뀌었으면 문서부터 · 문서 차례를 안 올리는 변화(분석 · LLM 결과 · 구성)도
      if (here() && typeof taskFlowLoad === "function") { try { await taskFlowLoad(); } catch (e) { console.warn(e); } } // 두 문서의 단계 재료(연결 목록 · 작성 지침 …)
      // 대시보드가 읽어 둔 서버 상태도 거울을 내리기 전에 새로 — 「!taskRun」 을 보는 쪽(사람 · 화면 검사)이 끝난 실행을 「도는 중」 으로 그린 낡은 상태를 보지 않게(대시보드의 시작은 끝까지 기다리지 않는다: dashFlowRun 의 detach)
      if (here() && typeof dashFlowRead === "function" && typeof dashFlow === "function") { try { dashFlowTouch(state.id); await dashFlowRead(); if (dashFlow().stale) await dashFlowRead(); } catch (e) { console.warn(e); } }
    }
    const E = flowEnd(rec), full = E ? E.text : "실행 기록을 읽지 못했습니다";
    const end = { ok: !!(E && E.ok), left: !!(E && E.left), text: full.replace(/^(끝남|남김|멈춤|오류|끊김) — /, ""), full, run: rec };
    relayFlowLast = { id: tid, n, ok: end.ok, left: end.left, text: full };
    if (taskRun === run) taskRun = null; // 끝 글과 같은 틈(동기)에
    relayFlowSync();
    if (!quiet && here()) toast(full, !end.ok);
    return end;
  } finally {
    if (taskRun === run) { taskRun = null; relayFlowSync(); }
  }
}

// 그 묶음을 서버 쪽 실행기로 시작하고 끝까지 따라간다 → 끝 {ok, text, full?, run?, none?}. from = 그 정의의 묶음 id(g1 …) · to = 묶음 연쇄의 끝 묶음(「이어서 한 번에」) · only = 그 줄 하나만 · row = only 의 줄과 같은 차례(행)에 선 옆 줄도 함께 ·
// paid = 에이전트의 실행 카드가 승인한 문서 id 들(있으면 by agent) · sig = 이 화면이 본 정의의 지문(그 사이 정의가 바뀌었으면 서버가 시작하지 않는다). **화면이 돌리지 않는다** — 서버가 못 맡으면 그 까닭을 돌려준다
// role = 한 문서만("source" | "target" — 그 묶음에서 그 문서의 줄만: spec_워크플로우 ② §18-21 — 2026-11-21 사용자 「하나의 문서만 작업할 수 있도록」)
// **문서마다 따로 도는 실행**(② §18-22): lane = 이 실행이 잡을 문서의 귀띔(source | target — 한 문서만 · 문서 하나의 줄뿐인 묶음 · 문서 하나의 줄: 부르는 쪽이 서버 상태에서 안다 · 잡는 문서는 서버가 정한다).
// 거울이 다른 문서만 잡은 실행을 따라가는 중이면 이 문서의 실행을 **같이** 시작한다 — 그 실행은 거울을 세우지 않고 곁에서 지켜본다(flowSideWatch). 보고 있지 않은 문서만 잡은 실행도 거울을 세우지 않는다(이 문서는 그대로 쓴다).
// detach = 시작까지만 기다린다(→ {ok, started: 실행 요약, side?, done: 끝의 약속}) — 대시보드가 쓴다: 따라가는 동안 다른 문서의 단추를 누를 수 있게(끝은 진행 줄 · 서버 상태의 「지난 실행」 으로 보인다)
async function relayFlowRun(from, { to = "", only = "", row = false, role = "", lane = "", paid = null, sig = "", quiet = false, detach = false } = {}) {
  if (!relayFlowOn()) return { ok: false, text: "줄 목록으로 조립한 이관형 워크플로우의 문서가 아닙니다" };
  const mirror = typeof taskRun !== "undefined" ? taskRun : null, want = role || lane;
  const beside = !!(mirror && mirror.flow && mirror.lane && want && mirror.lane !== want); // 거울의 실행은 다른 문서만 잡았다 — 이 문서의 실행은 같이 돈다
  if ((mirror && !beside) || relayFlowStarting || (typeof taskRunChecking !== "undefined" && taskRunChecking)) return { ok: false, text: "지금 진행 중인 작업이 끝난 뒤에 누르세요" };
  const id = state.id, epoch = state.epoch, job = state.task.job, cat = TASK_CATALOG[job] || {}, [src, tgt] = relayFlowPair();
  const say = (why, warn = true) => { if (!quiet) toast(why, warn); return { ok: false, text: why }; };
  const many = relayFlowMany(), mine = many ? src || tgt : src; // 같은 양식 취합 — 원본 문서(기관 문서)는 여럿이고 서버가 등록한 차례로 못 박는다: 시작 요청에 원본 하나를 적지 않는다(기관 문서가 없으면 서버가 그 까닭을 돌려준다)
  if ((!src && !many) || !tgt) return say(`${[[src, "원본 문서"], [tgt, "목적 문서"]].filter((x) => !x[0]).map((x) => x[1]).join(" · ")} 칸이 비었습니다 — 「준비」 에서 문서를 먼저 넣으세요`);
  relayFlowStarting = true;
  try {
    await flushAll(); // 화면의 약속(spec_워크플로우 ② §17-7 「시작」) — 고친 글 · 구성 입력을 먼저 서버에(서버 실행은 서버의 문서 · 값으로 돈다)
    if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 시작하지 않았습니다" };
    if (state.failed.size) return say("서버에 반영하지 못한 문단이 있어 시작하지 않았습니다 — 「고친 문단」 탭에서 먼저 다시 반영하세요");
    if (typeof divSettingsFlush === "function") await divSettingsFlush();
    if (typeof dv !== "undefined" && dv.values && dv.dirty && typeof divCanon === "function" && divCanon(divValues()) !== dv.savedKey) // 구성 입력을 저장하지 못함(틀린 값 400 은 저장이 조용히 건너뛴다) — 옛 값으로 문서를 바꾸지 않게
      return say("프로젝트 구성 입력 칸의 값을 저장하지 못해 시작하지 않았습니다 — 입력 칸의 값(사업기간 · 차년도 …)을 확인한 뒤 다시 누르세요");
    if (state.id !== id || state.epoch !== epoch) return { ok: false, text: "다른 문서를 열어 시작하지 않았습니다" };
    const skip = state.id === tgt.id && typeof dv !== "undefined" && dv.skip ? [...dv.skip] : []; // 「반영에서 빼기」 — 목적 문서의 화면에만 있는 입력(② §17-11 ⓙ)
    const skill = typeof tpaSkillKey === "function" ? tpaSkillKey() : ""; // 서식 정리 스킬(LLM 검증·보완의 셋째)
    const r = await flowStart(tgt.id, { from, ...(to && to !== from ? { to } : {}), ...(only ? { only, ...(row ? { row: true } : {}) } : {}), ...(role ? { role } : {}), where: "panel", docs: { target: tgt.id, source: many ? null : src.id },
      ...(Array.isArray(paid) ? { by: "agent", paid } : {}), ...(skip.length ? { skip } : {}), ...(skill ? { skill } : {}), ...(sig || cat.sig ? { sig: sig || cat.sig } : {}) });
    if (!r.ok && (r.reason === "client" || r.reason === "old")) return say(SINGLE_NOT_SERVED); // 서버가 맡지 않는 묶음 · 옛 서버 — 화면 실행으로 가지 않는다
    if (!r.ok && r.reason === "noWork") return { ok: true, text: r.message || "남은 단계가 없습니다", none: true };
    let n = r.ok ? r.run.n : 0, q = quiet, got = r.ok ? r.run : null;
    if (!r.ok && r.reason === "busy" && r.run) {
      if (beside || (r.run.lane && r.run.lane !== want)) return say(r.message || "지금 진행 중인 작업이 끝난 뒤에 누르세요"); // 다른 문서만 잡은 실행 때문에 못 한다(두 문서를 함께 쓰는 단계) · 거울이 이미 서 있다 — 그 실행을 따라가지 않고 까닭을
      toast("다른 화면에서 진행 중입니다 — 그 실행을 따라 보입니다"); n = r.run.n; q = true; got = r.run;
    } else if (!r.ok && r.reason === "error") { // 시작 요청의 답을 못 받음 — 서버가 이미 시작했을 수 있다: 도는 실행이 있으면 그것을 따라간다
      const live = await flowLive(want === "source" && src ? src.id : tgt.id);
      if (!flowActive(live) || beside) return say(`시작하지 못했습니다 — ${r.message || "서버 응답 없음"} · 다시 누르세요`);
      n = live.n; got = live;
    } else if (!r.ok) {
      if (r.reason === "definition" && typeof taskCatalogRefresh === "function") taskCatalogRefresh(job); // 그 사이 정의가 바뀌었다 — 목록 · 단계 흐름을 새 정의로 다시 읽는다(대시보드도)
      return say(r.message || "시작하지 못했습니다");
    }
    if (state.id !== tgt.id && state.id !== mine.id && !(many && relayFlowParts().some((w) => w.id === state.id))) return { ok: false, text: "다른 문서를 열었습니다 — 실행은 서버에서 이어집니다" };
    const L = (got && got.lane) || "", held = L === "source" ? mine.id : L === "target" ? tgt.id : "";
    if (beside || (taskRun && taskRun !== mirror) || (held && held !== state.id)) { // 거울을 세우지 않는다 — 다른 문서의 실행을 따라가는 거울이 서 있다 · 이 실행은 보고 있지 않은 문서만 잡았다: 곁에서 지켜본다
      const who = L === "source" ? "원본 문서" : L === "target" ? "목적 문서" : "", text = `${who ? `${who}의 실행을` : "실행을"} 시작했습니다 — 서버에서 진행합니다(진행은 대시보드에 보입니다${held && held !== state.id ? " · 이 문서는 그대로 쓸 수 있습니다" : ""})`;
      const done = flowSideWatch(tgt.id, got, text);
      if (typeof dashFlowTouch === "function") dashFlowTouch(state.id);
      if (!quiet) toast(text);
      return { ok: true, text, side: true, started: got, done };
    }
    const done = relayFlowFollow(tgt.id, mine.id, n, { quiet: q, stage: from, only, lane: L, role }); // 거울(taskRun)이 선 뒤에 relayFlowStarting 을 내린다(아래 finally — 사이에 틈이 없다)
    return detach ? { ok: true, text: "", started: got, done } : done;
  } finally { relayFlowStarting = false; }
}
