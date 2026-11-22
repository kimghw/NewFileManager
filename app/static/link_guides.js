/* 매칭 지침 — 표 · 본문별(spec_병합 ② §5-6, 2026-11-22 사용자 "테이블, 본문별로 어떻게 매칭해야하는지 지침을 관리하고 LLM이 검토할때 이 부분을 검토할 수 있도록" ·
   "LLM 검토할때 매핑 참고하도록 지침을 해당 테이블에 넣어주고"): 목적 문서(연차보고서) 양식의 양식 정보 「자리 연결」 절에 적어 둔 「이 표 · 이 본문 자리는 원본의 어디와 어떻게 잇는다」 를
   자리마다 한 줄로 문서 옆 열에 보이고(2열 kind "linkGuides"), 더하고 · 고치고 · 지운다. 줄을 누르면 문서의 그 표 · 그 헤딩으로 간다. 같은 절의 연결 코멘트(날짜가 붙은 메모)도 여기서 남긴다.
   원본 · 저장 = 서버(app/link_guides.py · app/link_guides_api.py: GET · PUT · DELETE /api/docs/{id}/link-guides · 코멘트 POST …/merge-links/comments) — 양식 정보 파일이 바뀔 뿐 문서는 안 바뀐다.
   읽는 곳 = LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 그 자리를 볼 때. 스크립트의 동작을 바꾸는 설정이 아니다(화면에 그렇게 적는다).
   여는 곳 = 이관 「작업 개요」 의 「자리 연결」 줄의 「매칭 지침」 단추(app.js taskSteps — 전의 「연결 코멘트」 단추).
   기대는 app.js 의 이름: api · el · hBtn · hTable · hCell · hRowKeys · headsDlg · headsColClose · heads · divGo · state · toast · short · nf · H_JSON · PEEK. */
let lgDoc = null; // 지금 목록의 문서 {id, name}
let lgEdit = null; // 고치는 중인 것 {n(없으면 새 지침), kind, title, text} | null

const LG_KIND = { table: "표", body: "본문" };

function lgHere(id) { return !!id && !!(paraEl(id) || document.querySelector(`#doc table[data-tbl="${CSS.escape(id)}"], #doc td[data-cell="${CSS.escape(id)}"]`)); } // 그 자리(헤딩 문단 · 표)가 지금 화면의 문서에 있나

async function linkGuidesOpen(work, keep = false) { // work = {id, name}(목적 문서 — 보통 연차보고서). keep = 열려 있는 목록을 다시 그림
  const doc = work || lgDoc;
  if (!doc) { toast("목적 문서가 없습니다"); return; }
  if (!keep) lgEdit = null;
  lgDoc = { id: doc.id, name: doc.name };
  let got;
  try { got = await api(`/api/docs/${doc.id}/link-guides`); }
  catch (e) { toast(`매칭 지침을 읽지 못했습니다: ${e.message}`, true); return; }
  if (keep && heads.dlg !== "linkGuides") return; // 읽는 사이 다른 열로 바뀜
  lgDraw(got);
}

