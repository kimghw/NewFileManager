"use strict";
// 진행 줄의 「조정」 줄 — 템플릿 조정 · 서식 조정 · 모두 반영(spec_hwpx_웹편집 ② §8-4 「계획 모두 반영」).
// 2026-11-16 사용자(진행 줄 그림 — 스크립트 / LLM 두 줄) "여기 밑에 ,, 템플릿 조정, 서식 조정 이 들어 가야함" · "확인 뒤 한 번에 반영... 을 좋고 다만 이 버튼을 어디에 둘건가... 헤딩 추출 탭 안에 두는 것도 좋고 … 찾기 쉽워야함".
// 헤딩 추출 탭 머리의 진행 줄(app.js headsProgLine — 스크립트 · LLM 두 층)에 셋째 층 「조정」 을 더한다: 칸 셋 =
//   「템플릿 조정」 = 레터가 대표와 다른 줄을 서식 종속 템플릿(T1L3a)으로 떼는 것 — 받아 둔 계획이 뗄 줄 수 · 반영하면 ✓(문서 글·서식은 안 바뀜 — 템플릿만)
//   「서식 조정」   = 같은 템플릿의 줄을 그 레벨 대표 서식에 맞추는 것 — 받아 둔 계획이 맞출 줄 수 · 반영하면 ✓(문서 서식이 바뀜)
//   행동 칸       = **「모두 반영」**(지금 문서 차례에서 받은 계획 전부를 에이전트가 고른 그대로, 모든 템플릿을 트랜잭션 하나로 — POST …/outline/agent/apply · 실행 취소 1) ·
//                   계획이 없거나 받은 뒤 문서가 바뀌었으면 「계획 받기」(서식 정리 계획만 — POST …/analysis/llm {only: "formats"} · 유료 · 문서는 안 바뀜) ·
//                   **헤딩 판정(LLM)을 안 거쳤으면 그보다 먼저 「LLM 판정」**(tpbJudge — 「LLM 검증·보완」 이어 돌리기: 헤딩 · 템플릿 → 표 · 서식 정리 계획. 행동 칸은 차례를 따른다 — 2026-11-17)
// 두 조정 칸을 누르면 계획 보기(문서 옆 열 「LLM 이 바꾼 것」 의 「서식 계획」 절 — 템플릿 · 레벨마다 맞출 줄 · 뗄 줄 · 남긴 줄), 계획이 하나도 없으면 「템플릿 관계」 열(손으로 맞추고 떼는 곳).
// 「모두 반영」 은 이 줄 한 곳에만 둔다(design.md §10) — 템플릿 하나만 반영하는 길은 전처럼 템플릿 줄의 「계획대로 맞추기」 · ★ 열의 「적용」.
// 자료 = 분석 상태(GET …/analysis — doc_status.js dsState.main 의 서식 항목 llm{state, text, need, planned, applied, stale, change, moved, reps(대표를 바꿀 레벨), left(반영한 계획이 남긴 줄 {kept, unanswered, marked?(표지 때문에 모양만 맞춘 줄)}), leftMarked(그 줄 id), list}) — 따로 읽지 않는다.
// 부르는 곳: app.js headsProgLine(tplPlanRow — 세 단계를 다 보이는 진행 줄에만) · doc_status.js dsFetch(tplPlanBarSync) · 이름 줄 진행표 · 에이전트 보기(tplPlanGo) ·
// heads_run_all.js(tpbApply — 상태 줄 「전체 실행」 이 LLM 단계 뒤에 같은 함수로 반영한다 · tplPlanGo).
// 기대는 것: app.js(state · el · hBtn · nf · toast · api · structOp · flushAll · heads · headsRender · headsPoll · headsLlmReady · outlineLoad · showTab · scrollToBlock · H_JSON) · doc_status.js(dsState · docStatusPing · dsLlmRun) ·
// outline_match.js(olmLoad · olmRefresh) · heading_llm_diff.js(llmDiffOpen) · app.js tplRelOpen · tpl_agent.js(tpaSkillKey).
const TPB = { sig: null, busy: false, mark: -1 }; // mark = 「표지 n줄」 칸을 눌러 간 줄의 차례(tpbMarkGo)
const TPB_STATE = { none: "안 함", plan: "계획 받음 — 반영 전", llm: "반영함", left: "반영함 — 답이 없어 안 바꾼 줄이 남음", marked: "반영함 — 표지 때문에 모양만 맞춘 줄이 남음", running: "계획 받는 중", failed: "실패", skip: "할 것 없음" };
const tpbView = () => (typeof dsState === "object" && state.id && dsState.mainId === state.id ? dsState.main : null);
const tpbFmt = (v = tpbView()) => (v ? (v.items || []).find((i) => i.key === "formats") || null : null);
// 확실한 종속 제안(한 자리에만 매달린 가지 템플릿 → 그 자리의 템플릿 아래 — 분석 상태 템플릿 항목의 hints 가운데 sure): 「모두 반영」 이 저절로 건다(spec_hwpx_웹편집 ② §8-2 「종속 제안」 — 2026-11-16 사용자 「확실이 구분되는건 자동으로」)
const tpbSure = (v = tpbView()) => (((v && v.items) || []).find((i) => i.key === "templates") || {}).hints || [];
const tpbRelText = (hs) => hs.slice(0, 4).map((h) => `T${h.childNo} → T${h.parentNo} L${h.at} 아래`).join(" · ") + (hs.length > 4 ? ` 외 ${hs.length - 4}` : "");
// 헤딩 판정(LLM)을 거쳤나(분석 상태 헤딩 항목의 llm.state) — 조정은 LLM 판정 뒤의 일이다: 안 거쳤으면 행동 칸은 「계획 받기」 가 아니라 **「LLM 판정」**(tpbJudge).
// 2026-11-17 사용자(스크립트 ✓ · LLM ○ · 조정 ✓ 그림) "LLM 검증 보완이 빠졌네" · "LLM 판정버튼이 없고 계획받기 버튼을 누르도록 되어 있었어" — 전에는 판정 전에도 「계획 받기」 가 떠서
// 스크립트 그래프 위에서 계획 → 반영이 되고 LLM 검증·보완이 빠졌다(spec_헤딩_추출 ② §7 「조정 층」 의 「행동 칸은 차례를 따른다」). function 선언 — 화면 검사가 바꿔 끼운다(tools/smoke_adjust_ui.py)
function tpbJudged(v = tpbView()) {
  return ((((v && v.items) || []).find((i) => i.key === "heads") || {}).llm || {}).state === "done";
}

