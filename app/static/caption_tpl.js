// 캡션 템플릿 「CN」(spec_hwpx_웹편집 ② §8-10) — 그림 아래 · 표 위의 캡션을 꼴이 같은 것끼리 묶은 템플릿 C1 · C2 …(개요 템플릿 「TN」 의 캡션 짝).
// 보이는 곳: ① 문서 쪽 왼쪽 여백의 표시 「C1」(캡션 줄마다 — app.js tplMarksDraw 가 captMarkOf 로 묻는다 · 「문서 표시」 를 켰을 때) ② 「템플릿 관계」 열·「템플릿」 탭의 트리 끝 「캡션 템플릿 n」 절
//   (app.js tplTreeDraw 가 captSection 을 붙인다): 템플릿 줄 [▸][C1] 「< … >」 · 그림 캡션 · 아래 45 → 「서식 n가지 · 대표 「…」 · 대표에 맞추기(m줄)」 → 펴면 서식 목록(대표 · 다른 서식 n — 대표와 다른 값 · 대표로 · 이 줄들만 맞추기 · 줄 목록).
// 자료: GET /api/docs/{id}/captions(문서 차례마다 다시 읽음) · 동작: PUT …/captions/{C}/rep(대표 정하기 — 문서는 안 바뀜 · 실행 취소 1) · POST …/captions/{C}/match(대표에 맞추기 — structOp).
// app.js · outline_match.js 다음에 읽힌다(el · hBtn · hHelp · api · toast · nf · short · state · heads · structOp · applyEditState · flushAll · refreshToolbar · refreshSaveState · tplMarksDraw ·
// tplRelOpen · headsParaLink · headsGo · olmDiffText · olmDiffTitle · olmText · olmNoText). 개요 템플릿의 카드 꾸밈(.olm-g · .olm-gh · .olm-diff …)을 같이 쓰되, 그쪽 코드가 전역으로 찾는 줄(.olm · li.olm-g.sel)과는
// 다른 이름을 쓴다(.capt-row · .capt-sel — olmRedraw 가 캡션 줄을 개요 레벨 줄로 알고 지우지 않게).
const CAPT = { data: null, rev: null, epoch: null, busy: null, asked: null, timer: 0, open: new Set(), lists: new Set(), openEpoch: null, sel: null, err: null };
// data = GET 의 답(templates · lines …) · rev/epoch = 그 답의 문서 차례·문서 · asked = 다시 읽기를 건 차례(같은 차례를 두 번 묻지 않는다) · open = 편 템플릿 · lists = 서식 목록을 편 템플릿 · sel = 여백 표시를 눌러 온 줄 {tpl, para}

const CAPT_HELP = "캡션 템플릿 CN — 그림 아래 · 표 위의 캡션을 꼴(대상 표·그림 + 레터)이 같은 것끼리 묶은 것입니다. 문서 왼쪽 여백의 「C1」 과 같은 번호입니다.\n"
  + "캡션 줄 = 표·그림에 붙인 캡션(개체 캡션)과, 본문에 문단으로 친 캡션(「표 1 …」·「그림 2 …」 꼴 또는 줄 전체가 「< 제목 >」 인 줄 — 바로 아래가 표 · 바로 위가 그림일 때).\n"
  + "레터가 다르면 다른 템플릿입니다(「<표 N>」 과 「표 N.」 · 「< … >」). 레터가 같으면 서식이 달라도 같은 템플릿의 「다른 서식」 이고 「대표에 맞추기」 로 맞춥니다 — 문단 모양 · 글자 모양 · 앞 빈칸 · 괄호와 그 안쪽 빈칸(번호와 제목은 그대로).\n"
  + "대표 = 사람이 정한 줄, 없으면 줄이 가장 많은 서식의 첫 줄. 작성요령(TEMP) 안의 글과 개요 줄(「TN Lk」)은 캡션 줄이 아닙니다.";
const CAPT_SIDE = { top: "위", bottom: "아래", left: "왼쪽", right: "오른쪽", own: "같은 문단" };

