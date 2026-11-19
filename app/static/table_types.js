"use strict";
// 양식의 표 판정 — 확정 · 상태 보기(spec_테이블매니저 ② §10 「양식의 표 판정」) — 표 메뉴 「양식의 표 판정…」 → 문서 옆 2열(kind tblType) · 「테이블」 탭의 상태 표지.
// 사용자 2026-11-19 "사업계획서나 연차보고서 같은 경우는 형식이 동일 하니깐 테이블 정보를 가지고 있어도 좋을거 같긴한데" → 사람이 표 전체의 판정을 **한 번 확정**해 양식에 저장하고,
// 구조가 꼭 같은 표(모든 칸의 자리 · 병합 · 음영 + 고정 머리글의 글)를 만나면 내용으로 다시 어림하지 않고 그것을 쓴다(값을 채워도 칸 역할 · 키가 안 흔들린다). 저절로 배우지 않는다.
// 2열(문서 옆 열 — 팝업 아님):
//   양식 이름 · 이 표의 상태(「확정됨」 · 「확정 안 됨」 · 「구조가 달라 안 맞음」 · 「같은 구조가 둘 이상」)
//   지금 판정의 격자(역할마다 색 — 「표 구조」 격자(table.hgrid)와 같은 색 · 칸에 올리면 문서의 그 칸 표시 · 누르면 그 칸으로)
//   확정본과 다른 칸(확정본이 없었다면 다르게 읽었을 칸 — 「초안은 행헤더 · 확정본은 필드」)
//   가변 머리글 고르기(문서마다 글이 달라도 되는 머리 칸 — 기관 이름 · 연도 · 차수 · 사람이 채우는 머리 칸: 체크 안 한 머리글은 글이 꼭 같아야 맞는다)
//   「이 판정으로 확정」 · 「확정하고 다음 표」(이 문서에서 확정 안 된 다음 표로) · 이 타입의 확정본 목록(지우기 — 알림의 「되돌리기」 로 되살린다: 확인 창을 쓰지 않는다 · 되살리기는 id 만 보낸다)
//   같이 쓰이는 표(2026-11-19 astra 4차): 확정본이 이 문서의 다른 표에도 맞아 쓰이면 요약 줄 아래에 「이 문서의 다른 표 n개에도 이 판정이 쓰입니다 — t45: 지금 판정과 2칸 다름(확인)」 — 표 번호를 누르면 그 표의 판정 화면.
//   고치기와 따로 확정: 이 표에 쓰이는 확정본과 지금 판정(헤더 지정 · 가변 체크를 얹은 것)이 다르면 단추가 「이 확정본 고치기」(그 확정본이 맞는 모든 표가 바뀐다 — 이 문서에서 몇 표인지 보인다) ·
//     「이 표만 따로 확정」(새 확정본 — 이 표에만 있는, 글이 있는 고정 머리글이 있을 때만 켜진다: 없으면 따로 확정해도 이 표에 안 쓰인다 · 까닭은 풍선 도움말) 둘로 바뀐다.
// 역할은 이 화면에서 고치지 않는다 — 표 칸을 골라 「헤더 지정」 으로 고친 뒤 확정한다. 확정은 문서를 바꾸지 않는다(실행 취소와 무관).
// 양식이 정해지지 않은 문서에서는 열을 열지 않고 알린다(「양식 정보」 에서 양식을 고른다). docx 에는 없다.
// app.js 가 주는 것: state·heads·el·api·toast·flushAll·headsDlg·hBtn·hFoot·nf·H_JSON·oneLine·fmtWhen·divFormOpen. tables.js: xlBlock·xlBlocks·XL_ROLE. 전역 이름은 tblType…·TTY_… 만 쓴다.
// 서버 짝: app/table_types_api.py(`GET/PUT …/tables/{tid}/type` · `GET …/tables/types` · `DELETE /api/table-types/{id}` · `POST /api/table-types/restore`) · 견주기 · 저장 app/table_types.py.
// index.html 이 table_kv.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TTY_STATE = { confirmed: "확정됨", none: "확정 안 됨", changed: "구조가 달라 안 맞음", ambiguous: "같은 구조가 둘 이상" };
const TTY_BY = { user: "이 작업의 헤더 지정", template: "양식의 확정본", stage3: "표 구조 결과", draft: "초안" }; // 칸의 역할이 어디서 왔나
const TTY_SRC = { template: "양식의 확정본", stage3: "표 구조 결과", draft: "초안(내용으로 어림)" };
const TTY_ROLE = { colhead: "열헤더", rowhead: "행헤더", corner: "귀퉁이", field: "필드", title: "제목", note: "안내", spacer: "간격" };
const TTY_NO_FORM = "양식이 정해지지 않은 문서입니다 — 양식 정보에서 양식을 고르세요";
const TTY_TEXT = 24; // 격자 · 목록에 보이는 칸 글의 길이
// map = Map(표 id → {type, state}) | null(양식 없음 · 못 읽음) · key = 읽은 것의 열쇠(문서) · wait = 읽는 중인 열쇠 · form = 그 문서의 양식 {key, name} | null
const tblTypes = { key: null, map: null, form: null, wait: null };
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tableType: "양식의 표 판정 확정" }); // 「기록」 탭의 이름

