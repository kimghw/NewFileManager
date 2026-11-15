"use strict";
// 서식 보관함(spec_일반편집 ② §7 끝점 · §12 화면) — 공통 모듈: TASK 「문서 일반 편집」 뿐 아니라 어느 TASK 의 문서에서나 연다(R6). 사용자 2026-11-13
// "여기에서 사용되는 문서 서식을 템플릿으로 저장되고 사용할 수 있도록 … 서식복사 … 선택하면 그 서식을 저장해서 재사용".
// 2열(headsDlg — 팝업 아님, design.md §2) kind 둘:
//   "styleLib"  = 보관한 서식: 종류 탭(표 서식 · 글 서식) · 서식마다 이름 · 원본 · 충실도 꼬리표 · PDF 검증 상태 · 견본 그림 · 뺀 것(접힘) ·
//                 「빈 표 넣기」·「고른 표에 입히기」·(글 서식 항목마다)「고른 문단에 입히기」 · 이름 바꾸기 · 다시 검증 · 지우기 / 맨 위 「이 문서에서 추출」·「파일에서 추출」.
//   "styleSave" = 추출 후보(표 → 글): 체크 · 이름 · 띠 수(머리행·머리열·합계행) · 같은 서식 n개 · 자리로 · 「구조까지 저장」 / 「글도 그대로 저장」 · 「이름 붙이기(LLM)」 · 「고른 n개 저장」.
// 여는 곳: 에이전트 보기의 「서식 보관함」(doc_agent.js) · 표 메뉴 「서식 보관함에 저장…」(table_menu.js → styleSaveOpen({table})) · 반영한 제안 카드 「이 표를 서식으로 저장」.
// 밖에 내는 것: styleLibOpen(tab?) · styleSaveOpen({table?, blueprint?, file?}) · 문서 자리 도우미 slSelection · slTopOf · slBlockEls · slGo(doc_agent.js 가 같이 쓴다).
// app.js 가 주는 것: state·heads·$·el·api·toast·structOp·flushAll·headsDlg·hBtn·hFoot·hHelp·paraEl·scrollToBlock·fmtWhen·nf·short·oneLine·H_JSON. tables.js: xlBlock·xlSelRange. table_menu.js: tmn·tmnActivate.
// table_make.js: tpk(문단 묶음). 서버 짝은 app/style_api.py — 끝점이 없거나(404) 보관함이 꺼져 있으면(503) 그 까닭을 한 줄로 보인다. index.html 이 doc_agent.js 앞에 읽는다.
//
// 2026-11-14 **서식 관리자**(spec_서식복사 ② §2 — 사용자 "사이드 패널로 서식관리자를 추가해줘 … 템플릿, 문서식, 테이블 서식등을 선택할 수 있게"): 이 열의 화면 이름이 「서식 관리자」 다(저장소를 가리키는 문장의 「보관함」 은 그대로).
//   styleLib  = 종류 세그먼트 셋(템플릿 text · 문서 서식 page · 테이블 서식 table — 처음 템플릿) · 「이 문서에서 복사」(hwpx·docx)·「파일에서 복사」 · 서식 줄마다 검증 꼬리표를 형식마다(hwpx · docx) ·
//               견본 그림의 형식 전환 · 「hwpx 받기」·「docx 받기」 · 문서 서식 줄(요약 한 줄 · 「이 문서에 입히기」). docx 문서에서는 「빈 표 넣기」·「고른 문단에 입히기」·받기·관리만.
//   styleSave = 「서식 복사」: 단계 줄(① 후보 찾기 ② 에이전트 추출 ③ 저장 ④ PDF 검증) + 「한 번에 진행」 · 후보 구역 셋(문서 서식 → 템플릿 → 테이블 서식) · 「에이전트 추출」 · 「고른 n개 저장」 · 저장 뒤 검증 진행 줄.
// 여는 곳: 도구 줄 「서식」 묶음(#tbStyleLib·#tbStyleCopy·#tbStyleFile — 이 파일 끝이 잇는다) · 에이전트 보기 상태 줄 · 표 메뉴 · TASK 「문서 서식 복사」(app.js taskEnter·load) · 시작 화면의 PDF(app.js homeTaskStart → styleFileExtract —
// 문서가 없어도 2열이 시작 화면 옆에 열린다: 그때 「이 문서에서 복사」·적용 단추는 꺼져 있다). 옛 서버(두 형식을 모름 — 목록 응답에 pdfDocx 가 없음)에서는 docx 꼬리표·받기·형식 전환을 내지 않는다.

// 2026-11-14(2차 — spec_서식복사 ② §12·§13·§15: 사용자 "서식을 그림/이미지로 보여줘야지" · "표지 서식이 있고, 내용서식이 있고 테이블 서식이 있고, 문단 서식이 있잖아" · "검증 + 보완을 LLM 이 해야지"):
//   갈래 넷(data-sl-tab — 표지 서식 cover · 내용 서식 content(레벨 있는 text + 쪽 설정 page) · 테이블 서식 table · 문단 서식 para(레벨 없는 text): 처음 = 내용 서식) ·
//   줄마다 **서식 그림이 먼저**(style_pic.js 의 stylePic — 보이는 줄만 견본을 받고(IntersectionObserver · 넷까지 함께), 목록을 다시 그려도 그림을 다시 받지 않는다: 아래 「서식 그림 자리」) ·
//   원천 고르기(웹 견본 | 한글 출력 | Word 출력) · 「크게」 · 관리 단추는 「⋯ 더보기」 아래 · 동작 이름에 적용 범위(글자·문단 모양 입히기 · 표 모양 입히기 · 쪽 설정 입히기 · 표지 넣기) ·
//   ② 단계 이름 「LLM 검토」 + 후보마다 검토 상태를 글로(봄 · 고침 + 되돌리기 · 확인 · 안 봄) · 「한 번에 진행」 은 의심·고침·넓히기 제안이 없는 추천만 저장.
//   옛 서버(견본 끝점·paras·covers·review 가 없음)에서는 없는 대로 — 견본 끝점이 404 면 그림 자리에 「서버를 다시 켜야 그림이 보입니다」.
// 2026-11-14(3차 — ② §18: 사용자 "표지/내용서식/테이블/쪽 을 여기 탭에서 따로 따로 볼 수 있게"): styleSave 의 후보를 탭 다섯(data-sl-ctab — 표지 서식 · 내용 서식 · 테이블 서식 · 쪽 설정 · 문단 서식)으로 갈라 한 번에 한 탭의 줄만 그린다
//   (전의 한 목록 「후보 구역」 을 없앰 — 아래 「서식 복사 열의 탭」). 서식 관리자(styleLib)의 갈래는 그대로 넷.
// 2026-11-14(4차 — ② §19: 사용자 "서식이름도 변경할 수 있고, 보통 문서 이름 사업계획서: body1 이런식이면" · "앞 여백, 2번째줄 여백 시작 위치, 폰트, 글자크기, 줄간격들을 수정할 수 있는 기능" · "서식을 복사하기"):
//   후보의 기본 이름 = 서버의 defaultName(「사업계획서: body1」 — 없으면 옛 이름) · LLM 의 이름은 이름을 덮지 않고 설명(row.note → 저장 몸의 note · 이름 칸 아래 .sl-cnote) ·
//   서식 관리자의 글 서식 항목마다 「값 고치기」(줄 안 다섯 칸 → PUT …/items/{key}/format) · 「⋯ 더보기」 의 「복사본 만들기」(POST …/copy) · 도구 줄 「서식 지도」(format_map.js 의 fmtMapOpen).
const SL_TABS = [["cover", "표지 서식", "문서 첫 쪽의 배치(제목·기관·날짜 자리 · 표지 표) — 글은 역할 견본으로"], ["content", "내용 서식", "개요 레벨의 글 서식(레벨마다 레터·글자·문단 모양)과 그 본문이 놓이는 쪽 설정"],
  ["table", "테이블 서식", "표 서식(띠 수·음영·괘선·칸 글 모양 · 구조)"], ["para", "문단 서식", "본문·캡션·주석·상자 글 같은 낱 문단의 서식(레벨 없음)"]]; // 갈래 넷(spec_서식복사 ② §12) — [data-sl-tab, 화면 이름, 뜻]
const SL_TAB = Object.fromEntries(SL_TABS.map(([k, name]) => [k, name]));
const SL_CTABS = [["cover", "표지 서식", "문서 첫 쪽의 블록 묶음(제목·기관·날짜 자리 · 표지 표) — 배치 그대로, 글은 역할 견본으로 바꿔 저장합니다"],
  ["content", "내용 서식", "개요 레벨의 글 서식 — 레벨마다 레터·글자·문단 모양(그 본문이 놓이는 쪽은 「쪽 설정」 탭)"],
  ["table", "테이블 서식", "띠 수와 구역 대표 칸의 모양(음영·글꼴·괘선)이 같은 표를 한 후보로 묶었습니다 — 그림은 대표 표(문서 순 첫 표) 하나의 것"],
  ["page", "쪽 설정", "쪽 설정(용지 크기·방향·여백)과 본문 바탕 글 모양 — 문서마다 하나"],
  ["para", "문단 서식", "개요 레벨에 들지 않은 낱 문단(본문·캡션·주석·상자 글)을 서식이 같은 것끼리 묶었습니다 — 역할은 스크립트가 먼저 붙이고 고칠 수 있습니다"]]; // 「서식 복사」 열의 탭 다섯(spec_서식복사 ② §18 — 서식 관리자의 갈래 넷과 달리 쪽 설정이 따로) — [data-sl-ctab, 화면 이름, 뜻(탭 아래 설명 줄 · 탭의 도움말)]
const SL_CTAB = Object.fromEntries(SL_CTABS.map(([k, name]) => [k, name]));
const SL_KIND = { cover: "표지 서식", text: "내용 서식", page: "쪽 설정", table: "테이블 서식" }; // 저장 꼴(kind) → 화면 이름(레벨 없는 text 는 「문단 서식」 — slPickName·slTabOf 가 가른다)
const SL_ROLES = [["body", "본문"], ["caption", "캡션"], ["note", "주석"], ["box", "상자 글"], ["toc", "목차"], ["other", "기타"]]; // 문단 서식의 역할(② §12)
const SL_ROLE = Object.fromEntries(SL_ROLES);
const SL_TROLE = { data: "자료 표", form: "양식", layout: "배치", sign: "서명", cover: "표지", guide: "안내" }; // LLM 이 본 표의 역할(② §15)
const SL_DOUBT = { repAtypical: "대표 문단이 그 레벨의 다수 서식이 아님", mixedSlot: "한 레벨에 서식이 여럿", levelGap: "레벨이 건너뜀", bodyClose: "바탕 글 1·2위의 차이가 작음", sectionsDiffer: "구역마다 쪽 설정이 다름",
  guideText: "안내문을 헤딩으로 읽은 듯함", levelOrder: "레벨의 사슬 순서가 어색함" }; // 의심 코드 → 화면 글(서버가 글을 안 실어 보냈을 때만 — 원본은 style_extract.DOUBTS)
const SL_SRC = [["web", "웹 견본", "저장된 서식 값으로 브라우저가 바로 그린 서식 견본입니다 — 글꼴·줄바꿈은 출력과 조금 다를 수 있습니다"], ["hwpx", "한글 출력", "한글로 출력한 PDF 검증 그림(hwpx 서식)"], ["docx", "Word 출력", "Word 로 출력한 PDF 검증 그림(docx 서식)"]]; // 그림의 원천(② §13)
function slTabOf(s) { // 보관한 서식 → 갈래(② §12): cover → 표지 · table → 테이블 · page → 내용(그 안 「쪽 설정」) · text → 레벨이 있으면 내용, 없으면 문단(요약의 leveled — 없으면 items 의 레벨로)
  if (!s) return "content";
  if (s.kind === "cover" || s.kind === "table") return s.kind;
  if (s.kind === "page") return "content";
  const items = s.items || [];
  return (typeof s.leveled === "boolean" ? s.leveled : items.length ? items.some((it) => it && it.level != null) : true) ? "content" : "para";
}
const slTabOfPick = (k) => (!k ? null : k.kind === "text" ? (k.template != null || k.leveled === true ? "content" : Array.isArray(k.paras) || k.leveled === false ? "para" : slTabOf(k)) : slTabOf(k)); // 에이전트 제안의 pick → 갈래(doc_agent.js)
const slPickName = (k) => (!k ? "서식" : k.kind === "page" ? "쪽 설정" : SL_TAB[slTabOfPick(k)] || "서식"); // 그 화면 이름(「내용 서식」·「문단 서식」·「쪽 설정」·「테이블 서식」·「표지 서식」)
const slTabArg = (x) => (x && typeof x === "object" ? slTabOf(x) : x in SL_TAB ? x : { page: "content", text: "content" }[x] || null); // styleLibOpen 의 인자 — 갈래 · 저장 꼴(kind) · 서식
const SL_FORMATS = [["hwpx", "verify", "한글"], ["docx", "verifyDocx", "Word"]]; // 두 형식(② §4·§7) — [형식, 요약·meta 의 검증 기록 키, 출력하는 앱]
const SL_STEPS = [["find", "후보 찾기", "스크립트가 문서·파일에서 서식 후보를 찾습니다(서식 값은 모두 스크립트가 읽습니다)"], ["name", "LLM 검토", "LLM 이 후보마다 설명 · 저장할 만한가 · 띠 수 · 역할 · 의심스러운 데를 봅니다 — 서식 값과 이름은 짓지 않습니다(유료 — 누를 때만)"],
  ["save", "저장", "고른 서식을 보관함에 hwpx·docx 두 형식으로 저장합니다"], ["verify", "PDF 검증", "저장한 서식을 한글·Word 로 출력해 서식 값과 견줍니다(뒤에서 돕니다)"]]; // 「서식 복사」 의 단계 줄(② §1 「단계」)
const SL_VERIFY_LIMIT = 180000; // 「한 번에 진행」·저장 뒤 검증을 기다리는 한도(ms — ② §2)
const SL_FID = { native: ["원본 서식", "hwpx 문서의 서식 정의를 그대로 옮긴 것"], summary: ["요약", "docx 의 서식을 요약 명세로 다시 지은 것 — 원본과 조금 다를 수 있습니다"], approx: ["근사", "PDF 에서 잰 값으로 어림한 것 — 칸 여백·줄 간격·괘선 종류는 재지 못합니다"] };
const SL_VERIFY = { ok: "검증됨", warn: "확인 필요", fail: "실패", none: "PDF 없음", running: "검증 중" };
const SL_VERIFY_HELP = { ok: "한글로 출력한 견본이 서식 값과 맞습니다\n「검증됨」 = 저장한 서식이 제 값대로 출력된다는 뜻 — 원본 문서와 같은지는 견주지 않습니다", warn: "실패는 없지만 확인이 필요합니다 — 재지 못한 것이 많거나 · 대체 글꼴로 출력됐거나 · 2쪽 이상", fail: "출력한 견본이 서식 값과 다른 데가 있습니다 — 「뺀 것 · 검증 내역」 을 보세요",
  none: "PDF 출력(한글)이 없어 검증하지 못했습니다", running: "한글로 견본을 출력해 재는 중입니다(2초마다 다시 읽음)" }; // docx 형식은 「한글」 자리에 「Word」(slVerifyHelp)
const SL_CHECK = { render: "출력", pages: "쪽 수", text: "칸 글", fontSize: "글자 크기", bold: "굵게", color: "글자 색", fontFace: "글꼴", fill: "음영", edge: "괘선", lineWidth: "선 굵기", width: "표 폭", indent: "들여쓰기",
  pageSize: "쪽 크기", marginLeft: "왼쪽 여백", marginTop: "위쪽 여백" }; // 뒤 셋 = 문서 서식(profile page-v1 — spec_서식복사 ② §7)
const SL_STATUS = { pass: "통과", fail: "실패", unknown: "모름", unsupported: "재지 못함" };
const SL_BANDS = [["headerRows", "머리행", "위쪽 열 제목 행 수"], ["headerCols", "머리열", "왼쪽 행 제목 열 수"], ["footRows", "합계행", "아래쪽 합계·소계 행 수"]];
const SL_KEEP_HELP = "기본은 자료값을 저장하지 않습니다 — 머리 칸(머리행·머리열)의 글은 그대로 두고, 나머지 칸·문단의 글은 견본(「0」·「가나다」·「견본 글입니다」)으로 바꿔 저장합니다.\n켜면 원래 글을 그대로 저장합니다 — 보관함은 서버 전체에서 보이므로 다른 문서·TASK 에서 열어도 그 글이 보입니다.";
// 한 번 읽어 둔 것(보관함은 문서와 무관 — 문서를 바꿔도 남는다). save = 추출 후보 열의 상태(문서·파일마다)
// tab = 고른 갈래(문서를 바꿔도 남는다 — 처음 내용 서식) · pdfDocx = Word 출력이 되나 · dual = 서버가 두 형식을 안다(목록 응답에 pdfDocx 가 있음 — 옛 서버면 docx 꼬리표·받기·Word 출력 그림을 내지 않는다) ·
// picSrc[sid] = 그 서식 그림의 원천(web | hwpx | docx — 사람이 고른 것: 출력이 끝나도 저절로 안 바꾼다) · big = 「크게」 로 편 그림(서식 `lib|sid` · 후보 `cand|…`) · manage = 「⋯ 더보기」 를 편 서식 · proofs = 출력 그림 요소(다시 그려도 다시 안 읽게)
// edit = 줄 안에서 고치는 것 하나({sid, mode: rename | delete | fmt(값 고치기 — item · base · draft · err · focus)}) · copying = 복사본을 만드는 중인 서식(spec_서식복사 ② §19-6)
const STYLE = { tab: "content", list: null, enabled: true, pdf: true, pdfDocx: false, dual: false, broken: [], err: "", edit: null, copying: null, big: new Set(), more: new Set(), manage: new Set(), cfold: new Set(), full: {}, msg: {}, picSrc: {}, proofs: new Map(), pollTimer: 0, file: null, save: null };
if (typeof LOG_KIND === "object") Object.assign(LOG_KIND, { styleApply: "서식 관리자 적용", styleSave: "서식 관리자에 저장", styleName: "서식 후보 LLM 검토" }); // 「기록」 탭의 이름

const styleErr = (e) => (e && e.status === 404 && e.message === "Not Found" ? "서버가 옛 판입니다 — 서버를 다시 켜야 「서식 관리자」 를 쓸 수 있습니다" : (e && e.message) || "알 수 없는 오류");
const styleUrl = (sid, tail = "") => `/api/styles/${encodeURIComponent(sid)}${tail}`;
const slWhen = (v) => { const t = typeof v === "number" ? (v > 1e12 ? v / 1000 : v) : v ? Date.parse(v) / 1000 : NaN; return Number.isFinite(t) ? fmtWhen(t) : ""; };
const slBandsText = (b) => (b ? SL_BANDS.filter(([k]) => b[k]).map(([k, name]) => `${name} ${b[k]}`).join(" · ") || "머리 없음" : "");
const slSecs = (t0) => `${Math.round((performance.now() - t0) / 1000)}초`;
const slVerifyHelp = (st, app) => (SL_VERIFY_HELP[st] || "").replaceAll("한글", app); // 형식마다 출력하는 앱 이름으로(hwpx = 한글 · docx = Word)
const SL_PAPER = [["A4", 210, 297], ["A3", 297, 420], ["A5", 148, 210], ["B5", 182, 257], ["B4", 257, 364], ["Letter", 215.9, 279.4]];
function slPageText(page, body) { // 문서 서식의 요약 한 줄 — 「A4 세로 · 여백 왼 30 · 오 30 · 위 20 · 아래 15mm · 본문 함초롬바탕 11pt」(서버의 view.summary 가 없을 때 page·body 로 짓는다: spec_서식복사 ② §2·§5)
  if (!page) return "";
  const w = Number(page.widthMm) || 0, h = Number(page.heightMm) || 0, a = Math.min(w, h), b = Math.max(w, h), n = (v) => String(Math.round((Number(v) || 0) * 10) / 10);
  const paper = SL_PAPER.find(([, x, y]) => Math.abs(a - x) <= 1 && Math.abs(b - y) <= 1), m = page.marginsMm || {}, f = (body && body.format) || {};
  const land = typeof page.landscape === "boolean" ? page.landscape : w > h;
  return [`${paper ? paper[0] : `${n(w)}×${n(h)}mm`} ${land ? "가로" : "세로"}`, `여백 왼 ${n(m.l)} · 오 ${n(m.r)} · 위 ${n(m.t)} · 아래 ${n(m.b)}mm`,
    f.font || f.sizePt ? `본문 ${[f.font || "", f.sizePt ? `${f.sizePt}pt` : ""].filter(Boolean).join(" ")}` : ""].filter(Boolean).join(" · ");
}
const slVerifyOf = (s, fmt) => (fmt === "docx" ? s.verifyDocx : s.verify) || null;
const slNoDocx = (s) => s.docx === false || (s.docx == null && s.verifyDocx === null); // docx 운반 문서가 없다(못 지음 — 「docx 없음」)
const slRunning = (s) => SL_FORMATS.some(([fmt]) => (slVerifyOf(s, fmt) || {}).status === "running");

