"use strict";
// 문서에서 고친 곳 보기 — 깃처럼(spec_작업 ② §8 「화면」 「문서에서 — 고친 곳 보기」).
// 2026-11-17 사용자 「웹원문에서 어떤걸 고쳤는지 확인하는 기능을 넣어줘. 지금은 문단으로 표기 되는데. git 처럼 볼 수 있게」 — 전에는 고친 문단이 통째로 주황 바탕이라
// (조정을 반영하면 줄마다 다 주황) 문서만 봐서는 무엇이 바뀌었는지 알 수 없었고, 오른쪽 「고친 문단」 목록과 한 줄씩 맞춰 봐야 했다.
//
// 켜져 있으면(기본 — 도구 줄 ↑↓ 옆 「±」 단추 #ddBtn, 브라우저에 기억) 창 가까이에 있는 고친 문단마다:
//  · 문단 바탕(주황)을 걷고 왼쪽 띠만 남긴다 — 고침 M 주황 · 새 문단 A 초록(옅은 초록 바탕).
//  · 글: 넣은 글자에 초록 바탕, 글자를 지우기만 한 자리는 그 앞뒤 글자에 빨간 물결 밑줄. 문단 DOM 은 건드리지 않는다(CSS Custom Highlight — 편집 상자의 글·커서·readText 가 그대로).
//  · 쪽 오른쪽 여백의 꼬리표: 「M 글 · 2번째 줄」(무엇이 바뀌었나) — 올리면 「− 빈칸 + 묶음 빈칸 · 2번째 줄 원본 16.4mm → 지금 14mm」(어떻게 — 값마다 이름), 누르면 「고친 문단」 목록의 그 항목(되돌리기는 거기서).
//    줄의 자리는 서식 값(왼쪽 여백 · 첫 줄)이 아니라 줄이 시작하는 자리(「앞 여백」 · 「2번째 줄」)로 온다 — 2026-11-17 사용자 「이게 원본이 원래 0은 아닌데」(「첫 줄 0mm → -7.8mm」 가 첫 줄이 옮겨진 것 · 빈칸 폭을 0 으로 잰 것처럼 읽혔다).
// 끄면 전처럼 문단 바탕만.
//
// 기대는 app.js 의 이름: state(id · epoch · edited · kinds · original · byId · sections · base) · $ · el · readText · LS · PEEK · api · baseWho · showTab · drawEdits · gutterSync ·
// PX_PER_MM · DEFAULT_PAGE. app.js 가 부르는 것(typeof 검사 뒤): ddSync(고친 문단·글이 바뀜 — updateEdits) · ddDraw(쪽을 다시 나눔·배율 — paginate · flowSettle · tplMarksDraw) · ddReset(다른 문서).
// 성능: 문서 전체에 클래스를 걸지 않는다(#doc · body 에 표시 클래스 없음) — 창 가까이(위아래 600px)의 고친 문단만 셈하고, 창을 벗어나면 걷는다(고친 문단이 수천이어도 같다).
const DD = {
  on: true,
  io: null, // 창 가까이에 온 고친 문단을 알려 주는 관찰자(#scroller)
  seen: new WeakSet(), // 관찰자에 맡긴 문단 요소
  vis: new Set(), // 창 가까이에 있는 문단 요소
  marks: new Map(), // 문단 요소 → { kind, hunks, ins: [Range], del: [Range] }
  dirty: new Set(), // 글을 치고 있는 문단 요소(그것만 다시)
  det: new WeakMap(), // 블록(state.byId 의 값) → 모양 다름 [{label, before, after}] | null(기준에 같은 문단 없음) | "none"(서버 답에 없음) | "fail"
  ask: new Map(), // 모양 값을 물을 문단 id → 블록
  timer: 0, busy: false, raf: 0,
  all: false, // 쪽을 다시 나눔·배율 — 보이는 것 전부 다시(글자 범위가 풀리고 꼬리표 자리가 바뀐다)
  check: false, // 고친 문단·글이 바뀜 — 보이는 것 전부 다시 견줌
  tags: false, // 꼬리표만 다시
  hi: null, // { ins, del } Highlight | false(브라우저가 모름 — 띠와 꼬리표만)
};
const DD_CELLS = 400000; // 바뀐 가운데 글(앞뒤 같은 글을 뺀 곳)의 글자 수 곱이 이보다 크면 한 덩이로 본다(긴 문단을 통째로 바꾼 경우 — 셈이 길어지지 않게)
const DD_KINDS = new Set(["format", "struct"]); // 모양 값을 서버에 묻는 종류(app.js EDET_KINDS 와 같다)
const DD_WS = { " ": "빈칸", " ": "묶음 빈칸", " ": "줄 안 바뀌는 빈칸", "　": "전각 빈칸", "\t": "탭", " ": "줄 바꿈", "\n": "줄 바꿈" };

