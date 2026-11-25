"""넣은 뒤 템플릿 · 서식 정리 끝점(spec_병합 ② §5-9) — 계획은 `app/merge_retidy.py`(순수), 줄을 서식으로 바꾸는 길은 조정과 같은 `outline_match_api.apply_templates`(확정 서식 — outline_conform).

- `GET /api/docs/{id}/merge-retidy` → 지금 상태 + (헤딩 그래프가 마지막 반영 뒤의 것이면) 계획의 수 · 레벨마다의 줄. 문서 안 바뀜 · 분석 안 돌림.
- `POST …/merge-retidy {expectRev?}` → ① 헤딩 그래프가 마지막 반영(이관 merge.json · 취합 gather.json 의 `filled`) 전 것이면 **헤딩 2단계를 스크립트로 다시**(넣은 줄이 템플릿에 들게 — 몇 초) ② 계획 ③ 반영(트랜잭션 하나 — 실행 취소 1 · 기록 `mergeRetidy`)
  ④ 기록 `retidy.json`. 바꿀 것이 없어도 기록은 남긴다(그 반영 뒤의 정리는 끝남). 409 = 넣은 기록이 없음 · 문서가 바뀜(expectRev) · 다른 헤딩 작업이 돎.
- 저장 = 작업 폴더 `retidy.json` {version, graph{run(이 정리가 다시 분석한 그래프의 실행 번호), llmRun(그 전 그래프가 LLM 검증·보완을 거친 것이면 그 번호)} | None,
  applied{at, fill(그때의 「내용 넣기」 반영 표식 시각), rev, run, counts{levels, grown, deep, lines, fix, near, own, cutLevels, cut, cutLines, held, changed, reps, left}, rows[…],
  cuts[{tpl, no, level, side, id, name, new, lines, moved, stop}](이번에 뗀 서식 종속 템플릿 — merge_retidy.cut_all), cutLeft[{tpl, no, level, why}](못 가른 deep 레벨)} | None,
  dropped?{at, by(undo | restore | discard), applied(내린 기록의 at), fill}(문서가 정리 전 상태로 돌아가 내린 마지막 기록 — _on_bump)}.
- deep 레벨(넣을 자리보다 깊은 내용)은 반영 전에 같은 트랜잭션에서 서식 종속 템플릿으로 가른다(`merge_retidy.cut_all` — 오버레이만 · 실행 취소 1). GET 은 오버레이 사본에 갈라 본 계획이다.
- **넣은 기록 어댑터**(`_records`): 이관 = merge.json · 취합 = gather.json(그 작업의 워크플로우가 취합 — server._gather_job: 마지막 「내용 반영 · 틀 맞춤」 의 표식 `filled` · 기관 문서마다 · 뺀 기관 문서의 본문 기록).
  사람이 처리를 고른 넘친 사례의 줄(merge_over.json 의 cases — 이관 · 취합 같이)은 맞추지 않는다(merge_retidy.plan 의 keep).
- **취합에서 달라지는 것**(spec_병합 ② §5-9 9): 취합본에 있던 줄은 바꾸지 않는다 — 「≈」 줄이 없고(plan near=False), 그 레벨에 취합본의 줄이 있으면(form · user) 확정 서식으로 다시 짓지 않고(settle 안 함)
  대표는 오버레이만 정한 뒤 넣은 줄만 대표의 모양으로(대표가 묶음 빈칸 · 자리 규칙을 갖추지 않았으면 그것도 걸지 않는다 — _full). 뒤에 올 기관 문서가 취합본 줄의 글(경계 줄)로 자리를 찾기 때문이다.
  넣은 줄만 있는 레벨(grown · cut)은 이관과 같다. 서식 종속 템플릿으로 가르기(cut)는 오버레이의 소속만 옮겨 문서를 안 바꾸므로 취합에도 같다(양식 쪽을 떼는 것도 — 그 줄이 넣은 줄의 템플릿에서 빠져 뒤의 조정이 넣은 줄의 서식으로 바꾸지 않는다).
  반영 뒤, 정리 전에 지문이 맞던 본문 넣은 기록의 지문(fp)을 다시 적는다(merge_gather_api.fp_matches · refit_fp — 다음 판정이 「이미 들어 있음」 으로 보게).
- **LLM 검증·보완을 거친 그래프를 다시 분석해도 그 줄이 「안 함」 으로 돌아가지 않게**: 워크플로우 상태(unit_steps.facts 의 heads.llm)는 지금 그래프가 이 정리가 다시 분석한 것이고
  그 전 그래프가 LLM 을 거친 것이면 거친 것으로 본다(`llm_kept`) — 넣기 전 문서의 판정은 받았고, 다시 분석은 넣은 줄을 템플릿에 넣으려는 것이다(에이전트 판단 — 사용자 확인 전).
- **다시 반영 · 복원**(spec_병합 ② §5-9 10): 이관의 「넣을 것 0」 표식은 앞의 실제 반영(`filled.last`)으로 본다(_filled — 넣은 내용은 문서에 남는다) ·
  문서가 정리 전 상태로 돌아가면(정리를 되돌린 실행 취소 · 정리 전에 만든 확정으로 복원 · 모두 되돌리기) 편집 알림(server.BUMPED)을 듣고 `applied` 를 내린다(_on_bump — 줄이 다시 「할 차례」 ·
  다시 하면 정리가 든 문서에서는 할 것 없음으로 끝남)."""
