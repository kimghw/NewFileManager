"use strict";
/* 앱으로 설치(PWA) — spec_hwpx_웹편집 ② §9 「앱으로 설치」 · design.md §9. app.js 다음에 읽는다(기대는 것: $ · toast — 없어도 돈다).
   하는 일: 브라우저(Chrome·Edge)가 이 화면을 앱으로 설치할 수 있다고 알려 주면(beforeinstallprompt) 상단 바 「에이전트 설정」 다음에 「앱으로 설치」 아이콘을 보이고,
   누르면 브라우저의 설치 창을 띄운다(설치하면 탭·주소창 없는 따로 선 창 — 작업 표시줄·시작 메뉴에서 연다). 설치 조건 = app.webmanifest + 192·512 아이콘(index.html <head>).
   단추가 생기지 않는 때: 이미 앱 창으로 연 화면(display-mode standalone 등) · 이미 설치한 브라우저 · 설치를 모르는 브라우저(Firefox 등) — 브라우저가 알려 주지 않으면 할 수 있는 일이 없어서다.
   설치를 마치면(appinstalled) 단추를 감추고 한 줄 알린다. 설치 창을 닫았으면(dismissed) 단추를 감춘다 — 같은 창은 한 번만 띄울 수 있고, 브라우저가 다시 알려 주면 다시 보인다. */
const appInst = { ev: null };
const appInstStandalone = () => ["standalone", "minimal-ui", "window-controls-overlay", "fullscreen"].some((m) => window.matchMedia(`(display-mode: ${m})`).matches);
const appInstSay = (t) => { if (typeof toast === "function") toast(t); };

function appInstBtn() {
  let b = document.getElementById("installBtn");
  if (b) return b;
  b = document.createElement("button");
  b.className = "btn app-install";
  b.id = "installBtn";
  b.type = "button";
  b.hidden = true;
  b.setAttribute("aria-label", "앱으로 설치");
  b.title = "앱으로 설치 — 이 화면을 탭·주소창 없는 따로 선 창(앱)으로 설치합니다. 작업 표시줄·시작 메뉴에서 바로 열고, 서버(8114)가 켜져 있어야 열립니다";
  // 그림 = 모니터 + 안으로 내려오는 화살표(「이 PC 에 설치」) — 패널 여닫기(오른쪽 열이 있는 창)와 닮지 않게(design.md §9 「닮은 것끼리는 그림을 가른다」)
  b.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    + '<rect x="3" y="3.5" width="18" height="12.5" rx="2"/><path d="M12 16v4.5M8.5 20.5h7M12 6.5v6M9.5 10l2.5 2.5 2.5-2.5"/></svg>';
  b.onclick = appInstGo;
  const before = document.getElementById("panelBtn");
  if (before) before.before(b);
  else { const bar = document.querySelector(".topbar"); if (bar) bar.append(b); }
  return b;
}

function appInstDraw() {
  appInstBtn().hidden = !(appInst.ev && !appInstStandalone());
}

async function appInstGo() {
  const ev = appInst.ev;
  if (!ev) { appInstDraw(); return; }
  appInst.ev = null; // 설치 창은 한 번만 띄울 수 있다
  appInstDraw();
  try {
    await ev.prompt();
    const r = await ev.userChoice;
    if (r && r.outcome === "dismissed") appInstSay("앱 설치를 취소했습니다 — 브라우저 메뉴(Edge: … → 앱 → 이 사이트를 앱으로 설치)에서도 설치할 수 있습니다");
  } catch (e) {
    appInstSay("설치 창을 띄우지 못했습니다 — 브라우저 메뉴(Edge: … → 앱 → 이 사이트를 앱으로 설치)에서 설치하세요");
  }
}

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault(); // 브라우저의 자체 안내 대신 상단 바 단추로
  appInst.ev = e;
  appInstDraw();
});
window.addEventListener("appinstalled", () => {
  appInst.ev = null;
  appInstDraw();
  appInstSay("앱으로 설치했습니다 — 작업 표시줄·시작 메뉴의 「HWPX·DOCX 웹 편집」 으로 엽니다");
});
appInstBtn();
