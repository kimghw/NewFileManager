"use strict";
// 첫 화면의 대시보드(#homeDash — 첫 화면 오른쪽 열 aside#homeAgent 의 탭 「대시보드」 칸(탭 「에이전트」 와 따로 — 2026-11-20): spec_작업에이전트 ② §10 「첫 화면의 대시보드」 · design.md §20).
// 2026-11-20 사용자 "우측에 에이전트가 있는데 여기에 워크플로우를 실행하는 워크플로우 실행 플로우를 넣고 세부적인 내용은 보지않고 실행할 수 있도록 해줘, 근데 이건 '대쉬보드' 라는 것과 동일해야함"
//   → 답 「첫 화면에 머문다」 · 「첫 화면 오른쪽」. 패널 탭 「대시보드」(dashboard.js)와 **같은 것**의 간단한 꼴이다 — 이름 · 말 · 모양(dashboard.css 의 .dash …)이 같고, 단계는 펴지지 않는다(번호 · 이름 · 꼬리표 · 상태 글만 한 줄).
// **실행을 눌러도 첫 화면에 머문다**: 문서 화면을 열지 않고 작업을 준비하고(home_files.js homeFilesStart), 실행은 서버 쪽 실행기가 돈다(workflow_exec.js flowStart · flowStop — 창을 닫아도 이어진다).
// **상태는 서버가 센다**(flowGet — GET /api/works/{wid}/flow): 이 파일은 단계의 상태를 세지 않는다. 서버가 아직 맡지 않은 묶음(server: false)은 「문서 화면에서 진행합니다」 로 보인다(그 묶음의 상태를 여기서 지어내지 않는다) —
//   그래도 그 묶음의 「한 번에 진행」 은 누르면 돈다: 문서 화면을 열고 그 화면의 대시보드 단추를 누른다(hdAway — 2026-11-20 사용자 "실제 실행할 수 있는 버튼이 있는 워크플로우야. 그림만 보여주는게 아냐"). 취합의 「워크플로우 시작」 도 문서 화면으로(homeFilesGo).
// 상태 넷(hdState): pick = 워크플로우를 안 골랐다(고르기 목록) · ready = 골랐고 시작 전(등록부의 단계 흐름 · 문서 칸 · 「워크플로우 시작」) · live = 시작한 뒤(서버 상태 — 묶음의 「한 번에 진행」 · 「멈춤」 · 「대시보드 자세히 보기」) ·
//   gone = 그 작업을 못 찾음(지웠거나 서버가 옛 판). wait = 시작한 묶음의 상태를 아직 못 읽음(처음 한 번).
// 읽히는 차례: dashboard.js · workflow_exec.js 다음. 기대는 이름 — app.js: state · $ · el · hBtn · toast · openWork · showTab · fmtDur · PEEK · homeTaskBusy / panel_help.js: hHelp · panelHelpOwner · panelHelpClose /
//   task_catalog.js: TASK_CATALOG · TASK_STAGE_META · taskAcceptOf / dashboard.js: DASH(reg · regErr) · dashRegLoad · dashTags / workflow_exec.js: flowGet · flowLive · flowActive · flowStart · flowStop · flowWord · flowEnd · flowBy /
//   home_files.js: hf · hfTarget · hfExt · homeFilesStart. doc_agent_work.js 의 homeAgentBind 가 상자(#homeDash)를 만들고, homeAgentDraw · homeAgentAct 가 homeDashDraw · homeDashPick 을 부른다.

// job = 고른 워크플로우 · wid = 시작한 묶음의 목적 문서 작업 id · view = 서버가 센 상태(flowGet) · gone = 그 작업이 없다(404) · err = 상태를 못 읽은 까닭 · note = 머리 아래 알림 {text, warn}(거절 글 · 시작의 알림) ·
// busy = 이 보기가 보낸 요청("start" · "run:<묶음>" · "away:<묶음>"(문서 화면을 여는 중) · "stop") · sig = 마지막으로 그린 것의 서명 · at = 마지막으로 상태를 읽은 때 · reading/again/living = 읽는 중 · 끝나면 한 번 더 · 확인 폴링 중 ·
// seq = 고름 · 비움의 차례(늦게 온 답을 버린다) · away = 문서 화면에 다녀왔다(돌아오면 바로 다시 읽는다) · regWait = 등록부를 읽는 중 · regTried = 등록부에 없어 다시 읽어 본 워크플로우
// form = 목적 문서 칸을 저장한 양식으로 할지 사람이 고른 것(true 양식 · false 목록의 파일 · undefined 저절로 — home_files.js hfUseForm: 고정이면 늘 양식 · 기본값이면 목록에서 목적 문서를 직접 안 골랐을 때)
const HD = { job: "", wid: "", view: null, gone: false, err: "", note: null, busy: "", sig: "", at: 0, reading: false, again: false, living: false, seq: 0, away: false, regWait: false, regTried: "", form: undefined };
const HD_KEY = "nfm.homeDash"; // 시작한 묶음의 기억(이 브라우저 — {job, wid}): 첫 화면을 다시 열어도 그 대시보드가 보인다 · 「다른 워크플로우」 로 비운다
const HD_HELP = "대시보드에서 워크플로우의 단계와 진행 상황을 보고 바로 실행할 수 있습니다.\n"
  + "실행을 눌러도 이 화면에 머뭅니다 — 세부(단계마다의 확인 · 보정)는 「대시보드 자세히 보기」 로 문서 화면에서 봅니다.\n"
  + "「워크플로우 시작」 은 왼쪽 문서 목록으로 문서를 준비합니다(올리기 · 프로젝트로 묶기 · 기본 분석) — 실행은 그 뒤 묶음의 「한 번에 진행」 을 누를 때만 하고, 누르면 확인 창 없이 바로 합니다(유료 LLM · 문서가 바뀌는 묶음은 단추의 풍선 도움말에 적습니다).\n"
  + "「문서 화면에서 진행합니다」 라고 적힌 묶음은 아직 서버가 맡지 않은 묶음입니다 — 그 묶음의 「한 번에 진행」 은 문서 화면을 열고 그 화면의 대시보드에서 진행합니다(취합의 「워크플로우 시작」 도 문서 화면을 엽니다).\n"
  + "꼬리표 아이콘 — 사람(파랑) · 스크립트(</>) · LLM(보라 반짝임) · 문서 바뀜(주황 문서+연필) — 마우스를 올리면 이름이 보입니다. 점선 단계(「선택」)는 안 해도 되는 단계입니다.";

const hdBox = () => $("homeDash");
const hdFront = () => !state.id && !document.hidden && !(typeof PEEK !== "undefined" && PEEK); // 첫 화면이 보이는 동안만 서버를 읽는다
const hdCat = (job) => (typeof TASK_CATALOG === "object" && TASK_CATALOG[job]) || null;
const hdReg = (job) => (DASH.reg && DASH.reg.tasks.find((t) => t.job === job)) || null; // 등록부의 그 워크플로우(묶음 › 단계 · 문서 역할 — dashboard.js 가 읽어 둔 것을 같이 쓴다)
const hdName = (job) => (hdCat(job) || {}).name || "대시보드"; // 목록에 없는 워크플로우(지워진 조립한 것 …)는 키를 보이지 않는다 — 까닭은 서버의 글(알림 줄)
// 시작한 뒤의 그림은 등록부(꼬리표 · 문서 역할의 이름)가 온 뒤에 — 그 전에 서버 상태만으로 그리면 꼬리표 없는 줄이 잠깐 보였다 바뀐다. 등록부를 못 읽었으면(regErr) 서버가 낸 것만으로 그린다
const hdState = () => (!HD.wid ? (HD.job ? "ready" : "pick") : HD.gone ? "gone" : HD.view && (!HD.job || DASH.reg || DASH.regErr) ? "live" : "wait");
const hdFiles = () => (typeof hf === "object" ? hf.files : []);
const hdPad = (n) => String(n).padStart(2, "0");

