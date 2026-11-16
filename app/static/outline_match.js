// 개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 「템플릿 관계」 열(app.js headsTplView)의 레벨 줄·템플릿 줄에 붙는다.
// 자료: GET /api/docs/{id}/outline/formats(레벨마다 서식 갈래 — 문서 차례(rev)마다 다시 읽음) · heads.outline(GET …/outline — 템플릿마다 hang·merged·into·partly, 레벨마다 rep·from).
// 동작: PUT …/outline/slots/{tpl}/{L}/rep(대표 정하기 — 문서는 안 바뀜 · 실행 취소 1) · POST …/slots/{tpl}/{L}/match(대표에 맞추기 — structOp) · POST …/outline/merge · unmerge(하위로 넣기 · 떼기) ·
//   POST …/slots/{tpl}/{L}/split · …/outline/unsplit(갈래를 서식 종속 템플릿 「T1L3a」 로 떼기 · 합치기 — ② §8-5: 갈래 줄의 「다른 템플릿으로」 · 레벨 줄의 「→ T1L3a(n줄) · 합치기」).
// 도구 줄 「서식」 묶음의 #tbTplRel(템플릿 관계 열 열기·닫기)도 여기서 잇는다. app.js 다음에 읽힌다(el·hBtn·api·toast·heads·state·structOp·applyEditState·tplMarksDraw·
// headsTplView·tplRelOpen·headsParaLink·headsColClose·colFolded·nf·short·oneLine·paraEl …). 훅: headsTplView 의 levels() 가 olmRow(id, L)·olmHidden(…) 을, make() 가 olmTplTools(…) 를,
// outlineLoad 가 olmRefresh() 를, tplRelOpen 이 olmFocus(at) 를 부른다.
const OLM = { data: null, rev: null, epoch: null, busy: null, pending: false, open: new Set(), mergeOpen: new Set(), splitOpen: new Set(), openEpoch: null, sel: null, pick: null }; // open = 갈래 목록을 편 레벨 「tpl|L」 · mergeOpen = 넣기 줄을 편 템플릿 · splitOpen = 「다른 템플릿으로」 줄을 편 갈래 「tpl|L|줄」 · sel = 표시할 줄

function olmOpenNow() { // 편 목록 기억(OLM.open·mergeOpen·splitOpen)은 문서마다 — 다른 문서를 열었으면 비운다
  if (OLM.openEpoch !== state.epoch) { OLM.open.clear(); OLM.mergeOpen.clear(); OLM.splitOpen.clear(); OLM.openEpoch = state.epoch; }
  return OLM;
}
function olmTpl(id) { return heads.outline && heads.outline.templates ? heads.outline.templates[String(id)] || null : null; }
function olmFresh() { return !!OLM.data && OLM.rev === state.serverRev && OLM.epoch === state.epoch; }
function olmSlotData(id, L) { return OLM.data && OLM.data[String(id)] ? OLM.data[String(id)][String(L)] || null : null; }

function olmLoad(force = false) { // 서식 갈래를 읽는다(같은 차례면 기억한 것) → 갈래 사전 | null
  if (!state.id || state.format !== "hwpx" || !heads.outline) { OLM.data = null; return Promise.resolve(null); }
  if (!force && olmFresh()) return Promise.resolve(OLM.data);
  if (OLM.busy) return OLM.busy;
  const id = state.id, epoch = state.epoch;
  OLM.busy = api(`/api/docs/${id}/outline/formats`).then((r) => {
    if (epoch !== state.epoch) return null;
    OLM.data = r && !r.off ? r.slots || {} : null;
    OLM.rev = r ? r.rev : null;
    if (r && r.keys) OLM.keys = r.keys; // 비교 값 차례·이름 [[키, 이름]…] — 「서식 비교」 창(outline_preview.js)의 열
    OLM.epoch = epoch;
    return OLM.data;
  }).catch(() => null).finally(() => { OLM.busy = null; });
  return OLM.busy;
}

// 대표와 다른 값 [[키, 이름, 대표, 이 갈래]…] → 「앞 공백: 지금 2칸 → 대표 1칸 · 2번째 줄: 지금 10.9mm → 대표 10.4mm」 — 값마다 이름표(지금 = 이 갈래 줄의 값 · 대표 = 대표 줄의 값),
// 화살표는 맞추면 바뀌는 방향(2026-11-15 사용자 「대표 값이 얼마고 현재 값이 얼마나 이렇게 해줘야지」 — 전에는 이름표 없이 「대표 → 이 갈래」 라 바뀌는 방향과 거꾸로 읽혔다)
const olmDiffPart = (d) => `${d[1]}: 지금 ${d[3]} → 대표 ${d[2]}`;
const olmDiffText = (diff, n = 4) => {
  const parts = (diff || []).map(olmDiffPart);
  return parts.length > n ? `${parts.slice(0, n).join(" · ")} 외 ${parts.length - n}` : parts.join(" · ");
};
const olmDiffTitle = (diff) => "대표와 다른 값 — 맞추면 이 갈래 줄의 지금 값이 대표 값으로 바뀝니다\n" + (diff || []).map(olmDiffPart).join("\n"); // 풍선 도움말 — 줄인 것 없이 전부
const olmText = (pid) => (state.texts && state.texts[pid] != null ? state.texts[pid] : (state.byId.get(pid) || {}).text || "");

