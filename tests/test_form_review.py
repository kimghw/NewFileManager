"""양식 검토 — 양식 전체를 읽고 어떻게 쓸지 · 쓰기 전에 사람이 확인할 것을 묻기(app/form_review.py · form_review_api.py — spec_양식작성 ② §5-1).
LLM 을 부르지 않는다(llm.call 을 가짜로)."""
import time

import pytest
from fastapi.testclient import TestClient

from app import doc_agent as A
from app import doc_agent_api, form_review, guide_write, server
from app import form_review_api as R
from app import guide_write_api as GW
from tests.test_guide_write import BLOCKS, GRAPH, IX, SMALL

PLACES = guide_write.places(BLOCKS, GRAPH, IX)
ANSWER = {"summary": "연구개발 목표와 추진 전략을 개조식으로 씁니다.",
          "places": [{"id": "h2", "how": "정량 지표와 함께 3줄", "needs": "목표 수치", "use": "자료의 최종 목표 문단", "gap": "기준 연도"}, {"id": "zz", "how": "없는 자리", "needs": "", "use": "", "gap": ""}],
          "questions": [{"text": "어느 기관의 몫을 쓰나요?", "why": "자료에 여러 기관", "places": [], "choices": ["한국선급", "주관기관"], "suggest": "한국선급", "source": "한국선급(KR)"},
                        {"text": "목표의 기준 연도는?", "why": "", "places": ["h2", "zz"], "choices": [], "suggest": "", "source": ""},
                        {"text": "어느 기관의 몫을 쓰나요?", "why": "겹침", "places": [], "choices": [], "suggest": "", "source": ""}]}


def test_form_text_reads_the_whole_form_in_order():
    text, cut = form_review.form_text(BLOCKS, GRAPH)
    assert not cut and text.splitlines()[0] == "# 1. 연구개발 목표 [h1]" and "이미 쓴 글" in text and "[표 t1]\n  구분 | 내용" in text and "## 1-1. 최종 목표 [h2]" in text
    long = BLOCKS + [{"id": f"x{i}", "type": "paragraph", "text": "가" * 500} for i in range(200)]
    t2, cut2 = form_review.form_text(long, GRAPH)
    assert cut2 and len(t2) <= form_review.FORM_MAX and "## 1-1. 최종 목표 [h2]" in t2   # 문단을 줄여도 헤딩 줄은 남는다


def test_check_keeps_known_places_and_drops_suggestions_without_materials():
    rv = form_review.check(ANSWER, [p["id"] for p in PLACES], has_materials=True)
    assert list(rv["places"]) == ["h2"] and [q["key"] for q in rv["questions"]] == ["q1", "q2"]   # 모르는 자리 · 같은 물음은 버린다
    assert rv["questions"][0]["suggest"] == "한국선급" and rv["questions"][1]["places"] == ["h2"]
    no = form_review.check(ANSWER, [p["id"] for p in PLACES], has_materials=False)
    assert (rv["places"]["h2"]["use"], rv["places"]["h2"]["gap"]) == ("자료의 최종 목표 문단", "기준 연도") and (no["places"]["h2"]["use"], no["places"]["h2"]["gap"]) == ("", "")   # 작성 계획(use · gap)은 자료가 있을 때만
    assert form_review.planned({**rv, "materials": ["m1"]}) and not form_review.planned({**no, "materials": []}) and not form_review.planned(None)
    assert all(q["suggest"] == "" and q["source"] == "" for q in no["questions"])               # 자료가 없으면 답 후보를 받지 않는다(짓지 않음)
    assert form_review.check(None, [], False) == {"summary": "", "places": {}, "questions": []}


