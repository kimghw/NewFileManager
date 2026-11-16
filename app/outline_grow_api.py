"""개요 레벨 더하기 API(spec_hwpx_웹편집 ② §8-6) — 템플릿의 마지막 레벨 줄에서 Alt+↓ 를 눌렀을 때: 후보 받기(POST …/outline/grow/suggest) · 더하기(POST …/outline/grow).
server.py 가 include 한다(개요 줄 자리 `outline_format_api` 와 같은 꼴). 후보·슬롯 만들기는 `app/outline_grow.py`, 줄을 새 레벨로 내리는 계획은 `outline_edit.plan_level`,
실행·응답은 개요 편집(POST …/outline)과 같은 길(`server._edit` · `server._outline_run` — 트랜잭션 하나: OWPML 검사 · 실행 취소 1개 · 기록 kind `outline`)."""
from fastapi import APIRouter, Body, HTTPException

from app import outline_edit, outline_grow

router = APIRouter()


def _ids(body):
    ids = list(dict.fromkeys(body.get("ids") or ([body["id"]] if body.get("id") else [])))
    if not ids or not all(isinstance(i, str) for i in ids):
        raise HTTPException(400, "id 가 필요합니다")
    return ids


@router.post("/api/docs/{doc_id}/outline/grow/suggest")
def grow_suggest(doc_id: str, body: dict = Body(...)):
    """{ids: 마지막 레벨 줄들} → 새 레벨의 후보(outline_grow.suggest 꼴 — 레터 약 10개 · 앞 공백 · 둘째 줄) + rev. 문서·오버레이는 안 바뀐다.
    400 더할 수 없는 자리(마지막 레벨이 아님 · 괄호 줄 · 템플릿이 섞임) · 409 2단계 결과 없음."""
    from app import server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    ids = _ids(body)
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        try:
            return {**outline_grow.suggest(s.doc, ov, ids), "rev": s.rev}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@router.post("/api/docs/{doc_id}/outline/grow")
def grow(doc_id: str, body: dict = Body(...)):
    """{ids(같은 그릇 · 같은 템플릿의 마지막 레벨 줄들), letter, lead?(앞 공백 칸 수 — 없으면 권하는 값), line2?(text|letter|keep — 기본 text)} —
    템플릿에 새 레벨 L(max+1)을 더하고 그 줄들을 그 레벨로 내린다(Alt+↓ 와 같은 계획 — 접두·모양을 새 슬롯 것으로, 번호형이면 형제 차례로 번호).
    응답 = 개요 편집 응답(_edit + outline{lines, removed, new, focuses}) + grown{tpl, no, level, letter, key, lead, line2, also}. 화면은 이어서 GET …/outline 로 템플릿 요약을 다시 읽는다.
    400 잘못된 값·더할 수 없는 자리 · 409 2단계 결과 없음 · 422 표준 검사에 걸려 되돌림."""
    from app import server
    s0 = server._sess(doc_id)
    if s0.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    ids = _ids(body)
    extra, made = {}, {}

    def make(s):
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        els = [server._para_el(s, i) for i in ids]
        par, seq = server._outline_seq(s, els[0])
        if any(e.getparent() is not par for e in els):
            raise HTTPException(400, "같은 구역·칸 안의 문단들만 함께 바꿀 수 있습니다")
        pos = {it["id"]: k for k, it in enumerate(seq)}
        text_of = lambda pid: s.doc._text(s.doc._ids[pid])  # noqa: E731
        try:
            g = outline_grow.prepare(s.doc, ov, ids, body.get("letter"), body.get("lead"), body.get("line2") or "text")
            plan = outline_edit.plan_level(seq, [pos[i] for i in ids], 1, outline_grow.preview_ov(ov, g), text_of)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        plan["alias"] = {it["id"]: it["host"] for it in seq if it.get("host")}  # 표 제목 줄(② §8-7) → 호스트 문단(server._outline_run 의 rid)
        touched = {pid for a in plan["actions"] for pid in (a.get("id"), a.get("after"), a.get("ref"), a.get("first"), a.get("last"))
                   if isinstance(pid, str) and not pid.startswith("$")}
        before = [s.doc._ids[i] for i in touched if i in s.doc._ids]

        def run():
            outline_grow.apply(ov, g)
            try:
                out = server._outline_run(s, ov, par, plan, extra, "grow", ids)
            except Exception:
                outline_grow.revert(ov, g)  # 문서를 건드리기 전의 실패 — 트랜잭션은 문서를 건드렸을 때만 오버레이를 되돌린다
                raise
            g.pop("_undo", None)
            outline_grow.settle(ov, g, sorted(ids, key=lambda i: pos[i]))  # 대표 = 문서 순 첫 줄
            made.update({"tpl": g["tid"], "no": g["no"], "level": g["level"], "letter": g["slot"]["letter"], "key": g["key"], "lead": g["lead"], "line2": g["line2"],
                         "also": [{"tpl": a, "no": ov["templates"][a]["no"], "level": b} for a, b in g["also"]]})
            out["log"] = {**(out.get("log") or {}), "grow": {k: made[k] for k in ("no", "level", "letter", "lead", "line2")}}
            return out
        return before, run
    out = server._edit(doc_id, make, "outline", {"op": "grow", **{k: body.get(k) for k in ("ids", "letter", "lead", "line2")}})
    if isinstance(out, dict):
        out["outline"] = extra
        out["grown"] = made
    return out
