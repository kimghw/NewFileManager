"use strict";
// 지침 설정 페이지 /guides (spec_양식작성 ② §5-10 · 서버 app/guides_page_api.py) — 2026-11-26 사용자 "설정페이지를 두고.. 이 내용들을 확인할 수 있도록 해줘, 지침들을 판단지침이나... 템플릿/양식 별로로" ·
// "결국에는 사람이 지침을 확인하고 관리하기 편하도록". 보기 둘: 「판단 지침」(LLM 이 따르는 기준 글 — 글마다 읽는 에이전트 · 쓰이는 워크플로우 › 단계 · 기본본 ↔ 고친 본) ·
// 「양식별」(양식마다 양식 정보 · 양식 지침의 나무 · 규정 · 테마 · 그 양식을 쓰는 프로젝트의 문서 목적 — 「보기 · 고치기」 는 검사 뒤 저장 · 판이 다르면 409).
// **새 저장 길이 없다** — 목록은 GET /api/guides-page/judgment · forms(읽기만), 고치기는 글마다 이미 있는 끝점(서버가 item.save · reset 에 주소를 적어 준다 · 양식 쪽은 아래 YAML_OF).
// app.js 를 읽지 않는다(혼자 선다) — account/chip.js 가 먼저 실려 fetch 를 감싼다(로그인이 풀리면 /login 으로).
const $ = (id) => document.getElementById(id);
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
const nf = (n) => Number(n || 0).toLocaleString("ko-KR");
const short = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const H_JSON = { "Content-Type": "application/json" };
async function api(url, opt) {
  const r = await fetch(url, opt);
  let data = null;
  try { data = await r.json(); } catch (e) { /* 몸통 없음 */ }
  if (!r.ok) { const err = new Error((data && (typeof data.detail === "string" ? data.detail : data.message)) || `요청 실패(${r.status})`); err.status = r.status; throw err; }
  return data;
}
let toastT = 0;
function toast(msg, bad) { const t = $("gpToast"); t.textContent = msg; t.classList.toggle("err", !!bad); t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, bad ? 7000 : 3200); }
function btn(text, on, opt = {}) { const b = el("button", opt.cls || "btn sm", text); b.type = "button"; if (opt.title) b.title = opt.title; b.onclick = on; return b; }
function link(href, text, cls) { const a = el("a", cls || "gp-link", text); a.href = href; return a; }
const NOTE_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h5"/></svg>';
function help(title, text) { // 제목 옆 노트 아이콘 — 설명 문단은 그 뒤에 둔다(누르면 펴진다)
  const wrap = el("span", "gp-help"), b = el("button", "gp-help-btn"), pop = el("span", "gp-help-pop", text);
  b.type = "button"; b.innerHTML = NOTE_SVG; b.title = title; b.setAttribute("aria-label", title); b.setAttribute("aria-expanded", "false");
  pop.hidden = true;
  b.onclick = () => { pop.hidden = !pop.hidden; b.setAttribute("aria-expanded", String(!pop.hidden)); };
  wrap.append(b, pop);
  return wrap;
}
function sec(title, helpTitle, helpText) { const s = el("section", "ags-sec gp-sec"), h = el("h3", "ags-h", title); if (helpText) h.append(help(helpTitle || title, helpText)); s.append(h); return s; }
function tag(text, cls) { return el("span", "gp-tag" + (cls ? " " + cls : ""), text); }

