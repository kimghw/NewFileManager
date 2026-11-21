"""워크플로우 실행기(spec_워크플로우 ② §18-4 「차례 실행기」 · ② §17-6 · §17-7 — app/workflow_exec.py · app/workflow_exec_api.py):
가짜 문으로 실행의 규칙(시작 → 끝 · 겹침 · 줄 하나 · 멈춤 · 승인 밖 남김 · 건너뜀 · 끊김 · 밀려남 · 대상 바뀜)을, 진짜 서버로 끝점 · 바쁨 막이 · 실행 기록을 본다."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import unit_steps, work_logs, works
from app import workflow_exec as X

Outcome = unit_steps.Outcome


class Fake:
    """가짜 문 — 문서 둘(s 원본 · t 목적)의 재료를 메모리에 두고, 분석 · LLM 은 `job` 을 몇 번 읽으면 끝난다."""

    def __init__(self):
        self.heads = {"s": False, "t": False}      # 헤딩 그래프 · 표 구조가 있나
        self.llm = {"s": False, "t": False}        # LLM 검증·보완을 거쳤나
        self.jobs, self.left = {}, {}              # 문서 → 헤딩 작업 보기 · 끝날 때까지 남은 읽기 수
        self.ok, self.skip, self.calls = True, [], []
        self.fail, self.evict, self.files = set(), set(), {}
        self.logs, self.source = [], {"id": "s", "name": "계획서.hwpx", "format": "hwpx"}
        self.store = self   # unit.store.write …
        self.divs = {}      # 문서 → 프로젝트 구성 재료(div_facts — 2단계 시험이 채운다 · 없으면 None)

    # 읽기
    def pair(self, wid):
        if wid not in ("s", "t"):
            return None
        return {"job": "plan_to_report", "scope": ["시험", "plan_to_report", 1], "file": "report" if wid == "t" else "plan", "kinds": {"target": "report", "source": "plan"},
                "target": {"id": "t", "name": "보고서.hwpx", "format": "hwpx"}, "source": self.source}

    def facts(self, doc):
        return {"id": doc, "name": doc, "rev": 0, "fmt": "hwpx", "heads": {"s2": self.heads[doc], "s3": self.heads[doc], "rev2": 0, "rev3": 0, "llm": self.llm[doc], "job": self.jobs.get(doc)}, "guides": None}

    def llm_ok(self):
        return self.ok

    def div_facts(self, doc):
        d = self.divs.get(doc)
        return dict(d) if d is not None else None

    def fill_facts(self, doc):   # 3 · 4단계 재료(넣기 · 정리 — tests/test_workflow_fill.py 의 가짜 문이 채운다 · 없으면 None)
        return getattr(self, "fills", {}).get(doc)

    def skips(self, wid):
        return list(self.skip)

    # 배경 일
    def _begin(self, doc, kind, polls=2):
        if (self.jobs.get(doc) or {}).get("status") == "running":
            return Outcome("busy", "헤딩 추출이 이미 돌고 있습니다")
        self.calls.append((kind, doc))
        self.jobs[doc] = {"status": "running", "chain": "llm" if kind == "llm" else None, "error": None}
        self.left[doc] = polls
        return Outcome("ok", "", dict(self.jobs[doc]))

    def start_heads(self, doc, how="first"):
        return self._begin(doc, "heads")

    def start_llm(self, doc, skill=None):
        return self._begin(doc, "llm")

    def job(self, doc):
        if doc in self.evict:
            return Outcome("missing", "밀려남")
        j = self.jobs.get(doc)
        if j and j["status"] == "running":
            self.left[doc] -= 1
            if self.left[doc] <= 0:
                bad = doc in self.fail
                j.update(status="failed" if bad else "done", error="까닭" if bad else None)
                if not bad and j["chain"]:
                    self.llm[doc] = not j.get("stopped")
                elif not bad:
                    self.heads[doc] = True
        return Outcome("ok", "", dict(j) if j else None, 0)

    def stop_llm(self, doc):
        self.calls.append(("stop", doc))
        if doc in self.jobs:
            self.jobs[doc]["stopped"] = True
            self.left[doc] = 0
        return Outcome("ok", "", {"stopping": True})

    def guides_keep(self, doc):
        self.calls.append(("guides", doc))
        return Outcome("ok", "", {"saved": {}})

    # 저장(unit.store)
    def write(self, wid, n, record):
        self.files[(wid, n)] = record
        return True

    def read(self, wid, n):
        return self.files.get((wid, n))

    def numbers(self, wid):
        return sorted(n for w, n in self.files if w == wid)

    def log(self, wid, **fields):
        self.logs.append((wid, fields))


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(X, "UNIT", f)
    monkeypatch.setitem(X.WAIT, "poll", 0.005)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
    yield f
    _done("t", 5)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()


def _done(target, seconds=5):
    t0 = time.time()
    while target in X.RUNS and time.time() - t0 < seconds:
        time.sleep(0.005)
    assert target not in X.RUNS, "실행이 끝나지 않았습니다"
    return X.last(target)


def test_review_runs_to_the_end_from_either_document(fake):
    """원본 문서에서 눌러도 목적 문서에서 돈다 — 없는 문서만 분석 → 목적 문서의 작성 지침 → 원본의 LLM 검증·보완."""
    run = X.start("s", {"from": "review"})
    assert run["status"] == "running" and run["docs"]["target"]["id"] == "t" and X.busy_text("s") and X.busy_text("t") and X.busy_text(project="시험") and not X.busy_text("x")
    rec = _done("t")
    assert rec["status"] == "done" and rec["end"]["ok"] and rec["end"]["text"].startswith("끝남 — ")
    assert fake.calls == [("heads", "s"), ("heads", "t"), ("guides", "t"), ("llm", "s")]   # 분석은 같이 걸고 · LLM 은 원본만(붙박이 이관)
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("heads", "done"), ("headsLlm", "done")] and rec["stages"][0]["status"] == "done"
    assert not X.BUSY and not X.busy_text("t") and X.live("t") is None
    assert [f["event"] for w, f in fake.logs if w == "t"] == ["start", "stage", "end"] and [f.get("role") for w, f in fake.logs if w == "s"] == ["source", "source"]
    assert fake.files[("t", 1)]["status"] == "done"
    v = X.status_of("s")
    assert v["run"] is None and v["last"]["n"] == 1 and v["stages"][0]["left"] == 0 and v["stages"][0]["why"] == "남은 단계가 없습니다"
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "review"})
    assert e.value.reason == "noWork"


def test_only_one_run_per_document_and_any_screen_can_stop_it(fake):
    fake.heads.update(s=True, t=True)
    X.WAIT["poll"] = 0.02
    fake._begin = lambda doc, kind, polls=200, _b=fake._begin: _b(doc, kind, polls)   # LLM 이 오래 돈다
    run = X.start("t", {"from": "review", "screen": "a"})
    with pytest.raises(X.Refuse) as e:
        X.start("s", {"from": "review", "screen": "b"})   # 다른 화면 · 다른 칸의 문서 — 같은 실행을 본다
    assert e.value.reason == "busy" and e.value.run["n"] == run["n"]
    t0 = time.time()
    while not any(c == ("llm", "s") for c in fake.calls) and time.time() - t0 < 3:
        time.sleep(0.005)
    assert X.pinned() == {"s"} and X.live("s")["now"]["key"] == "headsLlm" and X.status_of("t")["stages"][0]["can"] is False
    assert X.stop("s", 99) is None and X.stop("s")["stopping"]   # 번호가 다르면 아님 · 어느 문서에서나 멈춤
    rec = _done("t")
    assert rec["status"] == "stopped" and ("stop", "s") in fake.calls and not rec["end"]["ok"] and fake.llm["s"] is False
    assert [f["event"] for w, f in fake.logs if w == "t"][-1] == "stop"


def test_one_line_only_does_not_start_the_paid_line(fake):
    X.start("t", {"from": "review", "only": "heads"})
    rec = _done("t")
    assert rec["status"] == "done" and ("llm", "s") not in fake.calls and [s["key"] for s in rec["steps"]] == ["heads"]
    assert rec["end"]["text"] == "끝남 — 두 문서의 헤딩 그래프·표 구조가 있습니다 — 다음은 「LLM 검증·보완」 입니다"
    with pytest.raises(ValueError):
        X.start("t", {"from": "review", "only": "nope"})
    with pytest.raises(ValueError):
        X.start("t", {"from": "nope"})


def test_agent_run_only_calls_the_approved_documents(fake):
    """에이전트 카드에서 시작한 실행은 승인한 문서에만 유료 호출을 건다 — 밖이면 하지 않고 남긴다(실패도 끝남도 아니다)."""
    fake.heads.update(s=True, t=True)
    X.start("t", {"from": "review", "by": "agent", "paid": []})
    rec = _done("t")
    assert rec["status"] == "left" and rec["end"]["ok"] and rec["end"]["text"].startswith("남김 — ") and "승인한 유료 호출이 아님" in rec["left"][0]["what"] and ("llm", "s") not in fake.calls
    X.start("t", {"from": "review", "by": "agent", "paid": ["s"], "turn": "t1", "key": "k"})
    rec = _done("t")
    assert rec["status"] == "done" and ("llm", "s") in fake.calls and rec["origin"] == {"by": "agent", "where": "", "screen": "", "turn": "t1", "key": "k"} and rec["approval"] == {"paid": ["s"]}


@pytest.mark.parametrize("how", ["off", "skip"])
def test_llm_line_is_skipped_without_a_call(fake, how):
    """LLM 을 쓸 수 없거나 사람이 건너뛴 문서 — 「건너뜀」 으로 지나간다(유료 호출 없음 · 막다른 길 없음)."""
    fake.ok, fake.skip = how != "off", ["s"] if how == "skip" else []
    X.start("t", {"from": "review"})
    rec = _done("t")
    assert rec["status"] == "done" and ("llm", "s") not in fake.calls and rec["steps"][-1]["text"] == f"사업계획서 LLM 검증·보완은 건너뜀({'LLM 을 쓸 수 없음' if how == 'off' else '건너뛰기'})"
    assert rec["end"]["text"] == "끝남 — 두 문서의 헤딩 그래프·표 구조가 있습니다 · " + rec["steps"][-1]["text"] + " — 구성은 2단계 「구성 맞추기」 에서 맞춥니다"   # 끝 글 = 화면 실행의 글 그대로
    assert X.status_of("t")["stages"][0]["steps"][-1]["skipped"] is True


def test_refusals_before_starting(fake):
    fake.source = None
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "review"})
    assert e.value.reason == "notReady" and "사업계획서" in e.value.message
    fake.source = {"id": "s", "name": "계획서.hwpx", "format": "hwpx"}
    for body, reason in (({"from": "review", "docs": {"target": "t", "source": "zz"}}, "docs"),):   # 묶음 넷 모두 서버가 맡는다(걸음 3) — 「화면이 돈다」 는 끄는 스위치 시험이 본다
        with pytest.raises(X.Refuse) as e:
            X.start("t", body)
        assert e.value.reason == reason, body
    with pytest.raises(X.Refuse) as e:
        X.start("nope", {"from": "review"})
    assert e.value.reason == "gone" and not X.RUNS and not X.BUSY


def test_client_switch_turns_every_stage_over_to_the_screen(fake, monkeypatch):
    monkeypatch.setenv("NFM_FLOW_EXEC", "client")
    assert all(g["server"] is False and g["steps"] is None for g in X.status_of("t")["stages"])
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "review"})
    assert e.value.reason == "client"


@pytest.mark.parametrize("case", ["failed", "evicted", "moved"])
def test_halts_with_the_reason(fake, case):
    if case == "failed":
        fake.fail.add("t")
    elif case == "evicted":
        fake.evict.add("s")
    else:
        fake.heads.update(s=True, t=True)
        fake._begin = lambda doc, kind, _b=fake._begin: (fake.__setattr__("source", {"id": "s2", "name": "다른 계획서", "format": "hwpx"}), _b(doc, kind, 3))[1]   # LLM 을 건 뒤 문서 칸이 바뀐다
        fake.heads["s2"], fake.llm["s2"] = True, False
    X.start("t", {"from": "review"})
    rec = _done("t")
    if case == "moved":   # 원본의 LLM 이 끝난 뒤 다음 일을 시작하기 전(대상 고정)에 걸린다 — 한 줄뿐이라 줄은 끝났다
        assert rec["status"] in ("done", "halted")
        return
    assert rec["status"] == "halted" and rec["halt"]["code"] == case and not rec["end"]["ok"] and rec["end"]["text"].startswith("멈춤 — ") and rec["stages"][0]["status"] == "halted"
    assert not X.BUSY and [f["event"] for w, f in fake.logs if w == "t"][-1] == "halt"


def test_pair_changed_before_a_stage_halts(fake):
    fake.heads.update(s=True, t=True)
    run = X.Run({"docs": {"target": {"id": "t"}}, "job": "plan_to_report", "scope": ["시험", "plan_to_report", 1], "stopping": False}, None, {"target": {"id": "t"}, "source": {"id": "other"}}, None)
    with pytest.raises(X._Halt) as e:
        run.guard()
    assert e.value.code == "moved"


def test_a_running_record_of_another_boot_reads_as_cut(fake):
    """서버를 다시 켠 뒤 — `running` 으로 남은 기록은 읽는 때 「끊김」 으로 고쳐 쓴다(저절로 잇지 않는다)."""
    fake.files[("t", 3)] = {"v": 1, "n": 3, "boot": "deadbeef", "status": "running", "now": {"stage": "review", "key": "headsLlm", "note": "계획서 LLM 검증·보완 중"}, "range": {"from": "review", "to": "review"},
                            "docs": {"target": {"id": "t"}, "source": {"id": "s"}}, "stages": [], "steps": [], "left": []}
    rec = X.last("t")
    assert rec["status"] == "cut" and rec["cut"]["at"] == "headsLlm" and rec["end"]["text"].startswith("끊김 — ") and fake.files[("t", 3)]["status"] == "cut"
    assert [f["event"] for w, f in fake.logs] == ["cut"] and X.status_of("t")["last"]["status"] == "cut"
    assert X.start("t", {"from": "review"})["n"] == 4   # 「이어서」 = 새 실행(끝난 단계는 건너뛴다)
    assert _done("t")["status"] == "done" and [x["n"] for x in X.records("t")] == [4, 3]


def test_no_two_starts_win_at_once(fake):
    fake.heads.update(s=True, t=True)
    fake._begin = lambda doc, kind, polls=40, _b=fake._begin: _b(doc, kind, polls)
    got = []

    def go():
        try:
            got.append(X.start("t", {"from": "review"})["n"])
        except X.Refuse as e:
            got.append(e.reason)
    threads = [threading.Thread(target=go) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(map(str, got)) == ["1", "busy", "busy", "busy", "busy", "busy"]
    assert fake.calls.count(("llm", "s")) <= 1
    _done("t")


# ---------------------------------------------------------------- 진짜 서버
@pytest.fixture
def client():
    from app import merge_api, server
    server.DOCS.clear()
    merge_api._CACHE.clear()
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
    X.configure(unit_steps)
    yield TestClient(server.app)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()


def _upload(c, path):
    r = c.post("/api/docs?new=1", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _pair(c):
    plan, report = _upload(c, M.PLAN_FORM), _upload(c, M.REPORT_FORM)
    for d, f in ((plan, "plan"), (report, "report")):
        assert c.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "시험 과제"}).status_code == 200
    return plan, report


def test_flow_endpoints_run_the_script_analysis_on_the_server(client, monkeypatch):
    """끝점으로 — 상태 → 줄 하나(「분석」) 실행 → 창 없이 끝남 → 두 문서에 헤딩 그래프 · 표 구조 · 작성 지침 · 실행 기록 · 로그."""
    monkeypatch.setitem(X.WAIT, "poll", 0.05)
    plan, report = _pair(client)
    assert client.get("/api/works/nope/flow").status_code == 404
    v = client.get(f"/api/works/{plan}/flow").json()
    assert v["job"] == "plan_to_report" and v["ready"] and (v["docs"]["target"]["id"], v["docs"]["source"]["id"]) == (report, plan)
    review = v["stages"][0]
    assert review["server"] and review["can"] and [s["key"] for s in review["steps"]] == ["files", "heads", "headsLlm"] and review["steps"][1]["st"] == "now"
    assert v["stages"][1]["server"] and v["stages"][1]["steps"] is not None   # 2단계 「구성 맞추기」 도 서버가 센다(걸음 2)
    assert all(g["server"] and g["steps"] is not None for g in v["stages"][2:])   # 3단계 「내용 넣기」 · 4단계 「문서 정리」 도 서버가 센다(걸음 3)
    assert [s["key"] for s in v["stages"][2]["steps"]] == ["link", "llm", "plan", "gaps", "tableMap", "apply"] and v["stages"][2]["steps"][0]["st"] == "now" and "먼저 1단계 「문서 검토」 의 헤딩·표 분석" in v["stages"][2]["steps"][0]["text"]
    assert client.post(f"/api/works/{plan}/flow/runs", json={}).status_code == 400
    assert client.post(f"/api/works/{plan}/flow/runs", json={"from": "map", "to": "review"}).status_code == 400   # 뒤 묶음부터 앞 묶음으로는 없다
    r = client.post(f"/api/works/{plan}/flow/runs", json={"from": "review", "only": "heads", "where": "home"})
    assert r.status_code == 202 and r.json()["run"]["n"] == 1
    busy = client.post(f"/api/works/{report}/flow/runs", json={"from": "review"})
    assert busy.status_code == 409 and busy.json()["reason"] == "busy" and busy.json()["run"]["n"] == 1
    assert client.put(f"/api/works/{plan}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "다른"}).status_code == 409   # 바쁨 막이
    assert client.get("/api/flow/active").json()["runs"][0]["n"] == 1
    t0 = time.time()
    while client.get(f"/api/works/{report}/flow/live").json()["run"] and time.time() - t0 < 240:
        time.sleep(0.2)
    rec = client.get(f"/api/works/{plan}/flow/runs/1").json()
    assert rec["status"] == "done", rec
    assert rec["origin"]["where"] == "home" and rec["steps"][0]["key"] == "heads" and rec["steps"][0]["status"] == "done" and "두 문서의 헤딩 그래프·표 구조가 있습니다 · 작성 지침 " in rec["steps"][0]["text"]
    v = client.get(f"/api/works/{report}/flow").json()
    assert v["stages"][0]["steps"][1]["done"] and v["last"]["n"] == 1 and v["run"] is None
    assert unit_steps.facts(report)["guides"] is not None   # 목적 문서의 작성 지침 저장
    assert works.folder(report).joinpath("flowruns", "1.json").is_file() and not works.folder(plan).joinpath("flowruns").exists()
    assert [e["event"] for e in works.events(report) if e.get("kind") == "flowRun"] == ["start", "stage", "end"]
    assert any("실행 1" in line and "상태=done" in line for line in work_logs.read(report, "flows")["lines"])
    assert client.get(f"/api/works/{plan}/flow/runs").json()["runs"][0]["n"] == 1 and client.get(f"/api/works/{plan}/flow/runs/9").status_code == 404
    assert client.post(f"/api/works/{plan}/flow/runs/1/stop").status_code == 409   # 도는 실행이 없음
    # 건너뛰기 — 워크플로우 옵션(모든 화면 · 실행이 같이 본다)
    assert client.put(f"/api/works/{report}/flow/skip", json={"doc": plan}).status_code == 400
    assert client.put(f"/api/works/{report}/flow/skip", json={"doc": plan, "on": True}).json() == {"llmSkip": [plan]}
    line = client.get(f"/api/works/{plan}/flow").json()["stages"][0]["steps"][2]
    assert line["done"] and line["skipped"]
    assert client.put(f"/api/works/{report}/flow/skip", json={"doc": plan, "on": False}).json() == {"llmSkip": []}


def test_busy_documents_refuse_the_changes_that_would_pull_the_rug(client):
    """도는 실행에 든 문서 · 그 프로젝트 — 초기화 · 지우기 · 칸 바꾸기 · 새 라운드 · 묶음 초기화 · 프로젝트 이름 바꾸기 · 지우기가 409."""
    plan, report = _pair(client)
    X.BUSY.update({plan: report, report: report})
    X.RUNS[report] = X.Run({"n": 1, "scope": ["시험 과제", "plan_to_report", 1], "docs": {"target": {"id": report}}, "steps": [], "stages": []}, None, {}, None)
    try:
        calls = [client.post(f"/api/works/{report}/reset"), client.delete(f"/api/works/{plan}"), client.put(f"/api/works/{plan}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": ""}),
                 client.post(f"/api/works/{report}/round", json={}), client.post(f"/api/docs/{report}/merge-links/reset", json={"stage": "frame"}),
                 client.put("/api/projects/시험 과제", json={"name": "새 이름"}), client.delete("/api/projects/시험 과제?docs=keep"), client.put(f"/api/works/{plan}/flow/skip", json={"doc": plan, "on": True})]
        assert [r.status_code for r in calls] == [409] * len(calls), [(r.status_code, r.text[:80]) for r in calls]
        assert all("도는 중" in r.text for r in calls)
    finally:
        X.RUNS.clear(); X.BUSY.clear()
    assert client.put(f"/api/works/{plan}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "시험 과제"}).status_code == 200


# ================================================================ 걸음 2 — 「구성 맞추기」 · 울타리 · 같은 검사(spec_워크플로우 ② §17-8 · §17-10 걸음 2 · §18-4)
V2 = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대"], "nonprofit": [False, False], "outside": [], "overseas": [], "entrust": []}, "subs": [], "current": 1}


class FitFake(Fake):
    """가짜 문 + 프로젝트 구성(두 문서 · 같은 프로젝트의 공유 입력 · 확정) · 구조 반영(계획 → 반영 — 반영하면 목적 문서의 차례가 오른다)."""

    def __init__(self):
        super().__init__()
        self.heads.update(s=True, t=True)
        self.llm.update(s=True)
        self.rev = {"s": 0, "t": 0}
        self.hrev = {"s": 0, "t": 0}                       # 헤딩 분석을 한 때의 문서 차례
        self.asked = {"s": True, "t": False}
        self.readv, self.stops, self.apply_code, self.seen = V2, "", "ok", []
        self.stops_kind, self.already = "issues", True   # 같은 검사의 까닭 종류 · 바꿀 것이 없는 계획이 「이미 맞음」 인가(apply_code "nothing")
        for d in ("s", "t"):
            self.divs[d] = {"input": None, "applied": None, "confirmed": None, "partial": [], "form": "연구개발계획서", "supported": True, "rev": 0, "read": None,
                            "sharing": {"project": "시험", "shared": True}}
        self.divs["s"]["input"] = V2

    def facts(self, doc):
        f = super().facts(doc)
        f["rev"] = self.rev[doc]
        f["heads"].update(rev2=self.hrev[doc], rev3=self.hrev[doc], asked=self.asked[doc])
        return f

    def job(self, doc):
        was = (self.jobs.get(doc) or {}).get("status")
        got = super().job(doc)
        if was == "running" and (self.jobs.get(doc) or {}).get("status") == "done" and not self.jobs[doc]["chain"]:
            self.hrev[doc], self.asked[doc] = self.rev[doc], False   # 스크립트 분석 — 지금 차례의 것
        return got

    def start_heads(self, doc, how="first"):
        self.calls.append(("how", doc, how))
        return self._begin(doc, "heads")

    def config_read(self, doc):
        self.calls.append(("read", doc))
        return Outcome("ok", "", self.readv)

    def config_save(self, doc, values):
        self.calls.append(("save", doc))
        self.divs[doc]["input"] = values
        return Outcome("ok", "", {})

    def config_confirm(self, doc, values=None):
        self.calls.append(("confirm", doc))
        for d in ("s", "t"):   # 공유 중 — 프로젝트의 입력 · 확정
            self.divs[d].update(input=values, confirmed={"values": values, "at": time.time(), "valid": True})
        return Outcome("ok", "", {})

    def division_plan(self, doc, values, skip=()):
        self.calls.append(("plan", doc, tuple(skip)))
        self.seen.append(("plan", X.fence_why(doc), doc in X.FENCE, (X.NOTICE.get(doc) or {}).get("key")))
        out = []
        th = threading.Thread(target=lambda: out.append(X.fence_why(doc)))   # 다른 스레드(사람 편집)에는 울타리
        th.start()
        th.join()
        self.seen.append(("other", out[0]))
        self.divs[doc]["input"] = values
        return Outcome("ok", "", {"planId": "p1", "baseRev": self.rev[doc], "summary": {"groups": 2}, "autoStops": self.stops, "autoStopsKind": self.stops_kind if self.stops else "", "stale": False})

    def division_apply(self, doc, plan_id, expect, adopt=False):
        self.calls.append(("apply", doc, plan_id, expect))
        if self.apply_code == "nothing":   # 바꿀 것이 없는 계획 — adopt 면 「구조가 이미 값에 맞음」 을 반영 기록으로(문서는 그대로)
            fits = bool(adopt and self.already)
            if fits:
                self.divs[doc]["applied"] = {"values": self.divs[doc]["input"], "rev": self.rev[doc], "adopted": True}
            return Outcome("nothing", "할 일이 없습니다", {"nothing": True, "adopted": fits, "summary": {"already": 3 if self.already else 0, "unsupported": 1}, "rev": self.rev[doc]}, self.rev[doc])
        if self.apply_code != "ok":
            return Outcome(self.apply_code, "표준 검사에 걸려 되돌렸습니다" if self.apply_code == "rejected" else "계획이 낡았습니다")
        self.rev[doc] += 1
        self.divs[doc]["applied"] = {"values": self.divs[doc]["input"], "rev": self.rev[doc]}
        return Outcome("ok", "", {"rev": self.rev[doc]}, self.rev[doc])


@pytest.fixture
def fit(monkeypatch):
    f = FitFake()
    monkeypatch.setattr(X, "UNIT", f)
    monkeypatch.setitem(X.WAIT, "poll", 0.005)
    for k, v in (("settle", 0.3), ("limit", 0.8), ("poll", 0.01)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()
    yield f
    _done("t", 5)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()


def test_frame_runs_confirm_fit_reanalysis_and_llm_on_the_server(fit):
    """확정(원본의 값 → 목적 문서에서) → 울타리 안에서 계획 → 같은 검사 → 반영(다시 계획 없이 한 번) → 다시 분석(2 → 3단계) → 작성 지침 → LLM — 끝 글은 화면 실행의 글 그대로."""
    X.start("t", {"from": "frame", "skip": ["k1"]})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    order = [c for c in fit.calls if c[0] in ("confirm", "plan", "apply", "how", "guides", "llm")]
    assert order == [("confirm", "t"), ("plan", "t", ("k1",)), ("apply", "t", "p1", 0), ("how", "t", 2), ("how", "t", 3), ("guides", "t"), ("llm", "t")], order
    assert fit.seen[0][:3] == ("plan", "", True) and fit.seen[0][3].startswith("t:1:") and fit.seen[1] == ("other", X.FENCE_TEXT)   # 실행 스레드는 지나고 다른 스레드(사람 편집)는 409 · 알림이 걸려 있다
    assert not X.FENCE and not X.NOTICE   # 끝나면 내림
    assert [s["key"] for s in rec["steps"]] == ["config", "division", "reheads", "reheadsLlm"] and rec["skip"] == ["k1"]
    assert rec["end"]["text"] == ("끝남 — 구조를 맞췄습니다 — 사업계획서와 같음 · 연차보고서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳 · 연차보고서를 다시 분석했습니다 · 연차보고서 LLM 검증·보완을 거쳤습니다"
                                  " · 내용은 3단계 「내용 넣기」 에서 넣습니다")
    v = X.status_of("t")["stages"][1]
    assert v["server"] and v["left"] == 0 and v["why"] == "남은 단계가 없습니다"


def test_frame_halts_before_changing_the_document_when_a_screen_has_unsent_text(fit):
    """울타리 — 그 문서를 연 화면에 서버에 반영하지 못한 글이 있으면 문서를 바꾸기 전에 멈춘다(계획도 세우지 않음)."""
    X.report("t", "scr-a", 0)   # 알림 전부터 보고하던 화면
    stop = threading.Event()

    def screen():   # 알림을 본 뒤에도 고치던 글이 남는 화면(반영 실패)
        while not stop.is_set():
            X.report("t", "scr-a", 1)
            time.sleep(0.02)
    th = threading.Thread(target=screen, daemon=True)
    th.start()
    try:
        X.start("t", {"from": "frame"})
        rec = _done("t")
    finally:
        stop.set()
        th.join()
    assert rec["status"] == "halted" and rec["halt"]["code"] == "dirty" and rec["end"]["text"] == "멈춤 — " + X.DIRTY_TEXT
    assert not [c for c in fit.calls if c[0] in ("plan", "apply")] and not X.FENCE and not X.NOTICE


def test_fence_waits_for_the_screens_that_were_reporting(fit):
    """알림 전에 보고하던 화면이 알림 뒤에 0 을 보고하면 바로 · 보고가 끊긴 화면은 settle 뒤에(닫힌 화면) · 그동안 멈춤이면 _Stop."""
    run = X.Run({"n": 7, "docs": {"target": {"id": "t"}}, "stopping": False}, None, {}, None)
    X.report("t", "a", 0)

    def screen(acks=True):   # 알림을 받고(입력을 막고 보낸 뒤) 그 key 를 되돌려 0 을 보고하는 화면 — 받기 전에 잰 0 은 받았음이 아니다
        t0 = time.time()
        while "t" not in X.NOTICE and time.time() - t0 < 2:
            time.sleep(0.005)
        X.report("t", "a", 0)   # 알림을 아직 못 본 보고(ack 없음) — 받았음으로 세지 않는다
        time.sleep(0.05)
        if acks:
            X.report("t", "a", 0, X.NOTICE["t"]["key"])
    threading.Thread(target=screen).start()
    t0 = time.time()
    with run.fence("t"):
        assert X.notice_of("t")["fenced"] and X.notice_of("t")["key"].startswith("t:7:")
    assert time.time() - t0 < X.FENCE_WAIT["settle"] and X.notice_of("t") is None and X.fence_why("t") == ""
    X.report("t", "a", 0)
    threading.Thread(target=lambda: screen(acks=False)).start()   # 알림 뒤에 보고는 하는데 받았음을 안 보내는 화면 — settle 이 지나도 기다리다 멈춘다(입력을 아직 못 막은 화면)
    with pytest.raises(X._Halt) as e:
        with run.fence("t"):
            pass
    assert e.value.code == "dirty"
    X.REPORTS.clear()
    X.report("t", "gone", 0)
    t0 = time.time()
    with run.fence("t"):
        pass
    assert time.time() - t0 >= X.FENCE_WAIT["settle"] - 0.05
    run.rec["stopping"] = True
    with pytest.raises(X._Stop):
        with run.fence("t"):
            pass
    assert not X.FENCE and not X.NOTICE


@pytest.mark.parametrize("case", ["stops", "rejected", "stale"])
def test_frame_halts_on_the_same_check_and_on_a_failed_apply_without_replanning(fit, case):
    """같은 검사(autoStops)에 걸리면 반영하지 않고 멈춤 · 반영이 409 · 422 면 다시 계획하지 않고 멈춤(② §18-4 「다시 계획 없이 한 번」)."""
    if case == "stops":
        fit.stops = "미해결 2곳"
    else:
        fit.apply_code = case
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and len([c for c in fit.calls if c[0] == "plan"]) == 1, rec["end"]
    if case == "stops":
        assert rec["halt"]["code"] == "stops" and not [c for c in fit.calls if c[0] == "apply"]
        assert rec["end"]["text"] == "멈춤 — 미해결 2곳 — 저절로 반영하지 않습니다. 2단계 「구성 맞추기」 의 변경 계획 목록에서 확인한 뒤 「② 반영」 을 누르세요"
    else:
        assert rec["halt"]["code"] == case and rec["end"]["text"].startswith("멈춤 — 프로젝트 구성이 반영되지 않았습니다 — ")
    assert not X.FENCE and not X.NOTICE and fit.rev["t"] == 0


def test_frame_reads_the_values_from_the_document_when_none_are_saved(fit):
    fit.divs["s"]["input"] = None
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "done" and ("read", "s") in fit.calls and fit.calls.index(("read", "s")) < fit.calls.index(("confirm", "t"))
    for d in ("s", "t"):
        fit.divs[d].update(input=None, applied=None, confirmed=None)
    fit.readv = None
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "noValues" and "사업계획서에서 단계·차년도·기관을 읽지 못했습니다" in rec["end"]["text"]


def test_reheads_button_only_does_the_script_line_and_keeps_an_llm_result_when_llm_is_off(fit):
    """「다시 분석」 단추(only reheads) — 그 줄만(뒤의 LLM 을 시작하지 않음) · 앞 묶음이 덜 끝나도(줄의 단추) · LLM 을 못 쓰면 반영 전 LLM 결과를 그대로 둔다(redo 면 그래도 다시)."""
    fit.llm["s"] = False   # 1단계가 덜 끝남(원본의 LLM)
    for d in ("s", "t"):
        fit.divs[d].update(input=V2, confirmed={"values": V2, "at": 1}, applied={"values": V2, "rev": 2})
    fit.rev["t"], fit.hrev["t"], fit.asked["t"], fit.ok = 2, 1, True, False
    X.start("t", {"from": "frame", "only": "reheads"})
    rec = _done("t")
    assert rec["status"] == "done" and not [c for c in fit.calls if c[0] == "how"]
    assert rec["end"]["text"] == ("끝남 — 구조를 맞춘 문서의 헤딩·표 — 연차보고서의 분석은 구조 반영 전 것(LLM 결과 — LLM 을 쓸 수 없어 그대로 둠 · 늘어난 절·표는 못 이을 수 있음: 「다시 분석」)"
                                  " — 다음은 「다시 문서 검토(LLM)」 입니다")
    X.start("t", {"from": "frame", "only": "reheads", "redo": "reheads"})
    rec = _done("t")
    assert rec["status"] == "done" and [c for c in fit.calls if c[0] == "how"] == [("how", "t", 2), ("how", "t", 3)] and ("llm", "t") not in fit.calls
    assert rec["end"]["text"] == "끝남 — 구조를 맞춘 문서의 헤딩·표 — 연차보고서를 다시 분석했습니다 — 다음은 「다시 문서 검토(LLM)」 입니다"


def test_frame_agent_run_leaves_the_unapproved_llm(fit):
    X.start("t", {"from": "frame", "by": "agent", "paid": []})
    rec = _done("t")
    assert rec["status"] == "left" and ("llm", "t") not in fit.calls and "연차보고서 LLM 검증·보완은 하지 않음(실행 카드에서 승인한 유료 호출이 아님 — 남은 단계)" in rec["end"]["text"]


def test_every_edit_entry_that_bumps_checks_the_fence():
    """`_bump` 를 부르는 함수마다 울타리 검사(`_fenced`)가 있다 — 새 편집 길이 빠지지 않게(② §17-8 「편집 입구」)."""
    import ast
    from pathlib import Path
    app_dir, found = Path(X.__file__).parent, []
    for path in sorted(app_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            names = {(c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")) for c in ast.walk(fn) if isinstance(c, ast.Call)}
            if "_bump" in names and fn.name != "_bump":
                found.append(f"{path.name}:{fn.name}")
                assert "_fenced" in names, f"{path.name}:{fn.name} 가 _bump 를 부르는데 울타리 검사(_fenced)가 없습니다"
    assert {"server.py:_patch", "server.py:_transact", "server.py:undo", "server.py:revert_block", "server.py:commit_restore", "outline_format_api.py:align_edited"} <= set(found), found


def test_the_fence_refuses_human_edits_on_the_real_server(client):
    """진짜 서버 — 울타리 동안 사람 편집(글 · 실행 취소)은 409 · 확인 폴링은 고치던 글을 보고하고 알림을 받는다 · 같은 검사는 계획의 응답에 실린다."""
    plan, report = _pair(client)
    doc = client.get(f"/api/docs/{report}").json()
    para = next(b for b in doc["blocks"] if b.get("type") == "paragraph" and b.get("text"))
    X.NOTICE[report] = {"key": f"{report}:1", "since": time.time()}
    X.FENCE[report] = {"target": report, "n": 1, "thread": -1}
    try:
        r = client.patch(f"/api/docs/{report}/blocks/{para['id']}", json={"text": para["text"] + "x"})
        assert r.status_code == 409 and r.json()["detail"] == X.FENCE_TEXT
        assert client.post(f"/api/docs/{report}/undo").status_code == 409
        live = client.get(f"/api/works/{report}/flow/live", params={"screen": "scr1", "dirty": 2, "ack": f"{report}:1"}).json()
        assert live["notice"]["fenced"] and live["notice"]["key"] == f"{report}:1" and X.REPORTS[report]["scr1"][0] == 2 and X.REPORTS[report]["scr1"][3] == f"{report}:1"
        assert client.post(f"/api/docs/{report}/divisions/plan", json={"values": M.SMALL_VALUES}).status_code == 409   # 사람의 계획은 실행의 계획 자리를 밀어내지 않게 — 409
        assert "rev" in live and "lastRun" in live
        for path in ("divisions/settings", "divisions/hints"):
            assert (client.put if path.endswith("settings") else client.post)(f"/api/docs/{report}/{path}", json={"values": M.SMALL_VALUES} if path.endswith("settings") else {"para": para["id"], "dim": "org"}).status_code == 409
    finally:
        X.FENCE.clear()
        X.NOTICE.clear()
        X.REPORTS.clear()
    assert client.get(f"/api/works/{report}/flow/live").json()["notice"] is None
    assert client.patch(f"/api/docs/{report}/blocks/{para['id']}", json={"text": para["text"] + "x"}).status_code == 200
    got = client.post(f"/api/docs/{report}/divisions/plan", json={"values": M.SMALL_VALUES}).json()
    assert isinstance(got["autoStops"], str) and got["autoStopsKind"] in ("", "issues", "orgs")


# ---- astra 결과 검토(2026-11-20 — artifacts/flow_step2_astra_2026-11-20/answer.md)로 더한 것
def test_frame_never_changes_the_document_with_values_other_than_the_confirmed_ones(fit):
    """원본의 반영 값(기준 — 반영 값이 먼저)이 확정과 다르면 계획(입력 값 저장)도 반영도 하지 않고 멈춘다(P1 — 전에는 반영한 뒤 멈췄다)."""
    v1 = {**V2, "stages": [1]}
    fit.divs["s"].update(input=V2, applied={"values": v1, "rev": 1})
    fit.divs["t"].update(input=V2, confirmed={"values": V2, "at": 1})
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "unconfirmed" and "확정한 프로젝트 구성과 다릅니다" in rec["end"]["text"]
    assert not [c for c in fit.calls if c[0] in ("plan", "apply")] and fit.rev["t"] == 0 and fit.divs["t"]["input"] == V2


def test_frame_refuses_a_cut_exclusion_list(fit):
    """「반영에서 빼기」 목록을 자르지 않는다 — 너무 길면 시작을 거절(잘라 쓰면 사람이 뺀 자리가 반영된다 · astra P1)."""
    with pytest.raises(ValueError):
        X.start("t", {"from": "frame", "skip": ["k"] * (X.SKIP_MAX + 1)})
    with pytest.raises(ValueError):
        X.start("t", {"from": "frame", "skip": "k1"})


def test_same_check_does_not_flag_a_duplicate_name_that_kept_its_place():
    """같은 이름이 둘 — 자리가 그대로면 기관 차례가 바뀐 것이 아니다(astra P2 · 화면 divOrgsMoved 도 같게 고침)."""
    from app import division_plan as P
    v = {"orgs": {"lead": "A", "joint": ["B", "B"]}}
    assert P.orgs_moved(v, {"values": v}, []) == ""
    assert P.orgs_moved({"orgs": {"lead": "A", "joint": ["C", "B"]}}, {"values": {"orgs": {"lead": "A", "joint": ["B", "C"]}}}, []).startswith("기관 「B」 의 차례가 마지막 반영과 다릅니다(공동 1 → 공동 2)")
    assert P.auto_stops({"groups": 0, "changes": 0, "unresolved": 3}, v, None, []) == ("", "")   # 바꿀 것이 없는 계획은 멈추지 않는다
    assert P.auto_stops({"groups": 1, "unresolved": 3, "errors": 1}, v, None, []) == ("계획 오류 1건 · 미해결 3곳", "issues")


def test_only_the_relay_pair_workflows_are_served():
    """단계 key 가 워크플로우마다 겹친다 — 취합 · 양식 맞추기의 config · plan · apply 를 이관의 처리 함수로 돌리지 않는다(틀이 닫힌 워크플로우는 서버가 맡지 않고, 연 틀은 제 가족의 처리 함수로)."""
    from app import workflow_state as S
    from app import workflow_units as U
    for job in ("report_fit", "plan_fit", "doc_edit", "style_copy"):
        task = S.definition(job)
        assert not S.relay_pair(task) and not any(S.served(task, g["id"]) for g in task["stages"]), job
    task = S.definition("plan_to_report")
    assert S.relay_pair(task) and S.served(task, "review") and S.served(task, "frame")
    gather = S.definition("plan_merge")   # 취합 — 2026-11-20 틀을 엶: 이관의 것이 아니라 취합 가족의 단위 · 처리 함수로
    assert not S.relay_pair(gather) and S.served(gather, "map") and all(X._handler(gather, x) is not X._do_apply for x in S.lines(gather) if x["key"] == "apply")
    assert next(x["unit"] for x in S.lines(gather) if x["key"] == "plan") is U.GATHER["plan"]


# ---- 사람이 하는 일(hand1 …) — 「했음」 이 없으면 멈추고 있으면 지나간다(② §18-12 ⑦ · 갈래 C 의 확인 기록 문 hand_ver · hand_done)
def test_hand_lines_halt_until_a_person_marks_them_done(fit, monkeypatch):
    import copy
    from app import workflow_state as S
    from app import workflow_units as U
    base = S.definition("plan_to_report")
    task = copy.deepcopy(base)
    review = task["stages"][0]
    review["steps"] = [*review["steps"], {**review["steps"][-1], "key": "hand1", "name": "결과 확인", "does": "두 문서의 분석을 사람이 훑어봅니다", "by": ["human"], "optional": False, "soon": False, "on": "target", "change": "none"}]
    monkeypatch.setattr(S, "definition", lambda job: task if job == "plan_to_report" else None)
    marks = {}
    fit.hand_ver = lambda t, key: f"v-{key}"
    fit.hand_done = lambda target, key, ver: marks.get((target, key)) == ver
    assert U.hand_key("hand1") and U.unit("hand1")["kind"] == "hand" and not U.hand_key("handy") and S.served(task, "review")
    v = X.status_of("t")["stages"][0]
    line = next(s for s in v["steps"] if s["key"] == "hand1")
    assert line["st"] == "now" and not line["done"] and "사람이 할 일" in line["text"] and v["left"] == 1
    X.start("t", {"from": "review", "redo": "review"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "hand" and rec["halt"]["key"] == "hand1"
    assert rec["end"]["text"] == "멈춤 — 사람이 할 일 — 결과 확인: 두 문서의 분석을 사람이 훑어봅니다 · 마친 뒤 그 줄의 「했음」 을 누르고 「이어서」"
    marks[("t", "hand1")] = "v-hand1"
    v = X.status_of("t")["stages"][0]
    assert next(s for s in v["steps"] if s["key"] == "hand1")["done"] and v["left"] == 0
    X.start("t", {"from": "review", "redo": "review"})
    rec = _done("t")
    assert rec["status"] == "done" and "결과 확인 — 사람이 확인함" in rec["end"]["text"]


# ---- 원본 문서에 놓는 줄(② §18-2 「원본 문서에 놓는 줄」 — 2026-11-20 사용자 「원본 문서는 왜 네 맘대로 빼냐? 목적문서랑 원본 문서도 분리해서 따로 따로 하게 … 동일하게 같이 작업」)
def _fit_on(monkeypatch, **on):
    """붙박이 이관의 「구성 맞추기」 줄의 하는 문서를 바꾼 정의(조립한 정의가 그 줄을 원본 문서에도 놓은 꼴) — on = {줄 key: source | target | both}."""
    import copy
    from app import workflow_state as S
    task = copy.deepcopy(S.definition("plan_to_report"))
    frame = next(g for g in task["stages"] if g["id"] == "frame")
    frame["steps"] = [{**s, "on": on.get(s["key"], s["on"])} for s in frame["steps"]]
    monkeypatch.setattr(S, "definition", lambda job: task if job == "plan_to_report" else None)
    return task


def test_fit_lines_run_on_the_source_document_too_when_placed_together(fit, monkeypatch):
    """같이(한 줄이 두 문서) — 원본 → 목적 차례: 원본 문서는 제 값을 제 구조에(구조 확인 → 계획 → 반영 — 목적 문서 화면의 「반영에서 빼기」 는 넘기지 않는다) · 목적 문서는 그 구조를 기준으로 ·
    다시 문서 검토 · LLM 도 문서마다(작성 지침 저장은 목적 문서만). 끝 글은 문서마다의 글을 차례로."""
    _fit_on(monkeypatch, division="both", reheads="both", reheadsLlm="both")
    heads0 = fit.start_heads
    fit.start_heads = lambda doc, how="first": (fit.llm.__setitem__(doc, False), heads0(doc, how))[1]   # 스크립트로 다시 분석하면 LLM 을 거친 결과가 아니다(실제 문서처럼)
    fit.division_adopt = lambda doc, values=None: fit.calls.append(("adopt", doc)) or Outcome("ok", "", {"adopted": False})
    v = X.status_of("t")["stages"][1]
    assert v["server"] and [s["on"] for s in v["steps"] if s["key"] in ("division", "reheads", "reheadsLlm")] == ["both"] * 3 and sorted(v["paid"]) == ["s", "t"]
    X.start("t", {"from": "frame", "skip": ["k1"]})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    order = [c for c in fit.calls if c[0] in ("confirm", "adopt", "plan", "apply", "how", "guides", "llm")]
    # 구조 반영은 차례로(원본 → 목적 — 목적 문서가 원본의 구조를 기준으로 맞춘다) · 다시 문서 검토 · LLM 은 두 문서를 함께(2026-11-20 「병렬로 처리」 — 문서마다의 차례는 그대로 · 두 문서 사이의 차례는 정해져 있지 않다)
    assert order[:6] == [("confirm", "t"), ("adopt", "s"), ("plan", "s", ()), ("apply", "s", "p1", 0), ("plan", "t", ("k1",)), ("apply", "t", "p1", 0)], order
    assert sorted(order[6:11]) == sorted([("how", "s", 2), ("how", "s", 3), ("how", "t", 2), ("how", "t", 3), ("guides", "t")]) and sorted(order[11:]) == [("llm", "s"), ("llm", "t")], order
    assert [c for c in order if c[0] == "how" and c[1] == "s"] == [("how", "s", 2), ("how", "s", 3)] and [c for c in order if c[1] == "t" and c[0] in ("how", "guides")] == [("how", "t", 2), ("how", "t", 3), ("guides", "t")], order
    assert rec["end"]["text"] == ("끝남 — 구조를 맞췄습니다 — 사업계획서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳 · 사업계획서와 같음 · 연차보고서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳"
                                  " · 사업계획서를 다시 분석했습니다 · 연차보고서를 다시 분석했습니다 · 사업계획서 LLM 검증·보완을 거쳤습니다 · 연차보고서 LLM 검증·보완을 거쳤습니다"
                                  " · 내용은 3단계 「내용 넣기」 에서 넣습니다")
    v = X.status_of("t")["stages"][1]
    line = next(s for s in v["steps"] if s["key"] == "division")
    assert v["left"] == 0 and line["done"] and [(p["doc"], p["role"], p["st"]) for p in line["per"]] == [("s", "source", "done"), ("t", "target", "done")]
    assert not X.FENCE and not X.NOTICE


def test_a_source_document_that_already_fits_is_confirmed_without_a_change(fit, monkeypatch):
    """한 번도 반영한 적 없는 원본 문서의 구조가 이미 값에 맞으면 확인만(문서 안 바뀜 — 계획 · 반영을 부르지 않는다). 원본 문서만 고른 줄은 목적 문서를 건드리지 않는다(따로)."""
    _fit_on(monkeypatch, division="source", reheads="source", reheadsLlm="source")

    def adopt(doc, values=None):
        fit.calls.append(("adopt", doc))
        fit.divs[doc]["applied"] = {"values": fit.divs[doc]["input"], "rev": fit.rev[doc], "adopted": True}
        return Outcome("ok", "", {"adopted": True})
    fit.division_adopt = adopt
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    assert [c for c in fit.calls if c[0] in ("confirm", "adopt", "plan", "apply", "how", "guides", "llm")] == [("confirm", "t"), ("adopt", "s")]   # 구조가 안 바뀌었으니 분석도 그대로(원본의 LLM 은 이미 거침)
    assert rec["end"]["text"].startswith("끝남 — 구조를 맞췄습니다 — 사업계획서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳(구조가 이미 값에 맞음 — 확인함)")
    assert fit.divs["t"]["applied"] is None and fit.rev == {"s": 0, "t": 0}


def test_the_target_document_may_be_fitted_before_the_source_document(fit, monkeypatch):
    """문서끼리의 차례는 자유(사용자 「프로젝트 구성을 완료하고 문서 검토하고 다른문서 프로젝트 구성할 수도 있잖아」) — 목적 문서의 구성 반영 · 다시 문서 검토를 끝낸 뒤 원본 문서의 구성 반영.
    원본 문서도 구조 반영하는 정의에서는 목적 문서가 원본의 **제 값**(입력)에 맞춘다 — 원본의 옛 구조(반영 값)에 맞추지 않는다(workflow_units.basis_of)."""
    import copy
    from app import workflow_state as S
    task = copy.deepcopy(S.definition("plan_to_report"))
    frame = next(g for g in task["stages"] if g["id"] == "frame")
    div = next(s for s in frame["steps"] if s["key"] == "division")
    frame["steps"] = [*frame["steps"], {**div, "on": "source"}]   # 구성 불러오기 · 확정 · 구성 반영(목적) · 다시 문서 검토(목적) · LLM(목적) → 구성 반영(원본)
    monkeypatch.setattr(S, "definition", lambda job: task if job == "plan_to_report" else None)
    old = {**V2, "stages": [3]}
    fit.divs["s"]["applied"] = {"values": old, "rev": 0}   # 원본 문서의 지금 구조는 옛 값 — 입력(확정할 값)은 V2
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    order = [c for c in fit.calls if c[0] in ("confirm", "plan", "apply", "how", "guides", "llm")]
    assert order == [("confirm", "t"), ("plan", "t", ()), ("apply", "t", "p1", 0), ("how", "t", 2), ("how", "t", 3), ("guides", "t"), ("llm", "t"), ("plan", "s", ()), ("apply", "s", "p1", 0)], order
    assert fit.divs["t"]["applied"]["values"] == V2 and fit.divs["s"]["applied"]["values"] == V2   # 두 문서가 같은 확정 값으로(목적 문서가 원본의 옛 구조 [3] 에 맞춰지지 않았다)
    assert [s["key"] for s in rec["steps"]] == ["config", "division", "reheads", "reheadsLlm", "division"]
    assert "사업계획서와 같음 · 연차보고서에 반영됨" in rec["end"]["text"] and "사업계획서에 반영됨" in rec["end"]["text"]
    v = X.status_of("t")["stages"][1]
    assert v["left"] == 0 and [(s["key"], s["on"], s["done"]) for s in v["steps"] if s["key"] == "division"] == [("division", "target", True), ("division", "source", True)]


def test_the_source_document_is_not_changed_with_values_other_than_the_confirmed_ones(fit, monkeypatch):
    """원본 문서의 값이 확정한 프로젝트 구성과 다르면 그 문서를 바꾸지 않고 멈춘다(계획도 세우지 않는다)."""
    _fit_on(monkeypatch, division="both")
    fit.division_adopt = lambda doc, values=None: Outcome("ok", "", {"adopted": False})
    other = {**V2, "stages": [3]}
    fit.config_confirm = lambda doc, values=None: (fit.divs["t"].update(input=values, confirmed={"values": values, "at": time.time(), "valid": True}), Outcome("ok", "", {}))[1]   # 공유하지 않는 두 문서 — 확정은 목적 문서에만
    fit.divs["t"].update(input=other, confirmed={"values": other, "at": time.time(), "valid": True})
    X.start("t", {"from": "frame"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "unconfirmed" and "사업계획서의 값(1단계 · 전체 2년 · 기관 2곳)이 확정한 프로젝트 구성과 다릅니다" in rec["end"]["text"]
    assert not [c for c in fit.calls if c[0] in ("plan", "apply")]


# ---- 같은 차례(한 행)의 두 문서 일은 함께 돈다(② §18-4 「같은 차례 — 함께 돌기」 — 2026-11-20 사용자 「이런 경우 병렬로 처리 하도록 해줘」: 전에는 원본 문서의 것 다음에 목적 문서의 것)
def _review_as(monkeypatch, steps):
    """붙박이 이관의 「문서 검토」 줄을 바꾼 정의 — steps = [(줄 key, 하는 문서, 앞 줄과 같은 차례인가)](조립한 정의가 그렇게 놓은 꼴)."""
    import copy
    from app import workflow_state as S
    task = copy.deepcopy(S.definition("plan_to_report"))
    review = task["stages"][0]
    by = {s["key"]: s for s in review["steps"]}
    review["steps"] = [by["files"], *[{**by[k], "on": on, **({"beside": True} if beside else {})} for k, on, beside in steps]]
    monkeypatch.setattr(S, "definition", lambda job: task if job == "plan_to_report" else None)
    return task


def test_lines_of_one_turn_on_two_documents_run_together(fake, monkeypatch):
    """원본 문서의 「LLM 검증·보완」 과 목적 문서의 「헤딩 · 표 분석」 을 같은 차례에 — 함께 돈다: 목적 문서의 분석은 원본 문서의 LLM 이 걸린 뒤에야 시작하게 막아 두어도 끝난다(차례로 돌면 못 끝난다).
    줄마다의 기록 · 끝 글은 그대로이고, 일하는 문서는 스레드마다 따로 센다."""
    _review_as(monkeypatch, [("headsLlm", "source", False), ("heads", "target", True)])
    fake.heads["s"] = True
    seen, met, working = threading.Event(), [], []
    heads0, llm0 = fake.start_heads, fake.start_llm
    fake.start_llm = lambda doc, skill=None: (seen.set(), llm0(doc, skill))[1]
    fake.start_heads = lambda doc, how="first": (met.append(seen.wait(2)), working.append(set(X.pinned())), heads0(doc, how))[2]   # 원본의 LLM 이 걸릴 때까지 기다린다 — 함께 돌 때만 온다
    X.start("t", {"from": "review"})
    rec = _done("t")
    assert rec["status"] == "done" and met == [True], (rec["end"], met)
    assert sorted(c for c in fake.calls if c[0] in ("llm", "heads")) == [("heads", "t"), ("llm", "s")] and ("guides", "t") in fake.calls
    assert sorted((s["key"], s["status"]) for s in rec["steps"]) == [("heads", "done"), ("headsLlm", "done")]
    assert "사업계획서 LLM 검증·보완을 거쳤습니다" in rec["end"]["text"] and "연차보고서의 헤딩 그래프·표 구조가 있습니다" in rec["end"]["text"]
    assert not X.pinned() and not X.BUSY   # 끝나면 일하는 문서가 남지 않는다


def test_one_line_on_two_documents_calls_the_llm_together(fake, monkeypatch):
    """한 줄이 두 문서를 하는 「LLM 검증·보완」 — 두 문서의 유료 호출을 함께 건다(원본의 것이 끝나기를 기다리지 않는다) · 글은 원본 → 목적 차례."""
    _review_as(monkeypatch, [("heads", "both", False), ("headsLlm", "both", False)])
    fake.heads.update(s=True, t=True)
    seen, met = threading.Event(), []
    llm0 = fake.start_llm
    fake.start_llm = lambda doc, skill=None: (met.append(seen.wait(2)) if doc == "s" else seen.set(), llm0(doc, skill))[1]   # 원본의 호출은 목적 문서의 호출이 걸릴 때까지 기다린다
    X.start("t", {"from": "review"})
    rec = _done("t")
    assert rec["status"] == "done" and met == [True] and sorted(c for c in fake.calls if c[0] == "llm") == [("llm", "s"), ("llm", "t")], (rec["end"], met)
    assert rec["steps"][-1]["text"] == "사업계획서 LLM 검증·보완을 거쳤습니다 · 연차보고서 LLM 검증·보완을 거쳤습니다"


def test_two_hand_lines_of_one_turn_halt_once_with_both(fit, monkeypatch):
    """사람이 하는 일 둘을 같은 차례에 — 한 번 멈추고 두 일을 함께 알린다(전에는 하나씩 두 번) · 멈춘 줄 = 앞의 것 · 둘 다 「했음」 이면 지나간다."""
    task = _review_as(monkeypatch, [("heads", "both", False)])
    last = task["stages"][0]["steps"][-1]
    hand = lambda key, name, on, beside: {**last, "key": key, "name": name, "does": f"{name}을 봅니다", "by": ["human"], "optional": False, "soon": False, "on": on, "change": "none", **({"beside": True} if beside else {})}  # noqa: E731
    task["stages"][0]["steps"] += [hand("hand1", "원본 확인", "source", False), hand("hand2", "목적 확인", "target", True)]
    marks = {}
    fit.hand_ver = lambda t, key: f"v-{key}"
    fit.hand_done = lambda target, key, ver: marks.get((target, key)) == ver
    X.start("t", {"from": "review", "redo": "review"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "hand" and rec["halt"]["key"] == "hand1" and rec["halt"]["stage"] == "review", rec["halt"]
    assert "사람이 할 일 — 원본 확인: 원본 확인을 봅니다" in rec["end"]["text"] and "사람이 할 일 — 목적 확인: 목적 확인을 봅니다" in rec["end"]["text"], rec["end"]["text"]
    marks[("t", "hand1")] = "v-hand1"   # 하나만 「했음」 — 남은 하나에서 멈춘다(지난 것은 기록에)
    X.start("t", {"from": "review", "redo": "review"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["key"] == "hand2" and "원본 확인" not in rec["end"]["text"] and ("hand1", "nothing") in [(s["key"], s["status"]) for s in rec["steps"]]
    marks[("t", "hand2")] = "v-hand2"
    X.start("t", {"from": "review", "redo": "review"})
    assert _done("t")["status"] == "done"


def test_lines_that_touch_each_others_document_keep_their_turn():
    """함께 도는 조건 — 앞 줄과 같은 차례(beside)이고 · 문서가 서로 다른 문서 하나의 줄이며 · 한쪽이 **바꾸는** 문서를 다른 쪽이 읽지 않을 때. 아니면 전처럼 차례로."""
    from app import workflow_state as S
    from app import workflow_units as U
    task = S.definition("plan_to_report")
    line = lambda key, on, beside=False: {"key": key, "on": on, "unit": U.unit(key, "relay"), "beside": beside}  # noqa: E731
    ok = lambda a, b: X._together(task, a, b)  # noqa: E731
    assert ok(line("heads", "source"), line("headsLlm", "target", True)) and ok(line("headsLlm", "source"), line("guide", "target", True)) and ok(line("hand1", "source"), line("hand2", "target", True))
    assert ok(line("heads", "source"), line("division", "target", True))            # 구조 반영(목적) ∥ 분석(원본) — 원본 문서는 안 바뀐다
    assert ok(line("reheads", "source"), line("reheadsLlm", "target", True))        # 다시 문서 검토끼리 — 문서를 바꾸지 않는다
    assert not ok(line("heads", "source"), line("headsLlm", "target"))              # 같은 차례가 아니다
    assert not ok(line("guide", "source"), line("division", "target", True))        # 원본을 바꾸는 줄 ∥ 원본을 기준으로 보는 줄 — 차례로
    assert not ok(line("division", "source"), line("reheads", "target", True)) and not ok(line("reheads", "source"), line("division", "target", True))
    assert not ok(line("heads", "target"), line("headsLlm", "target", True))        # 같은 문서
    assert not ok(line("heads", "both"), line("headsLlm", "target", True)) and not ok(line("link", "pair"), line("hand1", "target", True)) and not ok(line("config", "flow"), line("heads", "source", True))


def test_a_line_button_runs_that_line_only_unless_the_whole_turn_is_asked(fake, monkeypatch):
    """줄 하나만(only) — 같은 차례에 선 옆 줄은 돌지 않는다(유료 줄이 따라 시작하지 않게) · row 를 함께 주면 그 차례(행)째 돈다. 상태 · 목록에는 같은 차례 표시(beside)가 실린다."""
    _review_as(monkeypatch, [("headsLlm", "source", False), ("heads", "target", True)])
    fake.heads["s"] = True
    v = X.status_of("t")["stages"][0]
    assert [bool(s.get("beside")) for s in v["steps"] if s["key"] != "files"] == [False, True]
    X.start("t", {"from": "review", "only": "heads"})
    rec = _done("t")
    assert rec["status"] == "done" and ("llm", "s") not in fake.calls and [s["key"] for s in rec["steps"]] == ["heads"] and "row" not in rec["range"]
    fake.heads["t"] = False
    X.start("t", {"from": "review", "only": "heads", "row": True})
    rec = _done("t")
    assert rec["status"] == "done" and ("llm", "s") in fake.calls and sorted(s["key"] for s in rec["steps"]) == ["heads", "headsLlm"] and rec["range"]["row"] is True


def test_one_document_only_runs_that_documents_lines_of_the_stage(fake, monkeypatch):
    """한 문서만 진행(spec_워크플로우 ② §18-21 — 2026-11-21 사용자 "목적문서 따로 원본 문서 작업 따로 할 수 있는 것들은 단계 에서 한 번에 진행할때 각각 따로 진행할 수 있도록 … 하나의 문서만 작업"):
    묶음의 실행에 role 을 주면 그 문서의 줄만 · 줄의 문서도 그 문서 하나로 돈다 — 다른 문서의 분석 · 유료 호출은 시작하지 않는다. 상태는 묶음마다 그 문서만의 몫(solo)을 싣는다."""
    _review_as(monkeypatch, [("heads", "both", False), ("headsLlm", "both", False)])
    g = X.status_of("t")["stages"][0]
    assert [(x["role"], x["title"], x["name"], x["total"], x["left"], x["can"]) for x in g["solo"]] == [("source", "원본 문서", "사업계획서", 2, 2, True), ("target", "목적 문서", "연차보고서", 2, 2, True)]
    assert g["leftBy"] == {"source": 2, "target": 2} and g["left"] == 2 and [x["paid"] for x in g["solo"]] == [["s"], ["t"]]   # 유료로 부를 문서도 그 문서만
    run = X.start("t", {"from": "review", "role": "source"})
    assert run["range"]["role"] == "source"
    rec = _done("t")
    assert rec["status"] == "done" and fake.calls == [("heads", "s"), ("llm", "s")], fake.calls   # 목적 문서는 건드리지 않는다(분석 · 작성 지침 · LLM 모두)
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("heads", "done"), ("headsLlm", "done")]
    assert rec["end"]["text"] == "끝남 — 원본 문서(사업계획서)만 — 사업계획서의 헤딩 그래프·표 구조가 있습니다 · 사업계획서 LLM 검증·보완을 거쳤습니다"   # 다음 묶음을 가리키는 꼬리는 없다(묶음이 끝난 것이 아니다)
    assert [f.get("role") for w, f in fake.logs if w == "t" and f["event"] == "start"] == ["source"]
    g = X.status_of("t")["stages"][0]
    assert [(x["role"], x["left"], x["can"], x["why"]) for x in g["solo"]] == [("source", 0, False, "남은 단계가 없습니다"), ("target", 2, True, "")] and g["left"] == 2 and g["can"]
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "review", "role": "source"})
    assert e.value.reason == "noWork" and e.value.message == "원본 문서(사업계획서)에 남은 단계가 없습니다"
    fake.calls.clear()
    X.start("s", {"from": "review", "role": "target"})   # 어느 문서에서 눌러도 같은 묶음
    rec = _done("t")
    assert rec["status"] == "done" and fake.calls == [("heads", "t"), ("guides", "t"), ("llm", "t")] and rec["end"]["text"].startswith("끝남 — 목적 문서(연차보고서)만 — 연차보고서의 헤딩 그래프·표 구조가 있습니다")
    g = X.status_of("t")["stages"][0]
    assert g["left"] == 0 and [x["left"] for x in g["solo"]] == [0, 0]
    # 줄 하나를 한 문서에만(only + role) · 꼴이 틀린 요청
    fake.heads["t"], fake.llm["t"] = False, False
    fake.calls.clear()
    X.start("t", {"from": "review", "only": "heads", "role": "target"})
    rec = _done("t")
    assert fake.calls == [("heads", "t"), ("guides", "t")] and [s["key"] for s in rec["steps"]] == ["heads"] and rec["range"] == {"from": "review", "to": "review", "only": "heads", "redo": "", "role": "target"}
    for bad in ({"from": "review", "role": "both"}, {"from": "review", "to": "frame", "role": "source"}):
        with pytest.raises(ValueError):
            X.start("t", bad)


def test_one_document_only_is_offered_where_it_differs_from_the_whole_stage(fit, monkeypatch):
    """「한 문서만」 은 묶음 전체와 다를 때만 선다 — 그 문서의 줄 말고도 실행기가 하는 줄(다른 문서의 줄 · 두 문서의 줄 · 워크플로우 전체 줄 · 원본 → 목적 줄)이 있는 묶음. 따로 할 것이 없는 문서 · 묶음은 거절(role).
    붙박이 이관: 1단계 = 분석(두 문서) + LLM(원본) → 원본 · 목적 둘 다 / 2단계 = 구성 추출(전체) + 목적 문서의 줄 → 목적 문서만 / 3단계(원본 → 목적 줄뿐) → 없음."""
    v = {g["id"]: g for g in X.status_of("t")["stages"]}
    assert [x["role"] for x in v["review"]["solo"]] == ["source", "target"] and [x["total"] for x in v["review"]["solo"]] == [2, 1]   # LLM 검증·보완은 원본 문서만의 줄
    assert [(x["role"], x["total"]) for x in v["frame"]["solo"]] == [("target", sum(1 for s in v["frame"]["steps"] if s["on"] == "target" and not s["optional"]))]
    assert v["map"]["solo"] == [] and v["map"]["leftBy"]["source"] == v["map"]["leftBy"]["target"] == v["map"]["left"]   # 원본 → 목적 줄은 어느 문서의 눈으로도 남은 일
    assert v["clean"]["solo"] == []   # 목적 문서의 줄뿐인 묶음 — 묶음 전체와 같다
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "frame", "role": "source"})
    assert e.value.reason == "role" and "원본 문서(사업계획서)만 따로 진행할 단계가 여기에는 없습니다" in e.value.message
    with pytest.raises(X.Refuse) as e:
        X.start("t", {"from": "map", "role": "target"})
    assert e.value.reason == "role"


def test_one_document_only_waits_for_the_earlier_stage_through_that_documents_eyes(fit, monkeypatch):
    """앞 묶음의 남은 일은 그 문서의 눈으로 센다 — 다른 문서만의 줄이 남아 있어도 기다리지 않고(문서마다의 몫은 따로 나아간다), 그 문서의 줄 · 워크플로우 전체 줄 · 원본 → 목적 줄이 남았으면 기다린다."""
    _review_as(monkeypatch, [("heads", "both", False), ("headsLlm", "source", False)])
    fit.heads.update(s=True, t=True)   # 분석은 둘 다 끝 · 원본 문서의 LLM 검증·보완만 남음
    fit.llm["s"] = False
    v = {g["id"]: g for g in X.status_of("t")["stages"]}
    assert v["review"]["left"] == 1 and v["review"]["leftBy"] == {"source": 1, "target": 0}
    assert v["frame"]["can"] is False and v["frame"]["why"] == "1단계 「문서 검토」 이 먼저입니다"   # 묶음 전체는 앞 묶음이 끝나야 한다
    solo = v["frame"]["solo"][0]
    assert solo["role"] == "target" and solo["can"] is True and solo["why"] == ""   # 목적 문서만은 원본 문서만의 줄을 기다리지 않는다
    fit.heads["t"] = False   # 목적 문서의 분석이 남으면 기다린다
    solo = {g["id"]: g for g in X.status_of("t")["stages"]}["frame"]["solo"][0]
    assert solo["can"] is False and solo["why"] == "1단계 「문서 검토」 이 먼저입니다"
    X.start("t", {"from": "frame", "role": "target", "redo": "frame"})
    rec = _done("t")
    assert rec["status"] == "left" and rec["end"]["text"] == "남김 — 1단계 「문서 검토」 이 덜 끝났습니다" and not [c for c in fit.calls if c[0] in ("plan", "apply")]   # 실행기의 경계 검사도 같은 눈으로
