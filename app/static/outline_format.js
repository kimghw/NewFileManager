// 개요 줄 자리(spec_hwpx_웹편집 ② §8-1) — 「템플릿 관계」 열의 레벨(줄)마다 자리 한 줄: 레터 위치 · 글 시작 · 둘째 줄(mm, 본문 왼끝에서) + 고치기.
// 자료 = GET /api/docs/{id}/outline 의 templates[tid].slots[레벨] {letter, lines, rooted, pos(규칙), at(대표 서식의 자리), to(규칙을 건 뒤 = 새 줄의 자리)} — app.js heads.outline.
// 고치면 PUT …/outline/slots/{tid}/{레벨} 이 그 레벨 줄 모두의 문단 여백(왼쪽·첫 줄)을 맞추고(구조 편집 1회 — 실행 취소), 화면은 바뀐 문단의 여백만 다시 잡는다.
// app.js 다음에 읽힌다(el·hBtn·api·toast·heads·state·indentLook·paginate …). 훅: app.js headsTplView 의 levels() 가 olfRow(id, L) 을, outlineLoad 가 olfRefresh() 를 부른다.
const OLF_RULE = { text: "글 시작에 맞춤", mm: "직접", keep: "문단 서식 그대로" };
const olfMm = (v) => (v == null ? "–" : (Math.round(v * 10) / 10).toFixed(1));

function olfSlot(id, L) {
  const t = heads.outline && heads.outline.templates ? heads.outline.templates[String(id)] : null;
  return t && t.slots ? t.slots[String(L)] || null : null;
}

function olfRuleText(sl) { // 지금 규칙을 한마디로 — 사용자가 정하지 않았고 대표 문단이 제 첫 줄 값을 갖고 있으면 그 값을 따른다(문서가 정함)
  const pos = sl.pos || {};
  if (pos.set) return pos.line2 === "mm" ? `직접 ${olfMm(pos.mm)}mm` : OLF_RULE[pos.line2] || pos.line2;
  return sl.at && Math.abs(sl.at.firstMm || 0) > 0.02 ? "문서가 정한 값" : OLF_RULE.text;
}

function olfRow(id, L) { // 레벨 줄 아래 한 줄(자리가 없는 레벨 — 괄호 줄·대표 문단 없음 — 은 null)
  const sl = olfSlot(id, L);
  if (!sl || sl.rooted || !sl.at || !sl.to) return null;
  const row = el("div", "olf");
  row.dataset.tpl = id;
  row.dataset.level = L;
  const to = sl.to, set = !!(sl.pos && sl.pos.set);
  const sum = el("span", "olf-sum", `레터 ${olfMm(to.letterMm)} · 글 시작 ${olfMm(to.textMm)} · 둘째 줄 ${olfMm(to.line2Mm)}mm`);
  sum.title = "본문(칸) 왼끝에서 잰 자리 — 레터 위치 · 레터 뒤 첫 글자(글 시작) · 줄이 넘어갈 때 둘째 줄이 시작하는 자리.\n"
    + "따로 정하지 않으면 둘째 줄은 글 시작에 맞춥니다: 이 레벨 줄에 글을 쓰거나 Enter 로 새 줄을 만들 때 그 문단에 내어쓰기가 붙습니다(문서가 이미 준 들여쓰기·내어쓰기는 그대로).";
  const rule = el("span", `hb olf-rule${set ? " chg" : ""}`, olfRuleText(sl));
  rule.title = set ? "이 레벨에 정한 규칙 — 새 줄과 글을 고치는 줄에 걸립니다" : "기본 규칙(정한 것 없음)";
  const edit = hBtn("자리 수정", () => {
    form.hidden = !form.hidden;
    edit.setAttribute("aria-expanded", String(!form.hidden));
    if (typeof olpOpen === "function") { if (form.hidden) olpFormClosed(id, L); else olpOpen(id, L, "pos"); } // 지금 → 바뀐 뒤 미리보기 창(outline_preview.js)
  }, { title: `이 레벨 줄 ${nf(sl.lines)}개의 레터 위치·둘째 줄을 고칩니다 — 펼치면 옆에 미리보기 창(지금 → 바뀐 뒤)이 뜹니다`, cls: "btn sm olf-btn" });
  edit.setAttribute("aria-expanded", "false");
  const form = olfForm(id, L, sl);
  form.hidden = true;
  row.append(sum, rule, edit, form);
  return row;
}