function ddHi() {
  if (DD.hi !== null) return DD.hi;
  DD.hi = false;
  try {
    if (typeof Highlight === "function" && window.CSS && CSS.highlights) {
      DD.hi = { ins: new Highlight(), del: new Highlight() };
      CSS.highlights.set("nfm-dd-ins", DD.hi.ins);
      CSS.highlights.set("nfm-dd-del", DD.hi.del);
    }
  } catch (e) { DD.hi = false; }
  return DD.hi;
}

// 글의 다름 → 바뀐 곳 [{ at, del, ins }] — at = 지금 글(b)에서의 자리, del = 거기서 지운 글, ins = 거기에 넣은 글. 글자 단위(가장 긴 공통 부분열).
// 사이에 같은 글자가 2자 이하로 낀 덩이는 잇는다(둘 다 지운 글이 있을 때) — 낱말을 바꿨는데 우연히 같은 글자가 한두 자 남아 잘게 갈려 보이지 않게.
function ddDiff(a, b) {
  if (a === b) return [];
  const n = a.length, m = b.length;
  let i = 0;
  while (i < n && i < m && a[i] === b[i]) i++;
  let j = 0;
  while (j < n - i && j < m - i && a[n - 1 - j] === b[m - 1 - j]) j++;
  const x = a.slice(i, n - j), y = b.slice(i, m - j);
  if (!x.length || !y.length || x.length * y.length > DD_CELLS) return [{ at: i, del: x, ins: y }];
  const w = y.length + 1, t = new Uint16Array((x.length + 1) * w);
  for (let p = x.length - 1; p >= 0; p--) {
    for (let q = y.length - 1; q >= 0; q--) t[p * w + q] = x[p] === y[q] ? t[(p + 1) * w + q + 1] + 1 : Math.max(t[(p + 1) * w + q], t[p * w + q + 1]);
  }
  const out = [];
  let p = 0, q = 0, cur = null;
  const open = () => cur || (cur = { at: i + q, del: "", ins: "" });
  while (p < x.length || q < y.length) {
    if (p < x.length && q < y.length && x[p] === y[q]) { if (cur) { out.push(cur); cur = null; } p++; q++; }
    else if (q < y.length && (p === x.length || t[p * w + q + 1] >= t[(p + 1) * w + q])) { const h = open(); h.ins += y[q]; q++; }
    else { const h = open(); h.del += x[p]; p++; }
  }
  if (cur) out.push(cur);
  const merged = [];
  for (const h of out) {
    const last = merged[merged.length - 1];
    if (last && last.del && h.del && h.at - (last.at + last.ins.length) <= 2) { // 둘 다 지운 글이 있을 때만(고쳐 쓴 낱말) — 가까이에 넣기만 한 두 곳은 따로 둔다(사이 글자가 「넣은 글」 로 보이지 않게)
      const same = b.slice(last.at + last.ins.length, h.at);
      last.del += same + h.del;
      last.ins += same + h.ins;
    } else merged.push(h);
  }
  return merged;
}

function ddPoints(p) { // 문단의 글 조각 [{ node, at, len }] — readText 와 같은 셈(글 노드 · <br> 과 줄 상자 사이는 한 글자)
  const out = [];
  let at = 0, nl = true;
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === Node.TEXT_NODE) {
        if (!c.data.length) continue;
        out.push({ node: c, at, len: c.data.length });
        at += c.data.length;
        nl = c.data.endsWith("\n");
      } else if (c.nodeName === "BR") { at += 1; nl = true; }
      else {
        if ((c.nodeName === "DIV" || c.nodeName === "P") && at && !nl) { at += 1; nl = true; }
        walk(c);
      }
    }
  };
  walk(p);
  return out;
}

function ddRange(pts, s, e) { // 글 자리 [s, e) → Range(빈 범위면 null)
  let a = null, b = null;
  for (const t of pts) {
    if (!a && s < t.at + t.len) a = [t.node, Math.max(0, s - t.at)];
    if (e <= t.at + t.len) { b = [t.node, Math.max(0, e - t.at)]; break; }
  }
  if (!a || !b) return null;
  const r = document.createRange();
  try { r.setStart(a[0], a[1]); r.setEnd(b[0], b[1]); } catch (err) { return null; }
  return r.collapsed ? null : r;
}

