"""TASK 옵션(spec_구역 ② §1 「TASK 옵션 — TASK 묶음마다」) — 저장소 app/task_options.py 와 끝점 GET·PUT /api/works/{wid}/task-options.

문서를 열지 않는다(작업 폴더와 task 만 쓴다) — 분석·LLM·한글 없음. 작업 폴더는 conftest 가 시험마다 임시 폴더로 둔다(NFM_WORKS)."""
import json

import pytest
from fastapi.testclient import TestClient

from app import server, task_options, works, zones


@pytest.fixture
def client():
    return TestClient(server.app)


def make(client, n, job="plan_merge", project="", kind=None, file="plan", **more):
    """작업 하나(문서 없이 폴더만) + task → 작업 id. kind 를 안 주면 그 TASK 의 작업 종류."""
    wid = f"{n:012x}"
    works.create(wid, f"doc{n}.hwpx", "hwpx", b"task options")
    task = {"kind": server.TASK_KIND.get(job, "rnd") if kind is None else kind, "file": file, "job": job, "project": project, **more}
    r = client.put(f"/api/works/{wid}/task", json=task)
    assert r.status_code == 200, r.text
    return wid


def get(client, wid):
    r = client.get(f"/api/works/{wid}/task-options")
    assert r.status_code == 200, r.text
    return r.json()


def put(client, wid, dims, **more):
    return client.put(f"/api/works/{wid}/task-options", json={"zones": {"dims": dims}, **more})


def stored():
    return json.loads((works.root() / "task_options.json").read_text("utf-8"))


