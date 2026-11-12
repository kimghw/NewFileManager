"use strict";
// 누른 자리 따라 보기(spec_작업 ② §12 「누른 자리 따라 보기」 — 2026-11-12 사용자 "작성된 부분은 클릭하면 상대 페이지 바로 보여주기 기능을 넣어줘, 이걸 끄고 킬 수 있게 해주고"). app.js·gather.js 다음에 읽는다.
// 이관(사업계획서 → 연차보고서)에서 **연차보고서의 자리를 누르면** 다른 면이 그 자리의 원본(사업계획서의 그 문단·표 칸)을 바로 보여 준다 — 넣은 내용이 어디서 왔는지 한 번에 본다.
// - 지도 = GET /api/docs/{연차보고서}/merge-links/origins → {map{목적 id: 원본 id}}(app/merge_origins.py — 넣기 계획과 같은 규칙으로 지금 두 문서의 짝을 다시 셈한 것. 문서는 안 바뀐다).
//   누른 곳에서 바깥으로(문단 → 칸 → 표 → 바깥 칸 …) 올라가며 처음 맞는 id 의 원본 자리로 간다. 짝이 없는 곳(구분 기준 반영이 만든 양식 글 · 사람이 직접 쓴 글)은 아무 일도 없다.
// - 어느 면에서 누르든: 연차보고서가 첫째 면(고치는 문서)이면 둘째 면(사업계획서)이 움직이고, 연차보고서가 둘째 면이면 첫째 면(사업계획서)이 움직인다. 둘째 면 화면(PEEK)은 누른 id 만 바깥에 넘긴다.
// - 따라가는 면은 **스크롤만** 한다(초점을 안 옮긴다 — 누른 문단에서 바로 이어 쓸 수 있다). 둘째 면이 닫혔거나 띠로 접혀 있으면 안 따라간다(다시 열지 않는다).
// - 켜고 끄기 = 둘째 면 머리의 「따라 보기」 단추(#peerFollow — 눌림 = 켬). 이 브라우저에 기억(nfm.peerFollow — 기본 켬). 이관의 두 칸이 차 있을 때만 보인다(취합에는 아직 없다).
// - 지도는 둘째 면이 뜰 때 한 번 미리 읽고, 문단 수가 달라졌을 때(내용 반영 · 실행 취소 · 줄 넣기·지우기)만 다시 읽는다 — 글만 고친 것으로는 다시 안 읽는다(자리 id 는 그대로 · 서버가 몇 초 문서를 잡는다).
//   다시 읽는 동안에는 가진 지도로 바로 가고, 거기 없는 자리만 새 지도를 기다린다.
const FOLLOW_KEY = "nfm.peerFollow";
const FOLLOW_AGAIN = 700; // 같은 자리를 이 안에 또 누르면(두 번 누르기) 다시 안 간다(ms)
const follow = { on: (() => { try { return localStorage.getItem(FOLLOW_KEY) !== "off"; } catch { return true; } })(),
  pair: "", key: "", map: null, busy: null, busyKey: "", missing: false, failAt: 0, seq: 0, last: "", lastAt: 0, peerSeq: 0 }; // pair = 지도의 문서 쌍 · key = 그때의 문서 꼴(followKey)

function followPair() { // 이관의 두 문서 → {to: 목적(연차보고서), from: 원본(사업계획서)} | null(이관이 아님 · 칸이 빔 · 취합)
  if (PEEK || !state.id || gatherOn()) return null;
  const slots = taskSlots();
  if (!slots || !slots.includes("plan") || !slots.includes("report")) return null;
  const to = taskSlotDoc("report"), from = taskSlotDoc("plan");
  return to && from && to.id !== from.id ? { to, from } : null;
}
const followPairKey = (pair) => `${pair.to.id}|${pair.from.id}`;
const followKey = (pair) => `${followPairKey(pair)}|${state.id}|${state.byId.size}`; // 문단 수가 달라지면 다시 읽는다(글만 고친 것은 그대로)
const followPeerOpen = () => { const col = $("peerCol"); return !col.hidden && !col.classList.contains("folded"); };

