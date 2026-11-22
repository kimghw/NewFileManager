"""양식의 표 등록부 — 양식(연구개발계획서 · 연차보고서 …)의 표마다 정체 · 구분 기준 자리 · 타입 · 병합 방식 · 서브 테이블을 저장해 다음 작업이 쓴다
(spec_테이블매니저 ② §11 「표 · 띠 정체」 — 2026-11-22 사용자 "표띠, 아이디는 이미 테이블이 소속한 헤딩이 있기 때문에 그걸로 자동으로 둘 수 있다고 봅니다, 사람이 판정하진 않습니다
LLM 이 판정하고 사람은 지침만 제공합니다." · "양식의 테이블은 레지스트리에 구분기준자리나. 기타 테이블 타입/병합 정보, 서브테이블을 저장하고 관리해서 향후 사용할 수 있게해줘").
순수 계산 + 파일 저장 — `app.server` · 세션을 모른다(끝점 app/form_tables_api.py 가 3단계 결과 · 병합 방식 · 엔진 묶음을 넘긴다). 문서를 안 고치고 LLM 도 안 부른다.

- **짓기**(`build`): 등록된 빈 양식 문서의 3단계 결과(LLM 표 판정을 거쳤으면 그 결과 — 판정은 LLM · 사람은 지침만)에서 표마다 항목 하나.
  **표 id** = 양식 열쇠 + 소속 헤딩 사슬의 **정규화 글**(`norm_part` — 「※」 안내 · 대괄호 안의 괄호 · 쌍점 뒤 글 · 빈칸을 빼고, 구분 기준 값의 번호(「1단계」 · 「2차년도」 · 「공동연구개발기관2」)는 N 으로)
  + 같은 소속 아래 차례의 해시(`tf` + 10자) — 사람이 주지 않고, 빈 양식이 같으면 다시 지어도 같다. **띠 id** = 표 id + 「/」 + 띠의 자리 차례 글자(A, B … — 좌표 차례로 다시 매김: LLM 이 준 이름은 안 씀).
  칸 안의 표 = 바깥 표 id + 「›」 + 바깥 표 안의 차례. 구분 기준 값마다 되풀이되는 자리(「(1) 1차년도」 · 「(2) 2차년도」 아래의 같은 차례 표)는 **한 항목**이고 `repeat` = 빈 양식에서 나온 수.
- 항목이 지니는 것 — 값은 안 둔다: 보일 이름 · 사슬(보일 글 · 정규화 글) · 차례 · 행 × 열 · **표 타입**(`table_kv.type_key` — 머리글 지문) · **병합 방식**(`table_kinds.kinds` — 표 · 띠마다) ·
  **구분 기준 자리**(`division` — 소속의 구분 라벨 기준 · 표 안의 구분 칸 기준 · 구분 기준 엔진이 늘리고 줄이는 자리 `engine`[{dim, kind: rows|cols|list|section}]) · **서브 테이블**(`subs` — 띠마다 id · 범위 · 종류 · 헤더 행/열 · 병합 방식 · 구분 기준 · 머리글 몇 개).
- **잇기**(`link`): 다른 문서의 3단계 결과를 등록부에 잇는다(스크립트 몫 — ② §11 「문서의 표를 목록에 잇기」 ⓐ). 문서의 사슬에서 등록부에 없는 줄(작성 글의 줄 「o …」 · 「▪ …」)을 빼고
  (정규화 사슬, 같은 자리 안의 차례)로 찾는다 → 못 찾으면 같은 사슬 안에서 타입이 하나뿐인 항목 → 사슬이 등록부에 없으면 문서 전체에서 타입이 하나뿐인 항목(`sure` 아님) → 여럿이면 `ambiguous`(후보) · 없으면 `unknown`.
  못 정한 것은 LLM 이 고른다(다음 걸음 — 지금은 후보만 보인다). 되풀이 자리는 여러 표가 한 항목에 이어진다(`occ` = 그 항목의 몇 번째).
- 저장: 양식 정보 폴더(`heading_forms.forms_dir()` — 저장소 `forms/` · env `NFM_FORMS`)의 `<양식 열쇠>.tables.json`(양식 정보 md 곁 · 깃으로 관리). 통째 원자적 저장.
  파일이 있는데 못 읽으면 읽기는 `Broken` 을 던진다(덮어쓰지 않는다 — 끝점 409). 지우기는 `<열쇠>.tables.json.removed-<때>` 로 옮긴다(되살리려면 이름을 되돌린다)."""
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

from app import heading_forms as HF
from app import table_kv

