"use strict";
/* 개요 레벨 더하기(spec_hwpx_웹편집 ② §8-6) — 템플릿의 **마지막 레벨** 줄에서 Alt+↓ 를 누르면(더 깊은 레벨이 없다) 새 개요 레벨의 후보를 그 줄 아래 작은 창에 보이고,
   고른 것으로 템플릿에 레벨을 더한 뒤 그 줄을 그 레벨로 내린다.
   2026-11-16 사용자 "alt + 아랫방향을 누르면 없는 경우 10개 정도 레터와 앞공백 2번째줄 공백을 제안해서 템플릿에 새로운 서식을 /개요레벨을 추가할 수 있는 기능을 넣어주세요".
   · 후보 = 서버가 준다(POST …/outline/grow/suggest — app/outline_grow.py): 레터 약 10개(이 템플릿이 안 쓰는 계열 · 깊은 기호 먼저 · 그다음 번호형) + 권하는 앞 공백(칸) + 둘째 줄 방식.
     레터는 「직접 입력」 으로도. 창 위쪽의 **견본 세 줄**(윗 레벨 줄 · 고른 레터의 첫째 줄 = 앞 공백 + 레터 + 글 · 둘째 줄 = 고른 방식의 자리)로 들여쓰기를 눈으로 보고,
     후보 줄은 한 줄씩(앞 공백 + 레터 + 글) — 후보마다 두 줄을 그리면 창이 길어 그 줄을 가린다.
   · 키: ↑↓(Alt+↑↓ 도) 고르기 · 1~9·0 그 후보 · ←→ 앞 공백 한 칸씩 · Tab 둘째 줄 방식 · Enter 더하기 · Esc 닫기. 마우스: 줄을 눌러 고르고 「더하기」(두 번 누르면 바로).
   · 더하기 = POST …/outline/grow(structOp — 트랜잭션 하나 · 실행 취소 1: 템플릿의 레벨도 함께 돌아간다) → 오버레이 요약을 다시 읽는다(outlineLoad — 「TN Lk」 표시 · 템플릿 관계 트리).
   · 모달이 아니다(design.md §8 「하나 고르고 닫는 목록」) — 밖을 누르거나 문서를 굴리면 닫힌다. 문서는 「더하기」 전에는 안 바뀐다.
   app.js 다음에 읽힌다(state · heads · $ · el · api · toast · paraEl · outlineLine · isRooted · selOffsets · setCaret · structOp · outlineLoad 를 쓴다). app.js outlineLevel 이 outlineGrowAt → outlineGrowOpen 을 부른다. */
const OLG = { box: null, st: null };
const OLG_KEYS = "↑↓ 고르기 · ←→ 앞 공백 · Tab 둘째 줄 · Enter 더하기 · Esc 닫기";

function outlineGrowAt(lines) { // 걸친 개요 줄이 모두 한 템플릿의 마지막 레벨인가(괄호 줄 제외) — 그때만 Alt+↓ 가 후보를 연다. 섞였으면 종전대로 서버가 까닭을 알린다
  if (!heads.outline || !lines.length) return false;
  const first = outlineLine(lines[0]);
  const t = first && heads.outline.templates ? heads.outline.templates[String(first.tpl)] : null;
  if (!t || +first.level !== +t.max) return false;
  return lines.every((q) => { const ol = outlineLine(q); return !!ol && String(ol.tpl) === String(first.tpl) && +ol.level === +first.level && !isRooted(ol.role); });
}

