"""서식 보관함 저장소(spec_일반편집 ② §2 · spec_서식복사 ② §4·§5·§12·§14) — 서버 전체에 저장하는 서식 템플릿(표 서식 `table` · 글 서식 `text` · 문서 서식 `page` · 표지 서식 `cover`). 문서·작업·프로젝트와 무관한 공통 모듈.
글 서식의 `role`(문단 서식의 역할 — `ROLES` 의 코드나 None: 레벨이 있는 글 서식은 늘 None) · 표지 서식의 `parts`(부분들)·`page`(그 구역의 쪽 설정)는 meta 에 그대로 둔다.

폴더 = env NFM_STYLES(기본 %LOCALAPPDATA%\\NewFileManager\\styles · `off`·`0` = 끔 → 끝점 503). 꼴:

    styles/<sid>/current.json                    {"revision": "r3"}
    styles/<sid>/revisions/<rid>/meta.json       meta(schemaVersion 1 — 뜻의 원본: 띠 수 · blueprint · items 의 레벨·marker)
    styles/<sid>/revisions/<rid>/carrier.hwpx    운반 문서(app/style_carrier.py) — 뜻의 원본 · 깨짐 판정의 기준
    styles/<sid>/revisions/<rid>/carrier.docx    docx 운반 문서(app/style_docx.py — 없을 수 있다: meta.docx = {sha256, losses} | None)
    styles/<sid>/revisions/<rid>/proof.png …     딸린 파일(검증 그림 — app/style_verify.py: hwpx = proof.png·proof.pdf · docx = proof_docx.png·proof_docx.pdf)

- `sid` = 12자리 16진, `rid` = `r<n>`(1부터). 새 revision 은 임시 폴더에 **다 쓴 뒤** `revisions/<rid>` 로 이름을 바꾸고 `current.json` 을 **마지막에** 바꾼다
  (원자적 쓰기 = `.tmp` + `os.replace`, PermissionError 는 `heading_rules._retry`) — 쓰다 죽어도 지금 revision 은 그대로다. 옛 revision 은 최근 5개만.
- 쓰기·읽기는 프로세스 잠금 하나(서버 프로세스 하나가 쓴다는 전제 — 8114 하나만: CLAUDE.md).
- 깨진 것(`current.json`·`meta.json` 이 없거나 JSON·꼴이 아님 · **운반 문서가 없거나 그 바이트의 해시가 meta 의 `carrierSha256` 과 다름**)은 `listing()` 이 건너뛰고 `broken` 에 id 를 적는다.
  `get`·`carrier` 는 None, `revise` 는 KeyError — **말없이 덮어쓰지 않는다**(지우기 `delete(sid)` 만 된다).
- `expected`(읽었을 때의 revision)는 **꼭 준다** — 지금 것과 다르면 `Stale`(→ 409), 안 주면(None·꼴이 아님) ValueError(→ 400): 오래된 화면이 남의 고침을 덮어쓰거나 지우지 못하게.
  깨진 템플릿을 지울 때만 없이 된다(읽을 revision 이 없다).
- 도는 검증이 붙든 revision(`pin` — `style_verify.start`)은 `unpin` 까지 치우지 않는다(검증 결과를 붙일 자리가 사라지지 않게).
- **두 형식**(spec_서식복사 ② §4): docx 운반 문서는 `create`·`revise` 의 `files={"carrier.docx": …}` 로 함께 넣거나, 옛 revision 에 `put_docx` 로 **붙인다**(revision 번호는 그대로).
  `meta.docx` 의 해시는 저장소가 그 바이트에서 낸다(준 값은 losses 만 읽는다). 깨짐 판정은 hwpx 운반 문서 기준 그대로 — docx 가 없거나 바뀌어도 템플릿은 성하다(`carrier(…, fmt="docx")` 만 None).
  검증 기록은 형식마다: `verify`(hwpx) · `verifyDocx`(docx) — `put_verify(…, fmt=)`. 새 칸이 없는 옛 meta 는 그대로 읽힌다(없는 칸 = None)."""
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
KINDS, FIDELITY = ("table", "text", "page", "cover"), ("native", "summary", "approx")  # cover = 표지 서식(spec_서식복사 ② §14 — 첫 쪽의 블록 묶음)
ROLES = ("body", "caption", "note", "box", "toc", "other")  # 문단 서식(레벨 없는 글 서식)의 역할 코드(spec_서식복사 ② §12) — 본문 · 캡션 · 주석 · 상자 글 · 목차 · 기타(None = 모름)
PART_TYPES = ("text", "table")  # 표지 서식의 부분 종류(② §14 — meta.parts[].type)
SID, RID = re.compile(r"[0-9a-f]{12}"), re.compile(r"r([1-9]\d{0,8})")
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # revision 폴더에 딸린 파일 이름(경로를 받지 않는다)
CARRIER, META, CURRENT = "carrier.hwpx", "meta.json", "current.json"
CARRIER_DOCX = "carrier.docx"  # docx 운반 문서(spec_서식복사 ② §4) — 딸린 파일로 넣는다(files) · meta.docx 가 그 해시를 적는다
FORMATS = ("hwpx", "docx")
VERIFY_KEY = {"hwpx": "verify", "docx": "verifyDocx"}  # 형식 → meta 의 검증 기록 칸
DOCX_PROOFS = ("proof_docx.png", "proof_docx.pdf")  # docx 검증의 딸린 파일 — docx 운반 문서가 바뀌면 물려받지 않는다
OWN = ("schemaVersion", "id", "revision", "kind", "created", "updated", "carrierSha256", "verify", "docx", "verifyDocx")  # 저장소가 정하는 키 — revise 의 changes 로 못 바꾼다
# 원본 문서 기록(spec_서식복사 ② §17 — 2026-11-14 사용자 "어떤 문서에서 추출한 건지 정보를 넣어줘 … 에이전트가 사용할때 참조할 수 있도록"): 어느 문서(name · format · sha256)의
# 어느 작업(work — 파일에서 뽑았으면 None)에서, 그 작업이 어느 프로젝트·TASK·라운드였고(project · job · round), 문서의 어디(block · page · where 「표 3번째」)에서, 언제(at) 뽑았나.
# 문서의 글(앞뒤 문단·제목)은 넣지 않는다 — 보관함은 서버 전체가 같이 쓴다.
SOURCE_KEYS = ("name", "format", "work", "block", "page", "sha256", "project", "job", "round", "where", "at")
SEEN_KEYS = ("name", "format", "work", "sha256", "project", "job", "round", "where", "at")   # 같은 서식이 나온 **다른 문서** 하나(`seenIn` 의 항목 — block 은 그 문서의 것이라 where 로만)
SEEN_MAX = 20            # `seenIn` 에 남기는 문서 수(넘으면 옛 것부터 버린다)
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


