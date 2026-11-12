"""TEMP 라벨 API(spec_헤딩_추출 ② §15) — 표 안 작성요령·쓸 자리 목록 · 지정/해제 · 다시 셈 · 문서에서 지우기.
server.py 가 include 한다(구분 라벨 지정 `heading_labels_api` 와 같은 꼴). 판정은 app/heading_temp.py, 저장·다시 셈은 heading_runs, 지우기는 구조 편집 트랜잭션(server._transact)."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_extract as E
from app import heading_runs as HR
from app import heading_temp as TP

router = APIRouter()
DELETE_MAX = 2000  # 한 번에 지울 항목 수


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "헤딩 추출은 지금 hwpx 만 됩니다")
    return s


@router.get("/api/docs/{doc_id}/headings/temp")
def temp_get(doc_id: str):
    """{key, run, rev, stale, version, hints, counts, items[{id, unit, why, rule, by, table, cell, para, block, n, paras, candidates, text, rows?, cols?, box?}],
    off[{id, text}], gone[id], stage2{run, tempStale}, stage3{run, tempStale}} — 1단계 결과가 없으면 빈 목록."""
    return HR.temp_view(_sess(doc_id))


def _reapply(s):
    """지금 2단계 결과를 지금 TEMP·지정으로 다시 셈한다(LLM 호출 없음) → (다시 셈했나, 못 했으면 까닭). 돌고 있으면 409."""
    try:
        n = HR.relabel(s, "TEMP 지정")
    except HR.Stale as e:
        return False, str(e)
    except HR.Busy as e:
        raise HTTPException(409, f"지정은 저장했습니다. {e}") from e
    return (True, "") if n is not None else (False, "2단계 결과가 아직 없습니다 — 2단계를 돌리면 TEMP 가 빠집니다")


@router.put("/api/docs/{doc_id}/headings/temp")
def temp_put(doc_id: str, body: dict = Body(...)):
    """{id: "tbl:<표 id>" | "cell:<칸 id>" | "para:<문단 id>", state: "on" | "off" | "auto", why?: "guide" | "todo"} — 지정을 저장하고 지금 2단계 결과를 다시 셈해
    새 실행으로 둔다. → GET 과 같은 꼴 + `applied` · `note`(못 했으면 까닭 — 지정은 저장됨). 400 잘못된 값 · 409 헤딩 추출이 돌고 있음."""
    s = _sess(doc_id)
    try:
        HR.set_temp(s, body.get("id"), body.get("state"), body.get("why") or "guide")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"지정을 저장하지 못했습니다: {e}") from e
    applied, note = _reapply(s)
    return {**HR.temp_view(s), "applied": applied, "note": note}


@router.post("/api/docs/{doc_id}/headings/temp/apply")
def temp_apply(doc_id: str):
    """지금 TEMP 로 2단계 결과를 다시 셈한다(TEMP 를 모르던 옛 결과 · 지정을 저장만 해 둔 뒤) — LLM 호출 없음. → GET 과 같은 꼴 + `applied` · `note`."""
    s = _sess(doc_id)
    applied, note = _reapply(s)
    return {**HR.temp_view(s), "applied": applied, "note": note}


def _targets(t, ids, why):
    """지울 항목 — ids(항목 id 들) 또는 why(까닭 하나 전부). 문서 뒤쪽부터."""
    by_id = {it["id"]: it for it in t["items"]}
    if ids is not None:
        if not isinstance(ids, list) or not ids or len(ids) > DELETE_MAX or not all(isinstance(i, str) for i in ids):
            raise HTTPException(400, f"ids 는 항목 id 1~{DELETE_MAX}개")
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise HTTPException(400, f"지금 TEMP 가 아닌 항목: {', '.join(missing[:5])}")
        picked = [by_id[i] for i in dict.fromkeys(ids)]
    elif why in TP.WHYS:
        picked = [it for it in t["items"] if it["why"] == why]
    else:
        raise HTTPException(400, 'ids(항목 id 들) 또는 why("guide" | "todo")가 필요합니다')
    return sorted(picked, key=lambda it: -it["n"])


def _delete_one(s, it):
    """항목 하나를 문서에서 지운다 → 못 지우면 까닭(글), 지웠으면 None. 표 = 표 블록 · 칸 = 칸 안 블록 전부 · 문단 = 그 문단."""
    doc = s.doc
    unit, raw = TP.split_id(it["id"])
    el = doc._ids.get(raw)
    if not it.get("block") or el is None or not doc._attached(el):
        return "문서에서 찾지 못함(웹 블록이 없는 자리이거나 이미 지워짐)"
    tag = str(el.tag).rsplit("}", 1)[-1]
    if tag != {"table": "tbl", "cell": "tc", "para": "p"}[unit]:
        return "블록 종류가 다름"
    try:
        if unit == "cell":
            ps = [p for p in el.iter(s.kit["para"]) if p.getparent().getparent() is el]  # 칸에 바로 든 문단(hp:tc > hp:subList > hp:p) — 칸 안 표의 문단은 그 호스트와 함께 지워진다
            if not ps:
                return "칸에 문단이 없음"
            doc.delete_blocks(doc._id(ps[0]), doc._id(ps[-1]))
        else:
            doc.delete_blocks(raw, raw)
    except ValueError as e:
        return str(e)
    return None


@router.post("/api/docs/{doc_id}/headings/temp/delete")
def temp_delete(doc_id: str, body: dict = Body(...)):
    """TEMP 항목을 문서에서 지운다 — {ids: [항목 id…]} 또는 {why: "guide" | "todo"}(그 까닭 전부). 한 구조 편집 트랜잭션(문서 전체 표준 검사 · 실행 취소 1 · 기록 `tempDelete`).
    → {deleted[항목 id], skipped[{id, why}], …편집 상태}. 400 고른 것 없음 · 409 1단계 결과가 지금 문서 것이 아님(다시 추출 뒤) · 422 표준 검사에 걸려 되돌림."""
    from app import server  # 트랜잭션(_transact)·세션은 server 것 — 부를 때 가져온다
    s = _sess(doc_id)
    ids, why = body.get("ids"), body.get("why")
    with s.lock:
        s1 = HR.state(s).get("stage1")
        if not s1 or (s1.get("meta") or {}).get("rev") != s.rev or s1.get("version") != E.VERSION:
            raise HTTPException(409, "문서가 추출 뒤 바뀌었습니다 — 1단계를 다시 추출한 뒤 지우세요")
        targets = _targets(HR.temp_label(s), ids, why)
        if not targets:
            raise HTTPException(400, "지울 TEMP 항목이 없습니다")
        deleted, skipped = [], []

        def run():
            for it in targets:
                err = _delete_one(s, it)
                if err:
                    skipped.append({"id": it["id"], "why": err})
                else:
                    deleted.append(it["id"])
            if not deleted:
                raise ValueError("지울 수 있는 TEMP 항목이 없습니다 — " + "; ".join(f"{x['id']}: {x['why']}" for x in skipped[:3]))
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None,
                    "log": {"deleted": len(deleted), "skipped": len(skipped), "why": why, "items": deleted[:50]}}
        out, after = server._transact(s, run, "tempDelete", req={"ids": ids[:50] if isinstance(ids, list) else None, "why": why}, check=server._full_check)
        if after is None:
            return out
        return {"deleted": deleted, "skipped": skipped, **s.state()}
