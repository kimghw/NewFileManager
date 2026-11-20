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


def _u(key, home, place, *, roles=(), kind="auto", change="none", paid="", needs=(), gives=(), spoils=(), redo=(), once=False, optional=False, via="", server=False, reads=()):
    """reads = 상태를 셀 때 그 줄의 문서 밖에서 재료를 읽어야 하는 문서 역할(구성 확정 · 구조 반영은 원본(구성의 기준)과 목적을 함께 본다)."""
    return dict(key=key, home=home, place=place, roles=tuple(roles), kind=kind, change=change, paid=paid, needs=tuple(needs), gives=tuple(gives), spoils=tuple(spoils), redo=tuple(redo),
                once=once, optional=optional, via=via, server=server, reads=tuple(reads))


# 두 틀이 같이 쓰는 단위 — 준비 · 문서 검토 · 구성 맞추기 · 문서 정리 · 사람이 하는 일
COMMON = {u["key"]: u for u in (
    _u("files", "", "flow", kind="pick", gives=("slots",), server=True),                                                    # 준비 — 실행기는 안 한다(칸이 비면 시작이 거절)
    _u("heads", "stage_review", "doc", roles=ROLES, change="store", needs=("slots",), gives=("heads",), server=True),       # 헤딩 · 표 분석(배경 일 · 목적 문서면 끝에 작성 지침 저장)
    _u("headsLlm", "stage_review", "doc", roles=ROLES, change="store", paid="doc", needs=("heads",), gives=("checked",), server=True),   # LLM 검증·보완(배경 일 — 못 쓰거나 건너뛰면 「건너뜀」)
    _u("configLoad", "stage_fit", "flow", kind="pick", change="store", optional=True, server=True),                         # 구성 불러오기(선택 — 실행기는 지나감)
    _u("config", "stage_fit", "flow", change="store", needs=("slots",), gives=("config",), server=True, reads=ROLES),        # 프로젝트 구성 확정(값 = 원본(구성의 기준) · 확정 = 목적 문서에서 — 화면 실행과 같다)
    _u("division", "stage_fit", "doc", roles=("target",), change="doc", needs=("config",), gives=("fit",), spoils=("fresh",), server=True, reads=ROLES),   # 프로젝트 구성 반영(같은 검사 · 울타리)
    _u("reheads", "stage_fit", "doc", roles=("target",), change="store", needs=("fit",), gives=("fresh", "heads"), server=True, reads=ROLES),   # 다시 문서 검토
    _u("reheadsLlm", "stage_fit", "doc", roles=("target",), change="store", paid="doc", needs=("fresh",), gives=("checked",), server=True, reads=ROLES),   # 다시 문서 검토(LLM)
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
_STATE.update({"config": lambda ctx: _config(ctx), "division": lambda ctx: _division(ctx), "reheads": lambda ctx: _reheads(ctx), "reheadsLlm": lambda ctx: _reheads_llm(ctx)})   # 2단계 「구성 맞추기」(걸음 2 — 아래 절)


def state(key, ctx, family="relay"):
    """그 줄의 지금 상태 | None(서버가 아직 세지 않는 줄 — 화면이 센다: ② §17-5 의 `server: false`)."""
    u = unit(key, family)
    fn = _STATE.get(key) if u and u["server"] else None
    return fn(ctx) if fn else None


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
    src = (s or {}).get("title") or "원본 문서"
    if not v:
        return {"st": "todo", "text": f"프로젝트 구성(단계·차년도·기관)이 없습니다 — {src}에서 추출하거나 아래 「프로젝트 구성 불러오기」 · 입력 칸에서 정하세요"}
    if cf:
        return {"st": "todo", "text": f"확정한 뒤 값이 바뀌었습니다 — 다시 저장하거나 확정본으로 되돌리세요(지금: {summary_text(v)})"}
    return {"st": "todo", "text": f"{summary_text(v)} — 확인한 뒤 {where}에 저장(확정)하세요"}


def _division(ctx):
    """프로젝트 구성 반영 — 두 문서의 값이 같고(당해 차년도 빼고) 목적 문서의 지금 값이 반영됐으면 끝남(② §18-12 ② 「fit」)."""
    (s, sf), (t, tf) = _pair_of(ctx, "source"), _pair_of(ctx, "target")
    if not ctx.get("ready") or not s or not t or _config(ctx)["st"] != "done":
        return {"st": "todo", "text": ""}
    A, B = (sf or {}).get("div"), (tf or {}).get("div")
    if A is None or B is None:
        return {"st": "blocked", "text": "문서를 읽지 못했습니다"}
    S, D = s["title"], t["title"]
    a, read = basis_values(A)
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
    """다시 문서 검토 — 구조 반영이 끝났고 목적 문서의 분석이 그 반영 뒤의 것이면 끝남 · 반영 전 분석이 LLM 결과이고 LLM 을 쓸 수 없으면 그대로 두고 끝남(keep)."""
    t, tf = _pair_of(ctx, "target")
    if _division(ctx)["st"] != "done" or tf is None:
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
    """다시 문서 검토(LLM) — 화면 llmStep(reheadsLlm): 앞 줄이 끝나야 셈 · 끝남 = 거침 | LLM 을 못 씀 | 건너뜀. 유료로 부를 문서 = 끝나지 않았고 건너뛰지 않은 목적 문서(앞 줄이 아직이어도 — 화면 taskPaidDocs)."""
    t, tf = _pair_of(ctx, "target")
    if not t or not ctx.get("ready"):   # 칸이 비면 유료 대상도 없다(화면 taskPaidDocs — 두 칸이 차야 센다)
        return {"st": "todo", "text": ""}
    paid = [] if ctx.get("llm") is False or t["id"] in (ctx.get("skip") or ()) else [t["id"]]
    if _reheads(ctx)["st"] != "done" or tf is None:
        return {"st": "todo", "text": "", "paid": paid}
    got = _llm_one({"facts": tf, "title": t["title"], "role": "target"}, ctx)
    return {"st": got["st"], "skipped": got.get("skipped", False), "text": got["text"], "paid": [] if got["st"] == "done" else paid}
