"use strict";
// 첫 화면의 대시보드(#homeDash — 첫 화면 오른쪽 열 aside#homeAgent 의 탭 「대시보드」 칸(탭 「에이전트」 와 따로 — 2026-11-20): spec_작업에이전트 ② §10 「첫 화면의 대시보드」 · design.md §20).
// 2026-11-20 사용자 "우측에 에이전트가 있는데 여기에 워크플로우를 실행하는 워크플로우 실행 플로우를 넣고 세부적인 내용은 보지않고 실행할 수 있도록 해줘, 근데 이건 '대쉬보드' 라는 것과 동일해야함"
//   → 답 「첫 화면에 머문다」 · 「첫 화면 오른쪽」. 패널 탭 「대시보드」(dashboard.js)와 **같은 것**이다 — 이름 · 말 · 모양(dashboard.css 의 .dash …)이 같고 **묶음 › 단계는 같은 그리기**다(dashGroupsEl · dashNodeEl:
//   번호 동그라미 · 화살표 · 꼬리표 · 메모 「하는 일 · 조건」 · 상태 글 · 누르면 펴지는 카드 · 묶음 머리의 「한 번에 진행」 · 머리 아래 「이어서 한 번에」). 2026-11-20 같은 날 사용자(두 대시보드를 나란히 보이며) "여기 dashboard 에는 여기 대쉬보드가 들어 가야지"
//   — 처음엔 단계를 펴지 않는 「간단한 꼴」 을 따로 그렸다(화살표 · 메모 · 편 카드 없음). 다른 것은 상태 · 단추의 출처뿐이다: 문서가 열려 있지 않아 상태는 서버가 센 것, 편 카드의 단추는 「했음」 과 「문서 화면에서 열기」(단계마다의 확인 · 보정 단추는 그 문서의 대시보드에).
// **실행을 눌러도 첫 화면에 머문다**: 문서 화면을 열지 않고 작업을 준비하고(home_files.js homeFilesStart), 실행은 서버 쪽 실행기가 돈다(workflow_exec.js flowStart · flowStop — 창을 닫아도 이어진다).
// **상태는 서버가 센다**(flowGet — GET /api/works/{wid}/flow): 이 파일은 단계의 상태를 세지 않는다. 서버가 아직 맡지 않은 묶음(server: false)은 「문서 화면에서 진행합니다」 로 보인다(그 묶음의 상태를 여기서 지어내지 않는다) —
//   그래도 그 묶음의 「한 번에 진행」 은 누르면 돈다: 문서 화면을 열고 그 화면의 대시보드 단추를 누른다(hdAway — 2026-11-20 사용자 "실제 실행할 수 있는 버튼이 있는 워크플로우야. 그림만 보여주는게 아냐"). 취합의 「워크플로우 시작」 도 문서 화면으로(homeFilesGo).
// 상태 넷(hdState): pick = 워크플로우를 안 골랐다(고르기 목록) · ready = 골랐고 시작 전(등록부의 단계 흐름 · 문서 칸 · 「워크플로우 시작」) · live = 시작한 뒤(서버 상태 — 묶음의 「한 번에 진행」 · 「멈춤」 · 「대시보드 자세히 보기」) ·
//   gone = 그 작업을 못 찾음(지웠거나 서버가 옛 판). wait = 시작한 묶음의 상태를 아직 못 읽음(처음 한 번).
// 읽히는 차례: dashboard.js · workflow_exec.js 다음. 기대는 이름 — app.js: state · $ · el · hBtn · toast · openWork · showTab · fmtDur · PEEK · homeTaskBusy / panel_help.js: hHelp · panelHelpOwner · panelHelpClose /
//   task_catalog.js: TASK_CATALOG · TASK_STAGE_META · taskAcceptOf / dashboard.js: DASH(reg · regErr) · dashRegLoad · dashTags / workflow_exec.js: flowGet · flowLive · flowActive · flowStart · flowStop · flowWord · flowEnd · flowBy /
//   home_files.js: hf · hfTarget · hfExt · hfHas · homeFilesStart · homeFilesDraw(놓은 문서 ↔ 대시보드 — 그 파일이 homeDashDocs · homeDashFiles · homeDashFilesGone 을 부른다). doc_agent_work.js 의 homeAgentBind 가 상자(#homeDash)를 만들고, homeAgentDraw · homeAgentAct 가 homeDashDraw · homeDashPick 을 부른다.

// job = 고른 워크플로우 · wid = 시작한 묶음의 목적 문서 작업 id · view = 서버가 센 상태(flowGet) · gone = 그 작업이 없다(404) · err = 상태를 못 읽은 까닭 · note = 머리 아래 알림 {text, warn}(거절 글 · 시작의 알림) ·
// busy = 이 보기가 보낸 요청("start" · "run:<묶음>" · "away:<묶음>"(문서 화면을 여는 중) · "stop") · sig = 마지막으로 그린 것의 서명 · at = 마지막으로 상태를 읽은 때 · reading/again/living = 읽는 중 · 끝나면 한 번 더 · 확인 폴링 중 ·
// seq = 고름 · 비움의 차례(늦게 온 답을 버린다) · away = 문서 화면에 다녀왔다(돌아오면 바로 다시 읽는다) · regWait = 등록부를 읽는 중 · regTried = 등록부에 없어 다시 읽어 본 워크플로우
// form = 목적 문서 칸을 저장한 양식으로 할지 사람이 고른 것(true 양식 · false 목록의 파일 · undefined 저절로 — home_files.js hfUseForm: 고정이면 늘 양식 · 기본값이면 목록에서 목적 문서를 직접 안 골랐을 때)
// open = 편 단계 key(null = 「지금」 단계를 저절로 · "" = 모두 접음 — 「지금」 이 바뀌면 null 로: 패널 대시보드의 DASH.open 과 같은 약속) · nowKey = 마지막으로 그린 「지금」(도는 중) 단계 ·
// pin = 편 카드에서 방금 「했음」 을 눌렀다(그 누름으로 「지금」 이 넘어가도 그 카드를 접지 않는다 — 「했음 취소」 가 보이게: 한 번만) ·
// prev = 왼쪽에 문서를 놓아 시작 전으로 바꾸기 전에 보던 작업 {job, wid}(목록을 다시 비우면 그 작업으로 돌아간다 — homeDashFiles · homeDashFilesGone) · docKey = 왼쪽 목록에 보인 대시보드 문서의 열쇠(바뀌면 목록을 다시 그린다)
const HD = { job: "", wid: "", view: null, gone: false, err: "", note: null, busy: "", sig: "", at: 0, reading: false, again: false, living: false, seq: 0, away: false, regWait: false, regTried: "", form: undefined, open: null, nowKey: "", pin: false, prev: null, docKey: "", reset: dashResetFresh() };
// reset = 발 줄의 「작업 내용 초기화…」 상태(dashboard.js dashResetParts — 패널 대시보드와 같은 것)
const HD_KEY = "nfm.homeDash"; // 시작한 묶음의 기억(이 브라우저 — {job, wid}): 첫 화면을 다시 열어도 그 대시보드가 보인다 · 「새 워크플로우 시작」(시작 전에는 「다른 워크플로우」)으로 비운다
const HD_HELP = "대시보드에서 워크플로우의 단계와 진행 상황을 보고 바로 실행할 수 있습니다.\n"
  + "문서 화면의 패널 탭 「대시보드」 와 같은 것입니다. 왼쪽 번호는 차례입니다 — 누르면 그 차례만 실행하고, 끝난 차례는 초록 ✓ 로 표시합니다. 오른쪽은 그 차례의 문서 카드(원본 문서 · 목적 문서)입니다 — 카드를 누르면 펴지고(지금 상태 · 단추), 이름 옆 메모 아이콘에 그 단계의 「하는 일 · 조건」 이 있습니다.\n"
  + "실행을 눌러도 이 화면에 머뭅니다 — 단계마다의 확인 · 보정 단추는 문서가 열려 있어야 해서, 편 카드의 「문서 화면에서 열기」 나 「대시보드 자세히 보기」 로 문서 화면에서 합니다.\n"
  + "왼쪽 문서 목록과 문서 칸은 같은 문서를 가리킵니다 — 시작한 작업을 보이는 동안 왼쪽에는 그 작업의 문서가 보이고, 새 문서를 놓으면 문서 칸이 그 문서로 바뀌어 시작 전으로 돌아갑니다(하던 작업은 그대로 — 놓은 목록을 비우면 다시 보입니다).\n"
  + "「워크플로우 시작」 은 왼쪽 문서 목록으로 문서를 준비합니다(올리기 · 프로젝트로 묶기 · 기본 분석) — 실행은 그 뒤 묶음의 「한 번에 진행」 을 누를 때만 하고, 누르면 확인 창 없이 바로 합니다(유료 LLM · 문서가 바뀌는 묶음은 단추의 풍선 도움말에 적습니다).\n"
  + "묶음 머리의 「한 번에 진행」 은 그 묶음의 남은 단계를 차례로 하고, 머리 아래 「이어서 한 번에」 는 남은 묶음을 차례로 잇습니다(사람이 봐야 할 곳에서는 멈추거나 남깁니다). 끝나면(멈춤이 아니면) 바뀐 문서의 고친 문단을 확정합니다.\n"
  + "「문서 화면에서 진행합니다」 라고 적힌 묶음은 아직 서버가 맡지 않은 묶음입니다 — 그 묶음의 「한 번에 진행」 은 문서 화면을 열고 그 화면의 대시보드에서 진행합니다(취합의 「워크플로우 시작」 도 문서 화면을 엽니다).\n"
  + "꼬리표 아이콘 — 사람(파랑) · 스크립트(</>) · LLM(보라 반짝임) · 문서 바뀜(주황 문서+연필) — 마우스를 올리면 이름이 보입니다. 「필수」 는 해야 다음으로 가는 단계, 점선 단계(「선택」)는 안 해도 되는 단계, 「준비 중」 은 아직 없는 단계입니다.";
