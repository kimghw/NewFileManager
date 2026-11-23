"""같은 양식 취합(조립 틀 · 가족 collect — spec_취합 ② §10: 2026-11-24 사용자 「사업계획서 1개 + 기관이 제출한 문서 N개 → 사업계획서의 자리에 … 수정본이 오면 앞 제출본과 견줘 바뀐 곳만 반영 ·
워크플로우는 「연차보고서 배포(안) 작성」 과 같은 꼴 · 가능한 한 지금 도구를 같이 쓰고」) — 워크플로우 틀 쪽:
조립(app/custom_tasks.py COLLECT_* · 검사 _collect_rules) · 등록부 꼴(app/workflow.py _assemble_collect · collect_tools) · 단위와 상태 식(app/workflow_units.py COLLECT · _STATE_BY["collect"]) ·
서버가 맡는 조건(app/workflow_state.py) · 실행기(app/workflow_exec.py 의 collect 절 — **가짜 문**으로: 문서마다 차례 · 줄마다 못 박기 · 미지정 건너뜀 · 수정본은 「수정본 반영」 만 · 남김 · 끝 글).
엔진(app/merge_collect_api.py — 등록부 · 못 박기 · 원장 · 수정본)은 따로 시험한다(tests/test_merge_collect*.py)."""
import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

from app import custom_tasks as C
from app import custom_tasks_api as CA
from app import job_prompts, unit_steps, workflow
from app import workflow_exec as X
from app import workflow_state as S
from app import workflow_units as U
from test_workflow_exec import Fake, FitFake, _done  # noqa: F401 — 가짜 문의 분석 · 저장 몫(start_heads · job · write …)

Outcome = unit_steps.Outcome
T = ["target"]
FOUR = [("문서 검토", [("heads", ["source", "target"]), ("headsLlm", T)]),
        ("구성 맞추기", [("configLoad", []), ("config", []), ("take", []), ("division", T), ("reheads", T), ("reheadsLlm", T)]),
        ("본문 및 테이블 매칭", [("part", ["source"]), ("link", []), ("plan", []), ("apply", []), ("revise", [])]),
        ("문서 정리", [("retidy", T), ("guide", T)])]


def _flow(groups=FOUR):
    return [{"name": name, "steps": [{"unit": u, "on": list(on)} for u, on in steps]} for name, steps in groups]


def _make(groups=FOUR, name="같은 양식 취합"):
    return C.create({"name": name, "shape": "collect", "source": "part", "target": "plan", "flow": _flow(groups)}, ["사업계획서 취합"])


def _errs(*units):
    """한 묶음에 그 줄들을 차례로 놓았을 때의 거절 글들 — (key, on) 또는 key(하는 문서는 검사가 채운다 · 문서 줄은 목적 문서)."""
    steps = [{"unit": u, "on": T if U.unit(u, "collect") and U.unit(u, "collect")["place"] == "doc" and u != "part" else ["source"] if u == "part" else []} if isinstance(u, str) else {"unit": u[0], "on": list(u[1])} for u in units]
    return C.check("collect", "part", "plan", [{"name": "a", "steps": steps}])["errors"]


# ---------------------------------------------------------------- 조립 — 틀 · 문서 짝 · 검사
def test_the_shape_is_its_own_frame_beside_the_gather_frame():
    sh = {s["id"]: s for s in C.shapes()}["collect"]
    assert (sh["io"], sh["family"], sh["many"], sh["soon"]) == ("N → 1 · 같은 양식", "collect", True, "") and "같은 양식(사업계획서)으로 기관이 따로 쓴 문서 여럿 → 사업계획서 하나의 자리에" in sh["name"]
    assert [(x["role"], x["many"], [k["id"] for k in x["kinds"]]) for x in sh["slots"]] == [("source", True, ["part"]), ("target", False, ["plan"])]
    assert C.COLLECT_PAIRS == (("part", "plan"),) == C.pairs_of("collect") and C.family_of("collect") == "collect" and C.col_of("config", "collect") == "target"
    t = _make()
    key = t["key"]
    assert (t["shape"], t["v"], t["assign"], t["source"], t["target"]) == ("collect", 2, None, "part", "plan") and [g["id"] for g in t["flow"]] == ["g1", "g2", "g3", "g4"]
    assert C.is_collect(key) and not C.is_gather(key) and not C.is_single(key) and not C.is_collect("plan_merge")   # 취합형이 아니다 — 취합 화면 · 배포 기준본으로 가지 않는다
    assert C.source_file(key) == "part" and C.target_file(key) == "plan" and C.base_of(t) == "plan_merge"
    assert job_prompts.get(key) == job_prompts.get("plan_merge") or "줄 목록으로 조립한 것" in (job_prompts.get(key) or "")   # 전제를 비우면 「사업계획서 취합」 의 것을 물려받는다
    with pytest.raises(ValueError):   # 옛 꼴(assign)로는 못 만든다 — 늘 줄 목록
        C.create({"name": "옛 꼴", "shape": "collect", "assign": {"source": ["stage_review"], "target": ["stage_fill"]}})
    with pytest.raises(ValueError, match="기관 문서 → 사업계획서"):   # 문서 짝 = 기관 문서 → 사업계획서뿐
        C.create({"name": "다른 짝", "shape": "collect", "source": "plan", "target": "report", "flow": _flow()})


