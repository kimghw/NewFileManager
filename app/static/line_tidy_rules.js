// 조립 화면의 「도구 설명」 열 — 「줄 정리」 의 「규칙」 절(spec_줄정리 ② §6 — 2026-11-23 사용자 "이 규칙도 관리할 수 있도록 도구에서 볼수 있게 해줘").
// 규칙은 이 PC 의 설정이다(이 도구를 쓰는 모든 워크플로우가 같이 씀) — 조립 폼의 저장 · 취소와 따로 바로 저장된다(「이름 바꾸기」 와 같은 범위).
// 이 파일은 workflow.js 없이 혼자 선다 — workflow.js 의 훅은 하나: helpUnitEl 에서 줄 key 가 lineTidy 면 `LineTidyRules.sec(redraw)` 를 설명 끝에 붙인다.
// 서버: GET /api/line-tidy/rules → {rules, defaults, defs[{key, default, lo, hi, unit, name, text}], updated, text} · PUT {rules} · DELETE(기본값으로) — app/line_tidy_api.py(거절 글은 서버의 것 그대로).
(() => {
  "use strict";
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const S = { data: null, draft: {}, busy: false, err: "", msg: "", loading: null }; // 다시 그려도 고치던 숫자 · 알림이 남는다(열은 자주 다시 선다)

  async function call(method, body) {
    const r = await fetch("/api/line-tidy/rules", { method, headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((typeof data.detail === "string" && data.detail) || `HTTP ${r.status}`);
    return data;
  }

  function load(redraw) {
    if (S.data || S.loading) return;
    S.loading = call("GET").then((d) => { S.data = d; }).catch((e) => { S.err = `규칙을 읽지 못했습니다 — ${e.message}`; }).finally(() => { S.loading = null; redraw(); });
  }

  async function save(redraw, reset) {
    S.busy = true; S.err = ""; S.msg = "";
    redraw();
    try {
      S.data = reset ? await call("DELETE") : await call("PUT", { rules: { ...S.data.rules, ...S.draft } });
      S.draft = {};
      S.msg = reset ? "기본값으로 되돌렸습니다 — 이 PC 의 모든 워크플로우에 바로 쓰입니다" : "저장했습니다 — 이 PC 의 모든 워크플로우에 바로 쓰입니다";
    } catch (e) {
      S.err = e.message;
    }
    S.busy = false;
    redraw();
  }

  function sec(redraw) { // → 「규칙」 절 요소(읽는 중이면 그 한 줄)
    const box = h("section", "wf-help-sec wf-lt-rules");
    box.dataset.ltRules = "1";
    box.append(h("h5", "", "규칙"));
    if (!S.data) {
      load(redraw);
      box.append(h("p", "wf-muted", S.err || "규칙을 읽는 중…"));
      return box;
    }
    box.append(h("p", "wf-lt-note", "이 PC 의 설정입니다 — 이 도구를 쓰는 모든 워크플로우가 같이 씁니다. 글자 수는 한글 · 영문 · 숫자만 셉니다."));
    const list = h("ul", "wf-lt-list"), D = S.data, dirty = Object.keys(S.draft).length > 0;
    for (const d of D.defs) {
      const li = h("li", "wf-lt-row"), top = h("label", "wf-lt-top"), inp = h("input", "wf-lt-num"), id = `wfLt-${d.key}`;
      const val = d.key in S.draft ? S.draft[d.key] : D.rules[d.key];
      inp.type = "number"; inp.id = id; inp.min = d.lo; inp.max = d.hi; inp.step = 1; inp.value = val; inp.disabled = S.busy;
      inp.dataset.ltKey = d.key;
      inp.setAttribute("aria-describedby", `${id}-t`);
      inp.addEventListener("input", () => {
        const n = Number(inp.value);
        if (inp.value !== "" && Number.isInteger(n) && n !== D.rules[d.key]) S.draft[d.key] = n; else delete S.draft[d.key];
        const act = box.querySelector("[data-lt-save]");
        if (act) act.disabled = S.busy || !Object.keys(S.draft).length;
      });
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && Object.keys(S.draft).length) { e.preventDefault(); save(redraw, false); } });
      top.htmlFor = id;
      top.append(h("b", "", d.name), inp, h("span", "wf-lt-unit", d.unit));
      if (D.rules[d.key] !== D.defaults[d.key]) top.append(h("span", "wf-lt-def", `기본 ${D.defaults[d.key]}${d.unit}`));
      const t = h("p", "wf-lt-text", d.text); t.id = `${id}-t`;
      li.append(top, t);
      list.append(li);
    }
    box.append(list);
    const acts = h("div", "wf-lt-acts"), ok = h("button", "btn sm primary", S.busy ? "저장하는 중…" : "규칙 저장"), back = h("button", "btn sm", "기본값으로");
    ok.type = back.type = "button";
    ok.dataset.ltSave = "1";
    ok.disabled = S.busy || !dirty;
    back.disabled = S.busy || (!dirty && D.defs.every((d) => D.rules[d.key] === D.defaults[d.key]));
    ok.addEventListener("click", () => save(redraw, false));
    back.addEventListener("click", () => save(redraw, true));
    acts.append(ok, back);
    box.append(acts);
    if (S.err || S.msg) { const p = h("p", S.err ? "wf-lt-err" : "wf-lt-msg", S.err || S.msg); p.setAttribute("role", S.err ? "alert" : "status"); box.append(p); }
    return box;
  }

  window.LineTidyRules = { sec, reset: () => { S.data = null; S.draft = {}; S.err = ""; S.msg = ""; } };
})();
