"""헤딩 추출 실행 저장(5b 검증) — S3-saverun · S3-corruptgz · S3-runmeta · S3-provenance(heading_runs 쪽).

LLM 은 늘 끈다(NFM_LLM_BACKEND=off) — LLM 이 필요한 곳은 가짜 llm.ask_all. 규칙·지침 저장소는 시험마다 임시 폴더(NFM_HEADINGS),
작업 폴더는 conftest 의 NFM_WORKS(시험마다 임시). 「다시 켬」 = server.DOCS 에서 비움 → 다음 요청이 작업 폴더에서 다시 연다."""
import gzip
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, llm, server, works

ROOT = Path(__file__).parents[1]
SMALL = ROOT / "samples" / "기술수요조사서.hwpx"
RND = ROOT / "samples" / "연구개발계획서_양식.hwpx"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    """규칙·지침 저장소는 시험마다 빈 임시 폴더, LLM 은 끔, 메모리 저장소(저장 끔일 때)도 비움."""
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture
def c():
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)  # 처리 못 한 예외는 500 으로 보이게
    server.DOCS.clear()


def _upload(c, path):
    r = c.post("/api/docs", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _open_ready(c, path):
    """올리고 가져오기 검증이 끝날 때까지 — 뒤 스레드가 세션을 건드리지 않게."""
    d = _upload(c, path)
    end = time.time() + 60
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/verify").json()
        if "import" in v and not v["import"]["running"]:
            return d
        time.sleep(0.05)
    raise AssertionError("가져오기 검증이 끝나지 않음")


def _wait_heads(c, d, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        v = c.get(f"/api/docs/{d}/headings").json()
        if v["job"] and v["job"]["status"] != "running":
            return v
        time.sleep(0.05)
    raise AssertionError("헤딩 추출이 끝나지 않음")


def _run(c, d, stage, use_llm=False):
    assert c.post(f"/api/docs/{d}/headings", json={"stage": stage, "llm": use_llm}).status_code == 202
    v = _wait_heads(c, d)
    assert v["job"]["status"] == "done", v["job"]
    return v


def _hd(d):
    return works.folder(d) / "headings"


def _dirs(d):
    return sorted(int(p.name) for p in _hd(d).iterdir() if p.is_dir())


def _gz(p):
    return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))


def _res(data=None, error=None):
    return {"data": data, "backend": "fake", "model": "fake", "ms": 0, "costUsd": 0.0, "error": error}


# ---- S3-saverun: 실행 번호는 겹치지 않는다 · 지운 작업·밀려난 세션은 쓰지 않는다 ---------------------------------------------

def test_run_numbers_unique_after_evict_and_reopen(c):
    d = _open_ready(c, SMALL)
    a = server.DOCS[d]
    assert heading_runs.run_sync(a, 1, False).run == 1
    server.DOCS.pop(d)  # = _admit 이 A 를 비움 — A 의 헤딩 작업은 계속 돈다
    b = server._sess(d)  # 다시 연 세션 B(A 의 작업이 안 보임)
    assert b is not a
    nb = heading_runs.run_sync(b, 1, False).run
    at_b = heading_runs.state(b)["runs"][-1]["at"]
    na = heading_runs.run_sync(a, 1, False).run  # A 가 늦게 끝남
    assert nb == 2 and na != nb  # 고치기 전: 둘 다 2(B 의 실행 2 를 A 가 덮음)
    assert _dirs(d) == [1, 2]  # 밀려난 A 는 작업 폴더에 쓰지 않는다
    assert json.loads((_hd(d) / "2" / "run.json").read_text("utf-8"))["at"] == at_b
    assert json.loads((_hd(d) / "current.json").read_text("utf-8")) == {"stage1": 2}
    assert heading_runs.run_sync(b, 1, False).run == 3 and _dirs(d) == [1, 2, 3]


def test_run_number_counts_dirs_when_current_json_missing(c):
    d = _open_ready(c, SMALL)
    heading_runs.run_sync(server.DOCS[d], 1, False)
    (_hd(d) / "current.json").unlink()  # current.json 쓰기 실패(디스크 가득) 뒤 다시 엶
    server.DOCS.pop(d)
    b = server._sess(d)
    assert [r["n"] for r in heading_runs.state(b)["runs"]] == [1]  # 실행 목록은 current.json 없이도 읽음
    assert heading_runs.run_sync(b, 1, False).run == 2  # 고치기 전: 1(실행 1 을 덮음)
    assert _dirs(d) == [1, 2]


def test_late_run_does_not_recreate_deleted_work(c, monkeypatch):
    d = _open_ready(c, SMALL)
    s = server.DOCS[d]
    f = works.folder(d)
    heading_runs.state(s)  # 지난 결과는 미리 읽고 — 저장할 때만 끼운다
    real = heading_runs._dir

    def dir_then_deleted(sess):  # 작업 지우기가 _dir 확인 바로 뒤에 옴
        got = real(sess)
        assert works.delete(d)
        return got
    monkeypatch.setattr(heading_runs, "_dir", dir_then_deleted)
    job = heading_runs.run_sync(s, 1, False)
    assert job.run == 1 and heading_runs.state(s)["stage1"]["meta"]["run"] == 1  # 결과는 메모리에
    assert not f.exists()  # 고치기 전: works/<id>/headings/1/… 만 있는(work.json 없는) 고아 폴더


