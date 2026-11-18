"use strict";
// 표 서식 점검 · 맞추기(spec_헤딩_추출 ② §19) — 표 모듈의 한 조각. 사용자 2026-11-17 "테이블은 열행헤더에 따른 서식. 폰트나 정렬, 여백, 줄간격등의 서식은 현재 관리 되지 않나?" ·
// "테이블 마다 공백일때 표현 패턴이 인식되어야 함 … 테이블 별로 작업을 해야 하지 않나" → 답 「표 구조 추출에 넣기」 · 「점검 + 맞추기」.
// 표 메뉴(table_menu.js) 「표 서식 점검…」 이 연다 → 2열 kind "tblStyle"(문서 옆 열 — 팝업 아님):
//   요약(자리 · 다른 서식 · 빈 값 표시) → 자리마다(머리행 · 머리열 · 열 · 합계행 · 빈 값) 대표 서식 한 줄 + 다른 서식 목록(칸 · 글 · 「무엇 지금 → 대표」 · 확인)
//   → 고른 것만 「맞추기」(한 트랜잭션 — 실행 취소 1개). 「확인」 이 붙은 것(글꼴 · 크기 · 굵게가 크게 다름 · 빈 칸에 표시 넣기)은 처음엔 고르지 않은 채다.
// app.js 가 주는 것: state·heads·el·api·toast·structOp·flushAll·headsDlg·hBtn·hFoot·hTable·nf·H_JSON. tables.js: xlBlock. 전역 이름은 tblStyle…·TST_… 만 쓴다.
// 서버 짝: app/tables_api.py `GET …/tables/{tid}/style` · `POST …/style/apply`, 판정 · 맞추기 app/table_style.py. index.html 이 table_fill.js 다음에 읽는다 — 이 파일이 없어도 다른 기능은 돈다.

const TST_SOURCE = { stage3: "칸 역할: 표 구조(3단계) 결과", draft: "칸 역할: 이 표의 스크립트 초안(표 구조를 아직 안 돌렸거나 그 뒤 표가 바뀜)" };
const tblStyle = { doc: null, picked: {} }; // picked[표 id] = Set(항목 키) — 문서를 다시 열기 전까지(열을 닫았다 열어도 고른 것이 남는다)
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { tableStyle: "표 서식 맞추기" }); // 「기록」 탭의 이름

const tblStyleUrl = (tid, tail = "") => `/api/docs/${encodeURIComponent(state.id)}/tables/${encodeURIComponent(tid)}/style${tail}`;

function tblStyleHit(cid) { // 줄에 올린 동안 문서의 그 칸을 칠한다(null = 걷기) — td.tst-hit — table-fill.css
  for (const e of document.querySelectorAll("#doc td.tst-hit")) e.classList.remove("tst-hit");
  if (!cid) return;
  for (const e of document.querySelectorAll(`#doc td[data-cell="${CSS.escape(cid)}"]`)) e.classList.add("tst-hit");
}
function tblStyleGo(tid, cid = null) { // 문서에서 그 칸(없으면 표)으로 — 열은 그대로(나란히 보기)
  const target = (cid && document.querySelector(`#doc td[data-cell="${CSS.escape(cid)}"]`)) || document.querySelector(`#doc table.tbl[data-tbl="${CSS.escape(tid)}"]`);
  if (!target) { toast("그 표가 지금 화면에 없습니다"); return; }
  target.scrollIntoView({ block: cid ? "center" : "start", behavior: "smooth" });
}
const tblStyleDiff = (o) => o.diff.map((x) => `${x.label} 지금 ${x.now} → 대표 ${x.want}`).join(" · ");

