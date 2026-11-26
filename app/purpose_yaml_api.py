"""문서 목적 YAML 의 끝점(spec_양식작성 ② §5-9) — 꼴은 `app/purpose_yaml.py`. server.py 가 include 한다. 문서를 바꾸지 않고 LLM 도 부르지 않는다 — 쓰기는 사람이 저장할 때만.
프로젝트 = 그 작업의 `task.project`(계정의 작업 뿌리 아래 — works.root 가 계정을 가른다). 프로젝트가 없는 작업(임시 · 미지정)은 읽기만 빈 것 · 쓰기 400.

- `GET /api/docs/{id}/purpose` → {project, why?, text, sha1, exists, counts{purpose, evaluation, requirements, guides, whole, linked}, unmatched[…]}.
- `PUT /api/docs/{id}/purpose` {text, sha1} → 검사 뒤 저장(400 = 틀린 꼴 · 프로젝트 없음 · 409 = 그 사이 바뀜).
- `overlay(s, t3, places)` = place_guides_api.index_of 가 부른다(세션 잠금 안) → purpose_yaml.locate 결과 | None."""
from fastapi import APIRouter, Body, HTTPException

from app import form_guide_yaml as FG
from app import purpose_yaml as PY
from app import works

router = APIRouter()


def project_of(wid):
    """그 작업의 프로젝트 이름 | ""(없음 · 못 읽음)."""
    try:
        w = works.load(wid)
    except Exception:   # 목적은 덤이다 — 못 읽어도 자리 지침은 나간다
        w = None
    task = (w or {}).get("task") if isinstance(w, dict) else None
    return " ".join(str((task or {}).get("project") or "").split()) if isinstance(task, dict) else ""


def overlay(s, t3, places=None):
    """세션 잠금 안 — 이 작업 프로젝트의 문서 목적을 지금 자리에 이은 것 | None(프로젝트 · 파일이 없음)."""
    project = project_of(s.id)
    d = PY.load(project) if project else None
    if not d:
        return None
    if places is None and any(g.get("targets") for g in d.get("guides") or ()):
        from app import form_guide_yaml_api
        places = form_guide_yaml_api.places_cached(s, t3)
    return PY.locate(d, places or {"heads": {}, "tables": {}, "bands": {}}, s.doc.blocks())


def _view(s):
    project = project_of(s.id)
    if not project:
        return {"project": "", "why": "이 작업에 프로젝트가 없습니다 — 프로젝트를 정한 뒤 문서 목적을 적습니다", "text": "", "sha1": "", "exists": False, "counts": {}, "unmatched": []}
    try:
        d, text, sha = PY.read(project)
        broken = ""
    except (ValueError, OSError) as e:
        d, text, sha, broken = PY._empty(project), None, "", str(e)
        p = PY.path_of(project)
        try:
            text = p.read_bytes().decode("utf-8") if p is not None and p.is_file() else None
            sha = FG._sha1(text) if text is not None else ""
        except OSError:
            text = None
    from app import form_guide_yaml_api, heading_runs
    places, _ = form_guide_yaml_api._places(s, heading_runs.tables(s) or {})
    got = PY.locate(d, places, s.doc.blocks())
    counts = {"purpose": bool(d.get("purpose")), "evaluation": len(d.get("evaluation") or ()), "requirements": len(d.get("requirements") or ()), "guides": len(d.get("guides") or ()),
              "whole": len(got["doc"]), "linked": len(got["links"])}
    return {"project": project, "why": broken, "text": text if text is not None else PY.dump(PY._empty(project)), "sha1": sha or "", "exists": text is not None,
            "counts": counts, "unmatched": got["unmatched"][:200], "rev": s.rev}


def _sess_doc(doc_id):
    from app import server
    return server._sess(doc_id)


def known_projects():
    """이 계정의 프로젝트 이름들(작업의 task.project + projects.json 의 기록) — 프로젝트로 읽고 쓰는 끝점이 아무 이름의 파일을 만들지 않게."""
    from app import projects
    out = set()
    for w in works.list_works():
        task = w.get("task") if isinstance(w.get("task"), dict) else {}
        name = " ".join(str(task.get("project") or "").split())
        if name:
            out.add(name)
    try:
        out |= {" ".join(str(k).split()) for k in (projects._read().get("projects") or {})}
    except Exception:   # noqa: BLE001 — 깨진 projects.json 은 작업의 이름만으로
        pass
    return out


def _project(name):
    name = " ".join(str(name or "").split())
    if not name or name not in known_projects():
        raise HTTPException(404, "그런 프로젝트가 없습니다")
    return name


@router.get("/api/purpose/yaml")
def purpose_yaml_get(project: str):
    """프로젝트로 읽기(지침 설정 페이지 /guides — 문서를 열지 않고: spec_양식작성 ② §5-10) → {project, text, sha1, exists}. 404 = 그런 프로젝트가 없음."""
    project = _project(project)
    p = PY.path_of(project)
    try:
        text = p.read_bytes().decode("utf-8") if p is not None and p.is_file() else None
    except OSError as e:
        raise HTTPException(503, f"문서 목적을 읽지 못했습니다: {e}") from e
    return {"project": project, "text": text if text is not None else PY.dump(PY._empty(project)), "sha1": FG._sha1(text) if text is not None else "", "exists": text is not None}


@router.put("/api/purpose/yaml")
def purpose_yaml_put(body: dict = Body(...)):
    """{project, text, sha1} → 검사 뒤 저장(같은 저장 길 — purpose_yaml.save_text) → {project, sha1}. 400 = 틀린 꼴 · 404 = 그런 프로젝트가 없음 · 409 = 그 사이 바뀜."""
    project = _project(body.get("project"))
    text, sha = body.get("text"), body.get("sha1")
    if not isinstance(text, str):
        raise HTTPException(400, "text(YAML 글)가 필요합니다")
    if sha is not None and not isinstance(sha, str):
        raise HTTPException(400, "sha1 은 문자열(읽었을 때의 판)이어야 합니다")
    try:
        _, new = PY.save_text(project, text, expect=sha)
    except FG.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"문서 목적을 저장하지 못했습니다: {e}") from e
    return {"project": project, "sha1": new}


@router.get("/api/docs/{doc_id}/purpose")
def purpose_get(doc_id: str):
    s = _sess_doc(doc_id)
    with s.lock:
        return _view(s)


@router.put("/api/docs/{doc_id}/purpose")
def purpose_put(doc_id: str, body: dict = Body(...)):
    s = _sess_doc(doc_id)
    text, sha = body.get("text"), body.get("sha1")
    if not isinstance(text, str):
        raise HTTPException(400, "text(YAML 글)가 필요합니다")
    if sha is not None and not isinstance(sha, str):
        raise HTTPException(400, "sha1 은 문자열(읽었을 때의 판)이어야 합니다")
    project = project_of(s.id)
    if not project:
        raise HTTPException(400, "이 작업에 프로젝트가 없습니다 — 프로젝트를 정한 뒤 문서 목적을 적습니다")
    try:
        PY.save_text(project, text, expect=sha)
    except FG.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"문서 목적을 저장하지 못했습니다: {e}") from e
    works.log(s.id, "purposeSave", project=project, chars=len(text))
    with s.lock:
        return _view(s)
