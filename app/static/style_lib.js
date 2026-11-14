"use strict";
// 서식 보관함(spec_일반편집 ② §7 끝점 · §12 화면) — 공통 모듈: TASK 「문서 일반 편집」 뿐 아니라 어느 TASK 의 문서에서나 연다(R6). 사용자 2026-11-13
// "여기에서 사용되는 문서 서식을 템플릿으로 저장되고 사용할 수 있도록 … 서식복사 … 선택하면 그 서식을 저장해서 재사용".
// 2열(headsDlg — 팝업 아님, design.md §2) kind 둘:
//   "styleLib"  = 보관한 서식: 종류 탭(표 서식 · 글 서식) · 서식마다 이름 · 원본 · 충실도 꼬리표 · PDF 검증 상태 · 견본 그림 · 뺀 것(접힘) ·
//                 「빈 표 넣기」·「고른 표에 입히기」·(글 서식 항목마다)「고른 문단에 입히기」 · 이름 바꾸기 · 다시 검증 · 지우기 / 맨 위 「이 문서에서 추출」·「파일에서 추출」.
//   "styleSave" = 추출 후보(표 → 글): 체크 · 이름 · 띠 수(머리행·머리열·합계행) · 같은 서식 n개 · 자리로 · 「구조까지 저장」 / 「글도 그대로 저장」 · 「이름 붙이기(LLM)」 · 「고른 n개 저장」.
// 여는 곳: 에이전트 보기의 「서식 보관함」(doc_agent.js) · 표 메뉴 「서식 보관함에 저장…」(table_menu.js → styleSaveOpen({table})) · 반영한 제안 카드 「이 표를 서식으로 저장」.
// 밖에 내는 것: styleLibOpen(tab?) · styleSaveOpen({table?, blueprint?, file?}) · 문서 자리 도우미 slSelection · slTopOf · slBlockEls · slGo(doc_agent.js 가 같이 쓴다).
// app.js 가 주는 것: state·heads·$·el·api·toast·structOp·flushAll·headsDlg·hBtn·hFoot·hHelp·paraEl·scrollToBlock·fmtWhen·nf·short·oneLine·H_JSON. tables.js: xlBlock·xlSelRange. table_menu.js: tmn·tmnActivate.
// table_make.js: tpk(문단 묶음). 서버 짝은 app/style_api.py — 끝점이 없거나(404) 보관함이 꺼져 있으면(503) 그 까닭을 한 줄로 보인다. index.html 이 doc_agent.js 앞에 읽는다.

const SL_FID = { native: ["원본 서식", "hwpx 문서의 서식 정의를 그대로 옮긴 것"], summary: ["요약", "docx 의 서식을 요약 명세로 다시 지은 것 — 원본과 조금 다를 수 있습니다"], approx: ["근사", "PDF 에서 잰 값으로 어림한 것 — 칸 여백·줄 간격·괘선 종류는 재지 못합니다"] };
const SL_VERIFY = { ok: "검증됨", warn: "확인 필요", fail: "실패", none: "PDF 없음", running: "검증 중" };
const SL_VERIFY_HELP = { ok: "한글로 출력한 견본이 서식 값과 맞습니다", warn: "실패는 없지만 확인이 필요합니다 — 재지 못한 것이 많거나 · 대체 글꼴로 출력됐거나 · 2쪽 이상", fail: "출력한 견본이 서식 값과 다른 데가 있습니다 — 「뺀 것 · 검증 내역」 을 보세요",
  none: "PDF 출력(한글)이 없어 검증하지 못했습니다", running: "한글로 견본을 출력해 재는 중입니다(2초마다 다시 읽음)" };
const SL_CHECK = { render: "출력", pages: "쪽 수", text: "칸 글", fontSize: "글자 크기", bold: "굵게", color: "글자 색", fontFace: "글꼴", fill: "음영", edge: "괘선", lineWidth: "선 굵기", width: "표 폭", indent: "들여쓰기" };
const SL_STATUS = { pass: "통과", fail: "실패", unknown: "모름", unsupported: "재지 못함" };
const SL_BANDS = [["headerRows", "머리행", "위쪽 열 제목 행 수"], ["headerCols", "머리열", "왼쪽 행 제목 열 수"], ["footRows", "합계행", "아래쪽 합계·소계 행 수"]];
const SL_KEEP_HELP = "기본은 자료값을 저장하지 않습니다 — 머리 칸(머리행·머리열)의 글은 그대로 두고, 나머지 칸·문단의 글은 견본(「0」·「가나다」·「견본 글입니다」)으로 바꿔 저장합니다.\n켜면 원래 글을 그대로 저장합니다 — 보관함은 서버 전체에서 보이므로 다른 문서·TASK 에서 열어도 그 글이 보입니다.";
// 한 번 읽어 둔 것(보관함은 문서와 무관 — 문서를 바꿔도 남는다). save = 추출 후보 열의 상태(문서·파일마다)
const STYLE = { tab: "table", list: null, enabled: true, pdf: true, broken: [], err: "", edit: null, big: new Set(), more: new Set(), full: {}, msg: {}, pollTimer: 0, file: null, save: null };
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { styleApply: "서식 보관함 적용", styleSave: "서식 보관함에 저장", styleName: "서식 후보 이름 붙이기(LLM)" }); // 「기록」 탭의 이름

const styleErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「서식 보관함」 을 쓸 수 있습니다" : (e && e.message) || "알 수 없는 오류");
const styleUrl = (sid, tail = "") => `/api/styles/${encodeURIComponent(sid)}${tail}`;
const slWhen = (v) => { const t = typeof v === "number" ? (v > 1e12 ? v / 1000 : v) : v ? Date.parse(v) / 1000 : NaN; return Number.isFinite(t) ? fmtWhen(t) : ""; };
const slBandsText = (b) => (b ? SL_BANDS.filter(([k]) => b[k]).map(([k, name]) => `${name} ${b[k]}`).join(" · ") || "머리 없음" : "");
const slSecs = (t0) => `${Math.round((performance.now() - t0) / 1000)}초`;

