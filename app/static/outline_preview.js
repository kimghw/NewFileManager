// 개요 레벨 미리보기·비교 창(spec_hwpx_웹편집 ② §8-3) — 「템플릿 관계」 열의 레벨 줄에서 띄우는 **떠 있는 창**(모달 아님 — 문서·열은 그대로 쓰고, 머리를 끌어 옮기고 모서리로 크기 조절).
// 탭 둘(한 레벨씩):
//  · 「자리 미리보기」 = 「자리 수정」(outline_format.js 고치기 줄)의 값을 바꾸면 지금 → 바뀐 뒤 — 대표 줄 그림(mm 자 · 레터/글 시작/둘째 줄) · 값 표 · 줄 묶음별 바뀌는 값.
//    자료 POST …/outline/slots/{tpl}/{L}/preview(문서·규칙은 안 바뀜). 「적용」 은 열의 고치기 줄 「적용」 과 같은 것.
//    창 머리 아래 **자리 수정 칸**(레터 위치 · 글 시작 · 둘째 줄 규칙·mm — olpEditBuild)에서도 고친다: 열의 고치기 줄의 거울(값의 원본은 그 줄 — olfBody 가 읽는다).
//  · 「서식 비교」 = 그 레벨의 서식 갈래(outline_match.js OLM.data · OLM.keys)를 표로 — 갈래마다 견본 글(그 갈래의 글꼴·크기·굵기로) · 대표와 다른 값만(「같은 값도」 로 전부) · 대표로 · 맞추기.
// app.js·outline_format.js·outline_match.js 다음에 읽힌다(el·hBtn·api·toast·heads·state·nf·short·oneLine·headsGo·headsParaLink·olfSlot·olfBody·olmFresh·olmSlotData·olmLoad·olmText·olmTpl·olmSetRep·olmMatch·OLM).
// 훅: olfRow 「자리 수정」 → olpOpen(…, "pos") · olpFormClosed · olfForm 입력 → olpFormInput · olfRefresh·olmRedraw → olpRefresh · olmRow 「비교」 → olpOpen(…, "cmp").
const OLP = { tpl: null, level: null, tab: "pos", epoch: null, seq: 0, timer: null, pv: null, showAll: false, at: null, loading: false };
const OLP_KEYS3 = [["letterMm", "레터 위치"], ["textMm", "글 시작"], ["line2Mm", "둘째 줄"]];
const OLP_PARA = new Set(["align", "line1Mm", "line2Mm", "indentRightMm", "spaceBeforePt", "spaceAfterPt", "lineSpacingPct"]); // 서식 비교 표의 「문단」 묶음(outline_match.PARA_KEYS)
const olpMm = (v) => (v == null ? "–" : (Math.round(v * 10) / 10).toFixed(1));
const olpSame = (a, b) => a != null && b != null && Math.abs(a - b) < 0.05;
const olpDelta = (a, b) => { const d = Math.round((b - a) * 10) / 10; return d > 0 ? `+${d.toFixed(1)}` : d < 0 ? `−${Math.abs(d).toFixed(1)}` : "0"; };

function olpWin() { // 창은 하나 — 처음 열 때 만든다
  let w = $("olpWin");
  if (w) return w;
  w = el("section", "olp");
  w.id = "olpWin";
  w.hidden = true;
  w.setAttribute("role", "dialog");
  w.setAttribute("aria-modal", "false");
  w.setAttribute("aria-labelledby", "olpTitle");
  const head = el("header", "olp-head");
  const title = el("strong", "olp-title");
  title.id = "olpTitle";
  const tabs = el("div", "olp-tabs");
  tabs.setAttribute("role", "tablist");
  for (const [k, t] of [["pos", "자리 미리보기"], ["cmp", "서식 비교"]]) {
    const b = el("button", "olp-tab", t);
    b.type = "button";
    b.dataset.tab = k;
    b.setAttribute("role", "tab");
    b.onclick = () => olpTab(k);
    tabs.append(b);
  }
  const x = el("button", "olp-x", "✕");
  x.type = "button";
  x.title = "닫기(Esc)";
  x.setAttribute("aria-label", "미리보기 창 닫기");
  x.onclick = olpClose;
  head.append(title, tabs, x);
  const edit = el("div", "olp-edit"); // 자리 수정 칸 — 몸(미리보기를 받을 때마다 다시 그림)과 달리 한 번만 만든다(치던 칸이 안 사라지게)
  edit.hidden = true;
  olpEditBuild(edit);
  const body = el("div", "olp-body");
  const foot = el("div", "olp-foot");
  w.append(head, edit, body, foot);
  w.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); olpClose(); } });
  olpDrag(w, head);
  document.body.append(w);
  return w;
}

