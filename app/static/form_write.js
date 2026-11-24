// 워크플로우 「양식 작성」 의 화면(spec_양식작성 ② §6) — 대시보드의 단계 상태(formWriteLive) · 2열 「자료 가져오기」(fwTakeOpen — 문서 라이브러리 서버의 추출 MD 를 이 문서의 자료로) ·
// 2열 「지침 작성」(fwWriteOpen — 자리마다 작성 지침 + 자료 → 문서 에이전트의 제안: 문서는 제안 카드의 「문서에 반영」 을 눌러야 바뀐다).
// 문서 라이브러리 · 자료 추출은 **따로 선 서버**(doclib/ — 새 탭으로 연다)이고, 여기는 그 서버를 8114 의 끝점(/api/doclib)으로만 읽는다. 두 열은 어느 hwpx 문서에서나 열 수 있다(공통 도구 — 워크플로우에 묶지 않는다).
// 기대는 app.js 의 이름: api · el · $ · state · H_JSON · hBtn · hHelp(panel_help.js) · toast · headsDlg · heads · scrollToBlock · showTab · toolShown / dashboard.js: dashBtn · dashDraw / doc_agent.js: AGENT · agentLoad.
const FW = { key: "", at: 0, lib: null, gw: null, loading: null, err: "", picks: new Set(), mats: null, note: "", onlyGuided: true, poll: 0, seen: "" };
const fwKey = () => `${state.id || ""}`;
const fwRunning = () => !!(FW.gw && FW.gw.run && FW.gw.run.state === "running");

async function fwRead(force = false) { // 문서 라이브러리의 목록 + 이 문서의 자리 · 자료 · 실행 — 10초(도는 동안 2초) 안의 것은 다시 읽지 않는다
  if (FW.key !== fwKey()) Object.assign(FW, { key: fwKey(), at: 0, lib: null, gw: null, err: "", picks: new Set(), mats: null, note: "", seen: "" });
  if (!state.id) return FW;
  const age = Date.now() - FW.at;
  if (!force && FW.gw && age < (fwRunning() ? 2000 : 10000)) return FW;
  if (FW.loading) return FW.loading;
  const key = FW.key;
  FW.loading = (async () => {
    try {
      const [lib, gw] = await Promise.all([api("/api/doclib").catch((e) => ({ alive: false, why: e.message, docs: [], url: "" })), api(`/api/docs/${state.id}/guide-write`)]);
      if (key !== fwKey()) return FW;
      Object.assign(FW, { lib, gw, at: Date.now(), err: "" });
      if (FW.mats === null) FW.mats = new Set(gw.materials.map((m) => m.id)); // 처음에는 자료를 모두 고른다
      else for (const id of [...FW.mats]) if (!gw.materials.some((m) => m.id === id)) FW.mats.delete(id);
      const run = gw.run;
      if (run && run.state !== "running" && FW.seen !== run.id && FW.watch === run.id) { // 지켜보던 실행이 끝남 — 에이전트 보기의 대화를 다시 읽어 제안 카드를 보인다
        FW.seen = run.id;
        if (typeof agentLoad === "function") agentLoad();
      }
    } catch (e) { if (key === fwKey()) FW.err = e.message || String(e); }
    FW.loading = null;
    return FW;
  })();
  return FW.loading;
}
function fwLibOpen(hash = "") { // 문서 라이브러리(따로 선 서버)를 새 탭으로
  const url = (FW.lib && FW.lib.url) || "";
  if (!url) return toast("문서 라이브러리 서버의 주소를 모릅니다", true);
  window.open(url + (hash ? `/#${hash}` : "/"), "_blank", "noopener");
}
const fwDoneExtracts = () => ((FW.lib && FW.lib.docs) || []).reduce((n, d) => n + d.extracts.length, 0);
const FW_LIB_DOWN = "문서 라이브러리 서버가 꺼져 있습니다 — tools/start_doclib.ps1 로 띄웁니다(자료 추출 · 「자료 가져오기」 를 할 수 없습니다)";

