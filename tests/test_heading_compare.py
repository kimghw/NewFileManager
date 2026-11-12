"""비교는 저장된 분석을 읽기만 하며 문서·분석 실행을 만들지 않는다."""
import gzip
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_runs, server, works


SAMPLE = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)
    server.DOCS.clear()


def _session(analyze=True):
    session = server.Session(SAMPLE.name, SAMPLE.read_bytes())
    works.create(session.id, session.name, "hwpx", session.original)
    server.DOCS[session.id] = session
    if analyze:
        job = heading_runs.run_sync(session, 2, False)
        assert job.status == "done", job.error
    return session


def _forbid_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("preview attempted a document load, analysis, verification, write or log")
    for module, names in ((server, ("_sess", "_reopen", "_start", "_admit")),
                          (heading_runs, ("start", "run_sync", "state")),
                          (works, ("load", "_write", "_write_json", "log"))):
        for name in names:
            # heading_runs.summary/labels legitimately call state on the isolated proxy.
            if module is heading_runs and name == "state":
                continue
            monkeypatch.setattr(module, name, forbidden)


def _files(folder):
    return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in folder.rglob("*") if p.is_file()}


def test_closed_work_preview_preserves_files_and_does_not_reopen(client, monkeypatch):
    session = _session()
    expected = json.loads(json.dumps(heading_runs.summary(session)))
    expected_labels = json.loads(json.dumps(heading_runs.labels(session)))
    expected_graph = json.loads(json.dumps(heading_runs.graph(session)))
    folder = works.folder(session.id)
    before = _files(folder)
    server.DOCS.clear()
    _forbid_side_effects(monkeypatch)

    response = client.get(f"/api/works/{session.id}/headings-preview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["work"]["name"] == SAMPLE.name and not data["work"]["open"]
    assert data["summary"]["stage1"] == expected["stage1"]
    assert data["summary"]["stage2"] == expected["stage2"]
    assert data["labels"] == expected_labels and data["graph"] == expected_graph
    assert data["readiness"] == {"stage1": "ready", "stage2": "ready", "stage3": "missing"}
    assert not data["errors"] and not server.DOCS
    assert _files(folder) == before


def test_active_preview_uses_live_revision_without_touching_session(client, monkeypatch):
    session = _session()
    monkeypatch.setattr(server, "_persist_all", lambda: None)  # 배경 저장 스레드(앞 시험이 켠 것, 1.5초마다)가 이 사이에 rev 4 를 써 버리면 「파일 그대로」가 깨진다(경합, 2026-11-10)
    session.rev = 4  # 배경 저장 전의 최신 편집 차례
    touched = session.touched
    before = _files(works.folder(session.id))
    _forbid_side_effects(monkeypatch)

    response = client.get(f"/api/works/{session.id}/headings-preview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["work"]["rev"] == data["summary"]["rev"] == 4
    assert data["work"]["open"]
    assert data["readiness"]["stage1"] == data["readiness"]["stage2"] == "stale"
    assert session.touched == touched and _files(works.folder(session.id)) == before


def test_reextracted_labels_make_old_graph_stale_even_at_same_revision(client):
    session = _session()
    old_run = heading_runs.graph(session)["meta"]["stage1Run"]
    heading_runs.run_sync(session, 1, False)
    assert heading_runs.state(session)["stage1"]["meta"]["run"] != old_run
    data = client.get(f"/api/works/{session.id}/headings-preview").json()
    assert data["readiness"]["stage1"] == "ready"
    assert data["readiness"]["stage2"] == "stale"
    assert data["summary"]["stage2"]["stale"]
    assert data["graph"]["meta"]["stage1Run"] == old_run


def test_active_preview_after_drift_check(client):
    """열어 둔 문서를 뼈대와 견준 뒤(heading_drift.check 가 세션 상태에 Lock·캐시를 둠)에도 미리보기가 된다 — 전에는 그 Lock 을 deepcopy 하다 500."""
    from app import heading_drift
    session = _session()
    heading_drift.check(session)
    assert "driftLock" in heading_runs.state(session)
    response = client.get(f"/api/works/{session.id}/headings-preview")
    assert response.status_code == 200, response.text
    assert response.json()["readiness"]["stage2"] == "ready"


def test_missing_analysis_does_not_extract_or_add_session_state(client, monkeypatch):
    session = _session(analyze=False)
    _forbid_side_effects(monkeypatch)
    data = client.get(f"/api/works/{session.id}/headings-preview").json()
    assert data["readiness"] == dict.fromkeys(("stage1", "stage2", "stage3"), "missing")
    assert data["labels"] == {"labels": [], "formats": 0} and data["graph"] is None
    assert not hasattr(session, "heads")


@pytest.mark.parametrize("damage", ["gzip", "structure", "pointer", "missing_file", "bad_number"])
def test_corrupt_analysis_is_reported_without_500(client, monkeypatch, damage):
    session = _session()
    st = heading_runs.state(session)
    directory = works.folder(session.id) / "headings"
    graph_file = directory / str(st["stage2"]["meta"]["run"]) / "graph.json.gz"
    if damage == "gzip":
        graph_file.write_bytes(b"\x1f\x8b\x08")
    elif damage == "structure":
        graph_file.write_bytes(gzip.compress(json.dumps({"meta": {}, "counts": {}}).encode()))
    elif damage == "pointer":
        (directory / "current.json").write_text("{broken", encoding="utf-8")
    elif damage == "missing_file":
        graph_file.unlink()
    else:
        (directory / "current.json").write_text('{"stage2": "../"}', encoding="utf-8")
    server.DOCS.clear()
    _forbid_side_effects(monkeypatch)
    response = client.get(f"/api/works/{session.id}/headings-preview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["graph"] is None and data["errors"]
    assert data["readiness"]["stage2"] == "invalid"
    assert not server.DOCS


def test_docx_is_explicitly_unsupported_and_missing_work_is_404(client, monkeypatch):
    wid = "a12345678901"
    works.create(wid, "양식.docx", "docx", b"not opened by preview")
    _forbid_side_effects(monkeypatch)
    response = client.get(f"/api/works/{wid}/headings-preview")
    assert response.status_code == 200
    data = response.json()
    assert not data["supported"] and data["work"]["format"] == "docx"
    assert data["readiness"] == dict.fromkeys(("stage1", "stage2", "stage3"), "unsupported")
    assert client.get("/api/works/000000000000/headings-preview").status_code == 404
