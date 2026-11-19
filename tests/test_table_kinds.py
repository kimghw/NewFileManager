"""표(띠)의 병합 방식 식별 — 순수 계산(app/table_kinds.py)과 끝점(app/table_kinds_api.py): spec_테이블매니저 ② §5 「병합 방식」.
방식 넷(기관마다 작성 · 구분 기준에 따라 병합 · 셀 값 합산 · 공통) + 섞임을 합성 표로, 편집 구역(zone_of)이 있을 때와 없을 때의 `sure`, 기관을 못 읽은 구역은 한 기관으로 안 침,
끝점의 관문(일반 문서) · 3단계 없음 404 · 견본 양식의 3단계(스크립트) 뒤 응답 꼴과 counts 합 = 표 수 · 프로젝트 구성 값이 있을 때 편집 구역이 근거가 됨."""
import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs as HR
from app import server
from app import table_kinds as TK

PLAN = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
SUB_KEYS = {"sub", "kind", "basis", "axes", "orgs", "why", "sure", "by"}
BANNED = ("공백", "갈래", "라벨")   # 화면 글에 쓰지 않는 말(CLAUDE.md 용어) — why 는 화면에 보인다


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


# ---- 합성 표(3단계 결과 꼴 — 쓰는 키만) -----------------------------------------------------------------------------------

def H(i, row, col, text, role="colhead", basis=None, kind=None, sub="A", **kw):
    """머리 칸 — basis · kind(name|value|total|ratio) = 3단계의 basis · basisKind."""
    x = {"id": i, "row": row, "col": col, "rs": 1, "cs": 1, "role": role, "text": text, "sub": sub, **kw}
    if basis:
        x.update(basis=list(basis), basisKind=kind)
    return x


def F(i, row, col, text="", num=None, sub="A", **kw):
    x = {"id": i, "row": row, "col": col, "rs": 1, "cs": 1, "role": "field", "text": text, "sub": sub, **kw}
    if num is not None:
        x["num"] = num
    return x


def band(i="A", kind="matrix", calc=False, why="합계 헤더"):
    return {"id": i, "kind": kind, "calc": {"is": calc, "why": why if calc else ""}, "signature": f"sig-{i}"}


def table(cells, bands=None, **kw):
    return {"id": "t1", "depth": 1, "parentCell": None, "before": "", "owner": None, "labels": [], "cells": cells, "subtables": bands or [band()], **kw}


def plain():
    """머리 행 「항목 | 내용」 + 값 행 둘 — 구분 기준도 합계도 없다."""
    return [H("h1", 0, 0, "항목"), H("h2", 0, 1, "내용"), F("a1", 1, 0, "가"), F("a2", 1, 1, "나"), F("b1", 2, 0, "다"), F("b2", 2, 1, "라")]


def org_rows():
    """머리 행 「구분 | 예산」 + 행헤더 「주관연구개발기관」·「공동연구개발기관1」(기관 값 머리 둘)."""
    return [H("c", 0, 0, "구분", "corner"), H("h", 0, 1, "예산"),
            H("r1", 1, 0, "주관연구개발기관", "rowhead", ["org"], "value"), F("f1", 1, 1, "100", 100.0),
            H("r2", 2, 0, "공동연구개발기관1", "rowhead", ["org"], "value"), F("f2", 2, 1, "200", 200.0)]


def one(t, zone_of=None, repeats=None):
    r = TK.kinds(t, zone_of, repeats)
    assert set(r) == {"table", "kind", "subs"} and r["table"] == t["id"]
    for s in r["subs"]:
        assert set(s) == SUB_KEYS and s["kind"] in TK.KINDS and isinstance(s["sure"], bool) and s["why"] and not any(w in s["why"] for w in BANNED), s
        assert all(set(a) == {"basis", "on", "values"} and a["basis"] in TK.DIMS and a["on"] in ("row", "col") for a in s["axes"]), s
        assert set(s["basis"]) >= {a["basis"] for a in s["axes"]}
    return r


def zone(labels, whole=None):
    """zone_of — labels = {id: 귀속}. whole(표 id → 귀속)이 있으면 실리지 않은 id 는 그 표의 것(편집 구역이 아는 표의 칸), 없으면 None(모르는 id)."""
    blank = {"org": None, "orgKind": None, "year": None, "stage": None}

    def zone_of(i):
        if i in labels:
            return {**blank, **labels[i]}
        return {**blank, **whole} if whole is not None else None
    return zone_of


def org(name):
    return {"org": name, "orgKind": "org", "orgName": name}


# ---- 머리글의 꼴만(편집 구역 없음 — sure 는 모두 False) -------------------------------------------------------------------

def test_per_org_under_an_org_division_line():
    t = table(plain(), owner={"text": "가. 인적사항", "path": [], "division": {"text": "[공동연구개발기관1(가나대)]", "basis": ["org"]}})
    r = one(t)
    assert r["kind"] == "perOrg" and [(s["kind"], s["by"], s["sure"], s["basis"], s["orgs"]) for s in r["subs"]] == [("perOrg", "owner", False, ["org"], 0)]
    assert "[공동연구개발기관1(가나대)]" in r["subs"][0]["why"]
    stage_only = table(plain(), owner={"text": "x", "division": {"text": "[1단계]", "basis": ["stage"]}})
    assert one(stage_only)["kind"] == "common"                      # 단계 구분 줄 아래의 표는 한 기관의 표가 아니다


