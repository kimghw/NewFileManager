"""저장한 양식 — 워크플로우의 문서 칸(수가 1인 칸)에 넣을 양식 파일과, 워크플로우마다의 설정(고정 · 기본값)을 서버 전체에 둔다(spec_워크플로우 ② §18-9 「양식」 · 고친 규칙 ② §18-12 ⑧).

2026-11-20 사용자 "템플릿은 워크플로우 설정에서 고정 또는 default 값을로 넣을 수 있는 것 까지" → 물어서 받은 답 「양식 파일」. **가벼운 저장 모듈** — 다른 app 코드를 가져오지 않는다(끝점 · 검사는 app/form_files_api.py).
- 자리 = `%LOCALAPPDATA%\\NewFileManager\\form_files\\`(env `NFM_FORM_FILES` 가 폴더 · `off`·`0` 이면 메모리만 — 양식 정보 폴더 `NFM_FORMS` 와 다른 것) =
  `index.json {version, files: [{id, name, file, fmt, kind, sha256, size, at}], slots: {워크플로우 키: {역할: {file, mode}}}, rev}` + 파일 `<id>.<fmt>`.
  id = `f_` + 16진 8자 · name = 화면 이름(1~60자) · file = 올린 파일 이름(보이는 용) · fmt = hwpx · docx(hwp 는 올릴 때 hwpx 로 바꿔서 — 끝점이) · kind = 문서 종류(plan · report · "") · rev = 설정(slots)의 판(바뀔 때마다 +1 — 시작 요청이 읽은 판과 견준다).
- **파일의 내용은 고치지 않는다**(양식은 올린 그대로 — 고치려면 새로 올린다). 파일을 다 쓴 뒤에 목록에 올린다(목록에 있는데 파일이 없는 양식을 만들지 않는다). 같은 내용(sha256 · 형식)을 다시 올리면 있던 양식을 돌려준다.
- 워크플로우 설정(`slots`) = 그 워크플로우의 문서 칸(목적 문서 `target` · 원본 문서 `source` — 수가 1인 칸만: 2026-11-20 사용자 "각 1이 되는것들은 특정 문서로 지정할 수 있도록, default 로")에 건 양식 `{file, mode}` —
  mode = `default`(시작의 칸에 미리 들어가 있고 바꿀 수 있음) · `fixed`(늘 그 양식). 그 칸이 그 워크플로우에서 수가 1인지는 끝점(app/form_files_api.py rule)이 본다. 정의(조립한 워크플로우)와 따로 둔다 — 붙박이도 건다.
- **저장 파일 보호**(app/custom_tasks.py 와 같은 규칙): 목록 파일이 있는데 못 읽으면 읽기는 빈 것(`broken`)이고 쓰지 않는다(`Refused` — 끝점 409). 설정에 쓰는 양식은 못 지운다(`Refused`)."""
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

ID = re.compile(r"f_[0-9a-f]{8}")
FMTS = ("hwpx", "docx")
KINDS = ("", "plan", "report")
MODES = ("default", "fixed")
ROLES = ("target", "source")   # 양식을 걸 수 있는 문서 칸 — 목적 문서 · 원본 문서(수가 1인 칸만 — 끝점이 본다: spec_워크플로우 ② §18-9)
NAME_MAX, FILES_MAX, SIZE_MAX = 60, 200, 200 * 2 ** 20
BROKEN = "저장한 양식의 목록 파일({name})을 읽지 못해 쓰지 않습니다 — 파일을 고치거나 옮긴 뒤 다시 하세요"
IN_USE = "이 양식을 건 워크플로우 설정이 {n}개 있어 지울 수 없습니다 — 그 설정을 먼저 푸세요"
_FIELDS = ("id", "name", "file", "fmt", "kind", "sha256", "size", "at")
_LOCK = threading.RLock()
_MEMORY = {"index": {"version": 0, "files": [], "slots": {}, "rev": 0}, "blobs": {}}


class Refused(ValueError):
    """쓰지 않음(끝점 409 — 글은 화면에 그대로): 목록 파일을 못 읽었거나 · 설정에 쓰는 양식을 지우려 함. 그 밖의 ValueError 는 값이 틀림(400)."""


