"""취합(가족 gather — 사업계획서 취합 plan_merge)을 서버 실행기로(spec_워크플로우 ② §18-13 「걸음 5 — 취합」 · 갈래 「다」 — app/workflow_units.py GATHER · app/workflow_exec.py 의 그 절 · 문 unit_steps.gather_*):
상태 식(화면 gather.js gatherSteps)과, **진짜 모듈**로 2단계(구조 확인 → 배포 기준본) · 3단계(원본 문서마다 한 덩이 — 반영할 기관 → 자리 연결 → 넣기 계획 → 내용 반영)를 끝까지 돌린다(LLM 은 끔).
준비 도구는 취합 API 시험의 것(tests/test_merge_gather_api.py — 값을 반영한 양식 = 기준본 · 기관 문서 = 그 사본을 고친 것)."""
import time

import pytest
from fastapi.testclient import TestClient

import gather_data as D
from app import merge_gather_api as GA
from app import server, unit_steps, works
from app import workflow_exec as X
from app import workflow_state as S
from app import workflow_units as U
from test_merge_gather_api import _analysed, _edit_a, _edit_b, _master, _part, _row, _texts, _upload, _bytes  # noqa: F401

J1, J2 = D.J1, D.J2


@pytest.fixture
def client(monkeypatch):
    server.DOCS.clear()
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS):
        box.clear()
    monkeypatch.setattr(S, "OPEN", {"relay", "gather"})   # 취합의 틀을 연 것으로(화면이 따라오는 갈래 「라」 에서 실제로 연다)
    monkeypatch.setattr(unit_steps, "llm_ok", lambda: False)   # 유료 호출을 걸지 않는다
    monkeypatch.setitem(X.WAIT, "poll", 0.05)
    for k, v in (("settle", 0.2), ("poll", 0.02)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()
    X.configure(unit_steps)
    yield TestClient(server.app)
    for d in (X.RUNS, X.BUSY, X.LAST, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()


def _run(c, wid, body, seconds=240):
    r = c.post(f"/api/works/{wid}/flow/runs", json=body)
    assert r.status_code == 202, r.text
    n, t0 = r.json()["run"]["n"], time.time()
    while c.get(f"/api/works/{wid}/flow/live").json()["run"] and time.time() - t0 < seconds:
        time.sleep(0.05)
    return c.get(f"/api/works/{wid}/flow/runs/{n}").json()


def _stage(v, gid):
    return next(g for g in v["stages"] if g["id"] == gid)


def test_the_gather_family_is_served_only_while_its_frame_is_open_and_reads_its_own_units(monkeypatch):
    task = S.definition("plan_merge")
    assert S.family(task) == "gather" and S.framed(task) and S.base(task) == "target" and "gather" in S.OPEN   # 2026-11-20 갈래 「라」 — 화면의 거울과 함께 열었다
    monkeypatch.setattr(S, "OPEN", {"relay"})
    assert not any(S.served(task, g["id"]) for g in task["stages"])   # 틀을 닫으면 화면이 돈다(끄는 길)
    monkeypatch.setattr(S, "OPEN", {"relay", "gather"})
    assert all(S.served(task, g["id"]) for g in task["stages"])
    lines = {x["key"]: x["unit"] for x in S.lines(task)}
    assert lines["config"] is U.COMMON["config"] and lines["files"] is U.COMMON["files"]   # 준비 · 구성 확정은 같이 쓰는 단위(구성의 기준 = 취합본 자신)
    assert all(lines[k] is U.GATHER[k] for k in ("division", "frame", "hand", "part", "heads", "link", "llm", "plan", "apply", "drop"))   # key 가 겹쳐도 취합의 단위가 먼저
    assert lines["hand"]["kind"] == "pick" and [k for k, u in lines.items() if u["each"]] == ["part", "heads", "link", "llm", "plan", "apply"]   # 「배포 · 회수」 는 「했음」 을 받지 않는다 · 원본 문서마다의 덩이
    for g in task["stages"]:
        for s in g["steps"]:   # 등록부의 줄과 문서 바뀜 · 선택 · 하는 문서가 같다
            u = lines[s["key"]]
            assert u["change"] == s["change"] and u["optional"] == s["optional"], s["key"]
            assert (u["place"] == s["on"]) if s["on"] in ("pair", "flow") else set(U.roles_of(s["on"])) <= set(u["roles"]), s["key"]
            assert (u["kind"] == "auto") == (s["key"] in X.FAMILY_HANDLERS["gather"] or s["key"] == "config"), s["key"]
    relay = S.definition("plan_to_report")
    assert X._handler(task, {"unit": lines["apply"], "key": "apply"}) is X._do_g_apply and X._handler(relay, {"unit": U.unit("apply", "relay"), "key": "apply"}) is X._do_apply
    assert not X._fill_need(task)   # 취합본에 이관의 연결 목록을 읽지 않는다


def test_gather_state_lines_follow_the_screen_rules():
    V2 = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대"], "nonprofit": [False, False], "outside": [], "overseas": [], "entrust": []}, "subs": [], "current": 1}
    cf = {"values": V2, "at": 1}

    def ctx(div, G):
        return {"ready": True, "lack": [], "llm": True, "skip": set(), "base": "target",
                "pair": {"target": {"role": "target", "title": "취합본", "id": "t", "facts": {"id": "t", "heads": {"s2": True, "s3": True, "llm": False, "job": None}, "div": div, "gather": G}}}}
    div = lambda **k: {"input": V2, "applied": None, "confirmed": cf, "partial": [], "form": "연구개발계획서", "supported": True, "rev": 0, "read": None, "sharing": None, "plan": None, "stale": False, **k}  # noqa: E731
    st = lambda key, d, G=None: U.state(key, ctx(d, G), "gather")  # noqa: E731
    assert st("division", div(confirmed=None)) == {"st": "todo", "text": ""}   # 확정이 먼저
    assert "아직 취합본에 반영되지 않았습니다" in st("division", div())["text"] and "지원하지 않습니다" in st("division", div(supported=False))["text"]
    assert st("division", div(applied={"values": V2}))["text"] == "취합본에 반영됨 — 1단계 · 전체 2년 · 기관 2곳"
    assert st("division", div(applied={"values": V2, "adopted": True}))["text"].startswith("구조가 이미 값에 맞음(확인함)")
    assert st("division", div(applied={"values": {**V2, "current": 2}}))["st"] == "todo"   # 반영 값 = 입력 값 전체(당해 차년도도 — 화면 gatherDivDone)
    ok = div(applied={"values": V2})
    assert st("frame", ok, None)["st"] == "blocked" and st("frame", ok, {"frame": None, "reasons": ["staleHeadings"], "parts": []})["text"].endswith("헤딩·표 분석이 지금 문서의 것이 아님")
    assert st("frame", ok, {"frame": {"stale": False}, "parts": []})["st"] == "done" and "기준본이 낡았습니다" in st("frame", ok, {"frame": {"stale": True}, "parts": []})["text"]
    assert st("hand", ok, {})["st"] == "done" and st("hand", ok, {})["skipped"]
    none = st("part", ok, {"frame": {"stale": False}, "parts": []})
    assert none["st"] == "done" and none["skipped"] and "기관 문서가 아직 없습니다" in none["text"]
    assert st("part", ok, {"frame": {"stale": True}, "parts": [{"work": "a"}]}) == {"st": "todo", "text": ""}   # 기준본이 낡으면 줄이 열리지 않는다
    rows = [{"work": "a", "name": "A.hwpx", "orgs": ["가나대"], "counts": {"ready": 0, "same": 3}, "todo": 0, "llm": None, "reasons": []},
            {"work": "b", "name": "B.hwpx", "orgs": [], "counts": None, "todo": None, "llm": None, "reasons": ["noHeadings"]},
            {"work": "c", "name": "C.hwpx", "orgs": ["다라연"], "counts": {"ready": 2}, "todo": 2, "llm": {"at": 1}, "reasons": ["lowMatch"]}]
    G = {"frame": {"stale": False}, "parts": rows}
    per = lambda key: [(p["doc"], p["st"]) for p in st(key, ok, G)["per"]]  # noqa: E731
    assert per("part") == [("a", "done"), ("b", "todo"), ("c", "done")] and per("heads") == [("a", "done"), ("b", "todo"), ("c", "done")]
    assert per("link") == [("a", "done"), ("b", "todo"), ("c", "done")] and per("llm") == [("a", "done"), ("b", "done"), ("c", "done")]
    assert per("apply") == per("plan") == [("a", "done"), ("b", "todo"), ("c", "todo")] and st("apply", ok, G)["text"] == "기관 문서 3개 · 남은 문서 2개"
    assert U.gt_part_done({**rows[2], "todo": 0}) is False   # 자리를 충분히 확인하지 못한 문서 — 넣을 수 있는 것이 남으면 끝이 아니다
    assert U.gt_done_text({"counts": {"paragraphs": 3, "cells": 1200, "blocks": 4, "placeholders": 1, "removed": 1}, "calc": [{"action": "needed"}, {"action": "recalculated"}], "dropped": [1]}) == "문단 3 · 표 칸 1,200 · 지운 자리표시 줄 1 · 다시 계산 필요 1칸 · 못 옮긴 것 1"
    assert U.gt_done_text({}) == "넣음" and U.gt_todo({"items": [{"status": "ready"}, {"status": "ready", "decision": {"value": "check"}}, {"status": "overlap"}]}) == 1


def test_frame_stage_confirms_the_structure_and_fixes_the_distribution_frame(client):
    """2단계 — 구조가 이미 값에 맞는 취합본(구조를 맞춘 프레임을 올린 것): 확인만(adopt) → 배포 기준본 · 낡은 기준본은 등록한 기관 문서가 있으면 다시 만들지 않고 멈춘다."""
    c = client
    to, _ = _master(c, frame=False)
    b = D.base()["side"]
    assert c.post(f"/api/docs/{to}/divisions/confirm", json={"values": b["values"]}).status_code == 200
    pair = unit_steps.pair(to)
    assert pair["job"] == "plan_merge" and pair["target"]["id"] == to and pair["source"] is None and pair["sources"] == [] and pair["kinds"] == {"target": "plan", "source": "part"}
    v = c.get(f"/api/works/{to}/flow").json()
    assert v["ready"] and v["docs"]["sources"] == [] and [(g["id"], g["server"]) for g in v["stages"]] == [("config", True), ("frame", True), ("map", True)]
    frame = _stage(v, "frame")
    assert _stage(v, "config")["left"] == 0 and [(s["key"], s["done"]) for s in frame["steps"]] == [("division", True), ("frame", False), ("hand", True)] and frame["can"]
    assert _stage(v, "map")["why"] == "「문서 프레임 작성」 이 먼저입니다" or "먼저입니다" in _stage(v, "map")["why"]
    rec = _run(c, to, {"from": "frame"})
    assert rec["status"] == "done", rec
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("division", "nothing"), ("frame", "done")] and "배포 기준본을 만들었습니다" in rec["end"]["text"]
    v = c.get(f"/api/works/{to}/flow").json()
    assert _stage(v, "frame")["left"] == 0 and _stage(v, "map")["left"] == 0 and all(s["skipped"] for s in _stage(v, "map")["steps"] if s["key"] in ("part", "apply"))   # 기관 문서가 아직 없다
    # 구조 확인(adopt) — 반영 기록이 없는 같은 문서를 새로: 구조가 이미 값에 맞으면 확인만 하고 기준본까지
    to2 = _upload(c, "취합본2.hwpx", b["bytes"])
    assert c.put(f"/api/works/{to2}/task", json={"kind": "rnd", "file": "plan", "job": "plan_merge", "project": "취합 시험 2"}).status_code == 200
    assert c.post(f"/api/docs/{to2}/divisions/confirm", json={"values": b["values"]}).status_code == 200
    _analysed(to2, b["graph"], b["tables"])
    rec = _run(c, to2, {"from": "config", "to": "frame"})
    assert rec["status"] == "done", rec
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("division", "done"), ("frame", "done")] and unit_steps.div_facts(to2)["applied"]["adopted"] is True
    assert "구조가 이미 값에 맞음(확인함)" in rec["steps"][0]["text"]
    # 낡은 기준본 — 등록한 기관 문서가 있으면 저절로 다시 만들지 않는다
    A = _part(c, to, f"기관A_{J1}.hwpx", _edit_a, orgs=[J1])
    monkey = server._sess(to)
    with monkey.lock:
        monkey.division["applied"] = {**monkey.division["applied"], "rev": 99, "planId": "p2"}   # 기준본 뒤에 프로젝트 구성을 다시 반영한 것으로
    G = c.get(f"/api/docs/{to}/gather").json()
    if G["frame"]["stale"]:
        rec = _run(c, to, {"from": "frame"})
        assert rec["status"] == "halted" and rec["halt"]["code"] == "frameStale" and "저절로 다시 만들지 않습니다" in rec["end"]["text"] and A in [p["work"] for p in G["parts"]]


