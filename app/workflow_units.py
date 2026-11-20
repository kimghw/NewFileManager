"""실행 단위 — 워크플로우의 단계 줄을 실행 · 조립이 읽는 꼴로(spec_워크플로우 ② §18-2 「실행 단위」). **순수** — 다른 app 코드를 가져오지 않는다(조립 저장 app/custom_tasks.py 도 이것을 읽는다).

- 단위 하나 = 등록부(app/workflow.py) 단계 줄의 기계가 읽는 짝. 글(이름 · 하는 일 · 조건 글)은 등록부의 줄에만 있고, 여기는 실행기 · 조립 검사가 쓰는 값만 지닌다:
  key(= 그 줄의 단계 key) · home(사는 일반 단계 | "hand") · place(놓을 수 있는 자리 — doc 문서마다 · pair 원본 → 목적 · flow 워크플로우 전체) · roles(doc 자리에서 고를 수 있는 문서 역할) ·
  kind(auto 실행기가 한다 · pick 사람이 고르는 줄 — 실행기는 지나감 · hand 사람이 하고 「했음」) · change(none · store · doc) · paid("" · doc 문서마다 유료 · stage 묶음째 유료) ·
  needs(먼저 있어야 할 사실) · gives(끝나면 생기는 사실) · spoils(끝나면 무르는 사실) · redo(낡았다는 답을 받으면 한 번 다시 할 사실) · once(한 실행에 한 번) · optional · via(화면이 부모 줄 안에 그리는 줄의 부모 key) ·
  server(서버 실행기가 돌릴 수 있나 — 걸음마다 참으로: ② §18-10).
- 가족: 문서 사이의 일(pair)은 틀마다 엔진이 달라 (가족, key)로 찾는다 — `relay`(이관형) · `gather`(취합형 — 걸음 5) · 두 틀이 같이 쓰는 `common`. 한 워크플로우 안에서는 key 가 하나다.
- 상태 함수(`state`)는 화면의 지금 식(app/static/app.js taskSteps)을 그대로 옮긴 것이다 — 재료(문서마다의 사실)는 문(app/unit_steps.py `facts`)이 준다. 서버가 아직 세지 않는 줄은 None."""

FACTS = ("slots", "heads", "checked", "config", "fit", "fresh", "links", "plan", "filled", "clean", "frame", "assigned")   # 사실의 이름(문서마다 · 쌍마다 · 워크플로우 전체 — ② §18-2)
PLACES = ("doc", "pair", "flow")
KINDS = ("auto", "pick", "hand")
ROLES = ("source", "target")   # 문서 역할 — 차례 = 원본 → 목적(app/workflow.py ROLES · app/custom_tasks.py ROLES 와 같다)


def _u(key, home, place, *, roles=(), kind="auto", change="none", paid="", needs=(), gives=(), spoils=(), redo=(), once=False, optional=False, via="", server=False):
    return dict(key=key, home=home, place=place, roles=tuple(roles), kind=kind, change=change, paid=paid, needs=tuple(needs), gives=tuple(gives), spoils=tuple(spoils), redo=tuple(redo),
                once=once, optional=optional, via=via, server=server)


