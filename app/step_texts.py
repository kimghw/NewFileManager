"""단계 설명 고치기 — 사람이 화면에서 고친 단계의 설명 글(spec_워크플로우 ② §18-26).
2026-11-24 사용자(대시보드 단계 카드의 메모 풍선 「LLM 검증·보완 — 하는 일 · 나오는 것 · 하려면 · 끝난 것으로 보는 때 · 멈추는 때」 를 보이며) "이거 수정할 수 있도록 해줘".

- 단위는 **워크플로우의 단계 줄**(워크플로우 키 + 줄 key)이다 — 같은 줄 key 라도 워크플로우마다 설명이 다르다(등록부가 워크플로우마다 따로 적는다).
- 글은 여섯: `does`(하는 일) · `out`(나오는 것) · `need`(하려면) · `done`(끝난 것으로 보는 때) · `stop`(멈추는 때) · `left`(남기는 것 · 보정) — 등록부 `app/workflow.py` 의 그 줄과 같은 키.
- **등록부의 글은 「기본 글」 이고 그대로다** — 만든 글(workflow.md · tasks/<job>.md)과 에이전트의 프롬프트는 기본 글이다(어느 PC 에서나 같아야 한다 — 도구 이름 고치기 `tool_names` 와 같은 원칙).
  고친 글을 얹는 곳은 등록부 응답(`workflow.listing` — `/workflow` · 두 대시보드의 메모)뿐이다.
- 저장 `%LOCALAPPDATA%\\NewFileManager\\step_texts.json`(env `NFM_STEP_TEXTS` 가 파일 경로 · `off`·`0` 이면 메모리만) = `{version, updated, texts: {"<워크플로우 키>.<줄 key>": {글 키: 글}}}` — 고친 글만.

**가벼운 모듈** — 다른 app 코드를 가져오지 않는다. 그 줄이 등록부에 있는지 · 기본 글은 부르는 쪽(API)이 본다."""
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

FIELDS = (("does", "하는 일"), ("out", "나오는 것"), ("need", "하려면"), ("done", "끝난 것으로 보는 때"), ("stop", "멈추는 때"), ("left", "남기는 것 · 보정"))
KEYS = tuple(k for k, _ in FIELDS)
TEXT_MAX = 1500   # 글 하나의 길이
JOB = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")
UNIT = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")
_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_LOCK = threading.RLock()
_MEMORY = {"version": 0, "texts": {}}
_CACHE = {"path": None, "mtime": None, "data": None}


class Stale(Exception):
    """기대한 판이 지금 판과 다름."""


def path():
    env = os.environ.get("NFM_STEP_TEXTS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NewFileManager" / "step_texts.json"


def key(job, unit):
    return f"{job}.{unit}"


def _key_ok(k):
    job, _, unit = k.rpartition(".") if isinstance(k, str) else ("", "", "")
    return bool(JOB.fullmatch(job)) and bool(UNIT.fullmatch(unit))


def _clean(data):
    data = data if isinstance(data, dict) else {}
    ver = data.get("version")
    rows = data.get("texts") if isinstance(data.get("texts"), dict) else {}
    texts = {}
    for k, row in rows.items():
        if _key_ok(k) and isinstance(row, dict):
            got = {f: v for f, v in row.items() if f in KEYS and isinstance(v, str) and v.strip() and len(v) <= TEXT_MAX}
            if got:
                texts[k] = got
    return {"version": ver if isinstance(ver, int) and not isinstance(ver, bool) else 0, "texts": texts}


def load():
    """{version, texts} — 파일이 없거나 깨졌으면 빈 것."""
    p = path()
    with _LOCK:
        if p is None:
            return _clean(_MEMORY)
        try:
            mt = p.stat().st_mtime_ns
        except OSError:
            return _clean(None)
        if _CACHE["path"] != str(p) or _CACHE["mtime"] != mt:
            try:
                data = _clean(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                data = _clean(None)
            _CACHE.update(path=str(p), mtime=mt, data=data)
        return _clean(_CACHE["data"])


def texts(job):
    """그 워크플로우에서 고친 글 → {줄 key: {글 키: 글}}. 못 읽어도 빈 사전(설명 때문에 화면이 멈추지 않는다)."""
    try:
        head = job + "."
        return {k[len(head):]: v for k, v in load()["texts"].items() if k.startswith(head)}
    except Exception:  # noqa: BLE001
        return {}


def apply(task):
    """등록부의 워크플로우 꼴(stages › steps) → 고친 글을 얹은 사본. 고친 줄에는 `baseText` = {고친 글 키: 기본 글}. 고친 것이 없으면 받은 것 그대로."""
    got = texts(task.get("job") or "") if task else {}
    if not got:
        return task
    hit, stages = False, []
    for g in task.get("stages") or ():
        steps = []
        for s in g["steps"]:
            row = {f: v for f, v in (got.get(s["key"]) or {}).items() if v != s.get(f, "")}
            if row:
                s, hit = {**s, **row, "baseText": {f: s.get(f, "") for f in row}}, True
            steps.append(s)
        stages.append({**g, "steps": steps})
    return {**task, "stages": stages} if hit else task


def check(text):
    """고칠 글 → 다듬은 글(한 줄 — 메모 풍선이 줄마다 「이름 — 글」 로 그린다). 글이 아니거나 너무 길면 ValueError."""
    if text is None:
        return ""
    if not isinstance(text, str):
        raise ValueError("설명은 글이어야 합니다")
    if _BAD.search(text):
        raise ValueError("설명에 쓸 수 없는 글자가 있습니다")
    text = " ".join(text.split())
    if len(text) > TEXT_MAX:
        raise ValueError(f"설명 하나는 {TEXT_MAX}자까지입니다(지금 {len(text)}자)")
    return text


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


def save(job, unit, given, base, expect=None):
    """그 단계의 설명을 저장한다 → {version, texts(고친 글만)}. given = {글 키: 글} — 준 키만 바꾼다(빈 글 · 기본 글과 같은 글 = 고친 글을 지움 → 기본 글로).
    base = {글 키: 기본 글}(부르는 쪽이 등록부에서). expect = 기대 판(다르면 Stale). 꼴이 틀리면 ValueError."""
    if not (isinstance(job, str) and JOB.fullmatch(job) and isinstance(unit, str) and UNIT.fullmatch(unit)):
        raise ValueError("단계(워크플로우 · 줄)의 꼴이 아닙니다")
    if not isinstance(given, dict) or any(f not in KEYS for f in given):
        raise ValueError(f"고칠 글의 키는 {' · '.join(KEYS)} 가운데서")
    clean = {f: check(v) for f, v in given.items()}
    with _LOCK:
        data = load()
        if expect is not None and expect != data["version"]:
            raise Stale(f"단계 설명이 그 사이에 바뀌었습니다(지금 판 {data['version']} · 요청 {expect}) — 다시 읽어 주세요")
        k = key(job, unit)
        row = dict(data["texts"].get(k) or {})
        for f, v in clean.items():
            if v and v != " ".join(str(base.get(f, "")).split()):
                row[f] = v
            else:
                row.pop(f, None)
        if row:
            data["texts"][k] = row
        else:
            data["texts"].pop(k, None)
        data["version"] += 1
        _write(data)
        return {"version": data["version"], "texts": row}