VERSION = 1
SUFFIX = ".tables.json"
PART_MAX = 40          # 사슬 한 줄의 정규화 글 길이
SHOW_MAX = 40          # 보일 글 길이
HEADS_MAX = 6          # 띠마다 남기는 머리글 수
CANDS_MAX = 5
ROOT, NONE = "(문서 맨 위)", "(소속 없음)"
HOW = ("path", "type", "typeOnly", "ambiguous", "unknown")
HOW_KO = {"path": "소속 헤딩 · 차례", "type": "소속 헤딩 · 표 타입", "typeOnly": "표 타입만(소속 헤딩이 등록부에 없음)", "ambiguous": "후보 여럿", "unknown": "양식에 없는 표"}
DIM_KO = {"org": "기관", "stage": "단계", "year": "차년도", "stageYear": "단계-차년도", "sub": "세부과제", "period": "연도"}
ENGINE_KO = {"rows": "행", "cols": "열", "list": "목록 행", "section": "절"}
HEAD_ROLES = ("colhead", "rowhead", "corner")
_WS = re.compile(r"\s+")
_BR = re.compile(r"[\[【]([^\[\]【】]*)[\]】]")
_PAREN = re.compile(r"\([^()]*\)|（[^（）]*）")
# 구분 기준 값의 번호가 든 줄 — 그 줄의 숫자는 모두 N(「(1) 1차년도」 · 「[2단계]」 · 「공동연구개발기관2」 · 「기관명 2」). 「2-2. 연구개발기관별 …」 같은 절 번호는 그대로
_DIVISION = re.compile(r"(?:\d+|[Nnx])\s*(?:단\s*계|차\s*년\s*도|년\s*차|연\s*차|차년)|(?:주관|공동|참여)\s*(?:연구개발)?\s*기관|기관\s*명\s*\d")
_DIGITS = re.compile(r"\d+")
_LOCK = threading.RLock()


class Broken(Exception):
    """등록부 파일이 있는데 읽을 수 없다(JSON · 꼴) — 덮어쓰지 않는다."""


# ---- 사슬 ---------------------------------------------------------------------------------------------------------------

def _bracket(m):
    s = _PAREN.sub("", m.group(1))
    s = re.split(r"[:：]", s, maxsplit=1)[0]
    return f"[{s.strip()}]"


def show_part(text):
    """사슬 한 줄의 보일 글 — 「※」 뒤를 떼고 빈칸을 하나로."""
    t = _WS.sub(" ", str(text or "").split("※")[0]).strip()
    return t if len(t) <= SHOW_MAX else t[:SHOW_MAX - 1] + "…"


def norm_part(text):
    """사슬 한 줄의 정규화 글 — 견줄 꼴(문서가 달라도 양식의 같은 헤딩이면 같다).
    「※」 뒤 · 대괄호 안의 괄호 글과 쌍점 뒤 글(기관 이름 · 「기관명 기입」 · 「(20xx~20xx)」)을 떼고 빈칸을 빼며, 구분 기준 값의 번호가 든 줄은 숫자를 N 으로."""
    t = str(text or "").split("※")[0]
    t = _BR.sub(_bracket, t)
    t = _WS.sub("", t)
    if _DIVISION.search(t):
        t = _DIGITS.sub("N", t)
    return t[:PART_MAX]


def chain_of(owner):
    """3단계 결과의 표 소속(`owner`) → [(보일 글, 정규화 글) …](바깥 → 안). 문서 맨 위 · 소속 없음은 한 줄짜리 표식."""
    if not isinstance(owner, dict) or not owner:
        return [(NONE, NONE)]
    if owner.get("root"):
        return [(ROOT, ROOT)]
    parts = [*(owner.get("path") or ()), owner.get("text") or ""]
    out = [(show_part(p), norm_part(p)) for p in parts if isinstance(p, str)]
    out = [(s, n) for s, n in out if n]
    return out or [(NONE, NONE)]


def _key(parts):
    return "›".join(n for _, n in parts)


def table_id(form, key, order, host=None):
    """양식 표 id — (양식 열쇠, 정규화 사슬, 같은 자리 안의 차례)의 해시. 칸 안의 표는 바깥 표 id + 「›」 + 차례."""
    if host:
        return f"{host}›{order}"
    return "tf" + hashlib.sha1(f"{form}\n{key}\n{order}".encode("utf-8")).hexdigest()[:10]


