"use strict";
// 단계별 실행 — 고른 단계만 차례로(spec_헤딩_추출 ② §7 「실행 메뉴는 머리에」 「고른 것만 차례로」).
// 2026-11-17 사용자(「단계별 실행 ▾」 메뉴 · 진행 줄 그림 — 규칙 보강을 돌린 뒤 헤딩 판정이 도는 중 · 표 판정은 아직) "단계별 실행은 여기에서 클릭한 다음에 클릭한 것들만 실행할 수 있도록 해줘.
// 검토도 그렇고 불필요하게 한개씩 하지 말고".
// 전에는 메뉴 항목을 누르면 그 단계 하나가 바로 돌았다 — 셋을 돌리려면 하나가 끝나기를 기다렸다 메뉴를 다시 열어야 했고, LLM 항목은 확인 창도 하나씩이었다.
// 이제 메뉴는 **고르기 목록**이다: 항목을 눌러 표시(✓)하고 「고른 n개 실행」 을 누르면 **고른 것만** 진행 줄의 차례(스크립트 문단·라벨 → 헤딩 그래프 → 표 구조 → LLM 규칙 보강 → 헤딩 판정 → 표 판정)로 하나씩 돌린다.
// 확인 창은 한 번(유료 LLM 단계가 있을 때 — 고른 단계와 그 어림) · 스크립트만 골랐으면 묻지 않는다(전과 같다).
// 새 실행 길을 만들지 않는다 — 단계마다 app.js headsStart(단계, LLM)(POST …/headings — 추출·설정의 단계 카드와 같은 끝점)를 부르고, 그 작업이 끝나기를 기다렸다 다음을 시작한다.
// 멈추는 곳(남기고 알린다 — 실패로도 「끝남」 으로도 뭉개지 않는다): 단계 실패 · LLM 이 답을 못 함(스크립트로 대신함 — 뒤 LLM 단계도 같을 것이라 돌리지 않는다) · 「멈추기」(지금 단계가 끝나면) ·
// 다른 문서를 엶 · 단계를 시작하지 못함. 끝나면 한 것 · 멈춘 까닭 · 돌리지 않은 것을 알린다(알림 + 단추 title 의 「지난 단계별 실행」).
// 실행은 시작한 문서(id · epoch)에 못 박는다 — 그 사이 다른 문서를 열면 남은 단계를 시작하지 않는다(돌던 단계는 서버에서 끝까지 돈다).
// 도는 동안: 단추는 「단계별 실행 2/3 ▾」 · 메뉴는 차례(끝남 · 도는 중 · 기다림)와 「멈추기」 · 진행 줄의 기다리는 칸은 점선 동그라미 · 에이전트 보기의 진행 카드(agwRunning kind headsPick).
// 부르는 곳: app.js headsRunMenu(headsPickBind — 「헤딩 추출」·「테이블」 탭 상태 줄의 단추) · headsProgLine(headsPickMarks) · heads_run_all.js(headsPickRunning — 「전체 실행」 을 끈다) · doc_agent_work.js agwRunning.
// 기대는 것: app.js(state · heads · ctx · ctxMenu · ctxClose · el · nf · toast · llmName · headsStart(시작한 작업을 돌려준다) · headsPoll · headsLlmReady · headsSource · headsProgRules · headsProgJudge ·
// headsRulesFrom · headsRunOpen · showTab) · heads_run_all.js(headsAllRunning · hraSync) · doc_status.js(dsLlmStop · docStatusPing) · heading_llm_diff.js(llmDiffOpen).
const HRP = { run: null, last: null, pick: new Set(), pickId: null, ui: null, watching: false };
// run = 도는 실행 {id, epoch, t0, steps[{…HRP_STEPS, state, msg}], i(지금 차례), stop, note} | null · last = 지난 실행 {id, text} · pick = 메뉴에서 고른 단계 키(문서마다) · ui = 열려 있는 메뉴의 요소
const HRP_STEPS = [ // 도는 차례 = 진행 줄의 차례(스크립트 → LLM). LLM 단계는 그 단계의 스크립트 초안을 스스로 뽑는다 — 같은 단계의 스크립트를 함께 골라도 된다(고른 그대로 돈다)
  { key: "s1", stage: 1, llm: false, name: "스크립트 — 문단·라벨 다시 추출", short: "스크립트 문단·라벨", tip: "스크립트로 1단계를 다시 뽑습니다(LLM 없음 · 1~2초)" },
  { key: "s2", stage: 2, llm: false, name: "스크립트 — 헤딩 그래프 만들기", short: "스크립트 헤딩 그래프", tip: "LLM 없이 스크립트로 헤딩 그래프를 만듭니다 — 지금 결과가 LLM 판정을 거친 것이면 스크립트 결과로 바뀝니다" },
  { key: "s3", stage: 3, llm: false, name: "스크립트 — 표 구조 만들기", short: "스크립트 표 구조", tip: "LLM 없이 음영·굵게·값 꼴로 표 구조 초안을 만듭니다(1초 안팎) — 지금 결과가 LLM 판정을 거친 것이면 스크립트 결과로 바뀝니다" },
  { key: "l1", stage: 1, llm: true, name: "LLM — 규칙 보강", short: "LLM 규칙 보강", tip: "스크립트가 판정하지 못한 첫머리 묶음(못 맞춤·충돌)을 LLM 에 보내 규칙식을 제안받고 검증을 통과한 것만 저장합니다(유료)" },
  { key: "l2", stage: 2, llm: true, name: "LLM — 헤딩 판정(헤딩 그래프) → 서식 계획", short: "LLM 헤딩 판정 · 서식 계획", tip: "헤딩 그래프를 LLM 이 판정하고, 이어서 서식이 여러 가지인 템플릿마다 서식 정리 계획을 받습니다(유료 · 몇 분 · 계획만 — 문서는 바뀌지 않습니다)" },
  { key: "l3", stage: 3, llm: true, name: "LLM — 표 판정(표 구조)", short: "LLM 표 판정", tip: "표 묶음마다 서브 테이블·헤더 행/열·칸 역할을 LLM 이 칸의 값을 보고 판정합니다(유료 · 수 분)" },
];
const HRP_T0 = new WeakMap(); // 진행 줄 칸 → 그 칸의 제 title(headsPickMarks)
const HRP_STATE = { wait: "기다림", running: "도는 중", done: "끝남", skip: "건너뜀", failed: "실패", miss: "LLM 답 없음" };
const HRP_GONE = "다른 문서를 열어 멈췄습니다 — 돌던 단계는 앞 문서에서 끝까지 돌고, 남은 단계는 시작하지 않았습니다";
const HRP_STOP = "멈추기를 눌러 멈췄습니다";
const hrpMine = () => (HRP.run && HRP.run.id === state.id ? HRP.run : null);
const hrpLive = (R) => HRP.run === R && state.id === R.id && state.epoch === R.epoch;
const hrpWait = (ms) => new Promise((res) => setTimeout(res, ms));
const hrpStep = (key) => HRP_STEPS.find((s) => s.key === key);

