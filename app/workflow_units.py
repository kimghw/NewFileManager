"""실행 단위 — 워크플로우의 단계 줄을 실행 · 조립이 읽는 꼴로(spec_워크플로우 ② §18-2 「실행 단위」). **순수** — 다른 app 코드를 가져오지 않는다(조립 저장 app/custom_tasks.py 도 이것을 읽는다).

- 단위 하나 = 등록부(app/workflow.py) 단계 줄의 기계가 읽는 짝. 글(이름 · 하는 일 · 조건 글)은 등록부의 줄에만 있고, 여기는 실행기 · 조립 검사가 쓰는 값만 지닌다:
  key(= 그 줄의 단계 key) · home(사는 일반 단계 | "hand") · place(놓을 수 있는 자리 — doc 문서마다 · pair 원본 → 목적 · flow 워크플로우 전체) · roles(doc 자리에서 고를 수 있는 문서 역할) ·
  kind(auto 실행기가 한다 · pick 사람이 고르는 줄 — 실행기는 지나감 · hand 사람이 하고 「했음」) · change(none · store · doc) · paid("" · doc 문서마다 유료 · stage 묶음째 유료) ·
  needs(먼저 있어야 할 사실) · gives(끝나면 생기는 사실) · spoils(끝나면 무르는 사실) · redo(낡았다는 답을 받으면 한 번 다시 할 사실) · once(한 실행에 한 번) · optional · via(화면이 부모 줄 안에 그리는 줄의 부모 key) ·
  server(서버 실행기가 돌릴 수 있나 — 걸음마다 참으로: ② §18-10).
- 가족: 문서 사이의 일(pair)은 틀마다 엔진이 달라 (가족, key)로 찾는다 — `relay`(이관형) · `gather`(취합형 — 걸음 5) · 두 틀이 같이 쓰는 `common`. 한 워크플로우 안에서는 key 가 하나다.
- 상태 함수(`state`)는 화면의 지금 식(app/static/app.js taskSteps)을 그대로 옮긴 것이다 — 재료(문서마다의 사실)는 문(app/unit_steps.py `facts`)이 준다. 서버가 아직 세지 않는 줄은 None."""

FACTS = ("slots", "heads", "checked", "config", "fit", "fresh", "links", "plan", "filled", "clean", "frame", "assigned",   # 사실의 이름(문서마다 · 쌍마다 · 워크플로우 전체 — ② §18-2)
         "tables", "tidy")   # 문서 하나(② §18-13): tables = 표 구조가 있음(문서 하나는 헤딩 그래프 heads 와 따로 센다) · tidy = 같은 템플릿의 줄을 대표 서식에 맞춤(조정)
PLACES = ("doc", "pair", "flow")
KINDS = ("auto", "pick", "hand")
ROLES = ("source", "target")   # 문서 역할 — 차례 = 원본 → 목적(app/workflow.py ROLES · app/custom_tasks.py ROLES 와 같다)


def _u(key, home, place, *, roles=(), kind="auto", change="none", paid="", needs=(), gives=(), spoils=(), redo=(), once=False, optional=False, via="", server=False, reads=(), each=False):
    """reads = 상태를 셀 때 그 줄의 문서 밖에서 재료를 읽어야 하는 문서 역할(구성 확정 · 구조 반영은 원본(구성의 기준)과 목적을 함께 본다) ·
    each = 원본 문서마다 한 덩이로 도는 줄(취합 — 잇달은 each 줄들을 원본 문서 하나에 끝까지 한 뒤 다음 원본 문서로: ② §18-4 「잇달은 pair 줄」 · §18-12 ⑥ 「원본 문서 하나를 끝내는 범위」)."""
    return dict(key=key, home=home, place=place, roles=tuple(roles), kind=kind, change=change, paid=paid, needs=tuple(needs), gives=tuple(gives), spoils=tuple(spoils), redo=tuple(redo),
                once=once, optional=optional, via=via, server=server, reads=tuple(reads), each=each)


# 두 틀이 같이 쓰는 단위 — 준비 · 문서 검토 · 구성 맞추기 · 문서 정리 · 사람이 하는 일
COMMON = {u["key"]: u for u in (
    _u("files", "", "flow", kind="pick", gives=("slots",), server=True),                                                    # 준비 — 실행기는 안 한다(칸이 비면 시작이 거절)
    _u("heads", "stage_review", "doc", roles=ROLES, change="store", needs=("slots",), gives=("heads",), server=True),       # 헤딩 · 표 분석(배경 일 · 목적 문서면 끝에 작성 지침 저장)
    _u("headsLlm", "stage_review", "doc", roles=ROLES, change="store", paid="doc", needs=("heads",), gives=("checked",), server=True),   # LLM 검증·보완(배경 일 — 못 쓰거나 건너뛰면 「건너뜀」)
    _u("configLoad", "stage_fit", "flow", kind="pick", change="store", optional=True, server=True),                         # 구성 불러오기(선택 — 실행기는 지나감)
    _u("config", "stage_fit", "flow", change="store", needs=("slots",), gives=("config",), server=True, reads=ROLES),        # 프로젝트 구성 확정(값 = 원본(구성의 기준) · 확정 = 목적 문서에서 — 화면 실행과 같다)
    # 문서마다의 줄은 원본 · 목적 문서 어느 쪽에도 놓는다(2026-11-20 사용자 「원본 문서는 왜 네 맘대로 빼냐? 목적문서랑 원본 문서도 분리해서 따로 따로 하게 해줘야지」 — 전에는 구성 반영 · 다시 문서 검토 · 작성요령 삭제가 목적 문서만이었다:
    # ② §18-2 「원본 문서에 놓는 줄」). 사실(fit · fresh · clean)은 문서마다다 — 원본 문서의 반영은 그 문서 자신의 값(own_values)을 제 구조에 맞춘다.
    _u("division", "stage_fit", "doc", roles=ROLES, change="doc", needs=("config",), gives=("fit",), spoils=("fresh",), server=True, reads=ROLES),   # 프로젝트 구성 반영(같은 검사 · 울타리)
    _u("reheads", "stage_fit", "doc", roles=ROLES, change="store", needs=("fit",), gives=("fresh", "heads"), server=True, reads=ROLES),   # 다시 문서 검토
    _u("reheadsLlm", "stage_fit", "doc", roles=ROLES, change="store", paid="doc", needs=("fresh",), gives=("checked",), server=True, reads=ROLES),   # 다시 문서 검토(LLM)
    _u("guide", "stage_clean", "doc", roles=ROLES, change="doc", needs=("filled",), gives=("clean",), server=True),   # 작성요령 삭제(먼저 있어야 할 것은 그 줄이 정의에 있을 때만 · 울타리)
    _u("hand", "hand", "doc", roles=ROLES, kind="hand", server=True),                                                       # 사람이 하는 일(여럿 놓을 수 있다 — ② §18-7 · 실행기는 「했음」 이 없으면 멈춘다)
)}
# 이관형 — 다른 양식 사이의 자리 연결 · 넣기(app/merge_api.py)
RELAY = {u["key"]: u for u in (
    _u("link", "stage_fill", "pair", change="store", needs=("heads", "fresh"), gives=("links",), server=True),
    _u("llm", "stage_fill", "pair", change="store", paid="stage", needs=("links",), once=True, optional=True, via="link", server=True),
    _u("plan", "stage_fill", "pair", needs=("links",), gives=("plan",), server=True),
    _u("gaps", "stage_fill", "pair", change="store", paid="stage", needs=("plan",), spoils=("plan",), once=True, optional=True, via="plan", server=True),       # 차례 = 빈 자리 검토 → 표 대응(고정 — ② §18-4 「무르기」)
    _u("tableMap", "stage_fill", "pair", change="store", paid="stage", needs=("plan",), spoils=("plan",), once=True, optional=True, via="plan", server=True),
    _u("apply", "stage_fill", "pair", change="doc", needs=("plan",), gives=("filled",), redo=("plan",), server=True),                                          # 울타리 · 낡은 계획(409)이면 한 번만 다시 계획
)}
# 취합형(걸음 5 — ② §18-13 갈래 「다」: app/merge_gather_api.py) — 원본 문서(기관 문서) 여럿 → 목적 문서(취합본) 하나 · 구성의 기준 = 목적 문서(준비 files · 프로젝트 구성 확정 config 는 같이 쓰는 단위가 base 를 따른다).
# 같이 쓰는 단위와 key 가 겹치는 것(division · hand · heads)은 가족의 것이 먼저다 — 뜻이 다르다: division = 구조가 이미 맞으면 확인만(adopt) · 간단 모드는 지울 것이 있으면 멈춤 /
# hand = 기관에 배포 · 회수(앱 밖의 일 — 「했음」 을 받지 않는다: 들어온 문서로 본다) / heads = 원본 문서 하나씩(열어 둘 수 있는 문서 수에 묶인다).
GATHER = {u["key"]: u for u in (
    _u("division", "stage_fit", "doc", roles=("target",), change="doc", needs=("config",), gives=("fit",), server=True, reads=("target",)),   # 프로젝트 구성 반영(울타리 · 같은 검사)
    _u("frame", "stage_fit", "doc", roles=("target",), change="store", needs=("fit",), gives=("frame",), server=True, reads=("target",)),     # 배포 기준본 만들기(낡은 기준본은 등록된 문서가 있으면 다시 만들지 않고 멈춘다)
    _u("hand", "", "doc", roles=("target",), kind="pick", server=True),                                                                     # 기관에 배포 · 회수(앱 밖 — 실행기는 지나간다)
    _u("part", "", "doc", roles=("source",), change="store", needs=("frame",), gives=("assigned",), server=True, each=True),               # 반영할 기관(사람이 정한 것은 안 건드린다 · 간단 모드에서 이번에 올린 미지정 문서만 자동 지정)
    _u("heads", "", "doc", roles=("source",), change="store", needs=("slots",), gives=("heads",), server=True, each=True),                 # 기관 문서의 헤딩 · 표 분석(그 문서 하나씩)
    _u("link", "", "pair", needs=("frame", "assigned", "heads"), gives=("links",), server=True, each=True),                                 # 자리 연결 · 기관 작성 내용 판정
    _u("llm", "", "pair", change="store", paid="stage", needs=("links",), once=True, optional=True, server=True, each=True),               # LLM 검토(한 번 · 실패해도 계속)
    _u("plan", "", "pair", needs=("links",), gives=("plan",), server=True, each=True),                                                      # 넣기 계획
    _u("apply", "", "pair", change="doc", needs=("plan",), gives=("filled",), redo=("plan",), server=True, each=True),                      # 내용 반영(울타리 · 낡은 계획이면 한 번만 다시 계획)
    _u("drop", "", "pair", kind="pick", change="doc", optional=True, server=True),                                                          # 끌어 넣기(사람이 한다)
)}
# 문서 하나(양식 표준화 plan_fit · 양식 맞추기 report_fit — 걸음 6: ② §18-13) — 그 문서가 곧 목적 문서다(등록부 줄의 on 이 빈 값 = 목적 문서: workflow_state.roles_on).
# 줄 key 가 다른 틀과 겹친다(plan · apply = 이관의 넣기 · heads · headsLlm = 공통의 문서 검토) — 가족의 것이 먼저다(unit). 이 가족은 등록부가 `units="single"` 로 적은 워크플로우만 쓴다(일반 편집 · 서식 복사는 단위가 없다).
SINGLE = {u["key"]: u for u in (
    _u("open", "", "flow", kind="pick", change="store", gives=("slots",), server=True),                                     # 준비 — 문서를 올리면 끝난 것(실행기는 지나간다)
    _u("read", "stage_fit", "doc", roles=("target",), change="store", optional=True, server=True, reads=("target",)),       # 구성 읽기(선택) — 입력 값이 없을 때만 문서에 적힌 값을 입력으로(확정하지 않는다)
    _u("load", "stage_fit", "flow", kind="pick", change="store", optional=True, server=True),                               # 구성 불러오기(선택 — 사람이 고른다)
    _u("values", "stage_fit", "flow", change="store", needs=("slots",), gives=("config",), server=True, reads=("target",)),  # 프로젝트 구성 확정 — **관문**: 사람이 확정한다(실행기는 저절로 확정하지 않고 확정 전이면 멈춘다 — 이관의 config 와 다르다)
    _u("review", "stage_fit", "doc", roles=("target",), kind="pick", change="store", optional=True, server=True),          # 구분 기준 LLM 검토(선택 · 유료 — 사람이 단추로만: 분석 상태의 규칙 「저절로 안 돎」)
    _u("plan", "stage_fit", "doc", roles=("target",), kind="pick", needs=("config",), via="apply", server=True, reads=("target",)),   # 변경 계획 보기 — 사람이 목록으로 본다(실행기의 계획은 반영 줄이 울타리 안에서 세운다)
    _u("apply", "stage_fit", "doc", roles=("target",), change="doc", needs=("config",), gives=("fit",), spoils=("fresh",), server=True, reads=("target",)),   # 구조 반영(울타리 안: 계획 → 같은 검사 → 반영 한 번)
    # 2단계 「헤딩 추출」 · 3단계 「표」(양식 표준화 — 갈래 「나」): 재료 = 분석 상태(unit_steps.analysis — 문서 이름 줄 · 진행표와 같은 값)
    _u("heads", "stage_review", "doc", roles=("target",), change="store", needs=("slots",), gives=("heads",), server=True),                        # 헤딩 · 템플릿 추출(스크립트 — 배경 일)
    _u("headsLlm", "stage_review", "doc", roles=("target",), change="store", paid="doc", needs=("heads",), gives=("checked",), server=True),       # 헤딩 LLM 판정 · 서식 계획(이어 돌리기 「llm」 — 거친 것은 건너뜀 · LLM 을 못 쓰면 **남김**: 이관의 「건너뜀」 과 다르다)
    _u("adjust", "stage_review", "doc", roles=("target",), change="doc", needs=("checked",), gives=("tidy",), server=True),                        # 조정 「모두 반영」(울타리 · 미판정이 있으면 반영하지 않고 남김 · 계획을 다시 받는 것은 유료 — 처리 함수가 승인을 본다)
    _u("tree", "stage_review", "doc", roles=("target",), kind="pick", change="doc", optional=True, server=True),                                    # 템플릿 관계 — 손으로 맞추기(선택 — 사람이 한다)
    _u("tables", "stage_review", "doc", roles=("target",), change="store", needs=("slots",), gives=("tables",), server=True),                       # 표 구조(스크립트 — 배경 일)
    _u("tablesLlm", "stage_review", "doc", roles=("target",), change="store", paid="doc", needs=("tables",), gives=("checked",), server=True),      # 표 판정(LLM) — 못 쓰거나 답을 못 받으면 스크립트 결과로 남김
    _u("tableTools", "stage_review", "doc", roles=("target",), kind="pick", change="doc", optional=True, server=True),                              # 표 점검 · 서식 맞추기(선택 — 사람이 한다)
)}
FAMILIES = {"common": COMMON, "relay": RELAY, "gather": GATHER, "single": SINGLE}


