"""양식 작성 — 근거 잇기 · 물음의 시점 · 덮임(spec_양식작성 ② §5-12 — 2026-11-27 세 모델 합의안의 구현).
LLM 은 부르지 않는다(양식 검토 `llm.call` · 자리 턴 `doc_agent_api._turn` · 조정 호출 `doc_agent.ask` 를 가짜로)."""
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import agent_settings, doc_agent, doc_agent_api, form_review, guide_write, server, works
from app import form_review_api as R
from app import guide_write_api as GW
from app import material_index as MI

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
MD = """<!-- p.46 -->
# 3. 연구개발 내용

## 3-2. 한국선급(1차년도)

보호협조 시험 절차서(안) 검토 및 위험도 식별 8건.

<!-- p.88 -->
# 4. 차년도 계획

## 4-2. 한국선급(2차년도 계획)

실선 적용 안전성 평가 기준(안) 제정 및 검증 시험 12건.
"""


def P(i, text):
    return {"id": i, "type": "paragraph", "text": text}


BLOCKS = [P("h1", "1. 개요"), P("p1", ""), P("h2", "2. 당해연도(1차년도) 실적"), P("p2", ""), P("h3", "3. 차년도 계획"), P("p3", "")]
GRAPH = {"nodes": [{"role": "heading", "area": "body", "para": i, "depth": 1} for i in ("h1", "h2", "h3")]}
PLACES = guide_write.places(BLOCKS, GRAPH, {"heads": {}, "tables": {}})
IDS = [p["id"] for p in PLACES]


def _mat(text=MD, mid="m0000000a"):
    return {"id": mid, "name": "계획서.md", "text": text, "sha256": "x" * 8}


# ---- 순수: 근거 절 · 물음의 갈래 · 요청 글 · 이전 답 ---------------------------------------------------------------------

def test_check_keeps_only_known_evidence_and_question_kinds():
    refs = form_review.material_refs([_mat()])
    sec1, sec2 = [k for k, v in refs.items() if v["title"].startswith("3-2")][0], [k for k, v in refs.items() if v["title"].startswith("4-2")][0]
    ans = {"summary": "s", "places": [{"id": "h2", "how": "개조식", "needs": "", "use": "3-2 의 실적", "gap": "",
                                       "evidence": [{"sec": sec1, "quote": "보호협조 시험 절차서(안) 검토"}, {"sec": sec1, "quote": "겹침"}, {"sec": "m0000000a/s999", "quote": "없는 절"}, {"sec": "엉뚱", "quote": ""}]},
                                      {"id": "zz", "how": "", "needs": "", "use": "", "gap": "", "evidence": [{"sec": sec2, "quote": ""}]}],
           "questions": [{"kind": "scope", "text": "어느 기관의 몫입니까?", "why": "", "places": [], "choices": [], "suggest": "", "source": ""},
                         {"kind": "content", "text": "금액 단위는?", "why": "", "places": ["h2"], "choices": [], "suggest": "", "source": ""}], "topics": []}
    plan = form_review.check(ans, IDS, True, refs)
    assert plan["places"]["h2"]["evidence"] == [{"mat": "m0000000a", "sec": sec1.split("/")[1], "page": 46, "title": "3-2. 한국선급(1차년도)", "quote": "보호협조 시험 절차서(안) 검토"}]
    assert [q["kind"] for q in plan["questions"]] == ["scope", "content"] and "deferred" not in plan
    review = form_review.check(ans, IDS, False, refs)   # 자료 없이(양식 검토) — scope 물음만 · 근거 · 작성 계획 없음
    assert [q["text"] for q in review["questions"]] == ["어느 기관의 몫입니까?"] and review["deferred"] == 1 and review["questions"][0]["key"] == "q1"
    assert "evidence" not in review["places"]["h2"] and review["places"]["h2"]["use"] == ""
    assert "evidence" not in form_review.check(ans, IDS, True)["places"]["h2"]   # 절 색인을 안 준 호출은 근거를 남기지 않는다(전과 같은 꼴)
    cut = form_review.materials_marked([_mat(MD * 40)], limit=400)             # 분량을 넘어 잘린 자료 — 모델이 못 본 절은 근거로 받아 주지 않는다(astra R2)
    seen = form_review.material_refs([_mat(MD * 40)], cut)
    assert 0 < len(seen) < len(form_review.material_refs([_mat(MD * 40)])) and all(f"[[{k} |" in cut for k in seen)
    wrong = form_review.evidence_of([{"sec": sec1, "quote": "이 절에 없는 구절"}], refs)
    assert wrong == [{"mat": "m0000000a", "sec": sec1.split("/")[1], "page": 46, "title": "3-2. 한국선급(1차년도)", "quote": ""}]   # 절은 남기고 그 절에 없는 구절은 지운다
    assert {"kind", "text"} <= set(form_review.SCHEMA["properties"]["questions"]["items"]["properties"]) and "evidence" in form_review.SCHEMA["properties"]["places"]["items"]["properties"]


def test_materials_marked_puts_section_headers_and_cuts_within_limit():
    text = form_review.materials_marked([_mat()])
    assert text.startswith("[자료: 계획서.md (m0000000a)]") and "[[m0000000a/" in text and "| p.88 |" in text and "실선 적용" in text
    small = form_review.materials_marked([_mat(), _mat(MD * 30, "m0000000b")], limit=1500)
    assert len(small) <= 1500 and "(뒤는 잘림)" in small and "m0000000a/" in small   # 짧은 자료는 다 실리고 긴 자료가 잘린다
    assert form_review.materials_marked([]) == ""