def test_by_division_org_rows_columns_and_name_column():
    r = one(table(org_rows()))
    s = r["subs"][0]
    assert (r["kind"], s["by"], s["sure"], s["orgs"]) == ("byDivision", "heads", False, 2) and s["axes"] == [{"basis": "org", "on": "row", "values": 2}]
    assert s["why"].startswith("기관 행 2 — 주관연구개발기관 · 공동연구개발기관1")
    cols = [H("c", 0, 0, "구분", "corner"), H("o1", 0, 1, "주관연구개발기관", "colhead", ["org"], "value"), H("o2", 0, 2, "공동연구개발기관", "colhead", ["org"], "value"),
            H("r", 1, 0, "담당", "rowhead"), F("f1", 1, 1), F("f2", 1, 2)]
    s = one(table(cols))["subs"][0]
    assert s["kind"] == "byDivision" and s["axes"] == [{"basis": "org", "on": "col", "values": 2}] and s["why"].startswith("기관 열 2")
    named = [H("h1", 0, 0, "기관명", "colhead", ["org"], "name"), H("h2", 0, 1, "역할"), F("a1", 1, 0), F("a2", 1, 1), F("b1", 2, 0), F("b2", 2, 1)]
    s = one(table(named))["subs"][0]                                # 「기관명」 열 — 값은 그 아래 행마다(몇 기관인지는 모른다)
    assert (s["kind"], s["by"], s["orgs"]) == ("byDivision", "heads", 0) and s["axes"] == [{"basis": "org", "on": "row", "values": 0}] and "머리글 「기관명」" in s["why"]
    single = [H("r1", 0, 0, "주관연구개발기관", "rowhead", ["org"], "value"), F("f1", 0, 1, "인텍"), H("r2", 1, 0, "연구책임자", "rowhead"), F("f2", 1, 1, "홍길동")]
    assert one(table(single, [band(kind="form")]))["kind"] == "common"   # 값 머리 하나(주관이 누구인지 적는 칸)는 기관 행이 아니다


def test_sum_needs_totals_and_comes_before_year_columns():
    money = [H("c", 0, 0, "비목", "corner"), H("y1", 0, 1, "1차년도", "colhead", ["year"], "value"), H("y2", 0, 2, "2차년도", "colhead", ["year"], "value"),
             H("tt", 0, 3, "합계", "colhead", ["total"], "total"),
             H("r1", 1, 0, "인건비", "rowhead"), F("a1", 1, 1, "10", 10.0), F("a2", 1, 2, "20", 20.0), F("a3", 1, 3, "30", 30.0, formulas=["f0"]),
             H("r2", 2, 0, "재료비", "rowhead"), F("b1", 2, 1, "1", 1.0), F("b2", 2, 2, "2", 2.0), F("b3", 2, 3, "3", 3.0, formulas=["f1"])]
    r = one(table(money, [band(calc=True, why="합계 헤더 · 숫자 필드 6")]))
    s = r["subs"][0]
    assert (r["kind"], s["by"], s["sure"]) == ("sum", "calc", False) and s["axes"] == [{"basis": "year", "on": "col", "values": 2}] and s["basis"] == ["year"]
    assert s["why"] == "합계 헤더 · 숫자 필드 6 · 기관 행·열 없음 · 차년도 열 2(1차년도 · 2차년도)"   # 차년도 열이 있어도 공통 숫자 표는 합산
    blank = [{k: v for k, v in x.items() if k not in ("num", "formulas")} | ({"text": ""} if x["role"] == "field" else {}) for x in money]
    s = one(table(blank, [band(calc=True, why="합계 헤더")]))["subs"][0]   # 빈 양식 — 수는 아직 없어도 채울 칸이 있다
    assert s["kind"] == "sum" and s["why"] == "합계 헤더 · 채울 칸 6 · 기관 행·열 없음 · 차년도 열 2(1차년도 · 2차년도)"
    no_total = [x for x in money if x["id"] not in ("tt", "a3", "b3")]
    s = one(table(no_total, [band(calc=True, why="숫자 필드 4")]))["subs"][0]   # 숫자 필드가 여럿일 뿐 — 합산이 아니다. 차년도 열이 있으니 구분 기준에 따라 병합
    assert (s["kind"], s["by"]) == ("byDivision", "heads") and s["why"] == "차년도 열 2(1차년도 · 2차년도) · 기관 행·열 없음"
    numbers = [H("h1", 0, 0, "항목"), H("h2", 0, 1, "값"), F("a1", 1, 0, "1", 1.0), F("a2", 1, 1, "2", 2.0), F("b1", 2, 0, "3", 3.0), F("b2", 2, 1, "4", 4.0)]
    assert one(table(numbers, [band(calc=True, why="숫자 필드 4")]))["kind"] == "common"
    with_org = org_rows() + [H("tt", 3, 0, "합계", "rowhead", ["total"], "total"), F("f3", 3, 1, "300", 300.0, formulas=["f0"])]
    assert one(table(with_org, [band(calc=True)]))["kind"] == "byDivision"   # 기관 행 + 합계 행 = 구분 기준에 따라 병합(기관이 먼저)


