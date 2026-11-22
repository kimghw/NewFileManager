"""양식의 표 등록부(app/form_tables.py · app/form_tables_api.py — spec_테이블매니저 ② §11 「표 · 띠 정체」):
사슬 정규화(「※」 · 기관 이름 · 구분 기준 값의 번호) · 표 id 가 소속 헤딩 + 차례로 저절로 서고 문서의 블록 id 와 무관함 · 되풀이 자리 · 칸 안의 표 · 띠 id · 병합 방식 · 구분 기준 자리(엔진) ·
잇기(작성 글의 줄을 빼고 · 기관마다 되풀이 · 타입만 · 후보 여럿 · 양식에 없음) · 저장(원자적 · 깨진 파일은 덮지 않음 · 지우기는 옮김) · 끝점(빈 양식으로만 · 3단계 없음 · 낡은 결과 · 견본 양식으로 짓고 자기 자신을 다 잇는다)."""
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import form_tables as FT
from app import heading_forms as HF
from app import heading_guides as G
from app import heading_rules as R
from app import heading_runs as HR
from app import server

REPO = Path(__file__).parents[1]
PLAN = REPO / "samples" / "연구개발계획서_양식.hwpx"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_HEADINGS", str(tmp_path / "heads"))
    monkeypatch.setenv("NFM_LLM_BACKEND", "off")
    R._MEMORY.clear()
    G._MEMORY.clear()
    yield
    R._MEMORY.clear()
    G._MEMORY.clear()


# ---- 합성 3단계 결과 ----------------------------------------------------------------------------------------------------

def owner(*parts, division=None):
    *path, text = parts
    o = {"source": "stage2", "path": list(path), "text": text}
    if division:
        o["division"] = {"text": division[0], "basis": list(division[1])}
    return o


def tbl(tid, own, heads=("항목", "내용"), bands=None, depth=1, parent=None, before=""):
    cells = [{"id": f"{tid}h{i}", "row": 0, "col": i, "rs": 1, "cs": 1, "role": "colhead", "shaded": True, "text": h, "sub": "A"} for i, h in enumerate(heads)]
    cells += [{"id": f"{tid}f{i}", "row": 1, "col": i, "rs": 1, "cs": 1, "role": "field", "text": "", "sub": "A"} for i in range(len(heads))]
    subs = bands or [{"id": "A", "rows": [0, 2], "cols": [0, len(heads)], "kind": "matrix", "headerRows": 1, "headerCols": 0}]
    return {"id": tid, "rows": 2, "cols": len(heads), "depth": depth, "parentCell": parent, "owner": own, "labels": [], "before": before, "cells": cells, "subtables": subs}


def t3(*tables):
    return {"tables": list(tables)}


# ---- 사슬 ---------------------------------------------------------------------------------------------------------------

def test_norm_part_drops_names_notes_and_numbers_of_division_values():
    n = FT.norm_part
    assert n("[주관연구개발기관(한국선급)]") == n("[주관연구개발기관(기관명 기입)]") == "[주관연구개발기관]"
    assert n("[주관연구개발기관명 : 한국선급]") == n("[주관연구개발기관명 : ]") == "[주관연구개발기관명]"      # 쌍점 뒤(기관 이름)는 뗀다 — 빈 양식의 꼴과 같다
    assert n("[공동연구개발기관2(유엔젤)]") == n("[공동연구개발기관1]") == "[공동연구개발기관N]"
    assert n("(1) 1차년도") == n("(2) 2차년도") == "(N)N차년도" and n("[1단계(2026~2027) 목표]") == n("[2단계 목표]") == "[N단계목표]"
    assert n("2-2. 연구개발기관별 사용계획") == "2-2.연구개발기관별사용계획"       # 절 번호는 그대로(구분 기준 값의 번호가 아니다)
    assert n("(4) 간접비 ※ 기업만 작성하며, 아래 세부") == n("(4)  간접비") == "(4)간접비"
    assert FT.chain_of(None) == [(FT.NONE, FT.NONE)] and FT.chain_of({"root": True}) == [(FT.ROOT, FT.ROOT)]


# ---- 짓기 ---------------------------------------------------------------------------------------------------------------

