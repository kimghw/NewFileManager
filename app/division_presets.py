"""저장한 구분 기준(spec_구분_기준 ② §8 「저장한 기준」) — FileMergeManager `division_presets.py` 를 NFM 경로·프로파일 계약으로 옮긴 것.
파일 = {"version": 1, "presets": {id: {"name", "profileId", "values", "updatedAt"}}} — %LOCALAPPDATA%\\NewFileManager\\division_presets.json,
env NFM_DIVISION_PRESETS 가 있으면 그것(시험·격리 서버). 값은 프로파일의 norm_values 를 다시 통과(저장은 늘 정리한 꼴 — FMM v1 값 그대로 가져올 수 있다).
통째 원자적 저장(임시 파일 → 바꿔 넣기, 프로세스 안 잠금), 손상 파일은 빈 목록 + .broken 사본. 틀린 이름·값은 ValueError, 같은 이름은 Conflict, 없는 id 는 KeyError."""
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


def _clean(data):
    if not isinstance(data, dict) or not isinstance(data.get("presets", {}), dict):
        raise ValueError("저장한 구분 기준 파일 꼴이 아닙니다")
    out = empty()
    for pid, p in (data.get("presets") or {}).items():
        if not isinstance(pid, str) or not isinstance(p, dict):
            raise ValueError(f"presets.{pid}: 항목이 아님")
        prof = division_profiles.get(p.get("profileId") or "rnd")
        at = p.get("updatedAt")
        out["presets"][pid] = {"name": _name(p.get("name")), "profileId": prof.ID, "values": prof.norm_values(p.get("values")),
                               "updatedAt": at if isinstance(at, str) and at else _now()}
    return out


def load(path=None, strict=False):
    p = Path(path) if path else presets_path()
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return empty()
    except OSError as e:
        if strict:
            raise
        log.warning("저장한 구분 기준 파일을 읽지 못해 빈 목록으로 봅니다: %s (%s)", p, e)
        return empty()
    try:
        return _clean(json.loads(raw.decode("utf-8")))
    except (ValueError, KeyError) as e:
        log.warning("저장한 구분 기준 파일이 손상되어 빈 목록으로 시작합니다(원본은 .broken 으로 보관): %s (%s)", p, e)
        try:
            shutil.copyfile(p, p.with_name(p.name + ".broken"))
        except OSError:
            pass
        return empty()


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
    """pid "new" = 새로(p1·p2…), 있는 id = 덮어씀 -> 저장한 항목. 이름·값이 틀리면 ValueError, 같은 이름은 Conflict, 없는 id 는 KeyError."""
    prof = division_profiles.get(profile_id)
    name, values = _name(name), prof.norm_values(values)
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
