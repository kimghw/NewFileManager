"""지침 작성 · 문서 라이브러리에서 자료 가져오기 끝점(spec_양식작성 ② §4 · §5) — 요청 글 · 자리 고르기는 `app/guide_write.py`(순수), 문서 라이브러리 서버(doclib/ · 따로 선 서버)는 `app/doclib_client.py` 로만 읽는다.
hwpx 문서만 · 어느 워크플로우의 문서에서나(공통 모듈 — 워크플로우 「양식 작성」 이 쓴다).

- `GET /api/doclib` → {url, alive, why, llm, docs[{id, name, ext, pages, org, topic, bytes, sha256, raw(원본을 글로 읽어 자료로 줄 수 있나), running, extracts[끝난 것 — {id, focus, span, at, chars, figures, formulas, open}]}]} — 문서 라이브러리 서버의 문서 · 추출 목록(그 서버가 꺼져 있으면 alive false + 까닭).
- `POST /api/doclib/docs`(multipart file) → 그 서버의 {doc, created} — 자료(참조) 문서를 문서 라이브러리에 올린다(양식 작성의 「참조 문서 올리기…」 — 새 탭 없이 · 추출은 그 서버에서).
- `POST /api/docs/{id}/agent/material/library` {extract} → 그 추출의 MD 를 이 문서의 **자료**로 가져온다(에이전트 보기의 자료와 같은 저장소 · 같은 꼴 — 같은 것이 있으면 그것: reused) → 자료 보기.
  {doc}(extract 없이) → 등록한 문서의 **원본 파일**을 글로 읽어 자료로(추출 전인 문서 — pdf · docx · hwpx · 20 MB 까지: hwp 는 400). 고르는 곳 = 에이전트 보기의 「라이브러리」(doc_agent.js) · 2열 「자료 가져오기」(form_write.js — 추출만).
- `GET /api/docs/{id}/guide-write` → {hwpx, enabled(LLM), places[자리 — guide_write.places], materials[자료 보기], run(도는 · 마지막 실행 | null), limits{places, note}}. 문서 안 바뀜.
- `POST /api/docs/{id}/guide-write/run` {places: [자리 id…], materials: [자료 id…], note} → 자리마다 **문서 에이전트의 한 턴**을 배경에서 돌린다(유료 LLM · 자리마다 호출 1번 이상 — 같이 2개까지) → {run}.
  제안은 에이전트 보기의 턴 · 제안 카드로 남는다(반영은 그 카드의 「문서에 반영」 — 문서는 여기서 바뀌지 않는다). 409 = 이 문서의 지침 작성이 이미 돈다 · 양식 검토가 없거나 답하지 않은 물음이 있다(`form_review_api.gate` — 쓰기 전에 묻는다) · 503 = LLM 없음.
  자리마다의 요청 글에 양식 검토의 글(사람이 정해 준 것 + 그 자리의 작성 방향 — `form_review_api.plans`)을 싣는다.
- `GET …/guide-write/run` → {run} · `POST …/guide-write/stop` → 남은 자리를 돌리지 않는다(도는 턴은 끝까지).
실행의 상태는 이 프로세스의 메모리에 둔다(서버를 다시 켜면 사라진다 — 끝난 턴은 에이전트 대화에 남아 있다). 끝나면 작업 기록에 `guideWrite` 한 줄."""
import concurrent.futures
import json
import threading
import time
import uuid

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse

from app import agent_notes, doc_agent, doclib_client, form_review, form_review_api, guide_write, llm, works

router = APIRouter()
WORKERS = 2
_RUNS = {}            # 작업 id → 실행 {id, at, ended, state, note, materials, items[…], stop(Event — 보기에 안 실음)}
_LOCK = threading.Lock()
GUIDE_VIEW = 400      # 목록에 싣는 지침 글(자리마다 — 화면은 앞부분만 보인다)


def _sess(doc_id):
    from app import server
    return server._sess(doc_id)


# ---- 문서 라이브러리(따로 선 서버) ----------------------------------------------------------------------------------------

@router.get("/api/doclib/prompt-editor")
def doclib_prompt_editor():
    return RedirectResponse(doclib_client.url() + "/#prompts")


@router.get("/api/doclib/where")
def doclib_where():
    """문서 라이브러리 서버의 주소와 켜져 있는가 → {url, alive, why} — 상단 바 「문서 라이브러리」 아이콘(doclib_link.js)이 새 탭을 열기 전에 묻는다(목록은 안 읽는다 — 가볍게)."""
    out = {"url": doclib_client.url(), "alive": False, "why": ""}
    try:
        out["alive"] = bool(doclib_client.health().get("ok"))
    except (doclib_client.Down, LookupError) as e:
        out["why"] = str(e)
    return out


