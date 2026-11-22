"use strict";
// 양식의 표 등록부(spec_테이블매니저 ② §11 「표 · 띠 정체」) — 「테이블」 탭의 표 목록 위 등록부 줄 + 표마다 「양식 표」 꼬리표.
// 사용자 2026-11-22 "표띠, 아이디는 이미 테이블이 소속한 헤딩이 있기 때문에 그걸로 자동으로 둘 수 있다고 봅니다, 사람이 판정하진 않습니다 LLM 이 판정하고 사람은 지침만 제공합니다." ·
// "양식의 테이블은 레지스트리에 구분기준자리나. 기타 테이블 타입/병합 정보, 서브테이블을 저장하고 관리해서 향후 사용할 수 있게해줘".
// 등록부 줄: 양식 이름 · 표 수 · 서브 테이블 수 · 지은 때 · 판정(LLM | 스크립트) · 이 문서의 표가 몇 개 이어졌나 — 「등록부 보기」(표 목록 위에 펼침 — 팝업 아님) · 빈 양식 문서면 「이 빈 양식으로 짓기 / 다시 짓기」.
// 사람은 등록부를 고치지 않는다(판정은 3단계 결과의 것 — 빈 양식에서 LLM 표 판정을 돌린 뒤 지으면 LLM 판정이 든다). 지침은 「보기·도구」 의 「양식 정보」(「## 표」 절)에 적는다.
// app.js 가 주는 것: state·el·api·toast·hBtn·nf·fmtWhen·H_JSON·flushAll. tables.js: TP_KIND·xlStageKey(있으면). panel_help.js: hHelp. 전역 이름은 ft…·FT_… 만 쓴다.
// 서버 짝: app/form_tables_api.py(`GET /api/docs/{id}/form-tables` · `POST …/form-tables/build` · `GET/DELETE /api/forms/{key}/tables`) · 짓기 · 잇기 app/form_tables.py.
// index.html 이 table_types.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const FT_HOW = { path: "소속 헤딩 · 차례", type: "소속 헤딩 · 표 타입", typeOnly: "표 타입만(소속 헤딩이 등록부에 없음)", ambiguous: "후보 여럿", unknown: "양식에 없는 표" };
const FT_DIM = { org: "기관", stage: "단계", year: "차년도", stageYear: "단계-차년도", sub: "세부과제", period: "연도" };
const FT_ENGINE = { rows: "행", cols: "열", list: "목록 행", section: "절" };
const FT_BAND = { matrix: "격자", form: "키-값", list: "목록", title: "제목", note: "안내", spacer: "간격", plain: "머리 없음" };
const ft = { key: null, v: null, wait: null, open: false, reg: null, busy: false }; // v = 이 문서의 잇기 응답 · reg = 펼친 등록부(항목 전부)
const ftKey = () => `${state.id}|${state.epoch}|${typeof xlStageKey === "function" ? xlStageKey() : ""}`;

function ftReset() { ft.key = ft.v = ft.wait = ft.reg = null; ft.open = false; ft.busy = false; } // 문서를 열거나 닫을 때(tables.js tablesReset)
function ftLoad(force = false) { // 탭을 열 때(force) · 지은 뒤(force) → Promise. 읽지 못해도 알리지 않는다(줄 · 꼬리표가 안 보일 뿐)
  if (!state.id || state.format === "docx") return Promise.resolve(null);
  const key = ftKey();
  if (ft.wait === key || (!force && ft.key === key)) return Promise.resolve(ft.v);
  ft.wait = key;
  return api(`/api/docs/${encodeURIComponent(state.id)}/form-tables`).catch(() => null).then((v) => {
    if (ft.wait === key) ft.wait = null;
    if (key !== ftKey()) return null; // 그 사이 다른 문서를 열었다
    ft.key = key;
    ft.v = v;
    ftFill();
    return v;
  });
}

const ftDims = (xs) => (xs || []).map((d) => FT_DIM[d] || d).join(" · ");
function ftDivisionText(dv) { // 구분 기준 자리 한 줄 — 「소속 [기관] · 표 안 구분 칸 차년도 · 엔진: 기관 절 · 차년도 열」
  if (!dv) return "";
  const out = [];
  if ((dv.owner || []).length) out.push(`소속 구분 라벨 ${ftDims(dv.owner)}${dv.ownerText ? `(${dv.ownerText})` : ""}`);
  if ((dv.labels || []).length) out.push(`표 안 구분 칸 ${ftDims(dv.labels)}`);
  if ((dv.engine || []).length) out.push(`엔진이 늘리는 자리 ${dv.engine.map((p) => `${FT_DIM[p.dim] || p.dim} ${FT_ENGINE[p.kind] || p.kind}`).join(" · ")}`);
  return out.join(" / ");
}
function ftKindText(k) { return (typeof TP_KIND === "object" && TP_KIND[k]) || (k === "mixed" ? "섞임" : k || "–"); }
function ftEntryTitle(e, link) { // 꼬리표 · 등록부 줄의 풍선 도움말
  const lines = [`양식 표 「${e.name}」${e.title ? ` — ${e.title}` : ""}`, `소속: ${(e.path || []).join(" › ") || "–"}`];
  if (link) lines.push(`잇는 근거: ${FT_HOW[link.how] || link.how}${link.sure ? "" : " — 확실하지 않음(LLM 이 확인할 자리)"}${link.occ > 1 ? ` · 같은 자리의 ${link.occ}번째` : ""}`);
  lines.push(`병합 방식: ${ftKindText(e.kind)}${e.repeat > 1 ? ` · 빈 양식에서 ${e.repeat}번 되풀이` : ""}`);
  const dv = ftDivisionText(e.division);
  if (dv) lines.push(`구분 기준 자리: ${dv}`);
  for (const b of e.subs || []) lines.push(`서브 테이블 ${b.at}: ${FT_BAND[b.kind] || b.kind || "–"} · ${ftKindText(b.merge)}${(b.heads || []).length ? ` · 머리글 ${b.heads.slice(0, 3).join(" · ")}` : ""}`);
  return lines.join("\n");
}