def test_people_cannot_change_the_gather_while_a_run_owns_it(client):
    """도는 실행에 든 취합 — 사람이 누른 배포 기준본 · 등록 · 빼기 · 반영할 기관 · 결정 · LLM 검토 · 넣기 계획 · 반영은 409(그 실행이 스스로 부르는 것은 지나간다 — 아래 3단계 시험이 본다)."""
    c = client
    to, _ = _master(c)
    A = _part(c, to, f"기관A_{J1}.hwpx", _edit_a, orgs=[J1])
    key = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["items"][0]["key"]
    X.BUSY.update({to: to, A: to})
    X.RUNS[to] = X.Run({"n": 1, "scope": ["취합 시험", "plan_merge", 1], "docs": {"target": {"id": to}}, "steps": [], "stages": []}, None, {}, None)
    try:
        g = f"/api/docs/{to}/gather"
        calls = [c.post(f"{g}/frame"), c.put(f"{g}/parts/{A}", json={"orgs": [J2]}), c.delete(f"{g}/parts/{A}"), c.post(f"{g}/parts/{A}/auto"), c.put(f"{g}/parts/{A}/links/{key}", json={"value": "skip"}),
                 c.post(f"{g}/parts/{A}/llm"), c.post(f"{g}/parts/{A}/plan"), c.post(f"{g}/parts/{A}/apply", json={"planId": "x"}), c.post(f"{g}/drop/apply", json={"planId": "x"})]
        assert [r.status_code for r in calls] == [409] * len(calls) and all("도는 중" in r.text for r in calls), [(r.status_code, r.text[:60]) for r in calls]
        assert c.get(g).status_code == 200 and c.get(f"{g}/parts/{A}/links").status_code == 200   # 읽기는 된다
    finally:
        X.RUNS.clear(); X.BUSY.clear()
    assert c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J1]}).status_code == 200


