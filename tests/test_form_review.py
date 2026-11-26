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


@pytest.fixture(autouse=True)
def _one_model():
    """이 파일의 시험은 호출 한 번의 검토를 본다 — 모델 여럿(LLM1 · LLM2 + 협의)은 tests/test_form_review_llms.py."""
    from app import agent_settings
    agent_settings.save("form_review", {"models": ["claude-opus-5-5"]})

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
    assert form_review.check(None, [], False) == {"summary": "", "places": {}, "questions": [], "topics": []}


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
    monkeypatch.setattr(doc_agent_api, "_turn", lambda doc_id, body, scope=None: seen.append(body) or {"turn": {"id": "t1", "reply": "", "proposals": []}}, raising=False)
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


# ---- 상자를 줄마다 읽기 · 자리의 지문 · 자료에서 찾을 테마 · 자리를 잃은 답(2026-11-24 — spec_양식작성 ② §5-2 · §5-3) --------------------------

def _box_places(blocks=None):
    from tests.test_guide_write import FGRAPH, FIX, FORM
    return guide_write.places(FORM if blocks is None else blocks, FGRAPH, FIX)


def test_form_text_reads_a_box_line_by_line():
    from tests.test_form_slots import BOX97
    from tests.test_guide_write import FGRAPH, FORM
    text, cut = form_review.form_text(FORM, FGRAPH)
    assert not cut and "# ■ 세부 과제별 당해연도 성과목표 관리 [f3]\n[상자 t44]\n  (빈 줄 1)\n  [p47] 「< 연구개발 과제명 작성 >」" in text               # 칸을 80자로 뭉개지 않는다 — 문단마다 id · 종류
    assert "[상자 t97]\n  [p99] (L1) 「■ 다음연도 연구개발 계획」" in text and "  [p103] (L4) 「000」\n  [p104] (L5) 「    - 」 (쓸 자리 — 글머리 줄)" in text
    assert "  [p75] (L4) 「공동(기업명 작성) : 」 (쓸 자리 — 같은 줄 뒤에 값)\n  [p76 p77] (쓸 자리 — 빈 줄 2)" in text and "[표 t117 3×3 — 표 · 그림 자리" in text
    assert "[표 t9]\n" in text and "[상자 tb]\n  [tbp] 「제목 상자」" in text and "[표 t97]" not in text                                         # 여러 칸 표는 전처럼 · 상자는 [표 …] 로 싣지 않는다
    orig = {b["id"]: b["text"] for b in BOX97["cells"][0]["blocks"] if b["type"] == "paragraph"}
    blocks = [b if b["id"] != "t97" else {**b, "cells": [{**b["cells"][0], "blocks": [{**x, "text": "    - 채운 목표"} if x["id"] == "p104" else x for x in b["cells"][0]["blocks"]]}]} for b in FORM]
    assert "「    - 채운 목표」 (이미 채움 — 다시 쓰지 않음)" in form_review.form_text(blocks, FGRAPH, orig=orig)[0]
    brief = {p["id"]: p for p in form_review.payload(FORM, FGRAPH, _box_places(), [])["places"]}                                             # 자리 목록에도 상자 · 같은 줄 자리가 보인다
    assert (brief["t44"]["kind"], brief["t44"]["slots"], brief["f1"]["slot"], brief["f2"]["slot"], brief["f3"]["boxed"]) == ("box", 3, "label", "check", True) and "fp" not in brief["t44"] and "slot" not in brief["f4"]
    assert "「[상자 id]」 = 1칸 표(상자)" in form_review.CONTRACT and "자료에서 찾을 테마 · 키워드" in form_review.CONTRACT and "topics" in form_review.SCHEMA["required"]


