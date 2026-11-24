"""문서 라이브러리 서버(spec_양식작성 ② §2) — `python -m uvicorn doclib.server:app --host 127.0.0.1 --port 8121`(띄우개 tools/start_doclib.ps1).

끝점(모두 이 파일 — 8114 의 끝점과 따로):
- `GET /api/health` → {ok, name, llm{available, cli, model, slots}, pdf{hwpx, docx}(한글 · Word 로 PDF 를 찍을 수 있나), size, root}
- `GET /api/docs` → {docs[{id, name, ext, bytes, pages, at, org, topic, note, extracts[요약]}]} · `POST /api/docs`(multipart file) → {doc, created}
- `PATCH /api/docs/{did}` {org?, topic?, note?} · `DELETE /api/docs/{did}`(도는 추출이 있으면 409) · `GET /api/docs/{did}/file`(올린 파일) · `GET /api/docs/{did}/pdf`(읽을 PDF — 없으면 그때 찍는다)
- `POST /api/docs/{did}/extracts` {focus | focuses[…], first?, last?} → 추출을 배경에서 시작 {extract, extracts[…]} — focuses 가 둘 이상이면 **범위마다 추출 하나(MD 하나)** 를 문서 한 번 읽기로 함께 뽑는다(같은 group) · `GET /api/extracts/{eid}` → {extract, running}
- `POST /api/extracts/{eid}/stop`(함께 뽑는 범위 모두 멈춤 → {stopping, mates}) · `DELETE /api/extracts/{eid}`(함께 도는 범위가 있으면 그 범위만 뺌) · `GET /api/extracts/{eid}/md`(?abs=1 이면 그림 링크를 이 서버의 주소로) · `…/images/{name}`
- `GET /api/extracts/{eid}/zip`(<문서>_<범위>.md + 수식 목록 + images/ · ?group=1 이면 함께 뽑은 범위의 MD 를 모두 한 zip 에)
- `GET /api/prompts` · `GET | PUT /api/prompts/{name}` {text} — 스킬 글(빈 글 = 기본본으로)
- `GET /` — 관리 화면(doclib/static/).
127.0.0.1 만 듣는다. 다른 출처의 페이지가 보내는 바꾸는 요청(Origin 이 이 서버가 아님)은 403 — 8114 서버가 보내는 요청(Origin 없음)과 이 서버의 화면만 바꾼다."""
import io
import os
import zipfile
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from doclib import agent, extract, pdfkit, store

