// 같은 양식 취합(조립 틀 「N → 1 · 같은 양식」 — task_catalog.js taskIsCollect · spec_취합 ② §10: 2026-11-24 사용자 "1개 사업계획서 그리고 N개의 제출된 문서를 가지고 사업계획서에 넣고 …
// 수정된 문서가 오면 이전 제출된 내용과 비교해서 수정된 부분만 적용하는 워크플로우")의 **「기관 문서」 목록** — 패널 대시보드(dashboard.js dashFlowLive)와 첫 화면의 대시보드(home_dash.js)가 같은 함수로 그린다(보기마다 다른 것은 opt 에만).
// 등록부 = 서버(GET /api/docs/{목적 id}/collect — app/merge_collect_api.py: ② §10-4 · §10-6). 문서마다 한 줄: 파일 이름 · **반영할 기관**(PUT …/collect/parts/{part} {orgs}) · **공통 자리 포함**({common}) · **수정본**({revOf}) · 상태 꼬리표 · 서버의 글.
// 미지정 문서가 있으면 머리에 「자동 지정」(POST …/auto 를 미지정 문서마다) · 「기관 문서 올리기…」(여러 파일 — 같은 묶음(프로젝트 · 워크플로우 · 라운드)의 기관 문서로: 다른 기관 문서를 밀어내지 않는다).
// 수정본으로 등록한 문서의 줄에는 「수정 계획 보기」(POST …/revise/plan — 문서는 안 바뀜: 그 줄 아래에 편다) → 「수정본 반영」(…/revise/apply {planId} — 문서가 바뀐다: 누르기 전에 한 줄 확인).
// 여기는 **고르기와 보기**뿐이다 — 넣는 것은 대시보드의 묶음 「한 번에 진행」 · 줄의 「이 단계만 진행」(서버 쪽 실행기)이 한다. 큰 목록은 창을 띄우지 않고 그 자리에서 편다.
// 기대는 이름: app.js api · el · hBtn · toast · H_JSON · panel_help.js hHelp. 그 밖의 것(문서 열기 · 다시 읽기 · 올린 뒤의 일)은 부르는 쪽이 opt 로 준다(이 파일은 state · 대시보드의 이름을 읽지 않는다).
const COLLECT = { by: {} }; // 목적 문서 id → {view 등록부 | null, err, at 읽은 때, loading, busy 지금 보내는 요청의 이름, plan{part, view, err, busy} | null, redraw 마지막에 그린 보기의 다시 그리기}
const COLLECT_STATE = { unassigned: "미지정", todo: "넣을 차례", revision: "수정본", superseded: "수정본 있음", done: "반영함", left: "남은 것 있음" }; // 등록부의 상태(② §10-4 「상태」) → 꼬리표
const COLLECT_BY = { name: ["파일 이름으로", "반영할 기관을 파일 이름에 든 기관 이름으로 정했습니다 — 다르면 고르기에서 바꾸세요"], label: ["문서의 기관 라벨로", "반영할 기관을 문서의 기관 라벨이 밝힌 이름으로 정했습니다 — 다르면 고르기에서 바꾸세요"] };
const COLLECT_ITEM = { ready: "고칠 곳", overlap: "겹침", hold: "확인 필요", missing: "수정본에 없음" }; // 수정 계획 항목의 상태(② §10-5) — same(이미 같음)은 서버가 목록에서 뺀다
const COLLECT_HELP = "기관이 같은 양식으로 따로 써 보낸 문서들입니다. 문서마다 「반영할 기관」 을 정해야 그 기관의 자리에 넣습니다 — 미지정인 문서는 넣지 않습니다.\n"
  + "반영할 기관 — 이 문서의 내용을 사업계획서의 어느 기관 자리에 넣을지. 파일 이름이나 문서의 기관 라벨로 알 수 있으면 「자동 지정」 이 정합니다(사람이 고른 것은 바꾸지 않습니다).\n"
  + "공통 자리 포함 — 기관이 안 걸린 절 · 표(공통 자리)에도 이 문서의 내용을 넣습니다. 기본은 꺼짐 — 그 기관의 자리에만 넣습니다.\n"
  + "수정본 — 앞서 낸 문서를 고쳐 다시 보낸 문서면 「○○ 의 수정본」 을 고릅니다. 수정본은 통째로 다시 넣지 않고, 앞 제출본과 견줘 바뀐 곳만 고칩니다(「수정 계획 보기」 → 「수정본 반영」). 사람이 고친 자리는 겹침으로 남기고 지우지 않습니다.\n"
  + "넣기는 묶음의 「한 번에 진행」 이 등록한 차례대로 합니다 — 여기서 고르는 것으로는 문서가 바뀌지 않습니다.";