function olpDrag(w, head) { // 머리를 끌어 옮긴다 — 화면 안에 머물게
  head.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    const r = w.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    head.setPointerCapture(e.pointerId);
    const move = (ev) => {
      const x = Math.min(Math.max(0, ev.clientX - dx), window.innerWidth - 80), y = Math.min(Math.max(0, ev.clientY - dy), window.innerHeight - 40);
      w.style.left = `${x}px`;
      w.style.top = `${y}px`;
      OLP.at = { x, y };
    };
    const up = () => { head.removeEventListener("pointermove", move); head.removeEventListener("pointerup", up); head.removeEventListener("pointercancel", up); };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", up);
    head.addEventListener("pointercancel", up);
  });
}

function olpPlace(w) { // 처음 자리 — 「템플릿 관계」 열 바로 왼쪽, 편집 도구 줄 아래(문서 위에 겹침 — 도구 줄·실행 취소는 가리지 않는다). 사용자가 옮겼으면 그 자리
  const vw = window.innerWidth, vh = window.innerHeight;
  const col = $("headsDlg"), pan = $("panel"), pr = pan ? pan.getBoundingClientRect() : null;
  const r = col && !col.hidden ? col.getBoundingClientRect() : pr && pr.width > 0 ? pr : null; // 열이 없으면(「템플릿」 탭에서 엶) 패널 바로 왼쪽 — 트리를 가리지 않는다
  const doc = $("doc"), dr = (doc && doc.parentElement ? doc.parentElement : $("viewer") || document.body).getBoundingClientRect();
  if (OLP.at) {
    w.style.left = `${Math.max(0, Math.min(OLP.at.x, vw - 120))}px`;
    w.style.top = `${Math.max(0, Math.min(OLP.at.y, vh - 80))}px`;
  } else {
    const room = r ? r.left - 16 : vw - 32;
    const width = Math.round(Math.min(720, Math.max(380, room), vw - 16));
    w.style.width = `${width}px`;
    const left = r && room >= 380 ? r.left - width - 8 : vw - width - 8;
    w.style.left = `${Math.max(8, left)}px`;
    w.style.top = `${Math.max(8, Math.min(vh - 200, Math.max(dr.top, r ? r.top : 0) + 8))}px`;
  }
  w.style.maxHeight = `${Math.max(180, vh - parseFloat(w.style.top) - 12)}px`; // 높이는 내용만큼(모서리로 늘리면 그만큼)
}

function olpOpen(tpl, L, tab = "pos") {
  if (!state.id) return;
  const w = olpWin();
  const same = !w.hidden && String(OLP.tpl) === String(tpl) && +OLP.level === +L;
  OLP.tpl = String(tpl);
  OLP.level = +L;
  OLP.tab = tab;
  OLP.epoch = state.epoch;
  if (!same) OLP.pv = null;
  if (w.hidden) { olpPlace(w); w.hidden = false; }
  olpRender();
  if (tab === "pos") olpFetch(0);
  else if (!olmFresh()) olmLoad().then(() => olpRender());
}

function olpClose() {
  const w = $("olpWin");
  clearTimeout(OLP.timer);
  OLP.seq += 1;
  if (w) w.hidden = true;
}

function olpFormClosed(tpl, L) { // 「자리 수정」 을 접었다 — 그 레벨의 자리 미리보기면 창도 닫는다
  const w = $("olpWin");
  if (w && !w.hidden && OLP.tab === "pos" && String(OLP.tpl) === String(tpl) && +OLP.level === +L) olpClose();
}

function olpFormInput(tpl, L) { // 고치기 줄의 값이 바뀜 — 그 레벨 창이 떠 있으면 바뀐 뒤를 다시(안 떠 있으면 띄움)
  const w = $("olpWin");
  if (!w || w.hidden || String(OLP.tpl) !== String(tpl) || +OLP.level !== +L) { olpOpen(tpl, L, "pos"); return; }
  if (OLP.tab !== "pos") { OLP.tab = "pos"; olpRender(); }
  olpEditSync();
  olpFetch();
}

function olpRefresh() { // 오버레이·서식 갈래가 바뀐 뒤(적용·맞추기·실행 취소·다른 문서) — 떠 있는 창을 새 값으로
  const w = $("olpWin");
  if (!w || w.hidden) return;
  if (OLP.epoch !== state.epoch || !state.id || !olmTpl(OLP.tpl)) { olpClose(); return; }
  if (OLP.tab === "pos") { olpEditSync(); olpFetch(120); } // 열의 고치기 줄을 새로 그렸다(olfRefresh) — 창의 칸도 그 값으로
  else olpRender();
}

function olpTab(tab) {
  if (tab === "pos") { // 자리 미리보기는 열의 고치기 줄 값으로 — 접혀 있으면 편다
    const b = olpRowEl() && olpRowEl().querySelector(".olf-btn");
    if (b && b.getAttribute("aria-expanded") !== "true") { b.click(); return; } // 「자리 수정」 이 olpOpen(…, "pos") 를 부른다
  }
  OLP.tab = tab;
  olpRender();
  if (tab === "pos") olpFetch(0);
  else if (!olmFresh()) olmLoad().then(() => olpRender());
}

