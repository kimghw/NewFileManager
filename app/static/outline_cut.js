"use strict";
/* 여기부터 새 템플릿으로 나누기 — 헤딩 라벨(문서 왼쪽 여백의 「T1 L4」)의 오른쪽 단추 메뉴(spec_hwpx_웹편집 ② §8-13 — 서버 app/outline_match.py `cut` · `cut_view` · outline_match_api.py).
   2026-11-23 사용자 "T1L1, L2, L3, L4 이렇게 가다가 L4부터 새로운 템플릿으로 나눌 수 있도록 기능을 넣어줘 그것도 여기 라벨 클릭하던지 더블클릭하던지.마우스 오른쪽을 하던지 옵셔니 나와서 선택할 수 있게,
   바꾸면 다른 템플릿도 다바꿀건지.. 아니면 여기서만 바꿀지도 선택할 수 있게".
   · 라벨을 오른쪽 단추로 누르면 서버에 그 줄의 나누기 계획을 묻고(GET …/outline/cut?paras= — 읽기만: 줄 수 · 못 하는 까닭은 서버가 센다) 공용 메뉴(app.js ctxOpen)를 연다:
       「여기서만 새 템플릿으로 나누기 → T1L4a」(그 줄과 그 아래 줄 — 번호 줄이면 「이 번호 묶음만」: 같은 번호 묶음의 형제도)
       「T1 L4 모두 새 템플릿으로 나누기 → T1L4a」(문서의 그 템플릿 · 그 레벨 줄 전부와 그 아래 줄)
       「여기서만 T1L4a 에 넣기」(그 레벨에서 이미 나눈 템플릿마다)
       「T1 L4 모두 T1L4a 에 넣기」 · 「여기서만 T1 L4 로 되돌리기」 · 「여기서만 / T1L4a L4 모두 T1L4b 로 옮기기」(나눈 템플릿끼리 옮기기 — 같은 무리 = T1 L4 와 거기서 나눈 템플릿:
         2026-11-24 사용자 "T7L2 로 모두변경하기, 이것만 변경하기 넣어줘, 대표에서 a로 b로 b에서 대표로.. 이것만 전체" — 서버 outline_match.move · move_view · POST …/outline/move)
       「T1L4a 전체를 T1 로 합치기」(누른 줄이 그렇게 나눈 템플릿의 줄일 때 — 있는 「합치기」: outline_match.js olmUnsplit · 나눈 템플릿 → 원래 템플릿 「모두」 가 이것이다)
       「템플릿 관계에서 보기」
     못 하는 항목은 꺼 두고 까닭을 풍선 도움말에 적는다(감추지 않는다). 긴 설명은 항목의 풍선 도움말에 둔다.
   · 한 라벨이 여러 줄을 가리키면(표 한 행의 칸들 — 「T11 L2 ×2」) 「여기서만」 은 그 줄 모두다(data-paras).
   · 실행 = POST …/outline/cut {paras, tpl, level, scope: "here" | "all", into?} — 문서는 안 바뀐다(템플릿만) · 「실행 취소」 한 번 · 되돌리기는 「합치기」.
     tpl · level · sig 는 메뉴가 보인 것(sig = 그 범위의 계획 지문) — 그 사이 그 줄의 소속이나 옮길 줄이 바뀌었으면 서버가 409 로 거절한다(메뉴가 보인 것과 다른 줄을 옮기지 않는다).
   · 계획을 묻는 동안 다른 곳을 누르거나 Esc · 스크롤하면 그 응답으로는 메뉴를 열지 않는다(늦게 온 메뉴가 엉뚱한 때에 뜨지 않게).
   부르기 · 다시 그리기는 outline_match.js 의 olmMergeCall(오버레이 요약 갈아 끼움 · 여백 표시 · 트리 다시 그림 · 알림)을 그대로 쓴다.
   기대는 이름: app.js — state · heads · api · toast · nf · ctxOpen · ctx · tplRelOpen / outline_match.js — olmMergeCall · olmKey · olmUnsplit · olmLookFrom(있으면).
   라벨의 꼴: app.js tplMarksDraw 의 `.tpl-mark` 안 `.tm-t[data-tpl][data-level][data-paras]`(「새 서식」·「잘못된 서식」 이 얹힌 줄은 `.tpl-mark` 자체에) — 그 꼴을 바꾸면 여기 olcAt 도 본다. outline_match.js 다음에 읽힌다. */
