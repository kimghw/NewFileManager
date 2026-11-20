// 취합 간단 모드(spec_취합 ② §8 · 전제 jobs/plan_merge.md 「간단 모드 · 세부 작업 모드」 — 2026-11-12 사용자 "여기서 취합은 문서 여러개 올려 놓고 목적문서 하나만 선택하면 자동으로 취합까지 다 하도록구현해줘.. 뭔가 여기서는 간단모드,,, 그리고 이제 세부적인 작업은 세부작업 모드로 해서 지금처럼").
// 시작 화면: 문서 목록(home_files.js — spec_작업 ② §15-1, 2026-11-13 옛 고르기 패널 #quickPanel 을 합침)에서 목적 문서(취합본)를 고르고 「사업계획서 취합」 카드 → 「자동 진행」 이면 확인 한 번 뒤 끝까지, 아니면 올리고 등록만.
// 목적 문서는 home_files.js 가 올려 연다 → 여기 gatherQuickRun 이 기관 문서를 맡는다.
// 차례(화면이 지휘 — gather.js 의 「한 번에 진행」 몸통 gatherRunStage 를 그대로 부른다): 기관 문서 올리기·등록 → 1단계(구분 기준) → 2단계(구조 확인 · 기준본) → 3단계(자동 지정 → LLM 검토 → 넣기 계획 → 반영).
// 진행·결과 = 취합 카드 안 간단 모드 줄(.gt-quick — gather.js gatherQuickEl 이 끼운다). 화면은 그대로 세부 작업 모드다. app.js·gather.js 다음에 읽는다(index.html).

const GQ_WHY = { assigned: "이미 정해져 있음", tie: "작성 내용이 가장 많은 기관이 둘 이상", noOrg: "기관 자리에 쓴 내용이 없음" }; // 자동 지정(POST …/auto)의 못 정한 까닭 — 그 밖은 GT_REASON
let gqRun = null;   // 돌린(돌리는) 간단 모드 {job, plan(취합본 작업 id), name, llm, uploadOnly, items[{file, name, pid?, err?, kept?}], auto(Set — 자동 지정할 기관 문서), log{기관 문서 id: {org, by, why, done, skip, llm}}, note, t0, stop, busy, timer, end{ok, text} | null}
const gqHwp = (f) => /\.hwp$/i.test(f.name);


