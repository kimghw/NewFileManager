"""사람이 하는 일의 확인 기록 — 조립한 워크플로우(정의 v2)의 「사람이 하는 일」 줄을 사람이 「했음」 으로 끝낸 기록(spec_워크플로우 ② §18-7 · 고친 규칙 ② §18-12 ⑦).

- 자리 = 그 묶음의 **목적 문서**의 작업 폴더 `flow_hands.json` = `{줄 key: {ver, docs[확인한 문서 id], at, by}}` — 작업 저장이 꺼져 있으면 메모리만.
  워크플로우 옵션(task_options)의 줄 하나에 적지 않는다(기관 문서 A 에서 누른 확인이 B 의 같은 줄을 끝내거나 · 글을 고친 뒤 · 초기화 뒤의 옛 탭이 보낸 「했음」 이 먹지 않게 — astra).
- **ver** = 그 줄의 판(`unit_steps.hand_ver` — 정의의 지문 + 그 줄의 이름 · 글): 판이 다르면 끝나지 않은 것이다(글을 고치면 앞 확인은 무효). 문서 전체의 차례에는 묶지 않는다(다음 반영이 방금 확인을 무효로 만들지 않게).
- 새 라운드로 잇지 않는다(다른 작업 폴더) · 작업 내용 초기화는 지운다(`forget` — server._reset_forget). 에이전트는 「했음」 을 대신 누르지 않는다(끝점은 사람의 화면만 — app/flow_hands_api.py).
**가벼운 모듈** — works 만 가져온다(함수 안에서)."""
import json
import os
import tempfile
import threading
import time

FILE = "flow_hands.json"
_LOCK = threading.Lock()
_MEMORY = {}   # 작업 저장이 꺼졌을 때 — {작업 id: {줄 key: 기록}}


def _path(wid):
    from app import works
    d = works.folder(wid)
    return d / FILE if d is not None else None


def read(wid):
    """그 목적 문서의 확인 기록들 → {줄 key: {ver, docs, at, by}}(사본 · 못 읽으면 빈 것 — 「했음」 이 없는 것으로: 다시 누르면 된다)."""
    p = _path(wid)
    if p is None:
        return {k: dict(v) for k, v in _MEMORY.get(wid, {}).items()}
    try:
        got = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: dict(v) for k, v in got.items() if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("ver"), str)} if isinstance(got, dict) else {}


def _write(wid, rows):
    p = _path(wid)
    if p is None:
        _MEMORY[wid] = {k: dict(v) for k, v in rows.items()}
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def done(wid, key, ver):
    """그 줄이 그 판으로 「했음」 인가."""
    r = read(wid).get(key)
    return bool(r) and r.get("ver") == ver


def mark(wid, key, ver, docs=(), by="human"):
    """「했음」 을 적는다 → 그 기록."""
    with _LOCK:
        rows = read(wid)
        rows[key] = {"ver": ver, "docs": [d for d in docs if isinstance(d, str)], "at": time.time(), "by": by}
        _write(wid, rows)
        return dict(rows[key])


def clear(wid, key):
    """「했음 취소」 → 지웠나."""
    with _LOCK:
        rows = read(wid)
        if key not in rows:
            return False
        rows.pop(key)
        _write(wid, rows)
        return True


def forget(wid):
    """그 목적 문서의 확인 기록을 모두 지운다(작업 내용 초기화) — 뒷정리라 예외를 내지 않는다."""
    with _LOCK:
        _MEMORY.pop(wid, None)
        p = _path(wid)
        if p is not None:
            try:
                p.unlink()
            except OSError:
                pass
