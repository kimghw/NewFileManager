"use strict";
// 양식 지침 YAML — 화면(spec_양식작성 ② §5-8 · design.md §32). 서버 = app/form_guide_yaml_api.py(끝점) · app/form_guide_yaml.py(꼴 · 자리 잇기 · 후보 · 올리기).
// 2026-11-26 사용자 "연차보고서, 사업계획서등 양식이 있는 문서들은 yaml 로 본문이랑 테이블 작성지침을 관리 … 서브 테이블 별로 … 작성예시나, 샘플등을 주고 향후 LLM이 작성할때 이 부분을 참조".
//   · 2열(kind "formGuide") 「양식 지침」: 이 문서의 양식 · 지침 파일의 수 · **이 작업의 후보**(내가 적은 지침 · 표 지침 · 04 작성 지침 보완의 규칙 — 고른 것만 「양식 지침에 올리기」) ·
//     주요 항목(구성 맞추기가 값을 읽는 곳) · 이어지지 않은 항목 · 「YAML 보기 · 고치기」. 저절로 쓰지 않는다(astra · Fable 합의 — 사람이 고른 것만).
//   · 「작성 지침 — 이 줄에 닿는 것」 열(place_guides.js pgLayersEl)의 절 · 상자 · 표 층마다 「예시 더하기」 — 그 자리(표면 서브 테이블도 고름)에 작성 예시를 적는다(fgyExampleEl).
// app.js 가 주는 것: state · heads · $ · el · api · toast · hBtn · headsDlg · headsColClose · short · nf · H_JSON · PEEK (+ place_guides.js pgSoon · panel_help.js hHelp — typeof 검사 뒤).
// index.html 이 place_guides.js 다음에 읽는다.

const FGY = { view: null };
const FGY_ORIGIN = { user: "사람", llm: "04 LLM" };
const FGY_OUTPUT = { stages: "단계", orgs: "기관", period: "사업기간", current: "당해 차년도", subs: "세부", "": "문서 항목" };
const FGY_KIND = { section: "절", table: "표", subtable: "서브 테이블", field: "칸" };
const fgyOk = () => !PEEK && !!state.id && state.format === "hwpx";
const fgyUrl = (tail = "") => `/api/docs/${encodeURIComponent(state.id)}/form-guide${tail}`;

async function fgyOpen() {
  if (!fgyOk()) return;
  if (typeof pgColOpen === "function" && pgColOpen() && typeof pgDirty === "function" && pgDirty() && !confirm("저장하지 않은 지침 글이 있습니다. 버릴까요?")) return;
  const { body } = headsDlg("formGuide", "양식 지침", "읽는 중…");
  body.append(el("div", "lk-cap", "읽는 중…"));
  const seq = heads.seq, id = state.id;
  let v;
  try { v = await api(fgyUrl()); }
  catch (e) { if (seq === heads.seq) { body.textContent = ""; body.append(el("div", "lk-cap", `양식 지침을 읽지 못했습니다: ${e.message}`)); } return; }
  if (seq !== heads.seq || id !== state.id) return;
  fgyRender(v);
}

function fgyAfter(v, msg) { // 쓴 뒤 — 열을 새 답으로 · 쪽 여백의 지침 단추도 다시 읽게
  if (heads.dlg === "formGuide" && !$("headsDlg").hidden) fgyRender(v); else FGY.view = v;
  if (typeof pgSoon === "function") pgSoon(0);
  if (msg) toast(msg);
}