function olpRowEl() { // 그 레벨의 자리 줄 — 트리가 두 곳(「템플릿」 탭 · 「템플릿 관계」 열)에 있으면 고치기 줄을 펴 둔 쪽
  const all = [...document.querySelectorAll(`.tpl-tree .olf[data-tpl="${CSS.escape(String(OLP.tpl))}"][data-level="${+OLP.level}"]`)];
  return all.find((r) => { const f = r.querySelector(".olf-edit"); return f && !f.hidden; }) || all[0] || null;
}
function olpForm() { const r = olpRowEl(); return r ? r.querySelector(".olf-edit") : null; }

// ---------------------------------------------------------------- 자리 수정 칸(창 안)
// 창의 칸은 열의 고치기 줄(outline_format.js olfForm)의 **거울**이다 — 값의 원본은 그 줄(olfBody 가 읽는다): 창에서 고치면 그 줄의 칸에 적고 그 칸의 입력 이벤트를 일으켜 같은 길(olpFormInput → 미리보기)로 간다.
// 「글 시작」 은 따로 저장하는 값이 아니다 — 레터와 글 사이(레터 + 레터 뒤 빈칸)는 글자 폭이라, 글 시작을 고치면 레터 위치가 같이 움직인다(레터 위치 = 글 시작 − 그 폭 · 서식 관리자의 「글 시작」 칸과 같은 뜻).
function olpRef() { const d = OLP.pv && OLP.pv.data; return d ? d.rep || d.slot || null : null; } // 받아 둔 미리보기의 기준 줄(대표 줄 — 없으면 새 줄) {before, after, gapMm}
function olpGap(sl) { // 레터 위치 → 글 시작(mm) = 레터 + 레터 뒤 빈칸 폭 — 미리보기가 준 0.01mm 값(gapMm), 옛 서버면 슬롯 요약(0.1mm 로 반올림한 두 값)의 차
  const ref = olpRef();
  return ref && ref.gapMm != null ? ref.gapMm : Math.round((sl.to.textMm - sl.to.letterMm) * 10) / 10;
}

function olpEditBuild(box) {
  const num = (cls, label) => {
    const i = el("input");
    i.type = "number"; i.min = "0"; i.max = "300"; i.step = "0.1"; i.className = cls; i.setAttribute("aria-label", label);
    return i;
  };
  const field = (k, name, ...ctl) => { const f = el("span", "olp-efield"); f.append(el("span", `olp-key k-${k}`, name), ...ctl); return f; };
  const letter = num("olp-e-letter", "레터 위치(mm)");
  letter.title = "레터 위치(mm) — 본문 왼끝에서 레터까지. 바꾸면 첫째 줄이 통째로 움직입니다(글 시작도 같이 · 앞 공백은 그대로)";
  const text = num("olp-e-text", "글 시작(mm) — 첫째 줄의 글이 시작하는 자리");
  const mode = el("select", "olp-e-mode");
  mode.setAttribute("aria-label", "둘째 줄 규칙");
  mode.title = "둘째 줄 규칙 — 글 시작에 맞춤 · 직접(mm 를 적음) · 문단 서식 그대로(문단이 지금 가진 값을 둠)";
  for (const [v, t] of Object.entries(OLF_RULE)) { const o = el("option", null, t); o.value = v; mode.append(o); }
  const l2 = num("olp-e-l2", "둘째 줄 위치(mm)");
  l2.title = "둘째 줄 위치(mm) — 본문 왼끝에서. 「직접」 일 때만 적습니다(다른 규칙이면 그 규칙이 정한 값이 보입니다)";
  letter.oninput = () => olpEditPush("letter");
  text.oninput = () => olpEditPush("text");
  l2.oninput = () => olpEditPush("l2");
  mode.onchange = () => olpEditPush("mode");
  for (const i of [letter, text, l2]) i.onblur = () => olpEditSync(); // 치던 칸을 떠나면 열의 값 꼴로(13 → 열에 적힌 그대로 · 글 시작은 0.1mm 로)
  box.append(field("letterMm", "레터 위치", letter), field("textMm", "글 시작", text), field("line2Mm", "둘째 줄", mode, l2, el("span", "muted", "mm")), el("span", "muted olp-e-note"));
}

function olpEditPush(which) { // 창의 칸 → 열의 고치기 줄 → 그 칸의 이벤트(안 퍼지게)가 olpFormInput 을 불러 미리보기를 다시
  const w = $("olpWin"), form = olpForm(), sl = olfSlot(OLP.tpl, OLP.level);
  if (!w || !form || form.hidden || !sl || !sl.to) return;
  const q = (c) => w.querySelector(c), f = (c) => form.querySelector(c);
  if (which === "mode") { f(".olf-mode").value = q(".olp-e-mode").value; f(".olf-mode").dispatchEvent(new Event("change")); return; }
  if (which === "l2") { f(".olf-l2").value = q(".olp-e-l2").value; f(".olf-l2").dispatchEvent(new Event("input")); return; }
  let v = q(".olp-e-letter").value;
  if (which === "text") { const n = parseFloat(q(".olp-e-text").value); v = Number.isFinite(n) ? olpMm(n - olpGap(sl)) : ""; }
  f(".olf-letter").value = v;
  f(".olf-letter").dispatchEvent(new Event("input"));
}