def test_open_questions_and_plan_for_each_place():
    rv = form_review.check(ANSWER, [p["id"] for p in PLACES], True)
    assert [q["key"] for q in form_review.open_questions(rv, [])] == ["q1", "q2"]
    dec = [{"key": "q1", "q": "어느 기관의 몫을 쓰나요?", "a": "한국선급"}, {"key": "q2", "q": "목표의 기준 연도는?", "a": form_review.SKIP}]
    assert form_review.open_questions(rv, dec) == []
    p2 = form_review.plan_for(rv, dec, "h2")
    assert p2["facts"] == [("어느 기관의 몫을 쓰나요?", "한국선급")] and p2["how"] == "정량 지표와 함께 3줄"   # 「자료대로」 는 싣지 않는다
    assert form_review.plan_for(rv, dec + [{"key": "", "q": "분량", "a": "1쪽"}], "h3")["facts"] == [("어느 기관의 몫을 쓰나요?", "한국선급"), ("분량", "1쪽")]
    text = form_review.plan_text(p2)
    assert text.startswith("사람이 정해 준 것(이대로 따릅니다):\n- 어느 기관의 몫을 쓰나요? → 한국선급") and "작성 방향(이 자리): 정량 지표와 함께 3줄" in text
    assert "작성 계획 — 자료에서 쓸 것: 자료의 최종 목표 문단 / 자료에 없는 것(짓지 않습니다): 기준 연도" in text
    req = guide_write.request(next(p for p in PLACES if p["id"] == "h2"), "개조식", "", text)
    assert "사람이 정해 준 것" in req and req.rstrip().endswith("그렇게 답하세요(지어내지 않습니다).") and len(req) <= guide_write.TEXT_MAX
    big = guide_write.request({**PLACES[0], "guides": [{"src": "doc", "kind": "k", "text": "가" * 9000}]}, "나" * 1000, "", "다" * form_review.PLAN_MAX)
    assert len(big) <= guide_write.TEXT_MAX and big.rstrip().endswith("그렇게 답하세요(지어내지 않습니다).")   # 넘치면 작성 지침 몫을 줄인다 — 묻는 말은 남는다