def test_the_check_keeps_the_per_document_block_together_and_in_order():
    ok = C.check("collect", "part", "plan", _flow())
    assert ok["errors"] == [] and ok["std"] is None and [g["id"] for g in ok["flow"]] == ["g1", "g2", "g3", "g4"]
    lines = {s["unit"]: s for g in ok["flow"] for s in g["steps"]}
    assert lines["link"]["on"] == lines["apply"]["on"] == lines["revise"]["on"] == ["source", "target"] and lines["config"]["on"] == [] and lines["part"]["on"] == ["source"]
    assert ok["warns"] == ["유료 LLM 을 부르는 줄: LLM 검증·보완 · 다시 문서 검토(LLM)",
                           "목적 문서(사업계획서)를 바꾸는 줄: 프로젝트 구성 반영 · 다시 문서 검토(LLM) · 내용 반영 · 수정본 반영 · 넣은 뒤 템플릿 · 서식 정리 · 작성요령 삭제 — 원본 문서(기관 문서)는 바뀌지 않습니다"]
    # v1 에 없는 줄 — 이관형의 LLM 줄 셋 · 취합형의 줄 · 문서 하나의 줄
    for k, name in (("llm", "자리 연결 LLM 검토"), ("gaps", "빈 자리 검토(LLM)"), ("tableMap", "표 대응(LLM)")):
        got = _errs("link", k, "plan")
        assert any(e.startswith(f"「{name}」") and "이 틀에서는 아직 쓸 수 없는 줄입니다" in e for e in got), (k, got)
    assert any("놓을 수 없는 줄입니다" in e for e in _errs("frame")) and any("놓을 수 없는 줄입니다" in e for e in _errs("adjust"))
    # 문서 줄은 목적 문서만 — 원본 문서(기관 문서)에는 「헤딩 · 표 분석」 과 「반영할 기관 지정」 뿐
    assert any("목적 문서에만 놓을 수 있습니다" in e for e in _errs(("division", ["source"]))) and any("목적 문서에만" in e for e in _errs(("headsLlm", ["source"])))
    assert any("원본 문서에만" in e for e in _errs(("part", T))) and _errs(("heads", ["source"])) == [] and _errs(("heads", ["source", "target"])) == []
    # 기관 문서마다 도는 줄 — 한 묶음에 잇달아 · 차례(반영할 기관 지정 → 자리 연결 → 넣기 계획 → 내용 반영 → 수정본 반영)
    assert C.COLLECT_EACH in _errs("part", "link", "division", "plan", "apply") and C.COLLECT_EACH in _errs("link", "plan", "retidy", "apply")
    split = C.check("collect", "part", "plan", _flow([("a", [("part", ["source"]), ("link", [])]), ("b", [("plan", []), ("apply", [])])]))["errors"]
    assert C.COLLECT_EACH in split
    assert "「반영할 기관 지정」 은 「자리 연결」 앞에 와야 합니다" in _errs("link", "part", "plan", "apply") and "「자리 연결」 은 「반영할 기관 지정」 뒤에 와야 합니다" in _errs("link", "part", "plan", "apply")
    assert "「자리 연결」 은 「표 안 연결 · 넣기 계획」 앞에 와야 합니다" in _errs("plan", "link", "apply") and "「내용 반영」 은 「수정본 반영」 앞에 와야 합니다" in _errs("link", "plan", "revise", "apply")
    assert "「내용 반영」 에는 「표 안 연결 · 넣기 계획」이 앞에 있어야 합니다" in _errs("link", "apply") and "「표 안 연결 · 넣기 계획」 에는 「자리 연결」이 앞에 있어야 합니다" in _errs("plan", "apply")
    # 구조 반영은 자리 연결 · 내용 반영 · 수정본 반영 · 작성요령 삭제보다 앞 · 작성요령 삭제는 내용 반영 뒤 · 다시 문서 검토(LLM)는 다시 문서 검토 뒤
    assert any(e.startswith("「프로젝트 구성 반영」 은 「자리 연결」") for e in _errs("link", "plan", "apply", "division")) and any(e.startswith("「프로젝트 구성 반영」 은") for e in _errs("revise", "division"))
    assert "「작성요령 삭제」 는 「내용 반영」 뒤에 와야 합니다" in _errs("guide", "link", "plan", "apply")
    assert "「다시 문서 검토(LLM)」 에는 「다시 문서 검토」가 앞에 있어야 합니다" in _errs("reheadsLlm") and "「다시 문서 검토(LLM)」 은 「다시 문서 검토」 뒤에 와야 합니다" in _errs("reheadsLlm", "reheads")
    # 경고(저장은 됨) — 그 줄이 쓰는 앞 줄이 정의에 없다 · 「원본 문서를 쓰는 줄」 은 따지지 않는다(원본은 등록한 기관 문서들이다)
    alone = C.check("collect", "part", "plan", _flow([("a", [("link", []), ("plan", []), ("apply", [])])]))
    assert alone["errors"] == [] and any("「반영할 기관 지정」이 없습니다" in w and "미지정 문서는 건너뜁니다" in w for w in alone["warns"]) and any("「프로젝트 구성 반영」이 없습니다" in w for w in alone["warns"])
    only = C.check("collect", "part", "plan", _flow([("a", [("retidy", T)])]))
    assert only["errors"] == [] and any("「내용 반영」이 없습니다" in w and "앞서 넣은 내용만 맞춥니다" in w for w in only["warns"])
    assert C.check("collect", "part", "plan", _flow([("a", [("revise", [])])]))["errors"] == []   # 수정본 반영만 놓은 정의도 된다
    # 고르기 목록의 「먼저 있어야 할 줄」 = 검사의 거절 · 경고와 같은 짝
    uses = {u["key"]: {x["unit"]: x["must"] for x in u["uses"]} for u in CA.collect_units()[0]}
    assert uses["apply"] == {"plan": True} and uses["plan"] == {"link": True} and uses["link"] == {"part": False} and uses["revise"] == {"part": False} and uses["retidy"] == {"apply": False}
    assert uses["reheadsLlm"] == {"reheads": True} and uses["division"] == {"config": False} and uses["heads"] == {} and uses["part"] == {}


def test_the_compose_response_offers_the_frame_and_its_lines():
    body = CA.tasks_get("2")
    box = body["byShape"]["collect"]
    assert [u["key"] for u in box["units"]] == [*C.COLLECT_UNITS, "hand"] and [h["name"] for h in box["homes"]] == ["문서 검토", "구성 맞추기", "내용 넣기", "문서 정리", "사람이 하는 일"]
    by = {u["key"]: u for u in box["units"]}
    assert [k for k, u in by.items() if u["each"]] == ["part", "link", "plan", "apply", "revise"] and by["heads"]["roles"] == ["source", "target"] and by["part"]["roles"] == ["source"]
    assert all(u["roles"] == ["target"] for k, u in by.items() if u["place"] == "doc" and k not in ("heads", "part", "hand")) and by["config"]["col"] == by["take"]["col"] == "target"
    assert {k: u["family"] for k, u in by.items() if u["family"] == "collect"} == dict.fromkeys(U.COLLECT, "collect") and not by["revise"]["optional"] and by["take"]["kind"] == "pick"
    assert by["link"]["name"] == by["link"]["base"] == "자리 연결" and by["plan"]["base"] == "표 안 연결 · 넣기 계획" and by["part"]["base"] == "반영할 기관 지정" and by["revise"]["base"] == "수정본 반영"
    assert [(g["name"], [s["unit"] for s in g["steps"]]) for g in box["flow"]] == [(n, [u for u, _ in steps]) for n, steps in FOUR[:3]] + [("문서 정리", ["retidy"])]
    assert C.check("collect", "part", "plan", box["flow"])["errors"] == [] and box["pairs"] == [{"source": "part", "target": "plan", "name": "기관 문서 → 사업계획서"}]
    assert [x["key"] for x in box["later"]] == list(C.COLLECT_LATER)
    # 이관형과 줄 key · 기본 이름이 같은 줄 = 같은 도구(이름 고치기 · 적어 둔 내용을 같이 쓴다) · 이 틀에만 있는 줄은 이관형에 없다
    from app import agent_notes, tool_names_api
    relay, mine = tool_names_api.bases("relay"), tool_names_api.bases("collect")
    same = {k for k in mine if relay.get(k) == mine[k]}
    assert same == set(C.COLLECT_UNITS) - {"part", "revise"} and "part" not in relay and "revise" not in relay and set(agent_notes.tool_map()["collect"]) == set(C.COLLECT_UNITS)
    assert agent_notes.tool_map()["collect"]["apply"]["agents"] == [] and agent_notes.tool_map()["collect"]["revise"]["agents"] == []   # 새 LLM 호출은 없다
    from app import user_reqs
    assert user_reqs.target_ok("tool:collect.revise") and not user_reqs.target_ok("tool:nope.revise")


