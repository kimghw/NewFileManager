"use strict";
/* hwpx 공유 — 주인 화면(spec_공유 ② §7 · design.md §14). app.js · panel_help.js 다음에 읽는다. 손님 화면은 따로다(app/static/share/ — 이 파일도 app.js 도 읽지 않는다).
   하는 일: ① 상단 바 「저장」 앞의 「공유」 단추(문서를 연 hwpx 작업일 때만) ② 누르면 떠 있는 창(모달 아님 — ✕/Esc/바깥 누름): 공유 켜기 · 링크·키 복사 · 접속 주소 · 저장 상태 · 사람들 · 키 새로 만들기 · 끄기
   ③ 공유 중이면 1.2초마다 GET /api/docs/{id}/share/changes 로 손님의 변경을 받아 화면에 반영(글 = 그 문단 · 나누기/합치기 = 그 블록만 · 그 밖 = 문서 다시 읽기) ④ 손님이 작성 중인 문단은 못 고치게(색 띠).
   app.js 에서 기대는 것(이름·인자가 바뀌면 여기도): state(id · epoch · serverRev · texts · original · unrestored · pristine · edited · timers · failed) · api · el · $ · toast · hhmm · paraEl · disp · readText ·
   selOffsets · focusAt · flushAll · applyServer · applyEditState · applyTops · applyDoc · setDocFonts · walkParas · refreshSaveState · PEEK · PLAIN, panel_help.js 의 hHelp.
   서버가 차례 어긋남을 가려 준다(share.Feed.read — ② §4): 내가 그 뒤 차례에 고친 문단에 닿는 옛 편집은 오지 않는다. 여기서는 아직 못 보낸 내 글만 본다. */
const SHARE_POLL = 1200, SHARE_WATCH = 1000, SHARE_IDLE = 60000; // IDLE = 커서만 두고 이만큼 아무것도 안 하면 그 문단을 놓는다(작성 중 — ② §5)
const sh = { doc: null, st: null, keys: new Map(), since: -1, epoch: "", timer: null, polling: false, people: [], pop: null, busy: false, seq: 0, act: 0 };
const shareOn = () => !!(sh.st && sh.st.active && sh.doc && sh.doc === state.id);
const shareGuests = () => sh.people.filter((p) => !p.host).length;

// ---------------------------------------------------------------- 단추 · 상태
function shareBtn() {
  let b = $("shareBtn");
  if (b) return b;
  b = el("button", "btn");
  b.id = "shareBtn";
  b.type = "button";
  b.hidden = true;
  b.setAttribute("aria-haspopup", "dialog");
  b.setAttribute("aria-expanded", "false");
  b.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="8.5" cy="7.5" r="3.2"/><path d="M3 19.5c0-3.1 2.5-5.5 5.5-5.5s5.5 2.4 5.5 5.5"/><path d="M15.8 4.8a3 3 0 0 1 0 5.6M17 14.2c2.3.5 4 2.4 4 4.8"/></svg><span class="share-btn-txt"></span>';
  b.onclick = () => (sh.pop ? sharePopClose() : sharePopOpen());
  const before = $("downloadBtn");
  if (before) before.before(b);
  return b;
}

function shareBtnDraw() {
  const b = shareBtn(), st = sh.st, show = !!(state.id && st && st.available);
  b.hidden = !show;
  if (!show) { sharePopClose(); return; }
  const txt = b.querySelector(".share-btn-txt"), on = shareOn(), bad = on && ((st.saved && st.saved.error) || (st.listen && st.listen.error));
  txt.textContent = on ? `공유 중 · ${shareGuests()}명` : "공유";
  txt.classList.toggle("idle", !on);
  if (on) b.dataset.n = `${shareGuests()}명`; else delete b.dataset.n; // 좁은 폭에서는 글 대신 이 수만 보인다(share.css)
  b.classList.toggle("on", on && !bad);
  b.classList.toggle("warn", !!bad);
  b.title = on ? `이 문서를 같이 쓰는 중 — 손님 ${shareGuests()}명${bad ? " · 확인할 것이 있습니다" : ""}` : "공유 — 링크와 키를 받은 사람과 이 문서를 같이 씁니다";
  b.setAttribute("aria-label", on ? `공유 중, 손님 ${shareGuests()}명` : "공유");
}

