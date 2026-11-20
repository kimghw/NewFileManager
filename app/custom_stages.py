"""내가 만든 단계 — 있는 줄(실행 단위)을 골라 이름 붙여 저장해 두는 묶음(spec_워크플로우 ② §18-14 「단계 만들기」).

2026-11-20 사용자(`/workflow` 목차의 「단계」 넷 — 문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리 — 을 보며) "이 단계 만들기도 있어야 하는거 아니냐?". 붙박이 단계 넷은 등록부(app/workflow.py STAGE_MODULES)의 것이고,
여기 것은 사람이 **있는 줄을 골라** 만든 단계다 — 워크플로우 조립(app/custom_tasks.py)의 「＋ 단계 넣기…」 가 그 줄들을 묶음 하나로 넣는다(넣은 뒤에는 그 워크플로우의 줄이다: 단계를 고쳐도 이미 만든 워크플로우는 안 바뀐다).
**줄(새 종류의 일)은 화면에서 만들지 않는다** — 줄은 코드의 실행 단위다(② §18-11).
- 저장 = 조립한 워크플로우의 저장 파일 옆 `<이름>_stages.json`(기본 `%LOCALAPPDATA%\\NewFileManager\\tasks_stages.json` · `NFM_TASKS` 가 임시 파일이면 그 옆 · `off` 면 메모리만) =
  `{version, stages: [{key(s_ + 16진 8자), name(1~20자), desc(200자), steps[{unit, on[역할]} + 사람이 하는 일은 {id, name, note, tool}], at}]}`.
- 검사는 조립과 같은 규칙(custom_tasks.check — 서버 한 곳): 꼴 · 모르는 줄 · 놓을 수 없는 문서 · 같은 문서에 두 번 · 차례가 거꾸로 · 서버가 못 돌리는 줄. 단계는 워크플로우의 한 조각이라
  「원본 문서를 쓰는 줄이 없음」 과 경고(먼저 있어야 할 것을 주는 줄이 정의에 없음 …)는 보지 않는다 — 그것은 조립할 때 워크플로우 전체에서 본다.
- 저장 파일 보호는 custom_tasks 와 같다: 못 읽으면 목록은 비고 쓰지 않는다(`Refused` — API 409) · 꼴이 틀린 줄은 숨기되 읽은 그대로 남긴다 · 원자 쓰기."""
import json
import os
import re
import tempfile
import threading
import time
import uuid

from app import custom_tasks

KEY = re.compile(r"s_[0-9a-f]{8}")
NAME_MAX, DESC_MAX, STAGES_MAX = custom_tasks.GROUP_NAME_MAX, 200, 50
BROKEN = "내가 만든 단계의 저장 파일({name})을 읽지 못해 쓰지 않습니다 — 파일을 고치거나 옮긴 뒤 다시 하세요"
NO_LINES = "줄을 하나 이상 넣으세요"
_LOCK = threading.RLock()
_MEMORY = {"version": 0, "stages": []}


class Refused(ValueError):
    """쓰지 않음(API 409) — 저장 파일을 못 읽음. 그 밖의 ValueError 는 값이 틀림(400 — 글은 화면에 그대로)."""


def path():
    """저장 파일 Path | None(메모리만 — 조립한 워크플로우의 저장이 꺼졌을 때)."""
    p = custom_tasks.path()
    return None if p is None else p.with_name(p.stem + "_stages.json")


def check(raw_steps):
    """단계의 줄 검사 → {errors[], steps(정리한 줄 | None)} — 조립의 검사(custom_tasks.check)에서 단계 하나로 볼 수 있는 것만(머리 글 참고). 글은 화면에 그대로."""
    if not isinstance(raw_steps, list) or not raw_steps:
        return {"errors": [NO_LINES], "steps": None}
    try:
        flow = custom_tasks._flow_in([{"name": "단계", "steps": raw_steps}])
    except ValueError as e:
        return {"errors": [str(e)], "steps": None}
    got = custom_tasks.check("relay", *custom_tasks.PAIRS[0], flow)
    return {"errors": [e for e in got["errors"] if e != custom_tasks.NO_SOURCE_FLOW], "steps": got["flow"][0]["steps"] if got["flow"] else None}


def _clean(row):
    """저장된 줄 하나 → 보이는 꼴 | None(꼴이 틀림 — 숨기되 파일에는 그대로)."""
    if not isinstance(row, dict) or not isinstance(row.get("key"), str) or not KEY.fullmatch(row["key"]) or not isinstance(row.get("name"), str) or not row["name"].strip():
        return None
    try:
        steps = custom_tasks._flow_in([{"name": "단계", "steps": row.get("steps")}])[0]["steps"]
    except ValueError:
        return None
    if not steps:
        return None
    at = row.get("at")
    return {"key": row["key"], "name": " ".join(row["name"].split())[:NAME_MAX], "desc": " ".join(str(row.get("desc") or "").split())[:DESC_MAX], "steps": steps,
            "at": at if isinstance(at, (int, float)) and not isinstance(at, bool) else 0}


