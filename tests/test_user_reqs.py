"""사용자 요구사항(spec_워크플로우 ② §18-20) — 저장(대상마다 · 항목 하나가 한 줄) · 끝점(등록부의 대상 · 단계 줄 → 도구) · 저장소 파일 reqs/requirements.json 의 점검.
conftest 가 NFM_REQS 를 시험마다 임시 파일로 돌린다(저장소 파일을 시험이 고치지 않게) — 저장소 파일을 보는 시험만 그 파일을 직접 읽는다."""
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_notes
from app import user_reqs as R
from app import user_reqs_api as A

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import reqs as cli  # noqa: E402  (tools/reqs.py)


def _client():
    app = FastAPI()
    app.include_router(A.router)
    return TestClient(app)


def test_store_keeps_items_by_target_one_line_each():
    assert R.load() == {"version": 0, "items": []} and R.of("tool:relay.heads") == []
    a = R.add({"targets": ["tool:relay.heads", "flow:plan_to_report", "tool:relay.heads"], "said": "  헤딩을 먼저  "})
    assert a["said"] == "헤딩을 먼저" and a["state"] == "open" and a["src"] == "web" and a["targets"] == ["tool:relay.heads", "flow:plan_to_report"] and a["id"].startswith("w") and a["date"]
    b = R.add({"targets": ["common:tables"], "said": "표", "state": "done", "note": "정리", "spec": "spec_테이블매니저 ② §5", "date": "2026-11-19"}, "chat")
    assert b["id"] == "r001" and b["src"] == "chat" and b["date"] == "2026-11-19"   # 대화에서 받은 것 = 차례 번호
    assert R.add({"targets": ["common:tables"], "said": "표 둘"}, "chat")["id"] == "r002"
    assert [it["id"] for it in R.of("tool:relay.heads")] == [a["id"]] and [it["id"] for it in R.of("common:tables")] == ["r001", "r002"]
    assert R.counts() == {"tool:relay.heads": {"n": 1, "open": 1}, "flow:plan_to_report": {"n": 1, "open": 1}, "common:tables": {"n": 2, "open": 1}}
    text = R.path().read_text(encoding="utf-8")
    assert text == R.dumps(R.load()) and len(text.splitlines()) == 3 + 3 + 2 and json.loads(text)["version"] == 3   # 항목 하나가 한 줄(깃 병합 · 손으로 고치기)
    assert R.edit(a["id"], {"state": "done", "note": "반영함"})["state"] == "done" and R.load()["items"][0]["note"] == "반영함" and R.load()["items"][0]["said"] == "헤딩을 먼저"
    assert R.edit("nope", {"state": "done"}) is None and R.remove("nope") is False
    assert R.remove("r001") is True and [it["id"] for it in R.load()["items"]] == [a["id"], "r002"]


@pytest.mark.parametrize("body", [
    {"targets": [], "said": "x"}, {"targets": ["tool:nope.heads"], "said": "x"}, {"targets": ["heads"], "said": "x"}, {"targets": "tool:relay.heads", "said": "x"},
    {"targets": ["flow:plan_fit"], "said": "  "}, {"targets": ["flow:plan_fit"], "said": "x" * (R.SAID_MAX + 1)}, {"targets": ["flow:plan_fit"], "said": "x", "state": "끝"},
    {"targets": ["flow:plan_fit"], "said": "x", "date": "11/21"}, {"targets": ["flow:plan_fit"] * 0 + [f"flow:a{i}" for i in range(R.TARGETS_MAX + 1)], "said": "x"}])
def test_store_refuses_bad_shapes(body):
    with pytest.raises(ValueError):
        R.add(body)
    assert R.load()["items"] == []


def test_broken_file_is_not_silently_emptied():
    """저장소 파일이라 — 깨진 파일을 빈 것으로 읽으면 다음 저장이 요구사항을 모두 지운다. 읽기가 멈춘다(끝점은 503)."""
    R.add({"targets": ["flow:plan_fit"], "said": "남아야 한다"})
    p = R.path()
    good = p.read_text(encoding="utf-8")
    p.write_text(good[:-20], encoding="utf-8")
    with pytest.raises(ValueError):
        R.load()
    c = _client()
    assert c.get("/api/reqs").status_code == 503 and c.post("/api/reqs", json={"targets": ["flow:plan_fit"], "said": "x"}).status_code == 503
    assert p.read_text(encoding="utf-8") == good[:-20]   # 덮어쓰지 않았다
    p.write_text(good, encoding="utf-8")
    assert [it["said"] for it in R.load()["items"]] == ["남아야 한다"]
    # 꼴이 아닌 항목은 읽을 때만 빠진다(파일은 사람이 고친다 — tools/reqs.py check 가 알린다)
    raw = json.loads(good)
    raw["items"].append({"id": "x1", "said": "대상 없음", "targets": []})
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    assert [it["said"] for it in R.load()["items"]] == ["남아야 한다"] and any("꼴이 아닌 항목" in x for x in cli.problems())


