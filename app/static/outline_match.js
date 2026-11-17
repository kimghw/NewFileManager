// 개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 「템플릿 관계」 열(app.js headsTplView)의 레벨 줄·템플릿 줄에 붙는다.
// 자료: GET /api/docs/{id}/outline/formats(레벨마다 서식 갈래 — 문서 차례(rev)마다 다시 읽음) · heads.outline(GET …/outline — 템플릿마다 hang·merged·into·partly, 레벨마다 rep·from).
// 동작: PUT …/outline/slots/{tpl}/{L}/rep(대표 정하기 — 문서는 안 바뀜 · 실행 취소 1) · POST …/slots/{tpl}/{L}/match(대표에 맞추기 — structOp) · POST …/outline/merge · unmerge(하위로 넣기 · 떼기) ·
//   POST …/slots/{tpl}/{L}/split · …/outline/unsplit(갈래를 서식 종속 템플릿 「T1L3a」 로 떼기 · 합치기 — ② §8-5: 갈래 줄의 「다른 템플릿으로」 · 레벨 줄의 「→ T1L3a(n줄) · 합치기」).
// 도구 줄 「서식」 묶음의 #tbTplRel(템플릿 관계 열 열기·닫기)도 여기서 잇는다. app.js 다음에 읽힌다(el·hBtn·api·toast·heads·state·structOp·applyEditState·tplMarksDraw·
// headsTplView·tplRelOpen·headsParaLink·headsColClose·colFolded·nf·short·oneLine·paraEl …). 훅: headsTplView 의 levels() 가 olmRow(id, L)·olmHidden(…) 을, make() 가 olmTplTools(…) 를,
// outlineLoad 가 olmRefresh() 를, tplRelOpen 이 olmFocus(at) 를 부른다. 뒤에 읽히는 fmt_focus.js 와는 서로 부른다(고른 갈래 ↔ 본문 표시 — 있을 때만): 그쪽이 olmFull·olmFullLoad·olmNos·olmTryOf·olmLookFrom 을,
// 여기서 tplPickShow·tplPickOwns·tplFocusIs·tplFocusOn·fmtFocusOff·fmtFocusRel 을.
const OLM = { data: null, rev: null, epoch: null, busy: null, pending: false, open: new Set(), mergeOpen: new Set(), splitOpen: new Set(), openEpoch: null, sel: null, pick: null, try: null, drag: null, chk: new Map(), // open = 갈래 목록을 편 레벨 「tpl|L」 · mergeOpen = 넣기 줄을 편 템플릿 · splitOpen = 「다른 템플릿으로」 줄을 편 갈래 「tpl|L|줄」 · sel = 표시할 줄
  chkAt: new Map(), chkGen: 0, going: null, full: new Map(), look: null, err: null };
// try = 대표 미리보기 {epoch, tpl, level, pid}(끌어 놓은 갈래 — 문서·대표는 안 바뀜) · drag = 끄는 중인 갈래 · chk = 고른 갈래 「tpl|L」 → Set(갈래 key)(「고른 서식 맞추기」)
// chkAt = 그 고르기를 한 때의 갈래 자료 「tpl|L」 → {rev(문서 차례), sig(그 레벨의 갈래 구성 지문)} · chkGen = 고르기가 바뀐 횟수 · going = 「고른 서식 맞추기」 요청이 도는 레벨 「tpl|L」(그동안 고르기를 못 바꾼다) ·
// full = 줄 전부의 갈래 대응 「tpl|L」 → {st, rev, of, by}(olmFull) · look = 살펴보는 갈래 {epoch, tpl, level, key}(고르기와 따로) · err = 갈래 읽기가 실패했나(olmLoad — 「갈래 없음」 과 가른다). 아래 「고른 갈래 ↔ 본문 표시」

function olmOpenNow() { // 편 목록 기억(OLM.open·mergeOpen·splitOpen)·미리보기·고른 갈래·살펴보는 갈래·줄 전부의 갈래 대응은 문서마다 — 다른 문서를 열었으면 비운다
  if (OLM.openEpoch !== state.epoch) {
    OLM.open.clear(); OLM.mergeOpen.clear(); OLM.splitOpen.clear(); OLM.chk.clear(); OLM.chkAt.clear(); OLM.full.clear();
    OLM.try = null; OLM.look = null; OLM.going = null; OLM.chkGen += 1; OLM.openEpoch = state.epoch;
  }
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
  const plans = api(`/api/docs/${id}/outline/agent/plans`).catch(() => null); // 받아 둔 서식 정리 계획(★) — 「템플릿 맞추기」 가 그 계획대로(olmTplPlan). 옛 서버면 없음
  OLM.busy = Promise.all([api(`/api/docs/${id}/outline/formats`), plans]).then(([r, p]) => {
    if (epoch !== state.epoch) return null;
    OLM.err = null;
    OLM.data = r && !r.off ? r.slots || {} : null;
    OLM.rev = r ? r.rev : null;
    if (r && r.keys) OLM.keys = r.keys; // 비교 값 차례·이름 [[키, 이름]…] — 「서식 비교」 창(outline_preview.js)의 열
    OLM.plans = (p && p.plans) || {};
    OLM.epoch = epoch;
    try { olmPicksCheck(); } catch (e) { console.error(e); } // 고른 갈래(☐) — 갈래 구성이 고른 때와 달라진 레벨은 비우고 알린다(아래 「고른 갈래 ↔ 본문 표시」)
    return OLM.data;
  }).catch((e) => { if (epoch === state.epoch) OLM.err = e || true; return null; }).finally(() => { OLM.busy = null; }); // 실패도 null — 「갈래 없음」 과는 OLM.err 로 가른다(fmt_focus.js 가 「대표 없음」 으로 읽지 않게)
  return OLM.busy;
}

// ★ 계획대로(spec_hwpx_웹편집 ② §8-4 「계획대로 맞추기」, 2026-11-16 사용자 답 「★ 계획이 있으면 따름」 — 전에는 「템플릿 맞추기」 가 계획이 사람에게 남긴 줄까지 다 맞췄다):
// 그 템플릿에 지금 문서 차례에서 받은 계획(state planned)이 있으면 템플릿 줄의 단추는 「계획대로 맞추기(n줄)」 — 에이전트가 고른 그대로(맞추기 · 떼기만, 남긴 줄은 빼고)
// tpl_agent.js tpaTodoOf 의 적용 몸을 같은 끝점(olmApplyTpl, by "agent")으로. 계획이 없거나 옛것·반영한 것이면 전처럼 「템플릿 맞추기」(대표와 다른 줄 모두).
function olmTplPlan(id) { // → 지금 쓸 계획 기록 | null
  const rec = olmFresh() && OLM.plans ? OLM.plans[String(id)] : null;
  return rec && rec.state === "planned" && rec.plan && typeof tpaTodoOf === "function" ? rec : null; // planned = 그 템플릿 줄의 지문이 계획을 받은 때와 같다(서버 — 문서 차례가 달라도)
}
function olmPlanGot(tpl, rec) { // ★ 열에서 새 계획을 받음(tpl_agent.js tpaRun) — 다시 읽지 않고 템플릿 줄 단추만 맞춘다
  if (!OLM.plans) OLM.plans = {};
  OLM.plans[String(tpl)] = { ...rec, state: "planned", applied: null };
  for (const old of document.querySelectorAll(`.tpl-tree .olm-tm[data-tpl="${CSS.escape(String(tpl))}"]`)) old.replaceWith(olmTplMatch(String(tpl)));
}

// 대표와 다른 값 [[키, 이름, 대표, 이 갈래]…] → 「앞 공백: 지금 2칸 → 대표 1칸 · 2번째 줄: 지금 10.9mm → 대표 10.4mm」 — 값마다 이름표(지금 = 이 갈래 줄의 값 · 대표 = 대표 줄의 값),
// 화살표는 맞추면 바뀌는 방향(2026-11-15 사용자 「대표 값이 얼마고 현재 값이 얼마나 이렇게 해줘야지」 — 전에는 이름표 없이 「대표 → 이 갈래」 라 바뀌는 방향과 거꾸로 읽혔다)
const olmDiffPart = (d) => `${d[1]}: 지금 ${d[3]} → 대표 ${d[2]}`;
const olmDiffText = (diff, n = 4) => {
  const parts = (diff || []).map(olmDiffPart);
  return parts.length > n ? `${parts.slice(0, n).join(" · ")} 외 ${parts.length - n}` : parts.join(" · ");
};
const olmDiffTitle = (diff) => "대표와 다른 값 — 맞추면 이 서식 줄들의 지금 값이 대표 값으로 바뀝니다\n" + (diff || []).map(olmDiffPart).join("\n"); // 풍선 도움말 — 줄인 것 없이 전부
const olmText = (pid) => (state.texts && state.texts[pid] != null ? state.texts[pid] : (state.byId.get(pid) || {}).text || "");

