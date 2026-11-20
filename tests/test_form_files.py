"""저장한 양식 · 워크플로우마다의 양식 설정(spec_워크플로우 ② §18-9 「양식」 — app/form_files.py): 저장 · 같은 내용 · 이름 · 종류 · 지우기 · 설정(기본값 · 고정) · 설정의 판 · 저장 파일 보호 · 메모리만."""
import json

import pytest

from app import form_files as F

HWPX = b"PK\x03\x04 form bytes"


def test_add_keeps_the_file_as_uploaded_and_returns_the_same_one_for_the_same_content():
    f, made = F.add("  연차보고서   양식 ", "보고서 서식.hwpx", "hwpx", HWPX, "report")
    assert made and F.ID.fullmatch(f["id"]) and (f["name"], f["file"], f["fmt"], f["kind"], f["size"]) == ("연차보고서 양식", "보고서 서식.hwpx", "hwpx", "report", len(HWPX))
    assert F.data(f["id"]) == HWPX and (F.root() / f"{f['id']}.hwpx").read_bytes() == HWPX   # 올린 그대로
    again, made2 = F.add("다른 이름", "x.hwpx", "hwpx", HWPX, "plan")
    assert not made2 and again == f   # 같은 내용 — 있던 양식(이름 · 종류는 그대로)
    other, made3 = F.add("계획서 양식", "p.hwpx", "hwpx", HWPX + b"!", "plan")
    assert made3 and [x["id"] for x in F.listing()["files"]] == [f["id"], other["id"]]
    assert F.get("nope") is None and F.get("f_00000000") is None and F.data("f_00000000") is None


@pytest.mark.parametrize("args, word", [(("", "a.hwpx", "hwpx", HWPX, ""), "이름"), (("가" * 61, "a.hwpx", "hwpx", HWPX, ""), "60자"), (("가", "a.hwp", "hwp", HWPX, ""), "hwpx"),
                                        (("가", "a.hwpx", "hwpx", b"", ""), "빈 파일"), (("가", "a.hwpx", "hwpx", HWPX, "part"), "문서 종류")])
def test_add_rejects_bad_values(args, word):
    with pytest.raises(ValueError) as e:
        F.add(*args)
    assert word in str(e.value) and not isinstance(e.value, F.Refused) and F.listing()["files"] == []


def test_workflow_setting_points_a_target_slot_at_a_form():
    """설정 = 워크플로우의 목적 문서 칸에 건 양식 — 기본값(바꿀 수 있음) · 고정(늘 그 양식). 정할 때마다 판이 오른다(시작 요청이 읽은 판과 견준다)."""
    f, _ = F.add("연차보고서 양식", "r.hwpx", "hwpx", HWPX, "report")
    assert F.slot("plan_to_report") is None and F.listing()["rev"] == 0
    assert F.slot_set("plan_to_report", "target", f["id"], "default") == 1
    assert F.slot("plan_to_report") == {"file": f["id"], "mode": "default", "form": f} and F.uses(f["id"]) == [("plan_to_report", "target", "default")]
    assert F.slot_set("plan_to_report", "target", f["id"], "default") == 1   # 그대로 — 판이 안 오른다
    assert F.slot_set("plan_to_report", "target", f["id"], "fixed") == 2 and F.slot("plan_to_report")["mode"] == "fixed"
    for bad in (("plan_to_report", "part", f["id"], "fixed"), ("plan_to_report", "target", "f_00000000", "fixed"), ("plan_to_report", "target", f["id"], "always"), ("", "target", f["id"], "fixed")):
        with pytest.raises(ValueError):
            F.slot_set(*bad)
    with pytest.raises(F.Refused) as e:   # 설정에 쓰는 양식은 못 지우고 종류도 못 바꾼다
        F.delete(f["id"])
    assert "1개" in str(e.value)
    with pytest.raises(F.Refused):
        F.update(f["id"], kind="plan")
    assert F.update(f["id"], name="새 이름")["name"] == "새 이름" and F.slot("plan_to_report")["form"]["name"] == "새 이름"
    assert F.slot_set("plan_to_report", "target", None) == 3 and F.slot("plan_to_report") is None and F.slot_set("plan_to_report", "target", None) == 3
    assert F.update(f["id"], kind="plan")["kind"] == "plan" and F.delete(f["id"]) is True and F.delete(f["id"]) is False
    assert F.listing()["files"] == [] and not (F.root() / f"{f['id']}.hwpx").exists()
    assert F.update("f_00000000", name="x") is None