async function shareLoad() { // 지금 문서의 공유 상태를 읽는다 — 문서를 열 때 · 창을 열 때
  const doc = state.id, seq = ++sh.seq;
  if (!doc) { sh.st = null; shareBtnDraw(); return; }
  let st;
  try { st = await api(`/api/docs/${doc}/share`); } catch { st = { available: false, active: false }; }
  if (seq !== sh.seq || doc !== state.id) return;
  shareSet(st);
}

function shareSet(st) { // 서버가 준 상태를 둔다 → 단추 · 창 · 읽기 시작/멈춤
  const was = shareOn();
  sh.st = st;
  if (st.key && st.id) sh.keys.set(st.id, st.key); // 키는 켠 직후·새로 만든 직후의 응답에만 온다 — 이 화면이 떠 있는 동안만 쥔다(저장소에 안 남긴다)
  if (st.people) sh.people = st.people;
  if (!shareOn()) { sh.people = []; clearTimeout(sh.timer); shareMarks(); }
  else if (!was) { sh.since = -1; sh.epoch = ""; sharePollSoon(200); }
  shareBtnDraw();
  if (sh.pop) sharePopDraw();
}

function shareDocChanged() { // 다른 문서를 열었다 · 닫았다
  sh.doc = state.id || null;
  clearTimeout(sh.timer);
  sh.st = null; sh.people = []; sh.since = -1; sh.epoch = "";
  sharePopClose();
  shareBtnDraw();
  if (sh.doc) shareLoad();
}

// ---------------------------------------------------------------- 손님의 변경 받기
function sharePollSoon(ms) { clearTimeout(sh.timer); if (shareOn()) sh.timer = setTimeout(sharePoll, ms); }

const shareFocused = () => { const a = document.activeElement; return a && a.classList && a.classList.contains("para") ? a : null; };
function shareFocusKeep() { const p = shareFocused(), o = p && selOffsets(p); return p ? { id: p.dataset.id, offset: o ? o.start : 0, end: o ? o.end : 0 } : null; }
function shareFocusBack(keep) { if (keep && !shareFocused() && paraEl(keep.id)) focusAt(keep); }

async function sharePoll() {
  if (!shareOn() || sh.polling) return;
  sh.polling = true;
  const doc = sh.doc, epoch = state.epoch, cur = Date.now() - sh.act < SHARE_IDLE ? shareFocused() : null; // 커서만 두고 오래 쉬면 놓는다 — 다시 치거나 누르면 다시 잡는다
  try {
    if (sh.since < 0) sh.since = state.serverRev; // 방금 읽은 문서의 차례부터
    const r = await api(`/api/docs/${doc}/share/changes?since=${sh.since}&epoch=${encodeURIComponent(sh.epoch)}&block=${encodeURIComponent(cur ? cur.dataset.id : "")}`);
    if (doc !== state.id || epoch !== state.epoch) return;
    if (!r.active) { shareLoad(); return; }
    sh.epoch = r.epoch;
    if (r.reload) await shareReload();
    else {
      let again = false;
      for (const it of r.items || []) if ((again = await shareApply(it))) break; // 다시 읽었으면 남은 것은 그 안에 이미 있다
      if (!again) sh.since = Math.max(sh.since, r.rev);
    }
    if (doc !== state.id || epoch !== state.epoch) return;
    sh.people = r.people || [];
    if (sh.st && r.saved) sh.st.saved = { ...sh.st.saved, ...r.saved };
    shareMarks();
    shareBtnDraw();
    sharePopLive();
    if (r.denied) { // 손님이 먼저 잡은 문단
      const p = shareFocused();
      if (p && cur === p) p.blur();
      toast(`${r.denied.name} 님이 작성 중인 문단입니다 — 끝나면 고칠 수 있습니다`);
    }
  } catch { /* 서버가 잠깐 안 닿음 — 다음 차례에 다시 */ }
  finally { sh.polling = false; sharePollSoon(document.hidden ? SHARE_POLL * 4 : SHARE_POLL); }
}

