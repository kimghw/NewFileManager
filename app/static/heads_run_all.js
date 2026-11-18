"use strict";
// 전체 실행(조정까지) — 헤딩 추출 탭 상태 줄의 「전체 실행」 단추(spec_헤딩_추출 ② §7 「전체 실행」).
// 2026-11-16 사용자(헤딩 추출 진행 줄 그림 — 스크립트 · LLM · 조정 세 층과 「실행 ▾」) "지금 실행은 단계별 실행, 그리고 추가로 전체 실행(조정까지) 로 변경해줘".
// 「단계별 실행 ▾」(app.js headsRunMenu — 전의 「실행 ▾」)이 단계를 하나씩 골라 돌리는 것이라면, 이것은 **남은 단계를 조정까지 차례로** 돌린다:
//   ① LLM 판정 = 이어 돌리기 「LLM 검증·보완」(doc_status.js dsLlmRun — POST …/analysis/llm: 헤딩 · 템플릿 → 표 · 서식 정리 계획 같이.
//      스크립트 초안은 그 단계가 스스로 뽑고, 이미 LLM 을 거친 단계는 서버가 건너뛴다)
//   ② 조정 = 받은 계획 모두 반영(tpl_plan_bar.js tpbApply — POST …/outline/agent/apply: 템플릿 조정 · 서식 조정을 트랜잭션 하나로 · 실행 취소 1)
//   ③ 반영으로 새로 생긴 서식 종속 템플릿에 서식이 갈린 레벨이 남으면 ① 의 서식 정리 계획 → ② 를 다시(HRA_MAX 번까지)
// 새 실행 길을 만들지 않는다 — 끝점도 서버 검사도 기존 함수의 것이다. 남은 것은 서버의 분석 상태(GET …/analysis — llmPlan · 서식 항목의 llm{planned, change, moved, reps(대표를 바꿀 레벨), left(반영한 계획이 남긴 줄), list})로 센다.
// 누르면 무엇이 돌지(돌 LLM 단계 · 건너뛸 단계 · 반영할 줄 수)를 확인 창에 먼저 보인다 — 유료 LLM 이고 문서가 바뀐다. 계획을 보고 반영하려면 「단계별 실행」 과 조정 층의 「모두 반영」.
// 멈추는 곳(남기고 알린다 — spec_작업에이전트 ② §7): 헤딩 · 표 LLM 단계 실패 · 멈추기 · 반영 실패(표준 검사 · 그 사이 문서가 바뀜) · 다른 문서를 엶 · 되풀이 한도(HRA_MAX)에 닿았는데 남은 것이 있음.
// 서식 정리 계획만 실패하면 받은 계획은 반영하고 못 받은 템플릿을 남긴다. 끝나면 한 것 · 멈춘 까닭 · 남은 것과 보정할 자리를 알린다(알림 + 단추 title).
// 실행은 시작한 문서(id · epoch)에 못 박는다 — 그 사이 다른 문서를 열면 반영하지 않고 끝낸다.
// 부르는 곳: app.js headsResultsSummary(headsRunAllBtn — 헤딩 추출 탭 상태 줄, 「단계별 실행 ▾」 앞) · doc_agent_work.js agwRunning(headsAllRunning — 에이전트 보기의 진행 카드).
// 기대는 것: app.js(state · heads · api · hBtn · nf · toast · headsPoll · headsLlmReady · structOp) · doc_status.js(dsLlmRun · dsLlmStop · dsRunning · docStatusPing) ·
// tpl_plan_bar.js(tpbApply — 반영 결과를 돌려준다 · tplPlanGo) · heading_llm_diff.js(llmDiffOpen).
const HRA = { run: null, last: null }; // run = 도는 전체 실행 {id, epoch, t0, note, stop, chains, applies, sig, did, left} | null · last = 지난 실행 {id, text}(단추 title)
const HRA_MAX = 3; // LLM 이어 돌리기 · 반영을 각각 몇 번까지 — 반영으로 새로 생긴 서식 종속 템플릿의 「계획 → 반영」 을 되풀이하는 한도
const HRA_PAGES = 12; // 갈래가 한도(40)를 넘는 레벨을 차례로 넘길 때의 LLM 이어 돌리기 한도 — 못 본 갈래가 줄어드는 동안만(HRA_MAX 는 진척 없는 되풀이의 한도)
const HRA_PART = { heads: "헤딩 · 템플릿", tables: "표", formats: "서식 계획" };
const HRA_GONE = "다른 문서를 열어 멈췄습니다 — 그 뒤로는 새로 반영하지 않았습니다(그때 이미 보낸 반영이 있었다면 앞 문서에서 끝났을 수 있습니다 — 그 문서의 「실행 취소」 로 되돌립니다)";
const HRA_STOP = "멈추기를 눌러 멈췄습니다";
const HRA_CAP = `되풀이 한도(${HRA_MAX}번)에 닿아 멈췄습니다 — 「전체 실행」 을 다시 누르면 남은 것부터 이어서 합니다`; // 남은 것이 있는데 한도에 닿음 — 「끝」 이 아니다(2026-11-16 astra: 까닭이 알림에 없었다)
const hraLive = (R) => HRA.run === R && state.id === R.id && state.epoch === R.epoch;
const hraWait = (ms) => new Promise((res) => setTimeout(res, ms));