async function outlineGrowOpen(p, lines) {
  outlineGrowClose(false);
  const id = state.id, epoch = state.epoch, ids = lines.map((q) => q.dataset.id);
  const caret = selOffsets(p);
  let d;
  try {
    d = await api(`/api/docs/${id}/outline/grow/suggest`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); return; }
  if (epoch !== state.epoch || !document.contains(p) || OLG.st) return;
  OLG.st = { epoch, ids, para: p.dataset.id, caret, d, sel: 0, lead: d.lead, line2: d.line2, custom: "" };
  const box = OLG.box = el("div", "ol-grow");
  box.id = "olGrow";
  box.tabIndex = -1;
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", `템플릿 T${d.no} 에 새 개요 레벨 L${d.level} 더하기`);
  box.addEventListener("keydown", olgKey);
  box.addEventListener("mousedown", (e) => { if (!e.target.closest("input, button")) e.preventDefault(); }); // 창 안 빈 곳을 눌러도 초점이 문서로 가지 않게
  document.body.append(box);
  olgDraw();
  olgPlace(p);
  box.focus({ preventScroll: true });
  document.addEventListener("mousedown", olgOutside, true);
  $("scroller").addEventListener("scroll", olgScrolled, { passive: true });
  window.addEventListener("resize", olgScrolled);
}

function outlineGrowClose(refocus) { // refocus = 문단으로 커서를 돌려준다(Esc · 더하기 직전)
  const st = OLG.st, box = OLG.box;
  if (!box) return;
  OLG.box = OLG.st = null;
  document.removeEventListener("mousedown", olgOutside, true);
  $("scroller").removeEventListener("scroll", olgScrolled);
  window.removeEventListener("resize", olgScrolled);
  box.remove();
  if (!refocus || !st || st.epoch !== state.epoch) return;
  const p = paraEl(st.para);
  if (!p) return;
  p.focus({ preventScroll: true });
  if (st.caret) setCaret(p, st.caret.start, st.caret.end);
}
const olgOutside = (e) => { if (OLG.box && !OLG.box.contains(e.target)) outlineGrowClose(false); };
const olgScrolled = () => outlineGrowClose(false);

function olgPlace(p) { // 그 줄 바로 아래(자리가 없으면 위) — 창 안에 들게
  const box = OLG.box, r = p.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
  const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
  const below = r.bottom + 6, top = below + h <= innerHeight - 8 ? below : Math.max(8, r.top - h - 6);
  box.style.left = `${Math.round(left)}px`;
  box.style.top = `${Math.round(top)}px`;
}

const olgPre = (t, cls) => el("span", "olg-pre" + (cls ? ` ${cls}` : ""), t);
function olgLine(st, letter, text) { // 한 줄 견본 — 앞 공백 · 레터 · 레터 뒤 공백 · 글(공백을 그대로 그린다)
  const l = el("span", "olg-l");
  l.append(olgPre(" ".repeat(st.lead)), olgPre(letter, "lt"), olgPre(st.d.gap), text);
  return l;
}
function olgDemo(st, letter) { // 견본(높이 고정 — design.md §6): 윗 레벨 줄 · 고른 레터의 첫째 줄 · 둘째 줄(고른 방식의 자리 — 안 보이는 같은 글로 그 폭만큼 민다)
  const d = st.d, demo = el("div", "olg-demo"), c = el("span", "olg-l ctx"), l2 = el("span", "olg-l");
  c.append(olgPre(d.last.prefix), `윗 레벨(L${d.last.level}) 줄`);
  l2.append(olgPre(st.line2 === "text" ? " ".repeat(st.lead) + letter + d.gap : st.line2 === "letter" ? " ".repeat(st.lead) : d.last.prefix, "hid"), el("span", "olg-2", "둘째 줄은 여기서 시작"));
  demo.append(c, olgLine(st, letter || "?", "새 레벨의 글(첫째 줄)"), l2);
  demo.title = `견본 — 윗 레벨(앞 공백 ${d.last.lead}칸 「${d.last.letter}」) 아래에 새 레벨이 놓이는 모양: 앞 공백 ${st.lead}칸 · 둘째 줄 = ${(d.line2s.find((x) => x[0] === st.line2) || [])[1] || ""}`;
  return demo;
}

