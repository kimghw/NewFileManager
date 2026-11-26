"""프로젝트의 공유 구분 설정과 워크플로우 라운드 범위. 문서·반영 상태는 작업별로 둔다."""
import copy
import json
import secrets
import threading
import time

from app import division_model, works

_LOCK = threading.RLock()
ROUND_LOCK = threading.Lock()
VERSION_MAX = 50        # 프로젝트 하나의 구분 기준 버전 수(spec_작업 ② §19)
VERSION_NAME_MAX = 40   # 버전 이름 길이(공백 정리 뒤)


class VersionError(Exception):
    """구분 기준 버전 오류의 뿌리 — 저장 파일 손상(ValueError)과 섞이지 않게 ValueError 가 아니다."""


class VersionName(VersionError):
    """버전 이름이 없거나 길다(400)."""


class VersionConflict(VersionError):
    """그 프로젝트에 같은 이름의 버전이 있다(409 — replace 일 때만 덮어씀)."""


class VersionLimit(VersionError):
    """버전이 VERSION_MAX 개 찼다(409)."""


class VersionMissing(VersionError):
    """그런 버전이 없다(404)."""


def normalize_name(value):
    if not isinstance(value, str):
        raise ValueError("프로젝트 이름은 글자여야 합니다")
    return " ".join(value.split())[:60]


# ---- 임시 프로젝트(spec_작업 ② §17 「임시 프로젝트」 — 2026-11-18 사용자 "파일을 올릴 때 프로젝트 이름을 넣지 않으면 임시이름을 넣어주고 프로젝트 명을 입력하면 그때 이름을 바꿔주는 식으로") ----
# 이름이 곧 표시다(따로 기록하지 않는다) — 「임시 프로젝트 N」. 화면 app/static/project_workspace.js PROJECT_TEMP_RE 와 같은 꼴.
TEMP_PREFIX = "임시 프로젝트 "
TEMP_RE = works.TEMP_PROJECT_RE   # 원본은 works(보이는 이름이 임시 이름을 안 붙인다 — works 가 projects 를 가져다 쓸 수 없어 거기 둔다)


def is_temp(name):
    """「임시 프로젝트 N」 꼴의 이름인가(정규화한 뒤)."""
    return isinstance(name, str) and bool(TEMP_RE.fullmatch(" ".join(name.split())))


def temp_name(rows=None):
    """다음 임시 이름 — 작업의 프로젝트 이름과 projects.json 기록에 쓰인 임시 번호의 **최댓값 + 1**(번호 차례가 올린 차례와 같다 · 비어 있는 작은 번호를 메우지 않는다).
    기록만 남은 임시 이름도 쓰인 것으로 센다 — 그 이름을 다시 주면 옛 프로젝트 구성을 물려받는다. ROUND_LOCK 안에서 부르고 바로 적는다."""
    used = {group_key(w.get("task"))[0] for w in (works.list_works() if rows is None else rows)}
    with _LOCK:
        used |= set(_read()["projects"]) if _path() is not None else set()
    numbers = [int(n[len(TEMP_PREFIX):]) for n in used if is_temp(n)]
    return f"{TEMP_PREFIX}{max(numbers, default=0) + 1}"


def round_of(task):
    value = (task or {}).get("round", 1)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 1


def group_key(task):
    task = task or {}
    return normalize_name(task.get("project") or ""), task.get("job") or "", round_of(task)


def latest_round(task, listing=None):
    project, job, number = group_key(task)
    if not project:
        return number
    return max([number, *(round_of(w.get("task")) for w in (works.list_works() if listing is None else listing)
                          if group_key(w.get("task"))[:2] == (project, job))])


def _path():
    root = works.root()
    return root / "projects.json" if root is not None else None


def _version_ok(v):
    """버전 하나의 꼴 {id, name, values, hash, at}."""
    return (isinstance(v, dict) and isinstance(v.get("id"), str) and bool(v["id"]) and isinstance(v.get("name"), str) and bool(v["name"])
            and isinstance(v.get("values"), dict) and isinstance(v.get("hash"), str)
            and isinstance(v.get("at"), (int, float)) and not isinstance(v.get("at"), bool))