const COLLECT_COMMON_HELP = "기관이 안 걸린 절 · 표(공통 자리)에도 이 문서의 내용을 넣습니다 — 기본은 꺼짐: 그 기관의 자리에만 넣습니다";

function collectOf(tid) { return (COLLECT.by[tid] = COLLECT.by[tid] || { view: null, err: "", at: 0, loading: null, busy: "", plan: null, redraw: null }); }
function collectTouch(tid) { if (COLLECT.by[tid]) COLLECT.by[tid].at = 0; } // 등록부가 바뀌었을 수 있다(실행이 끝남 · 문서를 올림) — 다음 그리기가 다시 읽는다
const collectView = (tid) => (COLLECT.by[tid] || {}).view || null; // 읽어 둔 등록부(문서 카드의 이름 — 반영할 기관 — 이 읽는다) | null
function collectPart(tid, part) { const V = collectView(tid); return (V && (V.parts || []).find((p) => p.work === part)) || null; }
// 문서 카드의 이름 — 「[기관 약칭] 파일 이름」(spec_취합 ② §11 — 반영할 기관이 없으면 「[미지정] 파일 이름」 · 등록부를 아직 못 읽었으면 준 이름)
function collectDocTag(tid, part) { // 그 기관 문서의 꼬리표 「[가나]」 · 「[미지정]」 | ""(등록부를 아직 못 읽음 · 이 등록부의 문서가 아님) — org_short.js orgTagText
  const V = collectView(tid), p = collectPart(tid, part);
  if (!p || typeof orgTagText !== "function") return "";
  const names = (p.orgNames || p.orgs || []).map(String), all = ((V && V.orgs) || []).map((o) => o.name);
  return orgTagText(names, all.length ? all : names);
}
function collectDocName(tid, part, name = "") { const p = collectPart(tid, part), file = (p && p.name) || name || "", tag = collectDocTag(tid, part); return tag ? `${tag} ${file}` : file; }
const collectDocOrgs = (tid, part) => ((collectPart(tid, part) || {}).orgNames || []).join(" · "); // 카드 꼬리표의 풍선 도움말 — 반영할 기관의 온 이름
function collectSig(tid) { // 다시 그릴지(대시보드의 sig 에 든다) — 등록부 · 보내는 요청 · 편 수정 계획
  const C = COLLECT.by[tid];
  if (!C) return 0;
  const V = C.view, P = C.plan;
  return [V ? [V.version, (V.orgs || []).map((o) => o.key), (V.parts || []).map((p) => [p.work, p.name, p.state, p.text, p.orgs, p.orgsBy, p.common, p.revOf])] : 0, C.err, C.busy, !!C.loading && !V,
    P ? [P.part, P.busy, P.err, P.view ? [P.view.planId, P.view.todo, P.view.text, (P.view.items || []).length] : 0] : 0];
}

