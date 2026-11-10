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
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
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
    st = json.loads((folder / "state.json").read_text("utf-8"))
    st["rev"] = 99  # 묶음(doc.pkl)과 차례가 어긋남 — 쓰다 꺼진 것처럼
    (folder / "state.json").write_text(json.dumps(st), "utf-8")
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
    """상태에 못 쓰는 값이 있으면 파일을 하나도 안 바꾸고(어긋난 셋이 남지 않게) 세션에 실패를 단다 — 화면이 「자동 저장」 대신 실패를 보임."""
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
