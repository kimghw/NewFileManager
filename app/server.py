"""HWPX 웹 편집 서버(spec_hwpx_웹편집 ② §6). 문서는 메모리(최근 8개)에 두고, 올린 파일마다 작업 폴더에 원본·편집 상태·검증·기록을
저장한다(spec_작업 — 서버를 다시 켜도 작업 목록에서 이어서).

실행: python -m uvicorn app.server:app --host 127.0.0.1 --port 8114"""
import atexit
import copy
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import (division_llm, division_model, division_plan, division_presets, division_profiles, docx_check, docx_restore, docx_struct, fonts, hwpx_struct,
                 outline_edit, owpml_check, pdf_map, pdf_render, restore, verify, works)
from app.docx_doc import W as WNS
from app.docx_doc import DocxDoc
from app.hwpx_doc import P, TC, HwpxDoc

# 문서 형식(확장자)마다 어댑터·구조 편집·원본 복원·표준 검사·문단/칸 태그·내려받기 형식(spec_docx_웹편집 ② §1)
FORMATS = {
    "hwpx": {"cls": HwpxDoc, "struct": hwpx_struct, "restore": restore, "check": owpml_check, "para": P, "cell": TC,
             "mime": "application/hwp+zip"},
    "docx": {"cls": DocxDoc, "struct": docx_struct, "restore": docx_restore, "check": docx_check, "para": WNS + "p",
             "cell": WNS + "tc", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}


def fmt_of(name):
    ext = (name or "").rsplit(".", 1)[-1].lower()
    return ext if ext in FORMATS else None

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).with_name("static")
SAMPLES = ROOT / "samples"
MAX_MB = int(os.environ.get("NFM_MAX_UPLOAD_MB", "200"))
MAX_DOCS = 8
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "bmp": "image/bmp",
               "svg": "image/svg+xml", "webp": "image/webp"}

app = FastAPI(title="NewFileManager — HWPX 웹 편집")
log = logging.getLogger("uvicorn.error")  # 서버 로그(콘솔 인코딩이 한글을 못 써도 예외를 내지 않음 — print 와 달리)


