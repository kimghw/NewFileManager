"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 연구개발계획서 양식 + 2단계(LLM 끔).
양식의 실제 갈래: T3 「o › -」 L2 = 「   - 」 5줄(대표 p6502) · 「    - 」(p5209) · 「    -」(p5765) / T2 「□ › o › - › ·」 L1 = 글꼴·크기가 다른 □ 3줄 /
T1 L2 「N-N.」 = 앞 공백이 다른 번호 줄 / T9 「[기관] › o › -」 가 T8 「[단계] › (N) › ①」 L3 아래 40곳 · T3 은 T1 L2 아래 7곳(T1 L3 = 「(N)」 이어도 종속 템플릿 「T1T3」 로 넣는다)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import outline_match as M
from app import server

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("outline_match")
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
    r = c.get(f"/api/docs/{d}/outline/formats")
    assert r.status_code == 200, r.text
    return r.json()["slots"][str(tid)][str(lv)]


def test_ws_and_form():
    assert M.ws("") == "없음" and M.ws("  ") == "2칸" and M.ws("\t") == "탭" and M.ws("　 ") == "전각 1칸 + 1칸"
    assert M._form("3.", "N.") == "#." and M._form("1-2.", "N-N.") == "#-#." and M._form("(가)", "(가)") == "(#)" and M._form("ㅇ", "o") == "ㅇ"


def test_variants_group_lines_and_show_differences(sess):
    c, d, s = sess
    v = _slot(c, d, 3, 2)
    assert v["total"] == 7 and v["rep"] == "p6502" and v["others"] == 2
    rep, *rest = v["groups"]
    assert rep["rep"] and rep["count"] == 5 and rep["diff"] == [] and rep["paras"][0] == "p6502"
    by = {g["paras"][0]: g for g in rest}
    assert by["p5209"]["diff"] == [["lead", "앞 공백", "3칸", "4칸"]]
    assert by["p5765"]["diff"] == [["lead", "앞 공백", "3칸", "4칸"], ["gap", "레터 뒤 공백", "1칸", "없음"]]
    assert by["p5765"]["raw"]["lead"] == "    " and by["p5765"]["raw"]["gap"] == "" and by["p5765"]["look"]["lead"] == "4칸"  # 원값(서식 비교의 견본 글)
    keys = c.get(f"/api/docs/{d}/outline/formats").json()["keys"]  # 비교 값 차례·이름(서식 비교 표의 열)
    assert keys[:3] == [["lead", "앞 공백"], ["letter", "레터"], ["gap", "레터 뒤 공백"]] and ["L.font", "레터 글꼴"] in keys
    v2 = _slot(c, d, 2, 1)  # 글자 모양이 다른 갈래 — 레터 런과 본문 런을 따로 견준다
    keys = [x[0] for g in v2["groups"] for x in g["diff"]]
    assert "L.font" in keys and "font" in keys and "L.sizePt" in keys
    o = c.get(f"/api/docs/{d}/outline").json()
    assert o["templates"]["3"]["slots"]["2"]["rep"] == "p6502" and o["templates"]["9"]["hang"]["8|3"] == 40
    assert o["lines"]["p970"]["key"] == "□"