function lgDraw(got) {
  const doc = lgDoc, mine = doc.id === state.id, G = got.guides || [], canSave = got.canSave && !PEEK;
  const { tools, body, foot } = headsDlg("linkGuides", "매칭 지침 — 표/본문별",
    `${doc.name} · ${got.formInfo ? `양식 정보 「${got.formInfo.name}」 의 「자리 연결」 절` : "이 문서에 맞는 양식 정보가 아직 없습니다(지침을 남기면 만듭니다)"}`);
  tools.append(el("span", "muted", `지침 ${nf(G.length)}개(표 ${nf(G.filter((g) => g.kind === "table").length)} · 본문 ${nf(G.filter((g) => g.kind === "body").length)}) — LLM 검토가 그 표 · 그 본문 자리를 볼 때 이 글을 먼저 따릅니다`));
  if (canSave) tools.append(hBtn("＋ 지침", () => { lgEdit = { kind: "table", title: "", text: "" }; lgDraw(got); }, { title: "표나 본문 자리 하나에 대한 지침을 더합니다" }));
  body.append(el("div", "lk-cap", "LLM 검토(자리 연결 · 표 대응 · 빈 자리)가 읽는 판단 기준입니다 — 스크립트가 넣는 방식은 이 글로 바뀌지 않습니다(「N page 이내」 의 쪽 한도만 빈 자리 검토가 읽습니다)"));
  if (lgEdit) body.append(lgForm(got));
  for (const kind of ["table", "body"]) {
    const items = G.filter((g) => g.kind === kind);
    if (!items.length) continue;
    body.append(el("div", "lk-cap", `${LG_KIND[kind]} — 지침 ${nf(items.length)}`));
    const [tbl, tb] = hTable(["자리", "지침", ""]);
    tbl.classList.add("lk-table");
    for (const g of items) {
      const tr = el("tr", mine && g.places.length ? "go" : null);
      const place = g.places.length ? `이 문서의 자리 ${nf(g.places.length)}곳: ${g.places.map((p) => short(p.text, 40)).join(" · ")}` : "이 문서에는 그 제목의 자리가 없습니다(제목이 다르면 「고치기」 로 맞추세요)";
      const td0 = hCell(tr, `「${g.title}」${g.pages ? `\n${g.pages}쪽 이내` : ""}${g.places.length ? "" : "\n(자리 없음)"}`, null, place);
      td0.style.whiteSpace = "pre-wrap";
      const td = hCell(tr, g.text, null, g.text.length > 400 ? g.text : "");
      td.style.whiteSpace = "pre-wrap";
      const acts = el("td", "lk-nw");
      if (canSave) acts.append(hBtn("고치기", (e) => { e.stopPropagation(); lgEdit = { n: g.n, kind: g.kind, title: g.title, text: g.text }; lgDraw(got); }, { title: "이 지침의 글 · 자리 제목 · 종류를 고칩니다" }),
        hBtn("지우기", (e) => { e.stopPropagation(); lgDrop(g); }, { title: "이 지침을 양식 정보에서 지웁니다" }));
      tr.append(acts);
      if (mine && g.places.length) {
        tr.tabIndex = 0;
        tr.onclick = () => { for (const x of body.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); const p = g.places.find((x) => lgHere(x.id)) || g.places[0]; divGo({ key: p.id }, false); tr.focus({ preventScroll: true }); };
      }
      tb.append(tr);
    }
    hRowKeys(tb);
    body.append(tbl);
  }
  if (!G.length && !lgEdit) body.append(el("div", "lk-cap", "적어 둔 지침이 없습니다 — 「＋ 지침」 으로 표나 본문 자리마다 어떻게 이을지 남기세요"));
  const C = got.comments || [];
  body.append(el("div", "lk-cap", `연결 코멘트 ${nf(C.length)} — 날짜와 함께 쌓이는 메모(같은 절 끝에 · LLM 검토가 함께 읽습니다)`));
  if (C.length) {
    const [tbl, tb] = hTable(["날짜", "코멘트"]);
    tbl.classList.add("lk-table");
    for (const c of C) { const tr = el("tr"); hCell(tr, c.date, "lk-nw"); hCell(tr, c.text).style.whiteSpace = "pre-wrap"; tb.append(tr); }
    body.append(tbl);
  }
  if (canSave) {
    const line = el("div", "lg-note"), ta = el("textarea");
    ta.rows = 2;
    ta.placeholder = "코멘트 — 어느 표 · 단락을 사업계획서의 어디와 이을지(한 줄로 저장됩니다)";
    ta.setAttribute("aria-label", "연결 코멘트");
    line.append(ta, hBtn("코멘트 남기기", async () => {
      if (!ta.value.trim()) { toast("코멘트 글을 적으세요"); return; }
      try { await api(`/api/docs/${doc.id}/merge-links/comments`, { method: "POST", headers: H_JSON, body: JSON.stringify({ text: ta.value }) }); toast("코멘트를 남겼습니다"); linkGuidesOpen(null, true); }
      catch (e) { toast(`코멘트를 남기지 못했습니다: ${e.message}`, true); }
    }, { title: "양식 정보 「자리 연결」 절의 코멘트 목록 끝에 오늘 날짜로 더합니다" }));
    body.append(line);
  }
  foot.append(el("span", "muted", "양식 정보에 저장됩니다 — 같은 양식의 다른 작업에서도 읽습니다 · 문서는 안 바뀝니다"), hBtn("닫기", () => headsColClose()));
}

function lgForm(got) { // 지침 하나 더하기 · 고치기 — 종류 · 자리 제목 · 글
  const E = lgEdit, box = el("div", "lg-form");
  const kind = el("select");
  for (const [v, name] of Object.entries(LG_KIND)) { const o = el("option", null, name); o.value = v; kind.append(o); }
  kind.value = E.kind;
  kind.setAttribute("aria-label", "종류");
  const title = el("input");
  title.type = "text";
  title.value = E.title;
  title.placeholder = "자리의 제목 — 표의 소속 제목이나 본문 헤딩 글(예: 2-1. 기술개발 추진 일정)";
  title.setAttribute("aria-label", "자리의 제목");
  const text = el("textarea");
  text.rows = 5;
  text.value = E.text;
  text.placeholder = "지침 — 사업계획서의 어디에서 가져오는지 · 무엇을 넣고 무엇을 비우는지";
  text.setAttribute("aria-label", "지침 글");
  const keep = () => { E.kind = kind.value; E.title = title.value; E.text = text.value; };
  for (const x of [kind, title, text]) x.oninput = keep;
  const save = hBtn(E.n === undefined ? "지침 더하기" : "고친 글 저장", async () => {
    keep();
    if (!E.title.trim() || !E.text.trim()) { toast("자리의 제목과 지침 글을 적으세요"); return; }
    save.disabled = true;
    try {
      const next = await api(`/api/docs/${lgDoc.id}/link-guides`, { method: "PUT", headers: H_JSON, body: JSON.stringify({ kind: E.kind, title: E.title, text: E.text, ...(E.n === undefined ? {} : { n: E.n }) }) });
      lgEdit = null;
      toast("지침을 양식 정보에 저장했습니다 — 다음 LLM 검토부터 읽습니다");
      if (heads.dlg === "linkGuides") lgDraw(next);
    } catch (e) { save.disabled = false; toast(`지침을 저장하지 못했습니다: ${e.message}`, true); }
  }, { cls: "btn sm primary" });
  const row1 = el("div", "lg-row");
  row1.append(el("span", "muted", E.n === undefined ? "새 지침" : "지침 고치기"), kind, title);
  const row2 = el("div", "lg-row");
  row2.append(save, hBtn("그만두기", () => { lgEdit = null; lgDraw(got); }));
  box.append(row1, text, row2);
  return box;
}

async function lgDrop(g) {
  if (!confirm(`「${g.title}」 지침을 지울까요?\n양식 정보의 「자리 연결」 절에서 지워집니다(같은 양식의 다른 작업에서도).`)) return;
  try {
    const next = await api(`/api/docs/${lgDoc.id}/link-guides/${g.n}`, { method: "DELETE" });
    toast("지침을 지웠습니다");
    if (heads.dlg === "linkGuides") lgDraw(next);
  } catch (e) { toast(`지침을 지우지 못했습니다: ${e.message}`, true); }
}
