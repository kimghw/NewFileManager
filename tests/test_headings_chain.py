"""헤딩 추출 2단계 — 잇닿은 사슬(spec_헤딩_추출 ② §6 「잇닿은 사슬」, 2026-11-17 사용자 "레터가 다르거나 하지 않고 늘어나면 같은 템플릿으로 포함되도록" · 답 「T1 에 넣기」).
ⓐ 받아 줄 부모가 열려 있지 않은 줄을 문서 맨 위로 보내며 열린 줄을 다 닫지 않는다(가장 가까운 더 얕은 줄에 어림으로) · ⓑ 문서 맨 위에 매달린 줄의 레터가 주 사슬에 있으면 주 사슬의 그 레벨 ·
ⓒ 사슬보다 더 내려가면 주 사슬이 늘어난다 · ⓓ 레벨을 건너뛴 줄(부모 템플릿의 더 깊은 레벨 레터)은 그 레벨 — 부모 사슬에 없는 레터·더 얕은 레터만 가지 템플릿 · ⓔ 다시 셈 때 옛 앵커의 슬롯 예외를 주 사슬 자리로.
LLM 은 가짜 ask."""
import pytest

from app import heading_graph as HG
from app import heading_guides as G
from app import heading_rules as R
from tests.test_headings_branch import _a, _nodes, _res, _stage1, fake_ask

MAIN = "body:N.›N-N.›(N)›o›-"
KNOW = {"N.": ["root"], "N-N.": ["N."], "(N)": ["N-N."], "o": ["(N)"], "-": ["o"]}


@pytest.fixture(autouse=True)
def _heads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


def _build(rows, parents=None, main=("N.", "N-N.", "(N)", "o", "-"), **handlers):
    st1 = _stage1(rows)
    A = _a(st1, parents or KNOW, list(main))
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A), **handlers))
    return st1, g, _nodes(g)


# ---- ⓐ 부모 초안 — 받아 줄 부모가 없는 줄 --------------------------------------------------------------------------------------

def _stray_rows():
    return [("5.", "N.", "decimal", "장", 0),
            ("5-2.", "N-N.", "hyphen", "절", 0),
            ("(3)", "(N)", "paren-num", "괄호", 1),
            ("-", "-", "dash", "o 를 건너뛴 줄", 3),  # A: - 의 부모 = o — 열려 있지 않다
            ("5-3.", "N-N.", "hyphen", "다음 절", 0),
            ("5-4.", "N-N.", "hyphen", "그 다음 절", 0),
            ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2), ("-", "-", "dash", "줄", 3)]


def test_unaccepted_line_keeps_open_lines():
    """「(3)」 바로 아래 「-」(o 를 건너뜀) 하나 때문에 뒤의 5-3.·5-4. 가 문서 맨 위에 매달려 따로 템플릿이 되지 않는다 — 「-」 는 가장 가까운 더 얕은 줄 (3) 에 어림으로."""
    _, g, N = _build(_stray_rows())
    assert N["p3"]["parent"] == "p2" and N["p3"]["heuristic"]  # 건너뛴 줄 = (3) 의 자식(어림)
    assert (N["p3"]["template"], N["p3"]["level"]) == (MAIN, 5)  # o 를 건너뛴 「-」 = 주 사슬 L5(ⓓ)
    assert [N[p]["parent"] for p in ("p1", "p4", "p5")] == ["p0"] * 3  # 절들은 모두 「5.」 아래 형제
    assert [(N[p]["template"], N[p]["level"]) for p in ("p4", "p5", "p6", "p7", "p8")] == [(MAIN, 2), (MAIN, 2), (MAIN, 3), (MAIN, 4), (MAIN, 5)]
    assert [t["anchor"] for t in g["templates"]] == [MAIN] and g["counts"]["heuristic"] == 1
    assert [i["root"] for i in g["instances"] if i["template"] == 1] == ["p0"]  # 주 사슬 인스턴스는 「5.」 하나


