// 계정 화면(/account — 내 비밀번호 · 로그아웃 / 관리자: 승인 대기 · 계정 목록 — spec_계정 ② §1 · §4). 혼자 선다(app.js 를 읽지 않는다).
(() => {
  const $ = id => document.getElementById(id);
  const api = async (url, method = "GET", body) => {
    const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body && JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "요청을 처리하지 못했습니다");
    return d;
  };
  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
  const STATE = { pending: "승인 대기", approved: "승인됨", blocked: "막음" };
  const when = t => t ? new Date(t * 1000).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" }) : "";
  const act = (label, fn, cls = "") => el("button", { className: "btn sm " + cls, type: "button", textContent: label,
    onclick: async () => {
      try { $("adMsg").textContent = ""; await fn(); await list(); } catch (e) { $("adMsg").textContent = e.message; }
    } });
  const user = name => "/api/account/users/" + encodeURIComponent(name);
  const put = (name, body) => api(user(name), "PUT", body);
  const drop = (name, ask) => confirm(ask) ? api(user(name), "DELETE") : null;
  const table = rows => rows.length ? el("table", { className: "acct-list" }, el("tbody", {}, ...rows)) : el("p", { className: "acct-empty", textContent: "없습니다" });

  async function list() {
    const users = (await api("/api/account/users")).users;
    const pend = users.filter(u => u.state === "pending"), rest = users.filter(u => u.state !== "pending");
    $("pendN").textContent = pend.length + "명";
    $("allN").textContent = rest.length + "명";
    $("pending").replaceChildren(table(pend.map(u => el("tr", {}, el("td", { textContent: u.name }), el("td", { textContent: when(u.created) }), el("td", {},
      act("승인", () => put(u.name, { state: "approved" }), "primary"),
      act("거절", () => drop(u.name, `「${u.name}」 의 가입 신청을 거절합니다(신청을 지움).`), "danger"))))));
    $("all").replaceChildren(table(rest.map(u => el("tr", {},
      el("td", { textContent: u.name + (u.admin ? " (관리자)" : "") }),
      el("td", {}, el("span", { className: "acct-tag " + u.state, textContent: STATE[u.state] })),
      el("td", {}, ...(u.admin ? [] : [
        u.state === "blocked" ? act("풀기", () => put(u.name, { state: "approved" })) : act("막기", () => put(u.name, { state: "blocked" })),
        act("비밀번호 초기화", () => {
          const p = prompt(`「${u.name}」 의 새 비밀번호(4자 이상)`);
          return p ? put(u.name, { password: p }) : null;
        }),
        act("지우기", () => drop(u.name, `「${u.name}」 계정을 지웁니다.\n그 계정의 작업 폴더는 지우지 않습니다(같은 이름으로 다시 가입하면 이어집니다).`), "danger")]))))));
  }

  $("logout").onclick = async () => {
    await api("/api/account/logout", "POST").catch(() => {});
    location.href = "/login";
  };
  $("pwForm").onsubmit = async e => {
    e.preventDefault();
    const msg = $("pwMsg");
    try {
      await api("/api/account/password", "POST", { old: $("old").value, new: $("new").value });
      msg.className = "acct-msg ok";
      msg.textContent = "바꿨습니다";
      e.target.reset();
    } catch (err) {
      msg.className = "acct-msg";
      msg.textContent = err.message;
    }
  };
  api("/api/account/me").then(me => {
    if (!me.name) {
      $("who").textContent = me.on ? "" : "로그인이 꺼져 있습니다(이 서버는 계정 없이 돕니다)";
      return;
    }
    $("who").textContent = me.name + (me.admin ? " · 관리자" : "") + (me.local ? " · 이 PC 에서 바로 접속(로그인 없이 관리자)" : "");
    if (me.admin) {
      $("admin").hidden = false;
      list().catch(e => { $("adMsg").textContent = e.message; });
    }
  });
})();