async function shareApply(it) { // 손님의 편집 하나를 화면에 → true = 문서를 통째로 다시 읽었다
  if (it.t === "text") {
    const id = it.id, p = paraEl(id);
    if (!(id in state.texts)) return false;
    if (state.timers.has(id) || (p && document.activeElement === p && readText(p) !== state.texts[id])) return false; // 내가 치는 중인 문단 — 내 글을 곧 보낸다
    const edited = it.text !== (state.original[id] ?? "");
    applyServer(id, { text: it.text, rev: Math.max(state.serverRev, it.rev), edited, unrestored: [...state.unrestored], pristine: state.pristine && !edited });
    if (p) { // 글만 바꾼다 — 문단 안 글자 모양은 한 가지로 보인다(문서를 다시 읽으면 맞는다 — ② §4)
      const keep = document.activeElement === p ? shareFocusKeep() : null;
      p.replaceChildren(el("span", null, disp(it.text)));
      if (keep) focusAt(keep);
    }
    refreshSaveState();
    return false;
  }
  if (it.t !== "tops" || !it.resp || !it.resp.tops) return false;
  const mine = new Set([...state.timers.keys(), ...state.failed]); // 아직 못 보낸 내 글이 있는 문단
  await flushAll(); // 곧 바뀔 블록에 치던 글을 먼저 보낸다
  let stale = false; // 그 문단이 이 블록 안에 있으면 옛 블록으로 덮지 않고 다시 읽는다
  if (mine.size) walkParas(it.resp.tops.blocks, (b) => { if (mine.has(b.id)) stale = true; });
  if (stale) { await shareReload(); return true; }
  const keep = shareFocusKeep(), r = { ...it.resp, rev: Math.max(state.serverRev, it.rev) };
  if (it.rev > state.serverRev) applyEditState(r); // 화면이 아는 것보다 뒤 차례 — 고친 문단 목록·실행 취소 수도 그 응답대로
  else for (const i of r.edited || []) state.edited.add(i); // 내 편집이 더 뒤다 — 목록은 내 응답의 것을 두고 보태기만
  if (r.webFonts) setDocFonts(r.webFonts);
  applyTops(r);
  shareFocusBack(keep);
  return false;
}

async function shareReload() { // 문서를 통째로 다시 읽어 그린다 — 보던 자리·커서는 그대로
  const id = state.id, epoch = state.epoch, keep = shareFocusKeep(), top = $("scroller").scrollTop;
  await flushAll();
  const d = await api(`/api/docs/${id}`);
  if (id !== state.id || epoch !== state.epoch) return;
  applyDoc(d);
  $("scroller").scrollTop = top;
  shareFocusBack(keep);
  sh.since = d.rev;
}

function shareMarks() { // 손님이 작성 중인 문단 — 색 띠, 못 고치게
  const held = new Map();
  if (shareOn()) for (const p of sh.people) if (p.block && !p.host) held.set(p.block, p);
  for (const p of document.querySelectorAll(".para.share-held")) {
    if (held.has(p.dataset.id) && p.dataset.shareWho === held.get(p.dataset.id).name) continue;
    p.classList.remove("share-held");
    p.style.removeProperty("--share-who");
    if (p.title === `${p.dataset.shareWho} 님이 작성 중`) p.removeAttribute("title");
    delete p.dataset.shareWho;
    p.contentEditable = PLAIN ? "plaintext-only" : "true";
  }
  for (const [id, who] of held) {
    const p = paraEl(id);
    if (!p || p.classList.contains("share-held")) continue;
    p.classList.add("share-held");
    p.dataset.shareWho = who.name;
    p.style.setProperty("--share-who", who.color);
    if (!p.title) p.title = `${who.name} 님이 작성 중`;
    p.contentEditable = "false";
    if (document.activeElement === p) p.blur();
  }
}

// ---------------------------------------------------------------- 떠 있는 창
function sharePopOpen() {
  if (!sh.st || !sh.st.available) return;
  const pop = el("div", "share-pop");
  pop.id = "sharePop";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-label", "공유");
  document.body.append(pop);
  sh.pop = pop;
  $("shareBtn").setAttribute("aria-expanded", "true");
  sharePopDraw();
  shareLoad(); // 저장 상태·사람들을 지금 것으로
}

function sharePopClose() {
  if (!sh.pop) return;
  sh.pop.remove();
  sh.pop = null;
  const b = $("shareBtn");
  if (b) b.setAttribute("aria-expanded", "false");
}

function sharePopPlace() {
  const pop = sh.pop, b = $("shareBtn");
  if (!pop || !b) return;
  const r = b.getBoundingClientRect(), w = pop.offsetWidth;
  pop.style.top = `${Math.round(r.bottom + 6)}px`;
  pop.style.left = `${Math.round(Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)))}px`;
}

