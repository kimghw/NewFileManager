"use strict";
/* 분석 상태 — 문서 이름 줄의 표시(index.html #docStatus · 둘째 면 머리 #peerStatus — spec_작업 ② §20, 2026-11-15 사용자 "이게 task 마다 작업을 표준화 했으면 좋겠는데. 그래서 올리면
   어디까지 작업이 되었는지 표시하는거지. 기본적으로 헤딩,표 분석은 해야하고 … 헤딩, 표 분석도 스크립트기반, 그리고 LLM 분리, 그리고 구분 기준은 옵션").
   어느 TASK · 어느 패널 탭에서나 같은 자리에 같은 꼴: 「헤딩 ✓ · 표 ✓ · LLM 안 함 · 구분 기준 안 함」 — 기본 분석(헤딩 · 표 — 스크립트, 올리면 저절로) · LLM 판정(사람이 단추로) ·
   구분 기준 LLM 검토(옵션 — 연구개발 문서만). 값은 서버가 센다(GET /api/docs/{id}/analysis — app/analysis.py) — 여기는 그리기와 다시 읽기뿐이다.
   - 항목은 누르는 표시다 — 그 도구로 간다(헤딩 · LLM → 「헤딩 추출」 · 표 → 「표」 · 구분 기준 → 「작업 내용」 + 2열 검토 결과). 여기서 바로 도는 것은 「분석」 단추 하나(기본 분석이 없을 때 —
     첫 분석과 같은 끝점 · 스크립트만). 유료 LLM 은 그 도구의 단추로만 돈다.
   - 다시 읽는 때: docStatusLoad(app.js taskDraw — 문서를 열 때 · 닫을 때 · TASK 를 고친 뒤) · docStatusPing(headsRender · 구분 기준 검토의 시작과 끝) · docStatusPeer(peerSync — 둘째 면의 문서가 바뀔 때),
     그리고 도는 것이 있는 동안 2초마다. 같은 내용이면 다시 그리지 않는다(포커스 유지 — 지난 시간 글만 1초마다).
   - 문서를 고친 뒤에도 「✓」 다(뼈대 유지 — 다시 돌리라고 하지 않는다). 해당 없는 항목은 안 보인다(일반 문서의 구분 기준 · docx 는 「헤딩 · 표 분석 없음(hwpx 만)」 한마디).
   app.js(state · api · el · $ · showTab · toolShown · headsFirst · divReviewList · dv · worksList · PEEK) 다음에 읽힌다. */
const DS_POLL = 2000; // 도는 것이 있는 동안 다시 읽는 간격
const dsState = { main: null, peer: null, mainId: "", peerId: "", sig: { main: "", peer: "" }, poll: 0, ping: 0, tick: 0, seq: 0 };
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
  const go = it.key === "heads" ? "Heads" : "Tables", n = it.name;
  if (it.state === "done") return { text: n, mark: "✓", cls: "ok", go, title: it.text + (it.moved ? "\n그 뒤 문서를 고쳤습니다 — 결과는 뼈대로 그대로 씁니다(새 레터 · 서식 · 표가 생기면 따로 알립니다)" : "") };
  if (it.state === "running") return { text: `${n} 분석 중`, spin: true, since, cls: "run", go, title: `${n} 분석 중(스크립트) — 끝나면 저절로 「✓」 가 됩니다` };
  if (it.state === "wait") return { text: n, mark: "대기", cls: "off", go, title: `${n} 분석 — 앞 항목이 끝나면 이어서 돕니다` };
  if (it.state === "failed") return { text: n, mark: "실패", cls: "warn", go, title: `${n} 분석 실패 — ${it.error || "까닭 모름"}\n「분석」 을 눌러 다시 돌립니다` };
  return { text: n, mark: "없음", cls: "warn", go, title: `${n} 분석 결과가 없습니다 — 「분석」 을 누르면 스크립트로 뽑습니다(무료 · 문서는 안 바뀜)` };
}

function dsLlm(it, since) { // 헤딩 · 표 — LLM 판정(분리 · 사람이 단추로)
  const l = it.llm, base = { opt: true, go: "Heads" };
  if (l.state === "done") return { ...base, text: "LLM", mark: "✓", cls: "ok", title: `${it.name} — ${l.text}` };
  if (l.state === "running") return { ...base, text: "LLM 판정 중", spin: true, since, cls: "run", title: `${it.name} — LLM 판정 중(유료 호출) — 몇 분 걸릴 수 있습니다` };
  if (l.state === "failed") return { ...base, text: "LLM", mark: "실패", cls: "warn", title: `${it.name} — ${l.text}${l.error ? ` — ${l.error}` : ""}` };
  return { ...base, text: "LLM", mark: "안 함", cls: "off", title: `${it.name} — ${l.text}` };
}

function dsDivision(d, main) { // 구분 기준 LLM 검토(옵션)
  const base = { go: "DivReview" }, how = "저절로 돌지 않습니다 — 「작업 내용」 의 검토 결과 열에서 「LLM 검토 실행」 으로 돌립니다(유료)";
  if (d.state === "running" || (main && dsReviewing())) return { ...base, text: "구분 기준 검토 중", spin: true, cls: "run", title: "구분 기준 LLM 검토 중 — 수십 초 걸립니다" };
  if (d.state === "done") return d.found ? { ...base, text: "구분 기준", mark: `후보 ${d.found}`, cls: "found", title: `${d.text}\n후보는 사람이 「자리로 추가」 해야 자리가 됩니다` }
    : d.partial ? { ...base, text: "구분 기준", mark: "일부만", cls: "warn", title: `${d.text}\n두 검토 가운데 답을 못 받은 것이 있습니다 — 다 본 것이 아닙니다(검토 결과 열에서 「다시 검토」)` } // 한쪽만 답함 — 「✓」 로 보이지 않게
    : { ...base, text: "구분 기준", mark: "✓", cls: "ok", title: d.text };
  return { ...base, text: "구분 기준", mark: "안 함", cls: "off", title: `${d.text}\n${how}` };
}

