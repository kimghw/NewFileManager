"use strict";
/* 분석 상태 — 문서 이름 줄의 표시(index.html #docStatus · 둘째 면 머리 #peerStatus — spec_작업 ② §20, 2026-11-15 사용자 "이게 task 마다 작업을 표준화 했으면 좋겠는데. 그래서 올리면
   어디까지 작업이 되었는지 표시하는거지. 기본적으로 헤딩,표 분석은 해야하고 … 헤딩, 표 분석도 스크립트기반, 그리고 LLM 분리, 그리고 구분 기준은 옵션").
   어느 TASK · 어느 패널 탭에서나 같은 자리에 같은 꼴: 「헤딩 ✓ · 표 ✓ · LLM 안 함 · 구분 기준 안 함」 — 기본 분석(헤딩 · 표 — 스크립트, 올리면 저절로) · LLM 판정(사람이 단추로) ·
   구분 기준 LLM 검토(옵션 — 연구개발 문서만). 값은 서버가 센다(GET /api/docs/{id}/analysis — app/analysis.py) — 여기는 그리기와 다시 읽기뿐이다.
   - 항목은 누르는 표시다 — 그 도구로 간다(헤딩 · LLM → 「헤딩 추출」 · 표 → 「표」 · 구분 기준 → 「작업 개요」 + 2열 검토 결과). 여기서 바로 도는 것은 「분석」 단추 하나(기본 분석이 없을 때 —
     첫 분석과 같은 끝점 · 스크립트만). 유료 LLM 은 그 도구의 단추로만 돈다.
   - 다시 읽는 때: docStatusLoad(app.js taskDraw — 문서를 열 때 · 닫을 때 · TASK 를 고친 뒤) · docStatusPing(headsRender · 구분 기준 검토의 시작과 끝) · docStatusPeer(peerSync — 둘째 면의 문서가 바뀔 때),
     그리고 도는 것이 있는 동안 2초마다. 같은 내용이면 다시 그리지 않는다(포커스 유지 — 지난 시간 글만 1초마다).
   - 문서를 고친 뒤에도 「✓」 다(뼈대 유지 — 다시 돌리라고 하지 않는다). 해당 없는 항목은 안 보인다(일반 문서의 구분 기준 · docx 는 「헤딩 · 표 분석 없음(hwpx 만)」 한마디).
   2026-11-16 넓힘(② §20 「넷 · 진행표 · LLM 검증·보완」 — 사용자 "모든 문서의 템플릿/서식/헤딩/테이블 작업은 공통 … 어디까지 했는지 알 수가 없다" · 답 「줄 넷 + 눌러서 표」 · 「단추 하나로 넷을 차례로」):
   줄 = 「헤딩 ✓ · 템플릿 ✓ · 서식 0/4 · 표 ✓ · LLM 1/4 ▾」(서식 = 맞춘 레벨/레벨 · LLM = LLM 칸이 끝난 일/4). 표시를 누르면(구분 기준 빼고) **진행표**(4×3 — 스크립트 · LLM 검증·보완 · 문서 반영)가
   이름 줄 아래로 펼쳐지고, 칸을 누르면 그 도구로 간다. 진행표 아래 「LLM 검증·보완」(POST …/analysis/llm — 「돌 것」 = 서버 llmPlan 을 보인 단추가 확인) · 도는 동안 단계마다 상태 · 「멈추기」(DELETE).
   app.js(state · api · el · $ · showTab · toolShown · headsFirst · headsRender · headsPoll · heads · H_JSON · flushAll · tplRelOpen · divReviewList · dv · worksList · PEEK) 다음에 읽힌다.
   tpl_agent.js(tplAgentOpen · TPA · TPA_NEW)는 부를 때 찾는다. doc_agent_work.js agwRunning 이 dsRunning 을 읽는다(진행 카드). */
const DS_POLL = 2000; // 도는 것이 있는 동안 다시 읽는 간격
const dsState = { main: null, peer: null, mainId: "", peerId: "", sig: { main: "", peer: "" }, tableSig: "", poll: 0, ping: 0, tick: 0, seq: 0 };
const dsHost = (which) => $(which === "main" ? "docStatus" : "peerStatus");
const dsId = (which) => (which === "main" ? state.id : dsState.peerId) || "";
const dsSecs = (t) => { const s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s < 60 ? `${s}초` : `${Math.floor(s / 60)}분 ${s % 60}초`; };
const dsReviewing = () => typeof dv !== "undefined" && !!(dv.marks && dv.marks.reviewing); // 이 화면이 건 구분 기준 검토 — 서버가 「도는 중」 을 적기 전에도 보이게
const dsBusy = (v) => !!v && (v.busy === true || v.base === "running" || v.items.some((i) => i.state === "running" || (i.llm && i.llm.state === "running"))); // busy = 헤딩 작업이 하나라도 도는 중(탭을 열 때 저절로 도는 1단계도 — 그동안은 「분석」 을 못 건다)

