"use strict";
// 구분 라벨 지정(spec_헤딩_추출 ② §13) — 「템플릿 관계」 열(2열 kind "templates")에서 괄호 줄(「[…]」)을 구분 라벨(구분 기준 값)·괄호 소제목으로 지정한다.
// 괄호 줄이 뿌리인 템플릿을 펼치면 L1 줄 아래에 그 템플릿의 괄호 글 목록(글 · 수 · 문서로)이 나오고, 구분 라벨은 「소제목으로 변경」,
// 괄호 소제목은 「구분 라벨로 지정…」(단계·차년도·기관·더한 기준·직접 입력), 사용자 지정에는 「지정」 표지와 「자동 판정으로」.
// 지정 단위 = 괄호 글 꼴(숫자를 N 으로 — 「[N차년도 목표]」 하나가 1~6차년도) · 문서 전체의 같은 꼴이 함께 바뀐다. 서버가 저장하고 2단계 결과를 곧바로 다시 셈한다(LLM 호출 없음).
// app.js 가 주는 것: state·heads·el·api·toast·hBtn·nf·short·headsParaLink·headsPoll·H_JSON. app.js 가 부르는 것(typeof 검사 뒤):
// divLabelsList(headsTplView 의 L1 줄) · divLabelsPending(headsTplView — 방금 바꾼 꼴이 든 템플릿을 다시 펼침). 서버 짝은 app/heading_labels_api.py.
// index.html 이 app.js 다음에 읽는다.
const DIVL = { key: null, data: null, loading: null, error: "", pending: null, busy: false };
const DIVL_NEW = "@new"; // 고르기 목록의 「직접 입력…」 값
const divlShape = (letter) => String(letter || "").trim().replace(/\p{Nd}+/gu, "N"); // 서버 heading_graph.label_shape 와 같은 꼴
const divlUrl = () => `/api/docs/${encodeURIComponent(state.id)}/headings/div_labels`;
const divlKey = (g) => { const m = (g && g.meta) || {}; return `${state.id}|${m.run}|${m.at}`; };

function divlData(g) { // 지금 그래프의 구분 기준·지정·꼴 목록 — 아직 없으면 읽기 시작하고 null(읽히면 열린 목록을 다시 채움)
  const key = divlKey(g);
  if (DIVL.key === key && DIVL.data) return DIVL.data;
  if (DIVL.loading !== key) {
    DIVL.loading = key;
    DIVL.error = "";
    const epoch = state.epoch;
    api(divlUrl()).then((d) => {
      if (epoch !== state.epoch || DIVL.loading !== key) return;
      Object.assign(DIVL, { key, data: d, loading: null });
      divlRefill();
    }).catch((e) => {
      if (DIVL.loading !== key) return;
      Object.assign(DIVL, { loading: null, error: e.message || "읽지 못함" });
      divlRefill();
    });
  }
  return null;
}

function divLabelsList(g, t) { // 템플릿 t 의 L1 이 괄호 줄이면 그 괄호 글 목록(.divl) — 아니면 null
  const rows = new Map();
  for (const x of g.nodes || []) {
    if (x.kind !== "label" || x.level !== 1 || x.tplNo !== (t.no ?? t.id) || !isRooted(x.role)) continue;
    const shape = divlShape(x.letter);
    const r = rows.get(shape) || { shape, text: String(x.letter || "").trim(), para: x.para, n: 0, role: x.role, basis: x.basis || (x.role === "label" ? String(x.key || "").slice(1, -1) : "") };
    r.n += 1;
    rows.set(shape, r);
  }
  if (!rows.size) return null;
  const box = el("div", "divl");
  box._g = g;
  box._rows = [...rows.values()];
  divlFill(box);
  return box;
}

function divlRefill() { document.querySelectorAll(".divl").forEach((b) => { if (b._g === heads.graph) divlFill(b); }); }

