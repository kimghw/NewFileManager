"use strict";
// 에이전트 보기(spec_일반편집 ② §8 한 턴 · §9 반영·엑셀 검증 · §10 자료 · §12 화면) — 공통 모듈: 어느 TASK 든(hwpx) 같은 보기를 연다(2026-11-16 — 전에는 「문서 일반 편집」 만 「작업 개요」 탭이 이 보기였다 · R6).
// 자리(2026-11-18 사용자 — agent_float.js): 상단 바 에이전트 아이콘이 여는 떠 있는 창(기본) 또는 패널 머리 탭 「에이전트」(대시보드 다음 — 창 머리의 「패널에 넣기」 로 고름). 같은 #paneAgent 노드를 옮긴다.
// 사용자 2026-11-13 "우측열에 에이전트 사이드열을 주고 여기서 요청하면 관련 자료를 작성할 수 있도록 … 에이전트에 자료주면 테이블에 넣어주고 … 어떤 테이블 구조가 좋은지 에이전트가 제시".
// 패널(3열) #paneAgent: 상태 줄(LLM 쓸 수 있나 · 「서식 보관함」 · 「비우기」) → 대화(턴마다 요청 글 · 답 · 제안 카드 · 호출 줄 + 「지침」) → 입력(아래 붙박이: 고른 자리 한 줄 · 표/글 서식 고르기 · 자료 칩 · 요청 글상자 · 「보내기」).
// 자료를 주는 길 셋(요청 글상자 아래 단추): 「자료 붙여넣기」 · 「파일」 · 「라이브러리」(문서 라이브러리 = 따로 선 서버 doclib 에 등록한 문서 · 추출한 MD 를 골라 — 입력 칸 위에 펴지는 고르기 .ag-lib: 아래 「문서 라이브러리에서 고르기」).
// 에이전트가 하는 일은 **제안까지**다 — 카드의 「문서에 반영」 을 눌러야 서버에 저장된 그 제안이 한 번의 편집(실행 취소 1개)으로 들어간다. 스크립트가 확인한 제안만 강조 단추(preselect),
// 에이전트가 지은 글(draft)·경고·엑셀 검증 안 맞음은 보통 단추 「읽고 반영」(design.md §8). 표 구조 후보는 한 카드의 라디오(하나만). 카드에 올리면 문서의 그 자리가 보라 테두리(§6).
// 2열(headsDlg — 팝업 아님) kind 둘: "agentProp"(제안 미리보기 — 표 후보 격자 나란히 · 채우기 목록(체크) · 글 줄) · "agentGuide"(그 턴에 보낸 글과 답 — 보기만).
// 상태는 모두 AGENT 에 둔다(DOM 밖) — 2열을 바꾸거나 다른 도구를 봐도 제안·고른 것이 남는다. 문서를 열고 닫을 때 agentReset()(app.js load·closeDoc).
// 밖에 내는 것: agentShow(showTab("Agent")) · agentReset · agentStylesRefresh(보관함이 바뀜 — style_lib.js) · agentPropOpen · agentGuideOpen.
// app.js 가 주는 것: state·heads·$·el·api·toast·structOp(+ structOp.lastError)·flushAll·headsDlg·headsColClose·hBtn·hTable·fmtWhen·nf·short·H_JSON. style_lib.js: slSelection·slTopOf·slBlockEls·slGo·styleLibOpen·styleSaveOpen.
// tables.js: xlColumn·xlRangeName. table_fill.js: TFL_FORM·TFL_WHERE·tblFillHit·tblFillGo. 서버 짝은 app/doc_agent_api.py — 끝점이 없으면(404·501·503) 그 까닭을 한 줄로 보이고 입력을 끈다.