def _load():
    p = path()
    if p is None:
        obj = _MEMORY
    else:
        try:
            raw = p.read_bytes()
        except FileNotFoundError:
            obj = {}
        except OSError:
            return {"version": 0, "rows": [], "stages": [], "extra": {}, "broken": True}
        else:
            try:
                obj = json.loads(raw.decode("utf-8"))
            except ValueError:
                return {"version": 0, "rows": [], "stages": [], "extra": {}, "broken": True}
    if not isinstance(obj, dict) or not isinstance(obj.get("stages", []), list):
        return {"version": 0, "rows": [], "stages": [], "extra": {}, "broken": True}
    rows, stages, seen = list(obj.get("stages", [])), [], set()
    for row in rows:
        c = _clean(row)
        if c is None or c["key"] in seen or len(stages) >= STAGES_MAX:
            continue
        seen.add(c["key"])
        stages.append(c)
    v = obj.get("version")
    return {"version": v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0, "rows": rows, "stages": stages,
            "extra": {k: x for k, x in obj.items() if k not in ("version", "stages")}, "broken": False}


def _save(data, rows):
    if data["broken"]:
        raise Refused(BROKEN.format(name=(path().name if path() else "tasks_stages.json")))
    out = {**data["extra"], "version": data["version"] + 1, "stages": list(rows)}
    p = path()
    if p is None:
        _MEMORY.clear()
        _MEMORY.update(out)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def broken():
    with _LOCK:
        return _load()["broken"]


def all():   # noqa: A001 — custom_tasks.all 과 같은 이름
    """내가 만든 단계들(만든 차례) — 사본."""
    with _LOCK:
        return [{**s, "steps": [dict(x) for x in s["steps"]]} for s in _load()["stages"]]


def get(key):
    return next((s for s in all() if s["key"] == key), None) if isinstance(key, str) else None


def _checked(body, taken, old=None):
    if not isinstance(body, dict):
        raise ValueError("값의 꼴이 틀립니다")
    name = " ".join(str(body.get("name") if "name" in body else (old or {}).get("name") or "").split())
    if not name:
        raise ValueError("단계 이름을 적으세요")
    if len(name) > NAME_MAX:
        raise ValueError(f"단계 이름은 {NAME_MAX}자까지입니다")
    if name in taken:
        raise ValueError(f"「{name}」{custom_tasks._eun(name)} 이미 있는 단계 이름입니다")
    desc = " ".join(str(body.get("desc") if "desc" in body else (old or {}).get("desc") or "").split())[:DESC_MAX]
    got = check(body["steps"] if "steps" in body else (old or {}).get("steps"))
    if got["errors"]:
        raise ValueError(got["errors"][0])
    return {"name": name, "desc": desc, "steps": got["steps"]}


def create(body, builtin_names=()):
    """새 단계 → 그 단계. builtin_names = 붙박이 단계의 이름들(같은 이름을 못 쓰게)."""
    with _LOCK:
        data = _load()
        if data["broken"]:
            _save(data, [])
        if len(data["stages"]) >= STAGES_MAX:
            raise ValueError(f"내가 만든 단계는 {STAGES_MAX}개까지입니다")
        s = _checked(body, set(builtin_names) | {x["name"] for x in data["stages"]})
        keys = {r.get("key") for r in data["rows"] if isinstance(r, dict)}
        key = next(k for k in (f"s_{uuid.uuid4().hex[:8]}" for _ in range(100)) if k not in keys)
        row = {"key": key, **s, "at": time.time()}
        _save(data, data["rows"] + [row])
        return _clean(row)


def update(key, body, builtin_names=()):
    """단계 고치기(보낸 키만) → 그 단계 | None(없음). 이미 워크플로우에 넣은 줄은 그 워크플로우의 것이라 안 바뀐다."""
    with _LOCK:
        data = _load()
        if data["broken"]:
            _save(data, [])
        old = next((x for x in data["stages"] if x["key"] == key), None)
        if old is None:
            return None
        s = _checked(body, set(builtin_names) | {x["name"] for x in data["stages"] if x["key"] != key}, old)
        rows = [({**r, **s} if isinstance(r, dict) and r.get("key") == key else r) for r in data["rows"]]
        _save(data, rows)
        return {**old, **s}


def delete(key):
    """단계 지우기 → 지웠나(없으면 False)."""
    with _LOCK:
        data = _load()
        if data["broken"]:
            _save(data, [])
        if not any(x["key"] == key for x in data["stages"]):
            return False
        _save(data, [r for r in data["rows"] if not (isinstance(r, dict) and r.get("key") == key)])
        return True
