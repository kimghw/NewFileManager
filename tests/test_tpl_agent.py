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


@pytest.fixture(autouse=True)
def _fresh_plans(request, monkeypatch):
    """받아 둔 서식 계획은 문서 차례가 아니라 그 템플릿 줄의 지문에 묶인다(spec_hwpx_웹편집 ② §8-4 「계획은 줄 지문에」) — 반영을 되돌리면 **다시 쓸 수 있는 계획으로 살아난다**.
    모듈 세션 하나를 시험들이 이어 쓰므로 앞 시험의 계획이 뒤 시험의 「모두 반영」 에 섞이지 않게 시험마다 비운다.
    「모두 반영」 은 확실한 템플릿 종속도 저절로 건다(② §8-2 「종속 제안」) — 이 모듈은 서식 계획만 보므로 종속 제안을 끈다(그것은 tests/test_outline_safety.py 가 본다)."""
    monkeypatch.setattr(M, "merge_hints", lambda ov: [])
    if "sess" in request.fixturenames:
        from app import tpl_agent_api as TA
        _, _, s = request.getfixturevalue("sess")
        with TA._plans_lock:
            s.tpl_plans = {"graph": None, "plans": {}}
    yield


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
    assert g1["currentRep"] and g1["values"]["레터 앞 빈칸"] == "3칸" and "values" not in g2 and ["레터 앞 빈칸", "3칸", "4칸"] in g2["differsFromRep"]
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
    assert [m["group"] for m in l2["match"]] == ["g1"] and l2["match"][0]["count"] == 5 and l2["match"][0]["diff"] == [["lead", "레터 앞 빈칸", "4칸", "3칸"]]  # 새 대표 기준
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
    r = c.post(f"/api/docs/{d}/outline/templates/9/match", json={**body, "place": False})
    assert r.status_code == 200, r.text
    assert len(r.json()["changed"]) == 3 and r.json()["splits"][0]["no"] == "9L2a" and r.json()["splits"][0]["changed"] == 2 and s.state()["undo"] == undo + 1
    got = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["9"]   # 받은 계획은 남고 적용하면 applied(분석 상태의 서식 LLM 칸 — spec_작업 ② §20)
    assert got["state"] == "applied" and got["applied"]["changed"] == 3 and got["plan"]["summary"] == "기관 줄은 따로"
    assert _slot(c, d, 9, 2)["total"] == 33 and _slot(c, d, "9~2a", 2)["total"] == 11 and len(_slot(c, d, "9~2a", 2)["groups"]) == 1
    assert s.outline["agent"]["9"] == got["at"]   # 반영의 표는 개요 오버레이에(실행 취소와 함께 되돌아간다 — tpl_agent_api._mark)
    _undo_all(c, d, s)
    assert "9~2a" not in s.outline["templates"]
    back = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["9"]   # 반영을 되돌리면 「반영함」 이 아니다 — 오버레이의 표가 사라지고, 줄이 계획을 받은 때로 돌아왔으니 **그 계획을 다시 쓸 수 있다**(planned — 다시 받지 않는다)
    assert back["state"] == "planned" and back["applied"]["changed"] == 3 and "9" not in (s.outline.get("agent") or {})


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
    r = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy", "request": "  레터 앞 빈칸 3칸  "})
    assert r.status_code == 200, r.text
    j = r.json()
    assert seen["model"] == "claude-opus-5-5" and seen["pin"] is True and seen["what"] == "tpl-agent"
    assert "내가 고친 기준 글" in seen["content"] and "레터 앞 빈칸 3칸" in seen["content"] and "## 대표 고르기" not in seen["content"]
    assert j["rev"] == s.rev and j["skill"]["version"] == 1 and j["request"] == "레터 앞 빈칸 3칸" and j["model"] == "claude-opus-5-5" and j["plan"]["change"] == 2
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
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False})
    assert r.status_code == 200, r.text
    j = r.json()
    lv2 = next(x for x in j["levels"] if x["level"] == 2)
    assert lv2 == {"level": 2, "rep": "p6502", "repChanged": False, "changed": 2} and {"p5209", "p5765"} <= set(j["changed"])
    assert s.state()["undo"] == before + 1  # 레벨이 여럿이어도 실행 취소 한 칸
    assert _slot(c, d, 3, 2)["others"] == 0 and all(_slot(c, d, 3, lv)["others"] == 0 for lv in ("1", "2"))
    assert c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False}).json()["nothing"] is True
    _undo_all(c, d, s)
    assert _slot(c, d, 3, 2)["others"] == 2


def test_template_match_with_new_rep_and_chosen_groups(sess):
    c, d, s = sess
    rev = s.rev
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False, "rev": rev, "by": "agent", "levels": [{"level": 2, "rep": "p5209", "likes": ["p6502"]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["levels"] == [{"level": 2, "rep": "p5209", "repChanged": True, "changed": 5}] and "p5765" not in j["changed"]
    v = _slot(c, d, 3, 2)
    assert v["rep"] == "p5209" and v["groups"][0]["count"] == 6 and v["others"] == 1  # p5765(레터 뒤 공백 없음)는 고르지 않아 그대로
    assert M.parts(s.doc, s.outline, "p6502")[0] == "    "  # 새 대표의 앞 공백 4칸
    assert c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False, "rev": rev, "levels": [{"level": 2}]}).status_code == 409  # 옛 차례의 계획
    _undo_all(c, d, s)
    assert _slot(c, d, 3, 2)["rep"] == "p6502"


