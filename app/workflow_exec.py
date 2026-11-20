"""워크플로우 실행기 — 정의의 줄을 차례대로 서버에서 돈다(spec_워크플로우 ② §18-4 「차례 실행기」 · 기록 · 잠금 · 끊김은 ② §17-6 · 시작 · 대상 고정 · 멈춤은 ② §17-7).

창을 닫거나 다른 문서를 열어도 「한 번에 진행」 이 끝까지 돌게 한다 — 화면(작업 개요 · 대시보드 · 첫 화면의 대시보드 · 에이전트)은 시작 · 멈춤 · 보기만 한다.
- **문서를 직접 만지지 않는다** — 늘 문(`UNIT` = app/unit_steps.py: `attach` 가 넣는다 · 시험은 가짜 문)을 부른다. 가져오는 앱 코드는 정의(app.workflow · app.custom_tasks) · 단위(app.workflow_units) · 상태(app.workflow_state)뿐.
- **줄마다 처리 함수 하나**(`HANDLERS` — 단위의 key): 할 필요가 있나 · 이번 호출이 약속한 결과를 냈나를 스스로 정해 `done`(끝남) · `nothing`(한 일 없음) · `left`(남김 — 까닭) · `halt`(멈춤 — 까닭)를 돌려준다.
  화면에 보이는 상태(workflow_state.view)는 따로 센다 — 실행기는 그 표시를 성공 판정에 쓰지 않는다(② §18-4).
- 지금 맡는 묶음 = 이관형의 「문서 검토」(준비 `files` · 헤딩 · 표 분석 `heads` · LLM 검증·보완 `headsLlm` — 걸음 1: ② §18-10). 그 밖의 묶음은 화면이 돈다(`server: false`).
- 실행 기록 = 목적 문서 작업 폴더의 `flowruns/<n>.json`(단계 경계마다 통째로 다시 씀 · 저장이 꺼져 있으면 메모리만) + 작업 기록의 `flowRun` 줄. **끝남은 늘 문서마다의 결과로 다시 센다** — 기록은 일어난 일만 적는다.
- 잠금: `RUNS{목적 id: 실행}` · `BUSY{문서 id: 목적 id}` — 실행에 든 문서마다 도는 실행은 하나. 이 잠금(`_LOCK`)을 쥔 채 문을 부르지 않는다(세션 잠금 → 이 잠금 차례 — ② §17-4).
- 끊김: 서버를 켤 때 `BOOT` 를 정한다 — 기록이 `running` 인데 지금 도는 실행이 아니면 읽는 때 `cut` 으로 고쳐 쓴다. **저절로 잇지 않는다**(「이어서」 = 새 실행)."""
import contextlib
import os
import threading
import time
import uuid

from app import workflow_state as S
from app import workflow_units as U

BOOT = uuid.uuid4().hex[:8]
UNIT = None                      # 문(app/unit_steps.py) — attach(app/workflow_exec_api.py)가 넣는다
_LOCK = threading.RLock()
RUNS = {}                        # 목적 문서 id → 도는 실행(Run)
BUSY = {}                        # 실행에 든 문서 id → 목적 문서 id
LAST = {}                        # 목적 문서 id → 마지막 실행 기록(메모리 — 작업 저장이 꺼져 있을 때의 원본 · 번호 세기)
WAIT = {"poll": 1.0, "heads": 30 * 60, "llm": 90 * 60}   # 기다림(초) — 상한은 화면 실행과 같다(분석 30분 · LLM 90분). 시험이 줄인다
STEPS_MAX, TEXT_MAX, SKIP_MAX = 300, 240, 5000
STATUS = ("running", "done", "left", "halted", "stopped", "failed", "cut")
BUSY_TEXT = "워크플로우 「한 번에 진행」 이 도는 중입니다 — 끝나거나 멈춘 뒤에 하세요"
# 울타리(② §17-8 — 문서를 바꾸는 줄): 알림 → 화면들의 고치던 글 보고 → 울타리(그 문서의 사람 편집 409 · 실행 스레드만 지남) → 몸 → 내림. 사전은 잠금 없이 한 번 읽는다(편집 입구가 세션 잠금 안에서 묻는다 — 교착 없음)
FENCE = {}                       # 문서 id → {target, n, thread(실행 스레드 ident)}
NOTICE = {}                      # 문서 id → {key, since} — 그 문서를 연 화면은 고치던 글을 보내고 읽기 전용 띠를 보인다(확인 폴링이 읽는다)
REPORTS = {}                     # 문서 id → {화면 id: (고치던 글 수, 보고 시각, 차례 번호)} — 확인 폴링(GET …/flow/live?screen=&dirty=)이 싣는다
_SEQ = __import__("itertools").count(1)   # 보고 · 알림의 차례 번호(잠금 안에서 뽑는다)
FENCE_WAIT = {"settle": 4.0, "limit": 10.0, "alive": 8.0, "poll": 0.2, "keep": 60.0}   # 초 — settle 안에 보고한 화면이 모두 0 이면 · limit 넘으면 멈춤 · alive = 알림 전에 보고하던 화면(기다릴 화면) · keep = 보고를 버리는 때. 시험이 줄인다
FENCE_TEXT = "워크플로우가 이 문서를 바꾸는 중입니다 — 끝나면 다시 하세요"
DIRTY_TEXT = "그 문서를 연 화면에 서버에 반영하지 못한 글이 있습니다 — 「고친 문단」 탭에서 다시 반영한 뒤 「이어서」"


def client_only():
    """끄는 스위치 — env NFM_FLOW_EXEC=client 면 모든 묶음을 화면이 돈다(되돌리기 쉬운 길: ② §17-5)."""
    return os.environ.get("NFM_FLOW_EXEC", "").strip().lower() == "client"


def configure(unit):
    global UNIT
    UNIT = unit


def _clip(text):
    s = " ".join(str(text or "").split())
    return s if len(s) <= TEXT_MAX else s[:TEXT_MAX - 1] + "…"


class Refuse(Exception):
    """시작하지 않음(끝점 409 — reason · 화면에 그대로 보이는 message · 이미 도는 실행이면 run)."""

    def __init__(self, reason, message, run=None):
        super().__init__(message)
        self.reason, self.message, self.run = reason, message, run


class _Halt(Exception):
    """줄의 처리 함수가 실행을 멈춘다(사람이 봐야 함) — code · text."""

    def __init__(self, code, text):
        super().__init__(text)
        self.code, self.text = code, text


class _Stop(Exception):
    """멈춤 요청을 받았다 — 지금 하던 일이 끝난 자리."""


# ---------------------------------------------------------------- 상태(화면에 내는 것 — GET …/flow)
MATERIALS = []   # 재료 덧붙이기(task, pair, facts) — 묶음마다의 재료(구성 · 넣기 …)를 그 묶음을 서버가 맡을 때만 읽는다. 세션마다 맡은 묶음의 절 끝에서 MATERIALS.append(fn)


def _materials(pair, task):
    """정의가 읽어야 하는 역할의 문서마다 재료 → {문서 id: facts | None}(안 닿는 문서는 열지 않는다)."""
    facts = {}
    for role in S.need(task):
        d = pair.get(role)
        if d:
            facts[d["id"]] = UNIT.facts(d["id"])
    for fn in MATERIALS:
        fn(task, pair, facts)
    return facts


