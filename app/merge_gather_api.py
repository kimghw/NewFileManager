"""취합 API(spec_취합 ② §2 저장 · §3 배포 기준본 · §4 내용 매핑 · §6 끝점) — 자리 정보(merge_gather_frame) · 3방향 엔진(merge_gather) · LLM 순회 검토(merge_gather_llm) ·
끌어 넣기(merge_gather_drop)를 저장과 HTTP 로 잇는다. 모두 **취합본 문서 id 기준**. 전제 = jobs/plan_merge.md.

- `GET  /api/docs/{to}/gather` → {project, reasons[지금 기준본을 못 만드는 까닭], frame{frameId, at, rev, stale} | null, version,
  orgs[{key, name, role, received[기관 문서 id], applied[기관 문서 id]}], parts[{work, name, order, orgs, common, frameId, state(blocked|unassigned|todo|done|new), counts{상태: n} | null, todo | null,
  llm{at, held, stale} | null, recommend{org, n} | null, reasons[]}]}. 기관 문서 하나의 판정을 못 내면 그 줄의 reasons 에만 싣는다(전체는 나간다).
- `POST …/gather/frame` → 위 몸통. 그때의 저장 바이트와 자리 정보를 **세션 잠금 안에서 함께** 고정(새 frameId). 409 unsupportedForm · noValues · notApplied · staleHeadings(2·3단계 분석이 지금 차례의 것이 아님 — 없을 때도).
- `GET  …/gather/frame/file` → 고정한 hwpx(첨부). 404 noFrame.
- `PUT|DELETE …/gather/parts/{part}` `{orgs?: [기관 열쇠…], common?: bool}` → 위 몸통. 없던 문서면 넣는다(order 끝 · 그 작업의 task = {rnd, part, 취합본의 과제, plan_merge} — server.work_task 의 길 그대로라
  다른 문서를 과제에서 내보내지 않는다). 400 badPart(취합본 자신 · 다른 과제 · hwpx 아님) · 404 badPart(그런 문서 없음). DELETE = 취합에서 뺌(넣은 내용은 그대로 · 그 작업의 task.file 만 비움 ·
  넣은 기록은 `gone` 에 남겨 다시 넣었을 때 같은 행을 두 번 넣지 않는다).
- `GET|POST …/gather/parts/{part}/links` → {part{위 줄}, coverage{anchors, blocks, ratio}, share(이름 든 기관 라벨이 맞은 몫 | null), counts, todo, items[작성 내용], llm, reasons[] | ["lowMatch"]}(POST = 다시 맞춤).
  409 noFrame · frameDiffers · frameStale · noHeadings(기관 문서에 2단계 분석 없음) · noMatch. 작성 내용 한 줄 = {key, kind, status, detail, scope, path, to{prev, next, at}, from{ids, table, at}, text, counts, unique,
  decision{value, source(user|llm|auto), nature, reason[, note][, held]} | null}(at = 화면이 갈 블록·칸 id — 표 칸·표 행은 그 칸).
- `PUT  …/gather/parts/{part}/links/{key}` `{value: keep|skip|null}` → 위(사람이 고름 — null = 지움: 앞선 LLM 결정이 있으면 그것으로). 404 noKey.
- `POST …/gather/parts/{part}/llm` → 위(llm 갱신). 자료는 두 세션 잠금 안에서 만들고(prepare) 호출은 잠금 밖(run). 409 noLlm(LLM 이 꺼져 있음 — 아무것도 안 적는다).
- `POST …/gather/parts/{part}/plan` → {planId, part, todo, counts, items[{key, kind, scope, path, text, to, from, counts, decision}], skipped{상태: n}, calc[{table, cell, why, kind, text, key}], dropped[{key, src, what}]}.
  `POST …/apply {planId}` → {counts{hunks, blocks, paragraphs, tables, pictures, placeholders, cells, rows, shaped, fitted, recalculated, skipped}, calc[{table, cell, kind, action, was, now, note}], dropped[], skipped[], …편집 상태}
  | {nothing: true, …편집 상태}. 409 stalePlan(계획 뒤 두 문서의 차례 · 기준본 · 취합 설정의 판 · 분석 실행 가운데 하나라도 바뀜) · 422 표준 검사(전부 복원).
- `POST …/gather/drop/plan` `{from, srcId, afterId}` → {planId, from, range{title, blocks, paragraphs, tables, pictures, lines, single}, after{id, text, given}, owner{id, text}, convert{…} | null, dropped[{src, what}]}.
  400 notPart(그 취합에 든 기관 문서가 아님) · badDrop(끌 수 없는 줄 · 놓을 수 없는 자리) · 409 noHeadings. `POST …/gather/drop/apply {planId, convert}` → {blocks, converted, kept{까닭: n}, labels, fitted, dropped[], …편집 상태}.
**오류 꼴**: 이 끝점들의 400·404·409 는 모두 `detail = {"reason": 까닭 열쇠, "message": 한국어 글}`(MSG). 422 는 server._transact 의 것 그대로.

저장(취합본 작업 폴더 — 작업 저장이 꺼져 있으면 메모리): `gather.json` {version(설정·결정이 바뀔 때마다 +1 — 넣은 기록만 적을 때는 그대로), frameId, order[], parts{id: {name, added, orgs[], common, frameId,
decisions{열쇠: {value, source, …}}, llm{at, units[], job, guide, held, rejected, left, counts} | null, applied{열쇠: {at, ids, fp, kind}}}}, gone{뺀 문서의 넣은 기록}} ·
`gather/frame-<frameId>.hwpx`(나눠 주는 바이트) · `gather/frame-<frameId>.json.gz`(자리 정보 + frameId·at·sha256·runs·division{planId, rev}) · `gather/llm-<기관 문서 id>.json`(마지막으로 보낸 프롬프트·답 — 화면 「지침」).
기준본이 낡음(frame.stale) = 기준본 뒤에 취합본의 구분 기준을 다시 반영함(그때 적어 둔 반영 계획 id·차례와 다름) · 또는 기준본의 블록 id 가 지금 문서에 절반도 안 남음.

**기준본에서 나오지 않은 문서**(전제: 저절로 넣지 않는다): 맞은 정도(coverage.ratio)가 LOW_MATCH 아래이거나, 기준본의 「기관 이름이 든 구분 라벨 줄」 이 기관 문서에 LABEL_MATCH 몫도 없으면
(같은 양식의 다른 과제 문서 — 맞은 정도는 0.6~0.8 로 높게 나온다, 실측) `lowMatch`: 넣을 수 있는(ready) 작성 내용마다 사람이 고르지 않은 것은 decision {check, auto} 를 달아 계획에서 뺀다 — LLM 의 「유지」 도 이것을 못 푼다.
캐시: 자리 연결 = (기준 판, 기관 문서 차례) · 판정 = (기준 판, 취합본 차례, 취합 설정의 판, 기관 문서 차례, 두 문서의 분석 실행) — 판정이 맞으면 GET 은 기관 문서를 열지 않는다."""
import gzip
import json
import threading
import time
import uuid
import zlib
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from app import heading_runs as HR
from app import merge_gather as MG
from app import merge_gather_drop as DROP
from app import merge_gather_frame as F
from app import merge_gather_llm as L
from app import merge_pairs as P
from app import works

