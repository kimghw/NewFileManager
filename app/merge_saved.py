"""병합 — 서식 쌍에 저장한 묶음 짝(spec_병합 ② §4 「서식 쌍 저장」 · §7): 사람이 확정한 묶음 짝을 문서와 무관한 키로 양식 폴더에 두고, 같은 서식 쌍의 다음 과제에서 스크립트보다 먼저 쓴다.

- 파일: `heading_forms.forms_dir()` 의 `<원본 양식 키>__<목적 양식 키>.pairs.json`(양식 정보 `*.md` 옆 — 양식 목록에는 안 잡힌다). 폴더가 꺼졌거나(None) 양식 키가 없으면 빈 목록·저장 안 함.
  꼴 = {"version": 1, "from": 원본 양식 키, "to": 목적 양식 키, "pairs": [{"to": 묶음 키, "from": 묶음 키, "anchor": 글 | None, "at": 시각}]} — 목적 묶음 키마다 하나(새것이 이김).
- 묶음 키(`group_key`) = 「구분|종류|맥락 차년도|맥락 기관|라벨 꼴|소속 경로|표 서명 해시」 — 블록 id 가 없는 글. 맥락 차년도는 **목적 문서의 당해 차년도(current)에서 떨어진 수**로 적는다
  (y+0 = 당해 · y+1 = 다음 연도 · y-1 = 전년도, 맥락 없음은 「-」) — 절대 차년도가 아니라서 1차년도 보고서로 저장한 짝이 2차년도 보고서에도 맞는다. **원본 문서의 묶음도 같은 기준**(목적 문서의 당해)으로 적는다 —
  「다음 연도 자리 ↔ 계획서의 N+1 차년도 절」 이 「y+1 ↔ y+1」 로 저장되어 N 이 바뀌면 그 해의 절을 가리킨다. current 를 안 주면 절대 차년도(「y=2」 — 대상 차년도가 같은 문서끼리만 맞음).
- 다시 찾기(`fixed_from`): 지금 두 문서의 묶음을 같은 키로 다시 매겨, 저장한 짝의 두 키가 **각각 꼭 한 묶음**에 맞을 때만 낸다(없거나 여럿이면 건너뜀 — 어림하지 않는다).
- 손상 파일(JSON·꼴·version·다른 서식 쌍): 조회(load)는 빈 목록 + broken 표시, 고치는 쪽(save·delete)은 Broken 으로 멈춘다(덮어쓰지 않음 — division_presets 와 같은 규칙)."""
import hashlib
import json
import logging
import re
import threading
from collections import Counter
from datetime import datetime

from app import heading_forms
from app import heading_rules as R
from app.division_presets import Broken

VERSION = 1
log = logging.getLogger(__name__)
_LOCK = threading.Lock()