async function formWriteLive() { // 대시보드(dashboard.js dashLive)의 「양식 작성」 가지 — 단계마다 지금 상태와 그 일을 하는 곳을 여는 단추
  await fwRead();
  const lib = FW.lib || { alive: false, docs: [] }, gw = FW.gw || { places: [], materials: [], run: null, enabled: false }, run = gw.run;
  const libBtn = (focus) => [dashBtn("문서 라이브러리 열기", () => fwLibOpen(), { disabled: !lib.alive, title: lib.alive ? "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭으로 엽니다" : FW_LIB_DOWN, focus })];
  const docs = lib.docs.length, done = fwDoneExtracts(), going = lib.docs.reduce((n, d) => n + (d.running || 0), 0), mats = gw.materials.length, guided = gw.places.filter((p) => p.n).length, heads = gw.places.filter((p) => p.kind === "head").length;
  const items = (run && run.items) || [], got = items.reduce((n, i) => n + (i.proposals || 0), 0), applied = typeof AGENT === "object" && AGENT.turns ? AGENT.turns.reduce((n, t) => n + (t.proposals || []).filter((p) => p.state === "applied").length, 0) : 0;
  const next = !mats ? "take" : "ask";
  const S = {
    open: { state: "done", text: "" },
    keep: { state: docs ? "done" : lib.alive ? "now" : "hold", text: lib.alive ? (docs ? `자료 문서 ${docs}개` : "아직 자료 문서가 없습니다") : FW_LIB_DOWN, acts: libBtn("act:keep") },
    extract: { state: going ? "run" : done ? "done" : docs ? "now" : "todo", text: lib.alive ? [done ? `끝난 추출 ${done}개` : "아직 추출한 것이 없습니다", going ? `추출 중 ${going}개` : ""].filter(Boolean).join(" · ") : "", acts: libBtn("act:extract") },
    take: { state: mats ? "done" : next === "take" ? "now" : "todo", text: mats ? `이 문서의 자료 ${mats}개` : "자료가 없습니다 — 추출한 MD 를 가져오거나 에이전트 보기에서 파일 · 글을 자료로 줍니다",
      acts: [dashBtn("자료 가져오기", () => fwTakeOpen(), { primary: !mats, title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로 가져옵니다(문서 옆 열)", focus: "act:take" })] },
    guides: { state: "", text: gw.hwpx === false ? "hwpx 문서만 됩니다" : `헤딩 ${heads}곳 · 작성 지침이 있는 자리 ${guided}곳`, acts: [dashBtn("지침 작성 열기", () => fwWriteOpen(), { title: "자리마다의 작성 지침을 보고, 채울 자리와 자료를 골라 제안을 받습니다(문서 옆 열)", focus: "act:guides" })] },
    ask: { state: run && run.state === "running" ? "run" : run ? "done" : mats ? "now" : "todo",
      text: run ? (run.state === "running" ? `자리 ${items.filter((i) => i.state !== "queued" && i.state !== "running").length}/${items.length} 받는 중` : `마지막 실행 — 자리 ${items.length}곳 · 제안 ${got}개${items.some((i) => i.state === "failed") ? ` · 실패 ${items.filter((i) => i.state === "failed").length}곳` : ""}`)
        : !gw.enabled ? "LLM 을 쓸 수 없습니다" : mats ? "" : "자료를 먼저 가져옵니다",
      acts: [dashBtn("지침 작성 열기", () => fwWriteOpen(), { primary: !!mats && !run, title: "채울 자리와 자료를 고르고 「제안 받기」 를 누릅니다 — 유료 LLM · 문서는 바뀌지 않습니다", focus: "act:ask" })] },
    check: { state: "", text: "제안마다 저절로 돕니다" },
    apply: { state: applied ? "done" : got ? "now" : "todo", text: applied ? `반영한 제안 ${applied}개` : "제안 카드의 「문서에 반영」 을 누른 제안만 들어갑니다",
      acts: toolShown("Agent") ? [dashBtn("에이전트 보기 열기", () => showTab("Agent"), { primary: !!got && !applied, title: "받은 제안 카드를 보고 「문서에 반영」 을 누릅니다", focus: "act:apply" })] : [] },
  };
  if (FW.err) S.take.text = `읽지 못했습니다 — ${FW.err}`;
  if (fwRunning() || going) { clearTimeout(FW.poll); FW.poll = setTimeout(() => { fwRead(true).then(() => { if (typeof dashDraw === "function") dashDraw(); fwRedraw(); }); }, 2500); }
  return { runs: {}, steps: S };
}

// ---- 2열 「자료 가져오기」 -------------------------------------------------------------------------------------------------
const FW_HELP_TAKE = "문서 라이브러리(따로 선 서버)에서 끝난 자료 추출의 MD 를 이 문서의 자료로 가져옵니다. 가져온 자료는 에이전트 보기의 자료와 같은 곳에 놓여 「지침 작성」 과 에이전트 요청이 함께 씁니다.\n"
  + "자료 문서를 올리거나 새로 추출하려면 「문서 라이브러리 열기」 로 그 서버의 화면을 엽니다(새 탭). 문서는 바뀌지 않습니다.";
function fwClearWay() { // 떠 있는 에이전트 창이 문서 옆 열(2열)을 가린다(창의 처음 자리 = 패널 바로 왼쪽) — 이 열을 열 때는 창을 닫는다(대화는 남는다 · 상단 바의 에이전트 아이콘 · 「에이전트 보기 열기」 로 다시 연다)
  if (typeof agentFloating === "function" && agentFloating() && typeof agentFloatClose === "function") agentFloatClose();
}
async function fwTakeOpen() {
  fwClearWay();
  const { tools, body } = headsDlg("fwTake", "자료 가져오기", "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로 · 문서는 안 바뀜");
  tools.append(hBtn("문서 라이브러리 열기", () => fwLibOpen(), { title: "자료 문서를 올리고 자료 추출을 하는 따로 선 서버 — 새 탭" }), hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("자료 가져오기 안내", FW_HELP_TAKE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await fwRead(true);
  fwTakeDraw();
}
function fwTakeDraw() {
  if (heads.dlg !== "fwTake") return;
  const body = $("headsDlgBody"), lib = FW.lib || { alive: false, docs: [] }, mats = (FW.gw && FW.gw.materials) || [];
  body.replaceChildren();
  if (!lib.alive) return void body.append(el("div", "fw-empty", lib.why || FW_LIB_DOWN));
  const have = (eid) => mats.some((m) => (m.note || "").includes(`(${eid})`));
  const withX = lib.docs.filter((d) => d.extracts.length);
  if (!withX.length) body.append(el("div", "fw-empty", lib.docs.length ? "끝난 자료 추출이 없습니다 — 문서 라이브러리에서 뽑을 범위를 적고 추출하세요." : "문서 라이브러리에 자료 문서가 없습니다 — 「문서 라이브러리 열기」 로 문서를 올리세요."));
  for (const d of withX) {
    const sec = el("section", "fw-doc"), h = el("h3", null, d.name);
    sec.append(h);
    for (const e of d.extracts) {
      const row = el("div", "fw-x"), meta = el("div", "fw-x-meta"), got = have(e.id);
      const info = [e.span ? `쪽 ${e.span[0]}–${e.span[1]}` : "", `${(e.chars || 0).toLocaleString()}자`, `그림 ${e.figures || 0}`, `수식 ${e.formulas || 0}`].filter(Boolean).join(" · ");
      meta.append(el("strong", null, e.focus || "문서 전체"), el("span", "fw-muted", info));
      if (e.open) meta.append(el("span", "fw-tag warn", `확인 필요 ${e.open}`));
      const take = hBtn(got ? "가져옴" : "가져오기", () => fwTake(e.id), { disabled: got, cls: "btn sm" + (got ? "" : " primary"), title: got ? "이미 이 문서의 자료입니다" : "이 추출의 MD 를 이 문서의 자료로 가져옵니다" });
      const view = hBtn("보기", () => fwLibOpen(`d=${d.id}&x=${e.id}`), { title: "문서 라이브러리에서 이 추출의 MD 와 그림을 봅니다(새 탭)" });
      row.append(meta, view, take);
      sec.append(row);
    }
    body.append(sec);
  }
  if (mats.length) {
    const sec = el("section", "fw-doc");
    sec.append(el("h3", null, `이 문서의 자료 ${mats.length}개`));
    for (const m of mats) { const r = el("div", "fw-x"); r.append(el("div", "fw-x-meta", null)); r.firstChild.append(el("strong", null, m.name), el("span", "fw-muted", `${(m.chars || 0).toLocaleString()}자${m.cut ? " · 잘림" : ""}`)); sec.append(r); }
    body.append(sec);
  }
}
async function fwTake(eid) {
  try {
    const got = await api(`/api/docs/${state.id}/agent/material/library`, { method: "POST", headers: H_JSON, body: JSON.stringify({ extract: eid }) });
    toast(got.reused ? "이미 있는 자료입니다" : `자료로 가져왔습니다 — ${got.name}`);
    if (FW.mats) FW.mats.add(got.id);
    if (typeof agentLoad === "function" && typeof AGENT === "object" && AGENT.loaded) agentLoad(true);
  } catch (e) { toast(e.message || String(e), true); }
  await fwRead(true);
  fwRedraw();
  if (typeof dashDraw === "function") dashDraw();
}

// ---- 2열 「지침 작성」 ---------------------------------------------------------------------------------------------------
const FW_HELP_WRITE = "문서의 자리(본문 헤딩 · 지침이 붙은 표)마다 작성 지침과 받은 자료를 에이전트에 주고, 그 자리에 넣을 글 · 표 채우기 제안을 받습니다(유료 LLM — 자리마다 호출 1번 이상).\n"
  + "작성 지침 = 양식이 적어 둔 것(작성 요령 · ※ 안내 · 각주 항목)과 사람이 그 헤딩에 적은 것(문서의 「지침」 단추). 아래 「이번 작성의 지침」 은 이번 실행의 모든 자리에 함께 갑니다.\n"
  + "문서는 여기서 바뀌지 않습니다 — 제안은 에이전트 보기의 제안 카드로 나오고 「문서에 반영」 을 누른 것만 들어갑니다. 자료에 없는 내용은 만들지 않으며, 에이전트가 지은 글과 자료에 없는 수가 든 제안은 처음부터 고르지 않은 채로 보입니다.";
async function fwWriteOpen() {
  fwClearWay();
  const { tools, body } = headsDlg("fwWrite", "지침 작성", "자리마다 작성 지침 + 자료 → 제안 · 문서는 「문서에 반영」 을 눌러야 바뀝니다");
  tools.append(hBtn("자료 가져오기", () => fwTakeOpen(), { title: "문서 라이브러리에서 추출한 MD 를 이 문서의 자료로" }), hBtn("새로 고침", () => fwRead(true).then(fwRedraw)), hHelp("지침 작성 안내", FW_HELP_WRITE, { note: true }));
  body.append(el("div", "fw-wait", "읽는 중…"));
  await fwRead(true);
  fwWriteDraw();
}
function fwRedraw() { fwTakeDraw(); fwWriteDraw(); }
function fwShown() { const ps = (FW.gw && FW.gw.places) || []; return FW.onlyGuided ? ps.filter((p) => p.n || FW.picks.has(p.id)) : ps; }
function fwWriteDraw() {
  if (heads.dlg !== "fwWrite") return;
  const body = $("headsDlgBody"), foot = $("headsDlgFoot"), gw = FW.gw;
  const keep = body.scrollTop, noteEl = body.querySelector(".fw-note");
  if (noteEl && document.activeElement === noteEl) return void fwFootDraw(foot); // 지침을 적는 동안에는 목록을 다시 그리지 않는다(쓰던 글 · 커서)
  body.replaceChildren();
  if (!gw) return void body.append(el("div", "fw-empty", FW.err || "읽는 중…"));
  if (gw.hwpx === false) return void body.append(el("div", "fw-empty", "지침 작성은 hwpx 문서만 됩니다."));
  // 자료
  const matSec = el("section", "fw-doc"), matBox = el("div", "fw-mats");
  matSec.append(el("h3", null, "쓸 자료"));
  if (!gw.materials.length) matBox.append(el("span", "fw-muted", "자료가 없습니다 — 「자료 가져오기」 로 추출한 MD 를 가져오거나 에이전트 보기에서 파일 · 글을 자료로 주세요."));
  for (const m of gw.materials) {
    const lab = el("label", "fw-mat"), cb = el("input");
    cb.type = "checkbox"; cb.checked = FW.mats.has(m.id);
    cb.addEventListener("change", () => { if (cb.checked) FW.mats.add(m.id); else FW.mats.delete(m.id); fwFootDraw(foot); });
    lab.append(cb, el("span", null, m.name), el("span", "fw-muted", `${(m.chars || 0).toLocaleString()}자`));
    lab.title = m.note || m.head || "";
    matBox.append(lab);
  }
  matSec.append(matBox);
  // 이번 작성의 지침
  const noteSec = el("section", "fw-doc"), note = el("textarea", "fw-note");
  note.rows = 3; note.maxLength = (gw.limits && gw.limits.note) || 1000; note.value = FW.note;
  note.placeholder = "이번 작성의 지침(선택) — 예: 한국선급이 맡은 내용만, 개조식으로 3~5줄, 2차년도 실적 위주로";
  note.addEventListener("input", () => { FW.note = note.value; });
  noteSec.append(el("h3", null, "이번 작성의 지침"), note);
  // 자리
  const plSec = el("section", "fw-doc"), head = el("h3", "fw-places-head"), only = el("label", "fw-mat"), onlyCb = el("input"), shown = fwShown();
  onlyCb.type = "checkbox"; onlyCb.checked = FW.onlyGuided;
  onlyCb.addEventListener("change", () => { FW.onlyGuided = onlyCb.checked; fwWriteDraw(); });
  only.append(onlyCb, el("span", null, "작성 지침이 있는 자리만"));
  const all = hBtn("모두 고르기", () => { for (const p of fwShown()) FW.picks.add(p.id); fwWriteDraw(); }, { title: "보이는 자리를 모두 고릅니다" }), none = hBtn("모두 해제", () => { FW.picks.clear(); fwWriteDraw(); });
  head.append(el("span", null, `채울 자리 — ${shown.length}곳`), only, all, none);
  plSec.append(head);
  if (!shown.length) plSec.append(el("div", "fw-empty", gw.places.length ? "작성 지침이 붙은 자리가 없습니다 — 「작성 지침이 있는 자리만」 을 끄면 모든 헤딩이 보입니다. 헤딩에 지침을 적으려면 문서에서 그 헤딩의 「지침」 단추를 씁니다." : "본문 헤딩이 없습니다 — 헤딩 추출(기본 분석)이 끝났는지 확인하세요."));
  const ran = new Map(((gw.run && gw.run.items) || []).map((i) => [i.id, i]));
  for (const p of shown) plSec.append(fwPlaceEl(p, ran.get(p.id), foot));
  body.append(matSec, noteSec, plSec);
  body.scrollTop = keep;
  fwFootDraw(foot);
}
const FW_ITEM = { queued: ["기다림", ""], running: ["받는 중", "run"], done: ["제안", "ok"], none: ["자료에 없음", ""], failed: ["실패", "fail"], skipped: ["안 함", ""] };
function fwPlaceEl(p, item, foot) {
  const row = el("div", `fw-place${p.kind === "table" ? " is-table" : ""}`), cb = el("input"), main = el("div", "fw-place-main"), name = el("button", "fw-place-name", p.text || (p.kind === "table" ? "표" : "(빈 헤딩)")), tags = el("span", "fw-tags");
  cb.type = "checkbox"; cb.checked = FW.picks.has(p.id); cb.setAttribute("aria-label", `${p.text} 고르기`);
  cb.addEventListener("change", () => { if (cb.checked) FW.picks.add(p.id); else FW.picks.delete(p.id); fwFootDraw(foot); });
  name.type = "button"; name.title = "문서의 그 자리로";
  name.addEventListener("click", () => scrollToBlock(p.id));
  row.style.setProperty("--fw-depth", String(Math.max(0, Math.min(5, (p.depth || 1) - 1))));
  if (p.kind === "table") tags.append(el("span", "fw-tag", "표"));
  if (p.n) tags.append(el("span", "fw-tag guide", `지침 ${p.n}`));
  if (p.user) tags.append(el("span", "fw-tag user", "사람 지침"));
  if (p.filled) tags.append(el("span", "fw-tag", "글 있음"));
  if (item) { const [word, cls] = FW_ITEM[item.state] || [item.state, ""]; const t = el("span", `fw-tag ${cls}`, item.state === "done" ? `제안 ${item.proposals}` : word); t.title = item.error || item.reply || ""; tags.append(t); }
  main.append(name, tags);
  if (p.guides.length) {
    const det = el("details", "fw-guides"), sum = el("summary", null, "작성 지침 보기");
    det.append(sum);
    for (const g of p.guides) { const li = el("div", "fw-guide"); li.append(el("span", `fw-tag ${g.src === "user" ? "user" : "guide"}`, g.src === "user" ? "사람" : g.kind || "양식"), el("span", null, g.text)); det.append(li); }
    main.append(det);
  }
  row.append(cb, main);
  return row;
}
function fwFootDraw(foot) {
  if (!foot || heads.dlg !== "fwWrite") return;
  const gw = FW.gw || {}, run = gw.run, n = FW.picks.size, mats = FW.mats ? FW.mats.size : 0, most = (gw.limits && gw.limits.places) || 40;
  foot.replaceChildren();
  if (run && run.state === "running") {
    const done = run.items.filter((i) => i.state !== "queued" && i.state !== "running").length;
    foot.append(el("span", "fw-muted", `제안 받는 중 — 자리 ${done}/${run.items.length}`), hBtn("멈춤", async () => { try { await api(`/api/docs/${state.id}/guide-write/stop`, { method: "POST" }); toast("남은 자리는 돌리지 않습니다"); } catch (e) { toast(e.message, true); } }, { title: "도는 자리는 끝까지 받고, 남은 자리는 돌리지 않습니다" }));
    return;
  }
  const why = !gw.enabled ? "LLM 을 쓸 수 없습니다" : !mats ? "쓸 자료를 고르세요" : !n ? "채울 자리를 고르세요" : n > most ? `한 번에 ${most}곳까지입니다` : "";
  if (run) {
    const got = run.items.reduce((s, i) => s + (i.proposals || 0), 0), failed = run.items.filter((i) => i.state === "failed").length, none = run.items.filter((i) => i.state === "none").length;
    foot.append(el("span", "fw-muted", `마지막 실행 — 제안 ${got}개${none ? ` · 자료에 없음 ${none}곳` : ""}${failed ? ` · 실패 ${failed}곳` : ""}`));
    if (got && toolShown("Agent")) foot.append(hBtn("에이전트 보기 열기", () => showTab("Agent"), { title: "받은 제안 카드를 보고 「문서에 반영」 을 누릅니다" }));
  }
  foot.append(el("span", "fw-grow"), hBtn(`제안 받기${n ? ` (${n}곳)` : ""}`, () => fwRun(), { cls: "btn sm primary", disabled: !!why, title: why || `고른 자리 ${n}곳의 제안을 받습니다 — 유료 LLM(자리마다 호출 1번 이상) · 문서는 바뀌지 않습니다` }));
}
async function fwRun() {
  const places = [...FW.picks], materials = [...(FW.mats || [])];
  if (!window.confirm(`유료 LLM 으로 자리 ${places.length}곳의 제안을 받습니다(자리마다 호출 1번 이상 · 수십 초씩). 문서는 바뀌지 않습니다. 진행할까요?`)) return;
  try {
    const got = await api(`/api/docs/${state.id}/guide-write/run`, { method: "POST", headers: H_JSON, body: JSON.stringify({ places, materials, note: FW.note }) });
    FW.watch = got.run.id;
    if (FW.gw) FW.gw.run = got.run;
    toast(`지침 작성을 시작했습니다 — 자리 ${got.run.items.length}곳`);
  } catch (e) { return toast(e.message || String(e), true); }
  fwRedraw();
  fwPoll();
  if (typeof dashDraw === "function") dashDraw();
}
function fwPoll() { // 도는 동안 2초마다 — 끝나면 에이전트 보기의 대화를 다시 읽는다(fwRead)
  clearTimeout(FW.poll);
  if (!fwRunning()) return;
  FW.poll = setTimeout(async () => { await fwRead(true); fwRedraw(); if (typeof dashDraw === "function") dashDraw(); fwPoll(); if (!fwRunning()) toast("지침 작성이 끝났습니다 — 에이전트 보기의 제안 카드를 확인하세요"); }, 2000);
}
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { guideWrite: "지침 작성" }); // 작업 기록의 표시 이름(app.js LOG_KIND — doc_agent.js 가 에이전트 기록의 이름을 더하는 것과 같은 방식)