// ---- 목적 문서가 열린 뒤 → 차례대로(gqGo) -------------------------------------------------------------------------
async function gatherQuickRun(planId, name, parts, { llm = true, uploadOnly = false, aliases = new Map() } = {}) { // home_files.js 가 목적 문서(취합본)를 열고 TASK 를 적은 뒤 부른다 — 기관 문서는 목록 차례
  if (state.id !== planId) return;
  gqRun = { job: (state.task && state.task.job) || "plan_merge", plan: planId, name, llm, uploadOnly, items: parts.map((f) => ({ file: f, name: f.name, alias: aliases.get(f) || "" })), auto: new Set(), log: {}, note: "", t0: Date.now(), stop: false, busy: false, end: null };
  await gqGo(gqRun);
}
async function gqGo(run) { // 목적 문서가 열린 뒤 — 남은 기관 문서 올리기 → (등록만이면 끝) → 1단계 → 2단계. 「이어서」 도 이것
  if (gqRun !== run || run.busy) return;
  Object.assign(run, { busy: true, stop: false, end: null, note: "" });
  run.timer = setInterval(gatherQuickSync, 1000);
  const at = (note) => { if (run.stop) gatherHalt("눌러서 멈췄습니다 — 끝난 것은 그대로입니다"); if (state.id !== run.plan) gatherHalt("다른 문서를 열어 멈췄습니다"); run.note = note; gqDraw(); };
  let end;
  try {
    at("취합 상태 읽기");
    taskPaneShow(); // 보통 패널 「작업 개요」 — 에이전트 보기가 이끌고 있으면 그대로(app.js: 진행은 에이전트 보기의 진행 카드가 보인다 — spec_작업에이전트 ② §7)
    for (const it of run.items) if (!it.pid && it.err && !it.skip) it.err = ""; // 「이어서」 — 못 올린 문서는 다시 올려 본다(목적 문서와 같은 파일만 빼고: astra 11-16 — 전에는 한 번 실패하면 다시 올릴 길이 없었다)
    await divShow();
    await gatherLoad();
    const plan = gatherPlan(), V = gt().view;
    if (!plan || plan.id !== run.plan) gatherHalt("목적 문서가 사업계획서(취합본)로 잡히지 않았습니다 — 작업 개요의 첨부 파일 종류를 확인하세요(양식 판정이 다른 종류로 정했을 수 있음)");
    if (!V) gatherHalt(`취합 상태를 읽지 못했습니다${gt().err ? `: ${gt().err}` : ""}`);
    if (V.frame && V.frame.stale) gatherHalt("이 취합본의 배포 기준본이 낡았습니다(기준본 뒤 프로젝트 구성을 다시 반영함) — 2단계 「문서 프레임 작성」 에서 기준본을 새로 만들지 정한 뒤 「이어서」 를 누르세요");
    const todo = run.items.filter((x) => !x.pid && !x.err);
    for (const [k, it] of todo.entries()) {
      at(`기관 문서 올리는 중 ${k + 1}/${todo.length} — ${it.name}${gqHwp(it) ? "(hwpx 로 바꿈)" : ""}`);
      await gqAddPart(run, it);
    }
    const named = run.items.filter((it) => it.pid && it.alias && !it.aliasSaved);
    for (const it of named) { // 올린 뒤 멈췄다가 이어도 약칭은 해당 기관 문서에 저장한다.
      at(`기관 문서 약칭 저장 — ${it.name}`);
      try {
        await api(`/api/works/${it.pid}/alias`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ alias: it.alias }) });
        Object.assign(it, { aliasSaved: true, aliasErr: "" });
      } catch (e) { it.aliasErr = `약칭 저장 실패: ${gatherErr(e)}`; }
    }
    if (todo.length || named.length) { await loadWorks(); await gatherLoad(); }
    const got = run.items.filter((x) => x.pid).length, failed = run.items.filter((x) => x.err && !x.skip).length; // 못 올린 문서(「이어서」 가 다시 올린다) — 목적 문서와 같은 파일(skip)은 세지 않는다
    if (run.uploadOnly) end = { ok: true, text: `올리고 등록했습니다 — 기관 문서 ${got}개${failed ? ` · 못 올림 ${failed}개` : ""}. 세부 작업 모드에서 단계마다 진행하세요` };
    else {
      if (!got) gatherHalt("넣을 기관 문서가 없습니다(모두 올리지 못함)");
      at("목적 문서의 헤딩·표 분석(스크립트) 기다리는 중");
      await gatherAnalyze(run.plan, { first: true }, () => gqRun === run && !run.stop && state.id === run.plan);
      // 1단계 구분 기준(값이 없으면 문서에서 읽어 확정 — 시작 때의 확인 한 번이 확정의 확인) → 2단계 문서 프레임 작성 → 3단계 내용 매핑(spec_취합 ② §9-1 · spec_작업 ② §18)
      const sname = (id) => { const s = GT_STAGES.find((x) => x.id === id); return `${s.no} ${s.name}`; };
      at(sname("config"));
      const e0 = await gatherRunStage("config", gatherPlan(), { read: true, quiet: true });
      if (!e0.ok) gatherHalt(`${sname("config")}에서 멈춤 — ${e0.text}`);
      at(sname("frame"));
      const e1 = await gatherRunStage("frame", gatherPlan(), { quick: true, quiet: true });
      if (!e1.ok) gatherHalt(`${sname("frame")}에서 멈춤 — ${e1.text}`);
      at(sname("map"));
      const e2 = await gatherRunStage("map", gatherPlan(), { auto: run.auto, llm: run.llm, log: run.log, quiet: true });
      if (!e2.ok) gatherHalt(`${sname("map")}에서 멈춤 — ${e2.text}`);
      end = { ok: true, text: (e2.none ? "넣을 것이 남은 기관 문서가 없습니다" : e2.text) + (failed ? ` · 못 올린 문서 ${failed}개(「이어서」 로 다시 올립니다)` : "") };
    }
  } catch (e) { end = { ok: false, text: e instanceof GatherHalt ? e.message : `오류 — ${gatherErr(e)}` }; if (!(e instanceof GatherHalt)) console.warn(e); }
  clearInterval(run.timer);
  const aliasFailed = run.items.filter((it) => it.aliasErr).length;
  if (aliasFailed) end.text += ` · 약칭 저장 실패 ${aliasFailed}개(이어서 다시 시도)`;
  Object.assign(run, { busy: false, end, note: "" });
  if (gqRun === run) { gatherDraw(); gqDraw(); }
  toast(end.ok ? `간단 모드 — ${end.text}` : `간단 모드가 멈췄습니다 — ${end.text}`, !end.ok || !!aliasFailed);
}
async function gqAddPart(run, it) { // 기관 문서 하나 올리고 이 취합에 넣는다 — 같은 이름의 기관 문서가 이미 있으면 그것을 쓴다(수정본은 다시 넣지 않음 — 할 일 프롬프트)
  const stem = (n) => String(n || "").replace(/\.(hwpx?|docx)$/i, "").normalize("NFC").trim();
  const same = ((gt().view || {}).parts || []).find((p) => stem(p.name) === stem(it.name));
  if (same) { Object.assign(it, { pid: same.work, kept: true }); run.auto.add(same.work); return; }
  const up = async (fresh) => { const fd = new FormData(); fd.append("file", it.file); return api(`/api/docs${fresh ? "?new=1" : ""}`, { method: "POST", body: fd }); };
  // 등록할 취합본은 **이 실행의 목적 문서**(run.plan)로 못 박는다 — gatherUrl 은 「지금 화면의 취합본」 을 따라가므로, 올리는 사이 다른 취합본을 열면 그쪽에 등록됐다(astra 11-16 P1). 그 사이 문서가 바뀌었으면 등록하지 않고 멈춘다
  const put = (pid) => { if (state.id !== run.plan) gatherHalt("다른 문서를 열어 멈췄습니다 — 올린 기관 문서는 등록하지 않았습니다"); return api(`/api/docs/${run.plan}/gather${gatherSeg(pid)}`, { method: "PUT", headers: H_JSON, body: "{}" }); };
  let d, V;
  try {
    d = await up(false); // 같은 파일로 하던 작업이면 그 작업
    if (d.docId === run.plan) { Object.assign(it, { err: "목적 문서와 같은 파일 — 건너뜀", skip: true }); return; }
    try { V = await put(d.docId); }
    catch (e) { if (e.status !== 400) throw e; d = await up(true); V = await put(d.docId); } // 그 작업은 다른 프로젝트·TASK·라운드의 것 — 새 작업으로
  } catch (e) { if (e instanceof GatherHalt) throw e; it.err = `올리지 못함 — ${gatherErr(e)}`; return; }
  it.pid = d.docId;
  run.auto.add(d.docId);
  if (state.id === run.plan) { gatherViewSet(V); gatherDraw(); }
  api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 2단계 자리 연결이 없으면 기다려 다시 건다
}

