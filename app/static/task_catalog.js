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
    hint: "hwp·hwpx 문서 하나 — 오른쪽 에이전트에 자료를 주고 요청하면 제안을 냅니다(「문서에 반영」 을 눌러야 문서가 바뀝니다). 서식 관리자는 어느 워크플로우의 문서에서나 도구 줄 「서식」 묶음으로 엽니다." },
  // 문서 서식 복사(spec_서식복사 ② §1) — accept = 이 TASK 의 카드가 받는 확장자(없으면 hwp·hwpx: taskAcceptOf) · entry "Style" = 처음 여는 것이 패널 도구가 아니라 서식 관리자의 「서식 복사」 보기(2열 — app.js taskEnter).
  // pdf 는 작업을 만들지 않고 서식 관리자의 파일 후보로 간다(app.js homeTaskStart). 문서는 바뀌지 않는다
  style_copy: { name: "문서 서식 복사", act: "서식 복사", doc: "any", file: "", up: "문서", kind: "general", entry: "Style", accept: ["hwp", "hwpx", "docx", "pdf"],
    desc: "문서에서 템플릿·문서 서식·테이블 서식을 뽑아 서식 관리자에 저장하고 PDF 로 검증합니다.",
    hint: "hwp·hwpx·docx 문서 하나 — 문서 옆 「서식 복사」 열에서 후보를 고르거나 「한 번에 진행」 을 누릅니다(문서는 바뀌지 않습니다). PDF 는 작업을 만들지 않고 서식 후보만 찾습니다. 저장한 서식은 다른 문서·워크플로우에서 서식 관리자로 다시 씁니다." },
});
// 화면에서 조립한 TASK(spec_워크플로우 ② §14 — 2026-11-19 사용자 "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」): 서버 저장소(app/custom_tasks.py)의 것을 이 목록 뒤에 더한다.
// `GET /api/tasks.js`(이 파일 다음 · app.js 앞에 읽는 스크립트)가 부른다 — app.js 가 이 목록에서 만드는 것(TASK 이름 · 문서 칸 · 카드)이 처음부터 조립한 TASK 를 안다.
// 조립한 TASK = 이관형(원본 문서 하나 → 목적 문서 하나): files = [원본, 목적] 칸 · target = 목적 문서 · groups = 고른 단계의 묶음 id(review · frame · map · clean — app.js taskStagesSync 가 그것만 세운다) · icon = 이관의 로고.
//   (틀이 다른 것: shape "gather" = 취합형 — gather 칸 · shape "single" = 문서 하나 — file 하나 + single 표지: 아래 가지 · taskIsGather · taskIsSingle)
// assign = 문서마다 고른 단계 {source: [단계 id…], target: [단계 id…], llm: [문서 역할…] | null}(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 묶음 안에서 어느 문서에 하는지: app.js taskReviewDocs) · 서버가 안 보냈으면 null(붙박이 이관처럼).
//   llm = 1단계 「LLM 검증·보완」 을 할 문서 역할(source · target — 서버 app/custom_tasks.py 가 정한다: 옛 정의는 원본만) · 옛 서버가 안 보냈으면 null(taskReviewDocs 가 전의 규칙으로 셈).
// does = 묶음 id → 그 조립한 워크플로우의 묶음 설명(서버가 실제 배정에서 만든 글 — 등록부 custom() 과 같은 글: app.js taskStagesSync 가 묶음 머리 · 「한 번에 진행」 · 에이전트 카드에 쓴다) · 없으면 null.
// desc = 사람이 적은 한 줄 설명 → 없으면 등록부가 실제 배정에서 지은 한 줄(descAuto — 「내용 넣기」 가 없으면 「옮깁니다」 라 하지 않는다) → 그것도 없으면(옛 서버) 기본 글.
// sig = 그 정의의 단계 표지(서버가 보낸 것 — 저장된 정의의 단계(배정 · 단계)가 바뀔 때만 바뀐다: 이름 · 설명 · 전제만 고치면 그대로) · sigLocal = 이 화면이 같은 값(정리한 배정 · 단계)으로 지은 짧은 표지(옛 서버 — sig 가 없을 때 견줄 것).
//   열어 둔 화면의 정의가 낡았나를 견주고(app.js taskCatalogRefresh — spec_워크플로우 ② §15 「실행」) 에이전트 실행 카드의 key 에 든다(doc_agent_work.js agwRelayStatus — 정의가 바뀌기 전에 낸 카드는 실행하지 않고 다시 묻는다).
// opt = {broken} — 서버가 조립한 워크플로우 저장 파일(tasks.json)을 못 읽었나(GET /api/tasks.js 의 둘째 인자 · GET /api/tasks 의 broken). 작업의 워크플로우가 목록에 없을 때 그 까닭을 가른다(taskLostWhy) — 안 보냈으면(옛 서버) 못 읽은 것이 아닌 것으로 본다.
let taskCatalogBroken = false;
function taskCatalogCustom(defs, opt = null) {
  taskCatalogBroken = !!(opt && opt.broken);
  for (const key of Object.keys(TASK_CATALOG)) if (TASK_CATALOG[key].custom) delete TASK_CATALOG[key];
  for (const d of Array.isArray(defs) ? defs : []) {
    if (!d || typeof d.key !== "string" || TASK_CATALOG[d.key]) continue;
    const A = d.assign && typeof d.assign === "object" ? d.assign : null, ids = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === "string") : []);
    const llm = A && Array.isArray(A.llm) ? ids(A.llm).filter((r) => r === "source" || r === "target") : null;
    const does = d.does && typeof d.does === "object" && !Array.isArray(d.does) ? Object.fromEntries(Object.entries(d.does).filter(([, v]) => typeof v === "string" && v.trim())) : null;
    const assign = A ? { source: ids(A.source), target: ids(A.target), llm } : null, stages = d.stages || [], auto = typeof d.descAuto === "string" && d.descAuto.trim() ? d.descAuto : "";
    // v2 = 줄 목록으로 조립한 정의(spec_워크플로우 ② §18-5 — 표준 차례가 아님: assign · stages 없음 · groups = g1 …) — 서버 실행기만 돌린다(화면의 이관 실행 코드는 그 묶음을 모른다 · 서버가 못 맡으면 409)
    const v2 = d.v === 2;
    if (d.shape === "gather") { // 취합형으로 조립한 것(원본 = 기관 문서 여럿 → 목적 = 취합본 하나 — spec_워크플로우 ② §18-13 갈래 「라」): 붙박이 「사업계획서 취합」 과 같은 칸(gather) · 같은 기본 구역(기관) · 늘 줄 목록(v2)
      // stageOf = 취합 화면의 묶음(config · frame · map — gather.js GT_STAGES) → 이 정의의 묶음 id(그 일을 하는 줄이 든 묶음 — 서버가 준 것 | 없으면 그 묶음이 이 정의에 없다)
      TASK_CATALOG[d.key] = { name: d.name, act: "취합", doc: "plan", file: d.target, up: "취합본", upMany: "문서 여러 개", quick: true, desc: d.desc || auto || "기관이 나눠 쓴 문서의 내용을 취합본 하나로 모읍니다 — 정한 차례대로 진행합니다.",
        hint: "취합본과 기관 문서를 위 목록에 올리고 목적 문서(취합본)를 고른 뒤 이 카드를 누릅니다(화면에서 조립한 워크플로우 — 묶음은 대시보드에서 진행합니다)",
        gather: { base: d.target, parts: d.source }, target: d.target, zones: ["org"], custom: true, groups: d.groups || [], stages: [], assign: null, does, v2: true,
        ...gatherDefMap(d.flow), sig: typeof d.sig === "string" ? d.sig : "", sigLocal: taskSigLocal(null, d.groups || []), icon: "plan_merge" };
      continue;
    }
    if (d.shape === "single") { // 문서 하나로 조립한 것(원본 문서 없음 — 그 문서가 곧 목적 문서: spec_워크플로우 ② §18-13 걸음 6 · 2026-11-20 사용자 "그리고 문서 하나는 왜 안되냐?" → 답 「조립한 것만 서버로」)
      // 칸의 꼴은 붙박이 문서 하나(양식 표준화 · 양식 맞추기)와 같다 — 문서 종류 하나(file · 문서 칸 둘 files 도 취합 칸 gather 도 없다: taskIsRelay · taskIsGather 가 거짓) · target = 그 종류(서버 custom_tasks.target_file 과 같게).
      // single = 가르는 표지(taskIsSingle — 붙박이 문서 하나에는 없다: 그것은 화면이 돈다) · 늘 줄 목록(v2) · **서버 실행기만 돌린다**(workflow_exec.js singleRunServer — 묶음 g1 … 은 대시보드에서: 처음 여는 보기 entry "Dash")
      const report = d.target === "report", kind = d.targetName || (report ? "연차보고서" : "사업계획서");
      TASK_CATALOG[d.key] = { name: d.name, act: report ? "양식 맞추기" : "양식 표준화", doc: report ? "report" : "plan", file: d.target, up: kind, entry: "Dash",
        desc: d.desc || auto || "줄 목록으로 조립한 문서 하나 워크플로우입니다 — 정한 차례대로 서버에서 진행합니다.",
        hint: `${kind} 하나 — 올린 뒤 묶음은 대시보드에서 진행합니다(화면에서 조립한 워크플로우 — 서버에서 진행)`,
        target: d.target, custom: true, single: true, groups: d.groups || [], stages: [], assign: null, does, v2: true,
        sig: typeof d.sig === "string" ? d.sig : "", sigLocal: taskSigLocal(null, d.groups || []), icon: report ? "report_fit" : "plan_fit" };
      continue;
    }
    TASK_CATALOG[d.key] = { name: d.name, act: "이관", doc: "plan-report", file: "", up: "문서", desc: d.desc || auto || `${d.sourceName}의 내용을 ${d.targetName}로 옮깁니다 — 고른 단계만 진행합니다.`,
      hint: `${d.sourceName}나 ${d.targetName} 가운데 하나 — 나머지 문서는 연 뒤 작업 개요의 첨부 파일 칸에서 올립니다(화면에서 조립한 워크플로우)`,
      files: [d.source, d.target], target: d.target, custom: true, groups: d.groups || [], stages, assign: v2 ? null : assign, does, v2,
      sig: typeof d.sig === "string" ? d.sig : "", sigLocal: taskSigLocal(assign, stages), icon: "plan_to_report" };
  }
}
// 조립한 워크플로우의 키 꼴(서버 app/custom_tasks.py KEY 와 같게 — u_ + 16진 8자). 목록에 없어도 이 꼴이면 조립한 것으로 본다(지워졌거나 저장 파일을 못 읽음 — taskLostWhy)
const taskCustomKey = (job) => typeof job === "string" && /^u_[0-9a-f]{8}$/.test(job);
function taskSigLocal(assign, stages) { // 정리한 배정(source · target · llm) + 단계 → 짧은 표지(「c」 + 36진 — 서버의 sig 와 섞이지 않게)
  const s = JSON.stringify([assign ? [assign.source, assign.target, assign.llm] : null, stages]);
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) | 0;
  return `c${(h >>> 0).toString(36)}`;
}
const taskCatalogSig = (c) => (c && (c.sig || c.sigLocal)) || ""; // 단계 표지 — 서버의 sig, 없으면 이 화면이 지은 것
const taskSigSame = (a, b) => (a.sig && b.sig ? a.sig === b.sig : a.sigLocal === b.sigLocal); // 같은 정의인가 — 둘 다 서버의 sig 가 있을 때만 그것으로(서버가 새 판으로 바뀐 것을 단계가 바뀐 것으로 읽지 않게)
// 작업의 워크플로우가 조립한 것(키 꼴)인데 목록에 없다 → 그 까닭 한 줄 | ""(spec_워크플로우 ② §15 「실행」 — 빈 칸 · 사라진 단계로 두지 않는다).
// 작업 개요(워크플로우 칸 아래) · 대시보드가 보인다 — 그 작업에서는 아무 실행도 내지 않고, job 값은 사람이 다른 워크플로우를 고를 때까지 그대로 둔다.
// 에이전트는 그 작업의 진행을 맡지 않고(입력 칸의 글은 편집 에이전트로 — doc_agent_work.js agwGuided) 맡던 때 낸 카드를 누르면 이 까닭으로 실행하지 않는다(agwStatusOf).
// 저장 파일 글이 가리키는 곳 = /workflow 의 절 「워크플로우 조립」(workflow.js composeSec 의 머리 · 목차의 「＋ 워크플로우 조립」)
function taskLostWhy(job) {
  if (!taskCustomKey(job) || TASK_CATALOG[job]) return "";
  return taskCatalogBroken ? "조립한 워크플로우 저장 파일(tasks.json)을 읽지 못했습니다 — 워크플로우 페이지의 「워크플로우 조립」 에서 확인하세요"
    : "이 작업의 워크플로우(조립한 것)가 지워졌습니다 — 다른 워크플로우를 고르세요";
}
// 이관형 TASK 인가 — 문서 칸 둘(원본 · 목적)을 쓰는 TASK: 붙박이 이관과 이관형으로 조립한 TASK. 화면의 「이관이면」 가지는 키를 견주지 않고 이것으로 가른다(문서 하나로 조립한 것은 문서 칸 둘이 없다 — 이관형이 아니다)
const taskIsRelay = (job) => { const c = TASK_CATALOG[job] || {}; return !!c.files && !c.single; };
// 문서 하나로 조립한 워크플로우인가(조립 폼의 「1」 — 원본 문서 없이 그 문서 하나에 정한 줄을 차례로: 서버 실행기만 돌린다). **붙박이 문서 하나(사업계획서 양식 표준화 · 연차보고서 양식 맞추기)는 아니다** — 그것은 화면이 돈다.
// 화면의 「조립한 문서 하나면」 가지(서버 실행의 거울 · 3초 확인 = 고치던 글 보고 · 대시보드 · 에이전트)는 키를 견주지 않고 이것으로 가른다 — 이 표지가 참인 워크플로우에서 taskIsRelay · taskIsGather 는 거짓이다
const taskIsSingle = (job) => !!(TASK_CATALOG[job] || {}).single;
// 취합형 TASK 인가 — 취합본 하나 + 기관 문서 여럿(붙박이 「사업계획서 취합」 · 취합형으로 조립한 것). 화면의 「취합이면」 가지는 키(plan_merge)를 견주지 않고 이것으로 가른다(spec_워크플로우 ② §18-13 갈래 「라」 ⓷)
const taskGatherOf = (job) => (TASK_CATALOG[job] || {}).gather || null; // {base: 취합본의 종류, parts: 기관 문서의 종류} | null — 그때그때 읽는다(조립한 워크플로우는 정의를 다시 읽으면 바뀐다)
const taskIsGather = (job) => !!taskGatherOf(job);
// 취합 화면의 묶음(config · frame · map — gather.js GT_STAGES)마다의 줄(실행 단위 key — 화면의 줄이 그 묶음에 서는 대로: gather.js gatherSteps). 「기관 문서마다」 = 기관 문서 하나에 차례로 도는 줄(화면은 문서마다 한 줄 part:<id>)
const GATHER_SCREEN_UNITS = { config: ["config"], frame: ["division", "frame"], map: ["part", "heads", "link", "llm", "plan", "apply", "drop"] };
const GATHER_EACH_UNITS = ["part", "heads", "link", "llm", "plan", "apply"];
// 취합형으로 조립한 정의의 줄 목록(flow [{id, steps[{unit}]}]) → {unitAt{줄 key: 그 줄이 든 묶음 id}, stageOf{화면의 묶음: 그 묶음의 줄이 처음 나오는 정의의 묶음 id}} — 화면의 묶음을 정의의 묶음으로 잇는 표(조립한 것만 — 붙박이는 같은 id)
function gatherDefMap(flow) {
  const unitAt = {}, stageOf = {};
  for (const g of Array.isArray(flow) ? flow : []) for (const s of (g && Array.isArray(g.steps) ? g.steps : [])) {
    if (!s || typeof s.unit !== "string" || unitAt[s.unit]) continue;
    unitAt[s.unit] = g.id;
    for (const [id, units] of Object.entries(GATHER_SCREEN_UNITS)) if (units.includes(s.unit) && !stageOf[id]) stageOf[id] = g.id;
  }
  return { unitAt, stageOf };
}
// 취합 화면의 묶음(+ 그 묶음에서 지금 할 줄의 key — 「part:<id>」 = 기관 문서마다의 줄) → 그 워크플로우의 묶음 id: 붙박이는 그대로 · 취합형으로 조립한 것은 그 줄이 든 묶음(g1 …) | ""(그 정의에 그 묶음의 줄이 없다).
// 서버 실행(workflow_exec.js gatherRunServer)과 대시보드(dashboard.js dashGatherLive)가 화면의 묶음을 정의의 묶음으로 잇는다
const gatherDefStage = (id, job, key = "") => {
  const c = TASK_CATALOG[job] || {};
  if (!c.custom) return id;
  const unit = key.startsWith("part:") ? GATHER_EACH_UNITS.find((u) => (c.unitAt || {})[u]) || "" : key;
  return (c.unitAt || {})[unit] || (c.stageOf || {})[id] || "";
};
// 서버 실행의 지금 줄(key) → 취합 화면의 묶음 id | ""(화면의 묶음에 없는 줄 — 「사람이 하는 일」: 부르는 쪽이 보던 묶음을 그대로 둔다). 붙박이는 서버의 묶음 id 가 곧 화면의 것
const gatherScreenStage = (now, job) => {
  if (!(TASK_CATALOG[job] || {}).custom) return (now && now.stage) || "";
  return (Object.entries(GATHER_SCREEN_UNITS).find(([, units]) => units.includes((now && now.key) || "")) || [""])[0];
};
// 그 TASK 의 작업 종류(kind — 없으면 연구개발 프로젝트 rnd: server.py TASK_KIND 와 같게)와 처음 여는 패널 보기(entry — 없으면 작업 개요 Div). 화면의 TASK 시작 길은 「rnd」·「Div」 를 박아 두지 않고 이것을 읽는다(spec_일반편집 ② §11).
const taskKindOf = (job) => (TASK_CATALOG[job] || {}).kind || "rnd";
const taskEntryOf = (job) => (TASK_CATALOG[job] || {}).entry || "Div";
const taskAcceptOf = (job) => (TASK_CATALOG[job] || {}).accept || ["hwp", "hwpx"]; // 그 TASK 의 카드가 받는 확장자(spec_서식복사 ② §1 — 다른 TASK 는 전과 같이 hwp·hwpx)
// 그 TASK 가 편집 구역에서 기본으로 켤 기준(사람이 정한 적 없을 때 — spec_구역 ② §1). 서버 app/task_options.py ZONES_DEFAULT 와 같아야 한다(tests/test_task_catalog.py)
const taskZonesDefault = (job) => (TASK_CATALOG[job] || {}).zones || [];
// 이름 뒤 조사 — 끝 글자에 받침이 있으면 a, 없으면 b(서버 app/custom_tasks.py _eun · dashboard_workflows.js dwfEul 과 같은 셈: 한글 · 숫자의 끝 글자로 가린다 — 그 밖의 글자는 b).
// 「으로/로」(a 가 「으로…」)는 ㄹ 받침이면 b(「로」). 이름 뒤에 조사를 박아 두지 않고 이것으로 붙인다(spec_워크플로우 ② §15 「화면 말」 — 「워크플로우」 · 이름이 바뀌면 받침도 바뀐다).
// 예: taskJosa("구성 · 넣기 · 정리", "을", "를") → "를" · taskJosa("이관", "을", "를") → "을" · taskJosa("이관", "으로", "로") → "으로" · taskJosa("문서 검토", "으로", "로") → "로" · taskJosa("사본 7", "으로", "로") → "로"(칠 — ㄹ 받침)
function taskJosa(word, a, b) {
  const c = String(word == null ? "" : word).slice(-1);
  const jong = c >= "가" && c <= "힣" ? (c.charCodeAt(0) - 0xac00) % 28 // 받침 번호 — 0 없음 · 8 ㄹ
    : /[0-9]/.test(c) ? [21, 8, 0, 16, 0, 0, 1, 8, 8, 0][Number(c)] : 0; // 숫자는 읽는 소리(영 · 일 · 이 · 삼 · 사 · 오 · 육 · 칠 · 팔 · 구) — 받침 = 0 1 3 6 7 8
  if (!jong) return b;
  return jong === 8 && String(a).startsWith("으로") ? b : a;
}

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