async function hraStatus(id) { // 지금 분석 상태를 서버에서 새로(이름 줄의 dsState 는 조금 늦을 수 있다) | null
  try { return await api(`/api/docs/${id}/analysis`); } catch { return null; }
}

function hraLeft(v) { // 분석 상태 → 남은 것 {llm[돌 LLM 단계], skip[건너뛸 단계], plans(반영할 수 있는 계획 수), change, moved, apply(반영할 것이 있나), need[계획이 없거나 옛것인 템플릿]}
  const f = (v.items || []).find((i) => i.key === "formats"), L = (f && f.llm) || {}, plan = v.llmPlan || [];
  // 반영하면 바뀔 것 = 맞출 줄 + 뗄 줄 + **대표를 바꿀 레벨**(reps — 「맞출 줄 0 · 대표 변경 1」 인 계획도 반영할 것이다: 2026-11-16 astra — 전에는 줄 수가 0 이면 조정을 안 돌렸다). null = 서버가 옛 판(줄 수를 모른다 — 반영은 해 본다)
  const lines = L.change === undefined ? null : (L.change || 0) + (L.moved || 0) + (L.reps || 0);
  const h = (v.items || []).find((i) => i.key === "heads") || {};
  const rel = ((v.items || []).find((i) => i.key === "templates") || {}).hints || [], sure = rel.filter((x) => x.sure).length; // 종속 — 확실한 것은 조정(모두 반영)이 저절로 건다 · 애매한 것은 제안으로 남긴다
  // undecided = 헤딩 판정의 미판정 노드(LLM 구간 검증이 실패해 스크립트 초안으로 남은 것) — 있으면 조정(반영)을 하지 않는다 · kept/unanswered = 반영해도 남는 줄(에이전트가 그대로 둔 것 · 답이 없던 것)
  return { llm: plan.filter((p) => p.run), skip: plan.filter((p) => !p.run), plans: L.planned || 0, change: L.change || 0, moved: L.moved || 0, reps: L.reps || 0,
    // done = **반영한** 계획이 지금 문서에 남긴 줄(서버가 지금 갈래로 다시 센다 — 분석 상태 서식 항목의 llm.left): 에이전트가 그대로 둔 줄 · 답이 없어 안 바꾼 줄(검토한 것이 아니다).
    // 반영한 뒤에도 남는다 — 「받음」 인 계획의 kept·unanswered(아래)와 따로 · norep = 대표가 없는 레벨(갈래가 하나여도 맞춘 레벨이 아니다)
    // marked = 표지(형광펜·필드) 때문에 모양만 맞추고 남긴 줄 가운데 지금도 대표와 다른 서식인 줄(spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」)
    done: L.left ? { kept: L.left.kept || 0, unanswered: L.left.unanswered || 0, marked: L.left.marked || 0 } : null, norep: (f && f.noRep) || 0, // null = 서버가 옛 판(이 수를 모른다 — 끝난 글은 이번 실행이 센 수로)
    place: (f && f.place) || 0, // 자리 맞춤이 남은 줄(레터 뒤 묶음 빈칸 · 둘째 줄 = 글 시작 — spec_hwpx_웹편집 ② §8-8): 계획이 없어도 조정(모두 반영)이 스크립트로 건다
    apply: (!!L.planned && lines !== 0) || sure > 0 || ((f && f.place) || 0) > 0, sure, hints: rel.length - sure, need: (L.list || []).filter((x) => x.state === "none" || x.state === "stale"),
    undecided: h.undecided || 0, kept: L.kept || 0, unanswered: L.unanswered || 0, omitted: L.omitted || 0,
    at: Object.fromEntries((L.list || []).filter((x) => x.state === "planned" && x.at != null).map((x) => [x.tpl, x.at])) }; // 반영할 계획의 표시 — 방금 읽은 것 그대로 반영한다(tpbApply 의 plans)
}
function hraUnseen(P, skipUndec = false) { // 반영할 것이 없어도 「다 봤다」 는 아니다 — 남아 있는, 사람이 볼 것(미판정 헤딩 · 받아 둔 계획이 남긴 줄 · 못 본 갈래) [글…]. 「남은 것 없음」 으로 뭉개지 않는다(2026-11-16 astra)
  const out = [];
  if (P.undecided && !skipUndec) out.push(`헤딩 판정의 미판정 ${nf(P.undecided)}곳(LLM 구간 검증 실패 — 「단계별 실행」 의 헤딩 판정을 다시)`);
  if (P.hints) out.push(`종속 제안 ${nf(P.hints)}개(애매한 것 — 결과 화면의 「템플릿 관계」 절에서 고릅니다)`);
  const k = [P.kept ? `에이전트가 그대로 둔 줄 ${nf(P.kept)}` : "", P.unanswered ? `답이 없어 안 바꾼 줄 ${nf(P.unanswered)}` : "", P.omitted ? `서식 가짓수가 많아 못 본 서식 ${nf(P.omitted)}가지` : ""].filter(Boolean);
  if (k.length) out.push(`받아 둔 계획이 남긴 것 — ${k.join(" · ")}(조정 층의 칸을 눌러 계획 보기 · 「템플릿 관계」 에서 손으로)`);
  out.push(...hraKept(P.done));
  if (P.norep) out.push(`대표가 없는 레벨 ${nf(P.norep)}개(「템플릿 관계」 에서 줄 하나를 대표로 — 대표가 없으면 맞춘 레벨로 세지 않습니다)`);
  return out;
}
// 반영한 계획이 남긴 줄 — 「끝」 으로 뭉개지 않는다: 에이전트가 그대로 둔 줄(까닭은 계획에) · 답이 없어 안 바꾼 줄(검토한 것이 아니다). 반영한 뒤에도(다음 「전체 실행」 에서도) 알린다 → [글] | []
function hraKept(d) {
  const kept = d ? [d.kept ? `그대로 둔 줄 ${nf(d.kept)}` : "", d.unanswered ? `답이 없어 안 바꾼 줄 ${nf(d.unanswered)}` : "",
    d.marked ? `형광펜·필드 표지가 있어 모양만 맞춘 줄 ${nf(d.marked)}(글은 그대로 — ${d.unanswered ? "남긴 줄은 조정 층 「서식 조정」 칸에서" : "조정 층 「서식 조정」 칸을 누르면 그 줄로"})` : ""].filter(Boolean).join(" · ") : "";
  return kept ? [`반영한 계획이 남긴 것 — ${kept}(「반영한 계획 보기」 · 「템플릿 관계」 에서 손으로)`] : [];
}
const hraUndec = (n) => `헤딩 판정에 미판정 ${nf(n)}곳이 있어(LLM 구간 검증 실패 — 스크립트 초안 그대로) 조정(반영)은 하지 않았습니다 — 받은 계획은 남아 있습니다: 「단계별 실행」 의 헤딩 판정을 다시 돌리거나, 조정 층에서 계획을 확인한 뒤 「모두 반영」 을 누르세요`;

