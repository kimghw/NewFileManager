"""헤딩 추출 2단계 — 구분 라벨 · 괄호 소제목 · 라벨 지정(spec_헤딩_추출 ② §13, 2026-11-10 사용자 「구분 기준도 아닌데 왜 라벨」 + astra 협의
artifacts/label_term_astra_2026-11-10). astra 가 요구한 회귀: 판정 규칙(복합 기준·작성 안내·붙여 쓴 차년도·주제 제목) · A·B·사용자 지정이 같은 규칙 ·
같은 지정으로 새로 추출한 결과 = 곧바로 다시 셈한 결과 · 구분 라벨 → 소제목 → 자동 왕복 · 조정 판정 이어받기(D 불일치의 first) · 체크 칸 아래 표 · 표 소속 오래됨."""
import copy
import gzip
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_calc as HC
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs, server, works
from tests.test_headings_branch import _a, _nodes, _res, _stage1, fake_ask

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _no_ask(jobs):
    raise AssertionError("LLM 을 부르면 안 됨: " + ", ".join(j["what"] for j in jobs))


# ---- 판정 규칙 -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("letter, want", [
    ("[1단계]", ("label", "단계")), ("[제2단계]", ("label", "단계")), ("[1단계(2027~2029) 목표]", ("label", "단계")), ("[N단계 개발내용]", ("label", "단계")),
    ("[1차년도 목표]", ("label", "차년도")), ("[1차년도목표]", ("label", "차년도")), ("[N차년도 개발내용]", ("label", "차년도")), ("[3년차 계획]", ("label", "차년도")),
    ("[주관연구개발기관(기관명 기입)]", ("label", "기관")), ("[공동연구개발기관N(기관명 기입)]", ("label", "기관")), ("[국외기관(기관명 기입)]", ("label", "기관")),
    ("[주관연구개발기관 : 기업명1]", ("label", "기관")), ("[해당 기관별 작성]", ("label", "기관")), ("【해당 기관별 작성】", ("label", "기관")),
    ("[1단계-1차년도]", ("label", "단계-차년도")), ("[1단계 2차년도 주관기관]", ("label", "단계-차년도-기관")),  # 겹친 기준은 하나로 줄이지 않는다
    ("[연구개발기관의 안전관리 계획]", ("subtitle", "")), ("[주관연구개발기관 현황]", ("subtitle", "")),  # 기관이라는 낱말이 든 주제 제목
    ("[한국선급]", ("subtitle", "")), ("[국내 기술 동향 및 수준]", ("subtitle", "")), ("[최종목표]", ("subtitle", "")), ("[과학⋅기술적 측면]", ("subtitle", "")),
    ("<참고>", ("subtitle", "")), ("[  ]", ("not_heading", "")), ("[ √ ]", ("not_heading", ""))])
def test_bracket_role_script(letter, want):
    assert HG.bracket_role(letter)[:2] == want
    assert HG.bracket_role(HG.label_shape(letter))[:2] == want  # 유형 표의 꼴(숫자 → N)로 물어도 같다


def test_bracket_role_llm_view_and_hint_go_through_one_rule():
    assert HG.bracket_role("[한국선급]", None, "label", "기관")[:2] == ("label", "기관")  # 이름만 있는 글 — LLM 이 구분 기준 목록의 이름을 적으면 구분 라벨
    role, basis, why = HG.bracket_role("[과학⋅기술적 측면]", None, "label", "측면")  # 목록 밖 이름(지어낸 것) — 괄호 소제목, 까닭을 남김
    assert (role, basis) == ("subtitle", "") and "측면" in why
    assert HG.bracket_role("[1단계]", None, "not_heading")[:2] == ("label", "단계")  # 스크립트가 확정하는 꼴은 LLM 답보다 앞
    assert HG.bracket_role("[한국선급]", None, "not_heading")[:2] == ("not_heading", "") and HG.bracket_role("[한국선급]", None, "note")[0] == "note"
    assert HG.bracket_role("[한국선급]", None, "heading")[:2] == ("subtitle", "")  # 괄호 줄은 보통 헤딩이 아니다
    hints = {"bases": ["세부과제"], "labels": {"[한국선급]": {"role": "label", "basis": "기관"}, "[N단계 목표]": {"role": "subtitle"},
                                              "[  ]": {"role": "subtitle"}, "[잘못]": {"role": "label", "basis": ""}}}
    assert HG.bracket_role("[한국선급]", hints, "not_heading") == ("label", "기관", HG.BY_USER)  # 사용자 지정이 가장 앞
    assert HG.bracket_role("[1단계 목표]", hints)[:2] == ("subtitle", "") and HG.bracket_role("[2단계 목표]", hints)[:2] == ("subtitle", "")  # 꼴 하나가 형제를 덮음
    assert HG.bracket_role("[  ]", hints)[0] == "subtitle" and HG.bracket_role("[잘못]", hints)[0] == "subtitle"  # basis 없는 label 지정은 지정이 아님
    assert HG.bases_of(hints) == ["단계", "차년도", "기관", "세부과제"] and HG.bases_of() == ["단계", "차년도", "기관"]
    assert HG.bracket_role("[세부1]", hints, "label", "세부과제")[:2] == ("label", "세부과제") and HG.bracket_role("[세부1]", None, "label", "세부과제")[0] == "subtitle"
    assert HG.norm_basis("단계·연차") == "단계-차년도" and HG.norm_basis("연구개발기관") == "기관" and HG.norm_basis("측면") == "" and HG.norm_basis("기관/측면") == ""
    assert HG.is_label_key("[기관]") and HG.is_label_key("[단계-차년도]") and not any(HG.is_label_key(k) for k in ("[…]", "[N]", "[가]", "o", None))