def test_forget_job_drops_the_settings_of_a_removed_workflow():
    f, _ = F.add("양식", "r.hwpx", "hwpx", HWPX, "report")
    F.slot_set("u_12345678", "target", f["id"], "fixed")
    assert F.forget_job("u_12345678") is True and F.forget_job("u_12345678") is False and F.uses(f["id"]) == [] and F.delete(f["id"])


def test_a_broken_index_is_not_overwritten():
    f, _ = F.add("양식", "r.hwpx", "hwpx", HWPX, "report")
    p = F.root() / "index.json"
    p.write_text("{broken", encoding="utf-8")
    assert F.broken() and F.listing() == {"files": [], "slots": {}, "rev": 0, "broken": True}
    for call in (lambda: F.add("둘", "b.hwpx", "hwpx", HWPX + b"2"), lambda: F.delete(f["id"]), lambda: F.slot_set("plan_to_report", "target", f["id"]), lambda: F.update(f["id"], name="x")):
        with pytest.raises(F.Refused):
            call()
    assert p.read_text(encoding="utf-8") == "{broken"
    # 꼴이 틀린 줄 · 머리의 모르는 키는 다른 줄을 쓸 때도 그대로 남는다
    p.write_text(json.dumps({"version": 3, "files": [{"id": "bad"}, {"id": f["id"], "name": "양식", "file": "r.hwpx", "fmt": "hwpx", "kind": "report", "sha256": f["sha256"], "size": 1, "at": 0}], "slots": {}, "more": 1}), encoding="utf-8")
    assert [x["id"] for x in F.listing()["files"]] == [f["id"]]
    F.update(f["id"], name="고침")
    got = json.loads(p.read_text(encoding="utf-8"))
    assert got["version"] == 4 and got["more"] == 1 and got["files"][0] == {"id": "bad"} and got["files"][1]["name"] == "고침"


def test_memory_only_when_the_store_is_off(monkeypatch):
    monkeypatch.setenv("NFM_FORM_FILES", "off")
    monkeypatch.setitem(F._MEMORY, "index", {"version": 0, "files": [], "slots": {}, "rev": 0})
    monkeypatch.setitem(F._MEMORY, "blobs", {})
    f, made = F.add("양식", "r.docx", "docx", b"docx bytes")
    assert made and F.root() is None and F.data(f["id"]) == b"docx bytes" and F.slot_set("doc_edit", "target", f["id"]) == 1 and F.slot("doc_edit")["form"]["fmt"] == "docx"


# ---------------------------------------------------------------- 끝점(app/form_files_api.py)
@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import form_files_api, server
    server.DOCS.clear()
    form_files_api._STARTS.clear()
    return TestClient(server.app)


def _put_form(c, path, **data):
    r = c.post("/api/form-files", files={"file": (path.name, path.read_bytes())}, data=data)
    assert r.status_code == 201, r.text
    return r.json()


