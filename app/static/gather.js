"use strict";
// 취합 — 할 일 「사업계획서 취합」(plan_merge) 화면(spec/spec_취합.md ② §5 화면 · §6 API app/merge_gather_api.py · 전제 jobs/plan_merge.md). app.js 다음에 읽는다.
// app.js 는 할 일별 가지만 둔다(gatherOn() 이면 여기로 — 이관의 taskSteps·taskRun*·links*·fill* 은 취합에서 안 부른다):
//   taskRow → gatherFlowEl(첫 카드) · taskFlowLoad → gatherLoad · taskStepsDraw → gatherStepsDraw · docSwitchDraw → gatherWorks · taskFrameHost(#gatherStage 안에 과제 구성 입력) ·
//   peerDocs/peerLeft/peerSync → gatherPeerDocs/gatherPeerLeft/gatherPeerMark(둘째 면) · outlineGrip 의 dragstart → gatherGripStart(끌어 넣기 출발) · 창의 파일 놓기 → gatherDragIs(이 형식은 안 받음).
// 첫 카드: 「사업계획서(취합본)」 칸 하나(이관의 칸 그대로 — taskSlot·taskSlotUp) + 기관 문서 줄 N + 「기관 문서 추가」 + 기관 현황 한 줄 + 편집 구역 줄(zones.js zonesBarEl — 전의 기관 구역 줄) + 묶음 셋(1단계 구분 기준 · 2단계 문서 프레임 작성 · 3단계 내용 매핑 — 이관과 같은 모양).
// 2열(headsDlg): 「기관 작성 내용」(kind gather — 기관 문서마다) · 「넣기 계획」(gatherFill) · 「끌어 넣기」(gatherDrop). 취합본은 사람이 확인한 뒤에만 바뀐다(계획 → 「반영」 · 「한 번에 진행」 — 2026-11-18 부터 확인 창 없이, 실행 취소로 되돌림).
// 화면 말(실무자용): 기관이 쓴 덩어리 = 「기관 작성 내용」, 상태 = 넣을 수 있음·이미 들어 있음·겹침·다른 기관 자리·반영할 기관 미지정·확인 필요·표 구조가 다름·양식 글이 바뀜·지워짐·계산 칸.

const GT_PART = "application/x-nfm-gather-part"; // 기관 문서 줄을 다른 기관 폴더로 끄는 자료 형식(작업 id — ② §5 「기관별 폴더」). 창의 파일 놓기와 가른다(app.js bind 의 own)
const gatherPartDragIs = (e) => !!(e && e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes(GT_PART));
const GT_TYPE = "application/x-nfm-gather"; // 끌어 넣기 자료 형식({from: 기관 문서 작업 id, srcId: 제목 줄 문단 id}) — 창의 파일 놓기·같은 문서 안 개요 줄 옮기기와 가른다(② §4-6)
const GT_POLL = 2000; // 스크립트 분석이 끝났는지 읽는 간격(ms)
const GT_STATUS = { ready: "넣을 수 있음", overlap: "겹침", unknownPlace: "확인 필요", same: "이미 들어 있음", otherOrg: "다른 기관 자리", unassigned: "반영할 기관 미지정",
  structure: "표 구조가 다름", changed: "양식 글이 바뀜", removed: "지워짐", calc: "계산 칸" }; // 작성 내용의 상태 → 화면 말(② §4-2 판정). 차례 = 보이는 차례(넣을 수 있음 · 겹침 · 확인 필요가 앞)
const GT_STATUS_HELP = { ready: "넣을 수 있음 — 취합본의 그 자리가 기준본 그대로입니다", same: "이미 들어 있음 — 할 일 없음", overlap: "겹침 — 취합본에 다른 내용이 있어 넣지 않음(덮어쓰지 않습니다 — 직접 넣으려면 끌어 넣기)",
  otherOrg: "다른 기관 자리 — 반영할 기관의 자리가 아니거나, 공통 자리인데 「공통 자리 포함」 이 꺼져 있음", unassigned: "반영할 기관 미지정 — 위 기관 문서 줄에서 기관을 고르면 넣을 수 있습니다",
  unknownPlace: "확인 필요 — 자리를 정하지 못함(억지로 넣지 않습니다 — 직접 넣으려면 끌어 넣기)", structure: "표 구조가 다름 — 병합·열이 달라졌거나 새로 그린 표(넣지 않음)",
  changed: "양식 글이 바뀜 — 제목·라벨·양식 글·표 머리(넣지 않고 알리기만)", removed: "지워짐 — 기준본에 있던 것이 기관 문서에 없음(취합본에서 지우지 않음)", calc: "계산 칸 — 기관 문서의 값을 복사하지 않음" };
const GT_BADGE = { ready: "applied", same: "already", overlap: "unsupported", otherOrg: "already", unassigned: "unsupported", unknownPlace: "unresolved", structure: "unsupported", changed: "already", removed: "already", calc: "already" }; // 색 = 구분 기준 목록의 꼬리표(.dv-badge)
const GT_KIND = { added: "더한 내용", filled: "채운 자리", cells: "표 칸", rows: "표 행", removed: "지워짐", changed: "바뀐 글" };
const GT_REASON = { noFrame: "배포 기준본이 없음", frameStale: "기준본이 낡음(프로젝트 구성을 다시 반영함 — 새로 만들어야 함)", frameDiffers: "기준본이 다름(다른 판의 기준본으로 온 문서)", noHeadings: "헤딩·표 분석 없음",
  staleHeadings: "헤딩·표 분석이 지금 문서의 것이 아님", noMatch: "기준본과 맞는 자리를 찾지 못함(끌어 넣기만)", noValues: "프로젝트 구성 값 없음", notApplied: "프로젝트 구성 반영 전", unsupportedForm: "지원하지 않는 양식·형식",
  lowMatch: "기준본과 자리를 충분히 확인하지 못함 — 넣을 것을 직접 고르세요", stalePlan: "계획 뒤 문서·설정이 바뀜(다시 계획)", notPart: "이 취합에 든 기관 문서가 아님", badPart: "기관 문서로 넣을 수 없는 문서(지운 문서 등)",
  noLlm: "LLM 을 쓸 수 없음", error: "판정하지 못함(오류)" }; // 서버의 까닭 열쇠(app/merge_gather_api.py MSG) → 줄에 보일 짧은 말. 알림에는 서버가 준 글(message)을 쓴다
const GT_SOFT = ["lowMatch"]; // 줄을 막지 않는 까닭 — 자리 연결은 됐고, 넣을 것은 사람이 「넣음」 으로 고른 것만(기준본에서 나오지 않은 문서는 저절로 넣지 않는다)
const GT_DROP = { secPr: "쪽·구역 설정", colPr: "단 설정", header: "머리말", footer: "꼬리말", pageNum: "쪽 번호", pageHiding: "쪽 감추기", pageNumCtrl: "쪽 번호 제어", newNum: "새 번호", ole: "OLE 개체", chart: "차트", video: "동영상" }; // 복사에서 빠지는 개체({src, what: 요소 이름} — hwpx_doc.DROP_ON_COPY) → 화면 말
const GT_CALC_WHY = { partValue: "기관 문서의 값 — 복사하지 않음", operands: "더하는 칸이 바뀜 — 반영하면 다시 계산", rows: "행이 늘어남 — 합의 범위를 확인" }; // 넣기 계획의 계산 칸 까닭(merge_gather.plan calc[].why)
const GT_ROLE = { lead: "주관", joint: "공동", outside: "외 기관", overseas: "국외", entrust: "위탁" };
const GT_COUNT = { items: "작성 내용", hunks: "작성 내용", blocks: "블록", paragraphs: "문단", tables: "표", pictures: "그림", cells: "표 칸", rows: "행 추가", placeholders: "지운 자리표시 줄", removed: "지운 자리표시 줄",
  shaped: "글자 모양 맞춤", fitted: "그림 폭 맞춤", converted: "틀 맞춤", kept: "쓴 대로 둔 개요 줄", over: "넘친 레벨", recalculated: "다시 계산", skipped: "반영 때 건너뜀" }; // 넣은 수(반영 응답 counts) → 화면 말. converted·kept = 취합본 틀에 맞춘 개요 줄 · 못 맞춰 쓴 대로 둔 개요 줄(merge_gather_fit)
const GT_STAGES = [ // 묶음 셋(spec_취합 ② §9-1 · spec_작업 ② §18) — config 는 2026-11-13 더함(있던 묶음의 dom·store 는 그대로)
  { id: "config", ...TASK_STAGE_META.config, dom: "gatherStage0", store: "nfm.gatherStageOpen0", short: "프로젝트 구성", does: "프로젝트 구성(단계·차년도·기관)만 정하기 — 문서에서 추출하거나 불러와 확인한 뒤 프로젝트에 저장(확정) · 문서는 안 바뀜" },
  { id: "frame", ...TASK_STAGE_META.frame, dom: "gatherStage", store: "nfm.gatherStageOpen", short: "프레임 작성", does: "프로젝트 구성 반영(절·표 행·열 — 구조만) → 배포 기준본" },
  { id: "map", ...TASK_STAGE_META.map, dom: "gatherStage2", store: "nfm.gatherStageOpen2", short: "내용 매핑", does: "기관 문서마다 자리 연결 → LLM 검토 → 넣기 계획 → 내용 반영" },
];

// ---- 상태(문서를 열 때마다 새로 — state.epoch 로 가른다: app.js divReset 에 가지를 더 두지 않는다)
const gatherFresh = () => ({ epoch: state.epoch, seq: 0, key: null, view: null, err: "", missing: false, loading: false, div: undefined, // view = GET …/gather 몸통 · div = 취합본이 지금 문서가 아닐 때 읽어 둔 구분 기준
  links: {}, plans: {}, done: {}, filter: {}, // 기관 문서 id → 작성 내용 {data, why[], error, busy} · 넣기 계획 · 반영 결과 · 목록 거르기
  frameBusy: "", partBusy: "", llmBusy: "", planBusy: "", applyBusy: "", listPart: "", listSel: "", fillPart: "", drop: null });
let gatherState = null;
function gt() { if (!gatherState || gatherState.epoch !== state.epoch) gatherState = gatherFresh(); return gatherState; }
let gatherStepsLast = null; // 마지막으로 셈한 단계(gatherCalc — 상태 st 포함)
let gatherRun = null; // 한 번에 진행 — 도는 중 {stage, plan 취합본 id, key 지금 단계, note 지금 하는 일, t0, stop, timer}
let gatherRunLast = null; // 마지막 실행의 끝 {stage, plan, ok, key, text, done 그때 그 묶음의 끝난 수} — 상태 줄에 남긴다
class GatherHalt extends Error {} // 멈춤(사람 손이 필요함 · 실패) — 글이 상태 줄에 그대로 보인다
const gatherHalt = (msg) => { throw new GatherHalt(msg); };

const gatherSpec = () => (state.task && taskGatherOf(state.task.job)) || null; // {base: 취합본의 종류(plan — 문서 하나), parts: 기관 문서의 종류(part — 여럿)}
const gatherPlan = () => { const s = gatherSpec(); return s ? taskSlotDoc(s.base) : null; }; // 취합본 = 그 칸의 문서(지금 문서가 그 종류면 지금 문서, 아니면 같은 프로젝트의 첫 문서)
const gatherMine = () => { const p = gatherPlan(); return !!p && p.id === state.id; }; // 취합본을 고치는 중인가
const gatherPart = (pid) => ((gt().view || {}).parts || []).find((p) => p.work === pid) || null;
const gatherKey = () => `${taskScopeKey()}|${(gatherPlan() || {}).id || ""}|${worksList.length}`;
const gatherDocIds = () => [(gatherPlan() || {}).id, ...((gt().view || {}).parts || []).map((p) => p.work)].filter(Boolean); // 이 취합의 문서(취합본 + 기관 문서) — 첫 카드의 「같은 프로젝트 문서」 줄에서 뺀다(app.js taskRow)
const gatherWhen = (at) => (at == null || at === "" ? "" : fmtWhen(typeof at === "number" ? at : Date.parse(at) / 1000)); // 서버의 시각이 초든 ISO 글이든
const gatherUrl = (path = "") => `/api/docs/${gatherPlan().id}/gather${path}`;
const gatherCall = (path, method = "GET", body = null) => api(gatherUrl(path), method === "GET" ? {} : method === "DELETE" ? { method } : { method, headers: H_JSON, body: JSON.stringify(body || {}) });
const gatherSeg = (pid) => `/parts/${encodeURIComponent(pid)}`;

function gatherWhy(e) { // 400·404·409 의 까닭 열쇠(noFrame · frameStale · staleHeadings · stalePlan …) — 취합 끝점의 오류는 늘 detail = {reason: 열쇠, message: 한국어 글}
  const d = e && e.body && e.body.detail;
  return d && typeof d === "object" && typeof d.reason === "string" && d.reason ? [d.reason] : [];
}
function gatherErr(e) { // 알림에 쓸 글 — 서버가 준 글(message), 없으면 까닭 열쇠의 화면 말 · 그 밖의 오류 글
  const why = gatherWhy(e), d = e && e.body && e.body.detail;
  return (d && typeof d === "object" && typeof d.message === "string" && d.message) || (why.length ? why.map((k) => GT_REASON[k] || k).join(" · ") : (e && e.message) || "알 수 없는 오류");
}
const gatherReasons = (xs) => (xs || []).map((k) => GT_REASON[k] || k).join(" · ");
const gatherHard = (xs) => (xs || []).filter((k) => !GT_SOFT.includes(k)); // 그 줄의 자리 연결을 막는 까닭만
const gatherLow = (p) => ((p && p.reasons) || []).includes("lowMatch"); // 기준본과 자리를 충분히 확인하지 못한 문서 — 넣을 수 있는 것마다 「보류」(decision {check, auto})로 온다
function gatherCountText(c) { // 「넣을 수 있음 n · 겹침 n · 확인 필요 n · …」 — 앞 셋은 0 이어도, 나머지는 있을 때만
  c = c || {};
  return Object.keys(GT_STATUS).filter((k) => ["ready", "overlap", "unknownPlace"].includes(k) || c[k]).map((k) => `${GT_STATUS[k]} ${c[k] || 0}`).join(" · ");
}
const gatherNums = (c, keys) => keys.filter((k) => c && c[k]).map((k) => `${GT_COUNT[k] || k} ${nf(c[k])}`).join(" · ");
function gatherPlanText(P) { // 넣기 계획 한 줄 — 넣을 작성 내용 수 + 문단·표·그림·칸·행(계획에 counts 가 없으면 항목에서 더한다)
  const sum = P.counts || (P.items || []).reduce((a, it) => { for (const [k, n] of Object.entries(it.counts || {})) if (typeof n === "number") a[k] = (a[k] || 0) + n; return a; }, {});
  const parts = gatherNums(sum, ["paragraphs", "tables", "pictures", "cells", "rows", "placeholders", "converted", "kept", "over"]); // over = 취합본 틀보다 깊은 줄(넘친 개요 레벨 — spec_병합 ② §5-5: 맞춤·쓴 대로 둔 줄 가운데)
  return P.todo ? `넣을 내용 ${nf(P.todo)}곳${parts ? ` — ${parts}` : ""}` : "넣을 것이 없습니다(이미 넣었거나 넣을 수 있는 자리가 없음)";
}
function gatherDoneText(r) { // 반영 결과 한 줄
  const c = r.counts || {}, known = Object.keys(GT_COUNT).filter((k) => k !== "blocks" && typeof c[k] === "number" && c[k]), seen = new Set(); // 블록 수는 문단·표·그림 수와 겹친다
  const parts = known.filter((k) => !seen.has(GT_COUNT[k]) && seen.add(GT_COUNT[k])).map((k) => `${GT_COUNT[k]} ${nf(c[k])}`), need = gatherCalcNeed(r.calc).length;
  return (parts.join(" · ") || "넣음") + (need ? ` · 다시 계산 필요 ${need}칸` : "") + ((r.dropped || []).length ? ` · 못 옮긴 것 ${r.dropped.length}` : "");
}
const gatherCalcNeed = (xs) => (xs || []).filter((c) => !c || c.action !== "recalculated"); // 반영 결과의 계산 칸 가운데 「다시 계산 필요」(다시 계산해 넣은 칸은 counts.recalculated 로 센다)
function gatherCalcText(c) { // 계산 칸 한 줄 — 계획 {table, cell, why, kind, text, key} · 반영 결과 {table, cell, kind, action: recalculated | needed, was, now, note}
  const kind = c.kind === "sum" ? "합" : c.kind ? "식" : "";
  if (c.action) return [kind, c.action === "recalculated" ? `다시 계산해 넣음: ${oneLine(c.was || "") || "(빈칸)"} → ${c.now}` : `다시 계산 필요 — ${c.note || "확인"}${c.was ? `(지금 값 ${oneLine(c.was)})` : ""}`].filter(Boolean).join(" · ");
  return [kind, GT_CALC_WHY[c.why] || c.why || "", c.text ? `기관 문서의 값 「${oneLine(c.text)}」` : ""].filter(Boolean).join(" · ") || "(계산 칸)";
}
function gatherDropped(xs) { // 옮기지 못하는 개체 [{src, what(요소 이름)[, key]}] → 종류별 한 줄(「쪽·구역 설정 2」)
  const m = new Map();
  for (const d of xs || []) { const k = (d && (GT_DROP[d.what] || d.what)) || "(개체)"; m.set(k, (m.get(k) || 0) + 1); }
  return [...m].map(([k, n]) => (n > 1 ? `${k} ${nf(n)}` : k));
}
function gatherJump(id) { // 그 블록·칸으로 — 표 id 면 그 표의 첫 문단(divGo 는 문단·칸만 안다). 둘째 면 화면에서도 같은 함수를 부른다
  const t = id ? document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(id)}"]`) : null, p = t && t.querySelector(".para[data-id]");
  if (id) divGo({ key: p ? p.dataset.id : id });
}
const gatherTodo = (L) => (L.items || []).filter((it) => it.status === "ready" && !(it.decision && ["skip", "check"].includes(it.decision.value))).length;
const gatherPartTodo = (p) => (p.todo != null ? p.todo : p.counts ? p.counts.ready || 0 : null); // 그 기관 문서에 남은 넣을 것 — null = 아직 모름(자리 연결 전)