// ---- 문서 자리 도우미(에이전트 보기와 같이 쓴다) ------------------------------------------------------------------------------
function slSelection() { // 지금 문서에서 고른 것 — {paras: 끌어 고른 문단 묶음, table: 고른 표, range: 그 표에서 끌어 고른 칸 범위, cursor: 커서 문단}
  const paras = typeof tpk === "object" && tpk ? tpk.ids.filter((i) => paraEl(i)) : [];
  let table = typeof tmn === "object" && tmn && tmn.active && typeof xlBlock === "function" && xlBlock(tmn.active) ? tmn.active : null;
  if (!table && typeof tselActive === "function" && tselActive() && tsel.tbl) table = tsel.tbl;
  const range = table && typeof xlSelRange === "function" ? xlSelRange(table) : null;
  const cursor = state.cur && paraEl(state.cur.id) ? state.cur.id : null;
  return { paras, table, range, cursor };
}
function slTopOf(id) { // 그 문단·표를 품은 본문 최상위 블록 id(칸 안이면 바깥 표) — 서버의 「넣을 자리」 는 본문 최상위만 받는다(spec ② §4)
  const has = (b) => b.id === id || (b.cells || []).some((c) => (c.blocks || []).some(has));
  const top = (state.blocks || []).find(has);
  return top ? top.id : null;
}
function slBlockEls(id) { // 문서의 그 블록 요소들 — 문단 하나 · 표의 쪽 조각들(엑셀식 보기로 바뀐 표 포함)
  if (typeof id !== "string" || !id) return [];
  const q = CSS.escape(id);
  return [...document.querySelectorAll(`#doc .para[data-id="${q}"], #doc table.tbl[data-tbl="${q}"], #doc .xl-wrap[data-tbl="${q}"]`)].filter((e) => !e.hidden);
}
function slGo(id) { // 문서에서 그 블록으로 — 열은 그대로 둔다(나란히 보기)
  if (id && paraEl(id)) { scrollToBlock(id); return true; }
  const t = slBlockEls(id)[0];
  if (!t) { toast("그 자리가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)"); return false; }
  t.scrollIntoView({ block: "center", behavior: "smooth" });
  if (t.dataset.tbl && typeof tmnActivate === "function") tmnActivate(t.dataset.tbl);
  return true;
}
function slHit(ids) { // 후보 줄에 올린 동안 문서의 그 표·문단(파랑 — 스크립트 후보. 보라는 LLM 제안에만: design.md §6). null = 걷기
  for (const e of document.querySelectorAll("#doc .sl-hit")) e.classList.remove("sl-hit");
  for (const id of ids || []) for (const e of slBlockEls(id)) e.classList.add("sl-hit");
}
function slRun(text) { // 도는 작업 한 줄 — 동그라미 + 지금 하는 일(+ 지난 시간은 .sl-run-text 만 바꾼다: design.md §7)
  const s = el("span", "sl-run");
  s.append(el("span", "sl-spin"), el("span", "sl-run-text", text));
  return s;
}

// ---- 보관함 목록(kind "styleLib") ------------------------------------------------------------------------------------------
const styleLibOn = () => heads.dlg === "styleLib";
function styleChanged() { if (typeof agentStylesRefresh === "function") agentStylesRefresh(); } // 에이전트 입력의 서식 고르기도 다시(doc_agent.js)

async function styleLibOpen(tab = null) {
  if (tab === "table" || tab === "text") STYLE.tab = tab;
  headsDlg("styleLib", "서식 보관함", "보관한 표 서식 · 글 서식 — 어느 문서에서나 씁니다");
  const seq = heads.seq;
  STYLE.edit = null;
  styleLibDraw(); // 읽어 둔 목록이 있으면 먼저 보인다
  await styleLibLoad();
  if (seq !== heads.seq || !styleLibOn()) return;
  styleLibDraw();
}

async function styleLibLoad() {
  try {
    const r = await api("/api/styles");
    Object.assign(STYLE, { list: r.styles || [], enabled: r.enabled !== false, pdf: !!r.pdf, broken: r.broken || [], err: "" });
  } catch (e) { STYLE.list = null; STYLE.err = styleErr(e); }
}

function styleLibDraw() {
  if (!styleLibOn()) return;
  const tools = $("headsDlgTools"), body = $("headsDlgBody"), keep = body.scrollTop, list = STYLE.list || [];
  const count = (k) => list.filter((s) => s.kind === k).length, hw = !!state.id && state.format !== "docx";
  tools.textContent = "";
  const tabs = el("span", "sl-tabs");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "서식 종류");
  for (const [k, name] of [["table", "표 서식"], ["text", "글 서식"]]) {
    const b = hBtn(STYLE.list ? `${name} ${nf(count(k))}` : name, () => { STYLE.tab = k; STYLE.edit = null; styleLibDraw(); }, { cls: "btn sm" + (STYLE.tab === k ? " on" : "") });
    b.dataset.slTab = k;
    b.setAttribute("aria-pressed", String(STYLE.tab === k));
    tabs.append(b);
  }
  const fromDoc = hBtn("이 문서에서 추출", () => styleSaveOpen(), { disabled: !hw, title: hw ? "이 문서의 표 서식·글 서식 후보를 찾아 보관함에 저장합니다(문서는 안 바뀜)" : "hwpx 문서를 열어야 합니다 — 다른 형식은 「파일에서 추출」" });
  const fromFile = hBtn("파일에서 추출", () => styleFilePick(), { disabled: !!STYLE.file, title: "hwp·hwpx·docx·pdf 파일을 올려 그 안의 서식 후보를 찾습니다 — 작업은 만들지 않습니다\nhwpx = 원본 서식 그대로 · docx = 요약 · pdf = 잰 값으로 근사(표만)" });
  fromDoc.dataset.slAct = "fromDoc";
  fromFile.dataset.slAct = "fromFile";
  tools.append(tabs, fromDoc, fromFile);
  if (STYLE.file) tools.append(slRun(`「${short(STYLE.file.name, 24)}」 에서 서식을 찾는 중 · ${slSecs(STYLE.file.t0)}`));
  body.textContent = "";
  const wrap = el("div", "sl-wrap");
  body.append(wrap);
  if (STYLE.err) {
    wrap.append(el("p", "hwarn fail", `서식 보관함을 읽지 못했습니다: ${STYLE.err}`), el("div", "sl-acts"));
    wrap.lastChild.append(hBtn("다시 읽기", () => styleLibOpen()));
    hFoot("", false);
    return;
  }
  if (!STYLE.list) { wrap.append(slRun("서식 보관함을 읽는 중…")); hFoot("", false); return; }
  const mine = list.filter((s) => s.kind === STYLE.tab);
  if (!mine.length) {
    wrap.append(el("p", "hnote", STYLE.tab === "table"
      ? "보관한 표 서식이 없습니다 — 「이 문서에서 추출」 로 문서의 표 서식을 저장하거나, 문서의 표 메뉴에서 「서식 보관함에 저장…」 을 누르세요."
      : "보관한 글 서식이 없습니다 — 「이 문서에서 추출」 로 개요템플릿의 글 서식(레벨마다 레터·글자·문단 모양)을 저장하세요."));
  }
  for (const s of mine) wrap.append(styleItemEl(s));
  if (STYLE.broken.length) wrap.append(el("p", "sl-msg", `읽지 못한 서식 ${nf(STYLE.broken.length)}개(파일이 깨짐) — ${STYLE.broken.slice(0, 6).join(" · ")}`));
  body.scrollTop = keep;
  hFoot(`표 서식 ${nf(count("table"))} · 글 서식 ${nf(count("text"))}${STYLE.pdf ? "" : " · PDF 출력이 꺼져 있어 검증은 건너뜁니다"}`, false);
  const inp = STYLE.edit && STYLE.edit.mode === "rename" && !STYLE.edit.busy ? body.querySelector(".sl-rename") : null;
  if (inp) { inp.focus({ preventScroll: true }); if (!STYLE.edit.shown) { STYLE.edit.shown = true; inp.select(); } }
  stylePoll();
}