def _letter(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _type_of(tb):
    """3단계 결과의 표 → 표 타입(`table_kv.type_key` — 3단계 칸에는 `textFull` 이 없어 `text` 로 읽는다) | None."""
    try:
        cells = [{**c, "textFull": c.get("textFull") or c.get("text") or ""} for c in tb.get("cells") or () if isinstance(c, dict)]
        return table_kv.type_key({"cells": cells}) if cells else None
    except Exception:  # noqa: BLE001 — 타입을 못 내도 등록부의 다른 값은 낸다
        return None


def _bands(tb):
    """띠 목록을 좌표 차례로 → [(자리 글자, 띠)]."""
    subs = sorted((b for b in tb.get("subtables") or () if isinstance(b, dict)), key=lambda b: (((b.get("rows") or [0])[0]), ((b.get("cols") or [0])[0])))
    return [(_letter(i), b) for i, b in enumerate(subs)]


def _heads(tb, band_id):
    seen, out = set(), []
    for x in sorted((c for c in tb.get("cells") or () if isinstance(c, dict) and c.get("sub") == band_id and c.get("role") in HEAD_ROLES),
                    key=lambda c: (c.get("row") or 0, c.get("col") or 0)):
        t = _WS.sub(" ", str(x.get("text") or "")).strip()[:24]
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= HEADS_MAX:
            break
    return out


# ---- 구분 기준 엔진의 자리 ---------------------------------------------------------------------------------------------------

def engine_places(groups):
    """구분 기준 엔진의 묶음(`core.find` — 판독 결과의 `_groups`) → {표 id: [{dim, kind}]}. 표의 행 · 열 · 목록 행을 늘리는 묶음은 그 표(kind rows|cols|list),
    절이 값마다 한 벌인 묶음은 그 항목 안의 표 모두(kind section)."""
    out = defaultdict(list)

    def put(tid, dim, kind):
        p = {"dim": dim, "kind": kind}
        if tid and p not in out[tid]:
            out[tid].append(p)
    for g in groups or ():
        if not isinstance(g, dict):
            continue
        dim = g.get("dim")
        if g.get("table"):
            put(g["table"], dim, "list" if g.get("list") else g.get("kind") or "rows")
        elif g.get("kind") == "paragraph":
            for it in g.get("items") or ():
                for bid in (it.get("scope") or ()) if isinstance(it, dict) else ():
                    put(bid, dim, "section")
    return dict(out)


# ---- 짓기 ---------------------------------------------------------------------------------------------------------------

def _kind_index(kinds):
    return {k.get("table"): k for k in kinds or () if isinstance(k, dict)}


def _division(tb, places):
    owner = tb.get("owner") if isinstance(tb.get("owner"), dict) else {}
    div = owner.get("division") if isinstance(owner.get("division"), dict) else {}
    labels = [x for x in tb.get("labels") or () if isinstance(x, dict)]
    return {"owner": list(div.get("basis") or ()), "ownerText": show_part(div.get("text")) if div else "",
            "labels": sorted({b for x in labels for b in x.get("basis") or ()}),
            "engine": list(places.get(tb.get("id")) or ())}


def _entry(form, tb, key, parts, order, siblings, kinds, places, entry_of_host=None):
    k = kinds.get(tb.get("id")) or {}
    sub_kind = {s.get("sub"): s for s in k.get("subs") or () if isinstance(s, dict)}
    eid = table_id(form, key, order, entry_of_host)
    subs = []
    for letter, b in _bands(tb):
        s = sub_kind.get(b.get("id")) or {}
        subs.append({"id": f"{eid}/{letter}", "at": letter, "rows": list(b.get("rows") or ()), "cols": list(b.get("cols") or ()), "kind": b.get("kind"),
                     "headerRows": b.get("headerRows"), "headerCols": b.get("headerCols"), "merge": s.get("kind"), "basis": list(s.get("basis") or ()),
                     "axes": list(s.get("axes") or ()), "heads": _heads(tb, b.get("id"))})
    last = parts[-1][0] if parts else NONE
    name = f"칸 안의 표 #{order}" if entry_of_host else (last + (f" #{order}" if siblings > 1 else ""))
    return {"id": eid, "name": name, "title": show_part(tb.get("before")), "path": [s for s, _ in parts], "key": key, "order": order, "host": entry_of_host,
            "rows": tb.get("rows"), "cols": tb.get("cols"), "type": _type_of(tb), "kind": k.get("kind"), "repeat": 1,
            "division": _division(tb, places), "subs": subs, "from": {"tables": [tb.get("id")]}}


def _occ_orders(tables, chain_fn):
    """표마다 (정규화 사슬, 자리 열쇠(보일 글 사슬 — 되풀이의 한 벌), 그 자리 안의 차례, 그 자리의 표 수) — 칸 안의 표가 아닌 것만, 문서 차례."""
    seen, out = Counter(), {}
    rows = []
    for tb in tables:
        parts = chain_fn(tb)
        occ = "›".join(s for s, _ in parts)
        seen[occ] += 1
        rows.append((tb, parts, _key(parts), occ, seen[occ]))
    for tb, parts, key, occ, n in rows:
        out[tb["id"]] = (parts, key, occ, n, seen[occ])
    return out


def _nested(tables):
    """칸 안의 표 → {표 id: (바깥 표 id, 바깥 표 안의 차례)} · 바깥이 칸 안 표면 그 바깥의 바깥이 아니라 바로 바깥 표."""
    cell_tab = {c["id"]: t["id"] for t in tables for c in t.get("cells") or () if isinstance(c, dict) and c.get("id")}
    seen, out = Counter(), {}
    for tb in tables:
        host = cell_tab.get(tb.get("parentCell")) if (tb.get("depth") or 1) > 1 else None
        if host:
            seen[host] += 1
            out[tb["id"]] = (host, seen[host])
    return out


def build(form, t3, *, kinds=(), groups=(), source=None):
    """빈 양식의 3단계 결과 → 등록부 {version, form, source, tables: [항목…], counts}. kinds = 표마다 `table_kinds.kinds` 결과 · groups = 엔진 묶음(`_groups`) · source = 어디서 지었나."""
    tables = [t for t in (t3 or {}).get("tables") or () if isinstance(t, dict) and t.get("id")]
    kinds, places = _kind_index(kinds), engine_places(groups)
    nested = _nested(tables)
    tops = [t for t in tables if t["id"] not in nested]
    occ = _occ_orders(tops, lambda tb: chain_of(tb.get("owner")))
    entries, by_tid, merged = [], {}, {}
    for tb in tops:
        parts, key, _o, n, siblings = occ[tb["id"]]
        slot = (key, n)
        if slot in merged:                       # 구분 기준 값마다 되풀이되는 자리의 같은 차례 표 — 한 항목(repeat +1)
            e = merged[slot]
            e["repeat"] += 1
            e["from"]["tables"].append(tb["id"])
            by_tid[tb["id"]] = e
            continue
        e = _entry(form, tb, key, parts, n, siblings, kinds, places)
        merged[slot] = by_tid[tb["id"]] = e
        entries.append(e)
    inner = {}
    for tb in tables:
        if tb["id"] not in nested:
            continue
        host, n = nested[tb["id"]]
        he = by_tid.get(host)
        if he is None:
            continue
        slot = (he["id"], n)
        if slot in inner:
            if tb["id"] not in inner[slot]["from"]["tables"]:
                inner[slot]["from"]["tables"].append(tb["id"])
            by_tid[tb["id"]] = inner[slot]
            continue
        e = _entry(form, tb, he["key"], chain_of(tb.get("owner")), n, 1, kinds, places, entry_of_host=he["id"])
        inner[slot] = by_tid[tb["id"]] = e
        entries.append(e)
    return {"version": VERSION, "form": form, "source": dict(source or {}), "tables": entries, "counts": counts(entries)}


def counts(entries):
    return {"tables": len(entries), "subs": sum(len(e["subs"]) for e in entries), "repeated": sum(1 for e in entries if e["repeat"] > 1),
            "nested": sum(1 for e in entries if e.get("host")), "engine": sum(1 for e in entries if e["division"]["engine"]),
            "kinds": dict(Counter(e.get("kind") or "none" for e in entries))}


# ---- 잇기 ---------------------------------------------------------------------------------------------------------------

def skeleton(reg):
    """등록부의 사슬에 나오는 정규화 글 모두 — 문서의 사슬에서 이 밖의 줄(작성 글의 줄)은 뺀다."""
    return {p for e in (reg or {}).get("tables") or () for p in str(e.get("key") or "").split("›") if p}


def link(reg, t3):
    """문서의 3단계 결과를 등록부에 잇는다 → {links: {문서 표 id: {id, name, how, sure, occ, cands}}, missing: [어느 표에도 안 이어진 항목 id], counts{how: n}}."""
    entries = [e for e in (reg or {}).get("tables") or () if isinstance(e, dict)]
    tops_e = [e for e in entries if not e.get("host")]
    by_slot = {(e["key"], e["order"]): e for e in tops_e}
    by_key = defaultdict(list)
    for e in tops_e:
        by_key[e["key"]].append(e)
    by_type = defaultdict(list)
    for e in tops_e:
        if e.get("type"):
            by_type[e["type"]].append(e)
    inner_e = {(e["host"], e["order"]): e for e in entries if e.get("host")}
    keep = skeleton(reg)
    tables = [t for t in (t3 or {}).get("tables") or () if isinstance(t, dict) and t.get("id")]
    nested = _nested(tables)
    tops = [t for t in tables if t["id"] not in nested]

    def chain(tb):
        parts = chain_of(tb.get("owner"))
        kept = [(s, n) for s, n in parts if n in keep]
        return kept or parts
    occ = _occ_orders(tops, chain)
    links, used = {}, Counter()

    def put(tb, e, how, sure, cands=()):
        if e is not None:
            used[e["id"]] += 1
        links[tb["id"]] = {"id": e["id"] if e else None, "name": e["name"] if e else None, "how": how, "sure": bool(sure),
                           "occ": used[e["id"]] if e else 0, "cands": [c["id"] for c in cands][:CANDS_MAX]}
    for tb in tops:
        parts, key, _o, n, _s = occ[tb["id"]]
        typ = _type_of(tb)
        e = by_slot.get((key, n))
        if e is not None:
            put(tb, e, "path", e.get("type") == typ)
            continue
        same = [x for x in by_key.get(key, ()) if typ and x.get("type") == typ]
        if len(same) == 1:
            put(tb, same[0], "type", True)
            continue
        if key not in by_key:
            anyw = by_type.get(typ, []) if typ else []
            if len(anyw) == 1:
                put(tb, anyw[0], "typeOnly", False)
                continue
            if len(anyw) > 1:
                put(tb, None, "ambiguous", False, anyw)
                continue
        cands = same or by_key.get(key, ())
        put(tb, None, "ambiguous" if cands else "unknown", False, cands)
    for tb in tables:
        if tb["id"] not in nested:
            continue
        host, n = nested[tb["id"]]
        hl = links.get(host)
        e = inner_e.get((hl["id"], n)) if hl and hl["id"] else None
        put(tb, e, "path" if e else "unknown", bool(e) and bool(hl and hl["sure"]))
    missing = [e["id"] for e in entries if not used[e["id"]]]
    return {"links": links, "missing": missing, "counts": dict(Counter(v["how"] for v in links.values()))}


# ---- 저장 ---------------------------------------------------------------------------------------------------------------

def path_of(key):
    """등록부 파일 Path | None(양식 정보 폴더가 꺼짐). 열쇠가 잘못이면 ValueError."""
    HF.check_key(key)
    d = HF.forms_dir()
    return d / f"{key}{SUFFIX}" if d is not None else None


def _valid(data):
    return isinstance(data, dict) and data.get("version") == VERSION and isinstance(data.get("tables"), list) and all(
        isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("subs"), list) for e in data["tables"])


