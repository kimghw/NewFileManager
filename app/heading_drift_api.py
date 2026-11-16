"""뼈대 유지 API(spec_헤딩_추출 ② §17) — 지금 문서를 2·3단계 뼈대와 견준 것(새 레터·새 서식 · 새 표·모양이 바뀐 표). server.py 가 include 한다.
견주기는 app/heading_drift.py(스크립트만 — 문서·결과를 바꾸지 않고 실행으로 저장하지 않는다)."""
from fastapi import APIRouter, HTTPException

from app import heading_drift

router = APIRouter()


@router.get("/api/docs/{doc_id}/headings/drift")
def drift_get(doc_id: str):
    """{rev, stage2: null | {moved, letters[{scope, kind, shape, letter, text, count, paras[]}], formats[{…, fmt, name, known[]}](새 서식 — 되풀이해 쓰는 것),
    wrong[formats 와 같은 꼴](잘못된 서식 — 되풀이되지 않는 것), counts{letters, letterParas, formats, formatParas, wrong, wrongParas}, formatsChecked}, stage3: null | {moved, new[{id, rows, cols, host}], changed[{id, rows, cols, host, was[행, 열], heads{text, gone, new}, examples[{what, role, was?, now?}]}](헤더가 바뀐 표),
    gone, resized(행·열 수만 달라진 표 — 알리지 않음), counts{new, changed, gone, resized}}, extracted, seconds}.
    문서가 그 결과를 만든 뒤 바뀌었고 지금 1단계가 옛것이면 여기서 문서를 메모리로 다시 뽑는다(큰 문서 1~2초 — 같은 문서 차례는 기억해 둔 답)."""
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "헤딩 추출은 지금 hwpx 만 됩니다")
    return heading_drift.check(s)
