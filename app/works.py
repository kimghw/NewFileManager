"""작업 저장소(spec_작업 ② §2·§4·§5) — 올린 파일마다 폴더 하나: 원본·지금 편집 상태·기록(log.jsonl)·검증 기록·출력 파일.

폴더 %LOCALAPPDATA%\\NewFileManager\\works\\<작업 id>, env NFM_WORKS(off·0 이면 저장 끔). 서버(server.py)가 세션 상태를 묶어 넘기고
이 모듈은 파일만 다룬다(문서 객체를 모름)."""
import hashlib
import json
import os
import pickle
import re
import shutil
import threading
import time
from pathlib import Path

ID = re.compile(r"^[0-9a-f]{12}$")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def root() -> Path | None:
    env = os.environ.get("NFM_WORKS")
    if env is not None and env.strip().lower() in ("off", "0", ""):
        return None
    if env:
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "works"


def enabled() -> bool:
    return root() is not None


def folder(wid: str) -> Path | None:
    """작업 폴더 — id 꼴(12자 16진)이 아니거나 저장이 꺼져 있으면 None(경로를 받지 않는다)."""
    base = root()
    if base is None or not isinstance(wid, str) or not ID.match(wid):
        return None
    return base / wid


def _lock(wid) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(wid, threading.Lock())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}-{threading.get_ident()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_json(path: Path, obj):
    _write(path, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


# ---- 작업 만들기·목록·지우기 -----------------------------------------------------------------------------

def create(wid, name, fmt, data, source="upload") -> dict | None:
    d = folder(wid)
    if d is None:
        return None
    now = time.time()
    work = {"id": wid, "name": name, "format": fmt, "size": len(data), "sha256": sha256(data), "source": source,
            "created": now, "updated": now, "rev": 0, "edited": 0, "verify": {}}
    with _lock(wid):
        _write(d / f"original.{fmt}", data)
        _write_json(d / "work.json", work)
    log(wid, "create", rev=0, name=name, size=len(data), sha256=work["sha256"], source=source)
    return work


def work(wid) -> dict | None:
    d = folder(wid)
    w = _read_json(d / "work.json") if d else None
    return w if isinstance(w, dict) and w.get("id") == wid else None


def update(wid, **fields) -> dict | None:
    """work.json 필드를 고친다(verify 는 종류별로 합침)."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        w = work(wid)
        if w is None:
            return None
        if "verify" in fields:
            w["verify"] = {**w.get("verify", {}), **fields.pop("verify")}
        w.update(fields, updated=time.time())
        _write_json(d / "work.json", w)
        return w


def list_works() -> list[dict]:
    """최근 바뀐 차례. 못 읽는 폴더는 빼기만 한다(지우지 않음)."""
    base = root()
    if base is None or not base.is_dir():
        return []
    out = []
    for p in base.iterdir():
        if p.is_dir() and ID.match(p.name):
            w = work(p.name)
            if w is not None:
                out.append(w)
    return sorted(out, key=lambda w: w.get("updated", 0), reverse=True)


def delete(wid, tries=6) -> bool:
    """작업 폴더를 지운다. work.json 을 먼저 지워 목록·다시 열기에서 곧바로 빠지게 하고, 나머지는 몇 번 다시 시도한다 —
    Windows 에서 백신·색인기가 막 쓴 파일을 잠깐 잡으면 rmtree 가 일부를 못 지운다(시험이 다른 PC 상태에서 빈 폴더가 남은 일, 2026-11-09)."""
    d = folder(wid)
    if d is None or not d.is_dir():
        return False
    with _lock(wid):
        for k in range(tries):
            try:
                (d / "work.json").unlink(missing_ok=True)
                shutil.rmtree(d)
            except FileNotFoundError:
                pass
            except OSError:
                time.sleep(0.05 * (k + 1))
                continue
            if not d.exists():
                return True
            time.sleep(0.05 * (k + 1))
    return not d.exists()


# ---- 편집 상태 ---------------------------------------------------------------------------------------

def save_state(wid, fmt, snap: dict, state: dict, **summary):
    """snap = struct.snapshot(doc)({"bytes", "dirty", "new"|"blobs", "ids"}), state = 세션 집합·매핑(JSON)."""
    d = folder(wid)
    if d is None:
        return
    # 직렬화를 먼저 끝낸다 — 못 쓰는 값이 있으면 파일을 하나도 안 바꾼다(셋이 어긋난 채 남지 않게)
    pkl = pickle.dumps({k: v for k, v in snap.items() if k != "bytes"}, protocol=pickle.HIGHEST_PROTOCOL)
    js = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with _lock(wid):
        if not (d / "work.json").exists():  # 지운 작업 — 되살리지 않는다
            return
        _write(d / f"current.{fmt}", snap["bytes"])
        _write(d / "doc.pkl", pkl)
        _write(d / "state.json", js)
    if summary:
        update(wid, **summary)


def set_aside_state(wid):
    """못 붙인 편집 상태(current·doc.pkl·state.json)를 <이름>.broken-<시각> 으로 옮긴다 — 지우지 않음."""
    d = folder(wid)
    if d is None:
        return
    tag = time.strftime("%Y%m%d-%H%M%S")
    with _lock(wid):
        for p in [*d.glob("current.*"), d / "doc.pkl", d / "state.json"]:
            if p.is_file() and ".broken-" not in p.name:
                try:
                    os.replace(p, p.with_name(f"{p.name}.broken-{tag}"))
                except OSError:
                    pass


def load(wid) -> dict | None:
    """{work, original, snap | None, state | None} — 편집 상태가 없거나 못 읽으면 snap None(원본으로 연다)."""
    d, w = folder(wid), work(wid)
    if d is None or w is None:
        return None
    fmt = w["format"]
    try:
        original = (d / f"original.{fmt}").read_bytes()
    except OSError:
        return None
    snap = state = None
    try:
        cur = d / f"current.{fmt}"
        if cur.exists() and (d / "doc.pkl").exists():
            snap = {**pickle.loads((d / "doc.pkl").read_bytes()), "bytes": cur.read_bytes()}
            state = _read_json(d / "state.json")
    except Exception:  # noqa: BLE001 — 깨진 묶음: 원본으로 열고 서버가 기록에 남긴다
        snap = state = None
    return {"work": w, "original": original, "snap": snap, "state": state}


# ---- 기록 ------------------------------------------------------------------------------------------

def log(wid, kind, **fields):
    d = folder(wid)
    if d is None:
        return
    line = json.dumps({"t": round(time.time(), 3), "kind": kind, **fields}, ensure_ascii=False, separators=(",", ":"))
    with _lock(wid):
        if not d.is_dir():
            return
        with open(d / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")


def events(wid) -> list[dict]:
    d = folder(wid)
    out = []
    try:
        with open(d / "log.jsonl", encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue  # 쓰다 끊긴 줄
    except (OSError, TypeError):
        pass
    return out


# ---- 검증 기록·출력 파일 ----------------------------------------------------------------------------------

def add_run(wid, kind, record: dict) -> int | None:
    """verify/<n>-<kind>.json 으로 남기고 n 을 돌려준다(작업 안에서 1부터)."""
    d = folder(wid)
    if d is None:
        return None
    with _lock(wid):
        if not (d / "work.json").exists():
            return None
        vd = d / "verify"
        n = 1 + max((int(p.name.split("-", 1)[0]) for p in vd.glob("*-*.json") if p.name.split("-", 1)[0].isdigit()), default=0) \
            if vd.is_dir() else 1
        _write_json(vd / f"{n}-{kind}.json", {"n": n, "kind": kind, **record})
    return n


def runs(wid) -> list[dict]:
    """검증 기록 요약 — 번호 차례."""
    d = folder(wid)
    vd = d / "verify" if d else None
    if vd is None or not vd.is_dir():
        return []
    out = []
    for p in vd.glob("*-*.json"):
        r = _read_json(p)
        if isinstance(r, dict) and isinstance(r.get("n"), int):
            out.append({k: r.get(k) for k in ("n", "kind", "status", "at", "seconds", "revision", "rev", "outputSha")})
    return sorted(out, key=lambda r: r["n"])


def run(wid, n) -> dict | None:
    d = folder(wid)
    vd = d / "verify" if d else None
    if vd is None or not vd.is_dir():
        return None
    for p in vd.glob(f"{int(n)}-*.json"):
        r = _read_json(p)
        if isinstance(r, dict) and r.get("n") == int(n):
            return r
    return None


def last_runs(wid) -> dict:
    """종류마다 마지막 검증 기록 전체 — 다시 열 때 결과로 보인다."""
    last = {}
    for r in runs(wid):
        last[r["kind"]] = r["n"]
    return {k: run(wid, n) for k, n in last.items()}


def add_output(wid, fmt, data: bytes) -> str:
    """outputs/<sha256 앞 16자>.<ext> — 같은 바이트는 한 번만. sha256 전체를 돌려준다."""
    h = sha256(data)
    d = folder(wid)
    if d is not None:
        p = d / "outputs" / f"{h[:16]}.{fmt}"
        with _lock(wid):
            if (d / "work.json").exists() and not p.exists():
                _write(p, data)
    return h


def file_path(wid, which) -> Path | None:
    w, d = work(wid), folder(wid)
    if w is None or which not in ("original", "current"):
        return None
    p = d / f"{which}.{w['format']}"
    if which == "current" and not p.exists():
        p = d / f"original.{w['format']}"
    return p if p.exists() else None


# ---- 부가 기록(spec_구분_기준 ② §4 — 로그 한 줄 + 상세는 결과 파일) ------------------------------------------------

def add_detail(wid, kind, name, record: dict) -> str | None:
    """`<kind>/<name>.json` 에 상세 기록(JSON) — 기록 한 줄에 다 못 싣는 변경 목록 등. 작업 저장이 꺼져 있으면 None."""
    d = folder(wid)
    if d is None:
        return None
    safe = "".join(ch for ch in str(name) if ch.isalnum() or ch in "-_")[:40] or "x"
    with _lock(wid):
        if not (d / "work.json").exists():
            return None
        sub = d / kind
        sub.mkdir(exist_ok=True)
        _write_json(sub / f"{safe}.json", record)
    return f"{kind}/{safe}.json"
