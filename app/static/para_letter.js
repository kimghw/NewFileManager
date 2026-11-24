"use strict";
/* 레터 넣기(spec_hwpx_웹편집 ② §8-9) — 도구 줄 「문단 수정」 묶음의 단추(#tbLetter)를 누르면 그 아래 작은 메뉴(#plMenu)에서 레터를 골라 **커서가 든 문단을 헤딩(레터 줄)으로** 만든다.
   2026-11-17 사용자 "여기 문단에 속한 아이콘 중에서 레터를 선택해서 헤딩으로 넣을 수 있는 기능을 넣어줘, 둥근 숫자, 숫자. 숫자., 숫자) 이런것도 포함해서".
   · 메뉴에 보일 것은 서버가 준다(POST …/letter/suggest — app/para_letter.py): 지금 레터 · 이 문서의 개요 레벨(hwpx + 헤딩 추출 2단계가 있을 때) · 번호 후보(후보마다 **넣을 레터** — 앞의 같은 꼴 줄에 이어서 / 처음부터) · 기호.
   · 고르면 POST …/letter(structOp — 트랜잭션 하나 · 실행 취소 1):
       개요 레벨(「T1」 줄의 단추) = 레터 + 그 레벨의 서식(이 문단이 그 템플릿 레벨의 줄이 된다 — 번호는 형제 차례로) ·
       번호·기호·직접 입력 = 레터만(문단 모양은 그대로 — 번호형은 고른 문단이 여럿이면 차례로, 뒤에 바로 이어지던 같은 꼴 줄의 번호도 민다) · 「레터 빼기」 = 레터와 레터 뒤 빈칸을 지움.
   · 모달이 아니다(design.md §8 「하나 고르고 닫는 목록」) — 밖을 누르거나 Esc 로 닫힌다. 문서는 고르기 전에는 안 바뀐다. 문서의 커서·고른 범위는 그대로 둔다(단추·메뉴의 mousedown 기본 동작을 막는다).
   app.js 다음에 읽힌다(state · $ · el · api · toast · paraEl · selOffsets · setCaret · outlineSelected · flushAll · structOp 를 쓴다). 단추의 켜고 끄기는 app.js refreshToolbar. */
const PL = { box: null, st: null };

function plOpenAt(anchor, para = null) { // 다른 단추에서 같은 메뉴를 — 그 단추 아래(자리가 없으면 위)에 뜬다. 줄 오른쪽의 서식 아이콘(outline_spot.js — spec_hwpx_웹편집 ② §8-14): 단추에 data-pl-anchor 를 달면 다시 눌러 닫힌다. para = 커서가 문서 밖일 때 쓸 문단
  return plToggle(null, anchor, para);
}

