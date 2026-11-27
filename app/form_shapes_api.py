"""양식 서식 점검의 끝점(spec_양식작성 ② §5-11 — 순수 계산은 app/form_shapes.py). 2026-11-27 사용자 "여기에 이상한 서식들을 삭제 제안하는 기능이 있어야 할거 같아. 레터가 없거나 이런건 서식을 수정해야 하고,".
스크립트만(LLM 없음) · 찾기는 문서를 안 바꾸고, 반영은 **사람이 고른 줄만** 구조 편집 하나(실행 취소 1 · rev +1 · 기록 `formShapes`)로 한다.

- GET  /api/docs/{id}/form-shapes → {items[form_shapes.find 의 항목 + pre(처음부터 고른 제안인가)], counts, rev}. hwpx 가 아니면 빈 목록.
- POST /api/docs/{id}/form-shapes {expectRev?, picks: {문단 id: {do: "restyle" | "delete", sig}}} → 지금 문서에서 다시 찾아 지문(sig)이 같은 줄만 반영.
  → {done{restyled[문단 id], deleted[문단 id], skipped[{id, why}]}, …편집 상태} · 넣을 것이 하나도 안 남으면 409(편집 없음) · expectRev 가 다르면 409.
처음부터 고르는 제안(pre) = 채운 줄의 서식 수정 · 친 글머리 줄의 서식 수정. 글머리 없는 **빈** 줄(여백일 수 있다)과 삭제 제안은 사람이 고른다."""
from fastapi import APIRouter, Body, HTTPException

from app import form_shapes

router = APIRouter()
DOS = ("restyle", "delete")
STALE = "목록을 읽은 뒤 그 줄이 바뀌었습니다"


def _pre(it):
    return it["propose"] == "restyle" and (it["filled"] or it["kind"] == "typed")


def _inputs(s):
    """헤딩 그래프의 레벨 · 올린 원본의 원문 — 작업 파일을 읽으므로 세션 잠금 밖에서."""
    from app import doc_agent_api, guide_write_api
    return doc_agent_api._levels(s), guide_write_api.uploaded_texts(s)


def read(s, levels, orig):
    """지금 문서의 점검 결과(세션 잠금 안에서 부른다)."""
    got = form_shapes.find(s.doc.blocks(), levels, orig)
    for it in got["items"]:
        it["pre"] = _pre(it)
    return got


@router.get("/api/docs/{doc_id}/form-shapes")
def form_shapes_get(doc_id: str):
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        return {"items": [], "counts": {"bare": 0, "typed": 0, "restyle": 0, "delete": 0, "total": 0}, "rev": s.rev}
    levels, orig = _inputs(s)
    with s.lock:
        return {**read(s, levels, orig), "rev": s.rev}


@router.post("/api/docs/{doc_id}/form-shapes")
def form_shapes_post(doc_id: str, body: dict = Body(default={})):
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    picks = body.get("picks")
    if not isinstance(picks, dict) or not picks or not all(isinstance(k, str) and isinstance(v, dict) and v.get("do") in DOS for k, v in picks.items()):
        raise HTTPException(400, "picks 는 {문단 id: {do: \"restyle\" | \"delete\", sig}}")
    levels, orig = _inputs(s)
    with s.lock:
        if body.get("expectRev") is not None and body["expectRev"] != s.rev:
            raise HTTPException(409, "목록을 읽은 뒤 문서가 바뀌었습니다 — 다시 읽으세요")
        now = {it["id"]: it for it in read(s, levels, orig)["items"]}
        todo, skipped = [], []
        for pid, v in picks.items():
            it = now.get(pid)
            if it is None or it["sig"] != v.get("sig"):
                skipped.append({"id": pid, "why": STALE})
            elif v["do"] not in it["options"]:
                skipped.append({"id": pid, "why": "이 줄에는 할 수 없는 일입니다" + (" — 글을 쓴 줄은 지우지 않습니다" if v["do"] == "delete" and it["filled"] else "")})
            else:
                todo.append((it, v["do"]))
        if not todo:
            raise HTTPException(409, "반영할 줄이 없습니다 — " + (skipped[0]["why"] if skipped else "고른 줄이 없습니다"))
        done = {"restyled": [], "deleted": [], "skipped": skipped}
        boxes = list(dict.fromkeys(it["box"] for it, _ in todo))

        def run():
            for it, do in todo:
                if do == "restyle" and s.doc.shape_like(it["id"], it["like"], it.get("text")):
                    done["restyled"].append(it["id"])
            for it, do in todo:   # 지우기는 뒤에(맞출 줄이 지울 줄일 수는 없다 — 맞출 줄은 글머리가 찍히는 줄이고 지울 줄은 아니다)
                if do == "delete":
                    s.doc.delete_blocks(it["id"], it["id"])
                    done["deleted"].append(it["id"])
            return {"hosts": [s.doc._ids[b] for b in boxes], "formatted": set(done["restyled"]), "struct": set(), "origin": {}, "anchor": boxes[0], "focus": None,
                    "log": {"restyled": len(done["restyled"]), "deleted": len(done["deleted"]), "skipped": len(skipped)}}
        out, after = server._transact(s, run, "formShapes", req={"picks": {it["id"]: do for it, do in todo}})
        if after is None:
            return out
        return {"done": done, **s.state()}