const GP = { tab: "judgment", sel: "", judgment: null, forms: null };
function parseHash() { const m = /^#(judgment|forms)(?:\/(.*))?$/.exec(location.hash); return m ? { tab: m[1], sel: decodeURIComponent(m[2] || "") } : { tab: "judgment", sel: "" }; }
const hashOf = (tab, sel) => `#${tab}${sel ? "/" + encodeURIComponent(sel) : ""}`;
function dirty() { const ta = document.querySelector("#gpMain textarea[data-dirty='1']"); return !!ta; }
async function render(force) {
  const { tab, sel } = parseHash();
  GP.tab = tab; GP.sel = sel;
  for (const b of document.querySelectorAll(".gp-tab")) { const on = b.dataset.tab === tab; b.classList.toggle("is-on", on); b.setAttribute("aria-selected", String(on)); }
  const nav = $("gpNav"), main = $("gpMain");
  if (force) GP[tab] = null;
  if (!GP[tab]) {
    try { GP[tab] = await api(`/api/guides-page/${tab}`); }
    catch (e) { nav.textContent = ""; main.replaceChildren(el("p", "ags-note", `지침을 읽지 못했습니다: ${e.message}`)); return; }
  }
  if (GP.tab !== tab || GP.sel !== sel) return;
  main.scrollTop = 0;
  if (tab === "judgment") drawJudgment(GP.judgment, sel); else drawForms(GP.forms, sel);
}
window.addEventListener("hashchange", () => render());
window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });
$("gpNav").addEventListener("click", (e) => { if (e.target.closest("a") && dirty() && !confirm("저장하지 않은 글이 있습니다. 버릴까요?")) e.preventDefault(); }); // 목차로 옮기기 전에 — 쓰던 글을 말없이 버리지 않는다
for (const b of document.querySelectorAll(".gp-tab")) b.onclick = () => { if (!dirty() || confirm("저장하지 않은 글이 있습니다. 버릴까요?")) location.hash = hashOf(b.dataset.tab, ""); };

function navDraw(tab, groups, sel) { // groups = [{name, items[{id, text, mark?}]}]
  const nav = $("gpNav");
  nav.textContent = "";
  const all = link(hashOf(tab, ""), "전체 보기");
  if (!sel) all.setAttribute("aria-current", "true");
  nav.append(all);
  for (const g of groups) {
    if (!g.items.length) continue;
    nav.append(el("h2", "", g.name));
    for (const it of g.items) {
      const a = link(hashOf(tab, it.id), "");
      a.append(el("span", "gp-nav-name", it.text));
      if (it.mark) a.append(tag(it.mark, "is-mine"));
      if (it.id === sel) a.setAttribute("aria-current", "true");
      nav.append(a);
    }
  }
}

// ---- 「판단 지침」 -----------------------------------------------------------------------------------------------
const KIND_NAME = { merge: "판단 지침", heading: "헤딩 지침", skill: "서식 정리 스킬", theme: "양식 테마" };
const JUDGE_HELP = "LLM 이 판단하거나 지침을 만들 때 따르는 기준 글입니다 —답의 꼴(계약)은 코드에 있고, 무엇을 어떻게 볼지는 이 글이 정합니다. 고치면 이 PC 의 사본으로 저장되어 다음 LLM 실행부터 쓰이고, 「기본으로 되돌리기」 로 저장소의 기본본으로 돌아갑니다. " +
  "글마다 어느 에이전트(작업 번호 · 이름)가 읽는지와 그 에이전트가 어느 워크플로우의 어느 단계에서 도는지를 함께 보입니다.";