function hraAsk(P) { // 확인 창의 글 — 무엇이 돌고 무엇이 바뀌나
  const rows = ["전체 실행 — 남은 단계를 조정까지 차례로 돌립니다(이미 거친 단계는 건너뜁니다).", ""];
  if (P.llm.length) {
    rows.push("① LLM 판정 · 유료(몇 분):", ...P.llm.map((p) => `   · ${p.name}`));
    if (P.skip.length) rows.push(`   건너뜀 — ${P.skip.map((p) => HRA_PART[p.key] || p.name).join(" · ")}(이미 거쳤거나 할 것이 없습니다)`);
    rows.push("② 조정 — 받은 서식 정리 계획을 에이전트가 고른 그대로 모두 반영합니다(템플릿 조정 · 서식 조정).");
  } else {
    rows.push("LLM 판정은 이미 거쳐 건너뜁니다.",
      `조정 — 받아 둔 서식 정리 계획 ${nf(P.plans)}개(템플릿)를 에이전트가 고른 그대로 모두 반영합니다: 대표에 맞출 줄 ${nf(P.change)} · 서식 종속 템플릿으로 뗄 줄 ${nf(P.moved)}${P.reps ? ` · 대표를 바꿀 레벨 ${nf(P.reps)}` : ""}.`);
  }
  if (P.sure) rows.push(`   템플릿 종속 — 한 자리에만 매달린 템플릿 ${nf(P.sure)}개를 그 자리의 템플릿 아래로 넣습니다(확실한 것만 — 문서는 안 바뀌고 템플릿만).`);
  rows.push(`   자리 맞춤(스크립트) — 맞춘 뒤 레터 뒤 빈칸을 묶음 빈칸으로 · 둘째 줄을 글 시작에 맞춥니다${P.place ? `(지금 ${nf(P.place)}줄 + 맞춘 줄)` : ""}.`);
  rows.push("   문서가 바뀝니다 — 반영 한 번마다 「실행 취소」 한 번으로 되돌립니다.",
    `   반영으로 새로 생긴 서식 종속 템플릿에 서식이 갈린 레벨이 남으면 그 계획도 이어서 받아 반영합니다(${HRA_MAX}번까지 · 유료).`, "",
    "계획을 먼저 보고 반영하려면 「취소」 를 누르고 「단계별 실행」 과 조정 층의 「모두 반영」 을 쓰세요. 계속할까요?");
  return rows.join("\n");
}