def _skips(pair, wid):
    return UNIT.skips(((pair.get("target") or {}).get("id")) or wid)


def status_of(wid):
    """그 문서가 든 묶음의 지금 상태(② §17-5 `GET …/flow`) → {…workflow_state.view, run(도는 실행 요약 | null), last(지난 실행 요약 | null)} | None(그런 작업 없음).
    워크플로우가 없거나 모르는 키면 `{job, stages: [], why}`. 끄는 스위치면 모든 묶음 `server: false`."""
    pair = UNIT.pair(wid)
    if pair is None:
        return None
    task = S.definition(pair["job"])
    if task is None:
        return {"job": pair["job"], "sig": "", "docs": {"target": pair.get("target"), "source": pair.get("source")}, "ready": False, "why": "이 문서에는 워크플로우가 없습니다" if not pair["job"] else "모르는 워크플로우입니다",
                "stages": [], "run": None, "last": None}
    target = (pair.get("target") or {}).get("id")
    run = RUNS.get(target) if target else None
    off = client_only()
    view = S.view(task, pair, {} if off else _materials(pair, task), llm=None if off else UNIT.llm_ok(), skip=[] if off else _skips(pair, wid),
                  running=run.now() if run is not None else None)
    if off:
        for g in view["stages"]:
            g.update(server=False, steps=None, can=False, why="", total=0, done=0, left=0, paid=[])
    if run is not None:
        for g in view["stages"]:
            if g["server"] and (g["can"] or not g["why"]):
                g["why"] = "지금 진행 중인 작업이 끝나면 쓸 수 있습니다"
            g["can"] = False
    view["run"] = run.summary() if run is not None else None
    view["last"] = _summary(last(target)) if target and run is None else None
    return view


# ---------------------------------------------------------------- 실행 기록
def _summary(rec):
    """기록 → 화면이 늘 받는 요약(진행 · 끝) | None."""
    if not rec:
        return None
    return {k: rec.get(k) for k in ("n", "status", "stopping", "started", "ended", "now", "range", "origin", "docs", "left", "halt", "end", "cut", "job", "sig")} | {
        "stages": [{k: g.get(k) for k in ("id", "status", "text")} for g in rec.get("stages") or []]}


def _numbers(target):
    got = list(UNIT.store.numbers(target))
    mem = LAST.get(target)
    return sorted(set(got + ([mem["n"]] if mem else [])))


def _cut(target, rec):
    """`running` 으로 남았는데 지금 도는 실행이 아닌 기록 → `cut` 으로 고쳐 쓴다(서버가 다시 켜졌거나 실행 스레드가 죽음) → 고친 기록."""
    if not rec or rec.get("status") != "running":
        return rec
    live = RUNS.get(target)
    if live is not None and live.rec["n"] == rec.get("n") and rec.get("boot") == BOOT:
        return rec
    now = rec.get("now") or {}
    rec = {**rec, "status": "cut", "stopping": False, "ended": time.time(), "now": None,
           "cut": {"why": "서버가 다시 켜져 끊겼습니다" if rec.get("boot") != BOOT else "실행이 끊겼습니다", "at": now.get("key") or ""},
           "end": {"ok": False, "text": f"끊김 — 서버가 다시 켜져 {now.get('note') or '진행 중'}에서 멈췄습니다 · 끝난 단계는 그대로 · 남은 단계는 「한 번에 진행」 으로 잇습니다"}}
    with _LOCK:
        LAST[target] = rec
    UNIT.store.write(target, rec["n"], rec)
    UNIT.store.log(target, event="cut", n=rec["n"], at=rec["cut"]["at"])
    return rec


def record(target, n):
    """실행 기록 하나 | None(끊긴 것이면 고쳐서)."""
    live = RUNS.get(target)
    if live is not None and live.rec["n"] == n:
        return dict(live.rec)
    mem = LAST.get(target)
    rec = mem if mem and mem.get("n") == n else UNIT.store.read(target, n)
    return _cut(target, rec)


def last(target):
    """그 목적 문서의 마지막 실행 기록 | None."""
    ns = _numbers(target)
    return record(target, ns[-1]) if ns else None


def records(target, limit=20):
    """최근 실행 기록의 요약들(새 것부터)."""
    return [x for x in (_summary(record(target, n)) for n in reversed(_numbers(target)[-max(1, min(int(limit), 100)):])) if x]


# ---------------------------------------------------------------- 서버가 묻는 것(② §17-3 「서버가 워크플로우 층에 묻는 셋」)
def busy_text(wid=None, project=None):
    """그 문서(또는 그 프로젝트의 문서)가 도는 실행에 들었으면 거절 글 | ""(바쁨 막이 — 초기화 · 지우기 · 칸 바꾸기 · 새 라운드 · 묶음 초기화 · 프로젝트 이름 바꾸기 · 지우기가 함수 안에서 묻는다).
    잠금 없이 사전을 한 번 읽는다(편집 입구가 세션 잠금 안에서 불러도 교착이 없다)."""
    if wid is not None and wid in BUSY:
        return BUSY_TEXT
    if project:
        for run in list(RUNS.values()):
            if (run.rec.get("scope") or [""])[0] == project:
                return BUSY_TEXT
    return ""


def pinned():
    """도는 실행이 지금 일하는 문서 id 들 — 서버의 `_admit` 이 비우지 않는다(② §17-7 「기다림」)."""
    return {d for run in list(RUNS.values()) for d in run.working}


def fence_why(doc_id):
    """울타리(② §17-8) — 실행이 그 문서를 바꾸는 동안 사람 편집을 거절할 글 | ""(울타리 없음 · 그 실행 스레드). `_bump` 를 부르는 편집 입구가 세션 잠금 안에서 묻는다 —
    잠금 없이 사전을 한 번 읽는다(교착 없음)."""
    f = FENCE.get(doc_id)
    return FENCE_TEXT if f is not None and f["thread"] != threading.get_ident() else ""


def report(doc_id, screen, dirty, ack=""):
    """확인 폴링의 보고 — 그 화면(탭)이 그 문서에서 서버에 아직 반영하지 못한 글 수(보낼 차례 · 보내는 중 · 반영 실패) · ack = 그 화면이 받아 **입력을 막고 고친 글을 보낸** 알림의 key.
    울타리는 그 알림의 key 를 되돌려 준 보고만 「받았음」 으로 센다(알림을 보기 전에 잰 0 을 받았음으로 쓰지 않게 — astra 2026-11-20 P1). 화면 id 가 없으면 적지 않는다(두 화면의 보고가 서로 덮지 않게)."""
    if not screen or not doc_id:
        return
    now = time.time()
    with _LOCK:
        rows = REPORTS.setdefault(doc_id, {})
        rows[str(screen)[:40]] = (max(0, int(dirty or 0)), now, next(_SEQ), str(ack or "")[:80])   # 차례 번호 — 알림 뒤의 보고인지는 시각이 아니라 이것으로 가른다(Windows 의 시계는 15 ms 단위)
        for k in [k for k, row in rows.items() if now - row[1] > FENCE_WAIT["keep"]]:
            rows.pop(k, None)


def notice_of(doc_id):
    """그 문서에 걸린 알림 {key, since, fenced} | None — 확인 폴링이 읽는다(읽기 전용 띠 · 고치던 글 보내기)."""
    n = NOTICE.get(doc_id)
    return {**n, "fenced": doc_id in FENCE} if n else None


