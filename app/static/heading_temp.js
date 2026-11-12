"use strict";
// TEMP 라벨(spec_헤딩_추출 ② §15) — 표 안의 임시 글(작성요령 · 쓸 자리)에 붙는 「TEMP」: 헤딩·템플릿(2단계)과 표 구조(3단계)에서 빠지고, 나중에 문서에서 지울 수 있다.
// 판정은 서버 스크립트(app/heading_temp.py — LLM 없음), 여기는 보이기·지정/해제·지우기:
//   · 「추출·설정」 1단계 카드 아래 TEMP 줄(tempCardRow) · 결과 요약의 TEMP 수(tempMetric) · TEMP 목록(2열 kind "temp" — tempView)
//   · 문서 표시 — TEMP 표는 표 표지에 「TEMP」(tempTableTag — tables.js tblMark), 칸·문단 단위는 쪽 왼쪽 여백 「TEMP」 표(tempMarkOf — app.js tplMarksDraw 가 「TN Lk」 와 한 줄로 맞춤)
//   · 오른쪽 단추 메뉴(tempCtxItems — 문단 메뉴 app.js divContextMenu · 표 칸 메뉴 table_edit.js tselContextMenu): TEMP 로 지정(문단·칸·표) · TEMP 해제
// 지정·해제는 서버가 저장하고 2단계 결과를 곧바로 다시 셈한다(LLM 호출 없음 — 구분 라벨 지정과 같은 길). 지우기는 한 번의 구조 편집(실행 취소 가능).
// app.js 가 주는 것: state·heads·$·el·api·toast·hBtn·hTable·hCell·hFoot·headsDlg·headsParaLink·headsGo·headsPoll·headsShow·headsStart·flushAll·applyEditState·reloadDoc·
// refreshToolbar·refreshSaveState·tplMarksDraw·nf·short·oneLine·hasBlock·H_JSON·LOG_KIND. app.js·tables.js·table_edit.js 가 부르는 것은 모두 typeof 검사 뒤.
// 서버 짝은 app/heading_temp_api.py. index.html 이 app.js·tables.js 다음에 읽는다.
const TEMP = { key: null, data: null, loading: null, error: "", busy: false, items: new Map(), marks: new Map() };
const TEMP_WHY = { guide: "작성요령", todo: "쓸 자리" };
const TEMP_WHY_TIP = { guide: "양식이 글쓴이에게 주는 안내 — 작성 요령 표 · 안내 상자 · 「… 작성합니다」 지시문", todo: "아직 안 쓴 자리 — 표 칸 안의 빈 글머리 줄(글을 써 넣으면 TEMP 가 풀립니다)" };
const TEMP_RULE = { guide_table: "작성 요령 표", guide_box: "안내 상자", guide_cell: "안내 칸", guide_line: "지시문", blank: "빈 글머리 줄", user: "사용자 지정" };
const TEMP_UNIT = { table: "표", cell: "칸", para: "문단" };
const tempUrl = (tail = "") => `/api/docs/${encodeURIComponent(state.id)}/headings/temp${tail}`;
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tempDelete: "TEMP 삭제", heading_temp: "TEMP 지정" }); // 「기록」 탭의 이름

function tempReset() { // 문서를 열거나 닫을 때(app.js headsReset)
  Object.assign(TEMP, { key: null, data: null, loading: null, error: "", busy: false, items: new Map(), marks: new Map() });
}

function tempSet(d) { // 읽은 자료를 두고 찾기 표를 만든다 — 항목 id → 항목 · 문단 id → 여백 표시(칸·문단 단위 항목의 「자리로」 문단)
  TEMP.data = d;
  TEMP.key = d ? d.key : null;
  TEMP.items = new Map(((d && d.items) || []).map((it) => [it.id, it]));
  TEMP.marks = new Map();
  for (const it of (d && d.items) || []) {
    if (it.unit === "table" || !it.para) continue;
    TEMP.marks.set(it.para, { text: "TEMP", temp: true, no: null, und: false, lbl: false,
      title: `TEMP · ${TEMP_WHY[it.why] || it.why}(${TEMP_RULE[it.rule] || it.rule}) — ${TEMP_UNIT[it.unit]}${it.paras > 1 ? ` · 문단 ${nf(it.paras)}` : ""}\n헤딩·템플릿을 주지 않습니다 · 누르면 TEMP 목록` });
  }
}

