"""자리마다의 작성 지침(spec_병합 ② §5-11 — app/place_guides.py): 가장 안쪽 3단계 표 · 칸 · 미연결 · 헤딩 · 사람 지침 · 자르기 · 판 · 묶음의 공통 지침.
astra 협의(artifacts/stage3_guides_astra_2026-11-23)의 음성 시험: 형제 표 · 겉표 옆 ※ · 다른 차년도 · 다른 기관 절에 지침이 새지 않는다."""
from app import form_guides as FG
from app import place_guides as PG


def _p(pid, text=""):
    return {"id": pid, "type": "paragraph", "text": text}


def _t(tid, cells):
    """cells = [(칸 id, 행, 열, [블록…])]"""
    return {"id": tid, "type": "table", "cells": [{"id": c, "row": r, "col": k, "blocks": bs, "text": ""} for c, r, k, bs in cells]}


def _blocks():
    inner = _t("t3", [("c31", 0, 0, [_p("p31", "보안등급1)")]), ("c32", 1, 0, [_p("p32", "과제명")])])   # 겉표 t1 안의 3단계 표
    twin_a = _t("t5", [("c51", 0, 0, [_p("p51")])])
    twin_b = _t("t6", [("c61", 0, 0, [_p("p61")])])
    return [
        _p("h1", "1. 표지"),
        _t("t1", [("c11", 0, 0, [_p("p11", "겉표 칸의 ※ 안내"), inner])]),   # 겉표 — 안쪽 3단계 표 하나
        _p("n1", "※ 겉표 옆 안내"),
        _p("h2", "2. 형제 표"),
        _t("t4", [("c41", 0, 0, [_p("p41", "겉표 칸의 ※"), twin_a, twin_b])]),   # 겉표 — 안쪽 3단계 표 둘
        _p("h3", "3. 본문"),
        _p("n3", "※ 본문 안내"),
        _t("t7", [("c71", 0, 0, [_p("p71")])]),   # 3단계 표(최상위)
    ]


T3 = ["t3", "t5", "t6", "t7"]


def _saved():
    item = lambda iid, text, head=None, table=None, top=0: {"id": iid, "kind": "notes", "name": "※ 안내", "text": text,  # noqa: E731
                                                          "heading": {"id": head, "text": head} if head else None, "table": {"id": table, "label": table} if table else None, "top": top}
    return {"items": [item("p11", "겉표 칸의 안내", "h1", "t1", 1),        # 겉표 칸에 바로 — 안쪽 3단계 표가 하나라 t3(칸은 안 붙임)
                      item("n1", "겉표 옆 ※", "h1", "t1", 2),             # 본문 ※ 이 3단계 표가 아닌 겉표에 붙음 — 미연결
                      item("p41", "형제 겉표 칸의 ※", "h2", "t4", 4),      # 겉표 칸에 바로 — 안쪽 3단계 표 둘: 미연결(헤딩으로도 안 넘김)
                      item("n3", "본문 안내", "h3", None, 6),              # 표 없음 — 헤딩의 것
                      item("n7", "표 바로 앞 ※", "h3", "t7", 6)],          # 본문 ※ 이 3단계 표에 붙음 — 그 표
            "marks": [{"no": "1", "at": "p31", "label": "보안등급1)", "heading": {"id": "h1", "text": "1. 표지"}, "table": {"id": "t1", "label": "t1"}, "guide": "g", "text": "1. 보안등급: …", "top": 1},
                      {"no": "2", "at": "p32", "label": "과제명2)", "heading": None, "table": None, "guide": None, "text": "", "top": 1}]}   # 글 없는 각주는 싣지 않는다