def forget(wid):
    """작업 내용 초기화 · 지우기 — 그 문서의 메모리 기록을 버린다(작업 폴더의 것은 초기화가 reset/<n>/ 으로 옮긴다)."""
    with _LOCK:
        LAST.pop(wid, None)


def active():
    """도는 실행 목록(메모리 — 8114 를 다시 켜기 전에 본다)."""
    return [run.summary() for run in list(RUNS.values())]


def live(wid):
    """그 문서가 든 도는 실행의 요약 | None — **메모리만**(세션을 열지 않고 디스크를 읽지 않는다: 확인 폴링)."""
    target = BUSY.get(wid)
    run = RUNS.get(target) if target else None
    return run.summary() if run is not None else None


def last_n(wid):
    """그 문서가 목적 문서인 마지막 실행의 번호 | None — 메모리만. 화면이 실행을 통째로 놓쳤을 때(숨긴 탭) 그 번호가 바뀐 것을 보고 문서를 다시 읽는다."""
    rec = LAST.get(wid)
    return rec.get("n") if rec else None


# ---------------------------------------------------------------- 실행
class Run:
    """도는 실행 하나 — rec = 실행 기록(사전 · 통째로 다시 쓴다) · working = 지금 일하는 문서 id 들."""

    def __init__(self, rec, task, pair, approval):
        self.rec, self.task, self.pair, self.approval = rec, task, pair, approval
        self.working = set()
        self.lock = threading.Lock()

    @property
    def target(self):
        return self.rec["docs"]["target"]["id"]

    def now(self):
        return self.rec.get("now")

    def summary(self):
        with self.lock:
            return _summary(self.rec)

    def save(self):
        with self.lock:
            rec = dict(self.rec, steps=list(self.rec["steps"][-STEPS_MAX:]))
        with _LOCK:
            LAST[self.target] = rec
        UNIT.store.write(self.target, rec["n"], rec)

    def note(self, stage, key, text, doc=None):
        with self.lock:
            self.rec["now"] = {"stage": stage, "key": key, "doc": doc, "note": _clip(text), "t0": time.time()}

    def step(self, stage, key, status, text, doc=None, t0=None):
        with self.lock:
            self.rec["steps"].append({"stage": stage, "key": key, **({"doc": doc} if doc else {}), "status": status, "text": _clip(text), "t0": t0 or time.time(), "t1": time.time()})
            if status == "left":
                self.rec["left"].append({"stage": stage, "key": key, **({"doc": doc} if doc else {}), "what": _clip(text)})
        self.save()

    def stopping(self):
        return bool(self.rec.get("stopping"))

    @contextlib.contextmanager
    def fence(self, doc):
        """울타리(② §17-8) — 문서를 바꾸는 처리 함수는 `with run.fence(문서 id): …` 안에서 문을 부른다. 차례:
        ① 알림(그 문서를 연 화면이 입력을 막고 고친 글을 보낸 뒤 그 알림의 key 를 되돌려 보고한다) → ② 보고를 기다림 — **받았음**(알림 key 를 되돌린 보고)이 모두 0 이고,
        기다릴 화면(알림 전에 보고하던 화면 · 알림 뒤에 보고한 화면)이 다 받았음을 보냈거나, settle 초가 지났고 남은 화면이 알림 뒤로 아무 보고도 없는 화면(닫힌 화면)뿐이면 →
        ③ 마지막 판정과 같은 잠금 안에서 울타리(그 문서의 사람 편집 409 · 이 스레드만 지남) → 몸 → ④ 울타리 · 알림을 내림(화면은 고치던 글이 없으면 다시 읽는다).
        limit 초 안에 안 되면 **문서를 바꾸기 전에** `_Halt("dirty", …)` · 그동안 멈춤을 누르면 `_Stop`. 몸 안의 일은 계획 → 같은 검사 → 반영처럼 짧게(길어야 20초 안팎)."""
        since = time.time()
        key = f"{self.target}:{self.rec['n']}:{next(_SEQ)}"   # 알림마다 다른 key(같은 실행의 둘째 울타리도 새로 받았음을 받는다)
        with _LOCK:
            seq = next(_SEQ)
            NOTICE[doc] = {"key": key, "since": since}
            known = {k for k, row in (REPORTS.get(doc) or {}).items() if since - row[1] <= FENCE_WAIT["alive"]}
        try:
            while True:
                if self.stopping():
                    raise _Stop()
                now = time.time()
                with _LOCK:   # 판정과 울타리 올리기를 한 잠금에서 — 그 사이에 들어온 보고가 판정에서 빠지지 않게
                    rows = dict(REPORTS.get(doc) or {})
                    after = {k for k, row in rows.items() if row[2] > seq}                       # 알림 뒤에 보고한 화면
                    acked = {k: row[0] for k, row in rows.items() if row[2] > seq and row[3] == key}   # 받았음 — 입력을 막고 보낸 뒤의 수
                    pending = (known | after) - set(acked)
                    clean = all(d == 0 for d in acked.values())
                    if clean and (not pending or (now - since >= FENCE_WAIT["settle"] and not (pending & after))):
                        FENCE[doc] = {"target": self.target, "n": self.rec["n"], "thread": threading.get_ident()}
                        break
                if now - since >= FENCE_WAIT["limit"]:
                    raise _Halt("dirty", DIRTY_TEXT)
                time.sleep(FENCE_WAIT["poll"])
            yield
        finally:
            with _LOCK:
                if (FENCE.get(doc) or {}).get("thread") == threading.get_ident():
                    FENCE.pop(doc, None)
                NOTICE.pop(doc, None)

    def guard(self):
        """대상 고정(② §17-7) — 멈춤 요청 · 문서 쌍이 그대로인가(일 하나를 시작할 때마다)."""
        if self.stopping():
            raise _Stop()
        now = UNIT.pair(self.target)
        same = lambda a, b: (a or {}).get("id") == (b or {}).get("id")  # noqa: E731
        if now is None or now["job"] != self.rec["job"] or now["scope"] != self.rec["scope"] or not same(now.get("target"), self.pair.get("target")) or not same(now.get("source"), self.pair.get("source")):
            raise _Halt("moved", "도는 중에 문서 칸(또는 워크플로우 · 프로젝트 · 라운드)이 바뀌어 멈췄습니다 — 다시 누르세요")

    def wait(self, doc, limit, what):
        """그 문서의 헤딩 작업이 끝날 때까지 — 1초마다 읽으며 그 문서를 만진다(밀려나지 않게). → 끝난 작업의 보기 | None(작업 없음). 밀려남 · 시간 초과는 멈춤."""
        t0 = time.time()
        while True:
            got = UNIT.job(doc)
            if got.code == "missing":
                raise _Halt("evicted", "열린 문서가 많아 이 문서가 메모리에서 밀려났습니다 — 「한 번에 진행」 으로 이어서 하세요")
            job = got.data
            if not job or job.get("status") != "running":
                return job
            if time.time() - t0 > limit:
                raise _Halt("timeout", f"{what}이(가) 시간 안에 끝나지 않았습니다 — 다시 누르세요")
            time.sleep(WAIT["poll"])