def hand_key(key):
    """사람이 하는 일의 줄 key 인가 — 정의에 여럿 놓을 수 있어 줄마다 key 가 `hand1` · `hand2` …(spec_워크플로우 ② §18-7 · §18-12 ⑦ — 단위는 하나)."""
    return isinstance(key, str) and key[:4] == "hand" and (key == "hand" or key[4:].isdigit())


def unit(key, family="relay"):
    """(가족, key) → 단위 | None — 가족의 것이 먼저, 없으면 두 틀이 같이 쓰는 것. 사람이 하는 일의 줄(`hand1` …)은 단위 `hand`."""
    if hand_key(key):
        key = "hand"
    return FAMILIES.get(family, {}).get(key) or COMMON.get(key)


SOURCE_FIT = ("division", "reheads", "reheadsLlm", "guide")   # 원본 문서에도 놓는 구조 · 정리 줄(같이 쓰는 단위 — ② §18-2 「원본 문서에 놓는 줄」)


def roles_in(u, family):
    """그 틀(가족)에서 그 단위를 놓을 수 있는 문서 역할 — 구조 · 정리 줄(SOURCE_FIT)을 원본 문서에 놓는 것은 이관형(relay)뿐이다: 취합의 원본 문서(기관 문서)는 바뀌지 않는다. 조립 검사 · 조립 화면의 고를 줄이 읽는다."""
    if family != "relay" and u["key"] in SOURCE_FIT and COMMON.get(u["key"]) is u:
        return tuple(r for r in u["roles"] if r != "source")
    return u["roles"]


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
_STATE.update({"config": lambda ctx: _config(ctx), "division": lambda ctx: _division(ctx), "reheads": lambda ctx: _reheads(ctx), "reheadsLlm": lambda ctx: _reheads_llm(ctx),
               "hand": lambda ctx: _hand(ctx)})   # 2단계 「구성 맞추기」(걸음 2 — 아래 절)


_STATE_BY = {}   # 가족 → {단위 key: 상태 함수} — key 가 다른 틀과 겹치는 가족의 것(문서 하나의 plan · apply …)이 먼저다


def state(key, ctx, family="relay"):
    """그 줄의 지금 상태 | None(서버가 아직 세지 않는 줄 — 화면이 센다: ② §17-5 의 `server: false`). 상태 함수는 단위처럼 가족의 것이 먼저다."""
    u = unit(key, family)
    if not (u and u["server"]):
        return None
    mine = FAMILIES.get(family, {}).get(u["key"]) is u   # 그 가족의 단위인가(두 틀이 같이 쓰는 것이 아니라)
    table = _STATE_BY.get(family) if mine else None   # 제 상태 표가 있는 가족의 단위는 그 표에서만(같은 key 의 다른 틀 식으로 새지 않게) · 없으면 같이 쓰는 표
    fn = (table if table is not None else _STATE).get(u["key"])   # 단위의 key 로(사람이 하는 일의 줄 hand1 … = 단위 hand) — 줄 key 는 ctx 에
    return fn({**ctx, "key": key}) if fn else None


# ---------------------------------------------------------------- 2단계 「구성 맞추기」 — 화면 app.js taskSteps 의 config · division · reheads · reheadsLlm 식을 그대로(spec_워크플로우 ② §17-10 걸음 2 「판정 식은 화면 것을 그대로」)
# ctx["pair"] = {역할: {title(문서 이름), id, facts}} — 그 묶음의 두 문서(facts.div = unit_steps.div_facts: 값은 서버가 정리한 꼴이라 화면 divCanon 의 견줌 = 사전 견줌).
# 서버의 비슷한 셈과 뜻이 다르다(시험이 못 박는다): 확정 유효 = 당해 차년도를 뺀 값이 확정한 값과 같음(화면 divConfirmValid — 서버 confirmed.valid 는 settings 전체의 해시) ·
# 두 문서의 값 견줌 = 정리한 꼴 전체의 단계 · 기관 · 사업기간 · 세부과제(화면 taskDivDiff — 서버 merge_pairs.values_diff 는 기관 이름 모음 + 주관).
def _no_cur(v):
    return {k: x for k, x in v.items() if k != "current"} if isinstance(v, dict) else None


def confirm_valid(values, confirmed):
    """확정이 지금 입력 값에 유효한가(화면 divConfirmValid — 당해 차년도는 안 견준다: 보고서마다 다를 수 있다)."""
    return bool(values and confirmed and confirmed.get("values") and _no_cur(confirmed["values"]) == _no_cur(values))


def div_diff(a, b):
    """기준 값 a(원본)와 b(목적)가 다른 곳 → 글 목록(같으면 []) — 당해 차년도는 안 견준다(화면 taskDivDiff)."""
    out, oa, ob = [], a.get("orgs") or {}, b.get("orgs") or {}
    if a.get("stages") != b.get("stages"):
        out.append(f"단계·차년도({'+'.join(str(x) for x in a.get('stages') or ())}년 ↔ {'+'.join(str(x) for x in b.get('stages') or ())}년)")
    if oa != ob:
        ja, jb = len(oa.get("joint") or ()), len(ob.get("joint") or ())
        out.append(f"공동 기관({ja}곳 ↔ {jb}곳)" if ja != jb else "기관 이름·구분")
    if (a.get("period") or None) != (b.get("period") or None):
        out.append("사업기간")
    if (a.get("subs") or []) != (b.get("subs") or []):
        out.append("세부과제")
    return out


def summary_text(v):
    """「1단계 · 전체 4년 · 기관 4곳」(화면 taskSteps 의 csum · sum)."""
    return f"{len(v.get('stages') or ())}단계 · 전체 {sum(int(x) for x in v.get('stages') or ())}년 · 기관 {len((v.get('orgs') or {}).get('joint') or ()) + 1}곳"


def _when(t):
    """확정 시각 — 화면 fmtWhen 과 같은 꼴(「오늘 13:47」 · 「11/14 13:47」 — 이 PC 의 시각)."""
    import time as _t
    if not t:
        return ""
    d, now = _t.localtime(t), _t.localtime()
    day = "오늘" if (d.tm_year, d.tm_yday) == (now.tm_year, now.tm_yday) else f"{d.tm_mon}/{d.tm_mday}"
    return f"{day} {d.tm_hour:02d}:{d.tm_min:02d}"


def _where(div):
    """확정이 놓이는 곳의 화면 이름(화면 divConfirmWhere) — 「프로젝트 「X」」 | 「이 문서」."""
    sh = (div or {}).get("sharing") or {}
    return f"프로젝트 「{sh['project']}」" if sh.get("shared") and sh.get("project") else "이 문서"


def _pair_of(ctx, role):
    d = (ctx.get("pair") or {}).get(role)
    return d, ((d or {}).get("facts") or None)


def basis_values(div):
    """원본(구성의 기준) 문서의 값 → (값 | None, 문서에서 읽은 값인가) — 반영 값이 먼저, 없으면 입력 값, 둘 다 없으면 문서에 적힌 값(화면 taskFlowLoad 의 기준 문서와 같은 차례)."""
    if not div:
        return None, False
    v = ((div.get("applied") or {}).get("values")) or div.get("input")
    return (v, False) if v else (div.get("read"), bool(div.get("read")))


def target_values(div):
    """목적 문서의 값 — 입력 값이 먼저, 없으면 반영 값(화면 taskFlowLoad 의 견줄 문서와 같은 차례)."""
    if not div:
        return None
    return div.get("input") or (div.get("applied") or {}).get("values")


