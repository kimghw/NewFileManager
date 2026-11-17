"""병합 API — 자리 연결(spec_병합 ② §0-1 ①②③ · §3 · §8 가운데 읽기 · 다시 내기 · 사람 고침). + LLM 보정(`POST …/merge-links/llm`) · 넣기 계획(`POST …/merge-links/plan`) · 반영(`POST …/merge-links/apply`) · 1·2단계 초기화(`POST …/merge-links/reset`) — 아래 함수 설명.

- `GET  /api/docs/{to}/merge-links` → {project, from{work, name, rev, reasons[]} | null, to{…}, diff[구분 값이 다른 곳], stale, groups[], counts} — 목적 문서(연차보고서) 기준.
  원본 = 같은 과제(`task.project`)에서 `task.file = plan` 인 작업(없으면 from null). 못 내는 까닭은 **문서별로**: noHeadings(헤딩 2·3단계 결과 없음) · noValues(구분 값 없음) ·
  notApplied(목적 문서에 값을 반영하지 않음) · unsupportedForm(hwpx 아님). 두 문서의 값이 다르면 diff 에 다른 곳(valuesDiffer 는 목적 문서 까닭에도). 까닭이 있으면 groups 는 비어 있다.
- `POST /api/docs/{to}/merge-links` → 요약을 다시 만들어 같은 몸통(사람이 고친 것은 유지).
- `PUT  /api/docs/{to}/merge-links/{groupId}` `{from: 원본 묶음 key | null}` 또는 `{reset: true}` → 사람이 연결을 고르거나(null = 끊음) 스크립트 결과로 되돌림. 400 후보가 될 수 없는 묶음 · 404 그런 묶음 없음.
저장: 목적 작업 폴더 `merge.json` {from(작업 id), fixed{목적 key: {from, source: user}}, toRev, fromRev}(작업 저장이 꺼져 있으면 메모리). 문서가 그 뒤 바뀌었으면 stale 만 보인다(다시 하라고 다그치지 않음)."""
import json
import threading

from fastapi import APIRouter, Body, HTTPException

from app import heading_runs as HR
from app import merge_pairs as P
from app import projects, works

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


def _source_scope(to_id, from_id):
    return tuple(projects.group_key((works.work(wid) or {}).get("task")) for wid in (to_id, from_id))


def _source_allowed(to_id, from_id):
    """프로젝트가 지정된 두 문서는 같은 TASK 라운드여야 한다. 미지정 문서의 수동 연결은 유지한다."""
    if from_id == to_id:
        return False
    if works.work(from_id) is None:
        return False
    a, b = _source_scope(to_id, from_id)
    return not (a[0] and b[0]) or a == b


def _mate(to_id, saved):
    """(프로젝트 이름, 원본 작업 id | None) — 같은 프로젝트·TASK·라운드의 사업계획서."""
    task = (works.work(to_id) or {}).get("task") or {}
    project = task.get("project") or ""
    if saved.get("from") and works.work(saved["from"]):
        # 명시한 원본이 다른 라운드로 이동했으면 멈춘다. 앞 원본의 연결 기록을 다른 문서에 적용하지 않는다.
        return project, saved["from"] if _source_allowed(to_id, saved["from"]) else None
    for w in works.list_works() if project else ():
        t = w.get("task") or {}
        if w["id"] != to_id and projects.group_key(t) == projects.group_key(task) and t.get("file") == "plan":
            return project, w["id"]
    return project, None


def _read(doc_id, target=False):
    """문서 하나에서 요약에 드는 것을 읽는다(세션 잠금 안에서 짧게) → {id, name, rev, reasons, values, blocks, graph, tables}."""
    from app import server   # server 가 이 모듈을 include 한다(순환 import 피함)
    s = server._sess(doc_id)
    with s.lock:
        server._project_settings_sync(s)
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
    head = lambda x: {"work": x["id"], "name": works.shown_name(x["name"], *(lambda w: (w.get("task"), w.get("alias")))(works.work(x["id"]) or {})), "rev": x["rev"], "reasons": x["reasons"]}  # noqa: E731 — name = 보이는 이름(spec_작업 ② §10: 목적 문서는 과제 이름 · 별칭이 뒤에)
    out = {"project": project, "to": head(to), "from": head(frm) if frm else None, "diff": [], "stale": False, "groups": [], "counts": dict(ZERO),
           "comments": _link_comments(to_id),   # 연결 코멘트(목적 양식의 양식 정보 「자리 연결」 절 — spec_병합 ② §5-3 1)
           "kept": _kept(saved)}   # 남은 2단계 기록의 수(화면의 「2단계 초기화」 — spec_작업 ② §14)
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
    out["kept"]["applied"] = len(_alive(saved.get("applied"), to))   # 넣은 기록 가운데 지금 문서에 남은 것(실행 취소로 사라진 것은 안 셈 — ③④ 「지난 반영」)
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
        if not _source_allowed(doc_id, body["from"]):
            raise HTTPException(400, "같은 프로젝트·TASK·라운드의 원본 문서를 고르세요")
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


