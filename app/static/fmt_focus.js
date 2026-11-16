"use strict";
/* 서식 라벨만 또렷이 · 템플릿만 또렷이(spec_헤딩_추출 ② §7 — 2026-11-15 사용자 "요 서식을 클릭하면 문서에서 이 부분만 잘 보이고 나머진 살짝 … 해당 서식만 잘보이게 해달라는 거지.
   그렇다고 다른게 완전히 보이지 못하게 하는건 아니고" → 같은 날 "템플릿도 클릭하면 똑같이 동일한 템플릿만 찐하게 해줄래? 그리고 서식이랑 이거랑 바탕면에 파랑색이든 무슨 색이든 연하게 표시되게 해줘.
   그리고 여백이 문제면 여백만 색상을 주고 차이가 있음을 표기해줘"). 문서 여백의 표시를 누르면 고른 것의 문단만 그대로 두고 **옅은 파란 바탕**을 입히며 나머지 문단을 흐리게 한다(감추지 않는다).
   · 고르는 것은 하나(FMF.kind): "fmt" = 서식 라벨 「S41」(app.js tplMarksDraw 의 .tm-f) · "tpl" = 템플릿·레벨 「T1 L2」(.tm-t — 개요 오버레이 줄의 표기). 같은 것을 다시 누르면 풀림 · 다른 것을 누르면 그것으로 ·
     문서를 바꿔 열면 풀림(app.js headsReset → fmtFocusReset). 문서도 서버도 안 바뀐다(화면 표시뿐 — 기억하지 않음).
   · 서식 라벨의 문단 = 1단계 결과의 문단(GET …/headings/paras?fmt= — 헤딩이 아닌 문단까지 · 500개씩 끝까지). 1단계 뒤에 새로 생긴 문단은 라벨이 없어 흐린 쪽이다(글을 쓰고 있는 문단은 흐리지 않는다 — fmt_focus.css).
   · 템플릿·레벨의 줄 = 개요 오버레이(heads.outline.lines)에서 그 템플릿·레벨인 줄 — 그릴 때마다 다시 센다(새로 만든 개요 줄도 곧바로).
     **대표와 다른 줄**: 서식 갈래(GET …/outline/formats — outline_match.js olmLoad 가 기억한 것)에서 그 줄의 갈래가 대표와 다른 값(diff)을 본다 —
       여백 값(앞 여백·2번째 줄·오른쪽 여백·위 간격·아래 간격)이 다르면 **그 쪽 여백 자리만 주황**(.fm-d + --fm-l/r/t/b — 여백이 0이면 4px 띠) + 쪽 오른쪽 여백에 표 「≠ 앞 여백」(.fm-tag — 도움말에 「지금 … → 대표 …」),
       여백이 아닌 값(레터·글자 모양·줄 간격 …)이 다르면 표만 「≠ 크기」·「≠ 서식」. 표를 누르면 「템플릿 관계」 의 그 레벨·그 줄의 갈래(맞추기·대표 정하기는 거기서).
     갈래 목록은 갈래마다 30줄까지라 — 잘린 갈래가 하나면 목록에 없는 줄은 그 갈래, 둘 이상이면 그 슬롯만 줄 전부로 다시 읽는다(?tpl=&level= — 옛 서버면 못 가른 줄은 「못 견줌」 으로 센다).
     문서가 바뀌면(편집 차례 rev) 0.4초 뒤 갈래를 다시 읽어 표시를 고친다 — 같은 차례에는 한 번만.
   · 표시: #doc.fmt-focus + 그 문단들에 .fmt-hit(+ .fm-d) — 쪽을 다시 나누면 문단 요소가 새것이라 app.js paginate·flowSettle 끝이 fmtFocusDraw() 를 다시 부른다(구분 기준 자리 표시 divMarksDraw 와 같은 때) ·
     여백 표를 다시 그린 뒤에는 tplMarksDraw 끝이 fmtFocusMarks() 를 부른다(템플릿을 고른 동안에는 문단·표도 같이 — 오버레이가 바뀌었을 수 있다).
   · 설명은 문서 이름 줄(#fmtKey — design.md §4: 문서에 남는 표시는 그 설명을 문서 바로 위에): 칩 + 「이 서식만 또렷이」·「이 템플릿만 또렷이」 + 수 +
     서식: 「목록」(그 라벨의 문단 목록 — headsParas) / 템플릿: 「여백 다름 n」·「서식 다름 n」(누르면 그런 줄로 차례로) · 「템플릿 관계」(전에 표를 누르면 열리던 것 — tplRelOpen) + 「끄기」.
   · **휠로 자리 옮기기 · 위·아래 몇 곳**(2026-11-15 사용자 "마우스 휠을 내리면 다른 … 템플릿으로 이동 할 수 있게 … 윗쪽에 몇개 아랫쪽에 몇개 있는지 표기" — 아래 「자리 옮기기」 절): 고른 것의 문단이 붙어 있는 묶음 = **곳**.
     또렷이가 켜진 동안 문서에서 휠을 굴리면 쪽 넘기기 대신 **아직 안 보인 다음·앞 곳**으로 가고(app.js bindWheelFlip 이 fmNavWheel 에 먼저 묻는다 · 이름 줄 「휠 이동」 으로 끔 — 이 브라우저에 기억),
     문서 창(#viewer) 오른쪽 위·아래의 알약 「▲ 위 n곳」·「▼ 아래 n곳」(.fm-nav — 창 밖에 남은 곳 수 · 누르면 그리로)이 스크롤을 따라 바뀐다. 도착한 곳은 잠깐 진하게(.fm-land).
   app.js · outline_match.js 다음에 읽힌다($·el·hBtn·api·toast·state·heads·nf·headsParas·scrollToBlock·gutterSync·tplRelOpen·PX_PER_MM·DEFAULT_PAGE · olmLoad·olmDiffTitle 를 쓴다). */