// ---- 읽기(GET …/gather) — 문서를 열 때(둘째 면의 탭이 본다) · 「연구개발과제」 내용을 열 때 · 계획/반영/실행 취소 뒤(divShow → taskFlowLoad) · 기관 문서를 넣고 뺀 뒤
async function gatherLoad() {
  const plan = gatherOn() ? gatherPlan() : null, g = gt(), epoch = state.epoch, seq = ++g.seq;
  if (!plan) { Object.assign(g, { view: null, err: "", missing: false, loading: false }); gatherDraw(); peerSync(); return; }
  g.loading = true;
  let view = null, err = "", missing = false, div;
  try {
    const dp = plan.id === state.id ? null : api(`/api/docs/${plan.id}/divisions`).catch(() => null); // 취합본이 다른 문서면 그 구분 기준도(닫힌 문서는 서버가 연다)
    view = await api(`/api/docs/${plan.id}/gather`);
    const r = dp && (await dp);
    if (r) div = { values: ((r.settings || r.applied) || {}).values || null, applied: r.applied || null, ok: !!(r.profile && r.profile.supported), confirmed: r.confirmed || null, sharing: r.projectSharing || null };
  } catch (e) { err = e.message; missing = e.status === 404 && e.message === "Not Found"; } // 끝점이 없는 서버(재시작 전)
  if (epoch !== state.epoch || g !== gatherState || seq !== g.seq) return;
  Object.assign(g, { view: err ? g.view : view, err, missing, loading: false, div });
  gatherDraw();
  peerSync(); // 둘째 면의 탭 = 그 취합에 든 기관 문서
  docRoleDraw(); // 이름 줄의 꼬리표 — 기관 문서를 보고 있으면 반영할 기관의 약칭(org_short.js — spec_취합 ② §11)
  if (typeof zonesLoad === "function") zonesLoad(); // 편집 구역(zones.js — 전의 기관 구역 표시: ② §9-2) — 반영·실행 취소·구분 기준 반영 뒤에도 이 길로 다시 읽는다
}
function gatherViewSet(V, wipe = false) { // 조작의 응답(취합 상태 몸통)을 화면 상태로 — wipe = 기준본이 바뀌어 읽어 둔 작성 내용·계획이 모두 낡음
  const g = gt();
  if (V && Array.isArray(V.parts)) { g.view = V; g.err = ""; g.missing = false; }
  if (wipe) { g.links = {}; g.plans = {}; }
  if (!PEEK && V && Array.isArray(V.parts)) { peerSync(); docRoleDraw(); } // 둘째 면 탭 글(반영할 기관 이름 — gatherPeerLabel) · 탭과 이름 줄의 기관 약칭(org_short.js — spec_취합 ② §11)이 바뀌었을 수 있다 — 같으면 peerTabsDraw 가 그대로 둔다
}
function gatherWorks() { // 작업 목록을 읽은 뒤(app.js docSwitchDraw) — 문서를 처음 열었거나 칸의 문서가 달라졌으면 다시 읽는다
  if (PEEK) return;
  const g = gt(), key = gatherKey();
  if (g.key === key && (g.view || g.loading || g.err)) return;
  g.key = key;
  gatherLoad();
}

// ---- 첫 카드(spec_취합 ② §5 「첫 카드」) — taskRow 가 넣는다(#gatherFlow). 읽은 뒤에는 gatherDraw 가 안쪽 덩어리만 바꾼다(과제 구성 입력 #taskFrameForm 은 그대로)
function gatherFlowEl() {
  const box = el("div", "dv-flow gt-flow"), stages = el("div", "dv-phases");
  box.id = "gatherFlow";
  box.dataset.key = gatherKey();
  stages.id = "gatherSteps";
  gatherCalc();
  stages.append(...GT_STAGES.map((stage) => gatherStageEl(stage)));
  box.append(taskJourneyEl(), gatherFilesEl(), gatherPartsEl(), gatherOrgsEl(), gatherZonesEl(), gatherQuickEl(), stages);
  gatherJourneySync(box);
  return box;
}

// 같은 순서 표시를 이관과 공유한다. 이동은 입력/세부 목록을 보여 주기만 하고 실행하지 않는다.
function gatherJourneySync(host = document.getElementById("gatherFlow")) {
  if (!host || !gatherStepsLast) return;
  const all = gatherStepsLast, files = all.find((s) => s.step === "files"), plan = gatherPlan();
  let before = !files?.done;
  const items = [{ id: "prepare", label: "준비", state: files?.done ? "done" : "now", target: host.querySelector(".gt-files"),
    note: "취합본을 고릅니다. 기관 문서는 들어오는 대로 추가할 수 있습니다." }];
  for (const stage of GT_STAGES) {
    const steps = all.filter((s) => s.stage === stage.id && s.step !== "files"), completed = steps.filter((s) => s.done).length;
    const run = gatherRun?.stage === stage.id || steps.some((s) => s.busy);
    const last = gatherRunLast?.stage === stage.id && gatherRunLast.plan === plan?.id && gatherRunLast.done === completed ? gatherRunLast : null;
    const done = steps.length > 0 && completed === steps.length;
    const status = run ? "run" : before ? "todo" : last && !last.ok ? "halt" : done ? "done" : "now";
    items.push({ id: stage.id, label: `${stage.no} ${stage.short}`, state: status, target: stage.dom, note: stage.does });
    if (!done) before = true;
  }
  taskJourneySync(host.querySelector(".dv-journey"), items);
}
function gatherDraw() { // 카드의 칸·기관 문서 줄·기관 현황·단계 목록을 그 자리에서 다시 + 열려 있는 2열 목록
  const box = document.getElementById("gatherFlow");
  if (box) {
    const act = document.activeElement, focus = act && box.contains(act) && act.dataset ? act.dataset.gatherFocus || "" : "";
    const swap = (sel, node) => { const old = box.querySelector(sel); if (old) old.replaceWith(node); };
    if (box.dataset.key !== gatherKey()) { box.dataset.key = gatherKey(); swap(".gt-files", gatherFilesEl()); }
    swap("#gatherParts", gatherPartsEl());
    swap(".gt-orgs", gatherOrgsEl());
    swap(".gt-zones", gatherZonesEl());
    swap(".gt-quick", gatherQuickEl());
    gatherMatesDraw();
    gatherStepsDraw();
    if (focus) { const to = box.querySelector(`[data-gather-focus="${CSS.escape(focus)}"]`); if (to && !to.disabled) to.focus({ preventScroll: true }); } // 바꾼 줄의 목록·체크 상자에 초점 그대로
  }
  if (heads.dlg === "gather" && gt().listPart) gatherList(gt().listPart, true);
  else if (heads.dlg === "gatherFill" && gt().fillPart) gatherFillList(gt().fillPart, true);
  else if (heads.dlg === "gatherDrop") gatherDropList(true);
}

function gatherQuickEl() { // 간단 모드 줄(② §8-6 — gather_quick.js 가 그린다). 간단 모드로 돌린 취합본이 아니면 빈 자리(숨김) — gatherDraw 가 바꿔 끼운다
  if (typeof gatherQuickLineEl === "function") return gatherQuickLineEl();
  const p = el("div", "gt-quick");
  p.hidden = true;
  return p;
}

function gatherMatesDraw() { // 첫 카드의 「같은 프로젝트 문서」 줄(app.js taskRow) — 이 취합의 문서(취합본·기관 문서)는 뺀다: 카드를 그릴 때는 취합 상태를 아직 못 읽어 기관 문서를 모를 수 있다
  const row = document.querySelector("#divBox .dv-task");
  if (!row) return;
  const ids = new Set(gatherDocIds()), mates = taskMates().filter((w) => !ids.has(w.id)), old = row.querySelector(".dv-task-mates");
  const text = mates.length ? `같은 프로젝트 문서 ${mates.length}개 — ${mates.map((w) => { const f = taskName("file", (w.task || {}).file); return f ? `${w.name}(${f})` : w.name; }).join(" · ")}` : "";
  if (!text) { if (old) old.remove(); return; }
  if (!old) row.append(el("p", "dv-caption dv-task-mates", text));
  else if (old.textContent !== text) old.textContent = text;
}

function gatherPeerBtn(wid, name) { // 같이 보기 단추(28×28) — 그 문서를 둘째 면에 띄우거나 닫는다(이관의 칸 단추와 같은 꼴 · 켜고 끈 것은 nfm.peer)
  const b = el("button", "icon dv-flow-up dv-flow-peer");
  b.type = "button";
  b.dataset.gatherPeer = wid || "";
  b.dataset.name = name || "";
  b.setAttribute("aria-label", `${name || "문서"} 같이 보기`);
  b.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/></svg>';
  b.onclick = (e) => {
    e.preventDefault(); // label 안일 때 — 누름이 select 로 넘어가지 않게
    if (!wid) return;
    const on = peerShown() === wid;
    peerPick = wid; // 둘째 면의 문서 이름 탭으로 고른 것과 같은 자리(app.js)
    peerKind = null;
    peerSet(!on);
  };
  gatherPeerBtnSync(b);
  return b;
}
function gatherPeerBtnSync(b) {
  const wid = b.dataset.gatherPeer, name = b.dataset.name, on = !!wid && wid === peerShown();
  b.disabled = !wid || wid === state.id;
  b.setAttribute("aria-pressed", on);
  b.title = !wid ? "문서가 없습니다" : wid === state.id ? "지금 보는 문서입니다 — 기관 문서를 옆에 같이 볼 수 있습니다" : on ? `${name} 같이 보기 닫기` : `같이 보기 — 문서 옆 열에 읽기 전용으로 엽니다\n${name}`;
}

function gatherFilesEl() { // 「사업계획서(취합본)」 칸 — 문서 고르기 · 폴더(올리기) · 같이 보기. 고르기·올리기는 이관의 칸 그대로(칸에 있던 문서는 빠진다 — 취합본은 하나)
  const files = el("div", "dv-flow-files gt-files"), lab = el("label"), base = gatherSpec().base, plan = gatherPlan();
  files.title = "취합본 — 기관 문서의 내용을 모을 원래 사업계획서(고치는 문서)";
  lab.append(el("span", null, `${taskName("file", base)}(취합본)`), taskSlot(base), taskSlotUp(base), gatherPeerBtn(plan ? plan.id : "", plan ? plan.name : ""));
  files.append(lab);
  return files;
}

function gatherPartTag(p) { // 기관 문서 줄의 상태 꼬리표 → [글, .dv-badge 색, 도움말]
  const c = p.counts || null, why = gatherReasons(gatherHard(p.reasons)), todo = gatherPartTodo(p);
  if (why) return ["확인 필요", "unresolved", `자리 연결을 할 수 없습니다 — ${why}` + (p.error ? `\n${p.error}` : "")];
  if (!(p.orgs || []).length) return ["기관 미지정", "unsupported", "반영할 기관 미지정 — 기관을 고르기 전에는 아무것도 넣지 않습니다"];
  if (todo > 0) return [`넣을 것 ${nf(todo)}`, "applied", gatherCountText(c)];
  if (!c) return ["자리 연결 전", "already", `아직 기준본과 견주지 않았습니다 — ${TASK_STAGE_META.map.no}에서 자리 연결`];
  if (gatherLow(p) && c.ready) return ["직접 고르기", "unresolved", `${GT_REASON.lowMatch}(「기관 작성 내용」 에서 넣음을 켠 것만 넣습니다)\n${gatherCountText(c)}`];
  return [c.same ? "반영함" : "넣을 것 없음", "already", gatherCountText(c)];
}