# ---- 빈 자리 검토(spec_병합 ② §5-4 — 사용자 2026-11-12 "여기 들어가지 않은 것들은 LLM 이 검토하고 넣어주는 기능 없나?" → 답 「표 + 단락 모두」) ----

_GAPS_LAST = {}   # 작업 저장이 꺼졌을 때의 merge_gaps_last.json


def _gaps(saved):
    """merge.json `gaps` = 빈 자리 검토의 답 {at, tables{목적 표 id: {from | None, reason}}, slots{목적 칸·줄 id: {from | None, take, kind, was, label, table, reason}}}(② §5-4 7)."""
    g = saved.get("gaps")
    return g if isinstance(g, dict) else {}


def _gaps_last(wid, data=None):
    """빈 자리 검토가 마지막으로 보낸 프롬프트·답(작업 폴더 `merge_gaps_last.json`) 읽기(data None) · 쓰기."""
    d = works.folder(wid)
    if data is None:
        return (works._read_json(d / "merge_gaps_last.json") if d is not None and (d / "merge_gaps_last.json").is_file() else _GAPS_LAST.get(wid)) or None
    if d is not None:
        works._write_json(d / "merge_gaps_last.json", data)
    else:
        _GAPS_LAST[wid] = data
    return data


def _gaps_plan(doc_id, saved, sides, fixed):
    """넣기 계획의 빈 자리 몫(세션 잠금 안에서) — 답이 있는 빈 칸·빈 라벨 줄에 넣을 글 + 아직 안 물은 빈 자리 수(counts.open). 빈 표 ← 원본 표는 표 짝(`tables`)으로 가 있어 다른 몫이 넣는다."""
    from app import merge_gaps
    T, F = sides
    gp = merge_gaps.plan(T, F, _gaps(saved))
    try:
        gp["counts"]["open"] = merge_gaps.open_count(merge_gaps.targets(T, F, fixed, _orig(doc_id)), _gaps(saved))
    except Exception:   # 빈 자리 세기는 덤이다 — 틀어져도 넣기 계획은 나가야 한다
        gp["counts"]["open"] = 0
    return gp