def _read():
    path = _path()
    if path is None or not path.exists():
        return {"version": 1, "projects": {}}
    try:
        data = json.loads(path.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("projects"), dict):
            raise ValueError("지원하지 않는 저장 형식")
        for name, record in data["projects"].items():
            if not isinstance(name, str) or not isinstance(record, dict):
                raise ValueError("프로젝트 설정 형식 오류")
            settings = record.get("settings")   # 없어도 된다 — 「새 프로젝트」 로 만든 문서·구성 없는 프로젝트(spec_작업 ② §17 「새 프로젝트」)
            if settings is not None and (not isinstance(settings, dict) or settings.get("schemaVersion") != 1
                                         or not isinstance(settings.get("profileId"), str) or not isinstance(settings.get("values"), dict)):
                raise ValueError("프로젝트 구성 설정 형식 오류")
            if record.get("confirmed") is not None and not isinstance(record["confirmed"], dict):   # 1단계 확정(spec_작업 ② §18) — 없어도 된다
                raise ValueError("프로젝트 구성 확정 형식 오류")
            refs = record.get("refs")   # 이 프로젝트의 참조 문서(문서 라이브러리의 문서 id — spec_양식작성 ② §2-1) — 없어도 된다
            if refs is not None and not (isinstance(refs, list) and all(isinstance(r, str) for r in refs)):
                raise ValueError("프로젝트 참조 문서 형식 오류")
            rows = record.get("versions")   # 구분 기준 버전(② §19) — 없어도 된다
            if rows is not None and not (isinstance(rows, list) and all(_version_ok(v) for v in rows)
                                         and len({v["id"] for v in rows}) == len(rows)):
                raise ValueError("프로젝트 구성 버전 형식 오류")
        return data
    except (OSError, ValueError) as exc:
        raise ValueError("프로젝트 구성 저장 파일을 읽지 못했습니다. 기존 파일을 확인하세요") from exc   # 화면 말 = 「프로젝트 구성」(spec_작업 ② §19)


def get(name):
    with _LOCK:
        return copy.deepcopy(_read()["projects"].get(normalize_name(name)))


def settings(name, value=None, *, seed=False):
    """None은 읽기. seed는 기존 공유 설정이 없을 때만 문서 설정으로 시작한다."""
    name = normalize_name(name)
    if not name or _path() is None:
        return None
    with _LOCK:
        data = _read()
        old = data["projects"].get(name)
        if value is not None and (not seed or old is None or old.get("settings") is None):   # 구성 없는 기록(새 프로젝트)에도 문서의 값으로 시작한다
            if old is None or old.get("settings") != value:
                old = {**(old or {}), "settings": copy.deepcopy(value), "updated": time.time()}   # 확정(confirmed)은 남긴다 — 맞는지는 hash 로 따진다(② §18)
                data["projects"][name] = old
                works._write_json(_path(), data)
        return copy.deepcopy(old.get("settings")) if old else None


def confirm(name, settings):
    """1단계 「구성 확정」(spec_작업 ② §18) — 프로젝트 구성을 settings 로 두고 확정 {at, hash, values} 을 적는다 → 확정 사본. 이름·작업 폴더가 없으면 None.
    저장 파일이 깨졌으면 ValueError(덮지 않는다)."""
    name = normalize_name(name)
    if not name or _path() is None:
        return None
    with _LOCK:
        data = _read()
        now = time.time()
        confirmed = {"at": now, "hash": division_model.settings_hash(settings), "values": copy.deepcopy(settings["values"])}
        data["projects"][name] = {**(data["projects"].get(name) or {}), "settings": copy.deepcopy(settings), "updated": now, "confirmed": confirmed}
        works._write_json(_path(), data)
        return copy.deepcopy(confirmed)


