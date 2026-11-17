"""HWPX 웹 편집 서버(spec_hwpx_웹편집 ② §6). 문서는 메모리(최근 8개)에 두고, 올린 파일마다 작업 폴더에 원본·편집 상태·검증·기록을
저장한다(spec_작업 — 서버를 다시 켜도 작업 목록에서 이어서).

실행: python -m uvicorn app.server:app --host 127.0.0.1 --port 8114"""
import atexit
import concurrent.futures
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
                 outline_edit, outline_match, outline_pos, owpml_check, pdf_map, pdf_render, projects, restore, verify, works)
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
    def __init__(self, name, data, sid=None, ids=None, base=0):
        self.id, self.name, self.original = sid or uuid.uuid4().hex[:12], name, data
        self.fmt = fmt_of(name)
        self.kit = FORMATS[self.fmt]
        self.doc = self.kit["cls"](data)
        # 기준(spec_작업 ② §8): original = 고친 문단을 견주는 바이트 — 처음엔 올린 원본(base_n 0), 확정하면 마지막 확정본(+ 그때의 블록 id 자리표 base_ids).
        # gen = 기준이 바뀐 횟수(검증 스레드가 옛 기준의 결과를 세션에 쓰지 않게 — glock), doc_key = 올린 원본의 sha256(확정해도 같은 문서 — _open·_reopen 이 채움)
        if ids is not None and not self.doc.adopt_ids(ids):
            raise RuntimeError("기준 확정의 블록 id 자리표가 문서와 맞지 않습니다")
        self.base_n, self.base_ids, self.gen, self.glock, self.doc_key = base, ids, 0, threading.Lock(), None
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
        self.owpml_ok = set()  # 다른 문서에서 가져온 내용이 물고 온 스키마 위반 종류(owpml_allow — 기준선에 더해 두고 작업에 저장: 다시 열어도 그 종류로 422 가 나지 않게)
        # 작업 저장(spec_작업 ② §3): 편집 차례·작업 폴더에 쓴 차례·만든 때, 저장 한 번에 하나(plock)
        self.rev, self.saved_rev, self.created, self.plock = 0, 0, time.time(), threading.Lock()
        self.persist_error = None  # 마지막 작업 저장 실패(있으면 화면 상단이 실패를 보임)
        # 구분 기준(spec_구분_기준 ② §4·§7): 입력 중 설정 · 마지막 적용(값·rev·planId·요약 — 문서와 함께 저장·실행 취소로 복원) · 마지막 계획(사본 문서 포함, 메모리만 하나)
        self.division = {"settings": None, "applied": None, "plan": None, "hints": [],   # hints = 추가한 자리(spec_구분_기준 ② §11)
                         "review": None, "reviewing": False,   # 마지막 LLM 검토(취합 — ② §14, 작업에 저장) · 도는 중(메모리만)
                         "prior": None,   # 앞서 이 문서에 반영한 값들(② §19 — None = 아직 안 모음: _division_prior 가 작업 기록에서 한 번)
                         "confirmed": None}   # 1단계 구성 확정 {at, hash, values}(spec_작업 ② §18) — 공유 중이면 프로젝트의 것을 옮겨 적음, 작업에 저장
        self.outline = None  # 개요(템플릿) 편집 오버레이(spec_hwpx_웹편집 ② §8) — 2단계 그래프에서 만들고 편집마다 손질, 실행 취소·작업 저장과 함께
        # 편집 구역(spec_구역 ② §7 「저장 · 읽는 길 · 등록」 — zones_api.blank() 와 같은 꼴): 구역 판 · 지정(사람이 고른 블록 — 실행 취소 대상 아님) · 출처(취합으로 들어온 내용 — 실행 취소와 함께). 작업에 저장
        self.zones = {"rev": 0, "marks": [], "origins": []}

    def text_edited(self):
        return {i for i, t in self.texts.items() if t != self.orig_texts.get(i)}

    def edited(self):
        return self.text_edited() | self.unrestored | self.formatted | self.struct | self.removed

    def kinds(self):
        """고친 문단마다 종류 — text(글만, 되돌리기 가능)·format(모양, 되돌리기 가능)·struct(나누기·합치기)·new·removed(실행 취소로)."""
        return {i: "removed" if i in self.removed else "new" if i not in self.orig_texts else "struct" if i in self.struct
                else "format" if i in self.formatted else "text" for i in self.edited()}

    def pristine_file(self):
        """지금 저장하면 기준(올린 원본 또는 마지막 확정본) 바이트 그대로인지(고친 XML 부분·새 멤버 없음)."""
        return not self.doc._dirty and not (self.doc._new_members if self.fmt == "hwpx" else self.doc._blobs)

    def open_base(self):
        """기준 문서를 따로 연다(문단 원본 복원용) — 세션 문서의 기준 요소와 같은 블록 id(올린 원본은 blocks() 차례, 확정본은 그때의 자리표)."""
        d = self.kit["cls"](self.original)
        if self.base_ids is not None:
            d.adopt_ids(self.base_ids)
        d.blocks()
        return d

    def state(self):
        return {"editedCount": len(self.edited()), "unrestored": sorted(self.unrestored), "pristine": self.pristine_file(),
                "kinds": self.kinds(), "undo": len(self.undo), "owpml": self.owpml_last,
                "rev": self.rev,  # 서버 편집 차례(spec_작업 ② §3) — 화면이 출력파일 검증의 rev 와 견줘 「검증 뒤 바뀜」 판정
                "base": self.base_n,  # 기준 확정 번호(spec_작업 ② §8) — 0 = 올린 원본
                "persistError": self.persist_error}


class _JobView:
    """검증 스레드에 넘기는 세션 보기(spec_작업 ② §8) — 시작 때의 기준(바이트·블록·원래 글·id 자리표·PDF 사전·문서)을 붙들어, 도는 중에 확정으로 기준이
    바뀌어도 옛 기준끼리 끝까지 맞게 돈다. 결과(매핑·재구성 바이트·기준선 …)는 기준이 그대로일 때만 세션에 쓰고, 바뀌었으면 이 보기에만 둔다."""
    KEEP = ("original", "blocks", "orig_texts", "base_ids", "base_n", "pdf", "doc")

    def __init__(self, s):
        self.__dict__.update(_s=s, _gen=s.gen, _own={k: getattr(s, k) for k in self.KEEP})

    def live(self):
        return self._s.gen == self._gen

    def __getattr__(self, k):  # 인스턴스 사전(_s·_gen·_own)에 없는 이름만 여기로 온다
        own = self.__dict__["_own"]
        return own[k] if k in own else getattr(self.__dict__["_s"], k)

    def __setattr__(self, k, v):
        s = self._s
        with s.glock:
            if s.gen != self._gen or k in self._own:
                self._own[k] = v
            if s.gen == self._gen:
                setattr(s, k, v)


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
    job.revision, job.rev, job.output, job.base = revision, sess.rev, output, sess.base_n
    sess.jobs[kind] = job
    works.log(sess.id, "verify", rev=sess.rev, verify=kind, revision=revision)
    view = _JobView(sess)  # 시작 때의 기준을 붙든 보기 — 도는 중에 확정해도 옛 기준끼리 돈다(spec_작업 ② §8)

    def run():
        try:
            fn(view, job, *args)
        finally:
            if view.live():  # 도는 중에 기준이 바뀐 검증은 기록하지 않는다 — 새 기준의 검증이 따로 돈다
                _record(sess, kind, job)
    threading.Thread(target=run, daemon=True).start()
    return job


def _admit(sess):
    while len(DOCS) >= MAX_DOCS:  # 가장 오래 안 쓴 문서부터 비운다(열린 순서가 아니라 마지막 요청 시각) — 작업 폴더에 먼저 쓴다
        old = min(DOCS.values(), key=lambda x: x.touched)
        _persist_safe(old)
        DOCS.pop(old.id, None)
    DOCS[sess.id] = sess


def _same(name, fmt, data, source, job=None):
    """같은 파일로 만든 작업이 있으면 그 작업을 이어 연다(spec_작업 ② §1) — 메모리에 없으면 작업 폴더에서(_reopen: 기준 확정·문서 키를 맞춤).
    job(고른 TASK)이 있으면 그 TASK 의 작업 → TASK 가 빈 작업 → 그 밖의 가장 최근 작업 차례(② §15). 못 열면 None(새 작업으로)."""
    w = works.find_same(name, fmt, works.sha256(data), job)
    if w is None:
        return None
    try:
        s = DOCS.get(w["id"]) or _reopen(w["id"])
    except Exception:  # noqa: BLE001 — 작업 폴더가 깨졌으면 새 작업으로 연다(깨진 작업은 지우지 않음)
        return None
    if s is None:
        return None
    s.touched = time.time()
    works.log(s.id, "reupload", rev=s.rev, source=source)
    w = works.update(s.id) or w  # 최근 작업 맨 위로
    return {"docId": s.id, "name": w["name"], "size": len(data), "reused": True,
            "work": {k: w.get(k) for k in ("created", "updated", "rev", "edited", "commits")}}


def _open(name, data, source="upload", new=False, job=None):
    """올리기·예제 열기 — 같은 파일(이름·형식·바이트)로 만든 작업이 있으면 그 작업을 이어 열고(reused), new 면 늘 새 작업(spec_작업 ② §1).
    job = 올릴 때 고른 TASK(② §15) — 같은 파일 작업이 여럿일 때 이어 열 작업을 고르는 차례에만 쓴다(작업의 task 는 안 바꾼다)."""
    fmt = fmt_of(name)
    if fmt is None:
        raise HTTPException(400, "hwp·hwpx·docx 파일만 열 수 있습니다")
    if len(data) > MAX_MB * 2 ** 20:
        raise HTTPException(413, f"{MAX_MB} MB 보다 큰 파일은 열 수 없습니다")
    same = None if new else _same(name, fmt, data, source, job)
    if same is not None:
        return same
    try:
        sess = Session(name, data)
    except Exception as e:
        raise HTTPException(400, f"{fmt} 로 열 수 없습니다: {e}") from e
    _admit(sess)
    w = works.create(sess.id, name, fmt, data, source)  # 같은 파일 작업이 없거나 new — 새 작업(spec_작업 ② §1)
    sess.doc_key = (w or {}).get("sha256") or works.sha256(data)  # 문서 키 = 올린 원본의 sha256(확정으로 기준이 바뀌어도 그대로, ② §8)
    _ensure_persister()
    _start(sess, "import", verify.run_import)
    return {"docId": sess.id, "name": name, "size": len(data), "reused": False}


# ---- 작업 저장·다시 열기·기록(spec_작업 ② §3~§5) ---------------------------------------------------------

PERSIST_EVERY = float(os.environ.get("NFM_PERSIST_EVERY", "1.5"))
MAP_KEYS = ("pages", "pageCount", "ratio", "unit", "twoUp", "sheets", "breaks", "pageStatus")  # 화면·출력파일 검증이 쓰는 매핑 키
_persister = None
_reopen_lock = threading.Lock()


def _map_view(m):
    return m and {k: m[k] for k in MAP_KEYS if k in m}


BUMPED = []  # 편집 한 번마다 부를 함수 (세션, 종류, 기록 필드) — 세션 잠금 안 · 차례 순. hwpx 공유의 변경 알림이 듣는다(app/share_api.py — spec_공유 ② §4)


def _bump(s, kind, **fields):
    """편집 한 번(세션 잠금 안에서) — 차례를 올리고 기록에 한 줄. 작업 폴더에는 배경 저장이 쓴다."""
    s.rev += 1
    works.log(s.id, kind, rev=s.rev, **fields)
    for fn in BUMPED:
        fn(s, kind, fields)


def _persist(s, force=False):
    """세션 편집 상태를 작업 폴더에 — 차례가 바뀌었을 때만(force 면 검증 결과·매핑이 바뀐 때도). 묶음은 잠금 안, 쓰기는 잠금 밖."""
    if not works.enabled() or (s.rev == s.saved_rev and not force):
        return
    if DOCS.get(s.id) is not s:  # 메모리에서 비웠거나 지운 세션(늦게 끝난 검증 스레드 등) — 다시 연 세션의 상태를 옛것으로 덮지 않는다
        return
    with s.plock:
        with s.lock:
            rev, base = s.rev, s.base_n  # base = 이 편집 상태가 기대는 확정(spec_작업 ② §8) — 다시 열 때 그 확정 위에 붙인다
            snap = s.kit["struct"].snapshot(s.doc)  # 실행 취소와 같은 묶음 — 다시 열 때 struct.restore 로 기준 유지
            state = {"rev": rev, "base": base, "texts": dict(s.texts), "unrestored": sorted(s.unrestored), "formatted": sorted(s.formatted),
                     "struct": sorted(s.struct), "removed": sorted(s.removed), "origin": dict(s.origin), "owpmlLast": s.owpml_last,
                     "owpmlOk": sorted(list(k) for k in s.owpml_ok),  # 가져온 내용이 물고 온 위반 종류(owpml_allow)
                     "pdf": {k: str(p) for k, p in s.pdf.items() if p}, "mapping": _map_view(s.mapping),
                     "mappingEdited": _map_view(s.mapping_edited),
                     "division": {"settings": s.division["settings"], "applied": s.division["applied"], "hints": s.division.get("hints") or [],  # spec_구분_기준 ② §4·§11
                                  "review": s.division.get("review"),  # 마지막 LLM 검토(② §14)
                                  "confirmed": s.division.get("confirmed"),  # 1단계 구성 확정(spec_작업 ② §18)
                                  **({"prior": s.division["prior"]} if s.division.get("prior") is not None else {})},  # 앞서 반영한 값들(② §19) — 아직 안 모았으면 키 없음
                     "outline": s.outline,  # 개요 편집 오버레이(spec_hwpx_웹편집 ② §8)
                     "zones": copy.deepcopy(s.zones)}  # 편집 구역의 지정·출처(spec_구역 ② §7 「저장 · 읽는 길 · 등록」) — 사본(쓰기는 잠금 밖: 그 사이 지정을 잇는 편집이 목록을 고친다)
            edited, framed = len(s.edited()), bool(s.division["applied"])
        snap = {**snap, "rev": rev, "base": base, "sha256": works.sha256(snap["bytes"])}
        works.save_state(s.id, s.fmt, snap, state, rev=rev, edited=edited, framed=framed)   # framed = 프로젝트 구성을 반영한 문서 — 닫힌 작업의 보이는 이름이 본다(spec_작업 ② §10 「프레임 이름」)
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
               "base": getattr(job, "base", 0),  # 그때의 기준 확정 — 다시 열 때 지금 기준의 기록만 결과로 보인다(spec_작업 ② §8)
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
    """작업 폴더의 묶음·집합을 세션에 — 묶음 차례·바이트·기준 확정이 상태와 어긋나면 False(기준 그대로 둔다)."""
    snap, st = got["snap"], got["state"]
    if snap is None or not isinstance(st, dict) or snap.get("rev") != st.get("rev") or snap.get("sha256") != works.sha256(snap["bytes"]):
        return False
    if snap.get("base", 0) != st.get("base", 0) or st.get("base", 0) != s.base_n:  # 다른 확정 위의 편집 상태(spec_작업 ② §8)
        return False
    doc = s.kit["struct"].restore(s.kit["cls"], s.original, snap)  # 기준 = 세션의 기준 바이트(원본 복원·바이트 동일 판정), adopt_ids 로 같은 블록 id
    s.doc = doc
    s.texts = dict(st.get("texts") or s.orig_texts)
    s.unrestored, s.formatted = set(st.get("unrestored", ())), set(st.get("formatted", ()))
    s.struct, s.removed, s.origin = set(st.get("struct", ())), set(st.get("removed", ())), dict(st.get("origin") or {})
    s.owpml_last = st.get("owpmlLast")
    s.owpml_ok, s.owpml_base = {tuple(k) for k in st.get("owpmlOk") or [] if isinstance(k, list) and all(isinstance(x, str) for x in k)}, None  # 기준선은 다음에 다시 센다(그 종류를 더해)
    s.pdf = {k: p for k, p in (st.get("pdf") or {}).items() if p and Path(p).exists()}  # 렌더 캐시에서 지워진 PDF 는 뺀다
    s.mapping, s.mapping_edited = st.get("mapping"), st.get("mappingEdited")
    dv = st.get("division") or {}
    s.division = {"settings": dv.get("settings"), "applied": dv.get("applied"), "plan": None, "hints": [h for h in dv.get("hints") or [] if isinstance(h, dict)],
                  "review": dv.get("review") if isinstance(dv.get("review"), dict) else None, "reviewing": False,
                  "prior": [v for v in dv["prior"] if isinstance(v, dict)] if isinstance(dv.get("prior"), list) else None,   # ② §19 — 키가 없으면(옛 작업) 처음 쓸 때 모음
                  "confirmed": dv.get("confirmed") if isinstance(dv.get("confirmed"), dict) else None}   # 1단계 구성 확정(spec_작업 ② §18) — 옛 작업은 없음
    s.outline = st.get("outline") if isinstance(st.get("outline"), dict) else None
    from app import zones_api
    s.zones = zones_api.load(st.get("zones"))   # 편집 구역의 지정·출처(spec_구역 ② §7 「저장 · 읽는 길 · 등록」) — 옛 작업(키 없음)은 빈 것
    return True


