"""단위문서 TASK 의 문 — 워크플로우 실행 층이 문서의 일을 시키는 하나뿐인 길(spec_워크플로우 ② §17-3 「단위문서 TASK 의 문」 · 단위의 뜻은 ② §18-2 「실행 단위」).

워크플로우 실행 층(app/workflow_units.py · workflow_state.py · workflow_exec.py · workflow_exec_api.py)은 `app.server` · `*_api` · `works` · `llm` · `heading_runs` · `task_options` 를 가져오지 않는다 —
그 이름을 아는 파일은 **이것 하나**다(함수 안에서 가져온다 — server 가 그 층을 붙이므로 순환 import 를 피한다 · 나중에 다른 프로세스로 뗄 때 바꿀 파일도 이것 하나: ② §17-10 「떼기」).
- **문서 id 만 받는다**(세션을 넘기거나 쥐지 않는다 — 밀려남 · 다시 열기를 견딘다). 일을 시키는 함수는 하나의 꼴 `Outcome{code, text, data, rev}` 를 돌려준다:
  `ok` · `nothing`(할 일 없음) · `busy`(헤딩 작업 자리가 참) · `stale`(409 — 계획 · 목록을 만든 뒤 문서가 바뀜) · `blocked`(409 — 전제 없음) · `rejected`(422 — 되돌리고 **돌려준** 응답) ·
  `invalid`(400) · `missing`(404 — 세션이 밀려남 포함) · `error`(그 밖 — 서버 로그). 409 가 셋 가운데 무엇인지는 부르는 함수가 정한다(`on409`).
- 판정 · 편집 · 프롬프트 · 저장은 지금 끝점 함수 그대로다 — 여기는 응답 꼴만 맞춘다. 끝점 함수는 인자를 모두 넘겨 부른다(`Body` 기본값을 타지 않게) · `get_doc` 은 부르지 않는다(작업에 종류 짐작을 저장하는 부작용).
- 지금 있는 것(걸음 1 — 「문서 검토」): 읽기 `work` · `pair` · `facts` · `llm_ok` · `skips` / 배경 일 `start_heads` · `start_llm` · `job` · `stop_llm` / 동기 일 `guides_keep` · `skip_set` / 저장 `store`(실행 기록 · 기록 줄)."""
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
    목적 종류가 없는 워크플로우(문서 하나)는 이 문서가 목적이고 원본은 없다."""
    from app import custom_tasks, merge_api, projects, works
    w = works.work(wid)
    if w is None:
        return None
    task = w.get("task") if isinstance(w.get("task"), dict) else {}
    job, kind = task.get("job") or "", task.get("file") or ""
    scope = list(projects.group_key(task))
    tkind = works.TARGET_FILE.get(job) if job else None
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
    src = merge_api._mate(target["id"], merge_api._store(target["id"]))[1]
    sw = works.work(src) if src else None
    out["source"] = _doc(sw) if sw else None
    return out


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
    return {"id": s.id, "name": s.name, "rev": s.rev, "fmt": s.fmt,
            "heads": {"s2": bool(s2), "s3": bool(s3), "rev2": ((s2 or {}).get("meta") or {}).get("rev"), "rev3": ((s3 or {}).get("meta") or {}).get("rev"), "llm": done(s2) and done(s3),
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
