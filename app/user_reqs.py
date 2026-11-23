"""사용자 요구사항 — 도구 · 단계 · 워크플로우마다 사용자가 말한 요구사항을 한곳에(spec_워크플로우 ② §18-20).
2026-11-21 사용자 "도구, 단계, 워크플로우 에 대한 사용자 요구사항을 관리 할 수 있고 웹에서 도구에서 볼 수 있게 해줘,, 우클릭이나 아이콘을 넣고 선택하면 될듯."

- **원본은 저장소 파일** `reqs/requirements.json`(env `NFM_REQS` 가 파일 경로 · `off`·`0` 이면 메모리만 — 시험 · 화면 검사는 임시 파일).
  코드 에이전트가 사용자의 말을 받을 때 여기 적고(대화에서 받은 것 `src: "chat"`), 사용자는 `/workflow` 의 「요구사항」 열에서 보고 적는다(`src: "web"`). 깃으로 관리된다(사양서 · jobs/ 와 같은 자리의 글).
- 꼴 = `{version, items: [{id, date(YYYY-MM-DD — 말한 날), said(사용자가 한 말), note(정리 — 어떻게 정했나 · 어디에 반영했나), state(open 요청 · done 반영 · hold 보류),
  targets["<종류>:<키>" …], spec(사양서 자리 — 「spec_워크플로우 ② §18-17」), src(chat · web), at(적은 시각)}]}` — 항목 하나가 한 줄(손으로 고치기 · 깃 병합이 쉽게).
- **대상**(`targets`) = 그 요구사항이 가리키는 것 — 넷:
  `tool:<틀>.<줄 key>`(조립에 놓는 도구 — agent_notes · tool_names 와 같은 단위: 틀 = relay · gather · single) · `common:<id>`(등록부의 도구 · 일반 단계 — `app/workflow.py` COMMON) ·
  `stage:<워크플로우 키>.<묶음 id>`(그 워크플로우의 단계 묶음) · `flow:<워크플로우 키>`(워크플로우). 이름이 아니라 키로 묶는다(도구 이름은 사람이 고칠 수 있다).
- 요구사항은 **기록**이다 — 이 글로 스크립트 · LLM 의 동작이 바뀌지 않는다(LLM 에 줄 글은 「도구에 적어 두는 내용」: agent_notes). 확정한 사양의 원본은 사양서 ② 이고 여기는 사용자의 말 + 그 자리의 링크다.

**가벼운 모듈** — 다른 app 코드를 가져오지 않는다. 그 대상이 등록부에 있는지는 부르는 쪽(API)이 본다."""
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "reqs" / "requirements.json"
SAID_MAX = 2000      # 사용자가 한 말
NOTE_MAX = 2000      # 정리
SPEC_MAX = 200       # 사양서 자리
TARGETS_MAX = 12     # 항목 하나의 대상 수
ITEMS_MAX = 3000
STATES = ("open", "done", "hold")
STATE_NAME = {"open": "요청", "done": "반영", "hold": "보류"}   # 화면 말
KINDS = ("tool", "common", "stage", "flow")
SRCS = ("chat", "web")
TARGET = re.compile(r"tool:(?:relay|gather|single|collect)\.[A-Za-z][A-Za-z0-9]{0,39}|common:[a-z][a-z0-9_]{0,39}|stage:[a-z][a-z0-9_]{0,39}\.[A-Za-z][A-Za-z0-9_]{0,39}|flow:[a-z][a-z0-9_]{0,39}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")

_LOCK = threading.RLock()
_MEMORY = {"version": 0, "items": []}   # 저장 끔일 때
_CACHE = {"path": None, "mtime": None, "data": None}


def path():
    """저장 파일 Path | None(메모리만)."""
    env = os.environ.get("NFM_REQS", "").strip()
    if env.lower() in ("off", "0"):
        return None
    return Path(env) if env else FILE


def target_ok(t):
    return isinstance(t, str) and bool(TARGET.fullmatch(t))


def _text(v, limit):
    return v.strip() if isinstance(v, str) and len(v.strip()) <= limit else None


def _item(x):
    """파일의 항목 하나 → 깨끗한 항목 | None(꼴이 아님 — 버리지 않고 읽을 때만 뺀다: 저장은 받은 항목 그대로 다시 쓴다)."""
    if not isinstance(x, dict) or not (isinstance(x.get("id"), str) and ID.fullmatch(x["id"])):
        return None
    said = _text(x.get("said"), SAID_MAX)
    targets = [t for t in x["targets"] if target_ok(t)] if isinstance(x.get("targets"), list) else []
    if not said or not targets:
        return None
    date = x.get("date") if isinstance(x.get("date"), str) and DATE.fullmatch(x["date"]) else ""
    at = x.get("at")
    return {"id": x["id"], "date": date, "said": said, "note": _text(x.get("note"), NOTE_MAX) or "", "state": x.get("state") if x.get("state") in STATES else "open",
            "targets": list(dict.fromkeys(targets))[:TARGETS_MAX], "spec": _text(x.get("spec"), SPEC_MAX) or "", "src": x.get("src") if x.get("src") in SRCS else "chat",
            "at": at if isinstance(at, (int, float)) and not isinstance(at, bool) else 0}


def _clean(data):
    data = data if isinstance(data, dict) else {}
    ver, seen, items = data.get("version"), set(), []
    for x in (data["items"] if isinstance(data.get("items"), list) else ()):
        it = _item(x)
        if it and it["id"] not in seen:
            seen.add(it["id"])
            items.append(it)
    return {"version": ver if isinstance(ver, int) and not isinstance(ver, bool) else 0, "items": items}