def _docx_bytes(d: Path, rid, m) -> bytes | None:
    """그 revision 의 docx 운반 문서 바이트 — 파일이 없거나 meta m 에 `docx` 가 없거나 해시가 `docx.sha256` 과 다르면 None."""
    want = m.get("docx").get("sha256") if m is not None and isinstance(m.get("docx"), dict) else None
    if not want:
        return None
    try:
        data = heading_rules._retry((d / "revisions" / rid / CARRIER_DOCX).read_bytes)
    except OSError:
        return None
    return data if sha256(data) == want else None


def _docx_meta(given, files) -> dict | None:
    """meta.docx = {"sha256", "losses": [글…]} | None — files 에 `carrier.docx` 가 있을 때만. 해시는 그 바이트에서 낸다(given 에서는 losses 만 읽는다)."""
    data = files.get(CARRIER_DOCX)
    if data is None:
        return None
    if not data:
        raise ValueError("docx 운반 문서가 비었습니다")
    losses = given.get("losses") if isinstance(given, dict) else None
    return {"sha256": sha256(data), "losses": [str(x)[:300] for x in (losses if isinstance(losses, list) else []) if x][:50]}


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
        raise ValueError(f"kind 는 {' · '.join(KINDS)} 중 하나")
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
           "seenIn": [{k: x.get(k) for k in SEEN_KEYS} for x in meta.get("seenIn") or [] if isinstance(x, dict) and x.get("name")][-SEEN_MAX:],
           "losses": [str(x)[:300] for x in meta.get("losses") or [] if x][:50],
           "requirements": {**req, "fonts": sorted({str(f) for f in req.get("fonts") or [] if f})}}
    if meta["kind"] == "table":
        rows, cols = meta.get("rows"), meta.get("cols")
        if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (rows, cols)):
            raise ValueError("표 서식에는 rows·cols(1 이상의 정수)가 필요합니다")
        out["bands"] = table_make.clean_roles(meta.get("bands"), rows, cols)
        out["blueprint"] = meta["blueprint"] if isinstance(meta.get("blueprint"), dict) else None
        out["preview"] = meta["preview"] if isinstance(meta.get("preview"), dict) else None
    elif meta["kind"] == "page":  # 문서 서식(spec_서식복사 ② §5) — 쪽 설정 + 본문 바탕 글 모양. 값의 범위는 만드는 쪽(style_page.clean)이 본다 — 여기는 꼴만
        page = meta.get("page")
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
        if not isinstance(page, dict) or not all(num(page.get(k)) and page[k] > 0 for k in ("widthMm", "heightMm")) or not isinstance(page.get("marginsMm"), dict) \
                or not all(num(page["marginsMm"].get(k)) and page["marginsMm"][k] >= 0 for k in ("l", "r", "t", "b")):
            raise ValueError("문서 서식에는 page(widthMm·heightMm·marginsMm{l,r,t,b})가 필요합니다")
        out["page"] = page
        out["body"] = meta["body"] if isinstance(meta.get("body"), dict) else None
    elif meta["kind"] == "cover":  # 표지 서식(spec_서식복사 ② §14) — 첫 쪽의 부분들(글 · 표) + 그 구역의 쪽 설정. 부분의 값은 만드는 쪽(style_cover.carrier)이 정한다 — 여기는 꼴만
        parts = meta.get("parts")
        if not isinstance(parts, list) or not parts or not all(isinstance(p, dict) and p.get("type") in PART_TYPES for p in parts):
            raise ValueError("표지 서식에는 parts(type 이 text·table 인 부분 1개 이상)가 필요합니다")
        out["parts"] = parts
        out["page"] = meta["page"] if isinstance(meta.get("page"), dict) else None
    else:
        items = meta.get("items")
        if not isinstance(items, list) or not items or not all(isinstance(i, dict) and isinstance(i.get("key"), str) and i["key"] for i in items):
            raise ValueError("글 서식에는 items(key 가 있는 항목 1개 이상)가 필요합니다")
        if len({i["key"] for i in items}) != len(items):
            raise ValueError("items 의 key 가 겹칩니다")
        role = meta.get("role")  # 문단 서식의 역할(spec_서식복사 ② §12) — 정해진 코드나 None(모름). 레벨이 있는 글 서식(내용 서식)에는 역할이 없다
        if role is not None and role not in ROLES:
            raise ValueError(f"role 은 {'·'.join(ROLES)} 중 하나 또는 null")
        out["role"] = None if leveled(out) else role
    return out