const FMF = { kind: null, label: null, ids: null, total: 0, seq: 0, // kind = "fmt"|"tpl" · label = 고른 것의 글(「S41」·「T1 L2」) · ids = 그 문단 id(서식: 읽기 전에는 null — 눌림만 먼저)
  tpl: null, level: 0, no: "", para: null, focus: null, // 템플릿: 오버레이 템플릿 id · 레벨 · 표기 번호 · 누른 줄 · 「템플릿 관계」 에서 펼 템플릿
  diff: null, sum: null, rev: null, tried: null, timer: 0, at: { margin: -1, other: -1 } }; // diff = Map(줄 → 대표와 다른 것) · sum = 줄 수 요약 · rev = 그 갈래의 문서 차례 · tried = 다시 읽기를 건 차례 · at = 「다름」 칩으로 가 본 줄

// 자리 옮기기(아래 「자리 옮기기」 절) — stops = 곳 목록(스크롤 좌표 · 위에서부터) + 그것을 잰 때의 스크롤 상자 크기(h·w — 달라지면 다시 잰다) · count = 창 위·아래에 남은 곳 수 ·
// up·down = 알약 · to·at = 마지막으로 보낸 자리(부드러운 스크롤이 끝나기 전에 또 굴리면 그 자리를 기준으로) · acc·lastEvt·lastStep·locked = 휠 손짓 하나에 한 번(app.js bindWheelFlip 과 같은 셈)
const FMN = { stops: null, h: -1, w: -1, count: null, raf: 0, up: null, down: null, to: null, at: 0, acc: 0, lastEvt: 0, lastStep: 0, locked: false };
const FMN_EDGE = 8; // 창 위·아래 끝에서 이만큼은 「창 밖」 으로 본다(끝에 몇 px 걸친 곳)
const FM_WHEEL_KEY = "nfm.fmFocusWheel"; // 「휠 이동」 끔 = "off"(없으면 켬 — 사용자가 청한 기본)

// 대표와 다른 값의 키 → 그 값이 그려지는 문단 상자의 쪽(왼·오른·위·아래 여백 — app.js indentLook·paraLook 이 padding 으로 그린다). 여기 없는 키(레터·공백·정렬·줄 간격·글자 모양)는 여백이 아니다
const FM_SIDE = { line1Mm: "l", line2Mm: "l", indentRightMm: "r", spaceBeforePt: "t", spaceAfterPt: "b" };
const FM_VARS = { l: "--fm-l", r: "--fm-r", t: "--fm-t", b: "--fm-b" };

function fmtFocusToggle(label) { // 여백의 서식 라벨을 눌렀을 때
  if (!label) return;
  if (FMF.kind === "fmt" && FMF.label === label) fmtFocusOff();
  else fmtFocusOn(label);
}

function fmFresh(kind) { // 고른 것을 바꾼다 — 읽고 있던 것은 버리고 템플릿 쪽 기억도 비운다
  FMF.seq += 1;
  clearTimeout(FMF.timer);
  Object.assign(FMF, { kind, label: null, ids: null, total: 0, tpl: null, level: 0, no: "", para: null, focus: null, diff: null, sum: null, rev: null, tried: null, timer: 0, at: { margin: -1, other: -1 } });
  return FMF.seq;
}

async function fmtFocusOn(label) {
  if (!state.id) return;
  const id = state.id, epoch = state.epoch, seq = fmFresh("fmt");
  FMF.label = label;
  fmtFocusDraw(); // 앞에 고른 것의 흐림은 걷고 눌림 표시는 곧바로 — 문서는 문단을 읽은 뒤
  const ids = new Set();
  let total = 0;
  try {
    for (let off = 0; off < 50000; off += 500) {
      const r = await api(`/api/docs/${id}/headings/paras?${new URLSearchParams({ fmt: label, offset: off, limit: 500 })}`);
      if (seq !== FMF.seq || epoch !== state.epoch) return; // 그 사이 다른 라벨·끄기·다른 문서
      const items = r.items || [];
      total = r.total || 0;
      for (const p of items) ids.add(p.id);
      if (!items.length || off + items.length >= total) break;
    }
  } catch (e) {
    if (seq === FMF.seq && epoch === state.epoch) { fmtFocusOff(); toast(`서식 ${label} 의 문단을 읽지 못했습니다: ${e.message}`, true); }
    return;
  }
  if (!ids.size) { fmtFocusOff(); toast(`서식 ${label} 의 문단이 없습니다 — 1단계를 다시 추출해 라벨 번호가 바뀌었을 수 있습니다`); return; }
  FMF.ids = ids; FMF.total = total;
  fmtFocusDraw();
}

function fmtFocusOff() {
  fmFresh(null);
  fmtFocusDraw();
}
const fmtFocusReset = fmtFocusOff; // 문서를 열고 닫을 때(app.js headsReset)

// ---- 템플릿만 또렷이 ---------------------------------------------------------------------------------------------------------
function tplFocusToggle(m) { // 여백의 템플릿 표기 「T1 L2」 를 눌렀을 때 — m = 그 줄의 표(app.js olMark: {tpl, level, no, para, focus})
  if (!m || m.tpl == null) return;
  if (FMF.kind === "tpl" && FMF.tpl === String(m.tpl) && FMF.level === +m.level) fmtFocusOff();
  else tplFocusOn(m);
}