function tempSync(r) { // 헤딩 상태를 그릴 때마다(app.js headsRender) — TEMP 가 바뀌었으면((1단계 실행, 지정 판)이 다름) 다시 읽는다
  const key = r && r.temp ? r.temp.key : null;
  if (!key) { if (TEMP.data) { tempSet(null); tempRedraw(); } return; }
  if (key === TEMP.key || key === TEMP.loading) return;
  tempLoad(key);
}

async function tempLoad(key = null) {
  if (!state.id) return;
  const epoch = state.epoch;
  TEMP.loading = key || "now";
  try {
    const d = await api(tempUrl());
    if (epoch !== state.epoch) return;
    TEMP.error = "";
    tempSet(d);
  } catch (e) {
    if (epoch !== state.epoch) return;
    TEMP.error = e.message || "읽지 못함";
  } finally {
    if (epoch === state.epoch) { TEMP.loading = null; tempRedraw(); }
  }
}

function tempRedraw() { // 문서 표시(여백 「TEMP」 · 표 표지) · 열려 있는 TEMP 목록 · 카드 줄
  if (typeof tplMarksDraw === "function") tplMarksDraw();
  if (typeof tblMarksDraw === "function") tblMarksDraw();
  if (heads.dlg === "temp") { heads.keepFold = true; try { tempView(); } finally { heads.keepFold = false; } }
  for (const box of document.querySelectorAll(".htemp")) box.replaceWith(tempCardRow(heads.view || {}));
}

// ---- 문서 표시 ---------------------------------------------------------------------------------------------------
const tempMarkCount = () => TEMP.marks.size;
const tempMarkOf = (pid) => TEMP.marks.get(pid) || null; // app.js tplMarksDraw — 「TN Lk」 표가 없는 문단의 여백 표시
function tempTableItem(tid) { // 그 표가 TEMP 표(표 단위 항목 · 그 안쪽 표)면 항목
  const iid = TEMP.data && TEMP.data.tables ? TEMP.data.tables[tid] : null;
  return iid ? TEMP.items.get(iid) || null : null;
}
function tempTableTag(tid) { // tables.js tblMark — TEMP 표의 표지 꼬리표(소속·Σ 대신)
  const it = tempTableItem(tid);
  if (!it) return null;
  const b = el("button", "tm-temp", "TEMP");
  b.type = "button";
  const inner = it.unit !== "table" ? ` — TEMP 칸 ${it.cell} 안의 표` : it.table !== tid ? ` — TEMP 표 ${it.table} 안의 표` : "";
  b.title = `TEMP · ${TEMP_WHY[it.why] || it.why}(${TEMP_RULE[it.rule] || it.rule})${inner}\n헤딩·템플릿과 표 구조에서 뺍니다 · 누르면 TEMP 목록`;
  b.onclick = (e) => { e.stopPropagation(); tempView(it.id); };
  return b;
}

// ---- 카드 줄 · 요약 수 -----------------------------------------------------------------------------------------------
function tempCountText(c) {
  const rule = c.byRule || {};
  return ["guide_table", "guide_box", "guide_cell", "guide_line", "blank", "user"].filter((k) => rule[k]).map((k) => `${TEMP_RULE[k]} ${nf(rule[k])}`).join(" · ");
}

function tempMetric(r) { // 결과 요약의 수 단추(app.js headsResultsSummary) — 1단계 결과가 없으면 null
  const t = r && r.temp;
  if (!t) return null;
  const b = hBtn("", () => tempView(), { cls: "result-metric" });
  b.title = "TEMP — 표 안 작성요령·쓸 자리(헤딩·템플릿과 표 구조에서 뺌 · 나중에 지울 수 있음)";
  b.append(el("span", null, "TEMP"), el("strong", null, nf(t.counts.items || 0)));
  return b;
}

