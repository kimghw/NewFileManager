"""개요 줄 자리(spec_hwpx_웹편집 ② §8-1) — 레터 위치·글 시작·둘째 줄 계산(글자 폭 모형) · 규칙(target) · 글 고침 뒤 저절로 맞춤(PATCH) ·
개요 편집이 만든 줄 · 슬롯 규칙 적용(PUT /outline/slots) · 실행 취소. 연구개발계획서 양식(본문 「  o 」 = 돋움체 12pt → 앞 공백 4.23 · 글 시작 8.47mm)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_pos as OP
from app import server
from app.hwpx_doc import HwpxDoc

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
HANG = pytest.approx(-8.47, abs=0.02)  # 「  o 」 = 빈칸 2(0.5em씩) + o(0.5em) + 빈칸 1 = 2em × 12pt


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


# ---------------------------------------------------------------- 계산(문서만)
@pytest.fixture(scope="module")
def plan_doc():
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    return doc


def test_place_measures_letter_and_text_start(plan_doc):
    m = OP.Measure(plan_doc)
    o = m.place("p972", "o")  # 「  o 」 돋움체 12pt, 문단 여백 0
    assert o["leadMm"] == pytest.approx(4.23, abs=0.02) and o["letterMm"] == pytest.approx(4.23, abs=0.02)
    assert o["textMm"] == pytest.approx(8.47, abs=0.02) and o["line2Mm"] == 0 and o["firstMm"] == 0
    dash = m.place("p974", "-")  # 「    - 」
    assert dash["letterMm"] == pytest.approx(8.47, abs=0.02) and dash["textMm"] == pytest.approx(12.70, abs=0.02)
    box = m.place("p970", "□")  # 전각 기호 1em + 빈칸
    assert box["letterMm"] == 0 and box["textMm"] == pytest.approx(6.35, abs=0.02)
    # 양식 저자가 내어쓰기를 준 문단(Shift+Tab — 커서 자리): 저장 값이 셈한 글 시작과 같다
    made = m.place("p6341", "o")
    assert made["firstMm"] == pytest.approx(-8.53, abs=0.01) and made["line2Mm"] == pytest.approx(made["textMm"], abs=0.1)
    circ = m.place("p1528", "①")  # 돋움 8pt 「 ① 」 — 비례 글꼴이어도 빈칸은 0.5em
    assert circ["line2Mm"] == pytest.approx(circ["textMm"], abs=0.05)
    assert m.place("p972", "x") is None and m.place("p971", "o") is None  # 첫머리에 그 레터가 없음 · 빈 문단


def test_advance_model_ratio_spacing_and_half_space(plan_doc):
    doc = plan_doc
    m = OP.Measure(doc)
    p = doc._ids["p972"]
    cid = doc._char_id(p)
    em = 12 * OP.PT_MM
    assert m.advance(" ", cid) == pytest.approx(0.5 * em, abs=1e-3) and m.advance("가", cid) == pytest.approx(em, abs=1e-3)
    assert m.advance("\t", cid) is None and m.width("  o \t", lambda i: cid) is None
    fmt = doc.derive_format(doc.get_format("p972"), {"ratioPct": 80, "spacingPct": -10})  # 장평 80% · 자간 −10% → 글자 폭 × 0.8 × 0.9
    cid2 = doc._parse(fmt)[1]
    assert m.advance("가", cid2) == pytest.approx(em * 0.72, abs=1e-3) and m.advance(" ", cid2) == pytest.approx(0.5 * em * 0.72, abs=1e-3)


def test_target_rules():
    cur = {"leftMm": 0.0, "firstMm": 0.0, "x0": 0.0, "leadMm": 4.23, "prefixMm": 8.47, "letterMm": 4.23, "textMm": 8.47, "line2Mm": 0.0}
    assert OP.target(cur, None) == (0.0, -8.47)  # 기본 = 글 시작에 맞춤(내어쓰기)
    assert OP.target(cur, {"line2": "keep"}) is None
    hung = {**cur, "firstMm": -5.0, "line2Mm": 5.0}
    assert OP.target(hung, None) is None  # 문서가 이미 정한 값은 기본 규칙이 안 건드림
    assert OP.target(hung, None, was=-5.0) == (0.0, -8.47)  # 앞서 저절로 넣은 값이면 다시 맞춤(접두가 바뀜)
    assert OP.target(hung, {"line2": "text", "set": True}, full=True) == (0.0, -8.47)  # 사용자가 정한 규칙은 덮음
    assert OP.target(cur, {"line2": "mm", "mm": 6, "set": True}, full=True) == (0.0, -6.0)
    assert OP.target(cur, {"line2": "text", "letterMm": 10, "set": True}, full=True) == (5.77, -8.47)  # 레터 위치 10 → 왼쪽 여백 5.77
    assert OP.target(cur, {"line2": "mm", "mm": 2, "letterMm": 9.23, "set": True}, full=True) == (2.0, 3.0)  # 둘째 줄이 첫 줄보다 왼쪽 = 들여쓰기
    assert OP.target(cur, {"line2": "keep", "letterMm": 9.23, "set": True}, full=True) == (5.0, 0.0)  # 그대로 = 같이 민다
    assert OP.target(cur, {"line2": "text", "letterMm": 10, "set": True}) is not None and OP.target(cur, {"line2": "text", "letterMm": 10, "set": True})[0] == 0.0  # 글 고침 길은 레터를 안 옮김
    with pytest.raises(ValueError):
        OP.target(cur, {"line2": "text", "letterMm": 1, "set": True}, full=True)  # 앞 공백 폭보다 작은 레터 위치
    assert OP.target({**cur, "prefixMm": 80.0}, None) is None  # 접두가 지나치게 넓으면(레터로 잘못 읽힌 긴 글) 안 맞춤
    assert OP.target({**cur, "firstMm": -8.47, "line2Mm": 8.47}, None, was=-8.47) is None  # 이미 맞음


def test_clean_pos():
    assert OP.clean_pos({"line2": "text"}) == {"line2": "text", "set": True}
    assert OP.clean_pos({"line2": "mm", "mm": 6, "letterMm": 4.234}) == {"line2": "mm", "mm": 6.0, "letterMm": 4.23, "set": True}
    for bad in ({"line2": "x"}, {"line2": "mm"}, {"line2": "mm", "mm": "6"}, {"line2": "mm", "mm": -1}, {"line2": "text", "letterMm": 999}, {"line2": "mm", "mm": True}):
        with pytest.raises(ValueError):
            OP.clean_pos(bad)


# ---------------------------------------------------------------- 서버(양식 + 2단계 LLM 끔)
@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("outline_pos")  # 모듈 픽스처는 conftest 의 시험별 임시 폴더보다 먼저 돈다 — 사용자 작업 폴더에 쌓이지 않게 직접 돌린다
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
        yield c, d, s
        server.DOCS.clear()


def _fmt(s, pid):
    p = s.doc._ids[pid]
    return s.doc._summary(p.get("paraPrIDRef"), s.doc._char_id(p))


def _tid(s):
    """가지 템플릿 「□ › o › - › ·」 의 id — 번호는 2단계 실행마다 달라질 수 있어 「  o 」 줄(p972)에서 읽는다."""
    assert s.outline["lines"]["p972"]["level"] == 2
    return s.outline["lines"]["p972"]["tpl"]


def _undo_all(c, d, s):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def test_view_has_slot_places(sess):
    c, d, s = sess
    o = c.get(f"/api/docs/{d}/outline").json()
    sl = o["templates"][_tid(s)]["slots"]  # 가지 템플릿 「□ › o › - › ·」
    assert sl["2"]["letter"] == "o" and sl["2"]["pos"] == {"line2": "text"} and sl["2"]["lines"] >= 1 and not sl["2"]["rooted"]
    assert sl["2"]["at"] == {"letterMm": 4.2, "textMm": 8.5, "line2Mm": 0.0, "leadMm": 4.2, "leftMm": 0.0, "firstMm": 0.0}
    assert sl["2"]["to"] == {"letterMm": 4.2, "textMm": 8.5, "line2Mm": 8.5}  # 새 줄은 둘째 줄 = 글 시작
    assert sl["3"]["to"]["line2Mm"] == sl["3"]["at"]["textMm"] == 12.7
    lab = next(t for t in o["templates"].values() if t["kind"] == "label")
    assert lab["slots"]["1"]["rooted"] and "at" not in lab["slots"]["1"]  # 괄호 줄 — 자리 규칙 없음


def test_typing_in_outline_line_aligns_second_line(sess):
    c, d, s = sess
    assert _fmt(s, "p972")["firstLineMm"] == 0
    r = c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "  o 우리는 무엇이든지 정리할 수 있는 기반을 완성해야 함. 또한 무엇이든지 잘 처리할 수 있도록 해야 합니다."})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["format"]["firstLineMm"] == HANG and j["format"]["indentLeftMm"] == 0  # 첫 줄은 그대로, 둘째 줄부터 글 시작(「우」)에
    assert j["kinds"]["p972"] == "text" and "p972" not in s.formatted  # 모양 편집으로 치지 않는다 — 글을 되돌리면 원본으로
    assert s.outline["lines"]["p972"]["first"] == HANG
    # 레터 뒤 공백을 늘리면(접두가 바뀜) 저절로 맞춘 값이므로 다시 맞춘다 — 빈칸 하나 = 0.5em = 2.12mm
    r = c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "  o  우리는 무엇이든지"})
    assert r.json()["format"]["firstLineMm"] == pytest.approx(-10.58, abs=0.02)
    r = c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "  o  우리는 무엇이든지 정리"})
    assert "format" not in r.json()  # 접두가 그대로면 모양도 그대로(응답에 안 실음)
    # 원래 글로 돌아가면 문단은 원본 XML(문단 모양 포함), 파일은 원본 바이트
    r = c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "  o "})
    j = r.json()
    assert j["restored"] is True and j["format"]["firstLineMm"] == 0 and j["pristine"] is True
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def test_typing_keeps_a_hanging_the_document_already_has(sess):
    c, d, s = sess
    t = s.texts["p6341"]  # 양식이 내어쓰기 8.53mm 를 준 「  o 과제 수행 중 …」
    r = c.patch(f"/api/docs/{d}/blocks/p6341", json={"text": t + " 덧붙임"})
    assert r.status_code == 200 and "format" not in r.json() and _fmt(s, "p6341")["firstLineMm"] == pytest.approx(-8.53, abs=0.01)
    c.patch(f"/api/docs/{d}/blocks/p6341", json={"text": t})
    # 개요 줄이 아닌 문단·괄호 줄(구분 라벨)은 안 건드린다
    lab = s.texts["p1725"]
    r = c.patch(f"/api/docs/{d}/blocks/p1725", json={"text": lab + " "})
    assert "format" not in r.json()
    c.patch(f"/api/docs/{d}/blocks/p1725", json={"text": lab})
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def test_align_catches_up_lines_edited_before(sess):
    """이 기능 전에(또는 2단계 전에) 글을 고쳐 둔 개요 줄 — 화면이 문서를 열 때 POST …/outline/align 한 번으로 맞춘다."""
    c, d, s = sess
    c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "  o 예전에 고쳐 둔 줄"})
    c.patch(f"/api/docs/{d}/blocks/p977", json={"text": "  o 손으로 모양을 준 줄"})
    for pid in ("p972", "p977"):  # 맞추기 전 상태를 흉내 — 문단 모양을 원래 것으로, 기억도 지움
        s.doc._ids[pid].set("paraPrIDRef", "39")
        s.doc._touch(s.doc._ids[pid])
        s.outline["lines"][pid].pop("first", None)
    s.formatted.add("p977")  # 사용자가 문단 수정으로 모양을 바꾼 줄은 건드리지 않는다
    rev = s.rev
    r = c.post(f"/api/docs/{d}/outline/align")
    assert r.status_code == 200, r.text
    j = r.json()
    assert list(j["formats"]) == ["p972"] and j["formats"]["p972"]["firstLineMm"] == HANG and j["kinds"]["p972"] == "text" and j["rev"] == rev + 1
    assert _fmt(s, "p977")["firstLineMm"] == 0
    assert c.post(f"/api/docs/{d}/outline/align").json()["formats"] == {} and s.rev == rev + 1  # 다시 부르면 할 일 없음(차례도 그대로)
    s.formatted.discard("p977")
    for pid in ("p972", "p977"):
        assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "  o "}).json()["restored"] is True
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def test_new_outline_lines_are_born_aligned(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p970", "offset": len(s.texts["p970"])})  # □ 에서 Enter → 새 「  o 」
    assert r.status_code == 200, r.text
    new = r.json()["focus"]["id"]
    f = _fmt(s, new)
    assert f["firstLineMm"] == HANG and f["indentLeftMm"] == 0 and s.outline["lines"][new]["first"] == HANG
    blk = next(b for b in r.json()["tops"]["blocks"] if b["id"] == new)
    assert blk["format"]["firstLineMm"] == HANG  # 화면이 받는 블록에도
    r = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": new})  # Alt+Enter 뼈대 「o › - › ⋅」 — 줄마다 제 글 시작
    assert r.status_code == 200, r.text
    made = [i for i in r.json()["outline"]["new"] if i in s.outline["lines"]]
    assert [round(-_fmt(s, i)["firstLineMm"], 1) for i in made] == [8.5, 12.7, 14.7]
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [new], "delta": 1})  # o → - : 그 레벨의 글 시작으로 다시
    assert r.status_code == 200, r.text
    assert _fmt(s, new)["firstLineMm"] == pytest.approx(-12.70, abs=0.02)
    _undo_all(c, d, s)


def test_slot_rule_applies_to_every_line_of_the_level(sess):
    c, d, s = sess
    T = _tid(s)
    n = len(OP.slot_lines(s.outline, T, 2))
    r = c.put(f"/api/docs/{d}/outline/slots/{T}/2", json={"line2": "text"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["aligned"] == len(j["formats"]) and 0 < j["aligned"] <= n and j["undo"] == 1
    assert j["formats"]["p972"]["firstLineMm"] == HANG and j["kinds"]["p972"] == "format"
    assert j["outline"]["templates"][T]["slots"]["2"]["pos"] == {"line2": "text", "set": True}
    assert j["owpml"]["status"] in ("ok", "warn")
    assert all(_fmt(s, i)["firstLineMm"] == pytest.approx(-OP.Measure(s.doc).place(i, "o")["prefixMm"], abs=0.02) for i in OP.slot_lines(s.outline, T, 2))
    # 직접 지정 + 레터 위치: 레터 10mm · 둘째 줄 12mm → 왼쪽 여백 5.77(= 10 − 앞 공백 4.23) · 내어쓰기 6.23
    r = c.put(f"/api/docs/{d}/outline/slots/{T}/2", json={"line2": "mm", "mm": 12, "letterMm": 10})
    assert r.status_code == 200, r.text
    f = r.json()["formats"]["p972"]
    assert f["indentLeftMm"] == pytest.approx(5.77, abs=0.02) and f["firstLineMm"] == pytest.approx(-6.23, abs=0.02)
    to = r.json()["outline"]["templates"][T]["slots"]["2"]["to"]
    assert to == {"letterMm": 10.0, "textMm": 14.2, "line2Mm": 12.0}
    # 그 규칙 아래에서 새로 만든 줄도 같은 자리
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p970", "offset": len(s.texts["p970"])})
    new = r.json()["focus"]["id"]
    assert _fmt(s, new)["indentLeftMm"] == pytest.approx(5.77, abs=0.02) and _fmt(s, new)["firstLineMm"] == pytest.approx(-6.23, abs=0.02)
    # 잘못된 값 — 문서·규칙 그대로
    before = s.state()["undo"]
    assert c.put(f"/api/docs/{d}/outline/slots/{T}/2", json={"line2": "text", "letterMm": 1}).status_code == 400  # 앞 공백 폭보다 작은 레터 위치
    assert c.put(f"/api/docs/{d}/outline/slots/{T}/2", json={"line2": "mm"}).status_code == 400
    assert c.put(f"/api/docs/{d}/outline/slots/{T}/9", json={"line2": "text"}).status_code == 404
    lab = next(tid for tid, t in s.outline["templates"].items() if t["kind"] == "label")
    assert c.put(f"/api/docs/{d}/outline/slots/{lab}/1", json={"line2": "text"}).status_code == 400  # 괄호 줄
    assert s.state()["undo"] == before and s.outline["templates"][T]["slots"]["2"]["pos"]["mm"] == 12.0
    # 실행 취소 — 규칙도 문서도 처음으로
    _undo_all(c, d, s)
    assert "pos" not in s.outline["templates"][T]["slots"]["2"] and _fmt(s, "p972")["firstLineMm"] == 0


def test_slot_preview_shows_before_after_without_changing(sess):
    """「자리 수정」 미리보기(POST …/slots/{tpl}/{level}/preview) — 적용과 같은 계산 · 문서·규칙·실행 취소 그대로."""
    c, d, s = sess
    assert c.get(f"/api/docs/{d}/outline").status_code == 200  # 오버레이를 만든다(이 시험만 돌릴 때)
    T = _tid(s)
    before_undo, before_rev, before_pos = s.state()["undo"], s.rev, s.outline["templates"][T]["slots"]["2"].get("pos")
    r = c.post(f"/api/docs/{d}/outline/slots/{T}/2/preview", json={"line2": "mm", "mm": 12, "letterMm": 10})
    assert r.status_code == 200, r.text
    j = r.json()
    g = next(x for x in j["groups"] if "p972" in x["paras"])
    assert g["changed"] and g["before"]["letterMm"] == 4.2 and g["before"]["line2Mm"] == 0.0
    assert g["after"] == {"letterMm": 10.0, "textMm": 14.2, "line2Mm": 12.0, "leftMm": 5.8, "firstMm": -6.2}
    assert j["slot"]["after"]["letterMm"] == 10.0 and j["slot"]["after"]["line2Mm"] == 12.0
    assert j["lines"] == len(OP.slot_lines(s.outline, T, 2)) and j["changed"] + j["same"] + j["skipped"] == j["lines"]
    assert s.state()["undo"] == before_undo and s.rev == before_rev and s.outline["templates"][T]["slots"]["2"].get("pos") == before_pos
    assert _fmt(s, "p972")["firstLineMm"] == 0
    # 적용한 수와 같다
    r = c.put(f"/api/docs/{d}/outline/slots/{T}/2", json={"line2": "mm", "mm": 12, "letterMm": 10})
    assert r.status_code == 200 and r.json()["aligned"] == j["changed"]
    j2 = c.post(f"/api/docs/{d}/outline/slots/{T}/2/preview", json={"line2": "mm", "mm": 12, "letterMm": 10}).json()
    assert j2["changed"] == 0 and j2["same"] == j["changed"] + j["same"]  # 이미 그 자리 — 바뀔 줄 없음
    # 잘못된 값
    j3 = c.post(f"/api/docs/{d}/outline/slots/{T}/2/preview", json={"line2": "text", "letterMm": 1}).json()
    assert j3["error"] and "레터 앞 빈칸" in j3["error"]  # 앞 공백 폭보다 작은 레터 위치 — 줄마다 거절(400 이 아니라 까닭을 보임)
    assert c.post(f"/api/docs/{d}/outline/slots/{T}/2/preview", json={"line2": "mm"}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline/slots/{T}/9/preview", json={"line2": "text"}).status_code == 404
    _undo_all(c, d, s)


def test_renumber_realigns_lines_aligned_before(plan_doc):
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    ov = {"lines": {"p972": {"tpl": "1", "level": 1, "letter": "o", "role": "heading"}}, "templates": {"1": {"slots": {"1": {}}}}}
    assert OP.align(doc, ov, "p972")["firstLineMm"] == HANG and ov["lines"]["p972"]["first"] == HANG
    doc.replace_prefix("p972", 4, "  oo ")  # 접두가 한 글자(0.5em) 길어짐 — 번호 다시 매김이 「9.」 → 「10.」 으로 바꾼 것과 같은 일
    ov["lines"]["p972"]["letter"] = "oo"
    assert OP.align(doc, ov, "p972")["firstLineMm"] == pytest.approx(-10.58, abs=0.02)
    assert OP.align(doc, ov, "p972") is None  # 이미 맞음
    ov["lines"]["p972"]["role"] = "label"
    doc.format_para(["p972"], {"firstLineMm": 0})
    assert OP.align(doc, ov, "p972") is None  # 괄호 줄은 안 건드림


def test_margin_values_are_written_even():
    """switch 없는 문단 모양의 여백은 2배 값 — 홀수면 한글이 5배로 그린다(references/HWPX_포맷.md, 한글 PDF 실측: 2835 = 5mm 가 25mm 로). 늘 짝수로 쓴다."""
    from app.hwpx_format import _c, _h
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    for mm in (5, 10, 13.76, 20, 0.1, 7.3):
        doc.format_para(["p972"], {"indentLeftMm": mm, "firstLineMm": -mm})
        m = doc._defs["paraPr"][doc._ids["p972"].get("paraPrIDRef")].find(_h("margin"))
        left, intent = int(m.find(_c("left")).get("value")), int(m.find(_c("intent")).get("value"))
        assert left % 2 == 0 and intent % 2 == 0 and left == -intent, (mm, left, intent)
        assert doc.get_format("p972")["summary"]["indentLeftMm"] == pytest.approx(mm, abs=0.01)


def test_reused_def_id_does_not_keep_old_summary():
    """뺀 정의의 id 는 다음 새 정의가 다시 쓴다 — 옛 id 의 서식 요약이 남아 있으면 새 문단 모양이 옛 내어쓰기로 읽힌다(drop_unused_defs 가 요약 캐시를 비움)."""
    doc = HwpxDoc(PLAN.read_bytes())
    doc.blocks()
    keep = {k: set(v) for k, v in doc._defs.items()}
    old = doc._ids["p972"].get("paraPrIDRef")
    doc.format_para(["p972"], {"firstLineMm": -10})
    made = doc._ids["p972"].get("paraPrIDRef")
    assert doc.get_format("p972")["summary"]["firstLineMm"] == -10
    doc._ids["p972"].set("paraPrIDRef", old)  # 되돌림 → 새 정의는 안 쓰임
    assert doc.drop_unused_defs(keep) >= 1
    doc.format_para(["p972"], {"firstLineMm": -20})
    assert doc._ids["p972"].get("paraPrIDRef") == made and doc.get_format("p972")["summary"]["firstLineMm"] == -20  # 같은 id, 새 값


def test_carry_keeps_user_rules_across_reruns():
    old = {"templates": {"3": {"anchor": "body:□›o", "slots": {"2": {"pos": {"line2": "mm", "mm": 6.0, "set": True}}, "1": {"pos": {"line2": "text"}}}}},
           "lines": {"p1": {"first": -8.47}, "p2": {}}}
    new = {"templates": {"7": {"anchor": "body:□›o", "slots": {"1": {}, "2": {}}}, "8": {"anchor": "body:x", "slots": {"2": {}}}}, "lines": {"p1": {}, "p3": {}}}
    OP.carry(old, new)
    assert new["templates"]["7"]["slots"]["2"]["pos"] == {"line2": "mm", "mm": 6.0, "set": True} and "pos" not in new["templates"]["7"]["slots"]["1"]
    assert "pos" not in new["templates"]["8"]["slots"]["2"] and new["lines"] == {"p1": {"first": -8.47}, "p3": {}}
    OP.carry(None, new)