router = APIRouter()
_LOCK = threading.RLock()
_MEM, _BLOB = {}, {}              # 작업 저장이 꺼졌을 때의 gather.json · gather/ 아래 파일
_FRAMES, _LINKS, _JUDGE = {}, {}, {}   # 취합본 id → (frameId, 자리 정보) · (취합본, 기관 문서) → (frameId, 기관 문서 차례, 자리 연결) · (취합본, 기관 문서) → (열쇠, 판정)
_PLANS, _DROPS = {}, {}           # (취합본, 기관 문서) → 마지막 넣기 계획 · 취합본 → 마지막 끌어 넣기 계획(메모리만 — 서버를 다시 켜면 다시 계획)
LOW_MATCH, LABEL_MATCH, FRAME_ALIVE = 0.5, 0.5, 0.5   # 맞은 정도 · 이름 든 기관 라벨이 맞은 몫(이 아래면 lowMatch) · 기준본 블록 id 가 지금 문서에 남은 몫(이 아래면 낡음)
AUTO = {"value": "check", "source": "auto", "reason": "기준본과 자리를 충분히 확인하지 못한 문서"}
DECISION = ("value", "source", "nature", "reason", "note", "held")
MSG = {"noFrame": "배포 기준본이 없습니다 — 1단계에서 기준본을 먼저 만드세요",
       "frameStale": "기준본을 만든 뒤 취합본의 구분 기준을 다시 반영했습니다 — 기준본을 새로 만들어 다시 나눠 주세요",
       "frameDiffers": "다른 판의 기준본으로 들어온 기관 문서입니다 — 저절로 넣지 않습니다(끌어 넣기로)",
       "noHeadings": "기관 문서의 헤딩·표 분석이 없습니다 — 먼저 분석하세요(스크립트)",
       "staleHeadings": "헤딩·표 분석이 지금 문서의 것이 아닙니다 — 2단계·3단계를 다시 분석한 뒤 기준본을 만드세요",
       "noMatch": "기준본과 맞는 자리를 찾지 못했습니다 — 기준본에서 나온 문서가 아닙니다(끌어 넣기만)",
       "noValues": "과제 구성 값(단계·차년도 · 기관)이 없습니다", "notApplied": "구분 기준이 아직 취합본에 반영되지 않았습니다",
       "unsupportedForm": "hwpx 문서만 취합할 수 있습니다", "stalePlan": "계획을 세운 뒤 문서나 취합 설정이 바뀌었습니다 — 다시 계획하세요",
       "notPart": "이 취합에 든 기관 문서가 아닙니다", "badPart": "기관 문서로 넣을 수 없는 문서입니다", "badValue": "요청 값이 올바르지 않습니다",
       "noKey": "그런 기관 작성 내용이 없습니다(다시 맞추면 열쇠가 바뀔 수 있습니다)", "noLlm": "LLM 을 쓸 수 없습니다(꺼져 있거나 설정 전) — 검토 없이도 넣기 계획은 세울 수 있습니다",
       "badDrop": "끌어 넣을 수 없습니다", "applyFailed": "반영하지 못했습니다"}


class _Why(Exception):
    """그 기관 문서의 판정을 낼 수 없는 까닭(끝점은 409 로, 목록은 그 줄의 reasons 로)."""

    def __init__(self, code, message=None):
        super().__init__(code)
        self.code, self.message = code, message or MSG.get(code) or code


def _err(status, code, message=None):
    return HTTPException(status, {"reason": code, "message": message or MSG.get(code) or code})


def _now():
    return datetime.now().isoformat(timespec="seconds")


# ---- 저장 -----------------------------------------------------------------------------------------------------

def _dir(wid):
    """취합본 작업 폴더 | None(작업 저장이 꺼짐 · 지운 작업 — 그때는 메모리)."""
    d = works.folder(wid)
    return d if d is not None and (d / "work.json").is_file() else None


def _store(wid, data=None):
    """gather.json 읽기(data None — 늘 {version, frameId, order, parts} 가 있는 사본) · 쓰기."""
    d = _dir(wid)
    if data is None:
        got = (works._read_json(d / "gather.json") if d is not None and (d / "gather.json").is_file() else _MEM.get(wid)) or {}
        parts = {k: v for k, v in (got.get("parts") or {}).items() if isinstance(v, dict)} if isinstance(got.get("parts"), dict) else {}
        order = [p for p in got.get("order") or () if p in parts]
        return {**got, "version": int(got.get("version") or 0), "frameId": got.get("frameId") or None, "order": order + [p for p in parts if p not in order], "parts": parts}
    if d is not None:
        works._write_json(d / "gather.json", data)
    else:
        _MEM[wid] = json.loads(json.dumps(data, ensure_ascii=False))
    return data


def _change(wid, fn, bump=True):
    """gather.json 을 읽어 fn(G) 로 고쳐 쓴다(한 번에 하나) — bump = 설정·결정이 바뀜(version +1: 세워 둔 계획이 낡는다). fn 이 던지면 안 쓴다."""
    with _LOCK:
        G = _store(wid)
        fn(G)
        if bump:
            G["version"] += 1
        _store(wid, G)
        for k in [k for k in _JUDGE if k[0] == wid]:   # 넣은 기록·결정이 바뀌었다 — 판정을 다시
            del _JUDGE[k]
        return G


def _blob(wid, name, data=None):
    """작업 폴더 `gather/<name>` 읽기(없으면 None) · 쓰기(바이트 — 바꿔 넣기)."""
    d = _dir(wid)
    if data is None:
        try:
            return (d / "gather" / name).read_bytes() if d is not None else _BLOB.get((wid, name))
        except OSError:
            return _BLOB.get((wid, name))
    if d is not None:
        works._write(d / "gather" / name, data)
    else:
        _BLOB[(wid, name)] = data
    return data


