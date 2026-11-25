"""양식 작성 04에서 참고할 샘플과 추가 서식. 작성 근거 자료와 별도로 작업마다 보관한다."""
import io
import json
import re
import threading
import time
from pathlib import Path
from zipfile import ZipFile

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from app import doc_agent, pic_tools, works

router = APIRouter()
FORMATS = {"hwp", "hwpx", "docx", "pdf", "txt", "md", "png", "jpg", "jpeg", "webp"}
FILES_MAX, TEXT_MAX, IMAGES_MAX, PDF_PAGES = 8, 60000, 3, 80
_ID = re.compile(r"f[0-9a-f]{64}")
_MEM = {}
_LOCK = threading.RLock()


def _folder(wid):
    d = works.folder(wid)
    return d / "form_examples" if d is not None and (d / "work.json").is_file() else None


def _entries(wid):
    folder = _folder(wid)
    if folder is None:
        return {fid: io.BytesIO(blob) for fid, blob in _MEM.get(wid, {}).items()}
    return {p.stem: p for p in folder.glob("*.zip") if _ID.fullmatch(p.stem)}


def _read(wid, full):
    # 한 첨부의 이름·발췌·그림을 한 파일로 교체한다. 목록만 읽을 때는 본문과 그림을 열지 않는다.
    records = []
    with _LOCK:
        for source in _entries(wid).values():
            with ZipFile(source) as archive:
                meta = json.loads(archive.read("file.json"))
                if full:
                    meta["text"] = archive.read("text.txt").decode("utf-8")
                    meta["images"] = [{**im, "data": archive.read(f"image-{i}")} for i, im in enumerate(meta["imageInfo"])]
                records.append(meta)
    return sorted(records, key=lambda r: (r["at"], r["id"]))


def listing(wid):
    return _read(wid, False)


def evidence(wid):
    """04 호출의 입력 스냅샷. images[].label은 파일 안의 쪽 또는 그림 위치다."""
    return _read(wid, True)


def _sample(seq, n):
    if len(seq) <= n:
        return list(seq)
    return [seq[round(i * (len(seq) - 1) / (n - 1))] for i in range(n)]


def _shorten(text):
    if len(text) <= TEXT_MAX:
        return text, False
    # 긴 양식은 끝 부록과 중간의 예시도 보낸다. 빠진 범위는 본문에 표시한다.
    gap = "\n[… 중간 생략 …]\n"
    part = (TEXT_MAX - len(gap) * 2) // 3
    middle = (len(text) - part) // 2
    return gap.join((text[:part], text[middle:middle + part], text[-part:])), True


def _raster(blob, label):
    with Image.open(io.BytesIO(blob)) as im:
        if im.width * im.height > pic_tools.MAX_PIXELS:
            raise ValueError("그림의 화소 수가 너무 큽니다")
    return {**pic_tools.for_llm(blob), "label": label}


def _document(doc):
    styles, pictures = {}, {}
    lines = []

    def style_tag(fmt, structure=()):
        attrs = [f"{k}={fmt[k]}" for k in ("font", "sizePt", "align", "bold", "italic", "underline",
                                            "color", "lineSpacingPct", "indentLeftMm", "firstLineMm") if fmt.get(k)]
        desc = ", ".join([*attrs, *structure])
        return f"[서식{styles.setdefault(desc, len(styles) + 1)}]" if desc else ""

    def visit(blocks):
        for b in blocks:
            if b["type"] == "paragraph":
                fmt = b.get("format") or {}
                structure = []
                if b.get("outlineLevel"):
                    structure.append(f"제목 수준 {b['outlineLevel']}")
                if b.get("list"):
                    structure.append(f"목록 {b['list'].get('label') or b['list'].get('kind') or ''}, 수준 {b['list'].get('level') or 1}")
                tag = style_tag(fmt, structure)
                text = b.get("text") or "(빈 문단)"
                if b.get("runs"):
                    text = "".join(style_tag({**fmt, **r["format"]}) + r["text"] for r in b["runs"])
                lines.append(f"{tag} {text}")
            elif b["type"] == "table":
                lines.append(f"[표 {b['id']} · {b.get('nRows')}행 × {b.get('nCols')}열]")
                for c in b.get("cells") or ():
                    span = (c.get("rowSpan", 1), c.get("colSpan", 1))
                    merged = f" · {span[0]}행 × {span[1]}열 병합" if span != (1, 1) else ""
                    lines.append(f"[{c['row'] + 1}행 {c['col'] + 1}열{merged}]")
                    visit(c.get("blocks") or ())
                lines.append("[표 끝]")
            elif b["type"] == "image":
                label = f"그림 {b['id']}"
                lines.append(f"[{label}]")
                pictures.setdefault(b.get("media"), label)

    visit(doc.blocks())
    legend = [f"[서식{i}] {desc}" for desc, i in styles.items() if desc]
    readable = [(media, label) for media, label in pictures.items() if pic_tools.is_raster(media)]
    images = []
    for media, label in _sample(readable, IMAGES_MAX):
        try:
            images.append(_raster(doc.media(media), label))
        except (ValueError, OSError, KeyError, Image.DecompressionBombError):
            continue
    if len(images) < len(pictures):
        legend.append(f"[원본 그림 {len(pictures)}개 중 {len(images)}개를 첨부]")
    return "\n".join([*legend, *lines]), images, len(images) < len(pictures)


