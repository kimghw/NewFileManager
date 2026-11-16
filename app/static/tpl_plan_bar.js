"use strict";
// 진행 줄의 「조정」 줄 — 템플릿 조정 · 서식 조정 · 모두 반영(spec_hwpx_웹편집 ② §8-4 「계획 모두 반영」).
// 2026-11-16 사용자(진행 줄 그림 — 스크립트 / LLM 두 줄) "여기 밑에 ,, 템플릿 조정, 서식 조정 이 들어 가야함" · "확인 뒤 한 번에 반영... 을 좋고 다만 이 버튼을 어디에 둘건가... 헤딩 추출 탭 안에 두는 것도 좋고 … 찾기 쉽워야함".
// 헤딩 추출 탭 머리의 진행 줄(app.js headsProgLine — 스크립트 · LLM 두 층)에 셋째 층 「조정」 을 더한다: 칸 셋 =
//   「템플릿 조정」 = 레터가 대표와 다른 줄을 서식 종속 템플릿(T1L3a)으로 떼는 것 — 받아 둔 계획이 뗄 줄 수 · 반영하면 ✓(문서 글·서식은 안 바뀜 — 템플릿만)
//   「서식 조정」   = 같은 템플릿의 줄을 그 레벨 대표 서식에 맞추는 것 — 받아 둔 계획이 맞출 줄 수 · 반영하면 ✓(문서 서식이 바뀜)
//   행동 칸       = **「모두 반영」**(지금 문서 차례에서 받은 계획 전부를 에이전트가 고른 그대로, 모든 템플릿을 트랜잭션 하나로 — POST …/outline/agent/apply · 실행 취소 1) ·
//                   계획이 없거나 받은 뒤 문서가 바뀌었으면 「계획 받기」(서식 정리 계획만 — POST …/analysis/llm {only: "formats"} · 유료 · 문서는 안 바뀜)
// 두 조정 칸을 누르면 계획 보기(문서 옆 열 「LLM 이 바꾼 것」 의 「서식 계획」 절 — 템플릿 · 레벨마다 맞출 줄 · 뗄 줄 · 남긴 줄), 계획이 하나도 없으면 「템플릿 관계」 열(손으로 맞추고 떼는 곳).
// 「모두 반영」 은 이 줄 한 곳에만 둔다(design.md §10) — 템플릿 하나만 반영하는 길은 전처럼 템플릿 줄의 「계획대로 맞추기」 · ★ 열의 「적용」.
// 자료 = 분석 상태(GET …/analysis — doc_status.js dsState.main 의 서식 항목 llm{state, text, need, planned, applied, stale, change, moved, list}) — 따로 읽지 않는다.
// 부르는 곳: app.js headsProgLine(tplPlanRow — 세 단계를 다 보이는 진행 줄에만) · doc_status.js dsFetch(tplPlanBarSync) · 이름 줄 진행표 · 에이전트 보기(tplPlanGo) ·
// heads_run_all.js(tpbApply — 상태 줄 「전체 실행」 이 LLM 단계 뒤에 같은 함수로 반영한다 · tplPlanGo).
// 기대는 것: app.js(state · el · hBtn · nf · toast · api · structOp · flushAll · heads · headsRender · headsPoll · outlineLoad · showTab · H_JSON) · doc_status.js(dsState · docStatusPing) ·
// outline_match.js(olmLoad · olmRefresh) · heading_llm_diff.js(llmDiffOpen) · app.js tplRelOpen · tpl_agent.js(tpaSkillKey).
const TPB = { sig: null, busy: false };
const TPB_STATE = { none: "안 함", plan: "계획 받음 — 반영 전", llm: "반영함", running: "계획 받는 중", failed: "실패", skip: "할 것 없음" };
const tpbView = () => (typeof dsState === "object" && state.id && dsState.mainId === state.id ? dsState.main : null);
const tpbFmt = (v = tpbView()) => (v ? (v.items || []).find((i) => i.key === "formats") || null : null);

