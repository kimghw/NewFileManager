"""구분 기준 열 넣기(spec_테이블매니저 ② §13 — app/table_divcol.py 순수 계산 · app/table_divcol_api.py 끝점).
견본 = samples/연구개발계획서_양식.hwpx 의 「연구개발성과 성능 목표」 표(머리 행 3줄 — 「평가 항목」 귀퉁이 · 「개발 목표치 › 1단계 › 1~3차 년도」 묶음 머리 · 값 줄 1. ~ 8.)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import server
from app import table_divcol as TD
from app.hwpx_doc import HwpxDoc

RND = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
VALUES = {"stages": [2, 1], "orgs": {"lead": "인텍", "joint": ["가나대", "다라연"], "nonprofit": [False, True, False]},
          "period": {"start": "2026-03-01", "end": "2028-12-31"}, "current": 1}


def _cell(row, col, rs=1, cs=1, role="field", text="", cid=None):
    return {"id": cid or f"c{row}_{col}", "row": row, "col": col, "rs": rs, "cs": cs, "role": role, "text": text, "sub": "A"}


def _goal():
    """성능 목표 표의 꼴(작게) — 0~1행 머리(귀퉁이 「평가 항목」 2줄 · 「단위」 2줄 · 「목표」 가 2열에 걸침 → 「1차」 「2차」) · 2~4행 값 · 5행 합계."""
    cells = [_cell(0, 0, 2, 1, "corner", "평가 항목"), _cell(0, 1, 2, 1, "colhead", "단위"), _cell(0, 2, 1, 2, "colhead", "목표"),
             _cell(1, 2, 1, 1, "colhead", "1차 년도"), _cell(1, 3, 1, 1, "colhead", "2차 년도"), _cell(0, 4, 2, 1, "colhead", "평가 방법")]
    for r, name in ((2, "1."), (3, "2."), (4, "3."), (5, "합계")):
        cells.append(_cell(r, 0, role="rowhead", text=name))
        cells += [_cell(r, c) for c in range(1, 5)]
    return {"id": "t1", "rows": 6, "cols": 5, "cells": cells}


def test_classes_positions_and_default_after_row_head():
    tb = _goal()
    assert TD.classes(tb) == ["head", "head", "data", "data", "data", "data"]
    pos = TD.positions(tb)
    ats = [p["at"] for p in pos]
    assert 3 not in ats   # 「목표」 묶음 머리 안(1차 | 2차 사이)에는 넣지 않는다
    assert ats == [0, 1, 2, 4, 5]
    by = {p["at"]: p for p in pos}
    assert by[1]["default"] and by[1]["src"] == 0 and by[1]["op"] == "col_right" and by[1]["label"] == "「평가 항목」 다음"
    assert by[0]["op"] == "col_left" and by[0]["label"] == "맨 앞" and by[5]["label"] == "맨 끝"
    assert by[4]["src"] == 4 and by[4]["op"] == "col_left"   # 왼쪽(2차 년도)은 머리에 「목표」 가 걸쳐 본뜰 수 없다 → 오른쪽 열


def test_items_skip_total_rows_and_heads_are_the_top_cell():
    tb = _goal()
    its = TD.items(tb, 0)
    assert [(i["id"], i["label"], i["rows"]) for i in its] == [("c2_0", "1.", [2, 2]), ("c3_0", "2.", [3, 3]), ("c4_0", "3.", [4, 4])]
    assert TD.heads_of(tb, 0) == ["c0_0"]
    assert TD.heads_of(tb, 2) == ["c1_2"]   # 「목표」 는 두 열에 걸친 칸이라 빠지고 그 열의 한 열 폭 머리 칸 가운데 맨 위
    assert TD.is_total("소 계") and TD.is_total("A › 합계") and not TD.is_total("계획")


def test_suggest_only_a_single_known_zone_value():
    tb = _goal()
    it = TD.items(tb, 0)[0]
    choices = {"org": [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}], "year": [{"key": 1, "label": "1차년도"}], "stage": []}
    one = lambda i: {"org": "a", "year": 1}
    assert TD.suggest(it, one, choices) == ({"year": [1], "org": ["a"]}, {"year": "zone", "org": "zone"})
    mixed = lambda i: {"org": "a" if i.endswith("1") else "b"}
    assert TD.suggest(it, mixed, choices) == ({}, {})   # 줄의 칸들이 서로 다른 기관 — 권하지 않는다
    assert TD.suggest(it, lambda i: {"org": "zz"}, choices) == ({}, {})   # 고를 값에 없는 값
    assert TD.suggest(it, None, choices) == ({}, {})


def test_width_estimate_is_bounded():
    assert TD.width_of(["기관", "인텍"], 0) == int(15 * TD.MM)
    assert TD.width_of(["한국전기연구원 · 가나대학교 산학협력단"], 0) == int(25 * TD.MM)
    assert TD.width_of(["기관"], 30000) == int(30000 * 0.3) or TD.width_of(["기관"], 30000) <= 30000 * 0.3


def test_set_col_widths_keeps_the_table_width():
    d = HwpxDoc(RND.read_bytes())
    d.blocks()   # 블록 id 를 매긴다
    tid = _goal_tid(d)
    tbl, cells, nr, nc = d._tgrid(d._ids[tid])
    before = d._tsizes(cells, nr, nc)[1]
    out = d.set_col_widths(tid, {1: 4000})
    assert out["widths"][1] == 4000 and sum(out["widths"]) == sum(before)


def _goal_tid(doc):
    from app import table_excel
    for tid, el in list(doc._ids.items()):
        if str(el.tag).endswith("}tbl"):
            before = table_excel.context(doc, tid)["before"]
            if before and "<연구개발성과성능목표>" in "".join(before[-1].split()):
                return tid
    raise AssertionError("성능 목표 표가 없다")


@pytest.fixture
def client():
    server.DOCS.clear()
    return TestClient(server.app)


def _open(c, values=True):
    r = c.post("/api/docs?new=1", files={"file": (RND.name, RND.read_bytes())})
    assert r.status_code == 200, r.text
    doc = r.json()["docId"]
    if values:
        assert c.put(f"/api/docs/{doc}/divisions/settings", json={"values": VALUES}).status_code == 200
    return doc, _goal_tid(server._sess(doc).doc)


def test_plan_lists_project_values_and_positions(client):
    doc, tid = _open(client)
    p = client.get(f"/api/docs/{doc}/tables/{tid}/divcol").json()
    assert p["gate"] == "rnd" and p["ready"]
    assert [v["label"] for v in p["values"]["org"]] == ["인텍", "가나대", "다라연"]
    assert [v["label"] for v in p["values"]["year"]] == ["1단계 1차년도", "1단계 2차년도", "2단계 1차년도"]
    assert [v["label"] for v in p["values"]["stage"]] == ["1단계", "2단계"]
    d = next(x for x in p["positions"] if x["default"])
    assert d["at"] == 1 and d["src"] == 0
    its = p["items"][str(d["src"])]
    assert [i["label"] for i in its][:3] == ["1.", "2.", "3."]
    ats = {x["at"]: x["label"] for x in p["positions"]}
    assert not {6, 7, 8, 9} & set(ats) and ats[10] == "「개발 목표치」 다음"   # 「개발 목표치 › 1단계 · n단계」 묶음 머리 안에는 넣지 않는다 · 묶음 뒤는 그 묶음 이름으로
    assert p["heads"][str(d["src"])]


def test_no_project_values_is_not_ready(client):
    doc, tid = _open(client, values=False)
    p = client.get(f"/api/docs/{doc}/tables/{tid}/divcol").json()
    assert p["gate"] == "rnd" and p["ready"] is False


def test_apply_inserts_columns_and_writes_values_then_undo(client):
    doc, tid = _open(client)
    p = client.get(f"/api/docs/{doc}/tables/{tid}/divcol").json()
    d = next(x for x in p["positions"] if x["default"])
    its = p["items"][str(d["src"])]
    s = server._sess(doc)
    nc = s.doc.table_block(tid)["nCols"]
    body = {"rev": p["rev"], "planId": p["planId"], "at": d["at"], "cols": [{"basis": "org"}, {"basis": "year", "head": "수행 연차"}],
            "values": {its[0]["id"]: {"org": "인텍", "year": "1단계 1차년도"}, its[1]["id"]: {"org": "가나대, 다라연"}}}
    r = client.post(f"/api/docs/{doc}/tables/{tid}/divcol/apply", json=body)
    assert r.status_code == 200, r.text[:800]
    out = r.json()["divcol"]
    assert out["bases"] == ["year", "org"] and out["cols"] == [1, 2] and out["filled"] == 3 and out["heads"] == 2
    b = s.doc.table_block(tid)
    assert b["nCols"] == nc + 2
    grid = {(c["row"], c["col"]): (c.get("text") or "").strip() for c in b["cells"]}
    assert grid[(0, 1)] == "수행 연차" and grid[(0, 2)] == "기관"   # 구분 순서: 차년도 → 기관
    assert grid[(3, 1)] == "1단계 1차년도" and grid[(3, 2)] == "인텍" and grid[(4, 2)] == "가나대, 다라연" and grid[(4, 1)] == ""
    assert grid[(3, 0)].startswith("1.") and grid[(0, 0)].startswith("평가 항목")   # 본뜬 열의 글은 그대로
    again = client.post(f"/api/docs/{doc}/tables/{tid}/divcol/apply", json=body)
    assert again.status_code == 409   # 문서 차례가 바뀜
    assert client.post(f"/api/docs/{doc}/undo").status_code == 200
    assert server._sess(doc).doc.table_block(tid)["nCols"] == nc


def test_apply_rejects_a_stale_plan_and_a_bad_position(client):
    doc, tid = _open(client)
    p = client.get(f"/api/docs/{doc}/tables/{tid}/divcol").json()
    bad = [x for x in range(p["cols"] + 1) if x not in {q["at"] for q in p["positions"]}]
    base = {"rev": p["rev"], "planId": p["planId"], "cols": [{"basis": "org"}], "values": {}}
    assert client.post(f"/api/docs/{doc}/tables/{tid}/divcol/apply", json={**base, "at": 1, "planId": "nope"}).status_code == 409
    if bad:
        assert client.post(f"/api/docs/{doc}/tables/{tid}/divcol/apply", json={**base, "at": bad[0]}).status_code == 400
    assert client.post(f"/api/docs/{doc}/tables/{tid}/divcol/apply", json={**base, "at": 1, "cols": [{"basis": "org"}, {"basis": "org"}]}).status_code == 400
    assert client.post(f"/api/docs/{doc}/tables/{tid}/divcol/apply", json={**base, "at": 1, "values": {"zz": {"org": "인텍"}}}).status_code == 400


def test_general_document_is_outside_the_gate(client):
    sample = Path(__file__).parents[1] / "samples" / "기술수요조사서.docx"
    r = client.post("/api/docs?new=1", files={"file": (sample.name, sample.read_bytes())})
    doc = r.json()["docId"]
    blk = next(b for b in server._sess(doc).doc.blocks() if b.get("type") == "table")
    assert client.get(f"/api/docs/{doc}/tables/{blk['id']}/divcol").json() == {"gate": "none"}