function dsKind(which, view) { // 작업 종류 — 화면이 아는 값이 먼저(작업 저장이 꺼져 있으면 서버는 모른다)
  if (which === "main") return (state.task && state.task.kind) || view.kind || "";
  const w = (typeof worksList !== "undefined" ? worksList : []).find((x) => x.id === dsState.peerId);
  return ((w && w.task) || {}).kind || view.kind || "";
}

function dsBase(it, since) { // 헤딩 · 표 — 기본 분석(스크립트)
  const go = "Table", n = it.name;
  if (it.state === "done") return { text: n, mark: "✓", cls: "ok", go, title: it.text + (it.moved ? "\n그 뒤 문서를 고쳤습니다 — 결과는 뼈대로 그대로 씁니다(새 레터 · 서식 · 표가 생기면 따로 알립니다)" : "") };
  if (it.state === "running") return { text: `${n} 분석 중`, spin: true, since, cls: "run", go, title: `${n} 분석 중(스크립트) — 끝나면 저절로 「✓」 가 됩니다` };
  if (it.state === "wait") return { text: n, mark: "대기", cls: "off", go, title: `${n} 분석 — 앞 항목이 끝나면 이어서 돕니다` };
  if (it.state === "failed") return { text: n, mark: "실패", cls: "warn", go, title: `${n} 분석 실패 — ${it.error || "까닭 모름"}\n「분석」 을 눌러 다시 돌립니다` };
  return { text: n, mark: "없음", cls: "warn", go, title: `${n} 분석 결과가 없습니다 — 「분석」 을 누르면 스크립트로 뽑습니다(무료 · 문서는 안 바뀜)` };
}

function dsTpl(it) { // 템플릿 — 헤딩 그래프(2단계)가 세운 것(헤딩과 같은 차례 — 도는 동안은 헤딩 표시가 돈다)
  const go = "Table", n = it.name;
  if (it.state === "done") return it.count ? { text: n, mark: "✓", cls: "ok", go, title: `템플릿 ${it.count} — ${it.text}` }
    : { text: n, mark: "없음", cls: "off", go, title: "헤딩 그래프에 줄이 있는 템플릿이 없습니다" };
  return { text: n, mark: it.state === "running" || it.state === "wait" ? "대기" : "없음", cls: "off", go, title: "템플릿 — 헤딩 그래프(2단계)가 세웁니다" };
}

function dsFmt(it) { // 서식 — 맞춘 레벨(갈래가 하나뿐인 레벨) / 줄이 있는 레벨
  const go = "Table", n = it.name, plan = `\n서식 정리 계획(LLM): ${it.llm.text}`;
  if (it.state !== "done") return { text: n, mark: it.state === "running" || it.state === "wait" ? "대기" : "없음", cls: "off", go, title: "서식 — 헤딩 그래프의 템플릿 레벨마다 쓰인 서식의 가짓수를 셉니다" };
  if (!it.levels) return { text: n, mark: "없음", cls: "off", go, title: "서식 — 템플릿 레벨이 없습니다" };
  const all = it.aligned === it.levels;
  return { text: n, mark: all ? "✓" : `${it.aligned}/${it.levels}`, cls: all ? "ok" : "", go,
    title: `서식 — ${it.text} · ${it.apply.text}${all ? "" : "\n「맞춘 레벨」 = 서식이 한 가지뿐인 레벨 — 「그대로」 로 둔 서식도 다른 줄로 셉니다"}${plan}` };
}

const DS_FOUR = [["heads", "헤딩"], ["templates", "템플릿"], ["formats", "서식"], ["tables", "표"]];
const dsChain = (v) => !!(v && v.job && v.job.chain && v.job.status === "running");
function dsLlmChip(by, view, since) { // LLM — 넷 가운데 LLM 칸이 끝난 수(헤딩 · 템플릿은 한 실행)
  const base = { opt: true, go: "Table" }, rows = DS_FOUR.filter(([k]) => by[k]);
  const lines = rows.map(([k, n]) => `${n} — ${by[k].llm.text}`).join("\n");
  if (dsChain(view)) {
    const run = ((view.chain || {}).steps || []).filter((x) => x.status === "running"); // 표 · 서식은 같이 돈다 — 둘 다 적는다
    return { ...base, text: "LLM 검증·보완", mark: run.map((x) => DS_STEP[x.key] || "").filter(Boolean).join(" · "), spin: true, since, cls: "run", title: `LLM 검증·보완 중(유료 호출) — 몇 분 걸릴 수 있습니다\n${lines}` };
  }
  if (rows.some(([k]) => by[k].llm.state === "running")) return { ...base, text: "LLM 판정 중", spin: true, since, cls: "run", title: `LLM 판정 중(유료 호출)\n${lines}` };
  const done = rows.filter(([k]) => by[k].llm.state === "done").length, bad = rows.some(([k]) => by[k].llm.state === "failed");
  const how = `\n누르면 진행표 — 「LLM 검증·보완」 단추 하나로 ${DS_ORDER}을 돌립니다(유료)`;
  if (bad) return { ...base, text: "LLM", mark: "실패", cls: "warn", title: lines + how };
  return { ...base, text: "LLM", mark: !done ? "안 함" : done === rows.length ? "✓" : `${done}/${rows.length}`, cls: done === rows.length ? "ok" : done ? "" : "off", title: lines + how };
}
const DS_STEP = { heads: "헤딩", tables: "표", formats: "서식" };
const DS_ORDER = "헤딩 · 템플릿과 표 판정을 같이, 그 뒤 서식(계획만 — 템플릿끼리 같이)"; // 차례(app/analysis_llm.py — 표 판정 호출은 1단계에만 기대어 헤딩 판정과 같이 돌고, 서식 계획은 헤딩 그래프가 끝난 뒤: 2026-11-17)

