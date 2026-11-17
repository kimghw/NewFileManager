/* 넘친 개요 레벨(spec_병합 ② §5-5 9 — 2026-11-13 사용자 「덮은 템플릿으로 사용할지 템플릿을 수정할지, 다른 템플릿을 선택할 수 있게」).
   2열 「넣기 계획」(이관 fillList · 취합 gatherFillList · 끌어 넣기 gatherDropList) 안의 한 절 — 모달 없음(design.md §2). 넣는 내용의 개요가 자리 템플릿보다 깊은 곳을 사례마다 한 줄로 보이고
   처리 셋(덮은 템플릿 그대로 · 템플릿 수정 · 다른 템플릿)을 고르게 한다. 고르면 PUT /api/docs/{목적}/merge-over → 부른 쪽이 계획을 다시 세워 목록을 다시 그린다(opt.onChange).
   넣은 줄의 기록이 있으면 「넣은 줄에 다시 맞추기」(POST …/merge-over/refit — 편집 하나 · 실행 취소 1).
   서버가 주는 것(계획 응답의 over): { version, cases[{ key, to{template, no, chain, level}, tail, levels[{ n, key, was, lines, applied, letter, like{template, level, letter, text}|null, lead, clash, missing }],
     lines(넣을 줄), applied(넣은 줄), places, at(첫 자리), mode, template, under[그 자리 아래 붙은 템플릿] }], templates[{ anchor, no, kind, chain, levels[{ level, key, letter, text, ok }] }], records{ lines, cases } }.
   app.js 의 el · hBtn · hHelp · api · toast · nf · H_JSON 을 쓴다(이 파일은 그 뒤에 읽는다). 글·PUT 바디를 만드는 함수(mergeOverCaseText · mergeOverLevelText · mergeOverDraft · mergeOverBody)는 화면 없이도 돈다(tests/test_merge_over.py). */
const MERGE_OVER_MODE = { cover: "덮은 템플릿 그대로", edit: "템플릿 수정", template: "다른 템플릿" };
const MERGE_OVER_HELP = "넣는 내용의 개요가 넣을 자리의 템플릿보다 깊으면, 넘친 레벨에는 넣는 쪽(원본)의 개요 레벨이 자리 템플릿 아래에 이어 붙습니다(덮은 템플릿). "
  + "「덮은 템플릿 그대로」 = 넘친 줄을 원본 모양 그대로 둡니다. 「템플릿 수정」 = 넘친 레벨마다 레터 · 본보기(문단·글자 모양을 가져올 목적 문서의 레벨) · 레터 앞 빈칸을 고칩니다. "
  + "「다른 템플릿」 = 목적 문서의 다른 템플릿을 골라 넘친 레벨이 그 템플릿의 레벨을 차례로 받게 합니다(모자란 레벨은 원본 그대로). "
  + "자리 템플릿에 맞는 레벨은 어느 쪽을 골라도 지금처럼 자리 템플릿으로 바뀝니다. 같은 자리 템플릿에 같은 원본 사슬이 넘치는 곳은 한 번만 고릅니다.";
const mergeOverDrafts = {}; // 「문서 id\n사례 열쇠」 → 펴 둔 편집 초안 — 목록을 다시 그려도 쓰던 값이 남는다
let mergeOverBusy = ""; // "" | "save" | "refit"

const mergeOverChain = (keys) => (keys || []).join(" › ");
const mergeOverId = (opt, c) => `${opt.docId}\n${c.key}`;

function mergeOverCaseText(c) { // 사례 한 줄의 이름 — 「자리 템플릿 사슬 ▸ 넘친 원본 레터들」
  return `${mergeOverChain((c.to || {}).chain) || (c.to || {}).template || ""} ▸ ${mergeOverChain((c.levels || []).map((x) => x.was || x.key || "?"))}`;
}