def confirmed(name):
    """그 프로젝트의 확정 {at, hash, values} 사본 | None."""
    name = normalize_name(name)
    if not name or _path() is None:
        return None
    with _LOCK:
        record = _read()["projects"].get(name) or {}
    return copy.deepcopy(record.get("confirmed")) if isinstance(record.get("confirmed"), dict) else None


# ---- 구분 기준 버전(spec_작업 ② §19) — 프로젝트의 구분 기준을 이름 붙여 남긴 목록. 지금 구분 기준(settings·confirmed)은 건드리지 않는다 ----

def version_name(value):
    """버전 이름 정리(공백 정리 뒤 1~VERSION_NAME_MAX 자) — 틀리면 VersionName."""
    if not isinstance(value, str) or not value.strip():
        raise VersionName("버전 이름을 넣으세요")
    value = " ".join(value.split())
    if len(value) > VERSION_NAME_MAX:
        raise VersionName(f"버전 이름은 {VERSION_NAME_MAX}자까지입니다")
    return value


def versions(name):
    """그 프로젝트의 버전 [{id, name, values, hash, at}] 사본(저장한 차례). 이름·작업 폴더·기록이 없으면 []. 저장 파일이 깨졌으면 ValueError."""
    name = normalize_name(name)
    if not name or _path() is None:
        return []
    with _LOCK:
        record = _read()["projects"].get(name) or {}
    return copy.deepcopy(record.get("versions") or [])


def version_get(name, vid):
    """버전 하나의 사본 — 없으면 VersionMissing."""
    for item in versions(name):
        if item["id"] == vid:
            return item
    raise VersionMissing("그런 프로젝트 구성 버전이 없습니다")


def version_save(name, title, settings, *, replace=False):
    """settings 를 title 이름의 버전으로 남긴다 → 그 버전 사본. hash = settings_hash(settings) — 확정과 같은 꼴.
    같은 이름이 있으면 replace 일 때만 덮어쓴다(id·자리 유지 · at 갱신) — 아니면 VersionConflict. 새 이름인데 VERSION_MAX 개 찼으면 VersionLimit.
    이름이 틀리면 VersionName, 저장 파일이 깨졌으면 ValueError(덮지 않는다). 프로젝트 이름·작업 폴더가 없으면 None.
    프로젝트 기록이 아직 없으면 settings 를 그 프로젝트의 입력으로 한 기록을 만든다(confirm 과 같은 방식)."""
    title = version_name(title)
    name = normalize_name(name)
    if not name or _path() is None:
        return None
    with _LOCK:
        data = _read()
        record = data["projects"].get(name)
        rows = list((record or {}).get("versions") or [])
        now = time.time()
        item = {"id": "", "name": title, "values": copy.deepcopy(settings["values"]), "hash": division_model.settings_hash(settings), "at": now}
        at = next((i for i, v in enumerate(rows) if v["name"] == title), None)
        if at is not None:
            if not replace:
                raise VersionConflict(f"같은 이름의 버전 「{title}」 이 이미 있습니다")
            item["id"] = rows[at]["id"]
            rows[at] = item
        else:
            if len(rows) >= VERSION_MAX:
                raise VersionLimit(f"프로젝트 구성 버전은 프로젝트마다 {VERSION_MAX}개까지입니다 — 안 쓰는 버전을 지우세요")
            used = {v["id"] for v in rows}
            while not item["id"] or item["id"] in used:
                item["id"] = secrets.token_hex(4)
            rows.append(item)
        base = dict(record or {})
        if base.get("settings") is None:   # 기록이 없거나 구성 없는 기록(새 프로젝트) — 버전의 값을 그 프로젝트의 입력으로
            base["settings"] = copy.deepcopy(settings)
        data["projects"][name] = {**base, "versions": rows, "updated": now}
        works._write_json(_path(), data)
        return copy.deepcopy(item)


