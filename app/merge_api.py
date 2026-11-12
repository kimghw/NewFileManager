"""병합 API — 자리 연결(spec_병합 ② §0-1 ①②③ · §3 · §8 가운데 읽기 · 다시 내기 · 사람 고침). + LLM 보정(`POST …/merge-links/llm`) · 넣기 계획(`POST …/merge-links/plan`) · 반영(`POST …/merge-links/apply`) — 아래 함수 설명.

- `GET  /api/docs/{to}/merge-links` → {project, from{work, name, rev, reasons[]} | null, to{…}, diff[구분 값이 다른 곳], stale, groups[], counts} — 목적 문서(연차보고서) 기준.
  원본 = 같은 과제(`task.project`)에서 `task.file = plan` 인 작업(없으면 from null). 못 내는 까닭은 **문서별로**: noHeadings(헤딩 2·3단계 결과 없음) · noValues(구분 값 없음) ·
  notApplied(목적 문서에 값을 반영하지 않음) · unsupportedForm(hwpx 아님). 두 문서의 값이 다르면 diff 에 다른 곳(valuesDiffer 는 목적 문서 까닭에도). 까닭이 있으면 groups 는 비어 있다.
- `POST /api/docs/{to}/merge-links` → 요약을 다시 만들어 같은 몸통(사람이 고친 것은 유지).
- `PUT  /api/docs/{to}/merge-links/{groupId}` `{from: 원본 묶음 key | null}` 또는 `{reset: true}` → 사람이 연결을 고르거나(null = 끊음) 스크립트 결과로 되돌림. 400 후보가 될 수 없는 묶음 · 404 그런 묶음 없음.
저장: 목적 작업 폴더 `merge.json` {from(작업 id), fixed{목적 key: {from, source: user}}, toRev, fromRev}(작업 저장이 꺼져 있으면 메모리). 문서가 그 뒤 바뀌었으면 stale 만 보인다(다시 하라고 다그치지 않음)."""
import threading

from fastapi import APIRouter, Body, HTTPException

from app import heading_runs as HR
from app import merge_pairs as P
from app import works

router = APIRouter()
_LOCK = threading.Lock()
_MEM, _CACHE, _PLANS = {}, {}, {}   # (끝의 _PLANS = 목적 작업 id → 마지막 넣기 계획 — 메모리만, 서버를 다시 켜면 다시 계획)  # 작업 저장이 꺼졌을 때의 merge.json · 요약 캐시(문서 차례가 같으면 다시 안 만든다 — 실제 쌍 4.6초)
_FIXED = {}   # 목적 작업 id → (열쇠, 고정 자리 요약) — _fixed_brief
ZERO = {"paired": 0, "ambiguous": 0, "toOnly": 0, "fromOnly": 0}
TABLE_KEYS, FIXED_KEYS = ("filled", "rowsAdded", "shaped"), ("filled", "shaped", "labels", "fitted", "flowed")   # 반영 응답·기록에 싣는 수(merge_tables.apply · merge_fixed.apply)


def _store(wid, data=None):
    """merge.json 읽기(data None) · 쓰기."""
    d = works.folder(wid)
    if data is None:
        return (works._read_json(d / "merge.json") if d is not None and (d / "merge.json").is_file() else _MEM.get(wid)) or {}
    if d is not None:
        works._write_json(d / "merge.json", data)
    else:
        _MEM[wid] = data
    return data


def _mate(to_id, saved):
    """(과제 이름, 원본 작업 id | None) — 같은 과제의 사업계획서. 사람이 원본을 따로 골랐으면(saved.from) 그것."""
    task = (works.work(to_id) or {}).get("task") or {}
    project = task.get("project") or ""
    if saved.get("from") and works.work(saved["from"]):
        return project, saved["from"]
    for w in works.list_works() if project else ():
        t = w.get("task") or {}
        if w["id"] != to_id and t.get("project") == project and t.get("file") == "plan":
            return project, w["id"]
    return project, None


def _read(doc_id, target=False):
    """문서 하나에서 요약에 드는 것을 읽는다(세션 잠금 안에서 짧게) → {id, name, rev, reasons, values, blocks, graph, tables}."""
    from app import server   # server 가 이 모듈을 include 한다(순환 import 피함)
    s = server._sess(doc_id)
    with s.lock:
        hwpx = s.fmt == "hwpx"
        g, t = (HR.graph(s), HR.tables(s)) if hwpx else (None, None)
        applied, settings = s.division.get("applied"), s.division.get("settings")
        values = (applied or {}).get("values") or (settings or {}).get("values")
        reasons = [r for r, bad in (("unsupportedForm", not hwpx), ("noHeadings", hwpx and not (g and t)), ("noValues", hwpx and not values),
                                    ("notApplied", target and hwpx and bool(values) and not applied)) if bad]
        return {"id": s.id, "name": s.name, "rev": s.rev, "reasons": reasons, "values": values, "doc": s.doc, "blocks": None if reasons else s.doc.blocks(), "graph": g, "tables": t}


def _summary(side):
    key = (side["id"], side["rev"], repr(side["values"]), id(side["graph"]), id(side["tables"]))
    with _LOCK:
        if _CACHE.get(side["id"], (None,))[0] != key:
            _CACHE[side["id"]] = (key, P.summarize(side["blocks"], side["graph"], side["tables"], side["values"]))
        return _CACHE[side["id"]][1]


def _alive(applied, to):
    """넣은 기록(merge.json `applied`) 가운데 지금도 믿을 것 — 넣은 블록 id(`ids`)를 적어 둔 기록은 그 블록이 하나라도 지금 문서에 있어야 한다. merge.json 은 문서의 실행 취소 단위에 안 들어,
    반영 → 실행 취소 뒤에도 기록이 남아 빈 자리를 「이미 넣음」 으로 건너뛰었다(astra 검토 2026-11-12). 블록이 사라졌으면 기록을 안 믿는다 — 그 자리가 비었으면 다시 넣을 일이 되고,
    글이 있으면 계획이 `occupied` 로 본다(겹쳐 넣지 않는다). `ids` 가 없는 옛 기록 · 문서를 다시 읽어 id 가 바뀐 경우도 같은 길(자리의 글로 판정)."""
    from app.division_profiles import _structure as structure
    if not applied or not to.get("blocks"):
        return applied or {}
    now = {b["id"] for b in structure.iter_blocks(to["blocks"])}
    return {k: v for k, v in applied.items() if not (v or {}).get("ids") or any(i in now for i in v["ids"])}


