"""에이전트 설정(spec_에이전트) — 등록부 · 사용자 설정(작업 번호·역할·모델·생각 깊이) · llm.call 의 모델 차례 · 실행 기록 · API. conftest 가 NFM_AGENTS 를 시험마다 임시 파일로 돌린다."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import agent_settings as S
from app import agents as A
from app import llm, server, tpl_agent

ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.delenv("NFM_LLM_MODEL_FORCE", raising=False)
    monkeypatch.delenv("NFM_LLM_MODEL", raising=False)
    S.reset_runs()
    yield
    S.reset_runs()


def test_every_llm_call_label_in_the_code_has_an_agent():
    """코드에 있는 llm.call 의 what 글이 모두 등록된 에이전트로 이어진다 — 새 호출을 만들고 등록을 잊으면 떨어진다."""
    labels = set()
    for p in (ROOT / "app").glob("*.py"):
        if p.name in ("llm.py", "agents.py", "agent_settings.py"):
            continue
        text = p.read_text(encoding="utf-8")
        labels |= {m.group(2) for m in re.finditer(r"""llm\.call\)?\([^"'
]*?,\s*f?(["'])([a-z][a-z_\-]+)""", text)}   # (call or llm.call)(스키마, 글, "이름" …) 의 이름
        labels |= {m.group(2) for m in re.finditer(r""""what":\s*f?(["'])((?:heading_|merge-|gather-|style-)[a-z_\-]+)""", text)}
    labels |= set(__import__("app.style_extract", fromlist=["WHAT"]).WHAT.values())
    assert {"divisions-llm", "divisions-missing", "doc-agent", "merge-llm", "table-formula", "table-fill", "table-make-", "tpl-agent", "heading_types", "heading_section", "heading_formats",
            "heading_review", "heading_rules", "heading_tables", "merge-gaps-", "merge-table-map-", "gather-llm-", "style-review-tables"} <= labels, sorted(labels)
    lost = sorted(w for w in labels if S.agent_of(w) is None)
    assert not lost, f"등록 안 된 LLM 호출: {lost}"
    assert S.agent_of("merge-llm-3") == "merge_links" and S.agent_of("merge-table-map-1") == "merge_table_map" and S.agent_of("heading_section#2") == "heading_section"
    assert S.agent_of("table-make-text") == "table_make" and S.agent_of("style-review-pages") == "style_review" and S.agent_of("something-else") is None and S.agent_of(None) is None


def test_registry_lists_role_place_prompt_for_every_agent(monkeypatch):
    monkeypatch.delenv("NFM_JOBS", raising=False)   # 할 일 프롬프트는 저장소 jobs/ 의 것을 본다(conftest 는 빈 임시 폴더로 돌려 둔다)
    L = A.listing()
    ags = L["agents"]
    assert len(ags) == 19 and [a["no"] for a in ags] == [f"{i:02d}" for i in range(1, 20)] and len({a["id"] for a in ags}) == 19
    assert {a["group"] for a in ags} == set(L["groups"]) and all(a["role"] and a["where"] and a["name"] and a["whats"] for a in ags)
    assert L["models"] == list(S.MODELS) and L["efforts"] == list(S.EFFORTS) and L["llm"]["available"] is False
    by = {a["id"]: a for a in ags}
    assert by["tpl_agent"]["model"] == {"id": "claude-opus-5-5", "source": "pin"} and by["tpl_agent"]["pin"]
    assert by["merge_links"]["model"] == {"id": "claude-opus-5-5", "source": "code"} and by["heading_rules"]["model"]["source"] == "default"
    assert by["heading_rules"]["effort"] == {"id": "low", "source": "code"} and by["doc_agent"]["effort"]["source"] == "default"
    for a in ags:  # 에이전트마다 계약 글이 있고 프롬프트의 차례가 계약 → … → 자료
        d = A.detail(a["id"])
        kinds = [p["kind"] for p in d["prompt"]]
        assert kinds[0] == "contract" and kinds[-1] == "data" and all(p["text"] for p in d["prompt"] if p["kind"] == "contract"), a["id"]
        assert all(p["title"] and p["source"] for p in d["prompt"]) and d["prompt"][-1]["note"]
    hp = A.detail("heading_types")["prompt"]
    hg = [p for p in hp if p["kind"] == "heading"]
    assert [p["name"] for p in hg] == ["graph", "templates", "tolerance"] and all(p["editable"] and p["text"] and p["api"] == f"/api/headings/guides/{p['name']}" for p in hg) and not hp[0]["editable"]
    assert [p["kind"] for p in hp] == ["contract", "heading", "heading", "heading", "form", "data"]
    m = [p for p in A.detail("merge_links")["prompt"] if p["kind"] in ("merge", "job")]
    assert [p["source"] for p in m] == ["app/merge_guides_default/links.md", "jobs/plan_to_report.md"] and all(p["text"] and not p["editable"] for p in m)
    assert [p["title"] for p in A.detail("style_review")["prompt"] if p["kind"] == "contract"] == ["계약 — 테이블 서식 후보", "계약 — 내용·문단 서식 후보", "계약 — 쪽 설정·표지 후보"]
    sk = [p for p in A.detail("tpl_agent")["prompt"] if p["kind"] == "skill"]
    assert [p["name"] for p in sk] == ["tidy", "majority"] and all(p["editable"] and p["api"].endswith(p["name"]) for p in sk)


def test_force_shows_as_the_model_of_every_agent_but_the_pinned_one(monkeypatch):
    monkeypatch.setenv("NFM_LLM_MODEL_FORCE", "claude-fable-5-2")
    by = {a["id"]: a for a in A.listing()["agents"]}
    assert by["merge_links"]["model"] == {"id": "claude-fable-5-2", "source": "force"} and by["merge_links"]["modelCode"] == "claude-opus-5-5"   # 코드가 정한 Opus 보다 서버 강제가 먼저
    assert by["heading_types"]["model"]["source"] == "force" and by["tpl_agent"]["model"] == {"id": "claude-opus-5-5", "source": "pin"}


def test_update_number_role_model_effort_and_back_to_default():
    d = A.update("merge_links", {"no": "M-1", "role": "  내가 적은 역할  ", "model": "claude-sonnet-5-5", "effort": "high"})
    assert d["no"] == "M-1" and d["noDefault"] == "09" and d["role"] == "내가 적은 역할" and d["model"] == {"id": "claude-sonnet-5-5", "source": "user"} and d["effort"] == {"id": "high", "source": "user"}
    assert d["custom"] == ["effort", "model", "no", "role"] and d["version"] == 1 and S.path().is_file()
    with pytest.raises(ValueError, match="쓰고 있습니다"):
        A.update("merge_gaps", {"no": "M-1"})          # 다른 에이전트의 번호
    with pytest.raises(ValueError, match="쓰고 있습니다"):
        A.update("merge_gaps", {"no": "10"})           # 다른 에이전트의 기본 번호
    assert A.update("merge_gaps", {"no": "09"})["no"] == "09"   # 비어 있는 번호(merge_links 가 M-1 로 옮겨 감)
    with pytest.raises(S.Stale):
        A.update("merge_links", {"role": "x"}, expect=0)
    for bad in ({"model": "Not A Model!"}, {"effort": "huge"}, {"no": "한 칸 띄움"}, {"no": "x" * 13}, {"role": "가" * 601}, {"model": 3}):
        with pytest.raises(ValueError):
            A.update("merge_links", bad)
    back = A.update("merge_links", {"no": None, "role": "", "model": None, "effort": None})
    assert back["custom"] == [] and back["role"] == back["roleDefault"] and back["model"]["source"] == "code" and back["effort"] == {"id": "medium", "source": "code"}
    assert back["no"] == "09" or back["no"] == back["noDefault"]
    same = A.update("heading_rules", {"no": "01", "role": A.BY_ID["heading_rules"]["role"]})   # 기본과 같은 값은 따로 적지 않는다
    assert same["custom"] == []
    with pytest.raises(KeyError):
        A.update("nope", {"no": "1"})


def test_llm_call_uses_the_agent_setting_first_and_records_the_run(monkeypatch):
    monkeypatch.setenv("NFM_LLM_MODEL_FORCE", "claude-fable-5-2")
    assert llm.call({}, "x", "merge-llm-2", model="claude-opus-5-5")["model"] == "claude-fable-5-2"      # 설정 없음 — 서버 강제
    A.update("merge_links", {"model": "claude-haiku-5-5", "effort": "max"})
    r = llm.call({}, "x", "merge-llm-2", model="claude-opus-5-5", effort="medium")
    assert r["model"] == "claude-haiku-5-5" and r["effort"] == "max"                                     # 사람이 정한 값이 강제·코드보다 먼저
    assert llm.call({}, "x", "merge-gaps-1", model="claude-opus-5-5")["model"] == "claude-fable-5-2"     # 다른 에이전트는 그대로
    A.update("tpl_agent", {"model": "claude-sonnet-5-5"})
    assert llm.call({}, "x", "tpl-agent", model="claude-opus-5-5", pin=True)["model"] == "claude-sonnet-5-5" and tpl_agent.status()["model"] == "claude-sonnet-5-5"   # 고정(pin)보다도 먼저
    runs = S.runs()
    assert [x["n"] for x in runs] == [4, 3, 2, 1] and runs[0]["agent"] == "tpl_agent" and runs[2]["agent"] == "merge_links" and runs[2]["model"] == "claude-haiku-5-5"
    assert runs[0]["error"] == "off" and runs[0]["ok"] is False and [x["what"] for x in S.runs("merge_links")] == ["merge-llm-2", "merge-llm-2"]
    t = S.tally()
    assert t["merge_links"]["runs"] == 2 and t["merge_links"]["fails"] == 2 and t["merge_links"]["last"]["n"] == 2
    by = {a["id"]: a for a in A.listing()["agents"]}
    assert by["merge_links"]["runs"] == 2 and by["merge_links"]["last"]["model"] == "claude-haiku-5-5" and by["heading_rules"]["runs"] == 0


def test_broken_settings_file_is_ignored_and_rewritten():
    S.path().write_text("{not json", encoding="utf-8")
    assert S.load() == {"version": 0, "agents": {}} and S.override("merge-llm") == {}
    assert A.update("merge_links", {"effort": "high"})["effort"]["id"] == "high"
    S.path().write_text('{"version": 5, "agents": {"merge_links": {"model": "claude-opus-5-5", "x": 1}, "ghost": {"model": "a"}, "div_review": 3}}', encoding="utf-8")
    assert S.load() == {"version": 5, "agents": {"merge_links": {"model": "claude-opus-5-5"}}}


def test_settings_off_keeps_values_in_memory(monkeypatch):
    monkeypatch.setenv("NFM_AGENTS", "off")
    S._MEMORY.update(version=0, agents={})
    assert S.path() is None and A.update("gather", {"effort": "low"})["effort"] == {"id": "low", "source": "user"} and S.override("gather-llm-1") == {"effort": "low"}
    S._MEMORY.update(version=0, agents={})


def test_api_roundtrip():
    c = TestClient(server.app, raise_server_exceptions=False)
    L = c.get("/api/agents").json()
    assert len(L["agents"]) == 19 and L["version"] == 0 and "prompt" not in L["agents"][0]
    d = c.get("/api/agents/doc_agent").json()
    assert d["name"] == "문서 에이전트" and d["prompt"][0]["kind"] == "contract" and d["recent"] == []
    r = c.put("/api/agents/doc_agent", json={"no": "E1", "model": "claude-opus-5-5", "version": 0})
    assert r.status_code == 200 and r.json()["no"] == "E1" and r.json()["model"] == {"id": "claude-opus-5-5", "source": "user"} and r.json()["version"] == 1
    assert c.put("/api/agents/doc_agent", json={"role": "x", "version": 0}).status_code == 409
    assert c.put("/api/agents/table_fill", json={"no": "E1"}).status_code == 400
    assert c.put("/api/agents/doc_agent", json={"effort": "nope"}).status_code == 400
    assert c.put("/api/agents/nope", json={}).status_code == 404 and c.get("/api/agents/nope").status_code == 404
    llm.call({}, "x", "doc-agent")
    runs = c.get("/api/agents/runs", params={"agent": "doc_agent"}).json()["runs"]
    assert len(runs) == 1 and runs[0]["model"] == "claude-opus-5-5" and c.get("/api/agents/runs", params={"agent": "nope"}).status_code == 404
    assert c.get("/api/agents/doc_agent").json()["recent"][0]["n"] == runs[0]["n"]
    assert c.put("/api/agents/doc_agent", json={"no": None, "model": None}).json()["custom"] == []


def test_page_and_the_start_page_link():
    """따로 선 페이지 /agents(② §5) — 파일 주소에 수정 시각 · 시작 화면 상단 바의 링크(새 탭) · 시작 화면은 agents.js·agents.css 를 읽지 않는다 · 주소의 # 에 쓰는 말은 에이전트 id 가 아니다."""
    c = TestClient(server.app)
    p = c.get("/agents")
    assert p.status_code == 200 and "text/html" in p.headers["content-type"] and p.headers["cache-control"] == "no-cache"
    for name in ("style.css", "agents.css", "agents.js"):
        m = re.search(rf'"/static/{re.escape(name)}\?v=(\d+)"', p.text)
        assert m and int(m.group(1)) == int((server.STATIC / name).stat().st_mtime), name
        assert c.get(f"/static/{name}").status_code == 200
    assert 'id="agNav"' in p.text and 'id="agMain"' in p.text and 'href="/workflow"' in p.text
    assert not {"overview", "runs"} & set(A.BY_ID)
    html = c.get("/").text
    m = re.search(r'<a class="btn ags-link" id="agentsLink" href="/agents" target="_blank"[^>]*>', html)
    assert m and 'aria-label="에이전트 설정"' in m.group(0) and 'rel="noopener"' in m.group(0)
    assert "agentsBtn" not in html and "/static/agents.js" not in html and "/static/agents.css" not in html
    js = (server.STATIC / "agents.js").read_text(encoding="utf-8")
    assert "headsDlg" not in js and "hHelp" not in js   # app.js 없이 혼자 돈다