def test_b_parent_clears_the_guess():
    """어림으로 붙인 줄을 B 가 보고 부모를 적으면 어림 표지가 풀린다(LLM 이 정한 부모)."""
    b = lambda job, d: _res({"changes": [{"id": "p3", "parent": "p2", "role": "heading", "template": "", "level": 0, "reason": "(3) 의 내용"}], "summary": ""})
    _, g, N = _build(_stray_rows(), heading_section=b)
    assert N["p3"]["parent"] == "p2" and N["p3"]["changed"] and not N["p3"]["heuristic"] and g["counts"]["heuristic"] == 0


def test_root_in_parents_still_goes_to_the_top():
    """A 가 「문서 맨 위에도 온다」(root)고 한 레터는 열린 부모가 없으면 전처럼 문서 맨 위 — 어림으로 붙이지 않는다."""
    rows = [("1.", "N.", "decimal", "장", 0), ("1-1.", "N-N.", "hyphen", "절", 0), ("(1)", "(N)", "paren-num", "괄호", 1),
            ("□", "□", "square", "붙임", 0), ("1-2.", "N-N.", "hyphen", "절", 0)]
    _, g, N = _build(rows, {**KNOW, "□": ["root", "o"]}, main=("N.", "N-N.", "(N)"))
    assert g["llm"]["mainChainFixed"] and N["p3"]["parent"] == "root" and not N["p3"]["heuristic"] and N["p3"]["template"] == "body:□"  # 주 사슬에 없는 레터 — 가지 템플릿 그대로
    assert N["p4"]["parent"] == "root" and (N["p4"]["template"], N["p4"]["level"]) == ("body:N.›N-N.›(N)", 2)  # 열린 「1.」 은 닫혔지만(문서 맨 위 줄 뒤) 레터가 주 사슬 — ⓑ


def test_unknown_rank_letter_goes_to_the_nearest_open_line():
    """서열을 모르는 글머리(「▸」)는 받아 줄 부모가 없으면 가장 가까운 열린 줄에(문서 맨 위가 아니라)."""
    rows = [("1.", "N.", "decimal", "장", 0), ("1-1.", "N-N.", "hyphen", "절", 0), ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2),
            ("▸", "▸", "arrow", "화살표", 3), ("1-2.", "N-N.", "hyphen", "절", 0)]
    _, g, N = _build(rows, {**KNOW, "▸": ["□"]}, main=("N.", "N-N.", "(N)", "o"))
    assert g["llm"]["mainChainFixed"] and N["p4"]["parent"] == "p3" and N["p4"]["heuristic"] and N["p5"]["parent"] == "p0" and N["p5"]["level"] == 2


# ---- ⓑ·ⓒ 템플릿 배정 — 문서 맨 위에 매달린 줄 ---------------------------------------------------------------------------------

def test_top_line_with_a_main_chain_letter_is_that_level():
    """「N.」 없이 문서 맨 위에 온 「5-4.」 — 따로 템플릿(「N-N.›(N)›o」)이 아니라 주 사슬 L2 이고, 그 아래는 L3… 로 이어진다. 인스턴스는 윗 레벨이 빠진 편차."""
    rows = [("5-4.", "N-N.", "hyphen", "장 없이 온 절", 0), ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2),
            ("6.", "N.", "decimal", "장", 0), ("6-1.", "N-N.", "hyphen", "절", 0), ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2),
            ("-", "-", "dash", "줄", 3)]
    _, g, N = _build(rows)
    assert N["p0"]["parent"] == "root" and [(N[p]["template"], N[p]["level"]) for p in ("p0", "p1", "p2")] == [(MAIN, 2), (MAIN, 3), (MAIN, 4)]
    assert [t["anchor"] for t in g["templates"]] == [MAIN] and g["templates"][0]["instances"] == 2
    ins = {i["root"]: i for i in g["instances"]}
    assert ins["p0"]["missing"] == [1, 5] and ins["p0"]["deviates"] and ins["p0"]["members"] == ["p1", "p2"] and ins["p3"]["missing"] == []
    assert g["templates"][0]["where"] == [{"parent": "root", "count": 2}]