function olpEditSync() { // 열의 고치기 줄 → 창의 칸(지금 치고 있는 칸은 그대로 둔다). 고치기 줄이 접혀 있거나 「서식 비교」 탭이면 칸을 숨긴다
  const w = $("olpWin"), box = w ? w.querySelector(".olp-edit") : null;
  if (!box) return;
  const sl = olfSlot(OLP.tpl, OLP.level), form = !w.hidden && OLP.tab === "pos" ? olpForm() : null;
  const on = !!(form && !form.hidden && sl && !sl.rooted && sl.at && sl.to);
  box.hidden = !on;
  if (!on) return;
  const q = (c) => box.querySelector(c), f = (c) => form.querySelector(c);
  const put = (i, v) => { if ((document.activeElement !== i || i.disabled) && i.value !== v) i.value = v; }; // 꺼진 칸은 초점이 남아 있어도 바꾼다(치는 중이 아니다)
  const gap = olpGap(sl), mode = f(".olf-mode").value, lv = parseFloat(f(".olf-letter").value);
  const now = olfBody(sl, form), ref = olpRef();
  const after = ref && ref.after && OLP.pv.body && !now.error && JSON.stringify(now.body) === JSON.stringify(OLP.pv.body) ? ref.after : null; // 받아 둔 미리보기가 지금 칸의 값으로 계산한 것일 때만 — 기준 줄의 바뀐 뒤
  put(q(".olp-e-mode"), mode);
  put(q(".olp-e-letter"), f(".olf-letter").value);
  put(q(".olp-e-text"), after && after.textMm != null ? olpMm(after.textMm) : Number.isFinite(lv) ? olpMm(lv + gap) : ""); // 아래 값 표의 「글 시작 — 바뀐 뒤」 와 같은 값(계산 전에는 레터 + 폭)
  const l2 = q(".olp-e-l2"), fl2 = f(".olf-l2");
  l2.disabled = mode !== "mm";
  if (mode !== "mm" && after && after.line2Mm != null) fl2.value = olpMm(after.line2Mm); // 「직접」 이 아니면 둘째 줄은 규칙이 정한다 — 꺼진 칸에 그 값(기준 줄의 바뀐 뒤)을 보인다(열의 꺼진 칸도 같이 — 「직접」 으로 바꾸면 그 값에서 시작)
  put(l2, fl2.value);
  q(".olp-e-text").title = `글 시작(mm) — 첫째 줄에서 레터 뒤 첫 글자의 자리.\n레터와 글 사이 ${olpMm(gap)}mm(레터 + 레터 뒤 빈칸)는 글자 폭이라 그대로입니다 — 글 시작을 바꾸면 레터 위치가 같이 움직입니다(레터 위치 = 글 시작 − ${olpMm(gap)})`;
  q(".olp-e-note").textContent = `레터 위치와 글 시작은 함께 움직입니다(사이 ${olpMm(gap)}mm = 레터·빈칸 글자 폭)`;
}

// ---------------------------------------------------------------- 자리 미리보기
function olpFetch(delay = 180) {
  clearTimeout(OLP.timer);
  OLP.timer = setTimeout(olpFetchNow, delay);
}

async function olpFetchNow() {
  const seq = ++OLP.seq, epoch = state.epoch, tpl = OLP.tpl, L = OLP.level;
  const sl = olfSlot(tpl, L), form = olpForm();
  OLP.loading = false; // 앞선 계산은 버린다(seq) — 아래에서 서버에 안 묻고 끝나는 길도 「계산하는 중」 에 머물지 않게
  if (!sl || sl.rooted || !sl.at || !sl.to) { OLP.pv = { error: "이 레벨은 자리(레터 위치·둘째 줄)가 없습니다 — 괄호 줄이거나 대표 줄의 자리를 못 잽니다", none: true }; olpRender(); return; }
  if (!form || form.hidden) { OLP.pv = { idle: true }; olpRender(); return; }
  const b = olfBody(sl, form);
  if (b.error) { OLP.pv = { error: b.error }; olpRender(); return; }
  if (b.body.letterMm != null && b.body.letterMm < 0) { // 글 시작을 레터·빈칸 폭보다 작게 적었다(레터 위치 = 글 시작 − 그 폭) — 서버에 묻기 전에 까닭을
    OLP.pv = { error: `글 시작이 레터와 글 사이 폭(${olpMm(olpGap(sl))}mm)보다 작습니다 — 레터 위치가 본문 왼끝(0)보다 왼쪽이 됩니다` };
    olpRender();
    return;
  }
  OLP.loading = true;
  olpRender();
  try {
    const r = await api(`/api/docs/${state.id}/outline/slots/${encodeURIComponent(tpl)}/${L}/preview`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b.body) });
    if (seq !== OLP.seq || epoch !== state.epoch) return;
    OLP.pv = { data: r, body: b.body };
  } catch (e) {
    if (seq !== OLP.seq || epoch !== state.epoch) return;
    OLP.pv = { error: e.message };
  } finally {
    if (seq === OLP.seq) OLP.loading = false;
  }
  olpRender();
}