const shareRow = (...kids) => { const d = el("div", "share-row"); d.append(...kids); return d; };
function shareInput(id, value, { readonly = false, placeholder = "", cls = "", label = "" } = {}) {
  const i = el("input", cls);
  i.id = id; i.value = value || ""; i.readOnly = readonly; i.placeholder = placeholder; i.spellcheck = false; i.autocomplete = "off";
  if (label) i.setAttribute("aria-label", label);
  if (readonly) i.onfocus = () => i.select();
  return i;
}
function shareAct(text, run, cls = "btn") { const b = el("button", cls, text); b.type = "button"; b.onclick = run; return b; }
function shareLabel(text, forId) { const l = el(forId ? "label" : "span", forId ? "" : "share-k", text); if (forId) l.htmlFor = forId; return l; }

async function shareCopy(text, what) {
  try { await navigator.clipboard.writeText(text); toast(`${what} 복사했습니다`); }
  catch { toast("복사하지 못했습니다 — 글을 골라 Ctrl+C 로 복사해 주세요", true); }
}

function sharePopDraw() {
  const pop = sh.pop, st = sh.st;
  if (!pop || !st) return;
  const typed = Object.fromEntries([...pop.querySelectorAll("input:not([readonly])")].map((i) => [i.id, i.value])); // 치던 글은 다시 그려도 남긴다
  const head = el("div", "share-head"), grid = el("div", "share-grid"), acts = el("div", "share-acts"), x = shareAct("✕", sharePopClose, "share-x");
  x.setAttribute("aria-label", "닫기");
  pop.textContent = "";
  if (!st.active) {
    head.append(el("strong", null, "공유"), hHelp("공유 설명", "링크와 키를 받은 사람이 브라우저로 들어와 이 문서를 같이 씁니다. 손님은 문단 글을 고치고 줄을 나누고 합칠 수 있습니다 — 서식 · 표 구조 · LLM · TASK 는 주인만 합니다.\n문서의 저장본과 링크 바로가기가 공유폴더에 놓입니다(같은 이름의 파일은 덮지 않습니다).\n키는 들어와서 쓰는 것을 막습니다 — 공유폴더의 저장본은 그 폴더를 볼 수 있는 사람이면 키 없이 읽습니다(SharePoint 폴더 권한이 정합니다)."), el("span", "spacer"), x);
    const folder = shareInput("shareFolder", typed.shareFolder ?? st.folder, { placeholder: (st.roots && st.roots[0] ? st.roots[0] : "C:\\Users\\…\\OneDrive") + "\\공유 폴더" });
    const host = shareInput("shareHost", typed.shareHost ?? st.host, { placeholder: "손님에게 보일 이름" });
    host.maxLength = 20;
    grid.append(shareLabel("공유폴더", "shareFolder"), shareRow(folder, hHelp("공유폴더 설명", "SharePoint 폴더를 OneDrive 로 이 PC 에 동기화해 둔 폴더의 경로를 넣습니다(탐색기 주소 줄에서 복사). 동기화는 OneDrive 가 합니다.")));
    grid.append(el("p", "share-note" + (st.roots && st.roots.length ? "" : " warn"), st.roots && st.roots.length ? `이 PC 의 동기화 폴더: ${st.roots.join(" · ")}` : "이 PC 에서 OneDrive·SharePoint 동기화 폴더를 찾지 못했습니다"));
    grid.append(shareLabel("내 이름", "shareHost"), shareRow(host));
    acts.append(shareAct(sh.busy ? "켜는 중…" : "공유 켜기", shareStart, "btn primary"));
    acts.lastChild.disabled = sh.busy;
    const go = (e) => { if (e.key === "Enter") shareStart(); };
    folder.onkeydown = host.onkeydown = go;
  } else {
    const key = sh.keys.get(st.id) || "", sv = st.saved || {};
    head.append(el("strong", null, "공유 중"), hHelp("공유 설명", "링크와 키를 둘 다 받은 사람만 들어옵니다. 키는 켠 직후와 새로 만든 직후에만 보입니다 — 잊었으면 새로 만드세요(들어와 있던 손님은 다시 넣어야 합니다).\n공유폴더의 hwpx 는 저장본입니다 — 거기서 한글로 고친 것은 이 문서에 들어오지 않고, 그 폴더를 볼 수 있는 사람은 키 없이 읽습니다."), el("span", "spacer"), x);
    grid.append(shareLabel("링크"), shareRow(shareInput("shareLink", st.link, { readonly: true, label: "링크" }), shareAct("복사", () => shareCopy(st.link, "링크를"))));
    grid.append(shareLabel("키"), key
      ? shareRow(shareInput("shareKey", key, { readonly: true, cls: "share-key", label: "키" }), shareAct("복사", () => shareCopy(key, "키를")))
      : shareRow(el("span", "share-val", "켠 직후에만 보입니다"), shareAct("새로 만들기", shareRekey)));
    const url = shareInput("shareUrl", typed.shareUrl ?? st.url, { placeholder: st.auto });
    url.onkeydown = (e) => { if (e.key === "Enter") shareUrlApply(); };
    grid.append(shareLabel("접속 주소", "shareUrl"), shareRow(url, shareAct("적용", shareUrlApply),
      hHelp("접속 주소 설명", `링크의 앞부분입니다. 비워 두면 이 PC 의 사내망 주소(${st.auto})를 씁니다 — 같은 망의 PC 에서만 들어옵니다.\n밖에서 들어오게 하려면 공유 포트(${st.listen ? st.listen.port : 8119})를 터널(이 PC 의 포트를 인터넷 주소로 이어 주는 프로그램)로 낸 주소(https://…)를 넣으세요. 켜져 있는 모든 공유가 이 주소를 같이 씁니다.`)));
    const where = el("span", "share-val", `${st.folder}\\${st.file}`);
    where.title = `${st.folder}\\${st.file}${st.linkFile ? `\n링크 바로가기: ${st.linkFile}` : ""}`;
    grid.append(shareLabel("공유폴더"), where);
    if (!st.synced) grid.append(el("p", "share-note warn", "OneDrive·SharePoint 동기화 폴더가 아닙니다 — 저장본이 이 PC 에만 있습니다"));
    const saved = el("span", "share-val");
    saved.id = "shareSaved";
    grid.append(shareLabel("저장"), shareRow(saved, shareAct(sv.conflict ? "덮어쓰기" : "지금 저장", () => shareSave(!!sv.conflict))));
    const people = el("div", "share-people");
    people.id = "sharePeople";
    grid.append(shareLabel("사람들"), people);
    if (st.listen && st.listen.error) grid.append(el("p", "share-note err", st.listen.error));
    if (key) acts.append(shareAct("안내 글 복사", () => shareCopy(`「${state.name}」 같이 쓰기\n링크: ${st.link}\n키: ${key}`, "링크와 키를")));
    acts.append(shareAct("키 새로 만들기", shareRekey), el("span", "spacer"), shareAct("공유 끄기", shareStop));
    for (const b of acts.querySelectorAll("button")) b.disabled = sh.busy;
  }
  pop.append(head, grid, acts);
  sharePopLive();
  sharePopPlace();
}