def _forced(saved, only=None):
    """merge.json `tables` = LLM 검토·사람이 정한 표 짝 {목적 표 id: {from, source(llm|user), reason, format}}(spec_병합 ② §5-1 「표 짝 검토」). only = 그 source 만."""
    return {k: v for k, v in (saved.get("tables") or {}).items() if isinstance(v, dict) and (only is None or v.get("source") == only)}


def _maps(saved):
    """merge.json `tableMaps` = 표 대응 에이전트가 낸 대응 {목적 표 id: {from, records, grow, fields, mark, …}}(spec_병합 ② §5-3 9)."""
    return {k: v for k, v in (saved.get("tableMaps") or {}).items() if isinstance(v, dict) and v.get("from")}


_ORIG = {}   # 목적 작업 id → (올린 원본 sha256, {칸 id: {text, top, bottom}}) — _orig


def _orig(doc_id):
    """목적 문서로 올린 원본이 **등록된 빈 양식**(그 양식 정보 `match.sha256` 에 원본의 sha256, 또는 `match.blank` 에 원본의 내용 지문 — merge_table_map.blank_fp)일 때 그 원본의 표 칸 {칸 id: {text, top, bottom}} | None(spec_병합 ② §5-3 6 「서식 예시」).
    표 대응이 서식의 예시 행을 덮어도 되는지 가리는 데만 쓴다 — None 이면 글이 든 칸은 모두 사람 글로 본다(이미 작성한 보고서를 올린 경우). 칸 id 는 읽을 때 차례로 붙어 원본을 다시 읽으면 처음 연 때와 같다."""
    from app import heading_forms as HF
    from app import merge_table_map as MM
    from app import server
    from app.hwpx_doc import HwpxDoc
    s = server._sess(doc_id)
    try:
        form, sha = HF.for_session(s), HF.doc_sha(s)
        cond = {"sha256": HF.parse(form["text"])["sha256"], "blank": HF.blank_fps(form["text"])} if form else None
        if not cond or not sha or not (cond["sha256"] or cond["blank"]):
            return None
        hit = _ORIG.get(doc_id)
        if hit is None or hit[0] != sha:
            cells, blocks = {}, HwpxDoc(s.original).blocks()

            def walk(seq):
                for b in seq:
                    lines = b.get("borderFills") or {}
                    for c in b.get("cells") or ():
                        ln = lines.get(c.get("bf")) or {}
                        cells[c["id"]] = {"text": c.get("text") or "", "top": MM._kind(ln.get("t")), "bottom": MM._kind(ln.get("b"))}
                        walk(c.get("blocks") or ())
            walk(blocks)
            hit = _ORIG[doc_id] = (sha, cells, MM.blank_fp(blocks))
        return hit[1] if sha.lower() in cond["sha256"] or hit[2] in cond["blank"] else None   # 바이트가 같거나(sha256) 내용이 같다(blank — 다시 저장·hwp 변환으로 바이트만 다른 빈 양식)
    except Exception:   # 예시 판정은 덤이다 — 못 읽으면 「예시 아님」 으로(덮지 않는 쪽)
        return None


def _link_form(doc_id):
    """목적 문서의 양식 정보(heading_forms.pin 꼴) | None — 「자리 연결」 절(연결 코멘트 — spec_병합 ② §5-3 1)을 읽고 쓰는 곳."""
    from app import heading_forms as HF
    from app import server
    try:
        return HF.pin(server._sess(doc_id))
    except Exception:
        return None


def _links_text(doc_id):
    """목적 양식의 「자리 연결」 절 글(LLM 프롬프트에 붙일 것) | ""."""
    from app import heading_forms as HF
    form = _link_form(doc_id)
    return HF.section(HF.body(form["text"]), HF.LINK_SECTION) if form else ""


def _link_comments(doc_id):
    from app import heading_forms as HF
    form = _link_form(doc_id)
    return HF.comments(form["text"], HF.LINK_SECTION) if form else []


def _fixed_brief(to, frm, saved):
    """연결 목록에 싣는 고정 자리 요약 {counts, todo} — 넣기 계획과 같은 셈(merge_fixed.plan)이되 표 칸 넣기 계획 없이(계산 칸·겹치는 칸에서 조금 다를 수 있다 — 정확한 수는 넣기 계획).
    두 문서의 차례·분석·넣은 기록이 같으면 다시 안 센다(실제 쌍 1.9초)."""
    import json

    from app import merge_fixed, merge_table_map, server
    if to.get("doc") is None or frm.get("doc") is None:   # 문서 없이 요약만 끼운 읽기(시험) — 고정 자리는 문서의 지금 글을 본다
        return None
    applied = _alive(saved.get("applied"), to)
    forced, maps = _forced(saved), _maps(saved)
    key = (to["id"], to["rev"], frm["id"], frm["rev"], repr(to["values"]), repr(frm["values"]), id(to["graph"]), id(to["tables"]), id(frm["graph"]), id(frm["tables"]),
           tuple(sorted((k, (v or {}).get("hash")) for k, v in applied.items())), tuple(sorted((k, v.get("from"), v.get("source")) for k, v in forced.items())),
           json.dumps(maps, sort_keys=True, ensure_ascii=False) if maps else "")
    with _LOCK:
        hit = _FIXED.get(to["id"])
    if hit is None or hit[0] != key:
        try:
            with server._sess(to["id"]).lock:
                sides = (merge_fixed._side(to), merge_fixed._side(frm))
                mp = merge_table_map.plan(*sides, maps, _orig(to["id"])) if maps else None   # 표 대응(② §5-3)이 맡은 표는 같은 이름 자리 셈에서 뺀다
                p = merge_fixed.plan(to, frm, applied=applied, forced=forced, sides=sides, skip=set(mp["owned"]) if mp else ())
            # maps = 대응이 맡은 표 수 · mapOpen = 같은 표로 이었는데 칸을 못 맞춰 표 대응이 필요한 표 수(표 묶음 쪽은 넣기 계획이 센다 — plan 의 maps.counts.open)
            counts = {**p["counts"], "maps": len(mp["owned"]) if mp else 0, "mapStale": mp["counts"]["stale"] if mp else 0, "mapOpen": len(merge_table_map.targets(None, p))}
            brief = {"counts": counts, "todo": p["todo"] + (mp["todo"] if mp else 0)}
        except Exception as e:   # 덤으로 싣는 요약이다 — 여기서 틀어져도 연결 목록(묶음)은 나가야 한다. 「못 셈」 은 「0」 과 다르다: error 를 싣고(화면이 보인다) 다음 읽기에 다시 센다(안 담아 둠)
            return {"counts": None, "todo": 0, "error": f"{type(e).__name__}: {e}"}
        hit = (key, brief)
        with _LOCK:
            _FIXED[to["id"]] = hit
    return hit[1]