function tplFocusOn(m) {
  if (!state.id || !heads.outline) return;
  fmFresh("tpl");
  Object.assign(FMF, { tpl: String(m.tpl), level: +m.level, no: String(m.no ?? m.tpl), para: m.para || null, focus: m.focus ?? m.no ?? null });
  FMF.label = `T${FMF.no} L${FMF.level}`;
  fmtFocusDraw(); // 줄만 또렷이는 곧바로(오버레이는 화면에 있다) — 대표와 견주기는 갈래를 읽은 뒤
  if (!FMF.kind) { toast(`T${String(m.no ?? m.tpl)} L${+m.level} 의 줄이 지금 문서에 없습니다`); return; } // 그리다가 풀렸다(fmtFocusDraw — 줄 0개)
  tplFocusDiff();
}

function tplFocusIds() { // 개요 오버레이에서 그 템플릿·레벨인 줄 — 그릴 때마다(새로 만든 줄 · 레벨을 바꾼 줄이 곧바로)
  const ids = new Set(), lines = heads.outline && heads.outline.lines;
  if (lines) for (const pid in lines) { const x = lines[pid]; if (String(x.tpl) === FMF.tpl && +x.level === FMF.level) ids.add(pid); }
  return ids;
}

function fmDiffInfo(diff) { // 갈래의 「대표와 다른 값」 [[키, 이름, 대표, 이 갈래]…] → 그 줄에 그릴 것 {sides(칠할 여백 쪽), margin, other, tag, title}
  const sides = new Set(), mn = [], on = [];
  for (const d of diff) { const s = FM_SIDE[d[0]]; if (s) { sides.add(s); mn.push(d[1]); } else on.push(d[1]); }
  const m = mn.length === 1 ? mn[0] : mn.length ? "여백" : "", o = on.length === 1 ? on[0] : on.length ? "서식" : "";
  const what = m && o ? "여백·서식" : m || o; // 하나만 다르면 그 값의 이름(「2번째 줄」·「크기」), 여럿이면 「여백」·「서식」
  // 표 글 「≠ 2번째 줄」 — 「다름」 을 앞의 「≠」 로: 오른쪽 여백(20mm 면 75~95px)이 좁아 줄임표로 잘려도 다르다는 표시는 남는다(풀어 쓴 글은 도움말에)
  return { sides: [...sides], margin: mn.length > 0, other: on.length > 0, tag: `≠ ${what}`,
    title: (typeof olmDiffTitle === "function" ? olmDiffTitle(diff) : diff.map((d) => `${d[1]}: 지금 ${d[3]} → 대표 ${d[2]}`).join("\n"))
      + (mn.length ? "\n여백이 다른 쪽은 문서에서 그 여백 자리만 주황으로 칠했습니다" : "") + "\n누르면 템플릿 관계 — 이 줄의 서식 갈래(맞추기 · 대표 정하기 · 다른 템플릿으로)" };
}

function tplFocusMap(v, ids) { // 그 슬롯의 서식 갈래 v + 그 줄들 → [Map(줄 → fmDiffInfo), 요약 {lines, same, margin, other, unknown, norep}]
  const map = new Map(), sum = { lines: ids.size, same: 0, margin: 0, other: 0, unknown: 0, norep: !v || !v.rep };
  if (sum.norep) return [map, sum]; // 대표가 없으면(대표 줄을 지움 · 갈래 없음) 견줄 것이 없다
  const of = new Map(), cut = v.groups.filter((g) => g.more > 0);
  for (const g of v.groups) for (const pid of g.paras) of.set(pid, g);
  const info = new Map(); // 갈래 → fmDiffInfo(같은 갈래의 줄은 같은 것)
  for (const pid of ids) {
    const g = of.get(pid) || (cut.length === 1 ? cut[0] : null); // 목록(30줄)에 없는 줄 — 잘린 갈래가 하나면 그 갈래
    if (!g) { sum.unknown += 1; continue; }
    if (g.rep || !(g.diff || []).length) { sum.same += 1; continue; }
    if (!info.has(g)) info.set(g, fmDiffInfo(g.diff));
    const d = info.get(g);
    map.set(pid, d);
    if (d.margin) sum.margin += 1;
    if (d.other) sum.other += 1;
  }
  return [map, sum];
}

async function tplFocusDiff() { // 서식 갈래를 읽어(같은 차례면 기억한 것) 줄마다 대표와 다른 것을 정하고 다시 그린다
  if (FMF.kind !== "tpl" || typeof olmLoad !== "function") return;
  const seq = FMF.seq, epoch = state.epoch, id = state.id, tpl = FMF.tpl, L = FMF.level;
  FMF.tried = state.serverRev;
  let data = null, rev = null;
  try { data = await olmLoad(); rev = typeof OLM !== "undefined" ? OLM.rev : null; } catch { data = null; }
  if (seq !== FMF.seq || epoch !== state.epoch) return;
  let v = data && data[tpl] ? data[tpl][String(L)] || null : null;
  if (v && v.groups.filter((g) => g.more > 0).length > 1) { // 30줄을 넘는 갈래가 둘 이상 — 목록에 없는 줄이 어느 갈래인지 모른다: 그 슬롯만 줄 전부로
    try {
      const r = await api(`/api/docs/${id}/outline/formats?${new URLSearchParams({ tpl, level: L })}`);
      if (seq !== FMF.seq || epoch !== state.epoch) return;
      const one = r && r.slots && r.slots[tpl] ? r.slots[tpl][String(L)] : null;
      if (one) { v = one; rev = r.rev; } // 옛 서버(인자를 모름)는 잘린 목록 그대로 — 못 가른 줄은 「못 견줌」
    } catch { /* 일시 오류 — 잘린 목록으로 */ }
  }
  const [map, sum] = tplFocusMap(v, tplFocusIds());
  FMF.diff = map; FMF.sum = sum; FMF.rev = rev;
  fmtFocusDraw();
}

