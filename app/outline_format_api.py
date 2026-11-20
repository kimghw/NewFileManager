"""개요 줄 자리 규칙 API(spec_hwpx_웹편집 ② §8-1) — 템플릿 레벨(슬롯)의 레터 위치·둘째 줄을 정하고 그 레벨 줄 모두에 적용한다(PUT …/outline/slots),
글을 고쳐 둔 개요 줄을 기본 규칙대로 맞춘다(POST …/outline/align). server.py 가 include 한다(구분 라벨 지정 `heading_labels_api` 와 같은 꼴). 자리 계산·규칙은 `app/outline_pos.py`, 읽기는 `GET /api/docs/{id}/outline` 의 `templates[].slots`."""
from fastapi import APIRouter, Body, HTTPException

from app import outline_edit, outline_pos

router = APIRouter()


@router.post("/api/docs/{doc_id}/outline/align")
def align_edited(doc_id: str):
    """글을 고쳐 둔 개요 줄 가운데 둘째 줄이 아직 안 맞은 것을 지금 맞춘다 — 이 기능 전에 고친 줄·서버가 꺼져 있던 동안의 줄(화면이 문서를 열 때 그런 줄이 보이면 한 번 부른다).
    글 고침(PATCH)과 같은 길: 기본 규칙(문단이 첫 줄 값을 안 가졌을 때만), 실행 취소 묶음 없음, 종류 `text` 그대로 — 손으로 문단 모양을 바꾼 줄(format)은 안 건드린다.
    → {formats{문단 id: 서식 요약}, …편집 상태}. 2단계 결과가 없거나 docx 면 빈 formats."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        server._fenced(s)   # 워크플로우 실행이 이 문서를 바꾸는 동안은 409(울타리 — spec_워크플로우 ② §17-8)
        ov = server._outline_ov(s) if s.fmt == "hwpx" else None
        formats = {}
        if ov:
            m = outline_pos.Measure(s.doc)
            for pid in sorted((s.text_edited() - s.formatted - s.removed) & set(ov["lines"])):
                fmt = outline_pos.align_quiet(s.doc, ov, pid, measure=m)
                if fmt is not None:
                    formats[pid] = fmt
            if formats:
                server._bump(s, "outlineAlign", ids=sorted(formats))
        return {"formats": formats, **s.state()}


@router.post("/api/docs/{doc_id}/outline/slots/{tpl}/{level}/preview")
def slot_preview(doc_id: str, tpl: str, level: int, body: dict = Body(...)):
    """PUT …/slots/{tpl}/{level} 와 같은 몸 {line2, mm?, letterMm?} — 적용하면 그 레벨 줄들이 어떻게 바뀌나(문서·규칙은 안 바뀜, 실행 취소 기록 없음).
    → outline_pos.preview 꼴 {lines, changed, same, skipped, error, rep, slot, groups[{count, changed, before, after, paras, more}]} + rev.
    400 잘못된 값 · 404 그런 레벨 없음 · 409 2단계 결과 없음."""
    from app import server, outline_match
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    try:
        pos = outline_pos.clean_pos(body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")
        out = outline_pos.preview(s.doc, ov, tpl, level, pos, order=outline_match._order(s.doc))
        return {**out, "rev": s.rev}


@router.put("/api/docs/{doc_id}/outline/slots/{tpl}/{level}")
def slot_put(doc_id: str, tpl: str, level: int, body: dict = Body(...)):
    """{line2: "text"(글 시작에 맞춤) | "mm"(직접 — mm: 값) | "keep"(문단 서식 그대로), letterMm?(레터 위치 — 없으면 그대로)} — 슬롯 규칙을 저장하고
    그 레벨 줄 모두의 문단 여백(왼쪽·첫 줄)을 맞춘다. 구조 편집 트랜잭션 하나(문서 전체 표준 검사 · 실행 취소 1 — 규칙도 함께 돌아감 · 기록 `outlineFormat`).
    → {formats{문단 id: 서식 요약}, aligned(바뀐 문단 수), outline(GET /outline 과 같은 꼴), …편집 상태}.
    400 잘못된 값·괄호 줄 레벨 · 404 그런 레벨 없음 · 409 2단계 결과 없음 · 422 표준 검사에 걸려 되돌림."""
    from app import server  # 트랜잭션(_transact)·세션은 server 것 — 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    try:
        pos = outline_pos.clean_pos(body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        if outline_edit._slot(ov, tpl, level) is None:
            raise HTTPException(404, "그런 템플릿 레벨이 없습니다")
        ids = outline_pos.slot_lines(ov, tpl, level)
        if ids and all(ov["lines"][i].get("role") in outline_edit.ROOTED for i in ids):
            raise HTTPException(400, "괄호 줄(구분 라벨·괄호 소제목)은 글 전체가 레터라 자리 규칙을 두지 않습니다")
        formats = {}

        def run():
            formats.update(outline_pos.apply_slot(s.doc, ov, tpl, level, pos))
            return {"hosts": [], "formatted": set(formats), "struct": set(), "origin": {}, "anchor": None,
                    "log": {"tpl": ov["templates"][str(tpl)].get("no"), "level": level, "pos": pos, "aligned": len(formats)}}
        out, after = server._transact(s, run, "outlineFormat", req={"tpl": tpl, "level": level, **{k: body.get(k) for k in ("line2", "mm", "letterMm")}},
                                      check=server._full_check)
        if after is None:
            return out
        edited = s.edited()
        return {"formats": formats, "aligned": len(formats), "outline": outline_pos.view(s.doc, s.outline),
                "edited": sorted(edited), "original": {i: s.orig_texts.get(i, "") for i in edited}, **s.state()}