def test_year_and_stage_need_two_values():
    two = [H("c", 0, 0, "구분", "corner"), H("h", 0, 1, "내용"),
           H("r1", 1, 0, "1단계-1차년도", "rowhead", ["stage", "year"], "value"), F("f1", 1, 1, "가"),
           H("r2", 2, 0, "1단계-2차년도", "rowhead", ["stage", "year"], "value"), F("f2", 2, 1, "나")]
    s = one(table(two))["subs"][0]                                  # 차년도 둘 · 단계는 하나(「1단계」) — 단계 행은 없다
    assert (s["kind"], s["by"], s["basis"]) == ("byDivision", "heads", ["year"]) and s["axes"] == [{"basis": "year", "on": "row", "values": 2}]
    one_year = [H("h1", 0, 0, "개발 내용"), H("h2", 0, 1, "1단계-1차년도(개월)", "colhead", ["stage", "year"], "value"), F("a1", 1, 0, "가"), F("a2", 1, 1, "")]
    assert one(table(one_year))["kind"] == "common"                  # 값 하나 = 그 표의 차년도를 적은 머리(갈린 것이 아니다)
    name_only = [H("h1", 0, 0, "발표연도", "colhead", ["year"], "name"), H("h2", 0, 1, "논문명"), F("a1", 1, 0, "2024"), F("a2", 1, 1, "가")]
    assert one(table(name_only))["kind"] == "common"                 # 이름 머리 「연도」 는 과제의 차년도가 아니다
    stages = [H("s1", 0, 0, "1단계", "colhead", ["stage"], "value"), H("s2", 0, 1, "2단계", "colhead", ["stage"], "value"), F("a1", 1, 0), F("a2", 1, 1)]
    s = one(table(stages))["subs"][0]
    assert s["kind"] == "byDivision" and s["axes"] == [{"basis": "stage", "on": "col", "values": 2}] and s["why"] == "단계 열 2(1단계 · 2단계) · 기관 행·열 없음"


def calendar(*years, side="colhead"):
    """「구분 | 2024 | 2025 …」(side = rowhead 면 연도가 행마다) — 연도 값 머리(3단계의 basis period)와 그 값 칸."""
    col = side == "colhead"
    out = [H("c", 0, 0, "구분", "corner"), H("k", 1, 0, "실적", "rowhead") if col else H("k", 0, 1, "실적")]
    for i, y in enumerate(years, 1):
        out += [H(f"p{i}", 0 if col else i, i if col else 0, y, side, ["period"], "value"), F(f"v{i}", 1 if col else i, i if col else 1, "가")]
    return out


def test_calendar_year_columns_are_a_division_when_two_or_more():
    """연도 열도 구분 기준으로(2026-11-19 사용자 답 「일단 하고 추가로 수정할게」) — 차년도 · 단계와 같은 조건: 값 머리 둘 이상 · 기관 근거와 셀 값 합산이 먼저 · 근거는 머리글의 꼴뿐."""
    s = one(table(calendar("2024", "2025년")))["subs"][0]
    assert (s["kind"], s["by"], s["sure"], s["basis"], s["orgs"]) == ("byDivision", "heads", False, ["period"], 0)
    assert s["axes"] == [{"basis": "period", "on": "col", "values": 2}] and s["why"] == "연도 열 2(2024 · 2025년) · 기관 행·열 없음"
    s = one(table(calendar("2023", "2024", "2025", side="rowhead")))["subs"][0]
    assert s["kind"] == "byDivision" and s["axes"] == [{"basis": "period", "on": "row", "values": 3}] and s["why"].startswith("연도 행 3(2023 · 2024 · 2025)")
    for years in (("2024",), ("20xx", "20xx"), ("2024", "2024년")):    # 값 하나 · 빈 양식의 같은 글 · 같은 해를 두 번 — 갈린 것이 아니다
        s = one(table(calendar(*years)))["subs"][0]
        assert (s["kind"], s["basis"], s["axes"]) == ("common", [], []) and s["why"] == "기관 · 단계 · 차년도 · 연도로 갈리지 않음", years
    named = [H("h1", 0, 0, "발표연도", "colhead", ["year"], "name"), H("h2", 0, 1, "논문명"), F("a1", 1, 0, "2024"), F("a2", 1, 1, "가"), F("b1", 2, 0, "2025"), F("b2", 2, 1, "나")]
    assert one(table(named))["kind"] == "common"                     # 이름 머리 아래 값 칸에 적힌 해는 값 머리가 아니다
    s = one(table(calendar("2024", "2025")), zone({}, whole={}))["subs"][0]   # 편집 구역은 연도를 주지 않는다 — 구역이 있어도 근거는 머리글의 꼴
    assert (s["kind"], s["by"], s["sure"]) == ("byDivision", "heads", False)
    both = [H("c", 0, 0, "구분", "corner"), H("y1", 0, 1, "1차년도(2026년)", "colhead", ["year", "period"], "value"), H("y2", 0, 2, "2차년도(2027년)", "colhead", ["year", "period"], "value"),
            H("k", 1, 0, "내용", "rowhead"), F("a1", 1, 1, "가"), F("a2", 1, 2, "나")]
    s = one(table(both))["subs"][0]                                  # 한 머리가 차년도와 연도를 함께 말한다 — 둘 다 싣고 글은 한 번만
    assert s["basis"] == ["year", "period"] and [(a["basis"], a["values"]) for a in s["axes"]] == [("year", 2), ("period", 2)]
    assert s["why"] == "차년도 열 2(1차년도(2026년) · 2차년도(2027년)) · 연도 열 2 · 기관 행·열 없음"
    money = calendar("2024", "2025") + [H("tt", 0, 3, "합계", "colhead", ["total"], "total"), F("v3", 1, 3, "3", 3.0, formulas=["f0"])]
    s = one(table(money, [band(calc=True)]))["subs"][0]              # 합계가 있는 숫자 표는 연도 열이 있어도 셀 값 합산(차례 5 가 먼저) — 연도 열은 적어 둔다
    assert (s["kind"], s["by"], s["basis"]) == ("sum", "calc", ["period"]) and s["why"].endswith("기관 행·열 없음 · 연도 열 2(2024 · 2025)")
    orgs = org_rows() + [H("p1", 0, 2, "2024", "colhead", ["period"], "value"), H("p2", 0, 3, "2025", "colhead", ["period"], "value")]
    s = one(table(orgs))["subs"][0]                                  # 기관 행이 먼저 — 연도 열은 행/열로만 실린다
    assert (s["kind"], s["basis"]) == ("byDivision", ["org", "period"]) and s["why"].startswith("기관 행 2")
    assert TK.VALUE_DIMS == ("stage", "year", "period") and TK.DIM_KO["period"] == "연도" and TK.DIMS == ("org", "stage", "year", "period")