def test_template_match_rep_only_changes_overlay_not_document(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False, "levels": [{"level": 2, "rep": "p5209", "likes": []}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["changed"] == [] and j["reps"] == 1 and "tops" not in j and j["outline"]["templates"]["3"]["slots"]["2"]["rep"] == "p5209"
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()  # 문서는 그대로
    _undo_all(c, d, s)
    assert _slot(c, d, 3, 2)["rep"] == "p6502"


def test_template_match_rejects_bad_input(sess):
    c, d, _ = sess
    u = f"/api/docs/{d}/outline/templates"
    assert c.post(f"{u}/999/match", json={"place": False}).status_code == 404
    assert c.post(f"{u}/3/match", json={"place": False, "levels": [{"level": 9}]}).status_code == 404
    assert c.post(f"{u}/3/match", json={"place": False, "levels": [{"level": 2, "rep": "p1"}]}).status_code == 400  # 그 레벨 줄이 아님
    assert c.post(f"{u}/3/match", json={"place": False, "levels": [{"level": 2}, {"level": 2}]}).status_code == 400
    assert c.post(f"{u}/3/match", json={"place": False, "levels": [{"level": 0}]}).status_code == 400
    assert c.post(f"{u}/3/match", json={"place": False, "levels": "x"}).status_code == 400


# ---------------------------------------------------------------- 받아 둔 계획을 한 번에 반영(② §8-4 — 2026-11-16 사용자 답 「확인 뒤 한 번에 반영」)
def test_todo_is_the_agent_choice_as_an_apply_body(sess):
    """A.todo = 계획을 에이전트가 고른 그대로 반영할 때의 몸(화면 tpaTodoOf 와 같은 셈) — 맞추기·떼기로 고른 갈래만, 「그대로」 는 빼고, 고른 갈래가 없는 레벨은 없다."""
    c, d, s = sess
    mat = A.material(s.doc, s.outline, "9")
    p = A.check_plan(mat, {"summary": "", "levels": [{"level": 2, "rep": "g1", "match": ["g4"], "keep": [{"group": "g5", "why": "예외"}], "why": "",
                                                      "split": [{"rep": "g2", "match": ["g3"], "why": "레터가 다름"}]}]})
    lv = next(x for x in p["levels"] if x["level"] == 2)
    sp = lv["split"][0]
    t = A.todo(p)
    assert (t["n"], t["moved"]) == (p["change"], p["moved"]) == (3, 11)
    assert t["levels"] == [{"level": 2, "rep": lv["rep"]["para"], "likes": [lv["match"][0]["para"]],
                            "splits": [{"likes": [sp["rep"]["para"], sp["match"][0]["para"]], "rep": sp["rep"]["para"], "sfx": "a"}]}]
    keep_only = A.check_plan(mat, {"summary": "", "levels": [{"level": 2, "rep": "g1", "match": [], "keep": [], "split": [], "why": ""}]})   # 말하지 않은 갈래는 「그대로」 — 바꿀 것 없음
    assert A.todo(keep_only) == {"levels": [], "n": 0, "moved": 0, "reps": 0} and A.todo(None) == {"levels": [], "n": 0, "moved": 0, "reps": 0}   # reps = 대표를 바꾸는 레벨 수
    assert t["reps"] == 0


def test_todo_keeps_a_level_that_only_changes_the_rep(sess):
    """계획이 대표만 바꾸는 레벨(맞출 갈래도 뗄 갈래도 없음)도 적용 몸에 든다 — 전에는 그 레벨을 버려 에이전트가 고른 대표가 걸리지 않았다(2026-11-16 astra). 화면 tpaTodoOf 도 같은 셈."""
    _, _, s = sess
    mat = A.material(s.doc, s.outline, "3")
    p = A.check_plan(mat, {"summary": "", "levels": [{"level": 2, "rep": "g2", "match": [], "keep": [{"group": "g1", "why": "예외"}, {"group": "g3", "why": "예외"}], "split": [], "why": ""}]})
    lv = next(x for x in p["levels"] if x["level"] == 2)
    assert lv["rep"]["para"] == "p5209" and lv["rep"]["changed"] and not lv["match"] and not lv["split"] and p["change"] == 0
    assert A.todo(p) == {"levels": [{"level": 2, "rep": "p5209", "likes": []}], "n": 0, "moved": 0, "reps": 1}
    both = A.check_plan(mat, {"summary": "", "levels": [{"level": 2, "rep": "g2", "match": ["g1"], "keep": [], "split": [], "why": ""}]})   # 대표를 바꾸면서 맞추는 레벨 — 대표 변경에도 센다
    assert (A.todo(both)["n"], A.todo(both)["reps"]) == (5, 1)


def test_apply_plans_applies_a_level_that_only_changes_the_rep(sess, monkeypatch):
    """「모두 반영」 은 대표만 바꾸는 레벨도 반영한다 — 대표를 바꾼 뒤 새 대표와 그 갈래는 **같은 반영에서** 확정 서식이 된다(실행 취소 1 · spec_hwpx_웹편집 ② §8-8).
    분석 상태는 「맞출 줄 0 · 대표 변경 1」 을 반영할 것으로 센다(서식 항목의 reps) — 「전체 실행」 이 그것으로 조정을 돌린다."""
    from app import outline_conform as OC
    from app import outline_pos as OP
    from app.hwpx_doc import NB
    c, d, s = sess
    url = f"/api/docs/{d}/outline/agent/apply"
    assert c.post(url, json={"rev": s.rev}).status_code == 200 and not OC.pending(s.doc, s.outline)   # 자리를 먼저 다 맞춘다(받아 둔 계획 없이) — 그 뒤에 받은 계획이라야 줄 지문이 맞는다
    answer = {"summary": "L2 대표만", "levels": [{"level": 2, "rep": "g2", "match": [], "keep": [{"group": "g1", "why": "예외"}, {"group": "g3", "why": "예외"}], "split": [], "why": ""}]}
    monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
    assert c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).status_code == 200
    fmt = lambda: next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")  # noqa: E731
    row = next(x for x in fmt()["llm"]["list"] if x["tpl"] == "3")
    assert (row["state"], row["change"], row["moved"], row["reps"]) == ("planned", 0, 0, 1) and fmt()["llm"]["reps"] == 1
    undo = s.state()["undo"]
    r = c.post(url, json={"rev": s.rev, "plans": {"3": row["at"]}})
    assert r.status_code == 200, r.text
    j = r.json()
    assert not j.get("nothing") and s.state()["undo"] == undo + 1 and j["plans"] == 1 and j["reps"] == 1
    assert [(t["tpl"], t["changed"], t["levels"], t["splits"]) for t in j["templates"]] == [("3", 0, [{"level": 2, "rep": "p5209", "repChanged": True, "changed": 0}], [])]
    assert _slot(c, d, 3, 2)["rep"] == "p5209" and j["changed"] == j["placed"] == ["p5209"]            # 맞춘 줄은 없다 — 새 대표의 자리만
    at = OP.Measure(s.doc).place("p5209", "-")
    assert M.parts(s.doc, s.outline, "p5209")[2] == NB and abs(at["line2Mm"] - at["textMm"]) < 0.02 and not OC.pending(s.doc, s.outline, {"3"})
    assert c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["3"]["state"] == "applied"
    left = next(x for x in fmt()["llm"]["list"] if x["tpl"] == "3")                                   # 반영한 뒤에도 남긴 줄을 센다 — 에이전트가 「그대로」 로 답한 옛 대표 갈래 ×5 · ×1
    assert left["state"] == "applied" and left["left"] == {"kept": 6, "unanswered": 0} and fmt()["llm"]["left"] == {"kept": 6, "unanswered": 0}
    assert c.post(f"/api/docs/{d}/undo").status_code == 200                                           # 한 번에 되돌아간다 — 대표도 자리도
    assert _slot(c, d, 3, 2)["rep"] == "p6502" and M.parts(s.doc, s.outline, "p5209")[2] == " " and s.state()["undo"] == undo
    _undo_all(c, d, s)


def test_plan_gives_a_rep_to_a_level_that_has_none(sess, monkeypatch):
    """대표가 없고 갈래가 하나뿐인 레벨 — 맞춘 레벨로 세지 않고(분석 상태의 aligned · noRep), 계획이 대표를 정하면 「모두 반영」 이 그 대표를 걸고 그 레벨을 확정 서식으로 한다."""
    from app import outline_conform as OC
    c, d, s = sess
    fmt = lambda: next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")  # noqa: E731
    a0 = fmt()["aligned"]
    was = s.outline["templates"]["3"]["slots"]["1"]["rep"]
    s.outline["templates"]["3"]["slots"]["1"]["rep"] = None                # 대표가 없는 레벨을 흉내 낸다(대표 줄이 지워진 레벨 · 옛 그래프) — T3 L1 「o」 ×9 · 서식 1가지
    try:
        v = _slot(c, d, 3, 1)
        assert v["repMissing"] and len(v["groups"]) == 1
        f0 = fmt()
        assert (f0["aligned"], f0["noRep"]) == (a0 - 1, 1) and "대표 없는 레벨 1" in f0["apply"]["text"]   # 갈래가 하나여도 대표가 없으면 맞춘 레벨이 아니다
        answer = {"summary": "L1 대표", "levels": [{"level": 1, "rep": "g1", "match": [], "keep": [], "split": [], "why": ""}]}
        monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
        p = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).json()["plan"]
        l1 = next(x for x in p["levels"] if x["level"] == 1)
        assert l1["single"] and l1["was"] is None and l1["rep"]["changed"] and l1["rep"]["para"] == v["groups"][0]["key"]
        assert A.todo(p) == {"levels": [{"level": 1, "rep": l1["rep"]["para"], "likes": []}], "n": 0, "moved": 0, "reps": 1}
        r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"rev": s.rev})
        assert r.status_code == 200, r.text
        t3 = next(t for t in r.json()["templates"] if t["tpl"] == "3")
        assert t3["levels"] == [{"level": 1, "rep": l1["rep"]["para"], "repChanged": True, "changed": 0}]
        assert _slot(c, d, 3, 1)["rep"] == l1["rep"]["para"] and not _slot(c, d, 3, 1)["repMissing"] and fmt()["noRep"] == 0
        assert set(M.slot_ids(s.outline, "3", 1)) <= set(r.json()["placed"]) and not OC.pending(s.doc, s.outline, {"3"})   # 대표가 생긴 레벨의 줄이 같은 반영에서 확정 서식으로
    finally:
        _undo_all(c, d, s)
        s.outline["templates"]["3"]["slots"]["1"]["rep"] = was


