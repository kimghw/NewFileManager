// 개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 「템플릿 관계」 열(app.js headsTplView)의 레벨 줄·템플릿 줄에 붙는다.
// 자료: GET /api/docs/{id}/outline/formats(레벨마다 서식 갈래 — 문서 차례(rev)마다 다시 읽음) · heads.outline(GET …/outline — 템플릿마다 hang·merged·into·partly, 레벨마다 rep·from).
// 동작: PUT …/outline/slots/{tpl}/{L}/rep(대표 정하기 — 문서는 안 바뀜 · 실행 취소 1) · POST …/slots/{tpl}/{L}/match(대표에 맞추기 — structOp) · POST …/outline/merge · unmerge(하위로 넣기 · 떼기).
// 도구 줄 「서식」 묶음의 #tbTplRel(템플릿 관계 열 열기·닫기)도 여기서 잇는다. app.js 다음에 읽힌다(el·hBtn·api·toast·heads·state·structOp·applyEditState·tplMarksDraw·
// headsTplView·tplRelOpen·headsParaLink·headsColClose·colFolded·nf·short·oneLine·paraEl …). 훅: headsTplView 의 levels() 가 olmRow(id, L)·olmHidden(…) 을, make() 가 olmTplTools(…) 를,
// outlineLoad 가 olmRefresh() 를, tplRelOpen 이 olmFocus(at) 를 부른다.
const OLM = { data: null, rev: null, epoch: null, busy: null, pending: false, open: new Set(), mergeOpen: new Set(), openEpoch: null, sel: null, pick: null }; // open = 갈래 목록을 편 레벨 「tpl|L」 · mergeOpen = 넣기 줄을 편 템플릿 · sel = 표시할 줄

