"""조립한 TASK(spec_워크플로우 ② §14 · app/custom_tasks.py · API /api/tasks) — 화면에서 단계를 골라 만든 TASK: 저장 · 검사 · 서버가 그 키를 TASK 로 받음 · 등록부에 조립돼 섬 · 전제 · 원본/목적 문서 ·
문서마다 단위문서 TASK(② §15 — 원본 · 목적 문서마다 고른 단계 assign · 옛 줄 호환 · 칸 cells · /api/workflow 의 roles)."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import custom_tasks as C
from app import job_prompts, server, workflow, works


@pytest.fixture
def client():
    yield TestClient(server.app)


def test_stage_ids_follow_the_registry():
    assert C.STAGES == tuple(m[0] for m in workflow.STAGE_MODULES) and set(C.STAGE_GROUP) == set(C.STAGES)   # 일반 단계의 차례 = 등록부의 단계 차례
    assert C.FILES == works.FILE_LABEL and all(a in C.FILES and b in C.FILES and a != b for a, b in C.PAIRS) and C.BASE in workflow.BY_JOB
    assert C.ROLES == tuple(r for r, _ in workflow.ROLES) and C.ROLE_STAGES == {"source": ("stage_review",), "target": C.STAGES}   # 원본 문서는 「문서 검토」 만(② §15)


def test_create_validates_and_keeps_the_general_order():
    t = C.create({"name": "  구성만   맞추기 ", "stages": ["stage_fit", "stage_review"], "desc": "프레임까지"}, ["사업계획서 취합"])
    assert C.KEY.fullmatch(t["key"]) and t["name"] == "구성만 맞추기" and t["stages"] == ["stage_review", "stage_fit"] and (t["source"], t["target"]) == ("plan", "report")   # 고른 것만 · 차례는 일반 단계의 차례
    assert C.get(t["key"])["desc"] == "프레임까지" and C.is_key(t["key"]) and not C.is_key("plan_to_report") and not C.is_key("u_zzzzzzzz")
    for body, word in (({"name": "", "stages": ["stage_fit"]}, "이름"), ({"name": "구성만 맞추기", "stages": ["stage_fit"]}, "이미 있는"), ({"name": "사업계획서 취합", "stages": ["stage_fit"]}, "이미 있는"),
                       ({"name": "새", "stages": []}, "하나 이상"), ({"name": "새", "stages": ["nope"]}, "단계"), ({"name": "새", "stages": ["stage_fit"], "source": "plan", "target": "plan"}, "문서 쌍"),
                       ({"name": "x" * 41, "stages": ["stage_fit"]}, "40자")):
        with pytest.raises(ValueError, match=word):
            C.create(body, ["사업계획서 취합"])
    u = C.update(t["key"], {"stages": ["stage_clean", "stage_fill"], "premise": "실적은 비워 둔다"})
    assert u["stages"] == ["stage_fill", "stage_clean"] and u["name"] == "구성만 맞추기" and u["premise"] == "실적은 비워 둔다"
    with pytest.raises(ValueError, match="문서 쌍"):
        C.update(t["key"], {"source": "report"})
    assert C.update("u_00000000", {"name": "없음"}) is None and C.delete(t["key"]) and not C.delete(t["key"]) and C.all() == []


def test_server_takes_the_key_as_a_task_and_knows_its_documents(client):
    t = C.create({"name": "넣기만", "stages": ["stage_fill"]})
    key = t["key"]
    assert works.TARGET_FILE.get(key) == "report" and key in works.TARGET_FILE and works.TARGET_FILE[key] == "report" and "u_00000000" not in works.TARGET_FILE
    assert works.TARGET_FILE == {"plan_to_report": "report", "plan_merge": "plan"}   # 붙박이 사전의 내용은 그대로(조립한 TASK 는 저장소에서 읽는다)
    assert C.source_file(key) == "plan" and C.source_file("plan_to_report") == "plan" and C.target_file("plan_to_report") is None
    d = client.post("/api/docs?new=1", files={"file": ("a.docx", _docx())}).json()["docId"]
    ok = client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": key, "project": "조립"})
    assert ok.status_code == 200 and ok.json()["task"]["job"] == key
    assert client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": "report", "job": "u_00000000", "project": "조립"}).status_code == 400   # 저장소에 없는 키
    gone = client.delete(f"/api/tasks/{key}")
    assert gone.status_code == 409 and "1개" in gone.json()["detail"]   # 그 TASK 로 하던 작업이 있으면 못 지운다


def _docx():
    import io

    import docx
    f, d = io.BytesIO(), docx.Document()
    d.add_paragraph("글")
    d.save(f)
    return f.getvalue()


def test_premise_is_the_written_text_or_the_base_tasks(monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("NFM_JOBS", str(Path(__file__).parents[1] / "jobs"))   # 저장소의 jobs/(conftest 는 임시 폴더로 돌려 둔다)
    a, b = C.create({"name": "물려받음", "stages": ["stage_fill"]}), C.create({"name": "제 전제", "stages": ["stage_fill"], "premise": "계획 쪽만 넣는다"})
    base, pa, pb = job_prompts.get(C.BASE), job_prompts.get(a["key"]), job_prompts.get(b["key"])
    assert pa["text"] == base["text"] and pa["job"] == a["key"] and "물려받음" in pa["name"]   # 비우면 틀이 같은 붙박이 TASK(이관)의 전제
    assert pb["text"] == "계획 쪽만 넣는다" and pb["name"] == "제 전제" and pb["path"] == ""


def test_api_lists_creates_edits_and_the_registry_assembles_it(client):
    v = client.get("/api/tasks").json()
    assert v["tasks"] == [] and [s["id"] for s in v["stages"]] == list(C.STAGES) and [s["name"] for s in v["stages"]] == ["문서 검토", "구성 맞추기", "내용 넣기", "문서 정리"]
    assert v["pairs"] == [{"source": "plan", "target": "report", "name": "사업계획서 → 연차보고서"}] and len(v["blocked"]) == 2 and v["base"] == "plan_to_report"
    assert client.post("/api/tasks", json={"name": "", "stages": ["stage_fit"]}).status_code == 400
    r = client.post("/api/tasks", json={"name": "구성 맞추고 넣기", "desc": "정리는 안 함", "stages": ["stage_fill", "stage_fit"]})
    t = r.json()["task"]
    assert r.status_code == 201 and t["groups"] == ["frame", "map"] and t["sourceName"] == "사업계획서" and t["targetName"] == "연차보고서"
    L = client.get("/api/workflow").json()
    mine = L["tasks"][-1]
    assert mine["job"] == t["key"] and mine["custom"] and mine["name"] == "구성 맞추고 넣기" and mine["doc"] == "" and mine["prompt"] is None and mine["base"] == "plan_to_report"
    assert [(g["id"], g["no"], g["name"], g["module"]) for g in mine["stages"]] == [("frame", "1단계", "구성 맞추기", "stage_fit"), ("map", "2단계", "내용 넣기", "stage_fill")]   # 고른 단계만 · 번호는 1부터 다시
    assert [s["key"] for s in mine["stages"][0]["steps"]] == ["files", "configLoad", "config", "division", "reheads", "reheadsLlm"]   # 맨 앞 묶음이 「준비」 를 가진다
    used = {c["id"]: c["usedBy"] for c in L["common"]}
    assert used["stage_fit"] == ["plan_to_report", t["key"]] and used["stage_review"] == ["plan_to_report"] and t["key"] in used["division"]
    assert [x["job"] for x in L["tasks"][:-1]] == [x["job"] for x in workflow.TASKS] and t["key"] not in workflow.markdown()   # 붙박이 등록부 · 만든 글(workflow.md)은 그대로
    js = client.get("/api/tasks.js")
    assert js.headers["cache-control"] == "no-store" and "javascript" in js.headers["content-type"] and js.text.startswith('if (typeof taskCatalogCustom === "function") taskCatalogCustom([') and t["key"] in js.text
    e = client.put(f"/api/tasks/{t['key']}", json={"name": "넣기까지", "stages": ["stage_review", "stage_fit", "stage_fill"]}).json()["task"]
    assert e["name"] == "넣기까지" and e["groups"] == ["review", "frame", "map"] and client.put("/api/tasks/u_00000000", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/tasks/{t['key']}").json() == {"deleted": True} and client.get("/api/tasks").json()["tasks"] == [] and client.delete(f"/api/tasks/{t['key']}").status_code == 404


def test_assign_picks_steps_per_document_and_still_takes_the_old_form():
    """문서마다 단위문서 TASK(spec_워크플로우 ② §15 「문서마다 단위문서 TASK」 — 2026-11-19 사용자 "목적문서랑 원본문서에 대해서 각각 task 를 할당할 수 있도록 해줘"):
    assign = 원본 · 목적 문서마다 고른 단계(일반 차례 — 원본은 「문서 검토」 만) · stages = 두 역할의 합집합(같이 씀) · 옛 꼴(stages 만)도 받는다(assign 이 먼저)."""
    t = C.create({"name": "문서마다", "assign": {"source": ["stage_review"], "target": ["stage_fill", "stage_review"]}})
    assert t["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"]} and t["stages"] == ["stage_review", "stage_fill"]
    assert C.create({"name": "원본만", "assign": {"source": ["stage_review"], "target": []}})["stages"] == ["stage_review"]   # 하나 이상이면 된다(원본만 검토)
    assert C.create({"name": "옛 꼴", "stages": ["stage_fill", "stage_review"]})["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_fill"]}   # 전의 동작(두 문서 분석 + 원본 LLM)
    assert C.create({"name": "옛 꼴 둘", "stages": ["stage_fit"]})["assign"] == {"source": [], "target": ["stage_fit"]}
    assert C.create({"name": "둘 다 보냄", "assign": {"source": [], "target": ["stage_clean"]}, "stages": ["stage_fill"]})["stages"] == ["stage_clean"]   # assign 이 먼저(stages 는 옛 꼴 — assign 이 없을 때만)
    for body, word in (({"name": "새", "assign": {"source": ["stage_fit"], "target": ["stage_fit"]}}, C.SOURCE_ONLY),
                       ({"name": "새", "assign": {"source": ["stage_review", "stage_clean"], "target": []}}, C.SOURCE_ONLY),
                       ({"name": "새", "assign": {"source": [], "target": []}}, "단계를 하나 이상 고르세요"), ({"name": "새", "assign": {}}, "단계를 하나 이상 고르세요"),
                       ({"name": "새", "assign": {"source": [], "target": ["nope"]}}, "단계를 고르세요"), ({"name": "새", "assign": ["stage_fit"]}, "단계를 고르세요"),
                       ({"name": "새", "assign": {"source": "stage_review", "target": []}}, "단계를 고르세요")):
        with pytest.raises(ValueError, match=re.escape(word)):
            C.create(body)
    assert C.SOURCE_ONLY == "원본 문서는 이 워크플로우에서 바뀌지 않아 「문서 검토」 만 고를 수 있습니다"
    u = C.update(t["key"], {"assign": {"source": [], "target": ["stage_fit", "stage_review"]}})
    assert u["assign"] == {"source": [], "target": ["stage_review", "stage_fit"]} and u["stages"] == ["stage_review", "stage_fit"] and u["name"] == "문서마다"
    assert C.update(t["key"], {"name": "이름만"})["assign"] == u["assign"]   # 단계를 안 보내면 그대로
    o = C.update(t["key"], {"stages": ["stage_clean", "stage_review"]})   # 옛 꼴로 고쳐도 assign 이 따라간다
    assert o["assign"] == {"source": ["stage_review"], "target": ["stage_review", "stage_clean"]} and o["stages"] == ["stage_review", "stage_clean"] and set(o) == set(t)
    got = C.get(t["key"])
    got["assign"]["target"].append("stage_fill")
    got["stages"].append("stage_fill")
    assert C.get(t["key"])["assign"]["target"] == ["stage_review", "stage_clean"] and C.get(t["key"])["stages"] == ["stage_review", "stage_clean"]   # 사본 — 돌려받은 값을 고쳐도 저장소는 그대로


def test_old_lines_without_assign_are_read_and_kept(client):
    """옛 줄(assign 없이 stages 만 — ② §14 의 꼴)은 버리지 않고 읽는다: 원본 = 「문서 검토」 가 있으면 [문서 검토] · 목적 = stages. 저장소를 다시 쓰면 새 꼴로 남는다.
    「구성 맞추기」 가 있는 옛 줄은 전의 동작 그대로(두 문서 분석 + 원본 LLM) — 없는 옛 줄은 목적 문서의 LLM 검증·보완도 「문서 검토」 에서 선다(② §15 「실행」 의 규칙 — 전에는 목적 문서의 LLM 이 어디에도 없었다)."""
    p = C.path()
    old = [{"key": "u_0000aaaa", "name": "옛 TASK", "desc": "전의 꼴", "source": "plan", "target": "report", "stages": ["stage_fill", "stage_review", "stage_fit"], "premise": "", "at": 1.0},
           {"key": "u_0000bbbb", "name": "옛 TASK 둘", "desc": "", "source": "plan", "target": "report", "stages": ["stage_fit", "stage_fill"], "premise": "계획 쪽만", "at": 2.0},
           {"key": "u_0000cccc", "name": "옛 TASK 셋", "desc": "", "source": "plan", "target": "report", "stages": ["stage_review", "stage_fill"], "premise": "", "at": 3.0},
           {"key": "u_0000dddd", "name": "새 꼴", "desc": "", "source": "plan", "target": "report", "assign": {"source": ["stage_review", "stage_fit"], "target": ["stage_clean"]}, "stages": ["stage_fill"],
            "premise": "", "at": 4.0}]   # 새 꼴 — assign 이 먼저(원본의 문서 검토 밖 단계는 버리고 stages 는 다시 셈)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 3, "tasks": old}, ensure_ascii=False), encoding="utf-8")
    assert [(t["key"], t["assign"], t["stages"]) for t in C.all()] == [
        ("u_0000aaaa", {"source": ["stage_review"], "target": ["stage_review", "stage_fit", "stage_fill"]}, ["stage_review", "stage_fit", "stage_fill"]),
        ("u_0000bbbb", {"source": [], "target": ["stage_fit", "stage_fill"]}, ["stage_fit", "stage_fill"]),
        ("u_0000cccc", {"source": ["stage_review"], "target": ["stage_review", "stage_fill"]}, ["stage_review", "stage_fill"]),
        ("u_0000dddd", {"source": ["stage_review"], "target": ["stage_clean"]}, ["stage_review", "stage_clean"])]
    mine = {t["job"]: t for t in workflow.custom()}
    relay = next(g for g in workflow.BY_JOB["plan_to_report"]["stages"] if g["id"] == "review")
    assert [(s["key"], s["on"], s["does"]) for s in mine["u_0000aaaa"]["stages"][0]["steps"]] == [(s["key"], s["on"], s["does"]) for s in relay["steps"]]   # 전의 동작 = 붙박이 이관의 문서 검토(글까지)
    assert [g["id"] for g in mine["u_0000aaaa"]["stages"]] == ["review", "frame", "map"] and [g["id"] for g in mine["u_0000bbbb"]["stages"]] == ["frame", "map"]
    assert [(s["key"], s["on"]) for s in mine["u_0000cccc"]["stages"][0]["steps"]] == [("files", "both"), ("heads", "both"), ("headsLlm", "both")]   # 구성 맞추기가 없음 — 목적 문서의 LLM 도 여기서
    v = client.get("/api/tasks").json()["tasks"]
    assert [t["key"] for t in v] == ["u_0000aaaa", "u_0000bbbb", "u_0000cccc", "u_0000dddd"] and v[0]["assign"]["source"] == ["stage_review"] and v[0]["groups"] == ["review", "frame", "map"]
    assert v[3]["groups"] == ["review", "clean"]
    C.create({"name": "새 것", "assign": {"source": [], "target": ["stage_clean"]}})   # 저장소를 다시 쓴다 — 옛 줄은 사라지지 않고 새 꼴(assign + 합집합 stages)로
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["version"] == 4 and [t["key"] for t in saved["tasks"]][:4] == ["u_0000aaaa", "u_0000bbbb", "u_0000cccc", "u_0000dddd"] and len(saved["tasks"]) == 5
    assert saved["tasks"][0] == {**old[0], "assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fit", "stage_fill"]}, "stages": ["stage_review", "stage_fit", "stage_fill"]}
    assert saved["tasks"][1]["assign"] == {"source": [], "target": ["stage_fit", "stage_fill"]} and saved["tasks"][1]["premise"] == "계획 쪽만"


def test_api_view_has_assign_and_cells_and_the_registry_builds_unit_tasks(client):
    """GET /api/tasks 의 단계마다 문서 역할의 칸(cells — pick · follow · no) · 조립한 TASK 의 assign · /api/workflow 의 roles(단위문서 TASK) · 「LLM 검증·보완」 이 서는 때(② §15)."""
    v = client.get("/api/tasks").json()
    cells = {s["id"]: s["cells"] for s in v["stages"]}
    assert {k: (c["source"]["mode"], c["target"]["mode"]) for k, c in cells.items()} == {"stage_review": ("pick", "pick"), "stage_fit": ("follow", "pick"), "stage_fill": ("follow", "pick"), "stage_clean": ("no", "pick")}
    assert cells["stage_review"]["source"]["text"] == "헤딩 · 표 분석 → LLM 검증·보완" and "「구성 맞추기」 를 고르면" in cells["stage_review"]["target"]["text"] and "「다시 문서 검토(LLM)」" in cells["stage_review"]["target"]["text"]
    assert cells["stage_fit"]["source"]["text"] == "구성의 기준 — 구성 불러오기 · 프로젝트 구성 확정(문서는 안 바뀜)" and cells["stage_fill"]["source"]["text"] == "내용을 줌(바뀌지 않음)"
    assert "← 원본 문서" in cells["stage_fill"]["target"]["text"] and cells["stage_clean"]["source"]["text"] == "원본은 바꾸지 않습니다" and all(c[r]["text"] for c in cells.values() for r in C.ROLES)
    bad = client.post("/api/tasks", json={"name": "x", "assign": {"source": ["stage_clean"], "target": ["stage_clean"]}})
    assert bad.status_code == 400 and bad.json()["detail"] == C.SOURCE_ONLY
    assert client.post("/api/tasks", json={"name": "x", "assign": {"source": [], "target": []}}).json()["detail"] == "단계를 하나 이상 고르세요"
    a = client.post("/api/tasks", json={"name": "목적만 구성까지", "assign": {"source": [], "target": ["stage_fit", "stage_review"]}}).json()["task"]
    b = client.post("/api/tasks", json={"name": "목적만 검토", "assign": {"source": [], "target": ["stage_review", "stage_fill"]}}).json()["task"]
    c = client.post("/api/tasks", json={"name": "두 문서 검토", "assign": {"source": ["stage_review"], "target": ["stage_review", "stage_fit", "stage_fill"]}}).json()["task"]
    assert set(a) == {"key", "name", "desc", "source", "target", "assign", "stages", "premise", "at", "sourceName", "targetName", "groups"}
    assert a["assign"] == {"source": [], "target": ["stage_review", "stage_fit"]} and a["stages"] == ["stage_review", "stage_fit"] and a["groups"] == ["review", "frame"]
    listed = {t["key"]: t for t in client.get("/api/tasks").json()["tasks"]}
    assert listed[a["key"]]["assign"] == a["assign"] and listed[a["key"]]["inUse"] == 0 and set(listed[a["key"]]) == set(a) | {"inUse"}
    assert '"assign": {"source": [], "target": ["stage_review", "stage_fit"]}' in client.get("/api/tasks.js").text   # 화면이 스크립트로 읽는 꼴(view)에도 든다
    L = {t["job"]: t for t in client.get("/api/workflow").json()["tasks"]}
    on = lambda key, gid: [(s["key"], s["on"]) for g in L[key]["stages"] if g["id"] == gid for s in g["steps"]]  # noqa: E731
    assert on(a["key"], "review") == [("files", "both"), ("heads", "target")]   # 원본은 검토를 안 고름 · 목적은 「구성 맞추기」 를 골라 LLM 은 「다시 문서 검토(LLM)」 에서 — 「LLM 검증·보완」 이 서지 않는다
    assert on(b["key"], "review") == [("files", "both"), ("heads", "target"), ("headsLlm", "target")]   # 목적만 검토 · 구성 맞추기 없음 — LLM 검증·보완은 목적 문서가 여기서
    assert on(c["key"], "review") == [("files", "both"), ("heads", "both"), ("headsLlm", "source")]   # 붙박이 이관과 같다
    assert all(s["on"] in workflow.ON for k in (a["key"], b["key"], c["key"]) for g in L[k]["stages"] for s in g["steps"])   # 문서 여럿인 워크플로우 — 모든 단계에 하는 문서
    assert L[a["key"]]["roles"] == [
        {"role": "source", "name": "사업계획서", "kind": "plan", "many": False, "unit": [{"stage": "review", "steps": ["files"]}, {"stage": "frame", "steps": ["configLoad", "config"]}]},
        {"role": "target", "name": "연차보고서", "kind": "report", "many": False, "unit": [{"stage": "review", "steps": ["files", "heads"]}, {"stage": "frame", "steps": ["division", "reheads", "reheadsLlm"]}]}]
    assert L[c["key"]]["roles"][1]["unit"][-1] == {"stage": "map", "steps": ["link", "llm", "plan", "tableMap", "gaps", "apply", "later"]} and L[c["key"]]["output"] == "고른 단계(문서 검토 → 구성 맞추기 → 내용 넣기)를 마친 연차보고서"
    e = client.put(f"/api/tasks/{b['key']}", json={"assign": {"source": ["stage_review"], "target": ["stage_review"]}}).json()["task"]
    assert e["stages"] == ["stage_review"] and e["groups"] == ["review"] and e["assign"] == {"source": ["stage_review"], "target": ["stage_review"]}
    L2 = {t["job"]: t for t in client.get("/api/workflow").json()["tasks"]}
    assert [(s["key"], s["on"]) for s in L2[b["key"]]["stages"][0]["steps"]] == [("files", "both"), ("heads", "both"), ("headsLlm", "both")]   # 두 문서 다 검토 · 구성 맞추기 없음 — LLM 도 두 문서
    assert client.put(f"/api/tasks/{b['key']}", json={"assign": {"source": ["stage_fit"], "target": ["stage_fit"]}}).json()["detail"] == C.SOURCE_ONLY
