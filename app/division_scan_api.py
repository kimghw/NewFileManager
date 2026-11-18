"""구분 기준 판독의 서비스 — 관문 · 지연 계산 · 캐시 · 끝점(spec_구분_기준 ② §23). 판독 자체는 `division_scan.scan`(순수 계산).

- **관문**(`enabled`): 연구개발과제 문서만 — hwpx 이고 작업 종류가 rnd(작업에 적힌 TASK 가 없으면 양식 판정으로 짐작 — `server._task` 와 같은 뜻이지만 **쓰지 않는다**).
  2026-11-18 사용자 "연구개발과제 에서만 구분 기준엔진을 쓸거야". 편집 구역 · 「구분 기준 자리 표시」 의 판독 보탬 · 헤딩 2단계가 같은 관문을 쓴다.
- **지연 계산**: 문서를 열거나 올릴 때 걸지 않는다(그 길은 다른 세션의 일 — newfilemanager-13 협의). 처음 읽을 때(이 끝점 · 편집 구역 · 「구분 기준 자리 표시」 · 헤딩 2단계의 첫 단계) 센다.
- **입력은 잠금 안에서 뜨고 계산은 잠금 밖**(`inputs` → `peek`/`compute`). 열쇠 = (판독 판 · 문서 객체 · rev · 기준 확정 수 · 귀속 값과 그 출처 · 추가한 자리 · 앞서 반영한 값) — 같으면 읽어 둔 것.
  캐시는 모듈의 문서마다 하나(작업 폴더에 쓰지 않는다 — 초기화·다시 열기는 문서 객체가 새것이라 열쇠가 달라진다).
- 「다시 판독」(`POST`) = 같은 입력이어도 다시 센다(결정적이라 결과는 같다 — 열쇠에 시각을 넣지 않는다).
"""
import hashlib
import json
import threading
import time

from fastapi import APIRouter, Body

from app import division_scan as DS
from app import works

router = APIRouter()
_CACHE, _LOCK = {}, threading.Lock()
CACHE_MAX = 16


def _server():
    from app import server
    return server


def enabled(s, blocks=None):
    """연구개발과제 문서인가(hwpx · 작업 종류 rnd). 세션 잠금 안에서 불러도 된다(작업 기록 읽기뿐)."""
    if getattr(s, "fmt", None) != "hwpx":
        return False
    t = (works.work(getattr(s, "id", None)) or {}).get("task") if getattr(s, "id", None) else None
    if t:
        return t.get("kind") == "rnd"
    srv = _server()
    return srv.PROFILE.form_of(blocks if blocks is not None else s.doc.blocks()) is not None


def inputs(s, blocks=None):
    """(세션 잠금 안) 판독에 쓸 것을 뜬다 → {id, rev, base, blocks, values, basis, find, hints, prior, key} | None(관문 밖). 값 = 반영한 값 → 입력 값(편집 구역과 같은 차례 — astra 협의)."""
    srv = _server()
    blocks = s.doc.blocks() if blocks is None else blocks
    if not enabled(s, blocks):
        return None
    srv._project_settings_sync(s)
    d = s.division
    raw = ((d.get("applied") or {}).get("values")) or ((d.get("settings") or {}).get("values"))
    values = None
    if raw:
        try:
            values = srv.PROFILE.norm_values(raw)
        except (KeyError, TypeError, ValueError):
            values = None
    basis = ("applied" if (d.get("applied") or {}).get("values") else "settings") if values is not None else None
    hints = [{k: h.get(k) for k in ("para", "dim", "value", "by")} for h in d.get("hints") or () if isinstance(h, dict) and h.get("para")]
    prior = list(srv._division_prior(s))
    inp = {"id": s.id, "rev": s.rev, "base": s.base_n, "blocks": blocks, "values": values, "basis": basis,
           "find": None if values is not None else srv.PROFILE.norm_values(srv.DIVISION_DEFAULT_VALUES), "hints": hints, "prior": prior}
    inp["key"] = hashlib.sha1(json.dumps([DS.VERSION, id(s.doc), inp["rev"], inp["base"], values, basis, hints, prior], ensure_ascii=False, sort_keys=True,
                                         default=str).encode("utf-8")).hexdigest()[:16]
    return inp


def peek(inp):
    """읽어 둔 판독(열쇠가 같을 때) | None."""
    if not inp:
        return None
    with _LOCK:
        e = _CACHE.get(inp["id"])
    return e if e is not None and e["key"] == inp["key"] else None


def compute(inp):
    """뜬 입력으로 판독(잠금 밖) → 항목 {key, rev, base, basis, at, secs, result} — 캐시에 넣는다(같은 문서의 옛 항목을 바꿈)."""
    t0 = time.perf_counter()
    result = DS.scan(inp["blocks"], inp["values"], inp["find"], hints=inp["hints"], prior=inp["prior"])
    e = {"key": inp["key"], "rev": inp["rev"], "base": inp["base"], "basis": inp["basis"], "at": time.time(), "secs": round(time.perf_counter() - t0, 2), "result": result}
    with _LOCK:
        _CACHE.pop(inp["id"], None)
        _CACHE[inp["id"]] = e
        while len(_CACHE) > CACHE_MAX:
            del _CACHE[next(iter(_CACHE))]
    return e


