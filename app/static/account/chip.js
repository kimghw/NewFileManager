// 상단 바의 계정 단추 · 로그인이 풀린 화면을 로그인으로(spec_계정 ② §4) — `/` · `/workflow` · `/agents` 가 읽는다. 혼자 선다(다른 스크립트의 이름에 기대지 않는다).
// 로그인 문이 꺼져 있으면(GET /api/account/me 의 on 이 거짓) 아무것도 그리지 않는다.
(() => {
  const real = window.fetch;
  window.fetch = async (...args) => {   // 로그인 문의 401(머리말 X-Login) = 로그인이 풀림 → 로그인 화면으로(끝나면 이 주소로 돌아온다)
    const r = await real(...args);
    if (r.status === 401 && r.headers.get("X-Login")) location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search + location.hash);
    return r;
  };
  real("/api/account/me").then(r => r.json()).then(me => {
    const bar = document.querySelector("header.topbar");
    if (!me.on || !me.name || !bar) return;
    const a = document.createElement("a");
    a.className = "btn acct-chip";
    a.id = "accountLink";
    a.href = "/account";
    a.target = "_blank";
    a.rel = "noopener";
    a.draggable = false;
    a.title = "계정 — 비밀번호 바꾸기 · 로그아웃" + (me.admin ? " · 가입 승인" : "");
    a.style.cssText = "display:inline-flex;align-items:center;gap:5px;max-width:11em;margin-left:6px;overflow:hidden;text-decoration:none;color:inherit";
    a.textContent = me.name;
    if (me.admin && me.pending) {
      const n = document.createElement("span");
      n.textContent = me.pending;
      n.title = `승인 대기 ${me.pending}명`;
      n.style.cssText = "padding:0 6px;border-radius:999px;background:var(--warn-soft);color:var(--warn);font-size:11.5px;font-weight:600";
      a.append(n);
    }
    bar.append(a);
  }).catch(() => {});
})();
