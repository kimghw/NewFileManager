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


def _places(s):
    """그 문서의 자리 목록(guide_write.places) — 분석 결과 · 올린 원본은 세션 잠금 밖에서, 문서 블록 · 지침 색인은 잠금 안에서."""
    from app import heading_runs, place_guides_api
    graph, orig = heading_runs.graph(s), uploaded_texts(s)
    with s.lock:
        return guide_write.places(s.doc.blocks(), graph, place_guides_api.index_of(s), orig), s.rev


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
    return {**{k: v for k, v in p.items() if k != "fp"}, "guides": [{**g, "text": g.get("text", "")[:GUIDE_VIEW]} for g in p["guides"]]}   # fp = 자리의 지문 재료(상자의 줄 전부 — 화면에는 안 보낸다)


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