def sum_band(sub="S", r0=0):
    """「비목 | 합계」 + 값 행 하나 — 합계 머리가 있는 숫자 띠(셀 값 합산)."""
    return [H(sub + "c", r0, 0, "비목", "corner", sub=sub), H(sub + "t", r0, 1, "합계", "colhead", ["total"], "total", sub=sub),
            H(sub + "r", r0 + 1, 0, "인건비", "rowhead", sub=sub), F(sub + "f", r0 + 1, 1, "10", 10.0, sub=sub)]


def test_common_mixed_and_bands_that_do_not_count():
    r = one(table(plain()))
    assert r["kind"] == "common" and [(s["sub"], s["kind"], s["by"], s["basis"], s["axes"], s["orgs"]) for s in r["subs"]] == [("A", "common", "none", [], [], 0)]
    org_b = [dict(x, id="B" + x["id"], row=x["row"] + 8, sub="B") for x in org_rows()]
    kinds_of = lambda r: [(s["sub"], s["kind"]) for s in r["subs"]]  # noqa: E731
    r = one(table([H("t", 0, 0, "제목", "title", sub="T")] + plain() + org_b, [band("T", "title"), band("A"), band("B")]))
    assert r["kind"] == "byDivision" and kinds_of(r) == [("A", "common"), ("B", "byDivision")]   # 제목 띠는 방식을 정하지 않는다 · 공통인 띠는 표 수준에서 빼고 본다(subs 에는 남는다)
    r = one(table(plain() + sum_band("S", 4), [band("A"), band("S", calc=True)]))
    assert r["kind"] == "sum" and kinds_of(r) == [("A", "common"), ("S", "sum")]                 # 숫자 띠 + 꼬리 양식 띠 = 셀 값 합산
    r = one(table(plain() + sum_band("S", 4) + org_b, [band("A"), band("S", calc=True), band("B")]))
    assert r["kind"] == "mixed" and kinds_of(r) == [("A", "common"), ("S", "sum"), ("B", "byDivision")]   # 공통 말고 둘 이상
    r = one(table(sum_band("S", 4) + org_b, [band("S", calc=True), band("B")]))
    assert r["kind"] == "mixed" and kinds_of(r) == [("S", "sum"), ("B", "byDivision")]
    r = one(table(sum_band("S", 0) + sum_band("U", 4), [band("S", calc=True), band("U", calc=True)]))
    assert r["kind"] == "sum" and kinds_of(r) == [("S", "sum"), ("U", "sum")]                    # 띠가 모두 같으면 그 방식
    r = one(table(plain() + [dict(x, id="D" + x["id"], row=x["row"] + 4, sub="D") for x in plain()], [band("A"), band("D")]))
    assert r["kind"] == "common" and kinds_of(r) == [("A", "common"), ("D", "common")]           # 모두 공통이면 공통
    K = lambda *ks: TK._table_kind([{"kind": k} for k in ks])       # noqa: E731
    assert (K(), K("common"), K("perOrg", "common", "common"), K("common", "sum", "sum"), K("perOrg", "sum"), K("common", "byDivision", "perOrg")) == \
        ("common", "common", "perOrg", "sum", "mixed", "mixed") and TK.QUIET == ("common",)
    only = table([H("t", 0, 0, "제목", "title", sub="T"), H("n", 1, 0, "※ 안내", "note", sub="N")], [band("T", "title"), band("N", "note")])
    r = one(only)
    assert r["kind"] == "common" and [s["sub"] for s in r["subs"]] == ["T", "N"]   # 그런 띠뿐인 표는 모든 띠
    assert TK.kinds({"id": "t0", "cells": [], "subtables": []}) == {"table": "t0", "kind": "common", "subs": []}
    assert TK.counts([{"kind": "mixed"}, {"kind": "sum"}, {"kind": "sum"}]) == {"perOrg": 0, "byDivision": 0, "sum": 2, "common": 0, "mixed": 1}
    assert TK.KIND_KO == {"perOrg": "기관마다 작성", "byDivision": "구분 기준에 따라 병합", "sum": "셀 값 합산", "common": "공통"}   # 화면 말 = 사용자의 말 그대로


