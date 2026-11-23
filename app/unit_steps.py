"""단위문서 TASK 의 문 — 워크플로우 실행 층이 문서의 일을 시키는 하나뿐인 길(spec_워크플로우 ② §17-3 「단위문서 TASK 의 문」 · 단위의 뜻은 ② §18-2 「실행 단위」).

워크플로우 실행 층(app/workflow_units.py · workflow_state.py · workflow_exec.py · workflow_exec_api.py)은 `app.server` · `*_api` · `works` · `llm` · `heading_runs` · `task_options` 를 가져오지 않는다 —
그 이름을 아는 파일은 **이것 하나**다(함수 안에서 가져온다 — server 가 그 층을 붙이므로 순환 import 를 피한다 · 나중에 다른 프로세스로 뗄 때 바꿀 파일도 이것 하나: ② §17-10 「떼기」).
- **문서 id 만 받는다**(세션을 넘기거나 쥐지 않는다 — 밀려남 · 다시 열기를 견딘다). 일을 시키는 함수는 하나의 꼴 `Outcome{code, text, data, rev}` 를 돌려준다:
  `ok` · `nothing`(할 일 없음) · `busy`(헤딩 작업 자리가 참) · `stale`(409 — 계획 · 목록을 만든 뒤 문서가 바뀜) · `blocked`(409 — 전제 없음) · `rejected`(422 — 되돌리고 **돌려준** 응답) ·
  `invalid`(400) · `missing`(404 — 세션이 밀려남 포함) · `error`(그 밖 — 서버 로그). 409 가 셋 가운데 무엇인지는 부르는 함수가 정한다(`on409`).
- 판정 · 편집 · 프롬프트 · 저장은 지금 끝점 함수 그대로다 — 여기는 응답 꼴만 맞춘다. 끝점 함수는 인자를 모두 넘겨 부른다(`Body` 기본값을 타지 않게) · `get_doc` 은 부르지 않는다(작업에 종류 짐작을 저장하는 부작용).
- 지금 있는 것(걸음 1 — 「문서 검토」): 읽기 `work` · `pair` · `facts` · `llm_ok` · `skips` / 배경 일 `start_heads` · `start_llm` · `job` · `stop_llm` / 동기 일 `guides_keep` · `skip_set` / 저장 `store`(실행 기록 · 기록 줄).
  묶음째 실행의 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」): `commit_info` · `commit`(server._commit_now — 울타리 안에서) · `base_now`(확인 폴링)."""
import logging
import time

log = logging.getLogger("uvicorn.error")
CODES = ("ok", "nothing", "busy", "stale", "blocked", "rejected", "invalid", "missing", "error")
RUNS = "flowruns"   # 실행 기록 폴더(목적 문서의 작업 폴더 — 검증 기록 `runs` · 문서마다의 진행 요약 `workflows` 와 겹치지 않는 이름: ② §17-4)
LOG_KIND = "flowRun"   # 작업 기록(log.jsonl)의 줄 종류


class Outcome:
    """문이 돌려주는 하나의 꼴 — code(CODES) · text(사람이 읽는 까닭 — 화면에 그대로) · data(끝점이 돌려준 것) · rev(그 문서의 차례 | None)."""
    __slots__ = ("code", "text", "data", "rev")

    def __init__(self, code="ok", text="", data=None, rev=None):
        self.code, self.text, self.data, self.rev = code, text, data, rev

    @property
    def ok(self):
        return self.code in ("ok", "nothing")

    def __repr__(self):
        return f"Outcome({self.code!r}, {self.text!r})"


def _detail(detail):
    """HTTPException 의 detail → 사람이 읽는 글(취합 끝점은 {reason, message} 를 준다)."""
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("reason") or "")
    return str(detail or "")


def _run(fn, *args, on409="busy", **kw):
    """끝점 함수를 불러 Outcome 으로 — HTTPException 은 상태 코드로 가르고(409 = on409), **돌려준** 응답(422 — `_transact` 가 되돌린 것)은 `rejected`."""
    import json

    from fastapi import HTTPException
    from starlette.responses import Response
    try:
        got = fn(*args, **kw)
    except HTTPException as e:
        code = {400: "invalid", 404: "missing", 409: on409, 413: "invalid", 422: "rejected"}.get(e.status_code, "error")
        return Outcome(code, _detail(e.detail), {"status": e.status_code, "detail": e.detail})
    except Exception as e:  # noqa: BLE001 — 실행 층에는 까닭만 넘기고 자취는 서버 로그에
        log.exception("[워크플로우 실행] 단계 함수 %s 오류", getattr(fn, "__name__", fn))
        return Outcome("error", f"{type(e).__name__}: {e}")
    if isinstance(got, Response):
        try:
            body = json.loads(bytes(got.body).decode("utf-8"))
        except (ValueError, AttributeError):
            body = None
        text = _detail((body or {}).get("detail") if isinstance(body, dict) else "") or (body.get("message") if isinstance(body, dict) else "") or ""
        return Outcome("rejected" if got.status_code == 422 else "error" if got.status_code >= 400 else "ok", text, body)
    return Outcome("ok", "", got)


# ---------------------------------------------------------------- 읽기(판정 재료)
def work(wid):
    """작업(work.json) | None."""
    from app import works
    return works.work(wid)


def _doc(w):
    from app import works
    return {"id": w["id"], "name": (works.shown(w) if w.get("name") else "") or w["id"], "format": w.get("format") or ""}


