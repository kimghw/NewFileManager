// 에이전트 보기 빈 화면의 「지금 할 수 있는 일」 — 현황 보고 카드 · LLM 검토 실행 카드 · 서식 반영(spec_일반편집 ② §12 「빈 화면 — 지금 할 수 있는 일」).
// 2026-11-16 사용자 "여기 에이전트에서는 아직 헤딩추출과 테이블에 LLM 검토 및 반영이 들어 가지 않았으니 가운데에 그걸 할 수 있다고 메뉴를 넣어줘야지. ..
// 그리고 에이전트에 현재 작업 진행 현황 보고를 사전 질의로 넣어줘." → 답 「스크립트 보고 카드」 · 「실행 카드로 묻고 진행」 · 「빈 화면에 늘」.
//
// 자료는 문서 이름 줄의 분석 상태와 같다(GET /api/docs/{id}/analysis — doc_status.js dsState.main) — 같은 칸은 같은 그리기(진행표의 dsRow · dsSteps).
// 보고 · 실행 카드는 화면에만 둔다(AGENT.local — 저장하지 않음: 「비우기」 · 문서를 바꾸면 사라짐). 실행 카드는 작업 진행 에이전트의 실행 카드와 같은 꼴(doc_agent_work.css .agw-act).
// 기대는 것: doc_agent.js(AGENT · agentIcon · agentDrawTalk · agentDrawStatus) · doc_status.js(dsState · dsDraw · dsRow · DS_FOUR · dsSteps · dsBusy · dsChain · dsLlmRun · dsGo) ·
// doc_agent_work.js(agwTags · agwRunning) · app.js(state · api · el · hBtn · nf · hhmm · toast). 부르는 곳: doc_agent.js agentEmptyEl · agentDrawTalk · doc_status.js dsFetch(agentNextSync).

const agnView = () => (typeof dsState === "object" && state.id && dsState.mainId === state.id ? dsState.main : null);
const agnPlanKey = (v) => JSON.stringify(((v && v.llmPlan) || []).map((p) => [p.key, !!p.run]));

function agnTodo(v = agnView()) { // → {llm: 돌 것(llmPlan 의 run) | null, apply: 반영이 남은 서식 항목 | null} — 도는 LLM 검증·보완이 있으면 llm 은 null(진행 카드가 보인다)
  if (!v) return { llm: null, apply: null };
  const run = (v.llmPlan || []).filter((p) => p.run);
  const f = (v.items || []).find((i) => i.key === "formats");
  return { llm: run.length && !dsChain(v) ? run : null, apply: f && f.state === "done" && f.levels && f.apply && f.apply.state !== "done" ? f : null };
}

// 남은 LLM 단계에 맞는 이름 — 헤딩 · 표가 남았으면 「헤딩·표 LLM 검토」, 서식 정리 계획만 남았으면 그것(문서를 고친 뒤 서식 계획만 다시 남는 때가 있다)
const agnLlmName = (run) => ((run || []).some((p) => p.key === "heads" || p.key === "tables") ? "헤딩·표 LLM 검토" : "서식 정리 계획 받기(LLM)");

function agnItem(icon, label, tag, run, title, cls = "") { // 빈 화면 요청 예시와 같은 꼴의 줄 단추(아이콘 · 글 · 꼬리표 · 화살표)
  const b = hBtn(label, run, { cls: `btn sm ag-example ag-next-item${cls ? ` ${cls}` : ""}`, title });
  b.prepend(agentIcon(icon));
  if (tag) b.append(el("span", "ag-next-tag", tag));
  b.append(agentIcon("arrow"));
  return b;
}