def test_one_org_form_org_cell_in_table_and_per_org_text():
    form = [H("k1", 0, 0, "연구개발기관명", "rowhead", ["org"], "name"), F("v1", 0, 1, "인텍"), H("k2", 0, 2, "구입연차", "rowhead", ["year"], "name"), F("v2", 0, 3, "1차년도"),
            H("k3", 1, 0, "재료명", "rowhead"), F("v3", 1, 1, "가")]
    more = [H("h1", 2, 0, "구분", sub="B"), H("h2", 2, 1, "금액", sub="B"), F("m1", 3, 0, "가", sub="B"), F("m2", 3, 1, "1", 1.0, sub="B")]
    t = table(form + more, [band("A", "form"), band("B")])
    r = one(t, repeats=[{"signature": "sig-A", "count": 3, "where": []}])
    assert r["kind"] == "perOrg" and [(s["kind"], s["by"], s["sure"]) for s in r["subs"]] == [("perOrg", "form", False)] * 2   # 이름 칸이 든 띠만이 아니라 표 전체
    assert r["subs"][0]["why"] == "기관 이름 칸뿐인 표 — 머리글 「연구개발기관명」 · 같은 꼴의 표 3곳" and "같은 꼴" not in r["subs"][1]["why"]
    listed = form + [H("h1", 2, 0, "기관명", "colhead", ["org"], "name", sub="B"), H("h2", 2, 1, "금액", sub="B"), F("m1", 3, 0, sub="B"), F("m2", 3, 1, sub="B")]
    r = one(table(listed, [band("A", "form"), band("B")]))           # 「기관명」 열이 있는 표는 한 기관의 양식이 아니다
    assert [(s["sub"], s["kind"]) for s in r["subs"]] == [("A", "common"), ("B", "byDivision")]
    again = form + [H("k4", 2, 0, "연구개발기관명", "rowhead", ["org"], "name"), F("v4", 2, 1, "가나대")]
    s = one(table(again, [band("A", "form")]))["subs"][0]            # 같은 이름 칸이 되풀이 — 기관마다 한 묶음
    assert (s["kind"], s["by"]) == ("byDivision", "heads") and s["axes"][0] == {"basis": "org", "on": "row", "values": 0}
    lab = table(plain(), labels=[{"cell": "a1", "text": "[주관연구개발기관(기관명 기입)]", "basis": ["org"]}])
    assert [(s["kind"], s["by"]) for s in one(lab)["subs"]] == [("perOrg", "labels")]
    labs = table(plain(), labels=[{"cell": "a1", "text": "[주관연구개발기관]", "basis": ["org"]}, {"cell": "b1", "text": "[공동연구개발기관1]", "basis": ["org"]}])
    s = one(labs)["subs"][0]                                         # 구분 칸이 여럿이면 표 안에서 기관이 갈린다
    assert (s["kind"], s["by"], s["orgs"]) == ("byDivision", "labels", 2)
    said = table(plain(), before="[해당 기관별 작성] 영리기관의 연구실운영비 활용‧관리 계획")
    s = one(said)["subs"][0]
    assert (s["kind"], s["by"], s["sure"]) == ("perOrg", "text", False) and "「기관별 작성」" in s["why"]
    assert one(table(plain(), owner={"text": "①", "path": ["별첨6 [해당 기관별 작성] 계획"], "division": None}))["kind"] == "perOrg"


# ---- 편집 구역(zone_of)이 있을 때 -----------------------------------------------------------------------------------------

def test_zone_whole_org_is_per_org_and_sure():
    t = table(org_rows())                                            # 머리글의 꼴은 기관 행이지만 편집 구역이 표를 통째로 한 기관의 것으로 본다
    r = one(t, zone({"t1": org("가나대")}, whole=org("가나대")))
    s = r["subs"][0]
    assert (r["kind"], s["by"], s["sure"], s["orgs"], s["basis"]) == ("perOrg", "zone", True, 1, ["org"]) and s["why"] == "한 기관의 구역 — 가나대"
    assert one(t)["subs"][0]["sure"] is False                        # 편집 구역 없이는 머리글의 꼴뿐


