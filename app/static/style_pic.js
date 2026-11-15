"use strict";
// 서식 그림 — Word 갤러리식 견본(spec_서식복사 ② §13 — 사용자 2026-11-14 "서식을 그림/이미지로 보여줘야지 … 그림으로 보고 사람이 템플릿 서식을 이해할 수 있게" · "mdword(= MS Word)에 보면 개요레벨 이미지로 보여주잖아. 그런거").
// 브라우저가 **형식 중립 값**만으로 그린다 — 표 명세(view.spec) · 항목의 서식 요약(view.items[].format) · 쪽 설정(view.page·view.body) · 표지의 부분(view.parts).
// 편집 화면의 그리기 함수(renderTable·renderPara·fontStack)와 state 를 쓰지 않는다(astra 협의: 그 함수들은 지금 문서의 글꼴 별칭·형식·편집 표시를 읽고, 같은 id 의 요소가 저장 길 paraEl 에 잡힌다).
// 그림 안에는 제 클래스(sp-*)만 쓴다 — .para · table.tbl · .sheet · data-id · contenteditable 을 만들지 않는다. 글꼴은 서식 요약의 글꼴 이름 그대로(PC 에 있으면 그 글꼴 · 없으면 웹 기본).
// 밖에 내는 것 하나: stylePic(view, opts) -> HTMLElement  (+ stylePic.height(kind, n) = 그 종류의 그림 상자 높이 — 자리를 먼저 잡을 때 쓴다 · stylePic.kindOf(view, kind) = 그릴 종류)
//   view = 견본의 보기(GET /api/styles/{sid} 의 view · POST …/styles/preview 의 view) · opts = {kind: "content"|"para"|"table"|"page"|"cover"|"text"(레벨이 있으면 content), bands?, role?, width?, big?}
// 배율: mm → px 을 그림마다 **한 번** 계산한다(opts.width — 기본 296px = 열 320px 의 안쪽). CSS zoom 을 쓰지 않고, 재려고 배율을 바꿨다 되돌리지도 않는다(화면 요소를 재지 않는다).
// 그림 = role="img" + aria-label(요약 글) · 그림 안은 aria-hidden · pointer-events: none(style_lib.css). 모양(sp-*)의 CSS 는 style_lib.css 끝에 있다. index.html 이 style_lib.js 앞에 읽는다.