# ---- LLM 없는 판정: 구조는 같고 뜻은 구분 라벨만 ---------------------------------------------------------------------

def _doc():
    return _stage1([
        ("1.", "N.", "decimal", "장", 0),                              # p0
        ("(1)", "(N)", "paren-num", "국내 기술", 1),                    # p1
        ("[국내 기술 동향]", "[국내 기술 동향]", "bracket", "", 3),       # p2 괄호 소제목
        ("o", "o", "latin-o", "가", 2),                                # p3 소제목보다 덜 들여 쓴 내용
        ("-", "-", "dash", "나", 3),                                   # p4
        ("[국내 시장 규모]", "[국내 시장 규모]", "bracket", "", 3),       # p5 다음 소제목 = p2 의 형제
        ("o", "o", "latin-o", "다", 2),                                # p6
        ("(2)", "(N)", "paren-num", "연차별 내용", 1),                  # p7
        ("[1차년도]", "[N차년도]", "bracket", "", 3),                    # p8 구분 라벨(차년도)
        ("[추진 내용]", "[추진 내용]", "bracket", "", 3),                # p9 구분 라벨 바로 아래 소제목 — 라벨이 품는다
        ("o", "o", "latin-o", "라", 2),                                # p10
        ("[2차년도]", "[N차년도]", "bracket", "", 3),                    # p11 다음 구분 라벨 = p8 의 형제(p9 도 닫힘)
        ("o", "o", "latin-o", "마", 2),                                # p12
        ("[  ]", "[  ]", "bracket", "일반형", 3),                       # p13 체크 칸
        ("[기술도입비 현물산정]", "[기술도입비 현물산정]", "bracket", "을 위해 아래와 같이 제출합니다.", 3)])  # p14 문장 속 괄호