def test_zone_split_by_rows_and_by_columns():
    t = table(org_rows())
    rows = {"r1": org("인텍"), "f1": org("인텍"), "r2": org("가나대"), "f2": org("가나대")}
    s = one(t, zone(rows, whole={}))["subs"][0]
    assert (s["kind"], s["by"], s["sure"], s["orgs"]) == ("byDivision", "zone", True, 2) and s["axes"] == [{"basis": "org", "on": "row", "values": 2}]
    assert s["why"] == "기관 행 2 — 인텍 · 가나대"
    wide = [H("c", 0, 0, "기관명 구분", "corner"), H("o1", 0, 1, "인텍 (주관기관)"), H("o2", 0, 2, "다라연 (공동)"),
            H("k1", 1, 0, "대표자", "rowhead"), F("a1", 1, 1, "가"), F("a2", 1, 2, "나"), H("k2", 2, 0, "주소", "rowhead"), F("b1", 2, 1, "다"), F("b2", 2, 2, "라")]
    cols = {i: org("인텍") for i in ("o1", "a1", "b1")} | {i: org("다라연") for i in ("o2", "a2", "b2")}
    s = one(table(wide), zone(cols, whole={}))["subs"][0]
    assert s["kind"] == "byDivision" and s["sure"] and s["axes"] == [{"basis": "org", "on": "col", "values": 2}] and s["why"].startswith("기관 열 2 — 인텍 · 다라연")
    years = {"a1": {"year": 1, "stage": 1}, "b1": {"year": 1, "stage": 1}, "a2": {"year": 2, "stage": 1}, "b2": {"year": 2, "stage": 1}}
    s = one(table(wide), zone(years, whole={}))["subs"][0]           # 기관은 없고 칸마다 차년도가 둘 — 구분 기준에 따라 병합(편집 구역이 근거)
    assert (s["kind"], s["by"], s["sure"], s["basis"]) == ("byDivision", "zone", True, ["year"]) and s["axes"] == [{"basis": "year", "on": "col", "values": 2}]


def test_unread_zone_is_not_counted_as_an_org():
    t = table(plain())
    unread = {"org": "가나대", "orgKind": "unknown"}                  # 기관 자리인데 못 읽은 곳 — org 에 무엇이 실려 와도 한 기관으로 치지 않는다
    s = one(t, zone({"t1": unread}, whole=unread))["subs"][0]
    assert (s["kind"], s["by"], s["sure"], s["orgs"], s["basis"]) == ("common", "none", False, 0, []) and s["why"].endswith("기관 모름 6칸")
    owned = table(plain(), owner={"text": "x", "division": {"text": "[공동연구개발기관(기관명 기입)]", "basis": ["org"]}})
    s = one(owned, zone({"t1": unread}, whole=unread))["subs"][0]    # 머리글의 꼴이 정한다 — 확실하지 않다
    assert (s["kind"], s["by"], s["sure"], s["orgs"]) == ("perOrg", "owner", False, 0)
    clash = {"org": None, "orgKind": "conflict"}
    s = one(t, zone({"t1": org("인텍"), "a2": clash}, whole=org("인텍")))["subs"][0]
    assert (s["kind"], s["by"], s["sure"], s["orgs"]) == ("perOrg", "zone", False, 1) and s["why"] == "한 기관의 구역 — 인텍 · 기관 확인 필요 1칸"
    two = {"r1": org("인텍"), "f1": org("인텍"), "r2": unread, "f2": unread}
    s = one(table(plain() + [dict(x, row=x["row"] + 3) for x in org_rows()[2:]]), zone(two, whole={}))["subs"][0]
    assert (s["kind"], s["by"], s["sure"], s["orgs"]) == ("byDivision", "zone", False, 1) and "(한 기관만 읽힘)" in s["why"] and "기관 모름 2칸" in s["why"]   # 읽힌 기관 하나 + 못 읽은 칸 ≠ 기관 둘


def test_sure_of_sum_and_common_follows_the_zones():
    money = [H("c", 0, 0, "비목", "corner"), H("tt", 0, 1, "합계", "colhead", ["total"], "total"), H("r1", 1, 0, "인건비", "rowhead"), F("a1", 1, 1, "10", 10.0)]
    looked = zone({}, whole={})                                      # 편집 구역이 그 표의 칸을 보았고 기관이 없다
    for t, kind in ((table(money, [band(calc=True)]), "sum"), (table(plain()), "common")):
        assert [(s["kind"], s["sure"]) for s in one(t)["subs"]] == [(kind, False)]
        assert [(s["kind"], s["sure"]) for s in one(t, looked)["subs"]] == [(kind, True)]
        assert [(s["kind"], s["sure"]) for s in one(t, zone({}))["subs"]] == [(kind, False)]   # 편집 구역이 모르는 표(칸 안의 표) — 보지 않았다