function tempCardRow(r) { // 「추출·설정」 1단계 카드 아래(app.js headsCard1)
  const box = el("div", "htemp");
  const t = r && r.temp;
  if (!t) return box;
  const c = t.counts || {};
  const line = el("div", "hnote temp-summary");
  const detail = "TEMP = 다 쓴 문서에 남지 않을 글(표 안 작성요령 · 빈 글머리 줄). 2단계는 헤딩 후보에서, 3단계는 TEMP 표를 표 구조에서 뺍니다.\n\n" + (c.items
    ? `${tempCountText(c)} · 문단 ${nf(c.paras)}(헤딩 후보 ${nf(c.candidates)})를 본문·표 검토에서 뺌`
    : "표 안 작성요령·쓸 자리를 찾지 못했습니다.");
  line.append(el("span", "hb temp", "TEMP"), el("span", null, `${nf(c.items || 0)}항목${c.off ? ` · 해제 ${nf(c.off)}` : ""}`), hHelp("TEMP 분류 안내", detail));
  box.append(line);
  const acts = el("div", "hacts");
  acts.append(hBtn("TEMP 목록", () => tempView(), { title: "항목마다 자리로 · 해제 · 삭제 — 문서 옆 열" }));
  const busy = !!(r.job && r.job.status === "running") || TEMP.busy;
  const s2 = r.stage2, s3 = r.stage3;
  if (s2 && s2.tempStale && !s2.stale) {
    headsCardNotice(box, "TEMP 반영 필요", "2단계 결과가 지금 TEMP와 다릅니다. TEMP 지정이 바뀌었거나 이전 결과에 TEMP 정보가 없어, TEMP 문단에 헤딩·템플릿이 남아 있습니다. 아래 버튼으로 반영하세요.", true);
    acts.append(hBtn("TEMP 를 2단계에 반영", () => tempApply(), { disabled: busy, cls: "btn sm primary", title: "지금 2단계 결과를 TEMP 를 빼고 다시 셈합니다 — LLM 호출 없음(LLM 실행이었으면 그 판정을 이어 씀)" }));
  }
  if (s3 && s3.tempStale && !s3.stale) {
    const llm = !!(s3.llm && s3.llm.calls);
    acts.append(hBtn("표 구조 다시(TEMP 표 빼기)", () => { if (!llm || confirm("지금 표 구조는 LLM 실행 결과입니다. 스크립트로 다시 만들면 LLM 이 고친 칸 역할이 사라집니다. 계속할까요?")) headsStart(3, false); },
      { disabled: busy, title: "3단계 결과의 TEMP 표가 지금과 다릅니다 — 스크립트로 다시 만들면 맞춰집니다(1초 안팎)" }));
  }
  box.append(acts);
  return box;
}

// ---- TEMP 목록(2열 kind "temp") ------------------------------------------------------------------------------------------
function tempUnitText(it) {
  if (it.unit === "table") return it.box ? "상자" : `표 ${it.rows ?? "?"}×${it.cols ?? "?"}`;
  return TEMP_UNIT[it.unit] || it.unit;
}

