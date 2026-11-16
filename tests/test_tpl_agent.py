"""템플릿 서식 정리 에이전트 · 템플릿 단위 맞추기(spec_hwpx_웹편집 ② §8-2 「템플릿 맞추기」 · §8-4) — 연구개발계획서 양식 + 2단계(LLM 끔 · 에이전트 답은 가짜).
양식의 갈래(test_outline_match 와 같은 문서): T3 「o › -」 L2 = 「   - 」 5줄(대표 p6502) · 「    - 」(p5209) · 「    -」(p5765)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, llm, server
from app import outline_match as M
from app import tpl_agent as A

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    monkeypatch.delenv("NFM_TPL_AGENT_MODEL", raising=False)
    R._MEMORY.clear()
    G._MEMORY.clear()
    A._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()
    A._MEMORY.clear()


@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tpl_agent")
    with pytest.MonkeyPatch.context() as mp:
        for k, v in {"NFM_PDF": "off", "NFM_LLM_BACKEND": "off", "NFM_WORKS": tmp / "works", "NFM_RENDER": tmp / "render",
                     "NFM_HEADINGS": tmp / "heads", "NFM_FORMS": tmp / "forms", "NFM_DIVISION_PRESETS": tmp / "presets.json"}.items():
            mp.setenv(k, str(v))
        server.DOCS.clear()
        c = TestClient(server.app, raise_server_exceptions=False)
        r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
        assert r.status_code == 200, r.text
        d = r.json()["docId"]
        s = server.DOCS[d]
        heading_runs.run_sync(s, 1, False)
        heading_runs.run_sync(s, 2, False)
        assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다
        yield c, d, s
        server.DOCS.clear()


def _undo_all(c, d, s):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def _slot(c, d, tid, lv):
    return c.get(f"/api/docs/{d}/outline/formats").json()["slots"][str(tid)][str(lv)]


# ---------------------------------------------------------------- 스킬(저장한 정리 기준 글)
def test_builtin_skills_listed_and_text_has_no_title_or_comment():
    ls = A.skills()
    assert [s["key"] for s in ls[:2]] == ["tidy", "majority"] and all(s["builtin"] and not s["custom"] and s["version"] == 0 for s in ls)
    t = A.skill("tidy")
    assert t["name"] == "템플릿 서식 정리" and "<!--" not in t["text"] and not t["text"].lstrip().startswith("# ") and "## 대표 고르기" in t["text"]
    with pytest.raises(KeyError):
        A.skill("nope")
    with pytest.raises(KeyError):
        A.skill("../x")


def test_skill_save_edit_reset_and_new_delete():
    a = A.save("tidy", "내 정리 기준", "줄 수가 많은 갈래로 맞춘다.\n")
    assert a["custom"] and a["builtin"] and a["version"] == 1 and a["name"] == "내 정리 기준" and a["text"] == "줄 수가 많은 갈래로 맞춘다.\n"
    with pytest.raises(R.StaleVersion):
        A.save("tidy", "x", "y", expect=0)  # 옛 판을 든 저장
    b = A.save("tidy", "내 정리 기준", "둘째 판", expect=1)
    assert b["version"] == 2 and A.skill("tidy")["text"] == "둘째 판"
    back = A.remove("tidy")  # 기본 스킬 — 사본을 버리고 기본본으로
    assert not back["custom"] and back["name"] == "템플릿 서식 정리" and back["version"] == 3 and "## 대표 고르기" in back["text"]
    n = A.save(None, "  글꼴만   통일 ", "글꼴이 다른 갈래만 맞춘다")
    assert n["key"].startswith("u") and n["name"] == "글꼴만 통일" and not n["builtin"] and n["custom"] and n["version"] == 1
    assert [s["key"] for s in A.skills()] == ["tidy", "majority", n["key"]]
    assert A.remove(n["key"]) == {"deleted": True, "key": n["key"]}
    with pytest.raises(KeyError):
        A.skill(n["key"])
    for bad in ("", "   ", "x" * (A.TEXT_MAX + 1)):
        with pytest.raises(ValueError):
            A.save(None, "이름", bad)
    with pytest.raises(ValueError):
        A.save(None, "", "글")


def test_skill_api_roundtrip(sess):
    c, _, _ = sess
    r = c.get("/api/outline/agent").json()
    assert r["model"] == "claude-opus-5-5" and r["available"] is False and [s["key"] for s in r["skills"]][:2] == ["tidy", "majority"]
    made = c.post("/api/outline/agent/skills", json={"name": "새 스킬", "text": "기준"}).json()
    assert made["version"] == 1
    assert c.put(f"/api/outline/agent/skills/{made['key']}", json={"name": "새 스킬", "text": "고친 기준", "version": 1}).json()["version"] == 2
    assert c.put(f"/api/outline/agent/skills/{made['key']}", json={"name": "새 스킬", "text": "x", "version": 1}).status_code == 409
    assert c.put("/api/outline/agent/skills/nope", json={"name": "a", "text": "b"}).status_code == 404
    assert c.post("/api/outline/agent/skills", json={"name": "a", "text": ""}).status_code == 400
    assert c.get(f"/api/outline/agent/skills/{made['key']}").json()["text"] == "고친 기준"
    assert c.delete(f"/api/outline/agent/skills/{made['key']}").json() == {"deleted": True, "key": made["key"]}
    assert c.get(f"/api/outline/agent/skills/{made['key']}").status_code == 404


# ---------------------------------------------------------------- 자료 · 계획
def test_material_groups_and_prompt(sess):
    c, d, s = sess
    mat = A.material(s.doc, s.outline, "3")
    assert mat["no"] == "3" and [lv["level"] for lv in mat["levels"]] == [1, 2]
    l2 = mat["levels"][1]
    assert [g["id"] for g in l2["groups"]] == ["g1", "g2", "g3"] and l2["groups"][0]["rep"] and l2["groups"][0]["para"] == "p6502" and l2["groups"][0]["count"] == 5
    pm = A.prompt_material(mat)
    g1, g2 = pm["levels"][1]["groups"][:2]
    assert g1["currentRep"] and g1["values"]["앞 공백"] == "3칸" and "values" not in g2 and ["앞 공백", "3칸", "4칸"] in g2["differsFromRep"]
    text = A.prompt(mat, A.skill("tidy"), "L2 는 3칸으로")
    assert "## 스킬 — 템플릿 서식 정리" in text and "## 이번 요청" in text and "L2 는 3칸으로" in text and '"id": "g2"' in text and "<!--" not in text
    dry = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy", "dry": True}).json()
    assert dry["chars"] == len(dry["prompt"]) and dry["groups"] >= 4 and dry["model"] == "claude-opus-5-5" and "## 이번 요청" not in dry["prompt"]
    with pytest.raises(KeyError):
        A.material(s.doc, s.outline, "999")


def test_check_plan_filters_unknown_and_keeps_unmentioned(sess):
    _, _, s = sess
    mat = A.material(s.doc, s.outline, "3")
    data = {"summary": "L2 를 4칸으로", "levels": [
        {"level": 2, "rep": "g2", "match": ["g1", "g9", "g2"], "keep": [{"group": "zz", "why": "?"}], "why": "까닭"},
        {"level": 7, "rep": "g1", "match": [], "keep": [], "why": ""}]}
    p = A.check_plan(mat, data)
    l1, l2 = p["levels"]
    assert l1["rep"]["group"] == l1["was"] == "g1" and not l1["rep"]["changed"] and not l1["match"]  # 답에 없는 레벨 — 그대로
    assert l2["rep"] == {"group": "g2", "para": "p5209", "count": 1, "sample": l2["rep"]["sample"], "changed": True} and l2["was"] == "g1"
    assert [m["group"] for m in l2["match"]] == ["g1"] and l2["match"][0]["count"] == 5 and l2["match"][0]["diff"] == [["lead", "앞 공백", "4칸", "3칸"]]  # 새 대표 기준
    assert [(k["group"], k["auto"]) for k in l2["keep"]] == [("g3", True)] and l2["change"] == 5 and p["change"] == 5
    assert any("g9" in n for n in p["notes"]) and any("zz" in n for n in p["notes"]) and any("L7" in n for n in p["notes"])
    assert A.check_plan(mat, {})["change"] == 0  # 빈 답 — 아무것도 안 바꿈


def test_check_plan_split_names_variant_templates(sess):
    """넷째 고르기 split(② §8-5) — 항목 하나 = 새 서식 종속 템플릿 하나(「T9L2a」): 대표 갈래 + 그 대표에 맞춰 같이 옮길 갈래."""
    c, d, s = sess
    mat = A.material(s.doc, s.outline, "9")  # T9 「[기관] › o › -」 L2 「o」 — g1 ×31(대표) · g2 ×9 · g3 ×2 · g4 ×1 · g5 ×1
    l2 = next(lv for lv in mat["levels"] if lv["level"] == 2)
    assert [g["count"] for g in l2["groups"]] == [31, 9, 2, 1, 1] and all(g["noSplit"] is None for g in l2["groups"]) and l2["taken"] == []
    raw = {g["id"]: g["raw"] for g in l2["groups"]}
    data = {"summary": "", "levels": [{"level": 2, "rep": "g1", "match": ["g4"], "keep": [{"group": "g5", "why": "모름"}], "why": "", "split": [
        {"rep": "g2", "match": ["g3", "g4", "g9"], "why": "기관 줄"}, {"rep": "g1", "match": [], "why": ""}, {"rep": "zz", "match": [], "why": ""}]}]}
    p = A.check_plan(mat, data)
    lv = next(x for x in p["levels"] if x["level"] == 2)
    assert len(lv["split"]) == 1 and lv["taken"] == []
    sp = lv["split"][0]
    assert sp["name"] == "T9L2a" and sp["sfx"] == "a" and sp["why"] == "기관 줄" and sp["rep"]["group"] == "g2" and sp["rep"]["count"] == 9
    assert sp["rep"]["diff"] == M.diff(raw["g1"], raw["g2"])  # 원래 템플릿의 대표 기준
    assert [m["group"] for m in sp["match"]] == ["g3"] and sp["match"][0]["diffTo"] == M.diff(raw["g2"], raw["g3"])  # 새 템플릿의 대표 기준
    assert sp["match"][0]["diff"] == M.diff(raw["g1"], raw["g3"])  # diff 는 다른 줄과 같이 이 레벨 대표 기준
    assert sp["moved"] == 11 and sp["change"] == 2 and [m["group"] for m in lv["match"]] == ["g4"] and [k["group"] for k in lv["keep"]] == ["g5"]
    assert lv["change"] == 3 and lv["moved"] == 11 and p["change"] == 3 and p["moved"] == 11
    for word in ("g9", "zz", "대표라 뗄 수 없음", "두 번"):
        assert any(word in n for n in p["notes"]), word
    # 번호형 레벨에서 같은 부모 아래 형제의 일부는 못 뗀다 — 자료의 cannotSplit · 계획은 그대로 둠
    mat5 = A.material(s.doc, s.outline, "5")  # T5 「가. › (N)」
    l1 = mat5["levels"][0]
    gid = next(g["id"] for g in l1["groups"] if g["noSplit"] and not g["rep"])
    assert any(g.get("cannotSplit") for g in A.prompt_material(mat5)["levels"][0]["groups"]) and "cannotSplit" in A.CONTRACT
    p5 = A.check_plan(mat5, {"levels": [{"level": 1, "rep": "g1", "match": [], "keep": [], "split": [{"rep": gid, "match": [], "why": ""}], "why": ""}]})
    assert not p5["levels"][0]["split"] and next(k for k in p5["levels"][0]["keep"] if k["group"] == gid)["noSplit"] and any("뗄 수 없어" in n for n in p5["notes"])
    # 이미 뗀 글자는 건너뛴다 · 서식 종속 템플릿도 정리 대상(자료에 「어디서 뗐나」)
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": [l2["groups"][1]["para"]]}).status_code == 200
    mat = A.material(s.doc, s.outline, "9")
    l2 = next(lv for lv in mat["levels"] if lv["level"] == 2)
    assert l2["taken"] == ["a"] and [g["count"] for g in l2["groups"]] == [31, 2, 1, 1]
    p = A.check_plan(mat, {"levels": [{"level": 2, "rep": "g1", "match": [], "keep": [], "split": [{"rep": "g2", "match": [], "why": ""}], "why": ""}]})
    assert next(x for x in p["levels"] if x["level"] == 2)["split"][0]["name"] == "T9L2b"
    sub = A.prompt_material(A.material(s.doc, s.outline, "9~2a"))["template"]
    assert sub["no"] == "T9L2a" and "T9 L2" in sub["subordinate"] and "L2 부터" in sub["subordinate"]
    _undo_all(c, d, s)


def test_plan_with_split_applies_in_one_undo(sess, monkeypatch):
    c, d, s = sess

    def fake(schema, content, what, **kw):
        assert "split" in schema["properties"]["levels"]["items"]["required"] and "## 맞출 갈래 · 다른 템플릿으로 뗄 갈래" in content
        return {"data": {"summary": "기관 줄은 따로", "levels": [{"level": 2, "rep": "g1", "match": ["g4"], "keep": [], "split": [{"rep": "g2", "match": ["g3"], "why": "다른 서식"}], "why": ""}]},
                "backend": "api", "ms": 5, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    j = c.post(f"/api/docs/{d}/outline/agent/9/plan", json={"skill": "tidy"}).json()
    lv = next(x for x in j["plan"]["levels"] if x["level"] == 2)
    sp = lv["split"][0]
    assert j["plan"]["moved"] == 11 and sp["name"] == "T9L2a"
    body = {"rev": j["rev"], "by": "agent", "levels": [{"level": 2, "rep": lv["rep"]["para"], "likes": [m["para"] for m in lv["match"]],  # 화면(tpl_agent.js tpaTodo)이 보내는 꼴
            "splits": [{"likes": [sp["rep"]["para"]] + [m["para"] for m in sp["match"]], "rep": sp["rep"]["para"], "sfx": sp["sfx"]}]}]}
    undo = s.state()["undo"]
    r = c.post(f"/api/docs/{d}/outline/templates/9/match", json=body)
    assert r.status_code == 200, r.text
    assert len(r.json()["changed"]) == 3 and r.json()["splits"][0]["no"] == "9L2a" and r.json()["splits"][0]["changed"] == 2 and s.state()["undo"] == undo + 1
    got = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["9"]   # 받은 계획은 남고 적용하면 applied(분석 상태의 서식 LLM 칸 — spec_작업 ② §20)
    assert got["state"] == "applied" and got["applied"]["changed"] == 3 and got["plan"]["summary"] == "기관 줄은 따로"
    assert _slot(c, d, 9, 2)["total"] == 33 and _slot(c, d, "9~2a", 2)["total"] == 11 and len(_slot(c, d, "9~2a", 2)["groups"]) == 1
    _undo_all(c, d, s)
    assert "9~2a" not in s.outline["templates"]


def test_plan_endpoint_uses_pinned_opus_and_saved_skill(sess, monkeypatch):
    c, d, s = sess
    seen = {}

    def fake(schema, content, what, **kw):
        seen.update(kw, content=content, what=what)
        return {"data": {"summary": "정리", "levels": [{"level": 2, "rep": "g1", "match": ["g2", "g3"], "keep": [], "why": "5줄"}]},
                "backend": "api", "ms": 12, "costUsd": 0.01, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    monkeypatch.setenv("NFM_LLM_MODEL_FORCE", "claude-fable-5-2")  # 모든 호출을 Fable 로 돌려도 이 에이전트는 Opus 5.5
    A.save("tidy", "템플릿 서식 정리", "내가 고친 기준 글")
    r = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy", "request": "  앞 공백 3칸  "})
    assert r.status_code == 200, r.text
    j = r.json()
    assert seen["model"] == "claude-opus-5-5" and seen["pin"] is True and seen["what"] == "tpl-agent"
    assert "내가 고친 기준 글" in seen["content"] and "앞 공백 3칸" in seen["content"] and "## 대표 고르기" not in seen["content"]
    assert j["rev"] == s.rev and j["skill"]["version"] == 1 and j["request"] == "앞 공백 3칸" and j["model"] == "claude-opus-5-5" and j["plan"]["change"] == 2
    kept = c.get(f"/api/docs/{d}/outline/agent/plans").json()
    assert kept["rev"] == s.rev and kept["plans"]["3"]["state"] == "planned" and kept["plans"]["3"]["applied"] is None and kept["plans"]["3"]["plan"]["change"] == 2
    assert c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "nope"}).status_code == 404
    assert c.post(f"/api/docs/{d}/outline/agent/999/plan", json={"skill": "tidy"}).status_code == 404


def test_llm_pin_beats_forced_model(monkeypatch):
    monkeypatch.setenv("NFM_LLM_MODEL_FORCE", "claude-fable-5-2")
    assert llm.call({}, "x", "t", model="claude-opus-5-5", pin=True)["model"] == "claude-opus-5-5"
    assert llm.call({}, "x", "t", model="claude-opus-5-5")["model"] == "claude-fable-5-2"  # 고정하지 않은 호출은 전처럼 FORCE 가 먼저
    assert llm.call({}, "x", "t", pin=True)["model"] == "claude-fable-5-2"  # 모델 없이 pin 만 — 뜻 없음


def test_plan_endpoint_llm_off_is_503(sess):
    c, d, _ = sess
    assert c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).status_code == 503


# ---------------------------------------------------------------- 템플릿 단위 맞추기(적용)
def test_template_match_all_levels_one_undo(sess):
    c, d, s = sess
    before = s.state()["undo"]
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={})
    assert r.status_code == 200, r.text
    j = r.json()
    lv2 = next(x for x in j["levels"] if x["level"] == 2)
    assert lv2 == {"level": 2, "rep": "p6502", "repChanged": False, "changed": 2} and {"p5209", "p5765"} <= set(j["changed"])
    assert s.state()["undo"] == before + 1  # 레벨이 여럿이어도 실행 취소 한 칸
    assert _slot(c, d, 3, 2)["others"] == 0 and all(_slot(c, d, 3, lv)["others"] == 0 for lv in ("1", "2"))
    assert c.post(f"/api/docs/{d}/outline/templates/3/match", json={}).json()["nothing"] is True
    _undo_all(c, d, s)
    assert _slot(c, d, 3, 2)["others"] == 2


def test_template_match_with_new_rep_and_chosen_groups(sess):
    c, d, s = sess
    rev = s.rev
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"rev": rev, "by": "agent", "levels": [{"level": 2, "rep": "p5209", "likes": ["p6502"]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["levels"] == [{"level": 2, "rep": "p5209", "repChanged": True, "changed": 5}] and "p5765" not in j["changed"]
    v = _slot(c, d, 3, 2)
    assert v["rep"] == "p5209" and v["groups"][0]["count"] == 6 and v["others"] == 1  # p5765(레터 뒤 공백 없음)는 고르지 않아 그대로
    assert M.parts(s.doc, s.outline, "p6502")[0] == "    "  # 새 대표의 앞 공백 4칸
    assert c.post(f"/api/docs/{d}/outline/templates/3/match", json={"rev": rev, "levels": [{"level": 2}]}).status_code == 409  # 옛 차례의 계획
    _undo_all(c, d, s)
    assert _slot(c, d, 3, 2)["rep"] == "p6502"


def test_template_match_rep_only_changes_overlay_not_document(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"levels": [{"level": 2, "rep": "p5209", "likes": []}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["changed"] == [] and j["reps"] == 1 and "tops" not in j and j["outline"]["templates"]["3"]["slots"]["2"]["rep"] == "p5209"
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()  # 문서는 그대로
    _undo_all(c, d, s)
    assert _slot(c, d, 3, 2)["rep"] == "p6502"


def test_template_match_rejects_bad_input(sess):
    c, d, _ = sess
    u = f"/api/docs/{d}/outline/templates"
    assert c.post(f"{u}/999/match", json={}).status_code == 404
    assert c.post(f"{u}/3/match", json={"levels": [{"level": 9}]}).status_code == 404
    assert c.post(f"{u}/3/match", json={"levels": [{"level": 2, "rep": "p1"}]}).status_code == 400  # 그 레벨 줄이 아님
    assert c.post(f"{u}/3/match", json={"levels": [{"level": 2}, {"level": 2}]}).status_code == 400
    assert c.post(f"{u}/3/match", json={"levels": [{"level": 0}]}).status_code == 400
    assert c.post(f"{u}/3/match", json={"levels": "x"}).status_code == 400
