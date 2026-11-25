"""단계 설명 고치기(spec_워크플로우 ② §18-26) — 저장(워크플로우 · 줄 key 마다 글 여섯) · 등록부 응답(listing)에만 얹기 · 만든 글은 기본 글 그대로 · API.
conftest 가 NFM_STEP_TEXTS 를 시험마다 임시 파일로 돌린다."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import step_texts as T
from app import step_texts_api as TA
from app import workflow

JOB, KEY = "form_write", "headsLlm"   # 사용자가 가리킨 단계(대시보드 「LLM 검증·보완」 의 메모)


def _client():
    app = FastAPI()
    app.include_router(TA.router)
    return TestClient(app)


def _step(job=JOB, key=KEY):
    t = next(t for t in workflow.listing()["tasks"] if t["job"] == job)
    return next(s for g in t["stages"] for s in g["steps"] if s["key"] == key)


def test_store_and_listing():
    base = TA.base_of(JOB, KEY)
    assert base and base["does"] and base["stop"] and T.load() == {"version": 0, "texts": {}}
    got = T.save(JOB, KEY, {"does": "  새   하는 일 ", "stop": "새 멈춤", "out": base["out"]}, base)
    assert got == {"version": 1, "texts": {"does": "새 하는 일", "stop": "새 멈춤"}}   # 기본 글과 같은 글은 남기지 않는다 · 빈칸은 한 칸으로
    s = _step()
    assert s["does"] == "새 하는 일" and {c["key"]: c["text"] for c in s["cond"]}["stop"] == "새 멈춤"
    assert s["baseText"] == {"does": base["does"], "stop": base["stop"]}
    assert _step()["out"] == base["out"]
    other = next(t for t in workflow.listing()["tasks"] if t["job"] != JOB and any(s["key"] == KEY for g in t["stages"] for s in g["steps"]))
    assert all(s["baseText"] == {} for g in other["stages"] for s in g["steps"])   # 다른 워크플로우의 같은 줄 key 는 그대로
    assert "새 하는 일" not in workflow.task_markdown(JOB)   # 만든 글(tasks/<job>.md)은 기본 글
    T.save(JOB, KEY, {"does": "", "stop": base["stop"]}, base)   # 빈 글 · 기본 글 = 고친 글을 지움
    assert T.load()["texts"] == {} and _step()["baseText"] == {}


def test_check():
    assert T.check("a\n b\t c") == "a b c"
    for bad in (3, "x" * (T.TEXT_MAX + 1), "a\x01"):
        try:
            T.check(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_api_roundtrip():
    cl = _client()
    assert cl.get("/api/step-texts").json()["texts"] == {}
    r = cl.put(f"/api/step-texts/{JOB}/{KEY}", json={"texts": {"done": "다 됐을 때"}, "version": 0})
    assert r.status_code == 200 and r.json()["texts"] == {"done": "다 됐을 때"} and r.json()["base"]["done"]
    assert cl.get("/api/step-texts").json()["texts"] == {f"{JOB}.{KEY}": {"done": "다 됐을 때"}}
    assert cl.put(f"/api/step-texts/{JOB}/{KEY}", json={"texts": {"done": "x"}, "version": 0}).status_code == 409
    assert cl.put(f"/api/step-texts/{JOB}/{KEY}", json={"texts": {"nope": "x"}}).status_code == 400
    assert cl.put(f"/api/step-texts/{JOB}/noSuch", json={"texts": {"does": "x"}}).status_code == 404
    assert cl.put(f"/api/step-texts/noJob/{KEY}", json={"texts": {"does": "x"}}).status_code == 404
    assert cl.delete(f"/api/step-texts/{JOB}/{KEY}").json()["texts"] == {}
    assert cl.get("/api/step-texts").json()["texts"] == {}
