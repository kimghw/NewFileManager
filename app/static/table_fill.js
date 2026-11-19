"use strict";
// 표 채우기(spec_헤딩_추출 ② §18) — 표 모듈의 한 조각. 사용자 2026-11-12 "에이전트로 표 테이블 채우기 기능도 있으면 좋겠다".
// 표 메뉴(table_menu.js) 「에이전트로 표 채우기…」 · 「작성요령 · 표 지침」 열의 단추가 연다 → 2열 kind "tblFill"(문서 옆 열 — 팝업 아님):
//   채울 칸 요약(빈 칸 · 체크 · 날짜 · 수 · 비율 — 서버가 찾는다) · 자료 글상자(붙여 넣기) · 「이 문서의 글도 자료로」·「채워진 칸도 다시 제안」 → 「채우기 제안 받기(LLM)」
//   → 제안 목록(칸 · 머리 글 · 지금 → 제안 · 근거 구절 · 경고) → 고른 것만 「문서에 반영」(한 트랜잭션 — 실행 취소 1개).
// LLM 이 하는 일은 제안까지다. 근거 구절을 자료에서 못 찾은 제안·꼴이 안 맞는 제안은 경고가 붙고 처음엔 고르지 않은 채다.
// app.js 가 주는 것: state·heads·$·el·api·toast·structOp·flushAll·headsDlg·hBtn·hFoot·hTable·nf·short·oneLine·H_JSON. tables.js: xlBlock·xlRangeName·tblAgentView. table_menu.js: tmnActivate.
// 전역 이름은 tblFill…·TFL_… 만 쓴다 — app.js 의 fillPlan·fillApply·FILL_MODE(이관 「넣기 계획」)와 옆 열 kind "fill" 은 다른 기능이다.
// 서버 짝: app/tables_api.py `POST …/tables/{tid}/fill`(dry | 제안)·`…/fill/apply`, 판정·계약 app/table_fill.py. index.html 이 table_menu.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TFL_FORM = { check: "체크", date: "날짜", num: "수", pct: "비율", ph: "글 자리표시", blank: "빈 칸", text: "글" };
const TFL_WHERE = { material: "자료", document: "이 문서", table: "이 표", context: "표 앞뒤", rule: "지침·칸 입력 규칙(고정 글)" };
const tblFill = { doc: null, drafts: {}, cur: null }; // drafts[표 id] = {material, useDoc, overwrite, result, picked} — 문서를 다시 열기 전까지 기억(열을 닫았다 열어도 자료·제안이 남는다)
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tableFillLlm: "표 채우기 제안(LLM)", tableFill: "표 채우기" }); // 「기록」 탭의 이름

const tblFillUrl = (tid, tail = "") => `/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/fill${tail}`;
const tblFillSecs = (ms) => (ms == null ? "" : `${(ms / 1000).toFixed(1)}초`);