async function plToggle(_e = null, anchor = null, para = null) {
  if (PL.box) { plClose(true); return; }
  if (state.busy || !state.id) return;
  const s = getSelection(), rng = s.rangeCount ? s.getRangeAt(0) : null;
  const at = rng && (rng.startContainer.nodeType === 1 ? rng.startContainer : rng.startContainer.parentElement);
  let p = at && at.closest ? at.closest(".para[data-id]") : null; // 커서(고른 범위의 시작)가 든 문단 — 이 문서(#doc)의 것만(둘째 면의 문단은 아님)
  const inDoc = !!p && $("doc").contains(p);
  if (!inDoc) p = para && para.isConnected ? para : state.cur ? paraEl(state.cur.id) : null; // 초점이 문서 밖에 있으면 마지막으로 커서를 둔 문단(다른 단추에서 열었으면 그 단추의 문단)
  if (!p) { toast("레터를 넣을 문단을 먼저 누르세요"); return; }
  const ids = (inDoc ? outlineSelected(p) : [p]).map((q) => q.dataset.id); // 고른 범위가 걸친 문단들(다음 문단 맨 앞에서 끝난 선택은 그 문단 제외) — 그릇이 섞였는지는 서버가 본다
  const caret = selOffsets(p), keep = inDoc && rng ? rng.cloneRange() : null, id = state.id, epoch = state.epoch;
  let d;
  try {
    await flushAll(); // 방금 친 글이 서버에 닿은 뒤에 묻는다(후보의 「넣을 레터」 는 서버의 글로 셈한다)
    if (epoch !== state.epoch) return;
    d = await api(`/api/docs/${id}/letter/suggest`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
  } catch (e) { if (epoch === state.epoch) toast(e.message, true); return; }
  if (epoch !== state.epoch || PL.box) return;
  PL.st = { epoch, ids, para: p.dataset.id, caret, keep, d, restart: false, custom: "", anchor: anchor instanceof Element ? anchor : null };
  const box = PL.box = el("div", "pl-menu");
  box.id = "plMenu";
  box.tabIndex = -1;
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", "레터 넣기 — 문단을 헤딩으로");
  box.addEventListener("keydown", plKey);
  box.addEventListener("mousedown", (e) => { if (!e.target.closest("input")) e.preventDefault(); }); // 단추를 눌러도 문서의 커서·고른 범위가 남게(입력 칸만 초점을 받는다)
  document.body.append(box);
  plDraw();
  plPlace();
  $("tbLetter").setAttribute("aria-expanded", "true");
  box.focus({ preventScroll: true });
  document.addEventListener("mousedown", plOutside, true);
  window.addEventListener("resize", plResized);
}

function plClose(refocus) { // refocus = 커서를 그 문단으로 돌려준다(Esc · 고른 직후)
  const st = PL.st, box = PL.box;
  if (!box) return;
  PL.box = PL.st = null;
  document.removeEventListener("mousedown", plOutside, true);
  window.removeEventListener("resize", plResized);
  box.remove();
  $("tbLetter").setAttribute("aria-expanded", "false");
  if (!refocus || !st || st.epoch !== state.epoch) return;
  const p = paraEl(st.para);
  if (!p) return;
  p.focus({ preventScroll: true });
  const k = st.keep;
  if (k && document.contains(k.startContainer) && document.contains(k.endContainer)) { const s = getSelection(); s.removeAllRanges(); s.addRange(k); } // 고른 범위 그대로(여러 문단에 걸친 것도)
  else if (st.caret) setCaret(p, st.caret.start, st.caret.end);
}
const plOutside = (e) => { if (PL.box && !PL.box.contains(e.target) && !e.target.closest("#tbLetter, [data-pl-anchor]")) plClose(false); }; // 단추를 다시 누른 것은 plToggle 이 닫는다
const plResized = () => plClose(false);

function plPlace() { // 단추 바로 아래 — 창 안에 들게. 다른 단추(plOpenAt — 문서 안의 아이콘)에서 열었으면 그 단추 아래, 아래 자리가 모자라면 위
  const box = PL.box, a = PL.st && PL.st.anchor && PL.st.anchor.isConnected ? PL.st.anchor : null;
  const r = (a || $("tbLetter")).getBoundingClientRect(), w = box.offsetWidth;
  box.style.left = `${Math.round(Math.max(8, Math.min(r.left, innerWidth - w - 8)))}px`;
  const below = innerHeight - r.bottom - 14, above = r.top - 14;
  if (a && below < 260 && above > below) { // 문서 아래쪽 줄 — 단추 위로
    box.style.maxHeight = `${Math.max(160, Math.round(above))}px`;
    box.style.top = `${Math.round(Math.max(8, r.top - 6 - box.offsetHeight))}px`;
    return;
  }
  box.style.top = `${Math.round(r.bottom + 6)}px`;
  box.style.maxHeight = `${Math.max(160, Math.round(below))}px`;
}

function plChip(text, title, fn, cls) {
  const b = el("button", "pl-chip" + (cls ? ` ${cls}` : ""), text);
  b.type = "button";
  b.title = title;
  b.onclick = fn;
  return b;
}
function plSec(name, note) { // 묶음 제목 한 줄 — 이름 + 옅은 설명
  const h = el("div", "pl-sec");
  h.append(el("b", null, name), el("span", "pl-note", note));
  return h;
}

function plDraw() { // 통째로 다시 그린다(단추 ≤ 50개) — 「이어서 · 처음부터」 가 바뀔 때. 직접 입력 칸의 글은 지킨다
  const st = PL.st, d = st.d, box = PL.box, many = d.count > 1;
  const head = el("div", "pl-head"), cur = d.cur || {};
  head.append(el("b", null, "레터 넣기"),
    el("span", "pl-sub", many ? ` — 고른 ${d.count}문단을 헤딩으로` : cur.letter ? ` — 지금 「${cur.letter}」${cur.no ? ` · T${cur.no} L${cur.level}` : ""}` : " — 이 문단을 헤딩으로"));
  const body = el("div", "pl-body");
  if (d.levels.length) { // 이 문서의 개요 레벨 — 템플릿마다 한 줄(레벨 차례: 왼쪽이 얕다)
    body.append(plSec("이 문서의 개요 레벨", "레터 + 그 레벨의 서식"));
    let row = null, last = null;
    for (const lv of d.levels) {
      if (lv.tpl !== last) {
        row = el("div", "pl-row");
        const t = el("span", "pl-t", `T${lv.no}`);
        t.title = `템플릿 T${lv.no} 의 레벨들 — 왼쪽이 얕은 레벨`;
        row.append(t);
        body.append(row);
        last = lv.tpl;
      }
      const b = plChip(lv.letter, `T${lv.no} L${lv.level} 「${lv.letter}」 줄로 — 레터와 이 레벨의 서식을 함께 넣습니다${lv.numbered ? "(번호는 같은 윗줄 아래 차례로)" : ""}`,
        () => plApply({ level: { tpl: lv.tpl, level: lv.level } }));
      b.dataset.level = `${lv.tpl}|${lv.level}`;
      if (lv.cur) { b.classList.add("cur"); b.setAttribute("aria-current", "true"); b.title = `지금 이 레벨(T${lv.no} L${lv.level})의 줄입니다`; }
      row.append(b);
    }
  } else if (d.format === "hwpx") {
    body.append(el("div", "pl-hint", "이 문서의 개요 레벨(레터 + 서식)은 헤딩 추출을 돌린 뒤에 보입니다."));
  }
  // 번호 — 레터만. 단추 글 = 넣을 레터(이어서: 앞의 같은 꼴 줄 다음 번호 · 처음부터: 그 꼴의 첫 번호)
  const hn = plSec("번호", "레터만 — 문단 모양은 그대로"), seg = el("span", "pl-seg");
  seg.setAttribute("role", "radiogroup");
  seg.setAttribute("aria-label", "번호를 매기는 방식");
  for (const [on, name, title] of [[false, "이어서", "앞의 같은 꼴 줄 다음 번호로(없으면 첫 번호)"], [true, "처음부터", "앞 줄과 무관하게 그 꼴의 첫 번호로"]]) {
    const b = plChip(name, `번호 — ${title}`, () => { st.restart = on; plDraw(); box.querySelector(`.pl-seg [aria-checked="true"]`).focus({ preventScroll: true }); }, "seg");
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(st.restart === on));
    if (st.restart === on) b.classList.add("on");
    seg.append(b);
  }
  hn.append(seg);
  const nums = el("div", "pl-grid");
  for (const n of d.numbers) {
    const put = st.restart ? n.first : n.next || n.letter, cont = !st.restart && n.from;
    const b = plChip(put, `「${put}」 넣기 — ${cont ? `앞 줄 「${n.from}」 에 이어서` : "이 꼴의 첫 번호"}${many ? ` · 고른 ${d.count}문단에 차례로` : ""} · 레터만(문단 모양은 그대로)`,
      () => plApply({ letter: n.letter, restart: st.restart }), cont ? "cont" : "");
    b.dataset.letter = n.letter;
    nums.append(b);
  }
  const syms = el("div", "pl-grid");
  for (const x of d.symbols) {
    const b = plChip(x.letter, `「${x.letter}」 넣기 — 레터만(문단 모양은 그대로)`, () => plApply({ letter: x.letter }));
    b.dataset.letter = x.letter;
    syms.append(b);
  }
  body.append(hn, nums, plSec("기호", "레터만"), syms);
  // 직접 입력(적은 그대로 넣는다) · 레터 빼기
  const foot = el("div", "pl-foot"), inp = el("input", "pl-in");
  inp.type = "text";
  inp.maxLength = d.max || 8;
  inp.placeholder = "직접 입력 — 예: ⑶ · (a) · 2.";
  inp.value = st.custom;
  inp.setAttribute("aria-label", "넣을 레터 직접 입력");
  inp.oninput = () => { st.custom = inp.value; };
  const go = plChip("넣기", "적은 레터를 그대로 넣습니다(Enter) — 헤딩 추출이 레터로 읽는 글자만", () => plCustom(), "go");
  foot.append(inp, go);
  if (cur.letter || many) {
    const rm = plChip("레터 빼기", many ? "고른 문단들의 레터와 레터 뒤 빈칸을 지웁니다(레터 앞 빈칸은 그대로)" : `레터 「${cur.letter}」 와 레터 뒤 빈칸을 지웁니다(레터 앞 빈칸은 그대로)`, () => plApply({ remove: true }), "rm");
    foot.append(rm);
  }
  box.replaceChildren(head, body, foot);
}