// ---- 문서 자리 도우미(에이전트 보기와 같이 쓴다) ------------------------------------------------------------------------------
function slSelection() { // 지금 문서에서 고른 것 — {paras: 끌어 고른 문단 묶음, table: 고른 표, range: 그 표에서 끌어 고른 칸 범위, cursor: 커서 문단}
  const paras = typeof tpk === "object" && tpk ? tpk.ids.filter((i) => paraEl(i)) : [];
  let table = typeof tmn === "object" && tmn && tmn.active && typeof xlBlock === "function" && xlBlock(tmn.active) ? tmn.active : null;
  if (!table && typeof tselActive === "function" && tselActive() && tsel.tbl) table = tsel.tbl;
  const range = table && typeof xlSelRange === "function" ? xlSelRange(table) : null;
  const cursor = state.cur && paraEl(state.cur.id) ? state.cur.id : null;
  return { paras, table, range, cursor };
}
function slTopOf(id) { // 그 문단·표를 품은 본문 최상위 블록 id(칸 안이면 바깥 표) — 서버의 「넣을 자리」 는 본문 최상위만 받는다(spec ② §4)
  const has = (b) => b.id === id || (b.cells || []).some((c) => (c.blocks || []).some(has));
  const top = (state.blocks || []).find(has);
  return top ? top.id : null;
}
function slBlockEls(id) { // 문서의 그 블록 요소들 — 문단 하나 · 표의 쪽 조각들(엑셀식 보기로 바뀐 표 포함)
  if (typeof id !== "string" || !id) return [];
  const q = CSS.escape(id);
  return [...document.querySelectorAll(`#doc .para[data-id="${q}"], #doc table.tbl[data-tbl="${q}"], #doc .xl-wrap[data-tbl="${q}"]`)].filter((e) => !e.hidden);
}
function slGo(id) { // 문서에서 그 블록으로 — 열은 그대로 둔다(나란히 보기)
  if (id && paraEl(id)) { scrollToBlock(id); return true; }
  const t = slBlockEls(id)[0];
  if (!t) { toast("그 자리가 지금 문서에 없습니다(지워졌거나 아직 그리지 않음)"); return false; }
  t.scrollIntoView({ block: "center", behavior: "smooth" });
  if (t.dataset.tbl && typeof tmnActivate === "function") tmnActivate(t.dataset.tbl);
  return true;
}
function slHit(ids) { // 후보 줄에 올린 동안 문서의 그 표·문단(파랑 — 스크립트 후보. 보라는 LLM 제안에만: design.md §6). null = 걷기
  for (const e of document.querySelectorAll("#doc .sl-hit")) e.classList.remove("sl-hit");
  for (const id of ids || []) for (const e of slBlockEls(id)) e.classList.add("sl-hit");
}
function slRun(text) { // 도는 작업 한 줄 — 동그라미 + 지금 하는 일(+ 지난 시간은 .sl-run-text 만 바꾼다: design.md §7)
  const s = el("span", "sl-run");
  s.append(el("span", "sl-spin"), el("span", "sl-run-text", text));
  return s;
}

// ---- 서식 그림 자리(spec_서식복사 ② §13 「견본을 받는 길」·「목록의 살림」) ---------------------------------------------------------------
// 그림 하나 = 열쇠(보관한 서식 `lib|sid|revision` · 문서 후보 `doc|문서 id|차례|후보 key|저장 몸` · 파일 후보 `file|토큰|후보 key|pick`)로 기억하는 E = {box: 자리 요소, state, view …}.
// styleLibDraw·styleSaveDraw 는 몸을 비우고 다시 짓지만 **자리 요소를 그대로 다시 붙인다** — 다시 그려도 견본을 다시 받지 않는다. 견본은 보이는 자리만 받는다(IntersectionObserver · root = #headsDlgBody),
// 함께 넷까지 · 같은 열쇠는 한 번 · 문서를 바꾼 뒤 늦게 온 답은 버린다. 띠 수·「글도 그대로 저장」·역할이 바뀌면 열쇠가 달라져 새로 받는다.
const SLP = { map: new Map(), active: 0, wait: [], io: null, ioRoot: null, max: 4, keep: 240 };
const slPicWidth = () => Math.max(200, (($("headsDlgBody") || {}).clientWidth || 320) - 24); // 그림 폭 = 열의 안쪽 폭(.sl-wrap 좌우 12px)
function slPicHeight(kind, n) { // 자리 높이 — 그림 상자 + (표가 넘쳐 「전체 n행」 글이 붙을 것이면) 그 한 줄
  if (typeof stylePic !== "function") return 64;
  return stylePic.height(kind, n) + (kind === "table" && (n || 0) * 15 + 30 > stylePic.height(kind, n) ? 17 : 0);
}
function slPicEntry(key, kind, n, fetcher, opts = {}, doc = false) { // 그 열쇠의 그림(없으면 만든다 — 아직 받지 않음)
  let E = SLP.map.get(key);
  if (E) { SLP.map.delete(key); SLP.map.set(key, E); return E; } // 방금 쓴 것이 맨 뒤(오래 안 쓴 것부터 버린다)
  E = { key, kind, n, fetcher, opts, doc, state: "idle", view: null, err: null, big: false, painted: "", box: el("div", "sl-pic") };
  E.box.dataset.picKey = key;
  E.box.dataset.spKind = kind;
  SLP.map.set(key, E);
  for (const [k, old] of SLP.map) { // 기억은 keep 개까지 — 화면에 없고 받는 중이 아닌 오래된 것부터
    if (SLP.map.size <= SLP.keep) break;
    if (!old.box.isConnected && old.state !== "loading") SLP.map.delete(k);
  }
  return E;
}
function slPicErrText(e) { // 견본을 못 받은 까닭 — 옛 서버(끝점 없음 404) · 올린 파일을 서버가 놓음(410)
  if (e && e.status === 404 && e.message === "Not Found") return "서버를 다시 켜야 그림이 보입니다";
  if (e && e.status === 410) return "올린 파일을 서버가 놓았습니다 — 다시 올려야 저장할 수 있습니다";
  return `서식 견본을 읽지 못했습니다 — ${(e && e.message) || "알 수 없는 오류"}`;
}
function slPicPaint(E, big = false) { // 자리의 내용을 지금 상태로(같은 상태면 그대로 둔다 — 다시 그려도 그림 요소가 안 바뀐다)
  const sig = `${E.state}|${big ? `big:${slPicWidth()}` : ""}`, box = E.box, h = slPicHeight(E.kind, E.n);
  E.big = big;
  if (E.painted === sig) return box;
  E.painted = sig;
  box.dataset.picState = E.state;
  box.classList.toggle("big", big && E.state === "done");
  box.style.minHeight = `${h}px`;
  box.style.height = E.state === "done" ? "" : `${h}px`;
  if (E.state === "done") {
    if (typeof stylePic !== "function") { box.dataset.picState = "err"; box.style.height = `${h}px`; box.replaceChildren(el("div", "sl-pic-msg", "서식 그림 모듈(style_pic.js)을 읽지 못했습니다 — 화면을 새로 고치세요")); return box; }
    const w = big ? Math.max(560, Math.round(slPicWidth() * 1.8)) : slPicWidth(), pic = stylePic(E.view, { kind: E.kind, ...E.opts, n: E.n, width: w, big });
    if (big) pic.style.width = `${w}px`; // 「크게」 — 그 상자 안에서만 가로로 넘긴다(열 전체는 안 넘친다)
    box.replaceChildren(pic);
  } else if (E.state === "err") {
    const m = el("div", "sl-pic-msg"), retry = hBtn("다시", () => { E.state = "idle"; E.err = null; slPicLoad(E); }, { title: "서식 견본을 다시 받습니다" });
    retry.dataset.slAct = "picRetry";
    m.append(el("span", null, slPicErrText(E.err)), retry);
    box.replaceChildren(m);
  } else box.replaceChildren(E.state === "loading" ? (() => { const w = el("div", "sl-pic-wait"); w.append(el("span", "sl-spin"), el("span", null, "서식 견본을 받는 중…")); return w; })() : el("div", "sl-pic-wait"));
  return box;
}
function slPicLoad(E) { // 견본을 받는다(한 번) — 함께 넷까지, 나머지는 줄을 선다
  if (!E || E.state !== "idle") return;
  E.state = "loading";
  slPicPaint(E, E.big);
  SLP.wait.push(E);
  slPicPump();
}
function slPicPump() {
  while (SLP.active < SLP.max && SLP.wait.length) {
    const E = SLP.wait.shift(), epoch = state.epoch;
    SLP.active += 1;
    Promise.resolve().then(() => E.fetcher()).then((view) => {
      if (E.doc && epoch !== state.epoch) { E.state = "idle"; SLP.map.delete(E.key); return; } // 문서를 바꾼 뒤 늦게 온 답 — 버린다
      E.view = view && typeof view === "object" ? view : {};
      E.state = "done";
    }, (e) => { E.err = e; E.state = "err"; }).then(() => { SLP.active -= 1; slPicPaint(E, E.big); slPicPump(); });
  }
}
function slPicWatch() { // 열을 그린 뒤 — 아직 안 받은 그림 자리만 지켜본다(보이는 줄만 받는다)
  const root = $("headsDlgBody");
  if (SLP.io) SLP.io.disconnect();
  const idle = root ? [...root.querySelectorAll('.sl-pic[data-pic-state="idle"]')] : [];
  if (!idle.length) return;
  if (typeof IntersectionObserver !== "function") { for (const b of idle) slPicLoad(SLP.map.get(b.dataset.picKey)); return; }
  if (!SLP.io || SLP.ioRoot !== root) {
    SLP.ioRoot = root;
    SLP.io = new IntersectionObserver((list) => {
      for (const x of list) if (x.isIntersecting) { SLP.io.unobserve(x.target); slPicLoad(SLP.map.get(x.target.dataset.picKey)); }
    }, { root, rootMargin: "120px 0px" });
  }
  for (const b of idle) SLP.io.observe(b);
}
function slPicBar(cap, bigKey, redraw, extra = []) { // 그림 아래 한 줄 — 무엇의 그림인가(글) · (원천 고르기) · 「크게」(그림 밖 단추 — aria-expanded)
  const bar = el("div", "sl-picbar"), on = STYLE.big.has(bigKey), c = el("span", "sl-pic-cap", cap[0]);
  if (cap[1]) c.title = cap[1];
  const big = hBtn(on ? "작게" : "크게", () => { if (on) STYLE.big.delete(bigKey); else STYLE.big.add(bigKey); redraw(); }, { title: "그림을 그 자리에서 크게 봅니다 — 그림 상자 안에서만 가로로 넘깁니다(창을 띄우지 않습니다)" });
  big.dataset.slAct = "big";
  big.setAttribute("aria-expanded", String(on));
  bar.append(c, ...extra, el("span", "sl-gap"), big);
  return bar;
}

// ---- 보관함 목록(kind "styleLib") ------------------------------------------------------------------------------------------
const styleLibOn = () => heads.dlg === "styleLib";
function styleChanged() { if (typeof agentStylesRefresh === "function") agentStylesRefresh(); } // 에이전트 입력의 서식 고르기도 다시(doc_agent.js)

async function styleLibOpen(tab = null) { // tab = 갈래(cover·content·table·para) · 저장 꼴(kind) · 서식(요약·meta) — 그 갈래를 고른 채로 연다
  const want = slTabArg(tab);
  if (want) STYLE.tab = want;
  headsDlg("styleLib", "서식 관리자", "보관한 표지 · 내용 · 테이블 · 문단 서식 — 어느 문서에서나 씁니다");
  const seq = heads.seq;
  STYLE.edit = null;
  styleLibDraw(); // 읽어 둔 목록이 있으면 먼저 보인다
  await styleLibLoad();
  if (seq !== heads.seq || !styleLibOn()) return;
  styleLibDraw();
}

async function styleLibLoad() {
  try {
    const r = await api("/api/styles");
    Object.assign(STYLE, { list: r.styles || [], enabled: r.enabled !== false, pdf: !!r.pdf, pdfDocx: !!r.pdfDocx, dual: "pdfDocx" in r, broken: r.broken || [], err: "" });
  } catch (e) { STYLE.list = null; STYLE.err = styleErr(e); }
}

function styleLibDraw() {
  if (!styleLibOn()) return;
  const tools = $("headsDlgTools"), body = $("headsDlgBody"), keep = body.scrollTop, list = STYLE.list || [];
  const count = (k) => list.filter((s) => slTabOf(s) === k).length, doc = !!state.id; // 내용 서식의 수 = 레벨 있는 글 서식 + 쪽 설정
  tools.textContent = "";
  const tabs = el("span", "sl-tabs");
  tabs.setAttribute("role", "group");
  tabs.setAttribute("aria-label", "서식 갈래");
  for (const [k, name, what] of SL_TABS) { // 갈래 고르기(세그먼트 넷 — 표지 서식 · 내용 서식 · 테이블 서식 · 문단 서식: spec_서식복사 ② §12). 고른 갈래는 문서를 바꿔도 남는다
    const b = hBtn(STYLE.list ? `${name} ${nf(count(k))}` : name, () => { STYLE.tab = k; STYLE.edit = null; styleLibDraw(); }, { cls: "btn sm" + (STYLE.tab === k ? " on" : ""), title: `${name} — ${what}` });
    b.dataset.slTab = k;
    b.setAttribute("aria-pressed", String(STYLE.tab === k));
    tabs.append(b);
  }
  const fromDoc = hBtn("이 문서에서 복사", () => styleSaveOpen(), { disabled: !doc, title: doc ? "이 문서의 표지 · 내용 · 테이블 · 문단 서식 후보를 찾아 보관함에 저장합니다(문서는 안 바뀜)" : "문서(hwpx·docx)를 열어야 합니다 — 파일만 있으면 「파일에서 복사」" });
  const fromFile = hBtn("파일에서 복사", () => styleFilePick(), { disabled: !!STYLE.file, title: "hwp·hwpx·docx·pdf 파일을 올려 그 안의 서식 후보를 찾습니다 — 작업은 만들지 않습니다\nhwpx = 원본 서식 그대로 · docx = 요약 · pdf = 잰 값으로 근사(테이블 서식 · 쪽 설정만)" });
  fromDoc.dataset.slAct = "fromDoc";
  fromFile.dataset.slAct = "fromFile";
  // 「서식 지도」(spec_서식복사 ② §19-3 — 같은 열을 바꿔 연다: format_map.js 의 fmtMapOpen). hwpx 문서만 — 안 되면 끄고 까닭을 도움말에(design.md §13-1)
  const hwpx = doc && state.format !== "docx", fmOk = typeof fmtMapOpen === "function";
  const fmap = hBtn("서식 지도", () => { if (typeof fmtMapOpen === "function") fmtMapOpen(); }, { disabled: !hwpx || !fmOk,
    title: !doc ? "hwpx 문서를 열어야 합니다 — 서식 지도는 문서의 어느 단락이 어느 서식인지 보입니다" : !hwpx ? "서식 지도는 hwpx 문서에서만 됩니다" : !fmOk ? "서식 지도 화면(format_map.js)을 읽지 못했습니다 — 화면을 새로 고치세요"
      : "이 문서의 어느 단락이 어느 서식인지 · 서식과 다른 단락이 있는지 봅니다(이 열을 바꿔 엽니다)" });
  fmap.dataset.slAct = "fmtMap";
  tools.append(tabs, fromDoc, fromFile, fmap);
  if (STYLE.file) tools.append(slRun(`「${short(STYLE.file.name, 24)}」 에서 서식을 찾는 중 · ${slSecs(STYLE.file.t0)}`));
  body.textContent = "";
  const wrap = el("div", "sl-wrap");
  body.append(wrap);
  if (STYLE.err) {
    wrap.append(el("p", "hwarn fail", `서식 보관함을 읽지 못했습니다: ${STYLE.err}`), el("div", "sl-acts"));
    wrap.lastChild.append(hBtn("다시 읽기", () => styleLibOpen()));
    hFoot("", false);
    return;
  }
  if (!STYLE.list) { wrap.append(slRun("서식 보관함을 읽는 중…")); hFoot("", false); return; }
  const mine = list.filter((s) => slTabOf(s) === STYLE.tab), pages = STYLE.tab === "content" ? mine.filter((s) => s.kind === "page") : [];
  if (!mine.length) {
    wrap.append(el("p", "hnote", STYLE.tab === "table"
      ? "보관한 테이블 서식이 없습니다 — 「이 문서에서 복사」 로 문서의 표 서식을 저장하거나, 문서의 표 메뉴에서 「서식 관리자에 저장…」 을 누르세요."
      : STYLE.tab === "cover" ? "보관한 표지 서식이 없습니다 — 「이 문서에서 복사」 로 문서 첫 쪽(제목·기관·날짜 자리 · 표지 표)의 배치를 저장하세요."
        : STYLE.tab === "para" ? "보관한 문단 서식이 없습니다 — 「이 문서에서 복사」 로 본문·캡션·주석 같은 낱 문단의 서식을 저장하세요."
          : "보관한 내용 서식이 없습니다 — 「이 문서에서 복사」 로 개요 레벨의 글 서식(레벨마다 레터·글자·문단 모양)과 쪽 설정(용지·방향·여백)을 저장하세요."));
  }
  for (const s of mine) if (s.kind !== "page") wrap.append(styleItemEl(s));
  if (pages.length) { // 내용 서식 갈래 안의 한 구역 「쪽 설정」(② §12 — 전의 「문서 서식」)
    const sec = el("div", "sl-sec", `쪽 설정 ${nf(pages.length)}`);
    sec.dataset.slSec = "page";
    sec.title = "쪽 설정(용지 크기·방향·여백)과 본문 바탕 글 모양 — 그 내용이 놓이는 쪽";
    wrap.append(sec);
    for (const s of pages) wrap.append(styleItemEl(s));
  }
  if (STYLE.broken.length) wrap.append(el("p", "sl-msg", `읽지 못한 서식 ${nf(STYLE.broken.length)}개(파일이 깨짐) — ${STYLE.broken.slice(0, 6).join(" · ")}`));
  body.scrollTop = keep;
  hFoot(`${SL_TABS.map(([k, name]) => `${name} ${nf(count(k))}`).join(" · ")}${STYLE.pdf ? "" : " · PDF 출력(한글)이 꺼져 있어 hwpx 검증은 건너뜁니다"}${STYLE.dual && !STYLE.pdfDocx ? " · Word 출력이 없어 docx 검증은 건너뜁니다" : ""}`, false);
  const inp = STYLE.edit && STYLE.edit.mode === "rename" && !STYLE.edit.busy ? body.querySelector(".sl-rename") : null;
  if (inp) { inp.focus({ preventScroll: true }); if (!STYLE.edit.shown) { STYLE.edit.shown = true; inp.select(); } }
  const fv = STYLE.edit && STYLE.edit.mode === "fmt" && !STYLE.edit.busy ? body.querySelector(`.sl-fform [data-sl-fv="${STYLE.edit.focus || SL_FV[0][0]}"]`) : null; // 값 고치기 — 다시 그려도 고치던 칸에 초점
  if (fv) { fv.focus({ preventScroll: true }); if (!STYLE.edit.shown) { STYLE.edit.shown = true; fv.select(); fv.closest(".sl-fform").scrollIntoView({ block: "nearest" }); } }
  slPicWatch(); // 보이는 줄의 서식 그림만 받는다
  stylePoll();
}