def _config(ctx):
    """프로젝트 구성 확정 — 목적 문서의 입력 값이 확정한 값과 같으면 끝남(화면 실행이 목적 문서에서 확정한다 · 공유 중이면 두 문서가 같은 확정)."""
    (s, _sf), (t, tf) = _pair_of(ctx, "source"), _pair_of(ctx, "target")
    if not ctx.get("ready") or not t:
        return {"st": "todo", "text": ""}
    div = (tf or {}).get("div")
    if tf is None or div is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    where, v, cf = _where(div), div.get("input"), div.get("confirmed")
    if confirm_valid(v, cf):
        return {"st": "done", "text": f"{where}에 확정함({_when(cf.get('at'))}) — {summary_text(v)}"}
    src = ((t if ctx.get("base") == "target" else s) or {}).get("title") or "원본 문서"   # 구성의 기준 문서(워크플로우의 base — 이관 = 원본 · 취합 · 문서 하나 = 목적 문서 자신)
    if not v:
        return {"st": "todo", "text": f"프로젝트 구성(단계·차년도·기관)이 없습니다 — {src}에서 추출하거나 아래 「프로젝트 구성 불러오기」 · 입력 칸에서 정하세요"}
    if cf:
        return {"st": "todo", "text": f"확정한 뒤 값이 바뀌었습니다 — 다시 저장하거나 확정본으로 되돌리세요(지금: {summary_text(v)})"}
    return {"st": "todo", "text": f"{summary_text(v)} — 확인한 뒤 {where}에 저장(확정)하세요"}


def own_values(div):
    """그 문서 자신의 값 → (값 | None, 문서에서 읽은 값인가) — 입력 값이 먼저, 없으면 반영 값, 둘 다 없으면 문서에 적힌 값. **원본 문서에 구조를 반영할 때**의 값이다(② §18-2 「원본 문서에 놓는 줄」):
    제 구조를 제 값에 맞춘다. basis_values(반영 값이 먼저)는 남의 기준이 될 때의 값이다 — 지금 구조가 곧 기준이라."""
    if not div:
        return None, False
    v = div.get("input") or ((div.get("applied") or {}).get("values"))
    return (v, False) if v else (div.get("read"), bool(div.get("read")))


def basis_of(sf):
    """목적 문서가 맞출 기준 값(원본 문서의 재료 sf 에서) → (값 | None, 문서에서 읽은 값인가). 보통은 basis_values(원본 문서의 지금 구조 = 반영 값이 먼저) ·
    **이 정의가 원본 문서의 구조도 반영하면**(재료의 `selfFit` — 실행기가 정의에서 세어 얹는다: 「프로젝트 구성 반영」 을 원본 문서에도 놓음) own_values(원본의 제 값 = 입력이 먼저)다 —
    두 문서가 같은 값(확정한 프로젝트 구성)으로 가므로 **차례와 무관**하다(2026-11-20 사용자 「프로젝트 구성을 완료하고 문서 검토하고 다른문서 프로젝트 구성할 수도 있잖아」 — 목적 문서를 먼저 해도 원본의 옛 구조에 맞추지 않는다)."""
    div = (sf or {}).get("div")
    return own_values(div) if (sf or {}).get("selfFit") else basis_values(div)


def _line_roles(ctx):
    """그 줄이 닿는 문서 역할들(차례 = 원본 → 목적) — 줄의 문서가 실려 있으면(workflow_state.view · 실행기의 줄 상태) 그 문서들, 없으면 목적 문서(줄을 모르고 세는 옛 부름 — 전과 같은 값)."""
    got = {d.get("role") for d in ctx.get("docs") or ()}
    return tuple(r for r in ROLES if r in got) or ("target",)


def _per(ctx, one):
    """문서마다의 줄(구성 반영 · 다시 문서 검토 · 작성요령 삭제)의 상태 — 그 줄이 닿는 문서마다 센 것(one(ctx, 역할))을 줄 하나로 모은다. 문서가 하나면 그 문서의 것 그대로(목적 문서만의 줄 = 전과 같은 값).
    둘이면 끝남 = 두 문서가 다 끝남 · 글은 문서 차례(원본 → 목적)로 잇고 · per[{doc, role, st, text}] 에 문서마다의 몫 · 유료로 부를 문서(paid)는 합친다."""
    got = [(r, one(ctx, r)) for r in _line_roles(ctx)]
    if len(got) == 1:
        return got[0][1]
    sts = [g["st"] for _, g in got]
    st = "blocked" if "blocked" in sts else "done" if all(x == "done" for x in sts) else next((x for x in ("busy", "failed") if x in sts), "todo")
    out = {"st": st, "text": " · ".join(dict.fromkeys(g["text"] for _, g in got if g.get("text"))),
           "per": [{"doc": ((ctx.get("pair") or {}).get(r) or {}).get("id"), "role": r, "st": g["st"], "skipped": bool(g.get("skipped")), "text": g.get("text") or ""} for r, g in got]}
    out["skipped"] = st == "done" and all(g.get("skipped") for _, g in got)
    if any("paid" in g for _, g in got):
        out["paid"] = [d for _, g in got for d in g.get("paid") or ()]
    if any("fresh" in g for _, g in got):   # 다시 문서 검토 — 두 문서가 다 새 분석 · 어느 하나라도 옛 분석을 그대로 둠
        out.update(fresh=all(g.get("fresh") for _, g in got), keep=any(g.get("keep") for _, g in got))
    return out


def _division(ctx):
    """프로젝트 구성 반영(줄) — 그 줄이 닿는 문서마다(_division_of)."""
    return _per(ctx, _division_of)


def _division_src(ctx):
    """원본 문서의 프로젝트 구성 반영 — 그 문서 자신의 값(own_values)이 확정한 프로젝트 구성과 같고(당해 차년도 빼고) 제 구조에 반영됐으면 끝남. 목적 문서의 값 · 구조는 보지 않는다(문서마다 따로)."""
    (s, sf), (t, tf) = _pair_of(ctx, "source"), _pair_of(ctx, "target")
    if not ctx.get("ready") or not s or not t or _config(ctx)["st"] != "done":
        return {"st": "todo", "text": ""}
    A, B = (sf or {}).get("div"), (tf or {}).get("div")
    if A is None or B is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    S = s["title"]
    a, read = own_values(A)
    if not a:
        return {"st": "todo", "text": f"{S}에 프로젝트 구성 값이 없습니다 — {S}에서 값을 넣거나 문서에서 읽으세요"}
    total = summary_text(a)
    if read:
        return {"st": "todo", "text": f"{S}에 저장된 값이 없어 문서에서 읽었습니다({total}) — 맞으면 {S}의 값으로 저장하세요(틀리면 {S}를 열어 고칩니다)"}
    if not confirm_valid(a, B.get("confirmed")):
        return {"st": "todo", "text": f"{S}의 값({total})이 확정한 프로젝트 구성과 다릅니다 — {S}의 값을 맞추거나 「프로젝트 구성 확정」 을 다시 하세요"}
    if not (A.get("applied") and A["applied"].get("values") == a):
        return {"st": "todo", "text": f"{S}에 아직 반영 전 — {total}"}
    return {"st": "done", "text": f"{S}에 반영됨 — {total}"}


def _division_of(ctx, role="target"):
    """프로젝트 구성 반영(문서 하나의 몫) — 목적 문서: 두 문서의 값이 같고(당해 차년도 빼고) 목적 문서의 지금 값이 반영됐으면 끝남(② §18-12 ② 「fit」) · 원본 문서: _division_src.
    목적 문서가 맞출 기준 값 = basis_of(원본 문서의 재료) — 이 정의가 원본 문서의 구조도 반영하면(재료의 selfFit) 원본의 「제 값」 이라 두 문서의 차례와 무관하다(목적 문서를 먼저 해도 같은 값)."""
    if role == "source":
        return _division_src(ctx)
    (s, sf), (t, tf) = _pair_of(ctx, "source"), _pair_of(ctx, "target")
    if not ctx.get("ready") or not s or not t or _config(ctx)["st"] != "done":
        return {"st": "todo", "text": ""}
    A, B = (sf or {}).get("div"), (tf or {}).get("div")
    if A is None or B is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    S, D = s["title"], t["title"]
    a, read = basis_of(sf)
    if not a:
        return {"st": "todo", "text": f"{S}(기준)에 프로젝트 구성 값이 없습니다 — {S}에서 값을 넣거나 문서에서 읽으세요"}
    b = target_values(B)
    diff = div_diff(a, b) if b else [f"{D}에 값 없음"]
    total = summary_text(a)
    ya, yb = a.get("current") or 1, (b or {}).get("current") or 0
    year = f" · 당해 차년도는 {D} {yb}차년도({S} {ya}차년도)" if yb and ya != yb else ""
    if read:
        return {"st": "todo", "text": f"{S}에 저장된 값이 없어 문서에서 읽었습니다({total}) — 맞으면 {S}의 값으로 저장하세요(틀리면 {S}를 열어 고칩니다)"}
    if diff:
        return {"st": "todo", "text": f"{S}({total})와 다름 — {' · '.join(diff)}"}
    if not (B.get("applied") and B["applied"].get("values") == b):
        return {"st": "todo", "text": f"값은 {S}와 같음({total}) · {D}에 아직 반영 전{year}"}
    return {"st": "done", "text": f"{S}와 같음 · {D}에 반영됨 — {total}{year}"}


def heads_stale(tf):
    """목적 문서의 분석이 마지막 구조 반영 전 것인가(스크립트 결과든 LLM 결과든 — 화면 taskHeadsStale)."""
    h, rev = (tf or {}).get("heads") or {}, (((tf or {}).get("div") or {}).get("applied") or {}).get("rev")
    parts = [r for ok, r in ((h.get("s2"), h.get("rev2")), (h.get("s3"), h.get("rev3"))) if ok]
    return rev is not None and any((r if r is not None else rev) < rev for r in parts)


def heads_kept(tf):
    """구조 반영 전의 분석인데 LLM 을 돌린 결과(화면 taskHeadsKept — 다시 안 돌리면 늘어난 절 · 표를 못 이었을 수 있다)."""
    return heads_stale(tf) and bool(((tf or {}).get("heads") or {}).get("asked"))


def _reheads(ctx):
    """다시 문서 검토(줄) — 그 줄이 닿는 문서마다(_reheads_of)."""
    return _per(ctx, _reheads_of)


def _reheads_of(ctx, role="target"):
    """다시 문서 검토(문서 하나의 몫) — 그 문서의 구조 반영이 끝났고 그 문서의 분석이 그 반영 뒤의 것이면 끝남 · 반영 전 분석이 LLM 결과이고 LLM 을 쓸 수 없으면 그대로 두고 끝남(keep)."""
    t, tf = _pair_of(ctx, role)
    if _division_of(ctx, role)["st"] != "done" or tf is None:
        return {"st": "todo", "text": ""}
    D, hr = t["title"], _got(tf)
    stale = heads_stale(tf) if hr else True
    kept = hr and heads_kept(tf)
    keep = kept and ctx.get("llm") is False
    J = _job(tf)
    run = J.get("status") == "running" and not J.get("chain")
    fresh = hr and not stale
    done = fresh or keep
    text = (f"{D} 헤딩·표 분석 중…" if run else f"구조를 맞춘 문서({D})의 헤딩·표 분석이 없습니다 — 다시 분석(스크립트)" if not hr
            else "구조 반영 전 분석(LLM 판정을 거친 결과 — LLM 을 쓸 수 없어 그대로 둠 · 늘어난 절·표는 못 이을 수 있음)" if keep
            else f"구조를 맞춘 문서({D})의 분석이 구조 반영 전 것입니다 — 늘어난 절·표가 분석에 없습니다(다시 분석 — 스크립트{' · LLM 판정은 다음 줄에서 다시 받습니다' if kept else ''})" if stale
            else "헤딩 그래프·표 구조가 구조 반영 뒤의 것입니다")
    return {"st": "done" if done else "busy" if run else "todo", "skipped": False, "text": text, "fresh": fresh, "keep": keep}


