"""조립한 TASK — 사용자가 화면(`/workflow` 의 「TASK 조립」)에서 단계를 골라 만든 TASK(spec_워크플로우 ② §14).

2026-11-19 사용자 "각 단계를 , 여기 모듈로 두고,, task 모듈로 조립할 수 있도록" → "배치를 내가 할 수 없네?" → 답 「새 TASK 만들기」: 일반 단계(문서 검토 · 구성 맞추기 · 내용 넣기 · 문서 정리)를
골라 이름 붙인 TASK 를 화면에서 만든다 — 만든 TASK 는 TASK 카드 · 워크플로우 · 대시보드에 서고, 고른 단계만으로 실행된다.
**가벼운 모듈**(works · server · workflow · job_prompts 가 가져온다 — 다른 app 모듈을 가져오지 않는다).

- 저장 = `%LOCALAPPDATA%\\NewFileManager\\tasks.json`(env `NFM_TASKS` 가 파일 경로 · `off`·`0` 이면 메모리만) =
  `{version, tasks: [{key, name, desc, source, target, assign{source[단계 id…], target[단계 id…], llm[역할…]}, stages[단계 id…], premise, at}]}`.
  이 PC 의 모든 문서가 같이 쓴다. 고친 시각 기준으로 다시 읽는다(다른 프로세스가 고쳐도 다음 호출에 반영).
- **저장 파일 보호**(astra 검토 2026-11-19 — 조용한 소실): 파일이 있는데 못 읽으면(JSON 이 깨짐 · 머리가 사전이 아님 · tasks 가 목록이 아님) 읽기는 빈 목록(`broken()` 이 참)이고
  **쓰지 않는다**(`Refused` — API 409: 다음 쓰기가 파일을 빈 목록으로 덮지 않게). 읽기 오류(다른 프로세스가 바꿔 넣는 중 · 권한 — OSError)는 **그 호출만** 못 읽은 것으로 보고 남기지 않는다
  (다음 호출이 다시 읽는다 — 남기는 것은 읽어서 해석한 결과뿐: 정상 · JSON 이 깨짐). 꼴이 틀린 줄(모르는 문서 쌍 · 고른 단계가 없음 · 겹친 키 · `TASKS_MAX` 뒤 · stages 가 목록이 아닌 옛 줄 …)은
  화면 목록에 안 보이고 **원래 모습 그대로** 남는다 — 쓸 때는 만들거나 고치거나 지운 줄만 바뀌고 그 밖의 줄은 읽은 그대로 쓴다(머리의 모르는 키도).
  고친 줄도 **고친 칸만** 다시 쓴다 — 배정이 그대로인 고치기(이름 · 설명 · 전제만)는 저장된 assign · stages 를 읽은 그대로 둔다(이 판이 모르는 단계 id 도). 지우기는 그 키의 줄을 모두 뺀다
  (보이는 줄 · 같은 키로 숨은 뒤 줄 · 꼴이 틀린 같은 키의 줄 — 지운 키가 다른 내용으로 되살아나지 않게).
- **문서마다 단위문서 TASK**(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 2026-11-19 사용자 "목적문서랑 원본문서에 대해서 각각 task 를 할당할 수 있도록 해줘"):
  `assign` = 문서 역할(원본 · 목적)마다 고른 단계(일반 단계의 차례 — 원본 문서는 「문서 검토」 만: `ROLE_STAGES` — 원본은 그 워크플로우에서 바뀌지 않는다) +
  `llm` = 1단계 「LLM 검증·보완」 을 할 문서 역할(`llm_rule` 이 허락하는 것만 — 「문서 검토」 를 고른 원본 · 「문서 검토」 를 골랐고 「구성 맞추기」 는 안 고른 목적).
  `llm` 은 저장할 때 **역할마다** 정한다: 규칙이 그 역할을 보는 입력(원본 = 「문서 검토」 · 목적 = 「문서 검토」 · 「구성 맞추기」)이 저장된 것과 같으면 그 역할의 저장된 결정을 지키고,
  입력이 바뀐 역할만 규칙(`llm_rule`)으로 다시 센다 — 결과는 늘 규칙의 부분(옛 줄의 「원본만」 에 다른 단계를 더해도 넓어지지 않는다 · 새로 만들 때 보낸 값은 받는다 — 「복제」).
  `sig` = 배정(원본 · 목적 · llm)과 합집합의 짧은 지문 — 단계가 바뀔 때만 바뀐다(화면이 연 뒤 정의가 바뀌었는지 견준다).
  `stages` = 두 역할의 합집합(같이 적는다 — 묶음 id `groups` 와 옛 서버가 그것을 읽는다).
  **옛 줄**(`assign` 없이 `stages` 만 — ② §14 의 꼴)은 버리지 않고 원본 = 「문서 검토」 가 있으면 [문서 검토] · 목적 = stages · llm = 「문서 검토」 가 있으면 [원본] 으로 읽는다(`from_stages` —
  옛 뜻 그대로: 1단계의 LLM 검증·보완은 원본 문서만 · astra P1 ⓐ). **옛 꼴 요청**(assign 없이 stages 만 — 옛 화면)은 합집합이 저장된 것과 같으면 저장된 배정을 그대로 두고, 다르면 옛 줄 규칙으로 읽는다.
- 거절(ValueError — API 400): 원본에 「문서 검토」 밖의 단계(`SOURCE_ONLY`) · 고른 것 없음 · **원본 문서를 쓰는 단계가 없음**(원본이 비었고 목적에 「구성 맞추기」 · 「내용 넣기」 가 없음 — `NO_SOURCE`).
  **쓰는 중인 정의**(그 키를 지금 워크플로우로 둔 작업이 있음 — 부르는 쪽이 `busy` 로 센다: app/custom_tasks_api.py `in_use`)는 실제 배정(원본 · 목적 · llm)을 바꾸지 않는다(`Refused` — API 409 · 「복제」 로 새 정의를) —
  이름 · 설명 · 전제는 고친다. 문서의 워크플로우 목록에만 든 정의는 단계를 고칠 수 있지만 지우지는 못한다(지우기는 부르는 쪽이 둘 다 센다 — `DELETE_IN_USE`).
- **지금 조립할 수 있는 틀 = 이관형 하나**(원본 문서 하나 → 목적 문서 하나) · **문서 쌍 = `PAIRS`**(지금 사업계획서 → 연차보고서 하나):
  문서의 역할을 첨부 파일 종류(plan · report · part)로만 가르고 있어 같은 종류끼리(계획서 → 계획서)는 원본 · 목적을 가를 수 없고, 화면 · 서버의 이관 실행이 두 종류의 이름에 묶여 있다 —
  다른 쌍 · 취합형(원본 여럿)은 그 묶임을 푼 뒤에 더한다(사양 ④).
- 키 = `u_` + 16진 8자(server.TASK["job"] 의 붙박이 키와 겹치지 않는다). 단계는 일반 단계의 차례(`STAGES`)로만 선다 — 고르는 것은 「쓰느냐」 뿐이다.
- 전제(`premise` — 그 TASK 의 LLM 호출이 읽는 글)는 비우면 틀이 같은 붙박이 TASK 의 전제(`BASE` — jobs/plan_to_report.md)를 쓴다(app/job_prompts.py)."""
import hashlib
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
BASE_ROLE = "source"            # 조립한 워크플로우의 구성의 기준 문서 역할(이관형 — 원본: 조립 표의 「구성의 기준」 칸 · app/workflow.py 의 base 는 목적 문서에 「구성 맞추기」 가 있을 때만 이것)
ROLES = ("source", "target")    # 문서 역할 — 원본 문서 · 목적 문서(차례 = 원본 → 목적: app/workflow.py ROLES)
ROLE_STAGES = {"source": ("stage_review",), "target": STAGES}   # 역할마다 고를 수 있는 단계(spec_워크플로우 ② §15) — 원본 문서는 「문서 검토」 만(원본은 바뀌지 않는다)
SOURCE_USE = ("stage_fit", "stage_fill")   # 목적 문서의 단계 가운데 원본 문서를 쓰는 것(구성의 기준 · 내용을 줌) — 원본이 비었으면 이 가운데 하나는 있어야 한다
SOURCE_ONLY = "원본 문서는 이 워크플로우에서 바뀌지 않아 「문서 검토」 만 고를 수 있습니다"   # 원본에 문서 검토 밖의 단계를 고르면(화면에 그대로 보이는 글)
NO_SOURCE = "원본 문서를 쓰는 단계가 없습니다 — 원본 문서의 「문서 검토」 나 목적 문서의 「구성 맞추기」 · 「내용 넣기」 를 고르세요"
BAD_LLM = "LLM 검증·보완을 할 문서의 꼴이 틀립니다"
IN_USE = "이 워크플로우로 하던 작업이 {n}개 있어 단계를 바꿀 수 없습니다 — 「복제」 로 새 워크플로우를 만들어 고치세요"   # 지금 워크플로우로 둔 작업이 있는 정의의 배정을 바꾸려 하면(API PUT 409 · 화면의 editWhy)
DELETE_IN_USE = ("이 워크플로우를 쓰는 작업이 {n}개 있어 지울 수 없습니다 — 지금 워크플로우로 둔 작업은 다른 워크플로우로 바꾸고, "
                 "대시보드 「이 문서의 워크플로우」 목록에서 빼면 지울 수 있습니다")   # n = 지금 워크플로우로 둔 작업 + 목록에만 든 작업(API DELETE 409 · 화면의 deleteWhy)
