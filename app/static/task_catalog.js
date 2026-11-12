// TASK 조합의 원본: 이름·차례·시작 문서·화면 종류를 함께 관리한다.
// job 키는 server.py TASK["job"] 및 저장된 work.task.job과의 계약이다.
// files = 이관의 문서 칸, gather = 취합본 한 개 + 기관 문서 여러 개.
// 새 TASK를 넣을 때 spec/spec_작업.md §16의 모듈·검사 범위도 확인한다.
const TASK_CATALOG = Object.freeze({
  plan_fit: { name: "사업계획서 양식 맞추기", act: "양식 맞추기", doc: "plan", file: "plan", up: "사업계획서", desc: "단계·차년도·기관에 맞춰 양식의 절·표를 늘리고 줄입니다." },
  plan_merge: { name: "사업계획서 취합", act: "취합", doc: "plan", file: "plan", up: "취합본", desc: "기관이 나눠 쓴 문서의 내용을 사업계획서 하나로 모읍니다.",
    hint: "취합본 = 내용을 모을 원래 사업계획서 — 기관 문서는 연 뒤 작업 내용에서 넣습니다", gather: { base: "plan", parts: "part" } },
  plan_to_report: { name: "사업계획서 → 연차보고서 이관", act: "이관", doc: "plan-report", file: "", up: "문서", desc: "사업계획서에서 필요한 내용을 뽑아 연차보고서로 옮깁니다.",
    hint: "사업계획서나 연차보고서 가운데 하나 — 나머지 문서는 연 뒤 작업 내용의 첨부 파일 칸에서 올립니다", files: ["plan", "report"] },
  report_fit: { name: "연차보고서 양식 맞추기", act: "양식 맞추기", doc: "report", file: "report", up: "연차보고서", desc: "단계·차년도·기관에 맞춰 양식의 절·표를 늘리고 줄입니다." },
  report_merge: { name: "연차보고서 취합", act: "취합", doc: "report", file: "report", up: "취합본", soon: true, desc: "기관이 나눠 쓴 문서의 내용을 연차보고서 하나로 모읍니다." },
});

// 이관·취합이 공유하는 사용자 단계 이름. 단계별 실행·완료 조건은 각 흐름이 정의한다.
const TASK_STAGE_META = Object.freeze({
  frame: { no: "1단계", name: "문서 프레임 작성" },
  map: { no: "2단계", name: "내용 매핑" },
});