// ---- 단추(상태 줄 — app.js headsResultsSummary 가 그릴 때마다 새로 만든다 · 도는 동안은 「멈추기」)
function headsRunAllBtn() {
  const b = hBtn("", () => (HRA.run ? hraStop() : headsRunAll()), { cls: "btn sm hrun-all" });
  hraBtnDraw(b);
  return b;
}
function hraBtnDraw(b) {
  const pick = typeof headsPickRunning === "function" && !!headsPickRunning(); // 고른 단계를 차례로 도는 「단계별 실행」(heads_run_pick.js) — 그 단계 사이에도 끈다
  const R = HRA.run && HRA.run.id === state.id ? HRA.run : null, job = (heads.view || {}).job, other = !R && (!!HRA.run || pick || !!(job && job.status === "running"));
  const last = HRA.last && HRA.last.id === state.id ? `\n지난 전체 실행: ${HRA.last.text}` : "";
  b.textContent = R ? (R.stop ? "멈추는 중…" : "멈추기") : "전체 실행";
  b.disabled = R ? R.stop : other || !state.id;
  b.classList.toggle("on", !!R);
  b.title = R ? `전체 실행 중 — ${R.note}\n누르면 멈춥니다: 지금 도는 단계가 끝나면 멈추고, 아직 하지 않은 조정(반영)은 하지 않습니다 — 이미 받은 결과 · 계획 · 반영은 남습니다`
    : other ? "다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요"
      : "전체 실행(조정까지) — 남은 단계를 차례로 끝까지 돌립니다: LLM 판정(헤딩 · 템플릿 → 표 · 서식 정리 계획) → 조정(받은 계획 모두 반영 — 템플릿 조정 · 서식 조정).\n"
        + `이미 거친 단계는 건너뜁니다 · 유료 LLM · 문서가 바뀝니다(실행 취소로 되돌림) — 누르면 무엇이 돌지 먼저 보이고 묻습니다. 단계를 하나씩 돌리거나 계획을 보고 반영하려면 「단계별 실행」${last}`;
}
function hraSync() { // 실행의 시작 · 끝 · 지금 하는 일이 바뀜 — 그려 둔 단추를 그 자리에서 다시
  for (const b of document.querySelectorAll("#headsOverview .hrun-all")) hraBtnDraw(b);
}

function hraStop() { // 「멈추기」 — 지금 도는 단계가 끝나면 멈춘다(바로 끊지 않는다)
  const R = HRA.run;
  if (!R || R.stop) return;
  R.stop = true;
  hraSync();
  const job = (heads.view || {}).job;
  if (job && job.status === "running" && job.chain && typeof dsLlmStop === "function") dsLlmStop(); // 도는 이어 돌리기 — DELETE …/analysis/llm(알림도 그 함수가)
  else toast("전체 실행을 멈춥니다 — 지금 하는 일이 끝나면 멈춥니다");
}

