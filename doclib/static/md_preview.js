// 문서 라이브러리 — 자료(MD)의 「미리보기」: 마크다운을 읽기 좋은 꼴로 그린다(제목 · 문단 · 목록 · 표 · 그림 · 인용 · 수식 · 주석).
// 바깥 라이브러리 없이 DOM 노드로만 짓는다(innerHTML 을 쓰지 않는다 — MD 는 LLM 이 쓴 글이다). 원문은 바꾸지 않는다.
// 쓰는 곳: doclib.js renderMd. 주석 가운데 「p.N」 은 쪽 구분선, 「확인 필요」 는 노란 꼬리표로 보이고 그 밖의 주석은 흐린 글로 보인다.
// 수식($$ … $$ · $…$)은 그리지 않고 LaTeX 글 그대로 수식 칸에 보인다(바깥 라이브러리를 들이지 않음).
(function () {
  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  const COMMENT = /^<!--([\s\S]*?)-->$/;
  function commentEl(body, inline) {
    const t = body.trim();
    const page = /^p\.\s*(\d+)$/.exec(t);
    if (page && !inline) return node("div", "mp-page", `p.${page[1]}`);
    if (/확인 필요/.test(t)) return node("span", "mp-warn", t);
    return node(inline ? "span" : "div", "mp-com", t);
  }
  // ---- 줄 안 ----
  const INLINE = [
    ["com", /<!--([\s\S]*?)-->/y],
    ["img", /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/y],
    ["link", /\[([^\]]+)\]\(([^)\s]+)\)/y],
    ["code", /`([^`]+)`/y],
    ["math", /\$([^$\n]+?)\$/y],
    ["strong", /\*\*([^*]+?)\*\*|__([^_]+?)__/y],
    ["em", /\*([^*\s][^*]*?)\*|(?<![\w가-힣])_([^_\s][^_]*?)_(?![\w가-힣])/y],
    ["br", /<br\s*\/?>/iy],
  ];
  function inline(text, ctx, out) {
    let buf = "", i = 0;
    const flush = () => { if (buf) { out.append(document.createTextNode(buf)); buf = ""; } };
    while (i < text.length) {
      const ch = text[i];
      let hit = null;
      if ("<![`$*_".includes(ch)) {
        for (const [kind, re] of INLINE) {
          re.lastIndex = i;
          const m = re.exec(text);
          if (m) { hit = [kind, m]; break; }
        }
      }
      if (!hit) { buf += ch; i += 1; continue; }
      flush();
      const [kind, m] = hit;
      i += m[0].length;
      if (kind === "com") out.append(commentEl(m[1], true));
      else if (kind === "img") out.append(imgEl(m[1], m[2], ctx));
      else if (kind === "link") {
        if (/^https?:\/\//i.test(m[2])) {
          const a = node("a");
          a.href = m[2]; a.target = "_blank"; a.rel = "noopener noreferrer";
          inline(m[1], ctx, a);
          out.append(a);
        } else inline(m[1], ctx, out);
      } else if (kind === "code") out.append(node("code", null, m[1]));
      else if (kind === "math") out.append(node("span", "mp-math-i", m[1]));
      else if (kind === "strong") { const b = node("strong"); inline(m[1] || m[2], ctx, b); out.append(b); }
      else if (kind === "em") { const e = node("em"); inline(m[1] || m[2], ctx, e); out.append(e); }
      else if (kind === "br") out.append(node("br"));
    }
    flush();
    return out;
  }
  function imgEl(alt, src, ctx) {
    const fig = node("figure", "mp-fig"), img = node("img");
    const m = /^images\/(.+)$/.exec(src);
    if (!m) return node("span", "mp-com", `그림: ${alt || src}`);
    img.src = ctx.img(m[1]); img.alt = alt; img.loading = "lazy";
    fig.dataset.img = m[1];
    fig.append(img);
    if (alt) fig.append(node("figcaption", null, alt));
    return fig;
  }
  // ---- 표 ----
  function cells(line) {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
    const out = [];
    let cur = "";
    for (let i = 0; i < s.length; i += 1) {
      if (s[i] === "\\" && s[i + 1] === "|") { cur += "|"; i += 1; } else if (s[i] === "|") { out.push(cur.trim()); cur = ""; } else cur += s[i];
    }
    out.push(cur.trim());
    return out;
  }
  const isSep = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
  function tableEl(head, aligns, rows, ctx) {
    const wrap = node("div", "mp-table"), t = node("table"), th = node("thead"), tb = node("tbody");
    const row = (vals, tag) => {
      const tr = node("tr");
      vals.forEach((v, k) => {
        const c = node(tag);
        if (aligns[k]) c.style.textAlign = aligns[k];
        inline(v, ctx, c);
        tr.append(c);
      });
      return tr;
    };
    th.append(row(head, "th"));
    rows.forEach((r) => tb.append(row(r, "td")));
    t.append(th, tb);
    wrap.append(t);
    return wrap;
  }
  // ---- 목록 ----
  const ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  function listEl(items, ctx) {
    const root = node(/\d/.test(items[0].mark) ? "ol" : "ul");
    const stack = [{ ind: items[0].ind, list: root }];
    let last = null;
    for (const it of items) {
      while (stack.length > 1 && it.ind < stack[stack.length - 1].ind) stack.pop();
      if (it.ind > stack[stack.length - 1].ind && last) {
        const sub = node(/\d/.test(it.mark) ? "ol" : "ul");
        last.append(sub);
        stack.push({ ind: it.ind, list: sub });
      }
      const li = node("li");
      if (/\d/.test(it.mark)) li.value = parseInt(it.mark, 10);
      inline(it.text, ctx, li);
      stack[stack.length - 1].list.append(li);
      last = li;
    }
    return root;
  }
  // ---- 덩이 ----
  function render(text, ctx) {
    const out = node("div", "mp"), L = text.replace(/\r\n?/g, "\n").split("\n");
    let i = 0, para = [];
    const endPara = () => {
      if (!para.length) return;
      const p = node("p");
      para.forEach((ln, k) => { if (k) p.append(document.createTextNode(" ")); inline(ln.trim(), ctx, p); });
      out.append(p);
      para = [];
    };
    while (i < L.length) {
      const ln = L[i], t = ln.trim();
      if (!t) { endPara(); i += 1; continue; }
      // 주석(여러 줄 가능)
      if (t.startsWith("<!--")) {
        let j = i, body = ln;
        while (!body.includes("-->") && j + 1 < L.length) { j += 1; body += "\n" + L[j]; }
        const whole = body.trim();
        if (COMMENT.test(whole)) { endPara(); out.append(commentEl(COMMENT.exec(whole)[1], false)); i = j + 1; continue; }
      }
      // 코드 울타리
      if (/^(```|~~~)/.test(t)) {
        endPara();
        const fence = t.slice(0, 3), buf = [];
        i += 1;
        while (i < L.length && !L[i].trim().startsWith(fence)) { buf.push(L[i]); i += 1; }
        i += 1;
        const pre = node("pre", "mp-code");
        pre.append(node("code", null, buf.join("\n")));
        out.append(pre);
        continue;
      }
      // 수식 덩이
      if (t.startsWith("$$")) {
        endPara();
        const buf = [];
        let rest = t.slice(2);
        if (rest.endsWith("$$") && rest.length >= 2) { buf.push(rest.slice(0, -2)); i += 1; } else {
          if (rest) buf.push(rest);
          i += 1;
          while (i < L.length) {
            const s = L[i].trim();
            i += 1;
            if (s.endsWith("$$")) { if (s.length > 2) buf.push(s.slice(0, -2)); break; }
            buf.push(L[i - 1]);
          }
        }
        const m = node("div", "mp-math");
        m.append(node("span", "mp-math-tag", "수식 (LaTeX)"), node("code", null, buf.join("\n").trim()));
        out.append(m);
        continue;
      }
      // 제목
      const h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(t);
      if (h) { endPara(); out.append(inline(h[2], ctx, node(`h${h[1].length}`))); i += 1; continue; }
      // 그림만 있는 줄 — 문단에 끼우지 않고 따로
      const im = /^!\[([^\]]*)\]\(([^)\s]+)\)$/.exec(t);
      if (im) { endPara(); out.append(imgEl(im[1], im[2], ctx)); i += 1; continue; }
      // 가로줄
      if (/^([-*_])(\s*\1){2,}$/.test(t)) { endPara(); out.append(node("hr")); i += 1; continue; }
      // 표
      if (t.includes("|") && i + 1 < L.length && isSep(L[i + 1])) {
        endPara();
        const head = cells(ln), aligns = cells(L[i + 1]).map((c) => (/^:-+:$/.test(c) ? "center" : /-+:$/.test(c) ? "right" : ""));
        const rows = [];
        i += 2;
        while (i < L.length && L[i].trim() && L[i].includes("|")) { rows.push(cells(L[i])); i += 1; }
        out.append(tableEl(head, aligns, rows, ctx));
        continue;
      }
      // 인용
      if (t.startsWith(">")) {
        endPara();
        const buf = [];
        while (i < L.length && L[i].trim().startsWith(">")) { buf.push(L[i].trim().replace(/^>\s?/, "")); i += 1; }
        const q = node("blockquote");
        q.append(render(buf.join("\n"), ctx));
        out.append(q);
        continue;
      }
      // 목록
      if (ITEM.test(ln)) {
        endPara();
        const items = [];
        while (i < L.length) {
          const m = ITEM.exec(L[i]);
          if (m) { items.push({ ind: m[1].replace(/\t/g, "  ").length, mark: m[2], text: m[3] }); i += 1; continue; }
          // 목록 안에서 들여 쓴 이어지는 줄
          if (L[i].trim() && /^\s{2,}/.test(L[i]) && items.length) { items[items.length - 1].text += " " + L[i].trim(); i += 1; continue; }
          break;
        }
        out.append(listEl(items, ctx));
        continue;
      }
      para.push(ln);
      i += 1;
    }
    endPara();
    return out;
  }
  window.mdPreview = render;
})();
