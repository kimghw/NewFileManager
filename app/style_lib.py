"""서식 보관함 저장소(spec_일반편집 ② §2) — 서버 전체에 저장하는 서식 템플릿(표 서식 `table` · 글 서식 `text`). 문서·작업·프로젝트와 무관한 공통 모듈.

폴더 = env NFM_STYLES(기본 %LOCALAPPDATA%\\NewFileManager\\styles · `off`·`0` = 끔 → 끝점 503). 꼴:

    styles/<sid>/current.json                    {"revision": "r3"}
    styles/<sid>/revisions/<rid>/meta.json       meta(schemaVersion 1 — 뜻의 원본: 띠 수 · blueprint · items 의 레벨·marker)
    styles/<sid>/revisions/<rid>/carrier.hwpx    운반 문서(app/style_carrier.py)
    styles/<sid>/revisions/<rid>/proof.png …     딸린 파일(검증 그림 — app/style_verify.py)

- `sid` = 12자리 16진, `rid` = `r<n>`(1부터). 새 revision 은 임시 폴더에 **다 쓴 뒤** `revisions/<rid>` 로 이름을 바꾸고 `current.json` 을 **마지막에** 바꾼다
  (원자적 쓰기 = `.tmp` + `os.replace`, PermissionError 는 `heading_rules._retry`) — 쓰다 죽어도 지금 revision 은 그대로다. 옛 revision 은 최근 5개만.
- 쓰기·읽기는 프로세스 잠금 하나(서버 프로세스 하나가 쓴다는 전제 — 8114 하나만: CLAUDE.md).
- 깨진 것(`current.json`·`meta.json` 이 없거나 JSON·꼴이 아님 · **운반 문서가 없거나 그 바이트의 해시가 meta 의 `carrierSha256` 과 다름**)은 `listing()` 이 건너뛰고 `broken` 에 id 를 적는다.
  `get`·`carrier` 는 None, `revise` 는 KeyError — **말없이 덮어쓰지 않는다**(지우기 `delete(sid)` 만 된다).
- `expected`(읽었을 때의 revision)는 **꼭 준다** — 지금 것과 다르면 `Stale`(→ 409), 안 주면(None·꼴이 아님) ValueError(→ 400): 오래된 화면이 남의 고침을 덮어쓰거나 지우지 못하게.
  깨진 템플릿을 지울 때만 없이 된다(읽을 revision 이 없다).
- 도는 검증이 붙든 revision(`pin` — `style_verify.start`)은 `unpin` 까지 치우지 않는다(검증 결과를 붙일 자리가 사라지지 않게)."""
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from app import heading_rules, table_make

SCHEMA, KEEP = 1, 5  # meta 판 · 남기는 revision 수
NAME_MAX, NOTE_MAX = 60, 400
KINDS, FIDELITY = ("table", "text"), ("native", "summary", "approx")
SID, RID = re.compile(r"[0-9a-f]{12}"), re.compile(r"r([1-9]\d{0,8})")
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # revision 폴더에 딸린 파일 이름(경로를 받지 않는다)
CARRIER, META, CURRENT = "carrier.hwpx", "meta.json", "current.json"
OWN = ("schemaVersion", "id", "revision", "kind", "created", "updated", "carrierSha256", "verify")  # 저장소가 정하는 키 — revise 의 changes 로 못 바꾼다
SOURCE_KEYS = ("name", "format", "work", "block", "page", "sha256")
NEED_EXPECTED = "expectedRevision(읽었을 때의 revision — 「r3」 꼴)이 필요합니다 — 서식을 다시 읽어 주세요"
_LOCK = threading.RLock()
_PINS = {}  # (템플릿 id, revision id) → 붙든 수 — 도는 검증이 붙든 revision(메모리 · _LOCK 안에서만 고친다)


class Stale(Exception):
    """expected revision 이 지금 revision 과 다름(409) — 그 사이 다른 쪽이 고쳤다."""


def root() -> Path | None:
    """보관함 폴더 | None(끔). env NFM_STYLES 가 폴더, off·0 이면 None."""
    env = os.environ.get("NFM_STYLES", "").strip()
    if env.lower() in ("off", "0"):
        return None
    if env:
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "styles"


def enabled() -> bool:
    return root() is not None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- 파일 ---------------------------------------------------------------------------------------------------------