def test_script_build_separates_label_and_subtitle():
    g = HG.build(_doc(), use_llm=False, ask=_no_ask)
    N = _nodes(g)
    assert [(N[f"p{i}"]["role"], N[f"p{i}"]["key"]) for i in (2, 5, 8, 9, 11, 13, 14)] == [
        ("subtitle", "[…]"), ("subtitle", "[…]"), ("label", "[차년도]"), ("subtitle", "[…]"), ("label", "[차년도]"), ("not_heading", None), ("not_heading", None)]
    assert "문장" in N["p14"]["reason"] and g["counts"]["labels"] == 2 and g["counts"]["subtitles"] == 3
    assert "[라벨]" not in {n["key"] for n in g["nodes"]} and N["p8"]["basis"] == "차년도" and "basis" not in N["p2"]
    # 구조 — 괄호 소제목도 그 줄부터 새 템플릿: 아래 내용(덜 들여 쓴 o)은 소제목의 자식, 같은 깊이의 다음 소제목은 형제
    assert [N[f"p{i}"]["parent"] for i in (2, 3, 4, 5, 6)] == ["p1", "p2", "p3", "p1", "p5"]
    assert (N["p2"]["template"], N["p2"]["level"], N["p3"]["level"], N["p4"]["level"]) == ("body:[…]›o›-", 1, 2, 3) and N["p5"]["tplNo"] == N["p2"]["tplNo"]
    # 구분 라벨은 바로 아래 소제목을 품고(소제목은 제 템플릿), 다음 같은 기준 라벨이 오면 형제 — 그 사이 소제목도 닫힌다
    assert [N[f"p{i}"]["parent"] for i in (8, 9, 10, 11, 12)] == ["p7", "p8", "p9", "p7", "p11"]
    assert N["p9"]["tplNo"] == N["p2"]["tplNo"] and N["p11"]["tplNo"] == N["p8"]["tplNo"] != N["p2"]["tplNo"]
    # 뜻 — 구분 소속(division)은 구분 라벨만: 소제목은 구분의 출발점이 아니지만 바깥 구분 라벨 소속은 그대로 잇는다
    assert [N[f"p{i}"]["division"] for i in (2, 3, 6, 8, 9, 10, 12)] == [None, None, None, None, "p8", "p8", "p11"]
    assert {(e["from"], e["to"]) for e in g["edges"] if e["t"] == "division"} == {("p8", "p9"), ("p8", "p10"), ("p11", "p12"), ("p11", "p13"), ("p11", "p14")}
    tp = {t["anchor"]: t for t in g["templates"]}
    sub, lab = tp["body:[…]›o›-"], tp["body:[차년도]›o"]
    assert (sub["kind"], sub["rootRole"], sub["instances"]) == ("branch", "subtitle", 3) and (lab["kind"], lab["rootRole"], lab["instances"]) == ("label", "label", 2)
    assert sub["slots"][0]["count"] == 3 and g["counts"]["labelTemplates"] == 1  # 소제목 L1 도 슬롯(대표 서식·조정 대상)
    ins = {i["root"]: i for i in g["instances"]}
    assert ins["p8"]["basis"] == "[1차년도]" and ins["p2"]["basis"] == "" and ins["p9"]["parent"] == "p8"
    assert g["bases"] == ["단계", "차년도", "기관"] and g["bracketRule"] == HG.BRACKET_RULE and g["hints"] == {"bases": [], "labels": {}}
    ty = {t["shape"]: t for t in g["types"]}
    assert (ty["[N차년도]"]["role"], ty["[N차년도]"]["key"], ty["[  ]"]["role"], ty["[  ]"]["reason"]) == ("label", "[차년도]", "not_heading", "빈 대괄호·체크 칸")


def test_subtitle_then_label_at_same_indent_are_siblings():
    """「[최종목표]」(소제목) 뒤 같은 깊이의 「[1차년도 목표]」(구분 라벨)는 소제목 밑이 아니라 형제 — 소제목은 같은 깊이의 다음 괄호 줄을 품지 않는다."""
    g = HG.build(_stage1([("1.", "N.", "decimal", "장", 0), ("[최종목표]", "[최종목표]", "bracket", "", 2), ("o", "o", "latin-o", "가", 2),
                          ("[1차년도 목표]", "[N차년도 목표]", "bracket", "", 2), ("o", "o", "latin-o", "나", 2),
                          ("[2차년도 목표]", "[N차년도 목표]", "bracket", "", 2), ("o", "o", "latin-o", "다", 2),
                          ("[세부 내용]", "[세부 내용]", "bracket", "", 4), ("-", "-", "dash", "라", 4)]), use_llm=False, ask=_no_ask)
    N = _nodes(g)
    assert [N[f"p{i}"]["parent"] for i in range(1, 9)] == ["p0", "p1", "p0", "p3", "p0", "p5", "p6", "p7"]  # 더 들여 쓴 소제목(p7)은 열린 줄(o) 아래, 그 내용(-)은 소제목 아래
    assert N["p7"]["division"] == "p5" and N["p8"]["division"] == "p5"


# ---- LLM(A·B) 답도 같은 규칙을 거친다 ------------------------------------------------------------------------------

def _llm_doc():
    st1 = _stage1([("1.", "N.", "decimal", "장", 0), ("(1)", "(N)", "paren-num", "국내", 1),
                   ("[과학적 측면]", "[과학적 측면]", "bracket", "", 3), ("o", "o", "latin-o", "가", 2),
                   ("[경제적 측면]", "[경제적 측면]", "bracket", "", 3), ("o", "o", "latin-o", "나", 2),
                   ("(2)", "(N)", "paren-num", "기관", 1),
                   ("[한국선급]", "[한국선급]", "bracket", "", 3, "S1"), ("o", "o", "latin-o", "다", 2),
                   ("[한국해양대학교]", "[한국해양대학교]", "bracket", "", 3, "S2"), ("o", "o", "latin-o", "라", 2),
                   ("[  ]", "[  ]", "bracket", "해당 없음", 3)])
    # 가짜 A — 예전처럼 소제목에 구분 기준 「측면」 을 지어내고 내용 「o」 의 parents 에 그 키를 적는다. 기관 이름만 있는 글은 기관으로 본다.
    A = _a(st1, {"N.": ["root"], "(N)": ["N."], "o": ["[측면]", "[기관]", "(N)"]}, ["N.", "(N)", "o"],
           basis={"[과학적 측면]": "측면", "[경제적 측면]": "측면", "[한국선급]": "기관", "[한국해양대학교]": "연구개발기관", "[  ]": "기관"})
    return st1, A