function followLoad(pair) { // 지도를 읽는다(같은 것을 읽는 중이면 그 약속) → 지도 | null(못 읽음)
  const key = followKey(pair);
  if (follow.busy && follow.busyKey === key) return follow.busy;
  const epoch = state.epoch;
  follow.busyKey = key;
  const p = api(`/api/docs/${pair.to.id}/merge-links/origins`).then((r) => {
    if (epoch !== state.epoch) return null;
    Object.assign(follow, { pair: followPairKey(pair), key, map: (r && r.map) || {}, missing: false, failAt: 0 });
    return follow.map;
  }).catch((e) => {
    if (epoch !== state.epoch) return null;
    if (e.status === 404 || e.status === 405) { // 끝점이 없는 서버(재시작 전) — 한 번만 알리고 그만 묻는다
      if (!follow.missing) toast("「따라 보기」 는 서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)");
      follow.missing = true;
    } else follow.failAt = Date.now();
    return null;
  }).finally(() => { if (follow.busy === p) follow.busy = null; followBtnSync(); });
  follow.busy = p;
  return p;
}

function followIds(target) { // 누른 곳 → 자리 id(안 → 밖: 문단 · 그림 → 칸 → 표 → 바깥 칸 → 바깥 표 …)
  const out = [], doc = $("doc");
  for (let n = target; n && n !== doc; n = n.parentElement) {
    const d = n.dataset || {};
    for (const id of [d.id, d.cell, d.tbl]) if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

function followShow(id) { // 이 화면의 문서를 그 자리(문단 · 칸 · 표 · 그림 id)로 — 스크롤만(초점은 그대로) → 갔나
  const q = CSS.escape(id);
  for (const host of document.querySelectorAll(`#doc .para[data-id="${q}"], #doc td[data-cell="${q}"], #doc table.tbl[data-tbl="${q}"], #doc [data-id="${q}"]`)) {
    const p = host.matches(".para") ? host : host.querySelector(".para"); // 쪽에 걸쳐 나뉜 칸·표는 조각이 여럿 — 문단이 든 첫 조각
    if (p) { scrollToBlock(p.dataset.id, false); return true; }
  }
  const host = document.querySelector(`#doc [data-id="${q}"], #doc table.tbl[data-tbl="${q}"]`); // 문단이 없는 것(그림)
  if (host) host.scrollIntoView({ block: "center", behavior: "smooth" });
  return !!host;
}
function followPeekId() { return state.id; } // 둘째 면 화면에서: 바깥 창이 「그 문서를 다 그렸나」 를 물을 때

function followPeer(wid, id) { // 둘째 면을 그 문서의 탭으로(다른 문서가 떠 있으면 바꾼다) → 다 그렸으면 그 자리로
  if (!followPeerOpen()) return;
  const seq = ++follow.peerSeq;
  if (peerShown() !== wid) { peerPick = wid; peerKind = null; peerSync(); if (peerShown() !== wid) return; }
  const t0 = Date.now(), tick = () => {
    if (seq !== follow.peerSeq || peerShown() !== wid || Date.now() - t0 > 20000) return;
    let ready = false;
    try { const w = $("peerFrame").contentWindow; ready = w.followPeekId() === wid && !!w.document.querySelector("#doc .sheet .para"); if (ready) w.followShow(id); } catch { ready = false; }
    if (!ready) setTimeout(tick, 200);
  };
  tick();
}

async function followClick(wid, ids) { // 문서 wid 의 자리 ids(안 → 밖)를 눌렀다 — 바깥 창에서만 돈다(둘째 면 화면은 parent.followClick 을 부른다)
  if (PEEK || !follow.on || follow.missing || !ids || !ids.length) return;
  const pair = followPair();
  if (!pair || wid !== pair.to.id) return; // 연차보고서(내용이 들어간 문서)의 자리만
  const where = wid === state.id ? "peer" : state.id === pair.from.id && peerShown() === wid ? "main" : ""; // 원본을 보일 면
  if (!where || (where === "peer" && !followPeerOpen())) return;
  const seq = ++follow.seq, find = (m) => (m ? ids.map((i) => m[i]).find(Boolean) : null) || null;
  const have = follow.pair === followPairKey(pair) ? follow.map : null, fresh = !!have && follow.key === followKey(pair);
  let hit = find(have);
  if (!fresh && Date.now() - follow.failAt > 10000) {
    const p = followLoad(pair); // 가진 지도가 없거나 문서 꼴이 달라졌다 — 새로 읽는다(가진 지도에 있는 자리는 기다리지 않고 바로)
    if (!hit) { hit = find(await p); if (seq !== follow.seq) return; }
  }
  if (!hit || (hit === follow.last && Date.now() - follow.lastAt < FOLLOW_AGAIN)) return;
  follow.last = hit;
  follow.lastAt = Date.now();
  if (where === "peer") followPeer(pair.from.id, hit); else followShow(hit);
}

function followSet(on) {
  follow.on = !!on;
  try { localStorage.setItem(FOLLOW_KEY, on ? "on" : "off"); } catch { /* 기억만 안 함 */ }
  followBtnSync();
  if (on) followWarm();
}
function followBtnSync() { // 단추의 보임·눌림·도움말 — 둘째 면이 바뀔 때(#peerFrame load) · 켜고 끌 때 · 지도를 읽은 뒤
  const b = $("peerFollow");
  if (!b) return;
  const pair = followPair();
  b.hidden = !pair;
  b.classList.toggle("on", follow.on);
  b.setAttribute("aria-pressed", String(follow.on));
  const n = follow.map && pair && follow.pair === followPairKey(pair) ? Object.keys(follow.map).length : null;
  b.title = (follow.on ? "따라 보기 켜짐 — 누르면 끕니다" : "따라 보기 꺼짐 — 누르면 켭니다")
    + "\n켜 두면 연차보고서에서 내용이 들어간 곳(문단·표 칸)을 누를 때 다른 면이 그 내용의 원본 자리(사업계획서의 그 쪽)를 바로 보여 줍니다. 누른 문단은 그대로 고칠 수 있습니다."
    + (follow.missing ? "\n서버를 다시 시작한 뒤에 쓸 수 있습니다(새 기능)" : n != null ? `\n이어진 자리 ${n.toLocaleString("ko-KR")}곳` : "");
}
function followWarm() { // 미리 읽기 — 둘째 면이 떴고 켜져 있을 때(첫 누름이 기다리지 않게)
  const pair = followPair();
  if (!pair || !follow.on || follow.missing || !followPeerOpen() || Date.now() - follow.failAt < 10000) return;
  if (follow.pair === followPairKey(pair) && follow.key === followKey(pair)) return;
  followLoad(pair);
}

(function followBind() {
  $("doc").addEventListener("click", (e) => {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    if (e.target.closest("button, a, input, select, .sheet-label")) return; // 표 손잡이·쪽 꼬리표 같은 문서 위 단추
    const sel = getSelection();
    if (sel && !sel.isCollapsed) return; // 글을 끌어 고른 것 — 누른 것이 아니다
    const ids = followIds(e.target);
    if (!ids.length) return;
    if (!PEEK) followClick(state.id, ids);
    else { try { parent.followClick(state.id, ids); } catch { /* 바깥이 아직 준비 전 */ } }
  });
  if (PEEK) return;
  const b = $("peerFollow");
  if (b) b.onclick = () => { followSet(!follow.on); toast(follow.on ? "따라 보기 켬 — 연차보고서에서 내용이 들어간 곳을 누르면 다른 면이 원본 자리를 보여 줍니다" : "따라 보기 끔"); };
  $("peerFrame").addEventListener("load", () => { followBtnSync(); setTimeout(followWarm, 1500); }); // 둘째 면의 문서가 뜸·바뀜 — 그 화면이 문서를 읽기 시작한 뒤에
  followBtnSync();
})();
