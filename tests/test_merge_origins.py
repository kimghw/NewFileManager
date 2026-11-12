"""원본 자리 지도(spec_작업 ② §12 「누른 자리 따라 보기」 · app/merge_origins.py · GET …/merge-links/origins): 목적 문서(연차보고서)의 자리 id → 원본 문서(사업계획서)의 자리 id.
저장소 안 자료만: merge_data.small 의 계획서(문단 묶음 항목마다 표식 줄)에 표지 칸 셋을 더 쓴 것(원본) ↔ 같은 값으로 반영한 연차보고서 서식(목적). 넣기 계획 → 반영을 한 **뒤에** 지도를 낸다 —
넣을 때 적어 둔 대응이 아니라 지금 두 문서의 짝을 다시 셈하므로, 넣은 뒤(목적 칸에 글이 찬 뒤)에도 같은 짝이 나와야 한다."""
import re

import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import merge_api, server
from app import merge_fill as MF
from app import merge_fixed as MX
from app import merge_origins as O
from app import merge_pairs as P
from app import merge_tables as MT
from app.division_profiles import _structure as structure

WRITE = {"중앙행정기관명": "산업통상부", "전문기관명": "한국산업기술기획평가원", "공고번호": "제2026-134호"}   # 표지의 머리 칸 글 → 그 오른쪽 칸에 쓸 글(test_merge_fixed 와 같은 칸)


def _bare(t):
    return re.sub(r"\d+\)$", "", re.sub(r"\s+", "", t or ""))


def _right_of(doc, head):
    tb = next(b for b in structure.iter_blocks(doc.blocks()) if b.get("type") == "table" and any(_bare(c.get("text")) == head for c in b["cells"]))
    h = next(c for c in tb["cells"] if _bare(c.get("text")) == head)
    return next(c["id"] for c in tb["cells"] if c["row"] <= h["row"] < c["row"] + c["rowSpan"] and c["col"] == h["col"] + h["colSpan"])


def _texts(doc):
    return {b["id"]: b.get("text") or "" for b in structure.iter_blocks(doc.blocks())}


def _pairs(to, frm, values):
    """연결 목록 — 2-2 기관 절(스크립트가 못 정함)은 사람 확정을 흉내 내 「② 개발 내용 및 범위」(1차년도)에 잇는다(test_merge_fill 과 같은 짝)."""
    s = {k: P.summarize(x["doc"].blocks(), x["graph"], x["tables"], values) for k, x in (("to", to), ("from", frm))}
    tk = next(x["key"] for x in s["to"] if x["kind"] == "paragraph" and x["dim"] == "org" and "추진 실적" in " ".join(x["path"]))
    fk = next(x["key"] for x in s["from"] if x["kind"] == "paragraph" and x["path"][-1:] == ["개발 내용 및 범위"] and x["ctx"]["year"] == 1)
    return P.pair(s["to"], s["from"], fixed={tk: {"from": fk, "source": "user", "anchor": "- (추진 내용)"}}), tk


@pytest.fixture(scope="module")
def sides():
    """(values, 목적 쪽, 원본 쪽) — 원본 = small 의 계획서 + 표지 칸 셋."""
    d = M.small()
    plan = M.fresh(d["from"])
    plan.blocks()
    for head, text in WRITE.items():
        plan.set_text(_right_of(plan, head), text)
    return d["values"], {**d["to"], "values": d["values"]}, {**M._side("origins-plan", plan, M.PLAN_FORM.name), "values": d["values"]}


@pytest.fixture(scope="module")
def filled(sides):
    """내용을 넣은 뒤 — (넣은 목적 쪽, 원본 쪽, 연결 목록, 넣은 기록, 넣기 전 계획들, 본문 반영 결과). 반영 차례 = merge_api.merge_apply(표 칸 → 같은 이름 자리 → 본문)."""
    values, to, frm = sides
    view, key = _pairs(to, frm, values)
    doc = M.fresh(to)
    doc.blocks()
    side = {**to, "doc": doc}
    fill, tabs = MF.plan(side, frm, values, values, view), MT.plan(side, frm, values, values, view)
    fixed = MX.plan(side, frm, tables_plan=tabs)
    MT.apply(doc, frm["doc"], tabs)
    rx = MX.apply(doc, frm["doc"], fixed)
    rf = MF.apply(doc, frm["doc"], fill)
    applied = {k: {**v, "ids": list(r["inserted"].get(k) or ())} for r in (rf, rx) for k, v in r["applied"].items()}
    return side, frm, view, applied, {"fill": fill, "tabs": tabs, "fixed": fixed, "key": key}, rf