function hrpLeft(v = heads.view) { // 스크립트가 판정하지 못한 첫머리 묶음(못 맞춤 + 충돌) 수
  const sm = (v && v.stage1 && v.stage1.summary) || {};
  return (sm.unmatchedGroups || 0) + (sm.conflicts || 0);
}
function hrpOff(s, v = heads.view) { // 그 단계를 지금 못 돌리는 까닭 | "" — 추출·설정 단계 카드의 단추와 같은 조건(1단계 결과 없음 · 규칙 보강은 묶음이 없으면)
  if ((s.stage > 1 || s.llm) && !(v && v.stage1)) return "1단계(문단·라벨) 결과가 없습니다 — 「문단·라벨 다시 추출」 을 먼저 돌리세요";
  if (s.key === "l1" && !hrpLeft(v)) return "보강할 묶음(못 맞춤·충돌)이 없습니다 — 스크립트가 모든 첫머리를 판정했습니다";
  return "";
}
function hrpBusy() { // 다른 헤딩 작업이 도는 중인가 — 도는 작업 · 「전체 실행」(그 단계 사이에도) · 다른 문서에서 시작한 단계별 실행(곧 끝난다)
  const job = (heads.view || {}).job;
  return !!(job && job.status === "running") || (typeof headsAllRunning === "function" && !!headsAllRunning()) || (!!HRP.run && !hrpMine());
}
function hrpLabel(s, v = heads.view) { // 메뉴 항목의 글 — 전의 메뉴와 같은 이름
  if (!s.llm) return s.name;
  if (s.key !== "l1") return `${s.name} · 유료`;
  const left = hrpLeft(v);
  return `${s.name} · ${left ? `남은 ${nf(left)}묶음` : "할 것 없음"} · 유료`;
}

