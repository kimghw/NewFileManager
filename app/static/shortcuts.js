/* 단축키 설명 — 도구 줄 「단축키 설명」 아이콘 단추(#shortcutsBtn) → 문서 옆 2열(#headsDlg, kind "shortcuts")에 키보드·마우스 조작 목록(spec_hwpx_웹편집 ② §2 「단축키 설명」).
   옛 도구 줄 키 안내(#editHint — 한 줄 글이라 좁으면 말줄임으로 잘렸다)를 대신한다. 목록은 아래 SHORTCUTS 가 원본 — 키 처리를 고치면 여기도 고친다:
   글 고치기·개요 줄 = app.js bindEditing · 표 칸 = table_edit.js bindCellSelect · 문단 묶음 = table_make.js tpkBind · 엑셀식 보기 = tables.js xlKey·xlEdit · 옆 열 폭 = app.js makeColSizer.
   app.js 다음에 읽힌다($·el·state·heads·headsDlg·headsColClose·colFolded 를 쓴다). headsDlg·headsColClose 에 고리를 더하지 않고 열 요소를 지켜본다(table_make.js 와 같은 방식). */

// 줄 = { k: [키 묶음…], at: 어디서(선택), d: 하는 일 }. 키 묶음은 「+」 로 이은 키(각각 <kbd>) — 「|」 는 그 자리의 여러 키(「Ctrl+B|I|U」), 「@」 로 시작하면 마우스 동작(글 그대로).
const SHORTCUTS = [
  { id: "edit", name: "글 고치기", note: "문단을 눌러 커서를 둔 뒤", rows: [
    { k: ["Enter"], d: "커서 자리에서 문단 나누기 — 개요 줄에서는 하위 레벨 줄(아래 「개요 줄」)" },
    { k: ["Shift+Enter"], d: "문단 안에서 줄 바꿈" },
    { k: ["Backspace"], at: "문단 맨 앞에서", d: "앞 문단과 합치기" },
    { k: ["Delete"], at: "문단 맨 끝에서", d: "뒤 문단과 합치기" },
    { k: ["Ctrl+B|I|U"], d: "굵게 · 기울임 · 밑줄 — 고른 글자에, 고르지 않았으면 문단 전체에" },
    { k: ["Tab"], d: "탭 글자 넣기" },
    { k: ["Ctrl+V"], d: "글만 붙여 넣기(서식은 버림)" },
    { k: ["Esc"], d: "편집 끝 — 커서가 문단에서 나감" },
    { k: ["Ctrl+S"], d: "수정본 내려받기" },
  ] },
  { id: "outline", name: "개요 줄", note: "헤딩 추출 2단계가 매긴 줄(쪽 왼쪽 여백의 「TN Lk」)에서 — 그 밖의 문단은 「글 고치기」 대로", rows: [
    { k: ["Enter"], d: "바로 아래에 하위 레벨 줄 만들기" },
    { k: ["Alt+Enter"], d: "부분 트리 끝 뒤에 같은 레벨의 템플릿 뼈대 만들기(그 레벨부터 마지막 레벨까지)" },
    { k: ["Alt+↑|↓"], d: "개요 레벨을 한 단계 올리기 · 내리기 — 여러 문단을 블록으로 잡으면 걸친 개요 줄 모두(자식은 안 따라감 · 하나라도 못 바꾸면 전부 거절)" },
    { k: ["Alt+↓"], at: "템플릿의 마지막 레벨 줄에서", d: "새 개요 레벨 더하기 — 레터 후보 약 10개 · 앞 공백 · 둘째 줄을 골라 템플릿에 레벨을 더하고 그 줄을 그 레벨로(↑↓ 고르기 · ←→ 앞 공백 · Tab 둘째 줄 · Enter 더하기 · Esc 닫기)" },
    { k: ["Enter"], at: "표 제목 줄에서", d: "표 아래에 그다음 레벨의 새 줄 만들기 — 제목 표를 템플릿의 L1 로 넣었을 때(「템플릿 관계」 의 「표를 L1 으로」) · 제목 글은 안 나눔(줄 바꿈은 Shift+Enter)" },
    { k: ["@손잡이 ⋮⋮ 끌기"], d: "같은 템플릿·같은 레벨 줄에 끌어 놓으면 부분 트리째 옮기기" },
    { k: ["Backspace"], at: "글 없는 레터 줄에서", d: "그 줄 지우기" },
  ] },
  { id: "cells", name: "표 칸 고르기", note: "문서의 표에서", rows: [
    { k: ["@칸에서 다른 칸으로 끌기"], d: "칸 묶음 고르기 — 같은 칸 안에서 끌면 글 고르기" },
    { k: ["Shift+@누름"], at: "칸을 고른 뒤", d: "처음 칸부터 누른 칸까지 고르기" },
    { k: ["Shift+화살표"], d: "고른 범위 늘리기 · 줄이기" },
    { k: ["Ctrl+C"], d: "고른 칸 복사" },
    { k: ["M"], at: "칸을 둘 이상 고른 뒤", d: "칸 합치기" },
    { k: ["S"], at: "칸을 고른 뒤", d: "칸 나누기 목록 — 위아래·좌우 · 표 크기 그대로 / 칸 크기 그대로" },
    { k: ["@오른쪽 단추"], d: "메뉴 — 칸 복사 · 고른 칸만 넣기·복사·줄 지우기 · 합치기·나누기 · 행·열 넣기·지우기 · 헤더 지정 · 표 나누기 · 엑셀식 보기 · 표 양식 등(올리면 문서에 미리보기)" },
    { k: ["Esc"], d: "고르기 풀기" },
  ] },
  { id: "paras", name: "문단 묶음 고르기", note: "본문이나 같은 칸 안의 문단 여러 개", rows: [
    { k: ["@문단에서 다른 문단으로 끌기"], d: "닿은 문단까지 묶어 고르기" },
    { k: ["Shift+@누름"], d: "앞서 누른 문단(없으면 커서 문단)부터 누른 문단까지" },
    { k: ["Ctrl+C"], d: "고른 문단의 글 복사" },
    { k: ["@오른쪽 단추"], d: "메뉴 — 「고른 글로 표 만들기…」(hwpx) · 구분 기준 자리로 추가 등" },
    { k: ["Esc"], d: "묶음 풀기" },
  ] },
  { id: "xl", name: "엑셀식 보기", note: "표 표지의 ⊞ · 표 메뉴로 연 격자에서", rows: [
    { k: ["화살표"], d: "칸 옮기기" },
    { k: ["Enter", "Tab", "Shift+Tab"], d: "아래 · 오른쪽 · 왼쪽 칸으로" },
    { k: ["F2", "@두 번 누름"], d: "칸 고치기 — 글자를 바로 치면 그 글자부터 새로 씀" },
    { k: ["Delete|Backspace"], d: "칸 값 지우기" },
    { k: ["Enter", "Tab"], at: "칸을 고치는 중", d: "넣고 아래 · 오른쪽 칸으로" },
    { k: ["Esc"], at: "칸을 고치는 중", d: "고치기 취소" },
    { k: ["Enter", "Esc"], at: "수식 줄에서", d: "넣기 · 되돌리기" },
  ] },
  { id: "view", name: "보기 · 옆 열 · 메뉴", note: "", rows: [
    { k: ["@휠"], d: "한 칸에 한 쪽씩 넘기기(2쪽 보기면 두 쪽씩) — 「휠 쪽 넘김」 을 켰을 때 · Ctrl·Shift·Alt+휠은 브라우저대로" },
    { k: ["@옆 열 왼쪽 가장자리 끌기"], d: "옆 열 폭 조절 — 두 번 누르면 기본 폭" },
    { k: ["←|→"], at: "폭 손잡이에 초점을 두고", d: "20px 씩 넓히기 · 좁히기(Shift 는 80px) · Home/End 는 최소·최대 폭" },
    { k: ["←|→"], at: "탭 줄 · 쪽 비교 창에서", d: "이웃 탭 · 앞뒤 쪽으로 — 탭 줄은 Home/End 로 처음·끝" },
    { k: ["↑|↓"], at: "오른쪽 단추 메뉴에서", d: "항목 옮기기" },
    { k: ["Esc"], d: "열린 메뉴 · 도움말 닫기" },
  ] },
];

