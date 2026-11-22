"""넣을 구성 선택(spec_병합 ② §4-1 — app/merge_take.py): 고른 기관 · 단계 · 차년도 밖의 자리를 자리 연결 · 넣기 계획이 건너뛰는가. 2026-11-21 사용자 "이관, 병합을 할떄는 어떤 구성을 추출해서 넣을건지에 대한 것이
매칭하기 전에 결정되어야 하는데.. 이걸 선택하는 도구가 있었으면 좋겠어" → 답 「넣을 범위」 · 「전부 넣음」. 순수 셈 + 저장소 안 작은 쌍(merge_data.small — 2년 · 기관 셋)으로."""
import pytest

import merge_data as M
from app import merge_fill as F
from app import merge_fixed as MX
from app import merge_pairs as P
from app import merge_tables as MT
from app import merge_take as TK
from app import task_options

V2 = {"stages": [2, 2], "orgs": {"lead": "㈜인텍", "joint": ["가나대", "다라연"]}}   # 2단계 4년 · 기관 셋


def test_choices_come_from_the_project_configuration():
    c = TK.choices(V2)
    assert [o["name"] for o in c["org"]] == ["㈜인텍", "가나대", "다라연"] and [s["n"] for s in c["stage"]] == [1, 2]
    assert [(y["n"], y["stage"]) for y in c["year"]] == [(1, 1), (2, 1), (3, 2), (4, 2)] and c["year"][2]["name"] == "3차년도(2단계 1차년도)"
    assert TK.choices(None) == {"org": [], "stage": [], "year": []} and TK.choices({"stages": [3], "orgs": {"lead": "가", "joint": []}})["year"][0]["name"] == "1차년도"


def test_clean_keeps_only_what_narrows_and_refuses_unknown_values():
    assert TK.clean(None, V2) is None and TK.clean({}, V2) is None
    assert TK.clean({"year": [2, 2, 1]}, V2) == {"year": [1, 2]} and TK.clean({"year": [4, 3, 2, 1]}, V2) is None   # 모두 고름 = 전부
    assert TK.clean({"org": ["가나대"], "stage": [1, 2]}, V2) == {"org": ["가나대"]} and TK.clean({"org": ["인텍"]}, V2) == {"org": ["㈜인텍"]}   # 이름은 ㈜ 를 떼고 견주고 구성의 이름으로
    for bad in ({"year": [5]}, {"org": ["없는 기관"]}, {"stage": []}, {"year": "2"}, {"year": [True]}, {"dept": [1]}, ["year"], {"org": [3]}):
        with pytest.raises(ValueError):
            TK.clean(bad, V2)
    assert TK.clean({"year": [9]}) == {"year": [9]}   # 값 없이는 꼴만(저장된 것을 읽을 때)


def test_allowed_reads_values_and_leaves_unknown_places_alone():
    A = TK.allowed({"year": [2]}, V2)
    assert A.active and A.ident(("year", 2)) and not A.ident(("year", 1)) and not A.ident(("year", 3))
    assert A.ident(("org", "가나대")) and A.ident(None) and A.ident(("raw", "x")) and A.ctx({"org": None, "year": None}) and A.ctx(None)   # 기관은 안 골랐다 · 값을 모르는 자리는 넣는다
    assert A.ident(("stage", 1)) and not A.ident(("stage", 2)) and not A.ctx({"org": "가나대", "year": 3})   # 2차년도만 = 1단계의 자리만
    B = TK.allowed({"stage": [2], "org": ["㈜인텍"]}, V2)
    assert B.ident(("year", 3)) and B.ident(("year", 4)) and not B.ident(("year", 2)) and B.ident(("org", "인텍")) and not B.ident(("org", "가나대"))
    assert not B.ctx({"org": "가나대", "year": 3}) and B.ctx({"org": "인텍", "year": None})
    off = TK.allowed(None, V2)
    assert not off.active and off.ident(("year", 9)) and off.ctx({"org": "x", "year": 9})
    assert TK.text(None) == "전부" and TK.text({"org": ["가나대"], "year": [3]}, V2) == "기관: 가나대 / 차년도: 3차년도(2단계 1차년도)"


@pytest.fixture(scope="module")
def small():
    d = M.small()
    s = {side: P.summarize(d[side]["doc"].blocks(), d[side]["graph"], d[side]["tables"], d["values"]) for side in ("to", "from")}
    return d, s