def _ws(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def group_key(summary, current=None):
    """묶음 요약(`merge_pairs.summarize` 의 한 항목) → 문서와 무관한 묶음 키(글). current = **목적 문서**의 당해 차년도(원본 문서의 묶음에도 같은 값을 준다 — 모듈 설명)."""
    ctx = summary.get("ctx") or {}
    y = ctx.get("year")
    year = "-" if y is None else f"y{y - current:+d}" if isinstance(y, int) and isinstance(current, int) else f"y={y}"
    sig = (summary.get("table") or {}).get("sig") or ()
    table = hashlib.sha1("\x1f".join(_ws(x) for x in sig).encode("utf-8")).hexdigest()[:12] if summary.get("table") else "-"
    return "|".join([summary["dim"], summary["kind"], year, _ws(ctx.get("org")) or "-", _ws(summary.get("label")),
                     ">".join(_ws(x) for x in summary.get("path") or ()), table])


def _keys(groups, current):
    """{문서의 묶음 key: 묶음 키} — 그 문서에서 묶음 키가 하나뿐인 묶음만(같은 꼴이 여럿이면 어느 것인지 알 수 없다)."""
    keys = {s["key"]: group_key(s, current) for s in groups}
    n = Counter(keys.values())
    return {k: v for k, v in keys.items() if n[v] == 1}


def path(from_form, to_form):
    """저장 파일 Path | None(양식 폴더 끔 · 양식 키 없음). 파일 이름으로 못 쓰는 양식 키는 ValueError."""
    d = heading_forms.forms_dir()
    if d is None or not from_form or not to_form:
        return None
    return d / f"{heading_forms.check_key(from_form)}__{heading_forms.check_key(to_form)}.pairs.json"


def _empty(from_form, to_form):
    return {"version": VERSION, "from": from_form, "to": to_form, "pairs": []}


def _clean(data, from_form, to_form):
    if not isinstance(data, dict) or data.get("version") != VERSION or not isinstance(data.get("pairs"), list):
        raise ValueError("서식 쌍 짝 파일 꼴이 아니거나 지원하지 않는 판")
    if (data.get("from"), data.get("to")) != (from_form, to_form):   # 양식 키에 「__」 가 들어 파일 이름이 겹친 다른 쌍
        raise ValueError(f"다른 서식 쌍({data.get('from')!r} → {data.get('to')!r})의 파일")
    out = _empty(from_form, to_form)
    for e in data["pairs"]:
        if not (isinstance(e, dict) and all(isinstance(e.get(k), str) and e[k] for k in ("to", "from")) and isinstance(e.get("anchor"), (str, type(None)))):
            raise ValueError(f"pairs 항목 꼴이 틀림: {e!r:.80}")
        out["pairs"].append({"to": e["to"], "from": e["from"], "anchor": e.get("anchor") or None, "at": e["at"] if isinstance(e.get("at"), str) else ""})
    return out


def _read(p, from_form, to_form):
    """파일 → 정리한 자료. 없으면 빈 목록, 못 읽으면 OSError, 손상이면 Broken."""
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return _empty(from_form, to_form)
    try:
        return _clean(json.loads(raw.decode("utf-8")), from_form, to_form)
    except ValueError as e:   # json·유니코드 오류도 ValueError
        raise Broken(f"서식 쌍 짝 파일이 손상되어 고치지 않았습니다: {p} ({e}) — 파일을 고치거나 옮긴 뒤 다시") from e


def load(from_form, to_form):
    """조회 → {"version", "from", "to", "pairs": [{to, from, anchor, at}], "broken": bool, "path": str | None}.
    양식 폴더 끔·양식 키 없음·파일 없음 = 빈 목록. 못 읽거나 손상 = 빈 목록 + broken(+ error — 파일은 그대로 둔다)."""
    p = path(from_form, to_form)
    if p is None:
        return {**_empty(from_form, to_form), "broken": False, "path": None}
    try:
        return {**_read(p, from_form, to_form), "broken": False, "path": str(p)}
    except (Broken, OSError) as e:
        log.warning("서식 쌍 짝 파일을 읽지 못해 빈 목록으로 봅니다: %s (%s)", p, e)
        return {**_empty(from_form, to_form), "broken": True, "path": str(p), "error": str(e)}


def save(from_form, to_form, pairs, to_groups, from_groups, *, current=None):
    """지금 짝 결과(`merge_pairs.pair`)의 paired 묶음 전부를 저장 — 부르는 쪽이 사람 확정 뒤에만 부른다(② §4 「저장은 사람이 누를 때만」).
    → {"saved": 넣은 수, "skipped": [{"id", "why"}], "total": 파일의 짝 수, "path": str | None}. 있던 파일과 합친다 — 목적 묶음 키가 같으면 새것이 이긴다.
    그 문서 안에서 묶음 키가 겹치는 묶음(같은 꼴이 여럿)은 다시 찾을 수 없으므로 저장하지 않고 skipped 로 알린다. current = 목적 문서의 당해 차년도(group_key).
    양식 폴더가 꺼졌거나 양식 키가 없으면 아무것도 안 쓰고 path None. 손상 파일은 Broken(덮어쓰지 않음)."""
    p = path(from_form, to_form)
    tk, fk = _keys(to_groups, current), _keys(from_groups, current)
    at, new, skipped = datetime.now().isoformat(timespec="seconds"), {}, []
    for g in pairs.get("groups") or ():
        if g.get("status") != "paired" or not g.get("to") or not g.get("from"):
            continue
        a, b = tk.get(g["to"].get("key")), fk.get(g["from"].get("key"))
        if a is None or b is None:
            skipped.append({"id": g.get("id"), "why": "같은 꼴의 묶음이 여럿이거나 지금 문서에 없는 묶음 — 다음 문서에서 다시 찾을 수 없어 저장하지 않음"})
            continue
        anchor = g.get("anchor")
        new[a] = {"to": a, "from": b, "anchor": anchor if isinstance(anchor, str) and anchor else None, "at": at}
    if p is None:
        return {"saved": 0, "skipped": skipped, "total": 0, "path": None}
    with _LOCK:
        data = _read(p, from_form, to_form)
        data["pairs"] = [e for e in data["pairs"] if e["to"] not in new] + list(new.values())
        R._write_json(p, data)
    return {"saved": len(new), "skipped": skipped, "total": len(data["pairs"]), "path": str(p)}


def fixed_from(saved, to_groups, from_groups, *, current=None):
    """저장한 짝(load 결과)을 지금 두 문서의 묶음에 대어 → `merge_pairs.pair(fixed=)` 에 줄 {목적 key: {"from": 원본 key, "source": "saved", "anchor"}}.
    저장한 두 묶음 키가 각각 꼭 한 묶음에 맞는 것만(없거나 여럿이면 건너뜀). current = 목적 문서의 당해 차년도(저장할 때와 같은 뜻)."""
    to_of = {v: k for k, v in _keys(to_groups, current).items()}
    from_of = {v: k for k, v in _keys(from_groups, current).items()}
    return {to_of[e["to"]]: {"from": from_of[e["from"]], "source": "saved", "anchor": e.get("anchor")}
            for e in (saved or {}).get("pairs") or () if e.get("to") in to_of and e.get("from") in from_of}


def delete(from_form, to_form, to):
    """저장한 짝 하나(to = 목적 묶음 키)를 지운다 → 남은 자료(load 꼴). 없으면 KeyError(양식 폴더 끔 포함), 손상 파일은 Broken."""
    p = path(from_form, to_form)
    if p is None:
        raise KeyError(to)
    with _LOCK:
        data = _read(p, from_form, to_form)
        rest = [e for e in data["pairs"] if e["to"] != to]
        if len(rest) == len(data["pairs"]):
            raise KeyError(to)
        data["pairs"] = rest
        R._write_json(p, data)
    return {**data, "broken": False, "path": str(p)}


def merge_fixed(saved_fixed, llm_fixed, user_fixed):
    """세 출처의 fixed 를 하나로 — 같은 목적 묶음은 사람 > LLM > 저장한 짝."""
    return {**(saved_fixed or {}), **(llm_fixed or {}), **(user_fixed or {})}
