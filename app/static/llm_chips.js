// LLM 칩 — LLM 을 쓰는 도구에 「어떤 모델인지」 를 자리마다(LLM1 · LLM2 …) 보이고, 누르면 모델을 고른다.
// 2026-11-25 사용자 "LLM 사용하는 도구는 어떤 모델인지 명시하도록, LLM1, LLM2 이런식으로 하고 클릭 해서 모델을 선택할 수 있도록".
// 원본 = 에이전트 설정(GET /api/agents 의 agents[].llms — app/agents.py llms_of) · 고침 = PUT /api/agents/{id} {model} | {models}(함께 부르는 에이전트 — 양식 검토 · 작성 지침 보완 · 04 「LLM 검증·보완」 의 판정 에이전트).
// 함께 부르는 에이전트의 메뉴에는 「한 모델만 쓰기 — LLMn 빼기」 가, 한 모델만으로 둔 그 에이전트의 메뉴에는 「두 모델로 — LLM2 더하기」 가 선다(agents[].llmsDefault = 등록부의 기본 자리).
// 혼자 선다(app.js 를 읽지 않는다) — 패널 대시보드 · 첫 화면의 대시보드(dashboard.js dashTags) · 워크플로우 페이지(workflow.js)가 같이 쓴다.
// 꼴: llm_chips.css. 모델을 바꾸면 이 페이지의 모든 칩을 다시 그린다(같은 에이전트가 여러 카드에 있다).
const LlmChips = (() => {
  const NAME = { "claude-fable-5-2": "Fable 5.2", "claude-opus-5-5": "Opus 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-haiku-5-5": "Haiku 5.5", "gpt-6-astra": "astra" };
  const name = (m) => NAME[m] || m;
  let data = null, loading = null, menu = null;

  function load(force) {
    if (force) { data = null; loading = null; }
    if (data) return Promise.resolve(data);
    if (!loading) loading = fetch("/api/agents").then((r) => (r.ok ? r.json() : null)).then((d) => { data = d; return d; }).catch(() => null);
    return loading;
  }
  const agentOf = (id) => data && (data.agents || []).find((a) => a.id === id);

  function chip(label, model, title, onOpen) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "llm-chip" + (model.startsWith("gpt-") ? " llm-chip-codex" : "");
    b.textContent = `${label} · ${name(model)}`;
    b.title = `${title}\n눌러서 모델 바꾸기`;
    b.setAttribute("aria-haspopup", "menu");
    b.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); onOpen(b); });
    return b;
  }

  // 2026-11-25 사용자 "서로 다른 모델을 요구하는게 아니면 1개 모델로 할게": 한 도구(단계)의 에이전트가 여럿이어도 모델이 같으면 칩 하나 —
  // 모델이 다른 것만 LLM1 · LLM2 … 로 따로(템플릿 서식 정리의 Opus 5.5 처럼). 함께 부르는 에이전트(양식 검토 — 자리마다 다른 모델)는 제 자리 그대로.
  function fill(box) {
    const ids = [...new Set((box.dataset.llmAgents || "").split(" ").filter(Boolean))], out = [], groups = new Map(), duos = new Map();
    const full = (a) => `${a.no ? a.no + " " : ""}${a.name}`;
    for (const id of ids) {
      const a = agentOf(id);
      if (!a) continue;
      const ls = a.llms || [];
      if (ls.length > 1) { // 함께 부르는 에이전트 — 모델 자리가 같은 것끼리 칩 한 벌(04 「LLM 검증·보완」 의 판정 에이전트 넷이 LLM1 · LLM2 한 벌로 보인다: 2026-11-26)
        const key = ls.map((s) => s.model).join("|");
        if (!duos.has(key)) duos.set(key, []);
        duos.get(key).push(a);
        continue;
      }
      for (const s of ls) {
        if (!groups.has(s.model)) groups.set(s.model, []);
        groups.get(s.model).push([a, s]);
      }
    }
    // 같은 카드에 한 모델 에이전트도 있으면(04 의 서식 정리 계획 · 구간 검증): 그 모델이 첫 벌의 어느 자리와 같으면 그 칩에 같이 싣고(이름표 「LLM1」 이 둘로 서지 않게), 다르면 자리 번호를 이어 매긴다(LLM3 …)
    const lead = duos.size ? [...duos.values()][0] : null, ride = new Map();
    if (lead) for (const [model, xs] of [...groups]) {
      const i = lead[0].llms.findIndex((s) => s.model === model);
      if (i >= 0 && !xs.some(([a]) => (a.llmsDefault || []).length > 1)) { ride.set(i, xs); groups.delete(model); }
    }
    let n = Math.max(0, ...[...duos.values()].map((as) => as[0].llms.length));
    for (const as of duos.values()) {
      as[0].llms.forEach((s, i) => {
        const with_ = as === lead ? ride.get(i) || [] : [];
        const who = as.length + with_.length > 1 ? `에이전트 ${as.length + with_.length}개` : as[0].name;
        const b = chip(s.slot, s.model, `${s.slot} 모델 ${s.model} — 함께 판정하고 협의:\n· ${as.map(full).join("\n· ")}${with_.length ? `\n이 모델 하나로 도는 에이전트:\n· ${with_.map(([a]) => full(a)).join("\n· ")}` : ""}`,
          (c) => open(c, `${who} · ${s.slot}`, s.model, "모델마다 따로 판정하고, 답이 다르면 LLM1 의 모델이 협의해 하나로 냅니다(한쪽만 답하면 그 답)", (m) => pick([...as.map((a) => [a, a.llms[i]]), ...with_], m),
            [{ text: `한 모델만 쓰기 — ${s.slot} 빼기`, title: "불가피할 때 — 남은 자리의 모델 하나로만 돕니다(협의 없음). 다시 두 모델로 되돌릴 수 있습니다",
              run: () => setModels(as, (a) => a.llms.filter((_, k) => k !== i).map((x) => x.model)) }]));
        b.dataset.llmAgents = as.map((a) => a.id).join(" "); b.dataset.llmSlot = s.slot;
        out.push(b);
      });
    }
    const solo = [];
    for (const [model, xs] of groups) {
      const label = `LLM${++n}`, names = xs.map(([a]) => full(a));
      const more = xs.filter(([a]) => (a.llmsDefault || []).length > 1).map(([a]) => a); // 「한 모델만」 으로 둔 함께 부르는 에이전트 — 다시 두 모델로
      const b = chip(label, model, `${label} 모델 ${model} — ${xs.length > 1 ? `에이전트 ${xs.length}개가 같이 씀` : "에이전트"}:\n· ${names.join("\n· ")}${more.length ? "\n(한 모델만 쓰는 중 — 눌러서 두 모델로)" : ""}`,
        (c) => open(c, xs.length > 1 ? `${label} · 에이전트 ${xs.length}개` : `${xs[0][0].name} · ${label}`, model,
          xs.length > 1 ? `이 ${xs.length}개 에이전트를 함께 바꿉니다 — 그 에이전트를 쓰는 모든 워크플로우에 적용됩니다` : "이 에이전트를 쓰는 모든 워크플로우에 적용됩니다", (m) => pick(xs, m),
          more.length ? [{ text: "두 모델로 — LLM2 더하기(협의)", title: `LLM2(${name(more[0].llmsDefault[1])})를 더해 두 모델이 따로 판정하고 협의합니다 — 호출이 늡니다:\n· ${more.map(full).join("\n· ")}`,
            run: () => setModels(more, (a) => [a.llms[0].model, ...a.llmsDefault.slice(1)]) }] : []));
      b.dataset.llmAgents = xs.map(([a]) => a.id).join(" ");
      b.dataset.llmSlot = label;
      if (more.length) b.dataset.llmOne = "1";
      solo.push(b);
    }
    box.replaceChildren(...out, ...solo); // 함께 부르는 자리(LLM1 · LLM2)가 먼저, 이어 매긴 한 모델 칩(LLM3 …)이 뒤
    box.hidden = !(solo.length + out.length);
  }

  function el(agents) { // agents = 에이전트 id 목록 | [{id}] → 칩 상자(읽은 뒤 채움)
    const box = document.createElement("span");
    box.className = "llm-chips";
    box.dataset.llmAgents = (agents || []).map((a) => (typeof a === "string" ? a : a && a.id)).filter(Boolean).join(" ");
    box.hidden = true;
    if (data) fill(box); else load().then(() => fill(box)); // 읽어 둔 뒤면 바로 채운다 — 그린 뒤 줄이 밀리지 않게(대시보드가 그리자마자 줄을 보이게 옮긴다)
    return box;
  }

  function close() { if (menu) { menu.remove(); menu = null; document.removeEventListener("pointerdown", outside, true); document.removeEventListener("keydown", esc, true); } }
  function outside(e) { if (menu && !menu.contains(e.target)) close(); }
  function esc(e) { if (e.key === "Escape") { close(); } }

  function open(chipEl, title, cur, noteText, onPick, extras) { // extras = 모델 목록 아래의 줄 [{text, title, run}] — 「한 모델만 쓰기」 · 「두 모델로」
    close();
    menu = document.createElement("div");
    menu.className = "llm-menu"; menu.setAttribute("role", "menu");
    const head = document.createElement("div");
    head.className = "llm-menu-head";
    head.textContent = title;
    menu.append(head);
    for (const m of data.models || []) {
      const b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "menuitemradio"); b.setAttribute("aria-checked", String(m === cur));
      b.textContent = `${m === cur ? "✓ " : ""}${name(m)}`;
      b.title = m + (m.startsWith("gpt-") ? " — Codex CLI(OpenAI 로그인)로 부릅니다" : "");
      b.addEventListener("click", () => { close(); onPick(m); });
      menu.append(b);
    }
    for (const x of extras || []) {
      const b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "menuitem"); b.className = "llm-menu-extra";
      b.textContent = x.text; b.title = x.title || "";
      b.addEventListener("click", () => { close(); x.run(); });
      menu.append(b);
    }
    const note = document.createElement("div");
    note.className = "llm-menu-note";
    note.textContent = noteText;
    menu.append(note);
    document.body.append(menu);
    const r = chipEl.getBoundingClientRect();
    menu.style.left = `${Math.max(4, Math.min(r.left, window.innerWidth - menu.offsetWidth - 4)) + window.scrollX}px`;
    menu.style.top = `${r.bottom + 4 + window.scrollY}px`;
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", esc, true);
    menu.querySelector("[aria-checked=true]")?.focus();
  }

  async function pick(xs, m) { // xs = [[에이전트, 자리]] — 같은 칩에 묶인 에이전트 모두
    for (const [a, s] of xs) {
      if (s.model === m) continue;
      const body = s.multi ? { models: (a.llms || []).map((x) => (x.slot === s.slot ? m : x.model)) } : { model: m };
      const r = await fetch(`/api/agents/${encodeURIComponent(a.id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) { alert(`${a.name} 의 모델을 바꾸지 못했습니다: ${(await r.text()).slice(0, 200)}`); break; }
    }
    await load(true);
    document.querySelectorAll(".llm-chips").forEach(fill);
  }

  // 함께 부르는 에이전트의 모델 자리를 통째로 고친다(2026-11-26 사용자 "2가지 모델을 같이 사용할 수 있도록 하고 불가피한 경우 1개만 선택 할 수도 있게") —
  // 한 모델만 = models 길이 1(서버가 기본 두 모델로 되돌리지 않는다) · 두 모델로 = 지금 LLM1 + 등록부의 LLM2. as = 에이전트들 · fn(a) → 그 에이전트의 새 models.
  async function setModels(as, fn) {
    for (const a of as) {
      const r = await fetch(`/api/agents/${encodeURIComponent(a.id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ models: fn(a) }) });
      if (!r.ok) { alert(`${a.name} 의 모델 자리를 바꾸지 못했습니다: ${(await r.text()).slice(0, 200)}`); break; }
    }
    await load(true);
    document.querySelectorAll(".llm-chips").forEach(fill);
  }

  return { el, load, name };
})();
LlmChips.load(); // 미리 읽어 둔다 — 카드를 그린 뒤 칩이 늦게 들어와 줄이 밀리지 않게(읽은 뒤면 칩은 그리는 차례 안에 찬다)
