"""개요(템플릿) 편집(spec_hwpx_웹편집 ② §8) — 번호 증감 · 오버레이 · 계획(순수 함수) · 서버 /outline(연구개발계획서 양식, 2단계 LLM 끔 → 가지 템플릿 「□›o›-›·」).
astra 협의 시나리오(artifacts/outline_edit_astra_2026-11-09): S1 Enter 하위 줄(글 나눔·간격 줄) · S2 마지막 레벨 Enter = 같은 레벨 · S5 Alt+Enter 뼈대(L~마지막) ·
S8~S12 레벨(가지 L1 승격 = 부모 슬롯, 마지막 레벨 하향 거절) · S14 블록 원자성 · S15 끌기(같은 템플릿·레벨, 단위 = 앞 간격 줄~마지막 내용) · S17 빈 줄 지움(라벨·자손 있는 줄 제외) ·
S18/S20 오버레이 손질(레터가 사라진 줄 제외) · S26 라벨은 Enter 만 · S27 실행 취소 뒤 오버레이 복원 · 번호 다시 매김(합성 「1-1.」, 재시작 묶음은 안 건드림)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs
from app import outline_edit as OE
from app import server
from app.hwpx_doc import P, HwpxDoc

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "samples" / "연구개발계획서_양식.hwpx"
APP_JS = ROOT / "app" / "static" / "app.js"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


# ---------------------------------------------------------------- 번호
def test_letter_numbering():
    assert OE.succ("1.") == "2." and OE.succ("(3)") == "(4)" and OE.succ("③") == "④" and OE.succ("나.") == "다." and OE.succ("b)") == "c)" and OE.succ("Ⅱ.") == "Ⅲ."
    assert OE.succ("1-1.", "1.") == "1-2." and OE.succ("1-3.", "2.") == "2-4."  # 합성 번호는 앞 번호를 부모 것으로
    assert OE.first("(3)") == "(1)" and OE.first("다.") == "가." and OE.first("2-3.", "2.") == "2-1." and OE.first("3-2.", "5.") == "5-1."
    assert OE.succ("⑳") is None and OE.succ("하.") is None  # 열의 끝
    assert OE.succ("□") == "□" and OE.first("-") == "-" and OE.succ("[기관]") == "[기관]"  # 기호·라벨은 그대로(번호 아님 — 「o」 같은 한 글자 레터는 is_numbered 가 거른다)
    assert OE.is_numbered("N-N.") and OE.is_numbered("(N)") and OE.is_numbered("①") and OE.is_numbered("가.") and OE.is_numbered("(a)")
    assert not OE.is_numbered("o") and not OE.is_numbered("-") and not OE.is_numbered("[라벨]") and not OE.is_numbered("□")
    assert OE.prefix_of("  o 글", "o") == ("  ", "o", " ") and OE.prefix_of("□글", "□") == ("", "□", "") and OE.prefix_of("  x 글", "o") == ("  ", "", "")
    assert OE.body_of("  o ", "o") == "" and OE.body_of("  o 글 ", "o") == "글"


# ---------------------------------------------------------------- 양식 + 2단계(LLM 끔) — 세션 하나를 모듈이 나눠 쓴다(열기 + 1·2단계 ≈ 3 s)
@pytest.fixture(scope="module")
def sess(tmp_path_factory):
    # 모듈 픽스처는 conftest 의 시험별 자동 픽스처(NFM_WORKS 등 임시 폴더)보다 먼저 돈다 — 여기서 모듈 임시 폴더로 두지 않으면
    # 사용자 작업 폴더(%LOCALAPPDATA%)에 작업이 쌓인다(「최근 작업」에 같은 파일이 반복, spec_작업 ① 2026-11-10)
    tmp = tmp_path_factory.mktemp("outline")
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


def _undo_all(c, d, s):
    while s.state()["undo"]:
        c.post(f"/api/docs/{d}/undo")
    assert c.get(f"/api/docs/{d}/download").content == PLAN.read_bytes()


def _seq(s, pid):
    par = s.doc._ids[pid].getparent()
    return [(s.doc._rev.get(k), s.doc._text(k)) for k in par.iterchildren(P)]


def _after(s, pid, n):
    seq = _seq(s, pid)
    i = next(k for k, (q, _) in enumerate(seq) if q == pid)
    return seq[i:i + n]


def _shape_like(s, pid, base):
    """문단 모양이 paraPr `base`(슬롯이 동결한 모양)와 같고 둘째 줄만 글 시작에 맞춰졌는지 — 개요 편집이 만든·레벨을 바꾼 줄은 내어쓰기가 붙은
    새 문단 모양을 갖는다(spec_hwpx_웹편집 ② §8-1, tests/test_outline_pos.py 가 값까지 본다)."""
    a = s.doc._para_summary(s.doc._defs["paraPr"][s.doc._ids[pid].get("paraPrIDRef")])
    b = s.doc._para_summary(s.doc._defs["paraPr"][base])
    return b["firstLineMm"] == 0 and a["firstLineMm"] < 0 and {**a, "firstLineMm": 0.0} == b


def test_overlay_and_view(sess):
    c, d, s = sess
    r = c.get(f"/api/docs/{d}/outline")
    assert r.status_code == 200
    o = r.json()
    # □ 가지 = 둘째 템플릿(T2): 그 앞 안내 상자(「※ … AI …」 t956) 안의 「o」 는 TEMP 라 헤딩 후보가 아니다(spec_헤딩_추출 ② §15 — 전에는 그 「o」 가지가 T2, □ 가 T3)
    assert o["lines"]["p970"] == {"no": 2, "level": 1, "tpl": "2", "letter": "□", "role": "heading"}
    assert o["lines"]["p972"]["level"] == 2 and o["lines"]["p975"]["level"] == 4 and o["lines"]["p968"] == {"no": 1, "level": 2, "tpl": "1", "letter": "1-1.", "role": "heading"}
    assert o["templates"]["2"]["chain"] == ["□", "o", "-", "·"] and o["templates"]["2"]["max"] == 4
    ov = s.outline
    sl = ov["templates"]["2"]["slots"]
    assert sl["2"]["prefix"] == "  o " and sl["3"]["prefix"] == "    - " and sl["4"]["prefix"] == "     ⋅"  # 접두·모양 동결(대표 문단에서)
    assert sl["1"]["attrs"] == {"paraPrIDRef": "39", "styleIDRef": "15", "charPrIDRef": "20"}
    assert sl["2"]["spacer"] and sl["3"]["spacer"] and sl["4"]["spacer"] is None  # 이 양식: o·- 앞은 빈 간격 문단, ⋅ 앞은 없음
    assert ov["lines"]["p972"]["parent"] == "p970" and ov["lines"]["p970"]["parent"] == "p968"
    # 구분 라벨(「[주관연구개발기관(기관명 기입)]」)·괄호 소제목(「[국내 기술 동향 및 수준]」)도 줄(Enter 만 됨), 체크 칸 「[ √ ]」(p5)은 헤딩 아님이라 줄이 아니다(spec_헤딩_추출 ② §13)
    assert ov["lines"]["p1725"]["role"] == "label" and ov["lines"]["p5876"]["role"] == "subtitle" and "p5" not in ov["lines"]


def test_enter_makes_child_line_with_spacer_and_splits_tail(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p970", "offset": len(s.texts["p970"])})
    assert r.status_code == 200, r.text
    j = r.json()
    new = j["focus"]["id"]
    assert j["focus"]["offset"] == 4 and j["outline"]["lines"][new] == {"no": 2, "level": 2, "tpl": "2", "letter": "o", "role": "heading"}
    rows = _after(s, "p970", 4)
    assert rows[0][1].startswith("□") and rows[1][1] == "" and rows[2] == (new, "  o ") and rows[3][1] == ""  # □ › 빈(간격) › 새 o › 기존 빈 › …
    assert _shape_like(s, new, "39") and s.outline["lines"][new]["parent"] == "p970"
    assert j["kinds"][new] == "new" and j["owpml"]["status"] in ("ok", "warn")
    # 한가운데 Enter — 뒤 글은 새 자식 줄로(공백·런 보존), 고른 글(offset..end)은 같은 트랜잭션에서 지움
    t = s.texts["p968"]  # " 1-1. 개발 대상 기술·제품의 개요"
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p968", "offset": 9, "end": 12})
    assert r.status_code == 200, r.text
    new2 = r.json()["focus"]["id"]
    assert s.texts["p968"] == t[:9] and s.texts[new2] == "  (1) " + t[12:]
    assert s.outline["lines"][new2]["level"] == 3 and s.outline["lines"][new2]["parent"] == "p968"
    _undo_all(c, d, s)
    assert new not in s.outline["lines"] and new2 not in s.outline["lines"]  # S27 실행 취소 = 오버레이도 복원


def test_enter_at_last_level_makes_sibling(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p975", "offset": 6})
    assert r.status_code == 200, r.text
    new = r.json()["focus"]["id"]
    rows = _after(s, "p975", 2)
    assert rows[1] == (new, "     ⋅") and s.outline["lines"][new]["level"] == 4 and s.outline["lines"][new]["parent"] == "p974"
    _undo_all(c, d, s)


def test_alt_enter_makes_same_level_skeleton_after_subtree(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": "p972"})  # o(L2) — 부분 트리 p972..p975(+p976 간격) 끝 뒤
    assert r.status_code == 200, r.text
    j = r.json()
    new = j["outline"]["new"]
    assert len(new) == 5 and j["focus"] == {"id": new[1], "offset": 4}
    rows = _after(s, "p975", 7)
    assert [t for _, t in rows] == ["     ⋅", "", "  o ", "", "    - ", "     ⋅", ""]  # 뼈대 o›-›⋅ 가 각자 앞 간격 줄과 함께, 기존 끝 간격 줄은 다음 줄 앞에 그대로
    ln = s.outline["lines"]
    assert ln[new[1]]["parent"] == "p970" and ln[new[3]]["parent"] == new[1] and ln[new[4]]["parent"] == new[3]
    # 마지막 레벨(⋅) Alt+Enter = 줄 하나
    r = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": "p975"})
    assert r.status_code == 200 and len(r.json()["outline"]["new"]) == 1
    # 주 사슬 「1-1.」 Alt+Enter → 1-2. 뼈대(1-2. › (1) › o › -) + 뒤 형제 1-2. → 1-3.
    r = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": "p968"})
    assert r.status_code == 200, r.text
    first = r.json()["focus"]["id"]
    assert s.texts[first] == " 1-2. " and s.texts["p982"].startswith(" 1-3. ") and s.outline["lines"]["p982"]["letter"] == "1-3."
    _undo_all(c, d, s)
    assert s.outline["lines"]["p982"]["letter"] == "1-2."


def test_level_up_down_and_refusals(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p977"], "delta": -1})  # o → □ (같은 템플릿 L1)
    assert r.status_code == 200, r.text
    assert s.texts["p977"] == "□ " and s.outline["lines"]["p977"]["level"] == 1 and s.outline["lines"]["p977"]["parent"] == "p968"
    assert s.outline["lines"]["p979"]["parent"] == "p977"  # 옛 자식 「-」 는 그대로 아래(L3 아래 L1 — 표시 레벨 유지, 부모만 검증)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p977"], "delta": 1})
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p977"], "delta": 1})  # → - (L3)
    assert r.status_code == 200 and s.texts["p977"] == "    - " and s.outline["lines"]["p977"]["level"] == 3
    assert s.outline["lines"]["p977"]["parent"] == "p972"  # 앞의 (3, L2) 줄 아래로
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p975"], "delta": 1})  # 마지막 레벨 — 거절, 가지 자동 선택 없음
    assert r.status_code == 400 and "더 깊은 레벨" in r.json()["detail"]
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p966"], "delta": -1})  # 주 사슬 L1 — 거절
    assert r.status_code == 400
    # 블록(여러 줄) — 하나라도 못 바꾸면 전부 거절(원자성)
    before = dict(s.texts)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p972", "p975"], "delta": 1})
    assert r.status_code == 400 and s.texts == before
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p972", "p977"], "delta": 1})
    assert r.status_code == 200 and s.texts["p972"] == "    - " and s.texts["p977"] == "     ⋅"
    # 개요 줄 아닌 문단·다른 그릇 섞임 — 거절
    assert c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p971"], "delta": 1}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p972", "p5"], "delta": 1}).status_code == 400
    # 가지 L1(□ p970) 승격 = 부모 슬롯(1-1. 다음 → 1-2.), 뒤 1-2. → 1-3.
    r = c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": ["p970"], "delta": -1})
    assert r.status_code == 200, r.text
    assert s.texts["p970"].startswith(" 1-2. 연구개발기술") and s.texts["p982"].startswith(" 1-3. ") and _shape_like(s, "p970", "14")
    assert s.outline["lines"]["p970"] | {} == s.outline["lines"]["p970"] and s.outline["lines"]["p970"]["tpl"] == "1" and s.outline["lines"]["p970"]["parent"] == "p966"
    _undo_all(c, d, s)
    assert s.outline["lines"]["p970"]["level"] == 1 and s.outline["lines"]["p970"]["tpl"] == "2"


def test_move_subtree_before_sibling_with_renumber(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "move", "id": "p982", "target": "p968", "where": "before"})  # 1-2. 를 1-1. 앞으로
    assert r.status_code == 200, r.text
    rows = _after(s, "p966", 4)
    assert [q for q, _ in rows] == ["p966", "p981", "p982", "p983"]  # 1. › (1-2. 의 앞 간격 줄) › 1-2.(이제 1-1.) › …
    assert s.texts["p982"].startswith(" 1-1. ") and s.texts["p968"].startswith(" 1-2. ")
    assert s.outline["lines"]["p982"]["letter"] == "1-1." and s.outline["lines"]["p968"]["letter"] == "1-2."
    # 다른 템플릿·레벨 · 제 부분 트리 안 — 거절
    assert c.post(f"/api/docs/{d}/outline", json={"op": "move", "id": "p972", "target": "p974", "where": "after"}).status_code == 400
    assert c.post(f"/api/docs/{d}/outline", json={"op": "move", "id": "p970", "target": "p972", "where": "after"}).status_code == 400
    # o(p977) 를 o(p972) 앞으로 — 단위 = 앞 간격 줄(p976) ~ 마지막 내용(p980)
    r = c.post(f"/api/docs/{d}/outline", json={"op": "move", "id": "p977", "target": "p972", "where": "before"})
    assert r.status_code == 200, r.text
    assert [q for q, _ in _after(s, "p970", 8)] == ["p970", "p976", "p977", "p978", "p979", "p980", "p971", "p972"]
    _undo_all(c, d, s)


def test_remove_empty_letter_line_only(sess):
    c, d, s = sess
    r = c.post(f"/api/docs/{d}/outline", json={"op": "remove", "id": "p974"})  # 「-」 아래 「⋅」 자손 있음 — 거절
    assert r.status_code == 400 and "하위 줄" in r.json()["detail"]
    r = c.post(f"/api/docs/{d}/outline", json={"op": "remove", "id": "p970"})  # 글 있음 — 거절
    assert r.status_code == 400
    r = c.post(f"/api/docs/{d}/outline", json={"op": "remove", "id": "p975"})  # 빈 ⋅ 줄 — 지움(앞 간격 줄 없음)
    assert r.status_code == 200, r.text
    assert r.json()["outline"]["removed"] == ["p975"] and "p975" not in s.outline["lines"] and r.json()["focus"]["id"] == "p974"
    r = c.post(f"/api/docs/{d}/outline", json={"op": "remove", "id": "p974"})  # 이제 빈 - 줄 — 앞 간격 줄(p973)과 함께
    assert r.status_code == 200 and sorted(r.json()["outline"]["removed"]) == ["p973", "p974"] and "p973" not in dict(_seq(s, "p972"))
    assert c.post(f"/api/docs/{d}/outline", json={"op": "remove", "id": "p1725"}).status_code == 400  # 구분 라벨
    _undo_all(c, d, s)
    assert "p975" in s.outline["lines"]


def test_label_line_only_enter(sess):
    c, d, s = sess
    for pid, name in (("p1725", "구분 라벨"), ("p5876", "괄호 소제목")):  # 괄호 줄은 둘 다 자식 줄 만들기(Enter)만
        r = c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": pid})
        assert r.status_code == 400 and name in r.text
        assert c.post(f"/api/docs/{d}/outline", json={"op": "level", "ids": [pid], "delta": 1}).status_code == 400


def test_overlay_sync_drops_broken_letter_and_merged_lines(sess):
    c, d, s = sess
    c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "글만"})  # 레터 「o」 가 첫머리에서 사라짐 → 개요 줄 아님
    assert "p972" not in s.outline["lines"] and s.outline["lines"]["p974"]["parent"] == "p970"  # 자식은 조부모로
    c.patch(f"/api/docs/{d}/blocks/p972", json={"text": "  o "})  # 글만 되돌려도 다시 줄이 되진 않음(2단계를 다시 돌려야) — 되돌리기로 원본 복원
    c.post(f"/api/docs/{d}/blocks/p972/revert")
    assert "p972" not in s.outline["lines"]
    r = c.post(f"/api/docs/{d}/merge", json={"id": "p975", "dir": "prev"})  # ⋅ 를 - 에 합침 → p975 줄 빠짐
    assert r.status_code == 200 and "p975" not in s.outline["lines"]
    _undo_all(c, d, s)
    assert "p975" in s.outline["lines"]  # 실행 취소는 구조 편집 직전 오버레이로(글 고침으로 뺀 p972 는 그대로 없음)
    assert c.post(f"/api/docs/{d}/outline", json={"op": "sibling", "id": "p972"}).status_code == 400


def test_outline_requires_stage2_and_hwpx():
    server.DOCS.clear()
    c = TestClient(server.app, raise_server_exceptions=False)
    r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes(), "application/octet-stream")})
    d = r.json()["docId"]
    r = c.get(f"/api/docs/{d}/outline")
    assert r.status_code == 200 and r.json()["off"] is True and r.json()["lines"] == {}  # 404 가 아니라 꺼짐 표시(문서 열 때마다 불러 콘솔 오류를 안 남김)
    assert c.post(f"/api/docs/{d}/outline", json={"op": "enter", "id": "p970", "offset": 0}).status_code == 409
    assert c.post(f"/api/docs/{d}/outline", json={"op": "bogus", "id": "p970"}).status_code == 400
    server.DOCS.clear()


def test_client_wiring():
    js = APP_JS.read_text(encoding="utf-8")
    for needle in ('outlineKey("sibling", p)', 'outlineKey("enter", p)', 'outlineLevel(p, e.key === "ArrowUp" ? -1 : 1)', 'outlineKey("remove", p)',
                   "if (r.outline) outlineApply(r.outline);", "function outlineGrip(", "function bindOutlineDrag(", "outlineLoad();", 'outline: "개요 편집"'):
        assert needle in js, needle
    assert js.index("if (e.altKey) outlineKey") < js.index("else if (outlineLine(p)) outlineKey") < js.index("else splitHere(p)")  # Alt+Enter 가 Enter 분기보다 먼저