def _docs_of(run, line):
    """그 줄이 닿는 문서들 → [(문서 id, 문서 이름(역할의 이름), 역할)] — 원본 → 목적 차례."""
    out = []
    for role in U.roles_of(line["on"]):
        d, r = run.pair.get(role), S._role(run.task, role)
        if d and r:
            out.append((d["id"], r["name"], role))
    return out


def _got(f):
    return bool(f and f["heads"]["s2"] and f["heads"]["s3"])


def _do_heads(run, stage, line):
    """헤딩 · 표 분석 — 헤딩 그래프 · 표 구조가 없는 문서만 스크립트로 분석(같이 걸고 함께 기다림) → 목적 문서가 이 줄에 들었으면 작성 지침 저장(분석을 새로 했는지와 무관 — 지금 화면과 같다: ② §18-12 ②)."""
    docs = _docs_of(run, line)
    missing = [(d, name) for d, name, _ in docs if not _got(UNIT.facts(d))]
    run.working = {d for d, _ in missing}
    for d, name in missing:
        run.note(stage, line["key"], f"{name} 헤딩 · 표 분석 중", d)
        got = UNIT.start_heads(d, "first")
        if got.code == "busy":   # 이미 도는 다른 헤딩 작업 — 끝난 뒤 한 번 더 건다
            run.wait(d, WAIT["heads"], f"{name}의 헤딩 작업")
            got = UNIT.start_heads(d, "first")
        if not got.ok:
            raise _Halt(got.code, f"{name}의 헤딩 · 표 분석을 시작하지 못했습니다 — {got.text}")
    for d, name in missing:
        run.wait(d, WAIT["heads"], f"{name}의 헤딩 · 표 분석")
    run.working = set()
    for d, name in missing:
        f = UNIT.facts(d)
        if not _got(f):
            err = ((f or {}).get("heads", {}).get("job") or {}).get("error") or "결과가 생기지 않았습니다"
            raise _Halt("failed", f"{name}의 헤딩 · 표 분석이 실패했습니다 — {err}(「헤딩 추출」 탭에서 확인)")
    # 끝 글은 화면 실행의 글 그대로(② §17-7 「끝 글」 — app.js taskRunSteps 의 base): 「두 문서의 헤딩 그래프·표 구조가 있습니다 · 작성 지침 n개 저장(헤딩 a · 표 b)」
    text = f"{'두 문서' if len(docs) == 2 else docs[0][1]}의 헤딩 그래프·표 구조가 있습니다"
    target = next((d for d, _, role in docs if role == "target"), None)
    if target:
        kept = UNIT.guides_keep(target)
        c = (((kept.data or {}).get("saved") or {}).get("counts") or {}) if kept.ok and isinstance(kept.data, dict) else {}
        if not kept.ok:
            text += f" · 작성 지침을 저장하지 못했습니다({kept.text})"
        elif c.get("items") or c.get("marks"):
            text += f" · 작성 지침 {c.get('items', 0):,}개 저장(헤딩 {c.get('headings', 0):,} · 표 {c.get('tables', 0):,})"
    return ("done" if missing else "nothing"), text


def _llm_job(run, stage, key, d, name):
    """그 문서의 「LLM 검증·보완」(배경 · 유료)을 걸고 끝날 때까지 기다린다 — 도는 다른 헤딩 작업이 있으면 그것이 끝난 뒤 한 번 더 건다 · 멈춤 요청이 오면 내가 건 이어 돌리기에 멈춤을 건다.
    시작 못 함 · 밀려남 · 시간 초과는 _Halt, 멈춤은 _Stop. 결과(거쳤나)는 부르는 쪽이 문서에서 다시 본다."""
    run.working = {d}
    run.note(stage, key, f"{name} LLM 검증·보완 중(헤딩 · 템플릿 → 표 → 서식 정리 계획 · 몇 분)", d)
    got = UNIT.start_llm(d, run.rec.get("skill"))
    if got.code == "busy":
        run.wait(d, WAIT["llm"], f"{name}의 헤딩 작업")
        run.guard()
        got = UNIT.start_llm(d, run.rec.get("skill"))
    if not got.ok:
        raise _Halt(got.code, f"{name}의 LLM 검증·보완을 시작하지 못했습니다 — {got.text}")
    t0, asked = time.time(), False
    while True:   # 끝날 때까지 — 멈춤 요청이 오면 그 이어 돌리기에 멈춤을 건다(내가 시작한 것만)
        job = UNIT.job(d)
        if job.code == "missing":
            raise _Halt("evicted", "열린 문서가 많아 이 문서가 메모리에서 밀려났습니다 — 「한 번에 진행」 으로 이어서 하세요")
        if not job.data or job.data.get("status") != "running":
            break
        if run.stopping() and not asked:
            UNIT.stop_llm(d)
            asked = True
        if time.time() - t0 > WAIT["llm"]:
            raise _Halt("timeout", f"{name}의 LLM 검증·보완이 시간 안에 끝나지 않았습니다 — 다시 누르세요")
        time.sleep(WAIT["poll"])
    run.working = set()
    if run.stopping():
        raise _Stop()


def _do_heads_llm(run, stage, line):
    """LLM 검증·보완 — 그 줄의 문서를 차례로: 이미 거쳤으면 지나감 · LLM 을 못 쓰거나 사람이 건너뛰었으면 「건너뜀」 · 승인 밖이면 남김 · 아니면 걸고 끝날 때까지 기다린다(유료 · 몇 분 — 문서는 안 바뀜)."""
    notes, left, did = [], [], False
    llm, skip = UNIT.llm_ok(), set(UNIT.skips(run.target))
    for d, name, _ in _docs_of(run, line):
        run.guard()   # 유료 호출 전에 멈춤 요청 · 대상을 다시 본다
        f = UNIT.facts(d)
        if not _got(f):
            left.append(f"{name} LLM 검증·보완은 하지 않음(헤딩 · 표 분석이 먼저입니다 — 남은 단계)")
            continue
        if f["heads"]["llm"]:
            continue
        if not llm:
            notes.append(f"{name} LLM 검증·보완은 건너뜀(LLM 을 쓸 수 없음)")
            continue
        if d in skip:
            notes.append(f"{name} LLM 검증·보완은 건너뜀(건너뛰기)")
            continue
        if run.approval is not None and d not in run.approval.get("paid", ()):
            left.append(f"{name} LLM 검증·보완은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)")
            continue
        _llm_job(run, stage, line["key"], d, name)
        f = UNIT.facts(d)
        if not (f and f["heads"]["llm"]):
            err = ((f or {}).get("heads", {}).get("job") or {}).get("error") or "LLM 이 답을 내지 못했습니다"
            raise _Halt("failed", f"{name}의 LLM 검증·보완이 끝나지 않았습니다 — {err}(다시 누르거나 그 줄의 「건너뛰기」)")
        did = True
        notes.append(f"{name} LLM 검증·보완을 거쳤습니다")
    if left:
        return "left", " · ".join(left + notes)
    return ("done" if did else "nothing"), " · ".join(notes)   # 이미 거친 문서는 글이 없다(화면 실행의 끝 글과 같게)


HANDLERS = {"heads": _do_heads, "headsLlm": _do_heads_llm}   # 단위 key → 처리 함수(run, 묶음 id, 줄) → (done | nothing | left, 글) · 멈춤은 _Halt · _Stop


