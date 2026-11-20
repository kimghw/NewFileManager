"""단위문서 TASK 의 문(spec_워크플로우 ② §17-3 「단위문서 TASK 의 문」 — app/unit_steps.py): 문서 쌍 · 판정 재료 · 분석 시작 → 끝 · 작성 지침 · 건너뛰기 · 실행 기록 저장 · Outcome 의 꼴."""
import time

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import task_options, unit_steps as U, works


@pytest.fixture
def client():
    from app import merge_api, server
    server.DOCS.clear()
    merge_api._CACHE.clear()
    return TestClient(server.app)


def _upload(c, path):
    r = c.post("/api/docs?new=1", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _task(c, wid, **task):
    assert c.put(f"/api/works/{wid}/task", json={"kind": "rnd", "job": "plan_to_report", "project": "시험 과제", **task}).status_code == 200


def test_pair_is_the_same_from_either_document(client):
    """어느 칸의 문서에서 불러도 같은 쌍 — 목적 문서 = 그 워크플로우의 목적 종류 · 원본 = 자리 연결이 쓰는 원본."""
    plan, report, alone = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM), _upload(client, M.REPORT_FORM)
    _task(client, plan, file="plan")
    _task(client, report, file="report")
    a, b = U.pair(plan), U.pair(report)
    assert (a["target"]["id"], a["source"]["id"]) == (b["target"]["id"], b["source"]["id"]) == (report, plan)
    assert a["job"] == "plan_to_report" and a["scope"] == ["시험 과제", "plan_to_report", 1] and (a["file"], b["file"]) == ("plan", "report") and a["kinds"] == {"target": "report", "source": "plan"}
    assert a["target"]["format"] == "hwpx" and a["target"]["name"]
    _task(client, plan, file="plan", round=2)   # 다른 라운드로 간 원본 — 그 묶음의 원본이 아니다
    assert U.pair(report)["source"] is None and U.pair(plan)["target"] is None and U.pair(plan)["source"]["id"] == plan
    lone = U.pair(alone)   # 워크플로우가 없는 문서 — 그 문서 하나
    assert lone["job"] == "" and lone["target"]["id"] == alone and lone["source"] is None
    assert U.pair("nope") is None and U.work("nope") is None and U.facts("nope") is None


def test_analysis_runs_to_the_end_and_guides_are_kept(client):
    report = _upload(client, M.REPORT_FORM)
    f = U.facts(report)
    assert f["fmt"] == "hwpx" and f["heads"] == {"s2": False, "s3": False, "rev2": None, "rev3": None, "llm": False, "asked": False, "job": None} and f["guides"] is None
    got = U.start_heads(report, "first")
    assert got.ok and got.code == "ok" and got.data["status"] in ("running", "done") and got.data["first"] is True
    again = U.start_heads(report, "first")
    assert again.code in ("busy", "ok")   # 도는 중이면 busy(끝났으면 다시 받는다)
    t0 = time.time()
    while (U.job(report).data or {}).get("status") == "running" and time.time() - t0 < 240:
        time.sleep(0.1)
    job = U.job(report)
    assert job.code == "ok" and job.data["status"] == "done" and job.rev == 0   # 분석은 문서를 바꾸지 않는다
    f = U.facts(report)
    assert f["heads"]["s2"] and f["heads"]["s3"] and f["heads"]["llm"] is False and f["heads"]["job"]["status"] == "done"
    kept = U.guides_keep(report)
    assert kept.ok and "saved" in kept.data and isinstance(U.facts(report)["guides"], int)
    assert U.stop_llm(report).code == "nothing"   # 도는 LLM 검증·보완이 없음
    assert U.touch(report) is True and U.touch("nope") is False


def test_outcome_codes_follow_the_endpoint_status(client):
    assert U.start_heads("nope").code == "missing" and U.job("nope").code == "missing" and not U.job("nope").ok
    assert U.start_heads(_upload(client, M.REPORT_FORM), 7).code == "invalid"   # 400 — 모르는 단계
    assert U.Outcome().ok and U.Outcome("nothing").ok and not U.Outcome("stale").ok and set(U.CODES) >= {"ok", "busy", "stale", "blocked", "rejected", "invalid", "missing", "error"}

    def boom():
        raise RuntimeError("x")
    assert U._run(boom).code == "error" and "RuntimeError" in U._run(boom).text
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    def stale():
        raise HTTPException(409, {"reason": "stalePlan", "message": "계획이 낡았습니다"})
    got = U._run(stale, on409="stale")
    assert got.code == "stale" and got.text == "계획이 낡았습니다" and got.data["detail"]["reason"] == "stalePlan"
    back = U._run(lambda: JSONResponse({"detail": "표준 검사에 걸렸습니다"}, status_code=422))   # _transact 가 되돌리고 **돌려준** 응답
    assert back.code == "rejected" and back.text == "표준 검사에 걸렸습니다"


