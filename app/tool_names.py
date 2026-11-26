"""도구 이름 — 사람이 화면에서 고친 도구의 이름(spec_워크플로우 ② §18-19).
2026-11-21 사용자(조립 화면의 카드 「다시 문서 검토」 를 보며) "도구 이름을 바꿀 수 없네?" → 물어서 받은 답 「도구 자체 (모든 워크플로우)」:
**도구(조립에 놓는 줄 — (틀, 줄 key): app/agent_notes.py 의 「도구에 적어 두는 내용」 과 같은 단위)의 이름을 화면에서 고치면 그 도구를 쓰는 모든 워크플로우(붙박이 포함)의 화면에 그 이름으로 보인다.**

- **코드의 이름(등록부 `app/workflow.py` 의 줄 이름 = 기본 이름)은 그대로다** — 이 모듈은 그 위에 얹는 이름만 지닌다. 만든 글(workflow.md · tasks/<job>.md)과 등록부의 설명 글(문장 안에 적힌 이름)은
  기본 이름 그대로다(등록부에서 만든 글은 어느 PC 에서나 같아야 한다 — spec_워크플로우 ② §8).
- 저장 `%LOCALAPPDATA%\\NewFileManager\\tool_names.json`(env `NFM_TOOL_NAMES` 가 파일 경로 · `off`·`0` 이면 메모리만) = `{version, updated, names: {"<틀>.<줄 key>": 이름}}`.
  없는 키 = 기본 이름. 이 PC 의 모든 문서 · 워크플로우가 같이 쓴다. 고친 시각으로 다시 읽는다. 틀 = relay(이관형) · gather(취합형) · single(문서 하나) — 같은 줄 key 도 틀마다 다른 도구다.
- `shown(family, unit, base)` = 화면에 보일 이름(고친 이름 | 기본 이름) · `apply(task, family)` = 등록부의 워크플로우 꼴에 고친 이름을 얹은 **사본**(고친 줄에는 `baseName` = 기본 이름 — 고친 것이 없으면 받은 것 그대로).
  얹는 곳은 화면으로 나가는 문 셋뿐이다: 등록부 응답(`workflow.listing` — `/workflow` · 두 대시보드의 단계 흐름) · 실행 층이 읽는 정의(`workflow_state.definition` — 실행 상태 · 실행 기록의 줄 이름) ·
  조립 응답(`custom_tasks_api` 의 `units[].name` — 카드 · 넣기 고르기 · 「도구 설명」 열).
- **같은 도구 — 틀이 없는 워크플로우의 줄**(2026-11-25 사용자 「도구도 공통내용은 같았으면」): 등록부의 워크플로우가 `twins`({이 줄 key: (틀, 그 틀의 줄 key)} — 양식 작성의 「LLM 검증·보완」 = 이관형의 그 도구)로 적은 줄은
  그 도구의 고친 이름으로 보인다(`twin_names` · `apply` 가 읽는다 — 짝은 등록부 한 곳에만 적는다 · 저장 키는 그 틀의 것 그대로: 따로 저장하지 않는다). 적지 않은 줄은 줄 key 가 같아도 닿지 않는다(기본 이름이 다르면 다른 도구).
- 「사람이 하는 일」(hand)은 도구 이름을 고치지 않는다 — 줄마다 사람이 적는 이름이 따로 있다(조립한 정의의 줄 `name`).

**가벼운 모듈** — 다른 app 코드를 가져오지 않는다(워크플로우 실행 층 · 등록부가 가져다 쓴다). 그 줄이 등록부에 있는지는 부르는 쪽(API)이 본다."""
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