function olgDraw() { // 통째로 다시 그린다(후보 ≤ 10줄) — 고른 줄 · 앞 공백 · 둘째 줄이 바뀔 때마다. 직접 입력 칸의 글·초점은 지킨다
  const st = OLG.st, box = OLG.box, d = st.d;
  const inFocus = document.activeElement && document.activeElement.classList.contains("olg-in");
  const head = el("div", "olg-head");
  head.append(el("b", null, `T${d.no} 에 새 개요 레벨 L${d.level}`),
    el("span", "olg-sub", ` — L${d.last.level} 「${d.last.letter}」 아래${d.lines > 1 ? ` · 고른 ${d.lines}줄을 내림` : ""}`));
  const nn = d.candidates.length;
  const demo = olgDemo(st, st.sel === nn ? st.custom.trim() : d.candidates[st.sel].letter);
  const list = el("div", "olg-list");
  list.setAttribute("role", "listbox");
  d.candidates.forEach((c, i) => {
    const o = el("div", "olg-opt" + (i === st.sel ? " sel" : ""));
    o.setAttribute("role", "option");
    o.setAttribute("aria-selected", String(i === st.sel));
    o.dataset.i = String(i);
    o.append(el("span", "olg-no", i < 9 ? String(i + 1) : i === 9 ? "0" : ""), olgLine(st, c.letter, "새 레벨의 글"));
    if (c.numbered) o.append(el("span", "olg-tag", "번호"));
    else if (c.inDoc) o.append(el("span", "olg-tag doc", "문서"));
    o.title = `레터 「${c.letter}」${c.numbered ? " — 번호형: 같은 부모 아래 형제 차례로 번호를 매깁니다" : ""}${c.inDoc ? " · 이 문서의 다른 템플릿이 쓰는 레터" : ""}`;
    o.onclick = () => olgPick(i);
    o.ondblclick = () => { olgPick(i); outlineGrowApply(); };
    list.append(o);
  });
  const n = d.candidates.length, co = el("div", "olg-opt cus" + (st.sel === n ? " sel" : ""));
  co.setAttribute("role", "option");
  co.setAttribute("aria-selected", String(st.sel === n));
  const inp = el("input", "olg-in");
  inp.type = "text";
  inp.maxLength = 8;
  inp.placeholder = "직접 입력 — 예: ◆ · (a) · 1.";
  inp.value = st.custom;
  inp.setAttribute("aria-label", "새 레벨의 레터 직접 입력");
  inp.oninput = () => { st.custom = inp.value; const old = box.querySelector(".olg-demo"); if (old) old.replaceWith(olgDemo(st, st.custom.trim())); }; // 견본만 갈아 끼운다(입력 칸을 다시 그리면 한글 조합이 끊긴다)
  inp.onfocus = () => { if (st.sel !== n) { st.sel = n; olgDraw(); } };
  co.append(el("span", "olg-no", "✎"), inp);
  list.append(co);
  const ctl = el("div", "olg-ctl");
  const btn = (text, title, fn) => { const b = el("button", "btn sm", text); b.type = "button"; b.title = title; b.onclick = fn; return b; };
  const leadBox = el("span", "olg-lead");
  leadBox.append(btn("−", "앞 공백 한 칸 줄이기(←)", () => olgLead(-1)), el("b", "olg-n", `${st.lead}칸`), btn("+", "앞 공백 한 칸 늘리기(→)", () => olgLead(1)));
  const seg = el("span", "olg-seg");
  seg.setAttribute("role", "radiogroup");
  seg.setAttribute("aria-label", "둘째 줄");
  for (const [k, name] of d.line2s) {
    const b = btn(name.replace("에 맞춤", "").replace("과 같게", ""), `둘째 줄부터 — ${name}(Tab 으로 바꿈)`, () => { st.line2 = k; olgDraw(); });
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(st.line2 === k));
    if (st.line2 === k) b.classList.add("on");
    seg.append(b);
  }
  ctl.append(el("span", "olg-lab", "앞 공백"), leadBox, el("span", "olg-lab", "둘째 줄"), seg);
  const foot = el("div", "olg-foot");
  const go = btn("더하기", "고른 레터로 템플릿에 새 레벨을 더하고 이 줄을 그 레벨로 내립니다(Enter) — 도구 줄 「↶ 실행 취소」 로 되돌립니다(템플릿의 레벨도 함께)", () => outlineGrowApply());
  go.classList.add("primary");
  foot.append(el("span", "olg-keys", OLG_KEYS), go);
  box.replaceChildren(head, demo, list, ctl, foot);
  if (inFocus || st.sel === n) { inp.focus({ preventScroll: true }); inp.setSelectionRange(inp.value.length, inp.value.length); }
}