@router.get("/api/doclib")
def doclib_list():
    """문서 라이브러리 서버의 문서 · 끝난 추출 목록. 그 서버가 꺼져 있으면 {alive: false, why}."""
    out = {"url": doclib_client.url(), "alive": False, "why": "", "llm": None, "docs": []}
    try:
        h = doclib_client.health()
        out.update(alive=bool(h.get("ok")), llm=h.get("llm"))
        for d in doclib_client.docs():
            # at(문서를 올린 때) · ended(추출이 끝난 때) — 양식 작성 대시보드가 「이 문서의 몫」(기준 시각 뒤의 것)을 이것으로 센다(form_write.js formWriteLive): 전에는 떨궈 늘 0 이었다
            ex = [{k: e.get(k) for k in ("id", "focus", "span", "at", "ended", "chars", "figures", "formulas", "open")} for e in d.get("extracts") or () if e.get("state") == "done"]
            run = sum(1 for e in d.get("extracts") or () if e.get("state") in ("queued", "running"))
            out["docs"].append({**{k: d.get(k) for k in ("id", "name", "ext", "pages", "org", "topic", "bytes", "sha256", "at")}, "extracts": ex, "running": run,
                                "raw": str(d.get("ext") or "").lower() in doc_agent.MATERIAL_EXT and (d.get("bytes") or 0) <= doc_agent.MATERIAL_BYTES})   # raw = 원본 파일을 글로 읽어 자료로 줄 수 있나(추출 전인 문서 — {doc})
    except (doclib_client.Down, LookupError) as e:
        out.update(alive=False, why=str(e))
    return out


@router.post("/api/doclib/docs")
async def doclib_upload(request: Request):
    """자료(참조) 문서를 문서 라이브러리 서버에 올린다(multipart file) → 그 서버의 {doc, created} — 양식 작성의 「문서 올리기 · 첫 분석」 줄의 「참조 문서 올리기…」(새 탭 없이).
    400: 받지 않는 형식 · 그 서버가 거절 · 413: 80 MB 초과 · 502: 그 서버에 닿지 못함. 올리기만 — 추출은 그 서버의 화면에서."""
    form = await request.form()
    f = form.get("file")
    if f is None or not hasattr(f, "read"):
        raise HTTPException(400, "file 이 필요합니다")
    name = f.filename or "문서"
    if name.rsplit(".", 1)[-1].lower() not in doclib_client.UPLOAD_EXT:
        raise HTTPException(400, f"받는 형식은 {' · '.join(doclib_client.UPLOAD_EXT)} 입니다")
    data = await f.read(doclib_client.UPLOAD_MAX + 1)
    if len(data) > doclib_client.UPLOAD_MAX:
        raise HTTPException(413, f"파일은 {doclib_client.UPLOAD_MAX // 2 ** 20} MB 까지입니다")
    try:
        return await run_in_threadpool(doclib_client.upload, name, data)
    except doclib_client.Down as e:
        raise HTTPException(502, str(e)) from e
    except LookupError as e:
        raise HTTPException(400, str(e)) from e


# ---- 이 프로젝트의 참조 문서(spec_양식작성 ② §2-1 — 2026-11-26 사용자 「있는 추출할때 전부 참조할 수 있지만 사용자가 선택한 문서만 사용할 수 있게 해줘, 선택된.
#      이 프로젝트의 참고 문헌은 문서 라이브러리랑 탭이든 뭐든 구분이 되어야함」) — 문서 라이브러리는 모두 보이고(보기 · 고르기), 자료로 쓰는 것은 고른 문서의 것만.
#      저장 = 프로젝트 기록(projects.refs — 작업의 task.project). 거르는 것은 워크플로우 「양식 작성」 의 문서뿐이다(그 밖의 워크플로우 · 프로젝트 없는 문서는 전과 같다).
REFS_JOBS = ("form_write",)


def refs_of(wid):
    """→ {project, docs[고른 문서 id], only(거르나)} — only = 양식 작성의 문서이고 프로젝트가 있을 때."""
    from app import projects
    t = (works.work(wid) or {}).get("task") or {}
    name = projects.normalize_name(t.get("project") or "") if isinstance(t.get("project"), str) else ""
    try:
        docs = projects.refs(name) if name else []
    except ValueError:   # 저장 파일이 깨짐 — 거르지 않고 알린다(화면이 프로젝트 구성에서 같은 오류를 본다)
        docs = []
    return {"project": name, "docs": docs, "only": bool(name) and t.get("job") in REFS_JOBS}


def _lib_doc(m):
    lib = m.get("library") if isinstance(m.get("library"), dict) else {}
    return lib.get("doc") if isinstance(lib.get("doc"), str) else None


def outside(wid, mids):
    """고른 자료 가운데 이 프로젝트의 참조 문서가 아닌 문서에서 온 것의 이름(거르지 않는 문서면 []) — 문서 라이브러리 밖의 자료(에이전트 보기에서 준 파일 · 글)는 거르지 않는다."""
    r = refs_of(wid)
    if not r["only"]:
        return []
    store, ok = doc_agent.Store(wid), set(r["docs"])
    return [m.get("name") or m.get("id") for m in (store.material(i) for i in mids or ()) if m is not None and _lib_doc(m) and _lib_doc(m) not in ok]


def _material_views(wid):
    r = refs_of(wid)
    out = []
    for m in doc_agent.Store(wid).materials():
        d = _lib_doc(m)
        out.append({**doc_agent.material_view(m), "libDoc": d, "outside": bool(r["only"] and d and d not in r["docs"])})
    return out


