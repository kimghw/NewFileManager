"use strict";
// 템플릿 서식 정리 에이전트(spec_hwpx_웹편집 ② §8-4) — 사용자 2026-11-15 "에이전트 기능을 추가 해서 opus5.5 가 템플릿의 서식을 직접 조정해주는 기능을 추가해줘, 아이콘으로 넣어주고,
// 이 에이전트에게 정리를 시킬때 프롬프트/스킬을 먼저 저장하고, 사용자가 이를 수정할 수 있는 형식으로".
// 여는 곳: 템플릿 트리(「템플릿」 탭 · 「템플릿 관계」 열 — app.js tplTreeDraw)의 템플릿 줄마다 별 모양 아이콘(tplAgentIcon). 자리: 문서 옆 열(2열 kind "tplAgent" — 팝업 아님).
// 열의 차례: ① 대상(템플릿 · 개요 레벨 그림 · 레벨마다 서식 갈래 수) ② 스킬(저장해 둔 정리 기준 글 — 고르고 · 고치고 · 저장 · 새로 만들기 · 기본으로) ③ 이번 요청(없어도 됨)
//   → 「정리 계획 받기」(고친 스킬은 **먼저 저장하고** 부른다 — 에이전트는 저장된 글로만 돈다) → ④ 계획(레벨마다 대표 · 갈래 줄마다 고르기 「맞추기 / 그대로 / T1L3a 로」 + 까닭) → 「적용」(실행 취소 1).
//   「T1L3a 로」 = 서식이 일부러 다른 갈래를 서식 종속 템플릿으로 떼기(spec_hwpx_웹편집 ② §8-5 — 같은 이름을 고른 갈래끼리 한 템플릿 · 그 대표에 나머지를 맞춘다). TPA.choice = 「레벨|갈래」 → "match" | "keep" | "s:글자".
//   「계획을 받으면 바로 적용」 을 켜면 계획을 받자마자 적용한다(이 브라우저에 기억 — 기본 끔).
// 끝점: GET /api/outline/agent · GET/POST/PUT/DELETE /api/outline/agent/skills[/{key}] · POST /api/docs/{id}/outline/agent/{tpl}/plan(dry = 보낼 글만) ·
//   적용 = POST /api/docs/{id}/outline/templates/{tpl}/match(outline_match.js olmApplyTpl — 「템플릿 맞추기」 와 같은 끝점). LLM 은 갈래 id 가운데 고르기만 한다(서식 값을 만들지 않는다).
// app.js · outline_match.js 다음에 읽힌다(el·hBtn·hHelp·api·toast·heads·state·headsDlg·headsTplView·headsParaLink·flushAll·nf·short·olmTpl·olmLoad·olmFresh·olmSlotData·olmPic·olmKey·olmApplyTpl …).
const TPA_DIRECT_KEY = "nfm.tplAgentDirect", TPA_NEW = "+new";
const TPA = { epoch: null, info: null, infoErr: "", skill: null, drafts: {}, key: "tidy", tpl: null, request: "", plan: null, choice: new Map(), busy: null, started: 0, timer: null,
  err: "", prompt: null, arm: null, done: null };
const TPA_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
  + '<path d="M11 3l1.8 4.9L17.5 9.5l-4.7 1.7L11 16l-1.8-4.8L4.5 9.5l4.7-1.6L11 3z"/><path d="M18.5 14.5l.8 2.1 2.2.9-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.9.8-2.1z"/></svg>';
const tpaModel = (m) => (/^claude-opus-5-5/.test(m || "") ? "Opus 5.5" : /^claude-fable/.test(m || "") ? "Fable" : m || "모델 모름");
const tpaOn = () => { const c = $("headsDlg"); return !!c && !c.hidden && c.dataset.kind === "tplAgent"; };
const tpaDirect = () => { try { return localStorage.getItem(TPA_DIRECT_KEY) === "on"; } catch { return false; } };

function tplAgentIcon(id) { // 템플릿 줄의 아이콘 단추 — 개요 오버레이에 줄이 있는 템플릿만(그래프에만 있는 템플릿은 맞출 줄을 모른다)
  const t = olmTpl(id);
  if (!t || !t.lines) return null;
  const b = el("button", "icon tpl-agent");
  b.type = "button";
  b.innerHTML = TPA_ICON;
  b.setAttribute("aria-label", `T${t.no} 서식 정리 에이전트`);
  b.title = `서식 정리 에이전트 — Opus 5.5 가 T${t.no} 의 레벨마다 서식 갈래를 보고 대표와 맞출 줄을 정합니다\n저장해 둔 스킬(정리 기준 글)을 보고 고친 뒤 시킵니다 · 계획을 보고 고른 것만 적용(문서 옆 열)`;
  b.onclick = (e) => { e.stopPropagation(); tplAgentOpen(id); };
  return b;
}

function tpaReset() { // 다른 문서 — 계획·대상은 비우고 스킬 초안은 남긴다(스킬은 문서와 무관)
  clearInterval(TPA.timer);
  Object.assign(TPA, { epoch: state.epoch, tpl: null, plan: null, choice: new Map(), busy: null, err: "", prompt: null, arm: null, done: null, request: "" });
}

async function tplAgentOpen(id = null) {
  if (!state.id || state.format !== "hwpx" || !heads.outline) { toast("템플릿 서식 정리는 헤딩 추출 2단계 결과가 있는 HWPX 문서에서 씁니다"); return; }
  if (TPA.epoch !== state.epoch) tpaReset();
  if (id != null && String(id) !== String(TPA.tpl)) Object.assign(TPA, { tpl: String(id), plan: null, choice: new Map(), err: "", prompt: null, done: null });
  if (TPA.tpl == null || !olmTpl(TPA.tpl)) TPA.tpl = (tpaTemplates()[0] || {}).id || null;
  headsDlg("tplAgent", "템플릿 서식 정리", "");
  tplAgentDraw();
  if (!olmFresh()) olmLoad().then(() => tplAgentSync());
  const epoch = state.epoch;
  tpaStored(); // 받아 둔 계획(LLM 검증·보완 · 앞서 받은 것)이 있으면 다시 부르지 않고 그것을
  try {
    TPA.info = await api("/api/outline/agent");
    TPA.infoErr = "";
  } catch (e) {
    TPA.info = null;
    TPA.infoErr = e.status === 404 ? "서버가 옛 판이라 서식 정리 에이전트를 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요" : `에이전트 정보를 읽지 못했습니다: ${e.message}`;
  }
  if (epoch !== state.epoch || !tpaOn()) return;
  if (TPA.info && !TPA.info.skills.some((s) => s.key === TPA.key) && TPA.key !== TPA_NEW) TPA.key = (TPA.info.skills[0] || {}).key || "tidy";
  await tpaSkillLoad();
  if (epoch === state.epoch && tpaOn()) tplAgentDraw();
}