function tplFocusCheck() { // 문서가 바뀌었으면(편집 차례) 갈래를 다시 — 그릴 때마다 불리므로 같은 차례에는 한 번만 · 0.4초 모아서
  if (FMF.kind !== "tpl" || !FMF.sum || FMF.rev === state.serverRev || FMF.tried === state.serverRev) return;
  FMF.tried = state.serverRev;
  clearTimeout(FMF.timer);
  const seq = FMF.seq;
  FMF.timer = setTimeout(() => { if (seq === FMF.seq) tplFocusDiff(); }, 400);
}

function tplFocusNext(kind) { // 이름 줄의 「여백 다름 n」·「서식 다름 n」 — 그런 줄로 차례로(문서 순 · 끝이면 처음으로)
  if (!FMF.diff) return;
  const list = [...document.querySelectorAll("#doc .para.fm-d[data-id]")].map((p) => p.dataset.id).filter((pid, i, a) => a.indexOf(pid) === i && (FMF.diff.get(pid) || {})[kind]);
  if (!list.length) { toast("그런 줄이 지금 문서에 없습니다"); return; }
  const i = (list.indexOf(FMF.at[kind]) + 1) % list.length;
  FMF.at[kind] = list[i];
  scrollToBlock(list[i]);
}

// ---- 그리기 ------------------------------------------------------------------------------------------------------------------
function fmtFocusDraw() { // 문단 표시 클래스 · 대표와 다른 줄의 표 · 여백 표의 눌림 · 이름 줄 설명 — 켬·끔 · 쪽을 다시 나눈 뒤(문단 요소가 새것)
  if (FMF.kind === "tpl") {
    FMF.ids = tplFocusIds();
    FMF.total = FMF.ids.size;
    if (!FMF.total) fmFresh(null); // 오버레이가 없어졌거나(2단계 다시 · 다른 형식) 그 레벨의 줄이 모두 사라졌다 — 풀림
  }
  fmtFocusParas();
  fmtFocusTags();
  fmtFocusMarkSync();
  fmtFocusKey();
  tplFocusCheck();
  fmNavDirty(); // 곳의 자리는 다음 프레임에 다시 잰다(여기서 재면 쪽을 나눌 때마다 강제 배치)
}

function fmtFocusParas() { // 문단 요소에 .fmt-hit(고른 것) · .fm-d + --fm-*(대표와 여백이 다른 쪽)
  const doc = $("doc");
  if (!doc) return;
  const on = !!(FMF.label && FMF.ids);
  if (!on) {
    if (!doc.classList.contains("fmt-focus")) return;
    doc.classList.remove("fmt-focus");
    for (const p of doc.querySelectorAll(".para.fmt-hit")) p.classList.remove("fmt-hit");
    for (const p of doc.querySelectorAll(".para.fm-d")) fmSides(p, null);
    return;
  }
  const diff = FMF.kind === "tpl" && FMF.diff && FMF.diff.size ? FMF.diff : null;
  for (const p of doc.querySelectorAll(".para[data-id]")) {
    const hit = FMF.ids.has(p.dataset.id);
    p.classList.toggle("fmt-hit", hit); // 같은 값이면 스타일을 다시 계산하지 않는다
    const d = hit && diff ? diff.get(p.dataset.id) : null;
    if (d || p.classList.contains("fm-d")) fmSides(p, d);
  }
  doc.classList.add("fmt-focus");
}

function fmSides(p, d) { // 대표와 여백이 다른 쪽의 자리만 칠할 폭·높이를 그 문단에(없으면 걷음) — 값은 그 문단의 인라인 padding(app.js indentLook·paraLook)에서: 배치를 읽지 않는다
  const st = p.style;
  p.classList.toggle("fm-d", !!d);
  for (const s in FM_VARS) {
    let want = "";
    if (d && d.sides.includes(s)) {
      // 왼쪽 = 모든 줄이 함께 비우는 폭(내어쓰기면 첫 줄 자리까지 — padding-left 에서 내어쓴 만큼 뺌: 글 뒤는 칠하지 않는다) · 여백이 0이어도 다름이 보이게 4px 띠
      const len = s === "l" ? `calc(${st.paddingLeft || "0mm"} + min(${st.textIndent || "0mm"}, 0mm))` : s === "r" ? st.paddingRight || "0mm" : s === "t" ? st.paddingTop || "0pt" : st.paddingBottom || "0pt";
      want = `max(${len}, 4px)`;
    }
    if (st.getPropertyValue(FM_VARS[s]) === want) continue; // 쪽을 다시 나눌 때마다 불린다 — 같으면 그대로(스타일을 다시 계산하지 않게)
    if (want) st.setProperty(FM_VARS[s], want); else st.removeProperty(FM_VARS[s]);
  }
}

