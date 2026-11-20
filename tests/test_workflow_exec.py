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
    for body, reason in (({"from": "frame"}, "client"), ({"from": "review", "to": "map"}, "client"), ({"from": "review", "docs": {"target": "t", "source": "zz"}}, "docs")):
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
    assert all(g["server"] is False and g["steps"] is None for g in v["stages"][1:])
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
