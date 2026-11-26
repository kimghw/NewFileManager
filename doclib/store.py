"""문서 라이브러리의 저장소(spec_양식작성 ② §2) — 파일 시스템뿐(DB 없음). 문서를 바꾸지 않는다(올린 그대로 보관).

    <root>/docs/<문서 id>/meta.json     {id, name, ext, sha256, bytes, pages, at, org, topic, note}
                          source.<ext>  올린 파일 그대로
                          source.pdf    읽을 PDF(pdf 는 올린 것 · hwp · hwpx · docx · ppt · pptx 는 한글 · Word · PowerPoint 로 찍은 것)
                          extracts/<추출 id>/meta.json  {id, doc, focus, span, state, at, done, …, group?, part?[차례, 수](함께 뽑은 범위)} — extract.py 가 쓴다
                                               doc.md · images/*.png · chunks/<n>.json
    <root>/prompts/<이름>.md             사람이 고친 스킬 글(없으면 doclib/prompts/ 의 기본본)

root = env NFM_DOCLIB | %LOCALAPPDATA%\\NewFileManager\\doclib. 문서 id = 「d」 + sha256 앞 12자(같은 파일을 다시 올리면 같은 문서) · 추출 id = 「x」 + 16진 10자."""
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

EXTS = ("pdf", "hwpx", "hwp", "docx", "pptx", "ppt")   # ppt · pptx = 2026-11-26 사용자 "ppt 도 참조 문서로 넣을 수 있도록" — PowerPoint 로 PDF 를 찍어 읽는다
MAX_BYTES = 80 * 2 ** 20
_DOC = re.compile(r"^d[0-9a-f]{12}$")
_EXT = re.compile(r"^x[0-9a-f]{10}$")
_LOCK = threading.RLock()
FIELDS = ("org", "topic", "note")      # 사람이 문서에 적어 두는 것(어느 기관 · 어느 연구의 문서인가 · 메모)
FIELD_MAX = 300


def root():
    env = os.environ.get("NFM_DOCLIB")
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "doclib"


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    # Windows: 화면의 조회(_read — 잠금 없이 읽는다)가 그 파일을 연 순간에는 바꿔 쓰기가 거절된다(WinError 5).
    # 잠깐 기다려 다시 한다 — 2026-11-24 254쪽 추출이 「준비하는 중」 에서 이것으로 죽었다.
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def doc_dir(did):
    if not isinstance(did, str) or not _DOC.fullmatch(did):
        return None
    p = root() / "docs" / did
    return p if (p / "meta.json").is_file() else None


def ext_dir(eid):
    """추출 id → 그 폴더 | None(문서들을 훑는다 — 추출은 제 문서 폴더 아래에 있다)."""
    if not isinstance(eid, str) or not _EXT.fullmatch(eid):
        return None
    base = root() / "docs"
    if not base.is_dir():
        return None
    for d in base.iterdir():
        p = d / "extracts" / eid
        if (p / "meta.json").is_file():
            return p
    return None


def doc(did):
    p = doc_dir(did)
    return _read(p / "meta.json") if p else None


def extract(eid):
    p = ext_dir(eid)
    return _read(p / "meta.json") if p else None


def extracts_of(did):
    p = doc_dir(did)
    out = []
    if p and (p / "extracts").is_dir():
        for e in (p / "extracts").iterdir():
            m = _read(e / "meta.json")
            if isinstance(m, dict):
                out.append(m)
    return sorted(out, key=lambda m: m.get("at") or 0, reverse=True)


def docs():
    """문서 목록(새것부터) — 문서마다 extracts(그 문서의 추출 요약)."""
    base = root() / "docs"
    out = []
    if base.is_dir():
        for d in base.iterdir():
            m = _read(d / "meta.json")
            if isinstance(m, dict) and m.get("id") == d.name:
                out.append({**m, "extracts": [brief(e) for e in extracts_of(d.name)]})
    return sorted(out, key=lambda m: m.get("at") or 0, reverse=True)


def brief(e):
    """추출 하나의 목록용 요약."""
    return {k: e.get(k) for k in ("id", "doc", "focus", "span", "state", "at", "ended", "pages", "chars", "figures", "formulas", "open", "error", "progress", "model", "costUsd",
                                  "group", "part")}   # group · part [차례, 수] = 함께 뽑은 범위(문서를 한 번 읽어 범위마다 MD 하나 — extract.start)


def clean_name(name):
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", (name or "").strip())[:160]
    return name or "문서"


def add_doc(name, data):
    """올린 파일을 보관 → (meta, 새로 만들었나). 형식 · 크기가 안 맞으면 ValueError. 같은 바이트는 같은 문서(다시 만들지 않는다)."""
    name = clean_name(name)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in EXTS:
        raise ValueError(f"받는 형식은 {' · '.join(EXTS)} 입니다")
    if not data:
        raise ValueError("빈 파일입니다")
    if len(data) > MAX_BYTES:
        raise ValueError(f"파일은 {MAX_BYTES // 2 ** 20} MB 까지입니다")
    sha = hashlib.sha256(data).hexdigest()
    did = "d" + sha[:12]
    with _LOCK:
        have = doc(did)
        if have is not None:
            return have, False
        p = root() / "docs" / did
        p.mkdir(parents=True, exist_ok=True)
        (p / f"source.{ext}").write_bytes(data)   # pdf 는 이것이 곧 읽을 PDF(source.pdf)
        meta = {"id": did, "name": name, "ext": ext, "sha256": sha, "bytes": len(data), "pages": None, "at": round(time.time(), 3), "org": "", "topic": "", "note": ""}
        _write(p / "meta.json", meta)
        return meta, True