function olpSplit(text) { // 줄 글 → {lead, tok, gap, body} — 첫머리 공백 · 레터(첫 낱말) · 레터 뒤 공백 · 본문(앞 공백을 살린다 — oneLine 은 다듬어 버림)
  const flat = (text || "").replace(/[\n\r\u2028]/g, " ");
  const m = /^([ \u00a0\u3000\t]*)(\S*)([ \u00a0\u3000\t]*)([\s\S]*)$/.exec(flat) || [];
  return { lead: m[1] || "", tok: m[2] || "", gap: m[3] || "", body: m[4] || "" };
}

function olpFigure(b, a, sample) { // 대표 줄 그림 — mm 자 위에 지금 · 바뀐 뒤 두 줄(첫 줄 = 레터·글, 둘째 줄), 바뀐 자리는 지금 자리를 점선으로
  const hi = Math.max(...OLP_KEYS3.flatMap(([k]) => [b[k] || 0, a[k] || 0]));
  const span = Math.max(30, Math.ceil((hi + 14) / 5) * 5);
  const pct = (mm) => `${Math.max(0, Math.min(100, (mm / span) * 100))}%`;
  const fig = el("div", "olp-fig");
  fig.setAttribute("role", "img");
  fig.setAttribute("aria-label", `대표 줄 자리 — 지금 ${OLP_KEYS3.map(([k, t]) => `${t} ${olpMm(b[k])}`).join(" · ")}mm, 바뀐 뒤 ${OLP_KEYS3.map(([k, t]) => `${t} ${olpMm(a[k])}`).join(" · ")}mm`);
  const ruler = el("div", "olp-ruler");
  for (let mm = 0; mm <= span; mm += 1) {
    const t = el("span", `olp-tick${mm % 5 ? "" : " major"}`);
    t.style.left = pct(mm);
    if (!(mm % 5)) t.append(el("b", null, String(mm)));
    ruler.append(t);
  }
  ruler.append(el("span", "olp-unit", "mm"));
  fig.append(ruler);
  const cut = Math.max(4, Math.round(sample.body.length / 2));
  for (const [label, v, cls] of [["지금", b, "now"], ["바뀐 뒤", a, "next"]]) {
    const row = el("div", `olp-prow ${cls}`);
    row.append(el("span", "olp-plab", label));
    const box = el("div", "olp-pbox");
    const seg = (k, text, line) => { const s = el("span", `olp-seg k-${k} l${line}`, text); s.style.left = pct(v[k]); return s; };
    box.append(seg("letterMm", sample.tok || "●", 1), seg("textMm", sample.body.slice(0, cut) || "가나다라마바사", 1), seg("line2Mm", sample.body.slice(cut) || "아자차카타파하", 2));
    if (cls === "next") {
      for (const [k] of OLP_KEYS3) {
        if (olpSame(b[k], v[k])) continue;
        const g = el("span", `olp-ghost k-${k}`);
        g.style.left = pct(b[k]);
        box.append(g);
      }
    }
    row.append(box);
    fig.append(row);
  }
  const leg = el("div", "olp-legend");
  for (const [k, t] of OLP_KEYS3) leg.append(el("span", `olp-key k-${k}`, t));
  leg.append(el("span", "olp-key ghost", "점선 = 지금 자리"), el("span", "muted", `본문 왼끝(0)에서 ${span}mm 까지만 크게`));
  fig.append(leg);
  return fig;
}

function olpFirst(v) { return v == null ? "–" : v < -0.04 ? `내어쓰기 ${olpMm(-v)}` : v > 0.04 ? `들여쓰기 ${olpMm(v)}` : "0"; }

function olpValTable(b, a) { // 항목 | 지금 | 바뀐 뒤 | 차
  const t = el("table", "olp-vals");
  const hr = el("tr");
  for (const h of ["", "지금", "바뀐 뒤", "차"]) hr.append(el("th", null, h));
  t.append(el("thead"));
  t.tHead.append(hr);
  const tb = el("tbody");
  const rows = [...OLP_KEYS3, ["leftMm", "왼쪽 여백"], ["firstMm", "첫 줄"]];
  for (const [k, name] of rows) {
    const same = olpSame(b[k], a[k]);
    const tr = el("tr", same ? "same" : "chg");
    const show = k === "firstMm" ? olpFirst : olpMm;
    tr.append(el("th", null, name), el("td", null, show(b[k])), el("td", "to", show(a[k])), el("td", "d", same ? "같음" : olpDelta(b[k], a[k])));
    tb.append(tr);
  }
  t.append(tb);
  return t;
}

