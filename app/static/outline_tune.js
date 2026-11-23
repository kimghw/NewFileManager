"use strict";
/* 개요 줄의 헤딩 고치기(spec_hwpx_웹편집 ② §8-12 — 2026-11-24 전의 이름 「레터 고치기」) — 고른 개요 줄의 **레터 글자를 누르면** 그 줄 아래에 뜨는 창(#olTune):
   레터 · 레터 앞 빈칸 · 레터 뒤 빈칸(칸 ↔ mm) · 앞 여백 · 2번째 줄(글 시작 · 레터 · 앞 여백)을 고치고, 그 고침을 어디까지 걸지(범위)를 눌러 고른 뒤 「적용」 한 번.
   2026-11-24 사용자 "레터 앞 빈칸 뒤 빈칸도 칸이랑 mm 둘다 할 수 있게 해줘, 그리고 새 탬플릿으로 추가 할떄 t1L6 부터 어디까지 알수 있고 선택할 수 있어야 함 … 대표도 새 탬플릿을 할 수 있지 …
   레토 코치기는 헤딩 레터 고치기로 하고 2번째 줄을 레터 앞에 맞추 ㄹ건지 레터 뒤의 첫번째 문자/글자에 맞출건지. 또는 여백으로 맞출건지를 선택할 수 있게 해줘 … 근데 새 템플릿으로 나누기 기능이 있네":
   셋째 범위 = 「새 템플릿으로 나누기」(라벨 메뉴의 나누기와 같은 길 — 대표 줄도) · 시작 레벨(이 줄 또는 윗줄의 레벨) · 끝 레벨 · 여기서만 | 그 레벨 모두.
   2026-11-23 사용자 "문장을 선택하고 레더를 클릭할 수 있고 레터를 변경할 수 있도록 레터 옵션을 줘, 문자 숫자, 둥근숫자 포함해서, 그리고 앞 여백, 레터 뒤여백을 조절할 수 있게 해줘, 그리고 수정을 했잖아.
   그럼 이제 그 서식 전체를 변경할 수 있는 옵션을 제공해줘, . 되돌릴 수 있는 옵션도 주고, , 전체서식변경으로 할 수 있는 옵션 해당 문단/헤딩만 수정할 수 있는 옵션을 주고 선택할 수 있게 해줘, ,,
   T1L5 이였는데 여기서 변경된 템플릿을 추가할 수 있도록해줘 … 옵션을 클릭해서 선택할 수 있도록 UI를 고려해줘"(astra 협의).
   · 입구: ⓐ 커서가 이미 든(고른) 개요 줄의 레터 글자를 누름 — 첫 누름은 그냥 커서 · 레터 **글자 위**를 눌렀을 때만(그 옆을 누르면 전처럼 커서). 커서가 든 개요 줄의 레터에는 점선 밑줄(누를 수 있다는 표시 — CSS 하이라이트: 글은 안 바뀐다)
     ⓑ 문단의 오른쪽 단추 메뉴 「헤딩 고치기…」(app.js divContextMenu 가 oltCtxItems 를 부른다) ⓒ 라벨의 오른쪽 단추 메뉴 「레벨 범위를 골라 나누기…」(outline_cut.js — 셋째 범위를 고른 채로).
   · 창: 견본(지금 → 바꾼 뒤 · 2번째 줄) · 레터(「레터 고르기 ▾」 → 기호 · 번호 · 직접 입력) · 자리(앞 여백 mm · 레터 앞 빈칸 · 레터 뒤 빈칸 — − / + · 값 칸에 적기 · 빈칸은 「칸 | mm」)
     · 2번째 줄(글 시작 · 레터 · 앞 여백) · 범위 카드 셋(「이 문단만 수정」 · 「T1 L6 서식 전체 변경」 · 「새 템플릿으로 나누기 · T1L6a」 — 고르면 아래에 레벨 범위 · 여기서만 | 모두)
     · 발(「되돌리기」 — 방금 이 창이 반영한 것 · 「적용」). 값이 바뀔 때마다 서버에 미리보기를 물어(POST …/outline/tune/preview) 카드마다 바뀔 줄 수 · 못 하는 까닭을 적는다 — 문서는 「적용」 전에는 안 바뀐다.
   · 적용 = POST …/outline/tune(structOp — 트랜잭션 하나 · 실행 취소 1) → 오버레이 요약을 다시 읽고(outlineLoad) 창은 열린 채 그 줄의 새 값으로. 되돌리기 = POST …/outline/tune/undo(문서 차례가 그대로일 때만).
   · 모달이 아니다(design.md §8) — 밖을 누르거나 Esc 로 닫힌다. 설명 글은 제목 옆 노트 아이콘에.
   app.js 다음에 읽힌다(state · heads · $ · el · api · toast · paraEl · outlineLine · isRooted · selOffsets · setCaret · pointAt · structOp · outlineLoad · applyDoc · flushAll · refreshToolbar · refreshSaveState · nf · hHelp(panel_help.js) 를 쓴다). */