const OLC = { seq: 0 };

function olcAt(target) { // 누른 곳 → {tpl, level, para(첫 줄), paras} | null — 표기(.tm-t)를 눌렀으면 그 표기, 표의 글 사이를 눌렀으면 첫 표기
  const mark = target && target.closest ? target.closest(".tpl-mark") : null;
  if (!mark) return null;
  const b = target.closest(".tm-t") || mark.querySelector(".tm-t") || mark; // 「새 서식」·「잘못된 서식」 이 얹힌 줄은 표 자체가 줄을 지닌다(app.js tplMarksDraw)
  const paras = b.dataset.paras ? b.dataset.paras.split(",").filter(Boolean) : [];
  if (!paras.length || b.dataset.tpl == null) return null;
  return { tpl: b.dataset.tpl, level: +b.dataset.level, para: paras[0], paras };
}

function olcCount(x) { return x.moved > x.lines ? `${nf(x.lines)}곳 · 총 ${nf(x.moved)}줄` : `${nf(x.moved)}줄`; } // 「2곳 · 총 7줄」 — 곳 = 그 레벨 줄 · 줄 = 그 아래 줄까지

function olcItems(at, v) { // 계획(cut_view) → 메뉴 항목 [[글, 꼬리, 실행, 꺼짐, 풍선 도움말] | null]
  const items = [];
  const name = `T${v.no} L${v.level}`, to = v.next ? `T${v.next}` : "";
  const full = "이 레벨에서 만들 수 있는 템플릿 이름을 다 썼습니다 — 안 쓰는 것을 합친 뒤 나누세요";
  const upper = v.level > 1 ? `(L1${v.level > 2 ? `~L${v.level - 1}` : ""} 은 T${v.no} 의 레벨)` : "";
  const tail = "문서는 안 바뀝니다(템플릿만) · 「실행 취소」 한 번으로 되돌립니다";
  const undo = "나눈 템플릿을 통째로 없애려면 그 줄의 이 메뉴에서 「합치기」";
  const h = v.here, a = v.all;
  const group = v.numbered && h.lines > at.paras.length; // 번호 줄 — 같은 번호 묶음의 형제가 함께 간다
  items.push([`${group ? "이 번호 묶음만" : "여기서만"} 새 템플릿으로 나누기${to ? ` → ${to}` : ""}`, olcCount(h), () => olcRun(at, v, "here"), !!h.why || !v.next,
    h.why || (!v.next ? full : `${group ? `번호 줄은 같은 번호 묶음의 형제 ${nf(h.lines)}줄이 함께 갑니다(번호가 템플릿마다 따로 매겨집니다).\n` : ""}`
      + `${at.paras.length > 1 ? `이 라벨의 줄 ${nf(at.paras.length)}개` : v.table ? "이 표 제목 줄" : "이 줄"}과 그 아래 줄(모두 ${nf(h.moved)}줄)만 ${name} 에서 떼어 새 템플릿 ${to} 로 — 줄은 L${v.level} 부터${upper}\n`
      + `이 템플릿에서 이미 뗀 다른 템플릿의 줄은 제 템플릿 그대로입니다 · 다른 자리의 ${name} 줄은 그대로입니다\n${tail} · ${undo}`)]);
  items.push([`${name} 모두 새 템플릿으로 나누기${to ? ` → ${to}` : ""}`, olcCount(a), () => olcRun(at, v, "all"), !!a.why || !v.next,
    a.why || (!v.next ? full : `지금 문서의 ${name} 줄 ${nf(a.lines)}개와 그 아래 줄(모두 ${nf(a.moved)}줄)을 새 템플릿 ${to} 로 — 줄은 L${v.level} 부터${upper}\n`
      + `${name} 줄 아래가 아니라 윗 레벨 바로 아래에 매달린 더 깊은 줄과, 이미 뗀 다른 템플릿의 줄은 그대로입니다 · 대표 · 서식은 지금 ${name} 것 그대로 옮겨 갑니다\n${tail} · ${undo}`)]);
  const p = typeof oltLineOk === "function" && typeof paraEl === "function" ? paraEl(at.para) : null;
  if (p && at.paras.length === 1 && oltLineOk(p)) // 레벨 범위(부터 · 까지)를 골라 나누기 — 헤딩 고치기 창의 「새 템플릿으로 나누기」(outline_tune.js — 2026-11-24 사용자 「t1L6 부터 어디까지 알수 있고 선택할 수 있어야 함」)
    items.push(["레벨 범위를 골라 나누기…", "", () => outlineTuneOpen(p, { scope: "split" }), !v.next,
      !v.next ? full : `이 줄의 「헤딩 고치기」 창을 「새 템플릿으로 나누기」 로 엽니다 — 새 템플릿이 가질 레벨을 「L${v.level} 부터 · L? 까지」 로 고르고(윗줄의 레벨부터도), 옮겨 갈 줄 수를 보고 적용합니다.\n끝 레벨보다 깊은 아래 줄은 T${v.no} 에 남습니다 · ${tail}`]);
  for (const m of v.made || []) {
    items.push([`여기서만 T${m.no} 에 넣기`, olcCount(h), () => olcRun(at, v, "here", m), !!(h.why || m.why),
      h.why || m.why || `이 줄과 그 아래 줄(모두 ${nf(h.moved)}줄)을 이미 있는 T${m.no}(줄 ${nf(m.lines)}개)로 옮깁니다 — 대표 · 서식은 T${m.no} 것 그대로\n${tail}(이번에 넣은 것만 되돌리려면 「실행 취소」 — 「합치기」 는 T${m.no} 의 줄을 모두 되돌립니다)`]);
  }
  const moves = v.moves || [];
  const groupName = (m) => (m.root ? `T${m.no} L${v.level}` : `T${m.no}`); // 갈 곳 — 원래 템플릿은 「T7 L2」 · 나눈 템플릿은 「T7L2a」
  const mvTip = (m, scope, r) => r.why || (scope === "here"
    ? `${at.paras.length > 1 ? `이 라벨의 줄 ${nf(at.paras.length)}개` : "이 줄"}${r.lines > at.paras.length ? `(번호 줄은 같은 번호 묶음의 형제까지 ${nf(r.lines)}줄)` : ""}과 그 아래 줄(모두 ${nf(r.moved)}줄)을 ${groupName(m)} 로 옮깁니다`
    : `지금 문서의 ${name} 줄 ${nf(r.lines)}개와 그 아래 줄(모두 ${nf(r.moved)}줄)을 ${groupName(m)} 로 옮깁니다`)
    + (r.why ? "" : `\n대표 · 서식은 ${groupName(m)} 것 그대로 · ${tail}`);
  for (const m of moves) { // 나눈 템플릿끼리 옮기기(② §8-13) — 「T7 L2」 ↔ 「T7L2a」 ↔ 「T7L2b」 · 여기서만 · 모두
    if (!m.root && (v.made || []).some((x) => String(x.id) === String(m.id))) { // 원래 템플릿의 줄 → 나눈 템플릿: 「여기서만 …에 넣기」 는 위에 있다
      items.push([`${name} 모두 T${m.no} 에 넣기`, olcCount(m.all), () => olcMove(at, v, m, "all"), !!m.all.why, mvTip(m, "all", m.all)]);
      continue;
    }
    if (m.root) { // 나눈 템플릿의 줄 → 원래 템플릿: 「모두」 는 아래 「합치기」
      items.push([`여기서만 ${groupName(m)} 로 되돌리기`, olcCount(m.here), () => olcMove(at, v, m, "here"), !!m.here.why, mvTip(m, "here", m.here)]);
      continue;
    }
    items.push([`여기서만 ${groupName(m)} 로 옮기기`, olcCount(m.here), () => olcMove(at, v, m, "here"), !!m.here.why, mvTip(m, "here", m.here)]);
    items.push([`${name} 모두 ${groupName(m)} 로 옮기기`, olcCount(m.all), () => olcMove(at, v, m, "all"), !!m.all.why, mvTip(m, "all", m.all)]);
  }
  if (v.back) {
    const b = v.back;
    items.push(null, [`T${b.no} 전체를 T${b.ofNo} 로 합치기`, `${nf(b.lines)}줄`, () => olmUnsplit(b.id), !!b.why,
      b.why || `T${b.no} 의 줄 ${nf(b.lines)}개를 모두 원래 자리의 템플릿으로 되돌리고 T${b.no} 를 없앱니다 — 보통 T${b.ofNo} 의 같은 레벨이고, 그 줄의 윗줄이 나눈 다른 템플릿의 줄이면 그 템플릿입니다\n문서는 안 바뀝니다 · 「실행 취소」 한 번`]);
  }
  items.push(null, ["템플릿 관계에서 보기", "", () => olcRel(at), false, "「템플릿 관계」 열에서 이 레벨의 서식 목록과 이 줄의 서식을 봅니다(라벨을 두 번 누른 것과 같습니다)"]);
  return items;
}