function dsDivision(d, main) { // 구분 기준 LLM 검토(옵션)
  const base = { go: "DivReview" }, how = "저절로 돌지 않습니다 — 「작업 개요」 의 검토 결과 열에서 「LLM 검토 실행」 으로 돌립니다(유료)";
  if (d.state === "running" || (main && dsReviewing())) return { ...base, text: "구분 기준 검토 중", spin: true, cls: "run", title: "구분 기준 LLM 검토 중 — 수십 초 걸립니다" };
  if (d.state === "done") return d.found ? { ...base, text: "구분 기준", mark: `후보 ${d.found}`, cls: "found", title: `${d.text}\n후보는 사람이 「자리로 추가」 해야 자리가 됩니다` }
    : d.partial ? { ...base, text: "구분 기준", mark: "일부만", cls: "warn", title: `${d.text}\n두 검토 가운데 답을 못 받은 것이 있습니다 — 다 본 것이 아닙니다(검토 결과 열에서 「다시 검토」)` } // 한쪽만 답함 — 「✓」 로 보이지 않게
    : { ...base, text: "구분 기준", mark: "✓", cls: "ok", title: d.text };
  return { ...base, text: "구분 기준", mark: "안 함", cls: "off", title: `${d.text}\n${how}` };
}

function dsModel(which, view) { // → [{opt, chips[{text, mark, cls, title, go, spin, since, opt}]}] | null(표시 없음)
  if (!view) return null;
  if (!view.items.length) return [{ chips: [{ text: "헤딩 · 표 분석 없음(hwpx 만)", cls: "off", title: `헤딩 · 표 분석은 hwpx 문서에서만 됩니다 — 이 문서는 ${view.format}` }] }];
  const by = Object.fromEntries(view.items.map((i) => [i.key, i])), since = view.job && view.job.status === "running" ? view.job.started : null, out = [];
  if (by.heads) out.push({ chips: [dsBase(by.heads, since)] });
  const graph = by.heads && by.heads.state === "done"; // 템플릿 · 서식은 헤딩 그래프에 기댄 셈 — 그래프가 없으면(없음 · 도는 중) 줄에 세우지 않는다(「헤딩 없음」 이 이미 말한다)
  if (graph && by.templates) out.push({ chips: [dsTpl(by.templates)] });
  if (graph && by.formats) out.push({ chips: [dsFmt(by.formats)] });
  if (by.tables) out.push({ chips: [dsBase(by.tables, since)] });
  if (by.heads && by.tables) out.push({ opt: true, chips: [dsLlmChip(by, view, since)] });
  if (by.division && dsKind(which, view) === "rnd") out.push({ opt: true, chips: [dsDivision(by.division, which === "main")] }); // 연구개발 문서에만 있는 항목
  return out;
}

const dsTo = (to) => (to === "Tables" && !toolShown("Tables") ? "Heads" : to); // 「표」 도구가 안 보이는 문서면 표 구조 결과가 있는 「헤딩 추출」 로
function dsGo(to) { // 표시 · 진행표 칸을 누름 — 그 도구로(문서 · 분석은 안 바뀜). "Table" = 진행표 펼치기/접기
  if (to === "Table") { dsTableToggle(); return; }
  dsTableClose();
  if (to === "DivReview") { showTab("Div"); if (typeof divReviewList === "function") divReviewList(); return; }
  if (to === "Tpl") { if (typeof tplRelOpen === "function") tplRelOpen(); return; }
  if (to === "Tidy") { dsTidyOpen(); return; }
  showTab(dsTo(to));
}

function dsTidyOpen() { // 서식의 LLM · 반영 칸 — 계획이 남은 첫 템플릿(없으면 정리할 첫 템플릿)의 「템플릿 서식 정리」 열
  const f = ((dsState.main || {}).items || []).find((i) => i.key === "formats"), list = (f && f.llm.list) || [];
  const pick = list.find((x) => x.state === "planned") || list.find((x) => x.state !== "applied") || list[0];
  if (typeof tplAgentOpen === "function") tplAgentOpen(pick ? pick.tpl : null);
}