function divlFill(box) {
  const g = box._g, rows = box._rows;
  const d = divlData(g);
  const items = new Map(((d && d.items) || []).map((it) => [it.shape, it]));
  box.replaceChildren();
  const head = el("p", "hnote divl-head", `괄호 글 ${nf(rows.length)}가지`);
  if (!d) head.append(DIVL.error ? ` · 지정 상태를 읽지 못했습니다: ${DIVL.error}` : " · 지정 상태를 읽는 중…");
  else if (d.stale) head.append(" · 문서가 추출 뒤 바뀜 — 지정은 저장되고 2단계를 다시 돌릴 때 반영됩니다");
  else if (d.bracketRule == null) head.append(" · 옛 규칙으로 만든 결과(괄호 줄이 모두 구분 라벨) — 2단계를 다시 돌리거나(스크립트는 몇 초) 아래에서 하나를 지정하면 구분 라벨·괄호 소제목으로 갈립니다");
  box.append(head);
  for (const r of rows) {
    const it = items.get(r.shape), hint = it && it.hint;
    const line = el("div", "divl-row");
    // 여러 줄을 덮는 꼴은 꼴 그대로(「[N차년도 목표]」 — 숫자 자리 N) 적는다: 지정이 미치는 범위가 그 꼴이다
    line.append(headsParaLink(r.para, r.n > 1 ? r.shape : r.text, 40,
      (r.role === "label" ? `구분 라벨 · 기준 ${r.basis}` : "괄호 소제목(구분 기준 값이 아닌 괄호 글)") + (r.n > 1 ? ` · 첫 줄 「${r.text}」` : "")));
    const all = it && it.count > r.n ? it.count : r.n;
    line.append(el("span", "muted", ` ×${nf(r.n)}${all > r.n ? ` · 문서 전체 같은 꼴 ${nf(all)}곳` : ""}`));
    if (r.role === "label") line.append(typeof dvTag === "function" ? dvTag(el("span", "hb div", `기준 ${r.basis}`), r.basis) : el("span", "hb div", `기준 ${r.basis}`)); // 배지 색 = 그 구분의 「구분 기준 자리」 색(app.js dvKeyOf)
    if (hint) {
      const b = el("span", "hb divl-by", "지정");
      b.title = `사용자가 ${hint.role === "label" ? `구분 라벨(기준 ${hint.basis})` : "괄호 소제목"}(으)로 지정함 — 「자동 판정으로」 를 누르면 지정을 지웁니다`;
      line.append(b);
    }
    if (d) {
      const off = DIVL.busy;
      const scope = all > 1 ? `문서 전체의 같은 꼴 ${nf(all)}곳이 함께 바뀝니다` : "이 줄 하나가 바뀝니다";
      if (r.role === "label") {
        line.append(hBtn("소제목으로 변경", () => divlPut(r, "subtitle"), { disabled: off, title: `구분 기준 값이 아닌 괄호 소제목으로 봅니다 — ${scope}(문단은 그대로)` }));
      } else {
        line.append(divlPick(r, d.bases || [], off, scope));
      }
      if (hint) line.append(hBtn("자동 판정으로", () => divlPut(r, "auto"), { disabled: off, title: `지정을 지우고 글의 꼴로 다시 판정합니다 — ${scope}` }));
    }
    box.append(line);
  }
}

function divlPick(r, bases, off, scope) { // 「구분 라벨로 지정…」 — 구분 기준 고르기(+ 직접 입력)
  const wrap = el("span", "divl-pick");
  const sel = el("select", "divl-sel");
  sel.disabled = off;
  sel.title = `이 괄호 글을 구분 라벨(구분 기준의 값)로 봅니다 — ${scope}(문단은 그대로)`;
  sel.setAttribute("aria-label", `${r.text} 을(를) 구분 라벨로 지정`);
  sel.append(new Option("구분 라벨로 지정…", ""));
  for (const b of bases) sel.append(new Option(`기준: ${b}`, b));
  sel.append(new Option("기준 직접 입력…", DIVL_NEW));
  const inp = el("input", "divl-inp");
  inp.type = "text";
  inp.maxLength = 12;
  inp.placeholder = "구분 기준 이름(예: 세부과제)";
  inp.hidden = true;
  const ok = hBtn("지정", () => { const v = inp.value.trim(); if (v) divlPut(r, "label", v); else inp.focus(); });
  ok.hidden = true;
  sel.onchange = () => {
    const custom = sel.value === DIVL_NEW;
    inp.hidden = ok.hidden = !custom;
    if (custom) inp.focus();
    else if (sel.value) divlPut(r, "label", sel.value);
  };
  inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); ok.click(); } else if (e.key === "Escape") { sel.value = ""; inp.hidden = ok.hidden = true; } };
  wrap.append(sel, inp, ok);
  return wrap;
}

async function divlPut(r, role, basis = "") {
  if (DIVL.busy || !state.id) return;
  DIVL.busy = true;
  divlRefill();
  const epoch = state.epoch;
  try {
    const d = await api(divlUrl(), { method: "PUT", headers: H_JSON, body: JSON.stringify({ shape: r.shape, role, basis, text: r.text }) });
    if (epoch !== state.epoch) return;
    const it = (d.items || []).find((x) => x.shape === r.shape);
    const what = role === "label" ? `구분 라벨(기준 ${(it && it.basis) || basis})` : role === "subtitle" ? "괄호 소제목" : "자동 판정";
    if (d.applied) {
      toast(`「${short(r.text, 24)}」 → ${what}${it && it.count > 1 ? ` · 같은 꼴 ${nf(it.count)}곳` : ""} · 템플릿을 다시 셈했습니다`);
      Object.assign(DIVL, { key: null, data: null, pending: r.shape }); // 새 실행의 그래프가 읽히면 목록도 다시 읽는다
      headsPoll(); // 상태를 다시 읽으면 2단계 카드·그래프·이 열이 새 실행으로 바뀐다
    } else {
      DIVL.data = d;
      toast(`지정을 저장했습니다 — ${d.note}`);
    }
  } catch (e) {
    if (epoch === state.epoch) toast(`지정하지 못했습니다: ${e.message}`, true);
  } finally {
    DIVL.busy = false;
    divlRefill();
  }
}

function divLabelsPending(g) { // 방금 지정을 바꾼 꼴이 든 템플릿 id(한 번만) — 다시 그린 「템플릿 관계」 가 그 템플릿을 펼친다
  const shape = DIVL.pending;
  if (!shape) return null;
  DIVL.pending = null;
  const x = (g.nodes || []).find((n) => n.kind === "label" && n.level === 1 && n.tplNo && divlShape(n.letter) === shape);
  return x ? x.tplNo : null;
}