# ---------------------------------------------------------------- 등록부 꼴 · 단위 · 서버가 맡는 조건
def test_the_registry_shape_and_units_agree_and_the_server_serves_it():
    t = _make()
    task = S.definition(t["key"])
    assert (task["units"], task["base"], task["custom"], task["premise_from"]) == ("collect", "target", True, "plan_merge")
    assert [(r["role"], r["name"], r["kind"], r["many"]) for r in task["roles"]] == [("source", "기관 문서", "part", True), ("target", "사업계획서", "plan", False)]
    assert [(g["id"], g["no"], g["name"], g["module"], [(s["key"], s["on"]) for s in g["steps"]]) for g in task["stages"]] == [
        ("g1", "1단계", "문서 검토", "stage_review", [("files", "flow"), ("heads", "both"), ("headsLlm", "target")]),
        ("g2", "2단계", "구성 맞추기", "stage_fit", [("configLoad", "flow"), ("config", "flow"), ("take", "flow"), ("division", "target"), ("reheads", "target"), ("reheadsLlm", "target")]),
        ("g3", "3단계", "본문 및 테이블 매칭", "stage_fill", [("part", "source"), ("link", "pair"), ("plan", "pair"), ("apply", "pair"), ("revise", "pair")]),
        ("g4", "4단계", "문서 정리", "stage_clean", [("retidy", "target"), ("guide", "target")])]
    assert [g["does"].split(" · ")[-1] for g in task["stages"]] == ["문서는 안 바뀜", "목적 문서(사업계획서)가 바뀜", "목적 문서(사업계획서)가 바뀜", "목적 문서(사업계획서)가 바뀜"]
    assert S.family(task) == "collect" and S.framed(task) and S.base(task) == "target" and not S.relay_pair(task) and "collect" in S.OPEN_CUSTOM and "collect" not in S.OPEN
    assert all(S.served(task, g["id"]) for g in task["stages"]) and S.need(task) == ["source", "target"]
    assert S.lane_of(task, [{"on": x["on"], "unit": x["unit"]} for x in S.lines(task) if x["stage"] == "g1"]) == ""   # 문서마다 따로 도는 실행은 없다(원본이 여럿 — 묶음에 실행 하나)
    lines = {x["key"]: x for x in S.lines(task)}
    for k in ("heads", "take", "part", "link", "plan", "apply", "revise", "retidy"):   # 이관형과 key 가 같아도 이 가족의 단위가 먼저(따로 선 객체)
        assert lines[k]["unit"] is U.COLLECT[k] and U.COLLECT[k] is not U.RELAY.get(k) and U.COLLECT[k] is not U.COMMON.get(k), k
    for k in ("files", "headsLlm", "configLoad", "config", "division", "reheads", "reheadsLlm", "guide"):
        assert lines[k]["unit"] is U.COMMON[k], k
    assert [k for k, x in lines.items() if x["unit"]["each"]] == ["part", "link", "plan", "apply", "revise"]
    for g in task["stages"]:   # 등록부의 줄과 단위 — 문서 바뀜 · 선택 · 하는 문서 · 유료
        for s in g["steps"]:
            u = lines[s["key"]]["unit"]
            assert u["change"] == s["change"] and u["optional"] == s["optional"], s["key"]
            assert (u["place"] == s["on"]) if s["on"] in ("pair", "flow") else set(U.roles_of(s["on"])) <= set(U.roles_in(u, "collect")), s["key"]
            assert not u["paid"] or "llm" in s["by"], s["key"]
    # 처리 함수 — 이 가족의 줄은 제 것(이관의 몸통을 감싼 것) · 같이 쓰는 줄은 같이 쓰는 것
    H = X.FAMILY_HANDLERS["collect"]
    assert set(H) == {k for k, u in U.COLLECT.items() if u["kind"] == "auto"} and H["retidy"] is X._do_retidy and X.EACH["collect"] is X._each_collect and "gather" not in X.EACH
    assert X._handler(task, lines["apply"]) is X._do_c_apply and X._handler(task, lines["division"]) is X._do_division and X._handler(task, lines["heads"]) is X._do_c_heads
    assert not X._fill_need(task) or S.family(task) == "collect"   # 이관의 넣기 재료(지금 원본 하나의 표식)는 얹지 않는다(_fill_materials 가 이 가족을 지나친다)
    # 헤딩 · 표 분석의 글은 줄이 고른 문서로 · 조립한 정의의 만든 글(작업 진행 에이전트의 참조 글)도 지어진다
    only_t = S.definition(_make([("a", [("heads", T)])], name="목적만")["key"])
    heads = next(s for g in only_t["stages"] for s in g["steps"] if s["key"] == "heads")
    assert heads["on"] == "target" and "기관 문서마다" not in heads["does"] and "사업계획서에 헤딩 그래프와 표 구조가 없으면" in heads["does"]
    md = workflow.task_markdown(t["key"])
    assert "반영할 기관 지정" in md and "수정본 반영" in md and "기관 문서" in md and "정한 차례: [문서 검토: 「헤딩 · 표 분석」" in workflow.picked_line(C.get(t["key"]))
    assert workflow.custom_desc(C.get(t["key"])) == "기관이 같은 양식으로 따로 쓴 문서의 내용을 사업계획서의 그 기관 자리에 넣습니다 — 수정본은 바뀐 곳만 고칩니다. 정한 차례대로 진행합니다."


def test_api_lists_the_definition_for_the_screens(monkeypatch):
    from app import server
    c = TestClient(server.app)
    r = c.post("/api/tasks", json={"name": "기관 작성본 취합", "shape": "collect", "source": "part", "target": "plan", "flow": _flow()})
    assert r.status_code == 201, r.text
    t = r.json()["task"]
    assert (t["shape"], t["v"], t["source"], t["target"], t["sourceName"], t["targetName"], t["groups"]) == ("collect", 2, "part", "plan", "기관 문서", "사업계획서", ["g1", "g2", "g3", "g4"])
    assert set(t["does"]) == {"g1", "g2", "g3", "g4"} and t["descAuto"].startswith("기관이 같은 양식으로 따로 쓴 문서의 내용을")
    assert t["key"] in c.get("/api/tasks.js?v=2").text and '"shape": "collect"' in c.get("/api/tasks.js?v=2").text and t["key"] not in c.get("/api/tasks.js").text   # 판 없이 읽는 옛 탭에는 안 실린다(줄 목록 정의)
    W = next(x for x in c.get("/api/workflow").json()["tasks"] if x["job"] == t["key"])
    assert W["base"] == "target" and [(r["role"], r["many"], r["kind"]) for r in W["roles"]] == [("source", True, "part"), ("target", False, "plan")]
    assert [s["onText"] for s in W["stages"][2]["steps"]] == ["원본 문서마다 — 기관 문서"] + ["원본 문서마다 → 목적 — 기관 문서 → 사업계획서"] * 4
    assert c.put(f"/api/tasks/{t['key']}", json={"shape": "gather"}).status_code == 400   # 틀은 못 고친다
    assert c.post("/api/tasks/check", json={"shape": "collect", "flow": _flow([("a", [("link", []), ("llm", []), ("plan", []), ("apply", [])])])}).json()["errors"][0].startswith("「자리 연결 LLM 검토」")


# ---------------------------------------------------------------- 상태 식 — 등록부의 보기로
V2 = {"stages": [2], "orgs": {"lead": "인텍", "joint": ["가나대"], "nonprofit": [False, False], "outside": [], "overseas": [], "entrust": []}, "subs": [], "current": 1}


def _row(work, state, name=None, **more):
    return {"work": work, "name": name or f"{work}.hwpx", "order": 0, "orgs": [] if state == "unassigned" else ["가나대"], "orgNames": [] if state == "unassigned" else ["가나대"], "orgsBy": "", "common": False,
            "revOf": None, "revName": "", "later": [], "state": state, "text": "", "done": None, **more}


def _ctx(parts=None, div=None, **facts):
    t = {"id": "t", "heads": {"s2": True, "s3": True, "llm": False, "job": None}, "div": div, **facts}
    if parts is not None:
        t["collect"] = {"collect": True, "version": 1, "orgs": [], "parts": parts}
    return {"ready": True, "lack": [], "llm": True, "skip": set(), "base": "target", "pair": {"target": {"role": "target", "title": "사업계획서", "id": "t", "facts": t}}}