function captNow() { // 편 것·고른 줄은 문서마다 — 다른 문서를 열었으면 비운다
  if (CAPT.openEpoch !== state.epoch) { CAPT.open.clear(); CAPT.lists.clear(); CAPT.sel = null; CAPT.openEpoch = state.epoch; }
  return CAPT;
}
function captHave() { return CAPT.data && CAPT.epoch === state.epoch ? CAPT.data : null; } // 이 문서의 자료(옛 차례의 것이어도 — 번호·줄은 대개 그대로다)
function captFresh() { return !!captHave() && CAPT.rev === state.serverRev; }
function captTpl(cid) { const d = captHave(); return d ? (d.templates || []).find((t) => t.id === cid) || null : null; }
function captTake(r) { CAPT.data = r && !r.off ? r : null; CAPT.rev = r ? r.rev : null; CAPT.epoch = state.epoch; CAPT.err = null; }

function captLoad(force = false) { // 캡션 템플릿을 읽는다(같은 차례면 가진 것) → 자료 | null
  if (!state.id || state.format !== "hwpx") { CAPT.data = null; return Promise.resolve(null); }
  if (!force && captFresh()) return Promise.resolve(CAPT.data);
  if (CAPT.busy) return CAPT.busy;
  const id = state.id, epoch = state.epoch;
  CAPT.asked = `${epoch}|${state.serverRev}`;
  CAPT.busy = api(`/api/docs/${id}/captions`).then((r) => {
    if (epoch !== state.epoch) return null;
    captTake(r);
    return CAPT.data;
  }).catch((e) => { if (epoch === state.epoch) CAPT.err = e || true; return null; }).finally(() => { CAPT.busy = null; }); // 옛 서버(끝점 없음) · 일시 오류 — 가진 것 그대로
  return CAPT.busy;
}

function captRefresh(force = false) { // 문서를 열 때 · 오버레이를 다시 읽은 뒤(app.js outlineLoad) — 다시 읽고 여백 표시·열린 절을 다시 그린다
  clearTimeout(CAPT.timer);
  if (!state.id || state.format !== "hwpx") { CAPT.data = null; captRedraw(); return; }
  captLoad(force).then(() => captRedraw());
}
function captSoon() { // 문서 차례가 바뀐 뒤(app.js applyEditState) — 더 고치지 않으면 잠시 뒤 다시 읽는다. 캡션이 없는 문서에서 절도 안 보고 있으면 읽지 않는다(편집마다 문서를 훑지 않게)
  if (!state.id || state.format !== "hwpx" || !(captMarkCount() || document.querySelector(".tpl-tree .capt-sec"))) return;
  clearTimeout(CAPT.timer);
  const epoch = state.epoch;
  CAPT.timer = setTimeout(() => {
    if (epoch !== state.epoch || captFresh() || CAPT.asked === `${epoch}|${state.serverRev}`) return;
    captRefresh();
  }, 1500);
}
function captRedraw() {
  if (typeof tplMarksDraw === "function") tplMarksDraw();
  for (const old of document.querySelectorAll(".tpl-tree .capt-sec")) old.replaceWith(captSection());
}

// ---- 문서 쪽 왼쪽 여백의 표시 「C1」 ------------------------------------------------------------------------------------------------
function captMarkCount() { const d = captHave(); return d ? Object.keys(d.lines || {}).length : 0; }
function captMarkOf(pid) { // app.js tplMarksDraw — 그 문단이 캡션 줄이면 표시 {text 「C1」, title, cap(템플릿 id), para}, 아니면 null
  const d = captHave(), x = d ? (d.lines || {})[pid] : null;
  if (!x) return null;
  const t = captTpl(x.tpl) || {};
  const g = (t.groups || []).find((q) => (q.paras || []).includes(pid));
  const off = g && !g.rep && (g.diff || []).length; // 대표와 서식이 다른 줄(목록이 30줄에서 잘린 서식의 뒤 줄은 모른다 — 표시만 안 붙는다)
  const title = `캡션 템플릿 ${x.tpl} 「${t.name || ""}」 — ${t.kindName || ""} 캡션 ${nf(t.total)}줄${t.rep === pid ? "\n이 템플릿의 대표 줄" : ""}`
    + (off ? `\n대표와 다른 값 — ${g.diff.map(olmDiffPart).join(" · ")}` : "")
    + `\n${pid}\n누르면 「템플릿 관계」 의 캡션 템플릿에서 이 줄의 서식을 봅니다(대표 정하기 · 대표에 맞추기)`;
  return { text: off ? `${x.tpl} ≠` : x.tpl, title, no: null, und: false, lbl: false, cap: x.tpl, para: pid };
}

