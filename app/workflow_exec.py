"""워크플로우 실행기 — 정의의 줄을 차례대로 서버에서 돈다(spec_워크플로우 ② §18-4 「차례 실행기」 · 기록 · 잠금 · 끊김은 ② §17-6 · 시작 · 대상 고정 · 멈춤은 ② §17-7).

창을 닫거나 다른 문서를 열어도 「한 번에 진행」 이 끝까지 돌게 한다 — 화면(작업 개요 · 대시보드 · 첫 화면의 대시보드 · 에이전트)은 시작 · 멈춤 · 보기만 한다.
- **문서를 직접 만지지 않는다** — 늘 문(`UNIT` = app/unit_steps.py: `attach` 가 넣는다 · 시험은 가짜 문)을 부른다. 가져오는 앱 코드는 정의(app.workflow · app.custom_tasks) · 단위(app.workflow_units) · 상태(app.workflow_state)뿐.
- **줄마다 처리 함수 하나**(`HANDLERS` — 단위의 key): 할 필요가 있나 · 이번 호출이 약속한 결과를 냈나를 스스로 정해 `done`(끝남) · `nothing`(한 일 없음) · `left`(남김 — 까닭) · `halt`(멈춤 — 까닭)를 돌려준다.
  화면에 보이는 상태(workflow_state.view)는 따로 센다 — 실행기는 그 표시를 성공 판정에 쓰지 않는다(② §18-4).
- 지금 맡는 묶음 = 이관형의 「문서 검토」(준비 `files` · 헤딩 · 표 분석 `heads` · LLM 검증·보완 `headsLlm` — 걸음 1: ② §18-10). 그 밖의 묶음은 화면이 돈다(`server: false`).
- 실행 기록 = 목적 문서 작업 폴더의 `flowruns/<n>.json`(단계 경계마다 통째로 다시 씀 · 저장이 꺼져 있으면 메모리만) + 작업 기록의 `flowRun` 줄. **끝남은 늘 문서마다의 결과로 다시 센다** — 기록은 일어난 일만 적는다.
- 잠금: `RUNS{목적 id: 실행}` · `BUSY{문서 id: 목적 id}` — 실행에 든 문서마다 도는 실행은 하나. 이 잠금(`_LOCK`)을 쥔 채 문을 부르지 않는다(세션 잠금 → 이 잠금 차례 — ② §17-4).
- 끊김: 서버를 켤 때 `BOOT` 를 정한다 — 기록이 `running` 인데 지금 도는 실행이 아니면 읽는 때 `cut` 으로 고쳐 쓴다. **저절로 잇지 않는다**(「이어서」 = 새 실행)."""
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
STEPS_MAX, TEXT_MAX = 300, 240
STATUS = ("running", "done", "left", "halted", "stopped", "failed", "cut")
BUSY_TEXT = "워크플로우 「한 번에 진행」 이 도는 중입니다 — 끝나거나 멈춘 뒤에 하세요"


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
def _materials(pair, task):
    """정의가 읽어야 하는 역할의 문서마다 재료 → {문서 id: facts | None}(안 닿는 문서는 열지 않는다)."""
    facts = {}
    for role in S.need(task):
        d = pair.get(role)
        if d:
            facts[d["id"]] = UNIT.facts(d["id"])
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
        run.working = {d}
        run.note(stage, line["key"], f"{name} LLM 검증·보완 중(헤딩 · 템플릿 → 표 → 서식 정리 계획 · 몇 분)", d)
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


def _tail(task, gid, R):
    """묶음의 끝 글 꼬리 — 화면 실행의 글 그대로(app.js taskRunSteps): 「문서 검토」 는 줄 하나(「분석」)면 「 — 다음은 「LLM 검증·보완」 입니다」, 묶음 전체면 「 — 구성은 N단계 「구성 맞추기」 에서 맞춥니다」(그 묶음이 있을 때)."""
    g = next((x for x in task["stages"] if x["id"] == gid), None)
    if g is None or g.get("module") != "stage_review":
        return ""
    if R.get("only") == "heads":
        return " — 다음은 「LLM 검증·보완」 입니다" if any(s["key"] == "headsLlm" for s in g["steps"]) else ""
    fit = next((x for x in task["stages"] if x.get("module") == "stage_fit"), None)
    return f" — 구성은 {fit['no']} 「{fit['name']}」 에서 맞춥니다" if fit and not R.get("only") else ""


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
            before = next((g for g in view["stages"][:ids.index(gid)] if g["server"] and g["left"]), None)   # 앞 묶음이 덜 끝남(범위 밖도) — 뒤 묶음은 하지 않고 남긴다
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
                st, text = HANDLERS[line["key"]](run, gid, line)
                run.working = set()
                run.step(gid, line["key"], st, text, t0=t0)
                got.append((st, text))
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
    body = {from(묶음 id), to?, only?(줄 key), redo?, skill?, by?(human | agent), where?, screen?, turn?, key?, paid?[문서 id], sig?, docs?{target, source}}.
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