import copy
import logging
import time

from fastapi import APIRouter, Body, HTTPException

from app import merge_retidy as MR
from app import works

router = APIRouter()
log = logging.getLogger("uvicorn.error")
FILE, VERSION = "retidy.json", 1
WAIT_MAX = 600   # 다시 분석을 기다리는 한도(초)
NO_FILL = "넣은 내용이 없습니다 — 「내용 반영」 뒤에 합니다"
NO_DRAFT = "반영한 초안이 없습니다 — 「고른 초안을 문서에 반영」 뒤에 합니다"   # 양식 작성(_form_write_doc)


def _path(wid):
    f = works.folder(wid)
    return f / FILE if f is not None and (f / "work.json").is_file() else None


def load(wid):
    """저장한 것 {version, graph, applied} | 빈 것."""
    p = _path(wid)
    got = works._read_json(p) if p is not None and p.is_file() else None
    return got if isinstance(got, dict) and got.get("version") == VERSION else {"version": VERSION, "graph": None, "applied": None}


def _save(wid, data):
    p = _path(wid)
    if p is not None:
        works._write_json(p, data)


def _store(wid):
    from app import merge_api
    try:
        return merge_api._store(wid) or {}
    except Exception:   # noqa: BLE001 — 목적 문서가 아니거나 넣은 기록이 없음
        return {}


def _filled(rec):
    """마지막 반영 표식 {at, rev, ids …} | None(넣은 것이 없음). 이관의 「넣을 것 0」 확인(nothing — merge_api.merge_apply)은 그것이 지닌 앞의 실제 반영 표식(`last`)으로 본다 —
    다 넣은 문서를 다시 반영해도 넣은 내용은 문서에 남는다(spec_병합 ② §5-9 10). `last` 가 없는 「넣을 것 0」 은 None(옛 판의 기록은 _records 가 넣은 기록으로 가린다)."""
    f = (rec or {}).get("filled") or {}
    if f.get("at") and not f.get("nothing"):
        return f
    last = f.get("last") if isinstance(f.get("last"), dict) else {}
    return last if last.get("at") and not last.get("nothing") else None


def _llm_done(g):
    lm = (g or {}).get("llm") or {}
    return bool(lm.get("requested")) and not lm.get("fallback")


def llm_kept(wid, run):
    """지금 헤딩 그래프(실행 번호 run)가 이 정리가 다시 분석한 것이고 그 전 그래프가 LLM 검증·보완을 거쳤나(모듈 설명)."""
    g = load(wid).get("graph") or {}
    return run is not None and g.get("run") == run and g.get("llmRun") is not None


def _gather_doc(wid):
    """그 목적 문서가 취합본인가 — 그 작업의 워크플로우가 붙박이 「사업계획서 취합」 이거나 취합형으로 조립한 것(server._gather_job — 키 글자로 가르지 않는다)."""
    from app import server
    return server._gather_job(((works.work(wid) or {}).get("task") or {}).get("job"))


def _form_write_doc(wid):
    """그 문서가 양식 작성(form_write)의 목적 문서인가 — 넣은 기록이 merge.json 이 아니라 문서 에이전트의 반영한 초안이다(spec_양식작성 ② §5-5)."""
    return ((works.work(wid) or {}).get("task") or {}).get("job") == "form_write"


AGENT_TYPES = ("fill", "write", "tableFill")   # 글을 넣는 제안(서식 입히기 restyle · 새 표 tableNew · 서식 복사는 넣은 「글」 이 아니다)


def agent_filled(wid):
    """양식 작성의 넣은 기록 → (표식 {at, rev, ids} | None, 넣은 블록 · 칸 id 모음). 표식 = 마지막으로 반영한 초안의 때 · 문서 차례 —
    문서 에이전트 저장소(doc_agent.Store)의 「반영됨」 제안 가운데 글을 넣는 것(fill · write · tableFill)의 `applied.paras` · `applied.cells`. 문서 안 바뀜."""
    from app import doc_agent
    store = doc_agent.Store(wid)
    ids, last = set(), None
    for row in store.turns():
        for p in (store.turn(row.get("id")) or {}).get("proposals") or ():
            a = p.get("applied") if p.get("state") == "applied" and p.get("type") in AGENT_TYPES else None
            if not isinstance(a, dict):
                continue
            got = [x for x in (a.get("paras") or ()) if isinstance(x, str)] + [x for x in (a.get("cells") or ()) if isinstance(x, str)]
            if not got:
                continue
            ids.update(got)
            if last is None or (a.get("at") or 0) > (last.get("at") or 0):
                last = {"at": a.get("at"), "rev": a.get("rev")}
    return ({**last, "ids": sorted(ids)} if last else None), ids


