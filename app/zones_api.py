"""편집 구역 — 끝점 · 세션 저장 · 실행 취소 · 취합 출처의 접점(spec_구역 ② §3 「지정 — 사람이 고른 블록」 · §4 「출처 — 취합으로 들어온 내용」 · §5 「응답」 · §7 「저장 · 읽는 길 · 등록」).
계산은 app/zones.py(순수 — 세션을 모른다). 이 모듈은 `app.server` 를 함수 안에서만 가져온다(server 가 이 모듈을 include_router 로 읽는다).

- `GET    /api/docs/{id}/zones` → {rev, zonesRev, basis, options, orgs, stages, blocks, cells, zones, marks, origins, counts, reasons}(§5). 문서는 안 바뀐다.
- `POST   /api/docs/{id}/zones/marks` `{ids, label, note?, docRev, zonesRev}` → 위 꼴(지정 하나 더함 — 그 블록은 다른 지정에서 빠진다).
- `PUT    /api/docs/{id}/zones/marks/{mid}` `{label?, note?, ids?, docRev, zonesRev}` → 위 꼴(준 것만 바꾼다).
- `DELETE /api/docs/{id}/zones/marks/{mid}?zonesRev=n` → 위 꼴(지정 해제).
  오류 꼴 = detail {reason, message}: 409 staleDoc(문서 편집 차례가 다름) · staleZones(구역 판이 다름) · 400 badMark(대상이 본문 최상위 문단·표가 아님 · 값이 틀림 · 지정할 수 없는 문서) · 404 noMark.
  지정은 문서를 안 바꾼다 — 편집 차례(rev)를 올리지 않고(`_bump` 없음: 분석이 낡지 않는다) 실행 취소 대상도 아니다. 구역 판(`zones.rev`)만 +1 하고 작업에 저장한다.

세션 `s.zones = {rev, marks[], origins[]}`(작업 폴더 `state.json` 의 `zones`) — server.py 의 접점: Session.__init__(blank 꼴) · _persist · _restore_state(load) · _snap(snap) · _rollback(rollback) ·
_transact(after_edit) · commit_restore(prune). 출처 이벤트는 취합 반영·끌어 넣기의 그 편집(run()) 안에서 `origin_add` 로 적는다 — 실행 취소 묶음에 들어 함께 돌아간다.

자동 판독(zones.read)은 문서마다 하나 읽어 둔다(메모리 — 열쇠: 문서 차례 · 기준 확정 · 값 · 값의 근거 · 분석 실행 번호 · 추가한 자리 · 앞서 반영한 값). 옵션·지정·출처는 늘 새로 입힌다(zones.build)."""
import copy
import json
import logging
import threading
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException

from app import heading_runs as HR
from app import works, zones

router = APIRouter()
log = logging.getLogger("uvicorn.error")   # 서버 로그(server.py 와 같은 것)

# 지정을 잇는 편집(server._transact 의 op) — 문단 나눔(Enter · 공유 손님의 줄 나누기도 이 끝점) · 개요 줄의 새 줄(Enter · Alt+Enter 가 만든 줄). 사람이 그 자리에서 글을 이어 쓰는 보통 편집뿐이다.
# 넣지 않는 것: 구분 기준 반영(divisions) · 취합(gatherFill · gatherDrop) · 이관 넣기(mergeFill) · 서식 적용(styleApply) · 에이전트 제안 반영(agentApply) · 표 만들기·나누기(새 표는 「나온 문단」 기록이 없다) —
# 다른 곳의 내용을 들여오거나 틀을 되풀이하는 편집이 만든 블록은 누구 것인지 이 기록으로 알 수 없다(§3).
INHERIT_OPS = frozenset({"split", "outline"})

AUTO_MAX, NOTE_MAX = 16, 200   # 읽어 둔 자동 판독은 문서 이만큼까지(오래된 것부터 버림) · 메모 길이
VIEW_KEYS = ("blocks", "cells", "zones", "marks", "origins", "counts")
MSG = {"staleDoc": "문서가 바뀌었습니다 — 구역을 다시 읽은 뒤 지정하세요", "staleZones": "구역 지정이 다른 곳에서 바뀌었습니다 — 다시 읽은 뒤 지정하세요",
       "badMark": "구역으로 지정할 수 없습니다", "noMark": "그런 지정이 없습니다(이미 해제했을 수 있습니다)"}
_LOCK = threading.Lock()
_AUTO = {}   # 문서 id → (열쇠, 자동 판독 info)


def _err(status, code, message=None):
    return HTTPException(status, {"reason": code, "message": message or MSG.get(code) or code})


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _int(x):
    return isinstance(x, int) and not isinstance(x, bool)


# ---- 세션 저장 · 실행 취소(server.py 가 부른다 — 세션 잠금 안) --------------------------------------------------------

def blank():
    return {"rev": 0, "marks": [], "origins": []}