function tblFillCellEl(cid) { // 문서의 그 칸(쪽에 걸쳐 나뉜 칸은 첫 조각)
  return document.querySelector(`#doc td[data-cell="${CSS.escape(cid)}"]`);
}
function tblFillHit(cid) { // 제안 줄에 올린 동안 문서의 그 칸을 보인다(null = 걷기)
  for (const e of document.querySelectorAll("#doc td.tfl-hit")) e.classList.remove("tfl-hit");
  if (!cid) return;
  for (const e of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(cid)}"]`)) e.classList.add("tfl-hit");
}
function tblFillGo(tid, cid = null) { // 문서에서 그 칸(없으면 표)으로 — 열은 그대로 둔다(나란히 보기)
  const target = (cid && tblFillCellEl(cid)) || document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`);
  if (!target) { toast("그 표가 지금 화면에 없습니다"); return; }
  target.scrollIntoView({ block: cid ? "center" : "start", behavior: scrollHow() });
  if (typeof tmnActivate === "function") tmnActivate(tid);
}

async function tblFillView(tid, range = null) {
  if (!state.id) return;
  if (state.format === "docx") { toast("표 채우기는 지금 hwpx 문서만 됩니다"); return; }
  if (!xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const key = `${state.id}|${state.epoch}`;
  if (tblFill.doc !== key) { tblFill.doc = key; tblFill.drafts = {}; }
  const rkey = range ? `${range.r0},${range.c0},${range.r1},${range.c1}` : "";
  // useDoc null = 아직 안 정함 — 첫 미리보기에서 정한다: 할 일 프롬프트가 붙은 작업(이관)은 기준 문서가 따로 있으므로 「이 문서의 글」 을 기본으로 끄고, 아니면 켠다(spec ② §18 「할 일 프롬프트가 붙을 때」)
  const draft = tblFill.drafts[tid] || (tblFill.drafts[tid] = { material: "", useDoc: null, overwrite: false, result: null, picked: null, rkey });
  if (draft.rkey !== rkey) { draft.rkey = rkey; draft.result = null; draft.picked = null; } // 범위가 바뀌면 앞 제안은 버린다
  const { tools, body } = headsDlg("tblFill", `표 채우기 · ${tid}${range ? ` ${xlRangeName(range)}` : ""}`,
    "작성요령 · 지침 · 칸 입력 규칙에 맞춰 빈 칸에 넣을 값을 LLM 이 제안합니다 — 고른 것만 문서에 들어갑니다");
  const seq = heads.seq, epoch = state.epoch;
  const live = () => seq === heads.seq && epoch === state.epoch;
  const cur = tblFill.cur = { tid, range, busy: false, timer: 0 };
  const wrap = el("div", "ta-wrap tfl-wrap");
  body.append(wrap);
  hFoot("채울 칸을 찾는 중…", false);

  // ---- 틀: 식별 줄 · 채울 칸 요약 · 기준 · 자료 · 옵션 · 실행 · 결과 ----
  const ident = el("div", "ta-ident"), acts = el("div", "ta-row"), sum = el("p", "hnote tfl-sum"), basis = el("p", "hnote");
  const mat = el("textarea"), matNote = el("span", "muted");
  const optDoc = el("input"), optOver = el("input"), optDocText = el("span"), runRow = el("div", "ta-row"), runState = el("span", "tfl-state muted"), result = el("div", "tfl-result");
  const RUN_TITLE = "작성요령 · 지침 · 칸 입력 규칙과 자료를 LLM 에 한 번 보내 칸마다 넣을 글을 받습니다(수 초~수십 초) — 문서는 「문서에 반영」 을 눌러야 바뀝니다";
  const runBtn = hBtn("채우기 제안 받기(LLM)", () => run(), { cls: "btn sm primary", title: RUN_TITLE });
  ident.append(el("b", null, tid));
  acts.append(hBtn("표 자리로", () => tblFillGo(tid), { title: "문서에서 이 표로" }),
    hBtn("작성요령 · 표 지침", () => { if (typeof tblAgentView === "function") tblAgentView(tid); }, { title: "문서의 작성요령 · 지침 · 칸 입력 규칙을 보고 고칩니다(저장한 것은 다음 제안부터 함께 갑니다)" }));
  mat.rows = 7;
  mat.value = draft.material;
  mat.placeholder = "채울 내용이 든 글을 붙여 넣으세요 — 과제 정보·공고문·협약서·메일·다른 문서에서 복사한 글(표를 복사해도 됩니다).\n비워 두면 이 문서의 글에서만 찾습니다.";
  mat.maxLength = 60000;
  mat.oninput = () => { draft.material = mat.value; matNote.textContent = mat.value ? `${nf(mat.value.length)}자` : ""; };
  matNote.textContent = mat.value ? `${nf(mat.value.length)}자` : "";
  for (const [box, on] of [[optDoc, draft.useDoc !== false], [optOver, draft.overwrite]]) { box.type = "checkbox"; box.checked = on; }
  const lab = (box, textEl, title) => { const l = el("label", "tfl-opt"); l.title = title; l.append(box, textEl); return l; };
  const opts = el("div", "ta-row");
  opts.append(lab(optDoc, optDocText, "이 문서의 본문과 다른 표의 글을 자료로 함께 보냅니다(이 표와 「작성 요령」 표는 뺌 — 앞에서부터 6만 자까지). 끄면 붙여 넣은 자료와 이 표의 글만 봅니다"),
    lab(optOver, el("span", null, "채워진 칸도 다시 제안"), "이미 글이 있는 필드도 대상에 넣습니다 — 그런 제안에는 「이미 채운 칸을 바꿈」 경고가 붙고 처음엔 고르지 않은 채입니다"));
  runRow.append(runBtn, runState);
  const matRow = el("div", "ta-row");
  matRow.append(matNote);
  wrap.append(ident, acts, sum, basis, el("h3", null, "자료 — 채울 내용이 든 글"), mat, matRow, opts, runRow, result);

  // ---- 채울 칸 미리보기(dry) ----
  let view = null;
  const req = (extra = {}) => ({ ...(range ? { range } : {}), overwrite: optOver.checked, useDoc: optDoc.checked, ...extra });
  const drawSummary = () => {
    const k = view.counts || {}, byForm = {};
    for (const t of view.targets || []) byForm[t.form] = (byForm[t.form] || 0) + 1;
    const forms = Object.keys(TFL_FORM).filter((f) => byForm[f]).map((f) => `${TFL_FORM[f]} ${nf(byForm[f])}`).join(" · ");
    ident.replaceChildren(el("b", null, tid), el("span", null, `${view.rows}×${view.cols}`), ...(view.unit ? [el("span", "hb", `단위 ${view.unit}`)] : []),
      ...(view.range ? [el("span", "hb", `범위 ${xlRangeName(view.range)}`)] : []));
    sum.textContent = view.note || (k.targets
      ? `채울 칸 ${nf(k.targets)}개 — ${forms} (채우는 필드 ${nf(k.fields)}개 · 빈 자리 ${nf(k.open)}개${view.range ? " · 고른 범위 안만" : ""})`
      : `채울 칸이 없습니다 — 채우는 필드 ${nf(k.fields)}개 가운데 빈 자리 ${nf(k.open)}개${view.range ? "(고른 범위에는 없음)" : ""}${optOver.checked ? "" : " · 채워진 칸도 보려면 「채워진 칸도 다시 제안」"}`);
    sum.title = "채우는 필드 = 칸 역할이 필드인 칸에서 수식으로 셈하는 칸(합계·비율)을 뺀 것\n빈 자리 = 글 없음 · 자리표시뿐(0,000 · ○○) · 표시 없는 체크 칸 · 숫자가 빠진 날짜\n머리 칸이 필드로 잡혔거나 그 반대면 칸을 골라 「헤더 지정」 으로 고칩니다"
      + ((view.skipped || []).length ? `\n뺀 칸 ${view.skipped.length}: ${view.skipped.slice(0, 8).map((x) => `${x.ref} ${x.why}`).join(" · ")}` : "");
    // 할 일 프롬프트가 붙은 작업 — 그 전제와 어긋날 수 있는 옵션을 켰으면 기준 줄에 알린다(막지는 않는다 — 사람이 정한다)
    const jobWarn = !view.job ? [] : [optDoc.checked ? "「이 문서의 글」 은 할 일의 기준 문서가 아닐 수 있습니다(값의 출처로는 안 쓰도록 LLM 에 알립니다)" : "", optOver.checked ? "「채워진 칸도 다시 제안」 은 할 일 전제(이미 쓴 글은 덮지 않음)와 어긋날 수 있습니다" : ""].filter(Boolean);
    basis.textContent = `기준 — 문서의 작성요령 ${nf(view.notes)}건${view.guides ? `(「작성 요령」 표 ${nf(view.guides)})` : ""} · 지침(양식·공통·이 표) · 칸 입력 규칙(기본·공통·이 표)`
      + (view.job ? ` · 할 일 「${view.job.name}」 의 전제` : "") + (jobWarn.length ? ` — ${jobWarn.join(" · ")}` : "");
    basis.classList.toggle("tfl-jobwarn", jobWarn.length > 0);
    basis.title = "제안은 이 기준을 모두 따릅니다 — 「작성요령 · 표 지침」 에서 보고 고칩니다" + (view.job ? "\n할 일의 전제(jobs/<할 일>.md)는 계약 바로 뒤에 함께 갑니다 — 기준 문서의 내용은 자료 글상자에 붙여 넣으세요" : "");
    const d = view.doc || {};
    optDocText.textContent = optDoc.checked && d.chars ? `이 문서의 글도 자료로 — ${nf(d.sent)}자${d.cut ? `(전체 ${nf(d.chars)}자 가운데 앞부분)` : ""}` : "이 문서의 글도 자료로";
    const off = !view.llm ? "LLM 을 쓸 수 없습니다" : view.blocked || "";
    runBtn.disabled = cur.busy || !k.targets || !!off;
    runBtn.title = !view.llm ? "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)" : view.blocked ? view.blocked : !k.targets ? "채울 칸이 없습니다" : RUN_TITLE;
    if (!cur.busy) { runState.textContent = off; runState.classList.toggle("hd-msg", !!view.blocked); }
    hFoot(`표 ${tid} · 채울 칸 ${nf(k.targets)} · 문서 차례 ${view.rev}`, false);
  };
  const loadDry = async () => {
    try {
      await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서의 칸 글로 판정한다
      let r = await api(tblFillUrl(tid), { method: "POST", headers: H_JSON, body: JSON.stringify(req({ dry: true })) });
      if (!live()) return false;
      if (draft.useDoc === null) { // 처음 연 표 — 할 일이 붙은 작업이면 「이 문서의 글」 을 끈 채로 시작
        draft.useDoc = !r.job;
        if (optDoc.checked !== draft.useDoc) {
          optDoc.checked = draft.useDoc;
          r = await api(tblFillUrl(tid), { method: "POST", headers: H_JSON, body: JSON.stringify(req({ dry: true })) });
          if (!live()) return false;
        }
      }
      view = r;
      drawSummary();
      return true;
    } catch (e) {
      if (!live()) return false;
      sum.textContent = e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「표 채우기」 를 쓸 수 있습니다" : `채울 칸을 찾지 못했습니다: ${e.message}`;
      runBtn.disabled = true;
      hFoot(sum.textContent);
      return false;
    }
  };
  optDoc.onchange = () => { draft.useDoc = optDoc.checked; loadDry(); }; // 사람이 고른 값은 그대로 둔다(할 일이 붙은 작업에서 켜면 기준 줄에 알림)
  optOver.onchange = () => { draft.overwrite = optOver.checked; loadDry(); };

  // ---- 제안 받기 ----
  const tick = (t0) => { runState.textContent = ""; runState.append(el("span", "tfl-spin"), `채우기 제안 — LLM 이 자료에서 값을 찾는 중 · ${Math.round((performance.now() - t0) / 1000)}초`); };
  async function run() {
    if (cur.busy || !view) return;
    cur.busy = true;
    runBtn.disabled = true;
    const t0 = performance.now();
    tick(t0);
    cur.timer = setInterval(() => { if (live()) tick(t0); else clearInterval(cur.timer); }, 1000);
    let r = null, err = null;
    try {
      await flushAll();
      r = await api(tblFillUrl(tid), { method: "POST", headers: H_JSON, body: JSON.stringify(req({ material: mat.value })) });
    } catch (e) { err = e; }
    clearInterval(cur.timer);
    cur.busy = false;
    if (epoch !== state.epoch) return; // 그 사이 다른 문서
    if (r) { draft.result = r; draft.picked = new Set(r.fills.filter((f) => !f.warn.length).map((f) => f.cell)); } // 경고 없는 제안만 처음부터 고른다
    if (!live()) { if (r) toast(`표 ${tid} 채우기 제안 ${nf(r.fills.length)}칸이 왔습니다 — 표 메뉴 「에이전트로 표 채우기」 에서 봅니다`); return; }
    runState.textContent = err ? `제안을 받지 못했습니다: ${err.message}` : "";
    runState.classList.toggle("hd-msg", !!err);
    if (r) { view = { ...view, ...r, counts: r.counts }; drawResult(); }
    runBtn.disabled = !view.llm || !!view.blocked || !(view.counts || {}).targets;
  }

  // ---- 제안 목록 ----
  function drawResult() {
    result.textContent = "";
    const r = draft.result;
    if (!r) return;
    const k = r.counts || {}, call = r.call || {}, picked = draft.picked || (draft.picked = new Set());
    const head = el("p", "hnote tfl-answer", `제안 ${nf(r.fills.length)}칸(경고 ${nf(k.warn || 0)})${k.rejected ? ` · 검사에서 뺌 ${nf(k.rejected)}` : ""} · 못 채운 칸 ${nf(k.left || 0)}`
      + ` · ${[tblFillSecs(call.ms), call.costUsd != null ? `$${Number(call.costUsd).toFixed(3)}` : "", call.model || ""].filter(Boolean).join(" · ")}`);
    head.title = "못 채운 칸 = 채울 칸 가운데 제안이 없는 칸 — 자료에서 값을 찾지 못해 LLM 이 답하지 않았거나 검사에서 빠진 칸(빈 채로 둡니다)\n경고 = 근거 구절을 자료에서 못 찾음 · 수 칸에 수가 아님 · 날짜 꼴이 다름 · 이미 채운 칸을 바꿈 — 처음엔 고르지 않은 채입니다";
    result.append(el("h3", null, "제안 — 고른 것만 문서에 들어갑니다"), head);
    if (r.answer) result.append(el("p", "hnote", `LLM: ${r.answer}`));
    if (!r.fills.length) { result.append(el("p", "hnote", "자료에서 찾은 값이 없습니다 — 자료 글상자에 채울 내용을 붙여 넣고 다시 받으세요.")); return; }
    const bar = el("div", "ta-row"), count = el("span", "muted");
    const applyBtn = hBtn("", () => apply(), { cls: "btn sm primary", title: "고른 제안을 문서의 칸에 씁니다 — 한 번의 편집(도구 줄 「실행 취소」 로 한꺼번에 되돌림). 제안을 받은 뒤 사람이 고친 칸은 건너뜁니다" });
    const sync = () => {
      const n = r.fills.filter((f) => picked.has(f.cell)).length;
      applyBtn.textContent = `고른 ${nf(n)}칸 문서에 반영`;
      applyBtn.disabled = !n || state.busy;
      count.textContent = `${nf(n)} / ${nf(r.fills.length)}`;
    };
    const [t, tb] = hTable(["", "칸", "머리 글", "지금 → 제안", "근거"]);
    t.classList.add("tfl-list");
    const boxes = [];
    for (const f of r.fills) {
      const tr = el("tr", f.warn.length ? "warn" : null);
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = picked.has(f.cell);
      cb.setAttribute("aria-label", `${f.ref} 제안 고르기`);
      cb.onchange = () => { if (cb.checked) picked.add(f.cell); else picked.delete(f.cell); sync(); };
      boxes.push([cb, f]);
      const c0 = el("td"), c1 = el("td"), c2 = el("td", "wrap", f.name || "—"), c3 = el("td", "wrap tfl-val"), c4 = el("td", "wrap tfl-why");
      c0.append(cb);
      const go = el("button", "hlink", f.ref);
      go.type = "button";
      go.title = `문서에서 그 칸으로 · ${TFL_FORM[f.form] || f.form}`;
      go.onclick = () => tblFillGo(tid, f.cell);
      c1.append(go, el("span", "hb", TFL_FORM[f.form] || f.form));
      if (f.now.trim()) c3.append(el("span", "tfl-now", f.now), el("span", "tfl-arrow", " → "));
      c3.append(el("b", "tfl-new", f.text));
      if (f.source) { const q = el("q", f.quoted ? null : "tfl-noquote", f.source); q.title = f.quoted ? `확인한 구절${f.where ? ` — ${TFL_WHERE[f.where] || f.where}` : ""}` : "이 구절을 자료(고정 글이면 지침·규칙)에서 찾지 못했습니다 — 값이 맞는지 직접 확인하세요"; c4.append(q); }
      if (f.reason) c4.append(el("span", "tfl-reason", f.reason));
      for (const w of f.warn) c4.append(el("span", "hb und", w));
      tr.append(c0, c1, c2, c3, c4);
      tr.addEventListener("mouseenter", () => tblFillHit(f.cell));
      tr.addEventListener("mouseleave", () => tblFillHit(null));
      tb.append(tr);
    }
    const pick = (fn) => { for (const [cb, f] of boxes) { cb.checked = fn(f); if (cb.checked) picked.add(f.cell); else picked.delete(f.cell); } sync(); };
    bar.append(applyBtn, hBtn("경고 없는 것만", () => pick((f) => !f.warn.length), { title: "근거 구절이 자료에 있고 꼴이 맞는 제안만 고릅니다" }), hBtn("모두", () => pick(() => true)), hBtn("모두 풀기", () => pick(() => false)), count);
    result.append(bar, t);
    if ((r.rejected || []).length) {
      const d = el("details", "more hblock"), ul = el("ul", "tfl-rej");
      for (const x of r.rejected) ul.append(el("li", null, `${x.ref || "?"} — ${x.why}${x.text ? ` · 「${short(x.text, 50)}」` : ""}`));
      d.append(el("summary", null, `검사에서 뺀 제안 ${nf(k.rejected || r.rejected.length)} — 채울 칸이 아닌 주소 · 체크 칸의 글을 바꾼 답`), ul);
      result.append(d);
    }
    sync();

    async function apply() {
      const todo = r.fills.filter((f) => picked.has(f.cell));
      if (!todo.length) return;
      tblFillHit(null);
      const out = await structOp(`tables/${encodeURIComponent(tid)}/fill/apply`, { fills: todo.map((f) => ({ cell: f.cell, text: f.text, was: f.now })) }); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
      if (!out || !out.filled) { if (live()) sync(); return; }
      const done = new Set(out.filled.cells || []), skip = out.filled.skipped || [];
      r.fills = r.fills.filter((f) => !done.has(f.cell)); // 넣은 제안은 목록에서 뺀다(건너뛴 것은 남는다 — 다시 받거나 그대로 둔다)
      for (const c of done) picked.delete(c);
      for (const x of skip) picked.delete(x.cell);
      toast(`표 ${tid} — ${nf(done.size)}칸을 채웠습니다${skip.length ? ` · 건너뜀 ${nf(skip.length)}(${skip[0].why})` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
      if (!live()) return;
      drawResult();
      loadDry(); // 남은 채울 칸 수를 다시
    }
  }

  if (!(await loadDry())) return;
  drawResult(); // 앞서 받은 제안이 있으면 다시 보인다(문서가 그 사이 바뀐 칸은 반영할 때 서버가 건너뛴다)
  tools.append(el("span", "muted", "제안은 문서를 바꾸지 않습니다 · 자료에 없는 값은 비워 둡니다 · 반영은 고른 칸만, 실행 취소 한 번으로 되돌립니다"));
}
