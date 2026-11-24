"""계정(spec_계정 ② §1 · §2) — 저장 · 비밀번호 해시 · 로그인 쿠키 값. 순수 모듈(서버 · 끝점을 가져오지 않는다 — 끝점 · 로그인 문은 app/accounts_api.py).

저장 = %LOCALAPPDATA%\\NewFileManager\\accounts.json(env NFM_ACCOUNTS): {secret, users{이름: {salt, hash, state, admin, created}}}.
상태 = pending(승인 대기) · approved(승인됨) · blocked(막음). 관리자 = ADMIN 하나 — 파일에 없으면 처음 비밀번호(이름과 같다)로 만든다(사용자 2026-11-24 "관리자 모드 sscb/sscb").
쿠키 값 = 「이름.만료.서명」 — 서명은 파일의 비밀 값 + 그 계정의 비밀번호 해시로 짓는다(서버를 다시 켜도 남고 · 비밀번호를 바꾸면 풀린다)."""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from app import works

ADMIN = "sscb"
NAME = re.compile(r"^[a-z0-9_]{2,20}$")   # 작업 폴더의 뿌리 이름으로 쓴다(works.ACCOUNTS_DIR/<이름>) — 경로 글자를 받지 않는다
PW_MIN, PW_MAX = 4, 200
STATES = ("pending", "approved", "blocked")
TOKEN_DAYS = 30
_ROUNDS = 200_000
_lock = threading.RLock()


def path() -> Path:
    return Path(os.environ.get("NFM_ACCOUNTS") or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "accounts.json")


def _hash(password, salt) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _ROUNDS).hex()


def _user(password, state="pending", admin=False) -> dict:
    salt = secrets.token_hex(16)
    return {"salt": salt, "hash": _hash(password, salt), "state": state, "admin": admin, "created": time.time()}


def _load() -> dict:
    """_lock 안. 파일이 없거나 관리자가 없으면 만들어 쓴다. 깨진 파일은 덮지 않고 ValueError(계정을 조용히 비우지 않는다)."""
    p = path()
    data = {"secret": secrets.token_hex(32), "users": {}}
    if p.exists():
        try:
            data = json.loads(p.read_text("utf-8"))
            assert isinstance(data.get("secret"), str) and isinstance(data.get("users"), dict)
        except (ValueError, AssertionError, AttributeError) as exc:
            raise ValueError(f"계정 파일을 읽지 못했습니다: {p}") from exc
    if ADMIN not in data["users"]:
        data["users"][ADMIN] = _user(ADMIN, "approved", True)
        _save(data)
    return data


def _save(data):
    works._write(path(), json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def _view(name, u) -> dict:
    return {"name": name, "state": u["state"], "admin": bool(u.get("admin")), "created": u.get("created")}


def _check(name, password):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("이름은 영문 소문자 · 숫자 · _ 로 2~20자입니다")
    if not isinstance(password, str) or not PW_MIN <= len(password) <= PW_MAX:
        raise ValueError(f"비밀번호는 {PW_MIN}자 이상입니다")


def users() -> list[dict]:
    with _lock:
        return [_view(n, u) for n, u in sorted(_load()["users"].items(), key=lambda x: x[1].get("created") or 0)]


def join(name, password) -> dict:
    """가입 신청 → 승인 대기. ValueError = 꼴 · KeyError = 이미 있는 이름."""
    _check(name, password)
    with _lock:
        data = _load()
        if name in data["users"]:
            raise KeyError(name)
        data["users"][name] = _user(password)
        _save(data)
        return _view(name, data["users"][name])


def verify(name, password) -> dict | None:
    """이름 · 비밀번호가 맞으면 그 계정(상태와 무관) | None."""
    with _lock:
        u = _load()["users"].get(name) if isinstance(name, str) else None
    if u is None or not isinstance(password, str) or not hmac.compare_digest(_hash(password, u["salt"]), u["hash"]):
        return None
    return _view(name, u)


def _sign(secret, u, name, exp) -> str:
    return hmac.new(bytes.fromhex(secret), f"{name}.{exp}.{u['hash']}".encode(), hashlib.sha256).hexdigest()


def token(name) -> str:
    with _lock:
        data = _load()
        exp = int(time.time()) + TOKEN_DAYS * 86400
        return f"{name}.{exp}.{_sign(data['secret'], data['users'][name], name, exp)}"


def who(tok) -> dict | None:
    """쿠키 값 → 승인된 계정 | None(꼴 · 만료 · 서명 · 없는 계정 · 승인 전 · 막음 — 요청마다 상태를 다시 본다)."""
    try:
        name, exp, sig = tok.split(".")
        exp = int(exp)
    except (AttributeError, ValueError):
        return None
    if exp < time.time():
        return None
    try:
        with _lock:
            data = _load()
    except ValueError:
        return None
    u = data["users"].get(name)
    if u is None or u["state"] != "approved" or not hmac.compare_digest(sig, _sign(data["secret"], u, name, exp)):
        return None
    return _view(name, u)


def change(name, state=None, password=None) -> dict:
    """상태 · 비밀번호를 바꾼다. KeyError = 없는 계정 · ValueError = 꼴 · 관리자의 상태는 못 바꾼다."""
    if state is not None and state not in STATES:
        raise ValueError("상태는 pending · approved · blocked")
    if password is not None:
        _check(name, password)
    with _lock:
        data = _load()
        u = data["users"][name]
        if state is not None and state != u["state"]:
            if u.get("admin"):
                raise ValueError("관리자 계정은 막거나 대기로 돌릴 수 없습니다")
            u["state"] = state
        if password is not None:
            u.update(salt=(salt := secrets.token_hex(16)), hash=_hash(password, salt))
        _save(data)
        return _view(name, u)


def remove(name):
    """계정을 지운다(작업 폴더는 그대로 — spec_계정 ② §1). KeyError = 없는 계정 · ValueError = 관리자."""
    with _lock:
        data = _load()
        if data["users"][name].get("admin"):
            raise ValueError("관리자 계정은 지울 수 없습니다")
        del data["users"][name]
        _save(data)
