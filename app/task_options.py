"""워크플로우 옵션 — 워크플로우 묶음(프로젝트 · 워크플로우 · 라운드)마다 따로 두는 저장소. 지금 옵션 = 편집 구역이 보이는 기준(zones.dims).
원본 spec_구역 ② §1 「TASK 옵션 — TASK 묶음마다」(첫 줄은 /workflow 의 코드 옆 글이라 화면 말로 — 사양서의 절 이름은 그대로).

작업의 `task`(work.json — `PUT …/task` 가 정해진 키만 남긴다)에 넣지 않는다: 묶음에 문서가 여럿이라(이관의 두 문서 · 취합본과 기관 문서) 문서마다 값이 갈릴 수 있고,
task 를 통째로 다시 적는 길(TASK 시작 · 기관 문서 등록 · 이관 원본 등록 · 새 라운드 …)마다 옵션을 실어 날라야 한다.
- 파일 = 작업 폴더 뿌리의 `task_options.json` {version: 1, scopes: {<범위>: {zones: {dims: [...]}, rev, updated}}} — **사람이 정한 묶음만** 적는다(키 없음 = 기본값 · 빈 목록 = 사람이 끔).
- 범위(scope) = `p:<프로젝트>|<job>|<라운드>`(projects.group_key 와 같은 셋) | `w:<작업 id>`(프로젝트 없는 작업). 프로젝트 이름에 「|」 가 들어 있어도 섞이지 않는다(_split).
- 작업 저장이 꺼져 있으면(NFM_WORKS=off) 이 프로세스의 메모리에만.
- 파일이 깨졌으면(JSON 아님 · 꼴 다름) 덮어쓰지 않는다 — 읽기(resolve)는 기본값 · 사람이 정하는 쓰기(set_zones)는 Broken · 뒷정리(rename_project · copy_round · drop_project)는 아무것도 안 하고 0·False.
`app.server` 를 import 하지 않는다(끝점은 app/task_options_api.py)."""
import logging
import threading
from datetime import datetime

from app import projects, works, zones

log = logging.getLogger(__name__)

ZONES_DEFAULT = {"plan_merge": ["org"]}   # TASK(job) → 기본으로 켤 기준 — 그 밖의 job 은 []. 화면 task_catalog.js 의 TASK 항목 `zones` 와 같아야 한다(tests/test_task_catalog.py)


def _zones_default(job):
    """그 워크플로우의 기본 기준 — 붙박이는 ZONES_DEFAULT · 취합형으로 조립한 것은 붙박이 취합과 같게(기관 — 화면 task_catalog.js taskCatalogCustom 의 `zones` 와 같다) ·
    이관형 · 문서 하나로 조립한 것은 그 틀의 붙박이처럼 없음(붙박이 이관 · 양식 표준화 · 양식 맞추기 = [])."""
    if job in ZONES_DEFAULT:
        return ZONES_DEFAULT[job]
    from app import custom_tasks   # 가벼운 모듈
    return ZONES_DEFAULT["plan_merge"] if custom_tasks.is_gather(job) else []
FILE = "task_options.json"
_LOCK = threading.RLock()   # 읽고-고치고-쓰기를 묶는다(프로세스 안 하나)
_MEMORY = {}                # 작업 저장이 꺼져 있을 때의 scopes
_MEMORY_FLOW = {}           # 작업 저장이 꺼져 있을 때의 flow(실행의 옵션 — 아래 「실행의 옵션」)
_warned = False             # 깨진 저장 파일을 기록에 알렸나(resolve)


class Stale(Exception):
    """rev 를 줬는데 저장된 판과 다르다 — 다른 화면이 먼저 바꿈(끝점 409 staleOptions)."""


class Broken(ValueError):
    """저장 파일이 깨졌다(JSON 아님 · 꼴 다름) — 덮어쓰지 않는다(끝점 409). 값이 틀린 것(ValueError → 400)과 가르려고 따로 둔다."""


# ---- 범위(scope) ------------------------------------------------------------------------------------