def load(value):
    """state.json 의 "zones" 값 → 정리한 사전 — 꼴이 틀리면 blank()(옛 작업에는 키가 없다). 못 읽는 지정·출처 한 줄은 그 줄만 버린다."""
    if not isinstance(value, dict) or not isinstance(value.get("marks"), list) or not isinstance(value.get("origins"), list):
        return blank()
    strs = lambda xs: [i for i in xs if isinstance(i, str) and i]  # noqa: E731
    marks = [{**copy.deepcopy(m), "ids": strs(m["ids"])} for m in value["marks"]
             if isinstance(m, dict) and isinstance(m.get("id"), str) and isinstance(m.get("ids"), list) and isinstance(m.get("label"), dict)]
    origins = [{**copy.deepcopy(e), "ids": strs(e["ids"]), "orgs": strs(e.get("orgs") or []) if isinstance(e.get("orgs"), list) else []} for e in value["origins"]
               if isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("ids"), list)]
    rev = value.get("rev")
    return {"rev": rev if _int(rev) and rev >= 0 else 0, "marks": [m for m in marks if m["ids"]], "origins": origins}


def snap(s):
    """실행 취소 묶음에 넣을 것(server._snap) — 출처 이벤트의 깊은 사본. 지정은 넣지 않는다(실행 취소 대상이 아니다 — §3)."""
    return copy.deepcopy(s.zones["origins"]) if s.zones["origins"] else []


def _attached(s, i):
    el = s.doc._ids.get(i)
    return el is not None and s.doc._attached(el)


def _num(i):
    """블록 id(p|t|c|i + 문서 전체 한 번호)의 번호 — 못 읽으면 None."""
    d = "".join(ch for ch in str(i) if ch.isdigit())
    return int(d) if d else None


def _prune_marks(s, reused_only=False):
    """지금 문서에 붙어 있지 않은 블록 id 를 지정에서 뺀다 → 바뀌었나(§3).
    reused_only(실행 취소·되돌림 뒤) = **되돌린 문서의 번호표(doc._n)보다 뒤에 매겨진 id 만** 뺀다 — 그 번호는 다음 새 블록에 다시 쓰여 옛 지정을 물려받는다(astra P1).
    번호표 안쪽의 id 는 다시 쓰이지 않으므로 지금 없어도 남긴다(지운 블록 — 실행 취소를 더 하면 같은 id 로 돌아온다: 응답에서는 gone 으로 센다)."""
    z = s.zones
    if not z["marks"]:
        return False
    top = getattr(s.doc, "_n", None) if reused_only else None
    keep = (lambda i: (n := _num(i)) is not None and n <= top) if _int(top) else (lambda i: False)
    alive = {i for m in z["marks"] for i in m.get("ids") or () if _attached(s, i) or keep(i)}
    marks, n = zones.marks_prune(z["marks"], alive)
    if n:
        z["marks"] = marks
    return bool(n)


def rollback(s, origins):
    """server._rollback 뒤(문서를 되돌린 다음) — 출처를 그 묶음의 것으로 되돌리고, 되돌린 문서의 번호표보다 뒤에 매겨진 id(다시 쓰일 번호)를 지정에서 뺀다. 바뀌었으면 구역 판 +1.
    origins None = 이 키가 생기기 전의 실행 취소 묶음 — 출처는 그대로 두고 지정만 정리한다."""
    z, changed = s.zones, False
    if origins is not None and origins != z["origins"]:
        z["origins"], changed = copy.deepcopy(origins), True
    if _prune_marks(s, reused_only=True) or changed:
        z["rev"] += 1


def prune(s):
    """확정 복원(server.commit_restore) 뒤 — 되돌린 문서에 없는 id 를 지정·출처에서 정리한다(남은 id 가 없는 지정·출처는 지운다). 바뀌었으면 구역 판 +1."""
    z = s.zones
    changed, keep = _prune_marks(s), []
    for e in z["origins"]:
        ids = [i for i in e.get("ids") or () if _attached(s, i)]
        if len(ids) != len(e.get("ids") or ()):
            changed = True
        if ids:
            keep.append({**e, "ids": ids})
    if changed:
        z["origins"] = keep
        z["rev"] += 1