def pair(wid):
    """그 문서가 든 묶음(프로젝트 · 워크플로우 · 라운드)의 문서 쌍 → {job, scope[project, job, round], file(이 문서의 종류), kinds{target, source},
    target{id, name, format} | None, source{…} | None} | None(그런 작업이 없음). **어느 칸의 문서에서 불러도 같은 쌍**이다.
    목적 문서 = 그 묶음에서 종류가 그 워크플로우의 목적 종류(`works.TARGET_FILE` — 조립한 것도 본다)인 문서 · 원본 문서 = 자리 연결 · 넣기가 쓰는 것과 같은 함수(`merge_api._mate` — `merge.json` 의 from 이 먼저).
    목적 종류가 없는 워크플로우(문서 하나)는 이 문서가 목적이고 원본은 없다. **문서 하나로 조립한 워크플로우**(custom_tasks.is_single — 목적 종류는 정의에 있지만 원본이 없다)도 붙박이 문서 하나와 같은 꼴이다:
    이 문서가 곧 목적 문서이고 짝 문서를 찾으러 가지 않는다(이관의 `_mate` 길을 타지 않는다)."""
    from app import custom_tasks, merge_api, projects, works
    w = works.work(wid)
    if w is None:
        return None
    task = w.get("task") if isinstance(w.get("task"), dict) else {}
    job, kind = task.get("job") or "", task.get("file") or ""
    scope = list(projects.group_key(task))
    tkind = works.TARGET_FILE.get(job) if job else None
    if tkind is not None and custom_tasks.is_single(job):   # 문서 하나로 조립한 것 — 문서 칸이 하나다(붙박이 양식 표준화 · 양식 맞추기와 같은 꼴: kinds 는 비운다)
        tkind = None
    out = {"job": job, "scope": scope, "file": kind, "kinds": {"target": tkind, "source": custom_tasks.source_file(job) if tkind else None}, "target": None, "source": None}
    if tkind is None:
        out["target"] = _doc(w)
        return out
    target = w if kind == tkind else None
    if target is None and scope[0]:   # 원본 문서에서 불렀다 — 같은 묶음의 목적 문서(가장 최근 것: 화면의 문서 칸과 같은 차례)
        target = next((x for x in works.list_works() if x["id"] != wid and projects.group_key(x.get("task")) == tuple(scope) and (x.get("task") or {}).get("file") == tkind), None)
    if target is None:
        if kind == out["kinds"]["source"]:
            out["source"] = _doc(w)
        return out
    out["target"] = _doc(target)
    if _gather(job):   # 취합형 — 원본 문서 = 그 목적 문서의 취합에 등록한 문서들(gather.json 의 order — 등록한 차례: 문서 종류 part 는 후보일 뿐이다 · ② §18-12 ⑥). 원본 하나(source)는 없다
        from app import merge_gather_api
        out["kinds"]["source"] = "part"
        out["sources"] = [_doc(x) for x in (works.work(p) for p in merge_gather_api._store(target["id"])["order"]) if x]
        return out
    src = merge_api._mate(target["id"], merge_api._store(target["id"]))[1]
    sw = works.work(src) if src else None
    out["source"] = _doc(sw) if sw else None
    return out


def _gather(job):
    """그 워크플로우가 취합형(원본 문서 여럿 → 목적 문서 하나)인가 — 등록부의 틀로(붙박이 키를 견주지 않는다)."""
    from app import workflow_state
    task = workflow_state.definition(job)
    return bool(task) and workflow_state.family(task) == "gather"


def facts(doc_id):
    """문서 하나의 판정 재료 → {id, name, rev, fmt, heads{s2, s3, rev2, rev3, llm, job}, guides(저장한 작성 지침 수 | None)} | None(없는 문서 · 못 엶).
    heads.llm = 헤딩 그래프 · 표 구조가 둘 다 LLM 검증·보완을 거쳤나(화면 app.js taskLlmDone 과 같은 식 — llm.requested 이고 fallback 이 아님) ·
    heads.job = 지금(또는 마지막) 헤딩 작업 {status, chain, first, stage, error, stopping} | None. 메모리의 세션을 쓰고 없으면 작업 폴더에서 연다(화면이 그 문서를 여는 것과 같은 만큼)."""
    from fastapi import HTTPException

    from app import form_guides_api, heading_runs, server
    try:
        s = server._sess(doc_id)
    except HTTPException:
        return None
    st = heading_runs.state(s) if s.fmt == "hwpx" else {}
    s2, s3, job = st.get("stage2"), st.get("stage3"), st.get("job")
    done = lambda x: bool(x) and bool((x.get("llm") or {}).get("requested")) and not (x.get("llm") or {}).get("fallback")  # noqa: E731
    jv = job.view() if job is not None else None
    saved = form_guides_api.load(doc_id) if s.fmt == "hwpx" else None
    # 넣은 뒤 템플릿 · 서식 정리(spec_병합 ② §5-9)가 헤딩 그래프를 스크립트로 다시 분석했으면 — 그 전 그래프가 LLM 검증·보완을 거친 것이면 거친 것으로 본다(넣은 줄을 템플릿에 넣으려고 다시 분석한 것이다:
    # 앞 단계의 「LLM 검증·보완」 줄이 「안 함」 으로 돌아가 「이어서 한 번에」 가 유료 호출을 다시 걸지 않게 — merge_retidy_api.llm_kept)
    kept = bool(s2) and not done(s2) and __import__("app.merge_retidy_api", fromlist=["llm_kept"]).llm_kept(s.id, ((s2.get("meta") or {}).get("run")))
    return {"id": s.id, "name": s.name, "rev": s.rev, "fmt": s.fmt,
            "heads": {"s2": bool(s2), "s3": bool(s3), "rev2": ((s2 or {}).get("meta") or {}).get("rev"), "rev3": ((s3 or {}).get("meta") or {}).get("rev"), "llm": (done(s2) or kept) and done(s3),
                      "asked": any(bool(((x or {}).get("llm") or {}).get("requested")) for x in (s2, s3)),   # 어느 단계든 LLM 을 부른 결과인가(화면 taskHeadsKept — 구조 반영 전 분석을 다시 돌릴지)
                      "job": {k: jv.get(k) for k in ("status", "chain", "first", "stage", "error", "stopping", "started", "ended")} if jv else None},
            "guides": (len(saved["items"]) + len(saved["marks"])) if saved else None}


def llm_ok():
    """서버의 LLM 을 쓸 수 있나(GET /api/headings/llm 의 available 과 같은 값)."""
    from app import llm
    try:
        return bool(llm.status().get("available"))
    except Exception:  # noqa: BLE001 — 설정을 못 읽으면 못 쓰는 것으로(유료 단계는 「건너뜀」)
        return False


def skips(wid):
    """그 묶음에서 사람이 「LLM 검증·보완」 을 건너뛴 문서 id 들(워크플로우 옵션 — ② §17-6 「건너뛰기」)."""
    from app import task_options, works
    return list(task_options.flow(works.work(wid)).get("llmSkip") or [])


def skip_set(wid, doc_id, on):
    """그 문서의 「건너뛰기」 를 켜거나 끈다 → Outcome(data = 지금 건너뛴 문서 id 들)."""
    from app import task_options, works
    w = works.work(wid)
    if w is None or works.work(doc_id) is None:
        return Outcome("missing", "그런 작업이 없습니다")
    try:
        got = task_options.flow_skip(w, doc_id, bool(on))
    except task_options.Broken as e:
        return Outcome("blocked", str(e))
    return Outcome("ok", "", got)


def take_get(target):
    """「넣을 구성 선택」 의 지금 값 · 고를 수 있는 값(spec_병합 ② §4-1 — merge_api.take_view) → Outcome(data = 그 보기)."""
    from app import merge_api
    return _run(merge_api.take_view, target)