def test_build_ids_come_from_the_owner_heading_and_order_not_block_ids():
    a = owner("1. 개요", "1-1. 목표")
    doc = t3(tbl("t1", a), tbl("t2", a, heads=("구분", "값")), tbl("t3", owner("2. 계획")))
    reg = FT.build("연구개발계획서", doc)
    ids = [e["id"] for e in reg["tables"]]
    assert len(set(ids)) == 3 and all(i.startswith("tf") for i in ids)
    assert [e["name"] for e in reg["tables"]] == ["1-1. 목표 #1", "1-1. 목표 #2", "2. 계획"]
    assert reg["tables"][0]["path"] == ["1. 개요", "1-1. 목표"] and reg["tables"][0]["order"] == 1 and reg["tables"][1]["order"] == 2
    renamed = t3(*({**t, "id": "x" + t["id"]} for t in doc["tables"]))          # 문서의 블록 id 가 달라도 같은 id(소속 헤딩 + 차례)
    assert [e["id"] for e in FT.build("연구개발계획서", renamed)["tables"]] == ids
    assert [e["id"] for e in FT.build("연차보고서", doc)["tables"]] != ids          # 양식마다 따로
    assert reg["counts"]["tables"] == 3 and reg["version"] == FT.VERSION


def test_build_repeat_nested_bands_kinds_and_engine_places():
    y1, y2 = owner("[1단계]", "(1) 1차년도"), owner("[1단계]", "(2) 2차년도")
    two = [{"id": "Q", "rows": [1, 2], "cols": [0, 2], "kind": "form", "headerRows": 0, "headerCols": 1},
           {"id": "P", "rows": [0, 1], "cols": [0, 2], "kind": "title", "headerRows": 0, "headerCols": 0}]
    outer = tbl("t1", y1, bands=two)
    inner = tbl("t9", y1, depth=2, parent="t1f0")
    doc = t3(outer, tbl("t2", y2), inner)
    kinds = [{"table": "t1", "kind": "byDivision", "subs": [{"sub": "Q", "kind": "byDivision", "basis": ["org"], "axes": [{"basis": "org", "on": "row", "values": 2}]},
                                                             {"sub": "P", "kind": "common", "basis": [], "axes": []}]}]
    groups = [{"kind": "rows", "dim": "org", "table": "t1", "container": None, "items": []},
              {"kind": "paragraph", "dim": "year", "table": None, "container": "body", "items": [{"scope": {"t1", "p1"}}, {"scope": {"t2"}}]}]
    reg = FT.build("양식", doc, kinds=kinds, groups=groups)
    top = [e for e in reg["tables"] if not e["host"]]
    assert len(top) == 1 and top[0]["repeat"] == 2 and top[0]["from"]["tables"] == ["t1", "t2"]   # 「(1) 1차년도」 · 「(2) 2차년도」 아래 같은 차례 — 한 항목
    e = top[0]
    assert [b["at"] for b in e["subs"]] == ["A", "B"] and [b["kind"] for b in e["subs"]] == ["title", "form"]   # 좌표 차례로 다시 매김(LLM 이 준 P · Q 가 아니다)
    assert e["subs"][1]["id"] == e["id"] + "/B" and e["subs"][1]["merge"] == "byDivision" and e["subs"][0]["merge"] == "common" and e["kind"] == "byDivision"
    assert {"dim": "org", "kind": "rows"} in e["division"]["engine"] and {"dim": "year", "kind": "section"} in e["division"]["engine"]
    nest = [x for x in reg["tables"] if x["host"]]
    assert len(nest) == 1 and nest[0]["id"] == e["id"] + "›1" and nest[0]["name"] == "칸 안의 표 #1"
    assert reg["counts"]["repeated"] == 1 and reg["counts"]["nested"] == 1 and reg["counts"]["engine"] == 1


# ---- 잇기 ---------------------------------------------------------------------------------------------------------------