// ---- 단추(상태 줄 끝 「단계별 실행 ▾」 — app.js headsRunMenu 가 요약을 그릴 때마다 새로 만든다 · 도는 동안은 「단계별 실행 2/3 ▾」)
function headsPickBind(b, opt) { // opt = {stages[보일 단계 — 「테이블」 탭은 [3]], detail()(「추출·설정에서 자세히」)}
  b.onclick = () => hrpOpen(b, opt);
  hrpBtnDraw(b);
}
function hrpBtnDraw(b) {
  const R = hrpMine(), n = R ? R.steps.length : 0;
  const last = HRP.last && HRP.last.id === state.id ? `\n지난 단계별 실행: ${HRP.last.text}` : "";
  b.replaceChildren("단계별", el("span", "hrun-word", " 실행"), R ? ` ${Math.min(R.i + 1, n)}/${n}` : "", " ▾"); // 좁은 패널(370px 아래)에서는 「실행」 을 감춘다(heading-panels.css)
  b.classList.toggle("on", !!R);
  b.title = R ? `단계별 실행 중 — ${R.note}\n누르면 차례와 「멈추기」 를 봅니다`
    : `단계별 실행 — 돌릴 단계를 여러 개 고른 뒤 「고른 것 실행」 을 누르면 고른 것만 차례로 돌립니다(스크립트 무료 · LLM 유료 — 확인 창은 한 번)${last}`;
}
function hrpSync() { // 실행의 시작 · 끝 · 차례가 바뀜 — 그려 둔 단추 · 열려 있는 메뉴 · 진행 줄의 기다림 표시 · 「전체 실행」 단추를 그 자리에서 다시
  for (const b of document.querySelectorAll(".hrun-menu")) hrpBtnDraw(b);
  for (const box of document.querySelectorAll(":is(#headsOverview, #tablesOverview) .hprog")) headsPickMarks(box);
  hrpMenuSync();
  if (typeof hraSync === "function") hraSync();
}

// ---- 진행 줄의 기다림 표시 — 고른 단계 가운데 아직 차례가 안 온 칸(점선 동그라미 · title 에 몇 번째). app.js headsProgLine 이 줄을 그릴 때마다 · hrpSync
function headsPickMarks(box) {
  const cells = [...box.querySelectorAll(".hprog-step")].filter((b) => !b.dataset.tpb), n = cells.length / 2; // 스크립트 줄 n칸 · LLM 줄 n칸(셋째 층 「조정」 의 칸은 뺀다) — 한 칸이면 「테이블」 탭(3단계)
  if (n !== 1 && n !== 3) return;
  const R = hrpMine(), stages = n === 1 ? [3] : [1, 2, 3];
  cells.forEach((b, i) => {
    const key = `${i < n ? "s" : "l"}${stages[i % n]}`, at = R ? R.steps.findIndex((s) => s.key === key) : -1, wait = at >= 0 && R.steps[at].state === "wait";
    if (!HRP_T0.has(b)) HRP_T0.set(b, b.title); // 칸의 제 title(app.js 가 그릴 때 정한 것) — 기다림 글은 그 뒤에 붙였다 뗀다
    b.toggleAttribute("data-queued", wait);
    b.title = wait ? `${HRP_T0.get(b)}\n— 단계별 실행: 기다리는 중(${nf(R.steps.length)}개 가운데 ${nf(at + 1)}번째)` : HRP_T0.get(b);
  });
}