function olmRow(id, L) { // 레벨 줄 아래 「서식 n가지 · 대표 「…」」 + 「대표에 맞추기(m줄)」 + 갈래 목록(편 것만) — 그 레벨에 줄이 없으면 null
  const t = olmTpl(id);
  const os = t && t.slots ? t.slots[String(L)] : null;
  if (!os || !os.lines) return null;
  const row = el("div", "olm");
  row.dataset.tpl = id;
  row.dataset.level = L;
  const v = olmFresh() ? olmSlotData(id, L) : null;
  if (!v) {
    row.append(el("span", "muted", olmFresh() ? "서식 갈래 없음" : "서식 갈래 읽는 중…"));
    olmNeed(); // 줄마다 부르지 않게 — 한 번 읽고 한 번 다시 그린다
    return row;
  }
  const n = v.groups.length, key = `${id}|${L}`, open = olmOpenNow().open.has(key);
  const repG = v.groups.find((g) => g.rep);
  const sum = el("span", `olm-sum${n > 1 ? " warn" : ""}`, n > 1 ? `서식 ${n}가지` : "서식 1가지 — 모두 같음");
  sum.title = "이 레벨 줄들을 레터(앞 공백·레터 글자·레터 뒤 공백) · 문단 모양(정렬·앞 여백·2번째 줄·간격·줄 간격) · 레터·본문 글자 모양이 같은 것끼리 묶었습니다";
  row.append(sum);
  if (v.rep) {
    const rep = el("span", "olm-rep");
    rep.append("대표 ", headsParaLink(v.rep, olmText(v.rep), 22, "이 레벨의 대표 줄 — 새 줄과 「대표에 맞추기」 가 이 모양을 따릅니다"));
    row.append(rep);
  } else if (v.repMissing) row.append(el("span", "hb und", "대표 없음 — 줄 하나를 대표로"));
  const tog = hBtn(open ? "▾ 갈래" : "▸ 갈래", () => { if (OLM.open.has(key)) OLM.open.delete(key); else OLM.open.add(key); olmRefresh(); },
    { title: "서식 갈래마다 대표와 다른 값 · 줄 목록 · 대표로 정하기", cls: "btn sm olm-btn" });
  tog.setAttribute("aria-expanded", String(open));
  if (n > 1 || v.repMissing) row.append(tog);
  if (typeof olpOpen === "function") { // 떠 있는 창에서 갈래를 표로 견줌(outline_preview.js — 모달 아님)
    row.append(hBtn(n > 1 ? "비교" : "서식 값", () => olpOpen(id, L, "cmp"),
      { title: n > 1 ? "서식 갈래를 표로 견줍니다 — 갈래마다 견본 글 · 대표와 다른 값만 · 갈래별 맞추기(옆에 떠 있는 창)" : "이 레벨 서식의 값(레터·문단·글자 모양)을 옆에 떠 있는 창으로", cls: "btn sm olm-btn olm-cmp" }));
  }
  const pick = olmPick(id, L);
  if (pick && pick.pid !== v.rep) { // 원문에서 고른 줄 — 문서 표를 누른 줄, 아니면 커서 줄
    row.append(hBtn(`${pick.how} 줄을 대표로`, () => olmSetRep(id, L, pick.pid), { title: `${pick.how} 줄(${pick.pid} 「${short(olmText(pick.pid), 24)}」)을 이 레벨의 대표로 정합니다 — 문서는 안 바뀝니다`, cls: "btn sm olm-btn" }));
  }
  if (v.rep && v.others) {
    row.append(hBtn(`대표에 맞추기(${nf(v.others)}줄)`, () => olmMatch(id, L, v.others),
      { title: "대표와 서식이 다른 이 레벨 줄 모두를 대표 모양으로 — 레터(앞 공백·글자·뒤 공백) · 문단 모양 · 레터·본문 바탕 글자 모양(강조한 글자는 그대로, 번호는 제 번호). 「실행 취소」 로 되돌립니다", cls: "btn sm primary olm-btn" }));
  }
  for (const sp of olmSplits(id, L)) { // 이 레벨에서 서식이 달라 뗀 템플릿 「→ T1L3a(6줄) · 합치기」(spec_hwpx_웹편집 ② §8-5)
    const chip = el("button", "olm-chip olm-vchip", `→ T${sp.no}(${nf(sp.lines)}줄)`);
    chip.type = "button";
    chip.title = `이 레벨에서 서식이 달라 뗀 서식 종속 템플릿 T${sp.no} — 줄 ${nf(sp.lines)}개(그 아래 줄 포함) · 누르면 그 템플릿을 펴 보입니다`;
    chip.onclick = () => tplTreeRefresh(sp.id, true);
    row.append(chip, hBtn("합치기", () => olmUnsplit(sp.id), { title: `T${sp.no} 를 지우고 그 줄을 T${t.no} L${L} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn olm-unsplit" }));
  }
  if (open) row.append(olmList(id, L, v, repG));
  return row;
}
function olmSplits(id, L) { const t = olmTpl(id); return ((t && t.splits) || []).filter((x) => +x.level === +L); } // 이 레벨에서 뗀 서식 종속 템플릿들

function olmPick(id, L) { // 이 레벨에서 원문으로 고른 줄 — 문서 표를 눌러 온 줄(OLM.pick) → 커서 줄 → null. {pid, how}
  const a = OLM.pick;
  if (a && a.epoch === state.epoch && String(a.tpl) === String(id) && +a.level === +L && heads.outline && heads.outline.lines[a.para]) return { pid: a.para, how: "누른" };
  const c = state.cur && heads.outline ? heads.outline.lines[state.cur.id] : null;
  return c && String(c.tpl) === String(id) && +c.level === +L ? { pid: state.cur.id, how: "커서" } : null;
}

function olmList(id, L, v, repG) { // 갈래 목록 — 갈래마다 [대표 | 대표로] ×수 · 대표와 다른 값 · 견본 줄 · 줄 목록
  const ul = el("ul", "olm-list");
  const pick = olmPick(id, L);
  for (const g of v.groups) {
    const first = pick && g.paras.includes(pick.pid) ? pick.pid : g.paras[0]; // 고른 줄이 든 갈래면 그 줄을 대표로
    const li = el("li", `olm-g${g.rep ? " rep" : ""}`);
    li.dataset.key = g.key;
    li._paras = g.paras;
    const head = el("div", "olm-gh");
    if (g.rep) head.append(el("span", "hb olm-badge", "대표"));
    else head.append(hBtn("대표로", () => olmSetRep(id, L, first), { title: `이 갈래의 ${first === g.paras[0] ? "첫" : "고른"} 줄(${first})을 이 레벨의 대표로 — 문서는 안 바뀝니다`, cls: "btn sm olm-btn" }));
    head.append(el("span", "olm-n", `×${nf(g.count)}`), headsParaLink(first, olmText(first), 28));
    if (!g.rep && v.rep) head.append(hBtn("이 갈래만 맞추기", () => olmMatch(id, L, g.count, [...g.paras]), { title: "이 갈래 줄들만 대표 모양으로", cls: "btn sm olm-btn" }));
    li.append(head);
    if (!g.rep && v.rep) { // 「다른 템플릿으로」 — 일부러 다르게 준 서식의 갈래를 서식 종속 템플릿 「T1L3a」 로 뗀다(② §8-5): 누르면 그 아래 한 줄(팝업 아님)
      const sk = `${id}|${L}|${g.key}`, form = olmSplitForm(id, L, g, first);
      form.hidden = !olmOpenNow().splitOpen.has(sk);
      const sb = hBtn("다른 템플릿으로", () => { form.hidden = !form.hidden; sb.setAttribute("aria-expanded", String(!form.hidden)); if (form.hidden) OLM.splitOpen.delete(sk); else OLM.splitOpen.add(sk); },
        { title: "서식이 다르면 템플릿도 다릅니다 — 이 갈래의 줄을 이 레벨부터 시작하는 서식 종속 템플릿(「T1L3a」)으로 떼어 그 줄들끼리만 서식을 견주게 합니다(문서는 안 바뀜). 손으로 치다 생긴 흔들림이면 「이 갈래만 맞추기」", cls: "btn sm olm-btn olm-split" });
      sb.setAttribute("aria-expanded", String(!form.hidden));
      head.append(sb);
      li.append(form);
    }
    if (!g.rep && g.diff && g.diff.length) {
      const d = el("div", "olm-diff", olmDiffText(g.diff));
      d.title = olmDiffTitle(g.diff);
      li.append(d);
    }
    if (g.count > 1) {
      const det = el("details", "olm-paras");
      det.append(el("summary", null, `줄 ${nf(g.count)}`));
      const box = el("div", "olm-plist");
      for (const pid of g.paras) box.append(headsParaLink(pid, olmText(pid), 30));
      if (g.more) box.append(el("span", "muted", `외 ${nf(g.more)}줄`));
      det.append(box);
      li.append(det);
    }
    ul.append(li);
  }
  return ul;
}

const OLM_SFX = "abcdefghijklmnopqrstuvwxyz"; // 같은 레벨에서 뗀 차례의 글자(서버 outline_match.SFX 와 같다)
function olmSplitForm(id, L, g, like) { // 갈래 줄 아래 「옮길 템플릿 [새 템플릿 T1L3a ▾] [넣기]」 + 설명 한 줄 — like = 그 갈래의 줄(새 템플릿의 대표가 된다)
  const t = olmTpl(id) || {}, made = olmSplits(id, L), used = new Set(made.map((x) => x.sfx)), next = [...OLM_SFX].find((ch) => !used.has(ch));
  const form = el("div", "olm-merge olm-splitf"), sel = el("select"), note = el("span", "olm-note");
  sel.setAttribute("aria-label", "옮길 템플릿");
  if (next) { const o = el("option", null, `새 템플릿 T${t.no}L${L}${next}`); o.value = ""; sel.append(o); }
  for (const m of made) { const o = el("option", null, `T${m.no} 에 더 넣기`); o.value = m.id; sel.append(o); }
  const sync = () => {
    const m = made.find((x) => x.id === sel.value);
    note.textContent = m ? `이 갈래 ${nf(g.count)}줄(과 그 아래 줄)을 T${m.no} 로 옮깁니다 — 대표·서식은 T${m.no} 것 그대로(옮긴 뒤 그 템플릿에서 「대표에 맞추기」)`
      : `서식 종속 템플릿 T${t.no}L${L}${next} 를 만듭니다 — 이 갈래 ${nf(g.count)}줄(과 그 아래 줄)이 옮겨 가고 이 갈래의 서식이 그 템플릿 L${L} 의 대표 · 줄은 L${L} 부터${L > 1 ? `(L1${L > 2 ? `~L${L - 1}` : ""} 은 T${t.no} 의 레벨)` : ""} · T${t.no} L${L} 의 갈래에서 빠집니다`;
  };
  sel.onchange = sync;
  sync();
  form.append(el("span", "olf-lab", "옮길 템플릿"), sel, hBtn("넣기", () => olmSplit(id, L, like, sel.value || null), { title: "문서는 안 바뀝니다 — 「실행 취소」 · 「합치기」 로 되돌립니다", cls: "btn sm primary", disabled: !sel.options.length }), note);
  return form;
}

function olmRefresh() { // 오버레이·서식 갈래가 바뀐 뒤 — 열려 있는 「템플릿 관계」 의 갈래 줄을 다시(편 목록은 편 채로), 도구 줄 단추도
  olmToolSync();
  if (typeof docStatusPing === "function") docStatusPing(); // 이름 줄의 「서식 맞춘 레벨」 · 진행표도(doc_status.js — spec_작업 ② §20)
  const rows = document.querySelectorAll(".tpl-tree .olm, .tpl-tree .tpl-pic, .tpl-tree .olm-tm");
  if (!rows.length && !(typeof tpaOn === "function" && tpaOn())) return; // 트리가 없어도 서식 정리 에이전트 열(tpl_agent.js)의 대상 칸은 새 갈래로
  if (!olmFresh()) { olmLoad().then((d) => { if (d) olmRedraw(); }); return; }
  olmRedraw();
}
function olmRedraw() {
  for (const old of document.querySelectorAll(".tpl-tree .olm")) { // 「템플릿」 탭과 「템플릿 관계」 열의 트리 모두(같은 줄이 두 곳에 있을 수 있다)
    const fresh = olmRow(old.dataset.tpl, +old.dataset.level);
    if (!fresh) { old.remove(); continue; }
    old.replaceWith(fresh);
  }
  for (const box of document.querySelectorAll(".tpl-tree .tpl-pic")) olmPicFill(box); // 개요 레벨 그림도 새 대표 서식으로
  for (const old of document.querySelectorAll(".tpl-tree .olm-tm")) old.replaceWith(olmTplMatch(old.dataset.tpl)); // 「템플릿 맞추기(n줄)」 의 줄 수도
  if (OLM.sel) olmMark(OLM.sel);
  if (typeof olpRefresh === "function") olpRefresh(); // 「서식 비교」·자리 미리보기 창 — 새 갈래로
  if (typeof tplAgentSync === "function") tplAgentSync(); // 열려 있는 서식 정리 에이전트 열의 대상 칸(tpl_agent.js)
}

function olmMark(at) { // 문서 표에서 온 줄 — 그 레벨 줄과 그 줄이 든 갈래를 표시
  let first = null;
  for (const row of document.querySelectorAll(`.tpl-tree .olm[data-tpl="${CSS.escape(String(at.tpl))}"][data-level="${+at.level}"]`)) {
    row.classList.add("sel");
    const g = [...row.querySelectorAll(".olm-g")].find((x) => (x._paras || []).includes(at.para));
    if (g) g.classList.add("sel");
    if (!first || row.closest("#headsDlgBody")) first = row; // 보일 줄 = 「템플릿 관계」 열의 것(문서 표를 누르면 그 열이 열린다)
  }
  return first;
}

function olmFocus(at) { // tplRelOpen 이 부른다 — 그 레벨의 갈래 목록을 펴고 그 줄이 든 갈래를 표시
  if (!at || at.tpl == null) return;
  OLM.sel = at;
  OLM.pick = { ...at, epoch: state.epoch }; // 표시(sel)는 잠시 · 고른 줄(pick)은 「대표로」 가 쓴다
  olmOpenNow();
  const key = `${at.tpl}|${+at.level}`;
  const v = olmFresh() ? olmSlotData(at.tpl, at.level) : null;
  if (!v || v.groups.length > 1) OLM.open.add(key);
  const go = () => {
    olmRedraw();
    const row = olmMark(at);
    if (row) row.scrollIntoView({ block: "center" });
    setTimeout(() => { if (OLM.sel === at) { OLM.sel = null; for (const e of document.querySelectorAll(".tpl-tree .olm.sel, .tpl-tree .olm-g.sel")) e.classList.remove("sel"); } }, 4000);
  };
  if (olmFresh()) go(); else olmLoad().then(go);
}

async function olmSetRep(id, L, pid) {
  if (state.busy || !state.id) return;
  const epoch = state.epoch;
  try {
    await flushAll();
    const r = await api(`/api/docs/${state.id}/outline/slots/${encodeURIComponent(id)}/${L}/rep`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ para: pid }) });
    if (epoch !== state.epoch) return;
    applyEditState(r);
    if (r.outline && !r.outline.off) heads.outline = r.outline;
    if (OLM.data && r.slot) { (OLM.data[String(id)] = OLM.data[String(id)] || {})[String(L)] = r.slot; OLM.rev = r.rev; OLM.epoch = state.epoch; }
    refreshToolbar(); // 실행 취소 단추(undo 수)
    refreshSaveState();
    tplMarksDraw();
    olmRefresh();
    const t = olmTpl(id);
    toast(`T${t ? t.no : id} L${L} 의 대표를 「${short(olmText(pid), 24)}」 로 정했습니다 — 새 줄과 「대표에 맞추기」 가 이 모양을 따릅니다(「실행 취소」 로 되돌림)`);
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); }
}

async function olmMatch(id, L, n, group = null) { // group = 갈래의 줄 목록(갈래 하나만 맞출 때) — 화면이 가진 목록은 30줄까지라 첫 줄만 보내 서버가 그 줄과 서식이 같은 줄을 모두 찾는다(like)
  const t = olmTpl(id);
  const r = await structOp(`outline/slots/${encodeURIComponent(id)}/${L}/match`, group && group.length ? { like: group[0] } : {});
  if (!r) return;
  if (r.nothing) { toast("맞출 줄이 없습니다 — 모두 대표와 같습니다"); olmLoad(true).then(() => olmRefresh()); return; }
  olmLoad(true).then(() => olmRefresh()); // 문서는 structOp 가 바뀐 블록으로 다시 그렸다(떨어진 줄들이면 문서를 다시 읽음)
  toast(`T${t ? t.no : id} L${L} 줄 ${nf((r.changed || []).length || n)}개를 대표 모양으로 맞췄습니다 — 「실행 취소」 로 되돌립니다`);
}

// ---------------------------------------------------------------- 템플릿 종속(하위로 넣기 · 떼기) — 종속 템플릿 「T1T3」(2026-11-15 사용자 "T1 이 주고 종속이 T3 라면 T1T3 템플릿으로")
// 넣으면 서버가 새 종속 템플릿(id 「A+B」 · 표기 「T{A}T{B}」 · base = at — L1~L at 은 A 의 레벨, L at+1 부터 B 의 레벨)을 만들고 그 자리의 B 줄을 거기로 옮긴다. A 는 안 바뀐다.
const olmKey = (id) => (/^\d+$/.test(String(id)) ? +id : String(id)); // 「템플릿 관계」 의 템플릿 키 — 그래프 템플릿은 정수, 종속 템플릿은 글(「1+3」)

function olmHidden(cid, pid, L) { // 「템플릿 관계」 의 (pid, L) 아래 가지 목록에서 뺄 것 — 그 자리에 넣은 템플릿(그 자리에는 종속 템플릿이 대신 보인다 · 다른 자리의 B 는 그대로)
  const c = olmTpl(`${pid}+${cid}`);
  return !!(c && c.comp && +c.comp.at === +L);
}

function olmRel(rel) { // headsTplView 가 그래프로 만든 관계(tplRel)에 종속 템플릿을 더한다 — (A, at) 아래 가지 · 인스턴스 = 그 첫 레벨 줄들(누르면 문서로)
  const o = heads.outline;
  if (!o || !o.templates) return;
  for (const [tid, t] of Object.entries(o.templates)) {
    if (!t.comp && !t.vari) continue;
    const first = (t.base || 0) + 1;
    const roots = Object.entries(o.lines).filter(([, x]) => String(x.tpl) === tid && +x.level === first).map(([pid]) => pid);
    if (t.vari) { // 서식 종속 템플릿 「T1L3a」(② §8-5) — 제 첫 레벨 줄이 매달린 자리(hang: 보통 (A, k−1) · 첫 레벨에서 뗀 것은 A 가 매달리던 자리·문서 최상위·표 칸)마다 가지로
      rel.tpl.set(tid, { id: tid, no: t.no, chain: t.chain || [], kind: t.base ? "branch" : t.kind, anchor: `T${t.vari.ofNo} L${t.vari.level} 의 다른 서식`, slots: [] });
      const at = new Map();
      for (const [k, n] of Object.entries(t.hang || {})) {
        at.set(k, n);
        if (!k.includes("|")) continue;
        const u = rel.under.get(k) || new Map();
        u.set(tid, n);
        rel.under.set(k, u);
      }
      rel.at.set(tid, at);
      rel.inst.set(tid, roots.map((pid, k) => ({ no: k + 1, root: pid, text: oneLine(olmText(pid)).slice(0, 40) })));
      continue;
    }
    const where = `${t.comp.parent}|${t.comp.at}`;
    rel.tpl.set(tid, { id: tid, no: t.no, chain: t.chain || [], kind: t.kind, anchor: `T${t.comp.parentNo} L${t.comp.at} 아래 T${t.comp.childNo}`, slots: [] });
    const u = rel.under.get(where) || new Map();
    u.set(tid, roots.length);
    rel.under.set(where, u);
    rel.at.set(tid, new Map([[where, roots.length]]));
    rel.inst.set(tid, roots.map((pid, k) => ({ no: k + 1, root: pid, text: oneLine(olmText(pid)).slice(0, 40) })));
  }
}

function olmPlaces(id) { // 넣을 수 있는 자리 — 이 템플릿 첫 레벨 줄이 매달린 (A, k)(제 자신 · 이미 넣은 A 빼고) → [{parent, at, n, label, to}]
  const t = olmTpl(id);
  if (!t || !t.hang) return [];
  const done = new Set((t.made || []).map((m) => String(m.parent)));
  const out = [];
  for (const [k, n] of Object.entries(t.hang)) {
    if (!k.includes("|")) continue;
    const [a, at] = k.split("|");
    if (a === String(id) || done.has(a)) continue;
    const A = olmTpl(a);
    if (!A) continue;
    const span = Math.max(1, (t.max || 0) - (t.base || 0));
    const letter = (A.slots && A.slots[at] ? A.slots[at].letter : (A.chain || [])[+at - 1]) || "?";
    out.push({ parent: a, at: +at, n, label: `T${A.no} L${at} 「${short(letter, 14)}」 아래 ${nf(n)}곳`, to: `T${A.no}T${t.no} L${+at + 1}${span > 1 ? `~L${+at + span}` : ""}` });
  }
  return out.sort((x, y) => y.n - x.n);
}

function olmNoPlace(t) { // 「하위로」 를 눌렀는데 넣을 자리가 없을 때의 까닭 글(단추를 감추지 않는다 — 2026-11-15 사용자 「종속 템플릿 … 보이질 않아」)
  const h = t.hang || {}, parts = [h.root ? `본문 최상위 ${nf(h.root)}곳` : "", h.cell ? `표 칸 ${nf(h.cell)}곳(그 칸 안에 앞선 다른 템플릿 줄이 없음)` : ""].filter(Boolean);
  const own = Object.keys(h).filter((k) => k.split("|")[0] === String(t.id ?? "")).length;
  return `넣을 자리가 없습니다 — 「하위로」 는 T${t.no} 의 첫 레벨 줄이 다른 템플릿 줄 바로 아래에 매달린 곳을, 그 템플릿 레벨 아래의 종속 템플릿(「T부모T${t.no}」)으로 묶어 그 줄들만 따로 맞추게 합니다. `
    + `이 문서에서 T${t.no} 의 첫 레벨 줄은 ${parts.join(" · ") || "매달린 곳이 없습니다"}${own ? " · 제 템플릿 줄 아래" : ""} — 다른 템플릿 줄 아래에 매달린 곳이 없습니다.`
    + ((t.made || []).length ? " 매달린 자리는 이미 종속 템플릿으로 넣었습니다(위 「→ T… · 떼기」)." : "");
}

function olmTplTools(li, row, id) { // 템플릿 줄 머리 — 종속 템플릿 표지 · 이 템플릿으로 만든 종속 템플릿 「T1T3 · 떼기」 · 「템플릿 맞추기」 · 「하위로」(넣을 자리가 없어도 보인다 — 누르면 까닭)
  const t = olmTpl(id);
  if (!t) return;
  if (t.comp) {
    const chip = el("span", "olm-chip", `종속 — T${t.comp.parentNo} L${t.comp.at} 아래 T${t.comp.childNo}`);
    chip.title = `T${t.comp.childNo} 를 T${t.comp.parentNo} L${t.comp.at} 아래로 넣어 만든 종속 템플릿 — L1~L${t.comp.at} 은 T${t.comp.parentNo} 의 레벨, L${t.comp.at + 1} 부터 T${t.comp.childNo} 의 레벨. 서식 갈래·대표·맞추기는 이 종속 템플릿의 줄끼리만 견줍니다`;
    row.append(chip, hBtn("떼기", () => olmUnmerge(t.comp.child, t.comp.parent), { title: `종속 템플릿을 지우고 그 줄을 T${t.comp.childNo} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn" }));
  }
  for (const m of t.made || []) {
    const chip = el("span", "olm-chip", `→ T${m.no}(${nf(m.moved)}줄)`);
    chip.title = `이 템플릿의 줄 ${nf(m.moved)}개를 T${m.parentNo} L${m.at} 아래로 넣어 종속 템플릿 T${m.no} 를 만들었습니다`;
    row.append(chip, hBtn("떼기", () => olmUnmerge(id, m.parent), { title: `T${m.no} 를 지우고 그 줄을 T${t.no} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn" }));
  }
  if (t.vari) { // 서식 종속 템플릿 — 「서식 종속 — T1 L3 의 다른 서식 · 합치기」(② §8-5)
    const v = t.vari, chip = el("span", "olm-chip", `서식 종속 — T${v.ofNo} L${v.level} 의 다른 서식`);
    chip.title = `T${v.ofNo} L${v.level} 에서 서식이 달라 뗀 템플릿${v.level > 1 ? ` — L1${v.level > 2 ? `~L${v.level - 1}` : ""} 은 T${v.ofNo} 의 레벨, 이 템플릿의 줄은 L${v.level} 부터` : ""}. 서식 갈래·대표·맞추기는 이 템플릿의 줄끼리만 견줍니다`;
    row.append(chip, hBtn("합치기", () => olmUnsplit(id), { title: `이 템플릿을 지우고 그 줄을 T${v.ofNo} 의 같은 레벨로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn olm-unsplit" }));
  }
  row.append(olmTplMatch(id)); // 「템플릿 맞추기(n줄)」 — 이 템플릿(종속 템플릿이면 그 줄만)의 모든 레벨을 한 번에
  if (t.all) { row.append(el("span", "olm-chip into", "줄을 다 넣음")); return; }
  if (!t.lines || t.vari) return; // 서식 종속 템플릿은 이미 제 템플릿의 레벨 아래 — 「하위로」 없음
  const places = olmPlaces(id);
  const open = olmOpenNow().mergeOpen.has(String(id));
  const form = el("div", "olm-merge");
  form.hidden = !open;
  const btn = hBtn("하위로", () => { form.hidden = !form.hidden; btn.setAttribute("aria-expanded", String(!form.hidden)); if (form.hidden) OLM.mergeOpen.delete(String(id)); else OLM.mergeOpen.add(String(id)); },
    { title: `T${t.no} 를 다른 템플릿 레벨 아래의 하위 개요 레벨로 넣어 종속 템플릿(「T부모T${t.no}」)을 만듭니다 — 그 자리에 매달린 줄만 옮기고(문서는 안 바뀜), 그 줄들끼리만 서식을 견주고 맞춥니다`
      + (places.length ? "" : "\n이 문서에는 넣을 자리가 없습니다 — 누르면 까닭"), cls: `btn sm olm-btn olm-sub${places.length ? "" : " none"}` });
  btn.setAttribute("aria-expanded", String(open));
  row.append(btn);
  if (!places.length) { // 넣을 자리가 없어도 단추는 보인다 — 펼치면 까닭 한 줄
    form.append(el("span", "olm-note", olmNoPlace({ ...t, id })));
    row.after(form);
    return;
  }
  const sel = el("select");
  sel.setAttribute("aria-label", "넣을 자리");
  for (const [i, p] of places.entries()) { const o = el("option", null, `${p.label} → ${p.to}`); o.value = String(i); sel.append(o); }
  const note = el("span", "olm-note");
  const go = hBtn("넣기", () => { const p = places[+sel.value]; if (p) olmMerge(id, p.parent, p.at); }, { title: "실행 취소로 되돌립니다", cls: "btn sm primary" });
  const sync = () => {
    const p = places[+sel.value];
    const A = olmTpl(p.parent) || {};
    note.textContent = `종속 템플릿 ${p.to.split(" ")[0]} 을 만듭니다 — 「${[...(A.chain || []).slice(0, p.at), ...(t.chain || []).slice(t.base || 0)].join(" › ")}」 · 그 자리의 T${t.no} 줄만(다른 자리의 T${t.no} · T${A.no || p.parent} 는 그대로) · 넣은 뒤 그 줄들만 따로 「종속 템플릿 맞추기」`;
  };
  sel.onchange = sync;
  sync();
  form.append(el("span", "olf-lab", "넣을 자리"), sel, go, note);
  row.after(form);
}

// ---------------------------------------------------------------- 템플릿 단위 맞추기(POST …/outline/templates/{tpl}/match — 여러 레벨을 트랜잭션 하나로: 실행 취소 1)
function olmTplOthers(id) { // 이 템플릿에서 대표와 서식이 다른 줄 수 · 그런 레벨 수(갈래 자료가 지금 것일 때만) → {n, levels} | null
  if (!olmFresh()) return null;
  const lv = Object.values(OLM.data[String(id)] || {}).filter((v) => v.rep && v.others);
  return { n: lv.reduce((a, v) => a + v.others, 0), levels: lv.length };
}
function olmTplMatch(id) { // 템플릿 줄의 「템플릿 맞추기(n줄)」 자리 — 맞출 줄이 없으면 빈 자리(갈래를 읽은 뒤 olmRedraw 가 다시 채운다)
  const box = el("span", "olm-tm");
  box.dataset.tpl = id;
  const t = olmTpl(id), o = t ? olmTplOthers(id) : null;
  if (!o) { olmNeed(); return box; }
  if (!o.n) return box;
  box.append(hBtn(`${t.comp || t.vari ? "종속 템플릿" : "템플릿"} 맞추기(${nf(o.n)}줄)`, () => olmMatchTpl(id),
    { title: `T${t.no} 의 레벨 ${o.levels}개에서 대표와 서식이 다른 줄 ${nf(o.n)}개를 레벨마다 그 대표 모양으로 — 한 번에(「실행 취소」 한 번으로 되돌림)`
      + (t.comp ? `\n종속 템플릿의 줄만 맞춥니다 — 다른 자리의 T${t.comp.childNo} · T${t.comp.parentNo} 줄은 그대로`
        : t.vari ? `\n서식 종속 템플릿의 줄만 맞춥니다 — T${t.vari.ofNo} 의 줄은 그대로` : "\n레벨마다 따로 하려면 펼쳐서 「대표에 맞추기」"), cls: "btn sm olm-btn olm-tm-btn" }));
  return box;
}
async function olmApplyTpl(id, body) { // 템플릿 단위 맞추기 한 번 → 응답 | null(실패 — 알림은 여기서). 「템플릿 맞추기」 단추와 서식 정리 에이전트의 적용(tpl_agent.js)이 같이 쓴다
  structOp.lastError = null;
  const r = await structOp(`outline/templates/${encodeURIComponent(id)}/match`, body);
  if (!r) {
    const e = structOp.lastError;
    if (e && e.status === 404 && /not found/i.test(e.message || "")) toast("서버가 옛 판이라 템플릿 단위 맞추기를 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요", true);
    return null;
  }
  outlineLoad(true); // 대표가 바뀌었을 수 있다 — 오버레이 요약(레벨의 대표·자리)을 다시
  olmLoad(true).then(() => olmRefresh());
  return r;
}
async function olmMatchTpl(id) {
  const t = olmTpl(id);
  const r = await olmApplyTpl(id, {});
  if (!r) return;
  if (r.nothing) { toast("맞출 줄이 없습니다 — 레벨마다 모두 대표와 같습니다"); return; }
  toast(`T${t ? t.no : id} 줄 ${nf((r.changed || []).length)}개를 레벨마다 대표 모양으로 맞췄습니다(레벨 ${(r.levels || []).length}개) — 「실행 취소」 한 번으로 되돌립니다`);
}

// ---------------------------------------------------------------- 개요 레벨 그림 — 서식 복사의 내용 서식 견본(style_pic.js stylePic 의 "content")과 같은 그림을 템플릿마다
// (2026-11-15 사용자 「문서 서식에 있는것 처럼 개요 레벨을 보여줘」). 값은 그 레벨 **대표 갈래**의 것(GET …/outline/formats 의 raw — 글꼴·크기·굵기·기울임·밑줄·색 = 본문 바탕 글자) +
// 레터 위치(오버레이 슬롯의 at.letterMm — 앞 공백 포함, 없으면 앞 여백). 견본 글은 서식 복사와 같은 「견본 글입니다」. 갈래를 아직 안 읽었으면 자리만 잡고 읽은 뒤 채운다.
function olmNeed() { // 갈래 자료가 없으면 한 번 읽고 한 번 다시 그린다(줄·그림마다 부르지 않게)
  if (olmFresh() || OLM.pending || !heads.outline) return;
  OLM.pending = true;
  olmLoad().then((d) => { OLM.pending = false; if (d) olmRedraw(); });
}
function olmPicLevels(t) { return Object.keys(t.slots || {}).map(Number).filter((L) => L > (t.base || 0) && t.slots[String(L)].lines && !t.slots[String(L)].table).sort((a, b) => a - b); } // 표 제목 레벨(② §8-7)은 글 서식 그림에 없다
function olmPicView(id) { // → stylePic 의 보기 {items[{level, letter, marker, sample, format}]} | null(오버레이·갈래 자료 없음)
  const t = olmTpl(id);
  if (!t || !olmFresh()) return null;
  const items = [];
  for (const L of olmPicLevels(t)) {
    const os = t.slots[String(L)], v = olmSlotData(id, L), g = v ? v.groups.find((x) => x.rep) || v.groups[0] : null, raw = g && g.raw ? g.raw : {};
    const letter = oneLine(os.letter || (t.chain || [])[L - 1] || "");
    items.push({ level: L, letter, marker: { mode: "literal", literal: letter }, sample: "견본 글입니다",
      format: { font: raw.font, sizePt: raw.sizePt, bold: !!raw.bold, italic: !!raw.italic, underline: !!raw.underline, color: raw.color, spacingPct: raw.spacingPct,
        indentLeftMm: os.at && os.at.letterMm != null ? os.at.letterMm : raw.line1Mm || 0, firstLineMm: 0 } });
  }
  return items.length ? { items } : null;
}
function olmPic(id) { // 템플릿 줄 아래 그림 상자 — 이 템플릿에 줄이 없으면 null
  const t = olmTpl(id);
  if (!t || typeof stylePic !== "function" || !olmPicLevels(t).length) return null;
  const box = el("div", "tpl-pic");
  box.dataset.tpl = id;
  olmPicFill(box);
  return box;
}
function olmPicFill(box) { // 그림을 (다시) 채운다 — 갈래를 아직 안 읽었으면 높이만 잡아 둔다(목록이 밀리지 않게)
  const id = box.dataset.tpl, t = olmTpl(id);
  if (!t || typeof stylePic !== "function") { box.replaceChildren(); return; }
  const n = olmPicLevels(t).length, view = olmPicView(id);
  if (!view) {
    olmNeed();
    if (!box.firstChild) { const hold = el("div", "tpl-pic-hold"); hold.style.height = `${14 + n * 26}px`; box.replaceChildren(hold); }
    return;
  }
  const pic = stylePic(view, { kind: "content", width: 300, big: true }); // big = 레벨을 다 보인다(높이는 내용만큼 — 아래를 흐리게 자르지 않는다)
  pic.title = `개요 레벨 그림 — 레벨마다 그 레벨 대표 줄의 레터 · 글꼴·크기·굵기 · 들여쓰기(견본 글)\n${view.items.map((it) => `L${it.level} 「${it.letter}」 ${it.format.font || ""} ${it.format.sizePt || ""}pt${it.format.bold ? " 굵게" : ""} · 레터 ${Math.round((it.format.indentLeftMm || 0) * 10) / 10}mm`).join("\n")}`;
  box.replaceChildren(pic);
}

async function olmMergeCall(path, body, done) {
  if (state.busy || !state.id) return;
  const epoch = state.epoch;
  try {
    await flushAll();
    const r = await api(`/api/docs/${state.id}/outline/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return;
    applyEditState(r);
    if (r.outline && !r.outline.off) heads.outline = r.outline;
    refreshToolbar(); // 실행 취소 단추(undo 수)
    refreshSaveState();
    tplMarksDraw();
    OLM.data = null;
    tplTreeRefresh(done.focus(r), true); // 그려 둔 트리(「템플릿」 탭 · 「템플릿 관계」 열)를 다시 그리고 그 템플릿을 펴 보인다 — 열을 새로 열지는 않는다
    olmLoad(true).then(() => olmRefresh());
    toast(done.msg(r));
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); }
}
function olmMerge(child, parent, at) {
  const B = olmTpl(child), A = olmTpl(parent);
  OLM.mergeOpen.delete(String(child));
  return olmMergeCall("merge", { child: String(child), parent: String(parent), at },
    { focus: (r) => olmKey((r.merged || {}).id || parent),
      msg: (r) => `T${B ? B.no : child} 를 T${A ? A.no : parent} L${at} 아래로 넣어 종속 템플릿 T${(r.merged || {}).no} 를 만들었습니다 — 줄 ${nf((r.merged || {}).moved)}개가 L${at + 1}~(「실행 취소」 · 「떼기」 로 되돌림)` });
}
function olmUnmerge(child, parent) {
  const B = olmTpl(child), C = olmTpl(`${parent}+${child}`);
  return olmMergeCall("unmerge", { child: String(child), parent: String(parent) },
    { focus: () => olmKey(child), msg: (r) => `종속 템플릿 T${C ? C.no : `${parent}+${child}`} 를 뗐습니다 — 줄 ${nf(r.back)}개가 T${B ? B.no : child} 로 돌아감` });
}
// 서식 종속 템플릿(② §8-5) — 갈래를 「T1L3a」 로 떼기 · 합치기. like = 그 갈래의 줄(서버가 그 줄과 서식이 같은 줄을 모두 찾는다 · 새 템플릿의 대표), into = 더 넣을 템플릿 id
function olmSplit(id, L, like, into = null) {
  const t = olmTpl(id);
  for (const k of [...OLM.splitOpen]) if (k.startsWith(`${id}|${L}|`)) OLM.splitOpen.delete(k);
  return olmMergeCall(`slots/${encodeURIComponent(id)}/${L}/split`, { likes: [like], rep: like, ...(into ? { into: String(into) } : {}) },
    { focus: (r) => olmKey((r.split || {}).id || id),
      msg: (r) => { const s = r.split || {}; return s.added ? `T${t ? t.no : id} L${L} 의 갈래 ${nf(s.lines)}줄을 T${s.no} 로 옮겼습니다 — 그 템플릿에서 「대표에 맞추기」 로 맞출 수 있습니다(「실행 취소」 로 되돌림)`
        : `서식 종속 템플릿 T${s.no} 를 만들었습니다 — T${t ? t.no : id} L${L} 의 줄 ${nf(s.moved)}개가 옮겨 갔습니다 · 줄은 L${L} 부터(「실행 취소」 · 「합치기」 로 되돌림)`; } });
}
function olmUnsplit(cid) {
  const C = olmTpl(cid), v = C && C.vari;
  return olmMergeCall("unsplit", { id: String(cid) },
    { focus: () => olmKey(v ? v.of : cid), msg: (r) => `T${C ? C.no : cid} 를 합쳤습니다 — 줄 ${nf(r.back)}개가 T${v ? v.ofNo : ""} 로 돌아감` });
}

// ---------------------------------------------------------------- 도구 줄 「서식」 묶음의 「템플릿 관계」(#tbTplRel)
const olmColOn = () => { const c = $("headsDlg"); return !!c && !c.hidden && c.dataset.kind === "templates"; };
function olmToolSync() {
  const b = $("tbTplRel");
  if (!b) return;
  const ok = !!state.id && state.format === "hwpx" && !!heads.outline;
  b.disabled = !ok;
  b.setAttribute("aria-pressed", String(ok && olmColOn()));
  b.title = ok ? "템플릿 관계 — 문서의 개요 템플릿 · 레벨마다 서식 갈래와 대표 · 대표에 맞추기 · 하위로 넣기(문서 옆 열 — 다시 누르면 닫힘)"
    : !state.id ? "템플릿 관계 — 문서를 열면 씁니다" : state.format !== "hwpx" ? "템플릿 관계 — HWPX 문서에서만 됩니다(헤딩 그래프가 HWPX 만)"
      : "템플릿 관계 — 헤딩 추출 2단계(헤딩 그래프) 결과가 있어야 합니다";
}
(() => {
  const b = $("tbTplRel"), col = $("headsDlg");
  if (!b || !col) return;
  b.onclick = () => { if (olmColOn() && !colFolded("heads")) headsColClose(); else tplRelOpen(); };
  if (typeof MutationObserver === "function") new MutationObserver(olmToolSync).observe(col, { attributes: true, attributeFilter: ["hidden", "data-kind"] });
  olmToolSync();
})();