def _pairs(s, take, values):
    v = P.pair(s["to"], s["from"])
    A = TK.allowed(take, values)
    return v, A, TK.narrow(v, s["to"], A)


def test_narrow_marks_groups_and_items_outside_the_selection(small):
    d, s = small
    base, _, n0 = _pairs(s, None, d["values"])
    assert n0 == 0 and "outside" not in base["counts"] and all(g["status"] != "outside" for g in base["groups"])   # 고른 것이 없으면 전과 같다
    v, A, n = _pairs(s, {"year": [2]}, d["values"])
    by = {t["key"]: t for t in s["to"]}
    assert n == v["counts"]["outside"] and sum(v["counts"].values()) == len(v["groups"])
    seen = 0
    for g, g0 in zip(v["groups"], base["groups"]):
        t = by.get((g.get("to") or {}).get("key"))
        if t is None:
            assert g["status"] == g0["status"]   # 원본에만 있는 묶음은 그대로
            continue
        idents = [it.get("ident") for it in t["items"]]
        if g["status"] == "outside":
            assert g["was"] == g0["status"] and (not A.ctx(g["ctx"]) or all(not A.ident(i) for i in idents)) and all(it["status"] == "outside" for it in g["items"])
        else:
            assert g["status"] == g0["status"] and A.ctx(g["ctx"])
            for it, it0, i in zip(g["items"], g0["items"], idents):
                assert it["status"] == ("outside" if not A.ident(i) else it0["status"])
                seen += it["status"] == "outside"
    assert n + seen > 0   # 1차년도의 자리가 실제로 빠졌다


def test_plans_skip_what_is_outside_and_are_unchanged_without_a_selection(small):
    d, s = small
    base, _, _ = _pairs(s, None, d["values"])
    v, A, _ = _pairs(s, {"year": [2]}, d["values"])
    f0, f1 = (F.plan(d["to"], d["from"], d["values"], d["values"], x) for x in (base, v))
    assert f0["counts"]["outside"] == 0 and f1["counts"]["todo"] <= f0["counts"]["todo"]
    out = [r for r in f1["items"] if r["skip"] == "outside"]
    assert all(r["detail"] == TK.OUT and not r["src"] for r in out)
    todo = {r["to"] for r in f1["items"] if r["skip"] is None}
    assert todo <= {r["to"] for r in f0["items"] if r["skip"] is None}   # 넣는 것은 줄기만 한다
    t0 = MT.plan(d["to"], d["from"], d["values"], d["values"], base)
    t1 = MT.plan(d["to"], d["from"], d["values"], d["values"], v, take=A)
    same = MT.plan(d["to"], d["from"], d["values"], d["values"], base, take=None)
    assert (same["cells"], same["rows"], same["counts"]) == (t0["cells"], t0["rows"], t0["counts"]) and t0["counts"]["skipped"]["outside"] == 0
    assert {c["to"] for c in t1["cells"]} <= {c["to"] for c in t0["cells"]} and len(t1["rows"]) <= len(t0["rows"])
    assert f1["counts"]["outside"] + t1["counts"]["skipped"]["outside"] + v["counts"]["outside"] > 0
    assert all("1차년도" not in str(c.get("item") or "") for c in t1["cells"])   # 1차년도의 칸은 하나도 안 넣는다
    T, Fm = {**d["to"], "values": d["values"]}, {**d["from"], "values": d["values"]}
    x0, x1 = MX.plan(T, Fm), MX.plan(T, Fm, take=A)
    assert x0["counts"]["skipped"]["outside"] == 0 and x1["counts"]["cells"] <= x0["counts"]["cells"]
    assert all(t["why"] == "outside" and t["status"] == "none" for t in x1["tables"] if not A.ctx(t["ctx"]))


def test_the_selection_is_kept_per_bundle_beside_the_llm_skips(tmp_path, monkeypatch):
    work = {"id": "aaaaaaaaaaaa", "task": {"project": "넣을 구성", "job": "plan_to_report", "round": 1}}
    assert task_options.flow(work) == {"llmSkip": [], "take": None, "caption": None}
    assert task_options.flow_take(work, {"year": [2]}) == {"year": [2]} and task_options.flow(work)["take"] == {"year": [2]}
    assert task_options.flow_skip(work, "bbbbbbbbbbbb", True) == ["bbbbbbbbbbbb"] and task_options.flow(work) == {"llmSkip": ["bbbbbbbbbbbb"], "take": {"year": [2]}, "caption": None}
    assert task_options.flow_skip(work, "bbbbbbbbbbbb", False) == [] and task_options.flow(work)["take"] == {"year": [2]}   # 건너뛰기를 다 풀어도 넣을 구성은 남는다
    assert task_options.flow_take(work, None) is None and task_options.flow(work) == {"llmSkip": [], "take": None, "caption": None}
    other = {"id": "cccccccccccc", "task": {"project": "넣을 구성", "job": "plan_to_report", "round": 2}}
    task_options.flow_take(work, {"org": ["가나대"]})
    assert task_options.flow(other)["take"] is None   # 다른 라운드 = 다른 묶음


