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
    for body, reason in (({"from": "review", "to": "map"}, "client"), ({"from": "review", "docs": {"target": "t", "source": "zz"}}, "docs")):
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
    assert all(g["server"] is False and g["steps"] is None for g in v["stages"][2:])
    assert client.post(f"/api/works/{plan}/flow/runs", json={}).status_code == 400
    assert client.post(f"/api/works/{plan}/flow/runs", json={"from": "map"}).json()["reason"] == "client"
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
        return Outcome("ok", "", {"planId": "p1", "baseRev": self.rev[doc], "summary": {"groups": 2}, "autoStops": self.stops, "autoStopsKind": "issues" if self.stops else "", "stale": False})

    def division_apply(self, doc, plan_id, expect):
        self.calls.append(("apply", doc, plan_id, expect))
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
    """단계 key 가 워크플로우마다 겹친다 — 취합 · 양식 맞추기의 config · plan · apply 를 이관의 처리 함수로 돌리지 않는다."""
    from app import workflow_state as S
    for job in ("plan_merge", "report_fit", "plan_fit", "doc_edit", "style_copy"):
        task = S.definition(job)
        assert not S.relay_pair(task) and not any(S.served(task, g["id"]) for g in task["stages"]), job
    task = S.definition("plan_to_report")
    assert S.relay_pair(task) and S.served(task, "review") and S.served(task, "frame")
