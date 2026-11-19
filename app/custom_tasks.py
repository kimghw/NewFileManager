"""조립한 TASK — 사용자가 화면(`/workflow` 의 「TASK 조립」)에서 단계를 골라 만든 TASK(spec_워크플로우 ② §14).

2026-11-19 사용자 "각 단계를 , 여기 모듈로 두고,, task 모듈로 조립할 수 있도록" → "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」: 일반 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를
골라 이름 붙인 TASK 를 화면에서 만든다 — 만든 TASK 는 TASK 카드 · 워크플로우 · 대시보드에 서고, 고른 단계만으로 실행된다.
**가벼운 모듈**(works · server · workflow · job_prompts 가 가져온다 — 다른 app 모듈을 가져오지 않는다).

- 저장 = `%LOCALAPPDATA%\\NewFileManager\\tasks.json`(env `NFM_TASKS` 가 파일 경로 · `off`·`0` 이면 메모리만) = `{version, tasks: [{key, name, desc, source, target, stages[단계 id…], premise, at}]}`.
  이 PC 의 모든 문서가 같이 쓴다. 고친 시각 기준으로 다시 읽는다(다른 프로세스가 고쳐도 다음 호출에 반영).
- **지금 조립할 수 있는 틀 = 이관형 하나**(원본 문서 하나 → 목적 문서 하나) · **문서 쌍 = `PAIRS`**(지금 사업계획서 → 연차보고서 하나):
  문서의 역할을 첨부 파일 종류(plan · report · part)로만 가르고 있어 같은 종류끼리(계획서 → 계획서)는 원본 · 목적을 가를 수 없고, 화면 · 서버의 이관 실행이 두 종류의 이름에 묶여 있다 —
  다른 쌍 · 취합형(원본 여럿)은 그 묶임을 푼 뒤에 더한다(사양 ④).
- 키 = `u_` + 16진 8자(server.TASK["job"] 의 붙박이 키와 겹치지 않는다). 단계는 일반 단계의 차례(`STAGES`)로만 선다 — 고르는 것은 「쓰느냐」 뿐이다.
- 전제(`premise` — 그 TASK 의 LLM 호출이 읽는 글)는 비우면 틀이 같은 붙박이 TASK 의 전제(`BASE` — jobs/plan_to_report.md)를 쓴다(app/job_prompts.py)."""
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

KEY = re.compile(r"u_[0-9a-f]{8}")
STAGES = ("stage_review", "stage_fit", "stage_fill", "stage_clean")   # 일반 단계의 차례 — app/workflow.py STAGE_MODULES 와 같아야 한다(tests/test_custom_tasks.py)
STAGE_GROUP = {"stage_review": "review", "stage_fit": "frame", "stage_fill": "map", "stage_clean": "clean"}   # 단계 → 이관 실행의 묶음 id(화면 app.js TASK_STAGES · 서버 …/merge-links/reset)
FILES = {"plan": "사업계획서", "report": "연차보고서"}   # 문서 종류의 이름(works.FILE_LABEL 과 같게)
PAIRS = (("plan", "report"),)   # 지금 조립할 수 있는 (원본, 목적) 문서 쌍 — 이관 실행이 받는 쌍
BASE = "plan_to_report"         # 틀이 같은 붙박이 TASK — 전제를 비우면 이 TASK 의 전제를 쓴다
NAME_MAX, DESC_MAX, PREMISE_MAX, TASKS_MAX = 40, 200, 8000, 50

_LOCK = threading.RLock()
_MEMORY = {"version": 0, "tasks": []}
_CACHE = {"path": None, "mtime": None, "data": None}