def _frame(wid, fid):
    """그 판의 자리 정보(읽어 둔다 — 취합본에 하나) | None(없음 · 못 읽음)."""
    if not fid:
        return None
    with _LOCK:
        hit = _FRAMES.get(wid)
    if hit is None or hit[0] != fid:
        raw = _blob(wid, f"frame-{fid}.json.gz")
        try:
            fr = json.loads(gzip.decompress(raw).decode("utf-8")) if raw else None
        except (OSError, ValueError, EOFError, zlib.error):
            fr = None
        if not isinstance(fr, dict) or fr.get("frameId") != fid or not isinstance(fr.get("blocks"), list):
            return None
        hit = (fid, fr)
        with _LOCK:
            _FRAMES[wid] = hit
    return hit[1]


def llm_last(wid, part):
    """그 기관 문서의 LLM 검토가 마지막으로 보낸 프롬프트·답(`gather/llm-<기관 문서 id>.json`) | None — 화면 「지침」(merge_api.llm_guide step gather)이 읽는다."""
    if not isinstance(part, str) or not works.ID.match(part):
        return None
    raw = _blob(wid, f"llm-{part}.json")
    try:
        got = json.loads(raw.decode("utf-8")) if raw else None
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


# ---- 두 문서 읽기(세션 잠금은 부르는 쪽) ---------------------------------------------------------------------------

def _run(x):
    return ((x or {}).get("meta") or {}).get("run")


def _runs(s):
    """그 문서의 분석 실행 번호 [2단계, 3단계] — 계획·판정의 유효성에 든다."""
    return [_run(HR.graph(s)), _run(HR.tables(s))] if s.fmt == "hwpx" else [None, None]


def _side(s):
    """문서 하나의 한 쪽(merge_api._read 의 꼴) — 세션 잠금 안에서. blocks 는 그때의 목록(고치면 문서가 새 목록을 만든다)."""
    return {"id": s.id, "name": s.name, "rev": s.rev, "doc": s.doc, "blocks": s.doc.blocks(), "graph": HR.graph(s), "tables": HR.tables(s)}


@contextmanager
def _both(a, b):
    """두 세션을 함께 잠근다(차례 = 문서 id — 서로 맞물리지 않게)."""
    first, second = sorted((a, b), key=lambda x: x.id)
    with first.lock, second.lock:
        yield


def _part_sess(pid):
    from app import server
    try:
        s = server._sess(pid)
    except HTTPException as e:
        raise _Why("badPart", "기관 문서를 열 수 없습니다(지운 문서)") from e
    if s.fmt != "hwpx":
        raise _Why("unsupportedForm")
    return s


def _frame_why(s):
    """(세션 잠금 안) 지금 기준본을 만들 수 없는 까닭 [] | [열쇠] — 구분 기준이 반영돼 있고 2·3단계 분석이 **지금 문서 차례의 것**이어야 한다(「결과가 있음」 만으로는 안 됨 — astra)."""
    if s.fmt != "hwpx":
        return ["unsupportedForm"]
    applied, settings = s.division.get("applied") or {}, s.division.get("settings") or {}
    if not (applied.get("values") or settings.get("values")):
        return ["noValues"]
    if not applied.get("values"):
        return ["notApplied"]
    g, t = HR.graph(s), HR.tables(s)
    mg, mt = (g or {}).get("meta") or {}, (t or {}).get("meta") or {}
    ok = bool(g and t) and mg.get("rev") == s.rev == mt.get("rev") and ("stage2Run" not in mt or mt["stage2Run"] == mg.get("run"))   # 표 소속이 기댄 2단계도 지금 것
    return [] if ok else ["staleHeadings"]


def _stale(s, frame):
    """(세션 잠금 안) 기준본이 낡았나(모듈 설명) — 실행 취소로 그 반영이 되돌아가면 다시 안 낡음."""
    a, mark = s.division.get("applied") or {}, frame.get("division") or {}
    if (a.get("planId"), a.get("rev")) != (mark.get("planId"), mark.get("rev")):
        return True
    now, ids = {b["id"] for b in s.doc.blocks()}, [b["id"] for b in frame["blocks"]]
    return bool(ids) and sum(i in now for i in ids) < FRAME_ALIVE * len(ids)


def _orgs(s, frame):
    """과제의 기관 [{key, name, role}] — 취합본의 지금 값(반영한 값 → 입력 중인 값), 없으면 기준본의 것."""
    from app.division_profiles.rnd import core
    values = (s.division.get("applied") or {}).get("values") or (s.division.get("settings") or {}).get("values")
    try:
        return F.orgs_of(core.norm_values(values)) if values else list((frame or {}).get("orgs") or [])
    except (KeyError, TypeError, ValueError):
        return list((frame or {}).get("orgs") or [])


def _ctx(doc_id):
    """(취합본 세션, gather.json, 지금 기준본 | None, 낡았나)."""
    from app import server
    s = server._sess(doc_id)
    G = _store(doc_id)
    frame = _frame(doc_id, G["frameId"])
    with s.lock:
        stale = frame is not None and _stale(s, frame)
    return s, G, frame, stale


def _rec(G, pid):
    rec = G["parts"].get(pid)
    if rec is None:
        raise _err(404, "notPart")
    return rec


def _blocked(rec, frame, stale):
    """기준본 탓에 그 기관 문서의 자리 연결을 할 수 없는 까닭 | None."""
    return "noFrame" if frame is None else "frameDiffers" if rec.get("frameId") != frame["frameId"] else "frameStale" if stale else None


# ---- 자리 연결 → 판정 → 결정(§4-1 · §4-2 · §4-3 의 저장한 결정) ---------------------------------------------------------

def _label_share(frame, blocks):
    """기준본의 「기관 이름이 든 구분 라벨 줄」 가운데 기관 문서에 그대로 있는 몫 | None(그런 줄이 없는 기준본). 기준본을 받아 쓴 문서는 남의 라벨도 그대로 둔다(1.0) —
    같은 양식의 다른 과제 문서는 기관 이름이 달라 0 에 가깝다(공통 자리의 뼈대는 같아 coverage 만으로는 안 걸린다)."""
    names = [o["key"] for o in frame.get("orgs") or () if o.get("key")]
    want = {b["key"] for b in frame["blocks"] if b["kind"] == "p" and b["cls"] == "label" and b["key"] and any(k in P.org_key(b["text"]) for k in names)}
    if not want:
        return None
    have = {F.para_key(b.get("text")) for b in blocks if b.get("type") == "paragraph" and not b.get("captionOf")}
    return round(len(want & have) / len(want), 3)