function headsAllRunning() { // 에이전트 보기의 진행 카드(doc_agent_work.js agwRunning) — 도는 전체 실행 | null
  const R = HRA.run;
  if (!R || state.id !== R.id) return null;
  const A = typeof dsRunning === "function" ? dsRunning() : null; // 그 안에서 도는 LLM 단계의 자세한 글(단계 · 템플릿)
  return { label: "전체 실행 — LLM 판정 → 서식 계획 → 조정(모두 반영)", note: A ? `${R.note} · ${A.note}` : R.note, t0: R.t0, stopping: R.stop, stop: () => hraStop() };
}

// ---- 실행
// opt.asked = 부른 쪽이 이미 확인받았다(대시보드의 「이어서 한 번에」 · 에이전트 실행 카드 — spec_양식표준화 ② §4) — 확인 창만 건너뛴다(LLM 연결 · 멈추는 검사는 그대로).
// → {ok, text}(끝까지 감 · 멈춤 — HRA.last 와 같은 글) | undefined(시작하지 않음 — 까닭은 알림 글)
async function headsRunAll(opt = {}) {
  if (HRA.run || !state.id) return;
  if (typeof headsPickRunning === "function" && headsPickRunning()) { toast("단계별 실행이 도는 중입니다 — 끝난 뒤 누르세요"); return; } // 단계 사이의 틈에 끼어들지 않는다
  const id = state.id, epoch = state.epoch;
  const v = await hraStatus(id);
  if (epoch !== state.epoch || HRA.run) return;
  if (!v) { toast("분석 상태를 읽지 못했습니다 — 잠시 뒤 다시 누르세요", true); return; }
  if (!(v.llmPlan || []).length) { toast("이 문서에는 돌릴 헤딩 · 표 분석이 없습니다(헤딩 추출은 hwpx 문서만)", true); return; }
  if (v.busy) { toast("다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요"); return; }
  const P = hraLeft(v);
  if (!P.llm.length && !P.apply) {
    const more = hraUnseen(P), tail = more.length ? ` · 남은 것: ${more.join(" / ")}` : "";
    toast((P.plans ? "돌릴 단계가 없습니다 — LLM 판정을 마쳤고, 받아 둔 계획에는 바꿀 줄이 없습니다" : more.length ? "돌릴 단계가 없습니다 — LLM 판정과 조정을 마쳤습니다" : "남은 단계가 없습니다 — LLM 판정과 조정을 모두 마쳤습니다") + tail,
      false, more.length && typeof tplPlanGo === "function" ? { label: "조정 줄 보기", run: () => tplPlanGo() } : null);
    return;
  }
  if (!P.llm.length && P.undecided) { toast(hraUndec(P.undecided), true, typeof tplPlanGo === "function" ? { label: "조정 줄 보기", run: () => tplPlanGo() } : null); return; } // 남은 것이 반영뿐인데 헤딩 판정에 미판정이 있다 — 묻지 않고 알린다
  if (P.llm.length && !(await headsLlmReady())) return; // LLM 연결이 없으면 알림은 그 함수가
  if (epoch !== state.epoch || HRA.run || (!opt.asked && !confirm(hraAsk(P))) || epoch !== state.epoch) return;
  const R = HRA.run = { id, epoch, t0: Date.now(), note: "시작", stop: false, chains: 0, applies: 0, sig: null,
    did: { llm: [], tpls: 0, lines: 0, splits: 0, undo: 0 }, left: [] };
  hraSync();
  let out;
  try { out = await hraLoop(R, v); } catch (e) { out = { why: `오류 — ${e.message}`, v: null }; }
  HRA.run = null;
  const P2 = out.v ? hraLeft(out.v) : null, text = hraDone(R, out.why, P2);
  HRA.last = { id, text };
  hraSync();
  if (typeof docStatusPing === "function") docStatusPing();
  const adj = !!P2 && (P2.need.length > 0 || P2.apply) && typeof tplPlanGo === "function" && state.id === id; // 조정 층에 남은 것이 있다 — 그 줄로
  // 끝나면 결과 화면을 연다(문서 옆 열 「LLM 이 바꾼 것」 의 「반영 결과」 — 무엇이 어떻게 바뀌었나 · 남긴 것: spec_헤딩_추출 ② §7 「결과 화면」) — 반영이 있었고 그 문서가 그대로 열려 있을 때만. 알림 글은 그대로 남긴다
  if ((R.did.tpls || R.did.merged) && state.id === id && state.epoch === epoch && typeof llmDiffOpen === "function") llmDiffOpen(R.did.tpls ? "res" : "rel");
  toast(text, !!out.why && out.why !== HRA_STOP && out.why !== HRA_CAP, adj ? { label: "조정 줄 보기", run: () => tplPlanGo() }
    : R.did.tpls && typeof llmDiffOpen === "function" && state.id === id ? { label: "반영한 계획 보기", run: () => llmDiffOpen("fmt") } : null);
  return { ok: !out.why, text };
}