function dsModel(which, view) { // → [{opt, chips[{text, mark, cls, title, go, spin, since, opt}]}] | null(표시 없음)
  if (!view) return null;
  if (!view.items.length) return [{ chips: [{ text: "헤딩 · 표 분석 없음(hwpx 만)", cls: "off", title: `헤딩 · 표 분석은 hwpx 문서에서만 됩니다 — 이 문서는 ${view.format}` }] }];
  const by = Object.fromEntries(view.items.map((i) => [i.key, i])), since = view.job && view.job.status === "running" ? view.job.started : null;
  const llmUsed = ["heads", "tables"].some((k) => by[k] && by[k].llm.state !== "none"), out = [];
  for (const k of ["heads", "tables"]) if (by[k]) out.push({ chips: [dsBase(by[k], since), ...(llmUsed ? [dsLlm(by[k], since)] : [])] }); // LLM 을 하나라도 돌렸으면 헤딩 · 표마다 따로
  if (!llmUsed) out.push({ opt: true, chips: [{ text: "LLM", mark: "안 함", cls: "off", go: "Heads",
    title: "헤딩 · 표의 LLM 판정 — 안 함(지금은 스크립트 결과)\n저절로 돌지 않습니다 — 「헤딩 추출」 탭의 「헤딩 그래프(LLM)」 · 「표 구조(LLM)」 단추로 돌립니다(유료)" }] });
  if (by.division && dsKind(which, view) === "rnd") out.push({ opt: true, chips: [dsDivision(by.division, which === "main")] }); // 연구개발 문서에만 있는 항목
  return out;
}

const dsTo = (to) => (to === "Tables" && !toolShown("Tables") ? "Heads" : to); // 「표」 도구가 안 보이는 문서면 표 구조 결과가 있는 「헤딩 추출」 로
function dsGo(to) { // 표시를 누름 — 그 도구로(문서 · 분석은 안 바뀜)
  if (to === "DivReview") { showTab("Div"); if (typeof divReviewList === "function") divReviewList(); return; }
  showTab(dsTo(to));
}

function dsChipEl(c, main) {
  const b = el(main && c.go ? "button" : "span", `ds-chip ${c.cls || ""}${c.opt ? " ds-opt" : ""}`);
  if (b.tagName === "BUTTON") { b.type = "button"; b.dataset.go = c.go; b.onclick = () => dsGo(c.go); }
  if (c.spin) b.append(el("i", "ds-spin"));
  b.append(el("span", "ds-text", c.text));
  if (c.mark) b.append(el("span", "ds-mark", c.mark));
  if (c.since) { const s = el("span", "ds-secs", dsSecs(c.since)); s.dataset.since = c.since; b.append(s); }
  b.title = c.title + (b.tagName !== "BUTTON" ? "" : c.go === "DivReview" ? "\n누르면 「작업 내용」 과 구분 기준 검토 결과 열이 열립니다" : `\n누르면 「${dsTo(c.go) === "Tables" ? "표" : "헤딩 추출"}」 탭으로 갑니다`);
  return b;
}

function dsTick(host) { if (host) for (const s of host.querySelectorAll(".ds-secs[data-since]")) s.textContent = dsSecs(+s.dataset.since); }

function dsDraw(which) {
  const host = dsHost(which), view = dsState[which], main = which === "main";
  if (!host) return;
  const m = dsModel(which, view), run = main && !!view && !dsBusy(view) && (view.base === "none" || view.base === "failed"); // 「분석」 — 기본 분석이 없고 도는 것도 없을 때(첫째 면만)
  const sig = m ? JSON.stringify([m, run]) : "";
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
  if (run) {
    const b = el("button", "btn sm ds-go", "분석");
    b.type = "button";
    b.title = "헤딩 · 표 분석을 지금 돌립니다 — 스크립트만(무료 · LLM 호출 없음) · 이미 결과가 있는 단계는 건너뜁니다 · 문서는 안 바뀝니다";
    b.onclick = () => { b.disabled = true; toast("헤딩 · 표 분석을 겁니다(스크립트) — 진행은 이 줄에 보입니다"); Promise.resolve(headsFirst()).finally(docStatusPing); }; // 다른 헤딩 작업이 도는 동안은 이 단추가 없다(busy) — 그래도 겹치면 서버가 거절하고 줄은 그대로 남는다
    kids.push(b);
  }
  host.replaceChildren(...kids);
}

async function dsFetch(which, seq) {
  const id = dsId(which), epoch = state.epoch;
  let v = null;
  if (id) { try { v = await api(`/api/docs/${id}/analysis`); } catch { v = null; } } // 못 읽으면 표시 없음(닫힌 문서 · 옛 서버)
  if (seq !== dsState.seq || epoch !== state.epoch || id !== dsId(which)) return; // 그 사이 문서가 바뀌었거나 더 새 읽기가 떠 있다
  dsState[which] = v;
  dsDraw(which);
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
  if (id !== dsState.mainId) { dsState.mainId = id; dsState.main = null; dsDraw("main"); } // 다른 문서 — 앞 문서의 표시를 남기지 않는다
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