const AG_TYPE = { write: "글 쓰기", tableNew: "새 표", tableFill: "표 채우기", restyle: "서식 입히기", styleCopy: "서식 복사" }; // styleCopy = 문서의 서식을 보관함에 저장(문서는 안 바뀜 — spec_서식복사 ② §6)
const AG_MODE = { extract: "자료·선택 글에서 옮긴 글", draft: "에이전트가 쓴 글" };
const AG_FILES = ".txt,.md,.csv,.tsv,.xlsx,.docx,.hwpx,.pdf";
const AG_STALE = "문서가 바뀌었습니다 — 다시 요청하세요";
const AG_EMPTY = "문서에서 자리를 고르고(문단 끌어 고르기 · 표 누르기 · 커서 두기) 아래에 요청을 적으세요. 에이전트는 제안만 냅니다 — 카드의 「문서에 반영」 을 눌러야 문서가 바뀌고, 도구 줄의 실행 취소로 되돌립니다.";
// 화면 장식은 같은 선 굵기의 작은 SVG로 — 버튼의 이름과 기존 동작은 그대로 둔다.
function agentIcon(name, size = 16) {
  const paths = {
    document: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
    library: '<rect x="4" y="3" width="6" height="18" rx="1.5"/><path d="m10 4.5 5.2-1.2a1.5 1.5 0 0 1 1.8 1.1l2.8 11.6a1.5 1.5 0 0 1-1.1 1.8L8.5 20.5"/><path d="M10 15h9.5a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5H7M7 17.5h.01"/>',
    paste: '<rect x="5" y="5" width="14" height="16" rx="2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/>',
    file: '<path d="m8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l8-8M6 14l8-8"/>',
    shelf: '<path d="M4 4v16M4 20h16M8 20V8h3v12M11 20V5h3v15M14.6 9.2l2.9-.8 2.9 10.8-2.9.8Z"/>', // 「라이브러리」(문서 라이브러리에서 자료 고르기) — 꽂힌 책 셋
    send: '<path d="M12 19V5M6 11l6-6 6 6"/>',
    arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10M15 10v10"/>',
    organize: '<path d="M4 5h16M4 9h10M4 13h5"/><rect x="12" y="13" width="8" height="7" rx="1"/><path d="M12 16h8M16 13v7"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18M7 15h3M14 15h3"/>',
    report: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 15v2M12 12v5M15 9v8"/>', // 「지금 할 수 있는 일」(doc_agent_next.js) — 현황 보고 · LLM 검토 · 서식 반영
    spark: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z"/><path d="M18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8Z"/>',
    format: '<path d="M4 7h10M4 12h7M4 17h10"/><path d="m15.5 14.5 4-4 1.5 1.5-4 4H15.5Z"/>',
    // 프로젝트 구성 폼 단추(확인 · 문서 보기 · 닫기) · 단계 꼬리표 칩(사람 · 스크립트 · LLM · 문서 바뀜) — 2026-11-18 사용자 「문서에서 보기는 문서 아이콘에 안경이나 눈알… 닫기는 X · 확정도 아이콘 · 사람, 스크립트, LLM, 문서바뀜 아이콘으로」
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    read: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4"/><path d="M14 3v5h5M8 11h4M8 15h2"/><path d="M11.5 17.5c1.2-2.1 2.9-3.2 4.8-3.2s3.6 1.1 4.8 3.2c-1.2 2.1-2.9 3.2-4.8 3.2s-3.6-1.1-4.8-3.2Z"/><circle cx="16.3" cy="17.5" r="1.3"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    human: '<circle cx="12" cy="8" r="3.5"/><path d="M5.5 19.5a6.5 6.5 0 0 1 13 0"/>',
    script: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 6l-3 12"/>',
    llm: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z"/><path d="M18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8Z"/>',
    doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h5"/><path d="M14 3v5h5M8 12h5M8 16h3"/><path d="m14.5 19.5 5-5 1.8 1.8-5 5H14.5v-1.8Z"/>',
    download: '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>' // 내려받기(첫 화면 「대시보드의 문서」 의 「원본」 · 「결과」 — 2026-11-23 사용자 「내려받기라고 쓰지 말고 … 다운로드 아이콘으로」)
  };
  const icon = el("span", "ag-icon");
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.document}</svg>`;
  return icon;
}
const agentFresh = () => ({ doc: null, loaded: false, loading: false, err: "", enabled: false, hwpx: true, policy: { apply: true, why: "" }, turns: [], materials: [], styles: { table: [], text: [] }, limits: {},
  matOff: new Set(), matBusy: null, matMsg: "", paste: { open: false, name: "", text: "" }, shelf: { open: false, loading: false, data: null, err: "", picks: new Set(), busy: null, msg: "", bad: false }, draft: "", pick: { table: "", text: "" }, busy: null, lost: null,
  choice: {}, fills: {}, req: {}, applying: null, prop: null, clearArm: 0, el: null, local: [], nextSig: "" });
// turns = 서버가 준 턴(제안 포함) · matOff = 이번 요청에 안 보낼 자료 · busy = 도는 턴 {text, t0, timer} · lost = 보내지 못한 요청 {text, error} · choice[후보 묶음] = 고른 제안 ·
// fills[제안 id] = 고른 칸 · req[제안 id] = 반영 요청 번호(같은 누름을 서버가 한 번으로) · prop = 2열에 띄운 제안 {turn, proposal} · el = 그려 둔 틀 ·
// local = 화면에만 두는 카드(현황 보고 · LLM 검토 실행 — doc_agent_next.js, 저장 안 함) · nextSig = 그 카드·빈 화면 묶음이 기대는 분석 상태의 서명
// shelf = 문서 라이브러리에서 고르기 {open, loading, data(GET /api/doclib 의 답), err, picks(고른 항목 key — 「x:<추출 id>」 · 「d:<문서 id>」), busy(가져오는 중 {i, n, name}), msg(끝 글), bad(끝 글이 못 가져온 것을 알림)}
let AGENT = agentFresh();
let agentSelRaf = 0;
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { agentTurn: "에이전트 요청", agentApply: "에이전트 제안 반영", agentMaterial: "에이전트 자료", agentClear: "에이전트 대화 비우기" }); // 「기록」 탭의 이름

const agentErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「에이전트」 를 쓸 수 있습니다" : (e && e.message) || "알 수 없는 오류");
const agentUrl = (tail = "") => `/api/docs/${encodeURIComponent(state.id)}/agent${tail}`;
const agentKey = () => (state.id ? `${state.id}|${state.epoch}` : null);
const agentWhen = (v) => { const t = typeof v === "number" ? (v > 1e12 ? v / 1000 : v) : v ? Date.parse(v) / 1000 : NaN; return Number.isFinite(t) ? fmtWhen(t) : ""; };
const agentTurnOf = (tid) => AGENT.turns.find((t) => t.id === tid) || null;
const agentPropOf = (t, pid) => (t && (t.proposals || []).find((p) => p.id === pid)) || null;
const agentGroup = (t, p) => (p.choiceGroup ? (t.proposals || []).filter((x) => x.choiceGroup === p.choiceGroup) : [p]);
const agentUuid = () => (crypto.randomUUID ? crypto.randomUUID() : `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`);
const agentBusyText = (b) => `${b.label || "요청을 읽는 중"} · ${Math.round((performance.now() - b.t0) / 1000)}초`; // label = 진행 턴의 글(doc_agent_work.js — 「작업 절차를 확인하는 중」 …)
function agentChosen(t, group) { // 후보 묶음에서 지금 고른 것 — 반영한 것이 있으면 그것 · 사람이 고른 것 · 스크립트가 확인한 첫 후보 · 첫 후보
  return group.find((p) => p.state === "applied") || group.find((p) => p.id === AGENT.choice[group[0].choiceGroup]) || group.find((p) => p.preselect && (p.state || "open") === "open") || group[0];
}
function agentFillPicks(p) { // 표 채우기 제안의 고른 칸 — 처음에는 서버가 골라 둔 칸(view.picked: 스크립트가 확인한 제안 — 엑셀 검증이 안 맞으면 비어 있다 · design.md §8). 옛 서버면 경고 없는 제안
  if (!AGENT.fills[p.id]) {
    const v = p.view || {};
    AGENT.fills[p.id] = new Set(Array.isArray(v.picked) ? v.picked : (v.fills || []).filter((f) => !(f.warn || []).length).map((f) => f.cell));
  }
  return AGENT.fills[p.id];
}
const agentStyleOf = (v, kind) => (v.styleName || agentStyleName(v.style, kind)) + (v.styleFrom ? ` (원본 ${v.styleFrom})` : ""); // 제안이 쓰는 서식의 이름(서버가 준 이름 먼저) + 그 서식을 뽑은 문서(spec_서식복사 ② §17)
const agentFillCount = (p) => { const s = agentFillPicks(p); return (((p.view || {}).fills) || []).filter((f) => s.has(f.cell)).length; };
function agentStyleName(id, kind) {
  if (!id) return kind === "text" ? "자리 둘레 서식" : "정하지 않음";
  if (id === "builtin") return "기본 표";
  if (/^doc:/.test(id)) return `이 문서의 표 ${id.slice(4)}`;
  const s = [...AGENT.styles.table, ...AGENT.styles.text].find((x) => x.id === id);
  return s ? s.name || id : id;
}
function agentBlockName(id) { // 「문단 p33 「연구개발의 …」」 · 「표 t12」
  if (!id) return "";
  const txt = state.texts && id in state.texts ? oneLine(state.texts[id]) : null;
  return txt == null ? `표 ${id}` : `문단 ${id}${txt ? ` 「${txt.length > 18 ? txt.slice(0, 18) + "…" : txt}」` : ""}`;
}
function agentGridLayout(grid) { // 격자의 칸 자리(HTML 표 규칙 — table_make.js tmkLayout · 서버 table_make.normalize 와 같음) → {cells: [{r, c, rs, cs, cell}], rows, cols}
  const occ = new Set(), cells = [], rows = (grid && grid.rows) || [];
  let cols = 0;
  rows.forEach((row, r) => {
    let c = 0;
    for (const cell of row.cells || []) {
      while (occ.has(`${r},${c}`)) c += 1;
      const rs = Math.min(Math.max(1, cell.rowSpan || 1), rows.length - r);
      let cs = Math.max(1, cell.colSpan || 1);
      for (let k = 1; k < cs; k += 1) if (occ.has(`${r},${c + k}`)) { cs = k; break; }
      for (let y = r; y < r + rs; y += 1) for (let x = c; x < c + cs; x += 1) occ.add(`${y},${x}`);
      cells.push({ r, c, rs, cs, cell });
      c += cs;
      cols = Math.max(cols, c);
    }
  });
  return { cells, rows: rows.length, cols };
}

// ---- 열기 · 닫기 · 읽기 ------------------------------------------------------------------------------------------------------
function agentReset() { // 문서를 열거나 닫을 때(app.js load·closeDoc) — 늦게 온 응답은 AGENT 가 바뀐 것으로 버린다
  if (AGENT.busy) clearInterval(AGENT.busy.timer);
  AGENT = agentFresh();
  agentHit(null);
  const box = $("agentBox");
  if (box) box.textContent = "";
  if (typeof agentFloatSync === "function") agentFloatSync(); // 떠 있는 에이전트 창 — 문서를 닫으면 닫고, 다른 문서를 열면 그 문서의 에이전트로(agent_float.js)
}

function agentShow() { // showTab("Agent")
  if (!state.id || !$("agentBox")) return;
  agentFrame();
  agentDraw();
  if (AGENT.doc !== agentKey() && !AGENT.loading) agentLoad();
}

async function agentLoad(quiet = false) { // quiet = 보관함·자료만 다시(대화는 화면 것 그대로 — 보관함이 바뀐 뒤)
  const A = AGENT, epoch = state.epoch;
  if (!state.id || A.loading) return;
  A.doc = agentKey();
  A.loading = true;
  if (!quiet) agentDraw();
  try {
    const r = await api(agentUrl());
    if (A !== AGENT || epoch !== state.epoch) return;
    const st = r.styles || {};
    Object.assign(A, { loaded: true, err: "", enabled: !!r.enabled, hwpx: r.hwpx !== false, policy: { apply: true, why: "", ...(r.policy || {}) }, materials: r.materials || [], styles: { table: st.table || [], text: st.text || [] },
      limits: r.limits || {} }); // limits = 서버의 한도(요청 글자 수 · 자료 형식·크기) — 입력 칸에 그대로 건다
    if (!quiet) A.turns = r.turns || [];
  } catch (e) {
    if (A !== AGENT || epoch !== state.epoch) return;
    if (!quiet) { A.loaded = false; A.err = agentErr(e); }
  }
  A.loading = false;
  agentDraw();
  if (!quiet && A.el) A.el.talk.scrollTop = A.el.talk.scrollHeight;
}
function agentStylesRefresh() { if (AGENT.loaded && !AGENT.busy && !AGENT.applying && AGENT.doc === agentKey()) agentLoad(true); } // 서식 보관함에 저장·이름 바꿈·지움 뒤(style_lib.js)

// ---- 틀(문서마다 한 번) -------------------------------------------------------------------------------------------------------
function agentFrame() {
  const box = $("agentBox");
  if (AGENT.el && AGENT.el.root.isConnected) return;
  const root = el("div", "ag"), E = (AGENT.el = { root, pickKey: null });
  E.status = el("div", "ag-status");
  E.status.setAttribute("role", "status");
  E.statusText = el("span", "ag-status-text");
  E.lib = hBtn("서식 관리자", () => { if (typeof styleLibOpen === "function") styleLibOpen(); }, { title: "보관한 표지 · 내용 · 테이블 · 문단 서식을 문서 옆 열에서 그림으로 보고 문서에 적용합니다 — 이 문서의 서식을 복사해 저장할 수도 있습니다" }); // 열 이름 = 서식 관리자(spec_서식복사 ② §2)
  E.lib.dataset.agAct = "library";
  E.lib.prepend(agentIcon("library"));
  E.clear = hBtn("비우기", () => agentClear(), { title: "이 문서의 대화(요청·답·제안)와 자료를 모두 지웁니다 — 문서는 그대로 · 한 번 더 눌러야 지웁니다" });
  E.clear.dataset.agAct = "clear";
  E.guide = hBtn("작업 설명", () => { if (typeof agentWorkStart === "function") agentWorkStart(true); }, { title: "이 워크플로우의 사전 준비 · 진행 상황 · 다음 단계를 지금 상태로 다시 설명합니다(작업 진행 에이전트)" });
  E.guide.dataset.agAct = "guide";
  E.status.append(el("span", "ag-dot"), E.statusText, E.guide, E.lib, E.clear);
  if (typeof agentFloatTools === "function") E.status.append(agentFloatTools()); // 패널 탭 자리일 때만 보이는 「에이전트 설정」 · 「창으로 띄우기」(agent_float.js — 떠 있는 창에서는 창 머리에 같은 것)
  E.talk = el("div", "ag-talk");
  E.talk.setAttribute("role", "log");
  E.talk.setAttribute("aria-label", "에이전트 대화");
  E.input = el("div", "ag-input");
  E.policy = el("p", "ag-policy", "원본 문서 — 제안은 보기만");
  E.policy.hidden = true;
  E.sel = el("div", "ag-sel");
  const picks = el("div", "ag-picks");
  const pick = (label, key, title) => {
    const l = el("label", "ag-pick"), s = el("select");
    l.title = title;
    s.setAttribute("aria-label", `${label} 서식`);
    s.dataset.agPick = key;
    s.onchange = () => { AGENT.pick[key] = s.value; };
    l.append(el("span", null, `${label} 서식`), s);
    picks.append(l);
    return s;
  };
  E.pickTable = pick("표", "table", "새 표에 입힐 서식 — 보관한 표 서식 · 기본 표 · 이 문서의 표(문서에서 표를 누르면 목록에 나옵니다)\n정하지 않으면 에이전트가 보관함에서 고릅니다");
  E.pickText = pick("글", "text", "새 글에 입힐 서식 — 보관한 글 서식 · 자리 둘레 서식(넣을 자리의 문단 모양 그대로)");
  E.mats = el("div", "ag-mats");
  E.paste = el("div", "ag-paste");
  E.paste.hidden = true;
  E.pasteName = el("input");
  E.pasteName.type = "text"; E.pasteName.maxLength = 80; E.pasteName.placeholder = "자료 이름(선택)";
  E.pasteName.setAttribute("aria-label", "자료 이름");
  E.pasteName.oninput = () => { AGENT.paste.name = E.pasteName.value; };
  E.pasteText = el("textarea");
  E.pasteText.rows = 4; E.pasteText.maxLength = 200000;
  E.pasteText.placeholder = "자료로 쓸 글을 붙여 넣으세요 — 공고문·협약서·메일·다른 문서에서 복사한 글(표를 복사해도 됩니다)";
  E.pasteText.setAttribute("aria-label", "자료 글");
  E.pasteText.oninput = () => { AGENT.paste.text = E.pasteText.value; E.pasteAdd.disabled = !E.pasteText.value.trim() || !!AGENT.matBusy; };
  E.pasteAdd = hBtn("자료로 넣기", () => agentPasteAdd(), { title: "붙여 넣은 글을 이 문서의 자료로 저장합니다 — 요청과 함께 에이전트에 보냅니다" });
  E.pasteAdd.dataset.agAct = "pasteAdd";
  const pasteActs = el("div", "ag-paste-acts");
  pasteActs.append(E.pasteAdd, hBtn("닫기", () => { AGENT.paste.open = false; agentDrawInput(); }));
  E.paste.append(E.pasteName, E.pasteText, pasteActs);
  E.shelf = el("div", "ag-lib"); // 문서 라이브러리에서 고르기 — 「자료 붙여넣기」 와 같은 자리에 펴진다(창 아님 — agentShelfDraw 가 채운다)
  E.shelf.hidden = true;
  E.text = el("textarea");
  E.text.rows = 3; E.text.maxLength = 4000;
  E.text.id = "agentRequest";
  E.text.placeholder = "어떤 작업을 도와드릴까요?";
  E.text.setAttribute("aria-label", "에이전트에 보낼 요청");
  E.text.oninput = () => { AGENT.draft = E.text.value; agentSendSync(); };
  E.text.onkeydown = (ev) => { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey) && !ev.isComposing && ev.keyCode !== 229) { ev.preventDefault(); agentSend(); } };
  E.send = hBtn("보내기", () => agentSend(), { cls: "btn sm primary", title: "요청을 에이전트에 보냅니다(Ctrl+Enter) — 제안만 받습니다. 문서는 카드의 「문서에 반영」 을 눌러야 바뀝니다" });
  E.send.dataset.agAct = "send";
  E.send.append(agentIcon("send"));
  E.run = el("span", "ag-run");
  E.run.hidden = true;
  E.run.append(el("span", "ag-spin"), el("span", "ag-run-text live"));
  E.why = el("span", "ag-why");
  const requestHead = el("div", "ag-request-head"), requestLabel = el("label", "ag-request-label", "작업 요청");
  requestLabel.htmlFor = E.text.id;
  requestHead.append(requestLabel);
  if (typeof hHelp === "function") requestHead.append(hHelp("작업 요청 안내", AG_EMPTY));
  requestHead.append(el("span", "ag-shortcut", "Ctrl / ⌘ + Enter"));
  const sendRow = el("div", "ag-send");
  sendRow.append(E.mats, E.send, E.run, E.why);
  const composer = el("div", "ag-composer");
  composer.append(requestHead, E.text, sendRow);
  E.input.append(E.policy, E.sel, picks, E.paste, E.shelf, composer);
  root.append(E.status, E.talk, E.input);
  box.replaceChildren(root);
}

// ---- 그리기 ---------------------------------------------------------------------------------------------------------------
function agentDraw() { agentDrawStatus(); agentDrawTalk(); agentDrawInput(); }

function agentDrawStatus() {
  const A = AGENT, E = A.el;
  if (!E) return;
  const st = A.err && !A.loaded ? ["off", `에이전트를 쓸 수 없습니다 — ${A.err}`] : !A.loaded ? ["", "에이전트 상태를 읽는 중…"] : !A.hwpx ? ["off", "hwpx 문서만 됩니다"]
    : A.enabled ? ["on", "LLM 사용 가능"] : ["off", "LLM 을 쓸 수 없습니다 — 제안을 받을 수 없습니다"];
  E.status.dataset.llm = st[0];
  E.statusText.textContent = st[1];
  E.statusText.title = st[1] + (st[0] === "off" && A.loaded && A.hwpx ? "\nClaude 실행 파일·로그인·API 키가 없거나 꺼져 있습니다 — 서식 관리자와 자료 넣기는 됩니다" : "");
  E.guide.hidden = !(typeof agwGuided === "function" && agwGuided() && A.hwpx); // 단계가 있는 TASK 에서만
  E.guide.disabled = !A.loaded || !!A.busy || !!A.applying || !!(A.work && A.work.running) || (typeof agwRunning === "function" && !!agwRunning()); // 도는 실행이 있으면 끝난 뒤에(진행 카드가 보인다)
  const armed = performance.now() < A.clearArm;
  E.clear.disabled = !A.loaded || !(A.turns.length || A.lost || A.materials.length || A.local.length) || !!A.busy || !!A.applying;
  E.clear.classList.toggle("arm", armed);
  E.clear.textContent = armed ? "정말 비우기" : "비우기";
}

function agentDrawTalk(toEnd = false) {
  const A = AGENT, E = A.el;
  if (!E) return;
  const box = E.talk, keep = box.scrollTop, atEnd = toEnd || box.scrollHeight - box.scrollTop - box.clientHeight < 24;
  const live = typeof agwLiveEl === "function" && A.loaded ? agwLiveEl() : null; // 진행 카드 — 지금 도는 「한 번에 진행」(doc_agent_work.js: 누가 시작했든 대화의 맨 아래 한 곳에)
  box.textContent = "";
  if (A.err && !A.loaded) {
    const acts = el("div", "ag-acts");
    acts.append(hBtn("다시 읽기", () => agentLoad()));
    box.append(el("p", "hwarn fail", `에이전트 상태를 읽지 못했습니다: ${A.err}`), acts);
  } else if (!A.turns.length && !A.busy && !A.lost && A.loaded && !(live && typeof agwGuided === "function" && agwGuided())) box.append(typeof agwGuided === "function" && agwGuided() && A.hwpx ? agentWorkEmptyEl() : agentEmptyEl()); // 단계가 있는 TASK = 진행 에이전트의 빈 상태(spec_작업에이전트 ② §5) — 도는 실행이 있으면 진행 카드만
  for (const t of A.turns) box.append(agentTurnEl(t));
  if (typeof agentLocalEls === "function" && A.local.length) box.append(...agentLocalEls()); // 현황 보고 · LLM 검토 실행 카드(doc_agent_next.js — 화면에만)
  if (A.lost) {
    const s = el("section", "ag-turn");
    s.dataset.turn = "";
    s.append(el("p", "ag-q", A.lost.text), el("p", "hwarn fail", `요청을 보내지 못했습니다: ${A.lost.error} — 요청 글은 아래 글상자에 그대로 있습니다`));
    box.append(s);
  }
  if (live) box.append(live);
  if (A.busy) { // 보낸 요청은 답이 오기 전에도 턴으로 보인다 — 동그라미 + 지금 하는 일 + 지난 시간(design.md §7)
    const s = el("section", "ag-turn pending"), run = el("div", "ag-run");
    run.append(el("span", "ag-spin"), el("span", "ag-run-text live", agentBusyText(A.busy)));
    if (A.busy.text) s.append(el("p", "ag-q", A.busy.text));
    s.append(run);
    box.append(s);
  }
  box.scrollTop = atEnd ? box.scrollHeight : keep;
}

function agentEmptyEl() {
  const box = el("section", "ag-empty"), heading = el("div", "ag-empty-heading");
  heading.append(agentIcon("document"), el("h2", null, "문서 작업을 시작하세요"));
  box.append(heading, el("p", "ag-empty-intro", "문단이나 표를 고른 뒤, 필요한 작업을 요청하세요."));
  if (typeof agentNextEl === "function" && AGENT.hwpx) box.append(agentNextEl(), el("p", "ag-next-title", "요청 예시")); // 「지금 할 수 있는 일」 — 현황 보고(사전 질의) · 아직 안 한 LLM 검토 · 서식 반영(doc_agent_next.js — spec ② §12) · 아래 예시와 가르는 제목
  const examples = el("div", "ag-examples");
  examples.setAttribute("aria-label", "요청 예시");
  for (const [label, prompt, icon] of [["자료로 표 채우기", "붙인 자료로 고른 표를 채워 줘", "table"], ["문단을 표로 정리하기", "고른 문단을 표로 정리해 줘", "organize"], ["추진 일정 작성하기", "이 자리에 추진 일정을 써 줘", "calendar"]]) {
    const button = hBtn(label, () => {
      const E = AGENT.el;
      if (!E || E.text.disabled) return;
      const draft = [AGENT.draft.trim(), prompt].filter(Boolean).join("\n");
      if (draft.length <= E.text.maxLength) { AGENT.draft = draft; E.text.value = draft; agentSendSync(); }
      E.text.focus();
    }, { cls: "btn sm ag-example", title: `요청 예시를 입력합니다 — ${prompt}` });
    button.prepend(agentIcon(icon));
    button.append(agentIcon("arrow"));
    examples.append(button);
  }
  box.append(examples, el("p", "ag-empty-note", "에이전트는 제안만 냅니다. 확인한 제안을 문서에 반영하세요."));
  return box;
}

function agentTurnEl(t) {
  if (t.kind === "guide" && typeof agentWorkTurnEl === "function") return agentWorkTurnEl(t); // 진행 턴(작업 진행 에이전트 — doc_agent_work.js)
  const box = el("section", "ag-turn"), seen = new Set(), c = t.call || {}, dropped = t.dropped || [];
  box.dataset.turn = t.id;
  box.append(el("p", "ag-q", t.text || ""));
  if (t.reply) box.append(el("p", "ag-a", t.reply));
  for (const n of t.notes || []) box.append(el("p", "ag-note", n)); // 스크립트가 덧붙인 말(채울 칸이 없는 표 · 자른 자료 …)
  if (t.error) box.append(el("p", "hwarn fail", `에이전트가 답하지 못했습니다: ${t.error}`));
  for (const p of t.proposals || []) {
    if (p.choiceGroup) { if (seen.has(p.choiceGroup)) continue; seen.add(p.choiceGroup); }
    box.append(agentCardEl(t, agentGroup(t, p)));
  }
  if (dropped.length) { // 스크립트 검사에서 버린 행동(틀린 꼴 — 없는 자리·없는 서식 …)
    const d = el("details", "ag-dropped"), ul = el("ul");
    for (const x of dropped) ul.append(el("li", null, `${AG_TYPE[x.type] || x.type || x.action || "행동"}${x.candidate != null ? `(후보 ${x.candidate})` : ""} — ${x.why || ""}`));
    d.append(el("summary", null, `검사에서 버린 행동 ${nf(dropped.length)}`), ul);
    box.append(d);
  }
  const meta = el("div", "ag-meta");
  meta.append(el("span", null, [agentWhen(t.at), c.ms != null ? `${(c.ms / 1000).toFixed(1)}초` : "", c.costUsd != null ? `$${Number(c.costUsd).toFixed(3)}` : "", c.model || "", t.calls > 1 ? `호출 ${nf(t.calls)}` : ""].filter(Boolean).join(" · ")));
  if (c.error) meta.append(el("span", "ag-state err", `호출 오류 — ${c.error}`));
  const g = hBtn("지침", () => agentGuideOpen(t.id), { title: "이 요청에 함께 보낸 글(계약 · 지침 · 할 일 프롬프트 · 자료)과 LLM 의 답을 문서 옆 열에서 봅니다 — 보기만(문서는 안 바뀜)" });
  g.dataset.agGuide = t.id;
  meta.append(g);
  box.append(meta);
  return box;
}

function agentCardEl(t, group) {
  const A = AGENT, p = agentChosen(t, group), many = group.length > 1, applied = group.some((x) => x.state === "applied");
  const card = el("article", "ag-card"), head = el("div", "ag-card-head");
  card.dataset.prop = p.id;
  card.dataset.type = p.type;
  card.dataset.state = p.state || "open";
  if (many) card.dataset.group = p.choiceGroup;
  head.append(el("span", "ag-tag", AG_TYPE[p.type] || p.type), el("strong", "ag-title", many ? `표 구조 후보 ${group.length}개 — 하나만 반영` : p.title || ""));
  card.append(head);
  if (many) { // 후보끼리는 배치만 다르고 값은 같다 — 하나만 고른다
    const list = el("div", "ag-cands");
    list.setAttribute("role", "radiogroup");
    list.setAttribute("aria-label", "표 구조 후보");
    for (const c of group) {
      const lab = el("label", "ag-cand"), rb = el("input"), cv = c.view || {}, lay = cv.rows && cv.cols ? cv : cv.grid ? agentGridLayout(cv.grid) : null;
      lab.dataset.cand = c.id;
      rb.type = "radio"; rb.name = `agc-${t.id}-${p.choiceGroup}`; rb.value = c.id; rb.checked = c.id === p.id; rb.disabled = applied || !!A.applying;
      rb.onchange = () => { if (rb.checked) agentChoose(c); };
      lab.append(rb, el("b", null, c.title || "후보"), el("span", "ag-size", lay ? `${lay.rows}×${lay.cols}` : ""));
      if (cv.why) lab.append(el("span", "ag-why", cv.why));
      list.append(lab);
    }
    card.append(list);
  } else if (p.summary) card.append(el("p", "ag-sum", p.summary));
  if (p.type === "styleCopy") card.append(agentStyleCopyEl(p)); // 무엇을 저장하나 · 저장 뒤 서식마다 검증 꼬리표
  card.append(agentChecksEl(p), agentActsEl(t, p));
  card.addEventListener("mouseenter", () => agentHit(p));
  card.addEventListener("mouseleave", () => agentHit(null));
  return card;
}

function agentExcelLine(x, after = false) { // 엑셀 검증 한 줄 → [꼴, 글, 도움말] — 수식이 0개거나 빈 칸뿐이면 「검산할 수식 없음」(통과가 아니다)
  const pre = after ? "반영 뒤 엑셀 검증" : "엑셀 검증", n = x.formulas || 0, exs = x.examples || [], fst = typeof H_FSTAT === "object" ? H_FSTAT : {};
  const rest = [x.missing ? `미기입 ${nf(x.missing)}` : "", x.incomplete ? `일부 빈 칸 ${nf(x.incomplete)}` : "", x.blank ? `빈 칸 ${nf(x.blank)}` : "", x.nonnumeric ? `수가 아님 ${nf(x.nonnumeric)}` : ""].filter(Boolean).join(" · ");
  const title = [x.note || "", ...exs.map((e) => `${e.ref} ${e.formula} — 계산 ${e.expected} · 표의 값 ${e.actual}${e.status ? ` (${fst[e.status] || e.status})` : ""}`)].filter(Boolean).join("\n");
  if (x.mismatch) {
    const e = exs.find((q) => q.status === "mismatch") || exs[0];
    return ["bad", `${pre} — 수식 ${nf(n)} · 안 맞음 ${nf(x.mismatch)}${e ? ` · ${e.ref} ${e.formula} 계산 ${e.expected} ≠ 표 ${e.actual}` : ""}`, title];
  }
  if (x.ok) return ["ok", `${pre} — 수식 ${nf(n)} · 맞음 ${nf(x.ok)}${rest ? ` · ${rest}` : ""}`, title];
  return ["none", `검산할 수식 없음${rest ? `(${rest})` : ""}`, title || "수식이 없거나 빈 칸뿐이라 검산하지 못했습니다 — 통과가 아닙니다"];
}

function agentChecksEl(p) { // 검사 줄 — 종류별 요약 · 엑셀 검증 · 경고 · 스크립트 검사
  const box = el("div", "ag-checks"), v = p.view || {};
  const add = (cls, text, title = "") => { const d = el("div", cls ? `ag-check ${cls}` : "ag-check", text); if (title) d.title = title; box.append(d); return d; };
  if (p.type === "tableFill") {
    const k = v.counts || {}, fills = v.fills || [];
    add("", `채울 칸 ${nf(k.targets || 0)} · 제안 ${nf(k.fills == null ? fills.length : k.fills)}(경고 ${nf(k.warn || 0)})${k.rejected ? ` · 검사에서 뺌 ${nf(k.rejected)}` : ""} · 못 채운 칸 ${nf(k.left || 0)}`,
      "못 채운 칸 = 자료에서 값을 찾지 못한 칸(빈 채로 둡니다) · 경고 = 근거 구절을 자료에서 못 찾음 · 꼴이 안 맞음 — 처음엔 고르지 않은 채입니다");
  }
  const after = p.state === "applied" && p.applied && p.applied.excel, x = after || p.excel;
  if (x) { const [cls, text, title] = agentExcelLine(x, !!after); add(cls, text, title).dataset.excel = cls; }
  for (const w of p.warn || []) add("warn", w); // 「에이전트가 쓴 글 — 읽고 반영하세요」 · 자료에 없는 수 · 엑셀 검증 안 맞음 … — 서버가 경고를 모두 여기에 싣는다
  const cs = (p.checks || []).filter((c) => c.status !== "warn" && c.what !== "excel"), pass = cs.filter((c) => c.status === "pass"); // 경고는 warn[] 에 · 엑셀 검증은 위 줄에 이미 있다(같은 말을 두 번 보이지 않는다)
  for (const c of cs) if (c.status !== "pass") add("", `${c.text || c.what || ""}${c.status === "unknown" ? " — 확인하지 못함" : ""}`);
  if (pass.length) add("ok", `스크립트 검사 통과 ${nf(pass.length)}`, pass.map((c) => c.text || c.what).join("\n"));
  for (const g of v.gridChanges || []) add("", `격자를 맞춤 — ${g}`, "LLM 이 낸 격자를 표 규칙에 맞게 고쳤습니다 — 보이는 격자가 반영할 격자입니다");
  return box;
}

function agentActsEl(t, p, inCol = false) { // 카드의 단추 줄(2열 미리보기의 발치도 같은 줄 — inCol = 「미리보기」 빼고)
  const A = AGENT, acts = el("div", inCol ? "agp-foot" : "ag-acts"), v = p.view || {}, st = p.state || "open";
  const btn = (key, b) => { b.dataset.agAct = key; acts.append(b); return b; };
  if (p.type === "styleCopy") { // 서식 복사 — 문서를 바꾸지 않는다: 미리보기 없음(카드에 목록이 있다) · 원본 문서(「제안은 보기만」)에서도 저장된다 · 저장 뒤 「서식 관리자에서 보기」
    const saved = (p.applied && p.applied.styles) || [];
    if (st === "applied") acts.append(el("span", "ag-state ok", `보관함에 저장함 — 서식 ${nf(saved.length)}개`));
    else if (st === "closed") acts.append(el("span", "ag-state", "닫힌 제안"));
    else btn("apply", hBtn("보관함에 저장", () => agentApply(t.id, p.id), { cls: p.preselect ? "btn sm primary" : "btn sm", disabled: st === "stale" || !!A.applying,
      title: st === "stale" ? "문서가 바뀌어 이 제안은 저장할 수 없습니다 — 다시 요청하세요" : "이 서식들을 보관함에 저장합니다(hwpx·docx 두 형식) — 문서는 바뀌지 않고, 저장하면 PDF 검증이 뒤에서 돕니다" }));
    if (A.applying === p.id) { const run = el("span", "ag-run"); run.append(el("span", "ag-spin"), el("span", "ag-run-text", "보관함에 저장하는 중…")); acts.append(run); }
    // 「서식 그림 보기」(spec_서식복사 ② §13) — 저장 전: 2열에 「서식 복사」 보기를 열고 이 제안의 대상(표 id · 템플릿 id · 문단 · 쪽 설정 · 표지)을 고른 채로 보인다(같은 견본 길 — 저장될 견본). 3열 카드 안에는 큰 그림을 넣지 않는다(design.md §13)
    if (!saved.length && st !== "closed" && (v.picks || []).length) btn("pics", hBtn("서식 그림 보기", () => { if (typeof styleSaveOpen === "function") styleSaveOpen({ picks: (v.picks || []).map((k) => ({ ...k })) }); },
      { cls: "btn sm ag-pics", title: "문서 옆 열(서식 복사)에서 이 제안이 저장할 서식의 그림(저장될 견본)을 봅니다 — 제안의 대상을 고른 채로 엽니다 · 문서는 안 바뀝니다" }));
    const tabOf = (x) => (typeof slTabOfPick === "function" ? slTabOfPick((v.picks || [])[x.pick] || x) : x.kind || null); // 저장한 서식의 갈래(내용 서식 · 문단 서식 …)
    if (saved.length) btn("toLib", hBtn("서식 관리자에서 보기", () => { if (typeof styleLibOpen === "function") styleLibOpen(tabOf(saved[0])); }, { title: "방금 저장한 서식을 서식 관리자에서 봅니다 — 서식 그림 · 검증 내역 · 문서에 쓰기" }));
    if (st === "stale") acts.append(el("span", "ag-state stale", p.why || AG_STALE));
    else if (st === "failed") acts.append(el("span", "ag-state err", `저장하지 못했습니다${p.why ? ` — ${p.why}` : ""}`));
    return acts;
  }
  if (!inCol) btn("preview", hBtn("미리보기", () => agentPropOpen(t.id, p.id), { title: "문서 옆 열에서 제안 내용을 봅니다 — 문서는 안 바뀝니다" }));
  if (st === "applied") {
    const ap = p.applied || {}, paras = Array.isArray(ap.paras) ? ap.paras : [], table = ap.table || (p.type === "tableFill" || p.type === "restyle" ? v.table : null) || null;
    const go = table || paras[0] || (v.paras || [])[0] || v.after;
    btn("go", hBtn("반영됨 — 자리로", () => slGo(go), { cls: "btn sm done", title: "문서에 반영했습니다 — 누르면 그 자리로 · 도구 줄의 실행 취소로 되돌립니다" }));
    if (table && (p.type === "tableNew" || p.type === "tableFill")) {
      btn("excel", hBtn("엑셀식 보기", () => { if (typeof xlColumn === "function") xlColumn(table); }, { title: "문서 옆 열에 이 표의 A1 격자 — 수식 자리 판정 · 계산 · 엑셀로 받기" }));
      btn("saveStyle", hBtn("이 표를 서식으로 저장", () => { if (typeof styleSaveOpen === "function") styleSaveOpen({ table, blueprint: true }); },
        { title: "이 표의 서식과 구조를 서식 보관함에 저장합니다 — 다른 문서·워크플로우에서 「빈 표 넣기」 로 다시 씁니다" }));
    }
    if (ap.note) acts.append(el("span", "ag-state", ap.note));
    return acts;
  }
  if (st === "closed") { acts.append(el("span", "ag-state", "다른 후보를 반영함")); return acts; } // 같은 묶음의 다른 후보가 들어갔다 — 이 후보는 끝난 것
  const n = p.type === "tableFill" ? agentFillCount(p) : null;
  const off = A.policy.apply === false ? A.policy.why || "원본 문서는 바꾸지 않습니다" : st === "stale" ? "문서가 바뀌어 이 제안은 반영할 수 없습니다 — 다시 요청하세요" : n === 0 ? "고른 칸이 없습니다 — 미리보기에서 넣을 칸을 고르세요" : "";
  const label = n == null ? (p.preselect ? "문서에 반영" : "읽고 반영") : `고른 ${nf(n)}칸 ${p.preselect ? "문서에 반영" : "읽고 반영"}`;
  btn("apply", hBtn(label, () => agentApply(t.id, p.id), { cls: p.preselect ? "btn sm primary" : "btn sm", disabled: !!off || !!A.applying,
    title: off || (p.preselect ? "서버에 저장된 이 제안을 문서에 넣습니다 — 한 번의 편집(도구 줄 「실행 취소」 로 되돌림)" : "스크립트가 확인하지 못한 제안입니다(에이전트가 쓴 글 · 경고 · 검증 안 맞음) — 미리보기로 읽어 본 뒤 넣으세요. 한 번의 편집(실행 취소로 되돌림)") }));
  if (A.applying === p.id) { const run = el("span", "ag-run"); run.append(el("span", "ag-spin"), el("span", "ag-run-text", "문서에 반영하는 중…")); acts.append(run); }
  if (st === "stale") acts.append(el("span", "ag-state stale", p.why || AG_STALE));
  else if (st === "failed") acts.append(el("span", "ag-state err", `반영하지 못했습니다${p.why ? ` — ${p.why}` : ""}`));
  return acts;
}

function agentChoose(c) { // 표 구조 후보 고르기(카드·미리보기 어느 쪽에서든)
  AGENT.choice[c.choiceGroup] = c.id;
  if (AGENT.prop && agentPropOn()) AGENT.prop.proposal = c.id;
  agentDrawTalk();
  agentPropSync();
}

function agentHit(p) { // 카드에 올린 동안 문서의 그 자리(보라 — LLM 제안: design.md §6). 「뒤에 넣음」 은 그 블록의 아래 변. null = 걷기
  for (const e of document.querySelectorAll("#doc .ag-hit, #doc .ag-after")) e.classList.remove("ag-hit", "ag-after");
  if (!p || typeof slBlockEls !== "function") return;
  const v = p.view || {}, tg = p.target || {}, ap = p.state === "applied" ? p.applied || {} : null, insert = p.type === "write" || p.type === "tableNew";
  let whole = p.type === "styleCopy" ? (v.picks || []).flatMap((k) => [k.table, ...(k.paras || [])]) // 서식 복사 — 서식을 뽑을 표·문단(저장한 뒤에도 같은 자리: 문서는 안 바뀐다)
    : ap ? [ap.table, ...(Array.isArray(ap.paras) ? ap.paras : [])] : p.type === "tableFill" ? [v.table] : p.type === "restyle" ? [v.table, ...(v.paras || [])] : [];
  if (!whole.filter(Boolean).length && !insert) whole = tg.blocks || [tg.block]; // 보기에 자리가 없으면 서버가 적어 둔 대상(target)
  for (const id of whole.filter(Boolean).slice(0, 60)) for (const e of slBlockEls(id)) e.classList.add("ag-hit");
  if (!ap && insert && (v.after || tg.block)) { const els = slBlockEls(v.after || tg.block); if (els.length) els[els.length - 1].classList.add("ag-after"); }
}

// ---- 입력 — 고른 자리 · 서식 고르기 · 자료 · 요청 ------------------------------------------------------------------------------
function agentSelDraw() { // 고른 자리 한 줄(문서의 선택 상태를 그대로 읽는다) + 표 서식 고르기의 「이 문서의 표」
  const A = AGENT, E = A.el;
  if (!E || typeof slSelection !== "function") return;
  const s = slSelection(), parts = [];
  if (s.paras.length) parts.push(`고른 문단 ${nf(s.paras.length)}`);
  if (s.table) parts.push(`표 ${s.table}${s.range && typeof xlRangeName === "function" ? `(범위 ${xlRangeName(s.range)})` : ""}`);
  if (s.cursor) { const txt = oneLine((state.texts || {})[s.cursor] || ""); parts.push(`커서 ${s.cursor}${txt ? ` 「${txt.length > 14 ? txt.slice(0, 14) + "…" : txt}」` : ""}`); }
  const text = parts.join(" · ") || "고른 자리 없음 — 문서에서 문단·표를 고르거나 커서를 두세요";
  if (E.sel.textContent !== text) {
    E.sel.textContent = text;
    E.sel.title = parts.length ? `요청과 함께 보내는 자리 — ${text}\n새 글·새 표는 커서 문단(칸 안이면 그 표) 뒤에 넣습니다` : "";
    E.sel.classList.toggle("has", parts.length > 0);
  }
  const key = JSON.stringify([A.styles.table.map((x) => [x.id, x.name]), A.styles.text.map((x) => [x.id, x.name]), s.table]);
  if (E.pickKey === key) return;
  E.pickKey = key;
  const opt = (name, value, title = "") => { const o = new Option(name, value); if (title) o.title = title; return o; };
  E.pickTable.replaceChildren(opt("정하지 않음", "", "에이전트가 보관함에서 고릅니다"), opt("기본 표", "builtin", "평범한 표(가는 괘선 · 음영 없음)"),
    ...A.styles.table.map((x) => opt(x.name || x.id, x.id, [x.rows ? `${x.rows}×${x.cols}` : "", x.blueprint ? "구조 있음" : ""].filter(Boolean).join(" · "))));
  if (s.table) E.pickTable.append(opt(`이 문서의 표(${s.table})`, "doc", "지금 고른 표의 서식을 따릅니다"));
  if (![...E.pickTable.options].some((o) => o.value === A.pick.table)) A.pick.table = "";
  E.pickTable.value = A.pick.table;
  E.pickText.replaceChildren(opt("자리 둘레 서식", "", "넣을 자리의 문단 모양 그대로"), ...A.styles.text.map((x) => opt(x.name || x.id, x.id, `항목 ${(x.items || []).length}`)));
  if (![...E.pickText.options].some((o) => o.value === A.pick.text)) A.pick.text = "";
  E.pickText.value = A.pick.text;
}

function agentDrawMats() {
  const A = AGENT, E = A.el, lock = !!A.busy || !!A.matBusy || !A.loaded;
  if (!E) return;
  E.mats.textContent = "";
  for (const m of A.materials) {
    const on = !A.matOff.has(m.id), chip = el("span", "ag-chip" + (on ? "" : " off")), name = el("button", "ag-chip-name", `${m.name || "자료"} · ${nf(m.chars || 0)}자${m.cut ? "(잘림)" : ""}${m.lossy ? " · 일부 원시값" : ""}`), x = el("button", "ag-chip-x", "×"); // lossy = 그대로 못 옮긴 엑셀 표시 형식·계산값 없는 수식(서버가 값 + 형식 글로 적음 — spec_일반편집 ② §10)
    chip.dataset.material = m.id;
    name.type = x.type = "button";
    name.disabled = x.disabled = lock;
    name.setAttribute("aria-pressed", String(on));
    name.title = `${on ? "이번 요청에 보냅니다" : "이번 요청에는 보내지 않습니다"} — 누르면 바꿉니다${m.cut ? "\n20만 자를 넘어 뒤를 잘랐습니다" : ""}${m.lossy ? `\n${m.note || "그대로 옮기지 못한 엑셀 표시 형식이 있어 저장된 값으로 적었습니다 — 단위·자릿수를 확인하세요"}` : ""}${m.head ? `\n\n${m.head}` : ""}`;
    name.onclick = () => { if (on) AGENT.matOff.add(m.id); else AGENT.matOff.delete(m.id); agentDrawMats(); };
    x.setAttribute("aria-label", `자료 ${m.name || ""} 지우기`);
    x.title = "이 자료를 지웁니다";
    x.onclick = () => agentMatDelete(m);
    chip.append(name, x);
    E.mats.append(chip);
  }
  const paste = hBtn("자료 붙여넣기", () => { AGENT.paste.open = !AGENT.paste.open; if (AGENT.paste.open) AGENT.shelf.open = false; agentDrawInput(); if (AGENT.paste.open) E.pasteText.focus(); },
    { cls: "btn sm" + (A.paste.open ? " on" : ""), disabled: lock, title: "글을 붙여 넣어 자료로 씁니다(아래에 글상자가 열립니다) — 에이전트는 자료에 있는 값만 옮깁니다" });
  paste.dataset.agAct = "paste";
  paste.prepend(agentIcon("paste"));
  paste.setAttribute("aria-pressed", String(A.paste.open));
  const file = hBtn("파일", () => agentMatPick(), { disabled: lock, title: `파일을 자료로 — ${(A.limits.ext || []).join("·") || "txt·md·csv·tsv·xlsx·docx·hwpx·pdf"}(${A.limits.materialMb || 20} MB 까지 · 글로 바꿔 읽습니다)` });
  file.dataset.agAct = "file";
  file.prepend(agentIcon("file"));
  const shelf = hBtn("라이브러리", () => agentShelfToggle(), { cls: "btn sm" + (A.shelf.open ? " on" : ""), disabled: lock && !A.shelf.open,
    title: "문서 라이브러리에 등록한 문서 · 추출한 MD 를 골라 자료로 가져옵니다(아래에 고르기가 열립니다 — 여럿 · 전체도 됩니다)" });
  shelf.dataset.agAct = "shelf";
  shelf.prepend(agentIcon("shelf"));
  shelf.setAttribute("aria-pressed", String(A.shelf.open));
  E.mats.append(paste, file, shelf);
  if (A.matBusy) { const run = el("span", "sl-run"); run.append(el("span", "sl-spin"), el("span", null, `「${short(A.matBusy.name || "자료", 20)}」 을(를) 자료로 읽는 중…`)); E.mats.append(run); }
  E.mats.append(el("span", "ag-mat-msg", A.matMsg));
}

function agentSendSync() { // 「보내기」 단추와 그 옆 글(못 보내는 까닭 · 도는 중)
  const A = AGENT, E = A.el;
  if (!E) return;
  const off = A.busy ? "" : A.err && !A.loaded ? A.err : !A.loaded ? "에이전트 상태를 읽는 중…" : !A.hwpx ? "hwpx 문서만 됩니다" : !A.enabled ? "LLM 을 쓸 수 없습니다" : "";
  E.send.disabled = !!A.busy || !!off || !A.draft.trim();
  E.run.hidden = !A.busy;
  if (A.busy) E.run.querySelector(".ag-run-text").textContent = agentBusyText(A.busy);
  E.why.textContent = off;
}

function agentDrawInput() {
  const A = AGENT, E = A.el;
  if (!E) return;
  E.policy.hidden = A.policy.apply !== false;
  E.policy.title = A.policy.why || "이 워크플로우의 원본 문서는 바꾸지 않습니다 — 제안은 볼 수 있지만 문서에 반영할 수 없습니다";
  agentSelDraw();
  agentDrawMats();
  E.paste.hidden = !A.paste.open;
  if (E.pasteName.value !== A.paste.name) E.pasteName.value = A.paste.name;
  if (E.pasteText.value !== A.paste.text) E.pasteText.value = A.paste.text;
  if (E.text.value !== A.draft) E.text.value = A.draft;
  if (A.limits.text) E.text.maxLength = A.limits.text;
  for (const x of [E.text, E.pickTable, E.pickText, E.pasteName, E.pasteText]) x.disabled = !!A.busy;
  E.pasteAdd.disabled = !!A.busy || !!A.matBusy || !A.paste.text.trim();
  agentShelfDraw();
  agentSendSync();
}

async function agentMatAdd(opts, name) { // 자료 하나 올리기(붙여 넣은 글 · 파일) → 됐나
  const A = AGENT;
  if (A.matBusy || !A.loaded || !state.id) return false;
  A.matBusy = { name };
  A.matMsg = "";
  agentDrawMats();
  let m = null, err = null;
  try { m = await api(agentUrl("/material"), opts); } catch (e) { err = e; }
  if (A !== AGENT) return false;
  A.matBusy = null;
  if (m && m.id) {
    A.materials = [...A.materials.filter((x) => x.id !== m.id), m];
    A.matOff.delete(m.id);
    if (m.reused) toast(`같은 자료가 이미 있습니다 — 「${m.name || "자료"}」 을(를) 그대로 씁니다`);
  } else A.matMsg = `자료를 넣지 못했습니다: ${agentErr(err)}`;
  agentDrawInput();
  return !!(m && m.id);
}
async function agentPasteAdd() {
  const P = AGENT.paste, text = P.text, name = P.name.trim();
  if (!text.trim()) return;
  if (await agentMatAdd({ method: "POST", headers: H_JSON, body: JSON.stringify({ ...(name ? { name } : {}), text }) }, name || "붙여 넣은 글")) {
    Object.assign(AGENT.paste, { open: false, name: "", text: "" });
    agentDrawInput();
  }
}
function agentMatPick() {
  const inp = el("input");
  inp.type = "file";
  inp.accept = (AGENT.limits.ext || []).map((x) => (String(x).startsWith(".") ? x : `.${x}`)).join(",") || AG_FILES;
  inp.onchange = () => {
    const f = inp.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    agentMatAdd({ method: "POST", body: fd }, f.name);
  };
  inp.click();
}
async function agentMatDelete(m) {
  const A = AGENT;
  if (A.busy || A.matBusy) return;
  let left = null;
  try { left = await api(agentUrl(`/material/${encodeURIComponent(m.id)}`), { method: "DELETE" }); }
  catch (e) { if (A !== AGENT) return; if (e.status !== 404 || e.message === "Not Found") { A.matMsg = `자료를 지우지 못했습니다: ${agentErr(e)}`; agentDrawMats(); return; } } // 이미 없는 자료(404)는 지운 것으로
  if (A !== AGENT) return;
  A.materials = left && Array.isArray(left.materials) ? left.materials : A.materials.filter((x) => x.id !== m.id); // 서버가 남은 자료 목록을 돌려준다
  A.matOff.delete(m.id);
  A.matMsg = "";
  agentDrawMats();
}

// ---- 문서 라이브러리에서 고르기 ------------------------------------------------------------------------------------------------
// 2026-11-24 사용자 "에이전트에서는 라이브러리에서 등록한 파일들을 선택해서 참조할 수 있도록 해줘, 전체 해도 되고"(spec_양식작성 ② §4 「에이전트 보기의 고르기」 · design.md §30).
// 입력 칸 위에 펴지는 칸(.ag-lib — 「자료 붙여넣기」 와 같은 자리 · 창 아님). 목록 = GET /api/doclib(문서 라이브러리는 따로 선 서버 — 8114 가 HTTP 로 읽어 준다) ·
// 가져오기 = 고른 것마다 차례로 POST …/agent/material/library {extract | doc}(form_write.js 의 「자료 가져오기」 열과 같은 끝점 — 가져온 것은 같은 자료 저장소에 놓여 자료 칩이 된다).
// 고를 것 = 문서마다 끝난 추출(MD) · 끝난 추출이 없는 문서는 원본 파일(글로 읽을 수 있는 형식만 — 서버의 raw). 「가져옴」 = 추출은 자료 메모의 추출 id(「(x…)」) · 원본은 같은 sha256.
const AG_LIB_HELP = "문서 라이브러리(자료 문서를 보관하고 자료 추출을 하는 따로 선 서버)에 등록한 문서를 골라 이 문서의 자료로 가져옵니다 — 가져온 자료는 아래 자료 칩이 되고 요청과 함께 에이전트에 갑니다(칩을 눌러 이번 요청에서 뺄 수 있습니다).\n"
  + "고르는 것: 문서마다 끝난 자료 추출(MD — 뽑을 범위마다 하나). 추출이 아직 없는 문서는 원본 파일을 글로 읽어 가져옵니다(pdf · docx · hwpx — 그림 · 수식은 빠지고 긴 문서는 앞부분만: hwp 와 20 MB 를 넘는 파일은 추출한 뒤에).\n"
  + "「전체 선택」 = 아직 가져오지 않은 것 모두 · 문서 이름 줄의 체크 = 그 문서의 것 모두. 자료는 문서마다 30개까지 둘 수 있어 넘치면 거기서 멈추고 못 가져온 수를 알립니다.\n"
  + "문서를 올리거나 새로 추출하려면 「열기」 로 문서 라이브러리의 화면을 엽니다(새 탭). 문서는 바뀌지 않습니다.";
const AG_LIB_DOWN = "문서 라이브러리 서버가 꺼져 있습니다 — 띄우개 tools/start_doclib.ps1 로 띄운 뒤 「새로 고침」 을 누르세요";
const agentShelfSize = (n) => (n >= 2 ** 20 ? `${(n / 2 ** 20).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);
function agentShelfItems(d) { // 그 문서에서 고를 것 → [{key, body(요청 본문), name(자료 이름 — 알림에), e(추출) | raw, got(이미 이 문서의 자료), off(못 고르는 까닭)}]
  const mats = AGENT.materials, base = String(d.name || "문서"), xs = d.extracts || [];
  if (xs.length) return xs.map((e) => ({ key: `x:${e.id}`, body: { extract: e.id }, name: `${base} — ${e.focus || "문서 전체"}`, e, got: mats.some((m) => (m.note || "").includes(`(${e.id})`)), off: "" }));
  const mb = AGENT.limits.materialMb || 20;
  const off = d.raw ? "" : (d.bytes || 0) > mb * 2 ** 20 ? `원본 파일이 ${mb} MB 를 넘습니다 — 문서 라이브러리에서 자료 추출(MD)을 한 뒤 가져오세요`
    : `${d.ext || "이 형식의"} 원본은 글로 읽지 못합니다 — 문서 라이브러리에서 자료 추출(MD)을 한 뒤 가져오세요`;
  return [{ key: `d:${d.id}`, body: { doc: d.id }, name: base, raw: true, got: !!d.sha256 && mats.some((m) => m.sha256 === d.sha256), off }];
}
const agentShelfAll = () => (((AGENT.shelf.data || {}).docs) || []).flatMap((d) => agentShelfItems(d));
function agentShelfToggle() {
  const S = AGENT.shelf;
  S.open = !S.open;
  if (S.open) { AGENT.paste.open = false; S.msg = ""; agentShelfLoad(); } // 펴는 칸은 하나만(입력 영역이 낮다) · 열 때마다 목록을 다시 읽는다(그 사이 끝난 추출)
  agentDrawInput();
}
async function agentShelfLoad() {
  const A = AGENT, S = A.shelf;
  if (S.loading) return;
  S.loading = true;
  S.err = "";
  agentShelfDraw();
  let r = null;
  try { r = await api("/api/doclib"); } catch (e) { S.err = agentErr(e); }
  if (A !== AGENT) return;
  S.loading = false;
  if (r) {
    S.data = r;
    const keys = new Set(agentShelfAll().filter((i) => !i.got && !i.off).map((i) => i.key));
    for (const k of [...S.picks]) if (!keys.has(k)) S.picks.delete(k); // 그 사이 없어졌거나 이미 가져온 것
  }
  agentShelfDraw();
}
function agentShelfDraw() {
  const A = AGENT, E = A.el, S = A.shelf;
  if (!E || !E.shelf) return;
  E.shelf.hidden = !S.open;
  if (!S.open) { E.shelf.textContent = ""; return; }
  const lock = !!A.busy || !!A.matBusy || !!S.busy || !A.loaded, L = S.data, docs = (L && L.docs) || [], max = A.limits.materials || 30;
  const old = E.shelf.querySelector(".ag-lib-list"), top = old ? old.scrollTop : 0;
  const head = el("div", "ag-lib-head");
  head.append(el("strong", "ag-lib-title", "문서 라이브러리"));
  if (typeof hHelp === "function") head.append(hHelp("문서 라이브러리에서 자료 고르기 안내", AG_LIB_HELP));
  const count = el("span", "ag-lib-count", `이 문서의 자료 ${nf(A.materials.length)}/${nf(max)}`);
  count.title = `자료는 문서마다 ${nf(max)}개까지 둘 수 있습니다`;
  const open = hBtn("열기", () => { if (L && L.url) window.open(`${L.url}/`, "_blank", "noopener"); }, { disabled: !(L && L.alive), title: L && L.alive ? "문서 라이브러리의 화면을 새 탭에 엽니다 — 문서 올리기 · 자료 추출" : AG_LIB_DOWN });
  open.dataset.agAct = "shelfOpen";
  const again = hBtn("새로 고침", () => agentShelfLoad(), { disabled: S.loading || !!S.busy, title: "문서 라이브러리의 목록을 다시 읽습니다" });
  again.dataset.agAct = "shelfReload";
  head.append(count, again, open, hBtn("닫기", () => { AGENT.shelf.open = false; agentDrawInput(); }));
  const kids = [head], note = (text, cls = "") => { const p = el("p", "ag-lib-state" + (cls ? ` ${cls}` : ""), text); p.setAttribute("role", "status"); return p; };
  const items = agentShelfAll(), can = items.filter((i) => !i.got && !i.off), picked = can.filter((i) => S.picks.has(i.key));
  if (S.err) kids.push(note(`문서 라이브러리의 목록을 읽지 못했습니다 — ${S.err}`, "down"));
  else if (!L) kids.push(note("문서 라이브러리의 목록을 읽는 중…"));
  else if (!L.alive) { const p = note(AG_LIB_DOWN, "down"); p.title = L.why || ""; kids.push(p); }
  else if (!docs.length) kids.push(note("문서 라이브러리에 등록한 문서가 없습니다 — 「열기」 로 문서 라이브러리에서 문서를 올리세요"));
  else {
    const list = el("div", "ag-lib-list");
    const row = (cls, on, some, off, fn, title = "") => { // 체크 한 줄(label) — 체크 상자 + 뒤에 붙일 것
      const l = el("label", `ag-lib-row ${cls}` + (off ? " is-off" : "")), c = el("input");
      c.type = "checkbox"; c.checked = on; c.indeterminate = !on && some; c.disabled = off || lock;
      c.onchange = () => { fn(c.checked); agentShelfDraw(); };
      if (title) l.title = title;
      l.append(c);
      return l;
    };
    const set = (its, on) => { for (const i of its) { if (on) S.picks.add(i.key); else S.picks.delete(i.key); } };
    const tag = (cls, text, title = "") => { const t = el("span", "ag-lib-tag" + (cls ? ` ${cls}` : ""), text); if (title) t.title = title; return t; };
    const all = row("is-all", can.length > 0 && picked.length === can.length, picked.length > 0, !can.length, (on) => set(can, on), can.length ? "아직 가져오지 않은 것을 모두 고릅니다" : "더 가져올 것이 없습니다");
    all.dataset.agLib = "all";
    const gotN = items.filter((i) => i.got).length;
    all.append(el("span", "ag-lib-name", "전체 선택"), el("span", "ag-lib-meta", `문서 ${nf(docs.length)}개 · 고를 수 있는 것 ${nf(can.length)}개${gotN ? ` · 가져옴 ${nf(gotN)}개` : ""}`));
    list.append(all);
    for (const d of docs) {
      const its = agentShelfItems(d), dcan = its.filter((i) => !i.got && !i.off), dpick = dcan.filter((i) => S.picks.has(i.key)), xs = d.extracts || [];
      const dr = row("is-doc", dcan.length > 0 && dpick.length === dcan.length, dpick.length > 0, !dcan.length, (on) => set(dcan, on), d.name || "");
      dr.dataset.agLib = `doc:${d.id}`;
      dr.append(el("span", "ag-lib-name", d.name || "문서"), el("span", "ag-lib-meta", [d.pages ? `${nf(d.pages)}쪽` : "", xs.length ? `추출 ${nf(xs.length)}개` : "추출 전", d.running ? `추출 중 ${nf(d.running)}개` : ""].filter(Boolean).join(" · ")));
      list.append(dr);
      for (const i of its) {
        const e = i.e, ir = row("is-item", !i.got && !i.off && S.picks.has(i.key), false, i.got || !!i.off, (on) => set([i], on),
          i.off || (i.got ? "이미 이 문서의 자료입니다" : i.raw ? "원본 파일을 글로 읽어 자료로 가져옵니다(그림 · 수식은 빠집니다 — 자료 추출을 하면 MD 로 가져올 수 있습니다)" : "이 추출의 MD 를 자료로 가져옵니다"));
        ir.dataset.agLib = i.key;
        ir.append(el("span", "ag-lib-name", e ? e.focus || "문서 전체" : "원본 파일"),
          el("span", "ag-lib-meta", e ? [e.span ? `쪽 ${e.span[0]}–${e.span[1]}` : "", `${nf(e.chars || 0)}자`].filter(Boolean).join(" · ") : [d.ext || "", d.bytes ? agentShelfSize(d.bytes) : ""].filter(Boolean).join(" · ")));
        if (e && e.open) ir.append(tag("warn", `확인 필요 ${nf(e.open)}`, "추출하며 사람이 볼 것으로 남긴 곳(잘렸을 수 있는 그림 · 못 바꾼 수식 …) — 문서 라이브러리에서 봅니다"));
        if (i.got) ir.append(tag("got", "가져옴"));
        else if (i.off) ir.append(tag("", "추출 뒤에", i.off));
        list.append(ir);
      }
    }
    kids.push(list);
  }
  const foot = el("div", "ag-lib-foot"), n = picked.length;
  const take = hBtn(n ? `가져오기 (${nf(n)})` : "가져오기", () => agentShelfTake(), { cls: "btn sm primary", disabled: !n || lock,
    title: !n ? "가져올 것을 고르세요" : `고른 ${nf(n)}개를 이 문서의 자료로 가져옵니다 — 문서는 바뀌지 않습니다` });
  take.dataset.agAct = "shelfTake";
  foot.append(take);
  if (S.busy) { const run = el("span", "sl-run"); run.append(el("span", "sl-spin"), el("span", null, `「${short(S.busy.name || "자료", 24)}」 가져오는 중 (${nf(S.busy.i)}/${nf(S.busy.n)})…`)); foot.append(run); }
  else if (S.msg) { const m = el("span", "ag-lib-msg" + (S.bad ? " bad" : ""), S.msg); m.setAttribute("role", "status"); foot.append(m); }
  kids.push(foot);
  E.shelf.replaceChildren(...kids);
  const list = E.shelf.querySelector(".ag-lib-list");
  if (list && top) list.scrollTop = top;
}
async function agentShelfTake() { // 고른 것을 차례로 가져온다 — 자료 한도에 닿으면 멈추고 못 가져온 수를 알린다(문서 라이브러리 서버에 닿지 못하면 거기서 멈춤)
  const A = AGENT, S = A.shelf, max = A.limits.materials || 30;
  const todo = agentShelfAll().filter((i) => S.picks.has(i.key) && !i.got && !i.off);
  if (!todo.length || S.busy || A.busy || A.matBusy || !A.loaded || !state.id) return;
  const epoch = state.epoch, bad = [];
  let ok = 0, same = 0, left = 0, full = false, down = false;
  S.msg = "";
  for (let k = 0; k < todo.length; k += 1) {
    if (A.materials.length >= max) { left = todo.length - k; full = true; break; }
    const it = todo[k];
    S.busy = { i: k + 1, n: todo.length, name: it.name };
    agentDrawInput();
    let m = null, err = null;
    try { m = await api(agentUrl("/material/library"), { method: "POST", headers: H_JSON, body: JSON.stringify(it.body) }); } catch (e) { err = e; }
    if (A !== AGENT || epoch !== state.epoch) return;
    if (m && m.id) {
      A.materials = [...A.materials.filter((x) => x.id !== m.id), m];
      A.matOff.delete(m.id);
      S.picks.delete(it.key);
      if (m.reused) same += 1; else ok += 1;
    } else {
      bad.push(`「${short(it.name, 24)}」 — ${agentErr(err)}`);
      if (err && err.status === 502) { left = todo.length - k - 1; down = true; break; } // 문서 라이브러리 서버에 닿지 못함 — 남은 것도 같은 까닭으로 실패한다
    }
  }
  S.busy = null;
  S.bad = bad.length > 0 || left > 0;
  S.msg = [ok ? `자료 ${nf(ok)}개를 가져왔습니다` : "", same ? `이미 있는 자료 ${nf(same)}개는 그대로 씁니다` : "", bad.length ? `가져오지 못함 ${nf(bad.length)}개: ${bad.slice(0, 2).join(" / ")}${bad.length > 2 ? " …" : ""}` : "",
    full ? `자료는 ${nf(max)}개까지 둘 수 있습니다 — 남은 ${nf(left)}개는 가져오지 못했습니다(안 쓰는 자료를 지우고 다시 가져오세요)` : left ? `남은 ${nf(left)}개는 가져오지 않았습니다` : ""].filter(Boolean).join(" · ");
  if (ok && !S.bad) toast(`문서 라이브러리에서 자료 ${nf(ok)}개를 가져왔습니다`);
  agentDrawInput();
  if (down) agentShelfLoad();
  if (ok && typeof FW === "object" && FW && FW.gw && typeof fwRead === "function") // 「양식 작성」 의 대시보드 · 「자료 가져오기」 · 「지침 작성」 열이 같은 자료를 보인다(form_write.js — 읽어 둔 것이 있을 때만 다시)
    fwRead(true).then(() => { if (typeof fwRedraw === "function") fwRedraw(); if (typeof dashDraw === "function") dashDraw(); }).catch(() => {});
}