def test_plan_text_puts_the_plan_before_the_direction_and_trims_direction_first():
    facts = [(f"물음 {k}", "답" * 250) for k in range(3)]   # 답 셋 ≈ 800자
    plan = {"facts": facts, "how": "방" * 300, "needs": "", "use": "3-2 절의 실적 문단", "gap": "정량 지표 없음", "evidence": [{"mat": "m0000000a", "sec": "s3", "page": 46}]}
    text = form_review.plan_text(plan)
    assert len(text) <= form_review.PLAN_MAX and "자료에서 쓸 것: 3-2 절의 실적 문단 / 자료에 없는 것(짓지 않습니다): 정량 지표 없음" in text and "m0000000a/s3(p.46)" in text
    assert text.index("사람이 정해 준 것") < text.index("작성 계획") and ("작성 방향" not in text or text.index("작성 계획") < text.index("작성 방향"))   # 넘치면 작성 방향이 줄거나 빠진다 — 계획은 남는다
    many = form_review.plan_text({**plan, "facts": [(f"물음 {k}", "답" * 300) for k in range(5)]})   # 답 다섯 — 그것만으로 한도를 넘는다: 작성 계획은 남기고 답을 줄이거나 뺀다(뺀 수를 적는다)
    assert len(many) <= form_review.PLAN_MAX and "자료에서 쓸 것: 3-2 절의 실적 문단" in many and "m0000000a/s3(p.46)" in many and "물음 0" in many
    short = form_review.plan_text({"facts": [], "how": "개조식 3줄", "use": "", "gap": "자료에 실적 없음", "evidence": []})
    assert form_review.NO_USE in short and "자료에 실적 없음" in short and short.endswith("개조식 3줄")   # 쓸 것이 비어도 없는 것은 싣는다
    assert form_review.plan_text({"facts": [], "how": "가", "use": "", "gap": "", "evidence": []}) == "양식 검토의 작성 방향(이 자리): 가"


def test_answers_reach_only_their_place_and_stale_answers_are_candidates():
    review = {"places": {}, "questions": [{"key": "q1", "text": "실적 건수?", "places": ["h2"]}, {"key": "q2", "text": "기관?", "places": []}], "materials": ["m0000000a"]}
    decided = [{"key": "q1", "q": "실적 건수?", "a": "12건", "places": ["h2"], "basis": ["m0000000a"]}, {"key": "q2", "q": "기관?", "a": "한국선급", "places": [], "basis": []}]
    assert form_review.answers_for(review, decided, "h2", IDS) == ["12건", "한국선급"] and form_review.answers_for(review, decided, "h3", IDS) == ["한국선급"]   # 다른 자리의 답은 안 간다(astra P1)
    assert form_review.mark_stale(decided, ["m0000000b"]) == 1 and decided[0]["stale"] is True and "stale" not in decided[1]   # 자료로 물은 답만 · 자료 없이 답한 것은 그대로
    assert form_review.mark_stale(decided, ["m0000000b"]) == 0
    assert [q["key"] for q in form_review.open_questions(review, decided)] == ["q1"] and form_review.prev_answer(review["questions"][0], decided)["a"] == "12건"
    assert form_review.answers_for(review, decided, "h2", IDS) == ["한국선급"] and "12건" not in form_review.plan_text(form_review.plan_for(review, decided, "h2", IDS))
    assert form_review.payload([], None, [], decided)["decided"] == [{"q": "기관?", "a": "한국선급"}]   # 이전 답은 LLM 에 「정한 것」 으로 안 간다(다시 물을 수 있게)
    old = [{"key": "", "q": "옛 물음", "a": "옛 답", "places": []}]   # basis 를 안 적은 옛 답 — 그대로 쓴다
    assert form_review.mark_stale(old, ["m0000000b"]) == 0