@router.post("/api/docs/{doc_id}/merge-links/gaps")
def merge_gaps_post(doc_id: str, body: dict = Body(default={})):
    """빈 자리 검토(② §5-4) — 다른 길이 못 채운 목적 자리(빈 표 · 빈 칸 · 빈 라벨 줄)를 모아 계획서의 어디에서 가져올지 LLM(목적 문서의 장마다 · 병렬 · Opus)에 묻고, 검증한 답을 `merge.json` `gaps` 에 둔다.
    빈 표에 고른 원본 표는 표 짝(`tables` source llm · by gaps)으로도 적는다 — 그 뒤는 같은 이름 자리·표 대응이 넣는다. **문서는 안 바뀐다**(넣기 계획 → 반영이 쓴다).
    이미 답이 있는 자리(「원본 없음」 포함)는 다시 안 묻는다 — `{again: true}` 면 전부 다시.
    → {at, asked(호출 수), found{tables, slots}, tables{paired, none}, slots{filled, none}, rejected[], units[{title, targets, error}]}. 409 까닭이 남음."""
    from datetime import datetime

    from app import job_prompts, merge_gaps, server
    view, ctx = _view(doc_id)
    if ctx is None:
        raise HTTPException(409, "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)")
    _, _, saved, to, frm = ctx
    again = bool(body.get("again"))
    with server._sess(doc_id).lock:
        _, _, fixed, (T, F) = _plan_parts(doc_id, view, saved, to, frm)
        prep = merge_gaps.prepare(T, F, fixed, _gaps(saved), again, _orig(doc_id))
    res = merge_gaps.ask(prep, job_prompts.for_work(doc_id), _links_text(doc_id))   # 잠금 밖 — 읽어 둔 것만 쓴다
    at = datetime.now().isoformat(timespec="seconds")
    now = _store(doc_id)
    old = {} if again else _gaps(now)
    gaps = {"at": at, "tables": {**(old.get("tables") or {}), **res["tables"]}, "slots": {**(old.get("slots") or {}), **res["slots"]}, "guide": res.get("guide"), "job": res.get("job")}
    pairs_t = dict(_forced(now))
    for tid, v in res["tables"].items():
        mine = pairs_t.get(tid) or {}
        if mine.get("source") == "user":   # 사람이 정한 표 짝은 안 건드린다
            continue
        if v["from"]:
            pairs_t[tid] = {"from": v["from"], "source": "llm", "by": "gaps", "reason": v["reason"], "format": ""}
        elif mine.get("by") == "gaps":   # 다시 물었더니 「같은 표 없음」 — 앞서 이 검토가 낸 짝을 지운다
            pairs_t.pop(tid, None)
    _store(doc_id, {**now, "gaps": gaps, "tables": pairs_t})
    if res["units"]:
        _gaps_last(doc_id, {"at": at, "units": [{k: u.get(k) for k in ("n", "title", "pages", "targets", "tables", "error", "prompt", "answer")} for u in res["units"]]})
    with _LOCK:
        _FIXED.pop(doc_id, None)
    count = lambda d, yes: sum(1 for v in d.values() if bool(v.get("from")) == yes)  # noqa: E731
    return {"at": at, "asked": res["asked"], "found": res["found"], "tables": {"paired": count(res["tables"], True), "none": count(res["tables"], False)},
            "slots": {"filled": count(res["slots"], True), "none": count(res["slots"], False)}, "rejected": res["rejected"][:40],
            "units": [{"title": u["title"], "targets": u["targets"], "error": u.get("error")} for u in res["units"]]}


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
               "table-map": "표 대응 에이전트",   # 표 대응(spec_병합 ② §5-3) — 표마다 한 단위
               "gaps": "빈 자리 검토",   # 빈 자리 검토(spec_병합 ② §5-4) — 목적 문서의 장마다 한 단위
               "zones": "편집 구역 LLM 검토"}   # 편집 구역 LLM 검토(spec_구역 ② §8 「LLM 검토 — 스크립트가 못 정한 것」) — 한 번 호출이라 단위 하나


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
    if step in ("merge-links", "gather", "table-map", "gaps", "zones"):
        if step == "gather":
            from app import merge_gather_api
            last = merge_gather_api.llm_last(doc_id, part) or {}   # 취합본 작업 폴더 `gather/llm-<기관 문서 id>.json`(spec_취합 ② §2)
        elif step == "zones":
            from app import zones_api
            last = zones_api.llm_last(doc_id) or {}   # 작업 폴더 `zones/llm-last.json`
        elif step == "table-map":
            last = _map_last(doc_id) or {}   # 작업 폴더 `merge_map_last.json`(표마다 한 단위)
        elif step == "gaps":
            last = _gaps_last(doc_id) or {}   # 작업 폴더 `merge_gaps_last.json`
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
    elif step == "gaps":
        from app import merge_gaps
        parts, model = merge_gaps.parts(job=job_prompts.for_work(doc_id), links=_links_text(doc_id)), merge_gaps.MODEL
    elif step == "gather":
        from app import merge_gather_llm
        parts, model = merge_gather_llm.parts(job=job_prompts.for_work(doc_id)), merge_gather_llm.MODEL
    elif step == "zones":
        from app import zones_llm
        parts, model = zones_llm.parts(), None   # 계약 + 판단 지침(app/merge_guides_default/zones.md) — 모델은 서버 기본
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
    from app import llm
    model = llm.forced() or model   # env NFM_LLM_MODEL_FORCE 가 있으면 실제로 부르는 모델은 그것
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