def test_api_lists_targets_from_the_registry():
    got = _client().get("/api/reqs").json()
    assert got["items"] == [] and got["counts"] == {} and got["states"] == {"open": "요청", "done": "반영", "hold": "보류"} and got["max"]["said"] == R.SAID_MAX
    t = got["targets"]
    assert t["flow:plan_to_report"]["kind"] == "flow" and t["stage:plan_to_report.review"] == {"kind": "stage", "name": "1단계 문서 검토", "group": t["flow:plan_to_report"]["name"]}
    assert t["common:stage_review"]["kind"] == "stage" and t["common:tables"]["kind"] == "tool" and t["common:tables"]["group"] == "도구"
    tools = agent_notes.tool_map()   # 조립에 놓는 도구 — 「도구에 적어 두는 내용」 · 「도구 이름」 과 같은 단위(틀 + 줄 key)
    assert {k for k in t if k.startswith("tool:")} == {f"tool:{fam}.{unit}" for fam, rows in tools.items() for unit in rows}
    assert t["tool:relay.heads"]["name"] == tools["relay"]["heads"]["name"] and t["tool:relay.heads"]["kind"] == "tool"
    assert all(R.target_ok(k) for k in t), [k for k in t if not R.target_ok(k)]   # 등록부의 키가 모두 저장할 수 있는 꼴이다
    # 단계 줄의 주소 → 그 줄의 도구(그 줄을 눌러도 같은 도구의 요구사항) · 틀이 없는 워크플로우 · 등록부의 도구(COMMON)의 줄은 없다
    s = got["steps"]
    assert s["plan_to_report--review--heads"] == "tool:relay.heads" and s["common-stage_review--heads"] == "tool:relay.heads"
    assert s["plan_merge--map--link"] == "tool:gather.link" and s["plan_fit--heads--adjust"] == "tool:single.adjust"
    assert not [k for k in s if k.startswith(("doc_edit--", "style_copy--", "common-tables--", "common-headings--"))] and set(s.values()) <= set(t)


def test_api_adds_edits_and_removes():
    c = _client()
    assert c.post("/api/reqs", json={"targets": ["tool:relay.nope"], "said": "x"}).status_code == 404   # 등록부에 없는 도구
    assert c.post("/api/reqs", json={"targets": ["flow:plan_fit"], "said": ""}).status_code == 400
    r = c.post("/api/reqs", json={"targets": ["tool:relay.heads", "stage:plan_to_report.review"], "said": "분석 이름을 바꾸자", "date": "2026-11-21"})
    assert r.status_code == 201 and r.json()["src"] == "web" and r.json()["state"] == "open"
    rid = r.json()["id"]
    got = c.get("/api/reqs").json()
    assert got["counts"] == {"tool:relay.heads": {"n": 1, "open": 1}, "stage:plan_to_report.review": {"n": 1, "open": 1}} and got["items"][0]["said"] == "분석 이름을 바꾸자"
    assert c.put(f"/api/reqs/{rid}", json={"state": "done", "note": "바꿨다"}).json()["state"] == "done" and c.get("/api/reqs").json()["counts"]["tool:relay.heads"] == {"n": 1, "open": 0}
    assert c.put(f"/api/reqs/{rid}", json={"state": "끝"}).status_code == 400 and c.put(f"/api/reqs/{rid}", json={"targets": ["flow:nope"]}).status_code == 404
    assert c.put("/api/reqs/nope", json={"state": "done"}).status_code == 404 and c.delete("/api/reqs/nope").status_code == 404
    assert c.delete(f"/api/reqs/{rid}").json() == {"ok": True} and c.get("/api/reqs").json()["items"] == []


def test_repo_file_is_well_formed(monkeypatch):
    """저장소의 reqs/requirements.json — 모든 항목이 읽히고(꼴) · 대상이 등록부에 있고 · 줄 꼴이 저장하는 꼴 그대로다(`python -X utf8 tools/reqs.py check` 가 같은 것을 본다).
    도구 · 단계 · 워크플로우를 없애거나 키를 바꾸면 여기서 떨어진다 — 그 요구사항의 대상을 새 키로 고친다(지우지 않는다)."""
    monkeypatch.setenv("NFM_REQS", str(R.FILE))
    assert R.FILE.is_file() and cli.problems() == []
    items = R.load()["items"]
    assert items and all(it["said"] and it["date"] for it in items) and len({it["id"] for it in items}) == len(items)