def test_applied_plan_still_reports_the_lines_it_left(sess, monkeypatch):
    """반영한 뒤에도 계획이 남긴 줄을 따로 센다(서식 항목의 left) — 에이전트가 「그대로」 로 답한 줄(kept) · 답이 없어 안 바꾼 줄(unanswered — 검토한 것이 아니다).
    전에는 「받음」 상태에서만 세어, 반영하면 사라지고 다음 「전체 실행」 이 「남은 것 없음」 이라 했다(2026-11-16 astra). 지금 문서의 갈래로 다시 센다 — 그 뒤 사람이 맞춘 갈래는 빠진다."""
    c, d, s = sess
    answer = {"summary": "T9", "levels": [{"level": 2, "rep": "g1", "match": ["g4"], "keep": [{"group": "g5", "why": "예외"}], "split": [], "why": ""}]}   # L2 의 g2 ×9 · g3 ×2 와 L1 의 다른 갈래는 답 없음
    monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
    p = c.post(f"/api/docs/{d}/outline/agent/9/plan", json={"skill": "tidy"}).json()["plan"]
    assert p["left"]["kept"] == 1 and p["left"]["unanswered"] >= 11
    fmt = lambda: next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]  # noqa: E731
    row = lambda: next(x for x in fmt()["list"] if x["tpl"] == "9")  # noqa: E731
    before = row()
    assert (before["state"], before["change"], before["kept"], before["unanswered"]) == ("planned", 1, 1, p["left"]["unanswered"]) and "left" not in before
    assert fmt()["left"] == {"kept": 0, "unanswered": 0}                                                # 아직 반영한 계획이 없다
    assert c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev}).status_code == 200
    after = row()
    assert after["state"] == "applied" and after["left"] == {"kept": 1, "unanswered": p["left"]["unanswered"]} and "kept" not in after
    f = fmt()
    assert f["left"] == after["left"] and (f["kept"], f["unanswered"]) == (0, 0)                        # 받아 둔(반영 전) 계획의 수와 따로
    nine = next(k["para"] for k in next(x for x in p["levels"] if x["level"] == 2)["keep"] if k["count"] == 9 and k["auto"])
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/match", json={"place": False, "like": nine}).status_code == 200   # 사람이 답 없던 ×9 갈래를 대표에 맞춘다
    assert row()["left"] == {"kept": 1, "unanswered": p["left"]["unanswered"] - 9}
    assert c.post(f"/api/docs/{d}/undo").status_code == 200 and c.post(f"/api/docs/{d}/undo").status_code == 200   # 반영까지 되돌리면 「반영함」 이 아니다 — 남긴 것은 다시 계획의 수로
    back = row()
    assert back["state"] == "planned" and "left" not in back and back["unanswered"] == p["left"]["unanswered"]
    _undo_all(c, d, s)


