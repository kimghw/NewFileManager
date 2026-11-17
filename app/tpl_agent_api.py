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


OLD_LABELS = (("앞 공백", "레터 앞 빈칸"), ("레터 뒤 공백", "레터 뒤 빈칸"))  # 2026-11-17 화면 말이 바뀌기 전에 남긴 계획의 값 이름(spec_헤딩_추출 ② §0 「줄 첫머리의 말」)


def _relabel(raw):
    """남겨 둔 계획 글(JSON)의 옛 값 이름을 지금 말로 — **값 이름 그 자체인 문자열만**(「대표와 다른 값」 의 이름 · 값 사전의 키). LLM 이 쓴 까닭 글 속의 말은 그대로 둔다."""
    for old, new in OLD_LABELS:
        raw = raw.replace(json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False))
    return raw


def _plans_box(s):
    """세션의 받은 계획 상자 {graph: [run, at] | None, plans: {tpl: 기록}} — 처음 한 번 작업 폴더에서 읽는다(옛 값 이름은 지금 말로 읽는다 — `_relabel`)."""
    box = getattr(s, "tpl_plans", None)
    if box is None:
        box = {"graph": None, "plans": {}}
        path = _plans_path(s.id)
        if path is not None and path.is_file():
            try:
                got = json.loads(_relabel(path.read_text(encoding="utf-8")))
                if isinstance(got, dict) and isinstance(got.get("plans"), dict):
                    box = {"graph": got.get("graph"), "plans": got["plans"], "applies": got.get("applies") if isinstance(got.get("applies"), list) else []}  # applies = 반영 기록(실행마다 — note_apply)
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


def _remember(s, graph, tpl, rec, since=None):
    """받은 계획을 남긴다 → 남겼는가. since = 그 요청이 자료를 읽은 때(기록의 since) — 같은 템플릿에 **더 늦게 시작한 요청**의 계획이 이미 남아 있으면 덮지 않는다(겹친 요청은 늦게 시작한 쪽이 이긴다).
    상자가 다른 그래프의 것이면 새 상자로 바꾼다 — 부르는 쪽(plan_one)이 그 그래프가 지금 것인지 먼저 본다(옛 그래프의 늦은 답이 새 그래프의 상자를 갈아 치우지 않게)."""
    with _plans_lock:
        box = _plans_box(s)
        if box.get("graph") != list(graph or []):
            box["graph"], box["plans"], box["applies"] = list(graph or []), {}, []
        old = box["plans"].get(str(tpl))
        if since is not None and old and (old.get("since") or 0) > since:
            return False
        box["plans"][str(tpl)] = rec
        _plans_save(s, box)
        return True


def plan_at(server, s, tpl, rev, want=None):
    """반영하려는 계획의 표시(그 계획의 at) — 지금 헤딩 그래프에 남아 있는 그 템플릿의 계획이 rev(계획을 세운 문서 차례)의 것이고, 화면이 보낸 것(want — 화면이 가진 계획의 at)이 있으면
    그것과 같을 때만. None = 그런 계획이 없다(그 사이 다른 계획으로 바뀜 · 이미 반영함) — 반영은 하되 「반영함」 으로 적지 않는다(남아 있는 계획은 반영한 그 계획이 아니다)."""
    with s.lock:
        ov = server._outline_ov(s) if s.fmt == "hwpx" else None
    if ov is None:
        return None
    rec = plans(s, ov.get("run")).get(str(tpl))
    if not rec or rec.get("at") is None or (want is not None and want != rec["at"]):
        return None
    with s.lock:
        state = state_of(s, ov, rec, s.rev)
    if state == "planned":
        return rec["at"]
    if want is not None and rec.get("fp"):  # 화면이 가진 그 계획이 남아 있는데 지금 문서와 안 맞는다(그 템플릿의 줄이 바뀜 · 이미 반영함) — 옛 계획대로 맞추지 않는다
        raise HTTPException(409, "계획을 받은 뒤 이 템플릿의 줄이 바뀌었습니다(또는 이미 반영했습니다) — 서식 계획을 다시 받은 뒤 반영하세요")
    return None


APPLIES_MAX = 20  # 작업 폴더에 남기는 반영 기록 수(헤딩 그래프마다 — 그래프가 바뀌면 계획과 함께 비운다)