def take_set(target, body):
    """넣을 구성 · 대상 차년도를 적는다(merge_api.take_put — take = 그 묶음의 실행 옵션 · year = 목적 문서의 당해 차년도) → Outcome(data = 다시 읽은 보기). 400 = invalid · 409 = blocked."""
    from app import merge_api
    return _run(merge_api.take_put, target, body, on409="blocked")


def rev_now(doc_id):
    """메모리의 그 세션의 문서 차례 | None(메모리에 없음) — 확인 폴링이 싣는다(세션을 열지 않는다: 울타리를 내린 뒤 화면이 다시 읽을지 견준다)."""
    from app import server
    s = server.DOCS.get(doc_id)
    return s.rev if s is not None else None


def base_now(doc_id):
    """메모리의 그 세션의 기준 확정 번호 | None(메모리에 없음) — 확인 폴링이 싣는다(세션을 열지 않는다: 묶음째 실행의 끝 확정 뒤 그 문서를 연 화면이 새 기준을 따라오게 — ② §18-24)."""
    from app import server
    s = server.DOCS.get(doc_id)
    return s.base_n if s is not None else None


# ---------------------------------------------------------------- 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」 — 묶음째 실행이 끝에 한 번: 「고친 문단」 탭의 확정과 같은 몸 server._commit_now)
def commit_info(doc_id):
    """그 문서의 확정 재료(세션 잠금 안에서 메모리 값만 — 저장 · 다시 열기를 하지 않는다) → {stored(작업 폴더에 확정을 남길 수 있나), dirty(확정할 변경이 있나), edited(고친 문단 수), base(기준 확정 번호)} | None(없는 문서)."""
    from fastapi import HTTPException

    from app import server
    try:
        s = server._sess(doc_id)
    except HTTPException:
        return None
    stored = store.enabled(doc_id)
    with s.lock:
        return {"stored": stored, "dirty": server._dirty(s), "edited": len(s.edited()), "base": s.base_n}


def commit(doc_id, message, flow=None, llm=True):
    """[기준 바뀜] 그 문서의 지금 상태를 확정(server._commit_now — 문서 글 · 블록 id · 차례는 그대로 · 실행 취소 기록은 빔 · 가져오기 검증을 새 기준으로) → Outcome:
    ok(data = {n, parent, counts}) · nothing(확정할 변경이 없음) · blocked(작업 저장이 꺼짐 · 409 — 다른 스레드의 울타리) · missing(404) · error.
    **그 문서의 울타리 안에서 부른다**(run.fence — 화면들의 고치던 글을 먼저 받고 사람 편집을 막는다). flow = 그 실행의 번호(확정 기록 · 작업 기록의 flowRun) · llm = 새 기준의 가져오기 검증이 검증 LLM 을 불러도 되나."""
    from app import server, works
    if not works.enabled():   # 확정 끝점의 400(_commits_on)과 「확정할 변경이 없음」 을 글로 가르지 않게 먼저 본다
        return Outcome("blocked", "작업 저장이 꺼져 있어 확정하지 않았습니다")
    meta = {"by": "flow", **({"flowRun": int(flow)} if flow is not None else {})}
    text = " ".join(str(message or "").split())[:200]

    def go():
        return server._commit_now(server._sess(doc_id), text, meta, verify_llm=bool(llm))
    go.__name__ = "commit"
    got = _run(go, on409="blocked")
    if not got.ok:
        return got
    c = got.data
    if c is None:
        return Outcome("nothing", "확정할 변경이 없습니다")
    return Outcome("ok", "", {"n": c.get("n"), "parent": c.get("parent"), "counts": c.get("counts") or {}}, rev_now(doc_id))


def touch(doc_id):
    """메모리의 그 세션을 방금 쓴 것으로 — 도는 실행이 기다리는 문서가 밀려나지 않게(② §17-7 「기다림」). 메모리에 없으면 False."""
    from app import server
    s = server.DOCS.get(doc_id)
    if s is None:
        return False
    s.touched = time.time()
    return True


# ---------------------------------------------------------------- 배경 일(시작 → 상태 → 멈춤)
def start_heads(doc_id, how="first"):
    """헤딩 · 표 분석을 스크립트로 시작(배경) — how = "first"(없는 단계만: 헤딩 그래프 → 표 구조) | 2 | 3(그 단계를 다시). 도는 중이면 busy."""
    from app import server
    body = {"first": True} if how == "first" else {"stage": how, "llm": False}
    return _run(server.headings_start, doc_id, body)


def start_llm(doc_id, skill=None):
    """헤딩 · 표의 「LLM 검증·보완」 을 시작(배경 · 유료) — 이미 거친 것은 그 실행이 건너뛴다. 도는 중이면 busy."""
    from app import analysis_api
    return _run(analysis_api.analysis_llm_start, doc_id, {"skill": skill} if skill else {})


def job(doc_id):
    """그 문서의 헤딩 작업(지금 · 마지막) → Outcome(data = {status, chain, first, stage, error, stopping, …} | None). **메모리의 세션에서만** 읽고 그 세션을 만진다(밀려났으면 missing)."""
    from app import heading_runs, server
    s = server.DOCS.get(doc_id)
    if s is None:
        return Outcome("missing", "열린 문서가 많아 이 문서가 메모리에서 밀려났습니다")
    s.touched = time.time()
    j = heading_runs.state(s).get("job") if s.fmt == "hwpx" else None
    return Outcome("ok", "", j.view() if j is not None else None, s.rev)


def stop_llm(doc_id):
    """도는 「LLM 검증·보완」 을 지금 일이 끝나면 멈추게(도는 것이 없으면 nothing)."""
    from app import analysis_api
    return _run(analysis_api.analysis_llm_stop, doc_id, on409="nothing")


# ---------------------------------------------------------------- 동기 일
def guides_keep(doc_id):
    """양식의 작성 지침을 헤딩/표별로 모아 저장(스크립트 · 문서 안 바뀜 — POST …/form-guides)."""
    from app import form_guides_api
    return _run(form_guides_api.form_guides_post, doc_id)