def test_set_rep_is_model_only_and_undoable(sess):
    c, d, s = sess
    before = c.get(f"/api/docs/{d}/download").content
    r = c.put(f"/api/docs/{d}/outline/slots/3/2/rep", json={"para": "p5209"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slot"]["rep"] == "p5209" and j["undo"] == 1 and j["outline"]["templates"]["3"]["slots"]["2"]["rep"] == "p5209"
    sl = s.outline["templates"]["3"]["slots"]["2"]
    assert sl["prefix"] == "    - " and sl["repSet"] and sl["attrs"]["paraPrIDRef"] == s.doc._ids["p5209"].get("paraPrIDRef")
    assert c.get(f"/api/docs/{d}/download").content == before  # 문서는 안 바뀜
    assert c.put(f"/api/docs/{d}/outline/slots/3/2/rep", json={"para": "p970"}).status_code == 400  # 그 레벨 줄이 아님
    assert c.put(f"/api/docs/{d}/outline/slots/3/9/rep", json={"para": "p5209"}).status_code == 404
    assert c.put(f"/api/docs/{d}/outline/slots/3/2/rep", json={}).status_code == 400
    g = heading_runs.graph(s)  # 서식 복사의 내용 서식 후보도 사람이 정한 대표 줄에서(apply_reps — 그래프는 안 바꾸고 사본)
    t3 = lambda gg: next(x for x in gg["templates"] if x["id"] == 3)  # noqa: E731
    g2 = M.apply_reps(g, s.outline)
    assert next(x for x in t3(g2)["slots"] if x["level"] == 2)["rep"] == "p5209" and next(x for x in t3(g)["slots"] if x["level"] == 2)["rep"] == "p6502"
    c.post(f"/api/docs/{d}/undo")
    assert s.outline["templates"]["3"]["slots"]["2"]["rep"] == "p6502" and M.apply_reps(g, s.outline) is g
    _undo_all(c, d, s)


def test_match_symbol_letters_prefix_and_shape(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/slots/3/2/match", json={})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["changed"] == ["p5209", "p5765"] and j["outline"]["lines"]["p5765"]["letter"] == "-" and j["tops"]["blocks"]
    assert s.texts["p5209"].startswith("   - ") and s.texts["p5765"].startswith("   - ")
    rep = s.doc._ids["p6502"]
    for pid in ("p5209", "p5765"):
        assert s.doc._ids[pid].get("paraPrIDRef") == rep.get("paraPrIDRef")
    assert len(_slot(c, d, 3, 2)["groups"]) == 1
    again = c.post(f"/api/docs/{d}/outline/slots/3/2/match", json={})
    assert again.status_code == 200 and again.json()["nothing"] and again.json()["undo"] == 1  # 맞출 줄이 없으면 편집을 안 연다
    _undo_all(c, d, s)


def test_match_one_group_by_like_even_past_the_list_limit(sess, monkeypatch):
    c, d, s = sess
    monkeypatch.setattr(M, "_LIST_MAX", 3)  # 화면이 받는 갈래 목록이 잘려도(30줄 → 여기선 3줄) like 로 갈래 전부(2026-11-15 newfilemanager-af 지적)
    v = _slot(c, d, 4, 3)
    g = next(x for x in v["groups"] if not x["rep"] and x["count"] > 3)
    assert len(g["paras"]) == 3 and g["more"] == g["count"] - 3
    others = sum(x["count"] for x in v["groups"] if not x["rep"])
    r = c.post(f"/api/docs/{d}/outline/slots/4/3/match", json={"like": g["paras"][0]})
    assert r.status_code == 200, r.text
    assert len(r.json()["changed"]) == g["count"] < others  # 그 갈래만 — 다른 갈래는 그대로
    assert c.post(f"/api/docs/{d}/outline/slots/4/3/match", json={"like": "p970"}).status_code == 400  # 그 레벨 줄이 아님
    assert c.post(f"/api/docs/{d}/outline/slots/4/3/match", json={"like": 3}).status_code == 400
    _undo_all(c, d, s)


def test_match_char_shapes_keep_emphasis_runs(sess):
    c, d, s = sess
    v = _slot(c, d, 2, 1)
    odd = next(g for g in v["groups"] if any(x[0] == "font" for x in g["diff"]))["paras"]
    r = c.post(f"/api/docs/{d}/outline/slots/2/1/match", json={"paras": odd})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["changed"]) == sorted(odd)
    rep_look = M.look(s.doc, s.outline, "p970")
    for pid in odd:
        assert M.look(s.doc, s.outline, pid) == rep_look
    _undo_all(c, d, s)


def test_match_numbered_letters_keep_own_number(sess):
    c, d, s = sess
    assert s.texts["p5930"].startswith("5-3. ")  # 앞 공백 없음 — 대표(p968 「 1-1. 」)는 한 칸
    r = c.post(f"/api/docs/{d}/outline/slots/1/2/match", json={"paras": ["p5930", "p889"]})
    assert r.status_code == 200, r.text
    assert s.texts["p5930"].startswith(" 5-3. ") and s.texts["p889"].startswith(" 7-1. ")
    assert s.outline["lines"]["p5930"]["letter"] == "5-3."
    _undo_all(c, d, s)


def test_merge_makes_a_composite_template_and_unmerge(sess):
    c, d, s = sess
    before = c.get(f"/api/docs/{d}/download").content
    t1 = dict(s.outline["templates"]["1"], slots=dict(s.outline["templates"]["1"]["slots"]))
    # T3 「o › -」 를 T1 「N. › N-N. › (N) › o › -」 의 L2 아래로 — T1 L3 은 「(N)」 이지만 종속 템플릿은 다른 템플릿이라 된다(2026-11-15 사용자 「T1T3 템플릿으로」)
    r = c.post(f"/api/docs/{d}/outline/merge", json={"child": "3", "parent": "1", "at": 2})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["merged"] == {"id": "1+3", "no": "1T3", "child": 3, "parent": 1, "at": 2, "moved": 14, "levels": [3, 4]} and j["undo"] == 1
    comp, t3 = j["outline"]["templates"]["1+3"], j["outline"]["templates"]["3"]
    assert comp["no"] == "1T3" and comp["chain"] == ["N.", "N-N.", "o", "-"] and comp["max"] == 4 and comp["base"] == 2 and sorted(comp["slots"]) == ["3", "4"]
    assert comp["comp"] == {"parent": "1", "child": "3", "at": 2, "parentNo": 1, "childNo": 3} and comp["hang"] == {"1|2": 7}
    assert t3["made"][0]["id"] == "1+3" and t3["lines"] == 2 and not t3["all"] and "1|2" not in t3["hang"]
    assert s.outline["templates"]["1"]["chain"] == t1["chain"] and s.outline["templates"]["1"]["max"] == t1["max"]  # T1 은 안 바뀐다
    mine = {p: x for p, x in s.outline["lines"].items() if x["tpl"] == "1+3"}
    first = next(p for p, x in mine.items() if x["level"] == 3)
    assert len(mine) == 14 and all(x["no"] == "1T3" for x in mine.values()) and s.outline["lines"][s.outline["lines"][first]["parent"]]["tpl"] == "1"
    assert c.get(f"/api/docs/{d}/download").content == before  # 문서는 안 바뀜
    v = _slot(c, d, "1+3", 3)
    assert v["total"] == 7 and v["rep"] in mine
    # 종속 템플릿 줄의 개요 편집: Enter = 그 템플릿의 다음 레벨(L4 「-」) · Alt+↑ = 첫 레벨이라 부모 줄의 (T1, L2)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": first, "offset": len(s.texts[first])})
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["lines"][r.json()["focus"]["id"]] == {"no": "1T3", "level": 4, "tpl": "1+3", "letter": "-", "role": "heading", "key": "-"}
    c.post(f"/api/docs/{d}/undo")
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [first], "delta": -1})
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["lines"][first]["tpl"] == "1" and r.json()["outline"]["lines"][first]["level"] == 2
    c.post(f"/api/docs/{d}/undo")
    # 둘째 종속 · 같은 것 또 · 매달린 곳 없음 · 제 자신 · 잘못된 값
    r = c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 3})
    assert r.status_code == 200 and r.json()["merged"]["no"] == "8T9" and r.json()["merged"]["moved"] == 80 and r.json()["merged"]["levels"] == [4, 6]
    again = c.post(f"/api/docs/{d}/outline/merge", json={"child": "3", "parent": "1", "at": 2})
    assert again.status_code == 400 and "T1T3" in again.json()["detail"]
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "5", "parent": "8", "at": 1}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "8", "parent": "8", "at": 1}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 0}).status_code == 400
    # 떼기 — 종속 템플릿이 없어지고 줄이 T3 로
    r = c.post(f"/api/docs/{d}/outline/unmerge", json={"child": "3", "parent": "1"})
    assert r.status_code == 200, r.text
    assert r.json()["back"] == 14 and "1+3" not in r.json()["outline"]["templates"]
    assert sum(1 for x in s.outline["lines"].values() if x["tpl"] == "3") == 16 and all(x["key"] in ("o", "-") for x in s.outline["lines"].values() if x["tpl"] == "3")
    assert "1+3" not in str(s.outline.get("branches"))
    assert c.post(f"/api/docs/{d}/outline/unmerge", json={"child": "3", "parent": "1"}).status_code == 400
    c.post(f"/api/docs/{d}/undo")  # 떼기 되돌림 → 종속 템플릿이 다시
    assert "1+3" in s.outline["templates"]
    _undo_all(c, d, s)
    assert "1+3" not in s.outline["templates"] and "8+9" not in s.outline["templates"] and not s.outline.get("merges")


