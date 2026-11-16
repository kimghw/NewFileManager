// 에이전트 설정 페이지(spec_에이전트 ② §5) — 사용자 2026-11-15 "에이전트 설정을 만들고, 어떤 역할을 하고 프롬프트가 무엇인지 작업번호등을 관리할 수 있는 관리를 우측 상단에 배치해줘"
//   → 같은 날 "에이전트도 워크플로우 처럼 페이지로 해줘": 문서 옆 열(2열)이던 것을 따로 선 페이지 /agents 로 옮겼다(상단 바 링크 a#agentsLink — 새 탭). app.js 없이 혼자 돈다.
// 화면 셋(주소의 #): ⓐ #overview 전체 보기 — 묶음마다 에이전트 줄(작업 번호 · 이름 · 모델·생각 깊이 · 쓰는 곳 · 역할 · 마지막 실행) ⓑ #<에이전트 id> 한 에이전트 — ① 작업 번호·쓰는 곳 ② 역할 ③ 모델·생각 깊이(여기까지 「저장」)
//   ④ 프롬프트(보내는 글의 차례: 계약 → 지침·스킬·할 일 프롬프트·양식 정보·표 지침 → 자료 — 고칠 수 있는 글은 그 자리에서 고쳐 제 저장소에 저장) ⑤ 최근 실행 ⓒ #runs 실행 기록(모든 에이전트 — 서버를 켠 뒤의 것).
// 끝점: GET /api/agents · GET/PUT /api/agents/{id} · GET /api/agents/runs — 프롬프트 글 저장은 그 글의 저장소 끝점(part.api: /api/headings/guides/{이름} · /api/outline/agent/skills/{키}).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const nf = (v) => (v == null ? "–" : Number(v).toLocaleString("ko-KR"));
  const MODEL = { "claude-fable-5-2": "Fable 5.2", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5" }; // 워크플로우 페이지(workflow.js MODEL)와 같은 이름
  const SRC = { user: "여기서 정함", pin: "이 에이전트에 고정", force: "서버 전체 설정", code: "코드가 정함", default: "서버 기본" };
  const EFFORT = { low: "낮음(low)", medium: "보통(medium)", high: "높음(high)", xhigh: "더 높음(xhigh)", max: "가장 높음(max)" };
  const KEYS = { no: "작업 번호", role: "역할", model: "모델", effort: "생각 깊이" };
  // drafts = 에이전트마다 저장 안 한 ①②③ 값(다른 화면에 갔다 와도 남는다 — 페이지를 닫으면 버린다) · edit = 고치는 프롬프트 조각 `id|차례` · arm = 한 번 더 눌러야 하는 단추
  const S = { list: null, err: "", view: "overview", id: null, detail: null, drafts: new Map(), busy: false, edit: null, text: "", arm: null, runs: null, open: new Set(), seq: 0 };
  const modelName = (m) => MODEL[m] || m || "모델 모름";
  const when = (t) => (t ? new Date(t * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "");
  const secs = (ms) => `${Math.round((ms || 0) / 100) / 10}초`;
  const customText = (a) => a.custom.map((k) => KEYS[k]).join(" · ");
  const tag = (text, kind) => el("span", "ags-tag" + (kind ? " " + kind : ""), text);
  const link = (href, text, cls) => { const a = el("a", cls || "", text); a.href = href; return a; };

  async function api(url, opts = {}) {
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try { const body = await r.json(); msg = (typeof body.detail === "string" ? body.detail : null) || msg; } catch { /* 본문 없음 */ }
      throw Object.assign(new Error(msg), { status: r.status });
    }
    return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
  }
  const put = (url, body) => api(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let toastTimer = 0;
  function toast(msg, err = false) {
    const t = $("agToast");
    t.textContent = msg;
    t.className = "toast" + (err ? " err" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, err ? 7000 : 3500);
  }
  function btn(text, fn, { disabled = false, title = "", cls = "btn sm" } = {}) {
    const b = el("button", cls, text);
    b.type = "button";
    b.disabled = disabled;
    if (title) b.title = title;
    b.onclick = fn;
    return b;
  }

  // ---------------------------------------------------------------- 읽기 · 주소
  async function loadList() {
    try { S.list = await api("/api/agents"); S.err = ""; }
    catch (e) { S.list = null; S.err = e.status === 404 ? "서버가 옛 판이라 에이전트 설정을 모릅니다 — 서버(8114)를 다시 시작한 뒤 쓰세요" : `에이전트 목록을 읽지 못했습니다: ${e.message}`; }
  }
  async function loadDetail(id) { // 읽는 사이 다른 화면으로 갔으면 버린다(늦게 온 답이 지금 화면을 덮지 않게)
    const here = () => S.view === "detail" && S.id === id;
    try { const d = await api(`/api/agents/${encodeURIComponent(id)}`); if (here()) { S.detail = d; S.err = ""; } }
    catch (e) { if (here()) { S.detail = null; S.err = `에이전트를 읽지 못했습니다: ${e.message}`; } }
  }
  async function loadRuns() {
    try { S.runs = (await api("/api/agents/runs?limit=200")).runs; }
    catch (e) { S.runs = []; toast(e.message, true); }
  }
  function route() { // 주소의 # → 화면(모르는 id 는 전체 보기)
    let id = "";
    try { id = decodeURIComponent(location.hash.replace(/^#/, "")); } catch { id = ""; }
    if (id === "runs") return { view: "runs", id: null };
    if (id && id !== "overview" && (!S.list || S.list.agents.some((a) => a.id === id))) return { view: "detail", id };
    return { view: "overview", id: null };
  }
  async function go() { // 주소가 바뀌었거나 처음 — 그 화면을 그리고(읽는 중) 읽은 뒤 다시 그린다
    const first = !S.list;
    if (first) await loadList(); // 목록이 있어야 주소의 id 를 가린다(못 읽었으면 올 때마다 다시 읽어 본다)
    const r = route(), seq = ++S.seq, moved = r.view !== S.view || r.id !== S.id;
    Object.assign(S, { view: r.view, id: r.id, arm: null });
    if (moved) S.edit = null;
    if (r.view === "detail" && (!S.detail || S.detail.id !== r.id)) S.detail = null;
    if (r.view === "runs") S.runs = null;
    draw();
    if (moved) $("agMain").scrollTop = 0;
    if (r.view === "detail") await loadDetail(r.id);
    else if (r.view === "runs") await loadRuns();
    else if (!first) await loadList(); // 전체 보기로 돌아올 때마다 마지막 실행 · 고친 것을 새로
    if (seq === S.seq) draw();
  }

  // ---------------------------------------------------------------- 저장 안 한 값(①②③)
  const saved = (a) => ({ no: a.no, role: a.role, model: a.user.model || "", effort: a.user.effort || "" });
  function dirty(a) { const x = S.drafts.get(a.id), v = saved(a); return !!x && (x.no !== v.no || x.role !== v.role || x.model !== v.model || x.effort !== v.effort); }
  const draftOf = (d) => S.drafts.get(d.id) || saved(d); // 고친 값이 있을 때만 drafts 에 둔다(detailView 의 sync)

  // ---------------------------------------------------------------- 상단 줄 · 목차
  function modelChip(a) { // 「Fable 5.2」 — 여기서 정했으면 파랑, 이 에이전트에 고정이면 보라
    const c = el("span", `ags-model ${a.model.source}`, modelName(a.model.id));
    c.title = `지금 부르는 모델: ${a.model.id} — ${SRC[a.model.source] || a.model.source}${a.modelCode && a.model.source === "force" ? `\n코드가 정한 모델은 ${modelName(a.modelCode)} 이지만 서버 전체 설정이 먼저입니다` : ""}`;
    return c;
  }
  function topDraw() {
    const L = S.list, llm = L ? L.llm : null, c = $("agLlm");
    $("agNote").textContent = L ? `에이전트 ${L.agents.length}개` : "";
    c.className = `ags-llm${llm && llm.available ? "" : " off"}`;
    c.textContent = !llm ? (S.err ? "읽지 못함" : "읽는 중…") : !llm.available ? "LLM 꺼짐"
      : `연결 ${llm.active === "api" ? "API" : llm.active || ""} · ${llm.forced ? `모든 에이전트 ${modelName(llm.forced)}` : `기본 ${modelName(llm.model)}`}`;
    c.title = !llm ? S.err : `LLM 길: ${llm.backend}${llm.active ? `(지금 ${llm.active})` : ""}\n${llm.forced ? `서버 전체 설정이 모든 에이전트의 모델을 ${llm.forced} 로 정해 두었습니다 — 에이전트에 따로 정한 모델과 「고정」 은 그보다 먼저입니다` : `서버 기본 모델 ${llm.model}`}`;
    const a = S.view === "detail" ? S.detail || (L && L.agents.find((x) => x.id === S.id)) : null;
    document.title = `${a ? `작업 ${a.no} · ${a.name} — ` : S.view === "runs" ? "실행 기록 — " : ""}에이전트 설정 — HWPX·DOCX 웹 편집`;
  }
  function navDraw() {
    const nav = $("agNav"), L = S.list, cur = S.view === "detail" ? S.id : S.view, keep = [nav.scrollTop, nav.scrollLeft];
    const focus = nav.contains(document.activeElement) ? document.activeElement.getAttribute("href") : null; // 다시 그려도 초점은 그 줄에
    const item = (href, id, kids) => { const a = link(href, null); a.append(...kids); if (id === cur) a.setAttribute("aria-current", "true"); return a; };
    const out = [item("#overview", "overview", [el("span", "ags-nname", "전체 보기")]), item("#runs", "runs", [el("span", "ags-nname", "실행 기록")])];
    for (const g of L ? L.groups : []) {
      const rows = L.agents.filter((a) => a.group === g);
      if (!rows.length) continue;
      out.push(el("h2", null, g));
      for (const a of rows) {
        const kids = [el("span", "ags-nno", a.no), el("span", "ags-nname", a.name)];
        if (dirty(a)) { const m = el("span", "ags-nmark dirty", "저장 안 됨"); m.title = "고친 값을 아직 저장하지 않았습니다"; kids.push(m); }
        else if (a.custom.length) { const m = el("span", "ags-nmark", "고침"); m.title = `고친 것: ${customText(a)}`; kids.push(m); }
        const row = item(`#${a.id}`, a.id, kids);
        row.dataset.agent = a.id;
        out.push(row);
      }
    }
    nav.replaceChildren(...out);
    [nav.scrollTop, nav.scrollLeft] = keep;
    if (focus) { const a = out.find((e) => e.tagName === "A" && e.getAttribute("href") === focus); if (a) a.focus({ preventScroll: true }); }
  }

  function draw() {
    topDraw();
    navDraw();
    const main = $("agMain"), keep = main.scrollTop;
    main.replaceChildren(S.view === "detail" ? detailView() : S.view === "runs" ? runsView() : overView());
    main.scrollTop = keep;
  }

  // ---------------------------------------------------------------- ⓐ 전체 보기
  function overView() {
    const L = S.list, wrap = el("section", "ags-body");
    wrap.id = "overview";
    wrap.append(el("h2", "ags-h2", "전체 보기"), el("p", "ags-lead", "에이전트 = 앱이 LLM 에 맡기는 일 하나입니다. 에이전트마다 작업 번호 · 어떤 역할인지 · 어디서 도는지 · 무슨 프롬프트로 도는지를 보고, 작업 번호 · 역할 글 · 모델 · 생각 깊이를 고칩니다. "
      + "프롬프트는 「계약」(답의 꼴 — 코드와 한 몸이라 고치지 않음) 뒤에 지침 · 스킬 · 할 일 프롬프트가 붙는 꼴이고, 고칠 수 있는 글은 그 자리에서 고칩니다. 설정은 이 PC 의 모든 문서가 같이 씁니다."));
    if (S.err) wrap.append(el("p", "ags-warn", S.err));
    if (!L) { if (!S.err) wrap.append(el("p", "ags-note", "읽는 중…")); return wrap; }
    for (const g of L.groups) {
      const rows = L.agents.filter((a) => a.group === g);
      if (!rows.length) continue;
      wrap.append(el("h3", "ags-g", `${g} ${rows.length}`));
      const ul = el("ul", "ags-list");
      for (const a of rows) {
        const li = el("li"), row = link(`#${a.id}`, null, "ags-row"), main = el("span", "ags-rmain"), head = el("span", "ags-head");
        row.dataset.agent = a.id;
        row.title = "누르면 이 에이전트의 설정 — 작업 번호 · 역할 · 모델 · 프롬프트";
        head.append(el("b", null, a.name), modelChip(a), el("span", "ags-eff", a.effort.id));
        if (dirty(a)) head.append(tag("저장 안 됨", "dirty"));
        else if (a.custom.length) { const c = tag("고침", "chg"); c.title = `고친 것: ${customText(a)}`; head.append(c); }
        main.append(head);
        if (a.last) main.append(el("span", `ags-last${a.last.ok ? "" : " bad"}`, `마지막 실행 #${a.last.n} · ${when(a.last.t)} · ${secs(a.last.ms)}${a.last.ok ? "" : " · 실패"} · 켠 뒤 ${nf(a.runs)}번`));
        row.append(el("span", "ags-no", a.no), main, el("span", "ags-where", a.where), el("span", "ags-role", a.role));
        li.append(row);
        ul.append(li);
      }
      wrap.append(ul);
    }
    return wrap;
  }

  // ---------------------------------------------------------------- ⓑ 한 에이전트
  const sec = (no, title, help) => { const s = el("section", "ags-sec"), h = el("h3", "ags-h"); h.append(el("span", "ags-n", no), title); s.append(h); if (help) s.append(el("p", "ags-help", help)); return s; };

  function detailView() {
    const d = S.detail && S.detail.id === S.id ? S.detail : null, L = S.list, wrap = el("article", "ags-body agd");
    wrap.append(link("#overview", "‹ 전체 보기", "ags-back"));
    if (S.err) wrap.append(el("p", "ags-warn", S.err));
    if (!d) { if (!S.err) wrap.append(el("p", "ags-note", "읽는 중…")); return wrap; }
    const x = draftOf(d), busy = S.busy, h2 = el("h2", "ags-h2");
    h2.append(el("span", "ags-no", d.no), el("span", "ags-dname", d.name), tag(d.group), tag(d.runText, d.run === "auto" ? "auto" : ""));
    wrap.append(h2);
    // ① 작업 번호 · 쓰는 곳
    const s1 = sec("①", "작업 — 번호 · 쓰는 곳", "목록과 실행 기록에서 이 번호로 부릅니다. 글자·숫자 12자까지 · 다른 에이전트와 겹칠 수 없음 · 비우면 기본 번호로 돌아갑니다.");
    const no = el("input", "ags-noin");
    no.type = "text"; no.maxLength = 12; no.value = x.no; no.placeholder = d.noDefault; no.setAttribute("aria-label", "작업 번호"); no.disabled = busy;
    const row1 = el("div", "ags-rowline");
    row1.append(el("span", "ags-lab", "작업 번호"), no);
    const where = el("p", "ags-kv"); where.append(el("span", "ags-lab", "쓰는 곳"), d.where);
    const whats = el("p", "ags-kv ags-muted"); whats.append(el("span", "ags-lab", "호출 이름"), d.whats.map((w) => `${w}…`).join(" · "));
    whats.title = "서버 기록·실행 기록에 남는 이 에이전트의 호출 이름 첫머리";
    s1.append(row1, where, whats);
    // ② 역할
    const s2 = sec("②", "역할", "이 에이전트가 무슨 일을 하는지 적은 글입니다(사람이 읽는 설명 — LLM 에 보내는 글이 아닙니다). 비우면 기본 글로 돌아갑니다.");
    const role = el("textarea", "ags-role-in");
    role.value = x.role; role.maxLength = 600; role.rows = 5; role.setAttribute("aria-label", "역할"); role.disabled = busy;
    s2.append(role);
    // ③ 모델 · 생각 깊이
    const s3 = sec("③", "모델 · 생각 깊이", "여기서 고른 값은 이 에이전트에만 걸리고, 서버 전체 설정이나 코드가 정한 값보다 먼저입니다. 「따로 정하지 않음」 이면 서버 설정대로 돕니다.");
    const base = d.pin && d.modelCode ? d.modelCode : (L && L.llm.forced) || d.modelCode || (L ? L.llm.model : ""), baseSrc = d.pin && d.modelCode ? "이 에이전트에 고정" : L && L.llm.forced ? "서버 전체 설정" : d.modelCode ? "코드가 정함" : "서버 기본";
    const model = el("select", "ags-model-in");
    model.setAttribute("aria-label", "모델");
    const opt = (sel, v, t) => { const o = el("option", null, t); o.value = v; sel.append(o); };
    opt(model, "", `따로 정하지 않음 — 지금 ${modelName(base)}(${baseSrc})`);
    for (const m of [...new Set([...(L ? L.models : Object.keys(MODEL)), ...(x.model ? [x.model] : [])])]) opt(model, m, modelName(m));
    model.value = x.model; model.disabled = busy;
    const effort = el("select", "ags-effort-in");
    effort.setAttribute("aria-label", "생각 깊이");
    opt(effort, "", `따로 정하지 않음 — 지금 ${d.effortCode || (d.effort.source === "user" ? "low" : d.effort.id)}`);
    for (const e of (L ? L.efforts : Object.keys(EFFORT))) opt(effort, e, EFFORT[e] || e);
    effort.value = x.effort; effort.disabled = busy;
    const row3 = el("div", "ags-form"); // 이름표 칸 + 고르기 칸 — 좁은 단에서도 이름표와 고르기가 한 줄에 선다
    row3.append(el("span", "ags-lab", "모델"), model, el("span", "ags-lab", "생각 깊이"), effort);
    const now = el("p", "ags-kv ags-muted"); now.append(el("span", "ags-lab", "지금"), `${modelName(d.model.id)} · ${d.effort.id} — ${SRC[d.model.source]}`);
    s3.append(row3, now);
    // 저장 줄(①②③ 을 함께 — 높이 고정)
    const state = el("div", "ags-rowline ags-state"), st = el("span", "ags-saved"), save = btn("저장", () => saveAgent(), { cls: "btn sm primary ags-save" });
    const drop = btn("고친 것 버리기", () => { S.drafts.delete(d.id); S.arm = null; draw(); });
    let was = null;
    const sync = () => {
      Object.assign(x, { no: no.value.trim(), role: role.value.trim(), model: model.value, effort: effort.value });
      const v = saved(d), dt = x.no !== v.no || x.role !== v.role || x.model !== v.model || x.effort !== v.effort;
      if (dt) S.drafts.set(d.id, x); else S.drafts.delete(d.id);
      st.textContent = dt ? "고침 — 저장 안 됨" : d.custom.length ? `저장됨 — 고친 것: ${customText(d)}` : "기본값 그대로";
      st.className = `ags-saved${dt ? " dirty" : ""}`;
      save.disabled = busy || !dt;
      drop.hidden = !dt;
      if (was !== null && was !== dt) navDraw(); // 목차의 「저장 안 됨」 표시
      was = dt;
    };
    no.oninput = role.oninput = model.onchange = effort.onchange = sync;
    state.append(st, el("span", "ags-spacer"), drop, save);
    if (d.custom.length) state.append(btn(S.arm === "reset" ? "기본으로 확인" : "모두 기본으로", () => { if (S.arm === "reset") saveAgent(true); else { S.arm = "reset"; draw(); } },
      { title: "작업 번호 · 역할 · 모델 · 생각 깊이를 모두 기본값으로 — 한 번 더 누르면 됩니다", cls: `btn sm${S.arm === "reset" ? " danger" : ""}`, disabled: busy }));
    sync();
    // ④ 프롬프트
    const s4 = sec("④", "프롬프트 — 보내는 글의 차례", "LLM 에 보내는 글은 아래 차례로 이어 붙습니다. 「계약」(입력의 뜻 · 답의 꼴)은 코드와 한 몸이라 읽기만 합니다. 「지침」·「스킬」 은 사람이 관리하는 판단 기준 — 「고치기」 가 있는 글은 여기서 고쳐 저장하면 다음 실행부터 쓰입니다. "
      + "저장소 파일이 원본인 글(판단 지침 · 할 일 프롬프트)은 그 파일을 고칩니다.");
    d.prompt.forEach((p, i) => s4.append(part(p, i)));
    // ⑤ 최근 실행
    const s5 = sec("⑤", "최근 실행", "서버를 켠 뒤 이 에이전트가 돈 기록입니다(서버를 다시 켜면 비워집니다). 실행 번호는 모든 에이전트가 함께 쓰는 차례 번호입니다.");
    s5.append(d.recent.length ? runTable(d.recent, false) : el("p", "ags-note", "서버를 켠 뒤 아직 돌지 않았습니다."));
    const left = el("div", "ags-card ags-set"), right = el("div", "ags-card ags-prompt"), cols = el("div", "ags-cols");
    left.append(s1, s2, s3, state);
    right.append(s4, s5);
    cols.append(left, right);
    wrap.append(cols);
    return wrap;
  }

  function part(p, i) { // 프롬프트의 한 조각 — 접는 줄(차례 · 이름 · 출처 · 글자 수) + 글(읽기만 | 고치기)
    const key = `${S.id}|${i}`, det = el("details", `agp k-${p.kind}`), sum = el("summary");
    det.open = S.open.has(key) || S.edit === key;
    det.ontoggle = () => { if (det.open) S.open.add(key); else S.open.delete(key); };
    sum.append(el("span", "agp-i", String(i + 1)), el("b", null, p.title), el("span", "agp-src", p.source));
    if (p.text) sum.append(el("span", "agp-len", `${nf(p.text.length)}자`));
    if (p.editable) sum.append(tag(p.custom ? "고침" : "고칠 수 있음", p.custom ? "chg" : ""));
    else if (p.kind === "contract") sum.append(tag("읽기만"));
    det.append(sum);
    if (p.note) det.append(el("p", "agp-note", p.note));
    if (!p.text && !p.editable) return det;
    const editing = S.edit === key, ta = el("textarea", `agp-text${editing ? "" : " ro"}`);
    ta.readOnly = !editing; ta.spellcheck = false; ta.value = editing ? S.text : p.text; ta.setAttribute("aria-label", p.title);
    ta.rows = Math.max(4, Math.min(32, (ta.value.match(/\n/g) || []).length + 2));
    ta.oninput = () => { S.text = ta.value; };
    det.append(ta);
    if (p.editable) {
      const acts = el("div", "ags-rowline agp-acts");
      if (!editing) acts.append(btn("고치기", () => { S.edit = key; S.text = p.text; S.arm = null; draw(); }, { title: "이 글을 고칩니다 — 저장하면 다음 실행부터 쓰입니다", disabled: S.busy }));
      else acts.append(btn("저장", () => savePart(p), { cls: "btn sm primary", disabled: S.busy }), btn("취소", () => { S.edit = null; draw(); }, { disabled: S.busy }));
      if (p.custom && (p.kind === "heading" || p.builtin)) acts.append(btn(S.arm === key ? "되돌리기 확인" : "기본으로 되돌리기", () => { if (S.arm === key) resetPart(p); else { S.arm = key; draw(); } },
        { title: "내 사본을 버리고 기본 글로 — 한 번 더 누르면 됩니다", cls: `btn sm${S.arm === key ? " danger" : ""}`, disabled: S.busy }));
      acts.append(el("span", "agp-ver", p.custom ? `내 사본 · 판 ${p.version}` : "기본 글"));
      det.append(acts);
    }
    return det;
  }

  function runTable(rows, withAgent) { // 실행 기록 표 — 번호 · 시각 · (에이전트) · 모델 · 시간 · 결과
    const t = el("table", "ags-runs"), head = el("tr"), names = new Map(((S.list && S.list.agents) || []).map((a) => [a.id, a]));
    for (const h of ["실행", "시각", ...(withAgent ? ["에이전트"] : []), "모델", "시간", "결과"]) head.append(el("th", null, h));
    const thead = el("thead"); thead.append(head);
    const tb = el("tbody");
    for (const r of rows) {
      const tr = el("tr", r.ok ? null : "bad"), a = names.get(r.agent);
      tr.append(el("td", "num", `#${r.n}`), el("td", null, when(r.t)));
      if (withAgent) { const td = el("td"); if (a) td.append(link(`#${a.id}`, `${a.no} ${a.name}`, "ags-runlink")); else td.textContent = r.what; tr.append(td); }
      const m = el("td", null, `${modelName(r.model)}${r.effort ? ` · ${r.effort}` : ""}`); m.title = `${r.what}${r.backend ? ` · 길 ${r.backend}` : ""}${r.costUsd != null ? ` · $${(+r.costUsd).toFixed(4)}` : ""}`;
      const res = el("td", r.ok ? "ok" : "bad", r.ok ? "성공" : r.error === "off" ? "LLM 꺼짐" : r.error === "busy" ? "자리 없음" : "실패"); if (r.error) res.title = r.error;
      tr.append(m, el("td", "num", secs(r.ms)), res);
      tb.append(tr);
    }
    t.append(thead, tb);
    const box = el("div", "ags-runbox"); box.append(t);
    return box;
  }

  // ---------------------------------------------------------------- ⓒ 실행 기록
  function runsView() {
    const wrap = el("section", "ags-body"), h2 = el("h2", "ags-h2");
    wrap.id = "runs";
    h2.append("실행 기록");
    if (S.runs) h2.append(el("span", "ags-count", `${nf(S.runs.length)}건`));
    h2.append(el("span", "ags-spacer"), btn("다시 읽기", () => go(), { cls: "btn sm ags-reload" }));
    wrap.append(h2, el("p", "ags-lead", "서버를 켠 뒤 모든 에이전트가 돈 기록입니다(새 것부터 · 서버를 다시 켜면 비워집니다). 에이전트 이름을 누르면 그 에이전트의 설정으로 갑니다."));
    wrap.append(!S.runs ? el("p", "ags-note", "읽는 중…") : S.runs.length ? runTable(S.runs, true) : el("p", "ags-note", "아직 돈 에이전트가 없습니다."));
    return wrap;
  }

  // ---------------------------------------------------------------- 저장
  async function saveAgent(reset = false) { // ①②③ 저장 — reset 이면 모두 기본으로
    const d = S.detail, x = d && S.drafts.get(d.id);
    if (!d || S.busy || (!reset && !x)) return;
    const body = reset ? { no: null, role: null, model: null, effort: null } : { no: x.no || null, role: x.role || null, model: x.model || null, effort: x.effort || null };
    S.busy = true;
    try {
      const next = await put(`/api/agents/${encodeURIComponent(d.id)}`, { ...body, version: d.version });
      if (S.id === d.id) S.detail = next;
      S.drafts.delete(d.id);
      S.arm = null;
      toast(reset ? `「${d.name}」 의 설정을 기본값으로 되돌렸습니다` : `「${d.name}」 의 설정을 저장했습니다 — 다음 실행부터 ${modelName(next.model.id)} · ${next.effort.id}`);
      await loadList();
    } catch (e) {
      toast(e.status === 409 ? "다른 곳에서 에이전트 설정을 먼저 고쳤습니다 — 다시 읽습니다" : e.message, true);
      if (e.status === 409) { S.drafts.delete(d.id); await loadDetail(d.id); }
    } finally { S.busy = false; draw(); }
  }
  async function savePart(p) { // 프롬프트의 고칠 수 있는 글 — 그 글의 저장소에 저장(헤딩 지침 · 템플릿 정리 스킬)
    if (S.busy) return;
    if (!S.text.trim()) { toast("빈 글은 저장할 수 없습니다", true); return; }
    const id = S.id;
    S.busy = true;
    try {
      await put(p.api, p.kind === "skill" ? { name: p.skillName, text: S.text, version: p.version } : { text: S.text, version: p.version, reason: "에이전트 설정" });
      S.edit = null;
      S.arm = null;
      toast(`「${p.title}」 을 저장했습니다 — 다음 실행부터 이 글로 돕니다`);
      await loadDetail(id);
    } catch (e) { toast(e.status === 409 ? "다른 곳에서 이 글을 먼저 고쳤습니다 — 「취소」 뒤 다시 고쳐 주세요" : `저장하지 못했습니다: ${e.message}`, true); }
    finally { S.busy = false; draw(); }
  }
  async function resetPart(p) {
    if (S.busy) return;
    const id = S.id;
    S.busy = true;
    try {
      await api(p.api, { method: "DELETE" });
      S.edit = null;
      S.arm = null;
      toast(`「${p.title}」 을 기본 글로 되돌렸습니다`);
      await loadDetail(id);
    } catch (e) { toast(`되돌리지 못했습니다: ${e.message}`, true); }
    finally { S.busy = false; draw(); }
  }

  addEventListener("hashchange", go);
  (async () => { await loadList(); await go(); })();
})();