def test_index_puts_each_guide_on_the_innermost_table_or_leaves_it_loose():
    ix = PG.index(_saved(), _blocks(), T3)
    t3 = ix["tables"]["t3"]
    assert [(g["text"], g.get("cell")) for g in t3] == [("겉표 칸의 안내", None), ("1. 보안등급: …", "r0c0")]   # 겉표 칸 → 안쪽 표(칸 없음) · 안쪽 표 칸의 각주 → 그 칸
    assert t3[1]["kind"] == "각주 번호 1)" and t3[1]["label"] == "보안등급1)"
    assert "t1" not in ix["tables"] and "t4" not in ix["tables"] and "t5" not in ix["tables"] and "t6" not in ix["tables"]   # 겉표 · 형제 표에는 아무것도 안 붙는다
    assert [g["text"] for g in ix["tables"]["t7"]] == ["표 바로 앞 ※"]
    assert [g["text"] for g in ix["heads"]["h3"]] == ["본문 안내"] and "h1" not in ix["heads"] and "h2" not in ix["heads"]   # 미연결은 헤딩으로도 넘기지 않는다
    assert ix["loose"] == 2   # 겉표 옆 ※ · 형제 겉표 칸의 ※


def test_user_guides_come_first_and_tables_take_the_table_agent_text():
    ix = PG.index(_saved(), _blocks(), T3, user={"heads": {"h3": {"text": "실적만 쓴다", "label": "3. 본문"}}}, table_user={"t7": "해당 연도 행만", "t5": ""})
    assert [(g["src"], g["text"]) for g in ix["heads"]["h3"]] == [("user", "실적만 쓴다"), ("doc", "본문 안내")]
    assert [(g["src"], g["kind"]) for g in ix["tables"]["t7"]] == [("user", PG.KIND_TABLE_USER), ("doc", "※ 안내")] and "t5" not in ix["tables"]


def test_for_table_adds_only_its_own_heading_body_guides():
    blocks = _blocks()
    ix = PG.index(_saved(), blocks, T3)
    graph = {"nodes": [{"para": h, "role": "heading", "area": "body"} for h in ("h1", "h2", "h3")]}
    place = PG.resolver(ix, blocks, graph)
    assert [g["text"] for g in place("table", "t7")] == ["표 바로 앞 ※", "본문 안내"]   # 그 표 → 그 표가 든 헤딩의 본문 지침
    assert [g["text"] for g in place("table", "t5")] == []   # 형제 겉표의 지침은 안 받는다(h2 에 붙은 것도 없다)
    assert [g["text"] for g in place("block", "p71")] == ["표 바로 앞 ※", "본문 안내"]   # 표 칸 안 블록 = 그 표
    assert [g["text"] for g in place("block", "n3")] == ["본문 안내"]


def test_group_guides_are_the_ones_every_item_shares():
    blocks = [_p("h1", "[1차년도]"), _p("a1"), _p("h2", "[2차년도]"), _p("a2")]
    graph = {"nodes": [{"para": h, "role": "heading", "area": "body"} for h in ("h1", "h2")]}
    common = {"id": "x", "kind": "notes", "name": "※ 안내", "text": "공통 안내", "top": 0}
    saved = {"items": [{**common, "id": "x1", "heading": {"id": "h1"}, "table": None}, {**common, "id": "x2", "heading": {"id": "h2"}, "table": None},
                       {"id": "y", "kind": "notes", "name": "※ 안내", "text": "1차년도만", "heading": {"id": "h1"}, "table": None, "top": 0}], "marks": []}
    place = PG.resolver(PG.index(saved, blocks, []), blocks, graph)
    group = {"key": "g", "items": [{"id": "h1"}, {"id": "h2"}]}
    assert [g["text"] for g in place("group", group)] == ["공통 안내"]   # 한 차년도만의 지침은 다른 차년도 항목에 새지 않는다
    assert [g["text"] for g in place("group", {"key": "g1", "items": [{"id": "h1"}]})] == ["공통 안내", "1차년도만"]