def after_edit(s, op, born):
    """server._transact 성공 뒤(_bump 앞) — 보통 편집(INHERIT_OPS)이 만든 새 본문 문단은 그 문단이 나온 문단의 지정에 잇는다(§3 「범위는 고른 id 그대로」 — 편집이 알려 준 새 블록만).
    born = {새 문단 id: 나온 문단 id}(server 의 s.origin 에 방금 적힌 것). 칸 안·캡션의 새 문단은 지정 대상이 아니라 뺀다. 지정도 출처도 없으면 아무 일도 안 한다(편집마다 불린다).
    출처 이벤트도 같은 편집에서 잇는다 — 취합으로 들어온 문단을 **나눈 뒷부분**(글이 든 새 문단)만(§4)."""
    z = s.zones
    if not (z["marks"] or z["origins"]) or not born or op not in INHERIT_OPS or s.fmt != "hwpx":
        return
    doc, para = s.doc, s.kit["para"]
    secs = set(doc._sections)

    def body(i):   # 지금 본문 최상위 문단인가(구역 바로 아래 hp:p)
        el = doc._ids.get(i)
        return el is not None and el.tag == para and el.getparent() in secs
    born = {i: o for i, o in born.items() if isinstance(o, str) and body(i)}
    if not born:
        return
    if len(born) > 1:   # 문서 차례로 잇는다 — born 은 집합에서 와 차례가 없다(한 줄에서 여럿이 나오는 편집: 사이 줄 + 새 줄 · 같은 레벨 뼈대)
        sec = {x: k for k, x in enumerate(doc._sections)}
        at = lambda i: (sec[doc._ids[i].getparent()], doc._ids[i].getparent().index(doc._ids[i]))  # noqa: E731
        born = dict(sorted(born.items(), key=lambda kv: at(kv[0])))
    try:
        n = zones.inherit(z["marks"], born) if z["marks"] else 0
        # 출처(§4 — astra 결과 검토 10): 취합으로 들어온 문단을 나누면 뒷부분도 그 기관 문서에서 온 내용이다 — **글이 든 새 문단만** 그 출처 이벤트에 잇는다.
        # 빈 새 줄(문단 끝에서 Enter · 개요의 새 줄)은 사람이 이제 쓸 자리라 잇지 않는다. 출처는 실행 취소 묶음에 들어 있어(snap) 이 편집을 되돌리면 함께 돌아간다
        full = {i: o for i, o in born.items() if (s.texts.get(i) or "").strip()} if z["origins"] else {}
        n += zones.inherit(z["origins"], full) if full else 0
        if n:
            z["rev"] += 1
    except Exception as e:  # noqa: BLE001 — 지정을 잇지 못해도 편집은 끝낸다(문서는 이미 바뀌었다 — 여기서 던지면 편집 차례·기록이 빠진다)
        log.warning("[편집 구역] %s 지정·출처를 잇지 못함(%s): %r", s.id, op, e)


def origin_add(s, part, name, orgs, kind, ids, key=None):
    """출처 이벤트 하나를 더한다 → 이벤트 id(§4). **그 내용을 넣는 편집의 run() 안에서**(세션 잠금 안) 부른다 — server._snap 이 run() 앞의 출처를 붙들고 있어
    그 편집이 되돌려지면(표준 검사 실패 · 실행 취소) 이벤트도 함께 사라진다. name·orgs = 그때의 기관 문서 이름·반영할 기관(굳혀 둔다 — 뒤에 바뀌어도 그대로)."""
    ev = zones.origin_event(part, name, [o for o in orgs or () if isinstance(o, str)], kind, [i for i in ids or () if isinstance(i, str)], key, _now())
    s.zones["origins"].append(ev)
    s.zones["rev"] += 1
    return ev["id"]


# ---- 읽기(§5) ---------------------------------------------------------------------------------------------------

def _run(x):
    return ((x or {}).get("meta") or {}).get("run")


def _j(x):
    return None if x is None else json.dumps(x, ensure_ascii=False, sort_keys=True, default=str)


def _taken(s):
    """(세션 잠금 안) 계산에 쓸 것을 뜬다 — 블록 목록(그때의 목록 그대로: 고치면 문서가 새 목록을 만든다) · 값(반영한 값 → 입력 값) · 분석 · 추가한 자리 · 앞서 반영한 값 · 구역의 사본.
    계산(zones.read — 큰 문서에서 1초 안팎)은 잠금 밖에서 한다(merge_gather_api.gather_zones 와 같은 방식)."""
    from app import server
    server._project_settings_sync(s)
    d, hwpx = s.division, s.fmt == "hwpx"
    applied = (d.get("applied") or {}).get("values")
    raw = (applied or (d.get("settings") or {}).get("values")) if hwpx else None
    t = {"id": s.id, "rev": s.rev, "base": s.base_n, "hwpx": hwpx, "raw": raw, "basis": ("applied" if applied else "settings") if raw else None,
         "blocks": s.doc.blocks(), "zones": copy.deepcopy(s.zones), "graph": None, "tables": None, "runs": (None, None), "hints": [], "prior": None}
    if hwpx:
        g, tb = HR.graph(s), HR.tables(s)
        t.update(graph=g, tables=tb, runs=(_run(g), _run(tb)), hints=copy.deepcopy(d.get("hints") or []), prior=copy.deepcopy(server._division_prior(s)))
    from app import division_scan_api as DSA
    t["dv"] = DSA.inputs(s, t["blocks"]) if hwpx else None   # 구분 기준 판독의 입력(spec_구분_기준 ② §23) — 자동 판독의 묶음 · 표 안 값 읽기는 그 판독에서 받는다
    if hwpx and t["dv"] is None:   # 연구개발과제 문서가 아님 — 구분 기준 엔진을 쓰지 않는다(2026-11-18 사용자 "연구개발과제 에서만 구분 기준엔진을 쓸거야")
        t.update(raw=None, basis=None)
    return t


