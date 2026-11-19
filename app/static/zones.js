"use strict";
// 편집 구역(spec_구역 ② §6 「화면」) — 문서의 본문 문단·표·표 칸이 어느 기관 · 어느 단계 · 어느 차년도의 것인지 값마다 가려 보이는 공통 모듈. 어느 연구개발 TASK 에서나 같다(취합 카드도 이 줄을 쓴다).
// app.js 다음 · gather.js 앞에 읽는다. 화면 표시일 뿐이다 — 내보내는 hwpx·docx 에는 아무것도 쓰지 않는다(지정·출처는 작업 폴더에만: ② §0 · §7).
//   줄      zonesBarEl(#zonesBar): 이름 + 노트 · 「구역 표시」 보기/감추기 · 「목록」 / 체크 셋(기관 · 단계 · 차년도 = TASK 옵션 — PUT …/task-options: ② §1) / 값마다 칩
//   문서    zonesDraw: 띠(.gz-in) · 쪽 오른쪽 여백의 이름표(.gz-tag — 사람이 지정한 띠는 .gz-mark) · 표와 값이 다른 칸(.gz-cell) · 들어온 내용(.gz-put — 출처 색 data-gzo 는 구역 색 data-gz 를 덮지 않는다)
//   색 설명 zonesKeyDraw(#zonesKey — 문서 위에 떠 있는 상자: key_float.js) · 지정 zonesCtxItems → #zonesPop(떠 있는 작은 입력 — 모달 아님) → POST/PUT/DELETE …/zones/marks(② §3) · 목록 zonesList(문서 옆 2열 kind "zones")
//   LLM 검토(spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」): 줄의 「LLM 검토」 · 「지침」 — 사람이 누를 때만(유료 · 2026-11-18 부터 확인 창 없이). GET …/zones/llm(보낼 후보 · 쓸 수 있나 · 마지막 결과) →
//     POST …/zones/llm {docRev, zonesRev}(응답 = 구역 자료 + llm) → LLM 이 지정한 구역(marks[].by "llm")은 이름표에 「LLM」 꼬리 · 목록의 「지정」 묶음에 근거·까닭 · 「LLM 지정 모두 해제」. 문서는 안 바뀐다
// 자료 = GET /api/docs/<대상 문서>/zones(② §5 의 꼴). 대상 문서 = 지금 문서 — 취합이면 취합본(gather.js gatherPlan: 기관 문서를 보는 중에도 줄은 취합본의 것이고, 문서 표시는 지금 문서가 취합본일 때만).
// 다시 읽는 때: 문서를 열 때 · TASK 를 바꾼 뒤(zonesReset) · 편집으로 문서 차례가 바뀐 뒤(zonesInvalidate — 잠깐 뒤 한 번) · 옵션·지정을 바꾼 뒤 · 취합 상태를 읽을 때(gather.js gatherLoad) · 프로젝트 구성 값이 바뀐 뒤(znSig).
// app.js 가 주는 것: state · PEEK · $ · el · api · H_JSON · toast · nf · oneLine · hBtn · hHelp · hTable · hCell · hRowKeys · headsDlg · headsColClose · heads · divGo · sheetMarginPx · outlineSelected · flushAll ·
//   taskRnd · taskSlots · gatherOn · divSettingsFlush · divCanon · dv · fmtWhen · ctxClose · LOG_KIND · TASK_CATALOG(task_catalog.js — taskZonesDefault). gather.js 가 주는 것(있을 때만): gatherPlan · gatherToPlan.
// app.js 가 부르는 곳(모두 typeof 검사 뒤): divRender(줄) · divMarksDraw(zonesDraw — 쪽을 다시 나눌 때마다) · divCtxItems(zonesCtxItems — 표 칸 메뉴에도 같이) · applyServer/applyEditState(zonesInvalidate) · divReset(zonesReset).

const ZN_KEY = "nfm.zones", ZN_KEY_OLD = "nfm.gatherZones"; // 「구역 표시」 켬/끔(이 브라우저에 기억) — 값이 없으면 옛 키(취합의 「기관 구역」), 그것도 없으면 켬
const ZN_COLORS = 8; // 색 수(zones.css [data-gz="0".."7"] — 그 뒤 값은 돌려 씀) · 모름·확인 필요·값 없음 = "u"
const ZN_DIMS = ["org", "stage", "year"]; // 기준의 차례(app/zones.py DIMS 와 같게)
const ZN_DIM_NAME = { org: "기관", stage: "단계", year: "차년도" };
const ZN_ROLE = { lead: "주관", joint: "공동" };
const ZN_KIND = { added: "더한 내용", filled: "채운 자리", cells: "표 칸", rows: "표 행", drop: "끌어 넣음" }; // 출처의 종류(② §4) → 화면 말
const ZN_KEY_MAX = 6; // 색 설명(문서 위에 떠 있는 상자 #zonesKey)에 보일 값 칩 수(넘으면 「외 n」)
const ZN_HELP = "문서의 문단·표·표 칸이 어느 기관·단계·차년도의 것인지 보입니다 — 구역의 블록 옆에 색 띠, 구역이 시작하는 곳의 쪽 오른쪽 여백에 이름표(「한국선급 · 2차년도」).\n" +
  "화면 표시일 뿐입니다 — 저장·PDF·내려받는 파일은 그대로입니다.\n" +
  "「보일 기준」(기관 · 단계 · 차년도)은 이 TASK 의 옵션입니다 — 같은 TASK 묶음의 문서가 함께 씁니다.\n" +
  "문서에서 오른쪽 단추 「구역 지정…」 으로 사람이 정할 수 있습니다(이름표가 점선 테로 보입니다).\n" +
  "「LLM 검토」 — 스크립트가 기관·차년도를 못 정한 표·자리를 LLM 에 물어 지정합니다(누를 때만 · 유료 · 문서는 안 바뀜). LLM 이 정한 것은 이름표 끝에 「LLM」 이 붙고, 「목록」 에서 하나씩 또는 모두 해제할 수 있습니다.\n" +
  "취합으로 들어온 내용은 어느 기관 문서에서 왔는지 남습니다 — 그 기관 색의 옅은 바탕(구역의 띠 색과 따로 보입니다).\n" +
  "기관을 켰으면 띠의 색은 기관, 아니면 차년도, 아니면 단계입니다. 기관을 읽지 못한 자리는 회색 「기관 모름」·「기관 확인 필요」.";
const ZN_LLM_KIND = [["conflict", "확인 필요"], ["unknown", "기관 모름"], ["hint", "이름표가 있는데 못 읽은 표"], ["alone", "혼자 빠진 표"]]; // LLM 에 보낼 후보의 종류(GET …/zones/llm kinds) → 확인 창의 말
const ZN_LLM_POLL = 3000; // 다른 화면이 돌린 검토가 끝났는지 다시 보는 간격(ms)
const ZN_RETRY = 2; // 문서 차례가 안 맞는 응답을 버린 뒤 다시 읽는 횟수(그 차례에서) — 서버의 문서가 이 화면보다 앞서 있으면 다시 읽어도 안 맞는다
const ZN_UNSENT = "서버에 반영하지 못한 문단이 있어"; // 밀린 편집이 실패했을 때의 알림 머리(app.js 의 다른 곳과 같은 글투) — 옛 서버 문서로 지정·검토하지 않는다
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { zoneMark: "구역 지정", zoneLlm: "편집 구역 LLM 검토" }); // 「기록」 탭의 이름
if (typeof LLM_GUIDE_STEPS === "object") LLM_GUIDE_STEPS.zones = "편집 구역 LLM 검토"; // 「지침」 열의 이름(app.js llmGuideOpen — step "zones")

// ---- 상태(문서를 열 때마다 새로 — state.epoch 로 가른다 · TASK 를 바꾸면 zonesReset)
let znState = null;
const znFresh = () => ({ epoch: state.epoch, seq: 0, key: "", data: null, loading: false, err: "", missing: false, // data = GET …/zones 몸통 · key = 그 자료의 문서 id · seq = 요청 세대(무효로 만들면 +1)
  timer: null, timerForce: false, sig: null, // 다시 읽기 대기 · 읽을 때의 프로젝트 구성 값 지문(znSig)
  again: 0, againRev: -1, ahead: false, // 문서 차례가 안 맞아 버린 응답 뒤의 다시 읽기 수(그 차례에서) · 서버의 문서가 이 화면보다 앞서 있음(다른 곳에서 바뀜)
  opt: null, optSeq: 0, optTried: "", optBusy: false, optWant: null, listOnly: null, // opt = TASK 옵션 {scope, offered, zones{dims, defaulted}, rev} · optWant = 저장하는 중인 고름
  llm: null, llmKey: "", llmSeq: 0, llmMissing: false, llmErr: "", llmBusy: false, llmT0: 0, llmTick: null, llmPoll: null, llmLast: null }); // llm = GET …/zones/llm 몸통(llmKey = 읽은 때의 문서·차례·구역 판) · llmBusy = 이 화면이 돌리는 중 · llmLast = 방금 끝난 결과
function znStop(Z) { if (Z) { clearTimeout(Z.timer); clearInterval(Z.llmTick); clearTimeout(Z.llmPoll); } } // 버리는 상태의 대기·시계를 끈다
function zn() { if (!znState || znState.epoch !== state.epoch) { znStop(znState); znState = znFresh(); } return znState; }

function znTarget() { // 자료를 읽을 문서 {id, name} | null — 취합이면 취합본(없으면 null)
  if (!state.id) return null;
  if (typeof gatherOn === "function" && gatherOn() && typeof gatherPlan === "function") return gatherPlan();
  return { id: state.id, name: state.name };
}
function zonesOffered() { // 이 문서에 편집 구역을 낼 수 있나 — 연구개발 TASK · 저장된 hwpx 작업 · 둘째 면 아님(② §0 「대상」)
  if (PEEK || !state.id || !state.stored || state.format === "docx" || !taskRnd()) return false;
  const o = zn().opt;
  return !(o && o.offered === false);
}
function zonesDims() { // 지금 옵션의 켠 기준(늘 ZN_DIMS 차례) — 읽은 옵션이 없으면 그 TASK 의 기본값(task_catalog.js)
  const o = zn().opt, job = (state.task && state.task.job) || "";
  const d = o && o.zones && Array.isArray(o.zones.dims) ? o.zones.dims
    : typeof taskZonesDefault === "function" ? taskZonesDefault(job) : ((typeof TASK_CATALOG === "object" && TASK_CATALOG[job]) || {}).zones || [];
  return ZN_DIMS.filter((k) => d.includes(k));
}
function zonesOn() { // 「구역 표시」 가 켜져 있나
  try { const v = localStorage.getItem(ZN_KEY); return (v != null ? v : localStorage.getItem(ZN_KEY_OLD)) !== "off"; } catch { return true; }
}
function znOnSet(on) { try { localStorage.setItem(ZN_KEY, on ? "on" : "off"); } catch { /* 기억만 안 함 */ } }
const znWanted = () => heads.dlg === "zones" || (zonesOn() && zonesDims().length > 0); // 구역을 셀 까닭이 있나 — 목록이 열려 있거나, 표시가 켜져 있고 켠 기준이 있음(켠 기준이 없는 TASK 는 문서를 열 때도 · 고칠 때도 세지 않는다)
function znStale(t) { // 읽어 둔 자료가 그 문서의 것이지만 지금 문서 차례의 것이 아닌가 — 편집 뒤 다시 읽기 전(지금 문서를 보는 중일 때만 견줄 수 있다)
  const Z = zn();
  return !!t && !!Z.data && Z.key === t.id && t.id === state.id && Z.data.rev !== state.serverRev;
}
function znData(t) { // 쓸 수 있는 자료 | null — 그 문서의 것이고 **지금 문서 차례**의 것일 때만(옛 차례의 구역을 새 문서 위에 그리지 않는다: ② §6 「다시 읽는 때」)
  const Z = zn();
  return t && Z.data && Z.key === t.id && !znStale(t) ? Z.data : null;
}
function znShown() { // 지금 문서에 입힐 자료 | null — 표시가 켜져 있고 읽어 둔 자료가 지금 문서의 지금 차례 것일 때만
  if (!zonesOffered() || !zonesOn()) return null;
  return znData({ id: state.id });
}
function znSig() { // 자동 판독이 읽는 값(반영한 값 → 입력 값)의 지문 | null(아직 모름) — 값이 바뀌면 문서 차례가 그대로여도 다시 읽는다
  if (typeof dv === "undefined" || !dv || !dv.view) return null;
  const a = dv.view.applied && dv.view.applied.values;
  try { return (a ? divCanon(a) : "") + "|" + (dv.savedKey || ""); } catch { return null; }
}
const znWhen = (at) => (at == null || at === "" ? "" : fmtWhen(typeof at === "number" ? at : Date.parse(at) / 1000)); // 서버의 시각이 초든 ISO 글이든
function znErr(e) { const d = e && e.body && e.body.detail; return (d && typeof d === "object" && typeof d.message === "string" && d.message) || (e && e.message) || "알 수 없는 오류"; } // 끝점의 오류 = detail {reason, message}
const znWhy = (e) => { const d = e && e.body && e.body.detail; return d && typeof d === "object" && typeof d.reason === "string" ? d.reason : ""; }; // 오류의 까닭 열쇠(staleDoc · staleZones · badMark · noMark …)
async function znFlushed(what) { // 밀린 편집을 먼저 서버에 보낸다 → 다 반영됐나. 반영하지 못한 문단이 남아 있으면(flushAll 은 실패를 삼킨다 — app.js state.failed) 알리고 false: 옛 서버 문서로 지정·검토하지 않는다
  try { await flushAll(); } catch { /* 실패는 state.failed 에 남는다 */ }
  if (!state.failed.size) return true;
  toast(`${ZN_UNSENT} ${what} — 「고친 문단」 탭에서 먼저 다시 반영하세요`, true);
  return false;
}