def _gaps_view(gp):
    """넣기 계획의 빈 자리 몫 → 화면에 보낼 꼴 {counts{open, tables, cells, lines, skipped{…}}, items[{to, kind, label, from, fromText, lines, skip, detail}], todo}."""
    if not gp:
        return {"counts": {"open": 0, "tables": 0, "cells": 0, "lines": 0, "skipped": {}}, "items": [], "todo": 0}
    return {"counts": gp["counts"], "items": gp["items"][:300], "todo": gp["todo"]}


def _plan_view(plan):
    fill, tabs, fx = plan["fill"], plan["tables"], plan["fixed"]
    keys = ("group", "value", "to", "from", "anchorText", "blocks", "paragraphs", "tables", "pictures", "skip", "detail")
    over = (plan.get("over") or {}).get("view") or {}   # 넘친 개요 레벨(② §5-5) — 사례가 있을 때만 싣는다(화면이 그 절을 그린다)
    return {"planId": plan["planId"], "baseRev": plan["baseRev"], "todo": plan["todo"], **({"over": over} if over.get("cases") else {}),
            "body": {"counts": fill["counts"], "items": [{k: it.get(k) for k in (*keys, "convert")} for it in fill["items"]]},   # convert = 항목의 템플릿 변환 미리보기 {converted, over, kept} | None(안 넣는 항목)
            "tables": {"counts": tabs["counts"], "tables": [_brief(t) for t in tabs["tables"]], "skipped": tabs["skipped"][:300]},
            "fixed": {"counts": fx["counts"], "tables": fx["tables"], "labels": [{k: it.get(k) for k in (*keys, "title")} for it in fx["labels"]], "skipped": fx["skipped"][:300]},
            "maps": _maps_view(plan.get("maps")),   # 표 대응(② §5-3) — 표마다 대응한 항목·칸·표시·늘릴 행과 못 넣은 것
            "gaps": _gaps_view(plan.get("gaps"))}   # 빈 자리(② §5-4) — 빈 칸·빈 라벨 줄에 넣을 글 · 아직 안 물은 빈 자리 수


@router.post("/api/docs/{doc_id}/merge-links/plan")
def merge_plan(doc_id: str):
    """넣기 계획 — 연결된(paired) 묶음마다 넣을 본문 블록·표 칸·늘릴 행과 못 넣는 것의 까닭을 센다. **문서는 안 바뀐다**.
    → {planId, baseRev, todo, body{counts, items[{group, value, to, from, anchorText, blocks, paragraphs, tables, pictures, skip, detail, convert}]}, tables{counts, tables[], skipped[]},
       fixed{counts, tables[{to, from, score, status, title, cells, skipped}], labels[본문 항목 꼴 + title], skipped[]}}(fixed = 같은 이름 자리 — merge_fixed, todo 에 든다). 409 까닭이 남음.
    (2026-11-13 — spec_병합 ② §5-5) 본문 항목마다 템플릿 변환 미리보기 `convert{converted, over(넘친 줄), kept}` 와, 넘친 개요 레벨이 있거나 넣은 넘친 줄의 기록이 있으면 `over{version, cases[], templates[], records}`.
    그때의 선택(merge_over.json)을 풀어 계획에 실어 둔다 — 반영은 그 지정 그대로 입힌다."""
    import uuid

    from app import merge_fill, merge_fixed, merge_tables, server
    from app import merge_over as MO
    from app import merge_over_api as MOA
    view, ctx = _view(doc_id)
    if ctx is None:
        raise HTTPException(409, "자리 연결을 낼 수 없는 상태입니다(문서별 까닭을 먼저 푸세요)")
    _, _, saved, to, frm = ctx
    s = server._sess(doc_id)
    with s.lock:
        applied = _alive(saved.get("applied"), to)   # 실행 취소로 사라진 내용의 기록은 안 믿는다
        fill = merge_fill.plan(to, frm, to["values"], frm["values"], view, applied=applied)
        maps, tabs, fixed, sides = _plan_parts(doc_id, view, saved, to, frm)   # 표 대응(② §5-3) → 표 묶음 → 같은 이름 자리: 대응이 맡은 표는 뒤의 둘에서 빠진다
        gaps = _gaps_plan(doc_id, saved, sides, fixed)   # 빈 자리(② §5-4) — 위 셋이 못 채운 자리 가운데 LLM 이 원본 줄을 고른 것
        store, specs = MOA.specs(doc_id, to["graph"])   # 넘친 개요 레벨(② §5-5) — 사례마다 사람이 고른 처리를 줄 지정으로 푼 것
        conv, cases = MO.fill_preview(to, frm, fill, specs)   # 본문 항목마다 템플릿 변환 미리보기 + 이번 계획의 넘친 사례
        for it in fill["items"]:
            if it["to"] in conv:
                it["convert"] = conv[it["to"]]
        over = {"version": store["version"], "specs": specs, "view": MOA.over_view(doc_id, cases, to["graph"], to["doc"], store)}
        plan = {"planId": uuid.uuid4().hex[:12], "baseRev": to["rev"], "fromRev": frm["rev"], "from": frm["id"], "scope": _source_scope(doc_id, frm["id"]), "fill": fill, "tables": tabs, "fixed": fixed, "maps": maps, "gaps": gaps, "over": over,   # 차례 = 읽은 때의 것(읽은 뒤 바뀌었으면 반영이 409)
                "todo": fill["counts"].get("todo", 0) + len(tabs["cells"]) + len(tabs["rows"]) + fixed["todo"] + maps["todo"] + gaps["todo"]}
    _PLANS[doc_id] = plan
    return _plan_view(plan)


