"""템플릿 서식 정리 에이전트 API(spec_hwpx_웹편집 ② §8-4) — server.py 가 include 한다. 계산·스킬 저장은 `app/tpl_agent.py`, 오버레이는 `server._outline_ov`.
계획 하나를 문서에 적용하는 끝점은 여기가 아니라 템플릿 단위 맞추기(`outline_match_api.match_template` — POST …/outline/templates/{tpl}/match)다.
받아 둔 계획 **모두**를 한 번에 반영하는 끝점(POST …/outline/agent/apply — 아래 apply_plans)은 여기 있고, 같은 몸(`outline_match_api.apply_templates`)으로 트랜잭션 하나에 반영한다.
받은 계획은 작업 폴더에 남긴다(`outline_agent/plans.json` — spec_작업 ② §20 「넷 · 진행표 · LLM 검증·보완」): 분석 상태의 서식 LLM 칸 · 「템플릿 서식 정리」 열이 다시 부르지 않고 그 계획을 쓴다.
헤딩 그래프 실행(오버레이의 run)이 바뀌면 그 계획들은 버린다(템플릿 id 가 달라진다)."""
import json
import threading
import time

from fastapi import APIRouter, Body, HTTPException

from app import analysis
from app import heading_rules as R
from app import tpl_agent as A
from app import works

router = APIRouter()
_plans_lock = threading.Lock()


def _plans_path(sid):
    f = works.folder(sid)
    return f / "outline_agent" / "plans.json" if f is not None and (f / "work.json").is_file() else None


def _plans_box(s):
    """세션의 받은 계획 상자 {graph: [run, at] | None, plans: {tpl: 기록}} — 처음 한 번 작업 폴더에서 읽는다."""
    box = getattr(s, "tpl_plans", None)
    if box is None:
        box = {"graph": None, "plans": {}}
        path = _plans_path(s.id)
        if path is not None and path.is_file():
            try:
                got = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(got, dict) and isinstance(got.get("plans"), dict):
                    box = {"graph": got.get("graph"), "plans": got["plans"]}
            except (OSError, ValueError):
                pass
        s.tpl_plans = box
    return box


