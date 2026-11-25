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
from app import writing_guidance as W
from app import writing_guidance_api as API
from tests.test_guide_write import BLOCKS, GRAPH, IX, SMALL


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
