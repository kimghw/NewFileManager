"""양식 테마(app/form_themes.py · app/form_themes_api.py — spec_양식작성 ② §5-7): 기본본 읽기 · 사본이 먼저 · added 합치기 · LLM 이 정의한 항목 · 테마 더하기 · 잘못된 YAML · 끝점.
이 PC 의 사본 폴더는 시험마다 임시 폴더다(tests/conftest.py 의 NFM_FORM_THEMES = tmp_path/form_themes)."""
import pytest
import yaml
from fastapi.testclient import TestClient

from app import form_themes as T
from app import server


def test_defaults_carry_the_users_types_division_and_templates():
    ids = T.ids()
    assert ids[:2] == ["common", "rnd"]
    common, rnd = T.get("common"), T.get("rnd")
    assert [(x["id"], x["name"]) for x in common["tables"]] == [("body", "본문 테이블"), ("heading", "헤딩 테이블"), ("figure", "그림 테이블"), ("value", "값 테이블")]
    assert all(x["src"] == "default" and x["how"] and x["signs"] for x in common["tables"])
    assert [x["name"] for x in rnd["division"]][:4] == ["참여기관", "연차", "연구목표", "예산"]   # 사용자가 말한 넷이 앞
    assert rnd["templates"][0]["levels"] == ["1.", "1-1.", "□", "o", "-", "⋅"] and {"사업계획서", "연차보고서"} <= set(rnd["docs"])
    assert not common["custom"] and common["default"] and "src" not in common
    for tid in ids:   # 기본본은 화면에서 고친 글과 같은 엄격한 검사를 지난다
        assert T.parse(T.default_text(tid), tid)["id"] == tid
    brief = T.brief()
    assert {x["id"] for t in brief for x in t["tables"]} >= {"common.body", "common.heading", "common.figure", "common.value"}
    assert brief[1]["templates"][0] == {"id": "rnd.main", "name": "연구개발계획서 기본", "levels": ["1.", "1-1.", "□", "o", "-", "⋅"], "how": rnd["templates"][0]["how"]}
    assert T.find("tables", "common.heading")[1]["name"] == "헤딩 테이블" and T.find("tables", "common.nope") == (None, None) and T.find("tables", None) == (None, None)
    assert T.by_name("tables", "본문  테이블") == "common.body" and T.by_name("tables", "없는 타입") is None
    assert T.division_text(rnd).startswith("연구개발과제 — 참여기관: ") and T.division_text(common) == ""
    assert T.get("nope") is None and T.get("Bad Id") is None and T.text("nope") is None


def test_copy_wins_and_reset_restores_the_default(tmp_path):
    text = T.text("common")
    assert text == T.default_text("common")
    edited = text.replace("name: 본문 테이블", "name: 서술 테이블")
    got = T.save("common", edited)
    assert got["custom"] and got["tables"][0]["name"] == "서술 테이블" and got["tables"][0]["src"] == "user" and got["tables"][1]["src"] == "default"
    assert (tmp_path / "form_themes" / "common.yaml").read_text(encoding="utf-8") == edited and T.text("common") == edited
    assert T.get("rnd")["custom"] is False   # 다른 테마는 그대로
    assert T.reset("common") and not T.reset("common")
    assert T.get("common")["tables"][0] == {**T.get("common")["tables"][0], "name": "본문 테이블", "src": "default"} and not T.get("common")["custom"]