def test_state_lines_count_the_registry_view_not_the_last_source():
    st = lambda key, ctx: U.state(key, ctx, "collect")  # noqa: E731
    assert st("part", _ctx()) == {"st": "blocked", "text": "기관 문서의 등록 상태를 읽지 못했습니다"} and st("apply", {**_ctx([]), "ready": False}) == {"st": "todo", "text": ""}
    none = st("part", _ctx([]))
    assert none["st"] == "done" and none["skipped"] and "기관 문서가 아직 없습니다" in none["text"]
    assert st("apply", _ctx([])) == {"st": "todo", "text": "넣을 기관 문서가 없습니다"}   # 넣기 대상이 하나도 없으면 끝남이 아니다
    rows = [_row("a", "done"), _row("b", "unassigned"), _row("c", "todo"), _row("d", "superseded", later=["e"]), _row("e", "revision", revOf="d"), _row("f", "left", text="반영함 — 본문 블록 · 표 칸 3곳 · 남은 것 1(확인 필요 · 겹침)")]
    part = st("part", _ctx(rows))
    assert (part["st"], part["text"]) == ("todo", "기관 문서 6개 — 지정 5 · 미지정 1") and [(p["doc"], p["st"], p["state"]) for p in part["per"]] == [
        ("a", "done", "done"), ("b", "todo", "unassigned"), ("c", "done", "todo"), ("d", "done", "superseded"), ("e", "done", "revision"), ("f", "done", "left")]
    assert part["per"][1]["text"] == "b.hwpx — 반영할 기관 미지정 — 미지정이면 넣지 않습니다" and part["per"][0]["text"] == "a.hwpx — 가나대" and all(p["role"] == "source" for p in part["per"])
    fill = st("apply", _ctx(rows))
    assert st("link", _ctx(rows)) == st("plan", _ctx(rows)) == fill and fill["st"] == "todo"
    assert fill["text"] == "기관 문서 2/3 반영 — a.hwpx(반영함) · c.hwpx(넣을 차례) · f.hwpx(반영함 · 확인 필요) · 확인 필요 · 겹침이 남은 문서 1개(연결 목록에서 고른 뒤 다시 진행)"   # 넣기 대상 = 넣을 차례 · 반영함 · 확인 필요(미지정 · 수정본 · 뒤 수정본이 있는 문서는 아니다)
    assert [(p["doc"], p["st"], p["skipped"]) for p in fill["per"]] == [("a", "done", False), ("b", "done", True), ("c", "todo", False), ("d", "done", True), ("e", "done", True), ("f", "done", False)]   # 확인 필요가 남은 문서(f)도 반영한 문서다 — 남은 것은 글에 밝힌다
    assert fill["per"][5]["text"].endswith("남은 것 1(확인 필요 · 겹침)") and "「수정본 반영」 이 바뀐 곳만" in fill["per"][4]["text"]
    assert st("apply", _ctx([_row("a", "done"), _row("b", "unassigned")]))["st"] == "done"   # 미지정 문서는 「반영할 기관 지정」 줄이 남는다(넣기 줄은 넣기 대상만 센다)
    assert st("apply", _ctx([_row("b", "unassigned")])) == {"st": "todo", "text": "넣을 기관 문서가 없습니다(반영할 기관 미지정 1개)", "per": st("apply", _ctx([_row("b", "unassigned")]))["per"]}
    assert st("apply", _ctx([_row("a", "done"), _row("f", "left")]))["st"] == "done"   # 확인 필요 · 겹침이 남은 문서도 반영한 것으로 센다(뒤의 「문서 정리」 가 막히지 않게 — 남은 것은 글에 · 사람이 연결을 고치면 다시 「넣을 차례」)
    many = st("apply", _ctx([_row(f"p{i}", "done") for i in range(11)]))
    assert many["st"] == "done" and many["text"].endswith("외 3개") and many["text"].startswith("기관 문서 11/11 반영 — p0.hwpx(반영함)")
    rev = st("revise", _ctx(rows))
    assert (rev["st"], rev["text"]) == ("todo", "수정본 1개 — 반영 0 · 반영 전 1") and [p["doc"] for p in rev["per"]] == ["e"]
    assert st("revise", _ctx([_row("a", "done")])) == {"st": "done", "skipped": True, "text": "수정본이 없습니다"}
    after = st("revise", _ctx([_row("d", "superseded", later=["e"]), _row("e", "left", revOf="d")]))
    assert (after["st"], after["text"]) == ("done", "수정본 1개 — 반영 1 · 반영 전 0 · 확인 필요 1")
    # 헤딩 · 표 분석 — 목적 문서는 같이 쓰는 줄의 식 · 원본 문서는 등록한 기관 문서마다(뒤 수정본이 있는 문서는 빼고)
    tdoc = [{"role": "target", "title": "사업계획서", "id": "t", "facts": _ctx()["pair"]["target"]["facts"]}]
    both = st("heads", {**_ctx(rows, partHeads={"a": True, "c": False, "e": True, "f": True}), "docs": tdoc, "roles": ("source", "target")})
    assert both["st"] == "todo" and both["text"].startswith("기관 문서 5개 — 헤딩 그래프·표 구조 있음 3 · 없음 2 · 헤딩 그래프·표 구조: 사업계획서 있음")
    assert [(p["doc"], p["role"], p["st"]) for p in both["per"]] == [("a", "source", "done"), ("b", "source", "todo"), ("c", "source", "todo"), ("e", "source", "done"), ("f", "source", "done"), ("t", "target", "done")]
    assert st("heads", {**_ctx(rows), "docs": tdoc, "roles": ("target",)}) == U.state("heads", {**_ctx(rows), "docs": tdoc}, "relay")   # 목적 문서만 = 같이 쓰는 줄의 값 그대로
    empty = st("heads", {**_ctx([]), "docs": [], "roles": ("source",)})
    assert empty["st"] == "done" and empty["skipped"] and "기관 문서가 아직 없습니다" in empty["text"]   # 기관 문서가 아직 없어도 줄이 막다른 길이 되지 않는다
    assert U.collect_filled({"parts": rows}) and not U.collect_filled({"parts": [_row("b", "unassigned"), _row("c", "todo"), _row("e", "revision", revOf="d")]}) and not U.collect_filled(None)
    assert U.collect_revise_text({"ready": 2, "overlap": 1, "hold": 0, "missing": 3, "same": 4}, 5) == "수정본 반영 — 고친 곳 2 · 겹침 1 · 확인 필요 0 · 수정본에 없음 3 · 새 자리 5 · 이미 같음 4"


def test_structure_follows_the_target_documents_own_values():
    """구성의 기준 = 목적 문서(사업계획서) — 같이 쓰는 「프로젝트 구성 반영」 · 「다시 문서 검토」 의 식이 원본 문서(기관 문서) 없이 목적 문서의 제 값으로 센다(이관형의 식은 그대로)."""
    cf = {"values": V2, "at": 1}
    div = lambda **k: {"input": V2, "applied": None, "confirmed": cf, "partial": [], "form": "연구개발계획서", "supported": True, "rev": 0, "read": None, "sharing": None, "plan": None, "stale": False, **k}  # noqa: E731
    st = lambda key, d: U.state(key, _ctx([], d), "collect")  # noqa: E731
    assert st("config", div())["st"] == "done" and st("config", div(confirmed=None))["st"] == "todo"
    assert st("division", div(confirmed=None)) == {"st": "todo", "text": ""}   # 확정이 먼저
    assert "아직 사업계획서에 반영되지 않았습니다" in st("division", div())["text"] and "지원하지 않습니다" in st("division", div(supported=False))["text"]
    assert st("division", div(applied={"values": V2})) == {"st": "done", "text": "사업계획서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳"}
    assert st("division", div(applied={"values": V2, "adopted": True}))["text"].startswith("사업계획서의 구조가 이미 값에 맞음(확인함)")
    assert "마지막으로 반영한 값과 다릅니다" in st("division", div(applied={"values": {**V2, "current": 2}}))["text"]   # 반영 값 = 입력 값 전체(당해 차년도도)
    assert st("reheads", div())["st"] == "todo" and st("reheads", div(applied={"values": V2, "rev": 0}))["st"] == "done"   # 구조 반영 뒤의 분석(rev 가 같다)
    # 이관형(구성의 기준 = 원본 문서)의 식은 그대로 — 원본 문서가 없으면 셈하지 않는다
    assert U.state("division", {**_ctx([], div(applied={"values": V2})), "base": "source"}, "relay") == {"st": "todo", "text": ""}