// ---- 메뉴(공용 ctx 메뉴 상자를 빌린다 — 바깥 누름 · 스크롤 · Esc 로 닫힘 · ↑↓ 로 옮김: app.js ctxMenu). 항목을 눌러도 닫히지 않는다(고르기) — 닫는 것은 「고른 n개 실행」 · 「추출·설정에서 자세히」 · 바깥
function hrpWatch(m) {
  if (HRP.watching) return;
  HRP.watching = true;
  new MutationObserver(() => { if (m.hidden && m.dataset.by === "hrp") { delete m.dataset.by; HRP.ui = null; } }).observe(m, { attributes: true, attributeFilter: ["hidden"] });
}
function hrpOpen(b, opt) {
  const stages = opt.stages || [1, 2, 3], steps = HRP_STEPS.filter((s) => stages.includes(s.stage)), m = ctxMenu();
  if (HRP.pickId !== state.id) { HRP.pick.clear(); HRP.pickId = state.id; } // 고른 것은 문서마다
  for (const k of [...HRP.pick]) if (!steps.some((s) => s.key === k)) HRP.pick.delete(k); // 이 메뉴에 없는 단계(다른 탭에서 고른 것)는 뺀다 — 보이지 않는 것을 돌리지 않는다
  hrpWatch(m);
  m.textContent = "";
  m.dataset.by = "hrp";
  const ui = HRP.ui = { opt, rows: new Map(), go: null, detail: null };
  const btn = (cls, role, run) => { const x = el("button", cls); x.type = "button"; x.setAttribute("role", role); x.onclick = run; return x; };
  steps.forEach((s, i) => {
    if (i && s.llm && !steps[i - 1].llm) m.append(el("hr"));
    const row = btn("hrp-row", "menuitemcheckbox", () => hrpToggle(s.key));
    row.dataset.hrp = s.key;
    row.append(el("span", "hrp-box"), el("span", "hrp-name"), el("span", "hrp-note"));
    ui.rows.set(s.key, row);
    m.append(row);
  });
  ui.go = btn("hrp-go", "menuitem", () => hrpGo());
  ui.detail = btn("hrp-detail", "menuitem", () => { ctxClose(); opt.detail(); });
  m.append(el("hr"), ui.go, el("hr"), ui.detail);
  hrpMenuSync();
  m.hidden = false;
  const R = b.getBoundingClientRect();
  m.style.left = `${Math.max(8, Math.min(R.left, innerWidth - m.offsetWidth - 8))}px`;
  m.style.top = `${Math.max(8, Math.min(R.bottom + 2, innerHeight - m.offsetHeight - 8))}px`;
  const first = m.querySelector("button:not([disabled])");
  if (first) first.focus({ preventScroll: true });
}
function hrpMenuSync() { // 열려 있는 메뉴를 지금 상태로 — 고른 것 · 꺼짐 · 도는 실행의 차례 · 아래 단추의 글
  const ui = HRP.ui, m = typeof ctx === "object" ? ctx.menu : null;
  if (!ui || !m || m.dataset.by !== "hrp") return;
  const v = heads.view, R = hrpMine(), busy = !R && hrpBusy();
  for (const [key, row] of ui.rows) {
    const s = hrpStep(key), q = R ? R.steps.find((x) => x.key === key) : null, off = hrpOff(s, v);
    if (!R && off) HRP.pick.delete(key);
    row.setAttribute("aria-checked", String(R ? !!q : HRP.pick.has(key)));
    row.dataset.state = q ? q.state : "";
    row.disabled = !!R || busy || !!off;
    row.querySelector(".hrp-name").textContent = hrpLabel(s, v);
    row.querySelector(".hrp-note").textContent = q ? HRP_STATE[q.state] : "";
    row.title = q ? `${HRP_STATE[q.state]}${q.msg ? ` — ${q.msg}` : ""}` : off || (busy ? "다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 고르세요" : `${s.tip}\n누르면 고릅니다(다시 누르면 뺍니다)`);
  }
  const n = [...ui.rows.keys()].filter((k) => HRP.pick.has(k)).length, go = ui.go;
  go.classList.toggle("stop", !!R);
  if (R) {
    const rest = R.steps.filter((s) => s.state === "wait").length;
    go.textContent = R.stop ? "멈추는 중…" : "멈추기";
    go.disabled = R.stop;
    go.title = `지금 도는 단계가 끝나면 멈춥니다${rest ? ` — 기다리는 ${nf(rest)}개는 돌리지 않습니다` : ""}(끝난 단계의 결과는 남습니다)`;
  } else {
    go.textContent = busy ? "다른 헤딩 작업이 도는 중" : n ? `고른 ${nf(n)}개 실행` : "돌릴 단계를 고르세요";
    go.disabled = busy || !n;
    go.title = busy ? "도는 작업이 끝난 뒤 고르세요" : n ? `고른 것만 이 차례로 하나씩 돌립니다: ${HRP_STEPS.filter((s) => HRP.pick.has(s.key) && ui.rows.has(s.key)).map((s) => s.short).join(" → ")}`
      + "\n유료 LLM 단계가 있으면 확인 창을 한 번 보입니다 · 한 단계가 실패하면 뒤는 돌리지 않고 남깁니다" : "위에서 돌릴 단계를 눌러 고르세요(여러 개) — 고른 것만 차례로 돌립니다";
  }
  ui.detail.textContent = R || busy ? "추출·설정에서 진행 보기" : "추출·설정에서 자세히";
}
function hrpToggle(key) {
  if (hrpMine() || hrpBusy() || hrpOff(hrpStep(key))) return;
  if (!HRP.pick.delete(key)) HRP.pick.add(key);
  hrpMenuSync();
}
function hrpGo() {
  if (hrpMine()) { hrpStop(); return; } // 도는 중 — 「멈추기」(메뉴는 열어 둔다: 「멈추는 중…」)
  const keys = HRP.ui ? HRP_STEPS.filter((s) => HRP.pick.has(s.key) && HRP.ui.rows.has(s.key)).map((s) => s.key) : [];
  if (!keys.length) return;
  ctxClose();
  headsPickRun(keys);
}