function agnNextButtons(v) { // 남은 일 단추 — 빈 화면 묶음과 보고 카드의 「다음 할 일」 이 같은 것
  const T = agnTodo(v), out = [];
  if (T.llm) out.push(agnItem("spark", agnLlmName(T.llm) === "헤딩·표 LLM 검토" ? "헤딩·표 LLM 검토하기" : agnLlmName(T.llm), "유료", () => agnExecOpen(),
    `돌 것: ${T.llm.map((p) => p.name).join(" · ")}\n누르면 실행 카드로 묻습니다(「진행」 을 눌러야 돎 · 유료 LLM · 몇 분 · 문서는 안 바뀜)`, "paid"));
  const all = T.apply && T.apply.llm && T.apply.llm.planned > 0 && typeof tplPlanGo === "function"; // 받아 둔 계획이 있으면 한 번에 반영하는 자리(헤딩 추출 탭 진행 줄의 「조정」 — tpl_plan_bar.js)
  if (T.apply) out.push(agnItem("format", "서식 반영하기", T.apply.apply.text || "", () => (all ? tplPlanGo() : dsGo("Tidy")),
    `${T.apply.apply.text || ""}\n${all ? "헤딩 추출 탭 진행 줄의 「조정」 으로 갑니다 — 「템플릿 조정」·「서식 조정」 칸을 눌러 계획을 확인하고 「모두 반영」 을 누르면 문서가 바뀝니다(실행 취소 1)" : "「템플릿 서식 정리」 열을 엽니다 — 계획을 골라 적용하면 문서가 바뀝니다(실행 취소 1)"}`));
  return out;
}

function agentNextEl() { // 빈 화면 가운데 「지금 할 수 있는 일」 — 사전 질의(현황 보고) + 아직 안 한 LLM 검토 · 서식 반영
  const box = el("div", "ag-next");
  box.setAttribute("role", "group");
  box.setAttribute("aria-label", "지금 할 수 있는 일");
  box.append(el("p", "ag-next-title", "지금 할 수 있는 일"),
    agnItem("report", "현재 작업 진행 현황 보고", "", () => agnReport(), "분석(헤딩 · 템플릿 · 서식 · 표) · 편집 · 서식 관리자가 어디까지 됐는지 대화에 보고합니다(스크립트 · 무료)"),
    ...agnNextButtons(agnView()));
  return box;
}

// ---------------------------------------------------------------- 현황 보고 카드(스크립트 — 그때 다시 읽은 분석 상태 · 편집 · 서식 관리자)
async function agnReport() {
  const A = AGENT, id = state.id, epoch = state.epoch;
  if (!id) return;
  const card = { kind: "report", at: Date.now(), loading: true };
  A.local = A.local.filter((c) => c.kind !== "report").concat(card); // 보고는 하나만 — 다시 누르면 새 것으로
  agentDrawTalk(true);
  const [v, lib] = await Promise.all([api(`/api/docs/${id}/analysis`).catch(() => null), api("/api/styles").catch(() => null)]);
  if (A !== AGENT || epoch !== state.epoch || id !== state.id) return;
  if (v && dsState.mainId === id) { dsState.main = v; dsDraw("main"); } // 이름 줄도 같은 자료로
  const mine = lib && Array.isArray(lib.styles) ? lib.styles.filter((s) => (s.source && s.source.work === id) || (s.seenIn || []).some((x) => x && x.work === id)) : null;
  Object.assign(card, { loading: false, view: v, styles: mine, edited: state.edited ? state.edited.size : 0, base: state.base || 0 });
  agentDrawTalk(true);
}