# ---------------------------------------------------------------- 저장(실행 기록 · 기록 줄) — 워크플로우 층은 works 를 직접 쓰지 않는다
class store:   # noqa: N801 — 함수 묶음(unit.store.write …)
    @staticmethod
    def enabled(wid):
        """그 작업의 폴더에 쓸 수 있나(작업 저장이 꺼졌으면 실행 기록은 메모리만)."""
        from app import works
        f = works.folder(wid)
        return f is not None and (f / "work.json").is_file()

    @staticmethod
    def write(wid, n, record):
        """실행 기록 하나를 통째로 쓴다(`flowruns/<n>.json` — 작업 잠금 · 원자) → 썼나."""
        from app import works
        return works.add_detail(wid, RUNS, str(int(n)), record) is not None

    @staticmethod
    def read(wid, n):
        from app import works
        f = works.folder(wid)
        p = f / RUNS / f"{int(n)}.json" if f is not None else None
        got = works._read_json(p) if p is not None and p.is_file() else None
        return got if isinstance(got, dict) else None

    @staticmethod
    def numbers(wid):
        """그 작업의 실행 기록 번호들(오름차순)."""
        from app import works
        f = works.folder(wid)
        d = f / RUNS if f is not None else None
        try:
            return sorted(int(p.stem) for p in d.iterdir() if p.suffix == ".json" and p.stem.isascii() and p.stem.isdigit()) if d is not None and d.is_dir() else []
        except OSError:
            return []

    @staticmethod
    def log(wid, **fields):
        """작업 기록(log.jsonl)에 실행 사건 한 줄(시작 · 묶음 · 멈춤 · 끝 · 끊김 — 단계 사건 · 확인 폴링은 적지 않는다)."""
        from app import works
        works.log(wid, LOG_KIND, **fields)


# ---------------------------------------------------------------- 구성 · 구조 반영(걸음 2 — 「구성 맞추기」: spec_워크플로우 ② §17-10 걸음 2)
# 프로젝트 구성 추출 · 구조 반영 · 다시 문서 검토의 재료와 일. 판정 · 편집은 지금 끝점 그대로(…/divisions · read · settings · confirm · plan · apply) — 여기는 꼴만 맞춘다.
_READ = {}   # 문서 id → (rev, 문서에서 읽은 값 | None) — 저장한 값이 없는 문서의 「문서에서 읽기」 는 상태를 셀 때마다 다시 읽지 않는다


def _read_values(got):
    """문서에서 읽은 값(…/divisions/read 의 read) → 정리한 구분 값 | None — 단계나 기관 이름이 읽혔을 때만(자리표시뿐인 빈 양식은 None: 화면 app.js taskReadValues 와 같은 기준)."""
    from app import server
    o = (got or {}).get("orgs") or {}
    if not got or not (got.get("stages") or o.get("lead") or any(o.get("joint") or ())):
        return None
    base = {"stages": [1], "orgs": {"lead": "", "joint": [], "nonprofit": [False]}}
    try:
        return server.PROFILE.norm_values({**base, **got, "orgs": {**base["orgs"], **o}})
    except (ValueError, KeyError, TypeError):
        return None


def div_facts(doc_id):
    """그 문서의 프로젝트 구성 재료 → {input(입력 값 | None), applied(마지막 전체 반영 {values, rev, …} | None), confirmed({values, valid, scope} | None), partial[한 자리만 반영 기록],
    form(양식 이름 | ""), supported, read(저장한 값 · 반영 값이 없을 때 문서에 적힌 값 | None), plan · stale(지금 계획의 요약 · 낡음), hash(입력의 판 | None), hints[추가한 자리의 문단 id]} | None(못 엶).
    값은 서버가 정리한 꼴(norm_values) — 상태 식이 그대로 견준다. 반영 기록(applied)에는 그 반영의 범위(hints · skip — server._division_scope)가 함께 있다(이 변경 전의 기록에는 없다)."""
    from fastapi import HTTPException

    from app import server
    try:
        s = server._sess(doc_id)
        with s.lock:
            v = server._division_view(s)
            rev = s.rev
    except HTTPException:
        return None
    def norm(x):   # 옛 저장본(키가 빠진 값 — 위탁 entrust 없음 …)도 지금 꼴로 — 화면 divCanon 이 같다고 보는 것을 상태 식도 같다고 보게(astra 2026-11-20)
        if not isinstance(x, dict):
            return x
        try:
            return server.PROFILE.norm_values(x)
        except (ValueError, KeyError, TypeError):
            return x
    rec = lambda r: {**r, "values": norm(r.get("values"))} if isinstance(r, dict) else r  # noqa: E731
    settings, applied = v.get("settings"), rec(v.get("applied"))
    from app import division_model
    out = {"input": norm((settings or {}).get("values")), "applied": applied, "confirmed": rec(v.get("confirmed")), "partial": [rec(p) for p in v.get("partial") or ()],
           "form": (v.get("profile") or {}).get("form") or "", "supported": bool((v.get("profile") or {}).get("supported")), "rev": rev, "read": None,
           "sharing": v.get("projectSharing"),   # 확정이 놓이는 곳(프로젝트 · 이 문서 — 화면 divConfirmWhere)
           "plan": v.get("plan"), "stale": bool(v.get("stale")),   # 지금 계획의 요약({planId, baseRev, only, skip, summary …} | None — 서버 메모리) · 계획 뒤 문서가 바뀜(문서 하나의 「변경 계획 보기」 줄이 읽는다 — 상태 조회는 계획을 세우지 않는다)
           "hash": division_model.settings_hash(settings) if settings is not None else None,   # 입력의 판(설정 해시 — 당해 차년도까지): 실행이 울타리 안에서 확정을 확인한 그 입력으로만 계획하게(division_plan 의 expect)
           "hints": sorted(h["para"] for h in v.get("hints") or () if isinstance(h, dict) and h.get("para"))}   # 추가한 자리(문단 id 들) — 반영 기록의 hints 와 견준다(그 뒤 바뀌었으면 옛 확인은 지금 후보의 것이 아니다: workflow_units.fit_done)
    if out["input"] is None and not applied and out["form"]:
        hit = _READ.get(doc_id)
        if hit is None or hit[0] != rev:
            got = config_read(doc_id)
            hit = _READ[doc_id] = (rev, got.data if got.ok else None)
        out["read"] = hit[1]
    return out


def config_read(doc_id):
    """문서에 적힌 단계 · 차년도 · 기관을 읽는다(문서 · 저장은 그대로 — GET …/divisions/read) → Outcome(data = 정리한 값 | None — 읽을 수 있는 값이 없음)."""
    from app import server
    got = _run(server.divisions_read, doc_id, on409="blocked")
    return Outcome(got.code, got.text, _read_values(got.data.get("read")) if got.ok and isinstance(got.data, dict) else None)


