"use strict";
/* 다른 서식 보기(spec_hwpx_웹편집 ② §8-2 「다른 서식 보기」 — 2026-11-16 사용자 "템플릿 내에서 다른 서식을 템플릿 서식으로 조정하기 기능 넣어주고, 다른 서식 보기 버튼도 넣어줘" → "대표 맞추기.. 로 하면 되겠네").
   「템플릿 관계」 열·「템플릿」 탭의 템플릿 줄 머리에 **「다른 서식 보기(n가지)」**(다른 서식이 없어도 보인다 — 흐린 점선 「다른 서식 보기」: 누르면 「없음」 과 레벨마다 줄 수) —
   누르면 그 템플릿의 개요 레벨 그림 바로 아래에 한 묶음이 펼쳐진다(팝업 아님 — design.md §2):
   · 서식이 한 가지인 레벨은 한 줄 「L1 「□」 서식 1가지 — 모두 같음 · 19줄」.
   · 대표와 다른 서식 갈래가 있는 레벨마다 「L2 「o」 · 다른 서식 2가지 · 11줄」 + 「문서에서 보기」(그 레벨의 줄만 또렷이 — fmt_focus.js tplFocusOn: 대표와 다른 줄에 「≠ …」 표) + 「이 레벨 맞추기(m줄)」,
     그 아래 대표 줄 「대표 ×8 견본 글」 과 다른 서식마다 「다름 ×3 견본 글(그 서식 그대로 — 누르면 문서의 그 줄) · 맞추기 · 이름: 지금 값 → 대표 값 · 줄 목록」.
   · 맞추기는 레벨 줄의 「대표에 맞추기」·「이 갈래만 맞추기」 와 같은 몸(outline_match.js olmMatch — 같은 끝점 · 실행 취소 1). 템플릿의 모든 레벨을 한 번에 맞추는 것은 템플릿 줄의 「대표 맞추기(n줄)」(olmTplMatch).
   · 대표가 없는 레벨(대표 줄을 지움)은 갈래만 보이고 맞추기는 없다(레벨 줄에서 대표를 정한 뒤).
   새 자료·새 끝점 없음 — 서식 갈래(GET …/outline/formats — outline_match.js olmLoad 가 기억한 OLM.data)만 읽는다. 문서도 서버도 이 보기만으로는 안 바뀐다.
   훅: outline_match.js olmTplTools 가 olmOddBtn(id) 를, olmRedraw 가 olmOddRefresh() 를, app.js tplTreeDraw 의 make() 가 그림 다음에 olmOddBox(id) 를 부른다. outline_match.js 다음에 읽힌다
   (OLM·olmTpl·olmFresh·olmNeed·olmMatch·olmDiffText·olmDiffTitle·olmText·olmKey · app.js el·hBtn·nf·short·headsParaLink·headsGo · outline_preview.js olpSample · fmt_focus.js tplFocusOn 을 쓴다). */
const OLO = { open: new Set(), epoch: -1 }; // open = 펼친 템플릿 id(문서마다 — 다른 문서를 열면 비운다)

function oloOpen() { if (OLO.epoch !== state.epoch) { OLO.open.clear(); OLO.epoch = state.epoch; } return OLO.open; }

function oloLevels(id) { // 이 템플릿의 줄이 있는 레벨 모두(레벨 순) → [{L, v, rep(대표 갈래 | null), others[대표가 아닌 갈래 — 갈래가 하나면 빈 목록 = 모두 같음]}] | null(갈래 자료가 지금 것이 아님)
  if (typeof olmFresh !== "function" || !olmFresh()) return null;
  const slots = OLM.data[String(id)] || {}, out = [];
  for (const L of Object.keys(slots).map(Number).sort((a, b) => a - b)) {
    const v = slots[String(L)];
    if (!v || !v.groups || !v.groups.length) continue;
    const rep = v.groups.find((g) => g.rep) || null;
    out.push({ L, v, rep, others: v.groups.length > 1 ? v.groups.filter((g) => g !== rep) : [] });
  }
  return out;
}
const oloSum = (lv) => ({ levels: lv.filter((x) => x.others.length).length, kinds: lv.reduce((a, x) => a + x.others.length, 0), lines: lv.reduce((a, x) => a + x.others.reduce((b, g) => b + g.count, 0), 0) });