function hrpStop() { // 「멈추기」 — 지금 도는 단계가 끝나면 멈춘다(바로 끊지 않는다)
  const R = HRP.run;
  if (!R || R.stop) return;
  R.stop = true;
  hrpSync();
  const job = (heads.view || {}).job, rest = R.steps.filter((s) => s.state === "wait").length;
  if (job && job.status === "running" && job.chain && typeof dsLlmStop === "function") dsLlmStop(); // 도는 이어 돌리기(헤딩 판정 → 서식 계획) — DELETE …/analysis/llm(알림도 그 함수가)
  else toast(`단계별 실행을 멈춥니다 — 지금 도는 단계가 끝나면 멈춥니다${rest ? ` · 기다리는 ${nf(rest)}개는 돌리지 않습니다` : ""}`);
}

function headsPickRunning() { // 도는 단계별 실행 | null — 에이전트 보기의 진행 카드(doc_agent_work.js agwRunning) · 「전체 실행」 을 끄는 데(heads_run_all.js)
  const R = hrpMine();
  return R ? { label: `단계별 실행 — 고른 ${nf(R.steps.length)}개를 차례로`, note: R.note, t0: R.t0, stopping: R.stop, stop: () => hrpStop() } : null;
}

// ---- 확인 창(유료 LLM 단계가 있을 때 한 번) — 고른 단계 · 차례 · 어림
function hrpAsk(steps, st) {
  const v = heads.view, sm = (v && v.stage1 && v.stage1.summary) || {}, left = hrpLeft(v), has = (k) => steps.some((s) => s.key === k);
  const judged = (k) => { const src = typeof headsSource === "function" ? headsSource(v, k) : null; return !!(src && src.llm); };
  const more = {
    s2: !has("l2") && judged(2) ? "지금 헤딩 그래프는 LLM 판정을 거친 결과입니다 — 스크립트 결과로 바뀝니다" : "",
    s3: !has("l3") && judged(3) ? "지금 표 구조는 LLM 판정을 거친 결과입니다 — 스크립트 결과로 바뀝니다" : "",
    l1: `못 맞춤 ${nf(sm.unmatchedGroups || 0)}묶음 · 충돌 ${nf(sm.conflicts || 0)}묶음을 보내 규칙식을 제안받고, 검증을 통과한 것만 후보 규칙으로 저장합니다(보통 $0.2~0.3 · 40초 안팎)`,
    l2: "헤딩 유형 · 본문 구간을 여러 번 물어 판정하고, 끝나면 이어서 서식이 여러 가지인 템플릿마다 서식 정리 계획을 받습니다(계획만 — 문서는 바뀌지 않습니다 · 연구개발계획서 양식 기준 약 4분 · $3 안팎 + 서식 계획)"
      + (left && !has("l1") ? `\n     스크립트가 판정하지 못한 첫머리 ${nf(left)}묶음(못 맞춤·충돌)의 규칙 보강을 먼저 합니다(아직 묻지 않은 묶음만 · $0.2~0.3 더)` : ""),
    l3: "표를 묶음(칸 500개 안팎)마다 보내 서브 테이블·헤더 행/열·칸 역할을 판정받습니다(연구개발계획서 양식 기준 10여 번 · 수 분)",
  };
  const rows = [steps.length > 1 ? `단계별 실행 — 고른 ${nf(steps.length)}개를 이 차례로 하나씩 돌립니다(앞 단계가 끝나면 다음).` : "단계별 실행 — 고른 단계를 돌립니다.", ""];
  steps.forEach((s, i) => {
    rows.push(`${i + 1}. ${s.name} · ${s.llm ? "유료" : "무료"}`);
    if (more[s.key]) rows.push(`     ${more[s.key]}`);
  });
  const paid = steps.filter((s) => s.llm).length;
  rows.push("", `유료 LLM 단계 ${nf(paid)}개 — ${llmName(st)} 에 보냅니다.`
    + (steps.length > 1 ? " 한 단계가 실패하거나 LLM 이 답을 못 하면 뒤 단계는 돌리지 않고 남깁니다(도는 동안 메뉴의 「멈추기」 로도 멈춥니다)." : "") + " 계속할까요?");
  return rows.join("\n");
}