function fgyRender(v) {
  FGY.view = v;
  const tools = $("headsDlgTools"), body = $("headsDlgBody"), foot = $("headsDlgFoot");
  for (const x of [tools, body, foot]) x.textContent = "";
  const note = $("headsDlgNote");
  note.textContent = v.form ? `${v.form.name} — forms/${v.form.key}.guide.yaml` : "이 문서에 맞는 양식이 없음";
  if (typeof hHelp === "function") $("headsDlgHelp").replaceChildren(hHelp("양식 지침이란",
    "같은 양식의 문서(연차보고서 · 연구개발계획서 …)마다 다시 쓰려고 양식에 저장해 두는 작성 지침입니다 — 본문 절 · 그 절의 표 · 표의 서브 테이블(띠) · 칸마다, 작성 예시와 주요 항목(구성 맞추기가 값을 읽는 곳)도 함께. " +
    "이관(자리 연결 · 표 대응 · 빈 자리 검토)과 양식 작성(검토 · 계획 · 초안)이 그 자리의 지침으로 함께 읽습니다(「양식 지침」 꼬리표). 예시는 초안을 쓸 때만 꼴 · 문체 · 분량의 참고로 실립니다(이름 · 수치는 옮기지 않음). " +
    "문서에 이미 있는 작성요령은 여기 옮기지 않습니다(문서마다 다시 읽음). 이 작업에서 적은 지침과 04 의 규칙은 저절로 올라가지 않고, 아래 후보에서 고른 것만 올립니다. 문서는 바뀌지 않습니다."));
  foot.append(hBtn("닫기", () => headsColClose(), { cls: "btn sm" }));
  const wrap = el("div", "pg-col fgy-col");
  body.append(wrap);
  if (!v.form) { wrap.append(el("p", "hnote", v.why || "이 문서에 맞는 양식이 없습니다.")); return; }
  const c = v.counts || {};
  tools.append(...fgyMoreBtns(), el("span", "muted fgy-total", `절 ${nf(c.sections || 0)} · 표 ${nf(c.tables || 0)} · 서브 테이블 ${nf(c.subtables || 0)} · 지침 ${nf(c.guides || 0)} · 예시 ${nf(c.examples || 0)}${c.docGuides ? ` · 일반 가이드라인 ${nf(c.docGuides)}` : ""}`));
  wrap.append(el("p", "hnote fgy-here", v.exists ? `이 문서에 이어진 것 — 헤딩 ${nf(c.headsHere || 0)}곳 · 표 ${nf(c.tablesHere || 0)}개` : "아직 양식 지침 파일이 없습니다 — 아래 후보를 올리거나 YAML 을 적으면 생깁니다."));
  if (!v.writable) wrap.append(el("p", "hnote fgy-warn", v.why || "이 문서에서는 양식 지침에 쓸 수 없습니다."));
  wrap.append(fgyCandsEl(v));
  if ((v.keywords || []).length) {
    const sec = el("section", "pg-sec fgy-sec");
    sec.append(el("h3", "pg-h", `주요 항목 ${nf(v.keywords.length)}`));
    const ul = el("ul", "pg-list fgy-list");
    for (const k of v.keywords) {
      const li = el("li", "fgy-item");
      li.append(el("span", "hb fgy-tag", FGY_OUTPUT[k.output] ?? k.output), el("span", "fgy-text", k.name), el("span", "muted fgy-where", k.at.length ? `문서에 ${nf(k.at.length)}곳` : "문서에서 못 찾음"));
      ul.append(li);
    }
    sec.append(ul);
    wrap.append(sec);
  }
  if ((v.unmatched || []).length) {
    const d = el("details", "fgy-sec fgy-lost");
    d.append(el("summary", "", `이 문서에 이어지지 않은 항목 ${nf(v.unmatched.length)}`));
    const ul = el("ul", "pg-list fgy-list");
    for (const u of v.unmatched) {
      const li = el("li", "fgy-item");
      li.append(el("span", "hb fgy-tag", FGY_KIND[u.kind] || u.kind), el("span", "fgy-text", short(u.what || u.id, 70)), el("span", "muted fgy-where", u.why));
      li.title = `${u.id} — ${u.what}\n${u.why}`;
      ul.append(li);
    }
    d.append(ul);
    wrap.append(d);
  }
  const ysec = el("section", "pg-sec fgy-sec fgy-yaml-sec");
  if (v.writable) ysec.append(hBtn("뼈대 채우기", async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try { const r = await api(fgyUrl("/skeleton"), { method: "POST", headers: H_JSON, body: JSON.stringify({ sha1: v.sha1 }) }); fgyAfter(r, r.added ? `구조 ${nf(r.added)}개를 깔았습니다(본문 절 → 표 → 서브 테이블)` : "더할 구조가 없습니다"); }
    catch (err) { toast(`뼈대를 깔지 못했습니다: ${err.message}`, true); b.disabled = false; }
  }, { cls: "btn sm", title: "이 문서의 본문 절 → 그 절의 표 → 표의 서브 테이블을 양식 지침 YAML 에 깝니다(없는 항목만 · 지침 없이) — 지침 · 예시를 적을 자리를 한눈에 봅니다" }));
  ysec.append(hBtn("YAML 보기 · 고치기", () => fgyYaml(v.form.key, ysec), { cls: "btn sm", title: `forms/${v.form.key}.guide.yaml 의 글 — 고쳐 저장하면 검사 뒤 저장합니다(지우기 · 순서 · 주요 항목은 여기서)` }));
  wrap.append(ysec);
}