def _auto(t):
    """자동 판독 → (info, 값 | None, basis | None) — 열쇠(모듈 설명)가 같으면 읽어 둔 것. 값을 못 읽으면(꼴이 틀림) 값 없음으로 본다."""
    values = None
    if t["raw"]:
        from app.division_profiles.rnd import core
        try:
            values = core.norm_values(t["raw"])
        except (KeyError, TypeError, ValueError):
            values = None
    basis = t["basis"] if values is not None else None
    dv = t.get("dv") if values is not None else None
    key = (t["rev"], t["base"], _j(values), basis, tuple(t["runs"]), _j(t["hints"]), _j(t["prior"]), dv["key"] if dv else None)
    with _LOCK:
        hit = _AUTO.get(t["id"])
    if hit is not None and hit[0] == key:
        return hit[1], values, basis
    scan = None
    if dv is not None:   # 구분 기준 판독(읽어 둔 것 · 없으면 여기서 — 같은 입력이면 다른 길이 이미 센 것을 쓴다)
        from app import division_scan_api as DSA
        scan = (DSA.peek(dv) or DSA.compute(dv))["result"]
    info = zones.read({"blocks": t["blocks"], "values": values, "graph": t["graph"], "tables": t["tables"], "hints": t["hints"], "prior": t["prior"], "scan": scan})
    with _LOCK:
        _AUTO.pop(t["id"], None)
        _AUTO[t["id"]] = (key, info)
        while len(_AUTO) > AUTO_MAX:
            del _AUTO[next(iter(_AUTO))]
    return info, values, basis


def _work(doc_id):
    return works.work(doc_id) or {"id": doc_id, "task": None}   # 작업 저장이 꺼졌거나 작업이 없음 — 옵션은 기본값


def _respond(t, auto=None):
    """뜬 것(t) → §5 의 꼴 + 밑줄 키(`_tableOf`·`_info` — zones.label_of 가 쓴다: 끝점은 뺀다). 잠금 밖에서."""
    from app import task_options
    info, values, basis = auto or _auto(t)
    w = _work(t["id"])
    opts = task_options.resolve(w)
    origins = list(t["zones"]["origins"])
    if t["hwpx"] and (w.get("task") or {}).get("job") == "plan_merge":   # 취합 TASK 의 문서 — 출처 이벤트가 생기기 전에 넣은 옛 기록도 출처로(§4 — legacy)
        from app import merge_gather_api
        origins += merge_gather_api.legacy_origins(t["id"])
    view = zones.build(info, t["zones"]["marks"], origins, opts["zones"]["dims"])
    reasons = (["unsupportedForm"] if not t["hwpx"] else ["noValues"] if values is None else []) + ([] if opts.get("offered") else ["notOffered"])
    out = {"rev": t["rev"], "zonesRev": t["zones"]["rev"], "basis": basis, "options": opts, "orgs": info.get("orgs") or [], "stages": info.get("stages") or [],
           **{k: view[k] for k in VIEW_KEYS}, "reasons": reasons, **{k: v for k, v in view.items() if k.startswith("_")}}
    if not t["hwpx"]:   # hwpx 가 아니면 구역을 내지 않는다(지정·출처는 그대로 싣는다)
        out.update(blocks={}, cells={}, zones=[], counts={**view["counts"], "zones": 0, "blocks": 0, "cells": 0, "conflicts": 0, "unknown": 0})
    return out


def read(s):
    """GET 의 몸통(§5 의 꼴 + 밑줄 키) — 세션 잠금은 이 함수가 잡는다. 다른 모듈이 읽는 길: `zones.label_of(zones_api.read(sess), 블록·칸 id)`(§7)."""
    with s.lock:
        t = _taken(s)
    return _respond(t)


def _public(out):
    return {k: v for k, v in out.items() if not k.startswith("_")}


@router.get("/api/docs/{doc_id}/zones")
def zones_get(doc_id: str):
    from app import server
    return _public(read(server._sess(doc_id)))


# ---- 지정(§3) ---------------------------------------------------------------------------------------------------

def _fresh(t, doc_rev, zones_rev, doc=True):
    """낡은 화면의 선택으로 지정하지 않는다 — 문서 편집 차례(docRev) · 구역 판(zonesRev)이 지금과 같아야 한다."""
    if (doc and not _int(doc_rev)) or not _int(zones_rev):
        raise _err(400, "badMark", "docRev(문서 편집 차례) · zonesRev(구역 판)가 있어야 합니다" if doc else "zonesRev(구역 판)가 있어야 합니다")
    if doc and doc_rev != t["rev"]:
        raise _err(409, "staleDoc")
    if zones_rev != t["zones"]["rev"]:
        raise _err(409, "staleZones")


def _markable(t):
    """지정할 수 있는 문서인가 — 연구개발 TASK 의 hwpx 문서(spec_구역 ② §0)."""
    from app import task_options
    if not t["hwpx"]:
        raise _err(400, "badMark", "hwpx 문서에서만 구역을 지정할 수 있습니다")
    if not task_options.resolve(_work(t["id"])).get("offered"):
        raise _err(400, "badMark", "연구개발 워크플로우의 문서에서만 구역을 지정할 수 있습니다")