NAME_MAX = 30   # 이름의 길이(카드의 폭 — 「사람이 하는 일」 의 이름과 같다: custom_tasks.HAND_NAME_MAX)
FAMILIES = ("relay", "gather", "single", "collect")   # 틀(가족) — 이관형 · 취합형 · 문서 하나 · 같은 양식 취합(agent_notes.FAMILIES 와 같다)
UNIT = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")   # 줄(단위) key 의 꼴
FIXED = ("hand",)   # 도구 이름을 고치지 않는 줄 — 「사람이 하는 일」(줄마다 이름이 따로 있다)
_BAD = re.compile(r"[「」\x00-\x1f\x7f]")   # 이름에 못 쓰는 글자 — 화면 글이 도구 이름을 「」 로 감싼다 · 줄바꿈 · 제어 문자

_LOCK = threading.RLock()
_MEMORY = {"version": 0, "names": {}}   # 저장 끔일 때
_CACHE = {"path": None, "mtime": None, "data": None}


class Stale(Exception):
    """기대한 판이 지금 판과 다름(그 사이에 다른 곳에서 고침)."""


def path():
    """저장 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_TOOL_NAMES", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "tool_names.json"


def key(family, unit):
    return f"{family}.{unit}"


def _key_ok(k):
    fam, _, unit = k.partition(".") if isinstance(k, str) else ("", "", "")
    return fam in FAMILIES and bool(UNIT.fullmatch(unit)) and unit not in FIXED


def _name_ok(n):
    return isinstance(n, str) and bool(n.strip()) and len(n) <= NAME_MAX and not _BAD.search(n)


def _clean(data):
    data = data if isinstance(data, dict) else {}
    ver = data.get("version")
    return {"version": ver if isinstance(ver, int) and not isinstance(ver, bool) else 0,
            "names": {k: n for k, n in (data["names"].items() if isinstance(data.get("names"), dict) else ()) if _key_ok(k) and _name_ok(n)}}


def load():
    """{version, names: {"<틀>.<줄 key>": 이름}} — 파일이 없거나 깨졌으면 빈 것(깨진 파일은 다음 저장 때 새로 쓴다)."""
    p = path()
    with _LOCK:
        if p is None:
            return _clean(_MEMORY)
        try:
            mt = p.stat().st_mtime_ns
        except OSError:
            _CACHE.update(path=str(p), mtime=None, data=_clean(None))
            return _clean(_CACHE["data"])
        if _CACHE["path"] != str(p) or _CACHE["mtime"] != mt:
            try:
                data = _clean(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                data = _clean(None)
            _CACHE.update(path=str(p), mtime=mt, data=data)
        return _clean(_CACHE["data"])


def names(family):
    """그 틀에서 고친 이름들 → {줄 key: 이름}(없으면 빈 사전). 못 읽어도 빈 사전 — 이름 때문에 화면 · 실행이 멈추지 않는다."""
    try:
        head = family + "."
        return {k[len(head):]: n for k, n in load()["names"].items() if k.startswith(head)} if family in FAMILIES else {}
    except Exception:  # noqa: BLE001
        return {}


def shown(family, unit, base):
    """화면에 보일 이름 — 고친 이름이 있으면 그것, 없으면 기본 이름(base)."""
    return names(family).get(unit) or base


def twin_names(task):
    """그 워크플로우가 「다른 틀의 그 도구와 같은 도구」 라고 적은 줄(등록부의 `twins` {이 줄 key: (틀, 그 틀의 줄 key)} — app/workflow.py: 짝은 거기 한 곳에만 적는다) → {이 줄 key: 그 도구의 고친 이름}(고친 것만).
    틀이 없는 워크플로우(양식 작성)의 줄이 이관형의 도구와 같은 도구일 때 그 도구의 고친 이름이 여기에도 보이게 한다(2026-11-25). 꼴이 틀린 짝 · 못 읽음은 빈 사전 — 이름 때문에 화면이 멈추지 않는다."""
    out = {}
    try:
        for own, pair in ((task or {}).get("twins") or {}).items():
            fam, unit = pair
            n = names(fam).get(unit)
            if n:
                out[own] = n
    except Exception:  # noqa: BLE001
        return {}
    return out


def apply(task, family):
    """등록부의 워크플로우 꼴(stages › steps) → 고친 이름을 얹은 사본. 고친 줄은 `name` = 고친 이름 · `baseName` = 기본 이름(워크플로우의 `base` = 구성의 기준 문서와 다른 키). 고친 것이 없으면 받은 것 그대로(사본을 만들지 않는다).
    줄의 key 로 찾는다 — 「사람이 하는 일」 의 줄(key = hand1 …)은 저장소에 없어 닿지 않는다.
    그 틀(family)의 이름이 먼저이고, 그 워크플로우가 「같은 도구」 라고 적은 줄(`twins` — twin_names)은 그 도구의 고친 이름을 쓴다(틀이 없는 워크플로우도 — 적지 않은 줄은 줄 key 가 같아도 닿지 않는다)."""
    if not task:
        return task
    got = {**twin_names(task), **names(family)}
    if not got:
        return task
    hit, stages = False, []
    for g in task.get("stages") or ():
        steps = []
        for s in g["steps"]:
            n = got.get(s["key"])
            if n and n != s["name"]:
                s, hit = {**s, "name": n, "baseName": s["name"]}, True
            steps.append(s)
        stages.append({**g, "steps": steps})
    return {**task, "stages": stages} if hit else task


def check(name):
    """고칠 이름 → 다듬은 이름("" = 기본 이름으로 되돌림). 글이 아니거나 너무 길거나 못 쓰는 글자가 있으면 ValueError(화면에 그대로 보이는 글)."""
    if name is None:
        return ""
    if not isinstance(name, str):
        raise ValueError("도구 이름은 글이어야 합니다")
    if _BAD.search(name.strip()):
        raise ValueError("도구 이름에 「 」 와 줄바꿈은 쓸 수 없습니다")
    name = " ".join(name.split())
    if len(name) > NAME_MAX:
        raise ValueError(f"도구 이름은 {NAME_MAX}자까지입니다(지금 {len(name)}자)")
    return name


def _write(data):
    data["updated"] = round(time.time(), 3)
    p = path()
    if p is None:
        _MEMORY.clear()
        _MEMORY.update(data)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    _CACHE.update(path=None, mtime=None, data=None)


def save(family, unit, name, base="", expect=None, also=()):
    """도구(틀 family 의 줄 unit)의 이름을 저장한다 → {version, name(고친 이름 | "" = 기본 이름)}. 빈 이름 · 기본 이름(base)과 같은 이름 = 고친 이름을 지움(기본 이름으로).
    also = 같이 고칠 다른 틀들(줄 key 와 기본 이름이 같은 다른 틀의 같은 도구 — 부르는 쪽이 정한다: 한 번에 쓴다).
    expect = 기대 판(다르면 Stale). 꼴이 틀린 틀 · 줄 key · 이름은 ValueError. 그 줄이 등록부에 있는지는 부르는 쪽(API)이 본다."""
    if family not in FAMILIES or any(f not in FAMILIES for f in also) or not (isinstance(unit, str) and UNIT.fullmatch(unit)):
        raise ValueError("도구(틀 · 줄)의 꼴이 아닙니다")
    if unit in FIXED:
        raise ValueError("「사람이 하는 일」 은 줄마다 이름을 적습니다 — 도구 이름은 고치지 않습니다")
    name = check(name)
    if name == base:
        name = ""
    with _LOCK:
        data = load()
        if expect is not None and expect != data["version"]:
            raise Stale(f"도구 이름이 그 사이에 바뀌었습니다(지금 판 {data['version']} · 요청 {expect}) — 다시 읽어 주세요")
        for k in dict.fromkeys(key(f, unit) for f in (family, *also)):
            if name:
                data["names"][k] = name
            else:
                data["names"].pop(k, None)
        data["version"] += 1
        _write(data)
        return {"version": data["version"], "name": name}