function collectRead(tid, force = false) { // 등록부를 읽는다 → 약속 | null(10초 안에 읽은 것이 있다) — 읽으면 마지막 보기를 다시 그린다
  const C = collectOf(tid), seq = C.seq || 0;
  if (C.loading && C.loadSeq === seq) return C.loading; // 읽는 중(같은 판) — 그 약속. 그 사이 고르기 · 올리기를 보냈으면(판이 올랐다) 그 읽기의 답은 버려지니 새로 읽는다
  if (!force && C.at && Date.now() - C.at < 10000) return null;
  const mine = (async () => {
    let view = null, err = "";
    try { view = await api(`/api/docs/${tid}/collect`); }
    catch (e) { err = e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켠 뒤에 볼 수 있습니다" : e.message || String(e); }
    if (C.loading === mine) C.loading = null;
    if ((C.seq || 0) !== seq) return; // 그 사이 고르기 · 올리기를 보냈다 — 이 답은 그 앞의 등록부일 수 있다(버린다: 그 요청이 새 등록부를 받는다)
    Object.assign(C, { at: Date.now(), err, ...(view ? { view } : {}) });
    if (C.plan && view && !(view.parts || []).some((p) => p.work === C.plan.part && p.revOf)) C.plan = null; // 수정본 표시를 푼 문서의 계획은 걷는다
    if (C.redraw) C.redraw();
    if (view && typeof orgTagsSync === "function") orgTagsSync(); // 문서 꼬리표(이름 줄 · 둘째 면 탭 · 「도구」 단추)의 기관 약칭 — 반영할 기관이 바뀌었을 수 있다(org_short.js)
  })();
  Object.assign(C, { loading: mine, loadSeq: seq });
  return mine;
}

const collectWhy = (e) => (e && e.body && (e.body.message || (e.body.detail && e.body.detail.message))) || (e && e.message) || String(e); // 서버의 글 그대로(400 · 409 · 422)
async function collectSend(tid, name, fn, opt) { // 요청 하나(고르기 · 자동 지정 · 올리기 · 수정 계획 · 반영) — 그동안 다른 고르기를 꺼 둔다. fn → 알릴 글 | "" · 400 · 409 의 글은 그대로 알림으로
  const C = collectOf(tid);
  if (C.busy) return;
  C.busy = name;
  C.seq = (C.seq || 0) + 1; // 이 요청 앞에 떠난 읽기의 답은 버린다(낡은 등록부가 방금 고친 것을 덮지 않게 — collectRead)
  if (C.redraw) C.redraw();
  let said = "", warn = false;
  try { said = (await fn(C)) || ""; }
  catch (e) { said = collectWhy(e); warn = true; }
  if (said) toast(said, warn);
  if (C.redraw) C.redraw(); // 새 등록부로 바로 — 고르기는 아래 다시 읽기가 끝날 때까지 꺼 둔 채(그 사이 또 고쳐 서버 상태와 어긋나지 않게)
  if (opt && opt.after) { try { await opt.after(); } catch (e) { console.warn(e); } } // 서버 상태(줄의 상태 글 · 묶음의 남은 수)도 바뀐다 — 그 보기가 다시 읽는다
  C.busy = "";
  if (C.redraw) C.redraw();
}

function collectPut(tid, part, body, opt) { // 반영할 기관 · 공통 자리 포함 · 수정본 — 사람이 정한 것(orgsBy user)
  return collectSend(tid, `put:${part}`, async (C) => {
    const view = await api(`/api/docs/${tid}/collect/parts/${part}`, { method: "PUT", headers: H_JSON, body: JSON.stringify(body) });
    Object.assign(C, { view, at: Date.now(), err: "" });
    if (C.plan && (C.plan.part === part || "revOf" in body)) C.plan = null; // 지정이 바뀌면 서버가 계획을 버린다 — 편 수정 계획도 걷는다
    return "";
  }, opt);
}

function collectAuto(tid, opt) { // 「자동 지정」 — 미지정 문서마다(등록한 차례) · 못 정한 문서는 그 까닭과 함께 미지정으로 남는다
  return collectSend(tid, "auto", async (C) => {
    const todo = ((C.view && C.view.parts) || []).filter((p) => p.state === "unassigned" && !(p.orgs || []).length), set = [], kept = [];
    for (const p of todo) {
      const r = await api(`/api/docs/${tid}/collect/parts/${p.work}/auto`, { method: "POST" });
      Object.assign(C, { view: r, at: Date.now(), err: "" });
      const A = r.auto || {};
      if (A.org) set.push(`${p.name} → ${((r.orgs || []).find((o) => o.key === A.org) || {}).name || A.org}`); else kept.push(`${p.name}${A.why ? `(${A.why})` : ""}`);
    }
    if (!todo.length) return "미지정인 기관 문서가 없습니다";
    return [`자동 지정 — ${set.length}개 지정${set.length ? `(${set.join(" · ")})` : ""}`, kept.length ? `${kept.length}개는 정하지 못해 미지정으로 둡니다 — 고르기에서 정하세요: ${kept.join(" · ")}` : ""].filter(Boolean).join("\n");
  }, opt);
}

// 「기관 문서 올리기…」 — 여러 파일을 고른 차례대로 하나씩: 새 작업으로 올리고(?new=1 — 열지 않는다) 같은 묶음의 기관 문서로 적고 헤딩 · 표 분석(스크립트)을 걸어 둔다. 하나가 실패하면 그 뒤는 멈춘다.
// scope = {job, project, round, kind(기관 문서 종류 — part)} — 목적 문서의 묶음(부르는 쪽이 준다). 다른 기관 문서는 그대로다(이관의 원본 칸 올리기 taskSlotSet 처럼 칸의 문서를 바꾸지 않는다)
function collectUpload(tid, files, scope, opt) {
  const list = [...(files || [])];
  if (!list.length) return null;
  const bad = list.find((f) => !/\.hwpx?$/i.test(f.name));
  if (bad) { toast(`기관 문서는 hwp·hwpx 파일만 올릴 수 있습니다 — 「${bad.name}」`, true); return null; }
  if (!scope || !scope.project) { toast("프로젝트 이름을 먼저 적으세요 — 올린 문서를 그 프로젝트에 넣습니다(「작업 개요」)", true); return null; }
  return collectSend(tid, "upload", async (C) => {
    let n = 0;
    for (const f of list) {
      toast(/\.hwp$/i.test(f.name) ? `${f.name} — hwpx 로 바꿔 올리는 중…(한글이 변환)` : `${f.name} 올리는 중…(${n + 1}/${list.length})`);
      const fd = new FormData();
      fd.append("file", f);
      let d;
      try { d = await api("/api/docs?new=1", { method: "POST", body: fd }); }
      catch (e) { throw new Error(`「${f.name}」 을 올리지 못했습니다: ${e.message}${n ? ` — 앞의 ${n}개는 넣었습니다` : ""}`); }
      try { await api(`/api/works/${d.docId}/task`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ kind: "rnd", file: scope.kind || "part", job: scope.job, project: scope.project, ...(scope.round && scope.round > 1 ? { round: scope.round } : {}) }) }); }
      catch (e) { throw new Error(`「${f.name}」 을 이 워크플로우의 기관 문서로 넣지 못했습니다: ${collectWhy(e)}${n ? ` — 앞의 ${n}개는 넣었습니다` : ""}`); }
      api(`/api/docs/${d.docId}/headings`, { method: "POST", headers: H_JSON, body: JSON.stringify({ first: true }) }).catch(() => {}); // 첫 분석(스크립트) — 못 걸어도 「문서 검토」 가 분석부터 한다
      n += 1;
    }
    C.at = 0;
    if (opt && opt.uploaded) { try { await opt.uploaded(); } catch (e) { console.warn(e); } } // 작업 목록 · 문서 칸을 다시 읽는다(그 보기의 것)
    await collectRead(tid, true);
    return `기관 문서 ${n}개를 넣었습니다 — 「반영할 기관」 을 정하세요(「자동 지정」 · 고르기)`;
  }, opt);
}
function collectPick(fn) { const inp = el("input"); inp.type = "file"; inp.accept = ".hwp,.hwpx"; inp.multiple = true; inp.onchange = () => fn([...inp.files]); inp.click(); } // 파일 고르기 창(여러 개)