def test_forms_are_stored_through_the_endpoint_and_set_on_a_workflow(client):
    import merge_data as M
    got = _put_form(client, M.REPORT_FORM)
    f = got["file"]
    assert got["made"] and f["kind"] == "report" and f["fmt"] == "hwpx" and f["usedBy"] == []   # 문서 종류는 양식 이름 문단으로 짐작
    assert _put_form(client, M.REPORT_FORM, name="다시")["made"] is False
    plan = _put_form(client, M.PLAN_FORM, name="계획서 양식")["file"]
    assert plan["kind"] == "plan" and plan["name"] == "계획서 양식"
    assert client.post("/api/form-files", files={"file": ("x.hwpx", b"not a document")}).status_code == 400
    assert client.post("/api/form-files", files={"file": ("x.txt", b"text")}).status_code == 400
    listing = client.get("/api/form-files").json()
    jobs = {j["job"]: j for j in listing["jobs"]}
    assert [x["id"] for x in listing["files"]] == [f["id"], plan["id"]] and listing["rev"] == 0 and not listing["broken"]
    assert {k: v for k, v in jobs["plan_to_report"].items() if k != "roles"} == {"job": "plan_to_report", "name": "사업계획서 → 연차보고서 이관", "kind": "report", "formats": ["hwpx"]} and jobs["plan_merge"]["kind"] == "plan"
    # 양식을 걸 수 있는 칸 = 수가 1인 칸(② §18-9 — 2026-11-20 사용자 "각 1이 되는것들은 특정 문서로 지정할 수 있도록"): 이관 = 원본 · 목적 · 취합 = 목적만(기관 문서는 여럿) · 문서 하나 = 그 문서
    assert [(x["role"], x["kind"], x["title"]) for x in jobs["plan_to_report"]["roles"]] == [("source", "plan", "원본 문서"), ("target", "report", "목적 문서")]
    assert [x["role"] for x in jobs["plan_merge"]["roles"]] == ["target"] and [x["role"] for x in jobs["plan_fit"]["roles"]] == ["target"]
    assert "style_copy" not in jobs and "report_merge" not in jobs and jobs["doc_edit"]["formats"] == ["hwpx", "docx"]
    r = client.put("/api/workflow-slots/plan_to_report", json={"target": {"file": f["id"], "mode": "default"}})
    want = {"file": f["id"], "mode": "default", "form": {k: f[k] for k in f if k != "usedBy"}}
    assert r.status_code == 200 and r.json() == {"slot": want, "slots": {"target": want, "source": None}, "rev": 1}
    assert client.get("/api/form-files").json()["files"][0]["usedBy"] == [{"job": "plan_to_report", "name": "사업계획서 → 연차보고서 이관", "role": "target", "mode": "default"}]
    for job, body, code in (("plan_to_report", {"target": {"file": plan["id"], "mode": "fixed"}}, 400), ("style_copy", {"target": {"file": f["id"]}}, 400), ("nope", {"target": None}, 400),
                            ("plan_to_report", {"target": {"file": "f_00000000"}}, 404), ("plan_to_report", {"target": {"file": f["id"], "mode": "always"}}, 400), ("plan_to_report", {"target": "x"}, 400)):
        assert client.put(f"/api/workflow-slots/{job}", json=body).status_code == code, (job, body)
    assert client.delete(f"/api/form-files/{f['id']}").status_code == 409 and client.put(f"/api/form-files/{f['id']}", json={"kind": "plan"}).status_code == 409
    assert client.put(f"/api/form-files/{f['id']}", json={"name": "연차보고서 표준 서식"}).json()["file"]["name"] == "연차보고서 표준 서식"
    assert client.get(f"/api/form-files/{f['id']}/file").content == M.REPORT_FORM.read_bytes()
    assert client.put("/api/workflow-slots/plan_to_report", json={"target": None}).json() == {"slot": None, "slots": {"target": None, "source": None}, "rev": 2}
    assert client.delete(f"/api/form-files/{f['id']}").json() == {"deleted": True} and client.delete(f"/api/form-files/{f['id']}").status_code == 404


