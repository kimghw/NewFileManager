// TASK 워크플로우 페이지(spec_워크플로우 ② §3·§7) — GET /api/workflow 등록부를 다이어그램(기본)·목록으로 그린다. 읽기만 한다(실행·진행 상태 없음).
// TASK 이름·한 줄 설명 = TASK_CATALOG · 이관·취합의 「N단계 이름」 = TASK_STAGE_META(task_catalog.js — 이 파일보다 먼저 읽힌다: 원본 하나).
// 절의 id: 전체 보기 `overview` · TASK `<job>`(묶음 `<job>--<묶음 id>`) · 단계 · 도구 `common-<id>` — 주소의 # 로 바로 열린다.
// 화면 말(2026-11-19 사용자 "모듈이라고 하지 말고 공통 모듈을 도구라고 하자"): 등록부의 COMMON = **「도구」**(전의 「공통 모듈」) · 그 가운데 kind "stage" = **「단계」**(TASK 가 조립하는 일반 단계) · 코드 파일(app/<이름>.py) = 「코드」.
// TASK 조립(spec_워크플로우 ② §14 — 같은 날 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」): 전체 보기 아래 「TASK 조립」 절에서 단계를 골라 TASK 를 만든다 — 저장은 서버(/api/tasks), 읽기 전용이던 이 페이지에서 고치는 것은 그것 하나다.
// 문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 같은 날 사용자 "각문서에 대한걸 단위문서 task 라고 하고 전체를 워크플로우라"): TASK 절의 「문서마다 단위문서 TASK」 표
// (등록부의 roles — 원본 → 목적 · 열 머리 = 역할의 title — 문서 이름 · 표 아래 = 워크플로우 전체(문서마다가 아니라 한 번)의 단계 flow 와 구성의 기준 base — null 이면 적지 않는다) · 단계 세부의 「하는 문서」(서버의 onText 그대로 — 화면이 셈하지 않는다) ·
// 조립 폼의 문서 역할 × 단계 표(GET /api/tasks 의 stages[].cells — 없으면 폼을 열지 않는다 · 저장 몸 = assign 만). 여러 문서 쪽은 「원본 문서」(「취합 대상」 은 쓰지 않는다).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const CAT = typeof TASK_CATALOG === "undefined" ? {} : TASK_CATALOG, META = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META;
  const josa = (word, a, b) => (typeof taskJosa === "function" ? taskJosa(word, a, b) : a); // 이름 뒤 조사(task_catalog.js taskJosa — 받침이 있으면 a · 없으면 b) · 없으면 옛 글 그대로(a)
  const MODEL = { "claude-fable-5-2": "Fable 5.2", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5" }; // 에이전트 설정 페이지(agents.js MODEL)와 같은 이름
  const SOURCE = { user: "에이전트 설정에서 정함", pin: "이 에이전트에 고정", force: "서버 전체 설정", code: "코드가 정함", default: "서버 기본" };
  const CHANGE = { none: "안 바뀜", doc: "바뀜", store: "안 바뀜 — 결과만 저장" }; // 펼친 세부의 「문서」 줄
  const taskName = (job) => (CAT[job] || {}).name || ((D && D.tasks.find((t) => t.job === job)) || {}).name || job; // 조립한 TASK 의 이름은 등록부(서버 저장소)에도 있다
  // 워크플로우의 한 줄 설명 — 사람이 적은 글 → (조립한 것) 등록부가 실제 배정에서 지은 글 descAuto(「내용 넣기」 가 없으면 「옮깁니다」 라 하지 않는다 — 등록부 · GET /api/tasks 어느 쪽에 있든) →
  // 화면 목록(TASK_CATALOG)의 글(붙박이 · descAuto 를 안 주는 옛 서버)
  const descOf = (t) => {
    const s = (x) => (typeof x === "string" ? x.trim() : ""), v = t.custom && T && Array.isArray(T.tasks) ? T.tasks.find((x) => x.key === t.job) : null;
    return s(t.desc) || s(v && v.desc) || (t.custom ? s(t.descAuto) || s(v && v.descAuto) : "") || s((CAT[t.job] || {}).desc);
  };
  const stageLabel =(g) => (g.meta && META[g.meta] ? { no: META[g.meta].no, name: META[g.meta].name } : { no: g.no || "", name: g.name });
  // 문서 역할 — 등록부 roles[{role, title, name, kind, many, unit[{stage, steps[key…]}]}](title = 역할의 화면 이름: 문서 여럿 = 원본 문서 · 목적 문서 / 문서 하나 = 작업 문서 · 서식을 가져올 문서) ·
  // 워크플로우의 flow[{stage, steps[key…]}](워크플로우 전체 — 문서마다가 아니라 한 번: 어느 역할의 unit 에도 안 듦) · base(구성의 기준 역할 | null — 조립한 것은 목적 문서에 「구성 맞추기」 가 있을 때만 source) · 단계의 onText(하는 문서 한 줄 — 서버가 만든 글 그대로 · 비면 줄 없음)
  const ROLES = ["source", "target"], ROLE = { source: "원본 문서", target: "목적 문서" }; // ROLE = title 이 없는 옛 서버 · 조립 폼(이관형 — 원본 · 목적)의 이름
  const roleOf = (roles, role) => (roles || []).find((r) => r.role === role) || null;
  const rolesSorted = (roles) => [...(roles || [])].sort((a, b) => ROLES.indexOf(a.role) - ROLES.indexOf(b.role)); // 차례 원본 → 목적
  const roleTitle = (r) => r.title || ROLE[r.role] || r.role;
  const FLOW_HEAD = "워크플로우 전체(문서마다가 아니라 한 번)"; // 표 아래 줄의 머리 — 만든 글(workflow.md · tasks/<job>.md)의 그 줄과 같은 글(전의 「프로젝트에 한 번」 은 라운드마다 하는 준비와 맞지 않아 바꿈)
  const WF_ICONS = { // 꼬리표 아이콘(사람 · 스크립트 · LLM · 문서 바뀜 — doc_agent.js agentIcon 과 같은 경로: 2026-11-18 사용자)
    script: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 6l-3 12"/>',
    llm: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z"/><path d="M18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8Z"/>',
    human: '<circle cx="12" cy="8" r="3.5"/><path d="M5.5 19.5a6.5 6.5 0 0 1 13 0"/>',
    doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h5"/><path d="M14 3v5h5M8 12h5M8 16h3"/><path d="m14.5 19.5 5-5 1.8 1.8-5 5H14.5v-1.8Z"/>',
  };
  const WF_ICON_BY_TEXT = { "스크립트": "script", LLM: "llm", "사람": "human", "문서 바뀜": "doc" };
  function wfIcon(name) {
    const icon = h("span", "wf-icon");
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${WF_ICONS[name] || WF_ICONS.script}</svg>`;
    return icon;
  }
  function tag(text, kind, icon = WF_ICON_BY_TEXT[text]) { // kind = llm · human · doc · soft · must(클래스는 모두 wf- 로 — style.css 의 .doc 등과 안 겹치게). 넷은 아이콘 + .sr-only 글
    if (!icon || !WF_ICONS[icon]) return h("span", "wf-tag" + (kind ? " wf-t-" + kind : ""), text);
    const e = h("span", "wf-tag" + (kind ? " wf-t-" + kind : ""));
    e.title = text;
    e.append(wfIcon(icon), h("span", "sr-only", text));
    return e;
  }
  const link = (href, text, cls) => { const a = h("a", cls || "", text); a.href = href; return a; };
  const plain = (s) => String(s || "").replace(/\*\*|`/g, ""); // 모듈 설명 첫 줄의 마크다운 표시는 뺀다
  let D = null; // 읽은 워크플로우
  let view = "diagram", current = "overview";
  const routes = new Map(); // 목록과 다이어그램이 같은 등록부·주소를 쓴다.

  function indexRoutes() {
    routes.clear();
    for (const item of [...D.tasks, ...D.common]) {
      const id = item.job || `common-${item.id}`, groups = item.stages || [{ id: "", name: item.name, steps: item.steps }];
      const flow = { id, item, groups, steps: [] };
      groups.forEach((g, gi) => g.steps.forEach((s) => {
        const path = [id, g.id, s.key].filter(Boolean).join("--");
        flow.steps.push({ s, gi, path });
      }));
      routes.set(id, { flow, index: 0 });
      groups.forEach((g, gi) => {
        if (g.id) routes.set(`${id}--${g.id}`, { flow, index: Math.max(0, flow.steps.findIndex((s) => s.gi === gi)) });
      });
      flow.steps.forEach((step, index) => routes.set(step.path, { flow, index }));
    }
  }

  const must = (s) => !s.optional && !s.soon && !s.auto; // 「필수」 — 선택 · 자동 · 준비 중이 아닌 단계(2026-11-18 사용자 「꼭 해야하는건 필수 라고 적어줘」 · dashboard.js dashTags · app/workflow.py step() 과 같은 셈)

  function promptTag(s, item) {
    return workflowPromptButton({ job: item.job || "", template: item.family || "", step: s.key, agents: s.agents,
      title: s.name, doclib: item.id === "doclib" || (s.uses || []).includes("doclib") && !s.agents.length },
      wfIcon("llm"), "wf-tag wf-t-llm");
  }
  function badges(s, item, separatePrompt = false) {
    const box = h("div", "wf-badges");
    for (const b of s.by) {
      if (b === "llm" && separatePrompt) continue;
      box.append(b === "llm" ? promptTag(s, item) : tag(D.by[b] || b, b === "script" ? "" : b, b));
    }
    if (s.auto) box.append(tag("자동", "soft"));
    if (must(s)) box.append(tag("필수", "must"));
    if (s.optional) box.append(tag("선택", "soft"));
    if (s.soon) box.append(tag("준비 중", "soft"));
    return box;
  }

  function drawDiagram(route) {
    const { flow, index } = route, { item, groups, steps } = flow, selected = steps[index];
    const diagram = $("wfDiagram"), title = item.job ? taskName(item.job) : item.name;
    const head = h("div", "wf-diagram-head"), heading = h("div");
    heading.append(h("p", "wf-eyebrow", item.job ? "워크플로우 / 순서 살펴보기" : item.kind === "stage" ? "단계 / 순서 살펴보기" : "도구 / 순서 살펴보기"), h("h2", "", title));
    head.append(heading, link("#overview", "전체 흐름 보기 ↗", "wf-back"));
    const lead = h("p", "wf-lead", item.job ? descOf(item) : item.does);
    const context = h("details", "wf-context"), info = h("dl", "wf-io"), docs = item.job ? docsEl(item) : null; // 문서마다 단위문서 TASK — 받는 문서 · 산출물 줄 아래(목록 보기의 TASK 절과 같은 표)
    context.append(h("summary", "", item.job ? (docs ? "입력·산출물 · 전제 · 문서마다 단위문서 TASK 보기" : "입력·산출물과 전제 보기") : "여는 곳 · 쓰는 워크플로우 보기"));
    if (item.job) {
      row(info, "받는 문서", item.inputs);
      if (!item.soon) row(info, "문서 칸", slotEl(item)); // 목록 보기의 워크플로우 절과 같은 줄(목적 문서 칸의 양식 설정)
      row(info, "산출물", item.output);
      if (item.note) row(info, "알아 둘 것", item.note);
      if (item.prompt) row(info, "전제", h("code", "", item.prompt));
    } else {
      row(info, "여는 곳", item.where);
      const related = h("div", "wf-links");
      for (const job of item.usedBy) related.append(link(`#${job}`, taskName(job), "wf-chip"));
      row(info, item.kind === "stage" ? "조립한 워크플로우" : "쓰는 워크플로우", item.usedBy.length ? related : item.kind === "stage" ? "아직 이 단계를 조립한 워크플로우가 없습니다." : "어느 워크플로우의 문서에서나 엽니다.");
    }
    context.append(info);
    if (docs) context.append(docs);
    diagram.replaceChildren(head, lead, context);
    if (item.job && (item.entry || []).length) { // 시작 점검(② §10) — 접어 두고, 펴면 때마다 묶음이 열린 채로
      const ent = h("details", "wf-context wf-entry-context"), note = h("p", "wf-entry-doc", "이 워크플로우의 세부(시작 점검 · 단계마다 조건)는 워크플로우 상세 문서 ");
      ent.append(h("summary", "", `시작 점검 — 시작할 때 저절로 확인하는 것 ${entryCount(item)}가지 보기`));
      note.append(h("code", "", item.doc), document.createTextNode(" 에도 같은 글로 있습니다."));
      if (item.doc) ent.append(note); // 조립한 워크플로우는 그 파일이 없다(doc "" — 시작 점검은 등록부가 그 정의로 바로 짓는다: spec_워크플로우 ② §15 「에이전트 · 만든 글」) — 빈 경로를 적지 않는다
      ent.append(entryEl(item, true));
      diagram.append(ent);
    }
    if (!selected) {
      const empty = h("div", "wf-empty");
      empty.append(tag("준비 중", "soft"), h("h3", "", "아직 등록된 단계가 없습니다"), h("p", "", "이 워크플로우의 과정이 준비되면 순서대로 확인할 수 있습니다."), link("#overview", "다른 워크플로우 살펴보기", "wf-chip"));
      diagram.append(empty);
      return;
    }

    // 흐름(왼쪽) — **모든 묶음의 단계를 한 번에**(spec_워크플로우 ② §7 — 2026-11-16 사용자 「여기서 모든 단계를 한번에 나타내도 될거 같은데」: 전에는 위의 가로 묶음 줄에서 고른 묶음의 단계만 보였다).
    // TASK = 묶음 머리(번호 · 이름 · 단계 수 — 누르면 그 묶음의 첫 단계) 아래 그 묶음의 단계, 번호는 TASK 전체로 이어 센다 · 공통 모듈 = 단계만. 위의 가로 묶음 줄은 없앴다(같은 것을 두 곳에 두지 않는다).
    const board = h("div", "wf-board"), map = h("div", "wf-map");
    const mapHead = h("div", "wf-map-head");
    mapHead.append(h("h3", "", "단계 흐름"), h("p", "", item.job ? `묶음 ${groups.length}개 · 단계 ${steps.length}개 — 번호를 따라 선택해 보세요` : "번호를 따라 선택해 보세요"));
    const node = ({ s, path }, i) => {
      const li = h("li"), a = link(`#${path}`, "", "wf-node" + (s.soon ? " wf-soon" : "") + (s.optional ? " wf-optional" : ""));
      a.dataset.wfFocus = `node-${i}`;
      a.setAttribute("aria-controls", "wfDetail");
      a.setAttribute("aria-label", `${i + 1}. ${s.name}`);
      if (i === index) a.setAttribute("aria-current", "step");
      const body = h("div", "wf-node-body"), meta = badges(s, item, true);
      if (s.change === "doc") meta.append(tag("문서 바뀜", "doc"));
      body.append(h("b", "", s.name), meta);
      a.append(h("span", "wf-node-no", String(i + 1).padStart(2, "0")), body);
      li.append(a);
      if (s.by.includes("llm")) {
        li.classList.add("wf-prompt-node");
        li.append(promptTag(s, item));
      }
      return li;
    };
    let nodes;
    if (item.job) {
      nodes = h("ol", "wf-groups");
      nodes.setAttribute("aria-label", "워크플로우 단계 묶음과 단계");
      groups.forEach((g, gi) => {
        const li = h("li"), a = link(`#${flow.id}--${g.id}`, "", "wf-stage-link"), label = stageLabel(g), ol = h("ol", "wf-flow");
        a.dataset.wfFocus = `stage-${gi}`;
        if (gi === selected.gi) a.setAttribute("aria-current", "step");
        a.append(h("span", "wf-stage-index", label.no || String(gi + 1)), h("b", "", label.name), h("small", "", `${g.steps.length}개 단계`));
        ol.setAttribute("aria-label", `${label.name}의 단계`);
        steps.forEach((st, i) => { if (st.gi === gi) ol.append(node(st, i)); });
        li.append(a, ol); nodes.append(li);
      });
    } else {
      nodes = h("ol", "wf-flow");
      nodes.setAttribute("aria-label", "순서대로 확인할 단계");
      steps.forEach((st, i) => nodes.append(node(st, i)));
    }
    map.append(mapHead, nodes, h("p", "wf-map-note", "점선 단계는 선택 사항입니다. 준비 중인 단계는 실행할 수 없습니다."));

    const detail = h("section", "wf-detail"); detail.id = "wfDetail";
    detail.setAttribute("aria-labelledby", "wfDetailTitle");
    const readHead = h("div", "wf-read-head"), position = h("span", "wf-position", `단계 ${index + 1} / ${steps.length}`);
    position.id = "wfPosition"; position.setAttribute("role", "status");
    readHead.append(h("span", "wf-eyebrow", "지금 확인하는 단계"), position);
    const name = h("h3", "", selected.s.name); name.id = "wfDetailTitle"; name.tabIndex = -1;
    detail.append(readHead, name, badges(selected.s, item));
    const onDoc = item.job ? selected.s.onText || "" : ""; // 이 단계가 하는 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 서버의 onText 그대로(비면 줄 없음: 문서 하나인 워크플로우 · 도구의 단계 · 옛 서버)
    if (onDoc) { const p = h("p", "wf-ondoc"); p.append(h("span", "", "하는 문서"), h("strong", "", onDoc)); detail.append(p); }
    const description = h("div", "wf-explain");
    description.append(h("h4", "", "이 단계에서 하는 일"), h("p", "", selected.s.does));
    detail.append(description);
    if (selected.s.out) {
      const result = h("div", "wf-result");
      result.append(h("h4", "", "나오는 것"), h("p", "", selected.s.out)); detail.append(result);
    }
    const cond = condEl(selected.s); // 단계마다 조건(② §10) — TASK 의 단계에만 있다
    if (cond) { const box = h("div", "wf-conds"); box.append(h("h4", "", "이 단계의 조건"), cond); detail.append(box); }
    const impact = h("div", "wf-impact" + (selected.s.change === "doc" ? " wf-impact-doc" : ""));
    impact.append(h("span", "", "문서 변경"), h("strong", "", CHANGE[selected.s.change] || selected.s.change));
    detail.append(impact);
    if (selected.s.soon) detail.append(h("p", "wf-pending", "준비 중인 단계입니다. 현재 사용할 수 있는 기능은 아닙니다."));
    if (selected.s.uses.length) {
      const related = h("div", "wf-related"), links = h("div", "wf-links");
      related.append(h("h4", "", "연결된 도구"));
      for (const id of selected.s.uses) { const c = D.common.find((x) => x.id === id); links.append(link(`#common-${id}`, c ? c.name : id, "wf-chip")); }
      related.append(links); detail.append(related);
    }
    // 기존 상세 렌더러를 재사용하되 기술 정보만 접어 둔다.
    const technical = stepEl(selected.s).querySelector(".wf-more");
    for (const dt of [...technical.querySelectorAll("dt")]) if (!["에이전트", "코드", "사양"].includes(dt.textContent)) { dt.nextElementSibling.remove(); dt.remove(); }
    if (technical.childElementCount) {
      const tech = h("details", "wf-tech");
      tech.append(h("summary", "", "기술 상세 · 에이전트 / 코드 / 사양"), technical); detail.append(tech);
    }
    const controls = h("div", "wf-reader-controls");
    for (const [id, text, to] of [["wfPrev", "← 이전", index - 1], ["wfNext", "다음 →", index + 1]]) {
      const b = h("button", "btn" + (id === "wfNext" ? " wf-primary" : ""), text);
      b.type = "button"; b.id = id; b.dataset.wfFocus = id; b.disabled = to < 0 || to >= steps.length;
      b.addEventListener("click", () => navigate(`#${steps[to].path}`));
      controls.append(b);
    }
    detail.append(controls, h("p", "wf-reading-note", item.job ? "순서를 살펴보는 화면입니다. 실제 진행 상태를 보고 단계를 실행하려면 문서를 연 뒤 패널 「대시보드」 에서 합니다." : "순서를 살펴보는 화면입니다. 실제 작업 진행 상태와는 별개입니다.")); // 대시보드 = 같은 흐름의 진행판(spec_작업에이전트 ② §9)
    board.append(map, detail); diagram.append(board);
  }

  function row(dl, name, value) { // 세부 한 줄(dt · dd) — value 는 글이나 노드(들)
    const dd = h("dd");
    if (typeof value === "string") dd.textContent = value; else dd.append(...[].concat(value));
    dl.append(h("dt", "", name), dd);
  }

  function condEl(s) { // 단계마다 조건(spec_워크플로우 ② §10) — 하려면 · 끝난 것으로 보는 때 · 멈추는 때 · 남기는 것 · 보정: 등록부에 적힌 것만(공통 모듈의 단계는 없음) → dl | null
    if (!(s.cond || []).length) return null;
    const dl = h("dl", "wf-cond");
    dl.setAttribute("aria-label", "이 단계의 조건");
    for (const c of s.cond) dl.append(h("dt", "", c.name), h("dd", "", c.text));
    return dl;
  }

  // 시작 점검에 소개된 동작과 같은 실행 단계를 찾는다. 에이전트 · 도구 지침은 그 단계의 등록부가 정한다.
  const entryCommonSteps = { import: ["intake", "import"], agent: ["agent", "guide"], llm: ["intake", "llm"],
    divisionLlm: ["intake", "division"], zonesLlm: ["zones", "llm"] };
  const entryTaskSteps = { extractRun: ["extract"], writeRun: ["ask"], reviewRun: ["review", "plan"], review: ["review"] };
  const entryFamilySteps = { relay: ["llm", "tableMap", "gaps"], gather: ["llm"], single: ["headsLlm", "tablesLlm"] };
  function entryPrompt(c, t) {
    const common = entryCommonSteps[c.key];
    if (common) {
      const step = D.common.find(m => m.id === common[0]).steps.find(s => s.key === common[1]);
      return promptTag({ ...step, name: c.name }, t);
    }
    const keys = (c.key === "taskLlm" ? entryFamilySteps[t.family] : entryTaskSteps[c.key]) || [];
    const steps = t.stages.flatMap(g => g.steps).filter(s => keys.includes(s.key));
    if (!steps.length) return null;
    if (steps.length === 1) return promptTag({ ...steps[0], name: c.name }, t);
    const agents = [...new Map(steps.flatMap(s => s.agents).map(a => [a.id, a])).values()];
    return workflowPromptButton({ job: t.job, template: t.family, steps: steps.map(s => s.key), agents, title: c.name },
      wfIcon("llm"), "wf-tag wf-t-llm");
  }
  function entryEl(t, open) { // 시작 점검(② §10) — 시작할 때 저절로 확인하는 것: 때마다 묶음(접힘) › 항목(이름 · 누가 · 무엇을 확인하나 · 안 맞으면)
    const box = h("div", "wf-entry");
    box.setAttribute("aria-label", "시작 점검");
    for (const g of t.entry) {
      const d = h("details", "wf-entry-group"), sum = h("summary"), ul = h("ul", "wf-entry-items");
      d.dataset.when = g.when;
      d.open = !!open;
      const chev = h("span", "wf-chev");
      chev.setAttribute("aria-hidden", "true");
      sum.append(h("b", "", g.name), h("span", "wf-muted", `${g.items.length}가지`), chev); // 펴고 접는 표시 — 단계 줄과 같은 꺾쇠
      for (const c of g.items) {
        const li = h("li"), line = h("div", "wf-line1");
        li.dataset.entry = c.key;
        line.append(h("span", "wf-name", c.name));
        for (const b of c.by) {
          const mark = b === "llm" ? entryPrompt(c, t) : tag(D.by[b] || b, b === "script" ? "" : b);
          if (mark) line.append(mark);
        }
        li.append(line, h("p", "wf-does", c.does));
        if (c.miss) { const p = h("p", "wf-miss"); p.append(h("b", "", "안 맞으면"), document.createTextNode(" " + c.miss)); li.append(p); }
        ul.append(li);
      }
      d.append(sum, h("p", "wf-entry-note", g.note), ul);
      box.append(d);
    }
    return box;
  }
  const entryCount = (t) => (t.entry || []).reduce((n, g) => n + (g.when === "manual" ? 0 : g.items.length), 0); // 저절로 확인하는 것의 수(「저절로 돌지 않는 것」 은 빼고 센다)

  function stepEl(s) { // 단계 한 줄 — 이름 · 누가 · 문서 바뀜 · 하는 일은 늘 보이고, 누르면 세부(조건 · 하는 문서 · 나오는 것 · 도구 · 에이전트 · 코드 · 사양 자리)
    const d = h("details", "wf-step" + (s.soon ? " wf-soon" : "")), sum = h("summary"), main = h("div"), line = h("div", "wf-line1");
    d.dataset.step = s.key;
    const nm = h("span", "wf-name", s.name);
    if (s.baseName) nm.title = `기본 이름 「${s.baseName}」 — 조립 화면의 「도구 설명」 에서 고친 이름입니다`; // 사람이 이름을 고친 도구(② §18-19) — 가리키면 기본 이름
    line.append(nm);
    for (const b of s.by) if (b !== "llm") line.append(tag(D.by[b] || b, b === "script" ? "" : b, b));
    if (s.change === "doc") line.append(tag(D.change.doc, "doc", "doc"));
    if (s.auto) line.append(tag("자동", "soft"));
    if (must(s)) line.append(tag("필수", "must"));
    if (s.optional) line.append(tag("선택", "soft"));
    if (s.soon) line.append(tag("준비 중", "soft"));
    main.append(line, h("p", "wf-does", s.does));
    const chev = h("span", "wf-chev");
    chev.setAttribute("aria-hidden", "true");
    sum.append(h("span", "wf-no" + (s.no ? "" : " wf-none"), s.no || ""), main, chev);
    const more = h("dl", "wf-more"), onDoc = s.onText || "";
    if (onDoc) row(more, "하는 문서", onDoc); // 이 단계가 하는 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 서버의 onText 그대로(원본 문서 · 목적 문서 · 두 문서 · 원본 → 목적 · 워크플로우 전체)
    if (s.out) row(more, "나오는 것", s.out);
    row(more, "문서", CHANGE[s.change] || s.change);
    if (s.uses.length) {
      const box = h("div", "wf-links");
      for (const u of s.uses) { const c = D.common.find((x) => x.id === u); box.append(link(`#common-${u}`, c ? c.name : u, "wf-chip")); }
      row(more, "도구", box);
    }
    if (s.agents.length) row(more, "에이전트", s.agents.map((a) => {
      const box = h("div", "wf-agent"), head = h("div", "wf-agent-head");
      box.dataset.agent = a.id;
      if (a.no) head.append(h("span", "wf-ano", a.no));
      if (a.group) { const nm = link(`/agents#${encodeURIComponent(a.id)}`, a.name, "wf-agent-link"); nm.title = "에이전트 설정에서 이 에이전트 보기 — 작업 번호 · 역할 · 모델 · 프롬프트"; head.append(nm); } // 등록부에 있는 에이전트 → 에이전트 설정 페이지(spec_에이전트 ② §5)
      else head.append(h("b", "", a.name));
      if (a.model) head.append(tag(MODEL[a.model.id] || a.model.id, "llm"), h("span", "wf-muted", [SOURCE[a.model.source], a.run].filter(Boolean).join(" · ")));
      box.append(head);
      if (a.role) box.append(h("p", "wf-role", a.role));
      return box;
    }));
    if (s.modules.length) row(more, "코드", s.modules.map((m) => {
      const box = h("div", "wf-mod");
      box.append(h("code", "", m.path || m.name));
      if (m.doc) box.append(h("span", "", " " + plain(m.doc)));
      return box;
    }));
    if (s.spec) { const c = h("code", "", s.spec.file); row(more, "사양", [c, document.createTextNode(" " + s.spec.at)]); }
    const cond = condEl(s);
    d.append(sum, ...(cond ? [cond] : []), more); // 조건은 세부(.wf-more) 앞에 따로 — 이름표가 길어 칸 폭이 다르다
    return d;
  }

  function stepsEl(steps, prefix, item) {
    const ol = h("ol", "wf-steps");
    for (const s of steps) {
      const li = h("li"), step = stepEl(s);
      if (prefix) step.dataset.wfPath = `${prefix}--${s.key}`;
      li.append(step);
      if (s.by.includes("llm")) {
        li.classList.add("wf-prompt-step");
        li.append(promptTag(s, item));
      }
      ol.append(li);
    }
    return ol;
  }

  const stageLink = (t, g) => { // 묶음 이름(「1단계 문서 검토」 — 누르면 그 묶음으로): 단위문서 TASK 표의 행 머리 · 워크플로우 전체 줄이 같이 쓴다
    const L = stageLabel(g), a = link(`#${t.job}--${g.id}`, "", "wf-docs-stage");
    if (L.no) a.append(h("b", "", L.no), document.createTextNode(" "));
    a.append(document.createTextNode(L.name));
    return a;
  };
  const stepLink = (t, g, s) => { // 단계 이름(누르면 그 단계로) — 선택 단계는 점선 밑줄 · 준비 중은 흐리게
    const a = link(`#${t.job}--${g.id}--${s.key}`, s.name, "wf-docs-step" + (s.optional ? " wf-optional" : "") + (s.soon ? " wf-soon" : ""));
    if (s.soon || s.optional) a.title = s.soon ? "준비 중인 단계" : "선택 단계";
    return a;
  };

  function flowEl(t, roles) { // 워크플로우 전체(문서마다가 아니라 한 번)의 단계 한 줄 — 등록부의 flow[{stage, steps}](준비 · 구성 불러오기 · 프로젝트 구성 추출: 어느 문서의 단위문서 TASK 에도 안 듦) + 구성의 기준(base 역할) | null(없음 · 옛 서버)
    // 꼴 = 「<번호> <이름>(<단계> › <단계>)」 · 묶음 사이도 「 › 」(= 다음 — 둘 다 CSS: 표 칸 안의 단계 이음과 같은 기호) — 만든 글의 그 줄과 같은 뜻이다(만든 글은 단계 이름을 「」 로 감싸고, 화면은 단계 이름이 링크라 감싸지 않는다).
    // 단계 이름 안의 「 · 」(「헤딩 · 표 분석」)와 헷갈리지 않게 단계 사이에 「 · 」 를 쓰지 않는다 · 괄호가 묶음 이름과 단계 이름을 가른다(전에는 「1단계 문서 검토 준비」 가 한 말로 읽혔다)
    const groups = (t.flow || []).map((f) => ({ g: t.stages.find((x) => x.id === f.stage), keys: f.steps || [] })).filter((x) => x.g && x.keys.length);
    if (!groups.length) return null;
    const p = h("p", "wf-docs-flow");
    p.append(h("b", "", FLOW_HEAD), document.createTextNode(": "));
    for (const { g, keys } of groups) { // 묶음마다 — 묶음 이름 + 괄호 안에 그 묶음의 단계(차례대로 ›)
      const span = h("span", "wf-docs-flow-group"), ol = h("ol", "wf-docs-steps");
      span.dataset.stage = g.id;
      for (const k of keys) { const li = h("li"); li.append(stepLink(t, g, g.steps.find((x) => x.key === k) || { key: k, name: k })); ol.append(li); }
      span.append(stageLink(t, g), document.createTextNode("("), ol, document.createTextNode(")"));
      p.append(span);
    }
    const base = roleOf(roles, t.base); // 구성의 기준 문서 — null(조립한 워크플로우의 목적 문서에 「구성 맞추기」 가 없음 · 문서 하나인 워크플로우)이면 적지 않는다
    if (base) { const b = h("span", "wf-docs-base", ` — 구성의 기준: ${roleTitle(base)}(${base.name})`); b.dataset.role = base.role; p.append(b); }
    return p;
  }

  function docsEl(t) { // 문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 열 = 문서 역할(원본 → 목적 · 머리 「<title> — <문서 이름>」) · 행 = 단계 묶음 · 칸 = 그 문서에 하는 단계(누르면 그 단계로) ·
    // 표 아래 = 워크플로우 전체(문서마다가 아니라 한 번)의 단계와 구성의 기준(flowEl) | null(옛 서버 — roles 없음)
    const roles = rolesSorted(t.roles);
    if (!roles.length) return null;
    const box = h("div", "wf-docs-box"), head = h("h3", "wf-docs-head", "문서마다 단위문서 TASK"), flow = flowEl(t, roles);
    box.append(head);
    if (roles.length === 1) { // 문서 하나 — 이 워크플로우가 곧 그 문서의 단위문서 TASK(역할의 이름 = 작업 문서 · 서식을 가져올 문서 …: 서버의 title)
      const p = h("p", "wf-docs-one"), r = roles[0];
      p.append(h("b", "", "문서 하나"), document.createTextNode(" — 이 워크플로우가 그 문서의 단위문서 TASK 입니다"));
      if (r.name) p.append(h("span", "wf-muted", ` · ${roleTitle(r)} — ${r.name}`));
      box.append(p, ...(flow ? [flow] : []));
      return box;
    }
    const src = roleOf(roles, "source"), many = !!(src && src.many), pairs = t.stages.some((g) => g.steps.some((s) => s.on === "pair"));
    head.append(h("span", "wf-muted", "문서마다 차례로 하는 단계" + (pairs ? " — 「← 원본 문서」 는 원본 문서의 내용을 받는 단계" : "") + (many ? " · 원본 문서가 여럿이면 원본 문서마다 되풀이합니다" : "")));
    const table = h("table", "wf-docs"), thead = h("thead"), hr = h("tr"), tbody = h("tbody"), th0 = h("th", "", "단계");
    table.setAttribute("aria-label", "문서마다 단위문서 TASK");
    th0.scope = "col";
    hr.append(th0);
    const label = (r) => `${roleTitle(r)} — ${r.name}` + (r.many ? "(문서마다)" : ""); // 칸의 문서 이름표(좁은 폭에서 칸 위에 — 표 머리 대신)
    for (const r of roles) {
      const th = h("th");
      th.scope = "col";
      th.dataset.role = r.role;
      th.append(h("b", "", roleTitle(r)), document.createTextNode(` — ${r.name}`));
      if (r.many) th.append(h("span", "wf-muted", "(문서마다)"));
      hr.append(th);
    }
    thead.append(hr);
    for (const g of t.stages) {
      const tr = h("tr"), th = h("th");
      tr.dataset.stage = g.id;
      th.scope = "row";
      th.append(stageLink(t, g));
      tr.append(th);
      for (const r of roles) {
        const td = h("td"), keys = ((r.unit || []).find((u) => u.stage === g.id) || {}).steps || [];
        td.dataset.role = r.role;
        td.dataset.label = label(r);
        if (!keys.length) td.append(h("span", "wf-docs-none", "—"));
        else {
          const ol = h("ol", "wf-docs-steps");
          let run = false; // 원본 → 목적 잇기(pair)가 이어지는 동안 — 그 첫 단계 앞에 「← 원본 문서」 한 번
          for (const k of keys) {
            const s = g.steps.find((x) => x.key === k) || { key: k, name: k }, pair = r.role === "target" && s.on === "pair", li = h("li");
            if (pair && !run) { const mark = h("span", "wf-docs-from", many ? "← 원본 문서마다" : "← 원본 문서"); mark.title = `원본 문서(${src ? src.name : ""})의 내용을 이 문서가 받는 단계`; li.append(mark); }
            run = pair;
            li.append(stepLink(t, g, s));
            ol.append(li);
          }
          td.append(ol);
        }
        tr.append(td);
      }
      tbody.append(tr);
    }
    if (!t.stages.length) { const tr = h("tr"), td = h("td", "wf-docs-none", "준비 중 — 아직 단계가 없습니다"); td.colSpan = roles.length + 1; tr.append(td); tbody.append(tr); }
    table.append(thead, tbody);
    box.append(table, ...(flow ? [flow] : []));
    return box;
  }

  function dots(steps) { // 묶음의 점 — LLM 이 도는 묶음(보라) · 문서를 바꾸는 묶음(주황)
    const out = [], dot = (cls, text) => { const s = h("span", "wf-dot wf-d-" + cls); s.setAttribute("role", "img"); s.setAttribute("aria-label", text); s.title = text; return s; };
    if (steps.some((s) => s.by.includes("llm") && !s.soon)) out.push(dot("llm", "LLM 이 도는 단계가 있습니다"));
    if (steps.some((s) => s.change === "doc" && !s.soon)) out.push(dot("doc", "문서를 바꾸는 단계가 있습니다"));
    return out;
  }

  // 절의 설명 글 — 본문에 두지 않고 절 머리의 노트 아이콘(누르면 · 가리키면 풍선)으로(2026-11-20 사용자 「이런 설명은 아이콘 클릭하면 보여주게 해줘」 — design.md §1-6 노트 도움말 · panel_help.js hHelp).
  // 상태 · 거절 · 빈 목록 글은 본문에 그대로 둔다. hHelp 가 없으면(옛 캐시) 본문 글로.
  function headHelp(sec, h2, label, text) {
    if (typeof hHelp === "function") { const b = hHelp(label, text); b.classList.add("wf-head-help"); h2.append(b); }
    else sec.append(h("p", "wf-lead", text));
  }
  function overview() { // 전체 보기 — TASK 마다 한 줄: 이름 + 단계 묶음의 사슬
    const sec = h("section", "wf-sec"), h2 = h("h2", "", "전체 보기");
    sec.id = "overview";
    sec.append(h2);
    headHelp(sec, h2, "전체 보기 — 설명", ["워크플로우는 단계를 정해진 차례로 밟는 일이고, 단계는 도구를 씁니다. 스크립트가 계산하고 LLM 은 검토 · 판정만 하며, 문서는 사람이 확인(「반영」 · 「한 번에 진행」)한 뒤에만 바뀝니다. 아래에서 워크플로우나 단계 묶음을 누르면 그 과정으로 갑니다.",
      D.waysNote || ""].filter(Boolean).join("\n\n")); // 진행 방식 둘(한 번에 진행 · 단계별) + 에이전트가 보이는 것 — TASK 절의 「진행 방식」 이 TASK 마다 적는다
    const legend = h("ul", "wf-legend");
    for (const [cls, name, text] of [["", D.by.script, "정해진 코드가 계산"], ["llm", D.by.llm, "에이전트가 검토 · 판정"], ["human", D.by.human, "사람이 고르거나 확인"], ["doc", D.change.doc, "이 단계에서 문서가 바뀜"],
      ["soft", "자동", "누르지 않아도 돎"], ["must", "필수", "해야 다음으로"], ["soft", "선택", "건너뛰어도 다음으로"]]) { const li = h("li"); li.append(tag(name, cls), document.createTextNode(WF_ICON_BY_TEXT[name] ? `${name} — ${text}` : text)); legend.append(li); } // 아이콘 칩은 이름이 안 보이므로 범례에 이름을 글로
    const lg = h("li");
    lg.append(...dots([{ by: ["llm"], change: "doc" }]), document.createTextNode("묶음에 LLM 단계 · 문서를 바꾸는 단계가 있음"));
    legend.append(lg);
    sec.append(legend);
    const list = h("ol", "wf-over");
    for (const t of D.tasks) {
      const li = h("li"), chain = h("ol", "wf-chain");
      li.dataset.job = t.job;
      if (t.soon || !t.stages.length) li.className = "wf-soon";
      li.append(link(`#${t.job}`, taskName(t.job), "wf-over-name"));
      if (!t.stages.length) { const c = h("li"); c.append(tag("준비 중", "soft")); chain.append(c); }
      for (const g of t.stages) {
        const L = stageLabel(g), c = h("li"), a = link(`#${t.job}--${g.id}`, "", "wf-chip");
        if (L.no) a.append(h("b", "", L.no));
        a.append(document.createTextNode(L.name), ...dots(g.steps));
        c.append(a);
        chain.append(c);
      }
      li.append(chain);
      list.append(li);
    }
    sec.append(list);
    const commonsBox = h("div", "wf-commons-box");
    for (const [label, stage] of [["단계", true], ["도구", false]]) { // 단계(TASK 가 조립하는 일반 단계) · 도구(여러 TASK 가 쓰는 과정)
      const commons = h("div", "wf-commons"), chips = h("div", "wf-commons-chips");
      commons.dataset.kind = stage ? "stage" : "tool";
      for (const c of D.common) if ((c.kind === "stage") === stage) chips.append(link(`#common-${c.id}`, c.name, "wf-chip"));
      commons.append(h("span", "wf-muted", label), chips);
      commonsBox.append(commons);
    }
    sec.append(commonsBox);
    return sec;
  }

  function taskSec(t) { // TASK 절 — 이름 · 한 줄 설명 · 받는 문서 → 산출물 · 알아 둘 것 → 단계 묶음(세로 차례)
    const sec = h("section", "wf-sec wf-task"), h2 = h("h2"), desc = descOf(t); // 한 줄 설명 — 조립한 것은 사람이 적은 글 · 없으면 등록부가 실제 배정에서 지은 글(descAuto)
    sec.id = t.job;
    h2.append(h("span", "wf-kind", "워크플로우"), document.createTextNode(taskName(t.job)));
    if (t.soon) h2.append(tag("준비 중", "soft"));
    sec.append(h2);
    if (t.custom) h2.append(tag("조립한 워크플로우", "soft"));
    if (desc) sec.append(h("p", "wf-lead", desc));
    const io = h("dl", "wf-io");
    if (t.custom) { // 화면에서 조립한 워크플로우(② §14) — 고치기 · 지우기는 「워크플로우 조립」 절에서(cells 를 주지 않는 옛 서버면 「고치기」 는 꺼짐)
      const edit = h("button", "btn sm", "고치기");
      edit.type = "button";
      edit.dataset.wfCompose = t.job;
      edit.disabled = !composable();
      if (edit.disabled) edit.title = NO_COMPOSE;
      edit.addEventListener("click", () => composeOpen(t.job));
      row(io, "조립", [document.createTextNode("화면에서 단계를 골라 만든 워크플로우입니다 — "), edit]);
      // 물려받는 전제 = premiseFrom(붙박이 키 — 등록부의 base 는 이제 구성의 기준 역할이고 null 일 수도 있다) · premiseFrom 을 안 주는 옛 서버는 base 가 그 키였다 · 그것도 아니면 GET /api/tasks 의 base(전제를 물려받는 붙박이 키)
      const from = t.premiseFrom || (CAT[t.base] ? t.base : "") || (T && typeof T.base === "string" ? T.base : "");
      row(io, "전제", t.premise ? "조립할 때 적은 글(이 워크플로우의 LLM 호출이 읽습니다)"
        : `틀이 같은 워크플로우${from ? `(${taskName(from)})` : ""}의 전제를 씁니다 — 그 글의 단계 설명 가운데 고르지 않은 단계는 하지 않습니다`);
    }
    row(io, "받는 문서", t.inputs);
    if (!t.soon) row(io, "문서 칸", slotEl(t)); // 역할마다의 칸 · 목적 문서 칸의 양식 설정(저장한 양식 — ② §18-9)
    row(io, "산출물", t.output);
    if (t.note) row(io, "알아 둘 것", t.note);
    if (t.prompt) row(io, "전제", [h("code", "", t.prompt), document.createTextNode(" — 이 워크플로우의 전제 · 기준을 적은 할 일 프롬프트(에이전트가 먼저 읽는 글)")]);
    sec.append(io);
    const docs = docsEl(t); // 문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 받는 문서 · 산출물 줄 아래 · 진행 방식 위
    if (docs) sec.append(docs);
    if ((t.ways || []).length) { // 진행 방식(spec_작업에이전트 ② §7) — 한 번에 진행 · 에이전트가 묻는 것 · 멈추거나 남기는 곳 · 단계별
      const ways = h("dl", "wf-io wf-ways");
      ways.id = `${t.job}--ways`;
      ways.setAttribute("aria-label", "진행 방식");
      for (const w of t.ways) row(ways, w.name, w.text);
      sec.append(h("h3", "wf-ways-head", "진행 방식"), ways);
    }
    if ((t.entry || []).length) { // 시작 점검(spec_워크플로우 ② §10) — 시작할 때 저절로 확인하는 것. 이 TASK 의 세부는 TASK 문서(tasks/<job>.md)에도 같은 글로 있다
      const head = h("h3", "wf-ways-head wf-entry-head", "시작 점검"), box = entryEl(t, false);
      head.append(h("span", "wf-muted", `시작할 때 저절로 확인하는 것 ${entryCount(t)}가지` + (t.doc ? " · 워크플로우 상세 문서" : "")), ...(t.doc ? [h("code", "", t.doc)] : [])); // 조립한 워크플로우는 그 파일이 없다(doc "") — 빈 경로를 적지 않는다
      box.id = `${t.job}--entry`;
      sec.append(head, box);
    }
    if (!t.stages.length) return sec;
    const ol = h("ol", "wf-stages");
    t.stages.forEach((g, i) => {
      const L = stageLabel(g), li = h("li", "wf-stage"), box = h("div", "wf-box"), head = h("div", "wf-stage-head");
      li.id = `${t.job}--${g.id}`;
      li.dataset.stage = g.id;
      head.append(h("h3", "", L.name));
      if (g.does) head.append(h("p", "", g.does));
      if (g.module) { // 이 묶음이 조립한 단계(spec_워크플로우 ② §13 — 등록부의 module: 그 단계의 절로)
        const m = D.common.find((x) => x.id === g.module), p = h("p", "wf-stage-module", "조립한 단계 ");
        p.append(link(`#common-${g.module}`, m ? m.name : g.module, "wf-chip"));
        head.append(p);
      }
      box.append(head, stepsEl(g.steps, `${t.job}--${g.id}`, t));
      li.append(h("span", "wf-stage-no" + (L.no ? "" : " wf-plain"), L.no || String(i + 1)), box);
      ol.append(li);
    });
    sec.append(ol);
    return sec;
  }

  function commonSec(c) { // 공통 모듈 절 — 하는 일 · 여는 곳 · 쓰는 TASK + 단계
    const sec = h("section", "wf-sec wf-common"), h2 = h("h2"), io = h("dl", "wf-io"), box = h("div", "wf-box");
    sec.id = `common-${c.id}`;
    const stage = c.kind === "stage", used = stage ? "조립한 워크플로우" : "쓰는 워크플로우"; // 단계 모듈 = TASK 가 조립하는 일반 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리 — ② §13)
    h2.append(h("span", "wf-kind", stage ? "단계" : "도구"), document.createTextNode(c.name));
    sec.append(h2, h("p", "wf-lead", c.does));
    row(io, "여는 곳", c.where);
    if (c.usedBy.length) { const links = h("div", "wf-links"); for (const job of c.usedBy) links.append(link(`#${job}`, taskName(job), "wf-chip")); row(io, used, links); }
    else row(io, used, stage ? "아직 이 단계를 조립한 워크플로우가 없습니다" : "어느 워크플로우의 문서에서나 엽니다(단계에 묶이지 않음)");
    box.append(stepsEl(c.steps, `common-${c.id}`, c));
    box.style.marginTop = "10px";
    sec.append(io, box);
    return sec;
  }

  function navDraw() {
    const nav = $("wfNav");
    const head = (text, count) => { const e = h("h2", "", text); e.dataset.count = String(count); return e; };
    const make = h("button", "btn sm wf-nav-make", "＋ 워크플로우 조립"); // 단계를 골라 새 워크플로우를 만든다(② §14) — 전체 보기 아래 「워크플로우 조립」 절의 폼으로(폼을 못 여는 서버면 그 절의 안내로)
    make.type = "button";
    make.dataset.wfCompose = "new";
    make.title = "원본 문서 · 목적 문서마다 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를 골라 새 워크플로우를 만듭니다";
    make.addEventListener("click", () => composeOpen(""));
    const formsWrap = h("div", "wf-nav-sep");
    formsWrap.append(link("#wfForms", "저장한 양식", "wf-nav-forms")); // 목적 문서 칸에 넣을 양식 파일(② §18-9) — 전체 보기와 함께 서는 절
    const stages = D.common.filter((c) => c.kind === "stage"), tools = D.common.filter((c) => c.kind !== "stage");
    const mine = (T && Array.isArray(T.userStages) ? T.userStages : []).map((s) => { // 내가 만든 단계(② §18-14) — 누르면 그 단계의 폼(「단계 만들기」 절)
      const a = link("#wfStage", s.name, "wf-made wf-mine");
      a.dataset.stage = s.key;
      a.addEventListener("click", (e) => { e.preventDefault(); stageOpen(s.key); });
      return a;
    });
    const makeStage = h("button", "btn sm wf-nav-make", "＋ 단계 만들기"); // 있는 줄을 골라 내 단계를 만든다(사용자 「이 단계 만들기도 있어야 하는거 아니냐?」)
    makeStage.type = "button";
    makeStage.dataset.wfStage = "new";
    makeStage.title = "있는 줄(헤딩 · 표 분석 · 자리 연결 …)을 골라 이름 붙인 내 단계를 만듭니다 — 워크플로우 조립에서 꺼내 씁니다";
    makeStage.disabled = !(T && Array.isArray(T.userStages)); // 옛 서버
    makeStage.addEventListener("click", () => stageOpen(""));
    navTools = h("div", "wf-nav-tools"); // 「워크플로우 도구」(조립에 놓는 도구 — 분류로 묶음 · 끌어서 넣기: navToolsDraw) — 단계 아래 · 등록부의 「도구」 위
    nav.replaceChildren(link("#overview", "전체 보기"), head("워크플로우", D.tasks.length), ...D.tasks.map((t) => link(`#${t.job}`, taskName(t.job), t.soon ? "wf-soon" : t.custom ? "wf-made" : "")), make,
      formsWrap,
      head("단계", stages.length + mine.length), ...stages.map((c) => link(`#common-${c.id}`, c.name)), ...mine, makeStage,
      navTools,
      head("도구", tools.length), ...tools.map((c) => link(`#common-${c.id}`, c.name)));
    navToolsDraw();
  }

  // ---- 목차의 「워크플로우 도구」(spec_워크플로우 ② §18-18 · design.md §23 — 2026-11-21 사용자 「여기 있는 도구는 첫번째 사이드 패널에 리스트로 있어야 하고, 여기 리스트에서 드래그로 워크플로우 도구를 넣을 수 있고,
  // 그리고 도구는 묶음을 했으면 좋겠는데 명칭은 뭘로 할진 모르겠지만. '일반', '사업계획서' 이런식으로 묶으면 좋을 듯」):
  // 조립에 놓을 수 있는 도구(넣기 고르기의 그 줄들 — unitsOf)를 **분류**로 묶어 목차에 둔다. 분류 = 그 도구가 받는 문서 — 서버의 units[].only(② §18-17 「전용 표시」) 그대로: 없음 = 「일반」 · 있으면 그 이름에서 「 전용」 을 뗀 것(화면이 따로 셈하지 않는다).
  // 목록은 펴 둔 폼의 틀을 따른다(조립 폼 → 없으면 단계 폼 → 둘 다 없으면 새 워크플로우의 틀 — 이관형) · 끌어서 그 폼의 줄 목록에 놓는다(dropFindNew · dropAdd — 카드 끌기와 같은 자리 셈) · 누르면 그 도구의 설명(폼이 없으면 새 조립 폼을 연다).
  // 등록부의 COMMON 목록(목차의 「도구」 — 도구 절로 가는 링크)은 그대로 그 아래에 둔다. 좁은 창(목차가 가로 한 줄)에서는 서지 않는다(workflow.css — 넣기 고르기는 그대로).
  const NAV_KINDS = ["", "rnd", "relay", "gather"]; // 분류의 차례 — 일반 먼저(모르는 종류는 뒤에 · 처음 나온 차례)
  let navTools = null; // 목차 안의 그 상자(navDraw 가 만든다)
  const navForm = () => composing || staging || null; // 목록이 따르는 폼
  const navKind = (u) => (u && u.only && typeof u.only.kind === "string" ? u.only.kind : "");
  const navKindName = (u) => { const l = u && u.only && typeof u.only.label === "string" ? u.only.label.replace(/\s*전용$/, "").trim() : ""; return l || "일반"; };
  function navToolsDraw() { // 폼 · 틀이 바뀌었을 때만 다시 그린다(초점 · 끌던 줄이 그대로) — 설명이 보이는 도구 표시는 늘
    const box = navTools;
    if (!box || !box.isConnected) return;
    const c = navForm(), list = c || composable() ? unitsOf(c) : [];
    const sig = [c ? (c === composing ? "c" : "s") : "-", c ? c.shape || "" : "", c ? c.pair || "" : "", c && c.locked ? 1 : 0, list.map((u) => `${u.key}:${u.name}:${u.server === false ? 0 : 1}`).join(",")].join("|");
    if (box.dataset.sig !== sig) {
      box.dataset.sig = sig;
      const focus = box.contains(document.activeElement) ? document.activeElement.dataset.tool || "" : "";
      box.hidden = !list.length; // 옛 서버(units 없음) · 조립을 못 여는 서버 — 머리도 세우지 않는다
      if (!list.length) { box.replaceChildren(); return; }
      const head = h("h2", "", "워크플로우 도구"), io = c && !c.single ? ((T && Array.isArray(T.shapes) ? T.shapes : []).find((x) => x && x.id === (c.shape || "relay")) || {}).io : "";
      head.dataset.count = String(list.length);
      const hint = h("p", "wf-nav-hint", !c ? "누르면 설명 · 조립 폼을 열면 끌어서 넣습니다" : c.locked ? "쓰는 중인 워크플로우라 줄을 못 바꿉니다 · 누르면 설명"
        : `끌어서 ${c.single ? "단계 만들기 폼" : `조립 폼${io ? `(${io})` : ""}`}의 묶음에 놓습니다 · 누르면 설명`);
      const groups = new Map(), byDoc = list.some((u) => u && "only" in u), homes = byDoc ? null : helpHomes(c); // only 를 안 주는 서버(② §18-17 전) — 넣기 고르기처럼 사는 단계로 묶는다(모두 「일반」 으로 보이지 않게)
      for (const u of list) {
        const k = byDoc ? navKind(u) : `home:${u.kind === "hand" ? "hand" : u.home || ""}`;
        if (!groups.has(k)) groups.set(k, { name: byDoc ? navKindName(u) : u.kind === "hand" ? "사람이 하는 일" : homes[u.home] || u.home || "", why: (u.only && u.only.why) || "", list: [] });
        groups.get(k).list.push(u);
      }
      const kids = [head, hint];
      for (const k of [...NAV_KINDS.filter((x) => groups.has(x)), ...[...groups.keys()].filter((x) => !NAV_KINDS.includes(x))]) {
        const g = groups.get(k), sec = h("div", "wf-nav-group"), gh = h("h3", "wf-nav-group-name", g.name), ul = h("ul", "wf-nav-tool-list");
        sec.dataset.kind = k.startsWith("home:") ? "home" : k || "general";
        gh.title = k.startsWith("home:") ? "사는 단계" : k ? `${g.name} 전용${g.why ? ` — ${g.why}` : ""}` : "문서를 가리지 않는 도구";
        for (const u of g.list) ul.append(navToolEl(u, c));
        sec.append(gh, ul);
        kids.push(sec);
      }
      box.replaceChildren(...kids);
      if (focus) { const to = [...box.querySelectorAll("[data-tool]")].find((x) => x.dataset.tool === focus); if (to) to.focus({ preventScroll: true }); }
    }
    for (const b of box.querySelectorAll("[data-tool]")) b.setAttribute("aria-pressed", c && c.help === b.dataset.tool ? "true" : "false"); // 오른쪽 「도구 설명」 열에 보이는 도구
  }
  function navToolEl(u, c) { // 도구 한 줄 — 끌 손잡이 · 이름 · 꼬리표(쌍 · 사람 · LLM · 문서 바뀜 — 넣기 고르기 · 도구 목록과 같은 값)
    const li = h("li"), b = h("button", "wf-nav-tool"), grip = h("span", "wf-nav-tool-grip"), tags = h("span", "wf-nav-tool-tags"), off = u.server === false, can = !!c && !c.locked && !off;
    b.type = "button";
    b.dataset.tool = u.key;
    grip.setAttribute("aria-hidden", "true");
    grip.innerHTML = '<svg viewBox="0 0 10 14" width="8" height="12" fill="currentColor"><circle cx="3" cy="3" r="1.15"/><circle cx="7" cy="3" r="1.15"/><circle cx="3" cy="7" r="1.15"/><circle cx="7" cy="7" r="1.15"/><circle cx="3" cy="11" r="1.15"/><circle cx="7" cy="11" r="1.15"/></svg>';
    if (u.place === "pair") { const p = h("span", "wf-nav-tool-pair", "쌍"); p.title = "원본 문서 → 목적 문서 — 두 문서 칸에 쌍으로 놓입니다"; tags.append(p); }
    if (u.kind === "hand" || u.kind === "pick") tags.append(tag("사람", "human", "human"));
    if (u.change === "doc") tags.append(tag("문서 바뀜", "doc", "doc"));
    b.append(grip, h("span", "wf-nav-tool-name", u.name), tags);
    if (off) b.classList.add("wf-off");
    b.title = `${u.name}${off ? " — 아직 서버가 못 돌림" : ""}\n${can ? "끌어서 조립 폼의 묶음에 놓습니다 · 누르면 설명" : "누르면 설명"}`;
    b.draggable = can;
    b.addEventListener("click", () => navToolPick(u.key));
    b.addEventListener("dragstart", (e) => {
      const f = navForm();
      if (!f || f.locked || off || !unitOf(u.key, f)) { e.preventDefault(); return; }
      drag = { c: f, unit: u.key, key: "" };
      e.dataTransfer.effectAllowed = "copy";
      try { e.dataTransfer.setData("text/plain", u.name); } catch { /* 끌 글을 못 실어도 끌기는 된다 */ }
      setTimeout(() => { if (drag && drag.c === f) { navReveal(f, f.linesBox); if (f.linesBox) f.linesBox.classList.add("wf-dragging"); } }, 0); // 끄는 그림을 뜬 뒤에 — 폼이 안 보이면 보이게
    });
    b.addEventListener("dragend", () => { if (drag && drag.unit) dragEnd(drag.c); }); // 놓지 않고 끝남(Esc · 밖) — 놓았으면 drop 이 먼저 지웠다
    li.append(b);
    if (u.paid) { li.classList.add("wf-prompt-tool"); li.append(builderPromptTag(u, c)); }
    return li;
  }
  function builderPromptTag(u, c) {
    const b = h("button", "wf-tag wf-t-llm");
    b.type = "button"; b.dataset.llmPrompt = u.key;
    b.title = `${u.name} LLM 프롬프트 보기·수정`;
    b.setAttribute("aria-label", b.title);
    b.append(wfIcon("llm"), h("span", "sr-only", "LLM"));
    b.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!c) navToolPick(u.key);
      const form = c || navForm();
      if (form) { WfAgents.showPrompt(form, u.key); navReveal(form, form.ag.box); }
    });
    return b;
  }
  function navReveal(c, el) { // 그 폼이 보이게 — 다이어그램 보기에서 다른 절을 보고 있으면 전체 보기로(조립 · 단계 만들기 절은 전체 보기와 함께 선다) · el 이 본문 화면 밖이면 거기까지
    const sec = $(c === composing ? "wfCompose" : "wfStage"), main = $("wfMain");
    if (sec && sec.hidden) { if (view === "diagram") navigate("#overview"); else go("#overview"); }
    if (!el || !main) return;
    const r = el.getBoundingClientRect(), m = main.getBoundingClientRect();
    if (r.bottom < m.top + 40 || r.top > m.bottom - 40) el.scrollIntoView({ block: "nearest" });
  }
  function navToolPick(key) { // 누름 — 그 도구의 설명(오른쪽 「도구 설명」 열 · 「에이전트」 열도 같은 고름) · 폼이 없으면 새 조립 폼을 연다(조립은 안 바뀐다)
    let c = navForm();
    if (!c) { if (!composable()) return; composeOpen(""); c = composing; if (!c) return; }
    if (!unitOf(key, c)) return;
    helpPick(c, key);
    navReveal(c, c.helpBox);
  }

  function navSync() { // 목차의 지금 절 — 본문 스크롤 자리로(본문이 혼자 스크롤한다)
    const main = $("wfMain"), line = main.getBoundingClientRect().top + 60; // 본문 위에서 60px 안에 머리가 들어온 마지막 절(맨 위에서는 전체 보기)
    let id = (routes.get(current) || {}).flow?.id || "overview";
    if (view === "list") {
      let cur = null;
      for (const s of main.querySelectorAll(".wf-sec")) if (!cur || s.getBoundingClientRect().top <= line) cur = s;
      if (cur) { if (cur.id !== id) current = cur.id; id = cur.id; }
    }
    for (const a of $("wfNav").querySelectorAll("a")) {
      const on = a.getAttribute("href") === `#${id}`;
      if (on) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    }
  }

  function go(hash) { // 주소의 # 자리로(없는 id 는 무시)
    if (!D) return;
    let id = "";
    try { id = decodeURIComponent((hash || "#overview").replace(/^#/, "")); } catch { id = "overview"; }
    const anchor = OVER_SECS.has(id) ? id : ""; // 전체 보기와 함께 서는 절(워크플로우 조립 · 저장한 양식) — 전체 보기를 펴고 그 절로
    if (anchor || (id !== "overview" && !routes.has(id))) id = "overview";
    const oldOwner = (routes.get(current) || {}).flow?.id, route = routes.get(id), main = $("wfMain"), diagram = $("wfDiagram");
    const focusKey = document.activeElement?.dataset.wfFocus;
    current = id;
    for (const sec of main.querySelectorAll(".wf-sec")) sec.hidden = view === "diagram" && (id !== "overview" || (sec.id !== "overview" && !OVER_SECS.has(sec.id))); // 「워크플로우 조립」 · 「저장한 양식」 절은 전체 보기와 함께
    diagram.hidden = view !== "diagram" || !route;
    if (view === "diagram") {
      if (route) {
        drawDiagram(route);
        if (focusKey) {
          const focus = [...diagram.querySelectorAll("[data-wf-focus]")].find((e) => e.dataset.wfFocus === focusKey && !e.disabled);
          (focus || $("wfDetailTitle"))?.focus({ preventScroll: true });
        }
        if (oldOwner !== route.flow.id) main.scrollTop = 0;
        else if (focusKey?.startsWith("node-") && matchMedia("(max-width: 760px)").matches) $("wfDetail").scrollIntoView({ block: "start" });
        else if ((focusKey === "wfPrev" || focusKey === "wfNext") && matchMedia("(min-width: 1200px)").matches) // 설명이 붙박이인 폭 — 이전·다음으로 고른 단계가 긴 흐름의 화면 밖이면 보이는 데까지만 민다
          diagram.querySelector(".wf-node[aria-current=step]")?.scrollIntoView({ block: "nearest" });
      } else main.scrollTop = 0;
    } else {
      const el = document.getElementById(id) || [...main.querySelectorAll("[data-wf-path]")].find((e) => e.dataset.wfPath === id);
      if (el?.matches("details")) el.open = true;
      if (el && main.contains(el)) el.scrollIntoView({ block: "start" });
    }
    if (anchor && $(anchor)) $(anchor).scrollIntoView({ block: "start" });
    navSync();
  }
  const OVER_SECS = new Set(["wfCompose", "wfStage", "wfForms"]); // 전체 보기와 함께 서는 절 — 주소 #wfForms 로 바로 열린다

  function navigate(hash) {
    // 주소는 남기되 브라우저의 기본 fragment 스크롤과 상세 자동 펼침은 피한다.
    if (location.hash !== hash) history.pushState(null, "", hash);
    go(hash);
  }

  function setView(next) {
    view = next;
    document.body.classList.toggle("wf-diagram-mode", view === "diagram");
    $("wfViewDiagram").setAttribute("aria-pressed", String(view === "diagram"));
    $("wfViewList").setAttribute("aria-pressed", String(view === "list"));
    $("wfOpenAll").hidden = $("wfCloseAll").hidden = view !== "list";
    if (D && location.hash !== `#${current}`) history.replaceState(null, "", `#${current}`);
    go(`#${current}`);
  }

  // ---- 워크플로우 조립(spec_워크플로우 ② §14 · §15) — 단계를 골라 새 워크플로우를 만든다 · 조립한 워크플로우를 고치고 지운다. 저장소 = 서버(GET·POST /api/tasks · PUT·DELETE /api/tasks/{key}).
  // 지금 조립할 수 있는 틀은 이관형(원본 문서 하나 → 목적 문서 하나)이고 문서 쌍은 서버가 주는 것(pairs)뿐이다 — 아직 안 되는 틀은 까닭과 함께 보인다(blocked). 단계의 차례는 일반 단계의 차례로 고정(고르는 것은 쓰느냐뿐).
  // 고르는 곳 = 문서 역할 × 단계 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」): 칸 = 서버의 stages[].cells[역할] — pick(체크) · follow(다른 역할이 그 단계를 고르면 따라오는 글) · no(고를 수 없음 — 까닭).
  // **cells 를 주지 않는 서버(옛 서버)에서는 폼을 열지 않는다** — 옛 서버는 assign 을 몰라 문서마다 고른 배정을 잃는다(astra P1 ④). 배정은 화면이 따로 셈하지 않고 서버의 assign({source, target, llm})을 그대로 쓴다.
  // 저장 몸 = assign {source, target}(일반 차례 — 합집합 stages 는 보내지 않는다). 고른 단계가 연 때 그대로면 서버가 준 llm 도 그대로 돌려준다(복제가 같은 배정이 되게 — 바뀌었으면 안 보내고 서버가 규칙으로 다시 정한다).
  // 쓰는 중 — 셈은 서버가 한다(조립한 워크플로우마다 inUse = 그 키를 지금 워크플로우로 둔 작업 · listed = 문서의 워크플로우 목록에만 든 작업 · editWhy · deleteWhy = 못 하는 까닭 글 | null):
  // editWhy 가 있으면(지금 워크플로우로 둔 작업이 있음) 이름 · 설명 · 전제만 고친다(assign 을 보내지 않음 — 서버도 409) — 단계를 바꾸려면 「복제」 로 새 워크플로우를 만든다 · deleteWhy 가 있으면(목록에만 든 작업도 셈) 못 지운다.
  // 까닭 글은 서버의 것 그대로(화면이 따로 짓지 않는다) — editWhy · deleteWhy 를 안 주는 옛 서버만 inUse(목록 줄까지 센 수)로 지은 글. broken = 저장 파일을 못 읽음(서버가 쓰지 않는다) — 까닭을 폼 위에.
  // 그 작업들 = 서버의 uses[{wid, name, project, round, active}](지금 워크플로우로 둔 것 먼저 · 앞 20개) + usesMore(나머지 수) — 목록 줄의 셈 아래에 작업마다 그 작업을 여는 링크(새 탭 · 앱의 #w=<작업 id>) +
  // 꼬리표 「지금 워크플로우」 · 「목록에만」(madeWorks — 셈만 보이면 어느 문서에서 바꾸거나 빼야 하는지 모른다: 3차 검토). uses 를 안 주는 옛 서버면 셈만.
  let T = null; // GET /api/tasks — {tasks, stages(붙박이 단계 — lines = 표준 줄), userStages(내가 만든 단계 — ② §18-14), pairs, blocked, base, limits, broken, warn} | null(못 읽음 — 옛 서버)
  let composing = null; // 펴 둔 폼 {key("" = 새로), name, desc, pair, assign: {source: Set, target: Set}, from(연 때의 배정 — 견줌), llm(연 때 서버가 준 llm | null), locked(단계를 못 바꾸는 까닭 글 — "" 이면 단계를 고침), copyOf(복제한 워크플로우 이름), premise, err, busy}
  const NO_COMPOSE = "조립은 서버를 다시 켠 뒤에 쓸 수 있습니다"; // cells 를 주지 않는 서버(옛 서버) · /api/tasks 를 못 읽음
  const why = (v) => (typeof v === "string" ? v : ""); // 서버의 까닭 글(null = 할 수 있음)
  const lockOf = (t) => (!t ? "" : t.editWhy !== undefined ? why(t.editWhy) // 단계를 못 바꾸는 까닭 — 서버의 editWhy(PUT 409 와 같은 글) · 옛 서버는 inUse 로
    : t.inUse > 0 ? `하던 작업이 ${t.inUse}개 있어 단계는 못 바꿉니다 — 「복제」 로 새 워크플로우를 만드세요` : "");
  const delOf = (t) => (!t ? "" : t.deleteWhy !== undefined ? why(t.deleteWhy) // 못 지우는 까닭 — 서버의 deleteWhy(DELETE 409 와 같은 글) · 옛 서버는 inUse 로 지은 전의 글
    : t.inUse > 0 ? `이 워크플로우로 하던 작업이 ${t.inUse}개 있어 지울 수 없습니다(문서의 워크플로우 목록에 든 것 포함) — 그 작업을 지운 뒤에 지울 수 있습니다` : "");
  // 조립 폼의 경고(막지 않음 — 목적 문서에 「구성 맞추기」 없이 「내용 넣기」) 뒷부분 = 서버의 warn.fillNoFit(등록부의 글이 원본 — 묶음 설명도 그 글을 쓴다) · 안 주는 옛 서버면 같은 글을 여기에
  const FILL_NO_FIT = "목적 문서에 구조 반영 기록이 있고 두 문서의 프로젝트 구성 값이 같아야 자리 연결이 섭니다(손으로 맞춘 구조는 「반영 전」 으로 멈춤)";
  const fillNoFit = () => { const w = T && T.warn && T.warn.fillNoFit; return typeof w === "string" && w.trim() ? w : FILL_NO_FIT; };
  const composable = () => !!T && Array.isArray(T.stages) && T.stages.length > 0 && T.stages.every((st) => st.cells && st.cells.source && st.cells.target) && Array.isArray(T.units); // units = 고를 줄(정의 v2 — 없으면 옛 서버)
  const cellOf = (st, role) => st.cells[role]; // 폼은 composable() 일 때만 그린다
  const stageName = (id) => ((T && T.stages.find((x) => x.id === id)) || {}).name || id;
  const ordered = (ids) => { const on = new Set(ids); return T.stages.map((x) => x.id).filter((id) => on.has(id)); }; // 일반 단계의 차례로
  const sameAssign = (a, b) => ROLES.every((r) => ordered(a[r]).join() === ordered(b[r]).join());
  const limit = (k, d) => ((T && T.limits) || {})[k] || d;
  function assignOf(t) { // 조립한 워크플로우의 문서마다 고른 단계 = 서버의 assign 그대로 {source, target, llm} — 옛 줄(assign 없이 저장된 것)도 서버가 읽어 채운다(원본 = 문서 검토 · 목적 = 고른 단계 · llm = 원본만: 1단계 LLM 검증·보완은 원본 — 옛 뜻 그대로)
    const a = t && t.assign, ids = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === "string") : []); // | null = assign 을 모르는 옛 서버(화면이 원본 · 목적을 따로 셈하지 않는다)
    return a && typeof a === "object" ? { source: ids(a.source), target: ids(a.target), llm: Array.isArray(a.llm) ? ids(a.llm) : null } : null;
  }
  function pairNames(value) { // 문서 쌍("plan>report") → {source, target} 문서 이름 — 서버의 쌍 이름(「사업계획서 → 연차보고서」)에서
    const p = T.pairs.find((x) => `${x.source}>${x.target}` === value) || T.pairs[0] || {};
    if (p.sourceName && p.targetName) return { source: p.sourceName, target: p.targetName };
    const [source, target] = String(p.name || "").split(" → ");
    return { source: source || "", target: target || "" };
  }
  function copyName(name) { // 복제의 이름 — 「<이름> 사본」(이름 길이 제한 안 · 그 이름이 이미 있으면 「<이름> 사본 2」 …)
    const max = limit("name", 40), taken = new Set([...T.tasks.map((x) => x.name), ...Object.values(CAT).map((x) => x && x.name)]);
    const make = (tail) => `${String(name).slice(0, Math.max(0, max - tail.length)).trimEnd()}${tail}`;
    for (let n = 1; n < 100; n++) { const out = make(n === 1 ? " 사본" : ` 사본 ${n}`); if (!taken.has(out)) return out; }
    return make(" 사본");
  }
  async function tasksLoad() {
    try { const r = await fetch("/api/tasks?v=2", { headers: { Accept: "application/json" } }); T = r.ok ? await r.json() : null; } catch { T = null; } // v=2 = 줄 목록 정의(v2)도(판 없이 읽는 옛 탭에는 표준 정의만 — spec_워크플로우 ② §18-12 ⑤)
    if (T && typeof taskCatalogCustom === "function") taskCatalogCustom(T.tasks, { broken: !!T.broken }); // 이 페이지의 워크플로우 이름도 지금 저장소의 것으로(/api/tasks.js 와 같은 꼴 — 둘째 인자 = 저장 파일을 못 읽음)
  }
  function composeOpen(key, copy) { // "" = 새 워크플로우 · 키 = 그 워크플로우 고치기 · copy = 복제할 워크플로우(같은 배정 · 설명 · 전제 + 이름 「<이름> 사본」 의 새 폼) — 전체 보기의 「워크플로우 조립」 절로 가서 폼을 편다
    composing = null;
    if (composable()) { // 아니면 폼 대신 그 절의 안내(「조립은 서버를 다시 켠 뒤에 …」)
      const t = copy || (key ? T.tasks.find((x) => x.key === key) : null), edit = !!(t && !copy), pair = T.pairs[0] || {}, all = T.stages.map((x) => x.id);
      const a = t ? assignOf(t) || { source: [], target: [...(t.stages || [])], llm: null } : { source: all, target: all, llm: null }; // 새 워크플로우 = 고를 수 있는 칸 모두(원본 = 문서 검토 · 목적 = 넷)
      const picked = (role) => new Set(T.stages.filter((st) => cellOf(st, role).mode === "pick" && a[role].includes(st.id)).map((st) => st.id));
      composing = { key: edit ? t.key : "", name: copy ? copyName(t.name) : edit ? t.name : "", desc: t ? t.desc || "" : "", pair: t ? `${t.source}>${t.target}` : `${pair.source}>${pair.target}`, shape: (t && t.shape) || "relay", slots: {},
        assign: { source: picked("source"), target: picked("target") }, llm: t ? a.llm : null, locked: edit ? lockOf(t) : "", copyOf: copy ? t.name : "", premise: t ? t.premise || "" : "", err: "", busy: false,
        flow: t && Array.isArray(t.flow) ? flowCopy(t.flow) : null, mode: t && t.v === 2 ? "lines" : "std", check: null, checking: false }; // flow = 묶음 › 줄(정의 v2) · mode = std(표에서 채운 표준 차례 — 옛 꼴로 저장) | lines(줄을 고침 — 줄 목록으로 저장)
      composing.from = { source: [...composing.assign.source], target: [...composing.assign.target] };
      if (composing.flow) composeCheck(composing, { flow: composing.flow, key: composing.key || undefined }).then(() => linesDraw(composing));
      else stdFill(composing);
    }
    if (view === "diagram") navigate("#overview"); else go("#overview");
    composeDraw();
    const box = $("wfCompose"), first = box && box.querySelector("input[name=name]");
    if (box) box.scrollIntoView({ block: "start" });
    if (first) first.focus({ preventScroll: true });
  }
  async function composeRecheck(c) { // 409 뒤 — 저장소를 다시 읽는다: 고치던 워크플로우가 그 사이 쓰는 중이 됐으면 폼을 잠근다(단계는 저장된 것 · 「복제」 단추) · 저장 파일을 못 읽으면 그 까닭이 폼 위에
    await tasksLoad();
    const t = composable() && c.key ? T.tasks.find((x) => x.key === c.key) : null, a = t && assignOf(t), lock = lockOf(t);
    if (!t || !lock || !a) return;
    c.locked = lock;
    c.assign = { source: new Set(a.source), target: new Set(a.target) };
    c.from = { source: [...a.source], target: [...a.target] };
    c.llm = a.llm;
    if (Array.isArray(t.flow)) { c.flow = flowCopy(t.flow); c.mode = t.v === 2 ? "lines" : "std"; }
  }
  async function composeSave() {
    const c = composing;
    if (!c || c.busy) return;
    const [source, target] = c.pair.split(">"), assign = { source: ordered(c.assign.source), target: ordered(c.assign.target) };
    if (c.llm && sameAssign(assign, c.from)) assign.llm = [...c.llm]; // 고른 단계가 연 때 그대로 — 서버가 준 llm 을 그대로 돌려준다(바뀌었으면 안 보냄: 서버가 규칙으로 다시 정한다)
    // 단계 = 표에서 채운 표준 차례면 assign(옛 꼴 — 옛 서버 · 옛 화면도 그대로) · 줄을 고쳤으면 flow(줄 목록 — 표준 차례와 같으면 서버가 옛 꼴로 저장: spec_워크플로우 ② §18-12 ⑤) · 쓰는 중이면 둘 다 안 보낸다(이름 · 설명 · 전제만)
    const steps = c.locked ? {} : c.mode === "lines" && c.flow ? { flow: c.flow } : { assign };
    const body = { name: c.name, desc: c.desc, premise: c.premise, ...steps, ...(c.key ? {} : { source, target, shape: c.shape }) }; // 합집합 stages 는 안 보낸다
    c.busy = true; c.err = "";
    composeDraw();
    let got = null, status = 0;
    try {
      const r = await fetch(c.key ? `/api/tasks/${encodeURIComponent(c.key)}` : "/api/tasks", { method: c.key ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      status = r.status;
      got = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof got.detail === "string" && got.detail ? got.detail : `HTTP ${r.status}`); // 서버의 글 그대로(400 값이 틀림 · 409 쓰는 중 · 저장 파일을 못 읽음)
    } catch (e) {
      c.busy = false; c.err = e.message;
      if (status === 409) await composeRecheck(c);
      if (composing === c) composeDraw(); // 기다리는 동안 「취소」 를 눌렀으면 그대로
      return;
    }
    composing = null;
    const slots = c.key ? {} : Object.fromEntries(Object.entries(c.slots || {}).filter(([, v]) => v && v.mode && v.file).map(([role, v]) => [role, { file: v.file, mode: v.mode }])); // 새 워크플로우의 문서 칸 양식 — 만든 뒤에 건다(설정은 정의와 따로: 고치기는 그 칸에서 바로)
    if (Object.keys(slots).length) {
      const r = await ffSend(`/api/workflow-slots/${encodeURIComponent(got.task.key)}`, { method: "PUT", headers: JSON_H, body: JSON.stringify(slots) });
      if (!r.ok) alert(`워크플로우는 만들었지만 문서 칸의 기본 문서를 걸지 못했습니다 — ${r.msg}

그 워크플로우 절의 「문서 칸」 에서 다시 거세요.`);
    }
    const noteErr = window.WfAgents ? await WfAgents.flush(c, got.task.key) : ""; // 「에이전트」 열에 적어 두고 저장 안 한 덧붙이는 글도 함께 저장(② §18-16 — 새 워크플로우의 전용 글은 방금 받은 키로)
    if (noteErr) alert(`워크플로우는 저장했지만 ${noteErr}\n\n그 워크플로우를 「고치기」 로 열어 「에이전트」 열에서 다시 저장하세요.`);
    await load(); // 등록부 · 저장소를 다시 읽어 목차 · 절을 새로
    navigate(`#${got.task.key}`);
  }
  async function composeDelete(t) {
    if (!confirm(`조립한 워크플로우 「${t.name}」 ${josa(t.name, "을", "를")} 지울까요?\n\n단계 · 도구는 그대로이고 이 워크플로우(이름 · 고른 단계 · 전제)만 지웁니다. 되돌릴 수 없습니다.`)) return;
    let msg = "";
    try { const r = await fetch(`/api/tasks/${encodeURIComponent(t.key)}`, { method: "DELETE" }); if (!r.ok) msg = ((await r.json().catch(() => ({}))).detail) || `HTTP ${r.status}`; }
    catch (e) { msg = e.message; }
    if (msg) { alert(`지우지 못했습니다 — ${msg}`); return; }
    if (composing && composing.key === t.key) composing = null;
    await load();
    navigate("#overview");
  }
  function composeSec() { // 「워크플로우 조립」 절 — 전체 보기 아래(다이어그램 · 목록 어느 보기에서나 전체 보기와 함께 보인다)
    const sec = h("section", "wf-sec wf-compose");
    sec.id = "wfCompose";
    return sec;
  }
  const WORK_ID = /^[0-9a-f]{12}$/; // 작업 id(서버 works.ID) — 앱이 그 작업을 여는 주소 = /#w=<작업 id>(app.js 「주소의 작업」)
  function madeWorks(t) { // 조립한 워크플로우를 쓰는 작업들(서버의 uses — 지금 워크플로우로 둔 것 먼저 · 앞 20개 · usesMore = 나머지 수) → 목록 줄의 셈 아래 한 줄 | null(없음 · uses 를 안 주는 옛 서버)
    // 작업마다 그 작업을 새 탭에서 여는 링크(이름 = 작업 리스트의 이름) · 프로젝트 · 라운드 · 꼬리표 「지금 워크플로우」(그동안 단계를 못 바꾸고 못 지움) / 「목록에만」(대시보드에서 목록에서 빼면 지울 수 있음)
    const rows = (Array.isArray(t.uses) ? t.uses : []).filter((u) => u && typeof u.wid === "string" && WORK_ID.test(u.wid));
    const more = Number.isInteger(t.usesMore) && t.usesMore > 0 ? t.usesMore : 0;
    if (!rows.length && !more) return null;
    const ul = h("ul", "wf-made-works");
    ul.setAttribute("aria-label", `쓰는 작업 — ${t.name}`);
    for (const u of rows) {
      const item = h("li"), now = u.active === true, a = link(`/#w=${u.wid}`, typeof u.name === "string" && u.name ? u.name : u.wid, "wf-made-work");
      item.dataset.use = now ? "current" : "listed";
      item.dataset.wid = u.wid;
      a.target = "_blank";
      a.rel = "noopener";
      a.title = now ? "이 작업을 새 탭에서 엽니다 — 이 작업의 지금 워크플로우입니다(그동안 이 워크플로우의 단계를 바꾸거나 지울 수 없습니다)"
        : "이 작업을 새 탭에서 엽니다 — 문서의 워크플로우 목록에만 든 줄입니다(대시보드 「이 문서의 워크플로우」 의 「목록에서 빼기」 로 빼면 지울 수 있습니다)";
      const where = [typeof u.project === "string" ? u.project : "", Number.isInteger(u.round) && u.round > 0 ? `라운드 ${u.round}` : ""].filter(Boolean).join(" · ");
      item.append(a);
      if (where) item.append(h("span", "wf-muted", where));
      item.append(h("span", "wf-made-tag", now ? "지금 워크플로우" : "목록에만"));
      ul.append(item);
    }
    if (more) ul.append(h("li", "wf-muted wf-made-more", `외 ${more}개`));
    return ul;
  }
  function composeDraw() {
    const sec = $("wfCompose");
    if (!sec) return;
    const h2 = h("h2"), can = composable(), off = () => { const p = h("p", "wf-lead wf-compose-off", NO_COMPOSE); p.setAttribute("role", "status"); return p; };
    h2.append(h("span", "wf-kind", "워크플로우 조립"), document.createTextNode("단계를 골라 새 워크플로우 만들기"));
    sec.replaceChildren(h2);
    sec.classList.remove("wf-wide"); // 폼 | 도구 설명 열이 설 때만 넓은 절(helpWrap 이 붙인다 — ② §18-15)
    if (!can) composing = null;
    navToolsDraw(); // 목차의 「워크플로우 도구」 — 폼을 열고 닫으면 따르는 폼 · 틀이 바뀐다
    if (!T) { sec.append(off()); return; }
    headHelp(sec, h2, "워크플로우 조립 — 설명", "문서 입출력(「1」 · 「1 → N」 · 「N → 1」)을 고르고, 단계를 묶음 › 줄로 놓아 이름을 붙이면 새 워크플로우가 됩니다 — 행이 위에서 아래로 차례이고, 행마다 목적 문서 칸 · 원본 문서 칸이 있습니다. "
      + "한 행의 두 칸에 줄이 서면 같은 차례(같이)이고, 한쪽이 빈칸이면 그 문서는 그 차례에 기다립니다. 줄은 마우스로 끌어 다른 행 · 다른 칸 · 다른 묶음에 놓습니다(빈칸에 놓으면 그 행의 줄과 같은 차례 · 행 사이에 놓으면 제 차례) — ▲ ▼ 로도 제 칸에서 한 걸음씩 옮깁니다(옆 칸의 줄은 그대로). "
      + "같은 줄을 여러 번 놓을 수 있습니다(뒤의 줄은 그 차례에 다시 보고, 할 것이 없으면 지나갑니다). 같은 차례에 놓은 두 문서의 줄은 함께 돕니다 — 한쪽이 바꾸는 문서를 다른 쪽이 기준으로 보는 짝(원본 문서의 작성요령 삭제와 목적 문서의 프로젝트 구성 반영 같은)은 차례로 돕니다. "
      + "상대 문서가 있어야 하는 줄(자리 연결 · 넣기 계획 · 내용 반영 …)은 두 칸에 쌍으로 놓입니다 — 어느 칸에서 골라도 쌍으로 들어갑니다. 워크플로우 전체에 한 번 하는 줄(구성 불러오기 · 프로젝트 구성 추출)은 한 칸에 서고 다른 칸으로 옮길 수 있습니다. "
      + "「…와 같이」 는 다른 문서가 하는 줄을 그 옆 칸(같은 차례)에 넣어 줍니다. "
      + "맨 앞 묶음에는 「준비」(문서 칸)가 저절로 섭니다. 수가 1인 문서 칸에는 기본 문서(저장한 양식 — 기본값 · 고정)를 걸 수 있습니다. 만든 워크플로우는 시작 화면의 카드 · 이 지도 · 대시보드에 섭니다.");
    if (T.broken) { // 저장 파일을 못 읽음 — 서버는 목록을 비워 보내고 그 파일을 덮지 않으려고 쓰지 않는다(만들기 · 고치기 · 지우기 모두 409)
      const p = h("p", "wf-compose-broken", "저장 파일(tasks.json)을 읽지 못했습니다 — 조립한 워크플로우가 목록에 보이지 않고, 그 파일을 덮지 않으려고 서버가 새로 만들거나 고친 것을 저장하지 않습니다. 파일을 고치거나 옮긴 뒤 이 페이지를 다시 읽으세요.");
      p.setAttribute("role", "alert");
      sec.append(p);
    }
    const list = h("ul", "wf-made-list");
    for (const t of T.tasks) {
      const li = h("li"), chips = h("span", "wf-links"), edit = h("button", "btn sm", "고치기"), del = h("button", "btn sm", "지우기"), a = assignOf(t);
      const n = t.inUse || 0, m = t.listed || 0, lock = lockOf(t), no = delOf(t); // n = 지금 워크플로우로 둔 작업(옛 서버는 목록 줄까지 센 수) · m = 문서의 워크플로우 목록에만 든 작업
      li.dataset.task = t.key;
      if (a) for (const role of ROLES) { // 문서마다 고른 단계 — 「원본: 문서 검토 · 목적: 문서 검토 · 구성 맞추기 …」
        const grp = h("span", "wf-made-role"), ids = ordered(a[role]);
        grp.dataset.role = role;
        grp.append(h("span", "wf-muted", role === "source" ? "원본:" : "목적:"));
        if (!ids.length) grp.append(h("span", "wf-muted", "—"));
        for (const id of ids) grp.append(h("span", "wf-chip", stageName(id)));
        chips.append(grp);
      } else if (t.v === 2 && Array.isArray(t.flow)) { // 줄 목록으로 조립한 것(배정 없음 — 취합형 · 표준 차례가 아닌 이관형) — 묶음 이름을 차례대로
        const grp = h("span", "wf-made-role");
        grp.append(h("span", "wf-muted", "묶음:"), ...t.flow.map((g) => h("span", "wf-chip", g.name || g.id)));
        chips.append(grp);
      } else { // assign 을 모르는 옛 서버 — 고른 단계(합집합)만 그대로
        const grp = h("span", "wf-made-role");
        grp.append(h("span", "wf-muted", "단계:"), ...ordered(t.stages || []).map((id) => h("span", "wf-chip", stageName(id))));
        chips.append(grp);
      }
      edit.type = del.type = "button";
      edit.disabled = !can;
      edit.title = !can ? NO_COMPOSE : lock ? `이름 · 설명 · 전제만 고칩니다\n${lock}` : "이름 · 설명 · 고른 단계 · 전제를 고칩니다"; // 잠금 = 서버의 editWhy(지금 워크플로우로 둔 작업이 있을 때만 — 목록에만 든 작업은 단계를 막지 않는다)
      edit.addEventListener("click", () => composeOpen(t.key));
      del.disabled = !!no;
      del.title = no || "이 워크플로우를 지웁니다(단계 · 도구는 그대로)"; // 까닭 = 서버의 deleteWhy 그대로(DELETE 409 와 같은 글 — 목록에만 든 작업도 센다: 목록 줄은 워크플로우를 바꿔도 남는다)
      del.addEventListener("click", () => composeDelete(t));
      const io = ((Array.isArray(T.shapes) ? T.shapes : []).find((x) => x && x.id === (t.shape || "relay")) || {}).io; // 문서 입출력의 꼴(「1 → 1」 — ② §18-8)
      li.append(link(`#${t.key}`, t.name, "wf-over-name"), h("span", "wf-muted", `${io ? `${io} · ` : ""}${t.sourceName} → ${t.targetName}`), chips);
      for (const [use, k, text, tip] of [["current", n, `하던 작업 ${n}개`, t.listed !== undefined ? "이 워크플로우를 지금 워크플로우로 둔 작업" : "이 워크플로우로 하던 작업(문서의 워크플로우 목록에 든 것 포함)"],
        ["listed", m, `목록에 든 작업 ${m}개`, "문서의 워크플로우 목록(대시보드 「이 문서의 워크플로우」)에만 든 작업 — 지금 워크플로우는 다른 것입니다. 그 목록에서 빼면 지울 수 있습니다"]]) { // 0 이면 안 보임
        if (!k) continue;
        const s = h("span", "wf-made-use", text);
        s.dataset.use = use;
        s.title = tip;
        li.append(s);
      }
      li.append(edit, del);
      const who = madeWorks(t); // 그 작업들 — 셈 아래 줄(링크 · 꼬리표)
      if (who) li.append(who);
      list.append(li);
    }
    if (T.tasks.length) sec.append(list);
    if (!can) sec.append(off()); // cells 를 주지 않는 서버 — 폼을 열지 않는다(목록은 읽기만)
    else if (!composing) {
      const make = h("button", "btn primary", "새 워크플로우 조립");
      make.type = "button";
      make.dataset.wfCompose = "open";
      make.addEventListener("click", () => composeOpen(""));
      sec.append(make);
    } else sec.append(helpWrap(composeForm(), composing, sec)); // 폼 | 도구 설명 열(② §18-15)
    const no = h("details", "wf-blocked"), ul = h("ul");
    no.append(h("summary", "", "아직 조립할 수 없는 것"));
    for (const b of T.blocked || []) { const li = h("li"); li.append(h("b", "", b.name), document.createTextNode(` — ${b.why}`)); ul.append(li); }
    no.append(ul);
    sec.append(no);
  }
  // ---- 단계(묶음 › 줄) — 정의 v2(spec_워크플로우 ② §18-5 · §18-6 · design.md §22): 묶음마다 이름 · 차례 · 줄(＋ 줄 · 하는 문서 · ▲▼ · 빼기) · 「＋ 묶음」.
  // 고를 줄 = 서버의 units(GET /api/tasks?v=2 — 사는 단계 · 놓을 자리 · 하는 문서 · 유료 · 문서 바뀜 · 서버가 돌리나) · 검사는 늘 서버(POST /api/tasks/check — 화면은 셈하지 않고 거절 · 경고를 그대로 보인다).
  // 표(문서 역할 × 단계 — 아래 「표준 차례로 채우기」)에서 고르면 줄 목록이 그 표준 차례로 다시 채워진다(mode std — 저장은 옛 꼴 assign). 줄을 고치면 mode lines(저장은 flow).
  const flowCopy = (flow) => (flow || []).map((g) => ({ ...g, steps: (g.steps || []).map((s) => ({ ...s, on: [...(s.on || [])] })) }));
  // 틀마다의 고를 줄(spec_워크플로우 ② §18-13 갈래 「라」 ⓶) — 취합형(N → 1)은 서버의 byShape.gather{units, homes, flow(처음 줄 목록), pairs} · 이관형은 units · stages 그대로. 같은 key 의 줄도 틀마다 다르다(취합의 「프로젝트 구성 반영」 은 목적 문서에만) — 줄은 늘 그 폼의 틀로 찾는다
  const shapeBox = (c) => (c && !c.single && c.shape && T && T.byShape && T.byShape[c.shape]) || null;
  const unitsOf = (c) => { // 그 폼의 틀이 놓을 수 있는 줄 — 문서 하나의 틀은 줄 이름을 고른 문서 종류의 것으로(서버 byShape.single.names[종류] — 연차보고서는 「프로젝트 구성 값 정하기」 · 「반영」 처럼 이름이 다르다: 한 번만 지어 둔다)
    const b = shapeBox(c);
    if (!(b && Array.isArray(b.units))) return T && Array.isArray(T.units) ? T.units : [];
    const kind = oneDoc(c) ? String(c.pair || "").split(">")[1] || "" : "", names = kind && b.names && b.names[kind];
    if (!names) return b.units;
    const by = b.unitsBy || (b.unitsBy = {});
    const bases = (b.baseNames && b.baseNames[kind]) || {}; // 그 문서 종류의 기본 이름(② §18-19 「도구 이름 고치기」 — 고친 도구의 「기본 이름」 으로 보인다)
    return by[kind] || (by[kind] = b.units.map((u) => (names[u.key] ? { ...u, name: names[u.key], ...(bases[u.key] ? { base: bases[u.key] } : {}) } : u)));
  };
  const unitOf = (k, c) => unitsOf(c).find((u) => u.key === k) || null;
  const lineName = (s, c) => s.name || (unitOf(s.unit, c) || {}).name || s.unit;
  function shapeFlow(c) { // 틀을 바꿈 — 줄 목록을 그 틀의 처음 것으로: 취합형 = 서버의 처음 줄 목록(붙박이 「사업계획서 취합」 의 묶음 · 줄 — 줄 목록으로 저장) · 이관형 = 표에서 고른 표준 차례(stdFill 이 채운다) ·
    // 문서 하나 = 고른 문서 종류의 처음 줄 목록(서버의 byShape.single.flows[종류] — 사업계획서 = 「양식 표준화」 의 줄 · 연차보고서 = 「양식 맞추기」 의 줄)
    const b = shapeBox(c), kind = String(c.pair || "").split(">")[1] || "", flow = b && ((b.flows && Array.isArray(b.flows[kind]) && b.flows[kind]) || b.flow);
    if (Array.isArray(flow)) { c.flow = flowCopy(flow); c.mode = "lines"; } else c.mode = "std";
  }
  // 문서 하나의 틀(「1」 — 조립 폼의 shape single: spec_워크플로우 ② §18-13 갈래 「라」 — 문서 하나) = 문서 칸이 하나(목적 문서)다 — 줄 편집기는 **한 칸**으로 서고 모든 줄이 그 칸의 카드다(저장 줄의 on 은 늘 빈 목록 · 같은 차례 · 쌍 줄 · 줄의 칸이 없다).
  // c.single(「단계 만들기」 폼의 표지)과 다른 것이다 — 그 폼은 이관형의 줄을 두 칸으로 놓는다.
  const oneDoc = (c) => !!c && !c.single && c.shape === "single";
  const ROLE_SHORT = { source: "원본", target: "목적" };
  const STALE = Symbol("stale"); // 늦게 온 검사 답 — 그 뒤에 새 검사를 걸었거나 그 사이 틀 · 문서 종류를 바꿨다: 버린다(2026-11-20 검토에서 짚음 — 이관의 표준 차례 답이 취합으로 바꾼 폼의 줄 목록을 덮었다)
  async function composeCheck(c, body) { // 서버의 조립 검사 → c.check {errors, warns, flow, std, sig} | STALE(늦게 온 답) — 기다리는 동안 「검사하는 중」
    const seq = (c.checkSeq = (c.checkSeq || 0) + 1);
    c.checking = true;
    if (c.linesBox) linesDraw(c);
    let got = null;
    try { const r = await fetch("/api/tasks/check", { method: "POST", headers: JSON_H, body: JSON.stringify(body) }); got = r.ok ? await r.json() : null; } catch { got = null; }
    if (composing !== c) return null;
    if (c.checkSeq !== seq || (body.shape && body.shape !== c.shape) || (body.target !== undefined && `${body.source}>${body.target}` !== c.pair)) return STALE;
    c.checking = false;
    c.check = got || { errors: ["조립 검사를 읽지 못했습니다 — 서버를 다시 켠 뒤에 쓸 수 있습니다"], warns: [], flow: null, std: false };
    return got;
  }
  async function stdFill(c) { // 표에서 고른 배정 → 그 표준 차례의 줄 목록(서버가 등록부로 짓는 것 그대로)
    const [source, target] = c.pair.split(">"), assign = { source: ordered(c.assign.source), target: ordered(c.assign.target) };
    if (c.llm && sameAssign(assign, c.from)) assign.llm = [...c.llm]; // 연 때 그대로 — 서버가 준 llm(옛 줄의 「원본만」 도)
    const got = await composeCheck(c, { assign, source, target, shape: c.shape });
    if (composing !== c || got === STALE) return; // 그 사이 틀 · 문서 종류를 바꿨거나 새 검사를 걸었다 — 이 답으로 줄 목록을 덮지 않는다
    if (got && got.flow) c.flow = flowCopy(got.flow);
    c.mode = "std";
    linesDraw(c);
  }
  function linesChanged(c) { // 줄을 고침 — 줄 목록으로 저장(mode lines) · 잠깐 뒤 서버 검사(예약은 폼마다 — 조립 폼과 단계 폼을 함께 펴 두어도 서로의 예약을 지우지 않는다)
    c.mode = "lines";
    clearTimeout(c.checkTimer);
    c.checking = true;
    linesDraw(c);
    if (c.single) { c.checkTimer = setTimeout(async () => { await stageCheck(c); linesDraw(c); }, 250); return; } // 단계 폼 — 단계의 검사(POST /api/stages/check)
    c.checkTimer = setTimeout(async () => { await composeCheck(c, { flow: c.flow, key: c.key || undefined, ...(c.key ? {} : { source: c.pair.split(">")[0], target: c.pair.split(">")[1], shape: c.shape }) }); linesDraw(c); }, 250);
  }
  function lineBtn(text, label, fn, off) {
    const b = h("button", "btn sm wf-lines-btn", text);
    b.type = "button"; b.title = label; b.setAttribute("aria-label", label); b.disabled = !!off;
    b.addEventListener("click", fn);
    return b;
  }
  // 줄 하나 = 문서 하나의 줄(spec_워크플로우 ② §18-6 「같이 · 따로」 · design.md §22 — 2026-11-20 사용자 「왼쭉은 예로 목적문서이면 우측은 원본문서 별로 도구 설정을 하도록 해야지. 공통은 공통으로 두고」 ·
  // 「원본 문서는 왜 네 맘대로 빼냐? 목적문서랑 원본 문서도 분리해서 따로 따로 하게 해줘야지」 · 「프로젝트 구성 반영을 왜 한줄에 놓냐, 따로따로 넣도록해야지. 왜 같이 묶냐고」 ·
  // 「프로젝트 구성을 완료하고 문서 검토하고 다른문서 프로젝트 구성할 수도 있잖아」): 차례는 위에서 아래로 하나이고 문서끼리의 차례는 자유다.
  // 번호 | 목적 문서 칸 | 원본 문서 칸(▲ ▼ 빼기는 카드마다 — 전의 줄 끝 단추 칸은 없앴다). 문서 줄 = 그 문서 칸의 카드(이름 + 꼬리표) · 사람이 하는 일은 카드 아래에 이름 · 글 ·
  // 문서마다의 줄이 아닌 줄(원본 → 목적 · 워크플로우 전체)은 **쌍 줄** — 두 문서 칸에 하나씩 그린다(아래 「대상 잇기」 — 전의 두 칸에 걸친 「공통」 한 칸은 없앴다).
  // 줄을 어느 행 · 어느 칸에 두는가(같은 차례 · 빈칸 · 따로 옮기기 · 끌어 놓기 · 저장 꼴)는 바로 아래 「행 × 두 칸」 이 정한다 — 여기 적혀 있던 「저장 줄이 두 문서면 두 줄로 보인다」 · 「…와 같이 = 그 줄 아래에 따로」 는 그 절이 바꿨다.
  // 넣기는 문서마다 따로(addRowEl — 「＋ 목적 문서 줄 넣기…」 · 「＋ 원본 문서 줄 넣기…」: 그 묶음에 제 행으로 — 그 줄이 쓰는 앞 줄이 그 묶음에 있으면 그 뒤 · 없으면 끝 / 쌍 줄은 어느 칸의 고르기에서든 · 이미 놓은 줄도 한 번 더 놓는다) · 「…와 같이」 는 다른 문서가 하는 줄을 그 옆 칸(같은 차례)에 넣어 주는 한 번짜리 단추.
  const LINE_COLS = ["target", "source"]; // 열의 차례 — 왼쪽 목적 문서 · 오른쪽 원본 문서(사용자 말 — 저장하는 on 의 차례는 그대로 원본 → 목적)
  // ---- 행 × 두 칸(spec_워크플로우 ② §18-6 「행 × 두 칸」 · design.md §22 — 위의 「줄 하나 = 문서 하나의 줄」 을 바꿈. 2026-11-20 사용자 「좌우가 같이 움직이잖아」 ·
  // 「각 도구가 같더라도 다른 시간 순서대로 적용할 수 있게 해야 하는데 지금은 그 배치가 안됨 … 마우스로 클릭 해서 드래그 해서 움직일 수도 있고 다음단계는 공백/즉 다른문서만 작업하고 기다릴 수도 있게」 ·
  // 「이걸 같이 실행할 수 있는 기능이 없음. 그리고 도구는 1번 이상 선택할 수 있어야지 한번 하고 두번 선택이 안되냐」):
  // 묶음 = 행(차례 — 위에서 아래로)의 목록 · 행 = 목적 문서 칸 | 원본 문서 칸. 칸마다 줄 하나(카드)나 빈칸 — 한 행에 두 문서의 줄이 서면 **같은 차례**(같이), 한쪽이 빈칸이면 그 문서는 그 차례에 기다린다.
  // 카드는 **제 칸에서 따로** 움직인다(▲ ▼ · 끌어 놓기 — 옆 칸의 줄은 그대로) · 다른 문서 칸에 끌어 놓으면 그 문서의 줄이 된다(그 줄을 그 문서에 놓을 수 있을 때) · 같은 줄을 여러 번 놓을 수 있다(서버 검사가 경고로 알린다).
  // 상대 문서가 있어야 하는 줄(원본 → 목적 · 워크플로우 전체 — 쌍 줄)은 두 칸을 다 쓰는 한 행이다(행째 옮긴다).
  // 저장 꼴은 줄 목록 그대로다(c.flow — 묶음 › 줄 {unit, on[]}) — 행은 그것을 편 꼴이고(rowsOf) 고치면 그 묶음만 다시 접는다(stepsOf — 안 건드린 묶음은 저장 줄 그대로: 표준 차례가 유지된다):
  //   한 행의 두 칸이 같은 줄 = 저장 줄 하나(on 둘 — 서버가 두 문서를 함께 한다) · 다른 줄 = 저장 줄 둘(원본 → 목적 — 둘째에 `beside: true`: 앞 줄과 같은 차례) · 한 칸뿐 = 저장 줄 하나(on 하나) · 두 칸 다 빈 행은 없다.
  // 워크플로우 전체 줄(구성 불러오기 · 프로젝트 구성 추출 — place flow)도 **한 칸 카드**다(2026-11-20 사용자 「양쪽에 걸쳐 있는 것들은 왜 분리가 안되고 붙어 있나? 의미가 없는데」 — 전에는 두 칸에 걸친 쌍 줄):
  //   처음 서는 칸 = 서버의 units[].col(구성 불러오기 = 목적 문서 · 프로젝트 구성 추출 = 구성의 기준 문서) · 다른 칸에 놓으면 저장 줄에 `col` · 옆 칸은 빈칸(다른 줄을 놓을 수 있다 — 같은 차례). 쌍 줄로 남는 것은 원본 → 목적 줄(place pair)뿐이다.
  const WIDE = Symbol("wide"); // 카드가 워크플로우 전체 줄이면 그 줄이 처음 서는 칸(글자 키가 아니라 서버로 가지 않는다)
  const ONE = Symbol("one"); // 카드가 문서 하나의 틀의 줄이면 참 — 접을 때 on 을 빈 목록으로(oneDoc)
  const colsOf = (c) => (oneDoc(c) ? ["target"] : LINE_COLS); // 그 폼의 문서 칸(문서 하나의 틀 = 목적 문서 칸 하나)
  const cardOf = (s) => { const { on, beside, col, ...card } = s; return card; }; // 저장 줄 → 카드(하는 문서 · 같은 차례 표시 · 선 칸은 행이 지닌다)
  const sameCard = (a, b) => a.unit === b.unit && (a.unit !== "hand" || (!!a.id && a.id === b.id && (a.name || "") === (b.name || "") && (a.note || "") === (b.note || ""))); // 저장 줄 하나(on 둘)로 접을 수 있나 — 사람이 하는 일은 같은 줄을 편 것일 때만(따로 넣은 두 줄은 저마다 「했음」)
  function rowsOf(c, g) { // 묶음의 저장 줄 → 행 [{line: 저장 줄(쌍 줄 · none = 할 문서가 없는 옛 문서 줄)} | {target?: 카드, source?: 카드}]
    const rows = [];
    if (oneDoc(c)) return g.steps.map((s) => ({ target: Object.assign(cardOf(s), { [ONE]: true }) })); // 문서 하나의 틀 — 줄마다 그 한 칸의 카드(행 하나)
    for (const s of g.steps) {
      const u = unitOf(s.unit, c), roles = ROLES.filter((r) => s.on.includes(r));
      if (u && u.place === "flow") { // 워크플로우 전체 줄 — 한 칸 카드: 적힌 칸(col) · 없으면 처음 서는 칸
        const home = ROLES.includes(u.col) ? u.col : "target", r = ROLES.includes(s.col) ? s.col : home, o = ROLES.find((x) => x !== r), last = rows[rows.length - 1], card = Object.assign(cardOf(s), { [WIDE]: home });
        if (s.beside && last && !last.line && last[o] && !last[r]) last[r] = card; else rows.push({ [r]: card });
        continue;
      }
      if (!u || u.place !== "doc") { rows.push({ line: s }); continue; }
      if (!roles.length) { rows.push({ line: s, none: true }); continue; }
      if (roles.length === 2) { rows.push({ source: cardOf(s), target: cardOf(s) }); continue; }
      const last = rows[rows.length - 1], r = roles[0], o = ROLES.find((x) => x !== r);
      if (s.beside && last && !last.line && last[o] && !last[r]) last[r] = cardOf(s); else rows.push({ [r]: cardOf(s) }); // 앞 줄과 같은 차례 — 바로 앞의 다른 문서 줄 옆 칸에(서버 _beside_fix 와 같은 조건)
    }
    return rows;
  }
  function stepsOf(rows) { // 행 → 저장 줄(빈 행은 없어진다)
    const out = [];
    for (const row of rows) {
      if (row.line) { out.push(row.line); continue; }
      const S = row.source, D = row.target, step = (x, r) => (x[ONE] ? { ...x, on: [] } : x[WIDE] ? { ...x, on: [], ...(r !== x[WIDE] ? { col: r } : {}) } : { ...x, on: [r] }); // 문서 하나의 틀의 줄 = on 없이 · 워크플로우 전체 줄 = on 없이(처음 서는 칸이 아니면 col)
      if (S && D && !S[WIDE] && !D[WIDE] && sameCard(S, D)) { out.push({ ...S, on: ["source", "target"] }); continue; }
      const pairs = [["source", S], ["target", D]].filter(([, x]) => x);
      if (pairs.length === 2 && D[WIDE] && !S[WIDE]) pairs.reverse(); // 같은 차례의 저장 차례 = 원본 → 목적 · 워크플로우 전체 줄(구성 확정 …)이 문서 줄과 함께면 그 줄이 먼저(문서 줄이 그 결과를 쓴다)
      pairs.forEach(([r, x], i) => out.push({ ...step(x, r), ...(i ? { beside: true } : {}) }));
    }
    return out;
  }
  const liveRows = (rows) => rows.filter((r) => r.line || r.target || r.source);
  function cardStep(c, gi, ri, role, d) { // 카드의 ▲ ▼ — 제 칸에서 한 걸음(옆 칸의 줄은 그대로): 같은 차례에 선 카드는 먼저 제 행으로 나오고, 혼자 선 카드는 위 · 아래 행의 제 칸으로(빈칸이면 같은 차례로 · 줄이 있으면 자리 바꿈 · 쌍 줄은 넘는다 · 묶음 끝이면 옆 묶음으로)
    const flow = c.flow, g = flow[gi], rows = rowsOf(c, g), row = rows[ri], x = row && !row.line && row[role], o = ROLES.find((r) => r !== role);
    if (!x) return;
    let to = { gi, rows, row };
    if (row[o]) { delete row[role]; to.row = { [role]: x }; rows.splice(d < 0 ? ri : ri + 1, 0, to.row); }
    else {
      const next = rows[ri + d];
      if (!next) {
        const g2 = flow[gi + d];
        if (!g2) return;
        const rows2 = rowsOf(c, g2);
        rows.splice(ri, 1);
        if (d < 0) rows2.push(row); else rows2.unshift(row);
        g2.steps = stepsOf(rows2);
        to = { gi: gi + d, rows: rows2, row };
      } else if (next.line) { rows[ri] = next; rows[ri + d] = row; }
      else if (!next[role]) { next[role] = x; rows.splice(ri, 1); to.row = next; }
      else { row[role] = next[role]; next[role] = x; to.row = next; }
    }
    g.steps = stepsOf(rows);
    c.focusLf = `${d < 0 ? "▲" : "▼"}:${to.gi}:${liveRows(to.rows).indexOf(to.row)}:${role}`; // 초점은 옮긴 카드를 따라간다
    linesChanged(c);
  }
  function rowStep(c, gi, ri, d) { // 쌍 줄(행째)의 ▲ ▼ — 위 · 아래 행과 자리 바꿈 · 묶음 끝이면 옆 묶음으로
    const flow = c.flow, g = flow[gi], rows = rowsOf(c, g), row = rows[ri];
    if (!row) return;
    let to = { gi, ri: ri + d };
    if (rows[ri + d]) { rows[ri] = rows[ri + d]; rows[ri + d] = row; }
    else {
      const g2 = flow[gi + d];
      if (!g2) return;
      const rows2 = rowsOf(c, g2);
      rows.splice(ri, 1);
      if (d < 0) rows2.push(row); else rows2.unshift(row);
      g2.steps = stepsOf(rows2);
      to = { gi: gi + d, ri: d < 0 ? rows2.length - 1 : 0 };
    }
    g.steps = stepsOf(rows);
    c.focusLf = `${d < 0 ? "▲" : "▼"}:${to.gi}:${to.ri}:c`;
    linesChanged(c);
  }
  function cardDrop(c, gi, ri, role) { // 빼기 — 그 칸만 비운다(옆 칸의 줄은 남는다 · 행이 비면 행도 없어진다) · role 이 없으면 행째(쌍 줄)
    const g = c.flow[gi], rows = rowsOf(c, g);
    if (!rows[ri]) return;
    if (role) delete rows[ri][role]; else rows.splice(ri, 1);
    g.steps = stepsOf(rows);
    linesChanged(c);
  }
  // 끌어 놓기 — 카드의 머리(.wf-card-head)를 끌어 다른 행 · 다른 칸 · 다른 묶음에: 행의 빈칸에 놓으면 그 행의 줄과 **같은 차례**, 행 사이(행의 위 · 아래 가장자리)에 놓으면 **제 행**(옆 칸은 빈칸 = 그 문서는 기다린다).
  let drag = null; // 끌고 있는 것 {c, gi, ri, role(문서 줄의 칸) | ""(쌍 줄 — 행째), key(지금 보인 놓을 자리)} | {c(목록이 따르는 폼), unit(목차의 「워크플로우 도구」 에서 끌어 온 새 도구 — navToolEl), key}
  function dropClear(c) { if (c.linesBox) for (const x of c.linesBox.querySelectorAll("[data-drop]")) { delete x.dataset.drop; delete x.dataset.dropCol; } }
  function dragEnd(c) {
    drag = null;
    dropClear(c);
    if (c.linesBox) c.linesBox.classList.remove("wf-dragging");
    if (c.redraw) linesDraw(c); // 끄는 동안 미뤄 둔 다시 그리기(서버 검사가 끝남)
  }
  function dropFindNew(c, gi, ol, e) { // 목차의 「워크플로우 도구」 에서 끌어 온 도구(새 줄 — navToolsDraw) → 놓을 자리(카드 끌기와 같은 셈): 놓을 칸 = 가리킨 칸(그 도구를 그 문서에 놓을 수 있을 때 · 아니면 놓을 수 있는 문서) · 쌍 줄은 행째(제 행으로만)
    const u = unitOf(drag.unit, c), t = e.target instanceof Element ? e.target : null, rows = rowsOf(c, c.flow[gi]);
    if (!u || u.server === false) return null; // 아직 서버가 못 돌리는 도구(넣기 고르기에서도 꺼짐)
    let role = "";
    if (oneDoc(c)) role = "target";
    else if (u.place !== "pair") {
      const cell = t && t.closest(".wf-line-cell[data-role], .wf-line-colname[data-role]"), box = ol.getBoundingClientRect(), roles = Array.isArray(u.roles) ? u.roles.filter((r) => ROLES.includes(r)) : [];
      const col = cell && ol.contains(cell) ? cell.dataset.role : LINE_COLS[e.clientX < box.left + box.width / 2 + 15 ? 0 : 1];
      role = u.place === "flow" || roles.includes(col) ? col : LINE_COLS.find((r) => roles.includes(r)) || ""; // 워크플로우 전체 줄은 어느 칸에나 · 한 문서에만 놓는 도구는 그 문서 칸으로
      if (!role) return null;
    }
    const li = t && t.closest("li.wf-line");
    if (!li || !ol.contains(li)) return { gi, kind: "gap", at: t && t.closest(".wf-line-cols") ? 0 : rows.length, role };
    const ri = +li.dataset.ri, row = rows[ri], r = li.getBoundingClientRect(), edge = Math.min(8, r.height / 4);
    if (role && row && !row.line && !row[role] && e.clientY > r.top + edge && e.clientY < r.bottom - edge) return { gi, kind: "in", ri, role };
    return { gi, kind: "gap", at: ri + (e.clientY > r.top + r.height / 2 ? 1 : 0), role };
  }
  function dropAdd(c, key, to) { // 목차에서 끌어 온 도구 → 그 자리에 새 줄(넣기 고르기가 넣는 저장 줄과 같은 꼴 — 쌍 줄 {unit, on: []} · 사람이 하는 일은 이름 · 글을 빈 채로) · 놓은 도구의 설명을 오른쪽 열에
    const u = unitOf(key, c), g = c.flow[to.gi];
    if (!u || !g) return;
    const rows = rowsOf(c, g), at = to.kind === "in" ? to.ri : to.at;
    if (u.place === "pair") rows.splice(at, 0, { line: { unit: u.key, on: [] } });
    else {
      const card = u.kind === "hand" ? { unit: "hand", name: "사람이 하는 일", note: "" } : { unit: u.key };
      if (oneDoc(c)) card[ONE] = true; else if (u.place === "flow") card[WIDE] = ROLES.includes(u.col) ? u.col : "target"; // 워크플로우 전체 줄 — 처음 서는 칸이 아니면 접을 때 col
      const row = to.kind === "in" ? rows[to.ri] : null;
      if (row && !row.line && !row[to.role]) row[to.role] = card; else rows.splice(at, 0, { [to.role]: card });
    }
    g.steps = stepsOf(rows);
    if (c.helpBox) c.help = u.key;
    linesChanged(c);
  }
  function dropFind(c, gi, ol, e) { // 놓을 자리 → {gi, kind: "in"(그 행의 빈칸 — 같은 차례로), ri, role} | {gi, kind: "gap"(행 사이 — 제 행으로), at, role} | null(이 폼에서 끄는 것이 아님)
    if (drag && drag.unit) return drag.c === c && c.flow[gi] ? dropFindNew(c, gi, ol, e) : null; // 목차에서 끌어 온 새 도구
    if (!drag || drag.c !== c || !c.flow[drag.gi] || !c.flow[gi]) return null;
    const from = rowsOf(c, c.flow[drag.gi])[drag.ri], rows = rowsOf(c, c.flow[gi]), t = e.target instanceof Element ? e.target : null;
    if (!from || (drag.role ? !from[drag.role] : !from.line)) return null;
    let role = "";
    if (drag.role) { // 놓을 문서 칸 = 가리킨 칸의 문서(그 줄을 그 문서에 놓을 수 있을 때) · 아니면 지금 문서
      const u = unitOf(from[drag.role].unit, c), cell = t && t.closest(".wf-line-cell[data-role], .wf-line-colname[data-role]"), box = ol.getBoundingClientRect();
      const col = cell && ol.contains(cell) ? cell.dataset.role : LINE_COLS[e.clientX < box.left + box.width / 2 + 15 ? 0 : 1];
      role = oneDoc(c) ? "target" : from[drag.role][WIDE] || (u && Array.isArray(u.roles) && u.roles.includes(col)) ? col : drag.role; // 워크플로우 전체 줄은 어느 칸에나 · 문서 하나의 틀은 칸이 하나
    }
    const li = t && t.closest("li.wf-line");
    if (!li || !ol.contains(li)) return { gi, kind: "gap", at: t && t.closest(".wf-line-cols") ? 0 : rows.length, role };
    const ri = +li.dataset.ri, row = rows[ri], r = li.getBoundingClientRect(), edge = Math.min(8, r.height / 4);
    if (role && row && !row.line && !row[role] && e.clientY > r.top + edge && e.clientY < r.bottom - edge) return { gi, kind: "in", ri, role };
    return { gi, kind: "gap", at: ri + (e.clientY > r.top + r.height / 2 ? 1 : 0), role };
  }
  function dropShow(c, ol, to) { // 놓을 자리 표시 — 빈칸(강조 테두리) · 행 사이(그 문서 칸 폭의 굵은 금: 쌍 줄은 두 칸 폭)
    const key = `${to.gi}:${to.kind}:${to.kind === "in" ? to.ri : to.at}:${to.role}`;
    if (drag.key === key) return;
    dropClear(c);
    drag.key = key;
    const lis = [...ol.querySelectorAll(":scope > li.wf-line")];
    if (to.kind === "in") { const cell = lis[to.ri] && lis[to.ri].querySelector(`.wf-line-cell[data-role=${to.role}]`); if (cell) cell.dataset.drop = "in"; return; }
    const li = lis[to.at] || lis[lis.length - 1] || ol.querySelector(":scope > li.wf-line-empty");
    if (!li) return;
    li.dataset.drop = lis[to.at] ? "before" : lis.length ? "after" : "in";
    li.dataset.dropCol = to.role || "pair";
  }
  function dropApply(c, d, to) { // d = 끌던 것 — 줄 목록을 고친다(자리가 그대로면 다시 그리기만)
    if (d.unit) { dropAdd(c, d.unit, to); return; } // 목차에서 끌어 온 새 도구
    const flow = c.flow, a = flow[d.gi], b = flow[to.gi], rowsA = rowsOf(c, a), rowsB = a === b ? rowsA : rowsOf(c, b), src = rowsA[d.ri];
    if (!src) return;
    const was = JSON.stringify([a.steps, b.steps]);
    if (d.role) {
      const x = src[d.role];
      if (!x) return;
      delete src[d.role]; // 행은 그대로 둔다(자리 번호가 안 밀리게 — 빈 행은 접을 때 없어진다)
      const row = to.kind === "in" ? rowsB[to.ri] : null;
      if (row && !row.line && !row[to.role]) row[to.role] = x; else rowsB.splice(to.kind === "in" ? to.ri : to.at, 0, { [to.role]: x });
    } else { rowsA[d.ri] = {}; rowsB.splice(to.kind === "in" ? to.ri : to.at, 0, src); }
    a.steps = stepsOf(rowsA);
    if (b !== a) b.steps = stepsOf(rowsB);
    if (JSON.stringify([a.steps, b.steps]) !== was) linesChanged(c); else linesDraw(c);
  }
  function dropWire(c, gi, ol) { // 묶음의 줄 목록이 놓을 자리다(열 머리 · 줄 · 「줄이 없습니다」)
    ol.addEventListener("dragover", (e) => { const to = dropFind(c, gi, ol, e); if (!to) return; e.preventDefault(); e.dataTransfer.dropEffect = drag.unit ? "copy" : "move"; dropShow(c, ol, to); }); // 목차의 도구 = 새 줄(copy — 끌기 시작의 effectAllowed 와 같게)
    ol.addEventListener("dragleave", (e) => { if (drag && !(e.relatedTarget instanceof Node && ol.contains(e.relatedTarget))) { dropClear(c); drag.key = ""; } });
    ol.addEventListener("drop", (e) => { const to = dropFind(c, gi, ol, e), d = drag; if (!to || !d) return; e.preventDefault(); dragEnd(c); dropApply(c, d, to); });
  }
  // 대상 잇기(spec_워크플로우 ② §18-6 「대상 잇기」 — 2026-11-20 사용자 「이것들 어떤 도구는 대상이 있어야 사용할 수 있는게 있어 잘 연결될 수 있도록」 ·
  // 「열을 분할해줘, 대상이 있어야 하는 경우에는 2개를 쌍으로 넣을 수 있게 해주면 되잖아. .. 순차적임을 표현하기 위해 한쪽은 공백을 두고 다른 한쪽은 도구를 주고」): **대상 = 상대 문서**.
  // 상대 문서가 있어야 하는 줄(문서마다의 줄이 아닌 줄 — 원본 → 목적 · 워크플로우 전체)은 **쌍 줄**: 같은 줄을 목적 문서 칸과 원본 문서 칸 두 칸에 하나씩 그린다(전의 두 칸에 걸친 「공통」 한 칸 · 「＋ 공통 줄 넣기…」 는 없앴다) ·
  // 문서 줄은 한 칸만 채우고 다른 칸은 빈칸(차례가 위에서 아래로 보이게) · 두 문서 칸 사이에는 세로 금(workflow.css). 쌍 줄은 두 문서 칸의 고르기 어디서든 넣는다(옵션 글 「… (쌍)」 — 저장은 `{unit, on: []}` 한 줄 그대로).
  // 넣기의 자리 · 꺼짐 까닭(그 줄이 쓰는 앞 줄)은 **서버의 `units[].uses`**([{unit(그 줄이 쓰는 결과를 만드는 줄의 key), must(앞에 없으면 서버 검사가 거절)}])만 읽는다 — 규칙을 화면에 새로 적지 않는다(없으면 빈 것: 옛 서버 · 그 값을 안 주는 틀).
  const usesOf = (u) => (u && Array.isArray(u.uses) ? u.uses : []).filter((x) => x && typeof x.unit === "string");
  const usesHit = (c, p, x, role) => { // 저장 줄 p 가 x 가 가리키는 앞 줄인가 — 그 줄이 문서마다의 줄이면 같은 문서(role)에 닿는 것(쌍 줄이 쓰면 어느 문서든)
    const pu = unitOf(x.unit, c);
    return p.unit === x.unit && (!(pu && pu.place === "doc") || !role || p.on.includes(role));
  };
  function badgeEl(s, c) { // 이름 + 꼬리표(칸마다 새로 — 같은 노드를 두 칸에 둘 수 없다)
    const u = unitOf(s.unit, c), nm = h("span", "wf-line-name"), tags = h("span", "wf-badges");
    nm.append(h("b", "", lineName(s, c)));
    if (u && u.kind === "hand") tags.append(tag("사람", "human", "human"));
    if (u && u.paid) tags.append(builderPromptTag(u, c));
    if (u && u.change === "doc") tags.append(tag("문서 바뀜", "doc", "doc"));
    if (u && u.optional) tags.append(tag("선택", "soft"));
    if (u && u.only && u.only.label) { // 전용 표시(② §18-17 — 2026-11-20 사용자 「도구에 *** 전용 이라고 명시를 해야 한다고봄」): 카드에는 짧게 「전용」 — 가리키면 어느 문서 전용인지와 까닭(「도구 설명」 · 「에이전트」 열에는 다 적는다)
      const t = tag("전용", "only");
      t.title = `${u.only.label}${u.only.why ? ` — ${u.only.why}` : ""}`;
      t.dataset.only = u.only.kind || "";
      tags.append(t);
    }
    nm.append(tags);
    return nm;
  }
  function headEl(c, gi, ri, role, name, lock) { // 카드의 머리 — 끌 손잡이(점 여섯 SVG) + (부르는 쪽이 이름 · 꼬리표 · 단추를 잇는다). 머리째 끈다(role "" = 쌍 줄: 행째) · 잠긴 폼은 못 끈다
    const head = h("div", "wf-card-head"), grip = h("span", "wf-card-grip");
    grip.setAttribute("aria-hidden", "true");
    grip.innerHTML = '<svg viewBox="0 0 10 14" width="10" height="14" fill="currentColor"><circle cx="3" cy="3" r="1.15"/><circle cx="7" cy="3" r="1.15"/><circle cx="3" cy="7" r="1.15"/><circle cx="7" cy="7" r="1.15"/><circle cx="3" cy="11" r="1.15"/><circle cx="7" cy="11" r="1.15"/></svg>';
    head.append(grip);
    if (lock) return head;
    head.draggable = true;
    grip.title = "끌어서 옮기기 — 행의 빈칸에 놓으면 그 줄과 같은 차례, 행 사이에 놓으면 제 차례";
    head.addEventListener("dragstart", (e) => {
      drag = { c, gi, ri, role, key: "" };
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", name); } catch { /* 끌 글을 못 실어도 끌기는 된다 */ }
      setTimeout(() => { if (drag && drag.c === c && c.linesBox) c.linesBox.classList.add("wf-dragging"); }, 0); // 끄는 그림을 뜬 뒤에(빈칸의 점선 테두리가 그 그림에 안 들게)
    });
    head.addEventListener("dragend", () => { if (drag && drag.c === c) dragEnd(c); });
    return head;
  }
  function handEl(c, gi, ri, role, x, lock) { // 사람이 하는 일 — 이름 · 사람에게 보일 글(200자): 그 카드 아래
    const more = h("div", "wf-line-hand"), name = h("input"), note = h("input");
    const set = (k, v) => { const g = c.flow[gi], rows = rowsOf(c, g); if (!rows[ri] || rows[ri].line || !rows[ri][role]) return; rows[ri][role][k] = v; g.steps = stepsOf(rows); linesChanged(c); };
    name.value = x.name || ""; name.maxLength = 30; name.placeholder = "이름(예: 결과 확인)"; name.disabled = lock; name.setAttribute("aria-label", `${ROLE[role]}의 사람이 하는 일의 이름`); name.dataset.lf = `hname:${gi}:${ri}:${role}`;
    note.value = x.note || ""; note.maxLength = 200; note.placeholder = "사람에게 보일 글(예: 원본의 헤딩 판정을 보고 맞으면 「했음」)"; note.disabled = lock; note.setAttribute("aria-label", `${ROLE[role]}의 사람에게 보일 글`); note.dataset.lf = `hnote:${gi}:${ri}:${role}`;
    name.addEventListener("change", () => set("name", name.value.trim()));
    note.addEventListener("change", () => set("note", note.value.trim()));
    more.append(name, note);
    return more;
  }
  function rowEl(c, gi, ri, row, count, no, lock) { // 행 하나 — 번호 | 목적 문서 칸 | 원본 문서 칸. row = rowsOf 의 행 · count = 그 묶음의 행 수
    const flow = c.flow, li = h("li", "wf-line"), top = h("div", "wf-line-top"), up = ri > 0 || gi > 0, down = ri < count - 1 || gi < flow.length - 1;
    const acts = (role, name) => { // ▲ ▼ 빼기 — 문서 줄은 그 카드만(옆 칸의 줄은 그대로 — 같은 차례에 선 카드는 제 행으로 나올 수 있어 묶음 끝에서도 켜진다) · 쌍 줄은 행째. 글은 .sr-only 로 그대로 두고 아이콘으로
      const box = h("span", "wf-line-acts"), who = role ? `${ROLE[role]}의 ` : "", beside = !!role && !!row[ROLES.find((r) => r !== role)];
      const ico = (b, d, cls) => {
        const t = b.textContent, ic = h("span", "wf-icon");
        ic.setAttribute("aria-hidden", "true");
        ic.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
        b.classList.add("wf-act-ico", ...(cls ? [cls] : []));
        b.replaceChildren(ic, h("span", "sr-only", t));
        return b;
      };
      box.append(ico(lineBtn("▲", `${who}「${name}」 위로`, () => (role ? cardStep(c, gi, ri, role, -1) : rowStep(c, gi, ri, -1)), lock || !(up || beside)), '<path d="m6 15 6-6 6 6"/>'),
        ico(lineBtn("▼", `${who}「${name}」 아래로`, () => (role ? cardStep(c, gi, ri, role, 1) : rowStep(c, gi, ri, 1)), lock || !(down || beside)), '<path d="m6 9 6 6 6-6"/>'),
        ico(lineBtn("빼기", `${who}「${name}」 빼기`, () => cardDrop(c, gi, ri, role), lock), '<path d="M6 6 18 18M18 6 6 18"/>', "wf-act-del"));
      for (const b of box.querySelectorAll("button")) b.dataset.lf = `${b.textContent}:${gi}:${ri}:${role || "c"}`;
      return box;
    };
    li.dataset.ri = String(ri);
    top.append(h("span", "wf-line-no", String(no).padStart(2, "0")));
    if (row.line) { // 쌍 줄 · 할 문서가 없는 옛 문서 줄 — 저장 줄 하나가 행 하나
      const s = row.line, u = unitOf(s.unit, c), name = lineName(s, c);
      li.dataset.unit = s.unit;
      li.dataset.role = row.none ? "none" : "pair";
      if (row.none) { // 할 문서가 없는 옛 문서 줄(서버 검사가 「할 문서를 고르세요」 로 거절한다) — 두 칸에 걸친 한 칸에 까닭 글
        const cell = h("div", "wf-line-cell wf-line-none"), head = headEl(c, gi, ri, "", name, lock);
        head.append(badgeEl(s, c), h("span", "wf-muted", "할 문서가 없습니다 — 빼고 문서 칸에서 다시 넣으세요"), acts("", name));
        cell.append(head);
        top.append(cell);
      } else { // 쌍 줄 — 상대 문서가 있어야 하는 줄: 같은 줄을 두 문서 칸에 하나씩(원본 → 목적 = 원본 칸 「→ 목적 문서로」 · 목적 칸 「← 원본 문서에서」 / 워크플로우 전체 = 두 칸 모두) · 단추는 끝 칸에 한 벌
        const flowWide = !!u && u.place !== "pair";
        LINE_COLS.forEach((r, i) => {
          const cell = h("div", "wf-line-cell wf-line-pair"), head = headEl(c, gi, ri, "", name, lock);
          cell.dataset.role = r;
          cell.dataset.on = "1";
          head.append(badgeEl(s, c), h("span", "wf-line-hint", flowWide ? "워크플로우 전체" : r === "source" ? "→ 목적 문서로" : "← 원본 문서에서"));
          if (i === LINE_COLS.length - 1) head.append(acts("", name));
          cell.append(head);
          top.append(cell);
        });
      }
      li.append(top);
      return li;
    }
    li.dataset.unit = [...new Set(LINE_COLS.filter((r) => row[r]).map((r) => row[r].unit))].join("+"); // 그 행의 줄(두 칸이 다른 줄이면 「목적+원본」)
    li.dataset.role = row.target && row.source ? "both" : row.target ? "target" : "source";
    for (const r of colsOf(c)) { // 문서 줄 — 칸마다 카드나 빈칸(빈칸 = 그 문서는 이 차례에 기다린다 · 끌어 놓을 자리) · 문서 하나의 틀은 칸이 하나
      const x = row[r], cell = h("div", x ? "wf-line-cell wf-card" : "wf-line-cell wf-line-blank");
      cell.dataset.role = r;
      if (x) {
        const name = lineName(x, c), head = headEl(c, gi, ri, r, name, lock);
        cell.dataset.on = "1";
        cell.dataset.unit = x.unit;
        if (x[WIDE]) cell.dataset.wide = "1"; // 워크플로우 전체 줄 — 문서마다가 아니라 한 번 하는 일(작은 글로 알린다)
        head.append(badgeEl(x, c), ...(x[WIDE] ? [h("span", "wf-line-hint", "워크플로우 전체")] : []), acts(r, name));
        cell.append(head);
        if (x.unit === "hand") cell.append(handEl(c, gi, ri, r, x, lock));
      }
      top.append(cell);
    }
    li.append(top);
    return li;
  }
  function addRowEl(c, gi, lock) { // 묶음의 넣기 줄 — 줄과 같은 격자에: 목적 문서 칸 「＋ 목적 문서 줄 넣기…」 · 원본 문서 칸 「＋ 원본 문서 줄 넣기…」(고르면 그 묶음에 제 행으로 줄 하나 · 자리 = 그 줄이 쓰는 앞 줄이 이 묶음에 있으면 그 뒤, 없으면 묶음 끝: placeAt)
    // 고를 줄 = 그 틀의 줄(unitsOf — 그 문서에 놓을 수 있는 문서 줄 + 사람이 하는 일 + **쌍 줄**(원본 → 목적 · 워크플로우 전체 — 두 칸의 고르기 모두에 · 옵션 글 「… (쌍)」: 어느 칸에서 골라도 쌍으로 들어간다 — spec ② §18-6 「대상 잇기」)).
    // 아직 못 고르는 줄 · 꼭 있어야 하는 앞 줄(서버의 uses — must)이 이 묶음 · 앞 묶음에 없는 줄은 까닭과 함께 꺼짐. 이미 놓은 줄은 꺼지지 않는다 — 옵션 글 끝에 「 — 한 번 더」(같은 줄을 여러 번 놓을 수 있다: ② §18-6 「행 × 두 칸」)
    const box = shapeBox(c), homes = Object.fromEntries(box && Array.isArray(box.homes) ? box.homes.map((x) => [x.id, x.name]) : (T.stages || []).map((st) => [st.id, st.name])); // 줄이 사는 단계의 이름 — 취합형은 붙박이 취합의 묶음(1단계 프로젝트 구성 …)
    const units = unitsOf(c), g = c.flow[gi];
    const has = (unit, r) => (c.flow || []).some((x) => x.steps.some((s) => s.unit === unit && (!r || s.on.includes(r)))); // 흐름에 그 줄이 (그 문서에) 이미 있나
    // 그 줄이 쓰는 앞 줄(서버의 units[].uses 만 읽는다 — usesOf 위 「대상 잇기」 주석): 꺼짐 까닭 · 넣는 자리
    const isPair = (u) => u.place === "pair"; // 쌍 줄(상대 문서가 있어야 하는 줄 — 원본 → 목적: 두 칸을 다 쓴다)
    const anyDoc = (u) => u.place !== "doc"; // 어느 문서의 것도 아닌 줄(쌍 줄 · 워크플로우 전체 줄) — 두 칸의 고르기 모두에 있고, 앞 줄은 어느 문서의 것이든 본다
    const homeCol = (u) => (ROLES.includes(u.col) ? u.col : "target"); // 워크플로우 전체 줄이 처음 서는 칸(서버의 units[].col — 없으면 목적 문서 칸)
    const one = oneDoc(c); // 문서 하나의 틀 — 칸이 하나(목적 문서): 모든 줄이 그 칸에 서고 저장 줄의 on 은 빈 목록
    const roleOfKind = (u, kind) => (one || anyDoc(u) ? "" : kind); // 앞 줄을 찾을 문서 — 문서 줄은 그 문서 · 쌍 줄 · 워크플로우 전체 줄은 어느 문서든(문서 하나의 틀은 문서가 하나)
    const lacks = (u, kind) => usesOf(u).filter((x) => x.must && !(c.flow || []).slice(0, gi + 1).some((x2) => x2.steps.some((p) => usesHit(c, p, x, roleOfKind(u, kind))))); // 꼭 있어야 하는 앞 줄 가운데 이 묶음 · 앞 묶음에 없는 것(문서 줄은 그 문서에 닿는 것) — 있으면 그 줄은 아직 못 고른다
    const placeAt = (u, kind) => { // 넣는 자리 — 이 묶음 안의 마지막 「그 줄이 쓰는 앞 줄」 바로 뒤에서 시작해, 잇달아 선 「같은 앞 줄을 쓰고 · 서버의 줄 차례(units 의 자리)가 새 줄보다 앞인」 줄을 건너뛴 자리 · 그 앞 줄이 이 묶음에 없으면 묶음 끝
      // 꼭 있어야 하는 앞 줄(must)은 늘 따르고, 아닌 것은 문서마다의 줄(같은 문서)일 때만 따른다 — 워크플로우 전체 · 원본 → 목적의 줄(프로젝트 구성 추출 …)이 한 문서의 줄을 다른 문서의 줄들 위로 끌어올리지 않게(문서끼리의 차례는 자유 — 따로 넣은 줄은 묶음 끝에)
      const r = roleOfKind(u, kind), order = (k) => units.findIndex((x) => x.key === k), mine = order(u.key);
      let last = -1, key = "";
      for (const x of usesOf(u)) {
        const pu = unitOf(x.unit, c);
        if (!x.must && !(pu && pu.place === "doc" && r)) continue;
        g.steps.forEach((p, i) => { if (i >= last && usesHit(c, p, x, r)) { last = i; key = x.unit; } }); // 두 문서를 하는 저장 줄(on 둘)이 그 앞 줄이면 그 저장 줄 뒤
      }
      if (last < 0) return g.steps.length;
      let at = last + 1;
      for (; at < g.steps.length; at++) { const v = unitOf(g.steps[at].unit, c); if (!v || order(v.key) >= mine || !usesOf(v).some((x) => x.unit === key)) break; }
      return at;
    };
    const pick = (kind) => { // kind = target | source — 그 문서 칸의 고르기(문서 줄 + 사람이 하는 일 + 쌍 줄)
      const sel = h("select", "wf-lines-add"), groups = {}, label = `${ROLE[kind]} 줄`;
      sel.dataset.add = kind;
      sel.dataset.lf = `add:${gi}:${kind}`;
      sel.setAttribute("aria-label", `${gi + 1}단계에 ${label} 넣기`);
      sel.disabled = lock;
      sel.append(new Option(`＋ ${label} 넣기…`, ""));
      for (const u of units) {
        const pair = isPair(u);
        if (!one && !anyDoc(u) && !u.roles.includes(kind)) continue; // 문서 줄은 그 문서에 놓을 수 있는 것만 · 쌍 줄 · 워크플로우 전체 줄은 두 칸의 고르기 모두에(워크플로우 전체 줄은 고른 칸에 한 칸 카드로 선다) · 문서 하나의 틀은 그 틀의 줄 모두
        const home = u.kind === "hand" ? "사람이 하는 일" : homes[u.home] || u.home, og = groups[home] || (groups[home] = h("optgroup"));
        og.label = home;
        const again = u.kind !== "hand" && has(u.key, one || anyDoc(u) ? "" : kind); // 이미 놓은 줄(쌍 줄 · 워크플로우 전체 줄 · 문서 하나의 틀의 줄은 흐름에 · 문서 줄은 그 문서에) — 막지 않는다: 한 번 더 놓을 수 있다(2026-11-20 사용자 「도구는 1번 이상 선택할 수 있어야지」 — 전의 「이미 놓음」 꺼짐을 없앰)
        const lack = lacks(u, kind).map((x) => (unitOf(x.unit, c) || {}).name || x.unit); // 꼭 있어야 하는 앞 줄이 아직 없는 줄 — 먼저 넣을 줄의 이름(「아직 서버가 못 돌림」 까닭이 먼저)
        const why = !u.server ? (u.kind === "hand" ? " — 아직(실행기가 멈추는 길을 만드는 중)" : " — 아직 서버가 못 돌림")
          : lack.length ? ` — 먼저 ${lack.map((n) => `「${n}」`).join(" · ")} ${josa(lack[lack.length - 1], "을", "를")} 넣으세요` : "";
        const o = new Option(u.name + (pair ? " (쌍)" : "") + (why || (again ? " — 한 번 더" : "")), u.key);
        o.disabled = !!why;
        if (again) o.dataset.again = "1";
        if (pair) o.dataset.pair = "1";
        og.append(o);
      }
      sel.append(...Object.values(groups));
      sel.addEventListener("change", () => {
        const u = unitOf(sel.value, c);
        if (!u) return;
        const on = one || anyDoc(u) ? [] : [kind]; // 쌍 줄은 어느 칸에서 골라도 한 줄({unit, on: []}) — 두 칸에 쌍으로 보인다 · 워크플로우 전체 줄은 고른 칸에(처음 서는 칸이 아니면 col) · 문서 하나의 틀의 줄은 늘 on 없이
        const col = !one && u.place === "flow" && kind !== homeCol(u) ? { col: kind } : {};
        let at = placeAt(u, kind);
        while (g.steps[at] && g.steps[at].beside) at++; // 같은 차례에 선 두 줄(한 행) 사이에는 넣지 않는다 — 그 행 뒤에
        g.steps.splice(at, 0, u.kind === "hand" ? { unit: "hand", on, name: "사람이 하는 일", note: "" } : { unit: u.key, on, ...col }); // 제 행으로(옆 칸은 빈칸) — 그 줄이 쓰는 앞 줄이 이 묶음에 있으면 그 뒤 · 없으면 묶음 끝. 넣은 뒤 끌어서(▲ ▼ 로) 옮긴다
        linesChanged(c);
      });
      return sel;
    };
    const same = (r) => { // 「…와 같이」(한 번짜리) — 다른 문서 o 가 이 묶음에서 하는 줄 가운데 이 문서 r 에 없는 것을, **그 줄의 옆 칸(같은 행 — 같은 차례)** 에 이 문서의 줄로 넣는다(사람이 하는 일은 줄마다 다른 일이라 안 넣는다 · 옆 칸이 찬 행은 건너뛴다).
      // 전에는 그 줄 바로 아래에 따로 넣었다 — 같은 행이 「같이」 다(2026-11-20 사용자 「이걸 같이 실행할 수 있는 기능이 없음」). 넣은 뒤에는 보통 카드다(따로 옮기고 뺀다)
      const o = ROLES.find((x) => x !== r);
      const todo = (rows) => { const seen = new Set(); return rows.filter((row) => { const x = !row.line && !row[r] && row[o], u = x && unitOf(x.unit, c);
        if (!u || u.kind === "hand" || !u.roles.includes(r) || has(x.unit, r) || seen.has(x.unit)) return false; seen.add(x.unit); return true; }); };
      const list = todo(rowsOf(c, g)), what = `${ROLE[o]}가 이 묶음에서 하는 줄 가운데 ${ROLE[r]}에 없는 것을, 그 줄의 옆 칸(같은 차례)에 ${ROLE[r]}의 줄로 넣습니다`;
      const b = lineBtn(`${ROLE[o]}와 같이`, list.length ? `${what} — ${list.map((row) => lineName(row[o], c)).join(" · ")}` : `${what} — 지금은 넣을 줄이 없습니다`,
        () => { const rows = rowsOf(c, g); for (const row of todo(rows)) row[r] = { unit: row[o].unit }; g.steps = stepsOf(rows); linesChanged(c); }, lock || !list.length);
      b.classList.add("wf-lines-same");
      b.dataset.same = r;
      b.dataset.lf = `same:${gi}:${r}`;
      return b;
    };
    const docSource = units.some((u) => u.place === "doc" && u.roles.includes("source")); // 그 틀에 원본 문서에 놓을 문서 줄이 있나
    const hasSource = docSource || units.some((u) => anyDoc(u)); // 원본 칸의 고르기 — 원본 문서 줄이 없어도 쌍 줄 · 워크플로우 전체 줄이 있으면 그린다(두 칸의 고르기 모두에)
    const canSame = !one && docSource && units.some((u) => u.place === "doc" && u.kind !== "hand" && u.roles.length === 2); // 두 문서에 다 놓을 수 있는 줄이 있을 때만 「…와 같이」(취합형은 문서마다의 줄이 모두 한 문서뿐 · 문서 하나의 틀은 문서가 하나)
    const cellOf = (r) => { const d = h("div", "wf-lines-addcell"); d.dataset.role = r; d.append(pick(r), ...(canSame ? [same(r)] : [])); return d; };
    const row = h("div", "wf-lines-addrow");
    row.append(h("span", "wf-lines-addpad"), cellOf("target"), ...(one ? [] : [hasSource ? cellOf("source") : h("span", "wf-lines-addpad")])); // 줄과 같은 격자(번호 | 목적 | 원본 — 문서 하나의 틀은 번호 | 목적) — 전의 「＋ 공통 줄 넣기…」 는 없앴다(쌍 줄은 문서 칸의 고르기에서)
    return row;
  }
  function checkEl(c) { // 서버 검사의 결과 — 표준 차례인가 · 거절(빨강 — 저장 단추가 꺼짐) · 경고(주황 — 저장은 됨)
    const box = h("div", "wf-lines-check");
    box.setAttribute("role", "status");
    if (c.checking) { box.append(h("p", "wf-muted", "검사하는 중…")); return box; }
    const k = c.check;
    if (!k) return box;
    if (!k.errors.length && !c.single) box.append(h("p", "wf-lines-std", k.std ? "표준 차례 — 저장하면 옛 꼴로 둡니다(옛 화면 · 옛 서버도 그대로 읽습니다)" : "줄 목록으로 조립한 워크플로우 — 서버 실행기가 정한 차례 그대로 돌립니다"));
    if (k.errors.length) { const ul = h("ul", "wf-lines-err"); ul.setAttribute("role", "alert"); for (const e of k.errors) ul.append(h("li", "", e)); box.append(ul); }
    if (k.warns.length) { const ul = h("ul", "wf-lines-warn"); for (const w of k.warns) ul.append(h("li", "", w)); box.append(ul); }
    return box;
  }
  function linesDraw(c) { // 줄 목록을 다시 그린다(초점은 같은 자리의 컨트롤로) · 저장 단추의 켜짐도
    const box = c.linesBox;
    if (!box) return;
    if (drag && drag.c === c) { c.redraw = true; return; } // 끄는 동안에는 줄을 갈아 끼우지 않는다(끄던 카드가 없어진다) — 놓은 뒤에(dragEnd)
    c.redraw = false;
    const a = document.activeElement, focus = c.focusLf || (a && box.contains(a) ? a.dataset.lf || "" : ""), lock = !!c.locked, flow = c.flow || []; // focusLf = 방금 ▲ ▼ 로 옮긴 카드의 그 단추(초점이 카드를 따라간다)
    c.focusLf = "";
    box.replaceChildren();
    box.classList.toggle("wf-one", oneDoc(c)); // 문서 하나의 틀 — 한 칸 격자(workflow.css)
    if (!c.flow) { box.append(h("p", "wf-muted", "줄 목록을 읽는 중…")); return; }
    const ol = h("ol", "wf-lines-groups");
    let no = 0;
    flow.forEach((g, gi) => {
      const li = h("li", "wf-lines-group"), head = h("div", "wf-lines-ghead"), nm = h("input"), steps = h("ol", "wf-lines-steps");
      li.dataset.group = g.id || `new${gi}`;
      nm.value = g.name; nm.maxLength = 20; nm.disabled = lock; nm.dataset.lf = `gname:${gi}`; nm.setAttribute("aria-label", `${gi + 1}단계 묶음의 이름`);
      nm.addEventListener("change", () => { g.name = nm.value.trim() || `묶음 ${gi + 1}`; linesChanged(c); });
      const swap = (d) => { const [x] = flow.splice(gi, 1); flow.splice(gi + d, 0, x); linesChanged(c); };
      const gIco = (b, d) => {
        const t = b.textContent, ic = h("span", "wf-icon");
        ic.setAttribute("aria-hidden", "true");
        ic.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
        b.classList.add("wf-act-ico");
        b.replaceChildren(ic, h("span", "sr-only", t));
        return b;
      };
      const delG = lineBtn("묶음 빼기", `${gi + 1}단계 묶음 빼기(그 줄도 함께)`, () => { flow.splice(gi, 1); linesChanged(c); }, lock || flow.length === 1);
      delG.classList.add("wf-gact-del");
      head.append(h("span", "wf-lines-no", `${gi + 1}단계`), nm, gIco(lineBtn("▲", `${gi + 1}단계 묶음 위로`, () => swap(-1), lock || gi === 0), '<path d="m6 15 6-6 6 6"/>'), gIco(lineBtn("▼", `${gi + 1}단계 묶음 아래로`, () => swap(1), lock || gi === flow.length - 1), '<path d="m6 9 6 6 6-6"/>'), delG);
      for (const b of head.querySelectorAll("button")) b.dataset.lf = `g${b.textContent}:${gi}`;
      { // 열 머리 — 왼쪽 목적 문서 · 오른쪽 원본 문서(줄의 칸과 같은 격자). 줄이 없어도 그린다 — 아래 넣기 줄의 칸 이름이기도 하다
        const cols = h("li", "wf-line-cols");
        cols.setAttribute("aria-hidden", "true");
        cols.append(h("span", ""), ...colsOf(c).map((r) => { const x = h("span", "wf-line-colname", ROLE[r]); x.dataset.role = r; return x; }));
        steps.append(cols);
      }
      const rows = rowsOf(c, g); // 보이는 행 — 저장 줄을 편 것(행 × 두 칸: 쌍 줄 = 두 칸을 다 쓰는 한 행 · 문서 줄 = 제 칸의 카드 — 두 문서를 하는 저장 줄과 같은 차례로 놓은 두 줄은 한 행의 두 칸 · 번호 = 행의 차례)
      rows.forEach((row, ri) => steps.append(rowEl(c, gi, ri, row, rows.length, ++no, lock)));
      if (!lock) dropWire(c, gi, steps);
      if (!g.steps.length) steps.append(h("li", "wf-muted wf-line-empty", c.single ? "줄이 없습니다 — 아래에서 넣으세요" : "줄이 없습니다 — 아래에서 넣거나 묶음을 빼세요"));
      li.append(...(c.single ? [] : [head]), steps, addRowEl(c, gi, lock)); // 단계 폼(single) = 묶음 하나 — 묶음 머리(이름 · 차례 · 빼기)가 없다
      ol.append(li);
    });
    const addG = lineBtn("＋ 묶음", "묶음을 끝에 더합니다", () => { flow.push({ name: `묶음 ${flow.length + 1}`, steps: [] }); linesChanged(c); }, lock || flow.length >= 8);
    addG.dataset.lf = "addGroup";
    box.append(ol, ...(c.single ? [] : shapeBox(c) ? [addG] : [addG, addStageEl(c, lock)]), checkEl(c)); // 「＋ 단계 넣기…」 의 단계(기본 넷 · 내가 만든 단계)는 이관형의 줄이라 취합형에는 두지 않는다 // 「위에서 아래로 차례대로 · 맨 앞 묶음의 준비」 설명은 절 머리의 노트 아이콘에(사용자 「아래 설명들은 빼고」)
    if (focus) { const to = [...box.querySelectorAll("[data-lf]")].find((x) => x.dataset.lf === focus && !x.disabled); if (to) to.focus({ preventScroll: true }); }
    if (c.saveBtn) c.saveBtn.disabled = c.busy || (!lock && c.mode === "lines" && (c.checking || !c.check || c.check.errors.length > 0));
    helpSync(c); // 도구 설명 열(② §18-15) — 다시 그린 카드에 고른 표시 · 놓인 곳의 수
  }
  // ---- 단계 넣기 · 단계 만들기(spec_워크플로우 ② §18-14 — 2026-11-20 사용자 「이 단계 만들기도 있어야 하는거 아니냐?」)
  // 단계 = 줄의 묶음: 붙박이 넷(서버 stages[].lines — 그 단계의 표준 줄) + 내가 만든 단계(userStages — 있는 줄을 골라 이름 붙여 저장: POST · PUT · DELETE /api/stages).
  // 조립 폼의 「＋ 단계 넣기…」 = 그 줄들을 묶음 하나로 끝에 넣는다(이미 놓은 줄도 그대로 — 2026-11-20 같은 줄을 여러 번 놓을 수 있다 · 넣은 뒤에는 그 워크플로우의 줄이다: 단계를 고쳐도 만든 워크플로우는 안 바뀐다).
  // 「단계 만들기」 절(#wfStage — 전체 보기와 함께) = 내가 만든 단계 목록(고치기 · 지우기) + 폼(이름 · 한 줄 설명 · 줄 — 조립의 줄 편집기를 묶음 하나로: c.single). 검사는 서버(POST /api/stages/check). 새 종류의 줄은 화면에서 못 만든다(줄은 코드).
  let staging = null; // 펴 둔 단계 폼 {key("" = 새로), name, desc, flow: [{name, steps}](묶음 하나), single: true, mode: "lines", check, checking, busy, err, locked: ""}
  function stageRest(c, steps) { // 그 단계의 줄들(사본 — 이 틀이 아는 줄만). 이미 놓은 줄도 그대로 넣는다 — 같은 줄을 여러 번 놓을 수 있다(2026-11-20: 전에는 이미 놓은 줄 · 문서를 뺐다 — 서버 검사가 경고로 알린다)
    const out = [];
    for (const s of steps || []) {
      const u = unitOf(s.unit, c), more = s.beside ? { beside: true } : {};
      if (!u) continue;
      out.push(u.kind === "hand" ? { unit: "hand", on: [...(s.on || [])], name: s.name || "사람이 하는 일", note: s.note || "", ...more } : { unit: s.unit, on: [...(s.on || [])], ...more });
    }
    return out;
  }
  function addStageEl(c, lock) { // 「＋ 단계 넣기…」 — 붙박이 단계 · 내가 만든 단계의 줄들을 묶음 하나로 끝에
    const sel = h("select", "wf-lines-add wf-lines-addstage"), groups = [["기본 단계", (T.stages || []).filter((st) => Array.isArray(st.lines)).map((st) => ({ id: st.id, name: st.name, steps: st.lines }))],
      ["내가 만든 단계", (T.userStages || []).map((s) => ({ id: s.key, name: s.name, steps: s.steps }))]];
    sel.setAttribute("aria-label", "단계를 묶음으로 넣기");
    sel.dataset.lf = "addStage";
    sel.disabled = lock || (c.flow || []).length >= 8;
    sel.append(new Option("＋ 단계 넣기…", ""));
    const by = {};
    for (const [label, list] of groups) {
      if (!list.length) continue;
      const og = h("optgroup");
      og.label = label;
      for (const st of list) {
        const rest = stageRest(c, st.steps), o = new Option(st.name, st.id);
        o.disabled = !rest.length;
        by[st.id] = { name: st.name, rest };
        og.append(o);
      }
      sel.append(og);
    }
    sel.addEventListener("change", () => {
      const st = by[sel.value];
      if (!st || !st.rest.length) return;
      c.flow.push({ name: String(st.name).slice(0, 20), steps: st.rest });
      linesChanged(c);
    });
    return sel;
  }
  async function stageCheck(c) { // 서버의 단계 검사 → c.check {errors, warns: [], std: false}
    c.checking = true;
    let got = null;
    try { const r = await fetch("/api/stages/check", { method: "POST", headers: JSON_H, body: JSON.stringify({ steps: c.flow[0].steps }) }); got = r.ok ? await r.json() : null; } catch { got = null; }
    if (staging !== c) return;
    c.checking = false;
    c.check = got ? { errors: got.errors || [], warns: [], std: false } : { errors: ["단계 검사를 읽지 못했습니다 — 서버를 다시 켠 뒤에 쓸 수 있습니다"], warns: [], std: false };
  }
  function stageOpen(key) { // "" = 새 단계 · 키 = 그 단계 고치기 — 「단계 만들기」 절로 가서 폼을 편다
    const s = key ? ((T && T.userStages) || []).find((x) => x.key === key) : null;
    staging = T && Array.isArray(T.userStages) && Array.isArray(T.units)
      ? { key: s ? s.key : "", name: s ? s.name : "", desc: s ? s.desc || "" : "", flow: [{ name: "단계", steps: s ? flowCopy([{ steps: s.steps }])[0].steps : [] }], single: true, mode: "lines", check: null, checking: false, busy: false, err: "", locked: "" } : null;
    if (view === "diagram") navigate("#overview"); else go("#overview");
    stageDraw();
    if (staging) stageCheck(staging).then(() => { if (staging) linesDraw(staging); });
    const box = $("wfStage"), first = box && box.querySelector("input[name=stage-name]");
    if (box) box.scrollIntoView({ block: "start" });
    if (first) first.focus({ preventScroll: true });
  }
  async function stageSave() {
    const c = staging;
    if (!c || c.busy) return;
    c.busy = true; c.err = "";
    stageDraw();
    const r = await ffSend(c.key ? `/api/stages/${encodeURIComponent(c.key)}` : "/api/stages", { method: c.key ? "PUT" : "POST", headers: JSON_H, body: JSON.stringify({ name: c.name, desc: c.desc, steps: c.flow[0].steps }) });
    if (!r.ok) { c.busy = false; c.err = r.msg; if (staging === c) stageDraw(); return; } // 서버의 글 그대로(400 값이 틀림 · 409 저장 파일을 못 읽음)
    staging = null;
    const noteErr = window.WfAgents ? await WfAgents.flush(c, "") : ""; // 「에이전트」 열에 적어 둔 범용 덧붙이는 글도 함께 저장(② §18-16 — 단계에는 전용 글이 없다)
    if (noteErr) alert(`단계는 저장했지만 ${noteErr}`);
    await load(); // 저장소를 다시 읽어 목차 · 절 · 조립 폼의 「＋ 단계 넣기…」 를 새로
    const box = $("wfStage");
    if (box) box.scrollIntoView({ block: "start" });
  }
  async function stageDelete(s) {
    if (!confirm(`내가 만든 단계 「${s.name}」 ${josa(s.name, "을", "를")} 지울까요?\n\n이미 이 단계를 넣어 만든 워크플로우는 그대로입니다(넣은 줄은 그 워크플로우의 것). 되돌릴 수 없습니다.`)) return;
    const r = await ffSend(`/api/stages/${encodeURIComponent(s.key)}`, { method: "DELETE" });
    if (!r.ok) { alert(`지우지 못했습니다 — ${r.msg}`); return; }
    if (staging && staging.key === s.key) staging = null;
    await load();
  }
  function stageSec() { const sec = h("section", "wf-sec wf-compose wf-stage-make"); sec.id = "wfStage"; return sec; }
  function stageDraw() {
    const sec = $("wfStage");
    if (!sec) return;
    const h2 = h("h2"), can = !!(T && Array.isArray(T.userStages) && Array.isArray(T.units));
    h2.append(h("span", "wf-kind", "단계 만들기"), document.createTextNode("줄을 골라 내 단계 만들기"));
    sec.replaceChildren(h2);
    sec.classList.remove("wf-wide"); // 폼 | 도구 설명 열이 설 때만 넓은 절(helpWrap 이 붙인다 — ② §18-15)
    navToolsDraw(); // 목차의 「워크플로우 도구」 — 조립 폼이 없으면 이 폼을 따른다
    if (!can) { staging = null; const p = h("p", "wf-lead wf-compose-off", NO_COMPOSE); p.setAttribute("role", "status"); sec.append(p); return; }
    headHelp(sec, h2, "단계 만들기 — 설명", "있는 줄(헤딩 · 표 분석 · 프로젝트 구성 반영 · 자리 연결 …)을 골라 차례대로 놓고 이름을 붙이면 내 단계가 됩니다. 워크플로우 조립의 「＋ 단계 넣기…」 가 그 줄들을 묶음 하나로 넣습니다 — "
      + "넣은 뒤에는 그 워크플로우의 줄이라, 단계를 고치거나 지워도 이미 만든 워크플로우는 바뀌지 않습니다. 새 종류의 줄(새로운 일)은 화면에서 만들 수 없습니다 — 기본 단계 넷(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)의 줄 가운데서 고릅니다.");
    if (T.stagesBroken) { const p = h("p", "wf-compose-broken", "내가 만든 단계의 저장 파일을 읽지 못했습니다 — 목록이 보이지 않고, 그 파일을 덮지 않으려고 서버가 새로 저장하거나 고치지 않습니다."); p.setAttribute("role", "alert"); sec.append(p); }
    const list = h("ul", "wf-made-list");
    for (const s of T.userStages) {
      const li = h("li"), chips = h("span", "wf-links"), edit = h("button", "btn sm", "고치기"), del = h("button", "btn sm", "지우기");
      li.dataset.stage = s.key;
      for (const n of s.lines || []) chips.append(h("span", "wf-chip", n));
      edit.type = del.type = "button";
      edit.addEventListener("click", () => stageOpen(s.key));
      del.addEventListener("click", () => stageDelete(s));
      li.append(h("b", "wf-over-name", s.name), ...(s.desc ? [h("span", "wf-muted", s.desc)] : []), chips, edit, del);
      list.append(li);
    }
    if (T.userStages.length) sec.append(list);
    if (!staging) {
      const make = h("button", "btn primary", "새 단계 만들기");
      make.type = "button";
      make.dataset.wfStage = "open";
      make.addEventListener("click", () => stageOpen(""));
      sec.append(make);
      return;
    }
    const c = staging, form = h("form", "wf-form"), field = (label, control) => { const f = h("label", "wf-field"); f.append(h("span", "wf-field-name", label), control); return f; };
    const name = h("input"), desc = h("input"), lines = h("div", "wf-lines"), blockF = h("div", "wf-field wf-field-block"), acts = h("div", "wf-form-acts");
    form.addEventListener("submit", (e) => { e.preventDefault(); stageSave(); });
    name.name = "stage-name"; name.required = true; name.maxLength = 20; name.value = c.name; name.placeholder = "예: 원본만 검토";
    name.addEventListener("input", () => { c.name = name.value; });
    desc.name = "stage-desc"; desc.maxLength = 200; desc.value = c.desc; desc.placeholder = "이 단계가 하는 일 한 줄(비워도 됩니다)";
    desc.addEventListener("input", () => { c.desc = desc.value; });
    const save = h("button", "btn primary", c.busy ? "저장 중…" : c.key ? "고친 것 저장" : "단계 만들기"), cancel = h("button", "btn", "취소");
    save.type = "submit";
    c.saveBtn = save;
    c.linesBox = lines;
    cancel.type = "button";
    cancel.addEventListener("click", () => { staging = null; stageDraw(); });
    acts.append(save, cancel);
    if (c.err) { const e = h("p", "wf-err", c.err); e.setAttribute("role", "alert"); acts.append(e); }
    blockF.append(h("span", "wf-field-name", "줄"), lines);
    form.append(h("h3", "", c.key ? `「${c.name}」 고치기` : "새 단계"), field("이름", name), field("한 줄 설명", desc), blockF, acts);
    sec.append(helpWrap(form, c, sec)); // 폼 | 도구 설명 열(② §18-15)
    linesDraw(c);
  }

  // 「문서 입출력」(spec_워크플로우 ② §18-8 「문서 입출력」 · §18-9 — 2026-11-20 사용자 "1->N, N-1 문서 입출력 … 입력을 설정할 수 있어야 … 각 1이 되는것들은 특정 문서로 지정할 수 있도록, default 로"):
  // 틀 = 서버의 shapes 그대로(「1」 문서 하나 · 「1 → 1」 이관 · 「N → 1」 취합 — 아직 못 여는 틀은 까닭과 함께 꺼 둔다: 감추지 않는다) → 고른 틀의 문서 칸(역할 · 수 · 문서 종류) ·
  // 목적 문서 칸(수가 N 이어도) · 수가 1인 원본 칸마다 기본 문서(저장한 양식 — 없음 · 기본값 · 고정: ioSlots). 새 워크플로우는 고른 것을 만든 뒤에 걸고(composeSave), 고치기는 그 워크플로우의 설정을 바로 바꾼다(워크플로우 절의 「문서 칸」 과 같은 끝점 — 정의와 따로라 지문이 안 바뀐다).
  // 만든 뒤에는 틀 · 문서 종류를 못 고친다(그 워크플로우로 하던 작업의 문서 역할이 달라진다). shapes 를 안 주는 옛 서버면 전의 문서 쌍 고르기(pairs).
  const pairOf = (sh) => { const k = (role) => (((sh.slots || []).find((s) => s.role === role) || {}).kinds || [])[0]; return `${(k("source") || {}).id || ""}>${(k("target") || {}).id || ""}`; };
  let ioRefresh = null; // 펴 둔 조립 폼의 문서 칸을 새로 그린다 — 저장한 양식 · 설정이 바뀐 뒤(ffRedraw: 그 칸에서 올린 양식 · 「저장한 양식」 절에서 더하거나 지운 양식 · 고치기 폼에서 바꾼 설정이 그 칸에 바로 보이게 — 전에는 옛 목록 · 꺼진 고르기 그대로였다)
  function ioEl(c, onChange) {
    const box = h("div", "wf-iobox"), shapes = Array.isArray(T.shapes) ? T.shapes.filter((x) => x && x.id) : [];
    if (!shapes.length) { // 옛 서버 — 문서 쌍 고르기
      const pair = h("select");
      for (const p of T.pairs) pair.append(new Option(p.name, `${p.source}>${p.target}`));
      pair.name = "pair"; pair.value = c.pair; pair.disabled = !!c.key;
      pair.setAttribute("aria-label", "문서 쌍(원본 → 목적)");
      pair.addEventListener("change", () => { c.pair = pair.value; onChange(); });
      box.append(pair);
      return box;
    }
    const opts = h("div", "wf-io-shapes");
    opts.setAttribute("role", "radiogroup");
    opts.setAttribute("aria-label", "문서 입출력");
    let slots = null;
    for (const sh of shapes) {
      const lab = h("label", "wf-io-opt"), r = h("input"), [what] = String(sh.name || sh.id).split(" — ");
      r.type = "radio"; r.name = "shape"; r.value = sh.id; r.checked = c.shape === sh.id; r.disabled = !!c.key || !!sh.soon;
      lab.dataset.shape = sh.id;
      if (sh.soon) lab.dataset.soon = "1";
      if (r.checked) lab.dataset.on = "1"; // 고른 틀 — 테두리(:has() 를 쓰지 않고 표지로)
      r.addEventListener("change", () => { if (!r.checked) return; for (const x of opts.children) delete x.dataset.on; lab.dataset.on = "1"; c.shape = sh.id; c.pair = pairOf(sh); c.slots = {}; shapeFlow(c); const next = ioSlots(c, sh, onChange); slots.replaceWith(next); slots = next; kindSync(); onChange(); });
      const soon = sh.soon ? h("span", "wf-io-soon", "준비 중") : null; // 설명 글은 두지 않는다(2026-11-20 사용자 「설명 빼줘」) — 아직 못 여는 까닭은 꼬리표의 풍선 글로만
      if (soon) soon.title = sh.soon;
      lab.append(r, h("b", "wf-io-form", sh.io || sh.id), h("span", "wf-io-name", what), ...(soon ? [soon] : []));
      opts.append(lab);
    }
    const shapeNow = () => shapes.find((x) => x.id === c.shape) || shapes.find((x) => !x.soon) || shapes[0];
    slots = ioSlots(c, shapeNow(), onChange);
    ioRefresh = () => { if (!slots.isConnected) return; const next = ioSlots(c, shapeNow(), onChange); swapKeep(slots, next); slots = next; };
    // 목적 문서의 종류 — 그 틀의 목적 문서 칸이 받는 문서 종류가 여럿일 때만 고른다(문서 하나의 틀: 사업계획서 · 연차보고서 — 이관 · 취합은 종류가 하나라 고르기가 없다). 고르면 줄 목록이 그 종류의 처음 것으로 바뀐다 · 만든 뒤에는 못 고친다
    const kindBox = h("div", "wf-io-kind");
    function kindSync() {
      const sh = shapeNow(), kinds = ((((sh && sh.slots) || []).find((s) => s.role === "target") || {}).kinds || []).filter((k) => k && k.id);
      kindBox.replaceChildren();
      kindBox.hidden = kinds.length < 2;
      if (kindBox.hidden) return;
      const sel = h("select"), [src] = String(c.pair || "").split(">");
      for (const k of kinds) sel.append(new Option(k.name || k.id, k.id));
      sel.name = "target-kind"; sel.value = String(c.pair || "").split(">")[1] || kinds[0].id; sel.disabled = !!c.key;
      sel.setAttribute("aria-label", "목적 문서의 종류");
      sel.addEventListener("change", () => { c.pair = `${src}>${sel.value}`; c.slots = {}; shapeFlow(c); const next = ioSlots(c, shapeNow(), onChange); slots.replaceWith(next); slots = next; onChange(); });
      kindBox.append(h("b", "", "목적 문서의 종류"), sel);
    }
    kindSync();
    box.append(opts, kindBox, slots); // 아래 설명 글은 두지 않는다(사용자 「아래 설명들은 빼고」)
    return box;
  }
  function ioSlots(c, sh, onChange) { // 고른 틀의 문서 칸 — 칸마다 역할 · 수(1 | N) · 기본 문서(저장한 양식). 설명 글 · 문서 종류 이름은 두지 않는다(사용자 「아래 설명들은 빼고 … 확정적인 이름은 빼줘」)
    // 양식을 거는 칸 = **목적 문서 칸은 늘**(수가 N 이어도 — 이관 「1 → N」 의 목적: 새 목적 문서마다 그 양식으로 시작) + 수가 1인 원본 칸. 안 거는 것은 원본이 여럿인 칸(취합의 기관 문서)뿐 — 서버 form_files_api.rule 과 같은 칸(② §18-9).
    // 2026-11-20 사용자(「원본 문서 1 [양식 올리기…] / 목적 문서 N」 을 보이며) "여기 목적문서 양식 넣는게 없네? 왜 없냐?" — 전에는 「수가 1인 칸만」 이라 이관을 「1 → N」 으로 바꾼 뒤 목적 칸의 고르기 · 올리기가 빠졌다(에이전트 판단이었다).
    const ul = h("ul", "wf-slot-list wf-io-slots"), [src, tgt] = c.pair.split(">");
    ul.dataset.shape = sh.id;
    for (const s of sh.slots || []) {
      const li = h("li", "wf-slot"), head = h("span", "wf-slot-role"), count = h("span", "wf-io-count", s.many ? "N" : "1"), kinds = s.kinds || [], kind = (s.role === "source" ? src : tgt) || (kinds[0] || {}).id || ""; // kind = 양식 고르기를 추리는 종류(보이지 않음 — 서버의 짝)
      li.dataset.role = s.role;
      count.dataset.count = s.many ? "N" : "1";
      head.append(h("b", "", s.title || ROLE[s.role] || s.role), count);
      li.append(head);
      if ((s.role === "target" || !s.many) && !sh.soon) li.append(c.key ? ioLive(c, s) : slotDraft(c, s, kind));
      else li.dataset.noForm = "1";
      ul.append(li);
    }
    return ul;
  }
  function ioLive(c, s) { // 고치기 — 그 워크플로우의 그 칸 설정을 바로(워크플로우 절의 「문서 칸」 과 같은 고르기)
    const t = D ? D.tasks.find((x) => x.job === c.key) : null, j = ffJob(c.key), jr = j ? ((j.roles || []).find((x) => x.role === s.role) || (s.role === "target" && !j.roles ? j : null)) : null;
    if (!FF) return h("span", "wf-muted", ffErr ? `저장한 양식을 읽지 못했습니다: ${ffErr}` : "기본 문서는 서버를 다시 켠 뒤에 걸 수 있습니다");
    if (!t || !jr) return h("span", "wf-muted", "이 칸에는 기본 문서를 걸지 않습니다");
    return slotPick(t, jr, (FF.slots && FF.slots[c.key] && FF.slots[c.key][s.role]) || null, s.role, s.title, true);
  }
  function slotDraft(c, s, kind) { // 새 워크플로우의 그 칸 — 기본 문서를 골라 둔다(만든 뒤에 건다: composeSave · 걸 수 있는지는 그때 서버가 다시 본다)
    const wrap = h("span", "wf-slot-pick");
    if (!FF) { wrap.append(h("span", "wf-muted", ffErr ? `저장한 양식을 읽지 못했습니다: ${ffErr}` : "기본 문서는 서버를 다시 켠 뒤에 걸 수 있습니다")); return wrap; }
    const combo = h("span", "wf-slot-combo"), mode = h("select", "wf-slot-mode"), form = h("select", "wf-slot-form"), j = { formats: ["hwpx"], kind }, fits = (FF.files || []).filter((f) => ffFits(f, j)), cur = c.slots[s.role] || null;
    const web = slotWeb(`draft-web-${s.role}`, s.title, !cur); // 「웹에서 직접 올림」 — 켜짐 = 양식 없음(c.slots[role] = null) · 끔 = 양식을 건다({mode, file} — 고를 양식이 없으면 file 이 비어 composeSave 가 거르고, 다시 그려도 꺼진 채 남는다)
    mode.name = `draft-mode-${s.role}`;
    mode.setAttribute("aria-label", `${s.title} 칸의 기본 문서 — 양식`);
    for (const [v, label] of Object.entries(FF_PICK)) mode.append(new Option(`양식: ${label}`, v));
    mode.value = cur && FF_PICK[cur.mode] ? cur.mode : "default";
    form.name = `draft-form-${s.role}`;
    form.setAttribute("aria-label", `${s.title} 칸에 넣을 저장한 양식`);
    for (const f of fits) form.append(new Option(`${f.name}${ffDate(f.at) ? ` (${ffDate(f.at)})` : ""}`, f.id));
    if (!fits.length) form.append(new Option("걸 수 있는 양식이 없음", ""));
    form.value = cur && fits.some((f) => f.id === cur.file) ? cur.file : (fits[0] || {}).id || "";
    const up = slotUp(j, s.title, `draft-up-${s.role}`, (f) => { c.slots[s.role] = { mode: (c.slots[s.role] || {}).mode || "default", file: f.id }; ffRedraw(); }); // 올린 양식을 이 칸에 골라 둔다(기본값 — 만든 뒤에 건다) · ffRedraw 가 이 칸도 새로 그린다(ioRefresh)
    const box = web.querySelector("input");
    const sync = () => {
      const on = box.checked;
      form.disabled = mode.disabled = !fits.length;
      wrap.dataset.mode = on ? "" : mode.value;
      wrap.dataset.web = on ? "1" : "";
      c.slots[s.role] = on ? null : { mode: mode.value, file: form.value };
      combo.hidden = mode.hidden = form.hidden = on || !fits.length; // 고를 양식이 없으면 꺼진 고르기 둘을 세워 두지 않는다 — 그 자리에서 할 수 있는 일(「양식 올리기…」)만 보인다(2026-11-20 사용자 "이거 클릭도 안되고 왜 아무것도 안해?")
      up.hidden = on;
    };
    if (!fits.length) wrap.dataset.empty = "1";
    box.addEventListener("change", sync);
    mode.addEventListener("change", sync);
    form.addEventListener("change", sync);
    sync();
    combo.append(mode, form);
    wrap.append(web, combo, up); // 설명 글 없음
    return wrap;
  }
  function composeForm() {
    const c = composing, form = h("form", "wf-form"), field = (label, control, note) => { const f = h("label", "wf-field"); f.append(h("span", "wf-field-name", label), control); if (note) f.append(h("span", "wf-muted", note)); return f; };
    const block = (label, control) => { const f = h("div", "wf-field wf-field-block"); f.append(h("span", "wf-field-name", label), control); return f; };
    form.addEventListener("submit", (e) => { e.preventDefault(); composeSave(); });
    const name = h("input"), desc = h("input"), premise = h("textarea");
    name.name = "name"; name.required = true; name.maxLength = limit("name", 40); name.value = c.name; name.placeholder = "예: 연차보고서 구성만 맞추기";
    name.addEventListener("input", () => { c.name = name.value; });
    desc.name = "desc"; desc.maxLength = limit("desc", 200); desc.value = c.desc; desc.placeholder = "시작 화면의 카드에 보이는 한 줄 설명(비워도 됩니다)";
    desc.addEventListener("input", () => { c.desc = desc.value; });
    premise.name = "premise"; premise.rows = 4; premise.maxLength = limit("premise", 8000); premise.value = c.premise;
    premise.placeholder = `이 워크플로우의 전제 · 기준(LLM 호출이 읽는 글). 비우면 「${taskName(T.base)}」 의 전제를 씁니다.`;
    premise.addEventListener("input", () => { c.premise = premise.value; });
    // 문서 역할 × 단계 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 행 = 일반 단계 넷(차례 고정) · 열 = 원본 문서 · 목적 문서 · 칸 = 서버의 cells(pick 체크 · follow 따라오는 글 · no 까닭)
    const pick = h("fieldset", "wf-stage-pick"), table = h("table", "wf-assign"), thead = h("thead"), hr = h("tr"), tbody = h("tbody"), th0 = h("th", "", "단계"), heads = {}, follows = [];
    pick.append(h("legend", "", "문서마다 단위문서 TASK — 원본 문서 · 목적 문서에 쓸 단계를 고릅니다(차례는 위에서 아래로 고정)"));
    th0.scope = "col";
    hr.append(th0);
    for (const role of ROLES) { const th = h("th"); th.scope = "col"; th.dataset.role = role; heads[role] = th; hr.append(th); }
    thead.append(hr);
    T.stages.forEach((st, i) => {
      const tr = h("tr"), th = h("th"), nm = h("b", "", `${i + 1}. ${st.name}`);
      tr.dataset.stage = st.id;
      th.scope = "row";
      nm.title = st.does;
      th.append(nm, h("span", "wf-stage-steps", st.steps.map((x) => x.name + (x.optional ? "(선택)" : "")).join(" › ")));
      tr.append(th);
      for (const role of ROLES) {
        const cell = cellOf(st, role), td = h("td");
        td.dataset.role = role;
        td.dataset.mode = cell.mode;
        if (cell.mode === "pick") {
          const lab = h("label", "wf-assign-opt"), box = h("input");
          box.type = "checkbox"; box.name = `assign-${role}`; box.value = st.id; box.checked = c.assign[role].has(st.id);
          box.addEventListener("change", () => { if (box.checked) c.assign[role].add(st.id); else c.assign[role].delete(st.id); sync(); stdFill(c); }); // 표에서 고르면 줄 목록을 그 표준 차례로 다시 채운다
          if (!cell.text) box.setAttribute("aria-label", `${ROLE[role]} — ${st.name}`);
          lab.append(box, h("span", "wf-assign-text", cell.text || ""));
          td.append(lab);
        } else if (cell.mode === "follow") { // 다른 역할이 이 단계를 골랐을 때만 그 글 — 아니면 「—」
          const other = role === "source" ? "target" : "source", span = h("span", "wf-assign-follow");
          span.title = `${ROLE[other]}가 이 단계를 고르면 따라옵니다`;
          follows.push({ span, id: st.id, other, text: cell.text || "" });
          td.append(span);
        } else td.append(h("span", "wf-assign-no", cell.text || "—"));
        tr.append(td);
      }
      tbody.append(tr);
    });
    table.append(thead, tbody);
    // 표 아래 — 직접 고른 단계(따라오는 칸 · 워크플로우 전체 단계는 표에만) · 「문서 검토」 의 LLM 검증·보완을 하는 문서(고치기 · 복제: 서버가 준 값 그대로) · 경고(막지 않음)
    const sum = h("div", "wf-assign-sum"), units = h("ul", "wf-assign-units"), llmLine = h("p", "wf-assign-llm"), warn = h("p", "wf-assign-warn", `목적 문서에 「구성 맞추기」 없이 「내용 넣기」 — ${fillNoFit()}`); // 뒷부분 = 서버의 warn.fillNoFit
    sum.append(h("span", "wf-assign-sum-head", "직접 고른 단계"), units);
    units.setAttribute("aria-label", "직접 고른 단계");
    warn.setAttribute("role", "status");
    pick.append(table, sum, llmLine, warn);
    let lock = null;
    if (c.locked) { // 쓰는 중(서버의 editWhy — 지금 워크플로우로 둔 작업이 있음) — 단계(배정)는 못 바꾼다(서버도 409): 표를 끄고 「복제」 로 새 워크플로우를(이름 · 설명 · 전제는 여기서 고친다) · 잠금 글 = 그 까닭 글 그대로
      pick.disabled = true;
      lock = h("div", "wf-assign-lock");
      lock.setAttribute("role", "status");
      const dup = h("button", "btn sm", "복제");
      dup.type = "button";
      dup.dataset.wfCopy = c.key;
      dup.title = "같은 단계 · 설명 · 전제로 새 워크플로우 폼을 엽니다(이름 「… 사본」)";
      dup.addEventListener("click", () => { const t = T.tasks.find((x) => x.key === c.key); if (t) composeOpen("", t); });
      lock.append(h("span", "", c.locked), dup);
    }
    function sync() { // 문서 이름(문서 쌍) · 따라오는 칸 · 직접 고른 단계 · LLM 검증·보완 줄 · 경고(막지 않음)를 지금 고른 것으로
      const names = pairNames(c.pair), docName = (role) => `${ROLE[role]}${names[role] ? " — " + names[role] : ""}`;
      for (const role of ROLES) heads[role].replaceChildren(h("b", "", ROLE[role]), document.createTextNode(names[role] ? ` — ${names[role]}` : ""));
      for (const td of tbody.querySelectorAll("td")) td.dataset.label = docName(td.dataset.role); // 좁은 폭 — 표 머리 대신 칸 위에
      for (const f of follows) { const on = c.assign[f.other].has(f.id); f.span.textContent = on ? f.text || "—" : "—"; f.span.dataset.active = on ? "1" : "0"; }
      units.replaceChildren(...ROLES.map((role) => {
        const li = h("li"), ids = ordered(c.assign[role]);
        li.dataset.role = role;
        li.append(h("b", "", docName(role)), document.createTextNode(": " + (ids.length ? ids.map(stageName).join(" › ") : "—"))); // 그 문서에 차례로 하는 단계 — 「 › 」 = 다음(워크플로우 전체 줄 · 만든 글과 같은 기호)
        return li;
      }));
      // 고치기 · 복제 — 「문서 검토」 의 LLM 검증·보완을 하는 문서는 서버가 준 값(llm) 그대로 보인다(옛 줄은 원본만 — 칸의 글이 말하는 규칙과 다를 수 있다). 고른 단계를 바꾸면 저장할 때 서버가 다시 정한다(화면은 셈하지 않는다)
      const keep = sameAssign({ source: [...c.assign.source], target: [...c.assign.target] }, c.from || { source: [], target: [] });
      llmLine.hidden = !(c.llm && ROLES.some((r) => c.assign[r].has("stage_review")));
      llmLine.dataset.keep = keep ? "1" : "0";
      if (!llmLine.hidden) llmLine.replaceChildren(h("b", "", "「문서 검토」 의 LLM 검증·보완: "),
        document.createTextNode(keep ? (c.llm.length ? c.llm.map((r) => `${ROLE[r] || r}${names[r] ? `(${names[r]})` : ""}`).join(" · ") : "하지 않음") : "저장할 때 고른 단계로 다시 정합니다"),
        h("span", "wf-muted", keep ? " — 저장된 값(고른 단계를 바꾸면 저장할 때 다시 정합니다)" : ""));
      warn.hidden = !(c.assign.target.has("stage_fill") && !c.assign.target.has("stage_fit"));
    }
    sync();
    const save = h("button", "btn primary", c.busy ? "저장 중…" : c.key ? "고친 것 저장" : "워크플로우 만들기"), cancel = h("button", "btn", "취소"), acts = h("div", "wf-form-acts");
    save.type = "submit"; save.disabled = c.busy;
    c.saveBtn = save;
    const std = h("details", "wf-std-pick"), lines = h("div", "wf-lines"); // 표 = 표준 차례로 채우기(문서마다 단계 고르기 — 고르면 줄 목록이 그 표준 차례로) · 줄 목록 = 묶음 › 줄(정의 v2)
    std.open = c.mode === "std";
    std.hidden = !!shapeBox(c); // 표(문서 역할 × 단계)는 이관형의 표준 차례 — 취합형에는 두지 않는다(줄 목록만)
    std.append(h("summary", "", "표준 차례로 채우기 — 문서마다 단계 고르기"), pick);
    c.linesBox = lines;
    linesDraw(c);
    cancel.type = "button";
    cancel.addEventListener("click", () => { composing = null; composeDraw(); });
    acts.append(save, cancel);
    if (c.err) { const e = h("p", "wf-err", c.err); e.setAttribute("role", "alert"); acts.append(e); }
    form.append(h("h3", "", c.key ? `「${c.name}」 고치기` : c.copyOf ? `새 워크플로우 — 「${c.copyOf}」 복제` : "새 워크플로우"), field("이름", name), field("한 줄 설명", desc),
      block("문서 입출력", ioEl(c, () => { sync(); std.hidden = !!shapeBox(c); std.open = c.mode === "std"; if (c.mode === "std") stdFill(c); else linesChanged(c); })), // 문서 입출력이 바뀌면 문서 이름 · 줄 목록(틀의 처음 것 — shapeFlow) · 서버 검사를 새로
      ...(lock ? [lock] : []), block("단계(묶음 › 줄)", lines), std, field("전제(선택)", premise), acts); // 여러 컨트롤이 든 칸은 label 이 아니라 div(누르면 첫 컨트롤로 가지 않게)
    return form;
  }

  // ---- 도구 설명 열(spec_워크플로우 ② §18-15 「도구 설명」 · design.md §22 — 2026-11-20 사용자 "우측에 각 도구가 어떤 역할을 하는지 설명해줘. 자리연결누르면 우측 열에 설명을 넣어주 astra 랑 협의해서 사람이 이해하기 쉽게 구성해줘.. 모든도구"):
  // 조립 폼 · 단계 폼의 **오른쪽 열**. 줄(도구) 카드를 누르면 그 도구의 설명 — 아무것도 안 골랐으면 그 틀의 도구 목록(넣기 전에도 읽게 · 이름을 누르면 그 도구의 설명).
  // 설명의 차례(astra 협의 — artifacts/unit_help_astra_2026-11-20/): 이름 · 한 문장(하는 일) · 누가 · 문서 → 「어느 문서에 쓰나요?」 → 「먼저 필요한 것」 → 「알아 둘 것」 → 「결과는 어디서 보나요?」 → 「왜 필요한가요?」 → 「예」 → 「이 결과를 쓰는 도구」. 글이 없는 칸은 서지 않는다.
  // 글의 원본은 둘로 나뉜다(같은 사실을 두 번 적지 않는다): 쉬운 말 = 서버의 units[].help(app/unit_help.py — easy · first · care · see · why · eg · who) ·
  // 누가 · 문서 · 어느 문서에 · 앞에 놓을 도구 · 이 결과를 쓰는 도구 = units 의 값(카드의 꼬리표 · 넣기 고르기와 같은 값을 글로 — 화면이 새 사실을 셈하지 않는다). 등록부의 조건 글은 싣지 않는다(손으로 할 때의 글이라 자동 진행과 어긋난다).
  // help 를 안 주는 서버면 units 값으로 그릴 수 있는 것만 보이고 「이 도구의 설명을 아직 읽을 수 없습니다」 한 줄. 줄 편집기의 함수(rowEl · linesDraw …)는 고치지 않는다 — 누름은 c.linesBox 에 위임하고 고른 표시는 다시 그린 뒤 helpMark 가 붙인다.
  // 고른 것 = 도구(줄 key) 하나다 — 같은 도구를 여러 번 놓았으면 그 카드 모두에 표시하고 「지금 이 조립에서는」 이 어느 문서에 몇 곳인지 적는다(카드 하나하나를 따로 쫓지 않는다: 줄을 옮기면 자리가 바뀐다).
  const helpHomes = (c) => { const box = shapeBox(c); return Object.fromEntries(box && Array.isArray(box.homes) ? box.homes.map((x) => [x.id, x.name]) : ((T && T.stages) || []).map((st) => [st.id, st.name])); }; // 줄이 사는 단계의 이름(넣기 고르기의 묶음 이름과 같다)
  const helpOf = (u) => (u && u.help && typeof u.help === "object" && typeof u.help.easy === "string" ? u.help : null);
  function helpWho(u, hp) { // 누가 하나 — 글(help.who)이 있으면 그것(단위의 값만으로는 틀리게 읽히는 줄: 사람이 확정하는 줄 · 단추로만 유료인 줄) · 없으면 단위의 값. 「무료」 라고는 적지 않는다(값이 비어도 유료 길이 있는 줄이 있다)
    if (!hp) return null; // 설명을 못 읽은 응답 — 단위의 값만으로 「자동으로 합니다」 라고 단정하지 않는다(사람이 정하는 줄 · 조건부로 유료인 줄이 있다: astra 2차)
    const human = u.kind === "hand" || u.kind === "pick" || /^사람/.test(hp.who || "");
    const text = hp.who ? hp.who : u.kind === "hand" ? "사람이 합니다 — 「했음」 이 없으면 자동 진행이 이 줄에서 멈춥니다" : u.kind === "pick" ? "사람이 직접 합니다 — 자동 진행은 기다리지 않고 지나갑니다" : u.paid ? "LLM 이 합니다 — 유료" : "자동으로 합니다";
    return { text, kind: human ? "human" : u.paid ? "llm" : "", icon: human ? "human" : u.paid ? "llm" : "script" };
  }
  function helpDoc(u, c) { // 문서가 바뀌나 — 바뀌면 **어느 문서가 · 언제**(원본 문서에 놓으면 원본 문서가 바뀐다 · 자동 줄 = 바꿀 것이 있으면: 이미 맞음 · 0건이면 그대로 / 사람이 하는 줄 = 사람이 반영할 때)
    if (u.change !== "doc") return { kind: "", text: "문서는 그대로입니다" };
    const r = (u.roles || []).filter((x) => ROLES.includes(x)), when = u.kind === "pick" || u.kind === "hand" ? "사람이 반영할 때 " : "바꿀 것이 있으면 ";
    const what = oneDoc(c) ? "이 문서가" : u.place === "pair" || (r.length === 1 && r[0] === "target") ? "목적 문서가" : r.length === 1 ? "원본 문서가" : "놓은 칸의 문서가";
    return { kind: "doc", text: `${when}${what} 바뀝니다${!oneDoc(c) && u.place === "doc" && r.length === 2 ? " — 원본 문서 칸에 놓으면 원본 문서가 바뀝니다" : ""}` };
  }
  function helpWhere(u, c) { // 어느 문서에 쓰나 — units 의 place · roles · each(카드가 서는 칸과 같은 값). 다른 문서에서 읽는 것(구성의 기준 문서 …)은 글의 first · care 가 말한다
    if (oneDoc(c)) return "이 워크플로우의 문서 하나(목적 문서)에 씁니다.";
    if (u.place === "pair") return u.each ? "원본 문서마다 목적 문서와 짝지어 합니다 — 한 원본 문서에 잇달아 놓은 도구를 마친 뒤 다음 원본 문서로 갑니다. 두 칸이 한 줄로 움직입니다."
      : "원본 문서 → 목적 문서. 두 문서가 다 있어야 하는 도구라 두 칸이 한 줄로 움직입니다.";
    if (u.place === "flow") return "이 카드는 어느 칸에 놓아도 됩니다 — 놓은 칸과 상관없이 워크플로우 전체에 적용됩니다.";
    const r = (u.roles || []).filter((x) => ROLES.includes(x));
    return r.length === 2 ? "놓은 칸의 문서가 이 도구의 작업 대상입니다 — 목적 문서 · 원본 문서 어느 쪽에나, 문서마다 따로 놓습니다." : r.length === 1 ? `${ROLE[r[0]]}에만 놓습니다.${u.each ? " 원본 문서가 여럿이면 문서마다 되풀이합니다." : ""}` : "";
  }
  function helpNow(u, c) { // 지금 이 조립에서 그 도구가 놓인 곳 — 저장 줄의 on(하는 문서) 그대로 센다 → 글
    const n = { target: 0, source: 0, all: 0, none: 0 }, perDoc = u.place === "doc" && !oneDoc(c);
    for (const g of c.flow || []) for (const s of g.steps) { // 문서마다의 줄만 문서별로 센다 — 쌍 줄 · 워크플로우 전체 줄 · 문서 하나의 틀의 줄은 줄 하나가 한 곳이다(저장 줄의 on 이 두 문서여도 · 비어도)
      if (s.unit !== u.key) continue;
      const on = perDoc ? (s.on || []).filter((x) => ROLES.includes(x)) : null;
      if (!on) n.all++; else if (on.length) for (const r of on) n[r]++; else n.none++; // none = 할 문서가 없는 옛 문서 줄(파란 테두리도 안 선다)
    }
    const parts = [...(n.all ? [`${n.all}곳`] : []), ...LINE_COLS.filter((r) => n[r]).map((r) => `${ROLE[r]} ${n[r]}곳`)];
    return (parts.length ? `지금 이 조립에서는 ${parts.join(" · ")}에 놓여 있습니다(파란 테두리의 카드).` : n.none ? "" : "지금 이 조립에 놓인 곳이 없습니다.") + (n.none ? `${parts.length ? " " : ""}문서가 정해지지 않은 줄이 ${n.none}곳 있습니다.` : "");
  }
  function helpClick(c, e) { // 카드를 누름 — 단추(▲ ▼ 빼기) · 입력 칸 · 고르기 · 빈칸은 제 일을 한다(고른 것이 안 바뀐다)
    if (e.target.closest("button, input, select, textarea, a, label")) return;
    const li = e.target.closest("li.wf-line"), cell = e.target.closest(".wf-line-cell");
    if (!li || !cell) return;
    const unit = cell.dataset.unit || (li.dataset.role === "pair" || li.dataset.role === "none" ? li.dataset.unit : "");
    if (unit) helpPick(c, unit);
  }
  function helpPick(c, unit, how) { // 그 도구의 설명을 연다("" = 이 틀의 도구 목록 · how "fold" = 설명 접기: 목록도 접고 방금 보던 카드로) — 설명을 여는 것은 조립(줄 · 검사 · 저장)을 바꾸지 않는다
    const box = c.helpBox, inside = !!(box && box.contains(document.activeElement)), prev = c.help;
    c.help = unit || "";
    if (!c.help) c.helpList = how !== "fold"; // 목록으로 돌아옴 — 좁은 창에서도 목록을 편 채로(접기는 한 줄로)
    helpSync(c);
    if (how === "fold") { const nm = c.linesBox && [...c.linesBox.querySelectorAll("b[data-help-for]")].find((x) => x.dataset.helpFor === prev); if (nm) nm.focus(); return; }
    if (!inside || !box) return; // 설명 열 안에서 옮겨 갔을 때만 초점을 따라 옮긴다(카드를 누른 것이면 카드에 그대로): 설명 = 도구 이름 · 목록 = 방금 읽던 항목
    const to = c.help ? box.querySelector(".wf-help-name") : [...box.querySelectorAll(".wf-help-item")].find((x) => x.dataset.helpGo === prev) || box.querySelector(".wf-help-back");
    if (to) to.focus();
  }
  function helpSync(c) { helpDraw(c); helpMark(c); if (window.WfAgents) WfAgents.sync(c); navToolsDraw(); } // 줄 목록을 다시 그린 뒤에도(linesDraw 끝) — 놓인 곳의 수 · 고른 표시 · 틀이 바뀐 도구 목록 · 「에이전트」 열(② §18-16)도 같은 고름으로
  function helpMark(c) { // 고른 도구가 놓인 카드에 표시 + 카드 이름을 자판으로도 누를 수 있게(linesDraw 가 줄을 갈아 끼운 뒤마다)
    const box = c && c.linesBox;
    if (!box || !c.helpBox) return;
    [...box.querySelectorAll(".wf-lines-group")].forEach((group, gi) => {
      for (const li of group.querySelectorAll("li.wf-line")) {
        const wide = li.dataset.role === "pair" || li.dataset.role === "none";
        for (const cell of li.querySelectorAll(".wf-line-cell")) {
          const unit = cell.dataset.unit || (wide ? li.dataset.unit : ""), nm = cell.querySelector(".wf-line-name > b");
          if (!unit) continue;
          if (c.help === unit) cell.dataset.help = "1"; else delete cell.dataset.help;
          if (nm && !nm.dataset.helpFor) {
            nm.dataset.helpFor = unit;
            nm.dataset.helpAt = `${gi}:${li.dataset.ri}:${cell.dataset.role || ""}`; // 그 카드의 자리(다시 그린 뒤 자판 초점을 되찾는 열쇠)
            nm.tabIndex = 0;
            nm.setAttribute("role", "button");
            nm.title = "이 도구의 설명 보기";
            nm.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); helpPick(c, unit); } });
            const nu = unitOf(unit, c); // 도구 이름 고치기(② §18-19) — 카드의 이름을 두 번 누르면 그 도구의 설명을 열고 바로 이름을 고친다(한 번 = 설명 보기 그대로 · 고친 도구는 가리키면 기본 이름)
            if (nameCan(nu) && !c.locked) {
              nm.title = `이 도구의 설명 보기 · 두 번 누르면 이름 바꾸기${nu.name !== nu.base ? `\n기본 이름 「${nu.base}」` : ""}`;
              nm.addEventListener("dblclick", (e) => { e.preventDefault(); nameStart(c, unit); });
            }
          }
          if (nm) nm.setAttribute("aria-pressed", c.help === unit ? "true" : "false");
        }
      }
    });
    if (c.helpFocus && (!document.activeElement || document.activeElement === document.body)) { // 카드 이름에 초점이 있던 채 줄을 다시 그렸다(늦게 온 서버 검사 …) — 같은 자리의 이름으로(linesDraw 의 초점 복원은 data-lf 가 있는 컨트롤만 안다)
      const to = [...box.querySelectorAll("b[data-help-at]")].find((x) => x.dataset.helpAt === c.helpFocus);
      if (to) to.focus({ preventScroll: true });
    }
  }
  function helpFocusWatch(c, box) { // 줄 편집기 안의 초점 — 카드 이름에 있으면 그 자리를 기억한다(다른 곳으로 옮기면 잊는다 · 다시 그려서 없어진 것이면 그대로 둔다)
    box.addEventListener("focusin", (e) => { c.helpFocus = e.target instanceof Element && e.target.matches("b[data-help-at]") ? e.target.dataset.helpAt : ""; });
    box.addEventListener("focusout", (e) => { if (e.relatedTarget || (e.target instanceof Element && e.target.isConnected)) c.helpFocus = ""; });
  }
  function helpSec(name, ...kids) { const s = h("section", "wf-help-sec"); s.append(h("h5", "", name), ...kids); return s; }
  function helpChips(c, list) { // 다른 도구로 가는 이름 단추들
    const box = h("span", "wf-help-chips");
    for (const v of list) { const b = h("button", "wf-chip wf-help-go", v.name); b.type = "button"; b.dataset.helpGo = v.key; b.addEventListener("click", () => helpPick(c, v.key)); box.append(b); }
    return box;
  }
  function helpUnitEl(c, u) { // 도구 하나의 설명 — 위에서 아래로: 이름 · 한 문장 · (누가 · 문서) · 어느 문서에 쓰나요? · 먼저 필요한 것 · 알아 둘 것 · 결과는 어디서 보나요? · 왜 필요한가요? · 예 · 이 결과를 쓰는 도구
    const box = h("article", "wf-help-unit"), hp = helpOf(u), who = helpWho(u, hp), doc = helpDoc(u, c), where = helpWhere(u, c), facts = h("ul", "wf-help-facts");
    box.dataset.unit = u.key;
    const fact = (label, text, kind, icon) => { const li = h("li"), t = h("span", "wf-help-fact" + (kind ? ` wf-t-${kind}` : "")); if (icon) t.append(wfIcon(icon)); t.append(document.createTextNode(text)); li.append(h("span", "wf-help-label", label), t); facts.append(li); };
    if (who) fact("누가", who.text, who.kind, who.icon);
    fact("문서", doc.text, doc.kind, doc.kind === "doc" ? "doc" : "");
    if (u.optional) fact("선택", "필요할 때만 놓는 도구입니다", "", "");
    if (u.server === false) fact("아직", "서버가 아직 이 도구를 돌리지 못합니다", "", "");
    const name = h("h4", "wf-help-name", u.name);
    name.tabIndex = -1; // 목록 · 이름 칩에서 옮겨 오면 초점이 여기로(자판 · 읽어 주는 도구가 설명의 처음부터)
    box.append(name);
    if (nameCan(u)) box.append(WfNames.row(nameCtx(c, u))); // 「이름 바꾸기」(② §18-19 — 이 도구를 쓰는 모든 워크플로우의 화면에: workflow_names.js)
    if (u.only && u.only.label) { // 전용 표시(② §18-17 — 그 도구가 받는 문서: 스크립트가 그 문서만 안다) — 이름 바로 아래: 「○○ 전용」 꼬리표 + 까닭 한 문장(서버 응답 units[].only 그대로)
      const p = h("p", "wf-help-only");
      p.append(tag(u.only.label, "only"), document.createTextNode(u.only.why ? ` ${u.only.why}` : ""));
      box.append(p);
    }
    if (hp) box.append(h("p", "wf-help-easy", hp.easy));
    else { const p = h("p", "wf-help-off", "이 도구의 설명을 아직 읽을 수 없습니다 — 아래는 지금 알 수 있는 것입니다."); p.setAttribute("role", "status"); box.append(p); }
    box.append(facts);
    box.append(helpSec("어느 문서에 쓰나요?", ...(where ? [h("p", "", where)] : []), h("p", "wf-help-now wf-muted", helpNow(u, c))));
    // 먼저 필요한 것 — 쉬운 글(first: 실제로 필요한 조건은 여기 문장으로) + 앞 도구(units 의 uses: must = 조립에서 꼭 앞에 놓는다 · 아니면 「관련된 앞 도구」 —
    // 그 결과가 이미 있거나 이 도구가 스스로 채우는 것도 있어(자리 연결은 빠진 분석을 먼저 한다) 「있어야 한다」 고 적지 않는다: astra 2차)
    const uses = usesOf(u).map((x) => ({ must: !!x.must, v: unitOf(x.unit, c) })).filter((b) => b.v), must = uses.filter((b) => b.must).map((b) => b.v), soft = uses.filter((b) => !b.must).map((b) => b.v);
    if ((hp && hp.first) || uses.length) {
      const dl = h("dl", "wf-help-order");
      if (must.length) row(dl, "앞에 놓을 도구", helpChips(c, must));
      if (soft.length) row(dl, "관련된 앞 도구", helpChips(c, soft));
      box.append(helpSec("먼저 필요한 것", ...(hp && hp.first ? [h("p", "", hp.first)] : []), ...(uses.length ? [dl] : [])));
    }
    if (hp && hp.care) box.append(helpSec("알아 둘 것", h("p", "", hp.care)));
    if (hp && hp.see) box.append(helpSec("결과는 어디서 보나요?", h("p", "", hp.see)));
    if (hp && hp.why) box.append(helpSec("왜 필요한가요?", h("p", "", hp.why)));
    if (hp && hp.eg) box.append(helpSec("예", h("p", "wf-help-eg", hp.eg)));
    if (u.kind === "hand") { // 사람이 하는 일 — 이 조립에 놓은 줄마다 사람이 적은 이름 · 글(줄마다 따로 「했음」 을 받는다)
      const mine = (c.flow || []).flatMap((g) => g.steps.filter((s) => s.unit === u.key));
      if (mine.length) { const ul = h("ul", "wf-help-hands"); for (const s of mine) { const li = h("li"); li.append(h("b", "", s.name || u.name), ...(s.note ? [document.createTextNode(` — ${s.note}`)] : [])); ul.append(li); } box.append(helpSec("이 조립에 놓은 사람이 하는 일", ul)); }
    }
    const after = unitsOf(c).filter((v) => v.key !== u.key && usesOf(v).some((x) => x.unit === u.key)); // 이 도구의 결과를 쓰는 도구(바로 다음에 오는 줄이라는 뜻이 아니다)
    if (after.length) box.append(helpSec("이 결과를 쓰는 도구", helpChips(c, after)));
    if (u.key === "lineTidy" && window.LineTidyRules) { // 줄 정리의 「규칙」(spec_줄정리 ② §6 — 이 PC 의 설정: line_tidy_rules.js) — 그 절만 다시 그린다(폼 · 열 전체는 그대로)
      const redraw = () => { const old = box.querySelector("[data-lt-rules]"); if (old && old.isConnected) old.replaceWith(LineTidyRules.sec(redraw)); };
      box.append(LineTidyRules.sec(redraw));
    }
    return box;
  }
  function helpListEl(c) { // 그 틀의 도구 모두 — 사는 단계로 묶어(넣기 고르기와 같은 차례 · 같은 묶음 이름)
    const box = h("div", "wf-help-list"), homes = helpHomes(c), groups = new Map();
    for (const u of unitsOf(c)) { const home = u.kind === "hand" ? "사람이 하는 일" : homes[u.home] || u.home || ""; if (!groups.has(home)) groups.set(home, []); groups.get(home).push(u); }
    for (const [home, list] of groups) {
      const sec = h("section", "wf-help-group"), ul = h("ul");
      if (home) sec.append(h("h5", "", home));
      for (const u of list) {
        const li = h("li"), b = h("button", "wf-help-item"), hp = helpOf(u), top = h("span", "wf-help-item-top"), who = helpWho(u, hp);
        b.type = "button"; b.dataset.helpGo = u.key;
        top.append(h("b", "", u.name));
        if (who ? who.kind === "human" : u.kind === "hand" || u.kind === "pick") top.append(tag("사람", "human", "human")); // 설명의 「누가」 와 같은 판단(사람이 확정 · 지정하는 줄도)
        if (u.change === "doc") top.append(tag("문서 바뀜", "doc", "doc"));
        if (u.optional) top.append(tag("선택", "soft"));
        if (u.only && u.only.label) { const t = tag("전용", "only"); t.title = u.only.label; top.append(t); } // 전용 표시(② §18-17) — 목록에서는 짧게(가리키면 어느 문서 전용인지)
        b.append(top, ...(hp ? [h("span", "wf-help-item-easy", hp.easy)] : []));
        b.addEventListener("click", () => helpPick(c, u.key));
        li.append(b);
        if (u.paid) { li.classList.add("wf-prompt-tool"); li.append(builderPromptTag(u, c)); }
        ul.append(li);
      }
      sec.append(ul); box.append(sec);
    }
    return box;
  }
  function helpDraw(c) {
    const box = c && c.helpBox;
    if (!box) return;
    const u = c.help ? unitOf(c.help, c) : null, head = h("div", "wf-help-head"), keep = box.scrollTop, same = box.dataset.unit === (u ? u.key : "");
    const a = document.activeElement, focus = a && box.contains(a) ? a.dataset.helpGo || (a.classList.contains("wf-help-back") ? "back" : "") : ""; // 다시 그려도 초점은 그대로
    if (c.help && !u) c.help = ""; // 틀을 바꾸거나 해서 그 도구가 이 틀에 없음 — 목록으로
    head.append(h("h3", "", "도구 설명"));
    const back = h("button", "btn sm wf-help-back", u ? "이 틀의 도구 보기" : c.helpList ? "목록 접기" : "이 틀의 도구 보기"); // 설명을 보는 중 = 목록으로 · 목록 = (좁은 창에서만 보이는) 펴고 접기
    back.type = "button";
    back.addEventListener("click", () => { if (u) helpPick(c, ""); else { c.helpList = !c.helpList; helpSync(c); } });
    head.append(back);
    if (u) { // 「설명 접기」(좁은 창에서만 보인다 — 폼 위의 띠를 한 줄로 접고 방금 보던 카드로 돌아간다: 띠가 가린 앞 묶음을 다시 보게)
      const fold = h("button", "btn sm wf-help-fold", "설명 접기");
      fold.type = "button";
      fold.addEventListener("click", () => helpPick(c, "", "fold"));
      head.append(fold);
    }
    box.dataset.unit = u ? u.key : "";
    box.dataset.list = c.helpList ? "open" : "closed";
    box.replaceChildren(head, ...(u ? [helpUnitEl(c, u)] : [h("p", "wf-help-hint", "줄(도구) 카드를 누르면 그 도구가 하는 일이 여기에 보입니다. 넣기 전에 읽으려면 아래 목록에서 고르세요."), helpListEl(c)]));
    if (focus) { const to = focus === "back" ? box.querySelector(".wf-help-back") : [...box.querySelectorAll("[data-help-go]")].find((x) => x.dataset.helpGo === focus); if (to) to.focus({ preventScroll: true }); }
    box.scrollTop = same ? keep : 0;
  }
  function helpWrap(form, c, sec) { // 폼 옆에 설명 열을 세운다 → 두 칸 상자(폼 | 도구 설명) · sec = 그 절(넓은 절 표시 wf-wide — :has() 를 쓰지 않는다: design.md)
    const cols = h("div", "wf-compose-cols"), aside = h("aside", "wf-help");
    aside.setAttribute("aria-label", "도구 설명");
    if (sec) sec.classList.add("wf-wide");
    c.helpBox = aside;
    if (c.linesBox) { c.linesBox.addEventListener("click", (e) => helpClick(c, e)); helpFocusWatch(c, c.linesBox); }
    cols.append(form, aside);
    // 「에이전트」 열(spec_워크플로우 ② §18-16 — workflow_agents.js: 설명 열의 오른쪽 형제 · 고른 줄이 쓰는 에이전트의 스킬 · 도구 · 프롬프트 · 덧붙이는 글) — 고름은 설명 열과 같다(c.help)
    if (window.WfAgents) WfAgents.mount(cols, c, sec, { unit: (k) => unitOf(k, c), units: () => unitsOf(c), family: () => (shapeBox(c) ? c.shape : "relay"), pick: (k) => helpPick(c, k), workflow: !c.single });
    if (window.WfReqs) WfReqs.mount(cols, { family: () => (shapeBox(c) ? c.shape : "relay") }); // 「요구사항」(② §18-20 — workflow_reqs.js: 줄 카드 · 목차의 도구를 오른쪽 단추로 누르면 그 도구의 요구사항) — 이 폼의 틀만 알려 준다(도구의 키 = 틀 + 줄 key)
    helpSync(c);
    return cols;
  }

  // ---- 저장한 양식 · 문서 칸(spec_워크플로우 ② §18-9 「양식」 · 고친 규칙 ② §18-12 ⑧ — 2026-11-20 사용자 "템플릿은 워크플로우 설정에서 고정 또는 default 값을로" → 물어서 받은 답 「양식 파일」)
  // 저장한 양식 = 워크플로우의 목적 문서 칸에 넣을 양식 파일(서버 전체 — GET /api/form-files · 파일은 올린 그대로 · 고치려면 새로 올린다).
  // 문서 칸 = 워크플로우 절의 「받는 문서」 아래 한 줄 — 역할마다(원본 → 목적) · 목적 문서 칸에만 양식을 건다: 「양식: 없음 · 기본값 · 고정」 + 저장한 양식 고르기(PUT /api/workflow-slots/{job}). 붙박이 · 조립한 것 모두.
  // 걸 수 있는지(워크플로우 · 형식 · 문서 종류)는 서버가 정한다(jobs[{job, kind, formats}] · noForm{job: 까닭}) — 화면은 그 목록대로 고를 것을 추리고, 거절 글은 서버의 것 그대로. 화면 말: 「저장한 양식」 · 「양식으로 저장」 · 「웹에서 직접 올림」(= 없음 — 아래 FF_PICK) · 「양식: 기본값 · 고정」(「템플릿」 은 쓰지 않는다).
  let FF = null, ffErr = ""; // GET /api/form-files | null(못 읽음 — 옛 서버면 이 절 · 줄이 서지 않는다)
  // 「문서 칸」 의 설정(워크플로우 설정 — 양식: 없음 · 기본값 · 고정)은 고르는 즉시 저장된다(저장 단추가 따로 없다). 2026-11-21 사용자 「워크플로우 설정에 저장버튼이 없냐」 — 저장된 것이 안 보였다:
  // 저장한 칸마다 「✓ 저장됨 HH:MM」 을 그 칸 옆에 둔다(ffRedraw 로 줄을 새로 그려도 남게 — 키 = 워크플로우:역할) · 고르기의 풍선 글 「고르면 바로 저장됩니다」.
  const ffSavedAt = new Map();
  const ffClock = (ms) => { const d = new Date(ms); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const FF_MODE = { "": "없음", default: "기본값", fixed: "고정" };
  // 「웹에서 직접 올림」 체크 박스(2026-11-21 사용자 — 원본 문서 칸에 다른 종류로 이미 있는 양식을 올려 거절 글이 뜬 것을 보이며 "이거는 웹에서 사용자가 직접 올리도록 하는 체크 박스를 넣어줘"):
  // 켜짐 = 그 칸에 양식을 걸지 않는다(설정 없음 = 전의 「양식: 없음」 — 시작할 때 사용자가 첫 화면에서 그 칸의 문서를 올린다) · 고르기 · 「양식 올리기…」 · 거절 글은 숨는다.
  // 끔 = 양식을 건다 — 「양식: 기본값 · 고정」(「없음」 은 이 체크 박스가 맡아 고르기에서 뺐다) + 저장한 양식 · 「양식 올리기…」. 서버 설정의 꼴은 그대로(없음 = null).
  const FF_PICK = { default: "기본값", fixed: "고정" };
  const ffWebOff = new Set(); // 워크플로우 절 · 고치기 폼에서 체크 박스를 껐지만 아직 걸 양식이 없는 칸(워크플로우:역할) — 다시 그려도 꺼진 채(올리기 단추가 보이게)
  function slotWeb(name, title, on) { // 체크 박스 하나(라벨 「웹에서 직접 올림」) — 바꾸면 부르는 쪽이 듣는다
    const lab = h("label", "wf-slot-web"), box = h("input");
    box.type = "checkbox"; box.name = name; box.checked = on;
    lab.title = `켜면 이 칸에 양식을 걸지 않고, 시작할 때 사용자가 웹에서 ${title}${josa(title, "을", "를")} 직접 올립니다 · 끄면 저장한 양식을 겁니다(기본값 · 고정)`;
    lab.append(box, h("span", "", "웹에서 직접 올림"));
    return lab;
  }
  const FF_KIND = { "": "정하지 않음", plan: "사업계획서", report: "연차보고서" };
  const ffDate = (at) => { const d = new Date((at || 0) * 1000); return at && Number.isFinite(d.getTime()) ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}` : ""; };
  const ffSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`);
  const ffJob = (job) => (FF && (FF.jobs || []).find((j) => j.job === job)) || null;
  const ffFits = (f, j) => j && (j.formats || []).includes(f.fmt) && (!j.kind || f.kind === j.kind); // 그 워크플로우의 목적 칸에 걸 수 있나(서버 form_files_api.fits 와 같은 셈 — 거절 글은 서버의 것)
  async function formsLoad() {
    try { const r = await fetch("/api/form-files", { headers: { Accept: "application/json" } }); FF = r.ok ? await r.json() : null; ffErr = r.ok || r.status === 404 ? "" : `HTTP ${r.status}`; }
    catch (e) { FF = null; ffErr = e.message; }
  }
  async function ffSend(url, opts) { // → {ok, data, msg} — 서버의 글 그대로(400 값이 틀림 · 404 없음 · 409 쓰는 양식 · 목록 파일을 못 읽음)
    try {
      const r = await fetch(url, opts), data = await r.json().catch(() => ({}));
      return { ok: r.ok, data, msg: r.ok ? "" : (typeof data.detail === "string" && data.detail) || data.message || `HTTP ${r.status}` };
    } catch (e) { return { ok: false, data: {}, msg: e.message }; }
  }
  const JSON_H = { "Content-Type": "application/json" };
  function swapKeep(old, next) { // 새로 그린 것으로 바꾼다 — 그 안에 있던 초점은 같은 이름의 컨트롤로(고르기를 바꾸거나 양식을 올린 뒤에도 자판으로 이어 가게)
    const a = document.activeElement, n = a && old.contains(a) ? a.getAttribute("name") : "";
    old.replaceWith(next);
    const el = n ? next.querySelector(`[name="${CSS.escape(n)}"]`) : null;
    if (el && !el.disabled && !el.hidden) el.focus();
  }
  function ffRedraw() { // 양식 · 설정이 바뀐 뒤 — 저장한 양식 절과 모든 「문서 칸」 줄 · 펴 둔 조립 폼의 문서 칸을 새로
    formsDraw();
    for (const box of document.querySelectorAll(".wf-slots[data-job]")) { const t = D && D.tasks.find((x) => x.job === box.dataset.job); if (t) swapKeep(box, slotEl(t)); }
    if (ioRefresh) ioRefresh();
  }
  function slotEl(t) { // 「문서 칸」 — 역할마다 한 줄(원본 → 목적): 수가 1인 칸 = 양식 설정(없음 · 기본값 · 고정 + 저장한 양식 — ② §18-9: 걸 수 있는 칸은 서버의 jobs[].roles) · 여럿인 칸 = 문서마다 사람이 넣음
    const box = h("div", "wf-slots"), roles = rolesSorted(t.roles), j = ffJob(t.job), box0 = (FF && FF.slots && FF.slots[t.job]) || {};
    const jrOf = (role) => (!j ? null : Array.isArray(j.roles) ? j.roles.find((x) => x.role === role) || null : role === "target" ? j : null); // roles 를 안 주는 옛 서버 = 목적 칸만
    box.dataset.job = t.job;
    const ul = h("ul", "wf-slot-list");
    for (const r of roles.length ? roles : [{ role: "target", title: "목적 문서", name: "" }]) {
      const li = h("li", "wf-slot"), head = h("span", "wf-slot-role");
      li.dataset.role = r.role;
      head.append(h("b", "", roleTitle(r)), document.createTextNode(r.name ? ` — ${r.name}` : ""), ...(r.many ? [h("span", "wf-muted", "(여럿)")] : []));
      li.append(head);
      const jr = jrOf(r.role);
      if (r.many) li.append(h("span", "wf-muted", "문서마다 사람이 넣습니다(여럿인 칸에는 양식을 걸지 않습니다)"));
      else if (!FF) li.append(h("span", "wf-muted", ffErr ? `저장한 양식을 읽지 못했습니다: ${ffErr}` : "양식 설정은 서버를 다시 켠 뒤에 쓸 수 있습니다"));
      else if (!j) li.append(h("span", "wf-muted", (FF.noForm || {})[t.job] || (t.soon ? "준비 중인 워크플로우라 양식을 걸지 않습니다" : "이 워크플로우는 양식을 걸지 않습니다")));
      else if (!jr) li.append(h("span", "wf-muted", "실행마다 사람이 넣습니다"));
      else li.append(slotPick(t, jr, box0[r.role] || null, r.role, roleTitle(r)));
      ul.append(li);
    }
    box.append(ul);
    return box;
  }
  function slotPick(t, j, cur, role = "target", title = "목적 문서", quiet = false) { // 그 칸(수가 1 — 목적 · 이관의 원본)의 양식 설정 — [없음 | 기본값 | 고정] [저장한 양식 ▾] + 저장한 날 · 거절 글. j = 그 칸의 규칙(서버 jobs[].roles 의 하나 — formats · kind) · quiet = 설명 글 없이(조립 폼)
    const wrap = h("span", "wf-slot-pick"), combo = h("span", "wf-slot-combo"), mode = h("select", "wf-slot-mode"), form = h("select", "wf-slot-form"), note = h("span", "wf-muted"), err = h("span", "wf-slot-err"); // 줄 아래 거절 글(.wf-err 는 조립 폼의 저장 거절 글 — 섞지 않는다)
    const savedKey = `${t.job}:${role}`, saved = h("span", "wf-slot-saved"); // 바로 저장된 것을 보인다(저장 단추가 없는 칸 — 위 ffSavedAt)
    saved.setAttribute("role", "status");
    if (ffSavedAt.has(savedKey)) { saved.textContent = `✓ 저장됨 ${ffClock(ffSavedAt.get(savedKey))}`; saved.title = "고른 설정이 서버에 저장됐습니다 — 이 칸은 고르는 즉시 저장됩니다(저장 단추가 따로 없습니다)"; }
    mode.title = form.title = "고르면 바로 저장됩니다 — 저장 단추가 따로 없습니다";
    const fits = (FF.files || []).filter((f) => ffFits(f, j)), now = cur ? (FF.files || []).find((f) => f.id === cur.file) : null, tail = role === "target" ? "" : `-${role}`; // 목적 칸의 이름은 전 그대로(화면 검사 · 옛 고르기)
    const web = slotWeb(`slot-web-${t.job}${tail}`, title, !cur && !ffWebOff.has(savedKey)), box = web.querySelector("input"); // 켜짐 = 설정 없음(양식을 걸지 않음) — 위 FF_PICK
    box.title = "바꾸면 바로 저장됩니다 — 저장 단추가 따로 없습니다";
    mode.name = `slot-mode-${t.job}${tail}`;
    mode.setAttribute("aria-label", `${taskName(t.job)} — ${title} 칸의 양식`);
    for (const [v, label] of Object.entries(FF_PICK)) mode.append(new Option(`양식: ${label}`, v));
    mode.value = cur && FF_PICK[cur.mode] ? cur.mode : "default";
    form.name = `slot-form-${t.job}${tail}`;
    form.setAttribute("aria-label", `${taskName(t.job)} — ${title} 칸에 넣을 저장한 양식`);
    for (const f of fits) form.append(new Option(`${f.name}${ffDate(f.at) ? ` (${ffDate(f.at)})` : ""}`, f.id));
    if (now && !fits.includes(now)) form.append(new Option(`${now.name} — 지금은 걸 수 없음`, now.id));
    if (!form.options.length) form.append(new Option("걸 수 있는 양식이 없음", ""));
    form.value = now ? now.id : (fits[0] || {}).id || "";
    if (!fits.length && !cur) wrap.dataset.empty = "1";
    const need = [j.formats.join(" · "), j.kind ? FF_KIND[j.kind] || j.kind : ""].filter(Boolean).join(" · ");
    let up = null;
    const sync = () => {
      const on = box.checked;
      wrap.dataset.mode = on ? "" : mode.value;
      wrap.dataset.web = on ? "1" : "";
      mode.disabled = !fits.length && !cur;
      form.disabled = !fits.length;
      combo.hidden = mode.hidden = form.hidden = on || (!fits.length && !cur); // 고를 양식이 없으면 꺼진 고르기 둘을 세워 두지 않는다 — 「양식 올리기…」 만(slotDraft 와 같은 꼴)
      if (up) up.hidden = on;
      if (on) err.textContent = "";
      note.textContent = on ? `시작할 때 사용자가 웹에서 ${title}${josa(title, "을", "를")} 직접 올립니다 — 이 칸에는 양식을 걸지 않습니다`
        : !fits.length && !cur ? `걸 수 있는 양식이 없습니다 — 「양식 올리기…」 로 ${need} 양식을 올리세요`
          : mode.value === "fixed" ? `늘 이 양식으로 시작합니다 — 시작의 ${title} 칸에 다른 파일을 넣을 수 없습니다` : "시작할 때 이 양식이 미리 들어가 있고, 다른 파일로 바꿀 수 있습니다";
    };
    const send = async () => {
      const on = box.checked;
      if (!on && !form.value) { sync(); return; }
      box.disabled = mode.disabled = form.disabled = true;
      err.textContent = "";
      saved.textContent = "저장하는 중…";
      const r = await ffSend(`/api/workflow-slots/${encodeURIComponent(t.job)}`, { method: "PUT", headers: JSON_H, body: JSON.stringify({ [role]: on ? null : { file: form.value, mode: mode.value } }) });
      box.disabled = false;
      if (!r.ok) { saved.textContent = ""; sync(); err.textContent = `저장하지 못했습니다 — ${r.msg}`; return; }
      ffWebOff.delete(savedKey);
      ffSavedAt.set(savedKey, Date.now());
      await formsLoad();
      ffRedraw();
    };
    box.addEventListener("change", () => { // 켬 = 설정을 푼다(걸린 양식이 있을 때만 저장) · 끔 = 고를 양식이 있으면 그 칸에 건다(기본값 + 처음 양식 — 고르는 즉시 저장) · 없으면 「양식 올리기…」 를 보인다
      if (box.checked) { ffWebOff.delete(savedKey); if (cur) send(); else sync(); return; }
      ffWebOff.add(savedKey);
      if (form.value && fits.length) send(); else sync();
    });
    mode.addEventListener("change", send);
    form.addEventListener("change", send);
    err.setAttribute("role", "alert");
    up = slotUp(j, title, `slot-up-${t.job}${tail}`, async (f) => { // 올린 양식을 이 칸에 바로 건다(지금 「고정」 이면 고정 그대로 · 아니면 기본값) → 걸지 못하면 그 까닭 글
      const r = await ffSend(`/api/workflow-slots/${encodeURIComponent(t.job)}`, { method: "PUT", headers: JSON_H, body: JSON.stringify({ [role]: { file: f.id, mode: cur && cur.mode === "fixed" ? "fixed" : "default" } }) });
      if (!r.ok) return `양식 「${f.name}」 ${josa(f.name, "은", "는")} 저장했지만 이 칸에 걸지 못했습니다 — ${r.msg}`;
      ffWebOff.delete(savedKey);
      ffSavedAt.set(savedKey, Date.now());
      await formsLoad();
      ffRedraw();
      return "";
    });
    sync();
    combo.append(mode, form);
    wrap.append(web, combo, saved, up, ...(quiet ? [] : [note]), err);
    return wrap;
  }
  // 그 칸에서 바로 양식 올리기(2026-11-20 사용자 — 저장한 양식이 없어 꺼진 고르기 둘을 보이며 "이거 클릭도 안되고 왜 아무것도 안해?": 그 칸에서 할 수 있는 일이 없었고 설명 글도 뺀 뒤였다 — ② §18-9 「그 칸에서 올리기」).
  // 「양식 올리기…」 → 파일 고르기 → 저장한 양식으로 올린다(POST /api/form-files — 문서 종류 = 그 칸의 종류: 사람이 그 칸에 넣은 것이 그 종류라는 말이다) → done(양식) 이 그 칸에 건다(걸지 못하면 까닭 글을 돌려준다).
  // j = 그 칸의 규칙 {formats, kind} · 거절 글은 서버의 것 그대로 · 올린 양식을 그 칸에 걸 수 없으면(같은 내용이 다른 문서 종류로 이미 있음) 걸지 않고 까닭을 보인다 — 양식은 「저장한 양식」 목록에 남는다.
  function slotUp(j, title, name, done) {
    const wrap = h("span", "wf-slot-up"), file = h("input"), btn = h("button", "btn sm", "양식 올리기…"), err = h("span", "wf-slot-err");
    const exts = [...(j.formats.includes("hwpx") ? ["hwp", "hwpx"] : []), ...(j.formats.includes("docx") ? ["docx"] : [])], idle = () => { btn.disabled = false; btn.textContent = "양식 올리기…"; file.value = ""; };
    file.type = "file"; file.hidden = true; file.tabIndex = -1; file.accept = exts.map((x) => `.${x}`).join(",");
    file.setAttribute("aria-label", `${title} 칸에 넣을 양식 파일 고르기`);
    btn.type = "button"; btn.name = name;
    btn.title = `${title} 칸에 넣을 양식 파일(${exts.join(" · ")})을 올려 이 칸에 겁니다 — 「저장한 양식」 목록에도 남습니다`;
    err.setAttribute("role", "alert");
    btn.addEventListener("click", () => file.click());
    file.addEventListener("change", async () => {
      const f = file.files && file.files[0];
      if (!f) return;
      err.textContent = "";
      if (!exts.includes((/\.([^.]+)$/.exec(f.name) || [])[1]?.toLowerCase() || "")) { err.textContent = `이 칸은 ${exts.join(" · ")} 파일만 받습니다`; idle(); return; }
      btn.disabled = true; btn.textContent = "올리는 중…";
      const fd = new FormData();
      fd.append("file", f); fd.append("name", ""); fd.append("kind", j.kind || "");
      const r = await ffSend("/api/form-files", { method: "POST", body: fd });
      if (!r.ok) { err.textContent = `올리지 못했습니다 — ${r.msg}`; idle(); return; }
      await formsLoad();
      const got = (FF && (FF.files || []).find((x) => x.id === (r.data.file || {}).id)) || r.data.file || null;
      const msg = !got ? "올린 양식을 목록에서 찾지 못했습니다 — 다시 올리세요"
        : !ffFits(got, j) ? `같은 내용의 양식 「${got.name}」 ${josa(got.name, "이", "가")} 「문서 종류: ${FF_KIND[got.kind || ""] || got.kind}」 ${josa(FF_KIND[got.kind || ""] || got.kind, "으로", "로")} 이미 있어 이 칸에 걸 수 없습니다 — 「저장한 양식」 에서 문서 종류를 바꾸세요`
          : (await done(got)) || "";
      if (!msg) return; // 걸었다 — done 이 이 칸을 새로 그렸다
      formsDraw(); // 양식은 저장됐다 — 「저장한 양식」 절만 새로(이 칸은 까닭 글이 보이게 그대로)
      err.textContent = msg;
      idle();
    });
    wrap.append(btn, file, err);
    return wrap;
  }

  function formsSec() { const sec = h("section", "wf-sec wf-forms"); sec.id = "wfForms"; return sec; }
  const ffAdd = { busy: false, err: "", msg: "", works: null, samples: null, open: false }; // 양식 더하기 — 보내는 중 · 거절 글 · 알림 · 작업 목록(GET /api/works — 펼칠 때 한 번) · 예제 목록 · 사람이 폈나(다시 그려도 펴 둔 채)
  async function ffListsLoad() {
    if (ffAdd.loading) return;
    ffAdd.loading = true;
    const get = async (url) => { try { const r = await fetch(url, { headers: { Accept: "application/json" } }); return r.ok ? await r.json() : []; } catch { return []; } };
    const [works, samples] = await Promise.all([get("/api/works"), get("/api/samples")]);
    ffAdd.works = (Array.isArray(works) ? works : []).filter((w) => w && WORK_ID.test(w.id) && /\.(hwpx|docx)$/i.test(w.name || ""));
    ffAdd.samples = (Array.isArray(samples) ? samples : []).filter((s) => s && /\.(hwpx|docx)$/i.test(s.name || ""));
    ffAdd.loading = false;
    formsDraw();
  }
  async function ffSave(how, v) { // 양식 더하기 — how = file(올리기) · work(작업의 처음 올린 원본) · sample(예제)
    if (ffAdd.busy) return;
    Object.assign(ffAdd, { busy: true, err: "", msg: "" });
    formsDraw();
    let r;
    if (how === "file") {
      const fd = new FormData();
      fd.append("file", v.file); fd.append("name", v.name || ""); fd.append("kind", v.kind || "");
      r = await ffSend("/api/form-files", { method: "POST", body: fd });
    } else r = await ffSend(how === "work" ? `/api/form-files/from-work/${encodeURIComponent(v.id)}` : `/api/form-files/from-sample/${encodeURIComponent(v.id)}`,
      { method: "POST", headers: JSON_H, body: JSON.stringify({ name: v.name || "", ...(v.kind ? { kind: v.kind } : {}) }) });
    ffAdd.busy = false;
    if (!r.ok) ffAdd.err = `저장하지 못했습니다 — ${r.msg}`;
    else ffAdd.msg = r.data.made === false ? `같은 내용의 양식 「${r.data.file.name}」 이 이미 있습니다 — 그 양식을 그대로 씁니다` : `양식 「${r.data.file.name}」 을 저장했습니다`;
    await formsLoad();
    ffRedraw();
  }
  async function ffEdit(f, body, err) { // 이름 · 문서 종류 고치기(설정에 건 양식의 종류는 서버가 409)
    const r = await ffSend(`/api/form-files/${encodeURIComponent(f.id)}`, { method: "PUT", headers: JSON_H, body: JSON.stringify(body) });
    if (!r.ok) { err.textContent = `고치지 못했습니다 — ${r.msg}`; return; }
    await formsLoad();
    ffRedraw();
  }
  async function ffDelete(f) {
    if (!confirm(`저장한 양식 「${f.name}」 ${josa(f.name, "을", "를")} 지울까요?\n\n그 양식으로 이미 만든 작업은 그대로입니다. 되돌릴 수 없습니다.`)) return; // 되돌릴 수 없는 것만 묻는다(design.md §18)
    const r = await ffSend(`/api/form-files/${encodeURIComponent(f.id)}`, { method: "DELETE" });
    if (!r.ok) ffAdd.err = `지우지 못했습니다 — ${r.msg}`;
    await formsLoad();
    ffRedraw();
  }
  function formsDraw() { // 「저장한 양식」 절 — 목록(이름 · 파일 · 형식 · 크기 · 저장한 날 · 문서 종류 · 쓰는 워크플로우 · 내려받기 · 지우기) + 양식 더하기(올리기 · 작업의 처음 올린 원본 · 예제)
    const sec = $("wfForms");
    if (!sec) return;
    const h2 = h("h2");
    h2.append(h("span", "wf-kind", "저장한 양식"), document.createTextNode("워크플로우의 목적 문서 칸에 넣을 양식"));
    sec.replaceChildren(h2);
    if (!FF) { const p = h("p", "wf-lead", ffErr ? `저장한 양식을 읽지 못했습니다: ${ffErr}` : "저장한 양식은 서버를 다시 켠 뒤에 쓸 수 있습니다"); p.setAttribute("role", "status"); sec.append(p); return; }
    headHelp(sec, h2, "저장한 양식 — 설명", "워크플로우 절의 「문서 칸」 에서 수가 1인 문서 칸(목적 문서 · 이관의 원본 문서)에 양식을 겁니다 — 기본값(시작할 때 미리 들어가 있고 다른 파일로 바꿀 수 있음) · 고정(늘 그 양식). "
      + "양식 파일은 올린 그대로 두고 고치지 않습니다(고치려면 새로 올립니다). 이미 하던 작업의 문서는 설정을 바꿔도 그대로입니다.");
    if (FF.broken) { const p = h("p", "wf-compose-broken", "저장한 양식의 목록 파일을 읽지 못했습니다 — 목록이 보이지 않고, 그 파일을 덮지 않으려고 서버가 새로 저장하거나 고치지 않습니다."); p.setAttribute("role", "alert"); sec.append(p); }
    const list = h("ul", "wf-ff-list");
    for (const f of FF.files || []) {
      const li = h("li", "wf-ff-row"), top = h("div", "wf-ff-top"), name = h("input"), kind = h("select"), err = h("span", "wf-err"), used = h("span", "wf-links");
      li.dataset.form = f.id;
      name.value = f.name; name.maxLength = 60; name.setAttribute("aria-label", `양식 「${f.name}」 의 이름`);
      name.addEventListener("change", () => { if (name.value.trim() && name.value.trim() !== f.name) ffEdit(f, { name: name.value }, err); });
      for (const [v, label] of Object.entries(FF_KIND)) kind.append(new Option(`문서 종류: ${label}`, v));
      kind.value = f.kind || "";
      kind.setAttribute("aria-label", `양식 「${f.name}」 의 문서 종류`);
      kind.disabled = (f.usedBy || []).length > 0;
      kind.title = kind.disabled ? "워크플로우 설정에 건 양식의 문서 종류는 바꿀 수 없습니다 — 그 설정을 먼저 푸세요" : "그 문서 종류를 목적 문서로 하는 워크플로우에만 걸 수 있습니다";
      kind.addEventListener("change", () => ffEdit(f, { kind: kind.value }, err));
      const dl = link(`/api/form-files/${encodeURIComponent(f.id)}/file`, "내려받기", "btn sm"), del = h("button", "btn sm", "지우기");
      dl.setAttribute("download", "");
      del.type = "button";
      del.disabled = (f.usedBy || []).length > 0;
      del.title = del.disabled ? `이 양식을 건 워크플로우 설정이 ${(f.usedBy || []).length}개 있어 지울 수 없습니다 — 그 설정을 먼저 푸세요` : "이 양식을 지웁니다(그 양식으로 만든 작업은 그대로)";
      del.addEventListener("click", () => ffDelete(f));
      top.append(name, h("span", "wf-muted", [f.file, f.fmt, ffSize(f.size), ffDate(f.at) ? `저장한 날 ${ffDate(f.at)}` : ""].filter(Boolean).join(" · ")), kind, dl, del);
      for (const u of f.usedBy || []) { const a = link(`#${u.job}`, `${u.name || taskName(u.job)} · ${FF_MODE[u.mode] || u.mode}`, "wf-chip"); a.dataset.use = u.mode; used.append(a); }
      li.append(top, ...(f.usedBy && f.usedBy.length ? [(() => { const p = h("p", "wf-ff-used"); p.append(h("span", "wf-muted", "쓰는 워크플로우:"), used); return p; })()] : []));
      err.setAttribute("role", "alert");
      li.append(err);
      list.append(li);
    }
    if ((FF.files || []).length) sec.append(list);
    else sec.append(h("p", "wf-muted", "저장한 양식이 없습니다 — 아래에서 더하세요."));
    sec.append(formsAddEl());
  }
  function formsAddEl() { // 양식 더하기 — 파일 올리기 · 작업의 처음 올린 원본(「양식으로 저장」 — 지금 편집 상태가 아니다) · 예제. 이름 · 문서 종류는 비워도 된다(이름 = 파일 이름 · 종류 = 양식 이름 문단으로 짐작)
    const box = h("details", "wf-ff-add"), sum = h("summary", "", "양식 더하기 — 파일 올리기 · 작업의 원본 · 예제"), body = h("div", "wf-ff-add-body");
    box.open = ffAdd.open || !(FF.files || []).length || ffAdd.busy || !!ffAdd.err || !!ffAdd.msg;
    box.addEventListener("toggle", () => { ffAdd.open = box.open; if (box.open && !ffAdd.works) ffListsLoad(); });
    if (box.open && !ffAdd.works) Promise.resolve().then(ffListsLoad); // 펴 둔 채 그리면 그때 한 번(읽는 중이면 다시 안 읽는다 — ffListsLoad)
    const name = h("input"), kind = h("select");
    name.maxLength = 60; name.placeholder = "양식 이름(비우면 파일 이름)"; name.setAttribute("aria-label", "새 양식의 이름");
    for (const [v, label] of Object.entries(FF_KIND)) kind.append(new Option(v ? `문서 종류: ${label}` : "문서 종류: 짐작", v));
    kind.setAttribute("aria-label", "새 양식의 문서 종류");
    const common = h("div", "wf-ff-add-row wf-ff-add-head"), pair = h("div", "wf-ff-add-pair");
    pair.append(name, kind);
    common.append(pair);
    const rowOf = (label, control, btn) => { const r = h("div", "wf-ff-add-row"); r.append(h("span", "wf-field-name", label), control, btn); return r; };
    const file = h("input"), up = h("button", "btn sm primary", ffAdd.busy ? "저장 중…" : "올려 저장");
    file.type = "file"; file.accept = ".hwp,.hwpx,.docx"; file.setAttribute("aria-label", "양식 파일 고르기");
    up.type = "button"; up.disabled = ffAdd.busy;
    up.addEventListener("click", () => { if (file.files && file.files[0]) ffSave("file", { file: file.files[0], name: name.value, kind: kind.value }); else file.click(); });
    const work = h("select"), fromWork = h("button", "btn sm", "양식으로 저장");
    work.setAttribute("aria-label", "양식으로 저장할 작업");
    work.append(new Option(ffAdd.works ? (ffAdd.works.length ? "작업 고르기…" : "작업이 없습니다") : "작업 목록을 읽는 중…", ""));
    for (const w of ffAdd.works || []) work.append(new Option(`${w.name}${(w.task || {}).project ? ` — ${w.task.project}` : ""}`, w.id));
    fromWork.type = "button"; fromWork.disabled = ffAdd.busy;
    fromWork.title = "그 작업의 처음 올린 원본을 양식으로 저장합니다(지금 편집 상태가 아닙니다 — 편집한 것을 양식으로 삼으려면 내려받아 올리세요)";
    fromWork.addEventListener("click", () => { if (work.value) ffSave("work", { id: work.value, name: name.value, kind: kind.value }); });
    const sample = h("select"), fromSample = h("button", "btn sm", "예제에서 저장");
    sample.setAttribute("aria-label", "양식으로 저장할 예제");
    sample.append(new Option(ffAdd.samples ? (ffAdd.samples.length ? "예제 고르기…" : "예제가 없습니다") : "예제 목록을 읽는 중…", ""));
    for (const s of ffAdd.samples || []) sample.append(new Option(s.name, s.name));
    fromSample.type = "button"; fromSample.disabled = ffAdd.busy;
    fromSample.addEventListener("click", () => { if (sample.value) ffSave("sample", { id: sample.value, name: name.value, kind: kind.value }); });
    body.append(common, rowOf("파일", file, up), rowOf("작업의 원본", work, fromWork), rowOf("예제", sample, fromSample));
    if (ffAdd.err) { const e = h("p", "wf-err", ffAdd.err); e.setAttribute("role", "alert"); body.append(e); }
    if (ffAdd.msg) { const m = h("p", "wf-muted wf-ff-msg", ffAdd.msg); m.setAttribute("role", "status"); body.append(m); }
    box.append(sum, body);
    return box;
  }

  // ---- 도구 이름 고치기(spec_워크플로우 ② §18-19 — 2026-11-21 사용자 「도구 이름을 바꿀 수 없네?」 → 답 「도구 자체 (모든 워크플로우)」): 그리기 · 저장은 workflow_names.js(WfNames) — 여기는 훅뿐.
  // 고칠 수 있는 도구 = 서버가 기본 이름(units[].base)을 준 것(옛 서버는 안 준다 — 단추가 서지 않는다) · 「사람이 하는 일」 은 줄마다 이름이 따로 있어 뺀다. 틀 = 조립 폼의 틀(단계 폼 · 틀이 없는 폼은 이관형).
  const nameCan = (u) => !!(window.WfNames && u && typeof u.base === "string" && u.kind !== "hand");
  const nameCtx = (c, u) => ({ state: c.nm || (c.nm = {}), family: shapeBox(c) ? c.shape : "relay", unit: u.key, name: u.name, base: u.base, max: T && T.limits && T.limits.toolName,
    redraw: () => helpDraw(c), changed: () => namesReload() });
  function nameStart(c, unit) { // 카드의 이름을 두 번 누름 — 그 도구의 설명을 열고(고른 것 = c.help) 이름 고치기를 편다
    const u = unitOf(unit, c);
    if (!nameCan(u)) return;
    WfNames.start(c.nm || (c.nm = {}), unit, u.name);
    if (c.help === unit) helpDraw(c); else helpPick(c, unit);
  }
  async function namesReload() { // 이름을 고친 뒤 — 등록부 · 조립 자료를 다시 읽는다(카드 · 넣기 고르기 · 목차 · 워크플로우 절이 새 이름으로): 열어 둔 폼(줄 · 적던 글 · 고른 도구)은 그대로 · 스크롤도 그 자리로
    const main = $("wfMain"), top = main.scrollTop;
    await load();
    main.scrollTop = top;
  }
  // 우클릭 메뉴(② §18-20 — workflow_reqs.js 의 문 WfReqs.menu)에 「이름 바꾸기…」 를 얹는다 — 도구(줄 카드 · 목차의 도구 · 설명 열의 이름)를 눌렀을 때. 그 틀의 폼이 열려 있어야 고친다(설명 열이 폼 옆에 선다 — 없으면 꺼 두고 까닭을 적는다).
  if (window.WfNames && window.WfReqs && typeof WfReqs.menu === "function") WfReqs.menu((info) => {
    if (!info || info.kind !== "tool" || !info.unit || info.unit === "hand") return [];
    const c = navForm(), u = c && (shapeBox(c) ? c.shape : "relay") === info.family ? unitOf(info.unit, c) : null, off = !nameCan(u);
    return [{ label: "이름 바꾸기…", run: () => nameStart(c, info.unit), off,
      title: off ? "조립 폼에서 이 도구의 틀(문서 입출력)을 열면 이름을 고칠 수 있습니다" : "이 도구의 이름을 고칩니다 — 이 도구를 쓰는 모든 워크플로우의 화면에 그 이름으로 보입니다" }];
  });

  async function load() {
    const main = $("wfMain");
    await Promise.all([tasksLoad(), formsLoad()]);
    try {
      const r = await fetch("/api/workflow", { headers: { Accept: "application/json" } });
      if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
      D = await r.json();
    } catch (e) {
      const p = h("p", "wf-load wf-err", e.status === 404 ? "워크플로우는 서버를 다시 시작한 뒤에 볼 수 있습니다(새 기능)." : `워크플로우를 읽지 못했습니다: ${e.message}`), b = h("button", "btn sm", "다시 읽기");
      p.setAttribute("role", "alert");
      b.type = "button";
      b.addEventListener("click", () => { main.replaceChildren(h("p", "wf-load", "워크플로우를 읽는 중…")); load(); });
      main.replaceChildren(p, b);
      return;
    }
    navDraw();
    indexRoutes();
    const diagram = h("section", "wf-diagram"); diagram.id = "wfDiagram"; diagram.hidden = true;
    main.replaceChildren(diagram, overview(), composeSec(), stageSec(), formsSec(), ...D.tasks.map(taskSec), ...D.common.map(commonSec));
    composeDraw();
    stageDraw();
    formsDraw();
    go(location.hash);
  }

  let tick = 0;
  $("wfMain").addEventListener("scroll", () => { if (!tick) tick = requestAnimationFrame(() => { tick = 0; navSync(); }); }, { passive: true });
  addEventListener("hashchange", () => go(location.hash));
  document.querySelector(".wf-wrap").addEventListener("click", (event) => {
    const a = event.target.closest("a[href^='#']");
    if (!a || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); navigate(a.getAttribute("href"));
  });
  $("wfViewDiagram").addEventListener("click", () => setView("diagram"));
  $("wfViewList").addEventListener("click", () => setView("list"));
  const setAll = (open) => { for (const d of document.querySelectorAll("#wfMain .wf-sec details.wf-step, #wfMain .wf-sec details.wf-entry-group")) d.open = open; }; // 목록 보기의 단계 · 시작 점검 묶음
  $("wfOpenAll").addEventListener("click", () => setAll(true));
  $("wfCloseAll").addEventListener("click", () => setAll(false));
  load();
})();