async function agentSend(edit = false) { // 한 턴 — 요청 글 + 고른 자료 + 고른 자리 + 고른 서식 → 답과 제안(문서는 안 바뀐다). 동기 응답이라 10~90초 걸릴 수 있다
  const A = AGENT, text = A.draft.trim();
  if (!text || A.busy || !A.loaded || !A.enabled || !A.hwpx || !state.id) return;
  if (edit !== true && typeof agentWorkSay === "function" && agentWorkSay(text)) return; // 단계가 있는 TASK — 진행 에이전트가 먼저 읽고, 글·표 요청이면 이 함수로 되넘긴다(edit true: spec_작업에이전트 ② §1 「넘기기」)
  const epoch = state.epoch, sel = slSelection();
  const body = { text, materials: A.materials.filter((m) => !A.matOff.has(m.id)).map((m) => m.id), selection: sel,
    styles: { table: A.pick.table === "doc" ? (sel.table ? `doc:${sel.table}` : null) : A.pick.table || null, text: A.pick.text || null } };
  A.busy = { text, t0: performance.now(), timer: 0 };
  A.lost = null;
  A.draft = "";
  agentDrawStatus();
  agentDrawTalk(true);
  agentDrawInput();
  A.busy.timer = setInterval(() => { if (A !== AGENT || !A.busy || !A.el) return; for (const e of A.el.root.querySelectorAll(".ag-run-text.live")) e.textContent = agentBusyText(A.busy); }, 1000);
  let r = null, err = null;
  try {
    await flushAll(); // 타자 중인 글을 서버에 먼저 — 에이전트는 서버 문서를 읽는다
    r = await api(agentUrl("/turn"), { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
  } catch (e) { err = e; }
  clearInterval(A.busy.timer);
  if (A !== AGENT || epoch !== state.epoch) return; // 그 사이 다른 문서
  A.busy = null;
  const failed = !r && err && err.body && err.body.turn ? err.body.turn : null; // LLM 호출 실패(502) — 서버가 그 턴을 까닭(error)과 함께 저장해 돌려준다: 대화에 그대로 남긴다
  if (r && r.turn) A.turns.push(r.turn);
  else if (failed) A.turns.push({ ...failed, error: failed.error || agentErr(err) });
  else A.lost = { text, error: agentErr(err || new Error("서버가 턴을 돌려주지 않았습니다")) };
  if (!(r && r.turn) && !A.draft.trim()) A.draft = text; // 요청 글을 글상자에 되돌려 둔다(그 사이 새로 쓴 글이 있으면 그대로)
  agentDrawStatus();
  agentDrawTalk(true);
  agentDrawInput();
  const last = A.el && r && r.turn ? A.el.talk.querySelector(".ag-turn:last-child") : null; // 새 답은 그 턴의 머리(요청 글 · 답)부터 보이게 — 카드가 많으면 아래로 굴려 본다
  if (last) A.el.talk.scrollTop += last.getBoundingClientRect().top - A.el.talk.getBoundingClientRect().top - 8;
  if ($("paneAgent").hidden && r && r.turn) toast(`에이전트의 답이 왔습니다 — 제안 ${nf((r.turn.proposals || []).length)}개(「에이전트」 에서 봅니다)`);
}

async function agentClear() { // 「비우기」 — 한 번 누르면 채비(4초), 한 번 더 누르면 지운다
  const A = AGENT;
  if (!A.loaded || A.busy || A.applying) return;
  if (performance.now() >= A.clearArm) {
    A.clearArm = performance.now() + 4000;
    agentDrawStatus();
    setTimeout(() => { if (A === AGENT) agentDrawStatus(); }, 4100);
    return;
  }
  A.clearArm = 0;
  try { await api(agentUrl(), { method: "DELETE" }); }
  catch (e) { toast(`대화를 비우지 못했습니다: ${agentErr(e)}`, true); if (A === AGENT) agentDrawStatus(); return; }
  if (A !== AGENT) return;
  Object.assign(A, { turns: [], lost: null, choice: {}, fills: {}, req: {}, prop: null, materials: [], local: [] }); // 서버는 대화·제안·자료를 모두 지운다(화면에만 둔 보고·실행 카드도)
  A.matOff.clear();
  if (heads.dlg === "agentProp" || heads.dlg === "agentGuide") headsColClose(true);
  agentHit(null);
  agentDraw();
  agentLoad(true); // 정책·보관함·남은 자료는 서버가 가진 대로
}

// ---- 반영 — 서버에 저장한 제안을 실행한다(클라이언트는 무엇을 넣을지 보내지 않는다) ------------------------------------------------------
async function agentApply(tid, pid) {
  const A = AGENT, t = agentTurnOf(tid), p = agentPropOf(t, pid);
  if (p && p.type === "styleCopy") { agentStyleCopy(tid, pid); return; } // 문서를 바꾸지 않는 제안 — 쓰기 정책(원본 문서)에 걸리지 않고, 문서 갱신 길(structOp)도 타지 않는다
  if (!p || A.applying || A.policy.apply === false || ["applied", "stale", "closed"].includes(p.state)) return;
  if (state.busy) { toast("다른 편집이 끝난 뒤 다시 누르세요"); return; }
  const v = p.view || {}, picks = p.type === "tableFill" ? { fills: (v.fills || []).filter((f) => agentFillPicks(p).has(f.cell)).map((f) => f.cell) } : null;
  if (picks && !picks.fills.length) return;
  const epoch = state.epoch;
  A.applying = pid;
  agentHit(null);
  agentDrawStatus();
  agentDrawTalk();
  agentPropSync();
  let r = null, err = null;
  try {
    await flushAll(); // 대기 중인 글 반영이 편집 차례를 올린다 — 그 뒤의 차례를 보낸다
    if (A === AGENT && epoch === state.epoch) {
      A.req[pid] = A.req[pid] || agentUuid(); // 답을 받을 때까지 같은 번호 — 두 번 눌러도 서버가 한 번으로 친다
      structOp.lastError = null;
      r = await structOp("agent/apply", { turn: tid, proposal: pid, ...(picks ? { picks } : {}), expectedRev: state.serverRev, requestId: A.req[pid] }); // 구조 편집 응답 — 바뀐 블록만 다시 그림
      err = r ? null : structOp.lastError || null;
    }
  } finally { if (A === AGENT) A.applying = null; }
  if (A !== AGENT || epoch !== state.epoch) return;
  if (r || err) delete A.req[pid];
  const undo = " · 도구 줄의 실행 취소로 되돌릴 수 있습니다";
  if (r) {
    const ap = r.applied || {}, made = ap.made || {}, filled = ap.filled || {}, written = ap.written || {}, skipped = filled.skipped || [];
    const nWritten = (Array.isArray(written.paras) ? written.paras.length : Number(written.paras) || 0) || (v.lines || []).length;
    p.state = "applied";
    if (p.choiceGroup) for (const x of agentGroup(t, p)) if (x !== p && (x.state || "open") === "open") x.state = "closed"; // 후보 묶음은 하나만 — 나머지는 끝난 것(서버도 그렇게 적는다)
    p.applied = { table: made.table || (p.type === "tableFill" || p.type === "restyle" ? v.table : null) || null, paras: Array.isArray(written.paras) ? written.paras : p.type === "restyle" ? v.paras || [] : [], cells: filled.cells || [], excel: ap.excel || null,
      note: p.type === "tableFill" ? `${nf((filled.cells || picks.fills).length)}칸 채움${skipped.length ? ` · 건너뜀 ${nf(skipped.length)}${skipped[0] && skipped[0].why ? `(${skipped[0].why})` : ""}` : ""}` : "" };
    toast((p.type === "tableNew" ? `새 표${made.table ? ` ${made.table}` : ""}${made.rows ? `(${made.rows}×${made.cols})` : ""}를 넣었습니다` : p.type === "tableFill" ? `표 ${v.table} — ${p.applied.note}` : p.type === "write"
      ? `문단 ${nf(nWritten)}개를 썼습니다` : "서식을 입혔습니다") + undo);
  } else if (err && err.status === 409) { // 문서가 바뀜 · 이미 반영함 · 다른 후보를 반영함 — 서버가 준 까닭 그대로 보이고, 서버의 제안 상태로 맞춘다(다른 창에서 이미 반영했을 수 있다)
    p.state = "stale";
    p.why = err.message && !/^409\b/.test(err.message) ? err.message : AG_STALE;
    agentStatesSync();
  }
  else if (err && err.status === 403) A.policy = { apply: false, why: err.message };
  else if (err) { p.state = "failed"; p.why = err.message; }
  agentDraw();
  agentPropSync();
}

// ---- 서식 복사 제안(type styleCopy — spec_서식복사 ② §6): 사람이 「서식을 복사·저장해 달라」 고 할 때 에이전트가 낸다. 문서는 바뀌지 않는다 ---------------------------------
const agentStyleSum = (x) => { const s = { verify: x.verify || null }; if (x.dual) { s.verifyDocx = x.verifyDocx || null; if (x.docx != null) s.docx = x.docx; } return s; }; // style_lib.js styleVerifyEls 가 읽는 꼴(형식마다의 검증 요약)
const agentStyleDone = (x) => !!x.gone || (!!x.seen && (typeof slWatchSettled !== "function" || slWatchSettled({ gone: false, verify: x.verify, verifyDocx: x.verifyDocx, docx: x.docx, dual: x.dual })));

function agentStyleCopyEl(p) { // 카드의 몸 — 저장 전: 무엇을 저장하나(view.picks) · 저장 뒤: 서식마다 검증 꼬리표(형식마다 — 2초마다 다시 읽음) · 못 저장한 것의 까닭
  const box = el("div", "ag-styles"), v = p.view || {}, ap = p.applied || {}, saved = ap.styles || [], failed = ap.failed || [];
  const kind = (k) => (typeof slPickName === "function" ? slPickName(k) : (typeof SL_KIND === "object" && SL_KIND[k && k.kind]) || (k && k.kind) || "서식"); // 표지 서식 · 내용 서식 · 쪽 설정 · 테이블 서식 · 문단 서식(서식 관리자의 갈래 이름 — spec_서식복사 ② §12)
  if (!saved.length) {
    for (const k of v.picks || []) {
      const row = el("div", "ag-style"), what = k.kind === "table" ? `표 ${k.table || ""}${k.blueprint ? " · 구조까지" : ""}` : k.kind === "page" ? "쪽 설정 · 본문 바탕 글 모양" : k.kind === "cover" ? "문서 첫 쪽의 배치"
        : k.template != null ? `개요 템플릿 ${k.templateName || k.template}` : `문단 ${nf((k.paras || []).length)}개`;
      row.dataset.kind = k.kind || "";
      row.append(el("span", "hb", kind(k)), el("b", null, k.name || "(이름 없음)"), el("span", "ag-style-what", what));
      box.append(row);
    }
  }
  for (const x of saved) {
    const row = el("div", "ag-style saved");
    row.dataset.style = x.id;
    row.dataset.kind = x.kind || "";
    row.append(el("span", "hb", kind((v.picks || [])[x.pick] || x)), el("b", null, x.name || x.id));
    if (x.gone) row.append(el("span", "ag-state", "보관함에서 지워짐"));
    else if (x.seen && typeof styleVerifyEls === "function") row.append(...styleVerifyEls(agentStyleSum(x)));
    else row.append(el("span", "ag-state", "검증 상태를 읽는 중…"));
    box.append(row);
  }
  for (const f of failed) box.append(el("p", "ag-state err", `저장하지 못함 — ${f.name || "서식"}: ${f.why || "까닭 모름"}`));
  if (ap.late) box.append(el("p", "ag-state", "검증이 아직 돕니다 — 서식 관리자에서 확인"));
  if (saved.length && !ap.watching && !ap.watched) setTimeout(() => agentStyleWatch(p), 0); // 다시 연 대화의 저장된 제안도 한 번 읽는다
  return box;
}

async function agentStyleWatch(p) { // 저장한 서식마다 GET /api/styles/{sid} 를 2초마다 — 두 형식 다 끝나거나 180초(그 뒤는 서식 관리자에서)
  const A = AGENT, ap = p.applied;
  if (!ap || ap.watching || ap.watched || !(ap.styles || []).length || typeof styleUrl !== "function") return;
  ap.watching = true;
  const t0 = performance.now(), sig = () => JSON.stringify(ap.styles.map((x) => [x.seen, x.gone, x.verify && x.verify.status, x.verifyDocx && x.verifyDocx.status, x.docx]));
  while (A === AGENT) {
    const was = sig();
    for (const x of ap.styles.filter((s) => !agentStyleDone(s))) {
      try {
        const m = await api(styleUrl(x.id));
        Object.assign(x, { seen: true, name: m.name || x.name, verify: m.verify || null, verifyDocx: m.verifyDocx || null, dual: "verifyDocx" in m || "docx" in m, docx: "docx" in m ? !!m.docx : null });
      } catch (e) { if (e.status === 404 && e.message !== "Not Found") x.gone = true; else x.seen = x.seen || false; } // 그 사이 지워짐 · 그 밖의 오류는 다음 차례에 다시
    }
    if (A !== AGENT) return;
    const done = ap.styles.every(agentStyleDone), late = !done && performance.now() - t0 > 180000;
    if (done || late) { ap.watching = false; ap.watched = true; ap.late = late; agentDrawTalk(); return; }
    if (sig() !== was) agentDrawTalk();
    await new Promise((r) => setTimeout(r, 2000));
  }
}

async function agentStyleCopy(tid, pid) { // 「보관함에 저장」 — 같은 반영 끝점(agent/apply)이지만 응답에 문서 조각이 없다: structOp 의 문서 갱신 길을 타지 않고 따로 부른다(문서 차례 그대로 · 실행 취소 없음 · 원본 문서에서도 된다)
  const A = AGENT, t = agentTurnOf(tid), p = agentPropOf(t, pid);
  if (!p || A.applying || ["applied", "stale", "closed"].includes(p.state)) return;
  const epoch = state.epoch;
  A.applying = pid;
  agentHit(null);
  agentDrawStatus();
  agentDrawTalk();
  let r = null, err = null;
  try {
    await flushAll(); // 타자 중인 글을 서버에 먼저 — 대상 지문(고른 표·문단의 글·서식)을 서버 문서로 견준다
    if (A === AGENT && epoch === state.epoch) {
      A.req[pid] = A.req[pid] || agentUuid(); // 답을 받을 때까지 같은 번호 — 두 번 눌러도 서버가 한 번으로 친다
      r = await api(agentUrl("/apply"), { method: "POST", headers: H_JSON, body: JSON.stringify({ turn: tid, proposal: pid, expectedRev: state.serverRev, requestId: A.req[pid] }) });
    }
  } catch (e) { err = e; }
  finally { if (A === AGENT) A.applying = null; }
  if (A !== AGENT || epoch !== state.epoch) return;
  if (r || err) delete A.req[pid];
  if (r) {
    const ap = r.applied || {}, saved = ap.styles || [], failed = ap.failed || [];
    p.applied = { styles: saved.map((x) => ({ ...x })), failed };
    if (saved.length) { // 하나라도 저장되면 「반영됨」(서버도 그렇게 적는다)
      p.state = ap.state && ap.state !== "open" ? ap.state : "applied";
      delete p.why;
      toast(`서식 ${nf(saved.length)}개를 보관함에 저장했습니다${failed.length ? ` · ${nf(failed.length)}개는 저장하지 못했습니다` : ""} — PDF 검증이 뒤에서 돕니다`, !!failed.length);
      if (typeof STYLE === "object") STYLE.list = null; // 서식 관리자의 목록은 다음에 열 때 다시 읽는다
      agentStyleWatch(p);
      setTimeout(() => agentStylesRefresh(), 0); // 입력의 서식 고르기에도 새 서식
    } else { p.state = "failed"; p.why = (failed[0] && failed[0].why) || "저장된 서식이 없습니다"; } // 모두 실패 — 제안은 열어 둔다(다시 누를 수 있다)
  } else if (err && err.status === 409) { // 문서가 바뀜 · 이미 저장함 — 서버가 준 까닭 그대로, 서버의 제안 상태로 맞춘다
    p.state = "stale";
    p.why = err.message && !/^409\b/.test(err.message) ? err.message : AG_STALE;
    agentStatesSync();
  } else if (err) { p.state = "failed"; p.why = agentErr(err); }
  agentDraw();
}

async function agentStatesSync() { // 409 뒤 — 서버가 적어 둔 제안 상태(applied · closed · stale)로 맞춘다. 서버가 아직 open 이라 하는 제안은 화면 것 그대로(방금 받은 까닭이 남는다)
  const A = AGENT, epoch = state.epoch;
  let r = null;
  try { r = await api(agentUrl()); } catch { return; }
  if (A !== AGENT || epoch !== state.epoch) return;
  const by = new Map();
  for (const t of r.turns || []) for (const p of t.proposals || []) by.set(`${t.id}|${p.id}`, p);
  for (const t of A.turns) {
    for (const p of t.proposals || []) {
      const s = by.get(`${t.id}|${p.id}`);
      if (!s || !s.state || s.state === "open" || s.state === p.state) continue;
      p.state = s.state;
      if (s.applied) p.applied = { ...s.applied };
      if (s.state !== "stale") delete p.why;
    }
  }
  agentDraw();
  agentPropSync();
}

// ---- 2열 — 제안 미리보기(kind "agentProp") -----------------------------------------------------------------------------------
const agentPropOn = () => heads.dlg === "agentProp" && !!AGENT.prop;
function agentPropOpen(tid, pid) {
  const p = agentPropOf(agentTurnOf(tid), pid);
  if (!p) return;
  AGENT.prop = { turn: tid, proposal: pid };
  headsDlg("agentProp", `제안 미리보기 — ${AG_TYPE[p.type] || p.type}`, "문서는 「문서에 반영」 을 눌러야 바뀝니다");
  agentPropSync();
}

function agentGridEl(g) { // 표 후보 격자(보기만) — 구역 색은 「표 만들기」 미리보기와 같다(머리행 · 머리열 · 합계행)
  const lay = agentGridLayout(g), box = el("div", "tm-scroll"), t = el("table", "tm-grid"), tb = el("tbody"), trs = ((g && g.rows) || []).map(() => el("tr"));
  for (const x of lay.cells) {
    const td = el("td", x.r < (g.headerRows || 0) ? "head" : x.r >= lay.rows - (g.footRows || 0) ? "foot" : x.c < (g.headerCols || 0) ? "hcol" : null, x.cell.text || "");
    if (x.rs > 1) td.rowSpan = x.rs;
    if (x.cs > 1) td.colSpan = x.cs;
    trs[x.r].append(td);
  }
  tb.append(...trs);
  t.append(tb);
  box.append(t);
  return box;
}

function agentWhereEl(bits) { // 「넣을 자리 — 문단 p3 뒤 [자리로] · 서식 — …」
  const p = el("p", "agp-where");
  bits.filter(Boolean).forEach((b, i) => {
    if (i) p.append(" · ");
    p.append(b.text);
    if (b.go) p.append(hBtn("자리로", () => slGo(b.go), { title: "문서에서 그 자리로(열은 그대로)" }));
  });
  return p;
}

function agentPropFoot(t, p) { const foot = $("headsDlgFoot"); foot.textContent = ""; foot.append(agentActsEl(t, p, true)); }

function agentPropSync() { // 열이 제안 미리보기일 때만 — 그 자리에서 다시 그린다(고르기 · 반영 뒤). 상태는 AGENT 에 있어 열을 닫았다 열어도 같다
  if (!agentPropOn()) return;
  const A = AGENT, P = A.prop, t = agentTurnOf(P.turn), first = agentPropOf(t, P.proposal), tools = $("headsDlgTools"), body = $("headsDlgBody"), keep = body.scrollTop;
  tools.textContent = "";
  body.textContent = "";
  $("headsDlgFoot").textContent = "";
  if (!first) { body.append(el("p", "hnote pad", "이 제안은 지금 대화에 없습니다(대화를 비웠거나 다른 문서를 열었습니다).")); return; }
  const group = agentGroup(t, first), p = group.length > 1 ? agentChosen(t, group) : first, v = p.view || {}, wrap = el("div", "ta-wrap agp-wrap"), ident = el("div", "ta-ident");
  P.proposal = p.id;
  ident.append(el("span", "ag-tag", AG_TYPE[p.type] || p.type), el("b", null, group.length > 1 ? `표 구조 후보 ${group.length}개 — 하나만 반영` : p.title || ""));
  wrap.append(ident);
  if (group.length < 2 && p.summary) wrap.append(el("p", "hnote", p.summary));
  tools.append(el("span", "muted", `요청 ${agentWhen(t.at)} — 「${short(t.text || "", 28)}」`));
  if (p.type === "write") {
    wrap.append(agentWhereEl([v.after ? { text: `넣을 자리 — ${agentBlockName(v.after)} 뒤`, go: v.after } : null, { text: `방식 — ${AG_MODE[v.mode] || v.mode || ""}` }, { text: `서식 — ${agentStyleOf(v, "text")}` }]), agentChecksEl(p));
    const [tbl, tb] = hTable(["", "쓸 글", "근거"]);
    tbl.classList.add("agp-lines");
    (v.lines || []).forEach((ln, i) => {
      const lw = ln.warn || [], tr = el("tr", lw.length || (ln.source && !ln.quoted) ? "warn" : null), c0 = el("td", null, String(i + 1)), c1 = el("td", "agp-text", ln.text || ""), c2 = el("td", "wrap agp-src tfl-why");
      if (ln.itemName || ln.item) c0.append(" ", el("span", "hb", ln.itemName || ln.item)); // 그 줄에 입힐 글 서식 항목
      if (ln.source) { const q = el("q", ln.quoted ? null : "tfl-noquote", ln.source); q.title = ln.quoted ? "자료·선택 글에서 확인한 구절(글자 포함 검사 — 사실 검증은 아닙니다)" : "이 구절을 자료·선택 글에서 찾지 못했습니다 — 직접 확인하세요"; c2.append(q); }
      else c2.append(v.mode === "draft" ? "에이전트가 쓴 글" : "—");
      for (const w of lw) c2.append(el("span", "hb und", w));
      tr.append(c0, c1, c2);
      tb.append(tr);
    });
    wrap.append(el("h3", null, `쓸 글 ${nf((v.lines || []).length)}줄`), tbl);
  } else if (p.type === "tableNew") {
    const applied = group.some((x) => x.state === "applied"), cols = el("div", "agp-cols");
    wrap.append(agentWhereEl([v.after ? { text: `넣을 자리 — ${agentBlockName(v.after)} 뒤`, go: v.after } : null, { text: `서식 — ${agentStyleOf(v, "table")}` }]));
    for (const c of group) { // 후보 격자를 나란히 — 좁으면 아래로 접힌다
      const col = el("div", "agp-col" + (c.id === p.id ? " on" : "")), lab = el("label"), rb = el("input"), cv = c.view || {}, g = cv.grid || { rows: [] }, lay = agentGridLayout(g);
      col.dataset.cand = c.id;
      col.dataset.state = c.state || "open";
      if (group.length > 1) {
        rb.type = "radio"; rb.name = `agp-${t.id}-${c.choiceGroup}`; rb.value = c.id; rb.checked = c.id === p.id; rb.disabled = applied || !!A.applying;
        rb.onchange = () => { if (rb.checked) agentChoose(c); };
        lab.append(rb);
      }
      lab.append(el("span", null, `${c.title || "새 표"} · ${lay.rows}×${lay.cols}`));
      col.append(lab);
      if (c.state === "applied" || c.state === "closed") col.append(el("p", "ag-state", c.state === "applied" ? "문서에 반영한 후보" : "다른 후보를 반영함"));
      if (cv.why) col.append(el("p", "ag-why", cv.why));
      col.append(agentChecksEl(c), agentGridEl(g));
      cols.append(col);
    }
    wrap.append(cols);
  } else if (p.type === "tableFill") {
    wrap.append(agentWhereEl([{ text: `대상 — 표 ${v.table || ""}${v.rows ? ` · ${v.rows}×${v.cols}` : ""}${v.range && typeof xlRangeName === "function" ? ` · 범위 ${xlRangeName(v.range)}` : ""}${v.unit ? ` · 단위 ${v.unit}` : ""}`, go: v.table }]), agentChecksEl(p));
    if (v.answer) wrap.append(el("p", "hnote", `LLM: ${v.answer}`));
    agentFillList(wrap, t, p);
  } else {
    const paras = v.paras || [], texts = v.texts || [], item = v.itemName || v.item || "";
    wrap.append(agentWhereEl([v.table ? { text: `대상 — 표 ${v.table}${v.rows ? ` · ${v.rows}×${v.cols}` : ""}`, go: v.table } : { text: `대상 — 문단 ${nf(paras.length)}개`, go: paras[0] },
      { text: `서식 — ${agentStyleOf(v, v.table ? "table" : "text")}${item ? ` · 항목 ${item}` : ""}` }]), agentChecksEl(p));
    if (texts.length) { const ul = el("ul", "tfl-rej"); for (const x of texts.slice(0, 12)) ul.append(el("li", null, short(x, 60))); if (texts.length > 12) ul.append(el("li", null, `… 외 ${nf(texts.length - 12)}개`)); wrap.append(ul); }
    wrap.append(el("p", "hnote", "글·구조는 그대로 두고 모양(괘선·음영·글자·문단 모양)만 바꿉니다."));
  }
  body.append(wrap);
  body.scrollTop = keep;
  agentPropFoot(t, p);
}

function agentFillList(wrap, t, p) { // 표 채우기 제안 목록 — 「에이전트로 표 채우기」 열(table_fill.js)과 같은 꼴: 칸 · 머리 글 · 지금 → 제안 · 근거 · 경고, 고른 것만 반영
  const A = AGENT, v = p.view || {}, fills = v.fills || [], picked = agentFillPicks(p), lock = (p.state || "open") !== "open" && p.state !== "failed" || !!A.applying;
  const form = typeof TFL_FORM === "object" ? TFL_FORM : {}, where = typeof TFL_WHERE === "object" ? TFL_WHERE : {};
  if (!fills.length) { wrap.append(el("p", "hnote", "자료에서 찾은 값이 없습니다 — 자료를 더하고 다시 요청하세요.")); return; }
  const bar = el("div", "ta-row"), count = el("span", "muted"), boxes = [];
  const sync = () => { count.textContent = `${nf(agentFillCount(p))} / ${nf(fills.length)}`; agentDrawTalk(); agentPropFoot(t, p); }; // 카드와 발치의 「고른 n칸 …」
  const [tbl, tb] = hTable(["", "칸", "머리 글", "지금 → 제안", "근거"]);
  tbl.classList.add("tfl-list");
  for (const f of fills) {
    const warn = f.warn || [], tr = el("tr", warn.length ? "warn" : null), cb = el("input");
    cb.type = "checkbox"; cb.checked = picked.has(f.cell); cb.disabled = lock;
    cb.setAttribute("aria-label", `${f.ref} 제안 고르기`);
    cb.onchange = () => { if (cb.checked) picked.add(f.cell); else picked.delete(f.cell); sync(); };
    boxes.push([cb, f]);
    const c0 = el("td"), c1 = el("td"), c2 = el("td", "wrap", f.name || "—"), c3 = el("td", "wrap tfl-val"), c4 = el("td", "wrap tfl-why"), go = el("button", "hlink", f.ref);
    c0.append(cb);
    go.type = "button";
    go.title = `문서에서 그 칸으로 · ${form[f.form] || f.form || ""}`;
    go.onclick = () => { if (typeof tblFillGo === "function") tblFillGo(v.table, f.cell); else slGo(v.table); };
    c1.append(go, el("span", "hb", form[f.form] || f.form || ""));
    if ((f.now || "").trim()) c3.append(el("span", "tfl-now", f.now), el("span", "tfl-arrow", " → "));
    c3.append(el("b", "tfl-new", f.text));
    if (f.source) { const q = el("q", f.quoted ? null : "tfl-noquote", f.source); q.title = f.quoted ? `확인한 구절${f.where ? ` — ${where[f.where] || f.where}` : ""}` : "이 구절을 자료에서 찾지 못했습니다 — 값이 맞는지 직접 확인하세요"; c4.append(q); }
    if (f.reason) c4.append(el("span", "tfl-reason", f.reason));
    for (const w of warn) c4.append(el("span", "hb und", w));
    tr.append(c0, c1, c2, c3, c4);
    tr.addEventListener("mouseenter", () => { if (typeof tblFillHit === "function") tblFillHit(f.cell); });
    tr.addEventListener("mouseleave", () => { if (typeof tblFillHit === "function") tblFillHit(null); });
    tb.append(tr);
  }
  const pick = (fn) => { for (const [cb, f] of boxes) { cb.checked = fn(f); if (cb.checked) picked.add(f.cell); else picked.delete(f.cell); } sync(); };
  const all = [hBtn("경고 없는 것만", () => pick((f) => !(f.warn || []).length), { disabled: lock, title: "근거 구절이 자료에 있고 꼴이 맞는 제안만 고릅니다" }), hBtn("모두", () => pick(() => true), { disabled: lock }), hBtn("모두 풀기", () => pick(() => false), { disabled: lock })];
  bar.append(...all, count);
  count.textContent = `${nf(agentFillCount(p))} / ${nf(fills.length)}`;
  wrap.append(el("h3", null, "제안 — 고른 것만 문서에 들어갑니다"), bar, tbl);
  const rej = v.rejected || [];
  if (rej.length) {
    const d = el("details", "more hblock"), ul = el("ul", "tfl-rej");
    for (const x of rej) ul.append(el("li", null, `${x.ref || "?"} — ${x.why || ""}${x.text ? ` · 「${short(x.text, 50)}」` : ""}`));
    d.append(el("summary", null, `검사에서 뺀 제안 ${nf(rej.length)}`), ul);
    wrap.append(d);
  }
}

// ---- 2열 — 그 턴에 보낸 글(kind "agentGuide") — LLM 이 도는 곳의 「지침」(design.md §11): 보기만 ------------------------------------------
async function agentGuideOpen(tid) {
  const t = agentTurnOf(tid);
  if (!t || !state.id) return;
  const { tools, body } = headsDlg("agentGuide", "에이전트 지침", "이 요청에 함께 보낸 글과 LLM 의 답 · 보기만(문서는 안 바뀜)");
  const seq = heads.seq, epoch = state.epoch, alive = () => seq === heads.seq && epoch === state.epoch && heads.dlg === "agentGuide";
  tools.append(el("span", "muted", `요청 ${agentWhen(t.at)} — 「${short(t.text || "", 28)}」`));
  body.append(el("p", "hnote lg-msg", "읽는 중…"));
  let g;
  try { g = await api(agentUrl(`/turns/${encodeURIComponent(tid)}`)); }
  catch (e) { if (alive()) body.replaceChildren(el("p", "hwarn fail lg-msg", `지침을 읽지 못했습니다: ${agentErr(e)}`)); return; }
  if (!alive()) return;
  const parts = g.parts || [], calls = Array.isArray(g.calls) ? g.calls : [], open = new Set(["guide", "job", "request"]); // 사람이 관리하는 글(지침 · 할 일 프롬프트)과 요청은 펴 둔다 — 계약(contract) · 자료(data) · 표 채우기 호출(fill:<표>)은 접음
  body.textContent = "";
  body.append(el("div", "lk-cap", `함께 보낸 글 ${nf(parts.length)}개 — 이 차례로 프롬프트에 들어갔습니다`));
  if (!parts.length) body.append(el("p", "hnote lg-msg", "저장된 프롬프트가 없습니다"));
  for (const part of parts) {
    const d = el("details", "lg-part"), s = el("summary");
    d.dataset.part = part.key || "";
    d.open = open.has(part.key);
    s.append(el("strong", null, part.title || part.key || ""), el("span", "lg-src", `${nf((part.text || "").length)}자`));
    d.append(s, el("pre", "lg-text", part.text || "(빈 글)"));
    body.append(d);
  }
  body.append(el("div", "lk-cap", "LLM 의 답"), el("pre", "lg-text", g.response == null ? "(답 없음)" : typeof g.response === "string" ? g.response : JSON.stringify(g.response, null, 2)));
  if (calls.length) {
    body.append(el("div", "lk-cap", `호출 ${nf(calls.length)}번`));
    for (const c of calls) body.append(el("p", "lg-note", [c.what || c.step || "", c.backend || "", c.model || "", c.ms != null ? `${(c.ms / 1000).toFixed(1)}초` : "", c.costUsd != null ? `$${Number(c.costUsd).toFixed(3)}` : "", c.error ? `오류 — ${c.error}` : ""].filter(Boolean).join(" · ")));
  }
}

// ---- 묶기 — 문서의 선택이 바뀌면 고른 자리 줄을 다시(패널이 에이전트일 때만 · 한 프레임에 한 번) ---------------------------------------------
function agentBind() {
  const later = () => {
    const pane = $("paneAgent");
    if (agentSelRaf || !AGENT.el || !pane || pane.hidden) return;
    agentSelRaf = requestAnimationFrame(() => { agentSelRaf = 0; agentSelDraw(); });
  };
  const soon = () => setTimeout(later, 0); // 표 고르기·문단 묶음 고르기(table_menu.js · table_make.js)가 같은 누름을 처리한 뒤에
  document.addEventListener("selectionchange", later);
  const doc = $("doc");
  if (doc) for (const ev of ["mousedown", "mouseup", "keyup"]) doc.addEventListener(ev, soon);
  document.addEventListener("keyup", (e) => { if (e.key === "Escape") soon(); });
}
agentBind();
// 이 파일이 읽히기 전에 문서가 먼저 열렸으면(주소의 작업 — 읽기가 빨리 끝난 경우) 탭 보임과 「일반 문서」 의 첫 보기를 지금 맞춘다
if (state.id && !PEEK && typeof toolTabsDraw === "function") { toolTabsDraw(); if (taskGeneral() && $("panel").dataset.tool === "Verify") showTab("Agent"); }