def test_start_check_and_set_is_atomic(c, monkeypatch):
    """두 요청이 거의 같이 와도 하나만 시작(나머지는 Busy → 409)."""
    d = _open_ready(c, SMALL)
    s = server.DOCS[d]
    heading_runs.state(s)
    go = threading.Event()

    class SlowJob(heading_runs.Job):  # 「돌고 있나」 확인과 자리 잡기 사이를 넓힌다
        def __init__(self, *a):
            time.sleep(0.3)
            super().__init__(*a)
    monkeypatch.setattr(heading_runs, "Job", SlowJob)
    monkeypatch.setattr(heading_runs, "run_stage1", lambda sess, job, use_llm: go.wait(10) and 0)
    out = []

    def go_start():
        try:
            out.append(heading_runs.start(s, 1, False))
        except heading_runs.Busy as e:
            out.append(e)
    ts = [threading.Thread(target=go_start) for _ in range(2)]
    try:
        ts[0].start()
        time.sleep(0.05)
        ts[1].start()
        for t in ts:
            t.join(5)
    finally:
        go.set()
    assert sorted(type(x).__name__ for x in out) == ["Busy", "SlowJob"], out  # 고치기 전: 둘 다 시작
    _wait_heads(c, d)


# ---- S3-corruptgz: 깨진 실행 파일은 그것만 빠진다(500 아님) · 성한 실행 번호를 다시 쓰지 않는다 -----------------------------------