def test_pack_dedupes_keeps_cells_apart_and_cuts_by_length():
    a = {"src": "doc", "kind": "각주 번호 1)", "text": "같은 항목", "label": "칸1", "cell": "r0c0"}
    b = {**a, "cell": "r1c0", "label": "칸2"}
    got, cut = PG.pack([a, a, b])
    assert got == [a, b] and cut == 0   # 같은 번호 · 같은 글이라도 다른 칸이면 따로
    big = [{"src": "doc", "kind": "k", "text": "가" * 1500} for _ in range(4)]
    for i, g in enumerate(big):
        g["text"] += str(i)
    got, cut = PG.pack(big, limit=4000)
    assert len(got) == 2 and cut == 2


def test_a_section_guide_reaches_the_places_under_it_but_not_a_sibling_section():
    """2026-11-24 — 장 · 절 제목의 지침은 그 아래 하위 제목 · 표에도 닿는다(그래프의 조상만 — 형제 절로는 안 간다) · 글 없는 글머리 줄은 헤딩으로 세지 않는다."""
    blocks = [_p("h1", "5. 다음 연도 계획"), _p("h11", "5-1 목표"), _p("b0", "o"), _t("t1", [("c1", 0, 0, [_p("p1")])]), _p("h2", "6. 보안"), _t("t2", [("c2", 0, 0, [_p("p2")])])]
    node = lambda pid, parent=None, **kw: {"id": pid, "role": "heading", "area": "body", "para": pid, "parent": parent, **kw}  # noqa: E731
    graph = {"nodes": [node("h1"), node("h11", "h1"), node("b0", "h11", blank=True), node("h2")]}
    item = lambda iid, text, head: {"id": iid, "kind": "notes", "name": "※ 안내", "text": text, "heading": {"id": head}, "table": None, "top": 0}  # noqa: E731
    ix = PG.index({"items": [item("x", "※ 다음연도 내용만 작성", "h1"), item("y", "변경 시 작성", "h11"), item("z", "기관별 작성", "h2")], "marks": []}, blocks, ["t1", "t2"])
    place = PG.resolver(ix, blocks, graph)
    assert [g["text"] for g in place("table", "t1")] == ["변경 시 작성", "※ 다음연도 내용만 작성"]   # 제 절의 것이 먼저 → 윗 절의 것(빈 글머리 줄 b0 은 건너뜀)
    assert [g["text"] for g in place("block", "h11")] == ["변경 시 작성", "※ 다음연도 내용만 작성"]
    assert [g["text"] for g in place("table", "t2")] == ["기관별 작성"]   # 형제 절(5.)의 지침은 안 온다
    assert PG.ancestors(graph) == {"h1": [], "h11": ["h1"], "h2": []}


def test_table_structure_is_a_guide_for_the_llm_but_not_part_of_the_sig():
    """2026-11-24 — 표 구조(1단계 판정의 요약 · 단위 · 칸의 괄호 안내)를 그 표의 지침 하나로 싣는다 · 판에는 안 든다(표 자체에서 읽은 것)."""
    cell = lambda cid, r, c, text: {"id": cid, "row": r, "col": c, "text": text, "blocks": [_p("p" + cid, text)]}  # noqa: E731
    table = {"id": "t1", "type": "table", "cells": [cell("a", 0, 0, "연구개발비(천원)"), cell("b", 0, 1, "기간 (YY.MM.DD)"), cell("c", 1, 0, "홍길동(연구원)"), cell("d", 1, 1, "과제 수행 중 (해당 시 작성) 하는 아주 긴 문장으로 된 본문 칸의 글입니다 — 머리글이 아닙니다")]}
    t3 = [{"id": "t1", "llm": {"summary": "기관별 연구개발비를 적는 매트릭스입니다."}, "unit": "천원"}, {"id": "t2"}]
    st = PG.struct([table], t3)
    assert list(st) == ["t1"] and st["t1"]["src"] == "struct" and st["t1"]["kind"] == PG.KIND_STRUCT
    assert st["t1"]["text"] == "기관별 연구개발비를 적는 매트릭스입니다. / 단위: 천원 / 칸의 꼴: 연구개발비(천원) · 기간 (YY.MM.DD)"   # 이름 괄호(「(연구원)」) · 긴 본문 칸은 칸의 꼴이 아니다
    ix = PG.index({"items": [], "marks": []}, [table], ["t1"], t3_tables=t3)
    got = PG.for_table(ix, "t1")[0]
    assert [g["kind"] for g in got] == [PG.KIND_STRUCT] and "t1" not in ix["tables"]   # LLM 에 싣는 목록에만 — 화면의 수(tables)에는 안 든다
    assert PG.sig(got) == "" and PG.sig([{"src": "doc", "kind": "k", "text": "A"}, *got]) == PG.sig([{"src": "doc", "kind": "k", "text": "A"}])