def test_place_sig_sees_swapped_titles_and_guide_edits():
    from tests.test_guide_write import FGRAPH, FIX, FORM
    ps = {p["id"]: p for p in _box_places()}
    swap = {"p102": "연구개발 내용 및 범위", "p110": "연구개발 목표"}
    blocks = [b if b["id"] != "t97" else {**b, "cells": [{**b["cells"][0], "blocks": [{**x, "text": swap.get(x["id"], x.get("text"))} if x["type"] == "paragraph" else x for x in b["cells"][0]["blocks"]]}]} for b in FORM]
    sw = {p["id"]: p for p in _box_places(blocks)}
    assert (sw["t97"]["id"], sw["t97"]["text"], len(sw["t97"]["chunks"]), [v["key"] for v in sw["t97"]["chunks"]]) == (ps["t97"]["id"], ps["t97"]["text"], len(ps["t97"]["chunks"]), [v["key"] for v in ps["t97"]["chunks"]])
    assert form_review.place_sig(sw["t97"]) != form_review.place_sig(ps["t97"])                    # 고정 제목 둘을 맞바꿈 — id · 이름 · 덩이 수는 같아도 지문이 다르다(astra 2차 G11)
    assert form_review.place_sig(sw["t44"]) == form_review.place_sig(ps["t44"]) and form_review.sig(list(sw.values())) != form_review.sig(list(ps.values()))
    ix2 = {**FIX, "heads": {"f4": [{"src": "doc", "kind": "※ 안내", "text": "붙임은 두 쪽"}]}}
    g2 = {p["id"]: p for p in guide_write.places(FORM, FGRAPH, ix2)}
    assert form_review.place_sig(g2["f4"]) != form_review.place_sig(ps["f4"]) and form_review.place_sig(g2["f1"]) == form_review.place_sig(ps["f1"])
    assert form_review.sigs(list(ps.values())) == {i: form_review.place_sig(p) for i, p in ps.items()}
    assert form_review.place_sig({**ps["f1"], "slot": "filled"}) != form_review.place_sig(ps["f1"])   # 같은 줄 자리를 채움 — 그 자리의 계획은 다시 본다


def test_topics_are_cleaned_and_make_one_scope_line():
    raw = [{"name": "당해연도 개발목표", "keywords": ["개발 목표", "세부 목표", "개발 목표", "당해연도 개발목표", 7, "", "가" * 50], "context": "성과목표 상자의 주관 · 공동 줄에 개조식으로", "scope": "당해연도 개발목표와\n추진 내용", "places": ["t44", "zz", "t44"]},
           {"name": "당해연도 개발목표", "keywords": [], "context": "겹침", "scope": "x", "places": []}, {"name": "", "keywords": [], "context": "", "scope": "이름 없음", "places": []}, "글",
           {"name": "다음 연도 계획", "keywords": ["k1", "k2", "k3", "k4", "k5", "k6", "k7"], "context": "", "scope": "", "places": ["zz"]}]
    ts = form_review.topics(raw, ["t44", "t97"])
    assert [(t["key"], t["name"], t["places"]) for t in ts] == [("t1", "당해연도 개발목표", ["t44"]), ("t2", "다음 연도 계획", [])]   # 겹친 이름 · 이름 없는 것은 버림 · 모르는 자리는 빼도 테마는 남는다
    assert ts[0]["keywords"] == ["개발 목표", "세부 목표", "가" * 29 + "…"] and ts[0]["scope"] == "당해연도 개발목표와 추진 내용" and "\n" not in ts[0]["scope"]
    assert ts[1]["scope"] == "다음 연도 계획" and len(ts[1]["keywords"]) == form_review.KEYWORDS_MAX                                  # 범위 글이 비면 이름 · 키워드는 6개까지
    assert len(form_review.topics([{"name": f"테마 {i}", "keywords": [], "context": "", "scope": "", "places": []} for i in range(30)], [])) == form_review.TOPICS_MAX
    assert form_review.topics(None, []) == [] and form_review.topics({"name": "x"}, []) == []
    rv = form_review.check({**ANSWER, "topics": raw}, ["t44", "t97", "h2"], False)
    assert [t["name"] for t in rv["topics"]] == ["당해연도 개발목표", "다음 연도 계획"]                                                # 자료 없이 한 검토에서도 받는다
    line = form_review.scope_line
    assert line(ts[0]) == "당해연도 개발목표와 추진 내용 (개발 목표 · 세부 목표 · " + "가" * 29 + "…)" and line(ts[0], "  한국선급,\n 1차년도 ").startswith("한국선급, 1차년도, 당해연도 개발목표와 추진 내용 (")
    assert line({"scope": "연구개발 목표와 개발 내용·범위", "keywords": ["개발 내용", "세부 목표"]}, "") == "연구개발 목표와 개발 내용·범위 (세부 목표)"   # 앞말이 없으면 쉼표도 없다 · 범위 글에 이미 든 키워드는 뺀다
    assert line({"name": "이름만", "keywords": []}) == "이름만" and "\n" not in line({"scope": "두\n줄", "keywords": ["가\n나"]}, "앞\n말")
    assert len(line({"scope": "가" * 900, "keywords": ["나" * 30]}, "다" * 300)) == 600