function collectPlan(tid, part, opt) { // 「수정 계획 보기」 — 앞 제출본 · 수정본 · 지금 문서를 견준 계획(문서는 안 바뀜). 다시 누르면 접는다
  const C = collectOf(tid);
  if (C.busy) return null;
  if (C.plan && C.plan.part === part && !C.plan.busy) { C.plan = null; if (C.redraw) C.redraw(); return null; }
  C.plan = { part, view: null, err: "", busy: "plan" };
  return collectSend(tid, `plan:${part}`, async () => {
    if (opt && opt.flush) await opt.flush(); // 고치던 글을 먼저 서버에 — 계획은 서버의 문서로 센다
    try { C.plan = { part, view: await api(`/api/docs/${tid}/collect/parts/${part}/revise/plan`, { method: "POST" }), err: "", busy: "" }; }
    catch (e) { C.plan = { part, view: null, err: collectWhy(e), busy: "" }; }
    return "";
  }, null);
}

function collectApply(tid, part, opt) { // 「수정본 반영」 — 그 계획을 목적 문서에(편집 하나 · 실행 취소 한 번) · 낡은 계획(409)이면 걷고 다시 보게 한다
  const C = collectOf(tid), P = C.plan, p = collectPart(tid, part);
  if (!P || P.part !== part || !P.view || P.busy || C.busy) return null;
  const n = P.view.todo || 0;
  if (!confirm(`「${(p && p.name) || "수정본"}」 의 바뀐 곳 ${n}곳을 목적 문서에 반영합니다 — 문서가 바뀝니다(실행 취소 한 번으로 되돌립니다). 계속할까요?`)) return null;
  P.busy = "apply";
  return collectSend(tid, `apply:${part}`, async () => {
    let r = null;
    try {
      if (opt && opt.flush) await opt.flush();
      r = await api(`/api/docs/${tid}/collect/parts/${part}/revise/apply`, { method: "POST", headers: H_JSON, body: JSON.stringify({ planId: P.view.planId }) });
    } catch (e) {
      if (e.status === 409) C.plan = null; else if (C.plan === P) P.busy = ""; // 낡은 계획 — 「수정 계획 보기」 로 다시
      throw e;
    }
    C.plan = null;
    C.at = 0;
    if (opt && opt.applied) { try { await opt.applied(r); } catch (e) { console.warn(e); } } // 문서를 다시 읽는다(그 보기의 길 — 이관의 「내용 반영」 뒤와 같다)
    await collectRead(tid, true);
    return r && r.nothing ? "고칠 곳이 없어 문서를 바꾸지 않았습니다" : `수정본을 반영했습니다 — ${(r && r.text) || ""}`;
  }, opt);
}