def test_left_lines_survive_when_only_the_key_line_of_an_unanswered_variant_is_matched(sess, monkeypatch):
    """대표를 못 고른 레벨의 답 없는 갈래도 지문(sig)으로 남긴 줄을 센다 — 열쇠 줄만 대표에 맞춰도 그 갈래의 나머지 줄은 「답이 없어 안 바꾼 줄」 로 남는다(2026-11-17 astra 2차 검토 2번).
    전에는 대표가 없는 레벨의 keep 에 지문이 없어 열쇠 줄로만 찾았고, 사람이 열쇠 줄 하나만 맞추면 남은 줄이 0 으로 사라져 조정 칸이 다시 ✓ 가 될 수 있었다."""
    c, d, s = sess
    was = s.outline["templates"]["3"]["slots"]["2"]["rep"]
    s.outline["templates"]["3"]["slots"]["2"]["rep"] = None                # T3 L2 「-」 를 대표 없는 레벨로 — 갈래 ×5(열쇠 줄 a) · p5209 · p5765
    try:
        v = _slot(c, d, 3, 2)
        assert v["repMissing"] and [g["count"] for g in v["groups"]] == [5, 1, 1]
        a = v["groups"][0]["key"]
        monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": {"summary": "모름", "levels": []}, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
        p = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).json()["plan"]   # 에이전트도 대표를 못 고름 — 모두 답 없음
        l2 = next(x for x in p["levels"] if x["level"] == 2)
        assert l2["rep"] is None and [(k["count"], k["auto"]) for k in l2["keep"]] == [(5, True), (1, True), (1, True)]
        assert all(k.get("sig") for k in l2["keep"]) and len({k["sig"] for k in l2["keep"]}) == 3              # 대표를 못 고른 레벨의 갈래에도 지문이 남는다
        assert c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev}).status_code == 200   # 바꿀 것 없는 계획 — 「반영함」 으로
        row = lambda: next(x for x in next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]["list"] if x["tpl"] == "3")  # noqa: E731
        assert row()["state"] == "applied" and row()["left"] == {"kept": 0, "unanswered": 7}
        assert c.put(f"/api/docs/{d}/outline/slots/3/2/rep", json={"para": "p5209"}).status_code == 200            # 사람이 p5209 를 대표로 정하고
        r = c.post(f"/api/docs/{d}/outline/slots/3/2/match", json={"place": False, "paras": [a]})                   # ×5 갈래의 **열쇠 줄만** 맞춘다
        assert r.status_code == 200 and r.json()["changed"] == [a]
        now = _slot(c, d, 3, 2)
        assert [g["count"] for g in now["groups"]] == [2, 4, 1] and now["groups"][1]["key"] != a                    # 그 갈래의 나머지 4줄은 서식 그대로 — 열쇠 줄만 바뀌었다
        assert row()["left"] == {"kept": 0, "unanswered": 5}                                                        # 남은 4줄 + p5765(대표가 된 p5209 는 빠진다)
    finally:
        _undo_all(c, d, s)
        s.outline["templates"]["3"]["slots"]["2"]["rep"] = was


