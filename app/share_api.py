"""hwpx 공유(spec_공유) — 주인 끝점(8114) · 손님 앱(공유 포트) · 공유폴더 저장. 순수 로직 app/share.py 위에 얹는다.

이 모듈은 app.server 를 import 하지 않는다 — server.py 가 attach(app, …) 한 번으로 필요한 것을 넘긴다(② §1):
세션 얻기 · 메모리에 있는 세션 · 보이는 이름 · 끝점 함수(문서 읽기·글 고침·나누기·합치기·그림) · 편집 알림 목록(BUMPED) · 작업 저장소 뿌리.
손님 앱(guest)은 따로 선 FastAPI 앱이다 — 공유 포트(8119)에서만 듣고, 끝점은 이 파일에 적힌 것이 전부다(② §3).
"""
import contextlib
import json
import logging
import math
import os
import re
import socket
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app import share

log = logging.getLogger("uvicorn.error")
STATIC = Path(__file__).with_name("static") / "share"
COOKIE = "nfms_"
BODY_MAX = 256 * 1024      # 손님 요청 본문(바이트)
GONE = 410                 # 끝난 공유·없어진 문서(손님 앱) — 404 는 「그 문단·그림이 없음」 에만 쓴다
TEXT_MAX = 20000           # 문단 글(자)
TAP_MAX = 4 * 2 ** 20      # 주인 편집 응답을 읽어 두는 상한(바이트) — 넘으면 「다시 읽기」
SAVE_QUIET, SAVE_MAX = 4.0, 30.0   # 공유폴더 저장: 조용해진 뒤(초) · 계속 바뀌어도(초)
CLOSE_AFTER = 4.0          # 마지막 공유를 끈 뒤 공유 포트를 닫기까지(초) — 그 사이 손님 화면이 「공유가 끝났습니다」 를 받는다
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def port() -> int:
    return int(os.environ.get("NFM_SHARE_PORT") or 8119)


def bind_host() -> str:
    return os.environ.get("NFM_SHARE_HOST", "").strip() or "0.0.0.0"


class _Ops:
    """server.py 가 넘긴 것(attach)."""
    session = loaded = name = doc = patch = split = merge = media = exists = None


OPS = _Ops()
FEEDS: dict[str, share.Feed] = {}      # 문서(작업) id → 변경 알림 — 공유가 켜져 있고 누가 읽기 시작한 문서만
_actor = threading.local()             # 지금 이 스레드에서 편집하는 손님 id(없으면 주인)
router = APIRouter()                   # 주인 끝점(8114 앱)


def attach(app, *, session, loaded, name, doc, patch, split, merge, media, bumped, store, exists):
    """8114 앱에 공유를 붙인다(server.py 가 한 번). session(doc_id) = 세션(없으면 404 — 작업 폴더에서 다시 엶) · loaded(doc_id) = 메모리에 있는 세션 | None ·
    name(세션) = 보이는 이름 · doc/patch/split/merge/media = 그 끝점 함수 · bumped = 편집 한 번마다 부를 함수 목록 · store() = 작업 저장소 폴더 | None ·
    exists(doc_id) = 그 작업이 아직 있는가(지운 작업의 공유를 걷는다)."""
    OPS.session, OPS.loaded, OPS.name, OPS.doc, OPS.patch, OPS.split, OPS.merge, OPS.media = session, loaded, name, doc, patch, split, merge, media
    OPS.exists = exists
    share.configure(store)
    bumped.append(_on_bump)
    app.include_router(router)
    app.add_middleware(_Observe)
    app.router.on_startup.append(_boot)
    app.router.on_shutdown.append(_halt)


def _json(obj, status=200):
    """dict 를 그대로 JSON 으로(FastAPI 의 변환을 건너뛴다 — 블록이 많은 응답에서 느리다)."""
    return Response(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), status_code=status, media_type="application/json")


# ---- 변경 알림(② §4) ---------------------------------------------------------------------------------

def _by():
    return getattr(_actor, "id", None) or share.HOST


@contextlib.contextmanager
def _acting(pid):
    _actor.id = pid
    try:
        yield
    finally:
        _actor.id = None


def _on_bump(s, kind, fields):
    """편집 한 번(server._bump — 세션 잠금 안 · 차례 순). 공유 중이고 읽는 사람이 있는 문서만 적는다."""
    feed = FEEDS.get(s.id)
    if feed is None:
        return
    try:
        feed.note(s.rev, kind, _by(), fields)
    except Exception:  # noqa: BLE001 — 알림이 편집을 막지 않는다
        log.exception("share: 변경 알림을 적지 못했습니다")