def test_answers_keep_their_own_scope_and_prompt_gets_only_usable_answers():
    """astra R2: 같은 글의 물음이 다른 자리로 다시 나와도 답의 범위가 조용히 바뀌지 않는다 · 새 자료의 계획은 옛 자료의 답을 「정한 것」 으로 받지 않는다."""
    a_only = [{"key": "q1", "q": "기관은?", "a": "가사", "places": ["h2"], "basis": []}]
    to_b = {"places": {}, "questions": [{"key": "q1", "text": "기관은?", "places": ["h3"]}], "materials": []}
    assert [q["key"] for q in form_review.open_questions(to_b, a_only)] == ["q1"] and form_review.prev_answer(to_b["questions"][0], a_only)["a"] == "가사"   # B 자리의 물음은 답하지 않은 것 — A 의 답은 후보로만
    assert form_review.answers_for(to_b, a_only, "h3", IDS) == [] and form_review.answers_for(to_b, a_only, "h2", IDS) == ["가사"]                 # 답은 답한 때의 자리에만
    wide = {"places": {}, "questions": [{"key": "q1", "text": "기관은?", "places": []}], "materials": []}
    assert form_review.open_questions(wide, a_only) and form_review.answers_for(wide, a_only, "h3", IDS) == []                                   # 문서 전체로 넓어진 물음 — A 의 답으로 다 답한 것이 아니다
    doc_wide = [{"key": "", "q": "기관은?", "a": "가사", "places": [], "basis": []}]
    assert not form_review.open_questions(to_b, doc_wide) and form_review.answers_for(to_b, doc_wide, "h1", IDS) == ["가사"]                    # 문서 전체 답은 어느 자리의 같은 물음도 덮는다
    decided = [{"q": "범위?", "a": "한국선급", "places": [], "basis": []}, {"q": "건수?", "a": "12건", "places": ["h2"], "basis": ["m0000000a"]}, {"q": "옛?", "a": "x", "places": [], "basis": ["m0000000a"], "stale": True}]
    assert [d["a"] for d in form_review.usable(decided, ["m0000000a"])] == ["한국선급", "12건"]
    assert [d["a"] for d in form_review.usable(decided, ["m0000000b"])] == ["한국선급"]      # 다른 자료의 계획 — 옛 자료로 물은 답은 호출 전에 뺀다
    assert [d["a"] for d in form_review.usable(decided, [])] == ["한국선급"]                 # 양식 검토(자료 없이) — 자료로 물은 답은 싣지 않는다
    assert not any(d.get("stale") for d in decided[:2])                                      # 사본으로 가린다 — 저장본의 표시는 계획이 끝난 뒤(mark_stale)
    same = {"summary": "", "places": [], "topics": [], "questions": [{"kind": "content", "text": "기준일은?", "why": "", "places": ["h2"], "choices": [], "suggest": "", "source": ""},
                                                                   {"kind": "content", "text": "기준일은?", "why": "", "places": ["h3"], "choices": [], "suggest": "", "source": ""}]}
    merged = form_review.check(same, IDS, True)["questions"]
    assert len(merged) == 1 and merged[0]["places"] == ["h2", "h3"]                          # 같은 글의 물음을 자리마다 냈으면 하나로 모으고 자리를 합친다(둘째를 버리지 않는다)


# ---- 순수: 근거의 자료 자리 · 대조 ---------------------------------------------------------------------------------------

def _ctx(**more):
    return {"mats": [_mat()], "evidence": [], "ctx": "", **more}


def test_evid_gives_location_and_flags_field_clash():
    at, evid, warn = doc_agent._evid(_ctx(), "보호협조 시험 절차서(안) 검토", True)
    assert evid == "match" and warn is None and (at["mat"], at["page"], at["title"], at["hits"]) == ("m0000000a", 46, "3-2. 한국선급(1차년도)", 1)
    assert doc_agent._evid(_ctx(), "없는 구절", False) == (None, "none", None)
    assert doc_agent._evid(_ctx(), "자료 글에 없는 구절", True) == (None, "match", None)   # 범위 없는 턴(에이전트 보기) — 요청 · 고른 글의 구절도 근거다: 자리 없이
    # 자리 턴(서버가 범위를 건 턴) — 보낸 자료 글에 없는 구절(절 머리 줄 · 목차 · 쪽 표시 · 요청 글)은 근거가 아니다(astra R2 P1: 머리 줄의 쪽수 46 이 값으로 골라졌다)
    for quote in ("[[m0000000a/s2 | p.46 | 3. 연구개발 내용 › 3-2. 한국선급(1차년도)]]", "m0000000a/s4 | p.88 | 4. 차년도 계획 (10자)", "<!-- p.46 -->", "작성 지침의 예시 문장"):
        assert doc_agent._evid(_ctx(scope={}), quote, True) == (None, "none", doc_agent.NOT_MATERIAL), quote
    # 근거 절만 실은 턴 — 싣지 않은 절의 구절도 근거가 아니다(에이전트가 본 글이 아니다)
    first = MI.sections(MD)[1]
    only = {"m0000000a": [(first["start"], first["end"])]}
    assert doc_agent._evid(_ctx(scope={}, spans=only), "보호협조 시험 절차서(안) 검토", True)[1] == "match"
    assert doc_agent._evid(_ctx(scope={}, spans=only), "검증 시험 12건", True) == (None, "none", doc_agent.NOT_MATERIAL)
    # 차년도는 가까운 글부터 — 제목에 없어도 근거 구절이 다른 차년도를 적었으면 어긋난다
    plain = {"id": "m0000000c", "name": "실적.md", "text": "# 시험 실적\n\n2차년도 검증 완료 12건\n"}
    assert doc_agent._evid({"mats": [plain], "evidence": [], "ctx": "1차년도 실적"}, "2차년도 검증 완료 12건", True)[1] == "field"
    at, evid, warn = doc_agent._evid(_ctx(ctx="2. 당해연도(1차년도) 실적"), "검증 시험 12건", True)   # 근거는 2차년도 계획 절 · 자리는 1차년도
    assert evid == "field" and doc_agent.FIELD_OFF in warn and "차년도 — 자리 1 · 근거 2" in warn and at["page"] == 88
    at, evid, _ = doc_agent._evid(_ctx(ctx="2. 당해연도(1차년도) 실적"), "한국선급", True)            # 같은 구절이 두 절에 — 자리와 어긋나지 않는 절을 고르고 여러 곳임을 알린다
    assert evid == "multi" and at["hits"] == 2 and at["page"] == 46
    later = MI.sections(MD)[-1]["id"]
    at, evid, _ = doc_agent._evid(_ctx(evidence=[{"mat": "m0000000a", "sec": later}]), "한국선급", True)   # 작성 계획이 고른 절이 먼저
    assert at["sec"] == later and evid == "multi"


