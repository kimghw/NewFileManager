"""표 매핑 규칙의 저장(spec_테이블매니저 ② §7 「키-값 추출과 매핑」 — 「매핑 규칙」). 2026-11-19 사용자 "그리고 동일한 테이블이 아니면 매핑규칙은 관리되어야지".

- **규칙 묶음** = (원본 표 타입 → 대상 표 타입) 한 짝마다 하나 — **같은 타입 → 같은 타입도 한 짝**이다(같은 타입이어도 키는 다를 수 있다: 「1차년도 › 현금」 ↔ 「2차년도 › 현금」):
  `{id, name, from: {type, label}, to: {type, label}, alias: [{from: 원본 머리글, to: 대상 머리글}], pairs: [{from: 원본 키, to: 대상 키, fromLabel, toLabel}],
   ops: [{part: 받을 표의 머리글 조각, op} | {key: 받을 칸의 키, op, label}], version, updated}`.
  `ops` = **칸마다 넣는 방식**(같은 사양서 ② §7 — 2026-11-19 사용자 "어떤건 더해서 합이되는 필드가 있고 어떤건 다른걸 덮어 씌우면 합하거나 빼는게 있고 하잖아"): op = fill(빈 칸에만 — 기본) · add(더하기) · sub(빼기) · replace(덮어쓰기).
  `part` 는 그 머리글 아래의 칸 모두 · `key` 는 그 칸 하나(칸 쪽이 먼저). 읽는 것은 `table_kv._ops`. `ops` 가 없는 옛 묶음은 빈 목록.
  표 타입 = `table_kv.type_key`(머리글 지문 — 음영 칸의 글에서 빈칸 · 숫자 · 문장 부호를 뺀 것: 값을 채워도 안 바뀐다 · 같은 날 사용자 "같은 표 가 아니라 같은 타입 이런걸로 하면 되지").
  `alias` = 머리글 바꿔 읽기 · `pairs` = 칸 짝. 규칙을 읽어 짝짓는 것은 `table_kv.plan(src, dst, rules)`.
- 저장: **서버 전체에 하나** — 헤딩 저장소 폴더(`heading_rules.store_dir()` — env `NFM_HEADINGS`)의 `table_maps.json` `{version: 1, maps: {id: 묶음}}`. 문서 · 작업에 묶이지 않는다
  (같은 두 표 타입이면 다른 문서에서도 다시 쓰인다). 저장이 꺼져 있으면(`NFM_HEADINGS=off`) 메모리.
- `list()` · `find(from_type, to_type)` · `put(묶음)`(없으면 새로 · 있으면 기대 `version` 이 맞을 때만 — 아니면 `heading_rules.StaleVersion` → API 409) · `delete(id)`.
  통째 원자적 저장(임시 파일 → 바꿔 넣기 · 프로세스 안 잠금). 손상된 파일: 조회는 빈 목록, 고치는 길(`put` · `delete`)은 `Broken` 으로 멈춘다(정상 묶음까지 빈 목록으로 덮어쓰지 않는다).
- **꺼 둔 값**(같은 사양서 ② §7 의 「구분 기준의 값 고르기」 — 「꺼 둔 값을 기억한다」: 2026-11-19 사용자 "꺼 둔 값을 기억할게"): 계획에서 꺼 둔 구분 기준의 값을 그 기준이 있는 표의 **타입**마다 저장한다 —
  같은 파일에 규칙 묶음과 따로 `offs: {표 타입: {기준(year · org · stage · period): [값 머리의 키 조각…]}}`. `get_offs(표 타입)` · `put_offs(표 타입, offs)`(빈 것이면 그 타입을 지운다).
  규칙 묶음(`maps`)과 서로 건드리지 않는다(둘 다 파일을 통째로 읽어 제 것만 고쳐 쓴다). `offs` 가 없는 옛 파일은 빈 것으로 읽는다. 판(version)은 없다 — 마지막에 쓴 것이 남는다.
- 이 모듈의 `list` 는 묶음 목록을 주는 함수다 — 모듈 안에서 내장 `list(…)` 를 쓰지 않는다."""
import json
import re
import threading
import time
import uuid

