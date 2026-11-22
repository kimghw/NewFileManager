"""도구 · 에이전트에 적어 두는 내용(spec_에이전트 ② §6 · 화면 spec_워크플로우 ② §18-16) — 저장(도구 공통 · 이 워크플로우 전용 + 에이전트에만) · 프롬프트 끝에 붙이기(llm.call) ·
지금 워크플로우 · 지금 도는 줄의 맥락(스레드로 넘기기) · 줄마다 쓰는 에이전트 · 작업 진행 에이전트의 요약 · API · 미들웨어. conftest 가 NFM_AGENT_NOTES 를 시험마다 임시 파일로 돌린다."""
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_notes as N
from app import agent_notes_api as NA
from app import agent_settings as S
from app import agents as A
from app import custom_tasks, custom_tasks_api, llm, server, workflow
from app import workflow_state as WS

EMPTY = {"version": 0, "tools": {}, "jobTools": {}, "all": {}, "jobs": {}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.delenv("NFM_LLM_MODEL_FORCE", raising=False)
    S.reset_runs()
    yield
    S.reset_runs()


def _relay(name="내 이관"):
    return custom_tasks.create({"name": name, "source": "plan", "target": "report", "assign": {"source": ["stage_review"], "target": list(custom_tasks.STAGES)}}, [])


def test_store_keeps_general_and_per_workflow_texts_apart():
    assert N.load() == EMPTY and N.get("merge_links") == "" and N.part("merge_links") == ""
    assert N.save("merge_links", "  표 머리의 단위를 본다  \r\n둘째 줄  ") == {"version": 1, "text": "표 머리의 단위를 본다\n둘째 줄"}
    assert N.save("merge_links", "3차년도만 잇는다", job="u_1234abcd")["version"] == 2 and N.path().is_file()
    assert N.get("merge_links") == "표 머리의 단위를 본다\n둘째 줄" and N.get("merge_links", "u_1234abcd") == "3차년도만 잇는다" and N.get("merge_links", "plan_merge") == ""
    assert N.get("merge_gaps") == "" and N.load()["jobs"] == {"u_1234abcd": {"merge_links": "3차년도만 잇는다"}}
    with pytest.raises(N.Stale):
        N.save("merge_links", "x", expect=0)
    with pytest.raises(KeyError):
        N.save("nope", "x")
    for bad in (3, "가" * (N.TEXT_MAX + 1)):
        with pytest.raises(ValueError):
            N.save("merge_links", bad)
    with pytest.raises(ValueError):
        N.save("merge_links", "x", job="Bad Key")
    assert N.save("merge_links", "", job="u_1234abcd") == {"version": 3, "text": ""} and N.load()["jobs"] == {}   # 빈 글 = 지움(빈 워크플로우 칸도 없앤다)
    N.save("gather", "가", job="u_1234abcd")
    N.save("merge_gaps", "나", job="u_1234abcd")
    assert N.forget_job("u_1234abcd") == 2 and N.load()["jobs"] == {} and N.forget_job("u_1234abcd") == 0 and N.get("merge_links")   # 워크플로우를 지우면 전용 글만 — 범용은 남는다


def test_broken_file_and_memory_mode(monkeypatch):
    N.path().write_text("{not json", encoding="utf-8")
    assert N.load() == EMPTY and N.attach("P", "merge-llm") == ("P", None)
    N.path().write_text('{"version": 4, "all": {"merge_links": "가", "ghost": "x", "gather": 3, "doc_agent": "  "}, "jobs": {"Bad Key": {"gather": "x"}, "u_1": {"gather": "나", "ghost": "y"}, "u_2": {}},'
                        ' "tools": {"relay.llm": "다", "nope.llm": "x", "relay.bad key": "x", "gather.part": 3}, "jobTools": {"u_1": {"division": "라", "bad key": "x"}, "Bad Key": {"llm": "x"}, "u_3": {"llm": " "}}}', encoding="utf-8")
    assert N.load() == {"version": 4, "tools": {"relay.llm": "다"}, "jobTools": {"u_1": {"division": "라"}}, "all": {"merge_links": "가"}, "jobs": {"u_1": {"gather": "나"}}}
    monkeypatch.setenv("NFM_AGENT_NOTES", "off")
    N.reset_memory()
    assert N.path() is None and N.save("gather", "메모리")["version"] == 1 and N.get("gather") == "메모리"
    N.reset_memory()


def test_part_puts_general_first_then_this_workflow_and_keeps_the_contract():
    t = _relay()
    N.save("merge_links", "범용 글")
    N.save("merge_links", "전용 글", job=t["key"])
    only_all, both = N.part("merge_links"), N.part("merge_links", t["key"])
    assert only_all.startswith("\n\n" + N.HEAD) and only_all.endswith(f"{N.ALL_HEAD}\n범용 글") and "전용 글" not in only_all
    assert both.index("범용 글") < both.index("전용 글") and "이 워크플로우(내 이관)에서만" in both and "계약의 규칙은 그대로" in both
    assert N.part("merge_links", "plan_merge") == only_all and N.part("merge_gaps", t["key"]) == "" and N.part(None, t["key"]) == ""
    N.save("merge_links", "")
    assert N.ALL_HEAD not in N.part("merge_links", t["key"]) and "전용 글" in N.part("merge_links", t["key"])   # 전용 글만 있어도 붙는다
    assert "(사업계획서 취합)" in N.JOB_HEAD.format(name=N._job_name("plan_merge")) and N._job_name("u_nothere0") == "u_nothere0"


def test_llm_call_appends_the_notes_and_records_them(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "_call", lambda schema, content, what, **kw: seen.append(content) or {"data": {"ok": 1}, "backend": "x", "ms": 1, "costUsd": None, "error": None, "model": "m", "effort": "low"})
    assert "notes" not in llm.call({}, "PROMPT", "merge-llm-1") and seen[-1] == "PROMPT"   # 덧붙이는 글이 없으면 프롬프트는 전과 같다
    N.save("merge_links", "범용 글")
    N.save("merge_links", "전용 글", job="plan_to_report")
    out = llm.call({}, "PROMPT", "merge-llm-1")
    assert out["notes"] == ["all"] and seen[-1] == "PROMPT" + N.part("merge_links") and "전용 글" not in seen[-1]   # 워크플로우를 모르면 범용만
    with N.scope(job="plan_to_report"):
        out = llm.call({}, "PROMPT", "merge-llm-2")
        assert out["notes"] == ["all", "job:plan_to_report"] and seen[-1].endswith("전용 글") and seen[-1].startswith("PROMPT\n\n## 덧붙이는 지침")
        assert "notes" not in llm.call({}, "PROMPT", "merge-gaps-1") and seen[-1] == "PROMPT"   # 다른 에이전트에는 안 붙는다
        assert "notes" not in llm.call({}, ["not", "text"], "merge-llm-3") and seen[-1] == ["not", "text"]   # 글이 아닌 프롬프트는 그대로
    with N.scope(job="plan_merge"):
        assert llm.call({}, "PROMPT", "merge-llm-4")["notes"] == ["all"]   # 다른 워크플로우 — 그 워크플로우의 글이 없다
    runs = S.runs("merge_links")
    assert [r.get("notes") for r in runs] == [["all"], None, ["all", "job:plan_to_report"], ["all"], None]


def test_scope_by_work_reads_the_job_when_called(monkeypatch):
    from app import works
    jobs = {"aaaaaaaaaaaa": {"task": {"job": "plan_merge"}}, "bbbbbbbbbbbb": {"task": {}}}
    monkeypatch.setattr(works, "work", lambda wid: jobs.get(wid))
    assert N.job_now() is None
    with N.scope(work="aaaaaaaaaaaa"):
        assert N.job_now() == "plan_merge"
        jobs["aaaaaaaaaaaa"]["task"]["job"] = "plan_to_report"   # 부를 때 읽는다 — 그 사이 워크플로우를 바꿨으면 바꾼 것
        assert N.job_now() == "plan_to_report"
        with N.scope(job="u_1234abcd"):
            assert N.job_now() == "u_1234abcd"
        assert N.job_now() == "plan_to_report"
    for wid in ("bbbbbbbbbbbb", "cccccccccccc"):
        with N.scope(work=wid):
            assert N.job_now() is None
    monkeypatch.setattr(works, "work", lambda wid: 1 / 0)
    with N.scope(work="aaaaaaaaaaaa"):
        assert N.job_now() is None and N.attach("P", "merge-llm") == ("P", None)   # 작업을 못 읽어도 호출은 돈다


def test_new_threads_need_carry_and_ask_all_carries(monkeypatch):
    got = {}

    def note(key):
        got[key] = N.job_now()

    with N.scope(job="plan_merge"):
        plain, kept, fixed = threading.Thread(target=note, args=("plain",)), threading.Thread(target=N.carry(note), args=("kept",)), threading.Thread(target=N.scoped(note, "u_1234abcd"), args=("fixed",))
        many = N.carry(note)
        more = [threading.Thread(target=many, args=(f"m{i}",)) for i in range(6)]   # 같은 함수를 여러 스레드가 함께 불러도 된다
        for t in (plain, kept, fixed, *more):
            t.start()
        for t in (plain, kept, fixed, *more):
            t.join()
    assert got["plain"] is None and got["kept"] == "plan_merge" and got["fixed"] == "u_1234abcd" and {got[f"m{i}"] for i in range(6)} == {"plan_merge"}
    N.save("gather", "전용", job="plan_merge")
    seen = []
    monkeypatch.setattr(llm, "_call", lambda schema, content, what, **kw: seen.append(content) or {"data": {}, "backend": "x", "ms": 1, "costUsd": None, "error": None, "model": "m", "effort": "low"})
    with N.scope(job="plan_merge"):
        res = llm.ask_all([{"schema": {}, "content": f"P{i}", "what": f"gather-llm-{i}"} for i in range(5)])
    assert all(r["notes"] == ["job:plan_merge"] for r in res) and sorted(s[:2] for s in seen) == [f"P{i}" for i in range(5)] and all(s.endswith("전용") for s in seen)
    assert "notes" not in llm.ask_all([{"schema": {}, "content": "P", "what": "gather-llm-9"}])[0]   # 맥락 밖


def test_lines_cover_every_unit_the_compose_form_offers(monkeypatch):
    L = NA.lines()
    assert set(L) == {"relay", "gather", "single"}
    g_units, _ = custom_tasks_api.gather_units()
    s_units, _ = custom_tasks_api.single_units()
    for fam, units in (("relay", custom_tasks_api.units()), ("gather", g_units), ("single", s_units)):
        for u in units:
            if u["key"] == "hand":   # 사람이 하는 일 — 등록부의 줄이 아니다(에이전트 · 도구 없음)
                continue
            assert u["key"] in L[fam], (fam, u["key"])
    ids = {a for box in L.values() for row in box.values() for a in row["agents"]}
    assert ids <= set(A.BY_ID) and {"merge_links", "merge_gaps", "merge_table_map", "gather", "heading_types", "heading_tables", "tpl_agent", "div_review"} <= ids
    assert L["relay"]["llm"]["agents"] == ["merge_links"] and L["gather"]["llm"]["agents"] == ["gather"] and L["relay"]["apply"]["agents"] == []   # 같은 key 도 틀마다 다르다
    assert L["relay"]["headsLlm"]["agents"] == list(workflow._ANALYSIS_LLM_AGENTS) and L["single"]["tablesLlm"]["agents"] == ["heading_tables"]
    assert all(t["id"] and t["name"] for box in L.values() for row in box.values() for t in row["tools"]) and L["relay"]["heads"]["tools"][0]["name"] == "헤딩 추출"
    for u in custom_tasks_api.units():   # LLM 을 부르는 줄(유료)은 에이전트가 있다 — 열이 「에이전트를 쓰지 않습니다」 라고 틀리게 말하지 않게
        if u["paid"]:
            assert L["relay"][u["key"]]["agents"], u["key"]
    ag = NA._agents()
    assert set(ag) == set(A.BY_ID) and ag["tpl_agent"]["parts"] == ["skill"] and ag["merge_links"]["parts"] == ["merge", "job", "form"] and ag["merge_links"]["no"] == "09"


def test_agent_detail_lists_the_notes_after_the_data():
    t = _relay("이관 둘")
    N.save("merge_links", "범용 글")
    N.save("merge_links", "전용 글", job=t["key"])
    N.save("merge_links", "취합 전용", job="plan_merge")
    notes = [p for p in A.detail("merge_links")["prompt"] if p["kind"] == "note"]
    assert [p["title"] for p in notes] == ["덧붙이는 글 — 범용(모든 워크플로우)", "덧붙이는 글 — 「이관 둘」 전용", "덧붙이는 글 — 「사업계획서 취합」 전용"]
    assert notes[0]["editable"] and notes[0]["custom"] and notes[0]["builtin"] and notes[0]["text"] == "범용 글" and notes[0]["version"] == 3 and notes[0]["api"] == "/api/agent-notes/merge_links"
    assert [(p["editable"], p["text"], p["name"]) for p in notes[1:]] == [(False, "전용 글", t["key"]), (False, "취합 전용", "plan_merge")]
    assert [p["kind"] for p in A.detail("merge_gaps")["prompt"]][-2:] == ["data", "note"] and not A.detail("merge_gaps")["prompt"][-1]["custom"]


def test_api_roundtrip_and_delete_forgets_the_workflow_notes():
    c = TestClient(server.app, raise_server_exceptions=False)
    assert c.get("/api/agent-notes").json() == {**EMPTY, "max": N.TEXT_MAX}
    L = c.get("/api/agent-notes/lines").json()
    assert set(L["families"]) == {"relay", "gather", "single"} and len(L["agents"]) == 22 and L["agents"]["gather"]["name"] == "취합 검토"
    key = c.post("/api/tasks", json={"name": "전용 글 시험", "source": "plan", "target": "report", "assign": {"source": ["stage_review"], "target": list(custom_tasks.STAGES)}}).json()["task"]["key"]
    r = c.put("/api/agent-notes/merge_links", json={"text": "범용 글", "version": 0})
    assert r.status_code == 200 and r.json() == {"aid": "merge_links", "job": None, "text": "범용 글", "version": 1}
    r = c.put("/api/agent-notes/merge_links", json={"text": "전용 글", "job": key, "version": 1})
    assert r.status_code == 200 and r.json()["job"] == key and r.json()["version"] == 2
    assert c.put("/api/agent-notes/merge_links", json={"text": "붙박이에도", "job": "plan_merge"}).status_code == 200   # 붙박이 워크플로우에도 적는다
    assert c.put("/api/agent-notes/merge_links", json={"text": "x", "version": 0}).status_code == 409
    assert c.put("/api/agent-notes/merge_links", json={"text": "x", "job": "u_00000000"}).status_code == 404   # 없는 워크플로우
    assert c.put("/api/agent-notes/merge_links", json={"text": "x", "job": "Bad Key"}).status_code == 400
    assert c.put("/api/agent-notes/nope", json={"text": "x"}).status_code == 404
    assert c.put("/api/agent-notes/merge_links", json={"text": "가" * (N.TEXT_MAX + 1)}).status_code == 400 and c.put("/api/agent-notes/merge_links", json={"text": 3}).status_code == 400
    assert c.put("/api/agent-notes/merge_links", json={"text": "x", "version": "1"}).status_code == 400
    got = c.get("/api/agent-notes").json()
    assert got["all"] == {"merge_links": "범용 글"} and got["jobs"] == {key: {"merge_links": "전용 글"}, "plan_merge": {"merge_links": "붙박이에도"}}
    d = c.get("/api/agents/merge_links").json()["prompt"]
    assert [p["text"] for p in d if p["kind"] == "note"] == ["범용 글", "전용 글", "붙박이에도"]
    assert c.delete("/api/agent-notes/merge_links", params={"job": "plan_merge"}).json()["text"] == "" and "plan_merge" not in c.get("/api/agent-notes").json()["jobs"]
    assert c.delete(f"/api/tasks/{key}").status_code == 200 and c.get("/api/agent-notes").json()["jobs"] == {}   # 워크플로우를 지우면 그 전용 글도
    assert c.delete("/api/agent-notes/merge_links").json()["text"] == "" and c.get("/api/agent-notes").json()["all"] == {}   # 범용 글 지우기(에이전트 설정의 「기본으로 되돌리기」)


def test_middleware_scopes_a_request_by_the_work_in_its_path(monkeypatch):
    from app import works
    monkeypatch.setattr(works, "work", lambda wid: {"task": {"job": "plan_merge"}} if wid == "0123456789ab" else None)
    app = FastAPI()
    app.add_middleware(NA.Scope)

    @app.get("/api/docs/{doc_id}/x")
    def one(doc_id: str):   # 동기 끝점 — 일꾼 스레드에서 돈다(맥락의 사본)
        return {"job": N.job_now(), "thread": N.carry(N.job_now)()}

    @app.get("/api/works/{wid}/y")
    async def two(wid: str):
        return {"job": N.job_now()}

    @app.get("/api/other")
    def three():
        return {"job": N.job_now()}

    c = TestClient(app)
    assert c.get("/api/docs/0123456789ab/x").json() == {"job": "plan_merge", "thread": "plan_merge"} and c.get("/api/works/0123456789ab/y").json() == {"job": "plan_merge"}
    assert c.get("/api/docs/ffffffffffff/x").json()["job"] is None and c.get("/api/other").json() == {"job": None} and N.job_now() is None
    assert any(m.cls is NA.Scope for m in server.app.user_middleware)   # 서버에 걸려 있다


def test_threads_that_lead_to_llm_calls_carry_the_scope():
    """LLM 호출로 이어지는 스레드 · 실행기를 만드는 곳은 지금 워크플로우를 넘긴다(agent_notes.carry · scoped) — 새로 만든 곳이 빠지면 전용 글이 조용히 안 붙는다."""
    import re
    from pathlib import Path
    root = Path(__file__).parents[1] / "app"
    need = {"heading_runs.py": 2, "analysis_llm.py": 3, "verify.py": 1, "server.py": 2, "llm.py": 1}   # 파일 → 넘기는 곳의 수(가장 적게)
    for name, n in need.items():
        text = (root / name).read_text(encoding="utf-8")
        assert len(re.findall(r"agent_notes\.(?:carry|scoped)\(", text)) >= n, name
    flow = (root / "workflow_exec.py").read_text(encoding="utf-8")   # 실행 층은 앱 코드를 더 가져오지 않는다(tests/test_workflow_units.py) — 표준 contextvars 로 맥락의 사본을 넘긴다(실행 스레드 · 옆 줄 스레드)
    assert len(re.findall(r"threading\.Thread\(target=contextvars\.copy_context\(\)\.run", flow)) == 2 and len(re.findall(r"threading\.Thread\(", flow)) == 2


def test_flow_run_thread_sees_the_scope_of_the_request_that_started_it(monkeypatch):
    """서버 실행기의 실행 스레드 · 옆 줄 스레드는 시작한 요청의 맥락에서 돈다 — 그 실행의 LLM 호출에 그 워크플로우 전용 글이 붙는다."""
    from app import workflow_exec as X
    from app import works
    monkeypatch.setattr(works, "work", lambda wid: {"task": {"job": "plan_merge"}})
    got = []

    class Rec(dict):
        pass

    class FakeRun:
        rec = Rec(n=1)
        threads = set()
        working = set()

    with N.scope(work="0123456789ab"):
        out = X._lanes(FakeRun(), [lambda: got.append(N.job_now()) or "a", lambda: got.append(N.job_now()) or "b", lambda: got.append(N.job_now()) or "c"])
    assert out == ["a", "b", "c"] and got == ["plan_merge"] * 3


# ---------------------------------------------------------------- 도구에 적어 두는 내용 — 도구 공통 · 이 워크플로우 전용(2026-11-20 사용자 「공통적으로 그 도구에서 쓰는 내용과 워크플로우마다 사용되는 내용 2가지」)
def test_tool_notes_are_kept_per_tool_and_per_workflow():
    assert N.save_tool("relay", "division", "  기관 이름은 문서에 적힌 그대로  ") == {"version": 1, "text": "기관 이름은 문서에 적힌 그대로"}
    assert N.save_tool("relay", "division", "이 문서는 차년도가 없다", job="u_1234abcd")["version"] == 2
    N.save_tool("gather", "division", "취합의 구성 반영")   # 같은 줄 key 도 틀마다 다른 도구
    assert N.get_tool("relay", "division") == "기관 이름은 문서에 적힌 그대로" and N.get_tool("relay", "division", "u_1234abcd") == "이 문서는 차년도가 없다"
    assert N.get_tool("gather", "division") == "취합의 구성 반영" and N.get_tool("single", "apply") == "" and N.get_tool("relay", "division", "plan_merge") == ""
    assert N.load()["tools"] == {"relay.division": "기관 이름은 문서에 적힌 그대로", "gather.division": "취합의 구성 반영"} and N.load()["jobTools"] == {"u_1234abcd": {"division": "이 문서는 차년도가 없다"}}
    for bad in (("nope", "division", "x", None), ("relay", "bad key", "x", None), ("relay", "division", 3, None), ("relay", "division", "x", "Bad Key"), ("relay", "division", "가" * (N.TEXT_MAX + 1), None)):
        with pytest.raises(ValueError):
            N.save_tool(bad[0], bad[1], bad[2], job=bad[3])
    with pytest.raises(N.Stale):
        N.save_tool("relay", "division", "x", expect=0)
    N.save("merge_links", "에이전트 전용", job="u_1234abcd")
    assert N.forget_job("u_1234abcd") == 2 and N.load()["jobTools"] == {} and N.load()["jobs"] == {} and N.get_tool("relay", "division")   # 워크플로우를 지우면 그 전용 글만(도구 · 에이전트) — 도구 공통은 남는다
    assert N.save_tool("relay", "division", "")["text"] == "" and "relay.division" not in N.load()["tools"]


def test_part_goes_from_wide_to_narrow_agent_tool_workflow():
    t = _relay("도구 글 시험")
    N.save("merge_links", "에이전트 범용")
    N.save_tool("relay", "llm", "도구 공통")
    N.save_tool("relay", "llm", "도구 전용", job=t["key"])
    N.save("merge_links", "에이전트 전용", job=t["key"])
    N.save_tool("relay", "division", "구성 반영 공통")   # 에이전트가 없는 도구
    N.save_tool("relay", "gaps", "다른 도구")
    got, tags = N._part("merge_links", t["key"], "relay", "llm")   # 서버 실행기가 그 줄을 도는 중 — 그 도구의 글만
    order = [got.index(x) for x in ("에이전트 범용", "도구 공통", "도구 전용", "에이전트 전용")]
    assert order == sorted(order) and "도구 「자리 연결 LLM 검토」 — 이 도구를 쓰는 모든 워크플로우에서" in got and "도구 「자리 연결 LLM 검토」 — 이 워크플로우(도구 글 시험)에서만" in got
    assert tags == ["all", "tool:relay.llm", f"jobtool:{t['key']}/llm", f"job:{t['key']}"] and "다른 도구" not in got and "구성 반영 공통" not in got
    assert N._part("merge_links", t["key"], "relay") == (got, tags)   # 줄을 모름(문서 화면에서 손으로) — 그 틀에서 이 에이전트를 쓰는 도구(= 자리 연결 LLM 검토 하나)
    both = N._part("heading_types", t["key"], "relay")   # 한 에이전트를 두 도구가 쓴다(LLM 검증·보완 · 다시 문서 검토(LLM)) — 손으로 돌릴 때는 둘 다
    assert both == ("", [])
    N.save_tool("relay", "headsLlm", "검증 공통")
    N.save_tool("relay", "reheadsLlm", "다시 검토 전용", job=t["key"])
    both = N._part("heading_types", t["key"], "relay")
    assert both[1] == ["tool:relay.headsLlm", f"jobtool:{t['key']}/reheadsLlm"] and N._part("heading_types", t["key"], "relay", "headsLlm")[1] == ["tool:relay.headsLlm"]
    assert N._part("merge_links", t["key"], "relay", "division")[1] == ["all", "tool:relay.division", f"job:{t['key']}"]   # 실행기가 도는 줄이 먼저다(그 줄이 부른 호출)
    assert N._part("merge_links", t["key"])[1] == ["all", f"job:{t['key']}"] and N._part("merge_links", None, "relay", "llm")[1] == ["all", "tool:relay.llm"]   # 틀을 모르면 도구의 글 없음 · 워크플로우를 몰라도 도구 공통은
    assert N._part("merge_links", "plan_merge", "gather")[1] == ["all"] and N._part("doc_agent", t["key"], "relay") == ("", [])


def test_attach_reads_the_running_line_or_the_family_of_the_workflow(monkeypatch):
    t = _relay("맥락 시험")
    N.save_tool("relay", "llm", "도구 공통")
    N.save_tool("relay", "llm", "도구 전용", job=t["key"])
    N.save_tool("relay", "division", "구성 공통")
    assert N.attach("P", "merge-llm-1") == ("P", None) and N.family_of(t["key"])[0] == "relay" and N.family_of("plan_merge")[0] == "gather" and N.family_of("doc_edit") == ("", ())
    assert "llm" in N.family_of(t["key"])[1] and N.family_of("u_nothere0") == ("", ()) and N.line_now() is None
    with N.scope(job=t["key"]):   # 문서 화면에서 손으로 — 그 워크플로우의 틀에서 이 에이전트를 쓰는 도구
        text, tags = N.attach("P", "merge-llm-1")
        assert tags == ["tool:relay.llm", f"jobtool:{t['key']}/llm"] and text.startswith("P\n\n## 덧붙이는 지침") and text.endswith("도구 전용")
        token = WS.LINE.set(("relay", "division"))   # 서버 실행기가 「프로젝트 구성 반영」 줄을 도는 중 — 그 줄의 글
        try:
            assert N.line_now() == ("relay", "division") and N.attach("P", "merge-llm-1")[1] == ["tool:relay.division"]
            assert N.carry(N.line_now)() == ("relay", "division")   # 새 스레드로도 들고 간다
        finally:
            WS.LINE.reset(token)
    with N.scope(job="plan_to_report"):   # 붙박이 이관 — 같은 틀이라 도구 공통은 붙고 그 워크플로우의 전용 글은 없다
        assert N.attach("P", "merge-llm-1")[1] == ["tool:relay.llm"]
    with N.scope(job="plan_merge"):   # 다른 틀(취합) — 이관의 도구에 적은 글은 안 붙는다
        assert N.attach("P", "gather-llm-1") == ("P", None)
    seen = []
    monkeypatch.setattr(llm, "_call", lambda schema, content, what, **kw: seen.append(content) or {"data": {}, "backend": "x", "ms": 1, "costUsd": None, "error": None, "model": "m", "effort": "low"})
    with N.scope(job=t["key"]):
        out = llm.call({}, "PROMPT", "merge-llm-7")
    assert out["notes"] == ["tool:relay.llm", f"jobtool:{t['key']}/llm"] and seen[-1].endswith("도구 전용") and S.runs("merge_links")[0]["notes"] == out["notes"]


def test_executor_marks_the_line_it_runs(monkeypatch):
    """서버 실행기가 줄의 처리 함수를 부르는 동안 「지금 도는 줄」 이 걸린다(그 줄이 부르는 LLM 호출에 그 도구의 글) — 끝나면 풀린다 · 처리 함수가 예외를 내도."""
    from app import workflow_exec as X
    got = []

    class Run:
        task = WS.definition("plan_to_report")

    monkeypatch.setattr(X, "_handler", lambda task, line: (lambda run, gid, ln: got.append(N.line_now()) or ("done", "")))
    assert X._line(Run(), "g1", {"unit": {"key": "llm", "kind": "auto"}}) == ("done", "") and got == [("relay", "llm")] and N.line_now() is None
    Run.task = WS.definition("plan_merge")
    X._line(Run(), "g1", {"unit": {"key": "llm", "kind": "auto"}})
    assert got[-1] == ("gather", "llm")

    def boom(run, gid, ln):
        raise RuntimeError("x")
    monkeypatch.setattr(X, "_handler", lambda task, line: boom)
    with pytest.raises(RuntimeError):
        X._line(Run(), "g1", {"unit": {"key": "plan", "kind": "auto"}})
    assert N.line_now() is None
    import re
    from pathlib import Path
    text = (Path(X.__file__)).read_text(encoding="utf-8")
    assert len(re.findall(r"_handler\(run\.task, line\)\(", text)) == 1 and len(re.findall(r"= _line\(run, gid, line\)", text)) == 2   # 처리 함수는 _line 을 지나서만 부른다(줄을 걸지 않고 부르는 곳이 없다)


def test_work_guide_reads_what_was_written_for_each_tool(monkeypatch):
    """에이전트 없이 스크립트 · 사람이 하는 도구에 적은 내용은 작업 진행 에이전트가 읽는다 — 그 워크플로우의 정의에 있는 줄의 것만 · 정의의 차례 · 긴 글은 줄여서."""
    t = _relay("안내 시험")
    assert N.digest(t["key"]) == "" and N.digest(None) == ""
    N.save_tool("relay", "division", "구성 반영 공통")
    N.save_tool("relay", "division", "사업계획서는 단계 · 차년도 · 기관을 준다", job=t["key"])
    N.save_tool("relay", "config", "가" * (N.DIGEST_MAX + 50), job=t["key"])
    N.save_tool("relay", "llm", "연결 공통")
    N.save_tool("gather", "frame", "취합의 도구")   # 다른 틀
    d = N.digest(t["key"])
    assert d.startswith("\n\n## 도구마다 사용자가 적어 둔 내용 — 이 워크플로우(안내 시험)") and "취합의 도구" not in d
    order = [d.index(x) for x in ("도구 「프로젝트 구성 추출」", "도구 「프로젝트 구성 반영」", "도구 「자리 연결 LLM 검토」")]
    assert order == sorted(order) and "- 공통: 구성 반영 공통\n- 이 워크플로우: 사업계획서는 단계 · 차년도 · 기관을 준다" in d and "가" * N.DIGEST_MAX + " …(줄임)" in d and "가" * (N.DIGEST_MAX + 1) not in d
    only = custom_tasks.create({"name": "검토만", "source": "plan", "target": "report", "assign": {"source": ["stage_review"], "target": ["stage_review"]}}, [])
    assert N.digest(only["key"]) == ""   # 그 정의에 없는 줄(구성 반영 · 자리 연결)의 글은 싣지 않는다
    seen = []
    monkeypatch.setattr(llm, "_call", lambda schema, content, what, **kw: seen.append(content) or {"data": {}, "backend": "x", "ms": 1, "costUsd": None, "error": None, "model": "m", "effort": "low"})
    assert "notes" not in llm.call({}, "GUIDE", "work-guide") and seen[-1] == "GUIDE"   # 워크플로우를 모르면(첫 화면) 그대로
    with N.scope(job=t["key"]):
        out = llm.call({}, "GUIDE", "work-guide")
        assert out["notes"] == ["tools-digest"] and seen[-1] == "GUIDE" + d
        N.save("work_guide", "설명은 짧게")
        assert llm.call({}, "GUIDE", "work-guide")["notes"] == ["all", "tools-digest"] and seen[-1].index("설명은 짧게") < seen[-1].index("도구마다 사용자가 적어 둔 내용")
    with N.scope(job="doc_edit"):   # 틀이 없는 워크플로우
        assert llm.call({}, "GUIDE", "work-guide")["notes"] == ["all"]


def test_tool_notes_api_and_the_agents_page_lists_them():
    c = TestClient(server.app, raise_server_exceptions=False)
    key = c.post("/api/tasks", json={"name": "도구 글 API", "source": "plan", "target": "report", "assign": {"source": ["stage_review"], "target": list(custom_tasks.STAGES)}}).json()["task"]["key"]
    L = c.get("/api/agent-notes/lines").json()["families"]
    assert L["relay"]["division"]["name"] == "프로젝트 구성 반영" and L["relay"]["division"]["agents"] == [] and L["relay"]["llm"]["name"] == "자리 연결 LLM 검토"
    r = c.put("/api/agent-notes/tools/relay/division", json={"text": "구성 반영 공통", "version": 0})
    assert r.status_code == 200 and r.json() == {"family": "relay", "unit": "division", "job": None, "text": "구성 반영 공통", "version": 1}
    r = c.put("/api/agent-notes/tools/relay/division", json={"text": "이 워크플로우의 구성", "job": key, "version": 1})
    assert r.status_code == 200 and r.json()["job"] == key and r.json()["version"] == 2
    assert c.put("/api/agent-notes/tools/relay/llm", json={"text": "연결 공통"}).status_code == 200 and c.put("/api/agent-notes/tools/relay/llm", json={"text": "붙박이 이관의 연결", "job": "plan_to_report"}).status_code == 200
    assert c.put("/api/agent-notes/tools/relay/llm", json={"text": "연결 전용", "job": key}).status_code == 200
    for url, body, code in (("/api/agent-notes/tools/relay/nope", {"text": "x"}, 404), ("/api/agent-notes/tools/nope/division", {"text": "x"}, 404), ("/api/agent-notes/tools/relay/hand", {"text": "x"}, 404),
                            ("/api/agent-notes/tools/relay/division", {"text": "x", "job": "plan_merge"}, 400), ("/api/agent-notes/tools/relay/division", {"text": "x", "job": "u_00000000"}, 404),
                            ("/api/agent-notes/tools/relay/division", {"text": "x", "job": "Bad Key"}, 400), ("/api/agent-notes/tools/relay/division", {"text": "x", "version": 0}, 409),
                            ("/api/agent-notes/tools/relay/division", {"text": 3}, 400), ("/api/agent-notes/tools/gather/division", {"text": "x", "job": key}, 400)):
        assert c.put(url, json=body).status_code == code, (url, body)
    got = c.get("/api/agent-notes").json()
    assert got["tools"] == {"relay.division": "구성 반영 공통", "relay.llm": "연결 공통"} and got["jobTools"] == {key: {"division": "이 워크플로우의 구성", "llm": "연결 전용"}, "plan_to_report": {"llm": "붙박이 이관의 연결"}}
    c.put("/api/agent-notes/merge_links", json={"text": "에이전트 범용"})
    notes = [p for p in c.get("/api/agents/merge_links").json()["prompt"] if p["kind"] == "note"]   # 에이전트 설정의 보내는 글 — 붙는 차례(넓은 것부터): 에이전트 범용 → 도구 공통 → 그 도구의 워크플로우 전용
    assert [p["title"] for p in notes] == ["덧붙이는 글 — 범용(모든 워크플로우)", "도구에 적어 둔 내용 — 「자리 연결 LLM 검토」 공통(이관형)", "도구에 적어 둔 내용 — 「자리 연결 LLM 검토」 · 「도구 글 API」 전용",
                                           "도구에 적어 둔 내용 — 「자리 연결 LLM 검토」 · 「사업계획서 → 연차보고서 이관」 전용"]
    assert [p["editable"] for p in notes] == [True, False, False, False] and [p["text"] for p in notes[1:]] == ["연결 공통", "연결 전용", "붙박이 이관의 연결"]
    assert c.delete("/api/agent-notes/tools/relay/llm", params={"job": "plan_to_report"}).json()["text"] == "" and "plan_to_report" not in c.get("/api/agent-notes").json()["jobTools"]
    assert c.delete(f"/api/tasks/{key}").status_code == 200 and c.get("/api/agent-notes").json()["jobTools"] == {}   # 워크플로우를 지우면 그 도구 전용 글도
    assert c.delete("/api/agent-notes/tools/relay/division").json()["text"] == "" and c.get("/api/agent-notes").json()["tools"] == {"relay.llm": "연결 공통"}