// 보관한 서식의 그림 상자(② §13) — 그림(웹 견본: GET /api/styles/{sid} 의 view · 또는 고른 출력 그림) + 그 아래 한 줄(원천 고르기 · 「크게」).
// 원천은 사람이 고른다(서식마다 기억 — STYLE.picSrc): 「웹 견본」(기본) · 「한글 출력」 · 「Word 출력」(그 형식의 검증이 끝나 그림이 있을 때만 켜짐). 출력이 끝나도 저절로 바꾸지 않는다.
const slPicKindOf = (s) => (s.kind === "text" ? (slTabOf(s) === "para" ? "para" : "content") : s.kind); // 서식 → 그림 종류(content · para · table · page · cover)
function slProof(s, fmt) { // 출력 그림 요소(기억 — 다시 그려도 다시 읽지 않는다). 쪽 설정·표지는 내용 둘레를 자르지 않은 첫 쪽 전체(&full=1)
  const key = `${s.id}|${s.revision || ""}|${fmt}`, app = (SL_FORMATS.find(([f]) => f === fmt) || [])[2] || fmt;
  let P = STYLE.proofs.get(key);
  if (P) return P;
  P = { key, failed: false, box: el("div", "sl-pic sl-pic-proof"), img: el("img", "sl-proof") };
  P.box.dataset.picState = "proof";
  P.box.dataset.format = fmt;
  P.img.loading = "lazy";
  P.img.alt = `${s.name} — ${app}로 출력한 견본`;
  P.img.dataset.format = fmt;
  P.img.src = styleUrl(s.id, `/proof.png?${STYLE.dual ? `format=${fmt}&` : ""}${s.kind === "page" || s.kind === "cover" ? "full=1&" : ""}v=${encodeURIComponent(s.revision || "")}`);
  P.img.onerror = () => { P.failed = true; if (styleLibOn()) styleLibDraw(); }; // 못 읽음 — 숨기지 않고 웹 견본 + 「출력 그림을 읽지 못했습니다 — 다시」
  P.box.append(P.img);
  STYLE.proofs.set(key, P);
  if (STYLE.proofs.size > 80) STYLE.proofs.delete(STYLE.proofs.keys().next().value);
  return P;
}
function styleLibPic(s) {
  const wrap = el("div", "sl-picbox"), kind = slPicKindOf(s), bigKey = `lib|${s.id}`, big = STYLE.big.has(bigKey), n = kind === "table" ? s.rows : (s.items || []).length;
  const shots = SL_FORMATS.filter(([fmt]) => (STYLE.dual || fmt === "hwpx") && ["ok", "warn", "fail"].includes((slVerifyOf(s, fmt) || {}).status)).map(([fmt]) => fmt); // 출력 그림이 있는 형식
  const want = STYLE.picSrc[s.id] || "web", src = want !== "web" && shots.includes(want) ? want : "web", P = src === "web" ? null : slProof(s, src), failed = !!(P && P.failed);
  const E = slPicEntry(`lib|${s.id}|${s.revision || ""}`, kind, n, () => api(styleUrl(s.id)).then((m) => m.view || {}), kind === "table" ? { bands: s.bands || null } : kind === "para" ? { role: s.role || null } : {});
  wrap.dataset.picSrc = failed ? "web" : src;
  if (P && !failed) { // 출력 그림 — 자리 높이는 웹 견본과 같게(원천을 바꿔도 목록이 안 밀린다)
    P.box.classList.toggle("big", big);
    P.box.style.height = big ? "" : `${slPicHeight(kind, n)}px`;
    wrap.append(P.box);
  } else wrap.append(slPicPaint(E, big));
  if (failed) {
    const m = el("p", "sl-msg err"), again = hBtn("다시", () => { STYLE.proofs.delete(P.key); styleLibDraw(); }, { title: "출력 그림을 다시 읽습니다" });
    again.dataset.slAct = "proofRetry";
    m.dataset.picMsg = "proof";
    m.append("출력 그림을 읽지 못했습니다 — 웹 견본을 보입니다 ", again);
    wrap.append(m);
  }
  const seg = el("span", "sl-src-seg");
  seg.setAttribute("role", "group");
  seg.setAttribute("aria-label", "서식 그림의 원천");
  for (const [k, name, what] of SL_SRC) {
    if (k === "docx" && !STYLE.dual && !("verifyDocx" in s)) continue; // 옛 서버 — docx 형식을 모른다
    const has = k === "web" || shots.includes(k), on = (failed ? "web" : src) === k;
    const b = hBtn(name, () => { STYLE.picSrc[s.id] = k; styleLibDraw(); }, { cls: "btn sm" + (on ? " on" : ""), disabled: !has, title: has ? what : `${what}\n아직 그 형식의 PDF 검증이 끝나지 않아 출력 그림이 없습니다 — 「⋯ 더보기」 의 「다시 검증」` });
    b.dataset.slSrc = k;
    b.setAttribute("aria-pressed", String(on));
    seg.append(b);
  }
  wrap.append(slPicBar(["서식 견본", "저장된 서식의 견본입니다 — 「이 서식이 이렇게 생겼다」 는 그림이지 「적용하면 문서가 이렇게 된다」 는 그림이 아닙니다(동작마다 바꾸는 범위는 단추 이름에 적혀 있습니다)"], bigKey, styleLibDraw, [seg]));
  return wrap;
}

function styleVerifyEls(s) { // 검증 꼬리표 — 형식마다 하나(.sl-verify[data-format]: 「hwpx 검증됨」 · 「docx 확인 필요」 · 「docx 없음」 …) + 그 형식의 「검증 뒤 바뀜」. 색만으로 가르지 않는다(글에 형식·상태)
  const out = [];
  for (const [fmt, , app] of SL_FORMATS) {
    if (fmt === "docx" && !STYLE.dual && !("verifyDocx" in s) && !("docx" in s)) continue; // 옛 서버 — docx 형식을 모른다: 꼬리표를 내지 않는다
    const tag = el("span", "sl-verify");
    tag.dataset.format = fmt;
    if (fmt === "docx" && slNoDocx(s)) { // docx 운반 문서를 못 지었다 — 검증할 것이 없다
      tag.dataset.status = "nodocx";
      tag.textContent = "docx 없음";
      tag.title = "docx 서식을 짓지 못했습니다 — 「docx 받기」 를 누르면 그 자리에서 다시 지어 봅니다";
      out.push(tag);
      continue;
    }
    const v = slVerifyOf(s, fmt), st = v ? v.status || "" : "", c = v && v.coverage;
    tag.dataset.status = st || "pending";
    if (st === "running") tag.append(el("span", "sl-spin"));
    tag.append(`${fmt} ${st ? SL_VERIFY[st] || st : "검증 전"}`);
    tag.title = (st ? slVerifyHelp(st, app) : `아직 ${fmt} 서식의 PDF 검증(${app})을 하지 않았습니다 — 「다시 검증」`)
      + (c ? `\n통과 ${nf(c.pass || 0)} · 실패 ${nf(c.fail || 0)} · 모름 ${nf(c.unknown || 0)} · 재지 못함 ${nf(c.unsupported || 0)}` : "");
    out.push(tag);
    if (v && v.stale && st !== "running") {
      const old = el("span", "sl-verify stale", `${fmt} 검증 뒤 바뀜`);
      old.dataset.format = fmt;
      old.dataset.status = "stale";
      old.title = "검증한 뒤에 띠 수·구조·항목이 바뀌었습니다 — 「다시 검증」 을 누르세요";
      out.push(old);
    }
  }
  return out;
}

async function styleGet(s, fmt) { // 「hwpx 받기」·「docx 받기」 — 운반 문서를 내려받는다(GET …/carrier?format= : docx 가 없으면 서버가 그 자리에서 지어 붙인다 · 못 지으면 422 — 그 까닭을 줄에)
  try {
    const r = await fetch(styleUrl(s.id, `/carrier?format=${fmt}`));
    if (!r.ok) { let m = `${r.status} ${r.statusText}`; try { m = (await r.json()).detail || m; } catch { /* 글 아님 */ } throw new Error(m); }
    const blob = await r.blob(), cd = r.headers.get("Content-Disposition") || "", m = /filename\*=UTF-8''([^;]+)/.exec(cd), a = el("a");
    a.href = URL.createObjectURL(blob);
    a.download = m ? decodeURIComponent(m[1]) : `${(s.name || s.id).replace(/[\\/:*?"<>|]+/g, "_")}.${fmt}`;
    document.body.append(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
    styleSay(s.id, "");
    if (fmt === "docx" && slNoDocx(s)) { s.docx = true; if (s.verifyDocx === null) delete s.verifyDocx; } // 방금 지어 붙였다 — 「docx 없음」 을 걷는다(검증은 「다시 검증」)
  } catch (e) { styleSay(s.id, `${fmt} 서식을 받지 못했습니다: ${e.message || e}`, true); }
  styleLibDraw();
}

function stylePageLine(s, line, rest) { // 문서 서식의 요약 줄 — 목록 요약에 page 가 없으면 그 서식을 한 번 읽어 채운다(view.summary)
  const sum = s.summary || slPageText(s.page, s.body);
  if (sum) { line.textContent = [sum, ...rest].join(" · "); return; }
  line.textContent = ["쪽 설정을 읽는 중…", ...rest].join(" · ");
  if (s.pageAsked) return;
  s.pageAsked = true;
  api(styleUrl(s.id)).then((m) => {
    const v = m.view || {};
    s.page = m.page || v.page || null;
    s.body = m.body || v.body || null;
    s.summary = v.summary || slPageText(s.page, s.body) || "쪽 설정 없음";
    if (line.isConnected) line.textContent = [s.summary, ...rest].join(" · ");
  }).catch(() => { if (line.isConnected) line.textContent = ["쪽 설정을 읽지 못함", ...rest].join(" · "); });
}

// 서식의 원본 문서(spec_서식복사 ② §17) — 「원본 연구개발계획서_양식.hwpx · 프로젝트 A · 표 3번째 외 2개 문서」. 자세한 것(TASK · 라운드 · 뽑은 때 · 같은 서식이 나온 다른 문서)은 그 줄의 풍선에.
function slSrcText(s) {
  const src = s.source || {}, n = (s.seenIn || []).length;
  if (!src.name) return "";
  return `원본 ${[src.name, src.project ? `프로젝트 ${src.project}` : "", src.where || (src.page ? `${src.page}쪽` : "")].filter(Boolean).join(" · ")}${n ? ` 외 ${nf(n)}개 문서` : ""}`;
}
function slSrcTitle(s) {
  const src = s.source || {}, seen = s.seenIn || [];
  if (!src.name) return "";
  const task = (x) => (typeof taskName === "function" && x.job ? taskName("job", x.job) : "") || x.job || "";
  const one = (x) => [x.name, x.project ? `프로젝트 ${x.project}` : "", task(x) ? `TASK ${task(x)}` : "", x.round ? `라운드 ${x.round}` : "", x.where || "", x.at ? slWhen(x.at) : ""].filter(Boolean).join(" · ");
  return [`이 서식을 뽑은 문서 — ${one(src)}${src.work ? "" : " (파일에서 바로 뽑음)"}`, ...(seen.length ? ["같은 서식이 나온 다른 문서:", ...seen.map((x) => `· ${one(x)}`)] : [])].join("\n");
}

function styleItemEl(s) {
  const box = el("section", "sl-item"), head = el("div", "sl-head"), E = STYLE.edit && STYLE.edit.sid === s.id ? STYLE.edit : null;
  // 문서에 쓰는 동작 — hwpx 문서는 모두 · docx 문서는 「빈 표 넣기」·「고른 문단에 입히기」 만(spec_서식복사 ② §2·§9) · 문서가 없으면(시작 화면) 모두 꺼짐
  const doc = !!state.id, dx = doc && state.format === "docx", can = doc && !dx, src = s.source || {}, items = s.items || [];
  const need = can ? "" : dx ? "\ndocx 문서에는 빈 표 넣기 · 문단에 입히기만 됩니다" : "\n문서를 열어야 합니다", needAny = doc ? (dx && slNoDocx(s) ? "\n이 서식에는 docx 서식이 없습니다 — 「docx 받기」 로 다시 지어 보세요" : "") : "\n문서를 열어야 합니다";
  const canAny = doc && !(dx && slNoDocx(s)); // hwpx·docx 문서 모두에서 되는 동작(빈 표 넣기 · 고른 문단에 입히기)
  box.dataset.style = s.id;
  box.dataset.kind = s.kind || "";
  box.dataset.tab = slTabOf(s);
  box.append(styleLibPic(s)); // 그림이 먼저(② §13) — 이름·꼬리표·요약·동작은 그 설명으로 아래에
  if (E && E.mode === "rename") { // 이름 줄 — Enter 저장 · Esc 취소
    const inp = el("input", "sl-rename");
    inp.type = "text"; inp.maxLength = 60; inp.value = E.draft; inp.disabled = !!E.busy;
    inp.setAttribute("aria-label", `「${s.name}」 의 새 이름`);
    inp.oninput = () => { E.draft = inp.value; };
    inp.onkeydown = (ev) => {
      if (ev.isComposing || ev.keyCode === 229) return;
      if (ev.key === "Enter") { ev.preventDefault(); styleRename(s); } else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); STYLE.edit = null; styleLibDraw(); }
    };
    head.append(inp, hBtn("저장", () => styleRename(s), { cls: "btn sm primary", disabled: !!E.busy }), hBtn("취소", () => { STYLE.edit = null; styleLibDraw(); }, { disabled: !!E.busy }));
  } else {
    head.append(el("strong", "sl-name", s.name || "(이름 없음)"));
    const fid = SL_FID[s.fidelity];
    if (fid) { const t = el("span", "hb", fid[0]); t.title = fid[1]; t.dataset.fidelity = s.fidelity; head.append(t); }
    if (s.kind === "text" && slTabOf(s) === "para" && SL_ROLE[s.role]) { const t = el("span", "hb", SL_ROLE[s.role]); t.title = "이 문단 서식의 역할"; t.dataset.role = s.role; head.append(t); } // 문단 서식의 역할 꼬리표(② §12)
    head.append(...styleVerifyEls(s));
  }
  const parts = [slSrcText(s), s.kind === "table" && s.rows ? `${s.rows}×${s.cols}` : "", s.kind === "table" ? slBandsText(s.bands) : "",
    s.kind === "table" && s.blueprint ? "구조 있음" : "", s.kind === "text" && items.length && slTabOf(s) === "content" ? `레벨 ${nf(items.length)}` : "", slWhen(s.updated || s.created)].filter(Boolean);
  const line = el("p", "sl-src", parts.join(" · "));
  const tip = [s.note || "", slSrcTitle(s)].filter(Boolean).join("\n\n");
  if (tip) line.title = tip;
  if (src.name) line.dataset.src = src.name;
  box.append(head);
  if (s.kind === "page") { // 문서 서식 — 요약 한 줄(쪽 설정 · 본문 바탕 글 모양)이 먼저, 원본·때는 그 아래 줄
    const sum = el("p", "sl-page");
    stylePageLine(s, sum, []);
    box.append(sum);
  }
  box.append(line);
  const nLoss = typeof s.losses === "number" ? s.losses : (s.losses || []).length;
  const more = el("details", "sl-more"), moreBody = el("div");
  more.open = STYLE.more.has(s.id);
  more.append(el("summary", null, `뺀 것 ${nf(nLoss)} · 검증 내역`), moreBody);
  more.ontoggle = () => { if (!more.open) STYLE.more.delete(s.id); else { STYLE.more.add(s.id); if (!moreBody.childElementCount) styleMoreFill(s, moreBody); } }; // 펴 둔 채 다시 그릴 때는 아래에서 이미 채운다
  if (more.open) styleMoreFill(s, moreBody);
  box.append(more);
  if (s.kind === "text" && items.length) { // 글 서식 — 항목(레벨)마다 한 줄
    const grid = el("div", "sl-levels");
    for (const it of items) {
      const m = it.marker || {}, name = el("span", "sl-lname");
      name.append(it.name || "(이름 없음)");
      if (m.mode === "literal" && m.literal) name.append(el("i", null, ` ${m.literal}`));
      else if (m.mode === "auto") name.append(el("i", null, " 자동 번호"));
      if (it.sample) name.append(el("i", null, ` · ${it.sample}`));
      name.title = [it.name, m.mode === "auto" ? "자동 번호 — 대상 문서의 번호 설정을 따릅니다" : m.literal ? `레터 「${m.literal}」` : "", it.sample].filter(Boolean).join("\n");
      const b = hBtn("글자·문단 모양 입히기", () => styleApply(s, "format", it), { disabled: !canAny, title: `문서에서 끌어 고른 문단들(없으면 커서 문단)에 이 항목의 글자·문단 모양을 입힙니다 — 글·레터·기존 번호는 그대로 · 실행 취소로 되돌림${needAny}` }); // 동작 이름 = 바꾸는 범위(② §13 — 전의 「고른 문단에 입히기」)
      b.dataset.slItem = it.key;
      const fon = !!(E && E.mode === "fmt" && E.item === it.key); // 이 항목의 값 고치기 칸이 펴져 있나(② §19-6)
      const fx = hBtn("값 고치기", () => slFmtToggle(s, it), { cls: "btn sm" + (fon ? " on" : ""), disabled: !!(E && E.busy),
        title: "이 항목의 앞 여백 · 2번째 줄 · 폰트 · 크기 · 줄간격을 고칩니다 — 보관함의 이 서식이 새 판이 되고 PDF 검증을 다시 합니다(문서는 안 바뀜)" });
      fx.dataset.slFmt = it.key;
      fx.setAttribute("aria-expanded", String(fon));
      grid.append(el("span", "sl-lv", it.level ? `L${it.level}` : "문단"), name, b, fx);
      if (fon) grid.append(slFmtForm(s, it, E));
    }
    box.append(grid);
  }
  const acts = el("div", "sl-acts"), act = (key, b) => { b.dataset.slAct = key; acts.append(b); return b; };
  if (s.kind === "table") {
    if (s.blueprint) act("blank", hBtn("빈 표 넣기", () => styleApply(s, "tableBlank"), { disabled: !canAny, title: `커서가 있는 문단(칸 안이면 그 표) 바로 뒤에 이 서식·구조의 빈 표를 넣습니다 — 실행 취소로 되돌림${needAny}` }));
    act("restyle", hBtn("표 모양 입히기", () => styleApply(s, "tableRestyle"), { disabled: !can, title: `문서에서 누른 표(고른 표)에 이 서식의 표 모양(음영·괘선·칸 글 모양)을 입힙니다 — 구조·글·칸 크기는 그대로 · 실행 취소로 되돌림${need}` })); // 전의 「고른 표에 입히기」
  } else if (s.kind === "page") { // 쪽 설정 — 이 문서의 모든 구역 쪽 설정을 이 값으로(hwpx 만 — spec_서식복사 ② §9). 전의 「이 문서에 입히기」
    act("page", hBtn("쪽 설정 입히기", () => styleApply(s, "page"), { disabled: !can, title: `이 문서의 모든 구역 쪽 설정(용지 크기·방향·여백)을 이 서식의 값으로 바꿉니다 — 본문 글 모양은 그대로 · 실행 취소로 되돌림${need}` }));
  } else if (s.kind === "cover") { // 표지 서식 — 이 문서의 맨 앞에 표지의 블록들을 넣는다(hwpx 만 — ② §14)
    act("cover", hBtn("표지 넣기", () => styleApply(s, "cover"), { disabled: !can, title: `이 문서의 맨 앞에 이 표지(견본 글이 든 제목·기관·날짜 자리 · 표지 표)를 넣습니다 — 원래 첫 내용은 다음 쪽에서 시작 · 실행 취소로 되돌림${need}` }));
  }
  // 관리 단추(받기 둘 · 이름 바꾸기 · 복사본 만들기 · 다시 검증 · 지우기)는 「⋯ 더보기」 한 단추 아래로(줄 안에서 펴진다 — 팝업 아님: ② §13). 이름을 고치는 중·지우기 확인 중에는 펴 둔다(값 고치기는 항목 줄 안이라 펴지 않는다)
  const open = STYLE.manage.has(s.id) || !!(E && E.mode !== "fmt"), manage = el("div", "sl-manage"), mact = (key, b) => { b.dataset.slAct = key; manage.append(b); return b; };
  acts.append(el("span", "sl-gap"));
  const more2 = act("more", hBtn("⋯ 더보기", () => { if (STYLE.manage.has(s.id)) STYLE.manage.delete(s.id); else STYLE.manage.add(s.id); styleLibDraw(); }, { cls: "btn sm" + (open ? " on" : ""), title: "hwpx 받기 · docx 받기 · 이름 바꾸기 · 복사본 만들기 · 다시 검증 · 지우기" }));
  more2.setAttribute("aria-expanded", String(open));
  mact("getHwpx", hBtn("hwpx 받기", () => styleGet(s, "hwpx"), { title: "이 서식을 담은 hwpx 문서를 내려받습니다(한글에서 열어 서식을 복사해 쓸 수 있습니다)" }));
  if (STYLE.dual) mact("getDocx", hBtn("docx 받기", () => styleGet(s, "docx"), { title: "이 서식을 담은 docx 문서를 내려받습니다(Word 에서 열어 서식을 복사해 씁니다)" + (slNoDocx(s) ? "\ndocx 서식이 아직 없습니다 — 누르면 그 자리에서 지어 봅니다" : "") }));
  mact("rename", hBtn("이름 바꾸기", () => { STYLE.edit = { sid: s.id, mode: "rename", draft: s.name || "" }; STYLE.manage.add(s.id); styleLibDraw(); }));
  mact("copy", hBtn("복사본 만들기", () => styleCopy(s), { disabled: !!STYLE.copying, title: "같은 값으로 새 서식을 만듭니다(이름 「<이름> 복사」 · PDF 검증은 새로) — 이 서식은 그대로. 만든 뒤 바로 이름을 바꿀 수 있습니다" })); // ② §19-6(답 ㉮)
  const canVerify = STYLE.pdf || (STYLE.dual && STYLE.pdfDocx); // 두 형식 가운데 하나라도 출력할 수 있으면
  mact("verify", hBtn("다시 검증", () => styleVerify(s), { disabled: !canVerify || slRunning(s), title: canVerify ? `${STYLE.dual ? "한글(hwpx)·Word(docx)" : "한글"}로 견본을 다시 출력해 서식 값과 견줍니다(수 초~수십 초 — 끝나면 상태가 바뀝니다)` : "PDF 출력(한글·Word)이 꺼져 있습니다" }));
  mact("delete", hBtn("지우기", () => { STYLE.edit = { sid: s.id, mode: "delete" }; STYLE.manage.add(s.id); styleLibDraw(); }, { cls: "btn sm danger", disabled: !!(E && E.mode === "delete") }));
  box.append(acts);
  if (open) box.append(manage);
  if (E && E.mode === "delete") { // 한 번 더 눌러야 지운다(그 줄에서 — 확인 창 없음)
    const row = el("div", "sl-confirm"), yes = hBtn("지우기", () => styleDelete(s), { cls: "btn sm danger", disabled: !!E.busy, title: "보관함에서 지웁니다 — 되살릴 수 없습니다(이 서식으로 이미 만든 표·글은 그대로)" });
    yes.dataset.slAct = "deleteYes";
    row.append(el("span", null, `「${s.name}」 을(를) 보관함에서 지울까요?`), yes, hBtn("취소", () => { STYLE.edit = null; styleLibDraw(); }, { disabled: !!E.busy }));
    box.append(row);
  }
  const m = STYLE.msg[s.id];
  if (m) box.append(el("p", "sl-msg" + (m.err ? " err" : ""), m.text));
  return box;
}

