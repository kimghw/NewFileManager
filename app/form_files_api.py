"""저장한 양식 · 워크플로우마다의 양식 설정 · 양식으로 시작하기의 끝점(spec_워크플로우 ② §18-9 「양식」 · 고친 규칙 ② §18-12 ⑧). 저장은 app/form_files.py(가벼운 모듈), server.py 가 include 한다.

- `GET /api/form-files` → {files[{id, name, file, fmt, kind, sha256, size, at, usedBy[{job, name, role, mode}]}], slots{워크플로우 키: {target | source: {file, mode}}}, rev(설정의 판), broken,
  jobs[{job, name, kind(목적 문서 종류 | ""), formats, roles[{role, title, docName, kind, formats}](양식을 걸 수 있는 칸 — 수가 1인 칸)}](양식을 걸 수 있는 워크플로우),
  noForm{워크플로우 키: 양식을 걸지 않는 까닭}}
- `POST /api/form-files/from-work/{wid}` {name?, kind?} → 201 {file, made} — 그 작업의 **처음 올린 원본**(새 라운드로 갈라진 작업도) · `POST /api/form-files/from-sample/{name}` {name?, kind?} → 201 — 예제(samples/)
- `POST /api/form-files`(multipart file · name? · kind?) → 201 {file, made} — hwp 는 한글로 hwpx 로 바꿔 저장 · 열 수 없는 파일은 400 · 같은 내용이면 있던 양식(made false). kind 를 비우면 양식 이름 문단으로 짐작(연구개발계획서 → plan · 연차보고서 → report).
- `PUT /api/form-files/{id}` {name?, kind?} → {file} · `DELETE /api/form-files/{id}` → {deleted}(설정에 쓰는 양식은 409) · `GET /api/form-files/{id}/file` → 그 파일.
- `PUT /api/workflow-slots/{job}` {target?: {file, mode: "default" | "fixed"} | null, source?: …}(보낸 칸만 — 수가 1인 칸: 목적 · 이관의 원본) → {slot(목적 칸), slots{칸: …}, rev} — 400 = 양식을 걸 수 없는 워크플로우 · 칸(없음 · 여럿) · 문서 종류 · 형식이 안 맞음 · 404 = 없는 양식.
- `POST /api/workflow-start/source` {job, main, request, source: {form, sha256?, rev?}} → {docId, name, task, form} — 원본 칸을 그 양식으로(목적 작업의 묶음에 원본 종류로 적는다 — 아래 함수 글).
- `POST /api/workflow-start` {job, request(같은 시작을 다시 보낼 때의 열쇠), project?, temp?, target: {form(양식 id), sha256?, rev?}} → {docId, name, task, round, temp, form{id, name, mode}} —
  **고정 · 기본값은 여기서 지킨다**(② §18-12 ⑧): 서버가 워크플로우 · 양식 · 해시 · 설정의 판을 견준 뒤 그 양식으로 **새 작업**을 만들어 그 워크플로우의 다음 라운드로 묶고, 그 작업에 쓴 양식을 적는다(work.json `form`). 같은 request 를 다시 보내면 같은 작업을 돌려준다.
  409 = 고정된 양식과 다름(fixedForm) · 양식이 바뀜(staleForm) · 설정이 바뀜(staleSlots). 올린 파일로 시작하는 길은 지금 것 그대로이고(`start-task`), 고정 설정이 있으면 그 끝점이 거절한다(server.work_start_task)."""
import threading
from pathlib import PurePath

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from app import form_files

router = APIRouter()
NO_FORM = {"style_copy": "서식을 가져올 문서는 내용을 받는 문서가 아니라 양식을 걸지 않습니다"}   # 목적 문서 칸이 없는 워크플로우(② §18-12 ⑧)
FORM_GUESS = {"연구개발계획서": "plan", "연차보고서": "report"}
_STARTS, _STARTS_LOCK, STARTS_MAX = {}, threading.Lock(), 200   # request → 결과(같은 시작을 다시 보내면 같은 작업)


ROLE_WORD = {"target": "목적 문서", "source": "원본 문서"}   # 칸의 화면 이름(등록부 roles 의 title 이 없을 때)