const tblTypeUrl = (tid) => `/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/type`;
const tblTypeCut = (s, n = TTY_TEXT) => { const t = oneLine(s); return t.length > n ? `${t.slice(0, n)}…` : t; };
const tblTypeErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「양식의 표 판정」 을 쓸 수 있습니다" : e.message);
const tblTypeRole = (r) => TTY_ROLE[r] || r;

function tblTypeHit(cid = null) { // 격자 · 목록의 칸에 올린 동안 문서의 그 칸을 칠한다(null = 걷기) — td.tty-hit(table_types.css)
  for (const e of document.querySelectorAll("#doc td.tty-hit")) e.classList.remove("tty-hit");
  if (cid) for (const e of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(cid)}"]`)) e.classList.add("tty-hit");
}
function tblTypeGo(tid, cid = null) { // 문서에서 그 칸(없으면 표)으로 — 열은 그대로(나란히 보기)
  const target = (cid && document.querySelector(`#doc td[data-cell="${CSS.escape(cid)}"]`)) || document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`);
  if (!target) { toast("그 표가 지금 화면에 없습니다"); return; }
  target.scrollIntoView({ block: cid ? "center" : "start", behavior: scrollHow() });
}

// ---- 「테이블」 탭의 상태 표지 — 확정된 표에만 「확정됨」(확정 안 된 표 · 양식이 없는 문서에는 아무것도 없다) -------------------------------------------
const tblTypesKey = () => `${state.id}|${state.epoch}`;
function tblTypesReset() { tblTypes.key = tblTypes.map = tblTypes.form = tblTypes.wait = null; } // 문서를 열거나 닫을 때(tables.js tablesReset)
function tblTypesLoad(force = false) { // 탭을 열 때(force) · 확정하거나 지운 뒤(force) → Promise(읽은 Map | null). 읽지 못해도 알리지 않는다(표지가 안 보일 뿐)
  if (!state.id || state.format === "docx") return Promise.resolve(null);
  const key = tblTypesKey();
  if (!force && tblTypes.key === key) return Promise.resolve(tblTypes.map);
  tblTypes.wait = key;
  return api(`/api/docs/${encodeURIComponent(state.id)}/tables/types`).catch(() => null).then((v) => {
    if (key !== tblTypesKey()) return null; // 그 사이 다른 문서를 열었다
    if (tblTypes.wait === key) tblTypes.wait = null;
    tblTypes.key = key;
    tblTypes.form = (v && v.form) || null;
    tblTypes.map = v && v.form && Array.isArray(v.tables) ? new Map(v.tables.map((t) => [t.table, t])) : null;
    tblTypesFill();
    return tblTypes.map;
  });
}
function tblTypeTags(tid) { // 표 하나의 표지 — 확정된 표에만
  const t = tblTypes.map && tblTypes.key === tblTypesKey() ? tblTypes.map.get(tid) : null;
  if (!t || t.state !== "confirmed") return [];
  const tag = el("span", "tp-tag tp-type", TTY_STATE.confirmed);
  tag.dataset.state = t.state;
  tag.title = `양식 「${(tblTypes.form && tblTypes.form.name) || ""}」 의 확정본으로 칸 역할을 읽습니다 — 값을 채워도 역할이 바뀌지 않습니다\n표 메뉴 「양식의 표 판정…」 에서 보고 고칩니다`;
  return [tag];
}
function tblTypesFill() { // 그려 둔 표 목록의 표지 자리(.tp-types)만 다시 채운다 — 목록을 통째로 다시 그리지 않는다(스크롤 · 초점 그대로)
  for (const slot of document.querySelectorAll("#tablesBox .tp-row .tp-types")) {
    const row = slot.closest(".tp-row");
    slot.replaceChildren(...tblTypeTags(row && row.dataset.tableId));
  }
}

// ---- 2열 「양식의 표 판정」 ---------------------------------------------------------------------------------------------
async function tblTypeView(tid) {
  if (!state.id) return;
  if (state.format === "docx") { toast("양식의 표 판정은 지금 hwpx 문서만 됩니다"); return; }
  if (typeof xlBlock === "function" && !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const id0 = state.id, epoch = state.epoch;
  let first;
  try {
    await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서의 칸 글로 읽는다
    first = await api(tblTypeUrl(tid));
  } catch (e) { toast(`양식의 표 판정을 읽지 못했습니다: ${tblTypeErr(e)}`, true); return; }
  if (id0 !== state.id || epoch !== state.epoch) return;
  if (!first.form) { // 양식이 정해지지 않은 문서 — 열을 열지 않고 알린다(양식은 「양식 정보」 에서 고른다)
    toast(TTY_NO_FORM, false, typeof divFormOpen === "function" ? { label: "양식 정보", run: () => divFormOpen() } : null);
    return;
  }
  const { tools, body } = headsDlg("tblType", `양식의 표 판정 · ${tid}`, "한 번 확정한 표 판정을 양식에 저장해 두고, 구조가 꼭 같은 표에 다시 씁니다 — 값을 채워도 칸 역할이 바뀌지 않습니다");
  const seq = heads.seq;
  const live = () => seq === heads.seq && epoch === state.epoch;
  const wrap = el("div", "ta-wrap tty-wrap");
  body.append(wrap);
  tools.append(el("span", "muted", "확정은 문서를 바꾸지 않습니다 · 역할을 고치려면 표 칸을 골라 「헤더 지정」 으로 고친 뒤 확정합니다 · 구조가 다른 표에는 쓰지 않습니다"));
  const ident = el("div", "ta-ident"), acts = el("div", "ta-row"), heldLine = el("p", "hnote tty-held"), sum = el("p", "hnote tty-sum"), alsoLine = el("p", "hnote tty-also");
  const gridBox = el("section", "tty-grid"), diffBox = el("details", "hblock tty-diff"), varBox = el("details", "hblock tty-var"), bar = el("div", "ta-row tty-bar"), barNote = el("p", "hnote tty-barnote");
  const listBox = el("details", "hblock tty-variants");
  heldLine.hidden = true;
  alsoLine.hidden = true;
  barNote.hidden = true;
  acts.append(hBtn("표 자리로", () => tblTypeGo(tid), { title: "문서에서 이 표로" }), hBtn("다시 읽기", () => load(), { title: "지금 문서 · 지금 저장된 확정본으로 다시 읽습니다(문서는 안 바뀜)" }));
  wrap.append(ident, acts, heldLine, sum, alsoLine, gridBox, diffBox, varBox, bar, barNote, listBox);
  let view = null, busy = false, picked = new Set(), touched = false; // picked = 가변으로 둘 머리 칸 id · touched = 사람이 체크를 바꿨다(다시 읽어도 지킨다)
  const cellOf = (cid) => view.judgment.cells.find((c) => c.id === cid);
  const hover = (node, cid) => { node.addEventListener("mouseenter", () => tblTypeHit(cid)); node.addEventListener("mouseleave", () => tblTypeHit()); };
  const textOf = (c) => (c.text ? `「${tblTypeCut(c.text)}」` : "(빈 칸)");

  function take(r) { // 응답을 받아 그린다 — 가변 머리글의 체크는 사람이 바꾼 것이 있으면 지금 머리 칸인 것만 남기고, 없으면 서버가 준 기본으로
    view = r;
    const labels = new Set(r.judgment.cells.filter((c) => c.label).map((c) => c.id));
    picked = touched ? new Set([...picked].filter((id) => labels.has(id))) : new Set(r.judgment.cells.filter((c) => c.variable).map((c) => c.id));
    draw();
  }
  async function load() {
    hFoot("읽는 중…", false);
    try {
      await flushAll();
      const r = await api(tblTypeUrl(tid));
      if (!live()) return;
      take(r);
      hFoot("", false);
    } catch (e) {
      if (!live()) return;
      sum.textContent = `읽지 못했습니다: ${tblTypeErr(e)}`;
      hFoot(sum.textContent);
    }
  }

  function draw() {
    const r = view, j = r.judgment, held = r.held || [], m = r.match;
    const stateTag = el("span", "hb tty-state", TTY_STATE[r.state] || r.state), formTag = el("span", "hb", `양식 ${r.form ? r.form.name : "없음"}`);
    stateTag.dataset.state = r.state;
    formTag.title = "이 문서의 양식(「양식 정보」 에서 고른 것 · 올린 원본 · 파일 이름으로 정해집니다) — 확정본은 이 양식의 문서에서만 씁니다";
    ident.replaceChildren(el("b", null, tid), el("span", null, `${j.rows}×${j.cols}`), formTag, stateTag);
    if (r.name) ident.append(el("span", "muted tty-name", tblTypeCut(r.name, 40)));
    heldLine.hidden = !held.length;
    heldLine.replaceChildren();
    if (held.length) { // 지금 표와 안 맞는 헤더 지정 — 확정하지 못한다(서버도 409)
      heldLine.append(`헤더 지정 ${nf(held.length)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요`);
      heldLine.title = "지정한 뒤 그 칸의 자리나 글이 바뀐 헤더 지정입니다 — 어느 칸의 지정인지 분명하지 않아 판정에 쓰지 않았습니다\n이런 지정이 있는 동안은 확정하지 않습니다";
      hover(heldLine, held[0].cell);
    }
    const src = TTY_SRC[j.source] || j.source;
    sum.textContent = r.state === "confirmed" ? `확정됨 — 이 표는 양식의 확정본(판 ${nf(m.rev)}${m.at ? ` · ${fmtWhen(m.at)} 확정` : ""})으로 읽습니다`
      : r.state === "ambiguous" ? `같은 구조가 둘 이상 — 이 표에 맞는 확정본이 ${nf(r.variants.filter((v) => v.fits).length)}개라 어느 쪽도 쓰지 않습니다(지금 판정: ${src})`
      : r.state === "changed" ? `구조가 달라 안 맞음 — 같은 타입의 확정본이 있지만 이 표와 구조나 머리글이 다릅니다(지금 판정: ${src})`
      : `확정 안 됨 — 지금 판정: ${src}`;
    sum.title = "확정됨 = 이 양식에 저장된 확정본 가운데 이 표와 구조가 꼭 같은 것이 하나 있다(모든 칸의 자리 · 병합 · 음영 + 고정 머리글의 글)\n"
      + "구조가 달라 안 맞음 = 행이 늘었거나 병합 · 머리글이 달라졌다 — 그때는 전처럼 표 구조 결과 · 초안으로 읽는다\n"
      + "맞는 확정본이 여럿이면 고정 머리글이 더 많이 맞은 것(다른 것들의 고정 머리글을 다 품은 것)을 쓴다\n같은 구조가 둘 이상 = 그런 것이 없다 — 안 쓰는 것을 아래 목록에서 지우면 남은 하나를 쓴다";
    drawAlso();
    drawGrid();
    drawDiff();
    drawVar();
    drawBar();
    drawList();
  }

  function drawAlso() { // 같이 쓰이는 표 — 이 확정본이 이 문서의 다른 표에도 맞아 쓰인다: 표마다 그 표의 지금 판정(확정본 없이 낸 것)과 다른 칸 수 · 누르면 그 표의 판정 화면
    const also = (view.match && view.also) || [];
    alsoLine.hidden = !also.length;
    alsoLine.replaceChildren();
    if (!also.length) return;
    alsoLine.append(`이 문서의 다른 표 ${nf(also.length)}개에도 이 판정이 쓰입니다 — `);
    also.slice(0, 8).forEach((t, i) => {
      const go = el("button", "hlink", t.table);
      go.type = "button";
      go.title = "이 표의 판정 화면으로 — 이 표의 판정이 따로여야 하면 그 표에서 헤더 지정으로 고친 뒤 「이 표만 따로 확정」 을 누르세요";
      go.onclick = () => { tblTypeGo(t.table); tblTypeView(t.table); };
      alsoLine.append(i ? " · " : "", go, t.differs ? el("span", "tty-warn", `: 지금 판정과 ${nf(t.differs)}칸 다름(확인)`) : ": 지금 판정과 같음");
    });
    if (also.length > 8) alsoLine.append(` 밖에 ${nf(also.length - 8)}개`);
    alsoLine.title = "같은 양식의 확정본은 구조가 꼭 같은 표(모든 칸의 자리 · 병합 · 음영 + 고정 머리글의 글)에 모두 쓰입니다\n"
      + "「지금 판정과 n칸 다름」 = 그 표를 확정본 없이 읽으면(표 구조 결과 · 초안) 역할이 다른 칸 — 값을 채워 초안이 흔들린 것일 수도, 그 표의 판정이 따로여야 하는 것일 수도 있습니다(확인)";
  }

  // 그 표에 맞아 쓰이는 확정본이 있을 때 — 지금 판정(헤더 지정 · 가변 체크를 얹은 것)이 그 확정본과 다른가 · 「이 표만 따로 확정」 을 할 수 있는가(서버 table_types.same_judgment · separable 과 같은 규칙)
  function changed() {
    return !!view.match && view.judgment.cells.some((c) => (c.auto && c.role !== c.auto) || (c.label && picked.has(c.id) !== !!c.variable));
  }
  function apartWhy() { // "" = 따로 확정할 수 있다 · 아니면 못 하는 까닭
    const cells = view.judgment.cells, mine = cells.filter((c) => c.label && !picked.has(c.id)), ids = new Set(mine.map((c) => c.id)), theirs = cells.filter((c) => c.fixed);
    if (!theirs.every((c) => ids.has(c.id)) || mine.length <= theirs.length)
      return "이 표에만 있는 고정 머리글이 없습니다 — 따로 확정해도 이 표에는 지금 확정본이 쓰입니다\n이 표에만 있는 머리 칸을 헤더 지정으로 헤더로 만든 뒤 따로 확정하거나, 「이 확정본 고치기」 를 쓰세요";
    if (!mine.some((c) => !c.fixed && oneLine(c.text)))
      return "이 표에만 있는 고정 머리글이 빈 칸뿐입니다 — 따로 확정하면 그 자리가 빈 다른 표까지 새 확정본으로 읽힙니다(글이 있는 머리 칸이 있어야 합니다)";
    return "";
  }

  function drawGrid() { // 지금 판정 — 「표 구조」 격자와 같은 꼴(table.hgrid · 역할마다 같은 색)
    const j = view.judgment, diff = new Set((view.differs || []).map((d) => d.cell));
    const head = el("div", "tty-h"), legend = el("span", "hlegend");
    for (const role of ["colhead", "rowhead", "corner", "field", "title", "note", "spacer"]) legend.append(el("span", role, TTY_ROLE[role]));
    head.append(el("h3", null, "지금 판정"), legend);
    const marks = el("p", "hnote tty-marks", "굵은 테두리 = 이 작업의 헤더 지정 · 점선 테두리 = 가변 머리글 · 주황 테두리 = 확정본이 없었다면 다르게 읽었을 칸");
    const occ = new Map();
    for (const c of j.cells) for (let r = c.row; r < c.row + c.rs; r += 1) for (let k = c.col; k < c.col + c.cs; k += 1) if (!occ.has(`${r},${k}`)) occ.set(`${r},${k}`, c);
    const subs = j.subs || [];
    const onTop = (r, k) => subs.some((s) => s.rows[0] > 0 && s.rows[0] === r && s.cols[0] <= k && k < s.cols[1]);
    const onLeft = (r, k) => subs.some((s) => s.cols[0] > 0 && s.cols[0] === k && s.rows[0] <= r && r < s.rows[1]);
    const table = el("table", "hgrid");
    table.setAttribute("aria-label", `${tid} 지금 판정의 칸 역할 격자`);
    for (let r = 0; r < j.rows; r += 1) {
      const tr = el("tr");
      for (let k = 0; k < j.cols; k += 1) {
        const c = occ.get(`${r},${k}`);
        if (!c) { tr.append(el("td", "none")); continue; }
        if (c.row !== r || c.col !== k) continue;
        const td = el("td", `${c.role}${onTop(r, k) ? " sb-top" : ""}${onLeft(r, k) ? " sb-left" : ""}${c.by === "user" ? " tty-user" : ""}${picked.has(c.id) && c.label ? " tty-varcell" : ""}${diff.has(c.id) ? " tty-differs" : ""} go`,
          tblTypeCut(c.text));
        if (c.rs > 1) td.rowSpan = c.rs;
        if (c.cs > 1) td.colSpan = c.cs;
        td.dataset.cell = c.id;
        td.title = [`${c.ref} · ${tblTypeRole(c.role)} · ${TTY_BY[c.by] || c.by}${c.by === "user" && c.auto && c.auto !== c.role ? `(지정 전 ${tblTypeRole(c.auto)})` : ""}`
          + `${c.shaded ? " · 음영" : ""}${picked.has(c.id) && c.label ? " · 가변 머리글" : ""}`, oneLine(c.text)].filter(Boolean).join("\n");
        td.tabIndex = 0;
        td.onclick = () => tblTypeGo(tid, c.id);
        td.onkeydown = (e) => { if (e.key === "Enter") tblTypeGo(tid, c.id); };
        hover(td, c.id);
        tr.append(td);
      }
      table.append(tr);
    }
    const scroll = el("div", "hgrid-scroll");
    scroll.append(table);
    gridBox.replaceChildren(head, scroll, marks);
  }

  function drawDiff() { // 확정본과 다른 칸 — 확정본이 맞을 때: 확정본 없이 낸 판정(표 구조 결과 · 초안)이 다르게 읽는 칸 + 이 작업의 헤더 지정이 확정본과 다른 칸
    const r = view, ds = r.differs || [];
    const mine = r.match ? r.judgment.cells.filter((c) => c.by === "user" && c.auto && c.auto !== c.role) : [];
    diffBox.hidden = !r.match || (!ds.length && !mine.length);
    if (diffBox.hidden) { diffBox.replaceChildren(); return; }
    const s = el("summary", null), was = diffBox.open;
    s.append(el("b", null, "확정본과 다른 칸"), el("span", "muted", ` ${nf(ds.length + mine.length)}`));
    diffBox.replaceChildren(s);
    diffBox.open = was;
    const base = r.differsFrom === "stage3" ? "표 구조 결과" : "초안", baseIs = r.differsFrom === "stage3" ? "표 구조 결과는" : "초안은";
    if (ds.length) {
      diffBox.append(el("p", "hnote", `확정본이 없었다면 다르게 읽었을 칸입니다(${base} — 칸의 글로 어림한 것). 이 표에는 확정본의 역할을 씁니다.`));
      const ul = el("ul", "tty-list");
      for (const d of ds) {
        const c = cellOf(d.cell), li = el("li"), go = el("button", "hlink", d.ref);
        go.type = "button";
        go.onclick = () => tblTypeGo(tid, d.cell);
        li.append(go, " ", el("span", "tty-text", c ? textOf(c) : ""), " ", el("span", "muted", `${baseIs} ${tblTypeRole(d.now)} · 확정본은 ${tblTypeRole(d.template)}`));
        hover(li, d.cell);
        ul.append(li);
      }
      diffBox.append(ul);
    }
    if (mine.length) {
      diffBox.append(el("p", "hnote tty-warn", `이 작업의 헤더 지정 ${nf(mine.length)}칸이 확정본과 다릅니다 — 「이 판정으로 확정」 을 누르면 확정본이 이 지정대로 고쳐집니다(같은 양식의 다른 문서에도 쓰입니다).`));
      const ul = el("ul", "tty-list");
      for (const c of mine) {
        const li = el("li"), go = el("button", "hlink", c.ref);
        go.type = "button";
        go.onclick = () => tblTypeGo(tid, c.id);
        li.append(go, " ", el("span", "tty-text", textOf(c)), " ", el("span", "muted", `헤더 지정은 ${tblTypeRole(c.role)} · 확정본은 ${tblTypeRole(c.auto)}`));
        hover(li, c.id);
        ul.append(li);
      }
      diffBox.append(ul);
    }
  }

  function drawVar() { // 가변 머리글 고르기 — 헤더 · 제목 · 안내 역할의 칸 가운데 문서마다 글이 달라도 되는 것
    const labels = view.judgment.cells.filter((c) => c.label);
    const s = el("summary", null), was = varBox.open || (!varBox.childElementCount && labels.length <= 12), count = el("span", "muted");
    const recount = () => { count.textContent = ` ${nf(labels.filter((c) => picked.has(c.id)).length)} / 머리글 ${nf(labels.length)}`; };
    recount();
    s.append(el("b", null, "가변 머리글"), count);
    varBox.replaceChildren(s);
    varBox.open = was;
    varBox.append(el("p", "hnote", "체크한 머리글은 문서마다 글이 달라도 됩니다(기관 이름 · 연도 · 차수 · 사람이 채우는 머리 칸). 체크 안 한 머리글은 글이 꼭 같은 표에만 이 확정본을 씁니다 — 구분 기준의 값 머리는 처음부터 체크해 둡니다."));
    if (!labels.length) { varBox.append(el("p", "hnote", "이 판정에는 머리글 칸이 없습니다(모두 필드) — 칸의 자리 · 병합 · 음영만 견줍니다.")); return; }
    const ul = el("ul", "tty-vars");
    for (const c of labels) {
      const li = el("li"), lab = el("label"), cb = el("input");
      cb.type = "checkbox";
      cb.checked = picked.has(c.id);
      cb.disabled = busy;
      cb.value = c.id;
      cb.onchange = () => { touched = true; if (cb.checked) picked.add(c.id); else picked.delete(c.id); recount(); drawGrid(); drawBar(); }; // 목록은 다시 그리지 않는다(체크 상자의 초점 그대로) — 수 · 격자의 점선 · 확정 단추만
      lab.append(cb, el("span", "tty-ref", c.ref), el("span", "tty-text", textOf(c)), el("span", "hb", tblTypeRole(c.role)));
      if (c.basis) { const b = el("span", "hb", "구분 기준의 값"); b.title = "구분 기준의 값 머리(차년도 · 기관 · 단계 · 연도) — 문서마다 달라지는 머리글이라 처음부터 가변으로 둡니다"; lab.append(b); }
      else if (c.empty) { const b = el("span", "hb", "빈 머리 칸"); b.title = "글이 없거나 자리표시뿐인 머리 칸입니다 — 사람이 채우는 칸이면 가변으로 두세요(안 두면 채운 문서의 표에는 이 확정본을 쓰지 않습니다)"; lab.append(b); }
      li.append(lab);
      hover(li, c.id);
      ul.append(li);
    }
    varBox.append(ul);
  }

  function nextTable(map) { // 이 문서에서 확정 안 된 다음 표(문서 순 — 이 표 뒤부터, 끝이면 처음부터) | null
    const order = (typeof xlBlocks === "function" ? xlBlocks() : []).map((b) => b.id).filter((id) => map && map.has(id));
    const i = order.indexOf(tid), rest = i < 0 ? order : order.slice(i + 1).concat(order.slice(0, i));
    return rest.find((id) => map.get(id).state !== "confirmed") || null;
  }

  async function save(next, mode = null) { // 이 판정으로 확정(next = 확정하고 다음 표 · mode = "update" 이 확정본 고치기 | "new" 이 표만 따로 확정 | null 고를 것이 없음)
    if (busy || !view) return;
    busy = true;
    drawBar();
    hFoot("확정하는 중…", false);
    let done = null;
    try {
      const labels = new Set(view.judgment.cells.filter((c) => c.label).map((c) => c.id));
      const body = { rev: view.rev, match: view.match ? { id: view.match.id, rev: view.match.rev } : null, variable: [...picked].filter((id) => labels.has(id)) };
      if (mode) body.mode = mode;
      done = await api(tblTypeUrl(tid), { method: "PUT", headers: H_JSON, body: JSON.stringify(body) });
    } catch (e) {
      busy = false;
      if (!live()) return;
      toast(e.status === 409 ? `${tblTypeErr(e)}` : `확정하지 못했습니다: ${tblTypeErr(e)}`, true);
      if (e.status === 409) await load(); else { drawBar(); hFoot("", false); }
      return;
    }
    busy = false;
    if (!live()) return;
    touched = false;
    take(done);
    hFoot("", false);
    const over = (done.saved.overlaps || []).length; // 격자가 같고 고정 머리글이 어긋나지 않는 다른 확정본 — 둘 다 맞는 표에는 어느 쪽도 안 쓰인다(지울지는 사람이 정한다)
    const also = (done.also || []).length, odd = (done.also || []).filter((t) => t.differs).length; // 같이 쓰이는 표 — 다른 칸이 있는 표는 사람이 본다(요약 줄 아래에 표마다)
    toast((mode === "new" ? "이 표만 따로 확정했습니다 — 지금까지 쓰던 확정본은 그대로입니다" : done.saved.created ? "확정했습니다 — 이 양식의 문서에서 구조가 꼭 같은 표에 이 판정을 씁니다" : `확정본을 고쳤습니다(판 ${nf(done.saved.rev)})`)
      + (also ? ` · 이 문서의 다른 표 ${nf(also)}개에도 쓰입니다${odd ? `(지금 판정과 다른 표 ${nf(odd)}개 — 확인)` : ""}` : "")
      + (over ? ` · 같은 구조의 다른 확정본 ${nf(over)}개와 함께 맞는 표에는 어느 쪽도 쓰지 않습니다 — 안 쓰는 확정본은 「이 타입의 확정본」 에서 지우세요` : ""), false);
    if (over) listBox.open = true;
    const map = await tblTypesLoad(true); // 「테이블」 탭의 표지도 다시
    if (!next || !live()) return;
    const to = nextTable(map);
    if (!to) { toast("이 문서에 확정 안 된 표가 더 없습니다"); return; }
    tblTypeGo(to);
    tblTypeView(to);
  }

  function drawBar() {
    const r = view, held = (r.held || []).length, amb = r.state === "ambiguous";
    const why = held ? "지금 표와 안 맞는 헤더 지정이 있어 확정하지 못합니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요"
      : amb ? "이 표에 맞는 확정본이 둘 이상입니다 — 아래 목록에서 안 쓰는 확정본을 지운 뒤 확정하세요"
      : r.match ? `지금 판정으로 확정본을 고칩니다(판 ${nf(r.match.rev)} → ${nf(r.match.rev + 1)}) — 같은 양식의 구조가 꼭 같은 표에 쓰입니다(문서는 안 바뀜)`
      : "위 격자의 판정(모든 칸의 역할)을 이 양식의 확정본으로 저장합니다 — 같은 양식의 문서에서 구조가 꼭 같은 표에 쓰입니다(문서는 안 바뀜)";
    barNote.hidden = true;
    barNote.replaceChildren();
    if (r.match && !held && changed()) { // 고치기와 따로 확정 — 이 표에 쓰이는 확정본과 지금 판정이 다르다: 사람이 고른다(서버도 mode 없이는 409)
      const n = (r.also || []).length + 1, apart = apartWhy();
      const up = hBtn("이 확정본 고치기", () => save(false, "update"), { cls: "btn sm primary tty-update", disabled: busy,
        title: `지금 판정으로 이 확정본을 고칩니다(판 ${nf(r.match.rev)} → ${nf(r.match.rev + 1)}) — 이 확정본이 맞는 모든 표의 판정이 바뀝니다: 이 문서에서 표 ${nf(n)}개(같은 양식의 다른 문서에서도)` });
      const nw = hBtn("이 표만 따로 확정", () => save(false, "new"), { cls: "btn sm tty-new", disabled: busy || !!apart,
        title: apart || "지금 판정을 새 확정본으로 저장합니다 — 지금까지 쓰던 확정본과 그것이 맞는 다른 표는 그대로입니다\n이 표에만 있는 고정 머리글까지 맞는 표(이 표)에는 새 확정본을 씁니다" });
      bar.replaceChildren(up, nw);
      barNote.hidden = false;
      barNote.append(`지금 판정이 이 표에 쓰이는 확정본과 다릅니다 — 그 확정본이 맞는 표: 이 문서에 ${nf(n)}개. 고치면 모두 바뀌고, 따로 확정하면 이 표만 새 확정본으로 읽습니다.`);
      if (apart) barNote.append(el("span", "tty-warn", ` 따로 확정은 지금 안 됩니다 — ${apart.split("\n")[0]}`));
      return;
    }
    const ok = hBtn("이 판정으로 확정", () => save(false), { cls: "btn sm primary tty-ok", disabled: busy || !!held || amb, title: why });
    const nx = hBtn("확정하고 다음 표", () => save(true), { cls: "btn sm tty-next", disabled: busy || !!held || amb, title: `${why}\n확정한 뒤 이 문서에서 확정 안 된 다음 표를 엽니다` });
    bar.replaceChildren(ok, nx);
  }

  function drawList() { // 이 타입의 확정본 — 같은 타입 · 같은 격자의 확정본(이 표에 맞는 것 · 안 맞는 까닭) · 지우기
    const vs = view.variants || [];
    const s = el("summary", null), was = listBox.open || view.state === "ambiguous" || view.state === "changed";
    s.append(el("b", null, "이 타입의 확정본"), el("span", "muted", ` ${nf(vs.length)}`));
    listBox.replaceChildren(s);
    listBox.open = was;
    if (!vs.length) { listBox.append(el("p", "hnote", "이 양식에 이 타입의 확정본이 없습니다 — 위 판정이 맞으면 「이 판정으로 확정」 을 누르세요.")); return; }
    const ul = el("ul", "tty-entries");
    for (const v of vs) {
      const li = el("li", "tty-entry"), top = el("div", "tty-entry-top"), name = el("b", "tty-entry-name", v.name);
      const tag = el("span", `hb${v.used ? " chg" : ""}`, v.used ? "이 표에 쓰임" : v.fits ? "이 표에 맞음" : "안 맞음");
      tag.title = v.used ? "지금 이 표의 판정이 이 확정본을 씁니다"
        : !v.fits ? v.why
        : view.match ? "이 표에도 맞지만, 고정 머리글이 더 많이 맞은 확정본(이 표에 쓰임)을 씁니다"
        : "이 표에 맞는 확정본이 둘 이상이고 고정 머리글이 서로를 품지 않아 어느 쪽도 쓰지 않습니다 — 안 쓰는 것을 지우세요";
      name.title = v.name;
      top.append(name, tag);
      const from = v.from || {};
      const meta = el("div", "tty-entry-meta", `판 ${nf(v.rev)}${v.at ? ` · ${fmtWhen(v.at)}` : ""} · ${v.rows}×${v.cols} · 고정 머리글 ${nf(v.fixed)} · 가변 ${nf(v.variable)}${from.table ? ` · ${from.table} 에서 확정` : ""}`);
      li.append(top, meta);
      if (!v.fits && v.why) li.append(el("div", "tty-entry-why", v.why));
      const remove = async () => {
        try { await api(`/api/table-types/${encodeURIComponent(v.id)}`, { method: "DELETE" }); }
        catch (e) { toast(`지우지 못했습니다: ${tblTypeErr(e)}`, true); if (live()) load(); return; }
        // 확인 창 없이 지우고, 알림의 「되돌리기」 로 그대로 되살린다(design.md §18 — 창으로 묻지 않는다). 되살리기는 id 만 보낸다 — 서버가 지닌 지운 확정본에서 되살린다(확정본을 보내지 않는다)
        toast(`확정본 「${tblTypeCut(v.name, 30)}」 를 지웠습니다`, false, { label: "되돌리기", run: async () => {
          try { await api("/api/table-types/restore", { method: "POST", headers: H_JSON, body: JSON.stringify({ id: v.id }) }); }
          catch (e) { toast(`되돌리지 못했습니다: ${tblTypeErr(e)}`, true); }
          tblTypesLoad(true);
          if (live()) load();
        } });
        tblTypesLoad(true);
        if (live()) load();
      };
      const btns = el("span", "tty-entry-acts");
      btns.append(hBtn("지우기", remove, { title: "이 확정본을 지웁니다 — 지운 직후 알림의 「되돌리기」 로 되살릴 수 있습니다(문서는 안 바뀜 · 같은 양식의 다른 문서에서도 더는 쓰이지 않습니다)" }));
      li.append(btns);
      ul.append(li);
    }
    listBox.append(ul);
  }

  take(first);
  hFoot("", false);
}
