"""양식 작성 04의 실제 HTTP 경로와 모델 입력·자리별 지침의 수명을 검증한다."""
import copy
import io
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import form_example_evidence, form_review, guide_write, guide_write_api, server
from app import form_themes as T
from app import writing_guidance as W
from app import writing_guidance_api as API
from tests.test_guide_write import BLOCKS, GRAPH, IX, SMALL


@pytest.fixture(autouse=True)
def one_model():
    """이 파일의 시험들은 호출 하나하나의 차례 · 입력을 본다 — 작성 지침 보완을 「한 모델만」 으로 두고 돈다(에이전트 설정은 conftest 의 임시 파일).
    두 모델(기본 — LLM1 · LLM2 따로 + 협의)은 test_two_models_judge_separately_then_consult_and_one_model_setting 이 본다."""
    from app import agent_settings
    agent_settings.save("writing_guidance", {"models": [W.MODEL]})


def test_card_guidance_matches_the_current_llm_prompt(monkeypatch, tmp_path):
    client = TestClient(server.app)
    guide = tmp_path / "writing_guidance.md"
    monkeypatch.setenv("NFM_MERGE_GUIDES", str(tmp_path))
    for criterion in ["각 표의 행과 열을 대조한다.", "각주에서 단위의 예외를 찾는다.", ""]:
        guide.write_text(f"# 작성 지침 보완\n\n{criterion}", encoding="utf-8")
        view = client.get("/api/agents/writing_guidance")
        assert view.status_code == 200
        parts = view.json()["prompt"]
        contract = next(p["text"] for p in parts if p["kind"] == "contract")
        shown = next(p["text"] for p in parts if p["kind"] == "merge" and p["name"] == W.GUIDE)
        prompt = W.prompt({}, None)
        assert contract == W.CONTRACT and prompt.startswith(contract)
        assert shown == criterion
        if criterion:
            assert shown in prompt
        else:
            assert "## 판단 지침" not in prompt


def test_evidence_budget_keeps_all_sources_and_maps_the_image_order(monkeypatch):
    def ref(name, text, images):
        return {"name": name, "text": text, "images": [{"media": "image/png", "data": b"i", "label": label} for label in images]}

    monkeypatch.setattr(W, "TEXT_BUDGET", 20)
    monkeypatch.setattr(W, "IMAGE_LIMIT", 2)
    sources, images = W.pack([ref("첫째", "a" * 80, ["2쪽", "8쪽"]), ref("둘째", "짧은 본보기", ["1쪽"])])
    assert len(images) == 2 and sources[0]["cut"] and not sources[1]["cut"]
    assert sources[0]["imageNumbers"] == [{"local": 1, "attached": 1, "label": "2쪽"}]
    assert sources[1]["imageNumbers"] == [{"local": 1, "attached": 2, "label": "1쪽"}]
    assert len(sources[0]["text"]) + len(sources[1]["text"]) <= 20 and sources[1]["text"] == "짧은 본보기"