function tempView(focus = null) { // focus = 눈에 띄게 할 항목 id(문서의 표지를 눌렀을 때)
  if (!state.id) return;
  const d = TEMP.data;
  const { tools, body } = headsDlg("temp", "TEMP 목록", "표 안 작성요령 · 쓸 자리");
  if (!d) {
    body.append(el("p", "hnote pad", TEMP.error ? `TEMP 를 읽지 못했습니다: ${TEMP.error}` : TEMP.loading ? "TEMP 를 읽는 중…" : "1단계(문단 추출) 결과가 아직 없습니다 — 헤딩 추출 탭을 열면 자동으로 뽑습니다."));
    if (!TEMP.loading) tools.append(hBtn("다시 읽기", () => tempLoad()));
    return;
  }
  const c = d.counts || {}, off = TEMP.busy || state.busy;
  const stale = d["stale"] || d.rev !== state.serverRev; // 읽은 뒤 문서를 고쳤으면(실행 취소 포함) 다시 추출하기 전까지 옛 문서 기준 — 삭제는 다시 추출한 뒤
  tools.append(el("span", "muted", d.items.length
    ? `${nf(c.items)}항목 · 문단 ${nf(c.paras)} · 헤딩 후보 ${nf(c.candidates)} — 헤딩·템플릿과 표 구조에서 뺍니다`
    : "TEMP 항목이 없습니다 — 문서의 문단·표 칸에서 오른쪽 단추로 지정할 수 있습니다"));
  const wrap = el("div", "temp-wrap");
  if (stale) wrap.append(el("p", "hwarn", "문서가 추출 뒤 바뀌었습니다 — 아래는 고치기 전 문서 기준입니다. 헤딩 추출 탭에서 1단계를 다시 추출하면 맞춰지고, 그 뒤에 지울 수 있습니다."));
  const s2 = d.stage2, s3 = d.stage3;
  if (s2 && s2.tempStale && !stale) {
    const p = el("p", "hwarn", "2단계 결과가 지금 TEMP 와 다릅니다 — TEMP 문단에 헤딩·템플릿이 남아 있습니다. ");
    p.append(hBtn("TEMP 를 2단계에 반영", () => tempApply(), { disabled: off, title: "LLM 호출 없이 다시 셈합니다" }));
    wrap.append(p);
  }
  if (s3 && s3.tempStale && !stale) wrap.append(el("p", "hnote", "3단계(표 구조) 결과의 TEMP 표가 지금과 다릅니다 — 표 구조를 다시 만들면 맞춰집니다(문서의 표 표지는 지금 TEMP 를 따릅니다)."));
  for (const why of ["guide", "todo"]) {
    const items = d.items.filter((it) => it.why === why);
    if (!items.length) continue;
    const head = el("div", "temp-head");
    const sum = (k) => items.reduce((a, it) => a + (it[k] || 0), 0);
    const name = el("b", null, TEMP_WHY[why]);
    name.title = TEMP_WHY_TIP[why];
    head.append(name, el("span", "muted", `${nf(items.length)}항목 · 문단 ${nf(sum("paras"))} · 헤딩 후보 ${nf(sum("candidates"))}`));
    const can = items.filter((it) => it.block).length;
    head.append(hBtn("모두 삭제…", () => tempDelete({ why }, `${TEMP_WHY[why]} ${nf(can)}항목(문단 ${nf(sum("paras"))})`), { disabled: off || stale || !can,
      title: stale ? "문서가 추출 뒤 바뀜 — 1단계를 다시 추출한 뒤" : `이 묶음을 문서에서 지웁니다 — 한 번의 편집(실행 취소 가능)${can < items.length ? ` · 지울 수 없는 ${items.length - can}항목은 건너뜀` : ""}` }));
    wrap.append(head);
    const [tbl, tb] = hTable(["글", "단위", "규칙", "문단", ""]);
    tbl.classList.add("temp-list");
    for (const it of items) {
      const tr = el("tr", it.id === focus ? "focus" : null);
      tr.dataset.item = it.id;
      const td = el("td", "txt");
      td.append(headsParaLink(it.para, it.text || "(글 없음)", 44, it.id));
      if (it.unit !== "para") td.append(" ", el("span", "muted", it.unit === "table" ? it.table : it.cell)); // 같은 글(「작성 요령」)의 표를 가르게 표·칸 id
      if (it.by === "user") td.append(" ", el("span", "hb divl-by", "지정"));
      tr.append(td);
      hCell(tr, tempUnitText(it), null, it.table ? `표 ${it.table}${it.cell ? ` · 칸 ${it.cell}` : ""}` : "본문");
      hCell(tr, TEMP_RULE[it.rule] || it.rule);
      hCell(tr, it.candidates ? `${nf(it.paras)} (${nf(it.candidates)})` : nf(it.paras), null, `문단 ${nf(it.paras)} · 그 가운데 헤딩 후보(레터·괄호 줄) ${nf(it.candidates)}`);
      const act = el("td", "acts");
      act.append(it.by === "user"
        ? hBtn("지정 지움", () => tempPut(it.id, "auto", it), { disabled: off, title: "TEMP 지정을 지웁니다 — 규칙대로 다시 판정" })
        : hBtn("해제", () => tempPut(it.id, "off", it), { disabled: off, title: "TEMP 가 아니라고 지정 — 헤딩·템플릿 대상으로 돌아옵니다(문서는 그대로)" }),
      hBtn("삭제", () => tempDelete({ ids: [it.id] }, `「${short(it.text, 30)}」 ${tempUnitText(it)}${it.paras > 1 ? `(문단 ${nf(it.paras)})` : ""}`), { disabled: off || stale || !it.block,
        title: !it.block ? "웹 블록이 없는 자리(머리말·글상자 안)라 여기서 지울 수 없습니다" : stale ? "문서가 추출 뒤 바뀜 — 1단계를 다시 추출한 뒤" : "문서에서 지웁니다(실행 취소 가능)" }));
      tr.append(act);
      tb.append(tr);
    }
    wrap.append(tbl);
  }
  const offs = d.off || [];
  if (offs.length) {
    const head = el("div", "temp-head");
    head.append(el("b", null, "해제한 항목"), el("span", "muted", `${nf(offs.length)}개 — TEMP 가 아니라고 지정한 것`));
    wrap.append(head);
    for (const o of offs) {
      const row = el("div", "temp-row");
      row.append(el("span", "muted", o.id), el("span", null, short(o.text, 40)), hBtn("다시 TEMP 로", () => tempPut(o.id, "auto", o), { disabled: off, title: "해제를 지웁니다 — 규칙대로 다시 TEMP" }));
      wrap.append(row);
    }
  }
  if ((d.gone || []).length) wrap.append(el("p", "hnote", `문서에 없는 지정 ${nf(d.gone.length)}개(그 표·문단이 지워짐): ${d.gone.slice(0, 8).join(" · ")}`));
  body.append(wrap);
  hFoot(`1단계 실행 ${d.run ?? "–"} · 지정 v${d.version}${d.stage2 ? ` · 2단계 실행 ${d.stage2.run ?? "–"}` : ""}`, false);
  if (focus) { const tr = wrap.querySelector(`tr[data-item="${CSS.escape(focus)}"]`); if (tr) tr.scrollIntoView({ block: "center" }); }
}