def config_save(doc_id, values, if_empty=False):
    """그 문서의 입력 값(프로젝트 구성)을 저장 — 문서는 그대로(PUT …/divisions/settings). 공유 중이면 프로젝트의 입력이 바뀐다.
    if_empty = **입력이 아직 비어 있을 때만** 저장한다(끝점의 ifEmpty — 문서 · 프로젝트 저장 쪽이 한 잠금 안에서 본다): 그 사이 입력이 생겼으면 덮지 않고 `nothing`(문서에서 읽은 값을 채우는 「구성 읽기」)."""
    from app import server
    got = _run(server.divisions_settings, doc_id, {"values": values, **({"ifEmpty": True} if if_empty else {})}, on409="blocked")
    if if_empty and got.ok and isinstance(got.data, dict) and got.data.get("saved") is False:
        return Outcome("nothing", "입력 값이 이미 있습니다 — 읽은 값으로 바꾸지 않았습니다", got.data)
    return got


def config_confirm(doc_id, values=None):
    """프로젝트 구성 추출 — values 가 있으면 먼저 그 값을 입력으로 저장(POST …/divisions/confirm). 문서는 안 바뀐다. 409 = 프로젝트 저장 파일 손상(blocked)."""
    from app import server
    return _run(server.divisions_confirm, doc_id, {"values": values} if values else {}, on409="blocked")


def division_plan(doc_id, values, skip=(), expect=None):
    """구조 반영 계획(POST …/divisions/plan — 작업용 사본에서 모의 실행: 문서는 그대로) → Outcome(data = 계획 {planId, baseRev, settingsHash, summary, autoStops, autoStopsKind, stale, …}).
    values 는 입력 값으로도 저장된다(그 끝점이 지금처럼) — **None 이면 값을 싣지 않는다**(저장된 입력 그대로 계획 — 앞에서 읽은 값으로 최신 공유 입력을 덮지 않게).
    expect = 입력의 판(div_facts 의 hash) — 지금 입력이 그 판이 아니면 계획하지 않고 stale(끝점의 expectSettings). 지원하지 않는 양식 · 값 오류 = invalid."""
    from app import server
    body = {"skip": [x for x in skip or () if isinstance(x, str)], **({"values": values} if values is not None else {}), **({"expectSettings": expect} if expect else {})}
    return _run(server.divisions_plan, doc_id, body, on409="stale")


def division_apply(doc_id, plan_id, expect_rev, adopt=False):
    """[문서 바뀜] 그 계획대로 구조 반영(POST …/divisions/apply — 편집 하나 · 실행 취소 1 · 표준 검사에 걸리면 전부 되돌림) → Outcome:
    ok(data = 반영 결과 · rev) · nothing(바꿀 것이 없는 계획 — data.summary 로 「이미 맞음」 과 「못 맞춤」 을 가른다) · stale(409 — 계획 뒤 문서가 바뀜 · 계획이 없음) · rejected(422 — 표준 검사로 되돌림).
    adopt = 바꿀 것이 없는 문서 전체 계획이 「구조가 이미 이 값에 맞음」 이면 그 확인을 반영 기록으로 남긴다(data.adopted — 끝남을 문서의 기록에서 다시 세려고: ② §18-13)."""
    from app import server
    got = _run(server.divisions_apply, doc_id, {"planId": plan_id, "expectRev": expect_rev, **({"adopt": True} if adopt else {})}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "할 일이 없습니다 — 이미 그 값에 맞습니다", got.data, got.data.get("rev"))
    return Outcome(got.code, got.text, got.data, (got.data or {}).get("rev") if isinstance(got.data, dict) else None)


def division_adopt(doc_id, values=None):
    """구조 확인(POST …/divisions/adopt — 문서 안 바뀜): 한 번도 반영한 적 없는 문서의 구조가 이미 값에 맞으면 반영 기록을 적는다 → Outcome(data = {adopted, why(applied · changes · unresolved · named · noCandidates | None), summary, applied, rev, named?(why 가 named 일 때 — 구분 값에 없는 기관 이름이 적힌 자리 수)}).
    409 = 확인하는 동안 문서나 값이 바뀜(stale). 취합의 「프로젝트 구성 반영」 이 계획 앞에 먼저 부른다(구조를 맞춘 프레임을 새로 올린 문서 — 울타리 없이)."""
    from app import server
    return _run(server.divisions_adopt, doc_id, {"values": values} if values else {}, on409="stale")


# ---------------------------------------------------------------- 자리 연결 · 넣기 · 정리(걸음 3 — 이관형 3 · 4단계: spec_워크플로우 ② §18-12 ② · ③) — 끝점은 app/merge_api.py · 문서 id = 목적 문서
def fill_facts(target):
    """「내용 넣기 · 문서 정리」 줄의 재료(merge_api.fill_summary — 문서 안 바뀜 · 계획을 세우지 않음) | None(문서를 못 엶)."""
    from app import merge_api
    got = merge_api.fill_summary(target)
    return None if "links" not in got else got


def fill_ver(target):
    """지금 입력의 판(16자 — 두 문서의 차례 · 분석 · 연결 · 표 짝 · 표 대응 · 빈 자리) | None — 유료 호출의 시도를 (줄 · 문서 쌍 · 판)에 묶는다(② §18-4 「한 번」)."""
    from app import merge_api
    return merge_api.inputs_now(target)


def links(target):
    """연결 목록(GET …/merge-links — 사람이 고친 것 · 저장된 짝 그대로) → Outcome(data = 그 몸통)."""
    from app import merge_api
    return _run(merge_api.merge_get, target)


def links_llm(target):
    """자리 연결 LLM 검토(동기 · 유료 · 수십 초 — POST …/merge-links/llm) → Outcome(data = 다시 읽은 연결 목록). 409 = 막는 까닭이 생김(blocked)."""
    from app import merge_api
    return _run(merge_api.merge_links_llm, target, on409="blocked")


def fill_plan(target):
    """넣기 계획(문서 안 바뀜 — POST …/merge-links/plan · 옛 계획은 버린다) → Outcome(data = 계획 보기 {planId, todo, body, tables, fixed, maps, gaps …})."""
    from app import merge_api
    return _run(merge_api.merge_plan, target, on409="blocked")


def fill_gaps(target):
    """빈 자리 검토(동기 · 유료 — POST …/merge-links/gaps · 이미 답이 있는 자리는 다시 안 물음) → Outcome(data = {asked, found, tables, slots, …})."""
    from app import merge_api
    return _run(merge_api.merge_gaps_post, target, {}, on409="blocked")


def fill_maps(target):
    """표 대응(동기 · 유료 — POST …/merge-links/table-map · 쓸 수 있는 대응이 있는 표는 다시 안 물음) → Outcome(data = {asked, mapped, tables[…]})."""
    from app import merge_api
    return _run(merge_api.merge_table_map_post, target, {}, on409="blocked")