function ftTags(tid) { // 표 하나의 꼬리표 — 등록부가 있는 문서에서만
  const v = ft.v && ft.key === ftKey() ? ft.v : null;
  if (!v || !v.registry || !v.links) return [];
  const link = v.links[tid];
  if (!link) return [];
  const entries = v.entries || {};
  let tag;
  if (link.id && entries[link.id]) {
    tag = el("span", "tp-tag ft-tag", `양식 표${link.sure ? "" : "?"}`);
    tag.title = ftEntryTitle(entries[link.id], link);
  } else if (link.how === "ambiguous") {
    tag = el("span", "tp-tag ft-tag is-warning", `양식 표 후보 ${nf(link.cands.length)}`);
    tag.title = `이 표가 양식의 어느 표인지 스크립트로 하나로 정하지 못했습니다 — 후보:\n${link.cands.map((i) => (entries[i] ? `· ${entries[i].name} (${(entries[i].path || []).join(" › ")})` : `· ${i}`)).join("\n")}`;
  } else {
    tag = el("span", "tp-tag ft-tag", "양식에 없는 표");
    tag.title = "양식의 표 등록부에 이 표와 맞는 표가 없습니다(작성자가 더한 표이거나 소속 헤딩이 달라진 표)";
  }
  tag.dataset.how = link.how;
  return [tag];
}

async function ftBuild() {
  if (ft.busy || !state.id) return;
  const v = ft.v, id0 = state.id;
  ft.busy = true;
  ftFill();
  try {
    if (typeof flushAll === "function") await flushAll();
    const r = await api(`/api/docs/${encodeURIComponent(id0)}/form-tables/build`, { method: "POST", headers: H_JSON, body: "{}" });
    if (id0 !== state.id) return;
    toast(`양식 「${r.form.name}」 의 표 등록부를 지었습니다 — 표 ${nf(r.summary.counts.tables)} · 서브 테이블 ${nf(r.summary.counts.subs)}`);
    ft.reg = null;
    await ftLoad(true);
    if (ft.open) await ftOpenList(true);
  } catch (e) {
    toast(`등록부를 짓지 못했습니다: ${(e && e.message) || e}`, true);
  } finally {
    ft.busy = false;
    ftFill();
  }
  return v;
}

async function ftOpenList(reload = false) { // 「등록부 보기」 — 항목 전부를 읽어 표 목록 위에 펼친다
  const v = ft.v;
  if (!v || !v.form) return;
  ft.open = true;
  if (!ft.reg || reload) {
    try { ft.reg = await api(`/api/forms/${encodeURIComponent(v.form.key)}/tables`); } catch (e) { ft.reg = null; toast(`등록부를 읽지 못했습니다: ${(e && e.message) || e}`, true); ft.open = false; }
  }
  ftFill();
}

function ftList() { // 펼친 등록부 — 항목마다 이름 · 소속 · 타입 · 병합 방식 · 구분 기준 자리 · 서브 테이블
  const reg = ft.reg, box = el("ol", "ft-list");
  box.setAttribute("aria-label", "양식의 표 등록부");
  const hit = new Map();
  for (const [tid, l] of Object.entries((ft.v && ft.v.links) || {})) if (l.id && !hit.has(l.id)) hit.set(l.id, tid);
  for (const e of (reg && reg.tables) || []) {
    const li = el("li", "ft-item"), head = el("div", "ft-item-head");
    head.append(el("strong", "ft-name", e.name), el("span", "tp-size", `${e.rows}×${e.cols}`));
    if (e.title) head.append(el("span", "ft-title", e.title));
    const mine = hit.get(e.id);
    head.append(el("span", `tp-tag${mine ? "" : " is-warning"}`, mine ? `이 문서 ${mine}` : "이 문서에 없음"));
    li.append(head, el("div", "ft-path", (e.path || []).join(" › ") || "–"));
    const meta = el("div", "tp-row-meta");
    meta.append(el("span", "tp-tag tp-kind", ftKindText(e.kind)));
    if (e.repeat > 1) meta.append(el("span", "tp-tag", `되풀이 ${nf(e.repeat)}`));
    if (e.host) meta.append(el("span", "tp-tag", "표 안 표"));
    const dv = ftDivisionText(e.division);
    if (dv) meta.append(el("span", "tp-tag", `구분 ${dv}`));
    if (e.type) { const t = el("span", "tp-detail", `타입 ${e.type.slice(0, 6)}`); t.title = `표 타입(머리글 지문) ${e.type}`; meta.append(t); }
    li.append(meta);
    if ((e.subs || []).length > 1 || (e.subs || []).some((b) => b.merge && b.merge !== e.kind)) {
      const subs = el("ul", "ft-subs");
      for (const b of e.subs) subs.append(el("li", null, `${b.at} ${FT_BAND[b.kind] || b.kind || "–"} · ${ftKindText(b.merge)}${(b.heads || []).length ? ` · ${b.heads.slice(0, 3).join(" · ")}` : ""}`));
      li.append(subs);
    }
    li.title = ftEntryTitle(e);
    box.append(li);
  }
  return box;
}

