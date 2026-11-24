/* 작성 지침 목록(spec_작업 ② §21 「작성 지침 저장」) — 작업에 저장해 둔 양식의 작성 지침(작성 요령 표 · <참고 N> 자료 · ※ 안내 · 각주 번호가 가리키는 작성 요령 항목)을
   헤딩별 · 표별로 문서 옆 열에 보인다(2열 kind "formGuides"). 4단계 「작성요령 삭제」 가 문서에서 지운 뒤에도 저장본은 남는다 — 그때는 줄을 눌러도 지침의 자리는 없고 그 헤딩 · 표로 간다.
   모으기 · 저장 = 서버(app/form_guides.py · app/form_guides_api.py: GET·POST /api/docs/{id}/form-guides) · 여는 곳 = 이관 「작업 개요」 의 「헤딩 · 표 분석」 줄(app.js taskSteps).
   문서를 바꾸지 않는다. 기대는 app.js 의 이름: api · el · hBtn · hTable · hCell · hRowKeys · headsDlg · headsColClose · heads · divGo · paraEl · state · toast · short · nf · fmtWhen. */
let fgView = "headings"; // 보는 묶음 — "headings"(헤딩별) | "tables"(표별) · 이 화면에서만 기억
let fgDoc = null; // 지금 목록의 문서 {id, name}

const FG_KIND = { tables: "작성 요령 표", refs: "<참고 N> 자료", notes: "※ 안내", boxes: "안내 상자", hints: "설명 줄" };

function fgHere(id) { return !!id && !!(paraEl(id) || document.querySelector(`#doc [data-id="${CSS.escape(id)}"], #doc td[data-cell="${CSS.escape(id)}"]`)); } // 그 블록이 지금 화면의 문서에 있나

async function formGuidesList(work, keep = false) { // work = {id, name}(보통 연차보고서). keep = 열려 있는 목록을 다시 그림(보기 바꿈)
  const doc = work || fgDoc;
  if (!doc) return;
  fgDoc = { id: doc.id, name: doc.name };
  let got;
  try { got = await api(`/api/docs/${doc.id}/form-guides`); }
  catch (e) { toast(`작성 지침을 읽지 못했습니다: ${e.message}`, true); return; }
  if (keep && heads.dlg !== "formGuides") return; // 읽는 사이 다른 열로 바뀜
  const S = got.saved, G = got.groups || {}, c = (S && S.counts) || {}, mine = doc.id === state.id;
  const { tools, body, foot } = headsDlg("formGuides", "작성 지침 — 헤딩/표별", `${doc.name} · ${mine ? "줄을 누르면 문서의 그 자리로(지운 뒤에는 그 헤딩 · 표로)" : "그 문서를 열면 줄을 눌러 자리로 갑니다"}`);
  if (!S || !(c.items || c.marks)) {
    body.append(el("div", "lk-cap", "저장한 작성 지침이 없습니다 — 양식에 작성 요령 표 · <참고 N> 자료 · ※ 안내가 없거나 아직 모으지 않았습니다"));
    foot.append(hBtn("닫기", () => headsColClose()));
    return;
  }
  const pick = (v, label, n) => { const b = hBtn(`${label} ${nf(n)}`, () => { fgView = v; formGuidesList(null, true); }, { cls: "btn sm" + (fgView === v ? " primary" : ""), title: `${label}로 묶어 봅니다` }); b.setAttribute("aria-pressed", String(fgView === v)); return b; };
  tools.append(pick("headings", "헤딩별", (G.headings || []).length), pick("tables", "표별", (G.tables || []).length),
    el("span", "muted", `지침 ${nf(c.items)}개${c.marks ? ` · 각주 번호 ${nf(c.marksLinked)}/${nf(c.marks)}개가 작성 요령 항목에 이어짐` : ""}${S.at ? ` · 저장 ${fmtWhen(S.at)}` : ""}`));
  const groups = (fgView === "tables" ? G.tables : G.headings) || [];
  const row = (tb, kind, text, ids, title = "") => {
    const tr = el("tr", mine ? "go" : null);
    hCell(tr, kind, "lk-nw");
    const td = hCell(tr, text, null, title);
    td.style.whiteSpace = "pre-wrap"; // 작성 요령 항목은 줄마다 번호다 — 줄바꿈을 살린다
    if (mine) {
      tr.tabIndex = 0;
      tr.onclick = () => { for (const x of body.querySelectorAll("tr.sel")) x.classList.remove("sel"); tr.classList.add("sel"); divGo({ key: ids.find(fgHere) || ids[0] }, false); tr.focus({ preventScroll: true }); };
    }
    tb.append(tr);
  };
  const cut = (t, n = 600) => (t.length > n ? t.slice(0, n) + " …" : t); // 작성 요령 표는 수천 자 — 열에는 앞부분만(전체는 칸의 풍선 도움말)
  const draw = (name, own, items, marks) => {
    body.append(el("div", "lk-cap", `${name} — 지침 ${nf(items.length)}${marks.length ? ` · 각주 번호 ${nf(marks.length)}` : ""}`));
    const [tbl, tb] = hTable(["종류", "지침"]);
    tbl.classList.add("lk-table");
    for (const it of items) row(tb, FG_KIND[it.kind] || it.name || it.kind, cut(it.text || ""), [it.id, own], (it.text || "").length > 600 ? it.text : "");
    for (const m of marks) row(tb, `${m.no})`, `${short(m.label, 40)}${m.text ? `\n→ ${cut(m.text, 300)}` : "\n→ (이어진 작성 요령 항목 없음)"}`, [m.at, own], m.text && m.text.length > 300 ? m.text : "");
    hRowKeys(tb);
    body.append(tbl);
  };
  for (const g of groups) draw(fgView === "tables" ? `표 「${short(g.label, 50)}」` : `「${short(g.text, 60)}」`, g.id, g.items || [], g.marks || []);
  const loose = G.loose || [];
  if (loose.length) draw("헤딩 · 표를 못 정한 것", "", loose.filter((x) => x.what === "items"), loose.filter((x) => x.what === "marks"));
  if (!groups.length && !loose.length) body.append(el("div", "lk-cap", fgView === "tables" ? "표에 붙은 지침이 없습니다 — 「헤딩별」 로 보세요" : "헤딩에 붙은 지침이 없습니다(분석 전에 모았거나 문서 맨 앞의 지침) — 「표별」 로 보세요"));
  foot.append(el("span", "muted", "작업에 저장해 둔 것입니다 — 문서에서 지워도 남습니다"), hBtn("닫기", () => headsColClose()));
}