def test_applied_sources_maps_paragraphs_and_cells():
    at = {"mat": "m0000000a", "name": "계획서.md", "start": 5, "end": 9, "sec": "s2", "page": 46, "title": "절", "hits": 1, "path": []}
    fill = {"type": "fill", "view": {"lines": [{"para": "p1", "source": "가", "at": at}, {"para": "p2", "source": "나", "at": None}]}}
    assert doc_agent.applied_sources(fill, lined=["p1", "p2"]) == [{"para": "p1", "mat": "m0000000a", "name": "계획서.md", "start": 5, "end": 9, "sec": "s2", "page": 46, "title": "절", "hits": 1, "quote": "가"}]
    write = {"type": "write", "view": {"lines": [{"source": "가", "at": at}, {"source": "나", "at": at}]}}
    assert [x["para"] for x in doc_agent.applied_sources(write, written=["n1", "n2"])] == ["n1", "n2"] and doc_agent.applied_sources(write, written=["n1"]) == []   # 줄 수와 문단 수가 다르면 짝짓지 않는다
    tf = {"type": "tableFill", "view": {"table": "t8", "fills": [{"cell": "c1", "source": "가"}, {"cell": "c2", "source": "나"}], "at": {"c1": at}}}
    assert doc_agent.applied_sources(tf, cells=["c1", "c2"]) == [{"cell": "c1", "table": "t8", "mat": "m0000000a", "name": "계획서.md", "start": 5, "end": 9, "sec": "s2", "page": 46, "title": "절", "hits": 1, "quote": "가"}]


# ---- 끝점 --------------------------------------------------------------------------------------------------------------

@pytest.fixture
def c(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.setenv("NFM_AGENTS", "off")
    agent_settings._MEMORY.update(version=0, agents={})
    doc_agent._MEMORY.clear()
    server.DOCS.clear()
    for m in (R._RUNS, R._MEM, GW._RUNS):
        m.clear()
    monkeypatch.setattr(GW, "_places", lambda s: (PLACES, 0))
    monkeypatch.setattr(R.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(GW.llm, "status", lambda: {"available": True})
    yield TestClient(server.app)
    server.DOCS.clear()
    for m in (R._RUNS, R._MEM, GW._RUNS):
        m.clear()


def _doc(c):
    return c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]


def _review_done(c, doc):
    for _ in range(200):
        run = c.get(f"/api/docs/{doc}/form-review").json()["run"]
        if run and run["state"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("양식 검토가 끝나지 않음")


def _run_done(c, doc):
    for _ in range(200):
        run = c.get(f"/api/docs/{doc}/guide-write/run").json()["run"]
        if run and run["state"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("지침 작성이 끝나지 않음")


def _answer(sec=""):
    q = lambda kind, text, places: {"kind": kind, "text": text, "why": "", "places": places, "choices": [], "suggest": "", "source": ""}  # noqa: E731
    return {"summary": "s", "sees": {"write": "", "guides": "", "asks": ""}, "topics": [],
            "places": [{"id": "h2", "how": "개조식", "needs": "실적", "use": "3-2 절" if sec else "", "gap": "", "evidence": [{"sec": sec, "quote": "보호협조"}] if sec else []},
                       {"id": "h3", "how": "개조식", "needs": "계획", "use": "4-2 절" if sec else "", "gap": "", "evidence": []}],
            "questions": [q("scope", "어느 기관의 몫입니까?", []), q("content", "실적 건수의 기준일은?", ["h2"])]}


def test_review_is_one_model_by_default_and_plan_keeps_evidence_and_basis(c, monkeypatch):
    doc = _doc(c)
    wid = server._sess(doc).id
    calls, state = [], {"sec": ""}

    def call(schema, content, what, **kw):
        calls.append((what, kw.get("model"), content))
        return {"data": _answer(state["sec"]), "backend": "fake", "ms": 5, "costUsd": 0.25, "model": kw.get("model")}
    monkeypatch.setattr(R.llm, "call", call)
    # ① 양식 검토 — 기본 한 모델 · scope 물음만
    assert c.post(f"/api/docs/{doc}/form-review", json={"duo": "yes"}).status_code == 400
    assert c.post(f"/api/docs/{doc}/form-review", json={}).status_code == 200 and _review_done(c, doc)["state"] == "done"
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert len(calls) == 1 and v["opts"] == {"duo": False} and v["llm2"] is True and v["review"]["call"]["calls"] == 1 and v["review"]["duo"] is False
    assert [q["text"] for q in v["review"]["questions"]] == ["어느 기관의 몫입니까?"] and v["review"]["deferred"] == 1 and v["held"] == {i: ["어느 기관의 몫입니까?"] for i in IDS}
    v = c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"key": "q1", "a": "한국선급"}]}).json()
    assert v["decided"][0]["basis"] == [] and v["held"] == {}
    # ② 작성 계획 — 두 모델로 협의(옵션): 호출 셋 · 자료 글에 절 머리 줄 · 근거 절 · 자료 지문
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "계획서.md", "text": MD}).json()["id"]
    state["sec"] = f"{mid}/" + next(s["id"] for s in MI.sections(MD.strip()) if s["title"].startswith("3-2"))
    calls.clear()
    assert c.post(f"/api/docs/{doc}/form-review", json={"materials": [mid], "duo": True}).status_code == 200 and _review_done(c, doc)["state"] == "done"
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert [w for w, _, _ in calls] == ["form-review", "form-review", "form-review#consult"] and v["opts"] == {"duo": True} and v["review"]["duo"] is True
    assert v["review"]["call"]["calls"] == 3 and v["review"]["call"]["costUsd"] == 0.75 and v["review"]["call"]["wallMs"] >= 0     # 모든 호출의 합(전에는 협의 호출 하나만)
    assert f"[[{mid}/" in calls[0][2] and v["review"]["places"]["h2"]["evidence"][0]["page"] == 46 and v["review"]["matSigs"] == {mid: R.doc_agent.Store(wid).material(mid)["sha256"]}
    assert [q["kind"] for q in v["review"]["questions"]] == ["content"] or [q["kind"] for q in v["review"]["questions"]] == ["scope", "content"]
    assert v["held"] == {"h2": ["실적 건수의 기준일은?"]} and v["open"] and "h3" not in v["held"]                                # 자리에 닿는 물음은 그 자리만 막는다
    key = next(q["key"] for q in v["review"]["questions"] if q["kind"] == "content")
    v = c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"key": key, "a": "2025-12-31"}]}).json()
    assert [d["basis"] for d in v["decided"]] == [[], [mid]] and v["held"] == {}
    # ③ 다른 자료로 다시 계획 — 자료로 물은 답은 「이전 답」(쓰지 않고 후보로만) · 자료 없이 답한 것은 그대로 · 옵션은 기억된다
    mid2 = c.post(f"/api/docs/{doc}/agent/material", json={"name": "다른.md", "text": "# 다른 자료\n\n다른 글"}).json()["id"]
    state["sec"] = ""
    calls.clear()
    assert c.post(f"/api/docs/{doc}/form-review", json={"materials": [mid2]}).status_code == 200 and _review_done(c, doc)["state"] == "done"
    v = c.get(f"/api/docs/{doc}/form-review").json()
    assert len(calls) == 3 and [bool(d.get("stale")) for d in v["decided"]] == [False, True]
    again = next(q["key"] for q in v["review"]["questions"] if q["kind"] == "content")
    assert v["prev"] == {again: "2025-12-31"} and again in v["open"] and v["held"] == {"h2": ["실적 건수의 기준일은?"]}
    v = c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"key": again, "a": "2025-12-31"}]}).json()             # 「그대로 씀」 = 같은 답을 다시 저장
    assert v["prev"] == {} and [bool(d.get("stale")) for d in v["decided"]] == [False, False] and v["decided"][-1]["basis"] == [mid2]