function tplPlanRow() { // 진행 줄을 그릴 때(app.js headsProgLine) — 「조정」 층의 이름표 + 칸 셋(빈 채로 만들고 바로 채운다)
  const layer = el("span", "hprog-layer tpb-layer", "조정");
  layer.title = "조정 — LLM 판정 뒤의 일: 템플릿 조정(레터가 다른 줄을 서식 종속 템플릿으로) · 서식 조정(같은 템플릿의 줄을 대표 서식에). 계획은 「헤딩 그래프(LLM)」 이 이어서 받고, 문서는 「모두 반영」 을 눌러야 바뀝니다. LLM 판정을 아직 안 했으면 줄 끝의 단추는 「LLM 판정」 입니다";
  const cells = ["tpl", "fmt", "act"].map((k) => { const b = hBtn("", null, { cls: "hprog-step tpb-cell" }); b.dataset.tpb = k; return b; });
  TPB.sig = null;
  tpbDraw([layer, ...cells]);
  return [layer, ...cells];
}

function tplPlanBarSync(force = false) { // 분석 상태가 바뀜(doc_status.js dsFetch) · 반영 중 — 그려 둔 칸을 그 자리에서 다시
  const cells = [...document.querySelectorAll("#headsOverview .hprog [data-tpb]")];
  if (!cells.length) return;
  if (force) TPB.sig = null;
  tpbDraw([document.querySelector("#headsOverview .hprog .tpb-layer"), ...cells]);
}

function tpbCell(b, i) { // 칸 하나 — 진행 줄의 다른 칸과 같은 꼴(표시 + 이름 + 수)
  b.textContent = "";
  b.dataset.state = i.state;
  b.disabled = !!i.off;
  b.classList.toggle("tpb-go", !!i.go);
  if (!i.plain) b.append(el("span", "hprog-mark"));
  b.append(el("span", "hprog-text", i.text));
  if (i.count) {
    const n = el("span", "hprog-count", i.count);
    if (i.unit) n.append(el("span", "hprog-unit", i.unit));
    b.append(n);
  }
  b.title = i.title || "";
  const say = TPB_STATE[i.say || i.state]; // say = 읽어 줄 상태(모양은 state 를 따르고 글만 다를 때 — 「표지 n줄」 은 「left」 모양)
  b.setAttribute("aria-label", `조정 ${i.text}${i.count ? ` ${i.count}${i.unit || ""}` : ""}${say && !i.plain ? ` — ${say}` : ""}`);
  b.onclick = i.run || null;
  b.hidden = !!i.hide;
}