// 그리기 문맥 — 패널 대시보드와 같은 그리기(dashboard.js dashGroupsEl · dashNodeEl · dashDetailEl · dashMemoEl)를 이 보기의 초점 이름 · 펴고 접기로 쓴다.
// 끝난 수 = 서버가 센 줄 가운데 필수 줄(준비 줄 포함 — 패널 대시보드의 셈과 같다: 「1단계 문서 검토 1/3」). 서버가 안 맡은 묶음의 줄은 상태가 없어 세지 않는다(「n개 단계」)
const HD_CTX = { focus: "hdFocus", id: "homeDashD", panel: false, job: () => HD.job, counted: (n) => !n.optional && !n.soon && !!n.live,
  toggle: (key, open) => { HD.open = open ? "" : key; homeDashDraw(true); }, go: (key) => { HD.open = key; homeDashDraw(true); } };

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
  Object.assign(HD, { job, wid: "", view: null, gone: false, err: "", note: null, busy: "", at: 0, reading: false, again: false, living: false, form: undefined, open: null, nowKey: "", pin: false, prev: null, reset: dashResetFresh() });
  hdMemo(null);
}

// ---------------------------------------------------------------- 놓은 문서 ↔ 대시보드(2026-11-21 사용자 — 첫 화면을 보이며 "올려놓은 문서랑 대시보드랑 매칭이 안되잖아" · "놓여진 문서랑 매칭을 해주라는거야")
// 왼쪽 문서 목록과 이 대시보드의 문서 칸은 늘 같은 문서를 가리킨다(spec_작업에이전트 ② §10 「놓은 문서와 대시보드」):
//  ⓐ 목록이 비어 있고 이 보기가 시작한 작업을 보이면 → 왼쪽 카드에 그 작업의 문서(역할 · 이름 — 서버가 본 문서 칸 그대로)를 보인다(home_files.js homeFilesDraw — homeDashDocs)
//  ⓑ 시작한 작업을 보이는 동안 왼쪽에 문서를 새로 놓으면 → 같은 워크플로우의 시작 전(②)으로 바꿔 문서 칸이 놓은 문서를 따른다(homeDashFiles) — 하던 작업 · 도는 실행은 그대로(이 보기만)이고,
//     목록을 다시 비우면(「비우기」 · 다 빼기) 그 작업의 대시보드로 돌아간다(homeDashFilesGone). 「워크플로우 시작」 이 되면 새 작업이 그 자리를 잇는다.
// 기억(hdMemo)은 하던 작업에 남긴다 — 새로 고치면 목록(브라우저 메모리)이 비고 대시보드는 하던 작업이라 ⓐ 로 맞는다
// state = 워크플로우의 진행(목적 문서 카드의 「완료」 · 「진행 중」 — 대시보드 머리와 같은 셈 hdTally): {all, done, total, run(도는 실행 · 진행 중인 줄), bad(실패 · 막힌 줄 — 머리처럼 진행 중 · 「다음」 줄이 없을 때만: 뒤 줄은 앞 줄을 기다리며 막힘으로 보인다)}
function homeDashDocs() { // 왼쪽 목록에 보일 대시보드의 문서 → {job, name, rows: [{role, label, name, id}], state} | null(시작한 작업을 아직 못 읽음 · 시작 전)
  if (!HD.wid || !HD.view || HD.gone) return null;
  const V = HD.view, job = V.job || HD.job, reg = hdReg(job), docs = V.docs || {}, many = (docs.sources || []).length > 0, T = hdTally(V, false);
  const run = T.runs.length > 0 || !!T.runNode, state = { all: T.all, done: T.done, total: T.total, run, bad: !run && !T.nowNode && !!T.badNode }; // 머리 한 줄의 차례(진행 중 › 다음 › 확인 필요)와 같게
  const roles = reg && (reg.roles || []).length ? reg.roles : [...(docs.source || many ? [{ role: "source", title: "원본 문서", name: "", many }] : []), { role: "target", title: "목적 문서", name: "" }]; // 등록부가 없으면 역할 이름만(hdLiveDocs 와 같다)
  const rows = [];
  for (const r of roles) for (const d of (r.many ? docs.sources || [] : [docs[r.role]]).filter((x) => x && x.name)) rows.push({ role: r.role, label: `${r.title}${r.name ? ` — ${r.name}` : ""}`, name: d.name, id: d.id || "" });
  return { job, name: hdName(job), rows, state };
}
function homeDashFiles() { // ⓑ 왼쪽에 문서를 새로 놓았다(home_files.js homeFilesAdd — 목록에 더한 뒤 그리기 전에 부른다)
  if (!HD.wid || HD.busy) return;
  const prev = { job: HD.job, wid: HD.wid }, job = (HD.view && HD.view.job) || HD.job, cat = hdCat(job), was = homeDashDocs(), tname = was && (was.rows.find((r) => r.role === "target") || {}).name;
  hdClear(cat && !cat.soon ? job : "");
  HD.prev = { ...prev, at: HD.job }; // at = 바꾼 뒤의 워크플로우(그 사이 다른 워크플로우를 고르면 돌아가지 않는다)
  hdMemo(prev); // 기억은 하던 작업에 — 새로 고치면 목록이 비어 그 작업이 보인다(ⓐ)
  HD.note = { text: `왼쪽에 놓은 문서로 문서 칸을 바꿨습니다 — 하던 작업${tname ? `(목적 문서 「${tname}」)` : ""}은 그대로이고, 왼쪽 목록을 비우면 다시 보입니다`, warn: false };
  homeDashDraw(true);
  if (typeof hfFormsLoad === "function") hfFormsLoad();
}
function homeDashFilesGone() { // 왼쪽 목록이 비었다(home_files.js homeFilesDraw) — ⓑ 로 바꾸기 전에 보던 작업이 있으면 그 대시보드로 돌아간다(시작 중 · 다른 워크플로우를 고른 뒤에는 안 돌아감)
  const p = HD.prev;
  if (!p || HD.wid || HD.busy || HD.job !== p.at) return;
  hdClear(p.job);
  Object.assign(HD, { wid: p.wid });
  hdMemo({ job: p.job, wid: p.wid });
  homeDashDraw(true);
  if (hdFront()) hdRead();
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

function homeDashReset() { // 「새 워크플로우 시작」(시작한 뒤) · 「다른 워크플로우」(시작 전) — 이 대시보드를 비우고 고르기로
  if (HD.busy === "start") return;
  hdClear("");
  homeDashDraw(true);
  if (typeof homeFilesDraw === "function") homeFilesDraw();
}

// ---------------------------------------------------------------- 워크플로우 카드로 시작 · 「New」 · 라운드(spec_작업에이전트 ② §10 「새 작업 — 카드 · New · 라운드」)
// 2026-11-24 사용자(새 워크플로우 카드를 누른 첫 화면 — 왼쪽 「대시보드의 문서」 에 앞 워크플로우의 문서가 남은 것을 보며) "새작업의 시작인데 왜 연차보고서가 남아 있나?" ·
// "프로젝트 오른쪽에 라운드 기능이랑 New 버튼 만들면 될거 같고" → 답 「첫 화면」 · New = 「새 작업」.
// 워크플로우 카드의 시작(app.js homeTaskStart · home_files.js homeFilesGo · hfStartForm(stay false) — 문서 화면을 여는 길)은 이 보기를 거치지 않아, 기억(hdMemo)이 앞 작업에 남아
// 여는 동안 왼쪽에 앞 작업의 문서가 보이고 첫 화면으로 돌아와도 앞 작업이 보였다. 이제 카드를 누르면 앞 작업의 보기를 바로 걷고(그 워크플로우의 시작 전 — 작업 · 문서 · 도는 실행은 그대로),
// 시작하면 그 작업을 기억한다. 대시보드의 「워크플로우 시작」(hdStart)이 부른 길이면(HD.busy start) hdStart 가 맡는다.
function homeDashCardStart(job) {
  if (HD.busy === "start") return;
  const cat = hdCat(job);
  hdClear(cat && !cat.soon ? job : "");
  homeDashDraw(true);
  if (typeof homeFilesDraw === "function") homeFilesDraw();
}
function homeDashCardDone(job, wid) { // 카드로 시작했다(wid = 연 작업 — 그 묶음의 어느 문서든 서버가 묶음을 찾는다) — 첫 화면으로 돌아오면 이 작업의 대시보드 · 문서
  if (HD.busy === "start" || !wid) return;
  hdClear(hdCat(job) ? job : "");
  Object.assign(HD, { wid, away: true });
  hdMemo({ job: HD.job, wid });
  homeDashDraw(true);
}
// 「New」 = 새 작업: 보던 작업의 프로젝트 · 워크플로우 그대로 새로 시작한다 — 이 보기를 그 워크플로우의 시작 전으로 걷고 왼쪽 프로젝트 칸에 그 프로젝트를 적어 둔다(문서를 놓고 시작하면 그 프로젝트의 다음 라운드).
// 보던 작업은 지우지 않는다(라운드 목록 · 최근 작업에서 다시 본다)
function homeDashNew(project) {
  if (HD.busy === "start" || (typeof homeTaskBusy !== "undefined" && homeTaskBusy)) return;
  const job = (HD.view && HD.view.job) || HD.job, cat = hdCat(job);
  hdClear(cat && !cat.soon ? job : "");
  if (typeof hf === "object") { hf.project = project || ""; hf.err = ""; }
  HD.note = { text: `새 작업 — ${project ? `프로젝트 「${project}」 · ` : ""}워크플로우 「${hdName(HD.job)}」 로 새로 시작합니다. 왼쪽에 문서를 놓고 「워크플로우 시작」 을 누르세요(보던 작업은 그대로 — 최근 작업에서 다시 엽니다)`, warn: false };
  homeDashDraw(true);
  if (typeof homeFilesDraw === "function") homeFilesDraw();
  if (typeof hfFormsLoad === "function") hfFormsLoad();
}
function homeDashRound(wid) { // 라운드 고르기 — 같은 프로젝트 · 워크플로우의 다른 라운드(그 라운드의 목적 문서 작업)의 대시보드를 본다(문서 화면을 열지 않는다)
  if (!wid || wid === HD.wid || HD.busy) return;
  const job = (HD.view && HD.view.job) || HD.job;
  hdClear(hdCat(job) ? job : "");
  Object.assign(HD, { wid });
  hdMemo({ job: HD.job, wid });
  homeDashDraw(true);
  if (hdFront()) hdRead();
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
    if (HD.note && HD.note.busy && HD.note.at <= began && view && !hdRuns(view).length) HD.note = null; // 「다른 화면에서 진행 중입니다」 — 그 실행이 끝났다
    if (view && view.job && view.job !== HD.job) { HD.job = view.job; hdMemo({ job: HD.job, wid }); } // 그 작업의 워크플로우가 문서 화면에서 바뀌었다 — 서버의 것을 따른다
  }
  if (HD.again) { HD.again = false; hdRead(); return; }
  homeDashDraw();
}