@router.post("/api/docs/{doc_id}/merge-links/apply")
def merge_apply(doc_id: str, body: dict = Body(...)):
    """{planId} → 그 계획을 목적 문서에 반영: 구조 편집 트랜잭션 하나(문서 전체 표준 검사 — 걸리면 전부 되돌리고 422 · 실행 취소 1 · rev +1 · 기록 `mergeFill`). 원본 문서는 안 바뀐다.
    → {body{…넣은 수}, tables{filled, rowsAdded, shaped(글자 모양을 얹은 칸)}, fixed{filled, shaped, labels{items, blocks, …}, fitted(줄인 그림), flowed(쪽 나눔을 맞춘 표)}(같은 이름 자리), converted{…템플릿 변환 · over = 넘친 줄 수(② §5-5)}, dropped[옮기지 못한 개체], …편집 상태}
      | {nothing: true}. 409 계획이 없거나 그 뒤 문서가 바뀜."""
    from collections import Counter

    from app import merge_convert, merge_fill, merge_fixed, merge_gaps, merge_over, merge_table_map, merge_tables, server
    plan = _PLANS.get(doc_id)
    if plan is None or plan["planId"] != body.get("planId"):
        raise HTTPException(409, "계획이 없거나 바뀌었습니다 — 다시 계획하세요")
    if not _source_allowed(doc_id, plan["from"]) or ("scope" in plan and plan["scope"] != _source_scope(doc_id, plan["from"])):
        _PLANS.pop(doc_id, None)
        raise HTTPException(409, "계획을 세운 뒤 프로젝트·TASK·라운드가 바뀌었습니다 — 다시 계획하세요")
    to, frm = _read(doc_id, target=True), _read(plan["from"])
    s, src = server._sess(doc_id), server._sess(plan["from"])
    first, second = sorted((s, src), key=lambda x: x.id)   # 원본도 같이 잠근다(차례 = id — 서로 맞물리지 않게): 반영 중 원본이 바뀌면 칸 글은 계획 때 것, 본문은 바뀐 것이 섞인다(astra P2-12)
    with first.lock, second.lock:
        if plan["baseRev"] != s.rev or plan["fromRev"] != src.rev:
            raise HTTPException(409, "계획을 세운 뒤 문서가 바뀌었습니다 — 다시 계획하세요")
        over = plan.get("over") or {}
        if over and merge_over.load(doc_id)["version"] != over.get("version"):   # 넘친 개요 레벨의 선택이 계획 뒤 바뀜(② §5-5 6 — 보통은 PUT 이 계획을 버린다)
            _PLANS.pop(doc_id, None)
            raise HTTPException(409, "계획을 세운 뒤 넘친 개요 레벨의 처리가 바뀌었습니다 — 다시 계획하세요")
        if not plan["todo"]:
            _PLANS.pop(doc_id, None)
            return {"nothing": True, **s.state()}
        done, conv = {}, Counter()

        def run():
            convert = merge_convert.converter(s.doc, to["graph"], frm["graph"], over=over.get("specs"))   # 넘친 레벨은 계획에 실어 둔 지정대로(없으면 원본 모양 그대로)

            def hook(anchor, pairs):   # 넣은 항목마다 — 목적 문서 틀에 받을 레벨이 있는 줄만 바뀐다(없으면 원본 모양 그대로, 까닭별로 셈)
                r = convert(anchor, pairs)
                lines = len(r.get("lines") or ())   # 넘친 줄(덮은 그대로 둔 것 포함) — merge_fill 이 그 기록을 항목의 applied 에 적는다(다시 맞추기의 근거)
                conv.update({"converted": r.get("converted", 0), **({"over": lines} if lines else {}), **{f"kept:{k}": n for k, n in (r.get("kept") or {}).items()}})
                return r
            done["tables"] = merge_tables.apply(s.doc, frm["doc"], plan["tables"])
            done["fixed"] = merge_fixed.apply(s.doc, frm["doc"], plan["fixed"])   # 같은 이름 자리 — 같은 편집 하나에(실행 취소 1). 라벨 내용은 원본 모양 그대로(템플릿 변환 없음)
            done["maps"] = merge_table_map.apply(s.doc, frm["doc"], plan.get("maps") or {})   # 표 대응(② §5-3) — 행 늘리기 · 칸 글 · 예시 지움 · 표시 선: 같은 편집 하나에
            done["gaps"] = merge_gaps.apply(s.doc, plan.get("gaps"))   # 빈 자리(② §5-4) — 빈 칸·빈 라벨 줄에 원본 줄의 글: 같은 편집 하나에
            done["fill"] = merge_fill.apply(s.doc, frm["doc"], plan["fill"], convert=hook)
            done["fill"]["counts"]["fitted"] = sum(s.doc.fit_image(i) for ids in done["fill"]["inserted"].values() for i in ids)   # 넣은 그림이 칸보다 넓으면 칸 폭으로(spec_병합 ② §5-2)
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None,
                    "log": {"planId": plan["planId"], "body": done["fill"]["counts"], "tables": {k: done["tables"].get(k) for k in TABLE_KEYS},
                            "fixed": {k: done["fixed"].get(k) for k in FIXED_KEYS}, "maps": {k: done["maps"].get(k) for k in MAP_KEYS},
                            "gaps": {k: done["gaps"].get(k) for k in ("cells", "lines")}, "converted": dict(conv)}}

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
                "gaps": {"cells": done["gaps"]["cells"], "lines": done["gaps"]["lines"], "skipped": skip(done["gaps"])},
                "converted": dict(conv), "dropped": done["fill"]["dropped"] + done["fixed"]["dropped"], **s.state()}