def test_04_reads_images_and_attached_form_persists_and_invalidates(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_WORKS", str(tmp_path))
    client = TestClient(server.app)
    doc = client.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    path = f"/api/docs/{doc}"
    ps = guide_write.places(BLOCKS, GRAPH, IX)
    monkeypatch.setattr(guide_write_api, "_base_places", lambda s: (copy.deepcopy(ps), s.rev))
    monkeypatch.setattr(API.llm, "status", lambda: {"available": True})
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, format="PNG")
    monkeypatch.setattr(form_example_evidence, "evidence", lambda *args: [
        {"id": "t20", "name": "작성 예시", "text": "성과 캡션", "images": [{"media": "image/png", "data": buf.getvalue()}]}])
    ep = path + "/writing-guidance"
    refs = path + "/form-examples"
    a = client.post(refs, files={"file": ("별지.txt", "단위는 천원, 한 줄에 한 항목".encode())})
    assert a.status_code == 200
    assert client.post(refs, files={"file": ("별지.txt", "이름이 같은 다른 작성 예시".encode())}).status_code == 200
    calls = []
    stop, resume = threading.Event(), threading.Event()

    def call(schema, content, what, **kw):
        data = json.loads(content.split("## 분석할 자료\n")[-1])
        calls.append((data, kw))
        assert what == "writing-guidance" and schema == W.SCHEMA
        if "recheck" in data:
            assert [p["id"] for p in data["places"]] == ["h1"] and "attached" in data["recheck"]["h1"]
            return {"data": {"decisions": [{"place": "h1", "status": "insufficient", "reason": "입력된 그림과 이 절의 관계가 불분명함", "rules": []}]}}
        if len(calls) > 1:
            stop.set()
            assert resume.wait(timeout=3)
        decisions = [{"place": p["id"], "status": "not_applicable", "reason": "고정된 제목이며 별도의 작성 방법이 없음", "rules": []}
                     for p in data["places"] if p["id"] not in ("h1", "h2")]
        decisions.append({"place": "h2", "status": "apply", "reason": "성과 항목의 그림과 단위 지시를 적용한다. 옛 견본의 백만원 단위는 제외한다.",
                          "rules": [{"instruction": "성과 그림 아래에 캡션을 넣고 설명한다", "basis": "example",
                                     "evidence": [{"source": "ref1", "image": 1, "detail": "그림 바로 아래의 캡션"}]},
                                    {"instruction": "천원 단위로 표시한다", "basis": "explicit",
                                     "evidence": [{"source": "ref2", "image": 0, "detail": "단위는 천원"}]}]})
        decisions.append({"place": "h1", "status": "apply", "reason": "예시 그림에서 보임",
                          "rules": [{"instruction": "캡션을 붙인다", "basis": "example",
                                     "evidence": [{"source": "ref2", "image": 1, "detail": "다른 출처의 그림을 잘못 지시"}]}]})
        return {"data": {"decisions": decisions}}
    monkeypatch.setattr(API.llm, "call", call)

    def watch():
        for _ in range(200):
            state = client.get(ep).json()
            if state["run"] and state["run"]["state"] != "running":
                return state
            time.sleep(0.01)
        raise AssertionError("작성 지침 보완이 끝나지 않았습니다")

    assert client.get(ep).json()["ready"] is False and client.post(ep).status_code == 200
    done = watch()
    assert done["ready"] and done["audited"] and done["count"] == 1 and done["images"] == 1
    assert done["judgmentCounts"] == {"apply": 1, "insufficient": 1, "not_applicable": len(ps) - 2}
    duplicates = [r for r in done["sourceDetails"] if r["name"].startswith("별지.txt")]
    assert [(r["name"], r["citedPlaces"]) for r in duplicates] == [("별지.txt [ref2]", 1), ("별지.txt [ref3]", 0)]
    data, kw = calls[0]
    assert kw["images"][0]["data"] == buf.getvalue() and "성과 캡션" in data["references"][0]["text"]
    assert "천원" in data["references"][1]["text"] and "materials" not in data
    path_on_disk = tmp_path / doc / API.FILE
    record = json.loads(path_on_disk.read_text(encoding="utf-8"))
    assert len(record["judgments"]) == len(ps)
    shown = client.get(path + "/guide-write").json()["places"]
    p = next(x for x in shown if x["id"] == "h2")
    assert any(g["src"] == "llm" and "별지.txt [ref2]" in g["sources"] and "별지.txt [ref3]" not in g["sources"] for g in p["guides"])
    observed = next(g for g in p["guides"] if g.get("basis") == "example")
    assert observed["evidence"][0] == {"source": "작성 예시 [t20]", "image": 1, "label": "그림 1", "detail": "그림 바로 아래의 캡션"}
    assert p["writingJudgment"]["status"] == "apply" and next(x for x in shown if x["id"] == "h1")["writingJudgment"]["status"] == "insufficient"
    assert "캡션을 넣고" in str(form_review._place_brief(p)) and "캡션을 넣고" in guide_write.request(p, "")
    assert "백만원" in p["writingJudgment"]["reason"]
    assert "백만원" not in str(form_review._place_brief(p)) and "백만원" not in guide_write.request(p, "")
    assert all(g["src"] != "llm" for x in shown if x["id"] != "h2" for g in x["guides"])
    key = form_review.place_sig(p)
    user = next(g for place in ps if place["id"] == "h2" for g in place["guides"] if g.get("src") == "user")
    user["text"] = "이번 작성에는 두 줄로 요약"
    assert client.get(ep).json()["ready"]
    edited = next(x for x in client.get(path + "/guide-write").json()["places"] if x["id"] == "h2")
    assert any(g["src"] == "llm" for g in edited["guides"]) and form_review.place_sig(edited) != key
    assert "이번 작성에는 두 줄로 요약" in str(form_review._place_brief(edited)) and form_review.fed([edited])["llmGuides"] == 2
    # 옛 판은 당시의 지침을 그대로 읽을 수 있지만 전 자리 판정 완료로 표시하지 않는다.
    API.works._write_json(path_on_disk, {**record, "judgments": {}, "judgmentCounts": {}})
    assert not client.get(ep).json()["ready"] and not client.get(ep).json()["stale"]
    historical = next(x for x in client.get(path + "/guide-write").json()["places"] if x["id"] == "h2")
    assert "writingJudgment" not in historical and any(g["src"] == "llm" for g in historical["guides"])
    API.works._write_json(path_on_disk, record)
    assert client.post(ep).status_code == 200 and stop.wait(timeout=3)
    assert client.post(ep).status_code == 409
    assert client.post(refs, files={"file": ("바뀐.md", "새 서식".encode())}).status_code == 200
    resume.set()
    stale = watch()
    assert stale["stale"] and not stale["ready"] and stale["run"]["state"] == "failed"
    changed = next(x for x in client.get(path + "/guide-write").json()["places"] if x["id"] == "h2")
    assert key != form_review.place_sig(changed) and all(g["src"] != "llm" for g in changed["guides"])


