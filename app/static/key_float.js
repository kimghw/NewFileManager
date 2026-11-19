"use strict";
/* 떠 있는 색 설명(index.html #viewer 안의 .key-float — 지금 #zonesKey 「편집 구역」 · #divKey 「구분 기준 자리」: design.md §4 「색 설명은 문서 위에 떠 있는 상자로」).
   2026-11-19 사용자 "구분자리, 편집구역은 각각 아이콘으로 두고 클릭 하면 문서 상단에 플로팅으로 띄어줘, 움직일 수 있게" — 전에는 두 설명이 문서 이름 줄에 있어 줄이 두 줄로 꺾이고 문서 이름을 밀어냈다.
   · 켜고 끄기는 이름 줄의 아이콘 그대로(doc_quick.js #nameZones · #nameDivMarks — 그 표시를 켜면 설명이 뜨고 끄면 사라진다). 내용을 그리는 것도 전의 함수 그대로다(zones.js zonesKeyDraw · app.js divKeyDraw) —
     이 파일은 **자리**만 맡는다: 놓기 · 끌어 옮기기 · 기억.
   · 제자리 = 문서 창(#viewer) 위 가운데. 둘이 함께 뜨면 한 줄에 나란히(편집 구역 · 구분 기준 자리), 창이 좁아 안 들어가면 아래로 쌓는다.
   · 상자의 빈 곳(왼쪽 손잡이 · 이름 · 단추가 아닌 칩)을 끌면 옮겨진다 — 문서 창 안에서만. 3px 넘게 움직였을 때만 옮긴 것으로 본다(누름은 그대로 누름).
     옮긴 자리는 이 브라우저에 기억(nfm.keyFloat — 상자마다 문서 창 왼쪽 위에서의 px). 창이 줄어 밖으로 나가면 보이는 자리만 안으로 당기고 기억한 값은 그대로 둔다(창이 넓어지면 돌아간다).
   · 두 번 누르면 제자리(기억을 지움).
   app.js · zones.js 다음에 읽힌다($ 를 쓴다). 그 둘은 설명을 다시 그린 뒤 keyFloatPlace() 를 부른다(내용이 바뀌면 폭이 바뀐다). */
const KEY_FLOAT = { ids: ["zonesKey", "divKey"], store: "nfm.keyFloat", at: {}, edge: 6, top: 8, gap: 6 }; // ids = 제자리에 놓는 차례(왼쪽 → 오른쪽 · 위 → 아래)
const KEY_FLOAT_TIP = "끌어서 옮기기 · 두 번 누르면 제자리로";

function keyFloatSave() { try { if (Object.keys(KEY_FLOAT.at).length) localStorage.setItem(KEY_FLOAT.store, JSON.stringify(KEY_FLOAT.at)); else localStorage.removeItem(KEY_FLOAT.store); } catch { /* 기억만 안 함 */ } }

function keyFloatPut(box, x, y, host) { // 문서 창 안으로 당겨 놓는다 — x · y = 문서 창 왼쪽 위에서의 px
  const e = KEY_FLOAT.edge, W = host.clientWidth, H = host.clientHeight;
  box.style.left = `${Math.round(Math.max(e, Math.min(x, W - box.offsetWidth - e)))}px`;
  box.style.top = `${Math.round(Math.max(e, Math.min(y, H - box.offsetHeight - e)))}px`;
}