def leveled(meta) -> bool:
    """글 서식에 레벨이 있나(spec_서식복사 ② §12 — items 가운데 level 이 하나라도 있으면 **내용 서식**, 모두 없으면 **문단 서식**). 글 서식이 아니면 False."""
    items = meta.get("items") if isinstance(meta, dict) and meta.get("kind") == "text" else None
    return any(isinstance(i, dict) and i.get("level") is not None for i in items or [])


def _stamp(meta, sid, rid, created, updated, carrier, verify, docx=None, verify_docx=None) -> dict:
    """저장소가 정하는 키를 앞에 둔 meta. docx = {"sha256", "losses"} | None(docx 운반 문서 없음) · verify_docx = docx 쪽 검증 기록(docx 가 없으면 None)."""
    head = {"schemaVersion": SCHEMA, "id": sid, "revision": rid, "kind": meta["kind"], "name": meta["name"], "note": meta["note"], "created": created, "updated": updated}
    return {**head, **{k: v for k, v in meta.items() if k not in head and k not in OWN}, "carrierSha256": sha256(carrier), "verify": verify,
            "docx": docx, "verifyDocx": verify_docx if docx else None}


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


def carrier(sid, rid=None, fmt="hwpx") -> bytes | None:
    """그 revision(없으면 지금 것)의 운반 문서 바이트 | None(없음 · 그 revision 의 meta 를 못 읽음 · 바이트의 해시가 meta 의 carrierSha256 과 다름).
    fmt="docx" = docx 운반 문서(`carrier.docx` — 없거나 해시가 meta.docx.sha256 과 다르면 None: 부르는 쪽이 지어 `put_docx` 로 붙인다)."""
    with _LOCK:
        r = _rev_dir(sid, rid)
        if r is None:
            return None
        m = _meta(r.parent.parent, r.name)
        return _docx_bytes(r.parent.parent, r.name, m) if fmt == "docx" else _carrier_bytes(r.parent.parent, r.name, m)


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
        out = _stamp(meta, sid, "r1", now, now, carrier, meta.get("verify") if isinstance(meta.get("verify"), dict) else None, _docx_meta(meta.get("docx"), files),
                     meta.get("verifyDocx") if isinstance(meta.get("verifyDocx"), dict) else None)
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
    지금 revision 과 다르면 Stale.
    docx 운반 문서(spec_서식복사 ② §4): files 에 `carrier.docx` 를 주면 그것(losses 는 changes["docx"]["losses"]), 안 주면 **운반 문서가 같을 때만** 앞 것을 물려받는다 —
    운반 문서가 바뀌었는데 docx 를 안 주면 `docx: None`. `verifyDocx` 와 그 그림(proof_docx.*)은 hwpx·docx 운반 문서가 둘 다 같을 때만 물려받는다."""
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
        kept = {p.name: p.read_bytes() for p in prev.iterdir() if p.is_file() and p.name not in (META, CARRIER) and FILE_NAME.fullmatch(p.name)} if same else {}
        # docx 운반 문서(spec_서식복사 ② §4): 새로 준 것 > (운반 문서가 같을 때만) 앞 것. 운반 문서가 바뀌었는데 안 주면 None — 부르는 쪽이 함께 지어 준다
        had = old.get("docx") if isinstance(old.get("docx"), dict) and CARRIER_DOCX in kept and sha256(kept[CARRIER_DOCX]) == old["docx"].get("sha256") else None
        docx = _docx_meta((changes or {}).get("docx"), files) if CARRIER_DOCX in files else had
        same_docx = same and docx is not None and had is not None and docx["sha256"] == had["sha256"]
        if not same_docx:  # docx 가 바뀌었거나 없다 — 그 검증 그림은 물려받지 않는다(깨져 있던 앞 docx 파일도)
            kept = {k: v for k, v in kept.items() if k not in DOCX_PROOFS and (k != CARRIER_DOCX or docx is not None)}
        new = _stamp(new, sid, f"r{n}", old.get("created"), time.time(), data, old.get("verify") if same else None, docx, old.get("verifyDocx") if same_docx else None)
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


def put_verify(sid, rid, record: dict, files: dict | None = None, fmt: str = "hwpx") -> bool:
    """검증 기록(spec ② §6)과 딸린 파일(proof.png …)을 **그 revision 에** 붙인다 -> 붙였나. 그 revision 이 이미 없으면(지워짐 · 옛 것이라 치워짐) False.
    그 사이 새 revision 이 생겼으면 새 것에는 **운반 문서가 같고 아직 검증 기록이 없을 때만** 함께 붙인다(`revise` 의 물려받기와 같은 규칙 — 검증이 도는 동안 이름만 바꾼 경우에
    기록이 옛 revision 에만 남지 않게). 운반 문서가 다른 새 revision 에는 안 붙인다(검증한 것이 아니다). 고친 때(updated)는 안 바꾼다.
    fmt = 형식(spec_서식복사 ② §7): hwpx → `verify` · docx → `verifyDocx`(새 revision 에는 docx 운반 문서까지 같을 때만). 모르는 형식은 False."""
    d, key = _dir(sid), VERIFY_KEY.get(fmt) if isinstance(fmt, str) else None
    if d is None or key is None or not isinstance(record, dict):
        return False
    files = _files(files)
    docx_of = lambda meta: meta.get("docx").get("sha256") if isinstance(meta.get("docx"), dict) else None  # noqa: E731
    with _LOCK:
        m = _meta(d, rid)
        if m is None:
            return False
        cur = _current(d)
        now = _meta(d, cur) if cur != rid else None
        same = now is not None and now.get(key) is None and now.get("carrierSha256") == m.get("carrierSha256") and (fmt != "docx" or bool(docx_of(now) and docx_of(now) == docx_of(m)))
        for r, meta in ((rid, m), *(((cur, now),) if same else ())):
            for name, data in files.items():
                _write(d / "revisions" / r / name, data)
            _write(d / "revisions" / r / META, _json({**meta, key: record}))
    return True


def same_doc(a, b) -> bool:
    """두 원본 기록이 같은 문서인가 — 둘 다 sha256 이 있으면 그것으로, 아니면 이름·형식으로(같은 파일을 다른 작업으로 연 것은 같은 문서다)."""
    a, b = a if isinstance(a, dict) else {}, b if isinstance(b, dict) else {}
    if a.get("sha256") and b.get("sha256"):
        return a["sha256"] == b["sha256"]
    return bool(a.get("name")) and (a.get("name"), a.get("format")) == (b.get("name"), b.get("format"))


def add_seen(sid, source) -> dict | None:
    """같은 서식이 **다른 문서에서 또 나왔다**(spec_서식복사 ② §17 — 같은 서식은 한 번만 저장하므로 둘째 문서의 기록이 여기 남는다) → 지금 revision 의 meta(바뀌었든 아니든) | None(없는 서식).
    그 문서가 원본(`source`)이거나 이미 `seenIn` 에 있으면 그대로. revision 번호·고친 때(updated)·검증 기록은 안 바꾼다 — 서식의 모양이 바뀐 것이 아니다(`put_docx` 와 같은 붙이기)."""
    d = _dir(sid)
    if d is None or not isinstance(source, dict) or not source.get("name"):
        return get(sid)
    with _LOCK:
        rid, m = _healthy(d)
        if m is None:
            return None
        seen = [x for x in m.get("seenIn") or [] if isinstance(x, dict)]
        if same_doc(m.get("source"), source) or any(same_doc(x, source) for x in seen):
            return m
        m = {**m, "seenIn": [*seen, {k: source.get(k) for k in SEEN_KEYS}][-SEEN_MAX:]}
        _write(d / "revisions" / rid / META, _json(m))
        return m


def put_docx(sid, rid, data: bytes, losses=None) -> bool:
    """docx 운반 문서를 **그 revision 에 붙인다**(spec_서식복사 ② §4 — 옛 템플릿: 내려받기·검증 때 그 자리에서 지은 것) -> 붙였나(그 revision 이 없으면 · 빈 바이트면 False).
    revision 번호·고친 때(updated)는 그대로 — meta 에 `docx: {sha256, losses}` 를 적고 `carrier.docx` 를 더한다. 그 revision 에 성한 docx 가 이미 있으면 그대로 둔다(True).
    그 사이 새 revision 이 생겼으면 새 것에는 **hwpx 운반 문서가 같고 성한 docx 가 없을 때만** 함께 붙인다(`put_verify` 와 같은 규칙).
    새로 붙인 revision 의 `verifyDocx` 는 비운다(전에 있었다면 다른 docx 를 잰 것이다)."""
    d = _dir(sid)
    if d is None or not isinstance(data, (bytes, bytearray)) or not data:
        return False
    data = bytes(data)
    rec = _docx_meta({"losses": losses}, {CARRIER_DOCX: data})
    with _LOCK:
        m = _meta(d, rid)
        if m is None:
            return False
        cur = _current(d)
        now = _meta(d, cur) if cur != rid else None
        same = now is not None and now.get("carrierSha256") == m.get("carrierSha256")
        for r, meta in ((rid, m), *(((cur, now),) if same else ())):
            if _docx_bytes(d, r, meta) is not None:
                continue
            _write(d / "revisions" / r / CARRIER_DOCX, data)
            _write(d / "revisions" / r / META, _json({**meta, "docx": rec, "verifyDocx": None}))
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