def rule(job, role="target"):
    """그 워크플로우의 그 문서 칸 → {job, name, role, title, docName, kind(그 칸의 문서 종류 | ""), formats} — 양식을 걸 수 없으면 HTTPException 400.
    걸 수 있는 칸 = 등록부 roles 에 있고 **수가 1인 칸**(2026-11-20 사용자 "각 1이 되는것들은 특정 문서로 지정할 수 있도록, default 로" — spec_워크플로우 ② §18-9: 목적 칸 · 이관의 원본 칸 /
    원본이 여럿인 칸 — 취합의 기관 문서 — 은 아니다)."""
    from app import custom_tasks, server, workflow, works
    task = workflow.task_of(job) if isinstance(job, str) and job else None
    if task is None or task.get("soon") or not server._job_ok(job):
        raise HTTPException(400, "양식을 걸 수 없는 워크플로우입니다(모르는 워크플로우 · 준비 중)")
    if job in NO_FORM:
        raise HTTPException(400, NO_FORM[job])
    if role not in form_files.ROLES:
        raise HTTPException(400, "모르는 문서 칸입니다 — target(목적 문서) · source(원본 문서)")
    r = next((x for x in task.get("roles") or () if x["role"] == role), None)
    if r is None:
        raise HTTPException(400, f"이 워크플로우에는 {ROLE_WORD[role]} 칸이 없습니다")
    title = r.get("title") or ROLE_WORD[role]
    if r.get("many"):
        raise HTTPException(400, f"{title} 칸은 문서가 여럿이라 양식을 걸지 않습니다 — 문서가 하나인 칸에만 겁니다")
    name = task.get("name") or (workflow.catalog()[0].get(job) or {}).get("name") or job
    own = r.get("kind") if r.get("kind") in form_files.KINDS else ""
    kind = (works.TARGET_FILE.get(job) or own or "") if role == "target" else own
    formats = ["hwpx", "docx"] if server.TASK_KIND.get(job) == "general" and not custom_tasks.is_key(job) else ["hwpx"]
    return {"job": job, "name": name, "role": role, "title": title, "docName": r.get("name") or "", "kind": kind, "formats": formats}


def fits(f, r):
    """그 양식을 그 워크플로우의 그 칸에 걸 수 있나 → 까닭 글 | ""."""
    if f["fmt"] not in r["formats"]:
        return f"워크플로우 「{r['name']}」 은 {' · '.join(r['formats'])} 문서로 합니다 — 이 양식은 {f['fmt']} 입니다"
    if r["kind"] and f["kind"] != r["kind"]:
        from app import works
        return (f"워크플로우 「{r['name']}」 의 {r.get('title') or ROLE_WORD.get(r.get('role'), '목적 문서')}는 {works.FILE_LABEL.get(r['kind'], r['kind'])}입니다 — "
                "이 양식의 문서 종류가 다릅니다(양식의 문서 종류를 먼저 고치세요)")
    return ""


def fixed_slot(job, file):
    """그 워크플로우에서 문서 종류 file 이 드는 칸에 건 **고정** 양식 → {file, mode, form, role, title} | None — 서버의 고정 검사(server._fixed_form_check · work_start_task)가 칸마다 쓴다.
    목적 종류가 없는 워크플로우(일반 편집 · 서식 복사)는 늘 목적 칸 · 원본 칸 = 등록부의 원본 역할이 수가 1이고 그 종류일 때."""
    from app import workflow, works
    box = form_files.listing()["slots"].get(job) or {}
    if not any(v.get("mode") == "fixed" for v in box.values()):
        return None
    tkind = works.TARGET_FILE.get(job)
    if tkind is None or file == tkind:
        role = "target"
    else:
        task = workflow.task_of(job)
        src = next((x for x in (task or {}).get("roles") or () if x["role"] == "source" and not x.get("many")), None)
        role = "source" if src and src.get("kind") == file else None
    v = box.get(role) if role else None
    if not v or v.get("mode") != "fixed":
        return None
    return {**form_files.slot(job, role), "role": role, "title": ROLE_WORD[role]}