def _refs_check(wid, did):
    r = refs_of(wid)
    if r["only"] and did not in r["docs"]:
        raise HTTPException(409, "이 프로젝트의 참조 문서가 아닙니다 — 「문서 라이브러리」 탭에서 「이 프로젝트에 넣기」 를 누른 뒤 가져옵니다")


@router.put("/api/docs/{doc_id}/refs")
def refs_put(doc_id: str, body: dict = Body(...)):
    """{doc, on} — 문서 라이브러리의 문서 하나를 이 문서가 든 프로젝트의 참조 문서로 넣거나(on true) 뺀다 → {refs}. 뺀다고 이미 가져온 자료가 지워지지는 않는다(그 자료는 「프로젝트 밖」 으로 보이고 쓰지 않는다).
    400 = 문서 id 꼴이 아님 · 프로젝트가 없는 문서 · 넘침 · 404 = 문서 라이브러리에 그런 문서가 없음(넣을 때) · 502 = 그 서버에 닿지 못함(넣을 때)."""
    from app import projects
    s = _sess(doc_id)
    did, on = (body or {}).get("doc"), (body or {}).get("on")
    if not doclib_client.ok_doc(did) or not isinstance(on, bool):
        raise HTTPException(400, "doc(문서 라이브러리의 문서 id)와 on(true · false)이 필요합니다")
    r = refs_of(s.id)
    if not r["project"]:
        raise HTTPException(400, "프로젝트가 없는 문서입니다 — 프로젝트를 정한 뒤 참조 문서를 고릅니다")
    if on:
        try:
            if not any(d.get("id") == did for d in doclib_client.docs()):
                raise HTTPException(404, "문서 라이브러리에 그런 문서가 없습니다")
        except doclib_client.Down as e:
            raise HTTPException(502, str(e)) from e
    try:
        projects.refs_set(r["project"], did, on)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    works.log(s.id, "projectRef", doc=did, on=on, project=r["project"])
    return {"refs": refs_of(s.id)}


