"use strict";
/* 개요 줄의 레터 고치기(spec_hwpx_웹편집 ② §8-12) — 고른 개요 줄의 **레터 글자를 누르면** 그 줄 아래에 뜨는 창(#olTune): 레터 · 레터 앞 빈칸 · 레터 뒤 빈칸 · 앞 여백을 고치고,
   그 고침을 어디까지 걸지(범위)를 눌러 고른 뒤 「적용」 한 번.
   2026-11-23 사용자 "문장을 선택하고 레더를 클릭할 수 있고 레터를 변경할 수 있도록 레터 옵션을 줘, 문자 숫자, 둥근숫자 포함해서, 그리고 앞 여백, 레터 뒤여백을 조절할 수 있게 해줘, 그리고 수정을 했잖아.
   그럼 이제 그 서식 전체를 변경할 수 있는 옵션을 제공해줘, . 되돌릴 수 있는 옵션도 주고, , 전체서식변경으로 할 수 있는 옵션 해당 문단/헤딩만 수정할 수 있는 옵션을 주고 선택할 수 있게 해줘, ,,
   T1L5 이였는데 여기서 변경된 템플릿을 추가할 수 있도록해줘 … 옵션을 클릭해서 선택할 수 있도록 UI를 고려해줘"(astra 협의).
   · 입구: ⓐ 커서가 이미 든(고른) 개요 줄의 레터 글자를 누름 — 첫 누름은 그냥 커서 · 레터 **글자 위**를 눌렀을 때만(그 옆을 누르면 전처럼 커서). 커서가 든 개요 줄의 레터에는 점선 밑줄(누를 수 있다는 표시 — CSS 하이라이트: 글은 안 바뀐다)
     ⓑ 문단의 오른쪽 단추 메뉴 「레터 고치기…」(app.js divContextMenu 가 oltCtxItems 를 부른다).
   · 창: 견본(지금 → 바꾼 뒤) · 레터(「레터 고르기 ▾」 → 기호 · 번호 · 직접 입력) · 자리(앞 여백 mm · 레터 앞 빈칸 · 레터 뒤 빈칸 — − / +) · 범위 카드 셋(「이 문단만 수정」 · 「T1 L6 서식 전체 변경」 · 「새 템플릿으로 추가 · T1L6a」)
     · 발(「되돌리기」 — 방금 이 창이 반영한 것 · 「적용」). 값이 바뀔 때마다 서버에 미리보기를 물어(POST …/outline/tune/preview) 카드마다 바뀔 줄 수 · 못 하는 까닭을 적는다 — 문서는 「적용」 전에는 안 바뀐다.
   · 적용 = POST …/outline/tune(structOp — 트랜잭션 하나 · 실행 취소 1) → 오버레이 요약을 다시 읽고(outlineLoad) 창은 열린 채 그 줄의 새 값으로. 되돌리기 = POST …/outline/tune/undo(문서 차례가 그대로일 때만).
   · 모달이 아니다(design.md §8) — 밖을 누르거나 Esc 로 닫힌다. 설명 글은 제목 옆 노트 아이콘에.
   app.js 다음에 읽힌다(state · heads · $ · el · api · toast · paraEl · outlineLine · isRooted · selOffsets · setCaret · pointAt · structOp · outlineLoad · applyDoc · flushAll · refreshToolbar · refreshSaveState · nf · hHelp(panel_help.js) 를 쓴다). */