function hdMemo(v) { // 시작한 묶음의 기억 — 값을 주면 적고(null = 지움), 안 주면 읽는다 → {job, wid} | null. 못 쓰는 브라우저에서는 기억만 안 한다
  try {
    if (v === undefined) {
      const m = JSON.parse(localStorage.getItem(HD_KEY) || "null");
      return m && typeof m.wid === "string" && /^[0-9a-f]{8,64}$/.test(m.wid) ? { job: typeof m.job === "string" ? m.job : "", wid: m.wid } : null;
    }
    if (v) localStorage.setItem(HD_KEY, JSON.stringify(v)); else localStorage.removeItem(HD_KEY);
  } catch { /* 기억만 안 한다 */ }
  return null;
}

function hdClear(job = "") { // 고른 것 · 시작한 것을 비운다 — 문서 · 작업 · 도는 실행은 그대로다(이 보기만)
  HD.seq += 1;
  Object.assign(HD, { job, wid: "", view: null, gone: false, err: "", note: null, busy: "", at: 0, reading: false, again: false, living: false, form: undefined });
  hdMemo(null);
}
const hdSlot = (job) => (typeof hfSlot === "function" ? hfSlot(job) : null); // 그 워크플로우의 목적 문서 칸에 건 양식(home_files.js — 저장한 양식: spec_워크플로우 ② §18-9) | null
const hdUseForm = (job) => !!(typeof hfUseForm === "function" && !(hdCat(job) || {}).gather && hfUseForm(job, HD.form)); // 취합은 양식으로 시작하지 않는다(취합의 「워크플로우 시작」 은 워크플로우 카드의 길 — hdStart)

// 워크플로우를 고른다(고르기 목록 · 첫 화면 에이전트의 start:<job>) → 골랐나. 문서 화면으로 넘어가지 않고 아직 아무것도 올리지 않는다 — 등록부의 단계 흐름과 「워크플로우 시작」 이 보인다.
// 이 보기가 문서를 준비하는 동안(「워크플로우 시작」 — 같은 파일 고르기 창을 기다리는 중일 수도)에는 고르지 않는다(그 준비를 다른 워크플로우로 덮지 않는다)
function homeDashPick(job) {
  const cat = hdCat(job);
  if (!cat || cat.soon || HD.busy === "start") return false;
  hdClear(job);
  homeDashDraw(true);
  if (typeof homeFilesDraw === "function") homeFilesDraw(); // 왼쪽 목록의 꼬리표 — 목적 문서 칸이 양식이면 목록의 문서는 모두 원본 문서
  if (typeof hfFormsLoad === "function") hfFormsLoad(); // 그 워크플로우의 양식 설정을 다시 읽는다(10초 안의 것은 그대로 — 읽으면 다시 그린다)
  return true;
}

function homeDashReset() { // 「다른 워크플로우」 — 이 대시보드를 비우고 고르기로
  if (HD.busy === "start") return;
  hdClear("");
  homeDashDraw(true);
  if (typeof homeFilesDraw === "function") homeFilesDraw();
}

function hdFocus(keys, ring = false) { // 그린 뒤 초점을 옮긴다 — 누른 단추가 사라지는 바뀜(고름 · 「다른 워크플로우」)에서 초점이 문서 밖으로 떨어지지 않게. keys = 차례대로 찾는 data-hd-focus · 초점 테두리는 키보드로 온 초점일 때만
  const box = hdBox();
  for (const key of keys) {
    const to = box && [...box.querySelectorAll("[data-hd-focus]")].find((x) => x.dataset.hdFocus === key && !x.disabled);
    if (to) { to.focus({ preventScroll: true, focusVisible: ring }); return; }
  }
}
const hdRing = () => { const a = document.activeElement; return !!(a && a.matches && a.matches(":focus-visible")); };

// ---------------------------------------------------------------- 서버 상태 읽기 · 실행(끝점은 workflow_exec.js)
async function hdRead() { // 서버가 센 상태를 다시 읽고 그린다 — 못 찾으면(404) gone · 그 밖의 오류는 지난 상태를 둔 채 알림 한 줄(다음 읽기가 바로잡는다)
  if (!HD.wid) return;
  if (HD.reading) { HD.again = true; return; } // 읽는 중 — 끝나면 한 번 더(방금 시작한 실행이 앞선 답에 덮이지 않게)
  const seq = HD.seq, wid = HD.wid, began = Date.now();
  HD.reading = true;
  let view = null, err = "";
  try { view = await flowGet(wid); } catch (e) { err = e.message || String(e); }
  if (seq !== HD.seq) return; // 그 사이 다른 워크플로우를 골랐거나 비웠다
  HD.reading = false;
  HD.at = Date.now();
  if (err) HD.err = err;
  else {
    Object.assign(HD, { err: "", gone: !view, view });
    if (HD.note && HD.note.busy && HD.note.at <= began && view && !flowActive(view.run)) HD.note = null; // 「다른 화면에서 진행 중입니다」 — 그 실행이 끝났다
    if (view && view.job && view.job !== HD.job) { HD.job = view.job; hdMemo({ job: HD.job, wid }); } // 그 작업의 워크플로우가 문서 화면에서 바뀌었다 — 서버의 것을 따른다
  }
  if (HD.again) { HD.again = false; hdRead(); return; }
  homeDashDraw();
}

async function hdLive() { // 도는 실행의 확인(1초 — 메모리만 읽는 끝점): 글만 바꾼다. 끝났거나 다른 실행이거나 단계가 넘어갔으면 상태를 다시 읽는다(끝 글 · 끝난 수 · 단계의 상태)
  if (HD.living || HD.reading || !HD.view || !HD.view.run) return;
  const seq = HD.seq, was = HD.view.run;
  HD.living = true;
  const run = await flowLive(HD.wid);
  if (seq !== HD.seq) return;
  HD.living = false;
  if (!HD.view || HD.reading) return;
  if (!flowActive(run) || run.n !== was.n) { hdRead(); return; }
  const a = run.now || {}, b = was.now || {};
  HD.view.run = run;
  if (a.stage !== b.stage || a.key !== b.key) hdRead(); else homeDashDraw();
}

// 「워크플로우 시작」 — 왼쪽 문서 목록으로 작업을 만든다(문서 화면을 열지 않는다 — home_files.js homeFilesStart: 검사 · 끝점은 워크플로우 카드의 시작 길과 같다).
// 준비까지다 — 실행은 그 뒤 묶음의 「한 번에 진행」 을 사람이 누를 때만(시작이 전체 실행을 저절로 잇지 않는다: spec ② §10 「확인 정책」)
async function hdStart() {
  const job = HD.job, seq = HD.seq;
  if (HD.busy || !job || typeof homeFilesStart !== "function") return;
  Object.assign(HD, { busy: "start", note: null });
  homeDashDraw(true);
  if ((hdCat(job) || {}).gather) { // 취합 — 첫 화면에서 준비하는 길(homeFilesStart)이 아직 없다: 워크플로우 카드의 길로 문서 화면을 열고 시작한다(기관 문서 올리기 · 등록 · 자동 진행은 그 길 — gather_quick.js).
    let ok = false; // 시작했으면 그 작업을 기억한다 — 첫 화면으로 돌아오면 이 대시보드가 그 작업의 상태를 보인다
    try { ok = !!(await homeFilesGo(job)); } catch (e) { toast(`워크플로우를 시작하지 못했습니다: ${e.message}`, true); }
    if (seq !== HD.seq) return;
    HD.busy = "";
    if (ok && state.id) { Object.assign(HD, { wid: state.id, view: null, gone: false, err: "", away: true }); hdMemo({ job, wid: state.id }); }
    homeDashDraw(true);
    return;
  }
  let r = null;
  try { r = await homeFilesStart(job, { form: hdUseForm(job) }); } catch (e) { toast(`워크플로우를 시작하지 못했습니다: ${e.message}`, true); } // 목적 문서 칸 = 저장한 양식이면 그 양식으로(서버의 「워크플로우 시작」 이 고정 · 기본값을 견준다)
  if (seq !== HD.seq) return;
  HD.busy = "";
  if (!r) { homeDashDraw(true); return; } // 그만둠 · 거절 — 까닭은 알림 · 왼쪽 목록의 줄
  if (r.opened) { // 같은 파일 고르기의 「그대로 열기」 — 그 작업이 같은 워크플로우일 때만 그 작업의 대시보드를 보인다(다른 워크플로우의 작업을 이 워크플로우로 바꾸지 않는다)
    let v = null;
    try { v = await flowGet(r.opened); } catch { v = null; }
    if (seq !== HD.seq) return;
    if (v && v.job === job) {
      Object.assign(HD, { wid: (v.docs && v.docs.target && v.docs.target.id) || r.opened, view: v, gone: false, err: "", at: Date.now() });
      hdMemo({ job, wid: HD.wid });
    } else toast("다른 워크플로우의 작업입니다 — 문서 화면에서 여세요", true);
    homeDashDraw(true);
    return;
  }
  Object.assign(HD, { wid: r.id, view: null, gone: false, err: "" });
  hdMemo({ job, wid: r.id });
  const left = (r.failed || []).length ? `올리지 못한 문서(${r.failed.map((n) => `「${n}」`).join(" · ")})는 왼쪽 문서 목록에 남겼습니다 — 「대시보드 자세히 보기」 로 문서 화면을 열어 「작업 개요」 의 첨부 파일 칸에서 올리세요` : "";
  if (r.note || left) HD.note = { text: [r.note, left].filter(Boolean).join("\n"), warn: !!left };
  homeDashDraw(true);
  await hdRead();
}