def version_delete(name, vid):
    """버전 하나를 지운다 → 지운 버전 사본. 없으면 VersionMissing, 저장 파일이 깨졌으면 ValueError. 지금 구분 기준·확정은 그대로."""
    name = normalize_name(name)
    if not name or _path() is None:
        raise VersionMissing("그런 프로젝트 구성 버전이 없습니다")
    with _LOCK:
        data = _read()
        record = data["projects"].get(name) or {}
        rows = list(record.get("versions") or [])
        gone = next((v for v in rows if v["id"] == vid), None)
        if gone is None:
            raise VersionMissing("그런 프로젝트 구성 버전이 없습니다")
        data["projects"][name] = {**record, "versions": [v for v in rows if v["id"] != vid], "updated": time.time()}
        works._write_json(_path(), data)
        return copy.deepcopy(gone)


# ---- 이 프로젝트의 참조 문서(spec_양식작성 ② §2-1 — 2026-11-26 사용자 「있는 추출할때 전부 참조할 수 있지만 사용자가 선택한 문서만 사용할 수 있게 해줘, 선택된.
#      이 프로젝트의 참고 문헌은 문서 라이브러리랑 탭이든 뭐든 구분이 되어야함」) — 문서 라이브러리(따로 선 서버 · 모든 작업이 같이 봄)에서 사람이 고른 문서 id 목록.
#      고른 차례대로 · 문서 라이브러리의 문서 · 추출은 건드리지 않는다(고르기만). 이름 바꾸기는 기록째 따라가고 지우기는 기록째 사라진다.
REFS_MAX = 200


def refs(name):
    """그 프로젝트의 참조 문서 id 목록(고른 차례). 이름 · 작업 폴더 · 기록이 없으면 []. 저장 파일이 깨졌으면 ValueError."""
    name = normalize_name(name)
    if not name or _path() is None:
        return []
    with _LOCK:
        return list((_read()["projects"].get(name) or {}).get("refs") or [])


def refs_set(name, doc, on):
    """참조 문서 하나를 넣거나(on) 뺀다 → 바뀐 목록. 기록이 없으면 만든다(넣을 때만). 이름 · 작업 폴더가 없으면 None · 넘치면 ValueError(덮지 않는다)."""
    name = normalize_name(name)
    if not name or _path() is None:
        return None
    with _LOCK:
        data = _read()
        record = data["projects"].get(name)
        rows = list((record or {}).get("refs") or [])
        if on and doc not in rows:
            if len(rows) >= REFS_MAX:
                raise ValueError(f"참조 문서는 프로젝트마다 {REFS_MAX}개까지입니다")
            rows.append(doc)
        elif not on and doc in rows:
            rows.remove(doc)
        else:
            return rows
        now = time.time()
        data["projects"][name] = {**(record or {"created": now}), "refs": rows, "updated": now}
        works._write_json(_path(), data)
        return rows


def listing():
    """프로젝트 → TASK → 라운드. 진행중 여부는 최신 라운드이며 완료를 추측하지 않는다.
    작업이 하나도 없고 projects.json 에 기록만 남은 프로젝트(문서 없는 프로젝트 — spec_작업 ② §17)도 낸다: works·tasks 가 [] 이고 updated 는 기록의 것."""
    rows = works.list_works()
    groups = {}
    for work in rows:
        project, job, number = group_key(work.get("task"))
        if project:
            groups.setdefault(project, {}).setdefault((job, number), []).append(work)
    with _LOCK:
        records = _read()["projects"]
    result = []
    for name in [*groups, *(n for n in records if n not in groups)]:   # 뒤쪽 = 문서 없는 프로젝트(기록만)
        tasks = groups.get(name, {})
        record = records.get(name) or {}
        entries = []
        for (job, number), members in tasks.items():
            latest = number == max(n for j, n in tasks if j == job)
            role = works.TARGET_FILE.get(job) or ("report" if job.startswith("report_") else "plan")
            main = next((w for w in members if (w.get("task") or {}).get("file") == role), members[0])
            entries.append({"job": job, "round": number, "latest": latest,
                            "status": "in_progress" if latest else "previous", "docId": main["id"],
                            "works": [w["id"] for w in members]})
        result.append({"name": name, "temp": is_temp(name), "settings": copy.deepcopy(record.get("settings")),
                       "confirmed": copy.deepcopy(record["confirmed"]) if isinstance(record.get("confirmed"), dict) else None,   # 1단계 확정(② §18)
                       "versions": [{k: copy.deepcopy(v[k]) for k in ("id", "name", "at", "values")} for v in record.get("versions") or []],   # 구분 기준 버전(② §19)
                       "updated": max([record.get("updated", 0), *(w.get("updated", 0) for members in tasks.values() for w in members)]),
                       "works": [w["id"] for members in tasks.values() for w in members],
                       "tasks": sorted(entries, key=lambda item: (item["job"], -item["round"]))})
    return sorted(result, key=lambda item: item["updated"], reverse=True)


