"""월별 일정 표를 스크립트로(spec_병합 ② §5-7 · app/merge_schedule.py) — 연차보고서 「2-1. 기술개발 추진 일정」 을 계획서의 **같은 차년도** 월별 일정 표에서 채운다(LLM 없음).
저장소 안 자료만(merge_data.small): 계획서 양식의 「1단계-1차년도」 일정 표(항목 아홉 — 앞의 둘에만 일정이 그어져 있다) ↔ 같은 값으로 반영한 연차보고서 서식(항목 다섯 자리 — 앞의 둘은 서식 예시).
계획 → 반영 → 다시 계획 · 계획 선과 실적 선 · 행 늘리기 · 예시 항목 · 사람이 쓴 항목 · 차년도 가리기를 본다."""
import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import merge_api, server
from app import merge_fixed as X
from app import merge_gaps as G
from app import merge_schedule as SC
from app import merge_table_map as MM
from app import merge_take as TK


def _sides(d, tgt, src, values=None):
    v = values or d["values"]
    to, frm = {**d["to"], "doc": tgt, "values": v}, {**d["from"], "doc": src, "values": v}
    return X._side(to), X._side(frm)


def _orig(doc):
    """올린 빈 양식의 칸(merge_api._orig 와 같은 꼴) — 서식 예시 판정의 근거."""
    out = {}

    def walk(seq):
        for b in seq:
            lines = b.get("borderFills") or {}
            for c in b.get("cells") or ():
                ln = lines.get(c.get("bf")) or {}
                out[c["id"]] = {"text": c.get("text") or "", "top": MM._kind(ln.get("t")), "bottom": MM._kind(ln.get("b"))}
                walk(c.get("blocks") or ())
    walk(doc.blocks())
    return out


def _state(S, tid):
    """목적 일정 표의 지금 모습 → [(일련번호, 개발 내용, 계획 선이 그어진 열들, 실적 선이 그어진 열들, 끝 열의 글)] — 항목마다."""
    sch = SC.read(S, tid)
    v, cols = sch["v"], sorted(c for cs in sch["months"].values() for c in cs)
    kind = {m["name"]: (m["type"], m["width"], m["color"]) for m in SC._marks(S, sch)}
    out = []
    for rows in sch["items"]:
        at = lambda r, c: v["at"].get((rows[r], c)) or {}  # noqa: E731
        line = lambda name, k: [c for c in cols if name in kind and MM._kind(at(k, c).get("bottom")) == kind[name]]  # noqa: E731
        out.append((at(0, 0).get("text", "").strip(), " ".join(at(0, 1).get("text", "").split()), line("당초계획", 0), line("개발실적", 1), at(0, v["cols"] - 1).get("text", "").strip()))
    return out


@pytest.fixture()
def pair():
    d = M.small()
    tgt, src = M.fresh(d["to"]), M.fresh(d["from"])
    T, F = _sides(d, tgt, src)
    tid = next(t["id"] for t in T["tables"] if t["id"] in T["idx"] and SC.read(T, t["id"]) and SC._marks(T, SC.read(T, t["id"])))
    return d, tgt, src, tid


def _source(F, year):
    """그 차년도 원본 일정 표의 항목 → [(이름, 일정이 그어진 달의 반 달 칸 차례 [(달, 몇째 칸)])]."""
    s = SC._sources(F, year, None)[0]["sch"]
    out = []
    for rows in s["items"]:
        name = " ".join((s["v"]["at"].get((rows[0], s["text"]["개발내용"])) or {}).get("text", "").split())
        out.append((name, [(m, k) for m, cs in sorted(s["months"].items()) for k, c in enumerate(cs) if SC._drawn(s, rows, c)]))
    return out


def test_reads_the_monthly_schedule_tables(pair):
    """일정 표로 읽는 것 = 월 머리 줄(1 … 12)이 있는 표 — 달마다의 열 · 글 열(일련번호 · 개발 내용) · 항목(세 행씩). 목적 표의 표시는 범례의 이름으로(「당초계획」 = 첫 경계의 점선 · 「개발실적」 = 둘째 경계).
    원본의 그 차년도 표는 월 머리 위의 「1단계-N차년도」 로 가린다(차년도마다 표가 따로 있다)."""
    d, tgt, src, tid = pair
    T, F = _sides(d, tgt, src)
    sch = SC.read(T, tid)
    assert sorted(sch["months"]) == list(range(1, 13)) and all(len(c) == 2 for c in sch["months"].values()) and sch["serial"] == 0
    assert {"일련번호", "개발내용", "달성도"} <= set(sch["text"]) and [len(r) for r in sch["items"]] == [3] * 5
    assert [(m["name"], m["boundary"]) for m in SC._marks(T, sch)] == [("당초계획", 0), ("개발실적", 1)]
    assert [len(SC._sources(F, y, None)) for y in (1, 2, 3)] == [1, 1, 0]
    assert SC._sources(F, 1, None)[0]["id"] != SC._sources(F, 2, None)[0]["id"]
    none = TK.allowed({"year": [2]}, d["values"])   # 「넣을 구성 선택」 에서 1차년도를 뺌 — 그 차년도의 표는 원본이 아니다
    assert not SC._sources(F, 1, none)