// ---- 실행
async function headsPickRun(keys) {
  if (HRP.run || !state.id) return;
  const id = state.id, epoch = state.epoch;
  const steps = HRP_STEPS.filter((s) => keys.includes(s.key) && !hrpOff(s)).map((s) => ({ ...s, state: "wait", msg: "" }));
  if (!steps.length) return;
  const busy = () => { if (!hrpBusy()) return false; toast("다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요"); return true; };
  if (busy()) return;
  if (steps.some((s) => s.llm)) { // 유료 — 확인 창은 한 번(전에는 단계마다 하나씩)
    const st = await headsLlmReady(); // LLM 연결이 없으면 알림은 그 함수가(스크립트만 돌리려면 LLM 단계를 빼고 다시)
    if (!st || epoch !== state.epoch || HRP.run || !confirm(hrpAsk(steps, st)) || epoch !== state.epoch || HRP.run || busy()) return;
  }
  HRP.pick.clear();
  const R = HRP.run = { id, epoch, t0: Date.now(), steps, i: 0, stop: false, note: "시작" };
  hrpSync();
  let why;
  try { why = await hrpLoop(R); } catch (e) { why = `오류 — ${e.message}`; }
  HRP.run = null;
  const text = hrpDone(R, why), bad = R.steps.find((s) => s.state === "failed" || s.state === "miss"), llm = [...R.steps].reverse().find((s) => s.llm && s.state === "done");
  HRP.last = { id, text };
  hrpSync();
  if (typeof docStatusPing === "function") docStatusPing();
  const here = state.id === id && state.epoch === epoch;
  toast(text, !!why && why !== HRP_STOP, !here ? null
    : bad ? { label: "실행 내역 보기", run: () => { if (typeof showTab === "function") showTab("Heads"); headsRunOpen(bad.stage); } }
      : llm && typeof llmDiffOpen === "function" ? { label: "LLM 이 바꾼 것 보기", run: () => llmDiffOpen(llm.stage) } : null);
}

