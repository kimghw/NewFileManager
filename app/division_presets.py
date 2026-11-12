"""저장한 과제 구성(spec_구분_기준 ② §0 용어 · §7 presets · §8 「저장한 과제 구성」 — 2026-11-11 까지 「저장한 구분 기준」) — FileMergeManager `division_presets.py` 를 NFM 경로·프로파일 계약으로 옮긴 것.
파일 = {"version": 1, "presets": {id: {"name", "profileId", "values", "updatedAt"}}} — %LOCALAPPDATA%\\NewFileManager\\division_presets.json,
env NFM_DIVISION_PRESETS 가 있으면 그것(시험·격리 서버). 값은 프로파일의 norm_values 를 다시 통과(저장은 늘 정리한 꼴 — FMM v1 값 그대로 가져올 수 있다).
통째 원자적 저장(임시 파일 → 바꿔 넣기, 프로세스 안 잠금). 손상 파일(JSON·꼴·version·항목 값 오류): 조회(load·state)는 빈 목록 + broken 표시 + .broken 사본,
고치는 읽기(strict — put·delete)는 Broken 으로 멈춘다(정상 항목까지 빈 목록으로 덮어쓰지 않음 — 2026-11-11 astra P1). 틀린 이름·값은 ValueError, 같은 이름은 Conflict, 없는 id 는 KeyError."""
import json
import logging
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from app import division_profiles

VERSION = 1
NAME_MAX = 60
log = logging.getLogger(__name__)
_LOCK = threading.Lock()


class Conflict(ValueError):
    """다른 저장 항목과 이름이 같음(409)."""


class Broken(ValueError):
    """저장 파일이 손상됨 — 고치지 않는다(503)."""


def presets_path():
    if env := os.environ.get("NFM_DIVISION_PRESETS"):
        return Path(env)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "division_presets.json"


def empty():
    return {"version": VERSION, "presets": {}}


def _name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("이름을 넣으세요")
    name = re.sub(r"\s+", " ", name.strip())
    if len(name) > NAME_MAX:
        raise ValueError(f"이름은 {NAME_MAX}자 이하")
    return name


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _values(prof, values):
    """프로파일 norm_values — 값 꼴이 아예 틀린 것(orgs 가 글 등)도 ValueError 로(500 이 아니라 400)."""
    try:
        return prof.norm_values(values)
    except (TypeError, AttributeError) as e:
        raise ValueError(f"값 꼴이 틀립니다: {e}") from e


def _clean(data):
    if not isinstance(data, dict) or not isinstance(data.get("presets", {}), dict):
        raise ValueError("저장한 과제 구성 파일 꼴이 아닙니다")
    if data.get("version") != VERSION:
        raise ValueError(f"지원하지 않는 파일 판 {data.get('version')!r}(지원 {VERSION})")
    out = empty()
    for pid, p in (data.get("presets") or {}).items():
        if not isinstance(pid, str) or not isinstance(p, dict):
            raise ValueError(f"presets.{pid}: 항목이 아님")
        try:
            prof = division_profiles.get(p.get("profileId") or "rnd")
            values = _values(prof, p.get("values"))
        except KeyError as e:
            raise ValueError(f"presets.{pid}: 모르는 프로파일 {e}") from e
        except ValueError as e:
            raise ValueError(f"presets.{pid}: {e}") from e
        at = p.get("updatedAt")
        out["presets"][pid] = {"name": _name(p.get("name")), "profileId": prof.ID, "values": values,
                               "updatedAt": at if isinstance(at, str) and at else _now()}
    return out


def _read(p):
    """파일 → 정리한 자료. 없으면 빈 목록. 못 읽으면 OSError, 손상(JSON·꼴·판·항목 값)이면 Broken."""
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return empty()
    try:
        return _clean(json.loads(raw.decode("utf-8")))
    except (ValueError, KeyError) as e:   # json 오류도 ValueError
        raise Broken(f"저장한 과제 구성 파일이 손상되어 고치지 않았습니다: {p} ({e}) — 파일을 고치거나 옮긴 뒤 다시(.broken 사본 참고)") from e


def _keep_broken(p):
    try:
        shutil.copyfile(p, p.with_name(p.name + ".broken"))
    except OSError:
        pass


def load(path=None, strict=False):
    """strict=False(조회) = 못 읽거나 손상이면 빈 목록(손상은 .broken 사본 + 경고). strict=True(고치기 전) = 못 읽으면 OSError, 손상이면 Broken 으로 멈춤."""
    p = Path(path) if path else presets_path()
    if strict:
        return _read(p)
    try:
        return _read(p)
    except Broken as e:
        log.warning("저장한 과제 구성 파일이 손상되어 빈 목록으로 보입니다(원본은 .broken 으로 보관): %s", e)
        _keep_broken(p)
        return empty()
    except OSError as e:
        log.warning("저장한 과제 구성 파일을 읽지 못해 빈 목록으로 봅니다: %s (%s)", p, e)
        return empty()


def state(path=None):
    """조회용 {"presets": [...], "broken": bool} — broken = 파일이 있는데 못 읽거나 손상(빈 목록으로 보이고 저장·삭제는 503)."""
    p = Path(path) if path else presets_path()
    try:
        data = _read(p)
    except Broken as e:
        log.warning("저장한 과제 구성 파일이 손상되어 빈 목록으로 보입니다(원본은 .broken 으로 보관): %s", e)
        _keep_broken(p)
        return {"presets": [], "broken": True}
    except OSError as e:
        log.warning("저장한 과제 구성 파일을 읽지 못해 빈 목록으로 봅니다: %s (%s)", p, e)
        return {"presets": [], "broken": True}
    return {"presets": listing(data), "broken": False}


def save(data, path=None):
    p = Path(path) if path else presets_path()
    data = _clean(data)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    tmp.write_bytes(json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
    for i in range(6):   # 잠긴 파일(백신·색인기)은 짧게 다시
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, p)


def new_id(table):
    nums = [int(m[1]) for k in table if (m := re.fullmatch(r"p(\d+)", k))]
    return f"p{max(nums, default=0) + 1}"


def _item(pid, p):
    return {"id": pid, **p}


def listing(data=None):
    data = load() if data is None else data
    return [_item(pid, p) for pid, p in sorted(data["presets"].items(), key=lambda kv: (kv[1]["name"], kv[0]))]


def put(pid, name, values, profile_id="rnd"):
    """pid "new" = 새로(p1·p2…), 있는 id = 덮어씀 -> 저장한 항목. 이름·값이 틀리면 ValueError, 같은 이름은 Conflict, 없는 id 는 KeyError, 저장 파일 손상은 Broken."""
    prof = division_profiles.get(profile_id)
    name, values = _name(name), _values(prof, values)
    with _LOCK:
        data = load(strict=True)
        ps = data["presets"]
        if pid == "new":
            pid = new_id(ps)
        elif pid not in ps:
            raise KeyError(pid)
        for k, p in ps.items():
            if k != pid and p["name"] == name:
                raise Conflict(f"「{name}」은 이미 있습니다")
        ps[pid] = {"name": name, "profileId": prof.ID, "values": values, "updatedAt": _now()}
        save(data)
        return _item(pid, ps[pid])


def delete(pid):
    with _LOCK:
        data = load(strict=True)
        if pid not in data["presets"]:
            raise KeyError(pid)
        del data["presets"][pid]
        save(data)
        return pid
