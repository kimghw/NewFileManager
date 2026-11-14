"""구분 기준 버전(spec_작업 ② §19) — `projects.version_*` · `GET …/divisions` 의 versions · `POST …/divisions/versions` · `…/versions/{vid}/apply` · `DELETE …/versions/{vid}` · `GET /api/projects` 의 versions."""
import json
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app import division_model, projects, server, works

SAMPLE = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
VALUES = {"stages": [2, 1], "orgs": {"lead": "주관 A", "joint": ["공동 B"]}}
YEAR2 = {**VALUES, "current": 2}   # 당해 차년도만 다른 값 — 차년도별 버전
CHANGED = {"stages": [1, 2], "orgs": {"lead": "주관 C", "joint": ["공동 D"]}}
NOT_SHARED = "프로젝트의 최신 라운드 작업에서만"


@pytest.fixture
def client(monkeypatch):
    server.DOCS.clear()
    monkeypatch.setattr(server, "_start", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_ensure_persister", lambda: None)
    with TestClient(server.app) as c:
        yield c
    server.DOCS.clear()


def upload(c, role="plan", job="plan_to_report", project="프로젝트 A", number=1, kind="rnd"):
    r = c.post("/api/docs?new=1", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    assert r.status_code == 200, r.text
    wid = r.json()["docId"]
    if project is not None:
        r = c.put(f"/api/works/{wid}/task", json={"kind": kind, "file": role, "job": job, "project": project, "round": number})
        assert r.status_code == 200, r.text
    return wid


def put_settings(c, wid, values):
    r = c.put(f"/api/docs/{wid}/divisions/settings", json={"values": values})
    assert r.status_code == 200, r.text
    return r.json()


def view(c, wid):
    r = c.get(f"/api/docs/{wid}/divisions")
    assert r.status_code == 200, r.text
    return r.json()


def save(c, wid, name, **more):
    return c.post(f"/api/docs/{wid}/divisions/versions", json={"name": name, **more})


def saved(c, wid, name, **more):
    r = save(c, wid, name, **more)
    assert r.status_code == 200, r.text
    return r.json()


def listed(c, project="프로젝트 A"):
    return next(p for p in c.get("/api/projects").json()["projects"] if p["name"] == project)["versions"]


def log_lines(wid):
    return [json.loads(line) for line in (works.root() / wid / "log.jsonl").read_text("utf-8").splitlines() if '"divisionVersion"' in line]


def test_save_lists_versions_in_both_views_and_marks_active(client):
    c = client
    plan, report = upload(c), upload(c, role="report")
    assert view(c, plan)["versions"] == [] and listed(c) == []
    first = put_settings(c, plan, VALUES)["settings"]
    v = saved(c, plan, "  1차년도   계획 ")
    assert [x["name"] for x in v["versions"]] == ["1차년도 계획"] and v["settings"] == first   # 같은 몸통(GET …/divisions) · 이름은 공백 정리
    one = v["versions"][0]
    assert set(one) == {"id", "name", "at", "values", "hash", "active"} and one["active"] is True
    assert one["hash"] == division_model.settings_hash(first) and one["values"] == first["values"] and one["at"] > 0
    assert len(one["id"]) == 8 and int(one["id"], 16) >= 0
    assert v["confirmed"] is None   # 버전 저장은 확정을 안 건드린다
    # values 를 주면 먼저 입력 값으로 저장하고 그 값을 버전으로
    v = saved(c, report, "2차년도", values=YEAR2)
    assert v["settings"]["values"]["current"] == 2 and [x["name"] for x in v["versions"]] == ["1차년도 계획", "2차년도"]   # 저장한 차례
    assert [x["active"] for x in v["versions"]] == [False, True]   # 당해 차년도까지 견준다
    assert view(c, plan)["versions"] == v["versions"] and view(c, plan)["settings"] == v["settings"]   # 같은 프로젝트의 다른 문서
    assert listed(c) == [{k: x[k] for k in ("id", "name", "at", "values")} for x in v["versions"]]
    assert projects.get("프로젝트 A")["versions"] == [{k: x[k] for k in ("id", "name", "values", "hash", "at")} for x in v["versions"]]
    # 입력을 바꾸면 어느 버전도 지금이 아니다 — 버전은 그대로
    put_settings(c, plan, CHANGED)
    after = view(c, report)["versions"]
    assert [x["active"] for x in after] == [False, False] and [x["hash"] for x in after] == [x["hash"] for x in v["versions"]]
    kinds = log_lines(plan) + log_lines(report)
    assert [(x["op"], x["name"], x["project"]) for x in kinds] == [("save", "1차년도 계획", "프로젝트 A"), ("save", "2차년도", "프로젝트 A")]
    assert kinds[0]["version"] == one["id"]
    server._persist_all()
    server.DOCS.clear()
    assert [x["name"] for x in view(c, plan)["versions"]] == ["1차년도 계획", "2차년도"]   # 다시 열어도


def test_same_name_conflicts_unless_replace(client):
    c = client
    wid = upload(c)
    put_settings(c, wid, VALUES)
    one = saved(c, wid, "1차년도")["versions"][0]
    saved(c, wid, "2차년도", values=YEAR2)
    r = save(c, wid, " 1차년도 ", values=CHANGED)
    assert r.status_code == 409 and "1차년도" in r.json()["detail"]
    assert projects.version_get("프로젝트 A", one["id"]) == {k: one[k] for k in ("id", "name", "values", "hash", "at")}   # 안 덮음
    assert save(c, wid, "1차년도", replace="yes").status_code == 409   # replace 는 true 일 때만
    v = saved(c, wid, "1차년도", replace=True, values=CHANGED)
    again = v["versions"][0]
    assert [x["name"] for x in v["versions"]] == ["1차년도", "2차년도"]   # 자리 그대로
    assert again["id"] == one["id"] and again["at"] >= one["at"] and again["hash"] != one["hash"] and again["active"] is True
    assert again["values"] == v["settings"]["values"] and v["settings"]["values"]["orgs"]["lead"] == "주관 C"


def test_apply_sets_input_and_confirms_for_the_whole_project(client):
    c = client
    plan, report, other_task = upload(c), upload(c, role="report"), upload(c, job="plan_fit")
    outside = upload(c, project="프로젝트 B")
    put_settings(c, outside, VALUES)
    first = put_settings(c, plan, VALUES)["settings"]
    vid = saved(c, plan, "1차년도")["versions"][0]["id"]
    put_settings(c, report, CHANGED)
    server.DOCS[other_task].division["plan"] = {"planId": "old-plan", "baseRev": 0, "settingsHash": division_model.settings_hash(view(c, other_task)["settings"])}
    r = c.post(f"/api/docs/{report}/divisions/versions/{vid}/apply")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["settings"] == first and v["versions"][0]["active"] is True
    cf = v["confirmed"]
    assert cf["scope"] == "project" and cf["project"] == "프로젝트 A" and cf["valid"] is True
    assert cf["hash"] == division_model.settings_hash(first) and cf["values"] == first["values"]
    stored = projects.get("프로젝트 A")
    assert stored["settings"] == first and stored["confirmed"] == {k: cf[k] for k in ("at", "hash", "values")} and len(stored["versions"]) == 1
    for wid in (plan, other_task):   # 같은 프로젝트의 다른 문서·다른 TASK 에도 입력·확정이 온다
        got = view(c, wid)
        assert got["settings"] == first and got["confirmed"]["valid"] is True and got["confirmed"]["hash"] == cf["hash"]
    assert server.DOCS[other_task].division["plan"] is None   # 값이 달라졌으니 옛 계획은 버린다
    assert server.DOCS[report].division["confirmed"] == stored["confirmed"]   # 작업 쪽에도 옮겨 적음
    assert view(c, outside)["versions"] == [] and view(c, outside)["confirmed"] is None   # 다른 프로젝트는 그대로
    assert [(x["op"], x["version"], x["name"]) for x in log_lines(report)] == [("apply", vid, "1차년도")]
    assert c.post(f"/api/docs/{report}/divisions/versions/없는버전/apply").status_code == 404


def test_delete_keeps_the_current_settings_and_confirm(client):
    c = client
    wid = upload(c)
    put_settings(c, wid, VALUES)
    a = saved(c, wid, "1차년도")["versions"][0]["id"]
    b = saved(c, wid, "2차년도", values=YEAR2)["versions"][1]["id"]
    assert c.post(f"/api/docs/{wid}/divisions/versions/{b}/apply").status_code == 200
    before = view(c, wid)
    r = c.delete(f"/api/docs/{wid}/divisions/versions/{b}")
    assert r.status_code == 200, r.text
    v = r.json()
    assert [x["id"] for x in v["versions"]] == [a] and v["settings"] == before["settings"] and v["confirmed"] == before["confirmed"]
    assert [x["id"] for x in listed(c)] == [a]
    assert c.delete(f"/api/docs/{wid}/divisions/versions/{b}").status_code == 404
    assert c.delete(f"/api/docs/{wid}/divisions/versions/x").status_code == 404
    assert [(x["op"], x["version"]) for x in log_lines(wid)][-1] == ("delete", b)


def test_versions_need_a_shared_project_work(client):
    c = client
    alone = upload(c, project=None)
    put_settings(c, alone, VALUES)
    old = upload(c)
    put_settings(c, old, VALUES)
    vid = saved(c, old, "1차년도")["versions"][0]["id"]
    branched = c.post(f"/api/works/{old}/round", json={"source": "current"})
    assert branched.status_code == 200, branched.text
    newer = branched.json()["mapping"][old]
    general = upload(c, job="doc_edit", project="프로젝트 G", kind="general")
    assert [x["id"] for x in view(c, newer)["versions"]] == [vid]   # 새 라운드 = 공유
    for wid in (alone, old, general):   # 프로젝트 없음 · 이전 라운드 · 일반 문서
        assert view(c, wid)["versions"] == []
        was = view(c, wid)["settings"]
        for r in (save(c, wid, "새 버전", values=CHANGED), c.post(f"/api/docs/{wid}/divisions/versions/{vid}/apply"),
                  c.delete(f"/api/docs/{wid}/divisions/versions/{vid}")):
            assert r.status_code == 409 and NOT_SHARED in r.json()["detail"], r.text
        assert view(c, wid)["settings"] == was   # 409 면 values 도 입력에 안 넣는다
    assert [x["id"] for x in projects.versions("프로젝트 A")] == [vid]


def test_save_rejects_missing_name_and_missing_values(client):
    c = client
    wid = upload(c)
    assert save(c, wid, "1차년도").status_code == 400   # 값 없음
    for bad in ({}, {"name": "   "}, {"name": 3}, {"name": "가" * 41}):
        r = c.post(f"/api/docs/{wid}/divisions/versions", json={"values": VALUES, **bad})
        assert r.status_code == 400, r.text
    assert view(c, wid)["settings"] is None   # 이름이 틀리면 values 도 입력에 안 넣는다
    assert save(c, wid, "1차년도", values={"stages": "x"}).status_code == 400
    assert saved(c, wid, "가" * 40, values=VALUES)["versions"][0]["name"] == "가" * 40
    assert projects.versions("프로젝트 A")[0]["name"] == "가" * 40 and len(projects.versions("프로젝트 A")) == 1


def test_limit_is_fifty_per_project(client, monkeypatch):
    c = client
    wid = upload(c)
    settings = put_settings(c, wid, VALUES)["settings"]
    monkeypatch.setattr(projects, "VERSION_MAX", 3)
    for i in range(3):
        saved(c, wid, f"버전 {i}")
    r = save(c, wid, "버전 3")
    assert r.status_code == 409 and "3개" in r.json()["detail"]
    assert len(saved(c, wid, "버전 1", replace=True)["versions"]) == 3   # 덮어쓰기는 한도와 무관
    with pytest.raises(projects.VersionLimit):
        projects.version_save("프로젝트 A", "버전 4", settings)
    other = upload(c, project="프로젝트 B")   # 한도는 프로젝트마다
    assert len(saved(c, other, "버전 0", values=VALUES)["versions"]) == 1


def test_versions_follow_a_project_rename_and_go_with_a_delete(client):
    c = client
    wid = upload(c)
    put_settings(c, wid, VALUES)
    vid = saved(c, wid, "1차년도")["versions"][0]["id"]
    c.post(f"/api/docs/{wid}/divisions/confirm", json={"values": CHANGED})   # 확정·입력 변경 뒤에도 버전은 남는다
    assert [x["id"] for x in projects.versions("프로젝트 A")] == [vid]
    assert c.put(f"/api/projects/{quote('프로젝트 A', safe='')}", json={"name": "새 이름"}).status_code == 200
    assert projects.versions("프로젝트 A") == [] and [x["id"] for x in projects.versions("새 이름")] == [vid]
    assert [x["id"] for x in view(c, wid)["versions"]] == [vid] and [x["id"] for x in listed(c, "새 이름")] == [vid]
    assert c.post(f"/api/docs/{wid}/divisions/versions/{vid}/apply").status_code == 200
    assert view(c, wid)["settings"]["values"]["orgs"]["lead"] == "주관 A"
    assert c.delete(f"/api/projects/{quote('새 이름', safe='')}").status_code == 200
    assert projects.versions("새 이름") == [] and view(c, wid)["versions"] == []


def test_broken_versions_block_every_route_and_are_not_overwritten(client):
    c = client
    wid = upload(c)
    put_settings(c, wid, VALUES)
    vid = saved(c, wid, "1차년도")["versions"][0]["id"]
    path = works.root() / "projects.json"
    good = json.loads(path.read_text("utf-8"))
    for bad in ("버전", [{"id": vid, "name": "1차년도"}], [{**good["projects"]["프로젝트 A"]["versions"][0], "at": "어제"}],
                good["projects"]["프로젝트 A"]["versions"] * 2):   # 꼴이 아님 · 칸 빠짐 · 칸 꼴 틀림 · id 겹침
        data = json.loads(json.dumps(good))
        data["projects"]["프로젝트 A"]["versions"] = bad
        text = json.dumps(data, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        assert c.get("/api/projects").status_code == 409
        assert c.get(f"/api/docs/{wid}/divisions").status_code == 409
        assert save(c, wid, "2차년도").status_code == 409
        assert c.post(f"/api/docs/{wid}/divisions/versions/{vid}/apply").status_code == 409
        assert c.delete(f"/api/docs/{wid}/divisions/versions/{vid}").status_code == 409
        assert path.read_text("utf-8") == text
    good["projects"]["프로젝트 A"]["versions"] = None   # 없어도 되는 칸
    path.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    assert view(c, wid)["versions"] == [] and listed(c) == []


def test_version_functions_copy_and_handle_missing_names(client):
    c = client
    wid = upload(c)
    settings = put_settings(c, wid, VALUES)["settings"]
    assert projects.versions("") == [] and projects.versions("없는 프로젝트") == []
    assert projects.version_save("", "1차년도", settings) is None
    with pytest.raises(projects.VersionName):
        projects.version_save("프로젝트 A", "", settings)
    got = projects.version_save(" 프로젝트   A ", "1차년도", settings)
    got["values"]["stages"] = [9]   # 사본을 돌려준다
    assert projects.version_get("프로젝트 A", got["id"])["values"] == settings["values"]
    with pytest.raises(projects.VersionConflict):
        projects.version_save("프로젝트 A", "1차년도", settings)
    for call in (lambda: projects.version_get("프로젝트 A", "없음"), lambda: projects.version_delete("프로젝트 A", "없음"),
                 lambda: projects.version_delete("", got["id"])):
        with pytest.raises(projects.VersionMissing):
            call()
    assert projects.version_delete("프로젝트 A", got["id"])["name"] == "1차년도" and projects.versions("프로젝트 A") == []
    made = projects.version_save("기록 없는 프로젝트", "처음", settings)   # 기록이 없으면 그 설정으로 기록을 만든다
    assert projects.get("기록 없는 프로젝트")["settings"] == settings and projects.versions("기록 없는 프로젝트")[0]["id"] == made["id"]