// ---- 간단 모드 줄(취합 카드 — ② §8-6) --------------------------------------------------------------------------------
function gqText(R) {
  if (R.busy) return `자동 취합 — ${R.note || "진행 중"} · ${fmtDur((Date.now() - R.t0) / 1000)}${R.stop ? " · 이 일이 끝나면 멈춥니다" : ""}`;
  if (R.end) return `${R.end.ok ? "끝남" : "멈춤"} — ${R.end.text}`;
  return "자동 취합 — 준비";
}
function gqDraw() { const old = document.querySelector("#gatherFlow .gt-quick"); if (old) old.replaceWith(gatherQuickLineEl()); }
function gatherQuickSync() { const m = document.querySelector("#gatherFlow .gt-quick-msg"); if (m && gqRun && gqRun.busy) m.textContent = gqText(gqRun); else gqDraw(); } // 1초마다 — 글만
function gqRowText(R, it) { // 문서 한 줄 → [반영할 기관, 결과]
  if (it.err) return ["", it.err];
  const p = gatherPart(it.pid), V = gt().view || {}, L = R.log[it.pid] || {}, orgName = (k) => ((V.orgs || []).find((o) => o.key === k) || {}).name || k;
  if (!p) return ["", "이 취합에서 빠짐"];
  const org = (p.orgs || []).length === 1 ? `${orgName(p.orgs[0])}${p.orgsBy ? ` (${p.orgsBy === "name" ? "파일 이름" : "추천"})` : ""}` : (p.orgs || []).length ? `기관 ${p.orgs.length}곳` : "미지정";
  const c = p.counts || {}, left = [c.overlap ? `겹침 ${nf(c.overlap)}` : "", c.unknownPlace ? `확인 필요 ${nf(c.unknownPlace)}` : "", c.structure ? `표 구조 다름 ${nf(c.structure)}` : ""].filter(Boolean).join(" · ");
  const why = L.why && !(p.orgs || []).length ? GQ_WHY[L.why] || GT_REASON[L.why] || L.why : "";
  const res = L.done ? `넣음 — ${L.done}` : L.skip ? `건너뜀 — ${why || L.skip}` : gatherHard(p.reasons).length ? `확인 필요 — ${gatherReasons(gatherHard(p.reasons))}`
    : gatherLow(p) ? GT_REASON.lowMatch : it.kept ? "이미 든 문서(같은 이름) — 그대로 씀" : c.same && !gatherPartTodo(p) ? "이미 들어 있음" : R.busy ? "" : "넣을 것 없음";
  return [org, [res, left, L.llm || "", it.aliasErr || ""].filter(Boolean).join(" · ")];
}
function gatherQuickLineEl() { // gather.js gatherQuickEl 이 부른다 — 간단 모드로 돌린 이 취합본이 아니면 빈 자리(숨김)
  const box = el("div", "gt-quick"), R = gqRun, plan = gatherPlan();
  if (!R || !plan || R.plan !== plan.id) { box.hidden = true; return box; }
  const head = el("div", "gt-quick-head"), spin = el("i", "dv-phase-spin"), msg = el("span", "gt-quick-msg", gqText(R));
  box.dataset.kind = R.busy ? "run" : R.end ? (R.end.ok ? "done" : "halt") : "next";
  spin.hidden = !R.busy;
  spin.style.animationDelay = `-${Date.now() % 800}ms`; // 다시 그려도 처음부터 다시 돌지 않게(design.md §7)
  msg.setAttribute("role", "status");
  head.append(el("strong", null, "간단 모드"), hHelp("간단 모드 설명", "시작 화면에서 문서를 한꺼번에 올려 목적 문서만 고르고 끝까지 자동으로 한 취합입니다. 아래 줄은 기관 문서마다 반영할 기관(정한 길)과 결과 — 줄을 누르면 그 문서의 「기관 작성 내용」 이 열립니다.\n"
    + "넣지 않고 남긴 것(겹침 · 확인 필요)은 세부 작업 모드의 2단계 목록이나 끌어 넣기로 이어 갑니다."));
  const st = el("div", "gt-quick-state"), acts = el("span", "gt-quick-acts"); // 단추는 오른쪽 끝에 한 묶음
  st.append(spin, msg);
  if (R.busy) {
    const stop = hBtn(R.stop ? "멈추는 중…" : "멈춤", () => { R.stop = true; if (gatherRun) gatherRun.stop = true; gqDraw(); gatherStageSync(); }, { disabled: R.stop, title: "지금 하는 일이 끝나면 멈춥니다 — 끝난 것은 그대로 남습니다" });
    stop.dataset.quickStop = "1";
    acts.append(stop);
  } else {
    if (R.end && (!R.end.ok || R.items.some((it) => it.aliasErr || (!it.pid && it.err && !it.skip)))) { // 멈춤 · 약칭 저장 실패 · 못 올린 문서가 남음(끝났어도 — 다시 올려 본다)
      const again = hBtn("이어서", () => gqGo(R), // 확인 창 없이 바로(2026-11-18 사용자 「이런 알람좀 주지마」: design.md §18 「확인 창」)
        { cls: "btn sm primary", disabled: !!gatherRun, title: `멈춘 곳부터 남은 일을 이어서 합니다 — 남은 기관 문서 올리기 → 1단계(남았으면) → 2단계. 앞서 넣은 것은 다시 넣지 않습니다${R.llm ? " · LLM 검토는 아직 안 한 문서만(유료)" : ""}` });
      again.dataset.quickAgain = "1";
      acts.append(again);
    }
    const close = hBtn("닫기", () => { if (gqRun === R) gqRun = null; gqDraw(); }, { title: "간단 모드 줄을 닫습니다 — 넣은 내용과 기관 문서 줄은 그대로입니다" });
    close.dataset.quickClose = "1";
    acts.append(close);
  }
  head.append(acts);
  box.append(head, st);
  const rows = R.items.filter((it) => it.pid || it.err);
  if (rows.length) {
    const ol = el("ol", "gt-quick-rows");
    ol.setAttribute("aria-label", "간단 모드 — 기관 문서마다 결과");
    for (const it of rows) {
      const [org, res] = gqRowText(R, it), li = el("li"), b = el("button", "gt-quick-row");
      b.type = "button";
      b.disabled = !it.pid || !gatherPart(it.pid);
      b.title = it.pid ? `「${it.name}」 — 기관 작성 내용 보기(문서 옆 열)` : it.name;
      b.onclick = () => { if (it.pid) gatherListOpen(it.pid); };
      if (it.pid) b.dataset.quickRow = it.pid;
      b.append(el("span", "gt-quick-name", it.name), el("span", "gt-quick-org", org), el("span", "gt-quick-res", res));
      li.append(b);
      ol.append(li);
    }
    box.append(ol);
  }
  return box;
}