const OLT = { box: null, st: null, down: null, hint: null, seq: 0 };
const OLT_SCOPES = ["line", "level", "split"];
const OLT_L2 = [["text", "글 시작", "레터 뒤 첫 글자"], ["letter", "레터", "레터 앞"], ["front", "앞 여백", "첫 줄 시작"]]; // 2번째 줄이 시작하는 자리 [규칙, 이름, 풀이]
const OLT_RULE = { mm: "직접", keep: "문단 서식 그대로" }; // 「자리 수정」(outline_format.js)으로 그 레벨에 건 다른 규칙
const OLT_HELP = "고른 헤딩 줄의 레터 · 레터 앞뒤 빈칸 · 앞 여백 · 2번째 줄을 고칩니다.\n"
  + "· 앞 여백 = 첫 줄이 시작하는 자리(문단 모양으로 비운 것 · mm). 레터 앞 빈칸 · 레터 뒤 빈칸 = 친 빈칸 글자 — 「칸 | mm」 로 단위를 바꿉니다. 빈칸은 글자라 칸 단위로만 바뀌어, mm 를 적으면 가장 가까운 칸 수로 맞춥니다(정확한 자리는 앞 여백으로).\n"
  + "· 2번째 줄 = 글이 넘어갈 때 둘째 줄부터가 시작하는 자리 — 「글 시작」(레터 뒤 첫 글자에 · 기본) · 「레터」(레터 앞에) · 「앞 여백」(첫 줄과 같은 자리 · 내어쓰기 없음). 「이 문단만」 은 이 줄에만, 넓히면 그 레벨의 규칙이 됩니다.\n"
  + "· 이 문단만 수정 — 이 줄만 고칩니다. 그 레벨의 다른 줄과 서식이 달라져 「다른 서식」 으로 남습니다. 레터가 다른 계열로 바뀌면(「-」 → 「▪」 · 「①」) 다른 템플릿이라 이 범위로는 못 합니다.\n"
  + "· 서식 전체 변경 — 이 줄을 그 레벨의 대표로 삼고 그 레벨의 줄을 모두 이 줄의 서식(레터 · 빈칸 · 여백 · 2번째 줄 · 글꼴 · 정렬)으로 맞춥니다. 번호형 레터는 줄마다 제 번호, 기호였던 레벨을 번호로 바꾸면 같은 윗줄 아래 차례로 1부터. 표의 서식을 쓰는 표 안의 줄은 모양을 그대로 둡니다.\n"
  + "· 새 템플릿으로 나누기 — 이 줄(대표 줄이어도)부터 새 템플릿(「T1L6a」)으로 나눕니다(라벨의 오른쪽 단추 메뉴 「나누기」 와 같은 기능). 고르면 아래에서 레벨 범위를 정합니다 — "
  + "「부터」 = 이 줄의 레벨이나 윗줄의 레벨(윗줄을 고르면 그 윗줄과 그 아래가 함께) · 「까지」 = 새 템플릿이 가질 마지막 레벨(그보다 깊은 아래 줄은 원래 템플릿에 남음) · 「여기서만」(이 줄과 아래) | 「모두」(그 레벨 줄 전부). "
  + "값을 바꿨으면 새 템플릿의 이 레벨이 이 서식이 됩니다. 원래 템플릿은 그대로이고 「합치기」 로 되돌립니다.\n"
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
  return oltLineOk(p) ? [null, ["헤딩 고치기…", "", () => outlineTuneOpen(p), state.busy]] : [];
}