def test_longer_chain_under_a_top_line_extends_the_main_chain():
    """레터가 다르지 않고 레벨만 늘어난 사슬 — 문서 맨 위 「5-4.」 아래가 주 사슬보다 한 레벨 더 내려가면(「·」) 따로 템플릿이 아니라 주 사슬이 그만큼 늘어난다."""
    rows = [("1.", "N.", "decimal", "장", 0), ("1-1.", "N-N.", "hyphen", "절", 0), ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2),
            ("-", "-", "dash", "줄", 3),
            ("□", "□", "square", "문서 맨 위 줄", 0),  # root 를 부모로 — 열린 「1.」 이 닫힌다
            ("5-4.", "N-N.", "hyphen", "장을 잃은 절", 0), ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2), ("-", "-", "dash", "줄", 3),
            ("·", "·", "dot", "점", 4)]
    _, g, N = _build(rows, {**KNOW, "□": ["root"], "·": ["-"]})
    long = MAIN + "›·"
    assert N["p6"]["parent"] == "root" and [(N[p]["template"], N[p]["level"]) for p in ("p6", "p7", "p8", "p9", "p10")] == [(long, k) for k in (2, 3, 4, 5, 6)]
    assert (N["p4"]["template"], N["p4"]["level"]) == (long, 5) and [t["anchor"] for t in g["templates"]] == [long, "body:□"]
    assert [(s["level"], s["count"]) for s in g["templates"][0]["slots"]] == [(1, 1), (2, 2), (3, 2), (4, 2), (5, 2), (6, 1)]


def test_without_llm_top_line_follows_the_learned_main_chain():
    """LLM 없이(스크립트 어림)도 같은 규칙 — 배운 주 사슬의 레터가 문서 맨 위에 오면 그 레벨."""
    keys = {"T1": "N.", "T2": "N-N.", "T3": "o"}
    rows = [("a", "T1", "root"), ("a1", "T2", "a"), ("a1o", "T3", "a1"), ("b", "T1", "root"), ("b1", "T2", "b"), ("b1o", "T3", "b1"),
            ("x", "T2", "root"), ("xo", "T3", "x")]  # 「N.」 없이 온 「N-N.」
    nodes = [{"id": i, "para": i, "n": n, "type": t, "fmt": "S1", "text": i, "kind": "marker", "family": "", "shape": keys[t], "letter": keys[t], "outline": None,
              "flow": "body", "lead": 0} for n, (i, t, _) in enumerate(rows)]
    graph = {i: {"id": i, "para": i, "type": t, "parent": p, "role": "heading", "key": keys[t], "division": None} for i, t, p in rows}
    asg = HG.assign_templates(nodes, graph, keys)
    assert [t["anchor"] for t in asg["templates"]] == ["body:N.›N-N.›o"]
    assert (asg["nodes"]["x"]["level"], asg["nodes"]["xo"]["level"]) == (2, 3) and asg["nodes"]["x"]["tplNo"] == 1
    assert [(i["root"], i["missing"]) for i in asg["instances"]] == [("a", []), ("b", []), ("x", [1])]


# ---- ⓓ 레벨 건너뜀 · 그대로인 것(부모 사슬에 없는 레터 · 표 칸) ---------------------------------------------------------------