// 묶음의 「한 번에 진행」 — 서버 쪽 실행기에 시작을 청한다(확인 창 없이 바로: design.md §18 · 유료 LLM · 문서 바뀜은 단추의 풍선 도움말과 꼬리표에).
// 이 보기가 본 문서 칸 · 정의의 지문을 같이 보낸다 — 그 사이 문서 화면에서 칸이나 단계가 바뀌었으면 서버가 시작하지 않고 까닭을 돌려준다(본 것과 다른 것을 돌리지 않는다).
// 두 자리(이 화면 · 문서 화면)에서 잇달아 눌러도 서버의 잠금이 한 번만 돌린다 — 거절(이미 도는 실행 포함)은 그 글을 머리 아래 한 줄로
async function hdRun(gid) {
  if (HD.busy || !HD.wid || !HD.view) return;
  const seq = HD.seq, V = HD.view, docs = V.docs || {};
  Object.assign(HD, { busy: `run:${gid}`, note: null });
  homeDashDraw(true);
  const r = await flowStart(HD.wid, { from: gid, where: "home", sig: V.sig || "", docs: { target: (docs.target || {}).id || null, source: (docs.source || {}).id || null } });
  if (seq !== HD.seq) return;
  HD.busy = "";
  if (r.ok) { if (HD.view) Object.assign(HD.view, { run: r.run, last: null }); }
  else {
    HD.note = { text: r.message || "시작하지 못했습니다", warn: true, busy: r.reason === "busy", at: Date.now() }; // busy = 「다른 화면에서 진행 중입니다 …」 — 그 실행이 끝나면 걷는다(hdRead: 이 알림 뒤에 시작한 읽기만)
    if (r.run && HD.view && !flowActive(HD.view.run)) HD.view.run = r.run; // 다른 화면에서 이미 도는 실행 — 그 실행을 그대로 보인다
  }
  homeDashDraw(true);
  hdRead();
}

async function hdStop(n) { // 「멈춤」 — 지금 하는 일이 끝나면 멈춘다(어느 화면이 시작한 실행이든)
  if (HD.busy || !HD.wid) return;
  const seq = HD.seq;
  HD.busy = "stop";
  homeDashDraw(true);
  const ok = await flowStop(HD.wid, n);
  if (seq !== HD.seq) return;
  HD.busy = "";
  if (ok && HD.view && HD.view.run && HD.view.run.n === n) HD.view.run.stopping = true;
  homeDashDraw(true);
  hdRead();
}

async function hdMore(wid) { // 「대시보드 자세히 보기」 — 그 목적 문서를 열고 패널 탭 「대시보드」 로(단계마다의 확인 · 보정 · 문서 화면에서 진행하는 묶음은 거기서)
  await openWork(wid);
  if (state.id === wid) showTab("Dash");
}

