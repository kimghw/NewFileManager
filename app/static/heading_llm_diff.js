"use strict";
// LLM 이 바꾼 것(spec_헤딩_추출 ② §7 「LLM 이 바꾼 것」, 2026-11-16 사용자 "LLM 작업하고 뭐가 수정되었는지를 모르겠다" → 답 「문서 옆 열」).
// 헤딩 추출의 LLM 실행(규칙 보강 · 헤딩 판정 · 표 판정)과 받아 둔 서식 정리 계획(★)이 **스크립트가 낸 것과 다르게 정한 것**을 문서 옆 열(2열 kind "llmDiff")에 한 목록으로.
// 여는 곳: 진행 줄(app.js headsProgLine)의 LLM 층 ✓ 칸 — 그 단계 절로 내려간다(안 돈 칸은 전처럼 추출·설정). 자료: GET /api/docs/{id}/headings/llm-changes(app/heading_llm_diff.py — 읽기만).
// LLM 판정은 분석 결과만 바꾼다 — 문서는 그대로다. 문서 서식을 바꾸는 것은 서식 계획의 반영(헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」 · 템플릿 줄 「계획대로 맞추기」 · ★ 열 「적용」 — 여기에는 반영 단추를 두지 않는다: design.md §10).
// 항목을 누르면 문서의 그 문단·칸으로(열은 그대로 — 나란히 본다). 값을 견줄 때는 두 값에 이름을 단다(「스크립트 미판정 56 → LLM 맞춤 43」 — 화살표 = 바뀐 쪽).
// app.js · tables.js · tpl_agent.js 다음에 읽힌다(el·hBtn·hHelp·api·toast·heads·state·headsDlg·headsParaLink·headsRunOpen·headsTables·tplAgentOpen·fmtWhen·fmtDur·nf·short·oneLine·
// H_KIND·H_VERDICT·H_ROLE·H_TROLE·H_DECISION·H_AREA).
const LLD = { data: null, key: null, stage: null, epoch: null, busy: false, err: "" };
const LLD_STAGE = { 1: "규칙 보강", 2: "헤딩 판정", 3: "표 판정", rel: "템플릿 관계", res: "반영 결과", fmt: "서식 계획" };
const lldOn = () => { const c = $("headsDlg"); return !!c && !c.hidden && c.dataset.kind === "llmDiff"; };
const lldRunKey = (r) => JSON.stringify([1, 2, 3].map((k) => { const s = r && r[`stage${k}`]; return s && s.meta ? s.meta.run : null; }).concat([r && r.rules ? r.rules.run : null]));
const lldRole = (x) => (x === "heading" ? "헤딩" : x === "not_heading" ? "헤딩 아님" : H_ROLE[x] || x || "—");
const lldText = (pid) => (state.texts && state.texts[pid] != null ? state.texts[pid] : (state.byId && state.byId.get(pid) || {}).text || "");
const lldMoney = (v) => (v ? ` · $${(+v).toFixed(2)}` : "");

function llmDiffOpen(stage = null) { // 진행 줄의 LLM ✓ 칸 → 이 열(그 단계 절로)
  if (!state.id || state.format !== "hwpx") { toast("LLM 이 바꾼 것은 헤딩 추출을 돌린 HWPX 문서에서 봅니다"); return; }
  LLD.stage = stage;
  headsDlg("llmDiff", "LLM 이 바꾼 것", "스크립트가 낸 것과 LLM 이 다르게 정한 것 · 누르면 문서의 그 자리로");
  $("headsDlgHelp").replaceChildren(hHelp("LLM 이 바꾼 것 도움말", "LLM 판정(규칙 보강 · 헤딩 판정 · 표 판정)은 분석 결과만 바꿉니다 — 문서 글·서식은 그대로입니다. "
    + "각 절은 그 단계의 스크립트 결과(또는 LLM 이 받은 초안)와 LLM 의 답이 다른 곳입니다. 문서 서식을 대표에 맞추는 것은 맨 아래 「서식 계획」 을 반영할 때뿐입니다 — 한 번에: 헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」 · 템플릿 하나만: 템플릿 줄의 「계획대로 맞추기」 나 ★ 열.", { note: true }));
  if (LLD.epoch !== state.epoch) LLD.data = null;
  lldDraw();
  lldLoad();
}

async function lldLoad() {
  if (LLD.busy) return;
  const id = state.id, epoch = state.epoch;
  LLD.busy = true;
  LLD.err = "";
  hFoot("읽는 중…", false);
  try {
    const d = await api(`/api/docs/${id}/headings/llm-changes`);
    if (epoch !== state.epoch) return;
    Object.assign(LLD, { data: d, epoch, key: lldRunKey(heads.view) });
  } catch (e) {
    if (epoch === state.epoch) LLD.err = e.status === 404 && /not found/i.test(e.message || "") ? "서버가 옛 판이라 이 목록을 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요" : `읽지 못했습니다: ${e.message}`;
  } finally {
    LLD.busy = false;
  }
  if (epoch === state.epoch && lldOn()) lldDraw(true);
}

function llmDiffSync(r) { // 헤딩 요약을 다시 그릴 때(app.js headsProgLine) — 열이 열려 있고 그 사이 실행이 바뀌었으면 다시 읽는다
  if (lldOn() && LLD.data && !LLD.busy && LLD.key !== lldRunKey(r)) { LLD.stage = null; lldLoad(); }
}

