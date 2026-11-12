"""확정(spec_작업 ② §8) — 고친 문단을 깃처럼: 확정하면 그 상태가 새 기준(고친 문단 0 · 되돌리기·검증이 확정본 대비), 확정 기록,
버리기, 이전 확정으로 복원(새 확정으로 남김). 「다시 켬」 = 배경 저장을 한 번 돌리고 메모리 문서를 모두 비움."""
import threading
import time
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app import server, works

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


def _wait(c, d, kind="import", base=0, timeout=60):
    """그 기준(base)에서 돈 검증이 끝나고 기록까지 남을 때까지."""
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if kind in v and not v[kind]["running"] and any(r["kind"] == kind and (r.get("base") or 0) == base for r in works.runs(d)):
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


def _doc(c, d):
    r = c.get(f"/api/docs/{d}")
    assert r.status_code == 200, r.text
    return r.json()


def _texts(c, d):
    return [p for p in _paras(_doc(c, d)["blocks"]) if p["text"].strip()]


def _patch(c, d, pid, text):
    r = c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _commit(c, d, message=""):
    r = c.post(f"/api/docs/{d}/commits", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def _restore(c, d, n, discard=False):
    return c.post(f"/api/docs/{d}/commits/{n}/restore", json={"discard": discard})


def _restart():
    server._persist_all()
    server.DOCS.clear()


def _events(c, d):
    return c.get(f"/api/works/{d}/log").json()["events"]


def _edit_some(c, d):
    """글 고침 + 문단 나누기(새 문단) + 글자 모양 — (고친 문단, 새 문단 id)."""
    a = _texts(c, d)[3]
    assert _patch(c, d, a["id"], a["text"] + "★")["edited"]
    new = c.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3}).json()["focus"]["id"]
    _patch(c, d, new, "새 문단 글")
    assert c.post(f"/api/docs/{d}/format/chars", json={"id": a["id"], "start": 0, "end": 2, "changes": {"bold": "toggle"}}).status_code == 200
    return a, new


def test_commit_makes_current_state_the_base(client):
    d = _upload(client)
    _wait(client, d)
    assert client.post(f"/api/docs/{d}/commits", json={}).status_code == 400  # 확정할 변경이 없음
    a, new = _edit_some(client, d)
    before = _doc(client, d)
    assert before["editedCount"] >= 3 and before["undo"] == 2 and before["base"] == 0
    saved = client.get(f"/api/docs/{d}/download").content
    j = _commit(client, d, "  첫   확정 ")
    c = j["commit"]
    assert c["n"] == 1 and c["message"] == "첫 확정" and c["size"] == len(saved)
    assert c["counts"]["total"] == before["editedCount"] and c["counts"]["new"] == 1
    # 고친 문단 0 · 실행 취소 비움 · 편집 차례 그대로 · 저장 바이트 = 기준
    assert j["edited"] == [] and j["editedCount"] == 0 and j["kinds"] == {} and j["pristine"] is True
    assert j["undo"] == 0 and j["base"] == 1 and j["rev"] == before["rev"]
    after = _doc(client, d)
    assert after["blocks"] == before["blocks"]  # 문서 글·블록 id 그대로
    assert after["edited"] == [] and after["original"] == {} and after["base"] == 1
    assert client.get(f"/api/docs/{d}/download").content == saved
    lst = client.get(f"/api/docs/{d}/commits").json()
    assert lst["base"] == 1 and lst["edited"] == 0 and [x["n"] for x in lst["commits"]] == [1, 0]
    assert lst["commits"][-1]["sha256"] == works.sha256(HWPX.read_bytes())
    assert works.commit_bytes(d, 1) == saved and works.head(d) == 1
    w = works.work(d)
    assert w["commits"] == 1 and w["edited"] == 0
    ev = [e for e in _events(client, d) if e["kind"] == "commit"]
    assert len(ev) == 1 and ev[0]["n"] == 1 and ev[0]["message"] == "첫 확정"
    assert client.post(f"/api/docs/{d}/commits", json={}).status_code == 400  # 또 확정할 것은 없다
    assert client.post(f"/api/docs/{d}/undo").status_code == 400  # 확정 앞으로는 실행 취소가 아니라 확정 기록의 복원으로