def test_starting_from_a_form_makes_the_target_work_once(client):
    """양식으로 시작 — 그 양식으로 새 작업을 만들어 그 워크플로우의 다음 라운드의 목적 문서로 묶고, 쓴 양식을 그 작업에 적는다. 같은 시작을 다시 보내면 같은 작업."""
    import merge_data as M
    from app import works
    f = _put_form(client, M.REPORT_FORM)["file"]
    body = {"job": "plan_to_report", "request": "req-0001", "project": "양식 시험", "target": {"form": f["id"], "sha256": f["sha256"], "rev": 0}}
    r = client.post("/api/workflow-start", json=body)
    assert r.status_code == 200, r.text
    got = r.json()
    w = works.work(got["docId"])
    assert w["source"] == "form" and w["form"] == {"id": f["id"], "sha256": f["sha256"], "name": f["name"], "mode": ""} and got["form"]["id"] == f["id"]
    assert (w["task"]["job"], w["task"]["file"], w["task"]["project"], got["round"]) == ("plan_to_report", "report", "양식 시험", 1)
    assert client.post("/api/workflow-start", json=body).json()["docId"] == got["docId"] and len(works.list_works()) == 1   # 다시 보낸 시작 — 같은 작업
    assert client.post("/api/workflow-start", json={**body, "request": "req-0002"}).json()["round"] == 2   # 새 시작 — 다음 라운드
    for bad, code in (({**body, "request": "short"}, 400), ({**body, "request": "req-0003", "target": {"form": "f_00000000"}}, 404), ({**body, "request": "req-0004", "job": "style_copy"}, 400),
                      ({**body, "request": "req-0005", "target": {"form": f["id"], "sha256": "x"}}, 409), ({**body, "request": "req-0006", "target": {"form": f["id"], "rev": 9}}, 409)):
        assert client.post("/api/workflow-start", json=bad).status_code == code, bad
    assert len(works.list_works()) == 2   # 거절한 시작은 작업을 남기지 않는다


def test_a_fixed_form_cannot_be_bypassed_by_uploading(client):
    import merge_data as M
    from app import works
    f, other = _put_form(client, M.REPORT_FORM)["file"], _put_form(client, M.PLAN_FORM)["file"]
    assert client.put(f"/api/form-files/{other['id']}", json={"kind": "report"}).status_code == 200   # 종류만 맞춘 다른 양식
    assert client.put("/api/workflow-slots/plan_to_report", json={"target": {"file": f["id"], "mode": "fixed"}}).status_code == 200
    up = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    r = client.post(f"/api/works/{up}/start-task", json={"project": "고정 시험", "job": "plan_to_report", "file": "report"})
    assert r.status_code == 409 and "고정" in r.json()["detail"]   # 올린 파일을 목적 문서로 — 거절
    src = client.post("/api/docs?new=1", files={"file": (M.PLAN_FORM.name, M.PLAN_FORM.read_bytes())}).json()["docId"]
    assert client.post(f"/api/works/{src}/start-task", json={"project": "고정 시험", "job": "plan_to_report", "file": "plan"}).status_code == 200   # 원본 문서는 사람이 준다
    wrong = client.post("/api/workflow-start", json={"job": "plan_to_report", "request": "req-fixed-1", "project": "고정 시험", "target": {"form": other["id"]}})
    assert wrong.status_code == 409 and wrong.json()["reason"] == "fixedForm"
    ok = client.post("/api/workflow-start", json={"job": "plan_to_report", "request": "req-fixed-2", "project": "고정 시험", "target": {"form": f["id"]}})
    assert ok.status_code == 200 and works.work(ok.json()["docId"])["form"]["mode"] == "fixed" and ok.json()["task"]["project"] == "고정 시험"


