"""워크플로우 실행기 — 정의의 줄을 차례대로 서버에서 돈다(spec_워크플로우 ② §18-4 「차례 실행기」 · 기록 · 잠금 · 끊김은 ② §17-6 · 시작 · 대상 고정 · 멈춤은 ② §17-7).

창을 닫거나 다른 문서를 열어도 「한 번에 진행」 이 끝까지 돌게 한다 — 화면(작업 개요 · 대시보드 · 첫 화면의 대시보드 · 에이전트)은 시작 · 멈춤 · 보기만 한다.
- **문서를 직접 만지지 않는다** — 늘 문(`UNIT` = app/unit_steps.py: `attach` 가 넣는다 · 시험은 가짜 문)을 부른다. 가져오는 앱 코드는 정의(app.workflow · app.custom_tasks) · 단위(app.workflow_units) · 상태(app.workflow_state)뿐.
- **줄마다 처리 함수 하나**(`HANDLERS` — 단위의 key): 할 필요가 있나 · 이번 호출이 약속한 결과를 냈나를 스스로 정해 `done`(끝남) · `nothing`(한 일 없음) · `left`(남김 — 까닭) · `halt`(멈춤 — 까닭)를 돌려준다.
  화면에 보이는 상태(workflow_state.view)는 따로 센다 — 실행기는 그 표시를 성공 판정에 쓰지 않는다(② §18-4).
- 지금 맡는 묶음 = 이관형의 「문서 검토」(준비 `files` · 헤딩 · 표 분석 `heads` · LLM 검증·보완 `headsLlm` — 걸음 1: ② §18-10). 그 밖의 묶음은 화면이 돈다(`server: false`).
- 실행 기록 = 목적 문서 작업 폴더의 `flowruns/<n>.json`(단계 경계마다 통째로 다시 씀 · 저장이 꺼져 있으면 메모리만) + 작업 기록의 `flowRun` 줄. **끝남은 늘 문서마다의 결과로 다시 센다** — 기록은 일어난 일만 적는다.
- 잠금: `RUNS{실행의 열쇠: 실행}` · `BUSY{문서 id: 실행의 열쇠}` — **실행이 잡은 문서마다** 도는 실행은 하나. 이 잠금(`_LOCK`)을 쥔 채 문을 부르지 않는다(세션 잠금 → 이 잠금 차례 — ② §17-4).
  **문서마다 따로 도는 실행**(② §18-22 — 2026-11-21 사용자 「원본문서랑, 목적문서를 따로따로 실행해서 처리할 수 있잖아? 매칭은 1개 실행이 같이 해야하고」): 문서 하나의 줄만 도는 실행(`lane` = source | target)은 **그 문서만** 잡는다 —
  원본 문서의 실행과 목적 문서의 실행이 같이 돈다. 두 문서를 다 쓰는 실행(워크플로우 전체 줄 · 원본 → 목적 줄 · 두 문서의 줄 — `lane` "")은 두 문서를 다 잡아 묶음에 하나뿐이다.
  열쇠 = 목적 문서 id(두 문서 · 목적 문서의 실행) · `<목적 id>/source`(원본 문서의 실행). 같은 묶음의 실행들 = `runs_of(목적 id)`.
- 끊김: 서버를 켤 때 `BOOT` 를 정한다 — 기록이 `running` 인데 지금 도는 실행이 아니면 읽는 때 `cut` 으로 고쳐 쓴다. **저절로 잇지 않는다**(「이어서」 = 새 실행).
- 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」): 묶음째 실행(범위에 only 가 없다)이 끝남 · 남김으로 끝나면 끝 글을 짓기 전에 한 번, 그 실행이 바꿀 수 있는 문서의 고친 문단을 그 실행의 울타리 안에서 확정한다(_commit_end).
  **문서를 바꾸는 처리 함수는 `run.fence` 안에서만 문서를 바꾸고, 그 단위의 change 를 doc 로 적는다** — 끝 확정이 그것으로 문서를 고른다(_commit_docs)."""
import contextlib
import contextvars
import functools
import os
import threading
import time
import uuid

from app import workflow_state as S
from app import workflow_units as U

BOOT = uuid.uuid4().hex[:8]
UNIT = None                      # 문(app/unit_steps.py) — attach(app/workflow_exec_api.py)가 넣는다
_LOCK = threading.RLock()
RUNS = {}                        # 실행의 열쇠(Run.key — 목적 문서 id | "<목적 id>/source" 원본 문서만 잡은 실행) → 도는 실행(Run)
BUSY = {}                        # 실행이 잡은 문서 id → 그 실행의 열쇠(RUNS 의 key)
LAST = {}                        # 목적 문서 id → {실행 번호: 실행 기록}(메모리 — 작업 저장이 꺼져 있을 때의 원본 · 번호 세기 · 새 것 몇 개만: LAST_KEEP)
LAST_KEEP = 4
MATES = {}                       # 도는 실행의 묶음에 든 문서 id(잡지 않은 문서도) → 목적 문서 id — 확인 폴링이 디스크를 읽지 않고 「이 문서의 묶음에서 도는 실행들」 을 찾는다(live_all)
CLAIMS = {}                      # 목적 문서 id → {실행 번호: (역할, 단위)} — 문서 하나만 잡은 실행이 지금 도는 줄(옆 실행의 줄과 겹치면 안 되는 줄은 차례로: _turn)
WAIT = {"poll": 1.0, "heads": 30 * 60, "llm": 90 * 60}   # 기다림(초) — 상한은 화면 실행과 같다(분석 30분 · LLM 90분). 시험이 줄인다
STEPS_MAX, TEXT_MAX, SKIP_MAX = 300, 240, 5000
SUMMARY_STEPS = 60   # 끝난 실행의 요약에 싣는 줄의 끝 글(마지막 것부터 — 화면이 몇 초마다 읽는다)
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


def _rev_of(doc):
    """메모리의 그 문서 차례 | None — 문에 rev_now 가 없으면(옛 가짜 문) None(울타리가 「이 실행이 그 문서를 바꿨나」 를 견준다: Run.changed)."""
    fn = getattr(UNIT, "rev_now", None)
    return fn(doc) if fn is not None else None


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
        self.at = None   # (묶음 id, 줄 key) — 멈춘 줄(같은 차례의 두 줄을 함께 돌 때 「지금 줄」 은 다른 줄일 수 있다: _drive 가 적는다)


class _Stop(Exception):
    """멈춤 요청을 받았다 — 지금 하던 일이 끝난 자리."""


# ---------------------------------------------------------------- 상태(화면에 내는 것 — GET …/flow)
MATERIALS = []   # 재료 덧붙이기(task, pair, facts, opt) — 묶음마다의 재료(구성 · 넣기 …)를 그 묶음을 서버가 맡을 때만 읽는다. 세션마다 맡은 묶음의 절 끝에서 MATERIALS.append(fn)


def _materials(pair, task, *, fresh=False, excl=None):
    """정의가 읽어야 하는 역할의 문서마다 재료 → {문서 id: facts | None}(안 닿는 문서는 열지 않는다).
    fresh = **실행의 판단**(시작의 「남은 일 없음」 · 묶음 경계 · 묶음 건너뜀)에 쓰는 재료 — 잠깐 든 값(문서 하나의 분석 상태 2초 값)을 쓰지 않고 새로 읽는다(그 값은 조회 `GET …/flow` 에만: 같은 문서 차례에 도착한
    계획 · LLM 결과를 못 보고 「남은 단계 없음」 으로 끝내지 않게 — astra C1). excl = 이번 실행의 「반영에서 빼기」 자리(문서 하나의 구조 반영이 끝났나를 그 범위로 센다 — None = 모름: 지난 반영의 것 그대로)."""
    facts = {}
    for role in S.need(task):
        d = pair.get(role)
        if d:
            facts[d["id"]] = UNIT.facts(d["id"])
    opt = {"fresh": bool(fresh), "excl": excl}
    for fn in MATERIALS:
        fn(task, pair, facts, opt)
    return facts


def _excl(rec):
    """그 실행의 「반영에서 빼기」 자리 | None(시작한 화면이 뺀 자리를 알려 주지 않음 — 첫 화면의 대시보드 …: 지난 반영이 뺀 자리를 그대로 둔다)."""
    return list(rec.get("skip") or ()) if rec.get("skipGiven") else None


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
    runs = runs_of(target) if target else []
    off = client_only()
    skips = [] if off else list(_skips(pair, wid) or ())
    view = S.view(task, pair, {} if off else _materials(pair, task), llm=None if off else UNIT.llm_ok(), skip=skips,
                  running=[r.now() for r in runs])
    view["llmSkip"] = sorted(skips)   # 사람이 「LLM 검증·보완」 을 건너뛴 문서 id 들(워크플로우 옵션 — PUT …/flow/skip) — 화면이 「건너뛰기 취소」 를 그 문서에만 보인다(LLM 을 못 써서 건너뛴 것과 가른다)
    if off:
        for g in view["stages"]:
            g.update(server=False, steps=None, can=False, why="", total=0, done=0, left=0, paid=[], solo=[])
    # 도는 실행이 잡은 문서(② §18-22 「문서마다 따로 도는 실행」) — 역할 → 그 문서를 잡은 실행의 번호. 두 문서를 다 쓰는 실행은 둘 다 잡는다
    held = {r: next((x.rec["n"] for x in runs if x.lane in ("", r)), None) for r in U.ROLES}
    view["held"] = held
    if runs:
        wait = "지금 진행 중인 작업이 끝나면 쓸 수 있습니다"
        for g in view["stages"]:
            lane = g.get("lane") or ""
            taken = [x for x in runs if not lane or x.lane in ("", lane)]   # 이 묶음이 쓰는 문서를 잡은 실행 — 두 문서를 쓰는 묶음은 어느 실행이든 · 문서 하나의 묶음은 그 문서를 잡은 실행만
            if taken:
                if g["server"] and (g["can"] or not g["why"]):
                    lanes = [x.lane for x in taken]   # 문서 하나만 잡은 실행들 때문에 두 문서를 쓰는 이 묶음이 기다린다 — 그 까닭을 적는다
                    g["why"] = f"{' · '.join(_who(task, x) for x in lanes)}의 실행이 끝나면 쓸 수 있습니다 — 이 묶음은 두 문서를 함께 씁니다" if not lane and all(lanes) else wait
                g["can"] = False
            for x in g.get("solo") or ():   # 「한 문서만 진행」 — 그 문서를 잡은 실행이 있을 때만 끈다(다른 문서의 실행은 같이 돈다)
                if held.get(x["role"]) is not None:
                    x.update(can=False, why=x["why"] if x["why"] and not x["can"] else wait)
    view["runs"] = [r.summary() for r in runs]   # 도는 실행들(번호 차례 — 문서마다 따로 도는 실행은 둘일 수 있다)
    mine = _holder(wid)
    view["run"] = (mine if mine is not None else runs[0]).summary() if runs else None   # 이 문서를 잡은 실행이 먼저(없으면 같은 묶음의 첫 실행 — 「도는 것이 있다」 를 보는 옛 읽기)
    ends = _ends(target) if target else []
    view["lasts"] = [_summary(x) for x in ends]   # 지난 실행의 끝들 — 마지막에 끝난 실행 + 그것과 같이 돌던 다른 문서의 실행(끝난 차례)
    view["last"] = view["lasts"][-1] if ends and not runs else None
    return view


def _who(task, role):
    """그 역할의 문서를 가리키는 글 — 「원본 문서(사업계획서)」."""
    r = S._role(task, role) or {}
    return f"{r.get('title') or ''}({r.get('name') or ''})" if r else "다른 문서"


def _ends(target):
    """지난 실행의 끝들(기록 — 끝난 차례) — 마지막 번호의 기록과, 그것과 **같이 돌던** 다른 문서의 실행(바로 앞 번호 · 둘 다 문서 하나만 잡은 실행 · 도는 때가 겹침). 도는 것은 뺀다."""
    ns = _numbers(target)
    got = [x for x in (record(target, n) for n in ns[-2:]) if x]
    if len(got) == 2:
        a, b = got
        together = bool(a.get("lane") and b.get("lane") and a["lane"] != b["lane"] and (a.get("ended") is None or (a.get("ended") or 0) > (b.get("started") or 0)))
        if not together:
            got = [b]
    done = [x for x in got if x.get("status") != "running"]
    return sorted(done, key=lambda x: x.get("ended") or 0)


# ---------------------------------------------------------------- 실행 기록
def _summary(rec):
    """기록 → 화면이 늘 받는 요약(진행 · 끝) | None."""
    if not rec:
        return None
    return {k: rec.get(k) for k in ("n", "status", "stopping", "started", "ended", "now", "range", "origin", "docs", "left", "halt", "end", "cut", "job", "sig", "commits")} | {   # commits = 끝 확정(② §18-24)
        "lane": rec.get("lane") or "",   # 이 실행이 잡은 문서(source | target — 그 문서만 · "" = 두 문서: ② §18-22)
        "stages": [{k: g.get(k) for k in ("id", "status", "text")} for g in rec.get("stages") or []]} | ({   # 끝난 실행 — 줄마다의 끝 글(대시보드 끝 글 띠의 풍선이 「줄 이름 — 글」 로 보인다: dashboard.js dashEndRows · 2026-11-23)
        "steps": [{k: s.get(k) for k in ("stage", "key", "doc", "status", "text")} for s in (rec.get("steps") or [])[-SUMMARY_STEPS:]]} if rec.get("ended") else {})


def runs_of(target):
    """그 목적 문서의 묶음에서 도는 실행들(번호 차례) — 두 문서를 다 쓰는 실행 하나, 또는 문서마다 따로 도는 실행 둘까지(② §18-22)."""
    return sorted((r for r in list(RUNS.values()) if r.target == target), key=lambda r: r.rec["n"])


def _live(target, n):
    """그 묶음에서 도는 그 번호의 실행 | None."""
    return next((r for r in runs_of(target) if r.rec["n"] == n), None)


def _holder(wid):
    """그 문서를 잡은 도는 실행 | None(잡히지 않음 — 같은 묶음의 다른 문서만 도는 중일 수 있다)."""
    key = BUSY.get(wid)
    return RUNS.get(key) if key else None


def _keep(target, rec):
    """메모리의 기록 사본(LAST) — 그 목적 문서의 새 것 몇 개만. `_LOCK` 안에서 부른다."""
    mem = LAST.setdefault(target, {})
    mem[rec["n"]] = rec
    for n in sorted(mem)[:-LAST_KEEP]:
        mem.pop(n, None)


def _numbers(target):
    got = list(UNIT.store.numbers(target))
    return sorted(set(got) | set(LAST.get(target) or ()) | {r.rec["n"] for r in runs_of(target)})   # 도는 실행의 번호도 — 같이 시작한 두 실행이 같은 번호를 받지 않게(첫 저장 전에도)


def _cut(target, rec):
    """`running` 으로 남았는데 지금 도는 실행이 아닌 기록 → `cut` 으로 고쳐 쓴다(서버가 다시 켜졌거나 실행 스레드가 죽음) → 고친 기록."""
    if not rec or rec.get("status") != "running":
        return rec
    if _live(target, rec.get("n")) is not None and rec.get("boot") == BOOT:
        return rec
    now = rec.get("now") or {}
    rec = {**rec, "status": "cut", "stopping": False, "ended": time.time(), "now": None,
           "cut": {"why": "서버가 다시 켜져 끊겼습니다" if rec.get("boot") != BOOT else "실행이 끊겼습니다", "at": now.get("key") or ""},
           "end": {"ok": False, "text": f"끊김 — 서버가 다시 켜져 {now.get('note') or '진행 중'}에서 멈췄습니다 · 끝난 단계는 그대로 · 남은 단계는 「한 번에 진행」 으로 잇습니다"}}
    with _LOCK:
        _keep(target, rec)
    UNIT.store.write(target, rec["n"], rec)
    UNIT.store.log(target, event="cut", n=rec["n"], at=rec["cut"]["at"])
    return rec


