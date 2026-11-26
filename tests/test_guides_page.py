"""지침 설정 페이지 /guides 의 끝점(app/guides_page_api.py · spec_양식작성 ② §5-10) — 읽기만 하는 목록 둘(판단 지침 · 양식별)과 프로젝트로 읽고 쓰는 문서 목적.
고치기는 글마다 이미 있는 끝점이다 — 목록이 적어 준 주소(save · reset)로 고치면 목록이 따라오는지 본다."""
import pytest
from fastapi.testclient import TestClient

from app import form_guide_yaml as FG
from app import form_rules as FR
from app import projects, server

GUIDE = """
form: 연차보고서
theme: rnd
guides: [어느 과제에나 맞는 일반 지침]
sections:
  - id: s1
    path: ["1. 개요"]
    guides: [한 문장으로]
    tables:
      - {id: s1.t1, head: 구분 | 목표, guides: [차년도마다 한 행]}
"""
RULES = """
form: 연차보고서
rules:
  - {id: r1, text: 본문은 10쪽 이내, source: {name: 작성지침서}, required: true}
  - {id: r2, text: 목표는 정량으로, required: false, targets: [{path: ["1. 개요"]}]}
"""
PURPOSE = "purpose: 탄소 저감을 보인다\nevaluation: [정량 근거]\n"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    """헤딩 저장소(헤딩 지침의 사본 · 양식 파일의 이력 history.jsonl)도 임시 폴더로 — 사용자의 저장소(%LOCALAPPDATA%)에 쓰지 않게."""
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "headings"))


def _by(c):
    return {x["id"]: x for x in c.get("/api/guides-page/judgment").json()["items"]}


def test_page_stands_alone_and_judgment_lists_readers_and_follows_edits():
    c = TestClient(server.app)
    html = c.get("/guides").text
    assert html.index("/static/account/chip.js") < html.index("/static/guides.js") and "/static/app.js" not in html and "guides.js?v=" in html   # 계정 스크립트가 먼저 · app.js 를 읽지 않는다
    j = c.get("/api/guides-page/judgment").json()
    by = {x["id"]: x for x in j["items"]}
    assert [g["key"] for g in j["groups"]] == ["merge", "heading", "skill", "theme"]
    assert {"merge:links", "merge:writing_guidance", "merge:guide_fix", "heading:rules", "heading:tables", "skill:tidy", "theme:rnd", "theme:common"} <= set(by)
    links = by["merge:links"]
    assert [r["id"] for r in links["readers"]] == ["merge_links"] and links["readers"][0]["no"] and any(u["job"] == "plan_to_report" and u["stepName"] for u in links["readers"][0]["used"])
    assert not links["custom"] and links["default"] == links["text"] and links["lang"] == "md"
    assert len(by["heading:tables"]["readers"]) >= 2 and by["skill:tidy"]["readers"][0]["id"] == "tpl_agent"   # 글 하나를 여러 에이전트가 읽는다
    assert by["theme:rnd"]["lang"] == "yaml" and by["theme:rnd"]["readers"] == by["merge:writing_guidance"]["readers"]   # 테마는 작성 지침 보완이 읽는다
    # 목록이 적어 준 주소로 고치면(이미 있는 저장 길) 목록이 따라온다 — 기본본은 그대로 남아 견줄 수 있다
    assert c.put(links["save"]["url"], json={"text": "고친 판단 지침 글", "version": links["version"]}).status_code == 200
    mine = _by(c)["merge:links"]
    assert mine["custom"] and mine["text"] == "고친 판단 지침 글" and mine["default"] == links["text"] and mine["version"] == links["version"] + 1
    assert c.put(links["save"]["url"], json={"text": "낡은 판", "version": links["version"]}).status_code == 409
    assert c.delete(f'{mine["reset"]["url"]}?version={mine["version"]}').status_code == 200
    assert not _by(c)["merge:links"]["custom"] and _by(c)["merge:links"]["text"] == links["text"]
    rules = by["heading:rules"]
    assert c.put(rules["save"]["url"], json={"text": rules["text"] + "\n- 시험 줄", "version": rules["version"]}).status_code == 200
    assert _by(c)["heading:rules"]["custom"] and _by(c)["heading:rules"]["default"] == rules["text"]
    assert c.delete(rules["reset"]["url"]).status_code == 200 and not _by(c)["heading:rules"]["custom"]