// 남은 것이 없을 때까지: LLM 이어 돌리기 → 반영 → (반영으로 새로 남은 계획 → 반영) … → {why 멈춘 까닭("" = 끝까지 감), v 마지막 분석 상태 | null}
async function hraLoop(R, v) {
  for (;;) {
    if (!hraLive(R)) return { why: HRA_GONE, v: null };
    if (R.stop) return { why: HRA_STOP, v };
    let why = "", ran = null;
    if (v.busy) { // 다른 헤딩 작업(문서가 바뀐 뒤의 1단계 다시 추출 …)이 끝난 뒤에
      R.note = "다른 헤딩 작업이 끝나기를 기다리는 중";
      hraSync();
      await hraWait(1000);
    } else {
      // sig = 남은 것의 꼴(단계 · 계획이 필요한 템플릿과 그 못 본 갈래 수) — 못 본 갈래가 줄었으면(갈래가 많은 레벨을 차례로 넘기는 중) 같은 템플릿이라도 다시 받는다
      const P = hraLeft(v), sig = JSON.stringify([P.llm.map((p) => p.key), P.need.map((x) => `${x.tpl}:${x.omitted || 0}`)]);
      const om = P.need.reduce((n, x) => n + (x.omitted || 0), 0), paging = R.om != null && om < R.om; // 못 본 갈래가 앞 차례보다 줄었다 — 되풀이 한도와 따로 센다(HRA_PAGES)
      // 같은 것(같은 단계 · 같은 템플릿)이 그대로 남았으면 다시 묻지 않는다 — 방금 못 받은 계획을 되풀이해 부르지 않게
      if (P.llm.length && sig !== R.sig && (R.chains < HRA_MAX || (paging && R.chains < HRA_PAGES))) { R.sig = sig; R.om = om; R.chains += 1; ran = P.llm.map((p) => p.key); why = await hraChain(R, P); }
      else if (P.apply && P.undecided) return { why: hraUndec(P.undecided), v }; // 다 판정하지 못한 헤딩 그래프 위의 계획은 사람이 보고 반영한다(남긴다 — 2026-11-16 astra: 미검증을 완료로 보고 반영하던 것)
      else if (P.apply && R.applies < Math.max(HRA_MAX, R.chains)) { R.applies += 1; why = await hraApply(R, P); } // 반영은 이어 돌리기 한 번마다 한 번까지(갈래를 차례로 넘길 때도)
      else { // 더 할 것이 없다 — 다 했거나 · 방금 물은 것이 그대로 남았거나(다시 묻지 않는다) · 한도에 닿았거나(까닭을 알린다)
        const capped = (P.llm.length > 0 && sig !== R.sig && R.chains >= (paging ? HRA_PAGES : HRA_MAX)) || (P.apply && R.applies >= Math.max(HRA_MAX, R.chains));
        return { why: capped ? HRA_CAP : "", v };
      }
    }
    const next = hraLive(R) ? await hraStatus(R.id) : null;
    if (ran && next) { // 한 것 = 돌린 단계 가운데 이제 남지 않은 것(멈췄거나 일부만 된 단계는 「한 것」 에 넣지 않는다 — 남은 것에 보인다)
      const still = new Set(hraLeft(next).llm.map((p) => p.key));
      R.did.llm.push(...ran.filter((k) => !still.has(k)));
    }
    if (why) return { why, v: next };
    if (!next) return { why: hraLive(R) ? "분석 상태를 읽지 못해 멈췄습니다" : HRA_GONE, v: null };
    v = next;
  }
}