def test_merge_and_rep_carry_over_a_new_overlay(sess):
    c, d, s = sess
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "3", "parent": "1", "at": 2}).status_code == 200
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 3}).status_code == 200
    rest = [p for p, x in s.outline["lines"].items() if x["tpl"] == "3" and x["level"] == 1][-1]  # T3 에 남은 줄(넣은 자리 밖 — T8 L1 아래)
    assert c.put(f"/api/docs/{d}/outline/slots/3/1/rep", json={"para": rest}).status_code == 200
    ov = OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)  # 2단계를 다시 돌린 것과 같이 — 그래프에서 새로 만든 오버레이
    assert not ov.get("merges") and "1+3" not in ov["templates"]
    fails = M.carry(s.outline, ov, M.context(s.doc, ov))
    assert fails == [] and ov["templates"]["1+3"]["no"] == "1T3" and ov["templates"]["8+9"]["max"] == 6
    assert sum(1 for x in ov["lines"].values() if x["tpl"] == "8+9") == 80 and ov["templates"]["3"]["slots"]["1"]["rep"] == rest
    _undo_all(c, d, s)


def test_requires_stage2_and_hwpx():
    server.DOCS.clear()
    c = TestClient(server.app, raise_server_exceptions=False)
    d = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}).json()["docId"]
    assert c.get(f"/api/docs/{d}/outline/formats").json()["off"] is True
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "2", "parent": "1", "at": 1}).status_code == 409
    assert c.post(f"/api/docs/{d}/outline/slots/1/1/match", json={}).status_code == 409
    server.DOCS.clear()


def test_client_wiring():
    js = (ROOT / "app" / "static" / "outline_match.js").read_text(encoding="utf-8")
    app = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert "olmRow(id, L)" in app and "olmTplTools(li, row, id)" in app and "olmHidden(cid, id, L)" in app and "olmRefresh()" in app
    assert "function tplRelOpen" in app and "olMark(p.dataset.id, ol" in app
    assert "/outline/formats" in js and "/match`" in js and '"merge"' in js and '"unmerge"' in js
    assert 'id="tbTplRel"' in html or 'data-tool-set="style"' not in html  # 도구 줄 「서식」 묶음(spec_서식복사 ② §3)이 있으면 넷째 아이콘 「템플릿 관계」 도 — 묶음이 없는 판(개요만 커밋)에서는 표·헤딩 탭으로 연다
    assert html.index('src="/static/outline_format.js"') < html.index('src="/static/outline_match.js"')
