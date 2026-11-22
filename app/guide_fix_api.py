"""지침 보정 끝점(spec_워크플로우 ② §18-23 「지침 보정」) — 자료 · 프롬프트 · 답 검증은 `app/guide_fix.py`. hwpx 문서만 · 어느 워크플로우의 문서에서나.

- `GET /api/docs/{id}/guide-fix` → 저장한 것(마지막 물음 · 마지막 반영)과 지금 지침 수. 문서 안 바뀜.
- `POST …/guide-fix/ask` → 지금 문서의 자리를 떠서(세션 잠금 안) **잠금 밖에서** LLM 에 묻고(유료 · 수십 초) 검증한 고침을 계획으로 저장 → {planId, fixes, left, rejected, units, asked}. 문서 안 바뀜.
- `POST …/guide-fix/apply {planId}` → 그 계획의 고침을 한 번에(구조 편집 트랜잭션 하나 — 실행 취소 1 · 기록 `guideFix`). 물은 뒤 글이 바뀐 문단은 건너뛴다(`skipped`). 고칠 것이 없어도 반영 기록은 남긴다(검토는 끝남).
  409 = 그 계획이 지금 계획이 아님.
- 저장 = 작업 폴더 `guidefix.json` {version, plan{planId, at, rev, fixes, left, rejected, units[{keys, where, error}], asked, guide, job} | None, applied{at, planId, rev, fill(그때의 「내용 넣기」 반영 표식 시각 | None), done[{id, where, old, new, rule, why}], skipped[…], left[…]} | None}
  · 마지막 호출의 프롬프트 · 답 = `guidefix_last.json`(화면의 「지침」 보기 · 찾아보기용)."""
import logging
import time
import uuid
from collections import Counter

from fastapi import APIRouter, Body, HTTPException

from app import guide_fix, works
from app.division_profiles import _structure as structure

router = APIRouter()
log = logging.getLogger("uvicorn.error")
FILE, LAST = "guidefix.json", "guidefix_last.json"
VERSION = 1


def _path(wid, name=FILE):
    f = works.folder(wid)
    return f / name if f is not None and (f / "work.json").is_file() else None


def load(wid):
    """저장한 것 {version, plan, applied} | 빈 것(없음 · 못 읽음 · 작업 저장 끔)."""
    p = _path(wid)
    got = works._read_json(p) if p is not None and p.is_file() else None
    return got if isinstance(got, dict) and got.get("version") == VERSION else {"version": VERSION, "plan": None, "applied": None}


def _save(wid, data, name=FILE):
    p = _path(wid, name)
    if p is not None:
        works._write_json(p, data)


def _fill_at(wid):
    """그 문서의 「내용 넣기」 마지막 반영 표식 시각 | None(merge.json `filled.at` — 넣은 뒤 다시 넣으면 보정을 다시 한다)."""
    try:
        from app import merge_api
        return ((merge_api._store(wid) or {}).get("filled") or {}).get("at")
    except Exception:   # noqa: BLE001 — 목적 문서가 아니거나 넣은 기록이 없음
        return None


def _saved_guides(s):
    """(세션 잠금 안) 저장한 작성 지침 — 없으면 지금 문서에서 한 번 모아 저장(form_guides_api.keep). 못 모으면 None."""
    from app import form_guides_api
    got = form_guides_api.load(s.id)
    if got is None:
        try:
            got, _ = form_guides_api.keep(s)
        except Exception:   # noqa: BLE001 — 못 모으면 지침 없음으로
            log.exception("[지침 보정] 작성 지침을 모으지 못했습니다")
            got = None
    return got


def _counts(saved):
    from app import form_guides
    g = form_guides.groups(saved or {})
    n = lambda xs: sum(1 for x in xs if any((i.get("text") or "").strip() for i in x["items"] + x["marks"]))  # noqa: E731
    return {"headings": n(g["headings"]), "tables": n(g["tables"]), "total": n(g["headings"]) + n(g["tables"])}


def facts(doc_id):
    """워크플로우 상태의 재료 → {guides{headings, tables, total}, plan{at, fixes, left, rejected, asked} | None, applied{at, fill, done, skipped, left} | None, fill(지금 반영 표식 시각 | None), why}. 문서 안 바뀜 · LLM 안 부름."""
    from app import form_guides_api, server
    s = server._sess(doc_id)
    with s.lock:
        if s.fmt != "hwpx":
            return {"guides": {"headings": 0, "tables": 0, "total": 0}, "plan": None, "applied": None, "fill": None, "why": "hwpx 문서가 아닙니다"}
        saved = form_guides_api.load(s.id)
    rec = load(doc_id)
    p, a = rec.get("plan"), rec.get("applied")
    return {"guides": _counts(saved), "saved": saved is not None,
            "plan": {"at": p.get("at"), "planId": p.get("planId"), "fixes": len(p.get("fixes") or ()), "left": len(p.get("left") or ()), "rejected": len(p.get("rejected") or ()), "asked": p.get("asked")} if p else None,
            "applied": {"at": a.get("at"), "fill": a.get("fill"), "done": len(a.get("done") or ()), "skipped": len(a.get("skipped") or ()), "left": len(a.get("left") or ())} if a else None,
            "fill": _fill_at(doc_id), "why": ""}


