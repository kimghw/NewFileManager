"""사람이 하는 일의 「했음」(spec_워크플로우 ② §18-7 · 고친 규칙 ② §18-12 ⑦ — app/flow_hands.py · app/flow_hands_api.py · app/unit_steps.py hand_ver · hand_done):
목적 문서의 작업 폴더에 줄 key 마다 판(정의 지문 + 줄의 이름 · 글)과 함께 적는다 · 판이 다르면 끝나지 않음 · 화면이 읽은 판이 낡았으면 409 · 취소 · 초기화(forget)."""
import json

import pytest
from fastapi.testclient import TestClient

from app import custom_tasks as C
from app import flow_hands, server, unit_steps, workflow, works

HAND_FLOW = [{"id": "g1", "name": "원본 검토", "steps": [{"unit": "heads", "on": ["source"]}, {"unit": "hand", "on": ["target"], "id": "hand1", "name": "결과 확인", "note": "원본의 판정을 본다", "tool": ""}]},
             {"id": "g2", "name": "넣기", "steps": [{"unit": "link", "on": ["source", "target"]}, {"unit": "plan", "on": ["source", "target"]}, {"unit": "apply", "on": ["source", "target"]}]}]


@pytest.fixture
def client():
    server.DOCS.clear()
    yield TestClient(server.app)


def _put_def(note="원본의 판정을 본다"):
    """사람이 하는 일 줄이 든 v2 정의를 저장소에 바로 적는다(조립 검사는 실행기가 그 줄에서 멈추는 길이 서기 전까지 hand 를 거절한다)."""
    flow = json.loads(json.dumps(HAND_FLOW))
    flow[0]["steps"][1]["note"] = note
    row = {"key": "u_0000beef", "name": "사람 확인을 낀 이관", "desc": "", "source": "plan", "target": "report", "shape": "relay", "v": 2, "flow": flow, "premise": "", "at": 1}
    p = C.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"version": 0, "tasks": []}
    old["tasks"] = [t for t in old["tasks"] if t.get("key") != row["key"]] + [row]
    p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    C._CACHE.update(path=None, mtime=None, data=None)
    return row["key"]


def test_the_registry_has_the_hand_line_and_its_version_follows_the_text():
    key = _put_def()
    t = workflow.task_of(key)
    hand = next(s for g in t["stages"] for s in g["steps"] if s["key"] == "hand1")
    assert hand["name"] == "결과 확인" and hand["on"] == "target" and hand["by"] == ("human",) and "원본의 판정을 본다" in hand["does"]
    v1 = unit_steps.hand_ver(t, "hand1")
    _put_def(note="다른 글")
    assert unit_steps.hand_ver(workflow.task_of(key), "hand1") != v1   # 글을 고치면 판이 바뀐다 — 앞의 「했음」 은 무효


def test_hand_done_is_recorded_per_target_and_version(client):
    import merge_data as M
    key = _put_def()
    up = lambda p: client.post("/api/docs?new=1", files={"file": (p.name, p.read_bytes())}).json()["docId"]  # noqa: E731
    tgt, src = up(M.REPORT_FORM), up(M.PLAN_FORM)
    for wid, file in ((tgt, "report"), (src, "plan")):
        assert client.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": file, "job": key, "project": "사람 확인"}).status_code == 200
    got = client.get(f"/api/works/{src}/flow/hand").json()   # 원본 문서에서 불러도 같은 목적 문서
    assert got["target"] == tgt and [x["key"] for x in got["lines"]] == ["hand1"] and got["lines"][0]["done"] is False
    ver = got["lines"][0]["ver"]
    assert client.post(f"/api/works/{tgt}/flow/hand/hand1", json={"ver": "낡은판"}).status_code == 409
    assert client.post(f"/api/works/{tgt}/flow/hand/hand9", json={"ver": ver}).status_code == 404
    done = client.post(f"/api/works/{tgt}/flow/hand/hand1", json={"ver": ver}).json()["line"]
    assert done["done"] is True and unit_steps.hand_done(tgt, "hand1", ver) and not unit_steps.hand_done(src, "hand1", ver)
    assert flow_hands.read(tgt)["hand1"]["docs"] == [tgt] and (works.folder(tgt) / flow_hands.FILE).is_file()
    _put_def(note="고친 글")   # 글을 고침 — 같은 기록이 남아 있어도 끝나지 않은 것으로
    after = client.get(f"/api/works/{tgt}/flow/hand").json()["lines"][0]
    assert after["done"] is False and after["ver"] != ver and not unit_steps.hand_done(tgt, "hand1", after["ver"])
    client.post(f"/api/works/{tgt}/flow/hand/hand1", json={"ver": after["ver"]})
    assert client.delete(f"/api/works/{tgt}/flow/hand/hand1").json()["line"]["done"] is False and "hand1" not in flow_hands.read(tgt)
    flow_hands.mark(tgt, "hand1", after["ver"])
    flow_hands.forget(tgt)
    assert flow_hands.read(tgt) == {} and not (works.folder(tgt) / flow_hands.FILE).exists()