def test_forms_listing_and_the_project_purpose(tmp_path):
    forms = tmp_path / "forms"   # conftest 의 NFM_FORMS
    forms.mkdir(parents=True, exist_ok=True)
    (forms / "연차보고서.md").write_text("# 연차보고서\n\n양식 정보 글\n", encoding="utf-8")
    FG.save_text("연차보고서", GUIDE, expect="")
    FR.save_text("연차보고서", RULES, expect="")
    assert projects.create("시험 프로젝트")
    c = TestClient(server.app)
    got = c.get("/api/guides-page/forms").json()
    f = next(x for x in got["forms"] if x["key"] == "연차보고서")
    assert f["guide"]["exists"] and f["guide"]["doc"]["guides"][0]["text"] == "어느 과제에나 맞는 일반 지침" and f["guide"]["doc"]["sections"][0]["tables"][0]["head"] == "구분 | 목표"
    assert [r["id"] for r in f["rules"]["doc"]["rules"]] == ["r1", "r2"] and f["theme"]["id"] == "rnd" and f["projects"] == []
    assert [(p["name"], p["works"], p["purpose"]["exists"]) for p in got["loose"]] == [("시험 프로젝트", 0, False)]   # 문서가 아직 없는 프로젝트도 문서 목적을 적을 수 있게
    # 양식 쪽 고치기 = 앞에서 만든 끝점 그대로(목록은 다음 읽기에 따라온다)
    y = c.get("/api/form-rules/연차보고서/yaml").json()
    assert c.put("/api/form-rules/연차보고서/yaml", json={"text": RULES.replace("10쪽", "12쪽"), "sha1": y["sha1"]}).status_code == 200
    assert c.put("/api/form-rules/연차보고서/yaml", json={"text": RULES, "sha1": y["sha1"]}).status_code == 409
    assert next(x for x in c.get("/api/guides-page/forms").json()["forms"] if x["key"] == "연차보고서")["rules"]["doc"]["rules"][0]["text"] == "본문은 12쪽 이내"
    (forms / "연차보고서.rules.yaml").write_text("rules: 글", encoding="utf-8")
    broken = next(x for x in c.get("/api/guides-page/forms").json()["forms"] if x["key"] == "연차보고서")["rules"]
    assert broken["broken"] and broken["doc"] is None   # 못 읽는 파일은 그렇게 보인다(목록이 죽지 않는다)
    # 문서 목적 — 프로젝트로 읽고 쓴다(문서를 열지 않는다)
    p = c.get("/api/purpose/yaml", params={"project": "시험 프로젝트"}).json()
    assert p["exists"] is False and p["sha1"] == "" and p["text"].startswith("# 문서 목적 — 프로젝트 「시험 프로젝트」")
    assert c.get("/api/purpose/yaml", params={"project": "없는 프로젝트"}).status_code == 404
    assert c.put("/api/purpose/yaml", json={"project": "없는 프로젝트", "text": PURPOSE, "sha1": ""}).status_code == 404   # 아무 이름의 파일을 만들지 않는다
    assert c.put("/api/purpose/yaml", json={"project": "시험 프로젝트", "text": "purpose: [목록]", "sha1": ""}).status_code == 400
    saved = c.put("/api/purpose/yaml", json={"project": "시험 프로젝트", "text": PURPOSE, "sha1": ""})
    assert saved.status_code == 200 and saved.json()["sha1"]
    assert c.put("/api/purpose/yaml", json={"project": "시험 프로젝트", "text": PURPOSE + "\n", "sha1": ""}).status_code == 409
    row = c.get("/api/guides-page/forms").json()["loose"][0]["purpose"]
    assert row == {"exists": True, "purpose": True, "evaluation": 1, "requirements": 0, "guides": 0}
