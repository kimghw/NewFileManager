"use strict";
// 양식 정보(spec_헤딩_추출 ② §12) — 양식마다 md 하나. 일반 지침(「지침」 — 모든 문서 공통)과 따로 두고, 그 양식 문서의 LLM 호출에만 덧붙는다.
// 2열 보기 kind "form": 이 문서의 양식 고르기(자동 · 양식 키 · 양식 없음) + 그 양식 정보 글 편집(없으면 이 문서로 새로 만들 뼈대) + 저장.
// app.js 가 주는 것: state·heads(dlg·view·form)·$·el·api·toast·hBtn·headsDlg·headsShow·H_JSON. app.js 가 부르는 것(typeof 검사 뒤):
// headsFormBtn(1단계 카드 단추 줄) · headsFormLeave(headsColClose — 저장 안 한 글 묻기). 서버 짝은 app/heading_forms_api.py · app/heading_forms.py.
// index.html 이 app.js 다음에 읽는다. 새 CSS 없음(지침 편집의 .hd-guide·.hd-field·.hd-msg 를 그대로 씀).
const FORM_AUTO = "@auto"; // 고르기 목록의 「자동」 값 — 양식 키에는 @ 를 못 쓴다
const FORM_HOW = { manual: "직접 고름", sha256: "올린 원본과 일치", name: "파일 이름과 일치" };
const formDocUrl = () => `/api/docs/${encodeURIComponent(state.id)}/headings/form`;
const formUrl = (key) => `/api/headings/forms/${encodeURIComponent(key)}`;

function headsFormBtn(r) { // 1단계 카드 단추 줄 — 이 문서에 맞은 양식 이름. 2단계 LLM 결과가 지금 양식 정보로 만든 것이 아니면 * 표
  const f = r.form, s2 = r.stage2;
  const ran = !!(s2 && s2.llm && s2.llm.requested && !s2.llm.fallback);
  const used = ran ? ((s2.meta && s2.meta.guides) || {}).form || null : null;
  const stale = ran && used !== (f ? f.sha1 : null);
  return hBtn(`양식 정보 · ${f ? f.name : "없음"}${stale ? " *" : ""}`, () => headsForm(), {
    title: (f ? `이 문서의 양식: ${f.name}(${FORM_HOW[f.how] || f.how}) — 이 양식에만 해당하는 내용을 LLM 호출에 덧붙입니다`
      : "이 문서에 맞는 양식 정보가 없습니다 — 눌러서 만들거나 고릅니다")
      + (stale ? "\n* 2단계 결과(LLM)는 지금 양식 정보로 만든 것이 아닙니다 — 다시 만들면 반영됩니다" : ""),
  });
}

function headsFormDirty() { // 고친 글이 있나 — 새 양식은 서버가 준 뼈대와 견준다(손대지 않은 뼈대는 닫아도 안 묻는다)
  const F = heads.form;
  return !!(heads.dlg === "form" && F && F.cur && F.E.ta.value !== (F.cur.isNew ? F.cur.draft : F.cur.text));
}
const headsFormLeave = () => !headsFormDirty() || confirm("저장하지 않은 양식 정보 글이 있습니다. 버릴까요?");
const formCanSave = () => !!(heads.form && heads.form.cur && (heads.form.cur.isNew || headsFormDirty())); // 새 양식은 뼈대 그대로도 저장할 수 있다

async function headsForm() {
  if (!state.id || (heads.dlg === "form" && !headsFormLeave())) return;
  const { tools, body, foot } = headsDlg("form", "양식 정보", "이 양식에만 해당하는 내용(일반 기준은 「지침」)");
  const sel = el("select"), selLab = el("label", "hd-field"), key = el("input"), keyLab = el("label", "hd-field");
  sel.setAttribute("aria-label", "이 문서의 양식");
  selLab.append(el("span", null, "이 문서의 양식"), sel);
  key.type = "text";
  key.maxLength = 60;
  key.spellcheck = false;
  key.title = "양식 키 = 파일 이름(forms/<키>.md) — 한글·영문·숫자·밑줄로 시작, 빈칸·괄호·점·가운뎃점·붙임표까지 60자";
  keyLab.append(el("span", null, "새 양식 이름"), key);
  keyLab.hidden = true;
  const fresh = hBtn("새 양식 정보", () => { if (headsFormLeave()) formNew(); }, { title: "이 문서로 새 양식 정보를 만듭니다(파일 이름·올린 원본으로 이 문서에 맞춰 둠)" });
  tools.append(selLab, keyLab, fresh);
  const msg = el("div", "hd-msg"), ta = el("textarea"), wrap = el("div", "hd-guide");
  ta.spellcheck = false;
  ta.setAttribute("aria-label", "양식 정보 글");
  ta.title = "맨 위 json 블록 = 이 양식으로 볼 문서의 조건(파일 이름 꼴 · 올린 원본 sha256). 그 아래 글이 LLM 에 들어갑니다(<!-- 주석 --> 은 안 들어감)";
  wrap.append(msg, ta);
  body.append(wrap);
  const save = hBtn("저장", () => formSave(), { cls: "btn sm primary", disabled: true });
  const info = el("span", "muted");
  foot.append(save, el("span", "spacer"), info);
  const F = heads.form = { E: { sel, key, keyLab, msg, ta, save, info, fresh }, view: null, cur: null };
  ta.oninput = () => { save.disabled = !formCanSave(); };
  sel.onchange = () => formPick(F);
  await formLoad();
}