from app import heading_rules as R

FILE = "table_maps.json"
VERSION = 1          # 파일 꼴의 판
NAME_MAX = 60
LABEL_MAX = 200      # 표 · 키의 보이는 이름
KEY_MAX = 1000       # 키 · 머리글 하나
ALIAS_MAX = 200
PAIRS_MAX = 2000
MAPS_MAX = 500
OPS = ("fill", "add", "sub", "replace")   # 칸마다 넣는 방식(= `table_kv.OPS`)
OPS_MAX = 500
OFF_BASES = ("year", "org", "stage", "period")   # 꺼 둔 값의 기준(= `table_kv.BASES` — 이 모듈은 table_kv 를 부르지 않는다: 시험이 둘이 같은지 본다)
OFF_PARTS_MAX = 200  # 기준 하나에 꺼 둔 값
OFFS_MAX = 2000      # 꺼 둔 값을 지닌 표 타입
_TYPE = re.compile(r"^[0-9a-f]{12}$")
_ID = re.compile(r"^m[0-9a-f]{10}$")
_WS = re.compile(r"\s+")
_LOCK = threading.RLock()
_MEMORY = {}         # 저장 끔(off)일 때의 저장소 {"data": …}

StaleVersion = R.StaleVersion


class Broken(ValueError):
    """저장 파일이 손상됨 — 고치지 않는다(API 503)."""


def _path():
    d = R.store_dir()
    return None if d is None else d / FILE


def _empty():
    return {"version": VERSION, "maps": {}, "offs": {}}


def _text(v, n, what, must=True):
    """한 줄 글(빈칸을 한 칸으로) — 글이 아니거나 너무 길면 ValueError."""
    if v is None and not must:
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{what}: 글이어야 합니다")
    s = _WS.sub(" ", v).strip()
    if must and not s:
        raise ValueError(f"{what}: 비어 있습니다")
    if len(s) > n:
        raise ValueError(f"{what}: {n}자 이하")
    return s


def _side(v, what):
    if not isinstance(v, dict) or not isinstance(v.get("type"), str) or not _TYPE.match(v["type"]):
        raise ValueError(f"{what}: {{type: 표 타입(12자리), label: 보일 이름}}")
    return {"type": v["type"], "label": _text(v.get("label"), LABEL_MAX, f"{what}.label", must=False)}


