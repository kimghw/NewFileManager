"""개요 줄의 헤딩 고치기(spec_hwpx_웹편집 ② §8-12 — app/outline_tune.py · app/outline_tune_api.py · 2026-11-24 전의 이름 「레터 고치기」): 줄의 레터 · 레터 앞뒤 빈칸 · 앞 여백 · 2번째 줄을 고치고 범위를 고른다.
연구개발계획서 양식(2단계 LLM 끔 → 가지 템플릿 T2 「□›o›-›·」 — p970 □ › p972 o › p974 - › p975 ⋅ · 다음 묶음 p977 o › p979 - › p980 ⋅ · L3 「-」 줄 5개 · 대표 p974).
창의 자료(suggest) · 미리보기(범위 셋의 가능 여부와 수) · 이 문단만(빈칸 · 앞 여백 · 닮은 글자 — 다른 줄 그대로 / 레터 계열이 달라지면 거절 / 레터로 안 읽히는 꼴 거절) ·
서식 전체 변경(이 줄이 대표 · 다른 줄 모두 같은 서식 · 레터 계열 바꿈 = 사슬 · 슬롯 · 줄의 키 / 기호 「o」 → 「①」 이 형제 차례로(「⑮」 아님)) · 값 없이 넓히기 ·
새 템플릿으로 나누기(T2L3a — 아래 줄이 따라감 · 원래 템플릿 그대로 · 대표 줄도 · 값 없이도 · 시작 · 끝 레벨 — 다시 분석해도 그 범위) · 2번째 줄(글 시작 · 레터 · 앞 여백) ·
실행 취소 = 원본 바이트 + 오버레이 · 창의 되돌리기는 문서 차례가 그대로일 때만."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_match as OM
from app import outline_pos as OP
from app import outline_tune as OT
from app import server

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
L3 = ["p974", "p979", "p988", "p994", "p1018"]


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
    tmp = tmp_path_factory.mktemp("outline_tune")
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
        assert c.get(f"/api/docs/{d}/outline").status_code == 200
        yield c, d, s
        server.DOCS.clear()


@pytest.fixture
def doc(sess):
    """시험마다 처음 상태에서 — 끝나면 실행 취소로 원본 바이트 · 오버레이를 되돌린다."""
    c, d, s = sess
    assert sorted(OM.slot_ids(s.outline, "2", 3), key=lambda p: int(p[1:])) == L3 and s.outline["templates"]["2"]["slots"]["3"]["rep"] == "p974"
    yield c, d, s
    while s.state()["undo"]:
        assert c.post(f"/api/docs/{d}/undo").status_code == 200
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
    t = s.outline["templates"]["2"]
    assert t["chain"] == ["□", "o", "-", "·"] and "2~3a" not in s.outline["templates"] and t["slots"]["3"]["rep"] == "p974" and not t["slots"]["3"].get("repSet")


def _text(s, pid):
    return s.doc._text(s.doc._ids[pid])


def _tune(c, d, **body):
    return c.post(f"/api/docs/{d}/outline/tune", json=body)


def _look(s, pid):
    return OM.look(s.doc, s.outline, pid)


def test_suggest(doc):
    c, d, s = doc
    r = c.post(f"/api/docs/{d}/outline/tune/suggest", json={"id": "p979"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["name"], j["tpl"], j["level"], j["isRep"]) == ("T2 L3", "2", 3, False) and j["rep"]["id"] == "p974" and j["differs"] == []
    assert j["cur"]["letter"] == "-" and j["cur"]["lead"] == 4 and j["cur"]["gap"] == 1 and j["cur"]["frontMm"] == 0.0
    assert "①" in j["numbers"] and "1." in j["numbers"] and "가." in j["numbers"] and "⑴" not in j["numbers"] and "㉮" not in j["numbers"]  # 번호를 이어 매길 줄 아는 꼴만
    assert "▪" in j["symbols"] and j["rev"] == s.rev
    # 개요 줄이 아닌 문단 · 괄호 줄은 400(까닭)
    assert c.post(f"/api/docs/{d}/outline/tune/suggest", json={"id": "p1"}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/tune/suggest", json={}).status_code == 400


def test_preview_counts(doc):
    c, d, s = doc
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979"}).json()   # 값 없음 · 대표와 같은 줄 — 이 문단만 · 전체 변경은 못 하고 나누기(자리로)는 된다
    assert not j["line"]["ok"] and not j["level"]["ok"] and j["split"]["ok"] and j["split"]["conform"] is None
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", "gap": 2}).json()
    assert j["line"]["ok"] and j["changes"] and not j["kin"] and j["new"] == {"letter": "-", "lead": 4, "gap": 2}
    new = {"letter": "-", "lead": 4, "gap": 2}
    assert j["level"] == {"ok": True, "new": new, "total": 5, "change": 4, "same": 0, "own": 0, "ownLetter": 0, "skip": 0, "letters": [], "more": 0}
    sp = j["split"]
    assert {k: sp[k] for k in ("ok", "new", "name", "start", "upto", "cut", "roots", "kids", "moved", "stay", "levels")} == {
        "ok": True, "new": new, "name": "T2L3a", "start": 3, "upto": None, "cut": "here", "roots": 1, "kids": 1, "moved": 2, "stay": 0, "levels": [[3, 1], [4, 1]]}   # p980 「⋅」 이 따라간다
    assert sp["conform"]["total"] == 1   # 새 템플릿의 L3 = 이 줄뿐
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", "letter": "▪"}).json()   # 레터 계열이 달라짐 — 이 문단만은 못 한다
    assert j["kin"] and not j["line"]["ok"] and "다른 템플릿" in j["line"]["why"] and j["level"]["ok"] and j["level"]["letters"] == [["-", "▪"]] and j["split"]["ok"]
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p974", "gap": 2}).json()     # 대표 줄도 새 템플릿으로 나눈다(2026-11-24 사용자 「대표도 새 탬플릿을 할 수 있지」)
    assert j["line"]["ok"] and j["level"]["ok"] and j["split"]["ok"] and j["split"]["name"] == "T2L3a"
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", "start": 1, "upto": 3}).json()   # L1 부터 L3 까지 — 윗줄 □ 부터 · L4 줄은 남는다
    assert {k: j["split"][k] for k in ("name", "start", "upto", "moved", "stay", "levels")} == {"name": "T2L1a", "start": 1, "upto": 3, "moved": 5, "stay": 2, "levels": [[1, 1], [2, 2], [3, 2]]}
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", "cut": "all"}).json()   # 그 레벨 줄 모두
    assert (j["split"]["roots"], j["split"]["moved"]) == (5, 9)
    for body, word in (({"start": 4}, "시작 레벨"), ({"upto": 2}, "끝 레벨"), ({"cut": "x"}, "cut")):
        j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", **body}).json()
        assert not j["split"]["ok"] and word in j["split"]["why"], (body, j["split"])
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p977", "letter": "①"}).json()   # 번호형 — 범위마다 이 줄의 번호가 다르다(astra 2차)
    assert j["level"]["new"]["letter"] == "②" and j["split"]["new"]["letter"] == "①"   # 레벨 전체 = 형제 차례(둘째) · 새 템플릿 = 1부터
    assert s.state()["undo"] == 0   # 읽기만


def test_line_only(doc):
    c, d, s = doc
    before = {p: _text(s, p) for p in L3}
    r = _tune(c, d, id="p979", lead=3, gap=2, frontMm=12.0, scope="line", rev=s.rev)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tune"]["scope"] == "line" and j["tune"]["changed"] == 1 and j["tune"]["split"] is None and j["owpml"]["status"] != "fail"
    assert _text(s, "p979").startswith("   -  ") and not _text(s, "p979").startswith("    ")
    cur = OT.now(s.doc, s.outline, "p979")
    assert (cur["lead"], cur["gap"], cur["frontMm"]) == (3, 2, 12.0) and cur["line2Mm"] == cur["textMm"]   # 2번째 줄 = 글 시작
    assert all(_text(s, p) == before[p] for p in L3 if p != "p979")   # 다른 줄은 그대로
    x = s.outline["lines"]["p979"]
    assert (x["tpl"], x["level"], x["letter"], x["key"]) == ("2", 3, "-", "-") and s.outline["templates"]["2"]["slots"]["3"]["rep"] == "p974"
    assert not OM.same(_look(s, "p979"), _look(s, "p974"))
    # 값 없이 「서식 전체 변경」 — 손으로(앞 걸음에서) 달라진 줄의 서식을 레벨 전체에
    r = _tune(c, d, id="p979", scope="level")
    assert r.status_code == 200, r.text
    assert r.json()["tune"]["matched"] == 4 and all(OM.same(_look(s, p), _look(s, "p979")) for p in L3)
    sl = s.outline["templates"]["2"]["slots"]["3"]
    assert sl["rep"] == "p979" and sl["repSet"] and s.state()["undo"] == 2


def test_line_only_rejects(doc):
    c, d, s = doc
    for body, word in (({"letter": "▪"}, "다른 템플릿"), ({"letter": "①"}, "다른 템플릿"), ({"gap": 0}, "레터로 읽히지"), ({}, "바뀔 것이 없습니다"),
                       ({"lead": 99}, "레터 앞 빈칸"), ({"gap": -1}, "레터 뒤 빈칸"), ({"frontMm": 999}, "앞 여백"), ({"letter": "※"}, ""), ({"letter": "o"}, "")):
        r = _tune(c, d, id="p979", scope="line", **body)
        assert r.status_code == 400 and word in r.json()["detail"], (body, r.text)
    assert _tune(c, d, id="p979", gap=2, scope="nope").status_code == 400
    assert _tune(c, d, id="p979", gap=2, rev=s.rev + 5).status_code == 409   # 창을 연 뒤 문서가 바뀜
    assert s.state()["undo"] == 0 and _text(s, "p979").startswith("    - ")


def test_line_only_kin_glyph(doc):
    c, d, s = doc
    r = _tune(c, d, id="p977", letter="○", scope="line")   # 닮은 글자(같은 레터 계열 「o」) — 이 문단만으로 된다
    assert r.status_code == 200, r.text
    x = s.outline["lines"]["p977"]
    assert _text(s, "p977").lstrip().startswith("○") and (x["letter"], x["key"], x["level"]) == ("○", "o", 2)


def test_level_spacing(doc):
    c, d, s = doc
    r = _tune(c, d, id="p979", gap=2, frontMm=5.0, scope="level")
    assert r.status_code == 200, r.text
    t = r.json()["tune"]
    assert (t["scope"], t["matched"], t["changed"], t["left"]) == ("level", 4, 5, [])
    sl = s.outline["templates"]["2"]["slots"]["3"]
    assert sl["rep"] == "p979" and sl["repSet"] and sl["letter"] == "-" and sl["key"] == "-"
    for p in L3:
        cur = OT.now(s.doc, s.outline, p)
        assert (cur["letter"], cur["lead"], cur["gap"], cur["frontMm"]) == ("-", 4, 2, 5.0) and cur["line2Mm"] == cur["textMm"], p
        assert OM.same(_look(s, p), _look(s, "p979"))
    assert s.outline["templates"]["2"]["chain"] == ["□", "o", "-", "·"] and _text(s, "p975").startswith("     ⋅")   # 다른 레벨은 그대로


def test_level_new_letter(doc):
    c, d, s = doc
    r = _tune(c, d, id="p979", letter="▪", scope="level")
    assert r.status_code == 200, r.text
    t = s.outline["templates"]["2"]
    assert t["chain"] == ["□", "o", "▫", "·"] and (t["slots"]["3"]["letter"], t["slots"]["3"]["key"], t["slots"]["3"]["rep"]) == ("▪", "▫", "p979")
    for p in L3:
        x = s.outline["lines"][p]
        assert _text(s, p).lstrip().startswith("▪") and (x["letter"], x["key"], x["tpl"], x["level"]) == ("▪", "▫", "2", 3), p
    assert r.json()["tune"]["matched"] == 4
    # 사슬의 다른 레벨이 쓰는 레터로는 못 바꾼다
    r = _tune(c, d, id="p979", letter="o", scope="level")
    assert r.status_code == 400 and "L2" in r.json()["detail"]


def test_level_symbol_to_number(doc):
    """기호 「o」 레벨 → 「①」: 같은 윗줄 아래 형제 차례로 1부터(「o」 를 영문 15번째로 읽어 「⑮」 를 만들지 않는다 — astra)."""
    c, d, s = doc
    ov = s.outline
    ids = [p for p in OM.slot_ids(ov, "2", 2) if p in ov["lines"]]
    by_parent = {}
    for p in sorted(ids, key=lambda q: int(q[1:])):
        by_parent.setdefault(ov["lines"][p]["parent"], []).append(p)
    assert by_parent["p970"][:2] == ["p972", "p977"]
    r = _tune(c, d, id="p977", letter="①", scope="level")
    assert r.status_code == 200, r.text
    assert s.outline["templates"]["2"]["chain"][1] == "①" and "⑮" not in "".join(_text(s, p) for p in ids)
    for sib in by_parent.values():
        got = [_text(s, p).lstrip()[0] for p in sib]
        assert got == list("①②③④⑤⑥⑦⑧⑨⑩")[:len(sib)], (sib, got)
    assert s.outline["lines"]["p977"]["letter"] == "②" and s.outline["lines"]["p977"]["key"] == "①"


def test_split_new_template(doc):
    c, d, s = doc
    r = _tune(c, d, id="p979", letter="▪", gap=2, scope="split")
    assert r.status_code == 200, r.text
    sp = r.json()["tune"]["split"]
    assert (sp["id"], sp["name"], sp["moved"], sp["lines"]) == ("2~3a", "T2L3a", 2, 1)
    ov = s.outline
    C = ov["templates"]["2~3a"]
    assert C["chain"] == ["□", "o", "▫", "·"] and (C["slots"]["3"]["rep"], C["slots"]["3"]["letter"], C["slots"]["3"]["key"]) == ("p979", "▪", "▫") and C["variant"]["of"] == "2"
    assert (ov["lines"]["p979"]["tpl"], ov["lines"]["p979"]["key"], ov["lines"]["p980"]["tpl"]) == ("2~3a", "▫", "2~3a")   # 아래 줄이 따라간다
    assert ov["templates"]["2"]["chain"] == ["□", "o", "-", "·"] and ov["templates"]["2"]["slots"]["3"]["rep"] == "p974"   # 원래 템플릿은 그대로
    assert _text(s, "p979").lstrip().startswith("▪") and OT.now(s.doc, ov, "p979")["gap"] == 2 and _text(s, "p974").startswith("    - ")
    assert s.state()["undo"] == 1


def test_split_rep_and_plain(doc):
    """대표 줄도 나눈다 · 값을 안 바꿔도 나눈다(자리로 — 라벨의 「나누기」 ② §8-13 와 같은 길: 문서는 안 바뀐다)."""
    c, d, s = doc
    r = _tune(c, d, id="p974", gap=2, scope="split")   # 대표 줄 — 새 템플릿의 대표가 되고 T2 L3 의 대표는 남은 줄의 첫 것으로
    assert r.status_code == 200, r.text
    ov = s.outline
    assert ov["lines"]["p974"]["tpl"] == "2~3a" and ov["templates"]["2~3a"]["slots"]["3"]["rep"] == "p974" and ov["templates"]["2"]["slots"]["3"]["rep"] == "p979"
    assert OT.now(s.doc, ov, "p974")["gap"] == 2
    assert c.post(f"/api/docs/{d}/undo").status_code == 200
    raw = c.get(f"/api/docs/{d}/download").content
    r = _tune(c, d, id="p979", scope="split")           # 값 없이 — 오버레이만
    assert r.status_code == 200, r.text
    assert s.outline["lines"]["p979"]["tpl"] == "2~3a" and r.json()["tune"]["changed"] == 0 and c.get(f"/api/docs/{d}/download").content == raw


def test_split_levels_range(doc):
    """시작 · 끝 레벨(2026-11-24 사용자 「t1L6 부터 어디까지 알수 있고 선택할 수 있어야 함 … T1L1 하고 T1L2 를 T3L1 로」): L1 부터 L3 까지 — 윗줄 □ 부터 새 템플릿 · L4 줄은 원래 템플릿에 남는다.
    다시 분석해도(2단계 다시) 그 범위로 다시 건다."""
    c, d, s = doc
    r = _tune(c, d, id="p979", scope="split", start=1, upto=3)
    assert r.status_code == 200, r.text
    sp = r.json()["tune"]["split"]
    assert (sp["name"], sp["start"], sp["upto"], sp["moved"], sp["stay"]) == ("T2L1a", 1, 3, 5, 2)
    ov = s.outline
    C = ov["templates"]["2~1a"]
    assert C["max"] == 3 and C["chain"] == ["□", "o", "-"] and sorted(C["slots"], key=int) == ["1", "2", "3"] and C["variant"]["upto"] == 3
    mine = {p: ov["lines"][p]["tpl"] for p in ("p970", "p972", "p974", "p975", "p977", "p979", "p980")}
    assert mine == {"p970": "2~1a", "p972": "2~1a", "p974": "2~1a", "p975": "2", "p977": "2~1a", "p979": "2~1a", "p980": "2"}, mine   # L4 「⋅」 줄은 T2 그대로
    before = {p: (x["tpl"], x["level"]) for p, x in ov["lines"].items()}
    from app import outline_edit as OE
    ov2 = OE.build_overlay(heading_runs.graph(s), server._outline_probe(s), rev=s.rev)   # 2단계를 다시 돌린 것과 같은 새 오버레이 — 떼기 기록(upto)으로 다시 건다
    lost = OM.carry(ov, ov2, OM.context(s.doc, ov2), doc=s.doc)
    after = {p: (x["tpl"], x["level"]) for p, x in ov2["lines"].items()}
    assert not lost and after == before, (lost, {p: (before.get(p), after.get(p)) for p in set(before) | set(after) if before.get(p) != after.get(p)})
    assert ov2["templates"]["2~1a"]["max"] == 3 and ov2["templates"]["2~1a"]["chain"] == ["□", "o", "-"]
    # 합치면 모두 T2 로 — 합친 뒤 끝 레벨 아래 줄을 나눈 템플릿이 데려가지 않는다
    ov3 = copy.deepcopy({k: ov.get(k) for k in ("templates", "lines", "branches", "splits", "merges")})
    OM.unsplit(ov3, "2~1a")
    assert all(x["tpl"] == "2" for p, x in ov3["lines"].items() if p in mine)


def test_split_letter_from_upper_start(doc):
    """윗줄부터 나누며 이 줄의 레터를 바꾸면 — 새 템플릿 안에서 「서식 전체 변경」(이 줄이 그 레벨의 대표 · 원래 템플릿은 그대로)."""
    c, d, s = doc
    r = _tune(c, d, id="p979", letter="▪", scope="split", start=2)
    assert r.status_code == 200, r.text
    ov = s.outline
    C = ov["templates"]["2~2a"]
    assert C["chain"][2] == "▫" and C["slots"]["3"]["rep"] == "p979" and C["slots"]["2"]["rep"] == "p977" and ov["templates"]["2"]["chain"] == ["□", "o", "-", "·"]
    assert _text(s, "p979").lstrip().startswith("▪") and _text(s, "p974").startswith("    - ")


def test_window_undo_guard(doc):
    c, d, s = doc
    r = _tune(c, d, id="p979", gap=2, scope="level")
    rev, token = r.json()["rev"], r.json()["tune"]["undo"]
    assert c.post(f"/api/docs/{d}/outline/tune/undo", json={"rev": rev - 1, "token": token}).status_code == 409   # 그 뒤에 문서가 바뀐 것으로 본다 — 안 되돌린다
    assert c.post(f"/api/docs/{d}/outline/tune/undo", json={"rev": rev}).status_code == 409                       # 표 없이는 안 된다
    assert c.post(f"/api/docs/{d}/outline/tune/undo", json={"rev": rev, "token": "x" * 16}).status_code == 409    # 다른 반영의 표
    assert s.state()["undo"] == 1
    u = c.post(f"/api/docs/{d}/outline/tune/undo", json={"rev": rev, "token": token})
    assert u.status_code == 200 and "blocks" in u.json()
    assert s.state()["undo"] == 0 and c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes() and s.outline["templates"]["2"]["slots"]["3"]["rep"] == "p974"
    assert c.post(f"/api/docs/{d}/outline/tune/undo", json={"rev": s.rev, "token": token}).status_code == 409   # 되돌릴 것이 없다
    # 이 창이 아닌 편집(문단 모양)이 맨 위면 차례가 맞아도 안 되돌린다(차례 번호만으로는 어느 편집인지 모른다 — astra 2차)
    assert c.post(f"/api/docs/{d}/format/para", json={"ids": ["p979"], "changes": {"indentLeftMm": 3}}).status_code == 200
    assert c.post(f"/api/docs/{d}/outline/tune/undo", json={"rev": s.rev, "token": token}).status_code == 409 and s.state()["undo"] == 1


def test_narrow_only_touches_changed_chars():
    """조각에서 실제로 달라지는 글자만 — 앞뒤의 같은 글자(그 런 · 글자 모양)는 안 건드린다(astra 2차: 「1.」→「2.」 가 마침표의 모양까지 바꾸던 것)."""
    assert OT._narrow(4, "1.", "2.") == (4, 5, "2") and OT._narrow(0, "  ", "   ") == (2, 2, " ") and OT._narrow(0, "    ", "  ") == (2, 4, "")
    assert OT._narrow(3, "-", "▪") == (3, 4, "▪") and OT._narrow(3, "(1)", "(가)") == (4, 5, "가") and OT._narrow(0, "", "  ") == (0, 0, "  ")


def test_outer_field_blocks_edit(doc):
    """앞 문단에서 열려 뒤 문단에서 닫히는 필드 안의 줄 — 제 표지가 없어도 못 고친다(미리보기 · 반영이 같은 까닭으로 · 문서 그대로: astra 2차 P1)."""
    c, d, s = doc
    p = s.doc._ids["p979"]
    assert not s.doc.own_marks(p)
    guard = OT.Guard(s.doc)
    assert guard.enclosed(p) is None
    guard._seen[p.getparent()] = {p: "field"}   # 그 그릇을 훑은 결과가 「필드 안」 인 것처럼(문서에 표지를 심지 않는다 — 원본 바이트 그대로)
    with pytest.raises(ValueError) as e:
        OT.pieces_of(s.doc, "p979", ("    ", "-", " "), ("    ", "-", "  "), guard)
    assert "필드" in str(e.value) and _text(s, "p979").startswith("    - ")
    # 그릇을 실제로 훑는 길 — 필드 시작만 있는 문단 뒤의 문단은 범위 안, 끝 표지 뒤는 밖
    from lxml import etree
    from app.hwpx_struct import FIELD_BEGIN, FIELD_END, RUN
    ns = FIELD_BEGIN.split("}")[0] + "}"
    box = etree.fromstring(f'<x xmlns:hp="{ns[1:-1]}"><hp:p><hp:run><hp:ctrl><hp:fieldBegin id="7" type="HYPERLINK"/></hp:ctrl><hp:t>가</hp:t></hp:run></hp:p>'
                           f'<hp:p><hp:run><hp:t>- 나</hp:t></hp:run></hp:p><hp:p><hp:run><hp:t>다</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="7"/></hp:ctrl></hp:run></hp:p>'
                           f'<hp:p><hp:run><hp:t>라</hp:t></hp:run></hp:p></x>')
    a, b, cc, dd = list(box)
    assert RUN == ns + "run" and FIELD_END == ns + "fieldEnd"
    got = OT.Guard(s.doc)._scan(box, a.tag)
    assert got.get(a) is None and got.get(b) == "field" and got.get(cc) == "field" and got.get(dd) is None


def test_level_rejects_when_a_line_cannot_change(doc, monkeypatch):
    """레터 계열을 바꾸는 「서식 전체 변경」 — 못 바꾸는 줄이 하나라도 있으면 레벨 전체를 안 바꾼다(「-」 · 「②」 · 「③」 이 한 레벨에 섞이지 않게: astra 2차 P1)."""
    c, d, s = doc
    real = OT.pieces_of

    def fake(doc_, pid, old, new, guard=None):
        if pid == "p994":
            raise OT.MarkBlock("field", ["필드"])
        return real(doc_, pid, old, new, guard)
    monkeypatch.setattr(OT, "pieces_of", fake)
    j = c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", "letter": "▪"}).json()
    assert not j["level"]["ok"] and "1개" in j["level"]["why"] and j["split"]["ok"]   # 새 템플릿으로는 된다(그 줄만)
    r = _tune(c, d, id="p979", letter="▪", scope="level")
    assert r.status_code == 400 and "바꿀 수 없는 줄" in r.json()["detail"]
    assert s.state()["undo"] == 0 and all(_text(s, p).startswith("    - ") for p in L3) and s.outline["templates"]["2"]["chain"][2] == "-"
    # 빈칸 · 여백만 바꾸는 전체 변경은 그 줄 때문에 막히지 않는다(레터는 그대로 — 맞추기가 표지를 지킨다)
    assert c.post(f"/api/docs/{d}/outline/tune/preview", json={"id": "p979", "gap": 2}).json()["level"]["ok"]


def test_front_with_positive_first_line(doc):
    """양수 첫 줄 들여쓰기가 있는 줄 — 고른 앞 여백이 실제 첫 줄 자리가 된다(왼쪽 여백부터 옮기면 들여쓰기가 남아 어긋난다: astra 2차)."""
    c, d, s = doc
    assert c.post(f"/api/docs/{d}/format/para", json={"ids": ["p979"], "changes": {"indentLeftMm": 2, "firstLineMm": 8}}).status_code == 200
    assert OT.now(s.doc, s.outline, "p979")["frontMm"] == 10.0
    r = _tune(c, d, id="p979", frontMm=3.0, scope="line")
    assert r.status_code == 200, r.text
    cur = OT.now(s.doc, s.outline, "p979")
    assert cur["frontMm"] == 3.0 and cur["line2Mm"] == cur["textMm"]


def test_heirs_chain(doc):
    """레벨을 물려 쓰는 템플릿을 끝까지 — 더 깊은 데서 뗀 서식 종속 템플릿의 사슬도 같이 바뀐다."""
    c, d, s = doc
    assert _tune(c, d, id="p980", lead=6, scope="split").status_code == 200   # L4 에서 뗀 T2L4a — L1~L3 은 T2 의 레벨
    cid = next(k for k, t in s.outline["templates"].items() if (t.get("variant") or {}).get("of") == "2")
    assert OT.heirs(s.outline, "2", 3) == [cid] and OT.heirs(s.outline, "2", 4) == []
    assert _tune(c, d, id="p974", letter="▪", scope="level").status_code == 200
    assert s.outline["templates"]["2"]["chain"][2] == "▫" and s.outline["templates"][cid]["chain"][2] == "▫"


def test_line2_modes(doc):
    """2번째 줄 — 글 시작 · 레터 · 앞 여백(2026-11-24 사용자 「2번째 줄을 레터 앞에 맞출건지 레터 뒤의 첫번째 문자/글자에 맞출건지. 또는 여백으로 맞출건지」).
    이 문단만 = 그 줄에만 건 규칙(글을 고친 뒤 저절로 맞춰도 남는다) · 서식 전체 변경 = 그 레벨의 규칙(모든 줄)."""
    c, d, s = doc
    j = c.post(f"/api/docs/{d}/outline/tune/suggest", json={"id": "p979"}).json()
    assert j["cur"]["line2"] == "front" and j["rule"]["line2"] == "text" and j["widths"]["lead"] == [j["widths"]["leadAdd"]] * 4 and j["cur"]["leadMm"] > 0
    r = _tune(c, d, id="p979", line2="letter", scope="line")
    assert r.status_code == 200, r.text
    cur = OT.now(s.doc, s.outline, "p979")
    assert abs(cur["line2Mm"] - cur["letterMm"]) < 0.06 and cur["line2"] == "letter" and s.outline["lines"]["p979"]["pos"] == {"line2": "letter"}
    assert _tune(c, d, id="p979", line2="letter", scope="line").status_code == 400   # 이미 그 자리
    assert OP.align(s.doc, s.outline, "p979") is None and OT.now(s.doc, s.outline, "p979")["line2"] == "letter"   # 저절로 맞추기는 그 줄에만 건 규칙을 지킨다
    r = _tune(c, d, id="p979", lead=2, scope="line")   # 다른 값만 고쳐도 그 줄의 2번째 줄 규칙은 그대로(새 레터 자리로)
    assert r.status_code == 200, r.text
    cur = OT.now(s.doc, s.outline, "p979")
    assert cur["line2"] == "letter" and abs(cur["line2Mm"] - cur["letterMm"]) < 0.06
    r = _tune(c, d, id="p974", line2="text", scope="level")
    assert r.status_code == 200, r.text
    assert (s.outline["templates"]["2"]["slots"]["3"].get("pos") or {"line2": "text"})["line2"] == "text" and "pos" not in s.outline["lines"]["p979"]   # 그 레벨의 규칙(기본 글 시작) · 줄에만 건 규칙은 지워짐
    for p in L3:
        cur = OT.now(s.doc, s.outline, p)
        assert abs(cur["line2Mm"] - cur["textMm"]) < 0.06, (p, cur)
    r = _tune(c, d, id="p974", line2="front", scope="level")   # 앞 여백 — 내어쓰기 없음
    assert r.status_code == 200, r.text
    assert all(OT.now(s.doc, s.outline, p)["line2"] == "front" for p in L3)
    assert _tune(c, d, id="p974", line2="nope", scope="level").status_code == 400


def test_resize_keeps_mixed_blanks():
    assert OT._resize("  ", 3) == "   " and OT._resize("　 ", 1) == "　" and OT._resize("　 ", 3) == "　  "   # 늘리고 줄이는 만큼만 — 있던 빈칸은 그대로
    assert OT._resize("", 2, nb=True) == "  " and OT._resize("  ", 3) == "   "
    with pytest.raises(ValueError):
        OT._resize(" \t", 1)