# 두 틀이 같이 쓰는 단위 — 준비 · 문서 검토 · 구성 맞추기 · 문서 정리 · 사람이 하는 일
COMMON = {u["key"]: u for u in (
    _u("files", "", "flow", kind="pick", gives=("slots",), server=True),                                                    # 준비 — 실행기는 안 한다(칸이 비면 시작이 거절)
    _u("heads", "stage_review", "doc", roles=ROLES, change="store", needs=("slots",), gives=("heads",), server=True),       # 헤딩 · 표 분석(배경 일 · 목적 문서면 끝에 작성 지침 저장)
    _u("headsLlm", "stage_review", "doc", roles=ROLES, change="store", paid="doc", needs=("heads",), gives=("checked",), server=True),   # LLM 검증·보완(배경 일 — 못 쓰거나 건너뛰면 「건너뜀」)
    _u("configLoad", "stage_fit", "flow", kind="pick", change="store", optional=True),                                      # 구성 불러오기(선택 — 실행기는 지나감)
    _u("config", "stage_fit", "flow", change="store", needs=("slots",), gives=("config",)),                                 # 프로젝트 구성 확정
    _u("division", "stage_fit", "doc", roles=("target",), change="doc", needs=("config",), gives=("fit",), spoils=("fresh",)),   # 프로젝트 구성 반영(같은 검사 · 울타리)
    _u("reheads", "stage_fit", "doc", roles=("target",), change="store", needs=("fit",), gives=("fresh", "heads")),         # 다시 문서 검토
    _u("reheadsLlm", "stage_fit", "doc", roles=("target",), change="store", paid="doc", needs=("fresh",), gives=("checked",)),   # 다시 문서 검토(LLM)
    _u("guide", "stage_clean", "doc", roles=("target",), change="doc", needs=("filled",), gives=("clean",)),                # 작성요령 삭제(먼저 있어야 할 것은 그 줄이 정의에 있을 때만)
    _u("hand", "hand", "doc", roles=ROLES, kind="hand"),                                                                    # 사람이 하는 일(여럿 놓을 수 있다 — ② §18-7)
)}
# 이관형 — 다른 양식 사이의 자리 연결 · 넣기(app/merge_api.py)
RELAY = {u["key"]: u for u in (
    _u("link", "stage_fill", "pair", change="store", needs=("heads", "fresh"), gives=("links",)),
    _u("llm", "stage_fill", "pair", change="store", paid="stage", needs=("links",), once=True, optional=True, via="link"),
    _u("plan", "stage_fill", "pair", needs=("links",), gives=("plan",)),
    _u("gaps", "stage_fill", "pair", change="store", paid="stage", needs=("plan",), spoils=("plan",), once=True, optional=True, via="plan"),
    _u("tableMap", "stage_fill", "pair", change="store", paid="stage", needs=("plan",), spoils=("plan",), once=True, optional=True, via="plan"),
    _u("apply", "stage_fill", "pair", change="doc", needs=("plan",), gives=("filled",), redo=("plan",)),
)}
GATHER = {}   # 취합형 — 걸음 5 에 채운다(배포 기준본 · 기관 문서 등록 · 자리 연결 · LLM 검토 · 계획 · 반영 · 끌어 넣기: app/merge_gather_api.py)
FAMILIES = {"common": COMMON, "relay": RELAY, "gather": GATHER}


def unit(key, family="relay"):
    """(가족, key) → 단위 | None — 가족의 것이 먼저, 없으면 두 틀이 같이 쓰는 것."""
    return FAMILIES.get(family, {}).get(key) or COMMON.get(key)


def roles_of(on):
    """등록부 단계 줄의 on → 그 줄이 닿는 문서 역할(차례 = 원본 → 목적). pair = 원본이 주고 목적이 받는다(둘 다) · flow · 빈 값 = 없음(문서마다의 일이 아니다)."""
    return {"source": ("source",), "target": ("target",), "both": ROLES, "pair": ROLES}.get(on, ())


# ---------------------------------------------------------------- 상태 — 화면의 지금 식을 그대로(app/static/app.js taskSteps 의 files · heads · llmStep)
# ctx = {ready(문서 칸이 참), lack[빈 칸의 문서 이름], docs[그 줄의 문서 — {role, title(문서 이름), facts(unit_steps.facts 의 값 | None)}], llm(LLM 을 쓸 수 있나 | None = 모름), skip(건너뛴 문서 id 들)}
# → {st: done | todo | busy | blocked | failed, skipped?, text, per?[{doc, role, st, skipped?, text}], paid?[유료로 부를 문서 id]} — 「지금 · 할 수 있음」 은 묶음의 차례에서 센다(workflow_state)
def _got(f):
    return bool(f and f["heads"]["s2"] and f["heads"]["s3"])


def _job(f):
    return (f["heads"].get("job") if f else None) or {}


def _files(ctx):
    lack = ctx.get("lack") or []
    return {"st": "todo" if lack else "done", "text": f"{' · '.join(lack)} 칸이 비었습니다" if lack else " · ".join(d["title"] for d in ctx.get("docs") or [])}