function tpbDraw(els) {
  const [layer, tplB, fmtB, actB] = els, v = tpbView(), f = tpbFmt(v), L = f && f.llm;
  if (!tplB || !fmtB || !actB) return;
  const hints = tpbSure(v), sure = hints.filter((h) => h.sure), maybe = hints.filter((h) => !h.sure), judged = tpbJudged(v);
  const sig = JSON.stringify([state.id, !!f, f && f.state, L && [L.state, L.text, L.need, L.planned, L.applied, L.stale, L.done, L.change, L.moved, L.reps, L.left, L.error], f && f.others, f && f.place, !!(v && v.busy), TPB.busy, !!state.busy,
    hints.map((h) => [h.child, h.parent, h.at, h.sure]), judged]);
  if (sig === TPB.sig && tplB.childNodes.length) return;
  TPB.sig = sig;
  const ready = !!(f && f.state === "done" && L && typeof L.need === "number");
  // 자리 맞춤(spec_hwpx_웹편집 ② §8-8 「확정 서식으로 바꾸기」): 대표와 그 갈래의 줄 가운데 레터 뒤 묶음 빈칸 · 자리 규칙(둘째 줄 = 글 시작)이 아직 안 걸린 줄 — 「모두 반영」 이 스크립트로 건다(LLM 계획이 없어도)
  const P = (ready && f.place) || 0;
  const placeTip = P ? `\n자리 맞춤 ${nf(P)}줄 — 레터 뒤 빈칸을 묶음 빈칸으로(양쪽 정렬이 늘리지 않습니다) · 둘째 줄을 글 시작에. 스크립트가 맞춥니다 — 「모두 반영」 이 같이 겁니다` : "";
  const list = (L && L.list) || [], none = list.filter((x) => x.state === "none").length, busy = !!(v && v.busy) || TPB.busy;
  // 대표만 바꾸는 레벨(L.reps — 맞출 줄이 0 이어도 반영할 것이다) · 반영한 계획이 지금 문서에 남긴 줄(L.left — 에이전트가 그대로 둔 줄 LK · 답이 없어 안 바꾼 줄 LU: 검토한 것이 아니다)
  // — 반영한 뒤에도 보인다(2026-11-16 astra: 답이 없던 줄이 ✓ 뒤로 사라졌다 — spec_hwpx_웹편집 ② §8-4)
  const R = (ready && L.reps) || 0, LK = (ready && L.left && L.left.kept) || 0, LU = (ready && L.left && L.left.unanswered) || 0;
  // LM = 반영이 형광펜 · 필드 표지 때문에 모양만 맞추고 남긴 줄(지금도 대표와 다른 서식 — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」): 레터 첫머리의 글은 그대로라 대표와 다르다. 실패가 아니라 남긴 것 — 단계별로 보정
  const LM = (ready && L.left && L.left.marked) || 0;
  const markTip = LM ? `표지 때문에 모양만 맞춘 줄 ${nf(LM)} — 형광펜·필드 표지가 있어 레터 첫머리의 글(레터 · 레터 앞·뒤 빈칸)은 그대로입니다(문단·글자 모양은 맞춤). 한글에서 표지를 지운 뒤 「이 줄들만 맞추기」, 또는 그대로 둡니다` : "";
  const leftTip = LK || LU || LM ? `\n반영한 계획이 남긴 줄 — ${[LK ? `에이전트가 그대로 둔 줄 ${nf(LK)}` : "", LU ? `답이 없어 안 바꾼 줄 ${nf(LU)}(검토한 것이 아닙니다)` : "", LM ? `표지 때문에 모양만 맞춘 줄 ${nf(LM)}` : ""].filter(Boolean).join(" · ")} — 「반영한 계획 보기」 · 「템플릿 관계」 에서 손으로` : "";
  const leftCell = () => { // 답이 없어 안 바꾼 줄이 남았으면 「서식 조정」 칸은 ✓ 가 아니다 — 남은 줄 수를 보인다(에이전트가 까닭을 적고 그대로 둔 줄은 검토한 것 — ✓ 그대로 · 도움말에만)
    if (LU) tpbCell(fmtB, { state: "left", text: "서식 조정", count: `답 없음 ${nf(LU)}`, unit: "줄", title: `${F}\n반영했지만 에이전트가 답하지 않아 안 바꾼 줄이 ${nf(LU)}줄 남았습니다 — 검토한 것이 아닙니다${leftTip}\n— ${seeTip}`, run: see });
    // 표지 때문에 모양만 맞춘 줄만 남았다 — 같은 모양(!)으로 「표지 n줄」, 누르면 그 줄로 차례로 간다(tpbMarkGo)
    else if (LM) tpbCell(fmtB, { state: "left", say: "marked", text: "서식 조정", count: `표지 ${nf(LM)}`, unit: "줄", title: `${F}\n${markTip}${leftTip}\n— 누르면 그 줄로 차례로 갑니다`, run: tpbMarkGo });
  };
  const has = ready && (L.planned || L.applied || L.stale || L.done); // 볼 계획이 있나
  const see = () => { if (has && typeof llmDiffOpen === "function") llmDiffOpen("fmt"); else if (typeof tplRelOpen === "function") tplRelOpen(); };
  const seeTip = has ? "누르면 계획 보기 — 문서 옆 열 「LLM 이 바꾼 것」 의 「서식 계획」(템플릿 · 레벨마다 맞출 줄 · 뗄 줄 · 남긴 줄)" : "누르면 「템플릿 관계」 열 — 손으로 대표에 맞추고 다른 템플릿으로 떼는 곳";
  const T = "템플릿 조정 — 레터가 대표와 다른 줄을 서식 종속 템플릿(T1L3a)으로 뗍니다(그 아래 줄도 같이). 문서의 글·서식은 안 바뀌고 템플릿만 나뉩니다";
  const F = "서식 조정 — 같은 템플릿의 줄을 그 레벨의 대표 서식에 맞춥니다(레터 첫머리 · 문단 모양 · 글자 모양). 문서의 서식이 바뀝니다";
  if (layer) layer.hidden = false;
  // 헤딩 판정(LLM)을 안 거쳤으면 두 칸의 도움말에 그 한 줄 — 조정은 LLM 판정 뒤의 일이다(행동 칸 「LLM 판정」 이 먼저)
  const judgeTip = judged ? "" : "\n헤딩 판정(LLM)을 아직 안 했습니다 — 조정은 LLM 판정 뒤의 일입니다: 줄 끝의 「LLM 판정」 이 헤딩 · 템플릿 → 표 · 서식 정리 계획을 차례로 돌립니다";
  const both = (state_, extra, tip) => {
    tpbCell(tplB, { state: state_, text: "템플릿 조정", ...(extra && extra.tpl), title: `${T}\n${tip}${judgeTip}\n— ${seeTip}`, run: see });
    tpbCell(fmtB, { state: state_, text: "서식 조정", ...(extra && extra.fmt), title: `${F}\n${tip}${judgeTip}\n— ${seeTip}`, run: see });
  };
  const act = (i) => tpbCell(actB, { plain: true, state: "act", ...i });
  // 종속(템플릿 사이 관계): 확실한 것 = 「모두 반영」 이 저절로 건다 · 애매한 것 = 제안만(결과 화면의 「템플릿 관계」 절에서 사람이). 계획이 없어도 확실한 종속이 있으면 「템플릿 조정」 칸과 「모두 반영」 이 뜬다
  const relTip = (sure.length ? `\n종속 ${nf(sure.length)}개를 저절로 넣습니다 — ${tpbRelText(sure)}(문서는 안 바뀜 · 템플릿만)` : "") + (maybe.length ? `\n종속 제안 ${nf(maybe.length)}개는 사람이 고릅니다(「템플릿 조정」 칸을 누르면 결과 화면의 「템플릿 관계」 절) — ${tpbRelText(maybe)}` : "");
  const relCell = () => tpbCell(tplB, { state: "plan", text: "템플릿 조정", count: `종속 ${nf(sure.length)}`, title: `${T}${relTip}`, run: () => (typeof llmDiffOpen === "function" ? llmDiffOpen("rel") : see()) });
  const relAct = () => act({ text: "모두 반영", go: true, off: busy || !!state.busy, run: () => tpbApply(), title: `확실한 종속 ${nf(sure.length)}개를 넣습니다 — ${tpbRelText(sure)}. 문서 글·서식은 안 바뀌고 템플릿만 바뀝니다(「실행 취소」 한 번으로 되돌립니다 · 풀려면 「템플릿 관계」 의 「떼기」)` });
  const placeCell = () => tpbCell(fmtB, { state: "plan", text: "서식 조정", count: nf(P), unit: "줄", title: `${F}${placeTip}\n— ${seeTip}`, run: see });
  const placeAct = () => act({ text: "모두 반영", go: true, off: busy || !!state.busy, run: () => tpbApply(),
    title: `자리 맞춤 ${nf(P)}줄 — 레터 뒤 빈칸을 묶음 빈칸으로 · 둘째 줄을 글 시작에 맞춥니다(스크립트 — LLM 을 부르지 않습니다)${sure.length ? ` · 확실한 종속 ${nf(sure.length)}개도 넣습니다` : ""}.\n문서가 바뀝니다 — 「실행 취소」 한 번으로 되돌립니다` });
  const planAct = (label) => act({ text: label, go: false, off: busy, run: () => tpbFetch(),
    title: busy ? "다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요" : "서식이 여러 가지인 템플릿마다 서식 정리 계획을 받습니다(유료 LLM · 템플릿마다 호출 하나 · 문서는 안 바뀜) — 이미 받은 계획은 다시 받지 않습니다" });
  // 행동 칸은 차례를 따른다 — 헤딩 판정(LLM)을 안 거쳤으면 계획 받기도 스크립트 반영(자리 맞춤 · 종속)도 아닌 「LLM 판정」 이 먼저다(계획은 그 이어 돌리기가 같이 받고, 자리 맞춤 · 종속은 그 뒤 「모두 반영」 이 같이 건다).
  // 판정을 거친 뒤에만 「계획 받기」·「다시 받기」·「나머지 받기」 · 계획 없는 「모두 반영」. 판정 전에도 서는 「모두 반영」 은 이미 받아 둔 계획의 것뿐이다(막지 않고 알린다)
  const scriptTodo = [P ? `자리 맞춤 ${nf(P)}줄` : "", sure.length ? `확실한 종속 ${nf(sure.length)}개` : ""].filter(Boolean).join(" · ");
  const judgeAct = () => act({ text: "LLM 판정", go: false, off: busy, run: () => tpbJudge(),
    title: busy ? "다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요"
      : "헤딩 판정(LLM)을 아직 안 했습니다 — 조정(서식 정리 계획 · 반영)보다 먼저 LLM 판정을 돌립니다: 헤딩 · 템플릿 → 표 · 서식 정리 계획(이름 줄 진행표의 「LLM 검증·보완」 과 같은 일 · 유료 LLM · 몇 분 · 문서는 안 바뀜).\n누르면 돌 것을 먼저 보이고 묻습니다 — 받은 계획은 이 줄의 두 칸에서 확인한 뒤 「모두 반영」"
        + (scriptTodo ? `\n스크립트가 맞출 것(${scriptTodo})은 LLM 판정 뒤 「모두 반영」 이 같이 겁니다 — LLM 연결이 없으면 누를 때 그것만 반영할지 묻습니다` : "") });
  const fetchAct = (label) => (judged ? planAct(label) : judgeAct());
  const idleAct = () => (judged ? act({ text: "", hide: true }) : judgeAct()); // 지금 반영할 것도 받을 계획도 없다 — 판정을 안 거쳤으면 그것이 남은 일이다
  const restAct = () => { // 받아 둔 계획이 없을 때 — 판정 전에는 「LLM 판정」, 판정 뒤에는 스크립트가 걸 것(자리 맞춤 · 종속)이 있으면 「모두 반영」 · 없으면 감춤
    if (!judged) judgeAct(); else if (P) placeAct(); else if (sure.length) relAct(); else act({ text: "", hide: true });
  };
  if (!ready) { // 헤딩 그래프가 아직 없다(또는 분석 상태를 아직 못 읽음)
    both("none", null, "헤딩 그래프(2단계)가 있어야 셉니다 — 「헤딩 그래프(LLM)」 이 헤딩 판정 뒤에 이어서 계획을 받습니다");
    act({ text: "", hide: true });
    return;
  }
  if (L.state === "running") { both("running", null, L.text || "서식 정리 계획을 받는 중"); act({ text: "받는 중…", off: true, title: L.text || "" }); return; }
  if (L.state === "wait") { both("none", null, L.text || "헤딩 판정이 끝나면 이어서 서식 정리 계획을 받습니다"); act({ text: "", hide: true }); return; }
  if (!L.need) { // 정리할 템플릿이 없다 — 계획을 반영해 다 맞춘 것이면 ✓, 처음부터 한 가지였으면 –
    if (L.done) both("llm", null, `모두 반영함 — 계획 ${nf(L.done)}개(템플릿) · 지금은 레벨마다 서식이 한 가지입니다`);
    else both("skip", null, "할 것 없음 — 레벨마다 서식이 한 가지입니다");
    if (sure.length) relCell(); // 서식은 다 맞았어도 확실한 종속이 남았다
    if (P) placeCell(); // 서식 갈래는 한 가지여도 자리(묶음 빈칸 · 둘째 줄)가 아직 규칙대로가 아니다
    restAct();
    return;
  }
  const rest = [L.stale ? `옛 계획 ${nf(L.stale)}(받은 뒤 문서가 바뀜)` : "", none ? `안 받음 ${nf(none)}` : "", L.applied ? `반영함 ${nf(L.applied)}` : ""].filter(Boolean).join(" · ");
  if (L.planned && L.change === undefined) { // 서버가 옛 판(이 기능 전 — 다시 켜기 전): 계획은 있는데 줄 수를 모른다. 수 없이 「계획 받음」 으로 보이고, 「모두 반영」 을 누르면 「서버를 다시 시작」 알림(tpbApply)
    both("plan", null, `받아 둔 계획 ${nf(L.planned)}개 — 줄 수는 서버(8114)를 다시 시작해야 보입니다`);
    act({ text: "모두 반영", go: true, off: busy || !!state.busy, run: () => tpbApply(), title: "서버가 옛 판이면 반영되지 않고 「서버를 다시 시작」 알림이 뜹니다" });
    return;
  }
  if (L.planned) {
    const todo = (L.change || 0) + (L.moved || 0) + R + sure.length + P, sum =`받아 둔 계획 ${nf(L.planned)}개(템플릿) — 맞출 줄 ${nf(L.change || 0)} · 뗄 줄 ${nf(L.moved || 0)}${R ? ` · 대표 변경 ${nf(R)}` : ""}${P ? ` · 자리 맞춤 ${nf(P)}` : ""}${rest ? ` · ${rest}` : ""}`;
    tpbCell(tplB, L.moved ? { state: "plan", text: "템플릿 조정", count: nf(L.moved), unit: sure.length ? `줄 · 종속 ${nf(sure.length)}` : "줄", title: `${T}\n${sum}${relTip}\n— ${seeTip}`, run: see }
      : sure.length ? { state: "plan", text: "템플릿 조정", count: `종속 ${nf(sure.length)}`, title: `${T}\n${sum} — 뗄 줄 없음${relTip}\n— ${seeTip}`, run: see }
      : { state: "skip", text: "템플릿 조정", title: `${T}\n${sum} — 뗄 줄 없음(레터가 다른 줄이 없습니다)\n— ${seeTip}`, run: see });
    tpbCell(fmtB, L.change || P ? { state: "plan", text: "서식 조정", count: nf((L.change || 0) + P), unit: R ? `줄 · 대표 ${nf(R)}` : "줄", title: `${F}\n${sum}${placeTip}\n— ${seeTip}`, run: see }
      : R ? { state: "plan", text: "서식 조정", count: `대표 ${nf(R)}`, title: `${F}\n${sum} — 맞출 줄은 없고 대표만 바꿉니다(새 대표와 서식이 같은 줄은 자리를 같이 맞춥니다)\n— ${seeTip}`, run: see } // 대표만 바꾸는 계획 — 맞출 줄이 0 이어도 반영할 것이다
      : { state: "skip", text: "서식 조정", title: `${F}\n${sum} — 맞출 줄 없음\n— ${seeTip}`, run: see });
    if (todo) {
      act({ text: "모두 반영", go: true, off: busy || !!state.busy, run: () => tpbApply(),
        title: `받아 둔 계획 ${nf(L.planned)}개를 에이전트가 고른 그대로 한 번에 반영합니다 — 대표에 맞출 줄 ${nf(L.change || 0)}개 · 서식 종속 템플릿으로 뗄 줄 ${nf(L.moved || 0)}개(그 아래 줄도 같이 갑니다)${R ? ` · 대표를 바꿀 레벨 ${nf(R)}개` : ""} · 「그대로」 로 남긴 줄은 안 바뀝니다.${P ?`\n맞춘 뒤 스크립트가 자리를 맞춥니다 — 레터 뒤 빈칸을 묶음 빈칸으로 · 둘째 줄을 글 시작에(지금 ${nf(P)}줄 + 맞춘 줄).` : ""}\n문서가 바뀝니다 — 「실행 취소」 한 번으로 되돌립니다. 먼저 「템플릿 조정」·「서식 조정」 칸을 눌러 계획을 확인하세요.${rest ? `\n${rest}` : ""}${judged ? "" : "\n※ 헤딩 판정(LLM)을 안 거친 스크립트 헤딩 그래프 위에서 받은 계획입니다 — LLM 판정부터 하려면 「전체 실행」"}` });
    } else if (L.stale || none) fetchAct("나머지 받기");
    else idleAct();
    return;
  }
  if (L.stale || none) {
    const part = !!(L.applied || L.done); // 반영한 계획이 있는데 남은 것도 있다 — 반영으로 새로 생긴 서식 종속 템플릿 · 그 뒤 고친 템플릿
    const st = L.state === "failed" ? "failed" : part ? "llm" : "none";
    both(st, null, `서식 정리 계획 — ${rest}${part ? "\n남은 것 = 계획을 받지 않은 템플릿(반영으로 새로 생긴 서식 종속 템플릿 · 그 뒤 서식이 갈린 템플릿) — 「나머지 받기」" : ""}${L.state === "failed" && L.error ? `\n${L.error}` : ""}${leftTip}`);
    if (st === "llm") leftCell(); // 반영한 계획이 답 없이 남긴 줄 — ✓ 로 덮지 않는다
    fetchAct(part ? "나머지 받기" : L.stale && !none ? "다시 받기" : "계획 받기");
    return;
  }
  both("llm", null, `모두 반영함 — 템플릿 ${nf(L.applied)}개${f.others ? ` · 대표와 다른 줄 ${nf(f.others)}(「그대로」 로 남긴 줄 · 그 뒤 고친 줄)` : ""}${leftTip}`);
  leftCell(); // 답이 없어 안 바꾼 줄이 남았으면 「서식 조정」 은 ✓ 가 아니라 「답 없음 n줄」
  if (sure.length) relCell();
  if (P) placeCell(); // 계획은 다 반영했는데 자리가 안 맞은 줄이 남았다(이 기능 전에 반영한 문서 · 그 뒤 고친 줄)
  restAct();
}