function tplPlanRow() { // 진행 줄을 그릴 때(app.js headsProgLine) — 「조정」 층의 이름표 + 칸 셋(빈 채로 만들고 바로 채운다)
  const layer = el("span", "hprog-layer tpb-layer", "조정");
  layer.title = "조정 — LLM 판정 뒤의 일: 템플릿 조정(레터가 다른 줄을 서식 종속 템플릿으로) · 서식 조정(같은 템플릿의 줄을 대표 서식에). 계획은 「헤딩 그래프(LLM)」 이 이어서 받고, 문서는 「모두 반영」 을 눌러야 바뀝니다";
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
  b.setAttribute("aria-label", `조정 ${i.text}${i.count ? ` ${i.count}${i.unit || ""}` : ""}${TPB_STATE[i.state] && !i.plain ? ` — ${TPB_STATE[i.state]}` : ""}`);
  b.onclick = i.run || null;
  b.hidden = !!i.hide;
}

function tpbDraw(els) {
  const [layer, tplB, fmtB, actB] = els, v = tpbView(), f = tpbFmt(v), L = f && f.llm;
  if (!tplB || !fmtB || !actB) return;
  const sig = JSON.stringify([state.id, !!f, f && f.state, L && [L.state, L.text, L.need, L.planned, L.applied, L.stale, L.done, L.change, L.moved, L.error], f && f.others, !!(v && v.busy), TPB.busy, !!state.busy]);
  if (sig === TPB.sig && tplB.childNodes.length) return;
  TPB.sig = sig;
  const ready = !!(f && f.state === "done" && L && typeof L.need === "number");
  const list = (L && L.list) || [], none = list.filter((x) => x.state === "none").length, busy = !!(v && v.busy) || TPB.busy;
  const has = ready && (L.planned || L.applied || L.stale || L.done); // 볼 계획이 있나
  const see = () => { if (has && typeof llmDiffOpen === "function") llmDiffOpen("fmt"); else if (typeof tplRelOpen === "function") tplRelOpen(); };
  const seeTip = has ? "누르면 계획 보기 — 문서 옆 열 「LLM 이 바꾼 것」 의 「서식 계획」(템플릿 · 레벨마다 맞출 줄 · 뗄 줄 · 남긴 줄)" : "누르면 「템플릿 관계」 열 — 손으로 대표에 맞추고 다른 템플릿으로 떼는 곳";
  const T = "템플릿 조정 — 레터가 대표와 다른 줄을 서식 종속 템플릿(T1L3a)으로 뗍니다(그 아래 줄도 같이). 문서의 글·서식은 안 바뀌고 템플릿만 나뉩니다";
  const F = "서식 조정 — 같은 템플릿의 줄을 그 레벨의 대표 서식에 맞춥니다(레터 첫머리 · 문단 모양 · 글자 모양). 문서의 서식이 바뀝니다";
  if (layer) layer.hidden = false;
  const both = (state_, extra, tip) => {
    tpbCell(tplB, { state: state_, text: "템플릿 조정", ...(extra && extra.tpl), title: `${T}\n${tip}\n— ${seeTip}`, run: see });
    tpbCell(fmtB, { state: state_, text: "서식 조정", ...(extra && extra.fmt), title: `${F}\n${tip}\n— ${seeTip}`, run: see });
  };
  const act = (i) => tpbCell(actB, { plain: true, state: "act", ...i });
  const fetchAct = (label) => act({ text: label, go: false, off: busy, run: () => tpbFetch(),
    title: busy ? "다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요" : "서식이 여러 가지인 템플릿마다 서식 정리 계획을 받습니다(유료 LLM · 템플릿마다 호출 하나 · 문서는 안 바뀜) — 이미 받은 계획은 다시 받지 않습니다" });
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
    act({ text: "", hide: true });
    return;
  }
  const rest = [L.stale ? `옛 계획 ${nf(L.stale)}(받은 뒤 문서가 바뀜)` : "", none ? `안 받음 ${nf(none)}` : "", L.applied ? `반영함 ${nf(L.applied)}` : ""].filter(Boolean).join(" · ");
  if (L.planned && L.change === undefined) { // 서버가 옛 판(이 기능 전 — 다시 켜기 전): 계획은 있는데 줄 수를 모른다. 수 없이 「계획 받음」 으로 보이고, 「모두 반영」 을 누르면 「서버를 다시 시작」 알림(tpbApply)
    both("plan", null, `받아 둔 계획 ${nf(L.planned)}개 — 줄 수는 서버(8114)를 다시 시작해야 보입니다`);
    act({ text: "모두 반영", go: true, off: busy || !!state.busy, run: () => tpbApply(), title: "서버가 옛 판이면 반영되지 않고 「서버를 다시 시작」 알림이 뜹니다" });
    return;
  }
  if (L.planned) {
    const todo = (L.change || 0) + (L.moved || 0), sum =`받아 둔 계획 ${nf(L.planned)}개(템플릿) — 맞출 줄 ${nf(L.change || 0)} · 뗄 줄 ${nf(L.moved || 0)}${rest ? ` · ${rest}` : ""}`;
    tpbCell(tplB, L.moved ? { state: "plan", text: "템플릿 조정", count: nf(L.moved), unit: "줄", title: `${T}\n${sum}\n— ${seeTip}`, run: see }
      : { state: "skip", text: "템플릿 조정", title: `${T}\n${sum} — 뗄 줄 없음(레터가 다른 줄이 없습니다)\n— ${seeTip}`, run: see });
    tpbCell(fmtB, L.change ? { state: "plan", text: "서식 조정", count: nf(L.change), unit: "줄", title: `${F}\n${sum}\n— ${seeTip}`, run: see }
      : { state: "skip", text: "서식 조정", title: `${F}\n${sum} — 맞출 줄 없음\n— ${seeTip}`, run: see });
    if (todo) {
      act({ text: "모두 반영", go: true, off: busy || !!state.busy, run: () => tpbApply(),
        title: `받아 둔 계획 ${nf(L.planned)}개를 에이전트가 고른 그대로 한 번에 반영합니다 — 대표에 맞출 줄 ${nf(L.change || 0)}개 · 서식 종속 템플릿으로 뗄 줄 ${nf(L.moved || 0)}개(그 아래 줄도 같이 갑니다) · 「그대로」 로 남긴 줄은 안 바뀝니다.\n문서가 바뀝니다 — 「실행 취소」 한 번으로 되돌립니다. 먼저 「템플릿 조정」·「서식 조정」 칸을 눌러 계획을 확인하세요.${rest ? `\n${rest}` : ""}` });
    } else if (L.stale || none) fetchAct("나머지 받기");
    else act({ text: "", hide: true });
    return;
  }
  if (L.stale || none) {
    const part = !!(L.applied || L.done); // 반영한 계획이 있는데 남은 것도 있다 — 반영으로 새로 생긴 서식 종속 템플릿 · 그 뒤 고친 템플릿
    const st = L.state === "failed" ? "failed" : part ? "llm" : "none";
    both(st, null, `서식 정리 계획 — ${rest}${part ? "\n남은 것 = 계획을 받지 않은 템플릿(반영으로 새로 생긴 서식 종속 템플릿 · 그 뒤 서식이 갈린 템플릿) — 「나머지 받기」" : ""}${L.state === "failed" && L.error ? `\n${L.error}` : ""}`);
    fetchAct(part ? "나머지 받기" : L.stale && !none ? "다시 받기" : "계획 받기");
    return;
  }
  both("llm", null, `모두 반영함 — 템플릿 ${nf(L.applied)}개${f.others ? ` · 대표와 다른 줄 ${nf(f.others)}(「그대로」 로 남긴 줄 · 그 뒤 고친 줄)` : ""}`);
  act({ text: "", hide: true });
}

