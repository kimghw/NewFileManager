// 로그인 · 가입 신청(/login — spec_계정 ② §1 · §4). 혼자 선다(app.js 를 읽지 않는다).
(() => {
  const $ = id => document.getElementById(id);
  let join = false;
  const say = (text, ok) => { $("msg").textContent = text; $("msg").classList.toggle("ok", !!ok); };
  const mode = on => {
    join = on;
    $("tabLogin").setAttribute("aria-selected", String(!on));
    $("tabJoin").setAttribute("aria-selected", String(on));
    $("pw2Row").hidden = !on;
    $("pw").autocomplete = on ? "new-password" : "current-password";
    $("go").textContent = on ? "가입 신청" : "로그인";
    say("");
  };
  $("tabLogin").onclick = () => mode(false);
  $("tabJoin").onclick = () => mode(true);
  $("form").onsubmit = async e => {
    e.preventDefault();
    const name = $("name").value.trim().toLowerCase(), password = $("pw").value;
    if (join && password !== $("pw2").value) return say("비밀번호가 서로 다릅니다");
    $("go").disabled = true;
    try {
      const r = await fetch(join ? "/api/account/join" : "/api/account/login",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, password }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) return say(typeof d.detail === "string" ? d.detail : "요청을 처리하지 못했습니다");
      if (join) {
        mode(false);
        $("pw").value = $("pw2").value = "";
        return say("신청했습니다 — 관리자가 승인하면 로그인할 수 있습니다", true);
      }
      const next = new URLSearchParams(location.search).get("next") || "/";
      location.href = next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";   // 이 사이트 안의 길만
    } catch {
      say("서버에 닿지 못했습니다");
    } finally {
      $("go").disabled = false;
    }
  };
  $("name").focus();
})();