function drawJudgment(data, sel) {
  const items = data.items || [];
  $("gpNote").textContent = `글 ${nf(items.length)}개 · 고친 것 ${nf(items.filter((x) => x.custom).length)}개`;
  navDraw("judgment", (data.groups || []).map((g) => ({ name: g.name, items: items.filter((x) => x.kind === g.key).map((x) => ({ id: x.id, text: x.title, mark: x.custom ? "고침" : "" })) })), sel);
  const main = $("gpMain");
  main.textContent = "";
  const it = items.find((x) => x.id === sel);
  if (it) return drawItem(main, it);
  const h = el("h2", "gp-title", "판단 지침");
  h.append(help("판단 지침이란", JUDGE_HELP));
  main.append(h);
  for (const g of data.groups || []) {
    const mine = items.filter((x) => x.kind === g.key);
    if (!mine.length) continue;
    const s = sec(`${g.name} ${nf(mine.length)}`);
    const tb = el("table", "gp-table");
    const tr0 = el("tr");
    for (const t of ["글", "읽는 에이전트", "쓰이는 워크플로우", "상태"]) tr0.append(el("th", "", t));
    tb.append(tr0);
    for (const x of mine) {
      const tr = el("tr"), jobs = [...new Set(x.readers.flatMap((r) => r.used.map((u) => u.name)))];
      const td = el("td");
      td.append(link(hashOf("judgment", x.id), x.title), el("div", "gp-sub", x.source));
      tr.append(td, el("td", "", x.readers.map((r) => `${r.no} ${r.name}`).join(" · ") || "—"), el("td", "", jobs.join(" · ") || "—"));
      const st = el("td");
      st.append(tag(x.custom ? "고친 본" : "기본본", x.custom ? "is-mine" : ""));
      tr.append(st);
      tb.append(tr);
    }
    s.append(tb);
    main.append(s);
  }
}
function drawItem(main, it) {
  const h = el("h2", "gp-title", it.title);
  h.append(tag(it.custom ? "고친 본 · 내 사본" : "기본본", it.custom ? "is-mine" : ""), help("판단 지침이란", JUDGE_HELP));
  main.append(h, el("p", "ags-note gp-meta", `${KIND_NAME[it.kind] || it.kind} · ${it.source}${it.kind === "merge" || it.kind === "heading" ? "" : it.lang === "yaml" ? " · YAML" : ""}`));
  const who = sec(`읽는 에이전트 ${nf(it.readers.length)}`, "읽는 에이전트 · 쓰이는 곳", "이 글을 프롬프트에 싣는 에이전트(에이전트 설정의 작업 번호 · 이름)와, 그 에이전트가 도는 워크플로우 › 단계 묶음 › 단계입니다. 이름을 누르면 에이전트 설정 · 워크플로우 페이지의 그 자리로 갑니다.");
  if (!it.readers.length) who.append(el("p", "ags-note", "이 글을 읽는 에이전트가 등록부에 없습니다."));
  for (const r of it.readers) {
    const row = el("div", "gp-reader");
    const a = link(`/agents#${encodeURIComponent(r.id)}`, `${r.no} ${r.name}`, "gp-link gp-agent");
    a.title = "에이전트 설정에서 이 에이전트 보기 — 역할 · 모델 · 프롬프트의 차례";
    row.append(a);
    const ul = el("ul", "gp-used");
    for (const u of r.used) { const li = el("li"); li.append(link(`/workflow#${encodeURIComponent(u.job)}`, u.name), ` › ${u.stage} › ${u.stepName}`); ul.append(li); }
    if (!r.used.length) ul.append(el("li", "gp-sub", "워크플로우의 단계 줄에 묶이지 않은 에이전트입니다(문서 화면의 단추로 부릅니다)."));
    row.append(ul);
    who.append(row);
  }
  main.append(who);
  const body = sec("글", "글 고치기", "「고치기」 로 글을 고쳐 저장하면 이 PC 의 사본이 되고 다음 LLM 실행부터 쓰입니다(그 사이 다른 화면에서 바뀌었으면 저장하지 않고 알립니다). 「기본본과 견주기」 는 기본본에서 빠진 줄(−)과 고친 본에 더한 줄(+)을 보입니다.");
  const tools = el("div", "gp-tools"), host = el("div", "gp-host");
  const show = () => { host.replaceChildren(Object.assign(el("pre", "gp-text"), { textContent: it.text })); };
  const edit = () => {
    const ta = el("textarea", "gp-ta");
    ta.value = it.text; ta.rows = 24; ta.spellcheck = false;
    ta.oninput = () => { ta.dataset.dirty = ta.value !== it.text ? "1" : ""; };
    const save = btn("저장", async () => {
      save.disabled = true;
      const b = { text: ta.value };
      if (it.save.version) b.version = it.version;
      if (it.save.name) b.name = it.save.name;
      try { await api(it.save.url, { method: "PUT", headers: H_JSON, body: JSON.stringify(b) }); toast("저장했습니다 — 다음 LLM 실행부터 이 글을 씁니다"); render(true); }
      catch (e) { toast(e.status === 409 ? `${e.message}` : `저장하지 못했습니다: ${e.message}`, true); save.disabled = false; }
    }, { cls: "btn sm primary" });
    const row = el("div", "gp-tools");
    row.append(save, btn("취소", () => show()));
    host.replaceChildren(ta, row);
    ta.focus();
  };
  if (it.save) tools.append(btn("고치기", edit, { title: "이 글을 고쳐 이 PC 의 사본으로 저장합니다" }));
  else tools.append(el("span", "gp-sub", "이 글을 읽는 에이전트가 없어 여기서 고칠 수 없습니다(파일을 직접 고칩니다)."));
  if (it.custom && it.default != null) tools.append(btn("기본본과 견주기", () => host.replaceChildren(diffEl(it.default, it.text)), { title: "기본본 → 고친 본 — 빠진 줄(−)과 더한 줄(+)" }), btn("지금 글 보기", show));
  if (it.reset && it.custom) tools.append(btn("기본으로 되돌리기", async () => {
    if (!confirm(`「${it.title}」 의 고친 글을 버리고 기본본으로 되돌립니다. 계속할까요?`)) return;
    try { await api(it.reset.url + (it.reset.version ? `?version=${encodeURIComponent(it.version)}` : ""), { method: "DELETE" }); toast("기본본으로 되돌렸습니다"); render(true); }
    catch (e) { toast(`되돌리지 못했습니다: ${e.message}`, true); }
  }, { cls: "btn sm danger" }));
  body.append(tools, host);
  show();
  main.append(body);
}
function diffLines(a, b) { // 줄 단위 LCS → [[" " | "-" | "+", 줄]] | null(너무 큼)
  const A = a.split("\n"), B = b.split("\n"), n = A.length, m = B.length;
  if (n * m > 4000000) return null;
  const L = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) { if (A[i] === B[j]) { out.push([" ", A[i]]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) out.push(["-", A[i++]]); else out.push(["+", B[j++]]); }
  while (i < n) out.push(["-", A[i++]]);
  while (j < m) out.push(["+", B[j++]]);
  return out;
}
function diffEl(base, mine) {
  const box = el("div", "gp-diff"), rows = diffLines(base.trim(), mine.trim());
  if (!rows) { box.append(el("p", "ags-note", "글이 너무 길어 줄마다 견주지 못했습니다.")); return box; }
  const minus = rows.filter((r) => r[0] === "-").length, plus = rows.filter((r) => r[0] === "+").length;
  box.append(el("p", "ags-note gp-diff-cap", `기본본 → 고친 본: 기본본에만 있는 줄(−) ${nf(minus)} · 고친 본에 더한 줄(+) ${nf(plus)}${minus + plus ? "" : " — 글이 같습니다(빈칸 · 줄 끝만 다름)"}`));
  const keep = new Set();
  rows.forEach((r, k) => { if (r[0] !== " ") for (let d = -2; d <= 2; d++) keep.add(k + d); });
  const pre = el("pre", "gp-text gp-difftext");
  let gap = false;
  rows.forEach((r, k) => {
    if (!keep.has(k)) { gap = true; return; }
    if (gap) { pre.append(el("span", "gp-dl is-gap", "  ⋯\n")); gap = false; }
    pre.append(el("span", "gp-dl" + (r[0] === "-" ? " is-del" : r[0] === "+" ? " is-add" : ""), `${r[0]} ${r[1]}\n`));
  });
  box.append(pre);
  return box;
}

