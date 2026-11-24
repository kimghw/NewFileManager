"use strict";
/* 상단 바 「문서 라이브러리」 아이콘(#libraryLink — 2026-11-24 사용자 「여기 라이브러리 아이콘을 추가해줘」 · spec_양식작성 ② §2).
   문서 라이브러리 = 따로 선 서버(doclib · 8121). 주소는 8114 서버가 안다(GET /api/doclib/where → {url, alive, why} — env NFM_DOCLIB_URL).
   · 그냥 누름: 그 서버가 켜져 있는지 먼저 보고 새 탭에 연다 · 꺼져 있으면 열지 않고 알린다(8114 는 그 서버를 저절로 띄우지 않는다 — 띄우개 tools/start_doclib.ps1).
   · Ctrl · Shift · 가운데 누름: 링크 그대로(href 는 처음 읽은 주소로 맞춰 둔다).
   기대는 이름: app.js — api · toast. */
(function () {
  const a = document.getElementById("libraryLink");
  if (!a) return;
  const where = () => api("/api/doclib/where");
  where().then((w) => { if (w && w.url) a.href = `${w.url}/`; }).catch(() => {});
  a.addEventListener("click", async (e) => {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    let w;
    try { w = await where(); } catch (err) { toast(`문서 라이브러리 주소를 읽지 못했습니다: ${err.message}`, true); return; }
    if (!w.alive) { toast(`문서 라이브러리 서버가 꺼져 있습니다 — ${w.why || w.url} · 띄우개 tools/start_doclib.ps1 로 띄운 뒤 다시 누르세요`, true); return; }
    a.href = `${w.url}/`;
    window.open(a.href, "_blank", "noopener");
  });
})();
