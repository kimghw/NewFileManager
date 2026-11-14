"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속 API(spec_hwpx_웹편집 ② §8-2) — server.py 가 include 한다(`outline_format_api` 와 같은 꼴).
계산은 `app/outline_match.py`, 오버레이는 `server._outline_ov`, 트랜잭션은 `server._transact`·`server._edit`(실행 취소 1 · 기록)."""
from fastapi import APIRouter, Body, HTTPException

from app import outline_edit, outline_match, outline_pos

router = APIRouter()


def _server():
    from app import server  # 세션·트랜잭션은 server 것 — 부를 때 가져온다(순환 import 피함)
    return server


def _hwpx(s):
    if s.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")


def _ov(server, s):
    ov = server._outline_ov(s)
    if ov is None:
        raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
    return ov


def _state(s):
    edited = s.edited()
    return {"edited": sorted(edited), "original": {i: s.orig_texts.get(i, "") for i in edited}, **s.state()}


def _model_only(server, s, op, req, change):
    """문서를 안 바꾸는 오버레이 변경(대표 정하기 · 넣기 · 떼기)을 트랜잭션 하나로 — 실행 취소 묶음에 오버레이가 들어 되돌릴 수 있고 기록에 한 줄.
    change() -> 기록에 더할 것(dict). 그 안의 ValueError·KeyError 는 400(오버레이는 바꾸기 전에 다 검사한다)."""
    got = {}

    def run():
        got.update(change() or {})
        return {"hosts": [], "formatted": set(), "struct": set(), "origin": {}, "anchor": None, "log": dict(got)}
    out, after = server._transact(s, run, op, req=req, local=[])
    return (out, None) if after is None else (got, True)


@router.get("/api/docs/{doc_id}/outline/formats")
def formats(doc_id: str):
    """모든 템플릿 레벨의 서식 갈래 → {rev, keys[[키, 이름]…](비교 값 차례), slots: {tpl: {레벨: {total, rep, repMissing, others, groups[{key, count, paras, more, rep, look, raw, diff}]}}}}.
    2단계 결과가 없거나 docx 면 {off: true}."""
    server = _server()
    s = server._sess(doc_id)
    with s.lock:
        ov = server._outline_ov(s) if s.fmt == "hwpx" else None
        if ov is None:
            return {"off": True, "rev": s.rev, "slots": {}}
        return {"rev": s.rev, "slots": outline_match.all_variants(s.doc, ov),
                "keys": [[k, outline_match.LABELS.get(k, k)] for k in outline_match.KEYS]}  # 비교 값의 차례·이름(화면 「서식 비교」 표의 열)


@router.put("/api/docs/{doc_id}/outline/slots/{tpl}/{level}/rep")
def set_rep(doc_id: str, tpl: str, level: int, body: dict = Body(...)):
    """{para} — 그 레벨의 대표를 그 줄로(오버레이 슬롯의 rep · 동결 접두·모양). 문서는 안 바뀐다 · 실행 취소 1(기록 `outlineRep`).
    → {slot: 그 레벨의 서식 갈래, outline(GET /outline 꼴), …편집 상태}. 400 그 레벨 줄이 아님 · 404 그런 레벨 없음 · 409 2단계 없음."""
    server = _server()
    pid = body.get("para")
    if not isinstance(pid, str) or not pid:
        raise HTTPException(400, "para(문단 id)가 필요합니다")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")

        def change():
            was = (outline_edit._slot(ov, tpl, level) or {}).get("rep")
            outline_match.set_rep(s.doc, ov, tpl, level, pid)
            return {"tpl": ov["templates"][str(tpl)]["no"], "level": level, "rep": pid, "was": was}
        out, ok = _model_only(server, s, "outlineRep", {"tpl": tpl, "level": level, "para": pid}, change)
        if not ok:
            return out
        return {"slot": outline_match.variants(s.doc, s.outline, tpl, level), "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/slots/{tpl}/{level}/match")
def match(doc_id: str, tpl: str, level: int, body: dict = Body(default={})):
    """{paras?, like?} — 그 레벨에서 대표와 비교 값이 다른 줄(paras 를 주면 그 가운데 그 레벨 줄만 · like(그 레벨 줄 id)를 주면 그 줄과 서식이 같은 갈래만 — 30줄 넘는 갈래도)을
    대표의 지금 모양으로(접두 · 문단 모양 · 레터·본문 바탕 글자 모양).
    구조 편집 트랜잭션 하나(기록 `outlineMatch` · 실행 취소 1 · 닿은 문단 검사). 응답 = 다른 구조 편집과 같은 꼴 + changed · outline{lines}.
    맞출 줄이 없으면 편집을 열지 않고 {changed: [], nothing: true, …편집 상태}. 400 대표가 문서에 없음 · 404 그런 레벨 없음 · 409 2단계 없음."""
    server = _server()
    paras, like = body.get("paras"), body.get("like")
    if paras is not None and (not isinstance(paras, list) or not all(isinstance(p, str) for p in paras)):
        raise HTTPException(400, "paras 는 문단 id 목록")
    if like is not None and (not isinstance(like, str) or not like):
        raise HTTPException(400, "like 는 문단 id")
    s0 = server._sess(doc_id)
    _hwpx(s0)
    with s0.lock:
        ov = _ov(server, s0)
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")
        try:
            pre = outline_match.match_targets(s0.doc, ov, tpl, level, paras, like)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not pre:
            return {"changed": [], "nothing": True, **_state(s0)}
    extra, changed = {}, []

    def make(s):
        ov2 = _ov(server, s)
        try:
            ids = outline_match.match_targets(s.doc, ov2, tpl, level, paras, like)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not ids:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 읽어 주세요")
        sl = outline_edit._slot(ov2, tpl, level)

        def run():
            sh = outline_match.rep_shape(s.doc, ov2, sl["rep"])
            sl.update(prefix=sh["prefix"], letter=sh["tok"], attrs=sh["attrs"], bodyChar=sh["body"])  # 새 줄도 대표의 지금 모양으로
            meas = outline_pos.Measure(s.doc) if (sl.get("pos") or {}).get("set") else None
            for pid in ids:
                outline_match.match_one(s.doc, ov2, pid, sh)
                if meas is not None:  # 사람이 정한 자리 규칙(② §8-1)도 다시
                    try:
                        outline_pos.align(s.doc, ov2, pid, full=True, measure=meas)
                    except ValueError:
                        pass
                changed.append(pid)
            extra.update({"lines": {pid: outline_edit.line_view(ov2["lines"][pid]) for pid in ids}, "removed": []})
            return {"hosts": [s.doc._ids[i] for i in ids], "formatted": set(ids), "struct": set(), "origin": {}, "anchor": ids[0],
                    "log": {"tpl": ov2["templates"][str(tpl)]["no"], "level": level, "rep": sl["rep"], "changed": len(ids)}}
        return [s.doc._ids[i] for i in ids], run
    out = server._edit(doc_id, make, "outlineMatch", {"tpl": tpl, "level": level, "paras": paras, "like": like})
    if isinstance(out, dict):
        out["outline"] = extra
        out["changed"] = changed
    return out


def _tid(v, what):
    if isinstance(v, bool) or not isinstance(v, (str, int)) or str(v) == "":
        raise HTTPException(400, f"{what}(템플릿 id)가 필요합니다")
    return str(v)


@router.post("/api/docs/{doc_id}/outline/merge")
def merge(doc_id: str, body: dict = Body(...)):
    """{child, parent, at} — 템플릿 child 를 parent 의 L at 아래로: 종속 템플릿 「T{parent}T{child}」(id 「parent+child」)를 만들어 그 자리에 매달린 child 줄을
    (종속 템플릿, at + 레벨)로. parent 는 안 바뀐다. 문서는 안 바뀐다 · 실행 취소 1(기록 `outlineMerge`). → {merged{id, no, moved, levels}, outline, …편집 상태}.
    400 매달린 곳 없음·이미 넣음·제 자신·잘못된 값 · 409 2단계 없음."""
    server = _server()
    child, parent, at = _tid(body.get("child"), "child"), _tid(body.get("parent"), "parent"), body.get("at")
    if isinstance(at, bool) or not isinstance(at, int) or at < 1:
        raise HTTPException(400, "at(넣을 자리의 레벨 — 1 이상의 정수)이 필요합니다")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)

        def change():
            rec = outline_match.merge(ov, child, parent, at, outline_match.context(s.doc, ov))
            C = ov["templates"][rec["id"]]
            return {"id": rec["id"], "no": C["no"], "child": ov["templates"][child]["no"], "parent": ov["templates"][parent]["no"], "at": at,
                    "moved": len(rec["moved"]), "levels": [at + 1, C["max"]]}
        got, ok = _model_only(server, s, "outlineMerge", {"child": child, "parent": parent, "at": at}, change)
        if not ok:
            return got
        return {"merged": got, "outline": outline_pos.view(s.doc, s.outline), **_state(s)}


@router.post("/api/docs/{doc_id}/outline/unmerge")
def unmerge(doc_id: str, body: dict = Body(...)):
    """{child, parent} — 종속 템플릿을 지우고 그 줄을 child 로 되돌린다(넣은 뒤 Enter 로 만든 줄 포함). 실행 취소 1(기록 `outlineUnmerge`). → {back, outline, …편집 상태}.
    400 기록 없음 · 그 종속 템플릿으로 또 만든 종속 템플릿이 있음(그것부터)."""
    server = _server()
    child, parent = _tid(body.get("child"), "child"), _tid(body.get("parent"), "parent")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov = _ov(server, s)

        def change():
            return {"child": ov["templates"].get(child, {}).get("no"), "parent": ov["templates"].get(parent, {}).get("no"),
                    "back": outline_match.unmerge(ov, child, parent)}
        got, ok = _model_only(server, s, "outlineUnmerge", {"child": child, "parent": parent}, change)
        if not ok:
            return got
        return {"back": got.get("back", 0), "outline": outline_pos.view(s.doc, s.outline), **_state(s)}