def _dir(sid):
    """그 템플릿의 폴더 — id 꼴이 아니거나 보관함이 꺼져 있으면 None(경로를 받지 않는다)."""
    base = root()
    return base / sid if base is not None and isinstance(sid, str) and SID.fullmatch(sid) else None


def _json(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def _write(path: Path, data: bytes):
    """원자적 쓰기 — 임시 파일에 쓴 뒤 바꿔 넣는다(Windows 의 잠깐 잠긴 파일은 다시)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        tmp.write_bytes(data)
        heading_rules._retry(lambda: os.replace(tmp, path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _read_json(path: Path):
    """사전 | None(없음 · 못 읽음 · JSON 사전이 아님)."""
    try:
        data = json.loads(heading_rules._retry(path.read_bytes).decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _rid_n(rid) -> int:
    m = RID.fullmatch(rid) if isinstance(rid, str) else None
    return int(m[1]) if m else 0


def _current(d: Path):
    """지금 revision id | None(current.json 이 없거나 깨짐)."""
    rid = (_read_json(d / CURRENT) or {}).get("revision")
    return rid if _rid_n(rid) else None


def _meta(d: Path, rid):
    """그 revision 의 meta | None(깨짐 — 없음 · JSON 아님 · 판·id·revision·종류·이름이 맞지 않음)."""
    if not _rid_n(rid):
        return None
    m = _read_json(d / "revisions" / rid / META)
    ok = m is not None and m.get("schemaVersion") == SCHEMA and m.get("id") == d.name and m.get("revision") == rid and m.get("kind") in KINDS and isinstance(m.get("name"), str)
    return m if ok else None


def _carrier_bytes(d: Path, rid, m) -> bytes | None:
    """그 revision 의 운반 문서 바이트 — 파일이 없거나 해시가 meta m 의 `carrierSha256` 과 다르면 None(손상 · 바꿔치기)."""
    try:
        data = heading_rules._retry((d / "revisions" / rid / CARRIER).read_bytes)
    except OSError:
        return None
    return data if m is not None and sha256(data) == m.get("carrierSha256") else None


def _healthy(d: Path):
    """성한 템플릿의 (지금 revision id, meta) | (지금 revision id | None, None) — 깨짐 = current·meta 를 못 읽음, 운반 문서가 없거나 해시가 다름."""
    rid = _current(d)
    m = _meta(d, rid)
    return (rid, m) if m is not None and _carrier_bytes(d, rid, m) is not None else (rid, None)


def _expected(expected):
    """읽었을 때의 revision — revision id 꼴이 아니면(None 포함) ValueError(끝점 400)."""
    if not _rid_n(expected):
        raise ValueError(NEED_EXPECTED)
    return expected


def _prune(d: Path):
    """옛 revision 은 최근 KEEP 개만(쓰다 만 임시 폴더도 치움) — 도는 검증이 붙든 것(_PINS)은 둔다. _LOCK 안에서."""
    n, revs = _rid_n(_current(d)), d / "revisions"
    if not n or not revs.is_dir():
        return
    for p in list(revs.iterdir()):
        if p.is_dir() and (p.name.startswith(".") or (0 < _rid_n(p.name) <= n - KEEP and (d.name, p.name) not in _PINS)):
            shutil.rmtree(p, ignore_errors=True)


def _files(files) -> dict:
    out = {}
    for name, data in (files or {}).items():
        if not isinstance(name, str) or not FILE_NAME.fullmatch(name) or name in (META, CARRIER, CURRENT) or not isinstance(data, (bytes, bytearray)):
            raise ValueError(f"딸린 파일 이름·내용이 틀렸습니다: {name!r}")
        out[name] = bytes(data)
    return out


def _write_rev(tmp: Path, final: Path, meta: dict, carrier: bytes, files: dict):
    """revision 폴더 하나를 임시 폴더 tmp 에 다 쓴 뒤 final 로 이름을 바꾼다 — final 은 다 쓰였거나 아예 없다."""
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        tmp.mkdir(parents=True)
        (tmp / CARRIER).write_bytes(carrier)
        for name, data in files.items():
            (tmp / name).write_bytes(data)
        (tmp / META).write_bytes(_json(meta))
        heading_rules._retry(lambda: os.replace(tmp, final))
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


# ---- meta 고르기 ---------------------------------------------------------------------------------------------------

def _clean(meta) -> dict:
    """meta 의 공통 항목을 고른 꼴로(이름 1~60자 · 메모 0~400자 · 종류 · 충실도 · 원본 · 뺀 것 · 글꼴) — 틀리면 ValueError. 그 밖의 키는 그대로 둔다."""
    if not isinstance(meta, dict):
        raise ValueError("meta 는 사전이어야 합니다")
    if meta.get("kind") not in KINDS:
        raise ValueError("kind 는 table 또는 text")
    name = re.sub(r"\s+", " ", meta["name"]).strip() if isinstance(meta.get("name"), str) else ""
    if not name:
        raise ValueError("이름을 넣으세요")
    if len(name) > NAME_MAX:
        raise ValueError(f"이름은 {NAME_MAX}자 이하")
    note = meta.get("note") or ""
    if not isinstance(note, str) or len(note.strip()) > NOTE_MAX:
        raise ValueError(f"메모는 {NOTE_MAX}자 이하의 글")
    fidelity = meta.get("fidelity") or "native"
    if fidelity not in FIDELITY:
        raise ValueError(f"fidelity 는 {'·'.join(FIDELITY)} 중 하나")
    src = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    req = meta.get("requirements") if isinstance(meta.get("requirements"), dict) else {}
    out = {**meta, "name": name, "note": note.strip(), "fidelity": fidelity, "source": {k: src.get(k) for k in SOURCE_KEYS},
           "losses": [str(x)[:300] for x in meta.get("losses") or [] if x][:50],
           "requirements": {**req, "fonts": sorted({str(f) for f in req.get("fonts") or [] if f})}}
    if meta["kind"] == "table":
        rows, cols = meta.get("rows"), meta.get("cols")
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (rows, cols)):
            raise ValueError("표 서식에는 rows·cols(1 이상의 정수)가 필요합니다")
        out["bands"] = table_make.clean_roles(meta.get("bands"), rows, cols)
        out["blueprint"] = meta["blueprint"] if isinstance(meta.get("blueprint"), dict) else None
        out["preview"] = meta["preview"] if isinstance(meta.get("preview"), dict) else None
    else:
        items = meta.get("items")
        if not isinstance(items, list) or not items or not all(isinstance(i, dict) and isinstance(i.get("key"), str) and i["key"] for i in items):
            raise ValueError("글 서식에는 items(key 가 있는 항목 1개 이상)가 필요합니다")
        if len({i["key"] for i in items}) != len(items):
            raise ValueError("items 의 key 가 겹칩니다")
    return out


def _stamp(meta, sid, rid, created, updated, carrier, verify) -> dict:
    """저장소가 정하는 키를 앞에 둔 meta."""
    head = {"schemaVersion": SCHEMA, "id": sid, "revision": rid, "kind": meta["kind"], "name": meta["name"], "note": meta["note"], "created": created, "updated": updated}
    return {**head, **{k: v for k, v in meta.items() if k not in head and k not in OWN}, "carrierSha256": sha256(carrier), "verify": verify}


# ---- 읽기 ---------------------------------------------------------------------------------------------------------

def listing() -> dict:
    """{"styles": [지금 revision 의 meta…(고친 때가 새것부터)], "broken": [깨진 템플릿 id…]}. 보관함이 꺼져 있으면 둘 다 빈 목록.
    깨진 것 = current·meta 를 못 읽음 + **운반 문서가 없거나 그 해시가 meta 의 carrierSha256 과 다름**(정상 목록에 섞지 않는다)."""
    out, base = {"styles": [], "broken": []}, root()
    if base is None or not base.is_dir():
        return out
    with _LOCK:
        for d in sorted(base.iterdir()):
            if not SID.fullmatch(d.name) or not d.is_dir():
                continue
            m = _healthy(d)[1]
            if m is None:
                out["broken"].append(d.name)
            else:
                out["styles"].append(m)
    out["styles"].sort(key=lambda m: m.get("updated") or 0, reverse=True)
    return out


def get(sid) -> dict | None:
    """지금 revision 의 meta | None(없음 · 깨짐(운반 문서가 없거나 해시가 다른 것 포함) · 보관함 끔)."""
    d = _dir(sid)
    if d is None or not d.is_dir():
        return None
    with _LOCK:
        return _healthy(d)[1]


def _rev_dir(sid, rid=None):
    """그 revision(없으면 지금 것)의 폴더 | None."""
    d = _dir(sid)
    if d is None:
        return None
    rid = rid or _current(d)
    r = d / "revisions" / rid if _rid_n(rid) else None
    return r if r is not None and r.is_dir() else None


def carrier(sid, rid=None) -> bytes | None:
    """그 revision(없으면 지금 것)의 운반 문서 바이트 | None(없음 · 그 revision 의 meta 를 못 읽음 · 바이트의 해시가 meta 의 carrierSha256 과 다름)."""
    with _LOCK:
        r = _rev_dir(sid, rid)
        return _carrier_bytes(r.parent.parent, r.name, _meta(r.parent.parent, r.name)) if r is not None else None


def file(sid, name, rid=None) -> Path | None:
    """그 revision(없으면 지금 것)에 딸린 파일(「proof.png」 등)의 경로 | None(없음 · 이름이 파일 이름 꼴이 아님)."""
    if not isinstance(name, str) or not FILE_NAME.fullmatch(name):
        return None
    with _LOCK:
        r = _rev_dir(sid, rid)
        p = r / name if r is not None else None
        return p if p is not None and p.is_file() else None


# ---- 쓰기 ---------------------------------------------------------------------------------------------------------

def _need_root() -> Path:
    base = root()
    if base is None:
        raise OSError("서식 보관함이 꺼져 있습니다")
    return base


def create(meta: dict, carrier: bytes, files: dict | None = None) -> dict:
    """새 템플릿 -> meta(id · revision "r1" · created/updated · carrierSha256 을 채운 것). 틀린 meta 는 ValueError, 보관함 끔·쓰기 실패는 OSError.
    템플릿 폴더째 임시 이름으로 다 쓴 뒤 바꿔 넣는다 — 쓰다 만 템플릿이 목록에 깨진 것으로 남지 않는다."""
    base, meta, files = _need_root(), _clean(meta), _files(files)
    if not isinstance(carrier, (bytes, bytearray)) or not carrier:
        raise ValueError("운반 문서가 비었습니다")
    carrier, now = bytes(carrier), time.time()
    with _LOCK:
        sid = uuid.uuid4().hex[:12]
        while (base / sid).exists():
            sid = uuid.uuid4().hex[:12]
        out = _stamp(meta, sid, "r1", now, now, carrier, meta.get("verify") if isinstance(meta.get("verify"), dict) else None)
        tmp = base / f".{sid}.tmp"
        try:
            _write_rev(tmp / "revisions" / ".r1.tmp", tmp / "revisions" / "r1", out, carrier, files)
            _write(tmp / CURRENT, _json({"revision": "r1"}))
            heading_rules._retry(lambda: os.replace(tmp, base / sid))
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    return out


def revise(sid, expected, changes: dict | None = None, carrier: bytes | None = None, files: dict | None = None) -> dict:
    """다음 revision -> meta. changes = 바꿀 meta 키(저장소가 정하는 키 OWN 은 무시), carrier 를 안 주면 앞 것을 복사, files = 더 쓸 딸린 파일.
    `verify` 와 딸린 파일(검증 그림)은 **운반 문서가 같을 때만** 물려받는다. 없는(또는 깨진) 템플릿은 KeyError, expected 를 안 주면(revision id 꼴이 아님) ValueError,
    지금 revision 과 다르면 Stale."""
    d, files = _dir(sid), _files(files)
    if d is None or not d.is_dir():
        raise KeyError(sid)
    with _LOCK:
        rid, old = _healthy(d)
        if old is None:  # 깨진 템플릿(운반 문서가 없거나 해시가 다른 것 포함)은 고치지 않는다 — 덮어쓰면 남은 것까지 잃고, 바뀐 운반 문서가 성한 것으로 둔갑한다
            raise KeyError(sid)
        if _expected(expected) != rid:
            raise Stale(f"서식이 그 사이 바뀌었습니다(지금 {rid} · 요청 {expected}) — 다시 읽어 주세요")
        prev = d / "revisions" / rid
        data = bytes(carrier) if carrier is not None else heading_rules._retry((prev / CARRIER).read_bytes)
        if not data:
            raise ValueError("운반 문서가 비었습니다")
        same = sha256(data) == old.get("carrierSha256")
        new = _clean({**old, **{k: v for k, v in (changes or {}).items() if k not in OWN}})
        n = max([_rid_n(p.name) for p in (d / "revisions").iterdir() if p.is_dir()] + [_rid_n(rid)]) + 1
        new = _stamp(new, sid, f"r{n}", old.get("created"), time.time(), data, old.get("verify") if same else None)
        kept = {p.name: p.read_bytes() for p in prev.iterdir() if p.is_file() and p.name not in (META, CARRIER) and FILE_NAME.fullmatch(p.name)} if same else {}
        _write_rev(d / "revisions" / f".r{n}.tmp", d / "revisions" / f"r{n}", new, data, {**kept, **files})
        _write(d / CURRENT, _json({"revision": f"r{n}"}))  # 마지막 — 여기까지 와야 새 revision 이 보인다
        _prune(d)
    return new


def pin(sid, rid) -> bool:
    """그 revision 을 붙든다 -> 붙들었나(그 revision 폴더가 있을 때만). 붙든 revision 은 `revise` 의 치우기(최근 KEEP 개)가 건너뛴다 — 도는 PDF 검증
    (`style_verify.start`)이 끝나 기록을 붙일 때까지 그 revision 이 남아 있게. 붙든 만큼 `unpin` 한다(센다). 메모리에만 — 프로세스가 끝나면 풀린다."""
    with _LOCK:
        if _rev_dir(sid, rid) is None or not _rid_n(rid):
            return False
        _PINS[sid, rid] = _PINS.get((sid, rid), 0) + 1
    return True


def unpin(sid, rid) -> None:
    """`pin` 한 것을 놓는다 — 마지막 것을 놓으면 그 사이 밀린 옛 revision 을 치운다."""
    with _LOCK:
        n = _PINS.get((sid, rid), 0)
        if n > 1:
            _PINS[sid, rid] = n - 1
            return
        _PINS.pop((sid, rid), None)
        d = _dir(sid)
        if n and d is not None and d.is_dir():
            _prune(d)


def put_verify(sid, rid, record: dict, files: dict | None = None) -> bool:
    """검증 기록(spec ② §6)과 딸린 파일(proof.png …)을 **그 revision 에** 붙인다 -> 붙였나. 그 revision 이 이미 없으면(지워짐 · 옛 것이라 치워짐) False.
    그 사이 새 revision 이 생겼으면 새 것에는 **운반 문서가 같고 아직 검증 기록이 없을 때만** 함께 붙인다(`revise` 의 물려받기와 같은 규칙 — 검증이 도는 동안 이름만 바꾼 경우에
    기록이 옛 revision 에만 남지 않게). 운반 문서가 다른 새 revision 에는 안 붙인다(검증한 것이 아니다). 고친 때(updated)는 안 바꾼다."""
    d = _dir(sid)
    if d is None or not isinstance(record, dict):
        return False
    files = _files(files)
    with _LOCK:
        m = _meta(d, rid)
        if m is None:
            return False
        cur = _current(d)
        now = _meta(d, cur) if cur != rid else None
        same = now is not None and now.get("verify") is None and now.get("carrierSha256") == m.get("carrierSha256")
        for r, meta in ((rid, m), *(((cur, now),) if same else ())):
            for name, data in files.items():
                _write(d / "revisions" / r / name, data)
            _write(d / "revisions" / r / META, _json({**meta, "verify": record}))
    return True


def delete(sid, expected=None) -> bool:
    """템플릿을 지운다 -> 지웠나(없으면 False). 성한 템플릿은 expected 를 꼭 준다 — 안 주면 ValueError, 지금 revision 과 다르면 Stale.
    **깨진 템플릿**(current·meta 를 못 읽음 · 운반 문서가 없거나 해시가 다름 — 읽을 revision 이 없다)만 expected 없이 지운다."""
    d = _dir(sid)
    if d is None or not d.is_dir():
        return False
    with _LOCK:
        rid, healthy = _healthy(d)
        if expected is None and healthy is not None:
            raise ValueError(NEED_EXPECTED)
        if expected is not None and expected != rid:
            raise Stale("서식이 그 사이 바뀌었습니다 — 다시 읽어 주세요")
        gone = d.with_name(f".{sid}.del{int(time.time() * 1000)}")  # 이름부터 바꾼다 — 지우다 만 폴더가 깨진 템플릿으로 보이지 않게
        heading_rules._retry(lambda: os.replace(d, gone))
        shutil.rmtree(gone, ignore_errors=True)
    return True
