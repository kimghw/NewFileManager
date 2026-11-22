"""캡션 템플릿 「CN」 API(spec_hwpx_웹편집 ② §8-10) — server.py 가 include 한다(`outline_match_api` 와 같은 꼴).
계산·역변환은 `app/caption_tpl.py`, 번호·사람이 정한 대표는 개요 오버레이의 `caps`(`server._outline_ov` — 실행 취소 묶음 · 작업 저장에 함께 든다), 트랜잭션은 `server._transact`·`server._edit`."""
import hashlib
import json
import logging
import threading

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


# ---------------------------------------------------------------- 모든 캡션을 한 꼴로(spec_hwpx_웹편집 ② §8-10 「모든 캡션을 한 꼴로」 — 「문서 정리」 의 조립 도구 「캡션 맞추기」: spec_워크플로우 ② §18-23)
# 고른 꼴 = 그 묶음(프로젝트 · 워크플로우 · 라운드)의 실행 옵션(task_options.flow 의 caption — 꼴 열쇠 `caption_tpl.form_key`) · 없으면 줄이 가장 많은 꼴. 계산 · 역변환은 caption_tpl(unify_plan · unify_line).
# 워크플로우 상태가 GET …/flow 마다 부르므로 (문서 차례 · 고른 꼴 · 사람이 정한 대표 · 뺄 문단)이 같으면 셈한 것을 쓴다(_UCACHE).
_UCACHE = {}   # 문서 id → (열쇠, 요약)
_ULOCK = threading.Lock()
UCACHE_MAX = 16
UNIFY_LIST = 60   # 요약에 싣는 맞출 줄 id 수


def chosen(doc_id):
    """그 문서가 든 묶음의 「캡션 맞추기」 에서 고른 꼴(꼴 열쇠) | None(줄이 가장 많은 꼴)."""
    from app import task_options, works
    w = works.work(doc_id)
    return task_options.flow(w).get("caption") if w else None


def _brief(P, rev, pick):
    rep = P["rep"]
    ids = [ln["id"] for ln, _m in P["todo"]]
    return {"rev": rev, "form": P["form"], "asked": P["asked"], "chosen": pick, "name": P["name"], "why": P["why"],
            "rep": {"id": rep["id"], "text": rep["text"].strip(), "kind": rep["kind"], "kindName": caption_tpl.KINDS[rep["kind"]]} if rep else None,
            "forms": P["forms"], "counts": P["counts"], "paras": ids[:UNIFY_LIST], "more": max(0, len(ids) - UNIFY_LIST)}


def _unify(server, s, form):
    """(세션 잠금 안) → (계획, 캐시 열쇠) | (None, 셈해 둔 요약 — 같은 열쇠)."""
    ov, st, skip = _caps(server, s)
    key = json.dumps([s.rev, form, st.get("reps") or {}, hashlib.sha1(",".join(sorted(skip)).encode("utf-8")).hexdigest()], ensure_ascii=False, sort_keys=True)
    with _ULOCK:
        hit = _UCACHE.get(s.id)
    if hit is not None and hit[0] == key:
        return None, hit[1]
    P = caption_tpl.unify_plan(s.doc, st, form, skip)
    return P, key


def unify_view(doc_id, form=None, use_chosen=True):
    """모든 캡션을 한 꼴로 맞출 계획의 요약(문서 안 바뀜) → {rev, form(쓸 꼴 | None), asked, chosen(묶음에 고른 꼴 | None), name, why, rep{id, text, kind, kindName} | None,
    forms[{key, family, name, count, kinds, rep, repSet, text, look}], counts{titles, change, full, style, frozen, cross, others}, paras(맞출 줄 — 60까지), more} · docx 면 {off: true, why}.
    form 을 주지 않으면 묶음에 고른 꼴(use_chosen) · 그것도 없으면 줄이 가장 많은 꼴."""
    server = _server()
    pick = chosen(doc_id) if use_chosen else None
    form = form or pick
    s = server._sess(doc_id)
    with s.lock:
        if s.fmt != "hwpx":
            return {"off": True, "why": "캡션 맞추기는 HWPX 문서에서만 됩니다", "rev": s.rev, "form": None, "asked": form, "chosen": pick, "name": "", "rep": None, "forms": [],
                    "counts": {"titles": 0, "change": 0, "full": 0, "style": 0, "frozen": 0, "cross": 0, "others": 0}, "paras": [], "more": 0}
        P, got = _unify(server, s, form)
        if P is None:   # 셈해 둔 요약(got)
            return {**got, "chosen": pick}
        key, out = got, _brief(P, s.rev, pick)
    with _ULOCK:
        _UCACHE.pop(doc_id, None)
        _UCACHE[doc_id] = (key, out)
        while len(_UCACHE) > UCACHE_MAX:
            del _UCACHE[next(iter(_UCACHE))]
    return out