function tpbAsk(L, P = 0, judged = true, note = "") { // 「모두 반영」 의 확인 창 글 — 무엇이 몇 줄 바뀌고 무엇이 남나(2026-11-16: 전에는 확인 없이 바로 문서를 바꿨다). P = 자리 맞춤이 남은 줄(② §8-8) · judged = 헤딩 판정(LLM)을 거쳤나 · note = 맨 앞 한 줄(「LLM 판정」 이 LLM 없이 넘어온 때)
  const rows = (note ? [note, ""] : []).concat(L.planned ? [`받아 둔 서식 정리 계획 ${nf(L.planned || 0)}개(템플릿)를 에이전트가 고른 그대로 반영합니다.`, "",
    `· 서식 조정 — 대표 서식에 맞출 줄 ${nf(L.change || 0)}${L.reps ? ` · 대표를 바꿀 레벨 ${nf(L.reps)}(맞출 줄이 없어도 대표가 바뀝니다)` : ""}`, `· 템플릿 조정 — 서식 종속 템플릿으로 뗄 줄 ${nf(L.moved || 0)}`]
    : ["받아 둔 서식 정리 계획은 없습니다 — 스크립트가 맞추는 것만 반영합니다.", ""]);
  if (P || L.change) rows.push(`· 자리 맞춤(스크립트) — 레터 뒤 빈칸을 묶음 빈칸으로(양쪽 정렬이 늘리지 않음) · 둘째 줄을 글 시작에: 지금 ${nf(P)}줄${L.change ? " + 위에서 맞춘 줄" : ""}`);
  const left = [L.kept ? `에이전트가 그대로 둔 줄 ${nf(L.kept)}` : "", L.unanswered ? `답이 없어 안 바꾸는 줄 ${nf(L.unanswered)}` : "", L.omitted ? `서식 가짓수가 많아 못 본 서식 ${nf(L.omitted)}가지(반영 뒤 「나머지 받기」)` : ""].filter(Boolean);
  if (left.length) rows.push(`· 안 바뀌는 것 — ${left.join(" · ")}`);
  const sure = tpbSure().filter((h) => h.sure);
  if (sure.length) rows.push(`· 템플릿 종속 — 한 자리에만 매달린 템플릿 ${nf(sure.length)}개를 그 자리의 템플릿 아래로 넣습니다(${tpbRelText(sure)} — 문서는 안 바뀌고 템플릿만)`);
  const edited = typeof tpaEdited === "function" ? tpaEdited() : null;
  if (edited != null) rows.push("", `※ 「템플릿 서식 정리」 열에서 T${edited} 의 고르기를 바꿔 두었습니다 — 「모두 반영」 은 바꾼 고르기가 아니라 에이전트가 고른 그대로 반영합니다. 바꾼 대로 하려면 「취소」 를 누르고 그 열의 「적용」 을 쓰세요.`);
  // 판정을 안 거친 그래프 위의 계획 — 막지는 않고 알린다(템플릿 줄의 ★ 열로 받은 계획 · 이 규칙 전에 받은 계획). LLM 판정은 헤딩 그래프를 다시 지어 이 계획을 새로 받는다
  if (!judged && L.planned) rows.push("", "※ 헤딩 판정(LLM)을 안 거친 스크립트 헤딩 그래프 위에서 받은 계획입니다 — LLM 판정부터 하려면 「취소」 를 누르고 「전체 실행」 을 쓰세요(헤딩 그래프를 다시 지으면 서식 정리 계획은 새로 받습니다).");
  rows.push("", "문서가 바뀝니다 — 「실행 취소」 한 번으로 되돌립니다. 계획의 내용은 「템플릿 조정」·「서식 조정」 칸을 누르면 보입니다. 계속할까요?");
  return rows.join("\n");
}