def clean(bundle):
    """묶음의 내용(이름 · 두 표 · 규칙)을 정리한 꼴로 — 꼴이 틀리면 ValueError. id · version · updated 는 여기서 안 본다."""
    if not isinstance(bundle, dict):
        raise ValueError("규칙 묶음이 아닙니다")
    src, dst = _side(bundle.get("from"), "from"), _side(bundle.get("to"), "to")   # 같은 타입끼리도 한 짝이다(모듈 설명)
    alias, pairs, ops = bundle.get("alias") or [], bundle.get("pairs") or [], bundle.get("ops") or []
    if not isinstance(ops, (tuple, type([]))) or len(ops) > OPS_MAX:
        raise ValueError(f"ops 는 {OPS_MAX}개 이하의 목록")
    if not isinstance(alias, (tuple, type([]))) or len(alias) > ALIAS_MAX:
        raise ValueError(f"alias 는 {ALIAS_MAX}개 이하의 목록")
    if not isinstance(pairs, (tuple, type([]))) or len(pairs) > PAIRS_MAX:
        raise ValueError(f"pairs 는 {PAIRS_MAX}개 이하의 목록")
    out_a, seen = [], set()
    for i, a in enumerate(alias):
        if not isinstance(a, dict):
            raise ValueError(f"alias[{i}]: {{from: 원본 머리글, to: 대상 머리글}}")
        f, t = _text(a.get("from"), KEY_MAX, f"alias[{i}].from"), _text(a.get("to"), KEY_MAX, f"alias[{i}].to")
        if f == t:
            raise ValueError(f"alias[{i}]: 같은 글로 바꿔 읽는 규칙입니다(「{f}」)")
        if f in seen:
            raise ValueError(f"alias[{i}]: 「{f}」 를 바꿔 읽는 규칙이 둘입니다")
        seen.add(f)
        out_a.append({"from": f, "to": t})
    out_p, seen = [], set()
    for i, p in enumerate(pairs):
        if not isinstance(p, dict) or not isinstance(p.get("from"), str) or not isinstance(p.get("to"), str) or not p["from"] or not p["to"]:
            raise ValueError(f"pairs[{i}]: {{from: 원본 키, to: 대상 키, fromLabel?, toLabel?}}")
        if len(p["from"]) > KEY_MAX or len(p["to"]) > KEY_MAX:
            raise ValueError(f"pairs[{i}]: 키는 {KEY_MAX}자 이하")
        if p["from"] in seen:
            raise ValueError(f"pairs[{i}]: 같은 원본 키의 칸 짝이 둘입니다")
        seen.add(p["from"])
        out_p.append({"from": p["from"], "to": p["to"], "fromLabel": _text(p.get("fromLabel"), LABEL_MAX, f"pairs[{i}].fromLabel", must=False),
                      "toLabel": _text(p.get("toLabel"), LABEL_MAX, f"pairs[{i}].toLabel", must=False)})
    out_o, seen = [], set()
    for i, o in enumerate(ops):   # 칸마다 넣는 방식 — {part, op} | {key, op, label?}: 조각 · 키의 글은 그대로(꼭 같아야 듣는다)
        if not isinstance(o, dict) or o.get("op") not in OPS or (o.get("part") is None) == (o.get("key") is None):
            raise ValueError(f"ops[{i}]: {{part: 받을 표의 머리글 조각, op}} 또는 {{key: 받을 칸의 키, op}} — op 는 {' · '.join(OPS)}")
        kind = "part" if o.get("part") is not None else "key"
        v = o[kind]
        if not isinstance(v, str) or not v.strip() or len(v) > KEY_MAX:
            raise ValueError(f"ops[{i}].{kind}: 글({KEY_MAX}자 이하)")
        if (kind, v) in seen:
            raise ValueError(f"ops[{i}]: 「{v}」 의 넣는 방식이 둘입니다")
        seen.add((kind, v))
        out_o.append({kind: v, "op": o["op"], **({"label": _text(o.get("label"), LABEL_MAX, f"ops[{i}].label", must=False)} if kind == "key" else {})})
    name = bundle.get("name")
    name = _text(name, NAME_MAX, "name") if isinstance(name, str) and name.strip() else (f"{src['label'] or '원본 표'} → {dst['label'] or '대상 표'}")[:NAME_MAX]
    return {"name": name, "from": src, "to": dst, "alias": out_a, "pairs": out_p, "ops": out_o}


def _parse(data):
    """파일 내용 → 저장소. 꼴이 틀리면 ValueError."""
    if not isinstance(data, dict) or not isinstance(data.get("maps"), dict) or data.get("version") != VERSION:
        raise ValueError("표 매핑 규칙 파일 꼴이 아닙니다")
    out = _empty()
    for mid, b in data["maps"].items():
        if not isinstance(mid, str) or not _ID.match(mid) or not isinstance(b, dict):
            raise ValueError(f"maps.{mid}: 묶음이 아님")
        ver, at = b.get("version"), b.get("updated")
        if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
            raise ValueError(f"maps.{mid}: version")
        out["maps"][mid] = {"id": mid, **clean(b), "version": ver, "updated": at if isinstance(at, (int, float)) and not isinstance(at, bool) else None}
    offs = data.get("offs", {})   # 없는 옛 파일 = 빈 것
    if not isinstance(offs, dict):
        raise ValueError("offs: {표 타입: {기준: [키 조각…]}}")
    for t, o in offs.items():
        if not isinstance(t, str) or not _TYPE.match(t):
            raise ValueError(f"offs.{t}: 표 타입이 아님")
        got = clean_offs(o)
        if got:
            out["offs"][t] = got
    return out