def _reheads_llm(ctx):
    """다시 문서 검토(LLM)(줄) — 그 줄이 닿는 문서마다(_reheads_llm_of)."""
    return _per(ctx, _reheads_llm_of)


def _reheads_llm_of(ctx, role="target"):
    """다시 문서 검토(LLM)(문서 하나의 몫) — 화면 llmStep(reheadsLlm): 앞 줄이 끝나야 셈 · 끝남 = 거침 | LLM 을 못 씀 | 건너뜀. 유료로 부를 문서 = 끝나지 않았고 건너뛰지 않은 그 문서(앞 줄이 아직이어도 — 화면 taskPaidDocs)."""
    t, tf = _pair_of(ctx, role)
    if not t or not ctx.get("ready"):   # 칸이 비면 유료 대상도 없다(화면 taskPaidDocs — 두 칸이 차야 센다)
        return {"st": "todo", "text": ""}
    paid = [] if ctx.get("llm") is False or t["id"] in (ctx.get("skip") or ()) else [t["id"]]
    if _reheads_of(ctx, role)["st"] != "done" or tf is None:
        return {"st": "todo", "text": "", "paid": paid}
    got = _llm_one({"facts": tf, "title": t["title"], "role": role}, ctx)
    return {"st": got["st"], "skipped": got.get("skipped", False), "text": got["text"], "paid": [] if got["st"] == "done" else paid}


def _hand(ctx):
    """사람이 하는 일(`hand1` …) — 끝남 = 그 줄이 지금 판으로 「했음」 으로 적혀 있음(목적 문서의 확인 기록 — 재료 `hands{줄 key: 참}`: 실행기의 MATERIALS 가 문 hand_done 으로 채운다)."""
    t, tf = _pair_of(ctx, "target")
    if not ctx.get("ready") or not t:
        return {"st": "todo", "text": ""}
    done = bool(((tf or {}).get("hands") or {}).get(ctx.get("key")))
    return {"st": "done" if done else "todo", "text": "사람이 확인함(「했음」)" if done else "사람이 할 일 — 마친 뒤 그 줄의 「했음」 을 누릅니다(「한 번에 진행」 은 여기서 멈춥니다)"}


# ---------------------------------------------------------------- 3단계 「내용 넣기」 · 4단계 「문서 정리」(걸음 3 — ② §18-2 「3 · 4단계 단위의 글」) — 화면 app.js taskSteps 의 link · plan · apply · guide 식과 글을 그대로
# 재료 = 목적 문서 facts 의 `fill`(unit_steps.fill_facts — merge_api.fill_summary 꼴 + 실행기가 얹은 stages{단계 모듈: {id, no, name}}). 글 함수(links_* · fill_* · cleanup_text)는 실행기의 끝 글도 쓴다(화면 실행의 글 그대로).
LINK_STATUS = (("paired", "연결됨"), ("ambiguous", "확인 필요"), ("toOnly", "후보 없음"), ("fromOnly", "원본에만"))
LINK_REASON = {"noHeadings": "헤딩·표 분석 없음", "noValues": "프로젝트 구성 값 없음", "notApplied": "프로젝트 구성 반영 전", "unsupportedForm": "hwpx 문서가 아님", "valuesDiffer": "프로젝트 구성 값이 사업계획서와 다름"}


def nf(v):
    """화면 nf — 수의 자리 점(ko-KR) · 없으면 「–」."""
    return "–" if v is None else f"{int(v):,}"


def _fx(L):
    return (L or {}).get("fixed") or {}


def links_fixed_err(L):
    return _fx(L).get("error") or ""


def links_fixed_n(L):
    return _fx(L).get("todo") or 0


def links_open_tables(L):
    return (_fx(L).get("counts") or {}).get("tablesOpen") or 0


def links_map_open(L):
    return (_fx(L).get("counts") or {}).get("mapOpen") or 0


def links_bad(L):
    """연결 목록이 없거나 · 못 읽었거나 · 막는 까닭이 있다(화면 taskRunMap 의 linkBad)."""
    return not L or bool(L.get("error")) or not L.get("counts") or not L.get("from") or not L.get("to") or bool(L["from"].get("reasons")) or bool(L["to"].get("reasons"))


def links_none(L):
    """정상 0건(화면 linksNone) — 서버가 전제를 확인하고 낸 연결 목록에 넣을 자리(이어진 묶음 · 같은 이름 자리)가 하나도 없다. 막힌 까닭 · 같은 이름 자리의 판정 실패는 0건이 아니다."""
    return not links_bad(L) and not L["counts"].get("paired") and not links_fixed_n(L) and not links_fixed_err(L)


def links_count_text(L):
    """「연결됨 a · 확인 필요 b · 후보 없음 c · 원본에만 d · 같은 이름 자리 n · 같은 표 T(LLM t)」(화면 linksCountText)."""
    c = (_fx(L).get("counts") or {})
    same = ""
    if c.get("tables"):
        same = f" · 같은 표 {c['tables']}" + (f"(LLM {c['tablesLlm']})" if c.get("tablesLlm") else "")
    fixed = (" · 같은 이름 자리 " + ("못 셈" if links_fixed_err(L) else str(links_fixed_n(L)))) if L.get("fixed") else ""
    return " · ".join(f"{name} {L['counts'].get(k) or 0}" for k, name in LINK_STATUS) + fixed + same


def links_llm_ok(L):
    """자리 연결 LLM 검토를 거쳤나 — 검토 기록이 있고, 부른 단위가 있으면 그 가운데 하나라도 답을 받았다(모든 단위가 실패한 기록은 거친 것이 아니다: astra 결과 검토)."""
    m = (L or {}).get("llm")
    if not m:
        return False
    called = [u for u in m.get("units") or () if u.get("call") is not None]
    return not called or any(not (u.get("call") or {}).get("error") for u in called)


def links_llm_text(L):
    """「 · LLM 검토함(n단위 — 일부 실패 · 표 a개 이음 · b개 비움 · 워크플로우 프롬프트 함께 보냄)」 | ""(화면 linksLlmText)."""
    m = (L or {}).get("llm")
    if not m:
        return ""
    units = [u for u in m.get("units") or () if u.get("call") is not None]   # 화면의 u.call 참 = 사전이 있음(빈 사전도)
    t = m.get("tables") or {}
    fail = " — 일부 실패" if any((u.get("call") or {}).get("error") for u in units) else ""
    tabs = f" · 표 {t.get('paired') or 0}개 이음 · {t.get('none') or 0}개 비움" if t.get("paired") or t.get("none") else ""
    job = " · 워크플로우 프롬프트 함께 보냄" if m.get("job") else ""
    return f" · LLM 검토함({len(units)}단위{fail}{tabs}{job})"


def links_why(L, S, D):
    """연결 목록을 낼 수 없는 까닭 글(화면 taskSteps 의 ② 「연결 목록을 낼 수 없습니다 — …」) | "" — 못 읽었으면 「연결 목록을 읽지 못했습니다: …」."""
    if not L or L.get("error") or not L.get("counts"):
        return f"연결 목록을 읽지 못했습니다: {(L or {}).get('error') or '응답이 없음'}"
    why = [f"{name}: {', '.join(LINK_REASON.get(r, r) for r in side['reasons']) if side else '같은 프로젝트에서 찾지 못함'}" for side, name in ((L.get("from"), S), (L.get("to"), D)) if not side or side.get("reasons")]
    return f"연결 목록을 낼 수 없습니다 — {' · '.join(why)}" if why else ""


def _fill_fixed_text(c):
    if not c:
        return ""
    pics = f"(그림 {c['pictures']})" if c.get("pictures") else ""
    flow = f" · 표 쪽 나눔 맞춤 {c['flow']}" if c.get("flow") else ""
    return f" · 같은 이름 자리 — 칸 {c.get('cells') or 0} · 라벨 내용 {c.get('labels') or 0}{pics}{flow}"


def fill_count_text(p):
    """넣기 계획의 수(화면 fillCountText) — 「본문 n항목 · 표 칸 c · 행 추가 r · 같은 이름 자리 … · 표 대응 … · 빈 자리 …」(+ 「 — 넣을 것 없음」)."""
    b, t = ((p.get("body") or {}).get("counts") or {}), ((p.get("tables") or {}).get("counts") or {})
    m, g = ((p.get("maps") or {}).get("counts") or {}), ((p.get("gaps") or {}).get("counts") or {})
    mp = (f" · 표 대응 — 표 {m['tables']} · 칸 {m.get('cells') or 0}" + (f" · 일정 선 {m['lines']}" if m.get("lines") else "") + (f" · 행 추가 {m['rows']}" if m.get("rows") else "")) if m.get("tables") else ""
    gp = f" · 빈 자리 — 칸 {g.get('cells') or 0} · 줄 {g.get('lines') or 0}" if g.get("cells") or g.get("lines") else ""
    return (f"본문 {b.get('todo') or 0}항목 · 표 칸 {t.get('cells') or 0} · 행 추가 {t.get('rows') or 0}" + _fill_fixed_text((p.get("fixed") or {}).get("counts")) + mp + gp
            + ("" if p.get("todo") else " — 넣을 것 없음"))


def fill_done_text(r):
    """반영한 수(화면 fillDoneText) — 「본문 블록 b · 표 칸 c · 행 추가 r · 템플릿 변환 n줄 …」."""
    g = lambda k: r.get(k) or {}  # noqa: E731
    body, tables, conv, fixed, maps, gaps = g("body"), g("tables"), g("converted"), g("fixed"), g("maps"), g("gaps")
    shaped = (tables.get("shaped") or 0) + (fixed.get("shaped") or 0) + (maps.get("shaped") or 0)
    fitted = (fixed.get("fitted") or 0) + (body.get("fitted") or 0)
    skipped = (tables.get("skipped") or 0) + (fixed.get("skipped") or 0)
    return (f"본문 블록 {body.get('blocks') or 0} · 표 칸 {tables.get('filled') or 0} · 행 추가 {tables.get('rowsAdded') or 0} · 템플릿 변환 {conv.get('converted') or 0}줄"
            + (f" · 넘친 레벨 {conv['over']}줄" if conv.get("over") else "")
            + (f" · 같은 이름 자리 — 칸 {fixed.get('filled') or 0} · 라벨 내용 {(fixed.get('labels') or {}).get('items') or 0}(블록 {(fixed.get('labels') or {}).get('blocks') or 0})" if r.get("fixed") else "")
            + ((f" · 표 대응 — 칸 {maps.get('filled') or 0}" + (f" · 일정 선 {maps['lines']}" if maps.get("lines") else "") + (f" · 행 추가 {maps['rowsAdded']}" if maps.get("rowsAdded") else ""))
               if maps.get("filled") or maps.get("lines") or maps.get("rowsAdded") else "")
            + (f" · 빈 자리 — 칸 {gaps.get('cells') or 0} · 줄 {gaps.get('lines') or 0}" if gaps.get("cells") or gaps.get("lines") else "")
            + (f" · 칸 서식 맞춤 {shaped}칸" if shaped else "")
            + (f" · 표 쪽 나눔 맞춤 {fixed['flowed']}" if fixed.get("flowed") else "") + (f" · 그림 폭 맞춤 {fitted}" if fitted else "")
            + (f" · 반영 때 건너뜀 {skipped}(계획 뒤 글이 생긴 칸 등)" if skipped else "")
            + (f" · 못 옮긴 것 {len(r['dropped'])}(쪽 설정 등)" if r.get("dropped") else ""))