function olfForm(id, L, sl) {
  const form = el("div", "olf-edit");
  const num = (value, label) => {
    const i = el("input");
    i.type = "number"; i.min = "0"; i.max = "300"; i.step = "0.1"; i.value = olfMm(value); i.setAttribute("aria-label", label); i.title = label;
    return i;
  };
  const letter = num(sl.to.letterMm, "레터 위치(mm) — 본문 왼끝에서 레터까지. 바꾸면 문단 왼쪽 여백이 움직입니다(앞 공백은 그대로)");
  letter.classList.add("olf-letter");
  const mode = el("select", "olf-mode");
  mode.setAttribute("aria-label", "둘째 줄 규칙");
  for (const [v, t] of Object.entries(OLF_RULE)) { const o = el("option", null, t); o.value = v; mode.append(o); }
  const pos = sl.pos || {};
  mode.value = pos.set ? pos.line2 : (Math.abs(sl.at.firstMm || 0) > 0.02 ? "keep" : "text");
  const line2 = num(sl.to.line2Mm, "둘째 줄 위치(mm) — 본문 왼끝에서");
  line2.classList.add("olf-l2");
  const changed = () => { if (typeof olpFormInput === "function") olpFormInput(id, L); }; // 미리보기 창(outline_preview.js)이 열려 있으면 바뀐 뒤를 다시
  const sync = () => { line2.disabled = mode.value !== "mm"; };
  mode.onchange = () => { sync(); changed(); };
  letter.oninput = changed;
  line2.oninput = changed;
  sync();
  const apply = hBtn(`적용(${nf(sl.lines)}줄)`, async () => {
    const b = olfBody(sl, form);
    if (b.error) { toast(b.error, true); return; }
    await olfApply(id, L, b.body);
  }, { title: "문서의 이 레벨 줄 모두에 적용 — 문단의 왼쪽 여백·첫 줄(내어쓰기)이 바뀝니다. 「실행 취소」 로 되돌립니다", cls: "btn sm primary olf-apply" });
  const lab = (t) => el("span", "olf-lab", t);
  form.append(lab("레터"), letter, lab("둘째 줄"), mode, line2, lab("mm"), apply);
  return form;
}

function olfBody(sl, form) { // 고치기 줄의 값 → PUT …/slots(·/preview) 몸 {body} | {error} — 적용과 미리보기 창이 같이 쓴다
  const pos = sl.pos || {};
  const mode = form.querySelector(".olf-mode").value;
  const lv = parseFloat(form.querySelector(".olf-letter").value), l2 = parseFloat(form.querySelector(".olf-l2").value);
  const body = { line2: mode };
  if (Number.isFinite(lv) && Math.abs(lv - sl.to.letterMm) >= 0.05) body.letterMm = lv; // 안 바꾼 레터 위치는 보내지 않는다(줄마다 제 자리 그대로)
  else if (pos.set && pos.letterMm != null) body.letterMm = pos.letterMm;
  if (mode === "mm") {
    if (!Number.isFinite(l2)) return { error: "둘째 줄 위치(mm)를 숫자로 적어 주세요" };
    body.mm = l2;
  }
  return { body };
}

