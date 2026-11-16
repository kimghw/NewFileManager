"""템플릿 서식 정리 에이전트 API(spec_hwpx_웹편집 ② §8-4) — server.py 가 include 한다. 계산·스킬 저장은 `app/tpl_agent.py`, 오버레이는 `server._outline_ov`.
계획을 문서에 적용하는 끝점은 여기가 아니라 템플릿 단위 맞추기(`outline_match_api.match_template` — POST …/outline/templates/{tpl}/match)다."""
from fastapi import APIRouter, Body, HTTPException

from app import heading_rules as R
from app import tpl_agent as A
from app import works

router = APIRouter()


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
    sk = _skill(key if isinstance(key, str) else "")
    s = server._sess(doc_id)
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
        rev = s.rev
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
    return {**head, "plan": res["plan"], **{k: res[k] for k in ("model", "effort", "backend", "ms", "costUsd")}}