def test_nested_table_inherits_the_outer_cell():
    t = table(plain(), id="t9", depth=2, parentCell="outer")
    s = one(t, zone({"outer": org("다라연")}))["subs"][0]            # 칸 안의 표 — 편집 구역은 바깥 칸만 안다
    assert (s["kind"], s["by"], s["sure"], s["orgs"]) == ("perOrg", "zone", True, 1) and "다라연" in s["why"]
    assert one(t, zone({"outer": {}}))["subs"][0]["sure"] is False   # 바깥 칸에 기관이 없다 — 안쪽 칸은 보지 않았으니 확실하지 않다


def test_kinds_does_not_touch_the_table():
    t = table(org_rows(), [band(calc=True)], owner={"text": "x", "division": {"text": "[기관]", "basis": ["org"]}}, labels=[{"cell": "f1", "text": "[주관]", "basis": ["org"]}])
    before = copy.deepcopy(t)
    one(t, zone({"t1": org("인텍")}, whole=org("인텍")), repeats=[{"signature": "sig-A", "count": 2}])
    one(t)
    assert t == before


# ---- 끝점 -----------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client():
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _open(c):
    r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes())})
    assert r.status_code == 200, r.text[:300]
    return r.json()["docId"]


def _check(v, n):
    assert v["gate"] == "rnd" and set(v["counts"]) == {"perOrg", "byDivision", "sum", "common", "mixed"}
    assert len(v["tables"]) == n and sum(v["counts"].values()) == n and v["counts"] == TK.counts(v["tables"])
    for t in v["tables"]:
        assert set(t) == {"table", "kind", "subs"} and t["kind"] in (*TK.KINDS, "mixed") and t["subs"]
        loud = {s["kind"] for s in t["subs"]} - {"common"}            # 공통인 띠는 표 수준에서 빼고 본다
        assert t["kind"] == ("mixed" if len(loud) > 1 else next(iter(loud)) if loud else "common")
        for s in t["subs"]:
            assert set(s) == SUB_KEYS and s["kind"] in TK.KINDS and s["why"] and not any(w in s["why"] for w in BANNED), s


def test_zone_reader_takes_the_place_not_the_origin(monkeypatch):
    """끝점이 편집 구역에서 읽는 것 — 자리의 기관(자동 · 지정)만: 취합으로 들어온 내용의 기관(src origin)과 못 읽은 곳은 기관이 아니다 · 모르는 id 는 None · 값이 없으면 구역 없이."""
    from app import table_kinds_api as API
    from app import zones_api
    lab = lambda org, kind="org", src="auto", **kw: {"org": org, "orgKind": kind, "stage": None, "year": None, "src": {"org": src} if kind else {}, "ev": {}, **kw}   # noqa: E731
    view = {"basis": "applied", "reasons": [], "orgs": [{"key": "가", "name": "가나대", "role": "joint"}],
            "blocks": {"t1": lab("가"), "t2": lab("가", src="origin"), "t3": lab("가", src="mark"), "t4": lab(None, "unknown"), "t5": lab(None, None, year=2, stage=1)},
            "cells": {"t5": {"c1": lab("가", year=1, stage=1)}}, "_tableOf": {"c1": "t5", "c2": "t5"}, "_info": {"order": ["t1", "t2", "t3", "t4", "t5", "p9"]}}
    monkeypatch.setattr(zones_api, "read", lambda s: view)
    z = API._zone_of(None)
    assert z("t1") == {"org": "가", "orgKind": "org", "orgName": "가나대", "year": None, "stage": None} and z("t3")["org"] == "가"
    assert z("t2") == {"org": None, "orgKind": None, "orgName": None, "year": None, "stage": None}        # 들어온 내용의 기관 — 자리의 기관이 아니다
    assert z("t4")["org"] is None and z("t4")["orgKind"] == "unknown"
    assert (z("c1")["org"], z("c1")["year"]) == ("가", 1) and (z("c2")["org"], z("c2")["year"]) == (None, 2)   # 칸의 것 · 없으면 그 표의 것
    assert z("p9") == {"org": None, "orgKind": None, "orgName": None, "year": None, "stage": None} and z("nested") is None
    t = table(plain(), id="t2")
    assert [(s["kind"], s["sure"]) for s in one(t, z)["subs"]] == [("common", True)]                       # 공통 자리의 표는 한 기관의 글이 들어와도 공통
    assert [(s["kind"], s["by"], s["sure"]) for s in one(table(plain(), id="t3"), z)["subs"]] == [("perOrg", "zone", True)]   # 사람이 지정한 구역
    monkeypatch.setattr(zones_api, "read", lambda s: {**view, "basis": None, "reasons": ["noValues"]})
    assert API._zone_of(None) is None

    def boom(s):
        raise RuntimeError("x")
    monkeypatch.setattr(zones_api, "read", boom)
    assert API._zone_of(None) is None                                # 구역을 못 읽어도 방식은 머리글의 꼴로 낸다