def test_lost_answers_go_to_no_place():
    rv = form_review.check({**ANSWER, "questions": [ANSWER["questions"][0]]}, ["h1", "h2", "h3"], True)   # 지금 검토의 물음 = 「어느 기관의 몫」 하나(문서 전체)
    dec = [{"key": "q1", "q": "어느 기관의 몫을 쓰나요?", "a": "한국선급", "places": []},
           {"key": "", "q": "다음 연도 목표는 어느 것을 따르나요?", "a": "2-2 ① 개발 목표 3개", "places": ["t117"]},          # 답할 때의 자리(t117)가 사라졌고 그 물음도 지금 검토에 없다
           {"key": "", "q": "분량", "a": "1쪽", "places": []}, {"key": "", "q": "옛 자리의 것", "a": form_review.SKIP, "places": ["t117"]},
           {"key": "", "q": "h2 의 기준 연도", "a": "2026년", "places": ["h2", "t117"]}]
    ids = ["h1", "h2", "h3"]
    assert [d["q"] for d in form_review.lost(rv, dec, ids)] == ["다음 연도 목표는 어느 것을 따르나요?"]                        # 「자료대로」 · 자리가 하나라도 남은 답 · 문서 전체의 답은 아니다
    assert form_review.plan_for(rv, dec, "h3", ids)["facts"] == [("어느 기관의 몫을 쓰나요?", "한국선급"), ("분량", "1쪽")]   # 자리를 잃은 답은 어느 자리에도 싣지 않는다
    assert ("h2 의 기준 연도", "2026년") in form_review.plan_for(rv, dec, "h2", ids)["facts"] and ("다음 연도 목표는 어느 것을 따르나요?", "2-2 ① 개발 목표 3개") not in form_review.plan_for(rv, dec, "h2", ids)["facts"]
    assert ("다음 연도 목표는 어느 것을 따르나요?", "2-2 ① 개발 목표 3개") not in form_review.plan_for(rv, dec, "h3")["facts"]   # 자리 목록을 안 줘도 그 답의 자리(t117)가 아닌 곳에는 안 간다
    assert form_review.lost(rv, dec, ids + ["t117"]) == [] and form_review.lost(None, dec[:1], ids) == [] and form_review.lost(rv, [], ids) == []
    back = {**rv, "questions": rv["questions"] + [{"key": "q2", "text": "다음 연도 목표는 어느 것을 따르나요?", "why": "", "places": ["h3"], "choices": [], "suggest": "", "source": ""}]}
    assert form_review.lost(back, dec, ids) == [] and ("다음 연도 목표는 어느 것을 따르나요?", "2-2 ① 개발 목표 3개") in form_review.plan_for(back, dec, "h3", ids)["facts"]   # 같은 물음이 새 자리에 다시 서면 그 자리에 잇는다


