"""문서별 워크플로우 목록은 TASK를 오가도 진행 요약과 문서 역할·라운드를 보관한다."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import server, works

WID = "00000000ff81"


@pytest.fixture
def client():
    works.create(WID, "workflows.hwpx", "hwpx", b"original document")
    return TestClient(server.app)


def url(wid=WID):
    return f"/api/works/{wid}/workflows"


def task(job="plan_fit", file="plan", project="", round=1):
    return {"job": job, "kind": server.TASK_KIND.get(job, "rnd"), "file": file, "project": project, "round": round}


def activate(client, job):
    response = client.post(url() + "/activate", json={"job": job})
    assert response.status_code == 200, response.text
    return response.json()


def test_legacy_current_task_appears_without_mutating_work(client):
    works.update(WID, task=task())
    before = works.work(WID)
    got = client.get(url()).json()
    assert got["active"] == "plan_fit"
    assert got["items"] == [{"job": "plan_fit", "status": "ready", "done": 0, "total": 0, "updated": before["updated"]}]
    assert works.work(WID) == before
    works.update(WID, task={})
    assert client.get(url()).json() == {"items": [], "active": ""}


def test_progress_persists_once_and_added_workflow_does_not_activate(client):
    works.update(WID, task=task())
    payload = {"job": "plan_fit", "status": "done", "done": 9, "total": 9}
    first = client.put(url(), json=payload)
    assert first.status_code == 200
    before = works.work(WID)
    assert client.put(url(), json=payload).json() == first.json()
    assert works.work(WID) == before  # 같은 1초 감시 결과는 시각·파일을 계속 고치지 않는다.
    got = client.put(url(), json={"job": "plan_merge"}).json()
    assert got["active"] == "plan_fit" and len(got["items"]) == 2
    assert all("context" not in item for item in got["items"])
    assert TestClient(server.app).get(url()).json() == got
    assert works.work(WID)["task"] == task()


def test_switch_restores_role_round_and_previous_progress(client):
    current = task(project="해양 연구", round=3)
    works.update(WID, task=current, rev=7, edited=3)
    assert client.put(url(), json={"job": "plan_fit", "status": "done", "done": 9, "total": 9}).status_code == 200
    # 새로운 취합 TASK는 기관 문서가 아니라 취합본(plan)이다. 이미 있는 최신 라운드는 기존 task API가 고른다.
    other = "00000000ff82"
    works.create(other, "other.hwpx", "hwpx", b"other")
    works.update(other, task=task("plan_merge", "part", "해양 연구", 4))
    merged = activate(client, "plan_merge")
    assert merged["task"] == task("plan_merge", "plan", "해양 연구", 4)
    assert merged["items"][0]["status"] == "done"
    assert activate(client, "plan_fit")["task"] == current
    saved = works.work(WID)
    assert saved["rev"] == 7 and saved["edited"] == 3
    assert (works.folder(WID) / "original.hwpx").read_bytes() == b"original document"


def test_roles_are_kept_per_workflow_and_project_is_common(client):
    works.update(WID, task=task("plan_to_report", "report", "프로젝트 A", 2))
    assert activate(client, "plan_fit")["task"]["file"] == "plan"
    assert activate(client, "plan_to_report")["task"] == task("plan_to_report", "report", "프로젝트 A", 2)
    assert activate(client, "doc_edit")["task"]["kind"] == "general"
    # 프로젝트가 달라지면 이전 프로젝트의 라운드를 복원하지 않는다.
    assert client.put(f"/api/works/{WID}/task", json=task("doc_edit", "report", "프로젝트 B", 1)).status_code == 200
    switched = activate(client, "plan_to_report")["task"]
    assert switched["project"] == "프로젝트 B" and switched.get("round", 1) == 1
    assert switched["file"] == "report"


def test_new_transfer_keeps_current_source_or_target_role(client):
    works.update(WID, task=task("report_fit", "report"))
    assert activate(client, "plan_to_report")["task"]["file"] == "report"
    works.update(WID, task=task("plan_merge", "part"), workflows=[])
    assert activate(client, "plan_to_report")["task"]["file"] == ""


@pytest.mark.parametrize("body", [
    {"job": "unknown"}, {"job": "report_merge"}, {"job": []},
    {"job": "plan_fit", "status": "running"},
    {"job": "plan_fit", "done": True}, {"job": "plan_fit", "done": -1},
    {"job": "plan_fit", "done": 2, "total": 1},
    {"job": "plan_fit", "done": 1.2, "total": 2},
    {"job": "plan_fit", "status": "done", "done": 0, "total": 0},
    {"job": "plan_fit", "status": "done", "done": 1, "total": 2},
])
def test_invalid_progress_does_not_change_work(client, body):
    before = works.work(WID)
    assert client.put(url(), json=body).status_code == 400
    assert works.work(WID) == before


def test_format_missing_and_unavailable_workflow_checks(client):
    works.update(WID, format="docx")
    assert client.put(url(), json={"job": "plan_fit"}).status_code == 400
    assert client.post(url() + "/activate", json={"job": "plan_fit"}).status_code == 400
    assert client.post(url() + "/activate", json={"job": "report_merge"}).status_code == 400
    assert activate(client, "style_copy")["task"]["kind"] == "general"
    missing = url("000000000001")
    assert client.get(missing).status_code == 404
    assert client.put(missing, json={"job": "style_copy"}).status_code == 404
    assert client.post(missing + "/activate", json={"job": "style_copy"}).status_code == 404


def test_a_row_can_be_removed_from_the_list_but_not_the_current_one(client):
    """C4 — DELETE /api/works/{wid}/workflows/{job}: 그 줄을 문서의 워크플로우 목록에서 뺀다(문서 · 분석 · 다른 줄은 그대로 — 진행 요약 줄만) → GET 과 같은 꼴.
    지금 워크플로우 400 · 그런 줄이 없음 404 · 작업이 없음 404 · 키는 따지지 않는다(모르는 키의 줄도 뺀다)."""
    works.update(WID, task=task(), rev=4)
    for job in ("plan_merge", "u_0000dead"):   # 모르는 키(지워진 조립한 워크플로우 등)의 줄도
        works.workflow_update(WID, job, status="progress", done=1, total=3)
    before = works.work(WID)
    cur = client.delete(url() + "/plan_fit")
    assert cur.status_code == 400 and cur.json()["detail"] == "지금 워크플로우는 목록에서 뺄 수 없습니다 — 다른 워크플로우로 바꾼 뒤에 빼세요" and works.work(WID) == before
    assert client.delete(url() + "/doc_edit").json() == {"detail": "목록에 그 워크플로우가 없습니다"} and works.work(WID) == before
    gone = client.delete(url() + "/u_0000dead")
    assert gone.status_code == 200 and gone.json() == client.get(url()).json() and [i["job"] for i in gone.json()["items"]] == ["plan_fit", "plan_merge"]
    after = works.work(WID)
    assert after["task"] == task() and after["rev"] == 4 and [r["job"] for r in after["workflows"]] == ["plan_merge"] and (works.folder(WID) / "original.hwpx").read_bytes() == b"original document"
    assert client.delete(url() + "/u_0000dead").status_code == 404 and client.delete(url("000000000001") + "/plan_merge").status_code == 404
    assert any(e["kind"] == "workflowRemove" and e.get("job") == "u_0000dead" for e in works.events(WID))


def test_independent_workflow_updates_do_not_overwrite_each_other(client):
    jobs = ("plan_fit", "plan_merge", "plan_to_report", "report_fit", "doc_edit", "style_copy")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda job: works.workflow_update(WID, job, status="progress", done=1, total=3), jobs))
    assert all(results)
    assert {row["job"] for row in client.get(url()).json()["items"]} == set(jobs)