def test_rep_chosen_by_an_agent_plan_does_not_lock_like_a_persons_choice(sess, monkeypatch):
    """에이전트 계획이 정한 대표는 사람이 정한 대표처럼 잠기지 않는다(2026-11-17 astra 2차 검토 — 전에는 계획 반영도 `repSet` 을 켜서, 다음 계획이 그 대표를 「사람이 정한 것」 으로 보고 못 바꿨다).
    출처를 따로 남긴다: 사람(대표 정하기 · 대표 미리보기의 묶음 맞추기) = repSet(잠김) · 서식 정리 계획(조정 「모두 반영」 · ★ 「적용」 · 「계획대로 맞추기」) = agentRep(안 잠김).
    실행 취소 · 2단계 다시 돌리기(carry)에서도 출처가 그대로 따라온다."""
    from app import outline_edit as OE
    c, d, s = sess
    answer = {"summary": "", "levels": [{"level": 2, "rep": "g2", "match": ["g1"], "keep": [], "split": [], "why": ""}]}   # T3 L2 — 대표를 p5209 로 바꾸고 옛 대표 갈래 ×5 를 맞춘다
    monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": answer, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
    slot = lambda: s.outline["templates"]["3"]["slots"]["2"]  # noqa: E731
    level = lambda: next(x for x in A.material(s.doc, s.outline, "3")["levels"] if x["level"] == 2)  # noqa: E731
    shown = lambda: next(x for x in A.prompt_material(A.material(s.doc, s.outline, "3"))["levels"] if x["level"] == 2)  # noqa: E731
    assert M.rep_origin(slot()) is None and not level()["repSet"]                                              # 헤딩 그래프가 뽑은 대표 — 출처 없음
    assert c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).status_code == 200
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev})                   # 조정 「모두 반영」
    assert r.status_code == 200 and len(r.json()["changed"]) == 5
    assert slot()["rep"] == "p5209" and not slot().get("repSet") and M.rep_origin(slot()) == "agent"           # 에이전트가 정한 대표 — 잠기지 않는다
    assert not level()["repSet"] and "repChosenByUser" not in shown()                                           # 다음 계획의 자료 — 사람이 정한 대표라 하지 않는다
    again = A.check_plan(A.material(s.doc, s.outline, "3"), {"summary": "", "levels": [{"level": 2, "rep": "g2", "match": ["g1"], "keep": [], "split": [], "why": ""}]})
    l2 = next(x for x in again["levels"] if x["level"] == 2)
    assert l2["rep"]["para"] == "p5765" and l2["rep"]["changed"] and not any("사람이 정한" in n for n in again["notes"])   # 다음 계획은 그 대표를 바꿀 수 있다
    ov = OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)                           # 2단계를 다시 돌린 것과 같이 — 정해 둔 대표는 출처와 함께 옮겨 온다
    assert M.carry(s.outline, ov, M.context(s.doc, ov)) == []
    nsl = ov["templates"]["3"]["slots"]["2"]
    assert nsl["rep"] == "p5209" and not nsl.get("repSet") and M.rep_origin(nsl) == "agent"
    assert c.post(f"/api/docs/{d}/undo").status_code == 200                                                     # 되돌리면 대표도 출처도 처음대로
    assert slot()["rep"] == "p6502" and M.rep_origin(slot()) is None
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False, "by": "agent", "levels": [{"level": 2, "rep": "p5209", "likes": ["p6502"]}]})   # ★ 「적용」 · 「계획대로 맞추기」(템플릿 하나)
    assert r.status_code == 200 and slot()["rep"] == "p5209" and M.rep_origin(slot()) == "agent" and not level()["repSet"]
    assert c.put(f"/api/docs/{d}/outline/slots/3/2/rep", json={"para": "p5209"}).status_code == 200            # 그 줄을 사람이 다시 「대표로」 — 이제 사람이 정한 대표(잠긴다)
    assert slot()["repSet"] and M.rep_origin(slot()) == "user" and "agentRep" not in slot() and level()["repSet"] and shown()["repChosenByUser"] is True
    held = A.check_plan(A.material(s.doc, s.outline, "3"), {"summary": "", "levels": [{"level": 2, "rep": "g2", "match": ["g1"], "keep": [], "split": [], "why": ""}]})
    assert not next(x for x in held["levels"] if x["level"] == 2)["rep"]["changed"] and any("사람이 정한" in n for n in held["notes"])   # 사람이 정한 대표는 계획이 못 바꾼다
    ov = OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)
    M.carry(s.outline, ov, M.context(s.doc, ov))
    assert ov["templates"]["3"]["slots"]["2"]["repSet"] and M.rep_origin(ov["templates"]["3"]["slots"]["2"]) == "user"
    _undo_all(c, d, s)
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={"place": False, "levels": [{"level": 2, "rep": "p5209", "likes": ["p6502"]}]})   # 대표 미리보기의 묶음 맞추기(사람 — by 없음)
    assert r.status_code == 200 and slot()["rep"] == "p5209" and slot()["repSet"] and M.rep_origin(slot()) == "user"
    _undo_all(c, d, s)


def test_template_whose_only_issue_is_a_level_without_a_rep_gets_a_plan(sess, monkeypatch):
    """갈래가 모두 하나뿐이어도 **대표가 없는 레벨**이 있으면 그 템플릿은 계획을 받을 템플릿이다(분석 상태의 need · 계획 끝점 · 「LLM 검증·보완」 의 서식 단계) —
    그래야 「전체 실행」 이 그 레벨에 대표를 줄 수 있다(2026-11-17 astra 2차 검토: ★ 화면은 갈래가 둘 이상인 레벨만 세어 받기 단추를 껐다 — 서버는 이미 받는다)."""
    c, d, s = sess
    fmt = lambda: next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")  # noqa: E731
    assert all(len(v["groups"]) == 1 and v["rep"] for v in c.get(f"/api/docs/{d}/outline/formats").json()["slots"]["7"].values())   # T7 「①」 — 레벨마다 서식 1가지 · 대표 있음
    assert "7" not in [x["tpl"] for x in fmt()["llm"]["list"]] and c.post(f"/api/docs/{d}/outline/agent/7/plan", json={"skill": "tidy"}).status_code == 422   # 정리할 것 없음
    was = s.outline["templates"]["7"]["slots"]["1"]["rep"]
    s.outline["templates"]["7"]["slots"]["1"]["rep"] = None                # 대표가 없는 레벨로(대표 줄이 지워진 레벨 · 옛 그래프)
    try:
        need0 = fmt()["llm"]["need"]
        row = next(x for x in fmt()["llm"]["list"] if x["tpl"] == "7")
        assert row["state"] == "none" and fmt()["noRep"] == 1                                                    # 서식은 1가지여도 계획을 받을 템플릿
        monkeypatch.setattr(llm, "call", lambda schema, content, what, **kw: {"data": {"summary": "", "levels": [{"level": 1, "rep": "g1", "match": [], "keep": [], "split": [], "why": ""}]},
                                                                               "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")})
        r = c.post(f"/api/docs/{d}/outline/agent/7/plan", json={"skill": "tidy"})
        assert r.status_code == 200, r.text
        rep7 = r.json()["plan"]["levels"][0]["rep"]["para"]
        assert A.todo(r.json()["plan"])["reps"] == 1 and next(x for x in fmt()["llm"]["list"] if x["tpl"] == "7")["reps"] == 1
        r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev, "tpls": ["7"]})
        assert r.status_code == 200 and r.json()["reps"] == 1 and s.outline["templates"]["7"]["slots"]["1"]["rep"] == rep7   # 계획이 고른 줄(한 갈래의 열쇠 줄)이 대표
        assert "7" not in [x["tpl"] for x in fmt()["llm"]["list"]] and fmt()["llm"]["need"] == need0 - 1 and fmt()["noRep"] == 0   # 대표가 생기면 정리할 템플릿에서 빠진다
    finally:
        _undo_all(c, d, s)
        s.outline["templates"]["7"]["slots"]["1"]["rep"] = was


