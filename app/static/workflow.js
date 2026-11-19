// TASK 워크플로우 페이지(spec_워크플로우 ② §3·§7) — GET /api/workflow 등록부를 다이어그램(기본)·목록으로 그린다. 읽기만 한다(실행·진행 상태 없음).
// TASK 이름·한 줄 설명 = TASK_CATALOG · 이관·취합의 「N단계 이름」 = TASK_STAGE_META(task_catalog.js — 이 파일보다 먼저 읽힌다: 원본 하나).
// 절의 id: 전체 보기 `overview` · TASK `<job>`(묶음 `<job>--<묶음 id>`) · 단계 · 도구 `common-<id>` — 주소의 # 로 바로 열린다.
// 화면 말(2026-11-19 사용자 "모듈이라고 하지 말고 공통 모듈을 도구라고 하자"): 등록부의 COMMON = **「도구」**(전의 「공통 모듈」) · 그 가운데 kind "stage" = **「단계」**(TASK 가 조립하는 일반 단계) · 코드 파일(app/<이름>.py) = 「코드」.
// TASK 조립(spec_워크플로우 ② §14 — 같은 날 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」): 전체 보기 아래 「TASK 조립」 절에서 단계를 골라 TASK 를 만든다 — 저장은 서버(/api/tasks), 읽기 전용이던 이 페이지에서 고치는 것은 그것 하나다.
// 문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 같은 날 사용자 "각문서에 대한걸 단위문서 task 라고 하고 전체를 워크플로우라"): TASK 절의 「문서마다 단위문서 TASK」 표
// (등록부의 roles — 원본 → 목적 · 단계의 on) · 단계 세부의 「하는 문서」 · 조립 폼의 문서 역할 × 단계 표(GET /api/tasks 의 stages[].cells · 저장은 assign). 여러 문서 쪽은 「원본 문서」(「취합 대상」 은 쓰지 않는다).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const CAT = typeof TASK_CATALOG === "undefined" ? {} : TASK_CATALOG, META = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META;
  const MODEL = { "claude-fable-5-2": "Fable 5.2", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5" }; // 에이전트 설정 페이지(agents.js MODEL)와 같은 이름
  const SOURCE = { user: "에이전트 설정에서 정함", pin: "이 에이전트에 고정", force: "서버 전체 설정", code: "코드가 정함", default: "서버 기본" };
  const CHANGE = { none: "안 바뀜", doc: "바뀜", store: "안 바뀜 — 결과만 저장" }; // 펼친 세부의 「문서」 줄
  const taskName = (job) => (CAT[job] || {}).name || ((D && D.tasks.find((t) => t.job === job)) || {}).name || job; // 조립한 TASK 의 이름은 등록부(서버 저장소)에도 있다
  const stageLabel = (g) => (g.meta && META[g.meta] ? { no: META[g.meta].no, name: META[g.meta].name } : { no: g.no || "", name: g.name });
  // 문서 역할 — 등록부 roles[{role, name, kind, many, unit[{stage, steps[key…]}]}] · 단계의 on(source 원본 · target 목적 · both 문서마다 · pair 원본 → 목적 · "" = 문서 하나인 TASK · 도구의 단계)
  const ROLES = ["source", "target"], ROLE = { source: "원본 문서", target: "목적 문서" };
  const roleOf = (roles, role) => (roles || []).find((r) => r.role === role) || null;
  const rolesSorted = (roles) => [...(roles || [])].sort((a, b) => ROLES.indexOf(a.role) - ROLES.indexOf(b.role)); // 차례 원본 → 목적
  function onText(on, roles) { // 단계의 「하는 문서」 한 줄 — on 이 비었거나 문서 역할을 모르면 ""(줄 없음 · 옛 서버)
    const src = roleOf(roles, "source"), dst = roleOf(roles, "target"), many = !!(src && src.many);
    if (!on || !dst || (on !== "target" && !src)) return "";
    if (on === "source") return `원본 문서 — ${src.name}` + (many ? "(문서마다)" : "");
    if (on === "target") return `목적 문서 — ${dst.name}`;
    if (on === "both") return many ? `목적 문서와 원본 문서마다 — ${dst.name} · ${src.name}` : `두 문서 — ${src.name} · ${dst.name}`;
    if (on === "pair") return `${many ? "원본 문서마다" : "원본"} → 목적 — ${src.name} → ${dst.name}`;
    return "";
  }
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
    heading.append(h("p", "wf-eyebrow", item.job ? "TASK / 순서 살펴보기" : item.kind === "stage" ? "단계 / 순서 살펴보기" : "도구 / 순서 살펴보기"), h("h2", "", title));
    head.append(heading, link("#overview", "전체 흐름 보기 ↗", "wf-back"));
    const lead = h("p", "wf-lead", item.job ? (CAT[item.job] || {}).desc : item.does);
    const context = h("details", "wf-context"), info = h("dl", "wf-io"), docs = item.job ? docsEl(item) : null; // 문서마다 단위문서 TASK — 받는 문서 · 산출물 줄 아래(목록 보기의 TASK 절과 같은 표)
    context.append(h("summary", "", item.job ? (docs ? "입력·산출물 · 전제 · 문서마다 단위문서 TASK 보기" : "입력·산출물과 전제 보기") : "여는 곳 · 쓰는 TASK 보기"));
    if (item.job) {
      row(info, "받는 문서", item.inputs);
      row(info, "산출물", item.output);
      if (item.note) row(info, "알아 둘 것", item.note);
      if (item.prompt) row(info, "전제", h("code", "", item.prompt));
    } else {
      row(info, "여는 곳", item.where);
      const related = h("div", "wf-links");
      for (const job of item.usedBy) related.append(link(`#${job}`, taskName(job), "wf-chip"));
      row(info, item.kind === "stage" ? "조립한 TASK" : "쓰는 TASK", item.usedBy.length ? related : item.kind === "stage" ? "아직 이 단계를 조립한 TASK 가 없습니다." : "어느 TASK의 문서에서나 엽니다.");
    }
    context.append(info);
    if (docs) context.append(docs);
    diagram.replaceChildren(head, lead, context);
    if (item.job && (item.entry || []).length) { // 시작 점검(② §10) — 접어 두고, 펴면 때마다 묶음이 열린 채로
      const ent = h("details", "wf-context wf-entry-context"), note = h("p", "wf-entry-doc", "이 TASK 의 세부(시작 점검 · 단계마다 조건)는 TASK 문서 ");
      ent.append(h("summary", "", `시작 점검 — 시작할 때 저절로 확인하는 것 ${entryCount(item)}가지 보기`));
      note.append(h("code", "", item.doc), document.createTextNode(" 에도 같은 글로 있습니다."));
      ent.append(note, entryEl(item, true));
      diagram.append(ent);
    }
    if (!selected) {
      const empty = h("div", "wf-empty");
      empty.append(tag("준비 중", "soft"), h("h3", "", "아직 등록된 단계가 없습니다"), h("p", "", "이 TASK의 과정이 준비되면 순서대로 확인할 수 있습니다."), link("#overview", "다른 TASK 살펴보기", "wf-chip"));
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
      nodes.setAttribute("aria-label", "TASK 단계 묶음과 단계");
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
    const onDoc = item.job ? onText(selected.s.on, item.roles) : ""; // 이 단계가 하는 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 문서 하나인 TASK · 도구의 단계는 없음
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
    const technical = stepEl(selected.s, item.roles).querySelector(".wf-more");
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

  function stepEl(s, roles) { // 단계 한 줄 — 이름 · 누가 · 문서 바뀜 · 하는 일은 늘 보이고, 누르면 세부(조건 · 하는 문서 · 나오는 것 · 공통 모듈 · 에이전트 · 모듈 · 사양 자리). roles = 그 TASK 의 문서 역할(도구의 단계는 없음)
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
    const more = h("dl", "wf-more"), onDoc = onText(s.on, roles);
    if (onDoc) row(more, "하는 문서", onDoc); // 이 단계가 하는 문서(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 원본 · 목적 · 두 문서 · 원본 → 목적
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

  function stepsEl(steps, prefix, roles) {
    const ol = h("ol", "wf-steps");
    for (const s of steps) { const li = h("li"), step = stepEl(s, roles); if (prefix) step.dataset.wfPath = `${prefix}--${s.key}`; li.append(step); ol.append(li); }
    return ol;
  }

  function docsEl(t) { // 문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) — 열 = 문서 역할(원본 → 목적) · 행 = 단계 묶음 · 칸 = 그 문서에 하는 단계(누르면 그 단계로) | null(옛 서버 — roles 없음)
    const roles = rolesSorted(t.roles);
    if (!roles.length) return null;
    const box = h("div", "wf-docs-box"), head = h("h3", "wf-docs-head", "문서마다 단위문서 TASK");
    box.append(head);
    if (roles.length === 1) { // 문서 하나인 TASK — 그 TASK 가 곧 그 문서(목적 문서)의 단위문서 TASK
      const p = h("p", "wf-docs-one"), r = roles[0];
      p.append(h("b", "", "문서 하나"), document.createTextNode(" — 이 워크플로우가 그 문서의 단위문서 TASK 입니다"));
      if (r.name) p.append(h("span", "wf-muted", ` · ${ROLE[r.role] || r.role} — ${r.name}`));
      box.append(p);
      return box;
    }
    const src = roleOf(roles, "source"), many = !!(src && src.many), pairs = t.stages.some((g) => g.steps.some((s) => s.on === "pair"));
    head.append(h("span", "wf-muted", "문서마다 차례로 하는 단계" + (pairs ? " — 「← 원본 문서」 는 원본 문서의 내용을 받는 단계" : "") + (many ? " · 원본 문서가 여럿이면 원본 문서마다 되풀이합니다" : "")));
    const table = h("table", "wf-docs"), thead = h("thead"), hr = h("tr"), tbody = h("tbody"), th0 = h("th", "", "단계");
    table.setAttribute("aria-label", "문서마다 단위문서 TASK");
    th0.scope = "col";
    hr.append(th0);
    const label = (r) => `${ROLE[r.role] || r.role} — ${r.name}` + (r.many ? "(문서마다)" : ""); // 칸의 문서 이름표(좁은 폭에서 칸 위에 — 표 머리 대신)
    for (const r of roles) {
      const th = h("th");
      th.scope = "col";
      th.dataset.role = r.role;
      th.append(h("b", "", ROLE[r.role] || r.role), document.createTextNode(` — ${r.name}`));
      if (r.many) th.append(h("span", "wf-muted", "(문서마다)"));
      hr.append(th);
    }
    thead.append(hr);
    for (const g of t.stages) {
      const L = stageLabel(g), tr = h("tr"), th = h("th"), a = link(`#${t.job}--${g.id}`, "", "wf-docs-stage");
      tr.dataset.stage = g.id;
      th.scope = "row";
      if (L.no) a.append(h("b", "", L.no), document.createTextNode(" "));
      a.append(document.createTextNode(L.name));
      th.append(a);
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
            if (pair && !run) { const from = h("span", "wf-docs-from", many ? "← 원본 문서마다" : "← 원본 문서"); from.title = `원본 문서(${src ? src.name : ""})의 내용을 이 문서가 받는 단계`; li.append(from); }
            run = pair;
            const step = link(`#${t.job}--${g.id}--${s.key}`, s.name, "wf-docs-step" + (s.optional ? " wf-optional" : "") + (s.soon ? " wf-soon" : ""));
            if (s.soon || s.optional) step.title = s.soon ? "준비 중인 단계" : "선택 단계";
            li.append(step);
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
    box.append(table);
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
      h("p", "wf-lead", "TASK 는 단계를 정해진 차례로 밟는 일이고, 단계는 도구를 씁니다. 스크립트가 계산하고 LLM 은 검토 · 판정만 하며, 문서는 사람이 확인(「반영」 · 「한 번에 진행」)한 뒤에만 바뀝니다. 아래에서 TASK 나 단계 묶음을 누르면 그 과정으로 갑니다."));
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
    for (const [label, stage] of [["단계", true], ["도구", false]]) { // 단계(TASK 가 조립하는 일반 단계) · 도구(여러 TASK 가 쓰는 과정)
      const commons = h("div", "wf-commons");
      commons.dataset.kind = stage ? "stage" : "tool";
      commons.append(h("span", "wf-muted", label));
      for (const c of D.common) if ((c.kind === "stage") === stage) commons.append(link(`#common-${c.id}`, c.name, "wf-chip"));
      sec.append(commons);
    }
    return sec;
  }

  function taskSec(t) { // TASK 절 — 이름 · 한 줄 설명 · 받는 문서 → 산출물 · 알아 둘 것 → 단계 묶음(세로 차례)
    const c = CAT[t.job] || {}, sec = h("section", "wf-sec wf-task"), h2 = h("h2");
    sec.id = t.job;
    h2.append(h("span", "wf-kind", "TASK"), document.createTextNode(taskName(t.job)));
    if (t.soon) h2.append(tag("준비 중", "soft"));
    sec.append(h2);
    if (t.custom) h2.append(tag("조립한 TASK", "soft"));
    if (c.desc || t.desc) sec.append(h("p", "wf-lead", t.desc || c.desc));
    const io = h("dl", "wf-io");
    if (t.custom) { // 화면에서 조립한 TASK(② §14) — 고치기 · 지우기는 「TASK 조립」 절에서
      const edit = h("button", "btn sm", "고치기");
      edit.type = "button";
      edit.dataset.wfCompose = t.job;
      edit.addEventListener("click", () => composeOpen(t.job));
      row(io, "조립", [document.createTextNode("화면에서 단계를 골라 만든 TASK 입니다 — "), edit]);
      row(io, "전제", t.premise ? "조립할 때 적은 글(이 TASK 의 LLM 호출이 읽습니다)" : `틀이 같은 TASK(${taskName(t.base)})의 전제를 씁니다`);
    }
    row(io, "받는 문서", t.inputs);
    row(io, "산출물", t.output);
    if (t.note) row(io, "알아 둘 것", t.note);
    if (t.prompt) row(io, "전제", [h("code", "", t.prompt), document.createTextNode(" — 이 TASK 의 전제 · 기준을 적은 할 일 프롬프트(에이전트가 먼저 읽는 글)")]);
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
      head.append(h("span", "wf-muted", `시작할 때 저절로 확인하는 것 ${entryCount(t)}가지 · TASK 문서`), h("code", "", t.doc));
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
      box.append(head, stepsEl(g.steps, `${t.job}--${g.id}`, t.roles));
      li.append(h("span", "wf-stage-no" + (L.no ? "" : " wf-plain"), L.no || String(i + 1)), box);
      ol.append(li);
    });
    sec.append(ol);
    return sec;
  }

  function commonSec(c) { // 공통 모듈 절 — 하는 일 · 여는 곳 · 쓰는 TASK + 단계
    const sec = h("section", "wf-sec wf-common"), h2 = h("h2"), io = h("dl", "wf-io"), box = h("div", "wf-box");
    sec.id = `common-${c.id}`;
    const stage = c.kind === "stage", used = stage ? "조립한 TASK" : "쓰는 TASK"; // 단계 모듈 = TASK 가 조립하는 일반 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리 — ② §13)
    h2.append(h("span", "wf-kind", stage ? "단계" : "도구"), document.createTextNode(c.name));
    sec.append(h2, h("p", "wf-lead", c.does));
    row(io, "여는 곳", c.where);
    if (c.usedBy.length) { const links = h("div", "wf-links"); for (const job of c.usedBy) links.append(link(`#${job}`, taskName(job), "wf-chip")); row(io, used, links); }
    else row(io, used, stage ? "아직 이 단계를 조립한 TASK 가 없습니다" : "어느 TASK 의 문서에서나 엽니다(단계에 묶이지 않음)");
    box.append(stepsEl(c.steps, `common-${c.id}`));
    box.style.marginTop = "10px";
    sec.append(io, box);
    return sec;
  }

  function navDraw() {
    const nav = $("wfNav");
    const make = h("button", "btn sm wf-nav-make", "＋ TASK 조립"); // 단계를 골라 새 TASK 를 만든다(② §14) — 전체 보기 아래 「TASK 조립」 절의 폼으로
    make.type = "button";
    make.dataset.wfCompose = "new";
    make.title = "원본 문서 · 목적 문서마다 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를 골라 새 TASK 를 만듭니다";
    make.addEventListener("click", () => composeOpen(""));
    nav.replaceChildren(link("#overview", "전체 보기"), h("h2", "", "TASK"), ...D.tasks.map((t) => link(`#${t.job}`, taskName(t.job), t.soon ? "wf-soon" : t.custom ? "wf-made" : "")), make,
      h("h2", "", "단계"), ...D.common.filter((c) => c.kind === "stage").map((c) => link(`#common-${c.id}`, c.name)),
      h("h2", "", "도구"), ...D.common.filter((c) => c.kind !== "stage").map((c) => link(`#common-${c.id}`, c.name)));
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
    if (id !== "overview" && !routes.has(id)) id = "overview";
    const oldOwner = (routes.get(current) || {}).flow?.id, route = routes.get(id), main = $("wfMain"), diagram = $("wfDiagram");
    const focusKey = document.activeElement?.dataset.wfFocus;
    current = id;
    for (const sec of main.querySelectorAll(".wf-sec")) sec.hidden = view === "diagram" && (id !== "overview" || (sec.id !== "overview" && sec.id !== "wfCompose")); // 「TASK 조립」 절은 전체 보기와 함께
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
    navSync();
  }

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

  // ---- TASK 조립(spec_워크플로우 ② §14) — 단계를 골라 새 TASK 를 만든다 · 조립한 TASK 를 고치고 지운다. 저장소 = 서버(GET·POST /api/tasks · PUT·DELETE /api/tasks/{key}).
  // 지금 조립할 수 있는 틀은 이관형(원본 문서 하나 → 목적 문서 하나)이고 문서 쌍은 서버가 주는 것(pairs)뿐이다 — 아직 안 되는 틀은 까닭과 함께 보인다(blocked). 단계의 차례는 일반 단계의 차례로 고정(고르는 것은 쓰느냐뿐).
  // 고르는 곳 = 문서 역할 × 단계 표(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」): 칸 = 서버의 stages[].cells[역할] — pick(체크) · follow(다른 역할이 그 단계를 고르면 따라오는 글) · no(고를 수 없음 — 까닭).
  // 저장 = assign {source, target}(일반 차례) + 두 문서의 합집합 stages(옛 서버가 읽는 꼴 — 서버는 assign 이 먼저).
  let T = null; // GET /api/tasks — {tasks, stages, pairs, blocked, base, limits} | null(못 읽음 — 옛 서버)
  let composing = null; // 펴 둔 폼 {key("" = 새로), name, desc, pair, assign: {source: Set, target: Set}, premise, err, busy}
  const cellOf = (st, role) => (st.cells && st.cells[role]) || { mode: role === "target" || st.id === "stage_review" ? "pick" : "no", text: "" }; // 옛 서버(cells 없음) — 원본은 문서 검토만 고른다
  const stageName = (id) => ((T && T.stages.find((x) => x.id === id)) || {}).name || id;
  const ordered = (ids) => { const on = new Set(ids); return T.stages.map((x) => x.id).filter((id) => on.has(id)); }; // 일반 단계의 차례로
  function assignOf(t) { // 조립한 TASK 의 문서마다 고른 단계 — 옛 줄(assign 없음)은 원본 = 문서 검토가 있으면 그것 · 목적 = 고른 단계 전부(전의 동작 그대로)
    if (t.assign) return { source: [...(t.assign.source || [])], target: [...(t.assign.target || [])] };
    return { source: (t.stages || []).includes("stage_review") ? ["stage_review"] : [], target: [...(t.stages || [])] };
  }
  function pairNames(value) { // 문서 쌍("plan>report") → {source, target} 문서 이름 — 서버의 쌍 이름(「사업계획서 → 연차보고서」)에서
    const p = T.pairs.find((x) => `${x.source}>${x.target}` === value) || T.pairs[0] || {};
    if (p.sourceName && p.targetName) return { source: p.sourceName, target: p.targetName };
    const [source, target] = String(p.name || "").split(" → ");
    return { source: source || "", target: target || "" };
  }
  async function tasksLoad() {
    try { const r = await fetch("/api/tasks", { headers: { Accept: "application/json" } }); T = r.ok ? await r.json() : null; } catch { T = null; }
    if (T && typeof taskCatalogCustom === "function") taskCatalogCustom(T.tasks); // 이 페이지의 TASK 이름도 지금 저장소의 것으로
  }
  function composeOpen(key) { // "" = 새 TASK · 키 = 그 TASK 고치기 — 전체 보기의 「TASK 조립」 절로 가서 폼을 편다
    if (!T) return;
    const t = key ? T.tasks.find((x) => x.key === key) : null, pair = T.pairs[0] || {}, all = T.stages.map((x) => x.id);
    const a = t ? assignOf(t) : { source: all, target: all }; // 새 TASK = 고를 수 있는 칸 모두(원본 = 문서 검토 · 목적 = 넷)
    const picked = (role) => new Set(T.stages.filter((st) => cellOf(st, role).mode === "pick" && a[role].includes(st.id)).map((st) => st.id));
    composing = { key: t ? key : "", name: t ? t.name : "", desc: t ? t.desc : "", pair: t ? `${t.source}>${t.target}` : `${pair.source}>${pair.target}`,
      assign: { source: picked("source"), target: picked("target") }, premise: t ? t.premise : "", err: "", busy: false };
    if (view === "diagram") navigate("#overview"); else go("#overview");
    composeDraw();
    const box = $("wfCompose"), first = box && box.querySelector("input[name=name]");
    if (box) box.scrollIntoView({ block: "start" });
    if (first) first.focus({ preventScroll: true });
  }
  async function composeSave() {
    const c = composing;
    if (!c || c.busy) return;
    const [source, target] = c.pair.split(">"), assign = { source: ordered(c.assign.source), target: ordered(c.assign.target) };
    const body = { name: c.name, desc: c.desc, assign, stages: ordered([...assign.source, ...assign.target]), premise: c.premise, ...(c.key ? {} : { source, target }) }; // stages = 두 문서의 합집합(옛 꼴)
    c.busy = true; c.err = "";
    composeDraw();
    let got = null;
    try {
      const r = await fetch(c.key ? `/api/tasks/${encodeURIComponent(c.key)}` : "/api/tasks", { method: c.key ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      got = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(got.detail || `HTTP ${r.status}`);
    } catch (e) { c.busy = false; c.err = e.message; composeDraw(); return; }
    composing = null;
    await load(); // 등록부 · 저장소를 다시 읽어 목차 · 절을 새로
    navigate(`#${got.task.key}`);
  }
  async function composeDelete(t) {
    if (!confirm(`조립한 TASK 「${t.name}」 을 지울까요?\n\n단계 · 도구는 그대로이고 이 TASK(이름 · 고른 단계 · 전제)만 지웁니다. 되돌릴 수 없습니다.`)) return;
    let msg = "";
    try { const r = await fetch(`/api/tasks/${encodeURIComponent(t.key)}`, { method: "DELETE" }); if (!r.ok) msg = ((await r.json().catch(() => ({}))).detail) || `HTTP ${r.status}`; }
    catch (e) { msg = e.message; }
    if (msg) { alert(`지우지 못했습니다 — ${msg}`); return; }
    if (composing && composing.key === t.key) composing = null;
    await load();
    navigate("#overview");
  }
  function composeSec() { // 「TASK 조립」 절 — 전체 보기 아래(다이어그램 · 목록 어느 보기에서나 전체 보기와 함께 보인다)
    const sec = h("section", "wf-sec wf-compose");
    sec.id = "wfCompose";
    return sec;
  }
  function composeDraw() {
    const sec = $("wfCompose");
    if (!sec) return;
    const h2 = h("h2");
    h2.append(h("span", "wf-kind", "TASK 조립"), document.createTextNode("단계를 골라 새 TASK 만들기"));
    sec.replaceChildren(h2);
    if (!T) { sec.append(h("p", "wf-lead", "TASK 조립은 서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능).")); return; }
    sec.append(h("p", "wf-lead", "원본 문서 · 목적 문서마다 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를 골라 이름을 붙이면 새 TASK 가 됩니다 — 문서마다 고른 단계가 그 문서의 단위문서 TASK 입니다. "
      + "시작 화면의 TASK 카드 · 이 지도 · 대시보드에 서고, 고른 단계만 진행합니다. 단계의 차례는 바뀌지 않습니다."));
    const list = h("ul", "wf-made-list");
    for (const t of T.tasks) {
      const li = h("li"), chips = h("span", "wf-links"), edit = h("button", "btn sm", "고치기"), del = h("button", "btn sm", "지우기"), a = assignOf(t);
      li.dataset.task = t.key;
      for (const role of ROLES) { // 문서마다 고른 단계 — 「원본: 문서 검토 · 목적: 문서 검토 · 구성 맞추기 …」
        const grp = h("span", "wf-made-role"), ids = ordered(a[role]);
        grp.dataset.role = role;
        grp.append(h("span", "wf-muted", role === "source" ? "원본:" : "목적:"));
        if (!ids.length) grp.append(h("span", "wf-muted", "—"));
        for (const id of ids) grp.append(h("span", "wf-chip", stageName(id)));
        chips.append(grp);
      }
      edit.type = del.type = "button";
      edit.addEventListener("click", () => composeOpen(t.key));
      del.disabled = t.inUse > 0;
      del.title = t.inUse ? `이 TASK 로 하던 작업이 ${t.inUse}개 있어 지울 수 없습니다 — 그 작업의 TASK 를 바꾸거나 작업을 지운 뒤에` : "이 TASK 를 지웁니다(단계 · 도구는 그대로)";
      del.addEventListener("click", () => composeDelete(t));
      li.append(link(`#${t.key}`, t.name, "wf-over-name"), h("span", "wf-muted", `${t.sourceName} → ${t.targetName}`), chips, edit, del);
      list.append(li);
    }
    if (T.tasks.length) sec.append(list);
    if (!composing) {
      const make = h("button", "btn primary", "새 TASK 조립");
      make.type = "button";
      make.dataset.wfCompose = "open";
      make.addEventListener("click", () => composeOpen(""));
      sec.append(make);
    } else sec.append(composeForm());
    const no = h("details", "wf-blocked"), ul = h("ul");
    no.append(h("summary", "", "아직 조립할 수 없는 것"));
    for (const b of T.blocked) { const li = h("li"); li.append(h("b", "", b.name), document.createTextNode(` — ${b.why}`)); ul.append(li); }
    no.append(ul);
    sec.append(no);
  }
  function composeForm() {
    const c = composing, form = h("form", "wf-form"), field = (label, control, note) => { const f = h("label", "wf-field"); f.append(h("span", "wf-field-name", label), control); if (note) f.append(h("span", "wf-muted", note)); return f; };
    form.addEventListener("submit", (e) => { e.preventDefault(); composeSave(); });
    const name = h("input"), desc = h("input"), pair = h("select"), premise = h("textarea");
    name.name = "name"; name.required = true; name.maxLength = T.limits.name; name.value = c.name; name.placeholder = "예: 연차보고서 구성만 맞추기";
    name.addEventListener("input", () => { c.name = name.value; });
    desc.name = "desc"; desc.maxLength = T.limits.desc; desc.value = c.desc; desc.placeholder = "TASK 카드에 보이는 한 줄 설명(비워도 됩니다)";
    desc.addEventListener("input", () => { c.desc = desc.value; });
    for (const p of T.pairs) pair.append(new Option(p.name, `${p.source}>${p.target}`));
    pair.name = "pair"; pair.value = c.pair; pair.disabled = !!c.key; // 만든 뒤에는 문서 쌍을 못 고친다(그 TASK 로 하던 작업의 문서 역할이 달라진다)
    pair.addEventListener("change", () => { c.pair = pair.value; sync(); });
    premise.name = "premise"; premise.rows = 4; premise.maxLength = T.limits.premise; premise.value = c.premise;
    premise.placeholder = `이 TASK 의 전제 · 기준(LLM 호출이 읽는 글). 비우면 「${taskName(T.base)}」 의 전제를 씁니다.`;
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
    const units = h("ul", "wf-assign-units"), warn = h("p", "wf-assign-warn", "목적 문서에 「구성 맞추기」 없이 「내용 넣기」 — 목적 문서가 이미 프로젝트 구성에 맞아야 자리 연결이 섭니다");
    units.setAttribute("aria-label", "문서마다 단위문서 TASK");
    warn.setAttribute("role", "status");
    pick.append(table, units, warn);
    function sync() { // 문서 이름(문서 쌍) · 따라오는 칸 · 문서마다 단위문서 TASK 줄 · 경고(막지 않음)를 지금 고른 것으로
      const names = pairNames(c.pair), docName = (role) => `${ROLE[role]}${names[role] ? " — " + names[role] : ""}`;
      for (const role of ROLES) heads[role].replaceChildren(h("b", "", ROLE[role]), document.createTextNode(names[role] ? ` — ${names[role]}` : ""));
      for (const td of tbody.querySelectorAll("td")) td.dataset.label = docName(td.dataset.role); // 좁은 폭 — 표 머리 대신 칸 위에
      for (const f of follows) { const on = c.assign[f.other].has(f.id); f.span.textContent = on ? f.text || "—" : "—"; f.span.dataset.active = on ? "1" : "0"; }
      units.replaceChildren(...ROLES.map((role) => {
        const li = h("li"), ids = ordered(c.assign[role]);
        li.dataset.role = role;
        li.append(h("b", "", docName(role)), document.createTextNode(": " + (ids.length ? ids.map(stageName).join(" · ") : "—")));
        return li;
      }));
      warn.hidden = !(c.assign.target.has("stage_fill") && !c.assign.target.has("stage_fit"));
    }
    sync();
    const save = h("button", "btn primary", c.busy ? "저장 중…" : c.key ? "고친 것 저장" : "TASK 만들기"), cancel = h("button", "btn", "취소"), acts = h("div", "wf-form-acts");
    save.type = "submit"; save.disabled = c.busy;
    cancel.type = "button";
    cancel.addEventListener("click", () => { composing = null; composeDraw(); });
    acts.append(save, cancel);
    if (c.err) { const e = h("p", "wf-err", c.err); e.setAttribute("role", "alert"); acts.append(e); }
    form.append(h("h3", "", c.key ? `「${c.name}」 고치기` : "새 TASK"), field("이름", name), field("한 줄 설명", desc),
      field("문서 쌍(원본 → 목적)", pair, c.key ? "만든 뒤에는 고칠 수 없습니다" : T.pairs.length > 1 ? "" : "지금 조립할 수 있는 쌍은 이것 하나입니다 — 까닭은 아래 「아직 조립할 수 없는 것」"),
      pick, field("전제(선택)", premise), acts);
    return form;
  }

  async function load() {
    const main = $("wfMain");
    await tasksLoad();
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
    main.replaceChildren(diagram, overview(), composeSec(), ...D.tasks.map(taskSec), ...D.common.map(commonSec));
    composeDraw();
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