// 「모두 반영」 — 지금 문서 차례의 계획 전부를 트랜잭션 하나로(실행 취소 1) → 반영 결과 | null(못 함 — 까닭은 structOp.lastError · 확인 창에서 「취소」 면 lastError 도 null). 「전체 실행」(heads_run_all.js)도 이 함수로 반영한다.
// opt.note = 확인 창 맨 앞에 실을 한 줄(「LLM 판정」 을 눌렀는데 LLM 연결이 없어 스크립트 반영만 묻는 때 — tpbJudge) ·
// opt.ask = false 면 확인 창을 건너뛴다(전체 실행은 시작할 때 이미 물었다) · opt.plans = 반영할 계획의 표시 {템플릿 id: at}(부른 쪽이 방금 읽은 분석 상태의 것 — 없으면 이 줄이 가진 분석 상태에서).
// 요청에 그 표시를 실어 서버가 「화면이 본 계획 그대로인가」 를 견준다(그 사이 다시 받은 계획이면 409 — 본 것과 다른 계획을 반영하지 않는다).
async function tpbApply(opt = {}) {
  if (TPB.busy || !state.id) return null;
  const id = state.id, epoch = state.epoch;
  let L = (tpbFmt() || {}).llm || {}, P = (tpbFmt() || {}).place || 0, judged = tpbJudged();
  structOp.lastError = null;
  if (!opt.plans) { // 이 줄이 가진 분석 상태는 늦을 수 있다(「템플릿 서식 정리」 열에서 방금 다시 받은 계획) — 묻기 전에 새로 읽어 그 수를 보이고 그 계획의 표시를 보낸다(옛 표시면 서버가 409 로 막는다)
    try {
      const a = await api(`/api/docs/${id}/analysis`), f = (a.items || []).find((i) => i.key === "formats");
      if (f && f.llm) { L = f.llm; P = f.place || 0; judged = tpbJudged(a); }
    } catch { /* 못 읽으면 가진 것으로 — 서버가 표시를 견준다 */ }
    if (epoch !== state.epoch || TPB.busy) return null;
  }
  const plans = opt.plans || Object.fromEntries((L.list || []).filter((x) => x.state === "planned" && x.at != null).map((x) => [x.tpl, x.at]));
  if (opt.ask !== false && !confirm(tpbAsk(L, P, judged, opt.note || ""))) return null;
  if (epoch !== state.epoch) return null;
  TPB.busy = true;
  tplPlanBarSync(true);
  const r = await structOp("outline/agent/apply", Object.keys(plans).length ? { rev: state.serverRev, plans } : { rev: state.serverRev }); // 표시가 없으면(서버가 옛 판) 전처럼 차례만
  TPB.busy = false;
  if (r) {
    // placed = 자리 맞춤만 한 줄(② §8-8) · lm = 형광펜·필드 표지 때문에 모양만 맞추고 남긴 줄(② §8-8 「짝 표지가 든 줄」 — changed 에도 든다) · n = 대표에 맞춘 줄
    const ts = r.templates || [], placed = (r.placed || []).length, lm = (r.left || []).length, n = (r.changed || []).length - placed - lm, made = ts.flatMap((t) => (t.splits || []).map((x) => `T${x.no}`));
    const rel = (r.merged || []).length ? ` · 템플릿 종속 ${nf(r.merged.length)}(${r.merged.slice(0, 4).map((m) => `T${m.no}`).join(" · ")})` : "";
    const put = [placed ? `자리 맞춤 ${nf(placed)}줄(묶음 빈칸 · 둘째 줄 = 글 시작)` : "", lm ? `형광펜·필드 표지가 있어 모양만 맞춘 줄 ${nf(lm)}(글은 그대로 — 남긴 줄은 조정 층 「서식 조정」 칸에서)` : ""].filter(Boolean).join(" · ");
    const reps = ts.reduce((a, t) => a + (t.levels || []).filter((x) => x.repChanged).length, 0); // 대표를 바꾼 레벨 — 맞춘 줄이 0 이어도 한 일이다
    toast(r.nothing ? "바꿀 줄이 없습니다 — 계획이 모두 「그대로」 입니다" : !ts.length && !placed && rel ? `템플릿 종속을 넣었습니다 —${rel.slice(2)} · 문서는 안 바뀜 · 「실행 취소」 한 번으로 되돌립니다`
      : !ts.length && placed ? `자리를 맞췄습니다 — ${put}${rel} · 「실행 취소」 한 번으로 되돌립니다`
      : `계획대로 반영했습니다 — 템플릿 ${nf(ts.length)}개 · ${[made.length ? `템플릿 조정: 서식 종속 템플릿 ${made.slice(0, 6).join(" · ")}${made.length > 6 ? " …" : ""}` : "", n ? `서식 조정: 맞춘 줄 ${nf(n)}` : "", reps ? `대표 변경 ${nf(reps)}` : "", put].filter(Boolean).join(" · ") || "대표만 바뀜"}${rel} · 「실행 취소」 한 번으로 되돌립니다`);
  } else {
    const e = structOp.lastError; // 까닭은 structOp 이 이미 알렸다 — 옛 서버만 따로
    if (e && e.status === 404 && /not found/i.test(e.message || "")) toast("서버가 옛 판이라 「모두 반영」 을 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요", true);
  }
  if (typeof outlineLoad === "function") outlineLoad(true); // 대표 · 새 템플릿 — 오버레이 요약을 다시
  if (typeof olmLoad === "function") olmLoad(true).then(() => olmRefresh()); // 서식 갈래 · 템플릿 줄의 단추 · 이름 줄 분석 상태(→ 이 줄)
  if (typeof docStatusPing === "function") docStatusPing();
  tplPlanBarSync(true);
  return r || null;
}