def test_apply_plans_applies_every_planned_template_in_one_undo(sess, monkeypatch):
    """POST …/outline/agent/apply — 지금 문서 차례에서 받은 계획 모두(T3 맞추기 · T9 맞추기 + 떼기)를 트랜잭션 하나로: 실행 취소 1 · 계획은 「반영함」 · 문서 차례가 다르면 409."""
    c, d, s = sess
    answers = {"T3": {"summary": "T3 정리", "levels": [{"level": 2, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]},
               "T9": {"summary": "T9 정리", "levels": [{"level": 2, "rep": "g1", "match": ["g4"], "keep": [], "split": [{"rep": "g2", "match": ["g3"], "why": "레터가 다름"}], "why": ""}]},
               "T5": {"summary": "T5 — 바꿀 것 없음", "levels": []}}

    def fake(schema, content, what, **kw):
        key = next(k for k in answers if f'"no": "{k}"' in content)
        return {"data": answers[key], "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    url = f"/api/docs/{d}/outline/agent/apply"
    assert c.post(url, json={"place": False}).status_code == 400 and c.post(url, json={"place": False, "rev": s.rev, "tpls": "3"}).status_code == 400
    assert c.post(url, json={"place": False, "rev": s.rev}).status_code == 409   # 받아 둔 계획이 없다
    for tid in ("3", "9", "5"):
        assert c.post(f"/api/docs/{d}/outline/agent/{tid}/plan", json={"skill": "tidy"}).status_code == 200
    rev, undo = s.rev, s.state()["undo"]
    assert c.post(url, json={"place": False, "rev": rev - 1}).status_code == 409 and c.post(url, json={"place": False, "rev": rev, "tpls": ["999"]}).status_code == 409   # 문서 차례가 다름 · 고른 템플릿에 계획이 없음
    r = c.post(url, json={"place": False, "rev": rev})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["plans"] == 3 and sorted(t["tpl"] for t in j["templates"]) == ["3", "9"] and s.state()["undo"] == undo + 1 and s.rev == rev + 1   # 트랜잭션 하나
    by = {t["tpl"]: t for t in j["templates"]}
    assert (by["3"]["changed"], by["9"]["changed"], len(j["changed"])) == (2, 3, 5) and by["9"]["splits"][0]["no"] == "9L2a" and by["3"]["splits"] == []
    assert j["tops"]["blocks"] and j["outline"]["lines"]
    plans = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert {k: v["state"] for k, v in plans.items()} == {"3": "applied", "9": "applied", "5": "applied"}   # 바꿀 것이 없던 계획(T5)도 반영함으로
    assert (plans["3"]["applied"]["changed"], plans["9"]["applied"]["changed"], plans["5"]["applied"]["changed"]) == (2, 3, 0)
    assert len(_slot(c, d, 3, 2)["groups"]) == 1 and _slot(c, d, "9~2a", 2)["total"] == 11 and len(_slot(c, d, "9~2a", 2)["groups"]) == 1
    assert c.post(url, json={"place": False, "rev": s.rev}).status_code == 409   # 이미 반영함 — 다시 반영할 계획이 없다
    assert {k: s.outline["agent"][k] for k in ("3", "9", "5")} == {k: plans[k]["at"] for k in ("3", "9", "5")}   # 반영의 표 — 계획마다 그 계획의 at
    fmt = lambda: next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]  # noqa: E731
    assert fmt()["done"] == 3
    assert c.post(f"/api/docs/{d}/undo").status_code == 200   # 실행 취소 한 번으로 모든 템플릿이 되돌아간다
    assert len(_slot(c, d, 3, 2)["groups"]) == 3 and "9~2a" not in s.outline["templates"]
    # 반영을 되돌렸다 — 세 계획 모두 「반영함」 이 아니다(진행 줄 「조정」 의 ✓ 가 남지 않는다). 줄이 계획을 받은 때로 돌아왔으니 그 계획들은 **다시 쓸 수 있다**(지문이 같다 — 유료로 다시 받지 않는다)
    back = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert {k: v["state"] for k, v in back.items()} == {"3": "planned", "9": "planned", "5": "planned"} and back["3"]["applied"]["changed"] == 2
    f = fmt()
    assert (f["applied"], f["done"], f["stale"]) == (0, 0, 0) and f["planned"] >= 2 and all(x["state"] == "planned" for x in f["list"] if x["tpl"] in ("3", "9"))
    r = c.post(url, json={"place": False, "rev": s.rev})   # 다시 받지 않고 그대로 반영한다
    assert r.status_code == 200 and r.json()["plans"] == 3 and len(r.json()["changed"]) == 5
    again = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert (again["3"]["state"], again["9"]["state"], again["5"]["state"]) == ("applied", "applied", "applied")
    # 그 템플릿의 줄이 바뀌면(되돌린 뒤 한 줄의 서식을 손으로) 그 계획만 옛것이 된다 — 다른 템플릿의 계획은 그대로
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert c.post(f"/api/docs/{d}/format/chars", json={"id": "p5209", "start": 0, "end": 0, "changes": {"sizePt": 31}}).status_code == 200   # T3 L2 의 줄
    mixed = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert (mixed["3"]["state"], mixed["9"]["state"]) == ("stale", "planned")
    _undo_all(c, d, s)


def test_apply_plans_without_document_change_still_marks_applied(sess, monkeypatch):
    """떼기만 있는 계획(문서는 그대로 — 오버레이만)도 반영하면 「반영함」 이 된다(전에는 「옛 계획」 으로 남았다) · 바꿀 것이 하나도 없으면 nothing."""
    c, d, s = sess

    def fake(schema, content, what, **kw):
        lv = [{"level": 2, "rep": "g1", "match": [], "keep": [], "split": [{"rep": "g2", "match": [], "why": "레터가 다름"}], "why": ""}] if '"no": "T9"' in content else []
        return {"data": {"summary": "", "levels": lv}, "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    for tid in ("9", "5"):
        assert c.post(f"/api/docs/{d}/outline/agent/{tid}/plan", json={"skill": "tidy"}).status_code == 200
    undo = s.state()["undo"]
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev, "tpls": ["5"]})   # 바꿀 것 없음 — 문서 · 오버레이 그대로
    assert r.status_code == 200 and r.json()["nothing"] is True and r.json()["templates"] == [] and s.state()["undo"] == undo
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["changed"] == [] and "tops" not in j and j["templates"][0]["splits"][0]["no"] == "9L2a" and s.state()["undo"] == undo + 1
    plans = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]
    assert plans["9"]["state"] == "applied" and plans["5"]["state"] == "applied" and "9~2a" in s.outline["templates"]
    _undo_all(c, d, s)


