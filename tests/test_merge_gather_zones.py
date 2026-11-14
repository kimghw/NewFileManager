"""취합 — 기관 구역 표시(spec_취합 ② §9-2 · `GET /api/docs/{취합본}/gather/zones`): 기관이 작성하는 구역 · 표 안 기관 칸 · 기관 문서에서 넣은 내용(남은 것 / 없어진 것).
자료는 test_merge_gather_api 와 같다(gather_data — 값(기관 셋)을 반영한 양식 = 기준본, 그 사본을 고쳐 다시 연 것 = 기관 문서)."""
import pytest
from fastapi.testclient import TestClient

import gather_data as D
import merge_data as M
from app import merge_gather_api as GA
from app import server
from test_merge_gather_api import _master, _part, _edit_a, _upload

J1, J2, LEAD = D.J1, D.J2, D.LEAD


@pytest.fixture
def client():
    server.DOCS.clear()
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS, GA._ZONES):
        box.clear()
    return TestClient(server.app)


def _zones(c, to):
    r = c.get(f"/api/docs/{to}/gather/zones")
    assert r.status_code == 200, r.text
    return r.json()


def _top(to):
    return [b for b in server._sess(to).doc.blocks() if not b.get("captionOf")]


def test_zones_cover_each_org_and_leave_common_places_out(client):
    c = client
    to, _ = _master(c)
    z = _zones(c, to)
    assert set(z) == {"rev", "values", "orgs", "zones", "cells", "applied", "counts", "reasons"} and z["reasons"] == [] and z["rev"] == 0
    assert [(o["key"], o["role"]) for o in z["orgs"]] == [(LEAD, "lead"), (J1, "joint"), (J2, "joint")] and z["values"]["orgs"]["joint"] == [J1, J2]
    assert {x["org"] for x in z["zones"] if x["kind"] == "org"} == {LEAD, J1, J2}   # 기관마다 구역이 있다
    top = _top(to)
    ids = {b["id"] for b in top}
    in_zone = [i for x in z["zones"] for i in x["ids"]]
    assert set(in_zone) <= ids and len(in_zone) == len(set(in_zone))   # 실제 블록 · 한 구역에만
    for x in z["zones"]:
        assert set(x) == {"org", "kind", "year", "stage", "ids", "path", "text"} and x["ids"] and x["kind"] in ("org", "unknown")
        assert (x["org"] is None) == (x["kind"] == "unknown") and len(x["text"]) <= 60 and isinstance(x["path"], list)
    for a, b in zip(z["zones"], z["zones"][1:]):   # 같은 기관이 이어지면 한 구역 — 이웃한 두 구역은 기관이 다르거나 사이에 공통 블록이 있다
        if (a["kind"], a["org"]) == (b["kind"], b["org"]):
            order = [x["id"] for x in top]
            assert order.index(b["ids"][0]) > order.index(a["ids"][-1]) + 1
    j1 = D.nxt(server._sess(to).doc, D.para(server._sess(to).doc, f"[공동연구개발기관1({J1})]", 0))   # 가나대 1차년도 자리(기관 문서 A 가 채우는 곳)
    assert any(j1 in x["ids"] and x["org"] == J1 for x in z["zones"])
    common = D.nxt(server._sess(to).doc, D.para(server._sess(to).doc, "□ 필요성"))   # 공통 자리
    assert common not in in_zone
    cells = {c_["id"] for b in top if b["type"] == "table" for c_ in b["cells"]}
    tables = {b["id"] for b in top if b["type"] == "table"}
    for tid, row in z["cells"].items():   # 표 안 기관 칸(있으면)
        assert tid in tables and all(x["id"] in cells and x["kind"] in ("org", "unknown") for x in row)
    assert z["counts"] == {"zones": len(z["zones"]), "blocks": len(in_zone), "cells": sum(len(v) for v in z["cells"].values()), "applied": 0} and z["applied"] == []


def test_zones_use_input_values_before_the_divisions_are_applied_and_cache(client, monkeypatch):
    c = client
    to = _upload(c, "프레임.hwpx", D.base()["side"]["bytes"])
    z = _zones(c, to)
    assert z["reasons"] == ["noValues"] and z["values"] is None and z["zones"] == [] and z["orgs"] == [] and z["cells"] == {} and z["applied"] == []
    assert z["counts"] == {"zones": 0, "blocks": 0, "cells": 0, "applied": 0}
    assert c.put(f"/api/docs/{to}/divisions/settings", json={"values": D.VALUES}).status_code == 200   # 반영 전 — 입력 값으로
    calls = []
    make = GA.F.make
    monkeypatch.setattr(GA.F, "make", lambda side: calls.append(1) or make(side))
    z = _zones(c, to)
    assert z["reasons"] == [] and {x["org"] for x in z["zones"] if x["kind"] == "org"} == {LEAD, J1, J2}
    assert _zones(c, to) == z and len(calls) == 1   # 같은 차례·값·분석이면 다시 안 센다
    first = next(b["id"] for b in _top(to) if b["type"] == "paragraph" and b["text"].strip())
    assert c.patch(f"/api/docs/{to}/blocks/{first}", json={"text": "고친 표지 글"}).status_code == 200
    assert _zones(c, to)["rev"] == 1 and len(calls) == 2   # 문서가 바뀌면 다시
    docx = _upload(c, "조사서.docx", (M.ROOT / "samples" / "기술수요조사서.docx").read_bytes())
    z = _zones(c, docx)
    assert z["reasons"] == ["unsupportedForm"] and z["zones"] == [] and z["applied"] == []


def test_applied_contents_are_listed_and_turn_gone_after_undo(client):
    c = client
    to, _ = _master(c)
    A = _part(c, to, "기관A_가나대.hwpx", _edit_a, orgs=[J1])
    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]}).status_code == 200
    z = _zones(c, to)
    assert z["rev"] == 1 and len(z["applied"]) == 4 and z["counts"]["applied"] == 4
    alive = {b["id"] for b in _top(to)} | {x["id"] for b in _top(to) if b["type"] == "table" for x in b["cells"]}
    for a in z["applied"]:
        assert set(a) == {"part", "name", "orgs", "key", "kind", "at", "ids", "gone"}
        assert a["part"] == A and a["name"] == "기관A_가나대.hwpx" and a["orgs"] == [J1] and a["gone"] == 0 and a["ids"] and set(a["ids"]) <= alive and a["at"]
    assert sorted(a["kind"] for a in z["applied"]) == ["cells", "filled", "filled", "rows"]
    zone_of = {i: x for x in z["zones"] for i in x["ids"]}
    filled = [a for a in z["applied"] if a["kind"] == "filled"]
    j1 = next(a for a in filled if any(J1 in (b.get("text") or "") and "1차년도" in (b.get("text") or "") for b in _top(to) if b["id"] in a["ids"]))
    assert all(zone_of.get(i, {}).get("org") == J1 for i in j1["ids"])   # 가나대 자리에 넣은 글 = 가나대 구역 안
    assert c.post(f"/api/docs/{to}/undo").status_code == 200
    z = _zones(c, to)
    by = {a["kind"]: a for a in z["applied"]}
    assert len(z["applied"]) == 4 and all(a["ids"] == [] and a["gone"] > 0 for a in z["applied"] if a["kind"] in ("filled", "rows"))   # 넣은 블록·행이 없어짐
    assert by["cells"]["ids"] and by["cells"]["gone"] == 0   # 칸은 그대로 있다(글만 되돌아감)
    assert z["counts"]["applied"] == 1