const shortcutsShown = () => { const c = $("headsDlg"); return !!c && !c.hidden && c.dataset.kind === "shortcuts"; };

function shortcutsKeys(cell, row) { // 키 칸 — 묶음마다 <kbd>…, 묶음 사이·자리 안 여러 키는 「/」, 「어디서」 는 아래 줄에 작게
  row.k.forEach((combo, i) => {
    if (i) cell.append(el("span", "sc-or", "/"));
    const box = el("span", combo.includes("@") ? "sc-combo mouse" : "sc-combo");
    combo.split("+").forEach((part, j) => {
      if (j) box.append(el("span", "sc-plus", "+"));
      if (part.startsWith("@")) { box.append(el("span", "sc-act", part.slice(1))); return; }
      part.split("|").forEach((key, n) => {
        if (n) box.append(el("span", "sc-or", "/"));
        box.append(el("kbd", null, key));
      });
    });
    cell.append(box);
  });
  if (row.at) cell.append(el("span", "sc-at", row.at));
}

function shortcutsState() { // 「개요 줄」 묶음 — 개요 편집 키가 지금 켜져 있는지(2단계 결과가 있어야 — app.js outlineLoad)
  const sec = document.querySelector('#headsDlgBody .sc-sec[data-sec="outline"]');
  if (!sec) return;
  const on = !!heads.outline, chip = sec.querySelector(".sc-state");
  sec.classList.toggle("off", !on);
  chip.className = `sc-state ${on ? "on" : "off"}`;
  chip.textContent = on ? "켜짐" : "꺼짐";
  chip.title = on ? "이 문서는 개요 편집 키가 켜져 있습니다"
    : state.format === "docx" ? "개요 편집은 hwpx 문서에서만 됩니다 — 지금은 Enter 가 문단 나누기"
      : "헤딩 추출 2단계를 돌리면 켜집니다 — 그때까지 Enter 는 문단 나누기";
  sec.querySelector(".sc-off-note").textContent = on ? "" : chip.title;
}

