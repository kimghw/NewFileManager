// TASK 워크플로우 페이지(spec_워크플로우 ② §3·§7) — GET /api/workflow 등록부를 다이어그램(기본)·목록으로 그린다. 읽기만 한다(실행·진행 상태 없음).
// TASK 이름·한 줄 설명 = TASK_CATALOG · 이관·취합의 「N단계 이름」 = TASK_STAGE_META(task_catalog.js — 이 파일보다 먼저 읽힌다: 원본 하나).
// 절의 id: 전체 보기 `overview` · TASK `<job>`(묶음 `<job>--<묶음 id>`) · 공통 모듈 `common-<id>` — 주소의 # 로 바로 열린다.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const CAT = typeof TASK_CATALOG === "undefined" ? {} : TASK_CATALOG, META = typeof TASK_STAGE_META === "undefined" ? {} : TASK_STAGE_META;
  const MODEL = { "claude-fable-5-2": "Fable 5.2", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5" }; // 에이전트 설정 페이지(agents.js MODEL)와 같은 이름
  const SOURCE = { user: "에이전트 설정에서 정함", pin: "이 에이전트에 고정", force: "서버 전체 설정", code: "코드가 정함", default: "서버 기본" };
  const CHANGE = { none: "안 바뀜", doc: "바뀜", store: "안 바뀜 — 결과만 저장" }; // 펼친 세부의 「문서」 줄
  const taskName = (job) => (CAT[job] || {}).name || job;
  const stageLabel = (g) => (g.meta && META[g.meta] ? { no: META[g.meta].no, name: META[g.meta].name } : { no: g.no || "", name: g.name });
  const tag = (text, kind) => h("span", "wf-tag" + (kind ? " wf-t-" + kind : ""), text); // kind = llm · human · doc · soft(클래스는 모두 wf- 로 — style.css 의 .doc 등과 안 겹치게)
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

  function badges(s) {
    const box = h("div", "wf-badges");
    for (const b of s.by) box.append(tag(D.by[b] || b, b === "script" ? "" : b));
    if (s.auto) box.append(tag("저절로", "soft"));
    if (s.optional) box.append(tag("안 해도 됨", "soft"));
    if (s.soon) box.append(tag("준비 중", "soft"));
    return box;
  }

  function drawDiagram(route) {
    const { flow, index } = route, { item, groups, steps } = flow, selected = steps[index];
    const diagram = $("wfDiagram"), title = item.job ? taskName(item.job) : item.name;
    const head = h("div", "wf-diagram-head"), heading = h("div");
    heading.append(h("p", "wf-eyebrow", item.job ? "TASK / 순서 살펴보기" : "공통 모듈 / 순서 살펴보기"), h("h2", "", title));
    head.append(heading, link("#overview", "전체 흐름 보기 ↗", "wf-back"));
    const lead = h("p", "wf-lead", item.job ? (CAT[item.job] || {}).desc : item.does);
    const context = h("details", "wf-context"), info = h("dl", "wf-io");
    context.append(h("summary", "", item.job ? "입력·산출물과 전제 보기" : "여는 곳 · 쓰는 TASK 보기"));
    if (item.job) {
      row(info, "받는 문서", item.inputs);
      row(info, "산출물", item.output);
      if (item.note) row(info, "알아 둘 것", item.note);
      if (item.prompt) row(info, "전제", h("code", "", item.prompt));
    } else {
      row(info, "여는 곳", item.where);
      const related = h("div", "wf-links");
      for (const job of item.usedBy) related.append(link(`#${job}`, taskName(job), "wf-chip"));
      row(info, "쓰는 TASK", item.usedBy.length ? related : "어느 TASK의 문서에서나 엽니다.");
    }
    context.append(info);
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
      related.append(h("h4", "", "연결된 공통 모듈"));
      for (const id of selected.s.uses) { const c = D.common.find((x) => x.id === id); links.append(link(`#common-${id}`, c ? c.name : id, "wf-chip")); }
      related.append(links); detail.append(related);
    }
    // 기존 상세 렌더러를 재사용하되 기술 정보만 접어 둔다.
    const technical = stepEl(selected.s).querySelector(".wf-more");
    for (const dt of [...technical.querySelectorAll("dt")]) if (!["에이전트", "모듈", "사양"].includes(dt.textContent)) { dt.nextElementSibling.remove(); dt.remove(); }
    if (technical.childElementCount) {
      const tech = h("details", "wf-tech");
      tech.append(h("summary", "", "기술 상세 · 에이전트 / 모듈 / 사양"), technical); detail.append(tech);
    }
    const controls = h("div", "wf-reader-controls");
    for (const [id, text, to] of [["wfPrev", "← 이전", index - 1], ["wfNext", "다음 →", index + 1]]) {
      const b = h("button", "btn" + (id === "wfNext" ? " wf-primary" : ""), text);
      b.type = "button"; b.id = id; b.dataset.wfFocus = id; b.disabled = to < 0 || to >= steps.length;
      b.addEventListener("click", () => navigate(`#${steps[to].path}`));
      controls.append(b);
    }
    detail.append(controls, h("p", "wf-reading-note", "순서를 살펴보는 화면입니다. 실제 작업 진행 상태와는 별개입니다."));
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

  function stepEl(s) { // 단계 한 줄 — 이름 · 누가 · 문서 바뀜 · 하는 일은 늘 보이고, 누르면 세부(조건 · 나오는 것 · 공통 모듈 · 에이전트 · 모듈 · 사양 자리)
    const d = h("details", "wf-step" + (s.soon ? " wf-soon" : "")), sum = h("summary"), main = h("div"), line = h("div", "wf-line1");
    d.dataset.step = s.key;
    line.append(h("span", "wf-name", s.name));
    for (const b of s.by) line.append(tag(D.by[b] || b, b === "script" ? "" : b));
    if (s.change === "doc") line.append(tag(D.change.doc, "doc"));
    if (s.auto) line.append(tag("저절로", "soft"));
    if (s.optional) line.append(tag("안 해도 됨", "soft"));
    if (s.soon) line.append(tag("준비 중", "soft"));
    main.append(line, h("p", "wf-does", s.does));
    const chev = h("span", "wf-chev");
    chev.setAttribute("aria-hidden", "true");
    sum.append(h("span", "wf-no" + (s.no ? "" : " wf-none"), s.no || ""), main, chev);
    const more = h("dl", "wf-more");
    if (s.out) row(more, "나오는 것", s.out);
    row(more, "문서", CHANGE[s.change] || s.change);
    if (s.uses.length) {
      const box = h("div", "wf-links");
      for (const u of s.uses) { const c = D.common.find((x) => x.id === u); box.append(link(`#common-${u}`, c ? c.name : u, "wf-chip")); }
      row(more, "공통 모듈", box);
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
    if (s.modules.length) row(more, "모듈", s.modules.map((m) => {
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
      h("p", "wf-lead", "TASK 는 여러 모듈을 정해진 차례로 쓰는 일입니다. 스크립트가 계산하고 LLM 은 검토 · 판정만 하며, 문서는 사람이 확인(「반영」 · 「한 번에 진행」)한 뒤에만 바뀝니다. 아래에서 TASK 나 단계 묶음을 누르면 그 과정으로 갑니다."));
    if (D.waysNote) { const p = h("p", "wf-lead wf-ways-note", D.waysNote); p.id = "waysNote"; sec.append(p); } // 진행 방식 둘(한 번에 진행 · 단계별) + 에이전트가 보이는 것 — TASK 절의 「진행 방식」 이 TASK 마다 적는다
    const legend = h("ul", "wf-legend");
    for (const [cls, name, text] of [["", D.by.script, "정해진 코드가 계산"], ["llm", D.by.llm, "에이전트가 검토 · 판정"], ["human", D.by.human, "사람이 고르거나 확인"], ["doc", D.change.doc, "이 단계에서 문서가 바뀜"],
      ["soft", "저절로", "누르지 않아도 돎"], ["soft", "안 해도 됨", "건너뛰어도 다음으로"]]) { const li = h("li"); li.append(tag(name, cls), document.createTextNode(text)); legend.append(li); }
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
    const commons = h("div", "wf-commons");
    commons.append(h("span", "wf-muted", "공통 모듈"));
    for (const c of D.common) commons.append(link(`#common-${c.id}`, c.name, "wf-chip"));
    sec.append(commons);
    return sec;
  }

  function taskSec(t) { // TASK 절 — 이름 · 한 줄 설명 · 받는 문서 → 산출물 · 알아 둘 것 → 단계 묶음(세로 차례)
    const c = CAT[t.job] || {}, sec = h("section", "wf-sec wf-task"), h2 = h("h2");
    sec.id = t.job;
    h2.append(h("span", "wf-kind", "TASK"), document.createTextNode(taskName(t.job)));
    if (t.soon) h2.append(tag("준비 중", "soft"));
    sec.append(h2);
    if (c.desc) sec.append(h("p", "wf-lead", c.desc));
    const io = h("dl", "wf-io");
    row(io, "받는 문서", t.inputs);
    row(io, "산출물", t.output);
    if (t.note) row(io, "알아 둘 것", t.note);
    if (t.prompt) row(io, "전제", [h("code", "", t.prompt), document.createTextNode(" — 이 TASK 의 전제 · 기준을 적은 할 일 프롬프트(에이전트가 먼저 읽는 글)")]);
    sec.append(io);
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
    h2.append(h("span", "wf-kind", "공통 모듈"), document.createTextNode(c.name));
    sec.append(h2, h("p", "wf-lead", c.does));
    row(io, "여는 곳", c.where);
    if (c.usedBy.length) { const links = h("div", "wf-links"); for (const job of c.usedBy) links.append(link(`#${job}`, taskName(job), "wf-chip")); row(io, "쓰는 TASK", links); }
    else row(io, "쓰는 TASK", "어느 TASK 의 문서에서나 엽니다(단계에 묶이지 않음)");
    box.append(stepsEl(c.steps, `common-${c.id}`));
    box.style.marginTop = "10px";
    sec.append(io, box);
    return sec;
  }

  function navDraw() {
    const nav = $("wfNav");
    nav.replaceChildren(link("#overview", "전체 보기"), h("h2", "", "TASK"), ...D.tasks.map((t) => link(`#${t.job}`, taskName(t.job), t.soon ? "wf-soon" : "")),
      h("h2", "", "공통 모듈"), ...D.common.map((c) => link(`#common-${c.id}`, c.name)));
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
    for (const sec of main.querySelectorAll(".wf-sec")) sec.hidden = view === "diagram" && (id !== "overview" || sec.id !== "overview");
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

  async function load() {
    const main = $("wfMain");
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
    main.replaceChildren(diagram, overview(), ...D.tasks.map(taskSec), ...D.common.map(commonSec));
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