# ---- 이관 1·2단계 초기화(spec_작업 ② §14 「초기화」 — 2026-11-12 사용자 "어차피 연차보고서는 원본이 있으니깐 작업 1,2 단계 초기화 할 수 있도록 해줘") ----

STAGE2_KEYS = ("fixed", "tables", "llm", "tableMaps", "gaps", "applied", "toRev", "fromRev")   # merge.json 가운데 2단계(내용 매핑)가 쌓은 것 — `from`(사람이 따로 고른 원본)은 진행이 아니라 고른 값이라 둔다


def _kept(saved):
    """merge.json 에 남은 2단계 기록의 수 {links(사람·LLM 이 정한 묶음), tables(표 짝), maps(표 대응), applied(넣은 기록), llm(LLM 검토함)}
    — 화면의 「2단계 초기화」 가 켜질지 · ③④ 가 지난 반영으로 끝났는지(다시 연 화면). applied 는 문서를 읽을 수 있으면 _view 가 지금 문서에 남은 것(_alive)으로 바꾼다."""
    n = lambda k: len([v for v in (saved.get(k) or {}).values() if isinstance(v, dict)])  # noqa: E731
    return {"links": n("fixed"), "tables": n("tables"), "maps": n("tableMaps"), "applied": n("applied"), "llm": bool(saved.get("llm"))}