def _stage_name(task, module, fallback):
    """묶음을 가리키는 글 — 화면 app.js taskStageName 과 같다: 이 워크플로우에 그 묶음이 있으면 「N단계 「이름」」, 없으면 「「이름」」(번호 없이)."""
    g = next((x for x in task["stages"] if x.get("module") == module), None)
    return f"{g['no']} 「{g['name']}」" if g else f"「{fallback}」"


def _tail_review(task, g, R):
    """「문서 검토」 — 줄 하나(「분석」)면 「 — 다음은 「LLM 검증·보완」 입니다」, 묶음 전체면 「 — 구성은 N단계 「구성 맞추기」 에서 맞춥니다」(그 묶음이 있을 때)."""
    if R.get("only") == "heads":
        return " — 다음은 「LLM 검증·보완」 입니다" if any(s["key"] == "headsLlm" for s in g["steps"]) else ""
    fit = next((x for x in task["stages"] if x.get("module") == "stage_fit"), None)
    return f" — 구성은 {fit['no']} 「{fit['name']}」 에서 맞춥니다" if fit and not R.get("only") else ""


_TAILS = {"stage_review": _tail_review}   # 묶음의 단계(module) → 끝 글 꼬리 함수(task, 묶음, 범위) — 세션마다 맡은 묶음의 절 끝에서 _TAILS.update({...}) 로 더한다


def _tail(task, gid, R):
    """묶음의 끝 글 꼬리 — 화면 실행의 글 그대로(app.js taskRunSteps)."""
    g = next((x for x in task["stages"] if x["id"] == gid), None)
    fn = _TAILS.get(g.get("module")) if g is not None else None
    return fn(task, g, R) if fn else ""


def _stage_lines(task, gid):
    return [x for x in S.lines(task) if x["stage"] == gid]


def _view(run):
    return S.view(run.task, run.pair, _materials(run.pair, run.task), llm=UNIT.llm_ok(), skip=UNIT.skips(run.target))


def _drive(run):
    rec, R = run.rec, run.rec["range"]
    ids = [g["id"] for g in run.task["stages"]]
    span = ids[ids.index(R["from"]): ids.index(R["to"]) + 1]
    status, texts, halt = "done", [], None
    try:
        for gid in span:
            run.guard()
            view = _view(run)
            rows = {g["id"]: g for g in view["stages"]}
            row = rows[gid]
            if not view["ready"]:
                raise _Halt("notReady", view["why"])
            before = None if R.get("only") else next((g for g in view["stages"][:ids.index(gid)] if g["server"] and g["left"]), None)   # 앞 묶음이 덜 끝남(범위 밖도) — 뒤 묶음은 하지 않고 남긴다 · 줄 하나(줄의 단추 — 화면의 early)는 묶음 차례를 안 따진다
            if before is not None:
                run.step(gid, "", "left", f"{before['no']} 「{before['name']}」 이 덜 끝났습니다")
                status = "left"
                break
            if not R.get("only") and not R.get("redo") and not row["left"]:
                rec["stages"].append({"id": gid, "status": "done", "text": "남은 단계가 없습니다", "t0": time.time(), "t1": time.time()})
                continue
            entry = {"id": gid, "status": "running", "text": "", "t0": time.time(), "t1": None}
            rec["stages"].append(entry)
            UNIT.store.log(run.target, event="stage", n=rec["n"], stage=gid)
            got = []
            for line in _stage_lines(run.task, gid):
                if R.get("only") and line["key"] != R["only"]:
                    continue   # 줄 하나만(「분석」) — 뒤의 유료 줄을 시작하지 않는다
                u = line["unit"]
                if u["kind"] == "pick":
                    continue   # 사람이 고르는 줄(준비) — 실행기는 지나간다
                run.guard()
                if u["kind"] == "hand":
                    raise _Halt("hand", f"사람이 할 일 — {line['name']}")
                t0 = time.time()
                run.note(gid, line["key"], line["name"])
                res = HANDLERS[line["key"]](run, gid, line)   # (st, 글) | (st, 글, 묶음 끝 글의 몫) — 줄의 기록 글과 묶음 끝 글의 몫이 다를 때 셋째(없으면 글 그대로)
                st, text = res[0], res[1]
                run.working = set()
                run.step(gid, line["key"], st, text, t0=t0)
                got.append((st, res[2] if len(res) > 2 else text))
            lefts = [t for st, t in got if st == "left"]
            entry.update(status="left" if lefts else "done", text=_clip((" · ".join(t for _, t in got if t) or "한 일이 없습니다") + _tail(run.task, gid, R)), t1=time.time())
            texts.append(entry["text"])
            if lefts:
                status = "left"
    except _Stop:
        status = "stopped"
    except _Halt as e:
        status, halt = "halted", e
    except Exception as e:  # noqa: BLE001 — 실행 스레드가 조용히 죽지 않게: 기록에 남기고 실패로 끝낸다
        status, halt = "failed", _Halt("error", f"{type(e).__name__}: {e}")
        import logging
        logging.getLogger("uvicorn.error").exception("[워크플로우 실행] 오류")
    now = rec.get("now") or {}
    with run.lock:
        for g in rec["stages"]:
            if g["status"] == "running":
                g.update(status="halted" if status in ("halted", "failed") else "stopped" if status == "stopped" else g["status"], t1=time.time(), text=_clip(halt.text) if halt else g["text"])
        if halt is not None:
            rec["halt"] = {"stage": now.get("stage") or "", "key": now.get("key") or "", "code": halt.code, "text": _clip(halt.text)}
        word = {"done": "끝남", "left": "남김", "halted": "멈춤", "stopped": "멈춤", "failed": "오류"}[status]
        tail = halt.text if halt is not None else "멈춤을 눌러 멈췄습니다 — 끝난 단계는 그대로입니다" if status == "stopped" else " / ".join(texts) or "남은 단계가 없습니다"
        rec.update(status=status, stopping=False, ended=time.time(), now=None, end={"ok": status in ("done", "left"), "text": _clip(f"{word} — {tail}")})
    with _LOCK:
        RUNS.pop(run.target, None)
        for d in [d for d, t in BUSY.items() if t == run.target]:
            BUSY.pop(d, None)
    run.working = set()
    run.save()
    UNIT.store.log(run.target, event={"halted": "halt", "stopped": "stop"}.get(status, "end"), n=rec["n"], status=status, text=rec["end"]["text"])
    src = (rec["docs"].get("source") or {}).get("id")
    if src:
        UNIT.store.log(src, event="end", n=rec["n"], status=status, role="source", target=run.target)