def _view(to_id, fresh=False):
    saved = _store(to_id)
    project, from_id = _mate(to_id, saved)
    to = _read(to_id, target=True)
    frm = _read(from_id) if from_id else None
    head = lambda x: {"work": x["id"], "name": works.shown_name(x["name"], (works.work(x["id"]) or {}).get("task")), "rev": x["rev"], "reasons": x["reasons"]}  # noqa: E731 — name = 보이는 이름(spec_작업 ② §10: 목적 문서는 과제 이름이 뒤에)
    out = {"project": project, "to": head(to), "from": head(frm) if frm else None, "diff": [], "stale": False, "groups": [], "counts": dict(ZERO),
           "comments": _link_comments(to_id)}   # 연결 코멘트(목적 양식의 양식 정보 「자리 연결」 절 — spec_병합 ② §5-3 1)
    if frm and to["values"] and frm["values"]:
        out["diff"] = P.values_diff(frm["values"], to["values"])
        if out["diff"]:
            out["to"]["reasons"].append("valuesDiffer")
    if not frm or out["to"]["reasons"] or out["from"]["reasons"]:
        return out, None
    if fresh:
        with _LOCK:
            _CACHE.pop(to_id, None), _CACHE.pop(from_id, None), _FIXED.pop(to_id, None)
    ts, fs = _summary(to), _summary(frm)
    fixed = {k: v for k, v in (saved.get("fixed") or {}).items() if isinstance(v, dict)}
    out.update(P.pair(ts, fs, fixed=fixed))
    out["fixed"] = _fixed_brief(to, frm, saved)   # 같은 이름 자리(고정 자리 — spec_병합 ② §5-1): 묶음(groups·counts)과 따로 센다 {counts, todo}
    out["llm"] = saved.get("llm")   # 마지막 LLM 보정 요약(단위별 쪽·묶음 수·호출) — 없으면 None
    out["stale"] = bool(fixed) and (saved.get("toRev"), saved.get("fromRev")) != (to["rev"], frm["rev"])
    return out, (ts, fs, saved, to, frm)


@router.get("/api/docs/{doc_id}/merge-links")
def merge_get(doc_id: str):
    return _view(doc_id)[0]


@router.post("/api/docs/{doc_id}/merge-links")
def merge_pairs_post(doc_id: str, body: dict = Body(default={})):
    """{from?: 원본 작업 id} — 요약을 다시 만든다(원본을 따로 고르면 저장)."""
    if body.get("from"):
        if not works.work(body["from"]):
            raise HTTPException(404, "그런 작업이 없습니다")
        _store(doc_id, {**_store(doc_id), "from": body["from"]})
    return _view(doc_id, fresh=True)[0]


@router.put("/api/docs/{doc_id}/merge-links/{group_id}")
def merge_pair_put(doc_id: str, group_id: str, body: dict = Body(...)):
    view, ctx = _view(doc_id)
    if ctx is None:
        raise HTTPException(409, "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)")
    ts, fs, saved, to, frm = ctx
    t = next((x for x in ts if x["key"] == group_id), None)
    if t is None:
        raise HTTPException(404, "그런 자리 묶음이 없습니다")
    fixed = dict(saved.get("fixed") or {})
    if body.get("reset"):
        fixed.pop(group_id, None)
    else:
        key = body.get("from")
        f = next((x for x in fs if x["key"] == key), None)
        if key is not None and (f is None or P.score(t, f) is None):
            raise HTTPException(400, "이을 수 없는 묶음입니다(구분·종류가 다르거나 맥락 차년도·기관이 어긋남)")
        fixed[group_id] = {"from": key, "source": "user"}
    _store(doc_id, {**saved, "fixed": fixed, "toRev": to["rev"], "fromRev": frm["rev"]})
    return _view(doc_id)[0]