def note_apply(s, graph, by, items, relations=None):
    """반영 한 번을 적는다(spec_헤딩_추출 ② §7 「결과 화면」) — items = [{tpl, no, plan(그 계획의 at | None), summary, changed(바뀐 줄 수), levels(tpl_agent.apply_view)}]. by = "all"(모두 반영 · 전체 실행) | "tpl"(템플릿 하나).
    계획 기록은 다음 계획이 덮지만 이 기록은 실행마다 따로 남는다(무엇을 어떻게 바꿨나 — 전 → 후 값 · 뗀 것 · 남긴 것과 까닭)."""
    items = [x for x in items if x]
    relations = [{k: v for k, v in m.items() if k != "ids"} for m in relations or []]  # 저절로 건 종속(확실한 것 — outline_match.auto_merge)
    if not items and not relations:
        return
    with _plans_lock:
        box = _plans_box(s)
        if box.get("graph") != list(graph or []):
            box["graph"], box["plans"], box["applies"] = list(graph or []), {}, []
        rows = box.setdefault("applies", [])
        rows.append({"at": time.time(), "rev": s.rev, "by": by, "templates": items, "lines": sum(int(x.get("changed") or 0) for x in items), "relations": relations})
        del rows[:-APPLIES_MAX]
        _plans_save(s, box)


def applies(s, graph):
    """지금 헤딩 그래프의 반영 기록(오래된 것부터) — 기록마다 템플릿의 `live` = 그 반영이 지금 문서에 남아 있나(오버레이의 표가 그 계획의 것 — 되돌렸으면 거짓)."""
    with _plans_lock:
        box = _plans_box(s)
        rows = [dict(r) for r in box.get("applies") or []] if box.get("graph") == list(graph or []) else []
    marks = (getattr(s, "outline", None) or {}).get("agent") or {}
    seen = set()  # 같은 계획을 되돌렸다가 다시 반영하면 기록이 둘이다 — 「남아 있음」 은 그 계획의 **마지막** 반영만(앞 기록은 되돌렸던 것)
    for r in reversed(rows):
        ts = []
        for t in r.get("templates") or []:
            key = (str(t.get("tpl")), t.get("plan"))
            ts.append({**t, "live": t.get("plan") is not None and marks.get(key[0]) == t.get("plan") and key not in seen})
            seen.add(key)
        r["templates"] = ts
    return rows


def state_of(s, ov, rec, rev=None):
    """받은 계획 하나의 상태(analysis.plan_state) — 그 템플릿의 지금 지문과 견줘서(세션 잠금 안에서 부른다: 지문은 문서를 읽는다). 지문이 없는 옛 기록은 문서 차례로."""
    fp = A.fingerprint_of(s.doc, ov, rec.get("tpl")) if rec and rec.get("fp") and ov is not None and str(rec.get("tpl")) in ov.get("templates", {}) else None
    return analysis.plan_state(rec, s.rev if rev is None else rev, ov, fp)