def _heads(ctx):
    docs = ctx.get("docs") or []
    if not ctx.get("ready") or not docs:
        return {"st": "todo", "text": ""}
    if any(d["facts"] is None for d in docs):
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    word = lambda d: "있음" if _got(d["facts"]) else "없음"  # noqa: E731
    done = all(_got(d["facts"]) for d in docs)
    run = [d for d in docs if _job(d["facts"]).get("status") == "running"]
    fail = next((d for d in docs if not _got(d["facts"]) and _job(d["facts"]).get("error")), None)
    text = "헤딩 그래프·표 구조: " + " · ".join(f"{d['title']} {word(d)}" for d in docs)
    if run:
        text += " · " + " · ".join(f"{d['title']} {'LLM 검증·보완' if _job(d['facts']).get('chain') else '분석'} 중…" for d in run)
    elif fail:
        text += f" · {fail['title']} 분석 실패 — {_job(fail['facts']).get('error')}"
    per = [{"doc": d["facts"]["id"], "role": d["role"], "st": "done" if _got(d["facts"]) else "busy" if d in run else "todo"} for d in docs]
    return {"st": "done" if done else "busy" if run else "failed" if fail else "todo", "text": text, "per": per}


def _llm_one(d, ctx):
    """문서 하나의 「LLM 검증·보완」 — 끝남 = 거침 | LLM 을 못 씀 | 사람이 건너뜀(뒤 둘은 「건너뜀」) · 스크립트 분석이 먼저."""
    f, who = d["facts"], d["title"]
    if f is None:
        return {"doc": None, "role": d["role"], "st": "blocked", "text": "문서를 읽지 못했습니다"}
    one = {"doc": f["id"], "role": d["role"]}
    if not _got(f):
        return {**one, "st": "todo", "text": "", "wait": True}   # 헤딩 · 표 분석이 먼저(그래도 「한 번에 진행」 은 분석한 뒤 부른다 — 유료 대상에는 센다)
    J = _job(f)
    run, did, off, skip = J.get("status") == "running" and bool(J.get("chain")), bool(f["heads"]["llm"]), ctx.get("llm") is False, f["id"] in (ctx.get("skip") or ())
    done = not run and (did or off or skip)
    text = (f"{who} — LLM 검증·보완 중…(헤딩 · 템플릿 → 표 → 서식 정리 계획 · 몇 분)" if run else f"{who} — LLM 검증·보완을 거쳤습니다" if did
            else "LLM 을 쓸 수 없어 건너뜁니다 — 스크립트 분석만으로 진행합니다" if off else f"건너뜀 — {who}는 스크립트 분석만으로 진행합니다" if skip
            else "LLM 을 쓸 수 있는지 확인하는 중…" if ctx.get("llm") is None
            else f"{who}의 헤딩 · 템플릿 → 표 → 서식 정리 계획을 LLM 이 검증·보완합니다 — 유료 · 몇 분 · 문서는 바뀌지 않습니다" + (f" · 지난 실행 실패 — {J['error']}" if J.get("chain") and J.get("error") else ""))
    return {**one, "st": "busy" if run else "done" if done else "todo", "skipped": done and not did, "text": text}


def _heads_llm(ctx):
    docs = ctx.get("docs") or []
    if not ctx.get("ready") or not docs:
        return {"st": "todo", "text": ""}
    per = [_llm_one(d, ctx) for d in docs]
    if any(p["st"] == "blocked" for p in per):
        return {"st": "blocked", "text": "문서를 읽지 못했습니다", "per": per}
    done = all(p["st"] == "done" for p in per)
    texts = list(dict.fromkeys(p["text"] for p in per if p["text"]))
    # 유료로 부를 문서(화면 taskPaidDocs 와 같은 셈) — 아직 거치지 않았고 건너뛰지 않은 문서(스크립트 분석이 아직 없어도 센다) · LLM 을 못 쓰면 없음
    paid = [] if ctx.get("llm") is False else [d["facts"]["id"] for d, p in zip(docs, per) if not d["facts"]["heads"]["llm"] and d["facts"]["id"] not in (ctx.get("skip") or ()) and p["st"] != "done"]
    return {"st": "done" if done else "busy" if any(p["st"] == "busy" for p in per) else "todo", "skipped": done and all(p.get("skipped") for p in per),
            "text": " · ".join(texts), "per": per, "paid": paid}


_STATE = {"files": _files, "heads": _heads, "headsLlm": _heads_llm}


def state(key, ctx, family="relay"):
    """그 줄의 지금 상태 | None(서버가 아직 세지 않는 줄 — 화면이 센다: ② §17-5 의 `server: false`)."""
    u = unit(key, family)
    fn = _STATE.get(key) if u and u["server"] else None
    return fn(ctx) if fn else None