async function tpaSkillLoad() { // 고른 스킬의 글을 읽는다(새 스킬 초안은 서버에 없다)
  if (!TPA.info || TPA.key === TPA_NEW) { if (TPA.key === TPA_NEW) TPA.skill = null; return; }
  try { TPA.skill = await api(`/api/outline/agent/skills/${encodeURIComponent(TPA.key)}`); }
  catch (e) { TPA.skill = null; TPA.infoErr = `스킬을 읽지 못했습니다: ${e.message}`; }
}

function tpaTemplates() { // 정리할 수 있는 템플릿(오버레이에 줄이 있는 것) — 번호 순
  const o = heads.outline;
  if (!o || !o.templates) return [];
  return Object.entries(o.templates).filter(([, t]) => t.lines).map(([id, t]) => ({ id, t }))
    .sort((a, b) => String(a.t.no).localeCompare(String(b.t.no), "en", { numeric: true }));
}
function tpaCur() { // 지금 편집 칸의 스킬 글 {name, text, dirty, isNew}
  const d = TPA.drafts[TPA.key], s = TPA.skill, isNew = TPA.key === TPA_NEW;
  const name = d ? d.name : s ? s.name : "", text = d ? d.text : s ? s.text : "";
  return { name, text, isNew, dirty: isNew || (!!d && !!s && (d.name !== s.name || d.text !== s.text)) };
}
const tpaSection = (no, title, help) => {
  const sec = el("section", "tpa-sec"), h = el("h3", "tpa-h");
  h.append(el("span", "tpa-no", no), title);
  if (help) h.append(hHelp(`${title} 도움말`, help));
  sec.append(h);
  return sec;
};

function tplAgentSync() { // 서식 갈래·오버레이가 바뀐 뒤(outline_match.js olmRedraw) — 열려 있으면 ① 대상만 새 값으로(스킬 칸에 쓰던 글·계획은 그대로)
  if (!tpaOn()) return;
  const old = $("headsDlgBody").querySelector(".tpa-target");
  if (old) old.replaceWith(tpaTarget());
  tpaRunSync();
}

function tpaTarget() { // ① 대상 — 템플릿 고르기 · 개요 레벨 그림 · 레벨마다 서식 갈래 수
  const sec = tpaSection("①", "대상 템플릿", "에이전트가 정리할 템플릿입니다. 레벨마다 줄들을 서식이 같은 것끼리 묶은 「갈래」 를 에이전트에 보냅니다 — 갈래가 하나뿐인 레벨은 정리할 것이 없습니다. 종속 템플릿(「T1T3」)·서식 종속 템플릿(「T1L3a」)을 고르면 그 줄만 정리합니다.");
  sec.classList.add("tpa-target");
  const list = tpaTemplates(), sel = el("select", "tpa-tpl");
  sel.setAttribute("aria-label", "정리할 템플릿");
  for (const { id, t } of list) { const o = el("option", null, `T${t.no} ${(t.chain || []).slice(t.base || 0).join(" › ")} · ${nf(t.lines)}줄${t.comp ? " · 종속" : t.vari ? " · 서식 종속" : ""}`); o.value = id; sel.append(o); }
  sel.value = String(TPA.tpl);
  sel.disabled = !!TPA.busy;
  sel.onchange = () => { Object.assign(TPA, { tpl: sel.value, plan: null, choice: new Map(), err: "", prompt: null, done: null }); tplAgentDraw(); tpaStored(); };
  sec.append(sel);
  const t = olmTpl(TPA.tpl);
  if (!t) { sec.append(el("p", "hnote", "정리할 템플릿이 없습니다 — 헤딩 추출 2단계(헤딩 그래프)를 먼저 만드세요.")); return sec; }
  const pic = typeof olmPic === "function" ? olmPic(TPA.tpl) : null;
  if (pic) sec.append(pic);
  const ul = el("ul", "tpa-levels");
  let others = 0, multi = 0;
  for (const L of Object.keys(t.slots || {}).map(Number).filter((x) => x > (t.base || 0) && t.slots[String(x)].lines).sort((a, b) => a - b)) {
    const os = t.slots[String(L)], v = olmFresh() ? olmSlotData(TPA.tpl, L) : null, li = el("li");
    li.append(el("b", null, `L${L}`), ` 「${short(os.letter || "", 10)}」 ×${nf(os.lines)} `);
    if (!v) li.append(el("span", "muted", "서식 갈래 읽는 중…"));
    else {
      const n = v.groups.length;
      if (n > 1) multi += 1;
      others += v.rep ? v.others || 0 : 0;
      li.append(el("span", n > 1 ? "tpa-warn" : "muted", n > 1 ? `서식 ${n}가지${v.rep ? ` · 대표와 다른 줄 ${nf(v.others)}` : " · 대표 없음"}` : "서식 1가지"));
    }
    ul.append(li);
  }
  sec.append(ul);
  sec.dataset.multi = String(multi);
  if (olmFresh() && !multi) sec.append(el("p", "hnote", "이 템플릿은 레벨마다 서식이 한 가지뿐입니다 — 정리할 것이 없습니다."));
  return sec;
}