function fmtFocusTags() { // 대표와 다른 줄마다 쪽 오른쪽 여백에 표 「≠ 앞 여백」 — 문단 요소 밖(.sheet 에 절대 위치 · 화면 크기 고정: 여백 표 .tpl-mark 와 같은 방식)
  for (const e of document.querySelectorAll(".sheet > .fm-tag")) e.remove();
  if (FMF.kind !== "tpl" || !FMF.diff || !FMF.diff.size || typeof gutterSync !== "function" || !gutterSync()) return;
  const jobs = []; // 읽기(자리) 먼저 → 쓰기(표 붙이기)
  for (const sheet of document.querySelectorAll("#doc .sheet")) {
    const ps = sheet.querySelectorAll(".para.fm-d[data-id]");
    if (!ps.length) continue;
    const sr = sheet.getBoundingClientRect(), z = sheet.offsetWidth ? sr.width / sheet.offsetWidth : 1;
    const mgr = Math.round(((state.sections[+sheet.dataset.sec] || DEFAULT_PAGE).marginsMm.r || 0) * PX_PER_MM * z * 10) / 10; // 그 쪽 오른쪽 여백 폭(화면 px)
    const rows = []; // 같은 높이(표 한 행의 칸들)는 표 하나에
    for (const p of ps) {
      const d = FMF.diff.get(p.dataset.id);
      if (!d) continue;
      const top = p.getBoundingClientRect().top - sr.top + (parseFloat(getComputedStyle(p).paddingTop) || 0) * z; // 첫 줄 높이(위 간격 아래)
      const r = rows.find((x) => Math.abs(x.top - top) < 14);
      if (r) r.items.push({ pid: p.dataset.id, d }); else rows.push({ top, items: [{ pid: p.dataset.id, d }] });
    }
    jobs.push({ sheet, z, mgr, rows });
  }
  for (const { sheet, z, mgr, rows } of jobs) {
    for (const r of rows) {
      const first = r.items[0], kinds = new Set(r.items.map((x) => x.d.tag));
      const t = el("span", `fm-tag${r.items.some((x) => x.d.margin) ? " mg" : ""}`, kinds.size > 1 ? "≠ 서식" : first.d.tag);
      if (r.items.length > 1) t.textContent += ` ×${r.items.length}`;
      t.title = `${FMF.label} 의 대표 줄과 다릅니다\n` + r.items.map((x) => x.d.title.split("\n누르면")[0]).filter((s, i, a) => a.indexOf(s) === i).join("\n—\n") + "\n누르면 템플릿 관계 — 이 줄의 서식 갈래(맞추기 · 대표 정하기 · 다른 템플릿으로)";
      t.setAttribute("role", "button");
      t.dataset.para = first.pid;
      t.onclick = () => tplRelOpen(FMF.focus, { tpl: FMF.tpl, level: FMF.level, para: first.pid });
      t.style.zoom = String(1 / z);
      t.style.setProperty("--mgr", `${mgr}px`);
      t.style.top = `${Math.round(r.top)}px`;
      sheet.append(t);
    }
  }
}

function fmtFocusMarks() { // app.js tplMarksDraw 끝 — 새로 그린 여백 표에 눌림. 템플릿을 고른 동안에는 문단·표도(여백 표는 오버레이가 바뀔 때도 다시 그려진다 — 새 줄 · 레벨 바꿈 · 대표 바꿈)
  if (FMF.kind === "tpl") { fmtFocusDraw(); return; }
  fmtFocusMarkSync();
  fmNavDirty(); // 여백 표는 배율·창 크기가 바뀔 때도 다시 그려진다 — 곳의 자리도 다시
}

function fmtFocusMarkSync() { // 여백의 서식 라벨(.tm-f)·템플릿 표기(.tm-t) 가운데 고른 것에 눌림(.on)
  for (const b of document.querySelectorAll(".tpl-mark .tm-f")) {
    const hit = FMF.kind === "fmt" && b.dataset.fmt === FMF.label;
    b.classList.toggle("on", hit);
    b.setAttribute("aria-pressed", String(hit));
  }
  for (const b of document.querySelectorAll(".tpl-mark .tm-t")) {
    const hit = FMF.kind === "tpl" && b.dataset.tpl === FMF.tpl && +b.dataset.level === FMF.level;
    b.classList.toggle("on", hit);
    b.setAttribute("aria-pressed", String(hit));
  }
  // 그 글이 든 표에도(.fm-on — 파란 테두리·옅은 바탕): 여백이 좁아 같은 줄 뒤에 붙은 라벨(.tm-fmt)은 줄임표로 잘려 글의 눌림만으로는 안 보인다
  for (const m of document.querySelectorAll(".tpl-mark")) m.classList.toggle("fm-on", !!m.querySelector(".tm-f.on, .tm-t.on"));
}

