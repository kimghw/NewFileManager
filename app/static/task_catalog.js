// TASK 조합의 원본: 이름·차례·시작 문서·화면 종류를 함께 관리한다.
// job 키는 server.py TASK["job"] 및 저장된 work.task.job과의 계약이다.
// files = 이관의 문서 칸, gather = 취합본 한 개 + 기관 문서 여러 개.
// target = 목적 문서(내용을 받는 문서)의 첨부 파일 종류 — server works.TARGET_FILE 과 같게(tests/test_task_catalog.py). 그 TASK 의 다른 종류 문서는 원본(spec_작업 ② §10 「목적 문서 표시」).
// zones = 그 TASK 가 편집 구역에서 기본으로 켤 기준(org 기관 · stage 단계 · year 차년도 — 없으면 켠 것 없음). 사람이 정하면 TASK 묶음마다 서버에 따로 적힌다(TASK 옵션 — spec_구역 ② §1).
//   서버 app/task_options.py ZONES_DEFAULT 와 같게(tests/test_task_catalog.py) — 취합은 기관 구역이 전부터 기본으로 보였다.
// 새 TASK를 넣을 때 spec/spec_작업.md §16의 모듈·검사 범위도 확인한다.
const TASK_CATALOG = ({ // 얼리지 않는다 — 화면에서 조립한 TASK(taskCatalogCustom — 아래)가 뒤에 더해진다. 붙박이 줄은 손대지 않는다
  plan_fit: { name: "사업계획서 양식 표준화", act: "양식 표준화", doc: "plan", file: "plan", up: "사업계획서", desc: "프로젝트 구성을 읽어 양식의 절·표에 적용하고, 헤딩·표를 뽑아 서식을 맞춥니다." }, // 키는 그대로(spec_양식표준화 ② §0 — 2026-11-18 「양식 맞추기 대신」)
  plan_merge: { name: "사업계획서 취합", act: "취합", doc: "plan", file: "plan", up: "취합본", upMany: "문서 여러 개", quick: true, desc: "기관이 나눠 쓴 문서의 내용을 사업계획서 하나로 모읍니다.",
    hint: "간단 모드 — 취합본과 기관 문서를 위 목록에 한꺼번에 올리고 목적 문서(취합본)를 고른 뒤 「자동 진행」 을 켜고 이 카드를 누르면 끝까지 자동으로 넣습니다.\n세부 작업 모드 — 「자동 진행」 을 끄면 올리고 등록만 합니다(취합본 하나만이면 단계마다 보고 고르며 함 — 기관 문서는 연 뒤 작업 개요에서 넣음).",
    gather: { base: "plan", parts: "part" }, target: "plan", zones: ["org"] }, // quick = 카드에 여럿을 올리면 간단 모드(gather_quick.js — spec_취합 ② §8)
  plan_to_report: { name: "사업계획서 → 연차보고서 이관", act: "이관", doc: "plan-report", file: "", up: "문서", desc: "사업계획서에서 필요한 내용을 뽑아 연차보고서로 옮깁니다.",
    hint: "사업계획서나 연차보고서 가운데 하나 — 나머지 문서는 연 뒤 작업 개요의 첨부 파일 칸에서 올립니다", files: ["plan", "report"], target: "report" },
  report_fit: { name: "연차보고서 양식 맞추기", act: "양식 맞추기", doc: "report", file: "report", up: "연차보고서", desc: "단계·차년도·기관에 맞춰 양식의 절·표를 늘리고 줄입니다." },
  report_merge: { name: "연차보고서 취합", act: "취합", doc: "report", file: "report", up: "취합본", soon: true, desc: "기관이 나눠 쓴 문서의 내용을 연차보고서 하나로 모읍니다." },
  // 문서 일반 편집(spec_일반편집 ② §11) — kind = 작업 종류 「일반 문서」(다른 TASK 는 rnd) · entry = 처음 여는 패널 보기(에이전트 — 다른 TASK 는 작업 개요 Div). 어느 문서든(doc "any" — 로고 바탕 옅은 회색)
  doc_edit: { name: "문서 일반 편집", act: "일반 편집", doc: "any", file: "", up: "문서", kind: "general", entry: "Agent", desc: "에이전트에 요청해 글·표를 쓰고, 표·글 서식을 보관함에 저장해 다시 씁니다.",
    hint: "hwp·hwpx 문서 하나 — 오른쪽 에이전트에 자료를 주고 요청하면 제안을 냅니다(「문서에 반영」 을 눌러야 문서가 바뀝니다). 서식 관리자는 어느 TASK 의 문서에서나 도구 줄 「서식」 묶음으로 엽니다." },
  // 문서 서식 복사(spec_서식복사 ② §1) — accept = 이 TASK 의 카드가 받는 확장자(없으면 hwp·hwpx: taskAcceptOf) · entry "Style" = 처음 여는 것이 패널 도구가 아니라 서식 관리자의 「서식 복사」 보기(2열 — app.js taskEnter).
  // pdf 는 작업을 만들지 않고 서식 관리자의 파일 후보로 간다(app.js homeTaskStart). 문서는 바뀌지 않는다
  style_copy: { name: "문서 서식 복사", act: "서식 복사", doc: "any", file: "", up: "문서", kind: "general", entry: "Style", accept: ["hwp", "hwpx", "docx", "pdf"],
    desc: "문서에서 템플릿·문서 서식·테이블 서식을 뽑아 서식 관리자에 저장하고 PDF 로 검증합니다.",
    hint: "hwp·hwpx·docx 문서 하나 — 문서 옆 「서식 복사」 열에서 후보를 고르거나 「한 번에 진행」 을 누릅니다(문서는 바뀌지 않습니다). PDF 는 작업을 만들지 않고 서식 후보만 찾습니다. 저장한 서식은 다른 문서·TASK 에서 서식 관리자로 다시 씁니다." },
});
// 화면에서 조립한 TASK(spec_워크플로우 ② §14 — 2026-11-19 사용자 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」): 서버 저장소(app/custom_tasks.py)의 것을 이 목록 뒤에 더한다.
// `GET /api/tasks.js`(이 파일 다음 · app.js 앞에 읽는 스크립트)가 부른다 — app.js 가 이 목록에서 만드는 것(TASK 이름 · 문서 칸 · 카드)이 처음부터 조립한 TASK 를 안다.
// 조립한 TASK = 이관형(원본 문서 하나 → 목적 문서 하나): files = [원본, 목적] 칸 · target = 목적 문서 · groups = 고른 단계의 묶음 id(review · frame · map · clean — app.js taskStagesSync 가 그것만 세운다) · icon = 이관의 로고.
function taskCatalogCustom(defs) {
  for (const key of Object.keys(TASK_CATALOG)) if (TASK_CATALOG[key].custom) delete TASK_CATALOG[key];
  for (const d of Array.isArray(defs) ? defs : []) {
    if (!d || typeof d.key !== "string" || TASK_CATALOG[d.key]) continue;
    TASK_CATALOG[d.key] = { name: d.name, act: "이관", doc: "plan-report", file: "", up: "문서", desc: d.desc || `${d.sourceName}의 내용을 ${d.targetName}로 옮깁니다 — 고른 단계만 진행합니다.`,
      hint: `${d.sourceName}나 ${d.targetName} 가운데 하나 — 나머지 문서는 연 뒤 작업 개요의 첨부 파일 칸에서 올립니다(화면에서 조립한 TASK)`,
      files: [d.source, d.target], target: d.target, custom: true, groups: d.groups || [], stages: d.stages || [], icon: "plan_to_report" };
  }
}
// 이관형 TASK 인가 — 문서 칸 둘(원본 · 목적)을 쓰는 TASK: 붙박이 이관과 조립한 TASK. 화면의 「이관이면」 가지는 키를 견주지 않고 이것으로 가른다
const taskIsRelay = (job) => !!(TASK_CATALOG[job] || {}).files;
// 그 TASK 의 작업 종류(kind — 없으면 연구개발 프로젝트 rnd: server.py TASK_KIND 와 같게)와 처음 여는 패널 보기(entry — 없으면 작업 개요 Div). 화면의 TASK 시작 길은 「rnd」·「Div」 를 박아 두지 않고 이것을 읽는다(spec_일반편집 ② §11).
const taskKindOf = (job) => (TASK_CATALOG[job] || {}).kind || "rnd";
const taskEntryOf = (job) => (TASK_CATALOG[job] || {}).entry || "Div";
const taskAcceptOf = (job) => (TASK_CATALOG[job] || {}).accept || ["hwp", "hwpx"]; // 그 TASK 의 카드가 받는 확장자(spec_서식복사 ② §1 — 다른 TASK 는 전과 같이 hwp·hwpx)
// 그 TASK 가 편집 구역에서 기본으로 켤 기준(사람이 정한 적 없을 때 — spec_구역 ② §1). 서버 app/task_options.py ZONES_DEFAULT 와 같아야 한다(tests/test_task_catalog.py)
const taskZonesDefault = (job) => (TASK_CATALOG[job] || {}).zones || [];