def _stage2_clear(doc_id):
    """2단계 기록을 지운다 — merge.json 의 진행 키 · 마지막 LLM·표 대응 프롬프트 파일 · 이 문서의 요약·계획 캐시. → 지운 키 목록."""
    saved = _store(doc_id)
    gone = [k for k in STAGE2_KEYS if k in saved]
    if gone:   # 지울 것이 없으면 merge.json 을 새로 만들지 않는다
        _store(doc_id, {k: v for k, v in saved.items() if k not in STAGE2_KEYS})
    d = works.folder(doc_id)
    for name, mem in (("merge_llm_last.json", _LAST), ("merge_map_last.json", _MAP_LAST), ("merge_gaps_last.json", _GAPS_LAST)):
        mem.pop(doc_id, None)
        if d is not None and (d / name).is_file():
            (d / name).unlink()
            gone.append(name)
    with _LOCK:
        for cache in (_CACHE, _FIXED, _ORIGINS, _ORIG):
            cache.pop(doc_id, None)
    _PLANS.pop(doc_id, None)
    return gone


@router.post("/api/docs/{doc_id}/merge-links/reset")
def merge_reset(doc_id: str, body: dict = Body(default={})):
    """{stage: "frame" | "map"} — 이관의 묶음을 처음으로(목적 문서 = 연차보고서 기준). 사업계획서(원본 문서)는 안 건드린다.
    - frame(1단계 — 1·2단계 모두): 문서를 **올린 원본(확정 0)** 으로 되돌리고(확정 복원과 같은 길 — 기준이 원본이면 「모두 되돌리기」, 아니면 「올린 원본으로 복원」 확정이 하나 생김:
      구분 기준 반영 상태·개요 오버레이도 그때 것 = 없음) 2단계 기록을 지운다. 구분 기준 **입력 값**·LLM 빠진 자리 검토·헤딩·표 분석은 그대로.
    - map(2단계만): 지금 반영된 구분 값으로 위와 같이 원본으로 되돌린 뒤 **같은 값으로 구조를 다시 반영**(변경 계획 → 반영 — 편집 1)하고 2단계 기록을 지운다.
      구조 반영 전 문서면 409. 다시 반영이 실패하면(표준 검사 422 등) 문서는 원본 상태로 두고 응답 `reset.reframe.error` 로 알린다(1단계부터 다시).
    실행 취소로 되돌릴 수 없다(확정 복원과 같음 — 화면이 확인을 받는다). → GET /api/docs/{id} 꼴 + reset{stage, restored, cleared[], reframe{summary} | {error} | None}.
    작업 저장이 꺼져 있으면 400(확정 기능이 없다)."""
    from app import server
    stage = body.get("stage") or "frame"
    if stage not in ("frame", "map"):
        raise HTTPException(400, "stage 는 frame 또는 map")
    server._commits_on()
    s = server._sess(doc_id)
    with s.lock:
        server._project_settings_sync(s)
        applied = s.division.get("applied") or {}
        values, base, dirty, settings = applied.get("values"), s.base_n, server._dirty(s), s.division.get("settings")
    if stage == "map" and not values:
        raise HTTPException(409, "구조(구분 기준)를 반영하기 전 문서입니다 — 1단계부터 진행하세요")
    restored = bool(base or dirty)
    if restored:
        server.commit_restore(doc_id, 0, {"discard": True})   # 같은 잠금 길(안에서 s.lock) — 위 잠금은 풀고 부른다
    cleared = _stage2_clear(doc_id)
    reframe = None
    if stage == "map":
        try:
            plan = server.divisions_plan(doc_id, {"values": values})
            done = server.divisions_apply(doc_id, {"planId": plan["planId"]})
            if getattr(done, "status_code", 200) != 200:   # 표준 검사에 걸림(_transact 가 되돌리고 422 응답을 돌려준다)
                reframe = {"error": json.loads(done.body).get("detail") or f"HTTP {done.status_code}"}
            else:
                reframe = {"summary": done.get("summary"), "nothing": bool(done.get("nothing"))}
        except HTTPException as e:
            reframe = {"error": str(e.detail)}
        with s.lock:   # 변경 계획은 넘긴 값을 입력 값으로 적는다 — 사람이 입력 칸에서 바꿔 둔 값(당해 차년도 등)은 그대로 둔다
            if settings is None:
                s.division["settings"] = None
            else:   # 프로젝트 최신 라운드면 공유 기록(projects.json)도 되돌린다 — 세션만 되돌리면 다음 조회의 공유 맞춤이 계획 값으로 다시 덮는다(spec_작업 ② §17)
                server._project_settings_sync(s, settings)
        server._persist_safe(s, force=True)
    with s.lock:
        rev = s.rev
    works.log(doc_id, "taskReset", rev=rev, stage=stage, restored=restored, cleared=cleared, reframe=reframe)
    return {**server.get_doc(doc_id), "reset": {"stage": stage, "restored": restored, "cleared": cleared, "reframe": reframe}}