// 둘째 면(같이 보기) 머리의 표시도 누를 수 있다(2026-11-19 spec_작업 ② §12 「도구는 문서마다」 — 사용자 "원본, 목적문서가 따로면 도구도,, 따로 따로" · 이름 줄 "이 행도 … 요청사항과 맞게"):
// 누르면 도구를 그 문서로 바꾸고(app.js toolDocSet — 두 면이 문서를 바꿈 · 보던 곳 그대로) 첫째 면에서와 같은 곳으로(진행표 · 구분 기준 검토)
const dsPeerGo = () => !PEEK && typeof toolDocSet === "function" && !!dsState.peerId;
function dsChipEl(c, main) {
  const go = !!c.go && (main || dsPeerGo());
  const b = el(go ? "button" : "span", `ds-chip ${c.cls || ""}${c.opt ? " ds-opt" : ""}`);
  if (go) { b.type = "button"; b.dataset.go = c.go; b.onclick = (e) => { e.stopPropagation(); if (main) dsGo(c.go); else toolDocSet(dsState.peerId, () => dsGo(c.go)); }; }
  if (c.spin) b.append(el("i", "ds-spin"));
  b.append(el("span", "ds-text", c.text));
  if (c.mark) b.append(el("span", "ds-mark", c.mark));
  if (c.since) { const s = el("span", "ds-secs", dsSecs(c.since)); s.dataset.since = c.since; b.append(s); }
  b.title = c.title + (!go ? "" : (main ? "\n" : "\n누르면 도구를 이 문서로 바꾸고(이 문서가 고치는 문서가 됩니다 — 두 문서의 자리 · 보던 곳은 그대로) ")
    + (c.go === "DivReview" ? `${main ? "누르면 " : ""}「작업 개요」 와 구분 기준 검토 결과 열이 열립니다` : `${main ? "누르면 " : ""}분석 진행표(헤딩 · 템플릿 · 서식 · 표 × 스크립트 · LLM 검증·보완 · 문서 반영)가 펼쳐집니다`));
  return b;
}

function dsTick(host) { if (host) for (const s of host.querySelectorAll(".ds-secs[data-since]")) s.textContent = dsSecs(+s.dataset.since); }

function dsDraw(which) {
  const host = dsHost(which), view = dsState[which], main = which === "main";
  if (!host) return;
  const m = dsModel(which, view), run = main && !!view && !dsBusy(view) && (view.base === "none" || view.base === "failed"); // 「분석」 — 기본 분석이 없고 도는 것도 없을 때(첫째 면만)
  const more = main && !!view && view.items.some((i) => i.key === "formats");
  const sig = m ? JSON.stringify([m, run, more]) : "";
  if (main) dsTableDraw();
  if (sig === dsState.sig[which]) { dsTick(host); return; }
  dsState.sig[which] = sig;
  host.hidden = !m;
  host.dataset.base = view ? view.base : "";
  if (!m) { host.replaceChildren(); return; }
  const kids = m.map((item, i) => {
    const box = el("span", "ds-item" + (item.opt ? " ds-opt" : ""));
    if (i) { const sep = el("span", "ds-sep", "·"); sep.setAttribute("aria-hidden", "true"); box.append(sep); }
    box.append(...item.chips.map((c) => dsChipEl(c, main)));
    return box;
  });
  if (more) { // 진행표 펼치기 — 좁아서 LLM 표시가 감춰져도 남는다
    const b = el("button", "ds-more", "▾");
    b.type = "button";
    b.id = "dsMore";
    b.setAttribute("aria-label", "분석 진행표 펼치기");
    b.setAttribute("aria-expanded", dsTableOpen() ? "true" : "false");
    b.setAttribute("aria-controls", "dsTable");
    b.title = "분석 진행표 — 헤딩 · 템플릿 · 서식 · 표가 스크립트 · LLM 검증·보완 · 문서 반영 가운데 어디까지 됐는지";
    b.onclick = (e) => { e.stopPropagation(); dsTableToggle(); };
    kids.push(b);
  }
  if (run) {
    const b = el("button", "btn sm ds-go", "분석");
    b.type = "button";
    b.title = "헤딩 · 표 분석을 지금 돌립니다 — 스크립트만(무료 · LLM 호출 없음) · 이미 결과가 있는 단계는 건너뜁니다 · 문서는 안 바뀝니다";
    b.onclick = () => { b.disabled = true; toast("헤딩 · 표 분석을 겁니다(스크립트) — 진행은 이 줄에 보입니다"); Promise.resolve(headsFirst()).finally(docStatusPing); }; // 다른 헤딩 작업이 도는 동안은 이 단추가 없다(busy) — 그래도 겹치면 서버가 거절하고 줄은 그대로 남는다
    kids.push(b);
  }
  host.replaceChildren(...kids);
}

