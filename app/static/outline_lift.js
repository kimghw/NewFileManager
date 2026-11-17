"use strict";
/* 표 제목을 템플릿의 레벨로(spec_hwpx_웹편집 ② §8-7 — 서버 app/outline_lift.py · outline_lift_api.py).
   2026-11-16 사용자 "그리고 이 테이블도 템플릿의 L1 으로 할 수 있도록 해줘. 이런 문서들이 꽥 많거든" → 답 「같은 꼴 표를 한 번에」 · 「표시·구조 + Enter 먼저」.
   같은 날 넓힘(② §8-7 「넓힘」) — 사용자 "테이블 1개 행 또는 3개 행에 3. N 이런식으로 헤딩을 주는 경우 … 동일한 테이블 서식과 헤딩 서식을 가지고 있으면" → 답 「여러 칸·3행 표까지」:
   제목 표 = 1칸 상자 · 번호 칸 + 제목 칸 띠 · 3행 표 · 같은 꼴이면 아래에 템플릿 줄이 없는 표도 · 표 레벨 여러 층(띠 › 상자 › □ — 층마다 레벨).
   「템플릿 관계」 열·「템플릿」 탭의 템플릿 줄 머리(app.js tplTreeDraw 의 make 가 olLiftTools 를 부른다 — outline_match.js olmTplTools 다음):
   · 「표를 L1 으로」 단추 → 그 아래 한 줄 펼침(팝업 아님 — design.md §2): 이 템플릿의 줄(표 줄 · 첫 글 레벨 줄) 바로 위에 있는 **제목 표**를 같은 꼴끼리 묶어 보이고(표 제목마다 문서로 가는 줄),
     묶음마다 「L{k} 으로 넣기(n곳)」(새 표 레벨 — 그 레벨부터 한 칸씩 밀림) · 「L{k} 에 더 넣기(n곳)」(있는 표 레벨) — 그 꼴의 표를 **모두** 한 번에 넣는다(POST …/outline/lift).
     넣으면 여백 표시가 표 「T1 L1」 · □ 「T1 L2」 … 로 바뀐다(문서는 안 바뀜 · 「실행 취소」 로 되돌림). 더 넣을 묶음이 있으면(그 위의 제목 표) 펼친 줄을 닫지 않는다.
   · 넣은 템플릿: 표지 「L1 = 표 제목 n곳」(층이 둘 이상이면 「L1~L{d} = …」) + 「떼기」(POST …/outline/unlift — 표 레벨 모두) · 단추는 「표 더 넣기」(다른 꼴 · 그 위의 제목 표 · 새로 생긴 같은 꼴 표).
   · 종속 템플릿·서식 종속 템플릿과 그런 템플릿이 걸린 템플릿은 못 넣는다(펼친 줄에 까닭).
   부르기·다시 그리기는 outline_match.js 의 olmMergeCall(오버레이 요약 갈아 끼움 · 여백 표시 · 트리 다시 그림 · 알림)을 그대로 쓴다. outline_match.js 다음에 읽힌다. */
const OLL = { open: new Set(), epoch: -1, seq: 0 };

function ollDepth(t) { return t && t.lift ? t.lift.depth || 1 : 0; } // 표 레벨 수
function ollShape(sh) { // 꼴 이름 — 「1칸 제목 표」 · 「1행 2칸 제목 표」 · 「3행 제목 표」
  if (!sh || (sh.rows === 1 && sh.cells === 1)) return "1칸 제목 표";
  return sh.rows === 1 ? `1행 ${nf(sh.cells)}칸 제목 표` : `${nf(sh.rows)}행 제목 표`;
}