async function hrpLoop(R) { // 고른 단계를 차례로 → 멈춘 까닭("" = 끝까지 감)
  for (R.i = 0; R.i < R.steps.length; R.i += 1) {
    const s = R.steps[R.i], no = `${R.i + 1}/${R.steps.length}`;
    let job = null;
    for (let t = 0; t < 3 && !job; t += 1) { // 시작 — 다른 헤딩 작업(문서가 바뀐 뒤 저절로 도는 1단계 다시 추출 …)이 끼어들었으면 그것이 끝난 뒤 다시(세 번까지)
      if (t) await hrpWait(1000);
      R.note = `${no} · ${s.short} — 다른 헤딩 작업이 끝나기를 기다리는 중`;
      const free = await hrpIdle(R, () => hrpSync());
      if (!hrpLive(R)) return HRP_GONE;
      if (R.stop) return HRP_STOP;
      if (!free) return "다른 헤딩 작업의 진행을 읽지 못해 멈췄습니다 — 진행 줄을 확인한 뒤 남은 단계를 다시 고르세요";
      const off = hrpOff(s); // 앞 단계의 결과로 달라질 수 있다 — 시작 직전에 다시 본다
      if (off) {
        if (s.key !== "l1" || !heads.view || !heads.view.stage1) { s.state = "failed"; s.msg = off; return `「${s.short}」 을 돌리지 못했습니다 — ${off}`; }
        s.state = "skip"; s.msg = "할 것 없음 — 판정하지 못한 묶음이 없습니다"; // 규칙 보강 — 앞 단계가 다시 뽑아 묶음이 없어졌다
        break;
      }
      s.state = "running";
      R.note = `${no} · ${s.name}`;
      hrpSync();
      job = await headsStart(s.stage, s.llm); // 못 시작하면 null(까닭은 그 함수가 알렸다 — 이미 도는 작업 409 …)
      if (!hrpLive(R)) return HRP_GONE;
    }
    if (s.state === "skip") { hrpSync(); continue; }
    if (!job) { s.state = "failed"; s.msg = "시작하지 못함"; return `「${s.short}」 을 시작하지 못했습니다`; }
    const end = await hrpJob(R, job.started);
    if (!hrpLive(R)) return HRP_GONE;
    if (!end) { s.state = "failed"; s.msg = "도는 작업을 놓침"; return `「${s.short}」 — 도는 작업을 놓쳤습니다(서버가 다시 시작됐을 수 있습니다): 진행 줄을 확인한 뒤 남은 단계를 다시 고르세요`; }
    if (end.status === "failed") { s.state = "failed"; s.msg = end.error || "까닭 모름"; return `「${s.short}」 실패 — ${end.error || "까닭 모름"}`; }
    const miss = hrpMiss(s);
    if (miss) { s.state = "miss"; s.msg = miss; return `「${s.short}」 — ${miss}`; }
    s.state = "done";
    if (end.stopping && end.chain) s.msg = "멈추기 — 헤딩 판정 뒤의 서식 계획은 받지 않았거나 일부만 받았습니다(진행 줄 「조정」 의 「계획 받기」)";
    hrpSync();
    if (R.stop || end.stopping) return HRP_STOP; // 이름 줄 · 에이전트 카드의 「멈춤」 으로 그 작업을 멈췄어도 뒤 단계를 잇지 않는다
  }
  return "";
}