function mergeOverLevelText(lv) { // 넘친 레벨 하나에 무엇이 들어가는가(글) — 알림(본보기 없음 · 윗 레벨과 같은 레터)은 괄호로
  const to = lv.letter ? `「${lv.letter}」` : lv.like ? `「${lv.like.letter || "?"}」` : "";
  const shape = lv.like ? ` · 본보기 L${lv.like.level}` : lv.letter || lv.lead != null ? " · 제 모양" : "";
  const what = to || lv.lead != null ? `${to ? `→ ${to}` : "레터 그대로"}${shape}${lv.lead != null ? ` · 레터 앞 빈칸 ${lv.lead}칸` : ""}` : "원본 그대로";
  const warn = [lv.missing ? "본보기 없음 — 원본 꼴로 둠" : "", lv.clash ? "윗 레벨과 같은 레터" : ""].filter(Boolean);
  return `L${lv.n} 「${lv.was || lv.key || ""}」 ${what}${warn.length ? ` (${warn.join(" · ")})` : ""}`;
}

function mergeOverOptions(c, templates) { // 본보기·「다른 템플릿」 으로 고를 (템플릿, 레벨) — 그 자리 아래에 이미 붙은 서브 템플릿이 맨 앞
  const under = new Set(c.under || []), out = [];
  const list = [...(templates || [])].sort((a, b) => Number(under.has(b.anchor)) - Number(under.has(a.anchor)));
  for (const t of list) for (const lv of t.levels || []) if (lv.ok) out.push({ template: t.anchor, level: lv.level, no: t.no, chain: t.chain || [], letter: lv.letter || "", text: lv.text || "", under: under.has(t.anchor) });
  return out;
}
const mergeOverOptText = (o) => `${o.under ? "이 자리 아래 · " : ""}#${o.no == null ? "–" : o.no} ${mergeOverChain(o.chain)} — L${o.level} 「${o.letter}」`;

function mergeOverDraft(c, templates) { // 사례의 지금 선택 → 편집 초안 { mode, template, levels[{ letter, like, lead }] }
  const first = mergeOverOptions(c, templates)[0];
  return { mode: c.mode || "cover", template: c.template ? { template: c.template.template, level: c.template.level } : first ? { template: first.template, level: first.level } : null,
    levels: (c.levels || []).map((x) => ({ letter: x.letter || "", like: x.like ? { template: x.like.template, level: x.like.level } : null, lead: x.lead == null ? null : x.lead })) };
}

function mergeOverBody(c, d) { // 편집 초안 → PUT 바디(아무것도 안 고친 레벨은 null = 원본 그대로)
  if (d.mode === "template") return { key: c.key, mode: "template", template: d.template ? { template: d.template.template, level: d.template.level } : null };
  if (d.mode !== "edit") return { key: c.key, mode: "cover" };
  return { key: c.key, mode: "edit", levels: (d.levels || []).map((x) => {
    const letter = String(x.letter || "").trim() || null, lead = x.lead === "" || x.lead == null || Number.isNaN(Number(x.lead)) ? null : Number(x.lead);
    const like = x.like ? { template: x.like.template, level: x.like.level } : null;
    return letter || like || lead != null ? { letter, like, lead } : null;
  }) };
}

function mergeOverSection(opt) { // opt = { docId, over, onChange(): 계획을 다시 세우고 목록을 다시 그린다, go(c): 문서의 그 자리로, disabled } → 절 | null(넘친 곳 없음)
  if (!opt || !opt.over || !(opt.over.cases || []).length) return null;
  const sec = el("div", "mo-sec");
  sec.dataset.mergeOver = "1";
  mergeOverDraw(sec, opt);
  return sec;
}

