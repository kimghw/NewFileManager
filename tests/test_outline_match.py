"""개요 레벨 대표 서식 · 대표에 맞추기 · 템플릿 종속(spec_hwpx_웹편집 ② §8-2) — 연구개발계획서 양식 + 2단계(LLM 끔).
양식의 실제 갈래: T1 L5 「-」 = 「    - 」 9줄(대표 p5209) · 「   - 」 5줄(p6502) · 「    -」(p5765) / T2 「□ › o › - › ·」 L1 = 글꼴·크기가 다른 □ 3줄 /
T1 L2 「N-N.」 = 앞 공백이 다른 번호 줄 / T9 「[기관] › o › -」 가 T8 「[단계] › (N) › ①」 L3 아래 40곳 · T2 는 T1 L2 아래 3곳 · T1 L3 아래 4곳(T1 L3 = 「(N)」 이어도 종속 템플릿 「T1T2」 로 넣는다).
2026-11-17 「잇닿은 사슬」(spec_헤딩_추출 ② §6) 전에는 「1-1.」 바로 아래 「o › -」 가 가지 T3 이었다 — 지금은 T1 L4·L5(그 「-」 줄 p6502 · p5209 · p5765 가 T1 L5)이고 T3 은 「[단계]」 아래 「o」 두 줄."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import outline_match as M
from app import outline_pos as OP
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


def test_lookalike_letter_glyph_is_the_same_letter(sess):
    """닮은 레터 글자(spec_hwpx_웹편집 ② §8-5 「닮은 글자」 — 2026-11-17 사용자 답 「같은 레터 · 글자도 대표로」): 헤딩 판정이 같은 레터 키로 묶는 글자(「o」·「ㅇ」·「○」)는 같은 레터다 —
    갈래는 전처럼 글자로 갈리지만 다른 값의 이름이 「레터」 가 아니라 「닮은 레터 글자」 이고, 맞추면 글자도 대표의 글자가 된다. 속이 찬 기호(「□」 자리의 「■」)는 전처럼 「레터」 가 다르다."""
    import copy

    from app.hwpx_doc import HwpxDoc

    assert M.kin("ㅇ", "o") == M.kin("o", "o") == M.kin("○", "o") and M.kin("·", "·") == M.kin("•", "·")
    assert M.kin("●", "o") != M.kin("○", "o") and M.kin("■", "□") != M.kin("□", "□") and M.kin("x", "") == "x"
    c, d, s = sess
    doc = HwpxDoc(PLAN.read_bytes())  # 세션 문서는 그대로 두고 사본에서(오버레이도 사본)
    doc.blocks()
    ov = copy.deepcopy(s.outline)
    assert doc._text(doc._ids["p6502"]).startswith("   - ") and ov["lines"]["p6502"]["key"] == "-"
    doc.set_chars("p6502", 3, "–")  # T1 L5 「-」 줄 하나를 닮은 글자(반각 줄표)로
    ov["lines"]["p6502"]["letter"] = "–"
    g = next(x for x in M.variants(doc, ov, "1", 5)["groups"] if "p6502" in x["paras"])
    assert g["count"] == 1 and ["letter", "닮은 레터 글자", "-", "–"] in g["diff"] and not any(x[1] == "레터" for x in g["diff"])
    assert "kin" not in g["look"] and g["raw"]["kin"] == M.kin("-", "-")  # 계열은 화면의 서식 비교 표에 줄로 나오지 않는다(raw 에만)
    M.match_one(doc, ov, "p6502", M.rep_shape(doc, ov, "p5209"))
    assert doc._text(doc._ids["p6502"]).startswith("    -") and ov["lines"]["p6502"]["letter"] == "-"  # 맞추면 글자도 대표 글자
    pid = next(p for p, x in ov["lines"].items() if x.get("key") == "□" and x.get("letter") == "□" and ov["templates"][x["tpl"]]["slots"][str(x["level"])].get("rep") not in (None, p))
    x = ov["lines"][pid]
    doc.set_chars(pid, doc._text(doc._ids[pid]).index("□"), "■")  # 속이 찬 기호 — 닮은 글자가 아니다
    x["letter"] = "■"
    g = next(v for v in M.variants(doc, ov, x["tpl"], x["level"])["groups"] if pid in v["paras"])
    assert ["letter", "레터", "□", "■"] in g["diff"]
    a = M.look(doc, ov, "p5209")
    assert M.diff({**a, "kin": ""}, {**a, "kin": "", "letter": "–"}) == [["letter", "레터", "-", "–"]]  # 계열을 모르는 값(옛 저장본)은 전처럼 「레터」


def _cell_tpl(ov, root):
    """표 칸 템플릿(사슬의 첫 레터가 root) — 번호는 그래프 규칙이 바뀌면 달라지므로 사슬로 찾는다."""
    return next(t for t, T in ov["templates"].items() if T.get("kind") == "cell" and (T.get("chain") or [""])[0] == root and not T.get("variant"))


def test_table_lines_keep_their_tables_format(sess):
    """표 안의 줄 — 표 양식마다의 서식(spec_hwpx_웹편집 ② §8-11 — 2026-11-17 사용자 「같은 것끼리는 서식을 공유하지만 그렇지 않은 경유, 기존 테이블 안의 서식을 사용」).
    표 칸의 번호 줄 「N.」 11줄: 대표 p6293 의 표(머리글 「기술개발 내용 · 위험요인 …」) 6줄 = 대표 4 + 레터 뒤 빈칸이 다른 2 / 다른 표 둘(「세부사업명 …」) 3줄 · 2줄 = 그 표의 서식.
    대표와 서식이 다른 줄은 표 양식마다 갈래 · 「대표에 맞추기」 는 다른 표의 서식을 건드리지 않고 · 골라서 맞추는 것은 된다."""
    c, d, s = sess
    tid = _cell_tpl(s.outline, "N.")
    v = _slot(c, d, tid, 1)
    assert v["rep"] == "p6293" and v["total"] == 11 and v["others"] == 2 and v["ownLines"] == 5
    by = {g["key"]: g for g in v["groups"]}
    rep, near, own, own2 = by["p6293"], by["p6302"], by["p12723"], by["p13221"]
    assert rep["form"]["label"].startswith("기술개발 내용") and rep["form"]["around"] == "Dotum 8pt" and not rep["own"]
    assert not near["own"] and near["form"]["key"] == rep["form"]["key"] and not any(x[0] == "form" for x in near["diff"])  # 대표와 같은 표 — 흔들린 줄
    assert own["own"] and own2["own"] and len({rep["form"]["key"], own["form"]["key"], own2["form"]["key"]}) == 3              # 머리글이 다른 표 = 다른 표 양식
    assert own["diff"][-1][:2] == ["form", "표"] and own["diff"][-1][2].startswith("기술개발 내용") and own["diff"][-1][3].startswith("세부사업명")
    assert own["form"]["tables"] == 1 and "form" not in own["look"] and "formLabel" not in own["look"] and own["raw"]["form"] == own["form"]["key"]
    assert M.table_form(s.doc, s.outline, s.doc._ids["p5209"]) is None and _slot(c, d, 1, 5)["ownLines"] == 0 and all(g["form"] is None for g in _slot(c, d, 1, 5)["groups"])  # 표 밖의 줄은 전과 같다
    kept = {p: (s.texts[p], s.doc._ids[p].get("paraPrIDRef")) for p in own["paras"] + own2["paras"]}
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/1/match", json={})
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j["changed"]) - set(j["placed"]) == set(near["paras"])                                     # 대표의 표에 있는 다른 서식만 맞춘다
    assert all((s.texts[p], s.doc._ids[p].get("paraPrIDRef")) == kept[p] for p in kept)                  # 다른 표의 줄은 글도 문단 모양도 그대로
    v2 = _slot(c, d, tid, 1)
    assert v2["others"] == 0 and v2["ownLines"] == 5 and len(v2["groups"]) == 3
    again = c.post(f"/api/docs/{d}/outline/slots/{tid}/1/match", json={})
    assert again.status_code == 200 and again.json()["nothing"]                                           # 남은 것은 표의 서식뿐 — 맞출 줄이 없다
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/1/match", json={"like": "p12723"})                    # 사람이 그 갈래를 골라서 맞추는 것은 된다
    assert r.status_code == 200 and set(r.json()["changed"]) - set(r.json()["placed"]) == set(own["paras"])
    assert _slot(c, d, tid, 1)["ownLines"] == 2                                                           # 같은 서식이어도 다른 표(p13221 의 표)는 그대로
    _undo_all(c, d, s)


def test_table_form_splits_into_its_own_template_on_a_numbered_level(sess):
    """번호형 레벨의 떼기(② §8-11) — 표 안의 줄은 같은 표의 형제를 통째로 옮기면 뗄 수 있다(전에는 같은 부모 아래 형제의 일부라 못 뗐다). 대표와 같은 표의 줄 일부는 전처럼 못 뗀다."""
    c, d, s = sess
    tid = _cell_tpl(s.outline, "N.")
    before = c.get(f"/api/docs/{d}/download").content
    own = next(g for g in _slot(c, d, tid, 1)["groups"] if g["key"] == "p12723")["paras"]
    units = M.split_units(s.outline, tid, 1, s.doc)
    assert len({units[p] for p in own}) == 1 and M.split_units(s.outline, 1, 5) is None                   # 그 표의 줄 = 한 묶음 · 기호 레벨은 묶음 제약이 없다
    assert M.split_block(s.outline, tid, 1, own, doc=s.doc) is None
    assert "형제 줄의 일부" in M.split_block(s.outline, tid, 1, ["p6302"], doc=s.doc)                    # 대표의 표에 있는 줄 일부
    assert M.split_block(s.outline, tid, 1, ["p6302"], doc=s.doc, partial=False) is None                  # 「형제의 일부」 만 빼고 보면 막는 것이 없다(계획 검사가 합쳐서 본다)
    r = c.post(f"/api/docs/{d}/outline/slots/{tid}/1/split", json={"likes": ["p12723"]})
    assert r.status_code == 200, r.text
    cid = r.json()["split"]["id"]
    assert cid == f"{tid}~1a" and r.json()["split"]["lines"] == len(own) and c.get(f"/api/docs/{d}/download").content == before  # 문서는 안 바뀜
    assert s.outline["templates"][cid]["slots"]["1"]["rep"] == "p12723" and all(s.outline["lines"][p]["tpl"] == cid for p in own)
    va, vc = _slot(c, d, tid, 1), _slot(c, d, cid, 1)
    assert va["ownLines"] == 2 and va["total"] == 11 - len(own) and vc["total"] == len(own) and len(vc["groups"]) == 1 and vc["ownLines"] == 0  # 뗀 템플릿은 그 표의 줄끼리 — 서식 하나
    assert c.post(f"/api/docs/{d}/outline/slots/{tid}/1/split", json={"likes": ["p6302"]}).status_code == 400
    _undo_all(c, d, s)


def test_variants_group_lines_and_show_differences(sess):
    c, d, s = sess
    v = _slot(c, d, 1, 5)
    assert v["total"] == 15 and v["rep"] == "p5209" and v["others"] == 6
    rep, *rest = v["groups"]
    assert rep["rep"] and rep["count"] == 9 and rep["diff"] == [] and rep["paras"][0] == "p5209"
    by = {g["paras"][0]: g for g in rest}
    assert by["p6502"]["diff"] == [["lead", "레터 앞 빈칸", "4칸", "3칸"]] and by["p6502"]["count"] == 5
    assert by["p5765"]["diff"] == [["gap", "레터 뒤 빈칸", "1칸", "없음"]]
    assert by["p5765"]["raw"]["lead"] == "    " and by["p5765"]["raw"]["gap"] == "" and by["p5765"]["look"]["lead"] == "4칸"  # 원값(서식 비교의 견본 글)
    # near = 대표와 오차 안(레터 앞 빈칸 1칸 차이 ≤ leadSpaces 1) — 화면 표의 「≈」(서식 라벨의 ≈ 와 같은 판단 · 대표 갈래는 늘 False)
    assert by["p6502"]["near"] is True and rep["near"] is False
    keys = c.get(f"/api/docs/{d}/outline/formats").json()["keys"]  # 비교 값 차례·이름(서식 비교 표의 열)
    assert keys[:3] == [["lead", "레터 앞 빈칸"], ["letter", "레터"], ["gap", "레터 뒤 빈칸"]] and ["L.font", "레터 글꼴"] in keys
    v2 = _slot(c, d, 2, 1)  # 글자 모양이 다른 갈래 — 레터 런과 본문 런을 따로 견준다
    keys = [x[0] for g in v2["groups"] for x in g["diff"]]
    assert "L.font" in keys and "font" in keys and "L.sizePt" in keys
    assert any(g["diff"] and g["near"] is False for g in v2["groups"])  # 글꼴이 다른 갈래 = 오차 밖 → 「≠」
    o = c.get(f"/api/docs/{d}/outline").json()
    assert o["templates"]["1"]["slots"]["5"]["rep"] == "p5209" and o["templates"]["9"]["hang"]["8|3"] == 40
    assert o["lines"]["p970"]["key"] == "□"


def test_formats_of_one_slot_lists_every_line(sess, monkeypatch):
    """`?tpl=&level=` — 그 슬롯 하나만, 갈래마다 줄 전부(문서의 「템플릿만 또렷이」 가 줄마다 대표와 다른 값을 표시: spec_헤딩_추출 ② §7)."""
    c, d, s = sess
    monkeypatch.setattr(M, "_LIST_MAX", 2)  # 모든 슬롯 응답은 갈래마다 2줄에서 자르게
    cut = _slot(c, d, 1, 5)["groups"][0]
    assert cut["count"] == 9 and len(cut["paras"]) == 2 and cut["more"] == 7
    r = c.get(f"/api/docs/{d}/outline/formats", params={"tpl": "1", "level": 5})
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["full"] is True and list(r["slots"]) == ["1"] and list(r["slots"]["1"]) == ["5"] and r["rev"] == s.rev and r["keys"][0] == ["lead", "레터 앞 빈칸"]
    one = r["slots"]["1"]["5"]
    assert one["total"] == 15 and one["rep"] == "p5209" and [len(g["paras"]) for g in one["groups"]] == [9, 5, 1] and all(g["more"] == 0 for g in one["groups"])
    assert one["groups"][1]["diff"] and not one["groups"][0]["diff"]
    assert c.get(f"/api/docs/{d}/outline/formats", params={"tpl": "1", "level": 9}).json()["slots"] == {}  # 줄이 없는 레벨
    assert c.get(f"/api/docs/{d}/outline/formats", params={"tpl": "999", "level": 1}).status_code == 404


def test_set_rep_is_model_only_and_undoable(sess):
    c, d, s = sess
    before = c.get(f"/api/docs/{d}/download").content
    r = c.put(f"/api/docs/{d}/outline/slots/1/5/rep", json={"para": "p6502"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slot"]["rep"] == "p6502" and j["undo"] == 1 and j["outline"]["templates"]["1"]["slots"]["5"]["rep"] == "p6502"
    sl = s.outline["templates"]["1"]["slots"]["5"]
    assert sl["prefix"] == "   - " and sl["repSet"] and sl["attrs"]["paraPrIDRef"] == s.doc._ids["p6502"].get("paraPrIDRef")
    assert c.get(f"/api/docs/{d}/download").content == before  # 문서는 안 바뀜
    assert c.put(f"/api/docs/{d}/outline/slots/1/5/rep", json={"para": "p970"}).status_code == 400  # 그 레벨 줄이 아님
    assert c.put(f"/api/docs/{d}/outline/slots/1/9/rep", json={"para": "p6502"}).status_code == 404
    assert c.put(f"/api/docs/{d}/outline/slots/1/5/rep", json={}).status_code == 400
    g = heading_runs.graph(s)  # 서식 복사의 내용 서식 후보도 사람이 정한 대표 줄에서(apply_reps — 그래프는 안 바꾸고 사본)
    t1 = lambda gg: next(x for x in gg["templates"] if x["id"] == 1)  # noqa: E731
    g2 = M.apply_reps(g, s.outline)
    assert next(x for x in t1(g2)["slots"] if x["level"] == 5)["rep"] == "p6502" and next(x for x in t1(g)["slots"] if x["level"] == 5)["rep"] == "p5209"
    c.post(f"/api/docs/{d}/undo")
    assert s.outline["templates"]["1"]["slots"]["5"]["rep"] == "p5209" and M.apply_reps(g, s.outline) is g
    _undo_all(c, d, s)


def test_match_symbol_letters_prefix_and_shape(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/slots/1/5/match", json={})
    assert r.status_code == 200, r.text
    j = r.json()
    # changed = 바뀐 줄 모두 · placed = 그 가운데 대표에 맞춘 줄이 아니라 확정 서식(레터 뒤 묶음 빈칸 · 둘째 줄 = 글 시작 — ② §8-8)만 건 줄(대표 + 대표 갈래 8줄)
    moved = set(j["changed"]) - set(j["placed"])                                    # 대표에 맞춘 줄 = 「   - 」 5줄 + 「    -」 1줄
    assert {"p6502", "p5765"} <= moved and len(moved) == 6 and j["outline"]["lines"]["p5765"]["letter"] == "-" and j["tops"]["blocks"]
    assert len(j["placed"]) == 9 and "p5209" in j["placed"]
    assert all(s.texts[p].startswith("    -\u2002") for p in ("p5209", "p5765", "p6502"))  # 대표 꼴(레터 앞 빈칸 4칸) · 레터 뒤 빈칸 = 묶음 빈칸
    at = OP.Measure(s.doc).place("p6502", "-")
    assert abs(at["line2Mm"] - at["textMm"]) < 0.02  # 둘째 줄 = 글 시작
    rep = s.doc._ids["p5209"]
    for pid in ("p6502", "p5765"):
        assert s.doc._ids[pid].get("paraPrIDRef") == rep.get("paraPrIDRef")
    assert len(_slot(c, d, 1, 5)["groups"]) == 1
    again = c.post(f"/api/docs/{d}/outline/slots/1/5/match", json={})
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
    assert len(r.json()["changed"]) - len(r.json()["placed"]) == g["count"] < others  # 그 갈래만 — 다른 갈래는 그대로(placed = 확정 서식만 건 대표·대표 갈래)
    assert c.post(f"/api/docs/{d}/outline/slots/4/3/match", json={"like": "p970"}).status_code == 400  # 그 레벨 줄이 아님
    assert c.post(f"/api/docs/{d}/outline/slots/4/3/match", json={"like": 3}).status_code == 400
    _undo_all(c, d, s)


def test_match_char_shapes_keep_emphasis_runs(sess):
    c, d, s = sess
    v = _slot(c, d, 2, 1)
    odd = next(g for g in v["groups"] if any(x[0] == "font" for x in g["diff"]))["paras"]
    r = c.post(f"/api/docs/{d}/outline/slots/2/1/match", json={"paras": odd})
    assert r.status_code == 200, r.text
    assert sorted(set(r.json()["changed"]) - set(r.json()["placed"])) == sorted(odd)
    rep_look = M.look(s.doc, s.outline, "p970")
    for pid in odd:
        assert M.same(M.look(s.doc, s.outline, pid), rep_look)  # 비교 값(KEYS)이 같다 — 줄 맞춤 값(장평·자간)은 그 줄 것을 지킨다(② §8-2 「줄 맞춤 값」)
    _undo_all(c, d, s)


def test_match_numbered_letters_keep_own_number(sess):
    c, d, s = sess
    assert s.texts["p5930"].startswith("5-3. ")  # 앞 공백 없음 — 대표(p968 「 1-1. 」)는 한 칸
    r = c.post(f"/api/docs/{d}/outline/slots/1/2/match", json={"paras": ["p5930", "p889"]})
    assert r.status_code == 200, r.text
    assert s.texts["p5930"].startswith(" 5-3.\u2002") and s.texts["p889"].startswith(" 7-1.\u2002")  # 대표 꼴에 제 번호 · 레터 뒤 빈칸은 묶음 빈칸(② §8-8)
    assert s.outline["lines"]["p5930"]["letter"] == "5-3."
    _undo_all(c, d, s)


def test_match_keeps_own_number_even_when_the_key_is_the_letter_itself(sess):
    """그래프가 번호 레터를 글자 그대로의 키로 둔 줄(「(2-1)」 — 정규 키 「(N-N)」 가 아님)도 대표 꼴에 **제 번호**(2026-11-22: 이관의 조정이 「(2-1)」 · 「(3-1)」 을 대표의 「(1-1)」 로 바꿨다)."""
    c, d, s = sess
    s.outline["lines"]["p5930"]["key"] = "5-3."   # 키가 번호형이 아니다(is_numbered 거짓)
    r = c.post(f"/api/docs/{d}/outline/slots/1/2/match", json={"paras": ["p5930"]})
    assert r.status_code == 200, r.text
    assert s.texts["p5930"].startswith(" 5-3. ") and s.outline["lines"]["p5930"]["letter"] == "5-3."   # 대표(「1-1.」)의 번호가 아니라 제 번호
    _undo_all(c, d, s)


def test_merge_makes_a_composite_template_and_unmerge(sess):
    c, d, s = sess
    before = c.get(f"/api/docs/{d}/download").content
    t1 = dict(s.outline["templates"]["1"], slots=dict(s.outline["templates"]["1"]["slots"]))
    # T2 「□ › o › - › ·」 를 T1 「N. › N-N. › (N) › o › -」 의 L2 아래로 — T1 L3 은 「(N)」 이지만 종속 템플릿은 다른 템플릿이라 된다(2026-11-15 사용자 「T1T3 템플릿으로」 —
    # 그때의 예 T3 「o › -」 는 2026-11-17 「잇닿은 사슬」 로 T1 L4·L5 가 되어 없다: T1 L2 아래 3곳 · T1 L3 아래 4곳에 매달린 T2 로)
    r = c.post(f"/api/docs/{d}/outline/merge", json={"child": "2", "parent": "1", "at": 2})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["merged"] == {"id": "1+2", "no": "1T2", "child": 2, "parent": 1, "at": 2, "moved": 15, "levels": [3, 6]} and j["undo"] == 1
    comp, t2 = j["outline"]["templates"]["1+2"], j["outline"]["templates"]["2"]
    assert comp["no"] == "1T2" and comp["chain"] == ["N.", "N-N.", "□", "o", "-", "·"] and comp["max"] == 6 and comp["base"] == 2 and sorted(comp["slots"]) == ["3", "4", "5", "6"]
    assert comp["comp"] == {"parent": "1", "child": "2", "at": 2, "parentNo": 1, "childNo": 2} and comp["hang"] == {"1|2": 3}
    band = next(k for k, t in s.outline["templates"].items() if t.get("kind") == "band")  # 띠 표 템플릿 「별첨N」(spec_헤딩_추출 ② §6 「띠 표 줄」) — 별첨4 아래 「□」 셋은 그 줄 아래에 매달린다(전에는 앞 장의 (N) 줄 아래에 어림으로)
    assert t2["made"][0]["id"] == "1+2" and t2["lines"] == 6 and not t2["all"] and "1|2" not in t2["hang"] and t2["hang"] == {"1|3": 1, f"{band}|1": 3}
    assert s.outline["templates"]["1"]["chain"] == t1["chain"] and s.outline["templates"]["1"]["max"] == t1["max"]  # T1 은 안 바뀐다
    mine = {p: x for p, x in s.outline["lines"].items() if x["tpl"] == "1+2"}
    first = next(p for p, x in mine.items() if x["level"] == 3)
    assert len(mine) == 15 and all(x["no"] == "1T2" for x in mine.values()) and s.outline["lines"][s.outline["lines"][first]["parent"]]["tpl"] == "1"
    assert c.get(f"/api/docs/{d}/download").content == before  # 문서는 안 바뀜
    v = _slot(c, d, "1+2", 3)
    assert v["total"] == 3 and v["rep"] in mine
    # 종속 템플릿 줄의 개요 편집: Enter = 그 템플릿의 다음 레벨(L4 「o」) · Alt+↑ = 첫 레벨이라 부모 줄의 (T1, L2)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": first, "offset": len(s.texts[first])})
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["lines"][r.json()["focus"]["id"]] == {"no": "1T2", "level": 4, "tpl": "1+2", "letter": "o", "role": "heading", "key": "o"}
    c.post(f"/api/docs/{d}/undo")
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [first], "delta": -1})
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["lines"][first]["tpl"] == "1" and r.json()["outline"]["lines"][first]["level"] == 2
    c.post(f"/api/docs/{d}/undo")
    # 둘째 종속 · 같은 것 또 · 매달린 곳 없음 · 제 자신 · 잘못된 값
    r = c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 3})
    assert r.status_code == 200 and r.json()["merged"]["no"] == "8T9" and r.json()["merged"]["moved"] == 80 and r.json()["merged"]["levels"] == [4, 6]
    again = c.post(f"/api/docs/{d}/outline/merge", json={"child": "2", "parent": "1", "at": 2})
    assert again.status_code == 400 and "T1T2" in again.json()["detail"]
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "5", "parent": "8", "at": 1}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "8", "parent": "8", "at": 1}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 0}).status_code == 400
    # 떼기 — 종속 템플릿이 없어지고 줄이 T2 로
    r = c.post(f"/api/docs/{d}/outline/unmerge", json={"child": "2", "parent": "1"})
    assert r.status_code == 200, r.text
    assert r.json()["back"] == 15 and "1+2" not in r.json()["outline"]["templates"]
    assert sum(1 for x in s.outline["lines"].values() if x["tpl"] == "2") == 21 and all(x["key"] in ("□", "o", "-", "·") for x in s.outline["lines"].values() if x["tpl"] == "2")
    assert "1+2" not in str(s.outline.get("branches"))
    assert c.post(f"/api/docs/{d}/outline/unmerge", json={"child": "2", "parent": "1"}).status_code == 400
    c.post(f"/api/docs/{d}/undo")  # 떼기 되돌림 → 종속 템플릿이 다시
    assert "1+2" in s.outline["templates"]
    _undo_all(c, d, s)
    assert "1+2" not in s.outline["templates"] and "8+9" not in s.outline["templates"] and not s.outline.get("merges")


def test_merge_and_rep_carry_over_a_new_overlay(sess):
    c, d, s = sess
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "2", "parent": "1", "at": 2}).status_code == 200
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 3}).status_code == 200
    rest = [p for p, x in s.outline["lines"].items() if x["tpl"] == "2" and x["level"] == 1][-1]  # T2 에 남은 줄(넣은 자리 밖 — T1 L3 아래)
    assert c.put(f"/api/docs/{d}/outline/slots/2/1/rep", json={"para": rest}).status_code == 200
    ov = OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)  # 2단계를 다시 돌린 것과 같이 — 그래프에서 새로 만든 오버레이
    assert not ov.get("merges") and "1+2" not in ov["templates"]
    fails = M.carry(s.outline, ov, M.context(s.doc, ov))
    assert fails == [] and ov["templates"]["1+2"]["no"] == "1T2" and ov["templates"]["8+9"]["max"] == 6
    assert sum(1 for x in ov["lines"].values() if x["tpl"] == "8+9") == 80 and ov["templates"]["2"]["slots"]["1"]["rep"] == rest
    _undo_all(c, d, s)


def _tpl_lines(s, tid, level=None):
    return [p for p, x in s.outline["lines"].items() if x["tpl"] == str(tid) and (level is None or x["level"] == level)]


def test_split_makes_a_format_variant_template_and_unsplit(sess):
    """서식 종속 템플릿(② §8-5) — T9 「[기관] › o › -」 L2 「o」 의 갈래(대표 ×31 · ×9 · ×2 · ×1 · ×1)를 「T9L2a」 로 떼고 합친다."""
    c, d, s = sess
    before = c.get(f"/api/docs/{d}/download").content
    v = _slot(c, d, 9, 2)
    assert [g["count"] for g in v["groups"]] == [31, 9, 2, 1, 1] and v["rep"] == "p1692"
    g9, g2, g1 = v["groups"][1]["paras"], v["groups"][2]["paras"], v["groups"][3]["paras"]
    kids = [p for p in _tpl_lines(s, 9, 3) if s.outline["lines"][p]["parent"] in g9]  # 뗄 줄 아래의 T9 줄 — 같이 간다
    t9 = dict(s.outline["templates"]["9"])
    r = c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": [g9[0]]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["split"] == {"id": "9~2a", "no": "9L2a", "of": 9, "level": 2, "moved": 9 + len(kids), "lines": 9, "added": False} and j["undo"] == 1
    C, A = j["outline"]["templates"]["9~2a"], j["outline"]["templates"]["9"]
    assert C["no"] == "9L2a" and C["chain"] == ["[기관]", "o", "-"] and C["base"] == 1 and C["max"] == 3 and sorted(C["slots"]) == ["2", "3"]  # 줄은 L2 부터 — L1 은 T9 의 레벨
    assert C["vari"] == {"of": "9", "level": 2, "sfx": "a", "ofNo": 9} and C["hang"] == {"9|1": 9} and C["lines"] == 9 + len(kids) and C["comp"] is None
    assert A["splits"] == [{"id": "9~2a", "no": "9L2a", "level": 2, "sfx": "a", "lines": 9 + len(kids)}] and A["vari"] is None
    assert s.outline["templates"]["9"]["chain"] == t9["chain"] and s.outline["templates"]["9"]["slots"]["2"]["rep"] == "p1692"  # T9 는 안 바뀐다
    sl = s.outline["templates"]["9~2a"]["slots"]["2"]
    assert sl["rep"] == g9[0] and sl["attrs"]["paraPrIDRef"] == s.doc._ids[g9[0]].get("paraPrIDRef") and s.texts[g9[0]].startswith(sl["prefix"]) and "pos" not in sl
    assert all(s.outline["lines"][p]["no"] == "9L2a" and s.outline["lines"][p]["level"] == 2 for p in g9)
    assert "9~2a" in s.outline["branches"]["9|1"] and c.get(f"/api/docs/{d}/download").content == before  # 문서는 안 바뀜
    va, vc = _slot(c, d, 9, 2), _slot(c, d, "9~2a", 2)
    assert va["total"] == 35 and len(va["groups"]) == 4 and vc["total"] == 9 and vc["rep"] == g9[0] and len(vc["groups"]) == 1
    # 뗀 줄의 Enter = 그 템플릿의 다음 레벨(L3 「-」)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": g9[0], "offset": len(s.texts[g9[0]])})
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["lines"][r.json()["focus"]["id"]] == {"no": "9L2a", "level": 3, "tpl": "9~2a", "letter": "-", "role": "heading", "key": "-"}
    c.post(f"/api/docs/{d}/undo")
    # 이미 있는 템플릿에 더 넣기 → 그 템플릿 안에서 「대표에 맞추기」 · 또 떼면 「T9L2b」
    r = c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": [g2[0]], "into": "9~2a"})
    assert r.status_code == 200 and r.json()["split"]["added"] and r.json()["split"]["lines"] == 2 and r.json()["split"]["no"] == "9L2a"
    vc = _slot(c, d, "9~2a", 2)
    assert vc["total"] == 11 and vc["rep"] == g9[0] and vc["others"] == 2
    r = c.post(f"/api/docs/{d}/outline/slots/9~2a/2/match", json={})
    assert r.status_code == 200 and sorted(set(r.json()["changed"]) - set(r.json()["placed"])) == sorted(g2)  # placed = 확정 서식만 건 대표·대표 갈래(② §8-8)
    assert M.look(s.doc, s.outline, g2[0]) == M.look(s.doc, s.outline, g9[0]) != M.look(s.doc, s.outline, "p1692")
    c.post(f"/api/docs/{d}/undo")
    r = c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": g1})
    assert r.status_code == 200 and r.json()["split"]["no"] == "9L2b" and [x["no"] for x in r.json()["outline"]["templates"]["9"]["splits"]] == ["9L2a", "9L2b"]
    # 못 떼는 것: 대표 갈래 · 그 레벨 줄이 아님 · 없는 레벨 · 남의 템플릿에 더 넣기 · 종속 템플릿의 부모 레벨 · 번호형 레벨에서 형제의 일부 · 잘못된 값 · 「하위로」
    bad = c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": ["p1692"]})
    assert bad.status_code == 400 and "대표 서식" in bad.json()["detail"]
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": ["p970"]}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/slots/9/7/split", json={"likes": [g9[0]]}).status_code == 404
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": []}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": [v["groups"][4]["paras"][0]], "into": "3"}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": [v["groups"][4]["paras"][0]], "sfx": "A"}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/slots/9/2/split", json={"likes": [v["groups"][4]["paras"][0]], "sfx": "a"}).status_code == 400  # 이미 있는 글자
    num = next(g for g in _slot(c, d, 5, 1)["groups"] if not g["rep"])  # T5 L1 「가.」 — 번호형
    bad = c.post(f"/api/docs/{d}/outline/slots/5/1/split", json={"likes": [num["paras"][0]]})
    assert bad.status_code == 400 and "번호형" in bad.json()["detail"]
    bad = c.post(f"/api/docs/{d}/outline/merge", json={"child": "9~2a", "parent": "9", "at": 1})
    assert bad.status_code == 400 and "서식 종속" in bad.json()["detail"]
    undo = s.state()["undo"]
    # 합치기 — 템플릿이 없어지고 줄이 T9 의 같은 레벨로
    r = c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "9~2b"})
    assert r.status_code == 200 and r.json()["back"] == 1 and "9~2b" not in r.json()["outline"]["templates"]
    r = c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "9~2a"})
    assert r.status_code == 200, r.text
    assert r.json()["back"] == 11 + len(kids) and r.json()["outline"]["templates"]["9"]["splits"] == [] and s.state()["undo"] == undo + 2
    assert not s.outline["splits"] and "9~2" not in str(s.outline["branches"]) and len(_tpl_lines(s, 9, 2)) == 44
    assert c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "9~2a"}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "9"}).status_code == 400
    c.post(f"/api/docs/{d}/undo")  # 합치기 되돌림 → 템플릿이 다시
    assert "9~2a" in s.outline["templates"] and len(_tpl_lines(s, "9~2a", 2)) == 11
    _undo_all(c, d, s)
    assert "9~2a" not in s.outline["templates"] and not s.outline.get("splits")


def test_split_at_first_level_and_level_up(sess):
    """첫 레벨(L1)에서 떼면 base 0 — 원래 템플릿이 매달리던 자리에 같이 매달린다. 뗀 줄의 Alt+↑ 는 첫 레벨이면 부모 줄의 자리로."""
    c, d, s = sess
    v = _slot(c, d, 2, 1)  # T2 「□ › o › - › ·」 L1 — 대표 ×3 · ×3 · ×1
    fam = lambda paras: M._members(s.outline, "2", paras)  # noqa: E731 — 그 줄들과 그 아래 T2 줄
    odd = next(g["paras"] for g in v["groups"] if len(fam(g["paras"])) > len(g["paras"]))  # 아래에 o · - 줄이 달린 갈래
    if v["rep"] in odd:  # 그 갈래가 대표면 다른 갈래의 줄을 대표로 정한 뒤 뗀다(대표 갈래는 못 뗀다)
        other = next(g["paras"][0] for g in v["groups"] if g["paras"][0] not in odd)
        assert c.put(f"/api/docs/{d}/outline/slots/2/1/rep", json={"para": other}).status_code == 200
    want = len(fam(odd))
    r = c.post(f"/api/docs/{d}/outline/slots/2/1/split", json={"likes": [odd[0]]})
    assert r.status_code == 200, r.text
    C = r.json()["outline"]["templates"]["2~1a"]
    assert C["no"] == "2L1a" and C["base"] == 0 and sorted(C["slots"]) == ["1", "2", "3", "4"] and C["kind"] == "branch"
    assert all("2~1a" in lst for key, lst in s.outline["branches"].items() if "2" in lst)  # T2 가 매달린 자리마다
    assert r.json()["split"]["moved"] == want > len(odd)  # 그 아래 o · - 줄도 같이
    deep = _tpl_lines(s, "2~1a", 2)
    assert deep and s.outline["templates"]["2~1a"]["slots"]["2"]["rep"] in deep
    # T4 「[…] › o › - › ·」 L3 「-」 의 갈래를 떼면 「T4L3a」(base 2) — 그 줄의 Alt+↑ 는 부모 줄의 (T4, L2)
    v = _slot(c, d, 4, 3)
    g = next(x for x in v["groups"] if not x["rep"] and x["count"] == 7)["paras"]
    r = c.post(f"/api/docs/{d}/outline/slots/4/3/split", json={"likes": [g[0]]})
    assert r.status_code == 200 and r.json()["split"]["no"] == "4L3a" and r.json()["outline"]["templates"]["4~3a"]["base"] == 2
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [g[0]], "delta": -1})
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["lines"][g[0]]["tpl"] == "4" and r.json()["outline"]["lines"][g[0]]["level"] == 2
    _undo_all(c, d, s)


def test_split_on_a_composite_carries_and_blocks_unmerge(sess):
    c, d, s = sess
    assert c.post(f"/api/docs/{d}/outline/merge", json={"child": "9", "parent": "8", "at": 3}).status_code == 200  # 「T8T9」 L4~L6
    v = _slot(c, d, "8+9", 5)
    g = next(x for x in v["groups"] if not x["rep"])["paras"]
    r = c.post(f"/api/docs/{d}/outline/slots/8+9/5/split", json={"likes": [g[0]]})
    assert r.status_code == 200, r.text
    assert r.json()["split"]["id"] == "8+9~5a" and r.json()["split"]["no"] == "8T9L5a" and r.json()["outline"]["templates"]["8+9~5a"]["base"] == 4
    assert c.post(f"/api/docs/{d}/outline/slots/8+9/3/split", json={"likes": [g[0]]}).status_code in (400, 404)  # L3 은 T8 의 레벨
    bad = c.post(f"/api/docs/{d}/outline/unmerge", json={"child": "9", "parent": "8"})
    assert bad.status_code == 400 and "8T9L5a" in bad.json()["detail"]  # 뗀 것이 있으면 그것부터
    n = len(_tpl_lines(s, "8+9~5a"))
    assert c.put(f"/api/docs/{d}/outline/slots/8+9~5a/5/rep", json={"para": _tpl_lines(s, "8+9~5a", 5)[-1]}).status_code == 200
    rep = s.outline["templates"]["8+9~5a"]["slots"]["5"]["rep"]
    ov = OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)  # 2단계를 다시 돌린 것과 같이
    fails = M.carry(s.outline, ov, M.context(s.doc, ov))
    assert fails == [] and ov["templates"]["8+9~5a"]["no"] == "8T9L5a" and ov["templates"]["8+9~5a"]["base"] == 4
    assert sum(1 for x in ov["lines"].values() if x["tpl"] == "8+9~5a") == n and ov["templates"]["8+9~5a"]["slots"]["5"]["rep"] == rep
    assert [m["id"] for m in ov["splits"]] == ["8+9~5a"] and ov["templates"]["8+9~5a"]["slots"]["5"]["repSet"]
    assert c.post(f"/api/docs/{d}/outline/unsplit", json={"id": "8+9~5a"}).status_code == 200
    assert c.post(f"/api/docs/{d}/outline/unmerge", json={"child": "9", "parent": "8"}).status_code == 200
    _undo_all(c, d, s)


def test_template_match_with_splits_is_one_transaction(sess):
    """템플릿 맞추기 끝점의 levels[].splits(② §8-5 「한 번에」 — 정리 에이전트의 적용): 맞추기 + 떼기 + 뗀 줄 맞추기가 실행 취소 한 번."""
    c, d, s = sess
    v = _slot(c, d, 4, 3)  # T4 L3 「-」 — 대표 ×9 · ×7 · ×1 · ×1
    assert [g["count"] for g in v["groups"]] == [9, 7, 1, 1]
    big, a, b = (g["paras"] for g in v["groups"][1:])
    undo = s.state()["undo"]
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"by": "agent", "levels": [{"level": 3, "likes": [a[0]], "splits": [{"likes": [big[0], b[0]], "rep": big[0], "sfx": "c"}]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    kids = len(_tpl_lines(s, "4~3c")) - 8
    assert sorted(set(j["changed"]) - set(j["placed"])) == sorted([a[0], b[0]]) and j["undo"] == undo + 1 and j["levels"] == [{"level": 3, "rep": v["rep"], "repChanged": False, "changed": 1}]
    assert j["splits"] == [{"level": 3, "id": "4~3c", "no": "4L3c", "moved": 8 + kids, "changed": 1}] and j["outline"]["lines"][big[0]]["no"] == "4L3c"
    assert M.look(s.doc, s.outline, a[0]) == M.look(s.doc, s.outline, v["rep"]) and M.look(s.doc, s.outline, b[0]) == M.look(s.doc, s.outline, big[0])
    assert len(_slot(c, d, 4, 3)["groups"]) == 1 and _slot(c, d, "4~3c", 3)["total"] == 8 and len(_slot(c, d, "4~3c", 3)["groups"]) == 1
    c.post(f"/api/docs/{d}/undo")  # 한 번에 다 돌아온다
    assert "4~3c" not in s.outline["templates"] and len(_slot(c, d, 4, 3)["groups"]) == 4 and s.state()["undo"] == undo
    # 떼기만(문서는 안 바뀜 — 오버레이만) · 글자는 빈 것 가운데 첫 것 · match=false 면 뗀 줄을 안 맞춘다
    before = c.get(f"/api/docs/{d}/download").content
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"levels": [{"level": 3, "likes": [], "splits": [{"likes": [big[0], b[0]], "rep": big[0], "match": False}, {"likes": [a[0]]}]}]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["changed"] == [] and j["reps"] == 0 and [x["no"] for x in j["splits"]] == ["4L3a", "4L3b"] and j["splits"][0]["changed"] == 0
    assert j["outline"]["templates"]["4~3a"]["vari"]["sfx"] == "a" and c.get(f"/api/docs/{d}/download").content == before
    assert len(_slot(c, d, "4~3a", 3)["groups"]) == 2
    c.post(f"/api/docs/{d}/undo")
    assert "4~3a" not in s.outline["templates"] and "4~3b" not in s.outline["templates"]
    # 못 하는 것 — 오버레이는 그대로
    for levels in ([{"level": 3, "likes": [big[0]], "splits": [{"likes": [big[0]]}]}],            # 맞추면서 뗌
                   [{"level": 3, "splits": [{"likes": [v["rep"]]}]}],                                # 대표 갈래
                   [{"level": 3, "splits": [{"likes": [big[0]]}, {"likes": [big[0]]}]}],             # 두 번
                   [{"level": 3, "splits": [{"likes": [big[0]], "sfx": "a"}, {"likes": [a[0]], "sfx": "a"}]}],  # 같은 글자
                   [{"level": 3, "splits": [{"likes": [big[0]], "rep": a[0]}]}],                     # 대표가 그 갈래 줄이 아님
                   [{"level": 3, "splits": [{"likes": []}]}]):
        assert c.post(f"/api/docs/{d}/outline/templates/4/match", json={"levels": levels}).status_code == 400, levels
    assert not s.outline.get("splits") and s.state()["undo"] == undo
    # 대표를 바꾸면서 옛 대표 갈래를 뗀다 — 새 대표가 먼저
    r = c.post(f"/api/docs/{d}/outline/templates/4/match", json={"levels": [{"level": 3, "rep": big[0], "likes": [], "splits": [{"likes": [v["rep"]]}]}]})
    assert r.status_code == 200, r.text
    assert s.outline["templates"]["4"]["slots"]["3"]["rep"] == big[0] and s.outline["lines"][v["rep"]]["tpl"] == "4~3a" and r.json()["reps"] == 1
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
