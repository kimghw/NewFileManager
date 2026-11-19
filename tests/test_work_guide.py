"""작업 진행 에이전트(spec_작업에이전트) — app/work_guide.py(계약 · workflow.md 에서 절 자르기 · 답 검사 · 스크립트 답) · app/work_guide_api.py(진행 턴 · 카드의 끝 · 첫 화면).
LLM 은 부르지 않는다(끔 = 스크립트 답 · 켠 척할 때는 `work_guide.ask` 를 가짜로 바꾼다)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import agents, doc_agent, llm, server, works
from app import work_guide as G
from app import work_guide_api as API
from app import workflow as W

SAMPLES = Path(__file__).parents[1] / "samples"
SMALL = SAMPLES / "기술수요조사서.hwpx"
STEPS = [{"stage": "준비", "key": "open", "name": "문서 올리기 · 첫 분석", "state": "done", "text": "헤딩 ✓ · 표 ✓"},
         {"stage": "프로젝트 구성", "key": "values", "name": "프로젝트 구성 값 정하기", "state": "now", "text": "아직 확정하지 않음"},
         {"stage": "구조 반영", "key": "plan", "name": "변경 계획 보기", "state": "todo", "text": ""},
         {"stage": "구조 반영", "key": "apply", "name": "반영", "state": "todo", "text": ""}]
ACTS = [{"name": "config_read", "label": "문서에서 읽기", "does": "문서에 적힌 구성을 읽어 입력 칸에", "change": "none"},
        {"name": "config_set", "label": "프로젝트 구성 입력", "does": "값을 넣고 확정", "change": "store", "primary": True},
        {"name": "edit", "label": "편집 에이전트에 넘김", "does": "글·표 요청", "change": "none"}]
PLAN = [{"name": "plan", "label": "변경 계획 보기", "does": "바뀔 자리를 셉니다", "change": "none", "primary": True},
        {"name": "apply", "label": "반영", "does": "절·표 행·열을 맞춥니다", "change": "doc"}]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    doc_agent._MEMORY.clear()
    server.DOCS.clear()
    yield
    server.DOCS.clear()
    doc_agent._MEMORY.clear()


def _doc(c, job=None):
    r = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    if job:
        assert c.put(f"/api/works/{d}/task", json={"kind": "", "file": "plan", "job": job, "project": ""}).status_code == 200
    return d


def test_agent_is_registered_and_its_prompt_shows_the_workflow():
    a = agents.BY_ID["work_guide"]
    assert a["no"] == "19" and a["group"] == "문서 편집" and G.WHAT == "work-guide" and llm.EFFORTS and G.EFFORT in llm.EFFORTS
    kinds = [p["kind"] for p in agents.detail("work_guide")["prompt"]]
    assert kinds[:3] == ["contract", "contract", "workflow"] and kinds[-1] == "data"   # 할 일 프롬프트(job)는 jobs/ 폴더가 켜져 있을 때 그 사이에 붙는다
    wf = next(p for p in agents.detail("work_guide")["prompt"] if p["kind"] == "workflow")
    assert wf["source"] == "workflow.md" and wf["text"] == W.MD.read_text(encoding="utf-8") and not wf["editable"]
    assert any("work_guide" in s["agents"] for _, s in W.steps())   # 워크플로우 등록부에도 적혀 있다


def test_workflow_part_cuts_the_task_section_and_the_common_modules_it_uses():
    p = G.workflow_part("plan_fit")
    assert "## 한눈에" in p and "### 사업계획서 양식 표준화 — `plan_fit`" in p and "### 프로젝트 구성(구분 기준) — `division`" in p and "### 문서 올리기 · 첫 분석 — `intake`" in p
    assert "`plan_to_report`" not in p.split("## 한눈에", 1)[1].split("도구:", 1)[1]   # 다른 TASK 의 절은 없다(「한눈에」 표에는 이름이 있다)
    assert "### 서식 관리자(서식 보관함) — `styles`" not in p and len(p) < len(G.workflow_text())   # 그 TASK 가 안 쓰는 공통 모듈은 없다
    assert "### 표 도구 — `tables`" in p                                                                    # 양식 표준화 3단계(표 점검 · 서식 맞추기)가 쓴다 — spec_양식표준화 ② §1
    home = G.workflow_part(None)
    assert all(f"— `{t['job']}`" in home for t in W.TASKS) and "####" not in home and "받는 문서" in home   # TASK 마다 머리만(단계 묶음 앞까지)
    assert G.workflow_part("nope") == home
    # 참조 글(spec ② §8) — 작업 화면의 그 TASK 절은 TASK 문서(tasks/<job>.md): workflow.md 의 절과 같은 글 + 시작 점검 + 단계마다 조건
    assert G.task_doc_text("plan_fit") == W.task_md("plan_fit").read_text(encoding="utf-8") and G.task_doc_text("nope") == ""
    fit = W.BY_JOB["plan_fit"]
    assert "#### 시작 점검 — 시작할 때 저절로 확인하는 것" in p and "##### TASK 를 시작할 때" in p and "#### 단계마다 조건" in p and "  - 끝난 것으로 보는 때: " in p and "  - 안 맞으면: " in p
    assert all(s["does"] in p and s["done"] in p for g in fit["stages"] for s in g["steps"]) and all(c["does"] in p for c in fit["entry"])
    assert "만든 글" not in p.split("### 사업계획서 양식 표준화 — `plan_fit`", 1)[1].split("#### 시작 점검", 1)[0]   # 파일 머리의 알림(> 줄)은 싣지 않는다
    assert "시작 점검(시작할 때 저절로 확인하는 것): TASK 를 시작할 때 — 문서 형식" in home and "`tasks/plan_fit.md`" in home and "  - 안 맞으면: " not in home   # 첫 화면은 이름만


def test_agent_asks_for_logs_and_the_endpoint_reads_them(monkeypatch):
    """로그(spec ② §8) — 자료에 로그 목록 · 작업 기록의 끝 몇 줄이 실리고, 에이전트가 read 로 청하면 끝점이 읽어 logsRead 에 붙여 다시 부른다(두 번까지)."""
    assert G.SCHEMA["properties"]["read"]["items"]["required"] == ["log", "n", "find"] and "read" in G.SCHEMA["required"]
    assert G.reads_in({"read": [{"log": " work ", "n": 500, "find": "divisionPlan"}, {"log": "work", "n": 80, "find": "divisionPlan"}, {"log": ""}, "x", {"log": "server", "n": True, "find": 3}, {"log": "a"}, {"log": "b"}]}) \
        == [{"log": "work", "n": 80, "find": "divisionPlan"}, {"log": "server", "n": 30, "find": "3"}, {"log": "a", "n": 30, "find": ""}]   # 셋까지 · 같은 것은 한 번 · 줄 수는 1~80
    assert G.reads_in({"reply": ""}) == [] and G.reads_in(None) == []
    for text in (G.CONTRACT, G.HOME_CONTRACT):
        assert "[{log, n, find}]" in text and "{{" not in text
    c = TestClient(server.app)
    d = _doc(c, "plan_fit")
    seen = []

    def fake(data, job=None, *, home=False, call=None, timeout=120.0):
        seen.append({"logs": dict(data.get("logs") or {}), "read": [dict(r, lines=list(r.get("lines") or [])) for r in data.get("logsRead") or []], "prompt": G.content(data, job, home)})
        first = len(seen) == 1
        raw = {"reply": "" if first else "방금 문서를 올렸고 아직 반영한 적이 없습니다", "act": "", "ask": {"kind": "", "text": "", "options": []},
               "read": [{"log": "work", "n": 5, "find": ""}, {"log": "nope", "n": 5, "find": ""}] if first else [{"log": "server", "n": 5, "find": ""}]}
        return {"data": G.clean(raw, data["actions"]), "reads": G.reads_in(raw), "prompt": seen[-1]["prompt"], "response": raw, "call": {"backend": "api", "model": "m", "effort": "low", "ms": 7, "costUsd": 0.01, "error": None}}

    monkeypatch.setattr(llm, "status", lambda: {"available": True})
    monkeypatch.setattr(G, "ask", fake)
    t = c.post(f"/api/docs/{d}/agent/guide", json={"event": "say", "text": "아까 뭐 했지?", "steps": STEPS, "actions": PLAN}).json()["turn"]
    assert len(seen) == 3 and [s["logs"]["rounds"] for s in seen] == [2, 1, 0]                                 # 두 번 읽고, 셋째 부름에는 더 읽을 수 없다(청해도 읽지 않는다)
    assert [x["log"] for x in seen[0]["logs"]["index"]] == ["work", "peers", "verify", "agent", "zones", "llm", "server"] and any(" create " in line for line in seen[0]["logs"]["recent"])
    assert seen[0]["read"] == [] and [r["log"] for r in seen[1]["read"]] == ["work", "nope"] and seen[1]["read"][0]["lines"] and "그런 로그가 없습니다" in seen[1]["read"][1]["error"]
    assert [r["log"] for r in seen[2]["read"]] == ["work", "nope", "server"] and '"logsRead"' in seen[2]["prompt"] and '"logsRead"' not in seen[0]["prompt"]
    assert t["llm"] and t["reply"].startswith("방금 문서를 올렸고") and t["notes"][0].startswith("로그를 읽었습니다 — 작업 기록 ") and "서버 로그 " in t["notes"][0]
    assert t["call"]["ms"] == 21 and t["call"]["costUsd"] == 0.03 and t["call"]["rounds"] == 3                  # 다시 물은 호출의 시간 · 비용은 더한다
    full = c.get(f"/api/docs/{d}/agent/turns/{t['id']}").json()
    assert full["parts"][0]["text"] == seen[2]["prompt"]
    last = [e for e in works.events(d) if e["kind"] == "agentGuide"][-1]
    assert last["reads"] == ["work", "nope", "server"]
    # 첫 화면에는 작업이 없다 — 로그를 싣지도 읽지도 않는다
    seen.clear()
    c.post("/api/agent/guide", json={"files": [{"name": "사업계획서.hwpx"}]})
    assert len(seen) == 1 and seen[0]["logs"] == {} and '"logs"' not in seen[0]["prompt"].split("## 자료(JSON)", 1)[1]


def test_inputs_are_trimmed_to_the_contract():
    steps = G.steps_in(STEPS + [{"name": ""}, "x", {"name": "이상한 상태", "state": "weird"}])
    assert [s["state"] for s in steps] == ["done", "now", "todo", "todo", "todo"] and steps[0]["stage"] == "준비"
    acts = G.actions_in(ACTS + [{"name": "config_read"}, {"name": "나쁜 이름"}, {"name": "run:map", "change": "doc", "paid": True}, None])
    assert [a["name"] for a in acts] == ["config_read", "config_set", "edit", "run:map"] and acts[1]["primary"] and acts[3] == {"name": "run:map", "label": "run:map", "does": "", "change": "doc", "paid": True, "primary": False, "key": ""}
    keyed = G.actions_in([{"name": "apply", "change": "doc", "key": "plan:p1:7"}])
    assert keyed[0]["key"] == "plan:p1:7"                                                                      # key = 그 카드가 가리키는 계획(화면이 「진행」 때 견준다)
    assert '"key"' not in G.content({"event": "start", "actions": keyed}, "plan_fit") and "plan:p1:7" not in G.content({"event": "start", "actions": keyed}, "plan_fit")   # LLM 에는 안 보낸다
    assert G.facts_in({"config": "1단계(1–3차년도)", "confirmed": False, "n": 3, "deep": {"x": 1}, "none": None}) == {"config": "1단계(1–3차년도)", "confirmed": False, "n": 3}
    assert G.talk_in([{"who": "me", "text": "양식 맞추기"}, {"who": "x", "text": "네"}, {"text": ""}], 5) == [{"who": "me", "text": "양식 맞추기"}, {"who": "agent", "text": "네"}]


def test_clean_keeps_only_actions_that_were_sent():
    acts = G.actions_in(ACTS)
    ok = G.clean({"reply": "읽겠습니다", "act": "config_read", "ask": {"kind": "", "text": "", "options": []}}, acts)
    assert ok == {"reply": "읽겠습니다", "act": "config_read", "ask": None, "notes": []}
    bad = G.clean({"reply": "지우겠습니다", "act": "delete_all", "ask": {"kind": "", "text": "", "options": []}}, acts)
    assert bad["act"] == "" and "delete_all" in bad["notes"][0]
    both = G.clean({"reply": "", "act": "config_read", "ask": {"kind": "config", "text": "값을 넣어 주세요", "options": []}}, acts)
    assert both["act"] == "" and both["ask"] == {"kind": "config", "text": "값을 넣어 주세요", "options": []}   # 물을 것이 먼저
    no_cfg = G.clean({"reply": "", "act": "", "ask": {"kind": "config", "text": "", "options": []}}, G.actions_in(PLAN))
    assert no_cfg["ask"] is None and no_cfg["notes"]
    one = G.clean({"reply": "", "act": "", "ask": {"kind": "choice", "text": "?", "options": [{"value": "plan", "label": "계획", "desc": ""}]}}, G.actions_in(PLAN))
    assert one["ask"] is None                                                                                  # 선택지 하나는 질문이 아니다
    assert G.clean("x", acts) is None and G.clean({"reply": 3}, acts) is None


def test_fallback_explains_and_proposes_the_primary_action():
    base = {"task": {"job": "plan_fit", "name": "사업계획서 양식 표준화"}, "steps": G.steps_in(STEPS)}
    start = G.fallback({**base, "event": "start", "actions": G.actions_in(ACTS)})
    assert "「사업계획서 양식 표준화」" in start["reply"] and "4개 가운데 1개" in start["reply"] and start["act"] == "" and start["ask"]["kind"] == "config"   # 값이 필요한 행동은 질문 카드로
    nxt = G.fallback({**base, "event": "result", "text": "프로젝트 구성을 확정했습니다", "ok": True, "act": "config_set", "actions": G.actions_in(PLAN)})
    assert nxt["act"] == "plan" and "하겠습니다" in nxt["reply"] and nxt["reply"].startswith("프로젝트 구성을 확정했습니다")
    doc = G.fallback({**base, "event": "result", "text": "계획 — 맞출 자리 12", "ok": True, "act": "plan", "actions": G.actions_in([{**PLAN[1], "primary": True}])})
    assert doc["act"] == "apply" and "제안합니다" in doc["reply"]                                              # 문서를 바꾸는 행동은 「제안」
    failed = G.fallback({**base, "event": "result", "text": "멈춤 — 미해결 2곳", "ok": False, "act": "plan", "actions": G.actions_in(PLAN)})
    assert failed["act"] == "" and "멈춘 까닭" in failed["reply"]                                              # 실패한 행동을 다시 고르지 않는다
    say = G.fallback({**base, "event": "say", "text": "표 채워줘", "actions": G.actions_in(ACTS)})
    assert say["reply"] == G.NO_LLM_SAY and [o["value"] for o in say["ask"]["options"]] == ["config_read", "config_set"]
    done = G.fallback({"event": "result", "text": "반영했습니다", "ok": True, "task": base["task"], "steps": [{**s, "state": "done"} for s in G.steps_in(STEPS)], "actions": []})
    assert "모두 끝났습니다" in done["reply"] and "출력파일 검증" in done["reply"] and not done["act"] and done["ask"] is None
    # 도는 실행이 있으면 행동을 권하지 않는다 · 한 번에 진행이 남긴 것은 보정할 곳을 고르게 한다(spec ② §7)
    run = G.fallback({**base, "event": "say" if False else "start", "actions": G.actions_in(PLAN), "facts": {"running": "간단 모드 — 끝까지 한 번에 진행 — 3단계 내용 매핑"}})
    assert run["act"] == "" and run["ask"] is None and "도는 중" in run["reply"]
    lists = [{"name": "list:aaaaaaaaaaaa", "label": "「가나대_작성본.hwpx」 남긴 것 보기", "does": "겹침 2", "change": "none"}, {"name": "open:div", "label": "패널 「작업 개요」 열기", "does": "", "change": "none"}]
    left = G.fallback({"event": "result", "text": "간단 모드(끝까지 한 번에 진행) 끝남 — 기관 문서 2개 반영", "ok": True, "act": "quick", "task": base["task"], "steps": [{**s, "state": "done"} for s in G.steps_in(STEPS)],
                       "actions": G.actions_in(lists), "facts": {"left": "넣지 않고 남긴 것 2곳(겹침 · 확인 필요 · 표 구조 다름) — 기관 문서마다 목록에서 보정합니다"}})
    assert left["reply"].startswith("간단 모드(끝까지 한 번에 진행) 끝남") and "남긴 것 2곳" in left["reply"] and left["ask"]["kind"] == "choice" and [o["value"] for o in left["ask"]["options"]] == ["list:aaaaaaaaaaaa", "open:div"]


def test_guide_turns_are_stored_in_the_agent_talk():
    c = TestClient(server.app)
    d = _doc(c, "plan_fit")
    r = c.post(f"/api/docs/{d}/agent/guide", json={"event": "start", "steps": STEPS, "actions": ACTS, "facts": {"llm": False}, "carry": [{"who": "me", "text": "양식 맞추기 해줘"}, {"who": "agent", "text": "시작하겠습니다"}]})
    assert r.status_code == 200, r.text
    t = r.json()["turn"]
    assert t["kind"] == "guide" and t["event"] == "start" and not t["llm"] and t["state"] == "open" and t["ask"]["kind"] == "config" and t["act"] is None
    assert len(t["carry"]) == 2 and [s["state"] for s in t["steps"]] == ["done", "now", "todo", "todo"] and "「사업계획서 양식 표준화」" in t["reply"]
    assert c.put(f"/api/docs/{d}/agent/guide/{t['id']}", json={"state": "done", "outcome": "1단계(1–3차년도) · 주관 한국선급"}).json()["turn"]["state"] == "done"
    r2 = c.post(f"/api/docs/{d}/agent/guide", json={"event": "result", "text": "프로젝트 구성을 확정했습니다", "ok": True, "act": "config_set", "steps": STEPS, "actions": PLAN})
    t2 = r2.json()["turn"]
    assert t2["act"] == {"name": "plan", "label": "변경 계획 보기", "does": "바뀔 자리를 셉니다", "change": "none", "paid": False, "key": ""} and t2["state"] == "open" and t2["text"] == ""
    keyed = c.post(f"/api/docs/{d}/agent/guide", json={"event": "result", "text": "계획 — 맞출 자리 12", "ok": True, "act": "plan", "steps": STEPS, "actions": [{**PLAN[1], "primary": True, "key": "plan:p1:7"}]}).json()["turn"]
    assert keyed["act"]["name"] == "apply" and keyed["act"]["key"] == "plan:p1:7"                               # 실행 카드가 가리키는 계획이 턴에 남는다
    assert c.put(f"/api/docs/{d}/agent/guide/{keyed['id']}", json={"state": "skipped", "outcome": "실행하지 않음 — 카드를 낸 뒤 계획이 바뀌었습니다"}).json()["turn"]["outcome"].startswith("실행하지 않음")
    got = c.get(f"/api/docs/{d}/agent").json()["turns"]
    assert [x["id"] for x in got] == [t["id"], t2["id"], keyed["id"]] and got[0]["kind"] == "guide" and got[0]["state"] == "done" and got[0]["outcome"].startswith("1단계") and got[0]["proposals"] == []
    full = c.get(f"/api/docs/{d}/agent/turns/{t['id']}").json()
    assert full["kind"] == "guide" and full["parts"] == [] and full["response"] is None                         # LLM 을 안 불렀다 — 보낸 글 없음
    assert [x["kind"] for x in works.read_log(d)["entries"] if x["kind"] == "agentGuide"] == ["agentGuide", "agentGuide"] if hasattr(works, "read_log") else True
    # 꼴이 틀린 요청 · 없는 턴
    assert c.post(f"/api/docs/{d}/agent/guide", json={"event": "nope"}).status_code == 400
    assert c.post(f"/api/docs/{d}/agent/guide", json={"event": "say", "text": " "}).status_code == 400
    assert c.put(f"/api/docs/{d}/agent/guide/t0", json={"state": "done"}).status_code == 404
    assert c.put(f"/api/docs/{d}/agent/guide/{t['id']}", json={"state": "open"}).status_code == 400
    # 비우면 진행 턴도 사라진다
    assert c.delete(f"/api/docs/{d}/agent").status_code == 200 and c.get(f"/api/docs/{d}/agent").json()["turns"] == []


def test_llm_answer_is_checked_against_the_sent_actions(monkeypatch):
    c = TestClient(server.app)
    d = _doc(c, "plan_fit")
    seen = {}

    def fake(data, job=None, *, home=False, call=None, timeout=120.0):
        seen.update(data=data, job=job, prompt=G.content(data, job, home))
        raw = {"reply": "계획을 세우고 바로 반영하겠습니다", "act": "wipe", "ask": {"kind": "", "text": "", "options": []}}
        return {"data": G.clean(raw, data["actions"]), "prompt": seen["prompt"], "response": raw, "call": {"backend": "api", "model": "m", "effort": "low", "ms": 5, "costUsd": None, "error": None}}

    monkeypatch.setattr(llm, "status", lambda: {"available": True})
    monkeypatch.setattr(G, "ask", fake)
    t = c.post(f"/api/docs/{d}/agent/guide", json={"event": "say", "text": "다 해줘", "steps": STEPS, "actions": PLAN, "facts": {"config": "1단계(1–3차년도)"}}).json()["turn"]
    assert t["llm"] and t["act"] is None and t["state"] == "done" and "wipe" in t["notes"][0] and t["text"] == "다 해줘"
    assert seen["job"] == "plan_fit" and seen["data"]["task"]["name"] == "사업계획서 양식 표준화" and seen["data"]["facts"] == {"config": "1단계(1–3차년도)"}
    assert G.CONTRACT in seen["prompt"] and "## 워크플로우 (workflow.md)" in seen["prompt"] and "### 사업계획서 양식 표준화 — `plan_fit`" in seen["prompt"]
    full = c.get(f"/api/docs/{d}/agent/turns/{t['id']}").json()
    assert full["parts"][0]["text"] == seen["prompt"] and full["response"]["act"] == "wipe"
    # 못 쓰는 답이면 스크립트가 답한다
    monkeypatch.setattr(G, "ask", lambda data, job=None, **k: {"data": None, "prompt": "p", "response": "x", "call": {"error": "못 쓰는 답"}})
    t = c.post(f"/api/docs/{d}/agent/guide", json={"event": "start", "steps": STEPS, "actions": PLAN}).json()["turn"]
    assert not t["llm"] and t["act"]["name"] == "plan" and "스크립트가 답했습니다" in t["notes"][0]


def test_home_guide_picks_or_asks_for_a_task():
    c = TestClient(server.app)
    assert c.post("/api/agent/guide", json={}).status_code == 400
    r = c.post("/api/agent/guide", json={"text": "사업계획서 양식을 맞추고 싶어"}).json()
    assert not r["llm"] and r["act"] == "" and r["ask"] is None and "올려" in r["reply"]                        # 파일이 없으면 시작할 수 없다
    assert [t["job"] for t in r["tasks"]] == [t["job"] for t in W.TASKS] and next(t for t in r["tasks"] if t["job"] == "style_copy")["accept"] == ["hwp", "hwpx", "docx", "pdf"]
    r = c.post("/api/agent/guide", json={"files": [{"name": "사업계획서 초안.hwpx", "size": 1000}]}).json()
    vals = [o["value"] for o in r["ask"]["options"]]
    assert r["ask"]["kind"] == "choice" and "start:plan_fit" in vals and "start:report_merge" not in vals and all(v.startswith("start:") for v in vals)   # 준비 중인 TASK 는 없다
    r = c.post("/api/agent/guide", json={"files": [{"name": "보고서.pdf"}]}).json()
    assert r["act"] == "start:style_copy" and r["ask"] is None                                                # pdf 를 받는 TASK 는 하나
    r = c.post("/api/agent/guide", json={"files": [{"name": "표.xlsx"}]}).json()
    assert r["act"] == "" and r["ask"] is None and "xlsx" in r["reply"]
    # 문서 목록(2026-11-16 — 파일은 첫 화면 왼쪽 목록 하나): 둘 이상인데 목적 문서를 안 골랐으면 시작하지 않는다(짐작하지 않음) · 골랐으면 그 문서의 형식으로 TASK 를 가린다
    two = [{"name": "취합본.hwpx", "size": 10}, {"name": "기관1.docx", "size": 10}]
    r = c.post("/api/agent/guide", json={"files": two, "list": {"target": "", "project": "", "auto": False}}).json()
    assert r["act"] == "" and r["ask"] is None and "목적 문서" in r["reply"] and "2개" in r["reply"]
    r = c.post("/api/agent/guide", json={"files": [{**two[0], "target": True}, two[1]], "list": {"target": "취합본.hwpx", "project": "수소", "auto": True}}).json()
    assert r["ask"]["kind"] == "choice" and "start:plan_merge" in [o["value"] for o in r["ask"]["options"]]   # 목적 문서(hwpx)의 형식만 본다 — 원본(docx)은 화면이 TASK 마다 따로 검사