// 문서마다 따로 도는 실행(spec_워크플로우 ② §18-22 — 2026-11-21 사용자 "원본문서랑, 목적문서를 따로따로 실행해서 처리할 수 있잖아? 매칭은 1개 실행이 같이 해야하고"): 도는 실행은 둘일 수 있다(서버 상태의 runs —
// 문서 하나만 잡은 실행 lane = source | target). hdRuns = 도는 실행들 · hdTakes(잡을 문서) = 그 단추를 꺼야 하나 — "source" | "target" = 그 문서를 잡은 실행이 있다 · "" = 도는 실행이 하나라도 있다(두 문서를 함께 쓰는 일)
const hdRuns = (V) => (V ? (V.runs || (V.run ? [V.run] : [])).filter(flowActive) : []);
const hdTakes = (V, lane = "") => { const rs = hdRuns(V); return lane ? rs.some((r) => !r.lane || r.lane === lane) : rs.length > 0; };
const HD_WAIT = "지금 진행 중인 작업이 끝나면 쓸 수 있습니다";

async function hdLive() { // 도는 실행의 확인(1초 — 메모리만 읽는 끝점): 글만 바꾼다. 끝났거나 다른 실행이거나 단계가 넘어갔으면 상태를 다시 읽는다(끝 글 · 끝난 수 · 단계의 상태)
  const was = hdRuns(HD.view);
  if (HD.living || HD.reading || !HD.view || !was.length) return;
  const seq = HD.seq;
  HD.living = true;
  let runs = null;
  try { runs = (await api(flowUrl(HD.wid, "/live"))).runs || []; } catch { runs = null; } // 이 묶음의 도는 실행들(목적 문서를 잡지 않은 원본 문서의 실행도)
  if (seq !== HD.seq) return;
  HD.living = false;
  if (!HD.view || HD.reading) return;
  if (!runs || runs.length !== was.length || runs.some((r, i) => !flowActive(r) || r.n !== was[i].n)) { hdRead(); return; }
  const moved = runs.some((r, i) => (r.now || {}).stage !== (was[i].now || {}).stage || (r.now || {}).key !== (was[i].now || {}).key);
  Object.assign(HD.view, { runs, run: runs.find((r) => HD.view.run && r.n === HD.view.run.n) || runs[0] });
  if (moved) hdRead(); else homeDashDraw();
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
    if (ok && state.id) { Object.assign(HD, { wid: state.id, view: null, gone: false, err: "", away: true, prev: null }); hdMemo({ job, wid: state.id }); }
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
      Object.assign(HD, { wid: (v.docs && v.docs.target && v.docs.target.id) || r.opened, view: v, gone: false, err: "", at: Date.now(), prev: null });
      hdMemo({ job, wid: HD.wid });
    } else toast("다른 워크플로우의 작업입니다 — 문서 화면에서 여세요", true);
    homeDashDraw(true);
    return;
  }
  Object.assign(HD, { wid: r.id, view: null, gone: false, err: "", prev: null });
  hdMemo({ job, wid: r.id });
  const left = (r.failed || []).length ? `올리지 못한 문서(${r.failed.map((n) => `「${n}」`).join(" · ")})는 왼쪽 문서 목록에 남겼습니다 — 「대시보드 자세히 보기」 로 문서 화면을 열어 「작업 개요」 의 첨부 파일 칸에서 올리세요` : "";
  if (r.note || left) HD.note = { text: [r.note, left].filter(Boolean).join("\n"), warn: !!left };
  homeDashDraw(true);
  await hdRead();
}

// 묶음의 「한 번에 진행」 — 서버 쪽 실행기에 시작을 청한다(확인 창 없이 바로: design.md §18 · 유료 LLM · 문서 바뀜은 단추의 풍선 도움말과 꼬리표에).
// 이 보기가 본 문서 칸 · 정의의 지문을 같이 보낸다 — 그 사이 문서 화면에서 칸이나 단계가 바뀌었으면 서버가 시작하지 않고 까닭을 돌려준다(본 것과 다른 것을 돌리지 않는다).
// 두 자리(이 화면 · 문서 화면)에서 잇달아 눌러도 서버의 잠금이 한 번만 돌린다 — 거절(이미 도는 실행 포함)은 그 글을 머리 아래 한 줄로.
// 범위 셋(서버의 같은 끝점 — spec_워크플로우 ② §18-4 「범위의 세 진입」): 묶음 하나(from) · 「이어서 한 번에 N→M단계」(from → to: 경계마다 최신 상태로 그 묶음을 할지 서버가 정한다 — 문서 화면의 taskRunAll(처음, 끝)과 같은 요청) ·
// 차례 하나(only = 줄 key + row — 왼쪽 차례 열의 번호 단추: 문서 화면의 줄 단추 「분석」 · 「다시 분석」 과 같은 길 · row = 같은 차례에 선 옆 줄도 함께). busy = 이 요청의 이름(다른 단추를 끄는 까닭) → 서버의 답 | null(보내지 않음 · 그 사이 비움)
async function hdSend(busy, body) {
  if (HD.busy || !HD.wid || !HD.view) return null;
  const seq = HD.seq, V = HD.view, docs = V.docs || {};
  Object.assign(HD, { busy, note: null });
  homeDashDraw(true);
  const r = await flowStart(HD.wid, { ...body, where: "home", sig: V.sig || "", docs: { target: (docs.target || {}).id || null, source: (docs.source || {}).id || null } });
  if (seq !== HD.seq) return null;
  HD.busy = "";
  const put = (run) => { if (HD.view) Object.assign(HD.view, { runs: [...hdRuns(HD.view).filter((x) => x.n !== run.n), run].sort((a, b) => a.n - b.n), run }); }; // 서버 상태를 다시 읽기 전에도 그 실행이 도는 것으로(진행 줄 · 그 문서의 단추)
  if (r.ok) { put(r.run); if (HD.view) HD.view.last = null; }
  else {
    HD.note = { text: r.message || "시작하지 못했습니다", warn: true, busy: r.reason === "busy", at: Date.now() }; // busy = 「다른 화면에서 진행 중입니다 …」 — 그 실행이 끝나면 걷는다(hdRead: 이 알림 뒤에 시작한 읽기만)
    if (r.run && HD.view && !hdRuns(HD.view).some((x) => x.n === r.run.n)) put(r.run); // 다른 화면에서 이미 도는 실행 — 그 실행을 그대로 보인다
  }
  homeDashDraw(true);
  hdRead();
  return r;
}
const hdRun = (gid, to = "") => hdSend(to ? "run:chain" : `run:${gid}`, { from: gid, ...(to ? { to } : {}) });
const hdRunSolo = (gid, role) => hdSend(`solo:${gid}:${role}`, { from: gid, role }); // 한 문서만 — 그 묶음에서 그 문서의 줄만(spec_워크플로우 ② §18-21 · 패널 대시보드의 「원본 문서만」 · 「목적 문서만」 과 같은 요청)

// 차례 번호를 눌렀다 — 그 차례의 줄을 서버 실행으로(2026-11-20 사용자 "그 번호를 누르면 그 순위에 있는게 자동 실행되고"). 한 번의 시작이다: only = 그 차례의 줄 · 같은 차례에 다른 줄이 서 있으면(조립한 워크플로우의 같은 행)
// row 로 그 줄도 함께(서버가 서로의 문서를 건드리지 않으면 같이 · 아니면 앞 줄 먼저 돈다 — spec_워크플로우 ② §18-4 「같은 차례 — 함께 돌기」). 앞 차례가 남았으면 서버의 처리 함수가 하지 않고 그 까닭으로 멈춘다(끝 글 한 줄 — 화면이 차례를 따로 따지지 않는다)
const hdRunOrder = (gid, o) => hdSend(`go:${gid}:${o.idx}`, { from: gid, only: o.key, ...(o.nodes.length > 1 ? { row: true } : {}) });

async function hdStop(n) { // 「멈춤」 — 지금 하는 일이 끝나면 멈춘다(어느 화면이 시작한 실행이든)
  if (HD.busy || !HD.wid) return;
  const seq = HD.seq;
  HD.busy = "stop";
  homeDashDraw(true);
  const ok = await flowStop(HD.wid, n);
  if (seq !== HD.seq) return;
  HD.busy = "";
  if (ok && HD.view) for (const x of [HD.view.run, ...(HD.view.runs || [])]) if (x && x.n === n) x.stopping = true;
  homeDashDraw(true);
  hdRead();
}