function mergeOverDraw(sec, opt) {
  const cases = opt.over.cases || [], rec = opt.over.records || {}, lines = cases.reduce((a, c) => a + (c.lines || 0), 0), busy = !!mergeOverBusy || !!opt.disabled;
  const cap = el("div", "lk-cap mo-cap");
  cap.append(el("span", null, `넘친 개요 레벨 — ${nf(cases.length)}곳${lines ? ` · 넣을 줄 ${nf(lines)}` : ""}${rec.lines ? ` · 넣은 줄 ${nf(rec.lines)}` : ""}`), hHelp("넘친 개요 레벨 설명", MERGE_OVER_HELP));
  if (rec.lines) {
    const b = hBtn(mergeOverBusy === "refit" ? "맞추는 중…" : `넣은 줄에 다시 맞추기(${nf(rec.lines)}줄)`, () => mergeOverRefit(sec, opt), { cls: "btn sm", disabled: busy,
      title: "이미 넣은 넘친 줄에 지금 고른 처리를 다시 입힙니다 — 한 번의 편집(실행 취소 1). 원본 문서는 필요 없습니다" });
    b.dataset.moRefit = "1";
    cap.append(b);
  }
  const list = el("div", "mo-list");
  for (const c of cases) list.append(mergeOverCaseEl(sec, opt, c, busy));
  sec.replaceChildren(cap, list);
}

function mergeOverCaseEl(sec, opt, c, busy) {
  const box = el("div", "mo-case"), head = el("div", "mo-head"), d = mergeOverDrafts[mergeOverId(opt, c)];
  box.dataset.key = c.key;
  box.dataset.mode = c.mode || "cover";
  const name = el("button", "mo-name", mergeOverCaseText(c));
  name.type = "button";
  name.title = `자리 템플릿 #${(c.to || {}).no == null ? "–" : c.to.no} 의 마지막 레벨(L${(c.to || {}).level}) 아래로 넘친 레벨 — 누르면 문서의 첫 자리로 갑니다`;
  name.onclick = () => { if (opt.go) opt.go(c); };
  const count = el("span", "mo-count muted", [c.lines ? `넣을 줄 ${nf(c.lines)}` : "", c.applied ? `넣은 줄 ${nf(c.applied)}` : "", c.places > 1 ? `자리 ${nf(c.places)}` : ""].filter(Boolean).join(" · "));
  const sel = el("select", "mo-mode");
  for (const [k, t] of Object.entries(MERGE_OVER_MODE)) { const o = el("option", null, t); o.value = k; sel.append(o); }
  sel.value = d ? d.mode : c.mode || "cover";
  sel.disabled = busy;
  sel.setAttribute("aria-label", "넘친 레벨의 처리");
  sel.onchange = () => mergeOverPick(sec, opt, c, sel.value);
  head.append(name, count, sel);
  const ul = el("ul", "mo-levels"); // 지금 저장된 처리로 레벨마다 무엇이 들어가는가
  for (const lv of c.levels || []) {
    const li = el("li", null, mergeOverLevelText({ ...lv, clash: false, missing: false }));
    if (lv.missing) li.append(el("span", "mo-flag", "본보기 없음 — 원본 꼴로 둠"));
    if (lv.clash) li.append(el("span", "mo-flag", "윗 레벨과 같은 레터"));
    ul.append(li);
  }
  box.append(head, ul);
  if (d && d.mode !== "cover") box.append(mergeOverEditEl(sec, opt, c, d, busy));
  return box;
}

function mergeOverPick(sec, opt, c, mode) { // 처리 목록을 바꿈 — 「덮은 템플릿 그대로」 는 바로 저장, 나머지는 그 줄 아래에 편집을 편다(「적용」 을 눌러야 저장)
  const id = mergeOverId(opt, c);
  if (mode === "cover") {
    delete mergeOverDrafts[id];
    if ((c.mode || "cover") !== "cover") mergeOverSave(sec, opt, c, { key: c.key, mode: "cover" });
    else mergeOverDraw(sec, opt);
    return;
  }
  const d = { ...(mergeOverDrafts[id] || mergeOverDraft(c, opt.over.templates)), mode };
  if (!mergeOverOptions(c, opt.over.templates).length && mode === "template") { toast("목적 문서에 본보기로 쓸 템플릿 레벨이 없습니다", true); mergeOverDraw(sec, opt); return; }
  mergeOverDrafts[id] = d;
  mergeOverDraw(sec, opt);
}

