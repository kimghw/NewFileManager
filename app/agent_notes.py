"""도구 · 에이전트에 적어 두는 내용(덧붙이는 글) — 「도구 공통」 · 「이 워크플로우 전용」 (spec_에이전트 ② §6 · 화면 spec_워크플로우 ② §18-16).
2026-11-20 사용자 "각각의 단계에서 사용하는 에이전트의 스킬/도구/프롬프트는 클릭해서 여기서 보고 수정할 수 있게 해줘,, 다만 그건 범용일 수도 있고 현재 이 워크플로우 전용일 수 있으니 구분해서 작성할 수 있게 해줘" ·
같은 날 "공통적으로 그 도구에서는 는 내용과 워크플로우마다 사용되는 애용 2가지. 예로 구성맞추기 할때.. 사업계획서랑 다른 문서랑 제공해야 하는 정보가 다르잖아":
**단위는 도구(조립에 놓는 줄 — (틀, 줄 key))다.** 도구마다 글 둘 — ① 그 도구에서 공통으로 쓰는 내용(그 도구를 쓰는 모든 워크플로우) ② 워크플로우마다 쓰는 내용(그 워크플로우에서 그 도구에만).
에이전트마다의 글(그 에이전트에만 — 모든 워크플로우 · 한 워크플로우)은 그 아래의 더 좁은 층으로 남는다.

**가벼운 모듈** — `app/llm.py` 가 부를 때마다 읽으므로 모듈을 읽을 때 다른 app 코드는 `agent_settings`(가벼운 모듈)만 가져온다(작업 · 워크플로우 · 등록부는 쓸 때 함수 안에서).

- 저장 `%LOCALAPPDATA%\\NewFileManager\\agent_notes.json`(env `NFM_AGENT_NOTES` 가 파일 경로 · `off`·`0` 이면 메모리만) =
  `{version, updated, tools: {"<틀>.<줄 key>": 글}, jobTools: {워크플로우 키: {줄 key: 글}}, all: {에이전트 id: 글}, jobs: {워크플로우 키: {에이전트 id: 글}}}`.
  없는 키 = 글 없음. 이 PC 의 모든 문서가 같이 쓴다. 고친 시각으로 다시 읽는다. 틀 = relay(이관형) · gather(취합형) · single(문서 하나) — 같은 줄 key 도 틀마다 다른 도구다.
- `tool_map()` = 틀마다 줄 key → {name, agents[에이전트 id…], tools[{id, name}]} — 워크플로우 등록부의 그 줄에서(따로 적는 표가 없다).
- `part(aid, job, family, unit)` = 그 에이전트의 프롬프트 **맨 끝**(자료 뒤)에 붙는 절 글 | "" — 넓은 것부터: 에이전트(모든 워크플로우) → 도구 공통 → 도구 · 이 워크플로우 → 에이전트 · 이 워크플로우.
  unit 을 알면(서버 실행기가 그 줄을 도는 중) 그 도구의 글만, 모르면(문서 화면에서 손으로 돌림) 그 틀에서 그 에이전트를 쓰는 도구들의 글. 계약(답의 꼴 · 입력에 있는 key 만)은 바꾸지 못한다고 머리 문장이 적는다.
- **같은 도구 — 틀이 없는 워크플로우의 줄**(2026-11-25 사용자 「도구도 공통내용은 같았으면」): 등록부의 워크플로우가 `twins`({이 줄 key: (틀, 그 틀의 줄 key)} — 양식 작성의 「LLM 검증·보완」 = 이관형의 그 도구)로 적은 줄은
  그 도구의 **「도구 공통」 글**이 그 워크플로우에서도 붙는다(`twins(job)` → `_part` — 그 도구가 부르는 에이전트에만: 그 줄에만 있는 에이전트(writing_guidance)에는 안 붙는다 · 작업 진행 에이전트의 요약 `digest` 에도).
  짝은 등록부 한 곳에만 적는다 · 저장 키는 그 틀의 것 그대로다(이 워크플로우 전용 칸은 없다 — 틀이 없는 워크플로우에는 조립 화면이 없다).
- `attach(content, what)` = `llm.call` 의 훅 — 호출 이름(what)으로 에이전트를 찾아 `part` 를 붙인다 → (글, 붙인 것의 꼬리표 목록 | None). 작업 진행 에이전트(work_guide)에는 그 워크플로우의 **도구마다 적어 둔 내용의 요약**을 붙인다
  (에이전트 없이 스크립트 · 사람이 하는 도구에 적은 내용을 읽는 곳 — 그 단계를 안내 · 제안할 때). 어떤 오류도 호출을 막지 않는다(못 읽으면 붙이지 않는다).
- **지금 워크플로우 · 지금 도구**는 맥락 변수다: `scope(job=…)` · `scope(work=…)`(작업 id 만 아는 곳 — 요청 주소의 문서: 부를 때 그 작업의 `task.job` 을 읽는다) · `job_now()` /
  지금 도는 줄 = 서버 실행기가 건 `workflow_state.LINE`((틀, 줄 key) — 이 모듈은 읽기만).
  **새 스레드는 맥락을 물려받지 않는다** — LLM 호출로 이어지는 스레드 · 실행기를 만드는 곳은 `carry(fn)`(지금 맥락을 들고 가는 함수)로 감싼다(`llm.ask_all` · 헤딩 실행 · 분석 LLM · 구분 기준 검토 · 검증 · 워크플로우 실행기는 표준 contextvars).
  물려받지 못한 호출에는 에이전트의 범용 글만 붙는다(실행 기록의 `notes` 로 보인다)."""