def load():
    """{version, items[…]} — 파일이 없으면 빈 것. 깨진 파일은 ValueError(조용히 비우지 않는다 — 저장소 파일이라 다음 저장이 덮으면 요구사항이 사라진다)."""
    p = path()
    with _LOCK:
        if p is None:
            return _clean(json.loads(json.dumps(_MEMORY)))
        try:
            mt = p.stat().st_mtime_ns
        except OSError:
            return _clean(None)
        if _CACHE["path"] != str(p) or _CACHE["mtime"] != mt:
            try:
                data = _clean(json.loads(p.read_text(encoding="utf-8")))
            except OSError as e:
                raise ValueError(f"요구사항 파일을 읽지 못했습니다: {e}") from e
            except ValueError as e:
                raise ValueError(f"요구사항 파일이 깨졌습니다({p.name}): {e}") from e
            _CACHE.update(path=str(p), mtime=mt, data=data)
        return json.loads(json.dumps(_CACHE["data"]))


def dumps(data):
    """파일의 글 — 항목 하나가 한 줄."""
    rows = ",\n".join("  " + json.dumps(it, ensure_ascii=False) for it in data["items"])
    return "{\n" + f' "version": {data["version"]},\n "items": [\n{rows}\n ]\n' + "}\n"


def _write(data):
    data["version"] = data.get("version", 0) + 1
    p = path()
    if p is None:
        _MEMORY.clear()
        _MEMORY.update(json.loads(json.dumps(data)))
        return data
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(dumps(data))
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _CACHE.update(path=None, mtime=None, data=None)
    return data


def _fields(body, *, need_all):
    """요청의 글 → 고칠 값 {…} · 꼴이 아니면 ValueError. need_all = 새 항목(said · targets 가 꼭)."""
    out = {}
    if "said" in body or need_all:
        said = _text(body.get("said"), SAID_MAX)
        if not said:
            raise ValueError(f"요구사항의 글을 적으세요({SAID_MAX}자까지)")
        out["said"] = said
    if "targets" in body or need_all:
        ts = body.get("targets")
        if not isinstance(ts, list) or not ts or len(ts) > TARGETS_MAX or not all(target_ok(t) for t in ts):
            raise ValueError("대상(도구 · 단계 · 워크플로우)의 꼴이 아닙니다")
        out["targets"] = list(dict.fromkeys(ts))
    for k, limit in (("note", NOTE_MAX), ("spec", SPEC_MAX)):
        if k in body:
            v = _text(body.get(k) or "", limit)
            if v is None:
                raise ValueError(f"글이 너무 깁니다({limit}자까지)")
            out[k] = v
    if "state" in body:
        if body.get("state") not in STATES:
            raise ValueError("상태는 요청 · 반영 · 보류 가운데 하나")
        out["state"] = body["state"]
    if "date" in body:
        d = body.get("date") or ""
        if d and not (isinstance(d, str) and DATE.fullmatch(d)):
            raise ValueError("날짜는 YYYY-MM-DD")
        out["date"] = d
    return out


def add(body, src="web"):
    """새 항목 → 그 항목. 꼴이 아니면 ValueError."""
    got = _fields(body if isinstance(body, dict) else {}, need_all=True)
    with _LOCK:
        data = load()
        if len(data["items"]) >= ITEMS_MAX:
            raise ValueError("요구사항이 너무 많습니다")
        have = {it["id"] for it in data["items"]}
        if src == "chat":   # 대화에서 받은 것 — 차례 번호(r001 …)
            rid = f"r{max([int(i[1:]) for i in have if re.fullmatch(r'r[0-9]+', i)] or [0]) + 1:03d}"
        else:               # 화면에서 적은 것 — 겹치지 않는 짧은 키(여러 PC 에서 적어도 깃 병합이 안 부딪히게)
            rid = next(i for i in iter(lambda: "w" + secrets.token_hex(4), None) if i not in have)
        item = {"id": rid, "date": got.get("date") or time.strftime("%Y-%m-%d"), "said": got["said"], "note": got.get("note", ""), "state": got.get("state", "open"),
                "targets": got["targets"], "spec": got.get("spec", ""), "src": src if src in SRCS else "web", "at": round(time.time())}
        data["items"].append(item)
        _write(data)
        return item


def edit(rid, body):
    """항목을 고침 → 그 항목 | None(없음). 꼴이 아니면 ValueError."""
    got = _fields(body if isinstance(body, dict) else {}, need_all=False)
    with _LOCK:
        data = load()
        item = next((it for it in data["items"] if it["id"] == rid), None)
        if item is None:
            return None
        item.update(got)
        _write(data)
        return item


def remove(rid):
    """항목을 지움 → True | False(없음)."""
    with _LOCK:
        data = load()
        rest = [it for it in data["items"] if it["id"] != rid]
        if len(rest) == len(data["items"]):
            return False
        data["items"] = rest
        _write(data)
        return True


def of(target):
    """그 대상의 요구사항(파일의 차례 = 적은 차례)."""
    return [it for it in load()["items"] if target in it["targets"]]


def counts(items=None):
    """대상 → {n(모두), open(요청)}."""
    out = {}
    for it in (load()["items"] if items is None else items):
        for t in it["targets"]:
            c = out.setdefault(t, {"n": 0, "open": 0})
            c["n"] += 1
            c["open"] += it["state"] == "open"
    return out