function styleVerifyEls(s) { // 검증 상태 꼬리표(+ 「검증 뒤 바뀜」)
  const v = s.verify, st = v ? v.status || "" : "", c = v && v.coverage, tag = el("span", "sl-verify"), out = [tag];
  tag.dataset.status = st || "pending";
  if (st === "running") tag.append(el("span", "sl-spin"));
  tag.append(st ? SL_VERIFY[st] || st : "검증 전");
  tag.title = (st ? SL_VERIFY_HELP[st] || "" : "아직 PDF 검증을 하지 않았습니다 — 「다시 검증」")
    + (c ? `\n통과 ${nf(c.pass || 0)} · 실패 ${nf(c.fail || 0)} · 모름 ${nf(c.unknown || 0)} · 재지 못함 ${nf(c.unsupported || 0)}` : "");
  if (v && v.stale && st !== "running") {
    const old = el("span", "sl-verify stale", "검증 뒤 바뀜");
    old.dataset.status = "stale";
    old.title = "검증한 뒤에 띠 수·구조·항목이 바뀌었습니다 — 「다시 검증」 을 누르세요";
    out.push(old);
  }
  return out;
}

function styleItemEl(s) {
  const box = el("section", "sl-item"), head = el("div", "sl-head"), E = STYLE.edit && STYLE.edit.sid === s.id ? STYLE.edit : null;
  const can = !!state.id && state.format !== "docx", need = can ? "" : "\nhwpx 문서를 열어야 합니다", src = s.source || {}, items = s.items || [];
  box.dataset.style = s.id;
  if (E && E.mode === "rename") { // 이름 줄 — Enter 저장 · Esc 취소
    const inp = el("input", "sl-rename");
    inp.type = "text"; inp.maxLength = 60; inp.value = E.draft; inp.disabled = !!E.busy;
    inp.setAttribute("aria-label", `「${s.name}」 의 새 이름`);
    inp.oninput = () => { E.draft = inp.value; };
    inp.onkeydown = (ev) => {
      if (ev.isComposing || ev.keyCode === 229) return;
      if (ev.key === "Enter") { ev.preventDefault(); styleRename(s); } else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); STYLE.edit = null; styleLibDraw(); }
    };
    head.append(inp, hBtn("저장", () => styleRename(s), { cls: "btn sm primary", disabled: !!E.busy }), hBtn("취소", () => { STYLE.edit = null; styleLibDraw(); }, { disabled: !!E.busy }));
  } else {
    head.append(el("strong", "sl-name", s.name || "(이름 없음)"));
    const fid = SL_FID[s.fidelity];
    if (fid) { const t = el("span", "hb", fid[0]); t.title = fid[1]; t.dataset.fidelity = s.fidelity; head.append(t); }
    head.append(...styleVerifyEls(s));
  }
  const parts = [src.name ? `원본 ${src.name}${src.page ? ` ${src.page}쪽` : ""}` : "", s.kind === "table" && s.rows ? `${s.rows}×${s.cols}` : "", s.kind === "table" ? slBandsText(s.bands) : "",
    s.kind === "table" && s.blueprint ? "구조 있음" : "", s.kind === "text" && items.length ? `항목 ${nf(items.length)}` : "", slWhen(s.updated || s.created)].filter(Boolean);
  const line = el("p", "sl-src", parts.join(" · "));
  if (s.note) line.title = s.note;
  box.append(head, line);
  const v = s.verify;
  if (v && ["ok", "warn", "fail"].includes(v.status)) { // 견본 그림 — 보일 때 읽고(lazy), 누르면 그 자리에서 크게/작게(팝업 아님)
    const img = el("img", "sl-proof" + (STYLE.big.has(s.id) ? " big" : "")), flip = () => { if (STYLE.big.has(s.id)) STYLE.big.delete(s.id); else STYLE.big.add(s.id); img.classList.toggle("big", STYLE.big.has(s.id)); };
    img.loading = "lazy";
    img.alt = `${s.name} — 한글로 출력한 견본`;
    img.title = "한글로 출력한 견본 — 누르면 크게/작게";
    img.tabIndex = 0;
    img.setAttribute("role", "button");
    img.src = styleUrl(s.id, `/proof.png?v=${encodeURIComponent(s.revision || "")}`);
    img.onclick = flip;
    img.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); flip(); } };
    img.onerror = () => { img.hidden = true; }; // 그림이 없는 옛 판 — 줄만 보인다
    box.append(img);
  }
  const nLoss = typeof s.losses === "number" ? s.losses : (s.losses || []).length;
  const more = el("details", "sl-more"), moreBody = el("div");
  more.open = STYLE.more.has(s.id);
  more.append(el("summary", null, `뺀 것 ${nf(nLoss)} · 검증 내역`), moreBody);
  more.ontoggle = () => { if (!more.open) STYLE.more.delete(s.id); else { STYLE.more.add(s.id); if (!moreBody.childElementCount) styleMoreFill(s, moreBody); } }; // 펴 둔 채 다시 그릴 때는 아래에서 이미 채운다
  if (more.open) styleMoreFill(s, moreBody);
  box.append(more);
  if (s.kind === "text" && items.length) { // 글 서식 — 항목(레벨)마다 한 줄
    const grid = el("div", "sl-levels");
    for (const it of items) {
      const m = it.marker || {}, name = el("span", "sl-lname");
      name.append(it.name || "(이름 없음)");
      if (m.mode === "literal" && m.literal) name.append(el("i", null, ` ${m.literal}`));
      else if (m.mode === "auto") name.append(el("i", null, " 자동 번호"));
      if (it.sample) name.append(el("i", null, ` · ${it.sample}`));
      name.title = [it.name, m.mode === "auto" ? "자동 번호 — 대상 문서의 번호 설정을 따릅니다" : m.literal ? `레터 「${m.literal}」` : "", it.sample].filter(Boolean).join("\n");
      const b = hBtn("고른 문단에 입히기", () => styleApply(s, "format", it), { disabled: !can, title: `문서에서 끌어 고른 문단들(없으면 커서 문단)에 이 항목의 글자·문단 모양을 입힙니다 — 글·레터는 그대로 · 실행 취소로 되돌림${need}` });
      b.dataset.slItem = it.key;
      grid.append(el("span", "sl-lv", it.level ? `L${it.level}` : "문단"), name, b);
    }
    box.append(grid);
  }
  const acts = el("div", "sl-acts"), act = (key, b) => { b.dataset.slAct = key; acts.append(b); return b; };
  if (s.kind === "table") {
    if (s.blueprint) act("blank", hBtn("빈 표 넣기", () => styleApply(s, "tableBlank"), { disabled: !can, title: `커서가 있는 문단(칸 안이면 그 표) 바로 뒤에 이 서식·구조의 빈 표를 넣습니다 — 실행 취소로 되돌림${need}` }));
    act("restyle", hBtn("고른 표에 입히기", () => styleApply(s, "tableRestyle"), { disabled: !can, title: `문서에서 누른 표(고른 표)에 이 서식을 입힙니다 — 구조·글·칸 크기는 그대로 · 실행 취소로 되돌림${need}` }));
  }
  acts.append(el("span", "sl-gap"));
  act("rename", hBtn("이름 바꾸기", () => { STYLE.edit = { sid: s.id, mode: "rename", draft: s.name || "" }; styleLibDraw(); }));
  act("verify", hBtn("다시 검증", () => styleVerify(s), { disabled: !STYLE.pdf || (v && v.status === "running"), title: STYLE.pdf ? "한글로 견본을 다시 출력해 서식 값과 견줍니다(수 초~수십 초 — 끝나면 상태가 바뀝니다)" : "PDF 출력(한글)이 꺼져 있습니다" }));
  act("delete", hBtn("지우기", () => { STYLE.edit = { sid: s.id, mode: "delete" }; styleLibDraw(); }, { cls: "btn sm danger", disabled: !!(E && E.mode === "delete") }));
  box.append(acts);
  if (E && E.mode === "delete") { // 한 번 더 눌러야 지운다(그 줄에서 — 확인 창 없음)
    const row = el("div", "sl-confirm"), yes = hBtn("지우기", () => styleDelete(s), { cls: "btn sm danger", disabled: !!E.busy, title: "보관함에서 지웁니다 — 되살릴 수 없습니다(이 서식으로 이미 만든 표·글은 그대로)" });
    yes.dataset.slAct = "deleteYes";
    row.append(el("span", null, `「${s.name}」 을(를) 보관함에서 지울까요?`), yes, hBtn("취소", () => { STYLE.edit = null; styleLibDraw(); }, { disabled: !!E.busy }));
    box.append(row);
  }
  const m = STYLE.msg[s.id];
  if (m) box.append(el("p", "sl-msg" + (m.err ? " err" : ""), m.text));
  return box;
}