// 템플릿 줄의 「다른 서식 보기(n가지)」 자리 — 줄이 있는 템플릿이면 다른 서식이 없어도 보인다(흐린 점선 「다른 서식 보기」 — 누르면 「없음」 과 레벨마다 줄 수:
// 「하위로」 와 같은 규칙 — 2026-11-15 사용자 「… 보이질 않아」). 갈래를 아직 안 읽었으면 빈 자리(읽은 뒤 olmOddRefresh 가 채운다)
function olmOddBtn(id) {
  const box = el("span", "olm-od");
  box.dataset.tpl = id;
  const t = olmTpl(id), lv = t ? oloLevels(id) : null;
  if (!lv) { if (t) olmNeed(); return box; }
  if (!lv.length) return box; // 줄이 없는 템플릿
  const s = oloSum(lv);
  const b = hBtn(s.kinds ? `다른 서식 보기(${nf(s.kinds)}가지)` : "다른 서식 보기", () => oloToggle(id), { cls: `btn sm olm-btn olm-odd-btn${s.kinds ? "" : " none"}`,
    title: s.kinds ? `T${t.no} 에서 레벨의 대표와 서식이 다른 줄 — 레벨 ${nf(s.levels)}개 · 서식 ${nf(s.kinds)}가지 · ${nf(s.lines)}줄\n누르면 아래에 레벨마다 대표와 다른 서식(견본 글 · 지금 값 → 대표 값 · 줄 목록)을 펴 보입니다 — 문서는 안 바뀝니다\n맞추기: 서식마다 「맞추기」 · 레벨마다 「이 레벨 맞추기」 · 모두 한 번에는 옆의 「대표 맞추기」`
      : `T${t.no} 에는 대표와 서식이 다른 줄이 없습니다 — 레벨마다 모두 대표와 같습니다\n누르면 레벨마다 줄 수를 보입니다(다른 서식이 생기면 여기에 「지금 값 → 대표 값」 과 맞추기가 보입니다)` });
  b.setAttribute("aria-expanded", String(oloOpen().has(String(id))));
  box.append(b);
  return box;
}

function oloToggle(id) { // 펼치기·접기 — 같은 템플릿 줄이 「템플릿」 탭과 「템플릿 관계」 열 두 곳에 있을 수 있다(둘 다)
  const set = oloOpen(), key = String(id), on = !set.has(key);
  if (on) set.add(key); else set.delete(key);
  for (const b of document.querySelectorAll(".tpl-tree .olm-od > .olm-odd-btn")) {
    if (b.parentNode.dataset.tpl !== key) continue;
    b.setAttribute("aria-expanded", String(on));
    const li = b.closest("li.trel-node"); // 되돌이 줄(그림이 없는 줄)에는 자리가 없다 — 그 줄 머리 바로 아래에 만든다
    if (on && li && !li.querySelector(":scope > .olm-odd")) b.closest(".trel-row").after(olmOddBox(id));
  }
  for (const box of document.querySelectorAll(".tpl-tree .olm-odd")) if (box.dataset.tpl === key) olmOddFill(box);
}

function olmOddBox(id) { // 템플릿 줄의 개요 레벨 그림 바로 아래 자리(app.js make) — 접혀 있으면 빈 채로 숨김
  const box = el("div", "olm-odd");
  box.dataset.tpl = id;
  olmOddFill(box);
  return box;
}