def test_filled_cells_and_inserted_blocks_lead_back_to_their_source(filled):
    side, frm, view, applied, plans, rf = filled
    out = O.build(side, frm, view, applied=applied)
    m, now, src = out["map"], _texts(side["doc"]), _texts(frm["doc"])
    assert set(m) <= set(now) and set(m.values()) <= set(src)   # 두 문서에 지금 있는 자리만
    cells = [c for c in plans["fixed"]["cells"] if c["text"] in WRITE.values()]   # 표지 칸 셋 — 넣은 뒤(글이 같아 계획에는 할 일이 없다)에도 짝이 남는다
    assert len(cells) == len(WRITE) and all(m.get(c["to"]) == c["from"] and now[c["to"]].strip() == src[c["from"]].strip() == c["text"] for c in cells), cells
    assert not [c for c in MX.plan(side, frm, applied=applied)["cells"] if c["text"] in WRITE.values()]   # 계획은 그 칸을 더 안 넣는다 — 지도는 계획의 할 일이 아니라 짝을 본다
    rows = [r for r in plans["fill"]["items"] if r["group"] == plans["key"] and r["skip"] is None]
    assert len(rows) == 3
    for r in rows:   # 본문 항목 — 넣은 블록마다 원본 블록(표식 줄 「★병합시험 …」), 항목 라벨은 원본 항목 라벨
        new = rf["inserted"][r["to"]]
        assert len(new) == len(r["src"]) and [m.get(i) for i in new] == r["src"], (new, r["src"])
        assert now[new[0]].startswith(M.SMALL_MARK) and now[new[0]] == src[r["src"][0]]
        assert m.get(r["to"]) == r["from"]
    tables = {(t["to"], t["from"]) for t in plans["fixed"]["tables"] if t["status"] == "paired"}
    assert tables and all(m.get(a) == b for a, b in tables)   # 표 짝 — 칸 짝이 없는 칸을 누르면 그 표의 원본 표로
    assert out["counts"]["cells"] >= len(WRITE) and out["counts"]["blocks"] >= 3 and out["counts"]["tables"] >= 1, out["counts"]


def test_no_record_means_no_block_link_and_unpaired_places_are_absent(filled):
    side, frm, view, applied, plans, rf = filled
    bare = O.build(side, frm, view)["map"]   # 넣은 기록이 없으면(실행 취소 뒤 등 — merge_api._alive 가 걸러 냄) 넣은 블록은 안 잇는다. 칸 짝·라벨 짝은 문서에서 다시 셈하므로 그대로
    new = {i for r in plans["fill"]["items"] if r["skip"] is None for i in rf["inserted"].get(r["to"], ())}
    assert new and not new & set(bare)
    assert all(bare.get(c["to"]) == c["from"] for c in plans["fixed"]["cells"] if c["text"] in WRITE.values())
    m = O.build(side, frm, view, applied=applied)["map"]
    head = _right_of(side["doc"], "중앙행정기관명")
    tb = next(b for b in structure.iter_blocks(side["doc"].blocks()) if b.get("type") == "table" and any(c["id"] == head for c in b["cells"]))
    heads = [c["id"] for c in tb["cells"] if _bare(c.get("text")) in WRITE]   # 머리 칸(양식 글)은 짝이 아니다 — 그 표의 짝으로만 간다(화면이 칸 → 표로 올라감)
    assert heads and not set(heads) & set(m) and tb["id"] in m