def fill_apply(target, plan_id):
    """그 계획을 반영(문서를 바꾼다 — 울타리 안에서 부른다: POST …/merge-links/apply) → Outcome — 409 = 낡은 계획(stale) · 422 = 표준 검사가 되돌림(rejected) · 넣을 것 0 = nothing."""
    from app import merge_api
    got = _run(merge_api.merge_apply, target, {"planId": plan_id}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "넣을 것이 없습니다", got.data, got.data.get("rev"))
    return got


def cleanup_count(target):
    """지울 양식 안내(GET …/form-cleanup — 문서 안 바뀜) → Outcome(data = {counts{total, …}, patterns[{key, name}], rev, …})."""
    from app import merge_api
    return _run(merge_api.form_cleanup_get, target)


def cleanup(target, rev):
    """양식 안내를 한 번에 지운다(문서를 바꾼다 — 울타리 안에서 · 지우기 전에 작성 지침 저장: 못 하면 지우지 않음) → Outcome — 409 = 센 뒤 문서가 바뀜(stale) · 지울 것 없음 = nothing."""
    from app import merge_api
    got = _run(merge_api.form_cleanup_post, target, {"expectRev": rev}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "지울 안내가 없습니다", got.data, got.data.get("rev"))
    return got


# ---------------------------------------------------------------- 「문서 정리」 의 조립 도구(spec_워크플로우 ② §18-23) — 지침 보정 = app/guide_fix_api.py · 빈 구역 지우기 = app/zone_prune_api.py ·
# 넣은 뒤 템플릿 · 서식 정리 = app/merge_retidy_api.py(spec_병합 ② §5-9) · 캡션 맞추기 = app/caption_tpl_api.py(unify_*) · 문서 id = 그 줄이 고른 문서
def guide_fix_facts(doc_id):
    """지침 보정 줄의 재료(문서 안 바뀜 · LLM 안 부름) → {guides{headings, tables, total}, saved, plan | None, applied | None, fill, why} | {error}."""
    from app import guide_fix_api
    try:
        return guide_fix_api.facts(doc_id)
    except Exception as e:  # noqa: BLE001 — 재료를 못 읽음은 상태 식이 「못 읽음」 으로 보인다
        log.exception("[워크플로우 실행] 지침 보정 재료를 읽지 못했습니다")
        return {"error": f"{type(e).__name__}: {e}", "guides": {}, "why": ""}


def guide_fix_ask(doc_id):
    """작성 지침에 따라 LLM 에 묻는다(동기 · 유료 · 수십 초 — 문서 안 바뀜: POST …/guide-fix/ask) → Outcome(data = {planId, fixes, left, rejected, units, asked} | {nothing, why, planId}). 503 = LLM 이 답을 못 냄."""
    from app import guide_fix_api
    return _run(guide_fix_api.guide_fix_ask, doc_id, on409="blocked")


def guide_fix_apply(doc_id, plan_id):
    """그 계획의 고침을 반영(문서를 바꾼다 — 울타리 안에서: POST …/guide-fix/apply) → Outcome — 409 = 지금 계획이 아님(stale) · 422 = 표준 검사가 되돌림(rejected) · 고칠 것 없음 = nothing(반영 기록은 남음)."""
    from app import guide_fix_api
    got = _run(guide_fix_api.guide_fix_apply, doc_id, {"planId": plan_id}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "고칠 것이 없습니다", got.data, got.data.get("rev"))
    return got


def zone_prune_count(doc_id):
    """지울 빈 구역의 수(문서 안 바뀜) → Outcome(data = {rev, counts{items, blocks, rows, cols, kept}, kept, reasons[], why})."""
    from app import zone_prune_api
    return _run(zone_prune_api.count, doc_id)


def zone_prune(doc_id, rev):
    """빈 구역을 한 번에 지운다(문서를 바꾼다 — 울타리 안에서: POST …/zone-prune) → Outcome — 409 = 센 뒤 문서가 바뀜(stale) · 지울 것 없음 = nothing."""
    from app import zone_prune_api
    got = _run(zone_prune_api.zone_prune_post, doc_id, {"expectRev": rev}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "지울 빈 구역이 없습니다", got.data, got.data.get("rev"))
    return got


def cap_unify_view(doc_id):
    """캡션 맞추기 줄의 재료 · 고르기(문서 안 바뀜 — spec_hwpx_웹편집 ② §8-10 「모든 캡션을 한 꼴로」) → Outcome(data = caption_tpl_api.unify_view —
    {rev, form(쓸 꼴), chosen(묶음에 고른 꼴 | None), name, why, rep, forms[], counts{titles, change, full, style, frozen, cross, others}, …})."""
    from app import caption_tpl_api
    return _run(caption_tpl_api.unify_view, doc_id)


def cap_unify(doc_id, rev):
    """모든 제목 캡션을 고른 꼴의 대표 서식으로(문서를 바꾼다 — 울타리 안에서: POST …/captions/unify) → Outcome — 409 = 센 뒤 문서가 바뀜 · 고른 꼴이 문서에 없음(stale) ·
    422 = 표준 검사가 되돌림(rejected) · 맞출 것 없음 = nothing."""
    from app import caption_tpl_api
    got = _run(caption_tpl_api.unify_post, doc_id, {"expectRev": rev}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "맞출 캡션이 없습니다", got.data, got.data.get("rev"))
    return got


def line_tidy_facts(doc_id):
    """줄 정리 줄의 재료(문서 안 바뀜 · 한글 안 부름 — spec_줄정리 ② §7) → {why, rev, fill, rules, rulesText, plan | None, applied | None} | {error}."""
    from app import line_tidy_api
    try:
        return line_tidy_api.facts(doc_id)
    except Exception as e:  # noqa: BLE001 — 재료를 못 읽음은 상태 식이 「못 읽음」 으로 보인다
        log.exception("[워크플로우 실행] 줄 정리 재료를 읽지 못했습니다")
        return {"error": f"{type(e).__name__}: {e}", "why": ""}


def line_tidy_plan(doc_id):
    """한글로 줄을 재고 고친 사본을 다시 재어 장평을 찾는다(동기 · 수십 초 · 문서 안 바뀜: POST …/line-tidy/plan) → Outcome(data = {planId, rev, items, left, counts, rounds, seconds, nothing?}).
    409 = 한글 없음 · 조판한 사본이 문서와 안 맞음(blocked) · 503 = 한글이 조판하지 못함(error)."""
    from app import line_tidy_api
    return _run(line_tidy_api.line_tidy_plan, doc_id, on409="blocked")


def line_tidy_apply(doc_id, plan_id):
    """그 계획의 장평을 반영(문서를 바꾼다 — 울타리 안에서: POST …/line-tidy/apply) → Outcome — 409 = 지금 계획이 아님 · 잰 뒤 문서가 바뀜(stale) · 422 = 표준 검사가 되돌림(rejected) ·
    고칠 것 없음 = nothing(반영 기록은 남음)."""
    from app import line_tidy_api
    got = _run(line_tidy_api.line_tidy_apply, doc_id, {"planId": plan_id}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "고칠 갈림이 없습니다", got.data, got.data.get("rev"))
    return got