function olmOddRefresh() { // olmRedraw 끝 — 서식 갈래·대표가 바뀐 뒤 단추의 수와 펼친 묶음을 새 갈래로
  for (const old of document.querySelectorAll(".tpl-tree .olm-od")) old.replaceWith(olmOddBtn(old.dataset.tpl));
  for (const box of document.querySelectorAll(".tpl-tree .olm-odd")) olmOddFill(box);
}

function olmOddFill(box) { // 펼친 묶음을 (다시) 그린다 — 접혔으면 숨긴다. 다른 서식이 없으면 「없음」 과 레벨마다 줄 수(맞춘 뒤에도 펼친 채 — 실행 취소로 다른 서식이 돌아오면 그 줄들이 다시 보인다)
  const id = box.dataset.tpl, t = olmTpl(id);
  if (!t || !oloOpen().has(String(id))) { box.hidden = true; box.replaceChildren(); return; }
  const lv = oloLevels(id);
  if (!lv) { // 갈래를 아직 안 읽음 — 읽은 뒤 olmRedraw → olmOddRefresh
    box.hidden = false;
    if (!box.firstChild) box.append(el("p", "hnote", "서식 갈래 읽는 중…"));
    olmNeed();
    return;
  }
  if (!lv.length) { box.hidden = true; box.replaceChildren(); return; } // 줄이 없는 템플릿
  const s = oloSum(lv);
  box.hidden = false;
  box.classList.toggle("none", !s.kinds);
  const head = el("div", "olo-head");
  head.append(el("b", null, s.kinds ? "대표와 다른 서식" : "대표와 다른 서식 없음"),
    el("span", "muted", s.kinds ? `레벨 ${nf(s.levels)}개 · ${nf(s.kinds)}가지 · ${nf(s.lines)}줄` : `T${t.no} 의 줄은 레벨마다 모두 대표와 서식이 같습니다`),
    hBtn("접기", () => oloToggle(id), { title: "이 묶음을 접습니다(템플릿 줄의 「다른 서식 보기」 를 다시 눌러도 됨)", cls: "btn sm olm-btn olo-close" }));
  const ul = el("ul", "olo-levels");
  for (const x of lv) ul.append(x.others.length ? oloLevel(id, t, x) : oloSame(t, x));
  box.replaceChildren(head, ul);
}

function oloLetter(t, L) { const os = t.slots ? t.slots[String(L)] : null; return os && os.table ? "표 제목" : short((os && os.letter) || (t.chain || [])[L - 1] || "?", 14); }

function oloSame(t, { L, v }) { // 서식이 한 가지인 레벨 — 한 줄 「L1 「□」 서식 1가지 — 모두 같음 · 19줄」
  const li = el("li", "olo-same");
  li.dataset.level = L;
  li.append(el("b", null, `L${L}`), el("span", "olo-letter", `「${oloLetter(t, L)}」`), el("span", "muted", `서식 1가지 — 모두 같음 · ${nf(v.total)}줄`));
  return li;
}