def test_edits_after_commit_compare_to_the_commit(client):
    d = _upload(client)
    _wait(client, d)
    a, new = _edit_some(client, d)
    committed = a["text"] + "★"
    _commit(client, d)
    r = _patch(client, d, a["id"], committed + "◆")
    assert r["edited"] and r["kinds"] == {a["id"]: "text"} and r["pristine"] is False
    g = _doc(client, d)
    assert g["edited"] == [a["id"]] and g["original"] == {a["id"]: committed}  # 원래 글 = 확정본의 글
    # 되돌리기 = 확정본 문단 XML 로(글자 모양까지) → 저장 바이트가 다시 확정본과 같다
    r = client.post(f"/api/docs/{d}/blocks/{a['id']}/revert").json()
    assert r["text"] == committed and r["restored"] is True and r["edited"] is False and r["pristine"] is True
    assert client.get(f"/api/docs/{d}/download").content == works.commit_bytes(d, 1)
    # 확정 때 새 문단이던 것도 이제 기준의 문단 — 글 고침·되돌리기가 된다(확정본의 블록 id 로 찾음)
    r = _patch(client, d, new, "새 문단 글 — 확정 뒤")
    assert r["kinds"] == {new: "text"}
    r = client.post(f"/api/docs/{d}/blocks/{new}/revert").json()
    assert r["text"] == "새 문단 글" and r["restored"] is True and r["pristine"] is True
    # 손으로 확정본 글로 되돌려도 원본 XML 복원
    _patch(client, d, a["id"], committed + "◆")
    assert _patch(client, d, a["id"], committed)["pristine"] is True


def test_commit_survives_restart(client):
    d = _upload(client)
    _wait(client, d)
    a, new = _edit_some(client, d)
    _commit(client, d, "확정 하나")
    _wait(client, d, base=1)  # 새 기준의 가져오기 검증
    _patch(client, d, a["id"], a["text"] + "★ 확정 뒤")
    newer = client.post(f"/api/docs/{d}/split", json={"id": new, "offset": 2}).json()["focus"]["id"]
    before = _doc(client, d)
    saved = client.get(f"/api/docs/{d}/download").content
    key = server.DOCS[d].doc_key
    assert key == works.sha256(HWPX.read_bytes())  # 문서 키 = 올린 원본(확정해도 그대로)
    _restart()
    after = _doc(client, d)
    assert after["blocks"] == before["blocks"] and after["base"] == 1
    for k in ("edited", "kinds", "original", "pristine", "editedCount"):
        assert after[k] == before[k], k
    assert set(after["edited"]) >= {a["id"], newer}
    assert client.get(f"/api/docs/{d}/download").content == saved
    assert server.DOCS[d].doc_key == key
    v = client.get(f"/api/docs/{d}/verify").json()  # 지금 기준(확정 1)에서 돈 가져오기 검증 기록을 보인다 — 다시 돌지 않음
    assert not v["import"]["running"] and works.run(d, v["import"]["stored"])["base"] == 1
    r = client.post(f"/api/docs/{d}/blocks/{a['id']}/revert").json()  # 다시 연 뒤에도 되돌리기 = 확정본
    assert r["text"] == a["text"] + "★" and r["restored"] is True
    # 고친 것 없이 확정만 한 상태로 다시 켜도 기준이 이어진다
    _commit(client, d, "둘")
    _restart()
    g = _doc(client, d)
    assert g["base"] == 2 and g["edited"] == [] and g["pristine"] is True
    assert [x["n"] for x in client.get(f"/api/docs/{d}/commits").json()["commits"]] == [2, 1, 0]


