"""엑셀(xlsx) 시트 편집의 끝점(spec_엑셀편집 ② §1 · §2 · §6) — server.py 가 include 하고 `_open` · `get_doc` 이 xlsx 를 여기로 넘긴다.

`app.server` 를 가져오지 않는다: 작업 폴더는 `works` 로만(계정마다 따로 — works.folder) · 문서는 `xlsx_doc.XlsxDoc`.
작업 폴더 = original.xlsx(올린 원본) · current.xlsx(지금 — 편집마다 바꿔 씀) · work.json(format "xlsx") · log.jsonl. 실행 취소는 메모리에만."""
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response

from app import works
from app import xlsx_doc as X

router = APIRouter()
STATIC = Path(__file__).with_name("static") / "sheet"
VERSIONED = ("sheet.css", "sheet.js")
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_MB = int(os.environ.get("NFM_MAX_UPLOAD_MB", "2048"))
UNDO_MAX = 50
MAX_BOOKS = 8


class Book:
    def __init__(self, wid, name, data):
        self.id, self.name = wid, name
        self.doc = X.XlsxDoc(data)
        self.rev, self.undo, self.edits = 0, [], 0
        self.lock = threading.Lock()
        self.touched = time.time()
        self.memory = None   # 작업 저장이 꺼졌을 때(시험) 지금 바이트


BOOKS: dict[str, Book] = {}
_guard = threading.Lock()


def is_xlsx(name: str) -> bool:
    return (name or "").lower().endswith(".xlsx")


def refuse_other(name: str):
    """엑셀의 다른 형식(옛 xls · 매크로 xlsm …)은 까닭을 붙여 거절한다."""
    low = (name or "").lower()
    if low.endswith((".xls", ".xlsm", ".xlsb", ".xltx", ".xltm")):
        raise HTTPException(400, "엑셀은 .xlsx 만 열 수 있습니다 — 엑셀에서 「Excel 통합 문서(.xlsx)」 로 저장해 올려 주세요")


def open_url(wid: str) -> str:
    return f"/sheet#w={wid}"


def work_of(wid: str):
    """이 계정의 xlsx 작업이면 work.json — 아니면 None."""
    w = works.work(wid) if works.enabled() else None
    return w if w and w.get("format") == "xlsx" else None


def open_upload(name: str, data: bytes, new=False, source="upload") -> dict:
    """올린 xlsx → 작업(같은 파일 작업이 있으면 그것을 이어 엶 — 묻지 않음: ② §1)."""
    if len(data) > MAX_MB * 2 ** 20:
        raise HTTPException(413, f"{MAX_MB} MB 보다 큰 파일은 열 수 없습니다")
    if not new and works.enabled():
        rows = works.same_works(name, "xlsx", works.sha256(data))
        for w in rows:
            if _book(w["id"], soft=True) is not None:
                works.log(w["id"], "reupload", source=source)
                works.update(w["id"])
                return {"docId": w["id"], "name": name, "size": len(data), "reused": True, "format": "xlsx", "open": open_url(w["id"])}
    try:
        b = Book(uuid.uuid4().hex[:12], name, data)
    except X.SheetError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001 — 깨진 xlsx
        raise HTTPException(400, f"xlsx 로 열 수 없습니다: {e}") from e
    works.create(b.id, name, "xlsx", data, source)
    if not works.enabled():
        b.memory = data
    _admit(b)
    return {"docId": b.id, "name": name, "size": len(data), "reused": False, "format": "xlsx", "open": open_url(b.id)}


def _admit(b):
    with _guard:
        while len(BOOKS) >= MAX_BOOKS:   # 모두 편집마다 작업 폴더에 쓰므로 비워도 잃지 않는다(실행 취소만 사라짐)
            old = min(BOOKS.values(), key=lambda x: x.touched)
            if old.memory is not None:   # 저장이 꺼진 때는 비우지 않는다
                break
            BOOKS.pop(old.id, None)
        BOOKS[b.id] = b


def _book(wid: str, soft=False) -> Book | None:
    mine = works.ACCOUNT.get() is None or bool((d := works.folder(wid)) and d.is_dir())   # 남의 작업 = 없는 작업(spec_계정 ② §3)
    b = BOOKS.get(wid) if mine else None
    if b is None and mine:
        w = work_of(wid)
        d = works.folder(wid)
        if w is not None and d is not None:
            src = d / "current.xlsx" if (d / "current.xlsx").is_file() else d / "original.xlsx"
            try:
                b = Book(wid, w.get("name") or "sheet.xlsx", src.read_bytes())
                b.rev = int(w.get("rev") or 0)
                b.edits = int(w.get("edited") or 0)
                b.doc.edited = b.edits > 0   # 고친 적이 있는 작업 — 수식 칸은 「다시 계산 전」 으로 보인다
            except Exception:  # noqa: BLE001 — 못 읽는 작업
                b = None
            if b is not None:
                _admit(b)
    if b is None:
        if soft:
            return None
        raise HTTPException(404, "서버에 이 엑셀 작업이 없습니다 — 지운 작업이거나 다른 계정의 작업입니다. 파일을 다시 열어 주세요")
    b.touched = time.time()
    return b


def _save(b: Book, kind: str, **fields):
    """편집 한 번 뒤 — 차례를 올리고 지금 바이트를 작업 폴더에(잠금 안)."""
    b.rev += 1
    b.edits += 1
    data = b.doc.save()
    d = works.folder(b.id) if works.enabled() else None
    if d is None:
        b.memory = data
    else:
        works._write(d / "current.xlsx", data)   # 다 쓴 사본을 바꿔 넣는다(작업 저장과 같은 길)
        works.update(b.id, rev=b.rev, edited=b.edits, size=len(data))
        works.log(b.id, kind, rev=b.rev, **fields)
    return data