async function tpbFetch() { // 「계획 받기」 — 서식 정리 계획만(헤딩 · 표 LLM 은 안 돎). 헤딩 작업 자리 하나에서 돈다(진행은 이 줄 · 추출·설정 2단계 · 이름 줄 진행표)
  if (!state.id) return;
  const L = (tpbFmt() || {}).llm || {}, todo = (L.list || []).filter((x) => x.state === "none" || x.state === "stale").length;
  if (!confirm(`서식 정리 계획 — 서식이 여러 가지인 템플릿 ${todo || L.need || ""}개를 LLM 에 묻습니다(템플릿마다 호출 하나).\n유료 호출이고 문서는 바뀌지 않습니다 — 받은 계획은 「템플릿 조정」·「서식 조정」 칸에서 확인한 뒤 「모두 반영」 으로 반영합니다. 계속할까요?`)) return;
  const id = state.id, epoch = state.epoch;
  await flushAll(); // 아직 반영 안 된 글부터 — 계획은 서버 문서를 읽는다
  if (epoch !== state.epoch) return;
  try {
    const job = await api(`/api/docs/${id}/analysis/llm`, { method: "POST", headers: H_JSON, body: JSON.stringify({ only: "formats", skill: typeof tpaSkillKey === "function" ? tpaSkillKey() : "tidy" }) });
    if (epoch !== state.epoch) return;
    heads.expect = job.started;
    headsRender({ ...(heads.view || { rev: state.serverRev, runs: [], stage1: null, stage2: null, stage3: null }), job });
  } catch (e) {
    if (epoch !== state.epoch) return;
    toast(e.status === 409 ? "헤딩 추출이 이미 돌고 있습니다 — 끝난 뒤 다시 누르세요" : `서식 정리 계획을 시작하지 못했습니다: ${e.message}`, e.status !== 409);
  }
  headsPoll();
}