function olpGroups(d) { // 줄 묶음 — 지금 자리가 같은 줄끼리 · 바뀌는 값은 「지금 → 바뀐 뒤」
  const t = el("table", "olp-grp");
  const hr = el("tr");
  for (const h of ["줄", ...OLP_KEYS3.map((x) => x[1]), "줄 보기"]) hr.append(el("th", null, h));
  t.append(el("thead"));
  t.tHead.append(hr);
  const tb = el("tbody");
  const SHOW = 12;
  for (const g of d.groups.slice(0, SHOW)) {
    const tr = el("tr", g.changed ? "chg" : "same");
    tr.append(el("td", "n", `×${nf(g.count)}`));
    for (const [k] of OLP_KEYS3) {
      const same = olpSame(g.before[k], g.after[k]);
      const td = el("td", same ? "v" : "v diff", same ? olpMm(g.before[k]) : `${olpMm(g.before[k])} → ${olpMm(g.after[k])}`);
      tr.append(td);
    }
    const cell = el("td", "who");
    if (g.paras.length) cell.append(headsParaLink(g.paras[0], olmText(g.paras[0]), 18));
    if (g.count > 1) {
      const det = el("details", "olp-more");
      det.append(el("summary", null, `${nf(g.count)}줄`));
      const box = el("div", "olp-plist");
      for (const pid of g.paras) box.append(headsParaLink(pid, olmText(pid), 26));
      if (g.more) box.append(el("span", "muted", `외 ${nf(g.more)}줄`));
      det.append(box);
      cell.append(det);
    }
    if (!g.changed) cell.prepend(el("span", "hb", "그대로"));
    tr.append(cell);
    tb.append(tr);
  }
  t.append(tb);
  const wrap = el("div", "olp-scroll");
  wrap.append(t);
  if (d.groups.length > SHOW) {
    const rest = d.groups.slice(SHOW);
    wrap.append(el("p", "muted olp-note", `외 ${nf(rest.length)}묶음 ${nf(rest.reduce((s, g) => s + g.count, 0))}줄`));
  }
  return wrap;
}

function olpPos(body, foot) {
  const sl = olfSlot(OLP.tpl, OLP.level);
  const pv = OLP.pv;
  if (!pv || (OLP.loading && !pv.data)) { body.append(el("p", "muted", "바뀐 뒤를 계산하는 중…")); return; }
  if (pv.idle) {
    const row = olpRowEl();
    body.append(el("p", "olp-note", row ? "「템플릿 관계」 열의 「자리 수정」 이 접혀 있습니다 — 펴고 레터·둘째 줄 값을 바꾸면 여기에 지금 → 바뀐 뒤가 보입니다."
      : "「템플릿 관계」 열에서 이 템플릿을 펴고 그 레벨의 「자리 수정」 을 누르면 여기에 지금 → 바뀐 뒤가 보입니다."));
    if (row) foot.append(hBtn("자리 수정 펴기", () => olpTab("pos"), { cls: "btn sm" }));
    if (sl && sl.at) body.append(olpFigure(sl.at, sl.at, olpSplit(olmText(sl.rep || ""))));
    return;
  }
  if (pv.error && !pv.data) {
    body.append(el("p", "olp-err", pv.error));
    if (sl && sl.at && !pv.none) body.append(olpFigure(sl.at, sl.at, olpSplit(olmText(sl.rep || ""))));
    return;
  }
  const d = pv.data;
  const ref = d.rep || d.slot;
  const head = el("div", "olp-sum");
  head.append(el("span", d.changed ? "olp-big chg" : "olp-big", d.changed ? `${nf(d.changed)}줄이 바뀝니다` : "바뀌는 줄 없음"),
    el("span", "muted", `이 레벨 ${nf(d.lines)}줄${d.same ? ` · 그대로 ${nf(d.same)}` : ""}${d.skipped ? ` · 자리 못 잼·괄호 줄 ${nf(d.skipped)}` : ""}`));
  if (OLP.loading) head.append(el("span", "muted", "· 다시 계산 중…"));
  body.append(head);
  if (d.error) body.append(el("p", "olp-err", d.error));
  const rule = el("p", "olp-note muted");
  const b = pv.body || {};
  rule.textContent = `규칙: 레터 위치 ${b.letterMm != null ? `${olpMm(b.letterMm)}mm 로 옮김` : "줄마다 제 자리 그대로"} · 둘째 줄 ${b.line2 === "mm" ? `직접 ${olpMm(b.mm)}mm` : OLF_RULE[b.line2] || b.line2}`;
  body.append(rule);
  if (ref) {
    const cap = el("div", "olp-cap");
    cap.append(el("b", null, d.rep ? "대표 줄" : "새 줄(대표 서식)"));
    if (d.rep) cap.append(" ", headsParaLink(d.rep.para, olmText(d.rep.para), 40, "이 레벨의 대표 줄"));
    body.append(cap, olpFigure(ref.before, ref.after, olpSplit(olmText(d.rep ? d.rep.para : sl && sl.rep || ""))), olpValTable(ref.before, ref.after));
  }
  if (d.groups.length) {
    const cap = el("div", "olp-cap");
    cap.append(el("b", null, "줄 묶음"), el("span", "muted", ` — 지금 자리가 같은 줄끼리(${nf(d.groups.length)}묶음)`));
    body.append(cap, olpGroups(d));
  }
  const apply = olpForm() ? olpForm().querySelector(".olf-apply") : null;
  const go = hBtn(d.changed ? `적용 — ${nf(d.changed)}줄` : "적용", () => { if (apply) apply.click(); },
    { title: "위 칸의 값(= 열의 「자리 수정」 줄) 그대로 이 레벨 줄 모두에 적용 — 「실행 취소」 로 되돌립니다", cls: "btn sm primary", disabled: !apply || !d.changed || state.busy });
  foot.append(go, el("span", "muted", "값만 바꿔서는 본문이 안 바뀝니다 — 「적용」 을 눌러야 바뀝니다 · 위 칸 = 「템플릿 관계」 열의 고치기 줄(같은 값)"));
}