function ftBar() { // 표 목록 위 등록부 줄(양식이 정해진 문서에서만) — 없으면 null
  const v = ft.v && ft.key === ftKey() ? ft.v : null;
  if (!v || !v.form) return null;
  const bar = el("section", "ft-bar");
  bar.id = "ftBar";
  bar.setAttribute("aria-label", "양식의 표 등록부");
  const line = el("div", "tp-actions");
  line.append(el("span", "tp-meta-label", "양식의 표 등록부"), el("strong", null, v.form.name));
  const r = v.registry;
  if (!r) {
    line.append(el("span", "tp-state", v.missing === "broken" ? "등록부 파일을 읽지 못했습니다" : "아직 없습니다"));
  } else {
    const c = r.counts || {}, src = r.source || {};
    line.append(el("span", "tp-state", `표 ${nf(c.tables)} · 서브 테이블 ${nf(c.subs)} · ${src.llm ? "LLM 판정" : "스크립트 판정"} · ${fmtWhen(r.at)}`));
    const links = Object.values(v.links || {}), got = links.filter((l) => l.id).length;
    if (links.length) {
      const n = el("span", `tp-state${got < links.length ? " is-warning" : ""}`, `이 문서: 이은 표 ${nf(got)}/${nf(links.length)}`);
      const by = {};
      for (const l of links) by[l.how] = (by[l.how] || 0) + 1;
      n.title = Object.entries(by).map(([k, x]) => `${FT_HOW[k] || k} ${nf(x)}`).join("\n") + ((v.missing_entries || []).length ? `\n이 문서에 없는 양식 표 ${nf(v.missing_entries.length)}` : "");
      line.append(n);
    } else if (v.missing === "stage3") line.append(el("span", "tp-state", "이 문서는 표 구조가 아직 없습니다"));
    if (v.stale) line.append(el("span", "analysis-state stale", "표 구조가 문서보다 오래됨"));
    line.append(hBtn(ft.open ? "등록부 접기" : "등록부 보기", () => { if (ft.open) { ft.open = false; ftFill(); } else ftOpenList(); }));
  }
  if (v.blank) line.append(hBtn(r ? "이 빈 양식으로 다시 짓기" : "이 빈 양식으로 짓기", () => ftBuild(), { disabled: ft.busy, cls: r ? "btn sm" : "btn sm primary" }));
  if (typeof hHelp === "function")
    line.append(hHelp("양식의 표 등록부", "양식의 표마다 이름 · 소속 헤딩 · 표 타입 · 병합 방식 · 구분 기준 자리 · 서브 테이블을 저장해 두고, 같은 양식의 다른 문서가 표마다 「양식 표」 로 잇습니다.\n"
      + "표 · 서브 테이블 id 는 소속 헤딩과 차례로 저절로 정해집니다. 판정은 등록된 빈 양식의 표 구조 결과의 것입니다(빈 양식에서 LLM 표 판정을 돌린 뒤 지으면 LLM 판정이 듭니다).\n"
      + "사람은 등록부를 고치지 않고 지침만 적습니다 — 「보기·도구」 › 「양식 정보」 의 「## 표」 절.\n「양식 표?」 = 소속 헤딩은 맞는데 표 타입이 다르거나 타입으로만 이은 표입니다.", { note: true }));
  bar.append(line);
  if (r && ft.open && ft.reg) bar.append(ftList());
  return bar;
}

function ftFill() { // 그려 둔 표 목록의 등록부 줄 · 꼬리표 자리만 다시 채운다(목록을 통째로 다시 그리지 않는다)
  const old = document.getElementById("ftBar");
  const bar = ftBar();
  if (old) { if (bar) old.replaceWith(bar); else old.remove(); } else if (bar) {
    const list = document.querySelector("#tablesBox .tp-list");
    if (list) list.before(bar);
  }
  for (const slot of document.querySelectorAll("#tablesBox .tp-row .tp-forms")) {
    const row = slot.closest(".tp-row");
    slot.replaceChildren(...ftTags(row && row.dataset.tableId));
  }
}