def _commit_state(s, extra):
    """확정 때의 구분 기준 적용 상태·개요 오버레이를 세션에(spec_작업 ② §8) — 편집 상태 파일이 있으면 _restore_state 가 그 뒤에 덮는다."""
    extra = extra or {}
    s.division["applied"] = extra["division"] if isinstance(extra.get("division"), dict) else None
    s.outline = extra["outline"] if isinstance(extra.get("outline"), dict) else None


def _base_session(w, n, original):
    """기준 확정 n 위의 새 세션(0 = 올린 원본, spec_작업 ② §8) — 확정 파일·블록 id 자리표를 못 읽으면 예외."""
    wid = w["id"]
    if not n:
        s = Session(w["name"], original, sid=wid)
    else:
        data, extra = works.commit_bytes(wid, n), works.commit_data(wid, n)
        if data is None or not isinstance((extra or {}).get("ids"), dict):
            raise RuntimeError(f"확정 {n} 의 파일을 읽지 못했습니다")
        s = Session(w["name"], data, sid=wid, ids=extra["ids"], base=n)
        _commit_state(s, extra)
    s.created = w.get("created", s.created)
    s.doc_key = w.get("sha256") or works.sha256(original)  # 문서 키 = 올린 원본의 sha256
    return s


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
        st = got["state"] if isinstance(got["state"], dict) else None
        has_state = got["snap"] is not None or got["state"] is not None
        base = st.get("base", 0) if st else works.head(doc_id)  # 편집 상태가 기대는 확정(spec_작업 ② §8) — 상태가 없으면 마지막 확정
        s, ok, why = None, True, None
        try:
            s = _base_session(w, base, got["original"])
            if has_state:
                ok = _restore_state(s, got)
                why = None if ok else "편집 상태 파일이 서로 맞지 않음"
        except Exception as e:  # noqa: BLE001 — 블록 id 자리표 불일치·기준 확정 파일을 못 읽음 등
            ok, why = False, str(e)
        if not ok:  # 마지막으로 읽히는 확정(없으면 올린 원본)으로 연다 — 어긋난 편집 상태 파일은 지우지 않고 옆으로(손으로 살릴 수 있게)
            s = None
            for k in dict.fromkeys((works.head(doc_id), 0)):
                try:
                    s = _base_session(w, k, got["original"])
                    break
                except Exception as e:  # noqa: BLE001 — 그 확정도 못 읽음: 올린 원본으로
                    why = f"{why} · 확정 {k}: {e}"
            if s is None:
                raise RuntimeError(f"작업 {doc_id} 를 열지 못했습니다 — {why}")
            if has_state:
                works.set_aside_state(doc_id)
            works.update(doc_id, rev=0, edited=0)
        s.rev = s.saved_rev = w.get("rev", 0) if ok else 0
        if bool(s.division.get("applied")) != bool(w.get("framed")):   # 이 표시가 생기기 전에 반영한 작업 · 어긋난 상태를 옆으로 옮긴 작업 — 닫힌 뒤의 보이는 이름이 맞게(② §10 「프레임 이름」 · 바뀐 때는 그대로)
            works.mark(doc_id, framed=bool(s.division.get("applied")))
        for kind, rec in works.last_runs(doc_id).items():  # 지금 기준에서 돈 검증만 결과로(확정 뒤 가져오기 검증이 끝나기 전에 꺼졌으면 다시 돈다)
            if isinstance(rec, dict) and isinstance(rec.get("job"), dict) and rec.get("base", 0) == s.base_n:
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
def open_sample(name: str, new: bool = False):
    p = SAMPLES / name
    if p.parent != SAMPLES or not p.is_file():
        raise HTTPException(404, "예제가 없습니다")
    return _open(p.name, p.read_bytes(), "sample", new)


@app.post("/api/docs")
async def upload(file: UploadFile = File(...), new: bool = False, job: str = ""):
    """?new=1 이면 같은 파일 작업이 있어도 새 작업(spec_작업 ② §1). hwp(바이너리)는 한글로 hwpx 로 바꿔 hwpx 작업으로 받는다.
    ?job=<TASK> = 올릴 때 고른 TASK(② §15) — 같은 파일 작업이 여럿이면 그 TASK 의 작업 → TASK 가 빈 작업 → 그 밖의 가장 최근 작업 차례로 이어 연다. 모르는 값은 없는 것으로 본다."""
    name, data = file.filename or "document.hwpx", await file.read()
    if name.lower().endswith(".hwp"):
        from starlette.concurrency import run_in_threadpool
        name, data = await run_in_threadpool(_from_hwp, name, data)   # 한글 변환은 수 초~수십 초 — 이벤트 루프 밖에서
    return _open(name, data, new=new, job=job if job and job in TASK["job"] else None)


def _from_hwp(name, data):
    """올린 hwp → (이름.hwpx, hwpx 바이트) — 2026-11-11 사용자 "hwp 넣어도 알아서 hwpx 로 변환해서 사용할 수 있게". 작업은 hwpx 작업이고 원본 hwp 는 남기지 않는다(변환본은 렌더 캐시에)."""
    if len(data) > MAX_MB * 2 ** 20:
        raise HTTPException(413, f"{MAX_MB} MB 보다 큰 파일은 열 수 없습니다")
    if not pdf_render.available("hwpx"):
        raise HTTPException(400, "hwp 파일은 이 PC 에 한글이 있어야 hwpx 로 바꿔 열 수 있습니다 — 한글에서 hwpx 로 저장해 올려 주세요")
    try:
        return name[:-4] + ".hwpx", pdf_render.hwp_to_hwpx(data)
    except (RuntimeError, TimeoutError, OSError) as e:
        raise HTTPException(400, f"hwp 를 hwpx 로 바꾸지 못했습니다: {e}") from e


