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

  function badges(s) {
    const box = h("div", "wf-badges");
    for (const b of s.by) box.append(tag(D.by[b] || b, b === "script" ? "" : b, b));
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
      const body = h("div", "wf-node-body"), meta = badges(s);
      if (s.change === "doc") meta.append(tag("문서 바뀜", "doc"));
      body.append(h("b", "", s.name), meta);
      a.append(h("span", "wf-node-no", String(i + 1).padStart(2, "0")), body);
      li.append(a);
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
    detail.append(readHead, name, badges(selected.s));
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
        for (const b of c.by) line.append(tag(D.by[b] || b, b === "script" ? "" : b));
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
    line.append(h("span", "wf-name", s.name));
    for (const b of s.by) line.append(tag(D.by[b] || b, b === "script" ? "" : b, b));
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

  function stepsEl(steps, prefix) {
    const ol = h("ol", "wf-steps");
    for (const s of steps) { const li = h("li"), step = stepEl(s); if (prefix) step.dataset.wfPath = `${prefix}--${s.key}`; li.append(step); ol.append(li); }
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

  function flowEl(t, roles) { // 워크플로우 전체(문서마다가 아니라 한 번)의 단계 한 줄 — 등록부의 flow[{stage, steps}](준비 · 구성 불러오기 · 프로젝트 구성 확정: 어느 문서의 단위문서 TASK 에도 안 듦) + 구성의 기준(base 역할) | null(없음 · 옛 서버)
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

  function overview() { // 전체 보기 — TASK 마다 한 줄: 이름 + 단계 묶음의 사슬
    const sec = h("section", "wf-sec");
    sec.id = "overview";
    sec.append(h("h2", "", "전체 보기"),
      h("p", "wf-lead", "워크플로우는 단계를 정해진 차례로 밟는 일이고, 단계는 도구를 씁니다. 스크립트가 계산하고 LLM 은 검토 · 판정만 하며, 문서는 사람이 확인(「반영」 · 「한 번에 진행」)한 뒤에만 바뀝니다. 아래에서 워크플로우나 단계 묶음을 누르면 그 과정으로 갑니다."));
    if (D.waysNote) { const p = h("p", "wf-lead wf-ways-note", D.waysNote); p.id = "waysNote"; sec.append(p); } // 진행 방식 둘(한 번에 진행 · 단계별) + 에이전트가 보이는 것 — TASK 절의 「진행 방식」 이 TASK 마다 적는다
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
      box.append(head, stepsEl(g.steps, `${t.job}--${g.id}`));
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
    box.append(stepsEl(c.steps, `common-${c.id}`));
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
    nav.replaceChildren(link("#overview", "전체 보기"), head("워크플로우", D.tasks.length), ...D.tasks.map((t) => link(`#${t.job}`, taskName(t.job), t.soon ? "wf-soon" : t.custom ? "wf-made" : "")), make,
      formsWrap,
      head("단계", stages.length), ...stages.map((c) => link(`#common-${c.id}`, c.name)),
      head("도구", tools.length), ...tools.map((c) => link(`#common-${c.id}`, c.name)));
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
  const OVER_SECS = new Set(["wfCompose", "wfForms"]); // 전체 보기와 함께 서는 절 — 주소 #wfForms 로 바로 열린다

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
  let T = null; // GET /api/tasks — {tasks, stages, pairs, blocked, base, limits, broken, warn} | null(못 읽음 — 옛 서버)
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
  const composable = () => !!T && Array.isArray(T.stages) && T.stages.length > 0 && T.stages.every((st) => st.cells && st.cells.source && st.cells.target);
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
    try { const r = await fetch("/api/tasks", { headers: { Accept: "application/json" } }); T = r.ok ? await r.json() : null; } catch { T = null; }
    if (T && typeof taskCatalogCustom === "function") taskCatalogCustom(T.tasks, { broken: !!T.broken }); // 이 페이지의 워크플로우 이름도 지금 저장소의 것으로(/api/tasks.js 와 같은 꼴 — 둘째 인자 = 저장 파일을 못 읽음)
  }
  function composeOpen(key, copy) { // "" = 새 워크플로우 · 키 = 그 워크플로우 고치기 · copy = 복제할 워크플로우(같은 배정 · 설명 · 전제 + 이름 「<이름> 사본」 의 새 폼) — 전체 보기의 「워크플로우 조립」 절로 가서 폼을 편다
    composing = null;
    if (composable()) { // 아니면 폼 대신 그 절의 안내(「조립은 서버를 다시 켠 뒤에 …」)
      const t = copy || (key ? T.tasks.find((x) => x.key === key) : null), edit = !!(t && !copy), pair = T.pairs[0] || {}, all = T.stages.map((x) => x.id);
      const a = t ? assignOf(t) || { source: [], target: [...(t.stages || [])], llm: null } : { source: all, target: all, llm: null }; // 새 워크플로우 = 고를 수 있는 칸 모두(원본 = 문서 검토 · 목적 = 넷)
      const picked = (role) => new Set(T.stages.filter((st) => cellOf(st, role).mode === "pick" && a[role].includes(st.id)).map((st) => st.id));
      composing = { key: edit ? t.key : "", name: copy ? copyName(t.name) : edit ? t.name : "", desc: t ? t.desc || "" : "", pair: t ? `${t.source}>${t.target}` : `${pair.source}>${pair.target}`,
        assign: { source: picked("source"), target: picked("target") }, llm: t ? a.llm : null, locked: edit ? lockOf(t) : "", copyOf: copy ? t.name : "", premise: t ? t.premise || "" : "", err: "", busy: false };
      composing.from = { source: [...composing.assign.source], target: [...composing.assign.target] };
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
  }
  async function composeSave() {
    const c = composing;
    if (!c || c.busy) return;
    const [source, target] = c.pair.split(">"), assign = { source: ordered(c.assign.source), target: ordered(c.assign.target) };
    if (c.llm && sameAssign(assign, c.from)) assign.llm = [...c.llm]; // 고른 단계가 연 때 그대로 — 서버가 준 llm 을 그대로 돌려준다(바뀌었으면 안 보냄: 서버가 규칙으로 다시 정한다)
    const body = { name: c.name, desc: c.desc, premise: c.premise, ...(c.locked ? {} : { assign }), ...(c.key ? {} : { source, target }) }; // 합집합 stages 는 안 보낸다 · 쓰는 중이면 assign 도 안 보낸다(이름 · 설명 · 전제만)
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
    if (!can) composing = null;
    if (!T) { sec.append(off()); return; }
    sec.append(h("p", "wf-lead", "원본 문서 · 목적 문서마다 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를 골라 이름을 붙이면 새 워크플로우가 됩니다 — 문서마다 고른 단계가 그 문서의 단위문서 TASK 입니다. "
      + "시작 화면의 카드 · 이 지도 · 대시보드에 서고, 고른 단계만 진행합니다. 단계의 차례는 바뀌지 않습니다."));
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
      li.append(link(`#${t.key}`, t.name, "wf-over-name"), h("span", "wf-muted", `${t.sourceName} → ${t.targetName}`), chips);
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
    } else sec.append(composeForm());
    const no = h("details", "wf-blocked"), ul = h("ul");
    no.append(h("summary", "", "아직 조립할 수 없는 것"));
    for (const b of T.blocked || []) { const li = h("li"); li.append(h("b", "", b.name), document.createTextNode(` — ${b.why}`)); ul.append(li); }
    no.append(ul);
    sec.append(no);
  }
  function slotField(c, field) { // 조립 폼의 「문서 칸」 — 워크플로우 절의 그 줄과 같은 것(고치기: 그 워크플로우의 설정을 바로 바꾼다 · 정의와 따로라 지문이 안 바뀐다 · 새로 만들 때는 만든 뒤에)
    const t = c.key && D ? D.tasks.find((x) => x.job === c.key) : null, box = h("div", "wf-compose-slots");
    if (t) box.append(slotEl(t));
    else box.append(h("span", "wf-muted", "목적 문서 칸의 양식(없음 · 기본값 · 고정)은 만든 뒤 그 워크플로우 절의 「문서 칸」 에서 겁니다 — 정의와 따로 두는 설정이라 하던 작업이 있어도 바꿀 수 있습니다"));
    return field("문서 칸", box);
  }
  function composeForm() {
    const c = composing, form = h("form", "wf-form"), field = (label, control, note) => { const f = h("label", "wf-field"); f.append(h("span", "wf-field-name", label), control); if (note) f.append(h("span", "wf-muted", note)); return f; };
    form.addEventListener("submit", (e) => { e.preventDefault(); composeSave(); });
    const name = h("input"), desc = h("input"), pair = h("select"), premise = h("textarea");
    name.name = "name"; name.required = true; name.maxLength = limit("name", 40); name.value = c.name; name.placeholder = "예: 연차보고서 구성만 맞추기";
    name.addEventListener("input", () => { c.name = name.value; });
    desc.name = "desc"; desc.maxLength = limit("desc", 200); desc.value = c.desc; desc.placeholder = "시작 화면의 카드에 보이는 한 줄 설명(비워도 됩니다)";
    desc.addEventListener("input", () => { c.desc = desc.value; });
    for (const p of T.pairs) pair.append(new Option(p.name, `${p.source}>${p.target}`));
    pair.name = "pair"; pair.value = c.pair; pair.disabled = !!c.key; // 만든 뒤에는 문서 쌍을 못 고친다(그 워크플로우로 하던 작업의 문서 역할이 달라진다)
    pair.addEventListener("change", () => { c.pair = pair.value; sync(); });
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
          box.addEventListener("change", () => { if (box.checked) c.assign[role].add(st.id); else c.assign[role].delete(st.id); sync(); });
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
    cancel.type = "button";
    cancel.addEventListener("click", () => { composing = null; composeDraw(); });
    acts.append(save, cancel);
    if (c.err) { const e = h("p", "wf-err", c.err); e.setAttribute("role", "alert"); acts.append(e); }
    form.append(h("h3", "", c.key ? `「${c.name}」 고치기` : c.copyOf ? `새 워크플로우 — 「${c.copyOf}」 복제` : "새 워크플로우"), field("이름", name), field("한 줄 설명", desc),
      field("문서 쌍(원본 → 목적)", pair, c.key ? "만든 뒤에는 고칠 수 없습니다" : T.pairs.length > 1 ? "" : "지금 조립할 수 있는 쌍은 이것 하나입니다 — 까닭은 아래 「아직 조립할 수 없는 것」"),
      ...(lock ? [lock] : []), pick, slotField(c, field), field("전제(선택)", premise), acts);
    return form;
  }

  // ---- 저장한 양식 · 문서 칸(spec_워크플로우 ② §18-9 「양식」 · 고친 규칙 ② §18-12 ⑧ — 2026-11-20 사용자 "템플릿은 워크플로우 설정에서 고정 또는 default 값을로" → 물어서 받은 답 「양식 파일」)
  // 저장한 양식 = 워크플로우의 목적 문서 칸에 넣을 양식 파일(서버 전체 — GET /api/form-files · 파일은 올린 그대로 · 고치려면 새로 올린다).
  // 문서 칸 = 워크플로우 절의 「받는 문서」 아래 한 줄 — 역할마다(원본 → 목적) · 목적 문서 칸에만 양식을 건다: 「양식: 없음 · 기본값 · 고정」 + 저장한 양식 고르기(PUT /api/workflow-slots/{job}). 붙박이 · 조립한 것 모두.
  // 걸 수 있는지(워크플로우 · 형식 · 문서 종류)는 서버가 정한다(jobs[{job, kind, formats}] · noForm{job: 까닭}) — 화면은 그 목록대로 고를 것을 추리고, 거절 글은 서버의 것 그대로. 화면 말: 「저장한 양식」 · 「양식으로 저장」 · 「양식: 없음 · 기본값 · 고정」(「템플릿」 은 쓰지 않는다).
  let FF = null, ffErr = ""; // GET /api/form-files | null(못 읽음 — 옛 서버면 이 절 · 줄이 서지 않는다)
  const FF_MODE = { "": "없음", default: "기본값", fixed: "고정" };
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
  function ffRedraw() { // 양식 · 설정이 바뀐 뒤 — 저장한 양식 절과 모든 「문서 칸」 줄을 새로
    formsDraw();
    for (const box of document.querySelectorAll(".wf-slots[data-job]")) { const t = D && D.tasks.find((x) => x.job === box.dataset.job); if (t) box.replaceWith(slotEl(t)); }
  }
  function slotEl(t) { // 「문서 칸」 — 역할마다 한 줄(원본 → 목적): 원본 문서 = 실행마다 사람이 넣음 · 목적 문서 = 양식 설정(없음 · 기본값 · 고정 + 저장한 양식)
    const box = h("div", "wf-slots"), roles = rolesSorted(t.roles), j = ffJob(t.job), cur = FF && FF.slots && FF.slots[t.job] && FF.slots[t.job].target;
    box.dataset.job = t.job;
    const ul = h("ul", "wf-slot-list");
    for (const r of roles.length ? roles : [{ role: "target", title: "목적 문서", name: "" }]) {
      const li = h("li", "wf-slot"), head = h("span", "wf-slot-role");
      li.dataset.role = r.role;
      head.append(h("b", "", roleTitle(r)), document.createTextNode(r.name ? ` — ${r.name}` : ""), ...(r.many ? [h("span", "wf-muted", "(여럿)")] : []));
      li.append(head);
      if (r.role !== "target") li.append(h("span", "wf-muted", "실행마다 사람이 넣습니다(양식은 목적 문서 칸에만 겁니다)"));
      else if (!FF) li.append(h("span", "wf-muted", ffErr ? `저장한 양식을 읽지 못했습니다: ${ffErr}` : "양식 설정은 서버를 다시 켠 뒤에 쓸 수 있습니다"));
      else if (!j) li.append(h("span", "wf-muted", (FF.noForm || {})[t.job] || (t.soon ? "준비 중인 워크플로우라 양식을 걸지 않습니다" : "이 워크플로우는 양식을 걸지 않습니다")));
      else li.append(slotPick(t, j, cur));
      ul.append(li);
    }
    box.append(ul);
    return box;
  }
  function slotPick(t, j, cur) { // 목적 문서 칸의 양식 설정 — [없음 | 기본값 | 고정] [저장한 양식 ▾] + 저장한 날 · 거절 글
    const wrap = h("span", "wf-slot-pick"), mode = h("select"), form = h("select"), note = h("span", "wf-muted"), err = h("span", "wf-slot-err"); // 줄 아래 거절 글(.wf-err 는 조립 폼의 저장 거절 글 — 섞지 않는다)
    const fits = (FF.files || []).filter((f) => ffFits(f, j)), now = cur ? (FF.files || []).find((f) => f.id === cur.file) : null;
    mode.name = `slot-mode-${t.job}`;
    mode.setAttribute("aria-label", `${taskName(t.job)} — 목적 문서 칸의 양식`);
    for (const [v, label] of Object.entries(FF_MODE)) mode.append(new Option(`양식: ${label}`, v));
    mode.value = cur ? cur.mode : "";
    form.name = `slot-form-${t.job}`;
    form.setAttribute("aria-label", `${taskName(t.job)} — 목적 문서 칸에 넣을 저장한 양식`);
    for (const f of fits) form.append(new Option(`${f.name}${ffDate(f.at) ? ` (${ffDate(f.at)})` : ""}`, f.id));
    if (now && !fits.includes(now)) form.append(new Option(`${now.name} — 지금은 걸 수 없음`, now.id));
    if (!form.options.length) form.append(new Option("걸 수 있는 양식이 없음", ""));
    form.value = now ? now.id : (fits[0] || {}).id || "";
    form.disabled = !mode.value || !fits.length;
    const need = [j.formats.join(" · "), j.kind ? FF_KIND[j.kind] || j.kind : ""].filter(Boolean).join(" · ");
    const sync = () => {
      note.textContent = !fits.length ? `걸 수 있는 양식이 없습니다 — 아래 「저장한 양식」 에서 ${need} 양식을 올리세요`
        : !mode.value ? "시작할 때 목적 문서를 사람이 넣습니다"
          : mode.value === "fixed" ? "늘 이 양식으로 시작합니다 — 시작의 목적 칸에 다른 파일을 넣을 수 없습니다" : "시작할 때 이 양식이 미리 들어가 있고, 다른 파일로 바꿀 수 있습니다";
    };
    const send = async () => {
      if (mode.value && !form.value) { sync(); return; }
      mode.disabled = form.disabled = true;
      err.textContent = "";
      const r = await ffSend(`/api/workflow-slots/${encodeURIComponent(t.job)}`, { method: "PUT", headers: JSON_H, body: JSON.stringify({ target: mode.value ? { file: form.value, mode: mode.value } : null }) });
      if (!r.ok) { err.textContent = `바꾸지 못했습니다 — ${r.msg}`; mode.disabled = false; form.disabled = !mode.value || !fits.length; return; }
      await formsLoad();
      ffRedraw();
    };
    mode.addEventListener("change", () => { form.disabled = !mode.value || !fits.length; sync(); send(); });
    form.addEventListener("change", send);
    mode.disabled = !fits.length && !cur;
    sync();
    err.setAttribute("role", "alert");
    wrap.append(mode, form, note, err);
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
    sec.append(h("p", "wf-lead", "워크플로우 절의 「문서 칸」 에서 목적 문서 칸에 양식을 겁니다 — 기본값(시작할 때 미리 들어가 있고 다른 파일로 바꿀 수 있음) · 고정(늘 그 양식). "
      + "양식 파일은 올린 그대로 두고 고치지 않습니다(고치려면 새로 올립니다). 이미 하던 작업의 문서는 설정을 바꿔도 그대로입니다."));
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
    main.replaceChildren(diagram, overview(), composeSec(), formsSec(), ...D.tasks.map(taskSec), ...D.common.map(commonSec));
    composeDraw();
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