def _jobs():
    """양식을 걸 수 있는 워크플로우 → [{job, name, kind, formats(목적 칸의 것 — 옛 화면이 읽는 꼴 그대로), roles[{role, title, docName, kind, formats}](걸 수 있는 칸 — 원본 → 목적 차례)}]."""
    from app import custom_tasks, server
    out = []
    for job in [j for j in server.TASK["job"] if j] + [t["key"] for t in custom_tasks.all()]:
        try:
            top = rule(job)
        except HTTPException:
            continue
        roles = []
        for role in ("source", "target"):
            try:
                x = rule(job, role)
            except HTTPException:
                continue
            roles.append({k: x[k] for k in ("role", "title", "docName", "kind", "formats")})
        out.append({"job": job, "name": top["name"], "kind": top["kind"], "formats": top["formats"], "roles": roles})
    return out


def _refused(e):
    return HTTPException(409 if isinstance(e, form_files.Refused) else 400, str(e))


@router.get("/api/form-files")
def form_files_get():
    """저장한 양식 목록 · 워크플로우마다의 양식 설정 · 양식을 걸 수 있는 워크플로우."""
    got, jobs = form_files.listing(), _jobs()
    names = {j["job"]: j["name"] for j in jobs}
    used = {}
    for job, box in got["slots"].items():
        for role, v in box.items():
            used.setdefault(v["file"], []).append({"job": job, "name": names.get(job, job), "role": role, "mode": v["mode"]})
    return {**got, "files": [{**f, "usedBy": used.get(f["id"], [])} for f in got["files"]], "jobs": jobs, "noForm": dict(NO_FORM)}   # noForm = 양식을 걸지 않는 워크플로우와 까닭(화면의 「문서 칸」 줄)


def _store(shown, blob, name="", kind=""):
    """양식 하나를 저장한다(이미 hwpx · docx 로 바꾼 뒤의 이름 · 바이트) → 응답 {file, made}. 문서로 열리는지 확인한 뒤에 저장 · kind 가 비면 양식 이름 문단으로 짐작(hwpx).
    올리기 · 작업의 처음 올린 원본 · 예제가 같이 쓴다(동기 — 부르는 쪽이 스레드에서)."""
    from app import server
    fmt = server.fmt_of(shown)
    if fmt is None or fmt == "hwp":
        raise HTTPException(400, "양식은 hwp · hwpx · docx 파일로 저장합니다")
    if len(blob) > server.MAX_MB * 2 ** 20:
        raise HTTPException(413, f"{server.MAX_MB} MB 보다 큰 파일은 저장할 수 없습니다")
    if kind not in form_files.KINDS:
        raise HTTPException(400, "모르는 문서 종류입니다")
    try:
        blocks = server.FORMATS[fmt]["cls"](blob).blocks()
    except Exception as e:  # noqa: BLE001 — 열 수 없는 파일은 양식으로 저장하지 않는다
        raise HTTPException(400, f"{fmt} 문서로 열 수 없는 파일입니다: {e}") from e
    if kind == "" and fmt == "hwpx":
        kind = FORM_GUESS.get(server.PROFILE.form_of(blocks), "")
    try:
        f, made = form_files.add(str(name or "").strip() or PurePath(shown).stem, shown, fmt, blob, kind)
    except ValueError as e:
        raise _refused(e) from e
    return {"file": {**f, "usedBy": [{"job": j, "role": r, "mode": m} for j, r, m in form_files.uses(f["id"])]}, "made": made}


@router.post("/api/form-files", status_code=201)
async def form_files_post(file: UploadFile = File(...), name: str = Form(""), kind: str = Form("")):
    """양식 파일을 저장한다 — 올린 그대로(hwp 는 hwpx 로 바꿔서). 문서로 열리는지 확인한 뒤에 저장한다."""
    from starlette.concurrency import run_in_threadpool

    from app import server
    shown, blob = file.filename or "양식.hwpx", await file.read()
    if shown.lower().endswith(".hwp"):
        shown, blob = await run_in_threadpool(server._from_hwp, shown, blob)   # 바꾼 뒤의 이름 · 바이트로 저장한다(② §18-12 ⑧)
    return await run_in_threadpool(_store, shown, blob, name, kind)