def applied(s, tpl, rev, changed, at=None):
    """그 계획을 반영함 — 기록에 applied{at, rev, changed}. rev = 계획을 세운 문서 차례 · at = 반영한 계획의 표시(반영 전에 잡은 것 — 그 사이 다른 계획으로 바뀌었으면 적지 않는다).
    「반영함」 인지는 이 기록 + 개요 오버레이의 표(반영의 트랜잭션이 같은 잠금 안에서 적는다 — outline_match_api._marks)로 본다(analysis.plan_applied)."""
    with _plans_lock:
        box = _plans_box(s)
        rec = box["plans"].get(str(tpl))
        if rec is None or (rec.get("at") != at if at is not None else rec.get("rev") != rev):  # 어느 계획인지는 그 계획의 표시(at)로 — 계획은 문서 차례에 묶이지 않는다(표시가 없는 옛 길만 rev)
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
    with s.lock:
        out = {k: {**v, "state": state_of(s, ov, v, rev)} for k, v in got.items()}
    return {"rev": rev, "graph": graph, "plans": out}


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
    (맞추기 · 떼기로 고른 갈래 · 대표만 바꾸는 레벨 — 「그대로」 로 남긴 갈래는 빼고: tpl_agent.todo) **트랜잭션 하나**(실행 취소 1 · 기록 `outlinePlansApply`)로 문서에 반영한다 — 헤딩 추출 탭 진행 줄 「조정」 의 「모두 반영」.
    → 다른 구조 편집과 같은 꼴 + changed[줄 id] · templates[{tpl, no, changed(완전히 맞춘 줄 수), left(모양만 맞춘 줄 수), levels[{level, rep, repChanged, changed, left?}], splits[…]}](바꾼 것이 있는 템플릿) · plans(반영한 계획 수) · reps(대표를 바꾼 레벨 수) · outline ·
    left[{id, tpl, no, level, why, kinds}] — 형광펜 · 필드 · 변경 추적 표지 때문에 글을 못 바꿔 모양만 맞추고 남긴 줄(spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」 — 그 줄 때문에 전체를 되돌리지 않는다 · 오버레이 agentLeft).
    바꿀 줄이 없으면 {changed: [], nothing: true, …}(그 계획들은 「반영함」 이 된다). 문서가 안 바뀌는 조합(떼기만 · 대표만 · 종속만)이면 오버레이만 — 다만 새 대표 · 새 템플릿의 대표와 그 갈래에
    확정 서식(묶음 빈칸 · 자리 규칙)이 안 걸려 있으면 같은 트랜잭션에서 건다(문서가 바뀐다 — placed).
    400 HWPX 아님 · 꼴 · 계획이 지금 문서와 안 맞음(「T3 — …」) · 409 2단계 없음 · 문서가 바뀜(rev) · 반영할 계획 없음 · 422 표준 검사에 걸림(되돌림)."""
    from app import outline_conform as OC  # 확정 서식으로 바꾸기(② §8-8)
    from app import outline_match_api as OM  # 적용의 몸 — 템플릿 단위 맞추기와 같다
    server = _server()
    rev, tpls, seen = body.get("rev"), body.get("tpls"), body.get("plans")
    if isinstance(rev, bool) or not isinstance(rev, int):
        raise HTTPException(400, "rev(계획을 본 문서 차례)가 필요합니다")
    if tpls is not None and (not isinstance(tpls, list) or not all(isinstance(t, (str, int)) and not isinstance(t, bool) for t in tpls)):
        raise HTTPException(400, "tpls 는 템플릿 id 목록")
    # plans = 화면이 본 계획의 표시 {템플릿 id: at}(분석 상태 서식 항목의 llm.list[].at) — 주면 **그 계획들만**, 지금 남아 있는 계획이 그것일 때만 반영한다
    # (문서 차례가 같아도 그 사이 계획을 다시 받았으면 화면이 본 것과 다른 계획이다 — 2026-11-16 astra: spec_hwpx_웹편집 ② §8-4 「계획 모두 반영」)
    if seen is not None and (not isinstance(seen, dict) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in seen.values())):
        raise HTTPException(400, "plans 는 {템플릿 id: 계획 표시(at)}")
    s = server._sess(doc_id)
    if s.fmt != "hwpx":
        raise HTTPException(400, "템플릿 서식 정리는 HWPX 에서만 됩니다(헤딩 그래프가 HWPX 만)")
    with s.lock:
        ov = server._outline_ov(s)
        if ov is None:
            raise HTTPException(409, "헤딩 추출 2단계(헤딩 그래프)를 먼저 실행하세요")
        if rev != s.rev:  # 화면이 본 문서가 지금 것이 아니다(계획이 옛것이라는 뜻이 아니다 — 계획은 그 템플릿 줄의 지문으로 본다)
            raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 화면이 문서를 다시 읽은 뒤 한 번 더 누르세요")
        pick = None if tpls is None else {str(t) for t in tpls}
        order = {str(tid): i for i, tid in enumerate(ov["templates"])}
        recs = sorted(((tid, rec) for tid, rec in plans(s, ov.get("run")).items()
                       if tid in order and rec.get("plan") and state_of(s, ov, rec, rev) == "planned" and (pick is None or tid in pick)), key=lambda x: order[x[0]])
        if seen is not None:
            have = {tid: rec.get("at") for tid, rec in recs}
            off = [tid for tid, at in seen.items() if have.get(str(tid)) != at]
            if off:
                raise HTTPException(409, "받아 둔 서식 계획이 그 사이에 바뀌었습니다(다시 받았거나 이미 반영함) — 조정 줄의 줄 수를 다시 확인한 뒤 반영하세요")
            recs = [(tid, rec) for tid, rec in recs if tid in {str(t) for t in seen}]
    # 확실한 종속(한 자리에만 매달린 가지 템플릿 → 그 자리의 템플릿 아래 — spec_hwpx_웹편집 ② §8-2 「종속 제안」)도 「모두 반영」 이 건다 — 2026-11-16 사용자 「확실이 구분되는건 자동으로」. relations: false 면 안 건다
    rel_on = body.get("relations") is not False and pick is None
    # 확정 서식으로(spec_hwpx_웹편집 ② §8-8 — 2026-11-16 사용자 「'조정' 단계에서 보정을 해줘야지」): 「모두 반영」 은 맞춘 뒤에 모든 템플릿(고른 템플릿)의 레벨마다 대표와 그 갈래의 줄에
    # 레터 뒤 묶음 빈칸 · 자리 규칙(둘째 줄 = 글 시작)을 스크립트로 건다 — 받아 둔 계획이 없어도 그 줄이 남아 있으면 그것만 건다
    # `place: false` 면 걸지 않는다(계획 · 종속만 — 전의 동작)
    settle = None if not OM._place_on(body) else "all" if pick is None else sorted(pick)
    with s.lock:
        sure = [h for h in A.M.merge_hints(ov) if h["sure"]] if rel_on else []
        pend = OC.pending(s.doc, ov, None if pick is None else set(OM._settle_ids(ov, settle))) if settle is not None else []
        if settle is not None and not pend and sure:  # 종속만 남은 반영 — 넣은 **뒤의** 대표로 보면 안 걸린 줄이 생기는가(② §8-8): 생기면 아래에서 문서 편집 트랜잭션으로(같은 반영에서 확정 서식 · 실행 취소 1)
            pend = OM._pend_after(s, ov, [], True, settle)
    if not recs and not sure and not pend:
        raise HTTPException(409, "반영할 서식 계획이 없습니다 — 계획을 받지 않았거나, 받은 뒤 문서가 바뀌었거나, 이미 반영했습니다")
    jobs = [(tid, lv) for tid, lv in ((tid, A.todo(rec["plan"])["levels"]) for tid, rec in recs) if lv]  # 바꿀 것이 있는 계획만 — 「바꿀 줄 없음」 인 계획은 아래에서 반영함으로만 적는다

    def log(per, doc):  # changed = 완전히 맞춘 줄 · left = 표지 때문에 모양만 맞춘 줄(spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」)
        nl = sum(len(x.get("left") or ()) for x in per)
        return {"templates": [{"tpl": x["no"], "levels": list(x["levels"]), "changed": len(x["changed"]), **({"left": len(x["left"])} if x.get("left") else {}),
                               **({"splits": list(x["splits"])} if x["splits"] else {}), **({"into": list(x["into"])} if x.get("into") else {})} for x in per],
                **({"changed": sum(len(x["changed"]) for x in per)} if doc else {}), **({"left": nl} if nl else {}), "by": "agent"}
    marks = {tid: rec["at"] for tid, rec in recs if rec.get("at") is not None}  # 반영하는 계획의 표시 — 반영과 같은 트랜잭션 · 같은 잠금 안에서 오버레이에 적는다(OM._marks: 「반영함은 문서에 남아 있을 때만」)
    per, out, rel = [], None, []
    if jobs or pend:
        _, per, out = OM.apply_templates(server, doc_id, [(tid, OM._want(lv)) for tid, lv in jobs], rev=rev, op="outlinePlansApply",
                                         req={"rev": rev, "tpls": [tid for tid, _ in jobs]}, log=log, marks=marks, relations=rel if rel_on else None, settle=settle,
                                         by="agent")  # 계획이 바꾼 대표 = 에이전트가 정한 대표(사람이 정한 대표처럼 잠기지 않는다 — 다음 계획이 바꿀 수 있다)
        if not isinstance(out, dict):  # 표준 검사에 걸려 되돌림(422 응답) — 계획은 그대로 남는다
            return out
    elif sure:  # 바꿀 서식은 없고 종속만 — 오버레이만 바꾸는 트랜잭션 하나(실행 취소 1)
        with s.lock:
            if rev != s.rev:
                raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 화면이 문서를 다시 읽은 뒤 한 번 더 누르세요")

            def change():
                OM._marks(s.outline, marks)
                rel.extend(A.M.auto_merge(s.outline))
                return {"relations": [{k: v for k, v in m.items() if k != "ids"} for m in rel], "by": "agent"}
            got, ok = OM._model_only(server, s, "outlinePlansApply", {"rev": rev, "relations": True}, change)
            if not ok:
                return got
            out = {"changed": [], "nothing": not rel, "outline": OM.outline_pos.view(s.doc, s.outline), **OM._state(s)}
    else:
        with s.lock:
            if rev != s.rev:  # 위에서 계획을 고른 뒤 그 사이에 문서가 바뀌었다(다른 화면의 편집 · 실행 취소)
                raise HTTPException(409, "그 사이에 문서가 바뀌었습니다 — 서식 계획을 다시 받은 뒤 반영하세요")
            OM._marks(s.outline, marks)
            s.saved_rev = -1  # 문서 차례가 그대로다 — 표가 다음 저장에 들어가게
            out = {"changed": [], "nothing": True, **OM._state(s)}
    done = {x["tpl"]: len(x["changed"]) for x in per}  # 완전히 맞춘 줄(표지 때문에 모양만 맞춘 줄은 left — spec_hwpx_웹편집 ② §8-8 「짝 표지가 든 줄」)
    kept = {x["tpl"]: len(x.get("left") or ()) for x in per}
    for tid, rec in recs:
        applied(s, tid, rev, done.get(tid, 0), rec.get("at"))
    # into = 윗레벨 떼기가 먼저 데려간 줄의 떼기 — 새 템플릿 대신 데려간 템플릿의 그 레벨 대표로(outline_match_api._cut_now)
    out["templates"] = [{"tpl": x["tpl"], "no": x["no"], "changed": len(x["changed"]), "left": kept[x["tpl"]], "levels": x["levels"], "splits": x["splits"],
                         **({"into": x["into"]} if x.get("into") else {})} for x in per]
    into = {x["tpl"]: x.get("into") or [] for x in per}
    out.setdefault("left", [])  # 표지 때문에 모양만 맞춘 줄 [{id, tpl, no, level, why, kinds}](apply_templates 의 답) — 계획 상태는 「반영함」 그대로
    out["plans"] = len(recs)
    out["reps"] = sum(1 for x in per for lv in x["levels"] if lv["repChanged"])  # 대표를 바꾼 레벨 수 — 맞춘 줄이 0 이어도 한 일이다(조정 줄 · 「전체 실행」 의 끝난 글)
    todo = dict(jobs)
    out["merged"] = [{k: v for k, v in m.items() if k != "ids"} for m in rel]  # 저절로 건 종속 [{id, no, child, childNo, parent, parentNo, at, moved}]
    note_apply(s, ov.get("run"), "all", [{"tpl": tid, "no": rec.get("no"), "plan": rec.get("at"), "summary": (rec.get("plan") or {}).get("summary", ""), "changed": done.get(tid, 0),
                                          **({"left": kept[tid]} if kept.get(tid) else {}),
                                          "levels": A.apply_view(rec.get("plan"), todo.get(tid) or [], into.get(tid))} for tid, rec in recs], relations=rel)
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
        prev = plans(s, ov.get("run")).get(str(tpl)) or {}
        try:  # 앞 계획이 검토해 그대로 둔 갈래는 뒤로 — 갈래가 많은 레벨에서 못 본 갈래가 에이전트에 닿게(A.material 의 reviewed)
            mat = A.material(s.doc, ov, tpl, reviewed=(prev.get("plan") or {}).get("reviewed"), sent=(prev.get("plan") or {}).get("sent"))
        except KeyError:
            raise HTTPException(404, "그런 템플릿이 없습니다") from None
        rev, graph, t0 = s.rev, list(ov.get("run") or []), time.time()
        fp = A.fingerprint_of(s.doc, ov, tpl)  # 자료를 읽은 그 잠금 안에서 — 계획은 이 지문에 묶인다(문서 차례가 아니라: 「계획은 줄 지문에」)
    head = {"tpl": str(tpl), "no": mat["no"], "rev": rev, "fp": fp, "skill": {k: sk[k] for k in ("key", "name", "version", "sha1")}, "request": (request or "").strip()[:A.REQUEST_MAX]}
    groups = sum(len(lv["groups"]) + lv["more"] + len(lv.get("held") or []) + len(lv.get("heldAuto") or []) for lv in mat["levels"])
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
    out = {**head, "plan": res["plan"], **{k: res[k] for k in ("model", "effort", "backend", "ms", "costUsd")}, "at": time.time()}  # at = 이 계획의 표시 — 화면이 적용할 때 되돌려 보낸다(plan_at)
    with s.lock:  # LLM 을 기다린 사이 2단계를 다시 돌렸으면(다른 그래프) 남기지 않는다 — 옛 그래프의 늦은 답이 새 그래프의 계획 상자를 갈아 치우지 않게
        now = server._outline_ov(s)
        current = now is not None and list(now.get("run") or []) == graph
    if current:
        _remember(s, graph, tpl, {**out, "applied": None, "since": t0}, since=t0)  # 더 늦게 시작한 요청이 먼저 끝나 남긴 계획은 덮지 않는다
    return out