function olLiftTools(li, row, id) {
  const t = typeof olmTpl === "function" ? olmTpl(id) : null;
  if (!t || t.comp || t.vari || (!t.lines && !t.lift)) return; // 종속 템플릿은 원래 템플릿에서 · 줄이 없는 템플릿은 넣을 자리가 없다
  if (t.kind === "band") { // 띠 표 템플릿(「별첨N」 — spec_헤딩_추출 ② §6 「띠 표 줄」) — 줄이 이미 표다(표를 더 끼우지 않는다): 표지만
    const chip = el("span", "olm-chip oll-chip", "L1 = 별첨·부록 표 제목");
    chip.title = `「${(t.chain || ["?"])[0]}」 칸과 제목 칸으로 된 표(「별첨2 | 제목」)를 헤딩 추출이 스스로 이 템플릿의 줄로 잡았습니다 — 문서 맨 위의 줄이고, 그 아래 줄은 다음 별첨·부록 표나 장이 올 때까지 이 줄 아래에 매달립니다`;
    row.append(chip);
    return;
  }
  if (OLL.epoch !== state.epoch) { OLL.open.clear(); OLL.epoch = state.epoch; }
  const key = String(id), d = ollDepth(t);
  if (t.lift) {
    const chip = el("span", "olm-chip oll-chip", `L1${d > 1 ? `~L${d}` : ""} = 표 제목 ${nf(t.lift.tables)}곳`);
    chip.title = `제목 표 ${nf(t.lift.tables)}곳을 이 템플릿의 표 레벨(L1${d > 1 ? `~L${d}` : ""})로 넣었습니다 — 글 레벨은 L${d + 1} 부터(「${(t.chain || []).slice(d).join(" › ")}」). 표 제목 줄에서 Enter = 표 아래에 L${d + 1} 새 줄 · 문서는 안 바뀌었습니다`;
    row.append(chip, hBtn("떼기", () => olLiftUndo(id), { title: `표 제목 줄을 모두 빼고 T${t.no} 의 레벨을 되돌립니다(□ L${d + 1} → L1 … · 「실행 취소」 로도 됨)`, cls: "btn sm olm-btn oll-un" }));
  }
  const form = el("div", "olm-merge oll-form");
  form.hidden = !OLL.open.has(key);
  const btn = hBtn(t.lift ? "표 더 넣기" : "표를 L1 으로", () => {
    form.hidden = !form.hidden;
    btn.setAttribute("aria-expanded", String(!form.hidden));
    if (form.hidden) OLL.open.delete(key); else { OLL.open.add(key); olLiftLoad(id, form); }
  }, { title: `T${t.no} 의 줄 바로 위에 있는 제목 표(1칸 상자 · 번호 칸 + 제목 칸 띠 · 3행 표)를 이 템플릿의 표 레벨로 넣습니다 — 같은 꼴 표를 한 번에. 표 = T${t.no} L1, 지금의 L1 줄은 L2 가 됩니다(문서는 안 바뀜)`, cls: "btn sm olm-btn oll-btn" });
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
    form.append(el("p", "hnote", d.lifted ? "더 넣을 제목 표가 없습니다 — 이 템플릿의 줄 바로 위에 있는 제목 표와 그 꼴의 표는 모두 넣었습니다."
      : `T${d.no} 의 첫 레벨 줄 바로 위에 제목 표가 없습니다 — 글 있는 칸이 셋 이상인 표 · 글이 긴 상자 · 레터가 있는 제목(이미 개요 줄)은 제목 표로 보지 않습니다.`));
    return;
  }
  for (const g of d.groups) {
    const box = el("div", "oll-g");
    const look = [g.look.font, g.look.sizePt ? `${g.look.sizePt}pt` : "", g.look.bold ? "굵게" : ""].filter(Boolean).join(" ");
    const head = el("div", "olm-gh");
    const join = g.lifted || !g.new; // 있는 표 레벨에 더 넣기(레벨은 안 밀림)
    head.append(el("b", null, `${ollShape(g.shape)} ${nf(g.count)}곳${g.shape && g.shape.num ? "(번호 칸)" : ""}`), el("span", "muted", look ? ` · ${look}` : ""), g.lifted ? el("span", "olm-chip", "이미 넣은 꼴") : "",
      hBtn(`L${g.level} ${join ? "에 더" : "으로"} 넣기(${nf(g.count)}곳)`, () => olLift(id, g.sig, g.count, g.level),
        { title: join ? `이 꼴의 제목 표 ${nf(g.count)}곳을 모두 T${d.no} 의 L${g.level}(표 제목 레벨)에 더 넣습니다 — 다른 레벨은 그대로(문서는 안 바뀜 · 「실행 취소」·「떼기」 로 되돌림)`
          : `이 꼴의 제목 표 ${nf(g.count)}곳을 모두 T${d.no} 의 L${g.level} 로 — 지금의 L${g.level} 부터는 한 칸씩 밀립니다(문서는 안 바뀜 · 「실행 취소」·「떼기」 로 되돌림)`, cls: "btn sm olm-btn oll-go" }));
    box.append(head);
    const ul = el("ul", "hlist oll-list");
    for (const tb of g.tables.slice(0, 12)) {
      const li = el("li");
      li.append(headsParaLink(tb.para, `${tb.num ? `${tb.num} ` : ""}${tb.text || "(빈 제목)"}`, 44, `표 ${tb.table} — 누르면 문서의 그 표로`));
      if (!tb.under) { // 닻이 없는 표 — 꼴이 같아 함께 든다
        const lone = el("span", "muted oll-lone", " · 아래에 이 템플릿의 줄 없음");
        lone.title = "이 표 바로 아래에는 이 템플릿의 줄이 없습니다 — 꼴(표 서식 + 제목 글 서식)이 같아 같은 레벨의 표 제목으로 함께 넣습니다";
        li.append(lone);
      }
      ul.append(li);
    }
    if (g.tables.length > 12) ul.append(el("li", "muted", `… ${nf(g.tables.length - 12)}곳 더`));
    box.append(ul);
    form.append(box);
  }
}

function olLift(id, sig, n, level) {
  const t = olmTpl(id);
  return olmMergeCall("lift", { tpl: String(id), sig },
    { focus: (r) => { // 더 넣을 묶음(그 위의 제목 표)이 있으면 펼친 줄을 닫지 않는다 — 다시 그릴 때 다음 후보를 읽는다
        if ((r.lifted || {}).more) OLL.open.add(String(id)); else OLL.open.delete(String(id));
        return olmKey(id);
      },
      msg: (r) => {
        const x = r.lifted || {};
        return `제목 표 ${nf((x.tables || []).length || n)}곳을 T${t ? t.no : id} 의 L${x.level || level || 1} 로 넣었습니다 — 글 줄은 L${(x.levels || [2])[0]} 부터(문서는 안 바뀜 · 「실행 취소」·「떼기」 로 되돌림). 표 제목 줄에서 Enter = 표 아래에 새 줄`
          + (x.more ? ` · 더 넣을 수 있는 제목 표 묶음 ${nf(x.more)}개가 아래에 보입니다` : "");
      } });
}
function olLiftUndo(id) {
  const t = olmTpl(id);
  return olmMergeCall("unlift", { tpl: String(id) },
    { focus: () => olmKey(id), msg: (r) => `표 제목 줄 ${nf((r.unlifted || {}).tables)}곳을 뺐습니다 — T${t ? t.no : id} 의 레벨이 넣기 전으로 돌아갔습니다` });
}