def test_two_models_judge_separately_then_consult_and_one_model_setting(monkeypatch):
    """두 모델(LLM1 · LLM2)이 따로 판정하고 다르면 협의(2026-11-26 사용자 「문서의 지침을 작성할 떄는 2가지 모델을 같이 사용 … 불가피한 경우 1개만 선택」 — 공통 함수 app/llm_duo.py)."""
    from app import agent_settings
    agent_settings.save("writing_guidance", {"models": None})   # 기본 = 두 모델(LLM1 = 평소 모델 · LLM2 = astra)
    batch, log = [{"id": "첫 자리", "text": "첫 자리"}], []

    def call(schema, prompt, what, **kw):
        log.append((what, kw.get("slot"), kw.get("model")))
        who = "협의" if what.endswith("#consult") else kw.get("slot") or "LLM1"
        if who in call.fail:
            return {"data": None, "error": "boom"}
        return {"data": {"decisions": [{"place": "첫 자리", "status": "not_applicable", "reason": f"{who} 의 판정", "rules": []}] if who != "LLM2" or not call.differ else
                         [{"place": "첫 자리", "status": "insufficient", "reason": "LLM2 는 다르게 봄", "rules": []}]}, "ms": 1}
    call.fail, call.differ = set(), False
    monkeypatch.setattr(API.llm, "call", call)
    run = {}
    got = API._judge(batch, {}, None, [], {}, {}, run=run)   # 판정이 같으면(풀이 글만 다름) 협의 없이 LLM1 의 답
    assert {x[:2] for x in log} == {("writing-guidance", None), ("writing-guidance", "LLM2")} and len(log) == 2 and got["첫 자리"]["reason"] == "LLM1 의 판정"
    assert [r["slot"] for r in run["duo"][0]] == ["LLM1", "LLM2", "협의"] and [r["state"] for r in run["llms"]] == ["done", "done"]
    log.clear()
    call.differ = True   # 판정이 다르면 LLM1 의 모델이 협의
    got = API._judge(batch, {}, None, [], {}, {}, run=run)
    assert [x[0] for x in log][-1] == "writing-guidance#consult" and len(log) == 3 and got["첫 자리"]["reason"] == "협의 의 판정" and run["consult"] == "done"
    log.clear()
    call.fail = {"LLM2"}   # 한쪽만 답하면 그 답
    assert API._judge(batch, {}, None, [], {}, {}, run=run)["첫 자리"]["reason"] == "LLM1 의 판정" and len(log) == 2
    call.fail = {"LLM1", "LLM2"}
    with pytest.raises(ValueError, match="반환하지 않았습니다"):
        API._judge(batch, {}, None, [], {}, {})
    log.clear()
    call.fail = set()
    agent_settings.save("writing_guidance", {"models": [W.MODEL]})   # 「한 모델만」 — 한 번
    assert API._judge(batch, {}, None, [], {}, {})["첫 자리"]["status"] == "not_applicable" and log == [("writing-guidance", "LLM1", W.MODEL)]