function ddUnrange(m) { // 그 문단의 글자 범위를 표시에서 뺀다
  const hi = DD.hi;
  if (hi) { for (const r of m.ins) hi.ins.delete(r); for (const r of m.del) hi.del.delete(r); }
}

function ddDrop(p) { // 그 문단의 표시를 걷는다(글자 범위 · 클래스) — 꼬리표는 ddTags 가 다시 그린다
  const m = DD.marks.get(p);
  if (!m) return;
  ddUnrange(m);
  p.classList.remove("dd", "dd-A");
  DD.marks.delete(p);
  DD.tags = true;
}

// 그 문단의 표시를 새로 — shared = 같은 문단 id 의 요소가 창에 둘 이상(글 조각이 나뉘어 있어 글자 자리를 못 믿는다 → 글자 표시는 생략).
// 클래스는 바뀔 때만 건드린다(다시 그릴 때마다 뗐다 붙이면 문단마다 스타일을 다시 계산한다).
function ddBuild(p, shared) {
  const old = DD.marks.get(p);
  if (old) ddUnrange(old);
  const id = p.dataset.id, kind = state.kinds[id] || "text", hi = ddHi();
  const now = readText(p);
  const hunks = kind === "new" || shared ? [] : ddDiff(state.original[id] || "", now);
  const m = { kind, hunks, ins: [], del: [] };
  if (hi && hunks.length) {
    const pts = ddPoints(p);
    for (const h of hunks) {
      if (h.ins) { const r = ddRange(pts, h.at, h.at + h.ins.length); if (r) { hi.ins.add(r); m.ins.push(r); } }
      else if (h.del) { const r = ddRange(pts, Math.max(0, h.at - 1), Math.min(now.length, h.at + 1)); if (r) { hi.del.add(r); m.del.push(r); } } // 지우기만 한 자리 — 앞뒤 한 글자씩
    }
  }
  if (!p.classList.contains("dd")) p.classList.add("dd");
  if (p.classList.contains("dd-A") !== (kind === "new")) p.classList.toggle("dd-A", kind === "new");
  DD.marks.set(p, m);
  DD.tags = true;
  if (DD_KINDS.has(kind)) {
    const b = state.byId.get(id);
    if (b && !DD.det.has(b)) DD.ask.set(id, b);
  }
}

function ddWord(s, n = 12) { // 꼬리표·도움말에 적는 글 — 빈칸뿐이면 이름으로(「빈칸」·「묶음 빈칸 2칸」), 그 밖은 따옴표 안에 앞 n자
  if (!s) return "";
  if (!/\S/.test(s)) {
    const parts = [];
    for (let i = 0; i < s.length;) {
      let j = i;
      while (j < s.length && s[j] === s[i]) j++;
      parts.push((DD_WS[s[i]] || "빈칸") + (j - i > 1 ? ` ${j - i}칸` : ""));
      i = j;
    }
    return parts.join(" · ");
  }
  const t = s.replaceAll(LS, "↵").replaceAll("\n", "↵").replaceAll("\t", "⇥");
  return `"${t.length > n ? t.slice(0, n) + "…" : t}"`;
}