function olmRow(id, L) { // 레벨 줄 아래 「서식 n가지 · 대표 「…」」 + 「대표에 맞추기(m줄)」 + 갈래 목록(편 것만) — 그 레벨에 줄이 없으면 null
  const t = olmTpl(id);
  const os = t && t.slots ? t.slots[String(L)] : null;
  if (!os || !os.lines || os.table) return null; // 표 제목 레벨(넣은 표 줄 · 띠 표 줄)은 서식 갈래가 없다 — 「서식 정보 없음」 줄을 그리지 않는다
  const row = el("div", "olm");
  row.dataset.tpl = id;
  row.dataset.level = L;
  const v = olmFresh() ? olmSlotData(id, L) : null;
  if (!v) {
    row.append(el("span", "muted", olmFresh() ? "서식 정보 없음" : "서식 읽는 중…"));
    olmNeed(); // 줄마다 부르지 않게 — 한 번 읽고 한 번 다시 그린다
    return row;
  }
  const n = v.groups.length, key = `${id}|${L}`, open = olmOpenNow().open.has(key);
  row.classList.add(n > 1 || v.repMissing ? "olm-warn" : "olm-ok");
  const repG = v.groups.find((g) => g.rep), cand = olmTryOf(id, L, v);
  const sum = el("span", `olm-sum${n > 1 ? " warn" : ""}`, n > 1 ? `서식 ${n}가지` : "서식 1가지 — 모두 같음");
  sum.title = "이 레벨 줄들을 레터(레터 앞 빈칸·레터 글자·레터 뒤 빈칸) · 문단 모양(정렬·앞 여백·2번째 줄·간격·줄 간격) · 레터·본문 글자 모양이 같은 것끼리 묶었습니다";
  row.append(sum);
  if (cand) { // 대표 미리보기 중 — 끌어 놓은 갈래(대표는 아직 그대로)
    const rep = el("span", "olm-rep olm-rep-try");
    rep.append(el("span", "olm-rep-k", "미리보기 "), headsParaLink(OLM.try.pid, olmText(OLM.try.pid), 22, "끌어 놓은 서식 — 아직 대표가 아닙니다(아래 「대표로 정하기」 · 「취소」)"));
    row.append(rep);
  } else if (v.rep) {
    const rep = el("span", "olm-rep");
    rep.append(el("span", "olm-rep-k", "대표 "), headsParaLink(v.rep, olmText(v.rep), 22, "이 레벨의 대표 줄 — 새 줄과 「대표에 맞추기」 가 이 모양을 따릅니다"));
    row.append(rep);
  } else if (v.repMissing) row.append(el("span", "hb und", "대표 없음 — 줄 하나를 대표로"));
  const tog = hBtn(open ? "▾ 서식 목록" : "▸ 서식 목록", () => { if (OLM.open.has(key)) { OLM.open.delete(key); if (cand) OLM.try = null; } else OLM.open.add(key); olmRefresh(); }, // 접으면 미리보기도 거둔다
    { title: "서식마다 대표와 다른 값 · 줄 목록 · 대표로 정하기", cls: "btn sm olm-btn" });
  tog.setAttribute("aria-expanded", String(open));
  if (n > 1 || v.repMissing) row.append(tog);
  if (typeof olpOpen === "function") { // 떠 있는 창에서 갈래를 표로 견줌(outline_preview.js — 모달 아님)
    row.append(hBtn(n > 1 ? "비교" : "서식 값", () => olpOpen(id, L, "cmp"),
      { title: n > 1 ? "서식을 표로 견줍니다 — 서식마다 견본 글 · 대표와 다른 값만 · 서식별 맞추기(옆에 떠 있는 창)" : "이 레벨 서식의 값(레터·문단·글자 모양)을 옆에 떠 있는 창으로", cls: "btn sm olm-btn olm-cmp" }));
  }
  const pick = olmPick(id, L);
  if (pick && pick.pid !== v.rep) { // 원문에서 고른 줄 — 문서 표를 누른 줄, 아니면 커서 줄
    row.append(hBtn(`${pick.how} 줄을 대표로`, () => olmSetRep(id, L, pick.pid), { title: `${pick.how} 줄(${pick.pid} 「${short(olmText(pick.pid), 24)}」)을 이 레벨의 대표로 정합니다 — 문서는 안 바뀝니다`, cls: "btn sm olm-btn" }));
  }
  if (v.rep && v.others && !cand) { // 미리보기 중에는 미리보기 카드 · 「고른 서식 맞추기」 가 대신한다(지금 대표 기준의 단추를 같이 두면 헷갈림)
    row.append(hBtn(`대표에 맞추기(${nf(v.others)}줄)`, () => olmMatch(id, L, v.others),
      { title: `대표와 서식이 다른 이 레벨 줄 모두를 대표 모양으로 — 레터(레터 앞 빈칸·글자·레터 뒤 빈칸) · 문단 모양 · 레터·본문 바탕 글자 모양(강조한 글자는 그대로, 번호는 제 번호).${v.ownLines ? ` 다른 표의 서식 ${nf(v.ownLines)}줄은 건드리지 않습니다(그 표의 서식).` : ""} 「실행 취소」 로 되돌립니다`, cls: "btn sm primary olm-btn" }));
  }
  if (v.rep && v.ownLines && !cand) { // 표의 서식(spec_hwpx_웹편집 ② §8-11) — 그 표에 대표 서식의 줄이 없는 서식: 「대표에 맞추기」 가 건드리지 않는다
    const own = el("span", "muted olm-own", `표의 서식 ${nf(v.ownLines)}줄은 그대로`);
    own.title = "표 안의 줄은 표마다 서식이 따로입니다 — 대표 서식의 줄이 하나도 없는 표의 줄은 그 표의 서식이라 「대표에 맞추기」 가 건드리지 않습니다. 그 서식 카드의 「다른 템플릿으로」 로 떼면 그 표의 줄끼리만 서식을 견주고, 꼭 맞추려면 「이 줄들만 맞추기」 를 누르세요";
    row.append(own);
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

function olmList(id, L, v, repG) { // 갈래 목록 — 맨 위 대표 카드(미리보기 중이면 미리보기 카드 · 대표가 없으면 「대표 자리」) → 「☐ 모두 고르기 · 고른 서식 맞추기」 줄 → 다른 갈래들
  // 갈래 카드마다 [☐ ×수] [⠿ 끌기] [대표로 | 지금 대표] · 견본 줄 · 이 줄들만 맞추기 · 다른 템플릿으로 · 기준과 다른 값 · 줄 목록. 기준 = 대표 갈래(미리보기 중이면 끌어 놓은 갈래)
  const ul = el("ul", "olm-list");
  const pick = olmPick(id, L), cand = olmTryOf(id, L, v), base = cand || repG;
  const firstOf = (g) => (pick && g.paras.includes(pick.pid) ? pick.pid : g.paras[0]); // 고른 줄이 든 갈래면 그 줄을 대표로
  const others = v.groups.filter((g) => g !== base);
  const nos = olmNos(v); // 갈래 번호 — 본문 오른쪽 여백의 꼬리표와 같은 번호(자료의 갈래 차례 — 고르기·미리보기로는 안 바뀐다)
  // 여기서는 고르기(OLM.chk)를 고치지 않는다 — 그리는 길은 보이기만 한다: 없어진 갈래·기준이 된 갈래를 빼는 것은 olmPicksSettle(다시 그리기 앞 · 자료를 다시 읽은 뒤)
  if (cand) ul.append(olmTryCard(id, L, cand, repG, OLM.try.pid, nos.get(cand.key)));
  else if (repG) ul.append(olmCard(id, L, v, repG, { first: firstOf(repG), no: 0 }));
  else ul.append(olmSlotDrop(id, L)); // 대표가 없는 레벨 — 끌어 놓을 「대표 자리」
  if (base && others.length) ul.append(olmBulk(id, L));
  for (const g of others) ul.append(olmCard(id, L, v, g, { first: firstOf(g), cand, base, no: nos.get(g.key) }));
  olmPickPaint(ul, id, L); // ☐ · 「모두 고르기」 · 단추의 글을 지금 고르기대로(두 트리가 같은 것을 본다)
  if (cand) ul.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); olmTryEnd(); } });
  return ul;
}