const stylePic = (() => {
  const PT_MM = 0.3528, W0 = 296;
  const SAMPLE = "가나다 AaBb 123", SAMPLE2 = "가나다라마바사 AaBbCc 123 가나다라마바사 AaBbCc 123 가나다라마바사 AaBbCc 123";
  const ROLE = { body: "본문", caption: "캡션", note: "주석", box: "상자 글", toc: "목차", other: "기타" }; // 문단 서식의 역할(② §12)
  const PART = { title: "제목", subtitle: "부제", org: "기관명", date: "날짜", person: "작성자", label: "라벨", other: "기타" }; // 표지 부분의 역할(② §14)
  const PAPER = [["A4", 210, 297], ["A3", 297, 420], ["A5", 148, 210], ["B5", 182, 257], ["B4", 257, 364], ["Letter", 215.9, 279.4]];
  const BAND = [["headerRows", "머리행"], ["headerCols", "머리열"], ["footRows", "합계행"]];
  const LINE = { SOLID: "solid", DOT: "dotted", CIRCLE: "dotted", DASH: "dashed", LONG_DASH: "dashed", DASH_DOT: "dashed", DASH_DOT_DOT: "dashed",
    DOUBLE_SLIM: "double", SLIM_THICK: "double", THICK_SLIM: "double", SLIM_THICK_SLIM: "double", DOUBLE: "double" }; // 괘선 종류 → CSS(Word 가 받는 값과 같은 묶음 — style_docx.LINES)
  const ROW_H = 15, ROW_MINI = 6; // 표의 행 높이(px — 고정: 명세에 행 높이가 없다) · 표지 안 작은 표

  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const num = (v, d = 0) => { const n = typeof v === "string" ? parseFloat(v) : Number(v); return Number.isFinite(n) ? n : d; };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const short = (t, n) => { const s = String(t == null ? "" : t).replace(/\s+/g, " ").trim(); return s.length > n ? `${s.slice(0, n)}…` : s; };
  const color = (v) => (typeof v === "string" && /^#[0-9a-fA-F]{3,8}$/.test(v.trim()) ? v.trim() : "");
  const r1 = (v) => String(Math.round(num(v) * 10) / 10);
  const fontFamily = (name) => { const n = typeof name === "string" ? name.replace(/["'\\;{}<>]/g, "").trim().slice(0, 60) : ""; return n ? `"${n}", "Malgun Gothic", "맑은 고딕", sans-serif` : ""; };
  const ALIGN = { left: "left", center: "center", right: "right", justify: "justify", distribute: "justify", both: "justify" };

  function look(e, f, px) { // 서식 요약 → 글 모양(글꼴 이름 그대로 · 크기는 부른 쪽이 정한 px · 굵게 · 기울임 · 밑줄 · 색 · 자간)
    f = f || {};
    const fam = fontFamily(f.font);
    if (fam) e.style.fontFamily = fam;
    if (px) e.style.fontSize = `${Math.round(px * 10) / 10}px`;
    if (f.bold) e.style.fontWeight = "700";
    if (f.italic) e.style.fontStyle = "italic";
    if (f.underline) e.style.textDecoration = "underline";
    const c = color(f.color);
    if (c) e.style.color = c;
    const sp = num(f.spacingPct);
    if (sp) e.style.letterSpacing = `${clamp(sp, -50, 50) / 100}em`;
    return e;
  }
  // 한글식 들여쓰기(서식 요약 — style_verify 와 같은 읽기): 첫 줄 자리 = 왼쪽 여백 + max(첫 줄, 0) · 둘째 줄부터 = 왼쪽 여백 + max(-첫 줄, 0)(내어쓰기)
  const firstX = (f) => Math.max(0, num(f && f.indentLeftMm)) + Math.max(0, num(f && f.firstLineMm));
  const restX = (f) => Math.max(0, num(f && f.indentLeftMm)) + Math.max(0, -num(f && f.firstLineMm));

  function frame(kind, label, opts) { // 그림 상자 — role="img" + aria-label · 안(.sp-in)은 aria-hidden
    const root = mk("div", "sp-pic"), box = mk("div", "sp-frame"), inner = mk("div", "sp-in");
    root.dataset.spKind = kind;
    root.setAttribute("role", "img");
    root.setAttribute("aria-label", label);
    inner.setAttribute("aria-hidden", "true");
    if (!opts.big) box.style.height = `${opts.height || height(kind, opts.n)}px`;
    else root.classList.add("sp-big");
    box.append(inner);
    root.append(box);
    return { root, box, inner };
  }
  function note(root, text) { if (!text) return; const p = mk("div", "sp-note", text); p.setAttribute("aria-hidden", "true"); root.append(p); } // 그림 아래 글(「전체 18행」) — 낭독은 aria-label 이 한다

  function height(kind, n) { // 그 종류의 그림 상자 높이(px) — 자리를 먼저 잡는다(목록이 밀리지 않게: ② §13 「목록의 살림」)
    n = Math.max(0, Math.round(num(n)));
    if (kind === "content") return clamp(16 + (n || 3) * 22, 64, 200);
    if (kind === "para") return 64;
    if (kind === "table") return clamp(30 + (n || 5) * ROW_H, 64, 150); // 30 = 위 띠 표시 자리(15) + 안쪽 여백·테두리 — 9행까지는 다 보인다
    if (kind === "page") return 170;
    if (kind === "cover") return 200;
    return 64;
  }
  function kindOf(view, kind) { // 그릴 종류 — "text" 는 항목에 레벨이 하나라도 있으면 내용 서식(content), 없으면 문단 서식(para): ② §12
    if (kind === "text" || !kind) {
      const v = view || {};
      if (v.spec) return "table";
      if (Array.isArray(v.parts)) return "cover";
      if (Array.isArray(v.items)) return v.items.some((it) => it && it.level != null) ? "content" : "para";
      if (v.page) return "page";
      return kind === "text" ? "para" : "";
    }
    return kind;
  }

  // ---- 내용 서식(개요 레벨) — MS Word 의 다단계 목록 미리보기처럼: 레벨마다 한 줄(왼쪽 바깥 「L1」 · 레터 · 견본 글 · 글 막대) ----
  function levelLine(it, k, fs, withTag) {
    const f = it.format || {}, m = it.marker || {}, row = mk("div", "sp-lv"), line = mk("div", "sp-line"), px = Math.max(9, num(f.sizePt, 10) * fs);
    row.dataset.level = it.level == null ? "" : String(it.level);
    if (withTag) row.append(mk("span", "sp-tag", it.level != null ? `L${it.level}` : ""));
    line.style.paddingLeft = `${Math.round(firstX(f) * k * 10) / 10}px`;
    line.style.minHeight = `${Math.round(px * 1.5)}px`;
    const letter = m.mode === "auto" ? "" : String(m.literal != null && m.literal !== "" ? m.literal : it.letter || "").trim();
    if (m.mode === "auto") line.append(look(mk("span", "sp-letter sp-auto", "1."), { font: f.font, bold: f.bold }, px)); // 자동 번호 — 대상 문서의 번호 설정을 따른다: 회색 자리표
    else if (letter) line.append(look(mk("span", "sp-letter", short(letter, 8)), f, px));
    let text = short(it.sample || "", 12);
    if (letter && text.startsWith(letter)) text = text.slice(letter.length).trim(); // 견본 글이 레터로 시작하면 한 번만
    if (text) line.append(look(mk("span", "sp-text", text), f, px));
    line.append(mk("span", "sp-bar")); // 글 막대(회색 — 줄 끝까지). 레터뿐인 레벨에도 붙는다
    row.append(line);
    return row;
  }
  function content(view, opts) {
    const items = (view.items || []).filter(Boolean), W = opts.width - 34;
    const maxX = Math.max(0, ...items.map((it) => firstX(it.format))), pts = items.map((it) => num((it.format || {}).sizePt, 10)).filter((p) => p > 0);
    const k = maxX > 0 ? Math.min(W / 160, (W * 0.55) / maxX) : W / 160; // mm → px: 모든 레벨에 같은 배율 — 가장 깊은 레벨의 첫 줄 자리가 상자 폭의 55% 안에 오게 한 번 정한다
    const lo = Math.min(...pts, 10), hi = Math.max(...pts, 10), fs = Math.min(10.5 / lo, 17 / hi); // pt → px: 모든 레벨에 같은 배율(레벨 사이의 크기 차이가 보이게) — 가장 작은 글이 10.5px · 가장 큰 글이 17px 을 안 넘게 · 줄마다 최소 9px
    const chain = items.map((it) => { const m = it.marker || {}; return m.mode === "auto" ? "자동 번호" : String(m.literal || it.letter || "").trim() || "(레터 없음)"; });
    const { root, box, inner } = frame("content", `개요 ${items.length}레벨: ${chain.join(" › ")}`, { ...opts, n: items.length });
    root.dataset.spLevels = String(items.length);
    for (const it of items) inner.append(levelLine(it, k, fs, true));
    const need = items.reduce((a, it) => a + Math.max(18, Math.round(Math.max(9, num((it.format || {}).sizePt, 10) * fs) * 1.5) + 3), 12);
    if (!opts.big && need > height("content", items.length)) { box.classList.add("sp-over"); note(root, `전체 ${items.length}레벨`); }
    return root;
  }

  // ---- 문단 서식 — 「가나다 AaBb 123」 꼴의 견본 두 줄을 그 서식으로(내어쓰기는 둘째 줄이 있어야 보인다) ----
  function para(view, opts) {
    const it = (view.items || []).filter(Boolean)[0] || {}, f = it.format || view.format || {}, px = clamp(num(f.sizePt, 10) * 1.2, 9, 22), k = Math.min(1.2 / PT_MM, (opts.width * 0.4) / Math.max(restX(f), firstX(f), 1));
    const role = opts.role || view.role || it.role || null, al = ALIGN[f.align] || "left";
    const label = ["문단 서식", ROLE[role] || "", [f.font || "", f.sizePt ? `${r1(f.sizePt)}pt` : "", f.bold ? "굵게" : "", f.italic ? "기울임" : "", f.underline ? "밑줄" : "",
      al === "center" ? "가운데" : al === "right" ? "오른쪽" : al === "justify" ? "양쪽" : ""].filter(Boolean).join(" ")].filter(Boolean).join(" — ");
    const { root, inner } = frame("para", label, opts), p = look(mk("p", "sp-para"), f, px), lh = clamp(num(f.lineSpacingPct, 160) / 100, 1, 2.6), m = it.marker || {};
    if (role) root.dataset.spRole = role;
    p.style.lineHeight = String(Math.round(lh * 100) / 100);
    p.style.textAlign = al;
    p.style.paddingLeft = `${Math.round(restX(f) * k * 10) / 10}px`;
    p.style.paddingRight = `${Math.round(Math.max(0, num(f.indentRightMm)) * k * 10) / 10}px`;
    p.style.textIndent = `${Math.round(num(f.firstLineMm) * k * 10) / 10}px`;
    if (!opts.big) p.style.maxHeight = `${Math.round(px * lh * 2)}px`; // 두 줄
    const letter = m.mode === "literal" && m.literal ? `${String(m.literal).trim()} ` : "";
    p.textContent = letter + SAMPLE2;
    inner.append(p);
    return root;
  }

  // ---- 테이블 서식 — 표 명세로 그린 작은 표(열 폭 비율 · 음영 · 괘선 · 칸 글 · 합친 칸). 행을 자르지 않는다 — 다 그리고 상자 높이만 제한 ----
  function edgeCss(e) { // {type, widthMm | width: "0.12 mm", color} | null → CSS border 값
    if (!e || typeof e !== "object") return "0";
    const kind = String(e.type || "NONE").toUpperCase(), css = LINE[kind];
    if (!css) return "0";
    const mm = num(e.widthMm != null ? e.widthMm : e.width, 0.12), px = clamp(Math.round(mm * 3.78), css === "double" ? 3 : 1, 4); // 굵기: mm 를 화면 배율(96dpi)로 — 최소 1px(겹선은 3px 부터 보인다)
    return `${px}px ${css} ${color(e.color) || "#000"}`;
  }
  function bandsOf(spec, opts) { // 띠 수 — 고른 값(opts.bands)이 먼저, 없으면 명세의 것. 표 크기 안으로
    const b = opts.bands || spec.bands || {}, rows = num(spec.rows), cols = num(spec.cols);
    const hr = clamp(Math.round(num(b.headerRows)), 0, rows), hc = clamp(Math.round(num(b.headerCols)), 0, cols), fr = clamp(Math.round(num(b.footRows)), 0, Math.max(0, rows - hr));
    return { headerRows: hr, headerCols: hc, footRows: fr };
  }
  const bandText = (b, rows) => [b.headerRows ? `머리행 ${b.headerRows > 1 ? `1–${b.headerRows}` : "1"}` : "", b.headerCols ? `머리열 ${b.headerCols > 1 ? `1–${b.headerCols}` : "1"}` : "",
    b.footRows ? `합계행 ${b.footRows > 1 ? `${rows - b.footRows + 1}–${rows}` : rows}` : ""].filter(Boolean);
  function grid(spec, o) { // <table class="sp-tbl"> — o = {rowH, fontPx(0 = 칸 글 없음)}
    const rows = Math.max(0, Math.round(num(spec.rows))), cols = Math.max(0, Math.round(num(spec.cols))), t = mk("table", "sp-tbl"), cg = mk("colgroup");
    const ws = Array.isArray(spec.widthsMm) && spec.widthsMm.length === cols && spec.widthsMm.every((w) => num(w) > 0) ? spec.widthsMm.map((w) => num(w)) : Array(cols).fill(1), sum = ws.reduce((a, w) => a + w, 0) || 1;
    for (const w of ws) { const c = mk("col"); c.style.width = `${Math.round((w / sum) * 10000) / 100}%`; cg.append(c); } // 열 폭 비율
    t.append(cg);
    const by = new Map();
    for (const c of spec.cells || []) { const r = Math.round(num(c && c.row, -1)); if (r >= 0 && r < rows) { if (!by.has(r)) by.set(r, []); by.get(r).push(c); } }
    const body = mk("tbody");
    for (let r = 0; r < rows; r += 1) {
      const tr = mk("tr");
      tr.style.height = `${o.rowH}px`;
      for (const c of (by.get(r) || []).sort((a, b) => num(a.col) - num(b.col))) {
        const td = mk("td"), f = c.format || {}, rs = Math.max(1, Math.round(num(c.rowSpan, 1))), cs = Math.max(1, Math.round(num(c.colSpan, 1))), e = c.edges || {};
        if (rs > 1) td.rowSpan = Math.min(rs, rows - r);
        if (cs > 1) td.colSpan = Math.min(cs, cols);
        const bg = color(c.fill);
        if (bg) td.style.backgroundColor = bg;
        td.style.borderTop = edgeCss(e.t); td.style.borderRight = edgeCss(e.r); td.style.borderBottom = edgeCss(e.b); td.style.borderLeft = edgeCss(e.l);
        const va = String(c.valign || "").toLowerCase();
        td.style.verticalAlign = va === "top" ? "top" : va === "bottom" ? "bottom" : "middle";
        td.style.textAlign = ALIGN[f.align] === "justify" ? "left" : ALIGN[f.align] || "left";
        if (o.fontPx) { // 칸 글(그 글꼴·굵게·색·정렬 — 작게 · 한 줄)
          const s = look(mk("span", "sp-ct", short(c.text || "", 24)), f, o.fontPx);
          s.style.lineHeight = `${o.rowH - 2}px`;
          td.append(s);
        }
        tr.append(td);
      }
      body.append(tr);
    }
    t.append(body);
    return t;
  }
  function table(view, opts) {
    const spec = view.spec || {}, rows = Math.max(0, Math.round(num(spec.rows))), cols = Math.max(0, Math.round(num(spec.cols))), b = bandsOf(spec, opts), marks = bandText(b, rows);
    const { root, box, inner } = frame("table", `표 ${rows}×${cols}${marks.length ? ` — ${marks.join(" · ")}` : " — 머리 없음"}`, { ...opts, n: rows });
    root.dataset.spRows = String(rows);
    root.dataset.spCols = String(cols);
    const rowBand = b.headerRows > 0 || b.footRows > 0, gl = rowBand ? 50 : 0, gt = b.headerCols > 0 ? 15 : 0, wrap = mk("div", "sp-tw");
    wrap.style.paddingLeft = `${gl}px`;
    wrap.style.paddingTop = `${gt}px`;
    const ws = Array.isArray(spec.widthsMm) && spec.widthsMm.length === cols ? spec.widthsMm.map((w) => Math.max(0, num(w))) : Array(cols).fill(1), sum = ws.reduce((a, w) => a + w, 0) || 1;
    const fontPx = clamp(((opts.width - gl) / Math.max(sum, 1)) * PT_MM * 10 * 1.5, 8, 11); // 칸 글 크기 — 표 폭(mm) 대비 배율로, 읽을 수 있게 8~11px
    wrap.append(grid(spec, { rowH: ROW_H, fontPx: cols && ws.length ? fontPx : 0 }));
    // 띠 표시 — 표 바깥(왼쪽·위)의 가는 괄호선과 글. 음영을 덮지 않는다. 띠 수가 0 이면 그 표시는 없다
    const mark = (key, text, css) => { const m = mk("div", `sp-band sp-band-${key}`), s = mk("span", null, text); m.dataset.spBand = key; Object.assign(m.style, css); m.append(s); wrap.append(m); };
    if (b.headerRows) mark("headerRows", marks.find((t) => t.startsWith("머리행")), { left: "0", width: `${gl - 3}px`, top: `${gt}px`, height: `${b.headerRows * ROW_H}px` });
    if (b.footRows) mark("footRows", marks.find((t) => t.startsWith("합계행")), { left: "0", width: `${gl - 3}px`, top: `${gt + (rows - b.footRows) * ROW_H}px`, height: `${b.footRows * ROW_H}px` });
    if (b.headerCols) mark("headerCols", marks.find((t) => t.startsWith("머리열")), { left: `${gl}px`, top: "0", height: `${gt - 3}px`, width: `calc((100% - ${gl}px) * ${Math.round((ws.slice(0, b.headerCols).reduce((a, w) => a + w, 0) / sum) * 10000) / 10000})` });
    inner.append(wrap);
    const need = gt + rows * ROW_H + 15;
    if (!opts.big && need > height("table", rows)) { // 넘치면 아래를 흐리게 + 그림 아래 글 「전체 n행」(합계행 표시는 아래에 있다)
      box.classList.add("sp-over");
      note(root, `전체 ${rows}행${b.footRows ? ` — ${marks.find((t) => t.startsWith("합계행"))} 은 아래쪽(「크게」 로 봅니다)` : ""}`);
    }
    return root;
  }

  // ---- 쪽 설정 — 쪽 도식: 용지 비율의 흰 상자 · 본문 상자(점선) · 네 변의 여백 수치(mm) · 본문 견본 줄 · 아래에 「A4 세로」 ----
  function paperName(page) {
    const w = num(page.widthMm), h = num(page.heightMm), a = Math.min(w, h), b = Math.max(w, h), p = PAPER.find(([, x, y]) => Math.abs(a - x) <= 1 && Math.abs(b - y) <= 1);
    const land = typeof page.landscape === "boolean" ? page.landscape : w > h;
    return `${p ? p[0] : `${r1(w)}×${r1(h)}mm`} ${land ? "가로" : "세로"}`;
  }
  function sheet(page, maxW, maxH) { // 용지 상자 + 본문 상자 — marginsMm.t·b 는 이미 「종이 끝에서 본문까지」 다(머리말을 다시 더하지 않는다: ② §5 「여백의 뜻을 하나로」)
    const w = Math.max(1, num(page.widthMm, 210)), h = Math.max(1, num(page.heightMm, 297)), m = page.marginsMm || {}, k = Math.min(maxW / w, maxH / h);
    const paper = mk("div", "sp-paper"), body = mk("div", "sp-body");
    paper.style.width = `${Math.round(w * k)}px`;
    paper.style.height = `${Math.round(h * k)}px`;
    const side = (v, total) => clamp(num(v), 0, total * 0.45) * k;
    Object.assign(body.style, { left: `${Math.round(side(m.l, w))}px`, right: `${Math.round(side(m.r, w))}px`, top: `${Math.round(side(m.t, h))}px`, bottom: `${Math.round(side(m.b, h))}px` });
    paper.append(body);
    return { paper, body, k };
  }
  function page(view, opts) {
    const pg = view.page || {}, m = pg.marginsMm || {}, bodyF = view.body && view.body.format ? view.body.format : null, name = paperName(pg);
    const { root, inner } = frame("page", `쪽 설정 — ${name} · 여백 왼 ${r1(m.l)} · 오 ${r1(m.r)} · 위 ${r1(m.t)} · 아래 ${r1(m.b)}mm${bodyF && bodyF.font ? ` · 본문 ${bodyF.font}` : ""}`, opts);
    const H = opts.big ? 300 : height("page") - 58, { paper, body } = sheet(pg, opts.width - 96, H), dia = mk("div", "sp-dia"); // 58 = 위·아래 여백 수치 두 줄 + 용지 이름 한 줄 + 안쪽 여백
    const mg = (key, label, v) => { const s = mk("span", `sp-mg sp-mg-${key}`, `${label} ${r1(v)}`); s.dataset.side = key; return s; };
    for (let i = 0; i < 4; i += 1) { // 본문 견본 줄 — 바탕 글이 있으면 첫 두 줄은 그 글꼴·굵기의 글, 없으면 글 막대만
      if (bodyF && i < 2) body.append(look(mk("span", "sp-bline", SAMPLE), { font: bodyF.font, bold: bodyF.bold, italic: bodyF.italic }, 8));
      else { const bar = mk("span", "sp-bar sp-bbar"); if (i === 3) bar.style.width = "60%"; body.append(bar); }
    }
    const mid = mk("div", "sp-mid");
    mid.append(mg("l", "왼", m.l), paper, mg("r", "오", m.r));
    dia.append(mg("t", "위", m.t), mid, mg("b", "아래", m.b), mk("span", "sp-paper-name", name));
    inner.append(dia);
    return root;
  }

  // ---- 표지 서식 — 쪽 도식 위에 표지의 부분들을 차례로(글 = 그 크기·굵기·정렬의 견본 글 + gapBeforeMm 만큼 띄움 · 표 = 작은 표) ----
  function cover(view, opts) {
    const pg = view.page || { widthMm: 210, heightMm: 297, marginsMm: { l: 20, r: 20, t: 20, b: 20 } }, parts = (view.parts || []).filter(Boolean);
    const names = parts.map((p) => (p.type === "table" ? "표" : PART[p.role] || "글"));
    const { root, inner } = frame("cover", `표지 — 부분 ${parts.length}개${names.length ? `: ${names.slice(0, 8).join(" · ")}` : ""}`, opts);
    root.dataset.spParts = String(parts.length);
    const H = (opts.big ? 420 : height("cover")) - 16, { paper, body, k } = sheet(pg, opts.width - 16, H), dia = mk("div", "sp-dia");
    body.classList.add("sp-cbody");
    const pts = parts.filter((p) => p.type !== "table").map((p) => num((p.format || {}).sizePt, 10)), hi = Math.max(...pts, 10), fs = Math.min((k * PT_MM) * 1.7, 15 / hi); // pt → px: 쪽 배율의 1.7배(읽을 수 있게) — 가장 큰 글이 15px 을 안 넘게 · 부분 사이의 크기 차이는 지킨다
    for (const p of parts) {
      const gap = Math.max(0, num(p.gapBeforeMm)) * k;
      if (p.type === "table") {
        const box = mk("div", "sp-part sp-part-table");
        box.dataset.type = "table";
        box.style.marginTop = `${Math.round(gap)}px`;
        box.append(grid(p.spec || {}, { rowH: ROW_MINI, fontPx: 0 })); // 더 작게 — 칸 글 없이 격자·음영·괘선만
        body.append(box);
      } else {
        const f = p.format || {}, px = Math.max(6, num(f.sizePt, 10) * fs), line = look(mk("div", "sp-part sp-part-text", PART[p.role] || short(p.sample || "글", 10)), f, px);
        line.dataset.type = "text";
        line.dataset.role = p.role || "";
        line.style.marginTop = `${Math.round(gap)}px`;
        line.style.textAlign = ALIGN[f.align] || "left";
        line.style.lineHeight = "1.25";
        body.append(line);
      }
    }
    dia.append(paper);
    inner.append(dia);
    return root;
  }

  function empty(kind, opts, text) {
    const { root, inner } = frame(kind || "none", text, opts);
    root.classList.add("sp-empty");
    inner.append(mk("span", "sp-none", text));
    return root;
  }

  function draw(view, opts = {}) {
    const v = view && typeof view === "object" ? view : {}, o = { ...opts, width: Math.max(160, Math.round(num(opts.width, W0))) }, kind = kindOf(v, o.kind);
    try {
      if (kind === "table" && v.spec && Array.isArray(v.spec.cells)) return table(v, o);
      if (kind === "content" && Array.isArray(v.items) && v.items.length) return content(v, o);
      if (kind === "para" && ((Array.isArray(v.items) && v.items.length) || v.format)) return para(v, o);
      if (kind === "page" && v.page) return page(v, o);
      if (kind === "cover" && Array.isArray(v.parts)) return cover(v, o);
    } catch (e) { return empty(kind, o, "서식 견본을 그리지 못했습니다"); } // 꼴이 다른 값 — 목록은 그대로 보인다
    return empty(kind, o, "서식 견본 값이 없습니다");
  }
  draw.height = height;
  draw.kindOf = kindOf;
  return draw;
})();