function fgyCandsEl(v) {
  const sec = el("section", "pg-sec fgy-sec fgy-cands");
  const cands = v.candidates || [];
  const open = cands.filter((x) => !x.saved);
  const head = el("div", "pg-sec-head");
  head.append(el("h3", "pg-h", `이 작업의 후보 ${nf(open.length)}`));
  if (cands.length > open.length) head.append(el("span", "pg-sec-tag", `올린 것 ${nf(cands.length - open.length)}`));
  sec.append(head);
  if (!cands.length) { sec.append(el("p", "hnote pg-empty", "올릴 것이 없습니다 — 「지침」 열에서 내가 적은 지침 · 표 지침, 양식 작성 04 「LLM 검증·보완」 의 작성 지침이 후보가 됩니다.")); return sec; }
  const ul = el("ul", "pg-list fgy-list");
  const picked = new Set();
  const go = hBtn("고른 것 양식 지침에 올리기", () => fgyPromote([...picked], go), { cls: "btn sm primary", disabled: true, title: "고른 지침을 양식 지침 파일에 더합니다(같은 글은 건너뜀 · 다른 과제의 같은 양식 문서에서도 읽힙니다)" });
  const sync = () => { go.disabled = !picked.size || !v.writable; go.textContent = picked.size ? `고른 것 양식 지침에 올리기 (${nf(picked.size)})` : "고른 것 양식 지침에 올리기"; };
  for (const x of cands) {
    const li = el("li", "fgy-item fgy-cand" + (x.saved ? " is-saved" : "") + (x.warn.length ? " has-warn" : ""));
    const cb = el("input");
    cb.type = "checkbox";
    cb.disabled = x.saved || !v.writable || !!x.blocked; // blocked = 이 문서의 줄 id 가 든 글(다른 문서에서는 다른 줄 — 고친 뒤 올린다)
    cb.onchange = () => { cb.checked ? picked.add(x.key) : picked.delete(x.key); sync(); };
    const lab = el("label", "fgy-cand-row");
    lab.append(cb, el("span", "hb fgy-tag", FGY_ORIGIN[x.origin] || x.origin), el("span", "fgy-where", short(x.where, 60)));
    li.append(lab, el("div", "fgy-text", short(x.text, 220)));
    if (x.saved) li.append(el("div", "muted fgy-note", "양식 지침에 이미 있음"));
    if (x.blocked) li.append(el("div", "fgy-warnline", `올릴 수 없음 — ${x.blocked}`));
    if (x.warn.length) li.append(el("div", "fgy-warnline", `과제마다 다를 수 있는 것 — ${x.warn.join(" · ")} (다른 과제에도 읽힙니다)`));
    li.title = x.text;
    ul.append(li);
  }
  const tl = el("div", "fgy-tools");
  tl.append(go);
  sec.append(ul, tl);
  return sec;
}