// ---- 값의 이름 · 색
function znYearStage(y, stages) { // 전체 차례의 차년도 → [단계, 단계 안 차년도] | null(범위 밖)
  let k = y;
  for (let s = 0; s < (stages || []).length; s++) { if (k <= stages[s]) return [s + 1, k]; k -= stages[s]; }
  return null;
}
function znYearName(y, stages) { // 「2차년도」 · 단계가 둘 이상이면 「2단계 1차년도」
  const at = znYearStage(y, stages);
  return !at ? `${y}차년도` : (stages || []).length > 1 ? `${at[0]}단계 ${at[1]}차년도` : `${at[1]}차년도`;
}
function znOrgs(D) { // 기관 열쇠 → {i(색 차례 | "u"), name, role}
  const m = new Map(((D && D.orgs) || []).map((o, i) => [o.key, { i: String(i % ZN_COLORS), name: o.name || o.key, role: o.role || "" }]));
  const of = (key, kind) => (kind === "unknown" ? { i: "u", name: "기관 모름", role: "" } : kind === "conflict" ? { i: "u", name: "기관 확인 필요", role: "" }
    : !key ? { i: "u", name: "기관 없음", role: "" } : m.get(key) || { i: "u", name: key, role: "" });
  return { of, has: (k) => m.has(k) };
}
const znAxis = (dims) => (dims.includes("org") ? "org" : dims.includes("year") ? "year" : dims.includes("stage") ? "stage" : ""); // 색 축은 하나 — 기관 › 차년도 › 단계
function znColor(L, axis, org) { // 그 값의 색 차례 "0".."7" | "u"
  L = L || {};
  if (axis === "org") return L.orgKind ? org.of(L.org, L.orgKind).i : "u";
  if (axis === "year") return L.year != null ? String(L.year % ZN_COLORS) : "u";
  if (axis === "stage") return L.stage != null ? String(L.stage % ZN_COLORS) : "u";
  return "u";
}
function znLabelText(L, D, dims) { // 값의 이름 「한국선급 · 1단계 2차년도」 — 서버의 이름표 글(zone.text)이 없는 곳(칸)에 쓴다
  L = L || {};
  const out = [], stages = (D && D.stages) || [];
  if (dims.includes("org") && L.orgKind) out.push(znOrgs(D).of(L.org, L.orgKind).name);
  if (dims.includes("year") && L.year != null) out.push(znYearName(L.year, stages));
  else if (dims.includes("stage") && L.stage != null) out.push(`${L.stage}단계`);
  return out.join(" · ");
}
function znMarkText(label, D) { // 사람이 지정한 값의 이름 — 키가 있는 기준만(null = 그 기준 없음)
  const out = [], has = (k) => Object.prototype.hasOwnProperty.call(label || {}, k), stages = (D && D.stages) || [];
  if (has("org")) out.push(label.org == null ? "기관 없음" : znOrgs(D).of(label.org, "org").name);
  if (has("stage")) out.push(label.stage == null ? "단계 없음" : `${label.stage}단계`);
  if (has("year")) out.push(label.year == null ? "차년도 없음" : znYearName(label.year, stages));
  return out.join(" · ") || "(값 없음)";
}

// ---- 읽기
function znRedraw() { zonesBarRefresh(); zonesDraw(); if (heads.dlg === "zones") zonesList(null, true); znLlmPeek(); }
function znApply(r, id) { // 지정 끝점의 응답(= GET 과 같은 꼴)을 상태로 — 그 사이 떠난 GET 은 버린다
  const Z = zn();
  Z.seq += 1;
  Object.assign(Z, { loading: false, data: r, key: id, err: "", missing: false, again: 0, ahead: false });
  if (r && r.options) Z.opt = r.options;
  if (r && id === state.id && r.rev !== state.serverRev) { // 응답이 지금 문서 차례의 것이 아니다(문서를 안 견주는 해제 끝점 등) — 그리지 않고(znData) 다시 읽거나, 서버가 앞서 있으면 그렇게 알린다
    Z.ahead = r.rev > state.serverRev;
    if (!Z.ahead) znSoon("edit");
  }
  znRedraw();
}
async function znOptionsLoad(force = false) { // 구역을 세지 않을 때(표시가 꺼져 있음 · 켠 기준이 없음) — 체크(옵션)만 가볍게 읽는다(문서마다 한 번)
  const Z = zn(), t = znTarget();
  if (!t || !zonesOffered() || (!force && Z.optTried === t.id)) return;
  Z.optTried = t.id;
  const epoch = state.epoch, seq = ++Z.optSeq;
  let r = null;
  try { r = await api(`/api/works/${t.id}/task-options`); } catch { /* 끝점이 없는 서버 — 기본값으로 그린다 */ }
  if (!r || epoch !== state.epoch || Z !== znState || seq !== Z.optSeq) return;
  Z.opt = r;
  znRedraw();
}
async function zonesLoad(force = false) { // GET …/zones → 상태 → 줄 · 문서 표시 · 색 설명(문서 위에 떠 있는 상자) · 열려 있는 목록. force = 표시가 꺼져 있어도 읽는다(지정 · 목록)
  if (PEEK || !state.id) return;
  const Z = zn(), t = znTarget();
  clearTimeout(Z.timer); Z.timer = null;
  if (!t || !zonesOffered()) { znRedraw(); return; }
  const epoch = state.epoch;
  if (!force && heads.dlg !== "zones") {
    if (!Z.opt && Z.optTried !== t.id && !znWanted()) { // 옵션을 아직 모르고 그 TASK 의 기본값으로는 셀 것이 없다 — 옵션만 먼저 가볍게 읽는다(사람이 켜 둔 기준이 있으면 그때 센다)
      await znOptionsLoad();
      if (epoch !== state.epoch || Z !== znState) return;
    }
    if (!znWanted()) { znRedraw(); return; } // 표시가 꺼져 있거나 켠 기준이 없음 — 구역은 안 센다(체크는 옵션으로 그린다)
  }
  const seq = ++Z.seq, mine = t.id === state.id;
  Z.loading = true;
  if (mine) Z.sig = znSig();
  const sig0 = mine ? Z.sig : null; // 이 요청을 보낼 때의 프로젝트 구성 값 지문 — 읽는 사이 값이 바뀌었으면 그 응답은 옛 값으로 센 것이다
  zonesBarRefresh();
  let data = null, err = "", missing = false;
  try {
    if (mine && typeof divSettingsFlush === "function") await divSettingsFlush(); // 자동 판독은 서버에 저장된 값으로 읽는다(입력 중인 값의 자동 저장을 먼저)
    data = await api(`/api/docs/${t.id}/zones`);
  } catch (e) { err = znErr(e); missing = e.status === 404 && e.message === "Not Found"; } // 끝점이 없는 서버(재시작 전)
  if (epoch !== state.epoch || Z !== znState || seq !== Z.seq) return; // 늦게 온 응답 — 문서·TASK 가 바뀌었거나, 그 사이 문서 차례·값이 바뀌어 무효가 됐거나(zonesInvalidate), 더 새 요청이 떠났다(상태에 넣지 않는다)
  Z.loading = false;
  if (data && data.options) Z.opt = data.options; // 옵션은 문서 차례와 무관하다
  if (data && mine) { // 응답이 **지금 문서 차례 · 지금 값**의 것일 때만 상태에 넣는다 — 아니면 버리고 다시 읽는다(편집 앞에 떠난 응답을 새 문서 위에 그리지 않는다)
    const sig1 = znSig(), moved = sig0 != null && sig1 != null && sig0 !== sig1;
    if (data.rev !== state.serverRev || moved) {
      Z.again = (Z.againRev === state.serverRev ? Z.again : 0) + 1;
      Z.againRev = state.serverRev;
      Z.ahead = !moved && data.rev > state.serverRev && Z.again > ZN_RETRY; // 다시 읽어도 서버가 앞서 있다 — 다른 곳에서 문서가 바뀌었다(이 화면의 문서를 다시 읽어야 맞는다)
      znRedraw();
      if (Z.again <= ZN_RETRY) znSoon(moved ? "values" : "edit");
      return;
    }
  }
  Z.again = 0;
  Z.ahead = false;
  if (data) Object.assign(Z, { data, key: t.id, err: "", missing: false });
  else Object.assign(Z, { err, missing });
  znRedraw();
}
function znSoon(reason = "edit") { // 잠깐 뒤 한 번 다시 읽는다 — 구역을 세는 중일 때만(표시가 켜져 있고 켠 기준이 있음 · 목록이 열려 있음) · 치는 동안은 미룬다
  const Z = zn(), force = reason !== "edit";
  clearTimeout(Z.timer); Z.timer = null;
  if (!znWanted()) return; // 꺼져 있으면 안 읽는다 — 켜거나 목록을 열 때 새로 읽는다
  Z.timerForce = Z.timerForce || force;
  const fire = () => {
    Z.timer = null;
    if (Z !== znState || Z.epoch !== state.epoch) return;
    if (state.timers.size || state.inflight) { Z.timer = setTimeout(fire, 800); return; } // 아직 치는 중·반영 중 — 더 기다린다
    const t = znTarget(), must = Z.timerForce;
    Z.timerForce = false;
    if (Z.loading) return; // 이미 읽는 중 — 무효로 만든 뒤에 떠난 요청이라 지금 차례의 것이다(다른 길: 취합 상태 읽기 등)
    if (znData(t) && t.id === state.id && !must) return; // 그 사이 다른 길로 이미 지금 차례의 것을 읽었다
    zonesLoad();
  };
  Z.timer = setTimeout(fire, force ? 200 : state.timers.size || state.inflight ? 800 : 250); // 글을 치는 중이면 넉넉히(치는 동안 되풀이해 읽지 않게), 구조 편집(Enter 등)이 끝난 뒤면 곧
}
function zonesInvalidate(reason = "edit") { // 문서 차례가 바뀜("edit" — app.js applyServer·applyEditState) · 프로젝트 구성 값이 바뀜("values") — **진행 중인 요청도 무효로** 만들고(요청 세대 +1) 잠깐 뒤 다시 읽는다
  if (PEEK || !state.id || !zonesOffered()) return;
  const Z = zn();
  Z.seq += 1; // 떠나 있는 GET 의 응답은 옛 문서 차례(옛 값)의 것 — 와도 버린다
  Object.assign(Z, { loading: false, again: 0, ahead: false });
  Promise.resolve().then(() => { if (Z === znState) zonesBarRefresh(); }); // 부르는 쪽이 이 함수 바로 뒤에 문서 차례를 올린다 — 그 뒤에 줄을 다시 그린다(「문서가 바뀜 — 다시 읽는 중」)
  znSoon(reason);
}
function zonesHeadsSeen(key) { // 헤딩 추출 결과의 열쇠를 받는다(app.js headsRender — 2단계 그래프 · 3단계 표 구조의 실행 「번호|때」 를 이은 글). 이 문서에서 처음 본 열쇠는 적어만 두고, 바뀌었으면 다시 읽는다
  // — 그래프는 윗 제목의 기관 근거 · 표 구조는 표의 머리 근거(② §2)라 헤딩 추출을 다시 돌리면(문서 차례는 그대로) 구역이 달라질 수 있다(2026-11-18 사용자 「그게 있어야 구분이 더 잘될거 아냐?」 · ② §6 「다시 읽는 때」)
  if (PEEK || !state.id) return;
  const Z = zn();
  if (!("graphKey" in Z)) { Z.graphKey = key; return; }
  if (Z.graphKey === key) return;
  Z.graphKey = key;
  zonesInvalidate("values"); // 꺼져 있으면(켠 기준 없음 · 표시 감춤) 안 읽는다 — 켤 때 새로 읽는다
}
function zonesReset() { // 문서를 열 때 · 닫을 때 · TASK 를 바꾼 뒤(app.js divReset) — 읽어 둔 것을 버리고, 문서가 열려 있으면 곧 다시 읽는다
  znStop(znState);
  znState = null;
  znPopClose();
  if (typeof heads !== "undefined" && heads.dlg === "zones") headsColClose(true);
  if (PEEK || !state.id) return;
  const Z = zn();
  Z.timer = setTimeout(() => { // load() 가 끝난 뒤에(divReset 은 그 가운데서 불린다)
    Z.timer = null;
    if (Z !== znState || Z.epoch !== state.epoch) return;
    if (typeof gatherOn === "function" && gatherOn()) { zonesBarRefresh(); return; } // 취합은 취합 상태를 읽을 때(gatherLoad) 함께 읽는다
    zonesLoad();
  }, 0);
}
function zonesToggle() { // 「구역 표시」 보기/감추기
  const on = zonesOn();
  znOnSet(!on);
  if (on) { zonesDraw(); zonesBarRefresh(); } else zonesLoad();
}
async function zonesOptionsSet(dims) { // TASK 옵션(보일 기준) 저장 → 다시 읽기. 판이 다르면(409 — 다른 화면이 먼저 바꿈) 다시 읽고 알린다
  const Z = zn(), t = znTarget();
  if (!t || Z.optBusy) return;
  const epoch = state.epoch, want = ZN_DIMS.filter((k) => (dims || []).includes(k));
  Z.optBusy = true;
  Z.optWant = want;
  Z.optSeq += 1; // 떠나 있던 옵션 읽기는 버린다
  zonesBarRefresh();
  try {
    const body = { zones: { dims: want }, ...(Z.opt && Z.opt.rev != null ? { rev: Z.opt.rev } : {}), ...(Z.opt && Z.opt.scope ? { scope: Z.opt.scope } : {}) }; // 읽어 둔 옵션의 판과 범위(TASK 묶음)를 같이 — 그 사이 다른 묶음으로 옮겨졌으면 서버가 409 staleOptions
    const r = await api(`/api/works/${t.id}/task-options`, { method: "PUT", headers: H_JSON, body: JSON.stringify(body) });
    if (epoch !== state.epoch || Z !== znState) return;
    Z.opt = r;
  } catch (e) {
    if (epoch !== state.epoch || Z !== znState) return;
    const d = e && e.body && e.body.detail, why = d && typeof d === "object" ? d.reason : "";
    if (e.status === 409 && why !== "brokenOptions") { // staleOptions — 다른 화면이 먼저 바꿨다: 지금 옵션(응답에 실려 온다 — 없으면 다시 읽는다)으로 돌아간다
      toast("다른 화면에서 편집 구역의 「보일 기준」 이 바뀌었습니다 — 다시 읽었습니다. 다시 고르세요", true);
      Z.optBusy = false;
      if (d && d.options && d.options.zones) Z.opt = d.options; else await znOptionsLoad(true);
      if (epoch !== state.epoch || Z !== znState) return;
    } else toast(`편집 구역의 「보일 기준」 을 저장하지 못했습니다: ${e.status === 404 && e.message === "Not Found" ? "서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : znErr(e)}`, true);
  } finally { if (Z === znState) Z.optBusy = false; }
  if (epoch !== state.epoch || Z !== znState) return;
  await zonesLoad(); // 켠 기준이 있으면 구역을 다시 세고, 없으면 줄·문서 표시만 다시 그린다
}