def start(wid, body):
    """실행을 시작한다 → 실행 요약(202). 못 하면 Refuse(409 — reason · message) · ValueError(400 — 몸의 꼴).
    body = {from(묶음 id), to?, only?(줄 key), redo?, skill?, skip?[구조 반영에서 뺄 자리 key], by?(human | agent), where?, screen?, turn?, key?, paid?[문서 id], sig?, docs?{target, source}}.
    검사 차례(② §17-7 「시작」): 문서 묶음(notReady · docs) → 정의(gone · definition) → 서버가 맡는 묶음(client) → 겹침(busy) → 남은 일(noWork)."""
    if not isinstance(body, dict) or not isinstance(body.get("from"), str):
        raise ValueError("from(묶음 id)이 있어야 합니다")
    pair = UNIT.pair(wid)
    if pair is None:
        raise Refuse("gone", "그런 작업이 없습니다")
    task = S.definition(pair["job"])
    if task is None:
        raise Refuse("gone", "이 문서의 워크플로우를 찾지 못했습니다 — 지워졌거나 워크플로우가 없는 문서입니다")
    ids = [g["id"] for g in task["stages"]]
    first, to, only = body["from"], body.get("to") or body["from"], body.get("only") or ""
    if first not in ids or to not in ids or ids.index(to) < ids.index(first):
        raise ValueError("모르는 묶음입니다")
    if only and (only not in [x["key"] for x in _stage_lines(task, first)] or to != first):
        raise ValueError("모르는 단계입니다")
    if body.get("skip") is not None and (not isinstance(body["skip"], list) or len(body["skip"]) > SKIP_MAX or not all(isinstance(x, str) for x in body["skip"])):
        raise ValueError(f"skip 은 뺄 자리 key 목록({SKIP_MAX}개까지)이어야 합니다")   # 자르면 사람이 뺀 자리가 반영된다 — 거절한다(astra P1)
    ok, _, why = S.ready(task, pair)
    if not ok:
        raise Refuse("notReady", why)
    want = body.get("docs")
    if isinstance(want, dict) and any((want.get(r) or None) != ((pair.get(r) or {}).get("id")) for r in ("target", "source") if r in want):
        raise Refuse("docs", "화면이 본 문서 칸과 서버의 문서 칸이 다릅니다 — 다시 읽은 뒤 누르세요")
    sig = S.sig(task)
    if task.get("custom") and isinstance(body.get("sig"), str) and body["sig"] != sig:
        raise Refuse("definition", "이 워크플로우의 단계가 바뀌었습니다 — 바뀐 단계를 보고 다시 누르세요")
    span = ids[ids.index(first): ids.index(to) + 1]
    if client_only() or not all(S.served(task, g) for g in span):
        raise Refuse("client", "이 묶음은 아직 문서 화면에서 진행합니다")
    target, source = pair["target"], pair.get("source")
    view = S.view(task, pair, _materials(pair, task), llm=UNIT.llm_ok(), skip=_skips(pair, wid))
    rows = {g["id"]: g for g in view["stages"]}
    if not body.get("redo") and not only and not any(rows[g]["left"] for g in span):
        raise Refuse("noWork", "남은 단계가 없습니다")
    by = "agent" if body.get("by") == "agent" else "human"
    approval = {"paid": [d for d in body.get("paid") or [] if isinstance(d, str)]} if by == "agent" else None   # 사람이 누른 실행은 제한 없음 · 에이전트 카드는 승인한 문서에만 유료
    docs = [d["id"] for d in (target, source) if d]
    with _LOCK:
        hit = next((BUSY[d] for d in docs if d in BUSY), None)
        if hit is not None:
            other = RUNS.get(hit)
            raise Refuse("busy", "다른 화면에서 진행 중입니다 — 끝나거나 멈춘 뒤에 하세요", other.summary() if other is not None else None)
        n = (_numbers(target["id"]) or [0])[-1] + 1
        rec = {"v": 1, "n": n, "boot": BOOT, "job": pair["job"], "sig": sig, "scope": pair["scope"],
               "docs": {"target": {"id": target["id"], "name": target["name"]}, "source": {"id": source["id"], "name": source["name"]} if source else None},
               "range": {"from": first, "to": to, "only": only, "redo": body.get("redo") or ""},
               "origin": {"by": by, "where": str(body.get("where") or "")[:20], "screen": str(body.get("screen") or "")[:40], **({"turn": body["turn"]} if isinstance(body.get("turn"), (str, int)) else {}),
                          **({"key": str(body["key"])[:200]} if body.get("key") else {})},
               "approval": approval, "skill": body.get("skill") if isinstance(body.get("skill"), str) else None,
               "skip": [x for x in body.get("skip") or () if isinstance(x, str)],   # 구조 반영에서 뺄 자리(화면의 「반영에서 빼기」 — 화면에만 있던 입력: ② §17-11 ⓙ · LLM 「건너뛰기」 와 다르다). 자르지 않는다(위에서 수를 거절)
               "status": "running", "stopping": False, "started": time.time(), "ended": None, "now": None, "stages": [], "steps": [], "left": [], "halt": None, "end": None, "cut": None}
        run = Run(rec, task, pair, approval)
        RUNS[target["id"]] = run
        for d in docs:
            BUSY[d] = target["id"]
    run.save()
    UNIT.store.log(target["id"], event="start", n=n, **{k: rec["range"][k] for k in ("from", "to", "only") if rec["range"][k]}, by=by)
    if source:
        UNIT.store.log(source["id"], event="start", n=n, role="source", target=target["id"])
    threading.Thread(target=_drive, args=(run,), daemon=True, name=f"flow-{target['id']}-{n}").start()
    return run.summary()


def stop(wid, n=None):
    """멈춤(어느 화면에서나) — 지금 하는 일이 끝나면 멈춘다 → {stopping} | None(도는 실행이 없음 · 번호가 다름)."""
    target = BUSY.get(wid)
    run = RUNS.get(target) if target else None
    if run is None or (n is not None and run.rec["n"] != n):
        return None
    with run.lock:
        run.rec["stopping"] = True
    return {"stopping": True, "n": run.rec["n"]}


def shutdown():
    """서버를 끌 때 — 아는 만큼 미리 적는다(끊김으로)."""
    for run in list(RUNS.values()):
        with run.lock:
            rec = dict(run.rec)
        with _LOCK:
            RUNS.pop(run.target, None)
        _cut(run.target, rec)


# ================================================================ 2단계 「구성 맞추기」(걸음 2 — spec_워크플로우 ② §17-10 걸음 2 · §18-4 · §18-12 ②)
# 프로젝트 구성 확정 → 프로젝트 구성 반영(울타리 · 같은 검사 · 다시 계획 없이 한 번) → 다시 문서 검토(스크립트) → 다시 문서 검토(LLM).
# 차례 · 조건 · 끝 글은 화면 실행(app.js taskRunSteps 의 frame 가지) 그대로 — 끝 글 = 「구조를 맞췄습니다 — <반영 줄의 글>[ · 다시 분석][ · LLM] · 내용은 N단계 「내용 넣기」 에서 넣습니다」.
# 끝남은 처리 함수가 문서에서 다시 센다(workflow_units 의 같은 식) — 화면에 보이는 「끝남」 을 성공 조건으로 쓰지 않는다(② §18-4 ⓐ~ⓒ).
_FIT_KEYS = ("config", "division", "reheads", "reheadsLlm")


def _fit_names(run):
    """(원본 문서 이름, 목적 문서 이름, 원본 id, 목적 id)."""
    s, t = S._role(run.task, "source"), S._role(run.task, "target")
    return (s or {}).get("name") or "원본 문서", (t or {}).get("name") or "목적 문서", (run.pair.get("source") or {}).get("id"), (run.pair.get("target") or {}).get("id")


def _fit_facts(pair):
    """두 문서의 지금 재료(헤딩 + 구성) — 「구성 맞추기」 줄의 상태를 세는 데 필요한 것만(넣기 재료는 읽지 않는다)."""
    out = {}
    for role in U.ROLES:
        d = (pair.get(role) or {}).get("id")
        if d:
            f = UNIT.facts(d)
            out[d] = {**f, "div": UNIT.div_facts(d)} if f is not None else None
    return out


