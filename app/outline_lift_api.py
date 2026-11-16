"""표 제목을 템플릿의 L1 으로 API(spec_hwpx_웹편집 ② §8-7) — 후보 보기(GET …/outline/lift) · 넣기(POST …/outline/lift) · 떼기(POST …/outline/unlift).
server.py 가 include 한다. 후보·넣기·떼기는 `app/outline_lift.py`, 트랜잭션은 템플릿 종속(`outline_match_api`)과 같은 틀 — 문서는 안 바뀌고 오버레이만(실행 취소 1 · 기록 `outlineLift`·`outlineUnlift`)."""
from fastapi import APIRouter, Body, HTTPException

from app import outline_lift, outline_pos
from app.outline_match_api import _hwpx, _model_only, _ov, _server, _state, _tid

router = APIRouter()


def _tpl(ov, tid):
    t = ov["templates"].get(tid)
    if t is None:
        raise HTTPException(404, "그 템플릿이 없습니다")
    return t


@router.get("/api/docs/{doc_id}/outline/lift")
def lift_candidates(doc_id: str, tpl: str):
    """템플릿 tpl 의 첫 레벨 줄 바로 위에 있는 1칸 제목 표 → {tpl, no, lifted(이미 넣은 표 줄 수), first(그 줄들의 지금 레벨), blocked(못 넣는 까닭 | null),
    groups[{sig, count, lifted, look{font, sizePt, bold}, tables[{table, para, text, under}]}], rev}. 문서·오버레이는 안 바뀐다. 404 템플릿 없음 · 409 2단계 결과 없음."""
    server = _server()
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)
        tid = _tid(tpl, "tpl")
        t = _tpl(ov, tid)
        n = sum(1 for x in ov["lines"].values() if x["tpl"] == tid and x.get("role") == outline_lift.ROLE)
        return {"tpl": tid, "no": t["no"], "lifted": n, "first": outline_lift._first_level(t), "blocked": outline_lift._blocked(ov, tid),
                "groups": outline_lift.candidates(s.doc, ov, tid), "rev": s.rev}


@router.post("/api/docs/{doc_id}/outline/lift")
def lift(doc_id: str, body: dict = Body(...)):
    """{tpl, sig?(표의 꼴 — 없으면 표가 가장 많은 꼴)} — 그 꼴의 제목 표를 **모두** 템플릿의 L1 로: 템플릿의 레벨을 한 칸 밀고(처음 넣을 때) 표 줄을 L1 에 둔다. 문서는 안 바뀐다 · 실행 취소 1.
    → {lifted{tid, no, sig, tables, paras, adopted, levels}, outline(GET …/outline 과 같은 꼴), …편집 상태}. 400 넣을 표 없음·종속 템플릿이 걸림 · 404 템플릿 없음 · 409 2단계 결과 없음."""
    server = _server()
    tid, sig = _tid(body.get("tpl"), "tpl"), body.get("sig")
    if sig is not None and not isinstance(sig, str):
        raise HTTPException(400, "sig 는 글")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)
        _tpl(ov, tid)
        got, ok = _model_only(server, s, "outlineLift", {"tpl": tid, "sig": sig}, lambda: outline_lift.lift(s.doc, ov, tid, sig))
        if not ok:
            return got
        return {"lifted": got, "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/unlift")
def unlift(doc_id: str, body: dict = Body(...)):
    """{tpl} — L1 로 넣은 표 줄을 모두 빼고 템플릿의 레벨을 되돌린다(그 아래 줄의 부모도 넣기 전으로). 문서는 안 바뀐다 · 실행 취소 1.
    → {unlifted{tpl, no, tables}, outline, …편집 상태}. 400 넣은 표 없음·종속 템플릿이 걸림 · 404 템플릿 없음 · 409 2단계 결과 없음."""
    server = _server()
    tid = _tid(body.get("tpl"), "tpl")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)
        t = _tpl(ov, tid)
        got, ok = _model_only(server, s, "outlineUnlift", {"tpl": tid}, lambda: {"tpl": tid, "no": t["no"], "tables": outline_lift.unlift(ov, tid)})
        if not ok:
            return got
        return {"unlifted": got, "outline": outline_pos.view(s.doc, s.outline), **_state(s)}