def test_budget_counts_a_repeated_guide_once():
    """2026-11-24 — 같은 지침이 한 호출의 여러 자리(표 · 그 안의 묶음)에 되풀이되면 한 번만 센다(되풀이가 다른 자리의 지침을 밀어내지 않게)."""
    same = lambda: [{"src": "doc", "kind": "k", "text": "가" * 300}]  # noqa: E731
    places = [{"key": "t", "guides": same()}, {"key": "g1", "guides": same()}, {"key": "g2", "guides": same()}, {"key": "u", "guides": [{"src": "doc", "kind": "k", "text": "나" * 300}]}]
    assert PG.budget(places, limit=700) == 0 and all(p.get("guides") for p in places)   # 300 × 3 은 한 번만 세어 600
    assert PG.budget(places, limit=500) == 1 and "guides" not in places[3] and places[3]["guidesCut"] == 1   # 넘치면 뒤 자리부터


def test_sig_changes_with_the_guides_and_budget_trims_from_the_end():
    g1 = [{"src": "doc", "kind": "k", "text": "A"}]
    assert PG.sig([]) == "" and PG.sig(g1) == PG.sig([dict(g1[0])]) and PG.sig(g1) != PG.sig([{**g1[0], "text": "B"}]) and PG.sig(g1) != PG.sig([{**g1[0], "src": "user"}])
    places = [{"key": "a", "guides": [{"text": "x" * 5000}]}, {"key": "b", "guides": [{"text": "y" * 5000}, {"text": "z" * 5000}]}]
    assert PG.budget(places, limit=12000) == 1 and places[1]["guidesCut"] == 1 and len(places[1]["guides"]) == 1 and len(places[0]["guides"]) == 1


def test_user_put_writes_and_clears():
    d = PG.user_put(None, "h1", "  적은 지침 \r\n 둘째 줄 ", "1. 표지", 5.0)
    assert d == {"version": 1, "heads": {"h1": {"text": "적은 지침 \n 둘째 줄", "label": "1. 표지", "at": 5.0}}}
    assert PG.user_put(d, "h1", "  ") == {"version": 2, "heads": {}}
    import pytest
    with pytest.raises(ValueError, match="4,000자"):
        PG.user_put(d, "h1", "가" * 4001)


def test_keep_old_keeps_deleted_guides_but_not_recreated_ones():
    old = {"items": [{"id": "n1", "kind": "notes", "text": "지운 안내", "top": 1}, {"id": "n2", "kind": "notes", "text": "남은 안내", "top": 2}],
           "marks": [{"at": "p1", "no": "3", "guide": "g", "text": "3. 항목", "top": 0}]}
    new = {"counts": {}, "items": [{"id": "n2", "kind": "notes", "text": "남은 안내(고침)", "top": 2}, {"id": "n9", "kind": "notes", "text": "다시 만든 안내", "top": 3}], "marks": []}
    old["items"].append({"id": "n8", "kind": "notes", "text": "다시 만든 안내", "top": 3})   # 지우고 다시 만든 블록(새 id · 같은 글) — 겹치지 않게
    got = FG.keep_old(new, old)
    assert [(x["id"], x["text"]) for x in got["items"]] == [("n1", "지운 안내"), ("n2", "남은 안내(고침)"), ("n9", "다시 만든 안내")]   # 같은 열쇠는 새 값 · 사라진 것만 옛 값
    assert [m["no"] for m in got["marks"]] == ["3"] and got["counts"]["items"] == 3 and got["counts"]["marks"] == 1
    assert FG.keep_old(new, None) is new