function ddInfo(p, m) { // 꼬리표에 적을 것 — { labels: [무엇이], long: [노드 — 어떻게], tip: [도움말 줄] }
  const id = p.dataset.id, who = baseWho(), labels = [], long = [], tip = [];
  const sep = () => { if (long.length) long.push(el("span", "dd-sep", " · ")); };
  if (m.kind === "new") {
    labels.push("새 문단");
    long.push("새 문단");
    tip.push(`A — 새 문단(깃의 added): ${who}에 없던 문단`);
  }
  if (m.hunks.length) {
    labels.push("글");
    const h = m.hunks[0];
    sep();
    if (h.del) long.push(el("del", null, `− ${ddWord(h.del)}`));
    if (h.del && h.ins) long.push(" ");
    if (h.ins) long.push(el("ins", null, `+ ${ddWord(h.ins)}`));
    if (m.hunks.length > 1) long.push(el("span", "dd-more", ` 외 ${m.hunks.length - 1}곳`));
    for (const x of m.hunks.slice(0, 6)) {
      tip.push(x.del && x.ins ? `글: − ${who} ${ddWord(x.del, 40)} → + 지금 ${ddWord(x.ins, 40)}` : x.ins ? `글: + 넣음 ${ddWord(x.ins, 40)}` : `글: − 지움 ${ddWord(x.del, 40)}`);
    }
    if (m.hunks.length > 6) tip.push(`… 글 바뀐 곳 ${m.hunks.length - 6}곳 더`);
  }
  if (DD_KINDS.has(m.kind)) {
    const b = state.byId.get(id), ch = b ? DD.det.get(b) : undefined;
    if (Array.isArray(ch)) {
      if (!ch.length && m.kind === "format") { labels.push("모양"); tip.push("모양: 견주는 값(글자·문단)은 같음 — 그 밖의 모양 속성이 바뀜"); }
      for (const c of ch) {
        labels.push(c.label);
        tip.push(`모양 ${c.label}: ${who} ${c.before} → 지금 ${c.after}${c.part ? " (일부 글자)" : ""}`);
      }
      for (const c of ch) if (c.hint) tip.push(`※ ${c.hint}`); // 줄의 자리 값(앞 여백 · 2번째 줄)의 뜻 — 문단 모양에서 센 자리이지 빈칸을 잰 폭이 아니다(edit_detail.HINTS)
      ch.slice(0, 2).forEach((c) => {
        sep();
        long.push(el("span", "dd-fmt", `${c.label} ${who} ${c.before} → 지금 ${c.after}`)); // 값마다 이름(「원본 0mm → 지금 7.8mm」 — 이름 없는 「0mm → 7.8mm」 는 어느 쪽이 원본인지 모른다)
      });
      if (ch.length > 2) long.push(el("span", "dd-more", ` 외 모양 ${ch.length - 2}`));
    } else if (ch === undefined) { if (m.kind === "format") labels.push("모양 …"); }
    else if (m.kind === "format") { labels.push("모양"); tip.push(ch === null ? `모양: ${who}에 같은 문단이 없어 견주지 않음` : "모양 값은 오른쪽 「고친 문단」 목록에서"); }
  }
  if (!labels.length) { labels.push(m.kind === "struct" ? "나누기·합치기" : "고침"); }
  if (!long.length) long.push(labels.join(" · "));
  return { labels, long, tip };
}

// 쪽 오른쪽 여백의 꼬리표 — .sheet 에 절대 위치(문단 요소 밖 · 화면 크기 고정: fmt_focus.js 의 .fm-tag 와 같은 방식) · 누르는 단추.
// 같은 높이(표 한 행의 칸들)이거나 꼬리표 높이(17px)보다 촘촘한 줄(작은 배율)은 한 꼬리표로 묶는다(「M ×3 글 · 첫 줄」) — 밀려 내려가 제 줄에서 멀어지지 않게.
function ddTags() {
  DD.tags = false;
  for (const e of document.querySelectorAll(".sheet > .dd-tag")) e.remove();
  if (!DD.marks.size || typeof gutterSync !== "function" || !gutterSync()) return;
  const bySheet = new Map();
  for (const [p, m] of DD.marks) {
    const sheet = p.closest(".sheet");
    if (!sheet) continue;
    if (!bySheet.has(sheet)) bySheet.set(sheet, []);
    bySheet.get(sheet).push([p, m]);
  }
  const jobs = []; // 읽기(자리) 먼저 → 쓰기(꼬리표 붙이기)
  for (const [sheet, list] of bySheet) {
    const sr = sheet.getBoundingClientRect(), z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1;
    const rows = list.map(([p, m]) => ({ top: p.getBoundingClientRect().top - sr.top + (parseFloat(getComputedStyle(p).paddingTop) || 0) * z, items: [[p, m]] }));
    rows.sort((a, b) => a.top - b.top);
    const tags = [];
    for (const r of rows) {
      const last = tags[tags.length - 1];
      if (last && r.top - last.top < 17) last.items.push(r.items[0]); else tags.push(r);
    }
    const mgr = Math.round(((state.sections[+sheet.dataset.sec] || DEFAULT_PAGE).marginsMm.r || 0) * PX_PER_MM * z * 10) / 10; // 그 쪽 오른쪽 여백 폭(화면 px)
    jobs.push({ sheet, z, mgr, tags });
  }
  for (const { sheet, z, mgr, tags } of jobs) {
    for (const r of tags) {
      const infos = r.items.map(([p, m]) => ddInfo(p, m)), n = r.items.length;
      const g = r.items.every(([, m]) => m.kind === "new") ? "A" : "M";
      const labels = [...new Set(infos.flatMap((x) => x.labels))];
      const t = el("button", `dd-tag dd-${g}`);
      t.type = "button";
      const k = el("span", "dd-k", g);
      k.setAttribute("aria-hidden", "true");
      const short = el("span", "dd-s", (n > 1 ? `×${n} ` : "") + labels.slice(0, 3).join(" · ") + (labels.length > 3 ? ` +${labels.length - 3}` : ""));
      const long = el("span", "dd-l");
      long.append(...infos[0].long);
      if (n > 1) long.append(el("span", "dd-more", ` 외 ${n - 1}문단`));
      t.append(k, short, long);
      const id = r.items[0][0].dataset.id;
      t.dataset.para = id;
      t.setAttribute("aria-label", `${g === "A" ? "새 문단" : "고친 문단"}${n > 1 ? ` ${n}개` : ""} — ${labels.join(", ")}`);
      t.title = [...(n > 1 ? [`이 높이의 고친 문단 ${n}개 — 첫 문단:`] : []), ...infos[0].tip, "누르면 오른쪽 「고친 문단」 목록의 이 항목 — 되돌리기는 거기서"].join("\n");
      t.onclick = () => ddGo(id);
      t.style.zoom = String(1 / z);
      t.style.setProperty("--mgr", `${mgr}px`);
      t.style.top = `${Math.round(r.top)}px`;
      sheet.append(t);
    }
  }
}