@pytest.mark.parametrize("damage", ["truncate", "flip"])
def test_reopen_with_damaged_run_gz(c, damage):
    d = _upload(c, SMALL)
    _run(c, d, 1)
    _run(c, d, 2)
    hd = _hd(d)
    run1 = [(hd / "1" / n).read_bytes() for n in ("run.json", "stage1.json.gz")]
    g = hd / "2" / "graph.json.gz"
    data = bytearray(g.read_bytes())
    if damage == "truncate":
        g.write_bytes(bytes(data[: len(data) // 2]))  # EOFError
    else:
        data[len(data) // 2] ^= 0xFF  # zlib.error
        g.write_bytes(bytes(data))
    server.DOCS.clear()  # 서버 다시 시작 → 다시 연다
    r = c.get(f"/api/docs/{d}/headings")
    assert r.status_code == 200, r.text  # 고치기 전: 500, 다음 GET 은 실행 목록 없이 200
    v = r.json()
    assert [x["n"] for x in v["runs"]] == [1, 2] and v["stage1"] is not None and v["stage2"] is None
    assert c.get(f"/api/docs/{d}/headings/graph").status_code == 404
    assert _run(c, d, 1)["job"]["run"] == 3
    assert [(hd / "1" / n).read_bytes() for n in ("run.json", "stage1.json.gz")] == run1  # 성한 실행 1 은 그대로(불변)


def test_reopen_with_corrupt_run_json_keeps_numbering(c):
    d = _upload(c, SMALL)
    _run(c, d, 1)
    _run(c, d, 2)
    hd = _hd(d)
    (hd / "1" / "run.json").write_text("{깨짐", "utf-8")
    s1 = (hd / "1" / "stage1.json.gz").read_bytes()
    server.DOCS.clear()
    v = c.get(f"/api/docs/{d}/headings").json()
    assert [x["n"] for x in v["runs"]] == [2] and v["stage1"]["meta"]["run"] == 1 and v["stage2"] is not None  # 고치기 전: 실행 목록 []
    assert _run(c, d, 1)["job"]["run"] == 3  # 고치기 전: 1(실행 1 을 덮음)
    assert (hd / "1" / "stage1.json.gz").read_bytes() == s1


# ---- S3-runmeta: 실행 번호가 파일에도 — 다시 열어도 meta.run·stage1Run 이 남는다 -------------------------------------------------

def test_run_numbers_survive_reopen(c):
    d = _upload(c, SMALL)
    _run(c, d, 1)
    _run(c, d, 2)
    hd = _hd(d)
    assert _gz(hd / "1" / "stage1.json.gz")["meta"]["run"] == 1  # 실행 번호도 저장
    assert _gz(hd / "2" / "graph.json.gz")["meta"]["run"] == 2
    server.DOCS.clear()
    v = c.get(f"/api/docs/{d}/headings").json()
    assert v["stage1"]["meta"]["run"] == 1 and v["stage2"]["meta"]["run"] == 2 and not v["stage1"]["stale"]
    assert _run(c, d, 2)["job"]["run"] == 3
    assert json.loads((hd / "3" / "run.json").read_text("utf-8"))["stage1Run"] == 1
    assert c.get(f"/api/docs/{d}/headings/graph").json()["meta"]["stage1Run"] == 1


def test_reopen_backfills_run_number_of_older_saves(c):
    """고치기 전에 저장한 결과(meta 에 run 없음) — 다시 열 때 current.json 의 번호를 채운다."""
    d = _upload(c, SMALL)
    _run(c, d, 1)
    p = _hd(d) / "1" / "stage1.json.gz"
    obj = _gz(p)
    obj["meta"].pop("run", None)
    p.write_bytes(gzip.compress(json.dumps(obj, ensure_ascii=False).encode("utf-8")))
    server.DOCS.clear()
    v = c.get(f"/api/docs/{d}/headings").json()
    assert v["stage1"]["meta"]["run"] == 1
    assert _run(c, d, 2)["job"]["run"] == 2
    assert json.loads((_hd(d) / "2" / "run.json").read_text("utf-8"))["stage1Run"] == 1


# ---- S3-provenance(heading_runs 쪽): 시작 때 고정한 지침이 프롬프트·기록에 · rulesVersion = 결과를 뽑은 저장소 ---------------------------

def test_stage2_guide_saved_mid_run_is_not_recorded(c, monkeypatch):
    """§7 — 실행 중 지침을 저장해도 실행 기록(meta.guides·guides.json)은 이 실행이 프롬프트에 쓴 지침."""
    d = _open_ready(c, SMALL)
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)
    old = G.get("graph")["sha1"]

    def ask(jobs):  # 사용자가 LLM 호출 중 「지침」 대화창에서 저장
        G.save("graph", "# 실행 중 고친 지침\n", reason="mid-run")
        return [_res(None, "가짜 실패") for _ in jobs]
    monkeypatch.setattr(llm, "ask_all", ask)
    job = heading_runs.run_sync(s, 2, True)
    g = heading_runs.state(s)["stage2"]
    snap = _gz(_hd(d) / str(job.run) / "guides.json.gz")
    assert G.get("graph")["sha1"] != old and g["guides"]["graph"] == old
    assert g["meta"]["guides"]["graph"] == old  # 고치기 전: 실행 끝의 새 sha1
    assert snap["graph"]["sha1"] == old and "실행 중 고친" not in snap["graph"]["text"]


def test_stage1_rule_change_mid_llm_is_not_recorded(c, monkeypatch):
    """LLM 이 아무것도 저장하지 않으면 다시 추출이 없다 — rulesVersion·tolerance sha1 은 결과를 뽑은 그때 것."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    R.add_rules([{"name": "x", "kind": "plain", "family": "x", "pattern": "ZZZ없는패턴", "scope": "prefix"}], source="user")
    rid, v0 = R.load()["rules"][-1]["id"], R.load()["version"]
    tol0 = G.get("tolerance")["sha1"]

    def ask(jobs):
        R.set_enabled(rid, False, reason="mid-run")
        G.save("tolerance", G.get("tolerance")["text"] + "\n<!-- mid-run -->\n", reason="mid-run")
        return [_res({"items": [], "summary": ""}) for _ in jobs]
    monkeypatch.setattr(llm, "ask_all", ask)
    heading_runs.run_sync(s, 1, True)
    s1 = heading_runs.state(s)["stage1"]
    assert s1["llm"]["saved"] == [] and R.load()["version"] > v0
    assert s1["meta"]["rulesVersion"] == v0  # 고치기 전: 실행 끝의 version
    assert s1["meta"]["guides"]["tolerance"] == tol0


def test_pinned_guides_reach_prompts(c, monkeypatch):
    """프롬프트 = 시작 때 고정한 지침 글(지금 저장소를 다시 읽지 않음) — 1단계 규칙 보강·2단계 A 호출 모두."""
    d = _open_ready(c, RND)
    s = server.DOCS[d]
    real = G.snapshot

    def pinned():
        snap = real()
        for name in ("rules", "graph"):
            snap[name] = {**snap[name], "text": f"# 고정한 {name} 지침 PIN", "sha1": f"pin-{name}"}
        return snap
    monkeypatch.setattr(G, "snapshot", pinned)
    seen = []

    def ask(jobs):
        seen.extend((j["what"].split("#")[0], j["content"]) for j in jobs)
        return [_res(None, "가짜 실패") for _ in jobs]
    monkeypatch.setattr(llm, "ask_all", ask)
    heading_runs.run_sync(s, 1, True)
    heading_runs.run_sync(s, 2, True)
    what = {w for w, _ in seen}
    assert {"heading_rules", "heading_types"} <= what, what
    for w, content in seen:
        name = "rules" if w == "heading_rules" else "graph"
        assert f"# 고정한 {name} 지침 PIN" in content, w  # 고치기 전: 2단계 A 는 저장소의 지침 글
    st = heading_runs.state(s)
    assert st["stage1"]["meta"]["guides"]["rules"] == "pin-rules" and st["stage2"]["meta"]["guides"]["graph"] == "pin-graph"
