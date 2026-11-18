"""헤딩 꼴 「레터 (제목) 둘째 레터」 — 줄 안 레터(spec_헤딩_추출 ② §2 「줄 안 레터」, 2026-11-18 사용자 "O ( 제목) 둥근1... 이게 패턴이라고 헤딩패턴 단순히 레터만 있는게 아니라").
ⓐ 1단계 구간 — 맞는 꼴 · 아닌 꼴 · ⓑ 2단계 — 줄 안 「①」 은 그 줄 「o」 아래(서열과 상관없이) · 뒤에 따로 선 「②」 는 그 형제 · 「①」 아래 「-」 와 「②」 아래 「-」 는 같은 자리 ·
ⓒ 오버레이 — 문단 하나 = 줄 하나 그대로(「o」 줄이 개요 편집에서 빠지지 않음), 「①」 아래 줄의 부모 = 그 문단 줄 · 취합 셈(multi 아님). LLM 은 끔."""
import copy

import pytest

from app import heading_extract as E
from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from app import merge_convert as MC
from app import outline_edit as OE
from tests.test_headings_branch import EMPTY, _nodes, _rec

BR = R.BR


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _spans(text):
    rules = R.active(copy.deepcopy(EMPTY))
    head = R.classify(text, rules)
    return E._spans(text, head, rules, R._Run())


# ---- ⓐ 1단계 구간 ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, letter", [
    ("  o (해양환경 위험요인 및 대응 전략) ① [H/W 물리적 위험 대응] IEC 60945 선박용 전자기기 인증", "①"),
    ("  o (기본방침) ① 인증된 장비 채택, ② 설계 단계 위험 내재화, ③ 실선 운용 중 KPI 기반 지속 감시", "①"),  # 줄 안에 늘어놓은 ②③ 은 구간이 아님 — 둘째 레터 하나만
    ("□ [추진 전략] (1) 첫째 항목", "(1)"),
])
def test_inline_letter_span(text, letter):
    sp = _spans(text)
    assert [(s["kind"], s["letter"], s["line"], bool(s.get("inline"))) for s in sp] == [("marker", sp[0]["letter"], 0, False), ("marker", letter, 0, True)]
    assert sp[1]["start"] == text.index(letter)


@pytest.mark.parametrize("text", [
    "  o (범위) 연안선, 관공선, 시험선 및 상선 대상",  # 괄호 뒤가 글
    "  o ① 괄호 제목 없이 겹친 레터",  # 괄호 제목이 있을 때만
    "  o (정의)",  # 둘째 레터 없음
    "  o (제목) ①",  # 둘째 레터 뒤 글 없음
    "  o (제목)① 붙은 레터",  # 괄호 뒤 빈칸이 없음
    "  o (제목) o 같은 계열",  # 첫 레터와 같은 계열
    "  o (제목) ※ 안내 글",  # 안내는 줄 안 레터가 아니다
    "  o (" + "가" * 41 + ") ① 너무 긴 괄호 제목",  # 괄호 제목 40자까지
    "[주관기관] ① 괄호 라벨 줄",  # 첫머리가 기호·번호 레터일 때만
    "  ② [데이터 품질 위험 대응] 이상치·결측치",  # 「② [제목] 글」 — 둘째 레터 없음
])
def test_no_inline_letter(text):
    assert not any(s.get("inline") for s in _spans(text))


# ---- ⓑ 2단계 그래프 ----------------------------------------------------------------------------------------------

def _inline_rec(i, letter, shape, family, title, letter2, family2, body, lead=0):
    """「letter (title) letter2 body」 — 1단계가 둔 줄 안 구간까지."""
    rest = f"({title}) {letter2} {body}"
    r = _rec(i, letter, shape, family, rest, lead)
    r["spans"].append({"i": 1, "line": 0, "kind": "marker", "family": family2, "letter": letter2, "start": r["text"].index(letter2), "inline": True})
    return r