def _why_not(i, info, blocks):
    """지정할 수 없는 id 의 까닭(사람에게 보일 글) — 본문 최상위 문단·표만 지정한다(칸·그림은 대상이 아니다 — §3)."""
    if (info.get("kinds") or {}).get(i) == "pic":
        return "그림은 구역으로 지정할 수 없습니다 — 그 앞뒤의 문단을 지정하세요"
    for b in blocks:
        if b.get("id") == i:
            return "캡션은 구역으로 지정할 수 없습니다 — 그 표를 지정하세요" if b.get("captionOf") else "구역으로 지정할 수 없는 블록입니다"
        for c in b.get("cells") or ():
            if c.get("id") == i:
                return "표 칸은 구역으로 지정할 수 없습니다 — 그 표를 지정하세요"
            if any(x.get("id") == i for x in c.get("blocks") or ()):
                return "표 칸 안의 문단은 구역으로 지정할 수 없습니다 — 그 표를 지정하세요"
    return "문서에 없는 블록입니다 — 문서가 바뀌었으면 다시 읽어 주세요"


def _targets(ids, info, blocks):
    """지정 대상 → 지금 문서의 본문 최상위 문단·표 id(문서 차례 · 중복 없음). 아니면 400 badMark."""
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        raise _err(400, "badMark", "ids 는 지정할 문단·표의 id 목록이어야 합니다")
    pos, kinds = {i: k for k, i in enumerate(info.get("order") or ())}, info.get("kinds") or {}
    ids = list(dict.fromkeys(ids))
    bad = next((i for i in ids if i not in pos or kinds.get(i) not in ("p", "tbl")), None)
    if bad is not None:
        raise _err(400, "badMark", _why_not(bad, info, blocks))
    return sorted(ids, key=pos.__getitem__)


def _label(raw, info, values):
    """지정 값 검증(zones.norm_label) — 프로젝트 구성 값이 없는 문서에서는 지정하지 않는다(기관 목록 · 단계·차년도 범위가 없다)."""
    if values is None:
        org = not isinstance(raw, dict) or "org" in raw or not any(k in raw for k in zones.DIMS)
        raise _err(400, "badMark", "프로젝트 구성 값이 없어 기관을 지정할 수 없습니다" if org else "프로젝트 구성 값이 없어 단계·차년도를 지정할 수 없습니다")
    try:
        return zones.norm_label(raw, info)
    except (ValueError, TypeError, KeyError) as e:
        raise _err(400, "badMark", str(e) or None) from e


def _note(x):
    if x is None:
        return ""
    if not isinstance(x, str):
        raise _err(400, "badMark", "메모는 글이어야 합니다")
    return " ".join(x.split())[:NOTE_MAX]


def _saved(s, t, auto, op, mark):
    """지정을 바꾼 뒤(잠금 밖) — 작업에 저장 · 작업 기록 한 줄 · §5 의 응답. 문서 편집 차례는 안 올린다."""
    from app import server
    server._persist_safe(s, force=True)
    works.log(s.id, "zoneMark", op=op, id=mark["id"], blocks=len(mark.get("ids") or ()), label=mark.get("label"))
    return _public(_respond(t, auto))


@router.post("/api/docs/{doc_id}/zones/marks")
def zones_mark_add(doc_id: str, body: dict = Body(...)):
    """지정 하나 더하기 {ids, label{org?, stage?, year?}, note?, docRev, zonesRev} — 고른 블록 id 그대로(사이의 블록을 끼워 넣지 않는다). 한 블록은 한 지정에만: 새 지정이 가져간 블록은 옛 지정에서 빠진다."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
        _fresh(t, body.get("docRev"), body.get("zonesRev"))
        _markable(t)
        auto = _auto(t)   # 화면이 같은 차례에서 이미 읽었으면 읽어 둔 것 — 아니면 여기서 센다(잠금 안)
        ids = _targets(body.get("ids"), auto[0], t["blocks"])
        mark = zones.mark_make(ids, _label(body.get("label"), auto[0], auto[1]), _note(body.get("note")), "user", _now())
        s.zones["marks"] = zones.marks_put(s.zones["marks"], mark)
        s.zones["rev"] += 1
        t["zones"] = copy.deepcopy(s.zones)
    return _saved(s, t, auto, "add", mark)


@router.put("/api/docs/{doc_id}/zones/marks/{mid}")
def zones_mark_edit(doc_id: str, mid: str, body: dict = Body(...)):
    """지정 고치기 {label?, note?, ids?, docRev, zonesRev} — 준 것만 바꾼다(label 은 통째로). ids 를 주면 지금 문서의 본문 최상위 문단·표여야 한다. 고친 지정은 사람의 것(by user)이 된다."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
        _fresh(t, body.get("docRev"), body.get("zonesRev"))
        old = next((m for m in s.zones["marks"] if m.get("id") == mid), None)
        if old is None:
            raise _err(404, "noMark")
        if not any(k in body for k in ("label", "note", "ids")):
            raise _err(400, "badMark", "바꿀 것(label · note · ids)이 없습니다")
        _markable(t)
        auto = _auto(t)
        ids = _targets(body["ids"], auto[0], t["blocks"]) if "ids" in body else list(old.get("ids") or ())
        label = _label(body["label"], auto[0], auto[1]) if "label" in body else old["label"]
        note = _note(body["note"]) if "note" in body else old.get("note") or ""
        mark = {**zones.mark_make(ids, label, note, "user", _now()), "id": mid}   # 이 끝점으로 고치는 것은 사람이다 — LLM 이 지정한 것(by llm)도 사람이 고치면 사람의 지정이 된다(「LLM 지정 모두 해제」 에 함께 지워지지 않게: spec_구역 ② §8)
        s.zones["marks"] = zones.marks_put(s.zones["marks"], mark)
        s.zones["rev"] += 1
        t["zones"] = copy.deepcopy(s.zones)
    return _saved(s, t, auto, "edit", mark)