def test_pairs_survive_the_fill(sides, filled):
    values, to, frm = sides
    side = filled[0]
    before, after = MX.pairs(to, frm), MX.pairs(side, frm)   # 넣기 전 · 넣은 뒤 — 같은 이름 자리의 표 짝·칸 짝이 그대로(넣은 뒤에만 사라지는 짝이 없다)
    assert set(before[0]) <= set(after[0]) and set(before[1]) <= set(after[1]), (set(before[1]) - set(after[1]))
    assert before[0] and len(before[1]) >= len(WRITE)
    was, tabs = filled[4]["tabs"], MT.plan(side, frm, values, values, filled[2])
    assert was["rows"] and not tabs["rows"]   # 이어 넣는 표 — 넣기 전에는 늘릴 행(목적 칸 id 가 아직 없다), 넣은 뒤에는 같은 행이 있어 할 일 없음
    got, now = {b: a for a, b in tabs["pairs"]}, _texts(side["doc"])
    for r in was["rows"]:   # 늘린 행의 칸 — 다시 계획하면 「이미 있는 같은 행」 으로 잡혀 칸끼리 짝(pairs)에 든다: 원본 칸 → 새로 생긴 목적 칸(글이 같다)
        assert r["cells"] and all(x["from"] in got and now[got[x["from"]]].strip() == x["text"].strip() for x in r["cells"]), r


@pytest.fixture
def client():
    server.DOCS.clear()
    merge_api._CACHE.clear()
    merge_api._ORIGINS.clear()
    return TestClient(server.app)


def test_origins_endpoint_after_apply_and_after_undo(client, monkeypatch):
    """끝점 — 까닭이 남으면 빈 지도(오류 아님) · 반영 뒤 넣은 블록이 원본 블록으로 · 실행 취소 뒤에는 그 블록이 지도에서 빠진다(문서는 안 바뀐다)."""
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        ids[side] = client.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])}).json()["docId"]
        client.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "따라 보기 시험"})
    to = ids["to"]
    cold = client.get(f"/api/docs/{to}/merge-links/origins")   # 헤딩·표 분석 전 — 자리 연결을 못 낸다
    assert cold.status_code == 200 and cold.json()["map"] == {} and "noHeadings" in cold.json()["reasons"] and cold.json()["from"]["work"] == ids["from"]
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):   # 분석 결과·구분 값만 시험 자료 것(문서는 세션의 살아 있는 문서 — test_merge_api 와 같은 길)
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    v = client.get(f"/api/docs/{to}/merge-links").json()
    g = next(x for x in v["groups"] if x["to"] and x["kind"] == "paragraph" and x["dim"] == "org" and "추진 실적" in " ".join(x["to"]["path"]))
    src = next(c["key"] for c in g["candidates"] if c["path"][-1:] == ["개발 내용 및 범위"])
    assert client.put(f"/api/docs/{to}/merge-links/{g['id']}", json={"from": src}).status_code == 200
    rev = client.get(f"/api/docs/{to}").json()["rev"]
    before = client.get(f"/api/docs/{to}/merge-links/origins").json()
    assert before["to"] == {"work": to, "rev": rev} and before["from"]["work"] == ids["from"] and before["map"] and not before["reasons"]
    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]}).status_code == 200
    after = client.get(f"/api/docs/{to}/merge-links/origins").json()
    assert client.get(f"/api/docs/{to}").json()["rev"] == rev + 1 == after["to"]["rev"]   # 지도를 읽어도 문서는 그대로(반영의 +1 뿐)
    now, was = _texts(server._sess(to).doc), _texts(server._sess(ids["from"]).doc)
    marks = [i for i, t in now.items() if t.startswith(M.SMALL_MARK)]
    assert marks and all(was.get(after["map"].get(i)) == now[i] for i in marks), marks   # 넣은 표식 줄 → 원본의 같은 표식 줄
    assert set(marks) - set(before["map"]) == set(marks) and after["counts"]["blocks"] >= len(marks)
    assert client.get(f"/api/docs/{to}/merge-links/origins").json() == after   # 같은 상태 — 담아 둔 것
    assert client.post(f"/api/docs/{to}/undo").status_code == 200
    undone = client.get(f"/api/docs/{to}/merge-links/origins").json()
    assert not set(marks) & set(undone["map"]) and undone["map"]   # 실행 취소로 사라진 블록은 지도에 없다(넣은 기록을 안 믿는다 — _alive) · 칸·라벨 짝은 그대로