def _records(wid):
    """넣은 기록 어댑터 → {mark(마지막 반영 표식 | None), ins(blocks → 지금 문서의 넣은 블록 id), n(넣은 블록 수), held(사람이 처리를 고른 넘친 줄), gather(취합인가)}.
    이관 = merge.json(merge_api._store — filled · applied · copied) · 취합 = gather.json(merge_gather_api._store — filled · 기관 문서마다 · 뺀 기관 문서의 본문 기록: merge_retidy.gather_ids ·
    표식을 적기 전 판에 넣은 취합본이면 표식을 한 번 적는다 — merge_gather_api.legacy_filled).
    held = 넘친 줄 기록(이관 applied[].over · 취합 applied[].convert.over) 가운데 사례 열쇠가 merge_over.json cases 에 있는 것의 줄(merge_retidy.held_ids)."""
    from app import merge_over as MO
    if _form_write_doc(wid):   # 양식 작성 — 넣은 줄 = 반영한 초안의 문단(사람이 고른 넘친 줄 · 취합의 규칙 없음 · 양식의 줄이 있는 레벨은 그 줄의 서식을 따른다)
        mark, want = agent_filled(wid)
        # relet=False — 레터를 바꾸지 않는다: 채운 줄의 레터는 양식이 적어 둔 자리표시(「    - 」)이거나 그 자리의 글이다(실측 d12321f92890: 「- → ■」 으로 같은 양식 줄 둘이 갈렸다)
        return {"mark": mark, "ins": (lambda blocks: MR.within(blocks, want)), "n": len(want), "held": set(), "gather": False, "relet": False}
    gather = _gather_doc(wid)
    if gather:
        from app import merge_gather_api as GA
        rec = GA._store(wid)
        if not rec.get("filled") and MR.gather_ids(rec):   # 표식을 적기 전(옛 판)에 넣은 취합본 — 한 번 적는다(rev = 지금: 그래프가 그보다 앞이면 한 번 다시 분석 — GA.legacy_filled)
            from app import server
            rec = GA.legacy_filled(wid, server._sess(wid).rev)
        want = MR.gather_ids(rec)
        ins, n, mark = (lambda blocks: MR.within(blocks, want)), len(want), _filled(rec)
    else:
        rec = _store(wid)
        mark, want = _filled(rec), MR.record_ids(rec)
        f = rec.get("filled") if isinstance(rec.get("filled"), dict) else {}
        if mark is None and f.get("at") and want:   # `last` 를 적기 전 판의 「넣을 것 0」 이 앞 반영을 덮은 기록 — 넣은 기록이 있으면 그 표식으로(정리를 한 번 다시 · 다 맞았으면 할 것 없음: spec_병합 ② §5-9 10)
            mark = f
        want = want | set((mark or {}).get("ids") or ())   # 「넣을 것 0」 이면 record_ids 는 그 빈 ids 만 읽는다 — 앞 반영(`last`)의 ids 에만 적힌 블록(빈 자리 검토가 넣은 줄 — merge_apply 의 gaps.inserted)도 정리 대상에 그대로 둔다
        ins, n = (lambda blocks: MR.within(blocks, want)), (len((mark or {}).get("ids") or ()) or len(want)) if mark else 0
    try:
        cases = MO.load(wid)["cases"]
    except Exception:   # noqa: BLE001 — 넘친 레벨의 선택을 못 읽음 = 사람이 고른 것이 없음
        cases = {}
    return {"mark": mark, "ins": ins, "n": n, "held": MR.held_ids(MR.overs(rec, gather), cases), "gather": gather}


def facts(doc_id):
    """워크플로우 상태의 재료 → {why, fill(마지막 반영 표식 시각 | None), applied{at, fill, counts} | None, inserted(넣은 블록 수)}. 문서 안 바뀜 · 분석 안 돌림."""
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        return {"why": "hwpx 문서가 아닙니다", "fill": None, "applied": None, "inserted": 0}
    R = _records(doc_id)
    f = R["mark"]
    a = load(doc_id).get("applied")
    return {"why": "" if f else NO_DRAFT if _form_write_doc(doc_id) else NO_FILL, "fill": (f or {}).get("at"), "inserted": R["n"],
            "applied": {"at": a.get("at"), "fill": a.get("fill"), "counts": a.get("counts") or {}} if a else None}