async function styleMoreFill(s, box) { // 뺀 것 · 필요한 글꼴 · 검사마다의 결과 — 펼 때 그 서식 전체를 읽는다(GET /api/styles/{sid})
  const key = `${s.id}|${s.revision || ""}|${s.verify ? s.verify.status : ""}`;
  let m = STYLE.full[key];
  if (!m) {
    box.replaceChildren(slRun("읽는 중…"));
    try { m = STYLE.full[key] = await api(styleUrl(s.id)); }
    catch (e) { if (box.isConnected) box.replaceChildren(el("p", "sl-msg err", `읽지 못했습니다: ${styleErr(e)}`)); return; }
  }
  if (!box.isConnected) return;
  const ul = el("ul"), losses = Array.isArray(m.losses) ? m.losses : [], fonts = (m.requirements && m.requirements.fonts) || [], vr = m.verify || null;
  for (const t of losses) ul.append(el("li", null, `뺀 것 — ${t}`));
  if (!losses.length) ul.append(el("li", "unknown", "뺀 것 없음"));
  if (fonts.length) ul.append(el("li", null, `필요한 글꼴 — ${fonts.join(" · ")}`));
  for (const c of (vr && vr.checks) || []) {
    const n = [c.pass ? `통과 ${nf(c.pass)}` : "", c.fail ? `실패 ${nf(c.fail)}` : "", c.unknown ? `모름 ${nf(c.unknown)}` : ""].filter(Boolean).join(" · ");
    const ex = (c.examples || [])[0];
    ul.append(el("li", c.status, `${SL_CHECK[c.what] || c.what} — ${SL_STATUS[c.status] || c.status}${n ? `(${n})` : ""}${c.note ? ` · ${c.note}` : ""}${ex ? ` · 예: ${ex.where || ""} ${ex.want} → ${ex.got}` : ""}`));
  }
  if (vr && vr.note) ul.append(el("li", null, vr.note));
  if (vr && vr.at) ul.append(el("li", "unknown", `검증 ${slWhen(vr.at)}${vr.pages ? ` · ${vr.pages}쪽` : ""}${vr.renderer && vr.renderer.name ? ` · ${vr.renderer.name}` : ""}`));
  box.replaceChildren(ul);
}

function styleMerge(m) { // 서식 하나 전체(meta) → 목록의 그 줄(요약 꼴)
  const s = (STYLE.list || []).find((x) => x.id === m.id);
  if (!s) return null;
  for (const k of ["name", "note", "revision", "updated", "bands", "rows", "cols", "fidelity", "source", "items"]) if (k in m) s[k] = m[k];
  if ("blueprint" in m) s.blueprint = !!m.blueprint;
  if (Array.isArray(m.losses)) s.losses = m.losses.length;
  if ("verify" in m) { const v = m.verify; s.verify = v ? { status: v.status, coverage: v.coverage || null, stale: !!v.stale } : null; }
  return s;
}
function styleSay(sid, text, err = false) { if (text) STYLE.msg[sid] = { text, err }; else delete STYLE.msg[sid]; }

function stylePoll() { // 「검증 중」 인 서식이 있는 동안 2초마다 그 서식을 다시 읽는다(열이 보관함일 때만) — 끝나면 그 줄이 바뀐다
  clearTimeout(STYLE.pollTimer);
  const running = (STYLE.list || []).filter((s) => s.verify && s.verify.status === "running");
  if (!running.length || !styleLibOn()) return;
  STYLE.pollTimer = setTimeout(async () => {
    let changed = false;
    for (const s of running) {
      try {
        const m = await api(styleUrl(s.id));
        if (!m.verify || m.verify.status !== "running") { styleMerge(m); changed = true; }
      } catch (e) { if (e.status === 404 && e.message !== "Not Found") { STYLE.list = (STYLE.list || []).filter((x) => x.id !== s.id); changed = true; } } // 그 사이 지워짐(서버가 「없는 서식」 이라 답함) · 그 밖의 오류는 다음 차례에 다시
    }
    if (changed) { styleChanged(); styleLibDraw(); } else stylePoll();
  }, 2000);
}