async function hraChain(R, P) { // 남은 LLM 단계 — 「LLM 검증·보완」 이어 돌리기를 시작하고 끝날 때까지 → 멈춘 까닭 | ""
  const keys = P.llm.map((p) => p.key);
  R.note = `LLM — ${keys.map((k) => HRA_PART[k] || k).join(" · ")}${R.chains > 1 ? `(${R.chains}번째)` : ""}`;
  hraSync();
  if ((await dsLlmRun()) !== true) return hraLive(R) ? "LLM 단계를 시작하지 못했습니다" : HRA_GONE; // 까닭은 그 함수가 알렸다(헤딩 작업이 도는 중 · 옛 서버 …)
  const job = await hraJob(R, ((heads.view || {}).job || {}).started);
  if (!hraLive(R)) return HRA_GONE;
  if (!job) return "도는 LLM 작업을 놓쳤습니다(서버가 다시 시작됐을 수 있습니다) — 진행 줄을 확인한 뒤 다시 누르세요";
  if (job.status === "failed") {
    if (keys.some((k) => k !== "formats")) return `LLM 단계가 실패했습니다 — ${job.error || "까닭 모름"}`;
    R.left.push(`서식 정리 계획을 받지 못함 — ${job.error || "까닭 모름"}`); // 서식 계획만 돌았다 — 이미 받은 계획은 반영하고 못 받은 템플릿은 남긴다
    return "";
  }
  return job.stopping || R.stop ? HRA_STOP : ""; // 멈추기 — 받은 계획이 있어도 반영하지 않는다(남긴다)
}

async function hraJob(R, started) { // 그 헤딩 작업이 끝날 때까지 — 요약은 app.js headsPoll 이 읽어 heads.view 에 둔다(따로 읽지 않는다) → 끝난 작업 | null(놓침 · 다른 문서)
  for (let dead = 0; ;) {
    await hraWait(700);
    if (!hraLive(R)) return null;
    const j = (heads.view || {}).job, ours = !!j && j.started === started;
    if (ours && j.status !== "running") return j;
    if (heads.pollEpoch != null) { dead = 0; continue; } // 읽는 중
    if (++dead > (ours ? 20 : 3)) return null; // 읽기가 끊긴 채다 — 서버가 세션을 잃었거나 내려갔다
    if (ours) headsPoll(); // 일시 오류로 끊겼으면 다시 잇는다
  }
}

async function hraApply(R, P) { // 조정 — 받은 계획 모두 반영(진행 줄 「조정」 의 「모두 반영」 과 같은 함수 · 같은 끝점) → 멈춘 까닭 | ""
  R.note = `조정 — 계획 ${nf(P.plans)}개 모두 반영(맞출 줄 ${nf(P.change)} · 뗄 줄 ${nf(P.moved)}${P.reps ? ` · 대표 변경 ${nf(P.reps)}` : ""}${P.place ? ` · 자리 맞춤 ${nf(P.place)}` : ""})`;
  hraSync();
  for (let i = 0; state.busy && i < 50; i += 1) await hraWait(200); // 다른 편집이 끝난 뒤에
  if (!hraLive(R)) return HRA_GONE;
  if (R.stop) return HRA_STOP;
  const undo0 = state.undo || 0, r = await tpbApply({ ask: false, plans: P.at }); // 확인은 시작할 때 한 번 받았다 — 「모두 반영」 단추의 확인 창은 건너뛴다 · 방금 읽은 분석 상태의 계획 그대로
  if (!hraLive(R)) return HRA_GONE;
  if (!r) { // 까닭은 structOp 이 알렸다(표준 검사 422 · 그 사이 문서가 바뀜 409 …)
    const e = structOp.lastError;
    return `조정(모두 반영)을 하지 못했습니다 — ${e && e.message ? e.message : "다른 편집이 도는 중이거나 반영할 계획이 없습니다"}`;
  }
  const ts = r.templates || [];
  R.did.tpls += ts.length;
  R.did.lines += (r.changed || []).length - (r.placed || []).length - (r.left || []).length; // 대표에 맞춘 줄(모양만 맞춘 줄은 빼고)
  R.did.placed = (R.did.placed || 0) + (r.placed || []).length; // 자리 맞춤만 한 줄(묶음 빈칸 · 둘째 줄 = 글 시작 — ② §8-8)
  R.did.splits += ts.reduce((n, t) => n + (t.splits || []).length, 0);
  R.did.reps = (R.did.reps || 0) + ts.reduce((n, t) => n + (t.levels || []).filter((x) => x.repChanged).length, 0); // 대표를 바꾼 레벨(맞춘 줄이 0 이어도 한 일이다)
  R.did.merged = (R.did.merged || 0) + (r.merged || []).length; // 저절로 건 종속(확실한 것)
  R.did.undo += Math.max(0, (state.undo || 0) - undo0);
  R.did.kept = (R.did.kept || 0) + P.kept; // 반영한 계획이 남긴 줄 — 끝난 글의 「남긴 것」(마지막 분석 상태를 못 읽었을 때만 쓴다 — 읽었으면 서버가 다시 센 수: hraDone)
  R.did.unanswered = (R.did.unanswered || 0) + P.unanswered;
  R.did.marked = (R.did.marked || 0) + (r.left || []).length; // 표지 때문에 모양만 맞춘 줄(② §8-8 「짝 표지가 든 줄」 — 마지막 분석 상태를 못 읽었을 때만 쓴다)
  return "";
}