// ---------------------------------------------------------------- 서식 비교
function olpCat(k) { return ["lead", "letter", "gap"].includes(k) ? "레터" : k.startsWith("L.") ? "레터 글자" : OLP_PARA.has(k) ? "문단" : "본문 글자"; }

function olpKeys(v) { // 서버가 준 차례 [[키, 이름]…] — 옛 서버면 갈래의 look 키(이름은 다른 값 목록에서)
  if (OLM.keys && OLM.keys.length) return OLM.keys;
  const names = new Map();
  for (const g of v.groups) for (const x of g.diff || []) names.set(x[0], x[1]);
  return Object.keys((v.groups[0] || {}).look || {}).map((k) => [k, names.get(k) || k]);
}

function olpSample(g) { // 갈래의 견본 글 — 레터는 레터 글자 모양, 본문은 본문 글자 모양으로(크기는 화면에 맞게 줄임) · 앞 여백만큼 들임
  const pid = g.paras[0], raw = g.raw || {};
  const sp = olpSplit(olmText(pid));
  const b = el("button", "olp-samp");
  b.type = "button";
  b.title = `문서에서 그 줄로 · ${pid}\n${short(olmText(pid), 80)}`;
  b.onclick = () => headsGo(pid);
  const style = (e, p) => {
    const f = raw[p + "font"];
    if (f) e.style.fontFamily = `"${f}", "Malgun Gothic", sans-serif`;
    const sz = raw[p + "sizePt"];
    if (sz) e.style.fontSize = `${Math.max(10, Math.min(20, sz * 1.2))}px`;
    if (raw[p + "bold"]) e.style.fontWeight = "700";
    if (raw[p + "italic"]) e.style.fontStyle = "italic";
    if (raw[p + "underline"]) e.style.textDecoration = "underline";
    if (raw[p + "color"] && raw[p + "color"] !== "#000000") e.style.color = raw[p + "color"];
  };
  const let_ = el("span", "olp-s-let", (raw.lead != null ? raw.lead : sp.lead) + sp.tok);
  const txt = el("span", "olp-s-txt", (raw.gap != null ? raw.gap : sp.gap) + sp.body.slice(0, 40));
  style(let_, "L.");
  style(txt, "");
  if (raw.line1Mm) b.style.paddingLeft = `${Math.min(40, Math.max(0, raw.line1Mm) * 1.5) + 4}px`;
  b.append(let_, txt);
  return b;
}