def test_a_fixed_form_cannot_be_bypassed_by_putting_the_task(client):
    """`PUT …/task` 로 그 워크플로우의 목적 문서로 새로 들어오는 작업도 고정 양식이어야 한다 — 이미 그 워크플로우 · 그 역할이던 작업(하던 작업)은 막지 않는다(② §18-11 ⓒ)."""
    import merge_data as M
    f = _put_form(client, M.REPORT_FORM)["file"]
    up = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    put = lambda wid, **t: client.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "", **t})  # noqa: E731
    assert put(up).status_code == 200   # 고정 전 — 들어옴(하던 작업이 된다)
    assert client.put("/api/workflow-slots/plan_to_report", json={"target": {"file": f["id"], "mode": "fixed"}}).status_code == 200
    assert put(up, project="이어 하는 프로젝트").status_code == 200   # 하던 작업 — 프로젝트만 바꿔도 막지 않는다
    other = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    r = put(other)
    assert r.status_code == 409 and "고정" in r.json()["detail"]   # 새로 들어옴 — 거절
    assert put(other, file="plan").status_code == 200   # 원본 문서 칸은 사람이 준다
    assert client.put("/api/workflow-slots/plan_to_report", json={"target": {"file": f["id"], "mode": "default"}}).status_code == 200
    third = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    assert put(third).status_code == 200   # 기본값 — 다른 파일로 바꿀 수 있다


def test_a_form_is_saved_from_the_first_original_of_a_work_and_from_a_sample(client):
    import merge_data as M
    from app import server
    wid = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    assert client.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": "report", "job": "plan_to_report", "project": ""}).status_code == 200
    r = client.post(f"/api/form-files/from-work/{wid}", json={})
    assert r.status_code == 201, r.text
    f = r.json()["file"]
    assert r.json()["made"] and f["kind"] == "report" and f["fmt"] == "hwpx" and f["name"] == M.REPORT_FORM.stem and client.get(f"/api/form-files/{f['id']}/file").content == M.REPORT_FORM.read_bytes()
    assert client.post(f"/api/form-files/from-work/{wid}", json={"name": "다시"}).json()["made"] is False   # 같은 원본 — 있던 양식
    assert client.post("/api/form-files/from-work/000000000000", json={}).status_code == 404
    sample = next((p for p in sorted(server.SAMPLES.iterdir()) if p.is_file() and server.fmt_of(p.name) == "hwpx"), None)
    if sample is not None:
        s = client.post(f"/api/form-files/from-sample/{sample.name}", json={"name": "예제 양식", "kind": ""})
        assert s.status_code == 201 and s.json()["file"]["name"] == "예제 양식"
    assert client.post("/api/form-files/from-sample/..%5Cx.hwpx", json={}).status_code == 404
    assert client.post("/api/form-files/from-sample/none.hwpx", json={}).status_code == 404
    assert client.post(f"/api/form-files/from-work/{wid}", json={"kind": "part"}).status_code == 400


def test_a_source_slot_is_set_only_where_the_source_is_a_single_document(client):
    """원본 칸의 양식(② §18-9 — 수가 1인 칸마다): 이관의 원본(사업계획서) 칸에는 걸고, 원본이 여럿인 칸(취합의 기관 문서) · 없는 칸 · 종류가 다른 양식은 거절.
    두 칸을 한 번에 보내면 모두 검사한 뒤에 쓴다(하나가 틀리면 아무것도 안 바꿈)."""
    import merge_data as M
    plan, report = _put_form(client, M.PLAN_FORM)["file"], _put_form(client, M.REPORT_FORM)["file"]
    r = client.put("/api/workflow-slots/plan_to_report", json={"source": {"file": plan["id"], "mode": "default"}})
    assert r.status_code == 200 and r.json()["slots"]["source"]["file"] == plan["id"] and r.json()["slot"] is None   # slot = 목적 칸(옛 꼴)
    assert F.uses(plan["id"]) == [("plan_to_report", "source", "default")]
    bad = client.put("/api/workflow-slots/plan_to_report", json={"source": {"file": report["id"]}})
    assert bad.status_code == 400 and "원본 문서는 사업계획서" in bad.json()["detail"]
    for job, body in (("plan_merge", {"source": {"file": plan["id"]}}), ("plan_fit", {"source": {"file": plan["id"]}}), ("plan_to_report", {}), ("plan_to_report", {"part": None})):
        assert client.put(f"/api/workflow-slots/{job}", json=body).status_code == 400, (job, body)
    rev = F.listing()["rev"]
    both = client.put("/api/workflow-slots/plan_to_report", json={"target": {"file": report["id"], "mode": "fixed"}, "source": {"file": report["id"]}})
    assert both.status_code == 400 and F.slot("plan_to_report") is None and F.listing()["rev"] == rev   # 원본 칸이 틀려 목적 칸도 안 바뀜
    ok = client.put("/api/workflow-slots/plan_to_report", json={"target": {"file": report["id"], "mode": "fixed"}, "source": None}).json()
    assert ok["slots"]["target"]["mode"] == "fixed" and ok["slots"]["source"] is None