async function fgyPromote(keys, btn) {
  const v = FGY.view;
  if (!keys.length || !v) return;
  const warn = (v.candidates || []).filter((x) => keys.includes(x.key) && x.warn.length).length;
  if (warn && !confirm(`고른 것 가운데 ${warn}개에 기관 이름 · 수가 있습니다 — 같은 양식의 다른 과제 문서에서도 읽힙니다. 그래도 올릴까요?`)) return;
  btn.disabled = true;
  try {
    const r = await api(fgyUrl("/promote"), { method: "POST", headers: H_JSON, body: JSON.stringify({ keys, sha1: v.sha1 }) });
    fgyAfter(r, `양식 지침에 ${nf(r.added)}개 올렸습니다${r.skipped ? ` (같은 글 ${nf(r.skipped)}개 건너뜀)` : ""}`);
  } catch (e) {
    toast(e.status === 409 ? `${e.message}` : `올리지 못했습니다: ${e.message}`, true);
    if (e.status === 409) fgyOpen(); else btn.disabled = false;
  }
}

// ---- 규정(forms/<양식>.rules.yaml) · 문서 목적(프로젝트의 purpose.yaml) — spec_양식작성 ② §5-9 · 서버 app/form_rules_api.py · app/purpose_yaml_api.py -----------------------------------
// 2026-11-26 사용자 "rules.yaml 을 선호 … 문서 목적은 purpose.yaml … 결국에는 사람이 지침을 확인하고 관리하기 편하도록". 둘 다 2열 보기(kind formRules · formPurpose): 수 · 항목 · 못 이은 항목 · YAML 고치기.
function fgyMoreBtns(ok = () => true) { // 「지침」 열 · 「양식 지침」 열의 도구 줄에 서는 단추 둘
  if (!fgyOk()) return [];
  return [hBtn("규정", () => { if (ok()) fgyRulesOpen(); }, { cls: "btn sm pg-tbtn fgy-rules-btn", title: "다른 규칙(관리 규정 · 지침서 · 법령)이 이 양식에 요구하는 것(forms/<양식>.rules.yaml) — 보기 · 고치기" }),
          hBtn("문서 목적", () => { if (ok()) fgyPurposeOpen(); }, { cls: "btn sm pg-tbtn fgy-purpose-btn", title: "이 프로젝트의 공고 · 목적 · 평가 관점 · 요구 사항과 그때 목적에 맞게 반영하는 지침(프로젝트마다 purpose.yaml) — 보기 · 고치기" })];
}

function fgyLostEl(list) { // 이 문서에 이어지지 않은 항목(규정 · 문서 목적의 targets)
  const d = el("details", "fgy-sec fgy-lost");
  d.append(el("summary", "", `이 문서에 이어지지 않은 자리 ${nf(list.length)}`));
  const ul = el("ul", "pg-list fgy-list");
  for (const u of list) {
    const li = el("li", "fgy-item");
    li.append(el("span", "hb fgy-tag", FGY_KIND[u.kind] || u.kind), el("span", "fgy-text", short(u.what || u.id, 70)), el("span", "muted fgy-where", `${u.id} — ${u.why}`));
    ul.append(li);
  }
  d.append(ul);
  return d;
}