def test_defaults_follow_the_task_and_nothing_is_written(client):
    """키 없음 = 기본값: 취합은 기관, 그 밖의 연구개발 TASK 는 없음 — 읽기만 해서는 파일이 안 생긴다."""
    merge, fit = make(client, 1, "plan_merge", "프로젝트 A"), make(client, 2, "plan_fit", "프로젝트 A")
    assert get(client, merge) == {"scope": "p:프로젝트 A|plan_merge|1", "offered": True, "zones": {"dims": ["org"], "defaulted": True}, "rev": 0}
    assert get(client, fit) == {"scope": "p:프로젝트 A|plan_fit|1", "offered": True, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    assert task_options.resolve(works.work(merge)) == get(client, merge)
    assert not (works.root() / "task_options.json").exists()
    assert set(task_options.ZONES_DEFAULT) <= set(server.TASK["job"])
    assert all(v == [d for d in zones.DIMS if d in v] for v in task_options.ZONES_DEFAULT.values())   # 기본값도 zones.DIMS 차례 · 아는 기준만


def test_person_choice_is_stored_with_a_revision(client):
    """사람이 정한 값: 차례는 zones.DIMS 로 · 중복은 버림 · 빈 목록 = 끔 · 기본값과 같은 값도 적는다(defaulted False) · 저장마다 판 +1 · 작업의 task 는 그대로."""
    wid = make(client, 1, "plan_merge", "프로젝트 A")
    task = works.work(wid)["task"]
    r = put(client, wid, ["year", "org", "year"])
    assert r.status_code == 200, r.text
    assert r.json() == {"scope": "p:프로젝트 A|plan_merge|1", "offered": True, "zones": {"dims": ["org", "year"], "defaulted": False}, "rev": 1}
    assert get(client, wid) == r.json()
    assert put(client, wid, []).json()["zones"] == {"dims": [], "defaulted": False}          # 빈 목록 = 사람이 끔(기본값 기관으로 돌아가지 않는다)
    assert get(client, wid)["zones"] == {"dims": [], "defaulted": False} and get(client, wid)["rev"] == 2
    assert put(client, wid, ["org"]).json() == {"scope": "p:프로젝트 A|plan_merge|1", "offered": True, "zones": {"dims": ["org"], "defaulted": False}, "rev": 3}   # 기본값과 같아도 사람이 정한 것
    data = stored()
    assert data["version"] == 1 and list(data["scopes"]) == ["p:프로젝트 A|plan_merge|1"]
    rec = data["scopes"]["p:프로젝트 A|plan_merge|1"]
    assert rec["zones"] == {"dims": ["org"]} and rec["rev"] == 3 and isinstance(rec["updated"], str) and rec["updated"]
    assert works.work(wid)["task"] == task                                                    # 옵션은 task 에 안 들어간다
    line = [e for e in works.events(wid) if e["kind"] == "taskOptions"][-1]
    assert (line["scope"], line["dims"], line["rev"]) == ("p:프로젝트 A|plan_merge|1", ["org"], 3)


def test_documents_of_one_group_share_and_other_groups_do_not(client):
    """같은 묶음(프로젝트 · TASK · 라운드)의 문서는 같은 옵션 — 다른 라운드 · 다른 TASK · 다른 프로젝트는 따로. 프로젝트 없는 작업은 작업마다."""
    base = make(client, 1, "plan_merge", "프로젝트 A")
    part = make(client, 2, "plan_merge", "프로젝트 A", file="part")
    later = make(client, 3, "plan_merge", "프로젝트 A", round=2)
    other_job = make(client, 4, "plan_to_report", "프로젝트 A", file="report")
    other_project = make(client, 5, "plan_merge", "프로젝트 B")
    assert put(client, part, ["stage"]).status_code == 200                                    # 기관 문서에서 정해도 묶음의 것
    assert get(client, base)["zones"] == {"dims": ["stage"], "defaulted": False} and get(client, base)["scope"] == get(client, part)["scope"]
    assert get(client, later) == {"scope": "p:프로젝트 A|plan_merge|2", "offered": True, "zones": {"dims": ["org"], "defaulted": True}, "rev": 0}
    assert get(client, other_job)["zones"] == {"dims": [], "defaulted": True}
    assert get(client, other_project)["zones"] == {"dims": ["org"], "defaulted": True}
    one, two = make(client, 6, "plan_merge"), make(client, 7, "plan_merge")
    assert (get(client, one)["scope"], get(client, two)["scope"]) == (f"w:{one}", f"w:{two}")
    assert put(client, one, ["org", "year"]).status_code == 200
    assert get(client, one)["zones"]["dims"] == ["org", "year"] and get(client, two)["zones"] == {"dims": ["org"], "defaulted": True}
    assert task_options.scope_of({"id": one, "task": {"project": "  프로젝트   A ", "job": "plan_fit"}}) == "p:프로젝트 A|plan_fit|1"   # 이름 정리 · 라운드 없는 옛 작업 = 1


def test_only_research_documents_are_offered(client):
    """offered = task 가 없거나 작업 종류가 연구개발(화면 taskRnd() 와 같게) — 일반 문서 · 종류를 비운 작업은 아니고, 그 작업의 PUT 은 400(아무것도 안 적는다)."""
    general = make(client, 1, "doc_edit", "프로젝트 A", file="")
    blank = make(client, 2, "", kind="", file="")
    assert get(client, general) == {"scope": "p:프로젝트 A|doc_edit|1", "offered": False, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    assert get(client, blank)["offered"] is False
    for wid in (general, blank):
        r = put(client, wid, ["org"])
        assert r.status_code == 400 and "편집 구역" in r.json()["detail"], r.text
    assert not (works.root() / "task_options.json").exists()
    bare = f"{9:012x}"
    works.create(bare, "bare.hwpx", "hwpx", b"no task")                                       # task 를 고른 적 없는 작업 — 전처럼 연구개발로 본다
    assert get(client, bare) == {"scope": f"w:{bare}", "offered": True, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    assert task_options.resolve(None)["offered"] is True and task_options.resolve({"id": "x", "task": None})["scope"] == "w:x"
    with pytest.raises(ValueError):
        task_options.set_zones(None, ["org"])                                                 # 어느 묶음인지 알 수 없다


def test_bad_requests_are_rejected(client):
    wid = make(client, 1, "plan_merge", "프로젝트 A")
    for dims in (["org", "team"], ["ORG"], "org", None, [1], [["org"]], {"org": True}):
        r = put(client, wid, dims)
        assert r.status_code == 400 and isinstance(r.json()["detail"], str) and r.json()["detail"], (dims, r.text)
    for body in ({}, {"zones": None}, {"zones": {}}, {"zones": ["org"]}, {"dims": ["org"]}):
        assert client.put(f"/api/works/{wid}/task-options", json=body).status_code == 400, body
    for rev in ("1", 1.5, True, -1):
        assert put(client, wid, ["org"], rev=rev).status_code == 400, rev
    assert get(client, wid)["rev"] == 0 and not (works.root() / "task_options.json").exists()
    assert client.get("/api/works/0000000000ee/task-options").status_code == 404                # 없는 작업
    assert put(client, "0000000000ee", ["org"]).status_code == 404
    with pytest.raises(ValueError):
        task_options.set_zones(works.work(wid), ["org", "nope"])


def test_stale_revision_is_a_conflict(client):
    """rev 를 보내면 저장된 판과 같을 때만 적는다 — 다르면 409 staleOptions(지금 옵션을 함께) · 안 보내면 그냥 적는다(시작 화면)."""
    wid = make(client, 1, "plan_merge", "프로젝트 A")
    assert put(client, wid, ["org", "stage"], rev=0).json()["rev"] == 1                       # 저장된 것이 없을 때의 판 = 0
    r = put(client, wid, ["year"], rev=0)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["reason"] == "staleOptions" and detail["message"] and detail["options"] == get(client, wid)
    assert get(client, wid)["zones"]["dims"] == ["org", "stage"] and get(client, wid)["rev"] == 1
    assert put(client, wid, ["year"], rev=1).json() == {"scope": "p:프로젝트 A|plan_merge|1", "offered": True, "zones": {"dims": ["year"], "defaulted": False}, "rev": 2}
    assert put(client, wid, []).json()["rev"] == 3                                            # rev 없이
    with pytest.raises(task_options.Stale):
        task_options.set_zones(works.work(wid), ["org"], rev=1)


def test_project_rename_moves_the_options(client):
    a1, a2 = make(client, 1, "plan_merge", "프로젝트 A"), make(client, 2, "plan_merge", "프로젝트 A", round=2)
    fit, b = make(client, 3, "plan_fit", "프로젝트 A"), make(client, 4, "plan_merge", "프로젝트 B")
    for wid, dims in ((a1, ["org", "year"]), (a2, []), (fit, ["stage"]), (b, ["year"])):
        assert put(client, wid, dims).status_code == 200
    assert task_options.rename_project("프로젝트 A", "프로젝트 A") == 0 and task_options.rename_project("없는 프로젝트", "프로젝트 C") == 0
    assert task_options.rename_project("프로젝트 A", "프로젝트 C") == 3
    assert sorted(stored()["scopes"]) == ["p:프로젝트 B|plan_merge|1", "p:프로젝트 C|plan_fit|1", "p:프로젝트 C|plan_merge|1", "p:프로젝트 C|plan_merge|2"]
    assert get(client, a1) == {"scope": "p:프로젝트 A|plan_merge|1", "offered": True, "zones": {"dims": ["org"], "defaulted": True}, "rev": 0}   # 옛 이름에는 안 남는다
    moved = {"id": a1, "task": {**works.work(a1)["task"], "project": "프로젝트 C"}}
    assert task_options.resolve(moved) == {"scope": "p:프로젝트 C|plan_merge|1", "offered": True, "zones": {"dims": ["org", "year"], "defaulted": False}, "rev": 1}
    assert task_options.resolve({"id": a2, "task": {**works.work(a2)["task"], "project": "프로젝트 C"}})["zones"] == {"dims": [], "defaulted": False}
    assert get(client, b)["zones"]["dims"] == ["year"]
    # 새 이름으로 이미 정한 것이 있으면 안 덮는다(astra 결과 검토 7 — 이름 변경과 옵션 저장이 겹칠 때: 서버가 소속을 바꾼 뒤 사람이 새 이름으로 정한 것이 남는다) · 옛 열쇠는 지운다
    assert task_options.rename_project("프로젝트 C", "프로젝트 B") == 3
    assert sorted(stored()["scopes"]) == ["p:프로젝트 B|plan_fit|1", "p:프로젝트 B|plan_merge|1", "p:프로젝트 B|plan_merge|2"]
    assert stored()["scopes"]["p:프로젝트 B|plan_merge|1"]["zones"]["dims"] == ["year"] and stored()["scopes"]["p:프로젝트 B|plan_fit|1"]["zones"]["dims"] == ["stage"]


def test_put_checks_the_scope_the_screen_read(client):
    """화면이 옵션을 읽은 뒤 작업이 다른 묶음으로 옮겨졌으면, 판(rev)이 우연히 같아도 옛 화면의 저장이 새 묶음의 옵션을 덮지 않는다(astra 결과 검토 7) — scope 를 같이 보내면 409."""
    wid = make(client, 1, "plan_fit", "프로젝트 A")
    other = make(client, 2, "plan_fit", "프로젝트 B")
    assert put(client, wid, ["org"]).status_code == 200 and put(client, other, ["year"]).status_code == 200   # 두 묶음 모두 판 1
    seen = get(client, wid)
    assert seen["scope"] == "p:프로젝트 A|plan_fit|1" and seen["rev"] == 1
    assert client.put(f"/api/works/{wid}/task", json={**works.work(wid)["task"], "project": "프로젝트 B"}).status_code == 200   # 작업이 B 묶음으로 옮겨짐
    r = client.put(f"/api/works/{wid}/task-options", json={"zones": {"dims": ["stage"]}, "rev": seen["rev"], "scope": seen["scope"]})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "staleOptions" and r.json()["detail"]["options"]["scope"] == "p:프로젝트 B|plan_fit|1"
    assert get(client, other)["zones"]["dims"] == ["year"]                                              # B 묶음의 옵션은 그대로
    now = get(client, wid)
    ok = client.put(f"/api/works/{wid}/task-options", json={"zones": {"dims": ["stage"]}, "rev": now["rev"], "scope": now["scope"]})
    assert ok.status_code == 200 and ok.json()["zones"]["dims"] == ["stage"] and get(client, other)["zones"]["dims"] == ["stage"]   # 지금 범위로 읽고 보내면 적힌다(같은 묶음의 다른 문서도 같이 본다)
    assert client.put(f"/api/works/{wid}/task-options", json={"zones": {"dims": []}, "scope": 3}).status_code == 400


def test_new_round_inherits_only_what_a_person_chose(client):
    """새 라운드: 앞 묶음에 사람이 정한 것이 있을 때만 새 묶음에 같은 기준을 판 1 로 — 이미 있으면 안 덮는다(묶음의 문서마다 불러도 한 번)."""
    wid = make(client, 1, "plan_merge", "프로젝트 A")
    old = works.work(wid)["task"]
    new = {**old, "round": 2}
    assert task_options.copy_round(old, new) is False and not (works.root() / "task_options.json").exists()   # 기본값만 쓰던 묶음 — 적을 것이 없다
    put(client, wid, ["org"])
    put(client, wid, ["stage", "year"])
    assert task_options.copy_round(old, new) is True
    assert stored()["scopes"]["p:프로젝트 A|plan_merge|2"]["zones"] == {"dims": ["stage", "year"]} and stored()["scopes"]["p:프로젝트 A|plan_merge|2"]["rev"] == 1
    assert task_options.copy_round(old, new) is False                                         # 둘째 문서의 호출
    later = make(client, 2, "plan_merge", "프로젝트 A", round=2)
    assert get(client, later) == {"scope": "p:프로젝트 A|plan_merge|2", "offered": True, "zones": {"dims": ["stage", "year"], "defaulted": False}, "rev": 1}
    put(client, later, ["org"])
    put(client, wid, [])
    assert task_options.copy_round(old, new) is False and get(client, later)["zones"]["dims"] == ["org"]   # 새 묶음에서 정한 것을 안 덮는다
    assert task_options.copy_round(old, old) is False
    assert task_options.copy_round({"job": "plan_merge", "project": ""}, new) is False and task_options.copy_round(old, {"job": "plan_merge"}) is False   # 프로젝트 없는 task = 묶음 없음


def test_dropping_a_project_removes_its_options(client):
    a1, a2, b = make(client, 1, "plan_merge", "프로젝트 A"), make(client, 2, "plan_fit", "프로젝트 A", round=3), make(client, 3, "plan_merge", "프로젝트 B")
    solo = make(client, 4, "plan_merge")
    for wid in (a1, a2, b, solo):
        assert put(client, wid, ["year"]).status_code == 200
    assert task_options.drop_project("없는 프로젝트") == 0 and task_options.drop_project("") == 0
    assert task_options.drop_project("프로젝트 A") == 2
    assert sorted(stored()["scopes"]) == sorted(["p:프로젝트 B|plan_merge|1", f"w:{solo}"])
    assert get(client, a1)["zones"] == {"dims": ["org"], "defaulted": True} and get(client, a2)["zones"] == {"dims": [], "defaulted": True}
    assert get(client, b)["zones"]["dims"] == ["year"] and get(client, solo)["zones"]["dims"] == ["year"]


def test_project_names_with_a_bar_do_not_mix(client):
    """프로젝트 이름에 「|」 가 들어 있어도 열쇠가 섞이지 않는다 — 이름 변경 · 삭제가 그 프로젝트의 것만 찾는다."""
    plain = make(client, 1, "plan_merge", "A")
    barred = make(client, 2, "plan_merge", "A|plan_fit", round=2)
    tail = make(client, 3, "plan_fit", "A|plan_merge|1")
    for wid, dims in ((plain, ["org"]), (barred, ["stage"]), (tail, ["year"])):
        assert put(client, wid, dims).status_code == 200
    scopes = [get(client, w)["scope"] for w in (plain, barred, tail)]
    assert scopes == ["p:A|plan_merge|1", "p:A|plan_fit|plan_merge|2", "p:A|plan_merge|1|plan_fit|1"] and len(set(scopes)) == 3
    assert [task_options._split(s) for s in scopes] == [("A", "plan_merge", 1), ("A|plan_fit", "plan_merge", 2), ("A|plan_merge|1", "plan_fit", 1)]
    assert task_options._split(f"w:{plain}") is None and task_options._split("p:꼴이 다름") is None
    assert task_options.rename_project("A", "Z") == 1                                          # 「A|…」 로 시작하는 다른 프로젝트는 그대로
    assert sorted(stored()["scopes"]) == sorted(["p:Z|plan_merge|1", "p:A|plan_fit|plan_merge|2", "p:A|plan_merge|1|plan_fit|1"])
    assert task_options.drop_project("A") == 0 and task_options.drop_project("A|plan_fit") == 1
    assert get(client, barred)["zones"] == {"dims": ["org"], "defaulted": True} and get(client, tail)["zones"]["dims"] == ["year"]
    assert task_options.rename_project("A|plan_merge|1", "B|C") == 1
    assert task_options.resolve({"id": tail, "task": {**works.work(tail)["task"], "project": "B|C"}})["zones"] == {"dims": ["year"], "defaulted": False}


@pytest.mark.parametrize("text", ["{ 깨진 글", "[]", '{"version": 2, "scopes": {}}', '{"version": 1, "scopes": []}',
                                  '{"version": 1, "scopes": {"p:프로젝트 A|plan_merge|1": {"zones": {"dims": ["team"]}, "rev": 1}}}',
                                  '{"version": 1, "scopes": {"p:프로젝트 A|plan_merge|1": {"zones": {"dims": ["org"]}, "rev": 0}}}',
                                  '{"version": 1, "scopes": {"p:프로젝트 A|plan_merge|1": {"dims": ["org"], "rev": 1}}}'])
def test_broken_file_is_never_overwritten(client, text):
    """저장 파일이 깨졌으면(JSON 아님 · 꼴 다름) 덮어쓰지 않는다 — 읽기는 기본값 · 사람이 정하는 쓰기는 409 · 뒷정리는 아무것도 안 함."""
    wid = make(client, 1, "plan_merge", "프로젝트 A")
    path = works.root() / "task_options.json"
    path.write_text(text, "utf-8")
    assert get(client, wid) == {"scope": "p:프로젝트 A|plan_merge|1", "offered": True, "zones": {"dims": ["org"], "defaulted": True}, "rev": 0}
    r = put(client, wid, ["year"])
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "brokenOptions" and r.json()["detail"]["message"], r.text
    with pytest.raises(task_options.Broken):
        task_options.set_zones(works.work(wid), ["year"])
    task = works.work(wid)["task"]
    assert task_options.rename_project("프로젝트 A", "프로젝트 B") == 0 and task_options.drop_project("프로젝트 A") == 0
    assert task_options.copy_round(task, {**task, "round": 2}) is False
    assert path.read_text("utf-8") == text
    assert not [e for e in works.events(wid) if e["kind"] == "taskOptions"]


def test_memory_when_work_storage_is_off(client, monkeypatch):
    """작업 저장이 꺼져 있으면(NFM_WORKS=off) 프로세스 메모리에만 — 작업이 없으니 문서마다(w: 범위), id 꼴이 아닌 것은 404."""
    monkeypatch.setenv("NFM_WORKS", "off")
    monkeypatch.setattr(task_options, "_MEMORY", {})
    assert works.root() is None
    one, two = "00000000a001", "00000000a002"
    assert get(client, one) == {"scope": f"w:{one}", "offered": True, "zones": {"dims": [], "defaulted": True}, "rev": 0}
    assert put(client, one, ["year", "org"]).json() == {"scope": f"w:{one}", "offered": True, "zones": {"dims": ["org", "year"], "defaulted": False}, "rev": 1}
    assert get(client, one)["zones"]["dims"] == ["org", "year"] and get(client, two)["zones"] == {"dims": [], "defaulted": True}
    assert put(client, one, [], rev=0).status_code == 409 and put(client, one, [], rev=1).json()["rev"] == 2
    assert client.get("/api/works/not-a-work/task-options").status_code == 404
    task = {"kind": "rnd", "job": "plan_merge", "project": "프로젝트 A"}                         # 저장소 함수는 메모리에서도 같은 일을 한다
    assert task_options.set_zones({"id": one, "task": task}, ["stage"])["scope"] == "p:프로젝트 A|plan_merge|1"
    assert task_options.copy_round(task, {**task, "round": 2}) is True and task_options.rename_project("프로젝트 A", "프로젝트 B") == 2
    assert task_options.resolve({"id": two, "task": {**task, "project": "프로젝트 B", "round": 2}})["zones"] == {"dims": ["stage"], "defaulted": False}
    assert task_options.drop_project("프로젝트 B") == 2 and sorted(task_options._MEMORY) == [f"w:{one}"]
