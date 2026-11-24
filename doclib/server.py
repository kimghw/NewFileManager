"""문서 라이브러리 서버(spec_양식작성 ② §2) — `python -m uvicorn doclib.server:app --host 127.0.0.1 --port 8121`(띄우개 tools/start_doclib.ps1).

끝점(모두 이 파일 — 8114 의 끝점과 따로):
- `GET /api/health` → {ok, name, llm{available, cli, model, slots}, pdf{hwpx, docx}(한글 · Word 로 PDF 를 찍을 수 있나), size, root}
- `GET /api/docs` → {docs[{id, name, ext, bytes, pages, at, org, topic, note, extracts[요약]}]} · `POST /api/docs`(multipart file) → {doc, created}
- `PATCH /api/docs/{did}` {org?, topic?, note?} · `DELETE /api/docs/{did}`(도는 추출이 있으면 409) · `GET /api/docs/{did}/file`(올린 파일) · `GET /api/docs/{did}/pdf`(읽을 PDF — 없으면 그때 찍는다)
- `POST /api/docs/{did}/extracts` {focus, first?, last?} → 추출을 배경에서 시작 {extract} · `GET /api/extracts/{eid}` → {extract, running}
- `POST /api/extracts/{eid}/stop` · `DELETE /api/extracts/{eid}` · `GET /api/extracts/{eid}/md`(?abs=1 이면 그림 링크를 이 서버의 주소로) · `…/images/{name}` · `…/zip`(doc.md + 수식 목록 equations.md + images/)
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
    return {"ok": True, "name": "문서 라이브러리", "llm": agent.status(), "pdf": _pdf_ok(), "size": pdfkit.SIZE, "root": str(store.root())}


@app.get("/api/docs")
def docs_list():
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
    try:
        meta = extract.start(did, (body or {}).get("focus") or "", span)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"extract": meta}


@app.get("/api/extracts/{eid}")
def extracts_get(eid: str):
    return {"extract": _ext(eid), "running": extract.running(eid)}


@app.post("/api/extracts/{eid}/stop")
def extracts_stop(eid: str):
    _ext(eid)
    return {"ok": True, "stopping": extract.halt(eid)}


@app.delete("/api/extracts/{eid}")
def extracts_delete(eid: str):
    _ext(eid)
    if extract.running(eid):
        raise HTTPException(409, "도는 추출입니다 — 멈춘 뒤 지우세요")
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


@app.get("/api/extracts/{eid}/zip")
def extracts_zip(eid: str):
    m = _ext(eid)
    md = _md(eid)
    doc = store.doc(m["doc"]) or {}
    base = store.clean_name((doc.get("name") or "문서").rsplit(".", 1)[0])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(md, f"{base}.md")
        if (md.parent / "equations.md").is_file():   # 수식 목록(캡처와 LaTeX 를 나란히)
            z.write(md.parent / "equations.md", f"{base}.equations.md")
        for img in sorted((md.parent / "images").glob("*.png")):
            z.write(img, f"images/{img.name}")
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(base + '_추출.zip')}"})


@app.get("/api/prompts")
def prompts_list():
    return {"prompts": [store.prompt(n) for n, _ in store.PROMPTS], "contracts": {"extract": extract.CONTRACT, "verify": extract.VERIFY_CONTRACT, "formula": extract.FORMULA_CONTRACT}}


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