def test_skipped_level_line_joins_the_parent_template():
    """「1-1.」 바로 아래 「o › -」((N) 을 건너뜀 — 그 문서의 T8) — 레터가 주 사슬의 더 깊은 레벨이면 가지가 아니라 주 사슬 L4·L5(인스턴스는 그 장의 것 · 슬롯 예외 없이)."""
    rows = [("1.", "N.", "decimal", "장", 0), ("1-1.", "N-N.", "hyphen", "절", 0), ("o", "o", "latin-o", "건너뜀", 2), ("-", "-", "dash", "줄", 3),
            ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "보통", 2),
            ("□", "□", "square", "네모", 1), ("o", "o", "latin-o", "네모 아래", 2)]
    _, g, N = _build(rows, {**KNOW, "o": ["(N)", "N-N.", "□"], "□": ["(N)"]})
    assert N["p2"]["parent"] == "p1" and [(N[p]["template"], N[p]["level"]) for p in ("p2", "p3", "p5")] == [(MAIN, 4), (MAIN, 5), (MAIN, 4)]
    assert N["p2"]["instance"] == N["p0"]["instance"] and not N["p2"]["heuristic"]
    # 부모 사슬에 없는 레터(□)는 전처럼 가지 — 그 아래 o 는 그 가지의 L2(□ 사슬의 다음 레터)
    assert N["p6"]["parent"] == "p4" and (N["p6"]["template"], N["p6"]["level"]) == ("body:□›o", 1) and (N["p7"]["template"], N["p7"]["level"]) == ("body:□›o", 2)
    assert [t["anchor"] for t in g["templates"]] == [MAIN, "body:□›o"]
    # 이종 형제 목록에는 그대로 든다(같은 부모 아래 다른 레터 — 「1-1.」 아래 o · (N))
    assert {h["parent"]: sorted(x["key"] for x in h["letters"]) for h in g["heterogeneous"]} == {"p1": ["(N)", "o"], "p4": ["o", "□"]}