// ---- LLM 검토(spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」) — 스크립트가 기관·차년도를 못 정한 표·자리를 LLM 이 보고 지정한다. 저절로 돌지 않는다(사람이 단추로 · 유료 · 확인 뒤) · 문서는 안 바뀐다.
// GET …/zones/llm → {available, why, running, candidates, kinds{conflict, unknown, hint, alone}, truncated, last{at, candidates, marked, kept, dropped, summary, error} | null}(LLM 을 안 부른다) ·
// POST …/zones/llm {docRev, zonesRev} → 구역 자료(② §5 의 꼴) + llm{candidates, marked, kept, dropped, summary, truncated, call} | llm{nothing, candidates: 0} · 409 staleDoc·staleZones·busy·noLlm · 502 llmFailed
const znSecs = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return s < 60 ? `${s}초` : `${Math.floor(s / 60)}분 ${s % 60}초`; };
const znCount = (x) => (Array.isArray(x) ? x.length : Number(x) || 0);
const znLlmKey = (t, D) => `${t.id}|${D.rev}|${D.zonesRev}`;
function znLlmText(L) { // 결과 한 줄의 글 — 「후보 3 · 지정 2 · 그대로 1」
  if (!L) return "";
  if (L.error) return `실패 — ${L.error}`;
  if (L.nothing) return "후보가 없습니다";
  return [`후보 ${nf(znCount(L.candidates))}`, `지정 ${nf(znCount(L.marked))}`, `그대로 ${nf(znCount(L.kept))}`, znCount(L.dropped) ? `버림 ${nf(znCount(L.dropped))}` : ""].filter(Boolean).join(" · ");
}
function znLlmPeek() { // 구역 자료를 읽은 뒤 한 번 — 문서 차례·구역 판이 바뀌면 다시. 줄에 단추가 있을 때만(켠 기준이 있음) · 끝점이 없는 서버면 다시 묻지 않는다
  const Z = zn(), t = znTarget();
  if (PEEK || !t || !zonesOffered() || Z.llmMissing || Z.llmBusy || !zonesDims().length) return;
  const D = znData(t); // 지금 문서 차례의 자료를 읽은 뒤에만
  if (!D || (D.reasons || []).includes("unsupportedForm") || Z.llmKey === znLlmKey(t, D)) return;
  znLlmLoad();
}
async function znLlmLoad() { // 보낼 후보 수 · LLM 을 쓸 수 있나 · 마지막 결과 — 문서도 구역도 안 바뀐다
  const Z = zn(), t = znTarget();
  if (PEEK || !t || !zonesOffered()) return;
  const D = znData(t), epoch = state.epoch, seq = ++Z.llmSeq;
  clearTimeout(Z.llmPoll); Z.llmPoll = null;
  if (D) Z.llmKey = znLlmKey(t, D); // 같은 차례에는 한 번만(못 읽어도 되풀이하지 않는다)
  let r = null, err = "", missing = false;
  try { r = await api(`/api/docs/${t.id}/zones/llm`); }
  catch (e) { err = znErr(e); missing = e.status === 404 && e.message === "Not Found"; } // 끝점이 없는 서버(재시작 전) — 단추를 안 보인다
  if (epoch !== state.epoch || Z !== znState || seq !== Z.llmSeq) return;
  const was = !!(Z.llm && Z.llm.running);
  Object.assign(Z, { llm: r, llmErr: err, llmMissing: missing });
  if (r && r.running && !Z.llmBusy) Z.llmPoll = setTimeout(() => { if (Z === znState) znLlmLoad(); }, ZN_LLM_POLL); // 다른 화면이 돌리는 중 — 끝났는지 다시 본다
  else if (was && r && !r.running && !Z.llmBusy) { zonesLoad(true); return; } // 다른 화면의 검토가 끝났다 — 그 지정을 읽는다
  zonesBarRefresh();
}
function znLlmBtn(Z, fkey, noValues = false) { // 줄 머리의 「LLM 검토」 — 도는 동안은 동그라미 + 「LLM 검토 중… n초」(design.md §7), 못 누를 때는 까닭을 도움말에
  const L = Z.llm, b = el("button", "btn sm zn-llm"), text = el("span", "zn-llm-t", "LLM 검토");
  b.type = "button";
  b.dataset.zones = "llm";
  fkey(b, "llm");
  b.append(text);
  if (Z.llmBusy || (L && L.running)) {
    b.classList.add("run");
    b.disabled = true;
    text.textContent = Z.llmBusy ? `LLM 검토 중… ${znSecs(Date.now() - Z.llmT0)}` : "LLM 검토 중…";
    b.title = Z.llmBusy ? "스크립트가 못 정한 표·자리를 LLM 에 묻는 중입니다(수십 초) — 그동안 지정을 바꾸면 결과를 반영하지 않습니다"
      : "이 문서의 LLM 검토가 다른 화면에서 도는 중입니다 — 끝나면 그 결과를 읽습니다";
  } else if (!L) { b.disabled = true; b.title = `LLM 검토 상태를 읽지 못했습니다${Z.llmErr ? `: ${Z.llmErr}` : ""}`; }
  else if (!L.available) { b.disabled = true; b.title = L.why || "LLM 을 쓸 수 없습니다"; }
  else if (!L.candidates) { b.disabled = true; b.title = noValues ? "프로젝트 구성 값이 없어 LLM 에 물을 후보가 없습니다 — 「프로젝트 구성」 에서 먼저 정하세요" : "LLM 에 물을 후보가 없습니다 — 스크립트가 모두 읽었습니다"; }
  else {
    b.title = `스크립트가 기관·차년도를 못 정한 표·자리 ${nf(L.candidates)}곳을 LLM 에 물어 지정합니다 — 누르면 무엇을 보내는지 보이고 확인을 받습니다(유료 · 문서는 안 바뀜)`;
    b.onclick = () => znLlmRun();
  }
  return b;
}
async function znLlmRun() {
  const Z = zn(), t = znTarget(), L = Z.llm;
  if (!t || Z.llmBusy || !L || !L.available || !L.candidates || L.running) return;
  // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」 — 전에는 보낼 후보 수를 적은 확인 창: design.md §18 「확인 창」)
  const epoch = state.epoch, mine = t.id === state.id, alive = () => epoch === state.epoch && Z === znState;
  Z.llmBusy = true;
  Z.llmT0 = Date.now();
  clearTimeout(Z.llmPoll); Z.llmPoll = null;
  Z.llmTick = setInterval(() => { // 1초마다 글만 바꾼다(줄을 다시 그리면 동그라미가 끊긴다)
    const s = document.querySelector('#zonesBar [data-zones="llm"] .zn-llm-t');
    if (s && Z.llmBusy) s.textContent = `LLM 검토 중… ${znSecs(Date.now() - Z.llmT0)}`;
  }, 1000);
  zonesBarRefresh();
  try {
    if (mine && !(await znFlushed("LLM 검토를 하지 않았습니다"))) return; // 밀린 편집을 먼저 보내고 그 뒤의 문서 차례를 쓴다(지정 저장과 같은 방식) — 반영 실패가 남아 있으면 멈춘다
    if (!alive()) return;
    if (!znData(t)) { await zonesLoad(true); if (!alive()) return; }
    const D = znData(t);
    if (!D) { toast("문서가 바뀌었습니다 — 구역을 다시 읽은 뒤 「LLM 검토」 를 다시 누르세요", true); return; }
    const r = await api(`/api/docs/${t.id}/zones/llm`, { method: "POST", headers: H_JSON, body: JSON.stringify({ docRev: D.rev, zonesRev: D.zonesRev }) });
    if (!alive()) return;
    const { llm, ...view } = r;
    Z.llmLast = { ...(llm || {}), at: Date.now() / 1000 };
    znApply(view, t.id); // 응답 = 구역 자료 그대로 — LLM 이 지정한 구역이 marks(by "llm")로 온다
    toast(`LLM 검토 — ${znLlmText(Z.llmLast)}`);
  } catch (e) {
    if (!alive()) return;
    const d = e && e.body && e.body.detail, why = d && typeof d === "object" ? d.reason : "";
    if (e.status === 409 && (why === "staleZones" || why === "staleDoc")) { // 검토하는 사이 지정·문서가 바뀌었다 — 서버가 결과를 버렸다
      toast(`검토하는 사이 ${why === "staleDoc" ? "문서가" : "구역이"} 바뀌어 결과를 반영하지 않았습니다 — 다시 누르세요`, true);
      zonesLoad(true);
    } else if (d && typeof d === "object" && d.message) toast(d.message, true); // busy · noLlm · llmFailed — 서버 글 그대로
    else toast(e.status === 404 && e.message === "Not Found" ? "LLM 검토는 서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : `LLM 검토를 하지 못했습니다: ${znErr(e)}`, true);
  } finally {
    clearInterval(Z.llmTick); Z.llmTick = null;
    Z.llmBusy = false;
    if (alive()) { Z.llmKey = ""; zonesBarRefresh(); znLlmPeek(); } // 후보 수 · 마지막 결과를 다시 읽는다
  }
}
async function znLlmClear() { // 「LLM 지정 모두 해제」 — LLM 이 지정한 것만(사람이 지정한 것은 그대로) · 문서는 안 바뀐다
  const epoch = state.epoch, t = znTarget(), Z = zn(), D = t && Z.key === t.id ? Z.data : null;
  const n = ((D && D.marks) || []).filter((m) => m.by === "llm").length;
  if (!D || !n) return;
  if (!confirm(`LLM 이 지정한 구역 ${nf(n)}개를 모두 해제할까요?\n그 블록은 자동으로 읽은 값으로 보입니다 — 사람이 지정한 것은 그대로입니다.`)) return;
  try {
    const r = await api(`/api/docs/${t.id}/zones/marks?by=llm&zonesRev=${encodeURIComponent(D.zonesRev)}`, { method: "DELETE" });
    if (epoch !== state.epoch) return;
    znApply(r, t.id);
    toast(`LLM 지정 ${nf(n)}개 해제 — 그 블록은 자동으로 읽은 값으로 보입니다`);
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (e.status === 409) { zonesLoad(true); toast("구역이 바뀌었습니다 — 다시 읽었습니다. 다시 해 보세요", true); }
    else toast(`LLM 지정을 해제하지 못했습니다: ${e.status === 404 && e.message === "Not Found" ? "서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : znErr(e)}`, true);
  }
}

// ---- 줄(패널 「작업 개요」 — 「구분 기준 자리 표시」 줄 아래 · 취합은 취합 카드 안)
function zonesBarEl(opts = {}) {
  const gather = !!opts.gather, box = el(gather ? "div" : "section", "zn-bar gt-zones" + (gather ? "" : " zn-card"));
  box.id = "zonesBar";
  box.dataset.host = gather ? "gather" : "panel";
  const t = znTarget();
  if (!t || !zonesOffered()) { box.hidden = true; return box; }
  const Z = zn(), D = znData(t), stale = znStale(t), on = zonesOn(), dims = zonesDims(), mine = t.id === state.id; // D = 지금 문서 차례의 자료만 — 옛 차례의 것(stale)으로는 칩을 그리지 않는다
  box.dataset.zn = on ? "on" : "off";
  const fkey = (node, k) => { node.dataset.znFocus = k; if (gather) node.dataset.gatherFocus = "zn-" + k; return node; }; // 다시 그린 뒤에도 초점 그대로(zonesBarRefresh · gather.js gatherDraw)
  if (mine && D && !Z.loading) { // 프로젝트 구성 값이 바뀌었으면(문서 차례는 그대로) 다시 읽는다 — 취합은 취합 상태를 읽을 때 함께 읽는다
    const sig = znSig();
    if (sig != null && Z.sig == null) Z.sig = sig;
    else if (sig != null && sig !== Z.sig && !gather) { Z.sig = sig; zonesInvalidate("values"); } // 지문을 먼저 맞춰 둔다 — 무효로 만든 뒤 줄을 다시 그릴 때 되풀이하지 않게
  }

  const head = el("div", "gt-zones-head"), copy = el("span", "zn-copy"), acts = el("span", "zn-head-acts");
  copy.append(el("strong", null, "편집 구역"), hHelp("편집 구역 안내", ZN_HELP, { note: true }));
  const tg = fkey(hBtn(on ? "감추기" : "보기", () => zonesToggle(), // 글 = 「구분 기준 자리 표시」 카드의 보기/감추기와 같은 꼴(2026-11-18 사용자 "디자인 매칭좀 해줘라 보이기 감추기" — design.md §12)
    { cls: "btn sm gt-zones-toggle" + (on ? " on" : ""), title: "문서의 구역 띠 · 이름표 · 넣은 내용 표시 보이기/감추기(이 브라우저에 기억)" }), "toggle");
  tg.setAttribute("aria-pressed", String(on));
  tg.dataset.zones = "toggle";
  const list = fkey(hBtn("목록", () => zonesList(), { title: "문서 옆 열에 값마다의 구역 · 지정 · 넣은 내용 목록을 엽니다 — 줄을 누르면 그 자리로" }), "list");
  list.dataset.zones = "list";
  head.append(copy);
  const llmOn = dims.length > 0 && !Z.llmMissing && (!!Z.llm || Z.llmBusy || !!Z.llmErr); // 「LLM 검토」 · 「지침」 — 켠 기준이 있을 때만(체크만 있는 줄에는 없다) · 끝점이 없는 서버에서는 안 보인다
  if (llmOn) {
    const llm = el("span", "zn-head-llm");
    llm.append(znLlmBtn(Z, fkey, ((D && D.reasons) || []).includes("noValues")));
    if (typeof llmGuideBtn === "function") llm.append(fkey(llmGuideBtn("zones", t.id), "guide")); // 보내는 계약·판단 지침·마지막 프롬프트(app.js — 다른 LLM 검토의 「지침」 과 같은 열)
    head.append(llm);
  }
  acts.append(tg, list);
  head.append(acts);

  const row = el("div", "zn-dims"); // 체크 셋 — 꺼져 있어도 늘 보인다(꺼진 TASK 에서 다시 켤 길)
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", "보일 기준 — 이 TASK 의 옵션");
  row.append(el("span", "zn-dims-name", "보일 기준"));
  const picked = Z.optBusy && Z.optWant ? Z.optWant : dims; // 저장하는 동안은 방금 고른 대로 보인다(누른 체크가 되돌아가 보이지 않게) — 저장이 끝나면 서버의 값
  for (const k of ZN_DIMS) {
    const lab = el("label", "zn-dim" + (picked.includes(k) ? " on" : "")), cb = el("input");
    lab.dataset.dv = k;
    cb.type = "checkbox";
    cb.checked = picked.includes(k);
    cb.disabled = Z.optBusy;
    cb.dataset.zonesDim = k;
    fkey(cb, "dim-" + k);
    cb.onchange = () => { lab.classList.toggle("on", cb.checked); zonesOptionsSet(ZN_DIMS.filter((d) => (d === k ? cb.checked : picked.includes(d)))); };
    lab.append(cb, el("span", null, ZN_DIM_NAME[k]));
    row.append(lab);
  }

  const chips = el("div", "gt-zones-chips"), cap = (text) => chips.append(el("span", "dv-caption", text));
  const chip = (text, title, key, color = null, cls = "") => {
    const c = el("button", "dv-chip gz-chip" + (cls ? " " + cls : ""), text);
    c.type = "button";
    if (color != null) c.dataset.gz = color;
    c.title = title;
    c.onclick = () => zonesList(key);
    chips.append(c);
    return c;
  };
  const reasons = (D && D.reasons) || [];
  if (!dims.length) cap("기관·단계·차년도를 켜면 문서에서 그 값의 구역을 가려 보입니다");
  else if (stale || (Z.ahead && !D)) cap(Z.ahead ? "문서가 다른 곳에서 바뀌었습니다 — 이 화면의 문서를 다시 읽은 뒤에 구역을 볼 수 있습니다" : "문서가 바뀜 — 다시 읽는 중"); // 옛 문서 차례의 구역은 보이지 않는다
  else if (Z.loading && !D) cap("구역을 세는 중…");
  else if (Z.err && !D) cap(Z.missing ? "편집 구역은 서버를 다시 시작한 뒤에 볼 수 있습니다(새 기능)" : `구역을 읽지 못했습니다: ${Z.err}`);
  else if (!D) cap(on ? "구역을 아직 읽지 않았습니다" : "구역 표시가 꺼져 있습니다 — 「보기」 를 누르면 문서에서 구역을 셉니다");
  else if (reasons.includes("unsupportedForm")) cap("이 문서 형식에는 편집 구역이 없습니다(hwpx 문서만)");
  else {
    const staged = gather || (typeof taskSlots === "function" && !!taskSlots());
    if (reasons.includes("noValues")) cap(`프로젝트 구성 값이 없어 구역을 셀 수 없습니다 — ${staged ? "1단계 " : ""}「프로젝트 구성」 에서 정하세요`);
    else znChips(D, dims, chip, cap);
    const marks = D.marks || [], bad = marks.filter((m) => (m.invalid || []).length).length, byLlm = marks.filter((m) => m.by === "llm").length;
    if (marks.length) chip(`지정 ${nf(marks.length)}${byLlm ? `(LLM ${nf(byLlm)})` : ""}`,
      `지정한 구역 ${nf(marks.length)}개 — 사람이 지정 ${nf(marks.length - byLlm)}(문서에서 오른쪽 단추 「구역 지정…」)${byLlm ? ` · LLM 이 지정 ${nf(byLlm)}(「LLM 검토」)` : ""}. 눌러서 목록`, "@marks", null, "zn-chip-mark");
    if (bad) chip(`유효하지 않은 지정 ${nf(bad)}`, "지정한 기관·단계·차년도가 지금 프로젝트 구성에 없습니다 — 그 기준은 자동으로 읽은 값으로 보입니다(다른 값으로 옮기지 않습니다). 눌러서 목록", "@marks", null, "zn-chip-warn");
  }
  box.append(head, row, chips);
  const last = llmOn ? Z.llmLast || (Z.llm && Z.llm.last) : null; // 마지막 LLM 검토의 결과 한 줄 — 방금 끝난 것, 없으면 서버에 남은 것(새로 고친 뒤에도)
  if (last) {
    const line = el("div", "zn-llm-last" + (last.error ? " err" : ""));
    line.dataset.zones = "llm-last";
    line.append(el("span", null, `LLM 검토 — ${znLlmText(last)}${last.truncated ? " · 후보가 많아 앞의 150곳만" : ""}${last.at ? ` · ${znWhen(last.at)}` : ""}`));
    if (last.summary) line.append(hHelp("LLM 검토 요약", String(last.summary), { note: true }));
    box.append(line);
  }
  return box;
}
function znChips(D, dims, chip, cap) { // 값마다 칩 — 기관(색 + 「<이름> 구역 n · 넣은 내용 m」) · 단계 · 차년도 · 확인 필요
  const org = znOrgs(D), axis = znAxis(dims), stages = D.stages || [], zs = D.zones || [];
  let n = 0;
  if (dims.includes("org")) {
    const per = new Map(), bump = (k, f) => { const e = per.get(k) || { zones: 0, put: 0 }; e[f] += 1; per.set(k, e); };
    for (const z of zs) { const L = z.label || {}; if (L.orgKind === "org" && L.org) bump(L.org, "zones"); else if (L.orgKind === "unknown") bump("?", "zones"); }
    for (const a of D.origins || []) if ((a.ids || []).length) for (const k of (a.orgs || []).length ? a.orgs : ["?"]) bump(k, "put");
    const keys = [...(D.orgs || []).map((o) => o.key), ...[...per.keys()].filter((k) => k !== "?" && !org.has(k)), ...(per.has("?") ? ["?"] : [])];
    for (const k of keys) {
      const e = per.get(k) || { zones: 0, put: 0 }, o = org.of(k === "?" ? null : k, k === "?" ? "unknown" : "org");
      const c = chip(`${o.name} 구역 ${nf(e.zones)}${e.put ? ` · 넣은 내용 ${nf(e.put)}` : ""}`,
        `${o.name}${o.role ? `(${ZN_ROLE[o.role] || o.role})` : ""} — 구역 ${nf(e.zones)}곳 · 기관 문서에서 넣은 내용 ${nf(e.put)}곳. 눌러서 목록`, k, o.i);
      c.dataset.org = k;
      n += 1;
    }
  }
  const count = (f) => { const m = new Map(); for (const z of zs) { const v = (z.label || {})[f]; if (v != null) m.set(v, (m.get(v) || 0) + 1); } return [...m].sort((a, b) => a[0] - b[0]); };
  if (dims.includes("stage")) for (const [s, k] of count("stage")) { const c = chip(`${s}단계 구역 ${nf(k)}`, `${s}단계 — 구역 ${nf(k)}곳. 눌러서 목록`, "stage:" + s, axis === "stage" ? String(s % ZN_COLORS) : null); c.dataset.stage = s; n += 1; }
  if (dims.includes("year")) for (const [y, k] of count("year")) { const name = znYearName(y, stages), c = chip(`${name} 구역 ${nf(k)}`, `${name} — 구역 ${nf(k)}곳. 눌러서 목록`, "year:" + y, axis === "year" ? String(y % ZN_COLORS) : null); c.dataset.year = y; n += 1; }
  const check = dims.includes("org") ? zs.filter((z) => (z.label || {}).orgKind === "conflict").length : 0;
  if (check) { chip(`확인 필요 ${nf(check)}`, "기관을 읽은 근거가 서로 다른 구역(번호로 읽은 기관과 글에 적힌 이름이 다름) — 문서의 라벨을 고치거나 「구역 지정…」 으로 정하세요. 눌러서 목록", "@check", "u", "zn-chip-warn"); n += 1; }
  if (!n) cap("구역을 찾지 못했습니다");
}
function zonesBarRefresh() { // 줄을 다시 그려 바꿔 끼운다(초점은 그대로)
  const old = document.getElementById("zonesBar");
  if (!old) return;
  const act = document.activeElement, focus = act && old.contains(act) && act.dataset ? act.dataset.znFocus || "" : "";
  old.replaceWith(zonesBarEl({ gather: old.dataset.host === "gather" }));
  if (focus) { const to = document.querySelector(`#zonesBar [data-zn-focus="${CSS.escape(focus)}"]`); if (to && !to.disabled) to.focus({ preventScroll: true }); }
}

// ---- 문서 표시 — 쪽을 다시 나눌 때마다(app.js divMarksDraw) · 자료가 바뀔 때 · 켜고 끌 때. 읽기 단계(자리 재기)와 쓰기 단계(이름표 붙이기)를 나눈다(references/브라우저_강제배치_비용.md).
// #doc·body 에는 클래스를 달지 않는다(문서 전체 스타일 다시 계산) — 표시는 요소마다
function zonesDraw() {
  const doc = typeof $ === "function" ? $("doc") : null;
  if (!doc) return;
  for (const t of doc.querySelectorAll(".gz-tag")) t.remove();
  for (const n of doc.querySelectorAll(".gz-in, .gz-put, .gz-cell")) {
    n.classList.remove("gz-in", "gz-put", "gz-cell");
    delete n.dataset.gz;
    delete n.dataset.gzo;
    if (n.dataset.gzTitle) { n.removeAttribute("title"); delete n.dataset.gzTitle; }
  }
  const D = znShown();
  zonesKeyDraw();
  if (!D) return;
  const dims = zonesDims(), axis = znAxis(dims);
  if (!axis) return; // 켠 기준이 없으면 문서에 입히는 것도 없다
  const zones = D.zones || [], cellsOf = D.cells || {}, puts = dims.includes("org") ? (D.origins || []).filter((a) => (a.ids || []).length) : []; // 들어온 내용의 색 = 그 기관 문서의 기관 — 기관을 켰을 때만
  if (!zones.length && !puts.length && !Object.keys(cellsOf).length) return;

  const org = znOrgs(D), idx = new Map(), add = (k, e) => { const a = idx.get(k); if (a) a.push(e); else idx.set(k, [e]); };
  for (const e of doc.querySelectorAll(".para[data-id], table.tbl[data-tbl], td[data-cell]")) add(e.dataset.id || e.dataset.tbl || e.dataset.cell, e);
  const mark = (e, cls, color, title) => { e.classList.add(cls); e.dataset.gz = color; if (title && !e.title) { e.title = title; e.dataset.gzTitle = "1"; } };
  const tags = [], zoneOf = new Map(), markOf = new Map((D.marks || []).map((m) => [m.id, m])); // 이름표를 달 곳(띠마다 첫 블록) · 블록 id → 그 띠의 이름 · 지정 id → 지정
  for (const z of zones) {
    const color = znColor(z.label, axis, org), name = z.text || znLabelText(z.label, D, dims) || "구역";
    const mk = z.mark ? markOf.get(z.mark) : null, llm = !!mk && mk.by === "llm"; // LLM 이 지정한 띠 — 사람이 지정한 것과 가려 보인다(이름표에 「LLM」 꼬리 · 도움말에 까닭)
    const how = !z.mark ? "" : llm ? `(LLM 이 지정${mk.note ? ` — ${mk.note}` : ""})` : "(사람이 지정)";
    const tip = `편집 구역 — ${name}${how}${(z.path || []).length ? `\n${z.path.slice(-2).join(" › ")}` : ""}`;
    let first = null;
    for (const id of z.ids || []) {
      zoneOf.set(id, name);
      for (const e of idx.get(id) || []) {
        if (e.matches(".para") && e.closest("td")) continue; // 칸 안 문단은 표가 맡는다
        mark(e, "gz-in", color, tip);
        if (!first) first = e;
      }
    }
    if (first) tags.push({ e: first, color, name: llm ? `${name} · LLM` : name, tip, marked: !!z.mark, llm });
  }
  const differs = (L, T) => (axis === "org" ? !!L.orgKind && ((L.org || null) !== (T.org || null) || L.orgKind !== (T.orgKind || null))
    : axis === "year" ? L.year != null && L.year !== T.year : L.stage != null && L.stage !== T.stage);
  for (const [tid, cells] of Object.entries(cellsOf)) { // 표와 값이 다른 칸(색 축의 값) — 기관마다 열 하나인 표의 기관 칸 등
    const T = (D.blocks || {})[tid] || {};
    for (const [cid, L] of Object.entries(cells || {})) {
      if (!L || !differs(L, T)) continue;
      const name = znLabelText(L, D, dims);
      for (const e of idx.get(cid) || []) mark(e, "gz-cell", znColor(L, axis, org), `${ZN_DIM_NAME[axis]} 칸 — ${name}`);
    }
  }
  for (const a of puts) { // 들어온 내용 — 출처 색(data-gzo)만 건다: 구역의 띠 색(data-gz)은 그대로(「A 구역 · B 에서 들어옴」)
    const ks = a.orgs || [], o = ks.length === 1 ? org.of(ks[0], "org") : { i: "u", name: ks.length ? `기관 ${ks.length}곳` : "기관 미지정" };
    const tip = `${o.name} — 「${a.name || ""}」 에서 넣음${a.at ? `(${znWhen(a.at)})` : ""}${ZN_KIND[a.kind] ? ` · ${ZN_KIND[a.kind]}` : ""}${a.legacy ? " · 옛 기록" : ""}`;
    for (const id of a.ids) {
      const zt = zoneOf.get(id);
      for (const e of idx.get(id) || []) { e.classList.add("gz-put"); e.dataset.gzo = o.i; e.title = tip + (zt ? `\n편집 구역 — ${zt}` : ""); e.dataset.gzTitle = "1"; } // 넣은 내용의 도움말이 구역 도움말보다 앞선다
    }
  }
  const jobs = []; // 이름표 — 띠 첫 블록의 쪽 오른쪽 여백(왼쪽 여백은 개요·표 표지 몫). 같은 쪽 같은 자리에 겹치면 아래로 민다
  for (const h of tags) {
    const sheet = h.e.closest(".sheet");
    if (!sheet) continue;
    const sr = sheet.getBoundingClientRect(), z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1;
    jobs.push({ sheet, z, top: Math.round(h.e.getBoundingClientRect().top - sr.top), mgr: typeof sheetMarginPx === "function" ? sheetMarginPx(sheet, z) : 60, h });
  }
  const last = new Map(); // 쪽 → 마지막 이름표 아래끝(화면 px)
  for (const j of jobs) {
    const t = el("div", "gz-tag" + (j.h.marked ? " gz-mark" : "") + (j.h.llm ? " gz-llm" : ""), j.h.name);
    t.dataset.gz = j.h.color;
    t.title = j.h.tip;
    t.style.zoom = String(1 / j.z);
    t.style.setProperty("--mgr", `${j.mgr}px`);
    const top = Math.max(j.top, (last.get(j.sheet) || -1e9) + 2);
    t.style.top = `${top}px`;
    last.set(j.sheet, top + 30);
    j.sheet.append(t);
  }
}

// ---- 색 설명(#zonesKey — design.md §4 「색 설명은 문서 위에 떠 있는 상자로」): 표시가 켜져 있고 띠가 있을 때만 — 「편집 구역」 + 지금 문서에 있는 값의 칩(색 네모 + 이름) + 노트.
// 2026-11-19 사용자 "구분자리, 편집구역은 각각 아이콘으로 두고 클릭 하면 문서 상단에 플로팅으로 띄어줘, 움직일 수 있게": 문서 이름 줄이 아니라 문서 위에 떠 있는 상자다(#viewer 안 — 자리 · 끌어 옮기기 · 기억은 key_float.js).
// 이름 줄에는 켜고 끄는 아이콘(#nameZones)만 남는다 — 그 아이콘으로 켜면 뜨고 끄면 사라진다
function zonesKeyDraw() {
  if (typeof docQuickSync === "function") docQuickSync(); // 이름 줄 아이콘 「편집 구역 표시」(doc_quick.js #nameZones)의 눌림 · 꺼짐(옵션을 읽은 뒤 · 줄의 「보기/감추기」 뒤에도 따라온다)
  const box = typeof $ === "function" ? $("zonesKey") : null;
  if (!box) return;
  const D = znShown(), dims = D ? zonesDims() : [], axis = znAxis(dims), items = new Map();
  let marked = false;
  if (D && axis) {
    const org = znOrgs(D), ord = new Map((D.orgs || []).map((o, i) => [o.key, i]));
    for (const z of D.zones || []) {
      const L = z.label || {};
      if (z.mark) marked = true;
      const k = axis === "org" ? (L.orgKind === "org" ? "o:" + L.org : L.orgKind ? "k:" + L.orgKind : "") : axis === "year" ? (L.year != null ? "y:" + L.year : "") : L.stage != null ? "s:" + L.stage : "";
      if (!k || items.has(k)) continue;
      items.set(k, { name: axis === "org" ? org.of(L.org, L.orgKind).name : axis === "year" ? znYearName(L.year, D.stages) : `${L.stage}단계`, color: znColor(L, axis, org),
        at: axis === "org" ? (L.orgKind === "org" ? (ord.has(L.org) ? ord.get(L.org) : 900) : L.orgKind === "unknown" ? 998 : 999) : axis === "year" ? L.year : L.stage });
    }
  }
  const list = [...items.values()].sort((a, b) => a.at - b.at);
  const sig = list.length ? list.map((x) => x.color + "=" + x.name).join("|") + (marked ? "|지정" : "") : "";
  if (box.dataset.sig === sig && box.hidden === !sig) return; // 쪽을 다시 나눌 때마다 불린다 — 같으면 그대로(열어 둔 노트가 닫히지 않게 · 옮긴 자리도 그대로)
  box.dataset.sig = sig;
  box.hidden = !sig;
  box.textContent = "";
  const place = () => { if (typeof keyFloatPlace === "function") keyFloatPlace(); }; // 떠 있는 상자의 자리(key_float.js) — 이 설명이 사라지면 옆 상자(구분 기준 자리)가 가운데로 온다
  if (!sig) { place(); return; }
  if (typeof keyFloatGrip === "function") box.append(keyFloatGrip()); // 손잡이(끌어서 옮기기)
  box.append(el("span", "dv-key-name", "편집 구역"));
  for (const x of list.slice(0, ZN_KEY_MAX)) { const chip = el("span", "dv-chip zn-key-chip"); chip.dataset.gz = x.color; chip.title = x.name; chip.append(el("span", "zn-key-chip-t", x.name)); box.append(chip); }
  if (list.length > ZN_KEY_MAX) { const more = el("span", "zn-key-more", `외 ${list.length - ZN_KEY_MAX}`); more.title = list.slice(ZN_KEY_MAX).map((x) => x.name).join(" · "); box.append(more); }
  if (marked) box.append(el("span", "zn-key-tone", "점선 이름표 = 지정"));
  // 감추기 · 다시 보기 = 문서 이름 줄의 아이콘 #nameZones(doc_quick.js — 2026-11-18 사용자 "… 편집구역 아이콘 … 활성화"). 설명 안에 「감추기」 단추는 없다 — 같은 일을 하는 아이콘이 있다(design.md §10)
  const again = "감추거나 다시 보려면 문서 이름 줄의 「편집 구역 표시」 아이콘을 누르세요(「작업 개요」 의 「편집 구역」 「보기/감추기」 에도 있음)";
  const move = "이 상자는 끌어서 옮길 수 있습니다(자리는 이 브라우저에 기억 · 두 번 누르면 제자리).";
  box.append(hHelp("편집 구역 색 안내", ZN_HELP + "\n" + again + ".\n" + move, { note: true }));
  place();
}

// ---- 지정(② §3) — 문서에서 오른쪽 단추 → 「구역 지정…」 → 떠 있는 작은 입력(#zonesPop). 대상은 본문 최상위 문단·표(칸 안이면 그 표 — 항목 글이 그렇게 말한다) · 그림·캡션은 아니다
function znTops() { // 본문 최상위 블록 id → "paragraph" | "table"(캡션 블록 뺌) — 문서 차례
  const m = new Map();
  for (const b of state.blocks || []) if (!b.captionOf && (b.type === "paragraph" || b.type === "table")) m.set(b.id, b.type);
  return m;
}
function znPick(e) { // 누른 곳·선택 → {ids[문서 차례], at(누른 블록), cell(칸 안에서 불렀나)} | null
  const n = e && e.target, t = n && (n.nodeType === 1 ? n : n.parentElement);
  if (!t || !t.closest || !t.closest("#doc")) return null;
  const tops = znTops();
  let tbl = t.closest("table.tbl[data-tbl]");
  if (tbl) { // 칸 안 — 가장 바깥 표가 대상(칸은 지정 대상이 아니다)
    for (;;) { const up = tbl.parentElement && tbl.parentElement.closest("table.tbl[data-tbl]"); if (!up) break; tbl = up; }
    const id = tbl.dataset.tbl;
    return tops.get(id) === "table" ? { ids: [id], at: id, cell: true } : null;
  }
  const p = t.closest(".para[data-id]");
  if (!p || tops.get(p.dataset.id) !== "paragraph") return null;
  const got = new Set([p.dataset.id]), s = getSelection();
  if (s.rangeCount && !s.isCollapsed && s.getRangeAt(0).intersectsNode(p)) { // 선택이 걸친 본문 문단 + 선택이 통째로 지나간 표
    const r = s.getRangeAt(0), paras = typeof outlineSelected === "function" ? outlineSelected(p) : [p];
    if (paras.includes(p)) {
      for (const q of paras) if (tops.get(q.dataset.id) === "paragraph") got.add(q.dataset.id);
      const part = new Set(); // 선택이 안에서 시작하거나 끝난 표(조각 포함) — 통째로 지나간 것이 아니다
      for (const x of $("doc").querySelectorAll("table.tbl[data-tbl]")) {
        const id = x.dataset.tbl;
        if (tops.get(id) !== "table" || !r.intersectsNode(x)) continue;
        if (x.contains(r.startContainer) || x.contains(r.endContainer)) part.add(id); else got.add(id);
      }
      for (const id of part) got.delete(id);
    }
  }
  return { ids: [...tops.keys()].filter((id) => got.has(id)), at: p.dataset.id, cell: false };
}
const znMarkOf = (D, id) => ((D && D.marks) || []).find((m) => (m.ids || []).includes(id)) || null; // 그 블록이 든 지정
function zonesCtxItems(e) { // 오른쪽 단추 메뉴 항목(앞에 구분선) — 문단 메뉴 · 표 칸 메뉴 공용(app.js divCtxItems). 켠 기준이 있고 지금 문서가 구역을 읽는 문서일 때만
  if (PEEK || !zonesOffered() || !zonesDims().length) return [];
  const t = znTarget();
  if (!t || t.id !== state.id) return [];
  const pick = znPick(e);
  if (!pick) return [];
  const mark = znMarkOf(znData(t), pick.at); // 지금 문서 차례의 자료로만 본다(없으면 「구역 지정…」 — 입력을 열 때 다시 읽고 가린다)
  if (mark) return [null, ["구역 지정 고치기…", "", () => znPop(e, pick, mark)], ["지정 해제", "", () => znMarkDelete(mark.id)]];
  return [null, [pick.cell ? "이 표를 구역으로 지정…" : "구역 지정…", "", () => znPop(e, pick, null)]];
}
function znPopClose() {
  const o = document.getElementById("zonesPop");
  if (o) o.remove();
  for (const x of document.querySelectorAll("#doc .zn-pick")) x.classList.remove("zn-pick");
}
function znPickText(ids, tops) { // 「문단 3 · 표 1 — 「첫 글…」」
  const np = ids.filter((id) => tops.get(id) === "paragraph").length, nt = ids.length - np, first = ids[0];
  let text = "";
  if (tops.get(first) === "paragraph") text = oneLine(state.texts[first] || "");
  else { const tb = document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(first)}"]`), q = tb && [...tb.querySelectorAll(".para")].find((x) => x.textContent.trim()); text = q ? oneLine(q.textContent) : ""; }
  return `${[np ? `문단 ${nf(np)}` : "", nt ? `표 ${nf(nt)}` : ""].filter(Boolean).join(" · ")} — ${text ? `「${text.slice(0, 40)}${text.length > 40 ? "…" : ""}」` : "(글 없음)"}`;
}
function znNowText(k, ids, D) { // 「그대로」 옆에 보일 지금 값(고른 블록들의 값) — 견주는 값에는 이름을 붙인다
  const vals = new Set(), org = znOrgs(D);
  for (const id of ids) {
    const L = (D.blocks || {})[id] || {};
    vals.add(k === "org" ? (L.orgKind ? org.of(L.org, L.orgKind).name : "없음") : k === "stage" ? (L.stage != null ? `${L.stage}단계` : "없음") : L.year != null ? znYearName(L.year, D.stages) : "없음");
    if (vals.size > 1) return " — 지금 여러 값";
  }
  return vals.size ? ` — 지금 ${[...vals][0]}` : "";
}
async function znPop(e, pick, mark) { // 작은 떠 있는 입력(모달 아님) — 대상 · 켠 기준마다 고르기(「그대로」 · 값 · 「없음」) · 메모 → 「지정」
  znPopClose();
  if (typeof ctxClose === "function") ctxClose();
  const epoch = state.epoch, at = { x: e.clientX || 0, y: e.clientY || 0 }, t = { id: state.id };
  if (!(await znFlushed("구역 지정을 열지 않았습니다"))) return; // 밀린 편집을 먼저 — 고른 블록이 그 뒤의 문서와 맞게(반영 실패가 남아 있으면 멈춘다)
  if (epoch !== state.epoch) return;
  if (!znData(t)) { await zonesLoad(true); if (epoch !== state.epoch) return; }
  const D = znData(t), Z = zn();
  if (!D) { toast(znStale(t) || Z.ahead ? "문서가 바뀌었습니다 — 잠깐 뒤 다시 해 보세요" : `구역을 읽지 못했습니다${Z.err ? `: ${Z.err}` : ""}`, true); return; }
  if ((D.reasons || []).includes("noValues")) { toast("프로젝트 구성 값이 없어 구역을 지정할 수 없습니다 — 「프로젝트 구성」 에서 단계·차년도·기관을 먼저 정하세요"); return; } // 고를 값(기관 목록 · 단계·차년도 범위)이 없다
  if (!mark) mark = znMarkOf(D, pick.at); // 읽어 보니 이미 지정에 든 블록 — 고치기로
  const tops = znTops(), ids = (mark ? mark.ids || [] : pick.ids).filter((id) => tops.has(id));
  if (!ids.length) { toast("지정할 본문 문단·표가 지금 문서에 없습니다"); return; }
  // 이 입력을 **열 때**의 구역 판과 그 지정의 값·메모를 붙들어 둔다 — 저장은 이 판으로 견준다(그 사이 다른 곳에서 지정이 바뀌었으면 서버가 409 staleZones: 오래 열어 둔 입력이 남의 수정을 덮지 않게)
  const held = { zonesRev: D.zonesRev, label: mark ? { ...(mark.label || {}) } : null, note: mark ? String(mark.note || "").trim() : "" };
  const dims = zonesDims(), stages = D.stages || [], cur = held.label || {}, has = (k) => Object.prototype.hasOwnProperty.call(cur, k);
  const title = mark ? "구역 지정 고치기" : "구역 지정";
  const pop = el("div", "dv-pop zn-pop");
  pop.id = "zonesPop";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", title);
  pop.append(el("strong", null, title), el("p", "dv-pop-text", znPickText(ids, tops)));
  if (pick.cell && !mark) pop.append(el("p", "dv-caption", "표 칸은 따로 지정하지 않습니다 — 이 표 전체가 대상입니다"));
  if (mark && mark.by === "llm") pop.append(el("p", "dv-caption", "LLM 이 지정한 구역입니다 — 값을 고치거나, 오른쪽 단추 「지정 해제」 로 자동으로 읽은 값으로 되돌릴 수 있습니다"));
  const sels = {};
  const field = (k, options) => {
    const lab = el("label", "dv-field"), sel = el("select");
    lab.append(el("span", null, ZN_DIM_NAME[k]));
    sel.dataset.znDim = k;
    sel.append(new Option(mark ? "그대로(자동으로 읽은 값)" : `그대로${znNowText(k, ids, D)}`, "="));
    for (const [v, name] of options) sel.append(new Option(name, "v:" + v));
    sel.append(new Option(`${ZN_DIM_NAME[k]} 없음`, "-"));
    if (has(k) && cur[k] != null && !options.some(([v]) => String(v) === String(cur[k]))) sel.append(new Option(`${cur[k]} — 지금 프로젝트 구성에 없음`, "v:" + cur[k])); // 유효하지 않은 지정 — 값은 그대로 보인다
    sel.value = !has(k) ? "=" : cur[k] == null ? "-" : "v:" + cur[k];
    lab.append(sel);
    pop.append(lab);
    sels[k] = sel;
  };
  const show = ZN_DIMS.filter((k) => dims.includes(k) || has(k)); // 켠 기준 + 이 지정이 이미 지닌 기준
  if (show.includes("org")) field("org", (D.orgs || []).map((o) => [o.key, `${o.name || o.key}${ZN_ROLE[o.role] ? `(${ZN_ROLE[o.role]})` : ""}`]));
  if (show.includes("stage")) field("stage", stages.map((_, i) => [i + 1, `${i + 1}단계`]));
  if (show.includes("year")) { const ys = []; for (let y = 1, n = stages.reduce((a, b) => a + b, 0); y <= n; y++) ys.push([y, znYearName(y, stages)]); field("year", ys); }
  if (sels.year && sels.stage) { // 차년도는 그 단계의 것이어야 한다(② §3) — 한쪽을 고르면 다른 쪽을 맞춘다
    const yearOf = () => (sels.year.value.startsWith("v:") ? znYearStage(Number(sels.year.value.slice(2)), stages) : null);
    sels.year.addEventListener("change", () => { const ys = yearOf(); if (ys && sels.stage.value !== "=") sels.stage.value = "v:" + ys[0]; });
    sels.stage.addEventListener("change", () => { const ys = yearOf(); if (ys && sels.stage.value !== "=" && sels.stage.value !== "v:" + ys[0]) sels.year.value = "="; });
  }
  const rowN = el("label", "dv-field");
  rowN.append(el("span", null, "메모(선택)"));
  const note = el("input");
  note.type = "text"; note.maxLength = 200; note.placeholder = "예: 공동2 기관이 맡은 절"; note.value = held.note;
  rowN.append(note);
  pop.append(rowN);
  const acts = el("div", "dv-pop-acts");
  const ok = hBtn(mark ? "고치기" : "지정", async () => {
    const label = mark ? { ...cur } : {};
    for (const [k, sel] of Object.entries(sels)) { const v = sel.value; if (v === "=") delete label[k]; else if (v === "-") label[k] = null; else label[k] = k === "org" ? v.slice(2) : Number(v.slice(2)); }
    if (!Object.keys(label).length) {
      toast(mark ? "모두 「그대로」 면 지정이 없는 것과 같습니다 — 오른쪽 단추 「지정 해제」 를 쓰세요" : "기관·단계·차년도 가운데 하나는 골라야 합니다(「그대로」 만으로는 지정할 것이 없습니다)");
      (Object.values(sels)[0] || note).focus();
      return;
    }
    ok.disabled = true;
    const done = await znMarkSave({ mark, ids, label, note: note.value.trim(), held });
    if (done) znPopClose(); else if (ok.isConnected) ok.disabled = false;
  }, { cls: "btn sm primary" });
  ok.dataset.zones = "mark-ok";
  acts.append(ok, hBtn("취소", () => znPopClose()));
  pop.append(acts);
  pop.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); znPopClose(); } else if (ev.key === "Enter" && ev.target.tagName !== "BUTTON" && !ev.isComposing) { ev.preventDefault(); ok.click(); } });
  document.body.append(pop);
  pop.style.left = `${Math.max(8, Math.min(at.x, innerWidth - pop.offsetWidth - 8))}px`;
  pop.style.top = `${Math.max(8, Math.min(at.y, innerHeight - pop.offsetHeight - 8))}px`;
  for (const id of ids) for (const x of document.querySelectorAll(`#doc .para[data-id="${CSS.escape(id)}"], #doc table.tbl[data-tbl="${CSS.escape(id)}"]`)) x.classList.add("zn-pick"); // 저장 전에 대상 범위를 보인다
  (Object.values(sels)[0] || note).focus();
}
document.addEventListener("mousedown", (e) => { const o = document.getElementById("zonesPop"); if (o && !o.contains(e.target)) znPopClose(); }, true);