def _st1():
    """□ › o (전략) ① [H/W] … › - · - | ② [데이터] … › - | ③ [통신] … › - | o 다음 줄."""
    paras = [_rec(0, "□", "□", "square", "위험요인 및 검증방안", 1),
             _inline_rec(1, "o", "o", "latin-o", "해양환경 위험요인 및 대응 전략", "①", "circled", "[H/W 물리적 위험 대응] 인증 장비", 2),
             _rec(2, "-", "-", "dash", "외부 센서", 4), _rec(3, "-", "-", "dash", "현장 실사", 4),
             _rec(4, "②", "①", "circled", "[데이터 품질 위험 대응] 자동 탐지", 2), _rec(5, "-", "-", "dash", "동기화 모듈", 4),
             _rec(6, "③", "①", "circled", "[통신 위험 대응] 로컬 큐잉", 2), _rec(7, "-", "-", "dash", "자동 재전송", 4),
             _rec(8, "o", "o", "latin-o", "다음 o 줄", 2)]
    for r in paras:  # 1단계처럼 레터에는 앞 빈칸이 없다(앞 빈칸은 lead)
        r["letter"] = r["letter"].strip()
    return {"paras": paras, "labels": {"S1": {"name": "보통"}}}


@pytest.fixture
def graph():
    g = HG.build(_st1(), use_llm=False)
    g["meta"] = {"run": 1, "at": 0}
    return g


def test_graph_inline_node_under_its_line(graph):
    N = _nodes(graph)
    assert N["p1#1"]["inline"] and N["p1#1"]["para"] == "p1" and N["p1#1"]["letter"] == "①" and N["p1#1"]["text"].startswith("[H/W")
    assert N["p1#1"]["parent"] == "p1"  # 서열로는 ① 이 o 보다 얕아도 — 한 줄에 적은 것이 부모·자식
    assert [N[p]["parent"] for p in ("p2", "p3")] == ["p1#1", "p1#1"]  # 줄 안 ① 아래 「-」
    assert [N[p]["parent"] for p in ("p4", "p6")] == ["p1", "p1"]  # 따로 선 ②·③ = 줄 안 ① 의 형제
    assert [N[p]["parent"] for p in ("p5", "p7")] == ["p4", "p6"]
    assert N["p8"]["parent"] == "p0"  # 다음 o 줄은 □ 아래 그대로
    dash = {(N[p]["template"], N[p]["level"]) for p in ("p2", "p3", "p5", "p7")}
    assert len(dash) == 1  # 줄 안 ① 아래 「-」 와 ②·③ 아래 「-」 는 같은 자리
    assert (N["p1#1"]["template"], N["p1#1"]["level"]) == (N["p4"]["template"], N["p4"]["level"])


def test_llm_section_cannot_move_inline_node(graph):
    N = _nodes(graph)
    g = {k: dict(v) for k, v in N.items()}
    sec = list(N)
    applied, rejected = HG.apply_changes([{"id": "p1#1", "parent": "p0"}], sec, [], g, set(), by_id={k: {"inline": v.get("inline"), "para": v["para"]} for k, v in N.items()})
    assert not applied and rejected[0]["id"] == "p1#1" and "줄 안 레터" in rejected[0]["why"]


# ---- ⓒ 오버레이 · 취합 셈 ----------------------------------------------------------------------------------------

def test_overlay_keeps_line_and_links_children(graph):
    text = {r["id"]: r["text"] for r in _st1()["paras"]}
    ov = OE.build_overlay(graph, lambda pid: {"text": text[pid], "attrs": {"para": "1", "char": "1"}, "spacer": None} if pid in text else None)
    L = ov["lines"]
    assert "p1" in L and L["p1"]["letter"] == "o" and L["p1"]["level"] == L["p8"]["level"] and L["p1"]["tpl"] == L["p8"]["tpl"]  # 「o」 줄은 개요 줄 그대로
    assert not any("#" in k for k in L)  # 줄 안 노드는 줄이 아니다
    assert [L[p]["parent"] for p in ("p2", "p3")] == ["p1", "p1"]  # 줄 안 ① 아래 줄의 부모 = 그 문단 줄
    assert [L[p]["parent"] for p in ("p4", "p6")] == ["p1", "p1"]


def test_merge_convert_does_not_count_inline_as_multi(graph):
    by_para, per, _ = MC._index(graph)
    assert per["p1"] == 1 and by_para["p1"]["id"] == "p1"