def _feed(doc_id, s=None) -> share.Feed:
    feed = FEEDS.get(doc_id)
    if feed is None:
        s = s or OPS.session(doc_id)
        with s.lock:   # 지금 차례부터 적는다 — 잠금 안이라 그 사이의 편집을 놓치지 않는다
            feed = FEEDS.get(doc_id) or FEEDS.setdefault(doc_id, share.Feed(s.rev))
    return feed


_DOC_PATH = re.compile(r"^/api/docs/([0-9a-f]{12})/(?!share(?:/|$))")


class _Observe:
    """8114 앱의 미들웨어 — 공유 중인 문서를 바꾸는 요청의 응답을 읽어, 그 편집이 바꾼 블록(tops)을 변경 알림의 그 차례에 채운다(② §4).
    공유 중이 아니면 사전을 한 번 찾아보고 끝이다. 응답은 그대로 지나간다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS") or not FEEDS:
            return await self.app(scope, receive, send)
        m = _DOC_PATH.match(scope.get("path") or "")
        feed = FEEDS.get(m.group(1)) if m else None
        if feed is None:
            return await self.app(scope, receive, send)
        st = {"take": False, "body": [], "size": 0}

        async def tap(msg):
            if msg["type"] == "http.response.start":
                st["take"] = msg["status"] == 200 and any(k.lower() == b"content-type" and b"json" in v for k, v in msg.get("headers") or ())
            elif msg["type"] == "http.response.body" and st["take"]:
                chunk = msg.get("body") or b""
                st["size"] += len(chunk)
                if st["size"] <= TAP_MAX:
                    st["body"].append(chunk)
                if not msg.get("more_body") and st["size"] <= TAP_MAX:
                    _filled(feed, b"".join(st["body"]))
            await send(msg)
        await self.app(scope, receive, tap)


def _filled(feed, raw):
    if b'"tops"' not in raw:
        return
    try:
        r = json.loads(raw)
    except ValueError:
        return
    if isinstance(r, dict) and not r.get("paged") and not r.get("replayed"):   # 쪽 설정이 바뀐 편집 · 다시 보낸 답은 화면도 문서를 다시 읽는다
        feed.fill(r.get("rev"), r)


# ---- 접속 주소 · 공유폴더(② §3·§8) --------------------------------------------------------------------

_ip = {"at": 0.0, "v": ""}


def _lan_ip() -> str:
    """이 PC 의 사내망 주소 — 밖으로 나가는 길의 주소(패킷은 안 보낸다)."""
    now = time.time()
    if now - _ip["at"] < 60 and _ip["v"]:
        return _ip["v"]
    ip = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))
            ip = sk.getsockname()[0]
    except OSError:
        with contextlib.suppress(OSError):
            ip = socket.gethostbyname(socket.gethostname())
    _ip.update(at=now, v=ip or "127.0.0.1")
    return _ip["v"]


def _auto_url() -> str:
    h = bind_host()
    return f"http://{_lan_ip() if h in ('0.0.0.0', '::') else h}:{port()}"


def _link(rec) -> str:
    return f"{share.base_url() or _auto_url()}/s/{rec['id']}"


def sync_roots() -> list[str]:
    """이 PC 의 OneDrive·SharePoint 동기화 폴더들(env · 레지스트리) — 고른 폴더가 그 안인지 알려 주는 데만 쓴다."""
    roots = [os.environ.get(k, "") for k in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer")]
    try:
        import winreg
        for base, value in ((r"Software\Microsoft\OneDrive\Accounts", "UserFolder"), (r"Software\SyncEngines\Providers\OneDrive", "MountPoint")):
            with contextlib.suppress(OSError), winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    with contextlib.suppress(OSError), winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                        roots.append(str(winreg.QueryValueEx(sub, value)[0]))
    except ImportError:
        pass
    seen, out = set(), []
    for r in roots:
        k = os.path.normcase(os.path.normpath(r)) if r else ""
        if k and k not in seen and os.path.isdir(r):
            seen.add(k)
            out.append(r)
    return out


def _in_sync(folder) -> bool:
    f = os.path.normcase(os.path.normpath(str(folder)))
    return any(f == r or f.startswith(r + os.sep) for r in (os.path.normcase(os.path.normpath(x)) for x in sync_roots()))


def _folder(text) -> Path:
    raw = str(text or "").strip().strip('"').strip()
    p = Path(raw) if raw else None
    if p is None or not p.is_absolute() or not p.is_dir():
        raise HTTPException(400, "그 폴더가 없습니다 — 탐색기에서 SharePoint(OneDrive) 동기화 폴더의 경로를 복사해 넣어 주세요")
    return p


def _save(rec, s, force=False) -> dict:
    """문서의 지금 저장본을 공유폴더의 그 파일에 쓴다 → 고친 기록. 폴더의 파일이 우리가 마지막에 쓴 것과 다르면(밖에서 바뀜) force 가 아닌 한 덮지 않는다(② §8)."""
    with s.lock:
        data, rev = s.doc.save(), s.rev
    folder, sv = Path(rec["folder"]), rec.get("saved") or {}
    target = folder / rec["file"]
    try:
        if not folder.is_dir():
            raise OSError("공유폴더가 없습니다")
        if target.exists() and not force and (sv.get("sha") is None or share.sha256(target.read_bytes()) != sv["sha"]):
            return share.update(rec["id"], saved={"error": "공유폴더의 파일이 밖에서 바뀌었습니다 — 덮어쓰지 않았습니다", "conflict": True})
        share.write_file(target, data)
    except OSError as e:
        return share.update(rec["id"], saved={"error": f"공유폴더에 쓰지 못했습니다: {e}", "conflict": False})
    return share.update(rec["id"], saved={"rev": rev, "at": time.time(), "sha": share.sha256(data), "error": None, "conflict": False})


def _link_file(rec) -> dict:
    """공유폴더의 링크 바로가기(.url)를 지금 링크로 쓴다 — 처음이면 빈 이름을 골라 만들고, 있던 것은 우리 것(이 공유의 링크가 든 것)일 때만 고쳐 쓴다."""
    folder = Path(rec["folder"])
    try:
        name = rec.get("link_file") or share.free_name(folder, share.safe_stem(Path(rec["file"]).stem) + " 같이 쓰기", ".url")
        target = folder / name
        if target.exists() and f"/s/{rec['id']}".encode() not in target.read_bytes():
            return rec
        share.write_file(target, share.url_file(_link(rec)), tmp_name=f"~${rec['id']}.tmp")
        return share.update(rec["id"], link_file=name) or rec
    except (OSError, share.ShareError) as e:
        log.warning("share: 링크 바로가기를 쓰지 못했습니다: %s", e)
        return rec


def _link_file_drop(rec):
    name = rec.get("link_file")
    if not name:
        return
    with contextlib.suppress(OSError):
        target = Path(rec["folder"]) / name
        if target.is_file() and f"/s/{rec['id']}".encode() in target.read_bytes():   # 우리가 쓴 것일 때만 지운다
            target.unlink()


_seen = {}                 # 공유 id → {rev, at(마지막으로 바뀐 때), first(안 쓴 채 처음 바뀐 때)}
_saver = {"thread": None, "stop": threading.Event()}


def _autosave(rec, now):
    s = OPS.loaded(rec["doc"])
    sv = rec.get("saved") or {}
    if s is None or sv.get("rev") == s.rev or sv.get("conflict"):   # 밖에서 바뀐 파일은 주인이 정할 때까지 그대로 둔다
        _seen.pop(rec["id"], None)
        return
    st = _seen.setdefault(rec["id"], {"rev": s.rev, "at": now, "first": now})
    if st["rev"] != s.rev:
        st.update(rev=s.rev, at=now)
    if now - st["at"] >= SAVE_QUIET or now - st["first"] >= SAVE_MAX:
        _seen.pop(rec["id"], None)
        _save(rec, s)


def _retire(rec):
    """공유 하나를 걷는다 — 링크 바로가기를 지우고(우리 것일 때만) 기록을 끄고, 켜진 공유가 더 없으면 저장을 멈추고 공유 포트를 조금 뒤에 닫는다. 저장본은 폴더에 남긴다."""
    _link_file_drop(rec)
    share.stop(rec["id"])
    FEEDS.pop(rec["doc"], None)
    _seen.pop(rec["id"], None)
    if not share.active():
        _saver["stop"].set()
        LISTENER.stop_later(CLOSE_AFTER)


def _orphans():
    """작업을 지운 문서의 공유를 걷는다 — 주인 화면에서 끌 길이 없어진 공유가 켜진 채 남지 않게."""
    for rec in share.active():
        if not OPS.exists(rec["doc"]):
            log.warning("share: 지운 작업의 공유를 끕니다(%s)", rec["id"])
            _retire(rec)


def _saver_loop(stop):
    n = 0
    while not stop.wait(1.0):
        n += 1
        try:
            if n % 15 == 0:
                _orphans()
                if share.active() and not LISTENER.running():   # 서버를 켤 때 못 열었던 공유 포트 — 다시 열어 본다
                    LISTENER.start()
            for rec in share.active():
                _autosave(rec, time.time())
        except Exception:  # noqa: BLE001
            log.exception("share: 공유폴더 저장 실패")


def _saver_start():
    t = _saver["thread"]
    if t is None or not t.is_alive():
        _saver["stop"] = threading.Event()
        _saver["thread"] = threading.Thread(target=_saver_loop, args=(_saver["stop"],), daemon=True, name="share-saver")
        _saver["thread"].start()


# ---- 공유 포트(② §3) ---------------------------------------------------------------------------------

class _Listener:
    """손님 앱을 공유 포트에 띄우는 것 — 8114 서버 프로세스 안의 스레드 하나."""

    def __init__(self):
        self.lock, self.server, self.thread, self.error, self.timer = threading.Lock(), None, None, None, None

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive() and self.server and self.server.started)

    def start(self) -> bool:
        with self.lock:
            if self.timer is not None:   # 닫으려던 참이면 그만둔다
                self.timer.cancel()
                self.timer = None
            if self.running():
                return True
            import uvicorn
            host, p = bind_host(), port()
            try:   # 먼저 열 수 있는지 본다 — uvicorn 은 못 열면 스레드를 끝낼 뿐 까닭을 돌려주지 않는다
                with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as sk:
                    sk.bind((host, p))
            except OSError as e:
                self.error = f"공유 포트 {p} 을(를) 열지 못했습니다 — 다른 프로그램이 쓰는 중일 수 있습니다({e})"
                return False
            self.server = uvicorn.Server(uvicorn.Config(guest, host=host, port=p, log_level="warning", access_log=False))
            self.thread = threading.Thread(target=self.server.run, daemon=True, name="share-listener")
            self.thread.start()
            for _ in range(60):
                if self.server.started or not self.thread.is_alive():
                    break
                time.sleep(0.05)
            self.error = None if self.running() else f"공유 포트 {p} 을(를) 열지 못했습니다"
            return self.running()

    def stop(self):
        with self.lock:
            if self.server is not None:
                self.server.should_exit = True
            if self.thread is not None:
                self.thread.join(5)
            self.server = self.thread = None

    def stop_later(self, after):
        """조금 뒤에 닫는다 — 그때도 켜진 공유가 없을 때만(그 사이 다시 켜면 start 가 그만두게 한다)."""
        if after <= 0:
            return self.stop()
        with self.lock:
            if self.timer is not None:
                self.timer.cancel()
            self.timer = threading.Timer(after, lambda: None if share.active() else self.stop())
            self.timer.daemon = True
            self.timer.start()

    def view(self):
        return {"port": port(), "host": bind_host(), "running": self.running(), "error": self.error}


LISTENER = _Listener()


def _boot():
    """서버를 켤 때 — 켜진 공유가 있으면 공유 포트와 저장을 다시 켠다."""
    try:
        if share.enabled() and share.active():
            _orphans()
        if share.enabled() and share.active():
            LISTENER.start()
            _saver_start()
    except Exception:  # noqa: BLE001 — 공유 때문에 서버가 안 켜지는 일은 없게
        log.exception("share: 공유를 다시 켜지 못했습니다")


def _halt():
    _saver["stop"].set()
    LISTENER.stop()


# ---- 주인 끝점(② §7) ---------------------------------------------------------------------------------

def _need():
    if not share.enabled():
        raise HTTPException(503, "공유가 꺼져 있습니다(작업 저장이 꺼져 있거나 NFM_SHARES=off)")


def _rec(doc_id) -> dict:
    _need()
    rec = share.by_doc(doc_id)
    if rec is None:
        raise HTTPException(409, "이 문서는 공유 중이 아닙니다")
    return rec


def _status(doc_id, key=None) -> dict:
    if not share.enabled():
        return {"available": False, "active": False}
    s = OPS.session(doc_id)
    rec = share.by_doc(doc_id)
    if rec is None:
        last = share.last_of(doc_id) or {}
        return {"available": s.fmt == "hwpx", "active": False, "format": s.fmt, "folder": last.get("folder") or "", "host": last.get("host") or "",
                "roots": sync_roots(), "url": share.base_url(), "auto": _auto_url()}
    sv = rec.get("saved") or {}
    return {"available": True, "active": True, "id": rec["id"], "link": _link(rec), "url": share.base_url(), "auto": _auto_url(),
            "key": share.show_key(key) if key else None, "host": rec["host"], "folder": rec["folder"], "file": rec["file"],
            "linkFile": rec.get("link_file") or "", "synced": _in_sync(rec["folder"]), "created": rec["created"],
            "saved": {"rev": sv.get("rev"), "at": sv.get("at"), "error": sv.get("error"), "conflict": bool(sv.get("conflict")), "behind": sv.get("rev") != s.rev},
            "listen": LISTENER.view(), "people": share.people(rec["id"])}


def _raise(e: share.ShareError):
    raise HTTPException(e.code, str(e)) from e


def _own_file(doc_id, folder) -> str | None:
    """이 문서를 지난번에 같은 폴더로 공유했고 그때 우리가 쓴 저장본이 그대로 있으면(밖에서 안 바뀜) 그 파일 이름 — 다시 켤 때마다 「 (2)」, 「 (3)」 이 늘지 않게."""
    last = share.last_of(doc_id)
    sha = ((last or {}).get("saved") or {}).get("sha")
    if not last or not sha or os.path.normcase(os.path.normpath(last.get("folder") or "")) != os.path.normcase(os.path.normpath(str(folder))):
        return None
    target = folder / last["file"]
    return last["file"] if target.is_file() and share.sha256(target.read_bytes()) == sha else None


@router.get("/api/docs/{doc_id}/share")
def share_get(doc_id: str):
    """공유 상태 — 꺼져 있으면 {active: false, folder(지난번 폴더), roots(동기화 폴더들)}."""
    return _status(doc_id)


@router.post("/api/docs/{doc_id}/share")
def share_start(doc_id: str, body: dict = Body(default={})):
    """공유 켜기 {folder, host?} → 상태 + key(이 응답에만). 문서의 지금 저장본과 링크 바로가기를 공유폴더에 쓰고 공유 포트를 연다.
    400 hwpx 아님 · 폴더 없음 · 폴더에 못 씀 · 409 이미 공유 중 · 503 공유 꺼짐 · 공유 포트를 못 엶."""
    _need()
    s = OPS.session(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 공유할 수 있습니다")
    if share.by_doc(doc_id):
        raise HTTPException(409, "이 문서는 이미 공유 중입니다")
    folder = _folder(body.get("folder"))
    name = OPS.name(s)
    if not LISTENER.start():   # 먼저 연다 — 못 열면 공유폴더에 아무것도 남기지 않는다
        raise HTTPException(503, LISTENER.error or "공유 포트를 열지 못했습니다")
    try:
        file = _own_file(doc_id, folder) or share.free_name(folder, share.safe_stem(re.sub(r"\.hwpx?$", "", name, flags=re.I)), ".hwpx")   # 있는 파일은 덮지 않는다 — 새 이름
        with s.lock:
            data, rev = s.doc.save(), s.rev
        share.write_file(folder / file, data)
    except (share.ShareError, OSError) as e:
        if not share.active():
            LISTENER.stop_later(0)
        if isinstance(e, share.ShareError):
            _raise(e)
        raise HTTPException(400, f"공유폴더에 쓸 수 없습니다: {e}") from e
    try:
        rec, key = share.create(doc_id, name, folder, file, body.get("host"))
    except share.ShareError as e:
        _raise(e)
    share.update(rec["id"], saved={"rev": rev, "at": time.time(), "sha": share.sha256(data), "error": None, "conflict": False})
    _link_file(rec)
    _feed(doc_id, s)
    _saver_start()
    return _json(_status(doc_id, key))


@router.put("/api/docs/{doc_id}/share")
def share_url(doc_id: str, body: dict = Body(default={})):
    """접속 주소 고치기 {url — 빈 글이면 사내망 주소로} → 상태. 켜진 공유들의 링크 바로가기도 다시 쓴다(모든 공유가 같은 주소를 쓴다)."""
    _need()
    try:
        share.set_base_url(body.get("url"))
    except share.ShareError as e:
        _raise(e)
    for rec in share.active():
        _link_file(rec)
    return _json(_status(doc_id))


@router.post("/api/docs/{doc_id}/share/key")
def share_key(doc_id: str):
    """키 새로 만들기 → 상태 + key. 들어와 있던 손님은 모두 나간다."""
    rec = _rec(doc_id)
    try:
        key = share.rekey(rec["id"])
    except share.ShareError as e:
        _raise(e)
    return _json(_status(doc_id, key))


@router.post("/api/docs/{doc_id}/share/save")
def share_save(doc_id: str, body: dict = Body(default={})):
    """지금 공유폴더에 저장 {force? — 밖에서 바뀐 파일도 덮어쓴다} → 상태."""
    rec = _rec(doc_id)
    _save(rec, OPS.session(doc_id), force=bool(body.get("force")))
    return _json(_status(doc_id))


@router.delete("/api/docs/{doc_id}/share")
def share_stop(doc_id: str):
    """공유 끄기 → 상태. 마지막으로 한 번 저장하고(밖에서 바뀐 파일은 안 덮음) 링크 바로가기를 지운다 — 저장본은 폴더에 남는다."""
    rec = _rec(doc_id)
    with contextlib.suppress(HTTPException):
        rec = _save(rec, OPS.session(doc_id)) or rec
    _retire(rec)
    return _json(_status(doc_id))


@router.get("/api/docs/{doc_id}/share/changes")
def share_changes(doc_id: str, since: int = -1, epoch: str = "", block: str = ""):
    """주인 화면이 읽는 남의 변경(② §4) + 사람들 · block = 주인이 지금 커서를 둔 문단. 공유 중이 아니면 {active: false}."""
    rec = share.by_doc(doc_id) if share.enabled() else None
    if rec is None:
        return {"active": False}
    s = OPS.session(doc_id)
    share.host_in(rec["id"], rec["host"])
    denied = share.touch(rec["id"], share.HOST, block or None)
    out = _feed(doc_id, s).read(since, epoch, share.HOST, full=True)
    sv = rec.get("saved") or {}
    return _json({"active": True, **out, "people": share.people(rec["id"]), "denied": denied,
                  "saved": {"at": sv.get("at"), "error": sv.get("error"), "behind": sv.get("rev") != s.rev}})


# ---- 손님 앱(② §3) -----------------------------------------------------------------------------------

guest = FastAPI(title="NewFileManager — hwpx 공유", docs_url=None, redoc_url=None, openapi_url=None)

_PAGE_CSP = "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DATA_CSP = "default-src 'none'; frame-ancestors 'none'; sandbox"


class _Guard:
    """손님 앱의 모든 요청 — 큰 본문을 막고 응답에 보안 머리말을 단다."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def tag(msg):
            if msg["type"] == "http.response.start":
                heads = [(k, v) for k, v in msg.get("headers") or () if k.lower() != b"server"]
                html = any(k.lower() == b"content-type" and b"text/html" in v for k, v in heads)
                heads += [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"), (b"x-frame-options", b"DENY"),
                          (b"content-security-policy", (_PAGE_CSP if html else _DATA_CSP).encode())]
                if not any(k.lower() == b"cache-control" for k, _ in heads):
                    heads.append((b"cache-control", b"no-store"))
                msg = {**msg, "headers": heads}
            await send(msg)
        if scope.get("method") not in ("GET", "HEAD"):
            size = next((v for k, v in scope.get("headers") or () if k == b"content-length"), None)
            if size is None or not size.isdigit() or int(size) > BODY_MAX:
                return await _json({"detail": "요청이 너무 큽니다"}, 413)(scope, receive, tag)
        await self.app(scope, receive, tag)