function collectPlanEl(tid, p, opt) { // 그 줄 아래에 편 수정 계획 — 한 줄 요약 · 「수정본 반영」 · 항목 목록(고칠 곳 · 겹침 · 확인 필요 · 수정본에 없음 — 「지금 "…" → 수정본 "…"」)
  const C = collectOf(tid), P = C.plan, box = el("div", "collect-plan"), F = opt.focus || "dashFocus";
  box.dataset.part = p.work;
  if (P.busy === "plan" && !P.view) { box.append(el("p", "dash-text muted", "수정 계획을 세우는 중… — 앞 제출본 · 수정본 · 지금 문서를 견줍니다")); return box; }
  if (P.err) { box.append(el("p", "dash-text collect-warn", `수정 계획을 세우지 못했습니다 — ${P.err}`)); return box; }
  const V = P.view, items = V.items || [], off = opt.off || (C.busy ? "지금 보내는 요청이 끝나면 누를 수 있습니다" : ""), none = !V.todo;
  const head = el("div", "collect-plan-head"), sum = el("p", "dash-text collect-plan-sum", V.text || "바뀐 곳이 없습니다");
  const go = hBtn(P.busy === "apply" ? "반영하는 중…" : "수정본 반영", () => collectApply(tid, p.work, opt), { cls: "btn sm" + (off || none ? "" : " primary"), disabled: !!off || none || !!P.busy,
    title: off || (none ? "고칠 곳이 없습니다 — 겹침 · 확인 필요 · 수정본에 없는 자리는 그대로 둡니다" : `바뀐 곳 ${V.todo}곳을 목적 문서에 반영합니다 — 문서가 바뀝니다(편집 하나 · 실행 취소 한 번으로 되돌립니다). 겹침 · 확인 필요 · 수정본에 없는 자리는 그대로 둡니다`) });
  go.dataset[F] = `collect:${p.work}:apply`;
  head.append(sum, go);
  box.append(head);
  if (!items.length) { box.append(el("p", "dash-text muted", "보일 항목이 없습니다 — 수정본이 앞 제출본과 같거나 이미 반영돼 있습니다")); return box; }
  const ul = el("ul", "collect-items");
  ul.setAttribute("aria-label", "수정 계획의 항목");
  for (const it of items) {
    const li = el("li", "collect-item"), top = el("div", "collect-item-top"), tag = el("span", "collect-item-tag", COLLECT_ITEM[it.status] || it.status);
    li.dataset.status = it.status;
    top.append(tag, el("span", "collect-item-kind", it.kind === "cell" ? "표 칸" : it.kind === "para" ? "문단" : it.kind === "add" ? "새 블록" : it.kind || ""), ...(it.detail ? [el("span", "collect-item-detail", it.detail)] : []));
    li.append(top);
    if (it.was != null || it.text != null) { // 값의 이름과 함께 — 「지금 "…" → 수정본 "…"」(화살표 = 바뀌는 쪽)
      const d = el("p", "collect-diff"), was = el("span", "collect-diff-side"), neu = el("span", "collect-diff-side"); // 쪽마다 한 덩이(이름이 값과 떨어져 줄 끝에 남지 않게)
      was.append(el("span", "collect-diff-name", "지금"), el("span", "collect-diff-was", it.was == null ? "(없음)" : `"${it.was}"`));
      neu.append(el("span", "collect-diff-arrow", "→"), el("span", "collect-diff-name", "수정본"), el("span", "collect-diff-new", it.text == null ? "(없음)" : `"${it.text}"`));
      d.append(was, neu);
      li.append(d);
    }
    if (opt.go && it.to) { li.tabIndex = 0; li.classList.add("go"); li.title = "문서의 그 자리로"; li.onclick = () => opt.go(it.to); li.onkeydown = (e) => { if (e.key === "Enter") opt.go(it.to); }; }
    ul.append(li);
  }
  box.append(ul);
  if (items.length >= 300) box.append(el("p", "dash-text muted", "항목이 많아 앞의 300개만 보입니다"));
  return box;
}