@router.get("/api/docs/{doc_id}/guide-fix")
def guide_fix_get(doc_id: str):
    """저장한 것 {plan, applied} + 지금 지침 수 · 「지침」 보기 글(parts). 문서 안 바뀜."""
    from app import job_prompts
    rec = load(doc_id)
    f = facts(doc_id)
    return {**rec, "guides": f["guides"], "fill": f["fill"], "parts": guide_fix.parts(job_prompts.for_work(doc_id))}


@router.post("/api/docs/{doc_id}/guide-fix/ask")
def guide_fix_ask(doc_id: str):
    """지금 문서의 자리마다 작성 지침과 지금 글을 LLM 에 묻고(유료) 검증한 고침을 계획으로 저장 → {planId, rev, fixes, left, rejected, units[{keys, where, error}], asked} | {nothing, why}.
    문서는 안 바뀐다 — 반영은 POST …/guide-fix/apply."""
    from app import form_cleanup, heading_runs, job_prompts, server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    with s.lock:
        saved = _saved_guides(s)
        blocks, rev = s.doc.blocks(), s.rev
        us, ctx = guide_fix.units(blocks, heading_runs.graph(s), saved, form_cleanup.find(s.doc)) if saved else ([], {})
    if not us:
        why = "저장한 작성 지침이 없습니다" if not saved else "지침이 붙은 자리에 넣은 글이 없습니다"
        rec = load(doc_id)
        _save(doc_id, {**rec, "plan": {"planId": uuid.uuid4().hex[:12], "at": time.time(), "rev": rev, "fixes": [], "left": [], "rejected": [], "units": [], "asked": 0, "nothing": why}})
        return {"nothing": True, "why": why, "planId": load(doc_id)["plan"]["planId"], "rev": rev, "fixes": [], "left": [], "rejected": [], "units": [], "asked": 0}
    res = guide_fix.ask({"units": us, "ctx": ctx}, job_prompts.for_work(doc_id))   # 잠금 밖 — 뜬 것만 쓴다
    if res["asked"] and all(u.get("error") for u in res["units"]):
        raise HTTPException(503, f"LLM 이 답을 내지 못했습니다 — {res['units'][0].get('error')}")
    plan = {"planId": uuid.uuid4().hex[:12], "at": time.time(), "rev": rev, "fixes": res["fixes"], "left": res["left"], "rejected": res["rejected"], "asked": res["asked"],
            "units": [{"keys": u["keys"], "where": u["where"], "error": u.get("error")} for u in res["units"]], "guide": res.get("guide"), "job": res.get("job")}
    rec = load(doc_id)
    _save(doc_id, {**rec, "plan": plan})
    _save(doc_id, {"at": plan["at"], "units": [{k: u.get(k) for k in ("n", "keys", "where", "error", "prompt", "answer")} for u in res["units"]]}, LAST)
    return {k: plan[k] for k in ("planId", "rev", "fixes", "left", "rejected", "units", "asked")}


@router.post("/api/docs/{doc_id}/guide-fix/apply")
def guide_fix_apply(doc_id: str, body: dict = Body(default={})):
    """{planId} → 그 계획의 고침을 한 번에 반영(실행 취소 1 · 기록 `guideFix`) → {done[…], skipped[…], …편집 상태} | {nothing: true}(고칠 것이 없음 — 반영 기록은 남김). 409 = 지금 계획이 아님."""
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    rec = load(doc_id)
    plan = rec.get("plan")
    if not plan or plan.get("planId") != body.get("planId"):
        raise HTTPException(409, "그 보정 계획은 지금 계획이 아닙니다 — 다시 물으세요")
    fill = _fill_at(doc_id)
    with s.lock:
        texts = {b["id"]: b.get("text") or "" for b in structure.iter_blocks(s.doc.blocks()) if b.get("type") == "paragraph"}
        todo, skipped = [], []
        for f in plan.get("fixes") or ():
            if texts.get(f["id"]) != f["old"]:
                skipped.append({**f, "skip": "물은 뒤 그 문단의 글이 바뀌었습니다" if f["id"] in texts else "그 문단이 문서에 없습니다"})
            else:
                todo.append(f)
        applied = {"at": time.time(), "planId": plan["planId"], "rev": s.rev, "fill": fill, "done": todo, "skipped": skipped, "left": plan.get("left") or []}
        if not todo:
            _save(doc_id, {**rec, "applied": applied})
            return {"nothing": True, "done": [], "skipped": skipped, **s.state()}
        chk = s.kit["check"]
        pre = chk.counts(chk.check_doc(s.doc))

        def run():
            for f in todo:
                s.doc.set_text(f["id"], f["new"])
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None, "log": {"fixed": len(todo), "skipped": len(skipped)}}

        def check(s_, out, base, header):
            return chk.verdict(s_.doc, {"schema": Counter(base["schema"]) | pre["schema"], "rules": Counter(base["rules"]) | pre["rules"]}, chk.check_doc(s_.doc))
        out, after = server._transact(s, run, "guideFix", req={"planId": plan["planId"], "fixes": len(todo)}, check=check)
        if after is None:
            return out
        applied["rev"] = s.rev
        _save(doc_id, {**load(doc_id), "applied": applied})
        return {"done": todo, "skipped": skipped, **s.state()}
