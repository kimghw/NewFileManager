"""캡션 템플릿 「CN」 API(spec_hwpx_웹편집 ② §8-10) — server.py 가 include 한다(`outline_match_api` 와 같은 꼴).
계산·역변환은 `app/caption_tpl.py`, 번호·사람이 정한 대표는 개요 오버레이의 `caps`(`server._outline_ov` — 실행 취소 묶음 · 작업 저장에 함께 든다), 트랜잭션은 `server._transact`·`server._edit`."""
import logging

from fastapi import APIRouter, Body, HTTPException

from app import caption_tpl, heading_runs
from app.outline_match_api import _model_only, _server
from app.outline_match_api import _state as _edit_state

router = APIRouter()
log = logging.getLogger(__name__)
NEED_OV = "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요 — 캡션 템플릿의 대표는 개요 오버레이에 적습니다"


def _temp(s):
    """TEMP 문단(표 안 작성요령 · 쓸 자리 — spec_헤딩_추출 ② §15) id 들 — 헤딩 후보에서 빼는 것과 같이 캡션 줄에서도 뺀다(다 쓴 문서에 남지 않을 글). 1단계 결과가 없으면 빈 것."""
    try:
        t = heading_runs.temp_label(s)
    except Exception as e:  # noqa: BLE001 — TEMP 라벨을 못 읽어도 캡션 템플릿은 보인다
        log.warning("[캡션 템플릿] %s TEMP 라벨을 읽지 못함: %r", s.id, e)
        return set()
    return (set(t.get("paras") or ()) | set(t.get("tableParas") or ())) if t else set()


def _caps(server, s):
    """(개요 오버레이 | None, 캡션 상태, 캡션으로 보지 않을 문단 = 개요 줄 + TEMP 문단). 오버레이가 없으면(2단계 전) 상태는 남기지 않는 빈 것 — 번호는 문서 차례로만 매긴다."""
    ov = server._outline_ov(s) if s.fmt == "hwpx" else None
    if ov is None:
        return None, {}, _temp(s) if s.fmt == "hwpx" else set()
    return ov, ov.setdefault("caps", {"ids": {}, "reps": {}}), set(ov["lines"]) | _temp(s)


def _hwpx(s):
    if s.fmt != "hwpx":
        raise HTTPException(400, "캡션 템플릿은 HWPX 문서에서만 됩니다")


def _view(server, s, tpl=None):
    ov, st, skip = _caps(server, s)
    return {"rev": s.rev, "stored": ov is not None, **caption_tpl.model(s.doc, st, skip, full=tpl is not None, only=tpl)}


@router.get("/api/docs/{doc_id}/captions")
def captions(doc_id: str, tpl: str | None = None):
    """캡션 템플릿 → {rev, stored(번호·대표를 남길 수 있나 = 개요 오버레이가 있나), templates[{id 「C1」, no, kind, kindName, shape, name, total, sides, struct, text, frozen, rep, repSet, others,
    groups[{key, count, paras, more, rep, look, raw, diff}], sig}], lines{문단 id: {tpl, no, shape}}, missed, keys}. docx 면 {off: true}(문서를 열 때마다 부르므로 404 를 내지 않는다).
    `?tpl=C1` 을 주면 그 템플릿만 갈래를 셈하고 갈래마다 **줄 전부**(30줄에서 자르지 않는다)."""
    server = _server()
    s = server._sess(doc_id)
    with s.lock:
        if s.fmt != "hwpx":
            return {"off": True, "why": "캡션 템플릿은 HWPX 문서에서만 됩니다", "rev": s.rev, "templates": [], "lines": {}, "missed": 0, "keys": []}
        return _view(server, s, tpl)