def load(strict=False):
    """저장소 {version, maps: {id: 묶음}} — 없으면 빈 것. 손상(JSON · 꼴): strict=False(조회)면 빈 것, strict=True(고치기 전)면 `Broken`. 못 읽으면(OSError) 조회는 빈 것 · 고치기는 그 오류."""
    with _LOCK:
        p = _path()
        if p is None:
            return {**_empty(), **json.loads(json.dumps(_MEMORY.get("data") or {}))}
        try:
            raw = R._retry(p.read_bytes)
        except FileNotFoundError:
            return _empty()
        except OSError:
            if strict:
                raise
            return _empty()
        try:
            return _parse(json.loads(raw.decode("utf-8")))
        except (ValueError, KeyError) as e:   # json 오류도 ValueError
            if strict:
                raise Broken(f"표 매핑 규칙 파일이 손상되어 고치지 않았습니다: {p} ({e}) — 파일을 고치거나 옮긴 뒤 다시 하세요") from e
            return _empty()


def _save(data):
    p = _path()
    if p is None:
        _MEMORY["data"] = json.loads(json.dumps(data))
    else:
        R._write_json(p, data)
        _MEMORY.pop("data", None)


def list():  # noqa: A001 — 사양의 이름(모듈 안에서 내장 list 를 쓰지 않는다)
    """저장된 규칙 묶음 전부 — 최근 고친 것부터."""
    return sorted(load()["maps"].values(), key=lambda b: (-(b.get("updated") or 0), b["name"], b["id"]))


def find(from_type, to_type):
    """(원본 타입 → 대상 타입) 짝의 묶음 | None. 방향이 있다 — 거꾸로 짝(대상 → 원본)은 다른 묶음이다. 같은 타입끼리(원본 타입 = 대상 타입)도 한 짝이다."""
    if not isinstance(from_type, str) or not isinstance(to_type, str):
        return None
    return next((b for b in load()["maps"].values() if b["from"]["type"] == from_type and b["to"]["type"] == to_type), None)


def get(mid):
    return load()["maps"].get(mid) if isinstance(mid, str) else None


def put(bundle):
    """묶음을 저장 → 저장한 묶음. 없으면 새로(id 를 만든다 · version 1), 있으면 **기대 version**(묶음의 `version`)이 지금과 같을 때만 고친다 — 아니면 `StaleVersion`.
    있는 묶음 = 묶음의 `id`, id 가 없으면 같은 (원본 타입 → 대상 타입) 짝의 묶음(짝마다 하나). 고칠 때 두 표의 타입은 그대로 둔다(이름 · 보일 이름 · 규칙만 바뀐다).
    ValueError 꼴이 틀림 · version 이 정수가 아님 · 그 짝의 묶음이 이미 있는데 다른 id / KeyError 없는 id / Broken 파일 손상 / OSError 못 씀."""
    body = clean(bundle)
    mid = bundle.get("id")
    if mid is not None and (not isinstance(mid, str) or not _ID.match(mid)):
        raise ValueError("id 가 규칙 묶음의 id 꼴이 아닙니다")
    expect = R.expect_version(bundle.get("version"))
    with _LOCK:
        st = load(strict=True)
        same = next((b for b in st["maps"].values() if b["from"]["type"] == body["from"]["type"] and b["to"]["type"] == body["to"]["type"]), None)
        cur = st["maps"].get(mid) if mid is not None else same
        if mid is not None and cur is None:
            raise KeyError(mid)
        if cur is None:
            if expect is not None:
                raise StaleVersion("그 매핑 규칙이 없습니다(지워졌습니다) — 다시 읽으세요")
            if len(st["maps"]) >= MAPS_MAX:
                raise ValueError(f"매핑 규칙 묶음은 {MAPS_MAX}개까지 저장합니다 — 안 쓰는 것을 지우세요")
            mid = "m" + uuid.uuid4().hex[:10]
            rec = {"id": mid, **body, "version": 1}
        else:
            if expect != cur["version"]:
                raise StaleVersion(f"매핑 규칙이 그 사이 바뀌었습니다(지금 {cur['version']}, 요청 {expect}) — 다시 읽으세요")
            rec = {"id": cur["id"], **body, "from": {**cur["from"], "label": body["from"]["label"] or cur["from"]["label"]},
                   "to": {**cur["to"], "label": body["to"]["label"] or cur["to"]["label"]}, "version": cur["version"] + 1}
        rec["updated"] = round(time.time(), 3)
        st["maps"][rec["id"]] = rec
        _save(st)
        return json.loads(json.dumps(rec))


