"use strict";
/* 표 제목을 템플릿의 L1 으로(spec_hwpx_웹편집 ② §8-7 — 서버 app/outline_lift.py · outline_lift_api.py).
   2026-11-16 사용자 "그리고 이 테이블도 템플릿의 L1 으로 할 수 있도록 해줘. 이런 문서들이 꽥 많거든" → 답 「같은 꼴 표를 한 번에」 · 「표시·구조 + Enter 먼저」.
   「템플릿 관계」 열·「템플릿」 탭의 템플릿 줄 머리(app.js tplTreeDraw 의 make 가 olLiftTools 를 부른다 — outline_match.js olmTplTools 다음):
   · 「표를 L1 으로」 단추 → 그 아래 한 줄 펼침(팝업 아님 — design.md §2): 이 템플릿의 첫 레벨 줄 바로 위에 있는 **1칸 제목 표**를 같은 꼴끼리 묶어 보이고(표 제목마다 문서로 가는 줄),
     묶음마다 「L1 으로 넣기(n곳)」 — 그 꼴의 표를 **모두** 한 번에 넣는다(POST …/outline/lift). 넣으면 여백 표시가 표 「T1 L1」 · □ 「T1 L2」 … 로 바뀐다(문서는 안 바뀜 · 「실행 취소」 로 되돌림).
   · 넣은 템플릿: 표지 「L1 = 표 제목 n곳」 + 「떼기」(POST …/outline/unlift) · 단추는 「표 더 넣기」(다른 꼴 · 새로 생긴 같은 꼴 표).
   · 종속 템플릿·서식 종속 템플릿과 그런 템플릿이 걸린 템플릿은 못 넣는다(펼친 줄에 까닭).
   부르기·다시 그리기는 outline_match.js 의 olmMergeCall(오버레이 요약 갈아 끼움 · 여백 표시 · 트리 다시 그림 · 알림)을 그대로 쓴다. outline_match.js 다음에 읽힌다. */
const OLL = { open: new Set(), epoch: -1, seq: 0 };

function olLiftTools(li, row, id) {
  const t = typeof olmTpl === "function" ? olmTpl(id) : null;
  if (!t || t.comp || t.vari || (!t.lines && !t.lift)) return; // 종속 템플릿은 원래 템플릿에서 · 줄이 없는 템플릿은 넣을 자리가 없다
  if (OLL.epoch !== state.epoch) { OLL.open.clear(); OLL.epoch = state.epoch; }
  const key = String(id);
  if (t.lift) {
    const chip = el("span", "olm-chip oll-chip", `L1 = 표 제목 ${nf(t.lift.tables)}곳`);
    chip.title = `1칸 제목 표 ${nf(t.lift.tables)}곳을 이 템플릿의 L1 로 넣었습니다 — 글 레벨은 L2 부터(「${(t.chain || []).slice(1).join(" › ")}」). 표 제목 줄에서 Enter = 표 아래에 L2 새 줄 · 문서는 안 바뀌었습니다`;
    row.append(chip, hBtn("떼기", () => olLiftUndo(id), { title: `표 제목 줄을 빼고 T${t.no} 의 레벨을 되돌립니다(□ L2 → L1 … · 「실행 취소」 로도 됨)`, cls: "btn sm olm-btn oll-un" }));
  }
  const form = el("div", "olm-merge oll-form");
  form.hidden = !OLL.open.has(key);
  const btn = hBtn(t.lift ? "표 더 넣기" : "표를 L1 으로", () => {
    form.hidden = !form.hidden;
    btn.setAttribute("aria-expanded", String(!form.hidden));
    if (form.hidden) OLL.open.delete(key); else { OLL.open.add(key); olLiftLoad(id, form); }
  }, { title: `T${t.no} 의 첫 레벨 줄 바로 위에 있는 1칸 제목 표(제목 상자)를 이 템플릿의 L1 로 넣습니다 — 같은 꼴 표를 한 번에. 표 = T${t.no} L1, 지금의 L1 줄은 L2 가 됩니다(문서는 안 바뀜)`, cls: "btn sm olm-btn oll-btn" });
  btn.setAttribute("aria-expanded", String(!form.hidden));
  row.append(btn);
  li.append(form);
  if (!form.hidden) olLiftLoad(id, form);
}