def ensure(s, force=False):
    """지금 문서의 판독 항목(없거나 낡았으면 센다) | None(연구개발과제 문서가 아님). 잠금은 이 함수가 잡는다 — 잡은 채로 부르지 말 것."""
    with s.lock:
        inp = inputs(s)
    if inp is None:
        return None
    return (None if force else peek(inp)) or compute(inp)


def last(s):
    """읽어 둔 판독 항목(센 적이 없으면 None — 세지 않는다: 분석 상태처럼 읽기만 하는 길)."""
    with _LOCK:
        return _CACHE.get(getattr(s, "id", None))


def summary(e, s=None):
    """판독 항목 → 화면·에이전트가 읽는 꼴 {at, rev, base, basis, secs, counts, fresh?}."""
    if not e:
        return None
    out = {k: e[k] for k in ("at", "rev", "base", "basis", "secs")}
    out["counts"] = dict(e["result"]["counts"])
    if s is not None:
        out["fresh"] = e["rev"] == getattr(s, "rev", None) and e["base"] == getattr(s, "base_n", None)
    return out


@router.get("/api/docs/{doc_id}/divisions/scan")
def scan_get(doc_id: str):
    """구분 기준 판독(② §23) — 처음이거나 문서·값·추가한 자리가 바뀌었으면 센다 → {enabled, scan{at, rev, basis, secs, counts, fresh} | None}."""
    s = _server()._sess(doc_id)
    e = ensure(s)
    return {"enabled": e is not None, "scan": summary(e, s)}


@router.post("/api/docs/{doc_id}/divisions/scan")
def scan_post(doc_id: str, body: dict = Body(default={})):
    """「다시 판독」 — 같은 입력이어도 다시 센다 → GET 과 같은 꼴. 연구개발과제 문서가 아니면 enabled false."""
    s = _server()._sess(doc_id)
    e = ensure(s, force=True)
    if e is not None:
        works.log(s.id, "divisionScan", rev=e["rev"], counts=e["result"]["counts"], secs=e["secs"])
    return {"enabled": e is not None, "scan": summary(e, s)}


# ---- 「구분 기준 자리 표시」 에 보탤 판독(② §23 「표시」) ----------------------------------------------------------------------

def reads(e, orgs=None, stages=None):
    """판독 항목 → 「구분 기준 자리 표시」 의 보탬 [{kind: label|scope|table, dim, dimName, value, src, inGroup, table?, paras[문단 id], text?}] —
    엔진 묶음의 라벨이 아닌 괄호 줄(pattern · name) + 기관 이름 줄(nameLine — 그 줄은 label · 그 아래 내용은 scope) + 표 안 귀속(표·값마다 한 줄). 엔진 묶음은 members 의 groups 가 그대로 낸다."""
    if not e:
        return []
    r = e["result"]
    from app.division_profiles import rnd
    names = {o["key"]: o.get("name") or o["key"] for o in orgs or ()}
    out = []
    for x in r.get("extra") or ():
        if x["src"] == "name" and not names:
            continue
        row = {"kind": "label", "dim": x["dim"], "dimName": rnd.DIM_NAME.get(x["dim"], x["dim"]), "value": names.get(x.get("value"), x.get("value") or ""),
               "src": x["src"], "inGroup": bool(x.get("inGroup")), "paras": [x["para"]], "text": x.get("text") or ""}
        out.append(row)
        if x.get("paras"):   # 기관 이름 줄(nameLine)의 자리 — 그 줄 아래의 내용(표 칸의 문단까지): 라벨 줄이 아닌 「자리 안」 으로
            out.append({**row, "kind": "scope", "paras": list(x["paras"])})
    groups = {}

    def add(tid, dim, value, paras):
        g = groups.setdefault((tid, dim, value), {"kind": "table", "dim": dim, "dimName": rnd.DIM_NAME.get(dim, dim), "value": value, "src": "table", "inGroup": False,
                                                  "table": tid, "paras": []})
        g["paras"].extend(p for p in paras if p not in g["paras"])

    def org_text(o):
        return names.get(o.get("key"), o.get("key")) if o.get("kind") == "org" else ("기관 확인 필요" if o.get("kind") == "conflict" else "기관 모름")

    cell_paras, cell_table = r.get("cellParas") or {}, r.get("cellTable") or {}
    by_table = {}
    for cid, tid in cell_table.items():
        by_table.setdefault(tid, []).extend(cell_paras.get(cid) or ())
    for tid, ev in (r.get("tables") or {}).items():   # 표 전체의 근거 — 그 표의 칸 문단 전부
        if "org" in ev:
            add(tid, "org", org_text(ev["org"]), by_table.get(tid) or [])
        if "year" in ev:
            add(tid, "year", _year_text(ev["year"], stages), by_table.get(tid) or [])
    for cid, ev in (r.get("cells") or {}).items():   # 행·열에서 읽은 칸
        tid, ps = cell_table.get(cid), cell_paras.get(cid) or []
        if "org" in ev:
            add(tid, "org", org_text(ev["org"]), ps)
        if "year" in ev:
            add(tid, "year", _year_text(ev["year"], stages), ps)
        elif "yearClash" in ev:
            add(tid, "year", "차년도 엇갈림 " + "·".join(str(y) for y in ev["yearClash"]), ps)
    out.extend(g for g in groups.values() if g["paras"])
    return out


def _year_text(y, stages):
    st = list(stages or ())
    if len(st) <= 1:
        return f"{y}차년도"
    for s_, n in enumerate(st, 1):
        if y <= n:
            return f"{s_}단계 {y}차년도"
        y -= n
    return f"{y}차년도"
