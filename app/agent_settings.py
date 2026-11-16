"""에이전트 설정 — 사용자가 에이전트마다 정한 값과 실행 기록(spec_에이전트 ② §2·§4). **가벼운 모듈**: `app/llm.py` 가 부를 때마다 읽으므로 다른 app 모듈을 가져오지 않는다
(에이전트 목록·프롬프트 구성은 `app/agents.py` — 그쪽은 LLM 을 쓰는 모듈들을 가져온다).

- 설정 파일 `%LOCALAPPDATA%\\NewFileManager\\agents.json`(env `NFM_AGENTS` 가 파일 경로 · `off`·`0` 이면 메모리만) = `{version, agents: {에이전트 id: {no?, role?, model?, effort?}}}`.
  없는 키 = 기본(코드 등록값). 이 PC 의 모든 문서가 같이 쓴다. 고친 시각 기준으로 다시 읽는다(다른 프로세스가 고쳐도 다음 호출에 반영).
- `override(what)` — `llm.call` 의 `what`(호출 이름 「merge-llm-3」·「heading_section#2」)을 에이전트 id 로 바꿔 그 에이전트의 모델·생각 깊이 설정을 준다.
  사용자가 여기서 정한 모델은 서버 전체 설정(`NFM_LLM_MODEL_FORCE`)·코드가 정한 모델보다 **먼저**다(에이전트 하나에 대해 사람이 직접 고른 값).
- `record(what, out)` — 모든 `llm.call` 의 결과 한 줄을 메모리 고리(최근 300)에 남긴다: 실행 번호(서버를 켠 뒤 1부터) · 시각 · 에이전트 · 모델 · 길 · 걸린 시간 · 비용 · 오류. 파일에는 안 남긴다."""
import collections
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

MODELS = ("claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")   # 화면이 고르게 하는 모델(다른 id 도 꼴만 맞으면 저장은 된다)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_MODEL_RE = re.compile(r"[a-z0-9][a-z0-9.\-]{0,63}")
_NO_RE = re.compile(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣._\-]{0,11}")
ROLE_MAX = 600
RUNS_MAX = 300

# llm.call 의 what 첫머리 → 에이전트 id(긴 것부터 견준다). 새 LLM 호출을 만들면 여기와 app/agents.py AGENTS 에 한 줄씩.
PREFIX = (
    ("heading_rules", "heading_rules"), ("heading_types", "heading_types"), ("heading_section", "heading_section"), ("heading_formats", "heading_formats"),
    ("heading_review", "heading_review"), ("heading_tables", "heading_tables"),
    ("divisions-llm", "div_review"), ("divisions-missing", "div_missing"),
    ("merge-llm", "merge_links"), ("merge-table-map", "merge_table_map"), ("merge-gaps", "merge_gaps"), ("gather-llm", "gather"),
    ("table-formula", "table_formula"), ("table-fill", "table_fill"), ("table-make", "table_make"),
    ("doc-agent", "doc_agent"), ("style-review", "style_review"), ("tpl-agent", "tpl_agent"),
    ("work-guide", "work_guide"),
    ("verify-llm", "verify_review"),
)
_BY_LEN = sorted(PREFIX, key=lambda x: -len(x[0]))
IDS = tuple(dict.fromkeys(a for _, a in PREFIX))

_LOCK = threading.RLock()
_MEMORY = {"version": 0, "agents": {}}     # 저장 끔일 때
_CACHE = {"path": None, "mtime": None, "data": None}
_RUNS = collections.deque(maxlen=RUNS_MAX)
_SEQ = [0]


class Stale(Exception):
    """기대한 판이 지금 판과 다름(그 사이에 다른 곳에서 고침)."""