function hrpMiss(s) { // LLM 단계가 끝났는데 LLM 이 답을 못 했나(호출이 모두 실패 · 스크립트로 대신함) → 까닭 | "" — 진행 줄의 그 칸(!)과 같은 판정
  const v = heads.view;
  if (!s.llm || !v) return "";
  const i = s.stage === 1 ? headsProgRules(v, null) : headsProgJudge(v, s.stage, null);
  if (i.state !== "failed") return "";
  const err = s.stage === 1 ? (headsRulesFrom(v) || {}).error : ((v[`stage${s.stage}`] || {}).llm || {}).error;
  return `LLM 이 답을 못 했습니다${s.stage > 1 ? "(스크립트 결과로 남음)" : ""}${err ? `: ${err}` : ""}`;
}

async function hrpIdle(R, tick) { // 도는 헤딩 작업이 없을 때까지 → true | false(다른 문서 · 읽기가 끊긴 채) — 요약은 app.js headsPoll 이 읽어 heads.view 에 둔다
  for (let dead = 0, said = false; ;) {
    if (!hrpLive(R)) return false;
    const j = (heads.view || {}).job;
    if (!(j && j.status === "running")) return true;
    if (!said) { said = true; tick(); } // 기다리게 됐을 때만 「기다리는 중」 을 보인다
    if (R.stop) return true; // 멈추기 — 기다리지 않는다(부른 쪽이 멈춘다)
    if (heads.pollEpoch != null) dead = 0;
    else { if (++dead > 20) return false; headsPoll(); }
    await hrpWait(700);
  }
}

async function hrpJob(R, started) { // 그 헤딩 작업이 끝날 때까지 → 끝난 작업 | null(놓침 · 다른 문서)
  for (let dead = 0; ;) {
    await hrpWait(700);
    if (!hrpLive(R)) return null;
    const j = (heads.view || {}).job, ours = !!j && j.started === started;
    if (ours && j.status !== "running") return j;
    if (heads.pollEpoch != null) { dead = 0; continue; } // 읽는 중
    if (++dead > (ours ? 20 : 3)) return null; // 읽기가 끊긴 채다 — 서버가 세션을 잃었거나 내려갔다
    if (ours) headsPoll(); // 일시 오류로 끊겼으면 다시 잇는다
  }
}

function hrpDone(R, why) { // 끝난 글 — 한 것 · (멈춘 까닭) · 건너뛴 것 · 돌리지 않은 것
  const of = (st) => R.steps.filter((s) => s.state === st), names = (list) => list.map((s) => s.short);
  const did = names(of("done")), rest = names(of("wait")), skip = of("skip"), run = names(of("running")), note = of("done").filter((s) => s.msg).map((s) => s.msg);
  const tail = [did.length ? `한 것: ${did.join(" → ")}` : "", skip.length ? `건너뜀: ${skip.map((s) => `${s.short}(${s.msg})`).join(" · ")}` : "", ...note,
    run.length ? `돌던 단계: ${run.join(" · ")}(끝까지 돕니다)` : "", rest.length ? `돌리지 않은 것: ${rest.join(" · ")} — 「단계별 실행」 에서 다시 고르세요` : ""].filter(Boolean);
  if (why) return `단계별 실행 멈춤 — ${why}${tail.length ? ` · ${tail.join(" · ")}` : ""}`;
  const more = tail.slice(did.length ? 1 : 0); // 「한 것」 은 머리에 적는다
  return `단계별 실행 끝 — ${did.length ? did.join(" → ") : "돌린 것 없음"}${more.length ? ` · ${more.join(" · ")}` : ""}`;
}