// ---- 「양식별」 --------------------------------------------------------------------------------------------------
const FORMS_HELP = "양식(연차보고서 · 연구개발계획서 …)마다 그 양식에 붙은 지침을 한 묶음으로 보입니다 — 양식 정보(양식을 알아보는 조건 · 자리 연결), 양식 지침(본문 절 › 표 › 서브 테이블 › 칸마다의 작성 지침 · 예시 · 일반 가이드라인), " +
  "규정(다른 규칙이 이 양식에 요구하는 것), 테마(테이블 타입 · 구분 기준 타입), 그 양식을 쓰는 프로젝트의 문서 목적(공고 · 평가 관점). 이관과 양식 작성의 LLM 이 같은 조립으로 읽습니다. 파일마다 「보기 · 고치기」 로 글을 고쳐 저장합니다(검사 뒤 저장 · 고치기 전 글은 이력).";
const YAML_OF = { // 파일마다 읽고 쓰는 끝점(앞에서 만든 것 그대로)
  md: (key) => ({ get: `/api/headings/forms/${encodeURIComponent(key)}`, put: `/api/headings/forms/${encodeURIComponent(key)}`, body: (text, sha1) => ({ text, sha1, reason: "지침 설정 페이지" }) }),
  guide: (key) => ({ get: `/api/form-guides/${encodeURIComponent(key)}/yaml`, put: `/api/form-guides/${encodeURIComponent(key)}/yaml`, body: (text, sha1) => ({ text, sha1 }) }),
  rules: (key) => ({ get: `/api/form-rules/${encodeURIComponent(key)}/yaml`, put: `/api/form-rules/${encodeURIComponent(key)}/yaml`, body: (text, sha1) => ({ text, sha1 }) }),
  purpose: (project) => ({ get: `/api/purpose/yaml?project=${encodeURIComponent(project)}`, put: "/api/purpose/yaml", body: (text, sha1) => ({ project, text, sha1 }) }),
};
function editBtn(host, label, ep, what) { // 「보기 · 고치기」 — 글 칸 + 저장(판이 다르면 409)
  return btn(label, async (e) => {
    const b = e.currentTarget;
    if (host.firstChild) { if (!dirty() || confirm("저장하지 않은 글이 있습니다. 버릴까요?")) host.textContent = ""; return; }
    b.disabled = true;
    let y;
    try { y = await api(ep.get); } catch (err) { toast(`${what}을(를) 읽지 못했습니다: ${err.message}`, true); b.disabled = false; return; }
    b.disabled = false;
    const ta = el("textarea", "gp-ta");
    ta.value = y.text || ""; ta.rows = 20; ta.spellcheck = false;
    ta.oninput = () => { ta.dataset.dirty = ta.value !== (y.text || "") ? "1" : ""; };
    const save = btn("저장", async () => {
      save.disabled = true;
      try { await api(ep.put, { method: "PUT", headers: H_JSON, body: JSON.stringify(ep.body(ta.value, y.sha1 || "")) }); toast(`${what}을(를) 저장했습니다`); render(true); }
      catch (err) { toast(err.status === 409 ? `${err.message}` : `저장하지 못했습니다: ${err.message}`, true); save.disabled = false; }
    }, { cls: "btn sm primary", title: "검사(꼴 · id 겹침) 뒤 저장 — 고치기 전 글은 이력에 남습니다" });
    const row = el("div", "gp-tools");
    row.append(save, btn("닫기", () => { if (!ta.dataset.dirty || confirm("저장하지 않은 글이 있습니다. 버릴까요?")) host.textContent = ""; }));
    host.replaceChildren(ta, row);
  }, { title: `${what}의 글을 봅니다 — 고쳐 저장하면 검사 뒤 저장합니다` });
}
function guideList(list, cls) { // 지침 · 예시 줄들
  const ul = el("ul", "gp-list" + (cls ? " " + cls : ""));
  for (const g of list || []) {
    const li = el("li");
    if (g.origin && g.origin !== "user") li.append(tag(g.origin === "llm" ? "04 LLM" : g.origin));
    li.append(short(g.text, 400));
    if (g.note) li.append(el("span", "gp-sub", ` — ${g.note}`));
    li.title = g.text;
    ul.append(li);
  }
  return ul;
}
const cnt = (g, e) => [g ? `지침 ${nf(g)}` : "", e ? `예시 ${nf(e)}` : ""].filter(Boolean).join(" · ");
function nodeEl(kind, title, node, inner) { // 절 · 표 · 서브 테이블 한 층(접고 펴기 — 지침 · 예시가 있으면 펴 둔다)
  const d = el("details", `gp-node gp-node-${kind}`), sum = el("summary");
  const g = (node.guides || []).length, e = (node.examples || []).length, f = (node.fields || []).filter((x) => (x.guides || []).length);
  sum.append(tag({ section: "절", table: "표", sub: "서브 테이블" }[kind]), el("span", "gp-node-name", title));
  const c = cnt(g, e);
  if (c) sum.append(el("span", "gp-sub gp-node-cnt", c));
  d.append(sum);
  if (g) d.append(guideList(node.guides));
  if (e) { d.append(el("div", "gp-sub gp-ex-cap", "작성 예시(꼴 · 문체 · 분량의 참고)")); d.append(guideList(node.examples, "is-ex")); }
  for (const x of f) { const row = el("div", "gp-field"); row.append(tag("칸"), el("span", "gp-node-name", x.label)); d.append(row, guideList(x.guides)); }
  for (const x of inner || []) d.append(x);
  if (g || e || f.length) d.open = true;
  return d;
}
function has(node) { return (node.guides || []).length + (node.examples || []).length + (node.fields || []).filter((x) => (x.guides || []).length).length; }
function guideTree(doc, all) { // 절 › 표 › 서브 테이블 › 칸 — all 이 아니면 지침 · 예시가 있는 가지만
  const box = el("div", "gp-tree");
  let shown = 0;
  for (const s of doc.sections || []) {
    const tabs = [];
    for (const t of s.tables || []) {
      const subs = (t.subtables || []).filter((b) => all || has(b)).map((b) => nodeEl("sub", b.head, b));
      if (all || has(t) || subs.length) tabs.push(nodeEl("table", t.head, t, subs));
    }
    if (!all && !has(s) && !tabs.length) continue;
    shown++;
    box.append(nodeEl("section", s.path.join(" › "), s, tabs));
  }
  if (!shown) box.append(el("p", "ags-note", all ? "절이 없습니다 — 문서 화면의 「양식 지침」 열에서 「뼈대 채우기」 로 구조를 깝니다." : "지침 · 예시가 적힌 자리가 아직 없습니다."));
  return box;
}
function countsOf(doc) {
  const c = { sections: 0, tables: 0, subs: 0, guides: (doc.guides || []).length, examples: 0, places: 0 };
  const add = (n) => { const g = (n.guides || []).length + (n.fields || []).reduce((a, f) => a + (f.guides || []).length, 0), e = (n.examples || []).length; c.guides += g; c.examples += e; if (g || e) c.places++; };
  for (const s of doc.sections || []) { c.sections++; add(s); for (const t of s.tables || []) { c.tables++; add(t); for (const b of t.subtables || []) { c.subs++; add(b); } } }
  return c;
}
function purposeRow(p) {
  const row = el("div", "gp-project"), host = el("div", "gp-host"), q = p.purpose;
  const head = el("div", "gp-tools");
  head.append(el("b", "gp-node-name", p.name), el("span", "gp-sub", `작업 ${nf(p.works)}개`),
    tag(q.exists ? "문서 목적 있음" : "문서 목적 없음", q.exists ? "is-mine" : ""),
    el("span", "gp-sub", q.exists ? `목적 ${q.purpose ? "있음" : "없음"} · 평가 관점 ${nf(q.evaluation)} · 요구 사항 ${nf(q.requirements)} · 프로젝트 지침 ${nf(q.guides)}` : ""),
    editBtn(host, q.exists ? "YAML 보기 · 고치기" : "문서 목적 적기", YAML_OF.purpose(p.name), `프로젝트 「${p.name}」 의 문서 목적`));
  row.append(head, host);
  return row;
}
function drawForms(data, sel) {
  const forms = data.forms || [], loose = data.loose || [];
  $("gpNote").textContent = `양식 ${nf(forms.length)}개`;
  navDraw("forms", [{ name: "양식", items: forms.map((f) => ({ id: f.key, text: f.name, mark: f.rules.exists || (f.guide.doc && countsOf(f.guide.doc).places) ? "지침" : "" })) },
    { name: "그 밖", items: loose.length ? [{ id: "_loose", text: `양식에 묶이지 않은 프로젝트 ${loose.length}` }] : [] }], sel);
  const main = $("gpMain");
  main.textContent = "";
  if (sel === "_loose" && loose.length) {
    const h = el("h2", "gp-title", "양식에 묶이지 않은 프로젝트");
    h.append(help("양식에 묶이지 않은 프로젝트", "문서가 아직 없거나, 문서가 어느 양식에도 맞지 않은(파일 이름 · 사람이 고른 양식이 없는) 프로젝트입니다. 문서 목적은 프로젝트의 것이라 여기서도 보고 고칩니다."));
    const s = sec(`프로젝트의 문서 목적 ${nf(loose.length)}`);
    for (const p of loose) s.append(purposeRow(p));
    main.append(h, s);
    return;
  }
  const f = forms.find((x) => x.key === sel);
  if (f) return drawForm(main, f);
  const h = el("h2", "gp-title", "양식별 지침");
  h.append(help("양식별 지침이란", FORMS_HELP));
  main.append(h);
  if (!forms.length) main.append(el("p", "ags-note", "등록된 양식 정보가 없습니다 — 문서 화면의 헤딩 추출 「양식」 에서 양식 정보를 만듭니다."));
  const tb = el("table", "gp-table");
  const tr0 = el("tr");
  for (const t of ["양식", "양식 지침", "규정", "테마", "프로젝트"]) tr0.append(el("th", "", t));
  tb.append(tr0);
  for (const x of forms) {
    const c = x.guide.doc ? countsOf(x.guide.doc) : null, rs = (x.rules.doc && x.rules.doc.rules) || [];
    const tr = el("tr"), td = el("td");
    td.append(link(hashOf("forms", x.key), x.name), el("div", "gp-sub", `forms/${x.key}.md`));
    tr.append(td, el("td", "", x.guide.broken ? "읽을 수 없음" : c && x.guide.exists ? `절 ${nf(c.sections)} · 표 ${nf(c.tables)} · 지침 ${nf(c.guides)} · 예시 ${nf(c.examples)}` : "없음"),
      el("td", "", x.rules.broken ? "읽을 수 없음" : rs.length ? `${nf(rs.length)}개(필수 ${nf(rs.filter((r) => r.required).length)})` : "없음"), el("td", "", x.theme ? x.theme.name : "—"),
      el("td", "", x.projects.length ? x.projects.map((p) => p.name).join(" · ") : "—"));
    tb.append(tr);
  }
  if (forms.length) main.append(tb);
}
function drawForm(main, f) {
  const h = el("h2", "gp-title", f.name);
  h.append(help("양식별 지침이란", FORMS_HELP));
  main.append(h, el("p", "ags-note gp-meta", `양식 키 ${f.key}${f.broken ? ` · 양식 정보를 읽을 수 없음: ${f.broken}` : ""}`));
  // ① 양식 정보(md)
  const s1 = sec("양식 정보", "양식 정보", "이 양식을 알아보는 조건(파일 이름 · 올린 원본의 지문)과 자리 연결 · 구분 기준 같은 양식마다의 설정을 적은 글입니다(forms/<키>.md). 헤딩 · 표 판정과 이관의 LLM 이 「양식 정보」 로 함께 읽습니다.");
  const h1 = el("div", "gp-host"), t1 = el("div", "gp-tools");
  t1.append(el("span", "gp-sub", `forms/${f.key}.md · ${nf(f.md.size)}자`), editBtn(h1, "보기 · 고치기", YAML_OF.md(f.key), "양식 정보"));
  s1.append(t1, h1);
  // ② 양식 지침(guide.yaml)
  const s2 = sec("양식 지침", "양식 지침", "같은 양식의 문서마다 다시 쓰려고 저장해 둔 작성 지침입니다(forms/<키>.guide.yaml) — 본문 절 › 그 절의 표 › 표의 서브 테이블 › 칸마다. 맨 위 「일반 가이드라인」 은 문서 전체에 닿습니다(어느 과제에나 맞는 것). " +
    "자리는 헤딩 경로와 머리글로 문서에 이어집니다. 이 작업에서 적은 지침을 골라 올리는 것은 문서 화면의 「양식 지침」 열에서 합니다.");
  const h2 = el("div", "gp-host"), t2 = el("div", "gp-tools");
  const doc = f.guide.doc;
  if (f.guide.broken) s2.append(el("p", "ags-note gp-bad", `파일을 읽을 수 없습니다 — 아래에서 고치세요: ${f.guide.broken}`));
  if (doc) {
    const c = countsOf(doc);
    t2.append(el("span", "gp-sub", f.guide.exists ? `forms/${f.key}.guide.yaml · 절 ${nf(c.sections)} · 표 ${nf(c.tables)} · 서브 테이블 ${nf(c.subs)} · 지침 ${nf(c.guides)} · 예시 ${nf(c.examples)} · 주요 항목 ${nf((doc.keywords || []).length)}` : "아직 파일이 없습니다"));
  }
  t2.append(editBtn(h2, "YAML 보기 · 고치기", YAML_OF.guide(f.key), "양식 지침"));
  s2.append(t2, h2);
  if (doc) {
    if ((doc.guides || []).length) { s2.append(el("h4", "gp-h4", `일반 가이드라인 ${nf(doc.guides.length)} — 문서 전체`)); s2.append(guideList(doc.guides)); }
    const treeHost = el("div"), cap = el("div", "gp-tools");
    let all = false;
    const draw = () => { treeHost.replaceChildren(guideTree(doc, all)); tog.textContent = all ? "지침이 있는 자리만" : "모든 자리 보기"; };
    const tog = btn("", () => { all = !all; draw(); }, { title: "지침 · 예시가 없는 절 · 표까지 양식의 구조를 모두 보입니다" });
    cap.append(el("h4", "gp-h4", "자리마다 — 절 › 표 › 서브 테이블 › 칸"), tog);
    s2.append(cap, treeHost);
    draw();
    if ((doc.keywords || []).length) {
      s2.append(el("h4", "gp-h4", `주요 항목 ${nf(doc.keywords.length)} — 구성 맞추기가 값을 읽는 곳`));
      const ul = el("ul", "gp-list");
      for (const k of doc.keywords) { const li = el("li"); li.append(tag(k.output || "문서 항목"), `${k.name}${(k.labels || []).length ? ` — 라벨: ${k.labels.join(" · ")}` : ""}`); ul.append(li); }
      s2.append(ul);
    }
  }
  // ③ 규정(rules.yaml)
  const s3 = sec("규정", "규정", "다른 규칙(관리 규정 · 지침서 · 법령)이 이 양식에 요구하는 것입니다(forms/<키>.rules.yaml) — 항목마다 출처 · 필수|권고 · 적용 조건 · 닿는 자리. 자리를 적지 않은 항목은 문서 전체에 닿습니다. 사람만 적습니다(LLM 은 참조로만 읽습니다).");
  const h3 = el("div", "gp-host"), t3 = el("div", "gp-tools"), rules = (f.rules.doc && f.rules.doc.rules) || [];
  if (f.rules.broken) s3.append(el("p", "ags-note gp-bad", `파일을 읽을 수 없습니다 — 아래에서 고치세요: ${f.rules.broken}`));
  t3.append(el("span", "gp-sub", f.rules.exists ? `forms/${f.key}.rules.yaml · 항목 ${nf(rules.length)} · 필수 ${nf(rules.filter((r) => r.required).length)} · 문서 전체 ${nf(rules.filter((r) => !(r.targets || []).length).length)}` : "아직 파일이 없습니다"),
    editBtn(h3, f.rules.exists ? "YAML 보기 · 고치기" : "규정 적기", YAML_OF.rules(f.key), "규정"));
  s3.append(t3, h3);
  if (rules.length) {
    const ul = el("ul", "gp-list gp-rules");
    for (const r of rules) {
      const li = el("li"), src = r.source || {};
      li.append(tag(r.required ? "필수" : "권고", r.required ? "is-req" : ""), short(r.text, 400));
      const where = (r.targets || []).length ? r.targets.map((t) => [t.path.join(" › "), t.table && `표 「${short(t.table, 30)}」`, t.subtable && `서브 테이블 「${short(t.subtable, 30)}」`, t.field && `칸 「${t.field}」`].filter(Boolean).join(" › ")).join(" / ") : "문서 전체";
      li.append(el("div", "gp-sub", [[src.name, src.clause].filter(Boolean).join(" ") + (src.date ? ` (${src.date})` : ""), r.applies && `적용: ${r.applies}`, `닿는 자리: ${where}`].filter(Boolean).join(" · ")));
      li.title = `${r.id}\n${r.text}`;
      ul.append(li);
    }
    s3.append(ul);
  }
  // ④ 테마
  const s4 = sec("테마", "테마", "이 양식 문서의 종류(테마 — 양식 지침의 theme)입니다. 테마 YAML 이 테이블 타입 · 구분 기준 타입 · 개요 템플릿의 작성 방법을 지닙니다 — 「판단 지침」 보기의 「양식 테마」 에서 보고 고칩니다.");
  s4.append(f.theme ? link(hashOf("judgment", `theme:${f.theme.id}`), `${f.theme.name} (${f.theme.id})`) : el("span", "gp-sub", "양식 지침에 theme 이 적혀 있지 않습니다."));
  // ⑤ 프로젝트의 문서 목적
  const s5 = sec(`프로젝트의 문서 목적 ${nf(f.projects.length)}`, "문서 목적", "공고 · RFP 처럼 과제(프로젝트)마다 다른 것 — 공고 · 이 문서를 왜 쓰나 · 평가 관점 · 요구 사항 · 그 프로젝트에서 그때 목적에 맞게 반영하는 지침. 프로젝트마다 파일 하나이고, 이 양식의 문서를 가진 프로젝트를 보입니다.");
  if (!f.projects.length) s5.append(el("p", "ags-note", "이 양식의 문서를 가진 프로젝트가 없습니다."));
  for (const p of f.projects) s5.append(purposeRow(p));
  for (const [s, id] of [[s1, "gpFormMd"], [s2, "gpFormGuide"], [s3, "gpFormRules"], [s4, "gpFormTheme"], [s5, "gpFormPurpose"]]) s.id = id; // 절의 자리(화면 검사 · 주소가 가리킨다)
  main.append(s1, s2, s3, s4, s5);
}

render();