function olgPick(i) {
  const st = OLG.st, n = st.d.candidates.length;
  st.sel = Math.max(0, Math.min(n, i));
  olgDraw();
  if (st.sel < n) OLG.box.focus({ preventScroll: true });
  const o = OLG.box.querySelector(".olg-opt.sel");
  if (o) o.scrollIntoView({ block: "nearest" });
}
function olgLead(by) {
  const st = OLG.st;
  st.lead = Math.max(0, Math.min(st.d.leadMax, st.lead + by));
  olgDraw();
}

function olgKey(e) {
  const st = OLG.st;
  if (!st) return;
  const inInput = e.target.classList && e.target.classList.contains("olg-in");
  const n = st.d.candidates.length, mod = e.ctrlKey || e.metaKey;
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); outlineGrowClose(true); return; }
  if (e.isComposing || e.keyCode === 229) return; // 한글 조합 중(직접 입력)
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); olgPick((st.sel + (e.key === "ArrowDown" ? 1 : n)) % (n + 1)); return; } // Alt+↓ 를 거듭 눌러도 다음 후보
  if (e.key === "Enter") { e.preventDefault(); outlineGrowApply(); return; }
  if (e.key === "Tab") { e.preventDefault(); const ks = st.d.line2s.map((x) => x[0]); st.line2 = ks[(ks.indexOf(st.line2) + (e.shiftKey ? ks.length - 1 : 1)) % ks.length]; olgDraw(); return; }
  if (inInput || mod || e.altKey) return; // 입력 칸 안의 글자·화살표는 그대로
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); olgLead(e.key === "ArrowLeft" ? -1 : 1); return; }
  if (/^[0-9]$/.test(e.key)) { const i = e.key === "0" ? 9 : +e.key - 1; if (i < n) { e.preventDefault(); olgPick(i); } }
}

async function outlineGrowApply() {
  const st = OLG.st;
  if (!st) return;
  const n = st.d.candidates.length;
  const letter = st.sel === n ? st.custom.trim() : st.d.candidates[st.sel].letter;
  if (!letter) { toast("레터를 고르거나 직접 입력하세요"); return; }
  outlineGrowClose(true); // 커서를 그 줄로 돌려준 뒤 편집(structOp 가 대기 표시를 그 문단에 건다)
  const r = await structOp("outline/grow", { ids: st.ids, letter, lead: st.lead, line2: st.line2 });
  if (!r) return; // 거절(이미 쓰는 계열 · 레터로 안 읽힘 · 표준 검사) — 까닭은 structOp 가 알렸다
  outlineLoad(true); // 템플릿의 레벨 수·사슬·새 레벨의 자리가 바뀌었다 — 여백 표시의 설명 · 템플릿 관계 트리 · 다음 Alt+↓ 의 판정이 읽는다
  const g = r.grown || {};
  toast(`T${g.no} 에 새 개요 레벨 L${g.level} 「${g.letter}」 를 더했습니다 — 이제 L${g.level - 1} 줄의 Enter 가 이 레벨의 새 줄을 만듭니다 · 되돌리기는 도구 줄 「↶ 실행 취소」`);
}