async function styleMoreFill(s, box) { // 뺀 것 · 필요한 글꼴 · 검사마다의 결과 — 펼 때 그 서식 전체를 읽는다(GET /api/styles/{sid})
  const key = `${s.id}|${s.revision || ""}|${s.verify ? s.verify.status : ""}|${s.verifyDocx ? s.verifyDocx.status : ""}`;
  let m = STYLE.full[key];
  if (!m) {
    box.replaceChildren(slRun("읽는 중…"));
    try { m = STYLE.full[key] = await api(styleUrl(s.id)); }
    catch (e) { if (box.isConnected) box.replaceChildren(el("p", "sl-msg err", `읽지 못했습니다: ${styleErr(e)}`)); return; }
  }
  if (!box.isConnected) return;
  const ul = el("ul"), losses = Array.isArray(m.losses) ? m.losses : [], fonts = (m.requirements && m.requirements.fonts) || [], dual = STYLE.dual || "verifyDocx" in m || "docx" in m;
  const dxLoss = m.docx && Array.isArray(m.docx.losses) ? m.docx.losses : [];
  for (const t of losses) ul.append(el("li", null, `뺀 것 — ${t}`));
  if (!losses.length) ul.append(el("li", "unknown", "뺀 것 없음"));
  for (const t of dxLoss) { const li = el("li", null, `docx 로 못 옮긴 것 — ${t}`); li.dataset.format = "docx"; ul.append(li); } // docx 운반 문서를 지을 때 뺀 것(자동 번호 · Word 에 없는 선 종류 … — spec_서식복사 ② §4)
  if (fonts.length) ul.append(el("li", null, `필요한 글꼴 — ${fonts.join(" · ")}`));
  for (const [fmt, vkey, app] of SL_FORMATS) { // 검증 내역은 형식마다(hwpx = 한글 · docx = Word)
    if (fmt === "docx" && !dual) continue;
    const vr = m[vkey] || null, mark = (li) => { li.dataset.format = fmt; ul.append(li); return li; };
    if (dual) mark(el("li", "sl-fmt", fmt === "docx" && m.docx === null ? "docx 검증 — docx 서식 없음" : `${fmt} 검증(${app})${vr ? "" : " — 아직 안 함"}`));
    for (const c of (vr && vr.checks) || []) {
      const n = [c.pass ? `통과 ${nf(c.pass)}` : "", c.fail ? `실패 ${nf(c.fail)}` : "", c.unknown ? `모름 ${nf(c.unknown)}` : ""].filter(Boolean).join(" · ");
      const ex = (c.examples || [])[0];
      mark(el("li", c.status, `${SL_CHECK[c.what] || c.what} — ${SL_STATUS[c.status] || c.status}${n ? `(${n})` : ""}${c.note ? ` · ${c.note}` : ""}${ex ? ` · 예: ${ex.where || ""} ${ex.want} → ${ex.got}` : ""}`));
    }
    if (vr && vr.note) mark(el("li", null, vr.note));
    if (vr && vr.at) mark(el("li", "unknown", `검증 ${slWhen(vr.at)}${vr.pages ? ` · ${vr.pages}쪽` : ""}${vr.renderer && vr.renderer.name ? ` · ${vr.renderer.name}` : ""}`));
  }
  box.replaceChildren(ul);
}

function styleMerge(m) { // 서식 하나 전체(meta) → 목록의 그 줄(요약 꼴)
  const s = (STYLE.list || []).find((x) => x.id === m.id);
  if (!s) return null;
  for (const k of ["name", "note", "revision", "updated", "bands", "rows", "cols", "fidelity", "source", "items", "role", "leveled"]) if (k in m) s[k] = m[k];
  if ("blueprint" in m) s.blueprint = !!m.blueprint;
  if (Array.isArray(m.losses)) s.losses = m.losses.length;
  for (const key of ["verify", "verifyDocx"]) if (key in m) { const v = m[key]; s[key] = v ? { status: v.status, coverage: v.coverage || null, stale: !!v.stale } : null; } // 두 형식의 검증 요약
  if ("docx" in m) s.docx = !!m.docx; // meta 의 docx = {sha256, losses} | null → 요약은 있나 없나
  if (m.page) { s.page = m.page; s.body = m.body || null; s.summary = (m.view && m.view.summary) || slPageText(m.page, m.body); } // 문서 서식의 요약 줄
  return s;
}
function styleSay(sid, text, err = false) { if (text) STYLE.msg[sid] = { text, err }; else delete STYLE.msg[sid]; }

function stylePoll() { // 「검증 중」 인 서식이 있는 동안 2초마다 그 서식을 다시 읽는다(열이 보관함일 때만) — 끝나면 그 줄이 바뀐다
  clearTimeout(STYLE.pollTimer);
  const running = (STYLE.list || []).filter(slRunning); // 두 형식 가운데 하나라도 도는 서식(hwpx → docx 차례로 돈다 — spec_서식복사 ② §7)
  if (!running.length || !styleLibOn()) return;
  STYLE.pollTimer = setTimeout(async () => {
    let changed = false;
    for (const s of running) {
      try {
        const m = await api(styleUrl(s.id)), was = SL_FORMATS.map(([fmt]) => (slVerifyOf(s, fmt) || {}).status || "").join("|");
        styleMerge(m);
        if (!("verifyDocx" in m) && (s.verifyDocx || {}).status === "running") delete s.verifyDocx; // docx 검증 기록을 안 주는 서버 — 화면이 걸어 둔 「검증 중」 을 걷는다(영영 돌지 않게)
        if (SL_FORMATS.map(([fmt]) => (slVerifyOf(s, fmt) || {}).status || "").join("|") !== was) changed = true; // 한 형식이 끝나면 그 꼬리표부터 바뀐다
      } catch (e) { if (e.status === 404 && e.message !== "Not Found") { STYLE.list = (STYLE.list || []).filter((x) => x.id !== s.id); changed = true; } } // 그 사이 지워짐(서버가 「없는 서식」 이라 답함) · 그 밖의 오류는 다음 차례에 다시
    }
    if (changed) { styleChanged(); styleLibDraw(); } else stylePoll();
  }, 2000);
}

async function styleRename(s) {
  const E = STYLE.edit;
  if (!E || E.sid !== s.id || E.mode !== "rename" || E.busy) return;
  const name = (E.draft || "").trim().replace(/\s+/g, " ");
  if (!name) return;
  if (name === s.name) { STYLE.edit = null; styleLibDraw(); return; }
  E.busy = true;
  try {
    const m = await api(styleUrl(s.id), { method: "PUT", headers: H_JSON, body: JSON.stringify({ expectedRevision: s.revision, name }) });
    styleMerge({ name, ...m, id: s.id });
    styleSay(s.id, "");
    STYLE.edit = null;
    styleChanged();
  } catch (e) {
    E.busy = false;
    if (e.status === 409) { // 다른 곳에서 먼저 바뀜 — 새 판을 읽고 그 위에 다시 저장하게
      styleSay(s.id, "다른 곳에서 이 서식을 먼저 고쳤습니다 — 새 판을 읽었습니다. 「저장」 을 한 번 더 누르세요.", true);
      try { styleMerge(await api(styleUrl(s.id))); } catch { /* 지워졌으면 다음 읽기에서 빠진다 */ }
    } else styleSay(s.id, `이름을 바꾸지 못했습니다: ${styleErr(e)}`, true);
  }
  styleLibDraw();
}

async function styleDelete(s) {
  const E = STYLE.edit;
  if (!E || E.sid !== s.id || E.mode !== "delete" || E.busy) return;
  E.busy = true;
  try {
    await api(styleUrl(s.id, `?expectedRevision=${encodeURIComponent(s.revision || "")}`), { method: "DELETE" });
    STYLE.list = (STYLE.list || []).filter((x) => x.id !== s.id);
    styleSay(s.id, "");
    toast(`서식 「${s.name}」 을(를) 보관함에서 지웠습니다`);
    styleChanged();
  } catch (e) {
    if (e.status === 409) { styleSay(s.id, "다른 곳에서 이 서식을 먼저 고쳤습니다 — 새 판을 읽었습니다. 다시 확인하고 지우세요.", true); try { styleMerge(await api(styleUrl(s.id))); } catch { /* 그대로 */ } }
    else if (e.status === 404 && e.message !== "Not Found") STYLE.list = (STYLE.list || []).filter((x) => x.id !== s.id); // 이미 지워짐
    else styleSay(s.id, `지우지 못했습니다: ${styleErr(e)}`, true);
  }
  STYLE.edit = null;
  styleLibDraw();
}

// ---- 서식 값 고치기 · 복사본 만들기(spec_서식복사 ② §19-6 — 사용자 "앞 여백, 2번째줄 여백 시작 위치, 폰트, 글자크기, 줄간격들을 수정할 수 있는 기능을 넣어줘" · "서식을 복사하기" → 답 ㉮·㉯) ------------------
// 값 고치기 = 글 서식(내용 서식 레벨 · 문단 서식)의 항목 줄 안에서 다섯 칸(팝업 아님 — Enter 저장 · Esc 취소: design.md §13) → PUT …/items/{key}/format {expectedRevision, changes: 바뀐 칸만}
// → 새 revision 의 meta(운반 문서의 견본 문단을 고침 · PDF 검증 다시). 409 = 다른 곳에서 먼저 고침 — 새 판을 읽고 칸의 값은 그대로 둔다. 표·쪽 설정·표지는 v1 에 없다(② §19-8)
const SL_FV = [["line1Mm", "앞 여백", "mm", 5, 0, 300, 10], ["line2Mm", "2번째 줄", "mm", 5, 0, 300, 10], ["font", "폰트", "", 0, 1, 40, 0], ["sizePt", "크기", "pt", 4, 1, 200, 10], ["lineSpacingPct", "줄간격", "%", 3, 50, 500, 1]]; // [키, 이름, 단위, 숫자 칸 자릿수, 아래, 위(폰트는 자 수), 반올림(10 = 0.1 단위)] — 서식 지도(② §19-3)와 같은 다섯
const SL_FV_HELP = "앞 여백 = 첫 줄이 시작하는 자리(왼쪽 여백 + 들여쓰기) · 2번째 줄 = 둘째 줄부터 시작하는 자리(왼쪽 여백 + 내어쓰기)\n폰트·크기는 본문 글자에만(레터·번호는 그대로) · 줄간격은 % · 비운 칸은 그대로 둡니다\n저장하면 보관함의 이 서식이 새 판이 되고 PDF 검증을 다시 합니다 — 문서는 안 바뀝니다(문서에는 「글자·문단 모양 입히기」)";
function slFmtBase(f) { // 항목의 서식 요약 → 다섯 칸의 값(② §19-1 — line1 = 왼쪽 여백 + max(첫 줄, 0) · line2 = 왼쪽 여백 + max(−첫 줄, 0)). 모르는 값은 null(빈 칸)
  f = f && typeof f === "object" ? f : {};
  const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null), r = (v, d) => (v == null ? null : Math.round(v * d) / d);
  const left = num(f.indentLeftMm), first = num(f.firstLineMm), known = left != null || first != null;
  return { line1Mm: known ? r((left || 0) + Math.max(first || 0, 0), 10) : null, line2Mm: known ? r((left || 0) + Math.max(-(first || 0), 0), 10) : null,
    font: typeof f.font === "string" ? f.font : "", sizePt: r(num(f.sizePt), 10), lineSpacingPct: r(num(f.lineSpacingPct), 1) };
}
function slFontList() { // 폰트 칸의 고르기(datalist) — 보관함 목록의 글 서식 항목 · 쪽 설정 바탕 글에 있는 글꼴
  const out = new Set(), add = (f) => { if (typeof f === "string" && f.trim()) out.add(f.trim()); };
  for (const s of STYLE.list || []) { for (const it of s.items || []) add(it && it.format && it.format.font); add(s.body && s.body.format && s.body.format.font); }
  return [...out].sort((a, b) => a.localeCompare(b, "ko"));
}
function slFmtToggle(s, it) { // 「값 고치기」 — 그 항목의 칸을 펴고 접는다(한 번에 하나 — 다른 항목의 고치기·이름 바꾸기는 닫힌다)
  const E = STYLE.edit;
  if (E && E.busy) return;
  if (E && E.mode === "fmt" && E.sid === s.id && E.item === it.key) STYLE.edit = null;
  else { const base = slFmtBase(it.format); STYLE.edit = { sid: s.id, mode: "fmt", item: it.key, base, draft: Object.fromEntries(SL_FV.map(([k]) => [k, base[k] == null ? "" : String(base[k])])), err: "", focus: null }; }
  styleLibDraw();
}
function slFmtDiff(E, k, d) { // 그 칸이 처음 값과 다른가(강조 — 비운 칸은 「그대로」)
  const raw = String(E.draft[k] == null ? "" : E.draft[k]).trim();
  if (!raw) return false;
  if (k === "font") return raw.replace(/\s+/g, " ") !== E.base.font;
  const v = Number(raw);
  return !Number.isFinite(v) || E.base[k] == null || Math.abs(Math.round(v * d) / d - E.base[k]) > 1e-9;
}
function slFmtChanges(E) { // 바뀐 칸만 → {changes} | {err, key}. 비운 칸은 그대로 · 범위는 서식 지도와 같다(② §19-7 — mm 0~300 · pt 1~200 · % 50~500 · 폰트 1~40자)
  const changes = {};
  for (const [k, label, unit, , lo, hi, d] of SL_FV) {
    const raw = String(E.draft[k] == null ? "" : E.draft[k]).trim().replace(/\s+/g, " ");
    if (!raw || !slFmtDiff(E, k, d)) continue;
    if (k === "font") { if (raw.length > hi) return { err: `${label}: ${hi}자까지 넣을 수 있습니다`, key: k }; changes[k] = raw; continue; }
    const v = Number(raw);
    if (!Number.isFinite(v) || v < lo || v > hi) return { err: `${label}: ${lo}~${hi}${unit} 사이의 수를 넣으세요`, key: k };
    changes[k] = Math.round(v * d) / d;
  }
  return { changes };
}
function slFmtForm(s, it, E) { // 항목 줄 바로 아래 그 줄 안의 칸(.sl-fform — 격자 한 줄을 다 쓴다): 이름 · 칸 · 단위가 한 묶음(design.md §1-4) · 숫자 칸은 자릿수 폭 28px(§1-3) · 설명은 노트 도움말(§1-6)
  const f = el("div", "sl-fform"), row = el("div", "sl-frow"), dl = el("datalist");
  f.dataset.slFform = it.key;
  f.setAttribute("role", "group");
  f.setAttribute("aria-label", `「${it.name || it.key}」 값 고치기`);
  dl.id = "slFontList";
  for (const name of slFontList()) { const o = el("option"); o.value = name; dl.append(o); }
  const keys = (ev) => {
    if (ev.isComposing || ev.keyCode === 229) return;
    if (ev.key === "Enter") { ev.preventDefault(); styleFmtSave(s); } else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); STYLE.edit = null; styleLibDraw(); }
  };
  for (const [k, label, unit, ch, lo, hi, d] of SL_FV) {
    const lab = el("label", "sl-fv"), inp = el("input");
    inp.dataset.slFv = k;
    if (k === "font") { inp.type = "text"; inp.maxLength = hi; inp.setAttribute("list", dl.id); inp.autocomplete = "off"; }
    else { inp.type = "number"; inp.min = String(lo); inp.max = String(hi); inp.step = String(1 / d); inp.inputMode = "decimal"; inp.style.width = `calc(${ch}ch + 20px)`; }
    inp.value = E.draft[k] == null ? "" : E.draft[k];
    inp.disabled = !!E.busy;
    inp.classList.toggle("chg", slFmtDiff(E, k, d));
    inp.oninput = () => { E.draft[k] = inp.value; inp.classList.toggle("chg", slFmtDiff(E, k, d)); };
    inp.onfocus = () => { E.focus = k; };
    inp.onkeydown = keys;
    lab.dataset.slFv = k;
    lab.append(el("span", "sl-fv-name", label), inp);
    if (unit) lab.append(el("span", "sl-fv-unit", unit));
    row.append(lab);
  }
  const acts = el("div", "sl-facts"), save = hBtn("저장", () => styleFmtSave(s), { cls: "btn sm primary", disabled: !!E.busy, title: "바뀐 칸만 보관함의 이 서식에 저장합니다 · Enter" });
  const no = hBtn("취소", () => { STYLE.edit = null; styleLibDraw(); }, { disabled: !!E.busy, title: "고치지 않고 닫습니다 · Esc" });
  save.dataset.slAct = "fmtSave";
  no.dataset.slAct = "fmtCancel";
  acts.append(save, no, hHelp("값 고치기 안내", SL_FV_HELP));
  if (E.busy) acts.append(slRun("저장 중…"));
  f.append(row, dl, acts);
  if (E.err) { const p = el("p", "sl-msg err", E.err); p.setAttribute("role", "alert"); f.append(p); }
  return f;
}
async function styleFmtSave(s) {
  const E = STYLE.edit;
  if (!E || E.mode !== "fmt" || E.sid !== s.id || E.busy) return;
  const cur = (STYLE.list || []).find((x) => x.id === s.id) || s, got = slFmtChanges(E);
  if (got.err) { E.err = got.err; E.focus = got.key || E.focus; styleLibDraw(); return; }
  if (!Object.keys(got.changes).length) { STYLE.edit = null; styleLibDraw(); return; } // 바뀐 칸이 없다 — 그냥 닫는다
  E.busy = true;
  E.err = "";
  styleLibDraw();
  try {
    const m = await api(styleUrl(cur.id, `/items/${encodeURIComponent(E.item)}/format`), { method: "PUT", headers: H_JSON, body: JSON.stringify({ expectedRevision: cur.revision, changes: got.changes }) });
    styleMerge({ ...m, id: cur.id }); // 새 revision — 그림(열쇠에 revision)·검증 꼬리표가 새것으로
    if (STYLE.edit === E) STYLE.edit = null;
    styleSay(cur.id, slRunning(cur) ? "값을 고쳤습니다 — 다시 검증 중" : "값을 고쳤습니다");
    styleChanged();
  } catch (e) {
    E.busy = false;
    if (e.status === 409) { // 다른 곳에서 먼저 바뀜 — 새 판을 읽고(처음 값도 새것으로) 고친 칸은 그대로 두어 다시 저장하게
      try { styleMerge(await api(styleUrl(cur.id))); } catch { /* 지워졌으면 다음 읽기에서 빠진다 */ }
      const it = (cur.items || []).find((x) => x && x.key === E.item);
      if (it) E.base = slFmtBase(it.format);
      E.err = "다른 곳에서 이 서식을 먼저 고쳤습니다 — 새 판을 읽었습니다. 칸의 값을 확인하고 「저장」 을 한 번 더 누르세요.";
    } else E.err = `값을 고치지 못했습니다: ${styleErr(e)}`;
  }
  styleLibDraw();
}

function slSummary(m) { // 서식 하나 전체(meta) → 목록 줄의 꼴(GET /api/styles 의 요약 — losses 는 수 · blueprint 는 있나 · 검증은 {status, coverage, stale} · docx 는 있나)
  const s = { ...m };
  delete s.view;
  s.losses = Array.isArray(m.losses) ? m.losses.length : m.losses || 0;
  s.blueprint = !!m.blueprint;
  for (const key of ["verify", "verifyDocx"]) if (key in m) { const v = m[key]; s[key] = v ? { status: v.status, coverage: v.coverage || null, stale: !!v.stale } : null; }
  if ("docx" in m) s.docx = !!m.docx;
  if (m.kind === "text" && typeof m.leveled !== "boolean") s.leveled = (m.items || []).some((it) => it && it.level != null);
  return s;
}
async function styleCopy(s) { // 「복사본 만들기」(② §19-6 — 답 ㉮) — POST /api/styles/{sid}/copy → 새 서식(같은 운반 문서·같은 값 · 이름 「<이름> 복사」 · 검증은 새로). 그 줄 바로 뒤에 넣고 그 줄로 가서 이름 칸을 연다
  if (STYLE.copying) return;
  STYLE.copying = s.id;
  styleLibDraw();
  let made = null;
  try {
    made = slSummary(await api(styleUrl(s.id, "/copy"), { method: "POST", headers: H_JSON, body: "{}" }));
    const list = STYLE.list || (STYLE.list = []), at = list.findIndex((x) => x.id === s.id);
    list.splice(at < 0 ? 0 : at + 1, 0, made);
    STYLE.tab = slTabOf(made);
    STYLE.edit = { sid: made.id, mode: "rename", draft: made.name || "" }; // 바로 이름을 바꾸게(Enter 저장 · Esc 면 「<이름> 복사」 그대로)
    STYLE.manage.add(made.id);
    styleSay(made.id, `「${short(s.name || "", 30)}」 의 복사본을 만들었습니다`);
    styleChanged();
  } catch (e) { styleSay(s.id, `복사본을 만들지 못했습니다: ${styleErr(e)}`, true); }
  STYLE.copying = null;
  styleLibDraw();
  const box = made && styleLibOn() ? $("headsDlgBody").querySelector(`.sl-item[data-style="${CSS.escape(made.id)}"]`) : null;
  if (box) box.scrollIntoView({ block: "nearest" });
}