function sharePopLive() { // 읽을 때마다 바뀌는 곳만 — 저장 상태 · 사람들(입력 칸은 안 건드린다)
  const st = sh.st, saved = $("shareSaved"), people = $("sharePeople");
  if (!sh.pop || !st || !st.active) return;
  if (saved) {
    const sv = st.saved || {};
    saved.textContent = sv.error || (sv.behind ? "바뀐 내용 저장 대기 중" : sv.at ? `${hhmm(new Date(sv.at * 1000))} 저장됨` : "아직 저장 안 함");
    saved.title = saved.textContent;
    saved.style.color = sv.error ? "var(--fail)" : "";
  }
  if (people) {
    people.textContent = "";
    for (const p of sh.people) {
      const busy = p.block && !p.host, chip = el(busy ? "button" : "span", "share-who"), dot = el("i");
      chip.style.setProperty("--c", p.color);
      chip.append(dot, `${p.name}${p.host ? " · 나" : ""}${busy ? " — 작성 중" : ""}`);
      if (busy) { chip.type = "button"; chip.title = "작성 중인 문단으로"; chip.onclick = () => { const x = paraEl(p.block); if (x) x.scrollIntoView({ block: "center", behavior: "smooth" }); }; }
      people.append(chip);
    }
    if (!shareGuests()) people.append(el("span", "share-val", "아직 들어온 손님이 없습니다"));
  }
}

