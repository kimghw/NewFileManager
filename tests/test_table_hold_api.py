"""사람의 헤더 지정 — 도장 · 보류(spec_테이블매니저 ② §3 「사람의 헤더 지정」 · app/table_heads.py `stamp` · `check`)와
빈 필드 제거 끝점의 보류 · rev 필수(② §4 「지우거나 쓰는 도구」 ⓒ ⓓ — app/tables_api.py `table_prune_lines` · `table_heads_put`).
빈 줄 판정 자체는 tests/test_table_prune.py, 표 서식 점검의 보류는 tests/test_table_style.py."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import heading_guides as G
from app import heading_rules as R
from app import server, table_heads
from app.hwpx_doc import P

SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
TID = "t8"            # 18×11 양식 표 — 빈 행 3~8(「기술수요 과제명」 · 「기술개발의 필요성」 · 「기술개발 최종목표」 의 값 줄 + 딸린 안내 줄)
NEED = "c54"          # 5행 「기술개발의 필요성」 의 값 칸(빈 필드)
BODY = "c64"          # 9행 머리열 「기술내용」(빈 행들 아래 — 빈 행을 지우면 자리가 3행으로 올라간다)
HELD_MSG = "헤더 지정 1칸이 지금 표와 맞지 않습니다 — 표 메뉴에서 다시 지정하거나 풀어 주세요"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


@pytest.fixture()
def opened():
    """(클라이언트, 문서 id, 세션, 빈 필드 제거 URL, 헤더 지정 URL) — 기술수요조사서."""
    server.DOCS.clear()
    c = TestClient(server.app)
    r = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()["docId"]
    yield c, d, server.DOCS[d], f"/api/docs/{d}/tables/{TID}/prune", f"/api/docs/{d}/tables/{TID}/heads"
    server.DOCS.clear()


def _go(p, **more):
    """미리보기(p)가 준 계획대로 지우는 요청 몸(spec_테이블매니저 ② §12 — action · planId · rev)."""
    return {"action": "rows", "planId": p["planId"], "rev": p["rev"], **more}


def _rows(c, d):
    def find(bs):
        for b in bs:
            if b["type"] == "table":
                if b["id"] == TID:
                    return b
                for cell in b["cells"]:
                    hit = find(cell.get("blocks") or [])
                    if hit:
                        return hit
        return None
    return find(c.get(f"/api/docs/{d}").json()["blocks"])["nRows"]


def _para(s, cid):
    return next(s.doc._id(p) for p in s.doc._ids[cid].iter(P))


# ---- 도장 ------------------------------------------------------------------------------------------------------------

def test_heads_put_stamps_the_cells_and_release_drops_the_stamp(opened):
    c, d, s, _prune, heads = opened
    r = c.put(heads, json={"cells": [NEED, BODY], "role": "rowhead"})
    assert r.status_code == 200 and r.json()["roles"] == {NEED: "rowhead", BODY: "rowhead"}
    rec = c.get(f"/api/docs/{d}/tables/heads").json()
    assert rec["stamps"] == {TID: {NEED: {"at": [5, 1, 1, 10], "text": ""}, BODY: {"at": [9, 0, 4, 1], "text": "기술내용"}}}   # 지정할 때의 자리 · 글(공백 뺀 앞 60자)
    assert c.put(heads, json={"cells": [NEED], "role": None}).status_code == 200                # 풀면 도장도 지운다
    rec = table_heads.load(s.id)
    assert rec["tables"] == {TID: {BODY: "rowhead"}} and rec["stamps"] == {TID: {BODY: {"at": [9, 0, 4, 1], "text": "기술내용"}}}
    assert c.put(heads, json={"cells": ["c0"], "role": "rowhead"}).status_code == 400           # 그 표의 칸이 아님 — 전과 같다
    assert c.get(f"/api/docs/{d}").json()["pristine"] is True                                   # 지정은 문서를 안 바꾼다


def test_designation_without_a_stamp_stays_valid(opened):
    c, d, s, prune, _heads = opened
    table_heads.put(s.id, TID, [NEED], "rowhead")                                               # 도장 없이 저장된 옛 지정(전의 저장 꼴)
    assert table_heads.load(s.id)["stamps"] == {}
    assert c.patch(f"/api/docs/{d}/blocks/{_para(s, NEED)}", json={"text": "0,000"}).status_code == 200
    p = c.post(prune, json={"dry": True}).json()
    assert p["held"] == [] and p["emptyRows"] == [3, 4, 7, 8]                                   # 견줄 도장이 없으니 유효로 본다 — 그 줄은 머리열뿐


def test_cell_id_reused_after_undo_does_not_inherit_the_designation(opened):
    """행 넣기 → 새 칸을 지정 → 실행 취소 → 다른 자리에 행 넣기: 새 칸이 옛 칸 id 를 다시 받는다 — 옛 지정은 그 칸의 것이 아니므로 보류된다."""
    c, d, s, prune, heads = opened

    def at():
        return {x["id"]: [x["row"], x["col"], x["rs"], x["cs"]] for x in table_heads.table(s.doc, TID)["cells"]}
    before = at()
    assert c.post(f"/api/docs/{d}/table", json={"id": _para(s, "c80"), "op": "row_below"}).status_code == 200   # 14행(「TRL」 줄) 아래에 행
    cid = sorted(set(at()) - set(before))[0]
    was = at()[cid]
    assert c.put(heads, json={"cells": [cid], "role": "rowhead"}).status_code == 200                           # 새 칸을 지정
    assert table_heads.load(s.id)["stamps"][TID][cid] == {"at": was, "text": ""}
    assert c.post(f"/api/docs/{d}/undo").status_code == 200                                                     # 행 넣기를 되돌림 — 그 칸이 없어진다
    assert cid not in at() and c.post(prune, json={"dry": True}).json()["held"] == []                           # 없는 칸의 지정은 유효에도 보류에도 없다
    assert c.post(f"/api/docs/{d}/table", json={"id": _para(s, "c91"), "op": "row_below"}).status_code == 200   # 16행 아래에 다른 행
    now = at()
    assert cid in now and now[cid] != was                                                                       # 새 칸이 옛 id 를 다시 받았다(다른 자리의 다른 칸)
    assert c.post(prune, json={"dry": True}).json()["held"] == [{"cell": cid, "role": "rowhead", "why": "자리가 바뀜"}]


# ---- 빈 필드 제거 — 유효한 지정만 · 보류 · rev ---------------------------------------------------------------------------

def test_prune_uses_only_valid_designations_and_stops_on_a_held_one(opened):
    c, d, s, prune, heads = opened
    p0 = c.post(prune, json={"dry": True}).json()
    assert p0["emptyRows"] == [3, 4, 5, 6, 7, 8] and p0["held"] == []
    assert c.put(heads, json={"cells": [NEED], "role": "rowhead"}).status_code == 200           # 빈 값 칸을 머리열로 — 그 줄에는 채울 필드가 없다
    p1 = c.post(prune, json={"dry": True}).json()
    assert p1["emptyRows"] == [3, 4, 7, 8] and p1["held"] == []                                 # 유효한 지정은 쓴다
    assert c.patch(f"/api/docs/{d}/blocks/{_para(s, NEED)}", json={"text": "0,000"}).status_code == 200   # 지정한 칸의 글이 바뀜(자리표시 — 필드로는 빈 칸)
    p2 = c.post(prune, json={"dry": True}).json()
    assert p2["held"] == [{"cell": NEED, "role": "rowhead", "why": "글이 바뀜"}]
    assert p2["emptyRows"] == [3, 4, 5, 6, 7, 8]                                                # 보류된 지정은 안 쓴다(그 칸은 다시 빈 필드)
    n = _rows(c, d)
    r = c.post(prune, json=_go(p2))
    assert r.status_code == 409 and r.json()["detail"] == HELD_MSG                              # 지우기는 멈춘다
    assert _rows(c, d) == n and table_heads.get(s.id, TID) == {NEED: "rowhead"}                 # 안 지움 · 지정을 버리지도 않는다
    assert c.put(heads, json={"cells": [NEED], "role": None}).status_code == 200                # 지정을 푼다
    p3 = c.post(prune, json={"dry": True}).json()
    assert p3["held"] == [] and p3["emptyRows"] == [3, 4, 5, 6, 7, 8]
    r = c.post(prune, json=_go(p3))
    assert r.status_code == 200 and r.json()["pruned"]["rows"] == [3, 4, 5, 6, 7, 8] and _rows(c, d) == n - 6


def test_prune_needs_rev(opened):
    c, d, _s, prune, _heads = opened
    p = c.post(prune, json={"dry": True}).json()
    n = _rows(c, d)
    plan = {"action": "rows", "planId": p["planId"]}
    for body in (plan, {**plan, "rev": None}, {**plan, "rev": str(p["rev"])}, {**plan, "rev": True}):
        r = c.post(prune, json=body)
        assert r.status_code == 400 and r.json()["detail"].startswith("rev 가 필요합니다"), body  # 미리 본 문서와 같은지 볼 수 없는 지우기는 안 한다
    for body in ({}, {"rows": True, "rev": p["rev"]}):   # 계획(planId) 없는 지우기도 안 한다(옛 요청 꼴 포함 — spec_테이블매니저 ② §12)
        r = c.post(prune, json=body)
        assert r.status_code == 400 and r.json()["detail"].startswith("planId 가 필요합니다"), body
    assert _rows(c, d) == n and c.get(f"/api/docs/{d}").json()["pristine"] is True
    assert c.post(prune, json=_go(p, rev=p["rev"] + 1)).status_code == 409
    assert c.post(prune, json=_go(p)).status_code == 200 and _rows(c, d) == n - 6


def test_rows_removed_above_move_the_cell_and_hold_its_designation(opened):
    c, d, s, prune, heads = opened
    assert c.put(heads, json={"cells": [BODY], "role": "rowhead"}).status_code == 200           # 9행의 머리열 칸을 지정
    p = c.post(prune, json={"dry": True}).json()
    assert p["held"] == [] and c.post(prune, json=_go(p)).status_code == 200   # 위의 빈 행 6줄을 지움 → 그 칸은 3행으로
    p = c.post(prune, json={"dry": True}).json()
    assert p["held"] == [{"cell": BODY, "role": "rowhead", "why": "자리가 바뀜"}] and p["emptyRows"] == []
    r = c.post(prune, json=_go(p))
    assert r.status_code == 409 and r.json()["detail"] == HELD_MSG                              # 지울 줄이 있는지 보기 전에 멈춘다
    assert c.put(heads, json={"cells": [BODY], "role": "rowhead"}).status_code == 200           # 다시 지정 — 새 도장(지금 자리)
    assert table_heads.load(s.id)["stamps"][TID][BODY]["at"] == [3, 0, 4, 1]
    p = c.post(prune, json={"dry": True}).json()
    assert p["held"] == []
    r = c.post(prune, json=_go(p))
    assert r.status_code == 400 and "지울 빈 줄이 없습니다" in r.json()["detail"]                 # 보류가 풀리면 전과 같은 답
    assert c.post(f"/api/docs/{d}/undo").status_code == 200                                     # 실행 취소 — 그 칸이 9행으로 돌아가 지금 도장(3행)과 다시 어긋난다
    assert c.post(prune, json={"dry": True}).json()["held"] == [{"cell": BODY, "role": "rowhead", "why": "자리가 바뀜"}]