function fmtFocusKey() { // 문서 이름 줄의 설명 — 고른 것이 있을 때만
  const box = $("fmtKey"), row = $("fileInfo");
  if (!box || !row) return;
  const tpl = FMF.kind === "tpl", s = FMF.sum, wheelOn = fmWheelOn();
  const sig = !FMF.label ? "" : (tpl ? `T|${FMF.label}|${FMF.total}|${s ? [s.margin, s.other, s.unknown, s.norep].join(",") : "…"}` : `${FMF.label}|${FMF.ids ? FMF.total : "…"}`) + `|w${+wheelOn}`;
  row.classList.toggle("has-fm-key", !!sig);
  if (box.dataset.sig === sig && box.hidden === !sig) return; // 쪽을 다시 나눌 때마다 불린다 — 같으면 그대로
  box.dataset.sig = sig; box.hidden = !sig; box.textContent = "";
  box.classList.toggle("tpl", !!sig && tpl); // 템플릿 설명은 칩이 더 있어 좁은 폭에서 글을 더 일찍 감춘다(fmt_focus.css)
  if (!sig) return;
  const label = FMF.label;
  const chip = el("span", "fm-key-chip", label);
  const text = el("span", "fm-key-text", tpl ? "이 템플릿만 또렷이" : "이 서식만 또렷이");
  const off = hBtn("끄기", () => fmtFocusOff(), { cls: "btn sm fm-key-btn fm-key-off", title: "흐리게 한 것을 풉니다 — 여백의 같은 표시를 다시 눌러도 풀립니다" });
  // 「휠 이동」 — 켜 두면(기본) 문서에서 휠을 굴릴 때 쪽 넘기기 대신 다음·앞 곳으로(아래 「자리 옮기기」). 좁으면 감춘다(fmt_focus.css — 켬·끔은 그대로 · 알약은 남는다)
  const wheel = hBtn("휠 이동", () => fmWheelSet(!fmWheelOn()), { cls: "btn sm fm-key-wheel",
    title: (wheelOn ? `켜짐 — 문서에서 마우스 휠을 굴리면 쪽 넘기기 대신 다음·앞의 ${label} 자리로 갑니다.\n누르면 끕니다(휠은 평소대로).` : `꺼짐 — 휠은 평소대로 움직입니다.\n누르면 켭니다: 휠을 굴리면 다음·앞의 ${label} 자리로 갑니다.`)
      + "\n문서 창 오른쪽 위·아래의 「▲ 위 n곳」·「▼ 아래 n곳」 은 창 밖에 남은 자리 수 — 눌러도 그리로 갑니다" });
  wheel.setAttribute("aria-pressed", String(wheelOn));
  if (!tpl) {
    chip.title = `서식 라벨 ${label} — 1단계가 서식이 같은 문단끼리 묶어 매긴 이름`;
    text.title = `문서에서 서식 ${label} 의 문단만 그대로(옅은 파란 바탕) 보이고 나머지 문단은 흐리게 보입니다(감추지 않습니다 · 문서는 안 바뀝니다).\n1단계 추출 뒤에 새로 생긴 문단은 라벨이 없어 흐리게 보입니다.\n켜진 동안 문서에서 휠을 굴리면 다음·앞의 이 서식 자리로 가고(「휠 이동」), 문서 창 오른쪽 위·아래에 창 밖에 남은 자리 수가 보입니다.`;
    box.append(chip, text, el("span", "fm-key-count", FMF.ids ? `문단 ${nf(FMF.total)}개` : "읽는 중…"), wheel,
      hBtn("목록",() => headsParas({ fmt: label }), { cls: "btn sm fm-key-btn fm-key-list", title: `서식 ${label} 의 문단 목록을 문서 옆 열에 — 줄을 누르면 그 문단으로` }), off);
    return;
  }
  chip.title = `템플릿 T${FMF.no} 의 ${FMF.level}번째 줄(레벨 ${FMF.level})`;
  text.title = `문서에서 ${label} 의 줄만 그대로(옅은 파란 바탕) 보이고 나머지 문단은 흐리게 보입니다(감추지 않습니다 · 문서는 안 바뀝니다).\n이 레벨의 대표 줄과 여백이 다른 줄은 그 여백 자리만 주황으로 칠하고, 쪽 오른쪽 여백에 무엇이 다른지 적습니다.\n켜진 동안 문서에서 휠을 굴리면 다음·앞의 이 템플릿 자리로 가고(「휠 이동」), 문서 창 오른쪽 위·아래에 창 밖에 남은 자리 수가 보입니다.`;
  box.append(chip, text, el("span", "fm-key-count", `줄 ${nf(FMF.total)}개`));
  if (!s) box.append(el("span", "fm-key-note", "대표와 견주는 중…"));
  else if (s.norep) { const n = el("span", "fm-key-note", "대표 없음"); n.title = "이 레벨에 대표 줄이 없어 견줄 서식이 없습니다 — 「템플릿 관계」 에서 줄 하나를 대표로 정하세요"; box.append(n); }
  else {
    const leg = (kind, cls, name, n, tip) => { // 색 설명 칩(색 네모 + 이름 + 수 — 색만으로 가르지 않는다) · 누르면 그런 줄로 차례로
      const b = hBtn("", () => tplFocusNext(kind), { cls: `fm-key-leg ${cls}`, title: `${tip}\n누르면 그런 줄로 차례로 갑니다` });
      b.append(el("i", "fm-key-sw"), el("span", "fm-key-leg-n", name), el("b", null, nf(n)));
      return b;
    };
    if (s.margin) box.append(leg("margin", "mg", "여백 다름", s.margin, `대표 줄과 여백(앞 여백 · 2번째 줄 · 오른쪽 여백 · 위·아래 간격)이 다른 줄 ${nf(s.margin)}개 — 문서에서 그 여백 자리만 주황`));
    if (s.other) box.append(leg("other", "ot", "서식 다름", s.other, `대표 줄과 여백이 아닌 값(레터 · 공백 · 정렬 · 줄 간격 · 글자 모양)이 다른 줄 ${nf(s.other)}개 — 쪽 오른쪽 여백의 표에 무엇이 다른지`));
    if (!s.margin && !s.other) { const n = el("span", "fm-key-note", s.unknown ? "" : "대표와 모두 같음"); if (n.textContent) { n.title = "이 레벨의 줄이 모두 대표 줄과 서식이 같습니다(레터 · 문단 모양 · 글자 모양)"; box.append(n); } }
    if (s.unknown) { const n = el("span", "fm-key-note", `못 견줌 ${nf(s.unknown)}`); n.title = `서식 갈래 둘 이상이 30줄을 넘어 ${nf(s.unknown)}줄은 어느 갈래인지 가르지 못했습니다 — 서버를 다시 켜면 줄 전부를 읽습니다(「템플릿 관계」 의 갈래 목록은 그대로 맞습니다)`; box.append(n); }
  }
  box.append(wheel, hBtn("템플릿 관계", () => tplRelOpen(FMF.focus, FMF.para ? { tpl: FMF.tpl, level: FMF.level, para: FMF.para } : null),
    { cls: "btn sm fm-key-btn fm-key-rel", title: `템플릿 관계를 문서 옆 열에 — ${label} 의 서식 갈래 · 대표 정하기 · 대표에 맞추기(전에 여백의 표를 누르면 열리던 것)` }), off);
}