def _plans_save(s, box):
    path = _plans_path(s.id)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(box, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # 남기지 못해도 이 세션 동안은 메모리에 있다


def plans(s, graph):
    """지금 헤딩 그래프(graph = 오버레이의 run)의 받은 계획 {tpl: 기록} — 다른 그래프의 계획은 없는 것으로 본다."""
    with _plans_lock:
        box = _plans_box(s)
        return dict(box["plans"]) if box.get("graph") == list(graph or []) else {}


def _remember(s, graph, tpl, rec):
    with _plans_lock:
        box = _plans_box(s)
        if box.get("graph") != list(graph or []):
            box["graph"], box["plans"] = list(graph or []), {}
        box["plans"][str(tpl)] = rec
        _plans_save(s, box)


def applied(s, tpl, rev, changed):
    """그 계획을 적용함(…/outline/templates/{tpl}/match 의 by "agent" — outline_match_api 가 부른다). rev = 계획을 세운 문서 차례(그 계획이 맞는지 본다)."""
    with _plans_lock:
        box = _plans_box(s)
        rec = box["plans"].get(str(tpl))
        if rec is None or rec.get("rev") != rev:
            return
        rec["applied"] = {"at": time.time(), "rev": s.rev, "changed": int(changed)}
        _plans_save(s, box)


def _server():
    from app import server  # 세션은 server 것 — 부를 때 가져온다(순환 import 피함)
    return server


def _skill(key):
    try:
        return A.skill(key)
    except KeyError:
        raise HTTPException(404, "그런 스킬이 없습니다") from None


@router.get("/api/outline/agent")
def info():
    """{model, effort, backend, available, skills[{key, name, builtin, custom, version, updated, sha1, defaultChanged}]} — 에이전트가 부를 모델 · 저장해 둔 스킬 목록."""
    return {**A.status(), "skills": A.skills()}


@router.get("/api/outline/agent/skills/{key}")
def skill_get(key: str):
    return _skill(key)


@router.post("/api/outline/agent/skills")
def skill_new(body: dict = Body(...)):
    """{name, text} — 새 스킬을 만든다 → 스킬. 400 빈 글·긴 글·이름."""
    try:
        return A.save(None, body.get("name"), body.get("text"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/api/outline/agent/skills/{key}")
def skill_put(key: str, body: dict = Body(...)):
    """{name, text, version?} — 스킬을 고쳐 저장한다(기본 스킬이면 사용자 사본이 생긴다) → 스킬. 409 그 사이에 바뀜(version)."""
    try:
        return A.save(key, body.get("name"), body.get("text"), expect=body.get("version"))
    except KeyError:
        raise HTTPException(404, "그런 스킬이 없습니다") from None
    except R.StaleVersion as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/outline/agent/skills/{key}")
def skill_delete(key: str):
    """만든 스킬은 지운다({deleted: true}) · 기본 스킬은 사본을 버리고 기본본으로 되돌린다(스킬)."""
    try:
        return A.remove(key)
    except KeyError:
        raise HTTPException(404, "그런 스킬이 없습니다") from None


@router.get("/api/docs/{doc_id}/outline/agent/plans")
def plans_get(doc_id: str):
    """→ {rev, graph, plans: {tpl: {…계획 받기의 답, at, applied, state}}} — 지금 헤딩 그래프에서 받은 계획(state = none 없음 · planned 바로 적용 가능 · applied · stale 문서가 바뀜).
    2단계 결과가 없으면 plans 가 빈다."""
    server = _server()
    s = server._sess(doc_id)
    with s.lock:
        ov = server._outline_ov(s) if s.fmt == "hwpx" else None
        rev = s.rev
    graph = (ov or {}).get("run")
    got = plans(s, graph) if ov is not None else {}
    return {"rev": rev, "graph": graph, "plans": {k: {**v, "state": analysis.plan_state(v, rev)} for k, v in got.items()}}


@router.post("/api/docs/{doc_id}/outline/agent/{tpl}/plan")
def plan(doc_id: str, tpl: str, body: dict = Body(default={})):
    """{skill(키), request?(이번 요청 — 스킬보다 먼저), dry?} — 템플릿 tpl 의 서식 정리 계획을 에이전트(Opus 5.5)에게 받는다. 문서는 안 바뀐다.
    → {tpl, no, rev(자료를 읽은 문서 차례 — 적용 때 그대로 보낸다), skill{key, name, version, sha1}, request, plan{summary, levels[…], change, notes}, model, effort, backend, ms, costUsd}.
    dry=true 면 LLM 을 부르지 않고 {prompt(보낼 글), chars, levels(자료의 레벨 수), groups(갈래 수)} 만. 400 HWPX 아님 · 404 템플릿·스킬 없음 · 409 2단계 없음 ·
    422 갈래가 모두 하나뿐(정리할 것 없음) · 502 LLM 실패 · 503 LLM 꺼짐."""
    server = _server()
    key, request, dry = body.get("skill"), body.get("request"), bool(body.get("dry"))
    if request is not None and not isinstance(request, str):
        raise HTTPException(400, "request 는 글")
    return plan_one(server, server._sess(doc_id), tpl, key if isinstance(key, str) else "", request, dry=dry)


@router.post("/api/docs/{doc_id}/outline/agent/apply")
def apply_plans(doc_id: str, body: dict = Body(default={})):
    """{rev(화면이 계획을 본 문서 차례), tpls?([템플릿 id] — 없으면 모두)} — 받아 둔 서식 정리 계획 가운데 **지금 문서 차례에서 받은 것(state planned) 모두**를 에이전트가 고른 그대로
    (맞추기 · 떼기로 고른 갈래만 — 「그대로」 로 남긴 갈래는 빼고: tpl_agent.todo) **트랜잭션 하나**(실행 취소 1 · 기록 `outlinePlansApply`)로 문서에 반영한다 — 헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」.
    → 다른 구조 편집과 같은 꼴 + changed[줄 id] · templates[{tpl, no, changed(수), levels[…], splits[…]}](바꾼 것이 있는 템플릿) · plans(반영한 계획 수) · outline.
    바꿀 줄이 없으면 {changed: [], nothing: true, …}(그 계획들은 「반영함」 이 된다). 문서가 안 바뀌는 조합(떼기만 · 대표만)이면 오버레이만.
    400 HWPX 아님 · 꼴 · 계획이 지금 문서와 안 맞음(「T3 — …」) · 409 2단계 없음 · 문서가 바뀜(rev) · 반영할 계획 없음 · 422 표준 검사에 걸림(되돌림)."""
    from app import outline_match_api as OM  # 적용의 몸 — 템플릿 단위 맞추기와 같다
    server = _server()
    rev, tpls = body.get("rev"), body.get("tpls")
    if isinstance(rev, bool) or not isinstance(rev, int):
        raise HTTPException(400, "rev(계획을 본 문서 차례)가 필요합니다")
    if tpls is not None and (not isinstance(tpls, list) or not all(isinstance(t, (str, int)) and not isinstance(t, bool) for t in tpls)):
        raise HTTPException(400, "tpls 는 템플릿 id 목록")
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "템플릿 서식 정리는 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        if rev != s.rev:
            raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 서식 계획을 다시 받은 뒤 반영하세요")
        pick = None if tpls is None else {str(t) for t in tpls}
        order = {str(tid): i for i, tid in enumerate(ov["templates"])}
        recs = sorted(((tid, rec) for tid, rec in plans(s, ov.get("run")).items()
                       if tid in order and rec.get("plan") and analysis.plan_state(rec, rev) == "planned" and (pick is None or tid in pick)), key=lambda x: order[x[0]])
    if not recs:
        raise HTTPException(409, "반영할 서식 계획이 없습니다 — 계획을 받지 않았거나, 받은 뒤 문서가 바뀌었거나, 이미 반영했습니다")
    jobs = [(tid, lv) for tid, lv in ((tid, A.todo(rec["plan"])["levels"]) for tid, rec in recs) if lv]  # 바꿀 것이 있는 계획만 — 「바꿀 줄 없음」 인 계획은 아래에서 반영함으로만 적는다

    def log(per, doc):
        return {"templates": [{"tpl": x["no"], "levels": list(x["levels"]), "changed": len(x["changed"]), **({"splits": list(x["splits"])} if x["splits"] else {})} for x in per],
                **({"changed": sum(len(x["changed"]) for x in per)} if doc else {}), "by": "agent"}
    per, out = [], None
    if jobs:
        _, per, out = OM.apply_templates(server, doc_id, [(tid, OM._want(lv)) for tid, lv in jobs], rev=rev, op="outlinePlansApply",
                                         req={"rev": rev, "tpls": [tid for tid, _ in jobs]}, log=log)
        if not isinstance(out, dict):  # 표준 검사에 걸려 되돌림(422 응답) — 계획은 그대로 남는다
            return out
    else:
        with s.lock:
            out = {"changed": [], "nothing": True, **OM._state(s)}
    done = {x["tpl"]: len(x["changed"]) for x in per}
    for tid, _ in recs:
        applied(s, tid, rev, done.get(tid, 0))
    out["templates"] = [{"tpl": x["tpl"], "no": x["no"], "changed": len(x["changed"]), "levels": x["levels"], "splits": x["splits"]} for x in per]
    out["plans"] = len(recs)
    return out


def plan_one(server, s, tpl, key, request=None, dry=False):
    """템플릿 하나의 서식 정리 계획(위 끝점 · LLM 검증·보완 — app/analysis_llm.py 가 같이 쓴다) → 끝점의 답. 실패는 HTTPException(끝점과 같은 코드). 받은 계획은 남긴다(_remember)."""
    sk = _skill(key)
    if s.fmt != "hwpx":
        raise HTTPException(400, "템플릿 서식 정리는 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        try:
            mat = A.material(s.doc, ov, tpl)
        except KeyError:
            raise HTTPException(404, "그런 템플릿이 없습니다") from None
        rev, graph = s.rev, list(ov.get("run") or [])
    head = {"tpl": str(tpl), "no": mat["no"], "rev": rev, "skill": {k: sk[k] for k in ("key", "name", "version", "sha1")}, "request": (request or "").strip()[:A.REQUEST_MAX]}
    groups = sum(len(lv["groups"]) + lv["more"] for lv in mat["levels"])
    if dry:
        text = A.prompt(mat, sk, head["request"])
        return {**head, "prompt": text, "chars": len(text), "levels": len(mat["levels"]), "groups": groups, **A.status()}
    if not mat["levels"]:
        raise HTTPException(422, "이 템플릿에는 줄이 없습니다")
    if groups <= len(mat["levels"]) and not any(lv["repMissing"] for lv in mat["levels"]):
        raise HTTPException(422, "이 템플릿은 레벨마다 서식이 한 가지뿐입니다 — 정리할 것이 없습니다")
    res = A.run(mat, sk, head["request"])  # 잠금 밖 — 수십 초 걸린다
    works.log(s.id, "tplAgentPlan", rev=rev, tpl=mat["no"], skill=sk["key"], skillVersion=sk["version"], skillSha1=sk["sha1"], model=res["model"], backend=res["backend"],
              ms=res["ms"], costUsd=res["costUsd"], change=(res["plan"] or {}).get("change"), error=res["error"])
    if res["plan"] is None:
        if res["error"] == "off":
            raise HTTPException(503, "LLM 이 꺼져 있어 에이전트를 부를 수 없습니다(서버의 LLM 설정)")
        if res["error"] == "busy":
            raise HTTPException(503, "다른 LLM 작업이 자리를 다 쓰고 있습니다 — 잠시 뒤 다시 하세요")
        raise HTTPException(502, f"에이전트 호출에 실패했습니다: {res['error']}")
    out = {**head, "plan": res["plan"], **{k: res[k] for k in ("model", "effort", "backend", "ms", "costUsd")}}
    _remember(s, graph, tpl, {**out, "at": time.time(), "applied": None})
    return out