async function formLoad(pick = null) { // 이 문서의 양식 보기 → 고르기 목록 + (pick | 맞은 양식 | 새 뼈대) 를 편집 칸에
  const F = heads.form;
  if (!F || heads.dlg !== "form") return;
  const E = F.E, epoch = state.epoch;
  E.msg.textContent = "";
  let v;
  try { v = await api(formDocUrl()); }
  catch (e) { if (heads.form === F) E.msg.textContent = `양식 정보를 읽지 못했습니다: ${e.message}`; return; }
  if (heads.form !== F || epoch !== state.epoch) return;
  F.view = v;
  E.sel.textContent = "";
  E.sel.append(new Option(v.choice == null && v.form ? `자동 — ${v.form.name}(${FORM_HOW[v.form.how] || v.form.how})` : "자동(파일 이름·올린 원본으로 찾기)", FORM_AUTO));
  for (const f of v.forms) E.sel.append(new Option(f.name === f.key ? f.key : `${f.name} (${f.key})`, f.key));
  E.sel.append(new Option("양식 없음(이 문서에는 안 씀)", ""));
  E.sel.value = v.choice == null || ![...E.sel.options].some((o) => o.value === v.choice) ? FORM_AUTO : v.choice;
  E.fresh.disabled = !v.dir;
  const key = pick || (v.form && v.form.key);
  if (key) await formOpen(key);
  else if (v.choice === "") formShow(null, "이 문서에는 양식 정보를 쓰지 않습니다(양식 없음으로 고름).");
  else if (!v.dir) formShow(null, "양식 정보 폴더가 꺼져 있습니다(NFM_FORMS).");
  else formNew();
}

function formShow(cur, note = "") { // cur = {key, text, sha1, isNew, path} | null(편집할 것 없음)
  const F = heads.form;
  if (!F) return;
  const E = F.E;
  F.cur = cur;
  E.ta.hidden = !cur;
  E.keyLab.hidden = !(cur && cur.isNew);
  if (cur) {
    E.ta.value = cur.isNew ? cur.draft : cur.text;
    if (cur.isNew) E.key.value = cur.key;
  }
  const f = F.view && F.view.form, tail = (p) => String(p || "").split(/[\\/]/).slice(-2).join("\\"); // 발치에는 「forms\키.md」 만 — 온 경로는 도움말
  E.info.textContent = !cur ? "" : cur.isNew ? `아직 없음 — 저장하면 ${tail(`${F.view.dir}\\${cur.key}.md`)}` : tail(cur.path) + (f && f.key === cur.key ? ` · ${FORM_HOW[f.how] || f.how}` : "");
  E.info.title = !cur ? "" : cur.isNew ? `${F.view.dir}\\${cur.key}.md` : cur.path;
  E.msg.classList.toggle("note", !!note);
  E.msg.textContent = note;
  E.save.disabled = !formCanSave();
}

async function formOpen(key) {
  const F = heads.form;
  let g;
  try { g = await api(formUrl(key)); }
  catch (e) { if (heads.form === F) F.E.msg.textContent = `양식 정보를 읽지 못했습니다: ${e.message}`; return; }
  if (heads.form !== F) return;
  formShow({ key: g.key, text: g.text, sha1: g.sha1, isNew: false, path: g.path }, g.broken ? `조건 블록 오류 — 이 양식은 자동으로 맞춰지지 않습니다: ${g.broken}` : "");
  if (g.broken) F.E.msg.classList.remove("note");
}