async function fgyColOpen(kind, title, url) { // 2열을 열고 읽는다 → {v, tools, wrap, foot} | null
  if (!fgyOk()) return null;
  const { body } = headsDlg(kind, title, "읽는 중…");
  body.append(el("div", "lk-cap", "읽는 중…"));
  const seq = heads.seq, id = state.id;
  let v;
  try { v = await api(url); }
  catch (e) { if (seq === heads.seq) { body.textContent = ""; body.append(el("div", "lk-cap", `${title}을(를) 읽지 못했습니다: ${e.message}`)); } return null; }
  if (seq !== heads.seq || id !== state.id) return null;
  const tools = $("headsDlgTools"), foot = $("headsDlgFoot");
  for (const x of [tools, body, foot]) x.textContent = "";
  foot.append(hBtn("닫기", () => headsColClose(), { cls: "btn sm" }));
  const wrap = el("div", "pg-col fgy-col");
  body.append(wrap);
  return { v, tools, wrap };
}

async function fgyRulesOpen() {
  const got = await fgyColOpen("formRules", "규정", `/api/docs/${encodeURIComponent(state.id)}/form-rules`);
  if (!got) return;
  const { v, tools, wrap } = got;
  $("headsDlgNote").textContent = v.form ? `${v.form.name} — forms/${v.form.key}.rules.yaml` : "이 문서에 맞는 양식이 없음";
  if (typeof hHelp === "function") $("headsDlgHelp").replaceChildren(hHelp("규정이란",
    "다른 규칙(관리 규정 · 지침서 · 법령)이 이 양식에 요구하는 것을 양식마다 적어 두는 파일입니다 — 항목마다 요구하는 것 · 출처(규정 이름 · 조항 · 시행일) · 필수인지 권고인지 · 적용 조건 · 닿는 자리(절 · 표 · 서브 테이블 · 칸). " +
    "자리를 적지 않은 항목은 문서 전체에 닿습니다. 이관과 양식 작성의 LLM 이 그 자리의 작성 지침으로 함께 읽고(「규정」 꼬리표), 필수 항목은 분량이 넘쳐도 가장 늦게 빠집니다. " +
    "사람이 적습니다 — LLM 은 이 파일에 쓰지 않고, 04 「LLM 검증·보완」 도 참조로만 읽습니다. 과제마다 다른 것(공고 · RFP)은 「문서 목적」 에 적습니다. 문서는 바뀌지 않습니다."));
  if (!v.form) { wrap.append(el("p", "hnote", v.why || "이 문서에 맞는 양식이 없습니다.")); return; }
  const c = v.counts || {};
  tools.append(el("span", "muted fgy-total", `항목 ${nf(c.rules || 0)} · 필수 ${nf(c.required || 0)} · 문서 전체 ${nf(c.whole || 0)} · 자리에 이어진 항목 ${nf(c.linked || 0)}`));
  if (v.why) wrap.append(el("p", "hnote fgy-warn", `규정 파일을 읽을 수 없습니다 — 아래에서 고치세요: ${v.why}`));
  else if (!v.exists) wrap.append(el("p", "hnote fgy-here", "아직 규정 파일이 없습니다 — 아래 「YAML 보기 · 고치기」 로 적으면 생깁니다."));
  if ((v.rules || []).length) {
    const sec = el("section", "pg-sec fgy-sec fgy-rules");
    sec.append(el("h3", "pg-h", `규정 항목 ${nf(v.rules.length)}`));
    const ul = el("ul", "pg-list fgy-list");
    for (const r of v.rules) {
      const li = el("li", "fgy-item fgy-rule" + (r.whole || r.linked ? "" : " has-warn"));
      const row = el("div", "fgy-cand-row");
      row.append(el("span", "hb fgy-tag", r.required ? "필수" : "권고"), el("span", "fgy-where", [r.source, r.applies ? `적용: ${r.applies}` : ""].filter(Boolean).join(" · ") || r.id),
        el("span", "muted fgy-where", r.whole ? "문서 전체" : r.linked ? `이 문서의 ${nf(r.linked)}곳` : "이 문서에 이어지지 않음"));
      li.append(row, el("div", "fgy-text", short(r.text, 260)));
      li.title = `${r.id}\n${r.text}`;
      ul.append(li);
    }
    sec.append(ul);
    wrap.append(sec);
  }
  if ((v.unmatched || []).length) wrap.append(fgyLostEl(v.unmatched));
  const ysec = el("section", "pg-sec fgy-sec fgy-yaml-sec");
  const url = `/api/form-rules/${encodeURIComponent(v.form.key)}/yaml`;
  ysec.append(hBtn("YAML 보기 · 고치기", () => fgyYaml(v.form.key, ysec, { url, reopen: fgyRulesOpen, said: (r) => `저장했습니다 — 규정 ${nf(r.rules)}개` }),
    { cls: "btn sm", title: `forms/${v.form.key}.rules.yaml 의 글 — 고쳐 저장하면 검사 뒤 저장합니다(고치기 전 글은 이력에 남습니다)` }));
  wrap.append(ysec);
}