async function styleVerify(s) {
  try {
    await api(styleUrl(s.id, "/verify"), { method: "POST" }); // 두 형식 모두 다시(hwpx → docx 차례 — spec_서식복사 ② §7·§8)
    s.verify = { ...(s.verify || {}), status: "running" };
    if (STYLE.dual && !slNoDocx(s)) s.verifyDocx = { ...(s.verifyDocx || {}), status: "running" };
    styleSay(s.id, "");
  } catch (e) { styleSay(s.id, `검증을 시작하지 못했습니다: ${styleErr(e)}`, true); }
  styleLibDraw();
}

async function styleApply(s, mode, item = null) { // 문서에 적용 — 구조 편집 한 번(structOp: 대기 중 글 반영 → 서버 편집 → 바뀐 블록만 다시 그림 · 실행 취소 1개)
  if (!state.id || state.busy) return;
  const sel = slSelection(), say = (t) => { styleSay(s.id, t, true); toast(t, true); styleLibDraw(); };
  let body = null;
  if (mode === "page" || mode === "cover") body = { mode }; // 쪽 설정 — 모든 구역의 쪽 설정 · 표지 — 문서의 맨 앞(둘 다 고를 자리가 없다)
  else if (mode === "tableBlank") {
    const after = slTopOf(sel.cursor || sel.table || "");
    if (!after) { say("넣을 자리를 먼저 정하세요 — 문서에서 문단에 커서를 두거나 표를 누르세요"); return; }
    body = { mode, after };
  } else if (mode === "tableRestyle") {
    if (!sel.table) { say("서식을 입힐 표를 먼저 고르세요 — 문서에서 그 표를 누르세요"); return; }
    body = { mode, table: sel.table };
  } else {
    const paras = sel.paras.length ? sel.paras : sel.cursor ? [sel.cursor] : [];
    if (!paras.length) { say("서식을 입힐 문단을 먼저 고르세요 — 문단을 끌어 고르거나 커서를 두세요"); return; }
    body = { mode: "format", item: item.key, paras };
  }
  styleSay(s.id, "");
  const r = await structOp(`styles/${encodeURIComponent(s.id)}/apply`, body); // 실패는 structOp 가 알림
  if (styleLibOn()) styleLibDraw();
  if (!r) return;
  const undo = " · 도구 줄의 실행 취소로 되돌릴 수 있습니다";
  if (mode === "page") { // 쪽 크기·여백이 바뀐다 — 응답에 paged 가 있으면 structOp 가 문서를 통째로 다시 읽어 그린다(app.js — spec_서식복사 ② §9)
    toast(`「${s.name}」 의 쪽 설정을 이 문서에 입혔습니다${r.paged && r.paged.sections ? ` — 구역 ${nf(r.paged.sections)}개` : ""}${undo}`);
  } else if (mode === "cover") { // 표지 넣기(② §14) — 응답의 covered: {blocks: n}. 문서는 structOp 가 다시 읽는다(tops 가 없는 응답이면 스스로 — 아니면 여기서 한 번 더)
    if (r.covered && r.tops && typeof reloadDoc === "function") reloadDoc();
    toast(`「${s.name}」 표지를 문서 맨 앞에 넣었습니다${r.covered && r.covered.blocks ? ` — 블록 ${nf(r.covered.blocks)}개` : ""}${undo}`);
  } else if (mode === "tableBlank") { toast(`「${s.name}」 서식의 빈 표를 넣었습니다${undo}`); if (r.made && r.made.table) setTimeout(() => slGo(r.made.table), 0); }
  else if (mode === "tableRestyle") toast(`표 ${body.table} 에 「${s.name}」 의 표 모양을 입혔습니다${undo}`);
  else toast(`문단 ${nf((r.formatted && r.formatted.paras) || body.paras.length)}개에 「${s.name} — ${item.name || item.key}」 의 글자·문단 모양을 입혔습니다${undo}`);
}

// ---- 파일에서 복사(추출) — 작업을 만들지 않는다. 시작 화면(문서 없음)에서도 된다: TASK 「문서 서식 복사」 카드에 놓은 PDF(app.js homeTaskStart) -------------------------
function styleFilePick() {
  const inp = el("input");
  inp.type = "file";
  inp.accept = ".hwp,.hwpx,.docx,.pdf";
  inp.onchange = () => styleFileExtract(inp.files[0]);
  inp.click();
}
async function styleFileExtract(file) {
  if (!file || STYLE.file) return;
  if (!/\.(hwpx?|docx|pdf)$/i.test(file.name)) { toast("hwp·hwpx·docx·pdf 파일에서 복사합니다", true); return; }
  STYLE.file = { name: file.name, t0: performance.now() };
  // 열을 바로 「서식 복사」 로 연다(시작 화면에서도 — 문서 옆 열이 시작 화면 본문 옆에 선다) — 찾는 동안 단계 줄 ① 에 동그라미 + 지난 시간(design.md §7)
  const S = STYLE.save = slSaveNew(`file|pending|${STYLE.file.t0}`, { name: file.name });
  S.loading = true;
  headsDlg("styleSave", `서식 복사 — ${file.name}`, "서식 관리자에 저장할 서식을 고릅니다 · 문서는 안 바뀝니다");
  styleSaveDraw();
  const tick = setInterval(() => { const t = styleSaveOn() && STYLE.save === S && STYLE.file ? $("headsDlgBody").querySelector(".sl-step-run .sl-run-text") : null; if (t) t.textContent = slStepRunText(S); }, 1000);
  let r = null, err = null;
  try {
    const fd = new FormData();
    fd.append("file", file);
    r = await api("/api/styles/extract-file", { method: "POST", body: fd });
  } catch (e) { err = e; }
  clearInterval(tick);
  STYLE.file = null;
  if (err) {
    toast(`서식을 찾지 못했습니다: ${styleErr(err)}`, true);
    if (STYLE.save === S) { S.loading = false; S.err = styleErr(err); if (styleSaveOn()) styleSaveDraw(); }
    if (styleLibOn()) styleLibDraw();
    return;
  }
  styleSaveOpen({ file: { ...r, name: r.name || file.name } });
}

// ---- 추출 후보(kind "styleSave") -------------------------------------------------------------------------------------------
const styleSaveOn = () => heads.dlg === "styleSave";
const styleCandUrl = () => `/api/docs/${encodeURIComponent(state.id)}/styles/candidates`;
function styleCandName(c) { const t = oneLine(c.sample || ""); return c.name || (t ? `${t.length > 16 ? t.slice(0, 16) + "…" : t} 표` : c.rows ? `표 서식 ${c.rows}×${c.cols}` : "표 서식"); }
function styleTextName(c) { // 템플릿 후보의 기본 이름 — 그래프의 안쪽 이름(표 칸 트리의 「cell:[N]」 같은 것)은 화면에 내지 않고 사슬로 짓는다(실물 확인 2026-11-14: 후보 이름 칸에 「cell:[N]」 이 보였다)
  const t = c.template;
  if (c.name || !t) return c.name || "글 서식";
  const cell = /^cell:/.test(t.name || ""), chain = (t.chain || []).map((x) => String(x).trim()).filter(Boolean).join(" › ");
  if (t.name && !cell) return t.name;
  return `${cell ? "표 칸 글머리" : `템플릿 ${t.no || ""}`.trim()}${chain ? ` ${chain}` : " 글 서식"}`.slice(0, 60);
}
const slDocStem = (S) => String(S.name || "문서").replace(/\.(hwpx?|docx|pdf)$/i, "").slice(0, 53);
function stylePageName(S, c) { return c.name || `${slDocStem(S)} 쪽 설정`; } // 쪽 설정 후보의 기본 이름 「<문서 이름> 쪽 설정」(② §12 — 전의 「… 문서 서식」)
function styleCoverName(S, c) { return c.name || `${slDocStem(S)} 표지`; } // 표지 서식 후보의 기본 이름
function styleParaName(c) { // 문단 서식 후보의 기본 이름 — 역할 + 글꼴·크기(문서의 글을 이름에 넣지 않는다)
  const f = ((c.items || [])[0] || {}).format || {}, look = [f.font || "", f.sizePt ? `${f.sizePt}pt` : ""].filter(Boolean).join(" ");
  return c.name || `${SL_ROLE[c.role] || "문단"} 서식${look ? ` — ${look}` : ""}`.slice(0, 60);
}
// 후보의 기본 이름(spec_서식복사 ② §19-2 — 사용자 "보통 문서 이름 사업계획서: body1 이런식이면 될거 같아"): 서버가 후보마다 지어 보낸 「<문서 이름>: <갈래><번호>」(defaultName — 서식 지도에서 고친 이름이면 그것).
// 옛 서버(defaultName 없음)면 화면이 짓던 이름(styleTextName · stylePageName · styleCoverName · styleParaName · styleCandName). 사람이 고친 이름(row.named)은 어느 쪽도 덮지 않는다
const slDefName = (c, fallback) => (c && typeof c.defaultName === "string" && c.defaultName.trim() ? c.defaultName.trim().replace(/\s+/g, " ").slice(0, 60) : fallback);
function slLlmNote(row, c) { // LLM 검토가 붙인 구조·겉모습의 말(② §19-2 — 전의 「LLM 이름」: 이름을 덮지 않고 **설명**(note)으로). 서버가 note 로 주면 그것, 계약 키 name 이면 그것 — 기본 이름과 같은 것은 설명이 아니다
  const t = oneLine([c.note, c.name].find((v) => typeof v === "string" && v.trim()) || "");
  return t && t !== oneLine(c.defaultName || "") && t !== row.script.name ? t.slice(0, 200) : "";
}
const slLeveled = (c) => !!c.template || (c.items || []).some((it) => it && it.level != null); // 글 후보에 레벨이 있나(없으면 문단 서식 후보 — 옛 서버가 texts 에 섞어 보낸 「서식이 같은 문단 묶음」)
const slBands0 = (b) => (b ? { headerRows: 0, headerCols: 0, footRows: 0, ...b } : null);

// ---- 후보의 검토 상태(② §15) — row.c.review = {by, seen, fixed: [{what, from, to}], doubts: [{code, text, by}]} · row.c.doubts = [코드…](스크립트 자기 점검) · row.undone = 사람이 되돌린 LLM 고침
const SL_FIX_KEYS = [[/대표|^rep$/i, "rep"], [/바탕|body/i, "bodyKey"], [/범위|끝 블록|^end$/i, "end"], [/역할|roles?$/i, "role"], [/띠|bands?/i, "bands"], [/이름|^name$/i, "name"]]; // 고침의 what → 저장 몸의 칸(되돌리면 그 칸을 안 보낸다)
function slFixKey(row, what) { const k = (SL_FIX_KEYS.find(([re]) => re.test(String(what || ""))) || [])[1] || ""; return k === "role" && row.kind === "cover" ? "roles" : k; }
function slRowDoubts(row) { // 의심(스크립트 자기 점검 + LLM) — [{code, text, by}]
  const c = row.c || {}, rv = c.review || {}, out = [], seen = new Set();
  for (const d of [...(Array.isArray(rv.doubts) ? rv.doubts : []), ...(Array.isArray(c.doubts) ? c.doubts : [])]) {
    const x = typeof d === "string" ? { code: d, text: SL_DOUBT[d] || d, by: "script" } : d && typeof d === "object" ? { code: d.code || "", text: d.text || SL_DOUBT[d.code] || d.code || "", by: d.by === "llm" ? "llm" : "script" } : null;
    if (!x || !x.text || seen.has(x.code || x.text)) continue;
    seen.add(x.code || x.text);
    out.push(x);
  }
  return out;
}
function slRowFixed(row) { // LLM 이 고친 것(되돌리지 않은 것만) — [{what, from, to, i, key}]
  const rv = (row.c || {}).review || {};
  return (Array.isArray(rv.fixed) ? rv.fixed : []).map((f, i) => ({ ...(f || {}), i, key: slFixKey(row, f && f.what) })).filter((f) => !(row.undone && row.undone.has(`#${f.i}`)));
}
const slRowKeep = (row) => { const k = (row.c || {}).keep; return k == null ? row.kind === "page" && !(row.c || {}).review : !!k; }; // 추천 — LLM 의 keep. 쪽 설정은 LLM 이 안 본 서버(옛 판)에서만 규칙으로 추천(문서에 하나)
const slRowClean = (row) => slRowKeep(row) && !slRowDoubts(row).length && !slRowFixed(row).length && !row.bandsWider; // 「한 번에 진행」 이 저장하는 것 = 추천이면서 의심·LLM 고침·띠 넓히기 제안이 없는 후보
const slFixOn = (row, key) => !(row.undone && row.undone.has(key)); // 그 칸의 LLM 고침을 되돌리지 않았다(저장 몸에 싣는다)
const slVal = (v) => { const t = v == null ? "없음" : typeof v === "object" ? JSON.stringify(v) : String(v); return t.length > 30 ? `${t.slice(0, 30)}…` : t; };
function slUnfix(row, f) { // 「되돌리기」 — 그 고침만 스크립트 값으로: 저장 몸에 그 칸을 싣지 않고(rep·bodyKey·end·roles), 화면 값(이름·띠 수·역할)은 스크립트 것으로
  row.undone.add(`#${f.i}`);
  if (f.key) row.undone.add(f.key);
  if (f.key === "name") { row.name = row.script.name; row.named = false; }
  if (f.key === "bands" && row.script.bands) row.bands = { ...row.script.bands };
  if (f.key === "role") row.role = row.script.role || null;
}
function slRowNew(kind, c, name, extra = {}) { // 후보 줄 하나 — script = 스크립트가 낸 값(LLM 고침을 되돌릴 때 돌아갈 곳) · note = LLM 검토의 설명(② §19-2 — 저장 몸의 note)
  return { kind, key: c.key, c, on: false, name, note: "", state: "", err: "", undone: new Set(), script: { name, bands: slBands0(c.bands), role: c.role || null }, ...extra };
}

// 「서식 복사」 의 상태 하나(문서·파일마다) — rows = 후보 줄(고른 것·이름·띠 수) · llm = 도는 에이전트 추출 {t0} · named = 에이전트 추출을 한 번 마쳤나 · busy = 도는 저장 {i, n, name} ·
// saved = 이번에 저장한 서식 수 · verify = 저장 뒤 검증 지켜보기 {items, t0, done, late, run} · auto = 도는 「한 번에 진행」 {t0, stop} ·
// tab = 고른 탭(② §18 — cover · content · table · page · para: 없으면 그릴 때 처음 규칙 slCtabFirst) · focus = 고른 채로 연 후보의 key(그 탭으로 바꾸고 그 줄로 굴린다)
function slSaveNew(key, file) {
  return { key, file: !!file, token: file ? file.token || null : null, name: file ? file.name : state.name, format: file ? file.format || "" : state.format || "hwpx", fidelity: (file && file.fidelity) || "", rev: null, stage2: true, rows: [], tab: null, focus: null,
    keepText: false, busy: null, llm: null, named: false, call: null, losses: [], loading: false, err: "", msg: "", msgErr: false, want: null, saved: 0, verify: null, auto: null, t0: performance.now() };
}

function styleSaveFill(S, r) { // 서버가 준 후보 → 줄(고른 것·이름·띠 수·역할은 여기서부터 화면 상태)
  // 차례 = 표지 서식 → 내용 서식(+ 그 아래 쪽 설정) → 테이블 서식 → 문단 서식(② §12). 옛 서버(covers·paras·pages 없음)면 그 구역이 빈다 · 옛 서버가 texts 에 섞어 보낸 레벨 없는 묶음(template: null)은 문단 서식 후보로 본다
  S.rows = [];
  const texts = r.texts || [], loose = texts.filter((c) => !slLeveled(c));
  // 기본 이름 = 서버의 defaultName(② §19-2 — 「사업계획서: T1」·「사업계획서: body1」·「사업계획서: table2」·「사업계획서: page」·「사업계획서: cover」) → 없으면(옛 서버) 화면이 짓던 이름
  for (const c of r.covers || []) S.rows.push(slRowNew("cover", { ...c, key: c.key || "cover" }, slDefName(c, styleCoverName(S, c))));
  for (const c of texts.filter(slLeveled)) S.rows.push(slRowNew("text", c, slDefName(c, styleTextName(c))));
  for (const c of r.pages || []) S.rows.push(slRowNew("page", { ...c, key: c.key || "page" }, slDefName(c, stylePageName(S, c))));
  for (const c of r.tables || []) S.rows.push(slRowNew("table", c, slDefName(c, styleCandName(c)), { bands: slBands0(c.bands), blueprint: false }));
  for (const c of [...(r.paras || []), ...loose]) S.rows.push(slRowNew("para", c, slDefName(c, styleParaName(c)), { role: c.role || null }));
  Object.assign(S, { rev: r.rev == null ? null : r.rev, stage2: r.stage2 !== false, losses: r.losses || [], call: r.call || null, loading: false, err: "" });
  if (r.format) S.format = r.format; // 문서의 형식(hwpx · docx) — docx 문서의 후보는 요약(fidelity "summary")이라 「글도 그대로 저장」·「구조까지 저장」 이 없다
  if (r.fidelity) S.fidelity = r.fidelity;
}
const slSaveNative = (S) => !S.file && S.format !== "docx"; // hwpx 문서의 후보 — 원본 서식 그대로 옮긴다(글 그대로·구조까지 저장 옵션이 있다)
function styleSaveParas(S) { // 고른 문단을 「레벨 없는 문단 서식」 으로 — 2단계(개요템플릿)가 없으면 커서 문단 하나도 후보(spec ② §5)
  S.rows = S.rows.filter((r) => r.kind !== "paras" || r.state === "done");
  if (S.file || S.loading || S.err) return;
  const sel = slSelection(), ids = sel.paras.length ? sel.paras : !S.stage2 && sel.cursor ? [sel.cursor] : [];
  if (ids.length) S.rows.push({ kind: "paras", key: "paras", c: {}, paras: ids, on: false, name: "문단 서식", state: "", err: "", undone: new Set(), script: { name: "문단 서식", bands: null, role: null } }); // 문단 서식 후보 구역의 맨 끝
}
function slPickTable(S, tid, blueprint) { // 그 표의 후보 줄(없으면 만든다) → 줄
  let row = S.rows.find((r) => r.kind === "table" && r.c.table === tid && r.state !== "done");
  if (!row) { // 후보에 없는 표(같은 서식 묶음의 대표가 아니거나 · 후보에서 빠진 표) — 그 표로 줄을 하나 만든다(저장 끝점은 어느 표든 받는다)
    const from = S.rows.find((r) => r.kind === "table" && (r.c.same || []).includes(tid)), b = typeof xlBlock === "function" ? xlBlock(tid) : null;
    const c = from ? { ...from.c, key: `pick:${tid}`, table: tid, same: [tid], count: 1, name: "", review: null, doubts: [], keep: undefined, sameAs: null }
      : { key: `pick:${tid}`, table: tid, same: [tid], count: 1, rows: b ? b.nRows : 0, cols: b ? b.nCols : 0, bands: null, sample: "" };
    row = slRowNew("table", c, from ? from.name : styleCandName(c), { bands: from && from.bands ? { ...from.bands } : null, blueprint: false });
    const at = S.rows.findIndex((r) => r.kind === "table");
    S.rows.splice(at < 0 ? S.rows.length : at, 0, row); // 테이블 서식 후보의 맨 앞
  }
  if (blueprint && slSaveNative(S)) row.blueprint = true;
  return row;
}
// 그 대상들만 고른 채로(표 메뉴 「서식 관리자에 저장…」 · 카드 「이 표를 서식으로 저장」 · 에이전트 「서식 복사」 카드의 「서식 그림 보기」 — 제안의 대상: 표 id · 템플릿 id · 문단 · 쪽 설정 · 표지).
// picks = [{kind: "table", table, blueprint?} | {kind: "text", template} | {kind: "text", paras} | {kind: "page"} | {kind: "cover"}, + name?] — 제안의 이름은 사람이 아직 안 고친 줄에만 넣는다
function styleSavePick(S, picks) {
  for (const r of S.rows) r.on = false;
  let first = null;
  for (const k of picks || []) {
    let row = null;
    if (!k) continue;
    if (k.kind === "table" && k.table) row = slPickTable(S, k.table, !!k.blueprint);
    else if (k.kind === "page" || k.kind === "cover") row = S.rows.find((r) => r.kind === k.kind && r.state !== "done");
    else if (k.kind === "text" && k.template != null) row = S.rows.find((r) => r.kind === "text" && r.c.template && r.c.template.id === k.template && r.state !== "done");
    else if (k.kind === "text" && Array.isArray(k.paras) && k.paras.length) {
      const ids = new Set(k.paras);
      row = S.rows.find((r) => r.kind === "para" && r.state !== "done" && (r.c.paras || (r.c.items || []).map((it) => it.para)).some((p) => ids.has(p)));
      if (!row) { // 후보에 없는 문단 — 그 문단들로 줄을 하나 만든다(저장 끝점은 어느 문단이든 받는다)
        row = { kind: "paras", key: `pick:p:${k.paras[0]}`, c: {}, paras: [...k.paras], on: false, name: "문단 서식", state: "", err: "", undone: new Set(), script: { name: "문단 서식", bands: null, role: null } };
        S.rows = S.rows.filter((r) => r.key !== row.key);
        S.rows.push(row);
      }
    }
    if (!row) continue;
    row.on = true;
    if (k.name && !row.named) row.name = String(k.name).slice(0, 60);
    first = first || row;
  }
  S.focus = first ? first.key : null; // 그린 뒤 그 줄이 보이게 굴린다(styleSaveDraw)
}