def test_map_stage_fills_document_by_document_and_leaves_the_unassigned_one(client):
    """3단계 — 원본 문서마다 한 덩이(등록한 차례): 기관이 정해진 문서는 자리 연결 → 넣기 계획 → 내용 반영(울타리 안) · 미지정 문서는 그 문서만 남기고 이어 간다 · 간단 모드(auto)면 이번에 올린 문서의 기관을 파일 이름으로 정한다."""
    c = client
    to, _ = _master(c)
    b = D.base()["side"]
    assert c.post(f"/api/docs/{to}/divisions/confirm", json={"values": b["values"]}).status_code == 200
    A = _part(c, to, f"기관A_{J1}.hwpx", _edit_a, orgs=[J1])
    B = _part(c, to, f"기관B_{J2}.hwpx", _edit_b)   # 반영할 기관 미지정
    pair = unit_steps.pair(B)   # 기관 문서에서 불러도 같은 묶음
    assert pair["target"]["id"] == to and [d["id"] for d in pair["sources"]] == [A, B]
    v = c.get(f"/api/works/{to}/flow").json()
    m = _stage(v, "map")
    assert [d["id"] for d in v["docs"]["sources"]] == [A, B] and m["can"] and m["change"] is True
    assert [(s["key"], [p["st"] for p in s.get("per") or ()]) for s in m["steps"] if s["key"] in ("part", "apply")] == [("part", ["done", "todo"]), ("apply", ["todo", "todo"])]
    before = _texts(to)
    rec = _run(c, A, {"from": "map"})   # 기관 문서에서 눌러도 취합본에서 돈다
    assert rec["status"] == "left", rec
    assert rec["docs"]["target"]["id"] == to and [d["id"] for d in rec["docs"]["sources"]] == [A, B]
    steps = [(s["key"], s.get("doc"), s["status"]) for s in rec["steps"]]
    assert steps == [("link", A, "done"), ("llm", A, "nothing"), ("plan", A, "done"), ("apply", A, "done"), ("part", B, "left")], steps   # LLM 을 쓸 수 없음 — 글만 남기고 계속
    assert rec["end"]["text"].startswith("남김 — 기관 문서 1개 반영 — ") and f"반영할 기관 미지정 1개는 건너뜀(기관B_{J2}.hwpx)" in rec["end"]["text"] and "LLM 검토는 못 함(LLM 을 쓸 수 없음)" in rec["end"]["text"]
    after = _texts(to)
    assert after != before and any(f"{J1} 1차년도 개발 목표" in t for t in after) and not any(f"{J2} 1차년도 개발 목표" in t for t in after)
    assert not X.FENCE and not X.NOTICE and X.busy_text(A) == "" and X.busy_text(B) == ""
    G = c.get(f"/api/docs/{to}/gather").json()
    assert _row(G, A)["todo"] == 0 and _row(G, B)["orgs"] == []
    # 끝 확정(spec_워크플로우 ② §18-24 「한 번에 진행 뒤 고친 문단 확정」) — 남김으로 끝나도 취합본을 한 번 · 기관 문서는 확정하지 않는다 · 기준만 바뀐다(차례 · 글은 그대로)
    made = works.commits(to)
    assert [(x["doc"], x["status"]) for x in rec["commits"]] == [(to, "ok")] and len(made) == 1 and made[-1]["flowRun"] == rec["n"] and made[-1]["by"] == "flow"
    assert works.commits(A) == [] and works.commits(B) == [] and server.DOCS[to].base_n == made[-1]["n"] and _texts(to) == after
    assert rec["end"]["text"].endswith(f"앞 상태 = 올린 원본)") and len(rec["end"]["text"]) <= X.TEXT_MAX
    m = _stage(c.get(f"/api/works/{to}/flow").json(), "map")
    assert [(s["key"], [p["st"] for p in s.get("per") or ()]) for s in m["steps"] if s["key"] in ("part", "apply")] == [("part", ["done", "todo"]), ("apply", ["done", "todo"])] and m["left"] > 0
    # 간단 모드 — 이번에 올린 문서(B)의 반영할 기관을 파일 이름으로 정하고 넣는다(공통 자리는 먼저 넣은 A 가 차지했다 — 겹침으로 남는다)
    rec = _run(c, to, {"from": "map", "quick": True, "auto": [B]})
    steps = [(s["key"], s.get("doc"), s["status"]) for s in rec["steps"]]
    assert steps[0] == ("part", B, "done") and ("apply", B, "done") in steps and not [s for s in steps if s[1] == A], steps   # A 는 넣을 것이 안 남아 지나간다
    assert rec["auto"] == [B] and rec["quick"] is True and f"반영할 기관 → {J2}(파일 이름)" in rec["steps"][0]["text"]
    assert any(f"{J2} 1차년도 개발 목표" in t for t in _texts(to)) and _row(c.get(f"/api/docs/{to}/gather").json(), B)["orgs"] == [J2]
    assert len(works.commits(to)) == 2 and works.commits(to)[-1]["flowRun"] == rec["n"]   # 묶음째 실행마다 끝에 한 번
    assert c.post(f"/api/works/{to}/flow/runs", json={"from": "map", "auto": "x"}).status_code == 400