async function shareCall(opts, path = "") { // 주인 끝점 하나 → 상태를 받아 둔다. 실패하면 알림 → null
  if (sh.busy || !state.id) return null;
  sh.busy = true;
  if (sh.pop) sharePopDraw();
  const doc = state.id;
  try {
    const st = await api(`/api/docs/${doc}/share${path}`, { ...opts, headers: { "Content-Type": "application/json" } });
    sh.busy = false;
    if (doc === state.id) shareSet(st);
    return st;
  } catch (e) {
    sh.busy = false;
    if (sh.pop) sharePopDraw();
    toast(e.message, true);
    return null;
  }
}

async function shareStart() {
  const folder = ($("shareFolder") || {}).value || "", host = ($("shareHost") || {}).value || "";
  if (!folder.trim()) { toast("공유폴더 경로를 넣어 주세요", true); $("shareFolder").focus(); return; }
  await flushAll(); // 첫 저장본에 지금 화면의 글까지
  const st = await shareCall({ method: "POST", body: JSON.stringify({ folder, host }) });
  if (st && st.active) toast("공유를 켰습니다 — 링크와 키를 같이 쓸 사람에게 보내 주세요");
}

async function shareUrlApply() {
  const st = await shareCall({ method: "PUT", body: JSON.stringify({ url: ($("shareUrl") || {}).value || "" }) });
  if (st) { const i = $("shareUrl"); if (i) i.value = st.url || ""; toast("접속 주소를 바꿨습니다 — 링크가 바뀌었으면 다시 보내 주세요"); }
}

async function shareSave(force) {
  if (force && !confirm("공유폴더의 파일을 지금 문서로 덮어씁니다. 밖에서 그 파일을 고친 내용은 사라집니다. 계속할까요?")) return;
  await flushAll();
  const st = await shareCall({ method: "POST", body: JSON.stringify({ force }) }, "/save");
  if (st && st.saved && !st.saved.error) toast("공유폴더에 저장했습니다");
}

async function shareRekey() {
  if (!confirm("키를 새로 만들면 지금 키는 더 쓸 수 없고, 들어와 있는 손님도 모두 나갑니다(새 키를 넣어야 다시 들어옵니다). 계속할까요?")) return;
  const st = await shareCall({ method: "POST" }, "/key");
  if (st && st.key) toast("새 키를 만들었습니다 — 같이 쓸 사람에게 다시 보내 주세요");
}

async function shareStop() {
  if (!confirm("공유를 끕니다. 손님은 모두 나가고 링크는 더 열리지 않습니다 — 공유폴더의 저장본은 남습니다. 계속할까요?")) return;
  await flushAll();
  const st = await shareCall({ method: "DELETE" });
  if (st && !st.active) toast("공유를 껐습니다");
}

// ---------------------------------------------------------------- 묶기
if (!PEEK) { // 둘째 면 화면(같이 보기)은 공유를 다루지 않는다
  shareBtn();
  setInterval(() => { if ((state.id || null) !== sh.doc) shareDocChanged(); }, SHARE_WATCH); // app.js 에 끼어들지 않고 문서가 바뀐 것만 본다
  document.addEventListener("pointerdown", (e) => {
    if (!sh.pop || sh.pop.contains(e.target) || (e.target.closest && e.target.closest("#shareBtn, #panelHelpTooltip"))) return;
    sharePopClose();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && sh.pop) { sharePopClose(); $("shareBtn").focus(); } });
  document.addEventListener("click", (e) => { // 손님이 작성 중인 문단을 누름 — 누가 쓰는지 알린다
    const p = e.target.closest && e.target.closest(".para.share-held");
    if (p) toast(`${p.dataset.shareWho} 님이 작성 중인 문단입니다 — 끝나면 고칠 수 있습니다`);
  });
  document.addEventListener("focusin", (e) => { if (shareOn() && e.target.classList && e.target.classList.contains("para")) { sh.act = Date.now(); sharePollSoon(60); } }); // 커서를 둔 문단을 곧바로 알린다
  for (const ev of ["keydown", "input", "pointerdown"]) document.addEventListener(ev, (e) => { if (e.target.closest && e.target.closest("#doc")) sh.act = Date.now(); }, true); // 문서에서 뭔가 하는 동안만 작성 중
  document.addEventListener("visibilitychange", () => { if (!document.hidden) sharePollSoon(100); });
  window.addEventListener("resize", sharePopPlace);
}