// 「대시보드 자세히 보기」 — 그 목적 문서를 열고 패널 탭 「대시보드」 로(단계마다의 확인 · 보정 · 문서 화면에서 진행하는 묶음은 거기서).
// key = 편 카드의 「문서 화면에서 열기」 — 그 화면의 대시보드에서 같은 단계를 펴 둔다(dashShow 가 문서를 바꿀 때 DASH.open 을 비운 뒤에 적는다 — showTab 은 그 비움까지 그 자리에서 한다)
async function hdMore(wid, key = "") {
  await openWork(wid);
  if (state.id !== wid) return;
  showTab("Dash");
  if (key && typeof dashDraw === "function") { DASH.open = key; dashDraw(true); }
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

// ---------------------------------------------------------------- 그릴 것 — 묶음 › 차례(얇은 번호 열) › 문서 카드
// 2026-11-20 사용자 "앞 페이지에서는 대시보드가 2열 이어야 겠지? 내 생각에는 얇은 열에 순서만 놓고 순서되면 원본/목적 문서에 대한 카드만 위아래로 보여주면 될거 같은데" ·
// "그 번호를 누르면 그 순위에 있는게 자동 실행되고.. 실행된건 실행표기하면 좋을듯": 묶음 안은 **두 열**이다 — 왼쪽 얇은 열 = 차례 번호(누르면 그 차례를 실행하는 단추 · 끝난 차례는 초록 ✓) ·
// 오른쪽 = 그 차례의 **문서 카드를 위아래로**(두 문서에 하는 줄은 「원본 문서」 · 「목적 문서」 카드 둘 · 「원본 → 목적」 · 「워크플로우 전체」 줄과 문서 하나인 워크플로우는 카드 하나).
// 차례 = 줄 하나(조립한 워크플로우의 같은 행 — 줄의 beside — 은 한 차례에 선다). 카드는 패널 대시보드의 단계 카드와 같은 그리기다(dashboard.js dashNodeEl — 번호 동그라미만 왼쪽 열로 나갔다).
// V 가 없으면 등록부만(시작 전 — 문서를 읽기 전이라 끝난 수 · 상태 글이 없다), 있으면 서버가 낸 묶음에 등록부의 꼬리표 · 준비 중인 단계를 얹는다. 상태(st · done · 건너뜀 · 문서마다의 몫 per · 할 수 있나)는 서버 것 그대로다
const HD_HAND = /^hand[1-9][0-9]?$/; // 사람이 하는 일 줄(정의 v2 — spec_워크플로우 ② §18-7)
const HD_ON = { source: "원본 문서", target: "목적 문서", pair: "원본 → 목적", flow: "워크플로우 전체" }; // 등록부를 못 읽었을 때의 문서 꼬리표(읽었으면 등록부의 말 — 역할의 title · 단계의 onText)

function hdGroups(reg, V, cards = true) { // cards = 차례마다의 문서 카드도 짓나(셈만 하는 hdTally(V, false) 는 단추를 짓지 않는다)
  const meta = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META, stages = reg ? reg.stages : [], roles = (reg && reg.roles) || [];
  const rows = V ? V.stages.map((sv) => [sv, stages.find((g) => g.id === sv.id) || null]) : stages.map((rg) => [null, rg]);
  const wid = V ? (V.docs && V.docs.target && V.docs.target.id) || HD.wid : "";
  let i = 0;
  return rows.map(([sv, rg], gi) => {
    const one = sv || rg, m = rg && rg.meta ? meta[rg.meta] : null, served = !!(sv && sv.server && sv.steps), live = served ? sv.steps : [];
    const base = rg ? rg.steps : live.map((x) => ({ key: x.key, name: x.name, by: [], change: "", auto: false, optional: !!x.optional, soon: false, on: x.on || "", beside: !!x.beside, does: "", out: "", cond: [] })); // 등록부에 없는 묶음(정의가 방금 바뀜) — 서버가 낸 줄만
    const no = m ? m.no : one.no || String(gi + 1), name = m ? m.name : one.name || ""; // 번호 · 이름 = 패널 대시보드와 같은 셈(취합은 TASK_STAGE_META)
    const nodes = base.map((s) => { const x = live.find((y) => y.key === s.key) || null; return { ...s, live: x, state: s.soon ? "soon" : x ? (x.done ? "done" : x.st) : "" }; }); // 줄(등록부의 단계) — 끝난 수 · 「다음: …」 은 줄로 센다
    const orders = [];
    for (const n of nodes) { if (n.beside && orders.length) orders[orders.length - 1].nodes.push(n); else orders.push({ idx: ++i, nodes: [n] }); }
    for (const o of orders) {
      for (const n of o.nodes) n.idx = o.idx;
      Object.assign(o, { no: hdPad(o.idx), key: o.nodes[0].key, state: hdOrderState(o.nodes), cards: cards ? o.nodes.flatMap((n) => hdCards(n, roles, wid, !!V)) : [] });
    }
    return { id: one.id, no, name, label: { no, name }, does: (rg && rg.does) || (sv && sv.does) || "", sv, served, nodes, orders };
  });
}

// 시작한 뒤의 셈 — 머리의 「끝남 n/m」 · 「모두 끝남」(hdLiveParts)과 왼쪽 「대시보드의 문서」 목적 문서 카드의 「완료」 · 「진행 중」(homeDashDocs → home_files.js hfDashDraw)이 이 하나를 쓴다.
// all = 머리가 「모두 끝남」 이라 적는 때 그대로: 도는 실행 · 진행 중 · 지금 · 실패 · 막힌 줄이 없고, 모든 묶음을 서버가 세며 남은 것이 없음
function hdTally(V, cards = true) {
  const job = V.job || HD.job, reg = hdReg(job), groups = hdGroups(reg, V, cards), runs = hdRuns(V), served = groups.filter((g) => g.served);
  const nodes = groups.flatMap((g) => g.nodes), counted = nodes.filter(HD_CTX.counted), total = counted.length, done = counted.filter((n) => n.state === "done").length; // 끝난 수 = 패널 대시보드의 셈(준비 줄 포함 · 선택 줄 빼고 — 서버가 센 줄만)
  const runNode = nodes.find((n) => n.state === "run"), nowNode = nodes.find((n) => n.state === "now"), badNode = nodes.find((n) => n.state === "failed" || n.state === "blocked");
  const left = served.some((g) => g.sv.left > 0), all = !runs.length && !runNode && !nowNode && !badNode && !!groups.length && !left && served.length === groups.length && total > 0;
  return { job, reg, groups, runs, served, nodes, total, done, runNode, nowNode, badNode, left, all };
}

function hdOrderState(nodes) { // 차례의 상태(번호 단추의 색 · 표시) — 그 차례의 줄들로: 진행 중 › 실패 · 막힘 › 모두 끝남 › 지금 › 남음 / 준비 중 / 상태 없음(시작 전 · 서버가 안 맡은 묶음)
  const st = nodes.map((n) => n.state), real = st.filter((s) => s && s !== "soon");
  if (!real.length) return st.length && st.every((s) => s === "soon") ? "soon" : "";
  return real.includes("run") ? "run" : real.includes("failed") ? "failed" : real.includes("blocked") ? "blocked" : real.every((s) => s === "done") ? "done" : real.includes("now") ? "now" : "todo";
}

function hdRoleEl(role, r, n) { // 카드 머리의 문서 꼬리표 — 「원본 문서」 · 「목적 문서」 · 「원본 → 목적」 · 「워크플로우 전체」(등록부의 말) | null(문서 하나인 워크플로우 — 문서가 하나라 적지 않는다)
  const org = role === "source" && typeof orgIsGather === "function" && orgIsGather((HD.view && HD.view.job) || HD.job); // 취합 — 문서 하나를 가리키지 않는 기관 문서 꼬리표는 「[기관]」(spec_취합 ② §11 · org_short.js — 패널 대시보드 dashFlowRoleEl 과 같다)
  const doc = role === "source" || role === "target", head = org ? "[기관]" : doc ? (r ? `${r.title}${r.many ? "마다" : ""}` : HD_ON[role]) : (n.onText || "").split(" — ")[0] || HD_ON[role] || "";
  if (!head) return null;
  const t = el("span", "hd-role", head);
  t.dataset.role = role;
  t.title = org ? `기관 문서${r && r.many ? "마다" : ""} — ${(r && r.name) || "기관 문서"}` : doc ? (r ? `${r.title} — ${r.name}${r.many ? "(문서마다)" : ""}` : head) : n.onText || head;
  return t;
}

// 줄 하나 → 그 줄의 문서 카드들(위아래로 — 원본 → 목적 차례). 카드 = 패널 대시보드의 단계 카드가 그리는 꼴(dashNodeEl · dashDetailEl): state · word(상태 글) · text · lines · acts.
// 상태 · 글은 서버가 센 것 그대로 — 두 문서에 하는 줄은 서버가 준 문서마다의 몫(per)으로 카드마다 다르게, 없으면 줄의 것을 두 카드에 같이. 시작 전과 서버가 안 맡은 묶음의 카드에는 상태가 없다 —
// 등록부의 「하는 일」 · 「하려면」 을 본문에 채우지 않는다(이름 옆 메모에 있다 — 2026-11-21 사용자 「설명문은 노트에 넣도록 했잖아. 왜 여기에 다 넣는거야」): 펼 것이 없으면 본문 없이 고른 테두리만(dashNodeEl).
// 단추: 사람이 하는 일 줄의 「했음」 · 「했음 취소」 + (시작한 뒤) 「문서 화면에서 열기」 — 단계마다의 확인 · 보정 단추는 문서가 열려 있어야 해서 그 문서의 대시보드에 있다(같은 단계를 편 채로 연다)
function hdCards(n, roles, wid, started) {
  const x = n.live;
  const parts = n.on === "both" ? ["source", "target"] : [n.on || ""];
  const hand = HD_HAND.test(n.key) && x && HD.hands && HD.hands.wid === HD.wid ? HD.hands.lines.find((l) => l.key === n.key) : null;
  // 같은 양식 취합(task_catalog.js taskIsCollect — 원본 문서 = 기관 문서 여럿: spec_취합 ② §10) — 패널 대시보드(dashboard.js dashFlowLive)와 같은 약속: 기관 문서마다 도는 줄은 **기관 문서마다 카드**(서버의 per — 그 줄의 대상이 아닌 문서는 뺀다 · 없으면 줄의 글 하나) ·
  // 「반영할 기관 지정」 은 카드 하나(문서마다의 줄은 위 「기관 문서」 목록 — collect.js). 취합형으로 조립한 것(gather)은 전과 같다(원본 문서마다 — 카드 하나)
  const V = HD.view, many = started && x && typeof taskIsCollect === "function" && taskIsCollect((V && V.job) || HD.job), srcs = (many && V && V.docs && V.docs.sources) || [];
  const partName = ((roles.find((q) => q.role === "source") || {}).name) || "기관 문서";
  const slots = parts.flatMap((role) => {
    const doc = role === "source" || role === "target";
    if (many && role && role !== "target" && role !== "flow") {
      const per = n.key === "part" ? [] : (x.per || []).filter((q) => (q.role || "source") === "source" && !q.skipped);
      return per.length ? per.map((q) => ({ role, p: q, one: true })) : [{ role, p: null, one: false }];
    }
    return [{ role, p: x && doc ? (x.per || []).find((q) => q.role === role) || null : null, one: false }];
  });
  return slots.map(({ role, p, one }, ci) => {
    const ref = one ? `${n.key}@${role}:${p.doc}#${n.idx}` : `${n.key}@${role}#${n.idx}`; // 차례 번호까지 — 같은 줄을 두 번 놓은 정의는 key 가 겹친다
    const state = n.soon ? "soon" : !x ? "" : !p ? n.state : p.st === "done" ? "done" : p.st === "busy" ? "run" : p.st === "blocked" || p.st === "failed" ? p.st : x.st === "now" || x.st === "run" ? "now" : "todo";
    const skipped = !!(x && (p ? p.skipped : x.skipped));
    let lead = hdRoleEl(role, roles.find((q) => q.role === role) || null, n), text = !x ? "" : p ? p.text || "" : x.text || "";
    if (one) { // 기관 문서마다의 카드 — 꼬리표 = 「[기관 약칭] 파일 이름」(spec_취합 ② §11 — collect.js collectDocName) · 서버의 글 앞의 파일 이름은 뗀다(패널 대시보드와 같다)
      const file = (srcs.find((d) => d.id === p.doc) || {}).name || "", name = collectDocName(wid, p.doc, file), full = collectDocOrgs(wid, p.doc);
      lead = el("span", "hd-role collect-doc", name || partName);
      lead.dataset.role = "source";
      lead.dataset.doc = p.doc;
      lead.title = `${partName} — ${full ? `반영할 기관 ${full} · ` : ""}${file || name}`;
      if (file && text.startsWith(`${file} — `)) text = text.slice(file.length + 3);
    }
    const c = { ...n, idx: null, ref, role, state, skipped, word: n.soon ? "준비 중" : !x ? "" : state === "done" && skipped ? "건너뜀" : FLOW_WORD[state] || "",
      text: dashHere(text), lines: [], acts: [], via: null, lead }; // dashHere — 서버의 글이 「작업 개요」 안의 자리(「아래 「…」」)를 가리키면 그 패널 이름으로(패널 대시보드와 같다)
    if (hand && ci === 0) { // 「했음」 · 「했음 취소」 는 이 화면에서도(사람의 단추 — 에이전트 행동에는 없다)
      const b = hBtn(hand.done ? "했음 취소" : "했음", () => hdHand(hand, !hand.done, ref), { cls: "btn sm" + (hand.done ? "" : " primary"),
        title: hand.done ? "「했음」 을 되돌립니다 — 다음 실행이 이 줄에서 다시 멈춥니다" : `사람이 할 일 — ${hand.does}\n마쳤으면 누릅니다 — 묶음의 「한 번에 진행」 이 이 줄을 지나 다음 줄로 갑니다` });
      b.dataset.hdFocus = `hand:${n.key}`;
      c.acts.push(b);
    }
    if (started && !n.soon && wid) {
      const b = hBtn("문서 화면에서 열기", () => hdMore(wid, n.key), { cls: "btn sm", title: "이 단계의 확인 · 보정 단추는 문서 화면의 대시보드에 있습니다 — 목적 문서를 열고 패널 탭 「대시보드」 에서 이 단계를 폅니다" });
      b.dataset.hdFocus = `open:${ref}`;
      c.acts.push(b);
    }
    return c;
  });
}

function hdSig() { // 다시 그릴지 — 상태 · 글 · 단추가 같으면 도는 글(지난 시간)만 바꾼다(초점 · 스크롤 유지 — 패널 대시보드의 dashSig 와 같은 방식)
  const st = hdState(), V = HD.view, list = st === "pick" || st === "ready";
  return JSON.stringify([st, HD.job, HD.wid, HD.err, HD.note, HD.busy, HD.open, st === "live" && hdCollect(V) ? [collectSig(hdCollect(V)), typeof worksList !== "undefined" ? worksList.length : 0] : 0, /* 같은 양식 취합의 「기관 문서」 목록(collect.js) */ [HD.reset.open, HD.reset.busy, HD.reset.err, HD.reset.docs], HD.hands ? HD.hands.lines.map((x) => [x.key, x.done, x.ver]) : 0, !!DASH.reg, !!hdReg(HD.job), DASH.regErr,
    list ? [hdFiles().map((f) => `${f.name}:${f.size}`), typeof hfTarget === "function" ? hfTarget() : -1, !!homeTaskBusy || !!(typeof hf === "object" && hf.busy), Object.keys(TASK_CATALOG),
      HD.job ? [hdSlot(HD.job), HD.form, hdUseForm(HD.job), (hdResume(HD.job) || {}).id || "", typeof hf === "object" ? hf.project : ""] : 0] : 0,
    st === "live" ? [V.job, V.sig, V.ready, V.why, V.docs, V.stages.map((g) => [g.id, g.no, g.name, g.server, g.done, g.total, g.left, g.can, g.why, (g.paid || []).length, g.change, (g.solo || []).map((x) => [x.role, x.left, x.total, x.can, x.why, (x.paid || []).length]), // solo = 한 문서만 진행의 몫

      (g.steps || []).map((s) => [s.key, s.st, s.done, s.skipped, s.text, s.beside, (s.paid || []).length, (s.per || []).map((p) => [p.role, p.st, p.skipped, p.text])])]),
      hdRuns(V).map((r) => [r.n, r.lane || "", r.status, r.stopping, (r.now || {}).stage, (r.now || {}).key, (r.now || {}).note, flowBy(r)]), V.last ? [V.last.n, V.last.status, (V.last.end || {}).text] : 0, (V.lasts || []).map((x) => [x.n, x.status, (x.end || {}).text]),
      V.stages.map((g) => [g.lane || "", g.wait || "", (g.steps || []).map((s) => s.wait || "")])] : 0]); // lane · wait = 그 묶음이 잡는 문서 · 구성 값을 기다리는 까닭(② §18-22)
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
  Object.assign(HD, { wid: w.id, view: null, gone: false, err: "", prev: null, note: { text: `프로젝트 「${(w.task || {}).project || ""}」 에 하던 작업을 이어서 봅니다`, warn: false } });
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
  const n = (docs.sources || []).length; // 원본 문서가 여럿인 워크플로우(취합 · 같은 양식 취합) — 몇 개인지(같은 양식 취합의 문서마다의 줄은 아래 「기관 문서」 목록)
  return roles.map((r) => [r.role, `${r.title}${r.name ? ` — ${r.name}` : ""}:`, r.role === "source" && (r.many || n) && !docs.source ? (n ? `문서 ${n}개` : "") : (docs[r.role] || {}).name || ""]);
}

// 같은 양식 취합(task_catalog.js taskIsCollect — spec_취합 ② §10)의 대시보드인가 → 목적 문서 id | "" · 그 「기관 문서」 목록(collect.js collectListEl — 패널 대시보드의 「준비」 카드와 같은 함수: 반영할 기관 · 공통 자리 포함 · 수정본 · 자동 지정 · 올리기 · 수정 계획)
const hdCollect = (V) => (V && typeof taskIsCollect === "function" && taskIsCollect(V.job || HD.job) ? (V.docs && V.docs.target && V.docs.target.id) || "" : "");
function hdCollectEl(V, active) {
  const tid = hdCollect(V);
  if (!tid || typeof collectListEl !== "function") return null;
  const job = V.job || HD.job, row = typeof worksList !== "undefined" ? worksList.find((w) => w.id === tid) : null, t = (row && row.task) || null;
  const moving = active || V.stages.some((g) => (g.steps || []).some((s) => s.busy || s.st === "run")), box = el("div", "home-dash-collect");
  box.append(collectListEl(tid, { off: active ? HD_WAIT : HD.busy ? "요청을 보내는 중입니다" : "", focus: "hdFocus", stale: moving ? 3000 : 10000, redraw: () => homeDashDraw(true),
    scope: t && t.project ? { job, project: t.project, round: Math.max(1, Number(t.round) || 1), kind: taskCollectKind(job) } : null, // 올릴 묶음 = 목적 문서의 묶음(작업 목록에서 — 못 찾으면 올리기 단추를 세우지 않는다)
    after: () => hdRead(), uploaded: async () => { if (typeof loadWorks === "function") await loadWorks(); } }));
  return box;
}

// 차례 번호 단추(왼쪽 얇은 열) — 누르면 그 차례를 실행한다(hdRunOrder) · 끝난 차례는 초록 ✓(실행 표시 — 끝남은 서버가 문서의 결과로 센 것) · 도는 차례는 파랑 고리.
// 누를 수 없는 때는 꺼 두고 까닭을 풍선 도움말에: 시작 전 · 준비 중 · 도는 실행이 있음 · 끝난 차례 · 문서 칸이 빔. 서버가 아직 맡지 않은 묶음의 차례는 그 단계를 편 채 문서 화면을 열고(hdMore — 그 화면의 단추로 진행),
// 사람이 하는 일뿐인 차례는 그 카드를 편다(「했음」 은 사람이 누른다 — 번호가 대신 누르지 않는다)
function hdGoBtn(g, o, V, active, wid) {
  const names = o.nodes.map((n) => n.name).join(" · "), hand = o.nodes.every((n) => HD_HAND.test(n.key)), x0 = o.nodes.map((n) => n.live).filter(Boolean);
  // 이 차례가 잡는 문서 — 그 차례의 줄이 모두 같은 한 문서의 줄이면 그 문서만(다른 문서의 실행과 같이 돈다 — ② §18-22) · 아니면 두 문서(도는 실행이 하나라도 있으면 기다린다)
  const ons = new Set(o.nodes.map((n) => (n.on === "source" || n.on === "target" ? n.on : ""))), lane = ons.size === 1 ? [...ons][0] : "";
  const waits = x0.map((x) => x.wait || ""), wait = waits.length && waits.every(Boolean) ? waits[0] : ""; // 구성 값을 기다리는 줄뿐인 차례(서버의 wait — 「프로젝트 구성 추출」 이 먼저)
  let why = "", run = null, tip = "";
  if (o.state === "soon") why = "준비 중인 단계입니다";
  else if (!V) why = "「워크플로우 시작」 으로 문서를 준비하면 누를 수 있습니다";
  else if (!g.served) { run = () => hdMore(wid, o.key); tip = "이 차례는 아직 서버가 맡지 않아 문서 화면에서 진행합니다 — 누르면 목적 문서를 열고 그 화면의 대시보드에서 이 단계를 폅니다"; }
  else if (hand) { run = () => HD_CTX.go(o.cards[0].ref); tip = "사람이 하는 일입니다 — 누르면 카드를 폅니다(마친 뒤 그 카드의 「했음」)"; }
  else if (o.state === "done") why = "✓ 끝난 차례입니다";
  else if (hdTakes(V, lane)) why = "지금 진행 중인 작업이 끝나면 누를 수 있습니다";
  else if (HD.busy) why = "요청을 보내는 중입니다";
  else if (!V.ready) why = V.why || "문서 칸이 비었습니다";
  else if (wait) why = wait;
  else {
    const paid = new Set(x0.flatMap((x) => x.paid || [])).size;
    run = () => hdRunOrder(g.id, o);
    tip = ["이 차례만 실행합니다 — 눌러도 이 화면에 머뭅니다(서버에서 진행 · 창을 닫아도 이어집니다). 앞 차례가 남았으면 실행하지 않고 그 까닭을 알립니다.",
      paid ? `유료 LLM — 문서 ${paid}개` : "", o.nodes.some((n) => n.change === "doc") ? "문서가 바뀝니다" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n");
  }
  const b = el("button", "dash-no hd-go", o.no);
  b.type = "button";
  b.disabled = !run;
  b.title = `${o.no} ${names} — ${why || tip}`;
  b.setAttribute("aria-label", `${o.no} 차례 ${run && g.served && !hand ? "실행" : ""} — ${names}${o.state === "done" ? "(끝남)" : ""}`);
  b.dataset.hdFocus = `go:${g.id}:${o.idx}`;
  if (run) b.onclick = run;
  return b;
}

function hdOrdersEl(g, openKey, V, active, wid) { // 묶음의 차례들 — 줄마다 [번호 단추 | 문서 카드(위아래로)]
  const ol = el("ol", "dash-flow hd-rows");
  ol.setAttribute("aria-label", `${g.name}의 차례`);
  for (const o of g.orders) {
    const li = el("li", "hd-row"), cards = el("ul", "hd-cards");
    li.dataset.key = o.key;
    li.dataset.state = o.state || "none";
    if (o.state === "now" || o.state === "run") li.setAttribute("aria-current", "step");
    for (const c of o.cards) cards.append(dashNodeEl(c, g.id, openKey, HD_CTX));
    li.append(hdGoBtn(g, o, V, active, wid), cards);
    ol.append(li);
  }
  return ol;
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

async function hdHand(line, on, ref = "") { // 「했음」 · 「했음 취소」 — 사람의 단추(에이전트 행동에는 없다). ref = 누른 카드 — 그 누름으로 「지금」 이 넘어가도 접지 않는다(「했음 취소」 가 보이게: HD.pin)
  if (HD.busy || !HD.wid) return;
  if (ref) Object.assign(HD, { open: ref, pin: true });
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
    g.does ? `하는 일 — ${g.does}` : "", (sv.paid || []).length ? `유료 LLM — 문서 ${sv.paid.length}개` : "", sv.change ? "문서가 바뀝니다 — 끝나면 고친 문단을 확정합니다(앞 상태는 「고친 문단」 탭 확정 기록의 복원)" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n"); // 끝 확정(spec_워크플로우 ② §18-24)
  const b = hBtn(sending ? "시작하는 중…" : "한 번에 진행", () => hdRun(g.id), { cls: "btn sm" + (primary && !why ? " primary" : ""), disabled: !!why, title: tip });
  b.dataset.hdFocus = `run:${g.id}`;
  return b;
}

// 묶음 › 차례 — 묶음 머리 · 끝 글 · 틀은 패널 대시보드의 그리기(dashboard.js dashGroupsEl)이고, 묶음마다 이 보기의 것을 얹는다: 머리의 꼬리표(유료 LLM · 문서 바뀜) · 「한 번에 진행」 ·
// 「문서 화면에서 진행합니다」 한 줄 · 차례 번호 열 + 문서 카드(hdOrdersEl). 서버가 센 묶음만 끝난 수 · 상태 글이 있다. 「한 번에 진행」 은 늘 있다 — 시작 전에는 꺼 두고(「워크플로우 시작」 이 먼저),
// 시작한 뒤에는 모든 묶음에서 누를 수 있다(서버가 안 맡은 묶음은 문서 화면에서: hdAwayBtn). 편 카드 = 사람이 편 것 · 아니면 도는(없으면 「지금」) 첫 카드 — 패널 대시보드와 같은 약속
function hdGroupsEl(groups, V) {
  // active = 도는 실행이 하나라도 있다(두 문서를 함께 쓰는 일 · 문서 화면으로 가는 단추를 끈다) · 묶음 · 「한 문서만」 은 **그 묶음 · 그 문서를 잡은 실행이 있을 때만** 끈다(hdTakes — 문서마다 따로 도는 실행: ② §18-22)
  const active = hdTakes(V), takes = (g) => hdTakes(V, (g.sv && g.sv.lane) || ""), first = V ? groups.find((g) => g.served && g.sv.can && !takes(g)) : null, wid = V ? (V.docs && V.docs.target && V.docs.target.id) || HD.wid : "";
  const cards = groups.flatMap((g) => g.orders.flatMap((o) => o.cards));
  const openKey = HD.open === null ? (cards.find((c) => c.state === "run") || cards.find((c) => c.state === "now") || {}).ref || "" : HD.open;
  const ends = V && !active && V.last && (V.last.stages || []).length > 1 ? V.last.stages : []; // 「이어서 한 번에」 로 여러 묶음을 돈 지난 실행 — 묶음마다 그 끝 글(묶음 하나만 돈 실행의 끝 글은 머리 아래 한 줄에 이미 있다)
  for (const g of groups) {
    const e = ends.find((x) => x.id === g.id && x.text);
    g.end = e ? { ok: e.status === "done" || e.status === "left", text: e.text, rows: dashEndRows(V.last, V, g.id) } : null; // 풍선 = 그 묶음의 줄마다(dashboard.js dashEndEl)
    g.tags = [];
    if (g.served) {
      if ((g.sv.paid || []).length) { const t = el("span", "dash-tag dash-t-llm", `유료 LLM · 문서 ${g.sv.paid.length}개`); t.title = "이 묶음의 「한 번에 진행」 은 유료 LLM 을 부릅니다(문서마다 몇 분)"; g.tags.push(t); }
      if (g.sv.change) { const t = el("span", "dash-tag dash-t-doc", "문서 바뀜"); t.title = "이 묶음의 「한 번에 진행」 은 문서를 바꿉니다"; g.tags.push(t); }
      g.run = hdRunBtn(g, g === first, takes(g));
    } else if (V) g.run = hdAwayBtn(g, wid, active); // 아직 서버가 맡지 않은 묶음도 누르면 돈다 — 문서 화면에서(2026-11-20)
    else { // 시작 전 — 꺼 둔 채 자리를 보인다(패널 대시보드와 같은 머리)
      g.run = hBtn("한 번에 진행", () => {}, { cls: "btn sm", disabled: true, title: "「워크플로우 시작」 으로 문서를 준비하면 누를 수 있습니다" });
      g.run.dataset.hdFocus = `run:${g.id}`;
    }
    g.sub = V && !g.served ? el("p", "dash-text muted home-dash-away", "문서 화면에서 진행합니다 — 「한 번에 진행」 이 문서를 엽니다") // 아직 서버가 맡지 않은 묶음 — 상태를 여기서 지어내지 않는다
      : V && g.served ? dashSoloEl(g.sv, `${g.no} ${g.name}`.trim(), { busyOf: (role) => (hdTakes(V, role) ? HD_WAIT : HD.busy ? "요청을 보내는 중입니다" : ""), run: (role) => hdRunSolo(g.id, role), focusAttr: "hdFocus",
        sending: HD.busy && HD.busy.startsWith(`solo:${g.id}:`) ? HD.busy.split(":")[2] : "" }) : null; // 한 문서만 진행 — 패널 대시보드와 같은 줄(dashboard.js dashSoloEl: 서버가 센 solo — 눌러도 이 화면에 머문다)
    g.flowEl = hdOrdersEl(g, openKey, V, active, wid);
  }
  return dashGroupsEl(groups, openKey, HD_CTX);
}

// 「이어서 한 번에 N→M단계」 — 패널 대시보드의 그 단추와 같은 범위(할 일이 남은 첫 묶음 → 끝 묶음: dashboard.js dashRelayLive): 이관형만 · 그 사이 묶음을 모두 서버가 맡을 때만(서버가 from → to 로 돈다 —
// 경계마다 최신 상태로 그 묶음을 할지 정한다). 꺼진 까닭이 서버의 것이면(앞 묶음이 먼저 · 문서 칸이 빔) 단추 옆에 글로
function hdChainEl(job, groups, active) {
  if (typeof taskIsRelay !== "function" || !taskIsRelay(job)) return null;
  const rest = groups.filter((g) => g.served && g.sv.left > 0);
  if (rest.length < 2) return null;
  const a = rest[0], z = rest[rest.length - 1], span = groups.slice(groups.indexOf(a), groups.indexOf(z) + 1);
  if (!span.every((g) => g.served)) return null;
  const cant = !a.sv.can ? a.sv.why || "지금은 진행할 수 없습니다" : "", why = cant || (active ? "지금 진행 중인 작업이 끝나면 쓸 수 있습니다" : HD.busy ? "요청을 보내는 중입니다" : "");
  const paid = new Set(span.flatMap((g) => g.sv.paid || [])).size, box = el("div", "dash-top");
  const b = hBtn(`이어서 한 번에 ${a.no.replace(/단계$/, "")}→${z.no}`, () => hdRun(a.id, z.id), { cls: "btn sm", disabled: !!why,
    title: why || [`${rest.map((g) => `${g.no} 「${g.name}」`).join(" → ")} 을 이어서 한 번에 — 눌러도 이 화면에 머뭅니다(서버에서 진행 · 창을 닫아도 이어집니다). 실패하거나 사람 손이 필요한 곳에서 전체가 멈춥니다.`,
      paid ? `유료 LLM — 문서 ${paid}개` : "", span.some((g) => g.sv.change) ? "문서가 바뀝니다 — 끝나면 고친 문단을 한 번 확정합니다(앞 상태는 「고친 문단」 탭 확정 기록의 복원)" : "문서는 바뀌지 않습니다"].filter(Boolean).join("\n") }); // 끝 확정(spec_워크플로우 ② §18-24)
  b.dataset.hdFocus = "run:chain";
  box.append(b);
  if (cant && !active) box.append(el("span", "dash-top-why", cant));
  return box;
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
// 「다시 시작」 — 같은 워크플로우의 시작 전(②)으로(2026-11-21 사용자 「다시 시작하기.. 기능이 없네」 — 전에는 「다른 워크플로우」 → 같은 것을 다시 골라야 했다). 이 보기만 비운다: 작업을 지우거나 초기화하지 않는다 —
// 「워크플로우 시작」 을 다시 누르면 지금 시작 길 그대로이고, 같은 파일로 하던 작업이 있으면 같은 파일 고르기 창이 「이어서」 · 「초기화하고 열기」 · 「새 작업으로 시작」 을 묻는다(spec_작업에이전트 ② §10 「다시 시작」).
// 도는 실행이 있으면 꺼 둔다(돌던 실행이 이 보기에서 사라져 보이지 않게 — 「멈춤」 이나 끝난 뒤에)
function hdAgainBtn(job, active = false) {
  const why = !hdCat(job) || (hdCat(job) || {}).soon ? "이 워크플로우를 찾지 못했습니다 — 「새 워크플로우 시작」 으로 고르세요" : active ? "지금 도는 실행이 끝난 뒤에 누르세요 — 「멈춤」 으로 멈출 수 있습니다" : HD.busy ? "지금 하는 일이 끝난 뒤에 누르세요" : "";
  const b = hBtn("다시 시작", () => { const ring = hdRing(); if (homeDashPick(job)) hdFocus(["start", "other"], ring); }, { disabled: !!why,
    title: why || "이 워크플로우를 시작 전으로 돌려 다시 시작합니다 — 왼쪽 문서 목록을 고친 뒤(빠진 문서 더하기 …) 「워크플로우 시작」 을 누릅니다. 지금 작업은 지우지 않습니다(같은 파일로 하던 작업이 있으면 그때 이어서 · 초기화 · 새 작업 가운데 고릅니다)" });
  b.dataset.hdFocus = "again";
  return b;
}
// 시작한 뒤(live · gone)의 이름은 「새 워크플로우 시작」(2026-11-22 사용자 첫 화면을 보이며 "새로운 워크플로우 시작하기가 없네" — 같은 단추가 「다른 워크플로우」 라 새로 시작하는 길로 안 읽혔다) · 시작 전(ready)은 「다른 워크플로우」(고르기를 바꿈)
function hdOtherBtn(title, disabled = false, label = "다른 워크플로우") { // 비운 뒤 초점은 고르기 목록으로
  const b = hBtn(label, () => { const ring = hdRing(); homeDashReset(); hdFocus(["pick"], ring); }, { title, disabled });
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
    if (cat.files && !cat.collect && list.length > 1) return `원본 문서는 하나만 둘 수 있습니다 — 목록에 문서가 ${list.length}개입니다`; // 같은 양식 취합(collect)은 기관 문서가 여럿이다
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

function hdLiveParts() { // ③ 시작한 뒤 — 서버가 센 상태 그대로: 머리 · 도는 실행 · 지난 실행의 끝 · 알림 · 문서 칸 · 「이어서 한 번에」 · 묶음 › 차례 › 문서 카드 · 「대시보드 자세히 보기」
  const V = HD.view, T = hdTally(V), { job, reg, groups, runs, served, nodes, total, done, runNode, nowNode, badNode, left } = T, active = runs.length > 0; // 셈 = hdTally(왼쪽 목적 문서 카드의 「완료」 와 같은 셈)
  if (nodes.some((n) => HD_HAND.test(n.key))) hdHands(); // 사람이 하는 일 줄 — 그 판 · 끝남을 읽어 둔다(「했음」 단추 — hdCards)
  const roleName = (role) => ((reg && (reg.roles || []).find((r) => r.role === role)) || {}).title || (role === "source" ? "원본 문서" : "목적 문서");
  const labelOf = (run) => { // 도는 실행의 이름 — 「1단계 문서 검토 — 한 번에 진행」 · 「… — 원본 문서만」 · 「03 헤딩 · 표 분석 — 이 차례만」
    const R = run.range || {}, runGroup = groups.find((g) => g.id === ((run.now || {}).stage || R.from)) || null;
    const one = R.only ? ((runGroup || {}).nodes || nodes).find((n) => n.key === R.only) || null : null; // 차례 하나만 도는 실행(번호 단추 · 문서 화면의 줄 단추)
    const what = one ? `${hdPad(one.idx)} ${one.name}` : runGroup ? `${runGroup.no} ${runGroup.name}` : "", who = R.role ? roleName(R.role) : "";
    return { what, label: one ? `${what}${who ? `(${who})` : ""} — 이 차례만` : `${what ? `${what} — ` : ""}${who ? `${who}만` : "한 번에 진행"}` };
  };
  // 한 줄 — 도는 실행 · 진행 중인 단계(올린 직후의 기본 분석 …) · 다음 단계 · 실패 · 막힌 단계 / 서버가 맡은 묶음이 다 끝났으면 「모두 끝남」(모든 묶음을 서버가 셀 때만) · 「N단계 끝남 — 그 밖의 묶음은 …」
  const next = active ? `진행 중 — ${runs.length > 1 ? runs.map((r) => labelOf(r).label).join(" · ") : labelOf(runs[0]).what || "한 번에 진행"}` : runNode ? `진행 중 — ${hdPad(runNode.idx)} ${runNode.name}` : nowNode ? `다음: ${hdPad(nowNode.idx)} ${nowNode.name}`
    : badNode ? `확인 필요 — ${hdPad(badNode.idx)} ${badNode.name}(${flowWord(badNode.live)})` : !groups.length || left ? "" : served.length === groups.length ? (total ? "모두 끝남" : "")
      : served.length ? `${served.map((g) => g.no).join(" · ")} 끝남 — 그 밖의 묶음은 문서 화면에서 진행합니다` : "이 워크플로우의 묶음은 문서 화면에서 진행합니다";
  const parts = [hdHeadEl(hdName(job), { job: hdCat(job) ? job : "", count: total ? `끝남 ${done}/${total}` : "", next })];
  for (const run of runs) { // 도는 실행마다 한 줄 — 지금 하는 일 · 지난 시간 · (이 화면이 시작하지 않았으면) 누가 · 「멈춤」(그 실행에만 — 문서마다 따로 도는 실행은 둘: ② §18-22)
    const box = el("div", "dash-live"), text = el("span", "dash-live-text", hdRunText(run)), by = flowBy(run), wait = !!run.stopping || HD.busy === "stop";
    text.setAttribute("role", "status");
    text.dataset.run = box.dataset.run = String(run.n);
    if (run.lane) box.dataset.lane = run.lane;
    box.append(el("span", "ag-spin"), el("b", null, labelOf(run).label), text);
    if (by) box.append(el("span", "dash-tag dash-t-soft home-dash-by", by));
    const stop = hBtn(wait ? "멈추는 중…" : "멈춤", () => hdStop(run.n), { disabled: wait || !!HD.busy, title: `${runs.length > 1 ? "이 실행만 멈춥니다 — " : ""}지금 하는 일이 끝나면 멈춥니다(바로 끊지 않습니다) — 끝난 것은 그대로 남습니다` });
    stop.dataset.hdFocus = runs.length > 1 ? `stop:${run.n}` : "stop";
    box.append(stop);
    parts.push(box);
  }
  for (const x of V.lasts || (V.last && !active ? [V.last] : [])) { // 지난 실행의 끝 — 서버가 지은 글 그대로(초록 = 끝남 · 주황 = 멈춤 · 남김 · 끊김 · 오류) · 같이 돌던 다른 문서의 실행도(끝난 차례 — 그 실행이 아직 도는 동안에도 끝난 쪽의 글은 보인다)
    const E = flowEnd(x);
    if (E && E.text) parts.push(dashEndEl("dash-last", E.ok && !E.left, E.text, dashEndRows(x, V), { title: `지난 실행 — ${dashOneLine(E.text).split(" — ")[0]}` })); // 끝 글 띠 — 패널 대시보드와 같은 그리기(두 줄까지 · 전문은 풍선: dashboard.js dashEndEl)
  }
  if (HD.note) parts.push(hdNoteEl(HD.note.text, HD.note.warn));
  if (HD.err) parts.push(hdNoteEl(`상태를 읽지 못했습니다: ${HD.err}`, true));
  if (V.why && (!V.stages.length || !V.ready)) parts.push(hdNoteEl(V.why, true)); // 워크플로우가 없거나 모르는 워크플로우 · 문서 칸이 비었음(서버의 글)
  parts.push(hdDocsEl(hdLiveDocs(reg, V)));
  const partsEl = hdCollectEl(V, active); // 같은 양식 취합 — 「기관 문서」 목록(문서마다 반영할 기관 · 공통 자리 포함 · 수정본 · 올리기: 패널 대시보드의 「준비」 카드와 같은 것)
  if (partsEl) parts.push(partsEl);
  const chain = hdChainEl(job, groups, active);
  if (chain) parts.push(chain);
  if (V.stages.length) parts.push(hdFlowEl(job, V));
  const tid =(V.docs && V.docs.target && V.docs.target.id) || HD.wid, canRun = served.some((g) => g.sv.can);
  const more = hBtn("대시보드 자세히 보기", () => hdMore(tid), { cls: "btn sm" + (!active && !canRun ? " primary" : ""), // 강조 단추는 다음 할 일 하나 — 여기서 실행할 것이 없으면 문서 화면으로 가는 이 단추
    title: "이 워크플로우의 목적 문서를 열고 패널 탭 「대시보드」 로 갑니다 — 단계마다의 확인 · 보정과 문서 화면에서 진행하는 묶음은 거기서 합니다" });
  more.dataset.hdFocus = "more";
  const resetOff = active ? "지금 도는 실행이 끝난 뒤에 초기화하세요 — 「멈춤」 으로 멈출 수 있습니다" : HD.busy ? "지금 하는 일이 끝난 뒤에 누르세요" : ""; // 작업 내용 초기화(dashboard.js — 패널 대시보드와 같은 것: 문서마다 · 모두)
  parts.push(hdFootEl(more, hdAgainBtn(job, active), hdOtherBtn("이 대시보드를 비우고 새 워크플로우를 고릅니다 — 왼쪽에 문서를 놓고 워크플로우를 골라 시작합니다(지금 작업의 문서 · 결과 · 도는 실행은 그대로 — 작업 리스트에서 다시 열 수 있습니다)", false, "새 워크플로우 시작"),
    ...dashResetParts(HD.reset, { wid: tid, off: resetOff, redraw: () => homeDashDraw(true), done: () => hdRead(), focusAttr: "hdFocus", say: dashResetSay(job) }))); // say — 양식 작성에서만 이름이 「전체 초기화…」(패널 대시보드와 같게 — dashboard.js DASH_RESET_ALL)
  return parts;
}

function hdLostParts(st) { // ④ 못 찾음(지웠거나 서버가 옛 판) · 아직 못 읽음
  const parts = [hdHeadEl(hdName(HD.job), { job: hdCat(HD.job) ? HD.job : "" })];
  if (st === "gone") parts.push(hdNoteEl("이 작업을 찾지 못했습니다 — 지웠거나 서버가 옛 판입니다", true));
  else parts.push(HD.err ? hdNoteEl(`상태를 읽지 못했습니다: ${HD.err}`, true) : el("p", "dash-text muted", "상태를 읽는 중…"));
  parts.push(hdFootEl(st === "gone" && hdCat(HD.job) ? hdAgainBtn(HD.job) : null, hdOtherBtn("이 대시보드를 비우고 새 워크플로우를 고릅니다 — 문서 · 작업은 그대로입니다", false, "새 워크플로우 시작")));
  return parts;
}

// 그린다 — 상태 · 글 · 단추가 같으면 도는 글만 바꾼다(force 가 아니면). 다시 그려도 초점은 그 단추에(초점 테두리는 키보드로 온 초점일 때만 — design.md §17) · 상자 안 스크롤은 그 자리에
function homeDashDraw(force = false) {
  const box = hdBox();
  if (!box) return;
  // 왼쪽 목록이 비어 있으면 거기 보이는 대시보드의 문서(ⓐ) · 진행(「완료」) · 프로젝트 줄(작업 목록에서 읽음 — 목록이 늦게 오면 「프로젝트 없음」 으로 남았다) — 바뀌었을 때만 목록을 다시 그린다.
  // 최근 작업의 「지금 대시보드」 표지(app.js recentDashIds)도 이때 다시 그린다
  const D = homeDashDocs(), tid = D ? (D.rows.find((r) => r.role === "target") || {}).id || "" : "", tw = tid && typeof worksList !== "undefined" ? worksList.find((x) => x.id === tid) : null;
  const docKey = JSON.stringify([HD.wid, D ? [D.job, D.name, D.rows, D.state] : 0, tw ? [(tw.task || {}).project || "", (tw.task || {}).round || 1] : 0]);
  if (docKey !== HD.docKey) {
    HD.docKey = docKey;
    if (typeof homeFilesDraw === "function" && typeof hfHas === "function" && !hfHas()) homeFilesDraw();
    if (!state.id && typeof renderRecentWorks === "function" && typeof recentShown !== "undefined" && recentShown.length) renderRecentWorks($("workList"), recentShown);
  }
  const a = document.activeElement;
  if (!force && a && a.tagName === "SELECT" && box.contains(a)) return; // 고르기 목록에 초점이 있는 동안은 다시 그리지 않는다(펼친 목록이 닫힌다) — 고르거나 초점이 떠나면 그린다
  // 등록부 — 페이지에 한 번 읽는다(패널 대시보드와 같이 쓴다). 읽어 둔 등록부에 고른 워크플로우가 없으면(이 화면을 연 뒤에 조립한 워크플로우) 그 워크플로우마다 한 번 다시 읽는다(dashboard.js dashCatalogChanged)
  if (HD.job && DASH.reg && !hdReg(HD.job) && hdCat(HD.job) && HD.regTried !== HD.job && typeof dashCatalogChanged === "function") { HD.regTried = HD.job; dashCatalogChanged(); }
  if (HD.job && !DASH.reg && !DASH.regErr && !HD.regWait) { HD.regWait = true; dashRegLoad().then(() => { HD.regWait = false; homeDashDraw(); }); }
  // 차례가 나아가면 펼친 카드도 새 「지금」 으로(사람이 편 카드는 차례가 그대로인 동안만 — 패널 대시보드의 DASH.nowKey 와 같은 약속) · 방금 「했음」 을 누른 카드는 그 한 번은 그대로(HD.pin)
  const steps = HD.wid && HD.view ? HD.view.stages.flatMap((g) => (g.server && g.steps) || []).filter((s) => !s.optional && !s.done) : [], nowKey = (steps.find((s) => s.st === "run") || steps.find((s) => s.st === "now") || {}).key || "";
  if (nowKey !== HD.nowKey) { if (HD.nowKey && !HD.pin) HD.open = null; Object.assign(HD, { nowKey, pin: false }); }
  const sig = hdSig();
  if (!force && sig === HD.sig) {
    for (const run of hdRuns(HD.view)) { const t = box.querySelector(`.dash-live-text[data-run="${run.n}"]`), s = hdRunText(run); if (t && t.textContent !== s) t.textContent = s; } // 도는 실행마다의 글
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
  if (hdRuns(V).length) { hdLive(); return; }
  const moving = !V || V.stages.some((g) => (g.steps || []).some((s) => s.busy || s.st === "run"));
  if (now - HD.at >= (HD.gone || !moving ? 10000 : 3000)) hdRead(); else homeDashDraw();
}, 1000);

(() => { // 시작한 묶음의 기억 — 첫 화면을 다시 열면(새 탭 포함) 그 대시보드가 보인다: 무엇을 시작했는지만 기억하고 상태는 서버에서 다시 읽는다
  const m = typeof PEEK !== "undefined" && PEEK ? null : hdMemo(); // 같이 보기의 옆 문서 화면(?peek)은 첫 화면을 보이지 않는다 — 기억을 읽지 않는다(서버도 안 읽는다)
  if (m) Object.assign(HD, { job: m.job, wid: m.wid });
  homeDashDraw(true);
  if (m && hdFront()) hdRead();
})();
