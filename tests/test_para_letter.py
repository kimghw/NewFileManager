"""레터 넣기(spec_hwpx_웹편집 ② §8-9 — app/para_letter.py · app/para_letter_api.py): 도구 줄 「문단 수정」 묶음의 단추로 문단을 헤딩(레터 줄)으로.
순수 함수 — 후보(모두 내장 레터 규칙이 읽는 글자) · 레터 검사 · 번호 열(with_last) · 문단 읽기 · 레터만 넣기(이어서 · 처음부터 · 더 얕은 줄에서 새 묶음 · 여러 문단 · 뒤 줄 번호 밀기 ·
있는 레터 바꾸기 · 번호가 여럿인 꼴 · 번호 열의 끝 · 레터 뒤 빈칸은 앞 줄 것) · 레터 빼기.
연구개발계획서 양식(2단계 LLM 끔 — 주 사슬 T1 「1.›1-1.›(1)›o›-」 · 가지 T2 「□›o›-›·」: p966 1. › p968 1-1. › p969 빈 문단 › p970 □ › p972 o › p974 - › p975 ⋅ › p976 빈 문단 › p977 o … › p982 1-2. › p984 □):
메뉴(개요 레벨의 차례 · 넣을 레터) · 레터만(오버레이 줄이 아님 · 같은 꼴이면 줄로 남음 · 다른 꼴이면 줄에서 빠짐) · 개요 레벨로(새 줄 · 번호 다시 매김 · 있던 줄의 레벨 · 거절) · 레터 빼기 ·
실행 취소 = 원본 바이트 + 오버레이 복원 · 2단계가 없는 문서 · docx(레터만 · 빼기)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import para_letter as PL
from app import server
from app.hwpx_doc import P
from tests.test_server import _paras

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
DOCX = ROOT / "samples" / "기술수요조사서.docx"


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
    tmp = tmp_path_factory.mktemp("para_letter")  # 모듈 픽스처는 conftest 의 시험별 임시 폴더보다 먼저 돈다 — 사용자 작업 폴더에 작업이 쌓이지 않게(test_outline_grow 와 같다)
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
    ln = s.outline["lines"]
    assert (ln["p970"]["tpl"], ln["p970"]["level"], ln["p970"]["parent"]) == ("2", 1, "p968") and ln["p982"]["letter"] == "1-2." and "p969" not in ln  # 오버레이도 그 편집 앞으로


def _text(s, pid):
    return s.doc._text(s.doc._ids[pid])


def _line(s, pid):
    x = s.outline["lines"].get(pid)
    return (x["tpl"], x["level"], x["letter"], x["parent"]) if x else None


def _cell_para(s):
    """표 칸 안의 글 문단 하나(본문 문단과 그릇이 다르다)."""
    secs = set(s.doc._sections)
    return next(i for i, e in s.doc._ids.items() if e.tag == P and e.getparent() not in secs and s.doc._attached(e) and s.doc._text(e).strip())


def _seq(*texts, obj=()):
    return [{"id": f"p{i}", "text": t, "blank": not t.strip() and i not in obj, "object": i in obj} for i, t in enumerate(texts)]


def _acts(plan):
    return [(a["id"], a["old_len"], a["prefix"]) for a in plan["actions"]]


# ---------------------------------------------------------------- 후보 · 레터 검사 · 번호 열
def test_catalog_is_all_heading_letters():
    """후보는 모두 헤딩 추출의 내장 규칙이 레터로 읽는 글자 — 번호 줄은 번호형(번호 열을 안다), 기호 줄은 아니다. 사용자가 든 꼴(둥근 숫자 · 숫자. · 숫자.숫자. · 숫자))이 들어 있다."""
    for lt in PL.NUMBERS:
        c = PL.check(lt)
        assert c["letter"] == lt and PL.numbered(c) and PL._last(c) == 1, lt  # 후보는 그 꼴의 첫 번호
        assert PL.with_last(c["family"], lt, 2) not in (None, lt), lt       # 다음 번호를 매길 수 있다
    for lt in PL.SYMBOLS:
        c = PL.check(lt)
        assert c["letter"] == lt and not PL.numbered(c), lt
    assert {"①", "1.", "1.1.", "1)", "(1)"} <= set(PL.NUMBERS)
    assert len(set(PL.NUMBERS)) == len(PL.NUMBERS) and len(set(PL.SYMBOLS)) == len(PL.SYMBOLS)


def test_check_rejects_non_letters():
    for bad in ("※", "*", "→", "", " ", "가나다라마바사아자", "[기관]", "a b", "1", "가", None, 3):  # 안내 · 각주 · 화살표 · 괄호 라벨 · 빈칸 · 너무 긴 글 · 맨 숫자·글자(구두점 없음)
        with pytest.raises(ValueError):
            PL.check(bad)
    assert PL.check(" ③ ")["letter"] == "③" and PL.check("(12)")["ord"] == [12] and PL.check("[2]")["family"] == "bracket-num"


def test_with_last():
    want = [("circled", "①", 3, "③"), ("circled", "⑳", 21, "㉑"), ("circled", "①", 51, None), ("decimal", "2.3.", 4, "2.4."), ("hyphen", "1-1.", 2, "1-2."), ("num-paren", "1)", 10, "10)"),
            ("paren-num", "(1)", 2, "(2)"), ("decimal", "1.", 100, None), ("hangul-dot", "가.", 3, "다."), ("hangul-paren", "가)", 14, "하)"), ("paren-hangul", "(가)", 15, None),
            ("alpha-lower", "a)", 3, "c)"), ("paren-alpha", "(A)", 2, "(B)"), ("alpha-upper", "A.", 27, None), ("roman-upper", "Ⅰ.", 3, "Ⅲ."), ("roman-upper", "Ⅰ.", 13, None),
            ("roman-upper", "I.", 4, "IV."), ("roman-lower", "i)", 9, "ix)"), ("enclosed", "⑴", 3, "⑶"), ("enclosed", "㉮", 3, "㉰"), ("enclosed", "❶", 3, "❸"), ("enclosed", "❶", 11, None),
            ("square", "□", 2, None), ("decimal", "1.", 0, None)]
    assert [PL.with_last(f, lt, n) for f, lt, n, _ in want] == [w for *_, w in want]
    for f, lt, n, w in want:  # 매긴 번호는 다시 읽어도 같은 꼴 · 그 번호다
        if w:
            c = PL.check(w)
            assert c["family"] == f and PL._last(c) == n, (w, c)


def test_read():
    r = PL.read("  □ 제목")
    assert (r["lead"], r["letter"], r["gap"], r["family"]) == ("  ", "□", " ", "square")
    assert PL.read(" 1-2. 배경")["ord"] == [1, 2] and PL.read("③")["letter"] == "③" and PL.read("o")["letter"] == "o"
    for plain in ("본문 글", "", "   ", "[기관명] 글", "※ 안내", "1.5", "2026. 11. 17", "-10도", "o리"):  # 본문 · 빈 문단 · 구분 라벨 · 안내 · 값 · 레터처럼 보이는 글
        assert PL.read(plain)["letter"] == "", plain
    assert PL.read("  본문")["lead"] == "  "
    k = PL.read("  ▣ 글", "▣")  # 내장 규칙은 못 읽지만 오버레이가 아는 레터(배운 규칙의 줄) — 바꿀 수 있다
    assert (k["lead"], k["letter"], k["gap"]) == ("  ", "▣", " ")


# ---------------------------------------------------------------- 레터만 넣기(순수)
def test_plain_continue_and_restart():
    seq = _seq("1. 장", "본문", "① 가", "② 나", "글")
    p = PL.plan_plain(seq, [4], "①")
    assert _acts(p) == [("p4", 0, "③ ")] and p["put"] == ["③"] and p["from"] == "②" and p["focus"] == {"id": "p4", "offset": 2} and p["follow"] == 0
    p = PL.plan_plain(seq, [4], "①", restart=True)
    assert _acts(p) == [("p4", 0, "① ")] and p["from"] is None
    assert PL.plan_plain(seq, [4], "③", restart=True)["put"] == ["③"]  # 직접 입력 = 적은 그대로
    assert PL.plan_plain(seq, [1], "1.")["put"] == ["2."]  # 「1.」 뒤


def test_plain_scope_by_rank():
    """거슬러 올라가다 더 얕은 서열의 레터 줄을 만나면 새 묶음(첫 번호) · 더 깊거나 서열을 모르는 줄 · 본문은 건너뛴다."""
    assert PL.plan_plain(_seq("① 가", "② 나", "1. 새 장", "글"), [3], "①")["put"] == ["①"]
    assert PL.plan_plain(_seq("① 가", "- 딸림", "· 더 딸림", "본문", "글"), [4], "①")["put"] == ["②"]
    assert PL.plan_plain(_seq("① 가", "□ 얕지 않음(서열 10)", "글"), [2], "①")["put"] == ["②"]
    assert PL.plan_plain(_seq("(1) 가", "1) 같은 서열의 다른 꼴", "글"), [2], "(1)")["put"] == ["(2)"]
    assert PL.plan_plain(_seq("1-1. 가", "1. 얕다", "글"), [2], "1-1.")["put"] == ["1-1."]  # 「1.」 은 「1-1.」 보다 얕다 — 그 아래 첫 번호


def test_plain_many_paras_skips_blank_and_object():
    seq = _seq("글1", "", "글2", "", "글3", obj=(3,))
    p = PL.plan_plain(seq, [0, 1, 2, 3, 4], "1)")
    assert _acts(p) == [("p0", 0, "1) "), ("p2", 0, "2) "), ("p4", 0, "3) ")] and p["put"] == ["1)", "2)", "3)"]
    assert _acts(PL.plan_plain(seq, [1], "□")) == [("p1", 0, "□ ")]  # 하나만 고르면 빈 문단에도(레터만 있는 줄)
    assert _acts(PL.plan_plain(seq, [0, 2], "-")) == [("p0", 0, "- "), ("p2", 0, "- ")]  # 기호는 모두 같은 레터
    for idxs, word in (([3], "표·그림만"), ([1, 3], "글 문단이 없습니다")):
        with pytest.raises(ValueError, match=word):
            PL.plan_plain(seq, idxs, "□")


def test_plain_follow_renumbers_the_run_after():
    """가운데에 넣으면 뒤에 바로 이어지던 같은 꼴 줄의 번호를 민다 — 다른 번호로 시작하는 묶음 · 더 얕은 줄 뒤는 안 건드린다."""
    seq = _seq("① 가", "글", "② 나", "- 딸림", "③ 다", "1. 장", "① 다른 묶음")
    p = PL.plan_plain(seq, [1], "①")
    assert _acts(p) == [("p1", 0, "② "), ("p2", 1, "③"), ("p4", 1, "④")] and p["follow"] == 2 and [a.get("follow") for a in p["actions"]] == [None, True, True]
    p = PL.plan_plain(_seq("글", "① 가", "② 나", "⑤ 이어지지 않음"), [0], "①")  # 앞 줄이 없다 — 첫 번호, 뒤의 ① ② 가 밀린다(⑤ 는 다른 묶음)
    assert _acts(p) == [("p0", 0, "① "), ("p1", 1, "②"), ("p2", 1, "③")]
    p = PL.plan_plain(_seq("① 가", "② 나", "③ 다"), [1], "①", restart=True)  # 있던 「②」 를 처음부터 — 뒤 「③」 은 「②」
    assert _acts(p) == [("p1", 2, "① "), ("p2", 1, "②")]
    assert PL.plan_plain(_seq("① 가", "② 나", "③ 다"), [1], "①")["actions"] == []  # 이미 그 번호 — 바뀔 것 없음
    assert _acts(PL.plan_plain(_seq("2.3. 가", "글", "2.4. 나"), [1], "1.1.")) == [("p1", 0, "2.4. "), ("p2", 4, "2.5.")]  # 앞 번호는 제 것 그대로


def test_plain_replaces_existing_letter_and_keeps_blanks():
    p = PL.plan_plain(_seq("  o 글"), [0], "□")
    assert _acts(p) == [("p0", 4, "  □ ")] and p["focus"]["offset"] == 4  # 레터 앞 빈칸 · 레터 뒤 빈칸은 그대로
    assert _acts(PL.plan_plain(_seq("     ⋅글"), [0], "-")) == [("p0", 6, "     - ")]  # 레터 뒤 빈칸이 없던 줄은 한 칸
    assert _acts(PL.plan_plain(_seq("□ 가", "글"), [1], "□")) == [("p1", 0, "□ ")]  # 레터 뒤 빈칸은 앞의 같은 꼴 줄 것(묶음 빈칸)
    assert PL.plan_plain(_seq("□ 글"), [0], "□")["actions"] == []
    assert _acts(PL.plan_plain(_seq("▣ 글"), [0], "□", known={"p0": "▣"})) == [("p0", 2, "□ ")]  # 오버레이가 아는 레터
    assert _acts(PL.plan_plain(_seq("[기관명] 글"), [0], "□")) == [("p0", 0, "□ ")]  # 구분 라벨은 레터가 아니다 — 그 앞에


def test_plain_multi_number_and_end_of_sequence():
    assert PL.plan_plain(_seq("3. 장", "글"), [1], "1.1.")["put"] == ["3.1."]  # 윗 줄의 번호를 앞 번호로
    assert PL.plan_plain(_seq("2. 장", "글"), [1], "1-1.")["put"] == ["2-1."]
    assert PL.plan_plain(_seq("2.3. 가", "글"), [1], "1.1.", restart=True)["put"] == ["2.1."]
    assert PL.plan_plain(_seq("글"), [0], "1.1.")["put"] == ["1.1."]
    assert PL.plan_plain(_seq("⑳ 가", "글"), [1], "①")["put"] == ["㉑"]
    with pytest.raises(ValueError, match="번호 열의 끝"):
        PL.plan_plain(_seq("하. 가", "글"), [1], "가.")
    with pytest.raises(ValueError, match="번호 열의 끝"):
        PL.plan_plain(_seq(*["글"] * 15), list(range(15)), "가)")
    with pytest.raises(ValueError, match="헤딩 레터로 읽히지 않습니다"):
        PL.plan_plain(_seq("글"), [0], "※")


def test_remove():
    p = PL.plan_remove(_seq("① 가", "  ② 나", "③ 다", "④ 라"), [1])
    assert _acts(p) == [("p1", 4, "  "), ("p2", 1, "②"), ("p3", 1, "③")] and p["put"] == ["②"] and p["follow"] == 2 and p["focus"] == {"id": "p1", "offset": 2}
    p = PL.plan_remove(_seq("① 가", "② 나", "③ 다", "④ 라"), [1, 2])  # 둘을 빼면 뒤는 「②」 부터
    assert _acts(p) == [("p1", 2, ""), ("p2", 2, ""), ("p3", 1, "②")]
    assert _acts(PL.plan_remove(_seq("□ 가", "본문", "- 나"), [0, 1, 2])) == [("p0", 2, ""), ("p2", 2, "")]  # 레터 없는 문단은 건너뜀
    with pytest.raises(ValueError, match="뺄 레터가 없습니다"):
        PL.plan_remove(_seq("본문", "[기관명] 글"), [0, 1])


# ---------------------------------------------------------------- 메뉴(연구개발계획서)
def test_suggest(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter/suggest", json={"ids": ["p969"]})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["count"] == 1 and o["cur"] == {"letter": ""} and o["format"] == "hwpx" and o["max"] == PL.LETTER_MAX
    lv = [(x["no"], x["level"], x["letter"]) for x in o["levels"]]
    assert lv[:9] == [(1, 1, "1."), (1, 2, "1-1."), (1, 3, "(1)"), (1, 4, "o"), (1, 5, "-"), (2, 1, "□"), (2, 2, "o"), (2, 3, "-"), (2, 4, "⋅")]  # 윗줄의 템플릿(T1) → 바로 뒤 줄의 템플릿(T2) → 매달리는 템플릿
    assert len(lv) <= PL.LEVELS_MAX and not any(x["cur"] for x in o["levels"]) and [x["numbered"] for x in o["levels"]][:6] == [True, True, True, False, False, False]
    assert not any(x["letter"].startswith("[") for x in o["levels"])  # 괄호 줄 레벨(구분 라벨 · 괄호 소제목)은 없다
    nums = {x["letter"]: x for x in o["numbers"]}
    assert [x["letter"] for x in o["numbers"]] == list(PL.NUMBERS) and [x["letter"] for x in o["symbols"]] == list(PL.SYMBOLS)
    assert nums["1."] == {"letter": "1.", "next": "2.", "from": "1.", "first": "1."} and nums["1-1."]["next"] == "1-2." and nums["1-1."]["from"] == "1-1."
    assert nums["①"] == {"letter": "①", "next": "①", "from": None, "first": "①"}  # 「1-1.」 아래의 새 묶음
    assert s.state()["undo"] == 0  # 메뉴 받기는 아무것도 안 바꾼다
    # 개요 줄에서 — 지금 자리 · 그 레벨이 「지금」
    o = c.post(f"/api/docs/{d}/letter/suggest", json={"ids": ["p975"]}).json()
    assert o["cur"] == {"letter": "⋅", "tpl": "2", "no": 2, "level": 4} and [(x["no"], x["level"]) for x in o["levels"] if x["cur"]] == [(2, 4)]
    assert [(x["no"], x["level"]) for x in o["levels"]][:9] == [(1, k) for k in range(1, 6)] + [(2, k) for k in range(1, 5)]
    # 여러 문단 — 빈 문단은 세지 않는다
    assert c.post(f"/api/docs/{d}/letter/suggest", json={"ids": ["p972", "p973", "p974", "p975"]}).json()["count"] == 3
    for ids, code in (([], 400), (["nope"], 404), (["p972", _cell_para(s)], 400)):  # id 없음 · 없는 문단 · 그릇이 섞임(본문 + 표 칸)
        assert c.post(f"/api/docs/{d}/letter/suggest", json={"ids": ids}).status_code == code, ids


# ---------------------------------------------------------------- 레터만(연구개발계획서)
def test_plain_on_blank_para(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p969"], "letter": "①"})
    assert r.status_code == 200, r.text
    o = r.json()
    assert _text(s, "p969") == "① " and o["letter"] == {"mode": "plain", "put": ["①"], "from": None, "follow": 0, "ids": ["p969"]} and o["focus"] == {"id": "p969", "offset": 2}
    assert _line(s, "p969") is None and "p969" in o["edited"] and o["undo"] == 1  # 레터만 — 개요 줄 표시는 헤딩 추출을 다시 돌려야 붙는다
    assert [b["id"] for b in o["tops"]["blocks"]] == ["p969"]
    # 그 뒤 문단에 이어서 — 「②」
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p971"], "letter": "①"})
    assert r.status_code == 200 and _text(s, "p971") == "② " and r.json()["letter"]["from"] == "①"
    assert [b["id"] for b in r.json()["tops"]["blocks"]] == ["p971"]
    _undo_all(c, d, s)


def test_plain_many_and_contiguous_tops(sess):
    """여러 문단 — ① ② ③ 차례로. 응답의 바뀐 블록은 **이어진 구간 전체**(사이의 안 바뀐 빈 문단 포함 — 화면이 그 토막만 바꾼다)."""
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p972", "p973", "p974", "p975"], "letter": "①"})
    assert r.status_code == 200, r.text
    o = r.json()
    assert [_text(s, p) for p in ("p972", "p973", "p974", "p975")] == ["  ① ", "", "    ② ", "     ③ "] and o["letter"]["put"] == ["①", "②", "③"] and o["undo"] == 1
    assert [b["id"] for b in o["tops"]["blocks"]] == ["p972", "p973", "p974", "p975"]
    assert sorted(o["outline"]["removed"]) == ["p972", "p974", "p975"] and all(_line(s, p) is None for p in ("p972", "p974", "p975"))  # 다른 꼴이 된 줄은 개요 줄에서 빠진다
    _undo_all(c, d, s)


def test_plain_on_outline_line(sess):
    c, d, s = sess
    # 같은 꼴의 번호 — 개요 줄로 남는다(레터만 고침)
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p982"], "letter": "1-1."})
    assert r.status_code == 400 and "바뀔 것이 없습니다" in r.json()["detail"] and "1-2." in r.json()["detail"]  # 앞 줄 「1-1.」 에 이으면 지금 그대로
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p982"], "letter": "1-1.", "restart": True})
    assert r.status_code == 200, r.text
    assert _text(s, "p982").startswith(" 1-1. 연구개발과제의") and _line(s, "p982") == ("1", 2, "1-1.", "p966") and r.json()["outline"]["lines"]["p982"]["letter"] == "1-1."
    assert r.json()["outline"]["removed"] == []
    # 다른 꼴 — 개요 줄에서 빠지고 그 아래 줄은 윗줄로
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p970"], "letter": "■"})
    assert r.status_code == 200 and _text(s, "p970").startswith("■ 연구개발기술") and r.json()["outline"]["removed"] == ["p970"]
    assert _line(s, "p970") is None and _line(s, "p972")[3] == "p968"
    _undo_all(c, d, s)


def test_plain_rejects(sess):
    c, d, s = sess
    for body, code, word in (({"ids": ["p972"], "letter": "o"}, 400, "바뀔 것이 없습니다"), ({"ids": ["p972"], "letter": "※"}, 400, "헤딩 레터로 읽히지 않습니다"),
                             ({"ids": ["p972"], "letter": "가나다라마바사아자"}, 400, "1~8글자"), ({"ids": ["p972"]}, 400, "letter"), ({"ids": [], "letter": "①"}, 400, "id"),
                             ({"ids": ["p972", _cell_para(s)], "letter": "①"}, 400, "같은 구역·칸")):
        r = c.post(f"/api/docs/{d}/letter", json=body)
        assert r.status_code == code and word in r.json()["detail"], (body, r.text)
    assert s.state()["undo"] == 0 and c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


# ---------------------------------------------------------------- 개요 레벨로
def test_level_adopts_new_line(sess):
    """개요 줄이 아니던 빈 문단 → T2 L1 「□」 줄: 접두 · 그 레벨의 문단 모양 · 윗줄 = 「1-1.」 · 응답의 개요 줄."""
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p969"], "level": {"tpl": "2", "level": 1}})
    assert r.status_code == 200, r.text
    o = r.json()
    assert _text(s, "p969") == "□ " and _line(s, "p969") == ("2", 1, "□", "p968") and s.doc._ids["p969"].get("paraPrIDRef") != PLAN  # 줄이 됐다
    ref, got = s.doc._ids["p970"], s.doc._ids["p969"]
    fm = lambda p: {k: v for k, v in s.doc._para_summary(s.doc._defs["paraPr"][p.get("paraPrIDRef")]).items() if k in ("align", "lineSpacingPct", "spaceBeforePt")}  # noqa: E731
    assert got.get("styleIDRef") == ref.get("styleIDRef") and fm(got) == fm(ref) and s.doc._char_id(got) == s.doc._char_id(ref)  # 그 레벨(대표 「□」 줄)의 문단·글자 모양
    assert o["letter"] == {"mode": "level", "tpl": "2", "no": 2, "level": 1, "put": ["□"], "from": None, "follow": 0, "ids": ["p969"]}
    assert o["outline"]["lines"]["p969"] == {"no": 2, "level": 1, "tpl": "2", "letter": "□", "role": "heading", "key": "□"} and o["focus"] == {"id": "p969", "offset": 2}
    assert _line(s, "p970") == ("2", 1, "□", "p968") and _line(s, "p972") == ("2", 2, "o", "p970")  # 뒤 줄은 그대로
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p969"], "level": {"tpl": "2", "level": 1}})
    assert r.status_code == 400 and "이미 T2 L1" in r.json()["detail"]
    _undo_all(c, d, s)


def test_level_numbered_renumbers_siblings(sess):
    """번호형 레벨(T1 L2 「N-N.」) — 윗줄 「1.」 아래 차례로: 끼워 넣은 줄이 「1-2.」, 뒤 「1-2.」 는 「1-3.」(바뀐 다른 줄 1)."""
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p976"], "level": {"tpl": "1", "level": 2}})
    assert r.status_code == 200, r.text
    o = r.json()
    assert _text(s, "p976") == " 1-2. " and _line(s, "p976") == ("1", 2, "1-2.", "p966") and _text(s, "p982").startswith(" 1-3. 연구개발과제의") and _line(s, "p982")[2] == "1-3."
    assert o["letter"]["put"] == ["1-2."] and o["letter"]["follow"] == 1 and set(o["outline"]["lines"]) == {"p976", "p982"}
    assert _line(s, "p977") == ("2", 2, "o", "p970")  # 새 줄의 부분 트리 밖 — 그대로
    _undo_all(c, d, s)
    # 번호형 L3 「(N)」 — 그 자리의 윗줄 「1-1.」 아래 첫 번호
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p976"], "level": {"tpl": "1", "level": 3}})
    assert r.status_code == 200 and _text(s, "p976").strip() == "(1)" and _line(s, "p976") == ("1", 3, "(1)", "p968")
    _undo_all(c, d, s)


def test_level_moves_existing_line(sess):
    """있던 개요 줄을 다른 레벨로(두 단계 위 — Alt+↑ 두 번과 같은 자리) · 다른 템플릿의 레벨로."""
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p975"], "level": {"tpl": "2", "level": 2}})
    assert r.status_code == 200, r.text
    assert _text(s, "p975") == "  o " and _line(s, "p975") == ("2", 2, "o", "p970") and r.json()["outline"]["focuses"][0]["shift"] == -2
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p974", "p975"], "level": {"tpl": "1", "level": 4}})  # 여러 줄 · 다른 템플릿(T1 L4 「o」)
    assert r.status_code == 200, r.text
    assert [_line(s, p)[:2] for p in ("p974", "p975")] == [("1", 4), ("1", 4)] and r.json()["letter"]["ids"] == ["p974", "p975"]
    _undo_all(c, d, s)


def test_level_rejects(sess):
    c, d, s = sess
    for body, code, word in (({"ids": ["p972"], "level": {"tpl": "9", "level": 1}}, 400, "바꿀 수 없습니다"),   # 구분 라벨 레벨
                             ({"ids": ["p972"], "level": {"tpl": "2", "level": 9}}, 400, "L9 이 없습니다"),
                             ({"ids": ["p972"], "level": {"tpl": "99", "level": 1}}, 400, "그 템플릿이 없습니다"),
                             ({"ids": ["p972"], "level": {"tpl": "2"}}, 400, "level 은"),
                             ({"ids": ["p972"], "level": {"tpl": "2", "level": "1"}}, 400, "level 은"),
                             ({"ids": ["p910"], "level": {"tpl": "2", "level": 3}}, 400, "윗 레벨 줄이 없습니다"),   # 개요 줄보다 앞 — 매달릴 줄이 없다
                             ({"ids": ["p1725"], "level": {"tpl": "2", "level": 1}}, 400, "구분 라벨")):          # 구분 라벨 줄은 다른 레벨로 안 바꾼다
        r = c.post(f"/api/docs/{d}/letter", json=body)
        assert r.status_code == code and word in r.json()["detail"], (body, r.text)
    assert s.state()["undo"] == 0 and c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


# ---------------------------------------------------------------- 레터 빼기
def test_remove_on_outline_line(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p982"], "remove": True})
    assert r.status_code == 200, r.text
    o = r.json()
    assert _text(s, "p982") == " 연구개발과제의 배경 및 필요성" and o["letter"]["mode"] == "remove" and o["letter"]["put"] == ["1-2."] and o["focus"] == {"id": "p982", "offset": 1}
    assert o["outline"]["removed"] == ["p982"] and _line(s, "p982") is None and _line(s, "p984")[3] == "p966"  # 그 아래 줄은 윗줄로
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p982"], "remove": True})
    assert r.status_code == 400 and "뺄 레터가 없습니다" in r.json()["detail"]
    _undo_all(c, d, s)


# ---------------------------------------------------------------- 2단계가 없는 문서 · docx
def test_without_outline_and_docx(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_PDF", "off")
    server.DOCS.clear()
    c = TestClient(server.app, raise_server_exceptions=False)
    d = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")}).json()["docId"]
    o = c.post(f"/api/docs/{d}/letter/suggest", json={"ids": ["p969"]}).json()
    assert o["levels"] == [] and o["format"] == "hwpx" and o["numbers"][1]["next"] == "2."  # 개요 레벨은 없고 번호는 글만 보고 잇는다
    assert c.post(f"/api/docs/{d}/letter", json={"ids": ["p969"], "level": {"tpl": "2", "level": 1}}).status_code == 409
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ["p969"], "letter": "1)"})
    assert r.status_code == 200 and "outline" not in r.json() and r.json()["letter"]["put"] == ["1)"]
    ev = [e for e in c.get(f"/api/works/{d}/log").json()["events"] if e["kind"] == "outline"]
    assert ev and ev[-1]["op"] == "letter" and ev[-1]["letter"]["put"] == ["1)"] and ev[-1]["req"]["letter"] == "1)"  # 기록 = 개요 편집 · 레터 넣기(app.js OUTLINE_OP.letter)
    c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()
    # docx — 레터만 · 빼기(개요 레벨로는 hwpx 만)
    d = c.post("/api/docs", files={"file": (DOCX.name, DOCX.read_bytes())}).json()["docId"]
    g = c.get(f"/api/docs/{d}").json()
    top = [b for b in g["blocks"] if b["type"] == "paragraph"][:3]
    ids, texts = [b["id"] for b in top], [b["text"] for b in top]
    o = c.post(f"/api/docs/{d}/letter/suggest", json={"ids": ids[:1]}).json()
    assert o["format"] == "docx" and o["levels"] == [] and o["cur"] == {"letter": ""}  # 「[별첨]」 은 구분 라벨 꼴 — 레터가 아니다
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ids, "letter": "①"})
    assert r.status_code == 200, r.text
    got = {b["id"]: b["text"] for b in _paras(r.json()["tops"]["blocks"])}
    assert [got[i] for i in ids] == [f"{n} {t}" for n, t in zip("①②③", texts)] and r.json()["letter"]["put"] == ["①", "②", "③"]
    r = c.post(f"/api/docs/{d}/letter", json={"ids": ids[:1], "remove": True})
    assert r.status_code == 200 and r.json()["letter"]["follow"] == 2  # 뒤 「②」「③」 이 「①」「②」 로
    got = {b["id"]: b["text"] for b in _paras(c.get(f"/api/docs/{d}").json()["blocks"])}
    assert [got[i] for i in ids] == [texts[0], f"① {texts[1]}", f"② {texts[2]}"]
    assert c.post(f"/api/docs/{d}/letter", json={"ids": ids[:1], "level": {"tpl": "1", "level": 1}}).status_code == 400
    while c.get(f"/api/docs/{d}").json()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}").json()["pristine"]
    server.DOCS.clear()