def test_add_appends_to_added_without_overwriting():
    iid, made = T.add("rnd", "tables", {"id": "check", "name": "체크 테이블", "signs": "항목마다 □ 가 있다", "how": "해당 항목에 표시한다"}, "llm", "w1", "2026-11-26")
    assert (iid, made) == ("check", True)
    item = T.get("rnd")["tables"][-1]
    assert item == {"id": "check", "name": "체크 테이블", "signs": "항목마다 □ 가 있다", "how": "해당 항목에 표시한다", "src": "llm", "work": "w1", "at": "2026-11-26"}
    assert not T.get("rnd")["custom"]   # 더한 항목뿐 — 사람이 고친 사본이 아니다
    assert T.add("rnd", "tables", {"name": "체크  테이블", "how": "다른 글"}) == ("check", False)   # 같은 이름 — 덮지 않는다
    assert T.get("rnd")["tables"][-1]["how"] == "해당 항목에 표시한다"
    other, made = T.add("rnd", "tables", {"id": "check", "name": "서명 테이블", "how": "서명 칸은 비워 둔다"})   # id 가 겹친다 — 새 id 를 짓는다
    assert made and other != "check" and T.ID.fullmatch(other) and T.by_name("tables", "서명 테이블") == f"rnd.{other}"
    text = T.text("rnd")   # 지금 글 = 기본본의 글(주석 그대로) + added
    assert text.startswith(T.default_text("rnd").rstrip("\n")) and [x["id"] for x in yaml.safe_load(text)["added"]["tables"]] == ["check", other]
    tid, made = T.add("common", "templates", {"name": "로마 숫자 장", "levels": ["Ⅰ.", "1.", "가."], "how": "장 번호를 로마 숫자로"})
    assert made and T.find("templates", f"common.{tid}")[1]["levels"] == ["Ⅰ.", "1.", "가."]
    for theme, kind, item in (("common", "templates", {"name": "레터 없음", "levels": []}), ("nope", "tables", {"name": "가", "how": "나"}), ("common", "tables", {"how": "이름 없음"}), ("common", "nope", {"name": "가"})):
        with pytest.raises(ValueError):
            T.add(theme, kind, item)


def test_add_into_an_edited_copy_keeps_the_users_text():
    edited = T.text("common").replace("name: 본문 테이블", "name: 서술 테이블") + "# 내 메모\n"
    T.save("common", edited)
    T.add("common", "tables", {"name": "체크 테이블", "how": "표시한다"})
    T.add("common", "tables", {"name": "서명 테이블", "how": "비워 둔다"})   # 둘째는 맨 끝의 added 덩이만 바꿔 쓴다
    text, got = T.text("common"), T.get("common")
    assert text.startswith(edited.rstrip("\n")) and "# 내 메모" in text and text.count("added:") == 1
    assert got["tables"][0]["name"] == "서술 테이블" and [(x["name"], x["src"]) for x in got["tables"][-2:]] == [("체크 테이블", "llm"), ("서명 테이블", "llm")]
    moved = "added:\n  tables:\n  - {id: old, name: 옛 타입, how: 그대로}\n" + T.default_text("common")   # added 가 가운데(맨 앞) — 통째로 다시 쓴다(읽은 것은 지킨다)
    T.save("common", moved)
    T.add("common", "tables", {"name": "새 타입", "how": "새로"})
    assert [x["name"] for x in T.get("common")["tables"]][-2:] == ["옛 타입", "새 타입"] and T.get("common")["tables"][0]["name"] == "본문 테이블"


def test_define_a_new_theme_and_reuse_one_with_the_same_name():
    tid, made = T.define({"name": "입찰 제안서", "docs": ["제안서"], "signs": "제안요청서의 목차를 따른다", "division": [{"name": "평가 항목", "how": "평가표의 항목마다 쓴다"}]}, "llm", "w1", "2026-11-26")
    got = T.get(tid)
    assert made and T.ID.fullmatch(tid) and tid in T.ids() and got["src"] == "llm" and not got["default"] and got["docs"] == ["제안서"]
    assert [(x["name"], x["how"], x["src"]) for x in got["division"]] == [("평가 항목", "평가표의 항목마다 쓴다", "llm")]
    assert T.define({"name": "입찰  제안서"}) == (tid, False) and T.define({"name": "연구개발과제"}) == ("rnd", False)
    assert T.add(tid, "tables", {"name": "평가 테이블", "how": "항목마다 쓴다"})[1] and T.get(tid)["tables"][0]["src"] == "llm"
    with pytest.raises(ValueError):
        T.define({"name": ""})
    assert T.reset(tid) and T.get(tid) is None and tid not in T.ids()