async function styleSaveOpen(opts = {}) { // 「서식 복사」 보기 — 이 문서(hwpx·docx)의 후보 · opts.file = 파일에서 찾은 후보(문서 없이도) · opts.table(+blueprint) | opts.picks = 그 대상만 고른 채로. 문서가 바뀌면 후보를 다시 찾는다
  const file = opts.file || null;
  if (!file && !state.id) { toast("문서를 열어야 합니다 — 파일만 있으면 서식 관리자의 「파일에서 복사」"); return; }
  const key = file ? `file|${file.token}` : `doc|${state.id}|${state.epoch}`;
  headsDlg("styleSave", `서식 복사 — ${file ? file.name : state.name || "이 문서"}`, "서식 관리자에 저장할 서식을 고릅니다 · 문서는 안 바뀝니다");
  let S = STYLE.save;
  const fresh = !S || S.key !== key || !!S.err || (!file && !S.loading && !S.busy && !S.llm && !S.auto && S.rev !== state.serverRev); // 문서가 바뀌었으면 후보를 다시 찾는다
  if (fresh) {
    if (S && S.auto) S.auto.stop = true; // 다른 문서·파일의 「한 번에 진행」 은 멈춘다
    S = STYLE.save = slSaveNew(key, file);
    S.loading = !file;
    if (file) styleSaveFill(S, file);
  } else if (!S.busy && !S.auto && !(S.verify && !S.verify.done)) { // 같은 후보를 다시 연다 — 앞서 저장한 줄도 다시 고를 수 있게(「저장했습니다」·실패 까닭은 그 저장을 본 동안만 · 검증을 지켜보는 동안은 그대로)
    for (const r of S.rows) { r.state = ""; r.err = ""; }
    S.msg = "";
    S.verify = null;
    S.saved = 0;
  }
  if (opts.table) S.want = { picks: [{ kind: "table", table: opts.table, blueprint: !!opts.blueprint }] };
  else if (Array.isArray(opts.picks) && opts.picks.length) S.want = { picks: opts.picks };
  if (fresh && !file) {
    styleSaveDraw();
    try {
      await flushAll(); // 타자 중인 글을 서버에 먼저 — 서버 문서로 후보를 찾는다
      const r = await api(styleCandUrl(), { method: "POST", headers: H_JSON, body: JSON.stringify({ llm: false }) });
      if (STYLE.save !== S) return;
      styleSaveFill(S, r);
    } catch (e) { if (STYLE.save !== S) return; S.loading = false; S.err = styleErr(e); }
  }
  if (!S.loading && !S.err) {
    styleSaveParas(S);
    if (S.want) { styleSavePick(S, S.want.picks); S.want = null; }
  }
  if (styleSaveOn() && STYLE.save === S) styleSaveDraw(); // 읽는 동안 이 열을 다시 열었어도(차례 번호가 바뀜) 같은 후보면 그린다
}

// 「서식 복사」 열의 탭(spec_서식복사 ② §18 — 사용자 2026-11-14 "표지/내용서식/테이블/쪽 을 여기 탭에서 따로 따로 볼 수 있게") — 후보를 갈래마다 따로: 한 번에 한 탭의 줄만 그린다(DOM 에도 그 탭의 줄만).
// 고름·이름·띠 수·역할은 S.rows 에 있어 탭을 바꿔도 남고, 「LLM 검토」·「한 번에 진행」·저장·검증은 모든 탭의 후보에 걸친다(그 함수들은 S.rows 만 본다 — DOM 의 줄을 찾지 않는다)
const slCtabOf = (row) => (row.kind === "text" ? "content" : row.kind === "paras" ? "para" : row.kind); // 후보 줄 → 탭(cover · content = 레벨 있는 글 · table · page · para = 문단 묶음과 고른 문단)
const slCtabFirst = (S) => ["content", "cover", "table", "page", "para"].find((k) => S.rows.some((r) => slCtabOf(r) === k)) || "content"; // 처음 탭 — 내용 서식(후보가 있을 때) → 표지 → 테이블 → 쪽 설정 → 문단
function slCtabText(S, k, name, what) { // 탭 글 「<이름> <후보 수>( · <n>개 고름)」 + 도움말(뜻 · 후보 N · 고름 n · LLM 검토 뒤면 확인이 필요한 것 n = 의심·LLM 고침이 있는 후보)
  const rows = S.rows.filter((r) => slCtabOf(r) === k), on = rows.filter((r) => r.on && r.state !== "done").length;
  const need = S.named ? rows.filter((r) => r.state !== "done" && (slRowDoubts(r).length || slRowFixed(r).length)).length : null;
  return { text: `${name} ${nf(rows.length)}${on ? ` · ${nf(on)}개 고름` : ""}`, title: `${name} — ${what}\n후보 ${nf(rows.length)} · 고름 ${nf(on)}${need == null ? "" : ` · 확인이 필요한 것 ${nf(need)}`}` };
}
function slCtabGo(S, k) { // 탭을 누름 — 그 탭의 후보만 다시 그리고 본문은 맨 위로(탭마다 스크롤 자리를 기억하지 않는다)
  if (STYLE.save !== S || !styleSaveOn()) return;
  S.tab = k;
  styleSaveDraw();
  const body = $("headsDlgBody"), b = body.querySelector(`[data-sl-ctab="${k}"]`);
  body.scrollTop = 0;
  if (b) b.focus({ preventScroll: true }); // 다시 그려 단추가 새것 — 글쇠로 탭을 옮기던 자리를 잇는다
}

function styleSaveDraw() {
  if (!styleSaveOn()) return;
  const S = STYLE.save, tools = $("headsDlgTools"), body = $("headsDlgBody"), foot = $("headsDlgFoot"), keep = body.scrollTop;
  const title = $("headsDlgTitle"), fileName = title.querySelector(".sl-title-file")?.textContent || title.textContent.replace(/^서식 복사 — /, "");
  const fileLabel = el("span", "sl-title-file", fileName);
  fileLabel.title = fileName;
  title.replaceChildren(el("span", "sl-title-main", "서식 복사"), el("span", "sl-title-sep", " — "), fileLabel);
  $("headsDlgHelp").replaceChildren(hHelp("서식 복사 안내", $("headsDlgNote").textContent));
  tools.textContent = "";
  body.textContent = "";
  foot.textContent = "";
  const wrap = el("div", "sl-wrap");
  body.append(wrap);
  const back = hBtn("‹ 서식 관리자", () => styleLibOpen(), { title: "보관한 서식 목록으로(고른 것·이름은 이 문서를 닫기 전까지 남습니다)" });
  back.dataset.slAct = "toLibTop";
  tools.append(back);
  if (!S) return;
  const steps = styleStepsEl(S), autoBtn = steps.querySelector('[data-sl-act="auto"]');
  wrap.append(steps);
  tools.append(autoBtn); // 동작은 도구 줄에, 네 단계는 같은 폭으로 나란히(찾는 중·못 찾음에서도 보인다)
  if (S.loading) return; // 찾는 중 — 단계 줄 ① 의 동그라미가 말한다
  if (S.err) {
    wrap.append(el("p", "hwarn fail", `후보를 찾지 못했습니다: ${S.err}`), el("div", "sl-acts"));
    wrap.lastChild.append(S.file ? hBtn("다른 파일 고르기", () => styleFilePick()) : hBtn("다시 찾기", () => styleSaveOpen()));
    return;
  }
  const busy = !!S.busy || !!S.llm || !!S.auto;
  // 탭 다섯(② §18) — 단계 줄 바로 아래. 한 번에 한 탭의 후보만 그린다(아래 「그 탭의 후보」) · 글(수 · 고른 수)과 도움말은 sync 가 채운다
  if (S.focus) { const fr = S.rows.find((r) => r.key === S.focus); if (fr) S.tab = slCtabOf(fr); } // 고른 채로 연 후보 — 그 탭으로(그 줄이 DOM 에 있어야 굴릴 수 있다)
  if (!SL_CTAB[S.tab]) S.tab = slCtabFirst(S);
  const ctabs = el("div", "sl-ctabs"), ctabBtn = {};
  ctabs.setAttribute("role", "group");
  ctabs.setAttribute("aria-label", "서식 후보의 갈래");
  for (const [k, name] of SL_CTABS) {
    const b = hBtn(name, () => slCtabGo(S, k), { cls: "btn sm" + (S.tab === k ? " on" : "") });
    b.dataset.slCtab = k;
    b.setAttribute("aria-pressed", String(S.tab === k));
    ctabBtn[k] = b;
    ctabs.append(b);
  }
  wrap.append(ctabs);
  const nameBtn = hBtn("LLM 검토", () => styleSaveName(), { disabled: busy || !S.rows.some((r) => r.kind !== "paras" && r.state !== "done"),
    title: "스크립트가 찾은 후보를 LLM 이 검토합니다(유료 — 수 초~수십 초): 설명(구조·겉모습 — 이름 칸 아래 한 줄) · 저장할 만한지(「추천」) · 띠 수 · 역할 · 의심스러운 데. 서식 값과 이름은 LLM 이 짓지 않습니다(값은 모두 스크립트가 문서에서 읽은 것 · 이름은 「<문서 이름>: <갈래><번호>」). 문서는 안 바뀌고, 직접 고친 이름·띠 수·역할은 그대로 둡니다" }); // 전의 「에이전트 추출」(② §15 · 설명 = ② §19-2)
  nameBtn.dataset.slAct = "name";
  tools.insertBefore(nameBtn, autoBtn);
  if (S.call && !S.llm) tools.append(el("span", "muted sl-call", [S.call.model || "", S.call.ms != null ? `${(S.call.ms / 1000).toFixed(1)}초` : "", S.call.costUsd != null ? `$${Number(S.call.costUsd).toFixed(3)}` : ""].filter(Boolean).join(" · ")));
  const save = hBtn("", () => styleSaveRun(), { title: "고른 서식을 차례로 보관함에 저장합니다(hwpx·docx 두 형식) — 저장하면 PDF 검증이 뒤에서 시작됩니다" }), count = el("span", "muted sl-selection-count");
  save.dataset.slAct = "save";
  const sync = () => {
    const n = S.rows.filter((r) => r.on && r.state !== "done").length, auto = autoBtn;
    save.textContent = `고른 ${nf(n)}개 저장`;
    save.disabled = !n || busy;
    save.className = "btn sm" + (n ? " primary" : ""); // 강조 단추는 다음 할 일 하나(design.md §11) — 고른 것이 있으면 「저장」, 없으면 「한 번에 진행」
    if (auto && !S.auto) auto.className = "btn sm" + (!n && !S.saved ? " primary" : "");
    count.textContent = `전체 ${nf(S.rows.filter((r) => r.state !== "done").length)}개 중 ${nf(n)}개 선택`;
    for (const [k, name, what] of SL_CTABS) {
      const t = slCtabText(S, k, name, what), [main, picked] = t.text.split(" · ");
      const stats = el("span", "sl-ctab-stats", main.slice(name.length));
      if (picked) stats.append(el("span", "sl-ctab-picked", ` · ${picked}`));
      ctabBtn[k].replaceChildren(el("span", "sl-ctab-main", name), stats);
      ctabBtn[k].title = t.title;
    } // 수는 늘 둘째 줄 — 고르거나 풀어도 탭 높이와 후보 위치가 바뀌지 않는다
  };
  // 옵션 — 자료값(글)을 그대로 둘지. 파일·docx 문서의 후보는 서버가 명세로 다시 짓는다(이 옵션 없음)
  if (!slSaveNative(S)) { if (S.format === "docx" && !S.file) wrap.append(el("p", "sl-msg", "docx 문서의 서식은 요약 명세로 다시 지어 저장합니다(원본과 조금 다를 수 있습니다) — 「글도 그대로 저장」·「구조까지 저장」 은 hwpx 문서에서만 됩니다.")); }
  if (slSaveNative(S)) {
    const opts = el("div", "sl-opts"), lab = el("label", "sl-opt"), cb = el("input");
    cb.type = "checkbox"; cb.checked = S.keepText; cb.disabled = busy;
    cb.onchange = () => { S.keepText = cb.checked; styleSaveDraw(); }; // 저장 몸이 바뀐다 — 서식 견본도 다시 받는다(② §13)
    lab.append(cb, el("span", null, "글도 그대로 저장"));
    lab.dataset.slOpt = "keepText";
    opts.append(lab, hHelp("글도 그대로 저장 안내", SL_KEEP_HELP));
    wrap.append(opts);
  } else if (S.losses.length) wrap.append(el("p", "sl-msg", `이 ${S.file ? "파일" : "문서"}에서 옮기지 못하는 것 — ${S.losses.join(" · ")}`));
  if (S.msg) wrap.append(el("p", "sl-msg" + (S.msgErr ? " err" : ""), S.msg));
  const vEl = styleSaveVerifyEl(S); // 저장 뒤 검증 진행 줄 → 요약 + 「서식 관리자에서 보기」
  if (vEl) wrap.append(vEl);
  if (!S.rows.length) {
    wrap.append(el("p", "hnote", S.file ? "이 파일에서 서식 후보를 찾지 못했습니다." : "이 문서에서 서식 후보를 찾지 못했습니다 — 표가 없거나(1칸 표·「작성 요령」 표는 뺍니다), 내용 서식 후보는 헤딩 2단계(개요템플릿) 결과가 있어야 나옵니다."));
  }
  // 그 탭의 후보(② §18): 갈래 이름·설명 도움말·저장 옵션([data-sl-sec]) → 왜 없는지(0개일 때) → 그 탭의 줄만. 다른 탭의 줄은 DOM 에 없다(자료는 S.rows)
  const mine = S.rows.filter((r) => slCtabOf(r) === S.tab), secNote = el("div", "sl-sec-note"), description = (SL_CTABS.find(([k]) => k === S.tab) || [])[2] || "";
  secNote.dataset.slSec = S.tab;
  secNote.append(el("strong", null, SL_CTAB[S.tab]), hHelp(`${SL_CTAB[S.tab]} 안내`, description));
  const opts = wrap.querySelector(".sl-opts");
  if (opts) secNote.append(opts);
  wrap.append(secNote);
  if (S.tab === "content" && slSaveNative(S) && !S.stage2) wrap.append(el("p", "hnote", "헤딩 2단계(개요템플릿) 결과가 없어 레벨이 있는 내용 서식 후보는 없습니다 — 문단을 끌어 고르고(또는 커서를 두고) 이 열을 다시 열면 「문단 서식」 으로 저장할 수 있습니다."));
  else if (!mine.length && S.rows.length) wrap.append(el("p", "hnote", `이 ${S.file ? "파일" : "문서"}에서 ${SL_CTAB[S.tab]} 후보를 찾지 못했습니다.`)); // 후보가 하나도 없으면 위의 한 줄이 말한다(같은 글을 두 번 두지 않는다)
  for (const row of mine) wrap.append(styleCandEl(S, row, sync));
  foot.append(save, count);
  if (S.busy) foot.append(slRun(`저장 중 ${nf(S.busy.i)}/${nf(S.busy.n)} — ${short(S.busy.name || "", 24)}`));
  sync();
  body.scrollTop = keep;
  if (S.focus) { // 고른 채로 연 줄(표 메뉴 · 에이전트 카드의 「서식 그림 보기」)이 보이게
    const e = body.querySelector(`.sl-cand[data-cand="${CSS.escape(S.focus)}"]`);
    S.focus = null;
    if (e) e.scrollIntoView({ block: "nearest" });
  }
  slPicWatch(); // 보이는 줄의 서식 견본만 받는다
}

// 후보의 저장 몸(spec_서식복사 ② §16 — POST …/styles) — 서식 견본(POST …/styles/preview)도 **같은 몸**을 보낸다(pic = 견본용: 이름·「구조까지 저장」 은 그림과 무관해 뺀다).
// LLM 이 고른 값(템플릿의 rep · 쪽 설정의 bodyKey · 표지의 end·roles)은 사람이 되돌리지 않았을 때만 싣는다 · 문단 서식의 role 은 고른 값
function slParaIds(row) { const c = row.c || {}; return row.kind === "paras" ? row.paras : Array.isArray(c.paras) && c.paras.length ? c.paras : (c.items || []).map((it) => it.para).filter(Boolean).slice(0, 1); } // 문단 묶음 = 대표 문단 하나(옛 서버의 묶음은 그 paras 그대로)
function slSaveBody(S, row, pic = false) {
  const native = slSaveNative(S), opt = native ? { keepText: S.keepText } : {}, c = row.c || {}; // 「글도 그대로 저장」·「구조까지 저장」 은 hwpx 문서에서만(docx 문서 = 명세로 다시 지음 — ② §6)
  if (row.kind === "page") return { kind: "page", ...(c.bodyKey && slFixOn(row, "bodyKey") ? { bodyKey: c.bodyKey } : {}) };
  if (row.kind === "cover") return { kind: "cover", ...(c.end && c.review && slFixOn(row, "end") ? { end: c.end } : {}), ...(c.roles && c.review && slFixOn(row, "roles") ? { roles: c.roles } : {}), ...opt };
  if (row.kind === "table") return { kind: "table", table: c.table, ...(row.bands ? { bands: row.bands } : {}), ...opt, ...(native && !pic ? { blueprint: !!row.blueprint } : {}) };
  if (row.kind === "text" && c.template && native) return { kind: "text", template: c.template.id, ...(c.rep && slFixOn(row, "rep") ? { rep: c.rep } : {}), ...opt };
  if (row.kind === "text") return { kind: "text", paras: c.paras || (c.items || []).map((it) => it.para).filter(Boolean), ...opt };
  return { kind: "text", paras: slParaIds(row), ...(row.role ? { role: row.role } : {}), ...opt };
}
function slFilePick(row) { // 파일 후보의 pick(POST /api/styles/from-file · preview-file) — {kind, key, bands?, role?, bodyKey?, end?, roles?}
  const c = row.c || {}, kind = row.kind === "para" ? "text" : row.kind;
  return { kind, key: row.kind === "page" ? "page" : row.key, ...(row.kind === "table" && row.bands ? { bands: row.bands } : {}), ...(row.kind === "para" && row.role ? { role: row.role } : {}),
    ...(row.kind === "page" && c.bodyKey && slFixOn(row, "bodyKey") ? { bodyKey: c.bodyKey } : {}), ...(row.kind === "cover" && c.end && c.review && slFixOn(row, "end") ? { end: c.end } : {}),
    ...(row.kind === "cover" && c.roles && c.review && slFixOn(row, "roles") ? { roles: c.roles } : {}) };
}
function slCandPic(S, row) { // 후보 줄의 그림 상자 — 「저장될 견본」(저장과 같은 몸으로 지은 운반 문서의 보기: 원문이 아니다 — 글은 라벨·견본으로 바뀌고 폭이 맞춰진 그 모습)
  const wrap = el("div", "sl-picbox"), c = row.c || {}, kind = row.kind === "text" ? "content" : row.kind === "paras" ? "para" : row.kind, n = kind === "table" ? c.rows : (c.items || []).length;
  const bigKey = `cand|${S.key}|${row.key}`, docId = state.id;
  let E;
  if (S.file) {
    const pick = slFilePick(row);
    E = slPicEntry(`file|${S.token}|${row.key}|${JSON.stringify(pick)}`, kind, n, () => api("/api/styles/preview-file", { method: "POST", headers: H_JSON, body: JSON.stringify({ token: S.token, pick }) }).then((r) => r.view || {}),
      kind === "table" ? { bands: row.bands || null } : {});
  } else {
    const body = slSaveBody(S, row, true);
    E = slPicEntry(`doc|${docId}|${S.rev}|${row.key}|${JSON.stringify(body)}`, kind, n, () => api(`/api/docs/${encodeURIComponent(docId)}/styles/preview`, { method: "POST", headers: H_JSON, body: JSON.stringify(body) }).then((r) => r.view || {}),
      kind === "table" ? { bands: row.bands || null } : kind === "para" ? { role: row.role || null } : {}, true);
  }
  wrap.append(slPicPaint(E, STYLE.big.has(bigKey)));
  wrap.append(slPicBar(["저장될 견본 · 웹 견본", "저장하면 보관함에 들어갈 서식의 견본입니다(원문 그대로가 아닙니다 — 글은 라벨·견본 글로 바뀌고 캡션·칸 안 표·그림은 빠집니다). 원문은 「자리로」 로 봅니다\n웹 견본 = 서식 값으로 브라우저가 그린 그림 — 글꼴·줄바꿈은 출력과 조금 다를 수 있습니다"],
    bigKey, styleSaveDraw));
  return wrap;
}

