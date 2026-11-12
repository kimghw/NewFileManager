"""양식 정보 API(spec_헤딩_추출 ② §12) — 양식마다 md 하나(`app/heading_forms.py`)를 읽고·고치고, 문서마다 어느 양식인지 본다·고른다.
server.py 가 include 한다(표 모듈 `tables_api` 와 같은 꼴)."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_forms as F
from app import heading_rules

router = APIRouter()

_PUBLIC = ("key", "name", "match", "sha1", "updated", "size", "broken", "path")


def _sess(doc_id):
    from app import server  # server 가 이 모듈을 include 하므로 부를 때 가져온다(순환 import 피함)
    return server._sess(doc_id)


def _key(key):
    try:
        return F.check_key(key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _dir():
    d = F.forms_dir()
    return str(d) if d is not None else None


@router.get("/api/headings/forms")
def forms_list():
    return {"dir": _dir(), "forms": F.listing()}


@router.get("/api/headings/forms/{key}")
def form_get(key: str):
    try:
        return F.get(_key(key))
    except KeyError:
        raise HTTPException(404, f"그런 양식 정보가 없습니다: {key}") from None


@router.put("/api/headings/forms/{key}")
def form_put(key: str, body: dict = Body(...)):
    """{text, sha1?(읽었을 때의 sha1 — 새 양식이면 ""), reason?} → 저장한 양식 정보. 그 사이 바뀌었으면 409."""
    key = _key(key)
    try:
        return F.save(key, body.get("text"), expect=body.get("sha1"), reason=str(body.get("reason") or "화면")[:200])
    except heading_rules.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"양식 정보를 저장하지 못했습니다: {e}") from e


def doc_view(s):
    """{form: 이 문서에 맞은 양식(how 포함) | null, choice: 고른 키 | "" | null(자동), forms: 목록, suggest: {key, text}(새로 만들 때), dir}."""
    f = F.for_session(s)
    return {"form": {**{k: f[k] for k in _PUBLIC}, "how": f["how"]} if f else None, "choice": F.choice(s.id), "forms": F.listing(),
            "suggest": F.suggest(s.name, F.doc_sha(s)), "dir": _dir()}


@router.get("/api/docs/{doc_id}/headings/form")
def doc_form(doc_id: str):
    return doc_view(_sess(doc_id))


@router.put("/api/docs/{doc_id}/headings/form")
def doc_form_put(doc_id: str, body: dict = Body(...)):
    """{form: 양식 키 | ""(양식 없음으로 고정) | null(자동)} — 이 문서의 양식을 고른다."""
    s = _sess(doc_id)
    if "form" not in body:
        raise HTTPException(400, "form 이 없습니다(양식 키 · \"\" · null)")
    try:
        F.set_choice(s.id, body["form"])
    except KeyError:
        raise HTTPException(404, f"그런 양식 정보가 없습니다: {body['form']}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"고른 양식을 저장하지 못했습니다: {e}") from e
    return doc_view(s)
