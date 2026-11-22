"""구분 기준 자리 표시의 「표 구조」 보탬(spec_구분_기준 ② §25) · 빠진 자리 검토의 일부만 잡힌 표 · 형제 표(② §13 — 2026-11-23).

사용자 문서(작업 51b32f08166c)의 표 「(2) 정량적 목표 항목의 평가방법 및 평가환경」(항목마다 차년도 행 — 1~4 · 3·4 · 4 하나) · 일정 표 「1단계」 머리 · 월별 표 「N차년도(M개월)」 넷을 줄인 꼴."""
from app import division_llm, division_struct as DT
from app.division_profiles.rnd import core


def _cell(cid, row, col, role, text="", rs=1, cs=1, basis=None, kind=None, sub="A"):
    c = {"id": cid, "row": row, "col": col, "rs": rs, "cs": cs, "role": role, "textFull": text, "text": text, "paras": [f"p{cid}"], "sub": sub}
    if basis:
        c.update(basis=basis, basisKind=kind or "value")
    return c


def _eval_table():
    """순번 | 항목 | 구분 | 방법 | 환경 — 항목 1 = 3·4차년도(환경 칸이 두 행에 걸침) · 항목 2 = 1·2차년도(엔진 묶음이 잡았다고 봄) · 항목 3 = 4차년도 하나."""
    Y = ["year"]
    return {"cells": [
        _cell("h0", 0, 0, "corner", "순번"), _cell("h2", 0, 2, "corner", "구분"), _cell("h3", 0, 3, "colhead", "평가방법"), _cell("h4", 0, 4, "colhead", "평가환경"),
        _cell("a0", 1, 0, "rowhead", "1", rs=2), _cell("a2", 1, 2, "rowhead", "3차년도", basis=Y), _cell("a3", 1, 3, "field", "전문가 평가"), _cell("a4", 1, 4, "field", "환경", rs=2),
        _cell("b2", 2, 2, "rowhead", "4차년도", basis=Y), _cell("b3", 2, 3, "field", "전문가 평가"),
        _cell("c2", 3, 2, "rowhead", "1차년도", basis=Y), _cell("c3", 3, 3, "field", "현장"), _cell("c4", 3, 4, "field", "환경2"),
        _cell("d2", 4, 2, "rowhead", "4차년도", basis=Y), _cell("d3", 4, 3, "field", "시험"), _cell("d4", 4, 4, "field", "환경3"),
    ]}


def test_partial_year_rows_get_labels_and_only_whole_scope():
    tb = _eval_table()
    hs = DT.heads(tb)
    assert [(h["cell"], h["dim"], h["num"]) for h in hs] == [("a2", "year", 3), ("b2", "year", 4), ("c2", "year", 1), ("d2", "year", 4)]
    out = DT.table_reads("t1", tb, hs, {"year": {"pc2"}})   # c2(1차년도)는 엔진 묶음의 라벨 — 같은 구분은 다시 그리지 않는다
    labels = [(x["paras"][0], x["value"]) for x in out if x["kind"] == "label"]
    assert labels == [("pa2", "3차년도"), ("pb2", "4차년도"), ("pd2", "4차년도")]
    scope = [(x["value"], sorted(x["paras"])) for x in out if x["kind"] == "scope"]
    assert scope == [("3차년도", ["pa3"]), ("4차년도", ["pb3"]), ("4차년도", ["pd3", "pd4"])]   # 두 행에 걸친 환경 칸(pa4)은 어느 한 차년도의 자리가 아니다(astra P1)
    assert all(x["src"] == "struct" and x["table"] == "t1" and not x["inGroup"] for x in out)


def test_head_text_must_itself_be_a_value():
    Y, S = ["year"], ["stage"]
    tb = {"cells": [_cell("x1", 1, 0, "rowhead", "건", basis=Y), _cell("x2", 2, 0, "rowhead", "1", basis=Y), _cell("x3", 3, 0, "rowhead", "매출액발생 1년차", basis=Y),
                    _cell("x4", 4, 0, "rowhead", "당해연도 개발기간(1단계, 1차년도)", basis=["stage", "year"]), _cell("x5", 5, 0, "rowhead", "N차년도", basis=Y),
                    _cell("y1", 6, 0, "rowhead", "2026 (1차년도)", basis=Y), _cell("y2", 7, 0, "colhead", "3차년도(12개월)", basis=Y),
                    _cell("y3", 8, 0, "rowhead", "1단계 (기반 구축)", basis=S), _cell("y4", 9, 0, "rowhead", "1단계 2차년도", basis=["stage", "year"]),
                    _cell("z1", 10, 0, "field", "3차년도", basis=Y), _cell("z2", 11, 0, "rowhead", "2차년도", basis=Y, kind="name")]}
    got = [(h["cell"], h["dim"], h["num"]) for h in DT.heads(tb)]
    assert got == [("y1", "year", 1), ("y2", "year", 3), ("y3", "stage", 1), ("y4", core.STAGE_YEAR, (1, 2))]


def test_fit_drops_a_dimension_outside_the_project():
    S = ["stage"]
    tb = {"cells": [_cell("s1", 1, 0, "rowhead", "1단계 (기반 구축)", basis=S), _cell("s2", 2, 0, "rowhead", "2단계 (실증)", basis=S),
                    _cell("y1", 0, 1, "colhead", "2차년도", basis=["year"])]}
    hs = DT.fit(DT.heads(tb), [4])   # 과제는 1단계뿐 — 「2단계」 가 있는 단계 머리는 과제의 단계가 아니다(한 칸만 남겨 칠하지 않는다)
    assert [h["cell"] for h in hs] == ["y1"]
    assert [h["cell"] for h in DT.fit(DT.heads(tb), [2, 2])] == ["y1", "s1", "s2"]
    assert [h["cell"] for h in DT.fit(DT.heads(tb), None)] == ["y1", "s1", "s2"]   # 구성을 모르면 그대로