def record(target, n):
    """실행 기록 하나 | None(끊긴 것이면 고쳐서)."""
    live = _live(target, n)
    if live is not None:
        return dict(live.rec)
    rec = (LAST.get(target) or {}).get(n) or UNIT.store.read(target, n)
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
    잠금 없이 사전을 한 번 읽는다(편집 입구가 세션 잠금 안에서 불러도 교착이 없다).
    **묶음의 문서 모두**다 — 문서 하나만 잡은 실행(② §18-22)이 도는 동안 잡히지 않은 다른 문서도 초기화 · 지우기 · 칸 바꾸기는 못 한다(실행 기록은 목적 문서의 작업 폴더에 남고 · 문서 칸이 바뀌면 그 실행이 멈춘다).
    그 문서를 실행이 **잡았나**만 볼 때는 held_text(잡히지 않은 문서의 「건너뛰기」 …)."""
    if wid is not None and (wid in BUSY or (wid in MATES and any(r.target == MATES.get(wid) for r in list(RUNS.values())))):
        return BUSY_TEXT
    if project:
        for run in list(RUNS.values()):
            if (run.rec.get("scope") or [""])[0] == project:
                return BUSY_TEXT
    return ""


def held_text(wid):
    """그 문서를 도는 실행이 **잡았으면** 거절 글 | "" — 같은 묶음의 다른 문서만 도는 실행은 세지 않는다(문서마다 따로 도는 실행: ② §18-22). 그 문서 하나에만 닿는 설정(「LLM 검증·보완」 의 건너뛰기)이 묻는다."""
    return BUSY_TEXT if wid in BUSY else ""


def busy_other(wid, family=None):
    """그 문서가 도는 실행에 들었고 부르는 쪽이 **그 실행의 스레드가 아니면** 거절 글 | "" — 실행이 스스로도 부르는 끝점(취합의 배포 기준본 · 자동 지정 · LLM 검토 · 넣기 계획 · 반영 …)의 바쁨 막이:
    사람의 요청만 막는다(그 사이 등록 · 결정 · 계획이 바뀌면 실행의 계획이 낡는다 — ② §18-13 갈래 「다」). 잠금 없이 사전을 한 번 읽는다.
    family = 그 틀(가족)의 실행일 때만 — "single": 문서 하나의 실행이 도는 동안의 헤딩 추출 시작 · LLM 검증·보완 · 조정 반영 · 표 판정 · 프로젝트 구성 계획 · 반영(화면의 실행이 같은 문서에서 겹치지 않게).
    다른 틀(이관형 · 취합)의 실행 동안 그 끝점들은 전과 같다."""
    run = _holder(wid)
    if run is None or threading.get_ident() in getattr(run, "threads", ()):   # 실행의 스레드들 — 같은 차례의 두 문서 일을 함께 도는 스레드도(_lanes)
        return ""
    if family is not None and (S.family(run.task) if getattr(run, "task", None) else "") != family:
        return ""
    return BUSY_TEXT


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
    """**그 문서를 잡은** 도는 실행의 요약 | None — **메모리만**(세션을 열지 않고 디스크를 읽지 않는다: 확인 폴링). 같은 묶음의 다른 문서만 도는 실행은 여기 안 든다(live_all)."""
    run = _holder(wid)
    return run.summary() if run is not None else None


def live_all(wid):
    """그 문서의 묶음에서 도는 실행들의 요약(번호 차례 — 이 문서를 잡지 않은 실행도) — 메모리만(MATES: 도는 실행이 있는 묶음의 문서 → 목적 문서). 화면이 제가 따라가는 실행(번호)을 여기서 찾는다(② §18-22)."""
    target = MATES.get(wid)
    return [r.summary() for r in runs_of(target)] if target else []


def last_n(wid):
    """그 문서가 목적 문서인 마지막 실행의 번호 | None — 메모리만. 화면이 실행을 통째로 놓쳤을 때(숨긴 탭) 그 번호가 바뀐 것을 보고 문서를 다시 읽는다."""
    mem = LAST.get(wid)
    return max(mem) if mem else None


# ---------------------------------------------------------------- 실행
class Run:
    """도는 실행 하나 — rec = 실행 기록(사전 · 통째로 다시 쓴다) · working = 지금 일하는 문서 id 들 · threads = 이 실행의 스레드들(실행 스레드 + 같은 차례의 두 문서 일을 함께 도는 스레드: _lanes)."""

    def __init__(self, rec, task, pair, approval):
        self.rec, self.task, self.pair, self.approval = rec, task, pair, approval
        self._working = {}   # 스레드 → 그 스레드가 지금 일하는 문서 id 들(같은 차례의 두 줄이 서로의 것을 지우지 않게)
        self.threads = set()
        self.lock = threading.Lock()
        self.io = threading.Lock()   # 기록 쓰기의 차례(두 스레드가 함께 쓸 때 옛 사본이 새 사본을 덮지 않게)
        self.changed = set()   # 이 실행의 울타리 안에서 차례(rev)가 오른 문서 id 들 — 끝 확정이 고를 문서의 하나(② §18-24 「한 번에 진행 뒤 고친 문단 확정」 · Run.fence 가 더한다)

    @property
    def working(self):
        """지금 일하는 문서 id 들 — 이 실행의 모든 스레드의 것(서버의 `_admit` 이 비우지 않는다: pinned)."""
        return {d for docs in list(self._working.values()) for d in docs}

    @working.setter
    def working(self, docs):
        """처리 함수의 `run.working = {…}` — **부른 스레드의 몫**만 바꾼다(빈 것 = 그 스레드의 일이 끝남)."""
        if docs:
            self._working[threading.get_ident()] = set(docs)
        else:
            self._working.pop(threading.get_ident(), None)

    @property
    def target(self):
        return self.rec["docs"]["target"]["id"]

    @property
    def lane(self):
        """이 실행이 잡은 문서 — source | target(그 문서만: 다른 문서의 실행과 같이 돈다) · ""(두 문서를 다 쓴다 — 묶음에 하나뿐)(② §18-22)."""
        return self.rec.get("lane") or ""

    @property
    def key(self):
        """RUNS 의 열쇠 — 목적 문서 id(두 문서 · 목적 문서의 실행) · `<목적 id>/source`(원본 문서만 잡은 실행 — 목적 문서의 실행과 같이 돌 수 있다)."""
        return f"{self.target}/source" if self.lane == "source" else self.target

    def now(self):
        return self.rec.get("now")

    def summary(self):
        with self.lock:
            return _summary(self.rec)

    def save(self):
        with self.io:   # 사본을 뜨고 쓰기까지 한 차례로
            with self.lock:
                rec = dict(self.rec, steps=list(self.rec["steps"][-STEPS_MAX:]))
            with _LOCK:
                _keep(self.target, rec)
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
        raised, r0 = False, None
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
            raised, r0 = True, _rev_of(doc)   # 울타리를 올린 뒤의 차례 — 내리기 전에 견줘 이 실행이 그 문서를 바꿨는지 적는다(끝 확정이 고를 문서: ② §18-24)
            yield
        finally:
            if raised:
                try:
                    if _rev_of(doc) != r0:
                        with self.lock:
                            self.changed.add(doc)
                except Exception:  # noqa: BLE001 — 차례를 못 읽어도 울타리는 내린다(끝 확정은 범위의 줄로도 문서를 고른다)
                    pass
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
    for role in S.roles_on(run.task, line["on"]):   # 문서 하나인 워크플로우의 빈 on = 그 문서(목적 문서)
        d, r = run.pair.get(role), S._role(run.task, role)
        if d and r:
            out.append((d["id"], r["name"], role))
    return out


def _got(f):
    return bool(f and f["heads"]["s2"] and f["heads"]["s3"])


# ---- 같은 차례(한 행)의 두 문서 일을 함께 돈다(spec_워크플로우 ② §18-4 「같은 차례 — 함께 돌기」 — 2026-11-20 사용자 「이런 경우 병렬로 처리 하도록 해줘」: 전에는 원본 문서의 것 다음에 목적 문서의 것)
def _lanes(run, jobs):
    """jobs = [() → 결과](문서마다 하나 — 원본 → 목적 차례) → 결과 목록(준 차례). 하나면 그대로 부르고, 둘 이상이면 첫 것은 이 스레드에서 · 나머지는 새 스레드에서 **함께** 돈다.
    모든 몫이 끝날 때까지 기다린다(한쪽이 멈춰도 다른 쪽의 일은 끝까지 — 끝난 줄은 기록에 남는다). 그 뒤: 멈춤 요청(_Stop)이 있었으면 그것 · 사람이 봐야 할 멈춤(_Halt)이 있으면 그 글들을 이어 하나로(code · 멈춘 줄은 첫 것) ·
    그 밖의 오류는 첫 것을 다시 던진다. 새 스레드는 그동안 이 실행의 스레드다(바쁨 막이 busy_other · 일하는 문서 working 이 스레드마다)."""
    if len(jobs) == 1:
        return [jobs[0]()]
    out, errs = [None] * len(jobs), [None] * len(jobs)

    def work(i, mine):
        ident = threading.get_ident()
        if mine:
            run.threads.add(ident)
        try:
            out[i] = jobs[i]()
        except BaseException as e:  # noqa: BLE001 — 다른 몫이 끝난 뒤 아래에서 다시 던진다
            errs[i] = e
        finally:
            if mine:
                run.working = set()   # 이 스레드의 몫만
                run.threads.discard(ident)

    # 옆 줄 스레드는 이 스레드의 맥락(contextvars)의 사본에서 돈다 — 시작한 요청이 건 「지금 워크플로우」(에이전트에 덧붙이는 글의 전용 범위: app/agent_notes.py · spec_에이전트 ② §6)가 그 스레드의 LLM 호출에도 닿게(새 스레드는 맥락을 물려받지 않는다)
    more = [threading.Thread(target=contextvars.copy_context().run, args=(work, i, True), daemon=True, name=f"flow-lane-{run.rec.get('n')}-{i}") for i in range(1, len(jobs))]
    for t in more:
        t.start()
    work(0, False)
    for t in more:
        t.join()
    bad = [e for e in errs if e is not None]
    if not bad:
        return out
    if any(isinstance(e, _Stop) for e in bad):
        raise _Stop()
    other = next((e for e in bad if not isinstance(e, _Halt)), None)
    if other is not None:
        raise other
    if len(bad) == 1:
        raise bad[0]
    halt = _Halt(bad[0].code, " / ".join(dict.fromkeys(e.text for e in bad)))
    halt.at = bad[0].at
    raise halt


def _together(task, a, b):
    """잇달은 두 줄(a 다음 b)을 함께 돌아도 되나 — b 가 a 와 **같은 차례**(조립 화면의 같은 행: 정의의 `beside`)이고, 둘 다 실행기가 하는 문서 하나의 줄이며(문서가 서로 다름 · 원본 문서마다 도는 덩이가 아님),
    **한쪽이 바꾸는 문서를 다른 쪽이 읽지 않을 때**(단위의 change 가 doc 인 줄의 문서가 다른 줄의 reads 에 없다 — 구조 반영 · 작성요령 삭제 같은 문서를 바꾸는 줄과, 그 문서를 기준으로 보는 줄은 차례로).
    아니면 전처럼 차례로(a 먼저)."""
    ua, ub = a.get("unit"), b.get("unit")
    if not b.get("beside") or not ua or not ub or ua.get("each") or ub.get("each") or ua["place"] != "doc" or ub["place"] != "doc" or ua["kind"] == "pick" or ub["kind"] == "pick":
        return False
    ra, rb = S.roles_on(task, a["on"]), S.roles_on(task, b["on"])
    if len(ra) != 1 or len(rb) != 1 or ra[0] == rb[0]:
        return False
    return not ((U.changes(ua, ra[0]) and ra[0] in ub["reads"]) or (U.changes(ub, rb[0]) and rb[0] in ua["reads"]))   # 바꾸는가 = 그 문서 역할에서(U.changes — 1단계 LLM 줄의 목적 문서는 안 바뀐다)


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


def _llm_job(run, stage, key, d, name, start=None, what="LLM 검증·보완", note=None, done=None, stops=False):
    """그 문서의 「LLM 검증·보완」(배경 · 유료)을 걸고 끝날 때까지 기다린다 — 도는 다른 헤딩 작업이 있으면 그것이 끝난 뒤 한 번 더 건다 · 멈춤 요청이 오면 내가 건 이어 돌리기에 멈춤을 건다.
    시작 못 함 · 밀려남 · 시간 초과는 _Halt, 멈춤은 _Stop. 결과(거쳤나)는 부르는 쪽이 문서에서 다시 본다. start = 다른 배경 LLM 일을 거는 함수(문서 id → Outcome — 문서 하나의 서식 정리 계획 · 표 판정) ·
    what = 그 일의 이름 · note = 진행 글. → 끝난 **내** 작업의 보기 | None(걸지 않음 · 내 작업을 더는 볼 수 없음).
    - **유료 시작 직전마다** 멈춤 요청 · 대상을 다시 본다(guard — 부르는 쪽이 상태를 읽는 사이 온 멈춤이 새 호출을 내지 않게: astra B4).
    - done = 「이미 됐나」 를 문서에서 다시 보는 함수(() → 참 · 거짓): 도는 다른 헤딩 작업을 기다린 뒤 그 작업이 이 일을 이미 해 놓았으면 **다시 걸지 않는다**(같은 것을 또 유료로 부르지 않게 — astra B3:
      문서 하나의 줄이 준다. 안 주면 전처럼 한 번 더 건다 — 이관형의 이어 돌리기는 거친 것을 스스로 건너뛴다).
    - 기다리고 멈춤을 거는 것은 **내가 건 작업**뿐이다(시작 응답의 started 로 가린다 — 내 작업이 끝난 뒤 다른 작업이 그 자리에서 돌면 그것을 기다리거나 멈추지 않는다).
    - stops = 내 작업이 **사람의 멈춤**(문서 진행표의 「멈춤」)으로 끝났으면 실행도 멈춘다(_Stop — 그 뒤의 유료 호출을 잇지 않는다: 문서 하나의 줄이 켠다)."""
    begin = start or (lambda doc: UNIT.start_llm(doc, run.rec.get("skill")))
    run.working = {d}
    run.note(stage, key, note or f"{name} LLM 검증·보완 중(헤딩 · 템플릿 → 표 → 서식 정리 계획 · 몇 분)", d)
    run.guard()
    got = begin(d)
    if got.code == "busy":
        run.wait(d, WAIT["llm"], f"{name}의 헤딩 작업")
        if done is not None and done():   # 기다린 그 작업이 이미 해 놓았다 — 다시 걸지 않는다
            run.working = set()
            if run.stopping():
                raise _Stop()
            return None
        run.guard()   # 유료 시작 직전(위에서 문서를 다시 읽는 사이 온 멈춤도)
        got = begin(d)
    if not got.ok:
        raise _Halt(got.code, f"{name}의 {what}을(를) 시작하지 못했습니다 — {got.text}" if start else f"{name}의 LLM 검증·보완을 시작하지 못했습니다 — {got.text}")
    mine = got.data.get("started") if isinstance(got.data, dict) else None   # 내 작업의 표시(없으면 가리지 않는다 — 전처럼)
    other = lambda j: mine is not None and j.get("started") is not None and j["started"] != mine  # noqa: E731
    t0, asked, job = time.time(), False, None
    while True:   # 끝날 때까지 — 멈춤 요청이 오면 그 이어 돌리기에 멈춤을 건다(내가 시작한 것만)
        job = UNIT.job(d)
        if job.code == "missing":
            raise _Halt("evicted", "열린 문서가 많아 이 문서가 메모리에서 밀려났습니다 — 「한 번에 진행」 으로 이어서 하세요")
        if not job.data or job.data.get("status") != "running" or other(job.data):
            break
        if run.stopping() and not asked:
            UNIT.stop_llm(d)
            asked = True
        if time.time() - t0 > WAIT["llm"]:
            raise _Halt("timeout", f"{name}의 {what}{'이(가)' if start else '이'} 시간 안에 끝나지 않았습니다 — 다시 누르세요")
        time.sleep(WAIT["poll"])
    run.working = set()
    if run.stopping():
        raise _Stop()
    mine_job = job.data if job.data and not other(job.data) else None
    if stops and mine_job and mine_job.get("stopping"):   # 사람이 그 작업을 멈췄다(실행의 멈춤이 아니라) — 위로 전한다
        raise _Stop()
    return mine_job


def _do_heads_llm(run, stage, line):
    """LLM 검증·보완 — 그 줄의 문서마다: 이미 거쳤으면 지나감 · LLM 을 못 쓰거나 사람이 건너뛰었으면 「건너뜀」 · 승인 밖이면 남김 · 아니면 걸고 끝날 때까지 기다린다(유료 · 몇 분 — 문서는 안 바뀜).
    줄이 두 문서를 하면(같은 차례) 두 문서의 것을 **함께** 돈다(_lanes — 2026-11-20: 전에는 원본 문서의 것이 끝난 뒤 목적 문서의 것). 글은 문서 차례(원본 → 목적)대로."""
    llm, skip = UNIT.llm_ok(), set(UNIT.skips(run.target))

    def one(d, name, role):   # → (left | note | did | "", 글)
        run.guard()   # 유료 호출 전에 멈춤 요청 · 대상을 다시 본다
        f = UNIT.facts(d)
        if not _got(f):
            return "left", f"{name} LLM 검증·보완은 하지 않음(헤딩 · 표 분석이 먼저입니다 — 남은 단계)"
        if f["heads"]["llm"]:
            return _tidy_after(run, stage, line["key"], d, name, role)   # 이미 거친 문서 — 받은 계획이 지금 그래프의 것이고 남았으면 반영만
        if not llm:
            return "note", f"{name} LLM 검증·보완은 건너뜀(LLM 을 쓸 수 없음)"
        if d in skip:
            return "note", f"{name} LLM 검증·보완은 건너뜀(건너뛰기)"
        if run.approval is not None and d not in run.approval.get("paid", ()):
            return "left", f"{name} LLM 검증·보완은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)"
        _llm_job(run, stage, line["key"], d, name)
        f = UNIT.facts(d)
        if not (f and f["heads"]["llm"]):
            err = ((f or {}).get("heads", {}).get("job") or {}).get("error") or "LLM 이 답을 내지 못했습니다"
            raise _Halt("failed", f"{name}의 LLM 검증·보완이 끝나지 않았습니다 — {err}(다시 누르거나 그 줄의 「건너뛰기」)")
        k, t = _tidy_after(run, stage, line["key"], d, name, role)
        return ("left" if k == "left" else "did"), f"{name} LLM 검증·보완을 거쳤습니다" + (f" · {t}" if t else "")

    docs = _docs_of(run, line)
    out = _lanes(run, [functools.partial(one, d, name, role) for d, name, role in docs]) if docs else []
    left, notes = [t for k, t in out if k == "left"], [t for k, t in out if k in ("note", "did")]
    if left:
        return "left", " · ".join(left + notes)
    return ("done" if any(k == "did" for k, _ in out) else "nothing"), " · ".join(notes)   # 이미 거친 문서는 글이 없다(화면 실행의 끝 글과 같게)


def _tidy_after(run, stage, key, d, name, role):
    """LLM 검증·보완을 거친 그 문서에 받은 서식 정리 계획을 반영(조정 「모두 반영」 — _adjust_doc(fresh_only): 울타리 · 지금 그래프의 받은 계획이 있을 때만 · 처음 반영 전에는 유료로 계획을 새로 받지 않음)
    → (left | did | note | "", 글). 이관형만 · 문서 역할은 workflow_units.TIDY_ROLES(1단계 = 원본 문서 · 2단계 = 그 줄의 문서) — 그 밖은 아무것도 안 한다."""
    if S.family(run.task) != "relay" or role not in U.TIDY_ROLES.get(key, ()):
        return "", ""
    st, text, did = _adjust_doc(run, stage, key, d, name, fresh_only=True)
    if not text:
        return "", ""
    return ("left" if st == "left" else "did" if did["applies"] else "note"), f"{name} {text}"


HANDLERS = {"heads": _do_heads, "headsLlm": _do_heads_llm}   # 단위 key → 처리 함수(run, 묶음 id, 줄) → (done | nothing | left, 글) · 멈춤은 _Halt · _Stop
FAMILY_HANDLERS = {}   # 가족 → {단위 key: 처리 함수} — 줄 key 가 다른 틀과 겹치는 가족의 것(문서 하나의 plan · apply · heads …)이 먼저다(단위 · 상태 함수와 같은 차례)


def _handler(task, line):
    """그 줄의 처리 함수 — 사람이 하는 일(hand1 …)은 하나 · 그 가족의 단위면 가족의 표에서만(같은 key 의 다른 틀 처리 함수로 새지 않게) · 아니면 같이 쓰는 표."""
    u, fam = line["unit"], S.family(task)
    if u["kind"] == "hand":
        return HANDLERS["hand"]
    if U.FAMILIES.get(fam, {}).get(u["key"]) is u and fam in FAMILY_HANDLERS:
        return FAMILY_HANDLERS[fam][u["key"]]
    return HANDLERS[u["key"]]


def _line(run, gid, line):
    """줄 하나의 처리 함수를 부른다 — 부르는 동안 「지금 도는 줄」(가족 · 줄 key)을 맥락에 건다(`S.LINE`): 그 줄이 부르는 LLM 호출에 그 도구에 적어 둔 내용이 붙는다(app/agent_notes.py — spec_에이전트 ② §6).
    맥락 변수라 같은 차례의 옆 줄 스레드와 섞이지 않는다(스레드마다 제 사본)."""
    token = S.LINE.set((S.family(run.task), line["unit"]["key"]))
    try:
        return _handler(run.task, line)(run, gid, line)
    finally:
        S.LINE.reset(token)


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
    fn = (_TAILS.get(g.get("module")) or (_tail_gather if S.family(task) == "gather" else None)) if g is not None else None
    return fn(task, g, R) if fn else ""


def _tail_gather(task, g, R):
    """취합 묶음의 끝 글 꼬리 — 화면 실행(gather.js gatherRunConfig · gatherRunFrame)의 글 그대로: 구성 확정 묶음 = 「 · 구조는 2단계 「문서 프레임 작성」 에서 맞춥니다」 ·
    기준본 묶음 = 「 · 내용은 3단계 「내용 매핑」 에서 넣습니다」(그 일을 하는 묶음이 이 정의에 있을 때 · 줄 하나만 돌 때는 없음)."""
    if R.get("only"):
        return ""
    keys = {s["key"] for s in g["steps"]}
    want = ("apply", "내용은", "넣습니다") if "frame" in keys else ("division", "구조는", "맞춥니다") if "config" in keys and "division" not in keys else None
    nxt = next((x for x in task["stages"] if x["id"] != g["id"] and any(s["key"] == want[0] for s in x["steps"])), None) if want else None
    if nxt is None:
        return ""
    no, name = S.stage_label(nxt)
    return f" · {want[1]} {no} 「{name}」 에서 {want[2]}"


def _stage_lines(task, gid):
    return [x for x in S.lines(task) if x["stage"] == gid]


def _only_lines(mine, only, row):
    """줄 하나만(only) 돌 때의 줄들 — 그 key 의 줄 · row 면 같은 차례(행)에 선 옆 줄도(실행 _drive 와 시작의 검사가 같은 줄을 본다)."""
    hit = {i for i, x in enumerate(mine) if x["key"] == only}
    if row:
        hit |= {i + 1 for i in hit if i + 1 < len(mine) and mine[i + 1].get("beside")} | {i - 1 for i in hit if i > 0 and mine[i].get("beside")}
    return [x for i, x in enumerate(mine) if i in hit]


def _role_lines(task, mine, role):
    """「한 문서만 진행」(spec_워크플로우 ② §18-21 — 2026-11-21 사용자 「목적문서 따로 원본 문서 작업 따로 … 하나의 문서만 작업」)의 줄들 — 그 문서만 따로 돌 수 있는 줄(workflow_state.solo_line: 문서마다 하는 줄 가운데 그 문서에 닿는 것)만 남기고,
    줄의 「하는 문서」 를 그 문서 하나로 좁힌 사본을 준다(처리 함수는 줄이 고른 문서마다 돈다 — _docs_of · _fit_docs). 워크플로우 전체 줄 · 원본 → 목적 줄 · 다른 문서만의 줄은 빠진다. 옆 줄과 함께 돌기(beside)는 없다 — 문서가 하나다."""
    return [{**x, "on": role, "beside": False} for x in mine if S.solo_line(task, x["unit"], x["on"], role)]


def _solo_row(row, role):
    """묶음 상태(workflow_state.view 의 줄)에서 그 문서만의 몫 {total, left, can, why, …} | None(이 묶음에 따로 돌 것이 없음)."""
    return next((x for x in row.get("solo") or () if x["role"] == role), None)


def _view(run):
    """묶음 경계의 상태 — 실행의 판단이라 새로 읽은 재료로(잠깐 든 값이 아니라 · 이번 실행의 뺀 자리로: _materials)."""
    return S.view(run.task, run.pair, _materials(run.pair, run.task, fresh=True, excl=_excl(run.rec)), llm=UNIT.llm_ok(), skip=UNIT.skips(run.target))


def _range_lines(task, span, only="", row=False, role=""):
    """그 범위의 실행이 돌 줄들(묶음 차례 · 줄 차례) — 줄 하나만(only · row 면 같은 차례의 옆 줄도) · 한 문서만(role)으로 좁힌 것. 시작(잡을 문서 — lane)과 실행(_drive)이 같은 줄을 본다."""
    out = []
    for gid in span:
        mine = _stage_lines(task, gid)
        if only:
            mine = _only_lines(mine, only, row)
        if role:
            mine = _role_lines(task, mine, role)
        out += mine
    return out


def _clash(a, b):
    """서로 다른 문서의 두 줄 a · b = (역할, 단위)를 같이 돌면 안 되나 — **한쪽이 바꾸는 문서를 다른 쪽이 읽을 때**(단위의 change 가 doc 인 줄의 문서가 다른 줄의 reads 에 있다 — _together 와 같은 조건)."""
    (ra, ua), (rb, ub) = a, b
    return (U.changes(ua, ra) and ra in ub["reads"]) or (U.changes(ub, rb) and rb in ua["reads"])


@contextlib.contextmanager
def _turn(run, gid, line):
    """문서 하나만 잡은 실행이 줄 하나를 도는 차례(② §18-22 「옆 실행과 겹치는 줄」) — 같은 묶음의 **다른 문서의 실행**이 지금 도는 줄과 겹치면(_clash — 한쪽이 바꾸는 문서를 다른 쪽이 읽는다:
    원본 문서의 구성 반영 ∥ 목적 문서의 구성 반영 …) 그 줄이 끝날 때까지 기다린 뒤 돈다(같은 실행 안의 「같은 차례 — 함께 돌기」 가 그런 두 줄을 차례로 도는 것과 같다). 겹치지 않으면 바로.
    자리(CLAIMS)는 한 잠금 안에서 보고 잡는다 — 기다리는 실행은 잡은 자리가 없어 서로 기다리다 멈추지 않는다. 기다리는 동안 멈춤 요청 · 대상 바뀜을 본다(guard). 두 문서를 다 쓰는 실행은 옆 실행이 없어 그대로 지난다."""
    u, lane = line["unit"], run.lane
    if not lane or u["place"] != "doc":
        yield
        return
    me, n, told = (lane, u), run.rec["n"], False
    while True:
        with _LOCK:
            mine = CLAIMS.setdefault(run.target, {})
            if not any(_clash(me, c) for k, c in mine.items() if k != n):
                mine[n] = me
                break
        run.guard()   # 기다리는 동안 — 멈춤 요청 · 문서 칸이 그대로인가
        if not told:
            told = True
            run.note(gid, line["key"], f"{line['name']} — 다른 문서의 실행이 이 문서를 보는(또는 바꾸는) 단계를 마칠 때까지 기다리는 중")
        time.sleep(WAIT["poll"])
    try:
        if told:
            run.note(gid, line["key"], line["name"])
        yield
    finally:
        with _LOCK:
            mine = CLAIMS.get(run.target) or {}
            mine.pop(n, None)
            if not mine:
                CLAIMS.pop(run.target, None)


def _release(run):
    """끝난(또는 끊긴) 실행을 내린다 — 실행 · 잡은 문서 · 줄의 차례(CLAIMS) · 그 묶음에 도는 실행이 더 없으면 묶음의 문서 표(MATES)도. `_LOCK` 안에서 부른다."""
    key = run.key
    if RUNS.get(key) is run:
        RUNS.pop(key, None)
    for d in [d for d, k in BUSY.items() if k == key]:
        BUSY.pop(d, None)
    (CLAIMS.get(run.target) or {}).pop(run.rec.get("n"), None)
    if not any(r.target == run.target for r in RUNS.values()):
        CLAIMS.pop(run.target, None)
        for d in [d for d, t in MATES.items() if t == run.target]:
            MATES.pop(d, None)


# ---- 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」 — 2026-11-22 사용자 「대쉬보드에서 이어서 하기나 하넌에 진행하는 경우, 고친문단을 자동으로 확정해줘,」)
# 묶음째 실행(범위에 only 가 없다)이 끝남 · 남김으로 끝나면 끝 글을 짓기 전에 한 번 — 그 실행이 바꿀 수 있는 문서(_commit_docs) 가운데 고친 것이 있는 문서를 그 실행의 울타리 안에서 확정한다(문 UNIT.commit → server._commit_now).
# 멈춤 · 멈춤 누름 · 오류는 확정하지 않는다(멈춤은 사람이 볼 계획을 남길 수 있다 — 확정이 구조 반영 계획을 비운다). 화면에 반영 못 한 글 · 대상 바뀜 · 멈춤을 누름은 확정만 건너뛰고 실행의 끝 상태는 그대로다.
_COMMIT_WHY = {"dirty": "그 문서를 연 화면에 반영하지 못한 글이 있음", "moved": "도는 중에 문서 칸이 바뀜"}


def _commit_on(run):
    """이 실행이 끝에 확정하는 실행인가 — 묶음째 실행(범위에 only 가 없다)이고 문이 확정을 안다(문에 commit 이 없는 옛 가짜 문은 조용히 건너뛴다). 끝 상태(끝남 · 남김)는 _drive 가 따로 본다."""
    return not (run.rec.get("range") or {}).get("only") and callable(getattr(UNIT, "commit", None)) and callable(getattr(UNIT, "commit_info", None))


def _held_docs(run):
    """그 실행이 잡은 문서 → [(문서 id, 역할, 이름(역할의 문서 이름))] — 원본 → 목적 차례. 문서 하나만 잡은 실행(lane)은 그 문서만 · 취합의 기관 문서(원본 문서 여럿)는 아니다(실행 기록의 source 는 원본 문서 하나뿐)."""
    docs, out = run.rec.get("docs") or {}, []
    for role in U.ROLES:
        d = docs.get(role) or {}
        if d.get("id") and (not run.lane or run.lane == role):
            r = S._role(run.task, role) if run.task else None
            out.append((d["id"], role, (r or {}).get("name") or d.get("name") or d["id"]))
    return out


def _commit_docs(run):
    """끝에 확정할 문서 후보 → [(문서 id, 역할, 이름)] — 잡은 문서 가운데 ⓐ 실행이 들어간 묶음(실행 기록의 stages)에서 **실행기가 하는**(auto) **문서를 바꾸는**(change doc) 줄이 닿는 문서
    (문서마다의 줄 = 그 줄의 문서 · 「한 문서만」 은 그 문서로 좁힌 줄 · 원본 → 목적 줄 · 원본 문서마다의 덩이 = 목적 문서) ∪ ⓑ 이 실행의 울타리 안에서 차례가 오른 문서(Run.changed).
    ⓐ 가 있어 앞 실행(멈춘 실행 · 「이 단계만 진행」)이 남긴 고침도 함께 확정된다 — 그 줄이 이번에 한 일이 없어도(② §18-24 「어느 문서」)."""
    task, role, roles = run.task, (run.rec.get("range") or {}).get("role") or "", set()
    for gid in dict.fromkeys(g.get("id") for g in run.rec.get("stages") or ()):
        mine = _stage_lines(task, gid)
        if role:
            mine = _role_lines(task, mine, role)
        for x in mine:
            u = x.get("unit") or {}
            if u.get("kind") != "auto" or u.get("change") != "doc":
                continue
            roles |= {"target"} if u.get("place") == "pair" or u.get("each") else {r for r in S.roles_on(task, x["on"]) if U.changes(u, r)}   # 서식 정리를 반영하는 LLM 줄은 그 역할만(U.TIDY_ROLES — 1단계 「LLM 검증·보완」 의 목적 문서는 아님)
    with run.lock:
        changed = set(run.changed)
    return [(d, r, name) for d, r, name in _held_docs(run) if r in roles or d in changed]


def _pre_edits(run):
    """실행을 시작할 때 이미 고친 문단 수 {문서 id: 수}(잡은 문서 가운데 고친 것이 있는 문서만) — 끝 확정의 메시지에 「실행 전부터 고친 문단 n 포함」 으로 적는다."""
    out = {}
    for doc, _, _ in _held_docs(run):
        try:
            info = UNIT.commit_info(doc)
        except Exception:  # noqa: BLE001 — 못 읽으면 적지 않는다(확정은 끝에 다시 본다)
            info = None
        if info and info.get("edited"):
            out[doc] = int(info["edited"])
    return out


def _commit_label(run):
    """확정 메시지의 범위 — 「2단계 「구성 맞추기」 한 번에 진행」 · 「2단계 「…」 → 4단계 「…」 이어서 한 번에」 · 「1단계 「…」 — 원본 문서(사업계획서)만」(대시보드의 진행 줄과 같은 말)."""
    R, task = run.rec["range"], run.task
    by = {g["id"]: g for g in task["stages"]}

    def name(gid):
        no, nm = S.stage_label(by.get(gid) or {})
        return f"{no} 「{nm or gid}」".strip()
    if R.get("role"):
        return f"{name(R['from'])} — {_who(task, R['role'])}만"
    if R.get("to") and R["to"] != R["from"]:
        return f"{name(R['from'])} → {name(R['to'])} 이어서 한 번에"
    return f"{name(R['from'])} 한 번에 진행"


def _commit_end(run, gid):
    """끝 확정 → 실행 기록의 commits[{doc, role, name, status, n, parent, count, pre, why}] — 후보 문서(_commit_docs)마다 원본 → 목적 차례로:
    문(commit_info — 메모리 · 세션 잠금 안)으로 먼저 보고 저장이 꺼짐 = off · 고친 것 없음 = nothing(울타리를 세우지 않는다) · 아니면 **그 실행의 울타리 안에서** 확정 = ok.
    울타리를 기다리다 시간이 다 됨 · 대상이 바뀜 = skipped · 멈춤을 누름 = skipped(남은 문서도) · 그 밖의 오류 = failed — 실행의 끝 상태는 그대로다.
    에이전트 카드가 시작한 실행은 카드가 유료로 승인한 문서만 새 기준의 가져오기 검증이 검증 LLM 을 부른다(llm — 사람이 누른 실행은 손으로 누른 확정과 같다)."""
    out, pre, n, stop = [], run.rec.get("pre") or {}, run.rec["n"], False
    for doc, role, name in _commit_docs(run):
        row = {"doc": doc, "role": role, "name": name, "status": "", "n": None, "parent": None, "count": 0, "pre": int(pre.get(doc) or 0), "why": ""}
        out.append(row)
        if stop:
            row.update(status="skipped", why="멈춤을 누름")
            continue
        got = None
        try:
            info = UNIT.commit_info(doc)
            if info is None:
                row.update(status="failed", why="문서를 읽지 못함")
            elif not info.get("stored"):
                row["status"] = "off"
            elif not info.get("dirty"):
                row["status"] = "nothing"
            else:
                msg = f"워크플로우 실행 {n} — {_commit_label(run)}" + (f"(실행 전부터 고친 문단 {U.nf(row['pre'])} 포함)" if row["pre"] else "")
                allow = run.approval is None or doc in (run.approval.get("paid") or ())
                run.working = {doc}
                run.note(gid, "", f"{name} 고친 문단 확정 중", doc)
                run.guard()
                with run.fence(doc):   # 화면들의 고치던 글을 먼저 받고 사람 편집을 막는다 — 확정은 이 스레드만 지난다(server._fenced)
                    got = UNIT.commit(doc, msg[:200], flow=n, llm=allow)
        except _Stop:
            row.update(status="skipped", why="멈춤을 누름")
            stop = True
        except _Halt as e:
            row.update(status="skipped", why=_COMMIT_WHY.get(e.code) or _clip(e.text))
        except Exception as e:  # noqa: BLE001 — 확정 하나가 죽어도 실행의 끝은 적는다
            import logging
            logging.getLogger("uvicorn.error").exception("[워크플로우 실행] 끝 확정 오류")
            row.update(status="failed", why=_clip(f"{type(e).__name__}: {e}")[:120])
        finally:
            run.working = set()
        if got is None:
            continue
        if got.code == "ok":
            d = got.data if isinstance(got.data, dict) else {}
            row.update(status="ok", n=d.get("n"), parent=d.get("parent"), count=int(((d.get("counts") or {}).get("total")) or 0))
        elif got.code == "nothing":
            row["status"] = "nothing"
        else:
            row.update(status="skipped" if got.code == "blocked" else "failed", why=_clip(got.text) or got.code)
    return out


_TAIL_NAME, _TAIL_WHY = 24, 40   # 끝 글 꼬리의 문서 이름 · 까닭 길이(자) — 둘 다 못 한 두 문서 + 안내도 200 자 안팎(TEXT_MAX 240 — 앞 글에 몫이 남는다)


def _brief(text, k):
    s = " ".join(str(text or "").split())
    return s if len(s) <= k else s[:k - 1] + "…"


def _commit_tail(commits):
    """끝 글의 꼬리(② §18-24 「글」) — 「 · 확정 8(연차보고서 — 고친 문단 1,234 · 앞 상태 = 확정 7)」 · 둘이면 「 · 확정 — 사업계획서 3 · 연차보고서 8」 ·
    못 하면 「 · 확정하지 않음(이름 — 까닭) · 반영은 「실행 취소」 로 되돌릴 수 있습니다 — 「고친 문단」 탭에서 확정」 | ""(확정할 것이 없었음 · 저장이 꺼짐).
    이름은 _TAIL_NAME · 까닭은 _TAIL_WHY 자까지(오류 글은 길다 — 실행 기록의 why 는 그대로) — 문서 둘이 다 못 해도 꼬리가 TEXT_MAX 안에 들어 앞 글만 잘리게(_end_text)."""
    oks = [c for c in commits or () if c.get("status") == "ok"]
    bad = [c for c in commits or () if c.get("status") in ("skipped", "failed")]
    parts = []
    if len(oks) == 1:
        c = oks[0]
        prev = "올린 원본" if c.get("parent") == 0 else f"확정 {c['parent']}" if c.get("parent") else ""
        parts.append(f"확정 {c['n']}({_brief(c['name'], _TAIL_NAME)} — 고친 문단 {U.nf(c.get('count') or 0)}" + (f" · 앞 상태 = {prev}" if prev else "") + ")")
    elif oks:
        parts.append("확정 — " + " · ".join(f"{_brief(c['name'], _TAIL_NAME)} {c['n']}" for c in oks))
    if bad:
        parts.append("확정하지 않음(" + " · ".join(f"{_brief(c['name'], _TAIL_NAME)} — {_brief(c.get('why') or '까닭 모름', _TAIL_WHY)}" for c in bad)
                     + ") · 반영은 「실행 취소」 로 되돌릴 수 있습니다 — 「고친 문단」 탭에서 확정")
    return (" · " + " · ".join(parts)) if parts else ""


def _end_text(body, tail):
    """끝 글 — 꼬리(끝 확정)가 늘 들도록 앞 글을 잘라 TEXT_MAX 안에."""
    body = " ".join(str(body or "").split())
    if not tail:
        return _clip(body)
    room = TEXT_MAX - len(tail)
    if room < 24:   # 꼬리가 너무 길다(문서 이름이 긴 두 문서의 까닭) — 통째로 자른다
        return _clip(body + tail)
    return (body if len(body) <= room else body[:room - 1] + "…") + tail


def _drive(run):
    run.thread = threading.get_ident()   # 이 실행의 스레드 — 실행이 스스로 부르는 끝점의 바쁨 막이가 이 실행의 스레드만 지나가게 한다(busy_other — 같은 차례의 두 줄을 함께 도는 스레드는 _lanes 가 더한다)
    run.threads.add(run.thread)
    rec, R = run.rec, run.rec["range"]
    ids = [g["id"] for g in run.task["stages"]]
    span = ids[ids.index(R["from"]): ids.index(R["to"]) + 1]
    status, texts, halt = "done", [], None
    role = R.get("role") or ""   # 「한 문서만 진행」 — 그 문서(원본 | 목적)의 줄만(② §18-21)
    eyes = role or run.lane   # 앞 묶음의 남은 일을 세는 눈 — 문서 하나만 잡은 실행(한 문서만 · 문서 하나의 줄뿐인 묶음 · 줄: ② §18-22)은 그 문서의 눈으로
    who = S._role(run.task, role) if role else None
    only_doc = f"{(who or {}).get('title') or ''}({(who or {}).get('name') or ''})만 — " if who else ""   # 묶음 끝 글의 머리 「원본 문서(사업계획서)만 — 」
    commits = None   # 끝 확정의 결과(묶음째 실행이 끝남 · 남김일 때 — ② §18-24)
    if _commit_on(run):
        rec["pre"] = _pre_edits(run)   # 실행 전부터 고친 문단 — 끝 확정의 메시지에 적는다
    try:
        for gid in span:
            run.guard()
            view = _view(run)
            rows = {g["id"]: g for g in view["stages"]}
            row = rows[gid]
            if not view["ready"]:
                raise _Halt("notReady", view["why"])
            # 앞 묶음이 덜 끝남 — 뒤 묶음은 하지 않고 남긴다 · 줄 하나(줄의 단추 — 화면의 early)는 묶음 차례를 안 따진다. 먼저 끝나야 하는 묶음 = 그 묶음의 after(이관형 = 모든 앞 묶음 — 범위 밖도 ·
            # 문서 하나 = 이 묶음의 줄이 요구하는 것을 주는 묶음만: workflow_state._feeds) + 이 실행의 범위에 든 앞 묶음(「이어서 한 번에」 는 안 끝난 묶음에서 멈춘다 — ② §18-13 「묶음 규칙」)
            must = set(row.get("after") or ()) | set(span[:span.index(gid)])
            # 문서 하나만 잡은 실행(「한 문서만」 · 문서 하나의 줄뿐인 묶음)이면 앞 묶음의 남은 일을 그 문서의 눈으로 센다(leftBy — 다른 문서만의 줄은 기다리지 않는다: 문서마다의 몫은 따로 나아간다 · 전체 줄 · 원본 → 목적 줄은 기다린다)
            left_of = (lambda g: (g.get("leftBy") or {}).get(eyes, g["left"])) if eyes else (lambda g: g["left"])
            before = None if R.get("only") else next((g for g in view["stages"][:ids.index(gid)] if g["server"] and left_of(g) and g["id"] in must), None)
            if before is not None:
                cut = f"{before['no']} 「{before['name']}」 이 덜 끝났습니다".strip()   # 번호 없는 묶음(양식 맞추기)은 이름만
                run.step(gid, "", "left", cut)
                texts.append(cut)   # 끝 글에도 — 전에는 이 까닭이 줄의 기록에만 남아 끝 글이 「남은 단계가 없습니다」 였다
                status = "left"
                break
            if not R.get("only") and not R.get("redo") and not ((_solo_row(row, role) or {}).get("left") if role else row["left"]):
                rec["stages"].append({"id": gid, "status": "done", "text": only_doc + "남은 단계가 없습니다", "t0": time.time(), "t1": time.time()})
                continue
            entry = {"id": gid, "status": "running", "text": "", "t0": time.time(), "t1": None}
            rec["stages"].append(entry)
            UNIT.store.log(run.target, event="stage", n=rec["n"], stage=gid)
            got, block, paired = [], [], None
            mine = _stage_lines(run.task, gid)
            if R.get("only"):   # 줄 하나만(「분석」)이면 그 줄만 — 뒤의 유료 줄을 시작하지 않는다 · row = 그 줄의 **차례(행)째**: 같은 차례에 선 옆 줄도(시작한 쪽이 그 행을 보이고 눌렀을 때만 — 줄의 단추는 그 줄만)
                mine = _only_lines(mine, R["only"], R.get("row"))
            if role:   # 한 문서만 — 그 문서의 줄만 · 줄의 문서도 그 문서 하나로
                mine = _role_lines(run.task, mine, role)

            def one(line, gid=gid):   # 줄 하나 — 처리 함수를 부르고 기록한다 → (상태, 묶음 끝 글의 몫). 멈춤에는 그 줄을 적는다(같은 차례의 두 줄을 함께 돌 때 「지금 줄」 은 다른 줄일 수 있다)
                t0 = time.time()
                run.note(gid, line["key"], line["name"])
                try:
                    with _turn(run, gid, line):   # 다른 문서의 실행이 지금 도는 줄과 겹치면 그 줄이 끝난 뒤에(② §18-22)
                        res = _line(run, gid, line)   # 사람이 하는 일(hand1 …)은 처리 함수 하나 — 「했음」 이면 지나가고 아니면 멈춘다   # (st, 글) | (st, 글, 묶음 끝 글의 몫) — 줄의 기록 글과 묶음 끝 글의 몫이 다를 때 셋째(없으면 글 그대로)
                except _Halt as e:
                    if e.at is None:
                        e.at = (gid, line["key"])
                    raise
                st, text = res[0], res[1]
                run.working = set()
                run.step(gid, line["key"], st, text, t0=t0)
                return st, res[2] if len(res) > 2 else text

            for i, line in enumerate(mine):
                if line is paired:
                    continue   # 앞 줄과 함께 돌았다(같은 차례)
                u = line["unit"]
                if u.get("each"):   # 원본 문서마다 한 덩이로 도는 줄(취합) — 잇달은 그 줄들을 모아 원본 문서 하나에 끝까지 한 뒤 다음 문서로(② §18-4 「잇달은 pair 줄」)
                    block.append(line)
                    if i + 1 == len(mine) or not mine[i + 1]["unit"].get("each"):
                        got.append(_each(run, gid, block))
                        block = []
                    continue
                if u["kind"] == "pick":
                    continue   # 사람이 고르는 줄(준비) — 실행기는 지나간다
                nxt = mine[i + 1] if i + 1 < len(mine) else None
                paired = nxt if nxt is not None and _together(run.task, line, nxt) else None   # 같은 차례(한 행)의 다른 문서 줄 — 서로의 문서를 건드리지 않으면 함께 돈다(② §18-4 「같은 차례 — 함께 돌기」)
                run.guard()
                got += _lanes(run, [functools.partial(one, x) for x in ([line, paired] if paired is not None else [line])])
            lefts = [t for st, t in got if st == "left"]
            entry.update(status="left" if lefts else "done", text=_clip(only_doc + (" · ".join(t for _, t in got if t) or "한 일이 없습니다") + ("" if role else _tail(run.task, gid, R))), t1=time.time())   # 한 문서만 돈 묶음은 다음 묶음을 가리키는 꼬리를 붙이지 않는다(묶음이 끝난 것이 아니다)
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
    if status in ("done", "left") and _commit_on(run):   # 끝 확정 — 문서들은 아직 이 실행이 잡고 있다(BUSY · 이 스레드: ② §18-24 「언제」)
        try:
            commits = _commit_end(run, rec["stages"][-1]["id"] if rec["stages"] else R["from"])
        except Exception:  # noqa: BLE001 — 끝 확정이 죽어도 실행의 끝은 적는다
            import logging
            logging.getLogger("uvicorn.error").exception("[워크플로우 실행] 끝 확정 오류")
            commits = []
    with run.lock:
        if commits is not None:
            rec["commits"] = commits
        for g in rec["stages"]:
            if g["status"] == "running":
                g.update(status="halted" if status in ("halted", "failed") else "stopped" if status == "stopped" else g["status"], t1=time.time(), text=_clip(halt.text) if halt else g["text"])
        if halt is not None:
            at = halt.at or (now.get("stage") or "", now.get("key") or "")   # 멈춘 줄 — 처리 함수가 멈췄으면 그 줄(함께 돌던 다른 줄이 아니라) · 묶음 경계의 멈춤은 지금 줄
            rec["halt"] = {"stage": at[0], "key": at[1], "code": halt.code, "text": _clip(halt.text)}
        word = {"done": "끝남", "left": "남김", "halted": "멈춤", "stopped": "멈춤", "failed": "오류"}[status]
        tail = halt.text if halt is not None else "멈춤을 눌러 멈췄습니다 — 끝난 단계는 그대로입니다" if status == "stopped" else " / ".join(texts) or "남은 단계가 없습니다"
        ctail = _commit_tail(commits)
        rec.update(status=status, stopping=False, ended=time.time(), now=None, end={"ok": status in ("done", "left"), "text": _end_text(f"{word} — {tail}", ctail),   # 꼬리(끝 확정)는 240자 안에 늘 든다
                                                                                    **({"tail": ctail.removeprefix(" · ")} if ctail else {})})   # 끝 확정만 따로(끝 글 띠의 풍선 — 「끝 확정 — …」 줄)
    with _LOCK:
        _release(run)
    run.working = set()
    run.save()
    UNIT.store.log(run.target, event={"halted": "halt", "stopped": "stop"}.get(status, "end"), n=rec["n"], status=status, text=rec["end"]["text"])
    src = (rec["docs"].get("source") or {}).get("id")
    if src:
        UNIT.store.log(src, event="end", n=rec["n"], status=status, role="source", target=run.target)


def start(wid, body):
    """실행을 시작한다 → 실행 요약(202). 못 하면 Refuse(409 — reason · message) · ValueError(400 — 몸의 꼴).
    body = {from(묶음 id), to?, only?(줄 key), row?(참 = only 의 줄과 같은 차례(행)에 선 옆 줄도 함께), role?(source | target — **한 문서만**: 그 묶음에서 그 문서의 줄만 · 줄의 문서도 그 문서 하나로 — ② §18-21), redo?, skill?, skip?[구조 반영에서 뺄 자리 key], by?(human | agent), where?, screen?, turn?, key?, paid?[문서 id], sig?, docs?{target, source}}.
    검사 차례(② §17-7 「시작」): 문서 묶음(notReady · docs) → 정의(gone · definition) → 서버가 맡는 묶음(client) → 사람이 직접 하는 줄만 고른 시작(pick — only 의 줄이 모두 사람의 줄) → 남은 일(noWork — 새로 읽은 재료로) → 겹침(busy).
    skip 을 실으면(빈 목록도) 「이번 실행이 뺀 자리」 로 안다 — 문서 하나의 구조 반영은 지난 반영이 뺀 자리를 이번에 풀었으면 다시 계획한다 · 안 실으면 지난 반영이 뺀 자리를 그대로 둔다(뺀 자리를 모르는 화면이 저절로 반영하지 않게)."""
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
    role = body.get("role") or ""   # 「한 문서만 진행」(② §18-21) — 그 묶음에서 그 문서(원본 | 목적)의 줄만. only 와 함께면 그 줄을 그 문서에만
    if role and (role not in U.ROLES or to != first or not S.relay_pair(task)):
        raise ValueError("한 문서만 진행은 원본 문서 하나 → 목적 문서 하나인 워크플로우의 묶음 하나에서, 원본 문서(source) 또는 목적 문서(target)로 합니다")
    if body.get("skip") is not None and (not isinstance(body["skip"], list) or len(body["skip"]) > SKIP_MAX or not all(isinstance(x, str) for x in body["skip"])):
        raise ValueError(f"skip 은 뺄 자리 key 목록({SKIP_MAX}개까지)이어야 합니다")   # 자르면 사람이 뺀 자리가 반영된다 — 거절한다(astra P1)
    auto = body.get("auto")
    if auto is not None and (not isinstance(auto, list) or len(auto) > SKIP_MAX or not all(isinstance(x, str) for x in auto)):
        raise ValueError("auto 는 문서 id 목록이어야 합니다")   # 취합의 간단 모드 — 이번에 올린 문서(반영할 기관을 자동 지정할 문서)
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
    if only:   # 줄 하나만 — 그 줄(row 면 같은 차례의 옆 줄도)이 모두 사람이 직접 하는 줄이면 실행기가 할 일이 없다: 아무 일 없이 「끝남」 으로 남기지 않고 시작을 거절한다(astra C2)
        hit = _only_lines(_stage_lines(task, first), only, bool(body.get("row")))
        if hit and all((x["unit"] or {}).get("kind") == "pick" for x in hit):
            raise Refuse("pick", f"{' · '.join('「' + x['name'] + '」' for x in hit)} 은(는) 사람이 직접 하는 단계입니다 — 서버가 대신 진행하지 않습니다(문서 화면에서 합니다)")
    who = S._role(task, role) if role else None
    who_text = f"{(who or {}).get('title') or ''}({(who or {}).get('name') or ''})" if who else ""
    if role and not _role_lines(task, _only_lines(_stage_lines(task, first), only, bool(body.get("row"))) if only else _stage_lines(task, first), role):
        raise Refuse("role", f"{who_text}만 따로 진행할 단계가 여기에는 없습니다 — 워크플로우 전체 줄 · 원본 → 목적 줄은 한 문서만으로 하지 않습니다")
    target, source = pair["target"], pair.get("source")
    given = body.get("skip") is not None   # 시작한 화면이 「반영에서 빼기」 의 자리를 알려 주었나(빈 목록 = 뺀 자리 없음 · 키가 없으면 모름 — 지난 반영이 뺀 자리를 그대로 둔다: _excl)
    # 「남은 일 없음」 은 실행의 판단 — 새로 읽은 재료로 센다(잠깐 든 값은 조회에만: astra C1)
    view = S.view(task, pair, _materials(pair, task, fresh=True, excl=list(body["skip"]) if given else None), llm=UNIT.llm_ok(), skip=_skips(pair, wid))
    rows = {g["id"]: g for g in view["stages"]}
    wait = ""   # 구성 값을 기다리는 줄에서 시작하는 실행은 시작하지 않는다(② §18-22 「구성 값 — 추출될 때까지」 — 2026-11-21 사용자 「그 값이 추출돌때까지 실행이 되면 안되고」: 전에는 시작한 뒤 그 줄에서 멈췄다)
    if role and not only:   # 그 문서만 — 남은 일 · 앞 묶음은 그 문서의 눈으로(서버가 센 solo: workflow_state.view)
        solo = _solo_row(rows[first], role)
        if solo is None:
            raise Refuse("role", f"이 묶음은 {who_text}만 따로 진행할 것이 없습니다 — 묶음의 「한 번에 진행」 과 같습니다")
        if not body.get("redo") and not solo["left"]:
            raise Refuse("noWork", f"{who_text}에 남은 단계가 없습니다")
        wait = solo.get("wait") or ""
    elif not body.get("redo") and not only and not any(rows[g]["left"] for g in span):
        raise Refuse("noWork", "남은 단계가 없습니다")
    elif only:   # 줄 하나만 — 실행기가 할 줄이 모두 기다리는 줄일 때
        waits = [next((s.get("wait") or "" for s in rows[first]["steps"] or () if s["key"] == x["key"]), "") for x in hit if (x["unit"] or {}).get("kind") != "pick"]
        wait = waits[0] if waits and all(waits) else ""
    else:
        wait = rows[first].get("wait") or ""
    if wait and not body.get("redo"):
        raise Refuse("needs", wait)
    by = "agent" if body.get("by") == "agent" else "human"
    approval = {"paid": [d for d in body.get("paid") or [] if isinstance(d, str)]} if by == "agent" else None   # 사람이 누른 실행은 제한 없음 · 에이전트 카드는 승인한 문서에만 유료
    sources = [d for d in pair.get("sources") or () if d]   # 취합 — 원본 문서들(등록한 차례 — 시작할 때 못 박는다: 공통 자리는 먼저 넣는 문서가 차지한다 · ② §18-13)
    docs = [d["id"] for d in (target, source, *sources) if d]
    # 잡을 문서(② §18-22 「문서마다 따로 도는 실행」) — 이 실행이 돌 줄이 모두 한 문서의 줄이면 그 문서만 잡는다(lane — 다른 문서의 실행과 같이 돈다) · 아니면 묶음의 문서 모두(그런 실행은 묶음에 하나뿐)
    lane = role or S.lane_of(task, _range_lines(task, span, only, bool(body.get("row"))))
    holds = [(source if lane == "source" else target)["id"]] if lane else docs
    with _LOCK:
        hit = next((BUSY[d] for d in holds if d in BUSY), None)
        if hit is None and not lane:   # 두 문서를 다 쓰는 실행 — 같은 묶음에서 문서 하나만 잡고 도는 실행이 있어도 못 한다(잡은 문서가 겹친다 — 위에서 걸리지만 열쇠로도 본다)
            hit = next((r.key for r in RUNS.values() if r.target == target["id"]), None)
        if hit is not None:
            other = RUNS.get(hit)
            mate = other is not None and bool(other.lane) and other.lane != lane   # 다른 문서만 잡은 실행 때문에 — 「다른 화면」 이 아니라 그 까닭
            raise Refuse("busy", f"{_who(task, other.lane)}의 실행이 도는 중입니다 — 이 단계는 두 문서를 함께 씁니다(끝나거나 멈춘 뒤에 하세요)" if mate else "다른 화면에서 진행 중입니다 — 끝나거나 멈춘 뒤에 하세요",
                         other.summary() if other is not None else None)
        n = (_numbers(target["id"]) or [0])[-1] + 1
        rec = {"v": 1, "n": n, "boot": BOOT, "job": pair["job"], "sig": sig, "scope": pair["scope"], **({"lane": lane} if lane else {}),   # lane = 이 실행이 잡은 문서(그 문서만 — 없으면 두 문서)
               "docs": {"target": {"id": target["id"], "name": target["name"]}, "source": {"id": source["id"], "name": source["name"]} if source else None,
                        **({"sources": [{"id": d["id"], "name": d["name"]} for d in sources]} if sources else {})},
               # 취합의 간단 모드(화면 gather_quick.js 의 입력을 실행 기록에 — ② §18-13 ⓔ): quick = 구조를 맞추려면 지워야 하는 곳이 있으면 멈춘다 · auto = 이번에 올린 문서(미지정이면 반영할 기관을 자동 지정) · llm false = LLM 검토를 끔
               **({"quick": True} if body.get("quick") is True else {}), **({"auto": list(auto)} if auto else {}), **({"llm": False} if body.get("llm") is False else {}),
               "range": {"from": first, "to": to, "only": only, "redo": body.get("redo") or "", **({"row": True} if only and body.get("row") else {}),   # row = only 의 줄과 같은 차례(행)에 선 옆 줄도 함께(② §18-4 「같은 차례 — 함께 돌기」)
                         **({"role": role} if role else {})},   # role = 한 문서만(그 문서의 줄만 — ② §18-21)
               "origin": {"by": by, "where": str(body.get("where") or "")[:20], "screen": str(body.get("screen") or "")[:40], **({"turn": body["turn"]} if isinstance(body.get("turn"), (str, int)) else {}),
                          **({"key": str(body["key"])[:200]} if body.get("key") else {})},
               "approval": approval, "skill": body.get("skill") if isinstance(body.get("skill"), str) else None,
               "skip": [x for x in body.get("skip") or () if isinstance(x, str)],   # 구조 반영에서 뺄 자리(화면의 「반영에서 빼기」 — 화면에만 있던 입력: ② §17-11 ⓙ · LLM 「건너뛰기」 와 다르다). 자르지 않는다(위에서 수를 거절)
               **({"skipGiven": True} if given else {}),   # 뺀 자리를 알려 준 시작(빈 목록도) — 문서 하나의 구조 반영이 「지난 반영이 뺀 자리를 이번에도 빼나」 를 이것으로 가린다(_excl)
               "status": "running", "stopping": False, "started": time.time(), "ended": None, "now": None, "stages": [], "steps": [], "left": [], "halt": None, "end": None, "cut": None}
        run = Run(rec, task, pair, approval)
        RUNS[run.key] = run
        for d in holds:
            BUSY[d] = run.key
        for d in docs:
            MATES[d] = target["id"]   # 묶음의 문서(잡지 않은 문서도) → 목적 문서 — 확인 폴링이 이 묶음의 도는 실행들을 찾는다(live_all)
    run.save()
    UNIT.store.log(target["id"], event="start", n=n, **{k: rec["range"][k] for k in ("from", "to", "only", "role") if rec["range"].get(k)}, **({"lane": lane} if lane and lane != role else {}), by=by)
    if source:
        UNIT.store.log(source["id"], event="start", n=n, role="source", target=target["id"])
    # 실행 스레드는 시작한 요청의 맥락(contextvars)의 사본에서 돈다 — 요청이 건 「지금 워크플로우」(주소의 작업 → 그 작업의 워크플로우 = 이 실행의 것: app/agent_notes_api.py Scope)가 이 실행의 LLM 호출에 닿아 그 워크플로우 전용 덧붙이는 글이 붙는다(spec_에이전트 ② §6)
    threading.Thread(target=contextvars.copy_context().run, args=(_drive, run), daemon=True, name=f"flow-{target['id']}-{n}").start()
    return run.summary()


def stop(wid, n=None):
    """멈춤(어느 화면에서나) — 지금 하는 일이 끝나면 멈춘다 → {stopping} | None(도는 실행이 없음 · 번호가 다름)."""
    run = _holder(wid)
    if n is not None and (run is None or run.rec["n"] != n):   # 같은 묶음의 다른 문서만 잡은 실행 — 번호로 찾는다(문서마다 따로 도는 실행: ② §18-22 · 어느 문서의 화면에서나 멈춘다)
        target = run.target if run is not None else MATES.get(wid)
        run = _live(target, n) if target else None
    if run is None:
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
            RUNS.pop(run.key, None)
        _cut(run.target, rec)


# ---------------------------------------------------------------- 3단계 「내용 넣기」 · 4단계 「문서 정리」(걸음 3: spec_워크플로우 ② §18-2 「3 · 4단계 단위의 글」 · §18-12 ② · ③)
# 화면 app.js taskRunMap · taskRunSteps 의 clean 가지를 줄마다의 처리 함수로 옮긴 것 — 차례 = 자리 연결 → (LLM 검토) → 넣기 계획 → (빈 자리 검토 → 표 대응) → 내용 반영 · 작성요령 삭제.
# 이번 실행 안의 기억(연결 목록 · 반영할 수 있는 지금 계획 · LLM 검토의 글)은 run.fill — 끝남은 늘 문서에서 다시 본다(workflow_units 의 상태 식). 묶음 끝 글 = 화면 실행의 글 그대로(셋째 값 — 줄의 기록 글과 따로).
FILL_KEYS = ("link", "llm", "plan", "gaps", "tableMap", "apply", "guide", "guideFix", "zonePrune", "capUnify", "retidy")
NOTHING_TEXT = "넣을 것이 없습니다(이미 넣었거나 넣을 자리가 없음)"


def _fill_need(task):
    """이 정의에 서버가 맡는 넣기 · 정리 줄이 있나 — 이관형의 단위일 때만(문서 하나의 plan · apply 는 key 만 같은 다른 단위다: 그 문서에 연결 목록을 읽지 않는다)."""
    mine = {**U.RELAY, **{k: U.COMMON[k] for k in ("guide", "guideFix", "zonePrune", "capUnify")}}   # 「문서 정리」 의 줄(작성요령 삭제 · 조립 도구 — ② §18-23)도 「내용 넣기」 의 끝을 재료로 읽는다
    return any(x["key"] in FILL_KEYS and x["unit"] is mine.get(x["key"]) and S.served(task, x["stage"]) for x in S.lines(task))


def _has_fill(task):
    """이 정의에 「내용 넣기」 의 줄이 있나 — 줄의 단위가 사는 단계(home)로 가린다(묶음의 module 이 아니라: 조립 v2 의 묶음은 여러 단계의 줄을 섞는다). 반영 줄을 뺐어도 넣기 줄이 있으면 참(② §18-12 ②)."""
    return any((x["unit"] or {}).get("home") == "stage_fill" for x in S.lines(task))


def _fill_materials(task, pair, facts, opt=None):
    """목적 문서 facts 에 넣기 재료(`fill` — unit_steps.fill_facts + 이 정의의 묶음 이름)를 얹는다 — 서버가 맡는 묶음에 넣기 · 정리 줄이 있을 때만(상태 조회마다 연결 목록을 읽지 않게)."""
    t = (pair.get("target") or {}).get("id")
    if not t or facts.get(t) is None or not _fill_need(task):
        return
    F = UNIT.fill_facts(t)
    if F is not None:
        F = {**F, "fills": _has_fill(task), "lines": [x["key"] for x in S.lines(task)], "stages": {g["module"]: {"id": g["id"], "no": g.get("no") or "", "name": g.get("name") or ""} for g in task["stages"] if g.get("module")}}   # stages = 글의 묶음 이름만
    facts[t] = {**facts[t], "fill": F}


MATERIALS.append(_fill_materials)


def _clean_materials(task, pair, facts, opt=None):
    """원본 문서 facts 에 지울 양식 안내의 수(`cleanup{counts | None, patterns, error}` — 목적 문서의 fill.cleanup 과 같은 꼴)를 얹는다 — 「작성요령 삭제」 를 원본 문서에 놓은 이관형 정의에서만
    (② §18-2 「원본 문서에 놓는 줄」 — 그 줄이 없는 정의는 원본 문서를 세지 않는다)."""
    s = (pair.get("source") or {}).get("id")
    if not s or facts.get(s) is None or not any(x["key"] == "guide" and x["unit"] is U.COMMON["guide"] and "source" in S.roles_on(task, x["on"]) and S.served(task, x["stage"]) for x in S.lines(task)):
        return
    c = UNIT.cleanup_count(s)
    C = c.data if c.ok and isinstance(c.data, dict) else None
    facts[s] = {**facts[s], "cleanup": {"counts": C.get("counts"), "patterns": [{"key": p["key"], "name": p["name"]} for p in C.get("patterns") or ()], "error": ""} if C
                else {"counts": None, "patterns": [], "error": c.text or "응답이 없음"}}


MATERIALS.append(_clean_materials)


def _scratch(run):
    """이번 실행의 넣기 기억 — L(연결 목록) · plan(반영할 수 있는 지금 계획 보기 | None = 없음 · 무름) · llmNote · none(정상 0건) · linked(묶음 끝 글의 앞머리)."""
    f = getattr(run, "fill", None)
    if f is None:
        f = run.fill = {"L": None, "plan": None, "llmNote": "", "none": False, "linked": ""}
    return f


def _names(run):
    s, t = S._role(run.task, "source"), S._role(run.task, "target")
    return (s or {}).get("name") or "원본 문서", (t or {}).get("name") or "목적 문서"


def _pair_ids(run):
    return (run.pair.get("source") or {}).get("id"), run.target


def _range_stages(run):
    ids, R = [g["id"] for g in run.task["stages"]], run.rec["range"]
    return ids[ids.index(R["from"]): ids.index(R["to"]) + 1]


def _stage_paid_ok(run, gid):
    """묶음째 유료(「내용 넣기」 의 LLM 셋)를 이 묶음에서 불러도 되나 — 사람이 누른 실행은 늘 · 에이전트 카드는 승인한 묶음(approval.stagePaid — 없으면 카드가 승인한 범위의 묶음)."""
    ap = run.approval
    if ap is None:
        return True
    allowed = ap.get("stagePaid")
    if isinstance(allowed, (list, tuple)):
        return gid in allowed
    R = run.rec["range"]   # 승인한 묶음이 적혀 있지 않은 카드 — 그 묶음 하나만 도는 카드일 때만(요청 범위를 넓혀 유료 줄을 늘리지 못하게: astra 결과 검토)
    return R["from"] == R["to"] == gid


def _tries_unknown(run, key, ver):
    """지난 실행이 같은 입력(판)으로 이 유료 줄을 부르다 끊겨 결과를 모르는가(시도를 적었는데 답이 안 적힘) — 그러면 「이어서」 가 저절로 다시 부르지 않는다(② §18-4 「한 번」 · 사람의 단추로만)."""
    if not ver:
        return False
    for n in reversed(_numbers(run.target)):   # 새 것부터 — 같은 줄 · 같은 판의 시도를 처음 만난 것이 그 판의 마지막 사정(그 뒤 다시 불러 답을 저장했으면 불명이 아니다)
        if n == run.rec["n"]:
            continue
        rec = record(run.target, n) or {}
        hit = [t for t in rec.get("tries") or () if t.get("key") == key and t.get("ver") == ver]
        if hit:
            return hit[-1].get("status") == "started"
    return False


def _try_mark(run, gid, key, ver, status):
    """유료 호출의 시도를 실행 기록에(줄 · 문서 쌍 · 입력의 판) — started(부르기 직전 · 기록을 쓴다) → saved | failed(답이 온 뒤). 그 사이 서버가 꺼지면 started 로 남아 「결과 불명」 이 된다."""
    src, tgt = _pair_ids(run)
    with run.lock:
        tries = run.rec.setdefault("tries", [])
        hit = next((t for t in tries if t["key"] == key and t["ver"] == ver and t["status"] == "started"), None) if status != "started" else None
        if hit is not None:
            hit.update(status=status, t1=time.time())
        else:
            tries.append({"stage": gid, "key": key, "pair": [src, tgt], "ver": ver, "status": status, "t0": time.time()})
    run.save()


def _paid_call(run, gid, key, name, button, call, failed_of=None):
    """묶음째 유료 LLM 한 번(선택 줄) → (Outcome | None(LLM 을 쓸 수 없어 부르지 않음), 남김 글 | "").
    승인 밖은 선택 줄에서도 멈춤 · 지난 실행의 결과 불명이면 부르지 않고 남김(② §18-4) · 부르기 직전에 멈춤 요청 · 대상을 다시 본다."""
    if not UNIT.llm_ok():
        return None, ""
    if not _stage_paid_ok(run, gid):
        raise _Halt("approval", f"{name}은(는) 실행 카드에서 승인한 유료 호출이 아닙니다 — 카드에서 다시 승인하세요")
    ver = UNIT.fill_ver(run.target)
    if _tries_unknown(run, key, ver):
        return None, f"{name}은(는) 하지 않음(지난 실행이 끊겨 같은 호출의 결과를 모릅니다 — 「{button}」 단추로 다시 · 남은 단계)"
    run.guard()
    _try_mark(run, gid, key, ver, "started")
    got = call()
    _try_mark(run, gid, key, ver, "saved" if got.ok and not (failed_of and failed_of(got.data or {})) else "failed")
    return got, ""


def _net_analyze(run, todo):
    """안전망의 분석(스크립트) — todo = [(문서 id, 이름, "first" | "again")] · first = 첫 분석(있는 단계는 건너뜀) · again = 구조 반영 뒤 다시(2단계 → 3단계: 화면 taskRunReanalyze). 같이 걸고 함께 기다린다."""
    def begin(d, name, how):
        got = UNIT.start_heads(d, how)
        if got.code == "busy":   # 도는 다른 헤딩 작업 — 끝난 뒤 한 번 더
            run.wait(d, WAIT["heads"], f"{name}의 헤딩 작업")
            got = UNIT.start_heads(d, how)
        if not got.ok:
            raise _Halt(got.code, f"{name}의 헤딩 · 표 분석을 시작하지 못했습니다 — {got.text}")
    def ended(d, name, what):   # 기다린 작업이 실패했으면 멈춘다 — 옛 분석이 남아 있어도 그것으로 잇지 않는다(astra 결과 검토)
        job = run.wait(d, WAIT["heads"], f"{name}의 {what}")
        if job and (job.get("error") or job.get("status") == "failed"):
            raise _Halt("failed", f"{name}의 {what}이 실패했습니다 — {job.get('error') or '까닭 모름'}(「헤딩 추출」 탭에서 확인)")
    run.working = {d for d, _, _ in todo}
    for d, name, how in todo:
        begin(d, name, "first" if how == "first" else 2)
    for d, name, how in todo:
        ended(d, name, "헤딩 · 표 분석")
        if how == "again":
            run.guard()
            begin(d, name, 3)
            ended(d, name, "표 구조 분석")


def _links_read(run, S_, D_):
    """연결 목록을 읽는다 — 못 읽거나 막는 까닭이 있으면 멈춤(화면 linkBad → taskHalt 와 같은 글)."""
    got = UNIT.links(run.target)
    L = got.data if got.ok else None
    if not got.ok:
        raise _Halt(got.code, f"연결 목록을 읽지 못했습니다: {got.text}")
    if U.links_bad(L):
        raise _Halt("blocked", U.links_why(L, S_, D_))
    _scratch(run)["L"] = L
    return L


def _do_link(run, gid, line):
    """② 자리 연결 — (안전망: 분석 없음 → 첫 분석 · 목적 문서의 구조 반영 전 스크립트 분석 → 2 · 3단계 다시 — 그 밖의 숨은 실행은 없다) → 연결 목록.
    성공 = 막는 까닭 없는 두 문서 + 유효한 목록(확인 필요가 남아도 — 뒤의 LLM 검토로: ② §18-12 ②)."""
    (S_, D_), (src, tgt) = _names(run), _pair_ids(run)
    run.working = {src, tgt}
    fs, ft, fill = UNIT.facts(src), UNIT.facts(tgt), UNIT.fill_facts(tgt)
    if fs is None or ft is None or fill is None:
        raise _Halt("missing", "문서를 읽지 못했습니다 — 다시 누르세요")
    old = bool((fill.get("heads") or {}).get("old"))
    # 원본 문서의 구조도 이 정의가 바꾸면(「프로젝트 구성 반영」 을 원본 문서에 놓음 — ② §18-2 「원본 문서에 놓는 줄」) 원본의 구조 반영 전 스크립트 분석도 같은 안전망으로 다시(LLM 을 거친 옛 분석은 그대로 — 목적 문서의 old 와 같은 기준).
    # 그 줄이 없는 정의는 전과 같다(원본 문서의 분석을 다시 돌리지 않는다).
    stale_src = lambda f: (lambda sf: U.heads_stale(sf) and not U.heads_kept(sf))({**f, "div": UNIT.div_facts(src)}) if _got(f) else False  # noqa: E731
    sold = any(x["key"] == "division" and x["unit"] is U.COMMON["division"] and "source" in S.roles_on(run.task, x["on"]) for x in S.lines(run.task)) and stale_src(fs)
    todo = ([(d, n, "first") for d, n, f in ((src, S_, fs), (tgt, D_, ft)) if not _got(f) and not (old and d == tgt)] + ([(src, S_, "again")] if sold else []) + ([(tgt, D_, "again")] if old else []))
    net = ""
    if todo:
        net = "헤딩·표 분석(스크립트) — " + " · ".join(n if how == "first" else f"{n}(구조 반영 뒤 다시)" for _, n, how in todo)
        run.note(gid, "link", net)
        _net_analyze(run, todo)
        if not (_got(UNIT.facts(src)) and _got(UNIT.facts(tgt))):
            raise _Halt("failed", "헤딩·표 분석 결과가 생기지 않았습니다 — 「헤딩 추출」 탭에서 확인하세요")
        if old and ((UNIT.fill_facts(tgt) or {}).get("heads") or {}).get("stale"):   # 다시 분석했는데 여전히 구조 반영 전 것 — 늘어난 절 · 표를 못 잇는다
            raise _Halt("failed", f"{D_}를 다시 분석했지만 분석이 구조 반영 뒤의 것이 되지 않았습니다 — 「헤딩 추출」 탭에서 확인하세요")
        if sold and stale_src(UNIT.facts(src)):
            raise _Halt("failed", f"{S_}를 다시 분석했지만 분석이 구조 반영 뒤의 것이 되지 않았습니다 — 「헤딩 추출」 탭에서 확인하세요")
        run.working = {src, tgt}
    run.guard()
    run.note(gid, "link", "연결 목록")
    L = _links_read(run, S_, D_)
    return "done", (f"안전망 — {net} · " if net else "") + f"연결 목록 — {U.links_count_text(L)}", ""


def _do_link_llm(run, gid, line):
    """자리 연결 LLM 검토(선택 · 묶음째 유료 · 한 번) — 확인 필요나 못 정한 표가 있고 아직 검토 전일 때만(사람이 고른 연결은 안 바뀐다).
    서비스 실패는 남기고 목록을 다시 읽어 확실한 자리로 계속 · 막는 까닭이 생기면 멈춤."""
    F, (S_, D_), (src, tgt) = _scratch(run), _names(run), _pair_ids(run)
    run.working = {src, tgt}
    L = F["L"] or _links_read(run, S_, D_)
    amb, open_t = L["counts"].get("ambiguous") or 0, U.links_open_tables(L)
    if not (amb or open_t) or U.links_llm_ok(L):   # 검토를 한 번 거쳤다(모든 단위가 실패한 검토는 거친 것이 아니다 — 새 실행이 다시 부른다)
        return "nothing", "", ""
    run.note(gid, "llm", f"LLM 검토 — 확인 필요 {amb}곳 · 못 정한 표 {open_t}개(수십 초)")
    got, left = _paid_call(run, gid, "llm", "자리 연결 LLM 검토", "LLM 검토", lambda: UNIT.links_llm(tgt), failed_of=lambda d: not U.links_llm_ok(d))
    if left:
        F["llmNote"] = f" · {left}"
        return "left", left, ""
    if got is None:
        F["llmNote"] = " · LLM 검토는 못 함(확인 필요한 자리는 비워 둠)"
        return "done", "LLM 을 쓸 수 없어 건너뜀 — 확인 필요한 자리는 비워 둡니다", ""
    if got.code in ("blocked", "missing"):
        raise _Halt(got.code, f"자리 연결 LLM 검토를 하지 못했습니다 — {got.text}")
    L2 = _links_read(run, S_, D_)   # 저장된 것을 다시 읽는다(화면과 같다 — 실패해도 확실한 자리로)
    if not U.links_llm_ok(L2):   # 답이 없거나 모든 단위가 실패(HTTP 200 이어도) — 남김
        F["llmNote"] = " · LLM 검토는 못 함(확인 필요한 자리는 비워 둠)"
        return "left", f"자리 연결 LLM 검토는 못 함({got.text or '답을 받지 못함'}) — 확인 필요한 자리는 비워 둡니다 · 「LLM 검토」 단추로 다시", ""
    return "done", "LLM 검토 — " + U.links_llm_text(L2).removeprefix(" · ") + f" · {U.links_count_text(L2)}", ""


def _plan_now(run, gid, note):
    """넣기 계획을 새로 세운다(옛 계획은 끝점이 버린다) → 계획 보기. 못 세우면 멈춤 — 성공 = 반영할 수 있는 계획 id(② §18-12 ②)."""
    F = _scratch(run)
    F["plan"] = None
    run.guard()
    run.note(gid, "plan", note)
    got = UNIT.fill_plan(run.target)
    if not got.ok or not isinstance(got.data, dict) or not got.data.get("planId"):
        raise _Halt(got.code if not got.ok else "failed", f"넣기 계획을 세우지 못했습니다 — {got.text or '계획이 없습니다'}")
    F["plan"] = got.data
    return got.data


def _plan_of(run, gid, note):
    F = _scratch(run)
    return F["plan"] if F["plan"] is not None else _plan_now(run, gid, note)


def _do_plan(run, gid, line):
    """③ 넣기 계획 — 정상 0건(막는 까닭 · 같은 이름 자리의 판정 오류를 가른 뒤)이면 계획하지 않고 끝 · 아니면 새 계획. 첫 계획의 넣을 것이 0 이어도 여기서 끝내지 않는다 —
    빈 자리 · 못 맞춘 표가 열려 있으면 그 선택 줄을 먼저 하고 마지막 계획으로 정한다(내용 반영 줄 — ② §18-12 ②)."""
    F, (S_, D_), (src, tgt) = _scratch(run), _names(run), _pair_ids(run)
    run.working = {src, tgt}
    L = F["L"] or _links_read(run, S_, D_)
    fill = UNIT.fill_facts(tgt) or {}
    amb = L["counts"].get("ambiguous") or 0
    F["linked"] = linked = (f"연결됨 {L['counts'].get('paired') or 0}" + (f" · 확인 필요 {amb}(비워 둠)" if amb else "") + F["llmNote"]
                            + (" · 헤딩·표 분석은 구조 반영 전 것(LLM 결과라 다시 안 돌림 — 늘어난 절·표는 못 이었을 수 있음)" if (fill.get("heads") or {}).get("kept") else ""))
    if U.links_none(L):
        F["none"] = True
        return "nothing", "이어진 자리가 없어 넣을 내용이 없습니다", f"이어진 자리가 없어 넣을 내용이 없습니다({linked})"
    p = _plan_now(run, gid, "넣기 계획")
    return "done", f"넣기 계획 — {U.fill_count_text(p)}", linked


def _opt_paid(run, gid, line, *, key, name, button, open_of, call, note_of, note, plan_note, failed_of=lambda res: False):
    """빈 자리 검토 · 표 대응(선택 · 묶음째 유료 · 한 번) — 지금 계획에 열린 자리가 있을 때만. 끝나면 계획을 무른다(다음에 계획을 쓰는 줄 앞에서 새로 — ② §18-4 「무르기」).
    LLM 을 못 쓰면 글만 · 서비스 실패는 남기고 계속 · 막는 까닭이 생기면 멈춤."""
    F, (src, tgt) = _scratch(run), _pair_ids(run)
    run.working = {src, tgt}
    if F["none"]:
        return "nothing", "", ""
    p = _plan_of(run, gid, plan_note)
    n = open_of(p) or 0
    if not n:
        return "nothing", "", ""
    run.note(gid, key, note(n))
    got, left = _paid_call(run, gid, key, name, button, lambda: call(tgt), failed_of=failed_of)
    if left:
        return "left", left, left
    if got is None:
        text = note_of(None)
        return "done", text, text
    F["plan"] = None   # 무르기 — 부른 뒤에는 늘 새 계획으로(실패해도 일부 답 · 표 짝이 저장됐을 수 있다: astra 결과 검토)
    if got.code in ("blocked", "missing"):
        raise _Halt(got.code, f"{name}를 하지 못했습니다 — {got.text}")
    bad = not got.ok or failed_of(got.data or {})   # 끝점은 200 인데 모든 단위(표)가 실패한 것도 실패
    text = note_of(None if bad else got.data)
    if bad:
        return "left", f"{text} — {got.text or '모든 호출이 실패했습니다'} · 「{button}」 단추로 다시", text
    return "done", text, text


def _do_gaps(run, gid, line):
    """빈 자리 검토(LLM) — 다른 길이 못 채운 빈 표 · 빈 칸 · 빈 라벨 줄 가운데 아직 안 물은 것(지금 계획의 gaps.counts.open)."""
    return _opt_paid(run, gid, line, key="gaps", name="빈 자리 검토", button="빈 자리 검토(LLM)", open_of=lambda p: ((p.get("gaps") or {}).get("counts") or {}).get("open"),
                     call=UNIT.fill_gaps, note_of=U.fill_gap_note, note=lambda n: f"빈 자리 검토(LLM) — 아직 빈 자리 {n}곳(수십 초)", plan_note="넣기 계획",
                     failed_of=lambda res: bool(res.get("asked")) and bool(res.get("units")) and all(u.get("error") for u in res["units"]))   # 모든 장(단위)의 호출이 실패


def _do_table_map(run, gid, line):
    """표 대응(LLM) — 같은 표로 이었는데 행 · 열 구성이 달라 칸을 못 맞춘 표(지금 계획의 maps.counts.open — 빈 자리 검토가 새로 정한 표 쌍도: 차례 고정)."""
    return _opt_paid(run, gid, line, key="tableMap", name="표 대응", button="표 대응(LLM)", open_of=lambda p: ((p.get("maps") or {}).get("counts") or {}).get("open"),
                     call=UNIT.fill_maps, note_of=U.fill_map_note, note=lambda n: f"표 대응(LLM) — 행·열 구성이 다른 표 {n}개(표마다 십수 초)", plan_note="넣기 계획(빈 자리 검토 뒤)",
                     failed_of=_maps_failed)


def _maps_failed(res):
    """표 대응의 답이 모두 호출 실패인가 — 물은 표(호출 기록이 있는 줄)가 있고 그 호출이 모두 오류(LLM 이 답했지만 못 맞춘 표는 실패가 아니다)."""
    calls = [t["call"] for t in res.get("tables") or () if isinstance(t.get("call"), dict)]
    return bool(res.get("asked")) and bool(calls) and all(c.get("error") for c in calls)


def _do_apply(run, gid, line):
    """④ 내용 반영(문서를 바꾼다 — 울타리 안에서) — 마지막 계획으로: 넣을 것 0 이면 반영하지 않고 끝(끝점이 「확인된 정상 0건」 표식만 남긴다) ·
    낡은 계획(409)이면 같은 입력으로 한 번만 다시 계획해 반영(둘째 충돌은 멈춤) · 표준 검사가 되돌리면(422) 멈춤."""
    F, (src, tgt) = _scratch(run), _pair_ids(run)
    run.working = {src, tgt}
    if F["none"]:
        return "nothing", "", ""
    p = _plan_of(run, gid, "넣기 계획(표 대응 뒤)")
    for attempt in (0, 1):
        if p.get("todo"):
            run.guard()
            run.note(gid, "apply", "내용 반영")
            with run.fence(tgt):
                got = UNIT.fill_apply(tgt, p["planId"])
        else:
            got = UNIT.fill_apply(tgt, p["planId"])   # 넣을 것 0 — 문서는 안 바뀐다(울타리 없이)
        if got.code != "stale" or attempt:
            break
        p = _plan_now(run, gid, "넣기 계획(계획 뒤 문서가 바뀌어 다시)")
    F["plan"] = None
    if got.code == "nothing":
        return "nothing", NOTHING_TEXT, NOTHING_TEXT
    if got.ok:
        text = U.fill_done_text(got.data or {})
        return "done", text, text
    if got.code == "stale":
        raise _Halt("stale", f"내용을 반영하지 못했습니다 — 다시 계획한 뒤에도 문서가 바뀌었습니다({got.text}) · 다시 누르세요")
    if got.code == "rejected":
        raise _Halt("rejected", f"내용을 반영하지 못했습니다 — 표준 검사에 걸려 되돌렸습니다: {got.text}")
    raise _Halt(got.code, f"내용을 반영하지 못했습니다 — {got.text}")


def _do_guide(run, gid, line):
    """⑥ 작성요령 삭제 — 그 줄이 닿는 문서마다(원본 → 목적: _guide_doc). 목적 문서만의 줄은 글이 전과 같고, 원본 문서가 들면 문서 이름을 붙인다."""
    docs = _fit_docs(run, line)
    out = [(name, *_guide_doc(run, gid, d)) for _role, d, name in docs]
    text = out[0][2] if len(out) == 1 and docs[0][0] == "target" else " · ".join(f"{name} — {t}" for name, _st, t in out)
    return ("done" if any(st == "done" for _n, st, _t in out) else "nothing"), text, text


def _guide_doc(run, gid, tgt):
    """⑥ 작성요령 삭제(문서 하나 — 문서를 바꾼다: 울타리 안에서 다시 세고 지운다) — 「내용 넣기」 를 함께 고른 정의는 그 끝(반영 · 확인된 정상 0건 — 목적 문서의 넣기 재료) 뒤에만(그 줄을 뺐어도 — ② §18-12 ②).
    지우기 전 작성 지침 저장이 실패하면 끝점이 지우지 않는다(멈춤) · 센 뒤 문서가 바뀌면(409) 한 번만 다시 센다. tgt = 지울 문서(목적 · 원본 — 줄이 고른 문서). → (done | nothing, 글)."""
    run.working = {tgt}
    if _has_fill(run.task) and not U.fill_done(UNIT.fill_facts(run.target)):
        raise _Halt("order", f"{_stage_name(run.task, 'stage_fill', '내용 넣기')} 이 먼저입니다 — ④ 내용 반영 전")
    c = UNIT.cleanup_count(tgt)
    if not c.ok:
        raise _Halt(c.code, f"지울 안내를 세지 못했습니다: {c.text}")
    C = c.data
    if not (C.get("counts") or {}).get("total"):
        return "nothing", "지울 안내가 없습니다"
    run.note(gid, "guide", "양식 안내 지우기 — " + " · ".join(p["name"] for p in C.get("patterns") or ()), tgt)
    for attempt in (0, 1):
        run.guard()
        with run.fence(tgt):
            run.guard()   # 울타리 안에서 — 문서 쌍이 그대로이고
            if _has_fill(run.task) and not U.fill_done(UNIT.fill_facts(run.target)):   # 기다리는 사이 도착한 편집 · 실행 취소로 「내용 넣기」 의 끝이 풀렸으면 지우지 않는다(astra 결과 검토)
                raise _Halt("order", f"{_stage_name(run.task, 'stage_fill', '내용 넣기')} 이 먼저입니다 — 그 사이 문서가 바뀌었습니다")
            c = UNIT.cleanup_count(tgt)   # 울타리 안에서 다시 센다(고친 글이 서버에 온 뒤의 문서)
            if not c.ok:
                raise _Halt(c.code, f"지울 안내를 세지 못했습니다: {c.text}")
            C = c.data
            got = UNIT.cleanup(tgt, C["rev"]) if (C.get("counts") or {}).get("total") else None
        if got is None or got.code != "stale" or attempt:
            break
    if got is None or got.code == "nothing":
        return "nothing", "지울 안내가 없습니다"
    if not got.ok:
        raise _Halt(got.code, f"양식 안내를 지우지 못했습니다 — {'표준 검사에 걸려 되돌렸습니다: ' if got.code == 'rejected' else ''}{got.text}")
    done = (got.data or {}).get("done") or {}
    after = UNIT.cleanup_count(tgt)
    left = ((after.data or {}).get("counts") or {}).get("total") or 0 if after.ok else 0
    text = (U.cleanup_text(done, C.get("patterns"), True) + (f" · 건너뜀 {U.nf(len(done['skipped']))}" if done.get("skipped") else "")
            + (f" · 남은 안내 {U.nf(left)}" if left else ""))
    return "done", text


HANDLERS.update({"link": _do_link, "llm": _do_link_llm, "plan": _do_plan, "gaps": _do_gaps, "tableMap": _do_table_map, "apply": _do_apply, "guide": _do_guide})   # 3단계 · 4단계(걸음 3 — 이 절)


# ---------------------------------------------------------------- 「문서 정리」 의 조립 도구 둘(spec_워크플로우 ② §18-23) — 지침 보정(LLM) · 빈 구역 지우기. 문서마다(_fit_docs) · 「내용 넣기」 의 끝 뒤에만(작성요령 삭제와 같은 조건)
def _per_doc(run, gid, line, one):
    """그 줄이 닿는 문서마다 one(run, gid, 문서 id) → (done | nothing | left, 글) 을 돌려 줄 하나의 결과로 — 목적 문서만의 줄은 글 그대로 · 원본 문서가 들면 문서 이름을 붙인다(작성요령 삭제와 같은 꼴)."""
    docs = _fit_docs(run, line)
    out = [(name, *one(run, gid, d)) for _role, d, name in docs]
    text = out[0][2] if len(out) == 1 and docs[0][0] == "target" else " · ".join(f"{name} — {t}" for name, _st, t in out)
    sts = [st for _n, st, _t in out]
    return ("left" if "left" in sts else "done" if "done" in sts else "nothing"), text, text


def _fill_first(run, why):
    if _has_fill(run.task) and not U.fill_done(UNIT.fill_facts(run.target)):
        raise _Halt("order", f"{_stage_name(run.task, 'stage_fill', '내용 넣기')} 이 먼저입니다 — {why}")


def _do_guide_fix(run, gid, line):
    """지침 보정(LLM) — 그 줄이 닿는 문서마다(_guide_fix_doc)."""
    return _per_doc(run, gid, line, _guide_fix_doc)


def _guide_fix_doc(run, gid, doc):
    """지침 보정(문서 하나 — 문서를 바꾼다) — 묻기(유료 · 문서 안 바뀜 — 울타리 밖) → 반영(울타리 안 · 물은 뒤 글이 바뀐 문단은 끝점이 건너뜀). 고칠 것이 없어도 반영 기록을 남겨 끝난 것으로 본다.
    LLM 을 쓸 수 없으면 「건너뜀」(nothing) · 에이전트 카드가 승인하지 않은 문서면 남김(left). → (done | nothing | left, 글)."""
    run.working = {doc}
    _fill_first(run, "④ 내용 반영 전")
    G = UNIT.guide_fix_facts(doc)
    if G.get("error"):
        raise _Halt("error", f"지침 보정의 재료를 읽지 못했습니다: {G['error']}")
    if G.get("why"):
        return "nothing", G["why"]
    if not (G.get("guides") or {}).get("total"):
        return "nothing", "저장한 작성 지침이 없습니다 — 건너뜀"
    if not UNIT.llm_ok():
        return "nothing", "지침 보정은 건너뜀(LLM 을 쓸 수 없음)"
    if run.approval is not None and doc not in run.approval.get("paid", ()):
        return "left", "지침 보정은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)"
    run.note(gid, "guideFix", f"작성 지침 {G['guides']['total']}곳에 따라 LLM 에 묻는 중(유료 · 수십 초)", doc)
    run.guard()
    asked = UNIT.guide_fix_ask(doc)
    if not asked.ok:
        raise _Halt(asked.code, f"지침 보정을 묻지 못했습니다 — {asked.text}(다시 누르세요)")
    P = asked.data or {}
    with run.fence(doc):
        run.guard()
        _fill_first(run, "그 사이 문서가 바뀌었습니다")
        got = UNIT.guide_fix_apply(doc, P.get("planId"))
    if got.code == "stale":
        raise _Halt("stale", f"지침 보정을 반영하지 못했습니다 — {got.text}")
    if not got.ok:
        raise _Halt(got.code, f"지침 보정을 반영하지 못했습니다 — {'표준 검사에 걸려 되돌렸습니다: ' if got.code == 'rejected' else ''}{got.text}")
    D = got.data or {}
    n, skip, left, bad = len(D.get("done") or ()), len(D.get("skipped") or ()), len(P.get("left") or ()), len(P.get("rejected") or ())
    tail = (f" · 건너뜀 {U.nf(skip)}" if skip else "") + (f" · 고치지 못한 것 {U.nf(left)}" if left else "") + (f" · 검사에 걸려 버린 고침 {U.nf(bad)}" if bad else "")
    if P.get("nothing"):
        return "nothing", f"지침 보정 — {P.get('why') or '고칠 자리가 없습니다'}"
    return ("done" if n else "nothing"), (f"지침 보정 — 고친 문단 {U.nf(n)}" if n else "지침 보정 — 지침에 어긋난 글이 없습니다") + tail


def _do_zone_prune(run, gid, line):
    """빈 구역 지우기 — 그 줄이 닿는 문서마다(_zone_prune_doc)."""
    return _per_doc(run, gid, line, _zone_prune_doc)


def _zone_prune_doc(run, gid, doc):
    """빈 구역 지우기(문서 하나 — 문서를 바꾼다: 울타리 안에서 다시 세고 지운다) · 센 뒤 문서가 바뀌면(409) 한 번만 다시 센다. → (done | nothing, 글)."""
    run.working = {doc}
    _fill_first(run, "④ 내용 반영 전")
    c = UNIT.zone_prune_count(doc)
    if not c.ok:
        raise _Halt(c.code, f"빈 구역을 세지 못했습니다: {c.text}")
    Z = c.data or {}
    if Z.get("why"):
        return "nothing", f"{Z['why']} — 건너뜀"
    if not (Z.get("counts") or {}).get("items"):
        return "nothing", "지울 빈 구역이 없습니다"
    run.note(gid, "zonePrune", f"빈 구역 {U.nf(Z['counts']['items'])}곳 지우기", doc)
    got = None
    for attempt in (0, 1):
        run.guard()
        with run.fence(doc):
            run.guard()
            _fill_first(run, "그 사이 문서가 바뀌었습니다")
            c = UNIT.zone_prune_count(doc)   # 울타리 안에서 다시 센다
            if not c.ok:
                raise _Halt(c.code, f"빈 구역을 세지 못했습니다: {c.text}")
            Z = c.data or {}
            got = UNIT.zone_prune(doc, Z["rev"]) if (Z.get("counts") or {}).get("items") else None
        if got is None or got.code != "stale" or attempt:
            break
    if got is None or got.code == "nothing":
        return "nothing", "지울 빈 구역이 없습니다"
    if not got.ok:
        raise _Halt(got.code, f"빈 구역을 지우지 못했습니다 — {'표준 검사에 걸려 되돌렸습니다: ' if got.code == 'rejected' else ''}{got.text}")
    done = (got.data or {}).get("done") or {}
    r = done.get("removed") or {}
    parts = " · ".join(f"{name} {U.nf(r[k])}" for k, name in (("blocks", "본문 블록"), ("rows", "표 행"), ("cols", "표 열")) if r.get(k))
    skip = f" · 건너뜀 {U.nf(len(done['skipped']))}" if done.get("skipped") else ""
    return "done", f"빈 구역 {U.nf(r.get('items'))}곳을 지웠습니다({parts}){skip}"


def _do_cap_unify(run, gid, line):
    """캡션 맞추기 — 그 줄이 닿는 문서마다(_cap_unify_doc)."""
    return _per_doc(run, gid, line, _cap_unify_doc)


def _cap_unify_doc(run, gid, doc):
    """캡션 맞추기(문서 하나 — 문서를 바꾼다: 울타리 안에서 다시 세고 맞춘다 · spec_hwpx_웹편집 ② §8-10 「모든 캡션을 한 꼴로」) · 센 뒤 문서가 바뀌면(409) 한 번만 다시 센다.
    쓸 꼴 = 그 묶음의 워크플로우 옵션(task_options.flow 의 caption) · 없으면 줄이 가장 많은 꼴. 고른 꼴의 캡션이 문서에 없으면 맞추지 않고 남긴다(left — 다시 고른다). → (done | nothing | left, 글)."""
    run.working = {doc}
    _fill_first(run, "④ 내용 반영 전")
    c = UNIT.cap_unify_view(doc)
    if not c.ok:
        raise _Halt(c.code, f"캡션을 세지 못했습니다: {c.text}")
    C = c.data or {}
    if C.get("off"):
        return "nothing", f"{C.get('why') or 'HWPX 문서가 아닙니다'} — 건너뜀"
    if not (C.get("counts") or {}).get("titles"):
        return "nothing", "맞출 제목 캡션이 없습니다"
    if C.get("why"):
        return "left", f"캡션 맞추기는 하지 않음 — {C['why']}"
    if not C["counts"].get("change"):
        return "nothing", U.cap_unify_text(C)
    run.note(gid, "capUnify", f"제목 캡션 {U.nf(C['counts']['change'])}곳을 「{C.get('name') or '?'}」 으로 맞추기", doc)
    got = None
    for attempt in (0, 1):
        run.guard()
        with run.fence(doc):
            run.guard()
            _fill_first(run, "그 사이 문서가 바뀌었습니다")
            c = UNIT.cap_unify_view(doc)   # 울타리 안에서 다시 센다
            if not c.ok:
                raise _Halt(c.code, f"캡션을 세지 못했습니다: {c.text}")
            C = c.data or {}
            if C.get("why") and (C.get("counts") or {}).get("titles"):
                return "left", f"캡션 맞추기는 하지 않음 — {C['why']}"
            got = UNIT.cap_unify(doc, C["rev"]) if (C.get("counts") or {}).get("change") else None
        if got is None or got.code != "stale" or attempt:
            break
    if got is None or got.code == "nothing":
        return "nothing", U.cap_unify_text(C)
    if not got.ok:
        raise _Halt(got.code, f"캡션을 맞추지 못했습니다 — {'표준 검사에 걸려 되돌렸습니다: ' if got.code == 'rejected' else ''}{got.text}")
    return "done", U.cap_unify_text(C, done=len((got.data or {}).get("changed") or ()))


def _do_retidy(run, gid, line):
    """넣은 뒤 템플릿 · 서식 정리(spec_병합 ② §5-9) — 그 줄이 닿는 문서마다(목적 문서뿐: _retidy_doc)."""
    return _per_doc(run, gid, line, _retidy_doc)


def _retidy_doc(run, gid, doc):
    """넣은 뒤 템플릿 · 서식 정리(문서 하나 — 문서를 바꾼다: 울타리 안에서 끝점이 헤딩을 다시 분석(스크립트 · 몇 초) → 계획 → 반영 한 번). 그 반영 뒤에 이미 했으면 「할 것 없음」 ·
    끝점이 그 사이 문서가 바뀌었다(409 — 다른 헤딩 작업 · 낡은 차례)고 하면 한 번만 다시. → (done | nothing, 글)."""
    run.working = {doc}
    _fill_first(run, "④ 내용 반영 전")
    R = UNIT.retidy_facts(doc)
    if R.get("error"):
        raise _Halt("error", f"넣은 뒤 정리의 재료를 읽지 못했습니다: {R['error']}")
    if R.get("why"):
        return "nothing", f"{R['why']} — 건너뜀"
    a = R.get("applied") or {}
    if a and a.get("fill") == R.get("fill"):
        return "nothing", U.retidy_text(a.get("counts") or {})
    run.note(gid, "retidy", "넣은 줄을 목적 문서의 템플릿 · 서식으로 — 헤딩 다시 분석(스크립트) → 레벨마다 대표 → 맞추기", doc)
    got = None
    for attempt in (0, 1):
        run.guard()
        with run.fence(doc):
            run.guard()
            _fill_first(run, "그 사이 문서가 바뀌었습니다")
            got = UNIT.retidy(doc)
        if got.code not in ("stale", "busy") or attempt:
            break
    if not got.ok:
        raise _Halt(got.code, f"넣은 줄의 템플릿 · 서식을 맞추지 못했습니다 — {'표준 검사에 걸려 되돌렸습니다: ' if got.code == 'rejected' else ''}{got.text}")
    D = got.data or {}
    c = (D.get("done") or {}).get("counts") or {}
    return ("nothing" if D.get("nothing") else "done"), U.retidy_text(c)


HANDLERS.update({"guideFix": _do_guide_fix, "zonePrune": _do_zone_prune, "retidy": _do_retidy, "capUnify": _do_cap_unify})   # 「문서 정리」 의 조립 도구(② §18-23 · 넣은 뒤 정리 = spec_병합 ② §5-9)


def _tidy_materials(task, pair, facts, opt=None):
    """그 줄이 닿는 문서 facts 에 「문서 정리」 조립 도구의 재료를 얹는다 — guideFix = unit_steps.guide_fix_facts · zonePrune = unit_steps.zone_prune_count · capUnify = unit_steps.cap_unify_view ·
    retidy = unit_steps.retidy_facts(넣은 뒤 템플릿 · 서식 정리 — 이관형 · 취합형의 단위(따로 선 두 단위 — 넣은 기록은 merge.json · gather.json: spec_병합 ② §5-9))(그 줄이 정의에 있을 때만 · 서버가 맡은 묶음)."""
    want = {}
    units = {"guideFix": (U.COMMON["guideFix"],), "zonePrune": (U.COMMON["zonePrune"],), "capUnify": (U.COMMON["capUnify"],), "retidy": (U.RELAY["retidy"], U.GATHER["retidy"])}   # 단위는 객체로 가린다(같은 key 의 다른 틀 단위로 새지 않게)
    for x in S.lines(task):
        if x["key"] in units and any(x["unit"] is u for u in units[x["key"]]) and S.served(task, x["stage"]):
            for r in S.roles_on(task, x["on"]):
                d = (pair.get(r) or {}).get("id")
                if d and facts.get(d) is not None:
                    want.setdefault(d, set()).add(x["key"])
    for d, keys in want.items():
        more = {}
        if "guideFix" in keys:
            more["guideFix"] = UNIT.guide_fix_facts(d)
        if "zonePrune" in keys:
            c = UNIT.zone_prune_count(d)
            more["zonePrune"] = c.data if c.ok and isinstance(c.data, dict) else {"error": c.text or "응답이 없음"}
        if "capUnify" in keys:
            c = UNIT.cap_unify_view(d)
            more["capUnify"] = c.data if c.ok and isinstance(c.data, dict) else {"error": c.text or "응답이 없음"}
        if "retidy" in keys:
            more["retidy"] = UNIT.retidy_facts(d)
        facts[d] = {**facts[d], **more}


MATERIALS.append(_tidy_materials)


# ================================================================ 2단계 「구성 맞추기」(걸음 2 — spec_워크플로우 ② §17-10 걸음 2 · §18-4 · §18-12 ②)
# 프로젝트 구성 추출 → 프로젝트 구성 반영(울타리 · 같은 검사 · 다시 계획 없이 한 번) → 다시 문서 검토(스크립트) → 다시 문서 검토(LLM).
# 차례 · 조건 · 끝 글은 화면 실행(app.js taskRunSteps 의 frame 가지) 그대로 — 끝 글 = 「구조를 맞췄습니다 — <반영 줄의 글>[ · 다시 분석][ · LLM] · 내용은 N단계 「내용 넣기」 에서 넣습니다」.
# 끝남은 처리 함수가 문서에서 다시 센다(workflow_units 의 같은 식) — 화면에 보이는 「끝남」 을 성공 조건으로 쓰지 않는다(② §18-4 ⓐ~ⓒ).
_FIT_KEYS = ("config", "division", "reheads", "reheadsLlm")


def _fit_names(run):
    """(구성의 기준 문서 이름, 목적 문서 이름, 기준 문서 id, 목적 id) — 기준 = 워크플로우의 base(이관 = 원본 문서 · 취합 · 문서 하나 = 목적 문서 자신: workflow_state.base)."""
    s, t = S._role(run.task, "source"), S._role(run.task, "target")
    D_, tgt = (t or {}).get("name") or "목적 문서", (run.pair.get("target") or {}).get("id")
    if S.base(run.task) == "target":
        return D_, D_, tgt, tgt
    return (s or {}).get("name") or "원본 문서", D_, (run.pair.get("source") or {}).get("id"), tgt


def _self_fit(task):
    """이 정의가 원본 문서의 구조도 반영하나 — 「프로젝트 구성 반영」(같이 쓰는 단위)을 원본 문서에 놓은 이관형 정의(② §18-2 「원본 문서에 놓는 줄」). 참이면 목적 문서가 맞출 기준 값이 원본의 「제 값」 이다(workflow_units.basis_of — 두 문서의 차례와 무관)."""
    return any(x["key"] == "division" and x["unit"] is U.COMMON["division"] and "source" in S.roles_on(task, x["on"]) for x in S.lines(task))


def _div_of(task, d, excl=None):
    """그 문서의 구성 재료(문 div_facts) — 문서 하나의 틀이고 이번 실행의 「반영에서 빼기」 자리를 알면(excl — None = 모름) 그것을 얹는다(`excl`: workflow_units.fit_done 이 지난 반영이 뺀 자리와 견준다).
    다른 틀(이관형 · 취합)의 재료는 전과 같다."""
    div = UNIT.div_facts(d)
    if div is not None and excl is not None and task is not None and S.family(task) == "single":
        div = {**div, "excl": list(excl)}
    return div


def _fit_facts(pair, task=None, excl=None):
    """두 문서의 지금 재료(헤딩 + 구성) — 「구성 맞추기」 줄의 상태를 세는 데 필요한 것만(넣기 재료는 읽지 않는다). task 를 주면 원본 문서의 재료에 selfFit(_self_fit) · excl = 이번 실행의 뺀 자리(_div_of)."""
    out = {}
    own = bool(task) and _self_fit(task)
    for role in U.ROLES:
        d = (pair.get(role) or {}).get("id")
        if d:
            f = UNIT.facts(d)
            out[d] = {**f, "div": _div_of(task, d, excl), **({"selfFit": True} if own and role == "source" else {})} if f is not None else None
    return out


def _fit_state(run, key, role=None):
    """그 줄의 지금 상태(화면 taskSteps 와 같은 식 — workflow_units.state) → (상태, 재료). role = 문서마다의 줄(구성 반영 · 다시 문서 검토)에서 그 문서 하나의 몫(source | target) —
    안 주면 목적 문서의 몫(전과 같다 — 줄의 문서를 싣지 않으면 상태 식이 목적 문서로 센다: workflow_units._line_roles)."""
    facts = _fit_facts(run.pair, run.task, _excl(run.rec))
    ctx = S.context(run.task, run.pair, facts, llm=UNIT.llm_ok(), skip=UNIT.skips(run.target))
    if role and role in ctx["pair"]:
        ctx["docs"] = [ctx["pair"][role]]
    return (U.state(key, ctx, S.family(run.task)) or {"st": "todo", "text": ""}), facts


def _fit_materials(task, pair, facts, opt=None):
    """상태를 셀 때(GET …/flow · 실행의 묶음 경계) 「구성 맞추기」 줄을 서버가 맡으면 구성 재료를 덧붙인다(MATERIALS) — **구성 재료를 실제로 읽는 줄**이 있을 때만 · 그 줄이 읽는 역할의 문서에만:
    단위가 사는 단계가 구성 맞추기(home stage_fit)이고 상태를 셀 때 문서를 읽는 단위(reads — 이관형의 config · division · reheads … · 취합의 division · frame · 문서 하나의 read · values · plan · apply).
    사람이 고르는 줄(구성 불러오기 · 자리 확인 — reads 없음)뿐인 정의는 읽지 않는다: 구성 재료를 읽으면 그 문서의 입력이 프로젝트의 공유 입력으로 올라갈 수 있다(상태 조회가 저장을 건드리지 않게 — astra P2)."""
    roles = {r for x in S.lines(task) if (x["unit"] or {}).get("home") == "stage_fit" and S.served(task, x["stage"]) for r in (x["unit"].get("reads") or ())}
    if not roles:
        return
    own, excl = _self_fit(task), (opt or {}).get("excl")
    for role in U.ROLES:
        d = (pair.get(role) or {}).get("id")
        if role in roles and d and d in facts and facts[d] is not None and "div" not in facts[d]:
            facts[d] = {**facts[d], "div": _div_of(task, d, excl), **({"selfFit": True} if own and role == "source" else {})}   # selfFit = 이 정의가 원본 문서의 구조도 반영한다(목적 문서의 기준 값 — workflow_units.basis_of)


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


def _fit_change(run, stage, key, tgt, D_, values, stops_text, adopt=False, check=None, skip=None, pin=None):
    """[문서 바뀜] 구조 반영의 몸통(이관형의 division · 문서 하나의 apply 가 같이 쓴다) — 울타리 안에서 계획 → 같은 검사(autoStops) → 반영을 **다시 계획 없이 한 번**(② §18-4) → 반영의 Outcome(ok | nothing).
    stops_text(계획) = 같은 검사에 걸렸을 때의 멈춤 글(화면 실행의 글 그대로 — 틀마다 보정할 곳이 다르다). 409(낡은 계획) · 422(표준 검사)는 멈춤. adopt = 바꿀 것이 없는 계획이 「구조가 이미 값에 맞음」 이면
    끝점이 그 확인을 반영 기록으로 남긴다(끝남을 문서의 기록에서 다시 셀 수 있게: ② §18-13) — **문서 하나만 켠다**. 이관형은 켜지 않는다(전과 같다 — 그 기록의 조건은 2026-11-20 에 조였다:
    구분 값에 없는 기관 이름이 적힌 자리가 남으면 적지 않는다 — server._division_named).
    skip = 「반영에서 빼기」 의 자리 key 들 — 안 주면 실행 기록의 것(목적 문서 화면에서 고른 것) · 다른 문서(원본 문서)에 돌릴 때는 빈 것을 준다(그 key 는 목적 문서 계획의 것이다).
    pin = **울타리 안에서** 입력 · 확정을 한 번에 읽어 검사하는 함수(문서 id) → 입력의 판(div_facts 의 hash | None) — 주면 values 는 쓰지 않는다: 계획 요청에 값을 싣지 않고(앞에서 읽은 값으로
    최신 공유 입력을 덮지 않게) 그 판일 때만 계획하며(문 division_plan 의 expect), 세운 계획이 그 판의 것인지 다시 본다. 반영은 그 계획이 남아 있을 때만 된다(값이 바뀌면 서버가 계획을 버린다 — 409).
    문서 하나의 구조 반영이 준다(astra A5 — 확정 검사와 계획 사이에 입력이 바뀌는 틈). 안 주면 전처럼 values 를 계획 요청에 싣는다(이관형 · 취합)."""
    skip = list(run.rec.get("skip") or []) if skip is None else list(skip)
    run.guard()
    run.working = {tgt}
    applied = None
    with run.fence(tgt):   # 알림 → 화면들의 고치던 글 → 울타리 — 계획과 반영 사이에 사람이 친 글이 끼지 않게(② §17-8)
        want = pin(tgt) if pin else None   # 울타리 안 — 이 문서에서 사람의 입력 · 확정 저장은 409 다(같은 프로젝트의 다른 문서로 공유 입력이 바뀌는 것은 아래 판 조건이 거른다)
        run.note(stage, key, "변경 계획", tgt)
        got = UNIT.division_plan(tgt, None, skip, expect=want) if pin else UNIT.division_plan(tgt, values, skip)
        if not got.ok or not isinstance(got.data, dict) or not got.data.get("planId"):
            raise _Halt("plan" if got.ok else got.code, f"프로젝트 구성 변경 계획을 세우지 못했습니다 — {got.text or '계획이 없습니다'}")
        plan = got.data
        if plan.get("stale") or (want is not None and plan.get("settingsHash") not in (None, want)):
            raise _Halt("stale", "계획을 세우는 사이 문서나 프로젝트 구성 값이 바뀌었습니다 — 다시 누르세요")
        if plan.get("autoStops"):   # 같은 검사(division_plan.auto_stops — 화면의 「한 번에 진행」 들과 같은 값)
            raise _Halt("stops", stops_text(plan))
        more = check(plan) if check else ""   # 틀마다 더 보는 것(취합의 간단 모드 — 지울 것이 있으면 멈춤) → 멈춤 글 | ""
        if more:
            raise _Halt("stops", more)
        run.guard()   # 문서 쓰기 직전 — 멈춤 요청 · 문서 칸(원본 · 목적) · 범위가 그대로인가(계획을 세우는 사이 원본을 바꿨으면 옛 원본 기준으로 바꾸지 않게 — astra P1)
        run.note(stage, key, f"{D_}에 반영", tgt)
        applied = UNIT.division_apply(tgt, plan["planId"], plan["baseRev"], **({"adopt": True} if adopt else {}))
    run.working = set()
    if applied.code not in ("ok", "nothing"):   # 409(낡은 계획) · 422(표준 검사) — 다시 계획하지 않고 멈춘다(② §18-4) · 상태를 다시 세어 「끝남」 으로 덮지 않는다
        raise _Halt(applied.code, f"프로젝트 구성이 반영되지 않았습니다 — {applied.text or '반영 요청이 거절되었습니다'}")
    return applied


def _do_config(run, stage, line):
    """프로젝트 구성 추출 — 원본(구성의 기준)의 입력 값(없으면 문서에 적힌 값)을 목적 문서에서 확정한다(화면 실행이 목적 문서의 입력 칸으로 확정하는 것과 같다 — 공유 중이면 프로젝트의 확정). 문서는 안 바뀐다."""
    st, _ = _fit_state(run, "config")
    if st["st"] == "done":
        return "nothing", ""
    S_, _D, src, tgt = _fit_names(run)
    fit = _stage_name(run.task, "stage_fit", "구성 맞추기") if S.base(run.task) != "target" else _g_no(run, stage)   # 값을 넣을 곳 — 이관형 = 「구성 맞추기」 묶음 · 구성의 기준이 목적 문서(취합) = 이 줄이 든 묶음(「1단계 「프로젝트 구성」」)
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
    if S.base(run.task) == "target":   # 구성의 기준이 목적 문서 자신(취합) — 끝 글은 화면 실행(gather.js gatherRunConfig)의 글
        return "done", f"{f'{S_}에서 읽은 ' if not A.get('input') else ''}프로젝트 구성을 {U._where(UNIT.div_facts(tgt))}에 확정했습니다 — {U.summary_text(values)}"
    return "done", ""


def _fit_docs(run, line):
    """문서마다의 줄(구성 반영 · 다시 문서 검토 · 작성요령 삭제)이 닿는 문서들 → [(역할, 문서 id, 문서 이름)] — 원본 → 목적 차례(목적 문서는 원본 문서의 구조를 기준으로 맞추므로 원본이 먼저).
    2026-11-20 사용자 「목적문서랑 원본 문서도 분리해서 따로 따로 하게」 — 줄이 고른 문서만 한다(② §18-2 「원본 문서에 놓는 줄」). 줄의 문서를 못 읽으면 목적 문서."""
    got = [(role, d, name) for d, name, role in _docs_of(run, {**line, "on": line.get("on") or ""})]
    if got:
        return got
    _S, D_, _src, tgt = _fit_names(run)
    return [("target", tgt, D_)]


def _do_division(run, stage, line):
    """[문서 바뀜] 프로젝트 구성 반영 — 그 줄이 닿는 문서마다(원본 → 목적): 목적 문서 = 원본(기준)의 값으로 맞춤(_division_target) · 원본 문서 = 제 값을 제 구조에(_division_source).
    끝 글의 묶음 몫 = 「구조를 맞췄습니다 — <문서마다의 글>」(이미 반영돼 있어도 — 화면 실행과 같다)."""
    out = [(_division_source if role == "source" else _division_target)(run, stage) for role, _d, _name in _fit_docs(run, line)]
    return ("done" if any(st == "done" for st, _ in out) else "nothing"), "구조를 맞췄습니다 — " + " · ".join(t for _, t in out)


def _division_source(run, stage):
    """[문서 바뀜] 원본 문서의 프로젝트 구성 반영(② §18-2 「원본 문서에 놓는 줄」) — 그 문서 자신의 값(workflow_units.own_values — 확정한 프로젝트 구성과 같아야 한다)을 제 구조에.
    한 번도 반영한 적 없는 문서의 구조가 이미 값에 맞으면 확인만(문 division_adopt — 울타리 없이 · 문서 안 바뀜: 손으로 채운 작성본이 흔한 원본 문서가 「반영 전」 으로 막히지 않게 — 취합의 구조 반영과 같은 길),
    아니면 목적 문서와 같은 몸통(_fit_change — 울타리 안 계획 → 같은 검사 → 반영 한 번). 목적 문서 화면의 「반영에서 빼기」 는 이 문서의 계획에 넘기지 않는다. → (done | nothing, 그 문서의 상태 글)."""
    s = S._role(run.task, "source")
    S_, src, tgt = (s or {}).get("name") or "원본 문서", (run.pair.get("source") or {}).get("id"), run.target
    fit = _stage_name(run.task, "stage_fit", "구성 맞추기")
    st, _ = _fit_state(run, "division", "source")
    if st["st"] == "done":
        return "nothing", st["text"]
    cf, _ = _fit_state(run, "config")
    if cf["st"] != "done":
        raise _Halt("notConfirmed", f"「프로젝트 구성 추출」 이 먼저입니다 — {cf['text'] or '프로젝트 구성을 확정한 뒤 다시 누르세요'}")
    run.note(stage, "division", f"{S_} 값 확인", src)
    A, B = UNIT.div_facts(src), UNIT.div_facts(tgt)
    if A is None or B is None:
        raise _Halt("missing", "두 문서의 프로젝트 구성을 읽지 못했습니다")
    if not A.get("supported"):
        raise _Halt("unsupportedForm", f"{S_}의 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다 — 이 줄을 원본 문서에서 빼거나 지원하는 양식의 문서로 하세요")
    a, read = U.own_values(A)
    if not a:
        raise _Halt("noValues", f"{S_}에 프로젝트 구성 값이 없습니다 — {S_}에서 값을 넣거나 문서에서 읽은 뒤 다시 누르세요")
    if read:   # 저장된 값이 없어 문서에서 읽은 값 — 그 문서의 값으로 저장한다(문서는 그대로 — 목적 문서의 반영이 기준 값을 저장하는 것과 같다)
        run.note(stage, "division", f"문서에서 읽은 값을 {S_} 값으로 저장", src)
        got = UNIT.config_save(src, a)
        a, read = U.own_values(UNIT.div_facts(src)) if got.ok else (None, False)
        if not a or read:
            raise _Halt("notSaved", f"{S_} 값을 저장하지 못했습니다{f' — {got.text}' if got.text else ''}")
    if not U.confirm_valid(a, B.get("confirmed")):   # 확정과 다른 값으로 문서를 바꾸지 않는다(계획 요청이 그 값을 입력으로 저장하므로 계획 **전**에)
        raise _Halt("unconfirmed", f"{S_}의 값({U.summary_text(a)})이 확정한 프로젝트 구성과 다릅니다 — {S_}의 값을 맞추거나 {fit} 의 「프로젝트 구성 추출」 을 다시 한 뒤 누르세요")
    named = 0
    if not (UNIT.div_facts(src) or {}).get("applied"):   # 한 번도 반영한 적 없는 문서 — 구조가 이미 값에 맞으면 「반영됨」 으로 적는다(못 해도 아래 계획 → 반영으로 간다)
        run.note(stage, "division", f"{S_} 구조 확인(이미 값에 맞는지)", src)
        named = _adopt_named(UNIT.division_adopt(src))
        st, _ = _fit_state(run, "division", "source")
        if st["st"] == "done":
            return "nothing", f"{st['text']}(구조가 이미 값에 맞음 — 확인함)"
    applied = _fit_change(run, stage, "division", src, S_, a, lambda plan: f"{plan['autoStops']} — 저절로 반영하지 않습니다. {S_}를 열어 「프로젝트 구성」 의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요", skip=())
    st, _ = _fit_state(run, "division", "source")
    if st["st"] != "done":
        if named and applied.code == "nothing":   # 바꿀 것은 없는데 다른 이름의 기관 자리가 남은 문서 — 「이미 맞음」 으로 적지 않은 까닭을 알린다
            raise _Halt("named", _named_text(S_, named))
        raise _Halt("notApplied", f"{S_}에 프로젝트 구성이 반영되지 않았습니다 — {st['text']}")
    return ("done" if applied.code == "ok" else "nothing"), st["text"]


def _adopt_named(got):
    """구조 확인(문 division_adopt)이 「구분 값에 없는 기관 이름이 적힌 자리가 남아」 적지 않았으면 그 자리 수(모르면 1) | 0."""
    d = got.data if got is not None and got.ok and isinstance(got.data, dict) else {}
    return (d.get("named") or 1) if d.get("why") == "named" else 0


def _named_text(D_, n):
    """값이 다르다고 이미 확인된 자리가 남아 「구조가 이미 값에 맞음」 으로 적지 않을 때의 멈춤 글 — 무엇이 · 몇 곳 · 어디서 고치나."""
    return (f"{D_}에 프로젝트 구성에 없는 기관 이름이 적힌 자리가 {U.nf(n)}곳 남아 있습니다 — 문서의 기관 이름이 프로젝트 구성과 다릅니다. 「프로젝트 구성」 의 변경 계획 목록에서 그 자리를 확인하고 "
            "문서의 이름을 고치거나 프로젝트 구성의 기관 이름을 맞춘 뒤 다시 누르세요(저절로 「맞음」 으로 적지 않습니다)")


def _division_target(run, stage):
    """[문서 바뀜] 목적 문서의 프로젝트 구성 반영 — 원본(기준)의 값으로 목적 문서의 값을 맞추고 울타리 안에서 계획 → 같은 검사(autoStops) → 반영을 **다시 계획 없이 한 번**(② §18-4). → (done | nothing, 그 문서의 상태 글)."""
    S_, D_, src, tgt = _fit_names(run)
    fit = _stage_name(run.task, "stage_fit", "구성 맞추기")
    st, _ = _fit_state(run, "division", "target")
    if st["st"] == "done":
        return "nothing", st["text"]
    cf, _ = _fit_state(run, "config")
    if cf["st"] != "done":
        raise _Halt("notConfirmed", f"「프로젝트 구성 추출」 이 먼저입니다 — {cf['text'] or '프로젝트 구성을 확정한 뒤 다시 누르세요'}")
    run.note(stage, "division", f"{S_} 값과 견주기")
    A, B = UNIT.div_facts(src), UNIT.div_facts(tgt)
    if A is None or B is None:
        raise _Halt("missing", "두 문서의 프로젝트 구성을 읽지 못했습니다")
    basis = U.own_values if _self_fit(run.task) else U.basis_values   # 이 정의가 원본 문서의 구조도 반영하면 원본의 제 값(입력이 먼저) — 차례와 무관하게 두 문서가 같은 값으로(상태 식 workflow_units.basis_of 와 같은 고르기)
    a, read = basis(A)
    if not a:
        raise _Halt("noValues", f"{S_}(기준)에 프로젝트 구성 값이 없습니다 — {S_}에서 값을 넣거나 문서에서 읽은 뒤 다시 누르세요")
    if read:   # 저장된 값이 없어 문서에서 읽은 값 — 원본 작업의 값으로 저장한다(문서는 그대로 — 화면 실행과 같다)
        run.note(stage, "division", f"문서에서 읽은 값을 {S_} 값으로 저장")
        got = UNIT.config_save(src, a)
        a, read = basis(UNIT.div_facts(src)) if got.ok else (None, False)
        if not a or read:
            raise _Halt("notSaved", f"{S_} 값을 저장하지 못했습니다{f' — {got.text}' if got.text else ''}")
    b = U.target_values(B)
    moved = not b or bool(U.div_diff(a, b))
    values = a if moved else b   # 다르면 원본의 값으로(당해 차년도도 — 화면 taskDivFit 과 같은 값) · 같으면 목적 문서의 값 그대로
    if not U.confirm_valid(values, B.get("confirmed")):   # 확정과 다른 값으로 문서를 바꾸지 않는다(계획 요청이 그 값을 입력으로 저장하므로 계획 **전**에 — astra 2026-11-20 P1)
        raise _Halt("unconfirmed", f"반영할 값({U.summary_text(values)})이 확정한 프로젝트 구성과 다릅니다 — {fit} 의 「프로젝트 구성 추출」 을 다시 한 뒤 누르세요")
    # 「반영에서 빼기」(run.rec.skip) — 위 확인을 지나면 값은 목적 문서의 지금 입력과 같다(확정 = 목적의 입력 · 원본 값이 다르면 멈춤) — 화면에서 고른 그 값의 자리
    applied = _fit_change(run, stage, "division", tgt, D_, values, lambda plan: f"{plan['autoStops']} — 저절로 반영하지 않습니다. {fit} 의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요")
    st, _ = _fit_state(run, "division", "target")
    if st["st"] != "done":
        raise _Halt("notApplied", f"프로젝트 구성이 반영되지 않았습니다 — {st['text']}")
    return ("done" if applied.code == "ok" else "nothing"), st["text"]


def _do_reheads(run, stage, line):
    """다시 문서 검토 — 그 줄이 닿는 문서마다(원본 → 목적) 구조 반영으로 바뀐 문서를 다시 분석한다(_reheads_doc). 줄의 상태 = 남긴 문서가 있으면 남김 · 다시 분석한 문서가 있으면 끝남."""
    R = run.rec["range"]
    out = _lanes(run, [functools.partial(_reheads_doc, run, stage, role, d, name) for role, d, name in _fit_docs(run, line)])   # 두 문서면 함께(분석은 제 문서만 — 글은 원본 → 목적 차례 그대로)
    again = " · ".join(t for _, t in out if t)
    if any(st == "left" for st, _ in out):
        return "left", again
    st = "done" if any(st == "done" for st, _ in out) else "nothing"
    if R.get("only") == "reheads":   # 「다시 분석」 단추 — 이 줄만
        return st, f"구조를 맞춘 문서의 헤딩·표{f' — {again}' if again else ' 분석은 구조 반영 뒤의 것입니다'} — 다음은 「다시 문서 검토(LLM)」 입니다"
    return st, again


def _reheads_doc(run, stage, role, tgt, D_):
    """다시 문서 검토(문서 하나) — 구조 반영으로 바뀐 그 문서를 다시 분석(스크립트: 분석이 있으면 2 → 3단계 · 없으면 첫 분석) → 목적 문서면 작성 지침 다시 저장(양식의 안내는 목적 문서의 것).
    구조 반영 전 분석이 LLM 결과이고 LLM 을 쓸 수 없으면 그대로 둔다(keep — 사람이 「다시 분석」 을 누르면 redo 로 그때도 다시). → (done | nothing | left, 글)."""
    R = run.rec["range"]
    dv, _ = _fit_state(run, "division", role)
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
        st, _ = _fit_state(run, "reheads", role)
        if st["st"] != "done":
            raise _Halt("failed", f"{D_}를 다시 분석하지 못했습니다 — {st['text'] or '「헤딩 추출」 탭에서 확인하세요'}")
        again, did = f"{D_}를 다시 분석했습니다", True
        if role == "target":
            run.note(stage, "reheads", "작성 지침 저장(헤딩/표별)", tgt)
            UNIT.guides_keep(tgt)   # 구조 반영으로 자리가 바뀌었다 — 새 분석으로 다시 저장(못 해도 멈추지 않는다: 「작성요령 삭제」 가 지우기 전에 다시 남긴다)
    elif keep:
        again = f"{D_}의 분석은 구조 반영 전 것(LLM 결과 — LLM 을 쓸 수 없어 그대로 둠 · 늘어난 절·표는 못 이을 수 있음: 「다시 분석」)"
    return ("done" if did else "nothing"), again


def _do_reheads_llm(run, stage, line):
    """다시 문서 검토(LLM) — 그 줄이 닿는 문서마다(_reheads_llm_doc — 두 문서면 유료 호출을 **함께** 건다: 2026-11-20 「병렬로 처리」 · 전에는 문서마다 차례로). 줄의 상태 = 남긴 문서가 있으면 남김 · 거친 문서가 있으면 끝남. 글은 원본 → 목적 차례."""
    out = _lanes(run, [functools.partial(_reheads_llm_doc, run, stage, role, d, name) for role, d, name in _fit_docs(run, line)])
    text = " · ".join(t for _, t in out if t)
    return ("left" if any(st == "left" for st, _ in out) else "done" if any(st == "done" for st, _ in out) else "nothing"), text


def _reheads_llm_doc(run, stage, role, tgt, D_):
    """다시 문서 검토(LLM)(문서 하나) — 구조를 맞춘 그 문서의 LLM 검증·보완(유료 · 몇 분 — 문서는 안 바뀜). 이미 끝났으면(거침 · LLM 을 못 씀 · 건너뜀) 글만 · 승인 밖이면 남김."""
    st, _ = _fit_state(run, "reheadsLlm", role)
    if st["st"] == "done":
        if st.get("skipped"):
            return "nothing", f"{D_} LLM 검증·보완은 건너뜀({'LLM 을 쓸 수 없음' if UNIT.llm_ok() is False else '건너뛰기'})"
        k, t = _tidy_after(run, stage, "reheadsLlm", tgt, D_, role)   # 이미 거친 문서 — 받은 계획이 지금 그래프의 것이고 남았으면 반영만
        return ("left" if k == "left" else "done" if k == "did" else "nothing"), t
    rh, _ = _fit_state(run, "reheads", role)
    if rh["st"] != "done":
        return "left", f"{D_} LLM 검증·보완은 하지 않음(「다시 문서 검토」 가 먼저입니다 — 남은 단계)"
    if run.approval is not None and tgt not in run.approval.get("paid", ()):
        return "left", f"{D_} LLM 검증·보완은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)"
    run.guard()   # 유료 호출 전에 멈춤 요청 · 대상을 다시 본다
    _llm_job(run, stage, "reheadsLlm", tgt, D_)
    st, _ = _fit_state(run, "reheadsLlm", role)
    if st["st"] != "done":
        err = (((UNIT.facts(tgt) or {}).get("heads") or {}).get("job") or {}).get("error")
        raise _Halt("failed", f"{D_}의 LLM 검증·보완을 끝내지 못했습니다{f' — {err}' if err else ''} · 다시 누르거나 그 줄의 「건너뛰기」 로 스크립트 분석만으로 진행하세요")
    k, t = _tidy_after(run, stage, "reheadsLlm", tgt, D_, role)
    return ("left" if k == "left" else "done"), f"{D_} LLM 검증·보완을 거쳤습니다" + (f" · {t}" if t else "")


def _tail_fit(task, g, R):
    """「구성 맞추기」 — 「 · 내용은 N단계 「내용 넣기」 에서 넣습니다」(줄 하나(「다시 분석」)면 없음 — 그 줄의 글이 다음을 적는다)."""
    return "" if R.get("only") else f" · 내용은 {_stage_name(task, 'stage_fill', '내용 넣기')} 에서 넣습니다"


HANDLERS.update({"config": _do_config, "division": _do_division, "reheads": _do_reheads, "reheadsLlm": _do_reheads_llm})
_TAILS.update({"stage_fit": _tail_fit})
MATERIALS.append(_fit_materials)


# ================================================================ 사람이 하는 일(spec_워크플로우 ② §18-7 · §18-12 ⑦ — 조립한 정의 v2 의 `hand1` … 줄)
# 끝남 = 목적 문서의 확인 기록(app/flow_hands.py — 「했음」 끝점은 app/flow_hands_api.py)에 그 줄이 지금 판(정의 · 줄의 이름 · 글 — unit_steps.hand_ver)으로 적혀 있음.
# 실행기는 그 줄에 오면 기록이 있으면 지나가고 없으면 `halted`(code hand)로 멈춘다 — 사람이 하고 「했음」 을 누른 뒤 「이어서」(새 실행 · 끝난 줄은 건너뜀). 에이전트 행동에 「했음」 은 없다.
def _step_of(task, key):
    return next((s for g in task.get("stages") or () for s in g["steps"] if s["key"] == key), None) or {}


def _do_hand(run, stage, line):
    """사람이 하는 일 — 「했음」(지금 판)이면 지나감 · 아니면 멈춤 「사람이 할 일 — <이름>: <글> · 마친 뒤 그 줄의 「했음」 을 누르고 「이어서」」."""
    key, name = line["key"], line["name"]
    if UNIT.hand_done(run.target, key, UNIT.hand_ver(run.task, key)):
        return "nothing", f"{name} — 사람이 확인함"
    note = " ".join(str(_step_of(run.task, key).get("does") or "").split())
    raise _Halt("hand", f"사람이 할 일 — {name}{f': {note}' if note else ''} · 마친 뒤 그 줄의 「했음」 을 누르고 「이어서」")


def _hand_materials(task, pair, facts, opt=None):
    """상태를 셀 때 — 서버가 맡는 묶음의 사람이 하는 일 줄마다 「했음」(지금 판)인가를 목적 문서의 재료 `hands{줄 key: 참}` 에(상태 식 workflow_units._hand 가 읽는다)."""
    keys = [x["key"] for x in S.lines(task) if U.hand_key(x["key"]) and (x["unit"] or {}).get("kind") == "hand" and S.served(task, x["stage"])]   # 취합의 「배포 · 회수」(key hand)는 「했음」 을 받는 줄이 아니다
    t = (pair.get("target") or {}).get("id")
    if keys and t and facts.get(t) is not None:
        facts[t] = {**facts[t], "hands": {k: bool(UNIT.hand_done(t, k, UNIT.hand_ver(task, k))) for k in keys}}


HANDLERS.update({"hand": _do_hand})
MATERIALS.append(_hand_materials)


# ================================================================ 문서 하나(가족 single — 걸음 6: spec_워크플로우 ② §18-13 「걸음 6 — 문서 하나」) — 양식 표준화(plan_fit) · 양식 맞추기(report_fit)
# 1단계 「프로젝트 구성」: 구성 읽기(선택) → 프로젝트 구성 추출(**관문** — 사람이 확정한다) → 구조 반영(울타리 안: 계획 → 같은 검사 → 반영 한 번 — 이관형과 같은 몸통 _fit_change).
# 화면 실행(app.js divRunAll)과 다른 것은 하나 — 확정 전이면 멈춘다(양식 맞추기의 「작업 개요」 단추는 확정 없이 돌았다: ② §18-13 「사용자와 정할 것」 ⓐ — 권장대로).
# 「변경 계획 보기」 · 「구성 불러오기」 · 「구분 기준 자리 확인」 은 사람이 보는 · 고르는 줄이라 실행기는 지나간다. 끝 글은 화면 실행의 글 그대로(divRunSync · divSameText · divRunAll 의 멈춤 글).
def _one(run):
    """(문서 이름, 문서 id) — 문서 하나인 워크플로우의 그 문서(목적 문서)."""
    t = S._role(run.task, "target")
    return (t or {}).get("name") or "문서", run.target


def _do_one_read(run, stage, line):
    """구성 읽기(선택) — 입력 값이 없을 때만 문서에 적힌 단계 · 차년도 · 기관을 읽어 입력 값으로 저장한다(문서 · 확정은 그대로). 읽을 값이 없으면 남김 — 값을 지어내지 않는다."""
    D_, doc = _one(run)
    A = UNIT.div_facts(doc)
    if A is None:
        raise _Halt("missing", f"{D_}의 프로젝트 구성을 읽지 못했습니다")
    if A.get("input") or not A.get("supported"):   # 값이 이미 있음 · 구조 반영을 지원하지 않는 양식(확정이 필요 없다)
        return "nothing", ""
    values = A.get("read")
    if not values:
        run.note(stage, line["key"], f"{D_}에서 단계·차년도·기관 읽기", doc)
        got = UNIT.config_read(doc)
        values = got.data if got.ok else None
    if not values:
        return "left", f"{D_}에서 읽을 단계·차년도·기관이 없습니다(값을 지어내지 않습니다) — 「프로젝트 구성 추출」 에서 입력하거나 불러옵니다"
    run.guard()
    got = UNIT.config_save(doc, values, if_empty=True)   # 입력이 **아직 비어 있을 때만** — 읽는 사이 다른 화면 · 같은 프로젝트의 다른 문서가 저장 · 확정한 입력을 읽은 값으로 덮지 않는다(저장 쪽이 한 잠금 안에서 본다: astra A6)
    if not got.ok:
        raise _Halt(got.code, f"{D_}에서 읽은 값을 입력 값으로 저장하지 못했습니다 — {got.text}")
    if got.code == "nothing":
        return "nothing", f"{D_}에서 읽는 사이 입력 값이 생겨 읽은 값으로 바꾸지 않았습니다"
    return "done", f"{D_}에서 읽은 값을 입력 칸에 채웠습니다({U.summary_text(values)}) — 확정은 따로 합니다"


def _do_one_values(run, stage, line):
    """프로젝트 구성 추출 — 관문: 확정했으면(또는 구조 반영을 지원하지 않는 양식이면) 지나가고, 아니면 멈춘다(실행기는 저절로 확정하지 않는다 — 읽은 값도 사람이 확인한다)."""
    st, _ = _fit_state(run, line["key"])
    if st["st"] == "done":
        return "nothing", ""
    raise _Halt("notConfirmed", f"「프로젝트 구성 추출」 이 먼저입니다 — {st['text'] or '프로젝트 구성을 확정한 뒤 다시 누르세요'}")


def _one_stops(plan):
    """같은 검사에 걸렸을 때의 멈춤 글(화면 divRunAll 의 halt 글 그대로) — 기관의 차례가 마지막 반영과 다르면 그 까닭을 덧붙인다."""
    tail = "쓴 내용이 다른 기관 이름 아래에 남을 수 있습니다. " if plan.get("autoStopsKind") == "orgs" else ""
    return f"{plan['autoStops']} — {tail}목록에서 확인한 뒤 「② 반영」 을 누르세요"


def _do_one_apply(run, stage, line):
    """[문서 바뀜] 구조 반영 — 확정한 입력 값으로 울타리 안에서 계획 → 같은 검사 → 반영 한 번. 바꿀 것이 없는 계획은 「이미 맞음」(반영 기록을 남기고 끝) 과 「못 맞춤」(멈춤) 을 가른다.
    지원하지 않는 양식 = 건너뜀(헤딩 · 표 묶음을 막지 않는다)."""
    D_, doc = _one(run)
    key = line["key"]
    st, _ = _fit_state(run, key)
    if st["st"] == "done":
        return "nothing", st["text"]
    cf, _ = _fit_state(run, "values")
    if cf["st"] != "done":
        raise _Halt("notConfirmed", f"「프로젝트 구성 추출」 이 먼저입니다 — {cf['text'] or '프로젝트 구성을 확정한 뒤 다시 누르세요'}")
    d0 = UNIT.div_facts(doc)
    if not (d0 or {}).get("input"):
        raise _Halt("noValues", f"{D_}의 프로젝트 구성 값을 읽지 못했습니다 — 다시 누르세요")
    # 「반영에서 빼기」 — 시작한 화면이 알려 주었으면 그 자리(빈 목록 = 뺀 자리 없음) · 모르는 화면(첫 화면의 대시보드 …)이 시작했으면 지난 반영이 뺀 자리를 그대로(사람이 뺀 자리를 저절로 반영하지 않는다)
    given = _excl(run.rec)
    skip = given if given is not None else list((d0.get("applied") or {}).get("skip") or ())

    def pin(d):   # 울타리 안에서 — 입력 · 확정을 한 번에 읽어 「확정한 그 입력」 인지 본다(위의 검사 뒤 · 울타리를 기다리는 사이 바뀐 값으로 문서를 바꾸지 않게: astra A5) → 그 입력의 판
        A = UNIT.div_facts(d)
        if A is None:
            raise _Halt("missing", f"{D_}의 프로젝트 구성을 읽지 못했습니다")
        if not A.get("input"):
            raise _Halt("noValues", f"{D_}의 프로젝트 구성 값을 읽지 못했습니다 — 다시 누르세요")
        if not U.confirm_valid(A["input"], A.get("confirmed")):
            raise _Halt("notConfirmed", "「프로젝트 구성 추출」 이 먼저입니다 — 그 사이 프로젝트 구성 값이나 확정이 바뀌었습니다(값을 확인해 확정한 뒤 다시 누르세요)")
        return A.get("hash")
    applied = _fit_change(run, stage, key, doc, D_, None, _one_stops, adopt=True, skip=skip, pin=pin)
    data = applied.data if isinstance(applied.data, dict) else {}
    s = data.get("summary") or {}
    out = f" · 반영에서 뺀 자리 {U.nf(len(skip))}곳은 그대로" if skip else ""
    if applied.code == "nothing":   # 바꿀 것이 없는 계획 — 「이미 맞음」 과 「못 맞춤」 을 가른다(화면 divSameText)
        ok, text = U.plan_same(s)
        if not ok:
            raise _Halt("same", text)
        if data.get("named"):   # 값이 다르다고 이미 확인된 자리 — 「이미 맞음」 으로 적지 않는다(끝점이 반영 기록을 남기지 않았다: 기존 기록 그대로)
            raise _Halt("named", _named_text(D_, data["named"]))
        st, _ = _fit_state(run, key)
        if st["st"] != "done":
            raise _Halt("notApplied", "구조는 이미 값에 맞지만 그 확인을 기록하지 못했습니다 — 다시 누르세요")
        return "nothing", text + out
    st, _ = _fit_state(run, key)
    if st["st"] != "done":
        raise _Halt("notApplied", "프로젝트 구성이 반영되지 않았습니다 — 반영한 값이 지금 입력 값과 다릅니다(다시 누르세요)")
    left = len(data.get("unresolved") or ())
    return "done", (f"반영 완료 · 편집 차례 {data.get('rev')}" + (f" · 미해결 {left}곳은 손으로 맞추세요" if left else "")
                    + (f" · 지원 안 됨 {s['unsupported']}곳은 그대로" if s.get("unsupported") else "") + out)


FAMILY_HANDLERS["single"] = {"read": _do_one_read, "values": _do_one_values, "apply": _do_one_apply}   # 사람이 고르는 줄(open · load · review · plan)은 실행기가 지나간다


# ---------------------------------------------------------------- 문서 하나의 2단계 「헤딩 추출」 · 3단계 「표」(양식 표준화 — ② §18-13 갈래 「나」)
# 화면 실행(heads_run_all.js headsRunAll · hraLoop — 「전체 실행」 · heads_run_pick.js 의 단계)을 줄마다의 처리 함수로 옮긴 것: 헤딩 · 템플릿 추출(스크립트) → 헤딩 LLM 판정 · 서식 계획(이어 돌리기 「llm」 —
# 헤딩 · 템플릿 → 표 → 서식 정리 계획: 거친 것은 건너뜀) → 조정 「모두 반영」(받을 계획이 남았으면 서식 정리 계획만 다시(유료) → 울타리 안에서 다시 읽고 반영 — ADJ_MAX 번까지) / 표 구조(스크립트) → 표 판정(LLM).
# 재료 = 분석 상태(UNIT.analysis — 문서 이름 줄 · 진행표와 같은 값). 처리 함수는 늘 **새로 읽은** 분석 상태로 판단한다(상태 조회의 잠깐 든 값이 아니라).
# 화면과 같은 것: LLM 을 쓸 수 없으면 LLM 줄은 「건너뜀」 이 아니라 **남김**(ⓑ) · 헤딩 판정에 미판정이 있으면 조정을 하지 않고 남김 · 구조 반영 뒤 헤딩을 다시 뽑지 않는다(ⓓ — 있던 결과를 뼈대로).
# 화면과 다른 것: 조정이 서식 정리 계획을 다시 받는 것(유료)은 에이전트 카드가 승인한 문서일 때만(ⓒ — 사람이 누른 실행은 늘).
ADJ_MAX = 3   # 계획 받기 · 반영을 각각 몇 번까지(화면 HRA_MAX — 반영으로 새로 생긴 서식 종속 템플릿의 「계획 → 반영」 을 되풀이하는 한도)
ADJ_PAGES = 12   # 서식이 한도를 넘는 레벨을 차례로 넘길 때의 계획 받기 한도 — 못 본 서식이 줄어드는 동안만(화면 HRA_PAGES)
_STD_KEYS = ("heads", "headsLlm", "adjust", "tables", "tablesLlm")


def _std_now(doc):
    """새로 읽은 분석 상태 — 못 읽으면 멈춤."""
    v = UNIT.analysis(doc)
    if v is None:
        raise _Halt("missing", "분석 상태를 읽지 못했습니다 — 다시 누르세요")
    return v


def _std_state(run, key, v=None):
    """그 줄의 지금 상태(새로 읽은 분석 상태로 — 화면에 보이는 셈과 같은 식) → (상태, 분석 상태)."""
    doc = run.target
    v = v or _std_now(doc)
    f = UNIT.facts(doc)
    facts = {doc: {**f, "std": v} if f is not None else None}
    ctx = S.context(run.task, run.pair, facts, llm=UNIT.llm_ok(), skip=())
    return (U.state(key, ctx, "single") or {"st": "todo", "text": ""}), v


def _std_materials(task, pair, facts, opt=None):
    """상태를 셀 때 — 문서 하나의 헤딩 · 표 줄을 서버가 맡으면 그 문서의 분석 상태(`std`)를 덧붙인다. 조회(`GET …/flow`)는 잠깐 든 값(서식 갈래 · 자리 셈을 조회마다 되풀이하지 않는다) ·
    **실행의 판단**(시작의 「남은 일 없음」 · 묶음 경계 — opt.fresh)은 새로 읽는다: 그 값은 문서 차례로만 무르는데 서식 계획 · LLM 결과는 같은 문서 차례에 도착한다(astra C1)."""
    if S.family(task) != "single" or not any(x["key"] in _STD_KEYS and S.served(task, x["stage"]) for x in S.lines(task)):
        return
    t = (pair.get("target") or {}).get("id")
    if t and facts.get(t) is not None:
        facts[t] = {**facts[t], "std": UNIT.analysis(t, fresh=bool((opt or {}).get("fresh")))}


def _do_std_script(run, stage, line):
    """헤딩 · 템플릿 추출 · 표 구조(스크립트 — 배경 일) — 결과가 없을 때만. 헤딩 그래프가 없으면 첫 분석(헤딩 그래프 → 표 구조), 표 구조만 없으면 그 단계만."""
    D_, doc = _one(run)
    key = line["key"]
    st, v = _std_state(run, key)
    if st["st"] == "done":
        return "nothing", ""
    if st["st"] == "blocked" or "heads" not in U.std_items(v):   # 분석 상태를 못 읽음 · 헤딩 추출이 없는 문서(hwpx 아님)
        raise _Halt("blocked", st["text"])
    name = U.STD_NAMES[key]
    run.note(stage, key, f"{D_} {name}(스크립트)", doc)
    _analyze(run, stage, key, doc, D_, 3 if key == "tables" and U.std_items(v)["heads"].get("state") == "done" else "first")
    st, _ = _std_state(run, key)
    if st["st"] != "done":
        raise _Halt("failed", f"{name}이(가) 끝나지 않았습니다 — {st['text']}(「헤딩 추출」 탭에서 확인)")
    return "done", f"{name} — {st['text']}" if st["text"] else name


def _std_paid_ok(run, doc):
    """이 문서에 유료 LLM 을 불러도 되나 → "" | 남기는 까닭 — LLM 을 쓸 수 없음 · 에이전트 카드가 승인한 문서가 아님."""
    if not UNIT.llm_ok():
        return "LLM 을 쓸 수 없습니다 — 스크립트 결과로 남깁니다(LLM 을 켠 뒤 이어서 합니다)"
    if run.approval is not None and doc not in run.approval.get("paid", ()):
        return "실행 카드에서 승인한 유료 호출이 아님 — 남은 단계"
    return ""


def _std_tried(run):
    """이번 실행이 **이미 유료로 불렀지만 답을 못 받은** 문서 하나의 LLM 줄 {줄 key: 그때의 상태 글} — 같은 실행의 뒤 줄이 같은 것을 다시 부르지 않게(헤딩 LLM 판정의 이어 돌리기는 표 판정도 같이 부른다:
    그 표 판정이 실패했는데 뒤의 「표 판정(LLM)」 줄이 같은 표를 또 유료로 부르지 않는다 — astra B3). 다음 실행(사람이 다시 누름)은 다시 부른다."""
    t = getattr(run, "std_tried", None)
    if t is None:
        t = run.std_tried = {}
    return t


def _do_std_llm(run, stage, line):
    """헤딩 LLM 판정 · 서식 계획 / 표 판정(LLM)(유료 · 몇 분 — 문서는 안 바뀜). 이미 거쳤으면 지나감 · 스크립트 결과가 먼저 · LLM 을 못 쓰거나 승인 밖이면 **남김**.
    헤딩 판정이 답을 못 내면 멈춘다(뒤의 조정을 잇지 않는다) · 표 판정이 답을 못 내면 스크립트 결과로 남긴다.
    도는 다른 헤딩 작업을 기다린 뒤에는 그 작업이 이미 해 놓았는지 다시 보고(해 놓았으면 다시 부르지 않는다) · 이 실행의 헤딩 줄이 같이 부른 표 판정이 답을 못 냈으면 표 줄이 다시 부르지 않고 남긴다(_std_tried) ·
    사람이 문서 진행표에서 그 작업을 멈췄으면 실행도 멈춘다(_llm_job 의 stops)."""
    D_, doc = _one(run)
    key = line["key"]
    heads = key == "headsLlm"
    name, base = U.STD_NAMES[key], "heads" if heads else "tables"
    st, v = _std_state(run, key)
    if st["st"] == "done":
        return "nothing", ""
    if st["st"] == "blocked":
        raise _Halt("blocked", st["text"])
    if _std_state(run, base, v)[0]["st"] != "done":
        return "left", f"{name}은(는) 하지 않음(「{U.STD_NAMES[base]}」 이 먼저입니다 — 남은 단계)"
    tried = _std_tried(run)
    if key in tried:   # 이 실행이 이미 유료로 불렀고 답을 못 받았다 — 같은 실행에서 다시 부르지 않는다
        return "left", f"{name}은(는) 다시 부르지 않음(이 실행의 「{U.STD_NAMES['headsLlm']}」 이 같이 불렀지만 답을 내지 못했습니다 — {tried[key] or st['text']} · 스크립트 결과로 남깁니다 · 다시 누르면 다시 합니다)"
    why = _std_paid_ok(run, doc)
    if why:
        return "left", f"{name}은(는) 하지 않음({why})"
    done = lambda: _std_state(run, key)[0]["st"] == "done"  # noqa: E731 — 기다린 다른 작업이 이미 해 놓았나(문서에서 다시 본다)
    if heads:   # 이어 돌리기 「llm」 — 헤딩 · 템플릿 → 표 → 서식 정리 계획(이미 거친 것은 그 실행이 건너뛴다)
        both = any(p.get("key") == "tables" and p.get("run") for p in v.get("llmPlan") or ())   # 이 이어 돌리기가 표 판정도 부르나(분석 상태의 「돌 것」)
        job = _llm_job(run, stage, key, doc, D_, note=f"{D_} 헤딩 LLM 판정 · 서식 계획(헤딩 · 템플릿 → 표 → 서식 정리 계획 · 몇 분)", done=done, stops=True)
        ts = _std_state(run, "tablesLlm")[0] if job is not None and both else None
        if ts is not None and ts["st"] != "done":   # 같이 부른 표 판정이 답을 못 냈다 — 뒤의 표 줄에 넘긴다
            tried["tablesLlm"] = ts["text"]
    else:
        _llm_job(run, stage, key, doc, D_, start=UNIT.start_tables_llm, what="표 판정(LLM)", note=f"{D_} 표 판정(LLM) — 수 분", done=done, stops=True)
    st, _ = _std_state(run, key)
    if st["st"] != "done":
        if heads:
            raise _Halt("failed", f"헤딩 LLM 판정이 끝나지 않았습니다 — {st['text']}(스크립트 결과로 남습니다 · 조정은 하지 않았습니다)")
        return "left", f"표 판정(LLM)이 답을 내지 못했습니다 — {st['text']}(스크립트 결과로 남깁니다 · 다시 누르면 다시 합니다)"
    return "done", f"{name} — {st['text']}" + (f" · 같이 부른 표 판정(LLM)은 답을 내지 못했습니다(「{U.STD_NAMES['tablesLlm']}」 에 남습니다)" if heads and "tablesLlm" in tried else "")


def _adjust_text(d, undo=True):
    """조정이 한 것 한 줄(화면 hraDone 의 그 몫) | "". undo = 「실행 취소」 로 되돌린다고 적나 — 묶음째 실행은 끝에 확정해 실행 취소 기록이 비므로 적지 않는다(확정하지 못하면 끝 글의 꼬리가 말한다: ② §18-24)."""
    one = (f"템플릿 {U.nf(d['tpls'])}개 반영(맞춘 줄 {U.nf(d['lines'])}" + (f" · 대표 변경 {U.nf(d['reps'])}" if d["reps"] else "") + (f" · 서식 종속 템플릿 {U.nf(d['splits'])}" if d["splits"] else "") + ")") if d["tpls"] else ""
    got = " · ".join(x for x in (one, f"자리 맞춤 {U.nf(d['placed'])}줄" if d["placed"] else "", f"템플릿 종속 {U.nf(d['merged'])}" if d["merged"] else "") if x)
    return f"조정 — {got}" + (f" · 「실행 취소」 {U.nf(d['applies']) + '번' if d['applies'] > 1 else '한 번'}으로 되돌립니다" if d["applies"] and undo else "") if got else ""


def _do_std_adjust(run, stage, line):
    """[문서 바뀜] 조정 「모두 반영」(문서 하나의 줄) — 몸은 문서마다의 _adjust_doc(이관형의 LLM 검증·보완 뒤 반영도 같은 몸)."""
    D_, doc = _one(run)
    st, text, _ = _adjust_doc(run, stage, "adjust", doc, D_)
    return st, text


def _adjust_doc(run, stage, key, doc, D_, fresh_only=False):
    """[문서 바뀜] 조정 「모두 반영」 — 문서 하나. 헤딩 판정(LLM) 뒤에: (받을 계획이 남았으면 서식 정리 계획만 다시 — 유료) → 울타리 안에서 분석 상태를 다시 읽고 방금 읽은 그 계획 · 확실한 종속 · 자리 맞춤을 반영 →
    반영으로 새로 생긴 서식 종속 템플릿에 받을 계획이 남으면 되풀이(각각 ADJ_MAX 번까지). 헤딩 판정에 미판정이 있으면 반영하지 않고 남긴다 · 표준 검사가 되돌리면 멈춤 · 그 사이 바뀌었으면 다시 읽는다.
    남긴 것(그대로 둔 줄 · 못 받은 계획 · 한도)은 실패로도 「끝남」 으로도 적지 않는다 — 무엇이 몇 줄 · 어디서 보정하는지.
    fresh_only = **지금 그래프의 받은 계획**이 있을 때만 한다(이관형의 LLM 검증·보완 · 다시 문서 검토(LLM) 뒤 — spec_워크플로우 ② §18-25): 반영할 받은 계획이 없으면 아무것도 안 하고
    (헤딩 추출이 없는 문서도 · 구조 반영으로 계획이 옛것이 된 문서에 유료로 계획을 다시 받지 않는다), 처음 반영하기 전에는 계획을 새로 받지 않는다(반영으로 새로 생긴 서식 종속 템플릿의 것만).
    → (done | nothing | left, 끝 글, 한 것 {tpls, lines, splits, reps, placed, merged, applies})."""
    did = {"tpls": 0, "lines": 0, "splits": 0, "reps": 0, "placed": 0, "merged": 0, "applies": 0}
    notes, asked, chains, tries, seen = [], None, 0, 0, None
    llm = UNIT.llm_ok()
    for _ in range(ADJ_PAGES + ADJ_MAX * 3 + 4):   # 돌 수 있는 가장 많은 차례(계획 받기 · 반영 · 기다림) — 그 안에 끝나지 않으면 아래에서 남긴다(끝없이 돌지 않게)
        run.guard()
        if fresh_only and not did["applies"] and UNIT.analysis(doc) is None:
            return "nothing", "", did   # 분석 상태를 못 읽음 — LLM 줄을 멈추지 않고 반영만 하지 않는다
        v = _std_now(doc)
        st = U.std_adjust_state(v, doc, llm)
        if "heads" not in U.std_items(v):
            if fresh_only:
                return "nothing", "", did
            raise _Halt("blocked", st["text"])
        if st["st"] == "busy" or v.get("busy"):   # 다른 헤딩 작업(서식 정리 계획 …)이 끝난 뒤에
            run.working = {doc}
            run.wait(doc, WAIT["llm"], f"{D_}의 헤딩 작업")
            continue
        if (U.std_items(v)["heads"].get("llm") or {}).get("state") != "done":
            return "left", "조정은 하지 않음(헤딩 LLM 판정이 먼저입니다 — 남은 단계)", did
        P = U.std_left(v)
        if fresh_only and not did["applies"] and not (P["at"] and P["apply"]):
            return "nothing", "", did   # 지금 그래프의 받은 계획이 없다 — 반영할 것도 · 새로 받을 것도 없다(유료를 부르지 않는다)
        sig = sorted(f"{x.get('tpl')}:{x.get('omitted') or 0}" for x in P["need"])   # 받을 계획의 꼴 — 같은 것이 그대로 남았으면 다시 묻지 않는다(방금 못 받은 계획을 되풀이해 부르지 않게)
        om = sum(x.get("omitted") or 0 for x in P["need"])
        paging = seen is not None and om < seen   # 못 본 서식이 앞 차례보다 줄었다(서식이 많은 레벨을 차례로 넘기는 중) — 되풀이 한도와 따로 센다(화면 HRA_PAGES)
        if P["need"] and sig != asked and chains < (ADJ_PAGES if paging else ADJ_MAX) and not (fresh_only and not did["applies"]):
            why = _std_paid_ok(run, doc)
            asked, seen = sig, om
            if why:
                notes.append(f"서식 정리 계획을 받지 않은 템플릿 {U.nf(len(P['need']))}개({why})")
            else:
                chains += 1
                # 유료 — _llm_job 이 시작 직전에 멈춤 요청 · 대상을 다시 보고(위에서 분석 상태를 읽는 사이 온 멈춤이 새 호출을 내지 않게), 도는 다른 작업을 기다린 뒤에는 받을 계획이 아직 남았을 때만 다시 건다 ·
                # 사람이 문서 진행표에서 그 작업을 멈췄으면 실행도 멈춘다(다음 차례가 계획을 다시 유료로 부르지 않게 — astra B3 · B4)
                job = _llm_job(run, stage, key, doc, D_, start=lambda d: UNIT.start_formats(d, run.rec.get("skill")), what="서식 정리 계획 받기",
                               note=f"{D_} 서식 정리 계획 받기 — 템플릿 {U.nf(len(P['need']))}개(유료)", done=lambda: not U.std_left(_std_now(doc))["need"], stops=True)
                if job and job.get("error"):
                    notes.append(f"서식 정리 계획을 받지 못함 — {job['error']}")   # 받은 계획은 반영하고 못 받은 템플릿은 남긴다
            continue
        if P["apply"] and P["undecided"]:
            break   # 다 판정하지 못한 헤딩 그래프 위의 계획은 사람이 보고 반영한다(남긴다)
        if P["apply"] and tries < ADJ_MAX:
            tries += 1
            got = None
            run.note(stage, key, (f"{D_} " if fresh_only else "") + f"조정 — {U.std_apply_text(P)}", doc)
            run.working = {doc}
            with run.fence(doc):
                run.guard()
                v2 = _std_now(doc)   # 울타리 안에서 다시 — 고치던 글이 서버에 온 뒤의 문서 · 그때의 계획
                P2, H2 = U.std_left(v2), U.std_items(v2).get("heads") or {}
                # 울타리 안에서 헤딩 판정(LLM)이 끝났는지 · 미판정이 없는지를 **함께** 다시 본다 — 울타리를 기다리는 사이 헤딩을 다시 뽑았으면(스크립트 재추출) 판정 전의 그래프다: 그 위에 반영하지 않는다(astra B2)
                judged = (H2.get("llm") or {}).get("state") == "done"
                if judged and P2["apply"] and not P2["undecided"] and not v2.get("busy"):
                    graph = [H2.get("run"), H2.get("at")] if H2.get("run") is not None else None   # 판정을 본 그 헤딩 그래프(실행 번호 · 만든 때) — 반영 직전에 문이 지금 그래프와 견준다(다르면 stale)
                    got = UNIT.adjust_apply(doc, v2["rev"], P2["at"], graph=graph)
            run.working = set()
            if got is None or got.code in ("stale", "nothing"):
                continue   # 그 사이 바뀌었거나 반영할 것이 없어졌다 — 다시 읽는다(한도 안에서)
            if not got.ok:
                raise _Halt(got.code, "조정(모두 반영)을 하지 못했습니다 — " + ("표준 검사에 걸려 되돌렸습니다: " if got.code == "rejected" else "") + (got.text or "반영 요청이 거절되었습니다"))
            r = got.data if isinstance(got.data, dict) else {}
            ts = r.get("templates") or []
            did["applies"] += 1
            did["tpls"] += len(ts)
            did["lines"] += max(0, len(r.get("changed") or ()) - len(r.get("placed") or ()) - len(r.get("left") or ()))   # 대표에 맞춘 줄(모양만 맞춘 줄은 빼고)
            did["placed"] += len(r.get("placed") or ())
            did["splits"] += sum(len(t.get("splits") or ()) for t in ts)
            did["reps"] += sum(1 for t in ts for x in t.get("levels") or () if x.get("repChanged"))
            did["merged"] += len(r.get("merged") or ())
            continue
        break
    v = _std_now(doc)
    st, P = U.std_adjust_state(v, doc, llm), U.std_left(v)
    head = _adjust_text(did, undo=not _commit_on(run))   # 묶음째 실행은 끝에 확정한다 — 「실행 취소」 를 약속하지 않는다(② §18-24)
    if st["st"] == "done":
        left = U.std_unseen(P) + notes   # 미판정도 끝 글에(수 · 다시 판정할 곳) — 반영할 것이 없어 줄은 끝났어도 「다 봤다」 는 아니다(astra P2: 화면의 전체 실행도 그 수를 알린다)
        text = (head or "반영할 것이 남지 않았습니다") + (f" · 남긴 것: {' / '.join(left)}" if left else "")
        return ("done" if did["applies"] else "nothing"), text, did
    if P["apply"] and P["undecided"]:
        notes.insert(0, U.std_undecided_text(P["undecided"]) + "(받은 계획은 남아 있습니다)")
    elif P["apply"]:
        notes.insert(0, f"되풀이 한도({ADJ_MAX}번)에 닿아 멈췄습니다 — 반영하지 않은 것: {U.std_apply_text(P)}(다시 누르면 남은 것부터)")
    elif P["need"] and not notes:
        notes.append(f"서식 정리 계획을 받지 않은 템플릿 {U.nf(len(P['need']))}개 — 「계획 보기」 의 「계획 받기」")
    return "left", " · ".join(x for x in (head, "남긴 것: " + " / ".join(notes) if notes else st["text"]) if x), did


FAMILY_HANDLERS["single"].update({"heads": _do_std_script, "tables": _do_std_script, "headsLlm": _do_std_llm, "tablesLlm": _do_std_llm, "adjust": _do_std_adjust})   # tree · tableTools 는 사람이 한다
MATERIALS.append(_std_materials)


# ================================================================ 취합(가족 gather — 걸음 5: spec_워크플로우 ② §18-13 갈래 「다」) — 원본 문서(기관 문서) 여럿 → 목적 문서(취합본) 하나
# 화면 실행(gather.js gatherRunConfig · gatherRunFrame · gatherRunMap)을 줄마다의 처리 함수로 옮긴 것. 1단계 「프로젝트 구성 추출」 은 같이 쓰는 config(구성의 기준 = 취합본 자신 — _fit_names 가 base 를 따른다).
# 2단계: 프로젝트 구성 반영(반영 기록이 없으면 구조 확인 adopt 먼저 → 아니면 울타리 안 계획 → 같은 검사 → (간단 모드) 지울 것이 있으면 멈춤 → 반영 한 번) → 배포 기준본(분석이 지금 문서의 것이 아니면 2 → 3단계 다시 분석하고 한 번 더).
# 3단계: **원본 문서마다 한 덩이**(_each — 등록한 차례 · 시작할 때 못 박은 목록): 반영할 기관 → 헤딩 · 표 분석 → 자리 연결 → LLM 검토(한 번 · 실패해도 계속) → 넣기 계획 → 내용 반영(울타리 · 낡은 계획이면 한 번만 다시).
# 그 문서만 남기는 것(뒤 문서는 이어 간다): 반영할 기관 미지정 · 다른 판의 기준본 · 기준본과 맞는 자리 없음. 전체를 멈추는 것: 자리 연결 · 계획 실패 · 표준 검사 · 둘째 낡은 계획(뒤 문서가 공통 자리를 차지하므로 건너뛰지 않는다).
# 화면과 다른 것: **낡은 기준본은 등록한 기관 문서가 있으면 다시 만들지 않고 멈춘다**(화면은 조용히 다시 만든다 — 새 기준본이 등록된 문서를 「다른 판」 으로 만든다) · 실행 중 상태는 그 문서 하나만 읽는다(UNIT.gather_row).
def _gather_materials(task, pair, facts, opt=None):
    """상태를 셀 때 — 취합의 줄을 서버가 맡으면 목적 문서의 취합 상태(`gather`)를 덧붙인다(기관 문서마다의 줄 · 배포 기준본)."""
    if S.family(task) != "gather" or not any(S.served(task, g["id"]) for g in task["stages"]):
        return
    t = (pair.get("target") or {}).get("id")
    if t and facts.get(t) is not None:
        facts[t] = {**facts[t], "gather": UNIT.gather(t)}


def _g_state(run, key):
    """그 줄의 지금 상태(화면에 보이는 셈과 같은 식 — 목적 문서의 구성 · 취합 상태로)."""
    tgt = run.target
    f = UNIT.facts(tgt)
    facts = {tgt: {**f, "div": UNIT.div_facts(tgt), "gather": UNIT.gather(tgt)} if f is not None else None}
    ctx = S.context(run.task, run.pair, facts, llm=UNIT.llm_ok(), skip=())
    return U.state(key, ctx, "gather") or {"st": "todo", "text": ""}


def _g_no(run, gid):
    g = next((x for x in run.task["stages"] if x["id"] == gid), None) or {}
    no, name = S.stage_label(g)   # 취합 묶음의 번호 · 이름은 화면의 목록에 있다(등록부에는 meta 만)
    return f"{no} 「{name or gid}」".strip()


def _do_g_division(run, stage, line):
    """[문서 바뀜] 프로젝트 구성 반영 — 반영 기록이 없고 구조가 이미 값에 맞으면 확인만(adopt — 울타리 없이) · 아니면 울타리 안에서 계획 → 같은 검사 → (간단 모드) 지울 것이 있으면 멈춤 → 반영 한 번."""
    D_, tgt = _one(run)
    st = _g_state(run, "division")
    if st["st"] == "done":
        return "nothing", ""
    cf, _ = _fit_state(run, "config")
    if cf["st"] != "done":
        raise _Halt("notConfirmed", f"「프로젝트 구성 추출」 이 먼저입니다 — {cf['text'] or '프로젝트 구성(단계·차년도·기관)을 확정한 뒤 다시 누르세요'}")
    d = UNIT.div_facts(tgt)
    if d is None:
        raise _Halt("missing", f"{D_}의 프로젝트 구성을 읽지 못했습니다")
    if not d.get("supported"):
        raise _Halt("unsupportedForm", "이 양식은 프로젝트 구성 자동 반영을 지원하지 않습니다")
    values, named = d.get("input"), 0
    if not d.get("applied"):   # 한 번도 반영한 적 없는 문서 — 구조가 이미 값에 맞으면 「반영됨」 으로 적는다(구조를 맞춘 프레임을 새로 올린 문서)
        run.note(stage, "division", "구조 확인(이미 값에 맞는지)", tgt)
        named = _adopt_named(UNIT.division_adopt(tgt))   # 못 해도(그 사이 바뀜 …) 아래 계획 → 반영으로 간다 · named = 다른 이름의 기관 자리가 남아 적지 않음
        if _g_state(run, "division")["st"] == "done":
            return "done", "구조가 이미 값에 맞음(확인함)"
    here = _g_no(run, stage)

    def gone(plan):   # 간단 모드 — 구조를 맞추려면 글을 지워야 하면 저절로 지우지 않는다(문서에서 읽은 값이 틀리면 절이 지워진다)
        n = ((plan.get("summary") or {}).get("removed") or 0) + ((plan.get("summary") or {}).get("deleted") or 0)
        return f"구조를 값에 맞추려면 {U.nf(n)}곳을 지워야 합니다 — 자동으로 지우지 않습니다. {here} 의 변경 계획을 확인하고 반영한 뒤 「이어서」 를 누르세요(문서에서 읽은 값이 틀리면 절이 지워집니다)" if n else ""
    applied = _fit_change(run, stage, "division", tgt, D_, values, lambda plan: f"{plan['autoStops']} — 저절로 반영하지 않습니다. {here} 의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요",
                          check=gone if run.rec.get("quick") else None)
    st = _g_state(run, "division")
    if st["st"] != "done":
        if named and applied.code == "nothing":   # 바꿀 것은 없는데 다른 이름의 기관 자리가 남은 문서 — 「이미 맞음」 으로 적지 않은 까닭을 알린다
            raise _Halt("named", _named_text(D_, named))
        raise _Halt("notApplied", f"프로젝트 구성이 반영되지 않았습니다 — {st['text'] or '반영 요청이 거절되었습니다'}")
    return "done", ""


def _do_g_frame(run, stage, line):
    """배포 기준본 만들기 — 문서는 안 바뀐다. 헤딩 · 표 분석이 지금 문서의 것이 아니면(staleHeadings) 2 → 3단계를 스크립트로 다시 분석하고 한 번 더.
    **낡은 기준본은 등록한 기관 문서가 있으면 다시 만들지 않고 멈춘다**(새 기준본은 새 판 — 앞서 나눠 준 기준본으로 온 문서를 저절로 넣지 못하게 된다: 사람이 정한다)."""
    D_, tgt = _one(run)
    if _g_state(run, "frame")["st"] == "done":
        return "nothing", ""
    G = UNIT.gather(tgt)
    if G is None:
        raise _Halt("missing", "취합 상태를 읽지 못했습니다 — 다시 누르세요")
    if G.get("frame") and G.get("parts"):
        raise _Halt("frameStale", "기준본을 만든 뒤 프로젝트 구성을 다시 반영해 기준본이 낡았습니다 — 저절로 다시 만들지 않습니다: 새 기준본은 새 판이라 앞서 나눠 준 기준본으로 온 기관 문서를 저절로 넣지 못하게 됩니다. "
                    f"{_g_no(run, stage)} 의 「기준본 다시 만들기」 로 정한 뒤 다시 누르세요")
    for tries in (0, 1):
        run.guard()
        run.note(stage, "frame", "기준본 만들기", tgt)
        got = UNIT.gather_frame(tgt)
        if got.ok:
            break
        why = UNIT.reason(got)
        if why != "staleHeadings" or tries:
            raise _Halt(why or got.code, f"기준본을 만들지 못했습니다 — {got.text or U.GT_REASON.get(why, '까닭 모름')}")
        for how in (2, 3):   # 2단계(헤딩 그래프) → 3단계(표 구조) · 스크립트만 — 지금 문서로 다시
            run.note(stage, "frame", f"헤딩·표 분석 {how}단계(스크립트 — 지금 문서로 다시)", tgt)
            _analyze(run, stage, "frame", tgt, D_, how)
    if _g_state(run, "frame")["st"] != "done":
        raise _Halt("failed", "기준본이 만들어지지 않았습니다")
    return "done", "구조를 맞추고 배포 기준본을 만들었습니다 — 「기준본 내려받기」 로 받아 기관에 나눠 주세요"


def _each(run, gid, block):
    """원본 문서마다 한 덩이 — 시작할 때 못 박은 원본 문서들을 차례로, 문서 하나에 그 덩이의 줄을 끝까지 한 뒤 다음 문서로(앞 문서의 반영이 목적 문서를 바꿔 뒤 문서의 자리 연결이 달라진다).
    줄의 처리 함수는 run.part(그 문서의 기억 — id · name · L 연결 목록 · plan 넣기 계획 · skip 이 문서는 여기까지) · run.each(덩이의 셈)를 쓴다. → (done | nothing | left, 묶음 끝 글의 몫)."""
    E = run.each = {"done": [], "unassigned": [], "blocked": [], "notes": [], "sum": {}, "calc": 0, "left": False}
    for src in list(run.pair.get("sources") or ()):
        run.guard()
        run.part = {"id": src["id"], "name": src.get("name") or src["id"], "L": None, "plan": None, "skip": False, "fresh": True}
        for line in block:
            if run.part["skip"]:
                break
            run.guard()
            t0 = time.time()
            run.note(gid, line["key"], f"{run.part['name']} — {line['name']}", src["id"])
            res = _line(run, gid, line)
            run.working = set()
            if res[0] != "nothing" or res[1]:   # 한 일이 없고 글도 없는 줄은 기록에 남기지 않는다(문서 × 줄이 많다)
                run.step(gid, line["key"], res[0], f"{run.part['name']} — {res[1]}" if res[1] else run.part["name"], doc=src["id"], t0=t0)
            E["left"] = E["left"] or res[0] == "left"
    run.part = None
    counts = U.gt_done_text({"counts": E["sum"]})
    tail = " · ".join(x for x in (f"반영할 기관 미지정 {len(E['unassigned'])}개는 건너뜀({' · '.join(E['unassigned'])})" if E["unassigned"] else "",
                                  f"저절로 넣지 못한 문서 {len(E['blocked'])}개({' · '.join(E['blocked'])} — 끌어 넣기로)" if E["blocked"] else "",
                                  f"다시 계산 필요 {E['calc']}칸" if E["calc"] else "", *E["notes"]) if x)
    text = (f"기관 문서 {len(E['done'])}개 반영 — {counts}" if E["done"] else "넣을 것이 없습니다(이미 넣었거나 넣을 수 있는 자리가 없음)") + (f" · {tail}" if tail else "")
    return ("left" if E["left"] else "done" if E["done"] else "nothing"), text


def _g_link(run, gid, key, fresh):
    """그 기관 문서의 자리 연결 → 연결 목록 | None(저절로 넣을 수 없는 문서 — 이 문서는 여기까지). 기관 문서의 분석이 없으면 한 번 분석하고 다시 · 그 밖의 까닭은 전체 멈춤."""
    P, tgt, E = run.part, run.target, run.each
    for tries in (0, 1):
        got = UNIT.gather_links(tgt, P["id"], fresh)
        if got.ok:
            P["L"] = got.data
            return got.data
        why = UNIT.reason(got)
        if why == "noHeadings" and not tries:
            run.note(gid, key, f"{P['name']} — 헤딩·표 분석(스크립트)", P["id"])
            _analyze(run, gid, key, P["id"], P["name"], "first")
            fresh = True
            continue
        if why in ("noMatch", "frameDiffers"):   # 저절로 넣을 수 없는 문서 — 끌어 넣기로. 다른 문서는 이어 간다
            E["blocked"].append(f"{P['name']}({U.GT_REASON[why]})")
            P["skip"] = True
            return None
        raise _Halt(why or got.code, f"「{P['name']}」 의 자리 연결을 하지 못했습니다 — {got.text or U.GT_REASON.get(why, '까닭 모름')}")
    return None


def _do_g_part(run, gid, line):
    """반영할 기관 — 정해져 있으면 지나감(사람이 정한 것은 안 건드린다) · 간단 모드에서 이번에 올린 미지정 문서만 자동 지정(파일 이름 → 추천) · 못 정하면 그 문서만 남긴다."""
    P, tgt, E = run.part, run.target, run.each
    row = UNIT.gather_row(tgt, P["id"])
    if row is None:   # 도는 중에 취합에서 뺀 문서
        P["skip"] = True
        return "nothing", "취합에서 뺀 문서 — 건너뜀"
    if row.get("orgs"):
        return "nothing", ""
    if P["id"] in (run.rec.get("auto") or ()):
        run.note(gid, "part", f"{P['name']} — 자리 연결(기준본과 견주기)", P["id"])
        if _g_link(run, gid, "part", True) is None:
            return "left", "기준본과 견줄 수 없어 반영할 기관을 정하지 못함 — 끌어 넣기로"
        run.guard()
        run.note(gid, "part", f"{P['name']} — 반영할 기관 정하기(파일 이름 → 추천)", P["id"])
        got = UNIT.gather_auto(tgt, P["id"])
        if not got.ok:
            raise _Halt(got.code, f"「{P['name']}」 의 반영할 기관을 정하지 못했습니다 — {got.text}")
        A = (got.data or {}).get("auto") or {}
        if A.get("org"):
            P["fresh"], P["L"] = False, None   # 방금 맞췄다 — 판정만 새로(반영할 기관이 바뀌었다)
            name = next((o.get("name") for o in (got.data or {}).get("orgs") or () if o.get("key") == A["org"]), A["org"])
            return "done", f"반영할 기관 → {name}({'파일 이름' if A.get('by') == 'name' else '작성 내용이 가장 많은 기관'})"
    E["unassigned"].append(P["name"])
    P["skip"] = True
    return "left", "반영할 기관을 정하지 못함 — 넣지 않고 건너뜁니다(기관 문서 줄에서 고른 뒤 다시)"


def _do_g_heads(run, gid, line):
    """기관 문서의 헤딩 · 표 분석 — 없을 때만 그 문서 하나를 스크립트로(원본을 한꺼번에 걸지 않는다)."""
    P = run.part
    row = UNIT.gather_row(run.target, P["id"]) or {}
    if "noHeadings" not in (row.get("reasons") or ()):
        return "nothing", ""
    _analyze(run, gid, "heads", P["id"], P["name"], "first")
    P["fresh"] = True
    return "done", "헤딩·표 분석(스크립트)"


def _do_g_link(run, gid, line):
    """자리 연결 · 기관 작성 내용 판정 — 넣을 것이 안 남은 문서는 지나감 · 저절로 넣을 수 있는 것이 없으면(겹침 · 확인 필요만) 이 문서는 여기까지."""
    P, tgt = run.part, run.target
    row = UNIT.gather_row(tgt, P["id"]) or {}
    if P["fresh"] and row.get("counts") and U.gt_part_todo(row) == 0 and not U.gt_hard(row.get("reasons")):   # 넣을 것이 안 남음(이미 넣은 문서)
        P["skip"] = True
        return "nothing", ""
    L = _g_link(run, gid, "link", P["fresh"])
    if L is None:
        return "left", "저절로 넣을 수 없는 문서 — 끌어 넣기로"
    if not U.gt_todo(L):
        P["skip"] = True
        return "nothing", "저절로 넣을 수 있는 것이 없습니다(겹침 · 확인 필요만 남음)"
    return "done", f"넣을 수 있음 {U.nf((L.get('counts') or {}).get('ready') or 0)}곳"


def _do_g_llm(run, gid, line):
    """LLM 검토(선택 · 묶음째 유료 · 한 번) — 아직 검토 전일 때만. 실패해도 멈추지 않는다(스크립트가 넣을 수 있다고 본 것만 넣는다) · 승인 밖은 전체 멈춤."""
    P, tgt, E = run.part, run.target, run.each
    L = P["L"] or {}
    if L.get("llm"):
        return "nothing", ""
    if run.rec.get("llm") is False:
        E["notes"].append(f"「{P['name']}」 LLM 검토는 끔")
        return "nothing", ""
    if not UNIT.llm_ok():
        E["notes"].append(f"「{P['name']}」 LLM 검토는 못 함(LLM 을 쓸 수 없음)")
        return "nothing", "LLM 검토는 못 함(LLM 을 쓸 수 없음) — 스크립트가 넣을 수 있다고 본 것만 넣습니다"   # 글을 남긴다(그 문서의 줄 기록 — 간단 모드의 문서별 결과가 읽는다)
    if not _stage_paid_ok(run, gid):
        raise _Halt("approval", "기관 작성 내용의 LLM 검토는 실행 카드에서 승인한 유료 호출이 아닙니다 — 카드에서 다시 승인하세요")
    run.guard()
    run.note(gid, "llm", f"{P['name']} — LLM 검토(넣을 수 있음 {U.nf((L.get('counts') or {}).get('ready') or 0)}곳 · 수십 초)", P["id"])
    got = UNIT.gather_llm(tgt, P["id"])
    if not got.ok:
        E["notes"].append(f"「{P['name']}」 LLM 검토는 못 함")
        return "left", f"LLM 검토는 못 함({got.text or U.GT_REASON.get(UNIT.reason(got), '답을 받지 못함')}) — 스크립트가 넣을 수 있다고 본 것만 넣습니다"
    P["L"] = got.data
    if not U.gt_todo(got.data):
        P["skip"] = True
        return "done", "LLM 검토함 — 넣을 것이 남지 않았습니다"
    return "done", "LLM 검토함"


def _g_plan(run, gid):
    P = run.part
    got = UNIT.gather_plan(run.target, P["id"])
    if not got.ok or not isinstance(got.data, dict) or not got.data.get("planId"):
        raise _Halt(UNIT.reason(got) or got.code, f"「{P['name']}」 의 넣기 계획을 세우지 못했습니다 — {got.text or '계획이 없습니다'}")
    P["plan"] = got.data
    return got.data


def _do_g_plan(run, gid, line):
    """넣기 계획 — 문서는 안 바뀐다. 넣을 것이 없으면 이 문서는 여기까지(실패가 아니다 — 이미 넣은 문서)."""
    P = run.part
    run.guard()
    p = _g_plan(run, gid)
    if not p.get("todo"):
        P["skip"] = True
        return "nothing", "넣을 것이 없습니다(이미 넣었거나 넣을 수 있는 자리가 없음)"
    return "done", f"넣을 내용 {U.nf(p['todo'])}곳"


def _do_g_apply(run, gid, line):
    """[문서 바뀜] 내용 반영(울타리 안에서) — 낡은 계획(409)이면 같은 울타리 안에서 한 번만 다시 계획해 반영 · 표준 검사가 되돌리면(422) · 둘째 낡은 계획이면 전체 멈춤."""
    P, tgt, E = run.part, run.target, run.each
    p = P["plan"] or _g_plan(run, gid)
    if not p.get("todo"):
        return "nothing", ""
    run.guard()
    run.working = {tgt, P["id"]}
    with run.fence(tgt):
        run.guard()
        got = UNIT.gather_apply(tgt, P["id"], p["planId"])
        if got.code == "stale":   # 계획 뒤 문서가 바뀜(고치던 글이 서버에 옴 …) — 한 번만 다시 계획
            p = _g_plan(run, gid)
            got = UNIT.gather_apply(tgt, P["id"], p["planId"]) if p.get("todo") else None
    run.working = set()
    P["plan"] = None
    if got is None or got.code == "nothing":
        return "nothing", "넣을 것이 없습니다(이미 넣었거나 넣을 수 있는 자리가 없음)"
    if got.code == "rejected":
        raise _Halt("rejected", f"「{P['name']}」 — 표준 검사에 걸려 되돌렸습니다: {got.text}")
    if not got.ok:
        raise _Halt(got.code, f"「{P['name']}」 의 내용을 반영하지 못했습니다 — {got.text or '반영 요청이 거절되었습니다'}")
    r = got.data if isinstance(got.data, dict) else {}
    E["done"].append(P["name"])
    for k, n in (r.get("counts") or {}).items():
        if isinstance(n, (int, float)) and not isinstance(n, bool):
            E["sum"][k] = E["sum"].get(k, 0) + n
    E["calc"] += sum(1 for x in r.get("calc") or () if not x or x.get("action") != "recalculated")
    return "done", U.gt_done_text(r)


FAMILY_HANDLERS["gather"] = {"division": _do_g_division, "frame": _do_g_frame, "part": _do_g_part, "heads": _do_g_heads, "link": _do_g_link, "llm": _do_g_llm, "plan": _do_g_plan, "apply": _do_g_apply,
                             "retidy": _do_retidy}   # hand(배포 · 회수) · drop 은 사람이 한다 · retidy = 이관의 처리 함수 그대로(목적 문서(취합본) 하나 · 「내용 넣기」 묶음이 없어 _fill_first 는 안 막는다 — 넣은 기록은 끝점이 gather.json 에서: spec_병합 ② §5-9 9)
MATERIALS.append(_gather_materials)