def _group(work):
    """작업 → (프로젝트, job, 라운드) — projects.group_key 와 같은 셋(라운드 없는 옛 작업은 1). 프로젝트가 없으면 프로젝트 = ""."""
    task = (work or {}).get("task")
    task = task if isinstance(task, dict) else {}
    try:
        return projects.group_key(task)
    except ValueError:   # 프로젝트 이름이 글자가 아님(손으로 고친 work.json) — 프로젝트 없는 작업으로 본다
        return "", task.get("job") if isinstance(task.get("job"), str) else "", projects.round_of(task)


def _key(project, job, number):
    return f"p:{project}|{job}|{number}"


def _split(scope):
    """범위 열쇠 → (프로젝트, job, 라운드) | None(`w:` 범위 · 모르는 꼴).
    프로젝트 이름에 「|」 가 들어 있어도 정확히 갈린다 — job(server.TASK["job"] 의 낱말)과 라운드(숫자)에는 「|」 가 없어 **뒤에서 둘만** 뗀다."""
    if not isinstance(scope, str) or not scope.startswith("p:"):
        return None
    parts = scope[2:].rsplit("|", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return parts[0], parts[1], int(parts[2])


def scope_of(work) -> str:
    """그 작업의 TASK 묶음 열쇠 — 프로젝트가 있으면 `p:<프로젝트>|<job>|<라운드>`, 없으면 `w:<작업 id>`. 같은 묶음의 문서(이관의 두 문서 · 취합본과 기관 문서)는 같은 열쇠다."""
    project, job, number = _group(work)
    return _key(project, job, number) if project else f"w:{(work or {}).get('id') or ''}"


def _offered(work):
    """연구개발 문서인가 — task 가 없거나 task.kind == "rnd"(화면 app.js taskRnd() 와 같게: 빈 종류 "" · 일반 문서 "general" 은 아니다)."""
    task = (work or {}).get("task")
    return task.get("kind") == "rnd" if isinstance(task, dict) else True


# ---- 저장 ------------------------------------------------------------------------------------------

def _path():
    root = works.root()
    return root / FILE if root is not None else None


def _dims_ok(dims):
    return isinstance(dims, list) and all(isinstance(d, str) and d in zones.DIMS for d in dims)


def _record_ok(rec):
    """범위 하나의 꼴 {zones: {dims: [아는 기준 …]}, rev: 1 이상} — updated 는 없어도 된다."""
    z = rec.get("zones") if isinstance(rec, dict) else None
    return (isinstance(z, dict) and _dims_ok(z.get("dims"))
            and isinstance(rec.get("rev"), int) and not isinstance(rec.get("rev"), bool) and rec["rev"] >= 1)


def _load():
    """→ {"version": 1, "scopes": {…}} — _LOCK 안에서 부른다. 파일이 없으면 빈 것, 작업 저장이 꺼져 있으면 메모리의 것. 깨졌으면 Broken(부르는 쪽이 덮어쓰지 않는다)."""
    path = _path()
    if path is None:
        return {"version": 1, "scopes": _MEMORY, "flow": _MEMORY_FLOW}
    if not path.exists():
        return {"version": 1, "scopes": {}}
    data = works._read_json(path)   # 못 읽음 · JSON 아님 = None(바꿔 넣는 중인 파일은 몇 번 다시 읽는다 — works)
    if (not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("scopes"), dict)
            or not all(isinstance(k, str) and _record_ok(v) for k, v in data["scopes"].items())):
        raise Broken("워크플로우 옵션 저장 파일(task_options.json)을 읽지 못했습니다. 기존 파일을 확인하세요")
    return data


