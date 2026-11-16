"""hwpx 공유(spec_공유) — 공유 기록 · 키 · 손님 세션 · 작성 중 · 변경 알림. 순수 로직: 웹 틀도 문서 객체도 모른다(표준 라이브러리만).

끝점·공유 포트·공유폴더 저장은 app/share_api.py 가 이 모듈 위에 얹는다. 다른 모듈은 이 모듈을 부르지 않는다(② §1).
- 기록 파일 shares.json(② §2): env NFM_SHARES(파일 경로 · off·0 = 끔) → 없으면 작업 저장소 폴더의 옆(configure 가 받은 store) → 작업 저장이 꺼져 있으면 공유도 끔.
- 키는 해시(scrypt)만 남긴다. 손님 세션·작성 중·변경 알림은 메모리에만(서버를 다시 켜면 손님은 키를 다시 넣는다).
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

ID = re.compile(r"^[0-9a-f]{16}$")
KEY_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 헷갈리는 I·O·0·1 없음(32글자 — 12자 = 60비트)
KEY_LEN = 12
NAME_MAX = 20          # 사람 이름(공백 정리 뒤)
GUESTS_MAX = 12        # 공유 하나에 같은 때 들어와 있는 손님
ONLINE = 20.0          # 이 안에 소식이 있던 사람만 「들어와 있음」(초)
HOLD = 8.0             # 작성 중이 풀리는 때(초 — 소식이 없으면)
TOKEN_IDLE = 12 * 3600  # 손님 세션이 사라지는 때(초 — 소식이 없으면)
FAIL_MAX, FAIL_LOCK, FAIL_LOCK_MAX = 5, 60.0, 3600.0      # 같은 주소: 5번 틀리면 60초(틀릴 때마다 두 배 · 최대 1시간)
SHARE_FAILS, SHARE_WINDOW, SHARE_LOCK = 50, 600.0, 600.0  # 공유 하나: 10분에 50번 틀리면 10분
FEED_KEEP, FEED_AGE, FEED_WAIT = 200, 180.0, 1.5          # 변경 알림: 적어 두는 수 · 나이(초) · 응답을 기다리는 때(초)
COLORS = ("#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#b45309", "#4d7c0f")
HOST = "host"          # 주인의 사람 id

_lock = threading.RLock()
_store = None          # 작업 저장소 뿌리를 주는 함수(configure) — 기록 파일의 기본 자리
_cache = None          # (경로, 읽은 것) — 파일은 이 프로세스만 쓴다


class ShareError(Exception):
    """공유 오류 — code 가 HTTP 상태."""

    def __init__(self, code, msg, **more):
        super().__init__(msg)
        self.code, self.more = code, more


# ---- 기록 파일 ---------------------------------------------------------------------------------------

def configure(store=None):
    """store() -> 작업 저장소 폴더 | None. 기록 파일의 기본 자리가 그 옆이다(임시 작업 폴더로 띄운 서버는 제 임시 기록을 쓴다)."""
    global _store, _cache
    with _lock:
        _store, _cache = store, None


def path() -> Path | None:
    env = os.environ.get("NFM_SHARES")
    if env is not None and env.strip().lower() in ("off", "0", ""):
        return None
    root = _store() if _store else None
    if _store is not None and not root:   # 작업 저장이 꺼져 있다 — 공유할 작업이 없다(env 가 파일 경로여도 끔)
        return None
    return Path(env) if env else Path(root).parent / "shares.json" if root else None


def enabled() -> bool:
    return path() is not None


def _read():
    global _cache
    p = path()
    if p is None:
        return {"version": 1, "url": "", "shares": {}}
    if _cache is not None and _cache[0] == p:
        return _cache[1]
    try:
        data = json.loads(p.read_text("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("shares"), dict):
            raise ValueError("꼴이 다름")
    except FileNotFoundError:
        data = {"version": 1, "url": "", "shares": {}}
    except (OSError, ValueError) as e:
        raise ShareError(500, f"공유 기록 파일을 읽지 못했습니다({p.name}): {e}") from e
    _cache = (p, data)
    return data


def _write(data):
    global _cache
    p = path()
    if p is None:
        raise ShareError(503, "공유가 꺼져 있습니다")
    write_file(p, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"), tmp_name=p.name + f".tmp{os.getpid()}")
    _cache = (p, data)


def write_file(target: Path, data: bytes, tmp_name=None):
    """같은 폴더의 임시 파일에 쓰고 바꿔 넣는다 — 대상을 다른 손잡이(동기화 프로그램·백신)가 잠깐 잡고 있으면 몇 번 다시(references/Windows_파일_바꿔넣기.md).
    공유폴더에서는 임시 이름을 `~$….tmp` 로(OneDrive 가 동기화하지 않는 이름 — references/SharePoint_공유폴더.md)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(tmp_name or f"~${target.stem[:40]}.tmp")
    tmp.write_bytes(data)
    for k in range(8):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if k == 7:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05 * (k + 1))