def _month(tid, text, owner="p1", caption=""):
    tb = {"cells": [_cell(f"{tid}a", 0, 0, "colhead", "일련 번호", rs=2), _cell(f"{tid}b", 0, 1, "colhead", text, cs=12, basis=["year"]),
                    *[_cell(f"{tid}m{k}", 1, k, "colhead", str(k)) for k in range(1, 13)], _cell(f"{tid}f", 2, 1, "field", "")]}
    for c in tb["cells"]:
        if c["role"] == "colhead":
            c["shaded"] = True
    t = {"tid": tid, "tb": tb, "owner": {"id": owner, "source": "stage2"} if owner else None, "caption": caption}
    t["hs"] = DT.heads(tb)
    return t


def test_series_same_heading_same_type_one_value_each():
    ts = [_month("t1", "1차년도(9개월)"), _month("t2", "2차년도(12개월)"), _month("t3", "3차년도(12개월)"), _month("t4", "4차년도(12개월)")]
    runs = DT.series(ts)
    assert [[x["tid"] for x in r] for r in runs] == [["t1", "t2", "t3", "t4"]]
    out = DT.series_reads(runs, {"t1": ["a", "b"], "t2": ["c"], "t3": [], "t4": ["d"]})
    assert [(x["table"], x["kind"], x["src"], x["dim"], x["value"]) for x in out] == [
        ("t1", "table", "series", "year", "1차년도(9개월)"), ("t2", "table", "series", "year", "2차년도(12개월)"), ("t4", "table", "series", "year", "4차년도(12개월)")]


def test_series_breaks():
    a, b = _month("t1", "1차년도(9개월)"), _month("t2", "2차년도(12개월)")
    assert DT.series([a, _month("t2", "2차년도(12개월)", owner="p9")]) == []                       # 다른 헤딩
    assert DT.series([a, _month("t2", "2차년도(12개월)", owner=None)]) == []                       # 소속 헤딩을 모름
    assert DT.series([_month("t1", "2차년도"), _month("t2", "1차년도")]) == []                       # 차례가 거꾸로
    assert DT.series([a, _month("t2", "1차년도(12개월)")]) == []                                     # 같은 값
    assert DT.series([_month("t1", "1차년도", caption="<위탁비 집행계획 1>"), _month("t2", "2차년도", caption="<장비비 집행실적 2>")]) == []   # 용도가 다른 같은 꼴 표(astra 반례)
    order = {"t1": 1, "h": 2, "t2": 3}
    assert DT.series([a, b], levels={"h": 2}, order=order) == []                                    # 사이에 헤딩 줄
    assert len(DT.series([a, b], levels={"x": 2}, order={**order, "x": 9})) == 1


def _tbl(tid, rows):
    cells = [{"id": f"{tid}_{r}_{c}", "row": r, "col": c, "text": t, "blocks": [{"type": "paragraph", "id": f"p{tid}_{r}_{c}", "text": t}]}
             for r, row in enumerate(rows) for c, t in enumerate(row)]
    return {"type": "table", "id": tid, "nRows": len(rows), "nCols": len(rows[0]), "cells": cells}


def test_missing_data_keeps_partly_grouped_table_and_siblings():
    head = {"type": "paragraph", "id": "h1", "text": "2-3. 연구개발과제 수행일정"}
    ev = _tbl("t1", [["구분", "평가방법"], ["1차년도", "현장"], ["2차년도", "현장"], ["3차년도", "평가"], ["4차년도", "평가"]])
    m1 = _tbl("m1", [["개발 내용", "1차년도(9개월)"], ["가", ""]])
    m2 = _tbl("m2", [["개발 내용", "2차년도(12개월)"], ["가", ""]])
    blocks = [head, ev, m1, m2]
    group = {"table": "t1", "dim": "year", "kind": "rows", "items": [{"label": "t1_1_0", "scope": ["t1_1_0", "t1_1_1"], "labelText": "1차년도"},
                                                                    {"label": "t1_2_0", "scope": ["t1_2_0", "t1_2_1"], "labelText": "2차년도"}]}
    p = division_llm.missing_data(blocks, {"h1": 1}, {"stages": [4], "orgs": {}}, [group], lambda d, v: str(v))
    by = {t["id"]: t for t in p["tables"]}
    assert by["t1"]["partial"] is True and [x["text"] for x in by["t1"]["rest"]] == ["3차년도", "4차년도"]   # 묶음이 일부만 잡은 표 — 남은 값 칸
    assert by["m1"]["siblings"] == ["m2"] and by["m2"]["siblings"] == ["m1"]                              # 같은 헤딩 아래 같은 꼴 표(숫자만 다름)
    full = dict(group, items=group["items"] + [{"label": "t1_3_0", "scope": ["t1_3_0", "t1_3_1"]}, {"label": "t1_4_0", "scope": ["t1_4_0", "t1_4_1"]}])
    p2 = division_llm.missing_data(blocks, {"h1": 1}, {"stages": [4], "orgs": {}}, [full], lambda d, v: str(v))
    assert "t1" not in {t["id"] for t in p2["tables"]}   # 묶음이 다 잡은 표는 그대로 뺀다
    assert "partial" in division_llm.MISSING_CONTRACT and "siblings" in division_llm.MISSING_CONTRACT and "1단계" in division_llm.MISSING_CONTRACT
