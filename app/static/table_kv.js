"use strict";
// 표의 키-값 보기 · 다른 표에서 가져오기 · 매핑 규칙(spec_테이블매니저 ② §7 「키-값 추출과 매핑」) — 표 모듈의 한 조각.
// 사용자 2026-11-19 "그리고 테이블을 키값 으로 추출하도록 하고 이걸 다른 테이블에 매핑하는. 기능도 추가해줘." · "그리고 동일한 테이블이 아니면 매핑규칙은 관리되어야지".
// 표 메뉴(table_menu.js) 「키-값으로 보기 · 매핑…」 이 연다 → 2열 kind "tblKv"(문서 옆 열 — 팝업 아님):
//   이 표의 키-값 목록(칸 · 키 · 값 — 줄에 올리면 문서의 그 칸을 칠한다)
//   「다른 표에서 가져오기」 = 원본 표 고르기(이 문서의 표) → 계획(「넣을 수 있음 n · 같음 n · 겹침 n · 짝 없음 n」) → 짝마다 「지금 (빈 칸) → 넣을 값 …」 · 체크 → 「고른 n칸 넣기」(한 번의 편집 — 실행 취소 1개).
//     겹침(칸에 다른 글) · 수식 칸 · 원본이 빈 칸은 고를 수 없고 까닭을 줄에 보인다. 요청에는 계획의 rev 와 짝마다의 sig 를 늘 보낸다(본 뒤 달라진 칸은 서버가 건너뛴다).
//   「매핑 규칙」(짝 없는 항목이 있거나 쓰인 규칙이 있을 때 — 같은 타입이어도) = 쓰인 규칙 줄(머리글 바꿔 읽기 · 칸 짝 · ✕) + 「짝 없는 항목」 에서 원본 하나 · 이 표 하나를 골라 「짝짓기」 → 바로 저장 → 계획 다시.
//     규칙 묶음은 두 표의 **타입**(머리글이 같은 표끼리 같은 타입 — 값을 채워도 안 바뀐다)의 짝마다 하나다(같은 타입끼리도). 계획 머리에 「같은 타입」 | 「다른 타입」.
//   「저장된 매핑 규칙 n」 = 서버 전체의 규칙 묶음 목록(이름 바꾸기 · 지우기).
//   **구분 기준으로 묶어 넣기**(다대일 — 사용자 같은 날 "구분기준에 따라 열헤더가 있을거 아냐? 거기 분류대로 넣으면 되지.. 넣을때 팝업으로 기준을 뭘로 할래 , 년차로 할래, 기관으로 할래"):
//     원본 표는 목록에서 **여럿** 체크한다 → 「가져오기」 → 이 표에 구분 기준의 값 머리(「1차년도 | 2차년도」 · 기관 열 …)가 있으면 단추 옆 **작은 고르기 창**(공용 .ctx-menu — 화면을 덮지 않는다)이
//     「차년도로」 · 「기관으로」 · 「단계로」 · 「연도로」 · 「기준 없이(키 그대로)」 를 묻는다(기준이 없으면 묻지 않고 키 그대로). 기준을 고르면 원본마다 「어느 값의 것」 줄(권한 값 · 어디서 읽었나 · 바꾸기)
//     → 계획은 값마다 묶어(「2차년도 — 넣을 수 있음 12 · 겹침 0」) → 「고른 n칸 넣기」. 값이 정해지지 않은 원본은 넣지 않는다. 원본 하나를 기준 없이 가져오면 전과 같은 1대1(매핑 규칙을 만들고 고치는 곳).
//   **값을 더해서 넣기**(다대일 — 셀 값 합산): 원본 표를 둘 이상 고르면 고르기 창에 「값을 더해서 넣기」 — 같은 키 칸의 수를 더해 넣는다: 「지금 (빈 칸) → 넣을 값 1,200 (= 500 + 700)」.
//     원본 가운데 일부만 값이 있는 칸은 「확인」 이 붙고 처음에는 안 고른다(「원본 3 가운데 2개만 값이 있습니다」). 수가 아닌 글 · 수식으로 셈하는 칸(합계 줄)에는 안 넣는다.
//   **구분 기준의 값 고르기**(사용자 같은 날 "테이블에 구분기준이 있으면 빼거나 일부 선택할 수 있게 해줘 예로 2027년 내용만 너허는다던지"): 값을 받을 표(나눠 넣기에서는 이 표)에 기준이 있으면
//     계획 위에 기준마다 값 표지 줄(「연도 ☑ 2026 ☑ 2027 ☐ 2028 · 모두 · 모두 풀기」) — 표지를 끄면 그 값 머리 아래의 짝이 고름에서 빠지고 목록에서 흐려진다(「2027 만」 = 나머지를 끔).
//     기준이 여럿이면 모두 켜진 값의 짝만. 고르기는 화면의 일이다(서버는 짝에 div 와 값마다의 수를 실어 준다 — 넣기 요청은 고른 칸만).
//     **꺼 둔 값을 기억한다**(사용자 같은 날 "꺼 둔 값을 기억할게"): 표지를 켜고 끌 때마다 이 표의 **타입**으로 바로 저장하고(`PUT /api/table-maps/offs` — 실패하면 알림만, 화면의 고름은 그대로)
//     계획을 그릴 때 저장된 것으로 시작한다(화면 메모리 tblKv.vals[타입] 이 이미 있으면 그것이 먼저) — 같은 타입의 표를 다음에 열어도, 다른 문서에서도 꺼진 채다. 값 표지 줄 끝에 「꺼 둔 값 n — 기억됨」,
//     「모두」 를 누르면 그 기준의 저장도 지워진다. 저장된 조각이 지금 표의 값에 없으면 무시한다(지우지는 않는다 — 다른 문서의 같은 타입 표의 값일 수 있다).
//   **칸마다 넣는 방식**(사용자 같은 날 "어떤건 더해서 합이되는 필드가 있고 어떤건 다른걸 덮어 씌우면 합하거나 빼는게 있고 하잖아" → 답 「둘 다」): 받을 칸마다 빈 칸에만(기본) · 더하기 · 빼기 · 덮어쓰기 —
//     1대1 계획의 줄에서 「넣는 방식…」(이 칸만 | 이 머리글 아래 모두 → 넷 가운데) → 매핑 규칙 묶음에 바로 저장 → 계획 다시. 줄에 방식 표지 · 「지금 500 → 넣을 값 1,200 (= 500 + 700)」.
//     받을 칸에 이미 값이 있는 더하기 · 빼기 · 덮어쓰기는 「확인」 이 붙고 처음에는 안 고른다(같은 매핑을 두 번 하면 두 번 더해진다). 「넣는 방식」 묶음 = 저장된 것 목록(✕).
//   **계산 칸 다시 계산**(같은 날): 이 표의 수식 칸(합계 · 소계 · 코드 식 · 비율)을 수식대로 다시 셈해 넣는 묶음 — 넣기를 한 뒤 저절로 다시 읽어 「다시 계산할 칸 n」(넣기 전에도 단추로).
//     줄 「지금 (빈 칸) → 계산한 값 400 (=SUM(B5:E5))」 · 지금 값과 다른 칸은 「확인」(처음에는 안 고름) · 두 수식이 다른 칸 · 셈할 칸이 빈 칸은 못 고르고 까닭 → 「고른 n칸 넣기」(한 번의 편집).
//   표 이름 줄의 꼬리표 「양식의 확정본」 = 이 표의 칸 역할 · 키를 양식의 확정본(사람이 확정한 표 판정)으로 읽었다(spec_테이블매니저 ② §10 「양식의 표 판정」 — 값을 채워도 키가 안 바뀐다).
//   **다른 표로 나눠 넣기**(일대다 — 묶어 넣기의 반대): 이 표에 구분 기준의 값 머리가 있을 때만 보이는 묶음 — 받을 표 여럿 체크 → 「나눠 넣기」 → 기준 고르기 창(이 표의 기준) →
//     받을 표마다 「어느 값의 것」 줄 → 받을 표마다 묶인 계획 → 「고른 n칸 넣기」(받을 표 여럿에 한 번의 편집 — 실행 취소 1개).
// 다른 문서의 표를 원본으로 고르는 화면은 없다(끝점은 받는다 — from.doc). 확인 창(confirm)은 쓰지 않는다 — 넣기는 실행 취소로, 규칙 지우기는 알림의 「되돌리기」 로 돌아간다.
// app.js 가 주는 것: state·heads·el·api·toast·structOp·flushAll·headsDlg·hBtn·hFoot·hTable·nf·H_JSON·oneLine·ctxOpen·ctxMenu. tables.js: xlBlock·xlBlocks. panel_help.js: hHelp. 전역 이름은 tblKv…·TKV_… 만 쓴다.
// 서버 짝: app/table_kv_api.py(`…/tables/{tid}/kv` · `/kv/plan` · `/kv/apply` · `/api/table-maps…` · `/api/table-maps/offs`) · 추출 · 계획 app/table_kv.py · 규칙 · 꺼 둔 값 저장 app/table_maps.py.
// index.html 이 table_style.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TKV_TEXT = 120; // 줄에 보이는 값 글의 길이(전체는 풍선 도움말)
const TKV_HINT = 26;  // 표 이름에 붙이는 글(표 앞 문단 · 첫 칸 글)의 길이
const TKV_STATUS = { same: "같음", clash: "겹침", calc: "수식 칸", emptySrc: "원본 빈 칸", nonnum: "수가 아님" };
const TKV_OP = { fill: "빈 칸에만", add: "더하기", sub: "빼기", replace: "덮어쓰기" }; // 칸마다 넣는 방식
const TKV_OP_HOW = { fill: "빈 칸에만(기본) — 칸에 다른 글이 있으면 넣지 않습니다", add: "더하기 — 지금 값 + 원본 값", sub: "빼기 — 지금 값 − 원본 값", replace: "덮어쓰기 — 원본 값으로 바꿉니다" };
const TKV_BASIS = { year: "차년도", org: "기관", stage: "단계", period: "연도" }; // 구분 기준의 이름(묶어 넣는 기준)
const TKV_BY = { year: "차년도로", org: "기관으로", stage: "단계로", period: "연도로" }; // 기준 고르기 창의 항목
const TKV_READ = { zone: "편집 구역에서 읽음", owner: "표의 소속에서 읽음", text: "표 앞 글에서 읽음", user: "직접 고름" }; // 원본 표의 값을 어디서 읽었나
// pick[표 id] = 마지막에 가져온 것 {tables: [원본 표…], basis: 기준 | null, mode: "sum" | null, values: {원본 표: 사람이 고른 값}} · split[표 id] = 마지막에 나눠 넣은 것 {tables: [받을 표…], basis, values} ·
// off[열쇠] = Set(사람이 체크를 푼 받을 칸) · on[열쇠] = Set(사람이 체크한 「확인」 줄의 받을 칸 — 처음에는 안 고른 줄) · vals[열쇠] = {기준: Set(꺼 둔 값)}(구분 기준의 값 고르기) — 문서를 다시 열기 전까지
const tblKv = { doc: null, pick: {}, split: {}, off: {}, on: {}, vals: {} };
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tableKv: "표 키-값 넣기" }); // 「기록」 탭의 이름

const tblKvUrl = (tid, tail = "") => `/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/kv${tail}`;
const tblKvCut = (s, n = TKV_TEXT) => { const t = oneLine(s); return t.length > n ? `${t.slice(0, n)}…` : t; };
const tblKvParts = (key) => { const i = (key || "").indexOf("|"), r = i < 0 ? key || "" : key.slice(0, i), c = i < 0 ? "" : key.slice(i + 1); return [r ? r.split("›") : [], c ? c.split("›") : []]; }; // 키 「행1›행2|열1›열2」 → [행 조각, 열 조각]
const tblKvErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「키-값으로 보기 · 매핑」 을 쓸 수 있습니다" : e.message);