async function styleRename(s) {
  const E = STYLE.edit;
  if (!E || E.sid !== s.id || E.mode !== "rename" || E.busy) return;
  const name = (E.draft || "").trim().replace(/\s+/g, " ");
  if (!name) return;
  if (name === s.name) { STYLE.edit = null; styleLibDraw(); return; }
  E.busy = true;
  try {
    const m = await api(styleUrl(s.id), { method: "PUT", headers: H_JSON, body: JSON.stringify({ expectedRevision: s.revision, name }) });
    styleMerge({ name, ...m, id: s.id });
    styleSay(s.id, "");
    STYLE.edit = null;
    styleChanged();
  } catch (e) {
    E.busy = false;
    if (e.status === 409) { // 다른 곳에서 먼저 바뀜 — 새 판을 읽고 그 위에 다시 저장하게
      styleSay(s.id, "다른 곳에서 이 서식을 먼저 고쳤습니다 — 새 판을 읽었습니다. 「저장」 을 한 번 더 누르세요.", true);
      try { styleMerge(await api(styleUrl(s.id))); } catch { /* 지워졌으면 다음 읽기에서 빠진다 */ }
    } else styleSay(s.id, `이름을 바꾸지 못했습니다: ${styleErr(e)}`, true);
  }
  styleLibDraw();
}

async function styleDelete(s) {
  const E = STYLE.edit;
  if (!E || E.sid !== s.id || E.mode !== "delete" || E.busy) return;
  E.busy = true;
  try {
    await api(styleUrl(s.id, `?expectedRevision=${encodeURIComponent(s.revision || "")}`), { method: "DELETE" });
    STYLE.list = (STYLE.list || []).filter((x) => x.id !== s.id);
    styleSay(s.id, "");
    toast(`서식 「${s.name}」 을(를) 보관함에서 지웠습니다`);
    styleChanged();
  } catch (e) {
    if (e.status === 409) { styleSay(s.id, "다른 곳에서 이 서식을 먼저 고쳤습니다 — 새 판을 읽었습니다. 다시 확인하고 지우세요.", true); try { styleMerge(await api(styleUrl(s.id))); } catch { /* 그대로 */ } }
    else if (e.status === 404 && e.message !== "Not Found") STYLE.list = (STYLE.list || []).filter((x) => x.id !== s.id); // 이미 지워짐
    else styleSay(s.id, `지우지 못했습니다: ${styleErr(e)}`, true);
  }
  STYLE.edit = null;
  styleLibDraw();
}

async function styleVerify(s) {
  try {
    await api(styleUrl(s.id, "/verify"), { method: "POST" });
    s.verify = { ...(s.verify || {}), status: "running" };
    styleSay(s.id, "");
  } catch (e) { styleSay(s.id, `검증을 시작하지 못했습니다: ${styleErr(e)}`, true); }
  styleLibDraw();
}

async function styleApply(s, mode, item = null) { // 문서에 적용 — 구조 편집 한 번(structOp: 대기 중 글 반영 → 서버 편집 → 바뀐 블록만 다시 그림 · 실행 취소 1개)
  if (!state.id || state.busy) return;
  const sel = slSelection(), say = (t) => { styleSay(s.id, t, true); toast(t, true); styleLibDraw(); };
  let body = null;
  if (mode === "tableBlank") {
    const after = slTopOf(sel.cursor || sel.table || "");
    if (!after) { say("넣을 자리를 먼저 정하세요 — 문서에서 문단에 커서를 두거나 표를 누르세요"); return; }
    body = { mode, after };
  } else if (mode === "tableRestyle") {
    if (!sel.table) { say("서식을 입힐 표를 먼저 고르세요 — 문서에서 그 표를 누르세요"); return; }
    body = { mode, table: sel.table };
  } else {
    const paras = sel.paras.length ? sel.paras : sel.cursor ? [sel.cursor] : [];
    if (!paras.length) { say("서식을 입힐 문단을 먼저 고르세요 — 문단을 끌어 고르거나 커서를 두세요"); return; }
    body = { mode: "format", item: item.key, paras };
  }
  styleSay(s.id, "");
  const r = await structOp(`styles/${encodeURIComponent(s.id)}/apply`, body); // 실패는 structOp 가 알림
  if (styleLibOn()) styleLibDraw();
  if (!r) return;
  const undo = " · 도구 줄의 실행 취소로 되돌릴 수 있습니다";
  if (mode === "tableBlank") { toast(`「${s.name}」 서식의 빈 표를 넣었습니다${undo}`); if (r.made && r.made.table) setTimeout(() => slGo(r.made.table), 0); }
  else if (mode === "tableRestyle") toast(`표 ${body.table} 에 「${s.name}」 서식을 입혔습니다${undo}`);
  else toast(`문단 ${nf((r.formatted && r.formatted.paras) || body.paras.length)}개에 「${s.name} — ${item.name || item.key}」 서식을 입혔습니다${undo}`);
}

// ---- 파일에서 추출 ---------------------------------------------------------------------------------------------------------
function styleFilePick() {
  const inp = el("input");
  inp.type = "file";
  inp.accept = ".hwp,.hwpx,.docx,.pdf";
  inp.onchange = () => styleFileExtract(inp.files[0]);
  inp.click();
}
async function styleFileExtract(file) {
  if (!file || STYLE.file) return;
  if (!/\.(hwpx?|docx|pdf)$/i.test(file.name)) { toast("hwp·hwpx·docx·pdf 파일에서 추출합니다", true); return; }
  STYLE.file = { name: file.name, t0: performance.now() };
  styleLibDraw();
  const tick = setInterval(() => { const t = styleLibOn() && STYLE.file ? $("headsDlgTools").querySelector(".sl-run-text") : null; if (t) t.textContent = `「${short(STYLE.file.name, 24)}」 에서 서식을 찾는 중 · ${slSecs(STYLE.file.t0)}`; }, 1000);
  let r = null, err = null;
  try {
    const fd = new FormData();
    fd.append("file", file);
    r = await api("/api/styles/extract-file", { method: "POST", body: fd });
  } catch (e) { err = e; }
  clearInterval(tick);
  STYLE.file = null;
  if (err) { toast(`서식을 추출하지 못했습니다: ${styleErr(err)}`, true); styleLibDraw(); return; }
  styleSaveOpen({ file: { ...r, name: r.name || file.name } });
}

// ---- 추출 후보(kind "styleSave") -------------------------------------------------------------------------------------------
const styleSaveOn = () => heads.dlg === "styleSave";
const styleCandUrl = () => `/api/docs/${encodeURIComponent(state.id)}/styles/candidates`;
function styleCandName(c) { const t = oneLine(c.sample || ""); return c.name || (t ? `${t.length > 16 ? t.slice(0, 16) + "…" : t} 표` : c.rows ? `표 서식 ${c.rows}×${c.cols}` : "표 서식"); }
function styleTextName(c) { const t = c.template; return c.name || (t ? t.name || `템플릿 ${t.no || ""} 글 서식`.replace("  ", " ") : "글 서식"); }