def test_skips_live_in_the_workflow_options_of_the_bundle(client):
    """「건너뛰기」 = 워크플로우 옵션(묶음마다 — 모든 화면 · 실행이 같이 본다) · 편집 구역 기준의 판과 따로 · 초기화 뒷정리가 지운다."""
    plan, report = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM)
    _task(client, plan, file="plan")
    _task(client, report, file="report")
    assert U.skips(report) == [] and U.skip_set(report, plan, True).data == [plan] and U.skips(plan) == [plan]   # 같은 묶음 — 어느 문서에서 읽어도
    assert task_options.resolve(works.work(report))["rev"] == 0   # 편집 구역 기준의 판은 그대로(그 화면의 「다른 화면이 먼저 바꿈」 이 안 걸린다)
    assert task_options.set_zones(works.work(report), ["org"])["rev"] == 1 and U.skips(report) == [plan]
    assert U.skip_set(report, "nope", True).code == "missing"
    assert task_options.flow_forget(plan) == 1 and U.skips(report) == []
    assert U.skip_set(report, plan, True).ok and U.skip_set(report, plan, False).data == []


def test_run_records_are_written_under_the_work_folder(client):
    wid = _upload(client, M.REPORT_FORM)
    assert U.store.enabled(wid) and U.store.numbers(wid) == [] and U.store.read(wid, 1) is None
    assert U.store.write(wid, 2, {"n": 2, "status": "running"}) and U.store.write(wid, 10, {"n": 10})
    assert U.store.numbers(wid) == [2, 10] and U.store.read(wid, 2) == {"n": 2, "status": "running"}
    assert works.folder(wid).joinpath(U.RUNS, "2.json").is_file()
    U.store.log(wid, event="start", n=2)
    assert [e for e in works.events(wid) if e.get("kind") == U.LOG_KIND][0]["event"] == "start"
    assert not U.store.enabled("nope") and U.store.write("nope", 1, {}) is False


# ---------------------------------------------------------------- 걸음 2 — 구성 · 구조 반영의 문(확정 → 계획(같은 검사) → 반영 · 낡은 계획 → 다시 분석)
def _wait_heads(doc, seconds=240):
    t0 = time.time()
    while (U.job(doc).data or {}).get("status") == "running" and time.time() - t0 < seconds:
        time.sleep(0.1)
    return U.job(doc).data


def test_config_and_division_doors_on_a_real_pair(client):
    plan, report = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM)
    _task(client, plan, file="plan")
    _task(client, report, file="report")
    d0 = U.div_facts(report)
    assert d0["input"] is None and d0["applied"] is None and d0["form"] and d0["sharing"]["shared"] and d0["sharing"]["project"] == "시험 과제"
    assert U.config_save(plan, M.SMALL_VALUES).ok
    got = U.config_confirm(report, U.div_facts(plan)["input"])
    assert got.ok and U.div_facts(report)["confirmed"]["values"] == U.div_facts(plan)["input"]   # 같은 프로젝트 — 공유 입력 · 확정
    plan_ = U.division_plan(report, U.div_facts(report)["input"])
    assert plan_.ok and plan_.data["planId"] and isinstance(plan_.data["autoStops"], str) and plan_.data["autoStopsKind"] in ("", "issues", "orgs")
    rev0 = U.facts(report)["rev"]
    old = U.division_plan(report, U.div_facts(report)["input"]).data   # 계획을 다시 세우면 앞 계획은 버린다 — 낡은 계획의 반영은 stale(다시 계획하지 않는 것은 실행기의 몫)
    assert U.division_apply(report, plan_.data["planId"], plan_.data["baseRev"]).code == "stale"
    done = U.division_apply(report, old["planId"], old["baseRev"])
    assert done.code in ("ok", "nothing"), done
    if done.code == "ok":
        assert U.facts(report)["rev"] == rev0 + 1 and U.div_facts(report)["applied"]["values"] == U.div_facts(report)["input"]
    assert U.division_apply(report, old["planId"], old["baseRev"]).code == "stale"   # 같은 계획을 두 번 — 이미 버려졌다
    assert U.division_plan("nope", M.SMALL_VALUES).code == "missing" and U.div_facts("nope") is None
    assert U.config_read(plan).code == "ok"   # 빈 양식이면 읽은 값이 없다(data None) — 끝점은 그대로