function tblKvHit(to = null, from = null) { // 줄에 올린 동안 문서의 칸을 칠한다(없으면 걷기) — td.tkv-hit = 이 표의 칸 · td.tkv-src = 원본 표의 칸(table_kv.css)
  for (const e of document.querySelectorAll("#doc td.tkv-hit, #doc td.tkv-src")) e.classList.remove("tkv-hit", "tkv-src");
  if (to) for (const e of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(to)}"]`)) e.classList.add("tkv-hit");
  if (from) for (const e of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(from)}"]`)) e.classList.add("tkv-src");
}
function tblKvGo(tid, cid = null) { // 문서에서 그 칸(없으면 표)으로 — 열은 그대로(나란히 보기)
  const target = (cid && document.querySelector(`#doc td[data-cell="${CSS.escape(cid)}"]`)) || document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`);
  if (!target) { toast("그 표가 지금 화면에 없습니다"); return; }
  target.scrollIntoView({ block: cid ? "center" : "start", behavior: "smooth" });
}
function tblKvTables() { // 문서의 표(칸 안 표 포함 · 문서 순) [{id, n(「테이블」 탭의 번호), rows, cols, depth, cells, hint(표 앞 문단 글 — 없으면 첫 칸 글), label}]
  const hints = new Map();
  const walk = (blocks) => {
    let last = "";
    for (const b of blocks || []) {
      if (b.type === "table") {
        const first = [...(b.cells || [])].sort((x, y) => x.row - y.row || x.col - y.col).map((c) => oneLine(c.text)).find((t) => t) || "";
        hints.set(b.id, last || first);
        for (const c of b.cells || []) walk(c.blocks);
        last = ""; // 잇달아 놓인 다음 표는 앞 표의 제목을 받지 않는다
      } else { const t = oneLine(b.text); if (t) last = t; }
    }
  };
  walk(state.blocks);
  return xlBlocks().map((b, i) => {
    const hint = hints.get(b.id) || "";
    return { ...b, n: i + 1, hint, label: `${i + 1}. ${b.id} · ${b.rows}×${b.cols}${b.depth > 1 ? " · 표 안 표" : ""}${hint ? ` · ${tblKvCut(hint, TKV_HINT)}` : ""}` };
  });
}
function tblKvAliasOf(s, d, bundle) { // 「머리글 바꿔 읽기」 후보 {from, to} | null — 원본 항목 s 와 이 표의 항목 d 의 키가 조각 수가 같고 조각 하나만 다를 때
  const raw = tblKvParts(s.key), a = tblKvParts(s.as || s.key), b = tblKvParts(d.key);
  if ([0, 1].some((k) => a[k].length !== b[k].length || raw[k].length !== a[k].length)) return null;
  const diff = [];
  for (const k of [0, 1]) a[k].forEach((f, i) => { if (f !== b[k][i]) diff.push([k, i]); });
  if (diff.length !== 1) return null;
  const [k, i] = diff[0], from = raw[k][i];
  if (from !== a[k][i]) return null; // 이미 다른 글로 바꿔 읽는 머리글 — 같은 머리글의 규칙을 둘 둘 수 없다(그 규칙을 지우고 다시 · 또는 「이 칸만」)
  if (((bundle && bundle.alias) || []).some((x) => x.from === from)) return null;
  return { from, to: b[k][i] };
}
function tblKvAliasGain(alias, plan, pick) { // 그 바꿔 읽기를 더하면 → {gain: 함께 짝지어질 다른 칸 수, lost: 지금 이어진 짝 가운데 키가 바뀌는 칸 수}(어림 — 정확한 것은 저장 뒤의 계획)
  const read = (key) => tblKvParts(key).map((ps) => ps.map((f) => (f === alias.from ? alias.to : f)).join("›")).join("|");
  const want = new Map(), got = new Map(), moved = [];
  for (const d of plan.unmatched.dst) if (d.key != null) want.set(d.key, (want.get(d.key) || 0) + 1);
  for (const s of plan.unmatched.src) {
    if (s.key == null) continue;
    const base = s.as || s.key, k = read(base);
    got.set(k, (got.get(k) || 0) + 1);
    if (k !== base) moved.push([s, k]);
  }
  const gain = moved.filter(([s, k]) => s.cell !== pick.cell && got.get(k) === 1 && want.get(k) === 1).length;
  const lost = plan.pairs.filter((p) => p.by !== "pair" && tblKvParts(p.fromKey || p.key).some((ps) => ps.includes(alias.from))).length;
  return { gain, lost };
}

async function tblKvView(tid) {
  if (!state.id) return;
  if (state.format === "docx") { toast("키-값으로 보기 · 매핑은 지금 hwpx 문서만 됩니다"); return; }
  if (typeof xlBlock === "function" && !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const docKey = `${state.id}|${state.epoch}`;
  if (tblKv.doc !== docKey) { tblKv.doc = docKey; tblKv.pick = {}; tblKv.split = {}; tblKv.off = {}; tblKv.on = {}; tblKv.vals = {}; }
  const { tools, body } = headsDlg("tblKv", `키-값 · ${tid}`, "값 칸마다 어느 머리글 아래의 칸인지(키)와 그 글(값)을 봅니다 — 다른 표의 같은 키 칸에서 값을 가져옵니다");
  const seq = heads.seq, epoch = state.epoch;
  const live = () => seq === heads.seq && epoch === state.epoch;
  const wrap = el("div", "ta-wrap tkv-wrap");
  body.append(wrap);
  tools.append(el("span", "muted", "보기 · 계획은 문서를 바꾸지 않습니다 · 넣기는 고른 칸만, 실행 취소 한 번으로 되돌립니다 · 칸에 글이 있으면 덮지 않습니다(「넣는 방식」 을 따로 정한 칸만 그 방식대로)"));
  const ident = el("div", "ta-ident"), acts = el("div", "ta-row"), heldLine = el("p", "hnote tkv-held"), sum = el("p", "hnote tkv-sum");
  const fromBox = el("section", "tkv-from"), planBox = el("div", "tkv-plan"), listBox = el("details", "hblock tkv-items"), mapsBox = el("details", "hblock tkv-maps");
  const splitFromBox = el("section", "tkv-split"), splitBox = el("div", "tkv-splitplan"); // 다른 표로 나눠 넣기 — 이 표에 기준이 있을 때만 채운다
  const recalcBox = el("section", "tkv-recalc"); // 계산 칸 다시 계산 — 이 표에 수식 칸이 있을 때만 채운다
  heldLine.hidden = true;
  listBox.open = true;
  acts.append(hBtn("표 자리로", () => tblKvGo(tid), { title: "문서에서 이 표로" }), hBtn("다시 읽기", () => load(), { title: "지금 문서로 다시 읽습니다(문서는 안 바뀜)" }));
  wrap.append(ident, acts, heldLine, sum, fromBox, planBox, recalcBox, splitFromBox, splitBox, listBox, mapsBox);
  let recalc = null, recalcAuto = false; // recalc = 다시 계산한 계획 · recalcAuto = 이 화면에서 이 표에 값을 넣은 뒤에는 다시 읽을 때마다 저절로 계획을 받는다
  const rOff = new Set(), rOn = new Set(); // 다시 계산 줄의 고름 — 넣을 수 있는 칸 가운데 끈 것 · 「확인」 줄 가운데 켠 것
  let view = null, plan = null, many = null, split = null, bundle = null, maps = [], busy = false, tables = []; // plan = 1대1 계획(원본 하나 · 기준 없이) · many = 여러 원본 · 묶어 넣기의 계획 — 둘 가운데 하나만
  const pickOf = () => tblKv.pick[tid] || null;
  const srcOf = () => { const pk = pickOf(); return pk && pk.tables.length === 1 && !pk.basis && !pk.mode ? pk.tables[0] : ""; }; // 1대1 의 원본 표(여럿이거나 기준 · 더하기가 있으면 없음)
  const planGo = () => (srcOf() ? planLoad() : planMany());
  let chase = 0; // 계획의 문서 차례가 이 표의 키-값과 다를 때 다시 읽은 횟수 — 문서가 잇달아 바뀌는 동안 끝없이 다시 읽지 않게(두 번까지 · 그 뒤에는 받은 계획을 그대로 그린다: 넣기는 rev 로 서버가 막는다)
  const stale = (p) => { if (view && p.rev !== view.rev && chase < 2) { chase += 1; load(); return true; } chase = 0; return false; };
  const usesMap = (id) => !!((plan && plan.rules && plan.rules.id === id) || (many && many.sources.some((x) => x.rules && x.rules.id === id)));
  const nameOf = (id) => { const t = tables.find((x) => x.id === id); return t ? tblKvCut(t.hint || t.id, 40) : id; };
  const labelOf = (id) => { const t = tables.find((x) => x.id === id); return t ? tblKvCut(`${t.hint ? `${t.hint} ` : ""}(${state.name ? `${state.name} · ` : ""}${t.id} · ${t.rows}×${t.cols})`, 160) : id; };
  const link = (text, fn, title) => { const b = el("button", "hlink", text); b.type = "button"; if (title) b.title = title; b.onclick = fn; return b; };
  const hover = (row, to, from) => { row.addEventListener("mouseenter", () => tblKvHit(to, from)); row.addEventListener("mouseleave", () => tblKvHit()); };
  const tplTag = (who) => { const b = el("span", "hb chg tkv-tpl", "양식의 확정본"); b.title = `${who}의 칸 역할 · 키는 양식의 확정본(사람이 확정한 표 판정)으로 읽었습니다 — 값을 채워도 키가 바뀌지 않습니다`; return b; };
  const valueEl = (text, cls) => { const s = el("span", cls, tblKvCut(text)); if (oneLine(text).length > TKV_TEXT || /\n/.test(text)) s.title = text; return s; };

  // ---- 구분 기준의 값 고르기 — 계획 위의 값 표지 줄(1대1 · 묶어 넣기 · 더해서 넣기 · 나눠 넣기가 같이 쓴다) ---------------------------------------------
  // 꺼 둔 값은 이 표(기준이 있는 표 = 지금 보는 표: 받을 때는 받을 표 · 나눠 넣을 때는 원본 표)의 **타입**마다 기억한다 — 화면 메모리 tblKv.vals[타입] 이 없으면 서버에 저장된 것으로 시작한다.
  let kept = { type: null, offs: {} }, keeping = Promise.resolve(), keepFail = false; // kept = 서버가 답한 저장된 것 {기준: [키 조각…]} · keeping = 저장 요청을 차례로(늦은 답이 앞의 것을 덮지 않게) · keepFail = 잇단 실패는 한 번만 알림
  const divNotes = new Map(); // 그리는 함수 → 그 계획의 값 표지 줄마다 「기억됨」 글을 다시 쓰는 함수들(저장이 끝나면 부른다 — 계획을 통째로 다시 그리지 않는다)
  const divOffs = () => { // {기준: Set(꺼 둔 값의 키 조각)} — 이 표 타입의 것
    const t = view.type;
    if (!tblKv.vals[t]) tblKv.vals[t] = Object.fromEntries(Object.entries(kept.type === t ? kept.offs : {}).map(([b, parts]) => [b, new Set(parts)]));
    return tblKv.vals[t];
  };
  const divOut = () => { // 그 짝이 꺼 둔 값의 것인가 — 기준이 여럿이면 하나라도, 같은 기준이 행 · 열 양쪽에 있어 값이 둘(목록)이면 그 가운데 하나라도 꺼졌으면
    const offs = divOffs();
    return (p) => Object.entries(p.div || {}).some(([b, v]) => offs[b] && (Array.isArray(v) ? v : [v]).some((x) => offs[b].has(x)));
  };
  async function offsLoad() { // 이 표 타입에 저장된 꺼 둔 값 — 못 읽으면 없는 것으로(화면의 고름은 그대로 쓴다)
    const type = view.type;
    try {
      const r = await api(`/api/table-maps/offs?type=${encodeURIComponent(type)}`);
      kept = { type, offs: (r && r.offs) || {} };
    } catch (e) { kept = { type, offs: {} }; }
  }
  function offsSave() { // 표지를 켜고 끌 때마다 바로 — 이 표 타입의 꺼 둔 값을 통째로 저장한다(빈 기준은 서버가 지운다). 실패하면 알림만(화면의 고름은 그대로)
    const type = view.type, offs = Object.fromEntries(Object.entries(divOffs()).map(([b, set]) => [b, [...set]]));
    keeping = keeping.then(async () => {
      try {
        const r = await api("/api/table-maps/offs", { method: "PUT", headers: H_JSON, body: JSON.stringify({ type, offs }) });
        keepFail = false;
        if (!live()) return;
        kept = { type, offs: (r && r.offs) || {} };
        for (const fns of divNotes.values()) for (const fn of fns) fn();
      } catch (e) {
        if (live() && !keepFail) toast(`꺼 둔 값을 기억하지 못했습니다(이 화면에서는 그대로 꺼져 있습니다): ${e && (e.status === 404 || e.status === 405) ? "서버가 옛 판입니다 — 서버를 다시 켜야 기억합니다" : tblKvErr(e)}`, true);
        keepFail = true;
      }
    });
  }
  function divChips(bases, redraw) { // 기준마다 값 표지 줄 → 요소 | ""(값 머리 아래의 짝이 없음). bases = 계획 응답의 기준(값마다 pairs · fill)
    const offs = divOffs(), box = el("div", "tkv-divs"), by = new Map(), notes = [];
    const flip = () => { redraw(); offsSave(); }; // 다시 그리고(이 줄도 새로 그려진다) 저장한다
    divNotes.set(redraw, notes);
    for (const b of bases || []) { // 같은 기준이 두 곳(행 쪽 · 열 쪽)에 있으면 값을 모아 한 줄로
      const got = by.get(b.basis) || by.set(b.basis, new Map()).get(b.basis);
      for (const v of b.values) { const x = got.get(v.part) || got.set(v.part, { part: v.part, label: v.label, pairs: 0, fill: 0 }).get(v.part); x.pairs += v.pairs || 0; x.fill += v.fill || 0; }
    }
    for (const [basis, got] of by) {
      const vals = [...got.values()].filter((v) => v.pairs > 0);
      if (!vals.length) continue;
      const set = offs[basis] || (offs[basis] = new Set()), row = el("div", "ta-row tkv-div"), note = el("span", "muted tkv-kept");
      row.dataset.basis = basis;
      row.append(el("span", "tkv-lab", TKV_BASIS[basis]));
      for (const v of vals) {
        const lab = el("label", `tkv-chip${set.has(v.part) ? "" : " on"}`), cb = el("input");
        cb.type = "checkbox";
        cb.value = v.part;
        cb.checked = !set.has(v.part);
        cb.onchange = () => { if (cb.checked) set.delete(v.part); else set.add(v.part); flip(); };
        lab.title = `${v.label} — 짝 ${nf(v.pairs)} · 넣을 수 있음 ${nf(v.fill)}\n끄면 이 ${TKV_BASIS[basis]}의 머리글 아래 칸은 넣지 않습니다(목록에서 흐려집니다)`;
        lab.append(cb, el("span", null, v.label));
        row.append(lab);
      }
      row.append(hBtn("모두", () => { set.clear(); flip(); }, { title: `${TKV_BASIS[basis]}의 값을 모두 켭니다 — 기억해 둔 꺼 둔 값도 지워집니다` }), hBtn("모두 풀기", () => { for (const v of vals) set.add(v.part); flip(); }, { title: `${TKV_BASIS[basis]}의 값을 모두 끕니다 — 넣을 값만 다시 켜세요` }), note);
      note.title = "꺼 둔 값은 이 표의 타입(머리글이 같은 표)으로 기억합니다 — 같은 타입의 표를 다음에 열어도, 다른 문서에서도 꺼진 채로 보입니다. 「모두」 를 누르면 지워집니다";
      const write = () => { // 서버가 기억한 것과 지금 꺼진 표지가 겹치는 수 — 저장이 끝나면 다시 쓴다
        const keep = new Set((kept.type === view.type && kept.offs[basis]) || []), n = vals.filter((v) => set.has(v.part) && keep.has(v.part)).length;
        note.textContent = n ? `꺼 둔 값 ${nf(n)} — 기억됨` : "";
        note.hidden = !n;
      };
      write();
      notes.push(write);
      box.append(row);
    }
    return box.children.length ? box : "";
  }

  // ---- 읽기 ----------------------------------------------------------------------------------------------------------
  async function load() {
    hFoot("읽는 중…", false);
    try {
      await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서의 칸 글로 읽는다
      const r = await api(tblKvUrl(tid));
      if (!live()) return;
      view = r;
      if (view.bases.length && kept.type !== view.type) { // 꺼 둔 값(이 표 타입에 저장된 것) — 값 표지 줄이 그것으로 시작한다(기준이 없는 표는 읽지 않는다)
        await offsLoad();
        if (!live()) return;
      }
      tables = tblKvTables();
      drawHead();
      drawFrom();
      drawSplitFrom();
      drawItems();
      const pk = pickOf();
      if (pk && pk.tables.length && pk.tables.every((id) => tables.some((t) => t.id === id))) await planGo();
      else { delete tblKv.pick[tid]; plan = null; many = null; bundle = null; drawPlan(); }
      const sp = tblKv.split[tid];
      if (live() && sp && view.bases.length && sp.tables.every((id) => tables.some((t) => t.id === id))) await splitLoad();
      else if (live()) { delete tblKv.split[tid]; split = null; drawSplit(); }
      if (live()) mapsLoad();
      if (live()) { if ((recalcAuto || recalc) && view.items.some((i) => i.calc)) await recalcLoad(); else { recalc = null; drawRecalc(); } }
    } catch (e) {
      if (!live()) return;
      sum.textContent = `읽지 못했습니다: ${tblKvErr(e)}`;
      planBox.textContent = "";
      hFoot(sum.textContent);
    }
  }
  async function planLoad() {
    const src = srcOf();
    if (!src) return;
    hFoot("계획을 세우는 중…", false);
    try {
      await flushAll();
      const p = await api(tblKvUrl(tid, "/plan"), { method: "POST", headers: H_JSON, body: JSON.stringify({ from: { table: src } }) });
      const b = p.rules ? await api(`/api/table-maps/find?from=${encodeURIComponent(p.types.from)}&to=${encodeURIComponent(p.types.to)}`) : null; // 쓰인 규칙 묶음의 내용(줄 · version)
      if (!live() || src !== srcOf()) return;
      plan = p;
      many = null;
      bundle = b;
      if (stale(p)) return; // 그 사이 문서가 바뀜 — 이 표의 키-값부터 다시
      listBox.open = false; // 계획이 같은 칸을 「지금 → 넣을 값」 으로 보인다 — 키-값 목록은 접어 둔다
      drawPlan();
      drawMaps(); // 저장된 목록의 「지금 쓰임」 표지를 이 계획에 맞춘다
      hFoot(`표 ${tid} ← ${src} · 넣을 수 있음 ${nf(p.counts.fill)} · 문서 차례 ${p.rev}`, false);
    } catch (e) {
      if (!live()) return;
      plan = null;
      many = null;
      bundle = null;
      planBox.replaceChildren(el("p", "hd-msg", `계획을 세우지 못했습니다: ${tblKvErr(e)}`));
      hFoot(`계획을 세우지 못했습니다: ${tblKvErr(e)}`);
    }
  }
  async function planMany() { // 여러 원본 · 구분 기준으로 묶어 넣기의 계획 — 사람이 고른 값(pick.values)이 있으면 그것을, 없으면 서버가 권한다
    const pk = pickOf();
    if (!pk) return;
    hFoot("계획을 세우는 중…", false);
    try {
      await flushAll();
      const body = { from: pk.tables.map((t) => ({ table: t, ...(pk.basis && pk.values[t] ? { value: pk.values[t] } : {}) })), ...(pk.mode ? { mode: pk.mode } : pk.basis ? { group: { basis: pk.basis } } : {}) };
      const p = await api(tblKvUrl(tid, "/plan"), { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
      if (!live() || pk !== pickOf()) return;
      plan = null;
      bundle = null;
      many = p;
      if (stale(p)) return; // 그 사이 문서가 바뀜 — 이 표의 키-값부터 다시
      listBox.open = false;
      drawMany();
      drawMaps(); // 저장된 목록의 「지금 쓰임」 표지를 이 계획에 맞춘다
      hFoot(`표 ${tid} ← 원본 표 ${nf(p.sources.length)}개 · 넣을 수 있음 ${nf(p.counts.fill)} · 문서 차례 ${p.rev}`, false);
    } catch (e) {
      if (!live()) return;
      plan = null;
      many = null;
      bundle = null;
      planBox.replaceChildren(el("p", "hd-msg", `계획을 세우지 못했습니다: ${tblKvErr(e)}`));
      hFoot(`계획을 세우지 못했습니다: ${tblKvErr(e)}`);
    }
  }
  async function splitLoad() { // 다른 표로 나눠 넣기의 계획 — 받을 표마다 사람이 고른 값이 있으면 그것을, 없으면 서버가 권한다
    const sp = tblKv.split[tid];
    if (!sp) return;
    try {
      await flushAll();
      const body = { to: sp.tables.map((t) => ({ table: t, ...(sp.values[t] ? { value: sp.values[t] } : {}) })), group: { basis: sp.basis } };
      const p = await api(tblKvUrl(tid, "/split/plan"), { method: "POST", headers: H_JSON, body: JSON.stringify(body) });
      if (!live() || sp !== tblKv.split[tid]) return;
      split = p;
      if (stale(p)) return; // 그 사이 문서가 바뀜 — 이 표의 키-값부터 다시
      drawSplit();
    } catch (e) {
      if (!live()) return;
      split = null;
      splitBox.replaceChildren(el("p", "hd-msg", `나눠 넣을 계획을 세우지 못했습니다: ${tblKvErr(e)}`));
    }
  }
  async function mapsLoad() {
    try {
      const r = await api("/api/table-maps");
      if (!live()) return;
      maps = r.maps || [];
    } catch { if (!live()) return; maps = []; }
    drawMaps();
  }

  // ---- 이 표의 키-값 ---------------------------------------------------------------------------------------------------
  function drawHead() {
    const k = view.counts, held = view.held || [];
    ident.replaceChildren(el("b", null, tid), el("span", null, `${view.rows}×${view.cols}`), el("span", "hb", `값 칸 ${nf(k.items)}`));
    if (view.source === "template") ident.append(tplTag("이 표")); // 양식의 확정본으로 판정한 표(spec_테이블매니저 ② §10 「양식의 표 판정」)
    ident.children[2].title = "값 칸 = 칸 역할이 필드인 칸(이 표의 스크립트 초안 — 양식의 확정본이 있으면 그것 — + 직접 지정한 헤더)\n키 = 그 칸 위 · 왼쪽 머리글의 사슬 — 각주 번호 · 단위 괄호 · 코드는 떼고 견줍니다";
    sum.textContent = k.items ? `값 칸 ${nf(k.items)} · 빈 칸 ${nf(k.empty)}${k.items - k.keyed ? ` · 키 없는 칸 ${nf(k.items - k.keyed)}` : ""}${k.dups ? ` · 같은 키가 둘 이상인 키 ${nf(k.dups)}` : ""}` : "값 칸이 없는 표입니다";
    sum.title = "빈 칸 = 글이 없거나 자리표시(0,000 · ○○)뿐인 칸\n키 없는 칸 = 위 · 왼쪽에 머리글이 없는 칸 · 같은 키가 둘 이상인 칸은 다른 표와 짝짓지 않습니다(어느 칸인지 가를 수 없음)";
    heldLine.hidden = !held.length;
    heldLine.textContent = held.length ? `헤더 지정 ${nf(held.length)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요(그때까지 이 표에 값을 넣지 않습니다)` : "";
    hFoot(`표 ${tid} · 값 칸 ${nf(k.items)} · 문서 차례 ${view.rev}`, false);
  }
  function drawItems() {
    const dups = new Set(view.dups || []);
    const s = el("summary", null);
    s.append(el("b", null, "이 표의 키-값"), el("span", "muted", ` · ${nf(view.items.length)}칸`));
    listBox.replaceChildren(s);
    if (!view.items.length) { listBox.append(el("p", "hnote", "값 칸(필드)이 없습니다 — 머리글만 있는 표이거나 칸 역할을 읽지 못했습니다. 칸을 골라 「헤더 지정」 으로 필드를 지정할 수 있습니다.")); return; }
    const [t, tb] = hTable(["칸", "키", "값"]);
    t.classList.add("tkv-list");
    for (const it of view.items) {
      const tr = el("tr", it.empty ? "tkv-empty" : null), c0 = el("td"), c1 = el("td", "wrap tkv-key"), c2 = el("td", "wrap tkv-val");
      c0.append(link(it.ref, () => tblKvGo(tid, it.cell), "문서에서 그 칸으로"));
      if (it.calc) { const b = el("span", "hb", "수식"); b.title = "수식으로 셈하는 칸(합계 · 비율) — 다른 표의 값을 넣지 않습니다"; c0.append(b); }
      if (it.obj) { const b = el("span", "hb", "표·그림"); b.title = "칸 안에 표 · 그림이 있습니다 — 글을 넣지 않습니다"; c0.append(b); }
      if (it.key == null) c1.append(el("span", "muted", "키 없음"));
      else {
        c1.textContent = it.label;
        if (dups.has(it.key)) { const b = el("span", "hb und", "같은 키"); b.title = "이 표에 같은 키의 칸이 둘 이상입니다 — 다른 표와 짝짓지 않습니다"; c1.append(" ", b); }
      }
      if (!it.text) c2.append(el("span", "muted", "(빈 칸)"));
      else { c2.append(valueEl(it.text, null)); if (it.empty) { const b = el("span", "hb", "자리표시"); b.title = "자리표시뿐인 칸 — 빈 칸으로 봅니다"; c2.append(" ", b); } }
      tr.append(c0, c1, c2);
      hover(tr, it.cell, null);
      tb.append(tr);
    }
    listBox.append(t);
  }

  // ---- 다른 표에서 가져오기 — 원본 표 고르기(여럿) · 기준 고르기 창 ---------------------------------------------------------------
  function drawFrom() {
    const head = el("div", "tkv-h"), row = el("div", "ta-row"), find = el("input"), list = el("ul", "tkv-srcs"), count = el("span", "muted tkv-count");
    const bases = [...new Set((view.bases || []).map((b) => b.basis))]; // 이 표에 있는 기준(값 머리가 둘 이상인 구분 기준) — 있으면 「가져오기」 가 기준을 묻는다
    const go = hBtn("가져오기", () => fetchGo(), { cls: "btn sm tkv-get", title: `고른 원본 표의 값을 이 표에 넣는 계획을 봅니다(문서는 안 바뀜)${bases.length ? `\n이 표에는 ${bases.map((b) => TKV_BASIS[b]).join(" · ")} 머리글이 있습니다 — 어느 기준으로 묶어 넣을지 묻습니다` : ""}` });
    head.append(el("h3", null, "다른 표에서 가져오기"), hHelp("다른 표에서 가져오기 안내",
      "원본 표(하나 또는 여럿)를 골라 「가져오기」 를 누릅니다 — 원본 표의 값을 이 표의 같은 키(머리글 사슬이 꼭 같은) 칸에 넣습니다.\n이 표에 구분 기준의 머리글(「1차년도 | 2차년도」 · 기관 이름 …)이 있으면 어느 기준으로 묶어 넣을지 묻습니다 — 원본 표마다 그 기준의 어느 값의 것인지 읽어 권하고, 그 값의 머리글 아래 칸에 넣습니다.\n넣는 것은 고른 빈 칸뿐입니다 — 칸에 다른 글이 있으면 덮지 않고, 수식으로 셈하는 칸(합계 · 비율)에는 넣지 않습니다.\n키가 다른 칸은 「매핑 규칙」 으로 어느 키를 어느 키로 읽을지 정합니다(원본 표 하나를 기준 없이 가져올 때 만들고, 저장해 두고 같은 두 표 타입에 다시 씁니다)."));
    const cands = tables.filter((t) => t.id !== tid && t.cells > 1 && !(typeof tempTableItem === "function" && tempTableItem(t.id))); // 1칸 표(글상자) · TEMP 표(나중에 지울 작성 요령 표)는 원본 후보가 아니다
    const pk = pickOf(), sel = new Set(pk ? pk.tables.filter((id) => cands.some((t) => t.id === id)) : []);
    const sync = () => { count.textContent = sel.size ? `${nf(sel.size)}개 고름` : ""; go.disabled = !sel.size; };
    find.type = "search";
    find.className = "tkv-find";
    find.placeholder = "표 번호 · 글";
    find.setAttribute("aria-label", "원본 표 찾기");
    list.setAttribute("role", "group");
    list.setAttribute("aria-label", "원본 표(여럿 고를 수 있습니다)");
    const rows = cands.map((t) => {
      const li = el("li"), lab = el("label"), cb = el("input");
      cb.type = "checkbox";
      cb.value = t.id;
      cb.checked = sel.has(t.id);
      cb.onchange = () => { if (cb.checked) sel.add(t.id); else sel.delete(t.id); sync(); };
      lab.title = t.hint || t.label;
      lab.append(cb, el("span", null, t.label));
      li.append(lab);
      list.append(li);
      return [li, t];
    });
    find.oninput = () => {
      const q = oneLine(find.value).toLowerCase();
      for (const [li, t] of rows) li.hidden = !!q && !sel.has(t.id) && !`${t.label} ${t.hint}`.toLowerCase().includes(q); // 고른 표는 찾는 글과 달라도 남는다
    };
    const fetchGo = () => {
      const picked = cands.filter((t) => sel.has(t.id)).map((t) => t.id); // 문서 차례
      if (!picked.length) return;
      const run = (basis, mode = null) => { tblKv.pick[tid] = { tables: picked, basis, mode, values: {} }; planGo(); };
      // 작은 고르기 창(사용자의 말 「팝업으로 기준을 뭘로 할래」) — 화면을 덮는 창이 아니라 단추 아래의 공용 메뉴(.ctx-menu): 이 표에 있는 기준 · (원본이 둘 이상이면) 값을 더해서 넣기 · 기준 없이
      const items = bases.map((b) => {
        const vals = (view.bases.find((x) => x.basis === b) || { values: [] }).values.map((v) => v.label);
        return [TKV_BY[b], () => run(b), `이 표의 ${TKV_BASIS[b]} 머리글(${tblKvCut(vals.join(" · "), 60)})마다 원본 표를 묶어 그 머리글 아래 칸에 넣습니다 — 원본 표가 어느 값의 것인지는 다음에 고칠 수 있습니다`];
      });
      if (picked.length >= 2) items.push(["값을 더해서 넣기", () => run(null, "sum"), "원본 표들의 같은 키 칸의 수를 더해 이 표의 그 키 칸에 넣습니다 — 합계 줄(수식으로 셈하는 칸)에는 넣지 않습니다"]);
      items.push(["기준 없이(키 그대로)", () => run(null), "기준으로 묶지 않고, 원본 표마다 키가 꼭 같은 칸에 넣습니다 — 두 원본이 같은 칸에 걸리면 어느 것도 넣지 않습니다"]);
      if (items.length === 1) { run(null); return; } // 이 표에 기준이 없고 원본이 하나면 묻지 않고 키 그대로
      const r = go.getBoundingClientRect(), menu = items.map(([label, fn]) => [label, "", fn, false]);
      if (bases.length) menu.splice(bases.length, 0, null); // 기준들 아래에 줄 하나
      ctxOpen({ clientX: Math.round(r.left), clientY: Math.round(r.bottom + 3) }, menu);
      [...ctxMenu().querySelectorAll("button")].forEach((b, i) => { if (items[i]) b.title = items[i][2]; });
    };
    sync();
    row.append(el("span", "tkv-lab", "원본 표"), find, go, count);
    fromBox.replaceChildren(head, row, cands.length ? list : el("p", "hnote", "이 문서에 다른 표가 없습니다."));
  }

  // ---- 계획 — 짝 · 넣기 ---------------------------------------------------------------------------------------------------
  function pairRow(p, { refs, off, on = new Set(), boxes, sync, from, src = null, out = null, ops = null }) { // 짝 한 줄 — 체크(넣을 수 있는 칸만) · 칸 · 키 · 「지금 → 넣을 값」(· 원본: 여러 원본 · 나눠 넣기). from = 원본 표의 칸(올리면 문서에 표시)
    const cell = typeof p.to === "string" ? p.to : p.to.cell, table = typeof p.to === "string" ? tid : p.to.table; // 나눠 넣기의 짝은 to 가 {table, cell}
    const gone = !!out && out(p); // 구분 기준의 값 고르기 — 위에서 꺼 둔 값의 머리글 아래 칸: 고름에서 빠지고 흐리게
    const fill = p.status === "fill", tr = el("tr", `tkv-${p.status}${gone ? " tkv-out" : ""}`), cb = el("input"), c0 = el("td"), c1 = el("td"), c2 = el("td", "wrap tkv-key", p.label), c3 = el("td", "wrap tkv-val");
    const ref = refs.get(cell) || cell;
    const okKey = `${cell}|${p.sig}`; // 「확인」 줄의 고름은 그 계획의 그 값(sig)에 묶는다 — 다시 받은 계획에서 값이 달라졌으면(더한 뒤 · 원본이 바뀐 뒤) 다시 보고 고르게
    const set = (v) => { if (p.check) { if (v) on.add(okKey); else on.delete(okKey); } else if (v) off.delete(cell); else off.add(cell); };
    cb.type = "checkbox";
    cb.disabled = !fill || gone;
    cb.checked = fill && !gone && (p.check ? on.has(okKey) : !off.has(cell)); // 「확인」 이 붙은 줄(원본 가운데 일부만 값 · 이미 값이 있는 칸 · 단위가 섞임)은 처음에는 고르지 않는다
    cb.setAttribute("aria-label", gone ? `${ref} — 위에서 꺼 둔 값의 칸` : fill ? `${ref} 넣기 고르기` : `${ref} — 넣지 않는 칸`);
    if (gone) tr.title = "위의 값 표지에서 꺼 둔 값의 머리글 아래 칸입니다 — 넣지 않습니다(표지를 켜면 다시 고를 수 있습니다)";
    if (fill && !gone) { cb.onchange = () => { set(cb.checked); sync(); }; boxes.push([cb, p, set]); }
    c0.append(cb);
    c1.append(link(ref, () => tblKvGo(table, cell), "문서에서 그 칸으로"));
    if (p.by !== "key") {
      const b = el("span", "hb chg", p.by === "pair" ? "칸 짝" : "규칙");
      b.title = `매핑 규칙으로 맺은 짝(${p.by === "pair" ? "칸 짝" : "머리글 바꿔 읽기"})${p.fromLabel || p.fromKey ? ` — 원본 표의 키 「${p.fromLabel || p.fromKey}」` : ""}`;
      c2.append(" ", b);
    }
    const op = p.op && p.op !== "fill" ? p.op : null; // 칸마다 넣는 방식 — 기본(빈 칸에만)은 표지 없음
    if (op) {
      const b = el("span", "hb chg tkv-op", TKV_OP[op]);
      b.title = `넣는 방식: ${TKV_OP_HOW[op]}\n매핑 규칙의 「넣는 방식」 에 저장된 것입니다`;
      c2.append(" ", b);
    }
    if (ops) { // 1대1 계획 — 이 칸(또는 이 머리글 아래 모두)의 넣는 방식을 정한다
      const b = link("넣는 방식…", () => ops(p, b), "이 칸(또는 이 머리글 아래 모두)에 값을 어떻게 넣을지 정합니다 — 빈 칸에만 · 더하기 · 빼기 · 덮어쓰기. 매핑 규칙에 저장됩니다");
      b.classList.add("tkv-oppick");
      c2.append(" ", b);
    }
    const nums = p.parts ? p.parts.filter((q) => q.num != null) : null; // 더해서 넣기 — 합의 풀이 「(= 500 + 700)」
    const how = p.expr ? el("span", "tkv-how", ` (${p.expr})`) : nums && nums.length ? el("span", "tkv-how", ` (= ${nums.map((q) => tblKvCut(q.text, 20)).join(" + ")})`) : "";
    const other = p.parts ? "더한 값 " : "원본 값 ";
    const had = !!p.had; // 받을 칸에 이미 값이 있다(자리표시가 아님) — 더하기 · 빼기 · 덮어쓰기의 「확인」
    if (fill) {
      c3.append(el("span", "tkv-now", p.was ? `지금 「${tblKvCut(p.was, 40)}」${had ? "" : "(자리표시)"}` : "지금 (빈 칸)"), el("span", "tkv-arrow", " → "), el("span", "tkv-lab2", "넣을 값 "), valueEl(p.text, "tkv-new"), how,
        op === "replace" && had ? el("span", "tkv-how", "(덮어쓰기)") : "");
      if (p.check) {
        const w = el("span", "hb und", "확인"), whys = [];
        if (p.missing) whys.push(`원본 ${nf(nums.length + p.missing)} 가운데 ${nf(nums.length)}개만 값이 있습니다`);
        if (had) whys.push("이미 값이 있는 칸입니다 — 같은 값을 두 번 넣으면 두 번 셈해집니다");
        if (p.why) whys.push(p.why); // 단위를 적지 않은 수가 섞여 있습니다
        w.title = `${p.missing ? "원본 가운데 일부만 값이 있습니다 — 있는 것만 더했습니다. " : ""}${had ? "받을 칸에 이미 값이 있습니다. " : ""}맞으면 체크해서 넣으세요(처음에는 고르지 않습니다)`;
        c3.append(" ", w, el("span", "tkv-why", whys.join(" · ")));
      }
    } else if (p.status === "same") {
      c3.append(el("span", "hb", TKV_STATUS.same), " ", valueEl(p.text, "muted"), how);
    } else if (p.status === "emptySrc") {
      c3.append(el("span", "hb", TKV_STATUS.emptySrc), " ", el("span", "tkv-why", p.why || ""));
    } else if (p.status === "nonnum") { // 더해서 넣기 — 원본에 수가 아닌 글: 원본 칸의 글을 그대로 보인다
      c3.append(el("span", "hb und", TKV_STATUS.nonnum), " ", el("span", "tkv-lab2", "원본 값 "), el("span", "muted", (p.parts || []).filter((q) => q.text).map((q) => `「${tblKvCut(q.text, 24)}」`).join(" · ")), el("span", "tkv-why", p.why || ""));
    } else { // 겹침 · 수식 칸 — 고를 수 없다: 두 값과 까닭을 보인다
      const b = el("span", "hb und", TKV_STATUS[p.status]);
      c3.append(b, " ", el("span", "tkv-now", p.was ? `지금 「${tblKvCut(p.was, 40)}」` : "지금 (빈 칸)"), el("span", "muted", " · "), el("span", "tkv-lab2", other), valueEl(p.text, "muted"), how, el("span", "tkv-why", p.why || ""));
    }
    tr.append(c0, c1, c2, c3);
    if (src != null) tr.append(el("td", "tkv-srccol", src));
    hover(tr, cell, from);
    return tr;
  }
  function drawPlan() {
    planBox.textContent = "";
    tblKvHit();
    if (!plan) return;
    const src = plan.from.table, c = plan.counts, refs = new Map(view.items.map((it) => [it.cell, it.ref]));
    const offKey = `${tid}|${src}`, off = tblKv.off[offKey] || (tblKv.off[offKey] = new Set()), on = tblKv.on[offKey] || (tblKv.on[offKey] = new Set());
    const head = el("div", "ta-ident tkv-planhead"), kind = el("span", `hb tkv-type${plan.types.same ? "" : " und"}`, plan.types.same ? "같은 타입" : "다른 타입");
    kind.title = `머리글(음영 칸의 글)이 같은 표끼리 같은 타입입니다 — 값을 채워도 바뀌지 않습니다\n${plan.types.same ? "두 표는 같은 타입입니다 — 그래도 키가 다른 칸은 「매핑 규칙」 으로 짝짓습니다" : "두 표는 타입이 다릅니다 — 꼭 같은 키의 칸만 이어지고, 그 밖은 「매핑 규칙」 으로 짝짓습니다"}\n매핑 규칙은 두 타입의 짝마다 저장되어 같은 타입의 표에 다시 쓰입니다`;
    head.append(el("span", "muted", "원본 표"), link(`${src} · ${plan.from.rows}×${plan.from.cols}`, () => tblKvGo(src), "문서에서 원본 표로"), el("span", "tkv-name", nameOf(src)), plan.from.source === "template" ? tplTag("원본 표") : "", el("span", "muted", "→ 이 표"), el("b", null, tid), kind);
    const psum = el("p", "hnote tkv-sum tkv-plansum", `넣을 수 있음 ${nf(c.fill)}${c.check ? `(확인 ${nf(c.check)})` : ""} · 같음 ${nf(c.same)} · 겹침 ${nf(c.clash)} · 짝 없음 ${nf(c.unmatched)}${c.calc ? ` · 수식 칸 ${nf(c.calc)}` : ""}${c.nonnum ? ` · 수가 아님 ${nf(c.nonnum)}` : ""}${c.emptySrc ? ` · 원본 빈 칸 ${nf(c.emptySrc)}` : ""}`);
    psum.title = `넣을 수 있음 = 이 표의 칸이 비었고 원본에 값이 있음(넣는 방식이 더하기 · 빼기 · 덮어쓰기인 칸은 값이 있어도 — 그때는 「확인」 이 붙고 처음에는 고르지 않습니다) · 같음 = 두 칸의 글이 같음 · 겹침 = 이 표의 칸에 다른 글이 있음(덮지 않습니다)\n짝 없음 = 원본 표에만 ${nf(c.unmatchedSrc)} · 이 표에만 ${nf(c.unmatchedDst)}(키가 없거나 · 같은 키가 둘 이상이거나 · 상대 표에 그 키가 없음)`;
    planBox.append(head, psum, divChips(plan.bases, drawPlan));
    const out = divOut();
    const held = (plan.held || []).length, left = leftOf();

    const bar = el("div", "ta-row tkv-bar"), count = el("span", "muted"), boxes = [];
    const applyBtn = hBtn("", () => apply(), { cls: "btn sm primary", title: "고른 칸에 원본 표의 값을 넣습니다 — 한 번의 편집(도구 줄 「실행 취소」 로 한꺼번에 되돌림). 계획을 본 뒤 달라진 칸은 건너뜁니다" });
    const sync = () => {
      const n = boxes.filter(([cb]) => cb.checked).length;
      applyBtn.textContent = `고른 ${nf(n)}칸 넣기`;
      applyBtn.disabled = !n || busy || state.busy || !!held;
      if (held) applyBtn.title = "헤더 지정이 지금 표와 맞지 않아 넣지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요";
      count.textContent = `${nf(n)} / ${nf(c.fill)}`;
    };
    const pickAll = (v) => { for (const [cb, p, set] of boxes) { const yes = typeof v === "function" ? v(p) : v; cb.checked = yes; set(yes); } sync(); };
    bar.append(applyBtn, hBtn("모두", () => pickAll(true), { title: "넣을 수 있는 칸을 모두 고릅니다" }), hBtn("모두 풀기", () => pickAll(false)), count);
    if (plan.pairs.length) {
      if (c.fill) planBox.append(bar);
      const [t, tb] = hTable(["", "칸", "키", "지금 → 넣을 값"]);
      t.classList.add("tkv-list", "tkv-pairs");
      for (const p of plan.pairs) tb.append(pairRow(p, { refs, off, on, boxes, sync, from: p.from, out, ops: opAsk }));
      planBox.append(t);
    } else planBox.append(el("p", "hnote", left.any ? "키가 꼭 같은 칸이 없습니다 — 아래 「짝 없는 항목」 에서 짝지으면 매핑 규칙으로 저장됩니다." : "짝지을 값 칸이 없습니다."));
    sync();
    if (bundle || plan.rules || left.any) drawRules(left); // 짝 없는 항목이 있거나 쓰인 규칙이 있을 때(같은 타입이어도)
    drawOps();
    drawLeft(left);

    async function apply() {
      const todo = boxes.filter(([cb]) => cb.checked).map(([, p]) => p);
      if (!todo.length || busy) return;
      busy = true;
      sync();
      tblKvHit();
      structOp.lastError = null;
      const sigs = Object.fromEntries(plan.pairs.map((p) => [p.to, p.sig]));
      const out = await structOp(`tables/${encodeURIComponent(tid)}/kv/apply`, { from: { table: src }, cells: todo.map((p) => p.to), rev: plan.rev, sigs }); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
      busy = false;
      if (!out || !out.mapped) { // 409 = 계획을 본 뒤 문서 · 규칙이 바뀜 — 다시 읽는다
        if (live()) { if (structOp.lastError && structOp.lastError.status === 409) load(); else sync(); }
        return;
      }
      const m = out.mapped, skip = m.skipped || [];
      toast(`표 ${tid} — ${nf((m.done || []).length)}칸에 값을 넣었습니다${skip.length ? ` · 건너뜀 ${nf(skip.length)}(${skip[0].why})` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
      for (const p of todo) on.delete(`${p.to}|${p.sig}`); // 넣은 「확인」 줄은 다시 꺼 둔다 — 다시 받은 계획(지금 값에서 또 셈한 것)을 사람이 다시 보고 고르게(두 번 더해지지 않게)
      recalcAuto = true; // 값을 넣었다 — 계산 칸을 저절로 다시 읽는다
      if (live()) load(); // 넣은 뒤 다시 읽고 계획도 다시(넣은 칸은 「같음」)
    }
  }

  // ---- 여러 원본 · 구분 기준으로 묶어 넣기(다대일) — 원본마다 「어느 값의 것」 · 값마다 묶은 계획 ---------------------------------------------
  function drawMany() {
    planBox.textContent = "";
    tblKvHit();
    if (!many) return;
    const pk = pickOf(), c = many.counts, g = many.group, adds = many.mode === "sum", refs = new Map(view.items.map((it) => [it.cell, it.ref])); // adds = 값을 더해서 넣기
    const offKey = `${tid}|${many.sources.map((x) => x.table).join(",")}|${adds ? "sum" : g ? g.basis : ""}`, off = tblKv.off[offKey] || (tblKv.off[offKey] = new Set()), on = tblKv.on[offKey] || (tblKv.on[offKey] = new Set());
    const head = el("div", "ta-ident tkv-planhead"), kind = el("span", "hb tkv-type", adds ? "값을 더해서 넣기" : g ? `${TKV_BY[g.basis]} 묶음` : "기준 없이(키 그대로)");
    kind.title = adds ? "원본 표들의 같은 키 칸의 수를 더해 이 표의 그 키 칸에 넣습니다 — 합계 줄(수식으로 셈하는 칸)에는 넣지 않습니다(표의 수식이 셈합니다)\n원본 가운데 일부만 값이 있는 칸은 「확인」 이 붙고 처음에는 고르지 않습니다 · 수가 아닌 글이 든 칸은 더하지 않습니다"
      : g ? `이 표의 ${TKV_BASIS[g.basis]} 머리글(${tblKvCut(g.values.map((v) => v.label).join(" · "), 60)})마다 원본 표를 묶어 그 머리글 아래 칸에 넣습니다\n원본 표가 어느 값의 것인지는 아래 줄에서 고칩니다 — 값이 정해지지 않은 원본은 넣지 않습니다`
      : "원본 표마다 키가 꼭 같은 칸에 넣습니다 — 두 원본이 같은 칸에 걸리면 어느 것도 넣지 않습니다(겹침)";
    head.append(el("span", "muted", `원본 표 ${nf(many.sources.length)}개`), el("span", "muted", "→ 이 표"), el("b", null, tid), kind);
    planBox.append(head);

    // 원본 표마다 — 묶어 넣을 때는 「어느 값의 것」(권한 값 · 어디서 읽었나 · 바꾸기)
    const sbox = el("section", "tkv-values"), sh = el("div", "tkv-h");
    sh.append(el("h3", null, g ? `원본 표가 어느 ${TKV_BASIS[g.basis]}의 것인지` : "원본 표"));
    if (g) sh.append(hHelp("원본 표의 값 안내", `원본 표마다 이 표의 ${TKV_BASIS[g.basis]} 머리글 가운데 어느 것의 표인지 정합니다 — 그 머리글 아래 칸에만 넣습니다.\n편집 구역(그 표가 놓인 기관 · 차년도 · 단계) → 표의 소속(구분 줄) → 표 앞 글, 차례로 읽어 권합니다. 맞지 않으면 고쳐 고르세요.\n못 읽은 원본은 값을 고를 때까지 넣지 않습니다(어림으로 넣지 않습니다). 두 원본이 같은 값이면 같은 칸에 걸려 어느 것도 넣지 않습니다.`));
    const [st, stb] = hTable(g ? ["원본 표", TKV_BASIS[g.basis], "어디서 읽었나", "넣을 수 있음"] : ["원본 표", adds ? "수가 든 칸" : "넣을 수 있음"]);
    st.classList.add("tkv-list", "tkv-sources");
    for (const x of many.sources) {
      const tr = el("tr", x.why ? "warn" : null), c0 = el("td", "wrap"), cn = el("td", null, nf(adds ? x.counts.nums : x.counts.fill));
      c0.append(link(x.table, () => tblKvGo(x.table), "문서에서 원본 표로"), " ", el("span", "muted", nameOf(x.table)));
      if (x.source === "template") c0.append(" ", tplTag("원본 표"));
      if (x.rules) { const b = el("span", "hb chg", "규칙"); b.title = `매핑 규칙 「${x.rules.name}」 — 이 규칙으로 이어진 칸 ${nf(x.rules.used)}`; c0.append(" ", b); }
      tr.append(c0);
      if (g) {
        const c1 = el("td"), c2 = el("td", "wrap"), sel = el("select"), none = el("option", null, x.by === "user" ? "권한 값으로(다시 읽기)" : "고르세요");
        sel.className = "tkv-value";
        sel.setAttribute("aria-label", `원본 표 ${x.table} 의 ${TKV_BASIS[g.basis]}`);
        none.value = "";
        sel.append(none);
        for (const v of g.values) { const o = el("option", null, v.label); o.value = v.part; sel.append(o); }
        sel.value = x.value || "";
        sel.title = "이 원본 표가 어느 값의 것인지 고릅니다 — 고르면 계획을 다시 세웁니다(문서는 안 바뀜)";
        sel.onchange = () => { if (sel.value) pk.values[x.table] = sel.value; else delete pk.values[x.table]; planMany(); };
        c1.append(sel);
        c2.append(el("span", x.value ? "muted" : "tkv-warn", x.value ? TKV_READ[x.by] || "" : "못 읽음 — 값을 고르세요"));
        if (x.why && x.value) c2.append(el("span", "tkv-why", x.why));
        tr.append(c1, c2);
      }
      tr.append(cn);
      hover(tr, null, null);
      stb.append(tr);
    }
    sbox.append(sh, st);
    if (many.sources.some((x) => x.rules)) sbox.append(el("p", "hnote", "저장된 매핑 규칙이 함께 쓰였습니다 — 규칙은 원본 표 하나를 기준 없이 가져올 때 만들고 고칩니다."));
    planBox.append(sbox);

    const psum = el("p", "hnote tkv-sum tkv-plansum", `넣을 수 있음 ${nf(c.fill)}${c.check ? `(확인 ${nf(c.check)})` : ""} · 같음 ${nf(c.same)} · 겹침 ${nf(c.clash)} · 짝 없음 ${nf(c.unmatched)}${c.calc ? ` · 수식 칸 ${nf(c.calc)}` : ""}${c.nonnum ? ` · 수가 아님 ${nf(c.nonnum)}` : ""}${c.emptySrc ? ` · 원본 빈 칸 ${nf(c.emptySrc)}` : ""}`);
    psum.title = adds ? `넣을 수 있음 = 이 표의 칸이 비었고 수인 원본이 하나 이상(확인 = 원본 가운데 일부만 값 — 처음에는 고르지 않습니다) · 같음 = 이 표의 수가 합과 같음 · 겹침 = 이 표의 칸에 다른 값(덮지 않습니다)\n수식 칸 = 합계 · 비율 줄(표의 수식이 셈합니다) · 수가 아님 = 원본에 수가 아닌 글\n짝 없음 = 원본 표에만 ${nf(c.unmatchedSrc)} · 이 표에만 ${nf(c.unmatchedDst)}`
      : `넣을 수 있음 = 이 표의 칸이 비었고 원본에 값이 있음 · 같음 = 두 칸의 글이 같음 · 겹침 = 이 표의 칸에 다른 글이 있거나 두 원본이 같은 칸에 걸림(넣지 않습니다)\n짝 없음 = 원본 표에만 ${nf(c.unmatchedSrc)} · 이 표에만 ${nf(c.unmatchedDst)}`;
    planBox.append(psum, divChips(many.bases, drawMany));
    const out = divOut();
    const held = (many.held || []).length, bar = el("div", "ta-row tkv-bar"), count = el("span", "muted"), boxes = [];
    const applyBtn = hBtn("", () => apply(), { cls: "btn sm primary", title: "고른 칸에 원본 표의 값을 넣습니다 — 한 번의 편집(도구 줄 「실행 취소」 로 한꺼번에 되돌림). 계획을 본 뒤 달라진 칸은 건너뜁니다" });
    const sync = () => {
      const n = boxes.filter(([cb]) => cb.checked).length;
      applyBtn.textContent = `고른 ${nf(n)}칸 넣기`;
      applyBtn.disabled = !n || busy || state.busy || !!held;
      if (held) applyBtn.title = "헤더 지정이 지금 표와 맞지 않아 넣지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요";
      count.textContent = `${nf(n)} / ${nf(c.fill)}`;
    };
    const pickAll = (v) => { for (const [cb, p, set] of boxes) { const yes = typeof v === "function" ? v(p) : v; cb.checked = yes; set(yes); } sync(); };
    bar.append(applyBtn, hBtn("모두", () => pickAll(true), { title: "넣을 수 있는 칸을 모두 고릅니다" }), hBtn("모두 풀기", () => pickAll(false)), count);
    if (c.check) bar.insertBefore(hBtn("확인 빼고 모두", () => pickAll((p) => !p.check), { title: "「확인」 이 붙지 않은 칸만 고릅니다(원본이 모두 값을 낸 칸)" }), count);
    if (c.fill) planBox.append(bar);
    if (adds) { // 더해서 넣기 — 묶지 않고 받을 표의 칸 차례로
      if (many.pairs.length) {
        const [t, tb] = hTable(["", "칸", "키", "지금 → 넣을 값"]);
        t.classList.add("tkv-list", "tkv-pairs");
        for (const p of many.pairs) tb.append(pairRow(p, { refs, off, on, boxes, sync, from: (p.parts[0] || {}).cell || null, out }));
        planBox.append(t);
      } else planBox.append(el("p", "hnote", "키가 꼭 같은 칸이 없습니다."));
    }
    // 값마다 묶어(기준 없이면 원본 표마다) — 「2차년도 — 넣을 수 있음 12 · 겹침 0」
    const parts = adds ? [] : g ? many.groups.map((x) => ({ title: x.label, k: x.counts, rows: many.pairs.filter((p) => p.value === x.value) }))
      : many.groups.map((x, i) => ({ title: `원본 표 ${x.table}`, k: x.counts, rows: many.pairs.filter((p) => p.src === i) }));
    for (const part of parts) {
      const d = el("details", "hblock tkv-group"), s = el("summary", null), k = part.k;
      d.open = true;
      s.append(el("b", null, part.title), el("span", "muted", ` — 넣을 수 있음 ${nf(k.fill)} · 겹침 ${nf(k.clash)}${k.same ? ` · 같음 ${nf(k.same)}` : ""}${k.calc ? ` · 수식 칸 ${nf(k.calc)}` : ""}${k.emptySrc ? ` · 원본 빈 칸 ${nf(k.emptySrc)}` : ""}`));
      d.append(s);
      if (!part.rows.length) d.append(el("p", "hnote", "키가 꼭 같은 칸이 없습니다."));
      else {
        const [t, tb] = hTable(["", "칸", "키", "지금 → 넣을 값", "원본"]);
        t.classList.add("tkv-list", "tkv-pairs");
        for (const p of part.rows) tb.append(pairRow(p, { refs, off, on, boxes, sync, from: p.from.cell, src: p.from.table, out }));
        d.append(t);
      }
      planBox.append(d);
    }
    if (!parts.length && !adds) planBox.append(el("p", "hnote", g ? "값이 정해진 원본 표가 없습니다 — 위에서 원본 표마다 값을 고르세요." : "짝지을 값 칸이 없습니다."));
    sync();
    // 짝 없는 항목(읽기만 — 짝짓기 · 매핑 규칙은 원본 표 하나를 기준 없이 가져올 때)
    const us = many.unmatched.src, ud = many.unmatched.dst;
    if (us.length || ud.length) {
      const d = el("details", "hblock tkv-left"), s = el("summary", null);
      s.append(el("b", null, "짝 없는 항목"), el("span", "muted", ` · 원본 표에만 ${nf(us.length)} · 이 표에만 ${nf(ud.length)}`));
      d.append(s);
      for (const [title, items, mine] of [["원본 표에만", us, false], ["이 표에만", ud, true]]) {
        if (!items.length) continue;
        d.append(el("h4", "tkv-side", `${title} ${nf(items.length)}`));
        const [t, tb] = hTable(mine ? ["칸", "키", "값"] : ["원본", "칸", "키", "값"]);
        t.classList.add("tkv-list", "tkv-unmatched");
        for (const it of items) {
          const tr = el("tr", "tkv-dim"), c1 = el("td"), c2 = el("td", "wrap tkv-key"), c3 = el("td", "wrap tkv-val");
          if (!mine) tr.append(el("td", "tkv-srccol", it.table));
          c1.append(link(it.ref, () => tblKvGo(mine ? tid : it.table, it.cell), "문서에서 그 칸으로"));
          if (it.key == null) c2.append(el("span", "muted", "키 없음")); else c2.textContent = it.label;
          c2.append(el("span", "tkv-why", it.why || ""));
          if (!it.text) c3.append(el("span", "muted", "(빈 칸)")); else c3.append(valueEl(it.text, null));
          tr.append(c1, c2, c3);
          hover(tr, mine ? it.cell : null, mine ? null : it.cell);
          tb.append(tr);
        }
        d.append(t);
      }
      planBox.append(d);
    }

    async function apply() {
      const todo = boxes.filter(([cb]) => cb.checked).map(([, p]) => p);
      if (!todo.length || busy) return;
      busy = true;
      sync();
      tblKvHit();
      structOp.lastError = null;
      const sigs = Object.fromEntries(many.pairs.map((p) => [p.to, p.sig]));
      const body = { from: many.sources.map((x) => ({ table: x.table, ...(x.value ? { value: x.value } : {}) })), ...(adds ? { mode: "sum" } : g ? { group: { basis: g.basis, on: g.on, level: g.level } } : {}), // 계획이 정한 값 그대로 — 반영 때 다시 권하지 않게
        cells: todo.map((p) => p.to), rev: many.rev, sigs };
      const out = await structOp(`tables/${encodeURIComponent(tid)}/kv/apply`, body); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
      busy = false;
      if (!out || !out.mapped) { // 409 = 계획을 본 뒤 문서 · 규칙이 바뀜 — 다시 읽는다
        if (live()) { if (structOp.lastError && structOp.lastError.status === 409) load(); else sync(); }
        return;
      }
      const m = out.mapped, skip = m.skipped || [];
      toast(`표 ${tid} — ${nf((m.done || []).length)}칸에 값을 넣었습니다${skip.length ? ` · 건너뜀 ${nf(skip.length)}(${skip[0].why})` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
      for (const p of todo) on.delete(`${p.to}|${p.sig}`); // 넣은 「확인」 줄은 다시 꺼 둔다 — 다시 받은 계획(지금 값에서 또 셈한 것)을 사람이 다시 보고 고르게(두 번 더해지지 않게)
      recalcAuto = true; // 값을 넣었다 — 계산 칸을 저절로 다시 읽는다
      if (live()) load(); // 넣은 뒤 다시 읽고 계획도 다시(넣은 칸은 「같음」)
    }
  }

  // ---- 다른 표로 나눠 넣기(일대다 — 묶어 넣기의 반대): 이 표에 구분 기준의 값 머리가 있을 때만 ------------------------------------------------
  function drawSplitFrom() {
    const bases = [...new Set((view.bases || []).map((b) => b.basis))];
    if (!bases.length) { splitFromBox.replaceChildren(); return; } // 기준이 없는 표 — 나눌 것이 없다(묶음을 안 보인다)
    const head = el("div", "tkv-h"), row = el("div", "ta-row"), find = el("input"), list = el("ul", "tkv-tgts"), count = el("span", "muted tkv-count");
    const go = hBtn("나눠 넣기", () => ask(), { cls: "btn sm tkv-split-get", title: `이 표의 ${bases.map((b) => TKV_BASIS[b]).join(" · ")} 머리글 아래 값을 고른 받을 표들에 나눠 넣는 계획을 봅니다(문서는 안 바뀜) — 어느 기준으로 나눌지 묻습니다` });
    head.append(el("h3", null, "다른 표로 나눠 넣기"), hHelp("다른 표로 나눠 넣기 안내",
      "이 표에는 구분 기준의 머리글(「1차년도 | 2차년도」 · 기관 이름 …)이 있습니다 — 그 머리글 아래의 값을, 그 기준의 값마다 받을 표 여럿(그 머리글이 없는 표: 한 기관 · 한 차년도의 표)에 나눠 넣습니다.\n받을 표를 고르고 「나눠 넣기」 를 누르면 어느 기준으로 나눌지 묻고, 받을 표마다 어느 값의 것인지 읽어 권합니다(맞지 않으면 고쳐 고르세요).\n넣는 것은 고른 빈 칸뿐입니다 — 받을 표의 칸에 다른 글이 있으면 덮지 않고, 수식으로 셈하는 칸에는 넣지 않습니다. 받을 표 여럿에 한 번의 편집으로 넣습니다(실행 취소 한 번)."));
    const cands = tables.filter((t) => t.id !== tid && t.cells > 1 && !(typeof tempTableItem === "function" && tempTableItem(t.id)));
    const sp = tblKv.split[tid], sel = new Set(sp ? sp.tables.filter((id) => cands.some((t) => t.id === id)) : []);
    const sync = () => { count.textContent = sel.size ? `${nf(sel.size)}개 고름` : ""; go.disabled = !sel.size; };
    find.type = "search";
    find.className = "tkv-find";
    find.placeholder = "표 번호 · 글";
    find.setAttribute("aria-label", "받을 표 찾기");
    list.setAttribute("role", "group");
    list.setAttribute("aria-label", "받을 표(여럿 고를 수 있습니다)");
    const rows = cands.map((t) => {
      const li = el("li"), lab = el("label"), cb = el("input");
      cb.type = "checkbox";
      cb.value = t.id;
      cb.checked = sel.has(t.id);
      cb.onchange = () => { if (cb.checked) sel.add(t.id); else sel.delete(t.id); sync(); };
      lab.title = t.hint || t.label;
      lab.append(cb, el("span", null, t.label));
      li.append(lab);
      list.append(li);
      return [li, t];
    });
    find.oninput = () => {
      const q = oneLine(find.value).toLowerCase();
      for (const [li, t] of rows) li.hidden = !!q && !sel.has(t.id) && !`${t.label} ${t.hint}`.toLowerCase().includes(q);
    };
    const ask = () => { // 기준 고르기 창 — 이 표의 기준(단추 아래의 작은 메뉴)
      const picked = cands.filter((t) => sel.has(t.id)).map((t) => t.id);
      if (!picked.length) return;
      const run = (basis) => { tblKv.split[tid] = { tables: picked, basis, values: {} }; splitLoad(); };
      const r = go.getBoundingClientRect();
      ctxOpen({ clientX: Math.round(r.left), clientY: Math.round(r.bottom + 3) }, bases.map((b) => [TKV_BY[b], "", () => run(b), false]));
      [...ctxMenu().querySelectorAll("button")].forEach((b, i) => {
        const vals = (view.bases.find((x) => x.basis === bases[i]) || { values: [] }).values.map((v) => v.label);
        b.title = `이 표의 ${TKV_BASIS[bases[i]]} 머리글(${tblKvCut(vals.join(" · "), 60)}) 아래 값을, 그 값의 받을 표에 나눠 넣습니다 — 받을 표가 어느 값의 것인지는 다음에 고칠 수 있습니다`;
      });
    };
    sync();
    row.append(el("span", "tkv-lab", "받을 표"), find, go, count);
    splitFromBox.replaceChildren(head, row, cands.length ? list : el("p", "hnote", "이 문서에 다른 표가 없습니다."));
  }
  function drawSplit() { // 나눠 넣는 계획 — 받을 표마다 「어느 값의 것」 · 받을 표마다 묶은 짝
    splitBox.textContent = "";
    if (!split) return;
    const sp = tblKv.split[tid], c = split.counts, g = split.group, refs = new Map(split.pairs.map((p) => [p.to.cell, p.ref]));
    const offKey = `${tid}>${split.targets.map((x) => x.table).join(",")}|${g.basis}`, off = tblKv.off[offKey] || (tblKv.off[offKey] = new Set()), on = tblKv.on[offKey] || (tblKv.on[offKey] = new Set());
    const head = el("div", "ta-ident tkv-planhead"), kind = el("span", "hb tkv-type", `${TKV_BY[g.basis]} 나눔`);
    kind.title = `이 표의 ${TKV_BASIS[g.basis]} 머리글(${tblKvCut(g.values.map((v) => v.label).join(" · "), 60)}) 아래 값을 그 값의 받을 표에 나눠 넣습니다\n받을 표가 어느 값의 것인지는 아래 줄에서 고칩니다 — 값이 정해지지 않은 받을 표에는 넣지 않습니다`;
    head.append(el("span", "muted", "이 표"), el("b", null, tid), el("span", "muted", `→ 받을 표 ${nf(split.targets.length)}개`), kind);
    const sbox = el("section", "tkv-values"), sh = el("div", "tkv-h");
    sh.append(el("h3", null, `받을 표가 어느 ${TKV_BASIS[g.basis]}의 것인지`), hHelp("받을 표의 값 안내", `받을 표마다 이 표의 ${TKV_BASIS[g.basis]} 머리글 가운데 어느 것의 표인지 정합니다 — 그 머리글 아래의 값만 그 표에 넣습니다.\n편집 구역(그 표가 놓인 기관 · 차년도 · 단계) → 표의 소속(구분 줄) → 표 앞 글, 차례로 읽어 권합니다. 맞지 않으면 고쳐 고르세요.\n못 읽은 받을 표에는 값을 고를 때까지 넣지 않습니다(어림으로 넣지 않습니다).`));
    const [st, stb] = hTable(["받을 표", TKV_BASIS[g.basis], "어디서 읽었나", "넣을 수 있음"]);
    st.classList.add("tkv-list", "tkv-targets");
    for (const x of split.targets) {
      const tr = el("tr", x.why ? "warn" : null), c0 = el("td", "wrap"), c1 = el("td"), c2 = el("td", "wrap"), sel = el("select"), none = el("option", null, x.by === "user" ? "권한 값으로(다시 읽기)" : "고르세요");
      c0.append(link(x.table, () => tblKvGo(x.table), "문서에서 받을 표로"), " ", el("span", "muted", nameOf(x.table)));
      if (x.source === "template") c0.append(" ", tplTag("받을 표"));
      if (x.rules) { const b = el("span", "hb chg", "규칙"); b.title = `매핑 규칙 「${x.rules.name}」 — 이 규칙으로 이어진 칸 ${nf(x.rules.used)}`; c0.append(" ", b); }
      sel.className = "tkv-value";
      sel.setAttribute("aria-label", `받을 표 ${x.table} 의 ${TKV_BASIS[g.basis]}`);
      none.value = "";
      sel.append(none);
      for (const v of g.values) { const o = el("option", null, v.label); o.value = v.part; sel.append(o); }
      sel.value = x.value || "";
      sel.title = "이 받을 표가 어느 값의 것인지 고릅니다 — 고르면 계획을 다시 세웁니다(문서는 안 바뀜)";
      sel.onchange = () => { if (sel.value) sp.values[x.table] = sel.value; else delete sp.values[x.table]; splitLoad(); };
      c1.append(sel);
      c2.append(el("span", x.value ? "muted" : "tkv-warn", x.value ? TKV_READ[x.by] || "" : "못 읽음 — 값을 고르세요"));
      if (x.why && x.value) c2.append(el("span", "tkv-why", x.why));
      tr.append(c0, c1, c2, el("td", null, nf(x.counts.fill)));
      stb.append(tr);
    }
    sbox.append(sh, st);
    const psum = el("p", "hnote tkv-sum tkv-splitsum", `넣을 수 있음 ${nf(c.fill)} · 같음 ${nf(c.same)} · 겹침 ${nf(c.clash)} · 짝 없음 ${nf(c.unmatched)}${c.calc ? ` · 수식 칸 ${nf(c.calc)}` : ""}${c.emptySrc ? ` · 원본 빈 칸 ${nf(c.emptySrc)}` : ""}`);
    psum.title = `넣을 수 있음 = 받을 표의 칸이 비었고 이 표에 값이 있음 · 같음 = 두 칸의 글이 같음 · 겹침 = 받을 표의 칸에 다른 글이 있음(덮지 않습니다)\n짝 없음 = 이 표에만 ${nf(c.unmatchedSrc)} · 받을 표에만 ${nf(c.unmatchedDst)}`;
    const held = split.held || [], bar = el("div", "ta-row tkv-splitbar"), count = el("span", "muted"), boxes = [];
    const applyBtn = hBtn("", () => apply(), { cls: "btn sm primary", title: "고른 칸에 이 표의 값을 넣습니다 — 받을 표 여럿에 한 번의 편집(도구 줄 「실행 취소」 로 한꺼번에 되돌림). 계획을 본 뒤 달라진 칸은 건너뜁니다" });
    const sync = () => {
      const n = boxes.filter(([cb]) => cb.checked).length;
      applyBtn.textContent = `고른 ${nf(n)}칸 넣기`;
      applyBtn.disabled = !n || busy || state.busy || !!held.length;
      count.textContent = `${nf(n)} / ${nf(c.fill)}`;
    };
    const pickAll = (v) => { for (const [cb, , set] of boxes) { cb.checked = v; set(v); } sync(); };
    bar.append(applyBtn, hBtn("모두", () => pickAll(true), { title: "넣을 수 있는 칸을 모두 고릅니다" }), hBtn("모두 풀기", () => pickAll(false)), count);
    splitBox.append(head, sbox, psum, divChips(split.bases, drawSplit));
    const out = divOut();
    if (held.length) splitBox.append(el("p", "hnote tkv-held", `받을 표 ${[...new Set(held.map((h) => h.table))].join(" · ")} 의 헤더 지정 ${nf(held.length)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요(그때까지 넣지 않습니다)`));
    if (c.fill) splitBox.append(bar);
    split.groups.forEach((grp) => { // 받을 표마다 묶어 — 「받을 표 t12 · 주관연구개발기관 — 넣을 수 있음 6 · 겹침 0」
      const d = el("details", "hblock tkv-sgroup"), s = el("summary", null), k = grp.counts, rows = split.pairs.filter((p) => p.to.table === grp.table);
      d.open = true;
      s.append(el("b", null, `받을 표 ${grp.table} · ${grp.label}`), el("span", "muted", ` — 넣을 수 있음 ${nf(k.fill)} · 겹침 ${nf(k.clash)}${k.same ? ` · 같음 ${nf(k.same)}` : ""}${k.calc ? ` · 수식 칸 ${nf(k.calc)}` : ""}${k.emptySrc ? ` · 원본 빈 칸 ${nf(k.emptySrc)}` : ""}`));
      d.append(s);
      if (!rows.length) d.append(el("p", "hnote", "키가 꼭 같은 칸이 없습니다."));
      else {
        const [t, tb] = hTable(["", "칸", "키", "지금 → 넣을 값", "원본 칸"]);
        t.classList.add("tkv-list", "tkv-pairs");
        for (const p of rows) tb.append(pairRow(p, { refs, off, on, boxes, sync, from: p.from, src: p.fromRef, out }));
        d.append(t);
      }
      splitBox.append(d);
    });
    if (!split.groups.length) splitBox.append(el("p", "hnote", "값이 정해진 받을 표가 없습니다 — 위에서 받을 표마다 값을 고르세요."));
    sync();
    const us = split.unmatched.src, ud = split.unmatched.dst;
    if (us.length || ud.length) { // 짝 없는 항목(읽기만)
      const d = el("details", "hblock tkv-left"), s = el("summary", null);
      s.append(el("b", null, "짝 없는 항목"), el("span", "muted", ` · 이 표에만 ${nf(us.length)} · 받을 표에만 ${nf(ud.length)}`));
      d.append(s);
      for (const [title, items, mine] of [["이 표에만", us, true], ["받을 표에만", ud, false]]) {
        if (!items.length) continue;
        d.append(el("h4", "tkv-side", `${title} ${nf(items.length)}`));
        const [t, tb] = hTable(mine ? ["칸", "키", "값"] : ["받을 표", "칸", "키", "값"]);
        t.classList.add("tkv-list", "tkv-unmatched");
        for (const it of items) {
          const tr = el("tr", "tkv-dim"), c1 = el("td"), c2 = el("td", "wrap tkv-key"), c3 = el("td", "wrap tkv-val");
          if (!mine) tr.append(el("td", "tkv-srccol", it.table));
          c1.append(link(it.ref, () => tblKvGo(mine ? tid : it.table, it.cell), "문서에서 그 칸으로"));
          if (it.key == null) c2.append(el("span", "muted", "키 없음")); else c2.textContent = it.label;
          c2.append(el("span", "tkv-why", it.why || ""));
          if (!it.text) c3.append(el("span", "muted", "(빈 칸)")); else c3.append(valueEl(it.text, null));
          tr.append(c1, c2, c3);
          hover(tr, mine ? null : it.cell, mine ? it.cell : null);
          tb.append(tr);
        }
        d.append(t);
      }
      splitBox.append(d);
    }

    async function apply() {
      const todo = boxes.filter(([cb]) => cb.checked).map(([, p]) => p);
      if (!todo.length || busy) return;
      busy = true;
      sync();
      tblKvHit();
      structOp.lastError = null;
      const body = { to: split.targets.map((x) => ({ table: x.table, ...(x.value ? { value: x.value } : {}) })), group: { basis: g.basis, on: g.on, level: g.level }, // 계획이 정한 값 그대로
        cells: todo.map((p) => ({ table: p.to.table, cell: p.to.cell })), rev: split.rev, sigs: Object.fromEntries(split.pairs.map((p) => [p.to.cell, p.sig])) };
      const out = await structOp(`tables/${encodeURIComponent(tid)}/kv/split/apply`, body); // 받을 표 여럿에 한 번의 편집 — 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
      busy = false;
      if (!out || !out.mapped) {
        if (live()) { if (structOp.lastError && structOp.lastError.status === 409) load(); else sync(); }
        return;
      }
      const m = out.mapped, skip = m.skipped || [], n = new Set((m.done || []).map((x) => x.table)).size;
      for (const p of todo) on.delete(`${p.to.cell}|${p.sig}`); // 넣은 「확인」 줄은 다시 꺼 둔다
      toast(`표 ${tid} 의 값을 받을 표 ${nf(n)}개 · ${nf((m.done || []).length)}칸에 나눠 넣었습니다${skip.length ? ` · 건너뜀 ${nf(skip.length)}(${skip[0].why})` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
      if (live()) load();
    }
  }

  // ---- 매핑 규칙 — 쓰인 규칙 줄 · 짝짓기 -------------------------------------------------------------------------------------
  async function ruleSave(change, done) { // 묶음 초안을 고쳐(change) 바로 저장 → 계획 다시. 규칙이 하나도 안 남으면 묶음을 지운다
    if (busy || !plan) return;
    const src = plan.from.table;
    const draft = bundle
      ? { id: bundle.id, version: bundle.version, name: bundle.name, from: bundle.from, to: bundle.to, alias: bundle.alias.map((x) => ({ ...x })), pairs: bundle.pairs.map((x) => ({ ...x })), ops: (bundle.ops || []).map((x) => ({ ...x })) }
      : { name: tblKvCut(`${tblKvCut(nameOf(src), 24)} → ${tblKvCut(nameOf(tid), 24)}`, 60), from: { type: plan.types.from, label: labelOf(src) }, to: { type: plan.types.to, label: labelOf(tid) }, alias: [], pairs: [], ops: [] };
    change(draft);
    busy = true;
    try {
      if (draft.id && !draft.alias.length && !draft.pairs.length && !draft.ops.length) await api(`/api/table-maps/${encodeURIComponent(draft.id)}`, { method: "DELETE" });
      else await api("/api/table-maps", { method: "PUT", headers: H_JSON, body: JSON.stringify(draft) });
      if (done) toast(done);
    } catch (e) {
      toast(e.status === 409 ? "매핑 규칙이 그 사이 바뀌었습니다 — 다시 읽었습니다. 한 번 더 해 주세요" : `매핑 규칙을 저장하지 못했습니다: ${tblKvErr(e)}`, true);
    }
    busy = false;
    if (!live()) return;
    await planLoad();
    if (live()) mapsLoad();
  }
  // ---- 칸마다 넣는 방식(1대1 계획 — 매핑 규칙 묶음의 ops) -------------------------------------------------------------------------------------
  function opAsk(p, at) { // 줄의 「넣는 방식…」 — 어디에(이 칸만 | 이 머리글 아래 모두) → 어떻게(넷 가운데). 단추 아래의 작은 고르기 창 둘(화면을 덮지 않는다)
    const r = at.getBoundingClientRect(), where = { clientX: Math.round(r.left), clientY: Math.round(r.bottom + 3) };
    const [rk, ck] = tblKvParts(p.key), frags = [...new Set([...rk, ...ck])];
    const how = (kind, value, name) => () => setTimeout(() => ctxOpen(where, Object.keys(TKV_OP).map((op) => [TKV_OP_HOW[op], "", () => opSave(kind, value, op, name, frags, p.label), false])), 0);
    ctxOpen(where, [["이 칸만", "", how("key", p.key, `칸 「${tblKvCut(p.label, 40)}」`), false], null, ...frags.map((f) => [`머리글 「${tblKvCut(f, 30)}」 아래 모두`, "", how("part", f, `머리글 「${tblKvCut(f, 30)}」 아래`), false])]);
  }
  function opSave(kind, value, op, name, frags, label) { // 바로 저장 → 계획 다시. 「빈 칸에만」 은 적어 둘 까닭이 있을 때만 남긴다(그 칸이 머리글의 방식 아래에 있어 그 칸만 되돌릴 때)
    ruleSave((d) => {
      d.ops = d.ops.filter((o) => o[kind] !== value);
      const under = kind === "key" && d.ops.some((o) => o.part != null && frags.includes(o.part));
      if (op !== "fill" || under) d.ops.push(kind === "key" ? { key: value, op, label } : { part: value, op });
    }, `${name} — 넣는 방식을 「${TKV_OP[op]}」 로 저장했습니다`);
  }
  function drawOps() { // 「넣는 방식」 묶음 — 이 두 표 타입의 규칙 묶음에 저장된 것 목록(머리글 · 칸 → 방식 · ✕)
    const list = bundle && bundle.ops ? bundle.ops : [];
    if (!list.length) return;
    const box = el("section", "tkv-ops"), head = el("div", "tkv-h"), ul = el("ul", "tkv-rule-list");
    head.append(el("h3", null, "넣는 방식"), hHelp("넣는 방식 안내",
      "받을 칸마다 값을 어떻게 넣을지를 정해 매핑 규칙에 저장해 둡니다 — 빈 칸에만(기본) · 더하기(지금 값 + 원본 값) · 빼기(지금 값 − 원본 값) · 덮어쓰기.\n계획의 줄에서 「넣는 방식…」 을 눌러 이 칸만 또는 이 머리글 아래 모두에 정합니다. 칸에 정한 것이 머리글에 정한 것보다 먼저이고, 머리글 둘에 걸리면 나중에 정한 것이 이깁니다.\n받을 칸에 이미 값이 있는 더하기 · 빼기 · 덮어쓰기는 「확인」 이 붙고 처음에는 고르지 않습니다(같은 매핑을 두 번 하면 두 번 셈해집니다). 수식으로 셈하는 칸에는 어느 방식도 넣지 않습니다."),
    el("span", "muted", `${nf(list.length)}개`));
    list.forEach((o, i) => {
      const li = el("li", "tkv-rule tkv-oprule"), x = el("button", "tkv-x", "✕"), part = o.part != null;
      const text = `${part ? `「${o.part}」 아래 모두` : o.label || o.key} → ${TKV_OP[o.op]}`;
      li.append(el("span", "hb", part ? "머리글" : "칸"), el("span", "tkv-rule-text", text), x);
      li.firstChild.title = part ? "이 표의 이 머리글 아래 칸 모두에 그 방식으로 넣습니다" : "이 표의 이 칸 하나에 그 방식으로 넣습니다(머리글에 정한 것보다 먼저)";
      x.type = "button";
      x.title = "이 넣는 방식 지우기 — 바로 저장하고 계획을 다시 세웁니다(문서는 안 바뀜 · 그 칸은 빈 칸에만으로 돌아갑니다)";
      x.setAttribute("aria-label", `넣는 방식 지우기 — ${text}`);
      x.onclick = () => ruleSave((d) => { d.ops.splice(i, 1); }, `넣는 방식 「${tblKvCut(text, 40)}」 를 지웠습니다`);
      ul.append(li);
    });
    box.append(head, ul);
    planBox.append(box);
  }

  // ---- 계산 칸 다시 계산 — 이 표의 수식 칸(합계 · 소계 · 코드 식 · 비율)을 수식대로 다시 셈해 넣는다 -------------------------------------------------------
  async function recalcLoad() {
    try {
      const p = await api(tblKvUrl(tid, "/recalc/plan"), { method: "POST" });
      if (!live()) return;
      recalc = p;
    } catch (e) {
      if (!live()) return;
      recalc = null;
      toast(`계산 칸을 다시 계산하지 못했습니다: ${tblKvErr(e)}`, true);
    }
    drawRecalc();
  }
  function drawRecalc() {
    recalcBox.textContent = "";
    const n = view ? view.items.filter((i) => i.calc).length : 0;
    if (!n) return; // 수식 칸이 없는 표 — 묶음이 없다
    const head = el("div", "tkv-h");
    head.append(el("h3", null, "계산 칸 다시 계산"), hHelp("계산 칸 다시 계산 안내",
      "합계 · 소계 · 비율처럼 다른 칸을 더하거나 나눠서 나오는 칸을 표의 수식대로 다시 셈해 넣습니다 — 한글 문서에는 살아 있는 수식이 없어, 값을 넣거나 고친 뒤 이 칸들은 따로 채워야 합니다.\n비어 있는 칸은 넣을 수 있고, 지금 값과 계산한 값이 다른 칸은 「확인」 이 붙어 처음에는 고르지 않습니다. 셈할 칸 가운데 빈 것이 있거나 두 수식(가로 · 세로)이 서로 다른 값을 내는 칸에는 넣지 않습니다.\n소계에 기대는 합계는 그 소계를 같이 넣을 때만 넣습니다. 지금 값이 계산과 다른 소계에 기대는 합계는 그 소계의 지금 값으로 셈한 것이라 「확인」 이 붙고, 그 소계를 같이 고치면 넣지 않습니다(넣은 뒤 다시 계산합니다).\n단위가 서로 다른 수(천원 · 백만원)는 더하지 않습니다. 넣기는 한 번의 편집입니다(실행 취소로 되돌림)."),
    el("span", "muted", `수식 칸 ${nf(n)}`), hBtn(recalc ? "다시 계산" : "다시 계산할 칸 보기", () => recalcLoad(), { cls: "btn sm tkv-recalc-get", title: "이 표의 수식 칸을 지금 문서의 값으로 다시 셈합니다(문서는 안 바뀜)" }));
    recalcBox.append(head);
    if (!recalc) { recalcBox.append(el("p", "hnote", "값을 넣은 뒤에는 저절로 다시 셈해 보입니다 — 지금 보려면 「다시 계산할 칸 보기」 를 누르세요.")); return; }
    const c = recalc.counts, todo = c.missing + c.mismatch, held = (recalc.held || []).length;
    const asks = recalc.items.filter((it) => (it.status === "missing" || it.status === "mismatch") && it.check).length; // 「확인」 이 붙은 줄 — 지금 값과 다름 · 다른 칸의 지금 값으로 셈함 · 단위가 섞임
    const rsum = el("p", "hnote tkv-sum tkv-recalcsum", `다시 계산할 칸 ${nf(todo)}${asks ? `(확인 ${nf(asks)})` : ""} · 같음 ${nf(c.ok)} · 셈할 칸이 빔 ${nf(c.incomplete)}${c.conflict ? ` · 두 수식이 다름 ${nf(c.conflict)}` : ""}`);
    rsum.title = "다시 계산할 칸 = 비어 있어 계산한 값을 넣을 수 있는 칸 + 지금 값이 계산한 값과 다른 칸(확인 — 처음에는 고르지 않습니다)\n같음 = 지금 값이 계산한 값과 같음 · 셈할 칸이 빔 = 더할 칸 가운데 빈 것이 있어 못 셈 · 두 수식이 다름 = 그 칸의 가로 · 세로 수식이 서로 다른 값";
    recalcBox.append(rsum);
    if (recalc.more) recalcBox.append(el("p", "hnote", "더 풀 겹이 남았습니다 — 고른 칸을 넣은 뒤 다시 계산하면 이어서 풀립니다."));
    if (held) recalcBox.append(el("p", "hnote tkv-held", `헤더 지정 ${nf(held)}칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요(그때까지 넣지 않습니다).`));
    const rows = recalc.items.filter((it) => it.status !== "ok" && it.status !== "incomplete"), rest = recalc.items.filter((it) => it.status === "incomplete");
    const refs = new Map(recalc.items.map((it) => [it.cell, it.ref])), boxes = [];
    const want = (it) => (it.status !== "missing" && it.status !== "mismatch" ? false : it.check ? rOn.has(`${it.cell}|${it.sig}`) : !rOff.has(it.cell)); // 「확인」 이 붙은 줄은 켠 것만 — 그 계획의 그 값(sig)에 묶는다(다시 받은 계획에서 값이 달라졌으면 다시 보고 고르게)
    const bar = el("div", "ta-row tkv-bar tkv-recalcbar"), count = el("span", "muted");
    const applyBtn = hBtn("", () => apply(), { cls: "btn sm primary", title: "고른 칸에 계산한 값을 넣습니다 — 한 번의 편집(도구 줄 「실행 취소」 로 한꺼번에 되돌림). 계획을 본 뒤 달라진 칸은 건너뜁니다" });
    const sync = () => { // 기대는 칸을 따져 고른다 — needs(이번에 채울 칸)를 다 고른 줄만 · stale(지금 값으로 셈한 칸)을 같이 고치면 그 줄은 꺼진다
      const byCell = new Map(boxes.map(([, it]) => [it.cell, it])), memo = new Map();
      const on = (cell, path = []) => { // 그 칸을 넣을 것인가 — 기대는 칸부터 따진다(겹겹이)
        if (memo.has(cell)) return memo.get(cell);
        const it = byCell.get(cell);
        if (!it || path.includes(cell)) return false;
        const next = [...path, cell], v = want(it) && (it.needs || []).every((x) => on(x, next)) && !(it.stale || []).some((x) => on(x, next));
        memo.set(cell, v);
        return v;
      };
      const chosen = new Set(boxes.filter(([, it]) => on(it.cell)).map(([, it]) => it.cell));
      for (const [cb, it] of boxes) {
        const lone = (it.needs || []).filter((x) => !chosen.has(x)), fix = (it.stale || []).filter((x) => chosen.has(x));
        cb.checked = chosen.has(it.cell);
        cb.disabled = !!lone.length || !!fix.length;
        cb.title = fix.length ? `${fix.map((x) => refs.get(x) || x).join(" · ")} 를 고친 뒤 다시 계산합니다 — 넣은 뒤 다시 읽으면 새 값으로 나옵니다` : lone.length ? `이 값이 기대는 칸(${lone.map((x) => refs.get(x) || x).join(" · ")})을 먼저 고르세요` : "";
      }
      applyBtn.textContent = `고른 ${nf(chosen.size)}칸 넣기`;
      applyBtn.disabled = !chosen.size || busy || state.busy || !!held;
      count.textContent = `${nf(chosen.size)} / ${nf(todo)}`;
      return chosen;
    };
    const pick = (it, v) => { if (!it.check) { if (v) rOff.delete(it.cell); else rOff.add(it.cell); } else if (v) rOn.add(`${it.cell}|${it.sig}`); else rOn.delete(`${it.cell}|${it.sig}`); };
    const row = (it) => {
      const can = it.status === "missing" || it.status === "mismatch";
      const tr = el("tr", `tkv-r-${it.status}`), cb = el("input"), c0 = el("td"), c1 = el("td"), c2 = el("td", "wrap tkv-key", it.label || ""), c3 = el("td", "wrap tkv-val");
      cb.type = "checkbox";
      cb.disabled = !can;
      cb.setAttribute("aria-label", can ? `${it.ref} 다시 계산한 값 넣기 고르기` : `${it.ref} — 넣지 않는 칸`);
      if (can) { cb.onchange = () => { pick(it, cb.checked); sync(); }; boxes.push([cb, it]); }
      c0.append(cb);
      c1.append(link(it.ref, () => tblKvGo(tid, it.cell), "문서에서 그 칸으로"));
      const now = el("span", "tkv-now", it.now ? `지금 「${tblKvCut(it.now, 40)}」` : "지금 (빈 칸)"), fx = (f) => el("span", "tkv-how", ` (${f})`);
      if (can) {
        c3.append(now, el("span", "tkv-arrow", " → "), el("span", "tkv-lab2", "계산한 값 "), valueEl(it.text, "tkv-new"), fx(it.formula));
        if (it.check) {
          const w = el("span", "hb und", "확인");
          w.title = `${it.status === "mismatch" ? "지금 값이 계산한 값과 다릅니다" : (it.stale || []).length ? "다른 계산 칸의 지금 값으로 셈한 값입니다(그 칸은 계산과 다릅니다)" : "넣기 전에 볼 것이 있습니다"} — 맞으면 체크해서 넣으세요(처음에는 고르지 않습니다)`;
          c3.append(" ", w, el("span", "tkv-why", it.why || ""));
        }
        if ((it.needs || []).length) c3.append(el("span", "tkv-why", `${it.needs.map((x) => refs.get(x) || x).join(" · ")} 을(를) 같이 넣을 때의 값`));
      } else if (it.status === "conflict") {
        c3.append(el("span", "hb und", "두 수식이 다름"), " ", now, el("span", "muted", " · "), ...(it.both || []).flatMap((b, i) => [i ? el("span", "muted", " ≠ ") : "", el("span", "tkv-lab2", "계산한 값 "), valueEl(b.text, "muted"), fx(b.formula)]), el("span", "tkv-why", it.why || ""));
      } else {
        c3.append(el("span", "hb und", "셈할 칸이 빔"), " ", now, fx(it.formula), el("span", "tkv-why", it.why || ""));
      }
      if (it.note) c3.title = it.note;
      tr.append(c0, c1, c2, c3);
      hover(tr, it.cell);
      return tr;
    };
    bar.append(applyBtn, hBtn("모두", () => { for (const [, it] of boxes) pick(it, true); sync(); }, { title: "넣을 수 있는 칸을 모두 고릅니다(「확인」 줄도)" }), hBtn("모두 풀기", () => { for (const [, it] of boxes) pick(it, false); sync(); }), count);
    if (rows.length) {
      if (todo) recalcBox.append(bar);
      const [t, tb] = hTable(["", "칸", "키", "지금 → 계산한 값"]);
      t.classList.add("tkv-list", "tkv-pairs", "tkv-recalcs");
      for (const it of rows) tb.append(row(it));
      recalcBox.append(t);
    } else recalcBox.append(el("p", "hnote", c.ok ? "다시 계산할 칸이 없습니다 — 수식 칸의 값이 모두 계산한 값과 같습니다." : "다시 계산할 칸이 없습니다 — 셈할 칸이 비어 있습니다."));
    if (rest.length) {
      const d = el("details", "hblock tkv-recalcrest"), s = el("summary", null), [t, tb] = hTable(["", "칸", "키", "까닭"]);
      s.append(el("b", null, "셈할 칸이 비어 못 센 칸"), el("span", "muted", ` · ${nf(rest.length)}칸`));
      t.classList.add("tkv-list", "tkv-pairs");
      for (const it of rest) tb.append(row(it));
      d.append(s, t);
      recalcBox.append(d);
    }
    sync();

    async function apply() {
      const cells = [...sync()];
      if (!cells.length || busy) return;
      busy = true;
      sync();
      tblKvHit();
      structOp.lastError = null;
      const out = await structOp(`tables/${encodeURIComponent(tid)}/kv/recalc/apply`, { cells, rev: recalc.rev, sigs: Object.fromEntries(recalc.items.map((it) => [it.cell, it.sig])) });
      busy = false;
      if (!out || !out.mapped) { // 409 = 계획을 본 뒤 문서가 바뀜 — 다시 읽는다
        if (live()) { if (structOp.lastError && structOp.lastError.status === 409) load(); else sync(); }
        return;
      }
      const m = out.mapped, skip = m.skipped || [];
      for (const it of recalc.items) if ((m.done || []).includes(it.cell)) rOn.delete(`${it.cell}|${it.sig}`); // 넣은 「확인」 줄은 다시 꺼 둔다
      toast(`표 ${tid} — 계산 칸 ${nf((m.done || []).length)}칸에 다시 계산한 값을 넣었습니다${skip.length ? ` · 건너뜀 ${nf(skip.length)}(${skip[0].why})` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
      recalcAuto = true;
      if (live()) load();
    }
  }

  function leftOf() { // 짝 없는 항목 — 짝지을 수 있는 것(키가 있고 그 표에서 하나뿐)과 두 쪽 모두에 그런 항목이 있는가(can)
    const us = plan.unmatched.src, ud = plan.unmatched.dst, sd = new Set(plan.from.dups || []), dd = new Set(view.dups || []);
    const okS = (it) => it.key != null && !sd.has(it.key), okD = (it) => it.key != null && !dd.has(it.key);
    return { us, ud, okS, okD, any: us.length + ud.length > 0, can: us.some(okS) && ud.some(okD) };
  }
  function drawRules(left) {
    const box = el("section", "tkv-rules"), head = el("div", "tkv-h"), used = plan.rules ? plan.rules.used : 0;
    head.append(el("h3", null, "매핑 규칙"), hHelp("매핑 규칙 안내",
      "키가 서로 다른 칸을 어느 키로 읽을지를 규칙으로 저장해 둡니다 — 두 표 타입의 짝마다 하나이고, 같은 두 타입의 표면 다른 문서에서도 다시 쓰입니다.\n타입 = 머리글(음영 칸의 글)이 같은 표끼리 같은 타입입니다(값을 채워도 바뀌지 않습니다). 같은 타입끼리도 규칙을 둘 수 있습니다(「1차년도 › 현금」 ↔ 「2차년도 › 현금」).\n머리글 바꿔 읽기 = 원본 표의 그 머리글 아래 칸을 모두 이 표의 그 머리글 아래로 읽습니다.\n칸 짝 = 그 칸 하나만 짝짓습니다(바꿔 읽기보다 먼저).\n규칙은 짝만 정합니다 — 넣는 것은 고른 빈 칸뿐이고, 칸에 다른 글이 있으면 덮지 않습니다."));
    if (bundle) head.append(el("span", "muted", `${bundle.name} · 이 규칙으로 이어진 칸 ${nf(used)}`));
    box.append(head);
    const rules = bundle ? [...bundle.alias.map((a, i) => ["alias", a, i]), ...bundle.pairs.map((p, i) => ["pair", p, i])] : [];
    if (!rules.length) box.append(el("p", "hnote", left.can ? "이 두 표 타입의 규칙이 없습니다 — 아래 「짝 없는 항목」 에서 원본 표의 항목 하나와 이 표의 항목 하나를 골라 짝지으면 저장됩니다."
      : "이 두 표 타입의 규칙이 없습니다 — 짝지을 수 있는 항목(키가 있고 그 표에서 하나뿐인 칸)이 두 표에 함께 있어야 규칙을 만들 수 있습니다."));
    else {
      const ul = el("ul", "tkv-rule-list");
      for (const [kind, r, i] of rules) {
        const li = el("li", "tkv-rule"), x = el("button", "tkv-x", "✕");
        const text = kind === "alias" ? `${r.from} → ${r.to}` : `${r.fromLabel || r.from} → ${r.toLabel || r.to}`;
        li.append(el("span", "hb", kind === "alias" ? "머리글" : "칸 짝"), el("span", "tkv-rule-text", text), x);
        li.firstChild.title = kind === "alias" ? "머리글 바꿔 읽기 — 원본 표의 이 머리글 아래 칸을 모두 이 표의 그 머리글 아래로 읽습니다" : "칸 짝 — 원본 표의 이 키 하나를 이 표의 그 키 하나에";
        x.type = "button";
        x.title = "이 규칙 지우기 — 바로 저장하고 계획을 다시 세웁니다(문서는 안 바뀜)";
        x.setAttribute("aria-label", `규칙 지우기 — ${text}`);
        x.onclick = () => ruleSave((d) => { (kind === "alias" ? d.alias : d.pairs).splice(i, 1); }, `규칙 「${tblKvCut(text, 40)}」 를 지웠습니다`);
        ul.append(li);
      }
      box.append(ul);
    }
    planBox.append(box);
  }
  function drawLeft({ us, ud, okS, okD, any, can }) { // 짝 없는 항목 — 두 쪽 모두에 짝지을 수 있는 항목이 있으면(can) 원본 하나 · 이 표 하나를 골라 짝짓는다(타입이 같든 다르든)
    if (!any) return;
    const src = plan.from.table;
    const d = el("details", "hblock tkv-left"), s = el("summary", null);
    d.open = can;
    s.append(el("b", null, "짝 없는 항목"), el("span", "muted", ` · 원본 표에만 ${nf(us.length)} · 이 표에만 ${nf(ud.length)}`));
    d.append(s);
    const chosen = { s: null, d: null }, bar = el("div", "tkv-pairbar");
    const side = (title, items, ok, which, name) => {
      if (!items.length) return;
      d.append(el("h4", "tkv-side", `${title} ${nf(items.length)}`));
      const [t, tb] = hTable(can ? ["", "칸", "키", "값"] : ["칸", "키", "값"]);
      t.classList.add("tkv-list", "tkv-unmatched");
      if (can) t.classList.add("tkv-pickable"); // 첫 열 = 고르는 동그라미
      for (const it of items) {
        const tr = el("tr", ok(it) ? null : "tkv-dim"), c1 = el("td"), c2 = el("td", "wrap tkv-key"), c3 = el("td", "wrap tkv-val");
        if (can) {
          const c0 = el("td"), rb = el("input");
          rb.type = "radio";
          rb.name = name;
          rb.disabled = !ok(it);
          rb.setAttribute("aria-label", `${title} ${it.ref} 고르기`);
          rb.onchange = () => { chosen[which] = it; drawBar(); };
          c0.append(rb);
          tr.append(c0);
        }
        c1.append(which === "d" ? link(it.ref, () => tblKvGo(tid, it.cell), "문서에서 그 칸으로") : link(it.ref, () => tblKvGo(src, it.cell), "문서에서 원본 표의 그 칸으로"));
        if (it.key == null) c2.append(el("span", "muted", "키 없음"));
        else { c2.textContent = it.label; if (it.as) { const b = el("span", "hb chg", "바꿔 읽음"); b.title = `매핑 규칙으로 「${it.as}」 로 읽었지만 이 표에 그 키가 없습니다`; c2.append(" ", b); } }
        if (!ok(it) || !can) c2.append(el("span", "tkv-why", it.why || ""));
        if (!it.text) c3.append(el("span", "muted", "(빈 칸)")); else c3.append(valueEl(it.text, null));
        tr.append(c1, c2, c3);
        hover(tr, which === "d" ? it.cell : null, which === "s" ? it.cell : null);
        tb.append(tr);
      }
      d.append(t);
    };
    const drawBar = () => {
      bar.textContent = "";
      if (!can) return;
      const a = chosen.s, b = chosen.d;
      if (!a || !b) { bar.append(el("span", "muted", a ? "이 표의 항목도 하나 고르세요" : b ? "원본 표의 항목도 하나 고르세요" : "원본 표의 항목 하나와 이 표의 항목 하나를 고르면 짝지을 수 있습니다")); return; }
      bar.append(el("span", "tkv-pick", `원본 「${tblKvCut(a.label, 40)}」 → 이 표 「${tblKvCut(b.label, 40)}」`));
      const alias = tblKvAliasOf(a, b, bundle), row = el("div", "ta-row");
      const pair = () => ruleSave((dr) => { dr.pairs = dr.pairs.filter((x) => x.from !== a.key); dr.pairs.push({ from: a.key, to: b.key, fromLabel: a.label, toLabel: b.label }); }, "칸 짝을 매핑 규칙으로 저장했습니다");
      if (alias) {
        const g = tblKvAliasGain(alias, plan, a);
        const ab = hBtn(`머리글 바꿔 읽기 — 「${tblKvCut(alias.from, 20)}」 → 「${tblKvCut(alias.to, 20)}」${g.gain ? ` (다른 칸 ${nf(g.gain)}개도 함께)` : ""}`,
          () => ruleSave((dr) => { dr.alias.push({ from: alias.from, to: alias.to }); }, `머리글 바꿔 읽기 「${tblKvCut(alias.from, 20)} → ${tblKvCut(alias.to, 20)}」 를 매핑 규칙으로 저장했습니다`),
          { cls: "btn sm tkv-go", title: `원본 표의 머리글 「${alias.from}」 아래 칸을 모두 이 표의 「${alias.to}」 아래로 읽습니다 — 바로 저장하고 계획을 다시 세웁니다(문서는 안 바뀜)${g.lost ? `\n지금 이어진 ${nf(g.lost)}칸의 키도 바뀌어 짝이 풀릴 수 있습니다` : ""}` });
        row.append(ab, hBtn("이 칸만", pair, { title: "이 두 칸만 짝짓습니다(칸 짝) — 바로 저장하고 계획을 다시 세웁니다(문서는 안 바뀜)" }));
      } else row.append(hBtn("이 칸만 짝짓기", pair, { cls: "btn sm tkv-go", title: "이 두 칸만 짝짓습니다(칸 짝) — 바로 저장하고 계획을 다시 세웁니다(문서는 안 바뀜)\n두 키의 머리글 수가 같고 머리글 하나만 다르면 「머리글 바꿔 읽기」 도 고를 수 있습니다" }));
      bar.append(row);
    };
    side("원본 표에만", us, okS, "s", `tkvS${seq}`);
    side("이 표에만", ud, okD, "d", `tkvD${seq}`);
    if (can) { drawBar(); d.append(bar); }
    planBox.append(d);
  }

  // ---- 저장된 매핑 규칙(서버 전체) ---------------------------------------------------------------------------------------------
  function drawMaps() {
    const s = el("summary", null), was = mapsBox.open;
    s.append(el("b", null, "저장된 매핑 규칙"), el("span", "muted", ` ${nf(maps.length)}`));
    mapsBox.replaceChildren(s);
    mapsBox.open = was;
    if (!maps.length) { mapsBox.append(el("p", "hnote", "저장된 매핑 규칙이 없습니다 — 키가 다른 칸을 짝지으면 두 표 타입의 짝마다 하나씩 여기에 모입니다(문서에 묶이지 않고 서버 전체에서 같은 타입의 표에 다시 씁니다).")); return; }
    const ul = el("ul", "tkv-map-list");
    for (const m of maps) {
      const li = el("li", "tkv-map"), top = el("div", "tkv-map-top"), name = el("b", "tkv-map-name", m.name), btns = el("span", "tkv-map-acts");
      const meta = el("div", "tkv-map-meta", `${m.from.label || "원본 표"} → ${m.to.label || "대상 표"}`);
      const n = el("span", "muted", `머리글 ${nf(m.alias.length)} · 칸 짝 ${nf(m.pairs.length)}${(m.ops || []).length ? ` · 넣는 방식 ${nf(m.ops.length)}` : ""}`);
      meta.title = meta.textContent;
      const kind = el("span", "hb", m.from.type === m.to.type ? "같은 타입끼리" : "다른 타입");
      kind.title = "규칙 묶음은 원본 표 타입 → 대상 표 타입의 짝마다 하나입니다(머리글이 같은 표끼리 같은 타입) — 같은 두 타입의 표에 다시 쓰입니다";
      top.append(name, kind);
      if (usesMap(m.id)) { const b = el("span", "hb chg", "지금 쓰임"); b.title = "지금 보고 있는 두 표의 계획이 이 규칙을 씁니다"; top.append(b); }
      const rename = () => {
        const inp = el("input", "tkv-rename"), ok = hBtn("저장", () => save()), no = hBtn("취소", () => drawMaps());
        inp.type = "text";
        inp.value = m.name;
        inp.maxLength = 60;
        inp.setAttribute("aria-label", "매핑 규칙 이름");
        const save = async () => {
          const v = oneLine(inp.value);
          if (!v || v === m.name) { drawMaps(); return; }
          try { await api("/api/table-maps", { method: "PUT", headers: H_JSON, body: JSON.stringify({ ...m, name: v }) }); }
          catch (e) { toast(e.status === 409 ? "매핑 규칙이 그 사이 바뀌었습니다 — 다시 읽었습니다" : `이름을 바꾸지 못했습니다: ${tblKvErr(e)}`, true); }
          if (!live()) return;
          if (bundle && bundle.id === m.id) await planLoad(); // 묶음의 version 이 올랐다 — 쓰는 중인 묶음도 다시
          if (live()) mapsLoad();
        };
        inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); drawMaps(); } };
        top.replaceChildren(inp, ok, no);
        inp.focus();
        inp.select();
      };
      const remove = async () => {
        try { await api(`/api/table-maps/${encodeURIComponent(m.id)}`, { method: "DELETE" }); }
        catch (e) { toast(`지우지 못했습니다: ${tblKvErr(e)}`, true); if (live()) mapsLoad(); return; }
        // 확인 창 없이 지우고, 알림의 「되돌리기」 로 같은 내용의 묶음을 다시 만든다(design.md §18 — 창으로 묻지 않는다)
        toast(`매핑 규칙 「${tblKvCut(m.name, 30)}」 를 지웠습니다`, false, { label: "되돌리기", run: async () => {
          try { await api("/api/table-maps", { method: "PUT", headers: H_JSON, body: JSON.stringify({ name: m.name, from: m.from, to: m.to, alias: m.alias, pairs: m.pairs }) }); }
          catch (e) { toast(`되돌리지 못했습니다: ${tblKvErr(e)}`, true); }
          if (!live()) return;
          if (plan || many) await planGo();
          if (live()) mapsLoad();
        } });
        if (!live()) return;
        if (usesMap(m.id)) await planGo();
        if (live()) mapsLoad();
      };
      btns.append(hBtn("이름 바꾸기", rename), hBtn("지우기", remove, { title: "이 규칙 묶음을 지웁니다 — 지운 직후 알림의 「되돌리기」 로 되살릴 수 있습니다(문서는 안 바뀜)" }));
      li.append(top, meta, n, btns);
      ul.append(li);
    }
    mapsBox.append(ul);
  }

  await load();
}