BROKEN = "저장 파일({name})을 읽지 못해 쓰지 않습니다 — 파일을 고치거나 옮긴 뒤 다시 하세요"   # 못 읽은 파일에 쓰려 하면(API 409)
NAME_MAX, DESC_MAX, PREMISE_MAX, TASKS_MAX = 40, 200, 8000, 50
_FIELDS = ("key", "name", "desc", "source", "target", "assign", "stages", "premise", "at")   # 저장하는 줄의 키(이 밖의 키는 고칠 때도 그대로 둔다)


class Refused(ValueError):
    """쓰지 않음(API 409 — 글은 화면에 그대로) — 저장 파일을 못 읽었거나(BROKEN) · 쓰는 중인 정의의 배정을 바꾸려 함(IN_USE). 그 밖의 ValueError 는 값이 틀림(400)."""


_LOCK = threading.RLock()
_MEMORY = {"version": 0, "tasks": []}   # 메모리만(NFM_TASKS=off) — 파일의 JSON 과 같은 꼴(줄은 원래 모습 그대로)
_CACHE = {"path": None, "mtime": None, "data": None}


def path():
    """저장 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_TASKS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "tasks.json"


def llm_rule(core):
    """원본 · 목적이 고른 단계 → 1단계 「LLM 검증·보완」 을 할 문서 역할(규칙 — 역할 차례): 「문서 검토」 를 고른 원본 · 「문서 검토」 를 골랐고 「구성 맞추기」 는 안 고른 목적
    (구성을 맞추면 목적 문서의 LLM 검증·보완은 구조를 맞춘 뒤 「다시 문서 검토(LLM)」 에서 한다 — app/workflow.py _st_fit). 저장하는 llm 은 늘 이것의 부분이다(`_llm_of`)."""
    return [r for r in ROLES if "stage_review" in core[r] and not (r == "target" and "stage_fit" in core[r])]


def _llm_of(raw, core):
    """llm 값 → 규칙(llm_rule)이 허락하는 역할만(역할 차례) — 넓히지 않는다(「문서 검토」 를 안 고른 문서 · 구조를 맞출 목적 문서의 1단계 LLM 은 없다). 좁히는 것은 된다(옛 줄 — 원본만)."""
    allowed = llm_rule(core)
    return [r for r in ROLES if r in raw and r in allowed]


def from_stages(stages):
    """옛 꼴(단계 하나 목록 — assign 없음: ② §14 의 줄 · 옛 화면의 요청) → assign: 원본 = 「문서 검토」 가 있으면 [문서 검토] · 목적 = 그 단계들(일반 차례) ·
    llm = 「문서 검토」 가 있으면 [원본](옛 뜻 그대로 — 1단계는 두 문서 분석 + 원본 문서의 LLM 검증·보완이었다: 「구성 맞추기」 가 없는 옛 줄도 목적 문서의 1단계 LLM 을 더하지 않는다 · astra P1 ⓐ)."""
    picked = [s for s in STAGES if s in stages]
    review = "stage_review" in picked
    return {"source": ["stage_review"] if review else [], "target": picked, "llm": ["source"] if review else []}


def union(assign):
    """두 역할에서 고른 단계의 합집합(일반 차례) — 저장의 `stages` · 화면의 묶음(groups)."""
    return [s for s in STAGES if any(s in assign[r] for r in ROLES)]


def _same(a, b):
    """두 배정이 실제로 같은가(원본 · 목적 · llm). 이 모듈의 all() 이 내장 all 을 가린다 — 목록끼리 견준다."""
    return [list(a[k]) for k in (*ROLES, "llm")] == [list(b[k]) for k in (*ROLES, "llm")]


def _assign_copy(a):
    return {k: list(a[k]) for k in (*ROLES, "llm")}


def sig(t):
    """정의의 단계 지문 — 정리한 배정(원본 · 목적 · llm)과 합집합 stages 의 sha1 앞 10자. 단계가 바뀔 때만 바뀐다(이름 · 설명 · 전제를 고쳐도 그대로 —
    화면이 연 뒤 정의의 단계가 바뀌었는지 견준다: GET /api/tasks 의 sig)."""
    a = t["assign"]
    return hashlib.sha1(json.dumps([a["source"], a["target"], a["llm"], t["stages"]], separators=(",", ":")).encode("utf-8")).hexdigest()[:10]


def _eun(word):
    """「…」 뒤 조사 「은」 · 「는」 — 끝 글자에 받침이 있으면 「은」(한글 · 숫자로 가린다 — 그 밖의 글자는 「는」)."""
    c = (word or "")[-1:]
    if "가" <= c <= "힣":
        return "은" if (ord(c) - 0xAC00) % 28 else "는"
    return "은" if c and c in "013678" else "는"


def _copy(t):
    """저장된 한 줄의 사본(목록까지 — 돌려받은 값을 고쳐도 저장소 · 캐시는 그대로) · 저장하는 키만(_FIELDS)."""
    return {**{k: t[k] for k in _FIELDS}, "stages": list(t["stages"]), "assign": _assign_copy(t["assign"])}


def _clean_one(t):
    """저장된 한 줄 → 정리한 사전 | None(꼴이 틀림 — 목록에 안 보이고 줄은 원래 모습 그대로 남는다: _parse).
    새 꼴(assign 이 사전) = 역할마다 고를 수 있는 단계만 · llm 이 없으면(2026-11-19 첫 판이 적은 줄) 규칙(llm_rule) / 옛 줄(assign 없이 stages 목록만) = from_stages.
    새 꼴인데 고른 것이 없으면 stages 로 되살리지 않는다(지우려던 배정이 살아난다 — astra 검토)."""
    if not isinstance(t, dict) or not isinstance(t.get("key"), str) or not KEY.fullmatch(t["key"]) or not isinstance(t.get("name"), str) or not t["name"].strip():
        return None
    if (t.get("source"), t.get("target")) not in PAIRS:
        return None
    a = t.get("assign")
    if isinstance(a, dict):
        core = {r: [s for s in ROLE_STAGES[r] if isinstance(a.get(r), list) and s in a[r]] for r in ROLES}   # 역할마다 고를 수 있는 단계만(일반 차례)
        assign = {**core, "llm": _llm_of(a["llm"], core) if isinstance(a.get("llm"), list) else llm_rule(core)}
    elif "assign" in t or not isinstance(t.get("stages"), list):   # assign 이 사전이 아님 · stages 가 목록이 아닌 옛 줄 — 꼴이 틀림(지우지 않고 그대로 둔다)
        return None
    else:
        assign = from_stages(t["stages"])
    stages = union(assign)
    if not stages:
        return None
    return {"key": t["key"], "name": t["name"].strip()[:NAME_MAX], "desc": str(t.get("desc") or "")[:DESC_MAX], "source": t["source"], "target": t["target"], "assign": assign, "stages": stages,
            "premise": str(t.get("premise") or "")[:PREMISE_MAX], "at": t.get("at") if isinstance(t.get("at"), (int, float)) and not isinstance(t.get("at"), bool) else 0}


def _broken():
    return {"version": 0, "rows": [], "tasks": [], "at": [], "extra": {}, "broken": True}


def _parse(obj):
    """파일의 JSON(또는 메모리의 같은 꼴) → {version, rows[줄 — 읽은 그대로], tasks[보이는 줄 — 정리한 것 · 만든 차례], at[그 줄의 rows 자리], extra{머리의 그 밖의 키}, broken}.
    보이는 줄 = 꼴이 맞고(_clean_one) 키가 앞에 안 나왔고 TASKS_MAX 안의 것. 머리가 사전이 아니거나 tasks 가 목록이 아니면 못 읽은 것(broken — 쓰지 않는다)."""
    if not isinstance(obj, dict) or not isinstance(obj.get("tasks", []), list):
        return _broken()
    rows, tasks, at, seen = list(obj.get("tasks", [])), [], [], set()
    for i, row in enumerate(rows):
        c = _clean_one(row)
        if c is None or c["key"] in seen or len(tasks) >= TASKS_MAX:
            continue
        seen.add(c["key"])
        tasks.append(c)
        at.append(i)
    v = obj.get("version")
    return {"version": v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0, "rows": rows, "tasks": tasks, "at": at,
            "extra": {k: x for k, x in obj.items() if k not in ("version", "tasks")}, "broken": False}


def _load():
    p = path()
    if p is None:
        return _parse(_MEMORY)
    try:
        st = p.stat()
        m = (st.st_mtime_ns, st.st_size)   # 크기도 — 같은 시계 눈금 안에 다시 쓴 파일을 옛 읽기로 보지 않게
    except FileNotFoundError:
        return _parse({})
    except OSError:   # 있는지도 모름 — 이 호출만 못 읽은 것으로(덮어쓰지 않는다 · 남기지 않는다)
        return _broken()
    if _CACHE["path"] == str(p) and _CACHE["mtime"] == m and _CACHE["data"] is not None:
        return _CACHE["data"]
    try:
        raw = p.read_bytes()
    except FileNotFoundError:   # 본 사이에 없어짐
        return _parse({})
    except OSError:   # 읽기 오류(다른 프로세스가 바꿔 넣는 중 · 권한) — 이 호출만 못 읽은 것으로(쓰지 않는다). 남기지 않는다: 파일이 그대로여도 다음 호출이 다시 읽는다
        return _broken()
    try:
        data = _parse(json.loads(raw.decode("utf-8")))
    except ValueError:   # JSON 이 깨짐 · 글자 꼴이 틀림 — 읽어서 해석한 결과라 남긴다(파일이 바뀌면 다시 읽는다) · 빈 목록으로 보이되 쓰지 않는다(broken)
        data = _broken()
    _CACHE.update(path=str(p), mtime=m, data=data)
    return data


def broken():
    """저장 파일을 못 읽었나(있는데 JSON · 꼴이 틀림) — 그동안 목록은 비어 보이고 쓰기는 거절한다(API 409 · 화면은 폼 위에 까닭)."""
    with _LOCK:
        return _load()["broken"]


def _writable(data):
    if data["broken"]:
        raise Refused(BROKEN.format(name=(path() or Path("tasks.json")).name))


def writable():
    """쓸 수 있나 — 못 읽은 저장 파일이면 Refused(API 409). 지우기처럼 다른 검사(404 · 쓰는 중)보다 먼저 볼 때."""
    with _LOCK:
        _writable(_load())


def _save(data, rows):
    """줄들을 쓴다(version + 1 · 머리의 다른 키는 그대로) — data = 이 쓰기 앞에 읽은 _load() 의 값. 못 읽은 파일이면 쓰지 않는다(Refused)."""
    _writable(data)
    data = {**data["extra"], "version": data["version"] + 1, "tasks": list(rows)}
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
    """조립한 TASK 들(만든 차례) — 사본(assign · stages 목록까지)."""
    with _LOCK:
        return [_copy(t) for t in _load()["tasks"]]


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


def _llm_kept(core, old):
    """고치는 배정의 llm — 역할마다 따진다: 규칙(llm_rule)이 그 역할에서 보는 입력(원본 = 「문서 검토」 를 골랐나 · 목적 = 「문서 검토」 와 「구성 맞추기」 를 골랐나)이
    저장된 배정(old)과 같은 역할은 저장된 결정(그 역할이 llm 에 있었나)을 지키고, 입력이 바뀐 역할만 규칙으로 다시 센다. 결과는 늘 llm_rule(core) 의 부분 —
    옛 줄 [문서 검토 · 내용 넣기](llm = 원본만)에 목적의 「문서 정리」 를 더해도 목적 문서의 1단계 LLM(유료)이 더해지지 않는다."""
    seen = lambda a, r: ("stage_review" in a[r], r == "target" and "stage_fit" in a[r])  # noqa: E731 — llm_rule 이 그 역할에서 보는 것
    allowed = llm_rule(core)
    return [r for r in ROLES if r in allowed and (r in old["llm"] if seen(core, r) == seen(old, r) else True)]


def _assign_in(body, old):
    """보낸 값의 단계 → assign {source, target, llm}(역할마다 일반 차례). assign 은 한 값이다 — 보낸 assign 에 없는 역할은 고른 것이 없는 것으로 본다.
    - `assign` 이 먼저: 고칠 때(old 있음)는 llm 을 역할마다 따진다(_llm_kept — 입력이 그대로인 역할은 저장된 결정 · 바뀐 역할만 규칙 · 보낸 llm 은 쓰지 않는다).
      새로 만들 때(old 없음)는 보낸 llm 을 받는다(규칙이 허락하는 것만 — 「복제」) · 안 보냈으면 규칙.
    - 없으면 옛 꼴 `stages`(옛 화면): 합집합이 저장된 것과 같으면 저장된 배정 그대로, 다르면(또는 새로 만들 때) 옛 줄 규칙(from_stages).
    - 둘 다 없으면 지금 값(이름 · 설명 · 전제만 고침)."""
    if "assign" in body:
        a = body["assign"]
        if not isinstance(a, dict) or any(not isinstance(a.get(r, []), list) or any(not isinstance(s, str) or s not in STAGES for s in a.get(r, [])) for r in ROLES):
            raise ValueError("단계를 고르세요")
        if any(s not in ROLE_STAGES["source"] for s in a.get("source", [])):
            raise ValueError(SOURCE_ONLY)
        llm = a.get("llm")
        if llm is not None and (not isinstance(llm, list) or any(not isinstance(r, str) or r not in ROLES for r in llm)):
            raise ValueError(BAD_LLM)
        core = {r: [s for s in ROLE_STAGES[r] if s in a.get(r, [])] for r in ROLES}
        if old is not None:
            return {**core, "llm": _llm_kept(core, old["assign"])}   # 원본 · 목적이 그대로면 저장된 llm 그대로(옛 줄의 「원본만」 도) — 바뀐 역할만 다시 센다
        return {**core, "llm": _llm_of(llm, core) if llm is not None else llm_rule(core)}
    if "stages" in body or old is None:
        picked = body.get("stages")
        if not isinstance(picked, list) or any(not isinstance(s, str) or s not in STAGES for s in picked):
            raise ValueError("단계를 고르세요")
        got = from_stages(picked)
        if old is not None and union(got) == union(old["assign"]):   # 옛 화면이 이름만 고쳐 같은 합집합을 보냄 — 문서마다 고른 배정을 펼치지 않는다
            return _assign_copy(old["assign"])
        return got
    return _assign_copy(old["assign"])


def _checked(body, taken, old=None):
    """화면이 보낸 값 → 저장할 값(틀리면 ValueError — 화면에 그대로 보이는 글). taken = 쓸 수 없는 이름들(붙박이 TASK · 다른 조립한 TASK).
    단계는 `assign`(문서 역할마다 — spec_워크플로우 ② §15 「문서마다 단위문서 TASK」) 또는 옛 꼴 `stages`(assign 이 없을 때만)로 받는다 — 저장하는 `stages` 는 늘 두 역할의 합집합.
    배정을 새로 정할 때만(만들 때 · 배정이 바뀔 때) 「하나 이상」 · 「원본 문서를 쓰는 단계」 를 따진다 — 배정이 그대로인 고치기(이름만)는 옛 줄도 받는다."""
    if not isinstance(body, dict):
        raise ValueError("값의 꼴이 틀립니다")
    name = " ".join(str(body.get("name") if "name" in body else (old or {}).get("name") or "").split())
    if not name:
        raise ValueError("워크플로우 이름을 적으세요")
    if len(name) > NAME_MAX:
        raise ValueError(f"워크플로우 이름은 {NAME_MAX}자까지입니다")
    if name in taken:
        raise ValueError(f"「{name}」{_eun(name)} 이미 있는 워크플로우 이름입니다")
    desc = " ".join(str(body.get("desc") if "desc" in body else (old or {}).get("desc") or "").split())[:DESC_MAX]
    source = body.get("source") if "source" in body else (old or {}).get("source") or PAIRS[0][0]
    target = body.get("target") if "target" in body else (old or {}).get("target") or PAIRS[0][1]
    if (source, target) not in PAIRS:
        raise ValueError("지금 조립할 수 있는 문서 쌍은 " + " · ".join(f"{FILES[a]} → {FILES[b]}" for a, b in PAIRS) + " 입니다")
    assign = _assign_in(body, old)
    stages = union(assign)   # 고른 것만 — 차례는 일반 단계의 차례
    if old is None or not _same(assign, old["assign"]):   # 배정을 새로 정함
        if not stages:
            raise ValueError("단계를 하나 이상 고르세요")
        if not assign["source"] and not any(s in assign["target"] for s in SOURCE_USE):
            raise ValueError(NO_SOURCE)
    premise = str(body.get("premise") if "premise" in body else (old or {}).get("premise") or "").strip()
    if len(premise) > PREMISE_MAX:
        raise ValueError(f"전제 글은 {PREMISE_MAX}자까지입니다")
    return {"name": name, "desc": desc, "source": source, "target": target, "assign": assign, "stages": stages, "premise": premise}


def create(body, builtin_names=()):
    """새 조립한 TASK → 그 TASK. builtin_names = 붙박이 TASK 의 이름들(같은 이름을 못 쓰게). 못 읽은 저장 파일이면 Refused(쓰지 않음)."""
    with _LOCK:
        data = _load()
        _writable(data)
        if len(data["tasks"]) >= TASKS_MAX:
            raise ValueError(f"조립한 워크플로우는 {TASKS_MAX}개까지입니다")
        t = _checked(body, set(builtin_names) | {x["name"] for x in data["tasks"]})
        keys = {r.get("key") for r in data["rows"] if isinstance(r, dict)}   # 안 보이는 줄(꼴이 틀림 · 겹침)의 키와도 겹치지 않게
        key = next(k for k in (f"u_{uuid.uuid4().hex[:8]}" for _ in range(100)) if k not in keys)
        t = {"key": key, **t, "at": time.time()}
        _save(data, data["rows"] + [t])
        return _copy(t)


def update(key, body, builtin_names=(), busy=0):
    """조립한 워크플로우 고치기(보낸 키만) → 그 정의(정리한 것) | None(없음). 문서 쌍은 고칠 수 없다(그 정의로 하던 작업의 문서 역할이 달라진다).
    busy = 그 키를 지금 워크플로우로 둔 작업 수(부르는 쪽이 센다 — app/custom_tasks_api.py in_use): 하나라도 있으면 실제 배정(원본 · 목적 · llm)을 바꾸지 않는다(Refused — 「복제」 로 새 정의를).
    **고친 칸만** 다시 쓴다 — 읽은 줄 그대로에 바뀐 이름 · 설명 · 전제만 얹고, 배정이 바뀌었을 때만 assign · stages 를 새로 쓴다(배정이 그대로면 저장된 assign · stages 를
    읽은 그대로 둔다 — 이 판이 모르는 단계 id · 옛 꼴 줄도). 바뀐 것이 없으면 쓰지 않는다. 그 밖의 줄은 읽은 그대로. 못 읽은 저장 파일이면 Refused."""
    with _LOCK:
        data = _load()
        _writable(data)
        i = next((n for n, x in enumerate(data["tasks"]) if x["key"] == key), None)
        if i is None:
            return None
        old = data["tasks"][i]
        if any(k in body and body[k] != old[k] for k in ("source", "target")):
            raise ValueError("문서 쌍은 고칠 수 없습니다 — 새 워크플로우로 만드세요")
        new = _checked(body, set(builtin_names) | {x["name"] for x in data["tasks"] if x["key"] != key}, old)
        moved = not _same(new["assign"], old["assign"])   # 배정(단계)이 바뀜
        if busy and moved:
            raise Refused(IN_USE.format(n=busy))
        at, rows = data["at"][i], list(data["rows"])
        row = {**rows[at], **{k: new[k] for k in ("name", "desc", "premise") if k in body and new[k] != old[k]}}   # 읽은 줄 그대로 + 보내서 바뀐 칸
        if moved:
            row.update(assign=new["assign"], stages=new["stages"])
        if row != rows[at]:
            rows[at] = row
            _save(data, rows)
        return _copy(_clean_one(row))


def delete(key):
    """조립한 워크플로우 지우기 → 지웠나(보이는 줄이 없으면 False). 그 키의 줄을 **모두** 뺀다 — 보이는 줄 · 같은 키로 숨은 뒤 줄 · 꼴이 틀렸지만 key 가 같은 줄
    (보이던 줄만 빼면 숨은 줄이 그 키로 다른 내용이 되어 되살아난다). 그 키로 하던 작업이 있는지는 부르는 쪽이 본다(app/custom_tasks_api.py). 못 읽은 저장 파일이면 Refused."""
    with _LOCK:
        data = _load()
        _writable(data)
        if not any(x["key"] == key for x in data["tasks"]):
            return False
        _save(data, [r for r in data["rows"] if not (isinstance(r, dict) and r.get("key") == key)])
        return True