def test_no_applicable_rules_is_complete_but_omissions_after_retry_fail(monkeypatch):
    batch = [{"id": name, "text": name} for name in ("첫 자리", "둘째 자리")]
    responses = []

    def call(schema, prompt, what, **kw):
        data = json.loads(prompt.split("## 분석할 자료\n")[-1])
        responses.append([p["id"] for p in data["places"]])
        return {"data": {"decisions": [{"place": "첫 자리", "status": "not_applicable", "reason": "고정된 절 제목", "rules": []}]}}

    monkeypatch.setattr(API.llm, "call", call)
    only = API._judge(batch[:1], {}, None, [], {}, {})
    assert only["첫 자리"]["status"] == "not_applicable" and not only["첫 자리"]["rules"]
    with pytest.raises(ValueError, match="자동 재판정 후에도.*둘째 자리"):
        API._judge(batch, {}, None, [], {}, {})
    assert responses == [["첫 자리"], ["첫 자리", "둘째 자리"], ["둘째 자리"]]


# ---- 테마(테이블 타입 · 구분 기준 타입 · 개요 템플릿 — spec_양식작성 ② §5-7) ----
EMPTY = {"name": "", "signs": "", "how": ""}
NO_THEME = {"name": "", "docs": [], "signs": "", "division": []}
NO_TEMPLATE = {"name": "", "levels": [], "how": ""}