def _rows_view(rows):
    return [{**{k: r[k] for k in ("tpl", "no", "level", "letter", "kind", "rep", "lines", "form")}, **{k: len(r.get(k) or ()) for k in ("fix", "near", "own", "same", "held")}} for r in rows]


def _preview(doc, ov, ins, R):
    """오버레이 사본에 deep 레벨을 갈라 본 뒤의 계획 → (rows, cuts, left, 사본, held, relet) — 문서 · 오버레이 안 바뀜. R = _records(사람이 고른 넘친 줄 · 취합이면 「≈」 줄 없음).
    relet = 위 레벨과 같은 레터를 쓰는 넣은 레벨의 바꿀 레터(merge_retidy.reletter_of — 가른 뒤의 사본에서)."""
    sim = copy.deepcopy(ov)
    cuts, left = MR.cut_all(doc, sim, ins, R["held"])
    relet = MR.reletter_of(doc, sim, ins, R["held"]) if R.get("relet", True) else []
    P = MR.plan(doc, sim, ins, R["held"], near=not R["gather"])
    return P["rows"], cuts, left, sim, P["held"], relet


def _kept_level(r, gather):
    """취합에서 취합본의 줄이 있는 레벨인가(대표를 레벨의 대표로 삼는 form · user 묶음 · 그 레벨에 넣은 줄 밖의 줄이 있음) — 그 레벨은 확정 서식으로 다시 짓지 않는다(settle 안 함: 모듈 설명)."""
    return gather and r["slot"] and r["form"] > 0


def _full(doc, ov, r, m):
    """취합본의 줄이 있는 레벨(_kept_level)에서 넣은 줄에도 확정 서식의 ①②(묶음 빈칸 · 자리 규칙)를 거나 — 대표가 넣은 줄이거나 대표(취합본의 줄)가 이미 그것을 갖춤.
    아니면 대표의 모양 그대로만(넣은 줄에만 ①② 를 걸면 대표와 서식이 갈라져 다음 누름이 그 레벨을 「넣은 줄끼리」 로 읽고 떼어 낸다)."""
    from app import outline_conform as OC
    return r["rep"] in r["same"] or not OC.needs(doc, ov, r["rep"], m, fit=False)   # ①② 만 — 안 바꾸는 취합본 대표의 접두 줄 맞춤 값(③) 때문에 넣은 줄의 ①② 를 미루면 끝나지 않는다(2026-11-23 astra 재현)


def _todo(doc, ov, rows, m, gather=False):
    """바꿀 것이 있나 — 맞출 줄 · 같이 맞출 「≈」 줄 · 레벨의 대표를 바꿈 · 대표와 이미 같은 줄에 확정 서식(묶음 빈칸 · 자리 규칙)이 안 걸림(outline_conform.needs).
    취합에서 취합본의 줄이 있는 레벨은 넣은 줄에 ①② 를 걸 때(_full)만 그것을 본다."""
    from app import outline_conform as OC
    from app import outline_edit as OE
    for r in rows:
        if r["rep"] is None:
            continue
        if r["fix"] or r["near"] or (r["slot"] and (OE._slot(ov, r["tpl"], r["level"]) or {}).get("rep") != r["rep"]):
            return True
        if _kept_level(r, gather) and not _full(doc, ov, r, m):
            continue
        base = None if r["slot"] else r["rep"]   # 넣은 줄끼리 맞추는 레벨 — 접두의 줄 맞춤 값은 이 묶음의 대표 것(반영과 같은 본보기: outline_conform ③)
        if any(OC.needs(doc, ov, p, m, base) for p in r["same"]):
            return True
    return False


@router.get("/api/docs/{doc_id}/merge-retidy")
def retidy_get(doc_id: str):
    """지금 상태 + 계획(그래프가 마지막 반영 뒤의 것일 때만 — 아니면 stale: 반영이 먼저 다시 분석한다). 문서 안 바뀜."""
    from app import heading_runs, server
    s = server._sess(doc_id)
    out = {**facts(doc_id), "rev": s.rev, "stale": None, "rows": [], "cuts": [], "cutLeft": [], "letters": [], "counts": None}
    R = _records(doc_id)
    f = R["mark"]
    out["gather"] = R["gather"]
    if s.fmt != "hwpx" or not f:
        return out
    with s.lock:
        g = heading_runs.graph(s)
        stale = g is None or int(((g.get("meta") or {}).get("rev")) or 0) < int(f.get("rev") or 0)
        out["stale"] = stale
        if stale:
            return out
        ov = server._outline_ov(s)
        if ov is None:
            return out
        rows, cuts, left, _, held, relet = _preview(s.doc, ov, R["ins"](s.doc.blocks()), R)
    out.update(rows=_rows_view(rows), cuts=cuts, cutLeft=left, letters=MR.letters_view(relet), counts=MR.summary(rows, cuts, left, held, relet))
    return out