@router.post("/api/form-files/from-work/{wid}", status_code=201)
def form_files_from_work(wid: str, body: dict = Body(default={})):
    """작업의 **처음 올린 원본**을 양식으로 저장한다(지금 편집 상태가 아니다 — 편집한 것을 양식으로 삼으려면 내려받아 올린다: ② §18-9 「넣는 길」).
    {name?, kind?} — 이름을 비우면 작업의 파일 이름 · 종류를 비우면 그 작업의 문서 종류(사업계획서 · 연차보고서), 그 밖은 양식 이름 문단으로 짐작.
    「양식으로 저장」 은 「빈 양식이라 예시 칸을 덮어도 됨」 과 다르다(② §18-12 ⑧ — 작성한 문서를 양식으로 저장해도 그 글을 예시로 보지 않는다: 그것은 양식 정보의 일)."""
    from app import server, works
    w = works.work(wid) if isinstance(wid, str) else None
    if w is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    blob = server._round_uploaded_original(w)   # 새 라운드로 갈라진 작업도 처음 올린 원본으로(409 = 원본을 못 읽음)
    shown = f"{PurePath(w.get('name') or 'document').stem}.{w.get('format') or 'hwpx'}"
    kind = body.get("kind") if isinstance(body.get("kind"), str) else ((w.get("task") or {}).get("file") if (w.get("task") or {}).get("file") in ("plan", "report") else "")
    return _store(shown, blob, body.get("name") if isinstance(body.get("name"), str) else "", kind)


@router.post("/api/form-files/from-sample/{name}", status_code=201)
def form_files_from_sample(name: str, body: dict = Body(default={})):
    """예제 파일(samples/ — GET /api/samples 의 목록)을 양식으로 저장한다. {name?, kind?}."""
    from app import server
    p = server.SAMPLES / name
    if p.parent != server.SAMPLES or not p.is_file() or server.fmt_of(p.name) in (None, "hwp"):
        raise HTTPException(404, "예제가 없습니다")
    return _store(p.name, p.read_bytes(), body.get("name") if isinstance(body.get("name"), str) else "", body.get("kind") if isinstance(body.get("kind"), str) else "")


@router.put("/api/form-files/{fid}")
def form_files_put(fid: str, body: dict = Body(...)):
    try:
        f = form_files.update(fid, name=body.get("name") if "name" in body else None, kind=body.get("kind") if "kind" in body else None)
    except ValueError as e:
        raise _refused(e) from e
    if f is None:
        raise HTTPException(404, "그런 양식이 없습니다")
    return {"file": f}


@router.delete("/api/form-files/{fid}")
def form_files_delete(fid: str):
    try:
        if not form_files.delete(fid):
            raise HTTPException(404, "그런 양식이 없습니다")
    except ValueError as e:
        raise _refused(e) from e
    return {"deleted": True}