class RevalidatedStatic(StaticFiles):
    """정적 파일(CSS·JS)은 쓸 때마다 서버에 다시 묻게(Cache-Control: no-cache — ETag 가 같으면 304) — 캐시 지시가 없으면 브라우저가
    Last-Modified 기준 추정으로 옛 파일을 그대로 써서, 고친 뒤에도 화면이 옛 모양으로 깨져 보였다(2026-11-09, spec_hwpx_웹편집 ③)."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", RevalidatedStatic(directory=STATIC), name="static")


class Session:
    def __init__(self, name, data, sid=None):
        self.id, self.name, self.original = sid or uuid.uuid4().hex[:12], name, data
        self.fmt = fmt_of(name)
        self.kit = FORMATS[self.fmt]
        self.doc = self.kit["cls"](data)
        self.blocks = self.doc.blocks()
        self.orig_texts = verify.flat_texts(self.blocks)
        self.texts = dict(self.orig_texts)
        self.unrestored = set()  # 글은 원래대로인데 XML 을 원본으로 못 되돌린 문단(줄 배치 캐시가 지워진 채)
        self.pristine = None     # 원본 복원용 — 처음 되돌릴 때 연다
        self.lock = threading.Lock()
        self.touched = time.time()
        self.rebuilt, self.mapping, self.mapping_edited, self.pdf, self.jobs = None, None, None, {}, {}
        # 구조·서식 편집(spec_owpml_편집 ② §3): 모양만 바뀐 문단·나누기/합치기가 닿은 문단·지운 원본 문단·새 문단의 출처·실행 취소 묶음
        self.formatted, self.struct, self.removed, self.origin, self.undo = set(), set(), set(), {}, []
        self.owpml_base, self.owpml_last = None, None
        # 작업 저장(spec_작업 ② §3): 편집 차례·작업 폴더에 쓴 차례·만든 때, 저장 한 번에 하나(plock)
        self.rev, self.saved_rev, self.created, self.plock = 0, 0, time.time(), threading.Lock()
        self.persist_error = None  # 마지막 작업 저장 실패(있으면 화면이 「자동 저장」 대신 실패를 보임)
        # 구분 기준(spec_구분_기준 ② §4·§7): 입력 중 설정 · 마지막 적용(값·rev·planId·요약 — 문서와 함께 저장·실행 취소로 복원) · 마지막 계획(사본 문서 포함, 메모리만 하나)
        self.division = {"settings": None, "applied": None, "plan": None, "hints": []}   # hints = 추가한 자리(spec_구분_기준 ② §11)
        self.outline = None  # 개요(템플릿) 편집 오버레이(spec_hwpx_웹편집 ② §8) — 2단계 그래프에서 만들고 편집마다 손질, 실행 취소·작업 저장과 함께

    def text_edited(self):
        return {i for i, t in self.texts.items() if t != self.orig_texts.get(i)}

    def edited(self):
        return self.text_edited() | self.unrestored | self.formatted | self.struct | self.removed

    def kinds(self):
        """고친 문단마다 종류 — text(글만, 되돌리기 가능)·format(모양, 되돌리기 가능)·struct(나누기·합치기)·new·removed(실행 취소로)."""
        return {i: "removed" if i in self.removed else "new" if i not in self.orig_texts else "struct" if i in self.struct
                else "format" if i in self.formatted else "text" for i in self.edited()}

    def pristine_file(self):
        """지금 저장하면 원본 바이트 그대로인지(고친 XML 부분·새 멤버 없음)."""
        return not self.doc._dirty and not (self.doc._new_members if self.fmt == "hwpx" else self.doc._blobs)

    def state(self):
        return {"editedCount": len(self.edited()), "unrestored": sorted(self.unrestored), "pristine": self.pristine_file(),
                "kinds": self.kinds(), "undo": len(self.undo), "owpml": self.owpml_last,
                "rev": self.rev,  # 서버 편집 차례(spec_작업 ② §3) — 화면이 출력파일 검증의 rev 와 견줘 「검증 뒤 바뀜」 판정
                "persistError": self.persist_error}


DOCS: dict[str, Session] = {}


def _sess(doc_id) -> Session:
    s = DOCS.get(doc_id) or _reopen(doc_id)
    if s is None:
        raise HTTPException(404, "서버에 이 문서(작업)가 없습니다 — 지운 작업이거나 작업 저장이 꺼진 채 서버를 다시 켰습니다. 파일을 다시 열어 주세요")
    s.touched = time.time()
    return s


def _start(sess, kind, fn, *args, revision=None, output=None):
    """검증 작업을 뒤 스레드로 — 끝나면(실패해도) 작업 폴더에 검증 기록을 남긴다(spec_작업 ② §5)."""
    job = verify.Job(kind, verify.steps(kind, sess.fmt))
    job.revision, job.rev, job.output = revision, sess.rev, output
    sess.jobs[kind] = job
    works.log(sess.id, "verify", rev=sess.rev, verify=kind, revision=revision)

    def run():
        try:
            fn(sess, job, *args)
        finally:
            _record(sess, kind, job)
    threading.Thread(target=run, daemon=True).start()
    return job


def _admit(sess):
    while len(DOCS) >= MAX_DOCS:  # 가장 오래 안 쓴 문서부터 비운다(열린 순서가 아니라 마지막 요청 시각) — 작업 폴더에 먼저 쓴다
        old = min(DOCS.values(), key=lambda x: x.touched)
        _persist_safe(old)
        DOCS.pop(old.id, None)
    DOCS[sess.id] = sess


def _open(name, data, source="upload"):
    fmt = fmt_of(name)
    if fmt is None:
        raise HTTPException(400, "hwpx·docx 파일만 열 수 있습니다")
    if len(data) > MAX_MB * 2 ** 20:
        raise HTTPException(413, f"{MAX_MB} MB 보다 큰 파일은 열 수 없습니다")
    try:
        sess = Session(name, data)
    except Exception as e:
        raise HTTPException(400, f"{fmt} 로 열 수 없습니다: {e}") from e
    _admit(sess)
    works.create(sess.id, name, fmt, data, source)  # 올리기 = 새 작업(spec_작업 ② §1)
    _ensure_persister()
    _start(sess, "import", verify.run_import)
    return {"docId": sess.id, "name": name, "size": len(data)}


# ---- 작업 저장·다시 열기·기록(spec_작업 ② §3~§5) ---------------------------------------------------------

PERSIST_EVERY = float(os.environ.get("NFM_PERSIST_EVERY", "1.5"))
MAP_KEYS = ("pages", "pageCount", "ratio", "unit", "twoUp", "sheets", "breaks", "pageStatus")  # 화면·출력파일 검증이 쓰는 매핑 키
_persister = None
_reopen_lock = threading.Lock()


def _map_view(m):
    return m and {k: m[k] for k in MAP_KEYS if k in m}


def _bump(s, kind, **fields):
    """편집 한 번(세션 잠금 안에서) — 차례를 올리고 기록에 한 줄. 작업 폴더에는 배경 저장이 쓴다."""
    s.rev += 1
    works.log(s.id, kind, rev=s.rev, **fields)


def _persist(s, force=False):
    """세션 편집 상태를 작업 폴더에 — 차례가 바뀌었을 때만(force 면 검증 결과·매핑이 바뀐 때도). 묶음은 잠금 안, 쓰기는 잠금 밖."""
    if not works.enabled() or (s.rev == s.saved_rev and not force):
        return
    if DOCS.get(s.id) is not s:  # 메모리에서 비웠거나 지운 세션(늦게 끝난 검증 스레드 등) — 다시 연 세션의 상태를 옛것으로 덮지 않는다
        return
    with s.plock:
        with s.lock:
            rev = s.rev
            snap = s.kit["struct"].snapshot(s.doc)  # 실행 취소와 같은 묶음 — 다시 열 때 struct.restore 로 원본 기준 유지
            state = {"rev": rev, "texts": dict(s.texts), "unrestored": sorted(s.unrestored), "formatted": sorted(s.formatted),
                     "struct": sorted(s.struct), "removed": sorted(s.removed), "origin": dict(s.origin), "owpmlLast": s.owpml_last,
                     "pdf": {k: str(p) for k, p in s.pdf.items() if p}, "mapping": _map_view(s.mapping),
                     "mappingEdited": _map_view(s.mapping_edited),
                     "division": {"settings": s.division["settings"], "applied": s.division["applied"], "hints": s.division.get("hints") or []},  # spec_구분_기준 ② §4·§11
                     "outline": s.outline}  # 개요 편집 오버레이(spec_hwpx_웹편집 ② §8)
            edited = len(s.edited())
        snap = {**snap, "rev": rev, "sha256": works.sha256(snap["bytes"])}
        works.save_state(s.id, s.fmt, snap, state, rev=rev, edited=edited)
        s.saved_rev = rev


def _persist_safe(s, force=False):
    try:
        _persist(s, force)
        s.persist_error = None
    except Exception as e:  # noqa: BLE001 — 저장 실패가 편집을 막지 않는다(다음 차례에 다시). 화면엔 state()["persistError"] 로
        s.persist_error = f"{type(e).__name__}: {e}"
        log.warning("[작업 저장] %s 실패: %r", s.id, e)


def _persist_all():
    for s in list(DOCS.values()):
        _persist_safe(s)


def _persist_loop():
    while True:
        time.sleep(PERSIST_EVERY)
        _persist_all()


def _ensure_persister():
    global _persister
    if _persister is None and works.enabled():
        _persister = threading.Thread(target=_persist_loop, name="work-persist", daemon=True)
        _persister.start()


atexit.register(_persist_all)  # 정상 종료 때 한 번 더(강제 종료는 마지막 PERSIST_EVERY 초 안의 편집을 잃을 수 있음)


def _record(s, kind, job):
    """검증 한 번이 끝남 — verify/<n>-<kind>.json·work.json 요약·기록 한 줄, 매핑·PDF 경로가 바뀌었으니 상태도 다시 쓴다."""
    try:
        v = job.view()
        mapping = s.mapping if kind == "import" else s.mapping_edited
        rec = {"status": v["status"], "at": time.time(), "seconds": v["seconds"], "revision": job.revision, "rev": job.rev,
               "outputSha": job.output, "job": v, "mapping": _map_view(mapping)}
        n = works.add_run(s.id, kind, rec)
        if n is None:
            return
        works.update(s.id, verify={kind: {k: rec[k] for k in ("status", "at", "revision", "rev", "outputSha")} | {"n": n}})
        works.log(s.id, "verified", rev=job.rev, verify=kind, n=n, status=v["status"], seconds=v["seconds"], outputSha=job.output,
                  steps=[{"key": st["key"], "title": st["title"], "status": st["status"]} for st in v["steps"]])
        _persist_safe(s, force=True)
    except Exception as e:  # noqa: BLE001
        log.warning("[작업 저장] %s 검증 기록 실패: %r", s.id, e)


class _Done:
    """디스크의 지난 검증 기록 — 다시 연 작업에서 Job 대신(view()·revision·output 만)."""

    def __init__(self, rec):
        self.rec, self.revision, self.rev, self.output = rec, rec.get("revision"), rec.get("rev"), rec.get("outputSha")

    def view(self):
        return {**self.rec["job"], "running": False, "stored": self.rec["n"]}


def _restore_state(s, got):
    """작업 폴더의 묶음·집합을 세션에 — 묶음 차례·바이트가 상태와 어긋나면 False(원본 그대로 둔다)."""
    snap, st = got["snap"], got["state"]
    if snap is None or not isinstance(st, dict) or snap.get("rev") != st.get("rev") or snap.get("sha256") != works.sha256(snap["bytes"]):
        return False
    doc = s.kit["struct"].restore(s.kit["cls"], s.original, snap)  # 기준 = 원본(원본 복원·바이트 동일 판정), adopt_ids 로 같은 블록 id
    s.doc = doc
    s.texts = dict(st.get("texts") or s.orig_texts)
    s.unrestored, s.formatted = set(st.get("unrestored", ())), set(st.get("formatted", ()))
    s.struct, s.removed, s.origin = set(st.get("struct", ())), set(st.get("removed", ())), dict(st.get("origin") or {})
    s.owpml_last = st.get("owpmlLast")
    s.pdf = {k: p for k, p in (st.get("pdf") or {}).items() if p and Path(p).exists()}  # 렌더 캐시에서 지워진 PDF 는 뺀다
    s.mapping, s.mapping_edited = st.get("mapping"), st.get("mappingEdited")
    dv = st.get("division") or {}
    s.division = {"settings": dv.get("settings"), "applied": dv.get("applied"), "plan": None, "hints": [h for h in dv.get("hints") or [] if isinstance(h, dict)]}
    s.outline = st.get("outline") if isinstance(st.get("outline"), dict) else None
    return True


def _reopen(doc_id):
    """메모리에 없는 작업을 작업 폴더에서 연다(spec_작업 ② §3) — 없으면 None."""
    if works.folder(doc_id) is None:
        return None
    with _reopen_lock:
        s = DOCS.get(doc_id)
        if s is not None:
            return s
        got = works.load(doc_id)
        if got is None:
            return None
        w = got["work"]
        s = Session(w["name"], got["original"], sid=doc_id)
        s.created = w.get("created", s.created)
        ok, why = True, None
        if got["snap"] is not None or got["state"] is not None:
            try:
                ok = _restore_state(s, got)
                why = None if ok else "편집 상태 파일이 서로 맞지 않음"
            except Exception as e:  # noqa: BLE001 — 블록 id 자리표 불일치 등: 원본으로 연다
                ok, why = False, str(e)
            if not ok:  # 원본으로 연다 — 어긋난 편집 상태 파일은 지우지 않고 옆으로(손으로 살릴 수 있게)
                s = Session(w["name"], got["original"], sid=doc_id)
                s.created = w.get("created", s.created)
                works.set_aside_state(doc_id)
                works.update(doc_id, rev=0, edited=0)
        s.rev = s.saved_rev = w.get("rev", 0) if ok else 0
        for kind, rec in works.last_runs(doc_id).items():
            if isinstance(rec, dict) and isinstance(rec.get("job"), dict):
                s.jobs[kind] = _Done(rec)
        _admit(s)
        works.log(doc_id, "reopen", rev=s.rev, ok=ok, **({"reason": why} if why else {}))
        _ensure_persister()
        if "import" not in s.jobs:  # 가져오기 검증이 끝나기 전에 꺼짐 — 다시
            _start(s, "import", verify.run_import)
        return s


@app.get("/")
def index():
    # style.css·app.js 주소에 수정 시각을 붙여(?v=) 파일이 바뀌면 주소도 바뀌게 — 보통 새로 고침만으로 새 CSS·JS 를 받는다(index.html 자체도 no-cache).
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for name in ("style.css", "app.js", "tables.js", "table_edit.js"):
        html = html.replace(f'"/static/{name}"', f'"/static/{name}?v={int((STATIC / name).stat().st_mtime)}"')
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@app.get("/api/status")
def status():
    return {"hangul": pdf_render.available(), "word": pdf_render.available("docx"), "renderDir": str(pdf_render.render_dir())}


@app.get("/api/samples")
def samples():
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(SAMPLES.iterdir()) if p.is_file() and fmt_of(p.name)]


@app.post("/api/samples/{name}")
def open_sample(name: str):
    p = SAMPLES / name
    if p.parent != SAMPLES or not p.is_file():
        raise HTTPException(404, "예제가 없습니다")
    return _open(p.name, p.read_bytes(), "sample")


@app.post("/api/docs")
async def upload(file: UploadFile = File(...)):
    return _open(file.filename or "document.hwpx", await file.read())


@app.get("/api/docs/{doc_id}")
def get_doc(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        edited = s.edited()
        blocks = s.doc.blocks()
        table = s.doc.font_table(blocks) if s.fmt == "docx" else s.doc.font_table()
        return {"docId": s.id, "name": s.name, "format": s.fmt, "size": len(s.original), "blocks": blocks,
                "webFonts": fonts.web_fonts(table),  # 문서 글꼴 @font-face 계획(spec_hwpx_웹편집 ② §3-3)
                "edited": sorted(edited), "original": {i: s.orig_texts.get(i, "") for i in edited},
                "work": {"created": s.created, "rev": s.rev, "stored": works.enabled()},  # 작업(spec_작업 ② §6)
                **s.state()}


@app.get("/api/fonts/{fid}")
def font_file(fid: int):
    """웹 글꼴 계획의 url() — 이 PC 글꼴 목록(fonts.font_index)의 낱 글꼴 파일만(설치 안 된 한컴 동봉 글꼴 등). 경로는 받지 않는다."""
    path = fonts.font_index().file_of(fid)
    if path is None:
        raise HTTPException(404, "그런 글꼴 파일이 없습니다")
    headers = {"Cache-Control": "private, max-age=86400"}
    if isinstance(path, bytes):  # ttc 의 face·내장 비트맵 글꼴 — 뽑은 TTF(fonts.extract_face)
        return Response(path, media_type="font/ttf", headers=headers)
    return FileResponse(path, media_type="font/otf" if path.suffix.lower() == ".otf" else "font/ttf", headers=headers)


def _restore(s, block_id):
    """글이 원래와 같아진 문단을 원본 XML 로 되돌리고(restore.py), 그 XML 부분에 고친 문단이 더 없으면 원본 바이트와 맞춰 본다."""
    rs = s.kit["restore"]  # hwpx: restore.py, docx: docx_restore.py
    if s.pristine is None:
        s.pristine = s.kit["cls"](s.original)
        s.pristine.blocks()  # 블록 id — 같은 차례로 붙어 세션 문서의 원본 요소와 같은 id(restore.restore_para 가 id 로 찾음)
    ok = rs.restore_para(s.doc, s.pristine, block_id)
    (s.unrestored.discard if ok else s.unrestored.add)(block_id)
    part = rs.part_of(s.doc, block_id)
    if ok and part and not any(rs.part_of(s.doc, i) == part for i in s.edited()):
        rs.settle(s.doc, [part])
    if ok and s.fmt == "hwpx" and not (s.formatted or s.struct or s.removed or set(s.texts) - set(s.orig_texts)):
        # 모양·구조 편집이 하나도 안 남음 — 서식 편집이 header 에 더한 정의를 빼서 header 도 원본 바이트로(spec_owpml_편집 ② §3)
        s.doc.drop_unused_defs({k: set(v) for k, v in s.pristine._defs.items()})
        restore.settle(s.doc, ["Contents/header.xml"])
    return ok


@app.patch("/api/docs/{doc_id}/blocks/{block_id}")
def patch_block(doc_id: str, block_id: str, body: dict = Body(...)):
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(400, "text 가 필요합니다")
    return _patch(doc_id, block_id, text, "text")


def _patch(doc_id, block_id, text, kind):
    """문단 글 고침 — kind 는 기록 종류(text = 입력, revert = 「되돌리기」)."""
    s = _sess(doc_id)
    with s.lock:
        el = s.doc._ids.get(block_id)
        if block_id not in s.texts or el is None or el.tag != s.kit["para"] or not s.doc._attached(el):
            raise HTTPException(404, "편집할 수 있는 문단이 아닙니다")
        before = s.texts[block_id]
        try:
            s.doc.set_text(block_id, text.replace("\r", ""))
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)) from e
        s.texts[block_id] = s.doc._text(s.doc._ids[block_id])
        _outline_sync(s)
        restored = None
        orig = s.orig_texts.get(block_id)
        # 모양·구조를 바꾼 문단은 글이 원래대로여도 원본 XML 로 되돌리지 않는다(모양이 사라짐) — 되돌리기 단추·실행 취소로
        plain = orig is not None and block_id not in s.formatted and block_id not in s.struct
        if plain and s.texts[block_id] == orig and (block_id in s.unrestored or s.kit["restore"].part_of(s.doc, block_id) in s.doc._dirty):
            restored = _restore(s, block_id)
        elif s.texts[block_id] != orig:
            s.unrestored.discard(block_id)
        if s.texts[block_id] != before or restored is not None or kind == "revert":
            _bump(s, kind, id=block_id, before=before, after=s.texts[block_id], restored=restored)
        return {"id": block_id, "text": s.texts[block_id], "edited": block_id in s.edited(), "restored": restored, **s.state()}


@app.post("/api/docs/{doc_id}/blocks/{block_id}/revert")
def revert_block(doc_id: str, block_id: str):
    s = _sess(doc_id)
    if block_id not in s.orig_texts or block_id in s.struct or block_id in s.removed:
        raise HTTPException(400, "나누기·합치기·새 문단·지운 문단은 「실행 취소」로 되돌립니다")
    if block_id not in s.formatted:
        return _patch(doc_id, block_id, s.orig_texts[block_id], "revert")
    with s.lock:  # 모양을 바꾼 문단: 글을 되놓고 원본 문단 XML(런·글자 모양·문단 모양·줄 배치)로
        before = s.texts[block_id]
        s.doc.set_text(block_id, s.orig_texts[block_id])
        s.texts[block_id] = s.doc._text(s.doc._ids[block_id])
        s.formatted.discard(block_id)
        ok = _restore(s, block_id)
        if not ok:
            s.formatted.add(block_id)
        _bump(s, "revert", id=block_id, before=before, after=s.texts[block_id], restored=ok, format=True)
        return {"id": block_id, "text": s.texts[block_id], "edited": block_id in s.edited(), "restored": ok, **s.state()}


@app.get("/api/docs/{doc_id}/download")
def download(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        data = s.doc.save()
        same = data == s.original
    ext = "." + s.fmt
    stem = s.name[:-len(ext)] if s.name.lower().endswith(ext) else s.name
    name = s.name if same else f"{stem}_수정{ext}"
    # 기록(spec_작업 ② §4·§5): 내려받은 파일(원본과 다르면 outputs/ 에)·마지막 출력파일 검증 파일과 같은 바이트인지
    sha = works.sha256(data) if same else works.add_output(s.id, s.fmt, data)
    ed = s.jobs.get("edit")
    verified = bool(ed is not None and not ed.view()["running"] and getattr(ed, "output", None) == sha)
    works.log(s.id, "download", rev=s.rev, name=name, size=len(data), sha256=sha, same=same, verified=verified)
    return Response(data, media_type=s.kit["mime"],
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
                             "X-Same-As-Original": "1" if same else "0", "Access-Control-Expose-Headers": "X-Same-As-Original"})


@app.get("/api/docs/{doc_id}/media")
def media(doc_id: str, name: str):
    s = _sess(doc_id)
    ext = name.rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_TYPES:
        raise HTTPException(415, "브라우저가 그릴 수 없는 그림 형식")
    try:
        with s.lock:
            data = s.doc.media(name)
    except KeyError as e:
        raise HTTPException(404, "그림이 없습니다") from e
    return Response(data, media_type=IMAGE_TYPES[ext], headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/docs/{doc_id}/verify")
def start_verify(doc_id: str, body: dict = Body(default={})):
    s = _sess(doc_id)
    kind = body.get("kind", "edit")
    if kind == "import":
        job = s.jobs.get("import")
        if job is None or not job.view()["running"]:
            _start(s, "import", verify.run_import)
    else:
        imp = s.jobs.get("import")
        if imp is not None and imp.view()["running"]:
            raise HTTPException(409, "가져오기 검증이 아직 끝나지 않았습니다")
        job = s.jobs.get("edit")
        if job is not None and job.view()["running"]:
            raise HTTPException(409, "출력파일 검증이 이미 진행 중입니다")
        with s.lock:
            saved, blocks = s.doc.save(), s.doc.blocks()
            edited = s.text_edited() | s.removed          # 글이 달라야 하는 것(새 문단은 원래 글 없음 = 글 고침)
            touched = s.formatted | s.struct              # 글은 같아도 되는 것(모양·구조만)
            unrestored, origin, ids = set(s.unrestored), dict(s.origin), s.doc.id_state()
        # 검사할 파일을 작업 폴더에(spec_작업 ② §5 — 원본과 같으면 해시만), 편집 상태도 지금 한 번 쓴다
        output = works.sha256(saved) if saved == s.original else works.add_output(s.id, s.fmt, saved)
        _persist_safe(s)
        _start(s, "edit", verify.run_edit, saved, edited, blocks, unrestored, touched, origin, ids,
               revision=body.get("revision"), output=output)
    return get_verify(doc_id)


@app.get("/api/docs/{doc_id}/verify")
def get_verify(doc_id: str):
    s = _sess(doc_id)
    out = {k: {**j.view(), "revision": getattr(j, "revision", None), "rev": getattr(j, "rev", None)} for k, j in s.jobs.items()}
    out["mapping"], out["mappingEdited"] = _map_view(s.mapping), _map_view(s.mapping_edited)
    out["pdfs"] = sorted(s.pdf)
    out["rev"] = s.rev  # 서버 편집 차례 — 다시 연 작업에서 화면이 「검증한 뒤 바뀌었는지」를 판정(spec_작업 ② §7)
    return JSONResponse(out)


def _pdf(s, which):
    p = s.pdf.get(which)
    if p is None or not Path(p).exists():
        raise HTTPException(404, "그 PDF 가 아직 없습니다")
    return p


@app.get("/api/docs/{doc_id}/pdf/{which}/{page}.png")
def pdf_page(doc_id: str, which: str, page: int, dpi: int = 110):
    png = pdf_map.page_png(_pdf(_sess(doc_id), which), page, max(60, min(200, dpi)))
    if png is None:
        raise HTTPException(404, "그 쪽이 없습니다")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/docs/{doc_id}/diff/{which}/{page}.png")
def pdf_diff(doc_id: str, which: str, page: int, dpi: int = 110):
    s = _sess(doc_id)
    png = pdf_map.diff_png(_pdf(s, "original"), _pdf(s, which), page, max(60, min(200, dpi)))
    if png is None:
        raise HTTPException(404, "그 쪽이 없습니다")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


# ---- 구조·서식 편집 + OWPML 검사(spec_owpml_편집 ② §2·§3) ------------------------------------------------

def owpml_base(s):
    """원본의 OWPML 위반 종류·개수(기준선) — 가져오기 검증이 먼저 채우고, 없으면 여기서."""
    if s.owpml_base is None:  # hwpx: OWPML, docx: OOXML 참조 규칙(docx_check) — 모양이 같은 모듈
        check = s.kit["check"]
        s.owpml_base = check.counts(check.check_doc(s.kit["cls"](s.original)))
    return s.owpml_base


def _snap(s):
    return {"doc": s.kit["struct"].snapshot(s.doc), "texts": dict(s.texts), "unrestored": set(s.unrestored),
            "formatted": set(s.formatted), "struct": set(s.struct), "removed": set(s.removed), "origin": dict(s.origin),
            "division": copy.deepcopy(s.division["applied"]),  # 구분 기준 적용 상태도 실행 취소와 함께(spec_구분_기준 ② §4)
            "outline": copy.deepcopy(s.outline)}  # 개요 편집 오버레이도(spec_hwpx_웹편집 ② §8)


def _rollback(s, snap):
    s.doc = s.kit["struct"].restore(s.kit["cls"], s.original, snap["doc"])
    s.texts, s.unrestored, s.formatted = dict(snap["texts"]), set(snap["unrestored"]), set(snap["formatted"])
    s.struct, s.removed, s.origin = set(snap["struct"]), set(snap["removed"]), dict(snap["origin"])
    s.division["applied"], s.division["plan"] = copy.deepcopy(snap.get("division")), None  # 계획은 문서 버전에 묶여 있어 되돌리면 무효
    s.outline = copy.deepcopy(snap.get("outline"))


def _para_el(s, block_id, cell_ok=False):
    el = s.doc._ids.get(block_id)
    if el is None or el.tag not in ((s.kit["para"], s.kit["cell"]) if cell_ok else (s.kit["para"],)) or not s.doc._attached(el):
        raise HTTPException(404, "편집할 수 있는 문단이 아닙니다(문서가 바뀌었으면 다시 읽어 주세요)")
    return el


def _hosts_check(s, out, base, header):
    """편집이 닿은 최상위 문단(+header)만 검사 — 기본(문단 나누기·합치기·모양·표 행/열). 닿은 호스트를 out["_hosts"] 에 남긴다."""
    st, chk = s.kit["struct"], s.kit["check"]
    hosts = [h for h in dict.fromkeys(st.top_host(s.doc, e) for e in out["hosts"]) if h is not None]
    out["_hosts"] = hosts
    return chk.verdict(s.doc, base, chk.check_hosts(s.doc, hosts, header=header), local=True)


def _full_check(s, out, base, header):
    """문서 전체 검사(원본 대비 개수 비교) — 떨어진 자리 여러 곳을 한 번에 고친 뒤(구분 기준 반영, spec_구분_기준 ② §4)."""
    chk = s.kit["check"]
    return chk.verdict(s.doc, base, chk.check_doc(s.doc))


def _transact(s, run, op=None, req=None, check=None):
    """구조 편집 트랜잭션(spec_구분_기준 ② §4 — _edit 의 공통부): 세션 잠금 안에서 직전 상태를 묶어 두고 → run() → 검사(check(s, out, base, header) -> verdict,
    기본 _hosts_check) → 원본에 없던 종류의 위반이면 되돌리고 422 → 성공이면 undo 1개·글/집합 갱신·rev +1·기록 1줄.
    run() -> {"hosts": 편집 뒤 닿은 요소, "focus", "formatted", "struct", "origin", "anchor", "log"?: 기록에 더 적을 것}.
    -> (out, 편집 뒤 블록) | (JSONResponse 422, None). run() 의 KeyError·ValueError 는 400(고치다 만 경우 복원)."""
    st, chk = s.kit["struct"], s.kit["check"]
    snap = _snap(s)
    ndefs = sum(len(v) for v in getattr(s.doc, "_defs", {}).values())  # hwpx header 정의 수(docx 서식 편집은 직접 서식 — 정의를 안 더함)
    base = owpml_base(s)
    try:
        out = run()
    except (KeyError, ValueError) as e:
        if s.doc._blocks_cache is None:  # 고치다 만 경우 — 직전 상태로
            _rollback(s, snap)
        raise HTTPException(400, str(e)) from e
    header = sum(len(v) for v in getattr(s.doc, "_defs", {}).values()) != ndefs
    if s.fmt == "docx":
        s.doc.blocks()  # docx 검사는 위반 자리를 블록 id 로 적는다 — 새 문단·칸에도 id 를 붙여 둔다
    v = (check or _hosts_check)(s, out, base, header)
    if v["status"] == "fail":
        _rollback(s, snap)
        std = "OWPML 표준" if s.fmt == "hwpx" else "OOXML 참조 규칙"
        works.log(s.id, "rejected", rev=s.rev, op=op, req=req, summary=chk.summary_text(v))
        return JSONResponse({"detail": f"{std}에 어긋나는 편집이라 되돌렸습니다 — " + chk.summary_text(v), "owpml": v},
                            status_code=422), None
    s.undo.append(snap)
    del s.undo[:-st.UNDO_MAX]
    after = s.doc.blocks()
    old = set(s.texts)
    cur = verify.flat_texts(after)
    for i in s.texts:  # 글이 비어 블록 목록에서 빠진 문단(개체만 남은 문단)도 지금 글로 둔다
        if i not in cur and s.doc._attached(s.doc._ids.get(i)) and s.doc._ids[i].tag == s.kit["para"]:
            cur[i] = s.doc._text(s.doc._ids[i])
    s.texts = cur
    s.formatted |= out.get("formatted", set())
    s.struct |= out.get("struct", set())
    for i in set(cur) - old:
        s.origin.setdefault(i, out.get("origin", {}).get(i, out.get("anchor")))
    s.removed = {i for i in s.orig_texts if not s.doc._attached(s.doc._ids.get(i))}
    s.unrestored -= s.removed
    s.owpml_last = {"status": v["status"], "summary": chk.summary_text(v)}
    _outline_sync(s)
    _bump(s, op or "edit", req=req, owpml=s.owpml_last, **(out.get("log") or {}))
    return out, after


def _edit(doc_id, make, op=None, req=None):
    """구조·서식 편집 한 번(_transact 위) — 닿은 최상위 문단(+header)만 OWPML 검사. make(s) -> (편집 전 닿는 요소들, run).
    응답 tops = 바뀐 최상위 블록 {drop: 옛 id, blocks: 새 블록}."""
    s = _sess(doc_id)
    with s.lock:
        st = s.kit["struct"]
        before, run = make(s)
        drop = [i for h in dict.fromkeys(st.top_host(s.doc, e) for e in before) if h is not None
                for i in st.top_ids(s.doc, h)]
        out, after = _transact(s, run, op, req)
        if after is None:
            return out
        want = {i for h in out["_hosts"] for i in st.top_ids(s.doc, h)}
        tops = [b for b in after if b["id"] in want]
        return {"tops": {"drop": drop, "blocks": tops}, "texts": verify.flat_texts(tops), "focus": out.get("focus"),
                "edited": sorted(s.edited()), "original": {i: s.orig_texts.get(i, "") for i in s.edited()}, **s.state()}


@app.post("/api/docs/{doc_id}/split")
def split(doc_id: str, body: dict = Body(...)):
    """문단 나누기 {id, offset} — offset 뒤가 새 문단(Enter)."""
    pid, offset = body.get("id"), body.get("offset")
    if not isinstance(offset, int):
        raise HTTPException(400, "offset(정수)이 필요합니다")

    def make(s):
        p = _para_el(s, pid)

        def run():
            new = s.doc.split_para(pid, offset)
            return {"hosts": [p, s.doc._ids[new]], "focus": {"id": new, "offset": 0}, "struct": {pid}, "origin": {new: pid}}
        return [p], run
    return _edit(doc_id, make, "split", body)


@app.post("/api/docs/{doc_id}/merge")
def merge(doc_id: str, body: dict = Body(...)):
    """문단 합치기 {id, dir: prev|next} — prev = 앞 문단 끝에 이 문단을 붙임(맨 앞 Backspace), next = 이 문단 끝에 뒤 문단(맨 끝 Delete)."""
    pid, way = body.get("id"), body.get("dir", "next")
    if way not in ("prev", "next"):
        raise HTTPException(400, "dir 은 prev 또는 next")

    def make(s):
        p = _para_el(s, pid)
        a = s.doc._sibling(p, -1) if way == "prev" else p
        if a is None:
            raise HTTPException(400, "앞 문단이 없습니다(구역·칸의 첫 문단)")
        b = s.doc._sibling(a, +1)
        aid = s.doc._id(a)

        def run():
            r = s.doc.merge_paras(aid)
            return {"hosts": [a], "focus": {"id": aid, "offset": r["offset"]}, "struct": {aid}}
        return [a] + ([b] if b is not None else []), run
    return _edit(doc_id, make, "merge", body)


@app.post("/api/docs/{doc_id}/format/chars")
def format_chars(doc_id: str, body: dict = Body(...)):
    """글자 모양 {id, start, end, changes: {bold|italic|underline: true|false|"toggle", sizePt, color}} — 빈 범위 = 문단 전체."""
    pid = body.get("id")

    def make(s):
        p = _para_el(s, pid)

        def run():
            r = s.doc.format_chars(pid, int(body.get("start", 0)), int(body.get("end", 0)), body.get("changes") or {})
            return {"hosts": [p], "focus": {"id": pid, "offset": r["start"], "end": r["end"]}, "formatted": {pid}}
        return [p], run
    return _edit(doc_id, make, "chars", body)


@app.post("/api/docs/{doc_id}/format/para")
def format_para(doc_id: str, body: dict = Body(...)):
    """문단 모양 {ids, changes: {align, indentLeftMm, indentRightMm, firstLineMm, lineSpacingPct, spaceBeforePt, spaceAfterPt}}."""
    ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
    if not ids:
        raise HTTPException(400, "ids 가 필요합니다")

    def make(s):
        ps = [_para_el(s, i) for i in ids]

        def run():
            changed = s.doc.format_para(ids, body.get("changes") or {})
            return {"hosts": ps, "focus": {"id": ids[0], "offset": int(body.get("offset", 0))}, "formatted": set(changed)}
        return ps, run
    return _edit(doc_id, make, "para", body)


# 표 행·열 편집 `POST /api/docs/{doc_id}/table` 은 표 모듈 app/tables_api.py 에(2026-11-10 — 트랜잭션 _edit 는 공유, spec_owpml_편집 ② §2).


@app.post("/api/docs/{doc_id}/undo")
def undo(doc_id: str):
    """마지막 구조·서식 편집 직전으로 — 그 뒤 고친 글도 함께 돌아간다. 응답 = GET /api/docs/{id}(블록 전체)."""
    s = _sess(doc_id)
    with s.lock:
        if not s.undo:
            raise HTTPException(400, "되돌릴 구조·서식 편집이 없습니다")
        _rollback(s, s.undo.pop())
        s.owpml_last = None
        _bump(s, "undo")
    return get_doc(doc_id)


# ---- 개요(템플릿) 편집(spec_hwpx_웹편집 ② §8) ----------------------------------------------------------------------
# 2단계 헤딩 그래프(graph.json) 위 오버레이(s.outline — outline_edit.build_overlay)로 Enter(하위 줄)·Alt+Enter(같은 레벨 뼈대)·Alt+↑/↓(레벨)·끌기(옮김)·
# 빈 줄 Backspace(지움)를 _edit 트랜잭션 하나로. hwpx 만(그래프가 hwpx 뿐).

def _outline_probe(s):
    doc = s.doc

    def probe(pid):
        el = doc._ids.get(pid)
        if el is None or el.tag != P or not doc._attached(el):
            return None
        prev = el.getprevious()
        while prev is not None and not isinstance(prev.tag, str):
            prev = prev.getprevious()
        sp = doc.para_attrs(doc._rev[prev]) if prev is not None and prev.tag == P and prev in doc._rev and doc.is_spacer(prev) else None
        return {"text": doc._text(el), "attrs": doc.para_attrs(pid), "spacer": sp}
    return probe


def _outline_ov(s, build=True):
    """세션의 개요 오버레이 — 2단계 결과가 없으면 None. 그래프 실행(run·at)이 오버레이 것과 다르면(2단계를 다시 돌림) 새로 만든다."""
    if s.fmt != "hwpx":
        return None
    g = heading_runs.graph(s)
    if g is None:
        return None
    meta = g.get("meta") or {}
    key = [meta.get("run"), meta.get("at")]
    ov = s.outline
    if (ov is None or ov.get("run") != key) and build:
        ov = s.outline = outline_edit.build_overlay(g, _outline_probe(s), rev=s.rev)
    return ov


def _outline_sync(s):
    """편집(글 고침·구조·개요) 뒤 — 떨어져 나갔거나 레터가 첫머리에서 사라진 줄을 오버레이에서 뺀다(astra P1-1 「살아 있는 id 만으로 믿지 않음」)."""
    ov = s.outline
    if not ov:
        return
    doc = s.doc

    def alive(pid):
        el = doc._ids.get(pid)
        return el is not None and el.tag == P and doc._attached(el)
    outline_edit.sync(ov, alive, lambda pid: doc._text(doc._ids[pid]))
    ov["rev"] = s.rev + 1


def _outline_seq(s, el):
    """el(문단)이 든 그릇(구역·표 칸 subList)의 문단 열 — 문서 순, 모든 hp:p."""
    doc, par = s.doc, el.getparent()
    seq = []
    for c in par.iterchildren(P):
        seq.append({"id": doc._id(c), "text": doc._text(c), "blank": doc.is_spacer(c), "object": doc._has_object(c)})
    return par, seq


@app.get("/api/docs/{doc_id}/outline")
def outline_get(doc_id: str):
    """개요 오버레이 요약(문단 → 템플릿 #N·레벨·레터, 템플릿 → 사슬) — 화면 표시·끌기 손잡이·키 판정용.
    2단계 결과가 없거나 docx 면 200 {"off": true, "lines": {}, …}(문서를 열 때마다 부르므로 404 로 콘솔 오류를 남기지 않음 — c1 세션 지적)."""
    s = _sess(doc_id)
    with s.lock:
        ov = _outline_ov(s)
        if ov is None:
            return {"off": True, "why": "헤딩 추출 2단계(헤딩 그래프) 결과가 없습니다" if s.fmt == "hwpx" else "개요 편집은 HWPX 에서만 됩니다",
                    "run": None, "rev": s.rev, "lines": {}, "templates": {}}
        return outline_edit.view(ov)


OUTLINE_OPS = ("enter", "sibling", "level", "move", "remove")


@app.post("/api/docs/{doc_id}/outline")
def outline(doc_id: str, body: dict = Body(...)):
    """개요 편집 한 번 {op: enter|sibling|level|move|remove, id, offset?, end?(고른 글 끝), ids?(level — 같은 그릇), delta?(±1), target?, where?(before|after)}.
    응답 = _edit 응답 + outline{lines: 바뀐·새 줄, removed} — 화면이 표시를 고친다."""
    op = body.get("op")
    if op not in OUTLINE_OPS:
        raise HTTPException(400, f"op 는 {', '.join(OUTLINE_OPS)} 중 하나")
    s0 = _sess(doc_id)
    if s0.fmt != "hwpx":
        raise HTTPException(400, "개요 편집은 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    extra = {}

    def make(s):
        ov = _outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        ids = [body.get("id")] if op != "level" else list(dict.fromkeys(body.get("ids") or ([body["id"]] if body.get("id") else [])))
        if not ids or not all(isinstance(i, str) for i in ids):
            raise HTTPException(400, "id 가 필요합니다")
        els = [_para_el(s, i) for i in ids]
        par, seq = _outline_seq(s, els[0])
        if any(e.getparent() is not par for e in els):
            raise HTTPException(400, "같은 구역·칸 안의 문단들만 함께 바꿀 수 있습니다")
        pos = {it["id"]: k for k, it in enumerate(seq)}
        text_of = lambda pid: s.doc._text(s.doc._ids[pid])  # noqa: E731
        try:
            if op == "enter":
                plan = outline_edit.plan_enter(seq, pos[ids[0]], body.get("offset", 0), body.get("end"), ov, text_of)
            elif op == "sibling":
                plan = outline_edit.plan_sibling(seq, pos[ids[0]], ov, text_of)
            elif op == "level":
                delta = body.get("delta")
                if delta not in (-1, 1):
                    raise HTTPException(400, "delta 는 -1 또는 1")
                plan = outline_edit.plan_level(seq, [pos[i] for i in ids], delta, ov, text_of)
            elif op == "move":
                tgt = _para_el(s, body.get("target"))
                if tgt.getparent() is not par:
                    raise ValueError("같은 구역·칸 안의 줄로만 옮길 수 있습니다")
                plan = outline_edit.plan_move(seq, pos[ids[0]], pos[s.doc._id(tgt)], "before" if body.get("where") == "before" else "after", ov, text_of)
            else:
                plan = outline_edit.plan_remove(seq, pos[ids[0]], ov, text_of)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        touched = {pid for a in plan["actions"] for pid in (a.get("id"), a.get("after"), a.get("ref"), a.get("first"), a.get("last"))
                   if isinstance(pid, str) and not pid.startswith("$")}
        before = [s.doc._ids[i] for i in touched if i in s.doc._ids]

        def run():
            return _outline_run(s, ov, par, plan, extra, op, ids)
        return before, run
    out = _edit(doc_id, make, "outline", body)
    if isinstance(out, dict):
        out["outline"] = extra
    return out


def _outline_run(s, ov, par, plan, extra, op, ids):
    """계획의 행동들을 hwpx_struct 원시 연산으로 실행하고 오버레이에 반영 — 닿은 범위는 그릇 안 **이어진 구간 전체**(화면이 첫 drop~마지막 drop 을 통째로 바꾸므로, astra P1-4)."""
    doc = s.doc
    last, first_new, prev_line, new_ids, changed, removed = None, None, None, [], {}, []
    struct, formatted, origin = set(), set(), {}
    focus = plan.get("focus") or {}

    def rid(x):
        if x == "$last":
            return last
        if x in ("$first", "$new"):
            return first_new
        return x

    def put_line(pid, line):
        line = dict(line)
        if line.get("parent") == "$prev":
            line["parent"] = prev_line
        ov["lines"][pid] = line
        changed[pid] = outline_edit.line_view(line)
        return pid

    for a in plan["actions"]:
        kind = a["act"]
        if kind == "erase":
            doc.delete_text(a["id"], a["start"], a["end"])
            struct.add(a["id"])
        elif kind == "split_restyle":
            new = doc.split_para(a["id"], a["at"])
            doc.replace_prefix(new, 0, a["prefix"], attrs=a["attrs"])
            struct.add(a["id"])
            origin[new] = a["id"]
            last = first_new = new
            new_ids.append(new)
            prev_line = put_line(new, a["line"])
        elif kind == "insert":
            new = doc.insert_like(rid(a["after"]), None, a["text"], after=True, attrs=a["attrs"])
            origin[new] = a.get("origin")
            last = new
            if first_new is None or a.get("head"):
                first_new = new
            new_ids.append(new)
            if a.get("line"):
                prev_line = put_line(new, a["line"])
        elif kind == "insert_blank":
            new = doc.insert_like(rid(a["after"]), None, "", after=True, attrs=a["attrs"])
            origin[new] = ids[0]
            new_ids.append(new)
            if not a.get("before_new"):
                last = new
        elif kind == "restyle":
            doc.replace_prefix(a["id"], a["old_len"], a["prefix"], attrs=a["attrs"])
            formatted.add(a["id"])
            put_line(a["id"], a["line"])
        elif kind == "retext":
            doc.replace_prefix(a["id"], a["old_len"], a["prefix"])
            if a["id"] in ov["lines"]:
                ov["lines"][a["id"]]["letter"] = a["letter"]
                changed[a["id"]] = outline_edit.line_view(ov["lines"][a["id"]])
        elif kind == "move":
            moved = doc.move_paras(rid(a["first"]), rid(a["last"]), rid(a["ref"]), after=a["after"])
            struct |= set(moved)
        elif kind == "remove":
            r = doc.remove_para(a["id"])
            removed.append(a["id"])
            ov["lines"].pop(a["id"], None)
        elif kind == "reparent":
            if a["id"] in ov["lines"]:
                ov["lines"][a["id"]]["parent"] = a["parent"]
    # 닿은 범위 = 그릇 안 이어진 구간 전체(가장 앞 ~ 가장 뒤 닿은 문단 사이의 모든 문단 — 표 호스트 포함)
    kids = [c for c in par.iterchildren(P)]
    ix = {c: k for k, c in enumerate(kids)}
    hit = [doc._ids[i] for a in plan["actions"] for i in (a.get("id"), rid(a.get("after")), rid(a.get("ref")), rid(a.get("first")), rid(a.get("last")))
           if i and i in doc._ids and doc._ids[i] in ix] + [doc._ids[i] for i in new_ids if i in doc._ids and doc._ids[i] in ix]
    if hit:
        lo, hi = min(ix[e] for e in hit), max(ix[e] for e in hit)
        hosts = kids[max(0, lo - 1):hi + 2]  # 이웃 하나씩 더(지운 줄의 앞뒤)
    else:
        hosts = kids[:1]
    fid = rid(focus.get("id")) if focus.get("id") else None
    off = focus.get("offset")
    if off == "end" and fid and fid in doc._ids:
        off = len(doc._text(doc._ids[fid]))
    if off is None and fid and fid in doc._ids and fid in ov["lines"]:
        off = outline_edit.prefix_len(doc._text(doc._ids[fid]), ov["lines"][fid]["letter"])
    extra.update({"lines": changed, "removed": removed, "new": new_ids, "focuses": plan.get("focuses")})
    return {"hosts": hosts, "focus": {"id": fid, "offset": off or 0} if fid else None, "struct": struct, "formatted": formatted, "origin": origin,
            "anchor": ids[0], "log": {"op": op, "ids": ids, "new": new_ids, "removed": removed}}


@app.get("/api/docs/{doc_id}/owpml")
def owpml_now(doc_id: str):
    """지금 상태 전체를 OWPML 검사(원본 대비)."""
    s = _sess(doc_id)
    with s.lock:
        base = owpml_base(s)
        if s.fmt == "docx":
            s.doc.blocks()
        return s.kit["check"].verdict(s.doc, base, s.kit["check"].check_doc(s.doc))


# ---- 작업 목록·기록 API(spec_작업 ② §6) ------------------------------------------------------------------

WORK_KEYS = ("id", "name", "format", "size", "source", "created", "updated", "rev", "edited", "verify")


def _work_or_404(wid):
    w = works.work(wid)
    if w is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    return w


@app.get("/api/works")
def works_list():
    """작업 목록 — 최근 바뀐 차례. open = 지금 서버 메모리에 열려 있음."""
    return [{**{k: w.get(k) for k in WORK_KEYS}, "open": w["id"] in DOCS} for w in works.list_works()]


@app.get("/api/works/{wid}/log")
def work_log(wid: str):
    w = _work_or_404(wid)
    return {"work": {k: w.get(k) for k in WORK_KEYS}, "events": works.events(wid), "runs": works.runs(wid)}


@app.get("/api/works/{wid}/headings-preview")
def work_headings_preview(wid: str):
    """비교용 읽기 전용 스냅샷 — 닫힌 문서를 다시 열거나 추출·검증하지 않는다."""
    from app import heading_compare
    result = heading_compare.preview(wid, DOCS.get(wid), WORK_KEYS)
    if result is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    return result


@app.get("/api/works/{wid}/runs/{n}")
def work_run(wid: str, n: int):
    _work_or_404(wid)
    r = works.run(wid, n)
    if r is None:
        raise HTTPException(404, "그 검증 기록이 없습니다")
    return r


@app.get("/api/works/{wid}/file/{which}")
def work_file(wid: str, which: str):
    """작업의 원본(original)·지금 편집본(current — 마지막 저장 차례) 파일."""
    w = _work_or_404(wid)
    p = works.file_path(wid, which)
    if p is None:
        raise HTTPException(404, "그 파일이 없습니다")
    ext = "." + w["format"]
    stem = w["name"][:-len(ext)] if w["name"].lower().endswith(ext) else w["name"]
    name = w["name"] if which == "original" or p.name.startswith("original.") else f"{stem}_수정{ext}"
    return FileResponse(p, media_type=FORMATS[w["format"]]["mime"], filename=name)


@app.delete("/api/works/{wid}")
def work_delete(wid: str):
    s = DOCS.pop(wid, None)
    gone = works.delete(wid)
    if s is None and not gone:
        raise HTTPException(404, "그런 작업이 없습니다")
    return {"ok": True}


# ---- 헤딩 추출(spec_헤딩_추출 ② §7) — 세션마다 헤딩 작업 하나, 검증 작업(s.jobs)과 따로 ---------------------------------

from app import heading_calc, heading_guides, heading_rules, heading_runs, llm, tables_api  # noqa: E402


def _heads_hwpx(s):
    if s.fmt != "hwpx":
        raise HTTPException(400, "헤딩 추출은 지금 hwpx 만 됩니다")


@app.get("/api/docs/{doc_id}/headings")
def headings_state(doc_id: str):
    """헤딩 작업 상태 + 지금 결과 요약(1단계·2단계, 오래됨 = 결과를 뽑은 뒤 문서가 바뀜)."""
    return heading_runs.summary(_sess(doc_id))


@app.post("/api/docs/{doc_id}/headings", status_code=202)
def headings_start(doc_id: str, body: dict = Body(default={})):
    """{stage: 1|2|3, llm: bool} — 뒤 스레드로 시작(돌고 있으면 409). 3 = 표 구조(spec_헤딩_추출 ② §8)."""
    s = _sess(doc_id)
    _heads_hwpx(s)
    stage, use_llm = body.get("stage", 1), body.get("llm", False)
    if type(stage) is not int or stage not in (1, 2, 3):  # true·1.0·"1" 은 거절
        raise HTTPException(400, "stage 는 1·2·3")
    if not isinstance(use_llm, bool):  # "false" 를 참으로 읽어 LLM 을 돌리지 않게
        raise HTTPException(400, "llm 은 true 또는 false")
    try:
        job = heading_runs.start(s, stage, use_llm)
    except heading_runs.Busy as e:
        raise HTTPException(409, str(e)) from e
    return job.view()


@app.get("/api/docs/{doc_id}/headings/paras")
def headings_paras(doc_id: str, kind: str = None, fmt: str = None, rule: str = None, area: str = None, q: str = None,
                   offset: int = 0, limit: int = 100):
    return heading_runs.paras(_sess(doc_id), kind=kind, fmt=fmt, rule=rule, area=area, q=q, offset=max(0, offset), limit=limit)


@app.get("/api/docs/{doc_id}/headings/labels")
def headings_labels(doc_id: str):
    return heading_runs.labels(_sess(doc_id))


@app.get("/api/docs/{doc_id}/headings/graph")
def headings_graph(doc_id: str):
    g = heading_runs.graph(_sess(doc_id))
    if g is None:
        raise HTTPException(404, "2단계(헤딩 그래프) 결과가 없습니다")
    return g


@app.get("/api/docs/{doc_id}/headings/tables")
def headings_tables(doc_id: str):
    """3단계 표 구조 결과 전체(표마다 칸 역할·서브 테이블·헤더 경로 — spec_헤딩_추출 ② §8)."""
    t = heading_runs.tables(_sess(doc_id))
    if t is None:
        raise HTTPException(404, "3단계(표 구조) 결과가 없습니다")
    return t


@app.get("/api/docs/{doc_id}/headings/tables/{tid}/xlsx")
def headings_table_xlsx(doc_id: str, tid: str):
    """3단계 표 하나를 엑셀로(spec_헤딩_추출 ② §9) — 시트 「표」(격자 + 엑셀 수식) · 「검증」 · 「필드」 · 「정보」."""
    s = _sess(doc_id)
    t = heading_runs.tables(s)
    if t is None:
        raise HTTPException(404, "3단계(표 구조) 결과가 없습니다")
    tb = next((x for x in t["tables"] if x["id"] == tid), None)
    if tb is None:
        raise HTTPException(404, "그 표가 없습니다")
    try:
        data = heading_calc.workbook(tb, s.name)
    except ImportError:
        raise HTTPException(503, "openpyxl 이 없어 엑셀을 만들 수 없습니다(pip install openpyxl)")
    stem = s.name.rsplit(".", 1)[0] if "." in s.name else s.name
    name = f"{stem}_{tid}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"})


# ---- 표 모듈 끝점은 app/tables_api.py(표 지침·사용자 수식 — spec_헤딩_추출 ② §10 「모듈」, 사용자 "본문 따로, 테이블 따로") ----------------------------------------
app.include_router(tables_api.router)


def _rules_view():
    st = heading_rules.load()
    off = {k for k, v in st["builtin"].items() if v.get("enabled") is False}
    return {"version": st["version"], "builtin": [{**{k: r[k] for k in ("id", "name", "kind", "family", "pattern", "scope")}, "enabled": r["id"] not in off}
                                                  for r in heading_rules.BUILTIN],
            "learned": st["rules"], "keeps": st.get("keeps", []), "store": str(heading_rules.store_dir() or "off")}


@app.get("/api/headings/rules")
def headings_rules():
    return _rules_view()


@app.patch("/api/headings/rules/{rid}")
def headings_rule_patch(rid: str, body: dict = Body(...)):
    """{enabled?: bool, status?: candidate|global, version?: int} — version 이 다르면 409. 둘 다 오면 둘 다 되거나 아무것도 안 됨."""
    if "enabled" in body and not isinstance(body["enabled"], bool):  # "false" 를 켬으로 읽지 않게
        raise HTTPException(400, "enabled 는 true 또는 false")
    try:
        with heading_rules._LOCK:  # 두 번 고치는 사이에 다른 쓰기가 못 끼게(RLock — update 도 같은 잠금)
            if "status" in body:  # 둘째(status)가 거절할 요청이면 첫째(enabled)를 쓰기 전에 거절
                if body["status"] not in ("candidate", "global"):
                    raise ValueError(f"status 는 candidate·global: {body['status']!r}")
                if not any(r.get("id") == rid for r in heading_rules.load(strict=True)["rules"]):
                    raise KeyError(rid)  # 없는 규칙 · 내장 규칙(상태 없음)
            if "enabled" in body:
                heading_rules.set_enabled(rid, body["enabled"], expect=body.get("version"), reason="화면")
            if "status" in body:
                heading_rules.set_status(rid, body["status"], expect=None if "enabled" in body else body.get("version"), reason="화면")
    except heading_rules.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"그런 규칙이 없습니다: {rid}") from e
    except ValueError as e:  # 잘못된 값 · 정수 아닌 version · 깨진 rules.json(StoreBroken)
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"규칙을 저장하지 못했습니다: {e}") from e
    return _rules_view()


@app.delete("/api/headings/rules/{rid}")
def headings_rule_delete(rid: str, version: int = None):
    try:
        heading_rules.delete_rule(rid, expect=version, reason="화면")
    except heading_rules.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"그런 규칙이 없습니다: {rid}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"규칙을 저장하지 못했습니다: {e}") from e
    return _rules_view()


@app.get("/api/headings/guides")
def headings_guides():
    return heading_guides.listing()


def _guide_name(name):
    if name not in heading_guides.NAMES:
        raise HTTPException(404, f"그런 지침이 없습니다: {name}")
    return name


@app.get("/api/headings/guides/{name}")
def headings_guide(name: str):
    return heading_guides.get(_guide_name(name))


@app.put("/api/headings/guides/{name}")
def headings_guide_put(name: str, body: dict = Body(...)):
    """{text, version?, reason?} 사용자 사본 저장 · {rebase: true} 기본본 바뀜 확인."""
    name = _guide_name(name)
    try:
        if body.get("rebase"):
            return heading_guides.rebase(name)
        return heading_guides.save(name, body.get("text"), expect=body.get("version"), reason=str(body.get("reason") or "화면")[:200])
    except heading_rules.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"지침을 저장하지 못했습니다: {e}") from e


@app.delete("/api/headings/guides/{name}")
def headings_guide_reset(name: str):
    name = _guide_name(name)
    try:
        return heading_guides.reset(name, reason="화면 — 기본본으로")
    except OSError as e:
        raise HTTPException(503, f"지침을 되돌리지 못했습니다: {e}") from e


@app.get("/api/headings/history")
def headings_history(kind: str = None, limit: int = 200):
    return heading_rules.history(kind if kind in ("rules", "guide") else None, max(1, min(limit, 1000)))


@app.get("/api/headings/llm")
def headings_llm():
    return llm.status()


# ---- 구분 기준(spec_구분_기준 ② §7) — 설정 · 계획(사본 모의 실행) · 반영(공통 트랜잭션 + 문서 전체 검사) · 문서에서 읽기 · 저장한 기준 ----------------

PROFILE = division_profiles.get("rnd")   # 1차 프로파일 하나(국가R&D) — 문서마다 고르게 되면 settings.profileId 로


def _division_settings(body):
    try:
        return division_model.norm_settings(body, PROFILE)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, f"구분 값 오류: {e}") from e


def _division_view(s):
    """GET …/divisions 의 몸통(세션 잠금 안에서) — 프로파일·양식 판정·입력 중 설정(+파생 뷰)·마지막 적용·마지막 계획 요약·오래됨."""
    form = PROFILE.form_of(s.doc.blocks())
    plan, settings = s.division.get("plan"), s.division["settings"]
    return {"profile": {"id": PROFILE.ID, "name": PROFILE.NAME, "version": PROFILE.VERSION, "form": form, "supported": PROFILE.supported(form),
                        "supportedForms": sorted(PROFILE.SUPPORTED)},
            "settings": settings, "dimensions": PROFILE.dimensions(settings["values"]) if settings else None,
            "applied": s.division["applied"], "plan": division_plan.brief(plan) if plan else None,
            "hints": s.division.get("hints") or [],   # 추가한 자리(② §11) — 수·출처만 쓰고 상세는 members
            "stale": bool(plan) and plan["baseRev"] != s.rev, "rev": s.rev}


@app.get("/api/docs/{doc_id}/divisions")
def divisions_get(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        view = _division_view(s)
    return {**view, "presets": division_presets.listing()}


@app.put("/api/docs/{doc_id}/divisions/settings")
def divisions_settings(doc_id: str, body: dict = Body(...)):
    """입력 중 설정 {values} (또는 FMM v1 값 그대로) — 저장만(문서는 그대로). 값이 달라지면 지금 계획은 버린다."""
    settings = _division_settings(body)
    s = _sess(doc_id)
    with s.lock:
        before = division_model.settings_hash(s.division["settings"]) if s.division["settings"] else None
        s.division["settings"] = settings
        if division_model.settings_hash(settings) != before:
            s.division["plan"] = None
        view = _division_view(s)
    _persist_safe(s, force=True)  # rev 가 안 바뀌어도 설정은 작업에 남긴다
    return view


@app.get("/api/docs/{doc_id}/divisions/plan")
def divisions_plan_get(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        plan = s.division.get("plan")
        if plan is None:
            raise HTTPException(404, "계획이 없습니다")
        return {**division_plan.view(plan), "stale": plan["baseRev"] != s.rev, "rev": s.rev}


@app.post("/api/docs/{doc_id}/divisions/plan")
def divisions_plan(doc_id: str, body: dict = Body(default={})):
    """{values?, only?: 묶음 key, skip?: [key]} → 계획(spec_구분_기준 ② §3·§7). 문서는 그대로 — 작업용 사본에서 모의 실행(잠금 밖, 사본만 만짐).
    values 가 없으면 입력 중 설정. 지원하지 않는 양식이면 400."""
    only, skip = body.get("only"), body.get("skip") or []
    if only is not None and not isinstance(only, str):
        raise HTTPException(400, "only 는 묶음 key")
    if not isinstance(skip, list) or not all(isinstance(x, str) for x in skip):
        raise HTTPException(400, "skip 은 key 목록")
    settings = _division_settings(body) if body.get("values") is not None else None
    s = _sess(doc_id)
    with s.lock:
        settings = settings or s.division["settings"]
        if settings is None:
            raise HTTPException(400, "구분 값을 먼저 넣으세요")
        s.division["settings"] = settings
        rev = s.rev
        applied = s.division["applied"]
        rebuild = not (applied and applied.get("values") == settings["values"])  # 같은 값을 이미 전체 반영한 문서면 자리표시를 다시 본뜨지 않음(FMM divisionsDone)
        hints = [h["para"] for h in s.division.get("hints") or [] if h.get("para")]   # 추가한 자리(② §11) — 후보·모의 실행에
        copy_doc, snap = division_plan.snapshot_copy(s.kit, s.original, s.doc)
    try:
        plan = division_plan.make(s.kit, s.original, copy_doc, rev, settings, PROFILE, only=only, skip=skip, rebuild=rebuild, copy=(copy_doc, snap), hints=hints)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    with s.lock:
        s.division["plan"] = plan
        stale = plan["baseRev"] != s.rev
    works.log(s.id, "divisionPlan", rev=rev, planId=plan["planId"], settingsHash=plan["settingsHash"], only=only, skip=skip, summary=plan["summary"])
    return {**division_plan.view(plan), "stale": stale, "rev": s.rev}


@app.post("/api/docs/{doc_id}/divisions/apply")
def divisions_apply(doc_id: str, body: dict = Body(...)):
    """{planId, expectRev?} → 고정된 계획만 반영(spec_구분_기준 ② §4): 계획의 사본 문서를 세션 문서로 바꿔 넣고 문서 전체 검사 → 실패면 복원·422,
    성공이면 undo 1·rev +1·기록 1줄 + 상세 결과 파일. 계획이 없거나 문서가 계획 뒤에 바뀌었으면 409(다시 계획). 화면은 문서를 다시 읽는다."""
    plan_id, expect = body.get("planId"), body.get("expectRev")
    s = _sess(doc_id)
    with s.lock:
        plan = s.division.get("plan")
        if plan is None or plan["planId"] != plan_id:
            raise HTTPException(409, "계획이 없거나 바뀌었습니다 — 다시 계획하세요")
        if plan["baseRev"] != s.rev or (expect is not None and expect != s.rev):
            raise HTTPException(409, "계획을 세운 뒤 문서가 바뀌었습니다 — 다시 계획하세요")
        if plan["profileVersion"] != PROFILE.VERSION:
            raise HTTPException(409, "프로파일이 바뀌었습니다 — 다시 계획하세요")
        if not plan["_report"]["groups"] and not plan["_report"]["changes"]:  # 할 일 없음 — undo·rev 를 늘리지 않는다
            s.division["plan"] = None
            return {"nothing": True, "applied": s.division["applied"], "summary": plan["summary"], **s.state()}

        def run():
            s.doc = plan["_doc"]
            return {"hosts": [], "struct": set(), "origin": plan["_origin"], "anchor": None,
                    "log": {"planId": plan["planId"], "settingsHash": plan["settingsHash"], "summary": plan["summary"]}}
        out, after = _transact(s, run, "divisions", req={"planId": plan["planId"], "only": plan["only"], "skip": plan["skip"]}, check=_full_check)
        s.division["plan"] = None
        if after is None:
            return out
        s.division["applied"] = {"values": plan["values"], "settingsHash": plan["settingsHash"], "profileVersion": plan["profileVersion"],
                                 "rev": s.rev, "at": time.time(), "planId": plan["planId"], "summary": plan["summary"]}
        detail = works.add_detail(s.id, "divisions", plan["planId"], {**division_plan.view(plan), "appliedRev": s.rev})
        return {"applied": s.division["applied"], "detail": detail, "summary": plan["summary"], "unresolved": plan["unresolved"],
                "candidates": [{k: c[k] for k in ("key", "status", "statusMessage")} for c in plan["candidates"]], **s.state()}


@app.get("/api/docs/{doc_id}/divisions/read")
def divisions_read(doc_id: str):
    """문서에 적힌 구분 값(프로파일 read_values — 못 읽은 것은 키 없음). 문서는 그대로. 별도 동작(초기화에 묶지 않음, spec_구분_기준 ② §7)."""
    s = _sess(doc_id)
    with s.lock:
        blocks = s.doc.blocks()
        form = PROFILE.form_of(blocks)
        if not form:
            raise HTTPException(400, "양식 이름 문단이 없어 값을 읽을 수 없습니다")
        return {"form": form, "read": PROFILE.read_values(blocks, PROFILE.levels_of(blocks))}


# ---- 문서 표시 · 추가한 자리 · LLM 재검토(spec_구분_기준 ② §11) ----------------------------------------------------------

DIVISION_DEFAULT_VALUES = {"stages": [1], "orgs": {"lead": "", "joint": [], "nonprofit": [False]}}   # 값이 아직 없을 때 members 가 쓰는 기본값(묶음 찾기에만)


def _division_values(s):
    settings = s.division["settings"]
    return settings["values"] if settings else PROFILE.norm_values(DIVISION_DEFAULT_VALUES)


@app.get("/api/docs/{doc_id}/divisions/members")
def divisions_members(doc_id: str):
    """문서 표시 자료(② §11) — 계획 없이 find 만: 묶음마다 항목 안 문단 id 전부 + 추가한 자리(hint) 행. 문서는 그대로."""
    s = _sess(doc_id)
    with s.lock:
        blocks = s.doc.blocks()
        form = PROFILE.form_of(blocks)
        m = PROFILE.members(blocks, PROFILE.levels_of(blocks), _division_values(s), s.division.get("hints") or [])
        return {**m, "rev": s.rev, "form": form, "supported": PROFILE.supported(form)}


@app.post("/api/docs/{doc_id}/divisions/hints")
def divisions_hint_put(doc_id: str, body: dict = Body(...)):
    """추가한 자리 하나 넣기·고치기 {id?, para, dim, value?, note?}(② §11) — 같은 문단의 표시가 있으면 그것을 고친다. 계획은 버린다(후보가 달라짐)."""
    s = _sess(doc_id)
    with s.lock:
        hints = s.division.setdefault("hints", [])
        idx = division_llm.index(s.doc.blocks())
        old = next((h for h in hints if h.get("id") == body.get("id")), None) or next((h for h in hints if h.get("para") == body.get("para")), None)
        try:
            hint = division_model.norm_hint(body, idx, PROFILE, old)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if old is not None:
            hints[hints.index(old)] = hint
        else:
            hints.append(hint)
        s.division["plan"] = None
        out = {"hint": hint, "hints": list(hints), "rev": s.rev}
    works.log(s.id, "divisionHint", op="put", hint=hint)
    _persist_safe(s, force=True)
    return out


@app.delete("/api/docs/{doc_id}/divisions/hints/{hid}")
def divisions_hint_delete(doc_id: str, hid: str):
    s = _sess(doc_id)
    with s.lock:
        hints = s.division.setdefault("hints", [])
        h = next((x for x in hints if x.get("id") == hid), None)
        if h is None:
            raise HTTPException(404, "그 표시가 없습니다")
        hints.remove(h)
        s.division["plan"] = None
        out = {"removed": h, "hints": list(hints), "rev": s.rev}
    works.log(s.id, "divisionHint", op="delete", hint=h)
    _persist_safe(s, force=True)
    return out


@app.post("/api/docs/{doc_id}/divisions/llm_review")
def divisions_llm_review(doc_id: str, body: dict = Body(default={})):
    """LLM 재검토(② §11) — 추가한 자리·묶음·후보를 보내 hint 층을 고친다(동기, 수십 초). 자료는 잠금 안에서, 호출은 잠금 밖, 반영은 잠금 안(문서가 바뀌었으면 409)."""
    s = _sess(doc_id)
    with s.lock:
        hints = copy.deepcopy(s.division.get("hints") or [])
        if not hints:
            raise HTTPException(400, "먼저 문서에서 구분 기준 자리를 하나 이상 표시하세요(오른쪽 단추 → 「구분 기준 자리로 추가」)")
        blocks = s.doc.blocks()
        lv = PROFILE.levels_of(blocks)
        values = _division_values(s)
        groups = PROFILE.find(blocks, lv, values, hints=[h["para"] for h in hints])
        payload = division_llm.data(blocks, lv, values, hints, groups, PROFILE.value_text)
        rev = s.rev
    res = division_llm.ask(payload, effort=body.get("effort") or "medium")
    name = f"llm_{int(time.time())}"
    record = {"rev": rev, "payload": payload, "prompt": res["prompt"], "response": res["data"], "call": res["call"]}
    if not res["data"]:
        works.add_detail(s.id, "divisions", name, record)
        works.log(s.id, "divisionLlm", rev=rev, error=res["call"].get("error"), ms=res["call"].get("ms"))
        raise HTTPException(502, f"LLM 재검토에 답을 못 받았습니다: {res['call'].get('error') or '응답 없음'}")
    with s.lock:
        if s.rev != rev:
            raise HTTPException(409, "검토하는 동안 문서가 바뀌었습니다 — 다시 재검토하세요")
        idx = division_llm.index(s.doc.blocks())
        new_hints, applied, skipped = division_llm.apply_revisions(s.division.get("hints") or [], res["data"].get("revisions"), idx, PROFILE.hint_read)
        s.division["hints"] = new_hints
        if applied:
            s.division["plan"] = None
        out = {"hints": list(new_hints), "applied": applied, "skipped": skipped, "summary": res["data"].get("summary") or "", "call": res["call"], "rev": s.rev}
    out["detail"] = works.add_detail(s.id, "divisions", name, {**record, "applied": applied, "skipped": skipped})
    works.log(s.id, "divisionLlm", rev=rev, applied=len(applied), skipped=len(skipped), backend=res["call"].get("backend"), ms=res["call"].get("ms"),
              costUsd=res["call"].get("costUsd"))
    _persist_safe(s, force=True)
    return out


@app.post("/api/docs/{doc_id}/divisions/llm_missing")
def divisions_llm_missing(doc_id: str, body: dict = Body(default={})):
    """빠진 자리 검토(spec_구분_기준 ② §13) — 어느 묶음에도 안 든 표·문단 요약을 LLM 에 보내 「구분 기준 자리로 보이는데 빠진 곳」 후보를 받는다(동기, 수십 초).
    판정만 — 문서·묶음·추가한 자리·계획·rev 는 그대로. 자료는 잠금 안에서, 호출은 잠금 밖. 보낼 것이 없으면 호출 없이 빈 결과, 답이 없으면 502(기록은 남김)."""
    s = _sess(doc_id)
    with s.lock:
        blocks = s.doc.blocks()
        lv = PROFILE.levels_of(blocks)
        values = _division_values(s)
        groups = PROFILE.find(blocks, lv, values, hints=[h["para"] for h in s.division.get("hints") or [] if h.get("para")])
        payload = division_llm.missing_data(blocks, lv, values, groups, PROFILE.value_text)
        rev = s.rev
    sent = {"tables": len(payload["tables"]), "paragraphs": len(payload["paragraphs"])}
    if not payload["tables"] and not payload["paragraphs"]:
        return {"missing": [], "skipped": [], "summary": "묶음 밖에 구분 낱말이 든 표·문단이 없습니다", "sent": sent, "call": None, "detail": None, "rev": rev}
    res = division_llm.ask_missing(payload, effort=body.get("effort") or "medium")
    name = f"missing_{int(time.time())}"
    record = {"rev": rev, "payload": payload, "prompt": res["prompt"], "response": res["data"], "call": res["call"]}
    if not res["data"]:
        works.add_detail(s.id, "divisions", name, record)
        works.log(s.id, "divisionMissing", rev=rev, error=res["call"].get("error"), ms=res["call"].get("ms"), **sent)
        raise HTTPException(502, f"빠진 자리 검토에 답을 못 받았습니다: {res['call'].get('error') or '응답 없음'}")
    items, skipped = division_llm.check_missing(res["data"], payload)
    detail = works.add_detail(s.id, "divisions", name, {**record, "missing": items, "skipped": skipped})
    works.log(s.id, "divisionMissing", rev=rev, found=len(items), skipped=len(skipped), backend=res["call"].get("backend"), ms=res["call"].get("ms"),
              costUsd=res["call"].get("costUsd"), **sent)
    return {"missing": items, "skipped": skipped, "summary": res["data"].get("summary") or "", "sent": sent, "call": res["call"], "detail": detail, "rev": rev}


@app.get("/api/divisions/presets")
def division_presets_list():
    return {"presets": division_presets.listing()}


@app.put("/api/divisions/presets/{pid}")
def division_presets_put(pid: str, body: dict = Body(...)):
    """{name, values, profileId?} — pid "new" 면 새로. 틀리면 400, 같은 이름 409, 없는 id 404."""
    try:
        return division_presets.put(pid, body.get("name"), body.get("values"), body.get("profileId") or PROFILE.ID)
    except division_presets.Conflict as e:
        raise HTTPException(409, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"없는 항목: {e}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except OSError as e:
        raise HTTPException(503, f"저장하지 못했습니다: {e}") from e


@app.delete("/api/divisions/presets/{pid}")
def division_presets_delete(pid: str):
    try:
        return {"deleted": division_presets.delete(pid)}
    except KeyError as e:
        raise HTTPException(404, f"없는 항목: {e}") from e
    except OSError as e:
        raise HTTPException(503, f"저장하지 못했습니다: {e}") from e