# ---------------------------------------------------------------- 실행기 — 가짜 문
class CFake(Fake):
    """가짜 문(같은 양식 취합) — 목적 문서 t 와 기관 문서들. 등록부의 보기 · 자동 지정 · 못 박기 · 연결 목록 · 넣기 계획 · 반영 · 수정 계획 · 수정본 반영을 메모리로 흉내 낸다(부른 차례를 calls 에)."""

    def __init__(self, key, rows):
        super().__init__()
        self.key, self.rows, self.bound, self.n = key, {r["work"]: r for r in rows}, None, 0
        self.heads = {"t": True, **{k: True for k in self.rows}}
        self.llm = {k: False for k in self.heads}
        self.autos, self.reasons, self.to_reasons, self.todo, self.after = {}, {}, [], {}, {}   # 자동 지정이 정할 기관 · 그 문서 쪽 까닭 · 목적 쪽 까닭 · 넣을 것의 수 · 반영 뒤의 상태
        self.nobind, self.revise, self.switch, self.pinned = set(), {}, None, None   # 못 박지 못하는 문서 · 수정 계획{todo, counts} · 넣기 계획 직전에 다른 화면이 고른 원본 · 시작할 때의 문서 목록
        self.guard = None

    def pair(self, wid):
        if wid != "t" and wid not in self.rows:
            return None
        docs = [{"id": k, "name": r["name"], "format": "hwpx"} for k, r in self.rows.items()]
        return {"job": self.key, "scope": ["시험", self.key, 1], "file": "plan" if wid == "t" else "part", "kinds": {"target": "plan", "source": "part"},
                "target": {"id": "t", "name": "계획서.hwpx", "format": "hwpx"}, "source": None, "sources": docs}

    def heads_have(self, doc):
        return self.heads[doc]

    def fill_facts(self, doc):
        return {"links": {}, "heads": {}}

    def collect(self, target):
        return {"collect": True, "version": 1, "orgs": [], "parts": [dict(r) for r in self.rows.values()]}

    def collect_auto(self, target, part):
        self.calls.append(("auto", part))
        org = self.autos.get(part)
        if org:
            r = self.rows[part]
            r.update(orgs=[org], orgNames=[org], orgsBy="name", state="revision" if r["revOf"] else "todo")
        return Outcome("ok", "", {**self.collect(target), "auto": {"part": part, "org": org, "by": "name" if org else None, "why": "" if org else "파일 이름과 문서에서 기관을 가리지 못했습니다"}})

    def collect_bind(self, target, part):
        self.calls.append(("bind", part))
        if part in self.nobind:
            return Outcome("blocked", "원본 문서를 그 기관 문서로 정하지 못했습니다")
        self.bound = part
        return Outcome("ok", "", {"from": part})

    def links(self, target):
        self.calls.append(("links", self.bound))
        return Outcome("ok", "", {"counts": {"paired": 1 if self.todo.get(self.bound) is not None else 0, "ambiguous": 0, "toOnly": 0, "fromOnly": 0},
                                  "from": {"id": self.bound, "reasons": list(self.reasons.get(self.bound, ()))}, "to": {"id": "t", "reasons": list(self.to_reasons)}})

    def fill_plan(self, target, part=None):
        if self.switch:
            self.bound = self.switch   # 다른 화면이 그 사이 원본을 바꿨다
        self.calls.append(("plan", self.bound, part))
        if part and part != self.bound:
            return Outcome("blocked", "기대한 기관 문서와 지금 원본이 다릅니다")
        self.n += 1
        return Outcome("ok", "", {"planId": f"p{self.n}", "todo": self.todo.get(self.bound) or 0, "body": {"counts": {"todo": self.todo.get(self.bound) or 0}}})

    def fill_apply(self, target, plan_id):
        self.calls.append(("apply", self.bound, plan_id))
        n = self.todo.get(self.bound) or 0
        self.todo[self.bound] = 0
        self.rows[self.bound].update(state=self.after.get(self.bound, "done" if n else "left"), text="" if n else "넣을 수 있는 자리를 찾지 못했습니다 — 연결 목록에서 확인하세요")
        return Outcome("ok", "", {"body": {"blocks": n}}) if n else Outcome("nothing", "넣을 것이 없습니다", {"nothing": True})

    def collect_revise_plan(self, target, part):
        self.calls.append(("rplan", part))
        p = self.revise.get(part)
        if p is None:
            return Outcome("blocked", "앞 제출본을 넣은 기록이 없습니다")
        return Outcome("ok", "", {"planId": f"r-{part}", "part": part, "base": [self.rows[part]["revOf"]], "todo": p["todo"], "counts": dict(p["counts"]), "fresh": {"todo": 0}})

    def collect_revise_apply(self, target, part, plan_id):
        self.calls.append(("rapply", part, plan_id))
        p = self.revise[part]
        c = p["counts"]
        self.rows[part]["state"] = "left" if c.get("overlap") or c.get("hold") else "done"
        return Outcome("ok", "", {"counts": dict(c)}) if p["todo"] else Outcome("nothing", "고칠 것이 없습니다", {"nothing": True, "counts": dict(c)})

    def take_default(self, target):
        self.calls.append(("takeDefault", target))
        return Outcome("ok", "", {})

    def take_get(self, target):   # 넣을 구성의 보기(merge_api.take_view 의 꼴 — 상태 식 workflow_units._take 가 읽는 것만)
        return Outcome("ok", "", {"ready": True, "year": 1, "yearApplied": None, "yearPicked": False, "yearAuto": 1, "active": False, "text": "", "notes": []})


EACH = [("넣기", [("part", ["source"]), ("link", []), ("plan", []), ("apply", []), ("revise", [])])]