def _reanalyze(s, wid):
    """헤딩 2단계를 스크립트로 다시(넣은 줄이 템플릿에 들게) — 그 전 그래프가 LLM 을 거친 것이면 그 번호를 기록에 남긴다(llm_kept). → 새 실행 번호 | None."""
    from app import heading_runs
    before = heading_runs.graph(s)
    try:
        job = heading_runs.start(s, 2, False)
    except heading_runs.Busy as e:
        raise HTTPException(409, f"{e} — 끝난 뒤 다시 누르세요") from e
    t0 = time.time()
    while job.status == "running":
        if time.time() - t0 > WAIT_MAX:
            raise HTTPException(409, "헤딩을 다시 분석하는 데 너무 오래 걸립니다 — 「헤딩 추출」 탭에서 확인하세요")
        time.sleep(0.2)
    if job.status != "done":
        raise HTTPException(409, f"넣은 뒤 헤딩을 다시 분석하지 못했습니다 — {job.error or '실패'}")
    now = heading_runs.graph(s)
    run = ((now or {}).get("meta") or {}).get("run")
    rec = load(wid)
    was = ((before or {}).get("meta") or {}).get("run")
    old = rec.get("graph") or {}
    # 그 전 그래프가 LLM 을 거친 것 — 또는 그 전 그래프도 이 정리가 다시 분석한 것이고 그 앞이 LLM 이었으면 그것을 잇는다(두 번 넣고 두 번 정리해도 「거침」 이 남게)
    llm_run = was if _llm_done(before) else (old.get("llmRun") if old.get("run") == was else None)
    _save(wid, {**rec, "graph": {"run": run, "llmRun": llm_run, "at": time.time()}})
    return run