# ---- 키 ----------------------------------------------------------------------------------------------

def new_key() -> str:
    return "".join(secrets.choice(KEY_ABC) for _ in range(KEY_LEN))


def show_key(key: str) -> str:
    return "-".join(key[i:i + 4] for i in range(0, len(key), 4))


def clean_key(text) -> str:
    """사람이 넣은 키 — 대문자로, 글자·숫자만(줄표·공백은 뺀다)."""
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())[:64]


def _hash(key: str, salt: str) -> str:
    return hashlib.scrypt(key.encode("utf-8"), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex()


def key_ok(rec, text) -> bool:
    key = clean_key(text)
    return bool(key) and hmac.compare_digest(_hash(key, rec["salt"]), rec["key"])


def clean_name(text) -> str:
    return " ".join(str(text or "").split())[:NAME_MAX]


# ---- 공유 기록 ---------------------------------------------------------------------------------------

def records() -> list[dict]:
    with _lock:
        return [dict(r) for r in _read()["shares"].values()]


def active() -> list[dict]:
    return [r for r in records() if r.get("active")]


def get(sid) -> dict | None:
    if not isinstance(sid, str) or not ID.match(sid):
        return None
    with _lock:
        r = _read()["shares"].get(sid)
        return dict(r) if r else None


def by_doc(doc) -> dict | None:
    """그 문서(작업)의 켜진 공유 | None."""
    with _lock:
        return next((dict(r) for r in _read()["shares"].values() if r.get("active") and r.get("doc") == doc), None)


def last_of(doc) -> dict | None:
    """그 문서의 가장 최근 공유(꺼진 것도) — 다시 켤 때 폴더·이름을 미리 채운다."""
    with _lock:
        rows = [r for r in _read()["shares"].values() if r.get("doc") == doc]
        return dict(max(rows, key=lambda r: r.get("created", 0))) if rows else None


def base_url() -> str:
    """주인이 정한 접속 주소(터널 등) → env NFM_SHARE_URL → ""(부르는 쪽이 사내망 주소로)."""
    with _lock:
        url = (_read().get("url") or "").strip() if enabled() else ""
    return (url or os.environ.get("NFM_SHARE_URL", "").strip()).rstrip("/")


def set_base_url(url):
    url = str(url or "").strip().rstrip("/")
    if url and not re.match(r"^https?://[^\s/]+(:\d+)?(/[^\s]*)?$", url):
        raise ShareError(400, "접속 주소는 http:// 또는 https:// 로 시작하는 주소여야 합니다")
    with _lock:
        data = _read()
        data["url"] = url
        _write(data)
    return url


def create(doc, name, folder, file, host) -> tuple[dict, str]:
    """새 공유를 켠다 → (기록, 키 — 여기서만 나온다). 그 문서에 켜진 공유가 있으면 409."""
    with _lock:
        data = _read()
        if any(r.get("active") and r.get("doc") == doc for r in data["shares"].values()):
            raise ShareError(409, "이 문서는 이미 공유 중입니다")
        sid, key, salt = secrets.token_hex(8), new_key(), secrets.token_hex(16)
        rec = {"id": sid, "doc": doc, "name": name, "host": clean_name(host) or "주인", "folder": str(folder), "file": file, "link_file": "",
               "salt": salt, "key": _hash(key, salt), "created": time.time(), "active": True, "stopped": None,
               "saved": {"rev": None, "at": None, "sha": None, "error": None}}
        data["shares"][sid] = rec
        _prune(data)
        _write(data)
        return dict(rec), key


def _prune(data, keep=30):
    """꺼진 공유 기록은 최근 것만 남긴다."""
    off = sorted((r for r in data["shares"].values() if not r.get("active")), key=lambda r: r.get("stopped") or 0)
    for r in off[:-keep] if len(off) > keep else []:
        data["shares"].pop(r["id"], None)


def update(sid, **fields) -> dict | None:
    with _lock:
        data = _read()
        rec = data["shares"].get(sid)
        if rec is None:
            return None
        for k, v in fields.items():
            if k == "saved":
                rec["saved"] = {**(rec.get("saved") or {}), **v}
            else:
                rec[k] = v
        _write(data)
        return dict(rec)


def rekey(sid) -> str:
    """새 키 — 들어와 있던 손님은 모두 내보낸다."""
    key, salt = new_key(), secrets.token_hex(16)
    if update(sid, salt=salt, key=_hash(key, salt)) is None:
        raise ShareError(404, "그런 공유가 없습니다")
    drop_guests(sid)
    return key


def stop(sid) -> dict | None:
    rec = update(sid, active=False, stopped=time.time())
    drop_room(sid)
    return rec


# ---- 키 넣기 제한 ------------------------------------------------------------------------------------

_fails = {}     # (sid, 주소) → {n, until}
_wide = {}      # sid → {times[], until}


def locked(sid, addr, now=None) -> float:
    """지금 키를 넣을 수 없으면 남은 초, 아니면 0."""
    now = time.time() if now is None else now
    with _lock:
        a, w = _fails.get((sid, addr)) if addr else None, _wide.get(sid)
        return max(0.0, (a or {}).get("until", 0) - now, (w or {}).get("until", 0) - now)


def failed(sid, addr, now=None):
    now = time.time() if now is None else now
    with _lock:
        if addr:   # 주소를 모르는 요청은 공유 하나의 상한만 센다 — 한 사람이 틀린 것으로 모두를 잠그지 않게
            a = _fails.setdefault((sid, addr), {"n": 0, "until": 0})
            a["n"] += 1
            if a["n"] >= FAIL_MAX:
                a["until"] = now + min(FAIL_LOCK_MAX, FAIL_LOCK * 2 ** (a["n"] - FAIL_MAX))
        w = _wide.setdefault(sid, {"times": [], "until": 0})
        w["times"] = [t for t in w["times"] if now - t < SHARE_WINDOW] + [now]
        if len(w["times"]) >= SHARE_FAILS:
            w["until"], w["times"] = now + SHARE_LOCK, []
        if len(_fails) > 5000:  # 오래된 것부터 비운다
            for k in sorted(_fails, key=lambda k: _fails[k]["until"])[:1000]:
                _fails.pop(k, None)


def passed(sid, addr):
    with _lock:
        _fails.pop((sid, addr), None)


# ---- 사람들 · 작성 중 --------------------------------------------------------------------------------

class Room:
    """공유 하나에 들어와 있는 사람들(메모리)."""

    def __init__(self):
        self.people = {}    # pid → {id, name, color, host, seen, block, joined}
        self.tokens = {}    # 손님 세션 토큰 → pid
        self.n = 0          # 들어온 차례(색)


_rooms = {}


def _room(sid) -> Room:
    return _rooms.setdefault(sid, Room())


def _fresh(p, now, within=ONLINE):
    return now - p["seen"] < within


def join(sid, name, now=None) -> tuple[str, dict]:
    """손님이 키를 맞혔다 → (세션 토큰, 사람). 자리가 없으면 409."""
    now = time.time() if now is None else now
    name = clean_name(name)
    if not name:
        raise ShareError(400, "이름을 넣어 주세요")
    with _lock:
        room = _room(sid)
        _sweep(room, now)
        if sum(1 for p in room.people.values() if not p["host"] and _fresh(p, now)) >= GUESTS_MAX:
            raise ShareError(409, f"지금은 자리가 없습니다(같은 때 {GUESTS_MAX}명까지)")
        pid, token = "g" + secrets.token_hex(4), secrets.token_urlsafe(32)
        person = {"id": pid, "name": name, "color": COLORS[room.n % len(COLORS)], "host": False, "seen": now, "block": None, "joined": now}
        room.n += 1
        room.people[pid], room.tokens[token] = person, pid
        return token, _public(person)


def _sweep(room, now):
    for t, pid in list(room.tokens.items()):
        p = room.people.get(pid)
        if p is None or now - p["seen"] > TOKEN_IDLE:
            room.tokens.pop(t, None)
            room.people.pop(pid, None)


def who(sid, token, now=None) -> dict | None:
    """세션 토큰의 손님 | None(없는 토큰 · 내보낸 손님)."""
    if not token:
        return None
    now = time.time() if now is None else now
    with _lock:
        room = _rooms.get(sid)
        pid = room.tokens.get(token) if room else None
        p = room.people.get(pid) if pid else None
        if p is None:
            return None
        if now - p["seen"] > TOKEN_IDLE:   # 오래 소식이 없던 세션 — 끝낸다
            room.tokens.pop(token, None)
            room.people.pop(pid, None)
            return None
        p["seen"] = now
        return _public(p)


def leave(sid, token):
    with _lock:
        room = _rooms.get(sid)
        if room:
            room.people.pop(room.tokens.pop(token, None), None)


def drop_guests(sid):
    with _lock:
        room = _rooms.get(sid)
        if room:
            room.tokens.clear()
            for pid in [k for k, p in room.people.items() if not p["host"]]:
                room.people.pop(pid, None)


def drop_room(sid):
    with _lock:
        _rooms.pop(sid, None)
        _wide.pop(sid, None)
        for k in [k for k in _fails if k[0] == sid]:
            _fails.pop(k, None)


def host_in(sid, name, now=None) -> dict:
    """주인의 소식(주인 화면이 변경을 읽을 때마다) → 사람."""
    now = time.time() if now is None else now
    with _lock:
        room = _room(sid)
        p = room.people.get(HOST)
        if p is None:
            p = room.people[HOST] = {"id": HOST, "name": clean_name(name) or "주인", "color": "#111827", "host": True, "seen": now, "block": None, "joined": now}
        p["seen"], p["name"] = now, clean_name(name) or p["name"]
        return _public(p)


def holder(sid, block, now=None, but=None) -> dict | None:
    """그 문단을 작성 중인 사람(but = 이 사람은 빼고) | None."""
    if not block:
        return None
    now = time.time() if now is None else now
    with _lock:
        room = _rooms.get(sid)
        for p in (room.people.values() if room else ()):
            if p["block"] == block and p["id"] != but and _fresh(p, now, HOLD):
                return _public(p)
    return None


def touch(sid, pid, block, now=None) -> dict | None:
    """사람의 소식 + 지금 커서를 둔 문단(block — 없으면 None). 남이 먼저 잡은 문단이면 그 사람을 돌려주고(못 잡음) 내 작성 중은 비운다."""
    now = time.time() if now is None else now
    with _lock:
        room = _rooms.get(sid)
        p = room.people.get(pid) if room else None
        if p is None:
            return None
        p["seen"] = now
        other = holder(sid, block, now, but=pid) if block else None
        p["block"] = None if other else (block or None)
        return other


def people(sid, now=None) -> list[dict]:
    now = time.time() if now is None else now
    with _lock:
        room = _rooms.get(sid)
        rows = sorted((p for p in (room.people.values() if room else ()) if _fresh(p, now)), key=lambda p: (not p["host"], p["joined"]))
        return [{**_public(p), "block": p["block"] if _fresh(p, now, HOLD) else None} for p in rows]


def _public(p):
    return {"id": p["id"], "name": p["name"], "color": p["color"], "host": p["host"]}


# ---- 변경 알림 ---------------------------------------------------------------------------------------

class Feed:
    """문서 하나의 편집을 차례(rev) 순으로 적어 둔 것(② §4). note 는 편집 한 번마다(세션 잠금 안 — 차례 순), fill 은 그 편집의 응답이 오면, read 는 화면이 읽을 때.
    항목 = {rev, by(한 사람 id), t(text | wait | tops | reload), ids(그 편집이 닿은 문단·블록 id), at} — text 는 id·text, tops 는 resp(그 편집의 응답)."""

    def __init__(self, rev):
        self.lock = threading.Lock()
        self._reset(rev)

    def _reset(self, rev):
        self.epoch, self.base, self.last, self.items = secrets.token_hex(4), rev, rev, []

    def note(self, rev, kind, by, fields, now=None):
        now = time.time() if now is None else now
        with self.lock:
            if rev <= self.last:      # 차례가 뒤로 갔다(작업을 다시 엶 등) — 묶음을 새로: 읽는 쪽은 모두 문서를 다시 읽는다
                self._reset(rev)
                return
            if rev > self.last + 1:   # 못 본 편집이 있다 — 그 자리는 「다시 읽기」
                self.items.append({"rev": rev - 1, "by": None, "t": "reload", "ids": set(), "at": now})
            text = fields.get("after")
            if kind in ("text", "revert") and not fields.get("format") and isinstance(fields.get("id"), str) and isinstance(text, str):
                item = {"rev": rev, "by": by, "t": "text", "id": fields["id"], "text": text, "ids": {fields["id"]}, "at": now}
            else:
                item = {"rev": rev, "by": by, "t": "wait", "kind": kind, "ids": set(), "at": now}
            self.items.append(item)
            self.last = rev
            self._trim(now)

    def _trim(self, now):
        cut = max(len(self.items) - FEED_KEEP, 0)
        while cut < len(self.items) - 1 and now - self.items[cut]["at"] > FEED_AGE:
            cut += 1
        if cut:
            self.base = self.items[cut - 1]["rev"]
            del self.items[:cut]

    def fill(self, rev, resp) -> bool:
        """그 차례 편집의 응답(tops = 바뀐 최상위 블록 {drop, blocks}) — 자리를 채운다. 못 채우면(자리가 없음 · 이미 「다시 읽기」) False."""
        tops = resp.get("tops") if isinstance(resp, dict) else None
        if not isinstance(rev, int) or not isinstance(tops, dict) or not isinstance(tops.get("blocks"), list):
            return False
        with self.lock:
            for it in reversed(self.items):
                if it["rev"] == rev:
                    if it["t"] != "wait":
                        return False
                    it.update(t="tops", resp=resp, ids=_ids(tops["blocks"]) | {i for i in tops.get("drop") or () if isinstance(i, str)})
                    return True
                if it["rev"] < rev:
                    break
        return False

    def _reload(self):
        return {"epoch": self.epoch, "rev": self.last, "reload": True}

    def read(self, since, epoch, by, full=False, now=None) -> dict:
        """since(읽는 쪽이 아는 rev) 뒤의 남의 편집 → {epoch, rev, items} | {epoch, rev, reload: True}(문서를 다시 읽어라).
        epoch 가 빈 글이면 「방금 문서를 읽었다」 — since 만 본다. full = 주인 화면(응답을 통째로 — 화면이 제 편집의 응답처럼 다시 쓴다), 아니면 {drop, blocks} 만.
        읽는 쪽의 제 편집은 건너뛴다(제 응답으로 이미 화면에 있다). 남의 편집이 **그 뒤 차례의 내 편집**과 같은 문단에 닿으면: 글 고침은 버리고(내 글이 더 새것),
        블록 바꿔 끼우기는 「다시 읽기」 — 옛 블록이 내 새 글을 덮지 않게."""
        now = time.time() if now is None else now
        with self.lock:
            if (epoch and epoch != self.epoch) or not isinstance(since, int) or isinstance(since, bool) or since < self.base:
                return self._reload()
            mine = [o for o in self.items if o["rev"] > since and o["by"] is not None and o["by"] == by]
            out, upto = [], since
            for it in self.items:
                if it["rev"] <= since:
                    continue
                if it["by"] is not None and it["by"] == by:
                    upto = it["rev"]
                    continue
                if it["t"] == "wait":
                    if now - it["at"] < FEED_WAIT:
                        break                                # 곧 채워진다 — 여기까지만(다음 읽기에 이어서)
                    it["t"] = "reload"
                if it["t"] == "reload":
                    return self._reload()
                later = [o for o in mine if o["rev"] > it["rev"]]
                if any(o["t"] == "wait" for o in later):     # 내 편집이 어디에 닿았는지 아직 모른다
                    if any(o["t"] == "wait" and now - o["at"] < FEED_WAIT for o in later):
                        break                                # 그 응답이 곧 온다 — 그때 다시 본다
                    return self._reload()                    # 실행 취소처럼 어디가 바뀌었는지 모르는 내 편집 — 그 앞의 남의 편집을 얹을 수 없다
                if any(o["ids"] & it["ids"] for o in later):
                    if it["t"] == "text":
                        upto = it["rev"]
                        continue
                    return self._reload()
                upto = it["rev"]
                if it["t"] == "text":
                    out.append({"rev": it["rev"], "by": it["by"], "t": "text", "id": it["id"], "text": it["text"]})
                elif full:
                    out.append({"rev": it["rev"], "by": it["by"], "t": "tops", "resp": it["resp"]})
                else:
                    tops = it["resp"]["tops"]
                    out.append({"rev": it["rev"], "by": it["by"], "t": "tops", "drop": tops.get("drop") or [], "blocks": tops["blocks"]})
            return {"epoch": self.epoch, "rev": upto, "items": out}


def _ids(blocks, out=None) -> set:
    """블록들 안의 블록·문단 id(표 칸 안까지)."""
    out = set() if out is None else out
    for b in blocks or ():
        if isinstance(b, dict):
            if isinstance(b.get("id"), str):
                out.add(b["id"])
            for c in b.get("cells") or ():
                _ids(c.get("blocks"), out)
    return out


# ---- 공유폴더의 파일 이름 ----------------------------------------------------------------------------

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_stem(name, fallback="문서") -> str:
    """파일 이름으로 쓸 수 있게(Windows·SharePoint 가 못 쓰는 글자를 뺌 · 끝의 점·공백 정리 · 80자)."""
    stem = _BAD.sub(" ", str(name or "")).strip().strip(".").strip()
    stem = re.sub(r"\s+", " ", stem)[:80].strip()
    return stem or fallback


def free_name(folder: Path, stem: str, ext: str) -> str:
    """그 폴더에 없는 이름 — 있으면 「 (2)」, 「 (3)」 … 을 붙인다(있는 파일을 덮지 않는다)."""
    name, k = f"{stem}{ext}", 2
    while (folder / name).exists():
        name, k = f"{stem} ({k}){ext}", k + 1
        if k > 500:
            raise ShareError(409, "공유폴더에 같은 이름의 파일이 너무 많습니다")
    return name


def url_file(link: str) -> bytes:
    """인터넷 바로가기(.url) — SharePoint·Windows 가 누르면 그 주소를 연다."""
    return f"[InternetShortcut]\r\nURL={link}\r\n".encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