def _save(data):
    """원자적 쓰기(임시 파일 → 바꿔치기: works._write_json). 메모리일 때는 _load 가 준 사전을 그 자리에서 고친 것으로 끝난다."""
    path = _path()
    if path is not None:
        works._write_json(path, data)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _norm_dims(x):
    """zones.norm_dims 가 없을 때의 같은 일 — 목록이 아니거나 모르는 값이 있으면 ValueError, 중복을 버리고 zones.DIMS 차례로."""
    if not isinstance(x, list):
        raise ValueError("편집 구역의 기준은 목록이어야 합니다")
    bad = [d for d in x if not isinstance(d, str) or d not in zones.DIMS]
    if bad:
        raise ValueError(f"모르는 기준입니다: {' · '.join(str(d) for d in bad)} — 기관(org) · 단계(stage) · 차년도(year) 가운데서 고릅니다")
    return [d for d in zones.DIMS if d in x]


def _ordered(dims):
    return [d for d in zones.DIMS if d in dims]


# ---- 읽기 · 정하기 -----------------------------------------------------------------------------------

def resolve(work) -> dict:
    """→ {scope, offered, zones: {dims, defaulted}, rev} — work = works.work(wid) 의 사전({id, task}) | None.
    offered = 연구개발 문서인가(_offered). dims = 사람이 정한 것(빈 목록 = 끔) → 없으면 그 TASK 의 기본값(ZONES_DEFAULT · defaulted True), 늘 zones.DIMS 차례. rev = 저장된 판(없으면 0).
    offered 가 False 여도 꼴은 같다(dims [] · defaulted True · rev 0). 저장 파일이 깨졌으면 기본값으로 읽는다(덮어쓰지 않는다)."""
    global _warned
    scope, job = scope_of(work), _group(work)[1]
    if not _offered(work):
        return {"scope": scope, "offered": False, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    rec = None
    with _LOCK:
        try:
            rec = _load()["scopes"].get(scope)
            _warned = False
        except Broken as exc:
            if not _warned:   # 구역을 읽을 때마다 불린다 — 깨진 동안 한 번만 적는다
                log.warning("[TASK 옵션] %s — 기본값으로 읽습니다", exc)
            _warned = True
    if rec is None:
        return {"scope": scope, "offered": True, "zones": {"dims": _ordered(_zones_default(job)), "defaulted": True}, "rev": 0}
    return {"scope": scope, "offered": True, "zones": {"dims": _ordered(rec["zones"]["dims"]), "defaulted": False}, "rev": rec["rev"]}


def set_zones(work, dims, rev=None, scope=None) -> dict:
    """그 묶음의 편집 구역 기준을 사람이 정한다 → resolve 와 같은 꼴(defaulted False). 기본값과 같은 값 · 빈 목록(끔)도 적는다. 저장하면 판 +1.
    ValueError = 모르는 기준 · 목록 아님(zones.norm_dims) · 연구개발 문서가 아님 · Stale = rev 를 줬는데 저장된 판과 다름 · **scope 를 줬는데 그 작업의 지금 묶음과 다름** · Broken = 저장 파일이 깨짐(덮어쓰지 않는다).
    scope = 화면이 옵션을 읽을 때의 묶음(astra 결과 검토 7): 읽은 뒤 작업이 다른 프로젝트·TASK·라운드로 옮겨졌으면 판(rev)이 우연히 같아도 다른 묶음의 옵션을 덮지 않는다."""
    if not _offered(work):
        raise ValueError("이 워크플로우에는 편집 구역 옵션이 없습니다 — 연구개발 워크플로우(양식 표준화 · 양식 맞추기 · 취합 · 이관)의 문서에서만 씁니다")
    try:
        dims = list(getattr(zones, "norm_dims", _norm_dims)(dims))
    except TypeError as exc:   # 목록 안에 글자가 아닌 것(목록 · 사전) — 모르는 기준과 같은 400
        raise ValueError("모르는 기준입니다 — 기관(org) · 단계(stage) · 차년도(year) 가운데서 고릅니다") from exc
    want, scope = scope, scope_of(work)
    if scope == "w:":   # 프로젝트도 작업 id 도 없다 — 어느 묶음의 옵션인지 알 수 없다
        raise ValueError("작업이 없어 워크플로우 옵션을 저장할 수 없습니다")
    if want is not None and want != scope:
        raise Stale(scope)
    with _LOCK:
        data = _load()
        old = data["scopes"].get(scope)
        if rev is not None and rev != (old["rev"] if old else 0):
            raise Stale(scope)
        rec = {**(old or {}), "zones": {**((old or {}).get("zones") or {}), "dims": dims}, "rev": (old["rev"] if old else 0) + 1, "updated": _now()}
        data["scopes"][scope] = rec
        _save(data)
        return {"scope": scope, "offered": True, "zones": {"dims": _ordered(dims), "defaulted": False}, "rev": rec["rev"]}


# ---- 실행의 옵션(spec_워크플로우 ② §17-6 「건너뛰기」) -------------------------------------------------------
# 워크플로우 실행이 읽는 묶음마다의 값 — 지금 `llmSkip`(사람이 「LLM 검증·보완」 을 건너뛴 문서 id 들: 스크립트 분석만으로 진행). 편집 구역 기준(scopes)과 **따로** 둔다(파일 머리의 `flow` 사전 — 같은 범위 열쇠):
# 그 판(rev)을 같이 올리지 않고(편집 구역 화면의 「다른 화면이 먼저 바꿈」 이 걸리지 않게), 옛 판의 코드가 읽어도 scopes 의 꼴이 그대로다(머리의 모르는 키는 그대로 다시 쓰인다).
# 새 라운드로 잇지 않는다(문서 id 가 다르다) · 사람이 정한 것만 적는다(빈 목록이 되면 그 열쇠를 지운다).

def _flow_of(data):
    f = data.get("flow")
    if not isinstance(f, dict):
        f = data["flow"] = {}
    return f


def _skip_ids(rec):
    ids = rec.get("llmSkip") if isinstance(rec, dict) else None
    return [x for x in ids if isinstance(x, str)] if isinstance(ids, list) else []


def flow(work) -> dict:
    """그 묶음의 실행 옵션 → {llmSkip: [문서 id …]}(없으면 빈 목록). 저장 파일이 깨졌으면 빈 것으로 읽는다(덮어쓰지 않는다)."""
    scope = scope_of(work)
    with _LOCK:
        try:
            return {"llmSkip": _skip_ids(_flow_of(_load()).get(scope))}
        except Broken:
            return {"llmSkip": []}


def flow_skip(work, doc_id, on) -> list:
    """그 묶음의 「건너뛰기」 에 문서를 넣거나(on) 뺀다 → 지금 건너뛴 문서 id 들. Broken = 저장 파일이 깨짐(덮어쓰지 않는다) · ValueError = 작업이 없어 묶음을 알 수 없음."""
    scope = scope_of(work)
    if scope == "w:" or not isinstance(doc_id, str) or not doc_id:
        raise ValueError("작업이 없어 워크플로우 옵션을 저장할 수 없습니다")
    with _LOCK:
        data = _load()
        box = _flow_of(data)
        ids = _skip_ids(box.get(scope))
        new = [x for x in ids if x != doc_id] + ([doc_id] if on else [])
        if new != ids:
            if new:
                box[scope] = {**(box.get(scope) if isinstance(box.get(scope), dict) else {}), "llmSkip": new, "updated": _now()}
            else:
                box.pop(scope, None)
            _save(data)
        return new


def flow_forget(doc_id) -> int:
    """작업 내용 초기화 · 작업 지우기 — 그 문서의 「건너뛰기」 를 모든 묶음에서 뺀다 → 뺀 수(뒷정리라 예외를 내지 않는다)."""
    def change(box):
        n = 0
        for k in list(box):
            ids = _skip_ids(box[k])
            if doc_id in ids:
                n += 1
                left = [x for x in ids if x != doc_id]
                if left:
                    box[k] = {**box[k], "llmSkip": left}
                else:
                    del box[k]
        return n
    return _tidy(f"건너뛰기 지우기({doc_id})", lambda scopes: 0, change)


# ---- 뒷정리 — 프로젝트 이름 변경 · 새 라운드 · 프로젝트 삭제(server.py 가 부른다) -----------------------------------
# 옵션은 보이는 것을 고르는 값일 뿐이라 이 셋은 예외를 내지 않는다(프로젝트 이름 변경·새 라운드가 옵션 파일 때문에 중간에 끊기지 않게) — 못 하면 기록에 남기고 0·False.

def _tidy(what, change, more=None):
    """_LOCK 안에서 change(scopes) → 바뀐 수. 0 이 아니면 저장한다. 깨진 파일 · 못 쓴 파일은 그대로 두고 0.
    more(flow) = 실행의 옵션(머리의 flow — 같은 범위 열쇠)도 같이 고친다 → 바뀐 수(scopes 가 안 바뀌었으면 이 수를 돌려준다)."""
    with _LOCK:
        try:
            data = _load()
            n = change(data["scopes"])
            m = more(data["flow"]) if more is not None and isinstance(data.get("flow"), dict) and data["flow"] else 0
            if n or m:
                _save(data)
            return n or m
        except (Broken, OSError) as exc:
            log.warning("[TASK 옵션] %s 을(를) 하지 못했습니다: %r", what, exc)
            return 0


def rename_project(old, new) -> int:
    """프로젝트 이름 변경 — 그 프로젝트의 열쇠(모든 TASK · 라운드)를 새 이름으로 옮긴다 → 옮긴 열쇠 수.
    **새 이름의 열쇠가 이미 있으면 안 덮는다**(옛 것만 지운다 — astra 결과 검토 7): 서버가 작업의 소속을 새 이름으로 바꾼 뒤 이 함수를 부르기까지의 사이에 사람이 새 이름으로 정한 옵션이 그것이다
    (없어진 프로젝트의 열쇠는 drop_project 가 그때 지운다 — 남아 있지 않다)."""
    try:
        old, new = projects.normalize_name(old), projects.normalize_name(new)
    except ValueError:
        return 0
    if not old or not new or old == new:
        return 0

    def change(scopes):
        moved = [(k, _split(k)) for k in list(scopes)]
        moved = [(k, g) for k, g in moved if g is not None and g[0] == old]
        for k, (_, job, number) in moved:
            rec = scopes.pop(k)
            scopes.setdefault(_key(new, job, number), rec)   # 새 이름으로 이미 정한 것이 있으면 그것을 둔다
        return len(moved)
    return _tidy(f"프로젝트 이름 변경({old} → {new})", change, change)   # 실행의 옵션(flow)도 같은 열쇠 — 같이 옮긴다


def drop_project(name) -> int:
    """프로젝트를 문서까지 지울 때 — 그 프로젝트의 열쇠를 모두 지운다 → 지운 열쇠 수."""
    try:
        name = projects.normalize_name(name)
    except ValueError:
        return 0
    if not name:
        return 0

    def change(scopes):
        gone = [k for k in scopes if (_split(k) or ("",))[0] == name]
        for k in gone:
            del scopes[k]
        return len(gone)
    return _tidy(f"프로젝트 삭제({name})", change, change)   # 실행의 옵션(flow)도 같이 지운다


def copy_round(task_from, task_to) -> bool:
    """새 라운드 — 앞 묶음(task_from 의 프로젝트 · TASK · 라운드)에 **사람이 정한 것이 있을 때만** 새 묶음(task_to)에 같은 기준을 판 1 로 적는다 → 적었나.
    새 묶음에 이미 있으면 안 덮는다(묶음의 문서마다 불러도 한 번만 적힌다). 프로젝트가 없는 task 는 묶음이 없어 False."""
    src, dst = _group({"task": task_from}), _group({"task": task_to})
    if not src[0] or not dst[0] or src == dst:
        return False

    def change(scopes):
        rec = scopes.get(_key(*src))
        if rec is None or _key(*dst) in scopes:
            return 0
        scopes[_key(*dst)] = {"zones": {"dims": _ordered(rec["zones"]["dims"])}, "rev": 1, "updated": _now()}
        return 1
    return bool(_tidy(f"새 라운드로 옵션 잇기({_key(*src)} → {_key(*dst)})", change))