async function captOpen(cid, para = null) { // 여백 표시 「C1」 을 눌렀을 때 — 「템플릿 관계」 열을 열고 그 템플릿을 펴 그 줄이 든 서식을 표시한다
  captNow();
  CAPT.open.add(cid);
  CAPT.lists.add(cid);
  CAPT.sel = para ? { tpl: cid, para, epoch: state.epoch } : null;
  await tplRelOpen(); // 그래프(2단계)가 없으면 까닭을 알리고 열지 않는다
  await captLoad();
  captRedraw();
  const li = document.querySelector(`#headsDlgBody .capt-node[data-cap="${CSS.escape(cid)}"]`) || document.querySelector(`.tpl-tree .capt-node[data-cap="${CSS.escape(cid)}"]`);
  const card = li ? li.querySelector("li.capt-g.capt-sel") : null;
  if (card || li) (card || li).scrollIntoView({ block: "center" });
}

// ---- 「템플릿 관계」 의 「캡션 템플릿」 절 ----------------------------------------------------------------------------------------------
function captSection() { // app.js tplTreeDraw 가 트리 끝에 붙인다 → 절(.capt-sec). 캡션이 없는 문서 · docx 면 빈 절(숨김)
  const box = el("div", "capt-sec");
  const d = captHave();
  if (!state.id || state.format !== "hwpx") { box.hidden = true; return box; }
  if (!d) { // 아직 못 읽음 — 한 번 읽고 다시 그린다
    box.hidden = true;
    if (!CAPT.busy && CAPT.asked !== `${state.epoch}|${state.serverRev}`) captLoad().then((got) => { if (got) captRedraw(); });
    return box;
  }
  const list = d.templates || [];
  if (!list.length && !d.missed) { box.hidden = true; return box; }
  captNow();
  const h = el("h3", null, `캡션 템플릿 ${nf(list.length)}`);
  h.append(hHelp("캡션 템플릿 도움말", CAPT_HELP));
  box.append(h);
  const ul = el("ul", "trel capt-list");
  for (const t of list) ul.append(captNode(t));
  box.append(ul);
  if (d.missed) box.append(el("p", "hnote capt-missed", `묶음 개체에 붙은 캡션 ${nf(d.missed)}줄은 다루지 않습니다(화면에 문단으로 나오지 않는 캡션)`));
  if (!captFresh() && !CAPT.busy && CAPT.asked !== `${state.epoch}|${state.serverRev}`) captLoad().then((got) => { if (got) captRedraw(); }); // 옛 차례의 자료로 먼저 그리고, 새 자료가 오면 다시
  return box;
}