function gatherPartsEl() { // 기관 문서 줄 N + 「기관 문서 추가」 — 줄 = 문서 이름 · 반영할 기관 · 공통 자리 포함 · 상태 · 같이 보기 · 빼기. 더해도 다른 기관 문서는 안 빠진다
  const g = gt(), plan = gatherPlan(), V = plan ? g.view : null, box = el("div", "gt-parts"), head = el("div", "gt-parts-head"), parts = (V && V.parts) || [], orgs = (V && V.orgs) || [], busy = !!g.partBusy;
  box.id = "gatherParts";
  head.append(el("strong", null, "기관 문서"), el("span", "gt-parts-n", V ? `${parts.length}개` : ""),
    hHelp("기관 문서와 취합 순서 설명", "기관이 배포 기준본을 받아 자기 몫만 채워 돌려준 문서입니다. 들어온 차례대로 진행하며 같은 공통 자리에 내용이 겹치면 먼저 넣은 내용을 두고 겹침으로 표시합니다. 반영할 기관을 고르지 않은 문서는 건너뜁니다."));
  box.append(head);
  if (parts.length) { // 열 제목은 위에 한 번(넓을 때만 — 좁으면 줄이 두 줄로 접히고 칸 이름은 그 줄에: gather.css)
    const cols = el("div", "gt-cols");
    cols.setAttribute("aria-hidden", "true");
    cols.append(el("span", null, "문서"), el("span", null, "반영할 기관"), el("span", null, "공통"), el("span", null, "상태"));
    box.append(cols);
  }
  const all = orgs.map((o) => o.key), P = taskProject();
  const off = !plan ? "사업계획서(취합본)를 먼저 고르세요" : !P ? "프로젝트 이름을 먼저 적으세요 — 기관 문서를 그 프로젝트에 넣습니다" : !V ? (g.err ? "취합 상태를 읽지 못했습니다" : "취합 상태를 읽는 중…") : "";
  const foldered = all.length > 0, byF = new Map(); // 기관별 폴더(② §5 「기관별 폴더」) — 과제 구분 기준에 기관이 있을 때만(없으면 전처럼 줄만)
  if (foldered) box.classList.add("gt-foldered");
  for (const p of parts) {
    const row = el("div", "gt-part"), name = el("span", "gt-part-name", p.name), sel = el("select"), chk = el("label", "gt-part-chk"), cb = el("input"), [tag, cls, tip] = gatherPartTag(p), cur = p.orgs || [];
    row.dataset.part = p.work;
    name.title = p.name;
    if (foldered && !busy && !gatherRun) { // 이름을 끌어 다른 기관 폴더에 놓으면 반영할 기관이 그 기관으로(gatherFolderEl 이 받는다)
      name.draggable = true;
      name.title = `${p.name}\n끌어서 다른 기관 폴더에 놓으면 반영할 기관이 그 기관으로 바뀝니다`;
      name.ondragstart = (e) => { e.dataTransfer.setData(GT_PART, p.work); e.dataTransfer.effectAllowed = "move"; row.classList.add("gt-dragging"); };
      name.ondragend = () => { row.classList.remove("gt-dragging"); for (const f of document.querySelectorAll("#gatherParts .gt-drop")) f.classList.remove("gt-drop"); };
    }
    sel.dataset.gatherOrg = p.work;
    sel.dataset.gatherFocus = `org:${p.work}`;
    sel.setAttribute("aria-label", `${p.name} — 반영할 기관`);
    sel.append(new Option("선택 안 함", ""));
    const rec = p.recommend && !cur.length ? p.recommend : null; // 작성 내용이 가장 많은 기관 — 추천만(고르는 것은 사람)
    const auto = p.orgsBy && cur.length === 1 ? cur[0] : ""; // 간단 모드가 정한 기관 — 사람이 고르면 서버가 표시를 지운다(② §8-3)
    for (const o of orgs) sel.append(new Option(o.name + (GT_ROLE[o.role] ? ` (${GT_ROLE[o.role]})` : "") + (rec && rec.org === o.key ? ` — 추천(작성 내용 ${nf(rec.n)})` : "")
      + (auto === o.key ? (p.orgsBy === "name" ? " — 자동(파일 이름)" : " — 자동(추천)") : ""), o.key));
    if (all.length > 1) sel.append(new Option("모든 기관", "*"));
    const isAll = all.length > 1 && cur.length === all.length && all.every((k) => cur.includes(k));
    if (cur.length && !isAll && !(cur.length === 1 && all.includes(cur[0]))) sel.append(new Option(cur.length === 1 ? `${cur[0]}(프로젝트 구성에 없음)` : `기관 ${cur.length}곳`, "~")); // 목록 밖의 조합 — 보이기만
    sel.value = !cur.length ? "" : isAll ? "*" : cur.length === 1 && all.includes(cur[0]) ? cur[0] : "~";
    sel.disabled = busy;
    sel.title = "반영할 기관 — 이 문서에서 가져올 기관(그 기관 자리의 내용만 넣습니다). 「선택 안 함」 이면 아무것도 넣지 않습니다"
      + (auto ? `
간단 모드가 ${p.orgsBy === "name" ? "파일 이름으로" : "작성 내용이 가장 많은 기관으로"} 정했습니다 — 다른 기관을 고르면 그것을 따릅니다` : "") + (rec ? `\n작성 내용이 가장 많은 기관: ${(orgs.find((o) => o.key === rec.org) || {}).name || rec.org}(${nf(rec.n)}곳)` : "");
    sel.onchange = () => { if (sel.value !== "~") gatherPartSet(p.work, { orgs: sel.value === "*" ? all : sel.value ? [sel.value] : [] }); };
    cb.type = "checkbox";
    cb.checked = p.common !== false;
    cb.disabled = busy;
    cb.dataset.gatherCommon = p.work;
    cb.dataset.gatherFocus = `common:${p.work}`;
    cb.setAttribute("aria-label", `${p.name} — 공통 자리 포함`);
    cb.onchange = () => gatherPartSet(p.work, { common: cb.checked });
    chk.title = "공통 자리 포함 — 기관이 갈리지 않은 공통 자리의 내용도 이 문서에서 가져옵니다(같은 자리에 두 문서가 쓰면 먼저 들어온 것을 두고 뒤의 것은 겹침)";
    chk.append(cb, el("span", null, "공통 자리 포함"));
    const badge = el("span", `dv-badge ${cls} gt-part-tag`, tag);
    badge.title = tip;
    const del = el("button", "icon dv-flow-up gt-part-del", "×");
    del.type = "button";
    del.dataset.gatherDel = p.work;
    del.disabled = busy || !!gatherRun;
    del.title = "빼기 — 이 문서를 취합에서 뺍니다(이미 넣은 내용은 취합본에 그대로)";
    del.setAttribute("aria-label", `${p.name} 빼기`);
    del.onclick = () => gatherPartDel(p.work);
    row.append(name, sel, chk, badge, gatherPeerBtn(p.work, p.name), del);
    if (!foldered) { box.append(row); continue; }
    const k = gatherFolderOf(p, all);
    if (!byF.has(k)) byF.set(k, []);
    byF.get(k).push(row);
  }
  if (foldered) { // 폴더 차례 = 구분 기준의 기관 차례 → 「여러 기관·그 밖」 → 「기관 미지정」(뒤의 둘은 문서가 있을 때만)
    for (const f of [...orgs, { key: "~", name: "여러 기관·그 밖" }, { key: "", name: "기관 미지정" }]) {
      const rows = byF.get(f.key) || [];
      if ((f.key === "~" || f.key === "") && !rows.length) continue;
      box.append(gatherFolderEl(f, rows, off));
    }
  }
  // 「기관 문서 추가」 — 이미 올린 문서 고르기(지금 과제의 문서 + 과제 이름 없는 문서) · 폴더 단추로 올리기(올리면 스크립트 분석을 바로 건다) — 기관 미지정으로 넣는다
  const add = el("div", "gt-add"), pick = el("select"), up = el("button", "icon dv-flow-up"), proj = (w) => (w.task || {}).project || "", have = new Set(parts.map((p) => p.work));
  const cands = !plan || !P || !V ? [] : taskDocs().filter((w) => w.id !== plan.id && !have.has(w.id) && String(w.format || "hwpx").toLowerCase() !== "docx" && (!proj(w) || taskSameScope(w)));
  pick.dataset.gatherAdd = "1";
  pick.dataset.gatherFocus = "add";
  pick.setAttribute("aria-label", "기관 문서 추가 — 올린 문서에서 고르기");
  pick.append(new Option(g.partBusy || (cands.length ? `기관 문서 추가 — 올린 문서 ${cands.length}개에서 고르기` : "기관 문서 추가 — 고를 문서 없음(오른쪽 폴더 단추로 올리기)"), ""));
  for (const w of cands) { const k = (w.task || {}).file; pick.append(new Option(w.name + (w.id === state.id ? " — 지금 문서" : "") + (k && k !== gatherSpec().parts ? ` (${taskName("file", k)})` : ""), w.id)); }
  pick.disabled = busy || !!off || !cands.length;
  pick.title = off || "기관에서 들어온 문서를 이 취합에 넣습니다 — 다른 기관 문서는 그대로 남습니다";
  pick.onchange = () => { if (pick.value) gatherPartAdd(pick.value); };
  up.type = "button";
  up.dataset.gatherUp = "1";
  up.disabled = busy || !!off;
  up.title = off || "기관 문서 올리기 — hwp·hwpx 파일(여러 개)을 올려 이 취합에 넣습니다(반영할 기관은 미지정 — 기관 폴더의 올리기 단추로 올리면 그 기관 · hwp 는 hwpx 로 바꿔 받음 · 지금 보는 문서는 그대로 · 헤딩·표 분석을 바로 겁니다)";
  up.setAttribute("aria-label", "기관 문서 올리기");
  up.innerHTML = GT_FOLDER_SVG;
  up.onclick = () => gatherPickFiles((fs) => gatherUploadMany(fs));
  add.append(pick, up);
  box.append(add);
  if (g.err && !V) box.append(el("p", "dv-caption gt-note", g.missing ? "취합은 서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : `취합 상태를 읽지 못했습니다: ${g.err}`));
  return box;
}

// ---- 기관별 폴더(spec_취합 ② §5 「기관별 폴더」, 2026-11-13 사용자 "업로드 되면 기관별로 폴더를 두고 파일을 관리") — 화면만: 폴더 = 반영할 기관이 그 기관 하나인 기관 문서(gather.json 은 그대로)
const GT_FOLDER_SVG = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7.5a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
function gatherFolderOf(p, all) { const cur = p.orgs || []; return !cur.length ? "" : cur.length === 1 && all.includes(cur[0]) ? cur[0] : "~"; } // 그 문서의 폴더 — 기관 열쇠 · "" 미지정 · "~" 여러 기관·그 밖
function gatherPickFiles(fn) { const inp = el("input"); inp.type = "file"; inp.accept = ".hwp,.hwpx"; inp.multiple = true; inp.onchange = () => fn([...inp.files]); inp.click(); }
function gatherFolderEl(f, rows, off) { // 폴더 하나 — 머리(접기 · 기관 이름(역할) · 문서 수 · 올리기) + 그 기관의 기관 문서 줄. 파일·기관 문서 줄을 놓으면 그 기관으로
  const g = gt(), box = el("div", "gt-folder"), head = el("div", "gt-folder-head"), tog = el("button", "gt-folder-tog"), n = rows.length, role = GT_ROLE[f.role] || "";
  const fold = (g.fold = g.fold || {}), drop = f.key !== "~"; // 「여러 기관·그 밖」 은 놓는 곳이 아니다(어느 기관으로 할지 모름)
  const shut = n > 0 && !!fold[f.key], label = f.name + (role ? ` (${role})` : "");
  box.dataset.org = f.key;
  box.classList.toggle("gt-folder-empty", !n);
  box.classList.toggle("shut", shut);
  tog.type = "button";
  tog.dataset.gatherFocus = `fold:${f.key}`;
  if (n) tog.setAttribute("aria-expanded", String(!shut));
  tog.title = !n ? `${label} — 아직 받은 문서가 없습니다${drop ? "(오른쪽 단추로 올리거나 파일·기관 문서 줄을 여기에 끌어 놓으세요)" : ""}` : `${label} — 기관 문서 ${n}개(누르면 ${shut ? "펴기" : "접기"})`;
  const ic = el("span", "gt-folder-ic");
  ic.innerHTML = GT_FOLDER_SVG.replace('width="20" height="20"', 'width="16" height="16"');
  tog.append(el("span", "gt-folder-caret", n ? (shut ? "▸" : "▾") : ""), ic, el("span", "gt-folder-name", f.name), role ? el("span", "gt-folder-role", role) : "", el("span", "gt-folder-n", n ? `${n}개` : "없음"));
  tog.onclick = () => { if (!n) return; fold[f.key] = !box.classList.contains("shut"); box.classList.toggle("shut", fold[f.key]); tog.setAttribute("aria-expanded", String(!fold[f.key])); tog.firstChild.textContent = fold[f.key] ? "▸" : "▾"; };
  head.append(tog);
  const busy = () => !!gt().partBusy || !!gatherRun, why = () => off || (busy() ? "저장·진행 중입니다 — 끝난 뒤에 하세요" : "");
  if (drop && f.key) { // 「기관 미지정」 의 올리기는 맨 아래 「기관 문서 추가」 의 폴더 단추가 한다(같은 것을 두 곳에 두지 않는다 — design.md §10) · 놓기는 받는다
    const up = el("button", "icon dv-flow-up gt-folder-up");
    up.type = "button";
    up.dataset.gatherFolderUp = f.key;
    up.dataset.gatherFocus = `fup:${f.key}`;
    up.disabled = !!why();
    up.title = why() || `${label} 문서 올리기 — hwp·hwpx 파일(여러 개)을 올려 ${f.key ? `반영할 기관을 「${f.name}」 으로` : "기관 미지정으로"} 넣습니다(헤딩·표 분석을 바로 겁니다) · 파일을 이 폴더에 끌어 놓아도 됩니다`;
    up.setAttribute("aria-label", `${f.name} 폴더에 문서 올리기`);
    up.innerHTML = GT_FOLDER_SVG;
    up.onclick = () => gatherPickFiles((fs) => gatherUploadMany(fs, f.key || null));
    head.append(up);
  }
  box.append(head, ...rows);
  const kind = (e) => (gatherPartDragIs(e) ? "part" : e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files") ? "files" : "");
  box.addEventListener("dragover", (e) => { // 창의 파일 놓기(그냥 열기 — app.js bind)보다 먼저 받는다
    const k = kind(e);
    if (!k) return;
    e.preventDefault();
    e.stopPropagation();
    $("drop").classList.remove("over");
    const ok = drop && !why();
    e.dataTransfer.dropEffect = ok ? (k === "part" ? "move" : "copy") : "none";
    box.classList.toggle("gt-drop", ok);
  });
  box.addEventListener("dragleave", (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("gt-drop"); });
  box.addEventListener("drop", (e) => {
    const k = kind(e);
    if (!k) return;
    e.preventDefault();
    e.stopPropagation();
    box.classList.remove("gt-drop");
    if (!drop) return toast("「여러 기관·그 밖」 에는 놓을 수 없습니다 — 기관 폴더나 「기관 미지정」 에 놓으세요", true);
    if (why()) return toast(why(), true);
    if (k === "files") return void gatherUploadMany([...e.dataTransfer.files], f.key || null);
    const pid = e.dataTransfer.getData(GT_PART), p = gatherPart(pid);
    if (p && gatherFolderOf(p, ((gt().view || {}).orgs || []).map((o) => o.key)) !== f.key) gatherPartSet(pid, { orgs: f.key ? [f.key] : [] });
  });
  return box;
}

function gatherOrgsEl() { // 기관 현황 한 줄 — 받은 기관 · 반영한 기관 · 아직 없는 기관(문서를 안 낸 기관이 있어도 취합은 진행한다 — 어느 기관이 빠졌는지 보인다)
  const V = gt().view, orgs = (V && V.orgs) || [], p = el("p", "dv-caption gt-orgs");
  if (!orgs.length) { p.hidden = true; return p; }
  const names = (xs) => (xs.length ? `(${xs.map((o) => o.name).join(" · ")})` : "");
  const sets = [["received", "받은 기관", orgs.filter((o) => (o.received || []).length)], ["applied", "반영한 기관", orgs.filter((o) => (o.applied || []).length)], ["missing", "아직 없는 기관", orgs.filter((o) => !(o.received || []).length)]];
  sets.forEach(([k, label, xs], i) => { const s = el("span", k === "missing" && xs.length ? "gt-orgs-miss" : null, `${label} ${xs.length}${names(xs)}`); s.dataset.k = k; p.append(i ? " · " : "", s); });
  p.append(hHelp("기관 현황 설명", "받은 기관: 반영할 기관으로 지정한 문서가 있는 기관입니다(내용이 모두 겹쳐도 받은 것으로 셉니다). 반영한 기관: 내용이 취합본에 들어간 기관입니다. 아직 없는 기관이 있어도 받은 문서부터 취합할 수 있습니다."));
  return p;
}

// ---- 기관 문서 넣기·빼기·반영할 기관(PUT/DELETE …/gather/parts/{id}) — 이관의 칸 바꾸기(taskSlotSet)를 안 거친다: 다른 문서를 과제에서 내보내지 않는다
async function gatherPartCall(pid, method, body, fail) {
  const g = gt(), epoch = state.epoch;
  try {
    const V = await gatherCall(gatherSeg(pid), method, body);
    if (epoch !== state.epoch || g !== gatherState) return false;
    gatherViewSet(V);
    delete g.plans[pid]; // 설정의 판(version)이 바뀌었다 — 세워 둔 계획은 못 쓴다
    return true;
  } catch (e) { toast(`${fail}: ${gatherErr(e)}`, true); return false; }
}
async function gatherPartSet(pid, body) { // 반영할 기관({orgs}) · 공통 자리 포함({common}) — 상태 판정이 달라지므로 읽어 둔 작성 내용은 버린다(열려 있는 목록은 다시 읽는다)
  const g = gt();
  g.partBusy = "저장 중…";
  const ok = await gatherPartCall(pid, "PUT", body, "기관 문서 설정을 저장하지 못했습니다");
  if (g !== gatherState) return;
  g.partBusy = "";
  if (ok && heads.dlg === "gatherFill" && g.fillPart === pid) headsColClose();
  if (ok && heads.dlg === "gather" && g.listPart === pid) { // 목록을 닫았다 열지 않고 그 자리에서 새 판정으로
    try { await gatherLinks(pid); } catch (e) { toast(`기관 작성 내용을 다시 읽지 못했습니다: ${gatherErr(e)}`, true); }
    return;
  }
  if (ok) delete g.links[pid];
  gatherDraw();
}
async function gatherPartAdd(pid, name = "", org = null) { // org = 기관 폴더로 올린 것(그 기관을 반영할 기관으로 — 사람이 고른 것과 같다: ② §5 「기관별 폴더」)
  const g = gt(), w = worksList.find((x) => x.id === pid), oname = org ? (((g.view || {}).orgs || []).find((o) => o.key === org) || {}).name || org : "";
  g.partBusy = "기관 문서 넣는 중…";
  gatherDraw();
  const ok = await gatherPartCall(pid, "PUT", org ? { orgs: [org] } : {}, "기관 문서를 넣지 못했습니다");
  if (g !== gatherState) return false;
  g.partBusy = "";
  if (ok && pid === state.id) state.task = { ...state.task, kind: "rnd", file: gatherSpec().parts }; // 지금 문서를 넣었으면 화면의 종류도(서버가 작업에 적었다)
  gatherDraw();
  if (ok) { toast(`${name || (w && w.name) || "문서"} — ${org ? `「${oname}」 폴더에 넣었습니다` : "기관 문서로 넣었습니다(반영할 기관을 고르세요)"}`); await loadWorks(); } // 문서 목록의 종류 꼬리표·둘째 면의 탭도 새로
  return ok;
}
async function gatherPartDel(pid) {
  const g = gt(), p = gatherPart(pid);
  if (!p || !confirm(`「${p.name}」 을 이 취합에서 뺄까요?\n\n이미 넣은 내용은 취합본에 그대로 남습니다(되돌리려면 실행 취소). 문서 자체는 지워지지 않습니다.`)) return;
  g.partBusy = "빼는 중…";
  gatherDraw();
  const ok = await gatherPartCall(pid, "DELETE", null, "기관 문서를 빼지 못했습니다");
  if (g !== gatherState) return;
  g.partBusy = "";
  if (ok) { delete g.links[pid]; delete g.done[pid]; }
  if (ok && ((heads.dlg === "gather" && g.listPart === pid) || (heads.dlg === "gatherFill" && g.fillPart === pid))) headsColClose();
  gatherDraw();
  if (ok) { peerSync(); loadWorks(); }
}
async function gatherUpload(file, org = null) { // 새 작업으로 올리고(?new=1 — 열지는 않는다) 스크립트 분석을 바로 건 뒤 이 취합에 넣는다(org = 기관 폴더로 올림) → 넣었으면 true
  if (!file) return false;
  if (!/\.hwpx?$/i.test(file.name)) { toast("hwp·hwpx 파일만 올릴 수 있습니다", true); return false; } // hwp 는 서버가 hwpx 로 바꿔 받는다
  const epoch = state.epoch, fd = new FormData();
  fd.append("file", file);
  toast(/\.hwp$/i.test(file.name) ? `${file.name} — hwpx 로 바꿔 올리는 중…(한글이 변환)` : `${file.name} 올리는 중…`);
  let d;
  try { d = await api("/api/docs?new=1", { method: "POST", body: fd }); }
  catch (e) { toast(`올리지 못했습니다: ${e.message}`, true); return false; }
  api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 못 걸어도 2단계 줄이 「헤딩·표 분석 없음」 으로 안내한다
  if (epoch !== state.epoch) return false;
  return gatherPartAdd(d.docId, file.name, org);
}
async function gatherUploadMany(files, org = null) { // 폴더 단추·폴더에 놓기 — 여러 파일을 고른 차례대로 하나씩(들어온 차례 = 공통 자리 차지 차례). 하나가 실패하면 그 뒤는 멈춘다(알림은 gatherUpload)
  const ok = files.filter((f) => /\.hwpx?$/i.test(f.name)), bad = files.length - ok.length;
  if (bad) toast(`hwp·hwpx 파일만 올릴 수 있습니다 — ${bad}개는 뺐습니다`, true);
  const epoch = state.epoch;
  for (const f of ok) if (epoch !== state.epoch || !(await gatherUpload(f, org))) break;
}

// ---- 단계(spec_취합 ② §5 · §9-1 「묶음 셋」) — 1단계 = 준비 · 프로젝트 구성 추출, 2단계 = ① 구분 기준 확인 · 배포 기준본, 3단계 = 기관 문서마다 한 줄(② 자리 연결 → LLM 검토 → ③ 넣기 계획 → ④ 내용 반영)
function gatherDiv() { // 취합본의 구분 기준 {values | null, applied | null, ok(지원 양식), confirmed(확정 — spec_작업 ② §18) | null, sharing} — 지금 문서면 화면 값(dv), 아니면 읽어 둔 것. undefined = 아직 못 읽음
  const plan = gatherPlan();
  if (!plan) return undefined;
  if (plan.id !== state.id) return gt().div;
  if (!dv.view || !dv.values) return undefined;
  return { values: dv.view.settings || dv.view.applied || dv.dirty ? divValues() : null, applied: dv.view.applied || null, ok: !!dv.view.profile.supported,
    confirmed: dv.view.confirmed || null, sharing: dv.view.projectSharing || null };
}
const gatherConfirmed = (d) => divConfirmValid(d && d.values, d && d.confirmed); // 1단계 「프로젝트 구성 추출」 끝남 — 지금 입력 값이 확정한 값과 같다(app.js divConfirmValid)
const gatherDivDone = (d) => !!(d && d.values && d.applied && divCanon(d.applied.values) === divCanon(d.values)); // 입력 값이 문서에 반영돼 있다(반영 뒤 글을 고쳤다고 「다시」 를 요구하지 않는다)
function gatherFrameText() { // 프레임 값 요약(1단계 머리 — 접혀 있어도 보임) → {text, title} · 값이 없으면 text ""
  const d = gatherDiv(), v = d && d.values;
  if (!v) return { text: "", title: "" };
  let start = 1;
  const stages = (v.stages || []).map((n, i) => { const y = Number(n) || 1, s = `${i + 1}단계(${y === 1 ? start : `${start}–${start + y - 1}`}차년도)`; start += y; return s; });
  const orgs = v.orgs || {}, joint = (orgs.joint || []).map((n, i) => n || `참여기관${i + 1}`);
  const text = `${stages.join(" · ")} · 주관 ${orgs.lead || "미입력"} · 공동 ${joint.length}${joint.length ? `(${joint.join(" · ")})` : ""}`;
  return { text, title: `문서 프레임 값(취합본)\n${text}` };
}
async function gatherToPlan() { // 취합본을 고치는 문서로(두 문서의 자리는 그대로 — 취합본이 왼쪽) → 됐으면 true
  const plan = gatherPlan();
  if (!plan) return false;
  if (state.id !== plan.id) {
    await openWork(plan.id);
    if (state.id !== plan.id) return false; // 바꾸지 않음(저장 안 한 글을 두고 그만둠) · 못 엶
  }
  taskPaneShow(); // 보통 패널 「작업 개요」 — 에이전트 보기가 이 TASK 를 이끌고 있으면 그대로(app.js — 진행 카드가 거기 있다)
  await divShow();
  if (state.id !== plan.id || !dv.view) return false;
  await gatherLoad();
  return true;
}

function gatherSteps() { // → [{stage, step(files|division|frame|part), key, part?, no, name, done, early?, runnable?, busy?, keep?, lines[[이름, 글]], acts[{label, run, primary?, disabled?, title?, data?} | {el}]}]
  const g = gt(), plan = gatherPlan(), V = plan ? g.view : null, d = gatherDiv(), mine = gatherMine(), running = !!gatherRun; // 취합본 칸이 비면 읽어 둔 상태도 안 쓴다
  const onPlan = (label, run, opt = {}) => ({ label, ...opt, title: (opt.title || "") + (mine ? "" : "\n취합본을 고치는 문서로 바꾼 뒤 이어서 합니다 — 두 문서의 자리는 그대로입니다"),
    run: async () => { if (!gatherMine() && !(await gatherToPlan())) return; run(); } }); // 취합본에서 하는 일(변경 계획·기준본·넣기 계획 …) — 다른 문서를 보고 있어도 단추는 같다
  const sum = (v) => `${v.stages.length}단계 · 전체 ${divTotalYears(v)}년 · 기관 ${((v.orgs || {}).joint || []).length + 1}곳`;

  // 준비 — 취합본 문서(1단계 묶음 · 세지 않음)
  const files = { stage: "config", step: "files", key: "files", no: "", name: "준비", done: !!plan, lines: [], acts: [] };
  if (!plan) files.lines.push(["", "사업계획서(취합본)를 위 칸에서 고르세요" + (taskProject() ? "" : " — 프로젝트 이름을 적으면 다른 문서를 고를 수 있습니다")]);
  else files.lines.push(["", plan.name]);

  // 1단계 「프로젝트 구성 추출」 — 단계·차년도·기관 구성만 정해 프로젝트에 저장(확정). 문서는 안 바뀐다(spec_작업 ② §18 · spec_취합 ② §9-1)
  const config = { stage: "config", step: "config", key: "config", no: "", name: "프로젝트 구성 추출", done: false, lines: [], acts: [], busy: !!dv.busy && mine };
  const cf = d && d.confirmed, where = divConfirmWhere(d && d.sharing);
  if (!files.done) { /* 준비가 먼저 */ }
  else if (d === undefined) config.lines.push(["", "취합본의 프로젝트 구성 값을 읽는 중…"]);
  else if (gatherConfirmed(d)) Object.assign(config, { done: true, lines: [["", `${where}에 확정함(${gatherWhen(cf.at)}) — ${sum(d.values)}`]] });
  else if (!d.values) Object.assign(config, { lines: [["", "프로젝트 구성(단계·차년도·기관)이 없습니다 — 취합본에서 추출하거나, 아래 「프로젝트 구성 불러오기」 · 입력 칸에서 정하세요"]],
    acts: [onPlan("취합본에서 추출", () => divRead(), { primary: true, disabled: dv.busy, data: { gatherConfigRead: "1" }, title: "취합본에 적힌 단계·차년도·기관을 읽어 입력 칸에 채웁니다 — 문서는 안 바뀌고, 확인한 뒤 「프로젝트에 저장」 으로 확정합니다" })] });
  else {
    const save = onPlan(dv.busy && mine ? "저장 중…" : `${where}에 저장`, () => divConfirm(), { primary: true, disabled: dv.busy, data: { gatherConfirm: "1" },
      title: `지금 입력 값(단계·차년도·기관)을 ${divConfirmWhat(where)}으로 확정합니다 — 문서는 바뀌지 않습니다. 확정해야 2단계 「문서 프레임 작성」 으로 갑니다` });
    if (cf) Object.assign(config, { lines: [["", `확정한 뒤 값이 바뀌었습니다 — 다시 저장하거나 확정본으로 되돌리세요(지금: ${sum(d.values)})`]],
      acts: [save, onPlan("확정본으로 되돌리기", () => divConfirmRevert(cf), { disabled: dv.busy, title: `입력 칸을 확정한 값(${sum(cf.values)})으로 되돌립니다` })] });
    else Object.assign(config, { lines: [["", `${sum(d.values)} — 확인한 뒤 ${where}에 저장(확정)하세요`]], acts: [save] });
  }

  // ① 구분 기준 확인 — 취합본에 과제 구성 값이 반영돼 있다(구분 기준의 계획 → 반영 그대로 — 기관 문서 없이 할 수 있다)
  const division = { stage: "frame", step: "division", key: "division", no: "①", name: "프로젝트 구성 반영", done: false, lines: [], acts: [], busy: !!dv.busy && mine };
  if (!config.done) { /* 1단계(프로젝트 구성 추출)가 먼저 */ }
  else if (gatherDivDone(d)) Object.assign(division, { done: true, lines: [["", `${d.applied.adopted ? "구조가 이미 값에 맞음(확인함)" : "취합본에 반영됨"} — ${sum(d.values)}`]] }); // adopted = 구조 확인(② §8-4)
  else if (d.ok === false) division.lines.push(["", "이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다(연구개발계획서 양식만)"]);
  else Object.assign(division, { lines: [["", d.applied ? "입력한 값이 마지막으로 반영한 값과 다릅니다 — 변경 계획을 확인하고 반영하세요" : "값이 아직 취합본에 반영되지 않았습니다 — 바뀔 자리를 확인한 뒤 반영합니다(절·표 행·열 — 구조만)"]],
    acts: [onPlan(dv.busy && mine ? "계산 중…" : "변경 계획 보기", () => divPlan(), { primary: true, disabled: dv.busy, title: "취합본에서 바뀔 자리를 확인한 뒤 「반영」 합니다 — 문서는 「반영」 을 눌러야 바뀝니다" })] });

  // 배포 기준본 — 1단계가 끝난 취합본을 그때의 파일 그대로 고정한 것(+ 자리 정보). 기관에 나눠 주는 파일이고, 기관 문서는 이것과 견준다
  const F = V && V.frame, frameOk = !!(F && !F.stale);
  const frame = { stage: "frame", step: "frame", key: "frame", no: "◆", name: "배포 기준본", done: frameOk, keep: true, lines: [], acts: [], busy: !!g.frameBusy }; // 번호 없음 — ②③④ 는 공통 차례(자리 연결 · 넣기 계획 · 내용 반영)의 것
  const file = () => { const a = el("a", "btn sm", "기준본 내려받기"); a.href = gatherUrl("/frame/file"); a.setAttribute("download", ""); a.dataset.gatherFrameFile = "1";
    a.title = "고정해 둔 기준본 파일(hwpx)을 내려받습니다 — 기관에 나눠 주는 파일" + (F && F.stale ? "(낡은 판)" : ""); return { el: a }; };
  const make = (label, primary) => onPlan(g.frameBusy ? "만드는 중…" : label, () => gatherFrameClick(), { primary, disabled: !!g.frameBusy || running, data: { gatherFrameMake: "1" },
    title: "지금 취합본 파일과 자리 정보(자리마다 기관·차년도 · 문단 헤딩·표·서식)를 고정합니다 — 문서는 안 바뀝니다. 헤딩·표 분석이 지금 문서의 것이 아니면 먼저 다시 분석합니다(스크립트)" });
  if (!config.done || !division.done) { if (F) Object.assign(frame, { lines: [["", `기준본 ${gatherWhen(F.at)} 만듦${F.stale ? " — 낡음(프로젝트 구성을 다시 반영함)" : ""}`]], acts: [file()] }); } // ① 이 먼저 — 있는 기준본은 받을 수 있다
  else if (g.frameBusy) frame.lines.push(["", `${g.frameBusy}…`]);
  else if (!V) Object.assign(frame, { lines: [["", g.err ? (g.missing ? "취합은 서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : `취합 상태를 읽지 못했습니다: ${g.err}`) : "취합 상태를 읽는 중…"]],
    acts: g.err && !g.missing ? [{ label: "다시 읽기", run: () => gatherLoad() }] : [] });
  else if (frameOk) Object.assign(frame, { lines: [["", `기준본 ${gatherWhen(F.at)} 만듦 — 내려받아 기관에 나눠 주세요(기관은 자기 몫만 채워 돌려줍니다)`]], acts: [file(), make("기준본 다시 만들기", false)] });
  else if (F) Object.assign(frame, { lines: [["", "기준본을 만든 뒤 프로젝트 구성을 다시 반영했습니다 — 기준본이 낡았습니다. 새로 만들어 다시 나눠 주세요(낡은 기준본으로 온 기관 문서는 저절로 넣지 않습니다)"]],
    acts: [make("기준본 다시 만들기", true), file()] });
  else Object.assign(frame, { lines: [["", "기관에 나눠 줄 기준본을 만듭니다 — 지금 취합본 파일과 자리 정보(자리마다 기관·차년도)를 고정합니다" + ((V.reasons || []).length ? ` · ${gatherReasons(V.reasons)}` : "")]],
    acts: [make("기준본 만들기", true)] });
  const usable = frameOk; // 기관 문서는 기준본과 견준다 — 기준본이 있어야(낡지 않아야) 2단계의 줄이 열린다

  // 3단계 — 기관 문서마다 한 줄(들어온 차례)
  const parts = ((V && V.parts) || []).map((p, i) => {
    const pid = p.work, S = g.links[pid] || {}, L = S.data, c = (L && L.counts) || p.counts || null, P = g.plans[pid], R = g.done[pid], todo = gatherPartTodo(p);
    const why = gatherHard([...new Set([...(p.reasons || []), ...(S.why || [])])]), assigned = (p.orgs || []).length > 0, blocked = why.length > 0, low = gatherLow(p); // low 는 막지 않는다 — 넣을 것을 사람이 고른다
    const busy = !!S.busy || g.llmBusy === pid || g.planBusy === pid || g.applyBusy === pid;
    const s = { stage: "map", step: "part", key: `part:${pid}`, part: pid, no: String(i + 1), name: p.name, lines: [], acts: [], keep: true, busy,
      done: assigned && !blocked && c != null && todo === 0 && !(low && c.ready > 0), early: usable && assigned, hold: usable && !assigned, runnable: usable && assigned }; // hold = 반영할 기관 미지정 — 사람이 고를 때까지 넣지 않는다(다른 문서는 진행 가능)
    if (!usable) return s;
    const list = { label: "기관 작성 내용", run: () => gatherListOpen(pid), disabled: !!S.busy, data: { gatherList: pid },
      title: "문서 옆 열에 이 문서에서 기관이 쓴 내용의 목록을 엽니다 — 줄을 누르면 취합본과 기관 문서가 그 자리로 갑니다" };
    if (!assigned) { s.lines.push(["", "반영할 기관을 위 기관 문서 줄에서 고르세요 — 미지정이면 넣지 않습니다" + (p.recommend ? `(작성 내용이 가장 많은 기관: ${((V.orgs || []).find((o) => o.key === p.recommend.org) || {}).name || p.recommend.org})` : "")]); if (c) s.acts.push(list); return s; }
    if (blocked) {
      s.lines.push(["② 자리 연결", `할 수 없습니다 — ${gatherReasons(why)}`]);
      if (why.includes("noHeadings")) s.acts.push(onPlan(busy ? "분석 중…" : "헤딩·표 분석", () => gatherPartAnalyze(pid), { primary: true, disabled: busy || running, title: "이 기관 문서의 헤딩·표를 분석한 뒤(스크립트 — LLM 호출 없음) 자리 연결을 다시 합니다" }));
      else if (!why.includes("noFrame") && !why.includes("frameStale")) s.acts.push(onPlan(S.busy ? "맞추는 중…" : "다시 맞춤", () => gatherRelink(pid), { disabled: busy || running, title: "기준본과 이 문서를 다시 견줍니다 — 사람·LLM 이 고른 것은 유지" }));
      return s;
    }
    if (!c) {
      s.lines.push(["② 자리 연결", S.busy ? "기준본과 견주는 중…" : "아직 안 함 — 기준본과 견줘 기관이 쓴 내용을 찾습니다"]);
      s.acts.push(onPlan(S.busy ? "맞추는 중…" : "자리 연결", () => gatherListOpen(pid), { primary: true, disabled: busy || running, data: { gatherLink: pid } }));
      return s;
    }
    s.lines.push(["② 자리 연결", gatherCountText(c) + (S.busy ? " · 읽는 중…" : "")]);
    if (low) s.lines.push(["", `${GT_REASON.lowMatch}(「기관 작성 내용」 에서 넣음을 켠 것만 넣습니다)`]);
    const llm = L ? L.llm : p.llm, held = (llm && llm.held ? ` · 보류 ${nf(llm.held)}(확인 필요로 둠)` : "") + (llm && llm.stale ? ` · 낡은 판정 ${nf(llm.stale)}(자료가 바뀜 — 다시 검토)` : "");
    s.lines.push(["LLM 검토", g.llmBusy === pid ? "검토 중…(수십 초)" : llm ? `검토함(${gatherWhen(llm.at)}${held})` : c.ready ? "아직 안 함 — 문단·표의 특성을 살펴 넣을 내용만 남깁니다(안 해도 넣기 계획은 세울 수 있습니다)" : "대상 없음"]);
    if (P) s.lines.push(["③ 넣기 계획", gatherPlanText(P)]);
    if (R) s.lines.push(["④ 내용 반영", gatherDoneText(R)]);
    else if (s.done) s.lines.push(["④ 내용 반영", c.same ? "넣을 것이 더 없습니다(이미 들어 있음)" : "넣을 것이 없습니다"]);
    else if (P && P.todo) s.lines.push(["④ 내용 반영", "「계획 보기」 에서 확인하고 「반영」 을 누르세요"]);
    const first = !llm && c.ready > 0 ? "llm" : P && P.todo ? "view" : !P && todo !== 0 ? "plan" : ""; // 강조 = 다음 할 일(카드에 하나)
    s.acts.push(list);
    if (c.ready > 0) s.acts.push(onPlan(g.llmBusy === pid ? "LLM 검토 중…" : llm ? "LLM 다시 검토" : "LLM 검토", () => gatherLlm(pid), { primary: first === "llm", disabled: busy || running || !!g.llmBusy || !c.ready, data: { gatherLlm: pid },
      title: "넣을 수 있는 작성 내용을 취합본의 챕터별로 나눠 LLM(Opus)에 묻습니다 — 수십 초 · 유료. LLM 은 넣을 것을 줄이기만 합니다(제외·확인 필요) — 스크립트가 막은 것을 넣게 하지 못하고, 사람이 고른 것은 안 바꿉니다. 판단 기준은 「지침」 에서 봅니다" }));
    if (!PEEK) s.acts.push({ el: llmGuideBtn("gather", plan.id, `part=${encodeURIComponent(pid)}`) }); // 이 LLM 검토에 보내는 지침·TASK 프롬프트·마지막 프롬프트(기관 문서마다)
    if (!s.done || P) s.acts.push(onPlan(g.planBusy === pid ? "계획 중…" : P ? "넣기 계획 다시" : "넣기 계획", () => gatherPlanMake(pid), { primary: first === "plan", disabled: busy || running, data: { gatherPlan: pid },
      title: "넣을 수 있는 작성 내용마다 넣을 문단·표·그림·칸·행을 셉니다 — 문서는 「반영」 을 눌러야 바뀝니다" }));
    if (P) s.acts.push({ label: "계획 보기", run: () => gatherFillList(pid), primary: first === "view", disabled: busy, data: { gatherFill: pid } });
    return s;
  });
  return [files, config, division, frame, ...parts];
}

function gatherCalc() { // 단계와 그 상태 — 첫 안 끝난 단계가 「지금」(묶음을 넘어 하나), 그 뒤의 기관 문서 줄은 기준본이 있으면 「진행 가능」(반영할 기관 미지정이면 「기관 미지정」 — 글만 보임)
  let open = true;
  gatherStepsLast = gatherSteps().map((s) => {
    const st = s.done ? "done" : open ? "now" : s.early ? "ready" : s.hold ? "hold" : "todo";
    if (!s.done) open = false;
    return { ...s, st };
  });
  return gatherStepsLast;
}
function gatherActEl(a, now) { // 단추 하나 — 강조는 「지금」 줄의 다음 할 일만
  if (a.el) return a.el;
  const b = hBtn(a.label, a.run, { cls: "btn sm" + (a.primary && now ? " primary" : ""), disabled: !!a.disabled, title: a.title || "" });
  for (const [k, v] of Object.entries(a.data || {})) b.dataset[k] = v;
  return b;
}
function gatherStepsEl(stage) { // 묶음 하나의 세부 목록(이관의 목록과 같은 꼴 — divisions.css .dv-flow-steps)
  const ol = el("ol", "dv-flow-steps gt-steps");
  ol.setAttribute("aria-label", `${stage.name} 세부 순서`);
  for (const s of (gatherStepsLast || gatherCalc()).filter((x) => x.stage === stage.id)) {
    const st = s.st, li = el("li"), body = el("div", "dv-flow-body"), title = el("div", "dv-flow-title");
    li.dataset.step = s.step;
    li.dataset.key = s.key;
    li.dataset.state = st;
    if (s.part) li.dataset.part = s.part;
    title.append(el("strong", null, s.name), el("span", "dv-flow-status"));
    body.append(title);
    if (st !== "todo") for (const [name, text] of s.lines) { const line = el("div", "dv-flow-text"); if (name) line.append(el("span", "gt-sub", name), " "); line.append(text); body.append(line); }
    li.append(el("span", "dv-flow-no", s.no || "·"), body);
    if ((st === "now" || st === "ready" || st === "hold" || (s.keep && st === "done")) && s.acts.length) { const acts = el("div", "dv-flow-acts"); acts.append(...s.acts.map((a) => gatherActEl(a, st === "now"))); li.append(acts); }
    ol.append(li);
  }
  if (stage.id === "map" && !ol.children.length) { const li = el("li", "gt-none"); li.dataset.step = "none"; li.dataset.state = "todo"; li.append(el("span", "dv-flow-no", "·"), el("div", "dv-flow-body", "기관 문서가 아직 없습니다 — 위 「기관 문서 추가」 로 넣으면 여기에 문서마다 한 줄이 생깁니다")); ol.append(li); }
  return ol;
}
function gatherStepsDraw() { // 두 묶음의 세부 목록을 다시 — 묶음 머리(끝난 수 · 상태 줄 · 「한 번에 진행」)도 함께. 프로젝트 구분 기준 입력을 바꿀 때마다(app.js divRefreshDerived → taskStepsDraw)
  if (!document.getElementById("gatherSteps")) return;
  gatherCalc();
  for (const stage of GT_STAGES) { const box = document.getElementById(stage.dom), old = box && box.querySelector("ol.dv-flow-steps"); if (old) old.replaceWith(gatherStepsEl(stage)); }
  gatherStageSync();
}

const gatherStageOpen = (stage) => { try { return localStorage.getItem(stage.store) === "1"; } catch { return false; } };
const gatherStepName = (s) => (s ? (s.step === "part" ? `기관 문서 ${s.no} 「${s.name}」` : `${s.no ? s.no + " " : ""}${s.name}`) : "");
function gatherStageEl(stage) { // 묶음 상자 하나(이관의 묶음과 같은 모양 — details.dv-phase: 머리 줄 · 진행 막대 · 상태 줄 · 접어 둔 세부 목록 · 「한 번에 진행」)
  const box = el("details", "dv-phase"), sum = el("summary"), st = el("span", "dv-phase-state"), spin = el("i", "dv-phase-spin"), run = el("button", "btn sm", "한 번에 진행"), progress = el("progress", "dv-phase-progress");
  box.id = stage.dom;
  box.dataset.stage = stage.id;
  box.open = gatherStageOpen(stage);
  box.ontoggle = () => { try { localStorage.setItem(stage.store, box.open ? "1" : "0"); } catch { /* 기억만 안 함 */ } gatherStageSync(); };
  run.type = "button";
  run.dataset.gatherRun = stage.id;
  run.onclick = (e) => { e.preventDefault(); e.stopPropagation(); if (gatherRun) { if (gatherRun.stage === stage.id) { gatherRun.stop = true; gatherStageSync(); } } else gatherRunAll(stage.id); }; // summary 안이라 — 누름이 접기·펴기로 넘어가지 않게
  spin.style.animationDelay = `-${Date.now() % 800}ms`; // 다시 그려도 동그라미가 처음부터 다시 돌지 않게(design.md §7)
  spin.hidden = true;
  st.append(spin, el("span"));
  sum.title = "세부 목록 펴기·접기 — 단계마다 따로 진행할 수 있습니다";
  progress.setAttribute("aria-label", "세부 작업 완료");
  run.setAttribute("aria-label", `${stage.no} ${stage.name} 한 번에 진행`);
  sum.append(el("span", "dv-phase-no", stage.no), el("strong", null, stage.name), hHelp(`${stage.name} 순서 설명`, stage.does), el("span", "dv-phase-count"), run, progress, st);
  box.append(sum, gatherStepsEl(stage));
  if (stage.id === "config") { // 1단계 = 구분 기준: 머리에 구성 요약 한 줄(접혀 있어도 보임) + 펴면 세부 목록 아래에 구성 입력(app.js divRender → taskFrameHost 가 #taskFrameForm 을 여기, 반영 상태·변경 계획은 2단계 묶음의 #taskFrameApply 에 둔다 — spec_작업 ② §18)
    const frame = el("span", "dv-phase-frame"), edit = el("button", "btn sm", "프로젝트 구성 고치기");
    frame.hidden = true;
    edit.type = "button";
    edit.dataset.gatherFrameEdit = "1";
    edit.title = "1단계를 펴고 프로젝트 구성 입력(불러오기·확정 · 단계·차년도 · 기관 구성)으로 갑니다";
    edit.onclick = (e) => { e.preventDefault(); e.stopPropagation(); taskFrameEdit(box); };
    frame.append(el("span", "dv-phase-frame-text"), edit);
    sum.append(frame);
  }
  gatherStageSync(stage, box);
  return box;
}
function gatherStageSync(only = null, el0 = null) { // 묶음 머리 — 끝난 수 · 상태 줄 · 단추. 단계 목록을 다시 그릴 때마다 · 도는 동안 1초마다(글만 바꾼다)
  if (!gatherStepsLast) return;
  for (const stage of GT_STAGES) if (!only || only === stage) gatherStageSync1(stage, el0 || document.getElementById(stage.dom));
  gatherJourneySync();
}
function gatherStageSync1(stage, box) {
  if (!box) return;
  const all = gatherStepsLast, work = (id) => all.filter((s) => s.stage === id && s.step !== "files"), steps = all.filter((s) => s.stage === stage.id), W = work(stage.id), completed = W.filter((s) => s.done).length; // 준비(문서 고르기)는 안 센다
  const files = all.find((s) => s.step === "files"), next = steps.find((s) => !s.done), R = gatherRun && gatherRun.stage === stage.id ? gatherRun : null, busy = steps.find((s) => s.busy);
  const before = GT_STAGES.slice(0, GT_STAGES.indexOf(stage)).find((g) => work(g.id).some((s) => !s.done)) || null; // 덜 끝난 앞 묶음 — 그 뒤에야 이 묶음의 「한 번에 진행」 이 켜진다
  const current = GT_STAGES.find((g) => work(g.id).some((s) => !s.done)), plan = gatherPlan();
  const last = gatherRunLast && gatherRunLast.stage === stage.id && plan && gatherRunLast.plan === plan.id && gatherRunLast.done === completed ? gatherRunLast : null;
  const runnable = stage.id === "map" ? steps.filter((s) => !s.done && s.runnable) : steps.filter((s) => !s.done && s.step !== "files");
  box.querySelector(".dv-phase-count").textContent = `${completed}/${W.length} 완료`;
  const progress = box.querySelector(".dv-phase-progress");
  progress.max = W.length || 1;
  progress.value = completed;
  progress.setAttribute("aria-valuetext", `세부 작업 ${W.length}개 중 ${completed}개 완료`);
  const st = box.querySelector(".dv-phase-state"), key = (k) => gatherStepName(steps.find((s) => s.key === k));
  let kind = "next", msg = "";
  if (R) { kind = "run"; msg = `${key(R.key)}${R.note ? ` — ${R.note}` : ""} · ${fmtDur((Date.now() - R.t0) / 1000)}${R.stop ? " · 이 일이 끝나면 멈춥니다" : ""}`; }
  else if (busy) { kind = "run"; msg = `${gatherStepName(busy)} — 진행 중`; }
  else if (before) msg = `${before.no}(${before.name}) 뒤에 — ${stage.does}`; // 이전 완료 기록보다 지금의 선행 조건을 우선한다.
  else if (last && !last.ok) { kind = "halt"; msg = `멈춤 — ${key(last.key) || stage.name}: ${last.text}`; }
  else if (last) { kind = "done"; msg = `끝남 — ${last.text}`; }
  else if (stage.id === "map" && !W.length) msg = "기관 문서가 아직 없습니다 — 위 「기관 문서 추가」 로 넣으세요(문서마다 자리 연결 → LLM 검토 → 넣기 계획 → 내용 반영)";
  else if (!next) { kind = "done"; msg = stage.id === "map" ? "모두 끝남 — 기관 문서마다 넣을 것이 남지 않았습니다" : stage.id === "config" ? "모두 끝남 — 프로젝트 구성을 확정했습니다(문서 프레임은 2단계)" : "모두 끝남 — 기준본을 내려받아 기관에 나눠 주세요"; }
  else msg = `다음: ${gatherStepName(next)}${!box.open && next.lines.length ? ` — ${next.lines[0][1]}` : ""}`;
  st.dataset.kind = kind;
  st.firstChild.hidden = !(R || busy);
  if (st.lastChild.textContent !== msg) st.lastChild.textContent = msg;
  const frame = box.querySelector(".dv-phase-frame"); // 1단계만 — 프레임 값 요약(단계·차년도 · 기관)
  if (frame) {
    const f = gatherFrameText(), t = frame.firstChild;
    frame.hidden = !f.text;
    if (t.textContent !== f.text) t.textContent = f.text;
    if (t.title !== f.title) t.title = f.title;
  }
  // 취합형으로 조립한 워크플로우 — 그 정의에 이 묶음의 줄이 없으면 「한 번에 진행」 은 끈다(세부 단추로는 할 수 있다 — 붙박이는 늘 있다: task_catalog.js gatherDefStage)
  const lacks = runnable.length > 0 && !gatherDefStage(stage.id, (state.task && state.task.job) || "", runnable[0].key);
  const b = box.querySelector("[data-gather-run]"), ready = !!files && files.done && !before && runnable.length > 0 && !lacks;
  b.textContent = R ? (R.stop ? "멈추는 중…" : "멈춤") : "한 번에 진행";
  b.setAttribute("aria-label", `${stage.no} ${stage.name} ${b.textContent}`);
  b.disabled = R ? R.stop : !!gatherRun || !!busy || !ready;
  b.className = "btn sm" + (!gatherRun && ready && !box.open && current === stage ? " primary" : ""); // 강조 단추는 카드에 하나 — 할 일이 남은 첫 묶음의 것, 펴면 세부 목록의 「다음 할 일」
  b.title = R ? "지금 하는 일이 끝나면 멈춥니다 — 끝난 단계는 그대로 남습니다" : gatherRun ? "다른 묶음이 진행 중입니다" : busy ? "지금 진행 중인 작업이 끝나면 사용할 수 있습니다"
    : !(files && files.done) ? "사업계획서(취합본)를 먼저 고르세요" : before ? `${before.no} 「${before.name}」 을 먼저 끝내세요` : !runnable.length ? (stage.id === "map" ? "넣을 것이 남은 기관 문서가 없습니다(반영할 기관을 고른 문서만 진행합니다)" : "남은 단계가 없습니다")
    : lacks ? "이 워크플로우(조립한 것)에는 이 묶음의 줄이 없습니다 — 아래 세부 단추로 진행하세요"
    : `이 묶음의 남은 일을 차례로 한 번에 — ${stage.does}. 사람 손이 필요한 곳에서는 멈춥니다`;
  const active = R ? R.key : busy && busy.key;
  for (const li of box.querySelectorAll("ol.dv-flow-steps > li[data-key]")) { // 줄마다 상태 꼬리표(글자로 — 색에만 기대지 않는다)
    const s = all.find((x) => x.key === li.dataset.key);
    if (!s) continue;
    let status = li.dataset.state;
    if (active === s.key) status = "run";
    else if (!active && last && !last.ok && last.key === s.key) status = "halt";
    else if (active && status === "now") status = "todo";
    li.dataset.status = status;
    li.querySelector(".dv-flow-status").textContent = { done: "완료", now: "다음 작업", todo: "대기", ready: "진행 가능", hold: "기관 미지정", run: "진행 중", halt: "멈춤" }[status];
    if (active ? active === s.key : status === "now" || status === "halt") li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  }
}

// ---- 배포 기준본(POST …/gather/frame) — 그때의 저장 바이트와 자리 정보를 고정. 헤딩 2단계·표 3단계 분석이 지금 문서 차례의 것이 아니면 409 staleHeadings → 스크립트 분석을 다시 건 뒤 한 번 더
async function gatherAnalyze(id, body, alive = () => true) { // 스크립트 분석을 걸고 끝날 때까지(요약을 2초마다 읽음) — 409(다른 헤딩 작업이 도는 중)면 그 작업이 끝난 뒤 한 번 더 건다
  const post = () => api(`/api/docs/${id}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
  let mine = true;
  try { await post(); } catch (e) { if (e.status !== 409) throw e; mine = false; }
  for (let i = 0; i < 900; i++) { // 30분까지
    await new Promise((r) => setTimeout(r, GT_POLL));
    if (!alive()) return;
    const job = (await api(`/api/docs/${id}/headings`)).job;
    if (job && job.status === "running") continue;
    if (!mine) { try { await post(); mine = true; } catch (e) { if (e.status !== 409) throw e; } continue; }
    if (job && job.error) throw new Error(`헤딩·표 분석 실패 — ${job.error}`);
    return;
  }
  throw new Error("헤딩·표 분석이 끝나지 않습니다 — 「헤딩 추출」 탭에서 확인하세요");
}
async function gatherFramePost(note, alive) { // → 취합 상태 몸통. 실패는 던진다
  const plan = gatherPlan();
  await flushAll(); // 고치던 글을 먼저 서버에 — 기준본은 서버의 저장 바이트다
  for (let tries = 0; ; tries++) {
    try { return await gatherCall("/frame", "POST"); }
    catch (e) {
      if (e.status !== 409 || tries || !gatherWhy(e).includes("staleHeadings")) throw e;
      for (const stage of [2, 3]) { // 2단계(헤딩 그래프) → 3단계(표 구조), 스크립트만
        note(`헤딩·표 분석 ${stage}단계(스크립트 — 지금 문서로 다시)`);
        await gatherAnalyze(plan.id, { stage, llm: false }, alive);
        if (!alive()) throw new GatherHalt("눌러서 멈췄습니다");
      }
      if (plan.id === state.id) headsPeek(); // 쪽 여백 표시·헤딩 탭도 새 결과로
      note("기준본 만들기");
    }
  }
}
async function gatherFrameClick() { // 「기준본 만들기」·「기준본 다시 만들기」
  const g = gt(), V = g.view, epoch = state.epoch;
  if (g.frameBusy || !gatherMine()) return;
  if (V && V.frame && V.parts.length && !confirm("기준본을 다시 만들까요?\n\n새 기준본은 새 판입니다 — 앞서 나눠 준 기준본으로 온 기관 문서는 「기준본이 다름」 으로 저절로 넣지 못합니다(끌어 넣기만). 이미 넣은 내용은 그대로입니다.")) return;
  g.frameBusy = "기준본 만들기";
  gatherStepsDraw();
  try {
    const R = await gatherFramePost((t) => { if (g === gatherState) { g.frameBusy = t; gatherStepsDraw(); } }, () => epoch === state.epoch && g === gatherState);
    if (epoch !== state.epoch || g !== gatherState) return;
    gatherViewSet(R, true);
    toast("배포 기준본을 만들었습니다 — 「기준본 내려받기」 로 받아 기관에 나눠 주세요");
  } catch (e) { if (epoch === state.epoch) toast(`기준본을 만들지 못했습니다: ${gatherErr(e)}`, true); }
  finally { if (g === gatherState) { g.frameBusy = ""; gatherDraw(); } }
}

// ---- ② 자리 연결 · LLM 검토(GET|POST …/parts/{id}/links · PUT …/links/{열쇠} · POST …/llm) → gt().links[id]. 실패는 던진다(부른 쪽이 알림)
async function gatherLinks(pid, method = "GET", path = "/links", body = null) {
  const g = gt(), S = (g.links[pid] ||= { data: null, why: [], error: "", busy: 0 }), epoch = state.epoch;
  S.busy += 1;
  gatherDraw();
  try {
    const L = await gatherCall(gatherSeg(pid) + path, method, body);
    if (epoch !== state.epoch || g !== gatherState) return null;
    Object.assign(S, { data: L, why: [], error: "" });
    const V = g.view, i = V ? V.parts.findIndex((p) => p.work === pid) : -1; // 기관 문서 줄의 수·LLM 표시도 같은 값으로
    if (i >= 0) V.parts[i] = { ...V.parts[i], counts: L.counts || V.parts[i].counts, llm: L.llm === undefined ? V.parts[i].llm : L.llm, todo: gatherTodo(L), reasons: [], ...(L.part || {}) };
    return L;
  } catch (e) {
    if (g === gatherState && e.status === 409 && method !== "PUT") Object.assign(S, { data: null, why: gatherWhy(e), error: gatherErr(e) }); // 낼 수 없는 까닭(noFrame · frameStale · noHeadings · noMatch)은 그 줄에 남긴다
    throw e;
  } finally { S.busy -= 1; if (g === gatherState) gatherDraw(); }
}
async function gatherListOpen(pid, again = false) { // 「기관 작성 내용」·「자리 연결」 — 읽어 둔 것이 없으면 먼저 읽고 2열 목록을 연다(again = 설정이 바뀌어 다시 읽음)
  const g = gt(), S = g.links[pid];
  if (!again && S && S.data) { gatherList(pid); return; }
  if (S && S.busy) return;
  try { if ((await gatherLinks(pid)) && g === gatherState) gatherList(pid, again); }
  catch (e) { toast(`기관 작성 내용을 읽지 못했습니다: ${gatherErr(e)}`, true); }
}
async function gatherRelink(pid) { // 「다시 맞춤」 — 기준본 ↔ 기관 문서를 다시 견준다(POST …/links). 사람·LLM 이 고른 것은 열쇠가 같으면 유지
  const g = gt();
  try { if ((await gatherLinks(pid, "POST")) && g === gatherState) { delete g.plans[pid]; gatherDraw(); } }
  catch (e) { toast(`자리 연결을 하지 못했습니다: ${gatherErr(e)}`, true); }
}
async function gatherPartAnalyze(pid) { // 기관 문서의 헤딩·표 분석이 없을 때 — 스크립트 분석(있는 단계는 건너뜀) 뒤 다시 맞춤
  const g = gt(), S = (g.links[pid] ||= { data: null, why: [], error: "", busy: 0 }), epoch = state.epoch;
  S.busy += 1;
  gatherDraw();
  try { await gatherAnalyze(pid, { first: true }, () => epoch === state.epoch && g === gatherState); }
  catch (e) { toast(e.message, true); }
  finally { S.busy -= 1; }
  if (epoch !== state.epoch || g !== gatherState) return;
  S.why = [];
  await gatherLoad();
  if (g === gatherState) gatherRelink(pid);
}
async function gatherDecide(pid, key, value) { // 넣음/뺌(PUT …/links/{열쇠} {value: keep | skip | null}) — 넣을 수 있음(ready) 줄만
  const g = gt();
  try { await gatherLinks(pid, "PUT", `/links/${encodeURIComponent(key)}`, { value }); if (g === gatherState) { delete g.plans[pid]; gatherDraw(); } }
  catch (e) { toast(`바꾸지 못했습니다: ${gatherErr(e)}`, true); if (g === gatherState) gatherDraw(); }
}
async function gatherLlm(pid) { // LLM 순회 검토 — 사람이 누를 때만(유료). 답은 좁히는 쪽만(제외 · 확인 필요)
  const g = gt(), p = gatherPart(pid);
  if (!p || g.llmBusy) return;
  g.llmBusy = pid;
  toast(`LLM 검토 — 「${p.name}」 의 작성 내용을 챕터별로 나눠 살핍니다(수십 초)`);
  try {
    const L = await gatherLinks(pid, "POST", "/llm");
    if (L && g === gatherState) { delete g.plans[pid]; toast(`LLM 검토 끝 — 넣을 내용 ${nf(gatherTodo(L))}곳${L.llm && L.llm.held ? ` · 보류 ${nf(L.llm.held)}` : ""}`); }
  } catch (e) { toast(`LLM 검토를 하지 못했습니다: ${gatherErr(e)}`, true); }
  finally { if (g === gatherState) { g.llmBusy = ""; gatherDraw(); } }
}

function gatherPeekReady(wid) { try { const w = $("peerFrame").contentWindow; return w.gatherPeekId() === wid && !!w.document.querySelector("#doc .sheet .para"); } catch { return false; } }
function gatherPeekId() { return state.id; } // 둘째 면 화면에서: 바깥 창이 「그 문서를 다 그렸나」 를 물을 때(const state 는 window 의 속성이 아니다)
let gatherPeerSeq = 0;
function gatherPeerGo(wid, id) { // 둘째 면을 그 문서의 탭으로 바꾸고(열이 떠 있을 때만) 그 자리로 — 새로 읽는 중이면 다 그릴 때까지 잠깐 기다린다
  if (!wid || !id || $("peerCol").hidden) return;
  const seq = ++gatherPeerSeq, go = () => { try { $("peerFrame").contentWindow.gatherJump(id); } catch { /* 아직 여는 중 */ } };
  if (peerShown() !== wid) { peerPick = wid; peerKind = null; peerSync(); if (peerShown() !== wid) return; }
  const t0 = Date.now(), tick = () => { if (seq !== gatherPeerSeq || peerShown() !== wid || Date.now() - t0 > 20000) return; if (gatherPeekReady(wid)) go(); else setTimeout(tick, 200); };
  tick();
}
function gatherGo(pid, it) { // 줄을 누름 — 취합본은 그 자리(앞 경계 to.prev)로, 둘째 면은 그 기관 문서 탭의 그 내용(from.ids[0])으로
  const plan = gatherPlan(), to = it.to && (it.to.at || it.to.prev || it.to.next), from = it.from && (it.from.at || (it.from.ids || [])[0] || it.from.table); // at = 서버가 준 갈 자리(표 칸·표 행은 그 칸)
  if (gatherMine()) { if (to) gatherJump(to); gatherPeerGo(pid, from); }
  else if (state.id === pid) { if (from) gatherJump(from); if (plan) gatherPeerGo(plan.id, to); } // 기관 문서를 열어 보는 중이면 거꾸로
}
const gatherPlace = (it) => { // 자리 글 → [소속 사슬 끝, 기관·차년도, 사슬 전체]
  const sc = it.scope || {}, path = it.path || [];
  const who = sc.kind === "common" ? "공통 자리" : sc.kind === "unknown" ? "어느 기관 자리인지 모름" : [sc.orgName || sc.org, sc.year ? `${sc.year}차년도` : ""].filter(Boolean).join(" · ");
  return [path[path.length - 1] || "(제목 없는 자리)", who, path.join(" › ")];
};

function gatherList(pid, keep = false) { // 2열 「기관 작성 내용」(kind "gather") — 줄 = 상태 · 자리(소속 사슬 끝 · 기관·차년도) · 내용 앞부분 · LLM 의견. 넣을 수 있음 줄은 넣음/뺌
  const g = gt(), p = gatherPart(pid), S = g.links[pid] || {}, L = S.data, plan = gatherPlan();
  if (!p || !L || !plan) { if (heads.dlg === "gather") headsColClose(); else toast("기관 작성 내용이 아직 없습니다"); return; }
  g.listPart = pid;
  const top = keep ? $("headsDlgBody").scrollTop : 0, busy = !!S.busy || g.llmBusy === pid || g.applyBusy === pid || !!gatherRun, c = L.counts || {}, items = L.items || [];
  if (keep) heads.keepFold = true; // 배경에서 다시 그릴 때 접어 둔 열은 그대로
  const { tools, body, foot } = headsDlg("gather", `기관 작성 내용 — ${p.name}`, `${p.name} → ${plan.name} · 줄을 누르면 취합본과 기관 문서가 그 자리로`);
  heads.keepFold = false;
  if (!g.filter[pid] || (g.filter[pid] !== "all" && !c[g.filter[pid]])) g.filter[pid] = c.ready ? "ready" : "all"; // 처음에는 넣을 수 있는 것부터
  const F = g.filter[pid], filt = el("span", "dv-filter");
  for (const k of ["all", ...Object.keys(GT_STATUS).filter((x) => c[x])]) filt.append(hBtn(k === "all" ? `모두 ${items.length}` : `${GT_STATUS[k]} ${c[k]}`, () => { g.filter[pid] = k; gatherList(pid); },
    { cls: "btn sm" + (F === k ? " on" : ""), title: k === "all" ? "" : GT_STATUS_HELP[k] }));
  tools.append(filt);
  const cov = L.coverage;
  if (cov && cov.ratio != null) { const s = el("span", "muted", `자리 맞춤 ${Math.round(cov.ratio * 100)}%` + ((L.reasons || []).includes("lowMatch") ? ` — ${GT_REASON.lowMatch}` : "")); s.title = `기준본과 맞은 정도(참고값) — 닻 ${nf(cov.anchors)} · 블록 ${nf(cov.blocks)}`; tools.append(s); }
  const [tbl, tb] = hTable(["상태", "자리", "내용", "LLM 의견"]);
  tbl.classList.add("lk-table", "gt-table");
  const rows = items.filter((it) => F === "all" || it.status === F);
  for (const it of rows) {
    const tr = el("tr", "go" + (g.listSel === it.key ? " sel" : "")), tds = el("td", "gt-st"), d = it.decision || null, off = !!d && (d.value === "skip" || d.value === "check"), [place, who, full] = gatherPlace(it);
    tr.tabIndex = 0;
    tr.dataset.hunk = it.key;
    tr.dataset.status = it.status;
    tds.append(el("span", `dv-badge ${GT_BADGE[it.status] || ""}`, GT_STATUS[it.status] || it.status));
    tds.title = [GT_STATUS_HELP[it.status] || "", it.detail || ""].filter(Boolean).join("\n");
    if (it.status === "ready") { // 넣음/뺌 — 사람이 고른 것은 다시 맞춰도·LLM 검토를 돌려도 유지
      const lab = el("label", "gt-keep"), cb = el("input");
      cb.type = "checkbox";
      cb.checked = !off;
      cb.disabled = busy;
      cb.dataset.gatherKeep = it.key;
      cb.onchange = () => gatherDecide(pid, it.key, cb.checked ? "keep" : "skip");
      lab.onclick = (e) => e.stopPropagation(); // 줄 누름(그 자리로 가기)으로 넘어가지 않게
      lab.title = off ? (d.value === "check" ? "보류(확인 필요) — 켜면 넣습니다" : "뺌 — 켜면 넣습니다") : "넣음 — 끄면 이 내용은 넣지 않습니다(뺌)";
      lab.append(cb, el("span", null, off ? (d.value === "check" ? "보류" : "뺌") : "넣음"));
      tds.append(lab);
      if (d && d.source === "user") { const b = hBtn("되돌리기", (e) => { e.stopPropagation(); gatherDecide(pid, it.key, null); }, { disabled: busy, title: "사람이 고른 것을 지우고 스크립트·LLM 이 낸 결과로" }); b.classList.add("gt-undo"); tds.append(b); }
    }
    tr.append(tds);
    const tdp = el("td", "lk-place");
    tdp.append(el("div", "lk-to", place), el("div", "lk-from", who));
    tdp.title = full;
    tr.append(tdp);
    const tdt = el("td", "gt-text"), n = gatherNums(it.counts, ["paragraphs", "tables", "pictures", "cells", "rows"]);
    tdt.append(el("span", "gt-kind", GT_KIND[it.kind] || it.kind || ""), oneLine(it.text || "") || "(글 없음)");
    if (n) tdt.append(el("span", "gt-n", n));
    if (it.kind === "cells" && it.status === "ready" && it.detail) tdt.append(el("span", "gt-n", it.detail)); // 칸마다 상태가 갈린 표 칸 — 「넣을 칸 a · 겹침 b」(넣을 칸만 넣는다)
    tr.append(tdt);
    const tdl = el("td", "gt-llm");
    if (d && (d.nature || d.reason)) {
      if (d.nature) tdl.append(el("strong", null, d.nature));
      tdl.append(`${d.nature && d.reason ? " — " : ""}${d.reason || ""}`);
      if (d.source === "llm") tdl.append(" ", el("span", "dv-badge hinted", d.value === "skip" ? "LLM 제외" : d.value === "check" ? (d.held ? "LLM 검토 못 함(보류)" : "LLM 확인 필요") : "LLM 유지"));
      else if (d.source === "auto") tdl.append(" ", el("span", "dv-badge hinted", "직접 고르기")); // 기준본과 자리를 충분히 확인하지 못한 문서 — 사람이 넣음을 켠 것만 넣는다
    } else tdl.textContent = "—";
    tr.append(tdl);
    const go = () => { g.listSel = it.key; for (const x of tb.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); gatherGo(pid, it); };
    tr.onclick = go;
    tr.onkeydown = (e) => { if (e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); go(); } };
    tb.append(tr);
  }
  if (!rows.length) { const tr = el("tr"), td = hCell(tr, items.length ? "해당하는 작성 내용이 없습니다" : "기준본과 달라진 곳이 없습니다 — 기관이 쓴 내용을 찾지 못했습니다"); td.colSpan = 4; tb.append(tr); }
  body.append(tbl);
  $("headsDlgBody").scrollTop = top;
  const llm = L.llm;
  foot.append(el("span", "muted", gatherCountText(c) + (llm ? ` · LLM 검토함(${gatherWhen(llm.at)}${llm.held ? ` · 보류 ${nf(llm.held)}` : ""}${llm.stale ? ` · 낡은 판정 ${nf(llm.stale)}` : ""})` : "")));
  foot.append(hBtn(S.busy ? "읽는 중…" : "다시 맞춤", () => gatherRelink(pid), { disabled: busy, title: "기준본과 이 문서를 다시 견줍니다 — 사람·LLM 이 고른 것은 유지" }));
  if (c.ready) foot.append(hBtn(g.llmBusy === pid ? "LLM 검토 중…" : llm ? "LLM 다시 검토" : "LLM 검토", () => gatherLlm(pid), { disabled: busy || !!g.llmBusy, title: "넣을 수 있는 작성 내용을 LLM 이 살펴 넣을 내용만 남깁니다(수십 초 · 유료)" }));
  foot.append(hBtn(g.planBusy === pid ? "계획 중…" : "넣기 계획", () => gatherPlanMake(pid), { cls: "btn sm primary", disabled: busy || !gatherMine() || !gatherTodo(L), title: gatherMine() ? "넣음으로 둔 작성 내용의 넣기 계획을 세웁니다 — 문서는 「반영」 을 눌러야 바뀝니다" : "취합본을 고치는 문서로 연 뒤에 할 수 있습니다" }),
    hBtn("닫기", () => headsColClose()));
}

// ---- ③ 넣기 계획 → ④ 내용 반영(POST …/parts/{id}/plan · …/apply {planId}) — 기관 문서 하나 = 편집 하나(실행 취소 1)
async function gatherPlanMake(pid, { show = true } = {}) { // → 계획 | null(실패는 알림)
  const g = gt(), epoch = state.epoch;
  if (!gatherMine() || g.planBusy || g.applyBusy) return null;
  g.planBusy = pid;
  gatherDraw();
  let P = null;
  try {
    await flushAll(); // 고치던 글을 먼저 서버에 — 계획은 서버의 문서로 센다
    P = await gatherCall(`${gatherSeg(pid)}/plan`, "POST");
    if (epoch !== state.epoch || g !== gatherState) return null;
    g.plans[pid] = P;
    delete g.done[pid];
  } catch (e) { toast(`넣기 계획을 세우지 못했습니다: ${gatherErr(e)}`, true); }
  finally { if (g === gatherState) { g.planBusy = ""; gatherDraw(); } }
  if (P && show && g === gatherState) gatherFillList(pid);
  return P;
}
async function gatherApplyCall(pid, planId) { // 반영 한 번 — 문서를 다시 읽는다. 넣을 것이 없으면 null · 실패는 던진다(409 = 계획 뒤 바뀜 · 422 = 표준 검사)
  const doc = gatherPlan().id; // 반영할 취합본을 먼저 붙든다 — 기다리는 사이 다른 문서를 열어도 그 문서의 취합본에 보내거나 그 화면에 얹지 않는다(astra 11-16: gatherUrl 은 「지금 화면의 취합본」 을 따라간다)
  await flushAll();
  if (state.id !== doc) throw new Error("다른 문서를 열어 반영하지 않았습니다");
  const r = await api(`/api/docs/${doc}/gather${gatherSeg(pid)}/apply`, { method: "POST", headers: H_JSON, body: JSON.stringify({ planId }) });
  if (r.nothing) return null;
  if (state.id !== doc) throw new Error("반영하는 사이 다른 문서를 열었습니다 — 취합본에는 반영됐습니다(그 문서를 다시 열면 보입니다)");
  applyEditState(r);
  await reloadDoc(); // 떨어진 자리 여러 곳이 바뀌어 문서를 다시 읽는다(구분 기준 반영과 같은 길)
  return r;
}
async function gatherApply(pid) { // 「반영」 — 반영(2026-11-18 부터 확인 창 없이) → 결과(다시 계산 필요가 있으면 2열에 남긴다)
  const g = gt(), P = g.plans[pid], p = gatherPart(pid), epoch = state.epoch;
  if (!P || !P.todo || !p || g.applyBusy || !gatherMine()) return;
  // 확인 창 없이 바로 넣는다(2026-11-18 사용자 「이런 알람좀 주지마」 — 실행 취소 한 번으로 되돌림: design.md §18 「확인 창」)
  g.applyBusy = pid;
  state.busy = true;
  refreshToolbar();
  gatherDraw();
  try {
    const r = await gatherApplyCall(pid, P.planId);
    if (epoch !== state.epoch || g !== gatherState) return;
    delete g.plans[pid];
    delete g.links[pid]; // 넣은 자리는 이제 「이미 들어 있음」 — 다시 읽는다
    if (!r) toast("넣을 것이 없습니다");
    else { g.done[pid] = r; toast(`반영 — ${gatherDoneText(r)}`); }
    if (r && gatherCalcNeed(r.calc).length) gatherFillList(pid); // 다시 계산 필요 — 옛 수를 새 취합 결과처럼 보이지 않게 목록으로 남긴다
    else if (heads.dlg === "gatherFill") headsColClose();
    gatherLoad();
  } catch (e) {
    if (g === gatherState && e.status === 409) delete g.plans[pid]; // 계획 뒤 문서·설정이 바뀜 — 계획을 버린다
    toast(e.status === 422 ? `표준 검사에 걸려 되돌렸습니다: ${e.message}` : e.status === 409 ? `계획을 세운 뒤 문서가 바뀌었습니다 — 넣기 계획을 다시 세우세요(${gatherErr(e)})` : `반영하지 못했습니다: ${gatherErr(e)}`, true);
  } finally {
    state.busy = false;
    refreshToolbar();
    if (g === gatherState) { g.applyBusy = ""; gatherDraw(); }
  }
}

function gatherFillList(pid, keep = false) { // 2열 「넣기 계획」(kind "gatherFill") — 넣을 것 목록 + 안 넣는 것의 상태별 수 + 못 옮기는 개체 + 「다시 계산 필요」 · 꼬리말 「반영」. 반영 뒤에는 결과(다시 계산 필요)
  const g = gt(), p = gatherPart(pid), P = g.plans[pid], R = g.done[pid], plan = gatherPlan();
  if (!p || !(P || R) || !plan) { if (heads.dlg === "gatherFill") headsColClose(); else toast("넣기 계획이 아직 없습니다"); return; }
  g.fillPart = pid;
  const top = keep ? $("headsDlgBody").scrollTop : 0, busy = g.applyBusy === pid || g.planBusy === pid;
  if (keep) heads.keepFold = true;
  const { tools, body, foot } = headsDlg("gatherFill", P ? `넣기 계획 — ${p.name}` : `반영 결과 — ${p.name}`, `${p.name} → ${plan.name} · ` + (P ? "문서는 「반영」 을 눌러야 바뀝니다" : "넣은 뒤 확인할 것"));
  heads.keepFold = false;
  tools.append(el("span", "muted", P ? gatherPlanText(P) : gatherDoneText(R)));
  const X = P || R, cap = (t) => el("div", "lk-cap", t);
  if (P) {
    const [tbl, tb] = hTable(["넣을 자리", "넣을 것", "내용"]);
    tbl.classList.add("lk-table", "gt-table");
    for (const it of P.items || []) {
      const tr = el("tr", "go"), [place, who, full] = gatherPlace(it), tdp = el("td", "lk-place");
      tr.tabIndex = 0;
      tr.dataset.hunk = it.key || "";
      tdp.append(el("div", "lk-to", place), el("div", "lk-from", who));
      tdp.title = full;
      tr.append(tdp);
      const what = hCell(tr, [GT_KIND[it.kind] || it.kind || "", gatherNums(it.counts, ["paragraphs", "tables", "pictures", "cells", "rows", "placeholders", "converted", "kept", "over"])].filter(Boolean).join(" — "), "gt-what");
      const cv = it.convert; // 틀 맞춤 — 개요 깊이·레터 꼴이 취합본 틀과 달라 맞출 줄(원래 레터 → 맞춘 레터)과 쓴 대로 둘 줄의 까닭을 도움말로
      if (cv && (cv.converted || Object.keys(cv.kept || {}).length)) what.title = [...(cv.rows || []).map((r) => `틀 맞춤: 「${r.was || ""}」 → 「${r.letter || ""}」`), ...Object.entries(cv.kept || {}).map(([k, n]) => `쓴 대로 둠 ${n}줄 — ${(cv.labels || {})[k] || k}`)].join("\n");
      hCell(tr, oneLine(it.text || "") || "(글 없음)", "gt-text");
      tr.onclick = () => gatherGo(pid, it);
      tr.onkeydown = (e) => { if (e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); gatherGo(pid, it); } };
      tb.append(tr);
    }
    if (!(P.items || []).length) { const tr = el("tr"), td = hCell(tr, "넣을 것이 없습니다"); td.colSpan = 3; tb.append(tr); }
    body.append(cap(`넣을 것 — ${nf((P.items || []).length)}곳`), tbl);
    const overEl = typeof mergeOverSection === "function" ? mergeOverSection({ docId: plan.id, over: P.over, disabled: busy || !!gatherRun || !gatherMine(), go: (c) => { if (c.at) gatherJump(c.at); }, // 넘친 개요 레벨(spec_병합 ② §5-5 — merge_over.js): 처리를 고르면 계획을 다시 센다
      onChange: async () => { await gatherPlanMake(pid, { show: false }); if (gt().plans[pid] && heads.dlg === "gatherFill") gatherFillList(pid, true); } }) : null;
    if (overEl) body.append(overEl);
    const skipped = Object.entries(P.skipped || {}).filter(([, n]) => n);
    const sk = el("p", "hnote gt-skipped", skipped.length ? "" : "넣지 않는 내용이 없습니다");
    for (const [k, n] of skipped) { const s = el("span", `dv-badge ${GT_BADGE[k] || ""}`, `${GT_STATUS[k] || (k === "skip" ? "뺌" : k === "check" ? "보류(확인 필요)" : k)} ${nf(n)}`); s.title = GT_STATUS_HELP[k] || ""; s.dataset.status = k; sk.append(s, " "); }
    body.append(cap("넣지 않는 것 — 상태별 수(「기관 작성 내용」 에서 줄마다 봅니다)"), sk);
  }
  if ((X.dropped || []).length) { const ul = el("ul", "gt-ul"); for (const t of gatherDropped(X.dropped)) ul.append(el("li", null, t)); body.append(cap(`옮기지 못하는 개체 — ${X.dropped.length}`), ul); }
  if ((X.calc || []).length) { // 계산 칸 — 기관 문서의 값은 복사하지 않는다(기관의 합계는 취합본의 합계가 아니다). 더하는 칸이 바뀐 단순 합은 반영 때 다시 계산해 넣고, 그 밖은 「다시 계산 필요」
    const ul = el("ul", "gt-ul gt-calc"), need = gatherCalcNeed(X.calc), rows = P ? X.calc : [...need, ...X.calc.filter((c) => !need.includes(c))]; // 반영 결과는 「다시 계산 필요」 가 앞
    for (const c of rows) {
      const id = c.cell || c.table, li = el("li", id ? "go" : null, gatherCalcText(c));
      li.dataset.calc = c.action || c.why || "";
      if (id) { li.tabIndex = 0; li.onclick = () => gatherJump(id); li.onkeydown = (e) => { if (e.key === "Enter") gatherJump(id); }; }
      ul.append(li);
    }
    body.append(cap(P ? `계산 칸 — ${X.calc.length}칸(기관 문서의 값은 복사하지 않습니다 · 더하는 칸이 바뀌는 합은 반영 때 다시 계산하고, 못 하는 칸은 「다시 계산 필요」 로 남깁니다)`
      : `다시 계산 필요 — ${need.length}칸${X.calc.length > need.length ? ` · 다시 계산해 넣음 ${X.calc.length - need.length}칸` : ""}(합계·소계·비율을 확인하세요 — 옛 수가 남아 있을 수 있습니다)`), ul);
  }
  $("headsDlgBody").scrollTop = top;
  if (P) foot.append(el("span", "muted", P.todo ? "실행 취소 한 번으로 되돌릴 수 있습니다" : "넣을 것이 없습니다"),
    hBtn(g.applyBusy === pid ? "반영 중…" : "반영", () => gatherApply(pid), { cls: "btn sm primary", disabled: !P.todo || busy || !!gatherRun || !gatherMine(), title: "이 계획대로 취합본에 넣습니다 — 기관 문서는 안 바뀝니다" }));
  foot.append(hBtn("닫기", () => headsColClose()));
}

// ---- 화면의 셈(gatherSteps)에 없는 조립 도구의 줄 — 서버만 아는 줄(dashboard.js DASH_GATHER_SERVER: 「넣은 뒤 템플릿 · 서식 정리」 retidy — spec_병합 ② §5-9 9). 취합형으로 조립한 것만(붙박이 취합의 차례에는 없다).
// 그 줄이 화면의 묶음과 같은 정의 묶음에 남았으면 그 묶음은 끝나지 않았다 — 「한 번에 진행」 · 간단 모드(이어서) · 에이전트가 화면의 줄만 보고 「남은 단계가 없습니다」 로 끝내지 않는다(검토에서 찾음 2026-11-22)
async function gatherServerView(plan) { // → 서버가 센 상태(GET …/flow — 대시보드와 같은 값) | null(조립한 취합이 아님 · 그 줄이 정의에 없음 · 못 읽음)
  const c = TASK_CATALOG[(state.task && state.task.job) || ""] || {};
  if (!c.custom || !plan || typeof flowGet !== "function" || typeof DASH_GATHER_SERVER === "undefined" || !Object.keys(c.unitAt || {}).some((u) => DASH_GATHER_SERVER.has(u))) return null;
  try { return await flowGet(plan.id); } catch { return null; }
}
function gatherServerRest(stageId, V) { // 화면의 묶음 → {gid 정의 묶음, steps[그 묶음의 서버만 아는 줄 — 서버 상태의 줄 그대로], left[그 가운데 안 끝난 줄]} | null
  // 정의 묶음 = 대시보드의 묶음 단추와 같은 묶음(task_catalog.js gatherDefStage). 화면의 묶음 여럿이 한 정의 묶음에 들면 마지막 화면 묶음의 몫이다(그 줄은 내용 반영 뒤 — 앞 화면 묶음의 실행이 그 묶음의 옵션 없이 뒤 줄까지 돌지 않게)
  const job = (state.task && state.task.job) || "", gid = V ? gatherDefStage(stageId, job) : "";
  if (!gid || GT_STAGES.filter((x) => gatherDefStage(x.id, job) === gid).pop().id !== stageId) return null;
  const row = (V.stages || []).find((g) => g.id === gid), steps = row ? (row.steps || []).filter((s) => DASH_GATHER_SERVER.has(s.key)) : [];
  return steps.length ? { gid, steps, left: steps.filter((s) => !s.done) } : null;
}

// ---- 한 번에 진행(spec_취합 ② §4-4 · §5 — 이관의 taskRunAll 과 같은 약속: 확인 창 없이(2026-11-18), 사람 손이 필요한 곳·실패에서 멈춤, 멈추면 세부 목록을 편다)
async function gatherRunAll(stageId) {
  if (gatherRun) return;
  const stage = GT_STAGES.find((x) => x.id === stageId), plan = gatherPlan();
  if (!stage || !plan) { toast("사업계획서(취합본)를 먼저 고르세요", true); return; }
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 묶음마다 할 일 · 기관 문서 차례를 적은 확인 창: design.md §18 「확인 창」) — 사람 손이 필요한 곳 · 실패에서 멈추는 것은 그대로.
  // 남은 일은 gatherRunStage 가 센다(화면의 줄 + 같은 정의 묶음에 남은 서버만 아는 줄 — gatherServerRest)
  const r = await gatherRunStage(stage.id, plan);
  if (r && r.none) toast("남은 단계가 없습니다");
}
// 묶음 하나를 확인 없이 끝까지(「한 번에 진행」 의 몸통 — 간단 모드 gather_quick.js 도 부른다: spec_취합 ② §8-2) → {ok, text, none?}. 남은 단계가 없으면 돌지 않는다(none).
// opt: config — (값이 없으면 늘 문서에서 읽음) / frame — quick(구조 맞춤에 지움이 있으면 멈춤) / map — auto(Set: 미지정이면 자동 지정할 기관 문서) · llm(false = LLM 검토 안 함) · log({기관 문서 id: 결과}) / quiet(끝 알림 없음)
async function gatherRunStage(stageId, plan, opt = {}) {
  const stage = GT_STAGES.find((x) => x.id === stageId);
  if (gatherRun || gatherRunStarting) return { ok: false, text: "다른 묶음이 진행 중입니다" };
  const left = gatherCalc().filter((s) => s.stage === stageId && !s.done && s.step !== "files"), none = { ok: true, text: "남은 단계가 없습니다", none: true };
  if (!stage || !plan) return none;
  // 서버 쪽 실행기가 이 묶음을 맡으면 서버가 돈다(workflow_exec.js gatherRunServer — 창을 닫거나 다른 문서를 열어도 끝까지: spec_워크플로우 ② §18-13 갈래 「라」) — 맡지 않으면(null · 옛 서버 · 끄는 스위치) 아래 화면 실행 그대로
  if (typeof gatherRunServer === "function") {
    gatherRunStarting = true; // 시작 요청(과 서버 상태 읽기)을 기다리는 동안 겹쳐 누르지 못하게
    let via = null;
    try {
      // 화면의 줄이 다 끝나도 같은 정의 묶음에 서버만 아는 줄(넣은 뒤 정리)이 남았으면 그 정의 묶음째 서버로 돈다 — 끝난 줄 · 넣을 것이 없는 기관 문서는 서버가 건너뛰고,
      // 묶음째 실행이라 끝나면 고친 문단을 확정한다(그 줄 하나 only 로 돌면 끝 확정이 없다: spec_병합 ② §5-9 9 ⓒ · spec_워크플로우 ② §18-24) · 멈춘 정리도 「간단 모드 이어서」 가 다시 한다
      const R = left.length ? null : gatherServerRest(stageId, await gatherServerView(plan)), rest = R && R.left.length ? R : null;
      if (left.length || rest) via = await gatherRunServer(stage, plan, rest ? { ...opt, from: rest.gid } : opt, rest ? rest.left[0].key : left[0].key);
    } finally { gatherRunStarting = false; }
    if (via) return via;
  }
  if (!left.length) return none; // 화면 실행은 서버만 아는 줄을 모른다
  const run = (gatherRun = { stage: stage.id, plan: plan.id, key: left[0].key, note: "", t0: Date.now(), stop: false });
  gatherRunLast = null;
  if (typeof projectControlsSync === "function") projectControlsSync(); // 도는 동안 프로젝트 칸·라운드·구분 기준 버전 줄을 끈다(spec_작업 ② §19)
  run.timer = setInterval(() => gatherStageSync(), 1000); // 지난 시간 — 글만 바꾼다
  gatherStageSync();
  let end;
  try { end = { ok: true, text: await (stage.id === "config" ? gatherRunConfig(run, plan, opt) : stage.id === "frame" ? gatherRunFrame(run, plan, opt) : gatherRunMap(run, plan, opt)) }; }
  catch (e) { end = { ok: false, text: e instanceof GatherHalt ? e.message : `오류 — ${gatherErr(e)}` }; if (!(e instanceof GatherHalt)) console.warn(e); }
  clearInterval(run.timer);
  return gatherRunEnd(stage, plan, run, end, opt);
}
let gatherRunStarting = false; // 서버 쪽 실행의 시작 요청을 기다리는 중(gatherRunStage)
function gatherRunEnd(stage, plan, run, end, opt = {}) { // 묶음 실행의 끝 — 상태 줄에 끝 글을 남기고 · 멈춘 곳을 펴고 · 알린다(화면 실행과 서버 실행의 거울 workflow_exec.js gatherRunFollow 가 같이 쓴다) → end
  if (gatherRun === run) gatherRun = null;
  if (typeof projectControlsSync === "function") projectControlsSync(); // 끝났다 — 꺼 둔 프로젝트 칸·버전 줄을 다시 켠다
  gatherDraw();
  gatherRunLast = { ...end, stage: stage.id, plan: plan.id, key: run.key, done: (gatherStepsLast || []).filter((s) => s.stage === stage.id && s.step !== "files" && s.done).length };
  const box = document.getElementById(stage.dom);
  if (box && !end.ok) box.open = true; // 멈춘 곳이 보이게 세부 목록을 편다
  gatherStageSync();
  if (!opt.quiet) toast(end.ok ? `${stage.name} — ${end.text}` : `${stage.name}이 멈췄습니다 — ${end.text}`, !end.ok);
  return end;
}
function gatherRunAt(run, plan) { // 일 하나를 시작하기 전 — 멈춤 요청·문서 바뀜을 보고 상태 줄을 바꾼다
  return (key, note) => {
    if (run.stop) gatherHalt("눌러서 멈췄습니다 — 끝난 것은 그대로입니다");
    if (key !== "open" && state.id !== plan.id) gatherHalt("다른 문서를 열어 멈췄습니다");
    const now = gatherPlan();
    if (!now || now.id !== plan.id) gatherHalt("도는 중에 사업계획서(취합본) 칸의 문서가 바뀌어 멈췄습니다 — 다시 누르세요");
    if (key !== "open") run.key = key;
    run.note = note;
    gatherStageSync();
  };
}
async function gatherRunConfig(run, plan) { // 1단계 「구분 기준」 — 값이 없으면 취합본에 적힌 단계·차년도·기관을 읽어 입력 칸에 → 확정(프로젝트에 저장). 문서는 안 바뀐다(spec_작업 ② §18)
  const at = gatherRunAt(run, plan), step = (key) => gatherCalc().find((s) => s.key === key);
  at("open", "취합본 여는 중");
  if (!(await gatherToPlan())) gatherHalt("취합본을 열지 못했습니다(고치던 글을 두고 그만뒀거나 열리지 않음)");
  let read = false;
  if (!(gatherDiv() || {}).values) { // 값이 없음 — 문서에 적힌 단계·차년도·기관(② §8-4 「값이 없으면 문서에서 읽는다」)
    at("config", "취합본에서 단계·차년도·기관 읽기");
    let got = null;
    try { got = taskReadValues((await api(`/api/docs/${plan.id}/divisions/read`)).read); } catch (e) { console.warn(e); }
    if (!got) gatherHalt("취합본에서 단계·차년도·기관을 읽지 못했습니다 — 1단계의 프로젝트 구성 입력 칸에 넣거나 「프로젝트 구성 불러오기」 로 불러온 뒤 다시 하세요");
    if (state.id !== plan.id) gatherHalt("다른 문서를 열어 멈췄습니다");
    dv.values = structuredClone(got);
    divTouched();
    read = true;
  }
  if (!step("config").done) {
    at("config", "프로젝트에 저장(확정)");
    if (!(await divConfirm({ quiet: true }))) gatherHalt("프로젝트 구성을 확정하지 못했습니다(알림 글 참고)");
    if (state.id !== plan.id) gatherHalt("다른 문서를 열어 멈췄습니다");
    if (!step("config").done) gatherHalt("프로젝트 구성이 확정되지 않았습니다");
  }
  const d = gatherDiv();
  return `${read ? "취합본에서 읽은 " : ""}프로젝트 구성을 ${divConfirmWhere(d && d.sharing)}에 확정했습니다 — ${divValuesText(d.values)} · 구조는 2단계 「문서 프레임 작성」 에서 맞춥니다`;
}
async function gatherRunFrame(run, plan, opt = {}) { // 2단계 — ① 구조 확인 또는 구분 기준 반영(구조만 — 편집 하나) → 배포 기준본. 내용은 넣지 않는다. 값은 1단계에서 확정한 것
  const at = gatherRunAt(run, plan), step = (key) => gatherCalc().find((s) => s.key === key);
  at("open", "취합본 여는 중");
  if (!(await gatherToPlan())) gatherHalt("취합본을 열지 못했습니다(고치던 글을 두고 그만뒀거나 열리지 않음)");
  if (!step("config").done) gatherHalt(`${TASK_STAGE_META.config.no} 「${TASK_STAGE_META.config.name}」 이 먼저입니다 — 프로젝트 구성(단계·차년도·기관)을 확정한 뒤 다시 누르세요`);
  const d0 = gatherDiv();
  if (!step("division").done && d0 && d0.values && !d0.applied && d0.ok !== false) { // 한 번도 반영한 적 없는 문서 — 구조가 이미 값에 맞으면 「반영됨」 으로 적는다(구조 확인 — ② §3 · §8-4). 안 맞으면 아래 변경 계획 → 반영
    at("division", "구조 확인(이미 값에 맞는지)");
    await flushAll();
    await divSettingsFlush();
    try { await api(`/api/docs/${plan.id}/divisions/adopt`, { method: "POST", headers: H_JSON, body: "{}" }); } catch (e) { console.warn("구조 확인:", e.message); }
    if (state.id !== plan.id) gatherHalt("다른 문서를 열어 멈췄습니다");
    await divShow();
  }
  if (!step("division").done) {
    at("division", "변경 계획");
    if (dv.view && !dv.view.profile.supported) gatherHalt("이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다");
    if (!(await divPlan()) || !dv.plan) gatherHalt("프로젝트 구성 변경 계획을 세우지 못했습니다(알림 글 참고)"); // divPlan 의 반환값을 본다 — 못 세워도 전의 계획이 dv.plan 에 남아 있을 수 있다
    const stops = divAutoStops(); // 양식 맞추기의 「한 번에 진행」 과 같은 검사(app.js — 계획 오류 · 미해결 · 기관 차례): 사람이 봐야 할 계획은 저절로 반영하지 않는다
    if (stops) gatherHalt(`${stops} — 저절로 반영하지 않습니다. ${TASK_STAGE_META.frame.no}의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요`);
    const gone = ((dv.plan.summary || {}).removed || 0) + ((dv.plan.summary || {}).deleted || 0);
    if (opt.quick && gone) gatherHalt(`구조를 값에 맞추려면 ${nf(gone)}곳을 지워야 합니다 — 자동으로 지우지 않습니다. ${TASK_STAGE_META.frame.no}의 변경 계획을 확인하고 반영한 뒤 「이어서」 를 누르세요(문서에서 읽은 값이 틀리면 절이 지워집니다)`);
    at("division", "취합본에 반영");
    await divApply({ quiet: true });
    await divShow();
    const s = step("division");
    if (!s.done) gatherHalt(`프로젝트 구성이 반영되지 않았습니다 — ${s.lines.length ? s.lines[0][1] : "알림 글 참고"}`);
  }
  if (!step("frame").done) {
    at("frame", "기준본 만들기");
    const g = gt();
    let R;
    try { R = await gatherFramePost((t) => at("frame", t), () => gatherRun === run && !run.stop && state.id === plan.id); }
    catch (e) { if (e instanceof GatherHalt) throw e; gatherHalt(`기준본을 만들지 못했습니다 — ${gatherErr(e)}`); }
    if (g !== gatherState) gatherHalt("다른 문서를 열어 멈췄습니다");
    gatherViewSet(R, true);
    gatherDraw();
    if (!step("frame").done) gatherHalt("기준본이 만들어지지 않았습니다");
  }
  return `구조를 맞추고 배포 기준본을 만들었습니다 — 「기준본 내려받기」 로 받아 기관에 나눠 주세요 · 내용은 ${TASK_STAGE_META.map.no} 「${TASK_STAGE_META.map.name}」 에서 넣습니다`;
}
async function gatherRunMap(run, plan, opt = {}) { // 3단계 — 들어온 차례로, 넣을 것이 남고 반영할 기관이 정해진 문서마다 자리 연결 → (LLM 검토) → 넣기 계획 → 반영. 반영한 뒤의 취합본으로 다음 문서를 계획한다
  const at = gatherRunAt(run, plan), log = (pid, x) => { if (opt.log) opt.log[pid] = { ...(opt.log[pid] || {}), ...x }; }; // 간단 모드의 문서별 결과(② §8-6)
  at("open", "취합본 여는 중");
  if (!(await gatherToPlan())) gatherHalt("취합본을 열지 못했습니다(고치던 글을 두고 그만뒀거나 열리지 않음)");
  const view = () => { const V = gt().view; if (!V) gatherHalt(`취합 상태를 읽지 못했습니다${gt().err ? `: ${gt().err}` : ""}`); return V; };
  if (gatherCalc().some((s) => (s.stage === "config" || s.stage === "frame") && s.step !== "files" && !s.done)) gatherHalt(`${TASK_STAGE_META.frame.no} 「${TASK_STAGE_META.frame.name}」 이 먼저입니다(프로젝트 구성 추출 · 프로젝트 구성 반영 · 배포 기준본)`);
  const order = view().parts.map((p) => p.work), unassigned = [], blocked = [], done = [], notes = [], sum = {};
  const link = async (pid, p, key, method) => { // 자리 연결 → L | false(저절로 넣을 수 없는 문서 — 건너뜀) | null(응답을 버림 — 문서가 바뀜). 기관 문서의 분석이 없으면 한 번 걸고 다시
    for (let tries = 0; ; tries++) {
      try { return await gatherLinks(pid, method); }
      catch (e) {
        const why = gatherWhy(e);
        if (e.status === 409 && why.includes("noHeadings") && !tries) { at(key, "헤딩·표 분석(스크립트)"); await gatherAnalyze(pid, { first: true }, () => gatherRun === run && !run.stop); at(key, "자리 연결(기준본과 견주기)"); method = "POST"; continue; }
        if (e.status === 409 && (why.includes("noMatch") || why.includes("frameDiffers"))) { blocked.push(`${p.name}(${gatherReasons(why)})`); log(pid, { skip: `${gatherReasons(why)} — 끌어 넣기로` }); return false; } // 저절로 넣을 수 없는 문서 — 끌어 넣기로. 다른 문서는 이어 간다
        gatherHalt(`「${p.name}」 의 자리 연결을 하지 못했습니다 — ${gatherErr(e)}`);
      }
    }
  };
  for (const pid of order) {
    let p = gatherPart(pid), method = "POST";
    const key = `part:${pid}`;
    if (!p) continue; // 도는 중에 뺀 문서
    if (!(p.orgs || []).length && opt.auto && opt.auto.has(pid)) { // 간단 모드 — 자리 연결 뒤 반영할 기관을 정한다(파일 이름 → 추천: ② §8-3). 사람이 고른 문서는 안 건드린다(서버도 막는다)
      at(key, "자리 연결(기준본과 견주기)");
      const L0 = await link(pid, p, key, "POST");
      if (L0 === false) continue;
      if (!L0) gatherHalt("다른 문서를 열어 멈췄습니다");
      at(key, "반영할 기관 정하기(파일 이름 → 추천)");
      let A;
      try { A = await gatherCall(`${gatherSeg(pid)}/auto`, "POST"); }
      catch (e) { gatherHalt(`「${p.name}」 의 반영할 기관을 정하지 못했습니다 — ${gatherErr(e)}`); }
      if (gt().epoch !== state.epoch || state.id !== plan.id) gatherHalt("다른 문서를 열어 멈췄습니다");
      gatherViewSet(A);
      delete gt().links[pid];
      gatherDraw();
      p = gatherPart(pid) || p;
      log(pid, { org: A.auto.org, by: A.auto.by, why: A.auto.why });
      method = "GET"; // 방금 맞췄다 — 판정만 새로(반영할 기관이 바뀌었다)
    }
    if (!(p.orgs || []).length) { unassigned.push(p.name); log(pid, { skip: "반영할 기관을 정하지 못함" }); continue; } // 반영할 기관 미지정 — 건너뛰고 알린다
    if (method === "POST" && gatherPartTodo(p) === 0 && p.counts && !gatherHard(p.reasons).length) continue; // 넣을 것이 안 남음(자리를 충분히 확인하지 못한 문서는 사람이 「넣음」 으로 고른 것이 있을 때만 진행)
    at(key, "자리 연결(기준본과 견주기)");
    let L = await link(pid, p, key, method);
    if (L === false) continue;
    if (!L) gatherHalt("다른 문서를 열어 멈췄습니다"); // 응답을 버렸다(문서가 바뀜)
    if (!gatherTodo(L)) continue; // 넣을 수 있는 것이 없다(겹침·확인 필요만 남음)
    if (!L.llm && opt.llm === false) notes.push(`「${p.name}」 LLM 검토는 끔`);
    else if (!L.llm) { // 아직 검토 전일 때만 한 번(유료) — 실패해도 멈추지 않는다(스크립트가 넣을 수 있다고 본 것만 넣는다)
      at(key, `LLM 검토 — 넣을 수 있음 ${nf((L.counts || {}).ready || 0)}곳(수십 초)`);
      gt().llmBusy = pid;
      try { L = (await gatherLinks(pid, "POST", "/llm")) || L; }
      catch (e) { notes.push(`「${p.name}」 LLM 검토는 못 함`); log(pid, { llm: "LLM 검토 못 함" }); }
      finally { gt().llmBusy = ""; }
      if (!gatherTodo(L)) continue;
    }
    for (let tries = 0; ; tries++) { // 계획 뒤 곧바로 반영 — 사이에 문서가 바뀌면 409: 계획을 한 번만 다시
      at(key, "넣기 계획");
      let P;
      try { await flushAll(); P = await gatherCall(`${gatherSeg(pid)}/plan`, "POST"); }
      catch (e) { gatherHalt(`「${p.name}」 의 넣기 계획을 세우지 못했습니다 — ${gatherErr(e)}`); }
      if (gt().epoch !== state.epoch || state.id !== plan.id) gatherHalt("다른 문서를 열어 멈췄습니다");
      gt().plans[pid] = P;
      if (!P.todo) { delete gt().plans[pid]; break; } // 실패가 아니다 — 이미 넣은 문서
      at(key, "내용 반영");
      gt().applyBusy = pid;
      state.busy = true;
      refreshToolbar();
      let r;
      try { r = await gatherApplyCall(pid, P.planId); }
      catch (e) {
        delete gt().plans[pid];
        if (e.status === 409 && !tries) continue; // 계획 뒤 문서가 바뀜 → 한 번만 다시 계획
        gatherHalt(e.status === 422 ? `「${p.name}」 — 표준 검사에 걸려 되돌렸습니다: ${e.message}` : `「${p.name}」 의 내용을 반영하지 못했습니다 — ${gatherErr(e)}`);
      } finally { gt().applyBusy = ""; state.busy = false; refreshToolbar(); }
      delete gt().plans[pid];
      delete gt().links[pid];
      if (r) { gt().done[pid] = r; done.push(p.name); log(pid, { done: gatherDoneText(r) }); for (const [k, n] of Object.entries(r.counts || {})) if (typeof n === "number") sum[k] = (sum[k] || 0) + n; sum.calc = (sum.calc || 0) + gatherCalcNeed(r.calc).length; }
      break;
    }
    at(key, "취합 상태 다시 읽기");
    await gatherLoad(); // 다음 문서는 반영한 뒤의 취합본으로 계획한다
    view();
  }
  if (heads.dlg === "gatherFill") headsColClose();
  const counts = gatherDoneText({ counts: sum }), tail = [unassigned.length ? `반영할 기관 미지정 ${unassigned.length}개는 건너뜀(${unassigned.join(" · ")})` : "", blocked.length ? `저절로 넣지 못한 문서 ${blocked.length}개(${blocked.join(" · ")} — 끌어 넣기로)` : "",
    sum.calc ? `다시 계산 필요 ${sum.calc}칸` : "", ...notes].filter(Boolean).join(" · ");
  return (done.length ? `기관 문서 ${done.length}개 반영 — ${counts}` : "넣을 것이 없습니다(이미 넣었거나 넣을 수 있는 자리가 없음)") + (tail ? ` · ${tail}` : "");
}

// ---- 둘째 면(spec_취합 ② §5 「둘째 면」) — 취합본은 늘 왼쪽(고치는 문서), 기관 문서들은 오른쪽 탭(들어온 차례). 탭의 문서 = 그 취합에 든 기관 문서뿐
function gatherPeerDocs() { // app.js peerDocs 가 부른다 → 둘째 면에 띄울 문서(탭 차례). 기관 문서를 열어 보는 중이면 취합본이 맨 앞(왼쪽에 뜬다 — gatherPeerLeft)
  const plan = gatherPlan(), V = gt().view, out = [];
  const add = (id, name, file) => { if (id && id !== state.id && !out.some((w) => w.id === id)) out.push(worksList.find((w) => w.id === id) || { id, name, task: { file } }); };
  if (!plan) return out;
  if (plan.id !== state.id) add(plan.id, plan.name, gatherSpec().base);
  for (const p of (V && V.parts) || []) add(p.work, p.name, gatherSpec().parts);
  return out;
}
function gatherPeerLabel(w) { // app.js peerLabel 이 부른다 → 둘째 면 탭 글 = 기관 문서의 반영할 기관 이름(2026-11-13 사용자 "여기 상단에는 반영할 기관 이름으로"). 기관 문서가 아니거나 미지정이면 "" — 파일 이름 그대로
  const p = gatherPart(w.id), V = gt().view, all = (V && V.orgs) || [], cur = (p && p.orgs) || [];
  if (!cur.length) return "";
  if (all.length > 1 && cur.length === all.length && all.every((o) => cur.includes(o.key))) return "모든 기관";
  const names = cur.map((k) => (all.find((o) => o.key === k) || {}).name || k);
  return names.length > 2 ? `${names[0]} 외 ${names.length - 1}곳` : names.join(" · ");
}
function gatherPeerLeft() { const plan = gatherPlan(); return !!plan && plan.id !== state.id && peerShown() === plan.id; } // 둘째 면이 왼쪽 = 떠 있는 문서가 취합본일 때(취합본은 늘 왼쪽)
let gatherPeerWas = "";
function gatherPeerMark() { // app.js peerSync 끝 — 같이 보기 단추의 눌림 · 둘째 면의 문서가 바뀌었으면 끌던 것을 걷는다
  for (const b of document.querySelectorAll("[data-gather-peer]")) gatherPeerBtnSync(b);
  const now = peerShown();
  if (now !== gatherPeerWas) { gatherPeerWas = now; gatherDragCancel(); }
}

// ---- 끌어 넣기(spec_취합 ② §4-6) — 둘째 면(기관 문서)의 제목 줄 손잡이(⋮⋮)를 끌어 취합본의 본문 블록 위에 놓는다 → 계획(2열) → 「반영」. 바로 넣지 않는다.
// 둘째 면 화면(PEEK)은 자료만 싣는다(GET 밖 요청은 안 보냄 — spec_작업 ② §12) — 요청은 이 창(바깥)이 보낸다.
function gatherDragIs(e) { const t = e && e.dataTransfer && e.dataTransfer.types; return !!t && Array.from(t).includes(GT_TYPE); } // 창의 파일 놓기(app.js bind)·같은 문서 안 개요 줄 옮기기와 가른다
function gatherPeekPart(id) { return !PEEK && gatherOn() && gatherMine() && !!gatherPart(id); } // 둘째 면 화면이 묻는다 — 바깥이 취합본을 고치는 중이고 그 문서가 이 취합의 기관 문서인가
function gatherGripStart(e, srcId) { // 둘째 면 화면에서: 손잡이의 dragstart(app.js outlineGrip) — 끌어 넣기 출발이면 전용 형식만 싣고 true(같은 문서 안 옮기기는 안 건다)
  let ok = false;
  try { ok = PEEK && parent !== window && parent.gatherPeekPart(state.id); } catch { /* 바깥이 준비 전 */ }
  if (!ok) return false;
  e.dataTransfer.setData(GT_TYPE, JSON.stringify({ from: state.id, srcId }));
  e.dataTransfer.effectAllowed = "copy";
  return true;
}
let gatherDropEl = null, gatherDropWhy = "";
function gatherDropMark(t) { // 놓을 줄(그 블록 아래의 선) — 표시는 그 블록 요소 하나에만(#doc·body 에 클래스를 달지 않는다 — design.md §8)
  const elx = t && t.id ? t.el : null, why = (t && t.why) || "";
  if (gatherDropEl !== elx) { if (gatherDropEl) gatherDropEl.classList.remove("gt-drop-after"); gatherDropEl = elx; if (elx) elx.classList.add("gt-drop-after"); }
  if (why && why !== gatherDropWhy) toast(why, true); // 놓을 수 없는 까닭은 들어설 때 한 번
  gatherDropWhy = why;
}
function gatherDragCancel() { gatherDropMark(null); } // 끌기가 끝남 · 둘째 면의 탭이 바뀜 · 둘째 면 화면을 다시 읽음
function gatherBlockEl(b) { // 최상위 블록의 화면 요소(표는 마지막 쪽 조각)
  if (b.type === "table") { const ts = [...document.querySelectorAll(`#doc table.tbl[data-tbl="${CSS.escape(b.id)}"]`)].filter((t) => !t.parentElement.closest("td")); return ts[ts.length - 1] || null; }
  return paraEl(b.id) || document.querySelector(`#doc [data-id="${CSS.escape(b.id)}"]`);
}
function gatherDropTarget(e) { // 놓을 자리 = 포인터 아래 본문 최상위 블록의 뒤(그 블록의 위 반쪽이면 앞 블록의 뒤). 표 칸 안은 안 됨 → {id, el} | {why} | null
  if (!gatherOn() || !gatherMine()) return { why: "취합본을 고치는 문서로 연 뒤에 놓을 수 있습니다" };
  const x = e.target && (e.target.nodeType === 1 ? e.target : e.target.parentElement);
  if (!x || !$("doc").contains(x)) return null;
  if (x.closest("td")) return { why: "표 칸 안에는 놓을 수 없습니다 — 표 밖의 문단 위에 놓으세요" };
  const at = (id) => state.blocks.findIndex((b) => b.id === id), SEL = "[data-id], table.tbl[data-tbl]";
  let node = x.closest(SEL), i = -1;
  while (node && (i = at(node.dataset.id || node.dataset.tbl)) < 0) node = node.parentElement && node.parentElement.closest(SEL); // 본문 최상위가 아니면(글상자 등) 그것을 품은 최상위 블록
  if (!node) { // 쪽의 빈 곳(문단 사이·여백) — 그 쪽에서 포인터에 가장 가까운 본문 문단
    const sheet = x.closest(".sheet");
    let best = Infinity;
    for (const q of sheet ? sheet.querySelectorAll(".para[data-id]") : []) {
      if (q.closest("td") || at(q.dataset.id) < 0) continue;
      const r = q.getBoundingClientRect(), dist = e.clientY < r.top ? r.top - e.clientY : e.clientY > r.bottom ? e.clientY - r.bottom : 0;
      if (dist < best) { best = dist; node = q; }
    }
    if (!node) return null;
    i = at(node.dataset.id);
  }
  const r = node.getBoundingClientRect(), k = e.clientY < r.top + r.height / 2 && i > 0 ? i - 1 : i, b = state.blocks[k];
  return { id: b.id, el: k === i ? node : gatherBlockEl(b) || node };
}
function gatherBindDrop() { // 이 창(바깥)의 문서에 놓기 — 전용 형식만 받는다
  const doc = $("doc");
  doc.addEventListener("dragover", (e) => {
    if (!gatherDragIs(e)) return;
    const t = gatherDropTarget(e);
    e.preventDefault();
    e.dataTransfer.dropEffect = t && t.id ? "copy" : "none";
    gatherDropMark(t);
  });
  doc.addEventListener("dragleave", (e) => { if (gatherDragIs(e) && !doc.contains(e.relatedTarget)) gatherDropMark(null); });
  doc.addEventListener("drop", (e) => {
    if (!gatherDragIs(e)) return;
    e.preventDefault();
    e.stopPropagation(); // 창의 파일 놓기로 넘어가지 않게
    const t = gatherDropTarget(e);
    let d = null;
    try { d = JSON.parse(e.dataTransfer.getData(GT_TYPE)); } catch { /* 자료 없음 */ }
    gatherDropWhy = "";
    gatherDropMark(null);
    if (!t || !t.id) { if (t && t.why) toast(t.why, true); return; }
    if (d && d.from && d.srcId) gatherDropPlan(d, t.id);
  });
  window.addEventListener("dragover", (e) => { if (gatherDragIs(e) && !doc.contains(e.target)) e.dataTransfer.dropEffect = "none"; }); // 문서 밖(패널·도구 줄)에는 못 놓는다 — 창의 파일 놓기가 받지 않게 둔 것(app.js bind)과 짝
  $("peerFrame").addEventListener("load", () => gatherDragCancel()); // 둘째 면 화면을 다시 읽으면 끌던 것은 없다
}
async function gatherDropPlan(d, afterId) { // 놓음 → 계획(POST …/gather/drop/plan {from, srcId, afterId} — 문서는 안 바뀜) → 2열 「끌어 넣기」
  const g = gt(), epoch = state.epoch;
  if (!gatherPart(d.from)) { toast("이 취합에 든 기관 문서에서만 끌어 넣을 수 있습니다", true); return; }
  let P;
  try { await flushAll(); P = await gatherCall("/drop/plan", "POST", { from: d.from, srcId: d.srcId, afterId }); }
  catch (e) { toast(`끌어 넣기 계획을 세우지 못했습니다: ${gatherErr(e)}`, true); return; }
  if (epoch !== state.epoch || g !== gatherState) return;
  g.drop = { plan: P, from: d.from, srcId: d.srcId, afterId, convert: true, busy: false }; // 틀 맞춤은 기본 켬
  gatherDropList();
}
function gatherDropList(keep = false) { // 2열 「끌어 넣기」(kind "gatherDrop") — 가져올 범위 · 수 · 놓을 자리 · 틀 맞춤(미리보기 수) · 못 옮기는 개체 · 꼬리말 「반영」
  const g = gt(), D = g.drop, p = D && gatherPart(D.from), plan = gatherPlan();
  if (!D || !plan) { if (heads.dlg === "gatherDrop") headsColClose(); return; }
  const P = D.plan, R = P.range || {}, C = P.convert || null, A = P.after || {}, O = P.owner || {}; // 서버의 계획: range{title, blocks, paragraphs, tables, pictures, lines, single} · after{id, text, given} · owner{id, text} · convert{converted, kept{까닭: n}, labels{까닭: 글}, rows, more} | null
  if (keep) heads.keepFold = true;
  const { body, foot } = headsDlg("gatherDrop", "끌어 넣기 — 넣기 전 확인", `${p ? p.name : "기관 문서"} → ${plan.name} · 문서는 「반영」 을 눌러야 바뀝니다`);
  heads.keepFold = false;
  const dl = el("dl", "gt-drop"), row = (name, node, go) => { const dt = el("dt", null, name), dd = el("dd"); dd.append(node); if (go) { dd.classList.add("go"); dd.tabIndex = 0; dd.onclick = go; dd.onkeydown = (e) => { if (e.key === "Enter") go(); }; } dl.append(dt, dd); return dd; };
  row("가져올 범위", `${oneLine(R.title || "") || "(제목 줄)"} — ${R.single ? "이 블록 하나만(절의 제목 줄이 아닙니다)" : "제목 줄과 그 아래 내용"}`, () => gatherPeerGo(D.from, D.srcId)).dataset.k = "range";
  row("넣을 것", gatherNums(R, ["blocks", "paragraphs", "tables", "pictures"]) || "—").dataset.k = "counts";
  row("놓을 자리", `「${oneLine(A.text || "") || "(빈 줄)"}」 뒤`, () => gatherJump(A.id || D.afterId)).dataset.k = "after"; // after.id = 그 뒤에 넣을 블록(표를 품은 문단 위에 놓았으면 그 표)
  const lab = el("label", "gt-convert"), cb = el("input"), kept = Object.entries((C && C.kept) || {}).filter(([k, n]) => k !== "cell" && n); // kept = {까닭: 줄 수}(cell = 복사한 표의 칸 안 개요 줄 — 줄 수에 안 넣는다)
  if (!C) D.convert = false; // 틀 맞춤을 할 수 없는 자리(놓은 자리를 품은 제목 줄이 없음) — 기관 문서 모양 그대로
  cb.type = "checkbox";
  cb.checked = D.convert;
  cb.disabled = D.busy || !C;
  cb.dataset.gatherConvert = "1";
  cb.onchange = () => { D.convert = cb.checked; };
  const keptN = kept.reduce((a, [, n]) => a + n, 0);
  lab.append(cb, el("span", null, !C ? "틀 맞춤 없음 — 놓은 자리를 품은 제목 줄이 없습니다(기관 문서 모양 그대로 넣습니다)"
    : `개요 줄을 취합본 틀에 맞춤 — 맞출 줄 ${nf(C.converted || 0)}${keptN ? ` · 그대로 두는 줄 ${nf(keptN)}` : ""}` + (O.text ? ` · 「${oneLine(O.text)}」 의 아래로` : "")));
  lab.title = "켜면 놓은 자리를 품은 제목 줄의 아래 단계로 개요 줄(레터·레벨)을 취합본 틀에 맞춥니다(받을 레벨이 없는 줄은 그대로). 끄면 기관 문서 모양 그대로 넣습니다";
  const dd = row("틀 맞춤", lab);
  dd.dataset.k = "convert";
  if (kept.length) { const ul = el("ul", "gt-ul"); for (const [k, n] of kept) ul.append(el("li", null, `${(C.labels || {})[k] || k} — ${nf(n)}줄`)); dd.append(ul); } // 그대로 두는 까닭별 줄 수
  if ((P.dropped || []).length) { const ul = el("ul", "gt-ul"); for (const t of gatherDropped(P.dropped)) ul.append(el("li", null, t)); row(`옮기지 못하는 개체 ${P.dropped.length}`, ul).dataset.k = "dropped"; }
  body.append(dl);
  const overEl = typeof mergeOverSection === "function" ? mergeOverSection({ docId: plan.id, over: P.over, disabled: D.busy || !gatherMine(), go: (c) => { if (c.at) gatherJump(c.at); }, // 넘친 개요 레벨(spec_병합 ② §5-5): 처리를 고르면 같은 자리로 계획을 다시 세운다(틀 맞춤 켬/끔은 그대로)
    onChange: async () => { const on = D.convert; await gatherDropPlan({ from: D.from, srcId: D.srcId }, D.afterId); const now = gt().drop; if (now && now !== D) { now.convert = on && !!now.plan.convert; if (heads.dlg === "gatherDrop") gatherDropList(true); } } }) : null;
  if (overEl) body.append(overEl);
  foot.append(el("span", "muted", "실행 취소 한 번으로 되돌릴 수 있습니다 · 기관 문서는 안 바뀝니다"),
    hBtn(D.busy ? "반영 중…" : "반영", () => gatherDropApply(), { cls: "btn sm primary", disabled: D.busy || !gatherMine(), title: "이 범위를 놓은 자리 뒤에 넣습니다" }), hBtn("닫기", () => { gt().drop = null; headsColClose(); }));
}
async function gatherDropApply() { // 「반영」(POST …/gather/drop/apply {planId, convert}) — 편집 하나 · 문서를 다시 읽는다
  const g = gt(), D = g.drop, epoch = state.epoch;
  if (!D || D.busy || !gatherMine()) return;
  D.busy = true;
  state.busy = true;
  refreshToolbar();
  gatherDropList(true);
  try {
    await flushAll();
    const r = await gatherCall("/drop/apply", "POST", { planId: D.plan.planId, convert: !!D.convert });
    if (epoch !== state.epoch || g !== gatherState) return;
    applyEditState(r);
    g.drop = null;
    g.links = {}; // 놓은 자리의 판정이 달라질 수 있다 — 다시 읽게
    g.plans = {};
    toast(`끌어 넣음 — 블록 ${nf(r.blocks || 0)}${r.converted ? ` · 틀 맞춤 ${nf(r.converted)}줄` : ""}${(r.dropped || []).length ? ` · 못 옮긴 것 ${r.dropped.length}` : ""}`);
    if (heads.dlg === "gatherDrop") headsColClose();
    await reloadDoc();
    gatherLoad();
  } catch (e) {
    if (g === gatherState && e.status === 409) g.drop = null; // 계획 뒤 문서가 바뀜 — 다시 끌어 놓는다
    toast(e.status === 422 ? `표준 검사에 걸려 되돌렸습니다: ${e.message}` : e.status === 409 ? `놓은 뒤 문서가 바뀌었습니다 — 다시 끌어 놓으세요(${gatherErr(e)})` : `끌어 넣지 못했습니다: ${gatherErr(e)}`, true);
  } finally {
    state.busy = false;
    refreshToolbar();
    if (g === gatherState) { if (g.drop) g.drop.busy = false; if (heads.dlg === "gatherDrop") gatherDropList(true); }
  }
}

if (PEEK) { // 둘째 면 화면 — 손잡이의 도움말(끌어 넣기 출발일 때만) · 끌기가 끝나면 바깥의 놓을 줄을 걷는다. 요청은 보내지 않는다
  const part = () => { try { return parent !== window && parent.gatherPeekPart(state.id); } catch { return false; } };
  document.addEventListener("mouseover", (e) => { const grip = e.target.closest && e.target.closest(".ol-grip"); if (grip && !grip.dataset.gather && part()) { grip.dataset.gather = "1"; grip.title = "끌어서 취합본의 문단 위에 놓으면 이 제목 줄과 그 아래 내용을 그 뒤에 넣습니다(넣기 전에 계획을 확인)"; } });
  document.addEventListener("dragend", () => { try { parent.gatherDragCancel(); } catch { /* 바깥이 준비 전 */ } });
} else gatherBindDrop();

// ---- 기관 구역 표시(spec_취합 ② §9-2 — 2026-11-13 사용자 "문서 프레임 작성할 때, 내용매핑할때 항시 각 기관이 작성하는 구역이 식별이 되어야함. 목적문서에서 그 작성 내용을 확인할 수도 있어야함").
// 2026-11-17 공통 모듈 「편집 구역」(zones.js — spec_구역 ② §6 「화면」)의 화면으로 바뀜: 취합 카드의 이 자리(.gt-zones)에 그 줄(#zonesBar — 「편집 구역」 · 체크 셋(취합은 기관이 기본으로 켜짐) · 「구역 표시」 보기/감추기 · 칩 · 「목록」)이 놓이고,
// 문서의 구역 띠·오른쪽 여백 이름표·넣은 내용 바탕(도움말 「<기관> — 「<기관 문서>」 에서 넣음」) · 2열 목록(kind zones)도 그 모듈이 그린다. 자료 = GET /api/docs/<취합본>/zones — 취합 상태를 읽을 때마다(gatherLoad) 함께 읽는다.
// 기관 문서를 보는 중에도 줄은 취합본의 것이고 문서 표시는 지금 문서가 취합본일 때만 · 둘째 면(기관 문서)에는 안 그린다(zones.js znTarget · znShown)
function gatherZonesEl() { // 카드의 「편집 구역」 줄(.gt-zones) — gatherFlowEl 이 넣고 gatherDraw 가 바꿔 끼운다
  if (typeof zonesBarEl === "function") return zonesBarEl({ gather: true });
  const box = el("div", "gt-zones"); // zones.js 가 없는 화면 — 빈 자리(숨김)
  box.hidden = true;
  return box;
}