const OLT = { box: null, st: null, down: null, hint: null, seq: 0 };
const OLT_SCOPES = ["line", "level", "split"];
const OLT_HELP = "고른 줄의 레터 · 레터 앞뒤 빈칸 · 앞 여백을 고칩니다.\n"
  + "· 앞 여백 = 첫 줄이 시작하는 자리(문단 모양으로 비운 것 · mm). 레터 앞 빈칸 · 레터 뒤 빈칸 = 친 빈칸 글자(칸 수). 2번째 줄은 글 시작에 맞춰집니다(그 레벨에 따로 정한 자리 규칙이 있으면 그것).\n"
  + "· 이 문단만 수정 — 이 줄만 고칩니다. 그 레벨의 다른 줄과 서식이 달라져 「다른 서식」 으로 남습니다. 레터가 다른 계열로 바뀌면(「-」 → 「▪」 · 「①」) 다른 템플릿이라 이 범위로는 못 합니다.\n"
  + "· 서식 전체 변경 — 이 줄을 그 레벨의 대표로 삼고 그 레벨의 줄을 모두 이 줄의 서식(레터 · 빈칸 · 여백 · 글꼴 · 정렬)으로 맞춥니다. 번호형 레터는 줄마다 제 번호, 기호였던 레벨을 번호로 바꾸면 같은 윗줄 아래 차례로 1부터. 표의 서식을 쓰는 표 안의 줄은 모양을 그대로 둡니다.\n"
  + "· 새 템플릿으로 추가 — 이 줄(값을 안 바꿨으면 서식이 같은 줄도)을 그 레벨에서 떼어 새 템플릿(「T1L6a」)으로 만듭니다. 아래 줄이 따라가고 원래 템플릿은 그대로입니다.\n"
  + "· 「적용」 한 번이 실행 취소 1개입니다 — 창의 「되돌리기」(바로 뒤에만)나 도구 줄 「↶ 실행 취소」.";

/* ---- 입구 ---- */
function oltLineOk(p) { // 레터를 고칠 수 있는 개요 줄인가(괄호 줄 · 표 제목 줄 제외 — 서버가 한 번 더 본다)
  if (!p || state.format === "docx" || !heads.outline) return null;
  const ol = outlineLine(p);
  return ol && ol.letter && !isRooted(ol.role) && ol.role !== "table" ? ol : null;
}
function oltLetterRange(p) { // 그 줄의 레터 글자 범위(Range) — 첫머리(빈칸 뒤)에 오버레이의 레터가 그대로 있을 때만
  const ol = oltLineOk(p);
  if (!ol) return null;
  const t = p.textContent || "", lead = t.length - t.trimStart().length;
  if (!t.startsWith(ol.letter, lead)) return null;
  const r = document.createRange();
  r.setStart(...pointAt(p, lead));
  r.setEnd(...pointAt(p, lead + ol.letter.length));
  return r;
}
function oltSelPara() { // 지금 커서 · 고른 범위가 든 문단(한 문단 안일 때만)
  const s = getSelection();
  if (!s || !s.rangeCount) return null;
  const n = s.anchorNode, f = s.focusNode;
  const a = n && (n.nodeType === 1 ? n : n.parentElement), b = f && (f.nodeType === 1 ? f : f.parentElement);
  const p = a && a.closest ? a.closest("#doc .para[data-id]") : null;
  return p && b && b.closest && b.closest(".para[data-id]") === p ? p : null;
}
function oltHint() { // 커서가 든 개요 줄의 레터에 점선 밑줄(누를 수 있다) — CSS 하이라이트(글 · 배치는 안 바뀐다). 못 쓰는 브라우저에서는 표시만 없다
  if (typeof Highlight !== "function" || !window.CSS || !CSS.highlights) return;
  const p = oltSelPara(), r = p && !state.busy ? oltLetterRange(p) : null;
  if (!r) { if (OLT.hint) { CSS.highlights.delete("nfm-olt-letter"); OLT.hint = null; } return; }
  OLT.hint = p.dataset.id;
  CSS.highlights.set("nfm-olt-letter", new Highlight(r));
}
function oltDown(e) { // 누르기 전에 커서가 있던 문단 · 창을 여는 중(자료를 기다리는 중)에 문서를 다시 누르면 그 열기는 버린다(뒤늦게 뜬 창이 초점을 가져가지 않게)
  if (!OLT.box) OLT.seq += 1;
  OLT.down = e.button === 0 ? (oltSelPara() || {}).dataset?.id || null : null;
}
function oltClick(e) { // 커서가 이미 있던 줄의 레터 글자 위를 한 번 누름 → 창
  if (e.button !== 0 || e.detail !== 1 || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || state.busy) return;
  const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
  const p = t && t.closest ? t.closest("#doc .para[data-id]") : null;
  if (!p || OLT.down !== p.dataset.id) return;
  const r = oltLetterRange(p);
  if (!r) return;
  const hit = [...r.getClientRects()].some((b) => e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom);
  if (hit) outlineTuneOpen(p);
}
function oltCtxItems(e) { // 문단의 오른쪽 단추 메뉴 — [구분선, [이름, 단축키, 실행, 못 씀]]
  const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
  const p = t && t.closest ? t.closest("#doc .para[data-id]") : null;
  return oltLineOk(p) ? [null, ["레터 고치기…", "", () => outlineTuneOpen(p), state.busy]] : [];
}