@router.post("/api/docs/{doc_id}/agent/material/library")
def material_from_library(doc_id: str, body: dict = Body(...)):
    """{extract} — 문서 라이브러리 서버의 그 추출(MD)을 이 문서의 자료로. 400: 추출 id 꼴이 아님 · 자료 30개 초과 · 404: 그런 추출 없음 · 409: 아직 안 끝난 추출 · 502: 그 서버에 닿지 못함.
    {doc}(extract 없이) — 등록한 문서의 **원본 파일**을 글로 읽어 자료로(추출 전인 문서 — `_raw_rec`: 2026-11-24 사용자 「라이브러리에서 등록한 파일들을 선택해서 참조」)."""
    s = _sess(doc_id)
    body = body if isinstance(body, dict) else {}
    if body.get("extract") is None and body.get("doc") is not None:
        if doclib_client.ok_doc(body["doc"]):
            _refs_check(s.id, body["doc"])
        return _lib_keep(s, _raw_rec(body["doc"]), body["doc"])
    eid = body.get("extract")
    if not doclib_client.ok_id(eid):
        raise HTTPException(400, "extract(추출 id)가 필요합니다")
    try:
        meta = doclib_client.extract(eid)
        if meta.get("state") != "done":
            raise HTTPException(409, "아직 끝나지 않은 추출입니다")
        _refs_check(s.id, meta.get("doc"))   # 양식 작성 — 이 프로젝트의 참조 문서에서 뽑은 것만
        text = doclib_client.md(eid)
        name = next((d.get("name") for d in doclib_client.docs() if d.get("id") == meta.get("doc")), None) or "문서"
    except doclib_client.Down as e:
        raise HTTPException(502, str(e)) from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    label = f"{name.rsplit('.', 1)[0]} — {meta.get('focus') or '문서 전체'}"[:110] + ".md"
    try:
        rec = doc_agent.material_from_text(label, text)
    except doc_agent.TooBig as e:
        raise HTTPException(413, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    rec.update(kind="md", note=f"문서 라이브러리의 자료 추출({eid}) — 그림 {meta.get('figures') or 0} · 수식 {meta.get('formulas') or 0}" + (f" · 확인 필요 {meta['open']}곳" if meta.get("open") else ""), library={"extract": eid, "doc": meta.get("doc")})
    return _lib_keep(s, rec, eid)


def _lib_keep(s, rec, ref):
    """문서 라이브러리에서 읽어 온 자료 기록을 이 문서의 자료로 저장 → 자료 보기(같은 것이 있으면 그것 + reused). ref = 추출 id | 문서 id(작업 기록에)."""
    store = doc_agent.Store(s.id)
    with store.lock:
        have = store.materials()
        same = next((m for m in have if m.get("sha256") == rec["sha256"]), None)
        if same is not None:
            return {**doc_agent.material_view(same), "reused": True}
        if len(have) >= doc_agent.MATERIALS_MAX:
            raise HTTPException(400, f"자료는 {doc_agent.MATERIALS_MAX}개까지 둘 수 있습니다 — 안 쓰는 자료를 지우세요")
        store.add_material(rec)
    works.log(s.id, "agentMaterial", material=rec["id"], name=rec["name"], format=rec["kind"], chars=rec["chars"], cut=rec["cut"], library=ref)
    return doc_agent.material_view(rec)


def _raw_rec(did):
    """문서 라이브러리에 등록한 문서의 **원본 파일**(자료 추출 전) → 자료 기록(`doc_agent.material_from_file` — 글로 바꿔 읽는다: pdf · docx · hwpx).
    400: 문서 id 꼴이 아님 · 글로 못 읽는 형식(hwp) · 못 읽는 파일(글이 없는 PDF) · 404: 그런 문서 없음 · 413: 자료 한도(20 MB) 초과 · 502: 그 서버에 닿지 못함."""
    if not doclib_client.ok_doc(did):
        raise HTTPException(400, "doc(문서 id)가 필요합니다")
    try:
        meta = next((d for d in doclib_client.docs() if d.get("id") == did), None)
        if meta is None:
            raise HTTPException(404, "문서 라이브러리에 그런 문서가 없습니다")
        ext = str(meta.get("ext") or "").lower()
        if ext not in doc_agent.MATERIAL_EXT:
            raise HTTPException(400, f"{ext or '이 형식의'} 원본은 글로 읽지 못합니다 — 문서 라이브러리에서 자료 추출(MD)을 한 뒤 가져오세요")
        if (meta.get("bytes") or 0) > doc_agent.MATERIAL_BYTES:
            raise HTTPException(413, f"원본 파일이 자료 한도({doc_agent.MATERIAL_BYTES // 2 ** 20} MB)를 넘습니다 — 문서 라이브러리에서 자료 추출(MD)을 한 뒤 가져오세요")
        name, data = doclib_client.file(did, doc_agent.MATERIAL_BYTES)
    except doclib_client.Down as e:
        raise HTTPException(502, str(e)) from e
    except doclib_client.TooBig as e:
        raise HTTPException(413, str(e)) from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    try:
        rec = doc_agent.material_from_file(meta.get("name") or name or f"문서.{ext}", data)
    except doc_agent.TooBig as e:
        raise HTTPException(413, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    rec.update(note=f"문서 라이브러리의 원본({did}) — 자료 추출 전의 문서를 글로 읽음(그림 · 수식 없음)" + (" · 긴 문서라 앞부분만 — 전체는 자료 추출(MD)로" if rec["cut"] else "")
               + (f" · {rec['note']}" if rec.get("note") else ""), library={"doc": did})
    return rec


# ---- 지침 작성 -----------------------------------------------------------------------------------------------------------

_UPLOADED = {}   # 작업 id → (올린 원본의 열쇠, {문단 id: 원문})


def uploaded_texts(s):
    """그 작업에 **올린 원본**(작업 폴더의 original.hwpx — 확정해도 안 바뀐다)의 문단 원문 {문단 id: 글} | None(그 파일이 없다 — 세션의 기준 바이트는 확정하면 바뀌므로 쓰지 않는다: astra 2차 G4).
    문단 id 는 읽을 때 차례로 붙어, 올린 원본을 다시 읽으면 처음 연 때와 같다(merge_api._orig 와 같은 가정 — 그 뒤 넣은 문단은 여기 없다). 채운 자리를 가리고(form_slots 의 filled) · 올린 뒤 사람이 쓴 줄을 가리는 데 쓴다."""
    from app.headings import iter_blocks
    from app.hwpx_doc import HwpxDoc
    p = works.file_path(s.id, "original")
    if p is None:
        return None
    try:
        st = p.stat()
        key = (str(p), st.st_mtime_ns, st.st_size)
        hit = _UPLOADED.get(s.id)
        if hit is None or hit[0] != key:
            texts = {b["id"]: b.get("text") or "" for b in iter_blocks(HwpxDoc(p.read_bytes()).blocks()) if b.get("type") == "paragraph"}
            hit = _UPLOADED[s.id] = (key, texts)
        return hit[1]
    except Exception:   # noqa: BLE001 — 못 읽는 원본은 없는 것으로(채운 자리를 가리지 못할 뿐이다)
        return None


def _base_places(s):
    """그 문서의 자리 목록(guide_write.places) — 분석 결과 · 올린 원본은 세션 잠금 밖에서, 문서 블록 · 지침 색인은 잠금 안에서."""
    from app import heading_runs, place_guides_api
    graph, orig = heading_runs.graph(s), uploaded_texts(s)
    with s.lock:
        return guide_write.places(s.doc.blocks(), graph, place_guides_api.index_of(s), orig), s.rev


def _places(s):
    from app import writing_guidance_api
    places, rev = _base_places(s)
    writing_guidance_api.attach(s, places, rev)
    return places, rev


def _scope(s, place, chunks, decided):
    """자리 하나의 턴에 거는 **서버 쪽 범위**(doc_agent_api._turn 의 scope — 클라이언트가 보낸 것이 아니다: astra 2차 G3) — 그 자리에서 할 수 있는 행동 종류 · 채울 수 있는 문단 · 채울 수 있는 표.
    상자 = fill 만(사람이 고른 덩이의 문단 — 같은 이름의 덩이는 고른 것 하나만) · 같은 줄 자리(label · check) = fill 만(그 줄) · 채운 줄 = 행동 없음 · 표 = tableFill(그 표만) ·
    헤딩 = write(+ 그 헤딩 아래의 표 tableFill — 상자 자리와 상자 안의 표는 빼고)."""
    from app import heading_runs
    orig = uploaded_texts(s)
    base = {"decided": list(decided or ()), "uploaded": orig}
    if place["kind"] == "box":
        with s.lock:
            box = guide_write.boxes(s.doc.blocks(), heading_runs.graph(s), orig).get(place["id"])
        return {**base, "types": {"fill"}, "paras": set(guide_write.chunk_paras(box, chunks) if box else ()), "tables": set()}
    if place["kind"] == "table":
        return {**base, "types": {"tableFill"}, "paras": set(), "tables": {place["id"]}}
    if place.get("slot") in ("label", "check"):
        return {**base, "types": {"fill"}, "paras": {place["id"]}, "tables": set()}
    if place.get("slot") == "filled":
        return {**base, "types": set(), "paras": set(), "tables": set()}
    return {**base, "types": {"write", "tableFill"}, "paras": set(), "tables": set(place.get("tables") or ()), "after": {place["id"]}}   # 글은 그 헤딩 줄 바로 뒤에만(다른 헤딩 뒤에 쓰지 않는다 — astra 3차)


def _run_view(run):
    return None if run is None else {k: v for k, v in run.items() if k not in ("stop", "plans", "decided")}


def _place_view(p):
    return {**{k: v for k, v in p.items() if k not in ("fp", "docTheme", "docGuides", "up")},   # docTheme(문서의 테마 글 — 모든 자리에 같은 글)는 화면에 자리마다 싣지 않는다(화면은 writing-guidance 의 theme 을 본다) · docGuides(문서 전체에 닿는 지침) · up(표 구조 · 윗 절의 지침)도 — 수만
            "upN": len(p.get("up") or ()), "docN": len(p.get("docGuides") or ()),
            "guides": [g if g.get("src") == "llm" else {**g, "text": g.get("text", "")[:GUIDE_VIEW]} for g in p["guides"]]}


@router.get("/api/docs/{doc_id}/guide-write")
def guide_write_get(doc_id: str):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        return {"hwpx": False, "enabled": False, "places": [], "materials": [], "run": None, "steps": steps_of(s.id), "libFrom": lib_from(s.id), "refs": refs_of(s.id), "limits": {"places": guide_write.PLACES_MAX, "note": guide_write.NOTE_MAX}}
    ps, rev = _places(s)
    with _LOCK:
        run = _run_view(_RUNS.get(s.id))
    return {"hwpx": True, "enabled": bool(llm.status()["available"]), "rev": rev, "places": [_place_view(p) for p in ps], "materials": _material_views(s.id),
            "run": run, "steps": steps_of(s.id), "libFrom": lib_from(s.id), "refs": refs_of(s.id), "limits": {"places": guide_write.PLACES_MAX, "note": guide_write.NOTE_MAX}}


# ---- 선택 줄의 표시(2026-11-24 사용자 「전체 초기화를 했는데 1,2 번은 끝났다고 했는데 3,4번이 지나가지 않았는데 왜 5로 오냐 순서가 안맞음」 — spec_양식작성 ② §6 「선택 줄도 차례에」) ----
# 양식 작성의 선택 줄(「LLM 검증·보완」 · 「작성 지침 확인 · 적기」)은 차례대로 「지금」 이 서고, 사람이 「건너뛰기」 · 「확인함」 을 눌러야 지나간다 — 그 표시를 작업 폴더에 둔다
# (작업 내용 초기화 · 준비 초기화는 작업 폴더를 reset/<n>/ 으로 옮기므로 표시도 함께 비워진다). 문서는 안 바뀐다.
STEP_FILE = "form_write_steps.json"
STEP_MARKS = {"headsLlm": ("skip",), "guides": ("done", "skip"), "keep": ("done",), "extract": ("done",)}   # 줄 key → 받을 표시(skip = 건너뜀 · done = 확인함 · keep · extract 의 done = 「있는 것 쓰기」)
LIB_FROM = "libFrom"   # 자료 준비(06 · 07)를 이 문서의 몫으로 세는 기준 시각 — 「2단계 초기화」 가 적는다(그 밖의 초기화는 reset/<n>/ 의 시각)


def lib_from(wid) -> float:
    """06 「자료 문서 올리기」 · 07 「자료 추출」 을 이 문서의 몫으로 세는 기준 시각(epoch 초) — 작업을 만든 때 · 마지막 작업 내용 초기화 · 「2단계 초기화」 가운데 늦은 것.
    문서 라이브러리는 모든 작업이 같이 쓰는 서버라, 그 서버에 문서가 있다고 이 문서의 06 · 07 을 끝남으로 세면 초기화해도 끝남이 남는다(2026-11-24 사용자 「초기화 할때 5,6 도 아직 안했다고 나와야지」)."""
    d = works.folder(wid)
    if d is None:
        return 0.0
    w = works.work(wid) or {}
    at = [float(w.get("created") or 0)]
    box = d / "reset"
    if box.is_dir():
        at += [p.stat().st_mtime for p in box.iterdir() if p.name.isdigit()]
    try:
        got = json.loads((d / STEP_FILE).read_text(encoding="utf-8")) if (d / STEP_FILE).exists() else {}
        if isinstance(got, dict) and isinstance(got.get(LIB_FROM), (int, float)):
            at.append(float(got[LIB_FROM]))
    except (OSError, ValueError):
        pass
    return max(at)


def steps_of(wid) -> dict:
    """{줄 key: "skip" | "done"} — 없거나 못 읽으면 빈 사전."""
    d = works.folder(wid)
    p = d / STEP_FILE if d is not None else None
    try:
        got = json.loads(p.read_text(encoding="utf-8")) if p is not None and p.exists() else {}
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in got.items() if isinstance(got, dict) and k in STEP_MARKS and v in STEP_MARKS[k]} if isinstance(got, dict) else {}


def _steps_write(d, marks, lib=None):
    """표시를 쓴다 — 파일의 기준 시각(libFrom)은 그대로 두거나(lib=None) 새 값으로."""
    p = d / STEP_FILE
    try:
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        old = {}
    keep = lib if lib is not None else (old.get(LIB_FROM) if isinstance(old, dict) else None)
    p.write_text(json.dumps({**marks, **({LIB_FROM: keep} if keep is not None else {})}, ensure_ascii=False), encoding="utf-8")


@router.put("/api/docs/{doc_id}/form-write/step")
def form_write_step(doc_id: str, body: dict = Body(...)):
    """선택 줄의 표시 {key, mark: "skip" | "done" | null(지움)} → {steps}. 400 = 모르는 줄 · 표시 · 작업 저장이 꺼짐."""
    key, mark = body.get("key"), body.get("mark")
    if key not in STEP_MARKS or (mark is not None and mark not in STEP_MARKS[key]):
        raise HTTPException(400, f"key 는 {' · '.join(STEP_MARKS)} · mark 는 그 줄이 받는 표시 또는 null 입니다")
    s = _sess(doc_id)
    d = works.folder(s.id)
    if d is None or not d.is_dir():
        raise HTTPException(400, "작업 저장이 꺼진 문서는 표시를 남길 수 없습니다")
    with _LOCK:
        cur = steps_of(s.id)
        if mark is None:
            cur.pop(key, None)
        else:
            cur[key] = mark
        _steps_write(d, cur)
    works.log(s.id, "formWriteStep", key=key, mark=mark)
    return {"steps": cur}


def _one(doc_id, place, head_text, mids, note, run):
    """자리 하나 = 문서 에이전트의 한 턴 → 그 자리의 결과 줄을 고친다. 요청 글에 양식 검토의 글(사람이 정해 준 것 + 이 자리의 작성 방향 — run["plans"])을 싣는다."""
    from app import doc_agent_api
    item = next(i for i in run["items"] if i["id"] == place["id"])
    if run["stop"].is_set():
        item.update(state="skipped", error="멈춤")
        return
    item["state"] = "running"
    try:
        if place["kind"] == "head" and place.get("boxed") and not place.get("slot"):   # 그 헤딩 아래는 상자에 쓴다 — 헤딩 아래에 같은 내용을 또 쓰지 않게 LLM 을 부르지 않는다(astra 3차: 실물에서 상자 내용이 헤딩 아래 글로도 나왔다)
            item.update(state="none", reply="이 헤딩 아래의 쓸 자리는 상자 안에 있습니다 — 그 상자 자리를 고릅니다.", why="boxed")
            return
        if place.get("slot") == "filled":   # 이미 채운 줄 — 다시 쓰지 않는다(LLM 을 부르지 않는다)
            item.update(state="none", reply="이미 값이 있는 줄입니다 — 다시 쓰지 않습니다(고치려면 문서에서 직접 고칩니다).", why="filled")
            return
        scope = _scope(_sess(doc_id), place, (run.get("chunks") or {}).get(place["id"]), run.get("decided"))
        if place["kind"] == "box" and not scope["paras"]:
            item.update(state="none", reply="이 상자에서 쓸 자리를 고르지 않았습니다 — 「지침 작성」 열에서 쓸 자리를 고릅니다.", why="noslot")
            return
        got = doc_agent_api._turn(doc_id, {"text": guide_write.request(place, note, head_text, run["plans"].get(place["id"], "")), "materials": list(mids), "selection": guide_write.selection(place)}, scope=scope)
    except HTTPException as e:
        item.update(state="failed", error=str(e.detail)[:300])
        return
    except Exception as e:   # noqa: BLE001 — 한 자리의 실패가 다른 자리를 멈추지 않게
        item.update(state="failed", error=f"{type(e).__name__}: {e}"[:300])
        return
    if isinstance(got, JSONResponse):   # 502 — 조정 호출이 답하지 못함(본문에 오류가 적힌 턴)
        try:
            body = json.loads(got.body.decode("utf-8"))
        except Exception:   # noqa: BLE001
            body = {}
        item.update(state="failed", error=str(body.get("detail") or "LLM 이 답하지 못했습니다")[:300], turn=((body.get("turn") or {}).get("id")))
        return
    turn = got.get("turn") or {}
    props = turn.get("proposals") or []
    dropped = turn.get("dropped") or []   # 초안이 0개인 까닭을 가른다(astra 1차 5): 검사에서 버림 ↔ 에이전트가 행동 없이 답함(자료에 없음 등 — 답 글에 있다)
    item.update(state="done" if props else "none", turn=turn.get("id"), proposals=len(props), reply=" ".join(str(turn.get("reply") or "").split())[:300],
                picked=sum(1 for p in props if p.get("preselect")), stale=sum(1 for p in props if p.get("state") == "stale"),
                dropped=len(dropped), why=None if props else "dropped" if dropped else "noaction", note=" ".join(str(dropped[0].get("why") or "").split())[:200] if dropped and not props else "")


def _go(doc_id, wid, todo, heads, mids, note, run, keep):
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(lambda p: keep(doc_id, p, heads.get(p.get("head") or ""), mids, note, run), todo))
    finally:
        items = run["items"]
        run.update(state="stopped" if run["stop"].is_set() else "done", ended=round(time.time(), 3))
        works.log(wid, "guideWrite", run=run["id"], places=len(items), proposals=sum(i.get("proposals") or 0 for i in items), failed=sum(1 for i in items if i["state"] == "failed"),
                  none=sum(1 for i in items if i["state"] == "none"), materials=len(mids), stopped=run["stop"].is_set())


