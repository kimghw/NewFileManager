"""내가 만든 단계(spec_워크플로우 ② §18-14 「단계 만들기」 — app/custom_stages.py · 끝점 app/custom_tasks_api.py): 있는 줄을 골라 이름 붙여 저장 · 조립과 같은 검사(단계 하나로 볼 수 있는 것만) · 저장 파일 보호."""
import json

import pytest

from app import custom_stages as S
from app import custom_tasks as C

REVIEW = [{"unit": "heads", "on": ["source"]}, {"unit": "headsLlm", "on": ["source"]}]


def test_a_stage_is_a_named_group_of_existing_lines():
    s = S.create({"name": "  원본만   검토 ", "desc": "원본 문서만 본다", "steps": REVIEW}, ["문서 검토"])
    assert S.KEY.fullmatch(s["key"]) and (s["name"], s["desc"], s["steps"]) == ("원본만 검토", "원본 문서만 본다", REVIEW)
    assert S.path() == C.path().with_name("tasks_stages.json") and json.loads(S.path().read_text(encoding="utf-8"))["stages"][0]["key"] == s["key"]   # 조립한 워크플로우의 저장 파일 옆
    assert [x["key"] for x in S.all()] == [s["key"]] and S.get(s["key"])["name"] == "원본만 검토" and S.get("s_00000000") is None
    # 목적 문서만의 단계도 된다(단계는 워크플로우의 한 조각 — 「원본 문서를 쓰는 줄이 없음」 은 조립할 때 본다)
    t = S.create({"name": "정리", "steps": [{"unit": "guide", "on": ["target"]}]})
    assert S.update(t["key"], {"name": "문서 정리만"})["name"] == "문서 정리만" and S.get(t["key"])["steps"] == [{"unit": "guide", "on": ["target"]}]
    assert S.update("s_00000000", {"name": "x"}) is None and S.delete(t["key"]) is True and S.delete(t["key"]) is False and len(S.all()) == 1
    # 구조 · 정리 줄은 원본 문서에도 놓는다(2026-11-20 사용자 「목적문서랑 원본 문서도 분리해서 따로 따로 하게」 — spec ② §18-2 「원본 문서에 놓는 줄」): 두 문서 같이 · 원본 문서만
    both = S.create({"name": "두 문서 구성", "steps": [{"unit": "division", "on": ["source", "target"]}, {"unit": "reheads", "on": ["source"]}]})
    assert both["steps"] == [{"unit": "division", "on": ["source", "target"]}, {"unit": "reheads", "on": ["source"]}] and S.delete(both["key"]) is True
    apart = [{"unit": "division", "on": ["target"]}, {"unit": "reheads", "on": ["target"]}, {"unit": "division", "on": ["source"]}]   # 문서끼리의 차례는 자유 — 목적 문서를 끝낸 뒤 원본 문서
    later = S.create({"name": "목적 먼저", "steps": apart})
    assert later["steps"] == apart and S.delete(later["key"]) is True


@pytest.mark.parametrize("body, word", [({"name": "", "steps": REVIEW}, "이름을 적으세요"), ({"name": "가" * 21, "steps": REVIEW}, "20자"), ({"name": "문서 검토", "steps": REVIEW}, "이미 있는 단계 이름"),
                                         ({"name": "빈", "steps": []}, "하나 이상"), ({"name": "모름", "steps": [{"unit": "nope", "on": ["target"]}]}, "nope"),
                                         ({"name": "거꾸로", "steps": [{"unit": "plan"}, {"unit": "link"}]}, "뒤에 와야"), ({"name": "검토가 먼저", "steps": [{"unit": "reheads", "on": ["source"]}, {"unit": "division", "on": ["source"]}]}, "「프로젝트 구성 반영」 뒤에")])
def test_stage_values_are_checked_by_the_same_rules_as_composing(body, word):
    with pytest.raises(ValueError) as e:
        S.create(body, ["문서 검토"])
    assert word in str(e.value) and S.all() == []


def test_a_broken_stage_file_is_not_overwritten():
    s = S.create({"name": "검토", "steps": REVIEW})
    S.path().write_text("{broken", encoding="utf-8")
    assert S.broken() and S.all() == []
    for call in (lambda: S.create({"name": "둘", "steps": REVIEW}), lambda: S.update(s["key"], {"name": "x"}), lambda: S.delete(s["key"])):
        with pytest.raises(S.Refused):
            call()
    assert S.path().read_text(encoding="utf-8") == "{broken"
    # 꼴이 틀린 줄은 숨기되 다른 줄을 쓸 때도 그대로 남는다
    S.path().write_text(json.dumps({"version": 2, "stages": [{"key": "bad"}, {"key": s["key"], "name": "검토", "steps": REVIEW, "at": 1}], "more": 1}), encoding="utf-8")
    assert [x["key"] for x in S.all()] == [s["key"]]
    S.update(s["key"], {"name": "고침"})
    got = json.loads(S.path().read_text(encoding="utf-8"))
    assert got["version"] == 3 and got["more"] == 1 and got["stages"][0] == {"key": "bad"} and got["stages"][1]["name"] == "고침"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import server
    return TestClient(server.app)


def test_stage_endpoints_and_the_builtin_stage_lines(client):
    t = client.get("/api/tasks?v=2").json()
    assert t["userStages"] == [] and t["stagesBroken"] is False
    lines = {s["id"]: [(x["unit"], x["on"]) for x in s["lines"]] for s in t["stages"]}   # 붙박이 단계의 표준 줄(조립의 「＋ 단계 넣기…」 가 넣는 것)
    assert lines["stage_review"] == [("heads", ["source", "target"]), ("headsLlm", ["source"])] and lines["stage_clean"] == [("guide", ["target"])]
    assert [u for u, _ in lines["stage_fit"]] == ["configLoad", "config", "division", "reheads", "reheadsLlm"] and [u for u, _ in lines["stage_fill"]][0] == "link"
    assert client.post("/api/stages/check", json={"steps": REVIEW}).json() == {"errors": [], "steps": REVIEW}
    assert "뒤에 와야" in client.post("/api/stages/check", json={"steps": [{"unit": "plan"}, {"unit": "link"}]}).json()["errors"][0]
    r = client.post("/api/stages", json={"name": "원본만 검토", "steps": REVIEW})
    assert r.status_code == 201, r.text
    s = r.json()["stage"]
    assert s["lines"] == ["헤딩 · 표 분석", "LLM 검증·보완"] and client.get("/api/tasks?v=2").json()["userStages"][0]["key"] == s["key"]
    assert client.post("/api/stages", json={"name": "원본만 검토", "steps": REVIEW}).status_code == 400 and client.post("/api/stages", json={"name": "문서 검토", "steps": REVIEW}).status_code == 400
    put = client.put(f"/api/stages/{s['key']}", json={"desc": "설명", "steps": REVIEW[:1]})
    assert put.status_code == 200 and put.json()["stage"]["desc"] == "설명" and put.json()["stage"]["lines"] == ["헤딩 · 표 분석"]
    assert client.put("/api/stages/s_00000000", json={"name": "x"}).status_code == 404 and client.delete("/api/stages/s_00000000").status_code == 404
    assert client.delete(f"/api/stages/{s['key']}").json() == {"deleted": True} and client.get("/api/tasks?v=2").json()["userStages"] == []