function tplAgentDraw() {
  if (!tpaOn()) return;
  const tools = $("headsDlgTools"), body = $("headsDlgBody"), keep = body.scrollTop, t = olmTpl(TPA.tpl), info = TPA.info, cur = tpaCur();
  $("headsDlgNote").textContent = t ? `T${t.no} ${(t.chain || []).slice(t.base || 0).join(" › ")}` : "";
  $("headsDlgHelp").replaceChildren(hHelp("템플릿 서식 정리 도움말", "에이전트(Opus 5.5)가 템플릿의 레벨마다 서식 갈래를 보고 어느 갈래를 대표로 삼고 어느 줄을 맞출지 정합니다. 에이전트는 저장해 둔 스킬 글(정리 기준)을 따르고, 스킬은 여기서 고쳐 저장할 수 있습니다. "
    + "계획을 받은 뒤 고른 것만 「적용」 하면 그 줄들의 레터 첫머리·문단 모양·글자 모양이 대표 것으로 바뀝니다 — 「실행 취소」 한 번으로 되돌립니다. 일부러 다르게 준 서식의 갈래는 맞추지 않고 서식 종속 템플릿(「T1L3a」)으로 뗍니다. "
    + "에이전트는 문서에 있는 갈래 가운데 고르기만 하고 서식 값을 새로 만들지 않습니다."));
  tools.replaceChildren(hBtn("‹ 템플릿 관계", () => headsTplView(t ? olmKey(TPA.tpl) : null), { title: "템플릿 관계로 돌아갑니다(쓰던 스킬 글·계획은 남습니다)", cls: "btn sm tpa-back" }),
    (() => { const c = el("span", `tpa-model${info && info.available ? "" : " off"}`, info ? `${tpaModel(info.model)}${info.available ? ` · ${info.backend === "api" ? "API" : info.backend || ""}` : " · LLM 꺼짐"}` : TPA.infoErr ? "에이전트 없음" : "읽는 중…");
      c.title = info ? `이 에이전트가 부르는 모델: ${info.model}(생각 깊이 ${info.effort}) — 다른 LLM 검토의 모델 설정과 따로입니다` : TPA.infoErr; return c; })(), el("span", "spacer"),
    hBtn("보낼 글", () => tpaPrompt(), { title: "에이전트에 보내는 글 전체(계약 · 스킬 · 이번 요청 · 자료)를 봅니다 — LLM 을 부르지 않습니다", disabled: !info || !!TPA.busy || !t }));
  const wrap = el("div", "tpa");
  if (TPA.infoErr) wrap.append(el("p", "hwarn tpa-err", TPA.infoErr));
  wrap.append(tpaTarget());

  // ② 스킬 — 저장해 둔 정리 기준 글(고르기 · 이름 · 글 · 저장 · 새 스킬 · 기본으로/지우기)
  const sk = tpaSection("②", "스킬 — 에이전트가 따를 정리 기준", "에이전트는 여기 저장된 글을 그대로 읽고 판단합니다. 글을 고쳤으면 「저장」 을 눌러야 쓰입니다(「정리 계획 받기」 가 먼저 저장합니다). "
    + "기본 스킬을 고치면 내 사본이 생기고 「기본으로 되돌리기」 로 돌아갑니다. 「새 스킬」 로 다른 기준을 따로 만들어 둘 수 있습니다. 스킬은 이 PC 의 모든 문서가 같이 씁니다.");
  const pick = el("select", "tpa-skill");
  pick.setAttribute("aria-label", "저장해 둔 스킬");
  for (const s of [...((info && info.skills) || [])].sort((a, b) => (b.key === "tidy") - (a.key === "tidy"))) { const o = el("option", null, `${s.name}${s.builtin ? (s.custom ? " (기본 · 고침)" : " (기본)") : ""}${TPA.drafts[s.key] ? " *" : ""}`); o.value = s.key; pick.append(o); }
  if (TPA.key === TPA_NEW) { const o = el("option", null, "새 스킬 (저장 전)"); o.value = TPA_NEW; pick.append(o); }
  pick.value = TPA.key;
  pick.disabled = !info || !!TPA.busy;
  pick.onchange = async () => { TPA.key = pick.value; TPA.arm = null; await tpaSkillLoad(); tplAgentDraw(); };
  const head = el("div", "tpa-row");
  head.append(pick, hBtn("새 스킬", () => { TPA.drafts[TPA_NEW] = { name: "새 스킬", text: cur.text }; TPA.key = TPA_NEW; TPA.skill = null; TPA.arm = null; tplAgentDraw(); },
    { title: "지금 글을 바탕으로 새 스킬을 만듭니다(이름을 바꾸고 저장)", disabled: !info || !!TPA.busy || TPA.key === TPA_NEW }));
  const name = el("input", "tpa-name");
  name.type = "text"; name.maxLength = 60; name.value = cur.name; name.placeholder = "스킬 이름"; name.setAttribute("aria-label", "스킬 이름");
  const ta = el("textarea", "tpa-text");
  ta.value = cur.text; ta.spellcheck = false; ta.setAttribute("aria-label", "스킬 글 — 에이전트가 따를 정리 기준");
  ta.placeholder = "에이전트가 따를 정리 기준을 적습니다 — 어느 갈래를 대표로 삼나 · 무엇을 맞추고 무엇을 남기나";
  name.disabled = ta.disabled = !info || !!TPA.busy || (!TPA.skill && TPA.key !== TPA_NEW);
  const stateLine = el("div", "tpa-row tpa-state");
  const edit = () => { TPA.drafts[TPA.key] = { name: name.value, text: ta.value }; tpaSkillState(stateLine); tpaRunSync(); };
  name.oninput = ta.oninput = edit;
  sk.append(head, name, ta, stateLine);
  wrap.append(sk);

  // ③ 이번 요청 + 실행
  const rq = tpaSection("③", "이번 요청", "이번 한 번만 더할 말입니다(없어도 됩니다) — 스킬보다 먼저 따릅니다. 예: 「L2 는 앞 공백 1칸짜리로」 · 「글꼴은 건드리지 말고 들여쓰기만」.");
  const req = el("input", "tpa-req");
  req.type = "text"; req.maxLength = 2000; req.value = TPA.request; req.placeholder = "없어도 됩니다 — 예: L2 는 앞 공백 1칸짜리로"; req.setAttribute("aria-label", "이번 요청");
  req.oninput = () => { TPA.request = req.value; };
  req.disabled = !!TPA.busy;
  const run = el("div", "tpa-row tpa-runrow");
  const go = hBtn("", () => tpaRun(), { cls: "btn sm primary tpa-go" });
  const direct = el("label", "tpa-direct"), dc = el("input");
  dc.type = "checkbox"; dc.checked = tpaDirect(); dc.disabled = !!TPA.busy;
  dc.onchange = () => { try { localStorage.setItem(TPA_DIRECT_KEY, dc.checked ? "on" : "off"); } catch { /* 기억만 안 함 */ } };
  direct.append(dc, " 계획을 받으면 바로 적용");
  direct.title = "켜면 계획을 받자마자 에이전트가 고른 대로 문서에 적용합니다(「실행 취소」 한 번으로 되돌림). 끄면 계획을 보고 고른 것만 적용합니다.";
  const live = el("span", "tpa-live");
  live.setAttribute("role", "status");
  run.append(go, direct, live);
  rq.append(req, run);
  wrap.append(rq);
  if (TPA.err) wrap.append(el("p", "hwarn tpa-err", TPA.err));
  if (TPA.prompt) wrap.append(tpaPromptBox());
  if (TPA.plan) wrap.append(tpaPlan());
  body.replaceChildren(wrap);
  body.scrollTop = keep;
  tpaSkillState(stateLine);
  tpaRunSync();
}