@router.delete("/api/docs/{doc_id}/zones/marks/{mid}")
def zones_mark_delete(doc_id: str, mid: str, zonesRev: int | None = None):   # noqa: N803 — 쿼리 이름(spec_구역 ② §3)
    """지정 해제 — 그 블록들은 자동 판독 값으로 돌아간다."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
        _fresh(t, None, zonesRev, doc=False)
        old = next((m for m in s.zones["marks"] if m.get("id") == mid), None)
        if old is None:
            raise _err(404, "noMark")
        s.zones["marks"] = [m for m in s.zones["marks"] if m.get("id") != mid]
        s.zones["rev"] += 1
        t["zones"] = copy.deepcopy(s.zones)
    return _saved(s, t, None, "delete", old)


# ---- LLM 검토(spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」) — 계산·계약은 app/zones_llm.py -------------------------------
# - `GET    /api/docs/{id}/zones/llm` → {available, why, running, candidates, kinds{conflict, unknown, hint, alone}, truncated, last{at, candidates, marked, kept, dropped, summary, error} | null}
#   — 보낼 후보 미리 보기(LLM 을 부르지 않는다 · 문서도 구역도 안 바뀐다).
# - `POST   /api/docs/{id}/zones/llm` `{docRev, zonesRev}` → §5 의 응답 + llm{candidates, marked, kept, dropped, summary, truncated, call{model, ms, costUsd, error}}
#   — 후보가 없으면 호출 없이 llm{nothing: true, candidates: 0}. candidates = marked + kept(지정으로 적은 후보 + 그대로 둔 후보) · dropped = 검증에서 버린 답의 수.
#   오류 꼴 = detail {reason, message}: 409 staleDoc · staleZones(호출 앞 · 호출 뒤 둘 다 본다) · 409 busy(이 문서의 검토가 도는 중) · 409 noLlm · 502 llmFailed(지정은 안 바뀐다).
# - `DELETE /api/docs/{id}/zones/marks?by=llm&zonesRev=n` → §5 의 응답(LLM 이 지정한 것만 모두 해제 — 하나도 없으면 그대로 200).
# 흐름(server.divisions_llm_review 와 같은 길): 세션 잠금 안에서 자료를 뜨고 → 잠금 밖에서 후보를 고르고 한 번 호출 → 다시 잠금 안에서 문서 · 분석 · 프로젝트 구성 · 구역 판이 그대로일 때만
# 후보마다 지정 하나(`by: "llm"` · ids = 그 후보 하나 · note = 까닭)로 적는다. 사람이 지정한 블록(과 앞선 검토가 지정한 블록)은 후보가 아니라 건드리지 않는다.
# 마지막 결과·프롬프트·답은 작업 폴더 `zones/llm-last.json`(화면 「지침」 = merge_api.llm_guide 의 step zones · 에이전트가 읽는 로그 = work_logs 의 zones). 작업 기록 `zoneLlm`.

LLM_MSG = {"busy": "이 문서의 편집 구역 LLM 검토가 이미 돌고 있습니다 — 끝난 뒤 다시 하세요", "noLlm": "LLM 을 쓸 수 없습니다 — 서버의 LLM 연결이 꺼져 있거나 없습니다",
           "llmFailed": "편집 구역 LLM 검토에 답을 못 받았습니다", "docMoved": "검토하는 동안 문서(또는 분석 · 프로젝트 구성)가 바뀌어 결과를 반영하지 않았습니다 — 다시 검토하세요",
           "zonesMoved": "검토하는 동안 구역 지정이 바뀌어 결과를 반영하지 않았습니다 — 다시 검토하세요", "byLlm": "by=llm 만 받습니다 — LLM 이 지정한 것만 한꺼번에 해제합니다"}
LLM_LAST_KEYS = ("at", "candidates", "marked", "kept", "dropped", "summary", "error")   # 미리 보기의 last 에 싣는 것
LLM_TITLE = "편집 구역 LLM 검토"
_LLM_RUN = set()    # 검토가 도는 중인 문서 id(메모리만 — _LOCK 안에서)
_LLM_LAST = {}      # 작업 저장이 꺼졌을 때의 zones/llm-last.json


def llm_last(wid):
    """마지막 LLM 검토의 기록(작업 폴더 `zones/llm-last.json`) | None — {at, t, rev, zonesRev, candidates, kinds, truncated, marked, kept, dropped, summary, error, items[{id, type, kind, label, reason, keep, mark}],
    droppedRows[{id, dim?, value?, why}], call, guide, units[{n, title, pages, targets, tables, error, prompt, answer}]}. units 는 화면 「지침」 이 읽는 꼴(merge_api._guide_units — 한 번 호출이라 단위 하나)."""
    d = works.folder(wid)
    if d is None:
        return _LLM_LAST.get(wid)
    p = d / "zones" / "llm-last.json"
    got = works._read_json(p) if p.is_file() else None
    return got if isinstance(got, dict) else None


def _llm_keep(wid, rec):
    if works.add_detail(wid, "zones", "llm-last", rec) is None:   # 작업 저장이 꺼져 있다 — 메모리에
        _LLM_LAST[wid] = rec


def _llm_cands(t, out):
    """보낼 후보 → (자른 뒤의 후보 — 문서 차례, 잘렸나). 구역을 내지 않는 문서(hwpx 아님 · 프로젝트 구성 값 없음 · 연구개발 문서 아님 — out 의 reasons)에는 후보가 없다."""
    from app import zones_llm
    if out["reasons"]:
        return [], False
    return zones_llm.cut(zones_llm.candidates(out["_info"], out, t["blocks"], t["tables"]))


def _llm_basis(t):
    """자동 판독이 기대는 문서 쪽 상태(문서 차례 · 기준 확정 · 값 · 분석 실행 · 추가한 자리 · 앞서 반영한 값 — `_auto` 의 열쇠와 같은 것) — 호출 동안 그대로였는지 견준다."""
    return (t["rev"], t["base"], _j(t["raw"]), t["basis"], tuple(t["runs"]), _j(t["hints"]), _j(t["prior"]))


def _llm_record(t, cands, more, res, **result):
    """마지막 검토의 기록(llm_last 의 꼴) — result 가 덮는다(marked · kept · dropped · summary · error · items · droppedRows)."""
    from app import zones_llm
    n, call = len(cands), res.get("call") or {}
    return {"at": _now(), "t": round(datetime.now().timestamp(), 3), "rev": t["rev"], "zonesRev": t["zones"]["rev"], "candidates": n, "kinds": zones_llm.kinds(cands), "truncated": more,
            "marked": 0, "kept": n, "dropped": 0, "summary": "", "error": None, "items": [], "droppedRows": [], "call": call, "guide": res.get("guide"),
            "units": [{"n": 0, "title": LLM_TITLE, "pages": None, "targets": n, "tables": sum(1 for c in cands if c.get("type") == "table"), "error": call.get("error"),
                       "prompt": res.get("prompt") or "", "answer": res.get("data")}], **result}


def _llm_log(wid, rec):
    call = rec.get("call") or {}
    works.log(wid, "zoneLlm", op="review", rev=rec["rev"], candidates=rec["candidates"], marked=rec["marked"], kept=rec["kept"], dropped=rec["dropped"], truncated=rec["truncated"],
              model=call.get("model"), backend=call.get("backend"), ms=call.get("ms"), costUsd=call.get("costUsd"), error=rec.get("error"))


@router.get("/api/docs/{doc_id}/zones/llm")
def zones_llm_peek(doc_id: str):
    """LLM 검토 미리 보기 — 지금 보낼 후보의 수(종류마다) · LLM 을 쓸 수 있나 · 도는 중인가 · 마지막 결과. LLM 을 부르지 않고 문서도 구역도 안 바뀐다."""
    from app import llm, server, zones_llm
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
    cands, more = _llm_cands(t, _respond(t))
    ok = bool(llm.status().get("available"))
    with _LOCK:
        running = s.id in _LLM_RUN
    last = llm_last(s.id)
    return {"available": ok, "why": None if ok else LLM_MSG["noLlm"], "running": running, "candidates": len(cands), "kinds": zones_llm.kinds(cands), "truncated": more,
            "last": {k: last.get(k) for k in LLM_LAST_KEYS} if last else None}


@router.post("/api/docs/{doc_id}/zones/llm")
def zones_llm_run(doc_id: str, body: dict = Body(default={})):
    """LLM 검토 {docRev, zonesRev} — 스크립트가 못 정한 표·문단(후보)을 한 번 보내고, 검증한 답 가운데 값이 바뀌는 것만 후보마다 「LLM 이 지정」 으로 적는다(동기 — 수십 초~몇 분).
    낡은 화면에서 누른 것(차례가 다름) · 호출하는 동안 문서나 구역 지정이 바뀐 것은 반영하지 않는다(409). 사람이 지정한 블록은 후보가 아니다."""
    from app import llm, server, zones_llm
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
        _fresh(t, body.get("docRev"), body.get("zonesRev"))
    auto = _auto(t)
    out = _respond(t, auto)
    cands, more = _llm_cands(t, out)
    if not cands:
        return {**_public(out), "llm": {"nothing": True, "candidates": 0}}
    ok = bool(llm.status().get("available"))
    with _LOCK:
        if s.id in _LLM_RUN:
            raise _err(409, "busy", LLM_MSG["busy"])
        if not ok:
            raise _err(409, "noLlm", LLM_MSG["noLlm"])
        _LLM_RUN.add(s.id)
    try:
        payload = zones_llm.payload(auto[0], cands, (auto[1] or {}).get("period"))
        effort = body.get("effort") if body.get("effort") in llm.EFFORTS else "medium"
        try:
            res = zones_llm.ask(payload, effort=effort, timeout=max(240.0, 120.0 + 3.0 * len(cands)))
        except Exception as e:  # noqa: BLE001 — 호출이 깨져도 「답 없음」 으로 남긴다(기록 · 502)
            res = {"data": None, "prompt": "", "call": {"error": f"{type(e).__name__}: {e}"}, "guide": None}
        if not isinstance(res.get("data"), dict):
            why = (res.get("call") or {}).get("error") or "응답 없음"
            rec = _llm_record(t, cands, more, res, error=str(why)[:300])
            _llm_keep(s.id, rec)
            _llm_log(s.id, rec)
            raise _err(502, "llmFailed", f"{LLM_MSG['llmFailed']}: {str(why)[:300]}")
        items, dropped = zones_llm.check(res["data"], payload)
        summary = " ".join(str(res["data"].get("summary") or "").split())[:600]
        kind_of = {c["id"]: c for c in cands}
        with s.lock:
            t2 = _taken(s)
            moved = "staleDoc" if _llm_basis(t2) != _llm_basis(t) else "staleZones" if t2["zones"]["rev"] != t["zones"]["rev"] else None
            made, at = {}, _now()
            for it in items if moved is None else ():
                if it["label"]:
                    mark = zones.mark_make([it["id"]], it["label"], it["reason"][:NOTE_MAX], "llm", at)
                    s.zones["marks"] = zones.marks_put(s.zones["marks"], mark)
                    made[it["id"]] = mark["id"]
            if made:
                s.zones["rev"] += 1
                t2["zones"] = copy.deepcopy(s.zones)
        rows = [{"id": it["id"], "type": kind_of[it["id"]].get("type"), "kind": kind_of[it["id"]].get("kind"), "label": it["label"], "reason": it["reason"], "keep": it["keep"], "mark": made.get(it["id"])}
                for it in items]
        rec = _llm_record(t, cands, more, res, marked=len(made), kept=len(cands) - len(made), dropped=len(dropped), summary=summary, items=rows, droppedRows=dropped,
                          error=None if moved is None else LLM_MSG["docMoved" if moved == "staleDoc" else "zonesMoved"])
        if made:
            server._persist_safe(s, force=True)
        _llm_keep(s.id, rec)
        _llm_log(s.id, rec)
        if moved:
            raise _err(409, moved, rec["error"])
        call = rec["call"]
        return {**_public(_respond(t2)), "llm": {"candidates": rec["candidates"], "marked": rec["marked"], "kept": rec["kept"], "dropped": rec["dropped"], "summary": summary, "truncated": more,
                                                 "call": {k: call.get(k) for k in ("model", "ms", "costUsd", "error")}}}
    finally:
        with _LOCK:
            _LLM_RUN.discard(s.id)


@router.delete("/api/docs/{doc_id}/zones/marks")
def zones_marks_clear(doc_id: str, by: str | None = None, zonesRev: int | None = None):   # noqa: N803 — 쿼리 이름(spec_구역 ② §8)
    """LLM 이 지정한 것만 모두 해제(?by=llm&zonesRev=n) — 그 블록들은 자동 판독 값으로 돌아간다. 사람이 지정한 것은 그대로다. 하나도 없으면 아무것도 안 바꾸고 200."""
    from app import server
    if by != "llm":
        raise _err(400, "badMark", LLM_MSG["byLlm"])
    s = server._sess(doc_id)
    with s.lock:
        t = _taken(s)
        _fresh(t, None, zonesRev, doc=False)
        gone = [m for m in s.zones["marks"] if m.get("by") == "llm"]
        if gone:
            s.zones["marks"] = [m for m in s.zones["marks"] if m.get("by") != "llm"]
            s.zones["rev"] += 1
            t["zones"] = copy.deepcopy(s.zones)
    if gone:
        server._persist_safe(s, force=True)
        works.log(s.id, "zoneLlm", op="clear", marks=len(gone), blocks=sum(len(m.get("ids") or ()) for m in gone))
    return _public(_respond(t))