// ---- 자리 옮기기 — 휠로 다음·앞 곳 · 창 위·아래에 남은 곳 수 -----------------------------------------------------------------------
// 곳 = 고른 것의 문단이 문서 순서로 붙어 있는 묶음(사이에 낀 빈 문단은 넘긴다 — 「- 가 / - 나 / - 다」 세 줄이 한 곳 · 제목 줄은 줄마다 한 곳). 서식·템플릿 모두 FMF.ids 로 센다.
// 자리는 스크롤 좌표(스크롤 상자 내용의 위끝 기준)로 한 번 재서 기억하고(FMN.stops), 그리기(fmtFocusDraw — 쪽 다시 나눔 · 고른 것 바뀜)·배율·창 크기·내용 높이가 바뀌면 다시 잰다.
function fmNavOn() { return !!(FMF.label && FMF.ids && FMF.ids.size) && !$("scroller").hidden; }
function fmWheelOn() { try { return localStorage.getItem(FM_WHEEL_KEY) !== "off"; } catch { return true; } }
function fmWheelSet(on) {
  try { if (on) localStorage.removeItem(FM_WHEEL_KEY); else localStorage.setItem(FM_WHEEL_KEY, "off"); } catch { /* 기억만 안 함 */ }
  fmtFocusKey();
  fmNavDraw(); // 알약의 도움말(휠로도 · 눌러서만)
}

function fmNavDirty() { FMN.stops = null; fmNavLater(); }
function fmNavLater() { // 프레임에 한 번 — 스크롤 · 그리기 뒤
  if (FMN.raf || (!FMF.label && !(FMN.up && !FMN.up.hidden))) return; // 꺼져 있고 알약도 없으면 할 일이 없다(문서를 쓰는 동안 paginate 마다 불린다)
  FMN.raf = requestAnimationFrame(() => { FMN.raf = 0; fmNavDraw(); });
}

function fmNavStops() { // 곳 목록 [{top, bottom(스크롤 좌표), n(줄 수), els(그 문단 요소)}] — 위에서부터
  const sc = $("scroller");
  if (FMN.stops && FMN.h === sc.scrollHeight && FMN.w === sc.scrollWidth) return FMN.stops;
  const base = sc.getBoundingClientRect().top - sc.scrollTop, stops = [];
  let run = null, last = null;
  for (const p of document.querySelectorAll("#doc .para[data-id]")) {
    const id = p.dataset.id;
    if (FMF.ids.has(id)) {
      const r = p.getBoundingClientRect();
      if (!r.width && !r.height) continue; // 안 그려진 문단
      const top = r.top - base, bottom = r.bottom - base;
      if (run) { run.top = Math.min(run.top, top); run.bottom = Math.max(run.bottom, bottom); run.els.push(p); if (id !== last) run.n += 1; } // 쪽에 걸쳐 둘로 나뉜 문단은 한 줄
      else { run = { top, bottom, n: 1, els: [p] }; stops.push(run); }
      last = id;
    } else if (run && p.textContent.trim()) run = null; // 글이 있는 다른 문단이 끼면 곳이 끝난다
  }
  stops.sort((a, b) => a.top - b.top); // 2쪽 보기 · 표 칸 — 화면에서 위인 것이 먼저(같으면 문서 순)
  FMN.stops = stops; FMN.h = sc.scrollHeight; FMN.w = sc.scrollWidth;
  return stops;
}

function fmNavEls() { // 알약 둘 — 문서 창(#viewer · position: relative)의 오른쪽 위·아래(fmt_focus.css). 처음 쓸 때 만든다
  if (FMN.up) return;
  const mk = (dir) => {
    const b = el("button", `fm-nav ${dir > 0 ? "down" : "up"}`);
    b.type = "button"; b.hidden = true;
    b.onclick = () => fmNavStep(dir);
    $("viewer").append(b);
    return b;
  };
  FMN.up = mk(-1); FMN.down = mk(1);
}

function fmNavDraw() { // 창 위·아래에 남은 곳 수 → 알약 「▲ 위 n곳」·「▼ 아래 n곳」 — 스크롤할 때마다(프레임에 한 번) · 켬·끔 · 쪽을 다시 나눈 뒤
  const stops = fmNavOn() ? fmNavStops() : null;
  if (!stops || !stops.length) {
    FMN.count = null;
    if (!stops) FMN.stops = null;
    if (FMN.up) { FMN.up.hidden = true; FMN.down.hidden = true; }
    for (const p of document.querySelectorAll("#doc .para.fm-land")) p.classList.remove("fm-land");
    return;
  }
  fmNavEls();
  const sc = $("scroller"), y = sc.scrollTop, h = sc.clientHeight;
  const c = { up: 0, down: 0, upN: 0, downN: 0, all: stops.length };
  for (const s of stops) { // 창에 조금이라도 보이는 곳은 어느 쪽에도 안 센다
    if (s.bottom <= y + FMN_EDGE) { c.up += 1; c.upN += s.n; }
    else if (s.top >= y + h - FMN_EDGE) { c.down += 1; c.downN += s.n; }
  }
  FMN.count = c;
  const tpl = FMF.kind === "tpl", what = `${tpl ? "템플릿" : "서식"} ${FMF.label}`, unit = tpl ? "줄" : "문단", wheel = fmWheelOn();
  const put = (b, arrow, word, roll, n, lines) => {
    b.hidden = false;
    const sig = `${FMF.label}|${n}|${lines}|${+wheel}`;
    if (b.dataset.sig === sig) return; // 스크롤마다 불린다 — 같으면 그대로
    b.dataset.sig = sig;
    b.textContent = `${arrow} ${word} ${nf(n)}곳`;
    b.classList.toggle("none", !n);
    b.setAttribute("aria-disabled", String(!n));
    b.title = n ? `이 창 ${word}쪽에 ${what} 이(가) ${nf(n)}곳(${unit} ${nf(lines)}개) 더 있습니다 — 곳 = 붙어 있는 ${unit} 묶음\n누르${wheel ? `거나 문서에서 휠을 ${roll}` : ""}면 바로 ${word}의 자리로 갑니다`
        + (wheel ? "" : "\n(「휠 이동」 이 꺼져 있어 휠은 평소대로 움직입니다 — 이름 줄에서 켭니다)")
      : `이 창 ${word}쪽에는 ${what} 이(가) 더 없습니다`;
  };
  put(FMN.up, "▲", "위", "올리", c.up, c.upN);
  put(FMN.down, "▼", "아래", "내리", c.down, c.downN);
}

