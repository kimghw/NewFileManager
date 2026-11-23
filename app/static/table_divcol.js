"use strict";
// 구분 기준 열 넣기(spec_테이블매니저 ② §13) — 표 모듈의 한 조각. 사용자 2026-11-23 "테이블 기능 중에 열에 구분기준을 추가할 수 있는 옵션을 넣어줘, 그럼 해당 행이 어떤 기관, 어떤 차년, 어떤 단계 인지
// 추가로 넣는거지. 1단계 구분기준이 추가된 이후에 하면 선택해서 넣을 수 있겠지?".
// 표 메뉴(table_menu.js) 「구분 기준 열 넣기…」(연구개발과제 문서 · hwpx) 가 연다 → 2열 kind "tblDivCol"(문서 옆 열 — 팝업 아님):
//   기준(단계 · 차년도 · 기관 — 고른 기준마다 열 하나, 구분 순서대로) · 넣을 자리(머리의 합친 칸 안은 서버가 빼고 줌) · 기준마다 머리 글 ·
//   값 줄마다 값 고르기(프로젝트 구성의 값 칩 — 여럿 고르면 프로젝트 구성의 차례로 「, 」 · 편집 구역이 읽은 값은 처음부터 골라져 「구역」 표지 · 「직접 입력」) · 「모두 같은 값으로」 ·
//   「열 넣기」(한 번의 편집 — 실행 취소 1개). 줄에 마우스를 올리면 문서의 그 줄을 칠한다. 프로젝트 구성 값이 없으면 「프로젝트 구성을 먼저 정하세요」 + 「프로젝트 구성 열기」.
// app.js 가 주는 것: state·heads·el·api·toast·structOp·flushAll·headsDlg·hBtn·nf·oneLine·showTab·scrollHow·divSettingsFlush. tables.js: xlBlock. 전역 이름은 tblDivCol…·tdc…·TDC_… 만 쓴다.
// 서버 짝: app/table_divcol_api.py(`GET …/tables/{tid}/divcol` · `POST …/divcol/apply`) · 계산 app/table_divcol.py. index.html 이 table_kv.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TDC_ORDER = ["stage", "year", "org"]; // 구분 순서(바깥 → 안) — 넣는 열의 차례(왼쪽 → 오른쪽)
const TDC_NAME = { stage: "단계", year: "차년도", org: "기관" };
const TDC_TEXT_MAX = 200, TDC_HEAD_MAX = 30;
// keep[표 id] = 마지막에 본 고름 {bases: Set, at, heads: {기준: 글}, rows: {항목 id: {기준: {keys: Set, custom}}}} — 문서를 다시 열기 전까지(같은 표를 다시 열면 이어서)
const tdc = { doc: null, keep: {} };
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tableDivCol: "구분 기준 열 넣기" }); // 「기록」 탭의 이름

const tdcUrl = (tid, tail = "") => `/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/divcol${tail}`;
const tdcErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「구분 기준 열 넣기」 를 쓸 수 있습니다" : e.message);

function tdcHit(ids = null) { // 줄에 올린 동안 문서의 그 줄 칸을 칠한다(없으면 걷기)
  for (const e of document.querySelectorAll("#doc td.tdc-hit")) e.classList.remove("tdc-hit");
  for (const id of ids || []) for (const e of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(id)}"]`)) e.classList.add("tdc-hit");
}

