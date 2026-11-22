"""그림 도구 끝점(spec_그림 ② §8) — 그림 정보 · 그림 → 표(LLM 읽기 · 넣기) · 캡션 넣기(LLM 짓기 · 넣기) · 선명하게(미리보기 · 바꾸기) · 가운데 · 한 줄에.

hwpx 문서만(그 밖은 415). 문서를 바꾸는 끝점은 `server._edit`(잠금 · 실행 취소 · OWPML 지역 검사 · 바뀐 블록만 응답) 위에서 돈다 — LLM 은 잠금 밖에서 부르고 문서는 안 바꾼다.
순수 로직은 `app/pic_tools.py`, 문서 바꾸기는 `app/hwpx_pic.py`(HwpxDoc 믹스인), 화면은 `app/static/pic_tools.js`."""
import time

from fastapi import APIRouter, Body, HTTPException, Response

from app import llm, pic_tools as PT, table_llm, table_make, works

router = APIRouter()
LEVELS = tuple(PT.LEVELS)


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _hwpx(s):
    if s.fmt != "hwpx" or not hasattr(s.doc, "pic_info"):
        raise HTTPException(415, "그림 도구는 지금 hwpx 문서만 됩니다")


def _info(s, pid):
    try:
        return s.doc.pic_info(pid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


def _raster(info):
    if not info["media"] or not PT.is_raster(info["media"]):
        raise HTTPException(415, "그림 파일을 읽을 수 없는 그림입니다(연결 그림 · wmf · emf 같은 벡터 그림) — 가운데 · 한 줄에만 됩니다")


def _caps(s, blocks):
    caps = PT.captions(blocks)
    return caps, [c["text"]["id"] for c in caps.values() if c["text"]]


def nearest_table(blocks, pid):
    """표 양식의 기본(② §2) — 문서 차례로 그림 앞의 가장 가까운 여러 칸 표(2행 · 2열 이상), 없으면 뒤의 첫 표 | None."""
    before, after, seen = None, None, False
    for b in PT.H.iter_blocks(blocks):
        if b.get("id") == pid:
            seen = True
            continue
        if b.get("type") == "table" and (b.get("nRows") or 0) >= 2 and (b.get("nCols") or 0) >= 2:
            if not seen:
                before = b["id"]
            elif after is None:
                after = b["id"]
                break
    return before or after


def _template(s, tid):
    from app import tables_api
    blk = tables_api._live_table(s, tid, "표 양식으로 고른 표")
    return blk, tables_api._roles(blk)


@router.get("/api/docs/{doc_id}/pics/{pid}")
def pic_get(doc_id: str, pid: str):
    """그림 하나 — {id, media, widthMm, heightMm, inline, host, align, cell, caption(개체 캡션), hasCaption(개체 · 글 캡션), raster, heading(소속 헤딩 경로), template(표 양식 기본)}."""
    s = _sess(doc_id)
    with s.lock:
        _hwpx(s)
        info = _info(s, pid)
        blocks = s.doc.blocks()
        caps, _ = _caps(s, blocks)
        return {**info, "raster": bool(info["media"] and PT.is_raster(info["media"])), "hasCaption": PT.has_caption(blocks, pid, caps),
                "heading": PT.heading_path(blocks, pid), "template": nearest_table(blocks, pid), "rev": s.rev}


def _need_llm():
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK · CLI · API 키 없음 또는 꺼짐)")


def _log_read(s, kind, pid, rev, res, extra):
    call = res.get("call") or {}
    detail = works.add_detail(s.id, "pics", f"{kind}_{int(time.time() * 1000)}", {"rev": rev, "pic": pid, **extra, "answer": {k: v for k, v in res.items() if k != "call"}, "call": call})
    works.log(s.id, "picRead", rev=rev, what=kind, pic=pid, backend=call.get("backend"), ms=call.get("ms"), costUsd=call.get("costUsd"), error=call.get("error"), detail=detail)


@router.post("/api/docs/{doc_id}/pics/{pid}/read-table")
def pic_read_table(doc_id: str, pid: str, body: dict = Body(default={})):
    """그림 → 표 읽기(LLM — 문서는 안 바뀜 · ② §2) {template?} → {tables: [격자 — 행 꼴], caption: [줄], note, dropped, call, template, context, rev}."""
    s = _sess(doc_id)
    _need_llm()
    with s.lock:
        _hwpx(s)
        info = _info(s, pid)
        _raster(info)
        data = s.doc.media(info["media"])
        blocks = s.doc.blocks()
        ctx = PT.context(blocks, pid)
        tid = body.get("template") or nearest_table(blocks, pid)
        template = None
        if tid:
            blk, roles = _template(s, tid)
            template = table_llm.template_data(blk, roles)
        rev = s.rev
    res = PT.ask_table(PT.for_llm(data), ctx, template)
    _log_read(s, "table", pid, rev, res, {"template": tid, "context": ctx})
    if res["call"].get("error") and not res["tables"] and not res["caption"]:
        raise HTTPException(502, f"LLM 이 그림을 읽지 못했습니다: {res['call']['error']}")
    return {**res, "tables": [table_make.to_rows(n) for n in res["tables"]], "template": tid, "context": ctx, "rev": rev}