def _linked(to_id, frame, part, fresh=False):
    """기준본 ↔ 기관 문서 자리 연결(merge_gather.links + lowMatch 판정) — (기준 판, 기관 문서 차례)가 같으면 다시 안 맞춘다. 기관 문서 세션 잠금 안에서(그림 바이트를 읽는다)."""
    key = (to_id, part["id"])
    with _LOCK:
        hit = _LINKS.get(key)
    if fresh or hit is None or hit[:2] != (frame["frameId"], part["rev"]):
        got = MG.links(frame, part)
        share = None if got["reasons"] else _label_share(frame, part["blocks"])
        got.update(share=share, low=not got["reasons"] and (got["coverage"]["ratio"] < LOW_MATCH or (share is not None and share < LABEL_MATCH)))
        hit = (frame["frameId"], part["rev"], got)
        with _LOCK:
            _LINKS[key] = hit
    return hit[2]


def _judged(to_s, src, G, frame, pid, fresh=False):
    """(두 세션 잠금 안) 기관 문서 하나의 판정 → {items(결정이 붙은 작성 내용 — 엔진의 꼴 그대로), coverage, share, low, counts, todo, recommend, llmStale}. 못 내면 _Why.
    결정: 사람이 고른 것 → (lowMatch 면 ready 마다 AUTO) → 저장한 LLM 결정 가운데 **지금 자료의 것**(inputHash 가 같음 — 다르면 낡은 것이라 안 쓴다, llmStale 로 셈)."""
    key = (frame["frameId"], to_s.rev, G["version"], src.rev, tuple(_runs(to_s)), tuple(_runs(src)))
    with _LOCK:
        hit = _JUDGE.get((to_s.id, pid))
    if not fresh and hit is not None and hit[0] == key:
        return hit[1]
    rec, part = G["parts"][pid], _side(src)
    if part["graph"] is None:
        raise _Why("noHeadings")
    lk = _linked(to_s.id, frame, part, fresh)
    if lk["reasons"]:
        raise _Why("noMatch")
    to = _side(to_s)
    items = MG.judge(lk["items"], frame, to, {"orgs": rec.get("orgs") or [], "common": rec.get("common", True) is not False}, rec.get("applied") or {})
    saved = {k: v for k, v in (rec.get("decisions") or {}).items() if isinstance(v, dict)}
    hashes = L.hashes(items, frame, to, part) if not lk["low"] and any(v.get("source") == "llm" for v in saved.values()) else {}
    stale = 0
    for h in items:
        d, pick = saved.get(h["key"]), None
        if d is not None and d.get("source") == "user" and d.get("value") in ("keep", "skip"):
            pick = d
        elif lk["low"] and h["status"] == "ready":
            pick = AUTO
        elif d is not None and d.get("source") == "llm" and h["status"] in L.TARGET:
            if hashes.get(h["key"]) == d.get("inputHash"):
                pick = d
            else:
                stale += 1
        h["decision"] = {k: pick[k] for k in DECISION if pick.get(k) is not None} if pick else None
    top = Counter(h["scope"]["org"] for h in lk["items"] if h["status"] == "ready" and h["scope"]["kind"] == "org" and h["scope"]["org"]).most_common(1)
    out = {"items": items, "coverage": lk["coverage"], "share": lk["share"], "low": lk["low"], "counts": dict(Counter(h["status"] for h in items)),
           "todo": sum(1 for h in items if h["status"] == "ready" and (h["decision"] or {}).get("value") not in ("skip", "check")),
           "recommend": {"org": top[0][0], "n": top[0][1]} if top else None, "llmStale": stale}   # 추천 = 넣을 수 있는 작성 내용이 가장 많은 기관(고르는 것은 사람)
    with _LOCK:
        _JUDGE[(to_s.id, pid)] = (key, out)
    return out


def _compute(to_s, G, frame, pid, fresh=False):
    """(잠금 밖) 판정 — 읽어 둔 것이 지금 것이면 기관 문서를 열지 않는다(메모리에 없는 기관 문서의 차례는 작업 폴더의 것 — 닫힌 문서는 안 바뀐다)."""
    from app import server
    src = server.DOCS.get(pid)
    with _LOCK:
        hit = None if fresh else _JUDGE.get((to_s.id, pid))
    if hit is not None:
        rev = src.rev if src is not None else (works.work(pid) or {}).get("rev")
        if hit[0][:5] == (frame["frameId"], to_s.rev, G["version"], rev, tuple(_runs(to_s))) and (src is None or hit[0][5] == tuple(_runs(src))):
            return hit[1]
    to_s.touched = time.time()   # 기관 문서를 여럿 여는 동안 취합본이 메모리에서 밀려나지 않게(server._admit 은 가장 오래 안 쓴 것을 비운다)
    src = _part_sess(pid)
    with _both(to_s, src):
        return _judged(to_s, src, G, frame, pid, fresh)


def _name(pid, rec):
    from app import server
    s = server.DOCS.get(pid)
    return s.name if s is not None else (works.work(pid) or {}).get("name") or rec.get("name") or pid


def _row(G, pid, got=None, why=(), error=None):
    """기관 문서 한 줄(GET …/gather 의 parts[] · links 의 part)."""
    rec = G["parts"][pid]
    orgs, llm = list(rec.get("orgs") or []), rec.get("llm")
    reasons = [*why, *(["lowMatch"] if got and got["low"] else [])]
    state = "blocked" if why else "unassigned" if not orgs else "new" if not got else "todo" if got["todo"] else "done"
    return {"work": pid, "name": _name(pid, rec), "order": G["order"].index(pid), "orgs": orgs, "common": rec.get("common", True) is not False, "frameId": rec.get("frameId"), "state": state,
            "counts": got["counts"] if got else None, "todo": got["todo"] if got else None,
            "llm": {"at": llm.get("at"), "held": llm.get("held") or 0, "stale": got["llmStale"] if got else 0} if isinstance(llm, dict) else None,
            "recommend": got["recommend"] if got else None, "reasons": reasons, **({"error": error} if error else {})}


def _part_view(to_s, G, frame, stale, pid, fresh=False):
    """→ (그 줄, 판정 | None) — 못 내는 까닭은 줄의 reasons 로(예외를 밖으로 안 낸다)."""
    why = _blocked(G["parts"][pid], frame, stale)
    if why:
        return _row(G, pid, why=[why]), None
    try:
        got = _compute(to_s, G, frame, pid, fresh)
    except _Why as e:
        return _row(G, pid, why=[e.code]), None
    except Exception as e:   # 한 문서의 판정이 틀어져도 취합 상태는 나가야 한다 — 「못 냄」 은 「0」 과 다르다: error 를 싣는다
        return _row(G, pid, why=["error"], error=f"{type(e).__name__}: {e}"[:300]), None
    return _row(G, pid, got), got