// ---------------------------------------------------------------- 진행표(2026-11-16 사용자 답 「줄 넷 + 눌러서 표」 — spec_작업 ② §20 「넷 · 진행표 · LLM 검증·보완」)
// 이름 줄 아래로 펼치는 4×3 표(창이 아니다 — 바깥을 누르거나 Esc 면 닫힘). 칸을 누르면 그 도구로. 아래에 「LLM 검증·보완」 단추와 「돌 것」(서버 llmPlan) — 이 글을 보고 누르는 것이 확인이다.
const dsTableEl = () => $("dsTable");
const dsTableOpen = () => { const t = dsTableEl(); return !!t && !t.hidden; };
function dsTableToggle() { if (dsTableOpen()) dsTableClose(); else dsTableShow(); }
function dsTableShow() {
  if (!dsState.main || !state.id) return;
  let t = dsTableEl();
  if (!t) {
    t = el("div", "ds-table");
    t.id = "dsTable";
    t.setAttribute("role", "region");
    t.setAttribute("aria-label", "분석 진행표");
    t.onclick = (e) => e.stopPropagation();
    document.body.append(t);
    document.addEventListener("click", () => dsTableClose());
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && dsTableOpen()) dsTableClose(); });
    window.addEventListener("resize", () => dsTableClose());
  }
  t.hidden = false;
  dsState.tableSig = "";
  dsTableDraw();
  const more = $("dsMore");
  if (more) more.setAttribute("aria-expanded", "true");
}
function dsTableClose() {
  const t = dsTableEl();
  if (!t || t.hidden) return;
  t.hidden = true;
  const more = $("dsMore");
  if (more) more.setAttribute("aria-expanded", "false");
}
function dsTablePlace(t) { // 이름 줄 표시 바로 아래 — 창 안에(오른쪽 넘침은 왼쪽으로 민다)
  const host = dsHost("main"), r = host && !host.hidden ? host.getBoundingClientRect() : null, row = host && host.parentElement ? host.parentElement.getBoundingClientRect() : r;
  if (!r) return;
  const w = Math.min(640, window.innerWidth - 32);
  t.style.width = `${w}px`;
  t.style.left = `${Math.max(16, Math.min(r.left, window.innerWidth - w - 16))}px`;
  t.style.top = `${row.bottom + 4}px`; // 이름 줄 바로 아래(줄을 가리지 않는다)
}