@router.post("/api/docs/{doc_id}/guide-write/run")
def guide_write_run(doc_id: str, body: dict = Body(...)):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "지침 작성은 hwpx 문서만 됩니다")
    body = body if isinstance(body, dict) else {}
    note = body.get("note") or ""
    if not isinstance(note, str) or len(note) > guide_write.NOTE_MAX:
        raise HTTPException(400, f"이번 작성의 지침(note)은 {guide_write.NOTE_MAX:,}자까지")
    mids = body.get("materials") or []
    store = doc_agent.Store(s.id)
    if not isinstance(mids, list) or not all(isinstance(m, str) for m in mids) or len(set(mids)) != len(mids) or any(store.material(m) is None for m in mids):
        raise HTTPException(400, "materials 는 이 문서의 자료 id 목록(겹침 없이)")
    if not mids:
        raise HTTPException(400, "자료를 하나 이상 고르세요 — 자료에 있는 내용만 넣습니다")
    bad = outside(s.id, mids)
    if bad:
        raise HTTPException(409, f"이 프로젝트의 참조 문서가 아닌 문서의 자료입니다({' · '.join(bad[:3])}) — 빼고 고르거나 그 문서를 「이 프로젝트에 넣기」 합니다")
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    ok, why, st = form_review_api.gate(s.id)   # 쓰기 전에 양식 검토 · 정할 것에 답하기(2026-11-24 사용자 — spec_양식작성 ② §5-1)
    if not ok:
        raise HTTPException(409, why)
    ps, _ = _places(s)
    todo, lost = guide_write.pick(ps, body.get("places"))
    if not todo:
        raise HTTPException(400, "작성할 자리를 하나 이상 고르세요" if not lost else "고른 자리가 지금 문서에 없습니다 — 목록을 다시 읽어 주세요")
    why = form_review_api.fresh(st, todo, mids)   # 계획을 세운 자료 · 고른 자리가 검토한 때와 같은가(astra 2차 G12 — 다른 기관의 자료 · 바뀐 자리로 옛 계획을 쓰지 않는다)
    if why:
        raise HTTPException(409, why)
    chunks = body.get("chunks") or {}
    if not isinstance(chunks, dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v) for k, v in chunks.items()):
        raise HTTPException(400, "chunks 는 {상자 id: [쓸 자리(덩이)의 key…]}")
    heads = {p["id"]: p["text"] for p in ps if p["kind"] == "head"}
    run = {"id": uuid.uuid4().hex[:10], "at": round(time.time(), 3), "ended": None, "state": "running", "note": note, "materials": list(mids), "lost": lost, "stop": threading.Event(),
           "plans": form_review_api.plans(s.id, todo, [p["id"] for p in ps]), "reviewed": True, "chunks": {k: list(v) for k, v in chunks.items()},
           "decided": [d["a"] for d in st["decided"] if d.get("a") and d["a"] != form_review.SKIP],
           "items": [{"id": p["id"], "kind": p["kind"], "text": p["text"], "state": "queued", "turn": None, "proposals": 0, "reply": "", "error": None} for p in todo]}
    with _LOCK:
        cur = _RUNS.get(s.id)
        if cur is not None and cur["state"] == "running":
            raise HTTPException(409, "이 문서의 지침 작성이 이미 돌고 있습니다")
        _RUNS[s.id] = run
    keep = agent_notes.carry(_one)   # 일꾼 스레드에도 지금 워크플로우(덧붙이는 글의 전용 범위)를 넘긴다
    threading.Thread(target=_go, args=(doc_id, s.id, todo, heads, mids, note, run, keep), name=f"guide-write-{run['id']}", daemon=True).start()
    return {"run": _run_view(run)}