def _g(*units):
    """취합형 조립의 줄들 — 하는 문서는 그 줄의 것(구성 반영 · 배포 기준본 = 목적 · 기관 문서 올리기 · 헤딩 · 표 분석 = 원본 · 나머지는 서버가 채운다)."""
    on = {"division": ["target"], "frame": ["target"], "part": ["source"], "heads": ["source"]}
    return [{"unit": u, "on": on.get(u, [])} for u in units]


def test_a_composed_gather_workflow_is_checked_saved_assembled_and_served(client):
    """취합형(N → 1)으로 조립한 워크플로우(② §18-13 갈래 「라」 ⓶ ⓷): 조립 화면의 처음 줄 목록 = 붙박이 취합의 묶음 · 줄 · 검사(차례 · 기관 문서마다의 덩이 · 앞 줄 · 이관의 줄 · 놓을 수 없는 문서 · 문서 쌍) ·
    늘 줄 목록(v2)으로 저장 · 서버가 그 키를 취합으로 다룬다(문서 종류 · 전제 · 기본 구역 · 가족 gather · 구성의 기준 = 취합본) · 그 정의의 묶음(g1 …)을 서버 실행기가 돈다(진짜 모듈)."""
    from app import custom_tasks as C
    from app import custom_tasks_api as CA
    from app import job_prompts, task_options
    c = client
    first = CA.gather_lines()
    assert [(g["name"], [s["unit"] for s in g["steps"]]) for g in first] == [("프로젝트 구성", ["config"]), ("문서 프레임 작성", ["division", "frame"]),
                                                                            ("내용 매핑", ["part", "heads", "link", "llm", "plan", "apply"])]
    got = C.check("gather", "part", "plan", first)
    assert not got["errors"] and got["std"] is None and [g["id"] for g in got["flow"]] == ["g1", "g2", "g3"], got
    assert any(w.startswith("유료 LLM") and "LLM 검토" in w for w in got["warns"]) and any(w.startswith("목적 문서(취합본)를 바꾸는 줄") for w in got["warns"]), got["warns"]
    units, homes = CA.gather_units()
    by = {u["key"]: u for u in units}
    assert [u["key"] for u in units] == [*C.GATHER_UNITS, "hand"] and by["division"]["roles"] == ["target"] and by["part"]["roles"] == ["source"] and by["link"]["place"] == "pair"
    assert [u["key"] for u in units if u["each"]] == ["part", "heads", "link", "llm", "plan", "apply"] and all(u["server"] for u in units)
    assert [h["name"] for h in homes] == ["1단계 프로젝트 구성", "2단계 문서 프레임 작성", "3단계 내용 매핑", "문서 정리", "사람이 하는 일"]   # 문서 정리 = 붙박이 차례에 없는 조립 도구(넣은 뒤 템플릿 · 서식 정리)
    assert by["retidy"]["home"] == "gather_clean" and by["retidy"]["roles"] == ["target"] and by["retidy"]["uses"] == [{"unit": "apply", "must": False}] and by["retidy"]["help"]["easy"]
    bad = {
        "앞에 와야 합니다": [{"name": "a", "steps": _g("config", "division", "frame", "part", "heads", "link", "apply", "plan")}],   # 차례가 거꾸로
        "한 묶음에 잇달아": [{"name": "a", "steps": _g("part", "heads", "link", "plan")}, {"name": "b", "steps": _g("apply")}],   # 기관 문서마다 도는 줄을 쪼갬
        "「넣기 계획」": [{"name": "a", "steps": _g("part", "link", "apply")}],   # 계획 없이 반영
        "놓을 수 없는 줄": [{"name": "a", "steps": _g("config") + [{"unit": "reheads", "on": ["target"]}]}],   # 이관의 줄
        "목적 문서에만 놓을 수 있습니다": [{"name": "a", "steps": [{"unit": "config"}, {"unit": "division", "on": ["source"]}]}],   # 기관 문서(원본)는 바꾸지 않는다
    }
    for word, flow in bad.items():
        errs = C.check("gather", "part", "plan", flow)["errors"]
        assert any(word in e for e in errs), (word, errs)
    assert any("기관 문서 → 사업계획서" in e for e in C.check("gather", "plan", "report", first)["errors"])   # 그 틀의 문서 쌍이 아니다
    warn = C.check("gather", "part", "plan", [{"name": "a", "steps": _g("part", "heads", "link", "plan", "apply")}])
    assert not warn["errors"] and any("배포 기준본이 이미 있어야" in w for w in warn["warns"]), warn   # 기대는 것을 만드는 줄이 정의에 없으면 경고(저장은 됨)
    # 저장 — 구성 · 프레임을 한 묶음으로 · LLM 검토 없이
    flow = [{"name": "프로젝트 구성", "steps": _g("config", "division", "frame")}, {"name": "내용 매핑", "steps": _g("part", "heads", "link", "plan", "apply")}]
    assert c.post("/api/tasks/check", json={"shape": "gather", "flow": flow}).json()["errors"] == []   # 문서 쌍을 안 보내면 그 틀의 짝
    r = c.post("/api/tasks", json={"name": "기관 문서 모으기", "shape": "gather", "source": "part", "target": "plan", "flow": flow})
    assert r.status_code == 201, r.text
    t = r.json()["task"]
    key = t["key"]
    assert t["v"] == 2 and t["shape"] == "gather" and t["groups"] == ["g1", "g2"] and t.get("assign") is None and (t["sourceName"], t["targetName"]) == ("기관 문서", "사업계획서")
    assert c.post("/api/tasks", json={"name": "옛 꼴 취합", "shape": "gather", "source": "part", "target": "plan", "assign": {"source": [], "target": ["stage_fill"]}}).status_code == 400   # 취합형은 줄 목록으로만
    assert [x["key"] for x in c.get("/api/tasks?v=2").json()["tasks"]] == [key] and c.get("/api/tasks").json()["tasks"] == []   # 판 없이 읽는 옛 탭에는 안 실린다(v2)
    assert f'"{key}"' in c.get("/api/tasks.js?v=2").text and '"shape": "gather"' in c.get("/api/tasks.js?v=2").text
    # 서버가 그 키를 취합으로 다룬다
    assert C.is_gather(key) and server._job_ok(key) and server._gather_job(key) and C.base_of(C.get(key)) == "plan_merge"
    assert job_prompts.get(key) == job_prompts.get("plan_merge") and task_options._zones_default(key) == task_options._zones_default("plan_merge") == ["org"]
    task = S.definition(key)
    assert S.family(task) == "gather" and S.base(task) == "target" and S.framed(task) and [g["id"] for g in task["stages"]] == ["g1", "g2"]
    assert all(S.served(task, g["id"]) for g in task["stages"])
    lines = {x["key"]: x["unit"] for x in S.lines(task)}
    assert all(lines[k] is U.GATHER[k] for k in ("division", "frame", "part", "heads", "link", "plan", "apply")) and "llm" not in lines and lines["config"] is U.COMMON["config"]
    # 진짜 모듈 — 그 정의의 g1(구성 확정 → 구조 확인 → 배포 기준본)을 서버 실행기가 돈다 · 구조가 이미 값에 맞는 취합본
    b = D.base()["side"]
    to = _upload(c, "취합본.hwpx", b["bytes"])
    assert c.put(f"/api/works/{to}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "조립 취합"}).status_code == 200
    assert c.post(f"/api/docs/{to}/divisions/confirm", json={"values": b["values"]}).status_code == 200
    _analysed(to, b["graph"], b["tables"])
    pair = unit_steps.pair(to)
    assert pair["job"] == key and pair["target"]["id"] == to and pair["sources"] == [] and pair["kinds"] == {"target": "plan", "source": "part"}
    v = c.get(f"/api/works/{to}/flow").json()
    assert [(g["id"], g["server"]) for g in v["stages"]] == [("g1", True), ("g2", True)] and _stage(v, "g1")["can"], v["stages"]
    rec = _run(c, to, {"from": "g1"})
    assert rec["status"] == "done", rec
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("config", "nothing"), ("division", "done"), ("frame", "done")] and "배포 기준본을 만들었습니다" in rec["end"]["text"]   # 구성은 이미 확정 — 지나간다
    assert (rec["range"]["from"], rec["job"]) == ("g1", key) and _stage(c.get(f"/api/works/{to}/flow").json(), "g1")["left"] == 0 and c.get(f"/api/docs/{to}/gather").json()["frame"]
    # 그 정의의 g2 — 기관 문서 하나를 한 덩이로(반영할 기관 → 자리 연결 → 넣기 계획 → 내용 반영 · LLM 검토 줄은 정의에 없다)
    A = _part(c, to, f"기관A_{J1}.hwpx", _edit_a, orgs=[J1])
    rec = _run(c, to, {"from": "g2"})
    steps = [(s["key"], s.get("doc"), s["status"]) for s in rec["steps"]]
    assert steps == [("link", A, "done"), ("plan", A, "done"), ("apply", A, "done")] and rec["status"] == "done", (steps, rec["end"])
    assert any(f"{J1} 1차년도 개발 목표" in x for x in _texts(to))
    # 쓰는 중인 정의 — 단계는 못 바꾸고 못 지운다(이관형과 같다)
    assert c.put(f"/api/tasks/{key}", json={"flow": [{"name": "a", "steps": _g("config")}]}).status_code == 409 and c.delete(f"/api/tasks/{key}").status_code == 409