function styleSaveFill(S, r) { // 서버가 준 후보 → 줄(고른 것·이름·띠 수는 여기서부터 화면 상태)
  S.rows = [];
  for (const c of r.tables || []) S.rows.push({ kind: "table", key: c.key, c, on: false, name: styleCandName(c), bands: c.bands ? { headerRows: 0, headerCols: 0, footRows: 0, ...c.bands } : null, blueprint: false, state: "", err: "" });
  for (const c of r.texts || []) S.rows.push({ kind: "text", key: c.key, c, on: false, name: styleTextName(c), state: "", err: "" });
  Object.assign(S, { rev: r.rev == null ? null : r.rev, stage2: r.stage2 !== false, losses: r.losses || [], call: r.call || null, loading: false, err: "" });
}
function styleSaveParas(S) { // 고른 문단을 「레벨 없는 문단 서식」 으로 — 2단계(개요템플릿)가 없으면 커서 문단 하나도 후보(spec ② §5)
  S.rows = S.rows.filter((r) => r.kind !== "paras" || r.state === "done");
  if (S.file || S.loading || S.err) return;
  const sel = slSelection(), ids = sel.paras.length ? sel.paras : !S.stage2 && sel.cursor ? [sel.cursor] : [];
  if (ids.length) S.rows.push({ kind: "paras", key: "paras", paras: ids, on: false, name: "문단 서식", state: "", err: "" });
}
function styleSavePick(S, tid, blueprint) { // 그 표 하나만 고른 채로(표 메뉴 「서식 보관함에 저장…」 · 카드 「이 표를 서식으로 저장」)
  for (const r of S.rows) r.on = false;
  let row = S.rows.find((r) => r.kind === "table" && r.c.table === tid && r.state !== "done");
  if (!row) { // 후보에 없는 표(같은 서식 묶음의 대표가 아니거나 · 후보에서 빠진 표) — 그 표로 줄을 하나 만든다(저장 끝점은 어느 표든 받는다)
    const from = S.rows.find((r) => r.kind === "table" && (r.c.same || []).includes(tid)), b = typeof xlBlock === "function" ? xlBlock(tid) : null;
    const c = from ? { ...from.c, key: `pick:${tid}`, table: tid, same: [tid], count: 1, name: "" } : { key: `pick:${tid}`, table: tid, same: [tid], count: 1, rows: b ? b.nRows : 0, cols: b ? b.nCols : 0, bands: null, sample: "" };
    row = { kind: "table", key: c.key, c, on: false, name: from ? from.name : styleCandName(c), bands: from && from.bands ? { ...from.bands } : null, blueprint: false, state: "", err: "" };
    S.rows.unshift(row);
  }
  row.on = true;
  if (blueprint) row.blueprint = true;
}

async function styleSaveOpen(opts = {}) {
  const file = opts.file || null;
  if (!file && (!state.id || state.format === "docx")) { toast("이 문서에서 추출하기는 hwpx 문서만 됩니다 — 다른 형식은 서식 보관함의 「파일에서 추출」"); return; }
  const key = file ? `file|${file.token}` : `doc|${state.id}|${state.epoch}`;
  headsDlg("styleSave", file ? `서식 추출 — ${file.name}` : "서식 추출 — 이 문서", "보관함에 저장할 서식을 고릅니다 · 문서는 안 바뀝니다");
  let S = STYLE.save;
  const fresh = !S || S.key !== key || !!S.err || (!file && !S.loading && !S.busy && S.rev !== state.serverRev); // 문서가 바뀌었으면 후보를 다시 찾는다
  if (fresh) {
    S = STYLE.save = { key, file: !!file, token: file ? file.token : null, name: file ? file.name : state.name, format: file ? file.format : "hwpx", rev: null, stage2: true, rows: [], keepText: false,
      busy: null, llm: null, call: null, losses: [], loading: !file, err: "", msg: "", msgErr: false, want: null };
    if (file) styleSaveFill(S, file);
  } else if (!S.busy) { // 같은 후보를 다시 연다 — 앞서 저장한 줄도 다시 고를 수 있게(「저장했습니다」·실패 까닭은 그 저장을 본 동안만)
    for (const r of S.rows) { r.state = ""; r.err = ""; }
    S.msg = "";
  }
  if (opts.table) S.want = { table: opts.table, blueprint: !!opts.blueprint };
  if (fresh && !file) {
    styleSaveDraw();
    try {
      await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서로 후보를 찾는다
      const r = await api(styleCandUrl(), { method: "POST", headers: H_JSON, body: JSON.stringify({ llm: false }) });
      if (STYLE.save !== S) return;
      styleSaveFill(S, r);
    } catch (e) { if (STYLE.save !== S) return; S.loading = false; S.err = styleErr(e); }
  }
  if (!S.loading && !S.err) {
    styleSaveParas(S);
    if (S.want) { styleSavePick(S, S.want.table, S.want.blueprint); S.want = null; }
  }
  if (styleSaveOn() && STYLE.save === S) styleSaveDraw(); // 읽는 동안 이 열을 다시 열었어도(차례 번호가 바뀜) 같은 후보면 그린다
}