@router.post("/api/docs/{doc_id}/merge-links/llm")
def merge_links_llm(doc_id: str):
    """LLM 보정(spec_병합 ② §4 · §5-1 「표 짝 검토」) — 못 정한 묶음과 **못 정한 표**(같은 표인지 · 어느 기관·차년도의 표인지 — 후보가 있는 것)를 목적 문서의 챕터별(20쪽 이내)로 나눠 병렬로 Opus 에 묻는다.
    받은 연결은 source llm 로 저장한다 — 사람이 고친 묶음·표는 안 건드리고, 스크립트가 낸 연결도 그대로. 앞선 LLM 표 짝은 이번 답으로 바뀐다(다시 검토).
    판단 지침(`merge_guides` links)과 할 일 프롬프트를 단위마다 함께 보내고, 보낸 프롬프트·답은 작업 폴더 `merge_llm_last.json` 에 둔다(화면 「지침」 — `GET …/llm-guide/merge-links`).
    → GET 과 같은 몸통(llm = {at, units[{title, pages, over, targets, tables, call}], none[], rejected, left, job, guide, tables{paired, none, rejected}}). 409 까닭이 남음.
    ponytail: 요청 하나가 끝까지 기다린다(실제 쌍 24초) — 문서가 커져 분 단위가 되면 배경 작업 + 폴링으로."""
    from datetime import datetime

    from app import job_prompts, merge_fixed, merge_llm, server
    view, ctx = _view(doc_id)
    if ctx is None:
        raise HTTPException(409, "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)")
    ts, fs, saved, to, frm = ctx
    mine = _forced(saved, "user")
    tables = None
    if to.get("doc") is not None and frm.get("doc") is not None:   # 문서 없이 요약만 끼운 읽기(시험)에서는 표를 안 본다(_fixed_brief 와 같은 조건)
        try:
            with server._sess(doc_id).lock:
                tables = merge_fixed.review_tables(to, frm, forced=mine)   # 사람이 정한 표만 빼고 — 앞선 LLM 짝은 다시 본다
        except Exception:   # 표 자료를 못 만들어도 묶음 검토는 한다(같은 이름 자리는 덤 — _fixed_brief 와 같은 뜻)
            tables = None
    res = merge_llm.review({"blocks": to["blocks"], "graph": to["graph"]}, {"blocks": frm["blocks"], "graph": frm["graph"]}, view, ts, fs,
                           job=job_prompts.for_work(doc_id), tables=tables,   # 이 작업의 할 일 프롬프트(jobs/<할 일 키>.md — spec_작업 ② §13)를 단위마다 함께 보낸다
                           links=_links_text(doc_id))   # 목적 양식의 「자리 연결」 절(연결 코멘트 — ② §5-3 1)도
    fixed = dict(saved.get("fixed") or {})
    fixed.update({k: v for k, v in res["fixed"].items() if (fixed.get(k) or {}).get("source") != "user"})
    got = res.get("tables") or {"fixed": {}, "none": [], "rejected": []}
    at = datetime.now().isoformat(timespec="seconds")
    llm = {"at": at, "units": [{k: u[k] for k in ("title", "pages", "over", "targets", "tables", "call") if k in u} for u in res["units"]],
           "none": res["none"], "rejected": len(res["rejected"]), "left": res.get("left", 0),   # prompt·answer 는 크다(단위마다 수십 KB) — merge.json 에는 안 싣는다(아래 따로)
           "job": res.get("job"), "guide": res.get("guide"),   # 함께 보낸 할 일 프롬프트 {job, name, sha1} · 판단 지침 {name, title, sha1} | None
           "tables": {"paired": len(got["fixed"]), "none": len(got["none"]), "rejected": len(got["rejected"])}}
    # 표 짝: 사람이 정한 것은 그대로 · 이번에 답이 온 표는 그 답으로(이음 = 바꿈, 「같은 표 없음」 = 앞선 LLM 짝을 지움) · 답이 안 온 표(그 단위의 호출이 실패)는 앞선 LLM 짝을 둔다
    gone = {n["to"] for n in got["none"]}
    pairs_t = {k: v for k, v in _forced(saved).items() if v.get("source") == "user" or k not in gone}
    pairs_t.update({k: v for k, v in got["fixed"].items() if (pairs_t.get(k) or {}).get("source") != "user"})
    _store(doc_id, {**saved, "fixed": fixed, "tables": pairs_t, "llm": llm, "toRev": to["rev"], "fromRev": frm["rev"]})
    _last(doc_id, {"at": at, "units": [{"n": i, "title": u["title"], "pages": u["pages"], "targets": u["targets"], "tables": u.get("tables", 0),
                                        "error": (u.get("call") or {}).get("error"), "prompt": u.get("prompt"), "answer": u.get("answer")} for i, u in enumerate(res["units"])]})
    return _view(doc_id)[0]


# ---- 표 대응 에이전트 · 연결 코멘트(spec_병합 ② §5-3 — 사용자 2026-11-12 "그 테이블을 저테이블에 매핑해주는 에이전트를 하나 호출해서" · "어디어디 테이블이나 단락을 연결해 주라고 코멘트를") ----

_MAP_LAST = {}   # 작업 저장이 꺼졌을 때의 merge_map_last.json


def _map_last(wid, data=None):
    """표 대응이 마지막으로 보낸 프롬프트·답(작업 폴더 `merge_map_last.json` — 표마다 한 단위) 읽기(data None) · 쓰기."""
    d = works.folder(wid)
    if data is None:
        return (works._read_json(d / "merge_map_last.json") if d is not None and (d / "merge_map_last.json").is_file() else _MAP_LAST.get(wid)) or None
    if d is not None:
        works._write_json(d / "merge_map_last.json", data)
    else:
        _MAP_LAST[wid] = data
    return data


def _plan_parts(doc_id, view, saved, to, frm, maps=None):
    """넣기 계획의 표 몫 셋을 한 차례로(세션 잠금 안에서 부른다) → (표 대응 계획, 표 묶음 계획, 같은 이름 자리 계획, 두 쪽 읽을거리). 표 대응이 맡은 표는 나머지 둘에서 뺀다(② §5-3 2).
    maps = 쓸 대응(None = 저장된 것 전부 · {} = 대응 없이 — 「전부 다시」 물을 때)."""
    from app import merge_fixed, merge_table_map, merge_tables
    sides = (merge_fixed._side(to), merge_fixed._side(frm))
    mp = merge_table_map.plan(*sides, _maps(saved) if maps is None else maps, _orig(doc_id))
    own = set(mp["owned"])
    tabs = merge_tables.plan(to, frm, to["values"], frm["values"], view, skip=own)
    fixed = merge_fixed.plan(to, frm, applied=_alive(saved.get("applied"), to), tables_plan=tabs, forced=_forced(saved), sides=sides, skip=own)   # 같은 이름 자리 — 묶음이 넣는 칸은 건너뛴다 · LLM·사람이 정한 표 짝 먼저
    mp["open"] = [t for t, _ in merge_table_map.targets(tabs, fixed)]   # 원본 표는 정해졌는데 칸을 못 맞춘 표 — 표 대응이 필요하다
    return mp, tabs, fixed, sides