function lldGo(pid) { if (typeof headsGo === "function") headsGo(pid); }
function lldCellGo(tid, cid) { // 표 칸으로(쪽에 걸친 칸은 글이 든 첫 조각) — 없으면 표로
  const td = [...document.querySelectorAll(`#doc td[data-cell="${CSS.escape(cid || "")}"]`)].find((x) => x.querySelector(".para")) || document.querySelector(`#doc td[data-cell="${CSS.escape(cid || "")}"]`);
  const t = td || document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`);
  if (!t) { toast("그 표가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)"); return; }
  t.scrollIntoView({ block: "center", behavior: "smooth" });
  t.classList.remove("lld-flash");
  void t.offsetWidth;
  t.classList.add("lld-flash");
}
function lldPara(pid, text, n = 40, extra = "") { return headsParaLink(pid, text || lldText(pid) || pid, n, extra); }

function lldDraw(loaded = false) {
  const body = $("headsDlgBody"), tools = $("headsDlgTools"), d = LLD.data;
  tools.textContent = "";
  body.textContent = "";
  if (!d) {
    body.append(el("p", LLD.err ? "hwarn pad" : "hnote pad", LLD.err || "읽는 중…"));
    if (LLD.err) hFoot(LLD.err);
    return;
  }
  // 절 차례 = 일의 차례: LLM 판정 셋 → 조정(템플릿 관계 제안 → 반영 결과 → 서식 계획). 「반영 결과」 는 실행마다 실제로 바뀐 것(전 → 후 값 · 뗀 것 · 남긴 것과 까닭 — spec_헤딩_추출 ② §7 「결과 화면」)
  const secs = [["1", lldRules(d.rules)], ["2", lldHeads(d.heads)], ["3", lldTables(d.tables)], ["rel", lldRelations(d.relations)], ["res", lldApplies(d.applies)], ["fmt", lldFormats(d.formats)]];
  const nav = el("div", "lld-nav");
  nav.setAttribute("role", "group");
  nav.setAttribute("aria-label", "절로 가기");
  for (const [k, s] of secs) {
    const b = hBtn("", () => { s.sec.scrollIntoView({ block: "start", behavior: "smooth" }); s.sec.open = true; }, { cls: `lld-jump${s.n ? " has" : ""}` });
    b.append(el("span", null, LLD_STAGE[k]), el("b", null, s.badge));
    b.title = s.tip;
    nav.append(b);
  }
  tools.append(nav, hBtn("다시 읽기", () => lldLoad(), { title: "지금 결과로 다시 모읍니다(LLM 을 부르지 않음)" }));
  const lead = el("p", "lld-lead", "LLM 판정은 분석 결과(규칙 · 헤딩 그래프 · 표 구조)만 바꿉니다 — 문서 글·서식은 그대로입니다. 문서 서식을 맞추는 것은 맨 아래 「서식 계획」.");
  const last = typeof HRA === "object" && HRA.last && HRA.last.id === state.id ? HRA.last.text : ""; // 지난 「전체 실행」 의 끝난 글(한 것 · 멈춘 까닭 · 남은 것) — 알림이 사라진 뒤에도 여기 남는다
  if (last) {
    const run = el("p", "lld-run-last");
    run.append(el("b", null, "지난 전체 실행 "), last);
    body.append(run);
  }
  body.append(lead, ...secs.map(([, s]) => s.sec));
  hFoot(`문서 차례 ${d.rev ?? "–"} 의 결과 · 실행 번호·시각은 절 머리`, false);
  if (loaded && LLD.stage != null) { // 진행 줄에서 누른 단계 절로
    const s = secs.find(([k]) => k === String(LLD.stage));
    if (s) { s[1].sec.open = true; requestAnimationFrame(() => s[1].sec.scrollIntoView({ block: "start" })); }
  }
}

function lldSection(k, title, meta, open = true) { // → {sec, body} — <details> 절(머리 = 이름 · 실행 정보 · 추출·설정 단추)
  const sec = el("details", "lld-sec");
  sec.open = open;
  sec.dataset.stage = k;
  const sum = el("summary", "lld-head");
  sum.append(el("b", null, title), el("span", "lld-meta", meta || ""));
  sec.append(sum);
  const body = el("div", "lld-body");
  sec.append(body);
  return { sec, body };
}
function lldMetaOf(p) { return p ? `실행 ${p.run ?? "–"} · ${fmtWhen(p.at)}${p.seconds ? ` · ${fmtDur(p.seconds)}` : ""}${lldMoney(p.costUsd)}` : ""; }
function lldLines(box, lines) { // 요약 줄(ul) — [글, cls?, title?]
  const ul = el("ul", "lld-sum");
  for (const ln of lines.filter(Boolean)) {
    const [t, cls, title] = Array.isArray(ln) ? ln : [ln];
    const li = el("li", cls || null, t);
    if (title) li.title = title;
    ul.append(li);
  }
  box.append(ul);
}
function lldSays(box, text, who = "LLM 요약") { if (text) { const q = el("p", "lld-says"); q.append(el("b", null, `${who} `), text); box.append(q); } }
function lldMore(label, open = false) { const d = el("details", "lld-more"); d.open = open; d.append(el("summary", null, label)); return d; }
function lldChip(text, cls) { return el("span", `lld-chip ${cls || ""}`, text); }
function lldStageBtn(box, k) { box.append(hBtn("추출·설정에서", () => headsRunOpen(k), { cls: "btn sm lld-run", title: `헤딩 추출 「추출·설정」 ${k}단계 탭 — 실행·지침·자세한 표` })); }

// ---- ① 규칙 보강
function lldRules(p) {
  if (!p) {
    const s = lldSection("1", "규칙 보강", "안 함", false);
    s.body.append(el("p", "hnote", "규칙 보강을 돌린 적이 없습니다 — 스크립트가 판정하지 못한 첫머리(못 맞춤·충돌)를 LLM 에 묻는 일입니다."));
    lldStageBtn(s.body, 1);
    return { ...s, n: 0, badge: "–", tip: "규칙 보강 안 함" };
  }
  const c = p.counts || {}, s = lldSection("1", "규칙 보강", lldMetaOf(p));
  lldLines(s.body, [
    p.asked === false ? [`LLM 답을 못 받음 — ${p.error || "까닭 모름"}`, "bad"] : null,
    `물은 묶음 ${nf(p.groups)} → 규칙 저장 ${nf(c.saved)} · 거절 ${nf(c.rejected)}${c.kept ? ` · 그대로 ${nf(c.kept)}` : ""}${c.unsure ? ` · 모름 ${nf(c.unsure)}` : ""}${c.duplicate ? ` · 중복 ${nf(c.duplicate)}` : ""}`,
    [`지금 남은 못 맞춤·충돌 ${nf(p.left)}묶음`, p.left ? "warn" : null],
    p.current ? null : ["지금 1단계 결과는 그 뒤 스크립트로 다시 뽑은 것 — 저장한 규칙은 그대로 쓰였습니다(아래 문단은 지금 결과에서 그 규칙이 판정한 것)", "muted"],
  ]);
  for (const it of p.items || []) {
    const row = el("div", `lld-item v-${it.verdict}`), top = el("div", "lld-top");
    top.append(lldChip(H_VERDICT[it.verdict] || it.verdict, it.verdict === "saved" ? "good" : it.verdict === "rejected" ? "warn" : ""));
    const name = el("span", "lld-name", it.name ? `「${it.name}」` : it.group || "");
    name.title = `묶음 ${it.group || "—"}${it.pattern ? `\n정규식 ${it.pattern}` : ""}${it.scope ? ` · ${it.scope === "whole" ? "글 전체" : "첫머리"}` : ""}${it.first ? " · 앞선 규칙" : ""}${it.rule ? `\n규칙 ${it.rule}` : ""}`;
    top.append(name);
    if (it.kind) top.append(el("span", "lld-to", `→ ${H_KIND[it.kind] || it.kind}`));
    if (it.verdict === "saved") top.append(el("span", "lld-n", `${nf(it.parasTotal)}문단`));
    row.append(top);
    if (it.reason) row.append(el("p", "lld-why", it.reason));
    if (it.verdict !== "saved" && it.why) row.append(el("p", "lld-why warn", `검증: ${it.why}`));
    if (it.paras && it.paras.length) {
      const m = lldMore(`문단 ${nf(it.parasTotal)} 보기`), ul = el("ul", "lld-paras");
      for (const x of it.paras) { const li = el("li"); li.append(lldPara(x.id, x.text, 50)); ul.append(li); }
      if (it.parasTotal > it.paras.length) ul.append(el("li", "muted", `외 ${nf(it.parasTotal - it.paras.length)}문단`));
      m.append(ul);
      row.append(m);
    }
    s.body.append(row);
  }
  lldStageBtn(s.body, 1);
  return { ...s, n: c.saved || 0, badge: nf(c.saved || 0), tip: `규칙 저장 ${nf(c.saved)} · 거절 ${nf(c.rejected)}` };
}

// ---- ② 헤딩 판정
function lldHeads(p) {
  if (!p || !p.llm) {
    const s = lldSection("2", "헤딩 판정", p ? (p.fallback ? "LLM 실패 — 스크립트로 대신함" : "안 함") : "결과 없음", false);
    s.body.append(el("p", p && p.fallback ? "hwarn" : "hnote", !p ? "2단계(헤딩 그래프) 결과가 없습니다."
      : p.fallback ? `LLM 을 불렀지만 실패해 스크립트 결과로 대신했습니다 — ${p.error || "까닭 모름"}` : "지금 헤딩 그래프는 스크립트 결과입니다 — LLM 판정을 거치지 않았습니다."));
    lldStageBtn(s.body, 2);
    return { ...s, n: 0, badge: "–", tip: "헤딩 판정 안 함" };
  }
  const s = lldSection("2", "헤딩 판정", lldMetaOf(p)), a = p.adjust || {}, mc = p.mainChain || {}, base = p.base && p.base.summary, cnt = p.counts || {};
  lldSays(s.body, p.summary);
  const chain = (x) => `「${(x || []).join(" › ")}」`;
  const same = JSON.stringify(mc.proposal || []) === JSON.stringify(mc.fixed || []);
  lldLines(s.body, [
    [`구조(부모·역할·템플릿·레벨): LLM 이 초안과 다르게 정한 노드 ${nf(p.nodesTotal)}${p.nodesTotal ? "" : " — 스크립트 초안 그대로"}`, p.nodesTotal ? "chg" : null,
      "본문 구간마다 스크립트 초안을 LLM(B 호출)에 보여 주고 다르게 볼 노드만 받습니다"],
    p.rejectedTotal ? [`검증에서 버린 LLM 변경 ${nf(p.rejectedTotal)}`, "warn"] : null,
    p.undecided ? [`미판정 노드 ${nf(p.undecided)} — LLM 이 판정하지 못한 구간(초안 그대로)`, "warn"] : null,
    mc.fixed && mc.fixed.length ? (same || !mc.proposal.length ? `주 사슬 ${chain(mc.fixed)} — 스크립트 제안 그대로 확인` : [`주 사슬: 스크립트 제안 ${chain(mc.proposal)} → LLM ${chain(mc.fixed)}`, "chg"]) : null,
    [`유형 ${nf((p.types || []).length)}개: 역할을 스크립트와 다르게 본 유형 ${nf(p.typesChanged)} · 다른 유형의 변형으로 본 유형 ${nf(p.variants)}`, p.typesChanged ? "chg" : null,
      "변형 = 크기·굵기만 조금 다른 같은 구실의 레터(같은 레벨로 셈)"],
    base && base.heuristic ? [`부모: 스크립트(실행 ${p.base.run})는 어림으로 둔 부모 ${nf(base.heuristic)}곳 → LLM ${nf(cnt.heuristic || 0)}곳`, null, "어림 = 레터 차례·앞 공백만으로 정한 부모(확정 사실로 안 봄)"] : null,
    a.asked === false // 서식 쌍 판정(C·D)은 기본 실행에서 뺐다(2026-11-16 — spec_헤딩_추출 ② §6): 「미판정」 을 실패처럼 보이지 않게
      ? [`서식 쌍 판정은 하지 않았습니다 — 같은 템플릿의 서식은 「조정」 층의 서식 정리 계획이 정합니다(대표와 서식 라벨이 다른 문단 ${nf(a.undecided)})`, "muted",
        "서식 쌍 판정(맞춤 · 다름 유지)과 그 재검토는 문서도 서식 계획도 바꾸지 않아 기본 실행에서 뺐습니다 — 켜려면 서버 설정 NFM_HEADS_PAIRS=on"]
      : [`서식 쌍 판정(조정): 스크립트 미판정 → LLM 맞춤 ${nf(a.adjust)}문단 · 다름 유지 ${nf(a.keep)}${a.undecided ? ` · 미판정 ${nf(a.undecided)}` : ""}${a.disagreed ? `(재검토 불일치 ${nf(a.disagreed)})` : ""}`,
        a.adjust || a.keep ? "chg" : null, `같은 템플릿 레벨에서 대표와 서식 라벨이 다른 문단 — 같은 구실이면 「맞춤」(쌍 ${nf(a.pairs)} · 재검토 ${nf(a.reviewPairs)})`],
    ["이 판정은 분석 결과입니다 — 문서 서식은 맨 아래 「서식 계획」 을 반영할 때 바뀝니다", "muted"],
  ]);
  if ((p.nodes || []).length) {
    const m = lldMore(`LLM 이 바꾼 노드 ${nf(p.nodesTotal)}`, true), ul = el("ul", "lld-rows");
    for (const x of p.nodes) {
      const li = el("li"), b = x.before || {}, f = x.after || {}, parts = [];
      if (b.role !== f.role) parts.push(`역할 ${lldRole(b.role)} → ${lldRole(f.role)}`);
      if (b.parent !== f.parent) parts.push(`부모 「${short(b.parentText || "(뿌리)", 18)}」 → 「${short(f.parentText || "(뿌리)", 18)}」`);
      if (b.slot !== f.slot) parts.push(`자리 ${b.slot || "스크립트"} → ${f.slot || "스크립트"}`);
      li.append(lldPara(x.para, x.text, 36), el("span", "lld-to", parts.join(" · ") || "변경"));
      if (x.reason) li.append(el("p", "lld-why", x.reason));
      ul.append(li);
    }
    m.append(ul);
    s.body.append(m);
  }
  for (const [list, label, key] of [[p.rejected, "검증에서 버린 변경", "why"], [p.undecidedNodes, "미판정 노드", null]]) {
    if (!(list || []).length) continue;
    const m = lldMore(`${label} ${nf(list.length)}`), ul = el("ul", "lld-rows");
    for (const x of list) { const li = el("li"); li.append(lldPara(x.para, x.text, 36)); if (key && x[key]) li.append(el("p", "lld-why warn", x[key])); ul.append(li); }
    m.append(ul);
    s.body.append(m);
  }
  if ((p.types || []).length) {
    const m = lldMore(`유형 판정 ${nf(p.types.length)}`), [t, tb] = hTable(["유형", "꼴", "노드", "역할 스크립트 → LLM", "변형", "까닭"]);
    for (const x of p.types) {
      const tr = el("tr", x.changed ? "chg" : null);
      hCell(tr, x.type);
      hCell(tr, x.shape, "code", `${H_AREA[x.area] || x.area || ""} · ${x.kind || ""}${x.size ? ` · ${x.size}pt` : ""}${x.bold ? " · 굵게" : ""}`);
      hCell(tr, nf(x.nodes));
      hCell(tr, x.changed ? `${lldRole(x.script)} → ${lldRole(x.role)}` : lldRole(x.role));
      hCell(tr, x.variantOf ? `${x.variantOf} 의 변형` : "");
      hCell(tr, x.reason, "wrap");
      tb.append(tr);
    }
    m.append(t);
    s.body.append(m);
  }
  if ((a.groups || []).length) {
    const m = lldMore(`서식 쌍 판정 — 맞춤 ${nf(a.adjust)} · 다름 유지 ${nf(a.keep)}${a.undecided ? ` · 미판정 ${nf(a.undecided)}` : ""}`), ul = el("ul", "lld-rows");
    for (const g of a.groups) {
      const li = el("li", `d-${g.decision}`), top = el("div", "lld-top");
      const dec = g.verdict === "disagree" ? `미판정(재검토 불일치 · 1차 ${H_DECISION[g.first] || g.first})` : `${g.decision === "adjust" ? "맞춤" : H_DECISION[g.decision] || g.decision}${g.verdict === "agree" ? " ✓" : ""}`;
      top.append(lldChip(dec, g.decision === "adjust" ? "good" : g.decision === "undecided" ? "warn" : ""), el("span", "lld-name", `T${g.tplNo ?? "?"} L${g.level} 「${short(g.letter || "", 6)}」`));
      const fm = el("span", "lld-to", `${g.from} → 대표 ${g.to}`);
      fm.title = `${g.fromName || g.from}\n→ 대표 ${g.toName || g.to}`;
      top.append(fm, el("span", "lld-n", `${nf(g.n)}문단`));
      li.append(top);
      if (g.reason) li.append(el("p", "lld-why", g.reason));
      if (g.review && g.verdict === "disagree") li.append(el("p", "lld-why warn", `재검토: ${g.review}`));
      const ps = el("div", "lld-plinks");
      for (const pid of g.paras || []) ps.append(lldPara(pid, "", 22));
      if (g.n > (g.paras || []).length) ps.append(el("span", "muted", `외 ${nf(g.n - g.paras.length)}`));
      li.append(ps);
      ul.append(li);
    }
    m.append(ul);
    s.body.append(m);
  }
  lldStageBtn(s.body, 2);
  const n = (p.nodesTotal || 0) + (p.typesChanged || 0) + (a.adjust || 0) + (a.keep || 0);
  return { ...s, n, badge: nf(n), tip: `노드 변경 ${nf(p.nodesTotal)} · 유형 역할 ${nf(p.typesChanged)} · 서식 쌍 판정 ${nf((a.adjust || 0) + (a.keep || 0))}문단` };
}

// ---- ③ 표 판정
function lldTables(p) {
  if (!p || !p.llm) {
    const s = lldSection("3", "표 판정", p ? (p.fallback ? "LLM 실패 — 스크립트로 대신함" : "안 함") : "결과 없음", false);
    s.body.append(el("p", p && p.fallback ? "hwarn" : "hnote", !p ? "3단계(표 구조) 결과가 없습니다."
      : p.fallback ? `LLM 을 불렀지만 실패해 스크립트 결과로 대신했습니다 — ${p.error || "까닭 모름"}` : "지금 표 구조는 스크립트 결과입니다 — LLM 판정을 거치지 않았습니다."));
    lldStageBtn(s.body, 3);
    return { ...s, n: 0, badge: "–", tip: "표 판정 안 함" };
  }
  const s = lldSection("3", "표 판정", lldMetaOf(p)), rows = p.tables || [], base = p.base && p.base.summary, cnt = p.counts || {};
  const touched = rows.filter((t) => t.changedTotal || (t.draftSubs != null && t.draftSubs !== t.subs));
  lldSays(s.body, p.summary);
  const roleDiff = base && base.roles ? Object.keys({ ...base.roles, ...(cnt.roles || {}) }).filter((k) => (base.roles[k] || 0) !== ((cnt.roles || {})[k] || 0))
    .map((k) => `${H_TROLE[k] || k} ${nf(base.roles[k] || 0)} → ${nf((cnt.roles || {})[k] || 0)}`).join(" · ") : "";
  lldLines(s.body, [
    `보낸 표 ${nf(p.sent)}${p.skipped ? ` · 안 보낸 표 ${nf(p.skipped)}(1칸 표 등)` : ""} → 칸 역할을 바꾼 표 ${nf(rows.filter((t) => t.changedTotal).length)} · 바꾼 칸 ${nf(p.applied)}`,
    p.rejected ? [`검증에서 버린 칸 변경 ${nf(p.rejected)}`, "warn"] : null,
    p.undecided ? [`답을 못 받은 표 ${nf(p.undecided)} — 초안 그대로`, "warn"] : null,
    base ? [`서브 테이블: 스크립트(실행 ${p.base.run}) ${nf(base.subtables)}개 → 지금 ${nf(cnt.subtables)}개`, base.subtables !== cnt.subtables ? "chg" : null] : null,
    roleDiff ? [`칸 역할 수 — 스크립트(실행 ${p.base.run}) → 지금: ${roleDiff}`, "chg"] : null,
  ]);
  const tableRow = (t) => {
    const li = el("li"), top = el("div", "lld-top");
    const name = hBtn(`${t.id}`, () => lldCellGo(t.id, null), { cls: "hlink lld-tid", title: "문서에서 그 표로" });
    top.append(name, el("span", "lld-name", short(t.before || `${t.rows}행 × ${t.cols}열`, 24)));
    if (t.changedTotal) top.append(el("span", "lld-n", `칸 ${nf(t.changedTotal)} 바꿈`));
    if (t.draftSubs != null && t.draftSubs !== t.subs) top.append(el("span", "lld-n", `서브 테이블 초안 ${nf(t.draftSubs)} → LLM ${nf(t.subs)}`));
    else if (t.draftSubs == null && t.subs > 1) top.append(el("span", "lld-n muted", `서브 테이블 ${nf(t.subs)}`));
    if (typeof headsTables === "function") top.append(hBtn("표 구조", () => headsTables(t.id), { cls: "btn sm lld-open", title: "칸 역할 격자(이 열에서 — 파란 테두리 = LLM 이 바꾼 칸)" }));
    li.append(top);
    if (t.summary) li.append(el("p", "lld-why", t.summary));
    if (t.error) li.append(el("p", "lld-why warn", t.error));
    if ((t.changed || []).length) {
      const ul = el("ul", "lld-cells");
      for (const c of t.changed) {
        const ci = el("li"), b = hBtn(`「${short(c.text || "(빈 칸)", 16)}」`, () => lldCellGo(t.id, c.id), { cls: "hlink", title: `${c.id} · ${c.row + 1}행 ${c.col + 1}열 — 문서에서 그 칸으로` });
        ci.append(b, el("span", "lld-to", `${H_TROLE[c.draft] || c.draft} → ${H_TROLE[c.role] || c.role}`));
        if (c.reason) ci.append(el("span", "lld-why", c.reason));
        ul.append(ci);
      }
      if (t.changedTotal > t.changed.length) ul.append(el("li", "muted", `외 ${nf(t.changedTotal - t.changed.length)}칸`));
      li.append(ul);
    }
    return li;
  };
  if (touched.length) { const ul = el("ul", "lld-rows"); touched.forEach((t) => ul.append(tableRow(t))); s.body.append(ul); }
  const rest = rows.filter((t) => !touched.includes(t));
  if (rest.length) {
    const m = lldMore(`칸을 바꾸지 않은 표 ${nf(rest.length)}${rest.some((t) => !t.sent) ? ` (안 보낸 표 ${nf(rest.filter((t) => !t.sent).length)})` : ""}`), ul = el("ul", "lld-rows");
    rest.forEach((t) => ul.append(tableRow(t)));
    m.append(ul);
    s.body.append(m);
  }
  if (rows.length && rows.every((t) => t.draftSubs == null)) s.body.append(el("p", "hnote", "표마다 서브 테이블 초안 수는 이 기능 뒤에 돌린 표 판정부터 남습니다(지금 결과는 그 전 실행)."));
  lldStageBtn(s.body, 3);
  return { ...s, n: p.applied || 0, badge: nf(p.applied || 0), tip: `바꾼 칸 ${nf(p.applied)} · 보낸 표 ${nf(p.sent)}` };
}

// ---- 템플릿 관계 제안(종속 — spec_hwpx_웹편집 ② §8-2 「종속 제안」): 한 자리에만 매달린 가지 템플릿을 그 자리의 템플릿 아래로. 확실한 것(sure)은 「모두 반영」·「전체 실행」 이 저절로 넣고, 애매한 것은 여기서 「하위로 넣기」 를 눌러야 한다(문서는 안 바뀜 · 실행 취소 1)
function lldRelations(list) {
  const hints = list || [], s = lldSection("rel", "템플릿 관계 — 종속 제안", hints.length ? `제안 ${nf(hints.length)}` : "없음", !!hints.length);
  if (!hints.length) {
    s.body.append(el("p", "hnote", "종속으로 넣을 만한 템플릿이 없습니다 — 한 자리에만 매달린 가지 템플릿이 있을 때 여기에 제안합니다(여러 자리에서 같이 쓰는 템플릿 · 자리마다 다른 템플릿은 그대로 둡니다)."));
    return { ...s, n: 0, badge: "–", tip: "종속 제안 없음" };
  }
  lldLines(s.body, [["가지 템플릿이 **한 자리의 줄 아래에만** 오면 그 자리의 템플릿 아래 종속 템플릿(T1T3 꼴)으로 넣을 수 있습니다 — 레벨이 윗템플릿에서 이어지고 서식 정리도 그 템플릿으로 합니다. 「확실」 은 「모두 반영」·「전체 실행」 이 저절로 넣고(「실행 취소」 한 번으로 되돌립니다), 「애매」 는 여기서 「하위로 넣기」 를 눌러야 바뀝니다 — 문서 글·서식은 안 바뀌고 템플릿만 바뀝니다.".replace(/\*\*/g, ""), "muted"]]);
  for (const h of hints) {
    const row = el("div", "lld-item"), top = el("div", "lld-top");
    top.append(el("b", "lld-name", `T${h.childNo}`), el("span", "lld-meta", `${(h.chain || []).join(" › ")} · ${nf(h.lines)}줄`),
      lldChip(`T${h.parentNo} L${h.at} 줄 아래에만 ${nf(h.places)}곳`, "good"),
      lldChip(h.sure ? "확실 — 「모두 반영」·「전체 실행」 이 넣습니다" : `애매 — 제안만${h.why ? `: ${h.why}` : ""}`, h.sure ? "" : "warn"));
    const go = hBtn("하위로 넣기", async () => {
      go.disabled = true;
      const r = await structOp("outline/merge", { child: h.child, parent: h.parent, at: h.at });
      if (r && r.merged) toast(`T${h.childNo} 를 T${h.parentNo} L${h.at} 아래 종속 템플릿 T${r.merged.no} 로 넣었습니다(줄 ${nf(r.merged.moved)}) — 문서는 안 바뀜 · 「실행 취소」 한 번 · 풀려면 「템플릿 관계」 의 「떼기」`);
      if (typeof outlineLoad === "function") outlineLoad(true);
      if (typeof olmLoad === "function") olmLoad(true).then(() => { if (typeof olmRefresh === "function") olmRefresh(); });
      if (typeof docStatusPing === "function") docStatusPing();
      lldLoad();
    }, { cls: "btn sm lld-open", title: `T${h.childNo} 의 줄을 T${h.parentNo} 의 L${h.at + 1} 부터로 옮긴 종속 템플릿을 만듭니다 — 문서 글·서식은 안 바뀌고 템플릿만 바뀝니다(실행 취소 1). 넣은 뒤 그 템플릿의 서식 계획은 다시 받습니다` });
    top.append(go);
    if (typeof tplRelOpen === "function") top.append(hBtn("템플릿 관계에서", () => tplRelOpen(/^\d+$/.test(String(h.child)) ? +h.child : h.child), { cls: "btn sm lld-open", title: "「템플릿 관계」 열에서 이 템플릿이 매달린 자리를 봅니다" }));
    row.append(top);
    s.body.append(row);
  }
  const nSure = hints.filter((h) => h.sure).length;
  return { ...s, n: hints.length, badge: nf(hints.length), tip: `종속 제안 ${nf(hints.length)} — 확실 ${nf(nSure)}(「모두 반영」·「전체 실행」 이 넣음) · 애매 ${nf(hints.length - nSure)}(사람이 「하위로 넣기」)` };
}

// ---- 반영 결과(실행마다 — spec_헤딩_추출 ② §7 「결과 화면」): 「모두 반영」·「전체 실행」·「적용」 이 실제로 바꾼 것 — 갈래마다 전 → 후 값 · 뗀 것 · 남긴 것과 까닭. 계획(아래 절)은 다음 계획이 덮지만 이 기록은 남는다
const LLD_KEEP = (k) => (k.byUser ? "사람이 그대로로 고름" : k.carried && !k.auto ? "앞 계획에서 그대로 둠" : k.auto ? "에이전트 답 없음 — 안 바꿈" : k.why || "에이전트가 그대로 둠");
function lldApplies(list) {
  const runs = [...(list || [])].reverse(), s = lldSection("res", "반영 결과", runs.length ? `반영 ${nf(runs.length)}번` : "없음", !!runs.length);
  if (!runs.length) {
    s.body.append(el("p", "hnote", "아직 반영한 서식 계획이 없습니다 — 「전체 실행」 이나 조정 층의 「모두 반영」 · 「템플릿 서식 정리」 열의 「적용」 으로 반영하면, 무엇이 어떻게 바뀌었는지(전 → 후 값) · 무엇을 남겼는지가 여기 남습니다."));
    return { ...s, n: 0, badge: "–", tip: "반영 기록 없음" };
  }
  const diffText = (g) => (g.diff || []).slice(0, 4).map((d) => `${d[0]} ${d[1]} → ${d[2]}`).join(" · ") + ((g.diff || []).length > 4 ? ` 외 ${g.diff.length - 4}` : "");
  const line = (ul, kind, cls, g, tail) => {
    const li = el("li", cls);
    li.append(el("b", "lld-kind", kind), ` ×${nf(g.count || 0)} `, lldPara(g.para, g.sample, 34), tail ? el("span", "lld-diff", ` — ${tail}`) : "");
    ul.append(li);
  };
  let lines = 0;
  runs.forEach((R, i) => {
    const row = el("div", "lld-item"), top = el("div", "lld-top"), live = (R.templates || []).some((t) => t.live);
    top.append(el("b", "lld-name", R.by === "all" ? "모두 반영" : "템플릿 하나 적용"), el("span", "lld-meta", `${fmtWhen(R.at)} · 바뀐 줄 ${nf(R.lines || 0)}`));
    if ((R.templates || []).length) top.append(lldChip(live ? "지금 문서에 남아 있음" : "되돌림 — 지금 문서에는 없음", live ? "good" : "warn"));
    row.append(top);
    if ((R.relations || []).length) row.append(el("p", "lld-why", `템플릿 종속 ${nf(R.relations.length)} — ${R.relations.map((m) => `T${m.childNo} → T${m.no}(T${m.parentNo} L${m.at} 아래 · 줄 ${nf(m.moved)})`).join(" · ")} · 문서는 안 바뀜`));
    if (i === 0 && live) lines = R.lines || 0;
    for (const T of R.templates || []) {
      const box = i ? lldMore(`T${T.no ?? T.tpl} — 바뀐 줄 ${nf(T.changed || 0)}`, false) : el("div", "lld-tpl");
      if (!i) box.append(el("p", "lld-why", `T${T.no ?? T.tpl} — 바뀐 줄 ${nf(T.changed || 0)}${T.live ? "" : " · 되돌림"}${T.summary ? ` · ${T.summary}` : ""}`));
      for (const L of T.levels || []) {
        const ul = el("ul", "lld-rows");
        const head = el("li", "lld-lv");
        head.append(el("b", null, `L${L.level} 「${short(L.letter || "", 6)}」 ${nf(L.lines || 0)}줄`), " 대표 ", L.rep && L.rep.para ? lldPara(L.rep.para, L.rep.sample, 30) : "–", L.rep && L.rep.changed ? lldChip("대표 바꿈", "chg") : "");
        ul.append(head);
        for (const g of L.match || []) line(ul, "맞춤", "chg", g, diffText(g));
        for (const sp of L.split || []) {
          line(ul, `T${T.no ?? T.tpl}L${L.level}${sp.sfx || ""} 로 뗌`, "chg", sp.rep || {}, "새 템플릿의 대표");
          for (const g of sp.match || []) line(ul, "뗀 줄 맞춤", "chg", g, diffText(g));
        }
        for (const k of L.keep || []) {
          const li = el("li", "kept");
          li.append(el("b", "lld-kind", "그대로"), ` ×${nf(k.count || 0)} `, lldPara(k.para, k.sample, 34), el("span", "lld-diff", ` — ${LLD_KEEP(k)}`));
          if (typeof tplRelOpen === "function") li.append(" ", hBtn("서식 보기", () => tplRelOpen(/^\d+$/.test(String(T.tpl)) ? +T.tpl : T.tpl, { tpl: T.tpl, level: L.level, para: k.para }),
            { cls: "btn sm lld-open", title: "「템플릿 관계」 열에서 이 줄의 서식 — 대표에 맞추거나 「다른 템플릿으로」 뗍니다" }));
          ul.append(li);
        }
        const more = [L.omitted ? `서식 가짓수가 많아 못 본 서식 ${nf(L.omitted)}가지(다음 계획이 받습니다)` : "", L.values ? `값 칸 ${nf(L.values)}줄(표 칸에 혼자 있는 레터 — 맞추지 않음)` : ""].filter(Boolean);
        if (more.length) ul.append(el("li", "muted", more.join(" · ")));
        box.append(ul);
      }
      row.append(box);
    }
    s.body.append(row);
  });
  lldLines(s.body, [["되돌리려면 「실행 취소」(반영 한 번 = 한 번) — 한 서식만 달리 하려면 되돌린 뒤 그 서식을 「템플릿 관계」 에서 「다른 템플릿으로」 떼고 다시 「전체 실행」 을 누르세요(계획은 다시 받지 않고 그대로 씁니다).", "muted"]]);
  return { ...s, n: lines, badge: lines ? `${nf(lines)}줄` : nf(runs.length), tip: `반영 ${nf(runs.length)}번 — 맨 위가 마지막 것` };
}

// ---- ④ 서식 계획(★)
const LLD_PLAN = { planned: "아직 반영 안 함", applied: "반영함", stale: "옛 계획 — 다시 받기" };
function lldFormats(list) {
  const plans = list || [], s = lldSection("fmt", "서식 계획", plans.length ? `템플릿 ${nf(plans.length)}개 · ★ 템플릿 서식 정리` : "없음", !!plans.length);
  if (!plans.length) {
    s.body.append(el("p", "hnote", "받아 둔 서식 정리 계획이 없습니다 — 「헤딩 그래프(LLM)」 이 헤딩 판정 뒤에 이어서, 서식이 여러 가지인 템플릿마다 받습니다(헤딩 추출 탭 진행 줄 「조정」 의 「계획 받기」 · 템플릿 줄의 ★ 로도)."));
    return { ...s, n: 0, badge: "–", tip: "서식 계획 없음" };
  }
  lldLines(s.body, [["계획은 LLM 이 레벨마다 대표와 맞출 줄 · 따로 뗄 줄(레터가 다른 줄 → 서식 종속 템플릿) · 남길 줄을 고른 것입니다. 반영은 헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」(「템플릿 조정」·「서식 조정」 옆 — 모든 템플릿을 한 번에 · 실행 취소 한 번으로 되돌림) — 템플릿 하나만은 템플릿 줄의 「계획대로 맞추기」 · 고르기를 바꾸려면 「★ 계획 열기」", "muted"]]);
  let todo = 0;
  for (const P of plans) {
    const row = el("div", `lld-item p-${P.state}`), top = el("div", "lld-top");
    top.append(el("b", "lld-name", `T${P.no ?? P.tpl}`), lldChip(LLD_PLAN[P.state] || P.state || "", P.state === "planned" ? "good" : P.state === "stale" ? "warn" : ""),
      el("span", "lld-meta", `${fmtWhen(P.at)}${P.model ? ` · ${/opus-5-5/.test(P.model) ? "Opus 5.5" : P.model}` : ""}${lldMoney(P.costUsd)}`));
    if (typeof tplAgentOpen === "function") top.append(hBtn("★ 계획 열기", () => tplAgentOpen(P.tpl), { cls: "btn sm lld-open", title: "템플릿 서식 정리 열 — 서식마다 고르기를 바꾸고 적용" }));
    row.append(top);
    if (P.summary) row.append(el("p", "lld-why", P.summary));
    const ul = el("ul", "lld-sum");
    for (const L of P.levels || []) {
      const parts = [];
      if (L.single) parts.push(L.repChanged ? "서식 1가지 — 대표 정함" : "서식 1가지 — 그대로"); // 대표만 정하는 레벨도 반영한다(맞출 줄 0 · 대표 변경 1 — spec_hwpx_웹편집 ② §8-4)
      else {
        if (L.repChanged) parts.push("대표 바꿈");
        if (L.match) parts.push(`맞출 줄 ${nf(L.match)}`);
        for (const sp of L.split || []) parts.push(`T${P.no}L${L.level}${sp.sfx} 로 뗄 줄 ${nf(sp.lines)}`);
        if (L.keep) parts.push(`사람에게 남긴 줄 ${nf(L.keep)}`);
        if (!parts.length) parts.push("바꿀 줄 없음");
      }
      const li = el("li", L.change || L.moved || L.repChanged ? "chg" : null, `L${L.level} 「${short(L.letter || "", 6)}」 ${nf(L.lines)}줄 — ${parts.join(" · ")}`);
      if (L.why) li.title = L.why;
      ul.append(li);
    }
    row.append(ul);
    if (P.applied && P.state === "applied") row.append(el("p", "lld-why", `${fmtWhen(P.applied.at)} 에 반영 — 줄 ${nf(P.applied.changed)}개`));
    else if (P.applied) row.append(el("p", "lld-why warn", `${fmtWhen(P.applied.at)} 에 반영했다가(줄 ${nf(P.applied.changed)}개) 되돌렸습니다(실행 취소 · 모두 되돌리기) — 지금 문서에는 반영돼 있지 않습니다${P.state === "planned" ? " · 계획은 그대로 다시 쓸 수 있습니다(다시 받지 않습니다)" : ""}`)); // 반영함은 문서에 남아 있을 때만(spec_hwpx_웹편집 ② §8-4)
    if (P.state === "stale") row.append(el("p", "lld-why warn", `계획을 받은 뒤 이 템플릿의 줄이 바뀌었거나(서식 · 줄 구성) 못 본 서식이 남아 계획대로 맞출 수 없습니다 — 「★ 계획 열기」 에서 다시 받으세요(템플릿 줄의 단추는 그동안 대표와 다른 줄을 모두 맞춥니다)`));
    if (P.state === "planned") todo += (P.change || 0) + (P.moved || 0);
    s.body.append(row);
  }
  return { ...s, n: todo, badge: todo ? `${nf(todo)}줄` : nf(plans.length), tip: `서식 계획 ${nf(plans.length)}개 · 반영 안 한 줄 ${nf(todo)}` };
}