@router.post("/api/docs/{doc_id}/form-write/reset")
def form_write_reset(doc_id: str, body: dict = Body(...)):
    """양식 작성의 단계 초기화(spec_양식작성 ② §6-1 — 2026-11-24 사용자 "준비/자료,작성 단계를 따로 두고 단계별로 실행할 수 있거나.. 모두 작업 내용 초기화") {stage} → {stage, …}.
    - material = 이 문서의 자료를 모두 지운다(문서 라이브러리의 문서 · 추출은 그대로 — 그 서버의 것) → {materials: 지운 수}.
    - write = 받은 초안(에이전트 대화 · 제안 카드) · 지침 작성의 실행 · 작성 계획을 비우고 **문서를 올린 원본으로** 되돌린다(반영한 초안과 그 밖에 고친 문단 — 확정이 있었으면 「올린 원본으로 복원」 확정 하나를 더한다)
      → {reverted, turns, plan}. 남김: 분석 · 작성 지침 · 양식 검토(찾을 테마) · 사람이 정한 답 · 자료.
    준비 단계의 초기화는 `POST /api/works/{id}/reset?keep=materials`(작업 내용 초기화에서 자료만 남김). 400 = 모르는 단계 · 409 = 지침 작성 · 양식 검토가 도는 중."""
    stage = body.get("stage")
    if stage not in ("material", "write"):
        raise HTTPException(400, "stage 는 material · write 가운데 하나입니다")
    s = _sess(doc_id)
    with _LOCK:
        if (_RUNS.get(s.id) or {}).get("state") == "running":
            raise HTTPException(409, "지침 작성이 도는 중입니다 — 멈추거나 끝난 뒤에 초기화하세요")
    with form_review_api._LOCK:
        if (form_review_api._RUNS.get(s.id) or {}).get("state") == "running":
            raise HTTPException(409, "양식 검토가 도는 중입니다 — 끝난 뒤에 초기화하세요")
    store = doc_agent.Store(s.id)
    if stage == "material":
        mids = [m["id"] for m in store.materials()]
        for mid in mids:
            store.drop_material(mid)
        d = works.folder(s.id)
        if d is not None and d.is_dir():   # 06 · 07 도 「아직 안 함」 으로 — 기준 시각을 지금으로 · 「있는 것 쓰기」 표시를 지움(문서 라이브러리의 문서 · 추출은 그대로)
            with _LOCK:
                cur = {k: v for k, v in steps_of(s.id).items() if k not in ("keep", "extract")}
                _steps_write(d, cur, lib=round(time.time(), 3))
        works.log(s.id, "formWriteReset", stage=stage, materials=len(mids))
        return {"stage": stage, "materials": len(mids)}
    from app import server
    with s.lock:
        back = server._dirty(s)
        if not back and s.base_n:   # 기준이 확정본 — 그 확정본이 올린 원본 그대로면(앞선 초기화의 「올린 원본으로 복원」) 되돌릴 것이 없다
            p = works.file_path(s.id, "original")
            back = p is None or p.read_bytes() != s.original
    if back:   # 문서를 올린 원본으로(기준이 올린 원본이면 고친 것만 버림 · 확정이 있었으면 새 확정 「올린 원본으로 복원」) — 못 되돌리면 아무것도 비우지 않는다
        server.commit_restore(doc_id, 0, {"discard": True})
    turns = len(store.turns())
    store.clear(materials=False)
    plan = form_review_api.unplan(s.id)
    try:   # 「지침 검토 · 수정」 의 검토 결과(guidefix.json — 문서를 올린 원본으로 되돌렸으니 그 계획은 낡았다: spec_양식작성 ② §5-9)
        from app import guide_fix_api
        guide_fix_api.clear(s.id)
    except Exception:   # noqa: BLE001 — 못 비워도 초기화는 끝낸다(다음 검토가 덮는다)
        pass
    with _LOCK:
        _RUNS.pop(s.id, None)
    works.log(s.id, "formWriteReset", stage=stage, reverted=back, turns=turns, plan=plan)
    return {"stage": stage, "reverted": back, "turns": turns, "plan": plan}


@router.get("/api/docs/{doc_id}/guide-write/run")
def guide_write_state(doc_id: str):
    s = _sess(doc_id)
    with _LOCK:
        return {"run": _run_view(_RUNS.get(s.id))}


@router.post("/api/docs/{doc_id}/guide-write/stop")
def guide_write_stop(doc_id: str):
    s = _sess(doc_id)
    with _LOCK:
        run = _RUNS.get(s.id)
        if run is None or run["state"] != "running":
            return {"ok": True, "stopping": False}
        run["stop"].set()
    return {"ok": True, "stopping": True}