function mergeOverEditEl(sec, opt, c, d, busy) { // 사례 줄 아래에 펴는 편집 — 「다른 템플릿」 = 템플릿·시작 레벨 하나 · 「템플릿 수정」 = 넘친 레벨마다 레터 · 본보기 · 앞 공백
  const box = el("div", "mo-edit"), opts = mergeOverOptions(c, opt.over.templates);
  box.dataset.mode = d.mode;
  const pick = (cur, none) => { // (템플릿, 레벨) 고르는 목록 — none = 맨 위의 「없음」 글
    const s = el("select", "mo-like");
    if (none) { const o = el("option", null, none); o.value = ""; s.append(o); }
    opts.forEach((o, i) => { const x = el("option", null, mergeOverOptText(o)); x.value = String(i); s.append(x); });
    const at = cur ? opts.findIndex((o) => o.template === cur.template && o.level === cur.level) : -1;
    if (cur && at < 0) { const x = el("option", null, `(지금 문서에 없음) ${cur.template} L${cur.level}`); x.value = "gone"; s.append(x); s.value = "gone"; }
    else s.value = at < 0 ? "" : String(at);
    s.disabled = busy;
    return s;
  };
  const read = (s, cur) => (s.value === "gone" ? cur : s.value === "" ? null : { template: opts[Number(s.value)].template, level: opts[Number(s.value)].level });
  if (d.mode === "template") {
    const row = el("label", "mo-row"), s = pick(d.template, "");
    s.setAttribute("aria-label", "다른 템플릿과 시작 레벨");
    s.onchange = () => { d.template = read(s, d.template); };
    row.append(el("span", "muted", `L${(c.levels[0] || {}).n} 부터 차례로`), s);
    box.append(row, el("p", "hnote", "넘친 레벨이 고른 템플릿의 그 레벨부터 아래 레벨을 차례로 받습니다(레터·문단 모양·글자 모양). 그 템플릿의 레벨이 모자란 넘친 레벨은 원본 그대로 둡니다."));
  } else {
    const grid = el("div", "mo-grid");
    for (const h of ["레벨", "원본", "넣을 레터", "본보기(모양)", "레터 앞 빈칸"]) grid.append(el("span", "mo-th", h));
    (c.levels || []).forEach((lv, i) => {
      const x = d.levels[i] || (d.levels[i] = { letter: "", like: null, lead: null });
      const letter = el("input", "mo-letter"), lead = el("input", "mo-lead"), like = pick(x.like, "원본 모양 그대로");
      letter.type = "text";
      letter.maxLength = 12;
      letter.value = x.letter || "";
      letter.placeholder = "그대로";
      letter.disabled = lead.disabled = busy;
      letter.setAttribute("aria-label", `L${lv.n} 에 넣을 레터`);
      letter.oninput = () => { x.letter = letter.value; };
      like.setAttribute("aria-label", `L${lv.n} 의 본보기`);
      like.onchange = () => { x.like = read(like, x.like); };
      lead.type = "number";
      lead.min = "0";
      lead.max = "40";
      lead.value = x.lead == null ? "" : String(x.lead);
      lead.placeholder = "–"; // 좁은 칸(두 자리 수) — 「그대로」 는 아래 안내 글에
      lead.setAttribute("aria-label", `L${lv.n} 의 레터 앞 빈칸 칸 수`);
      lead.oninput = () => { x.lead = lead.value === "" ? null : Number(lead.value); };
      grid.append(el("span", "mo-lv", `L${lv.n}`), el("span", "mo-was", `「${lv.was || lv.key || ""}」`), letter, like, lead);
    });
    box.append(grid, el("p", "hnote", "빈 칸 = 그대로. 본보기를 고르면 그 레벨 줄의 문단 모양·글자 모양·레터 앞뒤 빈칸을 받고, 레터를 안 적으면 본보기의 레터를 씁니다. 번호 꼴 레터(「(1)」·「가.」·「①」)는 부모 줄마다 처음부터 매깁니다."));
  }
  const acts = el("div", "mo-acts");
  acts.append(hBtn(mergeOverBusy === "save" ? "저장 중…" : "적용", () => mergeOverSave(sec, opt, c, mergeOverBody(c, d)), { cls: "btn sm", disabled: busy || (d.mode === "template" && !d.template), title: "이 처리를 저장하고 넣기 계획을 다시 셉니다 — 문서는 「반영」 을 눌러야 바뀝니다" }),
    hBtn("취소", () => { delete mergeOverDrafts[mergeOverId(opt, c)]; mergeOverDraw(sec, opt); }, { cls: "btn sm", disabled: busy }));
  box.append(acts);
  return box;
}