@router.post("/api/docs/{doc_id}/merge-links/table-map")
def merge_table_map_post(doc_id: str, body: dict = Body(default={})):
    """표 대응 에이전트(② §5-3) — 원본 표는 정해졌는데 스크립트가 칸을 못 맞춘 목적 표마다 LLM 한 번(병렬 · Opus)으로 행 짝·열 짝을 받아 검증해 `merge.json` `tableMaps` 에 둔다. **문서는 안 바뀐다**
    (넣기 계획 → 반영이 쓴다). 이미 쓸 수 있는 대응이 있는 표는 다시 안 묻는다 — `{again: true}` 면 전부 다시.
    → {at, tables[{to, from, title, records, grow, fields, mark, rejected, error}], asked, mapped}. 409 까닭이 남음."""
    from datetime import datetime

    from app import job_prompts, llm, merge_table_map, server
    view, ctx = _view(doc_id)
    if ctx is None:
        raise HTTPException(409, "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)")
    _, _, saved, to, frm = ctx
    s = server._sess(doc_id)
    again = bool(body.get("again"))
    with s.lock:
        mp, tabs, fixed, (T, F) = _plan_parts(doc_id, view, saved, to, frm, maps={} if again else None)
        user_cut = {k for k, v in _forced(saved, "user").items() if not v.get("from")}   # 사람이 끊은 표는 안 묻는다
        built = [(tid, fid, *merge_table_map.data(T, F, tid, fid)) for tid, fid in merge_table_map.targets(tabs, fixed) if tid not in user_cut]
    ask = [(tid, fid, p, c) for tid, fid, p, c in built if p is not None]
    job, links = job_prompts.for_work(doc_id), _links_text(doc_id)
    jobs = merge_table_map.jobs_for([p for _, _, p, _ in ask], job, links)
    res = llm.ask_all(jobs) if jobs else []
    at = datetime.now().isoformat(timespec="seconds")
    maps, rows, units = dict(_maps(_store(doc_id))), [], []
    pairs_t = dict(_forced(_store(doc_id)))
    for tid, fid, p, c in built:
        if p is None:
            rows.append({"to": tid, "from": fid, "error": c})
    for i, ((tid, fid, p, c), j, r) in enumerate(zip(ask, jobs, res)):
        call = {k: r.get(k) for k in ("backend", "model", "effort", "ms", "costUsd", "error", "retried")}
        m, rejected = merge_table_map.check(c, r["data"]) if r.get("data") is not None else (None, [])
        title = p["target"]["title"]
        units.append({"n": i, "title": f"{title} ({tid})", "pages": None, "targets": 1, "tables": 1 + len(p["sources"]), "error": call.get("error"), "prompt": j["content"], "answer": r.get("data")})
        if m is None:
            maps.pop(tid, None)   # 낡았거나 틀린 앞선 대응은 지운다(다시 물었는데 못 정함)
            rows.append({"to": tid, "from": fid, "title": title, "records": 0, "grow": 0, "fields": 0, "mark": "", "rejected": rejected[:20], "error": call.get("error") or (rejected[-1]["why"] if rejected else "대응을 못 정함"), "call": call})
            continue
        maps[tid] = {**m, "at": at, "source": "llm"}
        if m["from"] != fid and tid in pairs_t and pairs_t[tid].get("source") != "user":   # 같은 절의 다른 표를 골랐다(전 차년도 요약 표 → 그 차년도의 표) — 표 짝도 그 표로
            pairs_t[tid] = {**pairs_t[tid], "from": m["from"], "source": "llm", "reason": m["reason"][:300]}
        rows.append({"to": tid, "from": m["from"], "title": title, "records": len(m["records"]), "grow": len(m["grow"]), "fields": len(m["fields"]), "mark": m["mark"], "rejected": rejected[:20], "error": None, "call": call})
    _store(doc_id, {**_store(doc_id), "tableMaps": maps, "tables": pairs_t})
    if units:
        _map_last(doc_id, {"at": at, "units": units})
    with _LOCK:
        _FIXED.pop(doc_id, None)
    return {"at": at, "tables": rows, "asked": len(ask), "mapped": sum(1 for x in rows if not x.get("error"))}