def _pdf(blob):
    import fitz
    with fitz.open(stream=blob, filetype="pdf") as doc:
        if doc.needs_pass or not len(doc):
            raise ValueError("PDF를 읽을 수 없습니다(암호 또는 빈 파일)")
        pages = _sample(range(len(doc)), PDF_PAGES)
        lines, images, examples = [], [], []
        for n in pages:
            p = doc[n]
            text = p.get_text("text", sort=True)
            lines.append(f"[{n + 1}쪽]\n{text}")
            if re.search(r"작성\s*예|예시|샘플|sample|example", text[:400], re.I):
                examples.append(n)
        visuals = list(dict.fromkeys([*_sample(examples, IMAGES_MAX), *_sample(pages, IMAGES_MAX)]))[:IMAGES_MAX]
        for n in sorted(visuals):
            p = doc[n]
            scale = min(2, 1600 / max(1, p.rect.width, p.rect.height))
            pix = p.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
            images.append({"data": pix.tobytes("jpeg", jpg_quality=88), "media": "image/jpeg", "label": f"{n + 1}쪽", "w": pix.width, "h": pix.height})
        lines.insert(0, f"[원본 {len(doc)}쪽 중 본문 {len(pages)}쪽 · 쪽 이미지 {len(images)}개 첨부]")
        return "\n".join(lines), images, len(visuals) < len(doc)


def _extract(name, blob, kind):
    if kind == "hwp":
        from app import server
        _, blob = server._from_hwp(name, blob)
        kind = "hwpx"
    if kind in ("hwpx", "docx"):
        from app.docx_doc import DocxDoc
        from app.hwpx_doc import HwpxDoc
        return _document((HwpxDoc if kind == "hwpx" else DocxDoc)(blob))
    if kind == "pdf":
        return _pdf(blob)
    if kind in ("txt", "md"):
        text = doc_agent._decode(blob).replace("\x00", "").strip()
        if not text:
            raise ValueError("글이 없는 파일입니다")
        return text, [], False
    return "[그림 1]", [_raster(blob, "그림 1")], False


def _store(session, name, kind, fid, text, images, cut):
    from app import server
    wid = session.id
    meta = {"id": fid, "name": name, "kind": kind, "sha256": fid[1:], "chars": len(text), "cut": cut,
            "imageCount": len(images), "imageInfo": [{k: v for k, v in im.items() if k != "data"} for im in images],
            "at": time.time()}
    out = io.BytesIO()
    with ZipFile(out, "w") as archive:
        archive.writestr("file.json", json.dumps(meta, ensure_ascii=False).encode())
        archive.writestr("text.txt", text.encode())
        for i, im in enumerate(images):
            archive.writestr(f"image-{i}", im["data"])
    # 변환하는 동안 작업이 초기화·삭제되면 옛 입력을 새 작업에 쓰지 않는다.
    with server._reopen_lock, works._lock(wid), _LOCK:
        if server.DOCS.get(wid) is not session:
            raise HTTPException(409, "첨부를 읽는 동안 작업이 변경되었습니다. 작업을 확인한 뒤 다시 첨부하세요")
        entries = _entries(wid)
        if fid in entries:
            return
        if len(entries) >= FILES_MAX:
            raise HTTPException(400, f"샘플·추가 서식은 {FILES_MAX}개까지 첨부할 수 있습니다")
        folder = _folder(wid)
        if folder is None:
            _MEM.setdefault(wid, {})[fid] = out.getvalue()
        else:
            works._write(folder / f"{fid}.zip", out.getvalue())


def _session(doc_id):
    from app import server
    return server._sess(doc_id)


@router.get("/api/docs/{doc_id}/form-examples")
def get_examples(doc_id: str):
    return {"files": listing(_session(doc_id).id)}


@router.post("/api/docs/{doc_id}/form-examples")
def add_example(doc_id: str, file: UploadFile = File(...)):
    session = _session(doc_id)
    wid = session.id
    filename = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(filename).suffix
    kind = suffix.lower().lstrip(".")
    if kind not in FORMATS:
        raise HTTPException(400, "첨부 가능한 형식은 " + " · ".join(sorted(FORMATS)) + "입니다")
    name = doc_agent._name(Path(filename).stem, "샘플")[:120 - len(suffix)] + suffix
    blob = file.file.read(doc_agent.MATERIAL_BYTES + 1)
    if not blob or len(blob) > doc_agent.MATERIAL_BYTES:
        raise HTTPException(413 if blob else 400, f"빈 파일이거나 파일 한도({doc_agent.MATERIAL_BYTES // 2**20} MB)를 넘습니다")
    fid = "f" + works.sha256(blob)
    files = listing(wid)
    if any(f["id"] == fid for f in files):
        return {"files": files}
    if len(files) >= FILES_MAX:
        raise HTTPException(400, f"샘플·추가 서식은 {FILES_MAX}개까지 첨부할 수 있습니다")
    try:
        text, images, cut = _extract(name, blob, kind)
        text, trimmed = _shorten(text)
    except HTTPException:
        raise
    except Exception as e:  # 파일 파서마다 오류형이 다르다. 실패한 첨부는 저장하지 않는다.
        raise HTTPException(400, f"샘플·추가 서식을 읽지 못했습니다. {str(e)[:240]}") from e
    _store(session, name, kind, fid, text, images, cut or trimmed)
    return {"files": listing(wid)}


@router.delete("/api/docs/{doc_id}/form-examples/{fid}")
def remove_example(doc_id: str, fid: str):
    wid = _session(doc_id).id
    with _LOCK:
        source = _entries(wid).get(fid)
        if source is None:
            raise HTTPException(404, "이 작업에 해당 첨부가 없습니다")
        if isinstance(source, Path):
            source.unlink()
        else:
            _MEM[wid].pop(fid)
        return {"files": listing(wid)}