function oloLevel(id, t, { L, v, rep, others }) { // 레벨 한 묶음 — 머리(레벨 · 레터 · 수 · 문서에서 보기 · 이 레벨 맞추기) + 대표 줄 + 다른 서식 줄들
  const letter = oloLetter(t, L);
  const lines = others.reduce((a, g) => a + g.count, 0);
  const li = el("li", "olo-lv");
  li.dataset.level = L;
  const head = el("div", "olo-lh");
  head.append(el("b", null, `L${L}`), el("span", "olo-letter", `「${letter}」`), el("span", "olm-sum warn", `다른 서식 ${nf(others.length)}가지 · ${nf(lines)}줄`));
  const first = others[0] && others[0].paras[0];
  if (first && typeof tplFocusOn === "function") { // 문서에서 — 이 레벨의 줄만 또렷이 · 대표와 다른 줄에 「≠ …」 표(fmt_focus.js 「템플릿만 또렷이」)
    head.append(hBtn("문서에서 보기", () => { tplFocusOn({ tpl: String(id), level: L, no: t.no, para: first, focus: olmKey(id) }); headsGo(first); },
      { title: `문서에서 T${t.no} L${L} 의 줄만 또렷이 보이고(나머지는 흐리게) 대표와 다른 줄마다 쪽 오른쪽 여백에 「≠ 무엇」 표를 답니다 — 첫 다른 줄로 갑니다\n켜진 동안 휠을 굴리면 다음·앞 자리로 · 끄기는 문서 이름 줄의 「끄기」`, cls: "btn sm olm-btn olo-see" }));
  }
  if (rep && v.others) {
    head.append(hBtn(`이 레벨 맞추기(${nf(v.others)}줄)`, () => olmMatch(id, L, v.others),
      { title: `T${t.no} L${L} 에서 대표와 서식이 다른 줄 ${nf(v.others)}개를 모두 대표 모양으로 — 「실행 취소」 로 되돌립니다(레벨 줄의 「대표에 맞추기」 와 같은 것)`, cls: "btn sm olm-btn olo-lgo" }));
  }
  li.append(head);
  if (rep) li.append(oloRow(id, L, t, rep, true));
  else li.append(el("p", "hnote warn olo-norep", "대표 없음 — 이 레벨에 대표 줄이 없어 견줄 서식이 없습니다. 템플릿을 펼쳐 이 레벨의 줄 하나를 「대표로」 정하면 다른 값과 맞추기가 보입니다."));
  for (const g of others) li.append(oloRow(id, L, t, g, false, !!rep));
  return li;
}

function oloSamp(g) { // 갈래의 견본 글을 그 갈래 서식으로(outline_preview.js olpSample — 누르면 문서의 그 줄 · 없으면 글만)
  return typeof olpSample === "function" ? olpSample(g) : headsParaLink(g.paras[0], olmText(g.paras[0]), 40);
}

function oloRow(id, L, t, g, isRep, canMatch = false) { // 서식 한 줄 — [대표 | 다름] ×수 · 견본 글(그 서식 그대로 — 누르면 문서의 그 줄) · 맞추기 · 대표와 다른 값 · 줄 목록
  const row = el("div", `olo-row${isRep ? " rep" : ""}`);
  row.dataset.key = g.key;
  row._paras = g.paras;
  const head = el("div", "olo-rh");
  head.append(el("span", `hb ${isRep ? "olm-badge" : "und"} olo-tag`, isRep ? "대표" : "다름"), el("span", "olm-n", `×${nf(g.count)}`), oloSamp(g));
  if (!isRep && canMatch) {
    head.append(hBtn("맞추기", () => olmMatch(id, L, g.count, [...g.paras]),
      { title: `이 서식의 줄 ${nf(g.count)}개만 T${t.no} L${L} 의 대표 모양으로 — 「실행 취소」 로 되돌립니다(갈래 줄의 「이 갈래만 맞추기」 와 같은 것)`, cls: "btn sm olm-btn olo-go" }));
  }
  row.append(head);
  if (!isRep && (g.diff || []).length) { // 「이름: 지금 값 → 대표 값」 — 값마다 이름표 · 화살표 = 맞추면 바뀌는 방향(outline_match.js olmDiffText)
    const d = el("div", "olm-diff", olmDiffText(g.diff, 6));
    d.title = olmDiffTitle(g.diff);
    row.append(d);
  }
  if (!isRep && g.count > 1) {
    const det = el("details", "olm-paras");
    det.append(el("summary", null, `줄 ${nf(g.count)}`));
    const list = el("div", "olm-plist");
    for (const pid of g.paras) list.append(headsParaLink(pid, olmText(pid), 30));
    if (g.more) list.append(el("span", "muted", `외 ${nf(g.more)}줄`));
    det.append(list);
    row.append(det);
  }
  return row;
}
