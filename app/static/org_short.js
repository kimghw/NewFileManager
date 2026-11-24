// 취합의 기관 문서 꼬리표 — 기관 약칭 「[한국선]」(spec_취합 ② §11: 2026-11-24 사용자 "취합문서의 경우 이제 원본문서 가 아님 [기관] 으로 표기해야할거 같은데 [한국선] [씨드로] [유엔젤] 이런식이고 만약 앞 2글자가 동일하지 않다면 2글자로 하고").
// 취합(사업계획서 취합 · 취합형으로 조립한 것 · 같은 양식 취합)에서 기관 문서(원본 문서 — 여럿)를 「원본 문서」 · 「원본」 대신 반영할 기관의 약칭으로 보인다:
// 첫째 면 이름 줄의 꼬리표(app.js docRoleDraw) · 둘째 면 탭의 꼬리표(peerTabsDraw) · 「도구」 의 문서 단추(toolDocList · toolDocDraw) · 대시보드의 기관 문서 카드(dashboard.js · home_dash.js — collect.js collectDocName).
// 문서를 가리키지 않는 역할 꼬리표(「원본 문서마다」)는 「[기관]」. 역할(원본 · 목적)의 뜻 · 코드 · 저장 키는 그대로다 — 보이는 글만.
// 약칭 = 법인 표시(「(주)」 · 「㈜」 · 「주식회사」 · 「사단법인」 …)와 빈칸을 뺀 이름의 앞 글자. 길이는 **모든 기관이 같다**(에이전트 판단 — 사용자 확인 전: 사용자의 예 [씨드로] 가 앞 2글자 「씨드」 만으로도 갈리는데 3글자인 것을
// 「한 기관이라도 앞 2글자가 겹치면(한국선급 · 한국전기연구원) 모두 3글자」 로 읽음): 앞 2글자가 모두 다르면 2글자 · 아니면 3글자 · 그래도 겹치면 갈릴 때까지 늘린다(이름이 짧으면 이름 그대로).
// 견주는 기관 = 그 프로젝트 구성의 기관 모두(없으면 문서에 지정한 기관들) — 문서마다 달라지지 않게.
// 기대는 이름(부를 때 있으면): app.js state · TASK_CATALOG · taskDocRole · taskSlotDoc · docRoleDraw · toolDocDraw · peerSync · gatherOn / gather.js gt · gatherPart / collect.js collectView · collectRead / task_catalog.js taskIsCollect · taskGatherOf.
const ORG_LEGAL = /^(?:\((?:주|사|재|유|합|학|의)\)|㈜|㈔|㈕|주식회사|유한회사|합자회사|사단법인|재단법인|학교법인|의료법인)|(?:\((?:주|사|재|유)\)|㈜|주식회사)$/;

function orgBare(name) { // 법인 표시 · 빈칸을 뺀 이름(약칭을 셀 바탕)
  let s = String(name || "").replace(/\s+/g, "");
  for (let i = 0; i < 4; i += 1) { const t = s.replace(ORG_LEGAL, ""); if (t === s || !t) break; s = t; }
  return s;
}

function orgShortLen(names) { // 기관 이름들 → 약칭 길이(모두 같은 길이 — 2부터 앞 글자가 모두 갈릴 때까지)
  const bare = [...new Set((names || []).map(orgBare).filter(Boolean))];
  const most = Math.max(2, ...bare.map((b) => b.length));
  for (let n = 2; n <= most; n += 1) if (new Set(bare.map((b) => b.slice(0, n))).size === bare.length) return n;
  return most;
}

function orgShort(name, names) { // 기관 이름 → 약칭(「한국선급」 → 「한국선」) — names = 견줄 기관 모두(그 프로젝트 구성)
  const b = orgBare(name);
  return b ? b.slice(0, orgShortLen([...(names || []), name])) : String(name || "");
}

const orgTagText = (names, all) => { // 반영할 기관 이름들 → 꼬리표 글 「[한국선]」 · 「[한국선·씨드로]」 · 「[한국선 외 2]」 · 「[모든 기관]」 · 없으면 「[미지정]」
  const L = names.length;
  if (!L) return "[미지정]";
  if (all.length > 1 && L === all.length && all.every((n) => names.includes(n))) return "[모든 기관]";
  const s = names.map((n) => orgShort(n, all));
  return `[${L > 2 ? `${s[0]} 외 ${L - 1}` : s.join("·")}]`;
};

function orgJob() { return (typeof state !== "undefined" && state.task && state.task.job) || ""; }
function orgIsGather(job = orgJob()) { // 기관 문서가 여럿인 취합인가 — 사업계획서 취합 · 취합형으로 조립한 것 · 같은 양식 취합
  return !!job && ((typeof taskGatherOf === "function" && !!taskGatherOf(job)) || (typeof taskIsCollect === "function" && taskIsCollect(job)));
}

function orgCollectTarget(job) { // 같은 양식 취합의 목적 문서 id(그 등록부 — collect.js — 의 열쇠) | ""
  const kind = ((typeof TASK_CATALOG !== "undefined" && TASK_CATALOG[job]) || {}).target;
  return (kind && typeof taskSlotDoc === "function" && (taskSlotDoc(kind) || {}).id) || "";
}

// 문서 w({id, task}) → {tag 꼬리표 글, names 반영할 기관 이름들, all 견준 기관} | null(취합의 기관 문서가 아니다 — 「원본 문서」 그대로).
// 등록부를 아직 못 읽었으면 읽기를 걸고 null(읽으면 orgTagsSync 가 다시 그린다)
function docOrgTag(w, job = orgJob()) {
  if (!w || !orgIsGather(job) || typeof taskDocRole !== "function" || taskDocRole(w.task, job) !== "source") return null;
  if (typeof taskIsCollect === "function" && taskIsCollect(job)) {
    const tid = orgCollectTarget(job), V = tid && typeof collectView === "function" ? collectView(tid) : null;
    if (!V) { if (tid && typeof collectRead === "function") collectRead(tid); return null; }
    const p = (V.parts || []).find((q) => q.work === w.id);
    if (!p) return null;
    const names = (p.orgNames || p.orgs || []).map(String), all = (V.orgs || []).map((o) => o.name);
    return { tag: orgTagText(names, all.length ? all : names), names, all };
  }
  if (typeof gatherPart !== "function" || typeof gt !== "function") return null;
  const p = gatherPart(w.id), V = gt().view;
  if (!p || !V) return null;
  const orgs = V.orgs || [], names = (p.orgs || []).map((k) => (orgs.find((o) => o.key === k) || {}).name || k), all = orgs.map((o) => o.name);
  return { tag: orgTagText(names, all.length ? all : names), names, all };
}

const orgTagTitle = (t) => (t.names.length ? `기관 문서 — 반영할 기관 ${t.names.join(" · ")}` : "기관 문서 — 반영할 기관을 아직 정하지 않았습니다");

function orgTagsSync() { // 반영할 기관 · 등록부가 바뀐 뒤(collect.js collectRead · gather.js 의 등록부 읽기) — 문서 꼬리표를 다시(다시 부르면 같은 그림 — 바뀐 것만)
  if (typeof state === "undefined" || !state.id) return;
  if (typeof docRoleDraw === "function") docRoleDraw();
  if (typeof peerSync === "function" && !(typeof PEEK !== "undefined" && PEEK)) peerSync(); // 둘째 면 탭 · 「도구」 의 문서 단추(peerOpenMark → toolDocDraw)
  else if (typeof toolDocDraw === "function") toolDocDraw();
}
