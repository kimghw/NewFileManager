// 조립 화면의 「도구 설명」 열 — 도구 이름 고치기(spec_워크플로우 ② §18-19 · design.md §22 — 2026-11-21 사용자(카드 「다시 문서 검토」 를 보며) "도구 이름을 바꿀 수 없네?" → 물어서 받은 답 「도구 자체 (모든 워크플로우)」):
// 도구(조립에 놓는 줄 — (틀, 줄 key))의 이름을 고치면 **그 도구를 쓰는 모든 워크플로우(붙박이 포함)의 화면**에 그 이름으로 보인다. 코드의 이름(등록부 = 기본 이름) · 만든 글(workflow.md · tasks/)은 그대로다.
// 이 워크플로우의 조립(줄 · 검사 · 저장)과 따로 도는 설정이다 — 폼을 저장하지 않아도 바로 적용되고 폼을 취소해도 남는다(「도구에 적어 두는 내용」 의 「도구 공통」 과 같은 범위).
// 이 파일은 workflow.js 없이 혼자 선다(제 도우미) — workflow.js 의 훅은 둘: helpUnitEl 의 이름 아래 `WfNames.row(o)` · 카드 이름을 두 번 누르면 `WfNames.start(state, unit, name)`.
//   o = { state(폼마다의 상태 — c.nm: 다시 그려도 고치던 글이 남는다), family(relay · gather · single), unit(줄 key), name(지금 보이는 이름), base(기본 이름), max(이름의 길이),
//         redraw()(그 열을 다시 그린다), changed(답) → Promise(페이지의 등록부 · 조립 자료를 다시 읽는다 — 끝나면 그 열이 새 이름으로 다시 선다) }
// 서버: PUT /api/tool-names/{틀}/{줄 key} {name} → {name, base, shown, same[이름이 같아진 같은 틀의 다른 도구…], also[같이 고친 다른 틀…]} · DELETE = 기본 이름으로(app/tool_names_api.py — 거절 글은 서버의 것 그대로).
(() => {
  "use strict";
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const FAMILY = { relay: "이관형", gather: "취합형", single: "문서 하나" }; // 틀의 화면 이름(조립 폼의 문서 입출력: 1 → N · N → 1 · 1)
  const josa = (word, a, b) => (typeof taskJosa === "function" ? taskJosa(word, a, b) : a);
  const PEN = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';

  async function call(url, opts) { // → 답(JSON) | 예외(서버의 글 그대로)
    const r = await fetch(url, { headers: { Accept: "application/json", ...(opts && opts.body ? { "Content-Type": "application/json" } : {}) }, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((typeof data.detail === "string" && data.detail) || `HTTP ${r.status}`);
    return data;
  }

  function start(state, unit, name) { // 그 도구의 이름을 고치기 시작한다(상태만 — 그리는 것은 부르는 쪽)
    Object.assign(state, { unit, text: name, err: "", msg: "", at: "", busy: false, focus: true });
  }
  function stop(state) { Object.assign(state, { unit: "", text: "", err: "", busy: false, focus: false }); }

  function told(r) { // 저장한 뒤의 한 줄 — 무엇으로 바꿨나 · 같이 고친 틀 · 이름이 같아진 다른 도구
    const parts = [r.name ? `이름을 「${r.shown}」 ${josa(r.shown, "으로", "로")} 바꿨습니다` : `기본 이름 「${r.base}」 ${josa(r.base, "으로", "로")} 되돌렸습니다`];
    if ((r.also || []).length) parts.push(`${r.also.map((f) => FAMILY[f] || f).join(" · ")}의 같은 도구도 같이`);
    if ((r.same || []).length) parts.push(`이 틀에 같은 이름의 도구가 또 있습니다(기본 이름 ${r.same.map((b) => `「${b}」`).join(" · ")}) — 카드로 가르기 어렵습니다`);
    return parts.join(" · ");
  }

  async function send(o, name) {
    const s = o.state;
    s.busy = true; s.err = "";
    o.redraw();
    let r = null;
    try {
      r = await call(`/api/tool-names/${encodeURIComponent(o.family)}/${encodeURIComponent(o.unit)}`, name ? { method: "PUT", body: JSON.stringify({ name }) } : { method: "DELETE" });
    } catch (e) {
      s.busy = false; s.err = e.message; s.focus = true;
      o.redraw();
      return;
    }
    stop(s);
    s.msg = told(r); s.at = o.unit;
    await o.changed(r); // 페이지가 등록부 · 조립 자료를 다시 읽고 이 열을 새 이름으로 다시 세운다
  }

  function row(o) { // 이름 아래의 한 줄 — 닫힌 꼴(「이름 바꾸기」 · 고친 도구는 기본 이름) | 고치는 꼴(입력 칸 · 저장 · 기본 이름으로 · 취소 · 안내)
    const s = o.state, box = h("div", "wf-name"), renamed = o.name !== o.base;
    box.dataset.unit = o.unit;
    box.dataset.state = s.unit === o.unit ? "edit" : renamed ? "renamed" : "base";
    if (s.at && s.at !== o.unit) { s.msg = ""; s.at = ""; } // 다른 도구로 옮겨 감 — 앞 도구의 알림은 지운다
    if (s.unit !== o.unit) {
      const go = h("button", "btn sm wf-name-go");
      go.type = "button";
      go.innerHTML = PEN;
      go.append(h("span", "", "이름 바꾸기"));
      go.title = "이 도구의 이름을 고칩니다 — 이 도구를 쓰는 모든 워크플로우의 화면에 그 이름으로 보입니다(카드의 이름을 두 번 눌러도 됩니다)";
      go.addEventListener("click", () => { start(s, o.unit, o.name); o.redraw(); });
      const top = h("div", "wf-name-top");
      top.append(go);
      if (renamed) top.append(h("span", "wf-name-base", `기본 이름 「${o.base}」`));
      box.append(top);
      if (s.msg && s.at === o.unit) { const p = h("p", "wf-name-msg", s.msg); p.setAttribute("role", "status"); box.append(p); }
      if (s.focus === "go") { s.focus = false; queueMicrotask(() => { if (go.isConnected) go.focus({ preventScroll: true }); }); } // 취소한 뒤 — 초점은 단추로
      return box;
    }
    const form = h("form", "wf-name-edit"), input = h("input", "wf-name-input"), save = h("button", "btn sm primary", s.busy ? "저장하는 중…" : "저장"), cancel = h("button", "btn sm", "취소");
    const max = o.max || 30, old = document.activeElement, was = old && old.classList && old.classList.contains("wf-name-input") ? [old.selectionStart, old.selectionEnd] : null;
    input.type = "text"; input.value = s.text; input.maxLength = max; input.disabled = !!s.busy; input.spellcheck = false; input.autocomplete = "off";
    input.setAttribute("aria-label", `도구 「${o.base}」 의 이름`);
    input.placeholder = o.base;
    input.addEventListener("input", () => { s.text = input.value; });
    input.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); stop(s); s.focus = "go"; o.redraw(); } });
    save.type = "submit"; save.disabled = !!s.busy;
    cancel.type = "button"; cancel.disabled = !!s.busy;
    cancel.addEventListener("click", () => { stop(s); s.focus = "go"; o.redraw(); });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = input.value.replace(/\s+/g, " ").trim();
      if (s.busy) return;
      if (name === o.name) { stop(s); s.focus = "go"; o.redraw(); return; } // 그대로 — 닫기만
      send(o, name === o.base ? "" : name); // 빈 이름 · 기본 이름 = 기본 이름으로 되돌림
    });
    const acts = h("div", "wf-name-acts");
    acts.append(save);
    if (renamed) {
      const back = h("button", "btn sm", "기본 이름으로");
      back.type = "button"; back.disabled = !!s.busy;
      back.title = `고친 이름을 지우고 기본 이름 「${o.base}」 ${josa(o.base, "으로", "로")} 되돌립니다`;
      back.addEventListener("click", () => { if (!s.busy) send(o, ""); });
      acts.append(back);
    }
    acts.append(cancel);
    form.append(input, acts);
    box.append(form, h("p", "wf-name-hint", `이 도구를 쓰는 모든 워크플로우의 화면에 이 이름으로 보입니다(${max}자까지 · 이 PC 의 설정). 설명 글과 workflow.md 에 적힌 이름은 기본 이름 「${o.base}」 그대로입니다.`));
    if (s.err) { const p = h("p", "wf-name-err", s.err); p.setAttribute("role", "alert"); box.append(p); }
    if (s.focus || was) { // 방금 열었거나(처음 — 이름 전체를 고른다) 고치는 중에 열이 다시 그려졌다(커서를 그 자리에)
      const first = s.focus === true;
      s.focus = false;
      queueMicrotask(() => {
        if (!input.isConnected || input.disabled) return;
        input.focus({ preventScroll: !first });
        if (first) input.select(); else if (was) { try { input.setSelectionRange(was[0], was[1]); } catch { /* 고르지 못해도 고치기는 된다 */ } }
      });
    }
    return box;
  }

  window.WfNames = { row, start };
})();