# ---- 3단계 「문서 정리」 ⑥ 작성요령 삭제 — 양식 안내 지우기(spec_작업 ② §14 「3단계」 · app/form_cleanup.py) ----

def _cleanup_view(found):
    return {"counts": found["counts"], "patterns": found["patterns"], "marks": found["marks"][:300], "tables": found["tables"], "refs": found["refs"],
            "notes": [{k: n[k] for k in ("id", "text", "guide", "color", "whole")} for n in found["notes"]][:300]}


@router.get("/api/docs/{doc_id}/form-cleanup")
def form_cleanup_get(doc_id: str):
    """지울 양식 안내 목록(문서는 그대로 — 지금 문서에서 스크립트로 셈) → {counts{tables, refs, notes, marks, total}, patterns[{key, name, rule, how, example, count}](지우는 패턴 목록 —
    form_cleanup.PATTERNS), tables[{id, label, rows, blank}], refs[{id, label, last, tables, blank}], notes[{id, text, guide, color, whole}], marks[{id, text}], rev}. hwpx 만(아니면 빈 목록 — 패턴 목록은 있음)."""
    from app import form_cleanup, server
    s = server._sess(doc_id)
    with s.lock:
        if s.fmt != "hwpx":
            return {**_cleanup_view(form_cleanup.empty()), "rev": s.rev}
        return {**_cleanup_view(form_cleanup.find(s.doc)), "rev": s.rev}


@router.post("/api/docs/{doc_id}/form-cleanup")
def form_cleanup_post(doc_id: str, body: dict = Body(default={})):
    """{expectRev?} → 지금 문서에서 다시 찾아 한 번에 지운다(구조 편집 트랜잭션 하나 — 실행 취소 1 · rev +1 · 기록 `formCleanup`). 지울 것이 없으면 {nothing: true}.
    표준 검사의 기준선 = 올린 원본 + **편집 바로 전 문서**의 위반: 2단계 내용 반영이 사업계획서에서 옮겨 온 위반 종류(그림의 renderingInfo 등)를 이 지우기 탓으로 보지 않는다 —
    올린 원본만 기준이면 반영 뒤 문서의 모든 전체 검사 편집이 422 로 되돌려진다(2026-11-12 실측: TEMP 삭제). 이 편집이 새로 만든 위반만 되돌린다(422).
    → {done{marks, tables, notes, refs, notesWhole, notesInline, skipped}, …편집 상태}. 409 expectRev 가 지금과 다름."""
    from collections import Counter

    from app import form_cleanup, server
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "hwpx 문서만 됩니다")
    with s.lock:
        if body.get("expectRev") is not None and body["expectRev"] != s.rev:
            raise HTTPException(409, "목록을 읽은 뒤 문서가 바뀌었습니다 — 다시 읽으세요")
        found = form_cleanup.find(s.doc)
        if not found["counts"]["total"]:
            return {"nothing": True, **s.state()}
        chk = s.kit["check"]
        pre = chk.counts(chk.check_doc(s.doc))   # 편집 바로 전 문서의 위반 종류·개수
        done = {}

        def run():
            done.update(form_cleanup.apply(s.doc, found))
            return {"hosts": [], "struct": set(), "origin": {}, "anchor": None, "log": {k: done[k] for k in ("marks", "tables", "notes", "refs", "notesWhole", "notesInline")}}

        def check(s_, out, base, header):
            return chk.verdict(s_.doc, {"schema": Counter(base["schema"]) | pre["schema"], "rules": Counter(base["rules"]) | pre["rules"]}, chk.check_doc(s_.doc))
        out, after = server._transact(s, run, "formCleanup", req={"counts": found["counts"]}, check=check)
        if after is None:
            return out
        return {"done": done, **s.state()}


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