function olcMove(at, v, m, scope) { // 나눈 템플릿끼리 옮기기 — POST …/outline/move(sig = 메뉴가 보인 계획: 그 사이 바뀌었으면 409)
  const r = m[scope] || {};
  return olmMergeCall("move", { paras: at.paras, tpl: String(v.tpl), level: v.level, to: String(m.id), scope, ...(r.sig ? { sig: r.sig } : {}) }, {
    focus: (res) => olmKey((res.moved || {}).id || m.id),
    msg: (res) => {
      const c = res.moved || {};
      return `T${c.from} 의 줄을 ${m.root ? `T${c.no} L${c.level}` : `T${c.no}`} 로 옮겼습니다 — ${c.scope === "all" ? "모두" : "여기서만"} · ${nf(c.moved)}줄 · 문서는 안 바뀜 · 「실행 취소」`;
    },
  });
}

function olcRel(at) {
  const key = typeof olmKey === "function" ? olmKey(at.tpl) : at.tpl;
  const one = { tpl: key, level: at.level, para: at.para };
  if (typeof olmLookFrom === "function") olmLookFrom(one, key); else tplRelOpen(key, one);
}

function olcRun(at, v, scope, into = null) {
  return olmMergeCall("cut", { paras: at.paras, tpl: String(v.tpl), level: v.level, scope, ...((v[scope] || {}).sig ? { sig: v[scope].sig } : {}), ...(into ? { into: String(into.id) } : {}) }, {
    focus: (r) => olmKey((r.cut || {}).id || at.tpl),
    msg: (r) => {
      const c = r.cut || {};
      return c.added ? `T${c.no} 에 넣었습니다 · ${nf(c.moved)}줄 · 「실행 취소」 로 되돌림`
        : `T${c.no} 로 나눴습니다 — T${c.of} L${c.level} ${c.scope === "all" ? "모두" : "여기서만"} · ${nf(c.moved)}줄 · 문서는 안 바뀜 · 「실행 취소」`;
    },
  });
}