async function olfApply(id, L, body) { // structOp 과 같은 차례: 대기 중 글 반영 → 서버 편집(표준 검사) → 바뀐 문단의 여백만 다시 → 쪽 다시 나눔
  if (state.busy || !state.id) return;
  const epoch = state.epoch;
  state.busy = true;
  busyMark(true); // app.js — #doc 에만, 0.4초 넘게 걸릴 때만(body 클래스는 문단 전부의 스타일을 다시 계산시킨다)
  refreshToolbar();
  try {
    await flushAll();
    if (state.failed.size) { toast("서버에 반영하지 못한 문단이 있어 먼저 다시 반영해야 합니다 — 「고친 문단」 탭", true); return; }
    const r = await api(`/api/docs/${state.id}/outline/slots/${encodeURIComponent(id)}/${L}`,
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (epoch !== state.epoch) return;
    state.localRev += 1;
    state.structRev = state.localRev;
    applyEditState(r);
    for (const [pid, f] of Object.entries(r.formats || {})) {
      const b = state.byId.get(pid), p = paraEl(pid);
      if (b) state.byId.set(pid, { ...b, format: f }); // 새 사전으로 — 같은 블록을 기준 블록(byIdOrig)도 가리킨다(되돌리기가 그것으로 다시 그림)
      if (p) { indentLook(p.style, f); p.classList.add("edited"); }
    }
    if (r.outline && !r.outline.off) heads.outline = r.outline;
    if (r.aligned) paginate(); // 줄 수가 바뀌어 쪽이 넘칠 수 있다(표시도 다시 그림)
    updateEdits();
    renderSummary(state.verify || {});
    olfRefresh();
    const t = heads.outline && heads.outline.templates[String(id)];
    toast(r.aligned ? `T${t ? t.no : id} L${L} 줄 ${nf(r.aligned)}개의 자리를 맞췄습니다 — 「실행 취소」 로 되돌립니다` : `T${t ? t.no : id} L${L} — 규칙을 저장했습니다(이미 그 자리라 바뀐 줄 없음)`);
    if (r.owpml && r.owpml.status === "warn") toast(`${STD()}: ${r.owpml.summary}`);
  } catch (e) {
    if (epoch !== state.epoch) return;
    if (e.status === 422 && e.body && e.body.owpml) state.owpml = { status: "fail", summary: e.message };
    toast(e.message, true);
  } finally {
    if (epoch === state.epoch) {
      state.busy = false;
      busyMark(false);
      refreshToolbar();
      refreshSaveState();
    }
  }
}

function olfRefresh() { // 오버레이를 다시 읽었거나 규칙을 바꾼 뒤 — 열려 있는 「템플릿 관계」 의 자리 줄을 새 값으로(펼쳐 둔 고치기 줄은 그대로 펼친 채)
  for (const old of document.querySelectorAll("#headsDlgBody .olf")) {
    const fresh = olfRow(old.dataset.tpl, +old.dataset.level);
    if (!fresh) { old.remove(); continue; }
    const was = old.querySelector(".olf-edit"), now = fresh.querySelector(".olf-edit");
    if (was && now && !was.hidden) { now.hidden = false; fresh.querySelector(".olf-btn").setAttribute("aria-expanded", "true"); }
    old.replaceWith(fresh);
  }
  olfCatchUp();
  if (typeof olpRefresh === "function") olpRefresh(); // 미리보기 창 — 새 자리로 다시
}

// 글을 고쳐 둔 개요 줄인데 둘째 줄이 아직 안 맞은 것(이 기능 전에 고친 줄) — 문서를 열어 오버레이를 읽었을 때 한 번 서버에 맞춤을 부탁한다(POST …/outline/align).
// 글 고침과 같은 길이라 실행 취소 묶음이 없고, 원래 글로 되돌리면 문단 모양도 원본으로 돌아간다. 문서마다 한 번만 묻는다.
let olfCaught = null;
function olfCatchUp() {
  const o = heads.outline;
  if (!o || !state.id || state.format !== "hwpx" || state.busy) return;
  const key = `${state.id}|${state.epoch}`;
  if (olfCaught === key) return;
  olfCaught = key;
  const todo = [...state.edited].filter((id) => {
    const ln = o.lines[id], b = state.byId.get(id), sl = ln ? olfSlot(ln.tpl, ln.level) : null;
    return ln && !isRooted(ln.role) && state.kinds[id] !== "format" && b && b.format && Math.abs(b.format.firstLineMm || 0) <= 0.02 && !(sl && sl.pos && sl.pos.line2 === "keep");
  });
  if (!todo.length) return;
  const epoch = state.epoch;
  api(`/api/docs/${state.id}/outline/align`, { method: "POST" }).then((r) => {
    if (epoch !== state.epoch) return;
    const ids = Object.keys(r.formats || {});
    if (!ids.length) return;
    if (r.rev != null) state.serverRev = r.rev;
    state.pristine = r.pristine;
    if (r.kinds) state.kinds = r.kinds;
    for (const pid of ids) {
      const b = state.byId.get(pid), p = paraEl(pid);
      if (b) state.byId.set(pid, { ...b, format: r.formats[pid] });
      if (p) indentLook(p.style, r.formats[pid]);
    }
    headsMarkStale();
    refreshSaveState();
    toast(`글을 고쳐 둔 개요 줄 ${nf(ids.length)}개의 둘째 줄을 글 시작에 맞췄습니다`);
  }).catch(() => { /* 옛 서버(끝점 없음)·일시 오류 — 다음에 그 줄의 글을 고치면 맞춰진다 */ });
}