async function fgyPurposeOpen() {
  const url = `/api/docs/${encodeURIComponent(state.id)}/purpose`;
  const got = await fgyColOpen("formPurpose", "문서 목적", url);
  if (!got) return;
  const { v, tools, wrap } = got;
  $("headsDlgNote").textContent = v.project ? `프로젝트 「${v.project}」 — purpose.yaml` : "이 작업에 프로젝트가 없음";
  if (typeof hHelp === "function") $("headsDlgHelp").replaceChildren(hHelp("문서 목적이란",
    "공고 · RFP 처럼 과제(프로젝트)마다 다른 것을 프로젝트마다 적어 두는 파일입니다 — 공고(이름 · 기관 · 날짜) · 이 문서를 왜 쓰나 · 평가 관점 · 공고가 요구하는 것 · 이 프로젝트에서 그때 목적에 맞게 반영하는 지침. " +
    "같은 프로젝트의 문서들이 함께 읽습니다(「문서 목적」 꼬리표 — 문서 전체에 닿는 것은 LLM 호출에 한 번만). 어느 과제에나 맞는 일반 가이드라인은 「양식 지침」 에, 다른 규정이 요구하는 것은 「규정」 에 적습니다. " +
    "사람이 적습니다 — LLM 은 이 파일에 쓰지 않습니다. 문서는 바뀌지 않습니다."));
  if (!v.project) { wrap.append(el("p", "hnote", v.why || "이 작업에 프로젝트가 없습니다.")); return; }
  const c = v.counts || {};
  tools.append(el("span", "muted fgy-total", `목적 ${c.purpose ? "있음" : "없음"} · 평가 관점 ${nf(c.evaluation || 0)} · 요구 사항 ${nf(c.requirements || 0)} · 프로젝트 지침 ${nf(c.guides || 0)}(자리에 이어진 것 ${nf(c.linked || 0)})`));
  if (v.why) wrap.append(el("p", "hnote fgy-warn", `문서 목적 파일을 읽을 수 없습니다 — 아래에서 고치세요: ${v.why}`));
  else if (!v.exists) wrap.append(el("p", "hnote fgy-here", "아직 이 프로젝트의 문서 목적이 없습니다 — 아래 글을 채워 저장하면 생깁니다."));
  if ((v.unmatched || []).length) wrap.append(fgyLostEl(v.unmatched));
  const ysec = el("section", "pg-sec fgy-sec fgy-yaml-sec");
  wrap.append(ysec);
  fgyYamlEdit(ysec, { text: v.text, sha1: v.sha1 }, { url, reopen: fgyPurposeOpen, said: () => "문서 목적을 저장했습니다", close: () => headsColClose() });
}

async function fgyYaml(key, host, opt = {}) {
  const url = opt.url || `/api/form-guides/${encodeURIComponent(key)}/yaml`;
  let y;
  try { y = await api(url); } catch (e) { return toast(e.message || String(e), true); }
  fgyYamlEdit(host, y, { url, ...opt });
}