def test_applied_plan_is_not_applied_after_discard(sess, monkeypatch):
    """반영한 뒤 「모두 되돌리기」(확정 0 으로 · discard) — 문서가 원본으로 돌아가면 그 계획은 「반영함」 이 아니다. 2026-11-16 사용자 작업에서 난 일:
    17:11 모두 반영 → 17:31 모두 되돌리기 뒤에도 진행 줄 「조정」 이 ✓ 였다(대표와 다른 줄 96 · 「계획 받기」 단추도 숨음)."""
    c, d, s = sess

    def fake(schema, content, what, **kw):
        return {"data": {"summary": "T3 정리", "levels": [{"level": 2, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]},
                "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    assert c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).status_code == 200
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev, "tpls": ["3"]})
    assert r.status_code == 200 and len(r.json()["changed"]) == 2
    assert c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["3"]["state"] == "applied" and len(_slot(c, d, 3, 2)["groups"]) == 1
    r = c.post(f"/api/docs/{d}/commits/0/restore", json={"discard": True})
    assert r.status_code == 200, r.text
    assert len(_slot(c, d, 3, 2)["groups"]) == 3   # 문서가 원본으로 — 서식 갈래가 되돌아왔다
    got = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["3"]
    assert got["state"] == "planned" and got["applied"]["changed"] == 2   # 「반영함」 이 아니다 — 문서가 계획을 받은 때로 돌아왔으니 그 계획을 다시 쓸 수 있다(다시 받지 않는다)
    f = next(i for i in c.get(f"/api/docs/{d}/analysis").json()["items"] if i["key"] == "formats")["llm"]
    assert next(x for x in f["list"] if x["tpl"] == "3")["state"] == "planned" and f["applied"] == 0 and f["done"] == 0
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev, "tpls": ["3"]})
    assert r.status_code == 200 and len(r.json()["changed"]) == 2
    _undo_all(c, d, s)