@router.put("/api/docs/{doc_id}/captions/{cid}/rep")
def set_rep(doc_id: str, cid: str, body: dict = Body(...)):
    """{para} — 캡션 템플릿 cid 의 대표를 그 캡션 줄로. 문서는 안 바뀐다 · 실행 취소 1(기록 `captionRep`). → {captions(GET 과 같은 꼴), …편집 상태}.
    400 그 템플릿의 줄이 아님 · 404 그런 템플릿 없음 · 409 2단계 없음(대표를 적을 개요 오버레이가 없다)."""
    server = _server()
    pid = body.get("para")
    if not isinstance(pid, str) or not pid:
        raise HTTPException(400, "para(문단 id)가 필요합니다")
    s = server._sess(doc_id)
    _hwpx(s)
    with s.lock:
        ov, st, skip = _caps(server, s)
        if ov is None:
            raise HTTPException(409, NEED_OV)
        caption_tpl.model(s.doc, st, skip, only="")  # 번호를 매겨 둔다(갈래는 셈하지 않는다)
        if caption_tpl.key_of(st, cid) is None:
            raise HTTPException(404, "그런 캡션 템플릿이 없습니다")

        def change():
            was = caption_tpl.set_rep(s.doc, st, cid, pid, skip)
            return {"tpl": cid, "rep": pid, "was": was}
        out, ok = _model_only(server, s, "captionRep", {"tpl": cid, "para": pid}, change)
        if not ok:
            return out
        return {"captions": _view(server, s), **_edit_state(s)}


def _ids(v, what):
    if v is not None and (not isinstance(v, list) or not all(isinstance(p, str) and p for p in v)):
        raise HTTPException(400, f"{what} 는 문단 id 목록")
    return v


@router.post("/api/docs/{doc_id}/captions/{cid}/match")
def match(doc_id: str, cid: str, body: dict = Body(default={})):
    """{paras?, like?, likes?} — 캡션 템플릿 cid 에서 대표와 비교 값이 다른 줄(paras 를 주면 그 가운데서만 · like/likes(그 템플릿의 줄 id)를 주면 그 줄과 서식이 같은 갈래만)을
    대표의 지금 모양으로(`caption_tpl.conform` — 문단 모양 · 레터·바탕 글자 모양 · 앞 빈칸·레터·레터 뒤 빈칸 · 닫는 괄호). 구조 편집 트랜잭션 하나(기록 `captionMatch` · 실행 취소 1 · 닿은 문단 검사).
    응답 = 다른 구조 편집과 같은 꼴 + changed(바뀐 줄) · frozen(글은 못 바꾸고 모양만 맞춘 줄 — 머리에 자동 번호·표지) · captions. 맞출 줄이 없으면 편집을 열지 않고 {changed: [], nothing: true, …편집 상태}.
    400 그 템플릿의 줄이 아님 · 404 그런 템플릿 없음 · 409 그 사이에 문서가 바뀜."""
    server = _server()
    paras, likes = _ids(body.get("paras"), "paras"), _ids(body.get("likes"), "likes")
    like = body.get("like")
    if like is not None:
        if not isinstance(like, str) or not like:
            raise HTTPException(400, "like 는 문단 id")
        likes = (likes or []) + [like]

    def plan(s):
        ov, st, skip = _caps(server, s)
        caption_tpl.model(s.doc, st, skip, only="")
        try:
            return caption_tpl.targets(s.doc, st, cid, paras, likes, skip)
        except KeyError as e:
            raise HTTPException(404, "그런 캡션 템플릿이 없습니다") from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    s0 = server._sess(doc_id)
    _hwpx(s0)
    with s0.lock:
        if not plan(s0)[1]:
            return {"changed": [], "nothing": True, **_edit_state(s0)}
    changed, held = [], []

    def make(s):
        rep, hit = plan(s)
        if not hit:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 줄이 없습니다 — 다시 읽어 주세요")
        els = [s.doc._ids[ln["id"]] for ln in hit]

        def run():
            sh = caption_tpl.shape(s.doc, rep)
            for ln in hit:
                r = caption_tpl.conform(s.doc, ln, sh)
                changed.append(r["id"])
                if r["frozen"]:
                    held.append(r["id"])
            return {"hosts": els, "formatted": set(changed), "struct": set(), "origin": {}, "anchor": hit[0]["id"],
                    "log": {"tpl": cid, "rep": rep["id"], "changed": len(changed), "frozen": len(held)}}
        return els, run
    out = server._edit(doc_id, make, "captionMatch", {"tpl": cid, "paras": paras, "likes": likes})
    if isinstance(out, dict):
        out["changed"], out["frozen"] = changed, held
        s = server._sess(doc_id)
        with s.lock:
            out["captions"] = _view(server, s)
    return out