def _push_undo(b: Book):
    b.undo.append(b.doc.save())
    del b.undo[:-UNDO_MAX]


def _sheet_no(b: Book, i) -> int:
    try:
        i = int(i or 0)
    except (TypeError, ValueError):
        i = 0
    if not (0 <= i < len(b.doc.sheets)):
        raise HTTPException(400, "그런 시트가 없습니다")
    return i


def _rev_ok(b: Book, body: dict):
    rev = body.get("rev")
    if rev is not None and int(rev) != b.rev:
        raise HTTPException(409, "다른 화면에서 이 시트를 고쳤습니다 — 다시 읽습니다")


def _meta(b: Book, i: int) -> dict:
    return {"docId": b.id, "name": b.name, "rev": b.rev, "undo": len(b.undo), "edited": b.doc.edited or b.edits > 0,
            "sheets": [{"name": s["name"], "hidden": s["hidden"]} for s in b.doc.sheets], "sheet": b.doc.view(i)}


# ---- 끝점 --------------------------------------------------------------------------------------------------------

@router.get("/sheet")
def sheet_page():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for name in VERSIONED:
        html = html.replace(f'"/static/sheet/{name}"', f'"/static/sheet/{name}?v={int((STATIC / name).stat().st_mtime)}"')
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@router.post("/api/sheets")
async def upload(file: UploadFile = File(...), new: bool = False):
    name, data = file.filename or "sheet.xlsx", await file.read()
    refuse_other(name)
    if not is_xlsx(name):
        raise HTTPException(400, ".xlsx 파일만 열 수 있습니다")
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(open_upload, name, data, new)


@router.get("/api/sheets/{wid}")
def get_book(wid: str, sheet: int = 0):
    b = _book(wid)
    with b.lock:
        return _meta(b, _sheet_no(b, sheet))


@router.put("/api/sheets/{wid}/cells")
def put_cells(wid: str, body: dict = Body(...)):
    """{sheet, rev, cells[{r, c, text}]} → {rev, undo, cells[…]} — 칸 글 · 붙여 넣기 · 비우기(② §3)."""
    b = _book(wid)
    cells = body.get("cells") or []
    if not isinstance(cells, list) or not cells or len(cells) > 100000:
        raise HTTPException(400, "고칠 칸이 없습니다")
    try:
        items = [(int(x["r"]), int(x["c"]), str(x.get("text") or "")) for x in cells]
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(400, "칸의 꼴이 맞지 않습니다") from e
    with b.lock:
        i = _sheet_no(b, body.get("sheet"))
        _rev_ok(b, body)
        before = b.doc.save()
        try:
            got = b.doc.set_cells(i, items)
        except X.SheetError as e:
            b.doc = X.XlsxDoc(before)   # 반쯤 고친 것을 남기지 않는다
            raise HTTPException(400, str(e)) from e
        b.undo.append(before)
        del b.undo[:-UNDO_MAX]
        _save(b, "sheetCells", sheet=i, n=len(items), at=X.cell_ref(items[0][0], items[0][1]))
        return {"rev": b.rev, "undo": len(b.undo), "cells": got}


@router.post("/api/sheets/{wid}/rows")
def rows(wid: str, body: dict = Body(...)):
    """{sheet, rev, op: insert | delete, at, n | r0, r1} → 시트 보기 전체(② §3 「행 넣기 · 지우기」)."""
    b = _book(wid)
    op = body.get("op")
    with b.lock:
        i = _sheet_no(b, body.get("sheet"))
        _rev_ok(b, body)
        before = b.doc.save()
        try:
            if op == "insert":
                at, n = int(body.get("at") or 0), int(body.get("n") or 1)
                b.doc.insert_rows(i, at, n)
                fields = {"op": op, "at": at, "n": n}
            elif op == "delete":
                r0, r1 = int(body.get("r0") or 0), int(body.get("r1") or body.get("r0") or 0)
                b.doc.delete_rows(i, r0, r1)
                fields = {"op": op, "r0": r0, "r1": r1}
            else:
                raise HTTPException(400, "op 는 insert · delete 입니다")
        except X.SheetError as e:
            b.doc = X.XlsxDoc(before)
            raise HTTPException(400, str(e)) from e
        except (TypeError, ValueError) as e:
            b.doc = X.XlsxDoc(before)
            raise HTTPException(400, "행의 자리가 맞지 않습니다") from e
        b.undo.append(before)
        del b.undo[:-UNDO_MAX]
        _save(b, "sheetRows", sheet=i, **fields)
        return _meta(b, i)


@router.post("/api/sheets/{wid}/undo")
def undo(wid: str, body: dict = Body(default={})):
    b = _book(wid)
    with b.lock:
        if not b.undo:
            raise HTTPException(409, "되돌릴 편집이 없습니다")
        b.doc = X.XlsxDoc(b.undo.pop())
        b.doc.edited = True   # 되돌린 뒤에도 원본과 다를 수 있다 — 저장은 늘 계산 차례를 빼고 다시 계산을 건다
        try:
            i = _sheet_no(b, body.get("sheet"))
        except HTTPException:
            i = 0
        _save(b, "sheetUndo", sheet=i)
        return _meta(b, i)


@router.get("/api/sheets/{wid}/download")
def download(wid: str):
    b = _book(wid)
    with b.lock:
        data = b.doc.save() if b.doc.edited else (b.memory or _current_bytes(b))
    return Response(data, media_type=MIME, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(b.name)}"})


def _current_bytes(b: Book) -> bytes:
    d = works.folder(b.id)
    if d is not None:
        for n in ("current.xlsx", "original.xlsx"):
            if (d / n).is_file():
                return (d / n).read_bytes()
    return b.doc.save()