function agnReportEl(c) {
  const card = el("div", "ag-card agw-card ag-report"), head = el("div", "ag-card-head");
  head.append(el("b", null, "현재 작업 진행 현황"), el("span", "ag-report-at", `${hhmm(new Date(c.at))} 기준`));
  card.append(head);
  if (c.loading) { const run = el("div", "ag-run"); run.append(el("span", "ag-spin"), el("span", null, "상태를 읽는 중")); card.append(run); return card; }
  const v = c.view;
  if (!v) card.append(el("p", "hwarn", "분석 상태를 읽지 못했습니다 — 서버가 옛 판이거나 작업 저장이 꺼져 있습니다"));
  else {
    const by = Object.fromEntries((v.items || []).map((i) => [i.key, i]));
    const grid = el("div", "ds-grid ag-report-grid"); // 이름 줄 진행표와 같은 칸(dsRow — 누르면 그 도구)
    grid.append(el("span", "ds-col"), el("span", "ds-col", "스크립트"), el("span", "ds-col", "LLM 검토"), el("span", "ds-col", "문서 반영"));
    for (const [k, n] of DS_FOUR) if (by[k]) grid.append(...dsRow(k, n, by[k]));
    card.append(el("p", "ag-report-sec", "분석 — 스크립트는 올리면 저절로 · LLM 은 단추로"), grid);
    const ch = v.chain;
    if (ch && ch.steps && ch.steps.length) card.append(el("p", "ag-report-sec", dsChain(v) ? `${ch.name || "LLM 검증·보완"} — 도는 중` : `지난 ${ch.name || "LLM 검증·보완"} — ${ch.status === "failed" ? "멈춤(실패)" : "끝남"}`), dsSteps(ch.steps));
  }
  const lines = el("ul", "ag-report-lines");
  lines.append(el("li", null, `편집 — 고친 문단 ${nf(c.edited)}개 · 확정 ${nf(c.base)}번`));
  if (c.styles) {
    const names = c.styles.slice(0, 3).map((s) => `「${s.name}」`).join(" · ");
    lines.append(el("li", null, c.styles.length ? `서식 관리자 — 이 문서에서 저장한 서식 ${nf(c.styles.length)}개 · ${names}${c.styles.length > 3 ? " …" : ""}` : "서식 관리자 — 이 문서에서 저장한 서식 없음"));
  }
  card.append(lines);
  const next = v ? agnNextButtons(v) : [];
  card.append(el("p", "ag-report-sec", next.length ? "다음 할 일" : "남은 LLM 검토 · 서식 반영 없음"));
  if (next.length) { const box = el("div", "ag-examples ag-report-next"); box.append(...next); card.append(box); }
  return card;
}

// ---------------------------------------------------------------- 실행 카드 — 헤딩·표 LLM 검토(= 이름 줄 진행표의 「LLM 검증·보완」 · 유료). 카드는 그 카드가 보인 돌 것 목록에 묶인다
function agnExecOpen() {
  const v = agnView(), T = agnTodo(v);
  if (!T.llm) { toast("지금 돌 LLM 검토가 없습니다 — 이미 했거나 도는 중입니다"); return; }
  AGENT.local = AGENT.local.filter((c) => !(c.kind === "exec" && c.state === "open")).concat({ kind: "exec", state: "open", plan: v.llmPlan, key: agnPlanKey(v) });
  agentDrawTalk(true);
}

async function agnExecGo(c) {
  const A = AGENT, id = state.id, epoch = state.epoch;
  if (c.state !== "open" || c.busy) return;
  c.busy = true;
  agentDrawTalk();
  let v = null;
  try { v = await api(`/api/docs/${id}/analysis`); } catch { v = null; }
  if (A !== AGENT || epoch !== state.epoch) return;
  c.busy = false;
  if (v && dsState.mainId === id) { dsState.main = v; dsDraw("main"); }
  const why = !v ? "분석 상태를 읽지 못했습니다" : dsBusy(v) ? "다른 헤딩 작업이 도는 중입니다" : agnPlanKey(v) !== c.key ? "돌 것이 바뀌었습니다" : "";
  if (why) { // 그 카드가 보인 목록과 다르면 실행하지 않고 다시 묻는다(새 카드)
    Object.assign(c, { state: "stale", outcome: `실행하지 않음 — ${why}` });
    if (v && !dsBusy(v) && agnTodo(v).llm) A.local.push({ kind: "exec", state: "open", plan: v.llmPlan, key: agnPlanKey(v) });
    agentDrawTalk(true);
    return;
  }
  const ok = await dsLlmRun();
  if (A !== AGENT) return;
  Object.assign(c, ok ? { state: "done", outcome: "LLM 검증·보완을 시작했습니다 — 진행은 아래 진행 카드와 이름 줄 진행표" } : { state: "halt", outcome: "멈춤 — 시작하지 못했습니다(까닭은 알림 글)" });
  agentDrawTalk(true);
}