// 이관·취합이 공유하는 사용자 단계 이름. 단계별 실행·완료 조건은 각 흐름이 정의한다.
// config = 구성(단계·차년도·기관)만 추출해 프로젝트에 확정 — 문서를 안 바꾼다(spec_작업 ② §18, 2026-11-13 사용자 "구분 기준만 추출하는 단계를 1, 프레임 작성 2, 내용 매핑 3"). 묶음 id·저장 키는 번호와 따로(frame·map·clean 그대로).
const TASK_STAGE_META = Object.freeze({
  config: { no: "1단계", name: "프로젝트 구성" },
  frame: { no: "2단계", name: "문서 프레임 작성" },
  map: { no: "3단계", name: "내용 매핑" },
  clean: { no: "4단계", name: "문서 정리" }, // 이관만(spec_작업 ② §14 「3단계」 — 2026-11-12 사용자 "3단계에 작성요령 삭제 기능을 넣어줘" · 2026-11-13 번호 4)
});
// 이관의 묶음 이름(spec_작업 ② §21 — 2026-11-19 사용자 "문서 검토 … 단계가 있어야 하겠구나 헤딩/테이불 분석, 그 다음에 문서구성 그다음에 매핑" · "단계로 하면 구성 맞추기, 내용 넣기").
// 취합은 위 TASK_STAGE_META 그대로. 묶음 id 는 review(새) · frame · map · clean(그대로 — 서버 …/merge-links/reset 의 stage 값). 등록부 app/workflow.py 의 그 묶음 no·name 과 같아야 한다(tests/test_workflow.py).
const RELAY_STAGE_META = Object.freeze({
  review: { no: "1단계", name: "문서 검토" },
  frame: { no: "2단계", name: "구성 맞추기" },
  map: { no: "3단계", name: "내용 넣기" },
  clean: { no: "4단계", name: "문서 정리" },
});