const DS_MARK = { done: "✓", running: "◌", wait: "대기", none: "", failed: "실패", partial: "일부" };
function dsCell(text, state, go, title) { // 칸 하나 — 누르는 단추(go 가 있으면)
  const c = el(go ? "button" : "span", `ds-cell ${state || ""}`);
  if (go) { c.type = "button"; c.onclick = (e) => { e.stopPropagation(); dsGo(go); }; }
  if (state === "running") c.append(el("i", "ds-spin"));
  else if (DS_MARK[state]) c.append(el("b", "ds-cell-mark", DS_MARK[state]));
  c.append(el("span", "", text));
  c.title = title || text;
  return c;
}
function dsTplShort(it) { // 템플릿 칸 — 수 + 앞 셋(나머지는 도움말에)
  const list = it.list || [];
  if (!list.length) return "템플릿 없음";
  const head = list.slice(0, 3).map((r) => `T${r.no} ${r.chain}`.trim()).join(" · ");
  return `템플릿 ${list.length} — ${head}${list.length > 3 ? ` 외 ${list.length - 3}` : ""}`;
}
const dsLlmShort = (t) => String(t || "").replace(/^LLM 판정함 — /, "").replace(/^LLM 판정함$/, "판정함");
function dsRow(k, n, it) { // → [이름, 스크립트, LLM, 반영] 칸
  const go = k === "heads" ? "Heads" : k === "tables" ? "Tables" : "Tpl", L = it.llm;
  const sText = it.state === "done" ? (k === "heads" ? it.short : k === "templates" ? dsTplShort(it) : k === "formats" ? it.text || "레벨 없음"
    : [it.short, it.calc && it.calc.formulas ? `검산 맞음 ${it.calc.ok}/${it.calc.formulas}${it.calc.mismatch ? ` · 안 맞음 ${it.calc.mismatch}` : ""}` : ""].filter(Boolean).join(" · "))
    : { running: "분석 중", wait: "대기", failed: `실패 — ${it.error || "까닭 모름"}`, none: "없음 — 「분석」 으로" }[it.state] || it.state;
  const lText = { done: k === "heads" || k === "tables" ? dsLlmShort(L.text) : L.text, running: k === "formats" ? L.text : "판정 중", wait: "대기",
    failed: L.error || L.text, partial: L.text, none: k === "formats" ? L.text : k === "templates" ? "안 함 — 헤딩과 한 실행" : "안 함" }[L.state] || L.text;
  const rules = k === "heads" && it.rules && it.rules.asked !== false && L.state !== "failed" ? ` · 규칙 보강 ${it.rules.saved != null ? it.rules.saved : "함"}` : ""; // 답을 받은 보강만(못 받은 것은 세지 않는다)
  const lGo = k === "formats" ? "Tidy" : go, aGo = k === "formats" ? "Tidy" : null;
  const apply = k === "formats" ? dsCell(it.apply.text || "—", it.apply.state === "done" ? "done" : "", it.state === "done" ? aGo : null,
    `${it.apply.text}\n맞춘 레벨 = 서식이 한 가지뿐인 레벨 — 「템플릿 서식 정리」 에서 계획을 골라 적용하거나 「대표에 맞추기」 로 맞춥니다(문서가 바뀜 · 실행 취소 1)`)
    : dsCell("—", "na", null, "문서를 바꾸지 않는 일입니다 — 결과는 뼈대로만 씁니다");
  return [el("span", "ds-row-name", n), dsCell(sText, it.state, go, `${n} — 스크립트(올리면 저절로 · 무료)\n${it.text || sText}`),
    dsCell(lText + rules, L.state, lGo, `${n} — LLM 검증·보완(사람이 단추로 · 유료)\n${L.text}${rules}${L.error ? `\n${L.error}` : ""}`), apply];
}
const DS_STEP_MARK = { ok: "✓", skip: "건너뜀", running: "◌", wait: "대기", failed: "실패", partial: "일부", stopped: "멈춤" };
function dsWith(list, live) { // → (x) => 같이 도는가 — 차례 번호(no)가 같은 것 가운데 live 인 것이 둘 이상일 때만(한쪽이 건너뛰면 「같이」 가 아니다)
  const n = {};
  for (const x of list || []) if (x.no != null && live(x)) n[x.no] = (n[x.no] || 0) + 1;
  return (x) => x.no != null && live(x) && n[x.no] > 1;
}
function dsWithEl() {
  const b = el("span", "ds-with", "같이");
  b.title = "같은 번호의 일은 같이 돕니다 — 서로를 기다리지 않습니다(표 판정의 호출은 헤딩 판정과 같이 돌고 소속만 헤딩 그래프가 끝난 뒤 붙입니다 · 헤딩을 건너뛰면 표와 서식 계획이 같이)";
  return b;
}
function dsStepNo(no) { const s = el("span", "ds-step-no", String(no)); s.title = `차례 ${no}`; return s; }
function dsSteps(steps) { // LLM 검증·보완의 차례 — 단계마다 차례 번호 · 상태 · 한 줄(같은 번호 = 같이 돎 — 「같이」 표시)
  const ol = el("ol", "ds-steps"), together = dsWith(steps, (s) => s.status !== "skip" && s.status !== "stopped");
  for (const s of steps || []) {
    const li = el("li", `ds-step ${s.status}`);
    if (s.no != null) li.append(dsStepNo(s.no));
    li.append(s.status === "running" ? el("i", "ds-spin") : el("b", "ds-cell-mark", DS_STEP_MARK[s.status] || s.status), el("span", "ds-step-name", s.name));
    if (together(s)) li.append(dsWithEl());
    if (s.msg) li.append(el("span", "ds-step-msg", s.msg));
    ol.append(li);
  }
  return ol;
}
function dsTableDraw() {
  const t = dsTableEl(), v = dsState.main;
  if (!t || t.hidden) return;
  if (!v || !v.items.some((i) => i.key === "formats")) { dsTableClose(); return; }
  dsTablePlace(t);
  const sig = JSON.stringify([v.items.filter((i) => i.key !== "division"), v.chain, v.llmPlan, v.busy, v.job && v.job.status]);
  if (sig === dsState.tableSig) return;
  dsState.tableSig = sig;
  const by = Object.fromEntries(v.items.map((i) => [i.key, i]));
  const head = el("div", "ds-table-head");
  const x = el("button", "icon ds-table-x", "✕");
  x.type = "button"; x.setAttribute("aria-label", "진행표 닫기"); x.onclick = (e) => { e.stopPropagation(); dsTableClose(); };
  head.append(el("strong", "", "분석 진행"), el("span", "ds-table-note", "어느 문서 · 어느 워크플로우든 같은 네 가지 일 — 스크립트는 올리면 저절로, LLM 은 단추로"), x);
  const grid = el("div", "ds-grid");
  grid.append(el("span", "ds-col"), el("span", "ds-col", "스크립트"), el("span", "ds-col", "LLM 검증·보완"), el("span", "ds-col", "문서 반영"));
  for (const [k, n] of DS_FOUR) if (by[k]) grid.append(...dsRow(k, n, by[k]));
  const foot = el("div", "ds-table-foot");
  const ch = v.chain, running = dsChain(v);
  if (ch && ch.steps && ch.steps.length) {
    const cn = ch.name || "LLM 검증·보완"; // 이어 돌리기의 이름(서버 analysis.CHAIN_NAMES — 「헤딩 그래프(LLM)」 로 돌린 것은 「헤딩 LLM 판정 · 서식 계획」)
    foot.append(el("div", "ds-foot-title", running ? `${cn} — 도는 중${ch.stopping ? " · 지금 도는 일이 끝나면 멈춤" : ""}` : `지난 ${cn} — ${ch.status === "failed" ? "멈춤(실패)" : "끝남"}`), dsSteps(ch.steps));
    if (!running && ch.status === "failed" && v.job && v.job.error && !ch.steps.some((x) => x.status === "failed" && x.msg)) foot.append(el("div", "ds-foot-err", v.job.error)); // 단계 줄에 까닭이 없을 때만
  }
  if (running) {
    if (!ch.stopping) {
      const b = el("button", "btn sm", "멈추기");
      b.type = "button";
      b.title = "지금 하는 일이 끝나면 멈춥니다 — 이미 받은 결과 · 계획은 남습니다";
      b.onclick = (e) => { e.stopPropagation(); b.disabled = true; dsLlmStop(); };
      foot.append(b);
    }
  } else {
    const plan = v.llmPlan || [], todo = plan.filter((p) => p.run);
    if (todo.length) {
      const ol = el("ol", "ds-plan"), together = dsWith(plan, (p) => p.run);
      for (const p of plan) {
        const li = el("li", `${p.run ? "run" : "skip"}${p.no != null ? " numbered" : ""}`);
        if (p.no != null) li.append(dsStepNo(p.no));
        li.append(el("span", "ds-step-name", p.name));
        if (together(p)) li.append(dsWithEl());
        li.append(el("span", "ds-step-msg", p.why));
        ol.append(li);
      }
      const go = el("button", "btn sm primary ds-llm-go", "LLM 검증·보완");
      go.type = "button";
      go.disabled = !!v.busy;
      go.title = v.busy ? "다른 헤딩 작업이 도는 중입니다 — 끝난 뒤 누르세요" : `아래 「돌 것」 을 돌립니다 — ${DS_ORDER} · 유료 LLM 호출 · 몇 분 · 문서는 바뀌지 않습니다`;
      go.onclick = (e) => { e.stopPropagation(); go.disabled = true; dsLlmRun(); };
      foot.append(el("div", "ds-foot-title", "돌 것 — 유료 LLM · 몇 분 걸립니다 · 문서는 바뀌지 않습니다(서식 정리는 계획만 — 반영은 「템플릿 서식 정리」 에서 고른 것만)"), ol, go);
    } else {
      const left = by.formats && by.formats.apply.state !== "done" && by.formats.levels;
      foot.append(el("div", "ds-foot-title", `LLM 검증·보완을 모두 마쳤습니다${left ? ` — 남은 일: 서식 반영(${by.formats.apply.text})` : ""}`));
      if (left) { // 받아 둔 계획이 있으면 한 번에 반영하는 자리(헤딩 추출 탭 진행 줄의 「조정」 — tpl_plan_bar.js)로, 없으면 전처럼 「템플릿 서식 정리」 열
        const all = by.formats.llm.planned > 0 && typeof tplPlanGo === "function";
        const b = el("button", "btn sm", all ? "헤딩 추출 「조정」 으로 — 모두 반영" : "템플릿 서식 정리 열기");
        b.type = "button"; b.onclick = (e) => { e.stopPropagation(); if (all) { dsTableClose(); tplPlanGo(); } else dsGo("Tidy"); }; foot.append(b);
      }
    }
  }
  t.replaceChildren(head, grid, foot);
}