def test_frame_stage_runs_on_the_server_to_the_end_with_llm_off(client, monkeypatch):
    """실제 쌍 — 1단계(헤딩 · 표 분석 · LLM 을 못 써 「건너뜀」) → 2단계(확정 → 울타리 → 계획 → 반영 → 다시 분석 → 작성 지침 → LLM 「건너뜀」)가 창 없이 끝까지."""
    from app import workflow_exec as X
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
    X.configure(U)
    monkeypatch.setattr(U, "llm_ok", lambda: False)
    monkeypatch.setitem(X.WAIT, "poll", 0.05)
    monkeypatch.setitem(X.FENCE_WAIT, "settle", 0.2)
    plan, report = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM)
    _task(client, plan, file="plan")
    _task(client, report, file="report")
    assert U.config_save(plan, M.SMALL_VALUES).ok

    def run(body):
        X.start(report, body)
        t0 = time.time()
        while report in X.RUNS and time.time() - t0 < 400:
            time.sleep(0.1)
        return X.last(report)
    rec = run({"from": "review"})
    assert rec["status"] == "done", rec["end"]
    rec = run({"from": "frame"})
    assert rec["status"] == "done", rec["end"]
    assert rec["end"]["text"].startswith("끝남 — 구조를 맞췄습니다 — 사업계획서와 같음 · 연차보고서에 반영됨 — ") and "연차보고서 LLM 검증·보완은 건너뜀(LLM 을 쓸 수 없음)" in rec["end"]["text"]
    assert rec["end"]["text"].endswith(" · 내용은 3단계 「내용 넣기」 에서 넣습니다")
    f, d = U.facts(report), U.div_facts(report)
    assert d["applied"] and d["applied"]["values"] == d["input"] and f["heads"]["rev2"] == f["heads"]["rev3"] == d["applied"]["rev"]   # 분석이 구조 반영 뒤의 것
    frame = X.status_of(report)["stages"][1]
    assert frame["left"] == 0 and frame["why"] == "남은 단계가 없습니다" and not X.FENCE and not X.NOTICE
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()


def test_fill_and_clean_doors_and_the_whole_relay_chain_on_a_real_pair(client, monkeypatch):
    """실제 쌍 — 「이어서 한 번에」 1 → 4단계가 서버에서 창 없이 끝까지(LLM 끔): 분석 → 구성 확정 → 구조 반영 → 다시 분석 → 자리 연결 → 넣기 계획 → 반영 → 작성요령 삭제.
    그 뒤 넣기 · 정리의 문(fill_facts · fill_ver · links · fill_plan · fill_apply · cleanup_count · cleanup)의 꼴(spec_워크플로우 ② §18-12 ② · ③)."""
    from app import merge_api
    from app import workflow_exec as X
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
    X.configure(U)
    monkeypatch.setattr(U, "llm_ok", lambda: False)
    monkeypatch.setitem(X.WAIT, "poll", 0.05)
    monkeypatch.setitem(X.FENCE_WAIT, "settle", 0.2)
    plan, report = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM)
    _task(client, plan, file="plan")
    _task(client, report, file="report")
    assert U.config_save(plan, M.SMALL_VALUES).ok
    X.start(report, {"from": "review", "to": "clean"})
    t0 = time.time()
    while report in X.RUNS and time.time() - t0 < 600:
        time.sleep(0.1)
    rec = X.last(report)
    assert rec["status"] in ("done", "left"), rec["end"]
    assert [g["id"] for g in rec["stages"]] == ["review", "frame", "map", "clean"], rec["stages"]
    by = {g["id"]: g for g in rec["stages"]}
    assert by["frame"]["text"].startswith("구조를 맞췄습니다") and (by["map"]["text"].startswith("연결됨 ") or by["map"]["text"].startswith("이어진 자리가 없어 넣을 내용이 없습니다(연결됨 ")), by["map"]
    assert by["clean"]["text"].endswith("지웠습니다") or "지웠습니다 · " in by["clean"]["text"] or by["clean"]["text"] == "지울 안내가 없습니다", by["clean"]
    assert not X.FENCE and not X.NOTICE and not [t for t in rec.get("tries") or () if t["status"] == "started"]   # LLM 끔 — 유료 호출 없음
    assert U.cleanup_count(report).data["counts"]["total"] == 0 and U.facts(plan)["rev"] == 0   # 원본은 그대로
    # 문의 꼴
    F = U.fill_facts(report)
    assert set(F) >= {"links", "plan", "heads", "cleanup", "filled"} and F["links"]["error"] is None and F["heads"] == {"old": False, "kept": False, "stale": False}
    assert F["filled"] is not None or (F["links"]["kept"] or {}).get("applied") or by["map"]["text"].startswith("이어진 자리가 없어")   # 「내용 넣기」 의 끝은 문서의 표식으로
    ver = U.fill_ver(report)
    assert isinstance(ver, str) and len(ver) == 16 and U.fill_ver(report) == ver
    L = U.links(report)
    assert L.ok and L.data["counts"] == F["links"]["counts"]
    p = U.fill_plan(report)
    assert p.ok and p.data["planId"] and U.fill_facts(report)["plan"]["fresh"] is True
    got = U.fill_apply(report, p.data["planId"])
    assert got.code in ("ok", "nothing"), got
    assert U.fill_apply(report, p.data["planId"]).code == "stale"   # 같은 계획을 두 번 — 이미 버려졌다
    c = U.cleanup_count(report)
    assert c.ok and U.cleanup(report, c.data["rev"]).code == "nothing"
    assert U.fill_facts("nope") is None and U.fill_ver("nope") is None and U.links("nope").code == "missing"
    assert merge_api.inputs_now(plan) is None   # 원본 문서에는 넣기 계획이 없다(그 문서를 받는 원본이 없음)
    X.RUNS.clear(); X.BUSY.clear(); X.LAST.clear()