function keyFloatPlace() { // 보이는 상자를 놓는다 — 옮긴 것은 기억한 자리, 아닌 것은 제자리(문서 위 가운데). 설명을 다시 그린 뒤 · 문서 창의 크기가 바뀐 뒤 · 끌기를 마친 뒤
  const host = $("viewer");
  if (!host || !host.clientWidth || !host.clientHeight) return;
  const boxes = KEY_FLOAT.ids.map((id) => $(id)).filter((b) => b && !b.hidden && b.offsetWidth > 0);
  const free = boxes.filter((b) => !KEY_FLOAT.at[b.id]), g = KEY_FLOAT.gap, W = host.clientWidth;
  const total = free.reduce((s, b) => s + b.offsetWidth, 0) + g * Math.max(0, free.length - 1);
  if (total <= W - 2 * KEY_FLOAT.edge) { let x = (W - total) / 2; for (const b of free) { keyFloatPut(b, x, KEY_FLOAT.top, host); x += b.offsetWidth + g; } } // 한 줄에 나란히
  else { let y = KEY_FLOAT.top; for (const b of free) { keyFloatPut(b, (W - b.offsetWidth) / 2, y, host); y += b.offsetHeight + g; } } // 안 들어가면 아래로 쌓음
  for (const b of boxes) { const at = KEY_FLOAT.at[b.id]; if (at) keyFloatPut(b, at.x, at.y, host); }
}

function keyFloatHome(box) { // 제자리로 — 기억을 지운다
  if (!KEY_FLOAT.at[box.id]) return;
  delete KEY_FLOAT.at[box.id];
  box.classList.remove("kf-moved");
  keyFloatSave();
  keyFloatPlace();
}

function keyFloatGrip() { // 상자 맨 앞의 손잡이(점 여섯) — 설명을 그리는 함수가 맨 먼저 넣는다. 끌기는 상자의 빈 곳 어디서나 되고, 이 그림은 「옮길 수 있다」 를 보이는 표시 + 도움말 자리
  const g = document.createElement("span");
  g.className = "kf-grip";
  g.title = KEY_FLOAT_TIP;
  g.setAttribute("aria-hidden", "true");
  return g;
}

function keyFloatBind(box) {
  const ctl = (t) => !!(t && t.closest && t.closest("button, a, input, select, textarea")); // 조작(칩 단추 · 노트)은 끌기의 손잡이가 아니다
  if (KEY_FLOAT.at[box.id]) box.classList.add("kf-moved");
  box.addEventListener("pointerdown", (e) => {
    const host = $("viewer");
    if (e.button !== 0 || ctl(e.target) || !host) return;
    e.preventDefault(); // 글이 골라지거나 문서의 커서가 옮겨지지 않게
    const hr = host.getBoundingClientRect(), r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top, x0 = e.clientX, y0 = e.clientY;
    let moved = false;
    try { box.setPointerCapture(e.pointerId); } catch { /* 이미 끝난 누름 */ }
    const move = (ev) => {
      if (!moved && Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 3) return;
      if (!moved) { moved = true; box.classList.add("kf-moving"); }
      keyFloatPut(box, ev.clientX - dx - hr.left, ev.clientY - dy - hr.top, host);
    };
    const up = () => {
      box.removeEventListener("pointermove", move);
      box.removeEventListener("pointerup", up);
      box.removeEventListener("pointercancel", up);
      box.classList.remove("kf-moving");
      if (!moved) return;
      KEY_FLOAT.at[box.id] = { x: box.offsetLeft, y: box.offsetTop };
      box.classList.add("kf-moved");
      keyFloatSave();
    };
    box.addEventListener("pointermove", move);
    box.addEventListener("pointerup", up);
    box.addEventListener("pointercancel", up);
  });
  box.addEventListener("dblclick", (e) => { if (!ctl(e.target)) keyFloatHome(box); });
}

(function keyFloatInit() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY_FLOAT.store) || "{}");
    for (const id of KEY_FLOAT.ids) if (v && v[id] && Number.isFinite(v[id].x) && Number.isFinite(v[id].y)) KEY_FLOAT.at[id] = { x: v[id].x, y: v[id].y };
  } catch { /* 기억 없음 */ }
  for (const id of KEY_FLOAT.ids) { const b = $(id); if (b) keyFloatBind(b); }
  const host = $("viewer");
  if (host && typeof ResizeObserver === "function") new ResizeObserver(() => keyFloatPlace()).observe(host); // 패널 · 문서 옆 열을 여닫거나 창 크기를 바꾸면 다시(문서 창이 다시 보일 때도)
  else window.addEventListener("resize", keyFloatPlace);
  keyFloatPlace();
})();