/* ---- 창 ---- */
async function outlineTuneOpen(p, opt = {}) { // opt.scope = 처음 고른 범위(라벨 메뉴 「레벨 범위를 골라 나누기…」 = "split")
  outlineTuneClose(false);
  const id = state.id, epoch = state.epoch, pid = p.dataset.id, caret = selOffsets(p), seq = ++OLT.seq;
  let d;
  try {
    await flushAll(); // 치던 글을 먼저 반영한다 — 창이 본 문서 차례(rev)가 「적용」 때의 것과 같게
    if (epoch !== state.epoch || seq !== OLT.seq) return;
    d = await api(`/api/docs/${id}/outline/tune/suggest`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: pid }) });
  } catch (e) { if (epoch === state.epoch && seq === OLT.seq) toast(e.status === 404 ? "「헤딩 고치기」 는 서버를 다시 켠 뒤에 쓸 수 있습니다(지금 서버에 그 기능이 아직 없습니다)" : e.message, true); return; }
  if (epoch !== state.epoch || seq !== OLT.seq || !paraEl(pid) || OLT.st) return;
  OLT.st = { epoch, doc: id, pid, caret, d, ...oltFresh(d), scope: opt.scope === "split" ? "split" : "line", pin: opt.scope === "split", unit: { lead: "칸", gap: "칸" }, pv: null, pvErr: "", stale: true, open: false, tab: d.numbered ? "numbers" : "symbols", done: null, timer: 0, gen: 0 };
  const box = OLT.box = el("div", "ol-tune");
  box.id = "olTune";
  box.tabIndex = -1;
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", `헤딩 고치기 — ${d.name}`);
  box.addEventListener("mousedown", (e) => { if (!e.target.closest("input, button, select")) e.preventDefault(); }); // 창 안 빈 곳을 눌러도 초점이 문서로 가지 않게
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
function oltFresh(d) { // 창의 처음 값(그 줄의 지금 값) — 열 때 · 반영한 뒤
  return { letter: null, exact: false, custom: "", lead: d.cur.lead, gap: d.cur.gap, front: d.cur.frontMm, l2: null, start: d.level, upto: null, cut: "here" };
}
function oltBlankMm(key, n) { // 빈칸 n칸의 폭(mm) — 줄이면 앞에서부터 남고 늘리면 끝에 그 조각의 마지막 빈칸 글자(서버 outline_tune._resize · widths). 못 재면 null
  const w = (OLT.st.d.widths || {})[key], add = (OLT.st.d.widths || {})[`${key}Add`];
  if (!w || w.some((v) => v == null) || (n > w.length && add == null)) return null;
  const s = w.slice(0, n).reduce((a, b) => a + b, 0) + Math.max(0, n - w.length) * (add || 0);
  return Math.round(s * 100) / 100;
}
function oltBlankOf(key, mm) { // mm 에 가장 가까운 칸 수(0~한도)
  const hi = OLT.st.d.limits[key];
  let best = 0, gap = Infinity;
  for (let n = 0; n <= hi; n += 1) { const v = oltBlankMm(key, n); if (v != null && Math.abs(v - mm) < gap) { gap = Math.abs(v - mm); best = n; } }
  return best;
}
function oltL2Dflt() { // 2번째 줄 — 고르지 않았을 때 반영되는 규칙(이 문단만 = 이 줄에만 건 규칙 · 그 밖 = 그 레벨의 규칙)
  const st = OLT.st, d = st.d;
  return (st.scope === "line" && d.own) || d.rule.line2;
}
function oltNew() { // 창이 고른 값 가운데 지금 줄과 다른 것만 — 서버에 보낼 몸의 값 부분
  const st = OLT.st, c = st.d.cur, b = {};
  if (st.letter && st.letter !== c.letter) { b.letter = st.letter; if (st.exact) b.exact = true; }
  if (st.lead !== c.lead) b.lead = st.lead;
  if (st.gap !== c.gap) b.gap = st.gap;
  if (c.frontMm != null && st.front != null && Math.abs(st.front - c.frontMm) >= 0.05) b.frontMm = st.front;
  if (st.l2) b.line2 = st.l2;
  return b;
}
function oltSplitArgs() { // 새 템플릿으로 나누기의 범위 — 시작 · 끝 레벨 · 여기서만 | 모두
  const st = OLT.st;
  return { start: st.start, ...(st.upto != null ? { upto: st.upto } : {}), cut: st.cut };
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
      const pv = await api(`/api/docs/${st.doc}/outline/tune/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: st.pid, ...oltNew(), ...oltSplitArgs() }) });
      if (OLT.st !== st || gen !== st.gen) return;
      st.pv = pv; st.pvErr = "";
      // 못 하는 범위를 고른 채 두지 않는다(레터가 달라지면 새 템플릿 쪽으로) — 나누기의 레벨 범위를 고르던 중이면(pin) 그대로 두고 까닭을 보인다.
      // 나누기는 값을 안 바꿔도 되는 범위라(자리로 나눔) 값을 바꾸지 않았으면 저절로 고르지 않는다 — 창을 열자마자 「적용」 이 나누기가 되지 않게(사람이 카드를 눌러 고른다)
      if (st.scope === "split" && !st.pin && !pv.changes) st.scope = "line";
      else if (!pv[st.scope].ok && !(st.scope === "split" && st.pin)) { const nx = (st.scope === "line" ? ["split", "level"] : ["line", "level", "split"]).find((k) => pv[k].ok && (k !== "split" || pv.changes)); if (nx) st.scope = nx; }
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
  head.append(el("b", null, "헤딩 고치기"), el("span", "olt-sub", ` — ${d.name} 「${d.cur.letter}」${d.isRep ? " · 대표 줄" : ""}`), el("span", "olt-fill"), hHelp("헤딩 고치기 설명", OLT_HELP), x);
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
  // 자리 — 값 칸에 바로 적을 수도 있다(Enter · 칸을 떠나면). 빈칸은 「칸 | mm」 단위(mm 는 가장 가까운 칸 수로 — 빈칸은 글자라 칸 단위로만 바뀐다)
  const pos = el("div", "olt-pos");
  const step = (key, label, title, lo, hi) => {
    const c = el("div", "olt-step");
    c.dataset.key = key;
    const blank = key !== "front";
    const mmNow = () => blank && st.unit[key] === "mm";
    const move = (dir) => {
      const v = blank ? Math.max(lo, Math.min(hi, st[key] + dir)) : Math.max(lo, Math.min(hi, Math.round(((st[key] ?? 0) + dir * 0.5) * 10) / 10));
      if (v !== st[key]) { st[key] = v; oltAsk(); } else oltSync();
    };
    const val = el("input", "olt-val");
    val.type = "text"; val.inputMode = "decimal"; val.autocomplete = "off"; val.setAttribute("aria-label", label);
    const put = () => { // 적은 값 → 칸 수 · mm
      const n = parseFloat(String(val.value).replace(/[^0-9.]/g, ""));
      if (!Number.isFinite(n)) { oltSync(); return; }
      const v = !blank ? Math.max(lo, Math.min(hi, Math.round(n * 10) / 10)) : mmNow() ? oltBlankOf(key, n) : Math.max(lo, Math.min(hi, Math.round(n)));
      if (v !== st[key]) { st[key] = v; oltAsk(); } else oltSync();
    };
    val.onchange = put;
    val.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); put(); } else if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); move(e.key === "ArrowUp" ? 1 : -1); } };
    const ctl = el("span", "olt-ctl");
    ctl.append(btn("−", `${label} 줄이기`, () => move(-1), "btn sm olt-pm"), val, btn("+", `${label} 늘리기`, () => move(1), "btn sm olt-pm"));
    const top = el("span", "olt-lab-row");
    top.append(el("span", "olt-lab", label));
    if (blank) { // 단위 — 칸 | mm
      const seg = el("span", "olt-unit");
      seg.setAttribute("role", "group");
      seg.setAttribute("aria-label", `${label} 단위`);
      for (const u of ["칸", "mm"]) {
        const b = btn(u, u === "칸" ? `${label}을 칸 수(빈칸 글자 수)로` : `${label}을 mm 로 — 적은 mm 에 가장 가까운 칸 수가 됩니다`, () => { st.unit[key] = u; oltSync(); }, "olt-u");
        b.dataset.unit = u;
        seg.append(b);
      }
      top.append(seg);
    }
    c.append(top, ctl, el("span", "olt-was"));
    c.title = title;
    return c;
  };
  pos.append(step("front", "앞 여백", "앞 여백(mm) — 첫 줄이 시작하는 자리(문단 모양으로 비운 것). − / + 는 0.5mm 씩 · 값 칸에 바로 적어도 됩니다", 0, d.limits.front),
    step("lead", "레터 앞 빈칸", "레터 앞에 친 빈칸 — 칸(빈칸 글자 수) 또는 mm(그 폭)", 0, d.limits.lead),
    step("gap", "레터 뒤 빈칸", "레터와 글 사이에 친 빈칸 — 칸(빈칸 글자 수) 또는 mm(그 폭)", 0, d.limits.gap));
  // 2번째 줄 — 글이 넘어갈 때 둘째 줄부터가 시작하는 자리
  const l2 = el("div", "olt-row olt-l2row");
  const l2seg = el("span", "olt-l2s");
  l2seg.setAttribute("role", "radiogroup");
  l2seg.setAttribute("aria-label", "2번째 줄");
  for (const [k, name, hint] of [...OLT_L2, ...(OLT_RULE[d.rule.line2] ? [["rule", `규칙대로`, ""]] : [])]) {
    const b = btn(name, "", () => { if (k === "rule") st.l2 = null; else st.l2 = k === d.cur.line2 && k === oltL2Dflt() ? null : k; oltAsk(); }, "olt-l2b");
    b.dataset.l2 = k;
    b.setAttribute("role", "radio");
    b.title = k === "rule" ? `그 레벨에 건 규칙 그대로 — ${d.rule.line2 === "mm" ? `직접 ${oltMm(d.rule.mm)}mm` : OLT_RULE[d.rule.line2]}` : `2번째 줄을 ${hint}에 맞춤`;
    l2seg.append(b);
  }
  l2.append(el("span", "olt-lab", "2번째 줄"), l2seg);
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
    b.onclick = () => { if (b.getAttribute("aria-disabled") === "true" || st.stale) return; st.scope = k; st.pin = k === "split"; oltSync(); oltPlace(); };
    sc.append(b);
  }
  sc.append(oltSplitBox(st, d, btn)); // 나누기를 고르면 그 아래에 — 레벨 범위 · 여기서만 | 모두
  const foot = el("div", "olt-foot");
  const undo = btn("되돌리기", "방금 이 창이 반영한 것을 되돌립니다(그 뒤에 문서를 고쳤으면 도구 줄 「↶ 실행 취소」)", () => oltUndo(), "btn sm olt-undo");
  const go = btn("적용", "고른 범위에 반영합니다 — 실행 취소 1개", () => oltApply(), "btn sm primary olt-go");
  foot.append(el("span", "olt-msg"), undo, go);
  box.replaceChildren(head, demo, lrow, pal, pos, l2, el("div", "olt-sec", "적용 범위"), sc, foot);
  oltSync();
}

function oltSplitBox(st, d, btn) { // 「새 템플릿으로 나누기」 의 범위 — 레벨 띠(새 템플릿이 가질 레벨) · 부터 / 까지 · 여기서만 | 모두 · 옮겨 갈 줄 수
  const box = el("div", "olt-split");
  const name = `T${d.no}`;
  const lv = (k) => d.tplLevels.find((x) => x.level === k) || { level: k, letter: "" };
  const lvh = el("div", "olt-lvh"); // 레벨 띠 머리 — 새 템플릿 범위 · 원래 템플릿에 남는 쪽
  lvh.append(el("span", "olt-lvh-in"), el("span", "olt-lvh-out"));
  const strip = el("div", "olt-lvs"); // 템플릿의 레벨마다 칸 — 새 템플릿으로 가는 레벨은 강조 · 이 줄의 레벨은 점
  for (const x of d.tplLevels) {
    const c = el("span", "olt-lv");
    c.dataset.level = String(x.level);
    c.append(el("span", "olt-lv-n", `L${x.level}`), el("span", "olt-lv-l", x.table ? "▦" : x.letter || "·"), el("span", "olt-lv-c"));
    strip.append(c);
  }
  const sel = (cls, label, opts, get, set) => {
    const s = el("select", `olt-sel ${cls}`);
    s.setAttribute("aria-label", label);
    for (const [v, t] of opts) { const o = el("option", null, t); o.value = v; s.append(o); }
    s.onchange = () => { set(s.value); st.pin = true; oltAsk(0); };
    s._get = get; // oltSync 가 지금 값을 맞춘다
    return s;
  };
  const starts = Object.keys(d.ancestors).map(Number).sort((a, b) => a - b);
  const ends = d.tplLevels.map((x) => x.level).filter((k) => k >= d.level);
  const from = sel("olt-from", "새 템플릿의 시작 레벨", starts.map((k) => [String(k), `L${k} 「${lv(k).letter}」${k === d.level ? " · 이 줄" : " · 윗줄"}`]), () => String(st.start), (v) => { st.start = +v; });
  const to = sel("olt-to", "새 템플릿의 끝 레벨", ends.map((k, i) => [i === ends.length - 1 ? "" : String(k), `L${k} 「${lv(k).letter}」${i === ends.length - 1 ? " · 끝까지" : ""}`]), () => (st.upto == null ? "" : String(st.upto)), (v) => { st.upto = v === "" ? null : +v; });
  const r1 = el("div", "olt-srow");
  const sctrls = el("span", "olt-sctrls");
  const g1 = el("span", "olt-selg"), g2 = el("span", "olt-selg");
  g1.append(from, el("span", "olt-note", "부터"));
  g2.append(to, el("span", "olt-note", "까지"));
  sctrls.append(g1, g2);
  r1.append(el("span", "olt-lab", "레벨"), sctrls);
  const r2 = el("div", "olt-srow");
  const seg = el("span", "olt-cutseg");
  seg.setAttribute("role", "radiogroup");
  seg.setAttribute("aria-label", "나눌 줄");
  for (const k of ["here", "all"]) {
    const b = btn("", "", () => { st.cut = k; st.pin = true; oltAsk(0); }, "olt-cutb");
    b.dataset.cut = k;
    b.setAttribute("role", "radio");
    seg.append(b);
  }
  r2.append(el("span", "olt-lab", "나눌 줄"), seg);
  box.append(lvh, strip, r1, r2, el("div", "olt-ssum"));
  box.dataset.tpl = name;
  return box;
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
  const row = (tag, line, cls) => { const r = el("div", "olt-dr" + (cls ? ` ${cls}` : "")); r.append(el("span", "olt-dt", tag), line); return r; };
  const l2 = st.l2 || oltL2Dflt(); // 바꾼 뒤의 2번째 줄 — 둘째 줄이 시작하는 자리를 견본의 셋째 줄로(앞 여백 · 빈칸 · 레터 폭만큼 비움)
  const l2Line = el("div", "olt-l olt-l2" + (st.l2 ? " now" : " was"));
  l2Line.style.paddingLeft = `${Math.min(120, Math.max(0, st.front || 0) * 2.2)}px`;
  const hid = l2 === "text" ? d.leadCh.repeat(nw.lead) + nw.letter + d.gapCh.repeat(nw.gap) : l2 === "letter" ? d.leadCh.repeat(nw.lead) : "";
  l2Line.append(el("span", "olt-pre hid", hid), el("span", "olt-l2t", OLT_L2.some(([k]) => k === l2) ? "둘째 줄은 여기서" : "둘째 줄 — 규칙대로"));
  demo.replaceChildren(row("지금", oltLine(c.letter, c.lead, c.gap, d.leadCh, d.gapCh, d.text, c.frontMm, "was")), row("바꾼 뒤", oltLine(nw.letter, nw.lead, nw.gap, d.leadCh, d.gapCh, d.text, st.front, changed ? "now" : "was")), row("2번째 줄", l2Line, "olt-dr-l2"));
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
    const wmm = !mm ? oltBlankMm(k, v) : null, umm = !mm && st.unit[k] === "mm" && wmm != null; // 빈칸 — mm 로 보이나(폭을 못 재는 줄은 칸으로만)
    const cell = (n, w) => (mm ? `${oltMm(n)}mm` : umm ? `${oltMm(w)}mm` : `${n}칸`);
    const val = s.querySelector(".olt-val");
    if (document.activeElement !== val) val.value = off ? "–" : cell(v, wmm);
    val.disabled = off;
    s.dataset.unit = mm ? "mm" : umm ? "mm" : "칸";
    for (const b of s.querySelectorAll(".olt-u")) { const on = b.dataset.unit === (umm ? "mm" : "칸"); b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); b.disabled = b.dataset.unit === "mm" && wmm == null; }
    const diff = !off && (mm ? Math.abs(v - was) >= 0.05 : v !== was);
    s.classList.toggle("chg", diff);
    const other = mm || wmm == null ? "" : umm ? `${v}칸` : `${oltMm(wmm)}mm`; // 다른 단위의 값(「= 2칸」 · 「= 4.2mm」)
    s.querySelector(".olt-was").textContent = diff ? `지금 ${mm ? `${oltMm(was)}mm` : umm ? `${oltMm(oltBlankMm(k, was))}mm` : `${was}칸`}${other ? ` · 바꾼 뒤 ${other}` : ""}` : other ? `= ${other}` : "";
    for (const b of s.querySelectorAll(".olt-pm")) b.disabled = off;
  }
  // 2번째 줄
  const l2on = st.l2 || oltL2Dflt();
  for (const b of box.querySelectorAll(".olt-l2b")) {
    const k = b.dataset.l2, on = k === "rule" ? !st.l2 && !OLT_L2.some(([x]) => x === l2on) : k === l2on;
    b.classList.toggle("on", on);
    b.classList.toggle("cur", k === c.line2); // 지금 이 줄의 2번째 줄 자리
    b.setAttribute("aria-checked", String(on));
    b.dataset.now = k === c.line2 ? "지금" : "";
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
      if (!v || !v.ok) return ["새 템플릿으로 나누기", ""];
      const last = v.upto || Math.max(...d.tplLevels.map((x) => x.level));
      const who = v.cut === "all" ? `T${d.no} L${v.start} 줄 ${nf(v.roots)}개` : v.start < d.level ? `윗줄 L${v.start}` : v.roots > 1 ? `이 번호 묶음 ${nf(v.roots)}줄` : "이 줄";
      const parts = [`${who}부터 L${v.start}~L${last} · ${nf(v.moved)}줄이 ${v.name} 로`];
      if (v.stay) parts.push(`L${last} 아래 ${nf(v.stay)}줄은 T${d.no} 에 남음`);
      if (v.conform) parts.push(`${v.name} 의 L${d.level} = 이 서식${v.conform.change ? `(${nf(v.conform.change)}줄 맞춤)` : ""}`);
      return [`새 템플릿으로 나누기 · ${v.name}`, parts.join(" · ")];
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
  // 나누기의 범위 — 나누기를 고른 동안만(못 하는 범위가 됐어도 고치게 보인다)
  const sb = box.querySelector(".olt-split"), sv = pv && pv.split;
  sb.hidden = st.scope !== "split";
  const scopes = box.querySelector(".olt-scopes");
  scopes.dataset.split = st.scope === "split" ? "1" : "";
  scopes.dataset.splitBad = st.scope === "split" && sv && !sv.ok ? "1" : "";
  const last = st.upto || Math.max(...d.tplLevels.map((x) => x.level));
  const moved = new Map(((sv && sv.ok && sv.levels) || []).map(([k, n]) => [k, n]));
  const inLvs = d.tplLevels.map((x) => x.level).filter((k) => k >= st.start && k <= last);
  const firstIn = inLvs[0], lastIn = inLvs[inLvs.length - 1];
  const hasOut = d.tplLevels.some((x) => x.level < st.start || x.level > last);
  const rangeTxt = firstIn != null ? (firstIn === lastIn ? `L${firstIn}` : `L${firstIn}→L${lastIn}`) : "";
  sb.querySelector(".olt-lvh-in").textContent = sv && sv.ok && sv.name ? `새 템플릿 ${sv.name} · ${rangeTxt}` : `새 템플릿 · ${rangeTxt}`;
  const lvhOut = sb.querySelector(".olt-lvh-out");
  lvhOut.textContent = hasOut ? `T${d.no} 에 남음` : "";
  lvhOut.hidden = !hasOut;
  for (const x of sb.querySelectorAll(".olt-lv")) {
    const k = +x.dataset.level, inR = k >= st.start && k <= last;
    x.classList.toggle("in", inR);
    x.classList.toggle("in-first", inR && k === firstIn);
    x.classList.toggle("in-last", inR && k === lastIn);
    x.classList.toggle("out", !inR);
    x.classList.toggle("me", k === d.level);
    x.classList.toggle("stay", k > last && !!(sv && sv.ok && sv.stay));
    x.querySelector(".olt-lv-c").textContent = moved.has(k) ? `${nf(moved.get(k))}줄` : "";
    x.title = `T${d.no} L${k}${k === d.level ? " — 이 줄의 레벨" : ""}${inR ? ` · 새 템플릿 ${sv && sv.ok ? sv.name : ""}의 레벨${moved.has(k) ? ` · ${nf(moved.get(k))}줄이 옮겨 감` : ""}` : k < st.start ? ` · T${d.no} 에 남는 윗 레벨` : " · 새 템플릿에 안 듦(그 아래 줄은 T" + d.no + " 에 남음)"}`;
  }
  for (const s of sb.querySelectorAll(".olt-sel")) s.value = s._get();
  for (const b of sb.querySelectorAll(".olt-cutb")) {
    b.textContent = b.dataset.cut === "here" ? (st.start < d.level ? `윗줄 L${st.start} 과 그 아래` : "이 줄과 그 아래") : `T${d.no} L${st.start} 모두`;
    b.classList.toggle("on", st.cut === b.dataset.cut);
    b.setAttribute("aria-checked", String(st.cut === b.dataset.cut));
  }
  sb.querySelector(".olt-ssum").textContent = !sv ? "" : sv.ok ? `${sv.name} = L${sv.start}~L${last} · 옮겨 갈 줄 ${nf(sv.moved)}${sv.stay ? ` · T${d.no} 에 남는 아래 줄 ${nf(sv.stay)}` : ""} · 문서는 ${sv.conform ? "이 줄의 레벨만 이 서식으로" : "안 바뀜(템플릿만)"}` : sv.why;
  sb.classList.toggle("bad", !!(sv && !sv.ok));
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
  oltPlace(); // 높이가 바뀌었을 수 있다(나누기의 범위 칸이 저절로 펼쳐짐 · 레터 후보) — 창이 화면 아래로 넘치지 않게 자리를 다시
}

/* ---- 반영 · 되돌리기 ---- */
async function oltReload(done, keep = false) { // 반영 · 되돌린 뒤 — 그 줄의 새 값으로 창을 다시(열린 채). 그 줄을 더는 고칠 수 없으면 닫는다. keep = 고른 값은 그대로(문서 차례만 새로 — 409 뒤)
  const st = OLT.st;
  if (!st) return;
  try {
    const d = await api(`/api/docs/${st.doc}/outline/tune/suggest`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: st.pid }) });
    if (OLT.st !== st) return;
    if (keep) Object.assign(st, { d, pv: null, pvErr: "" });
    else Object.assign(st, { d, ...oltFresh(d), scope: "line", pin: false, pv: null, pvErr: "", done: done || null });
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
  const r = await structOp("outline/tune", { id: st.pid, scope, rev: st.d.rev, run: st.d.run, ...oltNew(), ...(scope === "split" ? oltSplitArgs() : {}) });
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
      : `새 템플릿 ${t.split ? t.split.name : ""}(L${t.split ? t.split.start : ""}${t.split && t.split.upto ? `~L${t.split.upto}` : " 부터"}) — ${nf(t.split ? t.split.moved : 0)}줄${t.split && t.split.stay ? ` · 아래 ${nf(t.split.stay)}줄은 T${st.d.no} 에 남음` : ""}`;
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

if (typeof OUTLINE_OP === "object") OUTLINE_OP.tune = "헤딩 고치기(레터 · 빈칸 · 앞 여백 · 2번째 줄 — 이 문단만 · 서식 전체 변경 · 새 템플릿으로 나누기)"; // 「기록」 탭의 이름(app.js — 기록 kind outline · op tune)
document.addEventListener("selectionchange", oltHint);
$("doc").addEventListener("input", oltHint);
$("doc").addEventListener("mousedown", oltDown, true);
$("doc").addEventListener("click", oltClick);