def _fit_state(run, key):
    """그 줄의 지금 상태(화면 taskSteps 와 같은 식 — workflow_units.state) → (상태, 재료)."""
    facts = _fit_facts(run.pair)
    ctx = S.context(run.task, run.pair, facts, llm=UNIT.llm_ok(), skip=UNIT.skips(run.target))
    return (U.state(key, ctx, S.family(run.task)) or {"st": "todo", "text": ""}), facts


def _fit_materials(task, pair, facts):
    """상태를 셀 때(GET …/flow · 실행의 묶음 경계) 「구성 맞추기」 줄을 서버가 맡으면 두 문서의 구성 재료를 덧붙인다(MATERIALS)."""
    if not any(x["key"] in _FIT_KEYS and S.served(task, x["stage"]) for x in S.lines(task)):
        return
    for role in U.ROLES:
        d = (pair.get(role) or {}).get("id")
        if d and d in facts and facts[d] is not None and "div" not in facts[d]:
            facts[d] = {**facts[d], "div": UNIT.div_facts(d)}


def _analyze(run, stage, key, doc, name, how):
    """헤딩 · 표 분석을 스크립트로 걸고 끝날 때까지(how = "first" | 2 | 3 — unit_steps.start_heads) — 도는 다른 헤딩 작업이 있으면 끝난 뒤 한 번 더. 실패는 _Halt(화면 taskRunAnalyze 의 글)."""
    run.working = {doc}
    got = UNIT.start_heads(doc, how)
    if got.code == "busy":
        run.wait(doc, WAIT["heads"], f"{name}의 헤딩 작업")
        run.guard()
        got = UNIT.start_heads(doc, how)
    if not got.ok:
        raise _Halt(got.code, f"{name}의 헤딩 · 표 분석을 시작하지 못했습니다 — {got.text}")
    job = run.wait(doc, WAIT["heads"], f"{name}의 헤딩 · 표 분석")
    run.working = set()
    if run.stopping():
        raise _Stop()
    if job and job.get("error"):
        raise _Halt("failed", f"헤딩·표 분석 실패 — {job['error']}")


def _do_config(run, stage, line):
    """프로젝트 구성 확정 — 원본(구성의 기준)의 입력 값(없으면 문서에 적힌 값)을 목적 문서에서 확정한다(화면 실행이 목적 문서의 입력 칸으로 확정하는 것과 같다 — 공유 중이면 프로젝트의 확정). 문서는 안 바뀐다."""
    st, _ = _fit_state(run, "config")
    if st["st"] == "done":
        return "nothing", ""
    S_, _D, src, tgt = _fit_names(run)
    fit = _stage_name(run.task, "stage_fit", "구성 맞추기")
    run.note(stage, "config", f"{S_}의 프로젝트 구성 확인")
    A = UNIT.div_facts(src)
    if A is None:
        raise _Halt("missing", f"{S_}의 프로젝트 구성을 읽지 못했습니다")
    values = A.get("input") or A.get("read")
    if not values:   # 저장한 값도 읽어 둔 값도 없음 — 문서에 적힌 값
        run.note(stage, "config", f"{S_}에서 단계·차년도·기관 읽기")
        got = UNIT.config_read(src)
        values = got.data if got.ok else None
        if not values:
            raise _Halt("noValues", f"{S_}에서 단계·차년도·기관을 읽지 못했습니다 — {fit} 의 프로젝트 구성 입력 칸에 넣거나 「프로젝트 구성 불러오기」 로 불러온 뒤 다시 누르세요")
    run.guard()
    run.note(stage, "config", "프로젝트에 저장(확정)")
    got = UNIT.config_confirm(tgt, values)
    if not got.ok:
        raise _Halt(got.code, f"프로젝트 구성을 확정하지 못했습니다 — {got.text}")
    st, _ = _fit_state(run, "config")
    if st["st"] != "done":
        raise _Halt("notConfirmed", f"프로젝트 구성이 확정되지 않았습니다 — {st['text']}")
    return "done", ""


def _do_division(run, stage, line):
    """[문서 바뀜] 프로젝트 구성 반영 — 원본(기준)의 값으로 목적 문서의 값을 맞추고 울타리 안에서 계획 → 같은 검사(autoStops) → 반영을 **다시 계획 없이 한 번**(② §18-4).
    끝 글의 묶음 몫 = 「구조를 맞췄습니다 — <이 줄의 글>」(이미 반영돼 있어도 — 화면 실행과 같다)."""
    S_, D_, src, tgt = _fit_names(run)
    fit = _stage_name(run.task, "stage_fit", "구성 맞추기")
    st, _ = _fit_state(run, "division")
    if st["st"] == "done":
        return "nothing", f"구조를 맞췄습니다 — {st['text']}"
    cf, _ = _fit_state(run, "config")
    if cf["st"] != "done":
        raise _Halt("notConfirmed", f"「프로젝트 구성 확정」 이 먼저입니다 — {cf['text'] or '프로젝트 구성을 확정한 뒤 다시 누르세요'}")
    run.note(stage, "division", f"{S_} 값과 견주기")
    A, B = UNIT.div_facts(src), UNIT.div_facts(tgt)
    if A is None or B is None:
        raise _Halt("missing", "두 문서의 프로젝트 구성을 읽지 못했습니다")
    a, read = U.basis_values(A)
    if not a:
        raise _Halt("noValues", f"{S_}(기준)에 프로젝트 구성 값이 없습니다 — {S_}에서 값을 넣거나 문서에서 읽은 뒤 다시 누르세요")
    if read:   # 저장된 값이 없어 문서에서 읽은 값 — 원본 작업의 값으로 저장한다(문서는 그대로 — 화면 실행과 같다)
        run.note(stage, "division", f"문서에서 읽은 값을 {S_} 값으로 저장")
        got = UNIT.config_save(src, a)
        a, read = U.basis_values(UNIT.div_facts(src)) if got.ok else (None, False)
        if not a or read:
            raise _Halt("notSaved", f"{S_} 값을 저장하지 못했습니다{f' — {got.text}' if got.text else ''}")
    b = U.target_values(B)
    moved = not b or bool(U.div_diff(a, b))
    values = a if moved else b   # 다르면 원본의 값으로(당해 차년도도 — 화면 taskDivFit 과 같은 값) · 같으면 목적 문서의 값 그대로
    if not U.confirm_valid(values, B.get("confirmed")):   # 확정과 다른 값으로 문서를 바꾸지 않는다(계획 요청이 그 값을 입력으로 저장하므로 계획 **전**에 — astra 2026-11-20 P1)
        raise _Halt("unconfirmed", f"반영할 값({U.summary_text(values)})이 확정한 프로젝트 구성과 다릅니다 — {fit} 의 「프로젝트 구성 확정」 을 다시 한 뒤 누르세요")
    skip = list(run.rec.get("skip") or [])   # 「반영에서 빼기」 — 위 확인을 지나면 값은 목적 문서의 지금 입력과 같다(확정 = 목적의 입력 · 원본 값이 다르면 멈춤) — 화면에서 고른 그 값의 자리
    run.guard()
    run.working = {tgt}
    applied = None
    with run.fence(tgt):   # 알림 → 화면들의 고치던 글 → 울타리 — 계획과 반영 사이에 사람이 친 글이 끼지 않게(② §17-8)
        run.note(stage, "division", "변경 계획", tgt)
        got = UNIT.division_plan(tgt, values, skip)
        if not got.ok or not isinstance(got.data, dict) or not got.data.get("planId"):
            raise _Halt("plan" if got.ok else got.code, f"프로젝트 구성 변경 계획을 세우지 못했습니다 — {got.text or '계획이 없습니다'}")
        plan = got.data
        if plan.get("stale"):
            raise _Halt("stale", "계획을 세우는 사이 문서나 프로젝트 구성 값이 바뀌었습니다 — 다시 누르세요")
        stops = plan.get("autoStops") or ""   # 같은 검사(division_plan.auto_stops — 화면의 「한 번에 진행」 들과 같은 값)
        if stops:
            raise _Halt("stops", f"{stops} — 저절로 반영하지 않습니다. {fit} 의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요")
        run.guard()   # 문서 쓰기 직전 — 멈춤 요청 · 문서 칸(원본 · 목적) · 범위가 그대로인가(계획을 세우는 사이 원본을 바꿨으면 옛 원본 기준으로 바꾸지 않게 — astra P1)
        run.note(stage, "division", f"{D_}에 반영", tgt)
        applied = UNIT.division_apply(tgt, plan["planId"], plan["baseRev"])
    run.working = set()
    if applied.code not in ("ok", "nothing"):   # 409(낡은 계획) · 422(표준 검사) — 다시 계획하지 않고 멈춘다(② §18-4) · 상태를 다시 세어 「끝남」 으로 덮지 않는다
        raise _Halt(applied.code, f"프로젝트 구성이 반영되지 않았습니다 — {applied.text or '반영 요청이 거절되었습니다'}")
    st, _ = _fit_state(run, "division")
    if st["st"] != "done":
        raise _Halt("notApplied", f"프로젝트 구성이 반영되지 않았습니다 — {st['text']}")
    return ("done" if applied.code == "ok" else "nothing"), f"구조를 맞췄습니다 — {st['text']}"