def test_link_drops_written_lines_and_follows_repeats():
    main = owner("7. 연구개발기관 현황", "[공동연구개발기관1]", division=("[공동연구개발기관1]", ["org"]))
    reg = FT.build("양식", t3(tbl("b1", owner("1. 개요")), tbl("b2", main, heads=("성명", "직위"))))
    doc = t3(tbl("d1", owner("1. 개요", "o 스마트쉽 솔루션 서비스")),                                     # 작성 글의 줄 「o …」 — 등록부에 없는 줄은 뺀다
             tbl("d2", owner("7. 연구개발기관 현황", "[공동연구개발기관1(유엔젤)]"), heads=("성명", "직위")),
             tbl("d3", owner("7. 연구개발기관 현황", "[공동연구개발기관2(랩오투원)]"), heads=("성명", "직위")))   # 기관마다 되풀이 — 같은 항목의 둘째
    got = FT.link(reg, doc)
    e1, e2 = (e["id"] for e in reg["tables"])
    assert got["links"]["d1"]["id"] == e1 and got["links"]["d1"]["how"] == "path" and got["links"]["d1"]["sure"]
    assert (got["links"]["d2"]["id"], got["links"]["d2"]["occ"]) == (e2, 1) and (got["links"]["d3"]["id"], got["links"]["d3"]["occ"]) == (e2, 2)
    assert got["missing"] == [] and got["counts"] == {"path": 3}


def test_link_type_only_ambiguous_and_unknown():
    reg = FT.build("양식", t3(tbl("b1", owner("1. 개요"), heads=("가", "나")), tbl("b2", owner("2. 계획"), heads=("다", "라")),
                             tbl("b3", owner("3. 기타"), heads=("다", "라"))))
    doc = t3(tbl("d1", owner("9. 고친 제목"), heads=("가", "나")),          # 사슬이 등록부에 없음 + 타입이 하나뿐 → 타입만(확실하지 않음)
             tbl("d2", owner("9. 고친 제목"), heads=("다", "라")),          # 타입이 둘 → 후보 여럿
             tbl("d3", owner("9. 고친 제목"), heads=("마", "바")))          # 어디에도 없음
    got = FT.link(reg, doc)["links"]
    ids = [e["id"] for e in reg["tables"]]
    assert (got["d1"]["id"], got["d1"]["how"], got["d1"]["sure"]) == (ids[0], "typeOnly", False)
    assert got["d2"]["id"] is None and got["d2"]["how"] == "ambiguous" and set(got["d2"]["cands"]) == {ids[1], ids[2]}
    assert got["d3"]["id"] is None and got["d3"]["how"] == "unknown" and got["d3"]["cands"] == []
    swapped = FT.link(reg, t3(tbl("d4", owner("1. 개요"), heads=("다", "라"))))["links"]["d4"]   # 사슬 · 차례가 맞는데 타입이 다름 — 이어 주되 확실하지 않음
    assert (swapped["id"], swapped["how"], swapped["sure"]) == (ids[0], "path", False)


# ---- 저장 ---------------------------------------------------------------------------------------------------------------

def test_save_load_broken_and_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_FORMS", str(tmp_path / "f"))
    reg = FT.build("연구개발계획서", t3(tbl("t1", owner("1. 개요"))))
    saved = FT.save("연구개발계획서", reg)
    p = tmp_path / "f" / "연구개발계획서.tables.json"
    assert p.is_file() and FT.load("연구개발계획서")["tables"] == saved["tables"] and saved["at"] > 0 and FT.load("연차보고서") is None
    assert not list((tmp_path / "f").glob("*.tmp"))
    p.write_text("{깨짐", encoding="utf-8")
    with pytest.raises(FT.Broken):
        FT.load("연구개발계획서")
    with pytest.raises(FT.Broken):
        FT.save("연구개발계획서", reg)                                    # 깨진 파일은 덮지 않는다
    assert p.read_text(encoding="utf-8") == "{깨짐"
    p.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    moved = FT.remove("연구개발계획서")
    assert moved.startswith("연구개발계획서.tables.json.removed-") and not p.exists() and (tmp_path / "f" / moved).is_file() and FT.remove("연구개발계획서") is None
    assert HF.listing() == []                                            # 등록부 파일(*.tables.json)은 양식 정보 목록(*.md)에 안 든다
    with pytest.raises(ValueError):
        FT.path_of("../밖")
    monkeypatch.setenv("NFM_FORMS", "off")
    with pytest.raises(ValueError):
        FT.save("연구개발계획서", reg)


# ---- 끝점 ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    forms = tmp_path / "forms"
    forms.mkdir(exist_ok=True)
    shutil.copy(REPO / "forms" / "연구개발계획서.md", forms / "연구개발계획서.md")   # 견본 양식의 sha256 이 이 양식 정보의 match 에 있다(등록된 빈 양식)
    monkeypatch.setenv("NFM_FORMS", str(forms))
    server.DOCS.clear()
    yield TestClient(server.app)
    server.DOCS.clear()