def _view(doc_id):
    """GET …/gather 의 몸통."""
    from app import server
    s = server._sess(doc_id)
    G = _store(doc_id)
    frame = _frame(doc_id, G["frameId"])
    with s.lock:
        why = _frame_why(s)
        stale = frame is not None and _stale(s, frame)
        orgs = _orgs(s, frame)
    rows, put = [], {}
    for pid in G["order"]:
        row, got = _part_view(s, G, frame, stale, pid)
        rows.append(row)
        done = G["parts"][pid].get("applied") or {}
        for h in (got or {}).get("items") or ():   # 반영한 기관 = 이 문서에서 넣은 기록이 지금도 맞는(same) 그 기관 자리의 작성 내용이 있음
            if h["status"] == "same" and h["key"] in done and h["scope"]["kind"] == "org":
                put.setdefault(h["scope"]["org"], set()).add(pid)
    return {"project": ((works.work(doc_id) or {}).get("task") or {}).get("project") or "", "reasons": why,
            "frame": {"frameId": frame["frameId"], "at": frame.get("at"), "rev": frame.get("rev"), "stale": stale} if frame else None, "version": G["version"],
            "orgs": [{**{k: o.get(k) for k in ("key", "name", "role")}, "received": [p for p in G["order"] if o["key"] in (G["parts"][p].get("orgs") or ())],
                      "applied": [p for p in G["order"] if p in put.get(o["key"], ())]} for o in orgs],
            "parts": rows}


def _ends(h):
    """작성 내용의 두 끝 → (to{prev, next, at}, from{ids, table, at}) — at = 화면이 그 자리로 갈 블록·칸 id(표 칸·표 행은 표가 아니라 그 칸: 취합본은 넣을 칸 먼저, 기관 문서는 쓴 칸)."""
    f, to = h["from"], h.get("to") or {}
    cells, rows = f.get("cells") or (), f.get("rows") or ()
    spot = next((c.get("to") for c in cells if c.get("status") == "ready"), None) or next((c.get("to") for c in cells), None)
    src = next(iter(f.get("ids") or ()), None) or next((c.get("id") for c in cells), None) or next((i for r in rows for i in r.get("ids") or ()), None)
    return ({"prev": to.get("prev"), "next": to.get("next"), "at": spot or to.get("prev") or to.get("next")},
            {"ids": list(f.get("ids") or ()), "table": f.get("table"), "at": src or f.get("table")})


def _item(h):
    """작성 내용 하나 → 화면에 보낼 꼴(엔진의 속 자료 base·from.cells·rows 는 뺀다)."""
    to, frm = _ends(h)
    return {**{k: h.get(k) for k in ("key", "kind", "status", "detail", "scope", "path", "text", "counts", "unique", "decision")}, "to": to, "from": frm}


def _links_view(doc_id, pid, fresh=False):
    """GET|POST …/links 의 몸통 — 못 내면 409 {reason}."""
    s, G, frame, stale = _ctx(doc_id)
    why = _blocked(_rec(G, pid), frame, stale)
    if why:
        raise _err(409, why)
    try:
        got = _compute(s, G, frame, pid, fresh)
    except _Why as e:
        raise _err(409, e.code, e.message) from e
    row = _row(G, pid, got)
    llm = G["parts"][pid].get("llm")
    return {"part": row, "coverage": got["coverage"], "share": got["share"], "counts": got["counts"], "todo": got["todo"], "items": [_item(h) for h in got["items"]],
            "llm": {**llm, "stale": got["llmStale"]} if isinstance(llm, dict) else None, "reasons": ["lowMatch"] if got["low"] else []}


# ---- 끝점: 상태 · 배포 기준본(§3) ---------------------------------------------------------------------------------

@router.get("/api/docs/{doc_id}/gather")
def gather_get(doc_id: str):
    return _view(doc_id)


@router.post("/api/docs/{doc_id}/gather/frame")
def gather_frame(doc_id: str):
    """배포 기준본 만들기 — 저장 바이트와 자리 정보를 **같은 잠금 안에서** 뜬다(그 사이 편집이 끼면 기록과 나눠 준 파일이 어긋난다 — astra). 문서는 안 바뀐다. 한 번 만든 판은 안 바꾼다(다시 만들면 새 frameId)."""
    from app import server
    s = server._sess(doc_id)
    with s.lock:
        why = _frame_why(s)
        if why:
            raise _err(409, why[0])
        a = s.division["applied"]
        data = s.doc.save()
        side = _side(s)
        info = F.make({**side, "values": a["values"]})
        fid = uuid.uuid4().hex[:12]
        frame = {"frameId": fid, "at": _now(), "rev": s.rev, "sha256": works.sha256(data), "values": info["values"], "runs": {"stage2": _run(side["graph"]), "stage3": _run(side["tables"])},
                 "division": {"planId": a.get("planId"), "rev": a.get("rev")}, "orgs": info["orgs"], "blocks": info["blocks"]}
    blob = gzip.compress(json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)   # 직렬화를 먼저 끝낸다 — 못 쓰는 값이 있으면 아무것도 안 남긴다
    _blob(doc_id, f"frame-{fid}.hwpx", data)
    _blob(doc_id, f"frame-{fid}.json.gz", blob)

    def fn(G):
        G["frameId"] = fid
        for rec in G["parts"].values():   # 기준본 전에 넣어 둔 기관 문서는 이 판의 것으로(판이 있는 문서는 그대로 — 새 판과 다르면 frameDiffers)
            if not rec.get("frameId"):
                rec["frameId"] = fid
    _change(doc_id, fn)
    with _LOCK:
        _FRAMES[doc_id] = (fid, frame)
    works.log(doc_id, "gatherFrame", rev=frame["rev"], frameId=fid, sha256=frame["sha256"], blocks=len(frame["blocks"]))
    return _view(doc_id)


@router.get("/api/docs/{doc_id}/gather/frame/file")
def gather_frame_file(doc_id: str):
    """고정해 둔 기준본 파일(나눠 주는 바이트 그대로)."""
    from app import server
    s = server._sess(doc_id)
    fid = _store(doc_id)["frameId"]
    data = _blob(doc_id, f"frame-{fid}.hwpx") if fid else None
    if data is None:
        raise _err(404, "noFrame")
    stem = s.name[:-5] if s.name.lower().endswith(".hwpx") else s.name
    return Response(data, media_type=s.kit["mime"], headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(stem + '_기준본.hwpx')}", "Cache-Control": "no-store"})


# ---- 끝점: 기관 문서(§2) -----------------------------------------------------------------------------------------