function tpaSkillState(line) { // 스킬 칸 아래 줄 — 저장 상태 · 저장 · 기본으로/지우기(줄 안에서 두 번)
  const s = TPA.skill, cur = tpaCur(), busy = !!TPA.busy;
  const when = s && s.updated ? new Date(s.updated * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
  const st = el("span", `tpa-saved${cur.dirty ? " dirty" : ""}`, cur.isNew ? "새 스킬 — 저장 전" : cur.dirty ? "고침 — 저장 안 됨" : !s ? "" : s.custom ? `저장됨 · 판 ${s.version}${when ? ` · ${when}` : ""}` : "기본 스킬(고친 적 없음)");
  const save = hBtn("저장", () => tpaSave(), { title: "이 글을 저장합니다 — 다음 정리부터 이 글로 돕니다", disabled: busy || !cur.dirty || !cur.text.trim() || !cur.name.trim(), cls: "btn sm tpa-save" });
  const out = [st, el("span", "spacer"), save];
  if (cur.dirty && !cur.isNew) out.push(hBtn("고친 것 버리기", () => { delete TPA.drafts[TPA.key]; tplAgentDraw(); }, { title: "저장하지 않은 고침을 버리고 저장된 글로", disabled: busy }));
  if (cur.isNew) out.push(hBtn("취소", () => { delete TPA.drafts[TPA_NEW]; TPA.key = ((TPA.info && TPA.info.skills[0]) || {}).key || "tidy"; tpaSkillLoad().then(tplAgentDraw); }, { disabled: busy }));
  else if (s && (s.custom || !s.builtin)) {
    const arm = TPA.arm === s.key, label = s.builtin ? (arm ? "되돌리기 확인" : "기본으로 되돌리기") : (arm ? "지우기 확인" : "지우기");
    out.push(hBtn(label, () => { if (TPA.arm === s.key) tpaRemove(); else { TPA.arm = s.key; tpaSkillState(line); } },
      { title: s.builtin ? "내 사본을 버리고 기본 글로 되돌립니다 — 한 번 더 누르면 됩니다" : "이 스킬을 지웁니다 — 한 번 더 누르면 됩니다", disabled: busy, cls: `btn sm${arm ? " danger" : ""}` }));
  }
  line.replaceChildren(...out);
}

function tpaRunSync() { // 「정리 계획 받기」 단추의 글·켜짐과 도는 표시
  const go = document.querySelector("#headsDlgBody .tpa-go"), live = document.querySelector("#headsDlgBody .tpa-live");
  if (!go) return;
  const cur = tpaCur(), info = TPA.info, t = olmTpl(TPA.tpl), sec = document.querySelector("#headsDlgBody .tpa-target");
  const none = olmFresh() && sec && sec.dataset.multi === "0";
  go.textContent = TPA.busy === "plan" ? "계획 받는 중…" : cur.dirty ? "저장하고 정리 계획 받기" : TPA.plan ? "정리 계획 다시 받기" : "정리 계획 받기";
  go.disabled = !!TPA.busy || !info || !info.available || !t || none || !cur.text.trim() || !cur.name.trim();
  go.title = !info ? TPA.infoErr || "에이전트 정보를 읽는 중" : !info.available ? "서버의 LLM 이 꺼져 있어 에이전트를 부를 수 없습니다" : none ? "레벨마다 서식이 한 가지뿐이라 정리할 것이 없습니다"
    : `${tpaModel(info.model)} 에게 T${t ? t.no : ""} 의 정리 계획을 받습니다 — 문서는 아직 안 바뀝니다${cur.dirty ? "(고친 스킬을 먼저 저장합니다)" : ""}`;
  if (live) {
    live.replaceChildren();
    if (TPA.busy === "plan" || TPA.busy === "apply") {
      const secs = Math.max(0, Math.round((Date.now() - TPA.started) / 1000));
      live.append(el("span", "ag-spin"), TPA.busy === "plan" ? ` ${tpaModel(info && info.model)} 가 서식 갈래를 보는 중 · ${secs}초` : " 문서에 적용하는 중");
    }
  }
}

async function tpaSave() { // 스킬 저장 → 성공 여부
  const cur = tpaCur();
  if (!cur.dirty) return true;
  TPA.busy = "save";
  tpaRunSync();
  try {
    const isNew = cur.isNew;
    const r = await api(isNew ? "/api/outline/agent/skills" : `/api/outline/agent/skills/${encodeURIComponent(TPA.key)}`, { method: isNew ? "POST" : "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: cur.name, text: cur.text, ...(isNew || !TPA.skill ? {} : { version: TPA.skill.version }) }) });
    delete TPA.drafts[TPA.key];
    TPA.key = r.key;
    TPA.skill = r;
    TPA.arm = null;
    TPA.info = await api("/api/outline/agent");
    toast(`스킬 「${r.name}」 을 저장했습니다(판 ${r.version}) — 다음 정리부터 이 글로 돕니다`);
    return true;
  } catch (e) {
    toast(e.status === 409 ? "다른 곳에서 이 스킬을 먼저 고쳤습니다 — 스킬을 다시 고른 뒤 고쳐 주세요" : `스킬을 저장하지 못했습니다: ${e.message}`, true);
    return false;
  } finally { TPA.busy = null; if (tpaOn()) tplAgentDraw(); }
}

async function tpaRemove() { // 만든 스킬 지우기 · 기본 스킬 되돌리기
  const s = TPA.skill;
  if (!s) return;
  TPA.busy = "save";
  try {
    const r = await api(`/api/outline/agent/skills/${encodeURIComponent(s.key)}`, { method: "DELETE" });
    delete TPA.drafts[s.key];
    TPA.arm = null;
    TPA.info = await api("/api/outline/agent");
    if (r.deleted) { TPA.key = (TPA.info.skills[0] || {}).key || "tidy"; await tpaSkillLoad(); toast(`스킬 「${s.name}」 을 지웠습니다`); }
    else { TPA.skill = r; toast(`스킬 「${r.name}」 을 기본 글로 되돌렸습니다`); }
  } catch (e) { toast(`스킬을 ${s.builtin ? "되돌리지" : "지우지"} 못했습니다: ${e.message}`, true); }
  finally { TPA.busy = null; if (tpaOn()) tplAgentDraw(); }
}

async function tpaPrompt() { // 「보낼 글」 — LLM 을 부르지 않고 보낼 글만(저장된 스킬 글로)
  if (TPA.prompt) { TPA.prompt = null; tplAgentDraw(); return; }
  try {
    await flushAll();
    TPA.prompt = await api(`/api/docs/${state.id}/outline/agent/${encodeURIComponent(TPA.tpl)}/plan`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill: TPA.key === TPA_NEW ? ((TPA.info && TPA.info.skills[0]) || {}).key : TPA.key, request: TPA.request, dry: true }) });
    tplAgentDraw();
  } catch (e) { toast(`보낼 글을 만들지 못했습니다: ${e.message}`, true); }
}
function tpaPromptBox() {
  const p = TPA.prompt, d = el("details", "tpa-prompt");
  d.open = true;
  d.append(el("summary", null, `에이전트에 보내는 글 · ${nf(p.chars)}자 · 스킬 「${p.skill.name}」${tpaCur().dirty ? " — 저장된 글 기준(고친 것은 저장해야 들어갑니다)" : ""}`));
  const ta = el("textarea", "tpa-text ro");
  ta.readOnly = true; ta.value = p.prompt; ta.setAttribute("aria-label", "에이전트에 보내는 글");
  d.append(ta);
  return d;
}

