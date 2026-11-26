"""작업 저장(spec_작업) — 올리기 = 작업 하나, 편집 상태·검증 기록·기록(log)이 작업 폴더에 남고 서버를 다시 켜도(메모리를 비워도) 이어진다.
「다시 켬」 = 배경 저장을 한 번 돌리고(server._persist_all) 메모리 문서를 모두 비움(server.DOCS.clear)."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from app import server, works
from app.hwpx_doc import HP, HwpxDoc

SAMPLES = Path(__file__).parents[1] / "samples"
HWPX, DOCX = SAMPLES / "기술수요조사서.hwpx", SAMPLES / "기술수요조사서.docx"


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _upload(c, path=HWPX):
    # 늘 새 작업(?new=1) — 같은 파일을 다시 올리면 이어 여는 것(spec_작업 ② §1)은 test_works_reuse.py
    r = c.post("/api/docs?new=1", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _wait(c, d, kind, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if kind in v and not v[kind]["running"]:
            # 검증 기록은 결과가 나온 뒤 같은 스레드가 쓴다 — 기록까지 기다린다
            if any(r["kind"] == kind and r["rev"] == v[kind]["rev"] for r in works.runs(d)):
                return v
        time.sleep(0.05)
    raise AssertionError("검증이 끝나지 않음")


def _paras(blocks):
    out = []
    for b in blocks:
        if b["type"] == "paragraph":
            out.append(b)
        for c in b.get("cells", ()):
            out += _paras(c["blocks"])
    return out


def _texts(c, d):
    return [p for p in _paras(c.get(f"/api/docs/{d}").json()["blocks"]) if p["text"].strip()]


def _restart():
    server._persist_all()
    server.DOCS.clear()


def _events(c, d):
    return c.get(f"/api/works/{d}/log").json()["events"]


def test_upload_creates_work(client):
    d = _upload(client)
    folder = works.folder(d)
    assert (folder / "original.hwpx").read_bytes() == HWPX.read_bytes()
    w = json.loads((folder / "work.json").read_text("utf-8"))
    assert w["id"] == d and w["name"] == HWPX.name and w["format"] == "hwpx" and w["source"] == "upload" and w["rev"] == 0
    listed = client.get("/api/works").json()
    assert [x["id"] for x in listed] == [d] and listed[0]["open"] is True
    assert _events(client, d)[0]["kind"] == "create"
    _wait(client, d, "import")  # 첫 작업의 가져오기 검증이 끝나며 work.json 을 고친다(updated) — 그 뒤에 둘째 작업을 만들어야 차례가 정해진다(경합, 2026-11-10)
    s = client.post(f"/api/samples/{DOCX.name}").json()["docId"]
    assert works.work(s)["source"] == "sample" and works.work(s)["format"] == "docx"
    assert client.get("/api/works").json()[0]["id"] == s  # 최근 바뀐 차례
    g = client.get(f"/api/docs/{d}").json()
    assert g["work"]["stored"] is True and g["work"]["rev"] == 0


def test_edits_survive_restart_with_same_ids(client):
    d = _upload(client)
    _wait(client, d, "import")
    a = _texts(client, d)[3]
    assert client.patch(f"/api/docs/{d}/blocks/{a['id']}", json={"text": a["text"] + "★ 둘째 줄"}).json()["edited"]
    r = client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3}).json()
    new = r["focus"]["id"]
    assert client.patch(f"/api/docs/{d}/blocks/{new}", json={"text": "새 문단 글"}).json()["edited"]
    client.post(f"/api/docs/{d}/format/chars", json={"id": a["id"], "start": 0, "end": 2, "changes": {"bold": "toggle"}})
    before = client.get(f"/api/docs/{d}").json()
    saved = client.get(f"/api/docs/{d}/download").content
    _restart()
    after = client.get(f"/api/docs/{d}").json()  # 메모리에 없음 → 작업 폴더에서 다시 엶
    assert d in server.DOCS
    assert after["blocks"] == before["blocks"]  # 같은 블록 id·글·모양
    for k in ("edited", "kinds", "original", "pristine", "editedCount"):
        assert after[k] == before[k], k
    assert after["undo"] == 0  # 실행 취소 기록은 남기지 않는다(spec_작업 ② §1)
    assert after["work"]["rev"] == before["work"]["rev"] == 4
    assert client.get(f"/api/docs/{d}/download").content == saved
    # 가져오기 검증은 다시 돌지 않고 지난 기록을 보인다
    v = client.get(f"/api/docs/{d}/verify").json()
    assert v["import"]["stored"] == 1 and not v["import"]["running"]
    kinds = [e["kind"] for e in _events(client, d)]
    assert kinds.count("verify") == 1 and kinds.count("reopen") == 1 and kinds.index("reopen") > kinds.index("chars")
    # 다시 연 뒤에도 편집이 쌓이고 한 번 더 다시 켜도 남는다
    client.patch(f"/api/docs/{d}/blocks/{new}", json={"text": "새 문단 글 — 다시 켠 뒤"})
    _restart()
    assert next(p for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["id"] == new)["text"] == "새 문단 글 — 다시 켠 뒤"


def test_revert_after_restart_restores_original_bytes(client):
    """다시 연 작업도 되돌리기 기준이 원본 — 모두 되돌리면 내려받기 = 원본 바이트."""
    d = _upload(client)
    ps = _texts(client, d)
    a, b = ps[2], ps[5]
    for p in (a, b):
        client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★\t탭"})
    _restart()
    r = client.post(f"/api/docs/{d}/blocks/{a['id']}/revert").json()
    assert r["restored"] is True and r["editedCount"] == 1
    r = client.patch(f"/api/docs/{d}/blocks/{b['id']}", json={"text": b["text"]}).json()
    assert r["restored"] is True and r["editedCount"] == 0 and r["pristine"] is True
    got = client.get(f"/api/docs/{d}/download")
    assert got.content == HWPX.read_bytes() and got.headers["x-same-as-original"] == "1"
    ev = _events(client, d)
    assert [e["kind"] for e in ev if e["kind"] in ("text", "revert")] == ["text", "text", "revert", "text"]
    rv = next(e for e in ev if e["kind"] == "revert")
    assert rv["id"] == a["id"] and rv["before"] == a["text"] + "★\t탭" and rv["after"] == a["text"] and rv["restored"] is True


def test_verify_records_and_download_trace(client):
    d = _upload(client)
    _wait(client, d, "import")
    assert [(r["n"], r["kind"], r["status"]) for r in works.runs(d)] == [(1, "import", "ok")]
    rec = client.get(f"/api/works/{d}/runs/1").json()
    assert {s["key"] for s in rec["job"]["steps"]} >= {"package", "xml", "model"}
    p = _texts(client, d)[1]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 수정"})
    client.post(f"/api/docs/{d}/verify", json={"kind": "edit", "revision": 7})
    _wait(client, d, "edit")
    run = works.runs(d)[-1]
    assert run["n"] == 2 and run["kind"] == "edit" and run["revision"] == 7 and run["rev"] == 1
    out = works.folder(d) / "outputs" / f"{run['outputSha'][:16]}.hwpx"
    assert out.exists() and HwpxDoc(out.read_bytes()).blocks()
    w = works.work(d)
    assert set(w["verify"]) == {"import", "edit"} and w["verify"]["edit"]["n"] == 2
    # 검증한 파일을 내려받으면 verified, 더 고친 뒤면 아님
    got = client.get(f"/api/docs/{d}/download").content
    assert works.sha256(got) == run["outputSha"]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 수정 둘"})
    client.get(f"/api/docs/{d}/download")
    dl = [e for e in _events(client, d) if e["kind"] == "download"]
    assert [e["verified"] for e in dl] == [True, False] and dl[0]["same"] is False
    done = next(e for e in _events(client, d) if e["kind"] == "verified" and e["verify"] == "edit")
    assert done["n"] == 2 and done["steps"] and done["outputSha"] == run["outputSha"]
    # 다시 켜면 마지막 출력파일 검증이 그대로(revision·rev 로 화면이 「검증 뒤 바뀜」 판정)
    _restart()
    v = client.get(f"/api/docs/{d}/verify").json()
    assert v["edit"]["stored"] == 2 and v["edit"]["revision"] == 7 and v["edit"]["rev"] == 1 and v["rev"] == 2


def test_rejected_and_undo_are_logged(client, monkeypatch):
    d = _upload(client)
    client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3})
    client.post(f"/api/docs/{d}/undo")
    real = HwpxDoc.split_para

    def broken(self, block_id, offset):
        new = real(self, block_id, offset)
        etree.SubElement(self._ids[new], f"{{{HP}}}t")  # hp:p 바로 아래 hp:t — OWPML 위반
        return new
    monkeypatch.setattr(HwpxDoc, "split_para", broken)
    assert client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 2}).status_code == 422
    ev = [e for e in _events(client, d) if e["kind"] in ("split", "undo", "rejected")]
    assert [e["kind"] for e in ev] == ["split", "undo", "rejected"]
    assert ev[0]["req"] == {"id": "p7", "offset": 3} and ev[0]["owpml"]["status"] in ("ok", "warn") and ev[1]["rev"] == 2
    assert ev[2]["op"] == "split" and ev[2]["rev"] == 2 and ev[2]["summary"]


def test_delete_work(client):
    d = _upload(client)
    _wait(client, d, "import")
    assert client.delete(f"/api/works/{d}").json() == {"ok": True}
    assert not works.folder(d).exists()
    assert client.get(f"/api/docs/{d}").status_code == 404
    assert client.get("/api/works").json() == []
    assert client.delete(f"/api/works/{d}").status_code == 404


def test_mismatched_state_opens_original_and_sets_aside(client):
    d = _upload(client)
    _wait(client, d, "import")
    p = _texts(client, d)[2]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"})
    _restart()
    folder = works.folder(d)
    for name in ("state.json", "state.json.prev"):   # 지금 저장본 · 직전 저장본이 모두 어긋남(직전만 맞으면 그것으로 연다 — 아래 시험)
        if (folder / name).is_file():
            st = json.loads((folder / name).read_text("utf-8"))
            st["rev"] = 99  # 묶음(doc.pkl)과 차례가 어긋남 — 쓰다 꺼진 것처럼
            (folder / name).write_text(json.dumps(st), "utf-8")
    g = client.get(f"/api/docs/{d}").json()
    assert g["edited"] == [] and g["pristine"] is True and g["work"]["rev"] == 0
    assert list(folder.glob("state.json.broken-*")) and list(folder.glob("current.hwpx.broken-*"))
    assert _events(client, d)[-1]["kind"] == "reopen" and _events(client, d)[-1]["ok"] is False


def test_docx_edits_survive_restart(client):
    d = _upload(client, DOCX)
    _wait(client, d, "import")
    p = _texts(client, d)[2]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + " 고침"})
    client.post(f"/api/docs/{d}/format/para", json={"ids": [p["id"]], "changes": {"align": "center"}})
    before = client.get(f"/api/docs/{d}").json()
    saved = client.get(f"/api/docs/{d}/download").content
    _restart()
    after = client.get(f"/api/docs/{d}").json()
    assert after["blocks"] == before["blocks"] and after["kinds"] == before["kinds"] and p["id"] in after["kinds"]
    assert client.get(f"/api/docs/{d}/download").content == saved
    assert client.post(f"/api/docs/{d}/blocks/{p['id']}/revert").json()["restored"] is True
    assert client.get(f"/api/docs/{d}/download").content == DOCX.read_bytes()


def test_evicted_document_reopens_with_edits(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_DOCS", 2)
    d = _upload(client)
    p = _texts(client, d)[1]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"})
    _upload(client)
    _upload(client)  # d 가 메모리에서 비워짐 — 비우기 전에 작업 폴더에 씀
    assert d not in server.DOCS
    assert client.get(f"/api/docs/{d}").json()["edited"] == [p["id"]]


def test_work_files(client):
    d = _upload(client)
    p = _texts(client, d)[1]
    assert client.get(f"/api/works/{d}/file/current").content == HWPX.read_bytes()  # 아직 편집 상태를 안 씀 → 원본
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"})
    server._persist_all()
    cur = client.get(f"/api/works/{d}/file/current")
    assert cur.content == client.get(f"/api/docs/{d}/download").content and "_%EC%88%98%EC%A0%95" in cur.headers["content-disposition"]
    assert client.get(f"/api/works/{d}/file/original").content == HWPX.read_bytes()
    assert client.get(f"/api/works/{d}/file/other").status_code == 404
    assert client.get("/api/works/../../x/log").status_code == 404


def test_works_off_keeps_memory_only(client, monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    d = _upload(client)
    assert client.get("/api/works").json() == [] and works.folder(d) is None
    assert client.get(f"/api/docs/{d}").status_code == 200
    server.DOCS.clear()
    assert client.get(f"/api/docs/{d}").status_code == 404


def test_pdf_paths_and_mapping_survive_restart(client, monkeypatch):
    """PDF 단계가 돈 작업(렌더 경로 = Path)도 상태를 쓰고, 다시 열면 매핑·PDF 쪽 그림·수정본 매핑이 그대로(e2e 에서 찾은 Path 직렬화 실패)."""
    from tests.test_server import _fake_pdf
    from app import pdf_render
    monkeypatch.setattr(pdf_render, "available", lambda fmt="hwpx": True)
    monkeypatch.setattr(pdf_render, "export_pdf", _fake_pdf)
    d = _upload(client)
    v = _wait(client, d, "import")
    assert v["mapping"]["ratio"] >= 0.9
    p = _texts(client, d)[-1]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "추가글"})
    client.post(f"/api/docs/{d}/verify", json={"kind": "edit"})
    before = _wait(client, d, "edit")
    server._persist_all()
    assert server.DOCS[d].persist_error is None
    assert client.get(f"/api/docs/{d}").json()["persistError"] is None
    _restart()
    after = client.get(f"/api/docs/{d}/verify").json()
    assert after["mapping"] == json.loads(json.dumps(before["mapping"])) and after["mappingEdited"] == json.loads(json.dumps(before["mappingEdited"]))
    assert after["pdfs"] == before["pdfs"] == ["edited", "original", "rebuilt"]
    assert after["edit"]["stored"] == 2 and after["edit"]["status"] == before["edit"]["status"]
    page = next(s for s in after["edit"]["steps"] if s["key"] == "epages")["expected"][0]
    assert client.get(f"/api/docs/{d}/pdf/original/{page}.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/docs/{d}/diff/edited/{page}.png").status_code == 200


def test_unserializable_state_writes_nothing(client, monkeypatch):
    """상태에 못 쓰는 값이 있으면 파일을 하나도 안 바꾸고(어긋난 셋이 남지 않게) 세션에 실패를 단다 — 화면 상단이 실패를 보임."""
    d = _upload(client)
    p = _texts(client, d)[1]
    server.DOCS[d].mapping = {"pages": {"x": object()}}  # 편집 전에 — 배경 저장이 먼저 돌아도 같은 실패(응답에는 안 나가는 값)
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"})
    server._persist_all()
    folder = works.folder(d)
    assert not (folder / "current.hwpx").exists() and not (folder / "state.json").exists()
    r = client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★★"}).json()
    assert r["persistError"] and "TypeError" in r["persistError"]
    server.DOCS[d].mapping = None
    server._persist_all()
    assert (folder / "state.json").exists()
    assert client.get(f"/api/docs/{d}").json()["persistError"] is None


def test_task_guess_and_save(client):
    """작업 종류·첨부 파일·할 일·과제(② §10): 안 골랐으면 문서에서 짐작(국가R&D 양식 → 연구개발과제·사업계획서 — 짐작도 적어 둠), 고르면 work.json 에 저장, 모르는 값 400.
    같은 프로젝트의 문서라도 TASK는 따로 고른다(프로젝트 아래 여러 TASK·라운드)."""
    none = {"kind": "", "file": "", "job": "", "project": ""}
    d = _upload(client)  # 기술수요조사서 — 국가R&D 양식이 아님
    assert client.get(f"/api/docs/{d}").json()["work"]["task"] == none and "task" not in works.work(d)
    t = {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "  선박  과제 "}
    saved = {**t, "project": "선박 과제"}  # 이름은 앞뒤를 떼고 빈칸을 하나로
    assert client.put(f"/api/works/{d}/task", json=t).json() == {"task": saved, "division": "none"}   # division = 프로젝트에 들어감 알림의 근거(② §10·§19)
    assert client.get(f"/api/docs/{d}").json()["work"]["task"] == saved and client.get("/api/works").json()[0]["task"] == saved
    assert client.put(f"/api/works/{d}/task", json={"kind": "x"}).status_code == 400
    assert client.put(f"/api/works/{d}/task", json={"project": 3}).status_code == 400
    assert client.put("/api/works/000000000000/task", json=t).status_code == 404
    p = _upload(client, SAMPLES / "연구개발계획서_양식.hwpx")
    g = {"kind": "rnd", "file": "plan", "job": "", "project": ""}
    assert client.get(f"/api/docs/{p}").json()["work"]["task"] == g and works.work(p)["task"] == g
    joined = client.put(f"/api/works/{p}/task", json={**g, "project": "선박 과제"}).json()["task"]
    assert joined == {**g, "project": "선박 과제"}  # 프로젝트에 들어와도 다른 TASK를 강제로 따르지 않는다.
    client.put(f"/api/works/{p}/task", json={**joined, "job": "plan_merge"})
    assert works.work(d)["task"] == saved  # 같은 프로젝트의 다른 TASK는 그대로.
    client.put(f"/api/works/{p}/task", json={**joined, "job": "report_merge", "project": ""})
    assert works.work(d)["task"]["job"] == "plan_to_report" and works.work(p)["task"] == {**g, "job": "report_merge"}


def test_target_doc_shown_name(client):
    """목적 문서의 보이는 이름(② §10): 과제에 묶인 목적 문서(이관의 연차보고서 · 취합의 취합본)는 「<올린 이름>_<과제 이름>.<확장자>」 — 목록·문서·내려받는 파일 이름에.
    저장된 이름은 올린 그대로라 같은 파일을 다시 올리면 그 작업을 이어 연다. 원본 문서·과제 밖 문서·올린 원본 받기는 그대로."""
    name = HWPX.name
    stem = name[:-len(".hwpx")]
    assert works.shown_name(name, None) == name and works.shown_name(name, {"job": "plan_to_report", "file": "report", "project": ""}) == name
    assert works.shown_name(name, {"job": "plan_to_report", "file": "plan", "project": "과제"}) == name   # 이관의 원본 문서(사업계획서)
    assert works.shown_name(name, {"job": "plan_merge", "file": "part", "project": "과제"}) == name       # 취합의 원본 문서(기관 문서)
    assert works.shown_name(name, {"job": "plan_merge", "file": "plan", "project": "과제"}) == f"{stem}_과제.hwpx"   # 취합본
    assert works.shown_name(f"{stem}_과제.hwpx", {"job": "plan_merge", "file": "plan", "project": "과제"}) == f"{stem}_과제.hwpx"   # 두 번 안 붙임
    d = _upload(client)
    t = {"kind": "rnd", "file": "report", "job": "plan_to_report", "project": "선박 과제 A/1"}
    client.put(f"/api/works/{d}/task", json=t)
    shown = f"{stem}_선박 과제 A_1.hwpx"   # 파일 이름에 못 쓰는 글자는 _
    from urllib.parse import quote
    assert client.get("/api/works").json()[0]["name"] == shown and client.get(f"/api/docs/{d}").json()["name"] == shown
    assert client.get(f"/api/works/{d}/log").json()["work"]["name"] == shown
    assert works.work(d)["name"] == name and server.DOCS[d].name == name   # 저장된 이름은 올린 그대로
    assert quote(shown) in client.get(f"/api/docs/{d}/download").headers["content-disposition"]   # 안 고친 문서도 보이는 이름으로
    p = _texts(client, d)[1]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"})
    server._persist_all()
    edited = quote(f"{stem}_선박 과제 A_1_수정.hwpx")
    assert edited in client.get(f"/api/docs/{d}/download").headers["content-disposition"]
    assert edited in client.get(f"/api/works/{d}/file/current").headers["content-disposition"]
    orig = client.get(f"/api/works/{d}/file/original").headers["content-disposition"]
    assert quote(name) in orig and quote("선박") not in orig   # 올린 원본은 올린 이름 그대로
    again = client.post("/api/docs", files={"file": (name, HWPX.read_bytes())}).json()
    assert again["reused"] and again["docId"] == d   # 같은 파일 이어 열기는 올린 이름으로 견준다
    client.put(f"/api/works/{d}/task", json={**t, "project": ""})
    assert client.get("/api/works").json()[0]["name"] == name and client.get(f"/api/docs/{d}").json()["name"] == name   # 과제에서 나오면 올린 이름


def test_frame_shown_name(client):
    """프레임 이름(② §10 「프레임 이름」 — 2026-11-14 사용자 "프로젝트 구성 반영이 완료 하면 사업계획서_{프로젝트이름}_프레임 .. 이라고 파일명을 저장하도록"):
    양식 맞추기 TASK 의 맞추는 문서에 프로젝트 구성을 반영한 기록이 있으면 보이는 이름 = 「<첨부 파일 종류>_<프로젝트 이름>_프레임.<확장자>」 — 목록·문서·내려받는 이름에(「_수정」 꼬리 없음).
    저장된 이름·올린 원본 받기는 그대로, 반영 기록이 없어지면(실행 취소) 올린 이름. 닫힌 작업은 work.json 의 framed 를 본다(옛 작업은 다시 열 때 맞춤 — 바뀐 때는 그대로).
    계획·반영 끝점을 거친 확인은 test_divisions.py::test_apply_names_the_frame."""
    from urllib.parse import quote
    name = HWPX.name
    stem = name[:-len(".hwpx")]
    fit = {"job": "plan_fit", "file": "plan", "project": "데이터플랫폼"}
    frame = "사업계획서_데이터플랫폼_프레임.hwpx"
    assert works.shown_name(name, fit) == name and works.frame_stem(fit, False) is None            # 반영 전 — 올린 이름
    assert works.shown_name(name, fit, framed=True) == frame and works.frame_stem(fit, True) == frame[:-5]
    assert works.shown_name(name, {"job": "report_fit", "file": "report", "project": "A/1"}, framed=True) == "연차보고서_A_1_프레임.hwpx"   # 파일 이름에 못 쓰는 글자는 _
    assert works.shown_name(name, fit, "1차 제출", framed=True) == "사업계획서_데이터플랫폼_프레임(1차 제출).hwpx"   # 별칭은 그 뒤에
    assert works.shown_name(name, {**fit, "project": ""}, framed=True) == name       # 프로젝트 이름 없음
    assert works.shown_name(name, {**fit, "file": "report"}, framed=True) == name    # 그 TASK 가 맞추는 문서가 아님
    assert works.shown_name(name, {"job": "plan_merge", "file": "plan", "project": "과제"}, framed=True) == f"{stem}_과제.hwpx"       # 취합본 · 이관의 연차보고서는 뒤에 내용이 들어간다 — 전의 이름
    assert works.shown_name(name, {"job": "plan_to_report", "file": "report", "project": "과제"}, framed=True) == f"{stem}_과제.hwpx"
    assert set(works.FRAME_FILE.values()) <= set(works.FILE_LABEL) and set(works.FRAME_FILE) <= set(server.TASK["job"])

    d = _upload(client)
    client.put(f"/api/works/{d}/task", json={"kind": "rnd", **fit})
    row = lambda: next(w for w in client.get("/api/works").json() if w["id"] == d)["name"]  # noqa: E731
    assert client.get(f"/api/docs/{d}").json()["name"] == name == row()   # 반영 전
    applied = {"values": {"stages": [1]}, "settingsHash": "h", "profileVersion": 1, "rev": 0, "at": time.time(), "planId": "p", "summary": {}}   # 반영 끝점이 적는 기록의 꼴
    server.DOCS[d].division["applied"] = dict(applied)
    assert client.get(f"/api/docs/{d}").json()["name"] == frame == row()   # 열린 문서는 세션의 지금 상태 — 저장 전에도
    assert client.get(f"/api/works/{d}/log").json()["work"]["name"] == frame
    assert works.work(d)["name"] == name and server.DOCS[d].name == name   # 저장된 이름은 올린 그대로
    p = _texts(client, d)[1]
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"})
    cd = client.get(f"/api/docs/{d}/download").headers["content-disposition"]
    assert quote(frame) in cd and quote("_수정") not in cd   # 고친 문서도 프레임 이름 그대로(올린 파일과 이미 다른 이름)
    server._persist_all()
    assert works.work(d)["framed"] is True
    cur = client.get(f"/api/works/{d}/file/current").headers["content-disposition"]
    assert quote(frame) in cur and quote("_수정") not in cur
    orig = client.get(f"/api/works/{d}/file/original").headers["content-disposition"]
    assert quote(name) in orig and quote("프레임") not in orig   # 올린 원본은 올린 이름
    server.DOCS.clear()
    assert row() == frame   # 닫힌 작업 — work.json 의 framed
    # 이 표시가 생기기 전에 반영한 작업(framed 없음): 닫혀 있으면 올린 이름, 다시 열 때 맞춘다 — 바뀐 때(updated)는 그대로
    works.mark(d, framed=None)
    assert row() == name
    assert client.get(f"/api/docs/{d}").json()["name"] == frame and works.work(d)["framed"] is True
    server.DOCS.clear()
    assert row() == frame
    works.create("0000000000aa", "표시.hwpx", "hwpx", b"mark")   # mark = 표시만 맞춤 — 바뀐 때는 그대로(세션·검증 스레드 없는 작업으로 본다)
    stamp = works.work("0000000000aa")["updated"]
    time.sleep(0.01)
    assert works.mark("0000000000aa", framed=True)["updated"] == stamp and works.work("0000000000aa")["framed"] is True
    again = client.post("/api/docs", files={"file": (name, HWPX.read_bytes())}).json()
    assert again["reused"] and again["docId"] == d   # 같은 파일 이어 열기는 올린 이름으로 견준다
    # 반영 기록이 없어지면(그 반영을 실행 취소) 올린 이름으로
    server.DOCS[d].division["applied"] = None
    assert client.get(f"/api/docs/{d}").json()["name"] == name == row()
    server.DOCS[d].division["applied"] = dict(applied)
    client.put(f"/api/works/{d}/task", json={"kind": "rnd", **fit, "project": ""})
    assert client.get(f"/api/docs/{d}").json()["name"] == name   # 프로젝트에서 나오면 올린 이름


def test_work_alias(client):
    """별칭(② §10 「별칭」 — 2026-11-13 사용자 "별칭을 쓰면 목적문서의 이름 뒤에 (별칭) 이 붙도록"): 보이는 이름의 확장자 앞, 프로젝트 꼬리 뒤에 「(별칭)」 —
    목록·문서·내려받는 이름에. 올린 이름·올린 원본 받기·같은 파일 이어 열기는 그대로. 빈 글 = 지움 · 40자 넘음 400 · 없는 작업 404 · 새 라운드는 이어받음."""
    name = HWPX.name
    stem = name[:-len(".hwpx")]
    target = {"job": "plan_to_report", "file": "report", "project": "과제"}
    assert works.shown_name(name, None, "1차 제출") == f"{stem}(1차 제출).hwpx"
    assert works.shown_name(name, target, "1차 제출") == f"{stem}_과제(1차 제출).hwpx"   # 프로젝트 꼬리 뒤
    assert works.shown_name(name, target, "A/B") == f"{stem}_과제(A_B).hwpx"           # 파일 이름에 못 쓰는 글자는 _
    assert works.shown_name(f"{stem}(1차 제출).hwpx", None, "1차 제출") == f"{stem}(1차 제출).hwpx"   # 두 번 안 붙임
    assert works.shown_name(name, None, "") == name and works.shown_name(name, None, None) == name
    d = _upload(client)
    r = client.put(f"/api/works/{d}/alias", json={"alias": "  1차   제출 "})
    assert r.status_code == 200 and r.json() == {"alias": "1차 제출", "name": f"{stem}(1차 제출).hwpx"}   # 앞뒤를 떼고 빈칸을 하나로
    row = next(w for w in client.get("/api/works").json() if w["id"] == d)
    assert row["name"] == f"{stem}(1차 제출).hwpx" and row["alias"] == "1차 제출" and client.get(f"/api/docs/{d}").json()["name"] == f"{stem}(1차 제출).hwpx"
    client.put(f"/api/works/{d}/task", json={"kind": "rnd", **target})
    shown = f"{stem}_과제(1차 제출).hwpx"
    assert client.get(f"/api/docs/{d}").json()["name"] == shown and works.work(d)["name"] == name
    from urllib.parse import quote
    assert quote(shown) in client.get(f"/api/docs/{d}/download").headers["content-disposition"]
    assert quote("1차") not in client.get(f"/api/works/{d}/file/original").headers["content-disposition"]   # 올린 원본은 올린 이름
    again = client.post("/api/docs", files={"file": (name, HWPX.read_bytes())}).json()
    assert again["reused"] and again["docId"] == d   # 이어 열기는 올린 이름으로 견준다
    assert any(e.get("kind") == "alias" and e.get("new") == "1차 제출" for e in client.get(f"/api/works/{d}/log").json()["events"])
    assert client.put(f"/api/works/{d}/alias", json={"alias": "가" * 41}).status_code == 400
    assert client.put(f"/api/works/{d}/alias", json={"alias": 3}).status_code == 400
    assert client.put("/api/works/000000000000/alias", json={"alias": "x"}).status_code == 404
    rnd = client.post(f"/api/works/{d}/round", json={"source": "original"})
    assert rnd.status_code == 200 and works.work(rnd.json()["docId"]).get("alias") == "1차 제출"   # 새 라운드는 별칭을 이어받는다
    assert client.put(f"/api/works/{d}/alias", json={"alias": ""}).json() == {"alias": "", "name": f"{stem}_과제.hwpx"}   # 빈 글 = 지움


def test_reupload_prefers_the_work_of_the_chosen_task(client):
    """같은 파일로 만든 작업이 여럿일 때 이어 열 작업(② §15 — `POST /api/docs?job=`): 그 TASK 의 작업(가장 최근) → TASK 가 빈 작업(가장 최근) → 그 밖의 가장 최근 작업.
    job 이 없거나 모르는 값이면 전처럼 가장 최근 것, new=1 이면 늘 새 작업. 작업의 task 는 안 바꾼다."""
    def tick():
        time.sleep(0.03)   # 「가장 최근」 은 work.json 의 updated 로 가린다 — 시각이 겹치지 않게

    def again(query=""):
        tick()
        r = client.post("/api/docs" + query, files={"file": (HWPX.name, HWPX.read_bytes())})
        assert r.status_code == 200, r.text
        return r.json()

    def task(d, job, file):
        tick()
        assert client.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": file, "job": job, "project": ""}).status_code == 200

    def new():
        d = _upload(client)
        _wait(client, d, "import")   # 가져오기 검증이 끝나며 work.json 을 고친다(updated) — 그 뒤에 차례를 견준다(test_upload_creates_work 와 같은 경합)
        return d

    move, fit = new(), new()
    task(move, "plan_to_report", "report")
    task(fit, "plan_fit", "plan")
    assert works.find_same(HWPX.name, "hwpx", works.work(move)["sha256"])["id"] == fit   # job 없이 = 가장 최근 것
    for _ in range(2):   # 다시 올려도 같은 작업 — 이어 열면 그 작업이 가장 최근이 되지만 고른 TASK 가 먼저다
        got = again("?job=plan_to_report")
        assert got["reused"] and got["docId"] == move
        got = again("?job=plan_fit")
        assert got["reused"] and got["docId"] == fit
    assert again("?job=plan_to_report")["docId"] == move
    assert again()["docId"] == move                      # job 없음 = 가장 최근 것(방금 이어 연 이관 작업)
    assert again("?job=plan_fit")["docId"] == fit
    assert again("?job=plan_merge")["docId"] == fit      # 그 TASK 의 작업도 빈 작업도 없음 = 그 밖의 가장 최근 것
    assert again("?job=%EC%97%86%EB%8A%94TASK")["docId"] == fit and again("?job=")["docId"] == fit   # 모르는 값·빈 값 = 없는 것으로
    blank = new()   # TASK 를 안 적은 작업(이 예제는 국가R&D 양식이 아니라 짐작도 안 적힌다)
    assert "task" not in works.work(blank)
    assert again("?job=plan_fit")["docId"] == fit        # 빈 작업이 더 최근이어도 그 TASK 의 작업이 먼저
    assert again("?job=plan_merge")["docId"] == blank    # 그 TASK 의 작업이 없으면 TASK 가 빈 작업(더 최근인 양식 맞추기 작업보다 먼저)
    cleared = new()
    task(cleared, "plan_fit", "plan")
    task(cleared, "", "")                                # 적었다 비운 작업(job "")도 빈 작업 — 더 최근 것
    assert again("?job=report_fit")["docId"] == cleared
    newer_fit = new()
    task(newer_fit, "plan_fit", "plan")
    assert again("?job=plan_to_report")["docId"] == move
    assert again("?job=plan_fit")["docId"] == newer_fit  # 그 TASK 의 작업이 여럿이면 가장 최근 것
    fresh = again("?new=1&job=plan_fit")
    assert not fresh["reused"] and fresh["docId"] not in (move, fit, blank, cleared, newer_fit)   # new=1 은 늘 새 작업
    assert works.work(move)["task"]["job"] == "plan_to_report" and works.work(fit)["task"]["job"] == "plan_fit" and "task" not in works.work(blank)


# ---- 저장 한 벌 · 직전 저장본 · 비우기 전 저장 확인(spec_작업 ② §3 「저장 한 벌 · 직전 저장본」) ----------------------------------

def _two_saves(client):
    """편집 둘(★ · ★★)을 하나씩 저장한 작업 → (id, 문단 id, 첫 편집 글, 둘째 편집 글)."""
    d = _upload(client)
    _wait(client, d, "import")
    p = _texts(client, d)[1]
    one, two = p["text"] + "★", p["text"] + "★★"
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": one})
    server._persist_all()
    client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": two})
    return d, p["id"], one, two


def _text_of(client, d, pid):
    return next(p["text"] for p in _paras(client.get(f"/api/docs/{d}").json()["blocks"]) if p["id"] == pid)


def test_broken_current_save_opens_previous_save(client):
    d, pid, one, two = _two_saves(client)
    _restart()
    folder = works.folder(d)
    assert (folder / "state.json.prev").is_file() and (folder / "doc.pkl.prev").is_file()
    st = json.loads((folder / "state.json").read_text("utf-8"))
    st["rev"] = 99   # 지금 저장본만 어긋남
    (folder / "state.json").write_text(json.dumps(st), "utf-8")
    assert _text_of(client, d, pid) == one   # 원본(0판)이 아니라 직전 저장본(1판)
    ev = _events(client, d)[-1]
    assert ev["kind"] == "reopen" and ev["ok"] is True and "직전 저장본" in ev["reason"]
    server._persist_all()   # 곧 다시 써서 지금 저장본을 바로잡는다
    server.DOCS.clear()
    assert _text_of(client, d, pid) == one and "reason" not in _events(client, d)[-1]


def test_failed_write_keeps_last_good_save(client, monkeypatch):
    """둘째 파일(doc.pkl)을 못 쓰면 셋 가운데 아무것도 안 바뀐다 — 다시 열면 마지막 정상 저장본(1판)."""
    d, pid, one, two = _two_saves(client)
    real = works._stage

    def stage(path, data):
        if path.name == "doc.pkl":
            raise OSError(28, "No space left on device")
        return real(path, data)
    monkeypatch.setattr(works, "_stage", stage)
    server._persist_all()
    assert server.DOCS[d].persist_error and "OSError" in server.DOCS[d].persist_error
    assert not [p for p in works.folder(d).iterdir() if ".tmp" in p.name]   # 반쯤 쓴 사본이 남지 않음
    server.DOCS.clear()
    assert _text_of(client, d, pid) == one


def test_crash_between_swaps_opens_a_whole_save(client, monkeypatch):
    """바꿔 넣는 도중 끊김(첫 파일만 새것) — 어긋난 셋이 아니라 맞는 한 벌(직전 저장본)로 연다."""
    d, pid, one, two = _two_saves(client)
    real, n = works._swap, []

    def swap(tmp, path):
        n.append(path.name)
        if len(n) == 2:
            raise OSError("끊김")
        return real(tmp, path)
    monkeypatch.setattr(works, "_swap", swap)
    server._persist_all()
    monkeypatch.setattr(works, "_swap", real)
    server.DOCS.clear()
    assert _text_of(client, d, pid) == one


def test_eviction_keeps_unsaved_document(client, monkeypatch):
    """저장이 실패한 문서는 메모리에서 비우지 않는다 — 200 을 받은 편집이 다른 문서를 연 뒤에도 남는다."""
    monkeypatch.setattr(server, "MAX_DOCS", 2)
    d = _upload(client)
    p = _texts(client, d)[1]
    real = works.save_state

    def fail(wid, *a, **k):
        if wid == d:
            raise OSError(28, "No space left on device")
        return real(wid, *a, **k)
    monkeypatch.setattr(works, "save_state", fail)
    assert client.patch(f"/api/docs/{d}/blocks/{p['id']}", json={"text": p["text"] + "★"}).status_code == 200
    _upload(client)
    third = _upload(client)   # 한도 2 — 비울 차례는 d 지만 저장이 실패해 남고, 저장된 다음 문서를 비운다
    assert d in server.DOCS and third in server.DOCS and len(server.DOCS) == 2
    monkeypatch.setattr(works, "save_state", real)
    _upload(client)   # 이제 저장되니 d 를 비운다
    assert d not in server.DOCS
    assert _text_of(client, d, p["id"]) == p["text"] + "★"


def test_save_goes_to_the_owner_account(client):
    """다른 계정의 요청이 메모리를 비우며 저장해도 그 문서를 연 계정의 뿌리에 쓴다."""
    tok = works.ACCOUNT.set("bob")
    try:
        d = server._open(HWPX.name, HWPX.read_bytes(), new=True)["docId"]
        s = server.DOCS[d]
        s.rev += 1
    finally:
        works.ACCOUNT.reset(tok)
    tok = works.ACCOUNT.set("alice")
    try:
        server._persist_safe(s)
        assert s.persist_error is None and s.saved_rev == s.rev
    finally:
        works.ACCOUNT.reset(tok)
    tok = works.ACCOUNT.set("bob")
    try:
        assert (works.folder(d) / "state.json").is_file()
    finally:
        works.ACCOUNT.reset(tok)