def _part_id(part):
    if not isinstance(part, str) or not works.ID.match(part):
        raise _err(400, "badPart", "기관 문서 id 가 올바르지 않습니다")


@router.put("/api/docs/{doc_id}/gather/parts/{part}")
def gather_part_put(doc_id: str, part: str, body: dict = Body(default={})):
    """기관 문서를 취합에 넣거나(없던 문서) 반영할 기관·공통 자리 포함을 바꾼다. `orgs: []` = 미지정(아무것도 안 넣음 — 「가리지 않음」 이 아니다)."""
    from app import server
    _part_id(part)
    orgs, common = body.get("orgs"), body.get("common")
    if (orgs is not None and not (isinstance(orgs, list) and all(isinstance(x, str) and x for x in orgs))) or (common is not None and not isinstance(common, bool)):
        raise _err(400, "badValue", "orgs 는 기관 열쇠 목록, common 은 true·false")
    server._sess(doc_id)
    project = ((works.work(doc_id) or {}).get("task") or {}).get("project") or ""
    new = part not in _store(doc_id)["parts"]
    name = ""
    if new:
        if part == doc_id:
            raise _err(400, "badPart", "취합본 자신은 기관 문서로 넣을 수 없습니다")
        try:
            src = server._sess(part)
        except HTTPException as e:
            raise _err(404, "badPart", "그런 문서가 없습니다") from e
        if src.fmt != "hwpx":
            raise _err(400, "badPart", "hwpx 문서만 기관 문서로 넣을 수 있습니다")
        theirs = ((works.work(part) or {}).get("task") or {}).get("project") or ""
        if theirs and theirs != project:
            raise _err(400, "badPart", f"다른 과제(「{theirs}」)의 문서입니다")
        name = src.name

    def fn(G):
        rec = G["parts"].get(part)
        if rec is None:
            old = (G.get("gone") or {}).pop(part, None) or {}   # 뺐다가 다시 넣은 문서 — 같은 판이면 넣은 기록을 잇는다(이어 넣는 표의 행은 기록으로만 「이미 넣음」 을 안다)
            rec = G["parts"][part] = {"name": name, "added": _now(), "orgs": [], "common": True, "frameId": G["frameId"], "decisions": {}, "llm": None,
                                      "applied": old.get("applied") or {} if old.get("frameId") == G["frameId"] else {}}
            G["order"].append(part)
        if orgs is not None:
            rec["orgs"] = list(dict.fromkeys(orgs))
        if common is not None:
            rec["common"] = common
    _change(doc_id, fn)
    with _LOCK:
        _PLANS.pop((doc_id, part), None)
    if new and works.work(part) is not None:   # 문서 목록에 종류를 보이려는 꼬리표 — 화면의 칸 바꾸기(다른 문서를 내보냄)를 거치지 않는다
        server.work_task(part, {"kind": "rnd", "file": "part", "job": "plan_merge", "project": project})
    return _view(doc_id)


@router.delete("/api/docs/{doc_id}/gather/parts/{part}")
def gather_part_delete(doc_id: str, part: str):
    """취합에서 뺀다 — 넣은 내용은 취합본에 그대로(되돌리려면 실행 취소). 문서 자체는 안 지운다."""
    from app import server
    server._sess(doc_id)

    def fn(G):
        _rec(G, part)
        rec = G["parts"].pop(part)
        G["order"] = [p for p in G["order"] if p != part]
        if rec.get("applied"):
            G.setdefault("gone", {})[part] = {"frameId": rec.get("frameId"), "applied": rec["applied"], "at": _now()}
    _change(doc_id, fn)
    with _LOCK:
        _PLANS.pop((doc_id, part), None), _LINKS.pop((doc_id, part), None)
        if (_DROPS.get(doc_id) or {}).get("from") == part:
            del _DROPS[doc_id]
    task = (works.work(part) or {}).get("task")
    if task and task.get("file") == "part":   # 종류 꼬리표만 뗀다 — 과제·할 일은 그대로(같은 과제의 문서로 남아 다시 넣을 수 있다)
        works.update(part, task={**task, "file": ""})
    return _view(doc_id)


# ---- 끝점: 자리 연결 · 사람 고름 · LLM 검토(§4-1~§4-3) --------------------------------------------------------------

@router.get("/api/docs/{doc_id}/gather/parts/{part}/links")
def gather_links(doc_id: str, part: str):
    return _links_view(doc_id, part)


@router.post("/api/docs/{doc_id}/gather/parts/{part}/links")
def gather_links_post(doc_id: str, part: str):
    """다시 맞춤 — 기준본 ↔ 기관 문서를 다시 견준다. 사람·LLM 의 결정은 열쇠가 같으면 유지(열쇠 = 기준 판 + 경계 + 종류 + 내용 지문)."""
    return _links_view(doc_id, part, fresh=True)


@router.put("/api/docs/{doc_id}/gather/parts/{part}/links/{key}")
def gather_decide(doc_id: str, part: str, key: str, body: dict = Body(...)):
    """사람이 고름 `{value: keep | skip | null}` — keep 은 넣을 수 있는(ready) 것에만 뜻이 있다(막힌 상태를 넣게 하지 못한다 — 판정은 그대로). null = 지움(앞선 LLM 결정이 있으면 그것으로)."""
    value = body.get("value")
    if value not in ("keep", "skip", None):
        raise _err(400, "badValue", "value 는 keep · skip · null")
    view = _links_view(doc_id, part)
    if key not in {it["key"] for it in view["items"]}:
        raise _err(404, "noKey")

    def fn(G):
        rec = _rec(G, part)
        ds = dict(rec.get("decisions") or {})
        old = ds.get(key) if isinstance(ds.get(key), dict) else None
        llm = old if old and old.get("source") == "llm" else (old or {}).get("llm")   # 사람이 덮기 전의 LLM 결정 — 지우면 되살린다
        if value is None:
            ds.pop(key, None)
            if llm:
                ds[key] = llm
        else:
            ds[key] = {"value": value, "source": "user", "at": _now()}
            if llm:   # LLM 의견(성격·까닭)은 그 줄에 계속 보인다
                ds[key].update({k: llm[k] for k in ("nature", "reason") if llm.get(k)}, llm=llm)
        rec["decisions"] = ds
    _change(doc_id, fn)
    with _LOCK:
        _PLANS.pop((doc_id, part), None)
    return _links_view(doc_id, part)


