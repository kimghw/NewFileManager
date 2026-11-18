"""프로젝트별 TASK·라운드 격리와 공유 구분 기준, 문서 보존 분기."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app import projects, server, works

SAMPLE = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
VALUES = {"stages": [2, 1], "orgs": {"lead": "주관 A", "joint": ["공동 B"]}}
CHANGED = {"stages": [1, 2], "orgs": {"lead": "주관 C", "joint": ["공동 D"]}}


@pytest.fixture
def client(monkeypatch):
    server.DOCS.clear()
    monkeypatch.setattr(server, "_start", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_ensure_persister", lambda: None)
    with TestClient(server.app) as client:
        yield client
    server.DOCS.clear()


def upload(client, role="plan", job="plan_to_report", project="프로젝트 A", number=1):
    response = client.post("/api/docs?new=1", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    assert response.status_code == 200, response.text
    wid = response.json()["docId"]
    response = client.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": role, "job": job, "project": project, "round": number})
    assert response.status_code == 200, response.text
    return wid


def settings(client, wid, values):
    response = client.put(f"/api/docs/{wid}/divisions/settings", json={"values": values})
    assert response.status_code == 200, response.text
    return response.json()["settings"]


def divisions(client, wid):
    response = client.get(f"/api/docs/{wid}/divisions")
    assert response.status_code == 200, response.text
    return response.json()


def branch(client, wid, source="current"):
    response = client.post(f"/api/works/{wid}/round", json={"source": source})
    assert response.status_code == 200, response.text
    return response.json()


def test_projects_allow_distinct_tasks_and_rounds(client):
    a = upload(client, job="plan_fit")
    b = upload(client, job="report_fit", role="report")
    old = upload(client, job="plan_fit", number=2)
    assert works.work(a)["task"]["job"] == "plan_fit"
    assert works.work(b)["task"]["job"] == "report_fit"
    listing = client.get("/api/projects").json()["projects"]
    assert len(listing) == 1 and listing[0]["name"] == "프로젝트 A"
    groups = {(item["job"], item["round"]): item for item in listing[0]["tasks"]}
    assert groups["plan_fit", 1]["status"] == "previous"
    assert groups["plan_fit", 2]["docId"] == old
    assert groups["report_fit", 1]["latest"] is True
    assert set(listing[0]["works"]) == {a, b, old}


def test_shared_settings_only_latest_round_and_same_project(client):
    plan = upload(client)
    report = upload(client, role="report")
    other_task = upload(client, job="plan_fit")
    outside = upload(client, project="프로젝트 B")
    original = settings(client, plan, VALUES)
    assert divisions(client, report)["settings"] == original
    assert divisions(client, other_task)["settings"] == original
    assert divisions(client, outside)["settings"] is None
    server.DOCS[report].division["applied"] = {"values": original["values"], "rev": 7}
    branched = branch(client, report)
    new_report = branched["docId"]
    assert divisions(client, new_report)["applied"]["rev"] == 0
    assert divisions(client, new_report)["applied"]["inheritedFrom"] == report
    new_settings = settings(client, new_report, CHANGED)
    assert divisions(client, plan)["settings"] == original
    assert divisions(client, report)["settings"] == original
    assert divisions(client, report)["projectSharing"] == {"project": "프로젝트 A", "round": 1, "latestRound": 2, "shared": False}
    assert divisions(client, branched["mapping"][plan])["settings"] == new_settings
    assert divisions(client, other_task)["settings"] == new_settings
    assert divisions(client, outside)["settings"] is None
    # 이전 라운드의 입력 수정은 현재 프로젝트 구성에 퍼지지 않는다.
    settings(client, report, {"stages": [4], "orgs": {"lead": "이전 라운드"}})
    assert divisions(client, new_report)["settings"] == new_settings
    server._persist_all()
    server.DOCS.clear()
    assert divisions(client, plan)["settings"] == original
    assert divisions(client, new_report)["settings"] == new_settings
    assert projects.get("프로젝트 A")["settings"] == new_settings


def test_new_round_copies_all_group_documents_and_preserves_old(client):
    plan = upload(client)
    report = upload(client, role="report")
    outside = upload(client, project="프로젝트 B")
    other_task = upload(client, job="plan_fit")
    session = server.DOCS[report]
    pid = next(pid for pid, value in session.texts.items() if len(value.strip()) > 10)
    changed_text = session.texts[pid] + " 새 라운드에 남길 수정"
    assert client.patch(f"/api/docs/{report}/blocks/{pid}", json={"text": changed_text}).status_code == 200
    before = client.get(f"/api/docs/{report}/download").content
    response = branch(client, report)
    assert response["round"] == 2 and response["sourceRound"] == 1
    assert set(response["mapping"]) == {plan, report}
    assert outside not in response["mapping"] and other_task not in response["mapping"]
    new_report = response["docId"]
    assert new_report != report
    assert client.get(f"/api/docs/{new_report}/download").content == before
    assert client.get(f"/api/docs/{report}/download").content == before
    assert works.work(new_report)["roundParent"] == report
    assert works.work(new_report)["task"]["round"] == 2
    assert works.work(report)["task"]["round"] == 1
    assert client.get(f"/api/docs/{new_report}").json()["editedCount"] == 0
    assert branch(client, report)["round"] == 3  # 이전 라운드에서 다시 갈라져도 번호는 겹치지 않는다.


def test_original_round_uses_uploaded_bytes(client):
    report = upload(client, role="report")
    session = server.DOCS[report]
    pid = next(pid for pid, value in session.texts.items() if value.strip())
    client.patch(f"/api/docs/{report}/blocks/{pid}", json={"text": "원본 라운드에는 없어야 함"})
    response = branch(client, report, "original")
    assert client.get(f"/api/docs/{response['docId']}/download").content == SAMPLE.read_bytes()
    assert client.get(f"/api/docs/{report}/download").content != SAMPLE.read_bytes()
    assert divisions(client, response["docId"])["applied"] is None


def test_default_round_uses_first_upload_after_current_copy(client):
    report = upload(client, role="report")
    session = server.DOCS[report]
    pid = next(pid for pid, value in session.texts.items() if value.strip())
    assert client.patch(f"/api/docs/{report}/blocks/{pid}", json={"text": "첫 라운드 수정"}).status_code == 200
    copied = branch(client, report, "current")["docId"]
    copied_session = server.DOCS[copied]
    copied_pid = next(pid for pid, value in copied_session.texts.items() if value.strip())
    assert client.patch(f"/api/docs/{copied}/blocks/{copied_pid}", json={"text": "둘째 라운드 수정"}).status_code == 200
    before = {wid: client.get(f"/api/docs/{wid}/download").content for wid in (report, copied)}
    response = client.post(f"/api/works/{copied}/round", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source"] == "original" and result["round"] == 3
    assert client.get(f"/api/docs/{result['docId']}/download").content == SAMPLE.read_bytes()
    assert all(client.get(f"/api/docs/{wid}/download").content == content for wid, content in before.items())
    assert divisions(client, result["docId"])["applied"] is None


def test_settings_change_invalidates_another_documents_plan(client):
    first, second = upload(client), upload(client, role="report")
    saved = settings(client, first, VALUES)
    divisions(client, second)
    server.DOCS[second].division["plan"] = {"planId": "old-plan", "settingsHash": server.division_model.settings_hash(saved)}
    settings(client, first, CHANGED)
    response = client.post(f"/api/docs/{second}/divisions/apply", json={"planId": "old-plan"})
    assert response.status_code == 409
    assert server.DOCS[second].division["plan"] is None


def test_invalid_round_and_unnamed_project_rejected(client):
    wid = upload(client, project="")
    assert client.post(f"/api/works/{wid}/round", json={}).status_code == 400
    for number in (0, -1, True, "2", 1000001):
        response = client.put(f"/api/works/{wid}/task", json={"round": number})
        assert response.status_code == 400
    assert client.post(f"/api/works/{wid}/round", json={"source": "unknown"}).status_code == 400


def test_broken_project_settings_are_not_overwritten(client):
    wid = upload(client)
    path = works.root() / "projects.json"
    path.write_text("{broken", encoding="utf-8")
    assert client.get("/api/projects").status_code == 409
    assert client.put(f"/api/docs/{wid}/divisions/settings", json={"values": VALUES}).status_code == 409
    assert path.read_text("utf-8") == "{broken"


def test_start_task_validates_fields_and_preserves_assigned_work(client):
    wid = upload(client, project="", job="")
    body = {"project": "프로젝트 A", "job": "plan_fit", "file": "plan"}
    for bad in ({"project": "  "}, {"project": 3}, {"job": "unknown"}, {"job": ""}, {"file": "unknown"}):
        assert client.post(f"/api/works/{wid}/start-task", json={**body, **bad}).status_code == 400
    started = client.post(f"/api/works/{wid}/start-task", json={**body, "project": " 프로젝트   A "})
    assert started.status_code == 200, started.text
    # division = 들어감 알림의 근거(② §10·§19) — work_task 응답에서 따라 나온다 · temp = 임시 이름을 받았나(② §17 「임시 프로젝트」)
    assert started.json() == {"docId": wid, "round": 1, "division": "none", "temp": False,
                              "task": {"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "프로젝트 A", "round": 1}}
    before = works.work(wid)["task"]
    assert client.post(f"/api/works/{wid}/start-task", json={**body, "project": "프로젝트 B"}).status_code == 409
    assert works.work(wid)["task"] == before


def test_start_task_allocates_unique_rounds_and_freezes_previous_settings(client):
    first = upload(client, project="", job="")
    body = {"project": "프로젝트 A", "job": "plan_fit", "file": "plan"}
    assert client.post(f"/api/works/{first}/start-task", json=body).json()["round"] == 1
    initial = settings(client, first, VALUES)
    second, third = upload(client, project="", job=""), upload(client, project="", job="")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda wid: client.post(f"/api/works/{wid}/start-task", json=body), [second, third]))
    assert all(response.status_code == 200 for response in responses)
    assert {response.json()["round"] for response in responses} == {2, 3}
    latest = next(response.json()["docId"] for response in responses if response.json()["round"] == 3)
    settings(client, latest, CHANGED)
    assert divisions(client, first)["settings"] == initial
    earlier = next(response.json()["docId"] for response in responses if response.json()["round"] == 2)
    assert divisions(client, earlier)["settings"] == initial
    separate = upload(client, project="", job="")
    response = client.post(f"/api/works/{separate}/start-task", json={**body, "job": "report_fit", "file": "report"})
    assert response.status_code == 200 and response.json()["round"] == 1


def project_url(name):
    return f"/api/projects/{quote(name, safe='')}"


def test_rename_project_moves_every_task_round_and_shared_settings(client):
    plan = upload(client)
    other_task = upload(client, job="plan_fit")
    outside = upload(client, project="프로젝트 B")
    saved = settings(client, plan, VALUES)
    newer = branch(client, plan)["docId"]
    response = client.put(project_url("프로젝트 A"), json={"name": "  새   이름 "})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "새 이름"
    assert set(response.json()["works"]) == {plan, other_task, newer}
    assert works.work(plan)["task"] == {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "새 이름", "round": 1}
    assert works.work(newer)["task"]["project"] == "새 이름" and works.work(newer)["task"]["round"] == 2
    assert works.work(other_task)["task"]["project"] == "새 이름" and works.work(other_task)["task"]["job"] == "plan_fit"
    assert works.work(outside)["task"]["project"] == "프로젝트 B"
    assert projects.get("프로젝트 A") is None
    assert projects.get("새 이름")["settings"] == saved
    assert divisions(client, newer)["settings"] == saved
    assert divisions(client, other_task)["settings"] == saved
    assert divisions(client, plan)["projectSharing"] == {"project": "새 이름", "round": 1, "latestRound": 2, "shared": False}
    assert {item["name"] for item in client.get("/api/projects").json()["projects"]} == {"새 이름", "프로젝트 B"}
    assert '"kind":"renameProject"' in (works.root() / plan / "log.jsonl").read_text("utf-8")


def test_rename_project_rejects_conflicts_and_bad_names(client):
    a = upload(client)
    b = upload(client, project="프로젝트 B")
    gone = upload(client, project="프로젝트 C")
    settings(client, gone, VALUES)
    assert client.delete(f"/api/works/{gone}").status_code == 200  # 작업은 없고 projects.json 기록만 남은 이름
    before = works.work(a)["task"]
    assert client.put(project_url("프로젝트 A"), json={"name": "프로젝트 B"}).status_code == 409
    assert client.put(project_url("프로젝트 A"), json={"name": "프로젝트 C"}).status_code == 409
    for bad in ({"name": "   "}, {"name": 3}, {}):
        assert client.put(project_url("프로젝트 A"), json=bad).status_code == 400
    assert client.put(project_url("없는 프로젝트"), json={"name": "새 이름"}).status_code == 404
    same = client.put(project_url("프로젝트 A"), json={"name": " 프로젝트   A "})
    assert same.status_code == 200 and same.json() == {"name": "프로젝트 A", "works": [], "join": False, "tasks": {}}
    assert works.work(a)["task"] == before
    assert works.work(b)["task"]["project"] == "프로젝트 B"
    moved = client.put(project_url("프로젝트 C"), json={"name": "프로젝트 D"})  # 기록만 있는 프로젝트도 옮긴다
    assert moved.status_code == 200 and moved.json() == {"name": "프로젝트 D", "works": [], "join": False, "tasks": {}}
    assert projects.get("프로젝트 C") is None and projects.get("프로젝트 D") is not None


def test_delete_project_keep_releases_documents(client):
    plan = upload(client)
    newer = branch(client, plan)["docId"]
    outside = upload(client, project="프로젝트 B")
    saved = settings(client, newer, VALUES)
    other = settings(client, outside, CHANGED)
    response = client.delete(project_url("프로젝트 A"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "프로젝트 A" and body["docs"] == "keep" and set(body["works"]) == {plan, newer}
    for wid in (plan, newer):
        task = works.work(wid)["task"]
        assert task["project"] == "" and "round" not in task
        assert task["job"] == "plan_to_report" and task["file"] == "plan" and task["kind"] == "rnd"
        assert client.get(f"/api/docs/{wid}").status_code == 200
    assert divisions(client, newer)["settings"] == saved  # 문서가 가진 입력은 남는다
    assert projects.get("프로젝트 A") is None
    assert projects.get("프로젝트 B")["settings"] == other
    assert works.work(outside)["task"]["project"] == "프로젝트 B"
    assert {item["name"] for item in client.get("/api/projects").json()["projects"]} == {"프로젝트 B"}
    assert client.delete(project_url("프로젝트 A")).status_code == 404


def test_delete_project_with_documents(client):
    plan = upload(client)
    newer = branch(client, plan)["docId"]
    outside = upload(client, project="프로젝트 B")
    settings(client, newer, VALUES)
    response = client.delete(project_url("프로젝트 A"), params={"docs": "delete"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["docs"] == "delete" and set(body["works"]) == {plan, newer}
    for wid in (plan, newer):
        assert works.work(wid) is None
        assert not (works.root() / wid).exists()
        assert wid not in server.DOCS
    assert projects.get("프로젝트 A") is None
    assert works.work(outside)["task"]["project"] == "프로젝트 B" and outside in server.DOCS
    assert {item["name"] for item in client.get("/api/projects").json()["projects"]} == {"프로젝트 B"}


def test_delete_project_rejects_bad_mode_and_missing_project(client):
    wid = upload(client)
    before = works.work(wid)["task"]
    assert client.delete(project_url("프로젝트 A"), params={"docs": "all"}).status_code == 400
    assert client.delete(project_url("없는 프로젝트")).status_code == 404
    assert client.delete(project_url("없는 프로젝트"), params={"docs": "delete"}).status_code == 404
    assert works.work(wid)["task"] == before


def test_broken_project_settings_block_rename_and_delete(client):
    wid = upload(client)
    before = works.work(wid)["task"]
    path = works.root() / "projects.json"
    path.write_text("{broken", encoding="utf-8")
    assert client.put(project_url("프로젝트 A"), json={"name": "새 이름"}).status_code == 409
    assert client.delete(project_url("프로젝트 A")).status_code == 409
    assert client.delete(project_url("프로젝트 A"), params={"docs": "delete"}).status_code == 409
    assert works.work(wid)["task"] == before
    assert wid in server.DOCS
    assert path.read_text("utf-8") == "{broken"


def test_confirm_records_hash_survives_settings_change_listing_and_rename(client):
    """1단계 구성 확정(spec_작업 ② §18) — projects.confirm/confirmed · 설정이 바뀌어도 확정은 남음 · 목록 · 이름 변경."""
    plan = upload(client)
    saved = settings(client, plan, VALUES)
    assert projects.confirmed("프로젝트 A") is None
    got = projects.confirm(" 프로젝트   A ", saved)
    assert got["hash"] == server.division_model.settings_hash(saved) and got["values"] == saved["values"] and got["at"] > 0
    assert projects.confirmed("프로젝트 A") == got and projects.get("프로젝트 A")["settings"] == saved
    assert projects.confirm("", saved) is None and projects.confirmed("") is None and projects.confirmed("없는 프로젝트") is None
    got["values"]["stages"] = [9]   # 사본을 돌려준다
    assert projects.confirmed("프로젝트 A")["values"] == saved["values"]
    got = projects.confirmed("프로젝트 A")
    settings(client, plan, CHANGED)
    record = projects.get("프로젝트 A")
    assert record["confirmed"] == got and record["settings"]["values"] != got["values"]   # 맞는지는 hash 로 — 설정이 바뀌어도 지우지 않는다
    upload(client, project="프로젝트 B")
    listed = {item["name"]: item["confirmed"] for item in client.get("/api/projects").json()["projects"]}
    assert listed == {"프로젝트 A": got, "프로젝트 B": None}
    assert client.put(project_url("프로젝트 A"), json={"name": "새 이름"}).status_code == 200
    assert projects.confirmed("새 이름") == got and projects.confirmed("프로젝트 A") is None


def test_confirmed_must_be_an_object(client):
    import json
    wid = upload(client)
    settings(client, wid, VALUES)
    path = works.root() / "projects.json"
    data = json.loads(path.read_text("utf-8"))
    data["projects"]["프로젝트 A"]["confirmed"] = "확정"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert client.get("/api/projects").status_code == 409
    data["projects"]["프로젝트 A"]["confirmed"] = None
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert client.get("/api/projects").json()["projects"][0]["confirmed"] is None and projects.confirmed("프로젝트 A") is None


# ---- 프로젝트에 들어가기(spec_작업 ② §10·§19) — round 를 안 보내면 새 묶음의 최신 라운드 · 들어감 알림의 근거 division ----

def bare(client):
    """task 를 안 적은 새 작업."""
    response = client.post("/api/docs?new=1", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    assert response.status_code == 200, response.text
    return response.json()["docId"]


def put_task(client, wid, **task):
    """round 를 안 보내는 화면의 저장(프로젝트·TASK 칸) — 응답 전체."""
    body = {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "프로젝트 A", **task}
    response = client.put(f"/api/works/{wid}/task", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_joining_without_round_takes_the_latest_round_of_the_new_group(client):
    first = upload(client)
    newer = branch(client, first)["docId"]   # 프로젝트 A · 이관의 최신 라운드 = 2
    saved = settings(client, newer, VALUES)
    joiner = bare(client)
    joined = put_task(client, joiner)
    assert joined["task"]["round"] == 2 and works.work(joiner)["task"]["round"] == 2   # 전에는 번호 없음(= 1) — 이전 라운드가 되어 공유가 안 됐다
    assert divisions(client, joiner)["projectSharing"] == {"project": "프로젝트 A", "round": 2, "latestRound": 2, "shared": True}
    assert divisions(client, joiner)["settings"] == saved
    assert works.work(first)["task"]["round"] == 1 and works.work(newer)["task"]["round"] == 2   # 다른 작업은 그대로
    assert put_task(client, joiner, file="report")["task"]["round"] == 2   # 같은 묶음 안에서는 전처럼 제 라운드를 지닌다
    # 빈 묶음이면 번호 없음(= 1)
    alone = bare(client)
    assert "round" not in put_task(client, alone, project="프로젝트 B")["task"] and "round" not in works.work(alone)["task"]
    assert "round" not in put_task(client, joiner, job="plan_fit")["task"]   # 같은 프로젝트의 다른 TASK — 그 묶음에 다른 작업이 없다(자기 자신은 안 센다)
    assert "round" not in put_task(client, joiner, job="plan_fit", file="report")["task"]
    second = bare(client)   # 번호 없는 작업만 있는 묶음 = 최신 라운드 1
    assert projects.round_of(put_task(client, second, project="프로젝트 B")["task"]) == 1
    assert divisions(client, second)["projectSharing"]["shared"] is True and divisions(client, alone)["projectSharing"]["shared"] is True
    # round 를 보내면 그 값(이전 라운드로 들어감 — 공유 안 됨)
    old = bare(client)
    sent = put_task(client, old, round=1)
    assert sent["task"]["round"] == 1 and "division" not in sent
    assert divisions(client, old)["projectSharing"] == {"project": "프로젝트 A", "round": 1, "latestRound": 2, "shared": False}
    assert put_task(client, bare(client), round=5)["task"]["round"] == 5
    # 프로젝트에서 나오면 번호 없음
    assert "round" not in put_task(client, joiner, job="plan_fit", project="")["task"]


def test_task_response_tells_how_the_division_settings_arrived(client):
    owner = upload(client)
    saved = settings(client, owner, VALUES)
    fresh = bare(client)
    assert put_task(client, fresh) == {"task": {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "프로젝트 A"}, "division": "adopted"}   # 최신 라운드가 1 이면 전처럼 번호 없음
    assert divisions(client, fresh)["settings"] == saved
    assert "division" not in put_task(client, fresh, file="report")   # 프로젝트가 안 바뀌면 칸 없음
    assert "division" not in put_task(client, fresh, job="plan_fit")   # TASK 만 바뀜
    own = bare(client)
    settings(client, own, CHANGED)
    assert put_task(client, own)["division"] == "adopted" and divisions(client, own)["settings"] == saved   # 제 값이 있어도 프로젝트의 것을 받는다
    seeder = bare(client)
    mine = settings(client, seeder, CHANGED)
    assert projects.get("프로젝트 C") is None
    assert put_task(client, seeder, project="프로젝트 C")["division"] == "seeded"   # 프로젝트에 없어 이 문서의 값이 올라감
    assert projects.get("프로젝트 C")["settings"] == mine and divisions(client, seeder)["settings"] == mine
    empty = bare(client)
    assert put_task(client, empty, project="프로젝트 D")["division"] == "none"
    assert divisions(client, empty)["settings"] is None and projects.get("프로젝트 D") is None
    assert put_task(client, empty, project="프로젝트 C")["division"] == "adopted"   # 다른 프로젝트로 옮겨도 들어감
    assert "division" not in put_task(client, empty, project="")   # 프로젝트에서 나옴
    general = bare(client)   # 일반 문서 — 구분 기준을 받지도 주지도 않는다
    assert "division" not in put_task(client, general, kind="general", job="doc_edit")
    closed = bare(client)   # 열려 있지 않은 작업
    server._persist_all()
    server.DOCS.pop(closed)
    assert put_task(client, closed) == {"task": {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "프로젝트 A"}}


# ---- 문서 없는 프로젝트 · 프로젝트 구성 초기화(spec_작업 ② §17) ----

def listed(client):
    response = client.get("/api/projects")
    assert response.status_code == 200, response.text
    return response.json()["projects"]


def log_text(wid):
    return (works.root() / wid / "log.jsonl").read_text("utf-8")


def test_project_without_documents_is_listed_renamed_and_deleted(client):
    moved, gone = upload(client), upload(client, role="report")
    saved = settings(client, moved, VALUES)
    assert client.post(f"/api/docs/{moved}/divisions/confirm", json={}).status_code == 200
    assert client.post(f"/api/docs/{moved}/divisions/versions", json={"name": "1차년도"}).status_code == 200
    stay = upload(client, project="프로젝트 B")
    put_task(client, moved, project="프로젝트 B")   # 프로젝트 칸에서 다른 프로젝트로 옮김
    assert client.delete(f"/api/works/{gone}").status_code == 200   # 문서 삭제 — 프로젝트 A 는 기록만 남는다
    rows = listed(client)
    by = {item["name"]: item for item in rows}
    assert set(by) == {"프로젝트 A", "프로젝트 B"}
    empty = by["프로젝트 A"]
    assert empty["works"] == [] and empty["tasks"] == [] and set(empty) == set(by["프로젝트 B"])   # 다른 항목과 같은 칸
    assert empty["settings"] == saved and empty["confirmed"]["values"] == saved["values"] and [v["name"] for v in empty["versions"]] == ["1차년도"]
    assert empty["updated"] == projects.get("프로젝트 A")["updated"]
    assert [item["updated"] for item in rows] == sorted((item["updated"] for item in rows), reverse=True)
    assert set(by["프로젝트 B"]["works"]) == {moved, stay}
    # 이름 변경 — 기록만 옮긴다
    renamed = client.put(project_url("프로젝트 A"), json={"name": "빈 프로젝트"})
    assert renamed.status_code == 200 and renamed.json() == {"name": "빈 프로젝트", "works": [], "join": False, "tasks": {}}
    by = {item["name"]: item for item in listed(client)}
    assert set(by) == {"빈 프로젝트", "프로젝트 B"} and by["빈 프로젝트"]["works"] == [] and [v["name"] for v in by["빈 프로젝트"]["versions"]] == ["1차년도"]
    assert client.put(project_url("빈 프로젝트"), json={"name": "프로젝트 B"}).status_code == 409   # 합치지 않는다
    # 삭제 — 문서가 없으니 기록만 지운다
    deleted = client.delete(project_url("빈 프로젝트"))
    assert deleted.status_code == 200 and deleted.json() == {"name": "빈 프로젝트", "docs": "keep", "works": []}
    assert {item["name"] for item in listed(client)} == {"프로젝트 B"} and projects.get("빈 프로젝트") is None
    assert client.delete(project_url("빈 프로젝트")).status_code == 404
    assert works.work(moved)["task"]["project"] == "프로젝트 B"
    # 문서 없는 프로젝트의 초기화 = 기록만 지움
    last = upload(client, project="프로젝트 C")
    settings(client, last, CHANGED)
    assert client.delete(f"/api/works/{last}").status_code == 200
    assert {item["name"] for item in listed(client)} == {"프로젝트 B", "프로젝트 C"}
    reset = client.delete(project_url("프로젝트 C"), params={"docs": "reset"})
    assert reset.status_code == 200 and reset.json() == {"name": "프로젝트 C", "docs": "reset", "works": [], "skipped": []}
    assert {item["name"] for item in listed(client)} == {"프로젝트 B"} and projects.get("프로젝트 C") is None


def test_reset_project_clears_shared_settings_and_keeps_documents(client):
    old = upload(client)   # 이관 Round 1 — 아래에서 이전 라운드가 된다
    kept = settings(client, old, VALUES)
    assert client.post(f"/api/docs/{old}/divisions/confirm", json={}).status_code == 200
    newer = branch(client, old)["docId"]                  # 이관 Round 2(최신)
    closed = upload(client, role="report", number=2)      # 같은 라운드의 다른 문서 — 닫아 둔다
    other_task = upload(client, job="plan_fit")           # 같은 프로젝트의 다른 TASK
    general = bare(client)                                # 일반 문서 — 프로젝트 구성을 받지도 주지도 않는다
    put_task(client, general, kind="general", job="doc_edit")
    own = settings(client, general, VALUES)
    outside = upload(client, project="프로젝트 B")
    other = settings(client, outside, VALUES)
    shared = settings(client, newer, CHANGED)             # 프로젝트 A 의 지금 구성
    assert client.post(f"/api/docs/{newer}/divisions/confirm", json={}).status_code == 200
    assert client.post(f"/api/docs/{newer}/divisions/versions", json={"name": "2차년도"}).status_code == 200
    for wid in (closed, other_task):
        assert divisions(client, wid)["settings"] == shared and divisions(client, wid)["confirmed"]["valid"] is True
    applied = {"values": shared["values"], "planId": "p1", "rev": 0}   # 문서에 이미 반영한 기록
    for wid in (newer, closed):
        server.DOCS[wid].division["applied"] = dict(applied)
    server.DOCS[other_task].division["plan"] = {"planId": "old-plan", "baseRev": 0, "settingsHash": server.division_model.settings_hash(shared)}
    server._persist(server.DOCS[closed], force=True)
    server.DOCS.pop(closed)

    response = client.delete(project_url("프로젝트 A"), params={"docs": "reset"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"name", "docs", "works", "skipped"} and body["name"] == "프로젝트 A" and body["docs"] == "reset" and body["skipped"] == []
    assert set(body["works"]) == {newer, closed, other_task}   # TASK 마다 최신 라운드 — 이전 라운드·일반 문서는 뺀다
    assert projects.get("프로젝트 A") is None and projects.versions("프로젝트 A") == [] and projects.confirmed("프로젝트 A") is None
    assert server.DOCS[other_task].division["plan"] is None
    for wid in (newer, closed, other_task):
        view = divisions(client, wid)
        assert view["settings"] is None and view["confirmed"] is None and view["versions"] == [] and view["plan"] is None
        assert view["projectSharing"]["shared"] is True and view["projectSharing"]["project"] == "프로젝트 A"
        assert '"kind":"resetProject"' in log_text(wid)
    assert projects.get("프로젝트 A") is None   # 비운 문서를 봐도 값이 프로젝트로 다시 안 올라온다
    assert divisions(client, newer)["applied"] == applied and divisions(client, closed)["applied"] == applied   # 반영 기록은 그대로
    assert works.work(newer)["task"] == {"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "프로젝트 A", "round": 2}   # 소속·TASK·라운드 그대로
    previous = divisions(client, old)   # 이전 라운드에 보관한 값·확정은 그대로
    assert previous["settings"] == kept and previous["confirmed"]["scope"] == "work" and previous["confirmed"]["valid"] is True
    assert previous["projectSharing"]["shared"] is False and "resetProject" not in log_text(old)
    assert divisions(client, general)["settings"] == own and "resetProject" not in log_text(general)
    assert divisions(client, outside)["settings"] == other and projects.get("프로젝트 B")["settings"] == other
    row = next(item for item in listed(client) if item["name"] == "프로젝트 A")   # 문서는 프로젝트에 그대로
    assert row["settings"] is None and row["confirmed"] is None and row["versions"] == []
    assert set(row["works"]) == {old, newer, closed, other_task, general}
    # 다시 켜서 문서를 열어도 값이 프로젝트로 다시 올라오지 않는다
    server._persist_all()
    server.DOCS.clear()
    for wid in (newer, closed, other_task):
        assert divisions(client, wid)["settings"] is None and divisions(client, wid)["confirmed"] is None
    assert projects.get("프로젝트 A") is None and divisions(client, old)["settings"] == kept
    # 초기화 뒤 새 값을 넣으면 다시 공유된다
    fresh = settings(client, other_task, VALUES)
    for wid in (newer, closed):
        assert divisions(client, wid)["settings"] == fresh and divisions(client, wid)["confirmed"] is None
    assert projects.get("프로젝트 A")["settings"] == fresh
    again = client.delete(project_url("프로젝트 A"), params={"docs": "reset"})   # 다시 초기화해도 된다
    assert again.status_code == 200 and set(again.json()["works"]) == {newer, closed, other_task}
    assert divisions(client, newer)["settings"] is None and projects.get("프로젝트 A") is None


def test_reset_project_rejects_missing_broken_and_skips_unopenable_work(client, monkeypatch):
    good, bad = upload(client), upload(client, role="report")
    saved = settings(client, good, VALUES)
    assert divisions(client, bad)["settings"] == saved
    assert client.delete(project_url("없는 프로젝트"), params={"docs": "reset"}).status_code == 404
    assert client.delete(project_url("프로젝트 A"), params={"docs": "all"}).status_code == 400
    path = works.root() / "projects.json"
    text = path.read_text("utf-8")
    path.write_text("{broken", encoding="utf-8")
    assert client.delete(project_url("프로젝트 A"), params={"docs": "reset"}).status_code == 409   # 아무것도 안 바꾼다
    assert path.read_text("utf-8") == "{broken" and server.DOCS[good].division["settings"] == saved
    assert "resetProject" not in log_text(good)
    path.write_text(text, encoding="utf-8")
    opened = server._sess

    def sess(wid):
        if wid == bad:
            raise server.HTTPException(404, "못 여는 작업")
        return opened(wid)

    with monkeypatch.context() as patch:   # 못 여는 작업은 건너뛰고 알린다
        patch.setattr(server, "_sess", sess)
        response = client.delete(project_url("프로젝트 A"), params={"docs": "reset"})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "프로젝트 A", "docs": "reset", "works": [good], "skipped": [bad]}
    assert projects.get("프로젝트 A") is None and server.DOCS[good].division["settings"] is None
    assert server.DOCS[bad].division["settings"] == saved and "resetProject" not in log_text(bad)   # 건너뛴 작업의 값은 그대로 남는다


# ---- 새 프로젝트 · 임시 프로젝트(spec_작업 ② §17 「새 프로젝트」·「임시 프로젝트」 — 2026-11-18) ----

def start_temp(client, job="plan_fit", role="plan"):
    """이름 없이 TASK 를 시작(시작 화면의 프로젝트 칸을 비움) → 응답."""
    wid = bare(client)
    response = client.post(f"/api/works/{wid}/start-task", json={"project": "", "temp": True, "job": job, "file": role})
    assert response.status_code == 200, response.text
    return response.json()


def test_start_without_a_name_gets_the_next_temp_project(client):
    first, second = start_temp(client), start_temp(client, job="plan_to_report")
    assert first["temp"] is True and first["task"]["project"] == "임시 프로젝트 1" and first["round"] == 1
    assert second["task"]["project"] == "임시 프로젝트 2"
    assert {p["name"]: p["temp"] for p in listed(client)} == {"임시 프로젝트 1": True, "임시 프로젝트 2": True}
    assert '"temp":true' in log_text(first["docId"])
    # 이름이 있으면 temp 를 보내도 그 이름 · 이름도 temp 도 없으면 전처럼 400
    named = client.post(f"/api/works/{bare(client)}/start-task", json={"project": "프로젝트 A", "temp": True, "job": "plan_fit", "file": "plan"})
    assert named.status_code == 200 and named.json()["task"]["project"] == "프로젝트 A" and named.json()["temp"] is False
    assert client.post(f"/api/works/{bare(client)}/start-task", json={"project": "", "job": "plan_fit", "file": "plan"}).status_code == 400
    # 번호는 쓰인 것의 최댓값 + 1 — 기록만 남은 임시 이름도 센다
    projects.settings("임시 프로젝트 7", settings(client, first["docId"], VALUES))
    assert start_temp(client)["task"]["project"] == "임시 프로젝트 8"
    assert projects.is_temp(" 임시   프로젝트 3 ") and not projects.is_temp("임시 프로젝트") and not projects.is_temp("임시 프로젝트 0") and not projects.is_temp("임시 프로젝트 2 사본")
    sample = client.post(f"/api/samples/{quote(SAMPLE.name)}?new=1").json()["docId"]   # 예제로 연 문서도 이름 없이 시작하면 임시 프로젝트
    got = client.post(f"/api/works/{sample}/start-task", json={"project": "", "temp": True, "job": "plan_fit", "file": "plan"})
    assert got.status_code == 200 and got.json()["task"]["project"] == "임시 프로젝트 9"
    copied = branch(client, sample)["docId"]   # 새 라운드로 만든 작업은 안 된다(그 라운드에 묶인 것)
    put_task(client, copied, project="", job="plan_fit")
    assert client.post(f"/api/works/{copied}/start-task", json={"project": "", "temp": True, "job": "plan_fit", "file": "plan"}).status_code == 409


def test_naming_a_temp_project_renames_it_or_joins_an_existing_one(client):
    temp = start_temp(client, job="plan_to_report")
    wid, name = temp["docId"], temp["task"]["project"]
    mate = bare(client)
    put_task(client, mate, project=name, file="report")   # 같은 묶음의 둘째 문서(이관의 원본 문서처럼)
    saved = settings(client, wid, VALUES)
    renamed = client.put(project_url(name), json={"name": "  과제 가 "})
    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert body["name"] == "과제 가" and body["join"] is False and set(body["works"]) == {wid, mate}
    assert body["tasks"][wid]["project"] == "과제 가" and works.work(mate)["task"]["project"] == "과제 가"
    assert projects.get(name) is None and projects.get("과제 가")["settings"] == saved
    # 이름 있는 프로젝트는 임시 이름 꼴로 바꾸지 못한다
    assert client.put(project_url("과제 가"), json={"name": "임시 프로젝트 9"}).status_code == 400
    # 이미 있는 이름이면 임시 프로젝트의 문서를 모두 그 프로젝트로(합치기는 임시 프로젝트만)
    owner = upload(client, project="프로젝트 B")
    newer = branch(client, owner)["docId"]   # 프로젝트 B · 이관의 최신 라운드 = 2
    theirs = settings(client, newer, CHANGED)
    second = start_temp(client, job="plan_to_report")
    other = start_temp(client, job="plan_fit")   # 같은 임시 프로젝트의 다른 TASK 를 만들려고 따로 시작한 뒤 옮긴다
    put_task(client, other["docId"], project=second["task"]["project"], job="plan_fit", round=3)
    settings(client, second["docId"], VALUES)
    joined = client.put(project_url(second["task"]["project"]), json={"name": "프로젝트 B"})
    assert joined.status_code == 200, joined.text
    body = joined.json()
    assert body["join"] is True and set(body["works"]) == {second["docId"], other["docId"]}
    assert works.work(second["docId"])["task"]["round"] == 2   # B 에 있는 TASK — 그 TASK 의 최신 라운드로(프로젝트 칸과 같다)
    assert works.work(other["docId"])["task"]["round"] == 3 and works.work(other["docId"])["task"]["project"] == "프로젝트 B"   # B 에 없는 TASK — 라운드 그대로
    assert projects.get(second["task"]["project"]) is None and projects.get("프로젝트 B")["settings"] == theirs   # B 의 구성이 이긴다
    assert divisions(client, second["docId"])["settings"] == theirs
    assert '"kind":"joinProject"' in log_text(second["docId"])
    # 구성이 없는 프로젝트(새 프로젝트)로 옮기면 임시 프로젝트의 구성 · 확정 · 버전이 따라간다
    assert client.post("/api/projects", json={"name": "빈 과제"}).status_code == 200
    third = start_temp(client)
    mine = settings(client, third["docId"], VALUES)
    assert client.post(f"/api/docs/{third['docId']}/divisions/confirm", json={}).status_code == 200
    assert client.post(f"/api/docs/{third['docId']}/divisions/versions", json={"name": "1차년도"}).status_code == 200
    assert client.put(project_url(third["task"]["project"]), json={"name": "빈 과제"}).json()["join"] is True
    got = projects.get("빈 과제")
    assert got["settings"] == mine and got["confirmed"]["values"] == mine["values"] and [v["name"] for v in got["versions"]] == ["1차년도"] and "created" in got


def test_temp_project_without_documents_is_not_kept(client):
    moved = start_temp(client)
    settings(client, moved["docId"], VALUES)   # 문서의 구성이 임시 프로젝트 기록으로 올라감
    name = moved["task"]["project"]
    assert projects.get(name) is not None
    put_task(client, moved["docId"], project="프로젝트 A", job="plan_fit")   # 마지막 문서가 나감
    assert projects.get(name) is None and name not in {p["name"] for p in listed(client)}
    gone = start_temp(client)
    settings(client, gone["docId"], VALUES)
    assert client.delete(f"/api/works/{gone['docId']}").status_code == 200   # 마지막 문서를 지움
    assert projects.get(gone["task"]["project"]) is None
    kept = upload(client, project="이름 있는 과제")
    settings(client, kept, VALUES)
    assert client.delete(f"/api/works/{kept}").status_code == 200
    assert projects.get("이름 있는 과제") is not None   # 이름 있는 프로젝트는 전처럼 「문서 없음」 으로 남는다


def test_create_project_makes_an_empty_record_that_documents_can_join(client):
    made = client.post("/api/projects", json={"name": "  새   과제 "})
    assert made.status_code == 200 and made.json() == {"name": "새 과제"}
    item = next(p for p in listed(client) if p["name"] == "새 과제")
    assert item["works"] == [] and item["tasks"] == [] and item["settings"] is None and item["temp"] is False and item["versions"] == []
    upload(client, project="프로젝트 A")
    for bad, code in (({"name": "새 과제"}, 409), ({"name": "프로젝트 A"}, 409), ({"name": "  "}, 400), ({}, 400), ({"name": 3}, 400), ({"name": "임시 프로젝트 4"}, 400)):
        assert client.post("/api/projects", json=bad).status_code == code, bad
    joiner = bare(client)
    mine = settings(client, joiner, VALUES)
    assert put_task(client, joiner, project="새 과제")["division"] == "seeded"   # 기록은 있어도 구성이 없다 — 받은 것이 아니라 올린 것
    assert projects.get("새 과제")["settings"] == mine and "created" in projects.get("새 과제")
    empty = bare(client)
    assert client.post("/api/projects", json={"name": "다른 과제"}).status_code == 200
    assert put_task(client, empty, project="다른 과제")["division"] == "none" and divisions(client, empty)["settings"] is None
    assert client.post(f"/api/docs/{empty}/divisions/versions", json={"name": "1차년도", "values": VALUES}).status_code == 200   # 구성 없는 기록에 버전 — 그 값이 입력이 된다
    assert projects.get("다른 과제")["settings"]["values"] == divisions(client, empty)["settings"]["values"]
    path = works.root() / "projects.json"
    path.write_text("{broken", encoding="utf-8")
    assert client.post("/api/projects", json={"name": "또 다른 과제"}).status_code == 409
    assert path.read_text("utf-8") == "{broken"


def test_temp_project_name_is_not_put_into_document_names():
    task = {"kind": "rnd", "job": "plan_to_report", "file": "report", "project": "임시 프로젝트 3"}
    assert works.shown_name("보고서.hwpx", task, "보고") == "보고서(보고).hwpx"   # 임시 이름은 안 붙임 — 이름을 정하면 그때
    assert works.shown_name("보고서.hwpx", {**task, "project": "과제 가"}) == "보고서_과제 가.hwpx"
    fit = {"kind": "rnd", "job": "plan_fit", "file": "plan", "project": "임시 프로젝트 3"}
    assert works.frame_stem(fit, True) is None and works.frame_stem({**fit, "project": "과제 가"}, True) == "사업계획서_과제 가_프레임"