@router.post("/api/docs/{doc_id}/pics/{pid}/table")
def pic_table(doc_id: str, pid: str, body: dict = Body(...)):
    """그림 → 표 넣기(② §2) {template, templateRoles?, tables: [격자], caption: [줄], replace: bool(기본 참)} — 그림의 문단 바로 뒤에 표들을 차례로(서식 = 표 양식) ·
    캡션 줄은 첫 표의 위 개체 캡션 · replace 면 그림을 지운다. 응답 = 구조 편집 응답 + made {tables: [id], caption: [문단 id], removed}."""
    from app import server, tables_api
    tid, replace = body.get("template"), body.get("replace", True) is not False
    grids = body.get("tables")
    if not isinstance(grids, list) or not grids:
        raise HTTPException(400, "넣을 표가 없습니다")
    try:
        norms = [table_make.normalize(g) for g in grids]
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    lines = [str(x) for x in body.get("caption") or () if str(x).strip()]
    made = {}

    def make(s):
        _hwpx(s)
        _info(s, pid)
        roles = tables_api._roles(tables_api._live_table(s, tid, "표 양식으로 고른 표"), body.get("templateRoles"))
        pic = s.doc._ids[pid]
        host = s.doc._host(pic)
        _, like = _caps(s, s.doc.blocks()) if lines else (None, None)

        def run():
            after, ids, hosts = pid, [], []
            for norm in norms:
                r = s.doc.table_make(after, tid, norm, roles)
                ids.append(r["table"])
                hosts.append(s.doc._ids[r["host"]])
                after = r["table"]
            cap = s.doc.obj_caption_set(ids[0], lines, side="TOP", like_text=like) if lines else []
            removed = s.doc.delete_blocks(pid, pid)["removed"] if replace else []
            made.update(tables=ids, caption=cap, removed=removed)
            return {"hosts": hosts + ([host] if s.doc._attached(host) else []), "anchor": pid, "focus": None,
                    "log": {"pic": pid, "tables": ids, "template": tid, "caption": len(cap), "replaced": replace}}
        return [host], run
    out = server._edit(doc_id, make, "picTable", {"pic": pid, "template": tid, "tables": len(norms), "caption": len(lines), "replace": replace})
    if isinstance(out, dict):
        out["made"] = made
    return out


@router.post("/api/docs/{doc_id}/pics/{pid}/read-caption")
def pic_read_caption(doc_id: str, pid: str):
    """캡션 짓기(LLM — 문서는 안 바뀜 · ② §3) → {caption, note, call, context, rev}. 이미 캡션이 있으면 409(그 글)."""
    s = _sess(doc_id)
    _need_llm()
    with s.lock:
        _hwpx(s)
        info = _info(s, pid)
        _raster(info)
        blocks = s.doc.blocks()
        caps, _ = _caps(s, blocks)
        if PT.has_caption(blocks, pid, caps):
            raise HTTPException(409, "이 그림에는 이미 캡션이 있습니다")
        data = s.doc.media(info["media"])
        ctx = PT.context(blocks, pid)
        rev = s.rev
    res = PT.ask_caption(PT.for_llm(data), ctx)
    _log_read(s, "caption", pid, rev, res, {"context": ctx})
    if not res["caption"]:
        raise HTTPException(502, f"LLM 이 캡션을 짓지 못했습니다: {res['call'].get('error') or '빈 답'}")
    return {**res, "context": ctx, "rev": rev}


@router.post("/api/docs/{doc_id}/pics/{pid}/caption")
def pic_caption(doc_id: str, pid: str, body: dict = Body(...)):
    """캡션 넣기(② §3) {caption: 글 | [줄]} — 그림의 아래 개체 캡션으로. 응답 = 구조 편집 응답 + made {caption: [문단 id]}."""
    from app import server
    cap = body.get("caption")
    lines = [cap] if isinstance(cap, str) else [str(x) for x in cap or ()]
    lines = [x for x in lines if x.strip()]
    if not lines:
        raise HTTPException(400, "캡션 글이 비었습니다")
    made = {}

    def make(s):
        _hwpx(s)
        _info(s, pid)
        host = s.doc._host(s.doc._ids[pid])
        _, like = _caps(s, s.doc.blocks())

        def run():
            made["caption"] = s.doc.obj_caption_set(pid, lines, side="BOTTOM", like_text=like)
            return {"hosts": [host], "anchor": pid, "focus": None, "log": {"pic": pid, "caption": len(made["caption"])}}
        return [host], run
    out = server._edit(doc_id, make, "picCaption", {"pic": pid, "lines": len(lines)})
    if isinstance(out, dict):
        out["made"] = made
    return out