function fgyYamlEdit(host, y, opt = {}) { // YAML 글 칸 + 저장(검사 뒤 · 판이 다르면 409) — 양식 지침 · 규정 · 문서 목적이 같이 쓴다
  const url = opt.url, reopen = opt.reopen || fgyOpen;
  host.textContent = "";
  const ta = el("textarea", "fgy-yaml");
  ta.value = y.text;
  ta.rows = 18;
  ta.spellcheck = false;
  let sha = y.sha1;
  const row = el("div", "fgy-tools");
  const save = hBtn("저장", async () => {
    save.disabled = true;
    try {
      const r = await api(url, { method: "PUT", headers: H_JSON, body: JSON.stringify({ text: ta.value, sha1: sha }) });
      sha = r.sha1;
      toast(opt.said ? opt.said(r) : `저장했습니다 — 절 ${nf(r.sections)} · 주요 항목 ${nf(r.keywords)}`);
      reopen();
      if (typeof pgSoon === "function") pgSoon(0);
    } catch (e) { toast(e.status === 409 ? `${e.message}` : `저장하지 못했습니다: ${e.message}`, true); save.disabled = false; }
  }, { cls: "btn sm primary", title: "검사(꼴 · id 겹침) 뒤 저장 — 고치기 전 글은 이력에 남습니다" });
  row.append(save, hBtn("닫기", () => (opt.close || reopen)(), { cls: "btn sm" }));
  host.append(ta, row);
  if (!opt.close) ta.focus();
}

// 「작성 지침 — 이 줄에 닿는 것」 열의 절 · 상자 · 표 층에서 — 그 자리에 작성 예시 하나(서브 테이블이 있는 표면 띠를 고른다)
function fgyExampleEl(at, kind) {
  const box = el("div", "fgy-ex");
  const ta = el("textarea", "fgy-ex-ta");
  ta.rows = 4;
  ta.placeholder = "이 자리에 쓰는 글의 예(꼴 · 문체 · 분량의 참고 — 기관 이름 · 수치는 자리표시로 바꿔 적으면 좋습니다)";
  const noteIn = el("input", "fgy-ex-note");
  noteIn.placeholder = "메모(선택 — 무엇을 보라는 예시인지)";
  const sel = el("select", "fgy-ex-band");
  sel.append(new Option(kind === "head" ? "이 절" : "표 전체", ""));
  sel.hidden = true;
  const bands = (FGY.view && FGY.view.bands && FGY.view.bands[at]) || null;
  const fill = (list) => { for (const b of list || []) sel.append(new Option(`서브 테이블 「${short(b.head, 30)}」(행 ${b.rows[0] + 1}–${b.rows[1]})`, b.id)); sel.hidden = !(list || []).length; };
  if (kind !== "head") {
    if (bands) fill(bands);
    else api(fgyUrl()).then((v) => { FGY.view = v; fill((v.bands || {})[at]); }).catch(() => {});
  }
  const row = el("div", "fgy-tools");
  const save = hBtn("양식 지침에 예시 저장", async () => {
    if (!ta.value.trim()) return toast("예시 글을 적으세요", true);
    save.disabled = true;
    try {
      const r = await api(fgyUrl("/example"), { method: "POST", headers: H_JSON, body: JSON.stringify({ place: at, band: sel.value || null, text: ta.value, note: noteIn.value }) });
      box.remove();
      fgyAfter(r, "작성 예시를 양식 지침에 저장했습니다" + (r.warn && r.warn.length ? ` — 과제마다 다를 수 있는 것: ${r.warn.join(" · ")}` : ""));
    } catch (e) { toast(`저장하지 못했습니다: ${e.message}`, true); save.disabled = false; }
  }, { cls: "btn sm primary", title: "같은 양식의 문서에서 이 자리의 초안을 쓸 때 참고로 실립니다" });
  row.append(save, hBtn("취소", () => box.remove(), { cls: "btn sm" }));
  box.append(sel, ta, noteIn, row);
  setTimeout(() => ta.focus(), 0);
  return box;
}