@pytest.fixture
def door(monkeypatch):
    def make(rows, groups=EACH):
        f = CFake(_make(groups, name=f"시험 {time.time_ns()}")["key"], rows)
        monkeypatch.setattr(X, "UNIT", f)
        return f
    monkeypatch.setitem(X.WAIT, "poll", 0.005)
    for k, v in (("settle", 0.05), ("poll", 0.005)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    for d in (X.RUNS, X.BUSY, X.LAST, X.MATES, X.CLAIMS, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()
    yield make
    _done("t", 5)
    for d in (X.RUNS, X.BUSY, X.LAST, X.MATES, X.CLAIMS, X.FENCE, X.NOTICE, X.REPORTS):
        d.clear()


def test_each_document_runs_its_own_lines_in_the_registered_order(door):
    """기관 문서마다 한 덩이 — 등록한 차례 · 문서의 등록 상태에 맞는 줄만: 넣을 차례 = 자리 연결 → 넣기 계획 → 내용 반영(줄마다 직전에 못 박기) · 미지정 = 자동 지정을 해 보고 못 정하면 건너뜀 ·
    뒤 수정본이 있는 문서 · 이미 반영한 문서 = 조용히 지나감 · 수정본 = 「수정본 반영」 만 · 겹침이 남으면 남김."""
    f = door([_row("a", "todo", "가나대.hwpx"), _row("b", "unassigned", "모름.hwpx"), _row("c", "unassigned", "다라연.hwpx"), _row("d", "superseded", "옛 제출.hwpx", later=["e"]),
              _row("e", "revision", "수정본.hwpx", revOf="d"), _row("g", "done", "끝난 것.hwpx")])
    f.todo.update(a=3, c=2)
    f.autos["c"] = "다라연"
    f.revise["e"] = {"todo": 2, "counts": {"ready": 2, "same": 5, "overlap": 1, "hold": 0, "missing": 1}}
    v = X.status_of("t")
    g = v["stages"][0]
    assert v["ready"] and [d["id"] for d in v["docs"]["sources"]] == ["a", "b", "c", "d", "e", "g"] and v["docs"]["source"] is None and g["server"] and g["can"] and "solo" not in g and g["lane"] == ""
    assert [(s["key"], s["st"], s["optional"]) for s in g["steps"]] == [("files", "done", False), ("part", "now", False), ("link", "todo", False), ("plan", "todo", False), ("apply", "todo", False), ("revise", "todo", False)]
    assert g["steps"][1]["text"] == "기관 문서 6개 — 지정 4 · 미지정 2" and g["steps"][4]["text"] == "기관 문서 1/2 반영 — 가나대.hwpx(넣을 차례) · 끝난 것.hwpx(반영함)" and g["left"] == 5 and g["change"] is True   # 남은 단계 = 반영할 기관 지정 · 넣기 셋 · 수정본 반영(반영 전인 수정본이 있다)
    run = X.start("c", {"from": "g1"})   # 기관 문서에서 눌러도 그 묶음에서 돈다
    assert run["docs"]["target"]["id"] == "t" and [d["id"] for d in run["docs"]["sources"]] == ["a", "b", "c", "d", "e", "g"] and run["lane"] == "" and X.busy_text("a") and X.busy_text("t")
    rec = _done("t")
    assert rec["status"] == "left", rec["end"]
    assert f.calls == [("bind", "a"), ("links", "a"), ("bind", "a"), ("plan", "a", "a"), ("bind", "a"), ("apply", "a", "p1"),   # 줄마다 부르기 직전에 못 박는다 · 넣기 계획은 기대한 원본을 넘긴다
                       ("auto", "b"),                                                                                              # 못 정함 — 그 문서는 여기까지
                       ("auto", "c"), ("bind", "c"), ("links", "c"), ("bind", "c"), ("plan", "c", "c"), ("bind", "c"), ("apply", "c", "p2"),
                       ("rplan", "e"), ("rapply", "e", "r-e")]                                                                     # d(뒤 수정본이 있음) · g(반영함)는 부르지 않는다 · 수정본은 「수정본 반영」 만
    steps = [(s["key"], s.get("doc"), s["status"]) for s in rec["steps"]]
    assert steps == [("link", "a", "done"), ("plan", "a", "done"), ("apply", "a", "done"), ("part", "b", "left"), ("part", "c", "done"), ("link", "c", "done"), ("plan", "c", "done"), ("apply", "c", "done"),
                     ("revise", "e", "left")], steps
    text = {(s["key"], s.get("doc")): s["text"] for s in rec["steps"]}
    assert text[("part", "c")] == "다라연.hwpx — 반영할 기관 → 다라연(파일 이름)" and text[("part", "b")].startswith("모름.hwpx — 반영할 기관을 정하지 못함 — 넣지 않고 건너뜁니다(파일 이름과 문서에서 기관을 가리지 못했습니다)")
    assert text[("revise", "e")] == "수정본.hwpx — 수정본 반영 — 고친 곳 2 · 겹침 1 · 확인 필요 0 · 수정본에 없음 1 · 이미 같음 5" and text[("link", "a")].startswith("가나대.hwpx — 연결 목록 — 연결됨 1")
    assert rec["end"]["text"] == ("남김 — 기관 문서 2개 반영(가나대.hwpx · 다라연.hwpx) · 수정본 1개 반영(수정본.hwpx) · 확인 필요 · 겹침이 남은 문서 1개(수정본.hwpx) · 반영할 기관 미지정 1개는 건너뜀(모름.hwpx)")
    assert [x["what"].split(" — ")[0] for x in rec["left"]] == ["모름.hwpx", "수정본.hwpx"] and not X.FENCE and not X.NOTICE and not X.busy_text("a")
    # 상태 — 등록부의 보기로 다시 센다: 미지정이 남아 「반영할 기관 지정」 이 남고 · 넣기 대상은 모두 반영 · 수정본은 반영(확인 필요)
    g = X.status_of("t")["stages"][0]
    by = {s["key"]: s for s in g["steps"]}
    assert (by["part"]["done"], by["apply"]["done"], by["revise"]["done"], g["left"]) == (False, True, True, 1) and by["apply"]["text"].startswith("기관 문서 3/3 반영")
    assert [(p["doc"], p["st"], p["state"]) for p in by["apply"]["per"]] == [("a", "done", "done"), ("b", "done", "unassigned"), ("c", "done", "done"), ("d", "done", "superseded"), ("e", "done", "left"), ("g", "done", "done")]
    # 다시 누르면 남은 문서만 — 사람이 b 의 기관을 정한 뒤
    f.rows["b"].update(orgs=["마바사"], orgNames=["마바사"], state="todo")
    f.todo["b"] = 0   # 이어진 자리는 있으나 넣을 것이 없다
    f.calls.clear()
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert [c[:2] for c in f.calls] == [("bind", "b"), ("links", "b"), ("bind", "b"), ("plan", "b"), ("bind", "b"), ("apply", "b"), ("rplan", "e"), ("rapply", "e")]   # e = 확인 필요가 남은 수정본 — 「수정본 반영」 이 다시 견준다
    assert rec["status"] == "left" and "넣을 것이 없는 문서 1개" in rec["end"]["text"] and "기관 문서 1개 반영" not in rec["end"]["text"]   # 넣을 것이 0 인 문서를 「반영함」 으로 세지 않는다


def test_a_document_side_block_skips_that_document_and_a_target_side_block_halts(door):
    f = door([_row("a", "todo", "가.hwpx"), _row("b", "todo", "나.hwpx"), _row("c", "todo", "다.hwpx")])
    f.todo.update(a=1, b=1, c=1)
    f.reasons["a"] = ["noHeadings"]   # 그 문서 쪽 까닭 — 그 문서만 남긴다
    f.nobind.add("b")                 # 못 박지 못함 — 그 문서만 남긴다
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert rec["status"] == "left" and [(s["key"], s.get("doc"), s["status"]) for s in rec["steps"]] == [("link", "a", "left"), ("link", "b", "left"), ("link", "c", "done"), ("plan", "c", "done"), ("apply", "c", "done")]
    assert "연결 목록을 낼 수 없습니다 — 가.hwpx: 헤딩·표 분석 없음" in rec["steps"][0]["text"] and "이 문서를 원본으로 정하지 못했습니다" in rec["steps"][1]["text"]
    assert rec["end"]["text"] == "남김 — 기관 문서 1개 반영(다.hwpx) · 넣지 못한 문서 2개(가.hwpx · 나.hwpx)"
    # 목적 문서 쪽 까닭 — 전체 멈춤(뒤 문서도 같은 까닭이다)
    f = door([_row("a", "todo", "가.hwpx"), _row("b", "todo", "나.hwpx")])
    f.todo.update(a=1, b=1)
    f.to_reasons = ["notApplied"]
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert rec["status"] == "halted" and rec["halt"]["code"] == "blocked" and rec["halt"]["key"] == "link" and "사업계획서: 프로젝트 구성 반영 전" in rec["end"]["text"] and ("bind", "b") not in f.calls
    # 넣기 계획 직전에 다른 화면이 원본을 바꿨다 — 다른 기관의 계획을 세우지 않고 멈춘다
    f = door([_row("a", "todo", "가.hwpx"), _row("b", "todo", "나.hwpx")])
    f.todo.update(a=1, b=1)
    f.switch = "b"
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert rec["status"] == "halted" and ("plan", "b", "a") in f.calls and not [c for c in f.calls if c[0] == "apply"] and "기대한 기관 문서와 지금 원본이 다릅니다" in rec["end"]["text"]


def test_revisions_without_the_revise_line_and_documents_added_after_the_start_are_told(door):
    f = door([_row("a", "todo", "가.hwpx"), _row("e", "revision", "수정본.hwpx", revOf="a"), _row("b", "unassigned", "나.hwpx")], [("넣기", [("link", []), ("plan", []), ("apply", [])])])
    f.todo["a"] = 1
    real = f.collect
    f.collect = lambda target: {**real(target), "parts": real(target)["parts"] + [_row("z", "todo", "늦게 올림.hwpx")]}   # 실행을 시작한 뒤 등록한 문서(못 박은 목록에 없다)
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert rec["status"] == "left" and not [c for c in f.calls if c[0] in ("auto", "rplan")] and [c for c in f.calls if c[0] == "bind"] == [("bind", "a")] * 3
    assert rec["end"]["text"] == ("남김 — 기관 문서 1개 반영(가.hwpx) · 반영할 기관 미지정 1개는 건너뜀(나.hwpx) · 수정본 1개는 「수정본 반영」 줄이 없어 그대로 · 실행을 시작한 뒤 등록한 문서 1개는 다음 실행에서")
    # 수정 계획을 못 세운 수정본은 그 문서만 남긴다 · 고칠 것이 0 인 수정본은 울타리 없이 끝 표식만(문서는 안 바뀐다)
    f = door([_row("a", "superseded", "가.hwpx", later=["e"]), _row("e", "revision", "수정본.hwpx", revOf="a"), _row("h", "revision", "수정본2.hwpx", revOf="x")])
    f.revise["e"] = {"todo": 0, "counts": {"ready": 0, "same": 9, "overlap": 0, "hold": 0, "missing": 0}}
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert f.calls == [("rplan", "e"), ("rapply", "e", "r-e"), ("rplan", "h")] and rec["status"] == "left"
    assert [(s["key"], s.get("doc"), s["status"]) for s in rec["steps"]] == [("revise", "e", "nothing"), ("revise", "h", "left")] and "수정 계획을 세우지 못했습니다 — 앞 제출본을 넣은 기록이 없습니다" in rec["steps"][1]["text"]
    assert f.rows["e"]["state"] == "done" and rec["end"]["text"] == "남김 — 넣지 못한 문서 1개(수정본2.hwpx)"


def test_heads_on_the_source_side_analyses_each_registered_document_one_by_one(door):
    """원본 문서에 놓은 「헤딩 · 표 분석」 — 등록한 기관 문서마다(뒤 수정본이 있는 문서는 빼고) 분석이 없는 문서만 하나씩 · 목적 문서는 같이 쓰는 줄과 같은 일(작성 지침 저장)."""
    f = door([_row("a", "todo", "가.hwpx"), _row("b", "unassigned", "나.hwpx"), _row("d", "superseded", "옛.hwpx", later=["e"]), _row("e", "revision", "수정본.hwpx", revOf="d")],
             [("문서 검토", [("heads", ["source", "target"])]), ("넣기", [("part", ["source"]), ("link", []), ("plan", []), ("apply", [])])])
    f.heads.update(a=False, b=True, d=False, e=False, t=False)
    g = X.status_of("t")["stages"][0]
    heads = g["steps"][1]
    assert heads["key"] == "heads" and heads["on"] == "both" and not heads["done"] and heads["text"].startswith("기관 문서 3개 — 헤딩 그래프·표 구조 있음 1 · 없음 2 · 헤딩 그래프·표 구조: 사업계획서 없음")
    assert [(p["doc"], p["role"], p["st"]) for p in heads["per"]] == [("a", "source", "todo"), ("b", "source", "done"), ("e", "source", "todo"), ("t", "target", "todo")]
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert rec["status"] == "done" and f.calls == [("heads", "a"), ("heads", "e"), ("heads", "t"), ("guides", "t")] and f.heads["d"] is False   # 하나씩 차례로 · 뒤 수정본이 있는 문서는 뺀다
    assert rec["steps"][0]["text"] == "기관 문서 3개의 헤딩 그래프·표 구조 — 이번에 분석 2개 · 사업계획서의 헤딩 그래프·표 구조가 있습니다" and rec["end"]["text"].startswith("끝남 — 기관 문서 3개의 헤딩")
    assert X.status_of("t")["stages"][0]["left"] == 0
    with pytest.raises(ValueError, match="한 문서만 진행은 원본 문서 하나 → 목적 문서 하나인 워크플로우"):   # 한 문서만 진행 · 문서마다 따로 도는 실행은 이 틀에 없다(원본이 여럿)
        X.start("t", {"from": "g1", "role": "source"})


def test_the_runs_pair_is_pinned_and_the_tidy_lines_wait_for_any_reflected_document(door, monkeypatch):
    f = door([_row("a", "todo", "가.hwpx")], [("넣기", [("link", []), ("plan", []), ("apply", [])]), ("정리", [("retidy", T)])])
    f.todo["a"] = 1
    task = S.definition(f.key)
    seen = []
    real = X._do_plan
    monkeypatch.setattr(X, "_do_plan", lambda run, gid, line: (seen.append((dict(run.pair.get("source") or {}), run.pinned.get("source"), run.bound, X._pair_ids(run))), real(run, gid, line))[1])
    f.retidy_facts = lambda doc: {"why": "", "fill": "m1", "applied": None, "inserted": 3}
    f.retidy = lambda doc: f.calls.append(("retidy", doc)) or Outcome("ok", "", {"done": {"counts": {"levels": 1, "fix": 2, "changed": 2}}})
    stub = types.SimpleNamespace(task=task, target="t")
    assert X._collect_fills(task) and X._fill_open(stub) is True   # 기관 문서가 하나도 반영되지 않았다 — 「문서 정리」 의 줄이 기다린다
    v = X.status_of("t")
    assert v["stages"][1]["steps"][0]["text"] == "1단계 「넣기」 이 끝난 뒤에 넣은 줄을 목적 문서의 템플릿 · 서식으로 맞춥니다" and v["stages"][1]["why"] == "1단계 「넣기」 이 먼저입니다"
    X.start("t", {"from": "g1", "to": "g2"})
    rec = _done("t")
    assert rec["status"] == "done" and seen == [({"id": "a", "name": "가.hwpx", "format": "hwpx"}, None, "a", ("a", "t"))]   # 덩이 안에서는 그 기관 문서가 원본 · 대상 고정은 시작할 때의 쌍으로 본다
    assert X._fill_open(stub) is False and [s["key"] for s in rec["steps"]] == ["link", "plan", "apply", "retidy"] and [g["status"] for g in rec["stages"]] == ["done", "done"] and f.calls[-1] == ("retidy", "t")
    run = X.Run({"docs": {"target": {"id": "t"}}, "job": f.key, "scope": ["시험", f.key, 1], "stopping": False, "n": 9}, task, f.pair("t"), None)
    run.pair = {**run.pinned, "source": {"id": "a"}}
    run.guard()   # 원본을 바꿔 끼운 동안에도 「도는 중에 문서 칸이 바뀜」 으로 멈추지 않는다
    f.rows.clear()
    assert X._fill_open(stub) is True


class CFit(CFake, FitFake):
    """가짜 문 + 목적 문서(사업계획서)의 프로젝트 구성 · 구조 반영 — 구성의 기준이 목적 문서 자신이다(기관 문서의 값은 읽지 않는다)."""

    def __init__(self, key, rows):
        super().__init__(key, rows)
        self.divs = {"t": {"input": None, "applied": None, "confirmed": None, "partial": [], "form": "연구개발계획서", "supported": True, "rev": 0, "read": None, "sharing": {"project": "시험", "shared": True}}}
        self.rev, self.hrev, self.asked, self.fits = {"t": 0}, {"t": 0}, {"t": False}, False   # fits = 구조가 이미 값에 맞는 문서(구조 확인이 반영 기록을 적는다)

    def config_confirm(self, doc, values=None):
        self.calls.append(("confirm", doc))
        self.divs[doc].update(input=values, confirmed={"values": values, "at": time.time(), "valid": True})
        return Outcome("ok", "", {})

    def division_adopt(self, doc, values=None):
        self.calls.append(("adopt", doc))
        if self.fits:
            self.divs[doc]["applied"] = {"values": self.divs[doc]["input"], "rev": self.rev[doc], "adopted": True}
        return Outcome("ok", "", {"adopted": self.fits})


@pytest.mark.parametrize("fits", [False, True])
def test_the_fit_stage_shapes_the_target_by_its_own_confirmed_values(door, monkeypatch, fits):
    """「구성 맞추기」 — 같이 쓰는 줄 그대로, 구성의 기준 = 목적 문서: 사업계획서에서 읽어 확정 → 제 값을 제 구조에(구조가 이미 맞으면 확인만 · 아니면 울타리 안 계획 → 반영) → 다시 문서 검토. 기관 문서는 읽지도 바꾸지도 않는다."""
    key = _make([("구성 맞추기", [("configLoad", []), ("config", []), ("take", []), ("division", T), ("reheads", T)])], name=f"구성 {fits}")["key"]
    f = CFit(key, [_row("a", "todo", "가.hwpx")])
    f.fits = fits
    monkeypatch.setattr(X, "UNIT", f)
    for k, v in (("settle", 0.05), ("limit", 0.8), ("poll", 0.005)):
        monkeypatch.setitem(X.FENCE_WAIT, k, v)
    g = X.status_of("t")["stages"][0]
    assert [(s["key"], s["st"]) for s in g["steps"]] == [("files", "done"), ("configLoad", "todo"), ("config", "now"), ("take", "todo"), ("division", "todo"), ("reheads", "todo")] and g["can"] and not g.get("wait")
    assert "사업계획서에서 추출하거나" in g["steps"][2]["text"]   # 구성의 기준 문서 = 사업계획서(기관 문서가 아니다)
    X.start("t", {"from": "g1"})
    rec = _done("t")
    assert rec["status"] == "done", rec["end"]
    docs = {c[1] for c in f.calls if len(c) > 1}
    assert docs == {"t"} and [c[0] for c in f.calls][:3] == ["read", "confirm", "takeDefault"]   # 기관 문서 a 는 부르지 않는다 · 「넣을 구성 선택」 은 올해의 차년도를 기본값으로 적고 지나간다
    if fits:
        assert [c[0] for c in f.calls] == ["read", "confirm", "takeDefault", "adopt"] and f.divs["t"]["applied"]["adopted"] is True and "사업계획서의 구조가 이미 값에 맞음(확인함)" in rec["end"]["text"]
    else:
        assert [c[0] for c in f.calls] == ["read", "confirm", "takeDefault", "adopt", "plan", "apply", "how", "heads", "how", "heads", "guides"] and f.divs["t"]["applied"]["rev"] == 1
        assert rec["end"]["text"].startswith("끝남 — 사업계획서에서 읽은 프로젝트 구성을 프로젝트 「시험」에 확정했습니다") and "구조를 맞췄습니다 — 사업계획서에 반영됨 — 1단계 · 전체 2년 · 기관 2곳 · 사업계획서를 다시 분석했습니다" in rec["end"]["text"]
    assert X.status_of("t")["stages"][0]["left"] == 0


def test_the_relay_and_gather_paths_stay_as_they_were(monkeypatch):
    """이관형 · 취합형은 그대로 — 넣기 계획에 기대한 원본을 넘기지 않고 · 「내용 넣기」 의 끝은 넣기 재료로 읽고 · 덩이는 취합의 것(_each) · 받은 서식 정리 계획의 반영은 이관형과 이 틀만."""
    relay, gather = S.definition("plan_to_report"), S.definition("plan_merge")
    calls, filled = [], [True]

    class Door:
        def fill_facts(self, target):
            return {"filled": filled[0], "plan": None, "links": None}

        def fill_plan(self, target, **kw):
            calls.append((target, kw))
            return Outcome("ok", "", {"planId": "p", "todo": 0})
    monkeypatch.setattr(X, "UNIT", Door())
    run = types.SimpleNamespace(task=relay, target="t", guard=lambda: None, note=lambda *a, **k: None)
    assert X._fill_open(run) is False and X._plan_now(run, "map", "넣기 계획")["planId"] == "p" and calls == [("t", {})]
    filled[0] = False
    assert X._fill_open(run) is True and X._fill_open(types.SimpleNamespace(task=gather, target="t")) is False   # 취합형 — 「내용 넣기」 의 줄(home)이 없어 기다리지 않는다(전과 같다)
    assert X.EACH.get(S.family(gather), X._each) is X._each and X.EACH.get(S.family(relay), X._each) is X._each
    assert X._tidy_after(types.SimpleNamespace(task=gather), "g", "reheadsLlm", "t", "취합본", "target") == ("", "")
    assert U.unit("take", "relay") is U.RELAY["take"] and U.unit("link", "gather") is U.GATHER["link"] and U.roles_in(U.COMMON["division"], "relay") == U.ROLES


def test_the_door_reads_the_registered_documents_as_the_sources(monkeypatch, tmp_path):
    """문(unit_steps.pair) — 같은 양식 취합의 원본 문서 = 등록부의 차례(merge_collect_api.order) · 원본 하나(source)는 없다 · 넣기 계획의 문은 기대한 원본을 몸에 싣는다."""
    from app import server, works
    c = TestClient(server.app)
    t = _make()
    key = t["key"]
    import io

    import docx
    def doc(name, kind):
        buf, d = io.BytesIO(), docx.Document()
        d.add_paragraph(name)
        d.save(buf)
        wid = c.post("/api/docs?new=1", files={"file": (name, buf.getvalue())}).json()["docId"]
        assert c.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": kind, "job": key, "project": "같은 양식"}).status_code == 200, (name, kind)
        return wid
    to, a, b = doc("계획서.docx", "plan"), doc("가.docx", "part"), doc("나.docx", "part")
    try:   # 엔진의 문(app/merge_collect_api.py)이 있으면 진짜로도 — 등록부는 같은 묶음의 기관 문서를 올린 차례로 저절로 싣는다 · 보기의 꼴이 실행기 · 상태 식이 읽는 것과 같다
        from app import merge_collect_api as real
    except ImportError:
        real = None
    if real is not None:
        assert [d["id"] for d in unit_steps.pair(a)["sources"]] == [a, b] and unit_steps.pair(a)["source"] is None
        V = unit_steps.collect(to)
        assert V["collect"] is True and [(p["work"], p["state"]) for p in U.collect_rows(V)] == [(a, "unassigned"), (b, "unassigned")] and not U.collect_filled(V)
        assert {"work", "name", "orgs", "orgNames", "revOf", "later", "state", "text", "done"} <= set(V["parts"][0])
        got = unit_steps.collect_auto(to, a)   # 프로젝트 구성이 없다 — 못 정하고 까닭을 준다(문서는 안 바뀐다)
        assert got.ok and got.data["auto"]["part"] == a and not got.data["auto"]["org"] and got.data["auto"]["why"]
        assert unit_steps.collect_bind(to, "없는 문서").code == "missing" and unit_steps.collect_revise_plan(to, a).code == "blocked"   # 등록부에 없는 문서 · 수정본으로 등록하지 않은 문서
    stub = types.SimpleNamespace(order=lambda target: [b, a] if target == to else [])
    monkeypatch.setitem(sys.modules, "app.merge_collect_api", stub)
    import app
    monkeypatch.setattr(app, "merge_collect_api", stub, raising=False)
    for wid in (to, a, b):   # 어느 칸의 문서에서 불러도 같은 묶음
        pair = unit_steps.pair(wid)
        assert pair["job"] == key and pair["target"]["id"] == to and pair["source"] is None and [d["id"] for d in pair["sources"]] == [b, a] and pair["kinds"] == {"target": "plan", "source": "part"}, wid
    assert works.TARGET_FILE.get(key) == "plan"
    got = []
    from app import merge_api
    monkeypatch.setattr(merge_api, "merge_plan", lambda doc_id, body: got.append((doc_id, body)) or {"planId": "p"})
    assert unit_steps.fill_plan(to, part=a).data == {"planId": "p"} and unit_steps.fill_plan(to).ok and got == [(to, {"part": a}), (to, {})]   # 몸을 늘 넘긴다(Body 기본값을 타지 않는다)
    assert unit_steps.heads_have(to) is False and unit_steps.heads_have("없는 문서") is False   # 세션을 열지 않는다(docx — 분석 없음)
