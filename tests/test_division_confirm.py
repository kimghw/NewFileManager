"""1단계 「구분 기준」 — 구성 확정 · 파일 올려 추출(spec_작업 ② §18): `POST …/divisions/confirm` · `GET …/divisions` 의 confirmed · `POST /api/divisions/read-file`."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import gather_data as D
from app import division_model, pdf_render, projects, server, works

SAMPLES = Path(__file__).parents[1] / "samples"
SAMPLE = SAMPLES / "기술수요조사서.hwpx"
VALUES = {"stages": [2, 1], "orgs": {"lead": "주관 A", "joint": ["공동 B"]}}
CHANGED = {"stages": [1, 2], "orgs": {"lead": "주관 C", "joint": ["공동 D"]}}


@pytest.fixture
def client(monkeypatch):
    server.DOCS.clear()
    monkeypatch.setattr(server, "_start", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_ensure_persister", lambda: None)
    with TestClient(server.app) as c:
        yield c
    server.DOCS.clear()


def upload(c, role="plan", job="plan_to_report", project="프로젝트 A", number=1):
    r = c.post("/api/docs?new=1", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    assert r.status_code == 200, r.text
    wid = r.json()["docId"]
    if project is not None:
        r = c.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": role, "job": job, "project": project, "round": number})
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


def confirm(c, wid, values=None):
    r = c.post(f"/api/docs/{wid}/divisions/confirm", json={} if values is None else {"values": values})
    assert r.status_code == 200, r.text
    return r.json()


def test_confirm_on_project_is_shared_and_invalidated_by_a_change(client):
    c = client
    plan, report = upload(c), upload(c, role="report")
    assert view(c, plan)["confirmed"] is None
    assert c.post(f"/api/docs/{plan}/divisions/confirm", json={}).status_code == 400   # 값이 없으면
    saved = put_settings(c, plan, VALUES)["settings"]
    v = confirm(c, plan)
    cf = v["confirmed"]
    assert cf["scope"] == "project" and cf["project"] == "프로젝트 A" and cf["valid"] is True
    assert cf["hash"] == division_model.settings_hash(saved) and cf["values"] == saved["values"] and cf["at"] > 0
    assert set(cf) == {"at", "hash", "values", "scope", "project", "valid"} and v["settings"] == saved   # 같은 몸통(GET …/divisions)
    stored = projects.get("프로젝트 A")
    assert stored["confirmed"] == {k: cf[k] for k in ("at", "hash", "values")} and stored["settings"] == saved
    assert view(c, report)["confirmed"] == cf   # 같은 프로젝트의 다른 문서 — 공유
    assert next(p for p in c.get("/api/projects").json()["projects"] if p["name"] == "프로젝트 A")["confirmed"] == stored["confirmed"]
    log = (works.root() / plan / "log.jsonl").read_text("utf-8")
    assert '"kind":"divisionConfirm"' in log and '"scope":"project"' in log

    # 확정 뒤 입력을 바꾸면 확정은 남되 맞지 않음 — 다른 문서에서도
    changed = put_settings(c, report, CHANGED)
    assert changed["confirmed"]["valid"] is False and changed["confirmed"]["hash"] == cf["hash"]
    assert view(c, plan)["confirmed"]["valid"] is False and projects.confirmed("프로젝트 A")["hash"] == cf["hash"]
    # values 를 주면 먼저 입력으로 저장하고 확정
    again = confirm(c, plan, VALUES)
    assert again["settings"] == saved and again["confirmed"]["valid"] is True and again["confirmed"]["hash"] == cf["hash"]
    assert view(c, report)["confirmed"]["valid"] is True and view(c, report)["settings"] == saved
    assert c.post(f"/api/docs/{plan}/divisions/confirm", json={"values": {"stages": "x"}}).status_code == 400


def test_confirm_without_project_stays_with_the_work_and_survives_reopen(client):
    c = client
    wid = upload(c, project=None)
    put_settings(c, wid, VALUES)
    cf = confirm(c, wid)["confirmed"]
    assert cf["scope"] == "work" and "project" not in cf and cf["valid"] is True
    assert projects.listing() == []   # 프로젝트 기록은 안 생긴다
    server._persist_all()
    server.DOCS.clear()
    assert view(c, wid)["confirmed"] == cf   # 작업 폴더에서 다시 열어도
    cf2 = put_settings(c, wid, CHANGED)["confirmed"]
    assert cf2["valid"] is False and cf2["hash"] == cf["hash"]


def test_previous_round_keeps_the_confirm_of_its_time(client):
    c = client
    plan = upload(c)
    put_settings(c, plan, VALUES)
    old = confirm(c, plan)["confirmed"]
    branched = c.post(f"/api/works/{plan}/round", json={"source": "current"})
    assert branched.status_code == 200, branched.text
    newer = branched.json()["mapping"][plan]
    assert view(c, newer)["confirmed"] == old   # 새 라운드 = 공유(프로젝트의 확정)
    now = confirm(c, newer, CHANGED)["confirmed"]
    assert now["scope"] == "project" and now["hash"] != old["hash"]
    prev = view(c, plan)["confirmed"]   # 이전 라운드 — 그때 확정이 작업에 남아 있다
    assert prev["scope"] == "work" and {k: prev[k] for k in ("at", "hash", "values")} == {k: old[k] for k in ("at", "hash", "values")} and prev["valid"] is True
    server._persist_all()
    server.DOCS.clear()
    assert view(c, plan)["confirmed"]["hash"] == old["hash"] and view(c, newer)["confirmed"]["hash"] == now["hash"]


def test_confirm_refuses_a_broken_project_file(client):
    c = client
    wid = upload(c)
    put_settings(c, wid, VALUES)
    path = works.root() / "projects.json"
    path.write_text("{broken", encoding="utf-8")
    assert c.post(f"/api/docs/{wid}/divisions/confirm", json={}).status_code == 409
    assert path.read_text("utf-8") == "{broken"


def test_old_project_records_without_confirm_still_read(client):
    c = client
    wid = upload(c)
    put_settings(c, wid, VALUES)
    path = works.root() / "projects.json"
    data = json.loads(path.read_text("utf-8"))
    assert "confirmed" not in data["projects"]["프로젝트 A"]
    assert view(c, wid)["confirmed"] is None
    data["projects"]["프로젝트 A"]["confirmed"] = None
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert view(c, wid)["confirmed"] is None and c.get("/api/projects").status_code == 200


# ---- 파일 올려 추출 -------------------------------------------------------------------------------------------------

def _read_file(c, name, data):
    return c.post("/api/divisions/read-file", files={"file": (name, data)})


def test_read_file_returns_values_and_creates_no_work(client, monkeypatch):
    c = client
    data = D.base()["side"]["bytes"]   # 값(기관 셋)을 반영한 연구개발계획서
    before, docs = len(works.list_works()), set(server.DOCS)
    r = _read_file(c, "기관 문서.hwpx", data)
    assert r.status_code == 200, r.text
    got = r.json()
    assert set(got) == {"name", "form", "read"} and got["name"] == "기관 문서.hwpx" and got["form"] == "연구개발계획서"
    assert got["read"]["orgs"]["lead"] == D.LEAD and got["read"]["orgs"]["joint"] == [D.J1, D.J2] and got["read"]["stages"] == [2]
    assert len(works.list_works()) == before and set(server.DOCS) == docs   # 작업·세션을 만들지 않는다
    wid = c.post("/api/docs?new=1", files={"file": ("같은 문서.hwpx", data)}).json()["docId"]
    assert c.get(f"/api/docs/{wid}/divisions/read").json() == {k: got[k] for k in ("form", "read")}   # 「문서에서 추출」 과 같은 꼴
    count = len(works.list_works())

    for name, body in (("조사서.docx", (SAMPLES / "기술수요조사서.docx").read_bytes()), ("메모.txt", b"text"), ("깨진.hwpx", b"not a zip")):
        r = _read_file(c, name, body)
        assert r.status_code == 400, (name, r.text)
    r = _read_file(c, SAMPLE.name, SAMPLE.read_bytes())   # 양식 이름 문단 없음
    assert r.status_code == 400 and "양식 이름" in r.json()["detail"]
    r = _read_file(c, "계획서.hwp", b"hwp bytes")   # 시험은 한글 없음
    assert r.status_code == 400 and "한글" in r.json()["detail"]
    seen = []
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "hwp_to_hwpx", lambda raw, limit=None: seen.append(raw) or data)
    r = _read_file(c, "계획서.HWP", b"hwp bytes")
    assert r.status_code == 200 and r.json()["name"] == "계획서.HWP" and r.json()["read"] == got["read"] and seen == [b"hwp bytes"]
    assert len(works.list_works()) == count