def test_table_types_and_the_document_judgment_are_checked_against_the_themes():
    themes = T.brief()
    types = {x["id"] for t in themes for x in t["tables"]}
    check_table = {"name": "체크 테이블", "signs": "항목마다 □", "how": "해당 항목에 표시한다"}
    data = {"theme": {"id": "rnd", "new": NO_THEME},
            "templates": [{"id": "rnd.main", "new": NO_TEMPLATE}, {"id": "rnd.main", "new": NO_TEMPLATE}, {"id": "rnd.nope", "new": NO_TEMPLATE},
                          {"id": "new", "new": {"name": "로마 숫자 장", "levels": ["Ⅰ.", "", "1."], "how": "장 번호"}}, {"id": "new", "new": {"name": "레터 없음", "levels": [], "how": ""}}],
            "decisions": [{"place": "h1", "status": "not_applicable", "reason": "고정 제목", "rules": [],
                           "tables": [{"table": "t1", "type": "common.body", "new": EMPTY}, {"table": "t1", "type": "common.value", "new": EMPTY},   # 표 하나에 타입 하나
                                      {"table": "t9", "type": "common.body", "new": EMPTY},   # 그 자리의 표가 아니다
                                      {"table": "t2", "type": "common.nope", "new": EMPTY},   # 목록에 없는 타입
                                      {"table": "t3", "type": "new", "new": check_table}, {"table": "t4", "type": "new", "new": {**check_table, "how": ""}}, "글"]},
                          {"place": "h2", "status": "not_applicable", "reason": "고정 제목", "rules": []}]}   # tables 가 없는 옛 꼴의 답도 받는다
    valid, errors = W.check(data, {"h1", "h2"}, {}, {}, {"h1": {"t1", "t2", "t3", "t4"}}, types)
    assert not errors and valid["h2"]["tables"] == []
    assert valid["h1"]["tables"] == [{"table": "t1", "type": "common.body"}, {"table": "t3", "type": "new", "new": check_table}]
    assert W.check(data, {"h1", "h2"}, {}, {})[0]["h1"]["tables"] == []   # 표 · 타입을 주지 않으면 싣지 않는다
    assert W.doc_judgment(data, themes) == {"theme": {"id": "rnd"}, "templates": [{"id": "rnd.main"}, {"id": "new", "new": {"name": "로마 숫자 장", "how": "장 번호", "levels": ["Ⅰ.", "1."]}}]}
    new_theme = {"theme": {"id": "new", "new": {"name": "입찰 제안서", "docs": ["제안서", ""], "signs": "목차", "division": [{"name": "평가 항목", "how": "항목마다"}, {"name": "", "how": "이름 없음"}]}}}
    assert W.doc_judgment(new_theme, themes)["theme"] == {"id": "new", "new": {"name": "입찰 제안서", "signs": "목차", "docs": ["제안서"], "division": [{"name": "평가 항목", "how": "항목마다"}]}}
    for raw in (None, {"decisions": []}, {"theme": {"id": "nope", "new": NO_THEME}, "templates": "글"}, {"theme": {"id": "new", "new": NO_THEME}}):
        assert W.doc_judgment(raw, themes) == {"theme": None, "templates": []}
    assert set(W.SCHEMA["required"]) == {"theme", "templates", "decisions"} and "tables" in W.DECISION["required"]


def test_heading_places_list_their_tables_and_new_definitions_are_added_once(monkeypatch):
    ps = guide_write.places(BLOCKS, GRAPH, IX)
    briefs = W.briefs(ps, BLOCKS, GRAPH, None, False)
    by = {b["id"]: b for b in briefs}
    assert "tables" not in by["h1"] and by["h3"]["tables"] == [{"id": "t2", "text": "항목 | 값"}]   # 제 자리로 선 표(t1)는 그 자리에서 — 제목 자리에는 딸린 표만
    assert [W.table_ids(by[k]) for k in ("h1", "h3", "t1", "t3")] == [set(), {"t2"}, {"t1"}, {"t3"}]
    assert "tables" not in {b["id"]: b for b in W.briefs(ps, BLOCKS, GRAPH, None, False, skip={"t2"})}["h3"]   # 작성 예시는 채울 표가 아니다
    themes = T.brief()
    types = {x["id"] for t in themes for x in t["tables"]}
    answers = {"h3": [{"table": "t2", "type": "new", "new": {"name": "체크 테이블", "signs": "항목마다 □", "how": "해당 항목에 표시한다"}}],
               "t1": [{"table": "t1", "type": "common.body", "new": EMPTY}], "t3": [{"table": "t3", "type": "common.value", "new": EMPTY}, {"table": "t1", "type": "common.body", "new": EMPTY}]}

    def call(schema, content, what, **kw):
        data = json.loads(content.split("## 분석할 자료\n")[-1])
        assert schema == W.SCHEMA and [t["id"] for t in data["themes"]] == ["common", "rnd"] and "common.figure" in {x["id"] for x in data["themes"][0]["tables"]}
        assert next(p for p in data["places"] if p["id"] == "h3")["tables"] == [{"id": "t2", "text": "항목 | 값"}]
        return {"data": {"theme": {"id": "rnd", "new": NO_THEME},
                         "templates": [{"id": "rnd.main", "new": NO_TEMPLATE}, {"id": "new", "new": {"name": "로마 숫자 장", "levels": ["Ⅰ.", "1."], "how": "장 번호"}}],
                         "decisions": [{"place": p["id"], "status": "not_applicable", "reason": "고정 제목", "rules": [], "tables": answers.get(p["id"], [])} for p in data["places"]]}}

    monkeypatch.setattr(API.llm, "call", call)
    doc = {}
    decisions = API._judge(briefs, {"themes": themes}, None, [], {}, {}, types, doc)
    assert decisions["t3"]["tables"] == [{"table": "t3", "type": "common.value"}] and decisions["h3"]["tables"][0]["type"] == "new" and decisions["h1"]["tables"] == []
    judged = W.doc_judgment(doc["got"], themes)
    theme, templates, by_place, defined = API._settle(judged, decisions, "w1")
    check_id, roman = T.by_name("tables", "체크 테이블"), T.by_name("templates", "로마 숫자 장")
    assert theme == "rnd" and check_id.startswith("rnd.") and roman.startswith("rnd.") and templates == ["rnd.main", roman]   # 새 항목은 문서의 테마에 더한다
    assert by_place == {"t1": [{"table": "t1", "type": "common.body"}], "h3": [{"table": "t2", "type": check_id}], "t3": [{"table": "t3", "type": "common.value"}]}
    assert defined == [{"kind": "templates", "id": roman, "name": "로마 숫자 장"}, {"kind": "tables", "id": check_id, "name": "체크 테이블"}]
    item = T.find("tables", check_id)[1]
    assert (item["src"], item["work"], item["how"]) == ("llm", "w1", "해당 항목에 표시한다") and T.find("templates", roman)[1]["levels"] == ["Ⅰ.", "1."]
    again = API._settle(judged, decisions, "w2")   # 다음 실행이 같은 이름을 또 정의해도 다시 더하지 않는다
    assert again[:3] == (theme, templates, by_place) and again[3] == [] and T.find("tables", check_id)[1]["work"] == "w1"
    none = API._settle({"theme": None, "templates": [{"id": "new", "new": {"name": "가나다 사슬", "levels": ["가.", "1)"], "how": ""}}]}, {}, "w3")   # 테마를 못 정했으면 공통에
    assert none[0] is None and none[1] == [T.by_name("templates", "가나다 사슬")] and none[1][0].startswith("common.")


