"""조립한 TASK(spec_워크플로우 ② §14 · app/custom_tasks.py · API /api/tasks) — 화면에서 단계를 골라 만든 TASK: 저장 · 검사 · 서버가 그 키를 TASK 로 받음 · 등록부에 조립돼 섬 · 전제 · 원본/목적 문서."""
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