def cap_form_set(doc_id, form):
    """그 문서가 든 묶음의 「캡션 맞추기」 꼴을 적는다(워크플로우 옵션 — 문서 안 바뀜 · None = 줄이 가장 많은 꼴) → Outcome(data = 그 문서의 다시 읽은 보기). 400 = invalid · 409 = blocked."""
    from app import caption_tpl_api, task_options, works
    w = works.work(doc_id)
    if w is None:
        return Outcome("missing", "그런 작업이 없습니다")
    try:
        task_options.flow_caption(w, form)
    except task_options.Broken as e:
        return Outcome("blocked", str(e))
    except ValueError as e:
        return Outcome("invalid", str(e))
    return _run(caption_tpl_api.unify_view, doc_id)


def retidy_facts(doc_id):
    """넣은 뒤 템플릿 · 서식 정리 줄의 재료(spec_병합 ② §5-9 — 문서 안 바뀜 · 분석 안 돌림) → {why, fill, applied{at, fill, counts} | None, inserted} | {error}."""
    from app import merge_retidy_api
    try:
        return merge_retidy_api.facts(doc_id)
    except Exception as e:  # noqa: BLE001 — 재료를 못 읽음은 상태 식이 「못 읽음」 으로 보인다
        log.exception("[워크플로우 실행] 넣은 뒤 정리 재료를 읽지 못했습니다")
        return {"error": f"{type(e).__name__}: {e}", "why": ""}