def test_plan_apply_and_replan_on_a_blank_form(pair):
    """등록된 빈 양식으로 올린 목적 문서(orig): 서식 예시 두 항목은 원본 항목으로 바뀌고(예시의 「100%」 와 선은 지워진다) 빈 항목 셋을 채운 뒤 모자란 넷은 마지막 빈 항목을 본떠 늘린다.
    계획 선은 원본에서 그어진 반 달 칸 그대로 · 실적 선도 같게 · 「달성도」 는 비운다(원본의 끝 열은 「기간」 — 다른 낱말이라 안 잇는다). 다시 계획하면 일 없음."""
    d, tgt, src, tid = pair
    T, F = _sides(d, tgt, src)
    orig = _orig(M.fresh(d["to"]))
    want = _source(F, 1)
    assert len(want) == 9 and sum(bool(m) for _, m in want) == 2
    p = SC.plan(T, F, orig, None)
    assert p["owned"] == [tid] and p["todo"] == 9 and not p["skipped"]
    assert (p["counts"]["items"], p["counts"]["done"], p["counts"]["write"], p["counts"]["rows"]) == (9, 0, 5, 4)
    row = p["tables"][0]
    assert (row["plan"], row["result"], row["year"], len(row["sources"])) == ("당초계획", "개발실적", 1, 1)
    done = SC.apply(tgt, src, p)
    assert done["rowsAdded"] == 4 and not done["skipped"] and done["cleared"] == 2 and done["shaped"] > 0
    T2, F2 = _sides(d, tgt, src)
    got = _state(T2, tid)
    cols = SC.read(T2, tid)["months"]
    assert [g[1] for g in got] == [n for n, _ in want] and [g[0] for g in got] == [str(i) for i in range(1, 10)]   # 원본 차례 그대로 · 일련번호
    for (_, name, plan, result, last), (_, marks) in zip(got, want):
        assert plan == result == sorted(cols[m][k] for m, k in marks), name   # 계획 선 = 원본의 그 반 달 칸 · 실적 선도 같게
        assert last == ""   # 달성도는 비운다(예시의 100% 도 지움)
    again = SC.plan(T2, F2, orig, None)
    assert again["todo"] == 0 and again["counts"]["done"] == 9


def test_written_items_are_kept_and_examples_need_a_blank_form(pair):
    """올린 원본이 등록된 빈 양식이 아니면(orig 없음) 글이 든 항목은 사람 글이다 — 건드리지 않는다: 이름이 같은 항목은 「이미 있음」 으로 세고(선 · 달성도를 덮지 않는다) 없는 항목만 빈 자리에 넣는다.
    사람이 고친 선도 다시 계획할 때 되돌리지 않는다."""
    d, tgt, src, tid = pair
    T, F = _sides(d, tgt, src)
    before = _state(T, tid)
    p = SC.plan(T, F, None, None)
    assert (p["counts"]["done"], p["counts"]["write"], p["counts"]["rows"]) == (2, 3, 4)   # 서식 예시 둘의 이름이 원본 양식의 예시와 같다
    SC.apply(tgt, src, p)
    T2, F2 = _sides(d, tgt, src)
    got = _state(T2, tid)
    assert got[:2] == before[:2] and got[0][4] == "100%"   # 그 두 항목은 그대로(예시의 선 · 달성도 포함)
    assert [g[1] for g in got] == [n for n, _ in _source(F, 1)]
    sch = SC.read(T2, tid)
    cell = sch["v"]["at"][(sch["items"][2][0], sch["months"][5][0])]
    tgt.set_cell_edges(cell["id"], {"bottom": {"type": "DASH", "width": "0.4 mm", "color": "#000000"}})   # 사람이 셋째 항목의 5월에 계획 선을 그음
    T3, F3 = _sides(d, tgt, src)
    assert SC.plan(T3, F3, None, None)["todo"] == 0 and sch["months"][5][0] in _state(T3, tid)[2][2]