function hraDone(R, why, P) { // 끝난 글 — 한 것 · (멈춘 까닭) · 남은 것과 보정할 자리. P = 마지막 분석 상태의 남은 것 | null(못 읽음 · 다른 문서)
  const d = R.did, llm = [...new Set(d.llm)].map((k) => HRA_PART[k] || k);
  const did = [llm.length ? `LLM ${llm.join(" · ")}` : "",
    d.tpls || d.merged || d.placed ? `조정 — ${[d.tpls ? `템플릿 ${nf(d.tpls)}개 반영(맞춘 줄 ${nf(d.lines)}${d.reps ? ` · 대표 변경 ${nf(d.reps)}` : ""}${d.splits ? ` · 서식 종속 템플릿 ${nf(d.splits)}` : ""})` : "", d.placed ? `자리 맞춤 ${nf(d.placed)}줄` : "", d.merged ? `템플릿 종속 ${nf(d.merged)}` : ""].filter(Boolean).join(" · ")}` : ""].filter(Boolean).join(" → ");
  const undo = d.undo ? ` · 「실행 취소」 ${d.undo > 1 ? `${nf(d.undo)}번` : "한 번"}으로 되돌립니다` : "";
  const left = [...R.left];
  if (P) {
    const judge = P.llm.filter((p) => p.key !== "formats").map((p) => HRA_PART[p.key] || p.key);
    if (judge.length) left.push(`LLM 판정을 안 한 단계 ${judge.join(" · ")} — 「단계별 실행」`);
    if (P.need.length) left.push(`계획을 받지 않은 템플릿 ${nf(P.need.length)}개(${P.need.slice(0, 5).map((x) => `T${x.no}`).join(" · ")}${P.need.length > 5 ? " …" : ""}) — 조정 층의 「나머지 받기」`);
    // 반영은 했지만 계획이 남긴 줄(에이전트가 그대로 둔 줄 · 답이 없어 안 바꾼 줄)은 서버가 **지금 문서의 갈래로 다시 센 수**(P.done)로 알린다 — 이번에 반영한 것뿐 아니라 앞서 반영한 계획이 남긴 것도(hraUnseen 이 싣는다)
    if (P.apply) left.push(`반영하지 않은 계획 ${nf(P.plans)}개 — 조정 층의 「모두 반영」`, ...hraKept(P.done || d));
    else left.push(...hraUnseen(P, !!why && why.startsWith("헤딩 판정에 미판정")), ...(P.done ? [] : hraKept(d))); // 바꿀 줄이 없는 계획 · 미판정 · 반영한 계획이 남긴 줄 — 「남은 것 없음」 이 아니다(서버가 옛 판이면 이번 실행이 센 수로)
  } else left.push(...hraKept(d)); // 마지막 분석 상태를 못 읽었다(다른 문서 · 읽기 실패) — 이번 실행이 반영하며 센 수로
  const rest = left.length ? ` · 남은 것: ${left.join(" / ")}` : "";
  return why ? `전체 실행 멈춤 — ${why}${did ? ` · 한 것: ${did}${undo}` : ""}${rest}` : `전체 실행 끝 — ${did || "새로 한 것 없음"}${undo}${rest || " · 남은 것 없음"}`;
}