// ---- 지정 · 해제 · 반영 · 삭제 --------------------------------------------------------------------------------------------
function tempApplied(d, msg) { // PUT·apply 응답 — 2단계를 다시 셈했으면 상태를 다시 읽는다(카드·그래프·문서 표시가 새 실행으로)
  tempSet(d);
  toast(d.applied ? `${msg} · 헤딩·템플릿을 다시 셈했습니다` : `${msg} — ${d.note}`);
  if (d.applied) headsPoll(); else if (typeof headsShow === "function") headsShow();
}

async function tempPut(id, to, it = null, why = "guide") {
  if (TEMP.busy || !state.id) return;
  TEMP.busy = true;
  tempRedraw();
  const epoch = state.epoch;
  try {
    const d = await api(tempUrl(), { method: "PUT", headers: H_JSON, body: JSON.stringify({ id, state: to, why }) });
    if (epoch !== state.epoch) return;
    const name = it && it.text ? `「${short(it.text, 24)}」` : id;
    tempApplied(d, to === "on" ? `${name} → TEMP` : to === "off" ? `${name} → TEMP 해제` : `${name} — 지정을 지움`);
  } catch (e) {
    if (epoch === state.epoch) toast(`TEMP 지정을 바꾸지 못했습니다: ${e.message}`, true);
  } finally {
    TEMP.busy = false;
    if (epoch === state.epoch) tempRedraw();
  }
}

async function tempApply() { // 지금 TEMP 로 2단계 결과를 다시 셈(LLM 호출 없음)
  if (TEMP.busy || !state.id) return;
  TEMP.busy = true;
  tempRedraw();
  const epoch = state.epoch;
  try {
    const d = await api(tempUrl("/apply"), { method: "POST" });
    if (epoch !== state.epoch) return;
    tempApplied(d, "TEMP 를 2단계에 반영");
  } catch (e) {
    if (epoch === state.epoch) toast(`반영하지 못했습니다: ${e.message}`, true);
  } finally {
    TEMP.busy = false;
    if (epoch === state.epoch) tempRedraw();
  }
}