def test_topics_kept_on_replan_lost_answers_and_old_saved_reviews(c, monkeypatch):
    doc = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    wid = server._sess(doc).id
    places = list(PLACES)
    monkeypatch.setattr(GW, "_places", lambda s: (places, 0))
    monkeypatch.setattr(R.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(GW.llm, "status", lambda: {"available": True})
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "자료.md", "text": "한국선급(KR) 최종 목표"}).json()["id"]
    topics = [{"name": "최종 목표", "keywords": ["목표 수치", "정량 지표"], "context": "1-1 에 3줄", "scope": "최종 목표와 정량 지표", "places": ["h2"]}]
    plan_t = [{"name": "자료의 목표 수치", "keywords": ["목표"], "context": "자료 2절", "scope": "자료에 적힌 목표 수치", "places": ["h2"]}]
    answers = [{**ANSWER, "topics": topics}, {**ANSWER, "topics": plan_t}, {**ANSWER, "topics": []}]
    monkeypatch.setattr(R.llm, "call", lambda *a, **k: {"data": answers.pop(0), "backend": "fake", "ms": 1})
    url = f"/api/docs/{doc}/form-review"
    assert c.post(url, json={}).status_code == 200 and _wait(c, doc)["state"] == "done"                 # ① 양식만 검토 — 테마를 받는다
    v = c.get(url).json()
    assert [t["name"] for t in v["review"]["topics"]] == ["최종 목표"] and v["topicLines"] == ["최종 목표와 정량 지표 (목표 수치)"] and v["lost"] == [] and "topicsKept" not in v["review"]
    assert set(v["review"]["sigs"]) == {p["id"] for p in PLACES}
    assert c.post(url, json={"materials": [mid]}).status_code == 200 and _wait(c, doc)["state"] == "done"   # ② 계획 — 답이 테마를 비워 보냄: 양식이 그대로면 앞의 것을 지닌다
    v = c.get(url).json()
    assert v["planned"] and [t["name"] for t in v["review"]["topics"]] == ["최종 목표"] and v["review"]["topicsKept"] is True
    # 작성 계획이 뽑은 테마는 따로(화면의 「작성 계획」 탭 — 2026-11-26 사용자 「6번에서 나온 결과 인지 모르잖아. 탭으로」) — 06 의 것을 덮지 않는다
    assert [t["name"] for t in v["review"]["planTopics"]] == ["자료의 목표 수치"] and v["planTopicLines"] and v["topicLines"] == ["최종 목표와 정량 지표 (목표 수치)"]
    assert R.unplan(wid) and "planTopics" not in R.load(wid)["review"]   # 「작성 초기화」 는 계획이 뽑은 테마도 비운다
    answers.insert(0, {**ANSWER, "topics": plan_t})
    assert c.post(url, json={"materials": [mid]}).status_code == 200 and _wait(c, doc)["state"] == "done"   # 계획을 되살린다(아래가 그 위에서 본다)
    places[:] = [{**p, "guides": [{"src": "user", "kind": "사용자 지침", "text": "두 줄로"}]} if p["id"] == "h2" else p for p in PLACES]   # 양식(지침)이 바뀜 → 옛 테마를 잇지 않는다
    assert c.post(url, json={"materials": [mid]}).status_code == 200 and _wait(c, doc)["state"] == "done"
    v = c.get(url).json()
    assert v["review"]["topics"] == [] and v["topicLines"] == [] and "topicsKept" not in v["review"] and not v["stale"]
    # 자리를 잃은 답 — 화면이 알리고(lost) 어느 자리의 요청에도 싣지 않는다
    st = R.load(wid)
    R._save(wid, {"review": st["review"], "decided": [{"key": "q1", "q": "어느 기관의 몫을 쓰나요?", "a": "한국선급", "places": []}, {"key": "q2", "q": "목표의 기준 연도는?", "a": "2026년", "places": ["h2"]},
                                                      {"key": "", "q": "옛 표의 물음", "a": "셋째 것", "places": ["t117"]}]})
    v = c.get(url).json()
    assert v["lost"] == ["옛 표의 물음"] and v["open"] == []
    assert all("옛 표의 물음" not in t for t in R.plans(wid, places, [p["id"] for p in places]).values()) and any("옛 표의 물음" not in t and "한국선급" in t for t in R.plans(wid, places, [p["id"] for p in places]).values())
    # 옛 저장본(테마 · 자리 지문이 없던 때의 검토) — 그대로 읽히고, 문은 자리 id 로만 본다
    R._save(wid, {"review": {"summary": "옛 검토", "places": {"h2": {"how": "3줄", "needs": "", "use": "목표 문단", "gap": ""}}, "questions": [], "materials": [mid], "sig": "old"}, "decided": []})
    v = c.get(url).json()
    assert v["review"]["summary"] == "옛 검토" and v["topicLines"] == [] and v["lost"] == [] and v["stale"] and "topics" not in v["review"]   # topics 열쇠 없음 = 아직 뽑지 않음(화면이 0개와 가른다)
    ok, why, got = R.gate(wid)
    assert ok and why == "" and R.fresh(got, [p for p in places if p["id"] == "h2"], [mid]) == ""
    assert "바뀐 자리 1곳" in R.fresh(got, [p for p in places if p["id"] == "h3"], [mid]) and "자료가 다릅니다" in R.fresh(got, [p for p in places if p["id"] == "h2"], [])
    new = {"review": {**got["review"], "sigs": form_review.sigs(places)}, "decided": []}                 # 새 검토 — LLM 이 작성 방향을 안 낸 자리(h3)도 검토한 자리다
    assert R.fresh(new, [p for p in places if p["id"] in ("h2", "h3")], [mid]) == "" and "바뀐 자리 1곳" in R.fresh(new, [{**places[0], "text": "고친 헤딩"}], [mid])