function shortcutsSync() { // 단추 눌림 + 「개요 줄」 켜짐/꺼짐 — 2열이 열리고 닫히거나 다른 보기로 바뀔 때(아래 지켜보기) · 개요 오버레이가 바뀔 때(app.js outlineHint)
  const b = $("shortcutsBtn");
  if (!b) return;
  const on = shortcutsShown();
  b.setAttribute("aria-pressed", String(on)); // 눌림 표시 = style.css .doc-bar .icon.tb[aria-pressed="true"]
  b.dataset.outline = heads.outline ? "1" : "0"; // 개요 편집 키가 켜졌는지(화면 검사용 — 옛 #editHint 글 「개요 줄: …」 자리)
  if (on) shortcutsState();
}

function shortcutsLeave() { // 2열에 저장 안 한 글(지침 · 표 지침 · 양식 정보)이 있으면 묻는다 — headsColClose 와 같은 차례
  return headsGuideLeave() && (typeof tblAgentLeave !== "function" || tblAgentLeave()) && (typeof headsFormLeave !== "function" || headsFormLeave());
}

function shortcutsOpen() {
  if (!state.id) return;
  if (!shortcutsShown() && !shortcutsLeave()) return;
  const { body, foot } = headsDlg("shortcuts", "단축키", "키보드 · 마우스 조작");
  if (typeof xlColumnClosed === "function") xlColumnClosed(); // 엑셀식 보기 자리에 열었으면 표지의 ⊞ 눌림을 푼다(tables.js)
  for (const s of SHORTCUTS) {
    const sec = el("section", "sc-sec"), h = el("h3", null, s.name);
    sec.dataset.sec = s.id;
    if (s.id === "outline") h.append(el("span", "sc-state"));
    if (s.note) h.append(el("span", "sc-note", s.note));
    const t = el("table", "sc-list"), tb = el("tbody");
    for (const r of s.rows) {
      const tr = el("tr"), th = el("th");
      th.scope = "row";
      shortcutsKeys(th, r);
      tr.append(th, el("td", null, r.d));
      tb.append(tr);
    }
    t.append(tb);
    sec.append(h);
    if (s.id === "outline") sec.append(el("p", "sc-off-note"));
    sec.append(t);
    body.append(sec);
  }
  foot.append(el("span", "muted", "편집용 보기입니다(출력 배치는 PDF 탭) · 나누기 · 합치기 · 글자·문단 모양 · 표 편집은 도구 줄 오른쪽 「↶ 실행 취소」 로 되돌립니다"));
  shortcutsSync();
}

function shortcutsToggle() { // 단추 — 열려 있으면 닫고, 닫혀 있거나 접혀 있거나 다른 보기면 연다
  if (shortcutsShown() && !colFolded("heads")) headsColClose();
  else shortcutsOpen();
}

(() => {
  const b = $("shortcutsBtn"), col = $("headsDlg");
  if (!b || !col) return;
  b.onclick = shortcutsToggle; // 도구 줄 단추는 mousedown 기본 동작을 막아 둬서(app.js bindToolbar) 눌러도 문서의 선택 범위가 남는다
  if (typeof MutationObserver === "function") new MutationObserver(shortcutsSync).observe(col, { attributes: true, attributeFilter: ["hidden", "data-kind"] });
  shortcutsSync();
})();
