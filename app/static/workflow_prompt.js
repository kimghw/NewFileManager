// 단계의 LLM 아이콘에서 여는 프롬프트 편집기. 문서에서는 문서 옆 열, 독립 워크플로우 페이지에서는 대화상자를 사용한다.
(() => {
  "use strict";
  const drafts = new Map(); // 열을 닫거나 다른 에이전트를 보는 동안에도 저장하지 않은 글을 보관한다.
  const pending = new Set();
  let active;

  function node(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function button(text, click, primary = false) {
    const b = node("button", primary ? "btn sm primary" : "btn sm", text);
    b.type = "button";
    b.onclick = click;
    return b;
  }
  async function request(url, opts) {
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`), { status: res.status });
    return data;
  }
  function mount(ctx) {
    const panel = node("section", "wfp-panel");
    panel.id = "workflowPromptDlg";
    const title = "LLM 프롬프트";
    if (typeof headsDlg === "function" && typeof state !== "undefined" && state.id && !document.body.classList.contains("no-doc")) {
      const { body } = headsDlg("workflowPrompt", title, ctx.title || "");
      body.append(panel);
    } else {
      active?.dialog?.close();
      const dialog = node("dialog", "wfp-dialog"), head = node("header", "wfp-head");
      const heading = node("h2", "", title);
      heading.id = "workflowPromptTitle";
      dialog.setAttribute("aria-labelledby", heading.id);
      head.append(heading, node("span", "wfp-sub", ctx.title), button("닫기", () => dialog.close()));
      dialog.append(head, panel);
      dialog.addEventListener("close", () => {
        dialog.remove();
        if (ctx.trigger?.isConnected && !active?.panel?.isConnected) ctx.trigger.focus();
      }, { once: true });
      document.body.append(dialog);
      dialog.showModal();
      return { panel, dialog };
    }
    return { panel };
  }
  function partsFor(agent, ctx) {
    const steps = ctx.step ? [ctx.step] : ctx.steps || [];
    return agent.prompt.filter(p => {
      if (p.kind !== "note" || !p.name) return true;
      if (p.name.startsWith("tool:")) return !ctx.template || (steps.length
        ? steps.some(step => p.name === `tool:${ctx.template}.${step}`) : p.name.startsWith(`tool:${ctx.template}.`));
      if (p.name.startsWith("jobtool:")) return !ctx.job || (steps.length
        ? steps.some(step => p.name === `jobtool:${ctx.job}/${step}`) : p.name.startsWith(`jobtool:${ctx.job}/`));
      return !ctx.job || p.name === ctx.job;
    });
  }
  // 미리보기 — 프롬프트의 마크다운(제목 · 목록 · 굵게 · 코드 · 표 · 인용)을 읽기 좋게 그린다. DOM 으로만 짓는다(innerHTML 을 쓰지 않음).
  // 원문과 미리보기는 열 전체에 하나의 선택이고 이 PC 에 기억한다(2026-11-26 사용자 「md 형식이라 보기 힘듬 — 프리뷰 기능 넣어줘」).
  const VIEW_KEY = "nfm.wfpView";
  let viewMode = (() => { try { return localStorage.getItem(VIEW_KEY) === "raw" ? "raw" : "preview"; } catch { return "preview"; } })();
  function inline(parent, text) {
    const re = /(`+)([\s\S]+?)\1|\*\*([^*\n]+?)\*\*|\*([^*\s][^*\n]*?)\*|\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g;
    let at = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > at) parent.append(text.slice(at, m.index));
      if (m[1]) parent.append(node("code", "", m[2].trim() || m[2]));
      else if (m[3] != null) inline(parent.appendChild(node("strong")), m[3]);
      else if (m[4] != null) inline(parent.appendChild(node("em")), m[4]);
      else {
        const a = node("a", "", m[5]);
        a.href = m[6];
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        parent.append(a);
      }
      at = re.lastIndex;
    }
    if (at < text.length) parent.append(text.slice(at));
    return parent;
  }
  const cells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
  function markdown(text) {
    const root = node("div", "wfp-text wfp-md"), lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
    const looksJson = /^\s*[[{]/.test(text || "") && (() => { try { JSON.parse(text); return true; } catch { return false; } })();
    if (looksJson) {
      root.append(node("pre", "wfp-md-code", text));
      return root;
    }
    let i = 0;
    const listRe = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      const fence = line.match(/^\s*(```+|~~~+)\s*([\w-]*)/);
      if (fence) {
        const body = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
        i++;
        const pre = node("pre", "wfp-md-code", body.join("\n"));
        if (fence[2]) pre.dataset.lang = fence[2];
        root.append(pre);
        continue;
      }
      const h = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
      if (h) {
        root.append(inline(node(`h${Math.min(6, h[1].length + 2)}`, "wfp-md-h"), h[2]));
        i++;
        continue;
      }
      if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { root.append(node("hr")); i++; continue; }
      if (/^\s*>/.test(line)) {
        const body = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ""));
        const q = node("blockquote");
        q.append(...markdown(body.join("\n")).childNodes);
        root.append(q);
        continue;
      }
      if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        const wrap = node("div", "wfp-md-table"), table = node("table"), head = node("tr");
        cells(line).forEach(c => head.append(inline(node("th"), c)));
        table.append(node("thead")).append(head);
        const tbody = table.appendChild(node("tbody"));
        i += 2;
        while (i < lines.length && /^\s*\|/.test(lines[i])) {
          const tr = node("tr");
          cells(lines[i++]).forEach(c => tr.append(inline(node("td"), c)));
          tbody.append(tr);
        }
        wrap.append(table);
        root.append(wrap);
        continue;
      }
      if (listRe.test(line)) {
        // 목록 — 들여쓰기로 겹친다. 항목 아래 들여 쓴 이어지는 줄은 그 항목의 글이다(원문이 긴 항목을 여러 줄로 나눠 적는다).
        const stack = [];
        while (i < lines.length) {
          const l = lines[i], m = l.match(listRe);
          if (!m) {
            if (!l.trim() || !stack.length || !/^\s/.test(l)) break;
            const li = stack[stack.length - 1].li;
            if (li) inline(li.querySelector(":scope > .wfp-md-li") || li, " " + l.trim());
            i++;
            continue;
          }
          const indent = m[1].replace(/\t/g, "  ").length, ordered = /\d/.test(m[2]);
          while (stack.length && indent < stack[stack.length - 1].indent) stack.pop();
          let top = stack[stack.length - 1];
          if (!top || indent > top.indent) {
            const list = node(ordered ? "ol" : "ul", "wfp-md-list");
            if (ordered) list.start = parseInt(m[2], 10) || 1;
            (top?.li || root).append(list);
            top = { indent, list, li: null };
            stack.push(top);
          }
          const li = node("li"), body = node("span", "wfp-md-li");
          inline(body, m[3]);
          li.append(body);
          top.list.append(li);
          top.li = li;
          i++;
        }
        continue;
      }
      const para = [];
      while (i < lines.length && lines[i].trim() && !listRe.test(lines[i]) && !/^\s*(```|~~~|#{1,6}\s|>|\|)/.test(lines[i])) para.push(lines[i++].trim());
      if (!para.length) { root.append(inline(node("p"), lines[i++].trim())); continue; }
      root.append(inline(node("p"), para.join(" ")));
    }
    return root;
  }
  function showText(text, kind) {
    if (viewMode === "raw") return node("pre", "wfp-text", text);
    if (kind === "data") {
      const box = node("div", "wfp-text wfp-md");
      box.append(node("pre", "wfp-md-code", text));
      return box;
    }
    return markdown(text);
  }
  function viewSwitch(view) {
    const box = node("div", "wfp-view");
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "보기");
    for (const [mode, label] of [["preview", "미리보기"], ["raw", "원문"]]) {
      const b = node("button", "wfp-view-btn", label);
      b.type = "button";
      b.dataset.view = mode;
      b.setAttribute("aria-pressed", String(viewMode === mode));
      b.onclick = () => {
        if (viewMode === mode) return;
        viewMode = mode;
        try { localStorage.setItem(VIEW_KEY, mode); } catch {}
        box.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.view === mode)));
        view.panel.dataset.view = mode;
        view.redraw.forEach(fn => fn());
      };
      box.append(b);
    }
    return box;
  }
  const editKey = p => p.job ? `${p.api}#${p.job}` : p.api;
  async function documentParts(agent, ctx) {
    const parts = partsFor(agent, ctx);
    const i = parts.findIndex(p => p.kind === "form");
    if (i < 0 || !ctx.docId) return parts;
    try {
      const { form } = await request(`/api/docs/${encodeURIComponent(ctx.docId)}/headings/form/prompt?agent=${encodeURIComponent(agent.id)}`);
      parts[i] = form ? {
        kind: "form", name: form.key, title: `선택한 문서의 양식 지침 — ${form.name}`, source: "",
        note: "이 단계가 읽는 부분을 표시합니다. 수정할 때는 양식 파일 전체가 열리며 같은 양식을 쓰는 문서에 적용됩니다.",
        text: form.applied, editText: form.text, editable: true, version: form.sha1,
        api: `/api/headings/forms/${encodeURIComponent(form.key)}`,
      } : { ...parts[i], note: "선택한 문서에 연결된 양식 지침이 없습니다.", source: "" };
    } catch (e) {
      parts[i] = { ...parts[i], note: `선택한 문서의 양식 지침을 읽지 못했습니다 — ${e.message}`, source: "" };
    }
    return parts;
  }
  function say(view, msg, error = false) {
    view.status.textContent = msg;
    view.status.classList.toggle("error", error);
  }
  function unit(view, p, expanded) {
    const det = node("details", "wfp-part"), summary = node("summary");
    det.dataset.kind = p.kind;
    det.dataset.name = p.name || "";
    const key = editKey(p);
    det.open = expanded || !!key && drafts.has(key);
    summary.append(node("strong", "", p.title));
    if (p.editable) {
      let scope = "공통";
      if (p.kind === "form") scope = "이 양식";
      if (p.job || p.kind === "job") scope = view.ctx.job === (p.job || p.name) ? "이 워크플로우" : "워크플로우별";
      summary.append(node("span", p.custom ? "wfp-scope wfp-custom" : "wfp-scope", p.custom ? scope + " · 수정됨" : scope));
    }
    det.append(summary);
    const content = node("div", "wfp-content");
    det.append(content);
    function draw() {
      const draft = key && drafts.get(key), busy = pending.has(key);
      det.classList.toggle("wfp-empty", !(p.text && p.text.trim()) && !draft);
      det.classList.toggle("wfp-editing", !!draft);
      const actions = node("div", "wfp-actions");
      content.replaceChildren();
      const info = [p.source, p.note].filter(Boolean).join(" · ");
      if (info) content.append(node("p", "wfp-source", info));
      if (!draft && p.text) content.append(showText(p.text, p.kind));
      if (!p.editable || !key) return;
      const original = p.editText ?? p.text ?? "";
      const edit = () => {
        drafts.set(key, { text: original, original, version: p.version });
        draw();
        content.querySelector("textarea")?.focus();
      };
      if (draft) {
        const input = node("textarea", "wfp-input");
        input.value = draft.text;
        input.setAttribute("aria-label", p.title);
        input.spellcheck = false;
        input.readOnly = busy;
        const save = button("저장", () => commit(false), true);
        const sync = () => { save.disabled = busy || draft.text === original || (!draft.text.trim() && p.kind !== "note"); };
        input.oninput = () => { draft.text = input.value; sync(); };
        sync();
        // 편집 중에도 미리보기 — 「편집」 · 「미리보기」 를 오간다(고친 글은 그대로 남는다).
        const tabs = node("div", "wfp-edit-tabs"), preview = node("div", "wfp-edit-preview");
        tabs.setAttribute("role", "tablist");
        const showTab = tab => {
          draft.tab = tab;
          input.hidden = tab !== "edit";
          preview.hidden = tab !== "preview";
          if (tab === "preview") preview.replaceChildren(draft.text.trim() ? markdown(draft.text) : node("p", "wfp-source", "(빈 글)"));
          tabs.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
        };
        for (const [tab, label] of [["edit", "편집"], ["preview", "미리보기"]]) {
          const b = node("button", "wfp-edit-tab", label);
          b.type = "button";
          b.dataset.tab = tab;
          b.setAttribute("role", "tab");
          b.onclick = () => { showTab(tab); if (tab === "edit") input.focus(); };
          tabs.append(b);
        }
        content.append(tabs, input, preview);
        showTab(draft.tab || "edit");
        if (draft.original !== original) {
          const changed = node("details", "wfp-latest");
          changed.append(node("summary", "", "다른 곳에서 저장된 현재 원문 보기"), node("pre", "wfp-text", original || "(빈 글)"));
          content.append(changed);
        }
        actions.append(save, button("취소", () => { drafts.delete(key); draw(); content.querySelector("button")?.focus(); }));
      } else {
        actions.append(button("수정", edit));
        if (p.custom && p.builtin !== false && p.kind !== "note") {
          actions.append(button("기본값 복원", () => {
            if (confirm(`「${p.title}」의 저장된 수정을 지우고 기본값을 사용할까요?`)) commit(true);
          }));
        }
      }
      if (busy) actions.querySelectorAll("button").forEach(b => { b.disabled = true; });
      content.append(actions);
    }
    async function commit(reset) {
      if (pending.has(key)) return;
      const draft = drafts.get(key);
      if (!reset && !draft) return;
      const visible = () => active?.panel.isConnected && active.keys?.has(key);
      pending.add(key);
      draw();
      let message = "", error = false;
      try {
        if (reset) {
          const url = new URL(p.api, location.origin);
          url.searchParams.set("version", p.version);
          await request(url, { method: "DELETE" });
        } else {
          const body = p.kind === "form" ? { text: draft.text, sha1: draft.version } : { text: draft.text, version: draft.version };
          if (p.job) body.job = p.job;
          if (p.kind === "skill") body.name = p.skillName;
          if (p.kind === "heading") body.reason = "워크플로우 단계에서 프롬프트 수정";
          await request(p.api, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        }
        drafts.delete(key);
        message = reset ? "기본값을 복원했습니다. 다음 호출부터 적용됩니다." : "저장했습니다. 다음 호출부터 적용됩니다.";
      } catch (e) {
        error = true;
        message = e.status === 409 ? "다른 곳에서 먼저 저장했습니다. 현재 원문과 수정 중인 글을 확인한 뒤 다시 저장하세요." : `저장하지 못했습니다 — ${e.message}`;
      } finally {
        pending.delete(key);
      }
      if (visible()) await load(active, key, message, error);
    }
    draw();
    view.redraw.push(() => { if (!drafts.has(key)) draw(); });
    return det;
  }
  async function load(view, opened = "", message = "", error = false) {
    const token = ++view.seq, id = view.agent;
    const current = () => token === view.seq && view.panel.isConnected;
    view.keys = null;
    view.redraw = [];
    say(view, "프롬프트를 읽고 있습니다…");
    view.parts.replaceChildren();
    try {
      const query = new URLSearchParams();
      if (view.ctx.job) query.set("job", view.ctx.job);
      const agent = await request(`/api/agents/${encodeURIComponent(id)}${query.size ? "?" + query : ""}`);
      if (!current()) return;
      const selected = view.select.options[view.select.selectedIndex];
      selected.textContent = agent.name;
      view.where.textContent = agent.where || "";
      const parts = await documentParts(agent, view.ctx);
      if (!current()) return;
      view.keys = new Set(parts.map(editKey).filter(Boolean));
      const first = (opened && parts.find(p => editKey(p) === opened)) || parts.find(p => ["heading", "merge", "skill"].includes(p.kind)) || parts[0];
      for (const p of parts) {
        const draft = drafts.get(editKey(p));
        // 다음 저장은 이 화면에서 다시 읽은 판을 기준으로 한다. 원문이 달라지면 비교할 글도 함께 표시한다.
        if (draft && draft.version !== p.version) draft.version = p.version;
        view.parts.append(unit(view, p, p === first));
      }
      say(view, message, error);
    } catch (e) {
      if (!current()) return;
      say(view, `프롬프트를 읽지 못했습니다 — ${e.message}`, true);
      view.parts.append(button("다시 읽기", () => load(view)));
    }
  }
  function open(ctx) {
    const agents = (ctx.agents || []).map(a => typeof a === "string" ? { id: a, name: a } : a);
    if (!agents.length) return;
    const view = { ...mount(ctx), ctx, seq: 0, agent: agents[0].id, redraw: [] };
    view.panel.dataset.view = viewMode;
    active = view;
    const row = node("label", "wfp-select"), select = node("select");
    view.select = select;
    for (const a of agents) select.add(new Option(a.name || a.id, a.id));
    select.setAttribute("aria-label", "에이전트");
    select.onchange = () => { view.agent = select.value; load(view); };
    row.append(node("span", "", "에이전트"), select);
    const bar = node("div", "wfp-bar");
    bar.append(row, viewSwitch(view));
    view.where = node("p", "wfp-source");
    view.status = node("p", "wfp-status");
    view.status.setAttribute("role", "status");
    view.parts = node("div", "wfp-parts");
    view.panel.append(bar, view.where, view.status, view.parts);
    load(view);
  }
  window.WorkflowPrompt = { open };
})();