function olpCmp(body, foot) {
  const v = olmFresh() ? olmSlotData(OLP.tpl, OLP.level) : null;
  if (!v) {
    body.append(el("p", "muted", olmFresh() ? "이 레벨의 서식 정보가 없습니다" : "서식 읽는 중…"));
    if (!olmFresh()) olmLoad().then((x) => { if (x && OLP.tab === "cmp") olpRender(); });
    return;
  }
  const groups = v.groups, n = groups.length, rep = groups.find((g) => g.rep) || null, base = rep || groups[0];
  const keys = olpKeys(v);
  const val = (g, k) => (g.look && g.look[k] != null ? g.look[k] : "—");
  const diffKeys = keys.filter(([k]) => groups.some((g) => val(g, k) !== val(base, k)));
  const cols = OLP.showAll || n < 2 ? keys : diffKeys;
  const head = el("div", "olp-sum");
  head.append(el("span", n > 1 ? "olp-big chg" : "olp-big", n > 1 ? `서식 ${n}가지` : "서식 1가지 — 모두 같음"),
    el("span", "muted", `이 레벨 ${nf(v.total)}줄${n > 1 ? ` · 다른 항목 ${diffKeys.length}개` : ""} · ${rep ? "기준 = 대표" : "대표 없음 — 첫 서식과 견줌"}`));
  body.append(head);
  if (n > 1) {
    const lab = el("label", "olp-chk");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = OLP.showAll;
    cb.onchange = () => { OLP.showAll = cb.checked; olpRender(); };
    lab.append(cb, " 같은 값도 보기");
    body.append(lab);
  }
  const t = el("table", "olp-cmp");
  const thead = el("thead");
  const cat = el("tr", "olp-cat"), names = el("tr");
  cat.append(el("th", "olp-gh", ""));
  names.append(el("th", "olp-gh", "서식 · 견본(누르면 문서로)"));
  let last = null, span = null;
  for (const [k, name] of cols) {
    const c = olpCat(k);
    if (c !== last) { span = el("th", "olp-catname", c); span.colSpan = 1; cat.append(span); last = c; } else span.colSpan += 1;
    const th = el("th", null, k.startsWith("L.") ? name.replace(/^레터 /, "") : name);
    th.title = name;
    names.append(th);
  }
  cat.append(el("th"));
  names.append(el("th", null, ""));
  thead.append(cat, names);
  t.append(thead);
  const tb = el("tbody");
  for (const g of groups) {
    const tr = el("tr", g.rep ? "rep" : "");
    const th = el("th", "olp-gh");
    const tag = el("div", "olp-gtag");
    if (g.rep) tag.append(el("span", "hb olm-badge", "대표"));
    else tag.append(hBtn("대표로", () => olmSetRep(OLP.tpl, OLP.level, g.paras[0]), { title: `이 서식의 첫 줄(${g.paras[0]})을 이 레벨의 대표로 — 문서는 안 바뀝니다`, cls: "btn sm olp-mini" }));
    tag.append(el("span", "olp-n", `×${nf(g.count)}`));
    th.append(tag, olpSample(g));
    tr.append(th);
    for (const [k] of cols) {
      const same = val(g, k) === val(base, k);
      tr.append(el("td", g === base ? "base" : same ? "same" : "diff", val(g, k)));
    }
    const act = el("td", "act");
    if (!g.rep && rep) {
      act.append(hBtn("맞추기", () => olmMatch(OLP.tpl, OLP.level, g.count, [...g.paras]),
        { title: `이 서식의 줄 ${nf(g.count)}개를 대표 모양으로 — 「실행 취소」 로 되돌립니다`, cls: "btn sm olp-mini" }));
    }
    tr.append(act);
    tb.append(tr);
  }
  t.append(tb);
  const wrap = el("div", "olp-scroll x");
  wrap.append(t);
  body.append(wrap);
  if (rep && v.others) {
    foot.append(hBtn(`대표에 맞추기(${nf(v.others)}줄)`, () => olmMatch(OLP.tpl, OLP.level, v.others),
      { title: "대표와 서식이 다른 이 레벨 줄 모두를 대표 모양으로 — 「실행 취소」 로 되돌립니다", cls: "btn sm primary", disabled: state.busy }));
  }
  foot.append(el("span", "muted", n > 1 ? "주황 = 대표와 다른 값 · 흐림 = 대표와 같음" : "이 레벨 줄은 모두 같은 서식입니다"));
}

// ---------------------------------------------------------------- 그리기
function olpRender() {
  const w = $("olpWin");
  if (!w || w.hidden) return;
  const t = olmTpl(OLP.tpl), sl = olfSlot(OLP.tpl, OLP.level);
  const os = t && t.slots ? t.slots[String(OLP.level)] : null;
  $("olpTitle").textContent = `T${t ? t.no : OLP.tpl} L${OLP.level} 「${(os && os.letter) || (sl && sl.letter) || "?"}」${os ? ` ×${nf(os.lines)}` : ""}`;
  const hasPos = !!(sl && !sl.rooted && sl.at && sl.to);
  for (const b of w.querySelectorAll(".olp-tab")) {
    b.setAttribute("aria-selected", String(b.dataset.tab === OLP.tab));
    b.disabled = b.dataset.tab === "pos" && !hasPos;
    if (b.disabled) b.title = "이 레벨은 자리(레터 위치·둘째 줄)가 없습니다 — 괄호 줄";
  }
  const body = w.querySelector(".olp-body"), foot = w.querySelector(".olp-foot");
  const top = body.scrollTop;
  body.replaceChildren();
  foot.replaceChildren();
  if (OLP.tab === "pos" && hasPos) olpPos(body, foot);
  else { OLP.tab = "cmp"; w.querySelector('.olp-tab[data-tab="cmp"]').setAttribute("aria-selected", "true"); olpCmp(body, foot); }
  foot.hidden = !foot.childNodes.length;
  body.scrollTop = top;
  olpEditSync();
}

(() => { // 「템플릿 관계」 열을 닫거나 다른 열로 바꾸면 창도 닫는다(창은 그 열의 레벨에 매여 있다)
  const col = $("headsDlg");
  if (!col || typeof MutationObserver !== "function") return;
  new MutationObserver(() => { if (col.hidden || col.dataset.kind !== "templates") olpClose(); }).observe(col, { attributes: true, attributeFilter: ["hidden", "data-kind"] });
})();