@router.post("/api/docs/{doc_id}/merge-retidy")
def retidy_post(doc_id: str, body: dict = Body(default={})):
    """넣은 줄을 목적 문서의 템플릿 · 서식으로(모듈 설명) → {done{counts, rows, cuts, cutLeft}, reanalyzed, …편집 상태} | {nothing: true, why, …}.
    반영 = 편집 하나(실행 취소 1 · 기록 `mergeRetidy`): ① deep 레벨을 서식 종속 템플릿으로 가름(merge_retidy.cut_all — 오버레이만) ② 레벨의 대표로 삼는 묶음(form · grown · cut · user)은 그 대표를 레벨의 대표로 두고
    확정 서식(outline_conform.settle — 맞출 줄 + 「≈」 줄 · 대표 갈래에 묶음 빈칸 · 자리 규칙), 못 가른 deep 은 레벨의 대표(목적 문서의 줄)와 그 갈래는 건드리지 않고 넣은 줄의 대표에 맞춘다
    (outline_conform.conform · place). 넣는 쪽의 서식을 받는 레벨(merge_retidy.KEEP)은 줄마다 본문 강조를 지킨다. 표준 검사는 다른 편집과 같다(닿은 문단만 — server._edit).
    취합이면 취합본의 줄이 있는 레벨은 settle 하지 않고 넣은 줄만 맞추며, 반영 뒤 넣은 기록의 지문을 다시 적는다(모듈 설명 「취합에서 달라지는 것」)."""
    from app import heading_runs, server
    from app import merge_collect_api as MCA
    from app import outline_conform as OC
    from app import outline_edit as OE
    from app import outline_match as OM
    from app import outline_pos as OP
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    exp = body.get("expectRev")
    if exp is not None and exp != s.rev:
        raise HTTPException(409, "본 뒤 문서가 바뀌었습니다 — 다시 읽으세요")
    R = _records(doc_id)
    f = R["mark"]
    if not f:
        raise HTTPException(409, NO_DRAFT if _form_write_doc(doc_id) else NO_FILL)
    g = heading_runs.graph(s)
    again = g is None or int(((g.get("meta") or {}).get("rev")) or 0) < int(f.get("rev") or 0)
    if again:
        _reanalyze(s, doc_id)
    matched = set()
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 그래프가 없습니다 — 헤딩 추출 2단계를 먼저 하세요")
        rows0, cuts0, left0, sim, held0, relet0 = _preview(s.doc, ov, R["ins"](s.doc.blocks()), R)   # 갈라 본 뒤의 계획(사본 — 반영은 아래 트랜잭션 안에서 다시)
        rev, run = s.rev, (ov.get("run") or [None])[0]
        todo = bool(cuts0) or any(r["now"] for r in relet0) or _todo(s.doc, sim, rows0, OP.Measure(s.doc), R["gather"])
        if R["gather"] and todo:   # 취합 — 정리 전에 지문이 맞던 본문 넣은 기록(반영 뒤 그것만 다시 적는다: 넣은 뒤 사람이 고친 기록은 「바뀜」 신호로 남김)
            from app import merge_gather_api as GA
            matched = GA.fp_matches(doc_id, s.doc.blocks())
        led = MCA.led_matches(s) if todo and MCA.is_collect(((works.work(doc_id) or {}).get("task") or {}).get("job") or "") else None   # 같은 양식 취합 — 정리 전에 「넣은 글」 과 같던 원장 줄(정리 뒤 그것만 다시 적는다: spec_취합 ② §10-4)
    counts = MR.summary(rows0, cuts0, left0, held0, relet0)
    done = {"changed": [], "left": [], "reps": 0, "cuts": cuts0, "cutLeft": left0, "rows": rows0, "held": held0, "relet": relet0}

    def make(s_):
        if s_.rev != rev:
            raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 다시 누르세요")
        ov2 = server._outline_ov(s_)
        R2 = _records(doc_id)
        ins2, keep2, near2, gather = R2["ins"](s_.doc.blocks()), R2["held"], not R2["gather"], R2["gather"]
        rows = MR.plan(s_.doc, ov2, ins2, keep2, near2)["rows"]
        # 닿는 줄 — 가르기 전의 계획으로(가른 뒤의 서식 종속 템플릿 줄은 모두 지금 그 템플릿의 줄이다)
        tids = list(dict.fromkeys(r["tpl"] for r in rows if r["rep"] is not None))
        hit = list(dict.fromkeys([p for r in rows if r["rep"] is not None for p in [r["rep"], *r["fix"], *r["near"], *r["same"], *r["own"]]] + OC.lines_of(s_.doc, ov2, tids)))
        if not hit:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 누르세요")

        def run_():
            changed, left = [], []
            cuts, left_cut = MR.cut_all(s_.doc, ov2, ins2, keep2)   # ① deep 레벨을 서식 종속 템플릿으로(오버레이만 — 같은 트랜잭션: 실행 취소 1)
            relet = MR.reletter_of(s_.doc, ov2, ins2, keep2) if R2.get("relet", True) else []   # ①-1 위 레벨과 같은 레터를 쓰는 넣은 레벨 — 레터 글자만 바꾼다(문서 · 오버레이 — spec_병합 ② §5-9 11)
            changed += MR.reletter(s_.doc, ov2, relet, left)
            m = OP.Measure(s_.doc)                                   # 레터를 바꾼 뒤에 잰다(접두 폭)
            P = MR.plan(s_.doc, ov2, ins2, keep2, near2)             # ② 가른 뒤의 계획 — 뗀 템플릿의 레벨은 넣은 줄만이라 cut
            rows = P["rows"]
            done.update(cuts=cuts, cutLeft=left_cut, rows=rows, held=P["held"], relet=relet)
            for r in rows:
                if r["rep"] is None:
                    continue
                keep = OM.EMPH if r["kind"] in MR.KEEP else None   # 넣는 쪽의 서식을 받는 레벨 — 줄마다 본문 강조는 그 줄의 것(merge_retidy 설명)
                if r["slot"] and not _kept_level(r, gather):   # 이 묶음의 대표가 레벨의 대표 — 확정 서식으로(대표 · 맞출 줄 · 「≈」 줄 · 대표 갈래)
                    if (OE._slot(ov2, r["tpl"], r["level"]) or {}).get("rep") != r["rep"]:
                        OM.set_rep(s_.doc, ov2, r["tpl"], r["level"], r["rep"], by="agent")   # 잠그지 않는다(서식 정리 계획이 다시 고를 수 있게 — 사람이 정한 대표가 아니다)
                        done["reps"] += 1
                    changed += OC.settle(s_.doc, ov2, r["tpl"], r["level"], r["fix"] + r["near"], m, left, keep, skip=r["held"])   # 사람이 처리를 고른 넘친 줄은 대표 갈래여도 안 건드린다
                    if keep:   # 강조만 다른 줄(대표 갈래가 아니라 settle 이 안 거는 줄)에도 묶음 빈칸 · 자리 규칙
                        changed += [p for p in r["same"] if p != r["rep"] and OC.place(s_.doc, ov2, p, m)]
                elif r["slot"]:   # 취합 — 취합본의 줄이 있는 레벨: 대표는 오버레이만 정하고 넣은 줄만 그 모양으로(취합본의 줄은 안 바꾼다 — 뒤에 올 기관 문서가 그 줄의 글로 자리를 찾는다)
                    if (OE._slot(ov2, r["tpl"], r["level"]) or {}).get("rep") != r["rep"]:
                        OM.set_rep(s_.doc, ov2, r["tpl"], r["level"], r["rep"], by="agent")
                        done["reps"] += 1
                    full = _full(s_.doc, ov2, r, m)   # 넣은 줄에도 ①② — 대표가 넣은 줄이거나 이미 그것을 갖춘 취합본의 줄일 때만
                    placed = r["rep"] in r["same"] and OC.place(s_.doc, ov2, r["rep"], m)
                    sh = OM.rep_shape(s_.doc, ov2, r["rep"])
                    if placed:   # 대표(넣은 줄)에 ①② 를 걸었다 — 슬롯의 동결 모양도 그것으로(Enter 로 만드는 새 줄이 같은 서식: settle 과 같다 · set_rep 은 걸기 전 모양을 얼렸다)
                        changed.append(r["rep"])
                        OC.freeze(ov2, r["tpl"], r["level"], sh)
                    for p in r["fix"]:   # full 이 아니면 대표의 모양 그대로(접두 · 문단 · 레터 글자 · 본문 바탕 글자 — 묶음 빈칸 · 자리 규칙은 대표가 갖추지 않았다: 역변환 스크립트의 rules=False)
                        OC.conform(s_.doc, ov2, p, sh, m, left, keep, rules=full)
                        changed.append(p)
                    if full:
                        changed += [p for p in r["same"] if p != r["rep"] and OC.place(s_.doc, ov2, p, m)]
                else:   # 넣은 줄끼리 — 레벨의 대표(목적 문서의 줄)와 그 갈래는 그대로 · 접두의 줄 맞춤 값도 이 묶음의 대표 것(base — 목적 문서 줄의 값을 받지 않는다: outline_conform ③)
                    if OC.place(s_.doc, ov2, r["rep"], m, r["rep"]):
                        changed.append(r["rep"])
                    sh = OM.rep_shape(s_.doc, ov2, r["rep"])
                    for p in r["fix"]:
                        OC.conform(s_.doc, ov2, p, sh, m, left, keep, base=r["rep"])
                        changed.append(p)
                    changed += [p for p in r["same"] if p != r["rep"] and OC.place(s_.doc, ov2, p, m, r["rep"])]
            MR.mark(ov2, rows)   # ③ 넣은 줄끼리 맞춘 레벨의 표 — 다음 누름이 그 레벨을 form 으로 바꾸지 않게(오버레이만)
            done["changed"], done["left"] = list(dict.fromkeys(changed)), left
            if led:   # 원장의 「넣은 글」 을 정리 뒤의 글로(레터를 바꾼 줄 — 수정본 반영이 「사람이 고친 자리」 로 보지 않게) · 이 편집 안에서: 실행 취소하면 원장도 함께 돌아간다
                MCA.led_refit(s_, led)
            seen = list(dict.fromkeys(hit + done["changed"]))
            return {"hosts": [s_.doc._ids[i] for i in seen], "formatted": set(done["changed"]), "struct": set(), "origin": {}, "anchor": seen[0],
                    "log": {**{k: counts[k] for k in ("levels", "grown", "deep", "fix", "near", "own", "cut", "cutLines", "held")}, "letters": sum(1 for r in done["relet"] if r["now"]), "changed": len(done["changed"]), "reanalyzed": again,
                            **({"gather": True} if gather else {})}}
        return [s_.doc._ids[i] for i in hit], run_
    out = server._edit(doc_id, make, "mergeRetidy", {"levels": counts["levels"]}) if todo else None
    if out is not None and not isinstance(out, dict):
        return out   # 표준 검사가 되돌림(422 응답 그대로)
    if out is not None:
        with s.lock:   # 이 편집의 실행 취소 묶음에 표 — 그것으로 실행 취소하면 정리 기록을 내린다(_on_bump)
            _tag_undo(s, out.get("rev"))
    if out is not None and matched:   # 취합 — 정리 전에 맞던 본문 넣은 기록의 지문을 지금 문서로(다음 판정이 「이미 들어 있음」 으로 보게 — spec_병합 ② §5-9 9 ⓑ)
        from app import merge_gather_api as GA
        with s.lock:   # 정리의 편집 뒤 다른 편집이 끼었으면(울타리 밖에서 손으로 누른 때 — 다른 탭의 글 고침) 다시 적지 않는다: 사람이 고친 글까지 지문에 넣으면 「바뀜」 신호가 없어진다
            if s.rev == out.get("rev"):
                GA.refit_fp(doc_id, s.doc.blocks(), matched)
            else:
                log.warning("[넣은 뒤 정리] %s: 정리 뒤 다른 편집이 끼어(rev %s → %s) 넣은 기록 %d개의 지문을 다시 적지 않았습니다 — 그 기관 문서의 판정이 「겹침」 으로 보일 수 있습니다",
                            doc_id, out.get("rev"), s.rev, len(matched))
    counts = {**MR.summary(done["rows"], done["cuts"], done["cutLeft"], done["held"], done["relet"]), "changed": len(done["changed"]), "reps": done["reps"], "left": len(done["left"])}
    applied = {"at": time.time(), "fill": f.get("at"), "rev": s.rev, "run": run, "counts": counts, "rows": _rows_view(done["rows"]), "cuts": done["cuts"], "cutLeft": done["cutLeft"],
               "letters": MR.letters_view(done["relet"])}
    _save(doc_id, {**load(doc_id), "applied": applied})
    if out is None:
        return {"nothing": True, "why": "맞출 줄이 없습니다 — 넣은 줄이 이미 목적 문서의 템플릿 · 서식입니다" if rows0
                else "넣은 개요 줄은 모두 사람이 넘친 레벨의 처리를 고른 줄입니다 — 그대로 둡니다" if held0 else "넣은 개요 줄이 없습니다",
                "done": {"counts": counts, "rows": applied["rows"], "cuts": applied["cuts"], "cutLeft": applied["cutLeft"], "letters": applied["letters"]}, "reanalyzed": again, **s.state()}
    return {**out, "done": {"counts": counts, "rows": applied["rows"], "cuts": applied["cuts"], "cutLeft": applied["cutLeft"], "letters": applied["letters"]}, "reanalyzed": again}