async function olcOpen(at, pos) { // pos = {clientX, clientY} — 메뉴가 뜰 자리
  if (!state.id || state.format !== "hwpx" || !heads.outline || state.busy) return;
  const seq = ++OLC.seq, epoch = state.epoch;
  let v;
  try { v = await api(`/api/docs/${state.id}/outline/cut?paras=${encodeURIComponent(at.paras.join(","))}`); }
  catch (e) { if (seq === OLC.seq && epoch === state.epoch) toast(e.status === 404 || e.status === 400 || e.status === 409 ? e.message : `나누기 계획을 읽지 못했습니다: ${e.message}`, true); return; }
  if (seq !== OLC.seq || epoch !== state.epoch) return; // 그 사이 다른 라벨을 눌렀거나 문서가 바뀜
  const items = olcItems(at, v);
  ctxOpen(pos, items.map((it) => (it ? it.slice(0, 4) : null)));
  const menu = ctx.menu;
  if (!menu) return;
  const tips = items.filter(Boolean).map((it) => it[4] || "");
  [...menu.querySelectorAll("button")].forEach((b, i) => { if (tips[i]) b.title = tips[i]; });
}

function bindOutlineCut() {
  const drop = () => { OLC.seq += 1; }; // 계획을 묻는 동안 다른 곳을 누름 · Esc · 스크롤 · 창 크기 — 늦게 온 응답으로 메뉴를 열지 않는다
  document.addEventListener("mousedown", drop, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") drop(); }, true);
  window.addEventListener("resize", drop);
  window.addEventListener("blur", drop);
  const sc = document.getElementById("scroller");
  if (sc) sc.addEventListener("scroll", drop, { passive: true });
  document.addEventListener("contextmenu", (e) => { // 라벨 위 — 문단 메뉴(divContextMenu) · 표 칸 메뉴보다 먼저(잡는 단계)
    const at = olcAt(e.target);
    if (!at) return;
    e.preventDefault();
    e.stopPropagation();
    olcOpen(at, { clientX: e.clientX, clientY: e.clientY });
  }, true);
}
bindOutlineCut();