function ddGo(id) { // 꼬리표를 눌렀다 — 「고친 문단」 목록의 그 항목으로(없으면 목록만 연다)
  if (typeof showTab === "function") showTab("Edits");
  const pane = $("paneEdits");
  if (!pane || pane.hidden) return;
  if (typeof drawEdits === "function") drawEdits();
  const li = document.querySelector(`#editsList li[data-id="${CSS.escape(id)}"]`);
  if (!li) return;
  li.scrollIntoView({ block: "center" });
  li.classList.remove("dd-flash");
  void li.offsetWidth;
  li.classList.add("dd-flash");
}

function ddAsk() { // 모양 값 읽기 — 0.25초 모아서 한 번(보이는 문단만: GET …/edits/detail?ids=), 받으면 꼬리표를 다시
  if (DD.timer || DD.busy || !DD.ask.size || !state.id) return;
  DD.timer = setTimeout(async () => {
    DD.timer = 0;
    const want = new Map([...DD.ask].slice(0, 200));
    for (const k of want.keys()) DD.ask.delete(k);
    const id = state.id, epoch = state.epoch;
    let data = null;
    DD.busy = true;
    try {
      data = await api(`/api/docs/${id}/edits/detail?limit=2000&ids=${encodeURIComponent([...want.keys()].join(","))}`); // 옛 서버는 ids 를 모르고 앞 2000개를 준다 — 그 안에 있으면 그대로 쓴다
    } catch (e) { data = null; } finally { DD.busy = false; }
    if (epoch !== state.epoch) return;
    for (const [pid, block] of want) {
      const v = data && data.items ? data.items[pid] : undefined;
      DD.det.set(block, v === undefined ? (data ? "none" : "fail") : v);
    }
    DD.tags = true;
    ddKick();
  }, 250);
}

function ddIo() {
  if (DD.io) return DD.io;
  DD.io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) DD.vis.add(e.target);
      else {
        DD.vis.delete(e.target); ddDrop(e.target); DD.dirty.delete(e.target);
        if (!e.target.isConnected) DD.io.unobserve(e.target); // 문서에서 떨어진 요소(바꿔 끼운 옛 문단) — 관찰자가 붙들고 있지 않게
      }
    }
    ddKick();
  }, { root: $("scroller"), rootMargin: "600px 0px" });
  return DD.io;
}

function ddClear() { // 표시를 모두 걷는다(끔 · 고친 문단 없음 · 다른 문서)
  for (const p of [...DD.marks.keys()]) ddDrop(p);
  if (DD.hi) { DD.hi.ins.clear(); DD.hi.del.clear(); }
  for (const e of document.querySelectorAll(".sheet > .dd-tag")) e.remove();
  DD.tags = false;
}