# ---- 문서가 정리 전 상태로 돌아가면 정리 기록을 내린다(spec_병합 ② §5-9 10 「다시 반영 · 복원」) ----
UNDO_TAG = "retidyUndo"   # 정리 편집의 실행 취소 묶음(오버레이 사본)에 다는 표 — 그 묶음으로 실행 취소하면 오버레이가 이 표를 지닌 채 돌아온다
RESTORE_OPS = ("restore", "discard")   # 문서를 확정 상태로 바꾸는 편집(server.commit_restore — 「이 확정으로 복원」 · 「모두 되돌리기」)


def _tag_undo(s, rev):
    """정리 편집이 쌓은 실행 취소 묶음(맨 위 — 그 뒤 다른 편집이 없을 때만)의 오버레이 사본에 표를 단다(세션 잠금 안)."""
    snap = s.undo[-1] if rev is not None and s.rev == rev and s.undo else None
    ov = snap.get("outline") if isinstance(snap, dict) else None
    if isinstance(ov, dict):
        ov[UNDO_TAG] = True


def _commit_at(wid, n):
    """확정 n 을 만든 때(초) | None(올린 원본 · 모르는 확정)."""
    if not n:
        return None
    try:
        return float((works.commit(wid, n) or {}).get("at"))
    except (TypeError, ValueError):
        return None