def test_applied_mark_is_written_inside_the_apply_transaction(sess, monkeypatch):
    """반영의 표(오버레이 agent[템플릿] = 계획의 at)는 반영과 같은 트랜잭션에서 적는다 — 반영 직전의 실행 취소 묶음에는 없고(되돌리면 사라짐),
    반영이 끝난 때에는 이미 있다(전에는 트랜잭션이 끝난 뒤에 따로 적어, 그 사이 다른 화면이 실행 취소하면 되돌린 오버레이에 표가 붙었다)."""
    from app import outline_match_api as OM
    c, d, s = sess

    def fake(schema, content, what, **kw):
        return {"data": {"summary": "T3 정리", "levels": [{"level": 2, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]},
                "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    j = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).json()
    assert isinstance(j["at"], float)   # 계획의 표시 — 화면이 적용할 때 되돌려 보낸다
    seen = []
    real = OM.apply_templates

    def spy(*a, **kw):   # 반영의 몸이 돌아온 바로 그때(끝점이 기록을 적기 전) 오버레이에 표가 있는가
        got = real(*a, **kw)
        seen.append(dict(s.outline.get("agent") or {}))
        return got
    monkeypatch.setattr(OM, "apply_templates", spy)
    r = c.post(f"/api/docs/{d}/outline/agent/apply", json={"place": False, "rev": s.rev, "tpls": ["3"]})
    assert r.status_code == 200 and seen and seen[0].get("3") == j["at"]
    assert "3" not in (s.undo[-1]["outline"].get("agent") or {})   # 반영 직전 묶음에는 표가 없다 — 실행 취소가 표를 지운다
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert "3" not in (s.outline.get("agent") or {}) and c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["3"]["state"] == "planned"   # 되돌린 계획은 다시 쓸 수 있다
    _undo_all(c, d, s)


def test_replaced_plan_is_not_marked_applied_and_late_answer_does_not_overwrite(sess, monkeypatch):
    """화면이 가진 계획(plan = 그 계획의 at)과 서버에 남은 계획이 다르면(같은 문서 차례에 다시 받음) 적용은 되지만 남은 계획을 「반영함」 으로 적지 않는다 ·
    늦게 끝난 옛 요청의 답은 더 늦게 시작한 요청이 남긴 계획을 덮지 않는다 · 다른 그래프의 답은 남기지 않는다."""
    from app import tpl_agent_api as TA
    c, d, s = sess

    def fake(schema, content, what, **kw):
        return {"data": {"summary": "T3 정리", "levels": [{"level": 2, "rep": "g1", "match": ["g2", "g3"], "keep": [], "split": [], "why": ""}]},
                "backend": "api", "ms": 3, "costUsd": 0.0, "error": None, "model": kw.get("model"), "effort": kw.get("effort")}
    monkeypatch.setattr(llm, "call", fake)
    old = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).json()
    new = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).json()   # 같은 문서 차례에 다시 받음 — 남은 것은 이 계획
    assert old["rev"] == new["rev"] and old["at"] != new["at"]
    lv = next(x for x in old["plan"]["levels"] if x["level"] == 2)
    body = {"rev": old["rev"], "by": "agent", "plan": old["at"], "levels": [{"level": 2, "rep": lv["rep"]["para"], "likes": [m["para"] for m in lv["match"]]}]}
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={**body, "place": False})   # 화면은 옛 계획으로 적용한다
    assert r.status_code == 200 and len(r.json()["changed"]) == 2
    got = c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["3"]
    assert got["at"] == new["at"] and got["applied"] is None and got["state"] == "stale" and "3" not in (s.outline.get("agent") or {})   # 남은 계획은 반영한 그 계획이 아니다
    _undo_all(c, d, s)
    # 화면이 가진 계획 = 남은 계획이면 반영함
    one = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"}).json()
    r = c.post(f"/api/docs/{d}/outline/templates/3/match", json={**body, "place": False, "rev": one["rev"], "plan": one["at"]})
    assert r.status_code == 200 and c.get(f"/api/docs/{d}/outline/agent/plans").json()["plans"]["3"]["state"] == "applied" and s.outline["agent"]["3"] == one["at"]
    _undo_all(c, d, s)
    # 늦은 답 — 더 늦게 시작한 요청의 계획이 남아 있으면 덮지 않는다 · 일찍 시작한 것 위에는 덮는다
    graph, t = list(s.outline["run"]), TA.time.time() + 1000   # 위에서 남긴 계획보다 늦은 때를 기준으로
    assert TA._remember(s, graph, "3", {"tpl": "3", "rev": s.rev, "at": t + 50, "since": t + 40, "applied": None}, since=t + 40) is True
    assert TA._remember(s, graph, "3", {"tpl": "3", "rev": s.rev, "at": t + 60, "since": t + 30, "applied": None}, since=t + 30) is False   # 일찍 시작해 늦게 끝난 답
    assert TA.plans(s, graph)["3"]["at"] == t + 50
    assert TA._remember(s, graph, "3", {"tpl": "3", "rev": s.rev, "at": t + 70, "since": t + 45, "applied": None}, since=t + 45) is True
    # 다른 그래프의 답(LLM 을 기다린 사이 2단계를 다시 돌림) — 남기지 않는다: 지금 그래프의 상자가 그대로다
    keep = TA.plans(s, graph)
    real = TA.A.run

    def slow(mat, sk, request):
        res = real(mat, sk, request)
        s.outline["run"] = [graph[0], "다른 실행"]   # 그 사이 오버레이의 그래프가 바뀜(흉내)
        return res
    monkeypatch.setattr(TA.A, "run", slow)
    monkeypatch.setattr(server, "_outline_ov", lambda sess_, build=True: sess_.outline)   # 흉내 낸 그래프 표시를 다시 짓지 않게
    late = c.post(f"/api/docs/{d}/outline/agent/3/plan", json={"skill": "tidy"})
    assert late.status_code == 200 and late.json()["plan"]["summary"] == "T3 정리"
    s.outline["run"] = graph
    assert TA.plans(s, graph) == keep   # 상자는 그대로 — 옛 그래프의 늦은 답이 갈아 치우지 않았다
    with TA._plans_lock:   # 흉내로 넣은 기록(먼 뒤의 since)을 지운다 — 모듈 세션을 다른 시험이 이어 쓴다
        TA._plans_box(s)["plans"].pop("3", None)


def test_stored_plan_reads_old_value_names_as_new():
    """2026-11-17 화면 말 「앞 공백」 → 「레터 앞 빈칸」 · 「레터 뒤 공백」 → 「레터 뒤 빈칸」(spec_헤딩_추출 ② §0 「줄 첫머리의 말」) — 그 전에 작업 폴더에 남긴 계획도 지금 말로 읽는다.
    값 이름 그 자체인 문자열만(다른 값의 이름 · 값 사전의 키) — LLM 이 쓴 까닭 글 속의 말은 그대로."""
    import json

    from app import tpl_agent_api as TA
    old = {"plans": {"1": {"plan": {"levels": [{"values": {"앞 공백": "3칸"}, "match": [{"diff": [["lead", "앞 공백", "3칸", "4칸"], ["gap", "레터 뒤 공백", "1칸", "없음"]],
                                                                                    "why": "앞 공백 한 칸 차이"}]}]}}}}
    got = json.loads(TA._relabel(json.dumps(old, ensure_ascii=False)))
    lv = got["plans"]["1"]["plan"]["levels"][0]
    assert lv["values"] == {"레터 앞 빈칸": "3칸"}
    assert lv["match"][0]["diff"] == [["lead", "레터 앞 빈칸", "3칸", "4칸"], ["gap", "레터 뒤 빈칸", "1칸", "없음"]]
    assert lv["match"][0]["why"] == "앞 공백 한 칸 차이"   # 글 속의 말은 안 건드린다
    assert [M.LABELS["lead"], M.LABELS["gap"]] == [new for _, new in TA.OLD_LABELS]   # 바꾸는 곳 = 지금의 값 이름