@router.get("/api/form-files/{fid}/file")
def form_files_file(fid: str):
    from app import server
    f, blob = form_files.get(fid), form_files.data(fid)
    if f is None or blob is None:
        raise HTTPException(404, "그런 양식이 없습니다")
    from urllib.parse import quote
    name = f"{PurePath(f['file'] or f['name']).stem}.{f['fmt']}"
    return Response(blob, media_type=server.FORMATS[f["fmt"]]["mime"], headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.put("/api/workflow-slots/{job}")
def workflow_slots_put(job: str, body: dict = Body(...)):
    """워크플로우 설정 — 수가 1인 문서 칸(target 목적 · source 원본)에 양식을 건다(기본값 · 고정) · 푼다(null). 보낸 칸만 바꾼다 — 모두 검사한 뒤에 쓴다(하나가 틀리면 아무것도 안 바꿈).
    → {slot(목적 칸 — 옛 꼴), slots{칸: 설정 | None}, rev}."""
    roles = [r for r in form_files.ROLES if r in body]
    if not roles:
        raise HTTPException(400, "target · source 가운데 바꿀 칸을 보내세요({file, mode} 또는 null)")
    todo = []
    for role in roles:
        r, want = rule(job, role), body[role]
        if want is None:
            todo.append((role, None, None))
            continue
        if not isinstance(want, dict) or not isinstance(want.get("file"), str):
            raise HTTPException(400, f"{role} 은 {{file, mode}} 또는 null")
        f = form_files.get(want["file"])
        if f is None:
            raise HTTPException(404, "그런 양식이 없습니다")
        why = fits(f, r)
        if why:
            raise HTTPException(400, why)
        todo.append((role, f["id"], want.get("mode") or "default"))
    try:
        rev = None
        for role, fid, mode in todo:
            rev = form_files.slot_set(job, role, fid, mode) if fid else form_files.slot_set(job, role, None)
    except ValueError as e:
        raise _refused(e) from e
    return {"slot": form_files.slot(job), "slots": {r: form_files.slot(job, r) for r in form_files.ROLES}, "rev": rev}


@router.post("/api/workflow-start")
def workflow_start(body: dict = Body(...)):
    """저장한 양식으로 워크플로우를 새로 시작한다 — 그 양식으로 새 작업을 만들어 그 워크플로우의 다음 라운드로 묶는다(목적 문서). 문서 화면을 열지 않는다(화면이 받은 작업 id 로 잇는다)."""
    from app import server, works
    job, req, want = body.get("job"), body.get("request"), body.get("target")
    if not isinstance(req, str) or not 8 <= len(req) <= 64 or not isinstance(want, dict) or not isinstance(want.get("form"), str):
        raise HTTPException(400, "request(8~64자) · target{form} 이 있어야 합니다")
    r = rule(job)
    with _STARTS_LOCK:
        if req in _STARTS:
            return _STARTS[req]   # 같은 시작을 다시 보냄 — 같은 작업
        f, slot = form_files.get(want["form"]), form_files.slot(job)
        if f is None:
            raise HTTPException(404, "그런 양식이 없습니다")
        if slot and slot["mode"] == "fixed" and slot["file"] != f["id"]:
            return JSONResponse({"reason": "fixedForm", "message": f"워크플로우 「{r['name']}」 의 목적 문서는 양식 「{(slot['form'] or {}).get('name', '지워진 양식')}」 으로 고정돼 있습니다"}, status_code=409)
        if "rev" in want and want["rev"] != form_files.listing()["rev"]:
            return JSONResponse({"reason": "staleSlots", "message": "워크플로우의 양식 설정이 바뀌었습니다 — 다시 읽은 뒤 시작하세요"}, status_code=409)
        if want.get("sha256") and want["sha256"] != f["sha256"]:
            return JSONResponse({"reason": "staleForm", "message": "양식이 바뀌었습니다 — 다시 읽은 뒤 시작하세요"}, status_code=409)
        why = fits(f, r)
        if why:
            raise HTTPException(400, why)
        blob = form_files.data(f["id"])
        if blob is None:
            raise HTTPException(500, "양식 파일을 읽지 못했습니다")
        mode = slot["mode"] if slot and slot["file"] == f["id"] else ""
        opened = server._open(f"{PurePath(f['file'] or f['name']).stem}.{f['fmt']}", blob, source="form", new=True)
        wid = opened["docId"]
        works.update(wid, form={"id": f["id"], "sha256": f["sha256"], "name": f["name"], "mode": mode})   # 그 작업에 쓴 양식을 적는다
        try:
            started = server.work_start_task(wid, {"project": body.get("project"), "job": job, "file": r["kind"], "temp": body.get("temp") is True})
        except HTTPException:
            try:
                server.work_delete(wid)   # 묶지 못한 작업은 남기지 않는다
            except HTTPException:
                pass
            raise
        out = {"docId": wid, "name": opened["name"], "task": started["task"], "round": started["round"], "temp": started["temp"], "form": {"id": f["id"], "name": f["name"], "mode": mode}}
        _STARTS[req] = out
        while len(_STARTS) > STARTS_MAX:
            _STARTS.pop(next(iter(_STARTS)))
        return out


@router.post("/api/workflow-start/source")
def workflow_start_source(body: dict = Body(...)):
    """원본 문서 칸을 저장한 양식으로 채운다(spec_워크플로우 ② §18-9 「원본 칸에 건 양식을 쓰는 때」) — 목적 문서를 만든 뒤(올리기 · 양식 어느 쪽이든) 부른다.
    {job, main(목적 문서 작업 id), request(8~64자 — 같은 요청을 다시 보내면 같은 작업), source: {form, sha256?, rev?}} → {docId, name, task, form{id, name, mode}}.
    그 양식으로 새 작업을 만들어 목적 작업의 묶음(프로젝트 · 워크플로우 · 라운드)에 원본 종류로 적는다 — 올린 원본(화면 hfAddSource 의 PUT …/task)과 같은 묶기 · 작업에 쓴 양식을 적는다.
    409 = 목적 문서가 그 워크플로우의 프로젝트에 묶여 있지 않음(notTarget) · 고정된 양식과 다름(fixedForm) · 설정 · 양식이 바뀜(staleSlots · staleForm). 기본 분석은 부르는 쪽이(올린 원본과 같게)."""
    from app import server, works
    job, req, main, want = body.get("job"), body.get("request"), body.get("main"), body.get("source")
    if not isinstance(req, str) or not 8 <= len(req) <= 64 or not isinstance(main, str) or not isinstance(want, dict) or not isinstance(want.get("form"), str):
        raise HTTPException(400, "request(8~64자) · main(목적 문서 작업 id) · source{form} 이 있어야 합니다")
    r = rule(job, "source")
    key = "source:" + req
    with _STARTS_LOCK:
        if key in _STARTS:
            return _STARTS[key]   # 같은 요청을 다시 보냄 — 같은 작업
        w = works.work(main)
        if w is None:
            raise HTTPException(404, "목적 문서 작업이 없습니다")
        t, tkind = w.get("task") or {}, works.TARGET_FILE.get(job)
        if t.get("job") != job or not t.get("project") or (tkind and t.get("file") != tkind):
            return JSONResponse({"reason": "notTarget", "message": "목적 문서가 이 워크플로우의 프로젝트에 묶여 있지 않아 원본 문서를 넣을 곳이 없습니다 — 목적 문서부터 시작하세요"}, status_code=409)
        f, slot = form_files.get(want["form"]), form_files.slot(job, "source")
        if f is None:
            raise HTTPException(404, "그런 양식이 없습니다")
        if slot and slot["mode"] == "fixed" and slot["file"] != f["id"]:
            return JSONResponse({"reason": "fixedForm", "message": f"워크플로우 「{r['name']}」 의 {r['title']}는 양식 「{(slot['form'] or {}).get('name', '지워진 양식')}」 으로 고정돼 있습니다"}, status_code=409)
        if "rev" in want and want["rev"] != form_files.listing()["rev"]:
            return JSONResponse({"reason": "staleSlots", "message": "워크플로우의 양식 설정이 바뀌었습니다 — 다시 읽은 뒤 시작하세요"}, status_code=409)
        if want.get("sha256") and want["sha256"] != f["sha256"]:
            return JSONResponse({"reason": "staleForm", "message": "양식이 바뀌었습니다 — 다시 읽은 뒤 시작하세요"}, status_code=409)
        why = fits(f, r)
        if why:
            raise HTTPException(400, why)
        blob = form_files.data(f["id"])
        if blob is None:
            raise HTTPException(500, "양식 파일을 읽지 못했습니다")
        mode = slot["mode"] if slot and slot["file"] == f["id"] else ""
        opened = server._open(f"{PurePath(f['file'] or f['name']).stem}.{f['fmt']}", blob, source="form", new=True)
        wid = opened["docId"]
        works.update(wid, form={"id": f["id"], "sha256": f["sha256"], "name": f["name"], "mode": mode})   # 그 작업에 쓴 양식(고정 검사가 본다)
        try:
            got = server.work_task(wid, {"kind": server.TASK_KIND.get(job, "rnd"), "file": r["kind"], "job": job, "project": t["project"], **({"round": t["round"]} if t.get("round") else {})})
        except HTTPException:
            try:
                server.work_delete(wid)   # 묶지 못한 작업은 남기지 않는다
            except HTTPException:
                pass
            raise
        works.log(main, "sourceForm", source=wid, form=f["id"])
        out = {"docId": wid, "name": opened["name"], "task": got["task"], "form": {"id": f["id"], "name": f["name"], "mode": mode}}
        _STARTS[key] = out
        while len(_STARTS) > STARTS_MAX:
            _STARTS.pop(next(iter(_STARTS)))
        return out