def fill_gap_note(res):
    """빈 자리 검토의 끝 글 몫(화면 fillGapNote — 앞의 「 · 」 없이) — 「빈 자리 검토 찾음/모음」 | 「빈 자리 검토는 못 함(그 자리는 비워 둠)」."""
    if not res:
        return "빈 자리 검토는 못 함(그 자리는 비워 둠)"
    t, s, f = res.get("tables") or {}, res.get("slots") or {}, res.get("found") or {}
    return f"빈 자리 검토 {(t.get('paired') or 0) + (s.get('filled') or 0)}/{(f.get('tables') or 0) + (f.get('slots') or 0)}"


def fill_map_note(res):
    """표 대응의 끝 글 몫(화면 taskRunMap 의 mapNote — 앞의 「 · 」 없이)."""
    return f"표 대응 {res.get('mapped') or 0}/{len(res.get('tables') or ())}" if res else "표 대응은 못 함(그 표는 비워 둠)"


def cleanup_text(n, patterns, done=False):
    """지울 · 지운 안내의 수(화면 taskCleanupText) — 패턴 이름 차례로 「작성 요령 표 3 · ※ 안내 12」(+ 「을(를) 지웠습니다」)."""
    return " · ".join(f"{p['name']} {nf(n[p['key']])}" for p in patterns or () if (n or {}).get(p["key"])) + ("을(를) 지웠습니다" if done else "")


def _fill(ctx):
    """(원본 {title, id, facts} | None, 목적 …, 목적 문서의 넣기 재료 | None)."""
    pair = ctx.get("pair") or {}
    s, t = pair.get("source"), pair.get("target")
    return s, t, ((t or {}).get("facts") or {}).get("fill")


def _sn(F, module, fallback):
    """묶음을 가리키는 글(화면 taskStageName — 그 묶음이 있으면 「N단계 「이름」」, 없으면 「「이름」」)."""
    g = ((F or {}).get("stages") or {}).get(module)
    return f"{g['no']} 「{g['name']}」" if g else f"「{fallback}」"


def _no_targets(F):
    """정상 0건 — 목적 문서의 분석이 구조 반영 전 스크립트 결과가 아니고(그러면 실행이 다시 분석한 뒤 판정한다) 연결 목록이 linksNone(화면 taskSteps 의 noTargets)."""
    return bool(F) and not (F.get("heads") or {}).get("old") and links_none(F.get("links"))


def fill_done(F):
    """「내용 넣기」 가 끝났나(넣기 계획 · 내용 반영 · 「문서 정리」 의 앞 조건 — ② §18-12 ②) — 넣을 것이 있는 지금 계획이 없고, 반영 표식 · 지난 반영 기록 · 정상 0건 · 지금 계획의 넣을 것 0 가운데 하나."""
    if not F:
        return False
    p = F.get("plan")
    if p and p.get("fresh") and p.get("todo"):
        return False
    return bool(F.get("filled") or _no_targets(F) or plan_final_zero(p))   # 지난 반영의 수(kept.applied)만으로는 끝이 아니다 — 원본에 묶인 반영 표식이나 마지막 0건이어야(astra 결과 검토: 「문서 정리」 의 허가)


def plan_final_zero(p):
    """지금 계획이 「마지막 0건」 인가 — 반영할 수 있는 계획의 넣을 것이 0 이고 빈 자리 · 못 맞춘 표가 열려 있지 않다(열려 있으면 그 선택 줄을 먼저 하고 마지막 계획으로 정한다 — ② §18-12 ②)."""
    if not (p and p.get("fresh")) or p.get("todo"):
        return False
    return not (((p.get("gaps") or {}).get("counts") or {}).get("open") or ((p.get("maps") or {}).get("counts") or {}).get("open"))