@app.get("/api/docs/{doc_id}")
def get_doc(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        edited = s.edited()
        blocks = s.doc.blocks()
        table = s.doc.font_table(blocks) if s.fmt == "docx" else s.doc.font_table()
        return {"docId": s.id, "name": _shown_of(s), "format": s.fmt, "size": len(s.original), "blocks": blocks,   # name = 보이는 이름(spec_작업 ② §10)
                "webFonts": fonts.web_fonts(table),  # 문서 글꼴 @font-face 계획(spec_hwpx_웹편집 ② §3-3)
                "edited": sorted(edited), "original": {i: s.orig_texts.get(i, "") for i in edited},
                "work": {"created": s.created, "rev": s.rev, "stored": works.enabled(), "task": _task(s.id, blocks)},  # 작업(spec_작업 ② §6 · task = §10)
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
        s.pristine = s.open_base()  # 블록 id — 세션 문서의 기준 요소와 같은 id(restore.restore_para 가 id 로 찾음). 기준 = 올린 원본 또는 마지막 확정본
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
        fmt0 = _para_fmt(s, block_id)
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
            # 개요 줄이면 둘째 줄을 글 시작에(spec_hwpx_웹편집 ② §8-1) — 글이 원래와 다른 동안만 걸리고(원래 글이면 위에서 원본 XML 로), 모양 편집(formatted)으로 치지 않는다
            _outline_align(s, block_id)
        fmts = _outline_relabel(s, [block_id])  # 글을 고쳐 첫머리(앞 공백 · 레터 뒤 공백)가 대표와 달라졌거나 같아졌으면 서식 라벨도
        fmt1 = _para_fmt(s, block_id)
        if s.texts[block_id] != before or restored is not None or kind == "revert" or fmt1 != fmt0:  # 글은 같아도 둘째 줄을 맞췄으면 차례를 올려 작업에 저장되게
            _bump(s, kind, id=block_id, before=before, after=s.texts[block_id], restored=restored)
        return {"id": block_id, "text": s.texts[block_id], "edited": block_id in s.edited(), "restored": restored, **s.state(),
                **({"format": fmt1} if fmt1 != fmt0 else {}),  # 문단 모양이 바뀌었으면(둘째 줄 맞춤·원본 복원) 화면이 그 문단의 여백을 다시 잡는다
                **({"fmts": fmts} if fmts else {})}


def _para_fmt(s, block_id):
    """hwpx 문단의 서식 요약(블록 format 과 같은 것) — 글 고침 앞뒤를 견줘 바뀌었을 때만 응답에 싣는다. docx·문단 아님 = None."""
    el = s.doc._ids.get(block_id)
    if s.fmt != "hwpx" or el is None or el.tag != P:
        return None
    return s.doc._summary(el.get("paraPrIDRef"), s.doc._char_id(el))


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
    # 보이는 이름(spec_작업 ② §10 — 과제에 묶인 목적 문서는 과제 이름이 뒤에 붙는다 · 프로젝트 구성을 반영한 양식 맞추기 문서는 프레임 이름 그대로). same = 기준과 같은 바이트 — 기준이 확정본이면 올린 파일과는 다른 파일
    name = _save_name(_shown_of(s), "." + s.fmt, works.work(s.id), bool(s.division.get("applied")), edited=not same or bool(s.base_n))
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
    """판정 기준선 = 원본의 OWPML 위반 종류·개수(`s.owpml_base` — 가져오기 검증이 먼저 채우고, 없으면 여기서: 캐시) + 받아들인 종류(`s.owpml_ok` — owpml_allow).
    둘을 **부를 때마다 합친다**(원본 기준선은 그대로 둔다 — 검증이 원본 결과로 다시 채워도, 실행 취소로 받아들인 종류가 줄어도 어긋나지 않게 · 2026-11-13 astra 결과 검토)."""
    if s.owpml_base is None:  # hwpx: OWPML, docx: OOXML 참조 규칙(docx_check) — 모양이 같은 모듈
        check = s.kit["check"]
        s.owpml_base = check.counts(check.check_doc(s.kit["cls"](s.original)))
    extra = [k for k in s.owpml_ok if k not in s.owpml_base["schema"]]
    if not extra:
        return s.owpml_base
    schema = s.owpml_base["schema"].copy()
    for k in extra:
        schema[k] = 1
    return {"schema": schema, "rules": s.owpml_base["rules"]}


def owpml_allow(s, kinds):
    """다른 문서에서 가져온 내용(서식 보관함의 운반 문서 — spec_일반편집 ② §4)이 물고 올 수 있는 스키마 위반 **종류**를 이 작업이 받아들인 종류(`s.owpml_ok`)에 더한다
    (세션 잠금 안, `_transact` 의 `run()` 안에서 — 그 편집의 판정은 run() 뒤에 기준선을 다시 읽는다) -> 새로 더한 종류. 한글이 그 문서의 **header 정의**에 써 둔 꼴(tabPr/switch 등)이라
    편집이 만든 위반이 아니다. 받는 것은 header 쪽 스키마 종류뿐 — 본문(section)의 종류(틀린 속성 값 등 가져온 문단·표 자체의 손상)와 참조 규칙 위반(끊어진 참조)은 안 받는다:
    그런 내용을 가져온 편집은 전처럼 422 로 되돌린다. 받아들인 종류는 실행 취소 묶음에 들고(`_snap` — 편집이 되돌려지면 함께 되돌아간다) 편집 상태와 함께 저장된다(`_persist`)."""
    base = owpml_base(s)["schema"]
    added = [k for k in kinds if isinstance(k, tuple) and len(k) == 5 and k[0] == "header" and k not in base]
    s.owpml_ok.update(added)
    return added


def _snap(s):
    return {"doc": s.kit["struct"].snapshot(s.doc), "texts": dict(s.texts), "unrestored": set(s.unrestored),
            "formatted": set(s.formatted), "struct": set(s.struct), "removed": set(s.removed), "origin": dict(s.origin),
            "division": copy.deepcopy(s.division["applied"]),  # 구분 기준 적용 상태도 실행 취소와 함께(spec_구분_기준 ② §4)
            "outline": copy.deepcopy(s.outline),  # 개요 편집 오버레이도(spec_hwpx_웹편집 ② §8)
            "owpml_ok": set(s.owpml_ok),  # 받아들인 위반 종류도(owpml_allow) — 가져온 정의가 되돌려지면 허용도 되돌린다
            "zones": __import__("app.zones_api", fromlist=["snap"]).snap(s)}  # 편집 구역의 출처(취합으로 들어온 내용의 기록)도 — 넣은 편집이 되돌려지면 함께(spec_구역 ② §4 「출처 — 취합으로 들어온 내용」). 지정은 안 넣는다


def _rollback(s, snap):
    s.doc = s.kit["struct"].restore(s.kit["cls"], s.original, snap["doc"])
    s.owpml_ok = set(snap.get("owpml_ok", s.owpml_ok))
    s.texts, s.unrestored, s.formatted = dict(snap["texts"]), set(snap["unrestored"]), set(snap["formatted"])
    s.struct, s.removed, s.origin = set(snap["struct"]), set(snap["removed"]), dict(snap["origin"])
    s.division["applied"], s.division["plan"] = copy.deepcopy(snap.get("division")), None  # 계획은 문서 버전에 묶여 있어 되돌리면 무효
    s.outline = copy.deepcopy(snap.get("outline"))
    # 편집 구역(spec_구역 ② §3 「지정 — 사람이 고른 블록」): 출처는 그 묶음의 것으로 · 되돌린 문서에 없는 블록은 지정에서 뺀다(번호표도 되돌아가 같은 번호가 다른 새 문단에 다시 쓰인다 — 옛 지정을 물려받지 않게)
    __import__("app.zones_api", fromlist=["rollback"]).rollback(s, snap.get("zones"))


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


def _texts_now(s, cur, ids):
    """cur(블록에서 읽은 글)에 — ids 가운데 글이 비어 블록 목록에서 빠진 문단(개체만 남은 문단)도 지금 글로 더한다."""
    for i in ids:
        if i not in cur and s.doc._attached(s.doc._ids.get(i)) and s.doc._ids[i].tag == s.kit["para"]:
            cur[i] = s.doc._text(s.doc._ids[i])
    return cur


def _touched_blocks(s, hosts, local, had):
    """편집 뒤 닿은 최상위 문단(hosts)의 블록만 — 못 읽으면(문서 순서로 세는 값이 든 문단이 있음) None. 개요 편집이 양 끝에 하나씩 더 싣는 **안 닿은 이웃**
    (편집 전부터 있었고(had) 편집이 닿지 않은(local 밖) 문단)이 번호·자동 번호 문단(캡션 번호가 붙은 표 등)이면 그 이웃만 빼고 읽는다 — 그 이웃은 안 바뀌었고
    화면은 옛 블록을 그대로 둔다. 구간 가운데에 낀 것은 뺄 수 없다(화면이 구간을 통째로 바꾼다) → None."""
    doc = s.doc
    out = doc.host_blocks(hosts)
    if out is not None:
        return out
    near, core = set(local), doc.in_order(hosts)
    idle = lambda h: h in had and h not in near and doc.order_bound([h])  # noqa: E731
    n = len(core)
    while core and idle(core[0]):
        core.pop(0)
    while core and idle(core[-1]):
        core.pop()
    return doc.host_blocks(core) if core and len(core) < n else None


def _transact(s, run, op=None, req=None, check=None, local=None):
    """구조 편집 트랜잭션(spec_구분_기준 ② §4 — _edit 의 공통부): 세션 잠금 안에서 직전 상태를 묶어 두고 → run() → 검사(check(s, out, base, header) -> verdict,
    기본 _hosts_check) → 원본에 없던 종류의 위반이면 되돌리고 422 → 성공이면 undo 1개·글/집합 갱신·rev +1·기록 1줄.
    run() -> {"hosts": 편집 뒤 닿은 요소, "focus", "formatted", "struct", "origin", "anchor", "log"?: 기록에 더 적을 것}.
    -> (out, 편집 뒤 블록) | (JSONResponse 422, None). run() 의 KeyError·ValueError 는 400(고치다 만 경우 복원).
    local = 편집이 닿는 최상위 문단들(편집 전 — _edit 가 준다): 주면 편집 뒤 문서 전체(blocks())를 다시 읽지 않고 **닿은 최상위 문단의 블록만** 읽어(HwpxDoc.host_blocks)
    글 사전을 그만큼만 고치고, 돌려주는 블록도 그것뿐이다(spec_owpml_편집 ② §3 「닿은 블록만 다시 읽기」 — 연구개발계획서 12,700문단에서 개요 줄 Enter 한 번에 1 s 들던 것).
    문서 순서로 세는 값(번호 문단·자동 번호 — order_bound)이 닿은 문단에 있거나 docx·전체 검사(check)면 전처럼 문서 전체."""
    st, chk = s.kit["struct"], s.kit["check"]
    snap = _snap(s)
    part = local is not None and check is None and hasattr(s.doc, "host_blocks") and not s.doc.order_bound(local)
    had = {p for sec in s.doc._sections for p in sec.iterchildren(s.kit["para"])} if part else None  # 편집 전부터 있던 최상위 문단 — 편집 뒤 「안 닿은 이웃」을 가린다(_touched_blocks)
    pre = {s.doc._rev[p] for h in local for p in h.iter(s.kit["para"]) if p in s.doc._rev} if part else None  # 닿는 문단 아래의 문단 id(편집 전) — 글 사전에서 이만큼만 갈아 끼운다
    ndefs = sum(len(v) for v in getattr(s.doc, "_defs", {}).values())  # hwpx header 정의 수(docx 서식 편집은 직접 서식 — 정의를 안 더함)
    base = owpml_base(s)
    try:
        out = run()
    except (KeyError, ValueError) as e:
        if s.doc._blocks_cache is None:  # 고치다 만 경우 — 직전 상태로
            _rollback(s, snap)
        else:  # 문서는 안 건드렸어도 오버레이는 시작 때 것으로(대표 바꿈 같은 오버레이 변경이 남지 않게 — spec_hwpx_웹편집 ② §8-8 「실패 뒤 오버레이」). snap 은 버리는 것이라 그대로 쓴다
            s.outline = snap["outline"]
        s.owpml_ok = set(snap["owpml_ok"])  # 실패한 편집이 받아들인 종류(owpml_allow)는 남기지 않는다
        raise HTTPException(400, str(e)) from e
    base = owpml_base(s)  # run() 이 받아들인 종류(owpml_allow)까지 넣어 다시 읽는다
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
    old = set(s.texts)
    after = _touched_blocks(s, out["_hosts"], local, had) if part else None
    if after is None:  # 문서 전체를 다시 읽는다
        after = s.doc.blocks()
        cur = _texts_now(s, verify.flat_texts(after), s.texts)
    else:  # 닿은 최상위 문단의 블록만 — 그 아래 문단의 글만 갈아 끼운다(밖은 안 바뀜: _hosts_check 가 닿은 문단만 검사하는 것과 같은 전제)
        cur = {i: t for i, t in s.texts.items() if i not in pre}
        cur.update(verify.flat_texts(after))
        _texts_now(s, cur, pre & old)  # 글 사전에 있던 것만(표만 품은 새 문단 같은 것은 전체를 읽어도 안 든다)
        if os.environ.get("NFM_BLOCKS_CHECK") == "1":  # 시험(tests/conftest.py): 편집마다 문서 전체를 다시 읽은 것과 견준다
            full, ids = s.doc.blocks(), {b["id"] for b in after}
            assert [b for b in full if b["id"] in ids] == after, f"{op}: 닿은 블록만 읽은 것이 blocks() 와 다름"
            want = _texts_now(s, verify.flat_texts(full), s.texts)
            assert cur == want, (f"{op}: 닿은 블록만 고친 글이 문서 전체를 다시 읽은 것과 다름 — 더 있음 {sorted(set(cur) - set(want))[:6]} · "
                                 f"없음 {sorted(set(want) - set(cur))[:6]} · 글 다름 {[i for i in cur if i in want and cur[i] != want[i]][:6]}")
    s.texts = cur
    s.formatted |= out.get("formatted", set())
    s.struct |= out.get("struct", set())
    for i in set(cur) - old:
        s.origin.setdefault(i, out.get("origin", {}).get(i, out.get("anchor")))
    s.removed = {i for i in s.orig_texts if not s.doc._attached(s.doc._ids.get(i))}
    s.unrestored -= s.removed
    s.owpml_last = {"status": v["status"], "summary": chk.summary_text(v)}
    _outline_sync(s)
    if s.outline and out.get("formatted"):  # 서식이 바뀐 개요 줄의 서식 라벨을 지금 서식에 맞춘다(손으로 바꿔 대표와 달라진 줄 = 「≠」 — spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」). 오버레이는 snap 에 들어 실행 취소와 함께 돌아온다
        fm = _outline_relabel(s, out["formatted"])
        if fm:
            out["_fmts"] = fm
    if s.zones["marks"] or s.zones["origins"]:  # 편집 구역(spec_구역 ② §3 「지정 — 사람이 고른 블록」): 지정한 문단에서 나온 새 문단(문단 나눔 · 새 줄 — zones_api.INHERIT_OPS)은 그 지정에 잇고, 취합으로 들어온 문단을 나눈 뒷부분은 그 출처에 잇는다. 둘 다 없으면 아무 일도 안 한다
        __import__("app.zones_api", fromlist=["after_edit"]).after_edit(s, op, {i: s.origin.get(i) for i in set(cur) - old})
    _bump(s, op or "edit", req=req, owpml=s.owpml_last, **(out.get("log") or {}))
    return out, after


def _edit(doc_id, make, op=None, req=None):
    """구조·서식 편집 한 번(_transact 위) — 닿은 최상위 문단(+header)만 OWPML 검사. make(s) -> (편집 전 닿는 요소들, run).
    응답 tops = 바뀐 최상위 블록 {drop: 옛 id, blocks: 새 블록}."""
    s = _sess(doc_id)
    with s.lock:
        st = s.kit["struct"]
        before, run = make(s)
        hosts = [h for h in dict.fromkeys(st.top_host(s.doc, e) for e in before) if h is not None]
        drop = [i for h in hosts for i in st.top_ids(s.doc, h)]
        faces = _font_names(s)
        out, after = _transact(s, run, op, req, local=hosts)
        if after is None:
            return out
        drop += [i for i in out.get("drop") or () if i not in drop]  # 편집이 알려 준 「지운 블록」(개요 편집 — 닿은 문단 목록에 없던 간격 줄 등)
        want = {i for h in out["_hosts"] for i in st.top_ids(s.doc, h)}
        tops = [b for b in after if b["id"] in want]
        return {"tops": {"drop": drop, "blocks": tops}, "texts": verify.flat_texts(tops), "focus": out.get("focus"),
                "edited": sorted(s.edited()), "original": {i: s.orig_texts.get(i, "") for i in s.edited()}, **s.state(),
                **({"fmts": out["_fmts"]} if out.get("_fmts") else {}),  # 서식이 바뀐 개요 줄의 새 서식 라벨(여백의 번호 — 대표와 달라진 줄은 「≠」)
                # 편집이 새 글꼴 정의를 들여왔으면(다른 문서의 서식을 입힘 — spec_일반편집 ② §4) 화면이 @font-face 계획을 다시 받게: 없으면 새 글꼴의 글이 기본 글꼴로 그려진다
                **({"webFonts": fonts.web_fonts(s.doc.font_table())} if faces is not None and _font_names(s) != faces else {})}


def _font_names(s):
    """hwpx 문서 header 의 (언어, 글꼴 이름)들 — 편집 앞뒤로 견줘 새 글꼴 정의가 들어왔는지 본다(docx 는 None — 직접 서식이라 편집이 글꼴 목록을 안 바꾼다)."""
    return {(lang, face) for lang, faces in s.doc.font_table().items() for face in faces} if s.fmt == "hwpx" else None


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
        # auto = 문단 모양의 글머리표·문단 번호("bullet" | "number" | None) — 레터가 글에 없는 자동 글머리 줄(spec_hwpx_웹편집 ② §8-8 「자동 글머리 줄」)
        return {"text": doc._text(el), "attrs": doc.para_attrs(pid), "spacer": sp, "auto": outline_match.auto_kind(doc, pid)}
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
        old = ov
        ov = s.outline = outline_edit.build_overlay(g, _outline_probe(s), rev=s.rev)
        old = __import__("app.outline_lift", fromlist=["carry"]).carry(old, ov, s.doc)  # 표 제목을 L1 로 넣은 템플릿(② §8-7)부터 — 레벨이 한 칸 밀리므로 아래 carry 들(앵커 + 레벨)보다 먼저
        outline_pos.carry(old, ov)  # 사용자가 정한 슬롯 자리 규칙(같은 앵커·레벨)·저절로 맞춘 줄의 기억은 새 오버레이로(② §8-1)
        fails = outline_match.carry(old, ov, outline_match.context(s.doc, ov))  # 템플릿 종속(같은 앵커끼리)·사람이 정한 대표도(② §8-2)
        if fails:
            log.warning("[개요 종속] %s 다시 걸지 못함: %s", s.id, [(m.get("child"), m.get("parent"), why) for m, why in fails])
        outline_pos.carry(old, ov)  # 종속으로 새로 생긴 레벨의 자리 규칙도(같은 앵커·레벨)
        __import__("app.outline_grow", fromlist=["carry"]).carry(old, ov)  # Alt+↓ 로 더한 레벨(② §8-6) — 그래프가 못 알아본 레벨은 슬롯을 다시, 알아본 레벨은 자리 규칙만
        __import__("app.caption_tpl", fromlist=["carry"]).carry(old, ov)  # 캡션 템플릿 「CN」 의 번호·사람이 정한 대표(② §8-10 — 그래프와 무관한 키라 그대로 옮긴다)
    if ov is not None and not ov.get("fmtv") and ov.get("run") == key:  # 줄의 서식 라벨을 지금 서식에 맞춘다 — 오버레이마다 한 번(라벨이 없던 옛 오버레이 · 새로 만든 오버레이)
        outline_match.label_sync(s.doc, ov, g)
    if ov is not None and not ov.get("autosv") and ov.get("run") == key:  # 자동 글머리 줄(spec_hwpx_웹편집 ② §8-8)이 생기기 전에 만든 오버레이 — 한 번 채운다(그래프를 다시 돌리지 않아도)
        outline_edit.add_autos(ov, g, _outline_probe(s))
    return ov


def _outline_align(s, block_id):
    """글을 고친 문단이 개요 줄이면 둘째 줄을 슬롯 규칙대로(기본 = 글 시작에 — spec_hwpx_웹편집 ② §8-1). 오버레이가 아직 없으면(화면이 /outline 을 안 읽은 세션)
    여기서 만든다. 어떤 오류도 글 반영을 막지 않는다(기록만)."""
    try:
        ov = _outline_ov(s)
    except Exception as e:  # noqa: BLE001
        log.warning("[개요 줄 자리] %s 오버레이를 만들지 못함: %r", s.id, e)
        return
    if ov and block_id in ov["lines"]:
        outline_pos.align_quiet(s.doc, ov, block_id)


def _outline_relabel(s, ids):
    """서식·첫머리가 바뀐 문단 ids 가운데 개요 줄이 든 레벨의 **지금 보일** 서식 라벨(outline_match.labels_now — 대표와 달라진 줄은 「≠」) → {줄 id: 라벨}. 화면이 여백 표시를 그 자리에서 고친다.
    라벨은 표시일 뿐이다 — 어떤 오류도 편집을 막지 않는다. 이 길을 안 거치는 편집(붙여넣기 · 되돌리기 · 넣기 …)은 화면이 문서 차례가 바뀔 때 `GET …/outline/fmts` 로 다시 읽는다."""
    ov = s.outline
    if not ov or not ov.get("fmtv"):
        return {}
    hit = [i for i in ids if i in ov["lines"]]
    if not hit:
        return {}
    try:
        return outline_match.labels_now(s.doc, ov, hit)
    except Exception as e:  # noqa: BLE001
        log.warning("[서식 라벨] %s 다시 매기지 못함: %r", s.id, e)
        return {}


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
    outline_edit.sync_autos(ov, alive, lambda pid: outline_match.auto_kind(doc, pid), lambda pid: doc._text(doc._ids[pid]))  # 자동 글머리 줄(② §8-8)
    ov["rev"] = s.rev + 1


def _outline_seq(s, el):
    """el(문단)이 든 그릇(구역·표 칸 subList)의 문단 열 — 문서 순, 모든 hp:p."""
    doc, par = s.doc, el.getparent()
    # 표 제목 줄(② §8-7 — 열쇠 = 칸 안 제목 문단)은 그 표를 품은 문단(호스트) 자리에 줄 id 로 놓는다(host = 구조 연산이 쓸 호스트 문단 id — _outline_run 의 rid)
    alias = __import__("app.outline_lift", fromlist=["aliases"]).aliases(doc, s.outline, par) if s.outline else {}
    seq = []
    for c in par.iterchildren(P):
        if c in alias:
            seq.append({"id": alias[c], "text": doc._text(doc._ids[alias[c]]), "blank": False, "object": True, "host": doc._id(c)})
            continue
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
        # outline_edit.view + 템플릿 레벨마다 자리(레터 위치·글 시작·둘째 줄 — ② §8-1) + fmts = 줄마다의 지금 서식 라벨(여백의 「S41」 — 맞춘 줄은 대표의 라벨)
        return {**outline_pos.view(s.doc, ov), "fmts": outline_match.labels_now(s.doc, ov)}


@app.get("/api/docs/{doc_id}/outline/fmts")
def outline_fmts(doc_id: str):
    """줄마다 지금 보일 서식 라벨만 {rev, fmts{문단 id: 라벨}} — 화면이 문서가 바뀔 때마다(어느 편집 길이든) 여백의 서식 라벨을 다시 읽는다(spec_헤딩_추출 ② §7 「서식 라벨은 다른 줄에만」).
    대표와 비교 값이 같은 줄은 대표의 라벨 · 다른데 라벨로 구별되지 않는 줄은 오차 안이면 「≈」, 아니면 「≠」(outline_match.labels_now). 2단계 결과가 없으면 빈 것."""
    s = _sess(doc_id)
    with s.lock:
        ov = _outline_ov(s)
        return {"rev": s.rev, "fmts": outline_match.labels_now(s.doc, ov) if ov else {}}


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
        els = [__import__("app.outline_lift", fromlist=["host_of"]).host_of(s.doc, ov, i, e) for i, e in zip(ids, els)]  # 표 제목 줄(② §8-7)이면 그 표를 품은 본문 문단
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

        plan["alias"] = {it["id"]: it["host"] for it in seq if it.get("host")}  # 표 제목 줄 → 호스트 문단(구조 연산의 자리)

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
    kids0 = [c for c in par.iterchildren(P)]  # 편집 전 차례 — 끝에서 「차례가 바뀐 구간」을 찾는다

    alias = plan.get("alias") or {}  # 표 제목 줄(② §8-7) → 그 표를 품은 문단: 뒤에 넣기·옮기기의 자리는 호스트 문단이다

    def rid(x):
        if x == "$last":
            return last
        if x in ("$first", "$new"):
            return first_new
        return alias.get(x, x)

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
    # 새 줄·레벨을 바꾼 줄은 슬롯 자리 규칙대로(기본 = 둘째 줄을 글 시작에), 번호가 바뀐 줄은 저절로 맞춘 것이면 다시 맞춘다(spec_hwpx_웹편집 ② §8-1)
    fresh, meas = set(new_ids) | formatted, outline_pos.Measure(doc)
    for pid in list(changed):
        if pid in ov["lines"] and pid in doc._ids:
            try:
                outline_pos.align(doc, ov, pid, full=pid in fresh, measure=meas)
            except ValueError:
                pass  # 사용자가 정한 레터 위치가 이 줄의 앞 공백 폭보다 작다 — 줄은 그대로 만들고 자리는 안 옮긴다
    # 닿은 범위 = 그릇 안 이어진 구간 전체(가장 앞 ~ 가장 뒤 닿은 문단 사이의 모든 문단 — 표 호스트 포함)
    kids = [c for c in par.iterchildren(P)]
    ix = {c: k for k, c in enumerate(kids)}
    hit = [doc._ids[i] for a in plan["actions"] for i in (a.get("id"), rid(a.get("after")), rid(a.get("ref")), rid(a.get("first")), rid(a.get("last")))
           if i and i in doc._ids and doc._ids[i] in ix] + [doc._ids[i] for i in new_ids if i in doc._ids and doc._ids[i] in ix]
    span = [ix[e] for e in hit]
    # 차례가 바뀐 구간(넣음·지움·옮김)도 닿은 범위다 — 편집 전 차례(kids0)와 견줘 앞뒤로 같은 부분을 뺀 가운데. 지우기만 하면 닿은 문단이 남지 않고(hit 없음 — 전에는 그릇의
    # 첫 문단을 돌려줘 화면이 엉뚱한 자리를 바꿨다), 줄을 여러 줄 건너 옮기면 옛 자리와 새 자리 사이의 문단이 hit 에 없다(화면은 그 사이를 통째로 바꾼다 — 빠지면 화면에서 사라진다). 2026-11-11
    pre = next((k for k, (x, y) in enumerate(zip(kids0, kids)) if x is not y), min(len(kids0), len(kids)))
    suf = next((k for k, (x, y) in enumerate(zip(reversed(kids0[pre:]), reversed(kids[pre:]))) if x is not y), min(len(kids0), len(kids)) - pre)
    if pre + suf < max(len(kids0), len(kids)):
        span += [pre, len(kids) - suf - 1]  # 지우기만이면 [pre, pre - 1] — 지운 자리의 앞뒤
    if span:
        lo, hi = max(0, min(span)), max(span)
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
    gone = [i for c in kids0 if c not in ix for i in s.kit["struct"].top_ids(doc, c)] if par in set(doc._sections) else []  # 지운 최상위 문단의 블록 id — 화면이 뺄 것(drop)
    return {"hosts": hosts, "focus": {"id": fid, "offset": off or 0} if fid else None, "struct": struct, "formatted": formatted, "origin": origin,
            "anchor": ids[0], "drop": gone, "log": {"op": op, "ids": ids, "new": new_ids, "removed": removed}}


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

WORK_KEYS = ("id", "name", "format", "size", "source", "created", "updated", "rev", "edited", "verify", "commits", "task", "roundParent", "alias")  # roundParent = 분기한 이전 라운드의 문서 id · alias = 별칭(② §10)
TASK = {"kind": ("", "rnd", "general"), "file": ("", "plan", "report", "part"),
        "job": ("", "plan_fit", "plan_merge", "plan_to_report", "report_fit", "report_merge", "doc_edit", "style_copy")}  # 작업 종류·첨부 파일·할 일(② §10) — 이름은 화면(app.js WORK_TASK)
TASK_KIND = {"doc_edit": "general", "style_copy": "general"}  # 할 일 → 작업 종류(여기 없으면 rnd) — 「문서 일반 편집」(spec_일반편집 ② §11)·「문서 서식 복사」(spec_서식복사 ② §1)는 일반 문서(general)의 일. 다른 조합은 저장하지 않는다(work_task)


def _task(wid, blocks):
    """작업의 task(② §10) — 고른 것(work.json)이 없으면 문서에서 짐작: 국가R&D 양식이면 연구개발과제, 첨부 파일 = 판정한 양식."""
    t = (works.work(wid) or {}).get("task")
    if not t:
        form = PROFILE.form_of(blocks)
        t = {"kind": "rnd" if form else "", "file": {"연구개발계획서": "plan", "연차보고서": "report"}.get(form, ""), "job": "", "project": ""}
        if form:
            works.update(wid, task=t)   # 짐작도 적어 둔다 — 문서 목록(상단 「다른 문서」·작업 목록)이 종류를 보이게
    return t


def _work_or_404(wid):
    w = works.work(wid)
    if w is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    return w


def _framed(w):
    """프로젝트 구성을 반영한 문서인가(② §10 「프레임 이름」) — 열려 있으면 세션의 지금 상태(반영·실행 취소 바로 뒤에도 맞게), 닫혀 있으면 작업에 적어 둔 것(work.json `framed` — _persist)."""
    s = DOCS.get(w.get("id"))
    return bool(s.division.get("applied")) if s is not None else bool(w.get("framed"))


def _shown(w):
    """작업(work.json)의 보이는 이름(② §10 「목적 문서의 보이는 이름」·「별칭」·「프레임 이름」) — 과제에 묶인 목적 문서면 과제 이름을, 별칭이 있으면 「(별칭)」 을 뒤에 붙인 것,
    프로젝트 구성을 반영한 양식 맞추기 문서면 「<첨부 파일 종류>_<프로젝트>_프레임」, 아니면 올린 이름."""
    return works.shown_name(w.get("name"), w.get("task"), w.get("alias"), _framed(w))


def _shown_of(s):
    """세션의 보이는 이름 — 저장된 이름(s.name)은 올린 그대로다(이어 열기·양식 판정이 그것을 본다)."""
    w = works.work(s.id) or {}
    return works.shown_name(s.name, w.get("task"), w.get("alias"), bool(s.division.get("applied")))


def _save_name(shown, ext, w, framed, edited=True):
    """내려받는 편집본의 파일 이름(② §10) — 보이는 이름, 고친 것이면 「_수정」 꼬리. 프레임 이름은 올린 파일과 이미 다른 이름이라 꼬리를 안 붙인다(「프레임 이름」)."""
    if not edited or works.frame_stem((w or {}).get("task"), framed):
        return shown
    stem = shown[:-len(ext)] if shown.lower().endswith(ext) else shown
    return f"{stem}_수정{ext}"


def _work_view(w):
    """작업 요약(WORK_KEYS) — name 은 보이는 이름."""
    return {**{k: w.get(k) for k in WORK_KEYS}, "name": _shown(w)}


@app.get("/api/works")
def works_list():
    """작업 목록 — 최근 바뀐 차례. open = 지금 서버 메모리에 열려 있음."""
    return [{**_work_view(w), "open": w["id"] in DOCS} for w in works.list_works()]


@app.put("/api/works/{wid}/task")
def work_task(wid: str, body: dict = Body(...)):
    """{kind, file, job, project, round?} → {task, division?}. 프로젝트 아래 TASK·라운드별로 문서를 묶는다.
    다른 TASK 또는 라운드의 작업 분류는 바꾸지 않는다. 기존 round 없는 작업은 1라운드.
    round 를 안 보냈고 묶음(프로젝트·TASK)이 바뀌면 새 묶음에 이미 있는 다른 작업들의 최신 라운드로 둔다(없으면 번호 없음 = 1 — spec_작업 ② §10·§19).
    프로젝트가 바뀌어 이름 있는 프로젝트에 들어갔고 작업이 열려 있고 공유 중이면 division: adopted(프로젝트의 구분 기준을 받음) | seeded(이 문서의 값을 프로젝트에 올림) | none(둘 다 없음)."""
    return _work_task(wid, body)


def _work_task(wid, body, locked=False):
    """work_task 의 몸통. locked = 부르는 쪽이 projects.ROUND_LOCK 을 이미 잡음(work_start_task — 재진입이 안 되는 잠금이라 여기서 다시 잡지 않는다).
    round 를 안 보낸 요청은 최신 라운드를 읽어 적는 동안 ROUND_LOCK 을 잡는다(새 라운드·새 TASK 시작의 번호 배정과 같은 잠금) — 세션 잠금·저장은 그 밖에서."""
    t = {k: body.get(k) or "" for k in TASK}
    if any(t[k] not in TASK[k] for k in TASK) or not isinstance(body.get("project") or "", str):
        raise HTTPException(400, "모르는 작업 종류 값입니다")
    # 할 일과 작업 종류의 조합(spec_일반편집 ② §11): 작업 종류가 정해진 할 일(TASK_KIND — 문서 일반 편집 = general)은 그 종류여야 하고(비워도 안 됨 — 비우면 화면·프로젝트 구분 기준 공유가 연구개발로 본다),
    # 그 밖의 할 일은 연구개발(rnd) — 작업 종류를 비운 채 할 일만 남기는 것은 전처럼 된다
    if t["job"] and (t["kind"] != TASK_KIND[t["job"]] if t["job"] in TASK_KIND else t["kind"] not in ("", "rnd")):
        raise HTTPException(400, "이 TASK 와 작업 종류가 맞지 않습니다 — 작업 종류를 바꾸려면 TASK 를 먼저 비우세요")
    _work_or_404(wid)
    t["project"] = projects.normalize_name(body.get("project") or "")
    if "round" in body and (not isinstance(body["round"], int) or isinstance(body["round"], bool) or not 1 <= body["round"] <= 1000000):
        raise HTTPException(400, "라운드는 1 이상의 정수여야 합니다")

    def store():
        """라운드를 정해 work.json 에 적는다 → (전의 task, 들어가기 전 그 프로젝트의 기록 | None)."""
        old = _work_or_404(wid).get("task") or {}
        same = projects.group_key(old)[:2] == projects.group_key(t)[:2]
        if "round" in body or (same and "round" in old):
            t["round"] = body.get("round", projects.round_of(old) if same else 1)
        elif not same and t["project"]:   # 묶음이 바뀜 · round 안 보냄 → 새 묶음의 최신 라운드(자기 자신은 안 센다 — 다른 작업이 없거나 최신이 1 이면 전처럼 번호 없음 = 1)
            others = [projects.round_of(w.get("task")) for w in works.list_works()
                      if w["id"] != wid and projects.group_key(w.get("task"))[:2] == (t["project"], t["job"])]
            if others and max(others) > 1:
                t["round"] = max(others)
        record = None
        if t["project"]:
            try:
                record = projects.get(t["project"])
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
        if works.update(wid, task=t) is None:
            raise HTTPException(404, "그런 작업이 없습니다")
        return old, record

    if locked or "round" in body:
        old, record = store()
    else:
        with projects.ROUND_LOCK:
            old, record = store()
    out = {"task": t}
    s = DOCS.get(wid)
    if s is not None:
        with s.lock:
            sharing = _project_settings_sync(s)
            entered = bool(t["project"]) and projects.group_key(old)[0] != t["project"]   # 프로젝트가 바뀌어 이름 있는 프로젝트에 들어감
            if entered and sharing and sharing["shared"]:   # 들어감 알림의 근거(② §19) — 이전 라운드·일반 문서·세션 없음은 칸 없음
                out["division"] = "adopted" if record is not None else "seeded" if s.division.get("settings") is not None else "none"
        _persist_safe(s, force=True)
    return out


@app.put("/api/works/{wid}/alias")
def work_alias(wid: str, body: dict = Body(...)):
    """{alias} → {alias, name}. 별칭(② §10 「별칭」) — 보이는 이름의 확장자 앞에 「(별칭)」. 빈 글 = 지움. 올린 이름(work.json name)은 그대로."""
    try:
        alias = works.normalize_alias(body.get("alias", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if len(alias) > works.ALIAS_MAX:
        raise HTTPException(400, f"별칭은 {works.ALIAS_MAX}자까지입니다")
    old = _work_or_404(wid).get("alias") or ""
    w = works.update(wid, alias=alias) if alias else works.update(wid, alias=None)
    if w is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    if alias != old:
        works.log(wid, "alias", old=old, new=alias)
    return {"alias": alias, "name": _shown(w)}


@app.get("/api/projects")
def projects_list():
    try:
        return {"projects": projects.listing()}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def _project_found(name):
    """ROUND_LOCK 안. (정규화한 이름, 그 프로젝트의 작업들, 전체 작업). 저장 파일이 깨졌으면 아무것도 바꾸기 전에 409, 없는 프로젝트는 404."""
    project = projects.normalize_name(name)
    try:
        record = projects.get(project)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    rows = works.list_works()
    members = [w for w in rows if projects.group_key(w.get("task"))[0] == project]
    if not project or (record is None and not members):
        raise HTTPException(404, "그런 프로젝트가 없습니다")
    return project, members, rows


def _project_sessions_refresh(ids):
    """task.project 가 바뀐 작업 중 열려 있는 세션을 새 소속에 맞추고 저장한다."""
    for wid in ids:
        s = DOCS.get(wid)
        if s is None:
            continue
        with s.lock:
            _project_settings_sync(s)
        _persist_safe(s, force=True)


def _task_options_follow(fn, *args):
    """TASK 옵션(TASK 묶음마다의 저장소 app/task_options.py — spec_구역 ② §1 「TASK 옵션 — TASK 묶음마다」)의 묶음 열쇠를 프로젝트 이름 변경 · 삭제 · 새 라운드에 맞춘다
    (fn = rename_project | drop_project | copy_round). 못 해도 본 일은 막지 않는다 — 옵션이 기본값으로 보일 뿐이다. 실패는 서버 로그에 남긴다."""
    try:
        from app import task_options
        return getattr(task_options, fn)(*args)
    except Exception as exc:  # noqa: BLE001
        log.warning("[TASK 옵션] %s%r 을 하지 못함: %r", fn, args, exc)
        return None


@app.put("/api/projects/{name:path}")
def project_rename(name: str, body: dict = Body(...)):
    """{name}. 프로젝트의 모든 TASK·라운드 작업과 공유 구분 기준을 새 이름으로 옮긴다(spec_작업 ② §17). 이미 쓰는 이름과는 합치지 않는다 — 라운드 번호가 겹친다."""
    new = body.get("name")
    if not isinstance(new, str) or not projects.normalize_name(new):
        raise HTTPException(400, "새 프로젝트 이름을 입력하세요")
    new = projects.normalize_name(new)
    with projects.ROUND_LOCK:
        old, members, rows = _project_found(name)
        if new == old:
            return {"name": old, "works": []}
        if projects.get(new) is not None or any(projects.group_key(w.get("task"))[0] == new for w in rows):
            raise HTTPException(409, "같은 이름의 프로젝트가 이미 있습니다. 프로젝트는 합치지 않습니다")
        changed = []
        for w in members:  # 작업 먼저 — 기록을 먼저 옮기면 열린 세션이 옛 이름으로 기록을 다시 만든다
            if works.update(w["id"], task={**w["task"], "project": new}) is not None:
                works.log(w["id"], "renameProject", old=old, new=new)
                changed.append(w["id"])
        projects.rename(old, new)
        _task_options_follow("rename_project", old, new)   # 그 프로젝트 묶음들의 TASK 옵션도 새 이름으로
        _project_sessions_refresh(changed)
        return {"name": new, "works": changed}


@app.delete("/api/projects/{name:path}")
def project_delete(name: str, docs: str = "keep"):
    """docs=keep: 문서는 남기고 프로젝트만 해제 · docs=delete: 문서까지 삭제(spec_작업 ② §17). 둘 다 공유 구분 기준 기록을 지운다.
    docs=reset: 프로젝트 구성 초기화 — 문서·소속은 그대로 두고 프로젝트 기록(구성 값·확정·버전)과, 그 구성을 공유하던 작업들의 구성 입력·확정·변경 계획을 비운다
    → {name, docs: "reset", works: 비운 작업, skipped: 못 열어 건너뛴 작업}."""
    if docs not in ("keep", "delete", "reset"):
        raise HTTPException(400, "docs 는 keep · delete · reset 가운데 하나여야 합니다")
    with projects.ROUND_LOCK:
        project, members, _ = _project_found(name)
        ids = [w["id"] for w in members]
        if docs == "reset":
            done, skipped = _project_reset(project, members)
            return {"name": project, "docs": docs, "works": done, "skipped": skipped}
        if docs == "delete":
            for wid in ids:  # 작업 하나 지우기(work_delete)와 같은 방식
                DOCS.pop(wid, None)
                works.delete(wid)
        else:
            for w in members:
                task = {k: v for k, v in w["task"].items() if k != "round"}
                task["project"] = ""
                if works.update(w["id"], task=task) is not None:
                    works.log(w["id"], "leaveProject", project=project)
            _project_sessions_refresh(ids)
        projects.remove(project)
        _task_options_follow("drop_project", project)   # 프로젝트가 없어졌다(해제 · 문서까지 삭제) — 그 프로젝트 묶음들의 TASK 옵션도 지운다: 남기면 같은 이름으로 다시 만든 프로젝트가 옛 옵션을 물려받는다. 구성 초기화(reset)는 남긴다(spec_구역 ② §1)
        return {"name": project, "docs": docs, "works": ids}


def _project_reset(project, members):
    """ROUND_LOCK 안. 프로젝트 구성 초기화(spec_작업 ② §17) → (비운 작업 id 들, 못 열어 건너뛴 작업 id 들).
    그 구성을 공유하던 작업(TASK 마다 최신 라운드 · 일반 문서 제외 — _project_settings_sync 의 shared 와 같은 조건)의 구성 입력·확정·변경 계획을 비운 **뒤에** 프로젝트 기록을 지운다
    — 기록을 먼저 지우면 값이 남은 세션의 다음 _project_settings_sync 가 그 값을 프로젝트로 다시 올린다(seed).
    문서 내용 · task(소속·TASK·라운드) · 반영 기록(applied) · hints · review · 이전 라운드 작업은 그대로. 닫힌 작업도 열어서 비운다."""
    latest = {}
    for w in members:
        job = projects.group_key(w.get("task"))[1]
        latest[job] = max(latest.get(job, 0), projects.round_of(w.get("task")))
    shared = [w["id"] for w in members if projects.round_of(w.get("task")) == latest[projects.group_key(w.get("task"))[1]]
              and (w.get("task") or {}).get("kind") != "general"]

    def clear(wid):
        """세션의 구성 입력·확정·계획을 비우고 저장 → 비울 것이 있었나."""
        s = _sess(wid)
        with s.lock:
            d = s.division
            if d.get("settings") is None and d.get("confirmed") is None and d.get("plan") is None:
                return False
            d["settings"] = d["confirmed"] = d["plan"] = None
            s.saved_rev = -1   # 문서 rev 가 같아도 비운 입력은 작업에 남긴다(_project_settings_sync 와 같은 표시)
        _persist_safe(s, force=True)
        return True

    done, skipped = [], []
    for wid in shared:
        try:
            clear(wid)
        except Exception as exc:  # noqa: BLE001 — 못 여는 작업(폴더 깨짐 등)은 건너뛴다. 못 여는 동안은 값을 프로젝트로 올리지도 못한다
            log.warning("[프로젝트 구성 초기화] %s 작업 %s 를 열지 못해 건너뜀: %r", project, wid, exc)
            skipped.append(wid)
            continue
        works.log(wid, "resetProject", project=project)
        done.append(wid)
    projects.remove(project)
    again = False
    for wid in done:   # 비우는 사이에 다른 요청이 그 세션에 프로젝트 값을 다시 받아 놓았으면(기록을 지우기 전의 동기화) 한 번 더 비운다
        try:
            again = clear(wid) or again
        except Exception:  # noqa: BLE001
            pass
    if again:
        projects.remove(project)
    return done, skipped


def _freeze_latest_project_round(project, job, rows):
    """ROUND_LOCK 안. 새 번호 배정 전에 현재 최신 라운드의 공유 입력을 고정한다."""
    members = [w for w in rows if projects.group_key(w.get("task"))[:2] == (project, job)]
    latest = max((projects.round_of(w.get("task")) for w in members), default=0)
    for member in members:
        if projects.round_of(member.get("task")) == latest:
            session = _sess(member["id"])
            with session.lock:
                _project_settings_sync(session)
            _persist(session, force=True)
    return latest


@app.post("/api/works/{wid}/start-task")
def work_start_task(wid: str, body: dict = Body(...)):
    """새로 올린 무소속 문서를 프로젝트의 다음 TASK 라운드로 배정한다."""
    project, job, role = body.get("project"), body.get("job"), body.get("file", "")
    if not isinstance(project, str) or not projects.normalize_name(project):
        raise HTTPException(400, "프로젝트 이름을 먼저 입력하세요")
    if not isinstance(job, str) or not job or job not in TASK["job"] or role not in TASK["file"]:
        raise HTTPException(400, "모르는 TASK 또는 문서 종류입니다")
    project = projects.normalize_name(project)
    with projects.ROUND_LOCK:
        work = _work_or_404(wid)
        if work.get("source") != "upload" or projects.group_key(work.get("task"))[0]:
            raise HTTPException(409, "새로 올린 무소속 문서로 시작하세요. 기존 프로젝트 작업은 그대로 보관합니다")
        latest = _freeze_latest_project_round(project, job, works.list_works())
        result = _work_task(wid, {"kind": TASK_KIND.get(job, "rnd"), "file": role, "job": job, "project": project, "round": latest + 1}, locked=True)
        works.log(wid, "startTask", project=project, job=job, round=latest + 1)
        return {**result, "docId": wid, "round": latest + 1}


def _round_uploaded_original(member):
    """수정본에서 갈라진 라운드도 최초 업로드 원본으로 돌아간다."""
    current, seen = member, set()
    while True:
        wid = current["id"]
        if wid in seen or current.get("format") != member.get("format"):
            raise HTTPException(409, "라운드의 원본 연결 정보를 확인할 수 없습니다")
        seen.add(wid)
        parent = current.get("roundParent")
        if not parent:
            path = works.file_path(wid, "original")
            if path is None:
                raise HTTPException(409, "처음 올린 원본 파일을 읽지 못했습니다")
            return path.read_bytes()
        current = works.work(parent)
        if current is None:
            raise HTTPException(409, "처음 올린 원본이 있는 이전 라운드를 찾지 못했습니다")


@app.post("/api/works/{wid}/round")
def work_round(wid: str, body: dict = Body(default={})):
    """기존 라운드의 문서들을 보존하고, 그 그룹 전체를 새 라운드로 복사한다."""
    source = body.get("source", "original")
    if source not in ("current", "original"):
        raise HTTPException(400, "라운드 시작 문서는 current 또는 original 입니다")
    if not works.enabled():
        raise HTTPException(400, "작업 저장을 켠 뒤 라운드를 만들 수 있습니다")
    with projects.ROUND_LOCK:
        work = _work_or_404(wid)
        task = work.get("task") or {}
        project, job, number = projects.group_key(task)
        if not project or not job:
            raise HTTPException(400, "프로젝트와 TASK를 먼저 선택하세요")
        rows = works.list_works()
        members = [w for w in rows if projects.group_key(w.get("task")) == (project, job, number)]
        next_round = _freeze_latest_project_round(project, job, rows) + 1
        prepared = []
        for member in members:
            original_session = _sess(member["id"])
            with original_session.lock:
                _project_settings_sync(original_session)
                if source == "current":
                    data = original_session.doc.save()
                    applied = copy.deepcopy(original_session.division.get("applied"))
                    if applied:
                        applied.update(rev=0, inheritedFrom=member["id"])  # 새 문서의 기준은 지금 구조: 이전 rev를 들고 오면 새 분석이 늘 오래된 것으로 보인다.
                else:
                    data, applied = _round_uploaded_original(member), None
                local_settings = copy.deepcopy(original_session.division.get("settings"))
            _persist(original_session, force=True)  # 새 최대 round가 생기기 전에 이전 설정을 고정한다.
            fresh = Session(member["name"], data)
            try:
                shared_settings = projects.settings(project)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            fresh.division["settings"] = shared_settings or local_settings
            fresh.division["applied"] = applied
            prepared.append((member, fresh, data))
        created, mapping = [], {}
        try:
            for member, fresh, data in prepared:
                _admit(fresh)
                created.append(fresh.id)
                new_work = works.create(fresh.id, fresh.name, fresh.fmt, data, "round")
                fresh.doc_key = new_work["sha256"]
                new_task = {**(member.get("task") or {}), "round": next_round}
                works.update(fresh.id, task=new_task, roundParent=member["id"], **({"alias": member["alias"]} if member.get("alias") else {}))  # 별칭은 이어받는다(② §10)
                from app import heading_forms
                form_choice = heading_forms.choice(member["id"])
                if form_choice is not None:
                    heading_forms.set_choice(fresh.id, form_choice)
                mapping[member["id"]] = fresh.id
                _persist(fresh, force=True)
                works.log(fresh.id, "round", fromWork=member["id"], source=source, round=next_round)
            # 취합의 참조 선택만 복사하고 분석·반영 기록은 새 라운드에서 시작한다.
            from app import merge_gather_api
            for member, fresh, data in prepared:
                if (member.get("task") or {}).get("file") == "plan" and job == "plan_merge":
                    old_gather = merge_gather_api._store(member["id"])
                    for part in old_gather.get("order") or []:
                        if part in mapping:
                            record = old_gather["parts"].get(part) or {}
                            merge_gather_api.gather_part_put(fresh.id, mapping[part], {"orgs": record.get("orgs") or [], "common": record.get("common", True)})
        except Exception:
            for created_id in created:
                DOCS.pop(created_id, None)
                works.delete(created_id)
            raise
        _task_options_follow("copy_round", task, {**task, "round": next_round})   # 앞 라운드 묶음의 TASK 옵션을 새 묶음이 이어받는다(묶음에 한 번 — 문서들의 task 는 프로젝트·TASK·라운드가 같다). 지정·출처는 안 옮긴다(블록 id 가 새로 매겨진다)
        _ensure_persister()
        for member, fresh, data in prepared:
            if DOCS.get(fresh.id) is fresh:
                _start(fresh, "import", verify.run_import)
        return {"docId": mapping[wid], "round": next_round, "sourceRound": number, "source": source,
                "works": [_work_view(works.work(new_id)) for new_id in mapping.values()], "mapping": mapping}


@app.get("/api/works/{wid}/log")
def work_log(wid: str):
    w = _work_or_404(wid)
    return {"work": _work_view(w), "events": works.events(wid), "runs": works.runs(wid)}


@app.get("/api/works/{wid}/headings-preview")
def work_headings_preview(wid: str):
    """비교용 읽기 전용 스냅샷 — 닫힌 문서를 다시 열거나 추출·검증하지 않는다."""
    from app import heading_compare
    result = heading_compare.preview(wid, DOCS.get(wid), WORK_KEYS)
    if result is None:
        raise HTTPException(404, "그런 작업이 없습니다")
    if isinstance(result.get("work"), dict):
        result["work"]["name"] = _shown(works.work(wid) or result["work"])   # 보이는 이름(② §10) — 작업 전체에서(프레임 표시 framed 는 WORK_KEYS 밖)
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
    # 올린 원본은 올린 이름 그대로, 편집본은 보이는 이름(② §10 「목적 문서의 보이는 이름」)에 꼬리(프레임 이름은 꼬리 없이)
    name = w["name"] if which == "original" or p.name.startswith("original.") else _save_name(_shown(w), "." + w["format"], w, _framed(w))
    return FileResponse(p, media_type=FORMATS[w["format"]]["mime"], filename=name)


@app.delete("/api/works/{wid}")
def work_delete(wid: str):
    s = DOCS.pop(wid, None)
    gone = works.delete(wid)
    if s is None and not gone:
        raise HTTPException(404, "그런 작업이 없습니다")
    return {"ok": True}


# ---- 확정(spec_작업 ② §8) — 고친 문단을 깃처럼: 확정 = 지금 상태를 한 시점으로 남기고 새 기준으로 · 확정 기록 · 버리기 · 이전 확정으로 복원 ----------

COMMIT_KINDS = ("text", "format", "struct", "new", "removed")
COMMIT_KEYS = ("n", "at", "message", "sha256", "size", "counts", "restoreOf")


def _commits_on():
    if not works.enabled():
        raise HTTPException(400, "작업 저장이 꺼져 있어 확정 기능을 쓸 수 없습니다")


def _dirty(s):
    """확정하지 않은 변경이 있는지 — 고친 문단이 있거나 저장 바이트가 기준과 다름."""
    return bool(s.edited()) or not s.pristine_file()


def _commit_changes(s):
    """기준 대비 변경 목록 [{id, kind, before, after}] — 문서 차례, 지운 문단은 끝에(세션 잠금 안)."""
    kinds = s.kinds()
    order = [i for i in s.texts if i in kinds] + [i for i in s.orig_texts if i in kinds and i not in s.texts]
    order += [i for i in kinds if i not in s.texts and i not in s.orig_texts]
    return [{"id": i, "kind": kinds[i], "before": s.orig_texts.get(i), "after": None if kinds[i] == "removed" else s.texts.get(i)}
            for i in order]


def _commit_counts(changes):
    c = dict.fromkeys(COMMIT_KINDS, 0)
    for x in changes:
        c[x["kind"]] = c.get(x["kind"], 0) + 1
    return {**c, "total": len(changes)}


def _open_at(s, data, ids):
    """(data, ids) 를 새로 연 문서와 그 블록 id 자리표(None = 올린 원본: blocks() 차례) — 번호표는 지금 세션 것보다 줄이지 않는다
    (되돌린 뒤 새 문단이 옛 id 를 다시 쓰지 않게 — id 로 묶인 표 지침·추가한 자리가 다른 블록에 붙지 않는다)."""
    doc = s.kit["cls"](data)
    if ids is not None and not doc.adopt_ids(ids):
        raise RuntimeError("블록 id 자리표가 그 확정의 문서와 맞지 않습니다")
    doc.blocks()  # 모든 블록에 id — 자리표에서 빠지는 요소가 없게
    doc._n = max(doc._n, s.doc._n)
    return doc, doc.id_state()


def _rebase(s, data, doc, ids, n, same=False):
    """세션의 기준을 (바이트 data, 그것을 연 문서 doc, 블록 id 자리표 ids, 확정 번호 n) 으로 — 세션 잠금 안에서. 고침 집합·실행 취소를 비운다.
    검증 결과·PDF·매핑은 옛 기준의 것이라 내린다(부른 쪽이 가져오기 검증을 다시 시작) — 돌던 검증은 gen 으로 끊는다(_JobView).
    same = 기준 바이트·블록 id 가 그대로(버리기): 기준 쪽 결과(가져오기 검증·기준 PDF·쪽 매핑·표준 기준선)는 그대로 쓰고, 지난 출력파일 검증은
    편집 차례(rev)가 달라 화면이 「검증 전」으로 본다 — 큰 문서에서 한글 PDF 를 다시 찍지 않는다."""
    blocks = doc.blocks()
    with s.glock:
        if not same:
            s.gen += 1
            s.owpml_base = None
            s.rebuilt, s.mapping, s.mapping_edited, s.pdf, s.jobs = None, None, None, {}, {}
        s.original, s.base_ids, s.base_n = data, ids, n
        s.doc, s.blocks = doc, blocks
        s.orig_texts = verify.flat_texts(blocks)
        s.texts = dict(s.orig_texts)
        s.unrestored, s.formatted, s.struct, s.removed, s.origin = set(), set(), set(), set(), {}
        s.pristine, s.undo = None, []
    s.division["plan"] = None  # 계획의 사본 문서는 옛 기준 위의 것 — 다시 계획


def _commit_view(c):
    return {k: c.get(k) for k in COMMIT_KEYS}


def _commit_zero(w):
    """올린 원본 = 확정 0(확정 기록 맨 아래)."""
    return {"n": 0, "at": w.get("created"), "message": "올린 원본", "sha256": w.get("sha256"), "size": w.get("size"), "counts": None, "restoreOf": None}


from app import edit_detail  # noqa: E402

DETAIL_KINDS = ("format", "struct")   # 모양이 바뀌었을 수 있는 고친 문단 — 글만 고친 문단(text)은 화면이 원래 글로 그린다


@app.get("/api/docs/{doc_id}/edits/detail")
def edits_detail(doc_id: str, limit: int = 300, ids: str = ""):
    """고친 문단이 어떻게 바뀌었나(② §8 「화면」 — 깃 diff 처럼): 모양이 바뀐 문단마다 모양 값의 기준 → 지금 [{key, label, before, after, part?}].
    문서 차례 앞 limit 개 · 읽기만(_bump 없음). 같은 편집 차례·기준이면 한 번 센 것을 돌려준다(지금 블록 읽기가 큰 문서에서 1 s 안팎).
    ids = 쉼표로 이은 문단 id — 있으면 앞 limit 개 대신 **그 문단들만**(문서의 「고친 곳 보기」 가 창에 보이는 문단만 묻는다 — ② §8 「문서에서」).
    모양이 바뀐 문단이 아닌 id 는 답에 없다. 두 블록 색인은 같은 차례·기준에서 한 번만 만든다(창을 옮길 때마다 다시 읽지 않게)."""
    s = _sess(doc_id)
    limit = max(1, min(int(limit), 2000))
    want = [i for i in dict.fromkeys(x.strip() for x in ids.split(",")) if i][:2000] if ids else None
    with s.lock:
        stamp = (s.rev, s.base_n, id(s.blocks))
        memo = getattr(s, "edit_detail_memo", None)
        if not isinstance(memo, dict) or memo.get("stamp") != stamp:
            memo = s.edit_detail_memo = {"stamp": stamp, "index": None, "outs": {}}
        if want is None and limit in memo["outs"]:
            return memo["outs"][limit]
        kinds = s.kinds()
        changed = [i for i in s.texts if kinds.get(i) in DETAIL_KINDS]
        items = {}
        if changed:
            if memo["index"] is None:
                memo["index"] = (edit_detail.index(s.blocks), edit_detail.index(s.doc.blocks()))
            base, now = memo["index"]
            pick = changed[:limit] if want is None else [i for i in want if kinds.get(i) in DETAIL_KINDS and i in s.texts]
            items = {i: edit_detail.changes(base.get(i), now.get(i), word=s.fmt == "docx") for i in pick}
        out = {"rev": s.rev, "base": s.base_n, "items": items, "more": max(0, len(changed) - limit) if want is None else 0}
        if want is None:
            memo["outs"][limit] = out
    return out


@app.get("/api/docs/{doc_id}/commits")
def commits_list(doc_id: str):
    """확정 기록 — 최근 것부터, 끝에 올린 원본(n 0). base = 지금 기준, edited = 확정하지 않은 고친 문단 수."""
    s = _sess(doc_id)
    w = works.work(doc_id) or {"created": s.created, "size": len(s.original), "sha256": s.doc_key}
    with s.lock:
        base, edited = s.base_n, len(s.edited())
    return {"base": base, "edited": edited, "enabled": works.enabled(),
            "commits": [_commit_view(c) for c in reversed(works.commits(doc_id))] + [_commit_zero(w)]}


@app.post("/api/docs/{doc_id}/commits")
def commit_create(doc_id: str, body: dict = Body(default={})):
    """확정 {message?} — 지금 편집 상태 전체를 한 시점으로 남기고 새 기준으로. 문서 글·블록 id 는 그대로(응답 = GET /api/docs/{id} + commit).
    실행 취소 기록·구분 기준 계획·지난 검증 결과는 비우고 가져오기 검증을 새 기준으로 다시 돈다. 편집 차례(rev)는 그대로."""
    _commits_on()
    message = body.get("message") or ""
    if not isinstance(message, str):
        raise HTTPException(400, "message 는 글이어야 합니다")
    message = " ".join(message.split())[:200]
    s = _sess(doc_id)
    with s.lock:
        if not _dirty(s):
            raise HTTPException(400, "확정할 변경이 없습니다")
        s.doc.blocks()  # 모든 블록에 id 를 붙여 둔다 — 자리표에서 빠지는 요소가 없게
        data = s.doc.save()
        changes = _commit_changes(s)
        counts = _commit_counts(changes)
        try:
            doc, ids = _open_at(s, data, s.doc.id_state())  # 확정본을 다시 연 문서 = 새 기준(같은 블록 id)
            extra = {"ids": ids, "division": s.division["applied"], "outline": s.outline, "changes": changes}
            c = works.add_commit(s.id, s.fmt, data, {"message": message, "counts": counts, "parent": s.base_n}, extra)
        except (OSError, TypeError, ValueError, RuntimeError) as e:
            raise HTTPException(500, f"확정을 작업 폴더에 쓰지 못했습니다: {e}") from e
        if c is None:
            raise HTTPException(404, "작업 폴더가 없습니다(지운 작업)")
        _rebase(s, data, doc, ids, c["n"])
        works.log(s.id, "commit", rev=s.rev, n=c["n"], message=message, counts=counts, sha256=c["sha256"])
        _start(s, "import", verify.run_import)  # 새 기준의 PDF·쪽 매핑·표준 검사 기준선
    _persist_safe(s, force=True)  # rev 는 그대로지만 기준(base)이 바뀌었다
    return {**get_doc(doc_id), "commit": _commit_view(c)}  # 화면은 다시 그리지 않고 블록 표·원래 글만 새 기준으로 바꾼다


@app.post("/api/docs/{doc_id}/commits/{n}/restore")
def commit_restore(doc_id: str, n: int, body: dict = Body(default={})):
    """확정 n(0 = 올린 원본) 상태로 되돌린다 {discard?}. n 이 지금 기준이면 「모두 되돌리기」(전 이름 「버리기」 — 확정하지 않은 변경만 버림 — 확정이 새로 안 생김),
    아니면 그 상태를 새 확정으로 남긴다(기록은 한 줄로만 자람). 확정하지 않은 변경이 있으면 discard 가 있어야(409). 응답 = GET /api/docs/{id} + commit."""
    _commits_on()
    s = _sess(doc_id)
    with s.lock:
        dirty, count = _dirty(s), len(s.edited())
        if n == s.base_n and not dirty:
            raise HTTPException(400, "이미 그 확정 상태입니다")
        if dirty and not body.get("discard"):
            raise HTTPException(409, f"확정하지 않은 변경이 있습니다(고친 문단 {count}개) — 먼저 확정하거나 버리세요")
        c = None
        extra = (works.commit_data(s.id, n) or {}) if n else {}
        try:
            if n == s.base_n:  # 버리기 — 기준 그대로, 문서만 기준 상태로
                data = s.original
                doc, ids = _open_at(s, data, s.base_ids)
            else:
                data = works.commit_bytes(s.id, n)
                if data is None or (n and not isinstance(extra.get("ids"), dict)):
                    raise HTTPException(404, "그 확정이 없거나 파일을 읽지 못했습니다")
                doc, ids = _open_at(s, data, extra.get("ids"))
                meta = {"message": f"확정 {n} 로 복원" if n else "올린 원본으로 복원", "counts": None, "parent": s.base_n, "restoreOf": n}
                c = works.add_commit(s.id, s.fmt, data, meta, {"ids": ids, "division": extra.get("division"), "outline": extra.get("outline"),
                                                                "changes": []})
                if c is None:
                    raise HTTPException(404, "작업 폴더가 없습니다(지운 작업)")
        except (OSError, TypeError, ValueError, RuntimeError) as e:
            raise HTTPException(500, f"그 확정 상태로 되돌리지 못했습니다: {e}") from e
        _rebase(s, data, doc, ids, c["n"] if c else n, same=c is None)
        _commit_state(s, extra)
        s.division["hints"] = [h for h in s.division.get("hints") or []  # 추가한 자리는 그 문단이 되돌린 문서에 있는 것만
                               if s.doc._attached(s.doc._ids.get(h.get("para")))]
        __import__("app.zones_api", fromlist=["prune"]).prune(s)   # 편집 구역의 지정·출처도 되돌린 문서에 있는 블록만(spec_구역 ② §3 「지정 — 사람이 고른 블록」)
        _outline_sync(s)
        s.owpml_last = None
        if c:
            _bump(s, "restore", n=c["n"], of=n, discarded=count)
        else:
            _bump(s, "discard", base=n, count=count)
        if "import" not in s.jobs:  # 기준이 바뀜(복원) — 새 기준의 PDF·쪽 매핑. 버리기는 기준이 그대로라 지난 가져오기 검증을 그대로 쓴다
            _start(s, "import", verify.run_import)
    _persist_safe(s, force=True)
    return {**get_doc(doc_id), "commit": _commit_view(c) if c else None}


@app.get("/api/works/{wid}/commits/{n}")
def commit_detail(wid: str, n: int, limit: int = 200):
    """확정 하나의 요약 + 변경 목록(앞 limit 개, more = 남은 수)."""
    w = _work_or_404(wid)
    if n == 0:
        return {**_commit_zero(w), "changes": [], "more": 0}
    c = works.commit(wid, n)
    if c is None:
        raise HTTPException(404, "그 확정이 없습니다")
    changes = (works.commit_data(wid, n) or {}).get("changes") or []
    limit = max(1, min(limit, 2000))
    return {**_commit_view(c), "changes": changes[:limit], "more": max(0, len(changes) - limit)}


@app.get("/api/works/{wid}/commits/{n}/file")
def commit_file(wid: str, n: int):
    """그 확정의 파일 — 0 = 올린 원본(이름 그대로), 그 밖은 <이름>_확정<n>.<ext>."""
    w = _work_or_404(wid)
    p = works.commit_path(wid, n)
    if p is None:
        raise HTTPException(404, "그 확정의 파일이 없습니다")
    ext, shown = "." + w["format"], _shown(w)   # 0 = 올린 파일 그대로, 그 밖은 보이는 이름(② §10)에 꼬리
    stem = shown[:-len(ext)] if shown.lower().endswith(ext) else shown
    return FileResponse(p, media_type=FORMATS[w["format"]]["mime"], filename=w["name"] if n == 0 else f"{stem}_확정{n}{ext}")


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
    """{stage: 1|2|3, llm: bool} — 뒤 스레드로 시작(돌고 있으면 409). 3 = 표 구조(spec_헤딩_추출 ② §8).
    {first: true} = 첫 분석(spec_작업 ② §9) — 2단계 → 3단계를 스크립트만으로 한 작업에(이미 결과가 있는 단계는 건너뜀), stage·llm 은 안 본다.
    {stage: 2, llm: true, skill?} = 「헤딩 그래프(LLM)」 — 헤딩 판정이 끝나면 **이어서** 서식이 여러 가지인 템플릿마다 서식 정리 계획을 받는다(이어 돌리기 "heads" — app/analysis_llm.py:
    2026-11-16 사용자 답 「헤딩 LLM 판정에 늘 이어서」). 계획만 받는다 — 문서는 안 바뀐다. skill = 서식 정리 스킬 키(기본 "tidy" · 없는 키면 404)."""
    s = _sess(doc_id)
    _heads_hwpx(s)
    first = body.get("first") is True
    stage, use_llm = (3, False) if first else (body.get("stage", 1), body.get("llm", False))
    if type(stage) is not int or stage not in (1, 2, 3):  # true·1.0·"1" 은 거절
        raise HTTPException(400, "stage 는 1·2·3")
    if not isinstance(use_llm, bool):  # "false" 를 참으로 읽어 LLM 을 돌리지 않게
        raise HTTPException(400, "llm 은 true 또는 false")
    if stage == 2 and use_llm:
        from app import analysis_api
        return analysis_api.start_chain(s, "heads", body.get("skill")).view()
    try:
        job = heading_runs.start(s, stage, use_llm, **({"first": True} if first else {}))
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

# ---- 양식 정보 끝점은 app/heading_forms_api.py(양식마다 md 하나 — 일반 지침과 따로, spec_헤딩_추출 ② §12) ----------------------------------------
from app import heading_forms_api  # noqa: E402

app.include_router(heading_forms_api.router)

# ---- 구분 라벨 지정 끝점은 app/heading_labels_api.py(괄호 줄 → 구분 라벨·괄호 소제목, spec_헤딩_추출 ② §13) ----------------------------------------
from app import heading_labels_api  # noqa: E402

app.include_router(heading_labels_api.router)

# ---- TEMP 라벨 끝점은 app/heading_temp_api.py(표 안 작성요령·쓸 자리 — 목록·지정/해제·문서에서 지우기, spec_헤딩_추출 ② §15) ----------------------------------------
from app import heading_temp_api  # noqa: E402

app.include_router(heading_temp_api.router)

# ---- 개요 줄 자리 규칙 끝점은 app/outline_format_api.py(템플릿 레벨의 레터 위치·둘째 줄 — 그 레벨 줄 모두에 적용, spec_hwpx_웹편집 ② §8-1) ----------------------------------------
from app import outline_format_api  # noqa: E402

app.include_router(outline_format_api.router)

# ---- 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속 끝점은 app/outline_match_api.py(spec_hwpx_웹편집 ② §8-2) ----------------------------------------
from app import outline_match_api  # noqa: E402

app.include_router(outline_match_api.router)
app.include_router(__import__("app.outline_lift_api", fromlist=["router"]).router)   # 표 제목을 템플릿의 L1 으로(후보 · 넣기 · 떼기) 끝점은 app/outline_lift_api.py(spec_hwpx_웹편집 ② §8-7)
app.include_router(__import__("app.outline_grow_api", fromlist=["router"]).router)   # 개요 레벨 더하기(마지막 레벨의 Alt+↓ — 후보 · 새 레벨) 끝점은 app/outline_grow_api.py(spec_hwpx_웹편집 ② §8-6)
app.include_router(__import__("app.para_letter_api", fromlist=["router"]).router)   # 레터 넣기(도구 줄 「문단 수정」 묶음 — 메뉴 · 레터만/개요 레벨로/빼기) 끝점은 app/para_letter_api.py(spec_hwpx_웹편집 ② §8-9)
app.include_router(__import__("app.caption_tpl_api", fromlist=["router"]).router)   # 캡션 템플릿 「CN」(그림 아래 · 표 위 캡션 — 템플릿 · 대표 정하기 · 대표에 맞추기) 끝점은 app/caption_tpl_api.py(spec_hwpx_웹편집 ② §8-10)
app.include_router(__import__("app.division_scan_api", fromlist=["router"]).router)   # 구분 기준 판독(연구개발과제 문서 — 헤딩 추출 앞 · 지연 계산 · 다시 판독) 끝점은 app/division_scan_api.py(spec_구분_기준 ② §23)
app.include_router(__import__("app.work_guide_api", fromlist=["router"]).router)   # 작업 진행 에이전트(진행 턴 · 카드의 끝 · 첫 화면) 끝점은 app/work_guide_api.py(spec_작업에이전트 ② §4)
app.include_router(__import__("app.agents_api", fromlist=["router"]).router)   # 에이전트 설정(등록부 · 작업 번호·역할·모델·생각 깊이 · 프롬프트 구성 · 실행 기록) 끝점은 app/agents_api.py(spec_에이전트 ② §3)
app.include_router(__import__("app.tpl_agent_api", fromlist=["router"]).router)   # 템플릿 서식 정리 에이전트(스킬 저장 · 계획 받기 — Opus 5.5) 끝점은 app/tpl_agent_api.py(spec_hwpx_웹편집 ② §8-4)
app.include_router(__import__("app.workflow_api", fromlist=["router"]).router)   # TASK 워크플로우(GET /api/workflow · 페이지 GET /workflow — 등록부 app/workflow.py) 끝점은 app/workflow_api.py(spec_워크플로우 ② §2)
app.include_router(__import__("app.analysis_api", fromlist=["router"]).router)   # 분석 상태(GET /api/docs/{id}/analysis — 헤딩 · 표 · LLM · 구분 기준이 어디까지 됐나) 끝점은 app/analysis_api.py(spec_작업 ② §20)
app.include_router(__import__("app.heading_llm_diff_api", fromlist=["router"]).router)   # LLM 이 바꾼 것(GET /api/docs/{id}/headings/llm-changes — 규칙 보강 · 헤딩 판정 · 표 판정 · 서식 계획) 끝점은 app/heading_llm_diff_api.py(spec_헤딩_추출 ② §7)

# ---- 뼈대 유지 끝점은 app/heading_drift_api.py(문서가 바뀌어도 2·3단계를 다시 만들라고 하지 않고 새 레터·새 서식·새 표만 알림, spec_헤딩_추출 ② §17) ----------------------------------------
from app import heading_drift_api  # noqa: E402

app.include_router(heading_drift_api.router)

# ---- 병합 — 자리 연결 끝점은 app/merge_api.py(spec_병합 ② §8) ----
from app import merge_api  # noqa: E402

app.include_router(merge_api.router)
app.include_router(__import__("app.merge_over_api", fromlist=["router"]).router)   # 넘친 개요 레벨(덮은 템플릿 · 수정 · 다른 템플릿 · 다시 맞추기) 끝점은 app/merge_over_api.py(spec_병합 ② §5-5 8)
app.include_router(__import__("app.merge_gather_api", fromlist=["router"]).router)   # 취합 끝점은 app/merge_gather_api.py(spec_취합 ② §6)
app.include_router(__import__("app.zones_api", fromlist=["router"]).router)   # 편집 구역(기관·단계·차년도 값마다의 구역 — 자동 판독 · 지정 · 취합 출처) 끝점은 app/zones_api.py(spec_구역 ② §5)
app.include_router(__import__("app.task_options_api", fromlist=["router"]).router)   # TASK 옵션(TASK 묶음마다 — 편집 구역이 보이는 기준) 끝점은 app/task_options_api.py(spec_구역 ② §1)
app.include_router(__import__("app.style_api", fromlist=["router"]).router)   # 서식 보관함(목록 · 문서·파일에서 추출 · PDF 검증 · 적용) 끝점은 app/style_api.py(spec_일반편집 ② §7)
app.include_router(__import__("app.doc_agent_api", fromlist=["router"]).router)   # 에이전트(한 턴 · 제안 반영 · 자료) 끝점은 app/doc_agent_api.py(spec_일반편집 ② §8~§10)
# hwpx 공유(링크와 키를 받은 사람과 같이 쓰기 — spec_공유 ② §1): 끝점·손님 앱(공유 포트)·공유폴더 저장은 app/share_api.py. 그 모듈은 이 파일을 import 하지 않는다 — 필요한 것을 여기서 넘긴다
__import__("app.share_api", fromlist=["attach"]).attach(app, session=_sess, loaded=DOCS.get, name=_shown_of, doc=get_doc, patch=patch_block, split=split, merge=merge,
                                                        media=media, bumped=BUMPED, store=works.root, exists=lambda wid: bool(works.folder(wid) and works.folder(wid).is_dir()))


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
    return heading_rules.history(kind if kind in ("rules", "guide", "form") else None, max(1, min(limit, 1000)))  # form = 양식 정보 저장(② §12)


@app.get("/api/headings/llm")
def headings_llm():
    return llm.status()


# ---- 구분 기준(spec_구분_기준 ② §7) — 설정 · 계획(사본 모의 실행) · 반영(공통 트랜잭션 + 문서 전체 검사) · 문서에서 읽기 · 저장한 과제 구성(presets) ----------------

PROFILE = division_profiles.get("rnd")   # 1차 프로파일 하나(국가R&D) — 문서마다 고르게 되면 settings.profileId 로


def _division_settings(body):
    try:
        return division_model.norm_settings(body, PROFILE)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, f"구분 값 오류: {e}") from e


PRIOR_MAX = 12   # 앞서 반영한 값은 이만큼까지(옛 것부터 버림)


def _division_prior(s):
    """앞서 이 문서에 반영한 값들(spec_구분_기준 ② §19 — 옛 것부터, 엔진의 prior 인자): 그 값의 기관 이름·연도가 적힌 자리는 반영이 쓴 것이라
    지금 값과 달라도 자리 차례로 다시 맞춘다. 반영할 때마다 쌓고(divisions_apply) 편집 상태와 함께 저장 — 실행 취소·복원에도 줄이지 않는다.
    목록이 없는 작업(이 규칙 전에 반영)은 작업 폴더의 반영 상세 기록(`divisions/<계획 id>.json` 의 values)에서 한 번 모은다. 세션 잠금 안에서."""
    prior = s.division.get("prior")
    if prior is None:
        prior = []
        for rec in works.detail_records(s.id, "divisions"):
            if rec.get("appliedRev") is None or not isinstance(rec.get("values"), dict):
                continue   # 검토·LLM 기록
            try:
                v = PROFILE.norm_values(rec["values"])
            except (ValueError, KeyError, TypeError):
                continue
            if v not in prior:
                prior.append(v)
        a = s.division.get("applied")
        if a and isinstance(a.get("values"), dict) and a["values"] not in prior:
            prior.append(a["values"])
        s.division["prior"] = prior = prior[-PRIOR_MAX:]
    return prior


def _project_settings_sync(s, settings=None):
    """세션 잠금 안. 최신 TASK 라운드는 프로젝트 설정, 이전 라운드는 저장한 설정을 쓴다."""
    task = (works.work(s.id) or {}).get("task") or {}
    project, _, number = projects.group_key(task)
    latest = projects.latest_round(task) if project else number
    shared = bool(project) and number == latest and task.get("kind") != "general"   # 일반 문서(구분 기준이 없는 작업 — spec_일반편집 ② §11)는 프로젝트의 구분 기준을 받지도 주지도 않는다
    current = s.division.get("settings")
    if shared:
        try:
            if settings is not None:
                settings = projects.settings(project, settings)
            else:
                settings = projects.settings(project, current, seed=True)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    target = settings if settings is not None else current
    if target != current:
        s.division["settings"] = copy.deepcopy(target)
        s.saved_rev = -1  # 문서 rev가 같아도 공유된 입력 변경은 다음 저장에 남긴다.
    if shared:   # 프로젝트의 1단계 확정을 작업 쪽에도 옮겨 적는다 — 새 라운드가 생겨도 이 작업엔 그때 확정이 남는다(spec_작업 ② §18)
        try:
            got = projects.confirmed(project)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if got is not None and got != s.division.get("confirmed"):
            s.division["confirmed"] = got
            s.saved_rev = -1
    plan = s.division.get("plan")
    if plan and target and plan.get("settingsHash") != division_model.settings_hash(target):
        s.division["plan"] = None
    return {"project": project, "round": number, "latestRound": latest, "shared": shared} if project else None


def _division_view(s):
    """GET …/divisions 의 몸통(세션 잠금 안에서) — 프로파일·양식 판정·입력 중 설정(+파생 뷰)·마지막 적용·마지막 계획 요약·오래됨."""
    sharing = _project_settings_sync(s)
    form = PROFILE.form_of(s.doc.blocks())
    plan, settings = s.division.get("plan"), s.division["settings"]
    return {"profile": {"id": PROFILE.ID, "name": PROFILE.NAME, "version": PROFILE.VERSION, "form": form, "supported": PROFILE.supported(form),
                        "supportedForms": sorted(PROFILE.SUPPORTED)},
            "settings": settings, "dimensions": PROFILE.dimensions(settings["values"]) if settings else None,
            "applied": s.division["applied"], "plan": division_plan.brief(plan) if plan else None,
            "hints": s.division.get("hints") or [],   # 추가한 자리(② §11) — 수·출처만 쓰고 상세는 members
            "review": s.division.get("review"), "reviewing": bool(s.division.get("reviewing")),   # 마지막 LLM 검토(취합)·도는 중(② §14)
            "stale": bool(plan) and plan["baseRev"] != s.rev, "rev": s.rev, "projectSharing": sharing,
            "confirmed": _division_confirmed(s, sharing), "versions": _division_versions(s, sharing)}


def _division_versions(s, sharing):
    """(세션 잠금 안 · _project_settings_sync 뒤) 구분 기준 버전의 보기(spec_작업 ② §19) — [{id, name, at, values, hash, active}] 저장한 차례.
    공유 중(프로젝트의 최신 라운드)일 때만 그 프로젝트의 버전, 아니면 []. active = 그 버전의 hash 가 지금 입력 설정의 hash 와 같음(당해 차년도까지)."""
    if not (sharing and sharing["shared"]):
        return []
    try:
        rows = projects.versions(sharing["project"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    settings = s.division.get("settings")
    now = division_model.settings_hash(settings) if settings is not None else None
    return [{**{k: v[k] for k in ("id", "name", "at", "values", "hash")}, "active": now is not None and v["hash"] == now} for v in rows]


def _division_confirmed(s, sharing):
    """(세션 잠금 안 · _project_settings_sync 뒤) 1단계 구성 확정의 보기(spec_작업 ② §18) — {at, hash, values, scope: project|work, project?, valid} | None.
    공유 중(프로젝트의 최신 라운드)이면 프로젝트 기록의 것, 아니면 작업의 것. valid = 지금 입력 값의 hash 가 확정한 hash 와 같음."""
    if sharing and sharing["shared"]:
        try:
            got = projects.confirmed(sharing["project"])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        extra = {"scope": "project", "project": sharing["project"]}
    else:
        got, extra = copy.deepcopy(s.division.get("confirmed")), {"scope": "work"}
    if not isinstance(got, dict):
        return None
    settings = s.division.get("settings")
    return {**{k: got.get(k) for k in ("at", "hash", "values")}, **extra,
            "valid": settings is not None and division_model.settings_hash(settings) == got.get("hash")}


def _division_form(s):
    """이 문서의 양식 정보(heading_forms.pin 꼴 {key, name, how, sha1, text} | None — spec_헤딩_추출 ② §12): 구분 기준 LLM 검토의 프롬프트에 붙고(spec_구분_기준 ② §16)
    화면의 「양식 정보」 단추 이름이 된다. 세션 잠금 밖에서 부른다(양식 폴더·작업 파일을 읽음). 못 읽으면 None."""
    from app import heading_forms
    try:
        return heading_forms.pin(s)
    except (OSError, ValueError):
        return None


@app.get("/api/docs/{doc_id}/divisions")
def divisions_get(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        view = _division_view(s)
    from app import heading_forms
    form = _division_form(s)
    ps = division_presets.state()   # 저장한 과제 구성(② §7·§8) — 파일이 손상되면 빈 목록 + presetsBroken
    return {**view, "presets": ps["presets"], "presetsBroken": ps["broken"], "formInfo": {k: form[k] for k in ("key", "name", "how")} if form else None,
            "comments": heading_forms.comments(form["text"]) if form else []}   # 양식별 코멘트(② §18) — 맞는 양식이 없으면 []


@app.put("/api/docs/{doc_id}/divisions/settings")
def divisions_settings(doc_id: str, body: dict = Body(...)):
    """입력 중 설정 {values} (또는 FMM v1 값 그대로) — 저장만(문서는 그대로). 값이 달라지면 지금 계획은 버린다."""
    settings = _division_settings(body)
    s = _sess(doc_id)
    with s.lock:
        _project_settings_sync(s, settings)
        view = _division_view(s)
    _persist_safe(s, force=True)  # rev 가 안 바뀌어도 설정은 작업에 남긴다
    return view


@app.post("/api/docs/{doc_id}/divisions/confirm")
def divisions_confirm(doc_id: str, body: dict = Body(default={})):
    """1단계 「구성 확정」(spec_작업 ② §18) {values?} → GET …/divisions 와 같은 몸통. values 가 있으면 먼저 입력 값으로 저장(PUT …/settings 와 같은 길).
    공유 중(프로젝트의 최신 라운드)이면 프로젝트 기록에 확정 {at, hash, values}(작업 쪽에도 옮겨 적음), 아니면 작업에만. 문서는 안 바뀐다.
    400 값 없음 · 409 프로젝트 저장 파일 손상."""
    settings = _division_settings(body) if body.get("values") is not None else None
    s = _sess(doc_id)
    with s.lock:
        sharing = _project_settings_sync(s, settings)
        settings = s.division["settings"]
        if settings is None:
            raise HTTPException(400, "구분 값을 먼저 넣으세요")
        got = None
        if sharing and sharing["shared"]:
            try:
                got = projects.confirm(sharing["project"], settings)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
        scope = "project" if got is not None else "work"
        if got is None:
            got = {"at": time.time(), "hash": division_model.settings_hash(settings), "values": copy.deepcopy(settings["values"])}
        s.division["confirmed"] = copy.deepcopy(got)
        view = _division_view(s)
    _persist_safe(s, force=True)  # rev 가 안 바뀌어도 확정은 작업에 남긴다
    works.log(s.id, "divisionConfirm", rev=s.rev, settingsHash=got["hash"], scope=scope,
              **({"project": sharing["project"]} if scope == "project" else {}))
    return view


def _version_sharing(s):
    """(세션 잠금 안) 구분 기준 버전을 다룰 수 있는 작업인지 — 공유 중(프로젝트의 최신 라운드)이 아니면 409(spec_작업 ② §19). → projectSharing."""
    sharing = _project_settings_sync(s)
    if not (sharing and sharing["shared"]):
        raise HTTPException(409, "프로젝트의 최신 라운드 작업에서만 프로젝트 구성 버전을 다룹니다")
    return sharing


@app.post("/api/docs/{doc_id}/divisions/versions")
def divisions_version_save(doc_id: str, body: dict = Body(...)):
    """구분 기준 버전 저장(spec_작업 ② §19) {name, values?, replace?} → GET …/divisions 와 같은 몸통. values 가 있으면 먼저 입력 값으로 저장(PUT …/settings 와 같은 길)하고
    지금 입력 설정을 그 이름의 버전으로 남긴다. 같은 이름은 replace: true 일 때만 덮어씀(id 유지 · at 갱신). 지금 구분 기준의 확정은 안 바뀐다.
    400 이름·값 없음 · 409 공유 중이 아님 · 같은 이름 · 50개 넘음 · 프로젝트 저장 파일 손상."""
    try:
        name = projects.version_name(body.get("name"))
    except projects.VersionName as exc:
        raise HTTPException(400, str(exc)) from exc
    settings = _division_settings(body) if body.get("values") is not None else None
    s = _sess(doc_id)
    with s.lock:
        sharing = _version_sharing(s)   # 공유 중이 아니면 입력을 바꾸기 전에 멈춘다
        if settings is not None:
            _project_settings_sync(s, settings)
        settings = s.division["settings"]
        if settings is None:
            raise HTTPException(400, "구분 값을 먼저 넣으세요")
        try:
            got = projects.version_save(sharing["project"], name, settings, replace=body.get("replace") is True)
        except (projects.VersionConflict, projects.VersionLimit) as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if got is None:
            raise HTTPException(409, "작업 폴더가 없어 프로젝트 구성 버전을 저장하지 못했습니다")
        view = _division_view(s)
    _persist_safe(s, force=True)  # values 로 입력이 바뀌었으면 작업에 남긴다
    works.log(s.id, "divisionVersion", op="save", version=got["id"], name=got["name"], project=sharing["project"], rev=s.rev)
    return view


@app.post("/api/docs/{doc_id}/divisions/versions/{vid}/apply")
def divisions_version_apply(doc_id: str, vid: str):
    """구분 기준 버전 적용(spec_작업 ② §19) → GET …/divisions 와 같은 몸통. 그 버전의 값을 입력 설정으로 두고(프로젝트 공유 입력이 바뀐다) 확정까지 — …/confirm 과 같은 결과.
    문서는 안 바뀐다. 404 없는 버전 · 409 공유 중이 아님 · 프로젝트 저장 파일 손상."""
    s = _sess(doc_id)
    with s.lock:
        sharing = _version_sharing(s)
        try:
            version = projects.version_get(sharing["project"], vid)
        except projects.VersionMissing as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        _project_settings_sync(s, _division_settings({"values": version["values"]}))
        settings = s.division["settings"]
        try:
            got = projects.confirm(sharing["project"], settings)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if got is None:
            got = {"at": time.time(), "hash": division_model.settings_hash(settings), "values": copy.deepcopy(settings["values"])}
        s.division["confirmed"] = copy.deepcopy(got)
        view = _division_view(s)
    _persist_safe(s, force=True)  # rev 가 안 바뀌어도 입력·확정은 작업에 남긴다
    works.log(s.id, "divisionVersion", op="apply", version=version["id"], name=version["name"], project=sharing["project"], rev=s.rev)
    return view


@app.delete("/api/docs/{doc_id}/divisions/versions/{vid}")
def divisions_version_delete(doc_id: str, vid: str):
    """구분 기준 버전 삭제(spec_작업 ② §19) → GET …/divisions 와 같은 몸통. 지금 구분 기준·확정은 안 바뀐다. 404 없는 버전 · 409 공유 중이 아님 · 프로젝트 저장 파일 손상."""
    s = _sess(doc_id)
    with s.lock:
        sharing = _version_sharing(s)
        try:
            gone = projects.version_delete(sharing["project"], vid)
        except projects.VersionMissing as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        view = _division_view(s)
    _persist_safe(s, force=True)
    works.log(s.id, "divisionVersion", op="delete", version=gone["id"], name=gone["name"], project=sharing["project"], rev=s.rev)
    return view


@app.get("/api/docs/{doc_id}/divisions/plan")
def divisions_plan_get(doc_id: str):
    s = _sess(doc_id)
    with s.lock:
        _project_settings_sync(s)
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
        before = copy.deepcopy(s.division["settings"])
        _project_settings_sync(s, settings)
        settings = s.division["settings"]
        if settings is None:
            raise HTTPException(400, "구분 값을 먼저 넣으세요")
        changed = settings != before
        rev = s.rev
        applied = s.division["applied"]
        rebuild = not (applied and applied.get("values") == settings["values"])  # 같은 값을 이미 전체 반영한 문서면 자리표시를 다시 본뜨지 않음(FMM divisionsDone)
        hints = [h["para"] for h in s.division.get("hints") or [] if h.get("para")]   # 추가한 자리(② §11) — 후보·모의 실행에
        prior = list(_division_prior(s))   # 앞서 반영한 값들(② §19) — 이름·연도를 바꾼 값으로 다시 반영할 때 옛 자리를 알아봄
        copy_doc, snap = division_plan.snapshot_copy(s.kit, s.original, s.doc)
    try:
        plan = division_plan.make(s.kit, s.original, copy_doc, rev, settings, PROFILE, only=only, skip=skip, rebuild=rebuild, copy=(copy_doc, snap), hints=hints,
                                  prior=prior)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    with s.lock:
        _project_settings_sync(s)
        settings_changed = division_model.settings_hash(s.division["settings"]) != plan["settingsHash"]
        s.division["plan"] = None if settings_changed else plan
        stale = plan["baseRev"] != s.rev or settings_changed
        a = s.division["applied"]
        # 지금 규칙(프로파일 판)으로 다시 계획했는데 할 일이 없음 = 마지막 반영이 새 규칙에도 맞는다 — 판을 올려 화면의 「새 규칙 — 계획 확인」 을 끈다(② §16). 자리를 빼거나 한 자리만 본 계획은 아님
        confirmed = bool(a and not stale and only is None and not skip and a.get("values") == plan["values"] and a.get("profileVersion") != plan["profileVersion"]
                         and not plan["_report"]["groups"] and not plan["_report"]["changes"])
        if confirmed:
            s.division["applied"] = {**a, "profileVersion": plan["profileVersion"]}
    if confirmed or changed:   # 설정이 바뀌었으면 작업에도 — 문서 차례가 그대로면 주기 저장이 건너뛰어 계획만 본 값이 디스크에 안 남았음(② §8 자동 저장, 2026-11-11 astra P1)
        _persist_safe(s, force=True)
    works.log(s.id, "divisionPlan", rev=rev, planId=plan["planId"], settingsHash=plan["settingsHash"], only=only, skip=skip, summary=plan["summary"])
    return {**division_plan.view(plan), "stale": stale, "rev": s.rev}


@app.post("/api/docs/{doc_id}/divisions/adopt")
def divisions_adopt(doc_id: str, body: dict = Body(default={})):
    """구조 확인(spec_취합 ② §8-4) — {values?} → {adopted, why, summary, applied, rev}. 문서는 안 바뀐다.
    한 번도 반영한 적 없는 문서의 구조가 이미 지금 값에 맞으면(전체 계획에 바뀔 것·못 정한 자리가 없고 이미 맞은 자리가 있음) 반영 기록을 적는다(adopted) —
    구조를 맞춘 프레임을 새로 올리면 반영 끝점은 할 일이 없어 기록을 안 남기고, 그러면 취합의 배포 기준본이 notApplied 로 막힌다. 계획은 rebuild=False(채워진 자리를 다시 본뜨지 않음) · 저장하지 않는다."""
    settings = _division_settings(body) if body.get("values") is not None else None
    s = _sess(doc_id)
    with s.lock:
        _project_settings_sync(s, settings)
        settings = s.division["settings"]
        if settings is None:
            raise HTTPException(400, "구분 값을 먼저 넣으세요")
        if s.division.get("applied"):
            return {"adopted": False, "why": "applied", "summary": None, "applied": s.division["applied"], "rev": s.rev}
        rev, key = s.rev, division_model.settings_hash(settings)
        hints = [h["para"] for h in s.division.get("hints") or [] if h.get("para")]
        prior = list(_division_prior(s))
        copy_doc, snap = division_plan.snapshot_copy(s.kit, s.original, s.doc)
    try:
        plan = division_plan.make(s.kit, s.original, copy_doc, rev, settings, PROFILE, only=None, skip=[], rebuild=False, copy=(copy_doc, snap), hints=hints, prior=prior)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    summary = plan["summary"]
    why = ("changes" if plan["_report"]["groups"] or plan["_report"]["changes"] else "unresolved" if summary.get("unresolved") else
           "noCandidates" if not summary.get("already") else None)
    with s.lock:
        _project_settings_sync(s)
        if s.rev != rev or division_model.settings_hash(s.division["settings"]) != key:
            raise HTTPException(409, "확인하는 동안 문서나 값이 바뀌었습니다 — 다시 하세요")
        if s.division.get("applied"):
            return {"adopted": False, "why": "applied", "summary": summary, "applied": s.division["applied"], "rev": s.rev}
        if why:
            return {"adopted": False, "why": why, "summary": summary, "applied": None, "rev": s.rev}
        s.division["prior"] = ([v for v in _division_prior(s) if v != plan["values"]] + [plan["values"]])[-PRIOR_MAX:]
        s.division["applied"] = {"values": plan["values"], "settingsHash": plan["settingsHash"], "profileVersion": plan["profileVersion"],
                                 "rev": s.rev, "at": time.time(), "planId": plan["planId"], "summary": summary, "adopted": True}
        applied = s.division["applied"]
    _persist_safe(s, force=True)   # rev 가 안 바뀌어도 반영 기록은 작업에 남긴다
    works.log(s.id, "divisionAdopt", rev=rev, planId=plan["planId"], settingsHash=plan["settingsHash"], summary=summary)
    return {"adopted": True, "why": None, "summary": summary, "applied": applied, "rev": s.rev}


@app.post("/api/docs/{doc_id}/divisions/apply")
def divisions_apply(doc_id: str, body: dict = Body(...)):
    """{planId, expectRev?} → 고정된 계획만 반영(spec_구분_기준 ② §4): 계획의 사본 문서를 세션 문서로 바꿔 넣고 문서 전체 검사 → 실패면 복원·422,
    성공이면 undo 1·rev +1·기록 1줄 + 상세 결과 파일. 계획이 없거나 문서가 계획 뒤에 바뀌었으면 409(다시 계획). 화면은 문서를 다시 읽는다."""
    plan_id, expect = body.get("planId"), body.get("expectRev")
    s = _sess(doc_id)
    with s.lock:
        _project_settings_sync(s)
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
        s.division["prior"] = ([v for v in _division_prior(s) if v != plan["values"]] + [plan["values"]])[-PRIOR_MAX:]   # 반영한 값 쌓기(② §19)
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


@app.post("/api/divisions/read-file")
async def divisions_read_file(file: UploadFile = File(...)):
    """1단계 「파일 올려 추출」(spec_작업 ② §18) — 올린 파일(hwpx · hwp 는 올리기와 같이 한글로 바꿔)에 적힌 구분 값 → {name(올린 파일 이름), form, read}(read = …/divisions/read 와 같은 꼴).
    작업을 만들지 않는다(세션·작업 폴더 없음 — 문서를 읽기만). 400 hwpx 아님 · 열 수 없음 · 양식 이름 문단 없음 · 413 크기."""
    from starlette.concurrency import run_in_threadpool
    shown, data = file.filename or "document.hwpx", await file.read()
    if len(data) > MAX_MB * 2 ** 20:
        raise HTTPException(413, f"{MAX_MB} MB 보다 큰 파일은 열 수 없습니다")
    name = shown
    if name.lower().endswith(".hwp"):
        name, data = await run_in_threadpool(_from_hwp, name, data)   # 한글 변환은 수 초~수십 초 — 이벤트 루프 밖에서
    if fmt_of(name) != "hwpx":
        raise HTTPException(400, "hwp·hwpx 파일만 구분 값을 읽을 수 있습니다")
    return await run_in_threadpool(_division_read_bytes, shown, data)   # 큰 문서는 읽는 데 1초 넘게 — 이벤트 루프 밖에서


def _division_read_bytes(name, data):
    """hwpx 바이트 → {name, form, read} — 세션 없이 문서만 연다(Session 과 같은 HwpxDoc · 등록·저장 없음)."""
    try:
        blocks = HwpxDoc(data).blocks()
    except Exception as e:  # noqa: BLE001 — 깨진 파일·hwpx 아님
        raise HTTPException(400, f"hwpx 로 열 수 없습니다: {e}") from e
    form = PROFILE.form_of(blocks)
    if not form:
        raise HTTPException(400, "양식 이름 문단이 없어 값을 읽을 수 없습니다")
    return {"name": name, "form": form, "read": PROFILE.read_values(blocks, PROFILE.levels_of(blocks))}


# ---- 문서 표시 · 추가한 자리 · LLM 재검토(spec_구분_기준 ② §11) ----------------------------------------------------------

DIVISION_DEFAULT_VALUES = {"stages": [1], "orgs": {"lead": "", "joint": [], "nonprofit": [False]}}   # 값이 아직 없을 때 members 가 쓰는 기본값(묶음 찾기에만)


def _division_values(s):
    _project_settings_sync(s)
    settings = s.division["settings"]
    return settings["values"] if settings else PROFILE.norm_values(DIVISION_DEFAULT_VALUES)


@app.get("/api/docs/{doc_id}/divisions/members")
def divisions_members(doc_id: str):
    """문서 표시 자료(② §11) — 계획 없이 find 만: 묶음마다 항목 안 문단 id 전부 + 추가한 자리(hint) 행. 문서는 그대로.
    + reads = 구분 기준 판독(② §23 — 연구개발과제 문서만)이 보탠 자리: 엔진 묶음의 라벨이 아닌 괄호 줄 · 표 안의 기관·차년도(판독만 — 반영 대상이 아니다). scan = 그 판독의 요약."""
    s = _sess(doc_id)
    with s.lock:
        blocks = s.doc.blocks()
        form = PROFILE.form_of(blocks)
        m = PROFILE.members(blocks, PROFILE.levels_of(blocks), _division_values(s), s.division.get("hints") or [], prior=_division_prior(s))
        out = {**m, "rev": s.rev, "form": form, "supported": PROFILE.supported(form)}
    from app import division_scan_api as DSA
    e = DSA.ensure(s)
    if e is not None and e["rev"] == out["rev"]:   # 판독이 같은 문서 차례의 것일 때만 보탠다(그 사이 고쳤으면 다음 읽기에)
        v = e["result"].get("_values")
        out["reads"] = DSA.reads(e, _division_orgs(v) if v else None, (v or {}).get("stages"))
        out["scan"] = DSA.summary(e, s)
    return out


def _division_orgs(values):
    """과제 기관 [{key, name, role}] — 구분 기준 판독의 보탬이 기관 열쇠를 이름으로 보일 때(merge_gather_frame.orgs_of)."""
    from app import merge_gather_frame
    return merge_gather_frame.orgs_of(values)


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


@app.post("/api/docs/{doc_id}/divisions/comments")
def divisions_comment(doc_id: str, body: dict = Body(...)):
    """양식별 코멘트 하나 {text}(② §18) → {formInfo {key, name, how}, comments [{date, text}], created} — 이 문서의 양식 정보 「구분 기준 자리」 절 코멘트 목록 끝에 한 줄.
    맞는 양식이 없으면 프로파일이 판정한 양식 이름(없으면 파일 이름에서 낸 키)으로 코멘트만 든 파일을 만들어(같은 키의 파일이 있으면 거기에 붙여) 이 문서의 양식으로 고른다.
    세션 상태(rev·계획·추가한 자리)는 안 바꾼다. 고치기·지우기는 「양식 정보」 편집기에서."""
    from app import heading_forms as F
    s = _sess(doc_id)
    try:
        text = F.comment_line(body.get("text"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if F.forms_dir() is None:
        raise HTTPException(503, "양식 정보 저장이 꺼져 있어 코멘트를 남길 수 없습니다(NFM_FORMS)")
    with s.lock:
        name = PROFILE.form_of(s.doc.blocks())
    date = time.strftime("%Y-%m-%d")
    try:
        for again in (True, False):   # 그 사이 다른 곳에서 고쳐 sha 가 어긋나면 한 번 다시 읽어 붙인다
            form, created = F.pin(s), False
            if form is None:
                new = F.bare(name or s.name, F.doc_sha(s))
                try:
                    form = F.get(new["key"])   # 조건이 안 맞았을 뿐 같은 키의 파일이 있다 — 거기에 붙인다
                except KeyError:
                    form, created = {**new, "sha1": ""}, True
            try:
                saved = F.save(form["key"], F.add_comment(form["text"], text, date), expect=form["sha1"], reason="구분 기준 코멘트")
                break
            except heading_rules.StaleVersion:
                if not again:
                    raise
    except (heading_rules.StaleVersion, ValueError, OSError) as e:   # 깨진 조건 블록·글 한도(20,000자)도 여기 — 코멘트 글 탓이 아니다
        raise HTTPException(503, f"코멘트를 양식 정보에 남기지 못했습니다: {e}") from e
    how = form.get("how")
    if how is None:   # 맞지 않던 양식 — 이 문서의 양식으로 고른다(화면이 새 양식을 저장한 뒤 하는 것과 같음)
        how = "manual"
        try:
            F.set_choice(s.id, saved["key"])
        except (KeyError, ValueError, OSError):   # 못 적어도 코멘트는 남았다(새 파일은 sha256 조건으로 맞는다)
            pass
    return {"formInfo": {"key": saved["key"], "name": saved["name"], "how": how}, "comments": F.comments(saved["text"]), "created": created}


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
        groups = PROFILE.find(blocks, lv, values, hints=[h["para"] for h in hints], prior=_division_prior(s))
        payload = division_llm.data(blocks, lv, values, hints, groups, PROFILE.value_text)
        rev = s.rev
    res = division_llm.ask(payload, effort=body.get("effort") or "medium", form=_division_form(s))   # 양식 정보 절(② §16)
    name = f"llm_{int(time.time())}"
    record = {"rev": rev, "payload": payload, "prompt": res["prompt"], "response": res["data"], "call": res["call"], "form": res.get("form")}
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
        out = {"hints": list(new_hints), "applied": applied, "skipped": skipped, "summary": res["data"].get("summary") or "", "call": res["call"], "rev": s.rev,
               "form": res.get("form")}
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
        groups = PROFILE.find(blocks, lv, values, hints=[h["para"] for h in s.division.get("hints") or [] if h.get("para")], prior=_division_prior(s))
        payload = division_llm.missing_data(blocks, lv, values, groups, PROFILE.value_text)
        rev = s.rev
    sent = {"tables": len(payload["tables"]), "paragraphs": len(payload["paragraphs"])}
    if not payload["tables"] and not payload["paragraphs"]:
        return {"missing": [], "skipped": [], "summary": "묶음 밖에 구분 낱말이 든 표·문단이 없습니다", "sent": sent, "call": None, "detail": None, "rev": rev,
                "form": None}
    res = division_llm.ask_missing(payload, effort=body.get("effort") or "medium", form=_division_form(s))   # 양식 정보 절(② §16)
    name = f"missing_{int(time.time())}"
    record = {"rev": rev, "payload": payload, "prompt": res["prompt"], "response": res["data"], "call": res["call"], "form": res.get("form")}
    if not res["data"]:
        works.add_detail(s.id, "divisions", name, record)
        works.log(s.id, "divisionMissing", rev=rev, error=res["call"].get("error"), ms=res["call"].get("ms"), **sent)
        raise HTTPException(502, f"빠진 자리 검토에 답을 못 받았습니다: {res['call'].get('error') or '응답 없음'}")
    items, skipped = division_llm.check_missing(res["data"], payload)
    detail = works.add_detail(s.id, "divisions", name, {**record, "missing": items, "skipped": skipped})
    works.log(s.id, "divisionMissing", rev=rev, found=len(items), skipped=len(skipped), backend=res["call"].get("backend"), ms=res["call"].get("ms"),
              costUsd=res["call"].get("costUsd"), **sent)
    return {"missing": items, "skipped": skipped, "summary": res["data"].get("summary") or "", "sent": sent, "call": res["call"], "detail": detail, "rev": rev,
            "form": res.get("form")}


@app.post("/api/docs/{doc_id}/divisions/review")
def divisions_review(doc_id: str, body: dict = Body(default={})):
    """LLM 검토(spec_구분_기준 ② §14) — 재검토(§11 — 표시한 자리가 있을 때만)와 빠진 자리 검토(§13)를 **동시에** 돌려 한 목록(items)으로. 자료는 잠금 안에서 한 번에(같은 rev),
    호출은 잠금 밖 스레드 둘, 재검토의 반영은 잠금 안에서 rev 가 그대로일 때만. 마지막 결과는 세션에 두고 작업에 저장한다(GET …/divisions 의 review).
    auto = 이미 검토했거나 지원 양식이 아니거나 LLM 연결이 없으면 호출 없이 {skipped}(전에는 새 작업의 첫 분석이 이 인자로 불렀다 — 2026-11-15 부터 화면은 auto 로 부르지 않는다: spec_작업 ② §9·§20
    「구분 기준은 옵션」). 부른 검토가 모두 답이 없으면 502, 돌고 있으면 409."""
    s = _sess(doc_id)
    auto, effort = body.get("auto") is True, body.get("effort") or "medium"
    with s.lock:
        if s.division.get("reviewing"):
            raise HTTPException(409, "LLM 검토가 이미 돌고 있습니다")
        blocks = s.doc.blocks()
        if auto:
            why = ("done" if s.division.get("review") else "unsupported" if not PROFILE.supported(PROFILE.form_of(blocks))
                   else "llm" if not llm.status().get("available") else None)
            if why:
                return {"skipped": why, "review": s.division.get("review")}
        hints = copy.deepcopy(s.division.get("hints") or [])
        lv = PROFILE.levels_of(blocks)
        values = _division_values(s)
        settings, applied0 = s.division["settings"], s.division["applied"]
        rebuild = not (settings and applied0 and applied0.get("values") == settings["values"])   # 계획과 같은 기준(divisions_plan) — 같은 값을 이미 반영한 문서면 자리표시를 다시 본뜨지 않음
        groups = PROFILE.find(blocks, lv, values, rebuild=rebuild, hints=[h["para"] for h in hints if h.get("para")], prior=_division_prior(s))
        pending = PROFILE.pending(groups) if settings else None   # 값과 아직 안 맞는 묶음(스크립트 — ② §16 「검토에 보이게」), 값을 안 넣었으면 모름
        p_review = division_llm.data(blocks, lv, values, hints, groups, PROFILE.value_text) if hints else None
        p_missing = division_llm.missing_data(blocks, lv, values, groups, PROFILE.value_text)
        sent = {"tables": len(p_missing["tables"]), "paragraphs": len(p_missing["paragraphs"])}
        if not p_missing["tables"] and not p_missing["paragraphs"]:
            p_missing = None
        rev = s.rev
        s.division["reviewing"] = True
    try:
        t0 = time.time()
        form = _division_form(s)   # 이 문서의 양식 정보 — 두 검토의 프롬프트에(② §16)

        def ask(fn, payload):  # → {"data", "prompt", "call"} | None(안 부름) — 예외도 답 없음으로
            if payload is None:
                return None
            try:
                return fn(payload, effort=effort, form=form)
            except Exception as e:  # noqa: BLE001
                return {"data": None, "prompt": "", "call": {"error": f"{type(e).__name__}: {e}"}}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="division-review") as ex:
            f_r, f_m = ex.submit(ask, division_llm.ask, p_review), ex.submit(ask, division_llm.ask_missing, p_missing)
            res_r, res_m = f_r.result(), f_m.result()
        why, errors = {}, {}
        if p_review is None:
            why["review"] = "표시한 자리가 없습니다"
        if p_missing is None:
            why["missing"] = "묶음 밖에 구분 낱말이 든 표·문단이 없습니다"
        for k, res in (("review", res_r), ("missing", res_m)):
            if res is not None and not res["data"]:
                errors[k] = res["call"].get("error") or "응답 없음"
        ran = {"review": bool(res_r and res_r["data"]), "missing": bool(res_m and res_m["data"])}
        name = f"review_{int(time.time())}"
        used = next((res["form"] for res in (res_r, res_m) if res and res.get("form")), None)   # 실제로 프롬프트에 붙은 양식 글 {key, name, sha1}
        record = {"rev": rev, "auto": auto, "form": used, "pending": pending,
                  **{k: res and {"payload": p, "prompt": res["prompt"], "response": res["data"], "call": res["call"]}
                     for k, res, p in (("review", res_r, p_review), ("missing", res_m, p_missing))}}
        if (res_r or res_m) and not ran["review"] and not ran["missing"]:  # 부른 검토가 모두 답이 없음
            works.add_detail(s.id, "divisions", name, record)
            works.log(s.id, "divisionReview", rev=rev, auto=auto, ran=ran, errors=errors)
            raise HTTPException(502, "LLM 검토에 답을 못 받았습니다: " + " · ".join(f"{'재검토' if k == 'review' else '빠진 자리'} — {v}" for k, v in errors.items()))
        with s.lock:
            old_hints = list(s.division.get("hints") or [])
            idx = division_llm.index(s.doc.blocks())
            applied, part_r, part_m = [], None, None
            if ran["review"]:
                if s.rev != rev:
                    ran["review"], errors["review"] = False, "검토하는 동안 문서가 바뀌어 재검토 결과는 반영하지 않았습니다"
                else:
                    new_hints, applied, skipped = division_llm.apply_revisions(old_hints, res_r["data"].get("revisions"), idx, PROFILE.hint_read)
                    s.division["hints"] = new_hints
                    if applied:
                        s.division["plan"] = None
                    part_r = {"applied": applied, "skipped": skipped, "summary": res_r["data"].get("summary") or "", "call": res_r["call"]}
            if ran["missing"]:
                items_m, skipped_m = division_llm.check_missing(res_m["data"], p_missing)
                part_m = {"missing": items_m, "skipped": skipped_m, "summary": res_m["data"].get("summary") or "", "sent": sent, "call": res_m["call"]}
            hints_now = list(s.division.get("hints") or [])
            para_of = {h["id"]: h.get("para") for h in [*old_hints, *hints_now] if h.get("id")}
            cost = sum((res["call"].get("costUsd") or 0) for res in (res_r, res_m) if res)
            out = {"at": time.time(), "rev": rev, "ran": ran, "why": why, "errors": errors, "review": part_r, "missing": part_m,
                   "items": division_llm.merge_review(applied, (part_m or {}).get("missing"), idx, para_of),
                   "pending": pending, "form": used,   # ② §16 — 값과 아직 안 맞는 묶음(스크립트) · 프롬프트에 붙은 양식 정보
                   "costUsd": round(cost, 4), "ms": int((time.time() - t0) * 1000)}
            s.division["review"] = out
        detail = works.add_detail(s.id, "divisions", name, {**record, "result": out})
        works.log(s.id, "divisionReview", rev=rev, auto=auto, ran=ran, applied=len(applied), found=len((part_m or {}).get("missing") or []), items=len(out["items"]),
                  ms=out["ms"], costUsd=out["costUsd"], **({"errors": errors} if errors else {}))
    finally:
        s.division["reviewing"] = False
    _persist_safe(s, force=True)
    return {**out, "hints": hints_now, "detail": detail}


@app.get("/api/divisions/presets")
def division_presets_list():
    """저장한 과제 구성(② §7) → {presets, broken} — broken = 파일 손상(빈 목록으로 보이고 저장·삭제는 503)."""
    return division_presets.state()


@app.put("/api/divisions/presets/{pid}")
def division_presets_put(pid: str, body: dict = Body(...)):
    """{name, values, profileId?} — pid "new" 면 새로. 틀리면 400, 같은 이름 409, 없는 id 404, 저장 파일 손상 503(고치지 않음)."""
    try:
        return division_presets.put(pid, body.get("name"), body.get("values"), body.get("profileId") or PROFILE.ID)
    except division_presets.Broken as e:
        raise HTTPException(503, str(e)) from e
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
    except division_presets.Broken as e:
        raise HTTPException(503, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, f"없는 항목: {e}") from e
    except OSError as e:
        raise HTTPException(503, f"저장하지 못했습니다: {e}") from e