async function tblStyleView(tid) {
  if (!state.id) return;
  if (state.format === "docx") { toast("표 서식 점검은 지금 hwpx 문서만 됩니다"); return; }
  if (typeof xlBlock === "function" && !xlBlock(tid)) { toast("그 표가 지금 문서에 없습니다"); return; }
  const key = `${state.id}|${state.epoch}`;
  if (tblStyle.doc !== key) { tblStyle.doc = key; tblStyle.picked = {}; }
  const { tools, body } = headsDlg("tblStyle", `표 서식 · ${tid}`, "같은 자리(머리행 · 머리열 · 열 · 빈 값)의 칸끼리 글꼴 · 크기 · 정렬 · 줄 간격 · 여백이 같은지 봅니다 — 고른 곳만 대표에 맞춥니다");
  const seq = heads.seq, epoch = state.epoch;
  const live = () => seq === heads.seq && epoch === state.epoch;
  const wrap = el("div", "ta-wrap tst-wrap");
  body.append(wrap);
  tools.append(el("span", "muted", "점검은 문서를 바꾸지 않습니다 · 맞추기는 고른 곳만, 실행 취소 한 번으로 되돌립니다 · 장평 · 자간은 칸 폭 맞춤이라 견주지 않습니다"));
  const ident = el("div", "ta-ident"), acts = el("div", "ta-row"), sum = el("p", "hnote tst-sum"), emptyLine = el("p", "hnote tst-empty"), result = el("div", "tst-result");
  acts.append(hBtn("표 자리로", () => tblStyleGo(tid), { title: "문서에서 이 표로" }), hBtn("다시 점검", () => load(), { title: "지금 문서로 다시 봅니다(문서는 안 바뀜)" }));
  const quick = typeof commitQuickEl === "function" ? commitQuickEl("표 서식 점검") : ""; // 고친 부분 적용하기(spec_작업 ② §8 — 맞춘 뒤 고친 문단을 이 열에서 바로 확정 · 고친 것이 있을 때만 보임: app.js)
  wrap.append(ident, acts, quick, sum, emptyLine, result);
  if (quick) commitQuickSync();
  let view = null, busy = false;

  async function load() {
    hFoot("점검하는 중…", false);
    try {
      await flushAll(); // 타자 중인 글을 서버에 먼저
      const r = await api(tblStyleUrl(tid));
      if (!live()) return;
      view = r;
      const all = r.places.flatMap((p) => p.odd);
      const old = tblStyle.picked[tid];
      const keys = new Set(all.map((o) => o.key));
      tblStyle.picked[tid] = old ? new Set([...old].filter((k) => keys.has(k))) : new Set(all.filter((o) => !o.check).map((o) => o.key)); // 처음엔 확인 없는 것만 고른 채
      draw();
    } catch (e) {
      if (!live()) return;
      sum.textContent = e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「표 서식 점검」 을 쓸 수 있습니다" : `점검하지 못했습니다: ${e.message}`;
      result.textContent = "";
      hFoot(sum.textContent);
    }
  }

  function draw() {
    const r = view, k = r.counts, e = r.empty || {}, picked = tblStyle.picked[tid];
    ident.replaceChildren(el("b", null, tid), el("span", null, `${r.rows}×${r.cols}`), el("span", "hb", r.source === "stage3" ? "표 구조 결과" : "초안"));
    ident.lastChild.title = TST_SOURCE[r.source] || "";
    const withOdd = r.places.filter((p) => p.odd.length);
    sum.textContent = k.odd ? `자리 ${nf(k.places)} · 다른 서식 ${nf(k.odd)}곳(자리 ${nf(withOdd.length)})${k.check ? ` · 확인 ${nf(k.check)}` : ""}` : `자리 ${nf(k.places)} — 다른 서식이 없습니다`;
    sum.title = "자리 = 같은 서식을 쓸 칸의 묶음 — 머리행 · 머리열 · 합계행 · 열(값 칸) · 빈 값\n대표 = 그 자리에서 가장 많이 쓴 서식 · 다른 서식 = 대표와 다른 문단 · 칸\n확인 = 글꼴 · 크기 · 굵게가 크게 다르거나(제목 · 강조일 수 있음) 빈 칸에 표시를 넣는 것 — 처음엔 고르지 않습니다";
    const counts = Object.entries(e.counts || {}).map(([m, n]) => `「${m}」 ${nf(n)}`).join(" · ");
    emptyLine.textContent = e.mark
      ? `빈 값 표시 「${e.mark}」 — ${counts}${e.blanks ? ` · 빈 칸 ${nf(e.blanks)}${e.fillBlanks ? "(표시를 넣을지 확인)" : "(쓸 자리로 보고 둠)"}` : ""}${e.mixed ? " · 줄표와 낱말 표시가 섞여 있습니다(알리기만)" : ""}`
      : e.blanks ? `빈 값 표시 없음 — 빈 칸 ${nf(e.blanks)}(쓸 자리로 보고 둠)` : "빈 값 칸 없음";
    emptyLine.title = "빈 값 칸 = 글이 없음 · 줄표 홀로(「-」 「–」 「—」) · 「해당없음」 「없음」 「N/A」 — 가장 많이 쓴 보이는 표시가 이 표의 표시입니다\n줄표 글자가 다른 칸은 표시로 맞추고, 빈 칸은 보이는 표시가 더 많을 때만 표시를 넣을지 묻습니다";
    result.textContent = "";
    hFoot(`표 ${tid} · 다른 서식 ${nf(k.odd)} · 문서 차례 ${r.rev}`, false);
    if (!k.odd) { result.append(el("p", "hnote", "같은 자리의 칸이 모두 대표와 같은 서식입니다.")); return; }

    const bar = el("div", "ta-row tst-bar"), count = el("span", "muted");
    const applyBtn = hBtn("", () => apply(), { cls: "btn sm primary", title: "고른 곳을 그 자리의 대표 서식으로 바꿉니다 — 한 번의 편집(도구 줄 「실행 취소」 로 한꺼번에 되돌림). 점검한 뒤 바뀐 곳은 건너뜁니다" });
    const boxes = [];
    const sync = () => {
      const n = boxes.filter(([cb]) => cb.checked).length;
      applyBtn.textContent = `고른 ${nf(n)}곳 맞추기`;
      applyBtn.disabled = !n || busy || state.busy;
      count.textContent = `${nf(n)} / ${nf(k.odd)}`;
    };
    const pick = (fn) => { for (const [cb, o] of boxes) { cb.checked = fn(o); if (cb.checked) picked.add(o.key); else picked.delete(o.key); } sync(); };
    bar.append(applyBtn, hBtn("확인 빼고 모두", () => pick((o) => !o.check), { title: "「확인」 이 붙지 않은 다른 서식만 고릅니다" }), hBtn("모두", () => pick(() => true)), hBtn("모두 풀기", () => pick(() => false)), count);
    result.append(bar);

    for (const p of withOdd) {
      const d = el("details", "hblock tst-place");
      d.open = true;
      const s = el("summary", null);
      s.append(el("b", null, p.name), el("span", "muted", ` · 칸 ${nf(p.cells)} · 다른 서식 ${nf(p.odd.length)}`));
      d.append(s);
      if (p.rep && p.rep.text) d.append(el("p", "hnote tst-rep", `대표 — ${p.rep.text}`));
      const [t, tb] = hTable(["", "칸", "글", "다른 점"]);
      t.classList.add("tst-list");
      for (const o of p.odd) {
        const tr = el("tr", o.check ? "warn" : null), cb = el("input");
        cb.type = "checkbox";
        cb.checked = picked.has(o.key);
        cb.setAttribute("aria-label", `${o.ref} 맞추기 고르기`);
        cb.onchange = () => { if (cb.checked) picked.add(o.key); else picked.delete(o.key); sync(); };
        boxes.push([cb, o]);
        const c0 = el("td"), c1 = el("td"), c2 = el("td", "wrap tst-text", o.text || (o.what === "blank" ? "(빈 칸)" : "")), c3 = el("td", "wrap tst-diff", tblStyleDiff(o));
        c0.append(cb);
        const go = el("button", "hlink", o.ref);
        go.type = "button";
        go.title = "문서에서 그 칸으로";
        go.onclick = () => tblStyleGo(tid, o.cell);
        c1.append(go);
        if (o.what === "cell") c1.append(el("span", "hb", "칸"));
        if (o.check) { const w = el("span", "hb und", "확인"); w.title = o.why || ""; c3.append(" ", w); }
        tr.append(c0, c1, c2, c3);
        tr.addEventListener("mouseenter", () => tblStyleHit(o.cell));
        tr.addEventListener("mouseleave", () => tblStyleHit(null));
        tb.append(tr);
      }
      d.append(t);
      result.append(d);
    }
    const same = r.places.filter((p) => !p.odd.length && p.cells > 1);
    if (same.length) result.append(el("p", "hnote muted", `대표와 같은 자리: ${same.map((p) => p.name).join(" · ")}`));
    sync();

    async function apply() {
      const keys = boxes.filter(([cb]) => cb.checked).map(([, o]) => o.key);
      if (!keys.length || busy) return;
      busy = true;
      sync();
      tblStyleHit(null);
      const out = await structOp(`tables/${encodeURIComponent(tid)}/style/apply`, { keys }); // 대기 중 글 반영 → 서버 편집(OWPML 검사) → 바뀐 블록만 다시 그림 · 실패는 structOp 가 알림
      busy = false;
      if (!out || !out.styled) { if (live()) sync(); return; }
      const st = out.styled;
      for (const kk of st.done || []) picked.delete(kk);
      toast(`표 ${tid} — ${nf((st.done || []).length)}곳을 대표 서식에 맞췄습니다${(st.skipped || []).length ? ` · 건너뜀 ${nf(st.skipped.length)}(${st.skipped[0].why})` : ""} · 도구 줄의 실행 취소로 되돌릴 수 있습니다`);
      if (live()) load(); // 맞춘 뒤 다시 점검
    }
  }

  await load();
}