def test_a_cell_label_in_a_group_gets_its_table_guides_and_the_nearest_table_stops_the_walk():
    """묶음의 항목 라벨이 표 칸이면 그 표의 지침도(「block」 과 같은 해석) · 지침 없는 안쪽 3단계 표는 겉표로 올라가지 않는다(astra 3차)."""
    inner = _t("t9", [("c91", 0, 0, [_p("p91", "칸 라벨")])])
    blocks = [_p("h1", "1. 절"), _t("t8", [("c81", 0, 0, [_p("p81", "겉표 칸"), inner])])]
    graph = {"nodes": [{"para": "h1", "role": "heading", "area": "body"}]}
    saved = {"items": [{"id": "p81", "kind": "notes", "name": "※ 안내", "text": "겉표 안내", "heading": {"id": "h1"}, "table": {"id": "t8"}, "top": 1}], "marks": []}
    ix = PG.index(saved, blocks, ["t8", "t9"])
    place = PG.resolver(ix, blocks, graph)
    assert [g["text"] for g in place("table", "t8")] == ["겉표 안내"]
    assert place("block", "p91") == [] and place("group", {"key": "g", "items": [{"id": "p91"}]}) == []   # 안쪽 표 t9 에서 멈춘다 — 겉표 t8 의 지침이 새지 않는다
    assert [g["text"] for g in place("group", {"key": "g", "items": [{"id": "p81"}]})] == ["겉표 안내"]   # 칸 라벨 = 그 표의 지침


def test_a_guide_whose_block_was_deleted_keeps_the_place_it_had_and_same_text_elsewhere_is_kept():
    """지침 블록이 지워져도 모은 때 정한 자리(`place`)로 읽는다 · 다른 헤딩의 같은 글은 지운 지침을 삼키지 않는다(astra 3차)."""
    saved = {"items": [], "marks": [{"no": "1", "at": "gone", "label": "보안등급1)", "heading": None, "table": {"id": "t1"}, "guide": "g", "text": "1. 보안등급", "top": 1,
                                     "place": {"table": "t3", "cell": "r0c0"}}]}
    ix = PG.index(saved, _blocks(), T3)
    assert [(g["text"], g.get("cell")) for g in ix["tables"]["t3"]] == [("1. 보안등급", "r0c0")] and ix["loose"] == 0
    old = {"items": [{"id": "a", "kind": "notes", "text": "※ 당해 연도만", "heading": {"id": "H1"}, "top": 1}], "marks": []}
    new = {"counts": {}, "items": [{"id": "b", "kind": "notes", "text": "※ 당해 연도만", "heading": {"id": "H2"}, "top": 2}], "marks": []}
    assert [x["id"] for x in FG.keep_old(new, old)["items"]] == ["a", "b"]


def test_collect_writes_the_resolved_place_of_table_guides():
    """모을 때 지침마다 가장 안쪽 3단계 표 · 칸을 적는다(form_guides._places_of) — 3단계 결과가 없으면 안 적는다."""
    items = [{"id": "p11", "table": {"id": "t1"}}, {"id": "n1", "table": {"id": "t1"}}, {"id": "n3", "table": None}]
    marks = [{"at": "p31", "table": {"id": "t1"}}]
    FG._places_of(_blocks(), {"tables": [{"id": t} for t in T3]}, items, marks)
    assert [x.get("place") for x in items] == [{"table": "t3"}, {"loose": True}, None] and marks[0]["place"] == {"table": "t3", "cell": "r0c0"}
    bare = [{"id": "p11", "table": {"id": "t1"}}]
    FG._places_of(_blocks(), None, bare, [])
    assert "place" not in bare[0]