async function tpbApply() { // 「모두 반영」 — 지금 문서 차례의 계획 전부를 트랜잭션 하나로(실행 취소 1) → 반영 결과 | null(못 함 — 까닭은 structOp.lastError). 「전체 실행」(heads_run_all.js)도 이 함수로 반영한다
  if (TPB.busy || !state.id) return null;
  TPB.busy = true;
  tplPlanBarSync(true);
  structOp.lastError = null;
  const r = await structOp("outline/agent/apply", { rev: state.serverRev });
  TPB.busy = false;
  if (r) {
    const ts = r.templates || [], n = (r.changed || []).length, made = ts.flatMap((t) => (t.splits || []).map((x) => `T${x.no}`));
    toast(r.nothing ? "바꿀 줄이 없습니다 — 계획이 모두 「그대로」 입니다"
      : `계획대로 반영했습니다 — 템플릿 ${nf(ts.length)}개 · ${[made.length ? `템플릿 조정: 서식 종속 템플릿 ${made.slice(0, 6).join(" · ")}${made.length > 6 ? " …" : ""}` : "", n ? `서식 조정: 맞춘 줄 ${nf(n)}` : ""].filter(Boolean).join(" · ") || "대표만 바뀜"} · 「실행 취소」 한 번으로 되돌립니다`);
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