def path():
    """저장 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_TASKS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "tasks.json"


def _clean_one(t):
    """저장된 한 줄 → 정리한 사전 | None(꼴이 틀림 — 그 줄만 버린다)."""
    if not isinstance(t, dict) or not isinstance(t.get("key"), str) or not KEY.fullmatch(t["key"]) or not isinstance(t.get("name"), str) or not t["name"].strip():
        return None
    stages = [s for s in STAGES if s in (t.get("stages") or ())]
    if not stages or (t.get("source"), t.get("target")) not in PAIRS:
        return None
    return {"key": t["key"], "name": t["name"].strip()[:NAME_MAX], "desc": str(t.get("desc") or "")[:DESC_MAX], "source": t["source"], "target": t["target"], "stages": stages,
            "premise": str(t.get("premise") or "")[:PREMISE_MAX], "at": t.get("at") if isinstance(t.get("at"), (int, float)) else 0}


def _clean(data):
    tasks = data.get("tasks") if isinstance(data, dict) else None
    out, seen = [], set()
    for t in tasks if isinstance(tasks, list) else ():
        c = _clean_one(t)
        if c and c["key"] not in seen:
            seen.add(c["key"])
            out.append(c)
    v = data.get("version") if isinstance(data, dict) else 0
    return {"version": v if isinstance(v, int) and v >= 0 else 0, "tasks": out[:TASKS_MAX]}


def _load():
    p = path()
    if p is None:
        return _MEMORY
    try:
        m = p.stat().st_mtime_ns
    except OSError:
        return {"version": 0, "tasks": []}
    if _CACHE["path"] == str(p) and _CACHE["mtime"] == m and _CACHE["data"] is not None:
        return _CACHE["data"]
    try:
        data = _clean(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        data = {"version": 0, "tasks": []}
    _CACHE.update(path=str(p), mtime=m, data=data)
    return data


def _save(data):
    data = {"version": data["version"] + 1, "tasks": data["tasks"]}
    p = path()
    if p is None:
        _MEMORY.clear()
        _MEMORY.update(data)
        return data
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _CACHE.update(path=None, mtime=None, data=None)
    return data


def all():   # noqa: A001 — 모듈 안의 이름(custom_tasks.all())
    """조립한 TASK 들(만든 차례) — 사본."""
    with _LOCK:
        return [dict(t, stages=list(t["stages"])) for t in _load()["tasks"]]


def get(key):
    """키 → 조립한 TASK | None."""
    if not isinstance(key, str) or not KEY.fullmatch(key):
        return None
    return next((t for t in all() if t["key"] == key), None)


def is_key(job):
    """그 할 일 키가 조립한 TASK 인가(저장소에 있는 것만)."""
    return get(job) is not None


def source_file(job):
    """그 TASK 의 원본 문서 종류 — 조립한 TASK 는 제 것, 그 밖(붙박이 이관)은 사업계획서."""
    t = get(job)
    return t["source"] if t else "plan"


def target_file(job):
    """조립한 TASK 의 목적 문서 종류 | None(조립한 TASK 가 아님 — 붙박이는 works.TARGET_FILE)."""
    t = get(job)
    return t["target"] if t else None


def _checked(body, taken, old=None):
    """화면이 보낸 값 → 저장할 값(틀리면 ValueError — 화면에 그대로 보이는 글). taken = 쓸 수 없는 이름들(붙박이 TASK · 다른 조립한 TASK)."""
    if not isinstance(body, dict):
        raise ValueError("값의 꼴이 틀립니다")
    name = " ".join(str(body.get("name") if "name" in body else (old or {}).get("name") or "").split())
    if not name:
        raise ValueError("TASK 이름을 적으세요")
    if len(name) > NAME_MAX:
        raise ValueError(f"TASK 이름은 {NAME_MAX}자까지입니다")
    if name in taken:
        raise ValueError(f"「{name}」 은 이미 있는 TASK 이름입니다")
    desc = " ".join(str(body.get("desc") if "desc" in body else (old or {}).get("desc") or "").split())[:DESC_MAX]
    source = body.get("source") if "source" in body else (old or {}).get("source") or PAIRS[0][0]
    target = body.get("target") if "target" in body else (old or {}).get("target") or PAIRS[0][1]
    if (source, target) not in PAIRS:
        raise ValueError("지금 조립할 수 있는 문서 쌍은 " + " · ".join(f"{FILES[a]} → {FILES[b]}" for a, b in PAIRS) + " 입니다")
    picked = body.get("stages") if "stages" in body else (old or {}).get("stages")
    if not isinstance(picked, list) or any(s not in STAGES for s in picked):
        raise ValueError("단계를 고르세요")
    stages = [s for s in STAGES if s in picked]   # 고른 것만 — 차례는 일반 단계의 차례
    if not stages:
        raise ValueError("단계를 하나 이상 고르세요")
    premise = str(body.get("premise") if "premise" in body else (old or {}).get("premise") or "").strip()
    if len(premise) > PREMISE_MAX:
        raise ValueError(f"전제 글은 {PREMISE_MAX}자까지입니다")
    return {"name": name, "desc": desc, "source": source, "target": target, "stages": stages, "premise": premise}


def create(body, builtin_names=()):
    """새 조립한 TASK → 그 TASK. builtin_names = 붙박이 TASK 의 이름들(같은 이름을 못 쓰게)."""
    with _LOCK:
        data = _load()
        if len(data["tasks"]) >= TASKS_MAX:
            raise ValueError(f"조립한 TASK 는 {TASKS_MAX}개까지입니다")
        t = _checked(body, set(builtin_names) | {x["name"] for x in data["tasks"]})
        keys = {x["key"] for x in data["tasks"]}
        key = next(k for k in (f"u_{uuid.uuid4().hex[:8]}" for _ in range(100)) if k not in keys)
        t = {"key": key, **t, "at": time.time()}
        _save({"version": data["version"], "tasks": data["tasks"] + [t]})
        return dict(t)


def update(key, body, builtin_names=()):
    """조립한 TASK 고치기(보낸 키만) → 그 TASK | None(없음). 문서 쌍은 고칠 수 없다(그 TASK 로 하던 작업의 문서 역할이 달라진다)."""
    with _LOCK:
        data = _load()
        old = next((x for x in data["tasks"] if x["key"] == key), None)
        if old is None:
            return None
        if any(k in body and body[k] != old[k] for k in ("source", "target")):
            raise ValueError("문서 쌍은 고칠 수 없습니다 — 새 TASK 로 만드세요")
        t = {**old, **_checked(body, set(builtin_names) | {x["name"] for x in data["tasks"] if x["key"] != key}, old)}
        _save({"version": data["version"], "tasks": [t if x["key"] == key else x for x in data["tasks"]]})
        return dict(t)


def delete(key):
    """조립한 TASK 지우기 → 지웠나. 그 TASK 로 하던 작업이 있는지는 부르는 쪽이 본다(app/custom_tasks_api.py)."""
    with _LOCK:
        data = _load()
        if not any(x["key"] == key for x in data["tasks"]):
            return False
        _save({"version": data["version"], "tasks": [x for x in data["tasks"] if x["key"] != key]})
        return True