def rename(old, new):
    """projects.json 기록을 새 이름으로 옮긴다(settings 그대로, updated 갱신). 기록이 없으면 False."""
    with _LOCK:
        data = _read()
        record = data["projects"].pop(old, None)
        if record is None:
            return False
        record["updated"] = time.time()
        data["projects"][new] = record
        works._write_json(_path(), data)
        _purpose("moved", old, new)   # 프로젝트의 문서 목적(purpose.yaml — spec_양식작성 ② §5-9)도 새 이름으로 따라간다
        return True


def _purpose(what, *names):
    """프로젝트의 문서 목적 파일(app/purpose_yaml.py)을 이름 바꾸기 · 지우기에 따라가게 한다 — 못 해도 프로젝트 기록의 일은 그대로다."""
    try:
        from app import purpose_yaml
        getattr(purpose_yaml, what)(*names)
    except Exception:   # noqa: BLE001 — 덤이다
        pass


def create(name):
    """「새 프로젝트」(spec_작업 ② §17) — 문서·구성 없는 기록 {created, updated} 을 만든다. 이미 기록이 있으면 False(부르는 쪽이 작업의 이름까지 보고 409).
    저장 파일이 깨졌으면 ValueError(덮지 않는다)."""
    name = normalize_name(name)
    if not name or _path() is None:
        return False
    with _LOCK:
        data = _read()
        if name in data["projects"]:
            return False
        now = time.time()
        data["projects"][name] = {"created": now, "updated": now}
        works._write_json(_path(), data)
        return True


def absorb(src, dst):
    """임시 프로젝트를 이미 있는 프로젝트로 옮길 때(spec_작업 ② §17 「임시 프로젝트」) — src 의 기록을 지운다. dst 에 구성이 없으면(기록 없음 · 새 프로젝트)
    src 의 구성 · 확정 · 버전을 dst 로 옮겨 붙이고, 있으면 dst 것을 그대로 둔다(문서들은 다음 맞춤에서 dst 의 구성을 받는다). → src 기록이 있었나."""
    with _LOCK:
        data = _read()
        record = data["projects"].pop(src, None)
        if record is None:
            return False
        cur = data["projects"].get(dst)
        if record.get("settings") is not None and (cur is None or cur.get("settings") is None):
            carry = {k: copy.deepcopy(record[k]) for k in ("settings", "confirmed", "versions") if k in record}
            data["projects"][dst] = {**(cur or {}), **carry, "updated": time.time()}
        if record.get("refs"):   # 참조 문서는 구성과 따로 — 늘 합친다(겹침 없이 · dst 의 차례가 먼저)
            cur = data["projects"].get(dst) or {}
            have = list(cur.get("refs") or [])
            data["projects"][dst] = {**cur, "refs": have + [r for r in record["refs"] if r not in have], "updated": time.time()}
        works._write_json(_path(), data)
        return True


def remove(name):
    """projects.json 의 프로젝트 기록(공유 구분 기준)을 지운다. 기록이 없으면 False."""
    with _LOCK:
        data = _read()
        if data["projects"].pop(name, None) is None:
            return False
        works._write_json(_path(), data)
        _purpose("removed", name)   # 문서 목적 파일은 지우지 않고 _purpose/_removed/ 로 옮긴다
        return True