def _do_reheads(run, stage, line):
    """다시 문서 검토 — 구조 반영으로 바뀐 목적 문서를 다시 분석(스크립트: 분석이 있으면 2 → 3단계 · 없으면 첫 분석) → 작성 지침 다시 저장.
    구조 반영 전 분석이 LLM 결과이고 LLM 을 쓸 수 없으면 그대로 둔다(keep — 사람이 「다시 분석」 을 누르면 redo 로 그때도 다시)."""
    _S, D_, _src, tgt = _fit_names(run)
    R = run.rec["range"]
    dv, _ = _fit_state(run, "division")
    if dv["st"] != "done":
        return "left", f"{D_} 다시 문서 검토는 하지 않음(「프로젝트 구성 반영」 이 먼저입니다 — 남은 단계)"
    f = UNIT.facts(tgt)
    tf = {**f, "div": UNIT.div_facts(tgt)} if f is not None else None
    keep = U.heads_kept(tf) and UNIT.llm_ok() is False
    again, did = "", False
    run.note(stage, "reheads", "헤딩·표 분석 확인(구조 반영 뒤)")
    if not _got(tf) or (U.heads_stale(tf) and not keep) or R.get("redo") == "reheads":
        run.guard()
        run.note(stage, "reheads", f"{D_} 헤딩·표 다시 분석(스크립트)", tgt)
        if _got(tf):
            for how in (2, 3):   # 2단계(헤딩 그래프 — 1단계는 스스로 뽑는다) → 3단계(표 구조) · 스크립트만
                _analyze(run, stage, "reheads", tgt, D_, how)
        else:
            _analyze(run, stage, "reheads", tgt, D_, "first")
        st, _ = _fit_state(run, "reheads")
        if st["st"] != "done":
            raise _Halt("failed", f"{D_}를 다시 분석하지 못했습니다 — {st['text'] or '「헤딩 추출」 탭에서 확인하세요'}")
        again, did = f"{D_}를 다시 분석했습니다", True
        run.note(stage, "reheads", "작성 지침 저장(헤딩/표별)", tgt)
        UNIT.guides_keep(tgt)   # 구조 반영으로 자리가 바뀌었다 — 새 분석으로 다시 저장(못 해도 멈추지 않는다: 「작성요령 삭제」 가 지우기 전에 다시 남긴다)
    elif keep:
        again = f"{D_}의 분석은 구조 반영 전 것(LLM 결과 — LLM 을 쓸 수 없어 그대로 둠 · 늘어난 절·표는 못 이을 수 있음: 「다시 분석」)"
    st = "done" if did else "nothing"
    if R.get("only") == "reheads":   # 「다시 분석」 단추 — 이 줄만
        return st, f"구조를 맞춘 문서의 헤딩·표{f' — {again}' if again else ' 분석은 구조 반영 뒤의 것입니다'} — 다음은 「다시 문서 검토(LLM)」 입니다"
    return st, again


def _do_reheads_llm(run, stage, line):
    """다시 문서 검토(LLM) — 구조를 맞춘 목적 문서의 LLM 검증·보완(유료 · 몇 분 — 문서는 안 바뀜). 이미 끝났으면(거침 · LLM 을 못 씀 · 건너뜀) 글만 · 승인 밖이면 남김."""
    _S, D_, _src, tgt = _fit_names(run)
    st, _ = _fit_state(run, "reheadsLlm")
    if st["st"] == "done":
        return "nothing", (f"{D_} LLM 검증·보완은 건너뜀({'LLM 을 쓸 수 없음' if UNIT.llm_ok() is False else '건너뛰기'})" if st.get("skipped") else "")
    rh, _ = _fit_state(run, "reheads")
    if rh["st"] != "done":
        return "left", f"{D_} LLM 검증·보완은 하지 않음(「다시 문서 검토」 가 먼저입니다 — 남은 단계)"
    if run.approval is not None and tgt not in run.approval.get("paid", ()):
        return "left", f"{D_} LLM 검증·보완은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)"
    run.guard()   # 유료 호출 전에 멈춤 요청 · 대상을 다시 본다
    _llm_job(run, stage, "reheadsLlm", tgt, D_)
    st, _ = _fit_state(run, "reheadsLlm")
    if st["st"] != "done":
        err = (((UNIT.facts(tgt) or {}).get("heads") or {}).get("job") or {}).get("error")
        raise _Halt("failed", f"{D_}의 LLM 검증·보완을 끝내지 못했습니다{f' — {err}' if err else ''} · 다시 누르거나 그 줄의 「건너뛰기」 로 스크립트 분석만으로 진행하세요")
    return "done", f"{D_} LLM 검증·보완을 거쳤습니다"


def _tail_fit(task, g, R):
    """「구성 맞추기」 — 「 · 내용은 N단계 「내용 넣기」 에서 넣습니다」(줄 하나(「다시 분석」)면 없음 — 그 줄의 글이 다음을 적는다)."""
    return "" if R.get("only") else f" · 내용은 {_stage_name(task, 'stage_fill', '내용 넣기')} 에서 넣습니다"


HANDLERS.update({"config": _do_config, "division": _do_division, "reheads": _do_reheads, "reheadsLlm": _do_reheads_llm})
_TAILS.update({"stage_fit": _tail_fit})
MATERIALS.append(_fit_materials)
