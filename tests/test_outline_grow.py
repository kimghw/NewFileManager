"""개요 레벨 더하기(spec_hwpx_웹편집 ② §8-6 — app/outline_grow.py · app/outline_grow_api.py): 마지막 레벨의 Alt+↓ → 레터·앞 공백·둘째 줄 후보 → 템플릿에 새 레벨.
연구개발계획서 양식(2단계 LLM 끔 → 가지 템플릿 T2 「□›o›-›·」 — p970 □ › p972 o › p974 - › p975 ⋅ · 다음 묶음 p977 o › p979 - › p980 ⋅).
레터 키 · 후보(사슬에 없는 계열만 · 깊은 기호 먼저 · 10개까지 · 앞 공백 = 마지막 두 레벨의 차만큼 더) · 더하기(번호형 — 사슬·max·슬롯·자리 규칙 · 줄 접두 · 둘째 줄 = 글 시작 ·
새 레벨의 Enter = 다음 번호 · 윗 레벨의 Enter = 그 아래 레벨 · 기존 줄의 Alt+↓ 가 새 레벨로 + 번호 다시 매김) · 여러 줄 한 번에(기호 · 둘째 줄 = 레터 자리 / 윗 레벨과 같게) ·
거절(이미 쓰는 계열 · 레터 아님 · 값 범위 · 마지막 레벨이 아님 · 괄호 줄 — 오버레이 그대로) · 실행 취소 = 원본 바이트 + 오버레이 복원 ·
같이 늘리는 템플릿(종속 · 서식 종속 — 순수 함수) · 2단계 다시 실행 뒤 잇기(carry)."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import outline_grow as OG
from app import server
from app.hwpx_doc import P

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
    tmp = tmp_path_factory.mktemp("outline_grow")  # 모듈 픽스처는 conftest 의 시험별 임시 폴더보다 먼저 돈다 — 사용자 작업 폴더에 작업이 쌓이지 않게(test_outline_edit 와 같다)
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
    t = s.outline["templates"]["2"]
    assert t["max"] == 4 and t["chain"] == ["□", "o", "-", "·"] and "5" not in t["slots"] and not s.outline.get("grows")  # 오버레이도 그 편집 앞으로


def _text(s, pid):
    return s.doc._text(s.doc._ids[pid])


def _para(s, pid):
    return s.doc._para_summary(s.doc._defs["paraPr"][s.doc._ids[pid].get("paraPrIDRef")])


def _under(s, pid, n):
    par = s.doc._ids[pid].getparent()
    seq = [(s.doc._rev.get(k), s.doc._text(k)) for k in par.iterchildren(P)]
    i = next(k for k, (q, _) in enumerate(seq) if q == pid)
    return [(q, t) for q, t in seq[i:i + n] if t.strip()]


# ---------------------------------------------------------------- 레터 키
def test_letter_key():
    want = {"·": "·", "•": "·", "⋅": "·", "▪": "▫", "▶": "▶", "◇": "◇", "-": "-", "○": "o", "o": "o", "□": "□", "①": "①", "③": "①", "(1)": "(N)", "(12)": "(N)", "1)": "N)",
            "가)": "가)", "다)": "가)", "(가)": "(가)", "가.": "가.", "a.": "a.", "c)": "a)", "1.": "N."}
    assert {k: OG.letter_key(k) for k in want} == want  # 2단계 그래프의 정규 키와 같은 꼴(변형군은 한 키)
    for bad in ("※", "*", "→", "", " ", "가나다라마바사아자", "[기관]", "a b", None, 3):  # 안내·각주·화살표는 헤딩 추출이 개요 레터로 보지 않는다 · 괄호 라벨 · 공백 · 너무 긴 글
        with pytest.raises(ValueError):
            OG.letter_key(bad)
    assert all(OG.letter_key(lt) for lt, _ in OG.POOL)  # 제안 레터는 모두 개요 레터
    assert all(OE.is_numbered(OG.letter_key(lt)) == (lt[0] not in "·•▪▶◇-○o□") for lt, _ in OG.POOL)  # 번호형은 번호를 매길 수 있는 꼴만(둘레 글자 ㉮ 없음)


# ---------------------------------------------------------------- 후보
def test_suggest(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/grow/suggest", json={"ids": ["p975"]})
    assert r.status_code == 200, r.text
    o = r.json()
    assert (o["tpl"], o["no"], o["level"], o["chain"], o["lines"]) == ("2", 2, 5, ["□", "o", "-", "·"], 1)
    assert o["last"] == {"level": 4, "letter": "⋅", "lead": 5, "gap": "", "prefix": "     ⋅"}
    assert o["lead"] == 6 and o["gap"] == " " and o["line2"] == "text"  # 앞 공백 = 5칸 + (5 − 4)칸 · 마지막 레벨에 레터 뒤 공백이 없으면 한 칸
    assert [k for k, _ in o["line2s"]] == ["text", "letter", "keep"]
    cs = o["candidates"]
    assert 3 <= len(cs) <= OG.MAX_SHOW and not {x["key"] for x in cs} & {"□", "o", "-", "·"}  # 이 템플릿이 쓰는 계열은 없다
    assert [x["letter"] for x in cs][:4] == ["▪", "▶", "◇", "①"] and [x["numbered"] for x in cs][:4] == [False, False, False, True]  # 깊은 기호가 먼저, 그다음 번호형
    assert next(x for x in cs if x["letter"] == "(1)")["key"] == "(N)" and next(x for x in cs if x["letter"] == "①")["inDoc"]  # 이 문서의 다른 템플릿이 「①」 을 쓴다
    assert s.state()["undo"] == 0 and s.outline["templates"]["2"]["max"] == 4  # 후보 받기는 아무것도 안 바꾼다
    # 여러 줄(같은 템플릿의 같은 마지막 레벨)
    assert c.post(f"/api/docs/{d}/outline/grow/suggest", json={"ids": ["p975", "p980"]}).json()["lines"] == 2
    # 더할 수 없는 자리
    for ids, word in ((["p972"], "이미 L3"), (["p975", "p974"], "같은 레벨"), (["p1725"], "구분 라벨"), (["p969"], "개요 줄이 아닙니다"), ([], "id")):
        r = c.post(f"/api/docs/{d}/outline/grow/suggest", json={"ids": ids})
        assert r.status_code == 400 and word in r.json()["detail"], (ids, r.text)


def test_candidates_order_after_dash():
    """사슬 「□›o›-」(사용자 문서 꼴) — 「-」 보다 깊은 기호(· • ▪ ▶ ◇)가 먼저, 그다음 번호형. 문서의 다른 템플릿이 「·」 계열을 「⋅」 로 쓰면 그 글자로 권한다."""
    slot = lambda letter, prefix: {"letter": letter, "key": OG.letter_key(letter), "rep": "x", "count": 3, "prefix": prefix, "attrs": {"paraPrIDRef": "1", "styleIDRef": "0", "charPrIDRef": "1"}, "spacer": None}  # noqa: E731
    ov = {"lines": {}, "templates": {"1": {"no": 1, "kind": "main", "anchor": "body:□›o›-", "chain": ["□", "o", "-"], "max": 3,
                                           "slots": {"1": slot("□", "□ "), "2": slot("o", " o "), "3": slot("-", "   - ")}}}}
    assert [x["letter"] for x in OG.candidates(ov, "1", 3)] == ["·", "•", "▪", "▶", "◇", "①", "(1)", "1)", "가)", "(가)"]
    ov["templates"]["2"] = {"no": 2, "kind": "cell", "anchor": "cell:·", "chain": ["·"], "max": 1, "slots": {"1": slot("⋅", "⋅")}}
    cs = OG.candidates(ov, "1", 3)
    assert [x["letter"] for x in cs][:2] == ["⋅", "•"] and cs[0]["inDoc"] and cs[0]["key"] == "·"
    assert OG._lead_default(ov, "1", 3, ov["templates"]["1"]["slots"]["3"]) == (5, " ")  # 3칸 + (3 − 1)칸
    assert OG._lead_default(ov, "2", 1, ov["templates"]["2"]["slots"]["1"]) == (2, " ")  # 윗 레벨이 없으면 2칸 더


# ---------------------------------------------------------------- 더하기
def test_grow_numbered_level(sess):
    c, d, s = sess
    base = s.outline["templates"]["2"]["slots"]["4"]["attrs"]["paraPrIDRef"]
    r = c.post(f"/api/docs/{d}/outline/grow", json={"ids": ["p975"], "letter": "(3)"})  # 번호형은 그 꼴의 첫 번호로
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["grown"] == {"tpl": "2", "no": 2, "level": 5, "letter": "(1)", "key": "(N)", "lead": 6, "line2": "text", "also": []}
    assert o["outline"]["lines"] == {"p975": {"no": 2, "level": 5, "tpl": "2", "letter": "(1)", "role": "heading", "key": "(N)"}}
    assert o["focus"] == {"id": "p975", "offset": 10} and o["undo"] == 1 and o["kinds"]["p975"] and o["owpml"]["status"] != "fail"
    assert _text(s, "p975") == "      (1) "
    t = s.outline["templates"]["2"]
    assert t["chain"] == ["□", "o", "-", "·", "(N)"] and t["max"] == 5
    sl = t["slots"]["5"]
    assert (sl["letter"], sl["key"], sl["prefix"], sl["rep"], sl["grown"], sl["pos"]) == ("(1)", "(N)", "      (1) ", "p975", True, {"line2": "text", "set": True})
    assert sl["attrs"] == s.outline["templates"]["2"]["slots"]["4"]["attrs"]  # 모양은 마지막 레벨 슬롯의 것(새 정의를 만들지 않는다)
    assert s.outline["lines"]["p975"]["parent"] == "p974" and s.outline["grows"][0]["level"] == 5
    a, b = _para(s, "p975"), s.doc._para_summary(s.doc._defs["paraPr"][base])
    assert a["firstLineMm"] < 0 and {**a, "firstLineMm": b["firstLineMm"]} == b  # 둘째 줄 = 글 시작(접두 폭만큼 내어쓰기) — 그 밖의 문단 모양은 마지막 레벨 것
    v = c.get(f"/api/docs/{d}/outline").json()["templates"]["2"]
    assert v["chain"][-1] == "(N)" and v["max"] == 5 and v["slots"]["5"]["letter"] == "(1)" and v["slots"]["5"]["lines"] == 1 and v["slots"]["5"]["rep"] == "p975"
    assert abs(v["slots"]["5"]["to"]["line2Mm"] - v["slots"]["5"]["to"]["textMm"]) < 0.2  # 새 줄의 둘째 줄 = 글 시작
    # 새 레벨의 Enter = 같은 레벨 다음 번호 · 윗 레벨(L3)의 Enter = L4 줄(전과 같다) · 그 L4 줄의 Alt+↓ = 새 레벨로(이제 있다) + 형제 번호 다시
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p975", "offset": 99})
    assert r.status_code == 200, r.text
    n5 = r.json()["outline"]["new"][0]
    assert r.json()["outline"]["lines"][n5]["level"] == 5 and _text(s, n5) == "      (2) "
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p974", "offset": 99})
    n4 = r.json()["outline"]["new"][0]
    assert r.json()["outline"]["lines"][n4] == {"no": 2, "level": 4, "tpl": "2", "letter": "⋅", "role": "heading", "key": "·"}
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [n4], "delta": 1})
    assert r.status_code == 200, r.text
    assert [t for _, t in _under(s, "p974", 5)] == ["    - ", "      (1) ", "      (2) ", "      (3) "] and _text(s, n4) == "      (1) " and _text(s, "p975") == "      (2) "
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [n4], "delta": 1})  # 이제 그 레벨이 마지막 — 더 내릴 곳 없음(화면이 다시 후보를 연다)
    assert r.status_code == 400 and "더 깊은 레벨이 없습니다" in r.json()["detail"]
    assert c.post(f"/api/docs/{d}/outline/grow/suggest", json={"ids": [n4]}).json()["level"] == 6
    _undo_all(c, d, s)


def test_grow_block_symbol_letter_and_keep(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline/grow", json={"ids": ["p980", "p975"], "letter": "▪", "lead": 8, "line2": "letter"})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["grown"]["letter"] == "▪" and o["grown"]["key"] == "▫" and o["grown"]["lead"] == 8 and set(o["outline"]["lines"]) == {"p975", "p980"}
    assert _text(s, "p975") == _text(s, "p980") == "        ▪ " and o["undo"] == 1  # 두 줄을 한 트랜잭션으로
    sl = s.outline["templates"]["2"]["slots"]["5"]
    assert sl["pos"]["line2"] == "mm" and sl["pos"]["set"] and sl["pos"]["mm"] > 0 and sl["rep"] == "p975"
    for pid in ("p975", "p980"):  # 둘째 줄 = 레터 자리: 첫 줄이 앞 공백 폭만큼 내어쓰기
        a = _para(s, pid)
        assert a["firstLineMm"] < 0 and abs(a["indentLeftMm"] + max(-a["firstLineMm"], 0) - sl["pos"]["mm"]) < 0.05
    _undo_all(c, d, s)
    # 둘째 줄 = 윗 레벨과 같게 — 문단 모양은 마지막 레벨 슬롯의 것 그대로
    r = c.post(f"/api/docs/{d}/outline/grow", json={"ids": ["p975"], "letter": "◇", "lead": 0, "line2": "keep"})
    assert r.status_code == 200, r.text
    sl = s.outline["templates"]["2"]["slots"]["5"]
    assert _text(s, "p975") == "◇ " and sl["pos"] == {"line2": "keep", "set": True} and s.doc._ids["p975"].get("paraPrIDRef") == sl["attrs"]["paraPrIDRef"]
    _undo_all(c, d, s)


def test_grow_rejects(sess):
    c, d, s = sess
    snap = copy.deepcopy(s.outline)
    cases = (({"ids": ["p975"], "letter": "o"}, "이미 씁니다"), ({"ids": ["p975"], "letter": "•"}, "이미 씁니다"), ({"ids": ["p975"], "letter": "※"}, "개요 레터로 읽히지 않습니다"),
             ({"ids": ["p975"], "letter": ""}, "1~8글자"), ({"ids": ["p975"], "letter": "①", "lead": 99}, "0~40칸"), ({"ids": ["p975"], "letter": "①", "lead": "3"}, "0~40칸"),
             ({"ids": ["p975"], "letter": "①", "line2": "x"}, "line2"), ({"ids": ["p972"], "letter": "①"}, "이미 L3"), ({"ids": ["p1725"], "letter": "①"}, "구분 라벨"),
             ({"ids": ["p969"], "letter": "①"}, "개요 줄이 아닙니다"), ({"letter": "①"}, "id"))
    for body, word in cases:
        r = c.post(f"/api/docs/{d}/outline/grow", json=body)
        assert r.status_code == 400 and word in r.json()["detail"], (body, r.text)
    assert s.outline == snap and s.state()["undo"] == 0  # 거절은 오버레이·문서를 안 건드린다
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


# ---------------------------------------------------------------- 같이 늘리는 템플릿 · 되돌리기(순수 함수)
def _ov():
    sl = lambda letter, prefix: {"letter": letter, "key": OG.letter_key(letter), "rep": None, "count": 1, "prefix": prefix,  # noqa: E731
                                 "attrs": {"paraPrIDRef": "1", "styleIDRef": "0", "charPrIDRef": "1"}, "spacer": None}
    tp = {"A": {"no": 1, "kind": "main", "anchor": "body:N.›가.", "chain": ["N.", "가."], "max": 2, "slots": {"1": sl("1.", "1. "), "2": sl("가.", " 가. ")}},
          "B": {"no": 3, "kind": "branch", "anchor": "body:□›o", "chain": ["□", "o"], "max": 2, "slots": {"1": sl("□", "□ "), "2": sl("o", "  o ")}},
          # 종속 템플릿 「T1T3」 — B 를 (A, L1) 아래로: L2 □ · L3 o
          "A+B": {"no": "1T3", "kind": "branch", "anchor": "body:N.›가.>1>body:□›o", "chain": ["N.", "□", "o"], "max": 3, "base": 1,
                  "slots": {"2": sl("□", "□ "), "3": sl("o", "  o ")}, "composite": {"parent": "A", "child": "B", "at": 1}},
          # 서식 종속 템플릿 「T3L2a」 — B 의 L2 에서 뗀 갈래
          "B~2a": {"no": "3L2a", "kind": "branch", "anchor": "body:□›o~L2a", "chain": ["□", "o"], "max": 2, "base": 1, "slots": {"2": sl("o", "   o ")},
                   "variant": {"of": "B", "level": 2, "sfx": "a"}}}
    lines = {"x": {"tpl": "A+B", "no": "1T3", "level": 3, "parent": None, "letter": "o", "key": "o", "role": "heading", "flow": "body"}}
    return {"lines": lines, "templates": tp, "branches": {}, "seq": 2}


def test_related_templates_grow_together():
    ov = _ov()
    assert sorted(OG._related(ov, "A+B", 4)) == [("B", 3), ("B~2a", 3)]  # 종속 템플릿 L4 = 넣은 템플릿 B 의 L3 = B 에서 뗀 서식 종속 템플릿의 L3
    assert sorted(OG._related(ov, "B", 3)) == [("A+B", 4), ("B~2a", 3)] and OG._related(ov, "A", 3) == []
    before = copy.deepcopy(ov)
    g = OG.prepare(None, ov, ["x"], "-", None, "text")
    assert (g["tid"], g["level"], g["key"], sorted(map(tuple, g["also"]))) == ("A+B", 4, "-", [("B", 3), ("B~2a", 3)]) and g["slot"]["prefix"] == "    - " and ov == before
    pv = OG.preview_ov(ov, g)
    assert pv["templates"]["A+B"]["max"] == 4 and pv["templates"]["B"]["slots"]["3"]["key"] == "-" and ov == before  # 계획용 사본 — 오버레이는 그대로
    OG.apply(ov, g)
    tp = ov["templates"]
    assert (tp["A+B"]["chain"], tp["A+B"]["max"]) == (["N.", "□", "o", "-"], 4) and (tp["B"]["chain"], tp["B"]["max"]) == (["□", "o", "-"], 3) and tp["B~2a"]["max"] == 3
    assert tp["A+B"]["slots"]["4"] == tp["B"]["slots"]["3"] == tp["B~2a"]["slots"]["3"] and tp["A+B"]["slots"]["4"] is not tp["B"]["slots"]["3"]  # 슬롯은 템플릿마다 사본
    assert tp["A"]["max"] == 2 and ov["grows"][0]["tid"] == "A+B" and ov["grows"][0]["n"] == 3
    OG.revert(ov, g)
    assert ov == {**before, "seq": 3, "grows": []}  # 문서를 건드리기 전의 실패 — 더한 것만 걷는다
    with pytest.raises(ValueError, match="이미 씁니다"):
        OG.prepare(None, ov, ["x"], "1.", None, "text")  # 종속 템플릿의 사슬에는 부모 템플릿의 레벨도 있다


def test_carry_after_rerun():
    """2단계를 다시 돌려 오버레이를 새로 만들 때 — 그래프가 새 레벨을 못 알아봤으면(그 레벨 줄이 없다) 슬롯을 다시 더하고, 알아봤으면(앵커 뒤에 「›키」) 자리 규칙만 옮긴다."""
    old = _ov()
    line = {"tpl": "B", "no": 3, "level": 2, "parent": None, "letter": "o", "key": "o", "role": "heading", "flow": "body"}
    old["lines"] = {"y": dict(line)}
    g = OG.prepare(None, old, ["y"], "-", 6, "keep")
    OG.apply(old, g)
    # ㉮ 못 알아봄 — 같은 앵커 · L3 없음
    new = _ov()
    assert OG.carry(old, new) == 1
    tp = new["templates"]
    assert tp["B"]["max"] == 3 and tp["B"]["slots"]["3"]["prefix"] == "      - " and tp["B"]["slots"]["3"]["pos"] == {"line2": "keep", "set": True} and tp["B"]["slots"]["3"]["rep"] is None
    assert tp["A+B"]["max"] == 4 and tp["B~2a"]["max"] == 3 and new["grows"][0]["tid"] == "B"  # 같이 늘리던 템플릿도 · 기록도 이어 간다
    assert OG.carry(new, _ov()) == 1  # 또 다시 돌려도
    # ㉯ 알아봄 — 새 그래프의 템플릿이 「□›o›-」(L3 「-」 · 자리 규칙 없음)
    new = _ov()
    b = new["templates"]["B"]
    b.update(anchor="body:□›o›-", chain=["□", "o", "-"], max=3)
    b["slots"]["3"] = {"letter": "-", "key": "-", "rep": "z", "count": 2, "prefix": "      - ", "attrs": {"paraPrIDRef": "9", "styleIDRef": "0", "charPrIDRef": "1"}, "spacer": None}
    assert OG.carry(old, new) == 0
    assert b["slots"]["3"]["pos"] == {"line2": "keep", "set": True} and b["slots"]["3"]["rep"] == "z" and b["slots"]["3"]["attrs"]["paraPrIDRef"] == "9" and not new.get("grows")
    # ㉰ 템플릿이 없어짐(앵커가 다름) — 아무것도 안 한다
    new = _ov()
    new["templates"]["B"]["anchor"] = "body:△›o"
    assert OG.carry(old, new) == 0 and new["templates"]["B"]["max"] == 2
    assert OG.carry(None, new) == 0 and OG.carry(old, None) == 0