def test_the_source_slot_is_filled_from_a_form_into_the_target_bundle(client):
    """원본 칸을 양식으로(POST /api/workflow-start/source): 목적 작업의 묶음(프로젝트 · 워크플로우 · 라운드)에 원본 종류로 · 쓴 양식을 적음 · 같은 요청은 같은 작업 ·
    목적 문서가 프로젝트에 안 묶였으면 409 · 고정이면 올린 파일을 원본 칸에 못 넣는다(PUT …/task 409)."""
    import merge_data as M
    from app import works
    plan, report = _put_form(client, M.PLAN_FORM)["file"], _put_form(client, M.REPORT_FORM)["file"]
    main = client.post("/api/workflow-start", json={"job": "plan_to_report", "request": "req-main-1", "project": "원본 양식", "target": {"form": report["id"]}}).json()
    body = {"job": "plan_to_report", "main": main["docId"], "request": "req-src-01", "source": {"form": plan["id"], "sha256": plan["sha256"]}}
    r = client.post("/api/workflow-start/source", json=body)
    assert r.status_code == 200, r.text
    got = r.json()
    w = works.work(got["docId"])
    assert w["source"] == "form" and w["form"]["id"] == plan["id"] and got["form"] == {"id": plan["id"], "name": plan["name"], "mode": ""}
    assert (w["task"]["job"], w["task"]["file"], w["task"]["project"], w["task"].get("round") or 1) == ("plan_to_report", "plan", "원본 양식", main["round"])
    assert client.post("/api/workflow-start/source", json=body).json()["docId"] == got["docId"]   # 다시 보낸 요청 — 같은 작업
    loose = client.post("/api/docs?new=1", files={"file": (M.REPORT_FORM.name, M.REPORT_FORM.read_bytes())}).json()["docId"]
    nt = client.post("/api/workflow-start/source", json={**body, "request": "req-src-02", "main": loose})
    assert nt.status_code == 409 and nt.json()["reason"] == "notTarget"
    for bad, code in (({**body, "request": "short"}, 400), ({**body, "request": "req-src-03", "main": "000000000000"}, 404), ({**body, "request": "req-src-04", "source": {"form": report["id"]}}, 400),
                      ({**body, "request": "req-src-05", "job": "plan_merge"}, 400), ({**body, "request": "req-src-06", "source": {"form": plan["id"], "sha256": "x"}}, 409)):
        assert client.post("/api/workflow-start/source", json=bad).status_code == code, bad
    n = len(works.list_works())
    assert client.put("/api/workflow-slots/plan_to_report", json={"source": {"file": plan["id"], "mode": "fixed"}}).status_code == 200
    up = client.post("/api/docs?new=1", files={"file": (M.PLAN_FORM.name, M.PLAN_FORM.read_bytes())}).json()["docId"]
    put = client.put(f"/api/works/{up}/task", json={"kind": "rnd", "file": "plan", "job": "plan_to_report", "project": "원본 양식"})
    assert put.status_code == 409 and "원본 문서는 저장한 양식" in put.json()["detail"]   # 고정 — 올린 파일을 원본 칸에 못 넣음
    assert client.post(f"/api/works/{up}/start-task", json={"project": "원본 양식", "job": "plan_to_report", "file": "plan"}).status_code == 409
    assert client.post("/api/workflow-start/source", json={**body, "request": "req-src-07", "source": {"form": plan["id"]}}).status_code == 200   # 고정한 그 양식은 된다
    assert len(works.list_works()) == n + 2