// 다음(dir 1)·앞(−1) 곳으로 — **아직 안 보인 곳**의 위끝을 창 위에서 PAD 만큼 아래에 둔다(그 아래로 이어지는 곳들이 같이 보인다 · 올라갈 때는 그 곳과 함께 창에 들어가는 앞 곳들까지).
// 창 끝에 걸친 곳이 있으면 그 곳부터: 위끝을 맞추고, 창보다 길면 창 높이만큼씩 그 안을 지난다(서식 한 가지가 여러 쪽 이어지는 곳). 더 없으면 그 쪽 알약이 까딱한다.
function fmNavStep(dir) {
  if (!fmNavOn()) return false;
  const sc = $("scroller"), stops = fmNavStops(), h = sc.clientHeight, now = performance.now(), E = FMN_EDGE;
  const y = FMN.to != null && now - FMN.at < 600 ? FMN.to : sc.scrollTop; // 부드러운 스크롤이 끝나기 전에 또 굴렸다 — 가던 자리를 기준으로 잇는다
  const PAD = Math.min(96, Math.round(h * 0.18)), OVER = 64, room = h - PAD - 24;
  let to = null, land = null;
  if (dir > 0) {
    const cut = stops.find((s) => s.top < y + h - E && s.bottom > y + h + E); // 창 아래로 이어지는 곳
    const next = stops.find((s) => s.top >= y + h - E);
    if (cut) { land = cut; to = cut.top - PAD - y > 40 ? cut.top - PAD : y + h - OVER; }
    else if (next) { land = next; to = next.top - PAD; }
  } else {
    let cut = null, k = -1;
    for (let i = 0; i < stops.length; i++) {
      const s = stops[i];
      if (s.top < y - E && s.bottom > y + E) cut = s; // 창 위로 이어지는 곳
      if (s.bottom <= y + E) k = i;
    }
    if (cut) { land = cut; to = Math.max(cut.top - PAD, y - (h - OVER)); }
    else if (k >= 0) {
      const prev = stops[k];
      let f = k;
      if (prev.bottom - prev.top > room) to = prev.bottom - h + OVER; // 창보다 긴 곳 — 아래끝부터
      else { while (f > 0 && prev.bottom - stops[f - 1].top <= room) f -= 1; to = stops[f].top - PAD; }
      land = stops[f];
    }
  }
  if (land) to = Math.max(0, Math.min(sc.scrollHeight - h, Math.round(to)));
  if (!land || Math.abs(to - y) < 2) { fmNavBump(dir); return false; }
  FMN.to = to; FMN.at = now;
  sc.scrollTo({ top: to, behavior: "smooth" });
  fmNavLand(land);
  return true;
}

function fmNavLand(s) { // 도착한 곳을 잠깐 진하게(fmt_focus.css .fm-land — 여러 곳이 같이 보일 때 어디로 왔는지)
  for (const p of document.querySelectorAll("#doc .para.fm-land")) p.classList.remove("fm-land");
  if (!s.els.length) return;
  void s.els[0].offsetWidth; // 같은 곳에 다시 와도 다시 깜박이게
  for (const p of s.els) p.classList.add("fm-land");
}

function fmNavBump(dir) { // 그 쪽에 더 없다 — 알약이 까딱
  const b = dir > 0 ? FMN.down : FMN.up;
  if (!b || b.hidden) return;
  b.classList.remove("bump");
  void b.offsetWidth;
  b.classList.add("bump");
}

// 문서 위의 휠 — app.js bindWheelFlip 이 쪽 넘기기보다 먼저 묻는다. true = 여기서 썼다(쪽 넘기기·기본 스크롤 없음). 손짓 하나에 한 곳(마우스 휠 한 칸 · 트랙패드 한 번 쓸기)
function fmNavWheel(e) {
  if (!fmNavOn() || !fmWheelOn() || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return false; // Ctrl+휠 확대 · Shift+휠 가로는 그대로
  if (Math.abs(e.deltaX) > Math.abs(e.deltaY) || !fmNavStops().length) return false;
  e.preventDefault();
  const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? $("scroller").clientHeight : 1);
  const now = performance.now(), pause = now - FMN.lastEvt;
  FMN.lastEvt = now;
  if (Math.abs(dy) >= 50) { // 마우스 휠 한 칸 — 칸마다 한 곳, 140ms 에 한 번까지
    FMN.acc = 0; FMN.locked = true;
    if (now - FMN.lastStep >= 140) { FMN.lastStep = now; fmNavStep(dy > 0 ? 1 : -1); }
    return true;
  }
  if (pause > 150) { FMN.acc = 0; FMN.locked = false; } // 트랙패드 — 손짓이 끊겼다 다시 시작
  if (FMN.locked) return true;
  FMN.acc += dy;
  if (Math.abs(FMN.acc) >= 60) { FMN.locked = true; FMN.lastStep = now; fmNavStep(FMN.acc > 0 ? 1 : -1); FMN.acc = 0; }
  return true;
}

$("scroller").addEventListener("scroll", fmNavLater, { passive: true }); // 스크롤을 따라 위·아래 수를 다시
window.addEventListener("resize", fmNavDirty);