def test_unplaced_question_goes_nowhere():
    """물음이 자리를 적었는데 모두 모르는 id 면 「문서 전체」 가 아니다 — 그 답은 어느 자리에도 싣지 않는다(astra 2차 「빠뜨린 2」 의 검토 시점 쪽). 자리를 안 적은 물음(문서 전체)은 전처럼 모든 자리에."""
    from app import form_review as FR
    rv = FR.check({"summary": "", "places": [], "topics": [], "questions": [
        {"text": "없는 자리의 물음", "why": "", "places": ["zz"], "choices": [], "suggest": "", "source": ""},
        {"text": "문서 전체의 물음", "why": "", "places": [], "choices": [], "suggest": "", "source": ""}]}, ["h1", "h2"], False)
    assert rv["questions"][0].get("unplaced") is True and rv["questions"][0]["places"] == [] and "unplaced" not in rv["questions"][1]
    dec = [{"key": "q1", "q": "없는 자리의 물음", "a": "가", "places": []}, {"key": "q2", "q": "문서 전체의 물음", "a": "나", "places": []}]
    for pid in ("h1", "h2"):
        assert FR.plan_for(rv, dec, pid)["facts"] == [("문서 전체의 물음", "나")]


def test_lost_answer_stays_lost_and_stale_key_is_refused(c):
    """astra 3차 — ⓐ 자리를 잃은 물음의 답은 그 물음이 사라진 뒤에도 「문서 전체」 로 되살아나지 않는다(답에 unplaced 를 적어 둔다) ⓑ 옛 화면의 물음 번호로 온 답(물음 글이 다르다)은 409."""
    from app import form_review as FR
    rv = {"places": {}, "questions": [{"key": "q1", "text": "보고서 종류", "why": "", "places": [], "choices": [], "suggest": "", "source": "", "unplaced": True}]}
    dec = [{"key": "q1", "q": "보고서 종류", "a": "연차보고서", "places": [], "unplaced": True}]
    assert FR.plan_for(rv, dec, "h1", ["h1"]) is None
    gone = {"places": {}, "questions": []}                                                                   # 다시 검토 — 그 물음이 없어졌다
    assert FR.plan_for(gone, dec, "h1", ["h1"]) is None and [d["q"] for d in FR.lost(gone, dec, ["h1"])] == ["보고서 종류"]
    doc = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    from app import form_review_api as API
    API._save(doc, {"review": {"places": {}, "questions": [{"key": "q1", "text": "주관기관", "why": "", "places": [], "choices": [], "suggest": "", "source": ""}], "materials": []}, "decided": []})
    r = c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"key": "q1", "q": "보고서 종류", "a": "연차보고서"}]})
    assert r.status_code == 409 and "검토가 바뀌었습니다" in r.json()["detail"]
    assert c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"key": "q1", "q": "주관기관", "a": "가"}]}).status_code == 200