def test_a_composed_gather_workflow_tidies_the_inserted_lines_after_filling(client, monkeypatch):
    """취합형 조립의 「넣은 뒤 템플릿 · 서식 정리」(spec_병합 ② §5-9 9 — 「문서 정리」 의 조립 도구 · 붙박이 「사업계획서 취합」 의 차례에는 없다):
    검사(내용 반영 뒤 · 목적 문서에만 · 기관 문서마다의 덩이를 쪼개지 않음 · 내용 반영 없이 놓으면 경고만) · 이관형과 따로 선 단위 · 처리 함수는 이관의 것 ·
    서버 실행기가 내용 반영 → 정리를 차례로(정리는 취합본의 울타리 안 · 끝점은 가짜 — 진짜 끝점은 tests/test_merge_gather_api.py 의 retidy 시험) · 상태 식(_g_retidy)."""
    import threading

    from app import custom_tasks as C
    from app import workflow
    c = client
    tidy = {"unit": "retidy", "on": ["target"]}
    base = [{"name": "프로젝트 구성", "steps": _g("config", "division", "frame")}, {"name": "내용 매핑", "steps": _g("part", "heads", "link", "plan", "apply")}]
    flow = base + [{"name": "문서 정리", "steps": [tidy]}]
    got = C.check("gather", "part", "plan", flow)
    assert not got["errors"] and any(w.startswith("목적 문서(취합본)를 바꾸는 줄") and "넣은 뒤 템플릿 · 서식 정리" in w for w in got["warns"]), got
    assert C.unit_names("gather")["retidy"] == "넣은 뒤 템플릿 · 서식 정리" and "retidy" not in {s["key"] for g in workflow.BY_JOB["plan_merge"]["stages"] for s in g["steps"]}   # 붙박이 차례에는 없다
    early = C.check("gather", "part", "plan", [{"name": "a", "steps": _g("config", "division", "frame") + [tidy] + _g("part", "heads", "link", "plan", "apply")}])
    assert any("앞에 와야 합니다" in e for e in early["errors"]), early
    inside = C.check("gather", "part", "plan", [{"name": "a", "steps": _g("part", "heads", "link") + [tidy] + _g("plan", "apply")}])
    assert C.GATHER_EACH in inside["errors"], inside
    for tail in ([tidy] + _g("drop"), _g("drop") + [tidy]):   # 끌어 넣기와는 차례 무관(내용 반영 → 정리 → 사람이 더 끌어 넣기도 된다 — 끌어 넣은 내용은 정리 대상이 아니다)
        late = C.check("gather", "part", "plan", [base[0], {"name": "내용 매핑", "steps": _g("part", "heads", "link", "plan", "apply") + tail}])
        assert not late["errors"], late
    alone = C.check("gather", "part", "plan", [{"name": "a", "steps": [tidy]}])
    assert not alone["errors"] and any("앞서 넣은 내용만 맞춥니다" in w for w in alone["warns"]), alone   # 앞 줄 「내용 반영」 은 경고만(GATHER_SOFT)
    assert any("목적 문서에만 놓을 수 있습니다" in e for e in C.check("gather", "part", "plan", [{"name": "a", "steps": [{"unit": "retidy", "on": ["source"]}]}])["errors"])
    r = c.post("/api/tasks", json={"name": "기관 문서 모으고 정리", "shape": "gather", "source": "part", "target": "plan", "flow": flow})
    assert r.status_code == 201, r.text
    key = r.json()["task"]["key"]
    task = S.definition(key)
    line = next(x for x in S.lines(task) if x["key"] == "retidy")
    step = next(s for g in task["stages"] for s in g["steps"] if s["key"] == "retidy")
    assert (step["on"], step["change"], step["name"]) == ("target", "doc", "넣은 뒤 템플릿 · 서식 정리") and "취합본에 있던 줄은 건드리지 않습니다" in step["does"]
    assert line["unit"] is U.GATHER["retidy"] and U.GATHER["retidy"] is not U.RELAY["retidy"] and U.unit("retidy", "gather") is U.GATHER["retidy"]
    assert X._handler(task, line) is X._do_retidy and not X._fill_need(task) and all(S.served(task, g["id"]) for g in task["stages"])   # 이관의 연결 목록은 읽지 않는다
    assert "목적 문서(취합본)가 바뀜" in task["stages"][2]["does"]

    # 상태 식 — 넣은 것이 아직 없음(기관 문서가 남음) → 아직 · 정리 기록이 그 반영 뒤 → 끝남 · 재료 오류 → 막힘
    def st(R, G):
        return U.state("retidy", {"ready": True, "pair": {"target": {"role": "target", "title": "취합본", "id": "t", "facts": {"id": "t", "retidy": R, "gather": G}}}}, "gather")
    rows = [{"work": "a", "name": "A.hwpx", "orgs": ["가나대"], "counts": {"ready": 2}, "todo": 2, "llm": None, "reasons": []}]
    none = {"why": "넣은 내용이 없습니다 — 「내용 반영」 뒤에 합니다", "fill": None, "applied": None, "inserted": 0}
    assert st(none, {"frame": {"stale": False}, "parts": rows})["st"] == "todo" and "넣은 뒤에" in st(none, {"frame": {"stale": False}, "parts": rows})["text"]
    skip = st(none, {"frame": {"stale": False}, "parts": []})
    assert skip["st"] == "done" and skip["skipped"]   # 기관 문서가 없다 — 건너뜀
    todo = st({"why": "", "fill": 5.0, "applied": {"fill": 4.0, "counts": {}}, "inserted": 7}, {"frame": {"stale": False}, "parts": rows})
    assert todo["st"] == "todo" and "넣은 블록 7개" in todo["text"]   # 넣을 기관 문서가 남아도 넣은 것이 있으면 할 것(모든 문서를 기다리지 않는다) · 뒤에 넣으면 표식이 바뀐다
    done = st({"why": "", "fill": 5.0, "applied": {"fill": 5.0, "counts": {"levels": 2, "fix": 3, "changed": 3, "held": 1}}, "inserted": 7}, {"frame": {"stale": False}, "parts": rows})
    assert done["st"] == "done" and "사람이 넘친 레벨의 처리를 고른 줄 1" in done["text"]
    assert st({"error": "KeyError: x", "why": ""}, {})["st"] == "blocked" and st(None, {})["st"] == "blocked"

    # 서버 실행기 — 진짜 모듈로 g1 · g2 를 돈 뒤 g2 → g3(정리는 가짜 끝점: 취합본의 울타리 안에서 한 번 · 두 번째는 할 것 없음)
    seen = {"calls": [], "applied": None}

    def facts(doc):
        mark = GA._store(doc).get("filled")
        return {"why": "" if mark else "넣은 내용이 없습니다 — 「내용 반영」 뒤에 합니다", "fill": (mark or {}).get("at"), "inserted": len((mark or {}).get("ids") or ()), "applied": seen["applied"]}

    def tidy_now(doc):
        seen["calls"].append((doc, (X.FENCE.get(doc) or {}).get("thread") == threading.get_ident()))
        c_ = {"levels": 2, "grown": 1, "lines": 4, "fix": 2, "near": 0, "own": 0, "held": 0, "changed": 2, "reps": 1, "left": 0}
        seen["applied"] = {"at": 1.0, "fill": GA._store(doc)["filled"]["at"], "counts": c_}
        return unit_steps.Outcome("ok", "", {"done": {"counts": c_, "rows": []}})
    monkeypatch.setattr(unit_steps, "retidy_facts", facts)
    monkeypatch.setattr(unit_steps, "retidy", tidy_now)
    b = D.base()["side"]
    to = _upload(c, "취합본.hwpx", b["bytes"])
    assert c.put(f"/api/works/{to}/task", json={"kind": "rnd", "file": "plan", "job": key, "project": "조립 취합 정리"}).status_code == 200
    assert c.post(f"/api/docs/{to}/divisions/confirm", json={"values": b["values"]}).status_code == 200
    _analysed(to, b["graph"], b["tables"])
    assert _run(c, to, {"from": "g1"})["status"] == "done"
    g3 = next(s for s in _stage(c.get(f"/api/works/{to}/flow").json(), "g3")["steps"] if s["key"] == "retidy")
    assert g3["done"] and g3["skipped"], g3   # 기관 문서가 아직 없다 — 건너뜀
    A = _part(c, to, f"기관A_{J1}.hwpx", _edit_a, orgs=[J1])
    rec = _run(c, to, {"from": "g2", "to": "g3"})
    steps = [(s["key"], s["status"]) for s in rec["steps"]]
    assert rec["status"] == "done" and steps == [("link", "done"), ("plan", "done"), ("apply", "done"), ("retidy", "done")], (steps, rec["end"])
    assert seen["calls"] == [(to, True)] and GA._store(to)["filled"]["part"] == A   # 내용 반영이 표식을 찍고 정리는 취합본의 울타리 안에서
    assert "넣은 줄 2줄을 목적 문서의 템플릿 · 서식으로 맞췄습니다" in rec["steps"][-1]["text"]
    g3 = next(s for s in _stage(c.get(f"/api/works/{to}/flow").json(), "g3")["steps"] if s["key"] == "retidy")
    assert g3["done"] and not g3.get("skipped"), g3
    rec = _run(c, to, {"from": "g3", "only": "retidy"})
    assert [(s["key"], s["status"]) for s in rec["steps"]] == [("retidy", "nothing")] and len(seen["calls"]) == 1   # 그 반영 뒤에 이미 했다 — 할 것 없음