def root():
    """저장 폴더 Path | None(메모리만)."""
    env = os.environ.get("NFM_FORM_FILES", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "form_files"


def _file_ok(f):
    return (isinstance(f, dict) and isinstance(f.get("id"), str) and bool(ID.fullmatch(f["id"])) and isinstance(f.get("name"), str) and bool(f["name"].strip())
            and f.get("fmt") in FMTS and f.get("kind", "") in KINDS and isinstance(f.get("sha256"), str))


def _slot_ok(v):
    return isinstance(v, dict) and isinstance(v.get("file"), str) and v.get("mode") in MODES


def _parse(obj):
    """목록 파일의 JSON → {version, files[보이는 것 — 꼴이 맞는 것], rows[읽은 그대로], slots, rev, extra, broken}."""
    if not isinstance(obj, dict) or not isinstance(obj.get("files", []), list) or not isinstance(obj.get("slots", {}), dict):
        return {"version": 0, "files": [], "rows": [], "slots": {}, "rev": 0, "extra": {}, "broken": True}
    rows, seen, files = list(obj.get("files", [])), set(), []
    for r in rows:
        if _file_ok(r) and r["id"] not in seen:
            seen.add(r["id"])
            files.append({k: r.get(k, "" if k in ("file", "kind") else 0) for k in _FIELDS})
    slots = {job: {role: dict(v) for role, v in box.items() if role in ROLES and _slot_ok(v)} for job, box in obj.get("slots", {}).items() if isinstance(job, str) and isinstance(box, dict)}
    num = lambda v: v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0  # noqa: E731
    return {"version": num(obj.get("version")), "files": files, "rows": rows, "slots": {j: b for j, b in slots.items() if b}, "rev": num(obj.get("rev")),
            "extra": {k: v for k, v in obj.items() if k not in ("version", "files", "slots", "rev")}, "broken": False}


def _load():
    d = root()
    if d is None:
        return _parse(_MEMORY["index"])
    p = d / "index.json"
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return _parse({})
    except OSError:   # 읽기 오류(바꿔 넣는 중 · 권한) — 이 호출만 못 읽은 것으로(쓰지 않는다)
        return _parse(None)
    try:
        return _parse(json.loads(raw.decode("utf-8")))
    except ValueError:
        return _parse(None)


def _writable(data):
    if data["broken"]:
        raise Refused(BROKEN.format(name="index.json"))


def _atomic(path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save(data, rows=None, slots=None, bump=False):
    """목록을 쓴다(version + 1 · 머리의 모르는 키는 그대로 · 꼴이 틀린 줄도 읽은 그대로) — data = 이 쓰기 앞에 읽은 _load() 의 값."""
    _writable(data)
    out = {**data["extra"], "version": data["version"] + 1, "files": list(data["rows"] if rows is None else rows), "slots": data["slots"] if slots is None else slots, "rev": data["rev"] + (1 if bump else 0)}
    d = root()
    if d is None:
        _MEMORY["index"] = out
    else:
        _atomic(d / "index.json", json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8"))
    return out


def broken():
    with _LOCK:
        return _load()["broken"]


def listing():
    """→ {files[만든 차례], slots{워크플로우 키: {역할: {file, mode}}}, rev, broken} — 사본."""
    with _LOCK:
        d = _load()
        return {"files": [dict(f) for f in d["files"]], "slots": {j: {r: dict(v) for r, v in box.items()} for j, box in d["slots"].items()}, "rev": d["rev"], "broken": d["broken"]}


def get(fid):
    """양식 하나 | None."""
    if not isinstance(fid, str) or not ID.fullmatch(fid):
        return None
    return next((f for f in listing()["files"] if f["id"] == fid), None)


def data(fid):
    """그 양식의 파일 바이트 | None(없는 양식 · 파일을 못 읽음)."""
    f = get(fid)
    if f is None:
        return None
    d = root()
    if d is None:
        return _MEMORY["blobs"].get(fid)
    try:
        return (d / f"{fid}.{f['fmt']}").read_bytes()
    except OSError:
        return None


def _name(name):
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("양식의 이름을 적으세요")
    if len(name) > NAME_MAX:
        raise ValueError(f"양식의 이름은 {NAME_MAX}자까지입니다")
    return name


def add(name, file_name, fmt, blob: bytes, kind=""):
    """양식을 저장한다 → (양식, 새로 만들었나). fmt = hwpx · docx(이미 바꾼 뒤의 형식) · kind = 문서 종류. 같은 내용(sha256 · 형식)이 있으면 그 양식을 돌려준다(새로 만들지 않음 — 이름 · 종류는 그대로).
    ValueError = 값이 틀림(이름 · 형식 · 종류 · 빈 파일 · 너무 큼 · 한도) · Refused = 목록 파일을 못 읽음."""
    if fmt not in FMTS:
        raise ValueError("양식은 hwpx · docx 파일로 저장합니다(hwp 는 hwpx 로 바꿔 저장)")
    if kind not in KINDS:
        raise ValueError("모르는 문서 종류입니다")
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        raise ValueError("빈 파일입니다")
    if len(blob) > SIZE_MAX:
        raise ValueError("파일이 너무 큽니다")
    name, sha = _name(name), hashlib.sha256(blob).hexdigest()
    with _LOCK:
        d = _load()
        _writable(d)
        same = next((f for f in d["files"] if f["sha256"] == sha and f["fmt"] == fmt), None)
        if same is not None:
            return dict(same), False
        if len(d["files"]) >= FILES_MAX:
            raise ValueError(f"저장한 양식은 {FILES_MAX}개까지입니다")
        ids = {r.get("id") for r in d["rows"] if isinstance(r, dict)}
        fid = next(k for k in (f"f_{uuid.uuid4().hex[:8]}" for _ in range(100)) if k not in ids)
        f = {"id": fid, "name": name, "file": " ".join(str(file_name or "").split())[:200], "fmt": fmt, "kind": kind, "sha256": sha, "size": len(blob), "at": time.time()}
        folder = root()
        if folder is None:
            _MEMORY["blobs"][fid] = bytes(blob)
        else:
            _atomic(folder / f"{fid}.{fmt}", bytes(blob))   # 파일을 다 쓴 뒤에 목록에 올린다
        _save(d, d["rows"] + [f])
        return dict(f), True


def update(fid, name=None, kind=None):
    """이름 · 문서 종류 고치기 → 양식 | None(없음). 설정에 쓰는 양식의 종류는 못 바꾼다(Refused — 그 워크플로우의 목적 종류와 어긋난다)."""
    with _LOCK:
        d = _load()
        _writable(d)
        cur = next((f for f in d["files"] if f["id"] == fid), None)
        if cur is None:
            return None
        new = dict(cur)
        if name is not None:
            new["name"] = _name(name)
        if kind is not None:
            if kind not in KINDS:
                raise ValueError("모르는 문서 종류입니다")
            if kind != cur["kind"] and _uses(d, fid):
                raise Refused("워크플로우 설정에 건 양식의 문서 종류는 바꿀 수 없습니다 — 그 설정을 먼저 푸세요")
            new["kind"] = kind
        if new != cur:
            _save(d, [({**r, "name": new["name"], "kind": new["kind"]} if isinstance(r, dict) and r.get("id") == fid else r) for r in d["rows"]])
        return new


def _uses(d, fid):
    return [(job, role, v["mode"]) for job, box in d["slots"].items() for role, v in box.items() if v["file"] == fid]


def uses(fid):
    """그 양식을 건 워크플로우 설정들 → [(워크플로우 키, 역할, mode)]."""
    with _LOCK:
        return _uses(_load(), fid)


def delete(fid):
    """양식 지우기 → 지웠나(없으면 False). 설정에 쓰는 양식은 Refused."""
    with _LOCK:
        d = _load()
        _writable(d)
        cur = next((f for f in d["files"] if f["id"] == fid), None)
        if cur is None:
            return False
        n = len(_uses(d, fid))
        if n:
            raise Refused(IN_USE.format(n=n))
        _save(d, [r for r in d["rows"] if not (isinstance(r, dict) and r.get("id") == fid)])
        folder = root()
        if folder is None:
            _MEMORY["blobs"].pop(fid, None)
        else:
            try:
                (folder / f"{fid}.{cur['fmt']}").unlink()
            except OSError:
                pass   # 목록에서는 뺐다 — 남은 파일은 쓰이지 않는다
        return True


def slot(job, role="target"):
    """그 워크플로우의 그 문서 칸에 건 양식 → {file, mode, form(양식 | None — 지워졌으면)} | None(설정 없음)."""
    with _LOCK:
        d = _load()
        v = (d["slots"].get(job) or {}).get(role)
        if v is None:
            return None
        return {**v, "form": next((dict(f) for f in d["files"] if f["id"] == v["file"]), None)}


def slot_set(job, role, fid, mode="default"):
    """워크플로우 설정을 정하거나(fid) 푼다(fid None) → 지금 설정의 판(rev). 그 워크플로우 · 칸 · 종류가 맞는지는 부르는 쪽(끝점)이 본다.
    ValueError = 모르는 칸 · mode · 없는 양식 · Refused = 목록 파일을 못 읽음."""
    if role not in ROLES:
        raise ValueError("양식은 목적 문서 · 원본 문서 칸에만 걸 수 있습니다")
    if not isinstance(job, str) or not job:
        raise ValueError("워크플로우를 고르세요")
    with _LOCK:
        d = _load()
        _writable(d)
        slots = {j: dict(box) for j, box in d["slots"].items()}
        if fid is None:
            if role not in (slots.get(job) or {}):
                return d["rev"]
            slots[job].pop(role)
            if not slots[job]:
                slots.pop(job)
        else:
            if mode not in MODES:
                raise ValueError("양식 설정은 기본값(default) · 고정(fixed) 가운데 하나입니다")
            if not any(f["id"] == fid for f in d["files"]):
                raise ValueError("그런 양식이 없습니다")
            if (slots.get(job) or {}).get(role) == {"file": fid, "mode": mode}:
                return d["rev"]
            slots.setdefault(job, {})[role] = {"file": fid, "mode": mode}
        return _save(d, slots=slots, bump=True)["rev"]


def forget_job(job):
    """그 워크플로우의 설정을 모두 푼다(조립한 워크플로우를 지울 때) → 풀었나. 뒷정리라 예외를 내지 않는다."""
    with _LOCK:
        try:
            d = _load()
            if d["broken"] or job not in d["slots"]:
                return False
            _save(d, slots={j: b for j, b in d["slots"].items() if j != job}, bump=True)
            return True
        except (OSError, ValueError):
            return False