async function tpaStored() { // 받아 둔 계획을 불러온다(GET …/outline/agent/plans — spec_작업 ② §20) — 지금 문서 차례에서 받은 것(planned)만. 적용함 · 옛 계획은 다시 받는다
  if (!state.id || TPA.plan || TPA.busy || TPA.tpl == null) return;
  const id = state.id, epoch = state.epoch, tpl = String(TPA.tpl);
  let r;
  try { r = await api(`/api/docs/${id}/outline/agent/plans`); } catch { return; } // 옛 서버 — 전처럼 「정리 계획 받기」 로
  if (epoch !== state.epoch || String(TPA.tpl) !== tpl || TPA.plan || TPA.busy) return;
  const rec = (r.plans || {})[tpl];
  if (!rec || rec.state !== "planned" || !rec.plan) return;
  TPA.plan = rec;
  TPA.choice = new Map();
  for (const lv of rec.plan.levels) for (const row of tpaRows(lv)) TPA.choice.set(tpaKey(lv, row.g), row.was); // 처음 값 = 에이전트가 고른 것(받았을 때와 같게)
  if (tpaOn()) tplAgentDraw();
}

async function tpaRun() { // 「정리 계획 받기」 — 고친 스킬은 먼저 저장 → 계획(LLM) → (바로 적용이면 적용)
  if (TPA.busy || !state.id) return;
  if (!(await tpaSave())) return;
  const epoch = state.epoch, tpl = TPA.tpl;
  Object.assign(TPA, { busy: "plan", started: Date.now(), err: "", plan: null, choice: new Map(), prompt: null, done: null });
  tplAgentDraw();
  clearInterval(TPA.timer);
  TPA.timer = setInterval(() => { if (TPA.busy && tpaOn()) tpaRunSync(); }, 1000);
  try {
    await flushAll();
    const r = await api(`/api/docs/${state.id}/outline/agent/${encodeURIComponent(tpl)}/plan`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill: TPA.key, request: TPA.request }) });
    if (epoch !== state.epoch || tpl !== TPA.tpl) return;
    TPA.plan = r;
    for (const lv of r.plan.levels) for (const row of tpaRows(lv)) TPA.choice.set(tpaKey(lv, row.g), row.was); // 처음 값 = 에이전트가 고른 것
    if (typeof olmPlanGot === "function") olmPlanGot(tpl, r); // 템플릿 줄의 「템플릿 맞추기」 가 이 계획대로(outline_match.js — spec_hwpx_웹편집 ② §8-4 「계획대로 맞추기」)
  } catch (e) {
    if (epoch === state.epoch) TPA.err = e.status === 404 && /not found/i.test(e.message || "") ? "서버가 옛 판이라 서식 정리 에이전트를 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요" : `계획을 받지 못했습니다: ${e.message}`;
  } finally {
    clearInterval(TPA.timer);
    if (epoch === state.epoch) { TPA.busy = null; if (tpaOn()) tplAgentDraw(); }
  }
  if (epoch === state.epoch && TPA.plan && tpaDirect() && tpaTodo().levels.length) tpaApply();
}