import contextlib
import contextvars
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from app import agent_settings

TEXT_MAX = 4000   # 글 하나(도구 · 에이전트 · 범위마다)의 길이
DIGEST_MAX = 700  # 작업 진행 에이전트에 붙이는 요약에서 글 하나의 길이(넘으면 줄인다)
JOB = re.compile(r"[a-z][a-z0-9_]{0,39}")   # 워크플로우 키의 꼴(붙박이 · 조립한 것 u_xxxxxxxx — job_prompts.KEY 와 같다)
UNIT = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")   # 줄(단위) key 의 꼴
FAMILIES = ("relay", "gather", "single", "collect")   # 틀(가족) — 이관형 · 취합형 · 문서 하나 · 같은 양식 취합(spec_취합 ② §10 — 이관형과 줄 key · 기본 이름이 같은 줄은 같은 도구다: tool_names_api 가 이름을 같이 고친다)
GUIDE = "work_guide"   # 작업 진행 에이전트 — 도구마다 적어 둔 내용의 요약을 읽는다
HEAD = ("## 덧붙이는 지침 — 사용자가 이 일에 따로 적어 둔 글\n"
        "아래는 위 자료의 일부가 아니라, 사용자가 이 검토 · 작업에 덧붙여 둔 지침입니다. 위의 지침 · 판단 기준과 어긋나면 이 글을 따릅니다. "
        "다만 답의 꼴과 「입력에 있는 key · id 가운데서만 고른다」 같은 계약의 규칙은 그대로 지킵니다(이 글로 바뀌지 않습니다).")
ALL_HEAD = "### 모든 워크플로우에서"
TOOL_HEAD = "### 도구 「{tool}」 — 이 도구를 쓰는 모든 워크플로우에서"
JOB_TOOL_HEAD = "### 도구 「{tool}」 — 이 워크플로우({name})에서만 — 위의 글과 어긋나면 이 글이 먼저입니다"
JOB_HEAD = "### 이 워크플로우({name})에서만 — 위 「모든 워크플로우에서」 와 어긋나면 이 글이 먼저입니다"
GUIDE_HEAD = ("## 도구마다 사용자가 적어 둔 내용 — 이 워크플로우({name})\n"
              "아래는 사용자가 이 워크플로우의 도구(단계 줄)마다 적어 둔 내용입니다 — 그 도구에 무엇을 주어야 하는지 · 무엇을 지켜야 하는지. 그 단계를 설명 · 제안하거나 필요한 것을 물을 때 이 내용을 따릅니다. "
              "「공통」 = 그 도구를 쓰는 모든 워크플로우 · 「이 워크플로우」 = 이 워크플로우에서만(어긋나면 이쪽이 먼저). 고를 수 있는 행동과 답의 꼴은 위 계약 그대로입니다.")