class _Static(StaticFiles):
    """손님 화면의 JS·CSS — 쓸 때마다 서버에 다시 묻게(고친 뒤 옛 파일이 남지 않게)."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


guest.add_middleware(GZipMiddleware, minimum_size=2048)
guest.add_middleware(_Guard)
guest.mount("/share-static", _Static(directory=STATIC), name="share-static")


def _addr(request: Request) -> str:
    """키 넣기 제한에 쓰는 손님 주소 — 접속한 쪽 주소. 이 PC 안에서 온 요청(터널이 넘긴 것)이면 터널이 적어 준 주소(CF-Connecting-IP → X-Forwarded-For 첫 값),
    터널이 안 적어 줬으면 ""(모름 — 주소별 잠금은 세지 않고 공유 하나의 상한만: 한 사람이 틀린 것으로 터널 뒤의 모두를 잠그지 않게)."""
    peer = request.client.host if request.client else ""
    if peer in ("127.0.0.1", "::1"):
        fwd = request.headers.get("cf-connecting-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0]
        return fwd.strip()[:64]
    return peer


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


def _open(sid) -> dict:
    rec = share.get(sid) if share.enabled() else None
    if rec is None or not rec.get("active"):
        raise HTTPException(GONE, "공유가 끝났거나 없는 링크입니다")   # 410 — 손님 화면이 「없어진 문단」(404)과 가른다
    return rec


def _doc(rec):
    """그 공유의 문서 세션 — 문서(작업)가 없어졌으면 410(8114 쪽의 오류 글을 손님에게 넘기지 않는다)."""
    try:
        return OPS.session(rec["doc"])
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(GONE, "공유가 끝났습니다(문서가 없습니다)") from e
        raise


def _guest(sid, request) -> tuple[dict, dict]:
    rec = _open(sid)
    me = share.who(sid, request.cookies.get(COOKIE + sid))
    if me is None:
        raise HTTPException(401, "키를 넣어 주세요")
    return rec, me


def _writes(request):
    if request.headers.get("x-share") != "1":   # 다른 사이트가 쿠키만으로 보내는 요청을 막는다
        raise HTTPException(400, "잘못된 요청입니다")


def _free(sid, block, me):
    other = share.holder(sid, block, but=me["id"])
    if other is not None:
        raise HTTPException(409, f"{other['name']} 님이 작성 중인 문단입니다")


_FMT = ("font", "sizePt", "bold", "italic", "underline", "color", "align", "lineSpacingPct", "firstLineMm", "indentLeftMm", "indentRightMm",
        "spaceBeforePt", "spaceAfterPt", "script", "wordBreak")
_CELL = ("id", "row", "col", "rowSpan", "colSpan", "fill", "valign", "marginsMm", "widthMm", "heightMm", "bf")


def _fmt(f):
    return {k: f[k] for k in _FMT if f.get(k) not in (None, False, 0, 0.0, "")} if f else None


def slim(blocks) -> list:
    """블록에서 손님 화면이 쓰는 키만(② §6) — 줄 배치·스타일 이름 같은 것은 뺀다(연구개발계획서 양식 6.5 MB → 3분의 1)."""
    out = []
    for b in blocks or ():
        t = b.get("type")
        if t == "paragraph":
            x = {"id": b["id"], "type": t, "text": b.get("text") or "", "format": _fmt(b.get("format"))}
            if b.get("runs"):
                x["runs"] = [{"text": r.get("text") or "", "format": _fmt(r.get("format"))} for r in b["runs"]]
            if (b.get("list") or {}).get("label") or b.get("outlineNum"):   # 자동 번호 · 개요 번호(한글이 찍는 글머리 — 주인 화면과 같이 보인다)
                x["label"] = (b.get("list") or {}).get("label") or b["outlineNum"]
            if b.get("pics"):  # 글 속 그림 — 글과 같은 줄의 그 자리에 그린다(spec_hwpx_웹편집 ② §3-6)
                x["pics"] = [{k: q.get(k) for k in ("id", "at", "media", "widthMm", "heightMm")} for q in b["pics"]]
        elif t == "table":
            x = {"id": b["id"], "type": t, "nRows": b.get("nRows"), "nCols": b.get("nCols"), "borderFills": b.get("borderFills") or {},
                 "cells": [{**{k: c[k] for k in _CELL if c.get(k) is not None}, "blocks": slim(c.get("blocks"))} for c in b.get("cells") or ()]}
        elif t == "image":
            x = {"id": b["id"], "type": t, "media": b.get("media"), "widthMm": b.get("widthMm"), "heightMm": b.get("heightMm")}
        else:
            continue
        for k in ("align", "inlineRow", "inlineOf", "captionOf", "page"):
            if b.get(k) is not None:
                x[k] = b[k]
        out.append(x)
    return out


def _page() -> Response:
    try:
        html = (STATIC / "guest.html").read_text("utf-8")
    except OSError as e:
        raise HTTPException(500, "손님 화면 파일이 없습니다") from e
    return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@guest.get("/s/{sid}")
def g_page(sid: str):
    return _page()


@guest.get("/s/{sid}/info")
def g_info(sid: str, request: Request):
    """{active, joined} — 키 없이는 문서 이름도 안 준다."""
    rec = share.get(sid) if share.enabled() else None
    on = bool(rec and rec.get("active"))
    return {"active": on, "joined": bool(on and share.who(sid, request.cookies.get(COOKIE + sid)))}


@guest.post("/s/{sid}/join")
def g_join(sid: str, request: Request, body: dict = Body(default={})):
    """{key, name} → {me} + 세션 쿠키. 400 이름 없음 · 403 키 틀림 · 429 잠금(wait 초) · 409 자리 없음 · 404 없는 공유."""
    _writes(request)
    rec, addr = _open(sid), _addr(request)
    if not share.clean_name(body.get("name")):
        raise HTTPException(400, "이름을 넣어 주세요")
    wait = share.locked(sid, addr)
    if wait > 0:
        return _json({"detail": f"키를 여러 번 틀렸습니다 — {math.ceil(wait)}초 뒤에 다시 넣어 주세요", "wait": math.ceil(wait)}, 429)
    if not share.key_ok(rec, body.get("key")):
        share.failed(sid, addr)
        return _json({"detail": "키가 맞지 않습니다", "wait": math.ceil(share.locked(sid, addr))}, 403)
    share.passed(sid, addr)
    try:
        token, me = share.join(sid, body.get("name"))
    except share.ShareError as e:
        _raise(e)
    resp = _json({"me": me})
    resp.set_cookie(COOKIE + sid, token, max_age=share.TOKEN_IDLE, httponly=True, samesite="strict", path=f"/s/{sid}", secure=_https(request))
    return resp


@guest.post("/s/{sid}/leave")
def g_leave(sid: str, request: Request):
    _writes(request)
    share.leave(sid, request.cookies.get(COOKIE + sid))
    resp = _json({"ok": True})
    resp.delete_cookie(COOKIE + sid, path=f"/s/{sid}")
    return resp


@guest.get("/s/{sid}/doc")
def g_doc(sid: str, request: Request):
    """문서 {name, host, rev, epoch, blocks, me, people} — 블록은 손님 화면이 쓰는 키만."""
    rec, me = _guest(sid, request)
    feed = _feed(rec["doc"], _doc(rec))  # 문서를 읽기 전에 — 읽은 차례 뒤의 편집이 빠짐없이 적히게
    d = OPS.doc(rec["doc"])
    return _json({"name": d["name"], "host": rec["host"], "rev": d["rev"], "epoch": feed.epoch, "blocks": slim(d["blocks"]), "me": me,
                  "people": share.people(sid)})


@guest.get("/s/{sid}/changes")
def g_changes(sid: str, request: Request, since: int = -1, epoch: str = "", block: str = ""):
    """남의 변경(② §4) + 사람들 · block = 내가 지금 커서를 둔 문단(남이 먼저 잡았으면 denied 에 그 사람)."""
    rec, me = _guest(sid, request)
    denied = share.touch(sid, me["id"], block[:40] or None)
    out = _feed(rec["doc"], _doc(rec)).read(since, epoch, me["id"])
    for it in out.get("items") or ():
        if it["t"] == "tops":
            it["blocks"] = slim(it["blocks"])
    return _json({**out, "people": share.people(sid), "denied": denied})


@guest.patch("/s/{sid}/blocks/{bid}")
def g_patch(sid: str, bid: str, request: Request, body: dict = Body(default={})):
    """문단 글 고침 {text} → {id, text, rev}. 409 남이 작성 중."""
    rec, me = _guest(sid, request)
    _writes(request)
    text = body.get("text")
    if not isinstance(text, str) or len(text) > TEXT_MAX:
        raise HTTPException(400, f"글은 {TEXT_MAX:,}자까지입니다")
    _free(sid, bid, me)
    share.touch(sid, me["id"], bid)
    _feed(rec["doc"], _doc(rec))
    with _acting(me["id"]):
        r = OPS.patch(rec["doc"], bid, {"text": _CTRL.sub("", text.replace("\r", "").replace("\n", " "))})
    return _json({"id": r["id"], "text": r["text"], "rev": r["rev"]})


def _struct(rec, me, fn, body):
    feed = _feed(rec["doc"], _doc(rec))
    with _acting(me["id"]):
        r = fn(rec["doc"], body)
    if not isinstance(r, dict):          # 표준에 어긋나 되돌린 편집(422) — 까닭 글만 넘긴다(8114 의 판정 전체는 손님에게 주지 않는다)
        try:
            detail = json.loads(r.body).get("detail")
        except (ValueError, AttributeError):
            detail = None
        return _json({"detail": detail if isinstance(detail, str) else "표준에 어긋나는 편집이라 되돌렸습니다"}, getattr(r, "status_code", 422))
    r = jsonable_encoder(r)
    feed.fill(r.get("rev"), r)
    tops = r.get("tops")
    return _json({"rev": r.get("rev"), "focus": r.get("focus"), "reload": not tops,
                  "drop": (tops or {}).get("drop") or [], "blocks": slim((tops or {}).get("blocks"))})


@guest.post("/s/{sid}/split")
def g_split(sid: str, request: Request, body: dict = Body(default={})):
    """줄 나누기 {id, offset} → {rev, drop, blocks, focus}."""
    rec, me = _guest(sid, request)
    _writes(request)
    bid, off = body.get("id"), body.get("offset")
    if not isinstance(bid, str) or not isinstance(off, int) or isinstance(off, bool) or off < 0:
        raise HTTPException(400, "id 와 offset 이 필요합니다")
    _free(sid, bid, me)
    return _struct(rec, me, OPS.split, {"id": bid, "offset": off})


@guest.post("/s/{sid}/merge")
def g_merge(sid: str, request: Request, body: dict = Body(default={})):
    """줄 합치기 {id, dir: prev|next} → {rev, drop, blocks, focus}."""
    rec, me = _guest(sid, request)
    _writes(request)
    bid, way = body.get("id"), body.get("dir")
    if not isinstance(bid, str) or way not in ("prev", "next"):
        raise HTTPException(400, "id 와 dir(prev|next) 이 필요합니다")
    _free(sid, bid, me)
    return _struct(rec, me, OPS.merge, {"id": bid, "dir": way})


@guest.get("/s/{sid}/media")
def g_media(sid: str, request: Request, name: str = ""):
    rec, _ = _guest(sid, request)
    _doc(rec)
    return OPS.media(rec["doc"], name)