async function tblDivColView(tid) {
  if (!state.id) return;
  if (state.format === "docx") { toast("구분 기준 열 넣기는 지금 hwpx 문서만 됩니다"); return; }
  if (typeof xlBlock === "function" && !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const docKey = `${state.id}|${state.epoch}`;
  if (tdc.doc !== docKey) { tdc.doc = docKey; tdc.keep = {}; }
  const { tools, body } = headsDlg("tblDivCol", `구분 기준 열 · ${tid}`, "표에 기관 · 차년도 · 단계 열을 넣고, 값 줄마다 어느 기관 · 차년도 · 단계의 것인지 적습니다");
  const seq = heads.seq, epoch = state.epoch;
  const live = () => seq === heads.seq && epoch === state.epoch;
  const wrap = el("div", "ta-wrap tdc-wrap");
  body.append(wrap);
  tools.append(el("span", "muted", "고를 값은 프로젝트 구성의 값입니다 · 「열 넣기」 는 한 번의 편집이라 실행 취소 한 번으로 되돌립니다"));
  let busy = false;

  async function load(note = "") {
    wrap.replaceChildren(el("p", "hnote", "이 표를 읽는 중…"));
    let v = null;
    try {
      await flushAll(); // 타자 중인 글을 서버에 먼저
      if (typeof divSettingsFlush === "function") await divSettingsFlush(); // 입력 중인 프로젝트 구성 값도 — 고를 값은 서버의 값이다
      v = await api(tdcUrl(tid));
    } catch (e) {
      if (live()) wrap.replaceChildren(el("p", "hnote tdc-warn", tdcErr(e)));
      return;
    }
    if (live()) draw(v, note);
  }

  function draw(v, note) {
    wrap.replaceChildren();
    tdcHit();
    const acts = el("div", "ta-row");
    acts.append(hBtn("표 자리로", () => { const t = document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`); if (t) t.scrollIntoView({ block: "start", behavior: scrollHow() }); }, { title: "문서에서 이 표로" }),
      hBtn("다시 읽기", () => load(), { title: "지금 문서로 다시 읽습니다(문서는 안 바뀜)" }));
    wrap.append(acts);
    if (note) wrap.append(el("p", "hnote tdc-done", note));
    if (v.gate !== "rnd") { wrap.append(el("p", "hnote", "구분 기준 열 넣기는 연구개발과제 문서에서만 씁니다(프로젝트 구성의 기관 · 차년도 · 단계를 고릅니다).")); return; }
    if (!v.ready) {
      wrap.append(el("p", "hnote tdc-warn", "프로젝트 구성을 먼저 정하세요 — 단계 · 차년도 · 기관을 정한 뒤(워크플로우 1단계 「프로젝트 구성 추출」) 그 값 가운데서 골라 넣습니다."),
        el("div", "ta-row"));
      wrap.lastChild.append(hBtn("프로젝트 구성 열기", () => showTab("Div"), { title: "패널의 프로젝트 구성으로 갑니다 — 정한 뒤 「다시 읽기」" }));
      return;
    }
    if (!v.positions.length) { wrap.append(el("p", "hnote tdc-warn", "이 표에는 구분 기준 열을 넣을 자리가 없습니다(머리 칸이 모든 열에 걸쳐 합쳐져 있음).")); return; }
    if ((v.held || []).length) wrap.append(el("p", "hnote tdc-warn", `헤더 지정 ${nf(v.held.length)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀기 전에는 넣을 수 없습니다`));

    const k = tdc.keep[tid] || (tdc.keep[tid] = { bases: null, at: null, heads: {}, rows: {} });
    const has = (b) => (v.values[b] || []).length > 0;
    if (!k.bases) k.bases = new Set(has("org") ? ["org"] : TDC_ORDER.filter(has).slice(0, 1));
    for (const b of [...k.bases]) if (!has(b)) k.bases.delete(b);
    const pos = v.positions.find((p) => p.at === k.at) || v.positions.find((p) => p.default) || v.positions[0];
    k.at = pos.at;
    const items = v.items[String(pos.src)] || [];
    for (const it of items) { // 처음 보는 줄 — 편집 구역이 읽은 값으로 시작
      if (k.rows[it.id]) continue;
      k.rows[it.id] = Object.fromEntries(TDC_ORDER.map((b) => [b, { keys: new Set((it.suggest || {})[b] || []), custom: "" }]));
    }
    const order = () => TDC_ORDER.filter((b) => k.bases.has(b));
    const textOf = (it, b) => {
      const r = k.rows[it.id][b];
      return [...(v.values[b] || []).filter((x) => r.keys.has(x.key)).map((x) => x.label), r.custom.trim()].filter(Boolean).join(", ");
    };

    // 기준 — 고른 기준마다 열 하나(구분 순서대로)
    const sec = (title, help = "") => { const h = el("div", "tdc-h"); h.append(el("h3", null, title)); if (help) h.append(el("span", "muted", help)); wrap.append(h); return h; };
    sec("기준", "고른 기준마다 열 하나 — 단계 → 차년도 → 기관 차례로 나란히 넣습니다");
    const baseRow = el("div", "ta-row tdc-bases");
    for (const b of TDC_ORDER) {
      const lab = el("label", `tdc-chip${k.bases.has(b) ? " on" : ""}`), cb = el("input");
      cb.type = "checkbox"; cb.checked = k.bases.has(b); cb.disabled = !has(b) || busy;
      cb.onchange = () => { if (cb.checked) k.bases.add(b); else k.bases.delete(b); draw(v, ""); };
      lab.append(cb, el("span", null, `${TDC_NAME[b]}${has(b) ? ` (${nf(v.values[b].length)})` : " — 프로젝트 구성에 없음"}`));
      lab.title = has(b) ? `프로젝트 구성의 ${TDC_NAME[b]}: ${v.values[b].map((x) => x.label).join(" · ")}` : `프로젝트 구성에 ${TDC_NAME[b]} 값이 없습니다(기관은 이름을 적어야 합니다)`;
      baseRow.append(lab);
    }
    wrap.append(baseRow);

    // 넣을 자리 · 머리 글
    sec("넣을 자리");
    const posRow = el("div", "ta-row"), sel = el("select", "tdc-at");
    for (const p of v.positions) { const o = el("option", null, `${p.label}${p.default ? " (기본)" : ""}`); o.value = String(p.at); o.selected = p.at === pos.at; sel.append(o); }
    sel.title = "열과 열 사이 — 머리 칸이 여러 열에 걸쳐 합쳐진 곳(「개발 목표치」 아래 같은 곳)은 새 열이 제 머리 칸을 가질 수 없어 빠져 있습니다";
    sel.disabled = busy;
    sel.onchange = () => { k.at = Number(sel.value); draw(v, ""); };
    posRow.append(sel);
    wrap.append(posRow);
    if (order().length) {
      const hd = el("div", "ta-row tdc-heads");
      for (const b of order()) {
        const lab = el("label", "tdc-headlab"), inp = el("input", "tdc-head");
        inp.maxLength = TDC_HEAD_MAX; inp.value = k.heads[b] != null ? k.heads[b] : TDC_NAME[b]; inp.disabled = busy;
        inp.oninput = () => { k.heads[b] = inp.value; };
        lab.append(el("span", "tdc-lab", `${TDC_NAME[b]} 열 머리`), inp);
        hd.append(lab);
      }
      wrap.append(hd);
    }

    // 값 줄마다 값 고르기
    sec("줄마다 값", items.length ? `값 줄 ${nf(items.length)}개 · 여럿 고르면 「, 」 로 잇습니다` : "");
    if (!order().length) { wrap.append(el("p", "hnote", "기준을 하나 이상 고르세요.")); return; }
    if (!items.length) wrap.append(el("p", "hnote", "이 자리의 새 열에는 값을 적을 줄이 없습니다 — 머리 글만 넣습니다."));
    else {
      const all = el("div", "ta-row tdc-all");
      for (const b of order()) {
        const s = el("select", "tdc-allsel"), o0 = el("option", null, `${TDC_NAME[b]} — 모두 같은 값으로…`);
        o0.value = ""; s.append(o0);
        for (const x of v.values[b]) { const o = el("option", null, x.label); o.value = String(x.key); s.append(o); }
        const o9 = el("option", null, "모두 비우기"); o9.value = "\u0000"; s.append(o9);
        s.disabled = busy;
        s.onchange = () => {
          if (!s.value) return;
          const key = s.value === "\u0000" ? null : v.values[b].find((x) => String(x.key) === s.value).key;
          for (const it of items) { k.rows[it.id][b].keys = new Set(key == null ? [] : [key]); k.rows[it.id][b].custom = ""; }
          draw(v, "");
        };
        all.append(s);
      }
      wrap.append(all);
      const t = el("table", "mini tdc-rows"), thead = el("thead"), hr = el("tr"), tb = el("tbody");
      hr.append(el("th", null, "줄"));
      for (const b of order()) hr.append(el("th", null, TDC_NAME[b]));
      thead.append(hr);
      t.append(thead, tb);
      for (const it of items) {
        const tr = el("tr");
        const name = el("td", "tdc-name", it.label);
        name.title = `${it.label} — ${it.rows[0] + 1}${it.rows[1] > it.rows[0] ? `~${it.rows[1] + 1}` : ""}행`;
        tr.append(name);
        for (const b of order()) {
          const td = el("td", "tdc-vals"), r = k.rows[it.id][b], zone = ((it.by || {})[b] === "zone");
          for (const x of v.values[b]) {
            const chip = el("button", `tdc-chip sm${r.keys.has(x.key) ? " on" : ""}`, x.label);
            chip.type = "button"; chip.disabled = busy;
            chip.title = r.keys.has(x.key) && zone && ((it.suggest || {})[b] || []).includes(x.key) ? "편집 구역이 읽은 값입니다 — 눌러서 풉니다" : "눌러서 고르거나 풉니다(여럿 고를 수 있음)";
            chip.onclick = () => { if (r.keys.has(x.key)) r.keys.delete(x.key); else r.keys.add(x.key); chip.classList.toggle("on", r.keys.has(x.key)); out.textContent = textOf(it, b) || "(빈 칸)"; foot(); };
            td.append(chip);
          }
          const inp = el("input", "tdc-custom");
          inp.placeholder = "직접 입력"; inp.maxLength = TDC_TEXT_MAX; inp.value = r.custom; inp.disabled = busy;
          inp.oninput = () => { r.custom = inp.value.replace(/\n/g, " "); out.textContent = textOf(it, b) || "(빈 칸)"; foot(); };
          const out = el("div", "tdc-out muted", textOf(it, b) || "(빈 칸)");
          td.append(inp, out);
          if (zone) { const z = el("span", "hb tdc-zone", "구역"); z.title = "편집 구역이 이 줄의 칸을 이 값의 것으로 읽었습니다"; td.append(z); }
          tr.append(td);
        }
        tr.addEventListener("mouseenter", () => tdcHit(it.cells));
        tr.addEventListener("mouseleave", () => tdcHit());
        tb.append(tr);
      }
      wrap.append(t);
    }

    // 넣기
    const bar = el("div", "ta-row tdc-bar"), sum = el("span", "muted");
    const go = hBtn("열 넣기", () => apply(), { cls: "btn sm tdc-go" });
    bar.append(go, sum);
    wrap.append(bar);
    function foot() {
      const filled = items.filter((it) => order().some((b) => textOf(it, b))).length;
      sum.textContent = `${order().map((b) => TDC_NAME[b]).join(" · ")} 열 ${nf(order().length)}개 · ${pos.label} · 값을 적을 줄 ${nf(filled)}${items.length - filled ? ` · 빈 줄 ${nf(items.length - filled)}` : ""}`;
      go.disabled = busy || !order().length || (v.held || []).length > 0;
    }
    foot();

    async function apply() {
      if (busy) return;
      const heads2 = order().map((b) => ({ basis: b, head: (k.heads[b] != null ? k.heads[b] : TDC_NAME[b]).replace(/\n/g, " ").trim().slice(0, TDC_HEAD_MAX) }));
      const values = {};
      for (const it of items) {
        const row = {};
        for (const b of order()) { const t = textOf(it, b).slice(0, TDC_TEXT_MAX); if (t) row[b] = t; }
        if (Object.keys(row).length) values[it.id] = row;
      }
      busy = true;
      go.disabled = true;
      tdcHit();
      structOp.lastError = null;
      const out = await structOp(`tables/${encodeURIComponent(tid)}/divcol/apply`, { rev: v.rev, planId: v.planId, at: pos.at, cols: heads2, values }); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
      busy = false;
      if (!out || !out.divcol) { if (live()) { if (structOp.lastError && structOp.lastError.status === 409) load(); else draw(v, ""); } return; }
      const m = out.divcol;
      const msg = `표 ${tid} — ${m.bases.map((b) => TDC_NAME[b]).join(" · ")} 열을 넣고 ${nf(m.filled)}칸에 값을 적었습니다 · 도구 줄의 실행 취소로 되돌릴 수 있습니다`;
      toast(msg);
      k.rows = {}; k.at = null; // 표가 바뀌었다 — 줄 · 자리는 새 계획으로
      if (live()) load(msg);
    }
  }
  await load();
}