async function olLiftLoad(id, form) { // 후보를 읽어 펼친 줄에 그린다 — 늦게 온 답(다른 문서 · 그 사이 다시 누름)은 버린다
  const epoch = state.epoch, seq = (OLL.seq += 1);
  form.dataset.seq = String(seq);
  form.replaceChildren(el("p", "hnote", "제목 표를 찾는 중…"));
  let d;
  try { d = await api(`/api/docs/${state.id}/outline/lift?tpl=${encodeURIComponent(id)}`); }
  catch (e) { if (epoch === state.epoch && form.dataset.seq === String(seq)) form.replaceChildren(el("p", "hnote warn", e.message)); return; }
  if (epoch !== state.epoch || form.dataset.seq !== String(seq)) return;
  form.replaceChildren();
  if (d.blocked) { form.append(el("p", "hnote warn", d.blocked)); return; }
  if (!d.groups.length) {
    form.append(el("p", "hnote", d.lifted ? "더 넣을 제목 표가 없습니다 — 이 템플릿의 글 줄 바로 위에 있는 1칸 제목 표는 모두 넣었습니다."
      : `T${d.no} 의 첫 레벨 줄 바로 위에 1칸 제목 표가 없습니다 — 여러 칸 표 · 글이 긴 상자 · 레터가 있는 제목(이미 개요 줄)은 제목 표로 보지 않습니다.`));
    return;
  }
  for (const g of d.groups) {
    const box = el("div", "oll-g");
    const look = [g.look.font, g.look.sizePt ? `${g.look.sizePt}pt` : "", g.look.bold ? "굵게" : ""].filter(Boolean).join(" ");
    const head = el("div", "olm-gh");
    head.append(el("b", null, `1칸 제목 표 ${nf(g.count)}곳`), el("span", "muted", look ? ` · ${look}` : ""), g.lifted ? el("span", "olm-chip", "이미 넣은 꼴") : "",
      hBtn(`L1 으로 넣기(${nf(g.count)}곳)`, () => olLift(id, g.sig, g.count), { title: `이 꼴의 제목 표 ${nf(g.count)}곳을 모두 T${d.no} 의 L1 로 — 그 아래 줄들은 L2 부터가 됩니다(문서는 안 바뀜 · 「실행 취소」·「떼기」 로 되돌림)`, cls: "btn sm olm-btn oll-go" }));
    box.append(head);
    const ul = el("ul", "hlist oll-list");
    for (const tb of g.tables.slice(0, 12)) {
      const li = el("li");
      li.append(headsParaLink(tb.para, tb.text || "(빈 제목)", 44, `표 ${tb.table} — 누르면 문서의 그 표로`));
      ul.append(li);
    }
    if (g.tables.length > 12) ul.append(el("li", "muted", `… ${nf(g.tables.length - 12)}곳 더`));
    box.append(ul);
    form.append(box);
  }
}

function olLift(id, sig, n) {
  const t = olmTpl(id);
  OLL.open.delete(String(id));
  return olmMergeCall("lift", { tpl: String(id), sig },
    { focus: () => olmKey(id),
      msg: (r) => `제목 표 ${nf(((r.lifted || {}).tables || []).length || n)}곳을 T${t ? t.no : id} 의 L1 로 넣었습니다 — 글 줄은 L2 부터(문서는 안 바뀜 · 「실행 취소」·「떼기」 로 되돌림). 표 제목 줄에서 Enter = 표 아래에 새 줄` });
}
function olLiftUndo(id) {
  const t = olmTpl(id);
  return olmMergeCall("unlift", { tpl: String(id) },
    { focus: () => olmKey(id), msg: (r) => `표 제목 줄 ${nf((r.unlifted || {}).tables)}곳을 뺐습니다 — T${t ? t.no : id} 의 레벨이 넣기 전으로 돌아갔습니다` });
}