def delete(mid):
    """묶음을 지운다 → 지운 묶음. 없는 id 는 KeyError · 파일 손상은 Broken."""
    with _LOCK:
        st = load(strict=True)
        if not isinstance(mid, str) or mid not in st["maps"]:
            raise KeyError(mid)
        gone = st["maps"].pop(mid)
        _save(st)
        return gone


# ---- 꺼 둔 값(같은 사양서 ② §7 의 「구분 기준의 값 고르기」 — 「꺼 둔 값을 기억한다」): 표 타입마다 · 규칙 묶음과 따로 ---------------------------------------------------

def clean_offs(offs):
    """꺼 둔 값 {기준: [값 머리의 키 조각…]} 을 정리한 꼴로 — 빈 기준은 빼고, 조각은 처음 나온 차례로 한 번씩(글은 그대로: 키 조각과 꼭 같아야 듣는다). None = 빈 것. 꼴이 틀리면 ValueError."""
    if offs is None:
        return {}
    if not isinstance(offs, dict):
        raise ValueError("offs: {기준: [값의 키 조각…]}")
    extra = [b for b in offs if b not in OFF_BASES]
    if extra:
        raise ValueError(f"offs: 모르는 기준 「{extra[0]}」 — {' · '.join(OFF_BASES)} 가운데")
    out = {}
    for b in OFF_BASES:   # 정해진 차례로
        parts = offs.get(b)
        if parts is None:
            continue
        if not isinstance(parts, (tuple, type([]))) or len(parts) > OFF_PARTS_MAX:
            raise ValueError(f"offs.{b}: {OFF_PARTS_MAX}개 이하의 목록")
        got = []
        for i, x in enumerate(parts):
            if not isinstance(x, str) or not x or len(x) > KEY_MAX:
                raise ValueError(f"offs.{b}[{i}]: 값의 키 조각(글 · {KEY_MAX}자 이하)")
            if x not in got:
                got.append(x)
        if got:
            out[b] = got
    return out


def get_offs(table_type):
    """그 표 타입의 꺼 둔 값 {기준: [키 조각…]} — 없으면 빈 것(타입 꼴이 아니어도 · 파일이 손상되어도 빈 것)."""
    if not isinstance(table_type, str):
        return {}
    return load()["offs"].get(table_type) or {}


def put_offs(table_type, offs):
    """그 표 타입의 꺼 둔 값을 통째로 바꿔 저장 → 저장한 것. 빈 것이면 그 타입을 지운다(지울 것도 없으면 파일을 다시 쓰지 않는다). 규칙 묶음은 그대로 둔다.
    ValueError 타입 · offs 의 꼴이 틀림 · 타입이 너무 많음 / Broken 파일 손상(덮지 않는다) / OSError 못 씀."""
    if not isinstance(table_type, str) or not _TYPE.match(table_type):
        raise ValueError("type: 표 타입(12자리)")
    body = clean_offs(offs)
    with _LOCK:
        st = load(strict=True)
        if body:
            if table_type not in st["offs"] and len(st["offs"]) >= OFFS_MAX:
                raise ValueError(f"꺼 둔 값은 표 타입 {OFFS_MAX}개까지 저장합니다")
            st["offs"][table_type] = body
        elif table_type in st["offs"]:
            st["offs"].pop(table_type)
        else:
            return {}
        _save(st)
        return json.loads(json.dumps(body))