STATIC = Path(__file__).with_name("static")
app = FastAPI(title="문서 라이브러리", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup():
    store.root().mkdir(parents=True, exist_ok=True)
    store.cut_running()


@app.middleware("http")
async def _own_origin(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != (request.headers.get("host") or ""):
            return JSONResponse({"detail": "다른 출처의 요청은 받지 않습니다"}, status_code=403)
    resp = await call_next(request)
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _pdf_ok():
    try:
        from app import pdf_render
        return {"hwpx": pdf_render.available("hwpx"), "docx": pdf_render.available("docx")}
    except Exception:   # noqa: BLE001
        return {"hwpx": False, "docx": False}


@app.get("/api/health")
def health():
    return {"ok": True, "name": "문서 라이브러리", "llm": agent.status(), "pdf": _pdf_ok(), "size": pdfkit.SIZE, "scopes": extract.FOCUSES_MAX, "root": str(store.root())}   # scopes = 한 번에 함께 뽑는 범위의 한도(화면이 이 값이 있을 때만 범위 여럿을 보낸다)


@app.get("/api/docs")
def docs_list():
    store.cut_orphans(extract.running)   # 스레드 없이 「추출 중」 으로 남은 것 → 「끊김」
    return {"docs": store.docs()}


@app.post("/api/docs")
async def docs_add(request: Request):
    form = await request.form()
    f = form.get("file")
    if f is None or not hasattr(f, "read"):
        raise HTTPException(400, "file 이 필요합니다")
    data = await f.read()
    try:
        meta, created = await run_in_threadpool(store.add_doc, f.filename or "문서", data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if created and meta["ext"] == "pdf":
        try:
            pdf = pdfkit.open_pdf(data)
            meta = store.patch_doc(meta["id"], {"pages": len(pdf)})
            pdf.close()
        except ValueError as e:
            store.drop_doc(meta["id"])
            raise HTTPException(400, str(e)) from e
    return {"doc": {**meta, "extracts": [store.brief(e) for e in store.extracts_of(meta["id"])]}, "created": created}


def _doc(did):
    m = store.doc(did)
    if m is None:
        raise HTTPException(404, "그런 문서가 없습니다")
    return m


def _ext(eid):
    m = store.extract(eid)
    if m is None:
        raise HTTPException(404, "그런 추출이 없습니다")
    return m


@app.patch("/api/docs/{did}")
def docs_patch(did: str, body: dict = Body(...)):
    _doc(did)
    return {"doc": store.patch_doc(did, {k: v for k, v in (body or {}).items() if k in store.FIELDS})}


@app.delete("/api/docs/{did}")
def docs_delete(did: str):
    _doc(did)
    if any(extract.running(e["id"]) for e in store.extracts_of(did)):
        raise HTTPException(409, "이 문서의 추출이 돌고 있습니다 — 멈춘 뒤 지우세요")
    store.drop_doc(did)
    return {"ok": True}


def _download(path, name):
    return FileResponse(path, filename=name, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@app.get("/api/docs/{did}/file")
def docs_file(did: str):
    m = _doc(did)
    src, _ = store.source(did)
    return _download(src, m["name"])


@app.get("/api/docs/{did}/pdf")
def docs_pdf(did: str):
    m = _doc(did)
    try:
        pdf = extract.ensure_pdf(did)
    except RuntimeError as e:
        raise HTTPException(422, str(e)) from e
    return FileResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(m['name'].rsplit('.', 1)[0] + '.pdf')}"})


@app.post("/api/docs/{did}/extracts")
def extracts_start(did: str, body: dict = Body(default={})):
    _doc(did)
    if not agent.status()["available"]:
        raise HTTPException(503, "LLM 을 쓸 수 없습니다(Claude CLI 가 없거나 꺼짐)")
    span = None
    first, last = (body or {}).get("first"), (body or {}).get("last")
    if first is not None or last is not None:
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in (first, last)) or last < first:
            raise HTTPException(400, "쪽 범위는 first ≤ last 인 정수 둘")
        span = (first, last)
    many = (body or {}).get("focuses")
    if many is not None and not isinstance(many, list):
        raise HTTPException(400, "focuses 는 글의 목록입니다")
    try:
        meta = extract.start(did, many if many else (body or {}).get("focus") or "", span)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"extract": meta, "extracts": extract._members(meta)}


@app.get("/api/extracts/{eid}")
def extracts_get(eid: str):
    return {"extract": _ext(eid), "running": extract.running(eid)}


@app.post("/api/extracts/{eid}/stop")
def extracts_stop(eid: str):
    _ext(eid)
    mates = extract.mates_n(eid)
    return {"ok": True, "stopping": extract.halt(eid), "mates": mates}


@app.delete("/api/extracts/{eid}")
def extracts_delete(eid: str):
    _ext(eid)
    if extract.leave(eid):   # 함께 뽑는 다른 범위가 돌고 있다 — 이 범위만 빼고 바로 지운다(나머지는 계속)
        store.drop_extract(eid)
        return {"ok": True, "left": True}
    if extract.halt(eid, drop=True):  # 도는 추출 — 멈추고, 스레드가 끝나면 지운다(도는 CLI 가 끊길 때까지 몇 초)
        return {"ok": True, "pending": True}
    store.drop_extract(eid)
    return {"ok": True}


def _md(eid):
    _ext(eid)
    p = store.ext_dir(eid) / "doc.md"
    if not p.is_file():
        raise HTTPException(404, "아직 MD 가 없습니다(추출이 끝나지 않았거나 실패)")
    return p


@app.get("/api/extracts/{eid}/md")
def extracts_md(eid: str, request: Request, abs: int = 0):   # noqa: A002 — 쿼리 이름
    text = _md(eid).read_text(encoding="utf-8")
    if abs:
        text = text.replace("](images/", f"]({str(request.base_url).rstrip('/')}/api/extracts/{eid}/images/")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@app.get("/api/extracts/{eid}/images/{name}")
def extracts_image(eid: str, name: str):
    _ext(eid)
    if "/" in name or "\\" in name or not name.endswith(".png"):
        raise HTTPException(404, "그런 그림이 없습니다")
    p = store.ext_dir(eid) / "images" / name
    if not p.is_file():
        raise HTTPException(404, "그런 그림이 없습니다")
    return FileResponse(p, media_type="image/png")


def _md_name(base, focus, taken):
    """MD 파일 이름(확장자 없이) — 「<문서>_<범위>」(범위가 없으면 「<문서>」). 같은 이름이 이미 있으면 (2) (3) … 을 붙인다."""
    tail = store.clean_name(focus)[:60].strip(" .") if focus else ""
    name = f"{base}_{tail}" if tail else base
    n, out = 1, name
    while out in taken:
        n += 1
        out = f"{name} ({n})"
    taken.add(out)
    return out


@app.get("/api/extracts/{eid}/zip")
def extracts_zip(eid: str, group: int = 0):
    m = _ext(eid)
    md = _md(eid)
    doc = store.doc(m["doc"]) or {}
    base = store.clean_name((doc.get("name") or "문서").rsplit(".", 1)[0])
    # group = 함께 뽑은 범위들의 MD 를 한 zip 에(끝난 것만 — 그림은 같은 이름이 같은 그림이라 한 번만)
    ms = [x for x in extract._members(m) if x.get("state") == "done" and (store.ext_dir(x["id"]) / "doc.md").is_file()] if group and m.get("group") else [m]
    buf, taken, seen = io.BytesIO(), set(), set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for x in ms or [m]:
            folder, name = store.ext_dir(x["id"]), _md_name(base, x.get("focus") or "", taken)
            z.write(folder / "doc.md", f"{name}.md")
            if (folder / "equations.md").is_file():   # 수식 목록(캡처와 LaTeX 를 나란히)
                z.write(folder / "equations.md", f"{name}.equations.md")
            for img in sorted((folder / "images").glob("*.png")):
                if img.name not in seen:
                    seen.add(img.name)
                    z.write(img, f"images/{img.name}")
    out = (base if len(ms) > 1 else next(iter(taken))) + "_추출.zip"
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(out)}"})


@app.get("/api/prompts")
def prompts_list():
    return {"prompts": [store.prompt(n) for n, _ in store.PROMPTS], "contracts": {"extract": extract.CONTRACT + "\n\n──── 범위가 여럿일 때(함께 뽑기 — 범위마다 MD 하나) ────\n\n" + extract.CONTRACT_MULTI, "verify": extract.VERIFY_CONTRACT, "formula": extract.FORMULA_CONTRACT}}


@app.put("/api/prompts/{name}")
def prompts_put(name: str, body: dict = Body(...)):
    try:
        got = store.put_prompt(name, (body or {}).get("text"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if got is None:
        raise HTTPException(404, "그런 스킬 글이 없습니다")
    return {"prompt": got}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
PORT = int(os.environ.get("NFM_DOCLIB_PORT") or 8121)