async function dsLlmRun() { // 「LLM 검증·보완」 — 헤딩 작업 자리 하나에서(헤딩 탭의 진행 · 결과도 같이 따라온다: headsPoll). → 시작했나(true) — 에이전트 실행 카드가 「실행함」/「멈춤」 을 가른다(doc_agent_next.js)
  if (!state.id) return false;
  const id = state.id, epoch = state.epoch;
  let ok = false;
  await flushAll(); // 아직 반영 안 된 글부터 — 분석은 서버 문서를 읽는다
  if (epoch !== state.epoch) return false;
  const skill = typeof tpaSkillKey === "function" ? tpaSkillKey() : "tidy"; // 서식 정리는 열에서 고른 스킬(없으면 기본 — tpl_agent.js)
  try {
    const job = await api(`/api/docs/${id}/analysis/llm`, { method: "POST", headers: H_JSON, body: JSON.stringify({ skill }) });
    if (epoch !== state.epoch) return;
    heads.expect = job.started;
    headsRender({ ...(heads.view || { rev: state.serverRev, runs: [], stage1: null, stage2: null, stage3: null }), job });
    headsPoll();
    toast("LLM 검증·보완을 시작했습니다 — 진행은 이름 줄과 진행표에 보입니다");
    ok = true;
  } catch (e) {
    if (epoch === state.epoch) toast(e.status === 409 ? "헤딩 작업이 이미 돌고 있습니다 — 끝난 뒤 다시 누르세요" : e.status === 404 && /not found/i.test(e.message || "") ? "서버가 옛 판이라 LLM 검증·보완을 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요" : `LLM 검증·보완을 시작하지 못했습니다: ${e.message}`, true);
  }
  docStatusPing();
  return ok;
}

async function dsLlmStop() {
  if (!state.id) return;
  try { await api(`/api/docs/${state.id}/analysis/llm`, { method: "DELETE" }); toast("지금 하는 일이 끝나면 멈춥니다"); }
  catch (e) { toast(`멈추지 못했습니다: ${e.message}`, true); }
  docStatusPing();
}