const tpaSkillKey = () => (typeof TPA.key === "string" && TPA.key && TPA.key !== TPA_NEW ? TPA.key : "tidy"); // 이어 돌리기(LLM 검증·보완 · 헤딩 그래프(LLM) · 계획 받기)가 쓸 스킬 — 이 열에서 고른 것(없으면 기본)
const TPA_SFX = "abcdefghijklmnopqrstuvwxyz";
const tpaKey = (lv, g) => `${lv.level}|${g.group}`;
function tpaEdited() { // 이 화면에서 고르기를 에이전트가 고른 것과 다르게 바꿔 둔 계획의 템플릿 번호 | null — 「모두 반영」 의 확인 창이 알린다(tpl_plan_bar.js): 바꾼 고르기는 화면에만 있어 이 열의 「적용」 으로만 반영된다
  const P = TPA.plan;
  if (!P || !P.plan || TPA.done) return null;
  for (const lv of P.plan.levels) for (const row of tpaRows(lv)) if ((TPA.choice.get(tpaKey(lv, row.g)) || row.was) !== row.was) return P.no;
  return null;
}

function tpaRows(lv) { // 레벨의 갈래 줄(대표 갈래 빼고) — 에이전트의 답 차례: 맞추기 · 다른 템플릿(그 대표 → 같이 옮길 것) · 그대로. {g, was(에이전트가 고른 것), sp(뗄 항목), head(그 항목의 대표)}
  const rows = [];
  for (const g of lv.match || []) rows.push({ g, was: "match" });
  for (const sp of lv.split || []) {
    rows.push({ g: sp.rep, was: `s:${sp.sfx}`, sp, head: true });
    for (const g of sp.match || []) rows.push({ g, was: `s:${sp.sfx}`, sp });
  }
  for (const g of lv.keep || []) rows.push({ g, was: "keep" });
  return rows;
}
function tpaLetters(lv) { // 이 레벨에서 고를 수 있는 새 템플릿 글자 — 에이전트가 정한 것 + 빈 글자 하나(사람이 따로 떼는 것)
  const mine = (lv.split || []).map((sp) => sp.sfx), used = new Set([...(lv.taken || []), ...mine]), spare = [...TPA_SFX].find((ch) => !used.has(ch));
  return spare ? [...mine, spare] : mine;
}
function tpaCuts(lv, choice = TPA.choice) { // 고른 것 → 이 레벨에서 뗄 템플릿들 [{sfx, rep(대표 갈래), rows[갈래…]}] — 대표 = 에이전트가 정한 대표(아직 그 글자에 있으면), 아니면 줄 수가 많은 갈래
  const by = new Map();
  for (const r of tpaRows(lv)) {
    const c = choice.get(tpaKey(lv, r.g)) || "";
    if (!c.startsWith("s:")) continue;
    if (!by.has(c.slice(2))) by.set(c.slice(2), []);
    by.get(c.slice(2)).push(r);
  }
  return [...by].map(([sfx, rows]) => {
    const head = rows.find((r) => r.head && r.sp.sfx === sfx) || rows.reduce((a, r) => (r.g.count > a.g.count ? r : a), rows[0]);
    return { sfx, rep: head.g, rows: rows.map((r) => r.g) };
  });
}

function tpaChoiceOf(P) { // 계획 → 에이전트가 고른 그대로의 고르기(받았을 때의 처음 값 — 「템플릿 맞추기」 의 「계획대로」 가 쓴다: outline_match.js olmTplMatch)
  const choice = new Map();
  for (const lv of (P && P.plan && P.plan.levels) || []) for (const row of tpaRows(lv)) choice.set(tpaKey(lv, row.g), row.was);
  return choice;
}
const tpaTodoOf = (P) => tpaTodo(P, tpaChoiceOf(P)); // 에이전트가 고른 그대로 반영할 때의 적용 몸 · 줄 수
function tpaTodo(P = TPA.plan, choice = TPA.choice) { // 고른 것 → 적용 몸의 levels · 바뀔 줄 수 n · 다른 템플릿으로 옮길 줄 수 moved · 고른 갈래 수 picked
  const levels = [];
  let n = 0, moved = 0, picked = 0;
  for (const lv of (P && P.plan.levels) || []) {
    if (!lv.rep) continue;
    const likes = tpaRows(lv).filter((r) => choice.get(tpaKey(lv, r.g)) === "match").map((r) => r.g), cuts = tpaCuts(lv, choice);
    if (!likes.length && !cuts.length) continue; // 고른 갈래가 없는 레벨은 대표도 안 바꾼다
    n += likes.reduce((a, g) => a + g.count, 0) + cuts.reduce((a, c) => a + c.rows.reduce((b, g) => b + (g === c.rep ? 0 : g.count), 0), 0); // 뗀 줄 가운데 새 대표와 다른 갈래는 그 대표에 맞춘다
    moved += cuts.reduce((a, c) => a + c.rows.reduce((b, g) => b + g.count, 0), 0);
    picked += likes.length + cuts.reduce((a, c) => a + c.rows.length, 0);
    levels.push({ level: lv.level, rep: lv.rep.para, likes: likes.map((g) => g.para),
      ...(cuts.length ? { splits: cuts.map((c) => ({ likes: c.rows.map((g) => g.para), rep: c.rep.para, sfx: c.sfx })) } : {}) });
  }
  return { levels, n, moved, picked };
}

