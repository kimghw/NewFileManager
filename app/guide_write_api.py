"""지침 작성 · 문서 라이브러리에서 자료 가져오기 끝점(spec_양식작성 ② §4 · §5) — 요청 글 · 자리 고르기는 `app/guide_write.py`(순수), 문서 라이브러리 서버(doclib/ · 따로 선 서버)는 `app/doclib_client.py` 로만 읽는다.
hwpx 문서만 · 어느 워크플로우의 문서에서나(공통 모듈 — 워크플로우 「양식 작성」 이 쓴다).

- `GET /api/doclib` → {url, alive, why, llm, docs[{id, name, ext, pages, org, topic, bytes, sha256, raw(원본을 글로 읽어 자료로 줄 수 있나), running, extracts[끝난 것 — {id, focus, span, at, chars, figures, formulas, open}]}]} — 문서 라이브러리 서버의 문서 · 추출 목록(그 서버가 꺼져 있으면 alive false + 까닭).
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

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from app import agent_notes, doc_agent, doclib_client, form_review_api, guide_write, llm, works

router = APIRouter()
WORKERS = 2
_RUNS = {}            # 작업 id → 실행 {id, at, ended, state, note, materials, items[…], stop(Event — 보기에 안 실음)}
_LOCK = threading.Lock()
GUIDE_VIEW = 400      # 목록에 싣는 지침 글(자리마다 — 화면은 앞부분만 보인다)


def _sess(doc_id):
    from app import server
    return server._sess(doc_id)


# ---- 문서 라이브러리(따로 선 서버) ----------------------------------------------------------------------------------------

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
            ex = [{k: e.get(k) for k in ("id", "focus", "span", "at", "chars", "figures", "formulas", "open")} for e in d.get("extracts") or () if e.get("state") == "done"]
            run = sum(1 for e in d.get("extracts") or () if e.get("state") in ("queued", "running"))
            out["docs"].append({**{k: d.get(k) for k in ("id", "name", "ext", "pages", "org", "topic", "bytes", "sha256")}, "extracts": ex, "running": run,
                                "raw": str(d.get("ext") or "").lower() in doc_agent.MATERIAL_EXT and (d.get("bytes") or 0) <= doc_agent.MATERIAL_BYTES})   # raw = 원본 파일을 글로 읽어 자료로 줄 수 있나(추출 전인 문서 — {doc})
    except (doclib_client.Down, LookupError) as e:
        out.update(alive=False, why=str(e))
    return out


@router.post("/api/docs/{doc_id}/agent/material/library")
def material_from_library(doc_id: str, body: dict = Body(...)):
    """{extract} — 문서 라이브러리 서버의 그 추출(MD)을 이 문서의 자료로. 400: 추출 id 꼴이 아님 · 자료 30개 초과 · 404: 그런 추출 없음 · 409: 아직 안 끝난 추출 · 502: 그 서버에 닿지 못함.
    {doc}(extract 없이) — 등록한 문서의 **원본 파일**을 글로 읽어 자료로(추출 전인 문서 — `_raw_rec`: 2026-11-24 사용자 「라이브러리에서 등록한 파일들을 선택해서 참조」)."""
    s = _sess(doc_id)
    body = body if isinstance(body, dict) else {}
    if body.get("extract") is None and body.get("doc") is not None:
        return _lib_keep(s, _raw_rec(body["doc"]), body["doc"])
    eid = body.get("extract")
    if not doclib_client.ok_id(eid):
        raise HTTPException(400, "extract(추출 id)가 필요합니다")
    try:
        meta = doclib_client.extract(eid)
        if meta.get("state") != "done":
            raise HTTPException(409, "아직 끝나지 않은 추출입니다")
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

def _places(s):
    """그 문서의 자리 목록(guide_write.places) — 분석 결과는 세션 잠금 밖에서, 문서 블록 · 지침 색인은 잠금 안에서."""
    from app import heading_runs, place_guides_api
    graph = heading_runs.graph(s)
    with s.lock:
        return guide_write.places(s.doc.blocks(), graph, place_guides_api.index_of(s)), s.rev


def _run_view(run):
    return None if run is None else {k: v for k, v in run.items() if k not in ("stop", "plans")}


def _place_view(p):
    return {**p, "guides": [{**g, "text": g.get("text", "")[:GUIDE_VIEW]} for g in p["guides"]]}


@router.get("/api/docs/{doc_id}/guide-write")
def guide_write_get(doc_id: str):
    s = _sess(doc_id)
    if s.fmt != "hwpx":
        return {"hwpx": False, "enabled": False, "places": [], "materials": [], "run": None, "limits": {"places": guide_write.PLACES_MAX, "note": guide_write.NOTE_MAX}}
    ps, rev = _places(s)
    with _LOCK:
        run = _run_view(_RUNS.get(s.id))
    return {"hwpx": True, "enabled": bool(llm.status()["available"]), "rev": rev, "places": [_place_view(p) for p in ps], "materials": [doc_agent.material_view(m) for m in doc_agent.Store(s.id).materials()],
            "run": run, "limits": {"places": guide_write.PLACES_MAX, "note": guide_write.NOTE_MAX}}


def _one(doc_id, place, head_text, mids, note, run):
    """자리 하나 = 문서 에이전트의 한 턴 → 그 자리의 결과 줄을 고친다. 요청 글에 양식 검토의 글(사람이 정해 준 것 + 이 자리의 작성 방향 — run["plans"])을 싣는다."""
    from app import doc_agent_api
    item = next(i for i in run["items"] if i["id"] == place["id"])
    if run["stop"].is_set():
        item.update(state="skipped", error="멈춤")
        return
    item["state"] = "running"
    try:
        got = doc_agent_api.agent_turn(doc_id, {"text": guide_write.request(place, note, head_text, run["plans"].get(place["id"], "")), "materials": list(mids), "selection": guide_write.selection(place)})
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
    item.update(state="done" if props else "none", turn=turn.get("id"), proposals=len(props), reply=" ".join(str(turn.get("reply") or "").split())[:300],
                picked=sum(1 for p in props if p.get("preselect")), stale=sum(1 for p in props if p.get("state") == "stale"))


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
    if not llm.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude Agent SDK·CLI·API 키 없음 또는 꺼짐)")
    ok, why, _ = form_review_api.gate(s.id)   # 쓰기 전에 양식 검토 · 정할 것에 답하기(2026-11-24 사용자 — spec_양식작성 ② §5-1)
    if not ok:
        raise HTTPException(409, why)
    ps, _ = _places(s)
    todo, lost = guide_write.pick(ps, body.get("places"))
    if not todo:
        raise HTTPException(400, "작성할 자리를 하나 이상 고르세요" if not lost else "고른 자리가 지금 문서에 없습니다 — 목록을 다시 읽어 주세요")
    heads = {p["id"]: p["text"] for p in ps if p["kind"] == "head"}
    run = {"id": uuid.uuid4().hex[:10], "at": round(time.time(), 3), "ended": None, "state": "running", "note": note, "materials": list(mids), "lost": lost, "stop": threading.Event(),
           "plans": form_review_api.plans(s.id, todo), "reviewed": True,
           "items": [{"id": p["id"], "kind": p["kind"], "text": p["text"], "state": "queued", "turn": None, "proposals": 0, "reply": "", "error": None} for p in todo]}
    with _LOCK:
        cur = _RUNS.get(s.id)
        if cur is not None and cur["state"] == "running":
            raise HTTPException(409, "이 문서의 지침 작성이 이미 돌고 있습니다")
        _RUNS[s.id] = run
    keep = agent_notes.carry(_one)   # 일꾼 스레드에도 지금 워크플로우(덧붙이는 글의 전용 범위)를 넘긴다
    threading.Thread(target=_go, args=(doc_id, s.id, todo, heads, mids, note, run, keep), name=f"guide-write-{run['id']}", daemon=True).start()
    return {"run": _run_view(run)}


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