/* ---- 창 ---- */
async function outlineTuneOpen(p) {
  outlineTuneClose(false);
  const id = state.id, epoch = state.epoch, pid = p.dataset.id, caret = selOffsets(p), seq = ++OLT.seq;
  let d;
  try {
    await flushAll(); // 치던 글을 먼저 반영한다 — 창이 본 문서 차례(rev)가 「적용」 때의 것과 같게
    if (epoch !== state.epoch || seq !== OLT.seq) return;
    d = await api(`/api/docs/${id}/outline/tune/suggest`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: pid }) });
  } catch (e) { if (epoch === state.epoch && seq === OLT.seq) toast(e.status === 404 ? "「레터 고치기」 는 서버를 다시 켠 뒤에 쓸 수 있습니다(지금 서버에 그 기능이 아직 없습니다)" : e.message, true); return; }
  if (epoch !== state.epoch || seq !== OLT.seq || !paraEl(pid) || OLT.st) return;
  OLT.st = { epoch, doc: id, pid, caret, d, letter: null, exact: false, custom: "", lead: d.cur.lead, gap: d.cur.gap, front: d.cur.frontMm, scope: "line", pv: null, pvErr: "", stale: true, open: false, tab: d.numbered ? "numbers" : "symbols", done: null, timer: 0, gen: 0 };
  const box = OLT.box = el("div", "ol-tune");
  box.id = "olTune";
  box.tabIndex = -1;
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", `레터 고치기 — ${d.name}`);
  box.addEventListener("mousedown", (e) => { if (!e.target.closest("input, button")) e.preventDefault(); }); // 창 안 빈 곳을 눌러도 초점이 문서로 가지 않게
  document.body.append(box);
  oltDraw();
  oltPlace();
  box.focus({ preventScroll: true });
  document.addEventListener("mousedown", oltOutside, true);
  document.addEventListener("keydown", oltEsc, true); // 초점이 창 밖(문서를 다시 그린 뒤)이어도 Esc 로 닫힌다
  window.addEventListener("resize", oltPlace);
  $("scroller").addEventListener("scroll", oltPlace, { passive: true });
  oltAsk(0);
}
function outlineTuneClose(refocus) {
  const st = OLT.st, box = OLT.box;
  OLT.seq += 1;
  if (!box) return;
  clearTimeout(st.timer);
  OLT.box = OLT.st = null;
  document.removeEventListener("mousedown", oltOutside, true);
  document.removeEventListener("keydown", oltEsc, true);
  window.removeEventListener("resize", oltPlace);
  $("scroller").removeEventListener("scroll", oltPlace);
  box.remove();
  if (!refocus || st.epoch !== state.epoch) return;
  const p = paraEl(st.pid);
  if (!p) return;
  p.focus({ preventScroll: true });
  if (st.caret) setCaret(p, st.caret.start, st.caret.end);
}
const oltEsc = (e) => { if (e.key === "Escape" && OLT.box && !e.isComposing && !document.querySelector(".ctx-menu:not([hidden])")) { e.preventDefault(); e.stopPropagation(); outlineTuneClose(true); } };
const oltOutside = (e) => { if (OLT.box && !OLT.box.contains(e.target) && !e.target.closest(".panel-help-pop, #panelHelp")) outlineTuneClose(false); };
function oltPlace() { // 그 줄 바로 아래(자리가 없으면 위) — 창 안에 들게. 줄이 화면 밖으로 굴러가면 창도 따라간다(닫지 않는다 — 값을 고치던 중이다)
  const box = OLT.box, st = OLT.st;
  if (st && (st.doc !== state.id || st.epoch !== state.epoch)) { outlineTuneClose(false); return; } // 다른 문서를 열었다
  const p = st && paraEl(st.pid);
  if (!box || !p) return;
  const r = p.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
  const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
  const below = r.bottom + 6, top = below + h <= innerHeight - 8 ? below : Math.max(8, Math.min(r.top - h - 6, innerHeight - h - 8));
  box.style.left = `${Math.round(left)}px`;
  box.style.top = `${Math.round(Math.max(8, top))}px`;
}