function plCustom() {
  const st = PL.st, v = (st.custom || "").trim();
  if (!v) { toast("넣을 레터를 적으세요"); const i = PL.box.querySelector(".pl-in"); if (i) i.focus({ preventScroll: true }); return; }
  plApply({ letter: v, restart: true }); // 직접 입력은 적은 그대로(앞 줄에 잇지 않는다)
}

function plKey(e) {
  const st = PL.st;
  if (!st) return;
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); plClose(true); return; }
  if (e.isComposing || e.keyCode === 229) return; // 한글 조합 중(직접 입력)
  const inInput = e.target.classList && e.target.classList.contains("pl-in");
  if (inInput) { if (e.key === "Enter") { e.preventDefault(); plCustom(); } return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
  if (!step) return;
  e.preventDefault(); // 화살표 — 단추 사이를 차례로(처음 ↔ 끝 이어짐)
  const items = [...PL.box.querySelectorAll("button, input")], i = items.indexOf(document.activeElement);
  items[i < 0 ? (step > 0 ? 0 : items.length - 1) : (i + step + items.length) % items.length].focus({ preventScroll: true });
}

async function plApply(body) {
  const st = PL.st;
  if (!st) return;
  if (st.epoch !== state.epoch) { plClose(false); return; } // 메뉴를 연 뒤 다른 문서를 열었다 — 그 문단 id 는 앞 문서의 것이다(새 문서에 보내지 않는다)
  plClose(true); // 커서를 그 문단으로 돌려준 뒤 편집(structOp 가 대기 표시를 그 문단에 건다)
  const r = await structOp("letter", { ids: st.ids, ...body });
  if (!r) return; // 거절(레터로 안 읽힘 · 바뀔 것이 없음 · 매달릴 윗줄 없음 · 표준 검사) — 까닭은 structOp 가 알렸다
  const m = r.letter || {}, put = (m.put || []).join(" "), n = (m.ids || []).length;
  const undo = " · 되돌리기는 도구 줄 「↶ 실행 취소」";
  const follow = m.follow ? ` · 뒤 ${m.follow}줄의 번호도 다시 매겼습니다` : "";
  if (m.mode === "level") toast(`T${m.no} L${m.level} 「${put}」 줄로 바꿨습니다${n > 1 ? `(${n}문단)` : ""} — 레터와 그 레벨의 서식${follow}${undo}`);
  else if (m.mode === "remove") toast(`레터 「${put}」 를 뺐습니다${follow}${undo}`);
  else toast(`레터 「${put}」 를 넣었습니다${n > 1 ? `(${n}문단)` : ""}${m.from ? ` — 앞 줄 「${m.from}」 에 이어서` : ""}${follow}${undo}`);
}

$("tbLetter").onclick = plToggle;