def _llm_ask(A, **kw):
    def c(job, d):
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "reason": "같은 구실"} for p in d["pairs"]], "summary": ""})

    def dd(job, d):
        return _res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "verdict": "disagree", "same": False, "reason": "일부러 다름"} for p in d["pairs"]], "summary": ""})
    return fake_ask(**{"heading_types": lambda job, d: _res(A), "heading_formats": c, "heading_review": dd, **kw})


def test_llm_answers_are_settled_by_the_same_rule():
    st1, A = _llm_doc()
    seen = {}

    def a(job, d):
        seen["a"] = d
        return _res(A)

    def b(job, d):
        seen["b"] = d
        # B — 소제목 하나를 지어낸 기준의 라벨로, 보통 헤딩 하나를 basis 없이 라벨로 바꾸려 함(둘 다 안 됨)
        return _res({"changes": [{"id": "p2", "parent": "p1", "role": "label", "basis": "측면", "template": "", "level": 0, "reason": "측면 라벨"},
                                 {"id": "p6", "parent": "p0", "role": "label", "basis": "", "template": "", "level": 0, "reason": "라벨?"}], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=_llm_ask(A, heading_types=a, heading_section=b))
    assert seen["a"]["bases"] == ["단계", "차년도", "기관"] and seen["b"]["bases"] == ["단계", "차년도", "기관"]
    assert {r["key"] for r in seen["a"]["types"] if r["kind"] == "label"} == {"[…]", ""}  # 스크립트 초안 — 소제목 「[…]」, 체크 칸은 키 없음
    N = _nodes(g)
    assert [(N[f"p{i}"]["role"], N[f"p{i}"]["key"]) for i in (2, 4, 7, 9, 11)] == [
        ("subtitle", "[…]"), ("subtitle", "[…]"), ("label", "[기관]"), ("label", "[기관]"), ("not_heading", None)]
    assert N["p3"]["parent"] == "p2" and N["p5"]["parent"] == "p4" and N["p8"]["parent"] == "p7"  # 「o」 의 parents 「[측면]」 → 「[…]」 로 맞춰져 소제목에 붙는다
    ty = {t["shape"]: t for t in g["types"]}
    assert ty["o"]["parents"] == ["[…]", "[기관]", "(N)"]
    t = ty["[과학적 측면]"]
    assert (t["role"], t["basis"], t["aRole"], t["aBasis"]) == ("subtitle", "", "label", "측면") and "측면" in t["reason"]  # A 가 본 것은 따로 남는다
    assert (ty["[한국해양대학교]"]["role"], ty["[한국해양대학교]"]["basis"], ty["[  ]"]["role"]) == ("label", "기관", "not_heading")
    assert (N["p6"]["role"], N["p6"]["key"]) == ("heading", "(N)")  # basis 없는 B 의 라벨 — 그대로
    asked = {c["id"]: c["asked"] for c in g["changes"]}
    assert asked["p2"]["role"] == "label" and asked["p2"]["basis"] == "측면" and g["llm"]["mainChainFixed"] is True


# ---- 라벨 지정 — 새로 추출한 결과 = 곧바로 다시 셈한 결과 · 왕복 --------------------------------------------------------

_SAME = ("role", "key", "parent", "template", "tplNo", "level", "instance", "division", "undecided")


def _view(g):
    return [{k: n.get(k) for k in _SAME} for n in g["nodes"]], [(t["anchor"], t["kind"], t["rootRole"], t["instances"]) for t in g["templates"]], g["adjustments"]


def test_replay_equals_fresh_extraction_and_roundtrips():
    st1, A = _llm_doc()
    g0 = HG.build(st1, use_llm=True, ask=_llm_ask(A))
    assert [a["decision"] for a in g0["adjustments"]] == ["undecided"] and g0["adjustments"][0]["first"] == "adjust"  # C 같음 → D 가 다르게 봄
    assert HG.replay_of(HG.build(st1, use_llm=False)) is None  # 스크립트 결과는 되풀이할 LLM 답이 없다(그대로 다시 돌리면 됨)
    g1 = HG.build(st1, replay=HG.replay_of(g0), ask=_no_ask)  # 지정 없이 다시 셈 = 같은 결과(LLM 호출 없음)
    assert _view(g1) == _view(g0) and g1["llm"]["calls"] == 0 and g1["llm"]["replay"]["calls"] == g0["llm"]["calls"] and g1["llm"]["carried"] == 1
    assert g1["adjustments"][0]["first"] == "adjust" and g1["adjustments"][0]["review"]["verdict"] == "disagree"  # D 불일치의 1차 판정은 first 에서 되살린다
    # 구분 라벨 → 소제목, 소제목 → 구분 라벨(새 구분 기준): 같은 지정으로 새로 추출한 것과 다시 셈한 것이 같다
    hints = {"bases": ["관점"], "labels": {"[한국선급]": {"role": "subtitle", "basis": ""}, "[과학적 측면]": {"role": "label", "basis": "관점"}}}
    fresh = HG.build(st1, use_llm=True, ask=_llm_ask(A), hints=hints)
    again = HG.build(st1, replay=HG.replay_of(g0), ask=_no_ask, hints=hints)
    assert _view(again)[:2] == _view(fresh)[:2]
    N = _nodes(again)
    assert (N["p2"]["role"], N["p2"]["key"], N["p2"]["basis"]) == ("label", "[관점]", "관점") and N["p3"]["division"] == "p2"
    assert {t["shape"]: t["reason"] for t in again["types"]}["[과학적 측면]"] == HG.BY_USER
    assert (N["p7"]["role"], N["p7"]["key"]) == ("subtitle", "[…]") and N["p8"]["division"] is None and N["p4"]["role"] == "subtitle"  # 꼴이 다른 「[경제적 측면]」 은 그대로
    assert again["bases"] == ["단계", "차년도", "기관", "관점"] and again["hints"]["labels"]["[한국선급]"] == {"role": "subtitle", "basis": ""}
    # 조정 — 「[기관]」 슬롯에서 「[한국선급]」 이 빠져 대표·예문이 달라졌으므로 그 쌍의 판정은 이어받지 않는다
    assert again["llm"]["carried"] == 0 and all(a["decision"] == "undecided" and "review" not in a for a in again["adjustments"])
    # 자동으로(지정 지움) — 지정을 반영한 결과에서 다시 셈해도 처음 결과로 돌아온다(A 가 본 것을 따로 남겨 두므로)
    back = HG.build(st1, replay=HG.replay_of(again), ask=_no_ask, hints={"bases": ["관점"], "labels": {}})
    assert _view(back)[:2] == _view(g0)[:2] and {t["shape"]: t["reason"] for t in back["types"]} == {t["shape"]: t["reason"] for t in g0["types"]}
    # 유형 id 가 달라져도(후보 차례가 바뀜) 정체(자리·종류·꼴·굵게·크기)로 맞춘다
    rp = HG.replay_of(g0)
    for t in rp["a"]["types"]:
        t["type"], t["variantOf"] = "X" + t["type"], ""
    assert _view(HG.build(st1, replay=rp, ask=_no_ask)) == _view(g0)


def test_replay_keeps_slot_exception_and_undecided():
    st1, A = _llm_doc()

    def b(job, d):  # 슬롯 예외(주 사슬 L3) + 부모 변경
        return _res({"changes": [{"id": "p8", "parent": "p6", "role": "heading", "basis": "", "template": "body:N.›(N)›o", "level": 3, "reason": "주 사슬 L3"}], "summary": ""})
    g0 = HG.build(st1, use_llm=True, ask=_llm_ask(A, heading_section=b))
    N0 = _nodes(g0)
    assert N0["p8"]["parent"] == "p6" and (N0["p8"]["template"], N0["p8"]["level"]) == ("body:N.›(N)›o", 3) and N0["p8"]["changed"]
    g1 = HG.build(st1, replay=HG.replay_of(g0), ask=_no_ask, hints={"labels": {"[한국해양대학교]": {"role": "subtitle"}}})
    N1 = _nodes(g1)
    assert N1["p8"]["parent"] == "p6" and (N1["p8"]["template"], N1["p8"]["level"]) == ("body:N.›(N)›o", 3) and N1["p8"]["changed"] and g1["rejected"] == []
    assert N1["p9"]["role"] == "subtitle" and len(g1["changes"]) == 1 and g1["changes"][0]["asked"]["level"] == 3


# ---- 표 소속: 체크 칸은 소속이 아니다 · 구분 기준은 2단계가 정한 것 그대로 -------------------------------------------------

def test_table_owner_skips_not_heading_and_uses_node_basis():
    nodes = [{"id": "pA", "para": "pA", "letter": "(1)", "text": "신청 구분", "role": "heading", "parent": "pL", "division": "pL", "template": "body:(N)", "tplNo": 2, "level": 1},
             {"id": "pL", "para": "pL", "letter": "[한국선급]", "text": "", "role": "label", "key": "[기관]", "basis": "기관", "parent": "root", "division": None},
             {"id": "pC", "para": "pC", "letter": "[ √ ]", "text": "일반형", "role": "not_heading", "key": None, "parent": "pA", "division": "pL"}]
    s2 = {"nodes": nodes, "containers": [{"id": "tbl:t1", "kind": "table", "parent": "pC"}, {"id": "tbl:t2", "kind": "table", "parent": "pL"}]}
    owner = HC.owners_index({"paras": []}, s2)
    o = owner({"id": "t1", "n": 5})
    assert o["id"] == "pA" and o["role"] == "heading"  # 체크 칸(헤딩 아님) 위 노드가 소속
    assert o["division"]["id"] == "pL" and o["division"]["basis"] == ["org"]  # 글(「[한국선급]」)에서 다시 어림하지 않고 2단계의 구분 기준을 쓴다
    assert owner({"id": "t2", "n": 5})["role"] == "label"
    # 2단계 없이(1단계 어림) — 괄호 소제목은 표의 제목 소속이 되고 구분 라벨은 구분 소속, 체크 칸은 건너뛴다
    paras = [{"id": f"q{i}", "n": i, "area": "body", "kind": k, "letter": lt, "text": lt, "blank": False} for i, (k, lt) in enumerate(
        [("marker", "1. 개요"), ("label", "[주관연구개발기관(기관명 기입)]"), ("label", "[국내 기술 동향]"), ("label", "[ √ ]")])]
    o = HC.owners_index({"paras": paras})({"id": "t9", "n": 4})
    assert (o["id"], o["role"], o["division"]) == ("q2", "subtitle", None)
    o = HC.owners_index({"paras": paras[:2]})({"id": "t9", "n": 2})
    assert (o["id"], o["role"]) == ("q0", "heading") and o["division"]["id"] == "q1" and o["division"]["basis"] == ["org"]


# ---- 실행 · API — 양식(LLM 끔) ------------------------------------------------------------------------------------

@pytest.fixture
def c():
    server.DOCS.clear()
    yield TestClient(server.app, raise_server_exceptions=False)
    server.DOCS.clear()


def _graph_view(c, d):
    g = c.get(f"/api/docs/{d}/headings/graph").json()
    return g, {n["id"]: {k: n.get(k) for k in _SAME} for n in g["nodes"]}


def test_div_labels_api_saves_hint_and_reextracts_without_llm(c):
    r = c.post("/api/docs", files={"file": (RND.name, RND.read_bytes())})
    d = r.json()["docId"]
    s = server.DOCS[d]
    v = c.get(f"/api/docs/{d}/headings/div_labels").json()
    assert v["bases"] == ["단계", "차년도", "기관"] and v["items"] == [] and v["hints"] == {} and v["run"] is None
    heading_runs.run_sync(s, 1, False)
    heading_runs.run_sync(s, 2, False)
    heading_runs.run_sync(s, 3, False)
    g0, n0 = _graph_view(c, d)
    assert c.get(f"/api/docs/{d}/headings").json()["stage3"]["ownerStale"] is False
    by = {i["shape"]: i for i in c.get(f"/api/docs/{d}/headings/div_labels").json()["items"]}
    sub, org = by["[국내 기술 동향 및 수준]"], by["[주관연구개발기관(기관명 기입)]"]
    assert (sub["role"], sub["basis"], sub["count"], sub["hint"]) == ("subtitle", "", 1, None) and sub["para"] == "p5876"
    assert (org["role"], org["basis"], org["key"]) == ("label", "기관", "[기관]") and org["count"] >= 10 and by["[ √ ]"]["role"] == "not_heading"
    assert (by["[N차년도 목표]"]["role"], by["[N차년도 목표]"]["basis"], by["[해당 기관별 작성]"]["basis"], by["[최종목표]"]["role"]) == ("label", "차년도", "기관", "subtitle")
    # 잘못된 값 — 400(아무것도 안 바뀜)
    for body in ({"shape": "[국내 기술 동향 및 수준]", "role": "anchor"}, {"shape": "[1차년도 목표]", "role": "subtitle"}, {"shape": "", "role": "auto"},
                 {"shape": "[국내 기술 동향 및 수준]", "role": "label"}, {"shape": "[국내 기술 동향 및 수준]", "role": "label", "basis": "기술|시장"},
                 {"shape": "[국내 기술 동향 및 수준]", "role": "label", "basis": "라벨"}):
        assert c.put(f"/api/docs/{d}/headings/div_labels", json=body).status_code == 400, body
    assert c.get(f"/api/docs/{d}/headings/div_labels").json()["version"] == 0 and _graph_view(c, d)[0]["meta"]["run"] == g0["meta"]["run"]
    # 소제목 → 구분 라벨(새 구분 기준 이름) — 저장 + 곧바로 다시 셈(새 실행, LLM 호출 없음)
    r = c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[국내 기술 동향 및 수준]", "role": "label", "basis": "세부과제", "text": "[국내 기술 동향 및 수준]"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["applied"] is True and v["note"] == "" and v["bases"] == ["단계", "차년도", "기관", "세부과제"] and v["version"] == 1
    it = {i["shape"]: i for i in v["items"]}["[국내 기술 동향 및 수준]"]
    assert (it["role"], it["basis"], it["key"], it["hint"]["by"]) == ("label", "세부과제", "[세부과제]", "user")
    g1, n1 = _graph_view(c, d)
    assert g1["meta"]["run"] == g0["meta"]["run"] + 2 and g1["meta"]["derivedFrom"] == g0["meta"]["run"] and g1["meta"]["stage1Run"] == g0["meta"]["stage1Run"]
    assert n1["p5876"]["key"] == "[세부과제]" and n1["p5876"]["role"] == "label" and n1["p5876"]["parent"] == n0["p5876"]["parent"]
    assert g1["counts"]["labels"] == g0["counts"]["labels"] + 1 and g1["counts"]["subtitles"] == g0["counts"]["subtitles"] - 1
    folder = works.folder(d) / "headings"
    assert json.loads((folder / "hints.json").read_text("utf-8"))["labels"]["[국내 기술 동향 및 수준]"]["basis"] == "세부과제"
    run = json.loads((folder / str(g1["meta"]["run"]) / "run.json").read_text("utf-8"))
    assert run["relabel"] is True and run["derivedFrom"] == g0["meta"]["run"] and run["llm"] is False and run["costUsd"] == 0
    assert json.loads(gzip.decompress((folder / str(g1["meta"]["run"]) / "graph.json.gz").read_bytes()))["hints"]["labels"]["[국내 기술 동향 및 수준]"]["role"] == "label"
    st = c.get(f"/api/docs/{d}/headings").json()
    assert st["stage3"]["ownerStale"] is True and st["job"]["status"] == "done" and "라벨 지정 반영" in st["job"]["steps"][0]["name"]  # 표 소속은 앞 2단계 것
    heading_runs.run_sync(s, 3, False)
    assert c.get(f"/api/docs/{d}/headings").json()["stage3"]["ownerStale"] is False
    # 구분 라벨 → 소제목 — 그 꼴의 줄이 모두 바뀐다(꼴이 다른 「[공동연구개발기관1(…)]」 은 그대로)
    v = c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[주관연구개발기관(기관명 기입)]", "role": "subtitle"}).json()
    it = {i["shape"]: i for i in v["items"]}
    assert it["[주관연구개발기관(기관명 기입)]"]["role"] == "subtitle" and it["[공동연구개발기관N(기관명 기입)]"]["role"] == "label" and v["version"] == 2
    g2, n2 = _graph_view(c, d)
    assert n2["p1725"]["role"] == "subtitle" and n2["p1728"]["role"] == "label" and g2["meta"]["derivedFrom"] == g1["meta"]["run"]
    # 다시 열어도(세션을 비움) 지정이 남는다
    server.DOCS.clear()
    v = c.get(f"/api/docs/{d}/headings/div_labels").json()
    assert set(v["hints"]) == {"[국내 기술 동향 및 수준]", "[주관연구개발기관(기관명 기입)]"} and v["run"] == g2["meta"]["run"]
    # 자동으로 — 둘 다 지우면 처음 결과와 같다(더한 구분 기준 이름은 남는다)
    c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[국내 기술 동향 및 수준]", "role": "auto"})
    v = c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[주관연구개발기관(기관명 기입)]", "role": "auto"}).json()
    g3, n3 = _graph_view(c, d)
    assert v["hints"] == {} and v["bases"][-1] == "세부과제" and n3 == n0 and [t["anchor"] for t in g3["templates"]] == [t["anchor"] for t in g0["templates"]]
    # 문서가 추출 뒤 바뀌었으면 — 지정은 저장하고 다시 셈하지 않는다(다음 2단계 실행이 쓴다)
    s = server.DOCS[d]
    s.rev += 1
    r = c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[최종목표]", "role": "label", "basis": "단계"})
    assert r.status_code == 200 and r.json()["applied"] is False and "다시" in r.json()["note"] and "[최종목표]" in r.json()["hints"]
    assert _graph_view(c, d)[0]["meta"]["run"] == g3["meta"]["run"]
    s.rev -= 1
    heading_runs.run_sync(s, 2, False)  # 새 2단계 실행은 처음부터 지정을 쓴다
    g4, n4 = _graph_view(c, d)
    assert n4["p683"]["key"] == "[단계]" and "derivedFrom" not in g4["meta"] and g4["hints"]["labels"]["[최종목표]"]["basis"] == "단계"


def test_relabel_of_llm_run_replays_saved_answers(c, monkeypatch):
    """LLM 으로 만든 2단계 결과에 지정을 반영할 때 — LLM 을 다시 부르지 않고 저장된 결과에서 A·B·C·D 판정을 되풀이한다."""
    from app import llm
    monkeypatch.setenv("NFM_HEADS_PAIRS", "on")  # 서식 쌍 판정(C·D)은 기본 실행에서 뺐다(spec_헤딩_추출 ② §6 2026-11-16) — 여기는 C·D 까지 되풀이하는 것을 본다(기본은 tests/test_outline_safety.py)
    r = c.post("/api/docs", files={"file": (RND.name, RND.read_bytes())})
    d = r.json()["docId"]
    s = server.DOCS[d]
    heading_runs.run_sync(s, 1, False)
    st1 = heading_runs.state(s)["stage1"]
    A = _a(st1, {}, [])
    for t in A["types"]:  # 가짜 A — 괄호 유형은 모두 「측면」 라벨로(예전 LLM 처럼 지어냄), 주 사슬은 제안 그대로
        t["basis"] = "측면" if t["role"] == "label" else ""
    calls = []

    def ask_all(jobs, **kw):
        out = []
        for job in jobs:
            what = job["what"].split("#", 1)[0]
            if what == "heading_rules":  # LLM 판정이 그래프보다 먼저 묻는 못 맞춤·충돌 묶음(spec ② §3, 2026-11-16) — 제안 없음 · 그래프 호출 수(calls)에는 안 센다
                out.append(_res({"items": [], "summary": ""}))
                continue
            calls.append(job["what"])
            data = json.loads(job["content"].rsplit("## 자료(JSON)\n", 1)[1])
            if what == "heading_types":
                out.append(_res({**A, "mainChain": data["mainChainProposal"]}))
            elif what == "heading_section":
                out.append(_res({"changes": [], "summary": ""}))
            else:
                out.append(_res({"pairs": [{"slot": p["slot"], "a": p["a"], "b": p["b"], "same": True, "verdict": "agree", "reason": "같음"} for p in data["pairs"]], "summary": ""}))
        return out
    monkeypatch.setattr(llm, "ask_all", ask_all)
    heading_runs.run_sync(s, 2, True)
    g0, n0 = _graph_view(c, d)
    assert calls and g0["llm"]["calls"] == len(calls) and not g0["llm"]["fallback"] and g0["counts"]["adjust"] > 0
    assert n0["p5876"]["role"] == "subtitle" and n0["p1725"]["key"] == "[기관]"  # 지어낸 「측면」 은 소제목으로, 꼴로 확정되는 기관 라벨은 구분 라벨
    n_calls = len(calls)
    v = c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[국내 기술 동향 및 수준]", "role": "label", "basis": "기관"}).json()
    g1, n1 = _graph_view(c, d)
    assert v["applied"] is True and len(calls) == n_calls  # LLM 호출 없음
    assert n1["p5876"]["key"] == "[기관]" and g1["llm"]["replay"]["from"] == g0["meta"]["run"] and g1["llm"]["replay"]["calls"] == n_calls and g1["llm"]["calls"] == 0
    assert g1["llm"]["mainChain"] == g0["llm"]["mainChain"] and g1["llm"]["mainChainFixed"] is True and g1["llm"]["carried"] > 0
    assert g1["counts"]["adjust"] > 0 and sum(1 for k in n0 if n0[k]["parent"] != n1[k]["parent"]) <= 4  # 트리는 그 줄 둘레만 달라진다
    run = json.loads((works.folder(d) / "headings" / str(g1["meta"]["run"]) / "run.json").read_text("utf-8"))
    assert run["llm"] is True and run["relabel"] is True and run["costUsd"] == 0
    c.put(f"/api/docs/{d}/headings/div_labels", json={"shape": "[국내 기술 동향 및 수준]", "role": "auto"})
    g2, n2 = _graph_view(c, d)
    assert n2 == n0 and len(calls) == n_calls and g2["counts"]["adjust"] == g0["counts"]["adjust"]  # 자동으로 — 처음 LLM 결과로 돌아온다(조정 판정도)
    assert copy.deepcopy(g2["adjustments"]) == g0["adjustments"]