// 단계 줄(spec_서식복사 ② §1 「단계」·§2 — design.md §7·§11): ① 후보 찾기 › ② 에이전트 추출 › ③ 저장 › ④ PDF 검증. 끝난 것 = ✓ + 「완료」(낭독) · 지금 도는 것 = 동그라미 + 하는 일 + 지난 시간 ·
// 다음 할 일 = aria-current="step". 번호는 끝나도 남는다. 줄 끝에 「한 번에 진행」(②③④ 를 차례로 — 도는 동안은 「멈춤」)
function slStepState(S) { // → {find, name, save, verify: "done"|"run"|"todo"}
  const V = S.verify;
  return { find: S.loading ? "run" : S.err ? "todo" : "done", name: S.llm ? "run" : S.named ? "done" : "todo", save: S.busy ? "run" : S.saved ? "done" : "todo", verify: V ? (V.done && !V.late ? "done" : V.done ? "todo" : "run") : "todo" };
}
function slStepRunText(S) { // 지금 도는 단계의 글(1초마다 이 글만 바꾼다)
  if (S.loading) return `${S.file ? `「${short(S.name || "", 20)}」 에서` : "이 문서에서"} 서식 후보를 찾는 중 · ${slSecs(S.file && STYLE.file ? STYLE.file.t0 : S.t0 || performance.now())}`;
  if (S.llm) return `LLM 이 후보를 검토하는 중(설명 · 추천 · 띠 수 · 역할 · 의심) · ${slSecs(S.llm.t0)}`;
  if (S.busy) return `저장 중 ${nf(S.busy.i)}/${nf(S.busy.n)}`;
  const V = S.verify;
  if (V && !V.done) return `PDF 검증 중 — ${nf(V.items.filter(slWatchSettled).length)}/${nf(V.items.length)} 끝남 · ${slSecs(V.t0)}`;
  return "";
}
function styleStepsEl(S) {
  const box = el("div", "sl-steps-row"), ol = el("ol", "sl-steps"), st = slStepState(S), next = SL_STEPS.map(([k]) => k).find((k) => st[k] !== "done");
  ol.setAttribute("aria-label", "서식 복사의 단계");
  SL_STEPS.forEach(([k, name, what], i) => {
    const li = el("li", "sl-step"), s = st[k];
    li.dataset.step = k;
    li.dataset.state = s;
    li.title = `${i + 1}단계 ${name} — ${what}`;
    if (k === next) li.setAttribute("aria-current", "step");
    li.append(el("span", "sl-step-no", `${s === "done" ? "✓" : ""}${"①②③④"[i]}`), el("span", "sl-step-name", name)); // 번호는 끝나도 남는다(design.md §11) — 끝난 것은 ✓ 를 앞에
    if (s === "done") { const sr = el("span", "sr-only", " 완료"); li.append(sr); }
    ol.append(li);
  });
  box.append(ol);
  const run = S.auto ? hBtn("멈춤", () => { S.auto.stop = true; S.msg = "「한 번에 진행」 을 멈춥니다 — 지금 하는 단계가 끝나면 멈춥니다."; S.msgErr = false; styleSaveDraw(); }, { title: "지금 하는 단계가 끝나면 멈춥니다(이미 저장한 서식은 그대로)" })
    : hBtn("한 번에 진행", () => styleSaveAuto(), { disabled: !!S.loading || !!S.err || !!S.busy || !!S.llm || !S.rows.some((r) => r.state !== "done"),
      title: "② LLM 검토(한 번 — 유료) → ③ 추천이면서 「확인」·「LLM 고침」·띠 넓히기 제안이 없는 후보(+ 이미 고른 것)만 저장 → ④ PDF 검증을 기다립니다(180초까지).\n확인이 필요한 후보는 저장하지 않고 남깁니다 — 보고 골라 저장하세요. 문서는 안 바뀌고, 직접 고친 이름·띠 수·역할은 그대로 둡니다 · LLM 을 쓸 수 없으면 ② 에서 멈춥니다" });
  run.dataset.slAct = "auto";
  box.append(run);
  const txt = S.loading || S.llm || S.busy ? slStepRunText(S) : ""; // ④ 검증은 아래 검증 진행 줄(.sl-vbox)이 말한다 — 같은 글을 두 곳에 두지 않는다(design.md §10)
  if (txt) { const r = slRun(txt); r.classList.add("sl-step-run"); box.append(r); } // 지금 하는 일 + 지난 시간(한 줄 — 단계 줄 아래)
  return box;
}

// 저장 뒤 검증(④) 지켜보기 — 서식마다 GET /api/styles/{sid} 를 2초마다(두 형식이 다 끝나거나 180초). 열을 닫았다 열어도 S.verify 가 남아 이어서 보인다
function slWatchItem(m) { // 서식 하나의 검증 상태(형식마다) — dual = 서버가 docx 형식을 안다
  return { id: m.id, name: m.name || m.id, kind: m.kind || "", tab: slTabOf(m), verify: m.verify || null, verifyDocx: m.verifyDocx || null, docx: "docx" in m ? !!m.docx : null, dual: "verifyDocx" in m || "docx" in m, gone: false };
}
const slFmtSettled = (v) => !!v && !!v.status && v.status !== "running";
function slWatchSettled(it) { // 두 형식 다 끝났나 — hwpx 가 먼저 돌고 docx 가 뒤따른다(docx 서식이 있는데 기록이 아직 없으면 기다린다)
  if (it.gone) return true;
  if (!slFmtSettled(it.verify)) return false;
  if (!it.dual || it.docx === false || (it.docx == null && !it.verifyDocx)) return true; // docx 형식을 모르는 서버 · docx 서식 없음
  return slFmtSettled(it.verifyDocx);
}
function slWatchSum(V) { // 형식마다 「검증됨 n · 확인 필요 n · 실패 n · 없음 n」 — 없음 = PDF 출력 없음 · docx 서식 없음 · 아직 안 끝남
  const out = [];
  for (const [fmt, key] of SL_FORMATS) {
    const its = V.items.filter((it) => !it.gone && (fmt === "hwpx" || it.dual));
    if (!its.length) continue;
    const n = { ok: 0, warn: 0, fail: 0, none: 0, run: 0 };
    for (const it of its) { const v = it[key], st = fmt === "docx" && it.docx === false ? "none" : v && v.status === "running" ? "run" : (v && v.status) || "run"; n[st in n ? st : "none"] += 1; }
    out.push(`${fmt} — ${[`검증됨 ${nf(n.ok)}`, `확인 필요 ${nf(n.warn)}`, `실패 ${nf(n.fail)}`, `없음 ${nf(n.none)}`, n.run ? `아직 도는 중 ${nf(n.run)}` : ""].filter(Boolean).join(" · ")}`);
  }
  return out;
}
function styleSaveVerifyEl(S) {
  const V = S.verify;
  if (!V || !V.items.length) return null;
  const box = el("div", "sl-vbox");
  box.dataset.state = V.done ? (V.late ? "late" : "done") : "run";
  if (!V.done) { const r = slRun(slStepRunText(S)); r.classList.add("sl-vrun"); box.append(r); }
  else {
    box.append(el("p", "sl-vsum" + (V.late ? " late" : ""), V.late ? "검증이 아직 돕니다 — 서식 관리자에서 확인" : `PDF 검증 끝 — 서식 ${nf(V.items.length)}개`));
    for (const t of slWatchSum(V)) { const p = el("p", "sl-vsum"); p.dataset.format = t.split(" ")[0]; p.textContent = t; box.append(p); }
  }
  const go = hBtn("서식 관리자에서 보기", () => styleLibOpen((V.items[0] || {}).tab || (V.items[0] || {}).kind || null), { title: "방금 저장한 서식을 서식 관리자에서 봅니다(그 갈래로) — 서식 그림 · 검증 내역 · 문서에 쓰기" });
  go.dataset.slAct = "toLib";
  box.append(go);
  return box;
}
async function styleSaveWatch(S, made) { // made = 방금 저장한 서식(meta) — 앞서 지켜보던 것에 더한다. 끝나면(또는 180초) 요약
  const V = S.verify || (S.verify = { items: [], t0: 0, done: false, late: false, run: 0 });
  for (const m of made) if (m && m.id && !V.items.some((x) => x.id === m.id)) V.items.push(slWatchItem(m));
  Object.assign(V, { t0: performance.now(), done: false, late: false });
  const run = (V.run += 1), mine = () => STYLE.save === S && V.run === run, sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const tick = setInterval(() => { if (!mine() || V.done || !styleSaveOn()) return; for (const t of $("headsDlgBody").querySelectorAll(".sl-vrun .sl-run-text, .sl-step-run .sl-run-text")) t.textContent = slStepRunText(S); }, 1000);
  if (styleSaveOn() && STYLE.save === S) styleSaveDraw();
  try {
    while (mine()) {
      if (V.items.every(slWatchSettled)) { V.done = true; break; }
      if (performance.now() - V.t0 > SL_VERIFY_LIMIT) { V.done = true; V.late = true; break; } // 한도 — 「검증이 아직 돕니다 — 서식 관리자에서 확인」
      await sleep(2000);
      if (!mine()) return;
      let changed = false;
      for (const it of V.items.filter((x) => !slWatchSettled(x))) {
        try { const was = JSON.stringify([it.verify && it.verify.status, it.verifyDocx && it.verifyDocx.status]), now = slWatchItem(await api(styleUrl(it.id))); Object.assign(it, { verify: now.verify, verifyDocx: now.verifyDocx, docx: now.docx, dual: now.dual });
          if (JSON.stringify([it.verify && it.verify.status, it.verifyDocx && it.verifyDocx.status]) !== was) changed = true; }
        catch (e) { if (e.status === 404 && e.message !== "Not Found") { it.gone = true; changed = true; } } // 그 사이 지워짐 · 그 밖의 오류는 다음 차례에 다시
      }
      if (changed && mine() && styleSaveOn()) styleSaveDraw();
    }
  } finally { clearInterval(tick); }
  if (mine() && styleSaveOn()) styleSaveDraw();
}

function styleCandEl(S, row, sync) {
  const done = row.state === "done", busy = !!S.busy || !!S.llm || !!S.auto, c = row.c || {};
  const box = el("div", "sl-cand" + (done ? " done" : "")), line = el("div", "sl-crow"), cb = el("input"), name = el("input", "sl-cname"), meta = el("div", "sl-cmeta");
  box.dataset.cand = row.key;
  box.dataset.kind = row.kind;
  cb.type = "checkbox"; cb.checked = row.on && !done; cb.disabled = done || busy;
  cb.setAttribute("aria-label", `${row.name || "서식"} — 저장할 것으로 고르기`);
  cb.onchange = () => { row.on = cb.checked; sync(); };
  name.type = "text"; name.maxLength = 60; name.value = row.name; name.placeholder = "서식 이름"; name.disabled = done || busy;
  name.setAttribute("aria-label", "서식 이름");
  name.oninput = () => { row.name = name.value; row.named = true; };
  line.append(cb, name);
  const goId = row.kind === "page" ? null : row.kind === "table" ? c.table : row.kind === "cover" ? (c.blocks || [])[0] : row.kind === "paras" ? (row.paras || [])[0] : ((c.items || [])[0] || {}).para || (c.paras || [])[0];
  if (!S.file && goId) line.append(hBtn("자리로", () => slGo(goId), { title: "문서에서 그 자리로(열은 그대로) — 원문은 여기서 봅니다(그림은 저장될 견본)" }));
  let pic = slCandPic(S, row); // 그림이 먼저(체크·이름 줄 바로 아래 — ② §13). 띠 수·역할을 바꾸면 저장 몸이 달라져 견본을 다시 받는다
  const repic = () => { const now = slCandPic(S, row); pic.replaceWith(now); pic = now; slFoldBar(fold, pic); slPicWatch(); };
  const keepTag = () => { if (!slRowKeep(row)) return; const llm = !!c.keep, k = el("span", llm ? "hb het" : "hb", "추천"); k.title = llm ? "LLM 이 저장할 만하다고 본 후보" : "문서에 하나뿐인 쪽 설정 — 규칙으로 추천(LLM 이 본 것이 아닙니다)"; meta.append(k); }; // 보라는 LLM 이 한 것에만(design.md §6)
  if (row.kind === "table") {
    if (c.rows) meta.append(el("span", null, `${c.rows}×${c.cols}`));
    for (const [k, label, title] of SL_BANDS) { // 띠 수 — 구역마다 그 서식을 따로 저장한다(비워 두면 서버가 판정)
      const l = el("label", "sl-num", label), i = el("input");
      i.type = "number"; i.min = "0"; i.max = String(Math.max(0, (k === "headerCols" ? c.cols : c.rows) || 99)); i.value = row.bands ? String(row.bands[k] || 0) : ""; i.placeholder = "–"; i.disabled = done || busy;
      i.title = `${title}${row.bands ? "" : " — 비워 두면 자동 판정"}`;
      i.dataset.band = k;
      i.onchange = () => {
        const v = Math.max(0, Math.min(Number(i.max), parseInt(i.value, 10) || 0));
        row.bands = { headerRows: 0, headerCols: 0, footRows: 0, ...(row.bands || {}), [k]: v };
        row.banded = true;
        for (const x of meta.querySelectorAll("input[data-band]")) x.value = String(row.bands[x.dataset.band] || 0);
        repic(); // 띠 수가 바뀌면 서식 견본도 다시(그림의 띠 표시 · 라벨로 남는 칸)
      };
      l.append(i);
      meta.append(l);
    }
    if ((c.count || 1) > 1) { // 전의 「같은 서식 n개」 — 서식 지문에는 행·열 수·합친 칸·열 폭이 들지 않는다(② §13)
      const n = el("span", null, `비슷한 서식 ${nf(c.count)}개`);
      n.title = `띠 수와 구역 대표 칸의 모양이 같은 표 — 그림은 대표 표 하나의 것\n${(c.same || []).slice(0, 12).join(" · ")}${(c.same || []).length > 12 ? " …" : ""}`;
      meta.append(n);
    }
    if (c.page) meta.append(el("span", null, `${c.page}쪽`));
    if (SL_TROLE[c.role]) { const t = el("span", "hb", SL_TROLE[c.role]); t.title = "LLM 이 본 이 표의 역할"; t.dataset.role = c.role; meta.append(t); }
    keepTag();
    if (row.bandsWider && !done) { // LLM 이 띠를 더 넓게 본 것 — 사람이 눌러야 들어간다(보라 = LLM 제안: design.md §6). 머리 띠 안 칸의 글은 라벨로 저장되므로 저절로 넓히지 않는다
      const w = row.bandsWider, b = hBtn(`LLM 제안 — ${slBandsText(w)}`, () => { row.bands = { ...w }; row.banded = true; row.bandsWider = null; styleSaveDraw(); },
        { cls: "btn sm sl-wider", disabled: busy, title: "LLM 이 머리 띠를 더 넓게 보았습니다 — 저절로 넣지 않았습니다.\n머리 띠 안 칸의 글은 라벨로 보관함에 저장됩니다(띠가 잘못 넓어지면 자료값이 남습니다). 맞으면 눌러 적용하세요." });
      b.dataset.slAct = "wider";
      meta.append(b);
    }
    if (slSaveNative(S)) {
      const lab = el("label", "sl-opt"), bp = el("input");
      bp.type = "checkbox"; bp.checked = !!row.blueprint; bp.disabled = done || busy;
      bp.onchange = () => { row.blueprint = bp.checked; };
      lab.dataset.slOpt = "blueprint";
      lab.title = "머리 글·칸 구성까지 저장합니다 — 서식 관리자에서 「빈 표 넣기」 로 같은 구조의 빈 표를 다시 씁니다(채우는 칸·계산 칸은 비워서)";
      lab.append(bp, el("span", null, "구조까지 저장"));
      meta.append(lab);
    }
    if (c.sample && !/^pick:/.test(row.key)) { const s = el("span", "sl-sample", `「${oneLine(c.sample)}」`); s.title = "첫 칸 글"; meta.append(s); }
  } else if (row.kind === "text") {
    const t = c.template, items = c.items || [];
    if (t) meta.append(el("span", null, `템플릿 ${t.no != null ? `T${t.no}` : t.name || ""}`));
    meta.append(el("span", null, `레벨 ${nf(items.length)}`));
    const chain = (t && t.chain) || items.map((it) => it.letter).filter(Boolean);
    if (chain && chain.length) { const s = el("span", "sl-sample", (Array.isArray(chain) ? chain : [chain]).join(" › ")); s.title = "레벨마다의 레터"; meta.append(s); }
    keepTag();
  } else if (row.kind === "page") { // 쪽 설정 후보 — 요약 한 줄(문서에 하나). 추천·검토는 다른 후보와 같은 규칙(② §15 — LLM 이 안 본 옛 서버에서만 규칙으로 추천)
    const s = el("span", "sl-sample", c.sample || slPageText(c.page, c.body) || "쪽 설정");
    s.title = "쪽 설정(용지 크기 · 방향 · 여백)과 본문 바탕 글 모양";
    meta.append(s);
    keepTag();
    if (S.format === "pdf") meta.append(el("span", null, "근사 — 여백은 글이 놓인 자리로 어림"));
  } else if (row.kind === "cover") { // 표지 서식 후보 — 첫 쪽의 블록 묶음(② §14)
    const parts = c.parts || [];
    meta.append(el("span", null, `부분 ${nf(parts.length || (c.blocks || []).length)}`));
    if (c.sample) { const s = el("span", "sl-sample", oneLine(c.sample)); s.title = "표지의 부분들(가린 글)"; meta.append(s); }
    keepTag();
  } else if (row.kind === "para") { // 문단 서식 후보 — 역할 꼬리표 · 역할 고르기(② §12): 고르면 저장 몸의 role 이 되고 견본을 다시 받는다
    const lab = el("label", "sl-role", "역할"), sel = el("select"), f = ((c.items || [])[0] || {}).format || {};
    for (const [k, name] of [["", "모름"], ...SL_ROLES]) { const o = el("option", null, name); o.value = k; sel.append(o); }
    sel.value = row.role || "";
    sel.disabled = done || busy;
    sel.dataset.slRole = "";
    sel.setAttribute("aria-label", `${row.name || "문단 서식"} 의 역할`);
    sel.onchange = () => { row.role = sel.value || null; row.roled = true; const t = meta.querySelector(".hb[data-role]"); if (t) { t.textContent = SL_ROLE[row.role] || "역할 모름"; t.dataset.role = row.role || ""; } repic(); };
    lab.append(sel);
    const tag = el("span", "hb", SL_ROLE[row.role] || "역할 모름");
    tag.dataset.role = row.role || "";
    tag.title = "이 문단 서식의 역할 — 스크립트가 먼저 붙이고(LLM 은 애매한 것만), 옆에서 고칠 수 있습니다";
    meta.append(tag, lab);
    if (c.count) meta.append(el("span", null, `문단 ${nf(c.count)}개`));
    const lookText = [f.font || "", f.sizePt ? `${f.sizePt}pt` : ""].filter(Boolean).join(" ");
    if (lookText) meta.append(el("span", "sl-sample", lookText));
    keepTag();
  } else meta.append(el("span", null, `고른 문단 ${nf(row.paras.length)}개 — 레벨 없는 문단 서식(서식이 같은 문단은 하나로)`));
  const fold = slCandFold(row, pic, meta, styleReviewEl(S, row, busy || done));
  box.append(line);
  if (row.note) { // LLM 검토의 설명(② §19-2) — 이름 칸 아래 회색 한 줄(넘치면 말줄임 · 전문은 도움말). 저장하면 서식의 설명(meta.note)
    const nt = el("p", "sl-cnote", row.note);
    nt.dataset.by = "llm";
    nt.title = `LLM 이 붙인 설명 — 이름은 그대로 두고, 저장하면 서식의 설명으로 남깁니다\n${row.note}`;
    box.append(nt);
  }
  box.append(pic, fold);
  const st = el("p", "sl-cstate" + (row.err ? " err" : ""), row.err ? `저장하지 못했습니다: ${row.err}` : done ? (row.existing ? "이미 보관함에 있는 서식입니다 — 다시 저장하지 않았습니다" : "보관함에 저장했습니다") : ""); // existing = 같은 서식이 이미 있어 서버가 있던 것을 돌려줌(spec_서식복사 ② §4 「같은 서식은 한 번만」)
  box.append(st);
  if (!S.file && row.kind !== "page") { // 줄에 올리면 문서의 그 표·문단(비슷한 서식 표 모두 · 표지의 블록들)
    const ids = (row.kind === "table" ? c.same || [c.table] : row.kind === "cover" ? c.blocks || [] : row.kind === "paras" ? row.paras : c.paras || (c.items || []).map((it) => it.para)).filter(Boolean);
    box.addEventListener("mouseenter", () => slHit(ids.slice(0, 40)));
    box.addEventListener("mouseleave", () => slHit(null));
  }
  return box;
}