def test_discard_and_restore(client):
    d = _upload(client)
    _wait(client, d)
    orig = _doc(client, d)
    a, new = _edit_some(client, d)
    _commit(client, d, "하나")
    one = _doc(client, d)
    b = _texts(client, d)[5]
    _patch(client, d, b["id"], b["text"] + "◆")
    client.post(f"/api/docs/{d}/split", json={"id": new, "offset": 2})
    _commit(client, d, "둘")
    two = _doc(client, d)
    assert _restore(client, d, 2).status_code == 400  # 이미 그 확정 상태
    # 버리기: 확정하지 않은 변경만 버림 — 확정은 안 생기고 편집 차례는 오른다
    _patch(client, d, a["id"], "버릴 글")
    client.post(f"/api/docs/{d}/split", json={"id": b["id"], "offset": 1})
    assert _restore(client, d, 2).status_code == 409  # discard 없이는 거절
    assert _restore(client, d, 1).status_code == 409
    r = _restore(client, d, 2, discard=True)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["commit"] is None and g["blocks"] == two["blocks"] and g["edited"] == [] and g["base"] == 2 and g["pristine"] is True
    assert g["rev"] > two["rev"] and g["undo"] == 0
    assert [x["n"] for x in client.get(f"/api/docs/{d}/commits").json()["commits"]] == [2, 1, 0]
    # 이전 확정으로 복원 = 새 확정으로 남는다(기록은 한 줄로만 자람, 파일은 같은 바이트)
    g = _restore(client, d, 1).json()
    assert g["commit"]["n"] == 3 and g["commit"]["restoreOf"] == 1 and g["base"] == 3
    assert g["blocks"] == one["blocks"] and g["edited"] == []
    assert works.commit(d, 3)["sha256"] == works.commit(d, 1)["sha256"]
    # 올린 원본으로
    g = _restore(client, d, 0).json()
    assert g["commit"]["n"] == 4 and g["commit"]["restoreOf"] == 0 and g["blocks"] == orig["blocks"]
    assert client.get(f"/api/docs/{d}/download").content == HWPX.read_bytes()
    # 되돌린 뒤 새 문단은 옛 id 를 다시 쓰지 않는다(번호표를 줄이지 않음)
    used = {p["id"] for p in _paras(two["blocks"])}
    fresh = client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3}).json()["focus"]["id"]
    assert fresh not in used
    # 다시 앞으로(확정 2) — 그때의 블록 id 그대로
    g = _restore(client, d, 2, discard=True).json()
    assert g["commit"]["n"] == 5 and g["blocks"] == two["blocks"]
    assert [x["n"] for x in client.get(f"/api/docs/{d}/commits").json()["commits"]] == [5, 4, 3, 2, 1, 0]
    kinds = [e["kind"] for e in _events(client, d)]
    assert kinds.count("commit") == 2 and kinds.count("restore") == 3 and kinds.count("discard") == 1
    assert _restore(client, d, 9).status_code == 404
    # 복원한 상태도 다시 켠 뒤 이어진다
    _restart()
    g = _doc(client, d)
    assert g["base"] == 5 and g["blocks"] == two["blocks"]


def test_verify_uses_the_new_base(client):
    d = _upload(client)
    _wait(client, d)
    a, new = _edit_some(client, d)
    _commit(client, d)
    v = _wait(client, d, base=1)
    steps = {s["key"]: s["status"] for s in v["import"]["steps"]}
    assert steps["package"] == "ok" and steps["model"] == "ok"  # 확정본도 그대로 저장하면 같은 바이트 · 블록 id 가 맞음
    assert "edit" not in v  # 지난 출력파일 검증 결과는 내린다
    assert [(r["kind"], r["base"]) for r in works.runs(d)] == [("import", 0), ("import", 1)]
    # 출력파일 검증 = 확정본 대비 — 확정 뒤 고친 문단만 달라야 한다
    _patch(client, d, a["id"], a["text"] + "★ 더")
    assert client.post(f"/api/docs/{d}/verify", json={"kind": "edit"}).status_code == 200
    v = _wait(client, d, "edit", base=1)
    pk = next(s for s in v["edit"]["steps"] if s["key"] == "epackage")
    assert pk["status"] == "ok" and pk["extra"] == [] and pk["missing"] == [], pk


def test_running_verify_does_not_write_into_the_new_base(client):
    d = _upload(client)
    _wait(client, d)
    s = server.DOCS[d]
    gate, done = threading.Event(), threading.Event()

    def slow(sess, job):  # 옛 기준에서 돌던 검증 — 확정 뒤에 결과를 쓴다
        try:
            gate.wait(10)
            sess.mapping = {"pages": {}, "stale": True}
            sess.pdf["original"] = "old.pdf"
            assert sess.mapping["stale"] and sess.base_n == 0  # 자기 것은 계속 읽힌다
        finally:
            job.finished = time.time()
            done.set()
    server._start(s, "import", slow)
    a = _texts(client, d)[3]
    _patch(client, d, a["id"], a["text"] + "★")
    _commit(client, d)  # 검증이 도는 중에도 확정된다
    gate.set()
    assert done.wait(10)
    _wait(client, d, base=1)
    assert s.mapping is None and s.pdf == {} and s.base_n == 1
    assert [(r["kind"], r["base"]) for r in works.runs(d)] == [("import", 0), ("import", 1)]  # 끊긴 검증은 기록하지 않음