// 「LLM 판정」 — 헤딩 판정(LLM)을 안 거친 문서의 행동 칸(tpbJudged): 조정(서식 정리 계획 · 반영)보다 먼저 「LLM 검증·보완」 이어 돌리기(헤딩 · 템플릿 → 표 · 서식 정리 계획 같이 —
// doc_status.js dsLlmRun: 이름 줄 진행표의 단추와 같은 함수 · 같은 끝점). 새 실행 길이 아니다 — 돌 것은 서버의 llmPlan 그대로이고 그 목록을 확인 창에 보인 뒤에 돈다(유료 · 문서는 안 바뀜).
// 받은 계획은 이 줄의 두 칸 → 「모두 반영」. 2026-11-17 사용자 「LLM 판정버튼이 없고 계획받기 버튼을 누르도록 되어 있었어」(spec_헤딩_추출 ② §7 「조정 층」)
async function tpbJudge() {
  if (!state.id || typeof dsLlmRun !== "function") return;
  const id = state.id, epoch = state.epoch;
  let v = null;
  try { v = await api(`/api/docs/${id}/analysis`); } catch { v = null; }
  if (epoch !== state.epoch) return;
  if (!v) { toast("분석 상태를 읽지 못했습니다 — 잠시 뒤 다시 누르세요", true); return; }
  const plan = v.llmPlan || [], run = plan.filter((p) => p.run), skip = plan.filter((p) => !p.run);
  if (!run.length) { toast("지금 돌 LLM 판정이 없습니다 — 이미 거쳤습니다"); if (typeof docStatusPing === "function") docStatusPing(); return; }
  if (v.busy) { toast("다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요"); return; }
  const L = (tpbFmt(v) || {}).llm || {};
  if (typeof headsLlmReady === "function" && !(await headsLlmReady())) { // LLM 연결이 없다(알림은 그 함수가) — 막다른 길로 두지 않는다: 스크립트가 맞출 것(자리 맞춤 · 확실한 종속)이 있으면 그것만 반영할지 묻는다
    const P = (tpbFmt(v) || {}).place || 0, sure = tpbSure(v).filter((h) => h.sure).length;
    if (epoch === state.epoch && !L.planned && (P || sure)) await tpbApply({ note: "LLM 연결이 없어 LLM 판정은 돌리지 못합니다 — 스크립트가 맞추는 것만 반영할 수 있습니다." });
    return;
  }
  if (epoch !== state.epoch) return;
  const rows = ["LLM 판정 — 조정(서식 정리 계획 · 반영)보다 먼저, 스크립트가 뽑은 헤딩 · 표를 LLM 이 검증·보완합니다(이름 줄 진행표의 「LLM 검증·보완」 과 같은 일).", "",
    "돌 것:", ...run.map((p) => `   · ${p.name}`)];
  if (skip.length) rows.push(`   건너뜀 — ${skip.map((p) => p.name).join(" · ")}(이미 거쳤거나 할 것이 없습니다)`);
  if (L.done || L.applied || L.planned) rows.push("", "※ 헤딩 그래프를 다시 짓습니다 — 앞서 받은 서식 정리 계획은 새로 받고, 이미 반영한 서식은 문서에 그대로 남습니다.");
  rows.push("", "유료 LLM · 몇 분 걸립니다 · 문서는 바뀌지 않습니다 — 받은 서식 정리 계획은 「템플릿 조정」·「서식 조정」 칸에서 확인한 뒤 「모두 반영」 으로 반영합니다. 계속할까요?");
  if (!confirm(rows.join("\n")) || epoch !== state.epoch) return;
  await dsLlmRun();
}