const oltMm = (v) => (v == null ? "–" : (Math.round(v * 10) / 10).toFixed(1));
function oltNew() { // 창이 고른 값 가운데 지금 줄과 다른 것만 — 서버에 보낼 몸의 값 부분
  const st = OLT.st, c = st.d.cur, b = {};
  if (st.letter && st.letter !== c.letter) { b.letter = st.letter; if (st.exact) b.exact = true; }
  if (st.lead !== c.lead) b.lead = st.lead;
  if (st.gap !== c.gap) b.gap = st.gap;
  if (c.frontMm != null && st.front != null && Math.abs(st.front - c.frontMm) >= 0.05) b.frontMm = st.front;
  return b;
}
function oltShown() { // 견본 · 카드에 보일 새 레터(미리보기가 정한 것 — 번호형은 그 줄의 번호로) · 빈칸
  const st = OLT.st, sc = st.pv && st.pv[st.scope], n = (sc && sc.new) || (st.pv && st.pv.new); // 번호형은 범위마다 이 줄의 번호가 다르다 — 고른 범위의 것
  return { letter: (n && n.letter) || st.letter || st.d.cur.letter, lead: st.lead, gap: st.gap };
}

function oltAsk(ms = 160) { // 값이 바뀐 뒤 — 범위 셋의 미리보기를 다시 묻는다(문서는 안 바뀐다)
  const st = OLT.st;
  if (!st) return;
  if (st.doc !== state.id || st.epoch !== state.epoch) { outlineTuneClose(false); return; } // 다른 문서를 열었다
  clearTimeout(st.timer);
  const gen = ++st.gen;
  st.stale = true; // 새 답이 올 때까지 — 「적용」 을 끄고 카드를 흐리게(본 것과 다른 것을 반영하지 않는다)
  oltSync();
  st.timer = setTimeout(async () => {
    const id = state.id;
    try {
      const pv = await api(`/api/docs/${st.doc}/outline/tune/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: st.pid, ...oltNew() }) });
      if (OLT.st !== st || gen !== st.gen) return;
      st.pv = pv; st.pvErr = "";
      if (!pv[st.scope].ok) { const nx = (st.scope === "line" ? ["split", "level"] : ["line", "level", "split"]).find((k) => pv[k].ok); if (nx) st.scope = nx; } // 못 하는 범위를 고른 채 두지 않는다(레터가 달라지면 새 템플릿 쪽으로)
    } catch (e) {
      if (OLT.st !== st || gen !== st.gen) return;
      st.pv = null; st.pvErr = e.message;
    }
    st.stale = false;
    oltSync();
  }, ms);
}

function oltDraw() { // 뼈대를 한 번 그린다 — 값이 바뀌면 oltSync 가 견본 · 값 · 카드 · 발만 고친다(입력 칸을 다시 그리면 치던 글 · 초점이 끊긴다)
  const st = OLT.st, box = OLT.box, d = st.d;
  const btn = (text, title, fn, cls = "btn sm") => { const b = el("button", cls, text); b.type = "button"; if (title) b.title = title; b.onclick = fn; return b; };
  const head = el("div", "olt-head");
  const x = btn("×", "닫기(Esc)", () => outlineTuneClose(true), "olt-x");
  x.setAttribute("aria-label", "닫기");
  head.append(el("b", null, "레터 고치기"), el("span", "olt-sub", ` — ${d.name} 「${d.cur.letter}」${d.isRep ? " · 대표 줄" : ""}`), el("span", "olt-fill"), hHelp("레터 고치기 설명", OLT_HELP), x);
  const demo = el("div", "olt-demo");
  // 레터
  const lrow = el("div", "olt-row");
  const pick = btn("레터 고르기 ▾", "기호 · 번호 · 직접 입력에서 레터를 고릅니다", () => { st.open = !st.open; oltSync(); oltPlace(); }, "btn sm olt-pick");
  lrow.append(el("span", "olt-lab", "레터"), el("span", "olt-cur"), pick);
  const pal = el("div", "olt-pal");
  const seg = el("div", "olt-seg");
  seg.setAttribute("role", "tablist");
  for (const [k, name] of [["symbols", "기호"], ["numbers", "번호"], ["custom", "직접 입력"]]) {
    const b = btn(name, "", () => { st.tab = k; oltSync(); oltPlace(); if (k === "custom") box.querySelector(".olt-in").focus(); }, "olt-tab");
    b.dataset.tab = k;
    b.setAttribute("role", "tab");
    seg.append(b);
  }
  const grid = (k, list, note) => {
    const g = el("div", "olt-grid");
    g.dataset.tab = k;
    for (const lt of list) {
      const b = btn(lt, `레터 「${lt}」${note}`, () => { st.letter = lt; st.exact = false; oltAsk(); }, "olt-chip");
      b.dataset.letter = lt;
      g.append(b);
    }
    return g;
  };
  const cus = el("div", "olt-cus");
  cus.dataset.tab = "custom";
  const inp = el("input", "olt-in");
  inp.type = "text"; inp.value = st.custom || ""; inp.maxLength = d.limits.letter; inp.placeholder = "예: ◆ · (a) · 3."; inp.setAttribute("aria-label", "레터 직접 입력");
  inp.oninput = () => { st.custom = inp.value; const v = inp.value.trim(); st.letter = v || null; st.exact = !!v; oltAsk(300); };
  cus.append(inp, el("span", "olt-note", "적은 그대로 넣습니다"));
  pal.append(seg, grid("symbols", d.symbols, ""), grid("numbers", d.numbers, " — 번호형: 줄마다 제 번호 · 번호가 없던 줄은 같은 윗줄 아래 차례로"), cus);
  // 자리
  const pos = el("div", "olt-pos");
  const step = (key, label, title, by, unit, lo, hi) => {
    const c = el("div", "olt-step");
    c.dataset.key = key;
    const move = (dir) => { const v = Math.max(lo, Math.min(hi, Math.round(((st[key] ?? 0) + dir * by) * 10) / 10)); if (v !== st[key]) { st[key] = v; oltAsk(); } };
    const val = el("b", "olt-val");
    const ctl = el("span", "olt-ctl");
    ctl.append(btn("−", `${label} 줄이기`, () => move(-1), "btn sm olt-pm"), val, btn("+", `${label} 늘리기`, () => move(1), "btn sm olt-pm"));
    c.append(el("span", "olt-lab", label), ctl, el("span", "olt-was"));
    c.title = title;
    c.dataset.unit = unit;
    return c;
  };
  pos.append(step("front", "앞 여백", "앞 여백(mm) — 첫 줄이 시작하는 자리(문단 모양으로 비운 것). 0.5mm 씩", 0.5, "mm", 0, d.limits.front),
    step("lead", "레터 앞 빈칸", "레터 앞에 친 빈칸 글자 수", 1, "칸", 0, d.limits.lead),
    step("gap", "레터 뒤 빈칸", "레터와 글 사이에 친 빈칸 글자 수", 1, "칸", 0, d.limits.gap));
  // 범위
  const sc = el("div", "olt-scopes");
  sc.setAttribute("role", "radiogroup");
  sc.setAttribute("aria-label", "적용 범위");
  for (const k of OLT_SCOPES) {
    const b = el("button", "olt-card");
    b.type = "button";
    b.dataset.scope = k;
    b.setAttribute("role", "radio");
    b.append(el("span", "olt-dot"), el("span", "olt-ct"), el("span", "olt-cn"));
    b.onclick = () => { if (b.getAttribute("aria-disabled") === "true" || st.stale) return; st.scope = k; oltSync(); };
    sc.append(b);
  }
  const foot = el("div", "olt-foot");
  const undo = btn("되돌리기", "방금 이 창이 반영한 것을 되돌립니다(그 뒤에 문서를 고쳤으면 도구 줄 「↶ 실행 취소」)", () => oltUndo(), "btn sm olt-undo");
  const go = btn("적용", "고른 범위에 반영합니다 — 실행 취소 1개", () => oltApply(), "btn sm primary olt-go");
  foot.append(el("span", "olt-msg"), undo, go);
  box.replaceChildren(head, demo, lrow, pal, pos, el("div", "olt-sec", "적용 범위"), sc, foot);
  oltSync();
}

function oltLine(letter, lead, gap, leadCh, gapCh, text, frontMm, cls) { // 견본 한 줄 — 앞 여백(왼쪽 띄움) · 레터 앞 빈칸 · 레터 · 레터 뒤 빈칸 · 글
  const l = el("div", "olt-l" + (cls ? ` ${cls}` : ""));
  const pre = (t, c) => el("span", "olt-pre" + (c ? ` ${c}` : ""), t);
  l.style.paddingLeft = `${Math.min(120, Math.max(0, frontMm || 0) * 2.2)}px`; // 1mm ≈ 2.2px(창 폭에 맞춘 축척 — 견줘 보는 용도)
  l.append(pre(leadCh.repeat(lead), "ws"), pre(letter, "lt"), pre(gapCh.repeat(gap), "ws"), text || "글");
  return l;
}

function oltSync() {
  const st = OLT.st, box = OLT.box;
  if (!st || !box) return;
  const d = st.d, c = d.cur, pv = st.pv, nw = oltShown(), body = oltNew(), changed = Object.keys(body).length > 0;
  // 견본
  const demo = box.querySelector(".olt-demo");
  const row = (tag, line) => { const r = el("div", "olt-dr"); r.append(el("span", "olt-dt", tag), line); return r; };
  demo.replaceChildren(row("지금", oltLine(c.letter, c.lead, c.gap, d.leadCh, d.gapCh, d.text, c.frontMm, "was")), row("바꾼 뒤", oltLine(nw.letter, nw.lead, nw.gap, d.leadCh, d.gapCh, d.text, st.front, changed ? "now" : "was")));
  // 레터
  const cur = box.querySelector(".olt-cur");
  cur.replaceChildren(el("span", "olt-lt", c.letter), ...(nw.letter !== c.letter ? [el("span", "olt-arrow", " → "), el("span", "olt-lt new", nw.letter)] : []));
  cur.title = nw.letter !== c.letter ? `지금 「${c.letter}」 → 바꾼 뒤 「${nw.letter}」` : `지금 레터 「${c.letter}」`;
  box.querySelector(".olt-pick").setAttribute("aria-expanded", String(st.open));
  box.querySelector(".olt-pick").textContent = st.open ? "레터 고르기 ▴" : "레터 고르기 ▾";
  const pal = box.querySelector(".olt-pal");
  pal.hidden = !st.open;
  for (const b of pal.querySelectorAll(".olt-tab")) { const on = b.dataset.tab === st.tab; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); }
  for (const g of pal.querySelectorAll(".olt-grid, .olt-cus")) g.hidden = g.dataset.tab !== st.tab;
  for (const b of pal.querySelectorAll(".olt-chip")) b.classList.toggle("on", !st.exact && (st.letter || "") === b.dataset.letter);
  // 자리
  for (const s of box.querySelectorAll(".olt-step")) {
    const k = s.dataset.key, v = st[k], was = k === "front" ? c.frontMm : c[k], mm = k === "front";
    const off = mm && c.frontMm == null; // 못 재는 줄(접두에 탭 …) — 앞 여백은 못 고친다
    s.querySelector(".olt-val").textContent = off ? "–" : mm ? `${oltMm(v)}mm` : `${v}칸`;
    const diff = !off && (mm ? Math.abs(v - was) >= 0.05 : v !== was);
    s.classList.toggle("chg", diff);
    s.querySelector(".olt-was").textContent = diff ? `지금 ${mm ? `${oltMm(was)}mm` : `${was}칸`}` : "";
    for (const b of s.querySelectorAll(".olt-pm")) b.disabled = off;
  }
  // 범위 카드
  const text = {
    line: () => ["이 문단만 수정", pv && pv.line.ok ? "이 줄만 — 다른 줄은 그대로" : ""],
    level: () => {
      const v = pv && pv.level;
      if (!v || !v.ok) return [`${d.name} 서식 전체 변경`, ""];
      const parts = [`${nf(v.total)}줄 가운데 ${nf(v.change + (changed ? 1 : 0))}줄 바뀜`];
      if (v.same) parts.push(`이미 같음 ${nf(v.same)}`);
      if (v.own) parts.push(`표의 서식 ${nf(v.own)}줄은 ${v.ownLetter ? "레터만" : "그대로"}`);
      if (v.skip) parts.push(`그대로 둠 ${nf(v.skip)}`);
      if (v.letters.length) parts.push(v.letters.map(([a, b]) => `「${a}」→「${b}」`).join(" ") + (v.more ? " …" : ""));
      return [`${d.name} 서식 전체 변경`, `이 줄이 대표 · ${parts.join(" · ")}`];
    },
    split: () => {
      const v = pv && pv.split;
      if (!v || !v.ok) return ["새 템플릿으로 추가", ""];
      return [`새 템플릿으로 추가 · ${v.name}`, `${v.roots > 1 ? `서식이 같은 ${nf(v.roots)}줄` : "이 줄"}이 ${v.name} 의 L${d.level}${v.kids ? ` · 아래 ${nf(v.kids)}줄이 따라감` : ""} · ${d.name} 의 다른 줄은 그대로`];
    },
  };
  for (const b of box.querySelectorAll(".olt-card")) {
    const k = b.dataset.scope, v = pv && pv[k], ok = !!(v && v.ok), [t, n] = text[k]();
    b.querySelector(".olt-ct").textContent = t;
    const note = b.querySelector(".olt-cn");
    note.textContent = ok ? n : (v && v.why) || (st.pvErr || "확인하는 중…");
    b.title = `${t}\n${note.textContent}`;
    b.setAttribute("aria-disabled", String(!ok));
    b.classList.toggle("off", !ok);
    b.classList.toggle("on", ok && st.scope === k);
    b.setAttribute("aria-checked", String(ok && st.scope === k));
  }
  // 발
  box.dataset.stale = st.stale ? "1" : "";
  const can = !!(pv && pv[st.scope] && pv[st.scope].ok) && !state.busy && !st.stale;
  const go = box.querySelector(".olt-go");
  go.disabled = !can;
  go.textContent = pv && pv.level && pv.level.ok && st.scope === "level" ? `적용(${nf(pv.level.change + (changed ? 1 : 0))}줄)` : "적용";
  const undo = box.querySelector(".olt-undo");
  undo.hidden = !st.done;
  undo.disabled = !st.done || state.busy;
  const msg = box.querySelector(".olt-msg");
  msg.textContent = st.done ? st.done.text : "";
  msg.title = msg.textContent;
}

/* ---- 반영 · 되돌리기 ---- */
async function oltReload(done, keep = false) { // 반영 · 되돌린 뒤 — 그 줄의 새 값으로 창을 다시(열린 채). 그 줄을 더는 고칠 수 없으면 닫는다. keep = 고른 값은 그대로(문서 차례만 새로 — 409 뒤)
  const st = OLT.st;
  if (!st) return;
  try {
    const d = await api(`/api/docs/${st.doc}/outline/tune/suggest`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: st.pid }) });
    if (OLT.st !== st) return;
    if (keep) Object.assign(st, { d, pv: null, pvErr: "" });
    else Object.assign(st, { d, letter: null, exact: false, custom: "", lead: d.cur.lead, gap: d.cur.gap, front: d.cur.frontMm, scope: "line", pv: null, pvErr: "", done: done || null });
    oltDraw();
    oltPlace();
    oltAsk(0);
  } catch (e) { outlineTuneClose(false); }
}

async function oltApply() {
  const st = OLT.st;
  if (!st || state.busy) return;
  if (st.doc !== state.id || st.epoch !== state.epoch) { outlineTuneClose(false); return; } // 다른 문서를 열었다 — 이 창은 그 문서의 것이 아니다
  const scope = st.scope, name = st.d.name, epoch = state.epoch;
  st.stale = true; // 반영하고 그 줄을 다시 읽을 때까지 — 카드 · 「적용」 을 잠근다(두 번 눌리지 않게)
  oltSync();
  await flushAll();
  if (epoch !== state.epoch) return;
  structOp.lastError = null;
  const r = await structOp("outline/tune", { id: st.pid, scope, rev: st.d.rev, run: st.d.run, ...oltNew() });
  if (epoch !== state.epoch) return;
  if (r) outlineLoad(true); // 템플릿의 대표 · 사슬 · 새 템플릿 — 여백 표시 · 템플릿 관계 트리(창을 그 사이 닫았어도 읽는다)
  if (OLT.st !== st) return;
  if (!r) { // 거절 — 까닭은 structOp 가 알렸다. 문서가 바뀐 것(409 — 치던 글 · 다른 탭)이면 고른 값은 그대로 두고 지금 문서의 차례로 다시 확인한다
    if (structOp.lastError && structOp.lastError.status === 409) await oltReload(null, true); else oltAsk(0);
    return;
  }
  const t = r.tune || {};
  const left = (t.left || []).length;
  const text = scope === "line" ? "이 문단만 고쳤습니다"
    : scope === "level" ? `${name} 줄 ${nf(t.changed)}개를 이 서식으로 바꿨습니다${t.kept ? ` · 표의 서식 ${nf(t.kept)}줄은 레터만` : ""}${left ? ` · 못 바꾼 줄 ${nf(left)}` : ""}`
      : `새 템플릿 ${t.split ? t.split.name : ""} — ${nf(t.split ? t.split.moved : 0)}줄`;
  toast(`${text} — 되돌리기는 창의 「되돌리기」 나 도구 줄 「↶ 실행 취소」`);
  if (left) toast(`형광펜 · 필드 · 변경 추적 표지 때문에 못 바꾼 줄이 ${nf(left)}개 있습니다 — 「템플릿 관계」 의 그 레벨에서 「다른 서식」 으로 보입니다`, true);
  await oltReload(t.undo ? { rev: r.rev, token: t.undo, text } : null);
}

async function oltUndo() {
  const st = OLT.st;
  if (!st || !st.done || state.busy) return;
  if (st.doc !== state.id || st.epoch !== state.epoch) { outlineTuneClose(false); return; } // 다른 문서를 열었다 — 그 문서의 편집을 되돌리지 않는다
  const epoch = state.epoch, id = st.doc, rev = st.done.rev, token = st.done.token;
  await flushAll();
  if (epoch !== state.epoch || OLT.st !== st) return;
  if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 먼저 다시 반영해야 합니다 — 「고친 문단」 탭", true); return; } // 되돌리면 문서를 다시 그린다 — 못 보낸 글을 덮지 않는다
  if (state.serverRev !== rev) { toast("그 뒤에 문서를 고쳐 이 창에서는 되돌릴 수 없습니다 — 도구 줄 「↶ 실행 취소」 를 쓰세요", true); st.done = null; oltSync(); return; }
  state.busy = true;
  st.stale = true;
  oltSync();
  refreshToolbar();
  try {
    const d = await api(`/api/docs/${id}/outline/tune/undo`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rev, token }) });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    state.structRev = state.localRev;
    applyDoc(d);
    outlineLoad(true);
    toast("되돌렸습니다");
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); }
  finally { if (epoch === state.epoch) { state.busy = false; refreshToolbar(); refreshSaveState(); } }
  if (OLT.st === st) { st.done = null; await oltReload(); }
  else if (OLT.st) { OLT.st.stale = false; oltSync(); }
}

if (typeof OUTLINE_OP === "object") OUTLINE_OP.tune = "레터 고치기(레터 · 빈칸 · 앞 여백 — 이 문단만 · 서식 전체 변경 · 새 템플릿으로 추가)"; // 「기록」 탭의 이름(app.js — 기록 kind outline · op tune)
document.addEventListener("selectionchange", oltHint);
$("doc").addEventListener("input", oltHint);
$("doc").addEventListener("mousedown", oltDown, true);
$("doc").addEventListener("click", oltClick);