def load(key):
    """등록부 dict | None(없음 · 폴더 꺼짐). 파일이 있는데 못 읽으면 Broken."""
    p = path_of(key)
    if p is None or not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as e:
        raise Broken(f"양식의 표 등록부 파일({p.name})을 읽지 못했습니다: {e}") from e
    if not _valid(data):
        raise Broken(f"양식의 표 등록부 파일({p.name})의 꼴이 맞지 않습니다")
    return data


def save(key, reg):
    """등록부를 통째로 쓴다(원자적) → 쓴 dict. 폴더가 꺼져 있으면 ValueError · 있는 파일이 깨졌으면 Broken(덮지 않는다)."""
    p = path_of(key)
    if p is None:
        raise ValueError("양식 정보 폴더가 꺼져 있어 등록부를 저장할 수 없습니다(NFM_FORMS=off)")
    with _LOCK:
        load(key)                      # 깨진 파일이면 Broken — 덮어쓰지 않는다
        data = {**reg, "form": key, "at": round(time.time(), 3)}
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
                f.write("\n")
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return data


def remove(key):
    """등록부를 `<열쇠>.tables.json.removed-<때>` 로 옮긴다 → 옮긴 파일 이름 | None(없음)."""
    p = path_of(key)
    if p is None or not p.is_file():
        return None
    with _LOCK:
        dst = p.with_name(f"{p.name}.removed-{time.strftime('%Y%m%d-%H%M%S')}")
        os.replace(p, dst)
    return dst.name


def summary(reg):
    """등록부 → 화면에 보일 요약(항목 빼고)."""
    if not reg:
        return None
    return {"form": reg.get("form"), "at": reg.get("at"), "source": reg.get("source") or {}, "counts": reg.get("counts") or counts(reg.get("tables") or [])}