@router.get("/api/docs/{doc_id}/captions/unify")
def unify_get(doc_id: str, form: str | None = None):
    """모든 캡션을 한 꼴로 — 고를 꼴들 · 쓸 꼴 · 맞출 줄의 수(문서 안 바뀜). `?form=` 을 주면 그 꼴로 셈한다(안 주면 묶음에 고른 꼴 · 없으면 가장 많은 꼴)."""
    return unify_view(doc_id, form)


@router.post("/api/docs/{doc_id}/captions/unify")
def unify_post(doc_id: str, body: dict = Body(default={})):
    """{form?, expectRev?} — 모든 제목 캡션을 그 꼴(안 주면 묶음에 고른 꼴 · 없으면 가장 많은 꼴)의 대표 서식으로(`caption_tpl.unify_line` → `conform`).
    같은 갈래(번호 붙은 머리끼리 · 줄 전체 괄호끼리)는 글 꼴도 · 다른 갈래와 자동 번호 · 표지가 든 줄은 서식만. 구조 편집 트랜잭션 하나(기록 `captionUnify` · 실행 취소 1 · 닿은 문단 검사).
    → 다른 구조 편집과 같은 꼴 + changed · frozen(서식만 맞춘 줄 — 자동 번호 · 표지) · unify(맞춘 뒤의 요약). 맞출 줄이 없으면 편집을 열지 않고 {changed: [], nothing: true, unify, …편집 상태}.
    400 꼴 · 409 미리 본 뒤 문서가 바뀜(expectRev) · 고른 꼴의 캡션이 문서에 없음."""
    server = _server()
    form = body.get("form")
    if form is not None and (not isinstance(form, str) or not form):
        raise HTTPException(400, "form 은 꼴 열쇠(글)")
    form = form or chosen(doc_id)
    s0 = server._sess(doc_id)
    if s0.fmt != "hwpx":
        raise HTTPException(400, "캡션 맞추기는 HWPX 문서에서만 됩니다")

    def plan(s):
        ov, st, skip = _caps(server, s)
        P = caption_tpl.unify_plan(s.doc, st, form, skip)
        if P["why"] and P["counts"]["titles"]:
            raise HTTPException(409, P["why"])
        return P

    with s0.lock:
        if body.get("expectRev") is not None and body["expectRev"] != s0.rev:
            raise HTTPException(409, "미리 본 뒤 문서가 바뀌었습니다 — 다시 읽으세요")
        idle = None if plan(s0)["todo"] else {"changed": [], "frozen": [], "nothing": True, **_edit_state(s0)}
    if idle is not None:   # 요약은 잠금 밖에서(unify_view 가 세션 잠금을 다시 잡는다)
        return {**idle, "unify": unify_view(doc_id, form)}
    changed, held = [], []

    def make(s):
        P = plan(s)
        if not P["todo"]:
            raise HTTPException(409, "그 사이에 문서가 바뀌어 맞출 캡션이 없습니다 — 다시 읽어 주세요")
        rep = P["rep"]
        els = [s.doc._ids[ln["id"]] for ln, _m in P["todo"]]

        def run():
            sh = caption_tpl.shape(s.doc, rep)
            for ln, mode in P["todo"]:
                r = caption_tpl.unify_line(s.doc, ln, mode, sh, rep)
                changed.append(r["id"])
                if r["frozen"]:
                    held.append(r["id"])
            return {"hosts": els, "formatted": set(changed), "struct": set(), "origin": {}, "anchor": P["todo"][0][0]["id"],
                    "log": {"form": P["form"], "rep": rep["id"], "changed": len(changed), "frozen": len(held), "counts": P["counts"]}}
        return els, run
    out = server._edit(doc_id, make, "captionUnify", {"form": form})
    with _ULOCK:
        _UCACHE.pop(doc_id, None)
    if isinstance(out, dict):
        out["changed"], out["frozen"] = changed, held
        out["unify"] = unify_view(doc_id, form)
    return out