function agnExecEl(c) {
  const card = el("div", "ag-card agw-card agw-act ag-next-exec"), head = el("div", "ag-card-head"), v = agnView();
  card.dataset.state = c.busy ? "running" : c.state;
  head.append(el("b", null, `${agnLlmName((c.plan || []).filter((p) => p.run))} — LLM 검증·보완`), agwTags({ change: "none", paid: true }));
  card.append(head, el("p", "agw-does", "헤딩 · 템플릿(헤딩 그래프 LLM)을 먼저 돌리고, 그 뒤 표(표 구조 LLM)와 서식(템플릿 서식 정리 — 계획만)을 돌립니다. 몇 분 걸리고 문서는 바뀌지 않습니다 — 서식 반영은 계획에서 고른 것만."));
  const ol = el("ol", "ds-plan");
  for (const p of c.plan || []) { const li = el("li", p.run ? "run" : "skip"); li.append(el("span", "ds-step-name", `${p.run ? "돎" : "건너뜀"} · ${p.name}`), el("span", "ds-step-msg", p.why || "")); ol.append(li); }
  card.append(ol);
  if (c.state === "done") { card.append(el("p", "ag-state ok", `실행함 — ${c.outcome}`)); return card; }
  if (c.state === "halt") { card.append(el("p", "ag-state stale", c.outcome)); return card; }
  if (c.state === "stale") { card.append(el("p", "ag-state", c.outcome)); return card; }
  if (c.state === "skipped") { card.append(el("p", "ag-state", "건너뜀")); return card; }
  if (c.busy) { const run = el("div", "ag-run"); run.append(el("span", "ag-spin"), el("span", null, "돌 것을 다시 확인하는 중")); card.append(run); return card; }
  const R = typeof agwRunning === "function" ? agwRunning() : null, busy = !!(v && dsBusy(v)) || !!R || !!AGENT.busy;
  const acts = el("div", "ag-acts");
  const go = hBtn("진행", () => agnExecGo(c), { cls: "btn sm primary", disabled: busy,
    title: busy ? `다른 작업이 도는 중입니다${R ? `(${R.label})` : ""} — 끝난 뒤 누르세요` : "누르면 유료 LLM 호출이 시작됩니다(몇 분 · 문서는 안 바뀜) — 진행은 아래 진행 카드" });
  go.dataset.agn = "go";
  const skip = hBtn("건너뛰기", () => { c.state = "skipped"; agentDrawTalk(); });
  skip.dataset.agn = "skip";
  acts.append(go, skip);
  card.append(acts);
  return card;
}

function agentLocalEls() { // 대화 끝(진행 카드 앞)에 붙는 화면만의 카드 — 보고 · 실행
  return (AGENT.local || []).map((c) => {
    const s = el("section", "ag-turn ag-local");
    s.dataset.local = c.kind;
    s.append(c.kind === "report" ? agnReportEl(c) : agnExecEl(c));
    return s;
  });
}

function agentNextSync() { // 분석 상태가 바뀜(doc_status.js dsFetch) — 빈 화면 묶음 · 실행 카드가 기대는 값이 달라졌을 때만 다시 그린다
  const A = typeof AGENT === "object" ? AGENT : null, E = A && A.el;
  if (!E || !E.root || !E.root.isConnected) return;
  const v = agnView(), T = agnTodo(v);
  const sig = JSON.stringify([!!v, T.llm && T.llm.map((p) => p.key), T.apply && T.apply.apply.text, !!(v && dsBusy(v)), (A.local || []).some((c) => c.kind === "exec" && c.state === "open")]);
  if (sig === A.nextSig) return;
  A.nextSig = sig;
  if (E.talk.querySelector(".ag-next") || (A.local || []).some((c) => c.kind === "exec" && c.state === "open")) agentDrawTalk();
}