def test_brief_can_leave_out_the_how_of_unconfirmed_items():
    """04 에 싣는 요약 — LLM 이 정의했고 사람이 확인하지 않은 항목(src llm)의 작성 방법은 빼고 이름 · 판별 단서 · 레터만(astra 2026-11-27 P1-4). 기본(인자 없음)은 전과 같다."""
    iid, _ = T.add("rnd", "tables", {"name": "체크 테이블", "signs": "항목마다 □ 가 있다", "how": "해당 항목에 표시한다"}, "llm", "w1", "2026-11-27")
    tid, _ = T.add("rnd", "templates", {"name": "로마 숫자 장", "levels": ["Ⅰ.", "1."], "how": "장 번호를 로마 숫자로"})
    made, _ = T.define({"name": "입찰 제안서", "division": [{"name": "평가 항목", "how": "평가표의 항목마다 쓴다"}]}, "llm")
    full, lean = {t["id"]: t for t in T.brief()}, {t["id"]: t for t in T.brief(unconfirmed_how=False)}
    assert next(x for x in full["rnd"]["tables"] if x["id"] == f"rnd.{iid}")["how"] == "해당 항목에 표시한다" and full[made]["division"] == [{"name": "평가 항목", "how": "평가표의 항목마다 쓴다"}]
    assert next(x for x in lean["rnd"]["tables"] if x["id"] == f"rnd.{iid}") == {"id": f"rnd.{iid}", "name": "체크 테이블", "signs": "항목마다 □ 가 있다"}
    assert next(x for x in lean["rnd"]["templates"] if x["id"] == f"rnd.{tid}") == {"id": f"rnd.{tid}", "name": "로마 숫자 장", "levels": ["Ⅰ.", "1."]}   # 레터는 남는다
    assert lean[made]["division"] == [{"name": "평가 항목"}]   # LLM 이 정의한 테마의 항목도 확인 전
    assert lean["common"] == full["common"] and lean["rnd"]["division"] == full["rnd"]["division"] and lean["rnd"]["tables"][0] == full["rnd"]["tables"][0]   # 기본본의 것은 그대로
    uid, _ = T.add("rnd", "tables", {"name": "서명 테이블", "signs": "서명 칸이 있다", "how": "서명 칸은 비워 둔다"}, "user")   # 사람의 것(src user = 확인한 것)은 싣는다
    assert next(x for t in T.brief(unconfirmed_how=False) for x in t["tables"] if x["id"] == f"rnd.{uid}")["how"] == "서명 칸은 비워 둔다"
    assert T.unconfirmed({"src": "llm"}) and not T.unconfirmed({"src": "user"}) and not T.unconfirmed({"src": "default"}) and not T.unconfirmed(None)


def test_same_def_compares_the_content_not_only_the_name():
    """이름이 같은 새 정의를 있는 항목에 이어도 되는가 — 템플릿 = 레터가 같음 · 테이블 타입 = 판별 단서와 작성 방법이 같음(astra 2026-11-27 P2-3)."""
    body, main = T.find("tables", "common.body")[1], T.find("templates", "rnd.main")[1]
    assert T.same_def("tables", body, {"name": "본문 테이블", "signs": body["signs"].replace(" ", "  "), "how": body["how"]})   # 빈칸의 차이는 같은 정의
    assert not T.same_def("tables", body, {"name": "본문 테이블", "signs": body["signs"], "how": "서명 칸은 비워 둔다"})
    assert not T.same_def("tables", body, {"name": "본문 테이블", "signs": "", "how": body["how"]})
    assert T.same_def("templates", main, {"name": "다른 이름이어도", "levels": list(main["levels"]), "how": "설명은 달라도 된다"})
    assert not T.same_def("templates", main, {"name": main["name"], "levels": list(reversed(main["levels"])), "how": main["how"]})   # 레터의 차례가 다르면 다른 템플릿
    assert not T.same_def("tables", None, {"name": "본문 테이블"}) and not T.same_def("tables", body, None)