// 후보 줄의 그림 아래(견본 줄 · 서식 정보 · 검토 상태 · 확인) — **기본은 접는다**(2026-11-14 사용자 "이 부분은 기본적으로 접어줘" — spec_서식복사 ② §19-0).
// 접어도 요약 줄에 추천 · 확인 n(주황) · LLM 고침 n · LLM 제안(보라)을 남긴다(경고가 숨지 않게 — design.md §1-6). 편 것은 다시 그려도 편 채로(STYLE.cfold — 갈래|키)
function slCandFold(row, pic, meta, review) {
  const key = `${row.kind}|${row.key}`, d = el("details", "sl-cfold"), sum = el("summary", "sl-cfold-sum"), body = el("div", "sl-cfold-body");
  d.open = STYLE.cfold.has(key);
  d.addEventListener("toggle", () => { if (d.open) STYLE.cfold.add(key); else STYLE.cfold.delete(key); });
  const chip = (cls, text, title) => { const c = el("span", `sl-cf-n${cls ? ` ${cls}` : ""}`, text); if (title) c.title = title; sum.append(c); };
  sum.append(el("span", "sl-cf-t", "자세히"));
  const keep = [...meta.querySelectorAll(".hb")].find((x) => x.textContent === "추천");
  if (keep) chip(keep.classList.contains("het") ? "llm" : "", "추천", keep.title);
  const doubts = review.querySelectorAll(".sl-rv.doubt").length, fixes = review.querySelectorAll(".sl-rv.fix").length;
  if (doubts) chip("doubt", `확인 ${nf(doubts)}`, "펴서 무엇을 확인할지 봅니다 — 「한 번에 진행」 은 이 후보를 저절로 저장하지 않습니다");
  if (fixes) chip("llm", `LLM 고침 ${nf(fixes)}`, "LLM 이 스크립트 값 대신 고른 것 — 펴서 보고 되돌릴 수 있습니다");
  if (meta.querySelector("[data-sl-act=wider]")) chip("llm", "LLM 제안", "LLM 이 머리 띠를 더 넓게 보았습니다 — 펴서 눌러야 들어갑니다");
  body.append(meta, review);
  d.append(sum, body);
  slFoldBar(d, pic);
  return d;
}
function slFoldBar(d, pic) { // 그림 아래 한 줄(저장될 견본 · 웹 견본 · 「크게」)도 접는 곳 맨 위로 — 그림을 다시 받으면(repic) 새 줄로 바꾼다
  const bar = pic.querySelector(":scope > .sl-picbar"), body = d.querySelector(":scope > .sl-cfold-body"), old = body.querySelector(":scope > .sl-picbar");
  if (!bar) return;
  if (old) old.replaceWith(bar); else body.prepend(bar);
}

// 후보 줄의 검토 상태(② §15) — 체크 표시가 아니라 **글로**: 「스크립트 후보 — LLM 이 보지 않음」(회색) · 「LLM 이 봄 — 이름 · 띠 수 · 역할」 · 보라 「LLM 고침 — <무엇>: <전> → <뒤>」 + 「되돌리기」 ·
// 주황 「스크립트 확인 — …」·「LLM 확인 — …」 · 「<다른 후보> 과 같은 서식으로 보임」. 「LLM 이 봄」 은 「맞음」 이 아니다. 띠 넓히기 제안(bandsWider)은 줄의 「LLM 제안」 단추 그대로
function styleReviewEl(S, row, off) {
  const box = el("div", "sl-review"), c = row.c || {}, rv = c.review || null, add = (key, cls, text) => { const p = el("div", cls ? `sl-rv ${cls}` : "sl-rv"); p.dataset.rv = key; p.append(el("span", null, text)); box.append(p); return p; };
  if (row.kind === "paras" || /^pick:/.test(row.key)) return box; // 사람이 고른 대상(표 메뉴 · 고른 문단) — 후보 검토가 아니다
  if (rv && rv.by === "llm") add("by", "", `LLM 이 봄${Array.isArray(rv.seen) && rv.seen.length ? ` — ${rv.seen.join(" · ")}` : ""}`).title = "LLM 이 이 후보의 그 항목들을 보았다는 뜻입니다 — 「맞다」 는 뜻이 아닙니다(값은 스크립트가 문서에서 읽은 것)";
  else add("by", "", "스크립트 후보 — LLM 이 보지 않음").title = "스크립트가 문서에서 찾은 후보 그대로입니다 — 「LLM 검토」 를 누르면 설명 · 저장할 만한지 · 띠 수 · 역할 · 의심스러운 데를 봅니다";
  for (const f of slRowFixed(row)) {
    const p = add("fixed", "fix", `LLM 고침 — ${f.what || "값"}: ${slVal(f.from)} → ${slVal(f.to)}`);
    p.title = "LLM 이 스크립트 값 대신 고른 것입니다(보낸 후보 가운데서 고른 것 — 서식 값을 지은 것이 아닙니다). 저장하면 이 값으로 저장됩니다";
    if (f.key) { // 무엇을 되돌릴지 아는 고침만(대표 문단 · 바탕 글 · 범위 · 역할 · 띠 수 · 이름)
      const b = hBtn("되돌리기", () => { slUnfix(row, f); styleSaveDraw(); }, { disabled: off, title: "이 고침만 스크립트 값으로 되돌립니다 — 저장할 때 LLM 의 값을 보내지 않습니다" });
      b.dataset.slAct = "unfix";
      p.append(b);
    }
  }
  for (const i of [...(row.undone || [])].filter((k) => k[0] === "#")) { const f = ((rv && rv.fixed) || [])[Number(i.slice(1))]; if (f) add("undone", "", `되돌림 — ${f.what || "값"}: 스크립트 값(${slVal(f.from)})으로 저장합니다`); }
  for (const d of slRowDoubts(row)) add("doubt", "doubt", `${d.by === "llm" ? "LLM" : "스크립트"} 확인 — ${d.text}`).title = "저장하기 전에 그림과 「자리로」 로 확인하세요 — 「한 번에 진행」 은 이 후보를 저절로 저장하지 않습니다";
  if (c.sameAs) { const other = S.rows.find((r) => r !== row && r.key === c.sameAs); if (other) add("same", "", `「${other.name || other.key}」 과 같은 서식으로 보임`).title = "LLM 이 같은 서식으로 보았고 스크립트가 두 후보의 서식이 가까운 것을 확인했습니다 — 하나만 저장해도 됩니다"; }
  return box;
}

async function styleSaveName(auto = false) { // LLM 검토(② §15 — 누를 때만 · 전의 「에이전트 추출」·「이름 붙이기(LLM)」): 후보마다 설명(② §19-2 — 전의 이름: row.note) · 추천 · 띠 수 · 역할 · 의심 · LLM 이 고른 값. 직접 고친 이름·띠 수·역할은 안 덮는다. → 됐나
  const S = STYLE.save;                        // 문서 = POST …/styles/candidates {llm: true} · 파일 = POST /api/styles/name-file {token}(spec_서식복사 ② §8·§16). 표·내용·문단·쪽 설정·표지 후보를 모두 본다(옛 서버는 표·글만)
  if (!S || S.llm || S.busy || (S.auto && !auto)) return false;
  let ok = false;
  S.llm = { t0: performance.now() };
  S.msg = "";
  styleSaveDraw();
  const tick = setInterval(() => { const t = styleSaveOn() && STYLE.save === S && S.llm ? $("headsDlgBody").querySelector(".sl-step-run .sl-run-text") : null; if (t) t.textContent = slStepRunText(S); }, 1000);
  try {
    if (!S.file) await flushAll();
    const r = S.file ? await api("/api/styles/name-file", { method: "POST", headers: H_JSON, body: JSON.stringify({ token: S.token }) })
      : await api(styleCandUrl(), { method: "POST", headers: H_JSON, body: JSON.stringify({ llm: true }) });
    // 응답 = 후보에 검토 결과를 합친 것(② §16 — tables · texts · paras · pages · covers: 후보마다 name · keep · role · bands · bandsWider · rep · sameAs · bodyKey · end · roles · review · doubts). 옛 서버는 tables·texts 의 이름·keep·띠 수만
    const maps = { table: [r.tables], text: [r.texts], para: [r.paras, r.texts], page: [r.pages], cover: [r.covers] }, find = (row) => {
      for (const list of maps[row.kind] || []) { const c = (list || []).find((x) => (x.key || row.kind) === row.key); if (c) return c; }
      return null;
    };
    let n = 0;
    for (const row of S.rows) {
      const c = find(row);
      if (!c || row.state === "done") continue;
      if (!row.named && slDefName(c, "")) row.name = row.script.name = slDefName(c, ""); // 기본 이름은 서버 것(서식 지도에서 고쳤으면 그 이름) — 사람이 고친 이름은 그대로
      const note = slLlmNote(row, c); // LLM 의 이름은 이름을 덮지 않고 설명으로(② §19-2)
      if (note) { row.note = note; n += 1; }
      if (c.bands && row.kind === "table" && !row.banded) row.bands = slBands0(c.bands);
      row.bandsWider = row.kind === "table" && c.bandsWider && !row.banded ? slBands0(c.bandsWider) : null; // LLM 이 띠를 넓히자고 한 것 — 저절로 넣지 않는다(머리 띠 안 칸의 글은 라벨로 저장된다)
      if (row.kind === "para" && c.role && !row.roled) row.role = c.role;
      const got = {};
      for (const k of ["role", "rep", "sameAs", "bodyKey", "isCover", "end", "roles", "review", "doubts", "body", "parts", "sample"]) if (k in c) got[k] = c[k]; // LLM 이 고른 값(보낸 후보 가운데 고른 것)과 검토 상태 — 서식 값은 없다
      row.c = { ...row.c, ...got, keep: "keep" in c ? !!c.keep : row.c.keep };
      row.undone = new Set(); // 새 검토 — 앞서 되돌린 고침 표시는 걷는다
    }
    S.call = r.call || null;
    S.named = true;
    const left = S.rows.filter((x) => x.state !== "done"), need = left.filter((x) => slRowKeep(x) && !slRowClean(x)).length;
    S.msg = `LLM 검토 끝 — 설명 ${nf(n)}개 · 추천 ${nf(left.filter(slRowKeep).length)}개${need ? ` · 그 가운데 확인이 필요한 후보 ${nf(need)}개(줄마다 「확인」·「LLM 고침」 글)` : ""}. 「추천」 표가 붙은 후보가 저장할 만한 것입니다(고르는 것은 직접).${r.note ? ` ${r.note}` : ""}`;
    S.msgErr = false;
    ok = true;
  } catch (e) { // LLM 을 쓸 수 없음(503) — 「한 번에 진행」 은 여기서 멈춘다 · 올린 파일을 서버가 잊음(410)
    S.msg = e.status === 503 ? "에이전트(LLM)를 쓸 수 없습니다 — 후보를 직접 골라 저장하세요" : e.status === 410 ? "올린 파일을 서버가 놓았습니다 — 서식 관리자의 「파일에서 복사」 로 다시 올리세요."
      : `LLM 검토를 하지 못했습니다: ${styleErr(e)} — 후보를 직접 골라 저장할 수 있습니다`;
    S.msgErr = true;
  }
  clearInterval(tick);
  S.llm = null;
  if (STYLE.save === S) styleSaveDraw();
  return ok;
}

// 「한 번에 진행」(spec_서식복사 ② §15 — design.md §11): ② LLM 검토(한 번) → ③ 추천(keep)이면서 의심·LLM 고침·띠 넓히기 제안이 없는 후보(+ 사람이 이미 고른 것)만 저장 → ④ 검증을 기다림(서식마다 2초 간격 · 180초 한도).
// 나머지는 그대로 두고 끝 요약에 「확인이 필요한 후보 n개 — 보고 골라 저장하세요」. 표지·쪽 설정도 같은 규칙(전에는 문서 서식 후보를 늘 저장했다).
// LLM 을 쓸 수 없으면 ② 에서 멈춘다 · 사람이 고친 이름·띠 수는 덮지 않는다(styleSaveName) · 도는 동안 다른 문서로 가면 멈춘다 · 「멈춤」 은 지금 단계가 끝난 뒤. 문서는 안 바뀐다
async function styleSaveAuto() {
  const S = STYLE.save;
  if (!S || S.auto || S.busy || S.llm || S.loading || S.err) return;
  const A = (S.auto = { t0: performance.now(), stop: false }), epoch = state.epoch;
  const gone = () => STYLE.save !== S || epoch !== state.epoch; // 다른 문서·다른 후보로 갔다
  const end = (msg, err = false) => { S.auto = null; if (msg) { S.msg = msg; S.msgErr = err; } if (STYLE.save === S && styleSaveOn()) styleSaveDraw(); };
  const halted = () => { if (gone()) { S.auto = null; return true; } if (A.stop) { end("「한 번에 진행」 을 멈췄습니다 — 이어서 하려면 다시 누르거나 후보를 직접 골라 저장하세요."); return true; } return false; };
  styleSaveDraw();
  if (S.rows.some((r) => r.kind !== "paras" && r.state !== "done")) { // ② — 후보가 있으면 LLM 검토 한 번(표 · 내용 · 문단 · 쪽 설정 · 표지 모두: ② §15)
    const ok = await styleSaveName(true);
    if (gone()) { S.auto = null; return; }
    if (!ok) { end(); return; } // 까닭은 styleSaveName 이 적었다(「에이전트(LLM)를 쓸 수 없습니다 — 후보를 직접 골라 저장하세요」)
    if (halted()) return;
  }
  // ③ — 추천이면서 의심(doubts)·LLM 고침(fixed)·띠 넓히기 제안(bandsWider)이 없는 후보만 고른다(+ 사람이 이미 고른 것은 그대로). 표지·쪽 설정도 같은 규칙. 나머지는 고르지 않은 채 남긴다
  for (const r of S.rows) if (r.state !== "done" && slRowClean(r)) r.on = true;
  const need = S.rows.filter((r) => r.state !== "done" && !r.on && slRowKeep(r) && !slRowClean(r)).length, needText = need ? ` 확인이 필요한 후보 ${nf(need)}개 — 보고 골라 저장하세요.` : "";
  if (!S.rows.some((r) => r.on && r.state !== "done")) { end(need ? `저절로 저장한 서식은 없습니다.${needText}` : "추천된 후보가 없습니다 — 저장할 후보를 직접 골라 「고른 n개 저장」 을 누르세요."); return; }
  const res = await styleSaveRun(true); // ③
  if (gone()) { S.auto = null; return; }
  if (!res || !res.made) { end(S.msg || "저장하지 못했습니다 — 줄마다의 까닭을 보세요.", true); return; }
  if (halted()) return;
  if (S.verify && !S.verify.done) await S.verify.wait; // ④ — styleSaveRun 이 건 지켜보기가 끝날 때까지(180초 한도)
  if (gone()) { S.auto = null; return; }
  const V = S.verify || {};
  end((res.failed ? `서식 ${nf(res.made)}개를 저장했습니다 · ${nf(res.failed)}개는 저장하지 못했습니다(줄마다 까닭).` : V.late ? "저장은 끝났습니다 — 검증이 아직 돕니다(서식 관리자에서 확인)." : `한 번에 진행 끝 — 서식 ${nf(res.made)}개를 저장하고 검증했습니다.`) + needText, !!res.failed);
}

async function styleSaveRun(auto = false) { // 고른 것을 차례로 저장 — 줄마다 결과를 남기고, 저장한 서식의 PDF 검증을 지켜본다(이 열에 남는다 — 「서식 관리자에서 보기」 로 목록). → {made, failed} | null
  const S = STYLE.save;
  if (!S || S.busy || S.llm || (S.auto && !auto)) return null;
  const todo = S.rows.filter((r) => r.on && r.state !== "done");
  if (!todo.length) return null;
  const docId = state.id, epoch = state.epoch, named = (row) => { // 이름 + LLM 검토의 설명(② §19-2 — meta.note). 견본 요청 몸(slSaveBody)에는 둘 다 없다
    const n = (row.name || "").trim().replace(/\s+/g, " ").slice(0, 60), note = oneLine(row.note || "");
    return { ...(n ? { name: n } : {}), ...(note ? { note } : {}) };
  };
  const made = [];
  let failed = 0;
  S.busy = { i: 0, n: todo.length, name: "" };
  S.msg = "";
  if (S.file) {
    S.busy.i = todo.length;
    S.busy.name = S.name;
    styleSaveDraw();
    try {
      const r = await api("/api/styles/from-file", { method: "POST", headers: H_JSON,
        body: JSON.stringify({ token: S.token, picks: todo.map((row) => { const { kind, key, ...rest } = slFilePick(row); return { kind, key, ...named(row), ...rest }; }) }) }); // 쪽 설정 = {kind: "page", key: "page", name} · 표 = {kind, key, name, bands}
      made.push(...(r.styles || []));
      todo.forEach((row, i) => { row.state = "done"; row.on = false; row.err = ""; row.existing = !!((r.styles || [])[i] || {}).existing; }); // 응답의 차례 = picks 의 차례
    } catch (e) {
      failed = todo.length;
      S.msg = e.status === 410 ? "올린 파일을 서버가 놓았습니다 — 서식 관리자의 「파일에서 복사」 로 다시 올리세요(이미 본 그림과 고른 것은 그대로 둡니다)." : `저장하지 못했습니다: ${styleErr(e)}`;
      S.msgErr = true;
    }
  } else {
    for (const row of todo) {
      if (epoch !== state.epoch) break; // 그 사이 다른 문서 — 멈춘다
      S.busy.i += 1;
      S.busy.name = row.name;
      styleSaveDraw();
      const body = slSaveBody(S, row); // 서식 견본을 받을 때 보낸 것과 같은 몸(+ 이름 · 구조까지) — 그림으로 본 것이 저장된다
      try {
        made.push(await api(`/api/docs/${encodeURIComponent(docId)}/styles`, { method: "POST", headers: H_JSON, body: JSON.stringify({ ...body, ...named(row) }) }));
        row.state = "done"; row.on = false; row.err = ""; row.existing = !!made[made.length - 1].existing;
      } catch (e) { failed += 1; row.err = styleErr(e); }
    }
  }
  S.busy = null;
  S.saved += made.length;
  if (made.length) { STYLE.list = null; styleChanged(); } // 목록은 다음에 열 때 다시 읽는다
  const had = made.filter((m) => m.existing).length; // 이미 있던 같은 서식(다시 저장하지 않음)
  if (made.length && !failed) toast(had === made.length ? `서식 ${nf(had)}개는 이미 보관함에 있습니다 — 다시 저장하지 않았습니다` : `서식 ${nf(made.length - had)}개를 보관함에 저장했습니다${had ? ` · ${nf(had)}개는 이미 있음` : ""} — PDF 검증이 뒤에서 돕니다`);
  else if (made.length) toast(`서식 ${nf(made.length)}개를 저장했습니다 · ${nf(failed)}개는 저장하지 못했습니다(줄마다 까닭)`, true);
  if (made.length && STYLE.save === S) { const wait = styleSaveWatch(S, made); S.verify.wait = wait; } // ④ 검증 진행 줄 → 요약 + 「서식 관리자에서 보기」(이 열에 남는다 — 그리는 것은 styleSaveWatch 가)
  else if (STYLE.save === S) styleSaveDraw();
  return { made: made.length, failed };
}

// ---- 도구 줄 「서식」 묶음(spec_서식복사 ② §3 — index.html #tbStyle): 아이콘 단추 셋을 잇는다. #tbStyleLib 의 눌림 = 2열이 서식 관리자(styleLib·styleSave)로 열려 있음 —
// headsDlg·headsColClose 에 고리를 더하지 않고 열 요소를 지켜본다(shortcuts.js 와 같은 방식). 묶음 아이콘을 사람이 누를 때 서식 관리자를 여는 것은 app.js bind
const styleColOn = () => { const c = $("headsDlg"); return !!c && !c.hidden && (c.dataset.kind === "styleLib" || c.dataset.kind === "styleSave"); };
function styleToolSync() { // 단추 눌림 · 「이 문서에서 복사」 켜짐(문서를 열었을 때 — hwpx·docx 모두)
  const lib = $("tbStyleLib"), copy = $("tbStyleCopy");
  if (lib) lib.setAttribute("aria-pressed", String(styleColOn()));
  if (copy) copy.disabled = !state.id;
}
function styleToolToggle() { // 「서식 관리자」 — 열려 있으면 닫고, 닫혀 있거나 접혀 있거나 다른 보기면 연다
  if (styleColOn() && !colFolded("heads")) headsColClose();
  else styleLibOpen();
}
(() => {
  const lib = $("tbStyleLib"), copy = $("tbStyleCopy"), file = $("tbStyleFile"), col = $("headsDlg");
  if (!lib || !col) return;
  lib.onclick = styleToolToggle;
  if (copy) copy.onclick = () => styleSaveOpen();
  if (file) file.onclick = () => styleFilePick();
  if (typeof MutationObserver === "function") {
    new MutationObserver(styleToolSync).observe(col, { attributes: true, attributeFilter: ["hidden", "data-kind"] });
    const empty = $("empty");
    if (empty) new MutationObserver(styleToolSync).observe(empty, { attributes: true, attributeFilter: ["hidden"] }); // 문서를 열고 닫을 때(#empty 의 hidden) — 「이 문서에서 복사」 켜짐
  }
  styleToolSync();
})();
