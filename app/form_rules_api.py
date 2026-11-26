"""규정 YAML 의 끝점(spec_양식작성 ② §5-9) — 꼴 · 자리 잇기는 `app/form_rules.py`. server.py 가 include 한다. 문서를 바꾸지 않고 LLM 도 부르지 않는다 — 쓰기는 사람이 「YAML 고치기」 로 저장할 때만.

- `GET /api/docs/{id}/form-rules` → {form{key, name, how} | null, why?, sha1, exists, counts{rules, required, whole(문서 전체), linked(자리에 이어진 항목), placesHere}, rules[{id, text, source, required, applies, whole, linked}], unmatched[…]}.
- `GET /api/form-rules/{key}/yaml` → {key, text, sha1, exists} · `PUT …` {text, sha1} → 검사 뒤 저장(400 = 틀린 꼴 · 409 = 그 사이 바뀜 — 고치기 전 글은 이력 forms_history/<키>.rules/).
- `overlay(s, t3)` = place_guides_api.index_of 가 부른다(세션 잠금 안) → form_rules.locate 결과 | None(양식이 없음 · 파일이 없음)."""
from fastapi import APIRouter, Body, HTTPException

from app import form_guide_yaml as FG
from app import form_rules as FR
from app import heading_forms as HF

router = APIRouter()
_FILE = {}    # {양식 키: ((mtime, size), 읽은 것)}


def _yaml(key):
    p = FR.path_of(key)
    try:
        st = p.stat() if p is not None and p.is_file() else None
    except OSError:
        st = None
    mark = (st.st_mtime_ns, st.st_size) if st else None
    hit = _FILE.get(key)
    if hit and hit[0] == mark:
        return hit[1]
    d = FR.load(key) if mark else None
    _FILE[key] = (mark, d)
    return d


def overlay(s, t3, places=None):
    """세션 잠금 안 — 이 문서 양식의 규정을 지금 자리에 이은 것 | None. places = 이미 셈한 form_guide_yaml.doc_places(없으면 여기서 셈)."""
    from app import form_guide_yaml_api
    f = form_guide_yaml_api._form(s)
    if not f:
        return None
    d = _yaml(f["key"])
    if not d or not d.get("rules"):
        return None
    if places is None:
        places = form_guide_yaml_api.places_cached(s, t3)
    return FR.locate(d["rules"], places, s.doc.blocks())


def _view(s):
    from app import form_guide_yaml_api, heading_runs
    f = form_guide_yaml_api._form(s)
    if f is None:
        return {"form": None, "why": "이 문서에 맞는 양식이 없습니다 — 헤딩 추출의 「양식」 에서 고르세요", "sha1": "", "exists": False, "counts": {}, "rules": [], "unmatched": []}
    try:
        d, text, sha = FR.read(f["key"])
        broken = ""
    except (ValueError, OSError) as e:
        d, text, sha, broken = FR._empty(f["key"]), None, None, str(e)
    places, _ = form_guide_yaml_api._places(s, heading_runs.tables(s) or {})
    got = FR.locate(d["rules"], places, s.doc.blocks())
    rows = [{"id": r["id"], "text": r["text"], "source": FR.source_text(r.get("source")), "required": bool(r.get("required", True)), "applies": r.get("applies") or "",
             "whole": not r.get("targets"), "linked": got["links"].get(r["id"], 0)} for r in d["rules"]]
    counts = {"rules": len(rows), "required": sum(r["required"] for r in rows), "whole": sum(r["whole"] for r in rows),
              "linked": sum(1 for r in rows if r["linked"]), "placesHere": len(got["heads"]) + len(got["tables"])}
    return {"form": {"key": f["key"], "name": f["name"], "how": f.get("how")}, "why": broken, "sha1": sha or "", "exists": text is not None, "counts": counts, "rules": rows,
            "unmatched": got["unmatched"][:200], "rev": s.rev}


@router.get("/api/docs/{doc_id}/form-rules")
def form_rules_get(doc_id: str):
    from app import form_guide_yaml_api
    s = form_guide_yaml_api._sess_doc(doc_id)
    with s.lock:
        return _view(s)


def _key(key):
    try:
        HF.check_key(key)
        if HF.get(key) is None:
            raise KeyError(key)
    except (ValueError, KeyError) as e:   # 틀린 키 · 양식 정보가 없는 키 — 규정은 등록된 양식에만 둔다
        raise HTTPException(404, "그런 양식이 없습니다") from e
    return key


@router.get("/api/form-rules/{key}/yaml")
def form_rules_yaml_get(key: str):
    p = FR.path_of(_key(key))
    if p is None:
        raise HTTPException(503, "양식 정보 저장이 꺼져 있습니다(NFM_FORMS)")
    text = p.read_bytes().decode("utf-8") if p.is_file() else None
    return {"key": key, "text": text if text is not None else FR.dump(FR._empty(key)), "sha1": FG._sha1(text) if text is not None else "", "exists": text is not None}


@router.put("/api/form-rules/{key}/yaml")
def form_rules_yaml_put(key: str, body: dict = Body(...)):
    _key(key)
    text, sha = body.get("text"), body.get("sha1")
    if not isinstance(text, str):
        raise HTTPException(400, "text(YAML 글)가 필요합니다")
    if sha is not None and not isinstance(sha, str):
        raise HTTPException(400, "sha1 은 문자열(읽었을 때의 판)이어야 합니다")
    try:
        d, new = FR.save_text(key, text, expect=sha, reason="edit")
    except FG.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"규정을 저장하지 못했습니다: {e}") from e
    return {"key": key, "sha1": new, "rules": len(d["rules"])}