function styleSaveDraw() {
  if (!styleSaveOn()) return;
  const S = STYLE.save, tools = $("headsDlgTools"), body = $("headsDlgBody"), foot = $("headsDlgFoot"), keep = body.scrollTop;
  tools.textContent = "";
  body.textContent = "";
  foot.textContent = "";
  const wrap = el("div", "sl-wrap");
  body.append(wrap);
  tools.append(hBtn("‹ 보관함", () => styleLibOpen(), { title: "보관한 서식 목록으로(고른 것·이름은 이 문서를 닫기 전까지 남습니다)" }));
  if (!S) return;
  if (S.loading) { wrap.append(slRun("이 문서의 표 서식·글 서식 후보를 찾는 중…")); return; }
  if (S.err) {
    wrap.append(el("p", "hwarn fail", `후보를 찾지 못했습니다: ${S.err}`), el("div", "sl-acts"));
    wrap.lastChild.append(hBtn("다시 찾기", () => styleSaveOpen()));
    return;
  }
  const busy = !!S.busy || !!S.llm, tables = S.rows.filter((r) => r.kind === "table"), texts = S.rows.filter((r) => r.kind !== "table");
  if (!S.file) {
    const nameBtn = hBtn("이름 붙이기(LLM)", () => styleSaveName(), { disabled: busy || !S.rows.some((r) => r.kind !== "paras"), title: "후보마다 이름 · 저장할 만한지 · 띠 수 보정을 LLM 에 한 번 묻습니다(유료 — 수 초~수십 초). 문서는 안 바뀌고, 직접 고친 이름·띠 수는 그대로 둡니다" });
    nameBtn.dataset.slAct = "name";
    tools.append(nameBtn);
    if (S.llm) tools.append(slRun(`후보에 이름을 붙이는 중 — LLM · ${slSecs(S.llm.t0)}`));
    else if (S.call) tools.append(el("span", "muted", [S.call.model || "", S.call.ms != null ? `${(S.call.ms / 1000).toFixed(1)}초` : "", S.call.costUsd != null ? `$${Number(S.call.costUsd).toFixed(3)}` : ""].filter(Boolean).join(" · ")));
  }
  const save = hBtn("", () => styleSaveRun(), { cls: "btn sm primary", title: "고른 서식을 차례로 보관함에 저장합니다 — 저장하면 PDF 검증이 뒤에서 시작됩니다" }), count = el("span", "muted");
  save.dataset.slAct = "save";
  const sync = () => {
    const n = S.rows.filter((r) => r.on && r.state !== "done").length;
    save.textContent = `고른 ${nf(n)}개 저장`;
    save.disabled = !n || !!S.busy || !!S.llm;
    count.textContent = `${nf(n)} / ${nf(S.rows.filter((r) => r.state !== "done").length)}`;
  };
  // 옵션 — 자료값(글)을 그대로 둘지. 파일에서 추출한 것은 서버가 명세로 다시 짓는다(이 옵션 없음)
  if (!S.file) {
    const opts = el("div", "sl-opts"), lab = el("label", "sl-opt"), cb = el("input");
    cb.type = "checkbox"; cb.checked = S.keepText; cb.disabled = busy;
    cb.onchange = () => { S.keepText = cb.checked; };
    lab.append(cb, el("span", null, "글도 그대로 저장"));
    lab.dataset.slOpt = "keepText";
    opts.append(lab, hHelp("글도 그대로 저장 안내", SL_KEEP_HELP));
    wrap.append(opts);
  } else if (S.losses.length) wrap.append(el("p", "sl-msg", `이 파일에서 옮기지 못하는 것 — ${S.losses.join(" · ")}`));
  if (S.msg) wrap.append(el("p", "sl-msg" + (S.msgErr ? " err" : ""), S.msg));
  if (!S.rows.length) {
    wrap.append(el("p", "hnote", S.file ? "이 파일에서 서식 후보를 찾지 못했습니다." : "이 문서에서 서식 후보를 찾지 못했습니다 — 표가 없거나(1칸 표·「작성 요령」 표는 뺍니다), 글 서식은 헤딩 2단계(개요템플릿) 결과가 있어야 나옵니다."));
  }
  if (tables.length) {
    const sec = el("div", "sl-sec", `표 서식 후보 ${nf(tables.length)}`);
    sec.title = "띠 수와 구역별 음영·글꼴·괘선이 같은 표를 한 후보로 묶었습니다(대표 = 문서 순 첫 표)";
    wrap.append(sec);
    for (const row of tables) wrap.append(styleCandEl(S, row, sync));
  }
  if (texts.length || (!S.file && !S.stage2)) {
    wrap.append(el("div", "sl-sec", `글 서식 후보 ${nf(texts.length)}`));
    if (!S.file && !S.stage2) wrap.append(el("p", "sl-msg", "헤딩 2단계(개요템플릿) 결과가 없어 레벨이 있는 글 서식 후보는 없습니다 — 문단을 끌어 고르고(또는 커서를 두고) 이 열을 다시 열면 「문단 서식」 으로 저장할 수 있습니다."));
    for (const row of texts) wrap.append(styleCandEl(S, row, sync));
  }
  foot.append(save, count);
  if (S.busy) foot.append(slRun(`저장 중 ${nf(S.busy.i)}/${nf(S.busy.n)} — ${short(S.busy.name || "", 24)}`));
  sync();
  body.scrollTop = keep;
}

function styleCandEl(S, row, sync) {
  const done = row.state === "done", busy = !!S.busy || !!S.llm, c = row.c || {};
  const box = el("div", "sl-cand" + (done ? " done" : "")), line = el("div", "sl-crow"), cb = el("input"), name = el("input", "sl-cname"), meta = el("div", "sl-cmeta");
  box.dataset.cand = row.key;
  box.dataset.kind = row.kind;
  cb.type = "checkbox"; cb.checked = row.on && !done; cb.disabled = done || busy;
  cb.setAttribute("aria-label", `${row.name || "서식"} — 저장할 것으로 고르기`);
  cb.onchange = () => { row.on = cb.checked; sync(); };
  name.type = "text"; name.maxLength = 60; name.value = row.name; name.placeholder = "서식 이름"; name.disabled = done || busy;
  name.setAttribute("aria-label", "서식 이름");
  name.oninput = () => { row.name = name.value; row.named = true; };
  line.append(cb, name);
  const goId = row.kind === "table" ? c.table : row.kind === "text" ? ((c.items || [])[0] || {}).para : (row.paras || [])[0];
  if (!S.file && goId) line.append(hBtn("자리로", () => slGo(goId), { title: "문서에서 그 자리로(열은 그대로)" }));
  if (row.kind === "table") {
    if (c.rows) meta.append(el("span", null, `${c.rows}×${c.cols}`));
    for (const [k, label, title] of SL_BANDS) { // 띠 수 — 구역마다 그 서식을 따로 저장한다(비워 두면 서버가 판정)
      const l = el("label", "sl-num", label), i = el("input");
      i.type = "number"; i.min = "0"; i.max = String(Math.max(0, (k === "headerCols" ? c.cols : c.rows) || 99)); i.value = row.bands ? String(row.bands[k] || 0) : ""; i.placeholder = "–"; i.disabled = done || busy;
      i.title = `${title}${row.bands ? "" : " — 비워 두면 자동 판정"}`;
      i.dataset.band = k;
      i.onchange = () => {
        const v = Math.max(0, Math.min(Number(i.max), parseInt(i.value, 10) || 0));
        row.bands = { headerRows: 0, headerCols: 0, footRows: 0, ...(row.bands || {}), [k]: v };
        row.banded = true;
        for (const x of meta.querySelectorAll("input[data-band]")) x.value = String(row.bands[x.dataset.band] || 0);
      };
      l.append(i);
      meta.append(l);
    }
    if ((c.count || 1) > 1) { const n = el("span", null, `같은 서식 ${nf(c.count)}개`); n.title = `이 서식을 쓰는 표 — ${(c.same || []).slice(0, 12).join(" · ")}${(c.same || []).length > 12 ? " …" : ""}`; meta.append(n); }
    if (c.page) meta.append(el("span", null, `${c.page}쪽`));
    if (c.keep) { const k = el("span", "hb het", "추천"); k.title = "LLM 이 저장할 만하다고 본 후보"; meta.append(k); }
    if (!S.file) {
      const lab = el("label", "sl-opt"), bp = el("input");
      bp.type = "checkbox"; bp.checked = !!row.blueprint; bp.disabled = done || busy;
      bp.onchange = () => { row.blueprint = bp.checked; };
      lab.dataset.slOpt = "blueprint";
      lab.title = "머리 글·칸 구성까지 저장합니다 — 보관함에서 「빈 표 넣기」 로 같은 구조의 빈 표를 다시 씁니다(채우는 칸·계산 칸은 비워서)";
      lab.append(bp, el("span", null, "구조까지 저장"));
      meta.append(lab);
    }
    if (c.sample && !/^pick:/.test(row.key)) { const s = el("span", "sl-sample", `「${oneLine(c.sample)}」`); s.title = "첫 칸 글"; meta.append(s); }
  } else if (row.kind === "text") {
    const t = c.template, items = c.items || [];
    if (t) meta.append(el("span", null, `템플릿 ${t.no != null ? `T${t.no}` : t.name || ""}`));
    meta.append(el("span", null, `레벨 ${nf(items.length)}`));
    const chain = (t && t.chain) || items.map((it) => it.letter).filter(Boolean);
    if (chain && chain.length) { const s = el("span", "sl-sample", (Array.isArray(chain) ? chain : [chain]).join(" › ")); s.title = "레벨마다의 레터"; meta.append(s); }
    if (c.keep) { const k = el("span", "hb het", "추천"); k.title = "LLM 이 저장할 만하다고 본 후보"; meta.append(k); }
  } else meta.append(el("span", null, `고른 문단 ${nf(row.paras.length)}개 — 레벨 없는 문단 서식(서식이 같은 문단은 하나로)`));
  box.append(line, meta);
  const st = el("p", "sl-cstate" + (row.err ? " err" : ""), row.err ? `저장하지 못했습니다: ${row.err}` : done ? "보관함에 저장했습니다" : "");
  box.append(st);
  if (!S.file) { // 줄에 올리면 문서의 그 표·문단(같은 서식 표 모두)
    const ids = row.kind === "table" ? c.same || [c.table] : row.kind === "text" ? (c.items || []).map((it) => it.para) : row.paras;
    box.addEventListener("mouseenter", () => slHit(ids.slice(0, 40)));
    box.addEventListener("mouseleave", () => slHit(null));
  }
  return box;
}