async function tpaApply() { // 「적용」 — 고른 갈래만 대표 모양으로(템플릿 단위 맞추기 — 실행 취소 1)
  const P = TPA.plan, todo = tpaTodo();
  if (TPA.busy || !P || !todo.levels.length) return;
  TPA.busy = "apply";
  TPA.started = Date.now();
  tpaRunSync();
  const r = await olmApplyTpl(P.tpl, { rev: state.serverRev, by: "agent", plan: P.at, levels: todo.levels }); // plan = 이 계획의 표시(at) — 서버는 남아 있는 계획이 이것일 때만 「반영함」 으로 적는다(spec_hwpx_웹편집 ② §8-4)
  TPA.busy = null;
  if (r) {
    const n = (r.changed || []).length, made = (r.splits || []).map((x) => `T${x.no}`);
    TPA.done = { n, levels: (r.levels || []).length, reps: (r.levels || []).filter((x) => x.repChanged).length, made, moved: (r.splits || []).reduce((a, x) => a + x.moved, 0) };
    toast(`에이전트 계획대로 ${[n ? `T${P.no} 줄 ${nf(n)}개를 맞췄습니다` : "", made.length ? `서식 종속 템플릿 ${made.join(" · ")} 를 만들었습니다` : ""].filter(Boolean).join(" · ") || "바꾼 것이 없습니다"} — 「실행 취소」 한 번으로 되돌립니다`);
  } else if (structOp.lastError && structOp.lastError.status === 409) TPA.err = "계획을 받은 뒤 문서가 바뀌었습니다 — 「정리 계획 다시 받기」 로 새 계획을 받으세요";
  if (tpaOn()) tplAgentDraw();
}

// 계획이 옛것인가 — 계획은 문서 차례가 아니라 **그 템플릿 줄의 지문**에 묶인다(서버 analysis.plan_state — spec_hwpx_웹편집 ② §8-4 「계획은 줄 지문에」): 문서의 다른 곳을 고쳤어도 계획은 그대로 쓴다.
// 화면은 지문을 모른다 — 계획을 받은 뒤 문서 차례가 바뀌었으면 서버에 그 계획의 상태를 한 번 묻고(GET …/outline/agent/plans), 그 답이 올 때까지는 쓸 수 있는 것으로 둔다(옛 계획이면 적용 때 서버가 409 로 막는다).
function tpaStale(P) {
  if (!P || P.rev === state.serverRev) return false;
  const k = `${state.id}|${P.tpl}|${P.at}|${state.serverRev}`;
  if (TPA.staleKey === k) return !!TPA.staleIs;
  TPA.staleKey = k;
  TPA.staleIs = false;
  const id = state.id, epoch = state.epoch;
  api(`/api/docs/${id}/outline/agent/plans`).then((r) => {
    if (epoch !== state.epoch || TPA.staleKey !== k) return;
    const rec = (r.plans || {})[String(P.tpl)];
    const bad = !rec || rec.at !== P.at || rec.state !== "planned";
    if (bad !== TPA.staleIs) { TPA.staleIs = bad; if (tpaOn()) tplAgentDraw(); }
  }).catch(() => { /* 못 물으면 쓸 수 있는 것으로 — 서버가 막는다 */ });
  return false;
}