def test_table_types_and_the_theme_reach_the_review_and_the_draft_request(monkeypatch, tmp_path):
    monkeypatch.setenv("NFM_WORKS", str(tmp_path))
    client = TestClient(server.app)
    doc = client.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    ps = guide_write.places(BLOCKS, GRAPH, IX)
    monkeypatch.setattr(guide_write_api, "_base_places", lambda s: (copy.deepcopy(ps), s.rev))
    s = server._sess(doc)
    record = {"sig": API._key(s, copy.deepcopy(ps), s.rev, []), "rules": {}, "judgments": {p["id"]: {"status": "not_applicable", "reason": "고정 제목"} for p in ps},
              "judgmentCounts": {"apply": 0, "not_applicable": len(ps), "insufficient": 0}, "count": 0, "placeCount": len(ps),
              "theme": {"id": "rnd", "name": "연구개발과제", "text": "판정 때의 글"},
              "templates": [{"id": "rnd.main", "name": "연구개발계획서 기본", "levels": ["1.", "1-1."]}, {"id": "rnd.gone", "name": "지워진 템플릿", "levels": ["가.", "1)"]}],
              "tableTypes": {"h3": [{"table": "t2", "text": "항목 | 값", "type": "common.body", "name": "판정 때의 이름", "how": "판정 때의 방법"}],
                             "t1": [{"table": "t1", "text": "", "type": "rnd.gone", "name": "지워진 타입", "how": "적어 둔 방법"}]},
              "defined": [{"kind": "tables", "id": "rnd.gone", "name": "지워진 타입"}]}
    API.works._write_json(tmp_path / doc / API.FILE, record)
    view = client.get(f"/api/docs/{doc}/writing-guidance").json()
    assert view["ready"] and view["theme"] == record["theme"] and view["templates"] == record["templates"] and view["tableTypeCount"] == 2 and view["defined"] == record["defined"]
    shown = {p["id"]: p for p in client.get(f"/api/docs/{doc}/guide-write").json()["places"]}
    assert shown["h3"]["tableTypes"] == [{"table": "t2", "type": "common.body", "name": "본문 테이블", "src": "default"}]   # 이름 · 작성 방법은 지금 테마의 것
    assert shown["t1"]["tableTypes"] == [{"table": "t1", "type": "rnd.gone", "name": "지워진 타입", "src": "", "unconfirmed": True}]   # 지워진 타입은 판정 때 적어 둔 이름으로 — 이 실행에서 LLM 이 정의한 것(defined)이라 확인 전
    assert "tableTypes" not in shown["h1"] and all("docTheme" not in p for p in shown.values())
    guide = shown["h3"]["guides"][-1]
    assert (guide["src"], guide["kind"], guide["sources"], shown["h3"]["n"]) == ("llm", "테이블 타입", ["테마 「공통」"], 1)
    assert guide["instruction"].startswith("테이블 타입 — 표 「항목 | 값」(t2): 본문 테이블. 본문 내용을 표 칸에 적는다")
    mine = [g for g in shown["t1"]["guides"] if g.get("kind") == "테이블 타입"]   # 양식의 지침(※ 안내)과 함께 선다
    # 2026-11-26(spec_양식작성 ② §5-9): LLM 이 정의한 타입의 작성 방법(how)은 사람이 확인하기 전에는 글 쓰는 호출에 싣지 않는다 — 이름 · 꼬리표만(전에는 「…: 지워진 타입. 적어 둔 방법」 이 실렸다)
    assert len(mine) == 1 and mine[0]["instruction"] == "테이블 타입 — 이 표: 지워진 타입" and mine[0]["sources"] == ["테마"] and shown["t1"]["n"] == 2
    places, _ = guide_write_api._places(s)
    by = {p["id"]: p for p in places}
    theme = by["h1"]["docTheme"]
    assert theme.startswith("연구개발과제 — 중요하게 볼 항목: 참여기관 · 연차 · 연구목표 · 예산 · 단계\n문서가 쓰는 개요 템플릿: 연구개발계획서 기본(1. › 1-1. › □ › o › - › ⋅) · 지워진 템플릿(가. › 1))\n항목마다: 참여기관: ")
    assert all(p["docTheme"] == theme for p in places) and len(theme) <= API.THEME_MAX
    brief = form_review._place_brief(by["h3"])
    assert brief["writingGuidance"] == [{"instruction": guide["instruction"], "sources": ["테마 「공통」"]}]
    data = form_review.payload([], {}, places, [])   # 06 은 문서의 테마를 한 번만 받는다(자리마다가 아니다)
    assert data["theme"] == theme and "theme" not in form_review.payload([], {}, ps, []) and "- theme = " in form_review.CONTRACT
    assert all("docTheme" not in p and "theme" not in p for p in data["places"])
    request = guide_write.request(by["h3"], "")
    assert "- (04 자동 판정 · 테이블 타입) 테이블 타입 — 표 「항목 | 값」(t2): 본문 테이블. 본문 내용을 표 칸에 적는다" in request
    assert "문서의 테마(04 자동 판정): 연구개발과제 — 중요하게 볼 항목: 참여기관 · 연차 · 연구목표 · 예산 · 단계 문서가 쓰는 개요 템플릿: 연구개발계획서 기본(1. › 1-1. › □ › o › - › ⋅)" in request
    assert "문서의 테마" not in guide_write.request(next(p for p in ps if p["id"] == "h3"), "")
    packed = guide_write.request(by["h3"], "가" * guide_write.NOTE_MAX, "", "나" * 1100)   # 사람의 지침 · 계획이 길면 테마는 줄이거나 빼고 묻는 말은 남긴다
    assert len(packed) <= guide_write.TEXT_MAX and packed.rstrip().endswith("(지어내지 않습니다).")