function ddRun() {
  DD.raf = 0;
  const doc = $("doc");
  if (!doc || PEEK) return;
  ddBtnSync();
  if (!DD.on || !state.id || !state.edited.size) { ddClear(); DD.all = DD.check = false; DD.dirty.clear(); return; }
  const full = DD.all || DD.check;
  if (full || !DD.io) {
    const io = ddIo();
    for (const p of doc.querySelectorAll(".para.edited")) if (!DD.seen.has(p)) { DD.seen.add(p); io.observe(p); }
  }
  const count = new Map(); // 같은 문단 id 의 요소 수(창 가까이)
  for (const p of DD.vis) count.set(p.dataset.id, (count.get(p.dataset.id) || 0) + 1);
  for (const p of [...DD.vis]) {
    if (!p.isConnected) { ddDrop(p); DD.vis.delete(p); continue; }
    if (!p.classList.contains("edited")) { ddDrop(p); continue; } // 되돌린 문단 — 다시 고치면 다시 그린다(관찰은 그대로)
    if (!(full || DD.dirty.has(p) || !DD.marks.has(p))) continue;
    const typing = !full && DD.marks.has(p), keep = DD.tags; // 글을 치는 동안(그 문단만 다시) — 꼬리표는 그대로 둔다(자리를 다시 재지 않는다: 서버에 반영되면 한 번에 다시)
    ddBuild(p, count.get(p.dataset.id) > 1);
    if (typing) DD.tags = keep;
  }
  for (const p of [...DD.marks.keys()]) if (!DD.vis.has(p)) ddDrop(p);
  DD.all = DD.check = false;
  DD.dirty.clear();
  if (DD.tags) ddTags();
  ddAsk();
}

function ddKick() { if (!DD.raf) DD.raf = requestAnimationFrame(ddRun); }
function ddSync() { DD.check = true; ddKick(); } // 고친 문단·글이 바뀜(app.js updateEdits)
function ddDraw() { DD.all = true; ddKick(); } // 쪽을 다시 나눔 · 배율이 바뀜(글자 범위가 풀리고 꼬리표 자리가 바뀐다)

function ddReset() { // 다른 문서 — 지켜보던 것을 버린다
  ddClear();
  if (DD.io) DD.io.disconnect();
  DD.io = null;
  DD.seen = new WeakSet();
  DD.vis.clear();
  DD.dirty.clear();
  DD.ask.clear();
  DD.all = DD.check = false;
}

function ddBtnSync() {
  const b = $("ddBtn");
  if (!b) return;
  if (b.getAttribute("aria-pressed") !== String(DD.on)) b.setAttribute("aria-pressed", String(DD.on));
  const title = DD.on
    ? "고친 곳 보기 — 켜짐: 문서에 무엇을 고쳤는지 깃처럼 보입니다.\n· 넣은 글 = 초록 바탕 · 글자를 지운 자리 = 빨간 물결 밑줄\n· 왼쪽 띠 = 고친 문단(주황 M) · 새 문단(초록 A)\n· 오른쪽 여백 꼬리표 = 바뀐 것(글 · 2번째 줄 …) — 올리면 원본 값 → 지금 값, 누르면 「고친 문단」 목록\n누르면 끕니다(고친 문단을 바탕색으로만)."
    : "고친 곳 보기 — 꺼짐: 고친 문단을 바탕색으로만 표시합니다.\n누르면 켭니다: 넣은 글(초록) · 지운 자리(빨간 물결) · 바뀐 모양 값(오른쪽 여백 꼬리표)을 문서에 보입니다.";
  if (b.title !== title) b.title = title;
}

function ddSet(on) {
  DD.on = !!on;
  try { localStorage.setItem("nfm.dd", DD.on ? "1" : "0"); } catch (e) { /* 기억만 못 함 */ }
  ddDraw();
}

function ddInit() {
  try { DD.on = localStorage.getItem("nfm.dd") !== "0"; } catch (e) { DD.on = true; }
  const b = $("ddBtn");
  if (b) b.onclick = () => ddSet(!DD.on);
  ddBtnSync();
  const doc = $("doc");
  if (doc) doc.addEventListener("input", (e) => { // 글을 치는 동안 — 그 문단만 바로 다시(넣은 글이 치는 대로 초록)
    const p = e.target && e.target.closest ? e.target.closest(".para") : null;
    if (!p || !DD.on || !DD.marks.has(p)) return;
    DD.dirty.add(p);
    ddKick();
  });
  window.addEventListener("resize", () => { if (DD.marks.size) ddDraw(); }); // 창 크기 — 꼬리표 자리를 다시(다음 프레임에 한 번)
}

ddInit();