function tpaPlan() { // ④ 계획 — 요약 · 레벨마다 대표 · 갈래 줄마다 고르기(맞추기 / 그대로 / T1L3a 로) · 적용
  const P = TPA.plan, plan = P.plan, sec = tpaSection("④", "정리 계획", "에이전트가 고른 것입니다 — 갈래마다 고르기를 바꿀 수 있습니다. 「맞추기」 = 이 레벨의 대표 모양으로 바꿉니다 · 「그대로」 = 손대지 않습니다 · "
    + "「T1L3a 로」 = 그 갈래를 서식 종속 템플릿으로 뗍니다(그 레벨부터 시작하는 다른 템플릿 — 뒤로는 그 줄들끼리만 서식을 견줍니다). 기본 스킬의 기준: 레터가 대표와 다른 갈래는 떼고, 레터가 같은 갈래는 대표에 맞춥니다 — 예외로 남길 갈래는 「그대로」 로 고르세요. 같은 이름을 고른 갈래끼리 한 템플릿이 되고, 그 가운데 대표(에이전트가 정한 것, 없으면 줄 수가 많은 것)에 나머지를 맞춥니다. "
    + "대표를 바꾸는 레벨은 그 레벨에서 고른 갈래가 있어야 적용됩니다."),
    stale = tpaStale(P) && !TPA.done, done = TPA.done, lock = !!TPA.busy || stale || !!done;
  sec.classList.add("tpa-plan");
  if (plan.summary) sec.append(el("p", "tpa-sum", plan.summary));
  const count = el("span", "tpa-count");
  const apply = hBtn("", () => tpaApply(), { cls: "btn sm primary tpa-apply" });
  const sync = () => {
    const todo = tpaTodo();
    apply.textContent = done ? `적용함 — ${nf(done.n)}줄${done.moved ? ` · 떼기 ${nf(done.moved)}줄` : ""}` : `적용 — ${nf(todo.n)}줄${todo.moved ? ` · 떼기 ${nf(todo.moved)}줄` : ""}`;
    apply.title = todo.moved && !done ? `맞출 줄 ${nf(todo.n)}개 · 서식 종속 템플릿으로 뗄 줄 ${nf(todo.moved)}개(그 아래 줄도 같이 갑니다) — 「실행 취소」 한 번으로 되돌립니다` : "";
    apply.disabled = lock || !todo.levels.length;
    count.textContent = done ? `레벨 ${done.levels}개${done.reps ? ` · 대표 바꿈 ${done.reps}` : ""}${done.made && done.made.length ? ` · 새 템플릿 ${done.made.join(" · ")}` : ""} · 「실행 취소」 한 번으로 되돌립니다`
      : stale ? "이 템플릿의 줄이 바뀌었습니다 — 계획을 다시 받으세요" : `고른 갈래 ${todo.picked}개`;
  };
  const redraw = (key) => { // 고르기를 바꾸면 계획 절만 다시 그리고(대표·맞춤 표시가 줄끼리 얽힌다) 그 고르기에 초점을 돌려준다
    const fresh = tpaPlan();
    sec.replaceWith(fresh);
    const again = [...fresh.querySelectorAll(".tpa-pick")].find((s) => s.dataset.key === key);
    if (again) again.focus();
  };
  const box = (lv, row, cuts) => {
    const g = row.g, key = tpaKey(lv, g), cur = TPA.choice.get(key) || "keep", cut = cur.startsWith("s:") ? cuts.find((c) => c.sfx === cur.slice(2)) : null, head = !!cut && cut.rep === g;
    const kind = cur === "match" ? "match" : cut ? "split" : "keep", name = (ch) => `T${P.no}L${lv.level}${ch}`;
    const line = el("div", `tpa-g ${kind}`), pick = el("select", "tpa-pick"), body = el("span", "tpa-gb");
    const opt = (v, text) => { const o = el("option", null, text); o.value = v; pick.append(o); };
    opt("match", "맞추기");
    opt("keep", "그대로");
    if (!g.noSplit) for (const ch of tpaLetters(lv)) opt(`s:${ch}`, `${name(ch)} 로`);
    pick.dataset.key = key;
    pick.value = cur;
    pick.disabled = lock;
    pick.setAttribute("aria-label", `×${g.count} 갈래 「${short(g.sample || "", 16)}」 를 어떻게 할지`);
    pick.title = "맞추기 = 이 레벨의 대표 모양으로 · 그대로 = 손대지 않음 · T…L…a 로 = 서식이 다른 종속 템플릿으로 떼기(같은 이름끼리 한 템플릿)" + (g.noSplit ? "\n이 갈래는 뗄 수 없습니다 — 번호형 레벨에서 같은 부모 아래 형제의 일부(번호가 따로 매겨집니다)" : "");
    pick.onchange = () => { TPA.choice.set(key, pick.value); redraw(key); };
    body.append(el("span", "olm-n", `×${nf(g.count)}`), headsParaLink(g.para, g.sample || "(빈 글)", 30, "이 갈래의 첫 줄"));
    if (cut) body.append(el("span", `olm-chip tpa-vt${head ? " head" : ""}`, head ? `${name(cut.sfx)} 의 대표` : `${name(cut.sfx)} 대표에 맞춤`));
    const diff = g.diff || [];
    if (head) { // 새 템플릿의 대표 — 안 바뀐다: 이 레벨 대표와 무엇이 다른지만(화살표 없이)
      if (diff.length) { const d = el("span", "tpa-diff", `${diff.slice(0, 3).map((x) => `${x[1]} ${x[3]}(T${P.no} 대표 ${x[2]})`).join(" · ")}${diff.length > 3 ? ` 외 ${diff.length - 3}` : ""}`); d.title = `T${P.no} L${lv.level} 대표와 다른 값 — 이 줄들은 안 바뀌고 ${name(cut.sfx)} 로 옮겨 갑니다\n${diff.map((x) => `${x[1]}: ${x[3]}(T${P.no} 대표 ${x[2]})`).join("\n")}`; body.append(d); }
    } else if (cut) { // 새 템플릿의 대표에 맞춘다 — 에이전트가 짠 짝이면 그 대표 기준의 다른 값
      const to = row.sp && row.sp.sfx === cut.sfx && row.sp.rep === cut.rep && g.diffTo ? g.diffTo : null;
      const d = el("span", "tpa-diff", to && to.length ? olmDiffText(to, 3) : `${name(cut.sfx)} 의 대표 「${short(cut.rep.sample || "", 18)}」 모양으로 맞춥니다`);
      if (to && to.length) d.title = olmDiffTitle(to);
      body.append(d);
    } else if (diff.length) { const d = el("span", "tpa-diff", olmDiffText(diff, 3)); d.title = olmDiffTitle(diff); body.append(d); }
    const why = row.head ? row.sp.why : row.was === "keep" ? (g.auto ? "에이전트가 말하지 않은 갈래 — 그대로 둡니다" : g.why || "") : "";
    if (why) body.append(el("span", "tpa-why", why));
    line.append(pick, body);
    return line;
  };
  for (const lv of plan.levels) {
    const b = el("div", "tpa-lv");
    const h = el("div", "tpa-lvh");
    h.append(el("b", null, `L${lv.level}`), ` 「${short(lv.letter || "", 10)}」 ${nf(lv.lines)}줄`, el("span", lv.change || lv.moved ? "tpa-warn" : "muted",
      lv.single ? " · 서식 1가지 — 그대로" : lv.change || lv.moved ? `${lv.change ? ` · 바꿀 줄 ${nf(lv.change)}` : ""}${lv.moved ? ` · 다른 템플릿으로 ${nf(lv.moved)}` : ""}` : " · 바꿀 줄 없음"));
    b.append(h);
    if (!lv.single && lv.rep) {
      const rep = el("div", "tpa-rep");
      rep.append(el("span", `hb olm-badge${lv.rep.changed ? " chg" : ""}`, lv.rep.changed ? "대표 바꿈" : "대표"), el("span", "olm-n", `×${nf(lv.rep.count)}`), headsParaLink(lv.rep.para, lv.rep.sample || "(빈 글)", 30, "대표로 삼을 줄"));
      if (lv.rep.changed) rep.title = `이 레벨의 대표를 이 갈래의 첫 줄로 바꾼 뒤 맞춥니다(지금 대표는 ${lv.was || "없음"})`;
      b.append(rep);
      if (lv.why) b.append(el("p", "tpa-why", lv.why));
      const cuts = tpaCuts(lv);
      for (const row of tpaRows(lv)) b.append(box(lv, row, cuts));
    } else if (!lv.single && !lv.rep) b.append(el("p", "tpa-why", "대표가 없어 손대지 않습니다 — 「템플릿 관계」 에서 줄 하나를 대표로 정한 뒤 다시 받으세요."));
    sec.append(b);
  }
  if (plan.notes && plan.notes.length) { const d = el("details", "ag-dropped"); d.append(el("summary", null, `걸러낸 답 ${plan.notes.length}`)); const ul = el("ul"); plan.notes.forEach((n) => ul.append(el("li", null, n))); d.append(ul); sec.append(d); }
  const foot = el("div", "tpa-row tpa-foot");
  foot.append(apply, count);
  sec.append(foot, el("p", "ag-note", `${tpaModel(P.model)}${P.backend ? ` · ${P.backend === "api" ? "API" : P.backend}` : ""} · ${Math.round((P.ms || 0) / 100) / 10}초${P.costUsd != null ? ` · $${(+P.costUsd).toFixed(4)}` : ""} · 스킬 「${P.skill.name}」${P.skill.version ? ` 판 ${P.skill.version}` : "(기본)"}${P.request ? ` · 요청 「${short(P.request, 30)}」` : ""}`));
  sync();
  return sec;
}