async function styleSaveName() { // 이름 붙이기(LLM — 누를 때만): 후보마다 이름 · 저장할 만한가 · 띠 수 보정. 직접 고친 이름·띠 수는 안 덮는다
  const S = STYLE.save;
  if (!S || S.file || S.llm || S.busy) return;
  S.llm = { t0: performance.now() };
  S.msg = "";
  styleSaveDraw();
  const tick = setInterval(() => { const t = styleSaveOn() && STYLE.save === S && S.llm ? $("headsDlgTools").querySelector(".sl-run-text") : null; if (t) t.textContent = `후보에 이름을 붙이는 중 — LLM · ${slSecs(S.llm.t0)}`; }, 1000);
  try {
    await flushAll();
    const r = await api(styleCandUrl(), { method: "POST", headers: H_JSON, body: JSON.stringify({ llm: true }) });
    const by = new Map([...(r.tables || []), ...(r.texts || [])].map((c) => [c.key, c]));
    let n = 0;
    for (const row of S.rows) {
      const c = by.get(row.key);
      if (!c || row.state === "done") continue;
      if (c.name && !row.named) { row.name = c.name; n += 1; }
      if (c.bands && row.kind === "table" && !row.banded) row.bands = { headerRows: 0, headerCols: 0, footRows: 0, ...c.bands };
      row.c = { ...row.c, keep: !!c.keep };
    }
    S.call = r.call || null;
    S.msg = `이름 ${nf(n)}개를 붙였습니다 — 「추천」 표가 붙은 후보가 저장할 만한 것입니다(고르는 것은 직접).`;
    S.msgErr = false;
  } catch (e) { S.msg = `이름을 붙이지 못했습니다: ${styleErr(e)}`; S.msgErr = true; }
  clearInterval(tick);
  S.llm = null;
  if (STYLE.save === S) styleSaveDraw();
}

async function styleSaveRun() { // 고른 것을 차례로 저장 — 줄마다 결과를 남기고, 모두 되면 보관함 목록으로
  const S = STYLE.save;
  if (!S || S.busy || S.llm) return;
  const todo = S.rows.filter((r) => r.on && r.state !== "done");
  if (!todo.length) return;
  const docId = state.id, epoch = state.epoch, named = (row) => { const n = (row.name || "").trim().replace(/\s+/g, " ").slice(0, 60); return n ? { name: n } : {}; };
  const made = [];
  let failed = 0;
  S.busy = { i: 0, n: todo.length, name: "" };
  S.msg = "";
  if (S.file) {
    S.busy.i = todo.length;
    S.busy.name = S.name;
    styleSaveDraw();
    try {
      const r = await api("/api/styles/from-file", { method: "POST", headers: H_JSON,
        body: JSON.stringify({ token: S.token, picks: todo.map((row) => ({ kind: row.kind, key: row.key, ...named(row), ...(row.kind === "table" && row.bands ? { bands: row.bands } : {}) })) }) });
      made.push(...(r.styles || []));
      for (const row of todo) { row.state = "done"; row.on = false; row.err = ""; }
    } catch (e) {
      failed = todo.length;
      S.msg = e.status === 410 ? "올린 파일을 서버가 잊었습니다(30분이 지남) — 서식 보관함의 「파일에서 추출」 로 다시 올리세요." : `저장하지 못했습니다: ${styleErr(e)}`;
      S.msgErr = true;
    }
  } else {
    for (const row of todo) {
      if (epoch !== state.epoch) break; // 그 사이 다른 문서 — 멈춘다
      S.busy.i += 1;
      S.busy.name = row.name;
      styleSaveDraw();
      const body = row.kind === "table" ? { kind: "table", table: row.c.table, ...(row.bands ? { bands: row.bands } : {}), keepText: S.keepText, blueprint: !!row.blueprint }
        : row.kind === "text" && row.c.template ? { kind: "text", template: row.c.template.id, keepText: S.keepText }
          : { kind: "text", paras: row.kind === "text" ? (row.c.items || []).map((it) => it.para).filter(Boolean) : row.paras, keepText: S.keepText };
      try {
        made.push(await api(`/api/docs/${encodeURIComponent(docId)}/styles`, { method: "POST", headers: H_JSON, body: JSON.stringify({ ...body, ...named(row) }) }));
        row.state = "done"; row.on = false; row.err = "";
      } catch (e) { failed += 1; row.err = styleErr(e); }
    }
  }
  S.busy = null;
  if (made.length) { STYLE.list = null; styleChanged(); } // 목록은 다음에 열 때 다시 읽는다
  if (made.length && !failed) {
    toast(`서식 ${nf(made.length)}개를 보관함에 저장했습니다 — PDF 검증이 뒤에서 돕니다`);
    if (styleSaveOn() && STYLE.save === S) { styleLibOpen(made[0].kind === "text" ? "text" : "table"); return; }
  } else if (made.length) toast(`서식 ${nf(made.length)}개를 저장했습니다 · ${nf(failed)}개는 저장하지 못했습니다(줄마다 까닭)`, true);
  if (STYLE.save === S) styleSaveDraw();
}