// 「기관 문서」 목록 → 요소. opt = {off 고르기를 끄는 까닭(도는 실행 · 다른 진행 — 대시보드가 아는 값), redraw 다시 그리기, focus 초점을 되찾는 data- 이름(dashFocus | hdFocus), scope 올릴 묶음{job, project, round, kind},
//   open(문서 id) 그 문서를 둘째 면에서 열기 | 없음(첫 화면), here 지금 보는 문서 id, flush · after · uploaded · applied · go — 위 함수들이 부르는 그 보기의 일, stale 다시 읽을 틈(ms — 도는 것이 있으면 짧게)}
function collectListEl(tid, opt = {}) {
  const C = collectOf(tid), F = opt.focus || "dashFocus", box = el("div", "collect-list"), head = el("div", "collect-head");
  C.redraw = opt.redraw || null;
  if (!C.loading && !C.busy && (!C.at || Date.now() - C.at >= (opt.stale || 10000))) collectRead(tid, true); // 기다리지 않는다 — 읽으면 다시 그린다
  box.dataset.collect = tid;
  const V = C.view, parts = (V && V.parts) || [], orgs = (V && V.orgs) || [], off = opt.off || (C.busy ? "지금 보내는 요청이 끝나면 고를 수 있습니다" : "");
  head.append(el("b", null, V ? `기관 문서 ${parts.length}개` : "기관 문서"), hHelp("기관 문서 도움말", COLLECT_HELP, { note: true }));
  const todo = parts.filter((p) => p.state === "unassigned" && !(p.orgs || []).length);
  if (todo.length) {
    const noOrg = !orgs.length ? "프로젝트 구성(기관)이 아직 없습니다 — 「프로젝트 구성 추출」 뒤에 정할 수 있습니다" : "";
    const b = hBtn(C.busy === "auto" ? "지정하는 중…" : "자동 지정", () => collectAuto(tid, opt), { cls: "btn sm", disabled: !!off || !!noOrg,
      title: off || noOrg || `미지정인 문서 ${todo.length}개의 반영할 기관을 파일 이름 · 문서의 기관 라벨로 정합니다 — 알 수 없는 문서는 미지정으로 둡니다(사람이 고른 것은 바꾸지 않습니다 · 문서는 바뀌지 않습니다)` });
    b.dataset[F] = "collect:auto";
    head.append(b);
  }
  if (opt.scope) {
    const no = off || (opt.scope.project ? "" : "프로젝트 이름을 먼저 적으세요 — 올린 문서를 그 프로젝트에 넣습니다(「작업 개요」)");
    const up = hBtn(C.busy === "upload" ? "올리는 중…" : "기관 문서 올리기…", () => collectPick((files) => collectUpload(tid, files, opt.scope, opt)), { cls: "btn sm", disabled: !!no,
      title: no || "기관 문서 파일(hwp · hwpx — 여러 개)을 올려 이 워크플로우의 기관 문서로 넣습니다 — 반영할 기관은 미지정으로 들어옵니다(「자동 지정」 · 고르기). hwp 는 hwpx 로 바꿔 받고, 헤딩 · 표 분석(스크립트)을 바로 걸어 둡니다. 지금 보는 문서는 그대로입니다" });
    up.dataset[F] = "collect:upload";
    up.classList.add("collect-up");
    head.append(up);
  }
  box.append(head);
  if (C.err) box.append(el("p", "dash-text collect-warn", `기관 문서 목록을 읽지 못했습니다 — ${C.err}`));
  if (!V) { if (!C.err) box.append(el("p", "dash-text muted", "기관 문서 목록을 읽는 중…")); return box; }
  if (!parts.length) { box.append(el("p", "dash-text muted collect-empty", "기관 문서가 아직 없습니다 — 「기관 문서 올리기…」 로 기관이 써 보낸 문서를 넣으세요")); return box; }
  const ul = el("ul", "collect-rows");
  ul.setAttribute("aria-label", "기관 문서");
  for (const p of parts) {
    const li = el("li", "collect-row"), top = el("div", "collect-row-top"), ctl = el("div", "collect-row-ctl"), st = COLLECT_STATE[p.state] || p.state || "";
    li.dataset.part = p.work;
    li.dataset.state = p.state || "";
    // 파일 이름 — 누르면 그 문서를 둘째 면에서(그 보기의 같이 보기 길) · 지금 보는 문서면 글만
    const here = opt.here === p.work, name = opt.open && !here ? el("button", "collect-name") : el("b", "collect-name");
    name.textContent = p.name;
    if (opt.open && !here) { name.type = "button"; name.title = `${p.name} — 문서 옆 열에 읽기 전용으로 엽니다(같이 보기)`; name.dataset[F] = `collect:${p.work}:open`; name.onclick = () => opt.open(p.work); }
    else name.title = here ? `${p.name} — 지금 보는 문서` : p.name;
    top.append(el("span", "dash-no collect-no", String((p.order || 0) + 1)), name, ...(here ? [el("span", "collect-here", "지금 문서")] : []));
    const tag = el("span", "collect-state", p.state === "done" ? `✓ ${st}` : st);
    tag.title = p.text || st;
    top.append(tag);
    li.append(top);
    // 반영할 기관
    const org = el("select", "collect-sel"), cur = (p.orgs || [])[0] || "", lab1 = el("label", "collect-field");
    org.dataset[F] = `collect:${p.work}:org`;
    org.setAttribute("aria-label", `${p.name} — 반영할 기관`);
    org.append(new Option("선택 안 함", ""));
    for (const o of orgs) org.append(new Option(o.role ? `${o.name}(${o.role})` : o.name, o.key));
    if ((p.orgs || []).length > 1) org.append(new Option(`여러 기관 — ${(p.orgNames || p.orgs).join(" · ")}`, "*")); // 화면 밖에서 여럿으로 적은 문서 — 그대로 보인다
    org.value = (p.orgs || []).length > 1 ? "*" : cur;
    org.disabled = !!off || !orgs.length;
    org.title = off || (!orgs.length ? "프로젝트 구성(기관)이 아직 없습니다 — 「프로젝트 구성 추출」 뒤에 고를 수 있습니다" : "이 문서의 내용을 사업계획서의 어느 기관 자리에 넣을지 — 「선택 안 함」 이면 넣지 않습니다(문서는 바뀌지 않습니다)");
    org.onchange = () => { if (org.value === "*") return; const o = orgs.find((x) => x.key === org.value); collectPut(tid, p.work, { orgs: o ? [o.name] : [] }, opt); };
    lab1.append(el("span", "collect-field-name", "반영할 기관"), org);
    const by = COLLECT_BY[p.orgsBy];
    if (by && cur) { const t = el("span", "dash-tag dash-t-soft collect-by", by[0]); t.title = by[1]; lab1.append(t); }
    ctl.append(lab1);
    // 공통 자리 포함
    const lab2 = el("label", "collect-check"), cb = el("input");
    cb.type = "checkbox";
    cb.checked = !!p.common;
    cb.disabled = !!off;
    cb.dataset[F] = `collect:${p.work}:common`;
    cb.title = off || COLLECT_COMMON_HELP;
    cb.onchange = () => collectPut(tid, p.work, { common: cb.checked }, opt);
    lab2.append(cb, el("span", null, "공통 자리 포함"));
    const wrap2 = el("span", "collect-check-wrap");
    wrap2.append(lab2, hHelp("공통 자리 포함 도움말", COLLECT_COMMON_HELP, { note: true }));
    ctl.append(wrap2);
    // 수정본 — 같은 목록의 다른 문서 가운데 고를 수 있는 것(아직 뒤 수정본이 없는 것 · 이 문서의 수정본 사슬이 아닌 것 — 못 고를 것을 고르면 서버가 400 으로 알린다)
    const rev = el("select", "collect-sel"), lab3 = el("label", "collect-field");
    rev.dataset[F] = `collect:${p.work}:rev`;
    rev.setAttribute("aria-label", `${p.name} — 수정본`);
    rev.append(new Option("수정본 아님", ""));
    for (const q of parts) {
      if (q.work === p.work || q.revOf === p.work) continue;
      if (q.work !== p.revOf && (q.later || []).some((k) => k !== p.work)) continue; // 이미 다른 수정본이 있는 문서
      rev.append(new Option(`${q.name} 의 수정본`, q.work));
    }
    rev.value = p.revOf || "";
    rev.disabled = !!off || rev.options.length < 2;
    rev.title = off || (rev.options.length < 2 ? "수정본으로 삼을 다른 기관 문서가 없습니다" : "앞서 낸 문서를 고쳐 다시 보낸 문서면 그 문서를 고릅니다 — 수정본은 통째로 넣지 않고 앞 제출본과 견줘 바뀐 곳만 고칩니다(「수정 계획 보기」 → 「수정본 반영」)");
    rev.onchange = () => collectPut(tid, p.work, { revOf: rev.value || null }, opt);
    lab3.append(el("span", "collect-field-name", "수정본"), rev);
    ctl.append(lab3);
    li.append(ctl);
    if (p.text) li.append(el("p", "dash-text collect-text", p.text));
    if (p.revOf) { // 수정본 — 「수정 계획 보기」(문서는 안 바뀜) → 그 줄 아래에 편다
      const P = C.plan && C.plan.part === p.work ? C.plan : null, acts = el("div", "dash-acts collect-acts");
      const b = hBtn(P && P.busy === "plan" ? "계획 세우는 중…" : P ? "수정 계획 접기" : "수정 계획 보기", () => collectPlan(tid, p.work, opt), { cls: "btn sm" + (P || off || p.state !== "revision" ? "" : " primary"), disabled: !!off || !!(P && P.busy),
        title: off || (P ? "편 수정 계획을 접습니다" : `「${p.revName || "앞 제출본"}」 과 견줘 바뀐 곳을 봅니다 — 고칠 곳 · 겹침(사람이 고친 자리) · 확인 필요 · 수정본에 없는 자리. 문서는 「수정본 반영」 을 눌러야 바뀝니다`) });
      b.dataset[F] = `collect:${p.work}:plan`;
      b.setAttribute("aria-expanded", String(!!P));
      acts.append(b);
      li.append(acts);
      if (P) li.append(collectPlanEl(tid, p, opt));
    }
    ul.append(li);
  }
  box.append(ul);
  if (opt.off) box.append(el("p", "dash-text dash-why collect-off", `고르기 — ${opt.off}`));
  return box;
}