function dsRunning() { // 작업 진행 에이전트의 진행 카드(doc_agent_work.js agwRunning) — 도는 LLM 검증·보완 | null
  const v = dsState.main;
  if (!dsChain(v) || !state.id || dsState.mainId !== state.id) return null;
  const run = ((v.chain || {}).steps || []).filter((x) => x.status === "running"), short = (x) => DS_STEP[x.key] || x.name; // 표 · 서식은 같이 돈다 — 둘 다 적는다
  const note = !run.length ? "진행 중" : run.length === 1 ? `${run[0].name}${run[0].msg ? ` — ${run[0].msg}` : ""}`
    : `${run.map(short).join(" · ")} 같이 — ${run.map((x) => `${short(x)}: ${x.msg || "도는 중"}`).join(" / ")}`;
  return { label: "LLM 검증·보완 — 헤딩 · 표 판정 같이 → 서식(계획만)", note, t0: v.job.started ? v.job.started * 1000 : 0,
    stopping: !!(v.chain && v.chain.stopping), stop: () => dsLlmStop() };
}

async function dsFetch(which, seq) {
  const id = dsId(which), epoch = state.epoch;
  let v = null;
  if (id) { try { v = await api(`/api/docs/${id}/analysis`); } catch { v = null; } } // 못 읽으면 표시 없음(닫힌 문서 · 옛 서버)
  if (seq !== dsState.seq || epoch !== state.epoch || id !== dsId(which)) return; // 그 사이 문서가 바뀌었거나 더 새 읽기가 떠 있다
  dsState[which] = v;
  dsDraw(which);
  if (which === "main" && typeof agentNextSync === "function") agentNextSync(); // 에이전트 빈 화면의 「지금 할 수 있는 일」 · 실행 카드(doc_agent_next.js)
  if (which === "main" && typeof tplPlanBarSync === "function") tplPlanBarSync(); // 헤딩 추출 탭 진행 줄의 「조정」(tpl_plan_bar.js) — 같은 자료
}

async function dsRefresh() {
  clearTimeout(dsState.poll); dsState.poll = 0;
  const seq = ++dsState.seq;
  await Promise.all([dsFetch("main", seq), dsFetch("peer", seq)]);
  if (seq !== dsState.seq) return;
  const on = dsBusy(dsState.main) || dsBusy(dsState.peer) || dsReviewing();
  if (on) dsState.poll = setTimeout(dsRefresh, DS_POLL);
  if (on && !dsState.tick) dsState.tick = setInterval(() => { dsTick(dsHost("main")); dsTick(dsHost("peer")); }, 1000);
  if (!on && dsState.tick) { clearInterval(dsState.tick); dsState.tick = 0; }
}

function docStatusPing() { // 상태가 바뀌었을 수 있다 — 곧 다시 읽는다(잇단 호출은 한 번으로)
  if (PEEK) return;
  clearTimeout(dsState.ping);
  dsState.ping = setTimeout(dsRefresh, 200);
}

function docStatusLoad() { // 문서를 열 때 · 닫을 때 · TASK 를 고친 뒤(app.js taskDraw)
  if (PEEK) return;
  const id = state.id || "";
  if (id !== dsState.mainId) { dsState.mainId = id; dsState.main = null; dsTableClose(); dsDraw("main"); } // 다른 문서 — 앞 문서의 표시 · 진행표를 남기지 않는다
  else if (dsState.main) dsDraw("main"); // 같은 문서 — 작업 종류가 바뀌었으면 구분 기준 항목의 보임이 달라진다(같으면 그대로 — dsDraw 가 견준다)
  docStatusPing();
}

function docStatusPeer(id) { // 둘째 면에 떠 있는 문서(app.js peerSync — "" = 없음)
  if (PEEK || (id || "") === dsState.peerId) return;
  dsState.peerId = id || "";
  dsState.peer = null;
  dsDraw("peer");
  docStatusPing();
}
// 도구를 쓸 문서를 바꿀 때(app.js toolDocSet — 두 면이 문서를 바꿈): 바꾸기 전의 두 표시를 적어 두었다가(docStatusSnap) 바꾼 뒤 면을 바꿔 바로 그린다(docStatusCarry — 다시 읽는 동안 비지 않게 ·
// 둘째 면 표시를 눌러 바꾼 경우 진행표를 곧바로 펼 수 있게). 다시 읽기(docStatusPing)는 그대로 돈다
function docStatusSnap() { return { main: dsState.main, peer: dsState.peer, mainId: dsState.mainId, peerId: dsState.peerId }; }
function docStatusCarry(s) {
  if (PEEK || !s) return;
  if (dsState.mainId === s.peerId && !dsState.main && s.peer) { dsState.main = s.peer; dsDraw("main"); }
  if (dsState.peerId === s.mainId && !dsState.peer && s.main) { dsState.peer = s.main; dsDraw("peer"); }
}