def test_review_and_plan_are_apart_and_review_sees_the_request(c, monkeypatch):
    """2026-11-25 사용자 「양식검토만 하는데 왜 다른걸 돌려 ... 목적문서의 양식에 뭘 작성해야하는지, 어떤 지침이 있는지 사용자가 요청하는건 뭔지를 봐야지」(spec_양식작성 ② §5-1 「① ② 를 뗀다」):
    작성 계획은 양식 검토 뒤(409) · 양식 검토는 자료 없이 사람의 요청(note)을 읽고 보는 셋(sees)을 낸다 · 계획은 검토의 요약 · 보는 셋 · 작성 방향을 바꾸지 않는다."""
    doc = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    monkeypatch.setattr(GW, "_places", lambda s: (PLACES, 0))
    monkeypatch.setattr(R.llm, "status", lambda: {"available": True})
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "자료.md", "text": "한국선급(KR) 최종 목표"}).json()["id"]
    sees = {"write": "1-1 에 최종 목표를 씀", "guides": "작성 요령: 개조식 3줄", "asks": "한국선급 몫만 — 요청대로"}
    answers = [{**ANSWER, "sees": sees}, {**ANSWER, "summary": "계획이 낸 다른 요약", "sees": {"write": "다름", "guides": "", "asks": ""},
                                          "places": [{**ANSWER["places"][0], "how": "계획이 낸 다른 방향"}]}]
    sent = []
    monkeypatch.setattr(R.llm, "call", lambda schema, content, what, **kw: sent.append(content) or {"data": answers.pop(0), "backend": "fake", "ms": 1})
    url = f"/api/docs/{doc}/form-review"
    r = c.post(url, json={"materials": [mid]})
    assert r.status_code == 409 and "양식 검토" in r.json()["detail"] and not sent                   # 계획은 검토가 먼저 — 한 단추가 두 걸음을 돌리지 않는다
    assert c.post(url, json={"note": "x" * (form_review.REQUEST_MAX + 1)}).status_code == 400
    assert c.post(url, json={"note": "  한국선급 몫만  "}).status_code == 200 and _wait(c, doc)["state"] == "done"
    data = sent[0].split("## 자료(JSON)")[1]
    assert '"request":"한국선급 몫만"' in data and '"materials"' not in data and "사람이 이번 작성에 대해 요청한 것" in sent[0]
    v = c.get(url).json()
    assert v["review"]["sees"] == sees and v["review"]["request"] == "한국선급 몫만" and not v["planned"]
    assert v["review"]["fed"] == {"places": len(PLACES), "formGuides": sum(1 for p in PLACES for g in p.get("guides") or () if g.get("src") != "user"), "userGuides": sum(1 for p in PLACES for g in p.get("guides") or () if g.get("src") == "user"), "request": True}
    assert c.post(url, json={"materials": [mid], "note": "한국선급 몫만"}).status_code == 200 and _wait(c, doc)["state"] == "done"
    v = c.get(url).json()["review"]
    assert c.get(url).json()["planned"] and v["summary"] == ANSWER["summary"] and v["sees"] == sees and v["places"]["h2"]["how"] == "정량 지표와 함께 3줄" and v["places"]["h2"]["use"] == "자료의 최종 목표 문단"


def test_plan_request_goes_only_with_materials():
    """「작성 계획에 줄 요청」(spec_양식작성 ② §5-1 ⓓ) — 자료가 있을 때(작성 계획)만 프롬프트 자료 planRequest 로 싣고, 양식 검토(자료 없음)에는 안 간다."""
    plan = form_review.payload([], {}, [], [], "자료 글", plan_request="2차년도 실적 위주로")
    review = form_review.payload([], {}, [], [], "", plan_request="2차년도 실적 위주로")
    assert plan["planRequest"] == "2차년도 실적 위주로" and "planRequest" not in review
    assert "planRequest" not in form_review.payload([], {}, [], [], "자료 글")
    assert "planRequest = **사람이 작성 계획에 대해 요청한 것**" in form_review.CONTRACT