function olmCard(id, L, v, g, { first, cand = null, base = null, no = null }) { // 갈래 카드 하나 — 대표 카드(미리보기가 아닐 때)는 끌어 놓는 곳, 다른 갈래는 끄는 것. no = 갈래 번호(olmNos — 0 = 대표)
  const isRep = g.rep && !cand;
  const li = el("li", `olm-g${isRep ? " rep" : ""}${g.rep && cand ? " was" : ""}${olmLooked(id, L, g.key) ? " sel" : ""}`); // .sel = 살펴보는 갈래(OLM.look — 다음 살펴보기까지)
  li.dataset.key = g.key;
  li._paras = g.paras;
  const head = el("div", "olm-gh");
  if (isRep) head.append(el("span", "hb olm-badge", "대표"), el("span", "olm-n", `×${nf(g.count)}`));
  else {
    if (no) { // 갈래 번호 — 본문 오른쪽 여백의 꼬리표 「서식 n」 과 같은 번호(「12개에서 뭔지」 를 번호로 잇는다 — 색으로 가르지 않는다)
      const tag = el("span", "olm-no", olmNoText(no));
      tag.title = `서식 번호 — 본문에서 이 서식의 줄 오른쪽 여백 꼬리표에 같은 번호 「${olmTagText(no)}」 가 붙습니다(고른 서식을 보거나 「본문에서 보기」 를 누른 동안). 번호는 서식을 다시 읽을 때만 바뀝니다`;
      head.append(tag);
    }
    if (base) { // 고르기 — ☐ 와 ×수가 한 label(×수를 눌러도 고른다). 바꾸는 길은 olmPickChange 하나(두 트리의 ☐ · 단추 글 · 본문 표시가 같이 바뀐다)
      const lab = el("label", "olm-pick"), cb = el("input", "olm-chk");
      cb.type = "checkbox";
      cb.title = `이 서식(${nf(g.count)}줄)을 고릅니다 — 본문에 고른 서식의 줄만 또렷이 보이고, 위 「고른 서식 맞추기」 로 고른 것을 한 번에 ${cand ? "미리보기 서식" : "대표 모양"}으로`;
      cb.onchange = () => {
        const want = cb.checked, ok = olmPickChange(id, L, (set) => { if (want) set.add(g.key); else set.delete(g.key); });
        if (ok && want !== olmChkSet(id, L).has(g.key)) olmRedraw(); // 이 목록이 지금 자료보다 옛것이다(그 갈래가 없어졌다) — 목록을 지금 것으로
      };
      lab.append(cb, el("span", "olm-n", `×${nf(g.count)}`));
      head.append(lab);
    } else head.append(el("span", "olm-n", `×${nf(g.count)}`));
    head.append(olmGrip(id, L, first));
    olmDragSrc(li, id, L, first);
    if (g.own) { // 표의 서식 — 이 서식의 줄이 든 표에는 대표 서식의 줄이 없다(② §8-11): 「대표에 맞추기」 가 건드리지 않는다
      const ob = el("span", "hb olm-badge was olm-ownb", "표의 서식");
      ob.title = `이 서식의 줄이 든 표${g.form ? `(머리글 「${g.form.label}」${g.form.tables > 1 ? ` · 표 ${nf(g.form.tables)}개` : ""}${g.form.around ? ` · 그 표의 다른 글 ${g.form.around}` : ""})` : ""}에는 대표 서식의 줄이 없습니다 — 그 표의 서식입니다. 「대표에 맞추기」 는 건드리지 않습니다(「다른 템플릿으로」 로 떼면 그 표의 줄끼리만 견줍니다)`;
      head.append(ob);
    }
    if (g.rep) head.append(el("span", "hb olm-badge was", "지금 대표"));
    else if (!cand) head.append(hBtn("대표로", () => olmSetRep(id, L, first), { title: `이 서식의 ${first === g.paras[0] ? "첫" : "고른"} 줄(${first})을 이 레벨의 대표로 — 문서는 안 바뀝니다`, cls: "btn sm olm-btn" }));
  }
  head.append(headsParaLink(first, olmText(first), 28), olmSeeBtn(id, L, g, no));
  if (!g.rep && v.rep && !cand) head.append(hBtn("이 줄들만 맞추기", () => olmMatch(id, L, g.count, [...g.paras]), { title: "이 서식의 줄들만 대표 모양으로", cls: "btn sm olm-btn" }));
  li.append(head);
  if (!g.rep && v.rep && !cand) { // 「다른 템플릿으로」 — 일부러 다르게 준 서식의 갈래를 서식 종속 템플릿 「T1L3a」 로 뗀다(② §8-5): 누르면 그 아래 한 줄(팝업 아님)
    const sk = `${id}|${L}|${g.key}`, form = olmSplitForm(id, L, g, first);
    form.hidden = !olmOpenNow().splitOpen.has(sk);
    const sb = hBtn("다른 템플릿으로", () => { form.hidden = !form.hidden; sb.setAttribute("aria-expanded", String(!form.hidden)); if (form.hidden) OLM.splitOpen.delete(sk); else OLM.splitOpen.add(sk); },
      { title: "서식이 다르면 템플릿도 다릅니다 — 이 서식의 줄을 이 레벨부터 시작하는 서식 종속 템플릿(「T1L3a」)으로 떼어 그 줄들끼리만 서식을 견주게 합니다(문서는 안 바뀜). 손으로 치다 생긴 흔들림이면 「이 줄들만 맞추기」", cls: "btn sm olm-btn olm-split" });
    sb.setAttribute("aria-expanded", String(!form.hidden));
    head.append(sb);
    li.append(form);
  }
  const diff = isRep ? [] : cand ? olmTryDiff(cand, g) : g.diff || []; // 미리보기 중이면 끌어 놓은 갈래와 견준 값(화면이 raw 로 셈 — 「대표」 = 미리보기 서식)
  if (diff.length) {
    const d = el("div", "olm-diff", olmDiffText(diff));
    d.title = olmDiffTitle(diff);
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
  if (isRep) olmDropTo(li, id, L);
  return li;
}

// ---------------------------------------------------------------- 대표 미리보기(끌어 놓기) · 고른 갈래 한 번에 맞추기 — 2026-11-16 사용자 「드래그 해서 대표로 갖어가면 그 서식으로 볼 수 있게 해줘」 ·
// 「클릭해서 한번에 변경하는 기능도 넣어줘, 체크체크체크 한번에 변경」(spec_hwpx_웹편집 ② §8-2 「대표 미리보기 · 고른 서식 맞추기」).
// 갈래 카드를 대표 카드(대표가 없으면 「대표 자리」)에 끌어 놓으면(⠿ 를 눌러도) 그 레벨이 **미리보기** — 문서·대표·실행 취소 기록은 안 바뀐다: 맨 위 미리보기 카드(그 갈래와 지금 대표의 견본 글을
// 저마다 제 서식으로) · 다른 갈래의 「대표와 다른 값」 을 그 갈래 기준으로 · 템플릿의 개요 레벨 그림도 그 서식으로. 「대표로 정하기」(PUT …/rep) · 「취소」(Esc · 지금 대표 갈래를 끌어 놓아도).
// 고른 갈래(☐)는 「고른 서식 맞추기」 한 번으로 기준 모양에 — 템플릿 맞추기 끝점 levels[{level, likes[고른 갈래의 첫 줄], rep?(미리보기 중이면 그 줄 — 대표를 바꾼 뒤 맞춤)}](트랜잭션 하나 · 실행 취소 1).
function olmChkSet(id, L) { const k = `${id}|${+L}`; let s = olmOpenNow().chk.get(k); if (!s) OLM.chk.set(k, (s = new Set())); return s; }
function olmTryOf(id, L, v) { // 이 레벨의 미리보기 갈래 | null(미리보기 아님 · 그 갈래가 없어짐 · 이미 대표가 됨)
  const t = OLM.try;
  if (!t || !v || t.epoch !== state.epoch || t.tpl !== String(id) || t.level !== +L) return null;
  const g = v.groups.find((x) => x.paras.includes(t.pid));
  return g && !g.rep ? g : null;
}
function olmTryDiff(b, g) { // 기준 갈래 b 와 갈래 g 의 다른 값 [[키, 이름, b 글, g 글]…] — 서버 diff 와 같은 꼴(KEYS 차례 · raw 로 견줌 · 글은 look)
  const ra = b.raw || {}, rg = g.raw || {}, la = b.look || {}, lg = g.look || {};
  const keys = OLM.keys && OLM.keys.length ? OLM.keys : Object.keys(ra).filter((k) => k !== "kin").map((k) => [k, k]);
  const glyph = !!ra.kin && ra.kin === rg.kin; // 레터 계열이 같다 = 닮은 레터 글자(「o」·「ㅇ」·「○」) — 서버 outline_match.diff 와 같은 이름(「레터」 는 레터가 다를 때만: spec_hwpx_웹편집 ② §8-5 「닮은 글자」)
  const out = keys.filter(([k]) => (ra[k] ?? null) !== (rg[k] ?? null)).map(([k, name]) => [k, k === "letter" && glyph ? "닮은 레터 글자" : name, la[k] ?? "—", lg[k] ?? "—"]);
  if (rg.form && (ra.form || "") !== rg.form) out.push(["form", "표", ra.formLabel || "표 밖", rg.formLabel || "—"]); // 표 안의 줄 — 기준 줄과 표(머리글)가 다르다(서버 diff 와 같은 줄: ② §8-11)
  return out;
}
function olmTry(id, L, pid) { // 그 줄이 든 갈래로 대표 미리보기 — 지금 대표 갈래면 미리보기를 거둔다
  const v = olmSlotData(id, L), g = v && v.groups.find((x) => x.paras.includes(pid));
  if (!g || g.rep) { olmTryEnd(); return; }
  OLM.try = { epoch: state.epoch, tpl: String(id), level: +L, pid };
  olmOpenNow().open.add(`${id}|${+L}`);
  olmRedraw();
  const sel = `.olm[data-tpl="${CSS.escape(String(id))}"][data-level="${+L}"] .olm-try`;
  const card = document.querySelector(`#headsDlgBody ${sel}`) || document.querySelector(`.tpl-tree ${sel}`);
  if (card) { card.scrollIntoView({ block: "nearest" }); const b = card.querySelector("button.primary"); if (b) b.focus({ preventScroll: true }); }
}
function olmTryEnd() { if (!OLM.try) return; OLM.try = null; olmRedraw(); }

function olmSamp(g) { // 갈래의 견본 글을 그 갈래 서식으로(outline_preview.js olpSample — 없으면 글만)
  return typeof olpSample === "function" ? olpSample(g) : headsParaLink(g.paras[0], olmText(g.paras[0]), 40);
}
function olmTryCard(id, L, cand, repG, pid, no = null) { // 맨 위 미리보기 카드 — 견본(미리보기 · 지금 대표) · 지금 대표와 다른 값 · 「대표로 정하기」 · 「취소」. 다른 갈래를 여기 끌어 놓으면 그 갈래로 바뀐다. no = 갈래 번호(미리보기로는 안 바뀐다)
  const li = el("li", `olm-g olm-try${olmLooked(id, L, cand.key) ? " sel" : ""}`);
  li.dataset.key = cand.key;
  li._paras = cand.paras;
  const head = el("div", "olm-gh");
  head.append(el("span", "hb olm-badge try", "대표 미리보기"));
  if (no) head.append(el("span", "olm-no", olmNoText(no)));
  head.append(el("span", "olm-n", `×${nf(cand.count)}`), headsParaLink(pid, olmText(pid), 28), olmSeeBtn(id, L, cand, no));
  li.append(head);
  const samps = el("div", "olm-samps");
  for (const [lab, g] of [["미리보기", cand], ...(repG ? [["지금 대표", repG]] : [])]) {
    const r = el("div", "olm-samp-row");
    r.append(el("span", "olm-samp-lab", lab), olmSamp(g));
    samps.append(r);
  }
  li.append(samps);
  if (repG) { // 대표를 이 서식으로 바꾸면 달라지는 값 — 「이름: 지금 대표 a → 미리보기 b」(값마다 이름표)
    const dd = olmTryDiff(repG, cand), part = (d) => `${d[1]}: 지금 대표 ${d[2]} → 미리보기 ${d[3]}`;
    if (dd.length) {
      const d = el("div", "olm-diff", dd.length > 4 ? `${dd.slice(0, 4).map(part).join(" · ")} 외 ${dd.length - 4}` : dd.map(part).join(" · "));
      d.title = "대표를 이 서식으로 바꾸면 달라지는 값\n" + dd.map(part).join("\n");
      li.append(d);
    }
  }
  const acts = el("div", "olm-try-acts");
  acts.append(hBtn("대표로 정하기", () => { OLM.try = null; olmSetRep(id, L, pid); }, { title: `이 서식의 줄(${pid})을 이 레벨의 대표로 — 문서는 안 바뀝니다(「실행 취소」 로 되돌림)`, cls: "btn sm primary olm-btn" }),
    hBtn("취소", () => olmTryEnd(), { title: "미리보기를 거둡니다(Esc) — 대표는 그대로", cls: "btn sm olm-btn" }));
  li.append(acts, el("div", "olm-note", "미리보기 — 문서와 대표는 아직 그대로입니다. 아래 서식들의 「대표」 값은 이 미리보기 기준입니다."));
  olmDropTo(li, id, L);
  return li;
}
function olmSlotDrop(id, L) { // 대표가 없는 레벨의 「대표 자리」 — 갈래를 끌어 놓으면 미리보기
  const li = el("li", "olm-g olm-slot", "대표 자리 — 아래 서식 카드를 여기로 끌어 놓거나 ⠿ 를 누르면 그 서식으로 미리 봅니다");
  olmDropTo(li, id, L);
  return li;
}
function olmGrip(id, L, pid) { // 끌기 손잡이 — 끌어서 대표 카드에 놓거나 눌러서 미리보기
  const b = el("button", "olm-grip", "⠿");
  b.type = "button";
  b.title = "끌어서 위 대표 카드에 놓으면 이 서식으로 대표를 미리 봅니다(눌러도 됨) — 문서·대표는 안 바뀝니다";
  b.setAttribute("aria-label", "이 서식으로 대표 미리보기");
  b.onclick = () => olmTry(id, L, pid);
  return b;
}
function olmDragSrc(li, id, L, pid) { // 갈래 카드를 끄는 것으로 — 끄는 동안 그 목록(ul)에만 표시 클래스(design.md §8: body·#doc 에 달지 않는다 · 「끌어 놓기」)
  li.draggable = true;
  li.addEventListener("dragstart", (e) => {
    OLM.drag = { epoch: state.epoch, tpl: String(id), level: +L, pid };
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", short(olmText(pid), 60)); } catch { /* 일부 브라우저 */ }
    setTimeout(() => { // dragstart 안에서 모양을 바꾸면 끌기가 끊기거나 멈춘다 — 다음 차례에(놓을 곳 표시는 겹쳐 그려 자리가 안 밀린다: .olm-drop-hint)
      if (!OLM.drag || OLM.drag.pid !== pid) return;
      li.classList.add("dragging");
      const ul = li.closest(".olm-list");
      if (ul) ul.classList.add("olm-dragging");
    }, 0);
  });
  li.addEventListener("dragend", () => {
    OLM.drag = null;
    li.classList.remove("dragging");
    for (const x of document.querySelectorAll(".olm-list.olm-dragging, .olm-g.over")) x.classList.remove("olm-dragging", "over");
  });
}
function olmDropTo(box, id, L) { // 끌어 놓는 곳(대표 카드 · 미리보기 카드 · 대표 자리) — 같은 레벨의 갈래만 받는다
  box.classList.add("olm-drop");
  const ok = () => { const d = OLM.drag; return !!d && d.epoch === state.epoch && d.tpl === String(id) && d.level === +L; };
  const over = (e) => { if (!ok()) return; e.preventDefault(); e.dataTransfer.dropEffect = "move"; box.classList.add("over"); };
  box.addEventListener("dragenter", over);
  box.addEventListener("dragover", over);
  box.addEventListener("dragleave", (e) => { if (!box.contains(e.relatedTarget)) box.classList.remove("over"); });
  box.addEventListener("drop", (e) => {
    if (!ok()) return;
    e.preventDefault();
    const d = OLM.drag;
    OLM.drag = null;
    box.classList.remove("over");
    olmTry(id, L, d.pid);
  });
  box.append(el("div", "olm-drop-hint", "여기에 놓으면 그 서식으로 대표를 미리 봅니다"));
}

function olmBulk(id, L) { // 「☐ 모두 고르기 · 고른 서식 n가지 맞추기(m줄)」 줄 — 켜짐·일부·단추의 글과 줄 수는 olmPickPaint 가 지금 고르기대로 채운다(카드의 ☐ 가 바뀔 때마다 — 목록을 다시 그리지 않는다: 고르는 동안 자리·초점 유지)
  const bar = el("li", "olm-bulk"), lab = el("label", "olm-pick olm-all"), all = el("input", "olm-chk");
  all.type = "checkbox";
  all.title = "이 레벨의 다른 서식을 모두 고르기 · 모두 풀기 — 본문에 고른 서식의 줄만 또렷이 보입니다";
  lab.append(all, el("span", null, "모두 고르기"));
  all.onchange = () => { const on = all.checked; olmPickChange(id, L, (set, others) => { for (const g of others) if (on) set.add(g.key); else set.delete(g.key); }); };
  bar.append(lab, hBtn("", () => olmBulkGo(id, L), { cls: "btn sm primary olm-btn olm-bulk-go" }));
  return bar;
}
async function olmBulkGo(id, L) { // 고른 갈래를 한 번에 — 템플릿 맞추기 끝점(트랜잭션 하나 · 실행 취소 1). 미리보기 중이면 대표를 그 줄로 바꾼 뒤 맞춘다.
  // 맞추는 것은 **고른 때의 갈래**여야 한다(2026-11-16 astra — 전에는 갈래의 첫 줄만 보내, 고른 뒤 그 줄의 서식이 바뀌면 서버가 그 줄의 새 서식과 같은 다른 줄을 맞췄다): 쓰던 글을 먼저 반영하고,
  // 그 사이 문서가 바뀌었으면 갈래를 다시 읽어 구성이 그대로인지 본 뒤(olmPicksCheck — 다르면 고르기를 비우고 알린다) 그 차례(rev)를 같이 보낸다. 서버가 차례가 다르다 하면(409) 아무것도 안 맞추고 고르기를 비운다.
  // 요청이 도는 동안에는 고르기를 못 바꾸고(OLM.going), 끝나면 **보낸 갈래만** 고른 것에서 뺀다(통째로 비우지 않는다).
  const k = olmPk(id, L);
  if (state.busy || OLM.going || !state.id || !(OLM.chk.get(k) || []).size) return;
  const epoch = state.epoch, t = olmTpl(id);
  OLM.going = k;
  olmPickSync(id, L);
  try {
    await flushAll();
    if (epoch !== state.epoch) return;
    for (let i = 0; i < 2 && !olmFresh(); i += 1) { await olmLoad(true); if (epoch !== state.epoch) return; } // 고른 뒤 문서 차례가 올랐다 — 갈래를 다시(읽고 있던 옛 응답을 받았으면 한 번 더)
    const set = OLM.chk.get(k), at = OLM.chkAt.get(k), o = olmParts(id, L);
    if (!set || !set.size || !at || !o) { olmRedraw(); return; } // 다시 읽어 보니 갈래 구성이 달라 고르기가 풀렸다(알림은 olmPicksCheck) — 목록을 지금 것으로
    if (!olmFresh()) { // 갈래를 못 읽었거나, 서버의 문서가 이 화면보다 앞서 있다(다른 곳에서 바뀜)
      if (OLM.err) toast("서식을 다시 읽지 못했습니다 — 잠시 뒤 다시 눌러 주세요", true); else olmPickStale(id, L);
      return;
    }
    const groups = o.others.filter((g) => set.has(g.key)), keys = groups.map((g) => g.key);
    if (!groups.length) return;
    const rep = o.cand && OLM.try ? OLM.try.pid : null;
    const lv = { level: +L, likes: groups.map((g) => g.paras[0]), ...(rep ? { rep } : {}) };
    const r = await olmApplyTpl(id, { rev: at.rev, levels: [lv] });
    if (epoch !== state.epoch) return;
    if (!r) { if (structOp.lastError && structOp.lastError.status === 409) olmPickStale(id, L); return; }
    if (rep) OLM.try = null;
    olmPickChange(id, L, (s) => { for (const key of keys) s.delete(key); }, true); // 본문 표시도 따라 꺼진다(그 레벨의 고르기가 켠 표시일 때)
    if (r.nothing) { toast("맞출 줄이 없습니다 — 고른 서식의 줄이 이미 같은 모양입니다"); return; }
    toast(`T${t ? t.no : id} L${L} ${rep ? `대표를 「${short(olmText(rep), 20)}」 로 정하고 ` : ""}고른 서식 ${nf(groups.length)}가지의 줄 ${nf(olmFit(r))}개를 그 모양으로 맞췄습니다${olmPut(r)} — 「실행 취소」 한 번으로 되돌립니다`);
  } finally {
    if (OLM.going === k) { OLM.going = null; if (epoch === state.epoch) olmPickSync(id, L); }
  }
}
function olmPickStale(id, L) { // 고른 뒤 문서가 바뀌었다(서버 409 · 서버의 문서가 이 화면보다 앞섬) — 고른 것을 믿을 수 없다: 그 레벨의 고르기를 비우고 알린 뒤 갈래를 다시 읽는다. 화면의 문서가 서버보다 옛것이면 문서도 다시 읽는다
  const epoch = state.epoch;
  olmPickChange(id, L, (s) => s.clear(), true);
  toast("문서가 바뀌었습니다 — 서식을 다시 골라 주세요", true);
  olmLoad(true).then(() => {
    if (epoch !== state.epoch) return;
    if (!OLM.err && OLM.rev != null && OLM.rev !== state.serverRev && typeof reloadDoc === "function") { // 다른 곳에서 바뀐 문서 — 이 화면의 문서·개요 오버레이를 서버 것으로
      reloadDoc().then(() => { if (epoch === state.epoch) outlineLoad(true); }).catch(() => {});
      return;
    }
    olmRefresh();
  });
}

// ---------------------------------------------------------------- 고른 갈래 ↔ 본문 표시 · 살펴보는 갈래 — 2026-11-16 사용자 「템플릿 관계에서 모두 고르기 를 하면 왼쪽 원문에도 관련된 것들이 모두 선택이 되어야지.
// 12개에서 내가 뭔지를 모르겠잖아. 이게 본문이랑 사이드패널 제어랑 연동이 안되어 있는거 같아 … 상호 동기화 되도록」(spec_hwpx_웹편집 ② §8-2 — astra 검토 2026-11-16).
// · 고르기의 원본은 OLM.chk 하나이고 **바꾸는 길도 하나**(olmPickChange — 카드의 ☐ · 「모두 고르기」 · 맞춘 뒤 정리): 집합을 고치고 → 그려 둔 모든 목록(같은 레벨이 「템플릿」 탭과 「템플릿 관계」 열 두 곳에
//   그려질 수 있다)의 ☐ · 「모두 고르기」 의 켜짐·일부 · 단추의 글·줄 수를 맞추고(olmPickSync) → 본문에 고른 갈래의 줄만 또렷이(olmPickShow → fmt_focus.js tplPickShow).
//   그리는 길(olmList)은 고르기를 고치지 않는다 — 지금 고를 수 없는 갈래(없어진 갈래 · 기준이 된 갈래)를 빼는 것은 olmPicksSettle(다시 그리기 앞 · 자료를 다시 읽은 뒤)이 한다.
// · 본문 표시의 수명: ☐ 를 하나라도 고르면 그 레벨의 고른 갈래 줄만 또렷이(켜져 있던 다른 표시는 갈아 끼운다) · 마지막 ☐ 를 풀면 **그 레벨의 고르기가 켠 표시일 때만** 끈다(다른 레벨의 표시 · 여백 표기를 눌러 켠 표시는 그대로) ·
//   이름 줄의 「끄기」 는 표시만 끄고 고르기는 남긴다(☐ 를 다시 건드리면 다시 보인다) · 열을 닫거나 목록을 접어도 그대로 · 다른 문서를 열면 둘 다 비운다(olmOpenNow · fmtFocusReset).
// · 갈래의 줄은 **자르지 않은 목록**으로(OLM.full — olmFull·olmFullLoad: 목록이 30줄에서 잘린 갈래가 있는 레벨만 GET …/outline/formats?tpl=&level= 로 줄 전부): 줄 → 갈래 · 갈래 → 줄.
//   「잘린 갈래가 하나면 목록에 없는 줄은 그 갈래」 로 어림하지 않는다 — 값 칸·서식을 못 읽은 줄은 어느 갈래에도 없다. 카드 찾기(olmMark·olmFocus) · 본문 표시 · 꼬리표가 같은 대응을 쓴다.
// · 갈래 번호(olmNos) = 자료의 갈래 차례(대표 = 「대표」 · 그 밖 「다른 서식 1」 …) — 카드 머리와 본문 오른쪽 여백의 꼬리표가 같은 번호다. 고르기·미리보기로는 안 바뀌고 자료를 다시 읽을 때만 바뀐다.
// · 고르기는 **고른 때의 갈래 구성**(OLM.chkAt — 문서 차례 rev · 그 레벨의 지문 sig)에 묶인다: 갈래를 다시 읽었을 때 지문이 다르면 그 레벨의 고르기를 비우고 한 번 알린다(olmPicksCheck — 갈래 key 는 문단 id 라
//   편집 뒤에는 같은 key 가 다른 갈래를 가리킬 수 있다: 말없이 옮겨 고르지 않는다). 같으면 차례만 올린다. 「고른 서식 맞추기」 는 그 차례를 보낸다(olmBulkGo). 실행 취소는 문서만 되돌린다 — 고르기는 되살리지 않는다.
// · 살펴보는 갈래(OLM.look) = 카드의 「본문에서 보기」 · 본문 꼬리표를 눌러 정한 갈래 하나. 고르기와 따로다(고르기를 안 바꾼다): 그 카드에 .sel(다음 살펴보기까지) · 본문의 그 갈래 줄 꼬리표에 강조.
//   캐럿 이동·본문 글 누름으로는 열을 움직이지 않는다(꼬리표를 눌렀을 때만).
const olmPk = (id, L) => `${id}|${+L}`;
const olmPkOf = (k) => { const i = k.lastIndexOf("|"); return [k.slice(0, i), +k.slice(i + 1)]; };
const olmRowsOf = (id, L) => document.querySelectorAll(`.tpl-tree .olm[data-tpl="${CSS.escape(String(id))}"][data-level="${+L}"]`); // 그 레벨의 그려 둔 줄 — 「템플릿」 탭 · 「템플릿 관계」 열 모두
const olmSig = (v) => (v ? v.sig || v.groups.map((g) => `${g.key}:${g.count}`).sort().join(",") : ""); // 그 레벨의 갈래 구성 지문 — 서버의 sig(줄 → 갈래), 옛 서버면 갈래 key·줄 수
function olmParts(id, L) { // 그 레벨의 지금 자료 → {v, repG, cand, base, others} | null — base = 기준 갈래(대표 · 미리보기 중이면 끌어 놓은 갈래) · others = 고를 수 있는 갈래(기준이 없으면 없다)
  const v = OLM.data && OLM.epoch === state.epoch ? olmSlotData(id, L) : null;
  if (!v) return null;
  const repG = v.groups.find((g) => g.rep) || null, cand = olmTryOf(id, L, v), base = cand || repG;
  return { v, repG, cand, base, others: base ? v.groups.filter((g) => g !== base) : [] };
}
function olmNos(v) { // 갈래 번호 Map(갈래 key → 번호) — 자료의 갈래 차례 그대로: 대표 = 0(「대표」), 그 밖은 1부터(「다른 서식 1」 …)
  const m = new Map();
  let n = 0;
  for (const g of v ? v.groups : []) m.set(g.key, g.rep ? 0 : (n += 1));
  return m;
}
const olmNoText = (no) => (no ? `다른 서식 ${no}` : "대표");
const olmTagText = (no) => (no ? `서식 ${no}` : "대표"); // 본문 오른쪽 여백 꼬리표의 짧은 꼴 — 여백이 좁아(56px 안팎) 「다른 서식 3」 은 번호가 잘린다(fmt_focus.js fmtFocusTags 가 같은 글을 쓴다)

// 줄 전부의 갈래 대응 — 항목 {st: "ready", rev, list(목록으로 지었나), of: Map(줄 → 갈래 key), by: Map(갈래 key → [줄…])} | {st: "pending"}(읽어야 함·읽는 중) | {st: "error"} | {st: "none"}(그 레벨의 갈래 자료 없음).
// 갈래 자료(OLM.data)의 그 문서 차례(OLM.rev)에 묶인다 — 차례가 달라지면 버린다. 잘린 갈래가 없으면 목록이 곧 전부라 읽지 않고 짓는다.
function olmFull(id, L) { // → 지금 쓸 수 있는 항목(읽지는 않는다 — 읽기는 olmFullLoad)
  olmOpenNow();
  const k = olmPk(id, L), v = OLM.data && OLM.epoch === state.epoch ? olmSlotData(id, L) : null;
  if (!v) return { st: "none" };
  const cut = v.groups.some((g) => g.more > 0);
  let e = OLM.full.get(k);
  if (e && (e.rev !== OLM.rev || (e.list && cut))) { OLM.full.delete(k); e = null; } // 다른 차례의 것 · 목록으로 지었는데 그 목록이 잘려 있다
  if (!e && !cut) {
    e = { st: "ready", rev: OLM.rev, list: true, of: new Map(), by: new Map() };
    for (const g of v.groups) { e.by.set(g.key, g.paras); for (const pid of g.paras) e.of.set(pid, g.key); }
    OLM.full.set(k, e);
  }
  return e || { st: "pending" };
}
function olmFullLoad(id, L, tries = 0) { // 줄 전부의 갈래 대응을 (필요하면) 읽는다 → Promise(항목) — 실패는 {st: "error"}(다시 부르면 다시 읽는다).
  // 응답은 그 요청이 아직 그 레벨의 것일 때만 쓴다: 그 사이 다른 문서를 열었으면 버리고, 갈래 자료의 차례가 바뀌어 밀려났으면(읽는 동안 문서가 바뀜) 지금 차례로 다시 읽는다(두 번까지)
  const e0 = olmFull(id, L);
  if (e0.st === "ready" || e0.st === "none") return Promise.resolve(e0);
  if (e0.st === "pending" && e0.p) return e0.p;
  const k = olmPk(id, L), doc = state.id, epoch = state.epoch, e = { st: "pending", rev: OLM.rev, list: false, p: null };
  const mine = () => epoch === state.epoch && OLM.full.get(k) === e;
  const again = () => (epoch !== state.epoch ? { st: "none" } : tries < 2 ? olmFullLoad(id, L, tries + 1) : { st: "error" });
  OLM.full.set(k, e);
  e.p = api(`/api/docs/${doc}/outline/formats?${new URLSearchParams({ tpl: String(id), level: +L })}`).then(async (r) => {
    if (!mine()) return again();
    if (!r || !r.full) { e.st = "error"; return e; } // 옛 서버(인자를 모름 — 잘린 목록 그대로) — 줄 전부를 알 수 없다
    const v = r.slots && r.slots[String(id)] ? r.slots[String(id)][String(+L)] || null : null;
    e.of = new Map(); e.by = new Map();
    for (const g of v ? v.groups : []) { e.by.set(g.key, g.paras); for (const pid of g.paras) e.of.set(pid, g.key); }
    e.rev = r.rev; e.st = "ready";
    if (r.rev === OLM.rev) return e;
    await olmLoad(true); // 갈래 자료보다 새 차례의 답 — 카드·번호의 자료와 어긋난다: 갈래를 다시 읽어 차례를 맞춘다(맞으면 이 항목이 그대로 쓰인다 · 또 어긋났으면 다시)
    const got = epoch === state.epoch ? olmFull(id, L) : { st: "none" };
    return got.st === "ready" || got.st === "none" ? got : again();
  }).catch(() => { if (!mine()) return again(); e.st = "error"; return e; }).finally(() => { e.p = null; });
  return e.p;
}
function olmKeyOf(id, L, pid) { // 그 줄이 든 갈래의 key — null = 어느 갈래에도 없는 줄(값 칸 · 서식을 못 읽은 줄) · undefined = 아직 모른다(줄 전부를 읽어야 안다 — olmFullLoad)
  const m = olmFull(id, L);
  if (m.st === "ready") return m.of.has(pid) ? m.of.get(pid) : null;
  const v = olmSlotData(id, L), g = v ? v.groups.find((x) => x.paras.includes(pid)) : null; // 목록에 있는 줄이면 그 갈래가 맞다
  return g ? g.key : undefined;
}

function olmPickPaint(root, id, L) { // 그려 둔 목록 하나(root — 레벨 줄 · 붙이기 전의 목록)의 고르기 모습을 지금 고르기대로: 카드의 ☐ · 「모두 고르기」 의 켜짐·일부 · 단추의 글·줄 수·켜짐
  const k = olmPk(id, L), set = OLM.chk.get(k) || new Set(), lock = OLM.going === k;
  for (const cb of root.querySelectorAll("li.olm-g .olm-chk")) { cb.checked = set.has(cb.closest("li.olm-g").dataset.key); cb.disabled = lock; }
  const bar = root.querySelector("li.olm-bulk"), o = bar ? olmParts(id, L) : null;
  if (!bar) return;
  const all = bar.querySelector(".olm-all .olm-chk"), go = bar.querySelector(".olm-bulk-go"), others = o ? o.others : [], cand = o ? o.cand : null;
  const on = others.filter((g) => set.has(g.key)), lines = on.reduce((a, g) => a + g.count, 0);
  all.checked = on.length > 0 && on.length === others.length;
  all.indeterminate = on.length > 0 && on.length < others.length;
  all.disabled = lock;
  go.disabled = !on.length || lock;
  go.textContent = `${cand ? "대표로 정하고 " : ""}고른 ${on.length ? `서식 ${nf(on.length)}가지 ` : "서식 "}맞추기${on.length ? `(${nf(lines)}줄)` : ""}`;
  go.title = on.length ? `고른 서식 ${nf(on.length)}가지의 줄 ${nf(lines)}개를 ${cand ? "미리보기 서식(대표를 그 줄로 바꾼 뒤)" : "대표"} 모양으로 한 번에 — 「실행 취소」 한 번으로 되돌립니다\n고른 뒤 문서가 바뀌어 서식 구성이 달라졌으면 맞추지 않고 다시 고르게 합니다`
    : "서식 카드의 ☐ 를 골라 한 번에 맞춥니다 — 고른 서식의 줄은 본문에 또렷이 보입니다";
}
function olmPickSync(id, L) { for (const row of olmRowsOf(id, L)) olmPickPaint(row, id, L); } // 두 트리의 같은 레벨을 같이
function olmPickShow(id, L, own = false) { // 그 레벨의 고르기를 본문에 — 고른 갈래의 줄만 또렷이(켜져 있던 다른 표시는 갈아 끼운다). 고른 것이 없으면 그 레벨의 고르기가 켠 표시일 때만 끈다.
  // own = 그 레벨의 고르기가 켠 표시가 켜져 있을 때만 고친다(사람이 ☐ 를 건드린 것이 아닐 때 — 「끄기」 로 꺼 둔 표시를 다시 켜지 않는다)
  if (typeof tplPickShow !== "function") return;
  const mine = tplPickOwns(id, L);
  if (own && !mine) return;
  const set = OLM.chk.get(olmPk(id, L)), t = olmTpl(id);
  if (set && set.size) tplPickShow({ tpl: String(id), level: +L, no: t ? t.no : id, focus: olmKey(id) }, set);
  else if (mine) fmtFocusOff();
}
function olmPickChange(id, L, fn, force = false) { // 고르기를 바꾸는 **하나뿐인 길** → 바꿨나. fn(set, others) 가 집합을 고친다. 맞추기 요청이 도는 동안에는 못 바꾼다(화면의 ☐ 만 되돌린다) — force = 그 요청 자신의 정리
  const k = olmPk(id, L);
  if (!force && (state.busy || OLM.going)) { olmPickSync(id, L); return false; }
  const o = olmParts(id, L), set = olmChkSet(id, L);
  fn(set, o ? o.others : []);
  for (const key of [...set]) if (!o || !o.others.some((g) => g.key === key)) set.delete(key); // 지금 자료에 없는 갈래 · 기준 갈래는 고를 수 없다
  if (!set.size) OLM.chkAt.delete(k);
  else if (!OLM.chkAt.has(k)) OLM.chkAt.set(k, { rev: OLM.rev, sig: olmSig(o.v) }); // 이 고르기가 본 갈래 자료 — 문서 차례 · 갈래 구성 지문
  OLM.chkGen += 1;
  olmPickSync(id, L);
  olmPickShow(id, L);
  if (!force && !olmFresh()) olmLoad().then((d) => { if (d) olmRedraw(); }); // 화면의 목록이 지금 문서보다 옛것일 수 있다 — 갈래를 다시 읽어 고른 것이 그대로인지 본다(olmPicksCheck)
  return true;
}
function olmPicksSettle() { // 다시 그리기 앞(olmRedraw) · 자료를 다시 읽은 뒤 — 고른 것 가운데 지금 고를 수 없는 갈래(없어진 갈래 · 기준이 된 갈래: 대표 미리보기를 시작함·거둠 · 대표를 바꿈)를 뺀다.
  // 바뀐 레벨은 그려 둔 ☐ 와 본문 표시(그 레벨의 고르기가 켠 것일 때)도 맞춘다. 살펴보는 갈래가 없어졌으면 그것도 거둔다
  olmOpenNow();
  for (const [k, set] of OLM.chk) {
    if (!set.size) continue;
    const [id, L] = olmPkOf(k), o = olmParts(id, L), was = [...set].sort().join("|");
    if (!o) continue; // 갈래를 읽는 중 — 읽은 뒤 olmPicksCheck 가 본다
    for (const key of [...set]) {
      if (o.others.some((g) => g.key === key)) continue;
      set.delete(key);
      // 갈래의 key 는 그 갈래의 한 줄이라, 구성이 그대로여도(여기 남은 고르기는 지문이 같은 것만이다 — olmPicksCheck) 가리키는 줄이 바뀔 수 있다(대표를 바꿈 · key 줄의 장평·자간만 바뀜):
      // 그 줄이 지금 든 갈래가 고를 수 있는 갈래면 같은 갈래다 — 새 key 로 잇는다. 기준이 됐거나 못 찾으면 뺀다
      const nk = olmKeyOf(id, L, key);
      if (nk != null && o.others.some((g) => g.key === nk)) set.add(nk);
    }
    if ([...set].sort().join("|") === was) continue;
    if (!set.size) OLM.chkAt.delete(k);
    OLM.chkGen += 1;
    olmPickSync(id, L);
    olmPickShow(id, L, true);
  }
  const lk = OLM.look, lv = lk ? olmSlotData(lk.tpl, lk.level) : null;
  if (lk && (lk.epoch !== state.epoch || (lv && !lv.groups.some((g) => g.key === lk.key)))) OLM.look = null;
  if (typeof fmtFocusRel === "function") fmtFocusRel(); // 본문의 꼬리표·설명 — 살펴보는 갈래 · 대표 미리보기가 바뀌었으면 다시(같으면 그대로)
}
function olmPicksCheck() { // 서식 갈래를 다시 읽었다(olmLoad) · 한 레벨을 새 답으로 바꿨다(olmSetRep) — 고른 때의 지문(OLM.chkAt.sig)과 지금 자료를 견줘, 갈래 구성이 달라진 레벨의 고르기는 비우고 **한 번** 알린다.
  // 같으면 그 고르기는 지금 차례에도 맞는 것이다 — 차례(rev)만 올린다(「고른 서식 맞추기」 가 그 차례를 보낸다)
  olmOpenNow();
  const gone = [];
  for (const [k, set] of OLM.chk) {
    if (!set.size) continue;
    const [id, L] = olmPkOf(k), v = olmSlotData(id, L), at = OLM.chkAt.get(k);
    if (v && at && at.sig === olmSig(v)) { at.rev = OLM.rev; continue; }
    set.clear();
    OLM.chkAt.delete(k);
    OLM.chkGen += 1;
    gone.push([id, L]);
  }
  for (const [id, L] of gone) { olmPickSync(id, L); olmPickShow(id, L, true); }
  olmPicksSettle();
  if (gone.length) {
    const names = gone.map(([id, L]) => { const t = olmTpl(id); return `T${t ? t.no : id} L${L}`; }).join(" · ");
    toast(`${names} 의 서식 구성이 바뀌었습니다 — 고른 것을 풀었습니다. 서식을 다시 골라 주세요`);
  }
}

const olmLooked = (id, L, key) => { const k = OLM.look; return !!k && k.epoch === state.epoch && k.tpl === String(id) && k.level === +L && k.key === key; };
function olmLookPaint() { // 살펴보는 갈래의 카드에 .sel(두 트리 모두) — 다른 카드의 .sel 은 걷는다
  for (const x of document.querySelectorAll(".tpl-tree li.olm-g.sel")) x.classList.remove("sel");
  const k = OLM.look;
  if (!k || k.epoch !== state.epoch) return;
  for (const row of olmRowsOf(k.tpl, k.level)) for (const li of row.querySelectorAll("li.olm-g")) if (li.dataset.key === k.key) li.classList.add("sel");
}
function olmLookSet(id, L, key) { // 살펴보는 갈래를 정한다(고르기는 안 바뀐다) — 카드의 .sel · 본문 꼬리표의 강조
  OLM.look = key == null ? null : { epoch: state.epoch, tpl: String(id), level: +L, key };
  olmLookPaint();
  if (typeof fmtFocusRel === "function") fmtFocusRel();
}
function olmSeeBtn(id, L, g, no) { // 카드의 「본문에서 보기」 — 카드 → 본문 찾기
  const name = no != null ? olmNoText(no) : "이 서식";
  return hBtn("본문에서 보기", () => olmSee(id, L, g), { cls: "btn sm olm-btn olm-see",
    title: `본문에서 ${name} 줄 ${nf(g.count)}개를 찾습니다 — 이 레벨의 줄만 또렷이 보이고(고른 서식을 보는 중이면 그대로) 이 서식의 줄마다 쪽 오른쪽 여백에 「${no != null ? olmTagText(no) : "서식 n"}」 꼬리표가 붙습니다 · 첫 줄로 갑니다\n고르기(☐)는 안 바뀝니다 · 끄기는 문서 이름 줄의 「끄기」` });
}
function olmSee(id, L, g) { // 이 갈래를 살펴보는 것으로 — 그 레벨의 본문 표시를 켜고(같은 레벨의 표시가 켜져 있으면 그대로: 고른 갈래를 보는 중이면 그것을 한 갈래로 바꾸지 않는다) 이 갈래의 첫 줄로. 고르기는 안 바뀐다
  const t = olmTpl(id), first = g.paras[0];
  OLM.look = { epoch: state.epoch, tpl: String(id), level: +L, key: g.key };
  olmLookPaint();
  if (typeof tplFocusIs === "function" && !tplFocusIs(id, L)) tplFocusOn({ tpl: String(id), level: +L, no: t ? t.no : id, para: first, focus: olmKey(id) }); // 레벨 전체로 — 고르기가 켠 표시가 아니다
  else if (typeof fmtFocusRel === "function") fmtFocusRel();
  if (first) headsGo(first);
}
function olmLookFrom(at, focus) { // 본문 꼬리표를 눌렀다(fmt_focus.js) — 그 줄의 갈래를 「템플릿 관계」 에서 살펴본다(고르기는 안 바뀐다).
  // 열이 열려 있고 그 레벨 줄이 보이면 열을 다시 짓지 않고 그 레벨 줄만 다시 그려(목록을 펴) 카드로 간다 — 펼친 것·스크롤이 그대로. 아니면 열을 연다(tplRelOpen → olmFocus)
  const row = olmColOn() && !colFolded("heads") ? document.querySelector(`#headsDlgBody .olm[data-tpl="${CSS.escape(String(at.tpl))}"][data-level="${+at.level}"]`) : null;
  if (row && row.getClientRects().length) olmFocus(at, true); else tplRelOpen(focus, at);
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
    note.textContent = m ? `이 서식의 ${nf(g.count)}줄(과 그 아래 줄)을 T${m.no} 로 옮깁니다 — 대표·서식은 T${m.no} 것 그대로(옮긴 뒤 그 템플릿에서 「대표에 맞추기」)`
      : `서식 종속 템플릿 T${t.no}L${L}${next} 를 만듭니다 — 이 서식의 ${nf(g.count)}줄(과 그 아래 줄)이 옮겨 가고 이 서식이 그 템플릿 L${L} 의 대표 · 줄은 L${L} 부터${L > 1 ? `(L1${L > 2 ? `~L${L - 1}` : ""} 은 T${t.no} 의 레벨)` : ""} · T${t.no} L${L} 의 서식 목록에서 빠집니다`;
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
  olmPicksSettle(); // 고른 갈래(☐)를 지금 고를 수 있는 것으로 먼저 — 그리는 길(olmList)은 고르기를 고치지 않는다(「고른 갈래 ↔ 본문 표시」)
  for (const old of document.querySelectorAll(".tpl-tree .olm")) { // 「템플릿」 탭과 「템플릿 관계」 열의 트리 모두(같은 줄이 두 곳에 있을 수 있다)
    const fresh = olmRow(old.dataset.tpl, +old.dataset.level);
    if (!fresh) { old.remove(); continue; }
    old.replaceWith(fresh);
  }
  for (const box of document.querySelectorAll(".tpl-tree .tpl-pic")) olmPicFill(box); // 개요 레벨 그림도 새 대표 서식으로
  for (const old of document.querySelectorAll(".tpl-tree .olm-tm")) old.replaceWith(olmTplMatch(old.dataset.tpl)); // 「대표 맞추기(n줄)」 의 줄 수도
  if (typeof olmOddRefresh === "function") olmOddRefresh(); // 「다른 서식 보기(n가지)」 의 수 · 펼친 묶음도(outline_odd.js)
  if (OLM.sel) olmMark(OLM.sel);
  if (typeof olpRefresh === "function") olpRefresh(); // 「서식 비교」·자리 미리보기 창 — 새 갈래로
  if (typeof tplAgentSync === "function") tplAgentSync(); // 열려 있는 서식 정리 에이전트 열의 대상 칸(tpl_agent.js)
}

function olmMark(at) { // 문서 표·꼬리표에서 온 줄 — 그 레벨 줄을 표시(.olm.sel — 잠시)하고 살펴보는 갈래의 카드에 .sel(olmLookPaint — 다음 살펴보기까지) → 보일 줄
  let first = null;
  for (const row of olmRowsOf(at.tpl, at.level)) {
    row.classList.add("sel");
    if (!first || row.closest("#headsDlgBody")) first = row; // 보일 줄 = 「템플릿 관계」 열의 것(문서 표를 누르면 그 열이 열린다)
  }
  olmLookPaint();
  return first;
}

function olmFocus(at, keep = false) { // tplRelOpen 이 부른다 — 그 레벨의 갈래 목록을 펴고 그 줄이 든 갈래를 살펴보는 것으로(OLM.look — 카드에 .sel · 고르기는 안 바뀐다).
  // keep = 열을 그대로 두고 그 레벨 줄만 다시 그린다(본문 꼬리표를 눌렀을 때 — olmLookFrom). 그 줄의 갈래는 줄 전부의 갈래 대응으로 찾는다(목록이 30줄에서 잘린 갈래의 31번째 줄도 — 읽어야 하면 읽은 뒤)
  if (!at || at.tpl == null) return;
  OLM.sel = at;
  OLM.pick = { ...at, epoch: state.epoch }; // 표시(sel)는 잠시 · 고른 줄(pick)은 「대표로」 가 쓴다
  olmOpenNow();
  const key = `${at.tpl}|${+at.level}`, epoch = state.epoch;
  const v = olmFresh() ? olmSlotData(at.tpl, at.level) : null;
  if (!v || v.groups.length > 1) OLM.open.add(key);
  const look = () => { // → 그 줄의 갈래를 알았나(어느 갈래에도 없는 줄 = 값 칸이면 살펴보는 갈래는 그대로 둔다)
    const k = at.para ? olmKeyOf(at.tpl, at.level, at.para) : null;
    if (k === undefined) return false;
    if (k != null) olmLookSet(at.tpl, at.level, k);
    return true;
  };
  const show = () => {
    const row = olmMark(at), card = row ? row.querySelector("li.olm-g.sel") : null;
    if (card) card.scrollIntoView({ block: keep ? "nearest" : "center" }); else if (row) row.scrollIntoView({ block: keep ? "nearest" : "center" });
  };
  const go = () => {
    if (epoch !== state.epoch || OLM.sel !== at) return;
    const known = look();
    if (!keep) olmRedraw();
    else for (const old of olmRowsOf(at.tpl, at.level)) { const fresh = olmRow(at.tpl, +at.level); if (fresh) old.replaceWith(fresh); } // 그 레벨 줄만(목록을 편 채로) — 열의 다른 것은 그대로
    show();
    if (!known) olmFullLoad(at.tpl, at.level).then(() => { if (epoch === state.epoch && OLM.sel === at && look()) show(); });
    setTimeout(() => { if (OLM.sel === at) { OLM.sel = null; for (const e of document.querySelectorAll(".tpl-tree .olm.sel")) e.classList.remove("sel"); } }, 4000);
  };
  if (olmFresh()) go(); else olmLoad().then(go);
}

async function olmSetRep(id, L, pid) {
  if (state.busy || !state.id) return;
  const epoch = state.epoch, doc = state.id; // 문서는 기다리기 전에 잡는다(structOp 와 같은 까닭 — 글 반영을 기다리는 사이 다른 문서를 열면 그 문서의 대표를 바꾸게 된다: 2026-11-16 astra)
  try {
    await flushAll();
    if (epoch !== state.epoch) return;
    const r = await api(`/api/docs/${doc}/outline/slots/${encodeURIComponent(id)}/${L}/rep`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ para: pid }) });
    if (epoch !== state.epoch) return;
    const fresh = olmFresh(); // 가진 갈래 자료가 이 요청 직전 문서의 것인가 — 아니면 이 레벨만 새 답으로 바꿔도 다른 레벨은 옛것이다: 차례를 올리지 않고 아래 olmRefresh 가 다시 읽게 둔다
    applyEditState(r);
    if (r.outline && !r.outline.off) heads.outline = r.outline;
    if (fresh && r.slot) { (OLM.data[String(id)] = OLM.data[String(id)] || {})[String(L)] = r.slot; OLM.rev = r.rev; OLM.epoch = state.epoch; olmPicksCheck(); } // 고른 갈래 — 새 자료와 견준다(기준이 된 갈래는 빠진다)
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
  toast(`T${t ? t.no : id} L${L} 줄 ${nf((r.left || []).length ? olmFit(r) : olmFit(r) || n)}개를 대표 모양으로 맞췄습니다${olmPut(r)} — 「실행 취소」 로 되돌립니다`);
}
// 맞추기 답의 줄 수 — changed = 바뀐 줄 모두 · placed = 그 가운데 대표에 맞춘 줄이 아니라 확정 서식(레터 뒤 묶음 빈칸 · 둘째 줄 = 글 시작 — spec_hwpx_웹편집 ② §8-8)만 걸린 줄(대표 · 대표 갈래)
// left = 형광펜·필드·변경 추적 표지 때문에 글을 못 바꿔 모양만 맞추고 남긴 줄(changed 에도 든다 — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」) [{id, tpl, no, level, why, kinds}]
const olmFit = (r) => (r.changed || []).length - (r.placed || []).length - (r.left || []).length; // 대표에 맞춘 줄(모양만 맞춘 줄은 빼고)
const olmPut = (r) => ((r.placed || []).length ? ` · 자리 맞춤 ${nf(r.placed.length)}줄(묶음 빈칸 · 둘째 줄 = 글 시작)` : "") + olmLeft(r);
const OLM_WHY = { letter: "레터를 바꿔야 함", inside: "빈칸 사이에 표지", field: "필드가 레터 앞·뒤 빈칸에 걸침", track: "변경 추적이 레터 앞·뒤 빈칸에 걸침", unpaired: "짝이 안 맞는 표지" };
function olmLeft(r) { // 맞추기 끝난 알림의 한 구절 — 모양만 맞춘 줄 수 · 표지 종류 · 까닭(글은 그대로)
  const xs = r.left || [];
  if (!xs.length) return "";
  const kinds = [...new Set(xs.flatMap((x) => x.kinds || []))].join("·") || "표지";
  const why = Object.entries(xs.reduce((a, x) => { const w = OLM_WHY[x.why] || x.why || "표지"; a[w] = (a[w] || 0) + 1; return a; }, {})).map(([w, n]) => `${w} ${nf(n)}`).join(" · ");
  return ` · ${kinds} 표지가 있어 모양만 맞춘 줄 ${nf(xs.length)}(글은 그대로 — ${why})`;
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
    if (!A || A.kind === "band") continue; // 띠 표 템플릿(「별첨N」 — spec_헤딩_추출 ② §6 「띠 표 줄」) 아래의 줄은 제 템플릿 그대로 — 종속 템플릿을 만들지 않는다
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

function olmTplTools(li, row, id) { // 템플릿 줄 머리 — 종속 템플릿 표지 · 이 템플릿으로 만든 종속 템플릿 「T1T3 · 떼기」 · 「대표 맞추기」 · 「다른 서식 보기」 · 「하위로」(넣을 자리가 없어도 보인다 — 누르면 까닭)
  const t = olmTpl(id);
  if (!t) return;
  if (t.comp) {
    const chip = el("span", "olm-chip", `종속 — T${t.comp.parentNo} L${t.comp.at} 아래 T${t.comp.childNo}`);
    chip.title = `T${t.comp.childNo} 를 T${t.comp.parentNo} L${t.comp.at} 아래로 넣어 만든 종속 템플릿 — L1~L${t.comp.at} 은 T${t.comp.parentNo} 의 레벨, L${t.comp.at + 1} 부터 T${t.comp.childNo} 의 레벨. 서식·대표·맞추기는 이 종속 템플릿의 줄끼리만 견줍니다`;
    row.append(chip, hBtn("떼기", () => olmUnmerge(t.comp.child, t.comp.parent), { title: `종속 템플릿을 지우고 그 줄을 T${t.comp.childNo} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn" }));
  }
  for (const m of t.made || []) {
    const chip = el("span", "olm-chip", `→ T${m.no}(${nf(m.moved)}줄)`);
    chip.title = `이 템플릿의 줄 ${nf(m.moved)}개를 T${m.parentNo} L${m.at} 아래로 넣어 종속 템플릿 T${m.no} 를 만들었습니다`;
    row.append(chip, hBtn("떼기", () => olmUnmerge(id, m.parent), { title: `T${m.no} 를 지우고 그 줄을 T${t.no} 로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn" }));
  }
  if (t.vari) { // 서식 종속 템플릿 — 「서식 종속 — T1 L3 의 다른 서식 · 합치기」(② §8-5)
    const v = t.vari, chip = el("span", "olm-chip", `서식 종속 — T${v.ofNo} L${v.level} 의 다른 서식`);
    chip.title = `T${v.ofNo} L${v.level} 에서 서식이 달라 뗀 템플릿${v.level > 1 ? ` — L1${v.level > 2 ? `~L${v.level - 1}` : ""} 은 T${v.ofNo} 의 레벨, 이 템플릿의 줄은 L${v.level} 부터` : ""}. 서식·대표·맞추기는 이 템플릿의 줄끼리만 견줍니다`;
    row.append(chip, hBtn("합치기", () => olmUnsplit(id), { title: `이 템플릿을 지우고 그 줄을 T${v.ofNo} 의 같은 레벨로 되돌립니다(「실행 취소」 로도 됨)`, cls: "btn sm olm-btn olm-unsplit" }));
  }
  row.append(olmTplMatch(id)); // 「대표 맞추기(n줄)」 — 이 템플릿(종속 템플릿이면 그 줄만)의 모든 레벨을 한 번에(전 이름 「템플릿 맞추기」 — 2026-11-16 사용자 「대표 맞추기.. 로 하면 되겠네」)
  if (typeof olmOddBtn === "function") row.append(olmOddBtn(id)); // 「다른 서식 보기(n가지)」 — 레벨마다 대표와 다른 서식을 그림 아래에 펴 보인다(outline_odd.js)
  if (t.all) { row.append(el("span", "olm-chip into", "줄을 다 넣음")); return; }
  if (!t.lines || t.vari || t.kind === "band") return; // 서식 종속 템플릿은 이미 제 템플릿의 레벨 아래 — 「하위로」 없음 · 띠 표 템플릿은 늘 문서 맨 위(다른 템플릿 아래로 넣지 않는다)
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
    note.textContent = `종속 템플릿 ${p.to.split(" ")[0]} 을 만듭니다 — 「${[...(A.chain || []).slice(0, p.at), ...(t.chain || []).slice(t.base || 0)].join(" › ")}」 · 그 자리의 T${t.no} 줄만(다른 자리의 T${t.no} · T${A.no || p.parent} 는 그대로) · 넣은 뒤 그 줄들만 따로 「대표 맞추기」`;
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
function olmTplMatch(id) { // 템플릿 줄의 「대표 맞추기(n줄)」 자리(전 이름 「템플릿 맞추기」·「종속 템플릿 맞추기」) — 맞출 줄이 없으면 빈 자리(갈래를 읽은 뒤 olmRedraw 가 다시 채운다)
  const box = el("span", "olm-tm");
  box.dataset.tpl = id;
  const t = olmTpl(id), o = t ? olmTplOthers(id) : null;
  if (!o) { olmNeed(); return box; }
  const P = olmTplPlan(id);
  if (P) { // ★ 계획대로 — 에이전트가 고른 그대로(남긴 갈래는 빼고)
    const todo = tpaTodoOf(P), keep = (P.plan.levels || []).reduce((a, lv) => a + (lv.keep || []).reduce((b, g) => b + (g.count || 0), 0), 0);
    const why = `★ 서식 정리 계획(${fmtWhen(P.at)})대로 — 맞추기 · 떼기로 고른 서식만 바꿉니다${keep ? ` · 계획이 사람에게 남긴 줄 ${nf(keep)}개는 그대로` : ""}`
      + `\n고르기를 바꾸려면 ★ · 대표와 다른 줄을 모두 맞추려면 레벨마다 「대표에 맞추기」(지금 대표와 다른 줄 ${nf(o.n)}개)`;
    if (!todo.levels.length) { const c = el("span", "olm-chip olm-tm-plan", "★ 계획: 바꿀 줄 없음"); c.title = why; box.append(c); return box; }
    const what = [todo.n || !todo.reps ? `${nf(todo.n)}줄` : "", todo.moved ? `떼기 ${nf(todo.moved)}` : "", todo.reps ? `대표 ${nf(todo.reps)}` : ""].filter(Boolean).join(" · "); // 대표만 바꾸는 계획(맞출 줄 0 · 대표 변경 n — tpl_agent.js tpaTodo 의 reps)도 할 일
    box.append(hBtn(`계획대로 맞추기(${what})`, () => olmMatchPlan(id),
      { title: `${why}\n한 번에(「실행 취소」 한 번으로 되돌림)`, cls: "btn sm olm-btn olm-tm-btn olm-tm-plan" }));
    return box;
  }
  if (!o.n) return box;
  const old = olmFresh() && OLM.plans ? OLM.plans[String(id)] : null, stale = !!(old && old.plan && old.state === "stale"); // 받은 뒤 문서가 바뀐 ★ 계획 — 계획대로는 못 맞춘다(서버 409)
  box.append(hBtn(`대표 맞추기(${nf(o.n)}줄)`, () => olmMatchTpl(id),
    { title: `T${t.no} 의 레벨 ${o.levels}개에서 대표와 서식이 다른 줄 ${nf(o.n)}개를 레벨마다 그 대표 모양으로 — 한 번에(「실행 취소」 한 번으로 되돌림)\n무엇이 다른지는 옆의 「다른 서식 보기」`
      + (t.comp ? `\n종속 템플릿의 줄만 맞춥니다 — 다른 자리의 T${t.comp.childNo} · T${t.comp.parentNo} 줄은 그대로`
        : t.vari ? `\n서식 종속 템플릿의 줄만 맞춥니다 — T${t.vari.ofNo} 의 줄은 그대로` : "\n레벨마다 따로 하려면 펼쳐서 「대표에 맞추기」")
      + (stale ? "\n★ 서식 정리 계획은 받은 뒤 문서가 바뀌어 옛것입니다 — 계획대로 맞추려면 「★ 계획 옛것」 을 눌러 다시 받으세요" : ""), cls: "btn sm olm-btn olm-tm-btn" }));
  if (stale && typeof tplAgentOpen === "function") { // 옛 계획이 있다는 것을 보인다 — 누르면 ★ 열(계획 다시 받기)
    box.append(hBtn("★ 계획 옛것", () => tplAgentOpen(id), { cls: "olm-chip olm-tm-stale",
      title: `★ 서식 정리 계획(${fmtWhen(old.at)})은 그 뒤 문서가 바뀌어 옛것입니다 — 계획대로 맞출 수 없습니다(옆 단추는 대표와 다른 줄을 모두 맞춤)\n누르면 ★ 열 — 계획을 다시 받으면 이 자리가 「계획대로 맞추기」 가 됩니다` }));
  }
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
  toast(`T${t ? t.no : id} 줄 ${nf(olmFit(r))}개를 레벨마다 대표 모양으로 맞췄습니다(레벨 ${(r.levels || []).length}개)${olmPut(r)} — 「실행 취소」 한 번으로 되돌립니다`);
}
async function olmMatchPlan(id) { // 「계획대로 맞추기」 — ★ 열의 「적용」 과 같은 몸(에이전트가 고른 그대로)
  const P = olmTplPlan(id);
  if (!P) { toast("쓸 계획이 없습니다 — 문서가 바뀌었거나 이미 반영했습니다. ★ 에서 계획을 다시 받으세요", true); olmLoad(true).then(() => olmRefresh()); return; }
  const todo = tpaTodoOf(P);
  if (!todo.levels.length) return;
  const r = await olmApplyTpl(P.tpl, { rev: state.serverRev, by: "agent", plan: P.at, levels: todo.levels }); // plan = 이 계획의 표시(at — tpl_agent.js tpaApply 와 같은 몸)
  if (!r) {
    if (structOp.lastError && structOp.lastError.status === 409) toast("계획을 받은 뒤 문서가 바뀌었습니다 — ★ 에서 계획을 다시 받으세요", true);
    return;
  }
  const n = olmFit(r), made = (r.splits || []).map((x) => `T${x.no}`);
  toast(`★ 계획대로 ${[n ? `T${P.no} 줄 ${nf(n)}개를 맞췄습니다` : "", made.length ? `서식 종속 템플릿 ${made.join(" · ")} 를 만들었습니다` : "", r.reps ? `대표 ${nf(r.reps)}개를 바꿨습니다` : ""].filter(Boolean).join(" · ") || ((r.placed || []).length ? "자리를 맞췄습니다" : (r.left || []).length ? "모양을 맞췄습니다" : "바꾼 것이 없습니다")}${olmPut(r)} — 「실행 취소」 한 번으로 되돌립니다`);
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
  const items = [], tries = [];
  for (const L of olmPicLevels(t)) {
    const os = t.slots[String(L)], v = olmSlotData(id, L), repG = v ? v.groups.find((x) => x.rep) || v.groups[0] : null;
    const c = v ? olmTryOf(id, L, v) : null, g = c || repG, raw = g && g.raw ? g.raw : {}; // 대표 미리보기 중인 레벨은 끌어 놓은 갈래의 서식으로
    if (c) tries.push(L);
    const letter = oneLine(os.letter || (t.chain || [])[L - 1] || "");
    let at = os.at && os.at.letterMm != null ? os.at.letterMm : raw.line1Mm || 0;
    if (c && os.at && os.at.letterMm != null && repG && repG.raw) at = Math.max(0, at + ((raw.line1Mm || 0) - (repG.raw.line1Mm || 0))); // 레터 자리 = 대표 자리 + 앞 여백 차(앞 공백 차는 안 셈)
    items.push({ level: L, letter, marker: { mode: "literal", literal: letter }, sample: "견본 글입니다",
      format: { font: raw.font, sizePt: raw.sizePt, bold: !!raw.bold, italic: !!raw.italic, underline: !!raw.underline, color: raw.color, spacingPct: raw.spacingPct,
        indentLeftMm: at, firstLineMm: 0 } });
  }
  return items.length ? { items, tries } : null;
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
  box.classList.toggle("try", !!(view.tries && view.tries.length)); // 대표 미리보기 중인 레벨이 있으면 점선 테
  pic.title = `개요 레벨 그림 — 레벨마다 그 레벨 대표 줄의 레터 · 글꼴·크기·굵기 · 들여쓰기(견본 글)${view.tries && view.tries.length ? `\n${view.tries.map((L) => `L${L}`).join(" · ")} 은 대표 미리보기로 끌어 놓은 서식` : ""}\n${view.items.map((it) => `L${it.level} 「${it.letter}」 ${it.format.font || ""} ${it.format.sizePt || ""}pt${it.format.bold ? " 굵게" : ""} · 레터 ${Math.round((it.format.indentLeftMm || 0) * 10) / 10}mm`).join("\n")}`;
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
      msg: (r) => { const s = r.split || {}; return s.added ? `T${t ? t.no : id} L${L} 의 ${nf(s.lines)}줄을 T${s.no} 로 옮겼습니다 — 그 템플릿에서 「대표에 맞추기」 로 맞출 수 있습니다(「실행 취소」 로 되돌림)`
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
  b.title = ok ? "템플릿 관계 — 문서의 개요 템플릿 · 레벨마다 쓰인 서식과 대표 · 대표에 맞추기 · 하위로 넣기(문서 옆 열 — 다시 누르면 닫힘)"
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