def _open(c):
    r = c.post("/api/docs", files={"file": (PLAN.name, PLAN.read_bytes())})
    assert r.status_code == 200, r.text[:300]
    return r.json()["docId"]


def test_api_build_from_the_blank_form_and_link_itself(client, monkeypatch):
    c = client
    d = _open(c)
    v = c.get(f"/api/docs/{d}/form-tables").json()
    assert v["form"]["key"] == "연구개발계획서" and v["registry"] is None and v["missing"] == "registry" and v["blank"] == "sha256"
    r = c.post(f"/api/docs/{d}/form-tables/build", json={})
    assert r.status_code == 409 and "표 구조" in r.json()["detail"]                     # 3단계 결과 없음
    s = server._sess(d)
    HR.run_sync(s, 3, False)
    n = len(HR.tables(s)["tables"])
    r = c.post(f"/api/docs/{d}/form-tables/build", json={})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["blank"] == "sha256" and r.json()["summary"]["counts"]["tables"] == n and r.json()["summary"]["source"]["llm"] is False
    reg = c.get("/api/forms/연구개발계획서/tables").json()
    ids = [e["id"] for e in reg["tables"]]
    assert len(ids) == n and len(set(ids)) == n
    assert all(b["id"].startswith(e["id"] + "/") for e in reg["tables"] for b in e["subs"]) and sum(len(e["subs"]) for e in reg["tables"]) == reg["counts"]["subs"]
    assert {e["kind"] for e in reg["tables"]} >= {"perOrg", "byDivision", "sum", "common"}          # 병합 방식(머리글의 꼴 — 빈 양식에는 프로젝트 구성 값이 없다)
    assert reg["counts"]["engine"] > 0 and any(p["kind"] == "section" and p["dim"] == "org" for e in reg["tables"] for p in e["division"]["engine"])   # 기관마다 한 벌인 절
    assert c.post(f"/api/docs/{d}/form-tables/build", json={}).status_code == 200
    assert [e["id"] for e in c.get("/api/forms/연구개발계획서/tables").json()["tables"]] == ids     # 다시 지어도 같은 id
    me = c.get(f"/api/docs/{d}/form-tables").json()
    assert me["counts"] == {"path": n} and me["missing_entries"] == [] and "stale" not in me
    assert all(v["sure"] for v in me["links"].values()) and set(me["entries"]) == set(ids)
    pid = next(b["id"] for b in s.doc.blocks() if b["type"] == "paragraph" and b.get("text"))
    assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "고친 글"}).status_code == 200
    assert c.get(f"/api/docs/{d}/form-tables").json()["stale"] is True                     # 낡은 3단계 결과 — 그대로 잇고 알린다
    r = c.post(f"/api/docs/{d}/form-tables/build", json={})
    assert r.status_code == 409 and "바뀌었" in r.json()["detail"]                          # 등록부는 빈 양식 그대로의 표로만


def test_api_refuses_a_document_that_is_not_the_blank_form(client, monkeypatch):
    from app import form_tables_api as API
    c = client
    d = _open(c)
    HR.run_sync(server._sess(d), 3, False)
    monkeypatch.setattr(API, "blank_of", lambda s, form, blocks: None)
    r = c.post(f"/api/docs/{d}/form-tables/build", json={})
    assert r.status_code == 409 and "빈 양식" in r.json()["detail"] and c.get("/api/forms/연구개발계획서/tables").status_code == 404
    r = c.post(f"/api/docs/{d}/form-tables/build", json={"force": True})
    assert r.status_code == 200 and r.json()["blank"] == "forced"
    assert c.delete("/api/forms/연구개발계획서/tables").json()["ok"] is True
    assert c.get("/api/forms/연구개발계획서/tables").status_code == 404 and c.delete("/api/forms/연구개발계획서/tables").status_code == 404
    assert c.get("/api/forms/..%2F밖/tables").status_code in (400, 404)


def test_api_document_without_form(client, monkeypatch):
    c = client
    d = _open(c)
    monkeypatch.setattr(HF, "for_session", lambda s: None)
    assert c.get(f"/api/docs/{d}/form-tables").json() == {"form": None, "registry": None, "missing": "form"}
    assert c.post(f"/api/docs/{d}/form-tables/build", json={}).status_code == 409
