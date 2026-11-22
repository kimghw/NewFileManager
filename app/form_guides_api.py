"""작성 지침 저장 끝점(spec_작업 ② §21 「작성 지침 저장」) — `GET`·`POST /api/docs/{id}/form-guides`. 모으기는 `app/form_guides.py`(순수), 화면은 `app/static/form_guides.js`.
문서를 바꾸지 않고 LLM 도 부르지 않는다. 어느 TASK 의 hwpx 문서에서나(공통 모듈).

- 저장 = 작업 폴더 `guides.json`(`form_guides.collect` 의 꼴 + `rev`(모은 때의 문서 차례) · `at`). id 는 그때의 것이라 글(지침 · 헤딩 · 표 이름)을 함께 적는다.
- `keep(s)` = 지금 문서에서 모아 저장한다. **문서에 지침이 하나도 없는데 저장해 둔 것이 있으면 그대로 둔다**(「작성요령 삭제」 가 지운 뒤 — 지운 것을 빈 목록으로 덮지 않는다).
  「작성요령 삭제」(`merge_api.form_cleanup_post`)가 지우기 바로 전에 이것을 부른다 — 어느 길로 지워도 지침이 남는다.
- `current(s)` = keep 과 같은 고르기를 하되 쓰지 않는다 — 헤딩 · 표 LLM 판정이 시작할 때 그 자리의 작성 지침을 자료로 싣는다(spec_헤딩_추출 ② §20 · 어느 문서 · 어느 워크플로우에서나).
- 헤딩 · 표 이름은 마지막 분석 결과(`heading_runs.graph` · `heading_runs.tables`)에서 — 없으면 헤딩은 비우고 표 이름은 첫 줄의 글이다. 문서가 분석 뒤 바뀌었어도 그대로 쓴다(없어진 줄은 안 쓰인다 — 다시 돌리라고 하지 않는다)."""
import logging
import time

from fastapi import APIRouter

from app import form_guides, works

router = APIRouter()
log = logging.getLogger("uvicorn.error")
FILE = "guides.json"


def _path(wid):
    f = works.folder(wid)
    return f / FILE if f is not None and (f / "work.json").is_file() else None


def load(wid):
    """저장한 작성 지침 | None(없음 · 못 읽음 · 작업 저장 끔). 읽는 기능(화면 · 에이전트)은 이것으로 읽는다 — 문서에서 다시 모으지 않는다(지운 뒤에는 문서에 없다)."""
    p = _path(wid)
    got = works._read_json(p) if p is not None and p.is_file() else None
    return got if isinstance(got, dict) and isinstance(got.get("items"), list) and isinstance(got.get("marks"), list) else None


def current(s, found=None):
    """지금 쓸 작성 지침 → (그것 | None, 저장본인가?) — `keep` 과 같은 고르기(문서에서 모음 · 문서에 지침이 하나도 없고 저장해 둔 것이 있으면 저장본)이고 **쓰지 않는다**.
    헤딩 · 표 LLM 판정이 시작할 때 자료로 고정한다(heading_runs._guides — spec_헤딩_추출 ② §20). **세션 잠금(s.lock)을 쥔 채** 부른다. hwpx 가 아니면 (None, False)."""
    from app import form_cleanup, heading_runs
    if s.fmt != "hwpx":
        return None, False
    old = load(s.id)
    found = found if found is not None else form_cleanup.find(s.doc)
    if not any(found.get(k) for k in ("tables", "refs", "notes", "marks")) and old is not None and (old["items"] or old["marks"]):
        return old, True
    got = form_guides.collect(s.doc, heading_runs.graph(s), heading_runs.tables(s), found)
    got = form_guides.keep_old(got, old)   # 일부만 지운 뒤 다시 모아도 지운 지침은 남긴다(keep_old — 사라진 항목만 옛 값으로)
    got.update(rev=s.rev, at=time.time())
    return got, False


def keep(s, found=None):
    """지금 문서에서 모아 저장한다 → (저장한 것 | None, 그대로 둠?). **세션 잠금(s.lock)을 쥔 채** 부른다. found = 이미 구한 `form_cleanup.find` 결과(없으면 여기서 구한다)."""
    got, kept = current(s, found)
    if got is None or kept:
        return got, kept
    p = _path(s.id)
    if p is not None:
        works._write_json(p, got)
    return got, False


def _view(s, saved, **more):
    return {"saved": saved, "groups": form_guides.groups(saved), "rev": s.rev, **more}


@router.get("/api/docs/{doc_id}/form-guides")
def form_guides_get(doc_id: str):
    """저장한 작성 지침 → {saved: {version, rev, at, counts{items, marks, marksLinked, headings, tables}, items[…], marks[…]} | null, groups: {headings[{id, text, items[], marks[]}], tables[{id, label, items[], marks[]}], loose[]}, rev}.
    읽기만(모으지 않는다 — 저장본이 없으면 saved null). hwpx 가 아니면 saved null."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        return _view(s, load(s.id) if s.fmt == "hwpx" else None)


@router.post("/api/docs/{doc_id}/form-guides")
def form_guides_post(doc_id: str):
    """지금 문서에서 작성 지침을 모아 저장 → GET 과 같은 몸통(+ kept: true = 문서에 지침이 없어 저장해 둔 것을 그대로 둠). 문서는 안 바뀐다 · 스크립트만."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        saved, kept = keep(s)
        return _view(s, saved, **({"kept": True} if kept else {}))