@pytest.fixture
def c(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    A._MEMORY.clear()
    server.DOCS.clear()
    R._RUNS.clear()
    R._MEM.clear()
    GW._RUNS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()
    R._RUNS.clear()
    R._MEM.clear()
    GW._RUNS.clear()


def _wait(c, doc):
    for _ in range(200):
        run = c.get(f"/api/docs/{doc}/form-review").json()["run"]
        if run and run["state"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("양식 검토가 끝나지 않음")


def test_review_then_answers_gate_the_guide_write_run(c, monkeypatch):
    doc = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    monkeypatch.setattr(GW, "_places", lambda s: (PLACES, 0))
    got = c.get(f"/api/docs/{doc}/form-review").json()
    assert got["review"] is None and got["decided"] == [] and got["run"] is None
    assert c.post(f"/api/docs/{doc}/form-review", json={}).status_code == 503                         # LLM 꺼짐
    monkeypatch.setattr(R.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(GW.llm, "status", lambda: {"available": True})
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "자료.md", "text": "한국선급(KR) 최종 목표: 차단 시간 1 ms"}).json()["id"]
    gw = f"/api/docs/{doc}/guide-write/run"
    r = c.post(gw, json={"places": ["h2"], "materials": [mid]})
    assert r.status_code == 409 and "양식 검토" in r.json()["detail"]                                 # 검토 전에는 쓰지 않는다
    sent = []

    def call(schema, content, what, **kw):
        sent.append((what, content, kw))
        return {"data": ANSWER, "backend": "fake", "ms": 1, "costUsd": 0}
    monkeypatch.setattr(R.llm, "call", call)
    assert c.post(f"/api/docs/{doc}/form-review", json={"materials": ["m00000000"]}).status_code == 400
    # ① 양식만 검토(자료 없이) — 작성 방향은 있고 작성 계획은 없다 → 아직 쓰지 않는다
    assert c.post(f"/api/docs/{doc}/form-review", json={}).status_code == 200
    assert _wait(c, doc)["state"] == "done"
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert not v["planned"] and v["review"]["places"]["h2"] == {"how": "정량 지표와 함께 3줄", "needs": "목표 수치", "use": "", "gap": ""} and "materials" not in sent[0][1].split("## 자료(JSON)")[1]
    r = c.post(gw, json={"places": ["h2"], "materials": [mid]})
    assert r.status_code == 409 and "작성 계획" in r.json()["detail"]
    # ② 자료를 주고 작성 계획 — 자리마다 자료에서 쓸 것 · 자료에 없는 것
    assert c.post(f"/api/docs/{doc}/form-review", json={"materials": [mid]}).status_code == 200
    assert _wait(c, doc)["state"] == "done"
    what, content, kw = sent[-1]
    assert what == "form-review" and kw["model"] == form_review.MODEL and "\"id\":\"h2\"" in content and "\"form\":" in content and "차단 시간 1 ms" in content and "쓰기 전에 사람이 정해 줘야 할 것" in content
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert v["open"] == ["q1", "q2"] and v["review"]["questions"][0]["suggest"] == "한국선급" and not v["stale"] and v["planned"] and v["review"]["places"]["h2"]["use"] == "자료의 최종 목표 문단"
    r = c.post(gw, json={"places": ["h2"], "materials": [mid]})
    assert r.status_code == 409 and "확인할 것 2개" in r.json()["detail"]                              # 답하기 전에는 쓰지 않는다
    url = f"/api/docs/{doc}/form-review/answers"
    assert c.put(url, json={"answers": [{"key": "q9", "a": "x"}]}).status_code == 400
    v = c.put(url, json={"answers": [{"key": "q1", "a": "한국선급"}, {"key": "q2", "a": "2026년"}, {"q": "분량", "a": "자리마다 1쪽 이내"}]}).json()
    assert v["open"] == [] and len(v["decided"]) == 3
    seen = []
    monkeypatch.setattr(doc_agent_api, "agent_turn", lambda doc_id, body: seen.append(body) or {"turn": {"id": "t1", "reply": "", "proposals": []}})
    r = c.post(gw, json={"places": ["h2", "h3"], "materials": [mid]})
    assert r.status_code == 200 and "plans" not in r.json()["run"]
    for _ in range(200):
        if c.get(f"{gw}").json()["run"]["state"] != "running":
            break
        time.sleep(0.05)
    by = {("id h2" in b["text"]): b["text"] for b in seen}
    assert "- 목표의 기준 연도는? → 2026년" in by[True] and "작성 방향(이 자리): 정량 지표와 함께 3줄" in by[True] and "자료에서 쓸 것: 자료의 최종 목표 문단" in by[True] and "- 분량 → 자리마다 1쪽 이내" in by[True]
    assert "기준 연도" not in by[False] and "- 어느 기관의 몫을 쓰나요? → 한국선급" in by[False]          # 자리에 닿는 물음만 · 문서 전체의 답은 모든 자리에
    # 다시 검토 — 실패해도 앞 검토 · 정한 것은 남는다
    monkeypatch.setattr(R.llm, "call", lambda *a, **k: {"data": None, "error": "busy"})
    assert c.post(f"/api/docs/{doc}/form-review", json={}).status_code == 200
    assert _wait(c, doc)["state"] == "failed"
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert v["review"]["summary"] == ANSWER["summary"] and len(v["decided"]) == 3 and v["open"] == []
    # 다시 검토 — 같은 물음은 정한 것을 다시 잇고 새 물음만 남는다
    monkeypatch.setattr(R.llm, "call", lambda *a, **k: {"data": {**ANSWER, "questions": [ANSWER["questions"][1], {"text": "새 물음", "why": "", "places": [], "choices": [], "suggest": "", "source": ""}]}})
    c.post(f"/api/docs/{doc}/form-review", json={})
    _wait(c, doc)
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert v["open"] == ["q2"] and {d["q"]: d["key"] for d in v["decided"]} == {"어느 기관의 몫을 쓰나요?": "", "목표의 기준 연도는?": "q1", "분량": ""}
    v = c.put(url, json={"answers": [{"q": "분량", "a": ""}]}).json()
    assert [d["q"] for d in v["decided"]] == ["어느 기관의 몫을 쓰나요?", "목표의 기준 연도는?"]   # 빈 답 = 지움


def test_agent_is_registered():
    from app import agent_settings, agents
    assert agents.BY_ID["form_review"]["no"] == "25" and "form_review" in agent_settings.IDS
    assert form_review.parts()[0]["key"] == "contract"


def test_work_reset_forgets_review_and_guide_write_memory():
    """작업 내용 초기화(server._reset_forget) — 양식 검토 · 지침 작성의 메모리 기억(실행 · 저장 끔 문서의 검토)도 버린다(2026-11-24 사용자 「작업내용 초기화 해도... 다 제거 되지 않고」)."""
    R._RUNS["w1"] = {"state": "done"}
    R._MEM["w1"] = {"review": {"summary": "x"}, "decided": []}
    GW._RUNS["w1"] = {"state": "done"}
    server._reset_forget("w1")
    assert "w1" not in R._RUNS and "w1" not in R._MEM and "w1" not in GW._RUNS