def path():
    """설정 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_AGENTS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "agents.json"


def _clean(data):
    agents = data.get("agents") if isinstance(data, dict) else None
    out = {}
    for aid, v in (agents.items() if isinstance(agents, dict) else ()):
        if aid in IDS and isinstance(v, dict):
            out[aid] = {k: v[k] for k in ("no", "role", "model", "effort") if isinstance(v.get(k), str) and v[k]}
    ver = data.get("version") if isinstance(data, dict) else 0
    return {"version": ver if isinstance(ver, int) and not isinstance(ver, bool) else 0, "agents": out}


def load():
    """{version, agents: {id: {no?, role?, model?, effort?}}} — 파일이 없거나 깨졌으면 빈 설정(깨진 파일은 덮어쓰지 않는다 — 저장할 때 새로 쓴다)."""
    p = path()
    with _LOCK:
        if p is None:
            return _clean(_MEMORY)
        try:
            mt = p.stat().st_mtime_ns
        except OSError:
            _CACHE.update(path=str(p), mtime=None, data={"version": 0, "agents": {}})
            return _clean(_CACHE["data"])
        if _CACHE["path"] != str(p) or _CACHE["mtime"] != mt:
            try:
                data = _clean(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                data = {"version": 0, "agents": {}}
            _CACHE.update(path=str(p), mtime=mt, data=data)
        return _clean(_CACHE["data"])


def get(aid):
    return dict(load()["agents"].get(aid) or {})


def check(patch):
    """고칠 값 {no?, role?, model?, effort?}(None·"" = 기본으로) → 다듬은 값. 꼴이 틀리면 ValueError."""
    if not isinstance(patch, dict):
        raise ValueError("고칠 값은 {no, role, model, effort} 가운데 있는 것")
    out = {}
    for k, v in patch.items():
        if k not in ("no", "role", "model", "effort"):
            continue
        if v is None or v == "":
            out[k] = None
            continue
        if not isinstance(v, str):
            raise ValueError(f"{k} 는 글이어야 합니다")
        v = v.strip()
        if k == "no" and not _NO_RE.fullmatch(v):
            raise ValueError("작업 번호는 글자·숫자로 시작하는 12자 이하(글자 · 숫자 · . _ -)")
        if k == "role":
            v = re.sub(r"[ \t]+\n", "\n", v)
            if len(v) > ROLE_MAX:
                raise ValueError(f"역할 글은 {ROLE_MAX}자 이하")
        if k == "model" and not _MODEL_RE.fullmatch(v):
            raise ValueError("모델 이름 꼴이 아닙니다")
        if k == "effort" and v not in EFFORTS:
            raise ValueError(f"생각 깊이는 {' · '.join(EFFORTS)} 가운데")
        out[k] = v or None
    return out


def save(aid, patch, expect=None):
    """에이전트 aid 의 설정을 고친다(patch 의 None = 그 값을 지워 기본으로) → 그 에이전트의 설정. expect = 기대 판(다르면 Stale). 없는 id 는 KeyError."""
    if aid not in IDS:
        raise KeyError(aid)
    patch = check(patch)
    with _LOCK:
        data = load()
        if expect is not None and expect != data["version"]:
            raise Stale(f"에이전트 설정이 그 사이에 바뀌었습니다(지금 판 {data['version']} · 요청 {expect}) — 다시 읽어 주세요")
        cur = dict(data["agents"].get(aid) or {})
        for k, v in patch.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        if cur:
            data["agents"][aid] = cur
        else:
            data["agents"].pop(aid, None)
        data["version"] += 1
        data["updated"] = round(time.time(), 3)
        p = path()
        if p is None:
            _MEMORY.clear()
            _MEMORY.update(data)
        else:
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
        return dict(cur)


def agent_of(what):
    """llm.call 의 what → 에이전트 id | None(등록 안 된 호출)."""
    w = what if isinstance(what, str) else ""
    for pre, aid in _BY_LEN:
        if w.startswith(pre):
            return aid
    return None


def override(what):
    """그 호출의 에이전트에 사용자가 정한 {model?, effort?} — 없으면 {}. 어떤 오류도 호출을 막지 않는다."""
    try:
        aid = agent_of(what)
        s = get(aid) if aid else {}
        return {k: s[k] for k in ("model", "effort") if s.get(k)}
    except Exception:  # noqa: BLE001 — 설정을 못 읽어도 LLM 호출은 기본값으로 돈다
        return {}


def record(what, out):
    """llm.call 한 번의 결과를 실행 기록에 — 실행 번호는 서버를 켠 뒤 1부터."""
    try:
        with _LOCK:
            _SEQ[0] += 1
            _RUNS.append({"n": _SEQ[0], "t": round(time.time(), 3), "agent": agent_of(what), "what": str(what)[:80], "model": out.get("model"), "effort": out.get("effort"),
                          "backend": out.get("backend"), "ms": out.get("ms") or 0, "costUsd": out.get("costUsd"), "error": (str(out["error"])[:300] if out.get("error") else None),
                          "ok": out.get("data") is not None})
    except Exception:  # noqa: BLE001
        pass


def runs(agent=None, limit=50):
    """실행 기록(새 것부터) — agent 를 주면 그 에이전트 것만."""
    with _LOCK:
        rows = [r for r in reversed(_RUNS) if agent is None or r["agent"] == agent]
    return rows[:max(1, min(int(limit), RUNS_MAX))]


def tally():
    """에이전트 id → {runs(서버를 켠 뒤 호출 수), fails, last(마지막 실행)}."""
    out = {}
    with _LOCK:
        for r in _RUNS:
            if not r["agent"]:
                continue
            t = out.setdefault(r["agent"], {"runs": 0, "fails": 0, "last": None})
            t["runs"] += 1
            t["fails"] += 0 if r["ok"] else 1
            t["last"] = r
    return out


def reset_runs():
    """시험용."""
    with _LOCK:
        _RUNS.clear()
        _SEQ[0] = 0