def test_decided_overflow_drops_stale_answers_first(c, monkeypatch):
    doc = _doc(c)
    wid = server._sess(doc).id
    stale = [{"key": "", "q": f"옛 물음 {k}", "a": "옛 답", "places": [], "at": k, "basis": ["m0000000a"], "stale": True} for k in range(R.DECIDED_MAX)]
    R._save(wid, {"review": {"summary": "", "places": {}, "questions": [], "topics": [], "materials": []}, "decided": stale})
    v = c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"q": "새 물음", "a": "새 답"}]})
    assert v.status_code == 200 and len(v.json()["decided"]) == R.DECIDED_MAX and v.json()["decided"][-1]["q"] == "새 물음" and v.json()["decided"][0]["q"] == "옛 물음 1"


def _planned(doc, mid, decided=(), questions=(), places=None):
    wid = server._sess(doc).id
    mat = doc_agent.Store(wid).material(mid)
    R._save(wid, {"review": {"summary": "", "places": places or {}, "questions": list(questions), "topics": [], "materials": [mid], "matSigs": {mid: mat["sha256"]}, "secVer": MI.VERSION,
                             "sig": form_review.sig(PLACES), "sigs": form_review.sigs(PLACES)}, "decided": list(decided)})
    return wid


def test_run_holds_only_asked_places_and_passes_per_place_answers_and_evidence(c, monkeypatch):
    doc = _doc(c)
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "계획서.md", "text": MD}).json()["id"]
    sec = next(s["id"] for s in MI.sections(MD.strip()) if s["title"].startswith("3-2"))
    ev = [{"mat": mid, "sec": sec, "page": 46, "title": "3-2", "quote": "보호협조"}]
    wid = _planned(doc, mid,
                   decided=[{"key": "q1", "q": "h2 의 건수?", "a": "8건", "places": ["h2"]}, {"key": "", "q": "기관", "a": "한국선급", "places": []}],
                   questions=[{"key": "q1", "kind": "content", "text": "h2 의 건수?", "places": ["h2"]}, {"key": "q2", "kind": "content", "text": "h3 의 기준?", "places": ["h3"]}],
                   places={"h1": {"how": "", "needs": "", "use": "개요 절", "gap": ""}, "h2": {"how": "", "needs": "", "use": "3-2 절", "gap": "", "evidence": ev}, "h3": {"how": "", "needs": "", "use": "", "gap": "없음"}})
    seen = {}

    def turn(doc_id, body, scope=None):
        seen[body["selection"]["cursor"]] = (body, scope)
        return {"turn": {"id": "t" + body["selection"]["cursor"], "reply": "쓸 내용이 없습니다", "proposals": [], "dropped": [], "narrowed": [f"{mid}/{sec}"] if (scope or {}).get("evidence") else []}}
    monkeypatch.setattr(doc_agent_api, "_turn", turn, raising=False)
    url = f"/api/docs/{doc}/guide-write/run"
    r = c.post(url, json={"places": ["h3"], "materials": [mid]})
    assert r.status_code == 409 and "확인할 것 1개" in r.json()["detail"]                                 # 고른 자리가 모두 막혔을 때만 409
    assert c.post(url, json={"places": ["h1"], "materials": [mid], "wide": "h1"}).status_code == 400
    r = c.post(url, json={"places": IDS, "materials": [mid]})
    assert r.status_code == 200 and r.json()["run"]["held"] == {"h3": ["h3 의 기준?"]} and "evidence" not in r.json()["run"] and "decided" not in r.json()["run"]
    by = {i["id"]: i for i in _run_done(c, doc)["items"]}
    assert (by["h3"]["state"], by["h3"]["why"], by["h3"]["asks"]) == ("none", "ask", 1) and "h3" not in seen                     # 막힌 자리는 LLM 을 부르지 않는다
    assert seen["h2"][1]["decided"] == ["8건", "한국선급"] and seen["h1"][1]["decided"] == ["한국선급"]                         # 그 자리에 닿는 답만(astra P1)
    assert seen["h2"][1]["evidence"] == ev and seen["h1"][1]["evidence"] == [] and "당해연도(1차년도) 실적" in seen["h2"][1]["ctx"]
    assert (by["h1"]["why"], by["h2"]["why"], by["h2"]["narrowed"], by["h1"]["narrowed"]) == ("noaction", "noaction", 1, 0)     # 계획이 쓸 것을 적은 자리의 「행동 없음」 — 자료에 없음으로 단정하지 않는다
    # 실행의 상태는 작업 폴더에 — 메모리를 비워도(서버를 다시 켠 것처럼) 읽힌다
    GW._RUNS.clear()
    kept = c.get(url).json()["run"]
    assert kept["state"] == "done" and {i["id"]: i.get("why") for i in kept["items"]} == {"h1": "noaction", "h2": "noaction", "h3": "ask"}
    path = works.folder(wid) / GW.RUN_FILE
    data = works._read_json(path)
    works._write_json(path, {**data, "state": "running", "items": [{**data["items"][0], "state": "running"}, *data["items"][1:]]})
    cut = c.get(url).json()["run"]
    assert cut["state"] == "cut" and cut["items"][0]["state"] == "cut"                                                         # 돌던 실행은 「끊김」
    # 「자료 전체로 다시 받기」 — 그 자리는 근거 절로 좁히지 않는다
    seen.clear()
    assert c.post(url, json={"places": ["h2"], "materials": [mid], "wide": ["h2"]}).status_code == 200
    _run_done(c, doc)
    assert "evidence" not in seen["h2"][1]
    # 자료 글이 계획 때와 다르면 근거 절을 쓰지 않는다
    st = R.load(wid)
    R._save(wid, {"review": {**st["review"], "matSigs": {mid: "다른 지문"}}, "decided": st["decided"]})
    seen.clear()
    assert c.post(url, json={"places": ["h2"], "materials": [mid]}).status_code == 200
    _run_done(c, doc)
    assert seen["h2"][1]["evidence"] == []