// 서버가 아직 맡지 않은 묶음의 「한 번에 진행」(2026-11-20 사용자 "그 워크플로우는 실제 실행할 수 있는 버튼이 있는 워크플로우야. 그림만 보여주는게 아냐"):
// 그 목적 문서를 열고 패널 탭 「대시보드」 의 **같은 묶음 단추를 누른다** — 그 단추의 검사 · 실행 그대로다(새 실행 길이 아니다 · dashboard.js 의 run:<묶음 id>).
// 첫 화면에 머물지 못하는 것은 그 묶음을 아직 서버 실행기가 맡지 않아서다 — 맡으면(spec_워크플로우 ② §18-10 의 걸음) hdRunBtn 이 첫 화면에서 돌린다.
// 패널의 단추가 꺼져 있으면(앞 묶음이 안 끝남 …) 누르지 않고 그 까닭을 알린다 · 그 묶음에 「한 번에 진행」 이 없으면(단계마다 하는 묶음) 그 묶음을 보이고 알린다
async function hdAway(g, wid) {
  if (HD.busy || !wid) return;
  HD.busy = `away:${g.id}`;
  homeDashDraw(true);
  try { await openWork(wid); } finally { HD.busy = ""; }
  if (state.id !== wid) { homeDashDraw(true); return; } // 열지 않았다(저장 안 한 글을 두고 그만둠 · 못 읽음 — 까닭은 openWork 의 알림)
  showTab("Dash");
  const gid = CSS.escape(g.id), at = Date.now();
  let li = null, b = null, seen = 0;
  while (state.id === wid && Date.now() - at < 12000) { // 패널 대시보드가 문서를 읽고 그 묶음을 그릴 때까지 — 묶음이 보인 뒤에도 4초는 단추가 붙고 켜지기를 기다린다
    li = document.querySelector(`#dashBox .dash-group[data-group="${gid}"]`); // (묶음 줄은 등록부로 먼저 그려지고 단추는 그 워크플로우의 상태를 읽은 뒤에 붙는다 — 취합: 기관 문서 보기를 읽은 뒤)
    b = li && li.querySelector(`.dash-ghead [data-dash-focus="run:${gid}"]`);
    if (b && !b.disabled) { b.click(); return; }
    if (li && !seen) seen = Date.now();
    if (li && Date.now() - seen > 4000) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (state.id !== wid) return;
  if (li) li.scrollIntoView({ block: "nearest" });
  const eun = typeof taskJosa === "function" ? taskJosa(g.name, "은", "는") : "은";
  toast(!li ? `대시보드에서 「${g.name}」 묶음을 찾지 못했습니다 — 패널 「대시보드」 에서 진행하세요` : !b ? `「${g.name}」 ${eun} 단계마다 진행합니다 — 대시보드의 단계 카드에서 누르세요`
    : `「${g.name}」 의 「한 번에 진행」 을 지금 누를 수 없습니다 — ${b.title || "대시보드의 까닭을 보세요"}`, !li || !!b);
}

function hdAwayBtn(g, wid, active) { // 서버가 아직 맡지 않은 묶음의 「한 번에 진행」 — 문서 화면을 열고 그 화면의 대시보드에서 돌린다(hdAway). 켜는 조건 · 꺼진 까닭은 그 화면의 단추가 정한다
  const sending = HD.busy === `away:${g.id}`, why = active ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : HD.busy ? "요청을 보내는 중입니다" : "";
  const tip = why || [`${g.no} 「${g.name}」 의 남은 단계를 차례로 한 번에 진행합니다 — 이 묶음은 아직 서버가 맡지 않아 문서 화면을 열고 그 화면의 대시보드에서 진행합니다(첫 화면에 머물지 않습니다). 사람이 봐야 할 곳에서는 멈추거나 남깁니다.`,
    g.does ? `하는 일 — ${g.does}` : ""].filter(Boolean).join("\n");
  const b = hBtn(sending ? "문서를 여는 중…" : "한 번에 진행", () => hdAway(g, wid), { cls: "btn sm", disabled: !!why, title: tip });
  b.dataset.hdFocus = `away:${g.id}`;
  return b;
}

// ---------------------------------------------------------------- 그릴 것 — 묶음 › 단계(등록부의 차례 · 이름 · 꼬리표 + 서버가 센 상태)
// V 가 없으면 등록부만(시작 전 — 문서를 읽기 전이라 끝난 수 · 상태 글이 없다), 있으면 서버가 낸 묶음에 등록부의 꼬리표 · 준비 중인 단계를 얹는다. 상태(st · done · 건너뜀 · 끝난 수 · 할 수 있나)는 서버 것 그대로다
function hdGroups(reg, V) {
  const meta = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META, stages = reg ? reg.stages : [];
  const rows = V ? V.stages.map((sv) => [sv, stages.find((g) => g.id === sv.id) || null]) : stages.map((rg) => [null, rg]);
  let i = 0;
  return rows.map(([sv, rg], gi) => {
    const one = sv || rg, m = rg && rg.meta ? meta[rg.meta] : null, served = !!(sv && sv.server && sv.steps), live = served ? sv.steps : [];
    const base = rg ? rg.steps : live.map((x) => ({ key: x.key, name: x.name, by: [], change: "", auto: false, optional: !!x.optional, soon: false })); // 등록부에 없는 묶음(정의가 방금 바뀜) — 서버가 낸 줄만
    return { id: one.id, no: m ? m.no : one.no || String(gi + 1), name: m ? m.name : one.name || "", does: (rg && rg.does) || (sv && sv.does) || "", sv, served, // 번호 · 이름 = 패널 대시보드와 같은 셈(취합은 TASK_STAGE_META)
      nodes: base.map((s) => { const x = live.find((y) => y.key === s.key) || null; return { ...s, idx: ++i, live: x, state: s.soon ? "soon" : x ? (x.done ? "done" : x.st) : "" }; }) };
  });
}

function hdSig() { // 다시 그릴지 — 상태 · 글 · 단추가 같으면 도는 글(지난 시간)만 바꾼다(초점 · 스크롤 유지 — 패널 대시보드의 dashSig 와 같은 방식)
  const st = hdState(), V = HD.view, list = st === "pick" || st === "ready";
  return JSON.stringify([st, HD.job, HD.wid, HD.err, HD.note, HD.busy, HD.hands ? HD.hands.lines.map((x) => [x.key, x.done, x.ver]) : 0, !!DASH.reg, !!hdReg(HD.job), DASH.regErr,
    list ? [hdFiles().map((f) => `${f.name}:${f.size}`), typeof hfTarget === "function" ? hfTarget() : -1, !!homeTaskBusy || !!(typeof hf === "object" && hf.busy), Object.keys(TASK_CATALOG),
      HD.job ? [hdSlot(HD.job), HD.form, hdUseForm(HD.job), (hdResume(HD.job) || {}).id || "", typeof hf === "object" ? hf.project : ""] : 0] : 0,
    st === "live" ? [V.job, V.sig, V.ready, V.why, V.docs, V.stages.map((g) => [g.id, g.no, g.name, g.server, g.done, g.total, g.left, g.can, g.why, (g.paid || []).length, g.change, (g.steps || []).map((s) => [s.key, s.st, s.done, s.skipped, s.text])]),
      V.run ? [V.run.n, V.run.status, V.run.stopping, (V.run.now || {}).stage, (V.run.now || {}).key, (V.run.now || {}).note, flowBy(V.run)] : 0, V.last ? [V.last.n, V.last.status, (V.last.end || {}).text] : 0] : 0]);
}

const hdRunText = (run) => `${(run.now || {}).note || "진행 중"} · ${fmtDur(Math.max(0, Date.now() / 1000 - (run.started || Date.now() / 1000)))}${run.stopping ? " · 이 일이 끝나면 멈춥니다" : ""}`; // 지금 하는 일 · 지난 시간(패널의 진행 줄과 같은 꼴)

function hdHeadEl(name, { count = "", next = "", job = "" } = {}) { // 머리 — 이름 · 「끝남 n/m」 · 도움말 · 「워크플로우 ↗」 / 한 줄(「다음: …」 · 「진행 중 — …」 · 「모두 끝남」): 패널 대시보드의 머리와 같은 꼴
  const head = el("header", "dash-head"), title = el("div", "dash-title"), help = hHelp("대시보드 도움말", HD_HELP);
  help.dataset.hdFocus = "help";
  title.append(el("b", null, name));
  if (count) title.append(el("span", "dash-count", count));
  title.append(help);
  if (job) {
    const wf = el("a", "dash-wf", "워크플로우 ↗");
    wf.href = `/workflow#${encodeURIComponent(job)}`; wf.target = "_blank"; wf.rel = "noopener"; wf.title = "워크플로우 페이지에서 이 워크플로우의 과정 보기(새 탭)";
    wf.dataset.hdFocus = "wf";
    title.append(wf);
  }
  head.append(title);
  if (next) { const p = el("p", "dash-next", next); p.setAttribute("role", "status"); head.append(p); }
  return head;
}

function hdNoteEl(text, warn = false) { const p = el("div", "dash-note" + (warn ? " warn" : "")); p.append(el("span", null, text)); return p; }

function hdDocsEl(rows) { // 문서 칸 — 역할마다 한 줄 「목적 문서 — 연차보고서: <파일 이름 | 없음>」(차례 = 등록부의 역할 차례: 원본 → 목적 — design.md §19)
  const ul = el("ul", "home-dash-docs");
  ul.setAttribute("aria-label", "문서 칸");
  for (const [role, k, v] of rows) {
    const li = el("li");
    li.dataset.role = role;
    li.append(el("span", "dash-sub", k), " ", el("span", "home-dash-file" + (v ? "" : " muted"), v || "없음"));
    if (v) li.title = v;
    ul.append(li);
  }
  return ul;
}

function hdListDocs(reg, job) { // 시작 전 — 문서 칸에 들 파일(왼쪽 문서 목록의 목적 고르기대로: 고른 것 = 목적 문서 · 나머지 = 원본 문서) · 목적 칸이 저장한 양식이면 그 양식(목록의 문서는 모두 원본 문서)
  const list = hdFiles(), form = hdUseForm(job) ? (hdSlot(job) || {}).form : null, ti = form ? -1 : typeof hfTarget === "function" ? hfTarget() : -1;
  const target = list[ti] || null, others = form ? list : list.filter((_, i) => i !== ti);
  const ss = typeof hfSourceSlot === "function" ? hfSourceSlot(job) : null; // 원본 칸에 건 양식(이관형 — spec_워크플로우 ② §18-9: 고정이면 늘 · 기본값이면 목록에 원본으로 쓸 파일이 없을 때)
  const srcForm = ss && (ss.mode === "fixed" || !others.length) ? `${hfFormLabel(ss.form)} · 양식: ${HF_FORM_MODE[ss.mode]}${ss.mode === "fixed" && others.length ? ` — 목록의 문서 ${others.length}개는 빼세요` : ""}` : "";
  return (reg.roles || []).map((r) => [r.role, `${r.title} — ${r.name}${r.many ? "(문서마다)" : ""}:`,
    r.role === "target" ? (form ? hfFormLabel(form) : target ? target.name : "") : !r.many && srcForm ? srcForm
      : (!target && !form) || !others.length ? "" : r.many ? `문서 ${others.length}개` : others.length > 1 ? `문서 ${others.length}개 — 하나만 둘 수 있습니다` : others[0].name]);
}

// 같은 프로젝트에 이 워크플로우로 하던 작업(목적 문서) — 양식으로 시작할 때만 본다(양식으로 만든 작업은 같은 파일 고르기에 걸리지 않고 늘 새 작업: spec_워크플로우 ② §18-11 ⓕ)
const hdResume = (job) => (hdUseForm(job) && typeof hfFormResume === "function" ? hfFormResume(job) : null);
function hdResumeGo(w) { // 「이어서」 — 그 작업의 대시보드(문서 화면을 열지 않는다 — 「그대로 열기」 와 같은 뜻)
  if (HD.busy || !w) return;
  Object.assign(HD, { wid: w.id, view: null, gone: false, err: "", note: { text: `프로젝트 「${(w.task || {}).project || ""}」 에 하던 작업을 이어서 봅니다`, warn: false } });
  hdMemo({ job: HD.job, wid: w.id });
  homeDashDraw(true);
  hdRead();
}

function hdFormRowEl(job) { // 목적 문서 칸의 양식(워크플로우 설정 — 저장한 양식: 기본값 · 고정) 한 줄 + (기본값이면) 양식 ↔ 목록의 파일 바꾸기 · (고정이면) 까닭 | null(설정 없음)
  const s = hdSlot(job);
  if (!s || (hdCat(job) || {}).gather) return null;
  const box = el("div", "home-dash-form" + (s.form ? "" : " warn")), use = hdUseForm(job), busy = HD.busy === "start";
  box.dataset.mode = s.mode;
  box.dataset.use = use ? "form" : "list";
  box.append(el("span", "dash-tag " + (s.mode === "fixed" ? "dash-t-doc" : "dash-t-soft"), `양식: ${HF_FORM_MODE[s.mode]}`), " ");
  if (!s.form) { box.append(el("span", null, "건 양식을 찾지 못했습니다 — 워크플로우 페이지 「문서 칸」 에서 다시 거세요")); return box; }
  if (!use) box.append(el("span", "home-dash-form-name", hfFormLabel(s.form))); // 양식을 쓰면 이름 · 저장한 날은 위 문서 칸의 목적 줄에 있다(두 번 적지 않는다)
  if (s.mode === "fixed") box.append(el("p", "dash-text muted", "고정 — 목적 문서 칸에 목록의 파일을 넣을 수 없습니다(바꾸려면 워크플로우 페이지의 「문서 칸」). 목록의 문서는 원본 문서로 씁니다"));
  else {
    const flip = hBtn(use ? "목록의 파일로" : "양식으로", () => { HD.form = !use; homeDashDraw(true); homeFilesDraw(); hdFocus(["form"]); }, { cls: "btn sm", disabled: busy, // 왼쪽 목록의 꼬리표(목적 · 원본)도 따라 바뀐다
      title: use ? "목적 문서 칸을 왼쪽 목록에서 고른 문서로 바꿉니다(기본값 — 바꿀 수 있습니다)" : "목적 문서 칸을 저장한 양식으로 되돌립니다(이 워크플로우의 기본값)" });
    flip.dataset.hdFocus = "form";
    box.append(" ", flip, el("p", "dash-text muted", use ? "기본값 — 목록의 문서는 원본 문서로 씁니다. 목록의 문서를 목적 문서로 하려면 「목록의 파일로」" : "목록에서 고른 목적 문서로 시작합니다 — 기본값은 저장한 양식입니다"));
  }
  return box;
}

function hdLiveDocs(reg, V) { // 시작한 뒤 — 서버가 본 문서 칸(그 묶음의 목적 문서 · 원본 문서)
  const docs = V.docs || {}, roles = reg && (reg.roles || []).length ? reg.roles : [...(docs.source ? [{ role: "source", title: "원본 문서", name: "" }] : []), { role: "target", title: "목적 문서", name: "" }]; // 등록부가 없으면 역할 이름만(차례는 같게 원본 → 목적)
  return roles.map((r) => [r.role, `${r.title}${r.name ? ` — ${r.name}` : ""}:`, (docs[r.role] || {}).name || ""]);
}

function hdNodeEl(n) { // 단계 한 줄 — 번호 · 이름 · 꼬리표 · 상태 글(펴지지 않는다 — 단추 · 메모 · 폼은 문서 화면의 대시보드에)
  const li = el("li", "dash-node" + (n.optional ? " opt" : "") + (n.soon ? " soon" : "")), top = el("div", "dash-node-top"), main = el("span", "dash-node-main"), name = el("span", "dash-node-head");
  const word = n.soon ? "준비 중" : n.live ? flowWord(n.live) : ""; // 서버가 센 상태의 글(끝남 · 건너뜀 · 지금 · 남음 · 진행 중 …) — 시작 전 · 문서 화면에서 진행하는 묶음에는 없다
  li.dataset.key = n.key;
  li.dataset.state = n.state || "none";
  if (n.state === "now" || n.state === "run") li.setAttribute("aria-current", "step");
  name.append(el("b", null, n.name));
  main.append(name, dashTags(n));
  top.append(el("span", "dash-no", hdPad(n.idx)), main);
  if (word) top.append(el("span", "dash-st", n.state === "done" && !(n.live && n.live.skipped) ? `✓ ${word}` : word));
  top.title = `${n.name}${word ? ` — ${word}` : ""}${n.live && n.live.text ? `\n${n.live.text}` : ""}`;
  const hand = /^hand[1-9][0-9]?$/.test(n.key) && n.live && HD.hands && HD.hands.wid === HD.wid ? HD.hands.lines.find((x) => x.key === n.key) : null; // 사람이 하는 일(정의 v2 — spec_워크플로우 ② §18-7) — 「했음」 · 「했음 취소」 는 이 화면에서도(사람의 단추)
  if (hand) {
    const b = hBtn(hand.done ? "했음 취소" : "했음", () => hdHand(hand, !hand.done), { cls: "btn sm" + (hand.done ? "" : " primary"), disabled: !!HD.busy,
      title: hand.done ? "「했음」 을 되돌립니다 — 다음 실행이 이 줄에서 다시 멈춥니다" : `사람이 할 일 — ${hand.does}\n마쳤으면 누릅니다 — 묶음의 「한 번에 진행」 이 이 줄을 지나 다음 줄로 갑니다` });
    b.dataset.hdFocus = `hand:${n.key}`;
    top.append(b);
  }
  li.append(top);
  return li;
}

async function hdHands(force = false) { // 사람이 하는 일 줄의 판 · 끝남(GET /api/works/{wid}/flow/hand — 3초 안의 것은 다시 읽지 않는다) — 읽으면 다시 그린다
  const wid = HD.wid, H = HD.hands;
  if (!wid || HD.handsWait || (!force && H && H.wid === wid && Date.now() - H.at < 3000)) return;
  HD.handsWait = true;
  let lines = [];
  try { lines = (await api(`/api/works/${wid}/flow/hand`)).lines || []; } catch { lines = []; }
  HD.handsWait = false;
  if (HD.wid !== wid) return;
  HD.hands = { wid, at: Date.now(), lines };
  homeDashDraw(true);
}

async function hdHand(line, on) { // 「했음」 · 「했음 취소」 — 사람의 단추(에이전트 행동에는 없다)
  if (HD.busy || !HD.wid) return;
  HD.busy = `hand:${line.key}`;
  homeDashDraw(true);
  try { await api(`/api/works/${HD.wid}/flow/hand/${encodeURIComponent(line.key)}`, on ? { method: "POST", headers: H_JSON, body: JSON.stringify({ ver: line.ver }) } : { method: "DELETE" }); }
  catch (e) { HD.note = { text: `${on ? "「했음」" : "「했음 취소」"}을 적지 못했습니다 — ${e.message}`, warn: true }; }
  HD.busy = "";
  await hdHands(true);
  hdRead();
}

function hdRunBtn(g, primary, active) { // 묶음의 「한 번에 진행」 — 켜는 조건 · 꺼진 까닭은 서버의 것(can · why). active = 도는 실행이 있다(방금 시작해 서버 상태를 다시 읽기 전에도 꺼 둔다 — 서버의 글과 같은 까닭)
  const sv = g.sv, sending = HD.busy === `run:${g.id}`;
  const why = !sv.can ? sv.why || "지금은 진행할 수 없습니다" : active ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : HD.busy ? "요청을 보내는 중입니다" : "";
  const tip = why || [`${g.no} 「${g.name}」 의 남은 단계를 차례로 한 번에 진행합니다 — 눌러도 이 화면에 머뭅니다(서버에서 진행 · 창을 닫아도 이어집니다). 사람이 봐야 할 곳에서는 멈추거나 남깁니다.`,
    g.does ? `하는 일 — ${g.does}` : "", (sv.paid || []).length ? `유료 LLM — 문서 ${sv.paid.length}개` : "", sv.change ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n");
  const b = hBtn(sending ? "시작하는 중…" : "한 번에 진행", () => hdRun(g.id), { cls: "btn sm" + (primary && !why ? " primary" : ""), disabled: !!why, title: tip });
  b.dataset.hdFocus = `run:${g.id}`;
  return b;
}

function hdGroupsEl(groups, V) { // 묶음 머리(번호 · 이름 · 끝난 수 · 「한 번에 진행」) + 단계 줄 — 서버가 센 묶음만 끝난 수 · 상태 글이 있다(「한 번에 진행」 은 시작한 뒤 모든 묶음에 — 서버가 안 맡은 묶음은 문서 화면에서: hdAwayBtn)
  const ol = el("ol", "dash-groups"), active = !!(V && flowActive(V.run)), first = V && !active ? groups.find((g) => g.served && g.sv.can) : null;
  ol.setAttribute("aria-label", "워크플로우 단계 묶음과 단계");
  for (const g of groups) {
    const li = el("li", "dash-group"), gh = el("div", "dash-ghead"), flow = el("ol", "dash-flow");
    li.dataset.group = g.id;
    li.dataset.served = g.served ? "1" : "0";
    gh.append(el("span", "dash-gno", g.no), el("b", "dash-gname", g.name), el("span", "dash-gcount", g.served && g.sv.total ? `${g.sv.done}/${g.sv.total}` : `단계 ${g.nodes.length}개`));
    gh.title = g.does;
    if (g.served) {
      if ((g.sv.paid || []).length) { const t = el("span", "dash-tag dash-t-llm", `유료 LLM · 문서 ${g.sv.paid.length}개`); t.title = "이 묶음의 「한 번에 진행」 은 유료 LLM 을 부릅니다(문서마다 몇 분)"; gh.append(t); }
      if (g.sv.change) { const t = el("span", "dash-tag dash-t-doc", "문서 바뀜"); t.title = "이 묶음의 「한 번에 진행」 은 문서를 바꿉니다"; gh.append(t); }
      gh.append(hdRunBtn(g, g === first, active));
    } else if (V) gh.append(hdAwayBtn(g, (V.docs && V.docs.target && V.docs.target.id) || HD.wid, active)); // 아직 서버가 맡지 않은 묶음도 누르면 돈다 — 문서 화면에서(2026-11-20)
    flow.setAttribute("aria-label", `${g.name}의 단계`);
    for (const n of g.nodes) flow.append(hdNodeEl(n));
    li.append(gh);
    if (V && !g.served) li.append(el("p", "dash-text muted home-dash-away", "문서 화면에서 진행합니다 — 「한 번에 진행」 이 문서를 엽니다")); // 아직 서버가 맡지 않은 묶음 — 상태를 여기서 지어내지 않는다
    li.append(flow);
    ol.append(li);
  }
  return ol;
}

function hdFlowEl(job, V) { // 단계 흐름 — 시작 전에는 등록부가 있어야 한다(못 읽었으면 그 까닭 · 읽는 중). 시작한 뒤에는 등록부가 없어도 서버가 낸 묶음 · 줄로 그린다(꼬리표만 빠진다)
  const reg = hdReg(job);
  if (!reg && !V && DASH.regErr) {
    const box = el("div", "dash-note warn"), again = hBtn("다시 읽기", () => { DASH.regErr = ""; homeDashDraw(true); });
    again.dataset.hdFocus = "reg";
    box.append(el("span", null, `워크플로우를 읽지 못했습니다: ${DASH.regErr}`), again);
    return box;
  }
  if (!reg && !V) return el("p", "dash-text muted", DASH.reg ? "이 워크플로우의 단계를 찾지 못했습니다" : "단계 흐름을 읽는 중…");
  const groups = hdGroups(reg, V);
  if (!groups.length) return el("p", "dash-text muted", reg && reg.soon ? "준비 중인 워크플로우입니다 — 아직 등록된 단계가 없습니다" : "등록된 단계가 없습니다");
  return hdGroupsEl(groups, V);
}

function hdFootEl(...kids) { const f = el("div", "home-dash-foot"); f.append(...kids.filter(Boolean)); return f; }
function hdOtherBtn(title, disabled = false) { // 「다른 워크플로우」 — 비운 뒤 초점은 고르기 목록으로
  const b = hBtn("다른 워크플로우", () => { const ring = hdRing(); homeDashReset(); hdFocus(["pick"], ring); }, { title, disabled });
  b.dataset.hdFocus = "other";
  return b;
}

function hdPickParts() { // ① 워크플로우를 안 골랐다 — 고르기 목록: 준비 중이 아닌 워크플로우 · 문서 목록의 목적 문서 형식으로 할 수 있는 것만
  const list = hdFiles(), target = list[typeof hfTarget === "function" ? hfTarget() : -1] || null, ext = target ? hfExt(target) : "", wrap = el("div", "home-dash-pick"), sel = el("select");
  sel.setAttribute("aria-label", "워크플로우 고르기");
  sel.dataset.hdFocus = "pick";
  sel.append(new Option("워크플로우 고르기…", ""));
  for (const [job, cat] of Object.entries(TASK_CATALOG)) if (!cat.soon && (!ext || taskAcceptOf(job).includes(ext))) sel.append(new Option(cat.name, job));
  sel.title = target ? `목적 문서 「${target.name}」 로 할 수 있는 워크플로우입니다 — 고르면 단계 흐름이 보입니다(아직 아무것도 올리지 않습니다)` : "워크플로우를 고르면 단계 흐름이 보입니다 — 문서는 「워크플로우 시작」 을 누를 때 올립니다";
  sel.onchange = () => { const ring = hdRing(); if (sel.value && homeDashPick(sel.value)) hdFocus(["start", "other"], ring); }; // 고른 뒤 초점은 「워크플로우 시작」 으로(꺼져 있으면 「다른 워크플로우」)
  sel.onblur = () => homeDashDraw(); // 고르기 목록에 초점이 있는 동안 미뤄 둔 그리기
  wrap.append(sel);
  return [hdHeadEl("대시보드", { next: "왼쪽에 문서를 넣고 목적 문서를 고른 뒤 워크플로우를 고르세요" }), wrap];
}

function hdStartWhy(job) { // 「워크플로우 시작」 을 미리 끄는 까닭 | "" — 검사 자체는 homeFilesStart 가 한다(워크플로우 카드의 시작 길과 같은 검사 · 같은 글)
  const cat = hdCat(job), list = hdFiles(), target = list[typeof hfTarget === "function" ? hfTarget() : -1] || null;
  if (!cat) return "이 워크플로우를 찾지 못했습니다 — 「다른 워크플로우」 로 다시 고르세요";
  if (cat.gather) { // 취합 — 워크플로우 카드의 길(homeFilesGo — 문서 화면을 열고 시작)로 시작한다: 검사는 그 길의 것 가운데 미리 알 수 있는 것만(2026-11-20 — 전에는 꺼 두고 「왼쪽 워크플로우 카드로」)
    if (!list.length) return "왼쪽에 문서를 넣으세요 — 취합본(목적 문서)과 기관 문서";
    if (!target) return "왼쪽 문서 목록에서 목적 문서(취합본)를 고르세요";
    if (!taskAcceptOf(job).filter((x) => x !== "pdf").includes(hfExt(target))) return `목적 문서 「${target.name}」 로는 시작할 수 없습니다 — hwp·hwpx 문서여야 합니다`;
    return homeTaskBusy || hf.busy ? "문서를 준비하고 있습니다" : "";
  }
  const slot = hdSlot(job), ss = typeof hfSourceSlot === "function" ? hfSourceSlot(job) : null, fixedSrc = ss && ss.mode === "fixed" ? `원본 문서 칸은 ${hfFormLabel(ss.form)}으로 고정돼 있습니다` : ""; // 원본 칸의 양식(spec_워크플로우 ② §18-9 — 고정이면 목록의 문서를 원본으로 못 넣음: homeFilesStart 의 hfSourceFixedAsk 와 같은 검사)
  if (slot && slot.mode === "fixed" && !slot.form) return "고정한 양식을 찾지 못했습니다 — 워크플로우 페이지 「문서 칸」 에서 다시 거세요";
  if (hdUseForm(job)) { // 목적 문서 칸 = 저장한 양식 — 목록의 문서는 원본 문서(이관 = 하나까지 · 없어도 시작한다: 원본 문서는 연 뒤 「작업 개요」 의 첨부 파일 칸에서도 올린다)
    if (fixedSrc && list.length) return `${fixedSrc} — 목록의 문서를 빼세요`;
    if (cat.files && list.length > 1) return `원본 문서는 하나만 둘 수 있습니다 — 목록에 문서가 ${list.length}개입니다`;
    return homeTaskBusy || hf.busy ? "문서를 준비하고 있습니다" : "";
  }
  if (!list.length) return "왼쪽에 문서를 넣으세요 — 넣은 뒤 목적 문서를 고르면 켜집니다";
  if (!target) return "왼쪽 문서 목록에서 목적 문서를 고르세요";
  const exts = taskAcceptOf(job).filter((x) => x !== "pdf");
  if (!exts.includes(hfExt(target))) return `이 워크플로우는 ${exts.join("·")} 문서로 시작합니다 — 목적 문서 「${target.name}」 로는 시작할 수 없습니다`;
  if (fixedSrc && list.length > 1) return `${fixedSrc} — 목록에는 목적 문서만 두세요`;
  if (homeTaskBusy || hf.busy) return "문서를 준비하고 있습니다";
  return "";
}

function hdReadyParts() { // ② 골랐고 시작 전 — 등록부의 단계 흐름(끝난 수 · 상태 글 없음: 문서를 읽기 전) · 문서 칸 · 「워크플로우 시작」
  const job = HD.job, reg = hdReg(job), busy = HD.busy === "start", why = busy ? "" : hdStartWhy(job), form = hdUseForm(job), resume = busy ? null : hdResume(job);
  const gather = !!(hdCat(job) || {}).gather; // 취합 — 「워크플로우 시작」 이 문서 화면을 열고 시작한다(hdStart)
  const parts = [hdHeadEl(hdName(job), { job, next: busy ? "문서를 준비하는 중 — 올리기 · 프로젝트로 묶기 · 기본 분석" : gather ? "시작 전 — 「워크플로우 시작」 을 누르면 문서 화면을 열고 시작합니다" : "시작 전 — 「워크플로우 시작」 을 누르면 문서를 준비합니다" })];
  if (HD.note) parts.push(hdNoteEl(HD.note.text, HD.note.warn));
  if (reg) parts.push(hdDocsEl(hdListDocs(reg, job)));
  const formRow = hdFormRowEl(job); // 목적 문서 칸의 양식(기본값 · 고정) — 설정이 있을 때만
  if (formRow) parts.push(formRow);
  let again = null;
  if (resume) { // 양식으로 시작하면 늘 새 작업(다음 라운드)이다 — 같은 프로젝트에 하던 작업이 있으면 「이어서」 를 먼저(② §18-11 ⓕ)
    const p = (resume.task || {}).project || "", box = el("div", "dash-note");
    again = hBtn("이어서", () => hdResumeGo(resume), { cls: "btn sm primary", title: `프로젝트 「${p}」 에 이 워크플로우로 하던 작업(${resume.name || resume.id})의 대시보드를 봅니다 — 새 작업을 만들지 않습니다` });
    again.dataset.hdFocus = "resume";
    box.dataset.resume = resume.id;
    box.append(el("span", null, `프로젝트 「${p}」 에 이 워크플로우로 하던 작업이 있습니다 — 「이어서」 로 그 작업을 보거나, 「새로 시작」 으로 양식에서 다음 라운드를 만듭니다`));
    parts.push(box);
  }
  parts.push(hdFlowEl(job, null));
  const tip = gather ? "목적 문서(취합본)를 열고 나머지 문서를 기관 문서로 올립니다 — 취합은 아직 첫 화면에서 준비할 수 없어 문서 화면으로 넘어갑니다(왼쪽 워크플로우 카드와 같은 길). 「자동 진행」 을 켰으면 그 화면에서 끝까지 진행합니다"
    : form ? `목적 문서를 ${hfFormLabel(hdSlot(job).form)}으로 만들고(문서 화면으로 넘어가지 않음) 왼쪽 목록의 문서를 원본 문서로 올립니다 — 기본 분석(스크립트)까지. 실행은 그 뒤 묶음의 「한 번에 진행」 을 누를 때만 합니다`
    : "왼쪽 문서 목록으로 문서를 준비합니다 — 올리기 · 프로젝트로 묶기 · 기본 분석(스크립트). 문서 화면으로 넘어가지 않고, 실행은 그 뒤 묶음의 「한 번에 진행」 을 누를 때만 합니다";
  const start = hBtn(busy ? "문서 준비 중…" : resume ? "새로 시작" : "워크플로우 시작", () => hdStart(), { cls: "btn sm" + (resume ? "" : " primary"), disabled: busy || !!why, title: why || tip });
  start.dataset.hdFocus = "start";
  parts.push(hdFootEl(...(again ? [again] : []), start, hdOtherBtn("워크플로우를 다시 고릅니다 — 문서 목록은 그대로입니다", busy), why ? el("p", "dash-text dash-why", why) : null));
  return parts;
}

function hdLiveParts() { // ③ 시작한 뒤 — 서버가 센 상태 그대로: 머리 · 도는 실행 · 지난 실행의 끝 · 알림 · 문서 칸 · 묶음 › 단계 · 「대시보드 자세히 보기」
  const V = HD.view, job = V.job || HD.job, reg = hdReg(job), groups = hdGroups(reg, V), run = V.run, active = flowActive(run), served = groups.filter((g) => g.served);
  const total = served.reduce((s, g) => s + g.sv.total, 0), done = served.reduce((s, g) => s + g.sv.done, 0), nodes = groups.flatMap((g) => g.nodes);
  if (nodes.some((n) => /^hand[1-9][0-9]?$/.test(n.key))) hdHands(); // 사람이 하는 일 줄 — 그 판 · 끝남을 읽어 둔다(「했음」 단추 — hdNodeEl)
  const runNode = nodes.find((n) => n.state === "run"), nowNode = nodes.find((n) => n.state === "now"), badNode = nodes.find((n) => n.state === "failed" || n.state === "blocked");
  const runGroup = active ? groups.find((g) => g.id === ((run.now || {}).stage || (run.range || {}).from)) : null, left = served.some((g) => g.sv.left > 0);
  // 한 줄 — 도는 실행 · 진행 중인 단계(올린 직후의 기본 분석 …) · 다음 단계 · 실패 · 막힌 단계 / 서버가 맡은 묶음이 다 끝났으면 「모두 끝남」(모든 묶음을 서버가 셀 때만) · 「N단계 끝남 — 그 밖의 묶음은 …」
  const next = active ? `진행 중 — ${runGroup ? `${runGroup.no} ${runGroup.name}` : "한 번에 진행"}` : runNode ? `진행 중 — ${hdPad(runNode.idx)} ${runNode.name}` : nowNode ? `다음: ${hdPad(nowNode.idx)} ${nowNode.name}`
    : badNode ? `확인 필요 — ${hdPad(badNode.idx)} ${badNode.name}(${flowWord(badNode.live)})` : !groups.length || left ? "" : served.length === groups.length ? (total ? "모두 끝남" : "")
      : served.length ? `${served.map((g) => g.no).join(" · ")} 끝남 — 그 밖의 묶음은 문서 화면에서 진행합니다` : "이 워크플로우의 묶음은 문서 화면에서 진행합니다";
  const parts = [hdHeadEl(hdName(job), { job: hdCat(job) ? job : "", count: total ? `끝남 ${done}/${total}` : "", next })];
  if (active) { // 도는 실행 한 줄 — 지금 하는 일 · 지난 시간 · (이 화면이 시작하지 않았으면) 누가 · 「멈춤」
    const box = el("div", "dash-live"), text = el("span", "dash-live-text", hdRunText(run)), by = flowBy(run), wait = !!run.stopping || HD.busy === "stop";
    text.setAttribute("role", "status");
    box.append(el("span", "ag-spin"), el("b", null, runGroup ? `${runGroup.no} ${runGroup.name} — 한 번에 진행` : "한 번에 진행"), text);
    if (by) box.append(el("span", "dash-tag dash-t-soft home-dash-by", by));
    const stop = hBtn(wait ? "멈추는 중…" : "멈춤", () => hdStop(run.n), { disabled: wait || !!HD.busy, title: "지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다" });
    stop.dataset.hdFocus = "stop";
    box.append(stop);
    parts.push(box);
  } else {
    const E = flowEnd(V.last); // 지난 실행의 끝 — 서버가 지은 글 그대로(초록 = 끝남 · 주황 = 멈춤 · 남김 · 끊김 · 오류)
    if (E && E.text) parts.push(el("p", "dash-last" + (E.ok && !E.left ? "" : " halt"), E.text));
  }
  if (HD.note) parts.push(hdNoteEl(HD.note.text, HD.note.warn));
  if (HD.err) parts.push(hdNoteEl(`상태를 읽지 못했습니다: ${HD.err}`, true));
  if (V.why && (!V.stages.length || !V.ready)) parts.push(hdNoteEl(V.why, true)); // 워크플로우가 없거나 모르는 워크플로우 · 문서 칸이 비었음(서버의 글)
  parts.push(hdDocsEl(hdLiveDocs(reg, V)));
  if (V.stages.length) parts.push(hdFlowEl(job, V));
  const tid = (V.docs && V.docs.target && V.docs.target.id) || HD.wid, canRun = served.some((g) => g.sv.can);
  const more = hBtn("대시보드 자세히 보기", () => hdMore(tid), { cls: "btn sm" + (!active && !canRun ? " primary" : ""), // 강조 단추는 다음 할 일 하나 — 여기서 실행할 것이 없으면 문서 화면으로 가는 이 단추
    title: "이 워크플로우의 목적 문서를 열고 패널 탭 「대시보드」 로 갑니다 — 단계마다의 확인 · 보정과 문서 화면에서 진행하는 묶음은 거기서 합니다" });
  more.dataset.hdFocus = "more";
  parts.push(hdFootEl(more, hdOtherBtn("이 대시보드를 비우고 워크플로우를 다시 고릅니다 — 문서 · 작업 · 도는 실행은 그대로입니다")));
  return parts;
}

function hdLostParts(st) { // ④ 못 찾음(지웠거나 서버가 옛 판) · 아직 못 읽음
  const parts = [hdHeadEl(hdName(HD.job), { job: hdCat(HD.job) ? HD.job : "" })];
  if (st === "gone") parts.push(hdNoteEl("이 작업을 찾지 못했습니다 — 지웠거나 서버가 옛 판입니다", true));
  else parts.push(HD.err ? hdNoteEl(`상태를 읽지 못했습니다: ${HD.err}`, true) : el("p", "dash-text muted", "상태를 읽는 중…"));
  parts.push(hdFootEl(hdOtherBtn("이 대시보드를 비우고 워크플로우를 다시 고릅니다 — 문서 · 작업은 그대로입니다")));
  return parts;
}

// 그린다 — 상태 · 글 · 단추가 같으면 도는 글만 바꾼다(force 가 아니면). 다시 그려도 초점은 그 단추에(초점 테두리는 키보드로 온 초점일 때만 — design.md §17) · 상자 안 스크롤은 그 자리에
function homeDashDraw(force = false) {
  const box = hdBox();
  if (!box) return;
  const a = document.activeElement;
  if (!force && a && a.tagName === "SELECT" && box.contains(a)) return; // 고르기 목록에 초점이 있는 동안은 다시 그리지 않는다(펼친 목록이 닫힌다) — 고르거나 초점이 떠나면 그린다
  // 등록부 — 페이지에 한 번 읽는다(패널 대시보드와 같이 쓴다). 읽어 둔 등록부에 고른 워크플로우가 없으면(이 화면을 연 뒤에 조립한 워크플로우) 그 워크플로우마다 한 번 다시 읽는다(dashboard.js dashCatalogChanged)
  if (HD.job && DASH.reg && !hdReg(HD.job) && hdCat(HD.job) && HD.regTried !== HD.job && typeof dashCatalogChanged === "function") { HD.regTried = HD.job; dashCatalogChanged(); }
  if (HD.job && !DASH.reg && !DASH.regErr && !HD.regWait) { HD.regWait = true; dashRegLoad().then(() => { HD.regWait = false; homeDashDraw(); }); }
  const sig = hdSig();
  if (!force && sig === HD.sig) {
    const t = box.querySelector(".dash-live-text"), run = HD.view && HD.view.run;
    if (t && flowActive(run)) { const s = hdRunText(run); if (t.textContent !== s) t.textContent = s; }
    return;
  }
  HD.sig = sig;
  const st = hdState(), focus = a && box.contains(a) ? a.dataset.hdFocus || "" : "", ring = !!(focus && a.matches(":focus-visible")), top = box.scrollTop;
  if (typeof panelHelpOwner !== "undefined" && panelHelpOwner && box.contains(panelHelpOwner)) panelHelpClose(); // 떼어 낼 도움말의 풍선이 주인 없이 남지 않게
  box.dataset.state = st;
  box.replaceChildren(...(st === "pick" ? hdPickParts() : st === "ready" ? hdReadyParts() : st === "live" ? hdLiveParts() : hdLostParts(st)));
  box.scrollTop = top;
  if (focus) { const f = [...box.querySelectorAll("[data-hd-focus]")].find((x) => x.dataset.hdFocus === focus && !x.disabled); if (f) f.focus({ preventScroll: true, focusVisible: ring }); }
}

// 1초 — 첫 화면이 보이는 동안만: 고르기 · 시작 전에는 문서 목록의 바뀜을 따라 그리고(서버를 읽지 않는다), 시작한 뒤에는 서버 상태를 읽는다 —
// 도는 실행이 있으면 1초마다 확인(글만) · 어느 단계가 진행 중이면(올린 직후의 기본 분석 …) 3초마다 · 그 밖에는 10초마다. 문서 화면에 다녀오면(로고로 첫 화면에) 바로 다시 읽는다
setInterval(() => {
  if (!hdBox()) return;
  if (!hdFront()) { if (state.id) HD.away = true; return; }
  if (!HD.wid) { HD.away = false; homeDashDraw(); return; }
  if (HD.busy) return; // 이 보기가 보낸 요청(시작 · 멈춤)이 가는 중
  const now = Date.now(), V = HD.view;
  if (HD.err && now - HD.at < 3000) return; // 못 읽었다 — 3초 뒤에 다시
  if (HD.away) { HD.away = false; hdRead(); return; }
  if (V && flowActive(V.run)) { hdLive(); return; }
  const moving = !V || V.stages.some((g) => (g.steps || []).some((s) => s.busy || s.st === "run"));
  if (now - HD.at >= (HD.gone || !moving ? 10000 : 3000)) hdRead(); else homeDashDraw();
}, 1000);

(() => { // 시작한 묶음의 기억 — 첫 화면을 다시 열면(새 탭 포함) 그 대시보드가 보인다: 무엇을 시작했는지만 기억하고 상태는 서버에서 다시 읽는다
  const m = typeof PEEK !== "undefined" && PEEK ? null : hdMemo(); // 같이 보기의 옆 문서 화면(?peek)은 첫 화면을 보이지 않는다 — 기억을 읽지 않는다(서버도 안 읽는다)
  if (m) Object.assign(HD, { job: m.job, wid: m.wid });
  homeDashDraw(true);
  if (m && hdFront()) hdRead();
})();