def test_default_hows_match_the_guidance_on_units_and_skipped_levels():
    """기본본의 작성 방법이 04 판단 지침과 부딪치지 않는다(astra 2026-11-27 P2-4 · P2-5) — 예산의 단위는 표에 적힌 단위가 먼저 · 번호 사슬의 「건너뛰지 않는다」 는 새로 쓰는 줄의 말."""
    budget = next(x for x in T.get("rnd")["division"] if x["id"] == "budget")["how"]
    assert "단위는 자료 그대로" not in budget and "표에 단위가 적혀 있으면 그 단위로 쓴다" in budget and "환산 관계를 확인할 수 있을 때만" in budget
    numbered = next(x for x in T.get("common")["templates"] if x["id"] == "numbered")["how"]
    assert "새로 쓰는 줄은 레벨을 건너뛰지 않는다" in numbered and "이미 놓인 줄의 깊이는 그대로" in numbered


def test_bad_yaml_is_rejected_and_nothing_is_written(tmp_path):
    for bad, word in (("id: common\nname: [", "읽을 수 없습니다"), ("- a\n- b\n", "묶음"), ("id: rnd\nname: x\n", "「common」"), ("id: common\ntables:\n  - {id: Bad Id, name: x}\n", "id"),
                      ("id: common\ntemplates:\n  - {id: a, name: x, levels: [1., 가.]}\n", "따옴표"), ("id: common\ntables:\n  - {id: a, name: x}\n  - {id: a, name: y}\n", "두 번"),
                      ("id: common\ntables: 본문\n", "목록"), ("", "비었습니다"), ("id: common\nname: x\n" + "# 긴 글\n" * 5000, "자까지")):
        with pytest.raises(ValueError, match=word):
            T.save("common", bad)
    assert not (tmp_path / "form_themes").exists() and not T.get("common")["custom"]
    (tmp_path / "form_themes").mkdir()
    (tmp_path / "form_themes" / "common.yaml").write_text("id: common\nname: [", encoding="utf-8")   # 깨진 사본 — 기본본으로 읽고, 더하기는 그 파일을 덮지 않는다
    assert T.get("common")["tables"][0]["name"] == "본문 테이블" and T.text("common") == T.default_text("common")
    with pytest.raises(ValueError, match="사본"):
        T.add("common", "tables", {"name": "체크 테이블", "how": "표시한다"})


def test_memory_only_when_the_store_is_off(monkeypatch):
    monkeypatch.setenv("NFM_FORM_THEMES", "off")
    monkeypatch.setattr(T, "_MEMORY", {})
    assert T.store_dir() is None
    T.add("common", "tables", {"name": "체크 테이블", "how": "표시한다"})
    assert T.get("common")["tables"][-1]["name"] == "체크 테이블"
    assert T.reset("common") and T.get("common")["tables"][-1]["id"] == "value"


def test_api_lists_reads_saves_and_resets():
    client = TestClient(server.app)
    listed = client.get("/api/form-themes").json()
    assert [t["id"] for t in listed["themes"]][:2] == ["common", "rnd"] and listed["max"] == T.TEXT_MAX
    y = client.get("/api/form-themes/rnd/yaml").json()
    assert y == {"id": "rnd", "text": T.text("rnd"), "custom": False, "default": True}
    assert client.put("/api/form-themes/rnd/yaml", json={"text": "id: rnd\nname: ["}).status_code == 400
    ok = client.put("/api/form-themes/rnd/yaml", json={"text": y["text"].replace("name: 연구개발과제", "name: 국가연구개발")})
    assert ok.status_code == 200 and ok.json()["theme"]["name"] == "국가연구개발" and ok.json()["theme"]["custom"]
    assert client.get("/api/form-themes/rnd/yaml").json()["custom"]
    gone = client.delete("/api/form-themes/rnd/yaml").json()
    assert gone["removed"] and gone["theme"]["name"] == "연구개발과제" and not gone["theme"]["custom"]
    assert client.get("/api/form-themes/nope/yaml").status_code == 404 and client.put("/api/form-themes/Bad!/yaml", json={"text": "name: x"}).status_code == 404
    new = client.put("/api/form-themes/bid/yaml", json={"text": "name: 제안서\ntables:\n  - {id: score, name: 평가 테이블, how: 항목마다 쓴다}\n"})   # 기본본이 없는 새 테마
    assert new.status_code == 200 and new.json()["theme"]["tables"][0]["src"] == "user" and not new.json()["theme"]["default"]
    assert client.delete("/api/form-themes/bid/yaml").json() == {"theme": None, "removed": True}