const znLabelKey = (label) => JSON.stringify(ZN_DIMS.filter((k) => Object.prototype.hasOwnProperty.call(label || {}, k)).map((k) => [k, label[k]])); // 지정 값의 견줄 글(기준 차례)
async function znMarkSave({ mark, ids, label, note, held }) { // → true = 입력을 닫는다(지정했거나 문서·지정이 바뀌어 다시 골라야 함) · false = 입력은 그대로(값이 틀림 · 반영하지 못한 편집이 있음)
  const epoch = state.epoch, id = state.id;
  const closed = (msg) => { toast(msg, true); return true; };
  if (!(await znFlushed("지정하지 않았습니다"))) return false; // 밀린 편집을 먼저 보낸다 — 반영 실패가 남아 있으면 멈춘다(옛 서버 문서에 지정하지 않는다)
  if (epoch !== state.epoch) return true;
  // docRev = 밀린 편집을 보낸 뒤의 문서 차례 · zonesRev = **입력을 열 때**의 구역 판(held — 최신으로 갈아 끼우지 않는다: 그 사이 지정이 바뀌었으면 서버가 409 staleZones)
  const body = { docRev: state.serverRev, zonesRev: held.zonesRev };
  if (!mark) {
    const tops = znTops();
    if (!ids.every((x) => tops.has(x))) return closed("문서가 바뀌었습니다 — 다시 지정하세요"); // 고른 블록이 그 사이 없어졌다
    Object.assign(body, { ids, label, note });
  } else { // 고치기 — 바꾼 것만 보낸다(메모만 고쳤으면 note 만 · 값만 고쳤으면 label 만: 서버는 준 것만 바꾼다)
    if (znLabelKey(label) !== znLabelKey(held.label)) body.label = label;
    if (note !== held.note) body.note = note;
    if (!("label" in body) && !("note" in body)) { toast("바꾼 것이 없어 그대로 두었습니다"); return true; }
  }
  try {
    const r = await api(`/api/docs/${id}/zones/marks${mark ? "/" + encodeURIComponent(mark.id) : ""}`, { method: mark ? "PUT" : "POST", headers: H_JSON, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return true;
    znApply(r, id);
    toast(`${mark ? "구역 지정 고침" : "구역 지정"} — ${znMarkText(label, r)} · 블록 ${nf(ids.length)}${zonesOn() ? "" : " · 「편집 구역」 의 「보기」 를 누르면 문서에 보입니다"}`);
    return true;
  } catch (e) {
    if (epoch !== state.epoch) return true;
    if (e.status === 409) { zonesLoad(true); return closed(znWhy(e) === "staleDoc" ? "문서가 바뀌었습니다 — 다시 지정하세요" : "구역 지정이 바뀌었습니다 — 다시 지정하세요"); } // 다시 읽고 닫는다 — 낡은 입력으로 덮지 않는다
    if (e.status === 404 && mark && e.message !== "Not Found") { zonesLoad(true); toast("그 지정이 이미 없습니다 — 다시 읽었습니다", true); return true; }
    toast(`지정하지 못했습니다: ${e.status === 404 && e.message === "Not Found" ? "서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : znErr(e)}`, true);
    return false;
  }
}
async function znMarkDelete(mid) { // 「지정 해제」 — 문서는 안 바뀐다(실행 취소 대상 아님)
  const epoch = state.epoch, t = znTarget();
  if (!t) return;
  let Z = zn();
  if (!Z.data || Z.key !== t.id) { await zonesLoad(true); if (epoch !== state.epoch) return; Z = zn(); }
  const D = Z.key === t.id ? Z.data : null;
  if (!D) { toast(`구역을 읽지 못했습니다${Z.err ? `: ${Z.err}` : ""}`, true); return; }
  try {
    const r = await api(`/api/docs/${t.id}/zones/marks/${encodeURIComponent(mid)}?zonesRev=${encodeURIComponent(D.zonesRev)}`, { method: "DELETE" });
    if (epoch !== state.epoch) return;
    znApply(r, t.id);
    toast("지정 해제 — 그 블록은 자동으로 읽은 값으로 보입니다");
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (e.status === 409) { zonesLoad(true); toast("구역이 바뀌었습니다 — 다시 읽었습니다. 다시 해 보세요", true); }
    else if (e.status === 404 && e.message !== "Not Found") { zonesLoad(true); toast("그 지정이 이미 없습니다 — 다시 읽었습니다", true); }
    else toast(`지정을 해제하지 못했습니다: ${znErr(e)}`, true);
  }
}

// ---- 목록(문서 옆 2열 — kind "zones"): 값마다 묶음(구역 줄 · 들어온 내용 줄) · 끝에 「지정」 · 「기관 확인 필요」. 줄을 누르면 그 자리로
function znJump(id) { // 그 블록·칸으로 — 표 id 면 그 표의 첫 문단(divGo 는 문단·칸만 안다)
  const tb = id ? document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(id)}"]`) : null, p = tb && tb.querySelector(".para[data-id]");
  if (id) divGo({ key: p ? p.dataset.id : id });
}
function znGo(ids) {
  const id = (ids || [])[0], t = znTarget();
  if (!id) return;
  if (t && t.id !== state.id && typeof gatherToPlan === "function") { gatherToPlan().then((ok) => ok && znJump(id)); return; } // 취합 — 기관 문서를 보는 중이면 취합본으로 간 뒤
  znJump(id);
}
function zonesList(only = null, keep = false) {
  const Z = zn(), t = znTarget();
  if (!t || !zonesOffered()) return;
  const D = znData(t), stale = znStale(t); // 지금 문서 차례의 자료만 — 옛 차례의 목록은 보이지 않는다(줄을 누르면 엉뚱한 자리로 간다)
  if (keep) heads.keepFold = true;
  const top = keep ? $("headsDlgBody").scrollTop : 0;
  if (!D) { // 아직 못 읽음 — 읽는 중·못 읽음을 열에 보이고(배경에서 다시 그릴 때는 또 읽지 않는다 — 못 읽는 서버에서 되풀이하지 않게) 읽으면 다시 그린다
    const { body, foot } = headsDlg("zones", "편집 구역", t.name || "");
    heads.keepFold = false;
    body.append(el("p", "hnote pad", Z.ahead ? "문서가 다른 곳에서 바뀌었습니다 — 이 화면의 문서를 다시 읽은 뒤에 구역을 볼 수 있습니다" : stale ? "문서가 바뀜 — 구역을 다시 읽는 중…"
      : Z.err && !Z.loading ? (Z.missing ? "편집 구역은 서버를 다시 시작한 뒤에 볼 수 있습니다(새 기능)" : `구역을 읽지 못했습니다: ${Z.err}`) : "구역을 세는 중…"));
    foot.append(hBtn("다시 읽기", () => zonesLoad(true), { disabled: Z.loading }), hBtn("닫기", () => headsColClose()));
    if (only) Z.listOnly = only;
    if (!keep && !Z.loading) zonesLoad(true);
    return;
  }
  const want = only || Z.listOnly;
  Z.listOnly = null;
  const dims = zonesDims(), axis = znAxis(dims), org = znOrgs(D), stages = D.stages || [], zs = D.zones || [], origins = D.origins || [], marks = D.marks || [];
  const { tools, body, foot } = headsDlg("zones", "편집 구역", `${t.name || ""} — ${dims.length ? dims.map((k) => ZN_DIM_NAME[k]).join(" · ") + " 값마다의 구역" : "켠 기준 없음"} · 사람이 지정한 구역 · 기관 문서에서 넣은 내용`);
  heads.keepFold = false;
  const c = D.counts || {};
  tools.append(el("span", "muted", [`구역 ${nf(c.zones || 0)}곳`, `블록 ${nf(c.blocks || 0)}`, `칸 ${nf(c.cells || 0)}`, `지정 ${nf(c.marks || 0)}`, `넣은 내용 ${nf(c.origins || 0)}곳`,
    c.conflicts ? `기관 확인 필요 ${nf(c.conflicts)}` : "", c.unknown ? `기관 모름 ${nf(c.unknown)}` : ""].filter(Boolean).join(" · ")));

  const row = (tb, cells, ids) => { // 줄 — 누르면(Enter·빈칸도) 그 자리로
    const tr = el("tr", ids && ids.length ? "go" : null);
    for (const [text, cls, title] of cells) hCell(tr, text, cls, title || "");
    if (ids && ids.length) { tr.tabIndex = 0; tr.onclick = () => znGo(ids); tr.onkeydown = (e) => { if (e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); znGo(ids); } }; }
    tb.append(tr);
    return tr;
  };
  const table = (head) => { const [tbl, tb] = hTable(head); tbl.classList.add("lk-table", "gt-table", "gz-table"); if (typeof hRowKeys === "function") hRowKeys(tb); return [tbl, tb]; };
  const capEl = (key, text, color = null) => { const cap = el("div", "lk-cap gz-cap", text); cap.dataset.znGroup = key; if (color != null) cap.dataset.gz = color; body.append(cap); return cap; };
  const SRC_HELP = "자동 = 스크립트가 문서에서 읽음 · 지정 = 사람이 지정 · 넣은 내용 = 기관이 안 걸린 자리에 들어온 기관 문서의 기관으로 채움";
  const zoneRow = (tb, z, group) => {
    const L = z.label || {}, text = z.text || znLabelText(L, D, dims), tail = text === group ? "" : text.startsWith(group + " · ") ? text.slice(group.length + 3) : text; // 묶음 이름과 겹치는 앞머리는 뺀다
    const src = z.mark ? "지정" : axis === "org" && (L.src || {}).org === "origin" ? "넣은 내용" : "자동";
    const tr = row(tb, [[`구역${tail ? ` · ${tail}` : ""}`, "gz-what"], [(z.path || []).slice(-2).join(" › ") || "(맨 위)", "lk-place"],
      [`${oneLine(z.first || "") || "(글 없음)"}${(z.ids || []).length > 1 ? ` — 블록 ${nf(z.ids.length)}` : ""}`, "gt-text"], [src, "gz-src", SRC_HELP]], z.ids);
    if (L.stage != null) tr.dataset.znStage = L.stage;
    if (L.year != null) tr.dataset.znYear = L.year;
  };
  const putRow = (tb, a, who = "") => row(tb, [[`넣은 내용 — ${[who, ZN_KIND[a.kind] || a.kind || ""].filter(Boolean).join(" · ")}`, "gz-what gz-put-row"], [`「${a.name || ""}」${a.at ? ` · ${znWhen(a.at)}` : ""}`, "lk-place"],
    [`${(a.ids || []).length ? `블록·칸 ${nf(a.ids.length)}` : "지금 문서에 남아 있지 않음"}${a.gone ? ` · 없어진 것 ${nf(a.gone)}` : ""}`, "gt-text"], [a.legacy ? "옛 기록" : "", "gz-src", a.legacy ? "출처를 따로 적기 전의 넣은 기록 — 기관은 지금의 반영할 기관으로 어림한 것" : ""]], a.ids);
  const HEAD = ["구역 · 넣은 내용", "자리", "글", "근거"];
  const none = (tb, text) => { const tr = el("tr"), td = hCell(tr, text); td.colSpan = HEAD.length; tb.append(tr); };
  const check = dims.includes("org") ? zs.filter((z) => (z.label || {}).orgKind === "conflict") : [];
  const rest = zs.filter((z) => !check.includes(z));
  let groups = 0;

  if (axis === "org") { // 기관마다 — 구역 + 그 기관 문서에서 넣은 내용
    const zk = (z) => { const L = z.label || {}; return L.orgKind === "org" && L.org ? L.org : L.orgKind === "unknown" ? "?" : "-"; };
    const pk = (a) => ((a.orgs || []).length ? a.orgs : ["?"]);
    const extra = [...new Set(origins.flatMap(pk))].filter((k) => k !== "?" && !org.has(k));
    const keys = [...(D.orgs || []).map((o) => o.key), ...extra, ...(rest.some((z) => zk(z) === "?") || origins.some((a) => pk(a).includes("?")) ? ["?"] : []), ...(rest.some((z) => zk(z) === "-") ? ["-"] : [])];
    for (const k of keys) {
      const o = k === "-" ? { i: "u", name: "공통 자리(기관 없음)", role: "" } : org.of(k === "?" ? null : k, k === "?" ? "unknown" : "org");
      const mine = rest.filter((z) => zk(z) === k), puts = k === "-" ? [] : origins.filter((a) => pk(a).includes(k));
      const cap = capEl(k, `${o.name}${o.role ? `(${ZN_ROLE[o.role] || o.role})` : ""} — 구역 ${nf(mine.length)}${k === "-" ? "" : ` · 넣은 내용 ${nf(puts.filter((a) => (a.ids || []).length).length)}`}`, o.i);
      if (k !== "-") cap.dataset.org = k;
      const [tbl, tb] = table(HEAD);
      for (const z of mine) zoneRow(tb, z, o.name);
      for (const a of puts) putRow(tb, a);
      if (!mine.length && !puts.length) none(tb, "구역도 넣은 내용도 없습니다");
      body.append(tbl);
      groups += 1;
    }
  } else if (axis) { // 차년도(없으면 단계)마다
    const f = axis, vals = [...new Set(rest.map((z) => (z.label || {})[f]).filter((v) => v != null))].sort((a, b) => a - b);
    for (const v of [...vals, ...(rest.some((z) => (z.label || {})[f] == null) ? [null] : [])]) {
      const name = v == null ? `${ZN_DIM_NAME[f]} 없음` : f === "year" ? znYearName(v, stages) : `${v}단계`, mine = rest.filter((z) => ((z.label || {})[f] == null ? null : (z.label || {})[f]) === v);
      capEl(v == null ? "-" : `${f}:${v}`, `${name} — 구역 ${nf(mine.length)}`, v == null ? "u" : String(v % ZN_COLORS));
      const [tbl, tb] = table(HEAD);
      for (const z of mine) zoneRow(tb, z, name);
      body.append(tbl);
      groups += 1;
    }
  }
  if (axis !== "org" && origins.length) { // 기관을 안 켰으면 넣은 내용은 따로 한 묶음
    capEl("@puts", `넣은 내용 — ${nf(origins.filter((a) => (a.ids || []).length).length)}곳`);
    const [tbl, tb] = table(HEAD);
    for (const a of origins) putRow(tb, a, (a.orgs || []).map((k) => org.of(k, "org").name).join("·") || "기관 미지정");
    body.append(tbl);
    groups += 1;
  }
  if (marks.length) { // 지정 — 값 · 블록 수 · 없어진 수 · 근거(사람 / LLM) · 메모(LLM 이 지정한 것은 그 까닭) · 「유효하지 않음」 · 줄마다 「해제」 · 묶음 머리에 「LLM 지정 모두 해제」
    const bad = marks.filter((m) => (m.invalid || []).length).length, byLlm = marks.filter((m) => m.by === "llm").length;
    const cap = capEl("@marks", "");
    cap.append(el("span", null, `지정 — ${nf(marks.length)}${byLlm ? `(LLM ${nf(byLlm)})` : ""}${bad ? ` · 유효하지 않음 ${nf(bad)}` : ""}`));
    if (byLlm) { // LLM 이 지정한 것이 있을 때만 — 한 번의 검토가 만든 지정을 묶음으로 되돌린다(② §8)
      const all = hBtn("LLM 지정 모두 해제", () => znLlmClear(), { title: `LLM 이 지정한 구역 ${nf(byLlm)}개를 모두 해제합니다(확인 한 번) — 사람이 지정한 것은 그대로` });
      all.dataset.zones = "llm-clear";
      cap.classList.add("zn-cap-acts");
      cap.append(all);
    }
    const [tbl, tb] = table(["지정한 값", "블록", "근거", "메모 · 까닭", ""]);
    for (const m of marks) {
      const inv = (m.invalid || []).map((k) => ZN_DIM_NAME[k] || k), llm = m.by === "llm";
      const tr = row(tb, [[`${znMarkText(m.label, D)}${inv.length ? ` · 유효하지 않음(${inv.join("·")})` : ""}`, "gz-what" + (inv.length ? " gz-bad" : ""), inv.length ? "지정한 값이 지금 프로젝트 구성에 없습니다 — 그 기준은 자동으로 읽은 값으로 보입니다(다른 값으로 옮기지 않습니다)" : ""],
        [`${(m.ids || []).length ? `블록 ${nf(m.ids.length)}` : "지금 문서에 남아 있지 않음"}${m.gone ? ` · 없어진 것 ${nf(m.gone)}` : ""}`, "lk-place"],
        [llm ? "LLM" : "사람", "gz-src" + (llm ? " gz-by-llm" : ""), llm ? "LLM 검토가 지정한 구역 — 메모 칸이 그 까닭입니다" : "사람이 지정한 구역(문서에서 오른쪽 단추 「구역 지정…」)"], [m.note || "", "gt-text"]], m.ids);
      tr.dataset.znBy = llm ? "llm" : "user";
      const td = el("td", "gz-act"), off = hBtn("해제", (ev) => { ev.stopPropagation(); znMarkDelete(m.id); }, { title: "이 지정을 해제합니다 — 그 블록은 자동으로 읽은 값으로 보입니다" });
      off.dataset.zones = "unmark";
      td.append(off);
      tr.append(td);
    }
    body.append(tbl);
    groups += 1;
  }
  if (check.length) { // 기관 확인 필요 — 읽은 근거가 서로 다른 구역(공통·모름과 묶지 않는다)
    capEl("@check", `기관 확인 필요 — 구역 ${nf(check.length)}`, "u");
    const [tbl, tb] = table(HEAD);
    for (const z of check) zoneRow(tb, z, "기관 확인 필요");
    body.append(tbl);
    groups += 1;
  }
  const reasons = D.reasons || [];
  if (reasons.includes("noValues")) body.prepend(el("p", "hnote pad","프로젝트 구성 값이 없어 구역을 셀 수 없습니다 — 「프로젝트 구성」 에서 정하세요"));
  else if (reasons.includes("unsupportedForm")) body.prepend(el("p", "hnote pad","이 문서 형식에는 편집 구역이 없습니다(hwpx 문서만)"));
  else if (!dims.length) body.prepend(el("p", "hnote pad","「작업 개요」 의 「편집 구역」 에서 기관·단계·차년도를 켜면 그 값의 구역이 여기에 나옵니다"));
  else if (!groups) body.append(el("p", "hnote pad","구역을 찾지 못했습니다"));
  foot.append(el("span", "muted", "넣은 내용 = 기관 문서에서 넣은 기록 가운데 지금 문서에 남은 것(실행 취소·지움으로 없어지면 빠집니다) · 지정 = 문서에서 오른쪽 단추 「구역 지정…」"),
    hBtn("다시 읽기", () => zonesLoad(true), { disabled: Z.loading }), hBtn("닫기", () => headsColClose()));
  if (want) {
    const m = /^(stage|year):(\d+)$/.exec(want);
    const to = body.querySelector(`.gz-cap[data-zn-group="${CSS.escape(want)}"]`) || (m ? body.querySelector(`tr[data-zn-${m[1]}="${m[2]}"]`) : null);
    if (to) to.scrollIntoView({ block: "start" });
  } else if (keep) $("headsDlgBody").scrollTop = top;
}