def test_endpoints_keep_the_selection_narrow_the_links_and_drop_the_old_plan(monkeypatch):
    """끝점(GET · PUT /api/works/{wid}/flow/take — merge_api.take_view · take_put): 고를 값 · 저장 · 구성에 없는 값 400 · 연결 목록이 고른 구성으로 좁아짐(범위 밖) · 입력의 판이 바뀜(세워 둔 계획은 못 쓴다) ·
    좁혀 고른 것이 대상 차년도 · 다음 연도의 자리를 빼면 알림. 대상 차년도(year)는 목적 문서의 구성 입력 값의 당해 차년도로 적힌다."""
    from fastapi.testclient import TestClient

    from app import merge_api, server
    server.DOCS.clear()
    merge_api._CACHE.clear()
    c = TestClient(server.app)
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        ids[side] = c.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])}).json()["docId"]
        assert c.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "넣을 구성 끝점"}).status_code == 200
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):   # 분석 결과 · 구분 값만 시험 자료 것(문서는 세션의 살아 있는 문서)
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    to, url = ids["to"], f"/api/works/{ids['to']}/flow/take"
    v = c.get(url).json()
    assert v["ready"] and v["take"] is None and v["text"] == "전부" and not v["active"] and [y["n"] for y in v["choices"]["year"]] == [1, 2] and len(v["choices"]["org"]) == 3 and v["notes"] == []
    assert c.get(f"/api/works/{ids['from']}/flow/take").json()["choices"] == v["choices"]   # 그 묶음의 어느 문서로 물어도 목적 문서의 것
    base = c.get(f"/api/docs/{to}/merge-links").json()
    assert base["take"] == {"take": None, "active": False, "text": "전부"} and "outside" not in base["counts"]
    key0 = merge_api.inputs_now(to)
    for bad in ({"take": {"year": [9]}}, {"take": {"org": ["없는 기관"]}}, {"take": {"year": []}}, {"year": 9}, {"year": "2"}, {}):
        assert c.put(url, json=bad).status_code == 400, bad
    assert c.put(url, json={"take": {"year": [1, 2]}}).json()["take"] is None   # 그 기준의 값을 모두 고름 = 전부
    got = c.put(url, json={"take": {"year": [1]}, "year": 1}).json()
    assert got["take"] == {"year": [1]} and got["active"] and got["text"] == "차년도: 1차년도" and got["year"] == 1 and got["notes"] == ["「다음 연도」 자리(2차년도)는 넣지 않습니다"]
    assert server._sess(to).division["settings"]["values"]["current"] == 1   # 대상 차년도 = 목적 문서의 당해 차년도
    assert merge_api.inputs_now(to) != key0   # 입력의 판이 바뀜 — 그 전에 세운 계획으로는 반영하지 못한다(409)
    v1 = c.get(f"/api/docs/{to}/merge-links").json()
    assert v1["take"]["text"] == "차년도: 1차년도" and v1["counts"]["outside"] + sum(it["status"] == "outside" for g in v1["groups"] for it in g["items"]) > 0
    assert sum(v1["counts"].values()) == len(v1["groups"]) and v1["counts"]["paired"] <= base["counts"]["paired"]
    plan = c.post(f"/api/docs/{to}/merge-links/plan").json()
    c.put(url, json={"take": None})
    assert c.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]}).status_code == 409   # 고른 것을 바꾼 뒤 — 옛 계획은 버려졌다
    two = c.put(url, json={"year": 2}).json()
    assert two["year"] == 2 and two["take"] is None and server._sess(to).division["settings"]["values"]["current"] == 2
    off = c.put(url, json={"take": {"year": [1]}}).json()
    assert off["notes"] == ["대상 차년도(2차년도)의 자리가 넣을 구성에서 빠져 있습니다"]
    assert c.get(f"/api/works/{to}/flow").json() is not None and c.get("/api/works/000000000000/flow/take").status_code == 404