def test_shallower_or_same_letter_under_a_line_is_still_a_branch():
    """부모보다 얕은 레터(「(1)」 아래 「N-N.」 꼴)와 바로 위 레벨과 같은 레터(「o」 아래 「o」)는 새 가지 — 레벨 건너뜀은 **더 깊은** 레터만."""
    rows = [("1.", "N.", "decimal", "장", 0), ("1-1.", "N-N.", "hyphen", "절", 0), ("(1)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "동그라미", 2),
            ("o", "o", "latin-o", "동그라미 아래 동그라미", 4)]
    st1 = _stage1(rows)
    A = _a(st1, KNOW, ["N.", "N-N.", "(N)", "o", "-"])
    b = lambda job, d: _res({"changes": [{"id": "p4", "parent": "p3", "role": "heading", "template": "", "level": 0, "reason": "o 아래 o"}], "summary": ""})
    g = HG.build(st1, use_llm=True, ask=fake_ask(heading_types=lambda job, d: _res(A), heading_section=b))
    N = _nodes(g)
    assert N["p4"]["parent"] == "p3" and (N["p4"]["template"], N["p4"]["level"]) == ("body:o", 1)


def test_other_containers_keep_their_top_line_as_a_branch():
    """글상자·각주 같은 다른 그릇(흐름이 본문이 아님)의 맨 위 줄은 주 사슬의 첫 레터가 아니면 전처럼 가지 — 그 그릇의 첫 줄이 주 사슬의 일부라고 볼 근거가 없다."""
    keys = {"T1": "N.", "T2": "N-N.", "T3": "o"}
    rows = [("a", "T1", "root", "body"), ("a1", "T2", "a", "body"), ("ao", "T3", "a1", "body"), ("box", "T3", "area:shape:k1", "shape:k1")]
    nodes = [{"id": i, "para": i, "n": n, "type": t, "fmt": "S1", "text": i, "kind": "marker", "family": "", "shape": keys[t], "letter": keys[t], "outline": None,
              "flow": f, "lead": 0} for n, (i, t, _, f) in enumerate(rows)]
    graph = {i: {"id": i, "para": i, "type": t, "parent": p, "role": "heading", "key": keys[t], "division": None} for i, t, p, _ in rows}
    asg = HG.assign_templates(nodes, graph, keys, ["N.", "N-N.", "o"], True)
    assert (asg["nodes"]["ao"]["template"], asg["nodes"]["ao"]["level"]) == ("body:N.›N-N.›o", 3)
    assert (asg["nodes"]["box"]["template"], asg["nodes"]["box"]["level"]) == ("body:o", 1)


def test_cell_lines_start_their_own_chain():
    """표 칸은 칸마다 레벨 1부터 — 칸 맨 위의 「o」 는 본문 주 사슬의 레터여도 칸 템플릿 L1."""
    keys = {"T1": "N.", "T2": "o"}
    nodes = [{"id": i, "para": i, "n": n, "type": t, "fmt": "S1", "text": i, "kind": "marker", "family": "", "shape": keys[t], "letter": keys[t], "outline": None,
              "flow": f, "lead": 0} for n, (i, t, f) in enumerate([("a", "T1", "body"), ("ao", "T2", "body"), ("c", "T2", "cell:c1")])]
    graph = {"a": {"id": "a", "para": "a", "type": "T1", "parent": "root", "role": "heading", "key": "N.", "division": None},
             "ao": {"id": "ao", "para": "ao", "type": "T2", "parent": "a", "role": "heading", "key": "o", "division": None},
             "c": {"id": "c", "para": "c", "type": "T2", "parent": "cell:c1", "role": "heading", "key": "o", "division": None}}
    asg = HG.assign_templates(nodes, graph, keys)
    assert (asg["nodes"]["c"]["template"], asg["nodes"]["c"]["level"]) == ("cell:o", 1) and asg["nodes"]["ao"]["template"] == "body:N.›o"


# ---- ⓔ 다시 셈 — 옛 앵커의 슬롯 예외 ---------------------------------------------------------------------------------------------

def test_replay_reads_an_old_anchor_as_the_main_chain_level():
    """이 규칙 전의 결과를 다시 셈 — B 가 「N-N.›(N)›o›-」(문서 맨 위 「5-4.」 의 옛 템플릿) L3 으로 적은 슬롯 예외는 주 사슬 L4 로 옮겨 읽는다(버리지 않는다)."""
    rows = [("5.", "N.", "decimal", "장", 0), ("5-4.", "N-N.", "hyphen", "절", 0), ("o", "o", "latin-o", "(1) 없이 온 o", 2),
            ("(2)", "(N)", "paren-num", "괄호", 1), ("o", "o", "latin-o", "보통", 2), ("-", "-", "dash", "줄", 3)]
    st1, g, N = _build(rows, {**KNOW, "o": ["(N)", "N-N."]})
    assert (N["p2"]["template"], N["p2"]["level"]) == (MAIN, 4)  # 새 규칙만으로도 주 사슬 L4(ⓓ) — 옛 결과의 슬롯 예외를 버리지 않는지만 본다
    replay = HG.replay_of(g)
    replay["changes"] = [{"id": "p2", "parent": "p1", "role": "heading", "basis": "", "template": "body:N-N.›(N)›o›-", "level": 3, "reason": "(1) 이 빠진 같은 사슬"}]
    g2 = HG.build(st1, use_llm=False, replay=replay)
    n2 = _nodes(g2)["p2"]
    assert (n2["template"], n2["level"], n2["parent"]) == (MAIN, 4, "p1") and g2["rejected"] == [] and g2["llm"]["applied"] == 1
    assert g2["changes"][0]["asked"]["template"] == MAIN and g2["changes"][0]["asked"]["level"] == 4  # 다음 다시 셈은 옮긴 자리 그대로
    assert HG._refold([{"id": "x", "template": "body:□›o", "level": 2}], g2["templates"]) == [{"id": "x", "template": "body:□›o", "level": 2}]  # 주 사슬 레터가 아니면 그대로(버림은 apply_changes)
    assert HG._refold([{"id": "y", "template": "body:o›·", "level": 2}], g2["templates"]) == [{"id": "y", "template": "body:o›·", "level": 2}]  # 주 사슬의 꼬리와 레터가 어긋남(o › - 가 아님) — 그대로