def test_held_table_is_not_filled_through_its_heading(c, monkeypatch):
    """astra R2 P1: 표 자리에 닿는 물음에 답하지 않았으면 그 표는 윗 헤딩의 턴에서도 채우지 않는다(전에는 표 자리만 막고 헤딩 턴의 표 채우기로 초안이 나갔다)."""
    T = {"id": "t1", "type": "table", "cells": [{"id": "t1k0", "row": 0, "col": 0, "blocks": [P("t1c0", "구분")]}, {"id": "t1k1", "row": 1, "col": 0, "blocks": [P("t1c1", "")]}]}
    blocks = [P("h1", "1. 실적"), P("p1", ""), T, P("h2", "2. 계획"), P("p2", "")]
    graph = {"nodes": [{"role": "heading", "area": "body", "para": i, "depth": 1} for i in ("h1", "h2")]}
    places = guide_write.places(blocks, graph, {"heads": {}, "tables": {"t1": [{"src": "doc", "kind": "작성 요령", "text": "실적 건수를 적는다"}]}})
    assert [(p["id"], p["kind"]) for p in places] == [("h1", "head"), ("t1", "table"), ("h2", "head")] and places[0]["tables"] == ["t1"]
    monkeypatch.setattr(GW, "_places", lambda s: (places, 0))
    doc = _doc(c)
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "계획서.md", "text": MD}).json()["id"]
    wid = server._sess(doc).id
    mat = doc_agent.Store(wid).material(mid)
    R._save(wid, {"review": {"summary": "", "places": {}, "questions": [{"key": "q1", "kind": "content", "text": "실적의 기준일은?", "places": ["t1"]}], "topics": [], "materials": [mid], "matSigs": {mid: mat["sha256"]},
                             "sig": form_review.sig(places), "sigs": form_review.sigs(places)}, "decided": []})
    seen = {}
    monkeypatch.setattr(doc_agent_api, "_turn", lambda doc_id, body, scope=None: seen.update({body["selection"]["cursor"]: scope}) or {"turn": {"id": "t9", "reply": "", "proposals": [], "dropped": []}}, raising=False)
    assert c.post(f"/api/docs/{doc}/guide-write/run", json={"places": ["h1", "h2"], "materials": [mid]}).status_code == 200   # 표 자리는 고르지 않았다 — 그래도 헤딩 턴이 그 표를 채우지 않는다
    _run_done(c, doc)
    assert seen["h1"]["tables"] == set() and seen["h1"]["place"] == "h1" and len(seen["h1"]["planSig"]) == 16 and seen["h2"]["tables"] == set()
    c.put(f"/api/docs/{doc}/form-review/answers", json={"answers": [{"key": "q1", "a": "2025-12-31"}]})
    seen.clear()
    assert c.post(f"/api/docs/{doc}/guide-write/run", json={"places": ["h1"], "materials": [mid]}).status_code == 200
    _run_done(c, doc)
    assert seen["h1"]["tables"] == {"t1"}   # 답한 뒤에는 헤딩 턴이 그 표도 채울 수 있다