def test_other_year_and_no_blank_item(pair):
    """목적 표의 차년도(「해당연도」 = 당해 차년도)가 바뀌면 그 차년도의 표에서 가져온다 — 원본에 그 차년도의 표가 없으면 이 길은 그 표를 맡지 않는다(다른 길에 맡긴다).
    본뜰 빈 항목이 없으면 넘치는 항목은 못 넣는다고 알린다(짐작해서 행을 만들지 않는다)."""
    d, tgt, src, tid = pair
    T, F = _sides(d, tgt, src, {**d["values"], "current": 2})
    p = SC.plan(T, F, _orig(M.fresh(d["to"])), None)
    assert p["tables"][0]["year"] == 2 and p["tables"][0]["sources"][0]["from"] == SC._sources(F, 2, None)[0]["id"]
    assert [w for w in p["fills"] if "2차 시제품" in w["name"]] or [g for g in p["grows"] if "2차 시제품" in g["name"]]
    T3, F3 = _sides(d, tgt, src, {**d["values"], "stages": [3], "period": {"start": "2026-03-01", "end": "2028-12-31"}, "current": 3})   # 3차년도 — 원본에 그 차년도의 일정 표가 없다
    assert SC.plan(T3, F3, None, None)["owned"] == []
    sch = SC.read(T, tid)
    for rows in sch["items"][2:]:   # 빈 항목 셋에 사람이 이름을 씀 — 본뜰 빈 항목이 없다
        tgt.set_text(sch["v"]["at"][(rows[0], 1)]["id"], "사람이 쓴 항목")
    T4, F4 = _sides(d, tgt, src)
    full = SC.plan(T4, F4, None, None)
    assert full["counts"]["write"] == 0 and full["counts"]["rows"] == 0 and full["counts"]["skipped"]["shape"] == 1 and full["tables"][0]["skipped"] == 7


def test_schedule_goes_through_the_merge_plan_and_owns_its_table(monkeypatch):
    """넣기 계획 · 반영(app/merge_api.py)에 일정 표 몫(`sched`)이 든다 — 그 표는 이 길이 **통째로 맡는다**: 저장된 표 대응(tableMaps)이 있어도 안 쓰이고 · 같은 이름 자리가 그 칸을 안 내고 ·
    빈 자리 검토가 그 표를 안 묻는다(한 표를 두 길이 쓰지 않게). 반영은 다른 몫과 같은 편집 하나(문서 전체 표준 검사 통과) · 다시 계획하면 일 없음."""
    server.DOCS.clear()
    merge_api._CACHE.clear()
    client = TestClient(server.app)
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        ids[side] = client.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])}).json()["docId"]
        client.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "일정 표 시험"})
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):   # 분석 결과·구분 값만 시험 자료 것(문서는 세션의 살아 있는 문서 — test_merge_api 와 같은 길)
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    to = ids["to"]
    first = client.post(f"/api/docs/{to}/merge-links/plan").json()
    sc = first["sched"]
    assert sc["counts"]["tables"] == 1 and sc["todo"] == 7 and first["todo"] >= sc["todo"] and (sc["counts"]["done"], sc["counts"]["write"], sc["counts"]["rows"]) == (2, 3, 4)
    tid = sc["tables"][0]["to"]
    merge_api._store(to, {**merge_api._store(to), "tableMaps": {tid: {"from": "t1690", "records": [{"to": [2, 3, 4], "from": [2, 3, 4], "example": False}], "grow": [], "fields": [{"to": 1, "from": 1, "kind": "text"}], "mark": ""}}})
    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert tid not in [t["to"] for t in plan["maps"]["tables"]] and plan["sched"]["todo"] == 7   # 표 대응 기록이 있어도 그 표는 일정 표 스크립트의 것
    assert not [t for t in plan["fixed"]["tables"] if t["to"] == tid and t.get("cells")]   # 같은 이름 자리도 그 칸을 안 낸다
    view, ctx = merge_api._view(to)
    with server._sess(to).lock:
        mp, _, fixed, (T, F) = merge_api._plan_parts(to, view, ctx[2], ctx[3], ctx[4])
        found = G.targets(T, F, fixed, skip=mp["sched"]["owned"])
    assert mp["sched"]["owned"] == [tid] and tid not in mp["open"] and tid not in {t["key"] for t in found["tables"]} and tid not in {s["table"] for s in found["slots"]}
    done = client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]})
    assert done.status_code == 200, done.text[:600]
    out = done.json()["sched"]
    assert (out["rowsAdded"], out["skipped"]) == (4, 0) and out["filled"] >= 7
    again = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert again["sched"]["todo"] == 0 and again["sched"]["counts"]["done"] == 9