function olmOpenNow() { // 편 목록 기억(OLM.open·mergeOpen)은 문서마다 — 다른 문서를 열었으면 비운다
  if (OLM.openEpoch !== state.epoch) { OLM.open.clear(); OLM.mergeOpen.clear(); OLM.openEpoch = state.epoch; }
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

const olmDiffText = (diff, n = 4) => { // [[키, 이름, 대표, 이 갈래]…] → 「앞 공백 1칸 → 2칸 · 2번째 줄 10.4mm → 10.9mm」(대표 → 이 갈래)
  const parts = (diff || []).map((d) => `${d[1]} ${d[2]} → ${d[3]}`);
  return parts.length > n ? `${parts.slice(0, n).join(" · ")} 외 ${parts.length - n}` : parts.join(" · ");
};
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
    if (!olmFresh() && !OLM.pending) { // 줄마다 부르지 않게 — 한 번 읽고 한 번 다시 그린다
      OLM.pending = true;
      olmLoad().then((d) => { OLM.pending = false; if (d) olmRedraw(); });
    }
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
  if (open) row.append(olmList(id, L, v, repG));
  return row;
}

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
    if (!g.rep && g.diff && g.diff.length) {
      const d = el("div", "olm-diff", olmDiffText(g.diff));
      d.title = "대표 → 이 갈래\n" + g.diff.map((x) => `${x[1]}: ${x[2]} → ${x[3]}`).join("\n");
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

function olmRefresh() { // 오버레이·서식 갈래가 바뀐 뒤 — 열려 있는 「템플릿 관계」 의 갈래 줄을 다시(편 목록은 편 채로), 도구 줄 단추도
  olmToolSync();
  const rows = document.querySelectorAll("#headsDlgBody .olm");
  if (!rows.length) return;
  if (!olmFresh()) { olmLoad().then((d) => { if (d) olmRedraw(); }); return; }
  olmRedraw();
}
function olmRedraw() {
  for (const old of document.querySelectorAll("#headsDlgBody .olm")) {
    const fresh = olmRow(old.dataset.tpl, +old.dataset.level);
    if (!fresh) { old.remove(); continue; }
    old.replaceWith(fresh);
  }
  if (OLM.sel) olmMark(OLM.sel);
  if (typeof olpRefresh === "function") olpRefresh(); // 「서식 비교」·자리 미리보기 창 — 새 갈래로
}

function olmMark(at) { // 문서 표에서 온 줄 — 그 레벨 줄과 그 줄이 든 갈래를 표시
  const row = document.querySelector(`#headsDlgBody .olm[data-tpl="${CSS.escape(String(at.tpl))}"][data-level="${+at.level}"]`);
  if (!row) return null;
  row.classList.add("sel");
  const g = [...row.querySelectorAll(".olm-g")].find((x) => (x._paras || []).includes(at.para));
  if (g) g.classList.add("sel");
  return row;
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
    setTimeout(() => { if (OLM.sel === at) { OLM.sel = null; for (const e of document.querySelectorAll("#headsDlgBody .olm.sel, #headsDlgBody .olm-g.sel")) e.classList.remove("sel"); } }, 4000);
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
    if (!t.comp) continue;
    const first = (t.base || 0) + 1;
    const roots = Object.entries(o.lines).filter(([, x]) => String(x.tpl) === tid && +x.level === first).map(([pid]) => pid);
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

function olmTplTools(li, row, id) { // 템플릿 줄 머리 — 종속 템플릿 표지 · 이 템플릿으로 만든 종속 템플릿 「T1T3 · 떼기」 · 「하위로」(넣을 자리가 있을 때)
  const t = olmTpl(id);
  if (!t) return;
  if (t.comp) {
    const chip = el("span", "olm-chip", `종속 — T${t.comp.parentNo} L${t.comp.at} 아래 T${t.comp.childNo}`);
    chip.title = `T${t.comp.childNo} 를 T${t.comp.parentNo} L${t.comp.at} 아래로 넣어 만든 종속 템플릿 — L1~L${t.comp.at} 은 T${t.comp.parentNo} 의 레벨, L${t.comp.at + 1} 부터 T${t.comp.childNo} 의 레벨`;
    row.append(chip, hBtn("떼기", () => olmUnmerge(t.comp.child, t.comp.parent), { title: `종속 템플릿을 지우고 그 줄을 T${t.comp.childNo} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn" }));
  }
  for (const m of t.made || []) {
    const chip = el("span", "olm-chip", `→ T${m.no}(${nf(m.moved)}줄)`);
    chip.title = `이 템플릿의 줄 ${nf(m.moved)}개를 T${m.parentNo} L${m.at} 아래로 넣어 종속 템플릿 T${m.no} 를 만들었습니다`;
    row.append(chip, hBtn("떼기", () => olmUnmerge(id, m.parent), { title: `T${m.no} 를 지우고 그 줄을 T${t.no} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn" }));
  }
  if (t.all) { row.append(el("span", "olm-chip into", "줄을 다 넣음")); return; }
  const places = olmPlaces(id);
  if (!places.length) return;
  const open = olmOpenNow().mergeOpen.has(String(id));
  const form = el("div", "olm-merge");
  form.hidden = !open;
  const btn = hBtn("하위로", () => { form.hidden = !form.hidden; btn.setAttribute("aria-expanded", String(!form.hidden)); if (form.hidden) OLM.mergeOpen.delete(String(id)); else OLM.mergeOpen.add(String(id)); },
    { title: `T${t.no} 를 다른 템플릿 레벨 아래의 하위 개요 레벨로 넣어 종속 템플릿을 만듭니다(그 자리에 매달린 줄만 — 문서는 안 바뀜)`, cls: "btn sm olm-btn" });
  btn.setAttribute("aria-expanded", String(open));
  row.append(btn);
  const sel = el("select");
  sel.setAttribute("aria-label", "넣을 자리");
  for (const [i, p] of places.entries()) { const o = el("option", null, `${p.label} → ${p.to}`); o.value = String(i); sel.append(o); }
  const note = el("span", "olm-note");
  const go = hBtn("넣기", () => { const p = places[+sel.value]; if (p) olmMerge(id, p.parent, p.at); }, { title: "실행 취소로 되돌립니다", cls: "btn sm primary" });
  const sync = () => {
    const p = places[+sel.value];
    const A = olmTpl(p.parent) || {};
    note.textContent = `종속 템플릿 ${p.to.split(" ")[0]} 을 만듭니다 — 「${[...(A.chain || []).slice(0, p.at), ...(t.chain || []).slice(t.base || 0)].join(" › ")}」 · 그 자리의 T${t.no} 줄만(다른 자리의 T${t.no} · T${A.no || p.parent} 는 그대로)`;
  };
  sel.onchange = sync;
  sync();
  form.append(el("span", "olf-lab", "넣을 자리"), sel, go, note);
  row.after(form);
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
    heads.keepFold = true;
    try { headsTplView(done.focus(r)); } finally { heads.keepFold = false; }
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
