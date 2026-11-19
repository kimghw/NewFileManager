"""표의 병합 방식 식별 끝점(spec_테이블매니저 ② §5 「병합 방식」) — `GET /api/docs/{id}/tables/kinds`. 판정은 `app/table_kinds.py`(순수), 화면은 「테이블」 탭(`app/static/tables.js`).
문서를 바꾸지 않고 LLM 도 부르지 않는다. 연구개발과제 문서만(일반 문서는 `{gate: "none"}`).

- 관문 = 구분 기준 판독과 같다(`division_scan_api.enabled` — hwpx · 작업 종류 rnd). 관문 밖이면 3단계 결과가 있든 없든 `{gate: "none"}` 뿐.
- 표 = 마지막 3단계 결과(`heading_runs.tables`) 그대로 — 없으면 빈 목록 + `missing: true`(404 가 아니다). 문서가 그 뒤 바뀌었으면(`meta.rev != rev`) `stale: true` 를 싣고 그대로 쓴다(다시 돌리라고 조르지 않는다).
- 편집 구역 = `zones_api.read(s)`(세션 잠금은 그 함수가 잡는다 — 여기서 잠금 안에서 부르지 않는다) · `zones.label_of`. 기관 · 차년도 자리를 여기서 다시 계산하지 않는다.
  TASK 의 「보일 기준」 옵션이 꺼져 있어도 읽는다(옵션은 구역 띠를 묶을 때만 쓰이고 블록 · 칸의 귀속은 늘 온전하다 — spec_구역 ② §5). 프로젝트 구성 값이 없거나(`noValues`) 읽다가 실패하면
  구역 없이 머리글의 꼴만으로 정한다(`source.zones: false` — `sure` 는 모두 False)."""
import logging

from fastapi import APIRouter

from app import table_kinds

router = APIRouter()
log = logging.getLogger("uvicorn.error")


def _zone_of(s):
    """편집 구역의 귀속을 읽는 함수(`table_kinds.kinds` 의 zone_of) | None(프로젝트 구성 값이 없음 · 읽지 못함).
    아는 id = 본문 최상위 블록과 그 표의 칸 — 칸 안의 표 · 그 칸은 None(편집 구역이 읽지 않는다: 바깥 칸의 귀속을 `kinds` 가 물려 준다)."""
    from app import zones, zones_api
    try:
        view = zones_api.read(s)
    except Exception:   # noqa: BLE001 — 구역을 못 읽어도 방식은 머리글의 꼴로 낸다
        log.exception("[병합 방식] 편집 구역을 읽지 못했습니다 — 구역 없이 정합니다")
        return None
    if view.get("basis") is None or "noValues" in (view.get("reasons") or ()) or "unsupportedForm" in (view.get("reasons") or ()):
        return None
    known = set((view.get("_info") or {}).get("order") or ()) | set(view.get("_tableOf") or ())
    names = {o.get("key"): o.get("name") for o in view.get("orgs") or ()}

    def zone_of(i):
        if i not in known:
            return None
        lab = zones.label_of(view, i) or {}
        kind = lab.get("orgKind")
        if (lab.get("src") or {}).get("org") == "origin":   # 취합으로 들어온 내용의 기관(spec_구역 ② §4) — 자리의 기관이 아니다: 공통 자리에 한 기관의 글이 들어왔다고 그 표가 그 기관의 표가 되지는 않는다
            kind = None
        return {"org": lab.get("org") if kind == "org" else None, "orgKind": kind, "orgName": names.get(lab.get("org")) if kind == "org" else None,
                "year": lab.get("year"), "stage": lab.get("stage")}
    return zone_of


@router.get("/api/docs/{doc_id}/tables/kinds")
def tables_kinds(doc_id: str):
    """→ {gate: "rnd", tables: [table_kinds.kinds 의 꼴…], counts: {perOrg, byDivision, sum, common, mixed}, source: {stage3Run, zones}, rev(, stale: true)} | {gate: "none"}."""
    from app import division_scan_api, heading_runs, server
    s = server._sess(doc_id)
    with s.lock:
        gate = division_scan_api.enabled(s)
        t3 = heading_runs.tables(s) if gate else None
        rev = s.rev
    if not gate:
        return {"gate": "none"}
    if not isinstance(t3, dict) or not isinstance(t3.get("tables"), list):
        # 3단계 결과가 아직 없다 — 404 가 아니라 빈 목록(`missing`): 「테이블」 탭이 열릴 때마다 묻는 끝점이라 404 면 브라우저 콘솔에 오류가 쌓인다(화면 검사 table_types 가 그것으로 떨어졌다)
        return {"gate": "rnd", "tables": [], "counts": table_kinds.counts([]), "source": {"stage3Run": None, "zones": False}, "rev": rev, "missing": True}
    zone_of = _zone_of(s)
    tables = [table_kinds.kinds(t, zone_of, t3.get("repeats")) for t in t3["tables"] if isinstance(t, dict)]
    meta = t3.get("meta") or {}
    out = {"gate": "rnd", "tables": tables, "counts": table_kinds.counts(tables), "source": {"stage3Run": meta.get("run"), "zones": zone_of is not None}, "rev": rev}
    if meta.get("rev") != rev:
        out["stale"] = True
    return out