_EMPTY = {"version": 0, "tools": {}, "jobTools": {}, "all": {}, "jobs": {}}
_LOCK = threading.RLock()
_MEMORY = json.loads(json.dumps(_EMPTY))   # 저장 끔일 때
_CACHE = {"path": None, "mtime": None, "data": None}
_SCOPE = contextvars.ContextVar("nfm_agent_scope", default=None)   # None | ("job", 워크플로우 키) | ("work", 작업 id)
_TOOLS = []   # [tool_map() 의 값] — 등록부는 프로세스가 사는 동안 그대로다(한 번만 짓는다)


class Stale(Exception):
    """기대한 판이 지금 판과 다름(그 사이에 다른 곳에서 고침)."""


def path():
    """저장 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_AGENT_NOTES", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "agent_notes.json"


def _ok(t):
    return isinstance(t, str) and bool(t.strip()) and len(t) <= TEXT_MAX


def _texts(box):
    return {a: t for a, t in (box.items() if isinstance(box, dict) else ()) if a in agent_settings.IDS and _ok(t)}


def tool_key(family, unit):
    return f"{family}.{unit}"


def _tool_ok(key):
    fam, _, unit = key.partition(".") if isinstance(key, str) else ("", "", "")
    return fam in FAMILIES and bool(UNIT.fullmatch(unit))


def _clean(data):
    data = data if isinstance(data, dict) else {}
    jobs, job_tools = {}, {}
    for job, box in (data["jobs"].items() if isinstance(data.get("jobs"), dict) else ()):
        if isinstance(job, str) and JOB.fullmatch(job) and _texts(box):
            jobs[job] = _texts(box)
    for job, box in (data["jobTools"].items() if isinstance(data.get("jobTools"), dict) else ()):
        got = {u: t for u, t in (box.items() if isinstance(box, dict) else ()) if isinstance(u, str) and UNIT.fullmatch(u) and _ok(t)}
        if isinstance(job, str) and JOB.fullmatch(job) and got:
            job_tools[job] = got
    tools = {k: t for k, t in (data["tools"].items() if isinstance(data.get("tools"), dict) else ()) if _tool_ok(k) and _ok(t)}
    ver = data.get("version")
    return {"version": ver if isinstance(ver, int) and not isinstance(ver, bool) else 0, "tools": tools, "jobTools": job_tools, "all": _texts(data.get("all")), "jobs": jobs}


def load():
    """{version, tools: {"<틀>.<줄 key>": 글}, jobTools: {워크플로우 키: {줄 key: 글}}, all: {에이전트 id: 글}, jobs: {워크플로우 키: {에이전트 id: 글}}} —
    파일이 없거나 깨졌으면 빈 것(깨진 파일은 다음 저장 때 새로 쓴다)."""
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


def get(aid, job=None):
    """그 에이전트에만 덧붙이는 글 — job 이 없으면 모든 워크플로우, 있으면 그 워크플로우 전용. 없으면 ""."""
    data = load()
    return (data["jobs"].get(job) or {}).get(aid, "") if job else data["all"].get(aid, "")


def get_tool(family, unit, job=None):
    """그 도구에 적어 둔 내용 — job 이 없으면 도구 공통, 있으면 그 워크플로우 전용. 없으면 ""."""
    data = load()
    return (data["jobTools"].get(job) or {}).get(unit, "") if job else data["tools"].get(tool_key(family, unit), "")


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


def check(text):
    """적어 두는 글 → 다듬은 글("" = 지움). 글이 아니거나 너무 길면 ValueError."""
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ValueError("덧붙이는 글은 글이어야 합니다")
    text = re.sub(r"[ \t]+\n", "\n", text.replace("\r\n", "\n")).strip()
    if len(text) > TEXT_MAX:
        raise ValueError(f"덧붙이는 글은 {TEXT_MAX:,}자 이하(지금 {len(text):,}자)")
    return text


def _job_arg(job):
    if job is not None and not (isinstance(job, str) and JOB.fullmatch(job)):
        raise ValueError("워크플로우 키의 꼴이 아닙니다")


def _put(top, job_top, key, text, job, expect):
    """글 하나를 넣거나 지운다 — top = 워크플로우와 무관한 칸의 이름 · job_top = 워크플로우마다의 칸의 이름."""
    with _LOCK:
        data = load()
        if expect is not None and expect != data["version"]:
            raise Stale(f"덧붙이는 글이 그 사이에 바뀌었습니다(지금 판 {data['version']} · 요청 {expect}) — 다시 읽어 주세요")
        box = data[job_top].setdefault(job, {}) if job else data[top]
        if text:
            box[key] = text
        else:
            box.pop(key, None)
        if job and not box:
            data[job_top].pop(job, None)
        data["version"] += 1
        _write(data)
        return {"version": data["version"], "text": text}


def save(aid, text, job=None, expect=None):
    """에이전트 aid 에만 덧붙이는 글을 저장한다(빈 글 = 지움) — job 이 없으면 모든 워크플로우, 있으면 그 워크플로우 전용 → {version, text}.
    expect = 기대 판(다르면 Stale). 없는 에이전트는 KeyError · 꼴이 틀린 글 · 키는 ValueError. job 이 실제로 있는 워크플로우인지는 부르는 쪽(API)이 본다."""
    if aid not in agent_settings.IDS:
        raise KeyError(aid)
    _job_arg(job)
    return _put("all", "jobs", aid, check(text), job, expect)


def save_tool(family, unit, text, job=None, expect=None):
    """도구(틀 family 의 줄 unit)에 적어 두는 내용을 저장한다(빈 글 = 지움) — job 이 없으면 도구 공통(그 도구를 쓰는 모든 워크플로우), 있으면 그 워크플로우 전용 → {version, text}.
    꼴이 틀린 틀 · 줄 key · 글 · 키는 ValueError. 그 줄이 등록부에 있는지 · job 이 그 틀의 워크플로우인지는 부르는 쪽(API)이 본다."""
    if family not in FAMILIES or not (isinstance(unit, str) and UNIT.fullmatch(unit)):
        raise ValueError("도구(틀 · 줄)의 꼴이 아닙니다")
    _job_arg(job)
    return _put("tools", "jobTools", unit if job else tool_key(family, unit), check(text), job, expect)


def forget_job(job):
    """그 워크플로우의 전용 글(도구 · 에이전트)을 모두 지운다(조립한 워크플로우를 지울 때 — 지운 키의 글이 남지 않게) → 지운 글 수. 어떤 오류도 내지 않는다."""
    try:
        with _LOCK:
            data = load()
            gone = len(data["jobs"].pop(job, None) or {}) + len(data["jobTools"].pop(job, None) or {})
            if gone:
                data["version"] += 1
                _write(data)
            return gone
    except Exception:  # noqa: BLE001 — 워크플로우 지우기를 막지 않는다
        return 0


# ---------------------------------------------------------------- 도구 → 에이전트(등록부에서)
def tool_map():
    """틀(가족)마다 줄 key → {name, agents[에이전트 id…], tools[{id, name}]} — 등록부의 그 줄이 적은 이름 · 에이전트(`agents`) · 쓰는 도구(`uses` — COMMON 의 id → 이름).
    조립에 놓는 줄의 글 · 이름과 같은 곳에서 읽는다(이관형 = 일반 단계 · 취합형 = 사업계획서 취합 · 문서 하나 = 양식 표준화 + 양식 맞추기). 한 번만 짓는다."""
    if _TOOLS:
        return _TOOLS[0]
    from app import custom_tasks, workflow
    tool = {c["id"]: c["name"] for c in workflow.COMMON}

    def row(s):
        return {"name": s["name"], "agents": list(s["agents"]), "tools": [{"id": i, "name": tool.get(i, i)} for i in s["uses"]]}

    def of_jobs(*jobs):
        out = {}
        for job in jobs:
            for g in workflow.BY_JOB[job]["stages"]:
                for s in g["steps"]:
                    out.setdefault(s["key"], row(s))
        return out

    relay = {}
    for mid, _name, make, _does in workflow.STAGE_MODULES:
        for s in make(*workflow._GENERIC, **({"llm": ("source", "target")} if mid == "stage_review" else {"take": True} if mid == "stage_fit" else {"more": True} if mid == "stage_clean" else {})):   # 일반 단계가 만드는 줄 모두(LLM 검증·보완은 두 문서 모두 고른 꼴에서 · 조립에 놓는 도구 「넣을 구성 선택」 · 「지침 보정(LLM)」 · 「빈 구역 지우기」 까지)
            relay.setdefault(s["key"], row(s))
    gather = of_jobs("plan_merge")
    for s in workflow.gather_tools():   # 취합형 조립에만 놓는 도구(붙박이 차례에 없다 — 「넣은 뒤 템플릿 · 서식 정리」: spec_병합 ② §5-9 9)
        gather.setdefault(s["key"], row(s))
    collect = {s["key"]: row(s) for s in workflow.collect_tools()}   # 같은 양식 취합의 줄(붙박이가 없다 — 조립에만 놓는 줄: workflow.collect_tools)
    _TOOLS.append({"relay": relay, "gather": gather, "single": of_jobs(*dict.fromkeys(custom_tasks.SINGLE_BASE.values())), "collect": collect})
    return _TOOLS[0]


def family_of(job):
    """워크플로우 키 → (틀, 그 정의의 줄 key 들(차례대로 · 겹치지 않게)) | ("", ()) — 모르는 키 · 틀이 없는 워크플로우(일반 편집 · 서식 복사)."""
    try:
        from app import workflow_state as S
        task = S.definition(job) if job else None
        fam = S.family(task) if task else ""
        if fam not in FAMILIES:
            return "", ()
        return fam, tuple(dict.fromkeys(s["key"] for g in task.get("stages") or () for s in g["steps"]))
    except Exception:  # noqa: BLE001 — 정의를 못 읽어도 호출은 돈다
        return "", ()


def twins(job):
    """그 워크플로우가 「다른 틀의 그 도구와 같은 도구」 라고 적은 줄 → [(이 줄 key, 틀, 그 틀의 줄 key)] — 등록부의 그 워크플로우 `twins`(app/workflow.py: 짝은 거기 한 곳에만 적는다 · 도구 이름도 같은 표를 읽는다 — tool_names.twin_names).
    2026-11-25 사용자 「도구도 공통내용은 같았으면」: 틀이 없는 워크플로우(양식 작성)의 줄이 이관형의 도구와 같은 엔진을 부를 때, 그 도구의 「도구 공통」 글이 여기서도 붙게 한다(_part · digest).
    등록부에 그 틀 · 그 줄이 없는 짝은 뺀다. 모르는 키 · 못 읽음은 빈 목록(호출은 돈다)."""
    try:
        from app import workflow
        t = workflow.task_of(job) if job else None
        rows, out = tool_map(), []
        for own, pair in ((t or {}).get("twins") or {}).items():
            fam, unit = pair
            if fam in FAMILIES and unit in rows.get(fam, {}):
                out.append((own, fam, unit))
        return out
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------- 지금 워크플로우 · 지금 도구 — 맥락 변수
@contextlib.contextmanager
def scope(job=None, work=None):
    """이 안에서 부르는 LLM 호출의 워크플로우를 정한다 — job(워크플로우 키를 아는 곳) | work(작업 id 만 아는 곳: 부를 때 그 작업의 task.job 을 읽는다). 둘 다 없으면 「모름」 으로."""
    token = _SCOPE.set(("job", job) if job else ("work", work) if work else None)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def job_now():
    """지금 맥락의 워크플로우 키 | None(모름 — 에이전트의 범용 글만 붙는다). 작업 id 로 정한 맥락은 여기서 그 작업의 지금 워크플로우를 읽는다(못 읽으면 None)."""
    s = _SCOPE.get()
    if not s:
        return None
    kind, v = s
    if kind == "job":
        return v if isinstance(v, str) and JOB.fullmatch(v) else None
    try:
        from app import works   # 쓸 때만(이 모듈은 가볍게)
        job = ((works.work(v) or {}).get("task") or {}).get("job")
        return job if isinstance(job, str) and JOB.fullmatch(job) else None
    except Exception:  # noqa: BLE001 — 작업을 못 읽어도 호출은 돈다
        return None


def line_now():
    """서버 실행기가 지금 도는 줄 → (틀, 줄 key) | None(실행기 밖 — 문서 화면에서 손으로 돌림 · 맥락을 못 받은 스레드)."""
    try:
        from app import workflow_state
        got = workflow_state.LINE.get()
        return (got[0], got[1]) if got and got[0] in FAMILIES and isinstance(got[1], str) else None
    except Exception:  # noqa: BLE001
        return None


def carry(fn):
    """지금 맥락(워크플로우 · 도는 줄)을 들고 가는 함수 — 새 스레드 · 실행기에 넘길 함수를 이것으로 감싼다(새 스레드는 맥락을 물려받지 않는다).
    부를 때마다 잡아 둔 맥락의 사본에서 돈다(같은 함수를 여러 스레드가 함께 불러도 된다)."""
    ctx = contextvars.copy_context()

    def run(*args, **kwargs):
        return ctx.copy().run(fn, *args, **kwargs)
    return run


def scoped(fn, job):
    """`carry` 와 같되 워크플로우를 job 으로 정해서 — 워크플로우를 아는 곳이 스레드를 띄울 때."""
    def run(*args, **kwargs):
        with scope(job=job):
            return fn(*args, **kwargs)
    return carry(run)


# ---------------------------------------------------------------- 프롬프트에 붙이기
def _job_name(job):
    try:
        from app import custom_tasks   # 가벼운 모듈
        c = custom_tasks.get(job)
        if c is not None:
            return c["name"]
        from app import workflow
        return (workflow.catalog()[0].get(job) or {}).get("name") or job
    except Exception:  # noqa: BLE001
        return job


def part(aid, job=None, family=None, unit=None):
    """그 에이전트의 프롬프트 맨 끝에 붙는 절 글 | ""(적어 둔 글 없음 — 프롬프트는 전과 같다). job = 지금 워크플로우 · family = 그 틀 · unit = 지금 도는 줄(모르면 그 틀에서 이 에이전트를 쓰는 도구들)."""
    return _part(aid, job, family, unit)[0]


def _part(aid, job, family=None, unit=None):
    if not aid:
        return "", []
    data = load()
    secs, tags = [], []
    every = data["all"].get(aid, "")
    if every:
        secs.append(f"{ALL_HEAD}\n{every}")
        tags.append("all")
    mine_tools = data["jobTools"].get(job) or {} if job else {}
    if family in FAMILIES and (data["tools"] or mine_tools):   # 도구에 적어 둔 내용 — 도는 줄을 알면 그 도구만 · 모르면 그 틀에서 이 에이전트를 쓰는 도구들(등록부의 차례)
        rows = tool_map().get(family, {})
        units = [unit] if unit else [k for k, r in rows.items() if aid in r["agents"]]
        name = None
        for u in units:
            common, own = data["tools"].get(tool_key(family, u), ""), mine_tools.get(u, "")
            tool = (rows.get(u) or {}).get("name") or u
            if common:
                secs.append(f"{TOOL_HEAD.format(tool=tool)}\n{common}")
                tags.append(f"tool:{tool_key(family, u)}")
            if own:
                name = name or _job_name(job)
                secs.append(f"{JOB_TOOL_HEAD.format(tool=tool, name=name)}\n{own}")
                tags.append(f"jobtool:{job}/{u}")
    if job and data["tools"]:   # 같은 도구(등록부의 twins) — 이 워크플로우의 줄이 다른 틀의 그 도구와 같은 도구면 그 도구의 「도구 공통」 글도(그 도구가 부르는 에이전트에만 · 도는 줄을 알면 그 줄의 짝만 · 이미 붙였으면 다시 안 붙인다)
        for mine_key, fam, u in twins(job):
            row, tag = tool_map().get(fam, {}).get(u) or {}, f"tool:{tool_key(fam, u)}"
            common = data["tools"].get(tool_key(fam, u), "")
            if common and aid in (row.get("agents") or ()) and tag not in tags and (not unit or unit == mine_key):
                secs.append(f"{TOOL_HEAD.format(tool=row.get('name') or u)}\n{common}")
                tags.append(tag)
    mine = (data["jobs"].get(job) or {}).get(aid, "") if job else ""
    if mine:
        secs.append(f"{JOB_HEAD.format(name=_job_name(job))}\n{mine}")
        tags.append(f"job:{job}")
    return ("\n\n" + HEAD + "\n\n" + "\n\n".join(secs), tags) if secs else ("", [])


def _cut(text):
    return text if len(text) <= DIGEST_MAX else text[:DIGEST_MAX].rstrip() + " …(줄임)"


def digest(job):
    """작업 진행 에이전트에 붙이는 절 — 그 워크플로우의 도구(정의의 줄 차례)마다 적어 둔 내용의 요약 | ""(없음 · 모르는 워크플로우).
    틀이 없는 워크플로우는 「같은 도구」 라고 적은 줄(twins)의 「공통」 글만 싣는다(적은 줄이 없으면 "")."""
    data = load()
    mine = data["jobTools"].get(job) or {} if job else {}
    if not job or not (data["tools"] or mine):
        return ""
    family, units = family_of(job)
    rows, lines, seen = tool_map().get(family, {}) if family else {}, [], set()
    for u in units if family else ():
        common, own = data["tools"].get(tool_key(family, u), ""), mine.get(u, "")
        if common or own:
            lines.append(f"### 도구 「{(rows.get(u) or {}).get('name') or u}」" + (f"\n- 공통: {_cut(common)}" if common else "") + (f"\n- 이 워크플로우: {_cut(own)}" if own else ""))
            seen.add(tool_key(family, u))
    for _own, fam, u in twins(job):   # 같은 도구(등록부의 twins — 틀이 없는 워크플로우의 줄이 다른 틀의 그 도구와 같은 도구) — 그 도구의 「공통」 글만(이 워크플로우 전용 칸은 없다)
        common = data["tools"].get(tool_key(fam, u), "")
        if common and tool_key(fam, u) not in seen:
            lines.append(f"### 도구 「{(tool_map().get(fam, {}).get(u) or {}).get('name') or u}」\n- 공통: {_cut(common)}")
            seen.add(tool_key(fam, u))
    return ("\n\n" + GUIDE_HEAD.format(name=_job_name(job)) + "\n\n" + "\n\n".join(lines)) if lines else ""


def attach(content, what):
    """`llm.call` 의 훅 — 호출 이름(what)의 에이전트에 적어 둔 글을 프롬프트 끝에 붙인다 → (글, 붙인 것의 꼬리표 | None):
    꼬리표 = "all"(에이전트 · 모든 워크플로우) · "tool:<틀>.<줄>"(도구 공통) · "jobtool:<키>/<줄>"(도구 · 그 워크플로우) · "job:<키>"(에이전트 · 그 워크플로우) · "tools-digest"(작업 진행 에이전트의 요약).
    글이 아닌 프롬프트 · 등록 안 된 호출 · 못 읽음은 그대로."""
    try:
        if not isinstance(content, str):
            return content, None
        aid = agent_settings.agent_of(what)
        if not aid:
            return content, None
        job, line = job_now(), line_now()
        family = line[0] if line else (family_of(job)[0] if job and _has_tools() else "")
        text, tags = _part(aid, job, family, line[1] if line else None)
        if aid == GUIDE and job:   # 작업 진행 에이전트 — 그 워크플로우의 도구마다 적어 둔 내용의 요약(스크립트 · 사람이 하는 도구의 내용을 읽는 곳)
            more = digest(job)
            if more:
                text, tags = text + more, tags + ["tools-digest"]
        return (content + text, tags) if text else (content, None)
    except Exception:  # noqa: BLE001 — 적어 둔 글 때문에 호출이 죽지 않는다
        return content, None


def _has_tools():
    data = load()
    return bool(data["tools"] or data["jobTools"])


def reset_memory():
    """시험용 — 메모리 저장 · 읽어 둔 것을 비운다."""
    with _LOCK:
        _MEMORY.clear()
        _MEMORY.update(json.loads(json.dumps(_EMPTY)))
        _CACHE.update(path=None, mtime=None, data=None)