async function mergeOverSave(sec, opt, c, body) { // PUT — 저장하면 서버가 세워 둔 계획을 버린다 → 부른 쪽이 다시 계획(opt.onChange)
  if (mergeOverBusy) return;
  mergeOverBusy = "save";
  mergeOverDraw(sec, opt);
  try {
    await api(`/api/docs/${opt.docId}/merge-over`, { method: "PUT", headers: H_JSON, body: JSON.stringify(body) });
    delete mergeOverDrafts[mergeOverId(opt, c)];
    toast(c.applied ? `저장 — 이미 넣은 ${nf(c.applied)}줄은 「넣은 줄에 다시 맞추기」 로 바꿉니다` : "저장 — 넣기 계획을 다시 셉니다");
    mergeOverBusy = "";
    if (opt.onChange) await opt.onChange();
  } catch (e) {
    toast(`저장하지 못했습니다: ${e.message}`, true);
  } finally {
    mergeOverBusy = "";
    if (sec.isConnected) mergeOverDraw(sec, opt);
  }
}

async function mergeOverRefit(sec, opt) { // 넣은 뒤 다시 맞추기(spec_병합 ② §5-5 7) — 넣은 줄의 기록과 지금 선택만으로. 편집 하나(실행 취소 1)
  const n = ((opt.over || {}).records || {}).lines || 0;
  if (mergeOverBusy || !n) return;
  if (!confirm(`이미 넣은 넘친 줄 ${nf(n)}줄에 지금 고른 처리를 다시 입힐까요?\n\n한 번의 편집으로 바뀌고, 실행 취소(Ctrl+Z) 한 번으로 되돌릴 수 있습니다. 사람이 첫머리를 고친 줄은 건너뜁니다.`)) return;
  mergeOverBusy = "refit";
  mergeOverDraw(sec, opt);
  try {
    if (typeof flushAll === "function") await flushAll(); // 고치던 글을 먼저 서버에
    const r = await api(`/api/docs/${opt.docId}/merge-over/refit`, { method: "POST", headers: H_JSON, body: "{}" });
    const kept = Object.entries(r.kept || {}).filter(([, k]) => k).map(([k, v]) => `${(r.labels || {})[k] || k} ${nf(v)}`).join(" · ");
    if (r.nothing) toast(`다시 맞출 줄이 없습니다${kept ? ` — 건너뜀: ${kept}` : "(이미 그 모양입니다)"}`);
    else {
      if (typeof applyEditState === "function") applyEditState(r);
      toast(`다시 맞춤 — ${nf(r.lines || 0)}줄${kept ? ` · 건너뜀: ${kept}` : ""}`);
      if (typeof reloadDoc === "function") await reloadDoc(); // 떨어진 자리 여러 곳이 바뀐다
    }
    mergeOverBusy = "";
    if (opt.onChange) await opt.onChange();
  } catch (e) {
    toast(e.status === 422 ? `표준 검사에 걸려 되돌렸습니다: ${e.message}` : `다시 맞추지 못했습니다: ${e.message}`, true);
  } finally {
    mergeOverBusy = "";
    if (sec.isConnected) mergeOverDraw(sec, opt);
  }
}