@router.post("/api/docs/{doc_id}/merge-links/comments")
def merge_link_comment(doc_id: str, body: dict = Body(...)):
    """연결 코멘트 하나 {text}(② §5-3 1) → {formInfo {key, name, how}, comments [{date, text}], created} — 이 문서(목적 문서)의 양식 정보 「자리 연결」 절 코멘트 목록 끝에 한 줄.
    자리 연결 LLM 검토와 표 대응 에이전트가 그 절을 읽는다. 양식별 코멘트(`POST …/divisions/comments` — spec_구분_기준 ② §18)와 같은 저장 길: 맞는 양식이 없으면 코멘트만 든 파일을 만든다.
    문서·세션 상태는 안 바꾼다. 고치기·지우기는 「양식 정보」 편집기에서."""
    import time

    from app import heading_forms as HF
    from app import heading_rules, server
    s = server._sess(doc_id)
    try:
        text = HF.comment_line(body.get("text"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if HF.forms_dir() is None:
        raise HTTPException(503, "양식 정보 저장이 꺼져 있어 코멘트를 남길 수 없습니다(NFM_FORMS)")
    with s.lock:
        name = server.PROFILE.form_of(s.doc.blocks())
    date = time.strftime("%Y-%m-%d")
    try:
        for again in (True, False):   # 그 사이 다른 곳에서 고쳐 sha 가 어긋나면 한 번 다시 읽어 붙인다
            form, created = HF.pin(s), False
            if form is None:
                new = HF.bare(name or s.name, HF.doc_sha(s))
                try:
                    form = HF.get(new["key"])
                except KeyError:
                    form, created = {**new, "sha1": ""}, True
            try:
                saved = HF.save(form["key"], HF.add_comment(form["text"], text, date, HF.LINK_SECTION, HF.LINK_TITLE), expect=form["sha1"], reason="연결 코멘트")
                break
            except heading_rules.StaleVersion:
                if not again:
                    raise
    except (heading_rules.StaleVersion, ValueError, OSError) as e:
        raise HTTPException(503, f"코멘트를 양식 정보에 남기지 못했습니다: {e}") from e
    how = form.get("how")
    if how is None:
        how = "manual"
        try:
            HF.set_choice(s.id, saved["key"])
        except (KeyError, ValueError, OSError):
            pass
    return {"formInfo": {"key": saved["key"], "name": saved["name"], "how": how}, "comments": HF.comments(saved["text"], HF.LINK_SECTION), "created": created}


# ---- LLM 지침·보낸 프롬프트 보기(spec_작업 ② §13 「화면에서 보기」 — 사용자 2026-11-12 "각 LLM이 검토나 작업할때 '지침' 이나 프롬프트를 확인할 수 있으면") ----

_LAST = {}   # 작업 저장이 꺼졌을 때의 merge_llm_last.json
GUIDE_STEPS = {"merge-links": "자리 연결 LLM 검토", "division-review": "구분 기준 LLM 재검토", "division-missing": "구분 기준 — 빠진 자리 검토", "gather": "취합 LLM 검토",
               "table-map": "표 대응 에이전트"}   # 표 대응(spec_병합 ② §5-3) — 표마다 한 단위


def _last(wid, data=None):
    """자리 연결 LLM 검토가 마지막으로 보낸 프롬프트·답(작업 폴더 `merge_llm_last.json` — 크다: 단위마다 수십 KB) 읽기(data None) · 쓰기."""
    d = works.folder(wid)
    if data is None:
        return (works._read_json(d / "merge_llm_last.json") if d is not None and (d / "merge_llm_last.json").is_file() else _LAST.get(wid)) or None
    if d is not None:
        works._write_json(d / "merge_llm_last.json", data)
    else:
        _LAST[wid] = data
    return data


def _division_last(wid):
    """구분 기준 LLM 검토의 마지막 기록(작업 폴더 `divisions/review_<시각>.json` — server.divisions_review 가 payload·prompt·response 를 적어 둔다) | None."""
    d = works.folder(wid)
    files = sorted((d / "divisions").glob("review_*.json")) if d is not None and (d / "divisions").is_dir() else []
    return works._read_json(files[-1]) if files else None


def _guide_units(step, doc_id, part=None):
    """그 검토가 마지막으로 보낸 것 → (at | None, [{n, title, pages, targets, tables, error, prompt, answer}]). part = 취합(step gather)의 기관 문서 id — 기관 문서마다 따로 남는다."""
    from datetime import datetime
    if step in ("merge-links", "gather", "table-map"):
        if step == "gather":
            from app import merge_gather_api
            last = merge_gather_api.llm_last(doc_id, part) or {}   # 취합본 작업 폴더 `gather/llm-<기관 문서 id>.json`(spec_취합 ② §2)
        elif step == "table-map":
            last = _map_last(doc_id) or {}   # 작업 폴더 `merge_map_last.json`(표마다 한 단위)
        else:
            last = _last(doc_id) or {}
        return last.get("at"), [u for u in last.get("units") or () if u.get("prompt")]
    rec = _division_last(doc_id) or {}
    part = rec.get("review" if step == "division-review" else "missing") or {}
    if not part.get("prompt"):
        return None, []
    at = (rec.get("result") or {}).get("at")
    return (datetime.fromtimestamp(at).isoformat(timespec="seconds") if at else None), [
        {"n": 0, "title": GUIDE_STEPS[step], "pages": None, "targets": None, "tables": None, "error": (part.get("call") or {}).get("error"), "prompt": part["prompt"], "answer": part.get("response")}]


@router.get("/api/docs/{doc_id}/llm-guide/{step}")
def llm_guide(doc_id: str, step: str, part: str = None):
    """그 LLM 검토에 함께 보내는 글(계약·판단 지침·할 일 프롬프트·양식 정보 — 자료 빼고)과 마지막으로 보낸 프롬프트의 목록.
    step = merge-links(자리 연결 LLM 검토 — doc_id 는 연차보고서) · division-review(구분 기준 재검토) · division-missing(빠진 자리 검토) ·
    gather(취합 LLM 검토 — doc_id 는 취합본, `?part=<기관 문서 id>` 의 마지막 프롬프트: spec_취합 ② §4-3).
    → {step, name, model(글 | null = 기본 모델), parts[{key: contract|guide|job|form, title, text, source, note}], last: null | {at, units[{n, title, pages, targets, tables, chars, error, has}]}}. 404 모르는 step."""
    from app import division_llm, heading_forms, job_prompts, merge_llm, server
    if step not in GUIDE_STEPS:
        raise HTTPException(404, "그런 LLM 검토가 없습니다")
    s = server._sess(doc_id)
    if step == "merge-links":
        parts, model = merge_llm.parts(job=job_prompts.for_work(doc_id), links=_links_text(doc_id)), merge_llm.MODEL
    elif step == "table-map":
        from app import merge_table_map
        parts, model = merge_table_map.parts(job=job_prompts.for_work(doc_id), links=_links_text(doc_id)), merge_table_map.MODEL
    elif step == "gather":
        from app import merge_gather_llm
        parts, model = merge_gather_llm.parts(job=job_prompts.for_work(doc_id)), merge_gather_llm.MODEL
    else:
        review = step == "division-review"
        parts = [{"key": "contract", "title": "계약 — 역할 · 자료 설명 · 답의 꼴 · 판단 기준", "text": division_llm.CONTRACT if review else division_llm.MISSING_CONTRACT, "source": "app/division_llm.py",
                  "note": "코드에 든 글입니다 — 양식마다 다른 사실·요청은 아래 양식 정보에 적습니다"}]
        form = server._division_form(s)
        if form and division_llm.form_part(form):
            parts.append({"key": "form", "title": f"양식 정보 — {form.get('name') or form.get('key')}", "text": heading_forms.body(form.get("text")), "source": "",
                          "note": "양식마다 관리하는 사실·요청 — 「양식 정보」 단추에서 고치면 다음 실행부터 적용됩니다"})
        model = None
    at, units = _guide_units(step, doc_id, part)
    return {"step": step, "name": GUIDE_STEPS[step], "model": model, "parts": parts,
            "last": {"at": at, "units": [{**{k: u.get(k) for k in ("n", "title", "pages", "targets", "tables", "error")}, "chars": len(u["prompt"]), "has": True} for u in units]} if units else None}


@router.get("/api/docs/{doc_id}/llm-guide/{step}/prompt")
def llm_guide_prompt(doc_id: str, step: str, unit: int = 0, part: str = None):
    """마지막으로 보낸 프롬프트 하나(전체 글)와 그 답 → {at, title, prompt, answer}. 404 모르는 step · 그런 단위 없음(아직 실행 전). part = 취합(step gather)의 기관 문서 id."""
    if step not in GUIDE_STEPS:
        raise HTTPException(404, "그런 LLM 검토가 없습니다")
    at, units = _guide_units(step, doc_id, part)
    u = next((u for u in units if u.get("n") == unit), None)
    if u is None:
        raise HTTPException(404, "보낸 프롬프트가 없습니다(아직 실행하지 않았거나 그 단위는 부르지 않았습니다)")
    return {"at": at, "title": u.get("title"), "prompt": u["prompt"], "answer": u.get("answer")}


# ---- 넣기 계획 → 확인 → 반영(spec_병합 ② §0-1 「넣기 계획」·④ · §6) — 본문(merge_fill) + 표 칸·행(merge_tables) + 템플릿 변환(merge_convert) ----

def _brief(x):
    """계획의 한 줄 → 화면에 보낼 꼴(목록은 수로)."""
    return {k: len(v) if isinstance(v, (list, tuple)) else v for k, v in x.items()}


MAP_KEYS = ("filled", "shaped", "lines", "rowsAdded", "cleared")   # 표 대응 반영의 수(merge_table_map.apply)


def _maps_view(mp):
    """넣기 계획의 표 대응 몫 → 화면에 보낼 꼴 {counts{tables, stale, records, cells, lines, rows, cleared, skipped{…}, open}, tables[], skipped[], todo}. open = 표 대응이 필요한데 아직 없는(낡은) 표 수."""
    if not mp:
        return {"counts": {"tables": 0, "stale": 0, "records": 0, "cells": 0, "lines": 0, "rows": 0, "cleared": 0, "skipped": {}, "open": 0}, "tables": [], "skipped": [], "todo": 0}
    return {"counts": {**mp["counts"], "open": len(mp.get("open") or ())}, "tables": mp["tables"], "skipped": mp["skipped"][:300], "todo": mp["todo"], "open": list(mp.get("open") or ())}


def _plan_view(plan):
    fill, tabs, fx = plan["fill"], plan["tables"], plan["fixed"]
    keys = ("group", "value", "to", "from", "anchorText", "blocks", "paragraphs", "tables", "pictures", "skip", "detail")
    return {"planId": plan["planId"], "baseRev": plan["baseRev"], "todo": plan["todo"],
            "body": {"counts": fill["counts"], "items": [{k: it.get(k) for k in keys} for it in fill["items"]]},
            "tables": {"counts": tabs["counts"], "tables": [_brief(t) for t in tabs["tables"]], "skipped": tabs["skipped"][:300]},
            "fixed": {"counts": fx["counts"], "tables": fx["tables"], "labels": [{k: it.get(k) for k in (*keys, "title")} for it in fx["labels"]], "skipped": fx["skipped"][:300]},
            "maps": _maps_view(plan.get("maps"))}   # 표 대응(② §5-3) — 표마다 대응한 항목·칸·표시·늘릴 행과 못 넣은 것


@router.post("/api/docs/{doc_id}/merge-links/plan")
def merge_plan(doc_id: str):
    """넣기 계획 — 연결된(paired) 묶음마다 넣을 본문 블록·표 칸·늘릴 행과 못 넣는 것의 까닭을 센다. **문서는 안 바뀐다**.
    → {planId, baseRev, todo, body{counts, items[{group, value, to, from, anchorText, blocks, paragraphs, tables, pictures, skip, detail}]}, tables{counts, tables[], skipped[]},
       fixed{counts, tables[{to, from, score, status, title, cells, skipped}], labels[본문 항목 꼴 + title], skipped[]}}(fixed = 같은 이름 자리 — merge_fixed, todo 에 든다). 409 까닭이 남음."""
    import uuid

    from app import merge_fill, merge_fixed, merge_tables, server
    view, ctx = _view(doc_id)
    if ctx is None:
        raise HTTPException(409, "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)")
    _, _, saved, to, frm = ctx
    s = server._sess(doc_id)
    with s.lock:
        applied = _alive(saved.get("applied"), to)   # 실행 취소로 사라진 내용의 기록은 안 믿는다
        fill = merge_fill.plan(to, frm, to["values"], frm["values"], view, applied=applied)
        maps, tabs, fixed, _ = _plan_parts(doc_id, view, saved, to, frm)   # 표 대응(② §5-3) → 표 묶음 → 같은 이름 자리: 대응이 맡은 표는 뒤의 둘에서 빠진다
        plan = {"planId": uuid.uuid4().hex[:12], "baseRev": to["rev"], "fromRev": frm["rev"], "from": frm["id"], "fill": fill, "tables": tabs, "fixed": fixed, "maps": maps,   # 차례 = 읽은 때의 것(읽은 뒤 바뀌었으면 반영이 409)
                "todo": fill["counts"].get("todo", 0) + len(tabs["cells"]) + len(tabs["rows"]) + fixed["todo"] + maps["todo"]}
    _PLANS[doc_id] = plan
    return _plan_view(plan)


@router.post("/api/docs/{doc_id}/merge-links/apply")
def merge_apply(doc_id: str, body: dict = Body(...)):
    """{planId} → 그 계획을 목적 문서에 반영: 구조 편집 트랜잭션 하나(문서 전체 표준 검사 — 걸리면 전부 되돌리고 422 · 실행 취소 1 · rev +1 · 기록 `mergeFill`). 원본 문서는 안 바뀐다.
    → {body{…넣은 수}, tables{filled, rowsAdded, shaped(글자 모양을 얹은 칸)}, fixed{filled, shaped, labels{items, blocks, …}, fitted(줄인 그림), flowed(쪽 나눔을 맞춘 표)}(같은 이름 자리), converted{…템플릿 변환}, dropped[옮기지 못한 개체], …편집 상태}
      | {nothing: true}. 409 계획이 없거나 그 뒤 문서가 바뀜."""
    from collections import Counter

    from app import merge_convert, merge_fill, merge_fixed, merge_table_map, merge_tables, server
    plan = _PLANS.get(doc_id)
    if plan is None or plan["planId"] != body.get("planId"):
        raise HTTPException(409, "계획이 없거나 바뀌었습니다 — 다시 계획하세요")
    to, frm = _read(doc_id, target=True), _read(plan["from"])
    s, src = server._sess(doc_id), server._sess(plan["from"])
    first, second = sorted((s, src), key=lambda x: x.id)   # 원본도 같이 잠근다(차례 = id — 서로 맞물리지 않게): 반영 중 원본이 바뀌면 칸 글은 계획 때 것, 본문은 바뀐 것이 섞인다(astra P2-12)
    with first.lock, second.lock:
        if plan["baseRev"] != s.rev or plan["fromRev"] != src.rev:
            raise HTTPException(409, "계획을 세운 뒤 문서가 바뀌었습니다 — 다시 계획하세요")
        if not plan["todo"]:
            _PLANS.pop(doc_id, None)
            return {"nothing": True, **s.state()}
        done, conv = {}, Counter()

        def run():
            convert = merge_convert.converter(s.doc, to["graph"], frm["graph"])

            def hook(anchor, pairs):   # 넣은 항목마다 — 목적 문서 틀에 받을 레벨이 있는 줄만 바뀐다(없으면 원본 모양 그대로, 까닭별로 셈)
                r = convert(anchor, pairs)
                conv.update({"converted": r.get("converted", 0), **{f"kept:{k}": n for k, n in (r.get("kept") or {}).items()}})
            done["tables"] = merge_tables.apply(s.doc, frm["doc"], plan["tables"])
            done["fixed"] = merge_fixed.apply(s.doc, frm["doc"], plan["fixed"])   # 같은 이름 자리 — 같은 편집 하나에(실행 취소 1). 라벨 내용은 원본 모양 그대로(템플릿 변환 없음)
            done["maps"] = merge_table_map.apply(s.doc, frm["doc"], plan.get("maps") or {})   # 표 대응(② §5-3) — 행 늘리기 · 칸 글 · 예시 지움 · 표시 선: 같은 편집 하나에
            done["fill"] = merge_fill.apply(s.doc, frm["doc"], plan["fill"], convert=hook)
            done["fill"]["counts"]["fitted"] = sum(s.doc.fit_image(i) for ids in done["fill"]["inserted"].values() for i in ids)   # 넣은 그림이 칸보다 넓으면 칸 폭으로(spec_병합 ② §5-2)
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None,
                    "log": {"planId": plan["planId"], "body": done["fill"]["counts"], "tables": {k: done["tables"].get(k) for k in TABLE_KEYS},
                            "fixed": {k: done["fixed"].get(k) for k in FIXED_KEYS}, "maps": {k: done["maps"].get(k) for k in MAP_KEYS}, "converted": dict(conv)}}

        def check(s_, out, base, header):
            """문서 전체 검사 — 단 **스키마 위반의 기준선에 원본 문서의 것을 더한다**: 문서 사이 복사는 원본 문서에 한글이 써 둔 스키마 위반(strikeout shape "3D" · transMatrix 자리 등 — 실제 작성본 6종)을
            내용과 함께 가져오므로 그 종류는 이 편집 탓이 아니다. 두 문서 어디에도 없던 종류와 규칙 위반(목적 문서 기준 그대로)은 전처럼 되돌린다."""
            chk = s_.kit["check"]
            return chk.verdict(s_.doc, {"schema": Counter(base["schema"]) + Counter(server.owpml_base(src)["schema"]), "rules": base["rules"]}, chk.check_doc(s_.doc))
        out, after = server._transact(s, run, "mergeFill", req={"planId": plan["planId"]}, check=check)
        _PLANS.pop(doc_id, None)
        if after is None:
            return out
        saved = _store(doc_id)
        new = {k: {**v, "ids": list(d["inserted"].get(k) or ())} for d in (done["fill"], done["fixed"]) for k, v in d["applied"].items()}   # 넣은 블록 id 도 — 실행 취소 뒤에 기록만 남지 않게(_alive)
        tm = dict(_maps(saved))   # 표 대응 — 늘린 묶음을 records 로 옮기고 구조 서명을 지금 표로(다시 계획하면 할 일 0: ② §5-3 9)
        for tid in (plan.get("maps") or {}).get("owned") or ():
            block = s.doc.table_block(tid)
            if tid in tm and block:
                tm[tid] = merge_table_map.settle(tm[tid], done["maps"]["grown"].get(tid), block)
        _store(doc_id, {**saved, "applied": {**(saved.get("applied") or {}), **new}, **({"tableMaps": tm} if tm else {})})   # 고정 라벨도 같은 기록(열쇠 = 목적 라벨 id — 묶음 항목과 안 겹친다)
        skip = lambda d: len(d.get("skipped") or ())  # noqa: E731 — 반영 때 건너뛴 수(계획 뒤 글이 생긴 칸 등)
        return {"body": done["fill"]["counts"], "tables": {**{k: done["tables"].get(k) for k in TABLE_KEYS}, "skipped": skip(done["tables"])},
                "fixed": {**{k: done["fixed"].get(k) for k in FIXED_KEYS}, "skipped": skip(done["fixed"])},
                "maps": {**{k: done["maps"].get(k) for k in MAP_KEYS}, "skipped": skip(done["maps"])},
                "converted": dict(conv), "dropped": done["fill"]["dropped"] + done["fixed"]["dropped"], **s.state()}


# ---- 원본 자리 지도(spec_작업 ② §12 「누른 자리 따라 보기」 — 2026-11-12 사용자 "작성된 부분은 클릭하면 상대 페이지 바로 보여주기") ----

_ORIGINS = {}   # 목적 작업 id → (열쇠, 지도) — 두 문서의 차례·분석·넣은 기록·고른 연결이 같으면 다시 안 센다(넣기 계획과 같은 셈이라 큰 문서는 몇 초)


@router.get("/api/docs/{doc_id}/merge-links/origins")
def merge_origins_get(doc_id: str):
    """원본 자리 지도 — 목적 문서(연차보고서)의 자리 id → 원본 문서(사업계획서)의 자리 id(문단·표 칸·표·라벨). 화면이 목적 문서에서 누른 곳의 원본 자리를 다른 면에 바로 띄운다. **문서는 안 바뀐다**.
    넣을 때 적어 둔 대응이 아니라 지금 두 문서의 짝을 다시 셈한다(`merge_origins.build` — 넣기 계획과 같은 규칙: 이 끝점이 생기기 전에 넣은 문서에서도 된다).
    → {to{work, rev}, from{work, name, rev} | null, reasons[], map{목적 id: 원본 id}, counts{groups, tables, labels, blocks, cells}}. 자리 연결을 못 내는 상태(까닭이 남음 · 원본 없음)면 map 은 비어 있다 —
    오류가 아니다(화면은 그냥 안 따라간다)."""
    from app import merge_origins, server
    view, ctx = _view(doc_id)
    frm_head = view.get("from")
    out = {"to": {k: view["to"][k] for k in ("work", "rev")}, "from": frm_head and {k: frm_head[k] for k in ("work", "name", "rev")},
           "reasons": [*view["to"]["reasons"], *((frm_head or {}).get("reasons") or ())], "map": {}, "counts": {}}
    if ctx is None:
        return out
    _, _, saved, to, frm = ctx
    if to.get("doc") is None or frm.get("doc") is None:   # 문서 없이 요약만 끼운 읽기(시험) — 지도는 문서의 지금 블록을 본다(_fixed_brief 와 같은 조건)
        return out
    applied, forced = _alive(saved.get("applied"), to), _forced(saved)
    key = (to["id"], to["rev"], frm["id"], frm["rev"], repr(to["values"]), repr(frm["values"]), id(to["graph"]), id(to["tables"]), id(frm["graph"]), id(frm["tables"]),
           tuple(sorted((k, (v or {}).get("hash"), tuple((v or {}).get("ids") or ())) for k, v in applied.items())),
           tuple(sorted((k, v.get("from"), v.get("source")) for k, v in forced.items())),
           tuple(sorted((k, v.get("from")) for k, v in (saved.get("fixed") or {}).items() if isinstance(v, dict))))
    with _LOCK:
        hit = _ORIGINS.get(doc_id)
    if hit is None or hit[0] != key:
        with server._sess(doc_id).lock:
            hit = (key, merge_origins.build(to, frm, view, applied=applied, forced=forced))
        with _LOCK:
            _ORIGINS[doc_id] = hit
    return {**out, **hit[1]}