def test_coverage_counts_from_turn_records(c, monkeypatch):
    doc = _doc(c)
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "계획서.md", "text": MD}).json()["id"]
    wid = _planned(doc, mid, places={"h1": {"how": "", "needs": "", "use": "개요", "gap": ""}, "h2": {"how": "", "needs": "", "use": "3-2 절", "gap": "지표 없음", "evidence": [{"mat": mid, "sec": "s2"}]},
                                     "h3": {"how": "", "needs": "", "use": "", "gap": "자료에 없음"}})
    store = doc_agent.Store(wid)

    def turn(tid, pid, props, text="[지침 작성] 헤딩", dropped=()):
        store.save_turn({"id": tid, "at": time.time(), "rev": 0, "request": {"text": text, "materials": [mid], "selection": {"paras": [], "table": None, "range": None, "cursor": pid}, "styles": {}},
                         "reply": "답", "notes": [], "error": None, "proposals": props, "dropped": list(dropped), "prompt": {}, "response": None, "call": {}, "fills": []})
    from app.headings import iter_blocks
    s = server._sess(doc)
    a, b, x = [(blk["id"], blk.get("text") or "") for blk in iter_blocks(s.doc.blocks()) if blk.get("type") == "paragraph"][:3]   # 문서에 실제로 있는 문단 셋 — 반영한 줄은 「지금 글이 넣은 글 그대로」 일 때만 센다
    now = {a[0]: a[1], b[0]: b[1], x[0]: x[1] + " (그 뒤 고침)"}   # 셋째 줄은 넣은 글과 지금 글이 다르다(실행 취소 · 그 뒤 고침)

    def fill(state, picked, applied=()):
        return {"id": "p1", "type": "fill", "state": state, "preselect": bool(picked), "view": {"lines": [{"para": a[0]}, {"para": b[0]}, {"para": x[0]}], "picked": list(picked)},
                "op": {"box": None, "lines": [{"para": i, "text": now[i]} for i in (a[0], b[0], x[0])]},
                **({"applied": {"filledLines": {"paras": list(applied)}, "sources": [{"para": i, "mat": mid, "start": 1, "end": 3, "page": 46, "quote": "가"} for i in applied]}} if applied else {})}
    turn("t0000001", "h2", [fill("open", [a[0]])])                    # 옛 턴 — 열린 카드 · 처음 고른 줄은 같은 자리의 뒤 턴이 덮는다
    turn("t0000002", "h2", [fill("applied", [a[0], b[0]], [a[0], b[0], x[0]])])   # 셋을 반영했지만 셋째는 그 뒤 글이 달라졌다 — 둘만 센다
    turn("t0000003", "h1", [fill("open", [a[0]])])
    turn("t0000004", "h3", [], dropped=[])
    turn("t0000005", "h1", [fill("open", [a[0], b[0], x[0]])], text="직접 요청")   # 지침 작성의 턴이 아니다 — 세지 않는다
    store.save_turn({"id": "t0000006", "at": time.time(), "rev": 0, "narrowed": [], "request": {"text": "[지침 작성] 사람이 직접 친 글", "materials": [], "selection": {"paras": [], "table": None, "range": None, "cursor": "h3"}, "styles": {}},
                     "reply": "", "notes": [], "error": None, "proposals": [fill("open", [a[0]])], "dropped": [], "prompt": {}, "response": None, "call": {}, "fills": []})   # 새 꼴의 턴인데 자리 표시(place)가 없다 = 에이전트 보기에서 직접 한 요청 — 머리 글이 같아도 세지 않는다
    got = c.get(f"/api/docs/{doc}/guide-write/coverage").json()
    by = {r["id"]: r for r in got["rows"]}
    assert (by["h2"]["turn"], by["h2"]["lines"], by["h2"]["applied"], by["h2"]["left"], by["h2"]["picked"], by["h2"]["evidence"]) == ("t0000002", 3, 2, 1, 0, 1)
    assert (by["h1"]["turn"], by["h1"]["picked"], by["h1"]["left"], by["h1"]["applied"], by["h1"]["old"]) == ("t0000003", 1, 2, 0, False)
    assert (by["h3"]["why"], by["h3"]["cards"], by["h3"]["use"], by["h3"]["gap"], by["h3"]["turn"]) == ("nomat", 0, False, True, "t0000004")
    assert got["counts"] == {"places": 3, "planned": 2, "drafted": 2, "applied": 1, "open": 1, "openLines": 1, "left": 2, "leftLines": 3, "appliedLines": 2, "none": {"nomat": 1}, "old": 0, "idle": 0, "ask": 0}
    src = c.get(f"/api/docs/{doc}/guide-write/sources").json()
    assert set(src["paras"]) == {a[0], b[0]} and src["paras"][a[0]]["turn"] == "t0000002" and src["paras"][a[0]]["page"] == 46   # 글이 달라진 줄의 근거는 보이지 않는다
    # 이전 계획의 초안 — 그 턴을 받은 뒤 그 자리에 닿는 답이 바뀌었다(턴에 적어 둔 지문과 다름): 「모두 반영」 에 넣지 않게 처음 고른 줄을 0 으로 · 남은 줄로 센다
    st = R.load(wid)
    store.save_turn({"id": "t0000007", "at": time.time(), "rev": 0, "narrowed": [], "place": "h1", "planSig": R.plan_sig(st, "h1", IDS), "request": {"text": "[지침 작성] 헤딩", "materials": [mid], "selection": {"paras": [], "table": None, "range": None, "cursor": "h1"}, "styles": {}},
                     "reply": "", "notes": [], "error": None, "proposals": [fill("open", [a[0]])], "dropped": [], "prompt": {}, "response": None, "call": {}, "fills": []})
    row = {r["id"]: r for r in c.get(f"/api/docs/{doc}/guide-write/coverage").json()["rows"]}["h1"]
    assert (row["turn"], row["picked"], row["old"]) == ("t0000007", 1, False)
    R._save(wid, {"review": st["review"], "decided": [{"key": "", "q": "기관은?", "a": "다른 기관", "places": [], "basis": []}]})
    got = c.get(f"/api/docs/{doc}/guide-write/coverage").json()
    row = {r["id"]: r for r in got["rows"]}["h1"]
    assert (row["picked"], row["left"], row["old"]) == (0, 3, True) and got["counts"]["old"] == 1 and got["counts"]["open"] == 0
    at = MI.locate("위험도 식별", [{"id": mid, "name": "", "text": MD.strip()}])
    ex = c.get(f"/api/docs/{doc}/agent/material/{mid}/at", params={"start": at["start"], "end": at["end"]}).json()
    assert ex["hit"] == "위험도 식별" and ex["sec"]["page"] == 46 and ex["sec"]["title"] == "3-2. 한국선급(1차년도)" and "보호협조" in ex["before"]
    assert c.get(f"/api/docs/{doc}/agent/material/m00000000/at").status_code == 404