function captWhere(t) { // 「그림 캡션 · 아래 45」 · 「표 캡션 · 위 28 · 아래 1」
  const sides = Object.entries(t.sides || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${CAPT_SIDE[k] || k} ${nf(n)}`);
  return `${t.kindName} 캡션 · ${sides.join(" · ")}`;
}

function captNode(t) { // 템플릿 한 줄 — [▸] [C1] 「레터 꼴」 · 그림 캡션 · 아래 45 + 서식 줄(+ 편 서식 목록)
  const li = el("li", "trel-node capt-node k-cap");
  li.dataset.cap = t.id;
  const row = el("div", "trel-row");
  const tog = el("button", "htog", "▸");
  tog.type = "button";
  tog.setAttribute("aria-label", `${t.id} 펼치기·접기`);
  const num = el("button", "hb tplno capt-no", t.id);
  num.type = "button";
  num.title = `캡션 템플릿 ${t.id} — 누르면 서식 줄 펼치기·접기`;
  const name = el("span", "trel-name", `「${t.name}」`);
  const meta = el("span", "trel-meta", captWhere(t));
  const info = `${t.kindName} 캡션 ${nf(t.total)}줄 — 개체에 붙인 캡션 ${nf(t.struct)} · 문단으로 친 캡션 ${nf(t.text)}`
    + `\n꼴: ${{ label: "번호 붙은 머리(「표 N」·「그림 N」)", wrap: "줄 전체를 괄호로(「< 제목 >」)", note: "출처·주 줄", plain: "레터 없는 글" }[t.shape] || t.shape}`
    + (t.frozen ? `\n자동 번호·표지가 든 줄 ${nf(t.frozen)}개 — 맞출 때 글(빈칸·괄호)은 그대로 두고 모양만 맞춥니다` : "");
  row.append(tog, num, name, meta);
  const kinds = (t.groups || []).length;
  if (kinds > 1) { // 접혀 있어도 서식이 갈린 템플릿이 보이게
    const chip = el("span", "olm-sum warn capt-chip", `서식 ${kinds}가지`);
    chip.title = `대표와 서식이 다른 줄 ${nf(t.others)}개 — 펴면 「대표에 맞추기」`;
    row.append(chip);
  }
  row.append(hHelp(`${t.id} 캡션 템플릿 정보`, info, { note: true }));
  li.append(row);
  let body = null;
  const open = (on) => {
    if (on && !body) { body = captRow(t); li.append(body); }
    if (body) body.hidden = !on;
    tog.textContent = on ? "▾" : "▸";
    tog.setAttribute("aria-expanded", String(on));
    if (on) CAPT.open.add(t.id); else CAPT.open.delete(t.id);
  };
  tog.onclick = num.onclick = () => open(!body || body.hidden);
  li._open = open;
  open(CAPT.open.has(t.id)); // 다시 그려도 편 채
  return li;
}

function captRow(t) { // 「서식 n가지 · 대표 「…」」 + 「▸ 서식 목록」 + 「대표에 맞추기(m줄)」 + 서식 목록(편 것만)
  const row = el("div", "capt-row");
  row.dataset.cap = t.id;
  const n = (t.groups || []).length, listed = CAPT.lists.has(t.id);
  row.classList.add(n > 1 ? "capt-warn" : "capt-ok");
  const sum = el("span", `olm-sum${n > 1 ? " warn" : ""}`, n > 1 ? `서식 ${n}가지` : "서식 1가지 — 모두 같음");
  sum.title = "이 템플릿의 캡션 줄을 앞 빈칸 · 레터(괄호·번호 머리) · 레터 뒤 빈칸 · 닫는 괄호 · 문단 모양(정렬·여백·간격·줄 간격) · 레터·본문 글자 모양이 같은 것끼리 묶었습니다";
  row.append(sum);
  if (t.rep) {
    const rep = el("span", "olm-rep");
    rep.append(el("span", "olm-rep-k", t.repSet ? "대표 " : "대표(가장 많은 서식) "),
      headsParaLink(t.rep, olmText(t.rep), 22, t.repSet ? "사람이 정한 대표 줄 — 「대표에 맞추기」 가 이 모양을 따릅니다" : "대표를 정하지 않아 줄이 가장 많은 서식의 첫 줄을 대표로 봅니다 — 다른 서식의 「대표로」 로 바꿉니다"));
    row.append(rep);
  }
  if (n > 1) {
    const tog = hBtn(listed ? "▾ 서식 목록" : "▸ 서식 목록", () => { if (CAPT.lists.has(t.id)) CAPT.lists.delete(t.id); else CAPT.lists.add(t.id); captRedraw(); },
      { title: "서식마다 대표와 다른 값 · 줄 목록 · 대표로 정하기", cls: "btn sm olm-btn" });
    tog.setAttribute("aria-expanded", String(listed));
    row.append(tog);
  }
  if (t.rep && t.others) {
    row.append(hBtn(`대표에 맞추기(${nf(t.others)}줄)`, () => captMatch(t.id, t.others),
      { title: "대표와 서식이 다른 이 템플릿의 캡션 줄 모두를 대표 모양으로 — 문단 모양 · 레터·본문 글자 모양 · 앞 빈칸 · 괄호와 그 안쪽 빈칸(번호와 제목 글은 그대로 · 강조한 글자도 그대로). 「실행 취소」 로 되돌립니다", cls: "btn sm primary olm-btn" }));
  }
  if (n === 1 && t.total > 1) { // 서식이 하나여도 줄로 갈 수 있게
    const det = el("details", "olm-paras");
    det.append(el("summary", null, `줄 ${nf(t.total)}`));
    det.append(captLines(t.groups[0]));
    row.append(det);
  }
  if (listed && n > 1) row.append(captList(t));
  return row;
}

function captLines(g) { // 그 서식의 줄 목록(30줄까지 — 누르면 문서의 그 캡션)
  const box = el("div", "olm-plist");
  for (const pid of g.paras || []) box.append(headsParaLink(pid, olmText(pid), 30));
  if (g.more) box.append(el("span", "muted", `… ${nf(g.more)}줄 더`));
  return box;
}

function captList(t) { // 서식 목록 — 대표 카드 → 다른 서식 1 · 2 …(대표와 다른 값 · 대표로 · 이 줄들만 맞추기 · 줄 목록)
  const ul = el("ul", "olm-list capt-glist");
  const sel = CAPT.sel && CAPT.sel.epoch === state.epoch && CAPT.sel.tpl === t.id ? CAPT.sel.para : null;
  let no = 0;
  for (const g of t.groups) {
    const li = el("li", `olm-g capt-g${g.rep ? " rep" : ""}${sel && (g.paras || []).includes(sel) ? " capt-sel" : ""}`);
    li.dataset.key = g.key;
    const head = el("div", "olm-gh");
    const first = sel && (g.paras || []).includes(sel) ? sel : g.key; // 여백 표시를 눌러 온 줄이 든 서식이면 그 줄을(「대표로」 도 그 줄)
    if (g.rep) head.append(el("span", "hb olm-badge", "대표"), el("span", "olm-n", `×${nf(g.count)}`));
    else {
      no += 1;
      head.append(el("span", "olm-no", olmNoText(no)), el("span", "olm-n", `×${nf(g.count)}`),
        hBtn("대표로", () => captSetRep(t.id, first), { title: `이 서식의 줄(${first})을 ${t.id} 의 대표로 — 문서는 안 바뀝니다`, cls: "btn sm olm-btn" }));
    }
    head.append(headsParaLink(first, olmText(first), 28));
    if (!g.rep && t.rep) head.append(hBtn("이 줄들만 맞추기", () => captMatch(t.id, g.count, g.key), { title: "이 서식의 캡션 줄들만 대표 모양으로", cls: "btn sm olm-btn" }));
    li.append(head);
    if (!g.rep && (g.diff || []).length) {
      const dv = el("div", "olm-diff", olmDiffText(g.diff));
      dv.title = olmDiffTitle(g.diff);
      li.append(dv);
    }
    if (g.count > 1) {
      const det = el("details", "olm-paras");
      det.append(el("summary", null, `줄 ${nf(g.count)}`));
      det.append(captLines(g));
      li.append(det);
    }
    ul.append(li);
  }
  return ul;
}

// ---- 대표 정하기 · 대표에 맞추기 ------------------------------------------------------------------------------------------------------
async function captSetRep(cid, pid) {
  if (state.busy || !state.id) return;
  const epoch = state.epoch, doc = state.id; // 문서는 기다리기 전에 잡는다(글 반영을 기다리는 사이 다른 문서를 열면 그 문서의 대표를 바꾸게 된다 — outline_match.js olmSetRep 과 같은 까닭)
  try {
    await flushAll();
    if (epoch !== state.epoch) return;
    const r = await api(`/api/docs/${doc}/captions/${encodeURIComponent(cid)}/rep`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ para: pid }) });
    if (epoch !== state.epoch) return;
    applyEditState(r);
    if (r.captions) captTake(r.captions);
    refreshToolbar(); // 실행 취소 단추(undo 수)
    refreshSaveState();
    captRedraw();
    toast(`${cid} 의 대표를 「${short(olmText(pid), 24)}」 로 정했습니다 — 「대표에 맞추기」 가 이 모양을 따릅니다(「실행 취소」 로 되돌림)`);
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); }
}

async function captMatch(cid, n, like = null) { // like = 그 서식의 줄 하나(그 서식만 맞출 때 — 화면이 가진 줄 목록은 30줄까지라 서버가 그 줄과 서식이 같은 줄을 모두 찾는다)
  const r = await structOp(`captions/${encodeURIComponent(cid)}/match`, like ? { like } : {});
  if (!r) return;
  if (r.captions) captTake(r.captions);
  captRedraw();
  if (r.nothing) { toast("맞출 줄이 없습니다 — 모두 대표와 같습니다"); captRefresh(true); return; }
  const done = (r.changed || []).length || n, held = (r.frozen || []).length;
  toast(`${cid} 캡션 ${nf(done)}줄을 대표 모양으로 맞췄습니다${held ? ` · 그 가운데 ${nf(held)}줄은 자동 번호·표지가 있어 글(빈칸·괄호)은 그대로 두고 모양만` : ""} — 「실행 취소」 로 되돌립니다`);
}