def retidy(doc_id):
    """넣은 줄을 목적 문서의 템플릿 · 서식으로(문서를 바꾼다 — 울타리 안에서: POST …/merge-retidy · 헤딩을 다시 분석해야 하면 그 안에서 몇 초) → Outcome —
    409 = 그 사이 문서가 바뀜 · 다른 헤딩 작업이 돎(stale) · 422 = 표준 검사가 되돌림(rejected) · 맞출 것 없음 = nothing(기록은 남음)."""
    from app import merge_retidy_api
    got = _run(merge_retidy_api.retidy_post, doc_id, {}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", got.data.get("why") or "맞출 줄이 없습니다", got.data, got.data.get("rev"))
    return got


# ---------------------------------------------------------------- 사람이 하는 일(갈래 C — spec_워크플로우 ② §18-7 · §18-12 ⑦) — 확인 기록은 app/flow_hands.py · 「했음」 끝점은 app/flow_hands_api.py
def hand_ver(task, line_key):
    """그 줄의 판 — 정의의 지문(workflow_state.sig) + 줄 key · 이름 · 사람에게 보일 글(등록부 줄의 does)의 sha1 앞 10자. 글을 고치면 판이 바뀌어 앞의 「했음」 은 무효다."""
    import hashlib
    import json

    from app import workflow_state
    step = next((s for g in task.get("stages") or () for s in g["steps"] if s["key"] == line_key), None) or {}
    core = [workflow_state.sig(task), line_key, step.get("name") or "", step.get("does") or ""]
    return hashlib.sha1(json.dumps(core, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]


def hand_done(target_id, line_key, ver):
    """그 묶음의 목적 문서에 그 줄이 그 판으로 「했음」 으로 적혀 있나."""
    from app import flow_hands
    return flow_hands.done(target_id, line_key, ver)


# ---------------------------------------------------------------- 문서 하나의 헤딩 추출 · 조정 · 표(걸음 6 의 2 · 3단계 — spec_워크플로우 ② §18-13 갈래 「나」) — 끝점은 app/analysis_api.py · tpl_agent_api.py · server.headings_start
_STD = {}   # 문서 id → (읽은 때, 문서 차례, 분석 상태) — 상태 조회가 잇달아 올 때 서식 갈래 · 자리 셈을 되풀이하지 않게 잠깐 든다(화면도 도는 동안 2초마다 읽는다)
STD_KEEP = 2.0


def analysis(doc_id, fresh=True):
    """분석 상태(GET …/analysis — 문서 이름 줄 · 진행표와 같은 값: 헤딩 · 템플릿 · 서식 · 표의 스크립트 · LLM · 반영, llmPlan, busy) | None(못 엶 · 없는 문서).
    fresh False = 방금(STD_KEEP 초 안) 읽은 것이 있고 문서 차례가 같으면 그것(상태 조회용 — 실행의 판단은 늘 새로 읽는다: 화면에 보이는 「끝남」 을 성공 조건으로 쓰지 않는다)."""
    from fastapi import HTTPException

    from app import analysis_api, server
    now = time.time()
    if not fresh:
        hit, s = _STD.get(doc_id), server.DOCS.get(doc_id)
        if hit is not None and s is not None and now - hit[0] <= STD_KEEP and hit[1] == s.rev:
            return hit[2]
    try:
        got = analysis_api.analysis_get(doc_id)
    except HTTPException:
        _STD.pop(doc_id, None)
        return None
    _STD[doc_id] = (now, got.get("rev"), got)
    if len(_STD) > 64:
        for k in [k for k, v in _STD.items() if now - v[0] > STD_KEEP]:
            _STD.pop(k, None)
    return got


def start_formats(doc_id, skill=None):
    """서식 정리 계획만 받기(배경 · 유료 — 계획이 없거나 옛것인 템플릿만: POST …/analysis/llm {only: "formats"}). 문서는 안 바뀐다. 도는 중이면 busy."""
    from app import analysis_api
    return _run(analysis_api.analysis_llm_start, doc_id, {"only": "formats", **({"skill": skill} if skill else {})})


def start_tables_llm(doc_id):
    """표 판정(LLM)을 시작(배경 · 유료 — POST …/headings {stage: 3, llm: true}). 문서는 안 바뀐다. 도는 중이면 busy."""
    from app import server
    return _run(server.headings_start, doc_id, {"stage": 3, "llm": True})


def graph_key(doc_id):
    """지금 헤딩 그래프(2단계 결과)의 표시 [실행 번호, 만든 때] | None(그래프 없음 · 못 엶) — 분석 상태 헤딩 항목의 run · at 과 같은 값(개요 오버레이의 run 도 이것)."""
    from fastapi import HTTPException

    from app import heading_runs, server
    try:
        s = server._sess(doc_id)
    except HTTPException:
        return None
    g = heading_runs.graph(s) if s.fmt == "hwpx" else None
    meta = (g or {}).get("meta") or {}
    return [meta.get("run"), meta.get("at")] if g is not None else None


def adjust_apply(doc_id, rev, plans=None, graph=None):
    """[문서 바뀜] 조정 「모두 반영」(POST …/outline/agent/apply — 받아 둔 서식 정리 계획 · 확실한 종속 · 자리 맞춤을 트랜잭션 하나로 · 실행 취소 1) → Outcome:
    ok(data = 반영 결과 {templates, changed, placed, left, merged …}) · nothing(반영할 것이 없음 — 409 NO_PLANS · 바꿀 줄이 없는 계획) · stale(409 — 그 사이 문서 · 계획이 바뀜) ·
    blocked(409 — 헤딩 그래프 없음) · rejected(422 — 표준 검사가 되돌림). rev = 계획을 본 문서 차례 · plans = 본 계획의 표시 {템플릿 id: at}(그 계획들만 · 그대로일 때만 —
    **빈 {} 도 그대로 보낸다**: 「계획은 반영하지 않고 확실한 종속 · 자리 맞춤만」 이다. 안 보내면 끝점이 그 사이 도착한 계획까지 고른다) ·
    graph = 판정을 본 헤딩 그래프의 표시(graph_key — 분석 상태 헤딩 항목의 [run, at]): 지금 그래프가 그것이 아니면 반영하지 않고 stale(그 사이 헤딩을 다시 뽑았다 — 판정 전의 그래프 위에 반영하지 않게)."""
    from app import tpl_agent_api
    if graph is not None and graph_key(doc_id) != list(graph):
        return Outcome("stale", "헤딩 그래프가 그 사이에 바뀌었습니다 — 판정을 본 그래프가 아닙니다")
    got = _run(tpl_agent_api.apply_plans, doc_id, {"rev": rev, **({"plans": plans} if plans is not None else {})}, on409="stale")
    detail = (got.data or {}).get("detail") if isinstance(got.data, dict) else None
    if got.code == "stale" and detail == tpl_agent_api.NO_PLANS:
        return Outcome("nothing", got.text, got.data)
    if got.code == "stale" and isinstance(detail, str) and detail.startswith("헤딩 추출 2단계"):
        return Outcome("blocked", got.text, got.data)
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "바꿀 줄이 없습니다", got.data, got.data.get("rev"))
    return got


# ---------------------------------------------------------------- 취합(걸음 5 — spec_워크플로우 ② §18-13 갈래 「다」) — 끝점은 app/merge_gather_api.py · 문서 id = 목적 문서(취합본) · part = 원본 문서(기관 문서)
def reason(got):
    """Outcome 의 까닭 열쇠(취합 끝점의 409 `detail.reason` — noHeadings · noMatch · frameDiffers · staleHeadings · stalePlan · noLlm …) | ""."""
    d = (got.data or {}).get("detail") if isinstance(got.data, dict) else None
    return str(d.get("reason") or "") if isinstance(d, dict) else ""


def gather(target):
    """취합 상태(GET …/gather — {frame{frameId, at, stale} | None, reasons, orgs, parts[{work, name, orgs, counts, todo, llm, reasons, state}], version}) | None(못 엶).
    모든 기관 문서의 판정을 다시 본다(읽어 둔 것이 지금 것이면 그 문서를 열지 않는다) — 상태 조회용. 실행 중의 처리 함수는 그 문서 하나만 읽는 `gather_row` 를 쓴다."""
    from fastapi import HTTPException

    from app import merge_gather_api
    try:
        return merge_gather_api.gather_get(target)
    except HTTPException:
        return None


def gather_row(target, part):
    """그 기관 문서 한 줄(취합 상태의 parts[] 한 줄 — 그 문서 하나만 판정) | None(취합에서 뺀 문서 · 못 엶)."""
    from fastapi import HTTPException

    from app import merge_gather_api as GA
    try:
        s, G, frame, stale = GA._ctx(target)
    except HTTPException:
        return None
    if part not in G["parts"]:
        return None
    return GA._part_view(s, G, frame, stale, part)[0]


def gather_frame(target):
    """배포 기준본 만들기(POST …/gather/frame — 문서 안 바뀜) → Outcome(data = 취합 상태). 409 = 만들 수 없는 까닭(blocked — reason(): unsupportedForm · noValues · notApplied · staleHeadings)."""
    from app import merge_gather_api
    return _run(merge_gather_api.gather_frame, target, on409="blocked")


def gather_auto(target, part):
    """반영할 기관 자동 지정(POST …/parts/{part}/auto — 파일 이름 → 추천 · 이미 지정돼 있으면 안 바꾼다) → Outcome(data = 취합 상태 + auto{org, by, why})."""
    from app import merge_gather_api
    return _run(merge_gather_api.gather_part_auto, target, part, on409="blocked")


def gather_links(target, part, fresh=False):
    """자리 연결 · 기관 작성 내용 판정(GET …/links · fresh = 다시 맞춤 POST) → Outcome(data = {part, counts, todo, items, llm, reasons}). 409 = 못 내는 까닭(blocked — reason())."""
    from app import merge_gather_api
    return _run(merge_gather_api.gather_links_post if fresh else merge_gather_api.gather_links, target, part, on409="blocked")


def gather_llm(target, part):
    """기관 작성 내용의 LLM 검토(동기 · 유료 · 수십 초 — POST …/parts/{part}/llm) → Outcome(data = 다시 읽은 연결 목록). 409 = 막는 까닭 · LLM 꺼짐(blocked — reason() noLlm)."""
    from app import merge_gather_api
    return _run(merge_gather_api.gather_llm, target, part, on409="blocked")


def gather_plan(target, part):
    """넣기 계획(POST …/parts/{part}/plan — 문서 안 바뀜) → Outcome(data = {planId, todo, counts, items …}). 409 = 못 내는 까닭(blocked)."""
    from app import merge_gather_api
    return _run(merge_gather_api.gather_plan, target, part, on409="blocked")


def gather_apply(target, part, plan_id):
    """[문서 바뀜] 그 계획을 취합본에 반영(POST …/parts/{part}/apply — 울타리 안에서 부른다 · 편집 하나 · 실행 취소 1) → Outcome: ok(data = {counts, calc, dropped, skipped}) ·
    nothing(넣을 것 0) · stale(409 stalePlan — 계획 뒤 문서 · 설정이 바뀜) · rejected(422 — 표준 검사가 되돌림)."""
    from app import merge_gather_api
    got = _run(merge_gather_api.gather_apply, target, part, {"planId": plan_id}, on409="stale")
    if got.ok and isinstance(got.data, dict) and got.data.get("nothing"):
        return Outcome("nothing", "넣을 것이 없습니다", got.data, got.data.get("rev"))
    return got