def test_turn_sends_only_evidence_sections_and_table_place_skips_the_coordinating_call(c, monkeypatch):
    doc = _doc(c)
    mid = c.post(f"/api/docs/{doc}/agent/material", json={"name": "계획서.md", "text": MD}).json()["id"]
    sec = next(s["id"] for s in MI.sections(MD.strip()) if s["title"].startswith("3-2"))
    monkeypatch.setattr(doc_agent_api.llm, "status", lambda: {"available": True})
    monkeypatch.setattr(doc_agent_api, "_listing", lambda: [])
    seen = []

    def ask(data, guide="", job="", **kw):
        seen.append(data)
        return {"data": {"reply": "없음", "actions": []}, "prompt": "", "contract": "", "response": {}, "call": {"backend": "api", "model": "m", "effort": None, "ms": 1, "costUsd": 0.0, "error": None}}
    monkeypatch.setattr(doc_agent, "ask", ask)
    body = {"text": "[지침 작성] 시험", "materials": [mid], "selection": {"paras": [], "table": None, "range": None, "cursor": None}}
    t = doc_agent_api._turn(doc, body, scope={"types": {"write"}, "paras": set(), "tables": set(), "decided": [], "uploaded": None, "evidence": [{"mat": mid, "sec": sec}], "ctx": "1차년도 실적"})["turn"]
    text = seen[-1]["materials"][0]["text"]
    assert f"{mid}/{sec}" in t["narrowed"] and len(t["narrowed"]) == 3   # 실제로 실은 절 = 근거 절 + 앞뒤 하나씩
    assert MI.NARROW_HEAD in text and "보호협조 시험 절차서" in text and "실선 적용" not in text.split(MI.NARROW_TOC)[0] and "4-2. 한국선급(2차년도 계획)" in text
    t = doc_agent_api._turn(doc, body, scope={"types": {"write"}, "paras": set(), "tables": set(), "decided": [], "uploaded": None, "evidence": [{"mat": mid, "sec": "s999"}]})["turn"]
    assert t["narrowed"] == [] and seen[-1]["materials"][0]["text"] == MD.strip()                                  # 아는 근거 절이 없으면 자료 전체
    # 표 자리 — 조정 호출 없이 표 채우기로 곧장
    seen.clear()
    filled = []
    monkeypatch.setattr(doc_agent_api, "_fill_gather", lambda s, tid, rng, tb, allowed=None: {"table": tid, "error": "가짜 — 여기까지 왔다"} if not filled.append(tid) else None)
    t = doc_agent_api._turn(doc, {**body, "selection": {"paras": [], "table": "t8", "range": None, "cursor": "t8"}}, scope={"types": {"tableFill"}, "paras": set(), "tables": {"t8"}, "decided": [], "uploaded": None})["turn"]
    assert seen == [] and filled == ["t8"] and t["call"]["skipped"] is True and t["calls"] == 0 and t["reply"] == "가짜 — 여기까지 왔다" and t["dropped"][0]["type"] == "tableFill"