def test_api_general_document_has_no_kinds(client):
    c = client
    d = _open(c)
    assert c.put(f"/api/works/{d}/task", json={"kind": "general", "file": "", "job": "doc_edit", "project": ""}).status_code == 200
    assert c.get(f"/api/docs/{d}/tables/kinds").json() == {"gate": "none"}   # 일반 문서 — 프로젝트 귀속 층이 없다(3단계 결과가 없어도 404 가 아니다)
    HR.run_sync(server._sess(d), 3, False)
    assert c.get(f"/api/docs/{d}/tables/kinds").json() == {"gate": "none"}
    assert c.get("/api/docs/없는문서/tables/kinds").status_code == 404


def test_api_needs_stage3_then_answers_by_header_shape(client):
    c = client
    d = _open(c)
    r = c.get(f"/api/docs/{d}/tables/kinds")   # 3단계 결과 없음 — 404 가 아니라 빈 목록(탭이 열릴 때마다 묻는 끝점이라 콘솔에 오류가 쌓이지 않게)
    assert r.status_code == 200 and r.json()["gate"] == "rnd" and r.json()["missing"] is True and r.json()["tables"] == [] and set(r.json()["counts"].values()) == {0}
    s = server._sess(d)
    HR.run_sync(s, 3, False)
    t3 = HR.tables(s)
    v = c.get(f"/api/docs/{d}/tables/kinds")
    assert v.status_code == 200, v.text[:300]
    v = v.json()
    assert set(v) == {"gate", "tables", "counts", "source", "rev"} and v["rev"] == s.rev
    assert v["source"] == {"stage3Run": t3["meta"]["run"], "zones": False}   # 프로젝트 구성 값이 없다 — 머리글의 꼴만
    _check(v, len(t3["tables"]))
    assert [t["table"] for t in v["tables"]] == [t["id"] for t in t3["tables"]]
    assert not any(x["sure"] for t in v["tables"] for x in t["subs"]) and not any(x["by"] == "zone" for t in v["tables"] for x in t["subs"])
    assert all(v["counts"][k] > 0 for k in ("perOrg", "byDivision", "sum", "common"))   # 빈 양식에도 네 방식이 다 있다
    by_id = {t["id"]: t for t in t3["tables"]}
    for t in v["tables"]:                                             # 근거와 방식이 3단계 결과와 맞는다
        owner = by_id[t["table"]].get("owner") or {}
        if "org" in ((owner.get("division") or {}).get("basis") or ()):
            assert t["kind"] == "perOrg" and all(x["by"] == "owner" for x in t["subs"])
        for x in t["subs"]:
            if x["kind"] == "sum":
                b = next(b for b in by_id[t["table"]]["subtables"] if b["id"] == x["sub"])
                assert b["calc"]["is"]
    pid = next(b["id"] for b in s.doc.blocks() if b["type"] == "paragraph" and b.get("text"))
    assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "고친 글"}).status_code == 200
    w = c.get(f"/api/docs/{d}/tables/kinds").json()                   # 문서가 바뀜 — 낡은 결과 그대로 + stale(다시 돌리라고 하지 않는다)
    assert w["stale"] is True and w["rev"] == s.rev and w["tables"] == v["tables"] and w["counts"] == v["counts"]


def test_api_reads_the_zones_when_project_values_exist(client):
    """값(기관 셋 · 1단계 2차년도)을 반영한 양식 — 편집 구역이 근거가 된다(test_zones_api 와 같은 자료)."""
    from test_merge_gather_api import _master
    import gather_data as D
    from app import merge_gather_api as GA
    from app import task_options as TO
    from app import zones_api as ZA
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS, GA._ZONES, ZA._AUTO, TO._MEMORY):
        box.clear()
    c = client
    to, _ = _master(c, frame=False)
    v = c.get(f"/api/docs/{to}/tables/kinds").json()
    n = len(HR.tables(server._sess(to))["tables"])
    assert v["source"]["zones"] is True and "stale" not in v
    _check(v, n)
    subs = [x for t in v["tables"] for x in t["subs"]]
    whole = [x for x in subs if x["kind"] == "perOrg" and x["by"] == "zone"]
    assert len(whole) >= 30 and all(x["sure"] and x["orgs"] == 1 for x in whole)              # 기관 구분 줄 아래의 표들 — 한 기관의 구역
    assert {x["why"].split(" — ")[1].split(" · ")[0] for x in whole} == {D.LEAD, D.J1, D.J2}
    split = [x for x in subs if x["kind"] == "byDivision" and x["by"] == "zone" and x["sure"] and "org" in x["basis"]]
    assert len(split) >= 8 and any(x["orgs"] == 3 and x["why"].startswith(f"기관 행 3 — {D.LEAD} · {D.J1} · {D.J2}") for x in split)   # 기관 행이 든 표(참여연구자 현황 …)
    assert any(x["kind"] == "sum" and x["sure"] for x in subs) and any(x["kind"] == "common" and x["sure"] for x in subs)
    assert c.put(f"/api/works/{to}/task", json={"kind": "rnd", "file": "plan", "job": "plan_fit", "project": "취합 시험"}).status_code == 200
    again = c.get(f"/api/docs/{to}/tables/kinds").json()             # 편집 구역 옵션(보일 기준)이 꺼진 TASK 에서도 귀속은 읽는다
    assert again["source"]["zones"] is True and again["counts"] == v["counts"]