// 「서식 조정 · 표지 n줄」 칸 — 반영이 형광펜·필드 표지 때문에 모양만 맞추고 남긴 줄(분석 상태 서식 항목의 llm.leftMarked — 지금도 대표와 다른 서식인 줄, 30개까지)로 누를 때마다 다음 줄
// (spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」 — 보정은 단계별: 한글에서 표지를 지운 뒤 「이 줄들만 맞추기」, 또는 그대로 둔다). 문서는 안 바꾼다 · app.js scrollToBlock
function tpbMarkGo() {
  const f = tpbFmt(), ids = (f && f.llm && f.llm.leftMarked) || [], n = (f && f.llm && f.llm.left && f.llm.left.marked) || ids.length;
  if (!ids.length) { toast("표지 때문에 모양만 맞춘 줄이 지금은 없습니다"); return; }
  TPB.mark = (TPB.mark + 1) % ids.length;
  if (typeof scrollToBlock === "function") scrollToBlock(ids[TPB.mark], true);
  toast(`표지 때문에 모양만 맞춘 줄 ${nf(TPB.mark + 1)}/${nf(n)} — 형광펜·필드 표지가 있어 레터 첫머리의 글은 그대로입니다. 한글에서 표지를 지운 뒤 「이 줄들만 맞추기」, 또는 그대로 둡니다${n > ids.length ? ` (${nf(ids.length)}줄까지 차례로 갑니다)` : ""}`);
}

function tplPlanGo() { // 다른 자리(이름 줄 진행표의 「남은 일: 서식 반영」 · 에이전트 보기의 「서식 반영하기」)에서 — 헤딩 추출 탭을 열고 「조정」 줄을 짚어 준다(반영은 그 줄의 단추로)
  if (typeof showTab === "function") showTab("Heads");
  let tries = 0;
  const find = () => {
    const cells = [...document.querySelectorAll("#headsOverview .hprog [data-tpb]")];
    if (cells.length) {
      cells[0].scrollIntoView({ block: "nearest" });
      for (const c of cells) { c.classList.remove("flash"); void c.offsetWidth; c.classList.add("flash"); }
      const b = cells.find((c) => c.dataset.tpb === "act" && !c.hidden && !c.disabled) || cells[0];
      b.focus({ preventScroll: true });
      return;
    }
    if (++tries < 12) setTimeout(find, 150); // 헤딩 추출 탭을 처음 열면 요약을 읽은 뒤에 그려진다
    else toast("「조정」 줄이 아직 없습니다 — 헤딩 추출 결과를 읽은 뒤에 보입니다");
  };
  find();
}