def _on_bump(s, kind, fields):
    """편집 알림(server.BUMPED — 세션 잠금 안 · 어떤 오류도 편집을 막지 않는다): 문서가 정리 전 상태로 돌아가면 정리 기록(`retidy.json` applied)을 내린다 — 줄이 다시 「할 차례」.
    ① 실행 취소가 정리 편집을 되돌림(_tag_undo 의 표가 오버레이로 돌아옴) ② 복원 · 모두 되돌리기로 간 확정이 그 정리 전에 만든 것(올린 원본 · 모르는 확정도) —
    정리 뒤에 만든 확정이면 정리가 든 문서라 그대로 둔다(정리 기록이 있는 동안 문서는 정리가 든 상태다: 그것을 빼는 길은 모두 여기서 기록을 내린다). 내린 기록은 `dropped` 에 남긴다."""
    try:
        if kind == "undo":
            ov = s.outline
            if not (isinstance(ov, dict) and ov.pop(UNDO_TAG, None)):
                return
        elif kind not in RESTORE_OPS:
            return
        rec = load(s.id)
        a = rec.get("applied")
        if not a:
            return
        if kind in RESTORE_OPS:
            at = _commit_at(s.id, (fields or {}).get("of" if kind == "restore" else "base"))
            if at is not None and at > float(a.get("at") or 0):
                return
        _save(s.id, {**rec, "applied": None, "dropped": {"at": time.time(), "by": kind, "applied": a.get("at"), "fill": a.get("fill")}})
        log.info("[넣은 뒤 정리] %s: %s 로 정리 전 상태가 되어 정리 기록을 내렸습니다(다시 할 차례)", s.id, kind)
    except Exception as e:  # noqa: BLE001
        log.warning("[넣은 뒤 정리] %s: %s 뒤 정리 기록을 내리지 못했습니다: %r", s.id, kind, e)


from app import server as _server  # noqa: E402 — 편집 알림을 듣는다(server 가 이 파일의 끝점을 싣는다 — 어느 쪽이 먼저 읽혀도 한 번만)

if _on_bump not in _server.BUMPED:
    _server.BUMPED.append(_on_bump)