def patch_doc(did, patch):
    """사람이 적는 것(org · topic · note)과 서버가 채우는 것(pages · pdfError)을 고친다 → meta | None."""
    with _LOCK:
        p = doc_dir(did)
        m = _read(p / "meta.json") if p else None
        if not isinstance(m, dict):
            return None
        for k, v in (patch or {}).items():
            if k in FIELDS and isinstance(v, str):
                m[k] = " ".join(v.split())[:FIELD_MAX]
            elif k in ("pages", "pdfError"):
                m[k] = v
        _write(p / "meta.json", m)
        return m


def source(did):
    """(올린 파일 경로, 읽을 PDF 경로 | None)."""
    p, m = doc_dir(did), doc(did)
    if not p or not m:
        return None, None
    pdf = p / "source.pdf"
    return p / f"source.{m['ext']}", pdf if pdf.is_file() else None


def drop_doc(did):
    with _LOCK:
        p = doc_dir(did)
        if not p:
            return False
        shutil.rmtree(p, ignore_errors=True)
        return True


def new_extract(did, focus, span, more=None):
    """추출 기록을 만든다 → meta(state 「queued」)."""
    p = doc_dir(did)
    if not p:
        return None
    eid = "x" + uuid.uuid4().hex[:10]
    meta = {"id": eid, "doc": did, "focus": focus, "span": list(span) if span else None, "state": "queued", "at": round(time.time(), 3), "ended": None, "progress": {"done": 0, "total": 0, "text": "기다리는 중"},
            "pages": 0, "chars": 0, "figures": 0, "formulas": 0, "open": 0, "error": None, "model": None, "costUsd": None, **(more or {})}
    with _LOCK:
        _write(p / "extracts" / eid / "meta.json", meta)
    return meta


def save_extract(meta):
    with _LOCK:
        p = ext_dir(meta["id"])
        if p:
            _write(p / "meta.json", meta)


def drop_extract(eid):
    with _LOCK:
        p = ext_dir(eid)
        if not p:
            return False
        shutil.rmtree(p, ignore_errors=True)
        return True


def cut_running():
    """서버를 켤 때 — 돌던 추출은 「끊김」 으로(저절로 잇지 않는다)."""
    n = 0
    for d in docs():
        for e in extracts_of(d["id"]):
            if e.get("state") in ("queued", "running"):
                e.update(state="cut", ended=round(time.time(), 3), error="서버가 꺼져 끊겼습니다 — 다시 추출하세요")
                save_extract(e)
                n += 1
    return n


def cut_orphans(alive):
    """「추출 중」 인데 돌던 스레드가 없는 추출 → 「끊김」(상태를 못 적고 죽은 것 — 영영 「추출 중」 으로 남지 않게). alive(추출 id) → 스레드가 도나."""
    n = 0
    for d in docs():
        for e in extracts_of(d["id"]):
            if e.get("state") == "running" and not alive(e["id"]):
                e.update(state="cut", ended=round(time.time(), 3), error=e.get("error") or "추출이 도중에 멈췄습니다 — 다시 추출하세요")
                try:
                    save_extract(e)
                    n += 1
                except OSError:
                    pass
    return n


DEFAULT_PROMPTS = Path(__file__).with_name("prompts")
PROMPTS = (("extract", "자료 추출 — 쪽 묶음을 읽어 MD 로"), ("verify", "그림 확인 — 잘라 낸 그림의 모서리"), ("formula", "수식 — 캡처를 LaTeX 로"))
PROMPT_MAX = 20000


def prompt(name):
    """스킬 글 {name, title, text, custom(내 사본인가), default(기본본 글)} | None."""
    title = dict(PROMPTS).get(name)
    if title is None:
        return None
    base = (DEFAULT_PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    mine = root() / "prompts" / f"{name}.md"
    try:
        text = mine.read_text(encoding="utf-8") if mine.is_file() else None
    except OSError:
        text = None
    return {"name": name, "title": title, "text": text if text is not None else base, "custom": text is not None, "default": base}


def put_prompt(name, text):
    """스킬 글을 고친다(빈 글 · 기본본과 같은 글 = 기본본으로 되돌림) → prompt(name) | None. 너무 길면 ValueError."""
    if dict(PROMPTS).get(name) is None:
        return None
    if not isinstance(text, str) or len(text) > PROMPT_MAX:
        raise ValueError(f"스킬 글은 {PROMPT_MAX:,}자까지입니다")
    mine = root() / "prompts" / f"{name}.md"
    base = (DEFAULT_PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    with _LOCK:
        if not text.strip() or text.strip() == base.strip():
            mine.unlink(missing_ok=True)
        else:
            mine.parent.mkdir(parents=True, exist_ok=True)
            mine.write_text(text, encoding="utf-8")
    return prompt(name)