def test_discard_keeps_the_base_verification(client):
    d = _upload(client)
    _wait(client, d)
    a = _texts(client, d)[3]
    _patch(client, d, a["id"], a["text"] + "★")
    client.post(f"/api/docs/{d}/split", json={"id": "p7", "offset": 3})
    g = _restore(client, d, 0, discard=True).json()
    assert g["commit"] is None and g["base"] == 0 and g["edited"] == [] and g["pristine"] is True and g["undo"] == 0
    assert client.get(f"/api/docs/{d}/download").content == HWPX.read_bytes()
    v = client.get(f"/api/docs/{d}/verify").json()
    assert not v["import"]["running"]
    time.sleep(0.3)
    assert [r["kind"] for r in works.runs(d)] == ["import"]  # 기준이 그대로 — 가져오기 검증(한글 PDF)을 다시 돌리지 않는다
    assert [x["n"] for x in client.get(f"/api/docs/{d}/commits").json()["commits"]] == [0]  # 버리기는 확정을 만들지 않는다
    assert [e["kind"] for e in _events(client, d)].count("discard") == 1


def test_commit_detail_and_file(client):
    d = _upload(client)
    _wait(client, d)
    a, new = _edit_some(client, d)
    saved = client.get(f"/api/docs/{d}/download").content
    _commit(client, d, "내용 보기")
    det = client.get(f"/api/works/{d}/commits/1").json()
    assert det["n"] == 1 and det["more"] == 0
    by = {x["id"]: x for x in det["changes"]}
    assert by[a["id"]]["before"] == a["text"] and by[a["id"]]["after"] == a["text"] + "★"
    assert by[new] == {"id": new, "kind": "new", "before": None, "after": "새 문단 글"}
    assert client.get(f"/api/works/{d}/commits/1?limit=1").json()["more"] == len(det["changes"]) - 1
    r = client.get(f"/api/works/{d}/commits/1/file")
    assert r.content == saved and "_확정1.hwpx" in unquote(r.headers["content-disposition"])
    assert client.get(f"/api/works/{d}/commits/0/file").content == HWPX.read_bytes()
    assert client.get(f"/api/works/{d}/commits/0").json()["message"] == "올린 원본"
    assert client.get(f"/api/works/{d}/commits/7").status_code == 404
    assert client.get(f"/api/works/{d}/commits/7/file").status_code == 404
    # 확정본을 내려받으면 올린 파일과 다른 파일이라 「_수정」 이름
    r = client.get(f"/api/docs/{d}/download")
    assert r.headers["x-same-as-original"] == "1" and "_수정.hwpx" in unquote(r.headers["content-disposition"])


def test_docx_commit(client):
    d = _upload(client, DOCX)
    _wait(client, d)
    a = _texts(client, d)[2]
    _patch(client, d, a["id"], a["text"] + "★")
    before = _doc(client, d)
    j = _commit(client, d, "docx")
    assert j["base"] == 1 and j["editedCount"] == 0 and j["pristine"] is True
    assert _doc(client, d)["blocks"] == before["blocks"]
    _patch(client, d, a["id"], a["text"] + "★◆")
    r = client.post(f"/api/docs/{d}/blocks/{a['id']}/revert").json()
    assert r["text"] == a["text"] + "★" and r["pristine"] is True
    _restart()
    g = _doc(client, d)
    assert g["base"] == 1 and g["blocks"] == before["blocks"] and g["edited"] == []
    assert _restore(client, d, 0).json()["blocks"] != before["blocks"]


def test_reopen_falls_back_when_the_commit_file_is_gone(client):
    d = _upload(client)
    _wait(client, d)
    a = _texts(client, d)[3]
    _patch(client, d, a["id"], a["text"] + "★")
    _commit(client, d)
    _restart()
    works.commit_path(d, 1).unlink()
    g = _doc(client, d)  # 기준 확정 파일이 없음 → 올린 원본으로 열고 기록에 남긴다
    assert g["base"] == 0 and g["edited"] == []
    last = [e for e in _events(client, d) if e["kind"] == "reopen"][-1]
    assert last["ok"] is False and "확정 1" in last["reason"]


def test_no_commits_without_work_storage(client, monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    d = _upload(client)
    a = _texts(client, d)[3]
    _patch(client, d, a["id"], a["text"] + "★")
    assert client.post(f"/api/docs/{d}/commits", json={}).status_code == 400
    assert client.post(f"/api/docs/{d}/commits/0/restore", json={"discard": True}).status_code == 400
    assert client.get(f"/api/docs/{d}/commits").json()["enabled"] is False