@router.post("/api/docs/{doc_id}/gather/parts/{part}/llm")
def gather_llm(doc_id: str, part: str):
    """LLM 순회 검토(§4-3) — 넣을 수 있는 작성 내용을 취합본의 장마다 나눠 병렬로 묻는다(merge_gather_llm). 권한은 좁히는 쪽뿐이고 사람이 고른 것은 보내지도 않는다.
    받은 결정은 source llm 로 저장: 사람 것은 그대로 · 이제 없는 열쇠의 앞선 LLM 결정은 버림 · 이번 답으로 갈아 끼움. 요약은 parts[part].llm, 프롬프트·답은 `gather/llm-<part>.json`.
    ponytail: 요청 하나가 끝까지 기다린다(merge_api.merge_links_llm 과 같다) — 분 단위가 되면 배경 작업 + 폴링으로."""
    from app import job_prompts
    s, G, frame, stale = _ctx(doc_id)
    rec = _rec(G, part)
    why = _blocked(rec, frame, stale)
    if why:
        raise _err(409, why)
    job = job_prompts.for_work(doc_id)   # 이 작업의 할 일 프롬프트(jobs/plan_merge.md — spec_작업 ② §13)
    try:
        src = _part_sess(part)
        with _both(s, src):   # 자료는 잠금 안에서 불변 입력으로(prepare 는 LLM 을 안 부른다) — 호출은 잠금 밖
            got = _judged(s, src, G, frame, part)
            names = {o["key"]: o["name"] for o in frame.get("orgs") or ()}
            plan = L.prepare(got["items"], frame, _side(s), _side(src), job=job, orgs=[names.get(k, k) for k in rec.get("orgs") or ()])
            keys = {h["key"] for h in got["items"]}
    except _Why as e:
        raise _err(409, e.code, e.message) from e
    res = L.run(plan)
    called = [u for u in res["units"] if u.get("call")]
    if called and all(u["call"].get("error") == "off" for u in called):   # 꺼진 LLM 을 「검토 실패 → 전부 보류」 로 적지 않는다(스크립트만으로 넣을 수 있다 — §4-3)
        raise _err(409, "noLlm")
    at = _now()

    def fn(G2):
        r = _rec(G2, part)
        ds = {k: v for k, v in (r.get("decisions") or {}).items() if isinstance(v, dict) and (v.get("source") == "user" or k in keys)}
        ds.update({k: v for k, v in res["decisions"].items() if (ds.get(k) or {}).get("source") != "user"})
        r["decisions"] = ds
        r["llm"] = {"at": at, "units": [{k: u[k] for k in ("title", "pages", "over", "targets", "opinions", "chars", "call", "held") if k in u} for u in res["units"]],   # prompt·answer 는 크다 — 따로
                    "job": res.get("job"), "guide": res.get("guide"), "held": len(res["held"]), "rejected": len(res["rejected"]), "left": res.get("left", 0), "counts": res.get("counts")}
    _change(doc_id, fn)
    last = {"at": at, "part": part, "units": [{"n": i, "title": u["title"], "pages": u["pages"], "targets": u["targets"], "opinions": u.get("opinions", 0), "tables": None,
                                               "error": (u.get("call") or {}).get("error"), "prompt": u.get("prompt"), "answer": u.get("answer")} for i, u in enumerate(res["units"])],
            "opinions": res["opinions"], "rejected": res["rejected"]}
    _blob(doc_id, f"llm-{part}.json", json.dumps(last, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    with _LOCK:
        _PLANS.pop((doc_id, part), None)
    return _links_view(doc_id, part)


# ---- 끝점: 넣기 계획 → 반영(§4-4 · §4-5) ---------------------------------------------------------------------------

def _tx(s, src, run, op, req, code):
    """구조 편집 트랜잭션 하나(server._transact — 실행 취소 1 · 문서 전체 표준 검사, 걸리면 전부 복원·422) — 두 세션 잠금 안에서. 스키마 위반의 기준선에 기관 문서의 것을 더한다
    (문서 사이 복사는 원본에 한글이 써 둔 위반을 내용과 함께 가져온다 — merge_api.merge_apply 와 같은 검사). run 의 ValueError·KeyError(400)는 이 끝점의 오류 꼴로."""
    from app import server

    def check(s_, out, base, header):
        chk = s_.kit["check"]
        return chk.verdict(s_.doc, {"schema": Counter(base["schema"]) + Counter(server.owpml_base(src)["schema"]), "rules": base["rules"]}, chk.check_doc(s_.doc))
    try:
        return server._transact(s, run, op, req=req, check=check)
    except HTTPException as e:
        if e.status_code == 400 and isinstance(e.detail, str):
            raise (_err(409, "stalePlan", e.detail) if e.detail == DROP.STALE else _err(400, code, e.detail)) from e
        raise


@router.post("/api/docs/{doc_id}/gather/parts/{part}/plan")
def gather_plan(doc_id: str, part: str):
    """넣기 계획 — 넣을 수 있고(ready) 결정이 skip·check 가 아닌 작성 내용마다 넣을 것을 센다. **문서는 안 바뀐다**. 계획에 적어 두는 것 = 두 문서의 차례 · 기준 판 · 취합 설정의 판 · 분석 실행(반영이 다시 본다)."""
    s, G, frame, stale = _ctx(doc_id)
    why = _blocked(_rec(G, part), frame, stale)
    if why:
        raise _err(409, why)
    try:
        src = _part_sess(part)
        with _both(s, src):
            got = _judged(s, src, G, frame, part)
            pl = MG.plan(got["items"], frame, _side(s), _side(src))
            plan = {"planId": uuid.uuid4().hex[:12], "part": part, "toRev": s.rev, "partRev": src.rev, "frameId": frame["frameId"], "version": G["version"],
                    "runs": [_runs(s), _runs(src)], "plan": pl}
    except _Why as e:
        raise _err(409, e.code, e.message) from e
    with _LOCK:
        _PLANS[(doc_id, part)] = plan
    by, total = {h["key"]: _ends(h) for h in got["items"]}, Counter()
    for it in pl["items"]:
        total.update({k: v for k, v in (it.get("counts") or {}).items() if isinstance(v, int)})
    return {"planId": plan["planId"], "part": part, "todo": pl["todo"], "counts": dict(total),
            "items": [{**it, "to": by[it["key"]][0], "from": by[it["key"]][1]} for it in pl["items"]],   # 계획 줄도 두 문서의 그 자리로 갈 수 있게(to.at · from.at)
            "skipped": pl["skipped"], "calc": pl["calc"], "dropped": pl["dropped"]}


@router.post("/api/docs/{doc_id}/gather/parts/{part}/apply")
def gather_apply(doc_id: str, part: str, body: dict = Body(...)):
    """{planId} → 그 계획을 취합본에 반영: 편집 하나(실행 취소 1 · rev +1 · 기록 `gatherFill`). 기관 문서는 안 바뀐다. 넣은 것은 parts[part].applied 에(판은 안 올린다 — 문서 차례가 바뀌어 계획은 어차피 낡는다)."""
    from app import server
    with _LOCK:
        plan = _PLANS.get((doc_id, part))
    if plan is None or plan["planId"] != body.get("planId"):
        raise _err(409, "stalePlan", "계획이 없거나 바뀌었습니다 — 다시 계획하세요")
    try:
        src = _part_sess(part)
    except _Why as e:
        raise _err(409, "stalePlan", e.message) from e
    s = server._sess(doc_id)
    with _both(s, src):   # 기관 문서도 같이 잠근다 — 반영 중 원본이 바뀌면 계획 때의 것과 바뀐 것이 섞인다
        G = _store(doc_id)
        rec, frame = G["parts"].get(part), _frame(doc_id, G["frameId"])
        ok = (rec is not None and frame is not None and server.DOCS.get(s.id) is s and plan["toRev"] == s.rev and plan["partRev"] == src.rev
              and plan["frameId"] == frame["frameId"] == rec.get("frameId") and plan["version"] == G["version"] and plan["runs"] == [_runs(s), _runs(src)] and not _stale(s, frame))
        if not ok:
            with _LOCK:
                _PLANS.pop((doc_id, part), None)
            raise _err(409, "stalePlan")
        if not plan["plan"]["todo"]:
            with _LOCK:
                _PLANS.pop((doc_id, part), None)
            return {"nothing": True, **s.state()}
        done = {}

        def run():
            done.update(MG.apply(s.doc, src.doc, plan["plan"]))
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None, "log": {"planId": plan["planId"], "part": part, "counts": done["counts"]}}
        try:
            out, after = _tx(s, src, run, "gatherFill", {"planId": plan["planId"], "part": part}, "applyFailed")
        finally:
            with _LOCK:
                _PLANS.pop((doc_id, part), None)
        if after is None:
            return out
        at = _now()

        def fn(G2):
            r = G2["parts"].get(part)
            if r is not None:
                r["applied"] = {**(r.get("applied") or {}), **{k: {**v, "at": at} for k, v in done["applied"].items()}}
        _change(doc_id, fn, bump=False)
        return {"counts": done["counts"], "calc": done["calc"], "dropped": done["dropped"], "skipped": done["skipped"], **s.state()}


# ---- 끝점: 끌어 넣기(§4-6) ----------------------------------------------------------------------------------------

@router.post("/api/docs/{doc_id}/gather/drop/plan")
def gather_drop_plan(doc_id: str, body: dict = Body(...)):
    """{from(기관 문서), srcId(끈 줄), afterId(놓은 블록)} → 끌어 넣기 계획(두 문서 모두 안 바뀜). 끌 수 있는 출처는 그 취합에 든 기관 문서뿐. 기준본은 없어도 된다(기준본에서 나오지 않은 문서를 넣는 길)."""
    from app import server
    frm, src_id, after_id = body.get("from"), body.get("srcId"), body.get("afterId")
    if not all(isinstance(x, str) and x for x in (frm, src_id, after_id)):
        raise _err(400, "badValue", "from · srcId · afterId 가 있어야 합니다")
    s = server._sess(doc_id)
    if frm not in _store(doc_id)["parts"]:
        raise _err(400, "notPart")
    try:
        src = _part_sess(frm)
    except _Why as e:
        raise _err(400, "notPart", e.message) from e
    with _both(s, src):
        tg, pg = HR.graph(s), HR.graph(src)
        if pg is None:   # 그래프가 없으면 절의 범위를 몰라 끈 줄 하나만 가게 된다 — 말없이 그러지 않는다
            raise _err(409, "noHeadings", "기관 문서의 헤딩 분석이 없어 절의 범위를 정할 수 없습니다 — 먼저 분석하세요(스크립트)")
        try:
            p = DROP.plan({"doc": s.doc, "graph": tg}, {"doc": src.doc, "graph": pg}, src_id, after_id)
        except (KeyError, ValueError) as e:   # DropError = 사람에게 보일 까닭
            raise _err(400, "badDrop", str(e)) from e
        plan = {"planId": uuid.uuid4().hex[:12], "from": frm, "toRev": s.rev, "partRev": src.rev, "runs": [_run(tg), _run(pg)], "plan": p}
    with _LOCK:
        _DROPS[doc_id] = plan
    return {"planId": plan["planId"], "from": frm, **{k: p[k] for k in ("range", "after", "owner", "convert", "dropped")}}


@router.post("/api/docs/{doc_id}/gather/drop/apply")
def gather_drop_apply(doc_id: str, body: dict = Body(...)):
    """{planId, convert(틀 맞춤 — 기본 켬)} → 계획대로 넣는다: 편집 하나(실행 취소 1 · rev +1 · 기록 `gatherDrop`). 계획 때와 같은 두 그래프(실행 번호가 같음)로 다시 풀어 계획과 다르면 409."""
    from app import server
    with _LOCK:
        plan = _DROPS.get(doc_id)
    if plan is None or plan["planId"] != body.get("planId"):
        raise _err(409, "stalePlan", "계획이 없거나 바뀌었습니다 — 다시 끌어 놓아 주세요")
    convert = body.get("convert", True) is not False
    try:
        src = _part_sess(plan["from"])
    except _Why as e:
        raise _err(409, "stalePlan", e.message) from e
    s = server._sess(doc_id)
    with _both(s, src):
        tg, pg = HR.graph(s), HR.graph(src)
        if (plan["from"] not in _store(doc_id)["parts"] or server.DOCS.get(s.id) is not s or plan["toRev"] != s.rev or plan["partRev"] != src.rev
                or plan["runs"] != [_run(tg), _run(pg)]):
            with _LOCK:
                _DROPS.pop(doc_id, None)
            raise _err(409, "stalePlan", DROP.STALE)
        done = {}

        def run():
            done.update(DROP.apply(s.doc, src.doc, plan["plan"], tg, pg, convert=convert))
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None,
                    "log": {"planId": plan["planId"], "from": plan["from"], "after": plan["plan"]["after"]["id"], "blocks": done["blocks"], "converted": done["converted"]}}
        try:
            out, after = _tx(s, src, run, "gatherDrop", {"planId": plan["planId"], "from": plan["from"], "convert": convert}, "badDrop")
        finally:
            with _LOCK:
                _DROPS.pop(doc_id, None)
        if after is None:
            return out
        return {**{k: done[k] for k in ("blocks", "converted", "kept", "labels", "fitted", "dropped", "ids")}, **s.state()}