def _need_both(ctx):
    """두 문서와 넣기 재료 → (원본, 목적, 재료, 막힘 상태 | None)."""
    s, t, F = _fill(ctx)
    if not ctx.get("ready") or not s or not t:
        return s, t, F, {"st": "todo", "text": ""}
    if s.get("facts") is None or t.get("facts") is None or F is None:
        return s, t, F, {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    return s, t, F, None


def _link(ctx):
    """② 자리 연결 — 끝남 = 확인 필요가 없거나 LLM 검토를 한 번 함(LLM 을 쓸 수 없으면 「건너뜀」 — 남은 자리는 비워 둔다)."""
    s, t, F, bad = _need_both(ctx)
    if bad:
        return bad
    S, D, hp, hr, L = s["title"], t["title"], _got(s["facts"]), _got(t["facts"]), F.get("links")
    word = lambda x: "있음" if x else "없음"  # noqa: E731
    if not (hp and hr):
        rv = (F.get("stages") or {}).get("stage_review")
        return {"st": "todo", "text": (f"먼저 {_sn(F, 'stage_review', '문서 검토')} 의 헤딩·표 분석" if rv else "헤딩·표 분석이 없습니다(이 워크플로우에는 「문서 검토」 가 없어 「한 번에 진행」 이 스크립트로 분석합니다)")
                + f" — 헤딩 그래프·표 구조: {S} {word(hp)} · {D} {word(hr)}"}
    why = links_why(L, S, D)
    if why:
        return {"st": "blocked", "text": why}
    c, llm = L["counts"], links_llm_ok(L)
    off = ctx.get("llm") is False or "llm" not in (F.get("lines") or ("llm",))   # LLM 을 쓸 수 없거나 · 정의에 LLM 검토 줄이 없다(조립 — 그 줄이 없으면 확인 필요는 비워 두고 끝: astra 결과 검토)
    amb, open_t = c.get("ambiguous") or 0, links_open_tables(L)
    hint = (" — 다음: 「LLM 검토」 로 확인 필요한 자리를 정리합니다" if amb and not llm and not off
            else f" — LLM 을 쓸 수 없어 확인 필요 {amb}곳은 넣지 않고 비워 둡니다(고르려면 「연결 목록」)" if amb and not llm   # 화면 taskSteps 와 같은 글
            else f" — 남은 확인 필요 {amb}곳은 넣지 않고 비워 둡니다(각 기관이 작성 · 고르려면 「연결 목록」)" if amb
            else f" — 같은 표인지 못 정한 표 {open_t}개(「LLM 검토」 가 기관·차년도를 가려 봅니다)" if open_t and not llm and not off else "")
    old = f" · 구조 반영으로 늘어난 절·표는 헤딩·표 분석에 아직 없습니다({_sn(F, 'stage_fit', '구성 맞추기') + ' 의 ' if (F.get('stages') or {}).get('stage_fit') else ''}「다시 문서 검토」)" if (F.get("heads") or {}).get("old") else ""
    done = not amb or llm or off
    return {"st": "done" if done else "todo", "skipped": done and bool(amb) and not llm, "text": links_count_text(L) + links_llm_text(L) + hint + old}


def _link_llm(ctx):
    """자리 연결 LLM 검토(선택 — 셈에 안 듦) — 할 일 = 확인 필요나 못 정한 표가 있고 아직 검토 전 · LLM 을 쓸 수 없으면 「건너뜀」."""
    s, t, F, bad = _need_both(ctx)
    if bad:
        return bad
    L = F.get("links")
    if links_bad(L) or not (_got(s["facts"]) and _got(t["facts"])):
        return {"st": "todo", "text": ""}
    amb, open_t = L["counts"].get("ambiguous") or 0, links_open_tables(L)
    if links_llm_ok(L):
        return {"st": "done", "text": links_llm_text(L).removeprefix(" · ")}
    if not (amb or open_t):
        return {"st": "done", "skipped": True, "text": "확인 필요한 자리 · 못 정한 표가 없습니다"}
    if ctx.get("llm") is False:
        return {"st": "done", "skipped": True, "text": "LLM 을 쓸 수 없어 건너뜁니다 — 확인 필요한 자리는 비워 둡니다"}
    return {"st": "todo", "text": f"확인 필요 {amb}곳 · 못 정한 표 {open_t}개를 LLM 이 검토합니다 — 유료 · 수십 초"}


def _plan(ctx):
    """③ 넣기 계획 — 끝남 = 반영할 수 있는 지금 계획 · 「내용 넣기」 의 끝(fill_done) · 정상 0건(「대상 없음」)."""
    s, t, F, bad = _need_both(ctx)
    if bad:
        return bad
    L, p, none = F.get("links"), F.get("plan"), _no_targets(F)
    if none:
        return {"st": "done", "skipped": True, "text": "이어진 자리가 없어 계획할 내용이 없습니다"}
    ok = not links_bad(L) and bool(L["counts"].get("paired") or links_fixed_n(L) or links_fixed_err(L))
    fresh = bool(p and p.get("fresh"))
    applied = ((L or {}).get("kept") or {}).get("applied") or 0
    prior = not fresh and bool(applied or F.get("filled"))
    done = fresh or fill_done(F)
    if not ok:
        return {"st": "done" if done else "todo", "text": ""}
    mp = (((p or {}).get("maps") or {}).get("counts") or {}).get("open") if fresh else links_map_open(L)
    gp = (((p or {}).get("gaps") or {}).get("counts") or {}).get("open") if fresh else 0
    text = (fill_count_text(p) if fresh else "계획을 세운 뒤 문서나 연결이 바뀌었습니다 — 「넣기 계획 다시」" if p
            else f"지난 반영으로 넣은 자리 {applied}곳 — 더 넣을 것은 「넣기 계획 다시」 가 셉니다" if prior and applied
            else "지난 반영으로 넣었습니다 — 더 넣을 것은 「넣기 계획 다시」 가 셉니다" if prior else "이어진 자리에 넣을 본문·표 칸·행을 셉니다 — 문서는 안 바뀝니다")
    text += (f" · 칸을 못 맞춘 표 {mp}개 — 「표 대응(LLM)」 이 행·열을 맞춥니다" if mp else "") + (f" · 아직 빈 자리 {gp}곳 — 「빈 자리 검토(LLM)」 가 사업계획서에서 찾습니다" if gp else "")
    return {"st": "done" if done else "todo", "text": text}


def _opt_llm(ctx, what, open_of, word):
    """빈 자리 검토 · 표 대응(선택) — 지금 계획에 열린 자리가 있으면 할 일 · 없거나 LLM 을 못 쓰면 끝남(「건너뜀」)."""
    s, t, F, bad = _need_both(ctx)
    if bad:
        return bad
    p = F.get("plan") if (F.get("plan") or {}).get("fresh") else None
    n = open_of(p, F.get("links")) or 0
    if not n:
        return {"st": "done", "skipped": True, "text": ""}
    if ctx.get("llm") is False:
        return {"st": "done", "skipped": True, "text": f"LLM 을 쓸 수 없어 건너뜁니다 — {word} {n}{'개' if what == 'tableMap' else '곳'}은 비워 둡니다"}
    return {"st": "todo", "text": f"{word} {n}{'개' if what == 'tableMap' else '곳'} — LLM 이 {'행·열을 맞춥니다' if what == 'tableMap' else '사업계획서에서 찾습니다'}(유료)"}


def _gaps(ctx):
    return _opt_llm(ctx, "gaps", lambda p, L: (((p or {}).get("gaps") or {}).get("counts") or {}).get("open"), "아직 빈 자리")


def _table_map(ctx):
    return _opt_llm(ctx, "tableMap", lambda p, L: (((p or {}).get("maps") or {}).get("counts") or {}).get("open") if p else links_map_open(L), "칸을 못 맞춘 표")


def _apply(ctx):
    """④ 내용 반영 — 끝남 = 「내용 넣기」 의 끝(반영 표식 · 지난 반영 · 넣을 것 0 · 정상 0건)."""
    s, t, F, bad = _need_both(ctx)
    if bad:
        return bad
    p, done = F.get("plan"), fill_done(F)
    nothing = _no_targets(F) or plan_final_zero(p)
    applied = ((F.get("links") or {}).get("kept") or {}).get("applied") or 0
    text = ("넣을 것이 없습니다(이미 넣었거나 넣을 자리가 없음)" if nothing else f"지난 반영 — 넣은 자리 {applied}곳" if done and applied else "반영했습니다" if done
            else "「계획 보기」 에서 확인하고 「반영」 을 누르세요" if p and p.get("fresh") else "")
    return {"st": "done" if done else "todo", "skipped": nothing and not applied and not F.get("filled"), "text": text}


def _guide(ctx):
    """⑥ 작성요령 삭제(줄) — 그 줄이 닿는 문서마다(_guide_of)."""
    return _per(ctx, _guide_of)


def _guide_of(ctx, role="target"):
    """⑥ 작성요령 삭제(문서 하나의 몫) — 끝남 = (「내용 넣기」 가 끝났거나 그 묶음이 없는 정의) · 그 문서에 지울 안내가 남지 않음.
    「내용 넣기」 의 끝은 워크플로우에 하나다(목적 문서의 넣기 재료 fill) · 지울 안내는 문서마다 — 목적 문서 = fill.cleanup · 원본 문서 = 그 문서 facts 의 cleanup(실행기의 MATERIALS 가 얹는다)."""
    t = (ctx.get("pair") or {}).get("target")
    F = ((t or {}).get("facts") or {}).get("fill")
    if not ctx.get("ready") or not t:
        return {"st": "todo", "text": ""}
    if t.get("facts") is None or F is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    if role == "source":
        s = (ctx.get("pair") or {}).get("source")
        if not s or s.get("facts") is None:
            return {"st": "blocked" if s else "todo", "text": "문서를 읽지 못했습니다" if s else ""}
        C, who = s["facts"].get("cleanup") or {}, f"{s['title']} — "
    else:
        C, who = F.get("cleanup") or {}, ""
    if C.get("error") or C.get("counts") is None:
        return {"st": "blocked", "text": f"{who}지울 안내를 세지 못했습니다: {C.get('error') or '응답이 없음'}"}
    n = C["counts"].get("total") or 0
    done = (fill_done(F) or not F.get("fills")) and not n   # fills = 정의에 「내용 넣기」 의 줄이 있나(실행기가 줄의 home 으로 셈 — 묶음 이름이 아니라)
    text = f"{cleanup_text(C['counts'], C.get('patterns'))} — 내용과 쓸 자리는 남깁니다(본문 색 ※ 줄은 내용으로 봄)" if n else "지울 안내가 없습니다"
    return {"st": "done" if done else "todo", "text": who + text}


_STATE.update({"link": _link, "llm": _link_llm, "plan": _plan, "gaps": _gaps, "tableMap": _table_map, "apply": _apply, "guide": _guide})   # 3단계 「내용 넣기」 · 4단계 「문서 정리」(걸음 3 — 이 절)


# ---------------------------------------------------------------- 문서 하나(가족 single — 걸음 6: spec_워크플로우 ② §18-13 「걸음 6 — 문서 하나」) — 1단계 「프로젝트 구성」 의 상태 식
# 화면 doc_agent_work.js agwFitStatus · agwFitApplied 의 식을 문서의 결과로 옮긴 것(화면 메모리의 「같은 계획」 · 「읽어 봤음」 은 서버의 기록으로 — 반영 기록 `applied`(구조가 이미 맞아 확인만 한 것은 adopted) · 입력 값).
# 재료 = 그 문서(목적 문서) facts 의 div(unit_steps.div_facts — plan(지금 계획의 요약 | None) · stale(계획 뒤 문서가 바뀜) 포함).
NO_FORM = "이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다"


def _one(ctx):
    """그 문서 → ({title, id, facts} | None, 구성 재료 | None)."""
    t, tf = _pair_of(ctx, "target")
    return t, ((tf or {}).get("div") if tf else None)


def fit_done(div):
    """구조 반영이 끝났나(화면 agwFitApplied) — 마지막 전체 반영의 값이 지금 입력 값과 같고(당해 차년도 빼고 — divConfirmKey) 그 뒤 다른 값으로 「한 자리만 반영」 한 기록이 없다."""
    a, v = (div or {}).get("applied") or {}, (div or {}).get("input")
    if not (a.get("values") and v) or _no_cur(a["values"]) != _no_cur(v):
        return False
    return not any(p.get("values") and _no_cur(p["values"]) != _no_cur(a["values"]) for p in div.get("partial") or ())


def plan_issues(s, every=True):
    """사람이 봐야 할 것(화면 divPlanIssues) — 「계획 오류 n건 · 미해결 n곳[ · 지원 안 됨 n곳]」 | ""."""
    s = s or {}
    return " · ".join(x for x in (f"계획 오류 {s['errors']}건" if s.get("errors") else "", f"미해결 {s['unresolved']}곳" if s.get("unresolved") else "",
                                  f"지원 안 됨 {s['unsupported']}곳" if every and s.get("unsupported") else "") if x)


def plan_same(s):
    """바꿀 것이 없는 계획의 글(화면 divSameText) → (이미 맞음인가, 글) — 「이미 맞음」 과 「못 맞춤」 을 같은 글로 보이지 않는다."""
    s = s or {}
    stops, rest = plan_issues(s, False), f" · 지원 안 됨 {s['unsupported']}곳은 그대로" if s.get("unsupported") else ""
    if stops:
        return False, f"바꿀 수 있는 자리가 없습니다 · {stops}{rest}"
    if s.get("already"):
        return True, f"현재 구성과 맞습니다 — 바꿀 자리가 없습니다{rest}"
    return False, f"맞출 수 있는 자리가 없습니다 · 지원 안 됨 {s['unsupported']}곳" if s.get("unsupported") else "맞출 자리를 찾지 못했습니다"


def plan_text(s):
    """변경 계획의 수(화면 agwFitStatus 의 planText) — 「맞출 자리 a곳 · 항목 추가 b · 지움 c · 글 바꿈 d · 지워지는 글 문단 e[ · 계획 오류 …]」."""
    s = s or {}
    issues = plan_issues(s, False)
    return (f"맞출 자리 {s.get('applied') or 0}곳 · 항목 추가 {s.get('added') or 0} · 지움 {s.get('removed') or 0} · 글 바꿈 {s.get('changes') or 0} · 지워지는 글 문단 {s.get('deleted') or 0}"
            + (f" · {issues}" if issues else ""))


def _s_open(ctx):
    """준비 — 문서가 있으면 끝난 것(문서를 올리면 작업이 생기고 워크플로우가 적힌다)."""
    return {"st": "done" if ctx.get("ready") else "todo", "text": ""}


def _s_read(ctx):
    """구성 읽기(선택) — 끝남 = 입력 값이 있음(화면의 「읽어 봤음」 은 탭 메모리라 서버는 이것으로 센다)."""
    t, div = _one(ctx)
    if not ctx.get("ready") or not t or div is None:
        return {"st": "todo", "text": ""}
    if div.get("input"):
        return {"st": "done", "text": ""}
    r = div.get("read")
    return {"st": "todo", "text": f"문서에 적힌 값 — {summary_text(r)}(입력 칸에 채웁니다 — 확정은 「프로젝트 구성 확정」 에서)" if r else "문서에 적힌 단계 · 차년도 · 기관을 읽어 입력 칸에 채웁니다 — 확정은 「프로젝트 구성 확정」 에서 합니다"}


def _s_values(ctx):
    """프로젝트 구성 확정 — 끝남 = 입력 값이 확정한 값과 같음(당해 차년도 빼고 — _config 와 같은 식: 구성의 기준 = 이 문서). 지원하지 않는 양식은 구조 반영을 할 수 없어 「건너뜀」(헤딩 · 표 묶음을 막지 않는다)."""
    t, div = _one(ctx)
    got = _config({**ctx, "base": "target"})
    if got["st"] != "done" and div is not None and ctx.get("ready") and not div.get("supported"):
        return {"st": "done", "skipped": True, "text": f"{NO_FORM} — 구조 반영이 없어 확정하지 않아도 됩니다"}
    return got


def _s_apply(ctx):
    """구조 반영 — 끝남 = 마지막 전체 반영의 값이 지금 입력 값과 같음(당해 차년도 빼고 · 구조가 이미 맞아 확인만 한 것 포함 — fit_done). 지원하지 않는 양식 = 「건너뜀」."""
    t, div = _one(ctx)
    if not ctx.get("ready") or not t:
        return {"st": "todo", "text": ""}
    if div is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    if not div.get("supported"):
        return {"st": "done", "skipped": True, "text": NO_FORM}
    if _s_values(ctx)["st"] != "done" or not fit_done(div):
        return {"st": "todo", "text": ""}
    return {"st": "done", "text": "이미 프로젝트 구성에 맞습니다" if (div.get("applied") or {}).get("adopted") else "문서 구조를 프로젝트 구성에 맞췄습니다"}


def _s_plan(ctx):
    """변경 계획 보기 — 끝남 = 구조 반영이 끝났거나 · 확정한 값으로 세운 지금 문서의 전체 계획이 있음(표 하나만의 계획 `only` 는 아니다 — 화면 agwTaskPlan). 계획은 서버 메모리의 것 그대로 읽는다(상태 조회가 계획을 세우지 않는다)."""
    t, div = _one(ctx)
    ap = _s_apply(ctx)
    if ap["st"] != "todo":
        return {**ap, "text": NO_FORM if ap.get("skipped") else ""} if ap["st"] == "done" else ap
    if div is None or _s_values(ctx)["st"] != "done":
        return {"st": "todo", "text": ""}
    p = div.get("plan")
    if not p:
        return {"st": "todo", "text": ""}
    if div.get("stale") or p.get("only") is not None:
        return {"st": "todo", "text": "계획이 낡았습니다 — 다시 계획해야 합니다"}
    s = p.get("summary") or {}
    same = not (s.get("groups") or s.get("changes"))
    return {"st": "done", "text": plan_same(s)[1] if same else plan_text(s)}


_STATE_BY["single"] = {"open": _s_open, "read": _s_read, "values": _s_values, "plan": _s_plan, "apply": _s_apply}   # 선택 줄 load · review 는 서버가 세지 않는다(사람이 고르는 줄 — 화면이 그린다)


# ---------------------------------------------------------------- 문서 하나의 2 · 3단계 — 헤딩 추출 · 조정 · 표(갈래 「나」): 화면 doc_agent_work.js agwStdSteps · heads_run_all.js hraLeft · hraUnseen 의 식 그대로
# 재료 = 그 문서 facts 의 std(분석 상태 — unit_steps.analysis: items[heads · templates · formats · tables] · llmPlan · busy). 글 함수(std_*)는 실행기의 끝 글도 쓴다.
STD_NAMES = {"heads": "헤딩 · 템플릿 추출", "headsLlm": "헤딩 LLM 판정 · 서식 계획", "adjust": "조정 — 템플릿 조정 · 서식 조정", "tables": "표 구조 — 칸 역할 라벨", "tablesLlm": "표 판정(LLM) — 라벨 검증 · 보완"}


def std_items(v):
    return {i["key"]: i for i in (v or {}).get("items") or ()}


def std_left(v):
    """분석 상태 → 조정에서 남은 것(화면 hraLeft): plans(반영할 수 있는 계획 수) · change · moved · reps · place(자리 맞춤이 남은 줄) · sure(확실한 종속) · hints(애매한 종속 제안) ·
    apply(반영할 것이 있나) · need[계획이 없거나 옛것인 템플릿] · undecided(헤딩 판정의 미판정) · kept · unanswered · omitted(받아 둔 계획이 남길 것) · done(반영한 계획이 지금 문서에 남긴 줄 | None) ·
    norep(대표가 없는 레벨) · at{템플릿 id: 계획의 표시}(방금 읽은 그 계획만 반영한다) · llm[돌 LLM 단계]."""
    it = std_items(v)
    f, h = it.get("formats") or {}, it.get("heads") or {}
    L, rel = f.get("llm") or {}, (it.get("templates") or {}).get("hints") or []
    lines = None if "change" not in L else (L.get("change") or 0) + (L.get("moved") or 0) + (L.get("reps") or 0)   # None = 줄 수를 모른다(반영은 해 본다)
    sure, place, rows, d = sum(1 for x in rel if x.get("sure")), f.get("place") or 0, L.get("list") or [], L.get("left")
    return {"llm": [p for p in (v or {}).get("llmPlan") or () if p.get("run")], "plans": L.get("planned") or 0, "change": L.get("change") or 0, "moved": L.get("moved") or 0, "reps": L.get("reps") or 0,
            "done": {"kept": d.get("kept") or 0, "unanswered": d.get("unanswered") or 0, "marked": d.get("marked") or 0} if d else None, "norep": f.get("noRep") or 0, "place": place,
            "apply": (bool(L.get("planned")) and lines != 0) or sure > 0 or place > 0, "sure": sure, "hints": len(rel) - sure,
            "need": [x for x in rows if x.get("state") in ("none", "stale")], "undecided": h.get("undecided") or 0,
            "kept": L.get("kept") or 0, "unanswered": L.get("unanswered") or 0, "omitted": L.get("omitted") or 0,
            "at": {x["tpl"]: x["at"] for x in rows if x.get("state") == "planned" and x.get("at") is not None}}


def std_apply_text(P):
    """조정이 반영할 것 한 줄(화면 agwStdApplyText)."""
    return " · ".join(x for x in (f"받아 둔 서식 정리 계획 {nf(P['plans'])}개(템플릿)" if P["plans"] else "", f"대표에 맞출 줄 {nf(P['change'])}" if P["change"] else "",
                                  f"서식 종속 템플릿으로 뗄 줄 {nf(P['moved'])}" if P["moved"] else "", f"대표를 바꿀 레벨 {nf(P['reps'])}" if P["reps"] else "",
                                  f"자리 맞춤 {nf(P['place'])}줄" if P["place"] else "", f"확실한 종속 {nf(P['sure'])}개" if P["sure"] else "") if x) or "반영할 것"


def std_kept(d):
    """반영한 계획이 남긴 줄(화면 hraKept) → [글] | [] — 「끝」 으로 뭉개지 않는다."""
    if not d:
        return []
    kept = " · ".join(x for x in (f"그대로 둔 줄 {nf(d['kept'])}" if d.get("kept") else "", f"답이 없어 안 바꾼 줄 {nf(d['unanswered'])}" if d.get("unanswered") else "",
                                  f"형광펜·필드 표지가 있어 모양만 맞춘 줄 {nf(d['marked'])}(글은 그대로)" if d.get("marked") else "") if x)
    return [f"반영한 계획이 남긴 것 — {kept}(「반영한 계획 보기」 · 「템플릿 관계」 에서 손으로)"] if kept else []


def std_unseen(P, skip_undecided=False):
    """반영할 것이 없어도 「다 봤다」 는 아니다 — 남아 있는, 사람이 볼 것(화면 hraUnseen) → [글…]."""
    out = []
    if P["undecided"] and not skip_undecided:
        out.append(f"헤딩 판정의 미판정 {nf(P['undecided'])}곳(LLM 구간 검증 실패 — 「단계별 실행」 의 헤딩 판정을 다시)")
    if P["hints"]:
        out.append(f"종속 제안 {nf(P['hints'])}개(애매한 것 — 결과 화면의 「템플릿 관계」 절에서 고릅니다)")
    k = [x for x in (f"에이전트가 그대로 둔 줄 {nf(P['kept'])}" if P["kept"] else "", f"답이 없어 안 바꾼 줄 {nf(P['unanswered'])}" if P["unanswered"] else "",
                     f"서식 가짓수가 많아 못 본 서식 {nf(P['omitted'])}가지" if P["omitted"] else "") if x]
    if k:
        out.append(f"받아 둔 계획이 남긴 것 — {' · '.join(k)}(조정 층의 칸을 눌러 계획 보기 · 「템플릿 관계」 에서 손으로)")
    out += std_kept(P["done"])
    if P["norep"]:
        out.append(f"대표가 없는 레벨 {nf(P['norep'])}개(「템플릿 관계」 에서 줄 하나를 대표로 — 대표가 없으면 맞춘 레벨로 세지 않습니다)")
    return out


def std_undecided_text(n):
    """미판정이 있어 조정을 하지 않을 때의 글(화면 agwStdSteps 의 adjust)."""
    return f"헤딩 판정에 미판정 {nf(n)}곳이 있어 반영하지 않습니다 — 헤딩 판정을 다시 돌리거나 「계획 보기」 에서 확인합니다"


def _std(ctx):
    """그 문서 → ({title, id, facts} | None, 분석 상태 | None, 막힘 상태 | None)."""
    t, tf = _pair_of(ctx, "target")
    if not ctx.get("ready") or not t:
        return t, None, {"st": "todo", "text": ""}
    v = (tf or {}).get("std") if tf else None
    if v is None:
        return t, None, {"st": "blocked", "text": "분석 상태를 읽지 못했습니다"}
    if "heads" not in std_items(v) or "tables" not in std_items(v):
        return t, v, {"st": "todo", "text": "헤딩 · 표 분석은 hwpx 문서에서만 됩니다"}
    return t, v, None


def _std_base(ctx, key):
    """헤딩 · 템플릿 추출 · 표 구조(스크립트) — 끝남 = 분석 상태의 그 항목이 「✓」(화면 agwStdSteps 의 base)."""
    t, v, bad = _std(ctx)
    if bad:
        return bad
    it = std_items(v)[key]
    st = it.get("state")
    if st == "done":
        return {"st": "done", "text": it.get("short") or it.get("text") or ""}
    if st in ("running", "wait"):
        return {"st": "busy", "text": f"{it.get('name')} 분석 중(스크립트)"}
    if st == "failed":
        return {"st": "failed", "text": f"{it.get('name')} 분석 실패 — {it.get('error') or '까닭 모름'}"}
    return {"st": "todo", "text": f"{it.get('name')} 분석 결과가 없습니다"}


def _std_llm(ctx, key):
    """헤딩 LLM 판정 · 표 판정(LLM) — 끝남 = 그 항목의 LLM 이 「✓」(화면 agwStdSteps 의 llm). LLM 을 쓸 수 없으면 **남음**(「건너뜀」 으로 끝내지 않는다 — ② §18-13 ⓑ: 화면과 같게) · 유료로 부를 문서 = 안 끝난 이 문서."""
    t, v, bad = _std(ctx)
    if bad:
        return bad
    it = std_items(v)
    L = it[key].get("llm") or {}
    st = {"done": "done", "running": "busy", "wait": "busy", "failed": "failed"}.get(L.get("state"), "todo")
    text = (L.get("text") or "LLM 판정 안 함") + (f" — {L['error']}" if L.get("error") else "")
    fl = (it.get("formats") or {}).get("llm") or {}
    if key == "heads" and st == "done" and fl.get("text"):
        text += f" · {fl['text']}"
    off = ctx.get("llm") is False
    if st in ("todo", "failed") and off:
        text += " · LLM 을 쓸 수 없어 지금은 할 수 없습니다"
    return {"st": st, "text": text, "paid": [] if st in ("done", "busy") or off else [t["id"]]}


def _s_adjust(ctx):
    """조정 「모두 반영」 — 헤딩 판정(LLM) 전이면 남음 · 판정 뒤 반영할 것(계획 · 자리 맞춤 · 확실한 종속 · 받을 계획)이 남지 않았으면 끝남(화면 agwStdSteps 의 adjust — 차례가 중요하다:
    서식 항목의 반영 칸이 ✓ 여도 판정 전이거나 확실한 종속 · 대표 변경이 남았으면 끝남이 아니다). 남긴 줄은 끝남의 글에 적는다(실패도 「다 맞음」 도 아니다)."""
    t, v, bad = _std(ctx)
    if bad:
        return bad
    it = std_items(v)
    H, F = it["heads"], it.get("formats")
    if not F or H.get("state") != "done":
        return {"st": "todo", "text": "헤딩 그래프가 있어야 셉니다"}
    judged = (H.get("llm") or {}).get("state") == "done"
    P, fl, ap = std_left(v), F.get("llm") or {}, F.get("apply") or {}
    if not judged:
        return {"st": "todo", "text": "헤딩 LLM 판정 뒤에 합니다" + (f" — 지금 {ap['text']}" if ap.get("text") else "")}
    if fl.get("state") in ("running", "wait"):
        return {"st": "busy", "text": fl.get("text") or "서식 정리 계획을 받는 중"}
    if P["apply"]:
        return {"st": "todo", "text": std_undecided_text(P["undecided"]) if P["undecided"] else f"반영할 것 — {std_apply_text(P)}"}
    if P["need"]:
        return {"st": "todo", "text": f"서식 정리 계획을 받지 않은 템플릿 {nf(len(P['need']))}개 — 「계획 보기」 의 「계획 받기」(유료)", "paid": [] if ctx.get("llm") is False else [t["id"]]}
    left = std_unseen(P, True)
    return {"st": "done", "text": "반영할 것이 남지 않았습니다" + (f" — {ap['text']}" if ap.get("text") else "") + (f" · 남긴 것: {' / '.join(left)}" if left else "")}


_STATE_BY["single"].update({"heads": lambda ctx: _std_base(ctx, "heads"), "headsLlm": lambda ctx: _std_llm(ctx, "heads"), "adjust": _s_adjust,
                            "tables": lambda ctx: _std_base(ctx, "tables"), "tablesLlm": lambda ctx: _std_llm(ctx, "tables")})   # 선택 줄 tree · tableTools 는 세지 않는다(사람이 한다)


# ---------------------------------------------------------------- 취합(가족 gather — 걸음 5: ② §18-13 갈래 「다」) — 화면 gather.js gatherSteps 의 식 그대로
# 재료 = 목적 문서(취합본) facts 의 div(프로젝트 구성) · gather(취합 상태 — unit_steps.gather: GET …/gather 의 값 {frame{stale}, parts[{work, name, orgs, counts, todo, llm, reasons}], orgs, reasons}).
# 3단계의 줄은 **원본 문서마다** 센다(per[]) — 그 줄의 끝남 = 모든 기관 문서에서 끝남 · 기관 문서가 아직 없으면 할 일이 없다(「건너뜀」 — 들어오면 그때).
GT_REASON = {"noFrame": "배포 기준본이 없음", "frameStale": "기준본이 낡음(프로젝트 구성을 다시 반영함 — 새로 만들어야 함)", "frameDiffers": "기준본이 다름(다른 판의 기준본으로 온 문서)", "noHeadings": "헤딩·표 분석 없음",
             "staleHeadings": "헤딩·표 분석이 지금 문서의 것이 아님", "noMatch": "기준본과 맞는 자리를 찾지 못함(끌어 넣기만)", "noValues": "프로젝트 구성 값 없음", "notApplied": "프로젝트 구성 반영 전",
             "unsupportedForm": "지원하지 않는 양식·형식", "lowMatch": "기준본과 자리를 충분히 확인하지 못함 — 넣을 것을 직접 고르세요", "stalePlan": "계획 뒤 문서·설정이 바뀜(다시 계획)",
             "notPart": "이 취합에 든 기관 문서가 아님", "badPart": "기관 문서로 넣을 수 없는 문서(지운 문서 등)", "noLlm": "LLM 을 쓸 수 없음", "error": "판정하지 못함(오류)"}   # 화면 gather.js GT_REASON 과 같은 말
GT_COUNT = (("items", "작성 내용"), ("hunks", "작성 내용"), ("paragraphs", "문단"), ("tables", "표"), ("pictures", "그림"), ("cells", "표 칸"), ("rows", "행 추가"), ("placeholders", "지운 자리표시 줄"),
            ("removed", "지운 자리표시 줄"), ("shaped", "글자 모양 맞춤"), ("fitted", "그림 폭 맞춤"), ("converted", "틀 맞춤"), ("kept", "쓴 대로 둔 개요 줄"), ("over", "넘친 레벨"), ("recalculated", "다시 계산"),
            ("skipped", "반영 때 건너뜀"))   # 넣은 수 → 화면 말(화면 GT_COUNT — 블록 수는 문단 · 표 · 그림과 겹쳐 뺀다)


def gt_reasons(xs):
    return " · ".join(GT_REASON.get(k, k) for k in xs or ())


def gt_hard(xs):
    """그 줄의 자리 연결을 막는 까닭만(lowMatch 는 막지 않는다 — 넣을 것을 사람이 고른다)."""
    return [k for k in xs or () if k != "lowMatch"]


def gt_todo(L):
    """연결 목록에서 저절로 넣을 수 있는 것의 수(화면 gatherTodo) — 넣을 수 있고(ready) 결정이 빼기 · 확인 필요가 아닌 작성 내용."""
    return sum(1 for it in (L or {}).get("items") or () if it.get("status") == "ready" and (it.get("decision") or {}).get("value") not in ("skip", "check"))


def gt_part_todo(p):
    """그 기관 문서에 남은 넣을 것(화면 gatherPartTodo) | None(아직 모름 — 자리 연결 전)."""
    if p.get("todo") is not None:
        return p["todo"]
    return (p["counts"].get("ready") or 0) if p.get("counts") else None


def gt_done_text(r):
    """반영 결과 한 줄(화면 gatherDoneText) — 「문단 3 · 표 칸 5 · …」(+ 「다시 계산 필요 n칸」 · 「못 옮긴 것 n」)."""
    c, seen, parts = (r or {}).get("counts") or {}, set(), []
    for k, name in GT_COUNT:
        if isinstance(c.get(k), (int, float)) and not isinstance(c.get(k), bool) and c[k] and name not in seen:
            seen.add(name)
            parts.append(f"{name} {nf(c[k])}")
    need = sum(1 for x in (r or {}).get("calc") or () if not x or x.get("action") != "recalculated") + int((r or {}).get("calcNeed") or 0)
    return (" · ".join(parts) or "넣음") + (f" · 다시 계산 필요 {need}칸" if need else "") + (f" · 못 옮긴 것 {len(r['dropped'])}" if (r or {}).get("dropped") else "")


def gt_part_done(p):
    """그 기관 문서의 넣기가 끝났나(화면 gatherSteps 의 part 줄 done) — 반영할 기관이 정해졌고 · 막는 까닭이 없고 · 남은 넣을 것이 0(자리를 충분히 확인하지 못한 문서는 넣을 수 있는 것이 남으면 아님)."""
    c, low = p.get("counts"), "lowMatch" in (p.get("reasons") or ())
    return bool(p.get("orgs")) and not gt_hard(p.get("reasons")) and c is not None and gt_part_todo(p) == 0 and not (low and (c.get("ready") or 0) > 0)


def _gt(ctx):
    """(목적 문서 {title, id, facts} | None, 구성 재료 | None, 취합 상태 | None)."""
    t, tf = _pair_of(ctx, "target")
    return t, ((tf or {}).get("div") if tf else None), ((tf or {}).get("gather") if tf else None)


def _g_division(ctx):
    """프로젝트 구성 반영 — 끝남 = 입력 값이 문서에 반영돼 있음(반영 값 = 입력 값 — 화면 gatherDivDone: 구조가 이미 맞아 확인만 한 것 포함)."""
    t, d, _g = _gt(ctx)
    if not ctx.get("ready") or not t or _config(ctx)["st"] != "done":
        return {"st": "todo", "text": ""}
    if d is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    v, a = d.get("input"), d.get("applied") or {}
    if v and a.get("values") == v:
        return {"st": "done", "text": f"{'구조가 이미 값에 맞음(확인함)' if a.get('adopted') else '취합본에 반영됨'} — {summary_text(v)}"}
    if not d.get("supported"):
        return {"st": "todo", "text": "이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다(연구개발계획서 양식만)"}
    return {"st": "todo", "text": "입력한 값이 마지막으로 반영한 값과 다릅니다 — 변경 계획을 확인하고 반영하세요" if a else "값이 아직 취합본에 반영되지 않았습니다 — 바뀔 자리를 확인한 뒤 반영합니다(절·표 행·열 — 구조만)"}


def _g_frame(ctx):
    """배포 기준본 — 끝남 = 기준본이 있고 낡지 않음(프로젝트 구성을 다시 반영하면 낡는다)."""
    t, _d, G = _gt(ctx)
    if not ctx.get("ready") or not t or _g_division(ctx)["st"] != "done":
        return {"st": "todo", "text": ""}
    if G is None:
        return {"st": "blocked", "text": "취합 상태를 읽지 못했습니다"}
    F = G.get("frame")
    if F and not F.get("stale"):
        return {"st": "done", "text": "기준본을 만들었습니다 — 내려받아 기관에 나눠 주세요(기관은 자기 몫만 채워 돌려줍니다)"}
    if F:
        return {"st": "todo", "text": "기준본을 만든 뒤 프로젝트 구성을 다시 반영했습니다 — 기준본이 낡았습니다. 새로 만들어 다시 나눠 주세요(낡은 기준본으로 온 기관 문서는 저절로 넣지 않습니다)"}
    why = gt_reasons(G.get("reasons"))
    return {"st": "todo", "text": "기관에 나눠 줄 기준본을 만듭니다 — 지금 취합본 파일과 자리 정보(자리마다 기관·차년도)를 고정합니다" + (f" · {why}" if why else "")}


def _g_hand(ctx):
    """기관에 배포 · 회수 — 앱 밖의 일이라 세지 않는다(기관 문서가 들어오면 3단계)."""
    return {"st": "done" if ctx.get("ready") else "todo", "skipped": True, "text": "기준본을 내려받아 기관에 나눠 주고 돌려받습니다(앱 밖의 일 — 세지 않습니다)"}


def _g_each(ctx, what):
    """원본 문서마다 세는 줄 — what = part(반영할 기관) · heads(헤딩 · 표 분석) · link(자리 연결) · llm(LLM 검토) · fill(넣기 계획 · 내용 반영). 기준본이 없거나 낡았으면 아직(줄이 열리지 않는다)."""
    t, _d, G = _gt(ctx)
    if not ctx.get("ready") or not t:
        return {"st": "todo", "text": ""}
    if G is None:
        return {"st": "blocked", "text": "취합 상태를 읽지 못했습니다"}
    F, rows = G.get("frame"), G.get("parts") or []
    if not (F and not F.get("stale")):
        return {"st": "todo", "text": ""}
    if not rows:
        return {"st": "done", "skipped": True, "text": "기관 문서가 아직 없습니다 — 들어오면 그때 넣습니다"}
    per = []
    for p in rows:
        c, why, orgs = p.get("counts"), gt_hard(p.get("reasons")), p.get("orgs") or []
        if what == "part":
            ok, text = bool(orgs), "" if orgs else "반영할 기관 미지정 — 미지정이면 넣지 않습니다"
        elif what == "heads":
            ok, text = "noHeadings" not in why, "헤딩·표 분석 없음" if "noHeadings" in why else ""
        elif what == "link":
            ok, text = c is not None and not why, f"자리 연결을 할 수 없습니다 — {gt_reasons(why)}" if why else "" if c is not None else "아직 안 함 — 기준본과 견줘 기관이 쓴 내용을 찾습니다"
        elif what == "llm":
            ok, text = bool(p.get("llm")) or not (c or {}).get("ready"), ""
        else:
            ok = gt_part_done(p)
            n = gt_part_todo(p)
            text = "" if ok else f"넣을 내용 {nf(n)}곳" if n else ""
        per.append({"doc": p["work"], "role": "source", "st": "done" if ok else "todo", "text": f"{p.get('name')} — {text}" if text else ""})
    left = [x for x in per if x["st"] != "done"]
    return {"st": "todo" if left else "done", "text": f"기관 문서 {nf(len(rows))}개" + (f" · 남은 문서 {nf(len(left))}개" if left else ""), "per": per}


_STATE_BY["gather"] = {"division": _g_division, "frame": _g_frame, "hand": _g_hand, "part": lambda ctx: _g_each(ctx, "part"), "heads": lambda ctx: _g_each(ctx, "heads"),
                       "link": lambda ctx: _g_each(ctx, "link"), "llm": lambda ctx: _g_each(ctx, "llm"), "plan": lambda ctx: _g_each(ctx, "fill"), "apply": lambda ctx: _g_each(ctx, "fill")}   # drop 은 사람이 한다
