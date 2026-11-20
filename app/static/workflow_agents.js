// 조립 화면의 「에이전트」 열(spec_워크플로우 ② §18-16 · design.md §22 — 2026-11-20 사용자 "각각의 단계에서 사용하는 에이전트의 스킬/도구/프롬프트는 클릭해서 여기서 보고 수정할 수 있게 해줘,,
// 다만 그건 범용일 수도 있고 현재 이 워크플로우 전용일 수 있으니 구분해서 작성할 수 있게 해줘, 우측 새로운 열에 확인할 수 있도록 해줘"):
// 같은 날 "공통적으로 그 도구에서는 는 내용과 워크플로우마다 사용되는 애용 2가지. 예로 구성맞추기 할때.. 사업계획서랑 다른 문서랑 제공해야 하는 정보가 다르잖아" — **단위는 도구(줄)다**:
// 조립 폼 · 단계 폼의 **오른쪽 새 열**(「도구 설명」 열의 오른쪽). 줄(도구) 카드를 누르면 맨 위에 **그 도구에 적어 두는 내용 두 칸** — 「도구 공통」(그 도구를 쓰는 모든 워크플로우) · 「이 워크플로우 전용」(이 워크플로우에서 그 도구에만) —
// 이 서고(에이전트가 없는 도구에도), 그 아래에 그 줄이 쓰는 에이전트(보내는 글의 차례: 계약 · 지침 · 스킬 · 전제 · 자료)와 쓰는 도구가 보인다. 지침 · 스킬 글은 범용 그대로 그 자리에서 고친다.
// 에이전트 하나에만 덧붙이는 글(모든 워크플로우 · 이 워크플로우)은 그 에이전트 안의 접어 둔 칸(더 좁은 층 — 선택)이다.
// 이 파일은 workflow.js 없이 혼자 선다(제 도우미) — workflow.js 의 훅은 셋: helpWrap 끝의 `WfAgents.mount(cols, c, sec, ctx)` · helpSync 끝의 `WfAgents.sync(c)` · composeSave 의 `WfAgents.flush(c, key)`.
//   ctx = { unit(key) → 조립 응답의 줄 | null, units() → 그 틀의 줄들, family() → relay · gather · single, pick(key) → 그 도구를 고른다(「도구 설명」 과 같은 고름), workflow → 워크플로우 폼인가(단계 폼은 false) }
// 고른 것은 「도구 설명」 열과 같다(c.help — 줄 key 하나). 이 열을 여닫거나 글을 적는 것은 조립(줄 · 서버 검사)을 바꾸지 않는다.
// 서버: GET /api/agent-notes/lines(줄 → 에이전트 · 도구) · GET /api/agent-notes(적어 둔 글) · PUT /api/agent-notes/tools/{틀}/{줄} {text, job?, version}(도구) · PUT /api/agent-notes/{에이전트} {text, job?, version}(에이전트) · GET /api/agents/{에이전트}(보내는 글) ·
//   범용 글의 저장 = 그 글의 저장소(헤딩 지침 PUT/DELETE /api/headings/guides/{이름} · 스킬 PUT/DELETE /api/outline/agent/skills/{키} — 에이전트 설정 페이지와 같은 끝점).
// 접기(design.md §5 — 열은 오른쪽으로 접혀 28px 띠): 넓은 창(1840px 위)은 폼 | 도구 설명 | 에이전트 세 칸 · 그 아래는 둘 가운데 하나가 띠로 접힌다(cols 의 data-side = help | agents) · 1360px 아래(한 칸)는 높이 28px 가로 띠.
(() => {
  "use strict";
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const MODEL = { "claude-fable-5-2": "Fable 5.2", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5" };
  const SOURCE = { user: "에이전트 설정에서 정함", pin: "이 에이전트에 고정", force: "서버 전체 설정", code: "코드가 정함", default: "서버 기본" };
  // 조각의 범위 꼬리표 — 무엇을 어디서 고치나(범용 = 모든 워크플로우 · 워크플로우 = 이 워크플로우만 · 문서 = 문서마다 · 코드 = 고치지 않는다)
  const SCOPE = { contract: ["코드", "code"], heading: ["범용", "all"], skill: ["범용", "all"], merge: ["범용 · 파일", "all"], job: ["이 워크플로우", "job"], form: ["문서마다", "doc"], table: ["문서마다", "doc"],
    workflow: ["만든 글", "code"], taskdoc: ["만든 글", "code"], logs: ["기록", "code"], data: ["스크립트", "code"], toolnote: ["도구", "all"] };
  const WIDE = "(min-width: 1840px)", NARROW = "(max-width: 1359px)";
  const nf = (n) => Number(n || 0).toLocaleString("ko-KR");
  const catalog = () => (typeof TASK_CATALOG === "undefined" ? {} : TASK_CATALOG);
  const josa = (word, a, b) => (typeof taskJosa === "function" ? taskJosa(word, a, b) : a);
  const A = { lines: null, notes: null, err: "", loading: null, detail: new Map(), detailErr: new Map() }; // 페이지에 하나 — 줄 → 에이전트 · 덧붙이는 글 · 에이전트마다 보내는 글

  async function call(url, opts) { // → 답(JSON) | 예외(e.status · 서버의 글 그대로)
    const r = await fetch(url, { headers: { Accept: "application/json", ...(opts && opts.body ? { "Content-Type": "application/json" } : {}) }, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error((typeof data.detail === "string" && data.detail) || `HTTP ${r.status}`); e.status = r.status; throw e; }
    return data;
  }
  function load(force) { // 줄 → 에이전트(한 번) · 덧붙이는 글(폼을 열 때마다 새로)
    if (A.loading && !force) return A.loading;
    A.loading = (async () => {
      try {
        const [lines, notes] = await Promise.all([A.lines ? A.lines : call("/api/agent-notes/lines"), call("/api/agent-notes")]);
        A.lines = lines; A.notes = notes; A.err = "";
      } catch (e) { A.err = e.status === 404 ? "서버를 다시 켠 뒤에 볼 수 있습니다(이 서버는 아직 에이전트 열을 모릅니다)." : `에이전트를 읽지 못했습니다 — ${e.message}`; }
    })();
    return A.loading;
  }
  async function detailLoad(aid, force) { // 에이전트 하나의 보내는 글(GET /api/agents/{id}) — 펼칠 때 읽는다
    if (A.detail.has(aid) && !force) return;
    try { A.detail.set(aid, await call(`/api/agents/${encodeURIComponent(aid)}`)); A.detailErr.delete(aid); }
    catch (e) { A.detailErr.set(aid, e.message); }
  }

  // ---- 폼마다의 상태(c.ag) — open(펼친 에이전트) · seen(펼친 조각) · typed(적었지만 저장 안 한 글: "<범위>|<도구의 줄 key | 에이전트 id>" → 글) · edit(고치는 범용 글 {key, text}) · side(좁은 창에서 펴 둔 열)
  // 범위 넷: tool(도구 공통) · jobtool(도구 · 이 워크플로우 전용) — id = 줄 key / all(에이전트 · 모든 워크플로우) · job(에이전트 · 이 워크플로우 전용) — id = 에이전트 id
  const st = (c) => c.ag;
  const family = (c) => { const f = st(c).ctx.family(); return A.lines && A.lines.families[f] ? f : "relay"; };
  const rowOf = (c, key) => (A.lines && key ? (A.lines.families[family(c)] || {})[/^hand\d*$/.test(key) ? "hand" : key] : null) || { agents: [], tools: [] };
  const agentOf = (aid) => (A.lines && A.lines.agents[aid]) || { id: aid, no: "", name: aid, role: "", parts: [], model: null, effort: null, runText: "" };
  const jobOf = (c) => (st(c).ctx.workflow && c.key ? c.key : ""); // 저장된 워크플로우의 키 | ""(새 워크플로우 · 단계 폼)
  const isJob = (scope) => scope === "job" || scope === "jobtool", isTool = (scope) => scope === "tool" || scope === "jobtool";
  const boxOf = (scope, job, make) => { // 그 범위의 글이 든 칸(A.notes 안) — job = 워크플로우 키(전용 범위일 때) · make = 없으면 만든다
    const N = A.notes, top = scope === "all" ? "all" : scope === "tool" ? "tools" : scope === "job" ? "jobs" : "jobTools";
    if (!N[top]) N[top] = {};
    if (!isJob(scope)) return N[top];
    if (!N[top][job] && make) N[top][job] = {};
    return N[top][job] || {};
  };
  const keyOf = (c, scope, id) => (scope === "tool" ? `${family(c)}.${id}` : id); // 도구 공통은 「틀.줄」 로 적는다
  const saved = (c, scope, id) => (!A.notes || (isJob(scope) && !jobOf(c)) ? "" : boxOf(scope, jobOf(c))[keyOf(c, scope, id)] || "");
  const urlOf = (c, scope, id) => (isTool(scope) ? `/api/agent-notes/tools/${encodeURIComponent(family(c))}/${encodeURIComponent(id)}` : `/api/agent-notes/${encodeURIComponent(id)}`);
  const unitName = (c, id) => { const u = st(c).ctx.unit(id); return (u && u.name) || id; };
  const SCOPE_NAME = { tool: "도구 공통", jobtool: "이 워크플로우 전용", all: "에이전트 · 모든 워크플로우", job: "에이전트 · 이 워크플로우 전용" };
  const typedKey = (scope, aid) => `${scope}|${aid}`;
  const textOf = (c, scope, aid) => (st(c).typed.has(typedKey(scope, aid)) ? st(c).typed.get(typedKey(scope, aid)) : saved(c, scope, aid));
  const dirty = (c, scope, aid) => st(c).typed.has(typedKey(scope, aid)) && st(c).typed.get(typedKey(scope, aid)).trim() !== saved(c, scope, aid);
  const flowName = (c) => (c.name && c.name.trim()) || (c.key ? (catalog()[c.key] || {}).name || c.key : "새 워크플로우");

  function seed(c) { // 복제한 새 워크플로우 — 원래 워크플로우의 전용 글을 적어 둔다(저장할 때 새 키로 함께 저장된다)
    const s = st(c);
    if (s.seeded || !A.notes || !s.ctx.workflow || c.key || !c.copyOf) return;
    s.seeded = true;
    const from = Object.keys(catalog()).find((k) => (catalog()[k] || {}).name === c.copyOf);
    for (const scope of ["jobtool", "job"]) for (const [id, text] of Object.entries((from && boxOf(scope, from)) || {})) if (!s.typed.has(typedKey(scope, id))) s.typed.set(typedKey(scope, id), text);
  }

  // ---- 그리기
  function tag(text, kind) { return h("span", `wf-ag-tag${kind ? ` wf-ag-s-${kind}` : ""}`, text); }
  function btn(text, fn, opts = {}) {
    const b = h("button", opts.cls || "btn sm", text);
    b.type = "button";
    if (opts.title) b.title = opts.title;
    if (opts.disabled) b.disabled = true;
    b.addEventListener("click", fn);
    return b;
  }
  function modelText(a) {
    if (!a.model) return "";
    return `${MODEL[a.model.id] || a.model.id}${a.effort ? ` · ${a.effort.id}` : ""}`;
  }
  function noteMarks(c, aid) { // 그 에이전트에 적어 둔 덧붙이는 글의 표시(머리 줄 — 펼치지 않아도 보이게)
    const out = [];
    if (textOf(c, "all", aid).trim()) out.push(tag(dirty(c, "all", aid) ? "에이전트 글 · 저장 안 됨" : "에이전트 글", dirty(c, "all", aid) ? "dirty" : "all"));
    if (st(c).ctx.workflow && textOf(c, "job", aid).trim()) out.push(tag(dirty(c, "job", aid) || !c.key ? "에이전트 전용 글 · 저장 전" : "에이전트 전용 글", dirty(c, "job", aid) || !c.key ? "dirty" : "job"));
    return out;
  }

  function noteBox(c, id, scope) { // 적어 두는 글 칸 하나 — 범위 넷(tool · jobtool = 도구의 줄 key / all · job = 에이전트 id)
    const s = st(c), job = isJob(scope), tool = isTool(scope), who = tool ? unitName(c, id) : agentOf(id).name;
    const box = h("div", `wf-ag-note wf-ag-n-${job ? "job" : "all"}`), head = h("div", "wf-ag-note-head"), ta = h("textarea", "wf-ag-text"), foot = h("div", "wf-ag-acts"), state = h("span", "wf-ag-state");
    const noFlow = job && !s.ctx.workflow, fresh = job && s.ctx.workflow && !c.key, max = (A.notes && A.notes.max) || 4000;
    box.dataset.scope = scope;
    head.append(tag(job ? "이 워크플로우 전용" : tool ? "도구 공통" : "모든 워크플로우", job ? "job" : "all"),
      h("b", "", tool ? (job ? "이 워크플로우에서만 쓰는 내용" : "이 도구에서 공통으로 쓰는 내용") : job ? "이 에이전트에만 — 이 워크플로우에서만" : "이 에이전트에만 — 모든 워크플로우"));
    box.append(head);
    if (noFlow) { box.dataset.state = "none"; box.append(h("p", "wf-ag-hint", "단계는 워크플로우가 아니어서 전용 내용을 적을 곳이 없습니다 — 워크플로우를 조립할 때 그 워크플로우의 이 칸에 적습니다.")); return box; }
    box.append(h("p", "wf-ag-hint", tool
      ? (job ? `「${flowName(c)}」 에서 「${who}」 ${josa(who, "을", "를")} 할 때만 씁니다(공통 내용 뒤 — 어긋나면 이쪽이 먼저). 워크플로우마다 달라지는 것을 적습니다.`
        : `「${who}」 ${josa(who, "을", "를")} 쓰는 모든 워크플로우에서 씁니다 — 여기서 고치면 다른 워크플로우에도 적용됩니다.`)
      : (job ? `「${flowName(c)}」 ${josa(flowName(c), "으로", "로")} 하는 작업에서 「${who}」 ${josa(who, "을", "를")} 부를 때만 붙습니다.` : `어느 워크플로우 · 어느 도구에서든 「${who}」 ${josa(who, "을", "를")} 부를 때마다 붙습니다.`)));
    ta.value = textOf(c, scope, id); ta.spellcheck = false; ta.maxLength = max; ta.dataset.agNote = typedKey(scope, id);
    ta.rows = Math.max(3, Math.min(14, (ta.value.match(/\n/g) || []).length + 2));
    ta.placeholder = tool ? (job ? "예: 이 워크플로우의 문서는 차년도가 없다 — 기관만 본다" : "예: 기관 이름은 문서에 적힌 그대로 쓴다(줄이지 않는다)") : job ? "예: 이 워크플로우에서는 3차년도 자리만 잇는다" : "예: 표 머리의 단위(천원 · 백만원)가 다르면 같은 자리로 보지 않는다";
    ta.setAttribute("aria-label", `${who} — ${SCOPE_NAME[scope]}`);
    const save = btn("저장", () => noteSave(c, id, scope), { cls: "btn sm primary wf-ag-save", title: job ? "이 워크플로우 전용 내용을 저장합니다 — 다음 실행부터 쓰입니다" : "저장합니다 — 다음 실행부터 모든 워크플로우에서 쓰입니다" });
    const drop = btn("되돌리기", () => { s.typed.delete(typedKey(scope, id)); draw(c, true); }, { title: "적은 것을 버리고 저장된 글로" });
    const paint = () => {
      const d = dirty(c, scope, id), has = saved(c, scope, id), mod = d || (fresh && !!ta.value.trim());
      state.textContent = fresh ? (ta.value.trim() ? "워크플로우를 저장할 때 함께 저장됩니다" : "아직 없음") : d ? "고침 — 저장 안 됨" : has ? `저장됨 · ${nf(has.length)}자` : "아직 없음";
      state.className = `wf-ag-state${mod ? " dirty" : ""}`;
      box.dataset.state = mod ? "dirty" : has ? "saved" : "empty";
      save.hidden = fresh; save.disabled = !d || !!s.busy;
      drop.hidden = fresh || !d;
    };
    ta.addEventListener("input", () => {
      if (ta.value.trim() === saved(c, scope, id) && !fresh) s.typed.delete(typedKey(scope, id)); else s.typed.set(typedKey(scope, id), ta.value);
      paint(); if (tool) railSync(c); else marksSync(c, id);
    });
    paint();
    foot.append(state, h("span", "wf-ag-spacer"), drop, save);
    box.append(ta, foot);
    return box;
  }

  function partEl(c, aid, p, i) { // 보내는 글의 한 조각 — 차례 · 이름 · 범위 꼬리표 · (펼치면) 안내 글 + 글(읽기만 | 고치기)
    const s = st(c), key = `${aid}|${p.kind}|${p.name || ""}|${i}`, det = h("details", `wf-ag-part wf-ag-k-${p.kind}`), sum = h("summary"), sc = SCOPE[p.kind] || ["", "code"];
    const editing = s.edit && s.edit.key === key;
    det.open = s.seen.has(key) || !!editing;
    if (editing) det.dataset.edit = "1";
    if (p.custom) det.dataset.custom = "1";
    det.addEventListener("toggle", () => { if (det.open) s.seen.add(key); else s.seen.delete(key); });
    sum.append(h("span", "wf-ag-i", String(i + 1)), h("b", "", p.title), tag(sc[0], sc[1]));
    if (p.editable) sum.append(tag(p.custom ? "고침" : "고칠 수 있음", p.custom ? "chg" : "edit"));
    det.append(sum);
    if (p.source) det.append(h("p", "wf-ag-src", `${p.source}${p.text ? ` · ${nf(p.text.length)}자` : ""}`));
    if (p.note) det.append(h("p", "wf-ag-hint", p.note));
    if (!p.text && !p.editable) return det;
    const ta = h("textarea", `wf-ag-text${editing ? "" : " ro"}`);
    ta.readOnly = !editing; ta.spellcheck = false; ta.value = editing ? s.edit.text : p.text; ta.setAttribute("aria-label", p.title);
    ta.rows = Math.max(4, Math.min(18, (ta.value.match(/\n/g) || []).length + 2));
    ta.addEventListener("input", () => { if (s.edit && s.edit.key === key) s.edit.text = ta.value; });
    det.append(ta);
    if (p.editable) {
      const acts = h("div", "wf-ag-acts");
      acts.append(h("span", "wf-ag-state", p.custom ? `내 사본 · 판 ${p.version}` : "기본 글"), h("span", "wf-ag-spacer"));
      if (!editing) acts.append(btn("고치기", () => { s.edit = { key, text: p.text }; s.arm = ""; draw(c, true); }, { title: "이 글을 고칩니다 — 범용 글이라 저장하면 모든 워크플로우에서 다음 실행부터 쓰입니다", disabled: !!s.busy }));
      else acts.append(btn("취소", () => { s.edit = null; draw(c, true); }, { disabled: !!s.busy }), btn("저장", () => partSave(c, aid, p), { cls: "btn sm primary", disabled: !!s.busy }));
      if (p.custom && (p.kind === "heading" || p.builtin)) acts.append(btn(s.arm === key ? "되돌리기 확인" : "기본으로", () => { if (s.arm === key) partReset(c, aid, p); else { s.arm = key; draw(c, true); } },
        { title: "내 사본을 버리고 기본 글로 — 한 번 더 누르면 됩니다", cls: `btn sm${s.arm === key ? " danger" : ""}`, disabled: !!s.busy }));
      det.append(acts);
    }
    return det;
  }

  function agentEl(c, aid) { // 에이전트 하나 — 머리(번호 · 이름 · 모델 · 덧붙이는 글 표시) → 펼치면 역할 · 보내는 글의 차례 · 덧붙이는 글 둘
    const s = st(c), a = agentOf(aid), det = h("details", "wf-ag-agent"), sum = h("summary"), marks = h("span", "wf-ag-marks");
    det.dataset.agent = aid;
    det.open = s.open.has(aid);
    det.addEventListener("toggle", async () => { // 사람이 여닫을 때만(그리면서 맞춘 open 은 지나간다) — 펴면 보내는 글을 읽고 다시 그린다
      if (det.open === s.open.has(aid)) return;
      if (det.open) { s.open.add(aid); if (!A.detail.has(aid)) await detailLoad(aid); } else s.open.delete(aid);
      if (c.ag) draw(c, true); // 그 사이 폼을 다시 그려 열이 새로 섰어도(c.ag 가 새것 — 펼친 것은 이어받는다) 지금 열에 그린다
    });
    marks.dataset.agMarks = aid;
    marks.append(...noteMarks(c, aid));
    sum.append(h("span", "wf-ag-no", a.no || "–"), h("b", "wf-ag-name", a.name), h("span", "wf-ag-model", modelText(a)), marks);
    det.append(sum);
    if (!det.open) return det;
    const body = h("div", "wf-ag-body"), d = A.detail.get(aid), top = h("p", "wf-ag-role", a.role);
    const set = h("a", "wf-ag-link", "에이전트 설정에서 번호 · 역할 · 모델 고치기");
    set.href = `/agents#${encodeURIComponent(aid)}`; set.target = "_blank"; set.rel = "noopener";
    const meta = h("p", "wf-ag-meta");
    meta.append(`${modelText(a)}${a.model ? `(${SOURCE[a.model.source] || a.model.source})` : ""}${a.runText ? ` · ${a.runText}` : ""} · `, set);
    body.append(top, meta);
    body.append(h("h5", "wf-ag-h", "보내는 글의 차례"));
    if (!d) body.append(h("p", "wf-ag-hint", A.detailErr.has(aid) ? `보내는 글을 읽지 못했습니다 — ${A.detailErr.get(aid)}` : "읽는 중…"));
    else {
      // 그 에이전트의 조각 가운데 전제(할 일 프롬프트 · 워크플로우 상세 문서)는 「이 워크플로우의 전제」 한 줄로 · 덧붙이는 글(note)은 아래 두 칸으로
      const parts = d.prompt.filter((p) => !["job", "taskdoc", "note"].includes(p.kind));
      if (d.prompt.some((p) => p.kind === "job")) {
        const at = parts.findIndex((p) => p.kind === "data");
        parts.splice(at < 0 ? parts.length : at, 0, { kind: "job", title: "전제 — 이 워크플로우의 할 일 프롬프트", source: s.ctx.workflow ? "이 폼의 「전제」 칸" : "워크플로우마다", editable: false, text: "",
          note: s.ctx.workflow ? "이 워크플로우의 전제가 한 절로 붙습니다 — 폼 아래 「전제(선택)」 칸에서 고칩니다(비우면 틀이 같은 붙박이 워크플로우의 전제 파일)." : "작업의 워크플로우에 적어 둔 전제가 한 절로 붙습니다." });
      }
      parts.push({ kind: "toolnote", title: "도구에 적어 둔 내용 — 공통 · 이 워크플로우 전용", source: "위의 「이 도구에 적어 두는 내용」 두 칸", editable: false, text: "",
        note: "위의 두 칸에 적은 내용이 이 에이전트의 프롬프트 맨 끝(자료 뒤)에 붙습니다 — 공통 내용 다음에 이 워크플로우 전용 내용(어긋나면 전용이 먼저). 계약(답의 꼴 · 입력에 있는 key 만 고르기)은 바뀌지 않습니다." });
      const list = h("div", "wf-ag-parts");
      parts.forEach((p, i) => list.append(partEl(c, aid, p, i)));
      body.append(list);
    }
    const own = h("details", "wf-ag-own"), osum = h("summary", "", "이 에이전트에만 덧붙이는 글(선택)"), okey = `own|${aid}`; // 더 좁은 층 — 이 에이전트 하나에만(도구의 다른 에이전트에는 안 붙는다)
    own.open = s.seen.has(okey) || !!textOf(c, "all", aid).trim() || !!textOf(c, "job", aid).trim();
    own.addEventListener("toggle", () => { if (own.open) s.seen.add(okey); else s.seen.delete(okey); });
    own.append(osum, h("p", "wf-ag-hint", "도구의 내용은 그 도구가 부르는 에이전트 모두에 붙습니다. 이 에이전트 하나에만 붙일 글은 여기에 적습니다."), noteBox(c, aid, "all"), noteBox(c, aid, "job"));
    body.append(own);
    det.append(body);
    return det;
  }

  function toolsEl(row) { // 그 줄이 쓰는 도구(등록부의 도구 — 스크립트 · 화면: 새 탭으로 그 절)
    if (!row.tools.length) return null;
    const p = h("p", "wf-ag-tools");
    p.append(h("span", "wf-ag-label", "쓰는 도구"));
    for (const t of row.tools) { const a = h("a", "wf-chip wf-ag-tool", t.name); a.href = `/workflow#common-${encodeURIComponent(t.id)}`; a.target = "_blank"; a.rel = "noopener"; a.title = "새 탭에서 이 도구의 절을 엽니다"; p.append(a); }
    return p;
  }
  function usersEl(c, skip) { // 이 틀에서 에이전트를 쓰는 도구들 — 이름을 누르면 그 도구를 고른다
    const s = st(c), list = s.ctx.units().filter((u) => u.key !== skip && rowOf(c, u.key).agents.length), box = h("div", "wf-ag-users");
    if (!list.length) return null;
    box.append(h("h5", "wf-ag-h", "에이전트를 쓰는 도구"));
    const ul = h("ul");
    for (const u of list) {
      const li = h("li"), b = h("button", "wf-ag-user"), ags = rowOf(c, u.key).agents;
      b.type = "button"; b.dataset.agGo = u.key;
      b.append(h("b", "", u.name), h("span", "wf-ag-user-n", `에이전트 ${ags.length}`), h("span", "wf-ag-user-list", ags.map((x) => agentOf(x).name).join(" · ")));
      b.addEventListener("click", () => s.ctx.pick(u.key));
      li.append(b); ul.append(li);
    }
    box.append(ul);
    return box;
  }

  const sig = (c) => [c.help || "", c.key || "", st(c).ctx.family(), A.lines ? 1 : 0, A.notes ? A.notes.version : -1, A.err].join("|");
  function marksSync(c, aid) { const m = st(c).box.querySelector(`[data-ag-marks="${CSS.escape(aid)}"]`); if (m) m.replaceChildren(...noteMarks(c, aid)); railSync(c); }
  function railSync(c) { // 접힌 띠의 글 — 고른 도구의 에이전트 수 · 저장 안 한 글
    const s = st(c), n = rowOf(c, c.help).agents.length, left = [...s.typed.keys()].filter((k) => dirty(c, ...k.split("|")) || (!c.key && isJob(k.split("|")[0]) && s.typed.get(k).trim())).length;
    s.rail.replaceChildren(h("span", "wf-ag-rail-arrow", "«"), h("span", "wf-ag-rail-name", "에이전트"), ...(n ? [h("span", "wf-ag-rail-n", String(n))] : []), ...(left ? [h("span", "wf-ag-rail-dirty", "저장 안 됨")] : []));
    if (n) s.rail.dataset.n = String(n); else delete s.rail.dataset.n;
    if (left) s.rail.dataset.dirty = "1"; else delete s.rail.dataset.dirty;
    s.rail.title = n ? `「에이전트」 열 펴기 — 고른 도구가 쓰는 에이전트 ${n}` : "「에이전트」 열 펴기";
  }
  function redraw(c) { if (c.ag) { c.ag.busy = false; draw(c, true); } } // 기다린 뒤 — 그 사이 폼을 다시 그려 열이 새로 섰어도 지금 열에(펼친 것 · 적던 글은 이어받는다)
  function draw(c, force) {
    const s = st(c);
    if (!s) return;
    const now = sig(c);
    if (!force && now === s.sig) { railSync(c); return; } // 줄을 옮기거나 서버 검사가 돌아와도(helpSync) 고른 것이 그대로면 다시 그리지 않는다 — 적던 글 · 초점이 그대로
    s.sig = now;
    seed(c);
    const body = s.body, keep = body.scrollTop, same = body.dataset.unit === (c.help || ""), a = document.activeElement;
    const focus = a && body.contains(a) ? (a.dataset.agNote ? `[data-ag-note="${CSS.escape(a.dataset.agNote)}"]` : a.dataset.agGo ? `[data-ag-go="${CSS.escape(a.dataset.agGo)}"]` : "") : "", caret = focus && a.selectionStart != null ? [a.selectionStart, a.selectionEnd] : null;
    const u = c.help ? s.ctx.unit(c.help) : null, kids = [];
    if (!same) say(c, ""); // 다른 도구를 고르면 방금의 알림 글은 내린다
    body.dataset.unit = c.help || "";
    if (A.err) kids.push(Object.assign(h("p", "wf-ag-off", A.err), { role: "status" }));
    else if (!A.lines || !A.notes) kids.push(h("p", "wf-ag-hint", "읽는 중…"));
    else if (!u) {
      kids.push(h("p", "wf-ag-hint", "줄(도구) 카드를 누르면 그 도구에 적어 두는 내용 두 칸(「도구 공통」 · 「이 워크플로우 전용」)과, 그 도구가 쓰는 에이전트의 프롬프트 · 스킬 · 도구가 여기에 보입니다."));
      const users = usersEl(c, "");
      if (users) kids.push(users); else kids.push(h("p", "wf-ag-hint", "이 틀에는 에이전트를 쓰는 도구가 없습니다."));
    } else {
      const row = rowOf(c, u.key), head = h("div", "wf-ag-unit"), n = row.agents.length, hand = u.kind === "hand";
      head.append(h("h4", "wf-ag-unit-name", u.name), h("p", "wf-ag-unit-sub", hand ? "사람이 하는 일입니다 — 줄마다 이름과 사람에게 보일 글을 폼에서 적습니다(여기 적어 둘 내용이 없습니다)."
        : n ? `이 도구는 에이전트 ${n}개를 차례대로 부릅니다.` : "이 도구는 에이전트(LLM)를 쓰지 않습니다 — 스크립트나 사람이 합니다."));
      if (u.only && u.only.label) { // 전용 표시(spec_워크플로우 ② §18-17 — 그 도구가 받는 문서: 스크립트가 그 문서만 안다) — 「○○ 전용」 꼬리표 + 까닭(조립 응답 units[].only 그대로)
        const p = h("p", "wf-ag-only");
        p.append(tag(u.only.label, "only"), document.createTextNode(u.only.why ? ` ${u.only.why}` : ""));
        head.append(p);
      }
      kids.push(head);
      if (!hand) { // 도구에 적어 두는 내용 — 공통 · 이 워크플로우 전용(에이전트가 없는 도구에도)
        const sec = h("section", "wf-ag-toolnotes");
        sec.append(h("h5", "wf-ag-h", "이 도구에 적어 두는 내용"), h("p", "wf-ag-hint wf-ag-reader", n
          ? `적은 내용은 이 도구가 부르는 에이전트 ${n}개의 프롬프트 끝에 붙고, 작업 진행 에이전트도 이 단계를 안내할 때 읽습니다.`
          : "이 도구는 스크립트나 사람이 하므로, 적은 내용은 작업 진행 에이전트가 이 단계를 안내 · 제안할 때 읽습니다(스크립트의 동작은 바뀌지 않습니다)."),
          noteBox(c, u.key, "tool"), noteBox(c, u.key, "jobtool"));
        kids.push(sec);
      }
      const tools = toolsEl(row);
      if (tools) kids.push(tools);
      if (n) {
        kids.push(h("h5", "wf-ag-h wf-ag-agents-h", `이 도구가 쓰는 에이전트 ${n} — 이름을 누르면 프롬프트 · 스킬이 펴집니다`));
        const list = h("div", "wf-ag-list");
        for (const aid of row.agents) list.append(agentEl(c, aid));
        kids.push(list);
      } else if (!hand) { const users = usersEl(c, u.key); if (users) kids.push(users); }
    }
    body.replaceChildren(...kids);
    if (focus) { const to = body.querySelector(focus); if (to) { to.focus({ preventScroll: true }); if (caret && to.setSelectionRange) to.setSelectionRange(caret[0], caret[1]); } }
    body.scrollTop = same ? keep : 0;
    s.rewind = !same && !body.getClientRects().length; // 접힌 채 다른 도구를 골랐다 — 감춰진 동안에는 스크롤을 못 올린다(브라우저가 펼 때 전 도구의 자리를 되살린다): 펼 때 맨 위로(sideSet)
    railSync(c);
  }

  // ---- 저장
  function say(c, text, bad) { const s = st(c); if (!s) return; s.said = [text || "", !!bad]; s.msg.textContent = text || ""; s.msg.className = `wf-ag-msg${bad ? " bad" : ""}`; s.msg.hidden = !text; }
  async function noteSave(c, id, scope) { // 적어 둔 글 하나 — 도구 공통 · 도구의 이 워크플로우 전용 · 에이전트(모든 워크플로우 · 이 워크플로우): 전용 범위는 저장된 워크플로우에서만
    const s = st(c), key = typedKey(scope, id), who = isTool(scope) ? unitName(c, id) : agentOf(id).name;
    if (s.busy || !s.typed.has(key) || (isJob(scope) && !jobOf(c))) return;
    s.busy = true;
    let note = null; // [글, 실패인가] — 다시 그린 뒤에 보인다(상태 글과 함께)
    try {
      const got = await call(urlOf(c, scope, id), { method: "PUT", body: JSON.stringify({ text: s.typed.get(key), ...(isJob(scope) ? { job: jobOf(c) } : {}), version: A.notes.version }) });
      s.typed.delete(key);
      A.notes.version = got.version;
      const box = boxOf(scope, jobOf(c), true), k = keyOf(c, scope, id);
      if (got.text) box[k] = got.text; else delete box[k];
      A.detail.clear(); // 보내는 글의 덧붙이는 글 조각도 새로(도구의 글은 그 도구의 에이전트 모두에 닿는다)
      note = [got.text ? `「${who}」 의 ${SCOPE_NAME[scope]} 내용을 저장했습니다 — 다음 실행부터 쓰입니다` : `「${who}」 의 ${SCOPE_NAME[scope]} 내용을 지웠습니다`, false];
    } catch (e) {
      if (e.status === 409) { await load(true); note = ["다른 곳에서 먼저 고쳤습니다 — 다시 읽었습니다. 적은 글은 그대로 두었으니 「저장」 을 다시 누르세요.", true]; }
      else note = [`저장하지 못했습니다 — ${e.message}`, true];
    } finally { s.busy = false; await Promise.all([...s.open].filter((x) => !A.detail.has(x)).map((x) => detailLoad(x))); redraw(c); if (note) say(c, ...note); }
  }
  async function partSave(c, aid, p) { // 범용 글(헤딩 지침 · 스킬) — 그 글의 저장소에(에이전트 설정 페이지와 같은 끝점)
    const s = st(c);
    if (s.busy || !s.edit) return;
    if (!s.edit.text.trim()) { say(c, "빈 글은 저장할 수 없습니다", true); return; }
    s.busy = true;
    let note = null;
    try {
      await call(p.api, { method: "PUT", body: JSON.stringify(p.kind === "skill" ? { name: p.skillName, text: s.edit.text, version: p.version } : { text: s.edit.text, version: p.version, reason: "워크플로우 조립" }) });
      s.edit = null; s.arm = "";
      A.detail.clear(); // 같은 지침을 쓰는 다른 에이전트의 글도 새로
      note = [`「${p.title}」 ${josa(p.title, "을", "를")} 저장했습니다 — 범용 글이라 모든 워크플로우에서 다음 실행부터 이 글로 돕니다`, false];
    } catch (e) { note = [e.status === 409 ? "다른 곳에서 이 글을 먼저 고쳤습니다 — 「취소」 뒤 다시 고쳐 주세요" : `저장하지 못했습니다 — ${e.message}`, true]; }
    finally { s.busy = false; await Promise.all([...s.open].map((x) => detailLoad(x))); redraw(c); if (note) say(c, ...note); }
  }
  async function partReset(c, aid, p) {
    const s = st(c);
    if (s.busy) return;
    s.busy = true;
    let note = null;
    try { await call(p.api, { method: "DELETE" }); s.edit = null; s.arm = ""; A.detail.clear(); note = [`「${p.title}」 ${josa(p.title, "을", "를")} 기본 글로 되돌렸습니다`, false]; }
    catch (e) { note = [`되돌리지 못했습니다 — ${e.message}`, true]; }
    finally { s.busy = false; await Promise.all([...s.open].map((x) => detailLoad(x))); redraw(c); if (note) say(c, ...note); }
  }
  async function flush(c, key) { // 폼의 「저장」 뒤 — 적어 두고 저장 안 한 덧붙이는 글을 함께 저장한다(전용 글은 그 워크플로우의 키로 — 새 워크플로우는 방금 받은 키) → 못 한 것의 글 | ""
    const s = c && st(c);
    if (!s || !s.typed.size) return "";
    await load(true);
    if (!A.notes) return "적어 둔 내용을 저장하지 못했습니다(서버를 읽지 못함)";
    const fails = [];
    for (const [k, text] of [...s.typed]) {
      const [scope, id] = k.split("|"), job = isJob(scope) ? (s.ctx.workflow ? key || c.key : "") : "";
      if (isJob(scope) && !job) continue;
      const old = boxOf(scope, job)[keyOf(c, scope, id)] || "";
      if (text.trim() === old) { s.typed.delete(k); continue; }
      try {
        const got = await call(urlOf(c, scope, id), { method: "PUT", body: JSON.stringify({ text, ...(job ? { job } : {}), version: A.notes.version }) });
        A.notes.version = got.version;
        const box = boxOf(scope, job, true), kk = keyOf(c, scope, id);
        if (got.text) box[kk] = got.text; else delete box[kk];
        s.typed.delete(k);
      } catch (e) { fails.push(`${isTool(scope) ? unitName(c, id) : agentOf(id).name}(${SCOPE_NAME[scope]}): ${e.message}`); }
    }
    A.detail.clear();
    return fails.length ? `적어 둔 내용 ${fails.length}개를 저장하지 못했습니다 — ${fails.join(" / ")}` : "";
  }

  // ---- 열 세우기 · 접기
  function sideSet(c, side) { // 좁은 창에서 펴 둘 열(help | agents) — 넓은 창은 둘 다 펴져 있다
    const s = st(c);
    s.side = side;
    s.cols.dataset.side = side;
    if (side === "agents" && s.rewind) { s.rewind = false; s.body.scrollTop = 0; } // 접힌 동안 고른 도구가 바뀌었다 — 그 도구의 맨 위부터
    s.fold.textContent = "»";
    s.fold.title = "「에이전트」 열 접기 — 「도구 설명」 을 폅니다";
  }
  function mount(cols, c, sec, ctx) { // helpWrap 끝 — 설명 열 옆에 「에이전트」 열을 세운다
    if (!cols || !c || !ctx) return;
    const old = c.ag, aside = h("aside", "wf-agents"), head = h("div", "wf-ag-head"), body = h("div", "wf-ag-main"), msg = h("p", "wf-ag-msg"), rail = h("button", "wf-ag-rail"), fold = h("button", "wf-ag-fold");
    aside.setAttribute("aria-label", "에이전트 — 스킬 · 도구 · 프롬프트");
    c.ag = { box: aside, body, msg, rail, fold, cols, ctx, sig: null, busy: false, arm: "", edit: old ? old.edit : null, seeded: old ? old.seeded : false,
      open: old ? old.open : new Set(), seen: old ? old.seen : new Set(), typed: old ? old.typed : new Map(), side: old ? old.side : "help" }; // 폼을 다시 그려도(저장 실패 · 검사) 펼친 것 · 적던 글은 그대로
    rail.type = "button"; fold.type = "button"; msg.hidden = true; msg.setAttribute("role", "status");
    if (old && old.body) body.dataset.unit = old.body.dataset.unit || ""; // 다시 선 열 — 같은 도구를 보고 있으면 방금의 알림 글을 내리지 않는다
    rail.addEventListener("click", () => sideSet(c, "agents"));
    fold.addEventListener("click", () => sideSet(c, "help"));
    fold.setAttribute("aria-label", "에이전트 열 접기");
    head.append(h("h3", "", "에이전트"), h("span", "wf-ag-head-sub", "스킬 · 도구 · 프롬프트"), h("span", "wf-ag-spacer"), fold);
    aside.append(rail, head, msg, body);
    cols.classList.add("wf-cols-ag");
    if (sec) sec.classList.add("wf-wider"); // 넓은 절(세 칸) — wf-wide 가 떼지면 함께 풀린다(CSS 가 둘을 같이 볼 때만)
    cols.append(aside);
    sideSet(c, c.ag.side);
    if (old && old.said && old.said[0]) say(c, old.said[0], old.said[1]); // 방금의 알림 글도 이어받는다
    if (c.helpBox) c.helpBox.addEventListener("click", () => { if (cols.dataset.side === "agents" && !matchMedia(WIDE).matches) sideSet(c, "help"); }); // 접힌 「도구 설명」 띠를 누르면 편다
    if (c.linesBox && !c.linesBox.dataset.agHook) { // 카드의 LLM 꼬리표를 누르면 이 열을 편다(고르는 것은 「도구 설명」 의 누름이 한다 — 같은 고름)
      c.linesBox.dataset.agHook = "1";
      c.linesBox.addEventListener("click", (e) => { if (c.ag && e.target.closest(".wf-tag.wf-t-llm") && e.target.closest(".wf-line-cell")) sideSet(c, "agents"); });
    }
    load(true).then(() => { if (c.ag && c.ag.box === aside) draw(c, true); });
    draw(c, true);
  }
  function sync(c) { if (c && c.ag) draw(c, false); } // helpSync 끝 — 고른 도구가 바뀌었으면 다시 그린다

  window.WfAgents = { mount, sync, flush };
})();