function formNew() { // 이 문서로 새 양식 정보 — 서버가 준 뼈대(키·조건 블록)를 편집 칸에. 저장해야 파일이 생긴다
  const F = heads.form;
  if (!F || !F.view || !F.view.dir) return;
  const sug = F.view.suggest, taken = new Set(F.view.forms.map((f) => f.key));
  let key = sug.key, text = sug.text;
  for (let n = 2; taken.has(key); n += 1) key = `${sug.key}_${n}`;
  if (key !== sug.key) text = text.split(`"name": "${sug.key}"`).join(`"name": "${key}"`);
  formShow({ key, text: "", draft: text, sha1: "", isNew: true }, "새 양식 정보 — 이 문서에 맞는 것이 아직 없습니다. 내용을 적고 저장하세요.");
}

async function formPick(F) { // 이 문서의 양식 고르기 — 자동 · 양식 키 · 양식 없음
  const E = F.E, v = F.view;
  const before = !v || v.choice == null ? FORM_AUTO : v.choice;
  if (!headsFormLeave()) { E.sel.value = before; return; }
  const val = E.sel.value;
  try {
    await api(formDocUrl(), { method: "PUT", headers: H_JSON, body: JSON.stringify({ form: val === FORM_AUTO ? null : val }) });
  } catch (e) {
    if (heads.form === F) { E.sel.value = before; E.msg.classList.remove("note"); E.msg.textContent = `양식을 고르지 못했습니다: ${e.message}`; }
    return;
  }
  if (heads.form !== F) return;
  await formLoad();
  headsShow(); // 1단계 카드의 양식 이름
  if (typeof divFormChanged === "function") divFormChanged(); // 「구분 기준」 탭 양식 줄의 단추 이름(spec_구분_기준 ② §16)
}

async function formSave() {
  const F = heads.form, cur = F && F.cur;
  if (!cur) return;
  const E = F.E, key = cur.isNew ? E.key.value.trim() : cur.key;
  E.msg.classList.remove("note");
  E.msg.textContent = "";
  if (!key) { E.msg.textContent = "새 양식 이름을 적으세요."; return; }
  E.save.disabled = true;
  try {
    const r = await api(formUrl(key), { method: "PUT", headers: H_JSON, body: JSON.stringify({ text: E.ta.value, sha1: cur.sha1, reason: "화면" }) });
    if (heads.form !== F) return;
    if (cur.isNew) { // 새로 만든 양식이 이 문서에 맞아야 한다 — 「양식 없음」 으로 고른 문서이거나 조건이 같은 다른 양식이 먼저 맞으면 이 양식을 고른 것으로
      try {
        const v2 = await api(formDocUrl());
        if (!v2.form || v2.form.key !== r.key) await api(formDocUrl(), { method: "PUT", headers: H_JSON, body: JSON.stringify({ form: r.key }) });
      } catch { /* 저장은 됨 — 목록에서 고르면 된다 */ }
      if (heads.form !== F) return;
    }
    Object.assign(cur, { key: r.key, text: r.text, sha1: r.sha1, path: r.path, isNew: false }); // 아래 다시 읽기가 실패해도 저장한 판이 기준
    toast(`양식 정보 「${r.name}」을(를) 저장했습니다 — 다음 LLM 실행부터 씁니다`);
    await formLoad(r.key);
    headsShow();
    if (typeof divFormChanged === "function") divFormChanged();
  } catch (e) {
    if (heads.form !== F) return;
    if (e.status === 409 && cur.isNew) E.msg.textContent = `「${key}」 양식 정보가 이미 있습니다 — 이름을 바꾸거나 위 목록에서 그 양식을 고르세요.`;
    else if (e.status === 409) {
      E.msg.textContent = "다른 곳(편집기·다른 창)에서 이 양식 정보를 먼저 고쳤습니다 — 새 판을 읽었습니다(내 글은 그대로). 그 위에 저장하려면 「저장」을 한 번 더 누르세요.";
      try {
        const g = await api(formUrl(key));
        if (heads.form === F && F.cur === cur) { cur.text = g.text; cur.sha1 = g.sha1; }
      } catch (e2) { // 파일이 밖에서 지워짐(404) — 기대 판을 「없음」 으로 두어 다음 저장이 다시 만든다
        if (e2.status === 404 && heads.form === F && F.cur === cur) {
          cur.text = "";
          cur.sha1 = "";
          E.msg.textContent = "이 양식 정보 파일이 밖에서 지워졌습니다 — 「저장」을 한 번 더 누르면 지금 글로 다시 만듭니다.";
        }
      }
    } else E.msg.textContent = `저장하지 못했습니다: ${e.message}`;
    E.save.disabled = !formCanSave();
  }
}