def _level(v):
    if v not in LEVELS:
        raise HTTPException(400, f"level 은 {' · '.join(LEVELS)}")
    return v


@router.get("/api/docs/{doc_id}/pics/{pid}/sharpen.png")
def pic_sharpen_preview(doc_id: str, pid: str, level: str = "normal"):
    """선명하게 미리보기(② §4 — 문서는 안 바뀜): 바뀔 그림 바이트. 머리말 X-Pixels = 「전 가로×세로 → 뒤 가로×세로」."""
    s = _sess(doc_id)
    with s.lock:
        _hwpx(s)
        info = _info(s, pid)
        _raster(info)
        data = s.doc.media(info["media"])
    r = PT.enhance(data, PT.ext_of(info["media"]), info["widthMm"], _level(level))
    return Response(r["data"], media_type="image/jpeg" if r["ext"] == "jpg" else "image/png",
                    headers={"Cache-Control": "no-store", "X-Pixels": f"{r['before'][0]}x{r['before'][1]}>{r['w']}x{r['h']}", "Access-Control-Expose-Headers": "X-Pixels"})


@router.post("/api/docs/{doc_id}/pics/{pid}/sharpen")
def pic_sharpen(doc_id: str, pid: str, body: dict = Body(default={})):
    """선명하게 바꾸기(② §4) {level} — 새 그림 파일로(표시 크기 그대로). 응답 = 구조 편집 응답 + made {before, after, scale}."""
    from app import server
    level = _level(body.get("level") or "normal")
    made = {}

    def make(s):
        _hwpx(s)
        info = _info(s, pid)
        _raster(info)
        host = s.doc._host(s.doc._ids[pid])
        r = PT.enhance(s.doc.media(info["media"]), PT.ext_of(info["media"]), info["widthMm"], level)

        def run():
            s.doc.pic_replace(pid, r["data"], r["ext"], r["w"], r["h"])
            made.update(before=list(r["before"]), after=[r["w"], r["h"]], scale=r["scale"])
            return {"hosts": [host], "anchor": pid, "focus": None, "log": {"pic": pid, "level": level, "before": list(r["before"]), "after": [r["w"], r["h"]]}}
        return [host], run
    out = server._edit(doc_id, make, "picSharpen", {"pic": pid, "level": level})
    if isinstance(out, dict):
        out["made"] = made
    return out


def _ids(body, n=None):
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids) or (n and len(dict.fromkeys(ids)) != n):
        raise HTTPException(400, f"그림 id {'둘' if n == 2 else ''} 목록(ids)이 필요합니다")
    return list(dict.fromkeys(ids))


@router.post("/api/docs/{doc_id}/pics/center")
def pic_center(doc_id: str, body: dict = Body(...)):
    """가운데(② §5) {ids} — 이미 모두 가운데면 {same: true}(문서 안 바뀜)."""
    from app import server
    ids = _ids(body)
    s = _sess(doc_id)
    with s.lock:
        _hwpx(s)
        infos = [_info(s, i) for i in ids]
        if all(x["inline"] and x["align"] == "center" for x in infos):
            return {"same": True}
    made = {}

    def make(s):
        hosts = [s.doc._host(s.doc._ids[i]) for i in ids if _info(s, i)]

        def run():
            made["centered"] = s.doc.pic_center(ids)
            return {"hosts": hosts, "anchor": ids[0], "focus": None, "log": {"pics": ids, "centered": made["centered"]}}
        return hosts, run
    out = server._edit(doc_id, make, "picCenter", {"pics": ids})
    if isinstance(out, dict):
        out["made"] = made
    return out


@router.post("/api/docs/{doc_id}/pics/row")
def pic_row(doc_id: str, body: dict = Body(...)):
    """한 줄에 나란히(② §6) {ids: [그림 둘]} → 구조 편집 응답 + made {first, second, host, removed, scaled}."""
    from app import server
    a, b = _ids(body, 2)
    made = {}

    def make(s):
        _hwpx(s)
        _info(s, a)
        _info(s, b)
        hosts = list(dict.fromkeys(s.doc._host(s.doc._ids[i]) for i in (a, b)))

        def run():
            made.update(s.doc.pic_row(a, b))
            return {"hosts": [h for h in hosts if s.doc._attached(h)], "anchor": a, "focus": None, "log": {"pics": [a, b], "scaled": made.get("scaled")}}
        return hosts, run
    out = server._edit(doc_id, make, "picRow", {"pics": [a, b]})
    if isinstance(out, dict):
        out["made"] = made
    return out