async function tempDelete(body, what) {
  if (TEMP.busy || state.busy || !state.id) return;
  if (!confirm(`TEMP ${what}을(를) 문서에서 지울까요?\n\n한 번에 지우고 표준 검사에 걸리면 전부 되돌립니다. 지운 뒤 「실행 취소」 로 되돌릴 수 있습니다.`)) return;
  const epoch = state.epoch;
  await flushAll(); // 아직 반영 안 된 글부터 — 서버 문서를 지운다
  if (epoch !== state.epoch) return;
  TEMP.busy = true;
  state.busy = true;
  refreshToolbar();
  tempRedraw();
  try {
    const r = await api(tempUrl("/delete"), { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    state.structRev = state.localRev; // 표 판정 캐시(tables.js)도 새로
    applyEditState(r);
    const skipped = (r.skipped || []).length;
    toast(`TEMP ${nf(r.deleted.length)}항목을 지웠습니다${skipped ? ` · 건너뜀 ${nf(skipped)}(${r.skipped[0].why})` : ""} — 「실행 취소」 로 되돌릴 수 있습니다`);
    await reloadDoc(); // 떨어진 자리 여러 곳이 바뀌어 문서를 다시 읽는다
    if (epoch !== state.epoch) return;
    headsShow(); // 문서가 바뀜 — 1단계가 다시 돌고 TEMP 목록도 새로
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (e.status === 409) { toast(e.message, true); headsShow(); }
    else if (e.status === 422) toast(`표준 검사에 걸려 되돌렸습니다: ${e.message}`, true);
    else toast(`지우지 못했습니다: ${e.message}`, true);
  } finally {
    TEMP.busy = false;
    if (epoch === state.epoch) {
      state.busy = false;
      refreshToolbar();
      refreshSaveState();
      tempRedraw();
    }
  }
}

// ---- 오른쪽 단추 메뉴(문단 · 표 칸) ----------------------------------------------------------------------------------------
function tempCtxItems(e) { // [구분선, [이름, 단축키, 실행, 못 씀]…] — 헤딩 추출을 아직 안 읽었으면(TEMP 자료 없음) 빈 목록
  const d = TEMP.data;
  if (!state.id || state.format === "docx" || !d || !d.run) return [];
  const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
  const p = t && t.closest(".para[data-id]"), td = t && t.closest("#doc td[data-cell]"), tbl = td && td.closest("table.tbl[data-tbl]");
  const pid = p && hasBlock(p.dataset.id) ? p.dataset.id : null, cid = td ? td.dataset.cell : null, tid = tbl ? tbl.dataset.tbl : null;
  if (!pid && !cid) return [];
  const busy = TEMP.busy;
  const iid = (pid && d.paras && d.paras[pid]) || (tid && d.tables && d.tables[tid]) || (cid && TEMP.items.has(`cell:${cid}`) ? `cell:${cid}` : null);
  const it = iid ? TEMP.items.get(iid) : null;
  if (it) {
    const what = `${tempUnitText(it)} 「${short(it.text, 16)}」`;
    return [null,
      [it.by === "user" ? `TEMP 지정 지움 — ${what}` : `TEMP 해제 — ${what}`, "", () => tempPut(it.id, it.by === "user" ? "auto" : "off", it), busy],
      ["TEMP 목록에서 보기", "", () => tempView(it.id)]];
  }
  const items = [null];
  if (pid) items.push(["TEMP 로 지정 — 이 문단", "", () => tempPut(`para:${pid}`, "on", { text: state.texts[pid] || "" }), busy]);
  if (cid) items.push(["TEMP 로 지정 — 이 칸", "", () => tempPut(`cell:${cid}`, "on", { text: `칸 ${cid}` }), busy]);
  if (tid) items.push(["TEMP 로 지정 — 이 표", "", () => tempPut(`tbl:${tid}`, "on", { text: `표 ${tid}` }), busy]);
  return items;
}
