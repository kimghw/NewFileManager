"""자리 연결 API(spec_병합 ② §8 — app/merge_api.py): 문서별 까닭 · 연결 목록 · 사람 고침."""
import pytest
from fastapi.testclient import TestClient

import merge_data as M
from app import merge_api, server


@pytest.fixture
def client():
    server.DOCS.clear()
    merge_api._CACHE.clear()
    return TestClient(server.app)


def _upload(c, path):
    r = c.post("/api/docs?new=1", files={"file": (path.name, path.read_bytes())})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _pair(c):
    plan, report = _upload(c, M.PLAN_FORM), _upload(c, M.REPORT_FORM)
    for d, f in ((plan, "plan"), (report, "report")):
        assert c.put(f"/api/works/{d}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "시험 과제"}).status_code == 200
    return plan, report


def test_reasons_per_document(client):
    alone = _upload(client, M.REPORT_FORM)
    v = client.get(f"/api/docs/{alone}/merge-links").json()
    assert v["from"] is None and v["groups"] == [] and v["project"] == ""   # 과제에 안 묶인 문서 = 원본 없음
    plan, report = _pair(client)
    v = client.get(f"/api/docs/{report}/merge-links").json()
    assert (v["project"], v["from"]["work"], v["to"]["work"]) == ("시험 과제", plan, report)
    assert "noHeadings" in v["from"]["reasons"] and "noHeadings" in v["to"]["reasons"] and v["groups"] == []   # 분석 전 — 문서마다 따로 알린다
    assert client.put(f"/api/docs/{report}/merge-links/p1", json={"from": None}).status_code == 409


@pytest.mark.parametrize("different", [{"project": "다른 프로젝트"}, {"job": "plan_merge"}, {"round": 2}])
def test_merge_sources_stay_in_the_same_task_round(client, monkeypatch, different):
    """최근 문서/저장된 원본/명시 요청/이미 만든 계획 모두 프로젝트·TASK·라운드를 넘지 않는다."""
    from app import works

    task = {"kind": "rnd", "job": "plan_to_report", "project": "선박", "round": 1}
    report, plan, other = "a00000000001", "a00000000002", "a00000000003"
    for wid, role, override in ((report, "report", {}), (plan, "plan", {}), (other, "plan", different)):
        works.create(wid, f"{wid}.hwpx", "hwpx", b"scope fixture")
        works.update(wid, task={**task, "file": role, **override})
    monkeypatch.setattr(merge_api, "_read", lambda wid, target=False: {
        "id": wid, "name": f"{wid}.hwpx", "rev": 0, "reasons": ["noHeadings"], "values": None})
    monkeypatch.setattr(merge_api, "_link_comments", lambda wid: [])
    url = f"/api/docs/{report}/merge-links"
    assert client.get(url).json()["from"]["work"] == plan  # 최신 other를 고르지 않는다.
    original = {"from": plan, "fixed": {"kept": {"from": "p1", "source": "user"}}}
    merge_api._store(report, original)
    assert client.post(url, json={"from": other}).status_code == 400
    assert merge_api._store(report) == original

    # 예전에 고른 원본이 다른 그룹으로 옮겨진 경우: 앞 원본의 기록을 다른 후보에 재사용하지 않는다.
    works.update(plan, task={**task, "file": "plan", **different})
    assert client.get(url).json()["from"] is None
    merge_api._PLANS[report] = {"planId": "old-scope", "from": plan}
    assert client.post(url + "/apply", json={"planId": "old-scope"}).status_code == 409
    assert report not in merge_api._PLANS and works.work(report)["rev"] == 0
    works.update(plan, task={**task, "file": "plan"})
    scope = merge_api._source_scope(report, plan)
    works.update(plan, task={**task, "file": "plan", "project": ""})
    merge_api._PLANS[report] = {"planId": "detached", "from": plan, "scope": scope}
    assert client.post(url + "/apply", json={"planId": "detached"}).status_code == 409


def test_merge_keeps_manual_unassigned_sources_and_legacy_round_one(client, monkeypatch):
    from app import works

    report, plan = "b00000000001", "b00000000002"
    task = {"kind": "rnd", "job": "plan_to_report", "project": "선박"}
    for wid, role in ((report, "report"), (plan, "plan")):
        works.create(wid, f"{wid}.hwpx", "hwpx", b"scope fixture")
        works.update(wid, task={**task, "file": role, **({"round": 1} if wid == report else {})})
    assert merge_api._mate(report, {}) == ("선박", plan)  # round 없는 기존 문서 = 1라운드.
    works.update(plan, task={**task, "file": "plan", "project": ""})
    monkeypatch.setattr(merge_api, "_read", lambda wid, target=False: {
        "id": wid, "name": f"{wid}.hwpx", "rev": 0, "reasons": ["noHeadings"], "values": None})
    monkeypatch.setattr(merge_api, "_link_comments", lambda wid: [])
    url = f"/api/docs/{report}/merge-links"
    assert client.get(url).json()["from"] is None  # 미지정 문서는 자동 선택하지 않는다.
    response = client.post(url, json={"from": plan})
    assert response.status_code == 200 and response.json()["from"]["work"] == plan


def test_pairs_and_user_fix(client, monkeypatch):
    plan, report = _pair(client)
    d = M.small()
    sides = {plan: d["from"], report: d["to"]}
    monkeypatch.setattr(merge_api, "_read", lambda doc_id, target=False: {   # 분석·반영을 거친 문서로 바꿔 끼움(그 과정은 test_merge_pairs·구분 기준 시험 몫)
        "id": doc_id, "name": sides[doc_id]["name"], "rev": 0, "reasons": [], "values": d["values"],
        "blocks": sides[doc_id]["doc"].blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]})
    v = client.get(f"/api/docs/{report}/merge-links").json()
    assert v["diff"] == [] and v["counts"]["paired"] >= 5 and sum(v["counts"].values()) == len(v["groups"]) and not v["stale"]
    g = next(x for x in v["groups"] if x["status"] == "paired")
    url = f"/api/docs/{report}/merge-links/{g['id']}"
    cut = client.put(url, json={"from": None}).json()   # 사람이 끊음 — 다시 읽어도 유지
    assert next(x for x in cut["groups"] if x["id"] == g["id"])["status"] == "toOnly"
    again = next(x for x in client.post(f"/api/docs/{report}/merge-links", json={}).json()["groups"] if x["id"] == g["id"])
    assert (again["status"], again["source"]) == ("toOnly", "user")
    back = next(x for x in client.put(url, json={"reset": True}).json()["groups"] if x["id"] == g["id"])
    assert (back["status"], back["source"], back["from"]["key"]) == ("paired", "script", g["from"]["key"])
    other = next(x for x in v["groups"] if x["to"] and x["dim"] != g["dim"] and x["from"])   # 구분이 다른 묶음으로는 못 잇는다
    assert client.put(url, json={"from": other["from"]["key"]}).status_code == 400
    assert client.put(f"/api/docs/{report}/merge-links/없는묶음", json={"from": None}).status_code == 404


def test_llm_review_keeps_user_choice(client, monkeypatch):
    plan, report = _pair(client)
    d = M.small()
    sides = {plan: d["from"], report: d["to"]}
    monkeypatch.setattr(merge_api, "_read", lambda doc_id, target=False: {
        "id": doc_id, "name": sides[doc_id]["name"], "rev": 0, "reasons": [], "values": d["values"],
        "blocks": sides[doc_id]["doc"].blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]})
    v = client.get(f"/api/docs/{report}/merge-links").json()
    und = [g for g in v["groups"] if g["status"] == "ambiguous" and g["candidates"]]
    assert len(und) >= 2 and v["llm"] is None
    a, b = und[0], und[1]
    client.put(f"/api/docs/{report}/merge-links/{a['id']}", json={"from": None})   # 사람이 먼저 끊은 묶음
    from app import merge_llm
    seen = {}

    def fake(to_side, from_side, pairs, to_groups, from_groups, **kw):
        seen.update(blocks=bool(to_side["blocks"] and from_side["blocks"]), graph=bool(to_side["graph"]))
        return {"fixed": {x["id"]: {"from": x["candidates"][0]["key"], "source": "llm", "anchor": None, "reason": "시험"} for x in (a, b)}, "rejected": [], "none": [],
                "units": [{"title": "2.", "pages": [5, 10], "over": False, "targets": 2, "call": {"model": merge_llm.MODEL}, "prompt": "긴 글", "answer": {}}], "left": 0, "form": []}
    monkeypatch.setattr(merge_llm, "review", fake)
    out = client.post(f"/api/docs/{report}/merge-links/llm").json()
    by = {g["id"]: g for g in out["groups"]}
    assert seen == {"blocks": True, "graph": True}
    assert (by[a["id"]]["status"], by[a["id"]]["source"]) == ("toOnly", "user")   # 사람이 고친 것은 LLM 이 못 바꾼다
    assert (by[b["id"]]["status"], by[b["id"]]["source"], by[b["id"]]["from"]["key"]) == ("paired", "llm", b["candidates"][0]["key"])
    assert out["llm"]["units"] == [{"title": "2.", "pages": [5, 10], "over": False, "targets": 2, "call": {"model": "claude-opus-5-5"}}]   # 긴 프롬프트는 merge.json 에 안 싣는다
    # 보낸 프롬프트는 따로 두고 화면 「지침」 이 읽는다(spec_작업 ② §13 — GET …/llm-guide/{step}): 계약 · 판단 지침 · 할 일 프롬프트 + 마지막으로 보낸 단위
    import os
    from pathlib import Path
    jobs = Path(os.environ["NFM_JOBS"])   # 시험마다 빈 임시 폴더(conftest) — 이 작업의 할 일 프롬프트를 하나 둔다
    jobs.mkdir(parents=True, exist_ok=True)
    (jobs / "plan_to_report.md").write_text("# 할 일 프롬프트 — 이관 시험\n<!-- 메모 -->\n- 기준은 계획서\n", encoding="utf-8")
    g = client.get(f"/api/docs/{report}/llm-guide/merge-links").json()
    assert (g["step"], g["name"], g["model"]) == ("merge-links", "자리 연결 LLM 검토", "claude-opus-5-5")
    assert [p["key"] for p in g["parts"]] == ["contract", "guide", "job"] and all(p["text"] and p["title"] for p in g["parts"])
    assert g["parts"][1]["source"].endswith("links.md") and g["parts"][2]["source"].endswith("plan_to_report.md") and "<!--" not in g["parts"][2]["text"]
    assert g["last"]["units"] == [{"n": 0, "title": "2.", "pages": [5, 10], "targets": 2, "tables": 0, "error": None, "chars": 3, "has": True}]
    got = client.get(f"/api/docs/{report}/llm-guide/merge-links/prompt?unit=0").json()
    assert (got["title"], got["prompt"], got["answer"]) == ("2.", "긴 글", {})
    r = client.get(f"/api/docs/{report}/llm-guide/merge-links/prompt?unit=7")
    assert r.status_code == 404 and r.json()["detail"] != "Not Found"   # 끝점이 없는 404(서버 재시작 전)와 글이 다르다 — 화면이 가른다
    r = client.get(f"/api/docs/{report}/llm-guide/nope")
    assert r.status_code == 404 and r.json()["detail"] != "Not Found"
    d2 = client.get(f"/api/docs/{report}/llm-guide/division-missing").json()   # 구분 기준 검토 — 계약만(양식 정보는 있을 때), 실행 전이라 last 없음
    assert d2["parts"][0]["key"] == "contract" and "빠진 곳" in d2["parts"][0]["text"] and d2["last"] is None and d2["model"] is None


def test_llm_table_pairs_are_stored_and_replaced_by_the_next_answer(client, monkeypatch):
    """LLM 이 정한 표 짝(spec_병합 ② §5-1 「표 짝 검토」)은 merge.json `tables` 에 — 사람이 정한 것은 그대로, 다음 검토에서 「같은 표 없음」 이면 지우고, 답이 안 온 표(실패한 단위)는 둔다."""
    plan, report = _pair(client)
    d = M.small()
    sides = {plan: d["from"], report: d["to"]}
    monkeypatch.setattr(merge_api, "_read", lambda doc_id, target=False: {
        "id": doc_id, "name": sides[doc_id]["name"], "rev": 0, "reasons": [], "values": d["values"],
        "blocks": sides[doc_id]["doc"].blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]})
    from app import merge_llm
    merge_api._store(report, {**merge_api._store(report), "tables": {"tU": {"from": None, "source": "user"}}})   # 사람이 끊은 표
    seen, answers = [], [{"fixed": {"tA": {"from": "fA", "source": "llm", "reason": "같은 표", "format": ""}, "tB": {"from": "fB", "source": "llm", "reason": "같은 표", "format": "행 수가 다름"},
                                    "tU": {"from": "fU", "source": "llm", "reason": "사람이 끊은 표", "format": ""}}, "none": [], "rejected": []},
                         {"fixed": {}, "none": [{"to": "tA", "reason": "다시 보니 다른 표"}], "rejected": [{"to": "x", "why": "y"}]},
                         {"fixed": {}, "none": [], "rejected": [], "kept": ["tB"]}]

    def fake(to_side, from_side, pairs, to_groups, from_groups, **kw):
        seen.append(kw.get("tables"))
        return {"fixed": {}, "rejected": [], "none": [], "tables": answers[len(seen) - 1], "units": [], "left": 0, "form": [], "guide": {"name": "links", "title": "자리 연결 LLM 검토", "sha1": "s"}}
    monkeypatch.setattr(merge_llm, "review", fake)
    out = client.post(f"/api/docs/{report}/merge-links/llm").json()
    assert seen == [None]   # 문서 없이 요약만 끼운 읽기(시험) — 표 자료는 안 만든다
    assert out["llm"]["tables"] == {"paired": 3, "none": 0, "rejected": 0, "kept": 0} and out["llm"]["guide"]["name"] == "links"
    saved = merge_api._store(report)["tables"]
    assert saved["tU"] == {"from": None, "source": "user"} and (saved["tA"]["from"], saved["tB"]["format"]) == ("fA", "행 수가 다름")   # 사람 것은 LLM 이 못 바꾼다
    out = client.post(f"/api/docs/{report}/merge-links/llm").json()
    saved = merge_api._store(report)["tables"]
    assert set(saved) == {"tU", "tB"} and out["llm"]["tables"] == {"paired": 0, "none": 1, "rejected": 1, "kept": 0}   # tA = 「같은 표 없음」 으로 지움 · tB = 이번에 답이 없어 그대로
    assert merge_api._forced(merge_api._store(report), "user") == {"tU": {"from": None, "source": "user"}}
    out = client.post(f"/api/docs/{report}/merge-links/llm").json()   # 표를 모두 읽는 검토(2026-11-22) — 스크립트가 이은 표를 LLM 이 그대로 둠(kept): 앞선 LLM 짝(다른 표로 바꿔 둔 것)은 지운다
    assert set(merge_api._store(report)["tables"]) == {"tU"} and out["llm"]["tables"] == {"paired": 0, "none": 0, "rejected": 0, "kept": 1}


def test_plan_apply_through_transaction(client, monkeypatch):
    """넣기 계획 → 반영을 실제 세션으로(문서 = 시험 쌍의 바이트를 올린 것 — 블록 id 가 시험 자료와 같다): 표식 줄이 연차보고서에 들어가고, 다시 계획하면 본문 할 일이 없다."""
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        r = client.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])})
        ids[side] = r.json()["docId"]
        client.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "넣기 시험"})
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):   # 분석 결과·구분 값만 시험 자료 것(문서는 세션의 살아 있는 문서)
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    to = ids["to"]
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": "없음"}).status_code == 409
    v = client.get(f"/api/docs/{to}/merge-links").json()   # 2-2 기관 절은 스크립트가 못 정한다 — 사람이 「② 개발 내용 및 범위」(1차년도)를 고른다
    g = next(x for x in v["groups"] if x["to"] and x["kind"] == "paragraph" and x["dim"] == "org" and "추진 실적" in " ".join(x["to"]["path"]))
    src = next(c["key"] for c in g["candidates"] if c["path"][-1:] == ["개발 내용 및 범위"])
    assert client.put(f"/api/docs/{to}/merge-links/{g['id']}", json={"from": src}).status_code == 200

    def racing(side):   # 읽은 직후 그 문서가 바뀐 경우(다른 탭·에이전트의 편집) — 읽은 것과 잠근 것의 차례가 다르면 반영하지 않는다
        def f(doc_id, target=False):
            out = read(doc_id, target)
            server._sess(doc_id).rev += doc_id == ids[side]
            return out
        return f
    monkeypatch.setattr(merge_api, "_read", racing("to"))
    stale = client.post(f"/api/docs/{to}/merge-links/plan").json()
    monkeypatch.setattr(merge_api, "_read", read)
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": stale["planId"]}).status_code == 409   # 계획이 읽은 뒤 목적이 바뀜
    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert plan["body"]["counts"]["todo"] >= 1 and plan["todo"] >= plan["body"]["counts"]["todo"], plan["body"]["counts"]
    monkeypatch.setattr(merge_api, "_read", racing("from"))
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]}).status_code == 409   # 반영이 읽은 뒤 원본이 바뀜
    monkeypatch.setattr(merge_api, "_read", read)
    server._sess(ids["from"]).rev -= 1
    before = client.get(f"/api/docs/{to}").json()
    done = client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]})
    assert done.status_code == 200, done.text[:600]
    out = done.json()
    assert out["rev"] == before["rev"] + 1 and "converted" in out
    texts = " ".join(b.get("text") or "" for b in server._sess(to).doc.blocks())
    assert texts.count(M.SMALL_MARK) >= plan["body"]["counts"]["todo"]
    assert server._sess(ids["from"]).rev == 0   # 원본은 그대로
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]}).status_code == 409   # 같은 계획을 두 번 못 쓴다
    mark = merge_api._store(to)["filled"]
    assert mark["planId"] == plan["planId"] and mark["nothing"] is False and mark["rev"] == out["rev"] and mark["ids"]   # 반영 표식 — 「내용 넣기」 의 끝(spec_워크플로우 ② §18-12 ②)
    assert merge_api.fill_summary(to)["filled"]["nothing"] is False
    again = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert again["body"]["counts"].get("todo", 0) == 0, again["body"]["counts"]   # 같은 내용을 두 번 넣지 않는다
    # 계획의 판(② §18-12 ③) — 계획 뒤 사람이 연결을 바꾸면(문서 차례는 그대로) 그 계획은 못 쓴다 · 새 계획을 청하다 실패해도 옛 계획이 남지 않는다
    assert merge_api.fill_summary(to)["plan"]["fresh"] is True
    assert client.put(f"/api/docs/{to}/merge-links/{g['id']}", json={"reset": True}).status_code == 200
    assert merge_api.fill_summary(to)["plan"]["fresh"] is False
    moved = client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": again["planId"]})
    assert moved.status_code == 409 and "자리 연결" in moved.json()["detail"]
    third = client.post(f"/api/docs/{to}/merge-links/plan").json()
    real_view = merge_api._view
    monkeypatch.setattr(merge_api, "_view", lambda doc_id, fresh=False: ({}, None))   # 막는 까닭이 생김 — 새 계획은 409
    assert client.post(f"/api/docs/{to}/merge-links/plan").status_code == 409
    monkeypatch.setattr(merge_api, "_view", real_view)
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": third["planId"]}).json()["detail"].startswith("계획이 없거나")   # 옛 계획은 버려졌다
    # 계획 뒤 사람이 다른 원본(같은 묶음의 다른 사업계획서)을 골랐다 — 옛 원본의 계획은 넣지 않는다(astra 결과 검토)
    fourth = client.post(f"/api/docs/{to}/merge-links/plan").json()
    real_mate = merge_api._mate
    monkeypatch.setattr(merge_api, "_mate", lambda to_id, saved: (real_mate(to_id, saved)[0], "다른원본"))   # merge.json 의 from 이 그 사이 다른 원본으로(사람이 고름)
    swapped = client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": fourth["planId"]})
    assert swapped.status_code == 409 and "원본 문서가 바뀌었습니다" in swapped.json()["detail"]
    assert merge_api.fill_summary(to)["filled"] is None   # 반영 표식은 원본에 묶였다 — 다른 원본이면 「내용 넣기」 의 끝이 아니다
    monkeypatch.setattr(merge_api, "_mate", real_mate)
    assert merge_api.fill_summary(to)["filled"]["nothing"] is False


def test_a_nothing_reapply_keeps_the_last_real_fill_for_retidy(client, monkeypatch):
    """다 넣은 문서를 다시 반영(넣을 것 0)해도 넣은 뒤 정리는 넣은 내용이 있다고 본다(spec_병합 ② §5-9 10): 「넣을 것 0」 표식이 앞의 실제 반영(`last`)을 지니고 ·
    정리의 재료는 그 표식(at · 넣은 블록)으로 센다 — 「넣은 내용이 없습니다」 로 줄이 「건너뜀」 이 되지 않는다. 「내용 넣기」 의 끝(fill_summary)은 전처럼 「넣을 것 0」."""
    from app import merge_retidy_api as RA
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        ids[side] = client.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])}).json()["docId"]
        client.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "다시 넣기 시험"})
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    to = ids["to"]
    v = client.get(f"/api/docs/{to}/merge-links").json()
    g = next(x for x in v["groups"] if x["to"] and x["kind"] == "paragraph" and x["dim"] == "org" and "추진 실적" in " ".join(x["to"]["path"]))
    assert client.put(f"/api/docs/{to}/merge-links/{g['id']}", json={"from": next(c["key"] for c in g["candidates"] if c["path"][-1:] == ["개발 내용 및 범위"])}).status_code == 200
    assert RA.facts(to)["why"] == RA.NO_FILL   # 넣기 전
    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]}).status_code == 200
    blocks = lambda: server._sess(to).doc.blocks()   # noqa: E731
    gap = next(b["id"] for b in blocks() if b.get("id") and b["id"] not in RA.MR.within(blocks(), RA.MR.record_ids(merge_api._store(to))))
    saved = merge_api._store(to)   # 빈 자리 검토가 넣은 줄처럼 — 반영 표식의 ids 에만 적힌 블록(merge_apply 의 gaps.inserted · applied 에는 없음)
    merge_api._store(to, {**saved, "filled": {**saved["filled"], "ids": [*saved["filled"]["ids"], gap]}})
    real = merge_api._store(to)["filled"]
    assert gap in RA._records(to)["ins"](blocks())
    first = RA.facts(to)
    assert real["nothing"] is False and real["ids"] and first["why"] == "" and first["fill"] == real["at"] and first["inserted"] == len(real["ids"])
    again = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert again["todo"] == 0, again["body"]["counts"]
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": again["planId"]}).json()["nothing"] is True
    mark = merge_api._store(to)["filled"]
    assert mark["nothing"] is True and mark["at"] > real["at"] and mark["last"] == real   # 앞의 실제 반영을 지닌다
    assert merge_api.fill_summary(to)["filled"] == {"nothing": True, "at": mark["at"]}   # 「내용 넣기」 의 끝은 전처럼
    now = RA.facts(to)
    assert now["why"] == "" and now["fill"] == real["at"] and now["inserted"] == len(real["ids"])   # 정리의 표식은 앞의 실제 반영 — 그 뒤 정리했으면 그대로 「끝남」
    assert RA.MR.within(blocks(), real["ids"]) <= RA._records(to)["ins"](blocks()) and gap in RA._records(to)["ins"](blocks())   # 정리 대상도 앞 반영 그대로(앞 반영의 ids 에만 적힌 블록까지)
    third = client.post(f"/api/docs/{to}/merge-links/plan").json()   # 「넣을 것 0」 을 거듭해도 같은 실제 반영
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": third["planId"]}).json()["nothing"] is True
    assert merge_api._store(to)["filled"]["last"] == real and RA.facts(to)["fill"] == real["at"]
    # `last` 를 적기 전 판의 기록(「넣을 것 0」 이 앞 반영을 덮음) — 넣은 기록이 있으면 그 표식으로 본다(정리를 한 번 다시)
    old = {k: v for k, v in merge_api._store(to)["filled"].items() if k != "last"}
    merge_api._store(to, {**merge_api._store(to), "filled": old})
    legacy = RA.facts(to)
    assert legacy["why"] == "" and legacy["fill"] == old["at"] and legacy["inserted"] == len(RA.MR.record_ids(merge_api._store(to)))
    merge_api._store(to, {k: v for k, v in merge_api._store(to).items() if k not in ("applied", "copied")} | {"filled": old})
    assert RA.facts(to)["why"] == RA.NO_FILL   # 넣은 기록도 없으면 넣은 것이 없다


def test_llm_endpoint_runs_real_review(client, monkeypatch, tmp_path):
    """끝점 → `merge_llm.review` 의 실제 코드(챕터 나누기 · 단위별 자료 · 답 검증)까지 — LLM 호출(`llm.ask_all`)만 가짜. 모델은 Opus, 못 정한 묶음은 모두 어느 단위에 실린다.
    이 작업의 할 일 프롬프트(jobs/plan_to_report.md — spec_작업 ② §13)가 단위마다 실리고 기록에 남는다."""
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "plan_to_report.md").write_text("# 할 일 프롬프트 — 시험 이관\n\n- 기준은 계획서(시험 표식)\n", encoding="utf-8")
    plan, report = _pair(client)
    d = M.small()
    sides = {plan: d["from"], report: d["to"]}
    monkeypatch.setattr(merge_api, "_read", lambda doc_id, target=False: {
        "id": doc_id, "name": sides[doc_id]["name"], "rev": 0, "reasons": [], "values": d["values"],
        "blocks": sides[doc_id]["doc"].blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]})
    before = client.get(f"/api/docs/{report}/merge-links").json()
    und = before["counts"]["ambiguous"] + before["counts"]["toOnly"]
    from app import llm
    jobs = []
    monkeypatch.setattr(llm, "ask_all", lambda js, **kw: jobs.extend(js) or [{"data": {"decisions": [], "summary": ""}, "backend": "fake", "model": j["model"], "error": None} for j in js])
    out = client.post(f"/api/docs/{report}/merge-links/llm")
    assert out.status_code == 200, out.text[:400]
    out = out.json()
    assert jobs and all(j["model"] == "claude-opus-5-5" for j in jobs)
    assert sum(u["targets"] for u in out["llm"]["units"]) == und and len([u for u in out["llm"]["units"] if u["call"]]) == len(jobs)
    assert all("prompt" not in u for u in out["llm"]["units"]) and out["counts"] == before["counts"]   # 빈 답 = 연결은 그대로
    assert all("## 할 일 — 시험 이관" in j["content"] and "기준은 계획서(시험 표식)" in j["content"] for j in jobs)
    assert (out["llm"]["job"]["job"], out["llm"]["job"]["name"]) == ("plan_to_report", "시험 이관")


def test_overflow_levels_choose_in_the_plan_then_refit_what_went_in(client, monkeypatch):
    """넘친 개요 레벨(spec_병합 ② §5-5): 마지막 레벨 자리 「- (추진 내용)」 아래로 가는 원본의 「o」 줄 = 사례 하나 → 계획에 보임 → 처리를 고르면 세워 둔 계획을 버림 → 그 처리로 반영 ·
    넣은 줄이 기록에 남음 → 넣은 뒤 다시 맞추기(덮은 그대로로 되돌리기 · 실행 취소 뒤에도 그 줄을 찾음) · 2단계 초기화에도 선택은 남는다."""
    from app import heading_runs as HR
    from app import merge_over as MO
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        ids[side] = client.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])}).json()["docId"]
        client.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": "넘침 시험"})
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):   # 분석 결과·구분 값만 시험 자료 것(문서는 세션의 살아 있는 문서)
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    to, src = ids["to"], server._sess(ids["from"]).doc
    doc = server._sess(to)
    HR.state(doc)["stage2"] = {**d["to"]["graph"], "meta": {"rev": doc.rev, "run": 2, "stage1Run": 1}}   # 넘친 레벨 끝점은 세션의 2단계 결과에서 템플릿을 읽는다
    v = client.get(f"/api/docs/{to}/merge-links").json()
    g = next(x for x in v["groups"] if x["to"] and x["kind"] == "paragraph" and x["dim"] == "org" and "추진 실적" in " ".join(x["to"]["path"]))
    assert client.put(f"/api/docs/{to}/merge-links/{g['id']}", json={"from": next(c["key"] for c in g["candidates"] if c["path"][-1:] == ["개발 내용 및 범위"])}).status_code == 200
    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    first = next(x for x in plan["body"]["items"] if x["group"] == g["id"] and not x["skip"])
    assert "over" not in plan and first["convert"] == {"converted": 0, "over": 0, "kept": {"body": 1}}   # 표식 줄뿐 — 넘친 줄이 없으면 그 절도 없다
    blocks = [b["id"] for b in src.blocks()]
    line = blocks[blocks.index(first["from"]) + 2]   # 그 기관 항목의 자리표시 줄 「  o 」([기관]›o›- 의 L2) — 글을 쓰면 넣을 내용이 된다
    assert src._text(src._ids[line]).strip() == "o"
    src.set_text(line, "  o 넘침 시험 내용")
    text = lambda: [(b.get("text") or "").strip() for b in doc.doc.blocks()]  # noqa: E731

    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    item = next(x for x in plan["body"]["items"] if x["to"] == first["to"])
    (case,) = plan["over"]["cases"]
    key = case["key"]
    assert item["convert"] == {"converted": 0, "over": 1, "kept": {"body": 1, "tooDeep": 1}} and key == "body:[…]›□›o›-<o›-" and case["at"]
    assert (case["mode"], case["lines"], case["applied"], case["places"], case["to"]["level"]) == ("cover", 1, 0, 1, 4) and [(x["n"], x["was"], x["lines"], x["clash"]) for x in case["levels"]] == [(5, "o", 1, True), (6, "-", 0, True)]
    assert plan["over"]["records"] == {"lines": 0, "cases": {}} and plan["over"]["templates"] and plan["over"]["version"] == 0

    for bad in ({"mode": "edit", "levels": [{"letter": "▪"}]}, {"key": key, "mode": "x"}, {"key": key, "mode": "edit", "levels": [{"like": {"template": "body:없는 템플릿", "level": 1}}]}):
        assert client.put(f"/api/docs/{to}/merge-over", json=bad).status_code == 400
    assert client.put(f"/api/docs/{'0' * 12}/merge-over", json={"key": key, "mode": "cover"}).status_code == 404
    r = client.put(f"/api/docs/{to}/merge-over", json={"key": key, "mode": "edit", "levels": [{"letter": "▪"}]})
    assert r.status_code == 200 and r.json() == {"version": 1, "key": key, "case": {**r.json()["case"], "mode": "edit", "levels": [{"letter": "▪", "like": None, "lead": None}], "template": None}}
    assert client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]}).status_code == 409   # 처리를 바꾸면 세워 둔 계획은 못 쓴다
    plan = client.post(f"/api/docs/{to}/merge-links/plan").json()
    case = plan["over"]["cases"][0]
    assert (case["mode"], case["levels"][0]["letter"], case["levels"][0]["clash"]) == ("edit", "▪", False) and next(x for x in plan["body"]["items"] if x["to"] == first["to"])["convert"] == {"converted": 1, "over": 1, "kept": {"body": 1}}
    done = client.post(f"/api/docs/{to}/merge-links/apply", json={"planId": plan["planId"]})
    assert done.status_code == 200, done.text[:600]
    out = done.json()
    assert out["converted"]["over"] == 1 and out["converted"]["converted"] == 1 and "▪ 넘침 시험 내용" in text() and src._text(src._ids[line]) == "  o 넘침 시험 내용"   # 원본은 그대로
    rec = merge_api._store(to)["applied"][first["to"]]["over"]
    assert rec["key"] == key and [(x["over"], x["was"], x["letter"], x["orig"]["prefix"]) for x in rec["lines"]] == [(1, "o", "▪", "  o ")] and doc.doc._attached(doc.doc._ids.get(rec["lines"][0]["id"]))
    got = client.get(f"/api/docs/{to}/merge-over").json()
    assert got["version"] == 1 and got["cases"][key]["mode"] == "edit" and got["records"] == {"lines": 1, "cases": {key: 1}} and any(t["anchor"] == "body:[…]›□›o›-" for t in got["templates"])

    again = client.post(f"/api/docs/{to}/merge-links/plan").json()   # 다 넣은 뒤에도 그 사례는 넣은 줄의 기록으로 보인다(다시 맞추기)
    case = again["over"]["cases"][0]
    assert again["body"]["counts"].get("todo", 0) == 0 and (case["key"], case["lines"], case["applied"], case["mode"]) == (key, 0, 1, "edit") and again["over"]["records"]["lines"] == 1
    assert client.post(f"/api/docs/{to}/merge-over/refit", json={}).json()["nothing"] is True   # 이미 그 모양
    assert client.put(f"/api/docs/{to}/merge-over", json={"key": key, "reset": True}).json() == {"version": 2, "key": key, "case": None}
    rev = doc.rev
    r = client.post(f"/api/docs/{to}/merge-over/refit", json={})
    assert r.status_code == 200 and (r.json()["lines"], r.json()["kept"], r.json()["rev"]) == (1, {}, rev + 1) and "o 넘침 시험 내용" in text() and "▪ 넘침 시험 내용" not in text()   # 덮은 그대로 = 넣은 그대로의 접두·모양
    assert merge_api._store(to)["applied"][first["to"]]["over"]["lines"][0]["letter"] == "o"
    assert client.post(f"/api/docs/{to}/undo").status_code == 200 and "▪ 넘침 시험 내용" in text()   # 실행 취소 — 문서만 돌아가고 기록의 지금 레터는 「o」
    r = client.post(f"/api/docs/{to}/merge-over/refit", json={"key": key}).json()
    assert r["lines"] == 1 and "o 넘침 시험 내용" in text() and client.post(f"/api/docs/{to}/merge-over/refit", json={"key": "다른 사례"}).json()["nothing"] is True
    assert client.put(f"/api/docs/{to}/merge-over", json={"key": key, "mode": "cover"}).status_code == 200
    merge_api._stage2_clear(to)   # 2단계 초기화 — 넣은 기록은 지우고 고른 처리는 남긴다
    assert "applied" not in merge_api._store(to) and MO.load(to)["cases"][key]["mode"] == "cover"


# ---- 실패가 앞 답을 지우지 않는다 · 사람 짝 되돌리기 · 원본 문서마다 따로(spec_작업 ② §22 「구현 계약」 22-1) ----------------------------------------

def _summaries(client, monkeypatch):
    """(원본 id, 목적 id, 시험 자료) — 분석 · 반영을 거친 요약만 끼운 쌍(문서 없이 — 연결 목록 · 사람 고침까지)."""
    plan, report = _pair(client)
    d = M.small()
    sides = {plan: d["from"], report: d["to"]}
    monkeypatch.setattr(merge_api, "_read", lambda doc_id, target=False: {
        "id": doc_id, "name": sides[doc_id]["name"], "rev": 0, "reasons": [], "values": d["values"],
        "blocks": sides[doc_id]["doc"].blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]})
    return plan, report, d


def _live(client, monkeypatch, project):
    """(목적 id, 원본 id) — 시험 쌍의 바이트를 올린 실제 세션에 시험 자료의 분석 결과 · 구분 값을 끼운 것(넣기 계획 · 빈 자리 검토가 문서를 읽는다). 자리 지침은 못 읽은 것으로(판을 안 본다)."""
    d = M.small()
    ids = {}
    for side, f in (("from", "plan"), ("to", "report")):
        ids[side] = client.post("/api/docs?new=1", files={"file": (d[side]["name"], d[side]["bytes"])}).json()["docId"]
        client.put(f"/api/works/{ids[side]}/task", json={"kind": "rnd", "file": f, "job": "plan_to_report", "project": project})
    sides = {ids["from"]: d["from"], ids["to"]: d["to"]}

    def read(doc_id, target=False):
        s = server._sess(doc_id)
        with s.lock:
            return {"id": doc_id, "name": s.name, "rev": s.rev, "reasons": [], "values": d["values"], "doc": s.doc, "blocks": s.doc.blocks(), "graph": sides[doc_id]["graph"], "tables": sides[doc_id]["tables"]}
    monkeypatch.setattr(merge_api, "_read", read)
    monkeypatch.setattr(merge_api, "_places", lambda doc_id, to: None)
    return ids["to"], ids["from"]


def test_table_map_call_failure_keeps_the_prior_map_but_an_undecided_answer_drops_it(client, monkeypatch):
    """표 대응 저장(_map_store): 호출이 실패한 표(답이 안 옴)는 앞 대응을 지우지 않는다 — 줄에 error · 앞 대응이 있었으면 kept. 답은 왔는데 검증이 못 정한 표는 전처럼 앞 대응을 지운다."""
    from app import merge_table_map
    plan, report = _pair(client)
    old = lambda frm: {"from": frm, "records": [], "grow": [], "fields": [], "mark": "", "source": "llm", "at": "앞"}  # noqa: E731
    merge_api._store(report, {"tableMaps": {"tA": old("fA"), "tB": old("fB")}})
    monkeypatch.setattr(merge_table_map, "check", lambda c, data: (None, [{"to": "x", "why": "행을 못 맞춤"}]))
    p = lambda title: {"target": {"title": title}, "sources": []}  # noqa: E731
    built = [("tA", "fA", p("표 A"), {}), ("tB", "fB", p("표 B"), {}), ("tC", "fC", p("표 C"), {})]
    res = [{"data": None, "error": "시간 초과"}, {"data": {"records": []}, "error": None}, {"data": None, "error": "시간 초과"}]
    out = merge_api._map_store(report, {"id": plan}, built, built, [{"content": "프롬프트"}] * 3, res, {}, None, "지금")
    assert merge_api._store(report)["tableMaps"] == {"tA": old("fA")}   # 실패한 표의 앞 대응은 남고 · 못 정한 표의 앞 대응은 지워진다
    rows = {x["to"]: x for x in out["tables"]}
    assert rows["tA"]["error"] == "시간 초과" and rows["tA"]["kept"] is True
    assert rows["tC"]["error"] == "시간 초과" and "kept" not in rows["tC"]   # 앞 대응이 없던 표
    assert rows["tB"]["error"] == "행을 못 맞춤" and "kept" not in rows["tB"]
    assert (out["asked"], out["mapped"]) == (3, 0)


def test_gaps_missing_or_failed_answers_do_not_replace_what_was_answered(client, monkeypatch):
    """빈 자리 검토의 저장: 답 누락(`missing`)은 「원본 없음」 이 아니다 — 답을 받은 자리로 세지 않고 · 넣기 계획의 「아직 빈 자리」 에 들고 · 다음 검토가 다시 묻는다.
    「전부 다시」 여도 이번 답에 없는 자리(호출이 실패한 단위)와 답이 빠진 자리의 앞 답은 그대로다."""
    from app import merge_gaps
    to, _ = _live(client, monkeypatch, "빈 자리 시험")
    seen, script, pick = [], [], {}

    def fake(prep, job=None, links="", **kw):
        seen.append(set(prep["ctx"]["slots"]))
        tables, slots = script.pop(0)(prep["ctx"])
        return {"tables": tables, "slots": slots, "rejected": [], "units": [], "asked": 1, "found": {"tables": len(prep["found"]["tables"]), "slots": len(prep["found"]["slots"])}, "guide": None, "job": None}
    monkeypatch.setattr(merge_gaps, "ask", fake)
    none = lambda s, reason: {"kind": s["kind"], "was": s["was"], "label": s["label"], "table": s["table"], "from": None, "take": None, "reason": reason}  # noqa: E731
    lost = lambda s: {**none(s, merge_gaps.MISSING), "missing": True}  # noqa: E731
    closed = lambda ctx, reason: {k: {"from": None, "reason": reason} for k in ctx["tables"]}  # noqa: E731
    url = f"/api/docs/{to}/merge-links/gaps"

    def first(ctx):   # c 만 답에 빠짐 — 나머지는 「원본 없음」
        a, b, c = sorted(ctx["slots"])[:3]
        pick.update(a=a, b=b, c=c)
        return closed(ctx, "처음"), {k: lost(s) if k == c else none(s, "처음") for k, s in ctx["slots"].items()}
    script.append(first)
    out = client.post(url, json={})
    assert out.status_code == 200, out.text[:400]
    a, b, c = pick["a"], pick["b"], pick["c"]
    saved = merge_api._store(to)
    assert (out.json()["slots"]["missing"], out.json()["kept"]) == (1, 0) and saved["gaps"]["slots"][c]["missing"] is True and saved["gaps"]["slots"][a]["reason"] == "처음"
    rows = [v for k in ("tables", "slots") for v in saved["gaps"][k].values()]
    assert merge_api._kept(saved)["gaps"]["n"] == len(rows) - 1   # 답이 빠진 자리는 답을 받은 자리가 아니다
    assert client.post(f"/api/docs/{to}/merge-links/plan").json()["gaps"]["counts"]["open"] == 1   # 「아직 빈 자리」 에 든다

    script.append(lambda ctx: ({}, {k: none(s, "둘째") for k, s in ctx["slots"].items()}))   # 다음 검토 — 빠졌던 자리만 다시 묻는다
    assert client.post(url, json={}).status_code == 200 and seen[1] == {c}
    saved = merge_api._store(to)["gaps"]["slots"]
    assert saved[c]["reason"] == "둘째" and "missing" not in saved[c] and saved[a]["reason"] == "처음"

    def third(ctx):   # 「전부 다시」 — a 는 답에 빠짐 · b 는 호출이 실패한 단위(답에 없음) · 나머지는 새 답
        return closed(ctx, "셋째"), {k: lost(s) if k == a else none(s, "셋째") for k, s in ctx["slots"].items() if k != b}
    script.append(third)
    out = client.post(url, json={"again": True})
    assert out.status_code == 200 and {a, b, c} <= seen[2]
    saved = merge_api._store(to)["gaps"]["slots"]
    assert saved[a]["reason"] == "처음" and "missing" not in saved[a]   # 답 누락은 앞 답을 갈지 않는다
    assert saved[b]["reason"] == "처음"   # 「전부 다시」 중 실패한 단위의 앞 답이 남는다
    assert saved[c]["reason"] == "셋째" and (out.json()["slots"]["missing"], out.json()["kept"]) == (1, 1)


def test_gaps_place_missing_twice_is_closed_and_not_asked_forever(client, monkeypatch):
    """두 번 물었는데 두 번 다 답에 빠진 자리는 「원본 없음」 으로 닫는다 — 실행마다 유료로 다시 묻지 않고 「아직 빈 자리」 가 0 이 된다(다음 단계가 막히지 않게)."""
    from app import merge_gaps
    to, _ = _live(client, monkeypatch, "빈 자리 두 번")
    seen = []

    def fake(prep, job=None, links="", **kw):   # 물은 자리 가운데 첫 자리를 늘 답에서 빠뜨린다
        seen.append(set(prep["ctx"]["slots"]))
        keys = sorted(prep["ctx"]["slots"])
        slots = {k: {"kind": s["kind"], "was": s["was"], "label": s["label"], "table": s["table"], "from": None, "take": None,
                     **({"reason": merge_gaps.MISSING, "missing": True} if k == keys[0] else {"reason": "없음"})} for k, s in prep["ctx"]["slots"].items()}
        return {"tables": {k: {"from": None, "reason": "없음"} for k in prep["ctx"]["tables"]}, "slots": slots, "rejected": [], "units": [], "asked": 1,
                "found": {"tables": len(prep["found"]["tables"]), "slots": len(prep["found"]["slots"])}, "guide": None, "job": None}
    monkeypatch.setattr(merge_gaps, "ask", fake)
    url = f"/api/docs/{to}/merge-links/gaps"
    assert client.post(url, json={}).status_code == 200
    lost = sorted(seen[0])[0]
    assert merge_api._store(to)["gaps"]["slots"][lost]["missing"] is True
    out = client.post(url, json={})   # 둘째 — 빠졌던 자리만 다시 묻고 또 빠짐
    assert out.status_code == 200 and seen[1] == {lost} and out.json()["slots"]["missing"] == 0
    got = merge_api._store(to)["gaps"]["slots"][lost]
    assert "missing" not in got and got["silent"] is True and got["from"] is None
    assert client.post(f"/api/docs/{to}/merge-links/plan").json()["gaps"]["counts"]["open"] == 0


def test_gaps_missing_answer_keeps_the_table_pair_that_review_made(client, monkeypatch):
    """빈 자리 검토가 낸 표 짝(`by: gaps`)은 그 표의 답이 빠졌을 때(`missing`) 지워지지 않는다 — 다시 물어 「같은 표 없음」 이라고 답했을 때만 전처럼 지운다."""
    from app import merge_gaps
    to, _ = _live(client, monkeypatch, "빈 표 시험")
    pair = {"from": "fG", "source": "llm", "by": "gaps", "reason": "같은 표", "format": ""}
    merge_api._store(to, {**merge_api._store(to), "tables": {"tG": pair}, "gaps": {"at": "앞", "tables": {"tG": {"from": "fG", "reason": "같은 표"}}, "slots": {}}})
    answers = [{"tG": {"from": None, "missing": True, "reason": merge_gaps.MISSING}}, {"tG": {"from": None, "reason": "다시 보니 다른 표"}}]
    monkeypatch.setattr(merge_gaps, "ask", lambda prep, job=None, links="", **kw: {"tables": answers.pop(0), "slots": {}, "rejected": [], "units": [], "asked": 1, "found": {"tables": 1, "slots": 0}, "guide": None, "job": None})
    url = f"/api/docs/{to}/merge-links/gaps"
    out = client.post(url, json={"again": True})
    assert out.status_code == 200, out.text[:400]
    saved = merge_api._store(to)
    assert saved["tables"]["tG"] == pair and saved["gaps"]["tables"]["tG"] == {"from": "fG", "reason": "같은 표"} and (out.json()["tables"]["missing"], out.json()["kept"]) == (1, 1)
    assert client.post(url, json={"again": True}).status_code == 200
    saved = merge_api._store(to)
    assert "tG" not in saved["tables"] and saved["gaps"]["tables"]["tG"]["reason"] == "다시 보니 다른 표"   # 답이 온 「같은 표 없음」 은 전처럼


def test_user_fix_over_an_llm_pair_resets_back_to_the_llm_pair(client, monkeypatch):
    """사람이 LLM 짝을 고치면 그 LLM 짝을 사람 항목의 `llm` 에 지닌다 — 「되돌리기」 는 그 LLM 짝으로(사람 지정과 LLM 값을 같은 칸에 쓰지 않는다). 지닌 LLM 짝이 없으면 전처럼 지운다(스크립트 결과로)."""
    plan, report, _ = _summaries(client, monkeypatch)
    v = client.get(f"/api/docs/{report}/merge-links").json()
    g = sorted((x for x in v["groups"] if x["to"] and len(x["candidates"]) >= 2), key=lambda x: x["status"] != "ambiguous")[0]   # 후보가 둘 이상인 묶음(못 정한 것이 먼저)
    first, second = g["candidates"][0]["key"], g["candidates"][1]["key"]
    llm_pair = {"from": first, "source": "llm", "anchor": None, "reason": "시험", "guideSig": ""}
    merge_api._store(report, {**merge_api._store(report), "fixed": {g["id"]: llm_pair}})
    url = f"/api/docs/{report}/merge-links/{g['id']}"
    group = lambda body: next(x for x in client.put(url, json=body).json()["groups"] if x["id"] == g["id"])  # noqa: E731
    stored = lambda: merge_api._store(report)["fixed"].get(g["id"])  # noqa: E731
    cut = group({"from": None})
    assert (cut["status"], cut["source"]) == ("toOnly", "user") and stored() == {"from": None, "source": "user", "llm": llm_pair}
    moved = group({"from": second})   # 사람이 한 번 더 고쳐도 LLM 짝을 이어 지닌다
    assert (moved["source"], moved["from"]["key"]) == ("user", second) and stored() == {"from": second, "source": "user", "llm": llm_pair}
    back = group({"reset": True})
    assert (back["status"], back["source"], back["from"]["key"]) == ("paired", "llm", first) and stored() == llm_pair   # LLM 짝으로 돌아간다
    assert group({"reset": True})["source"] == "script" and stored() is None   # LLM 짝에서 되돌리기 = 전처럼 지움
    assert group({"from": second})["source"] == "user" and stored() == {"from": second, "source": "user"}   # LLM 짝이 없던 자리 — 지닐 것이 없다
    assert group({"reset": True})["source"] == "script" and stored() is None


def test_switching_the_source_keeps_each_source_its_own_pairs(client, monkeypatch):
    """원본 문서를 A → B → A 로 바꾸면 A 에서 정한 것(사람 짝 · 표 짝 · 표 대응 · 빈 자리 답 · LLM 요약)이 그대로 돌아오고, B 에서는 A 의 것이 안 보인다(원본 작업마다 `bySource`).
    목적 문서에 이미 넣은 것의 기록은 안 옮긴다 · 같은 원본을 다시 고르면 아무것도 안 옮긴다 · 원본을 따로 고른 적이 없으면 저절로 정해진 원본이 「앞 원본」 이다 · 2단계 초기화는 넣어 둔 것도 지운다."""
    from app import works
    task = {"kind": "rnd", "job": "plan_to_report", "project": "원본 바꾸기", "round": 1}
    report, a, b = "c00000000001", "c00000000002", "c00000000003"
    for wid, role in ((report, "report"), (a, "plan"), (b, "plan")):
        works.create(wid, f"{wid}.hwpx", "hwpx", b"source fixture")
        works.update(wid, task={**task, "file": role})
    monkeypatch.setattr(merge_api, "_read", lambda wid, target=False: {"id": wid, "name": f"{wid}.hwpx", "rev": 0, "reasons": ["noHeadings"], "values": None})
    monkeypatch.setattr(merge_api, "_link_comments", lambda wid: [])
    url = f"/api/docs/{report}/merge-links"
    pick = lambda wid: client.post(url, json={"from": wid}).status_code  # noqa: E731
    of_a = {"fixed": {"g1": {"from": "pA", "source": "user", "llm": {"from": "pL", "source": "llm"}}}, "tables": {"t1": {"from": "fA", "source": "user"}},
            "tableMaps": {"t1": {"from": "fA", "records": []}}, "gaps": {"at": "앞", "tables": {}, "slots": {"s1": {"from": "nA"}}}, "llm": {"at": "앞"}, "toRev": 3, "fromRev": 5}
    put_in = {"applied": {"k": {"hash": "h"}}, "copied": {"c": {"to": "t9"}}, "filled": {"at": 1, "src": {"id": a, "rev": 5}}}   # 목적 문서에 이미 넣은 것의 기록 — 안 옮긴다
    merge_api._store(report, {"from": a, **of_a, **put_in})
    assert pick(a) == 200 and merge_api._store(report) == {"from": a, "src": a, **of_a, **put_in}   # 같은 원본을 다시 고름(src = 이 판정을 받은 원본 — _bound)
    assert pick(b) == 200
    now = merge_api._store(report)
    assert now["from"] == b and now["src"] == b and not [k for k in merge_api.SOURCE_KEYS if k in now] and now["bySource"] == {a: of_a}   # B 에서는 A 의 짝이 안 보인다
    assert {k: now[k] for k in put_in} == put_in
    of_b = {"fixed": {"g1": {"from": "pB", "source": "user"}}, "toRev": 4, "fromRev": 1}
    merge_api._store(report, {**now, **of_b})
    assert pick(a) == 200
    back = merge_api._store(report)
    assert back["from"] == a and back["src"] == a and {k: back.get(k) for k in of_a} == of_a and back["bySource"] == {b: of_b}   # A 의 사람 짝까지 그대로 돌아온다
    assert {k: back[k] for k in put_in} == put_in
    assert pick(b) == 200
    again = merge_api._store(report)
    assert {k: again[k] for k in merge_api.SOURCE_KEYS if k in again} == of_b and again["bySource"] == {a: of_a}
    merge_api._stage2_clear(report)   # 2단계 초기화 — 다른 원본 몫으로 넣어 둔 것도 2단계가 쌓은 것이다
    assert merge_api._store(report) == {"from": b}
    # 원본을 따로 고른 적이 없는 작업 — 저절로 정해진 원본과 낸 저장값이다: 다른 원본을 처음 고르면 그 원본 몫으로 넣어 둔다 · 저절로 정해진 그 원본을 고르면 안 옮긴다
    merge_api._store(report, dict(of_a))
    auto = merge_api._mate(report, merge_api._store(report))[1]
    other = b if auto == a else a
    assert auto in (a, b) and pick(auto) == 200 and merge_api._store(report) == {**of_a, "from": auto, "src": auto}
    merge_api._store(report, dict(of_a))
    assert pick(other) == 200 and merge_api._store(report) == {"from": other, "src": other, "bySource": {auto: of_a}}


# ---- 가져온 스키마 위반 종류(spec_병합 ② §5-10 「가져온 스키마 위반 종류」 — server.import_check · _heal) ----------------------------------------
PIC_TABLE = "t12501"   # 연구개발계획서 양식의 그림이 든 표(칸 안 그림 하나) — 연차보고서 서식에는 그림이 없다
PIC_KINDS = {("section", "renderingInfo", "transMatrix", "", "SCHEMAV_ELEMENT_CONTENT"), ("section", "imgRect", "pt0", "", "SCHEMAV_ELEMENT_CONTENT"),
             ("section", "pic", "inMargin", "", "SCHEMAV_ELEMENT_CONTENT")}   # 한글이 그림마다 써 두는 꼴(hc:transMatrix · hc:pt0 · img 앞 inMargin) — 실제 작업 728b2a673374 에서 각 20


def _bring_picture(c, check=None):
    """(목적 id, 원본 id, 넣은 표 id) — 연차보고서 서식에 사업계획서 양식의 그림 표를 「내용 반영」 처럼(문서 사이 복사 · 편집 하나) 넣은 상태. check 기본 = server.import_check(원본)."""
    src_id, to_id = _upload(c, M.PLAN_FORM), _upload(c, M.REPORT_FORM)
    s, src = server._sess(to_id), server._sess(src_id)
    assert not PIC_KINDS & set(server.owpml_base(s)["schema"]) and PIC_KINDS <= set(server.owpml_base(src)["schema"])
    got = {}

    def run():
        got["new"] = s.doc.insert_after("p975", [{"kind": "copy", "srcId": PIC_TABLE}], src=src.doc)
        return {"hosts": [], "struct": set(), "origin": {}, "anchor": None}
    with s.lock, src.lock:
        out, after = server._transact(s, run, "mergeFill", check=check or server.import_check(src))
    assert after is not None, out.body[:400]
    return to_id, src_id, got["new"][0]


def _cell_para(c, doc_id, table_id):
    t = next(b for b in c.get(f"/api/docs/{doc_id}").json()["blocks"] if b["id"] == table_id)
    return next(x["id"] for cell in t["cells"] for x in cell["blocks"] if x["type"] == "paragraph")


def _noop():
    return {"hosts": [], "struct": set(), "origin": {}, "anchor": None}


def test_fill_carries_imported_kinds_for_later_edits(client):
    """반영이 들여온 종류(목적 기준선에 없고 원본 기준선에 있는 것)는 작업에 남아, 그 뒤 그림이 든 표의 편집 · 문서 전체 검사 편집 · 지금 검사가 그 종류로 되돌리지 않는다(전에는 422).
    반영을 되돌리면 함께 돌아간다."""
    to, _, tid = _bring_picture(client)
    s = server._sess(to)
    assert PIC_KINDS <= s.owpml_ok and all(k[0] in ("header", "section") for k in s.owpml_ok)
    r = client.post(f"/api/docs/{to}/format/para", json={"ids": [_cell_para(client, to, tid)], "changes": {"align": "right"}})
    assert r.status_code == 200, r.text[:400]
    assert client.get(f"/api/docs/{to}/owpml").json()["status"] != "fail"
    with s.lock:   # 문서 전체 검사 편집(TEMP 삭제 · 구분 기준 반영 · 레벨 자리 규칙 · 넘친 레벨 다시 맞추기)도
        out, after = server._transact(s, _noop, "fullCheck", check=server._full_check)
    assert after is not None, out.body[:400]
    for _ in range(3):
        assert client.post(f"/api/docs/{to}/undo").status_code == 200
    assert server._sess(to).owpml_ok == set()   # 반영을 되돌리면 받아들인 종류도


def test_edit_verification_sees_imported_kinds(client):
    """수정본 OWPML 검사(verify.eowpml)도 받아들인 종류를 기준선에 더한다(owpml_check.accepted) — 넣은 그림의 꼴로 「실패」 하지 않는다."""
    import time
    to, _, _ = _bring_picture(client)

    def wait(kind):
        end = time.time() + 120
        while time.time() < end:
            v = client.get(f"/api/docs/{to}/verify").json()
            if kind in v and not v[kind]["running"]:
                return {x["key"]: x for x in v[kind]["steps"]}
            time.sleep(0.1)
        raise AssertionError("검증이 끝나지 않음")
    wait("import")
    assert client.post(f"/api/docs/{to}/verify", json={"kind": "edit"}).status_code == 200
    st = wait("edit")
    assert st["eowpml"]["status"] in ("ok", "warn"), st["eowpml"]


def test_fill_still_rejects_kinds_neither_document_has(client, monkeypatch):
    """두 문서 어디에도 없던 종류는 전처럼 422 — 받아들인 종류도 남기지 않는다."""
    from app import owpml_check
    foreign = ("section", "x", "y", "", "SCHEMAV_TEST")
    src_id, to_id = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM)
    s, src = server._sess(to_id), server._sess(src_id)
    real = owpml_check.check_doc   # 목적 문서의 편집 뒤 검사에만 가짜 종류(기준선 · 가져오기 검증은 새로 연 문서를 센다)
    monkeypatch.setattr(owpml_check, "check_doc", lambda doc: (lambda res: {**res, "schema": res["schema"] + [{"part": "section", "kind": foreign, "el": None, "message": "시험"}]} if doc is s.doc else res)(real(doc)))

    def run():
        s.doc.insert_after("p975", [{"kind": "copy", "srcId": PIC_TABLE}], src=src.doc)
        return _noop()
    with s.lock, src.lock:
        out, after = server._transact(s, run, "mergeFill", check=server.import_check(src))
    assert after is None and out.status_code == 422 and s.owpml_ok == set()


def test_legacy_fill_heals_on_the_first_edit(client, monkeypatch):
    """고침 전에 넣은 작업(받아들인 종류를 남기지 않음): 처음 걸린 편집에서 넣은 기록(merge.json `filled.src`)의 원본 기준선으로 그 종류를 받아들이고 다시 판정한다 — 원본 세션을 열지 않고
    올린 원본 파일에서 센다. 넣은 기록이 없으면 받지 않고, 원본 기준선에 없는 종류는 여전히 422. 받아들인 종류는 그 편집을 되돌려도 남는다."""
    from app import owpml_check
    to, src_id, tid = _bring_picture(client)
    s = server._sess(to)
    s.owpml_ok.clear()
    for u in s.undo:
        u["owpml_ok"] = set()

    def edit():
        return client.post(f"/api/docs/{to}/format/para", json={"ids": [_cell_para(client, to, tid)], "changes": {"align": "right"}})
    r = edit()
    assert r.status_code == 422 and {x["kind"] for x in r.json()["owpml"]["new"]} == {owpml_check.kind_text(k) for k in PIC_KINDS}   # 넣은 기록 없음 — 받지 않는다
    merge_api._store(to, {"filled": {"at": 0, "planId": "시험", "src": {"id": src_id, "rev": 0}, "rev": s.rev, "nothing": False, "ids": [tid]}})
    server._SRC_KINDS.clear()
    server.DOCS.pop(src_id)
    r = edit()
    assert r.status_code == 200, r.text[:400]
    assert PIC_KINDS <= server._sess(to).owpml_ok and src_id not in server.DOCS   # 원본 세션은 안 열었다(올린 원본 파일에서 셈)
    assert client.post(f"/api/docs/{to}/undo").status_code == 200 and PIC_KINDS <= server._sess(to).owpml_ok   # 이 편집 전부터 있던 종류 — 되돌려도 남는다
    foreign = ("section", "x", "y", "", "SCHEMAV_TEST")
    real = owpml_check.check_hosts
    monkeypatch.setattr(owpml_check, "check_hosts", lambda doc, hosts, header=False: (lambda res: {**res, "schema": res["schema"] + [{"part": "section", "kind": foreign, "el": None, "message": "시험"}]})(real(doc, hosts, header)))
    bad = edit()
    assert bad.status_code == 422 and [x["kind"] for x in bad.json()["owpml"]["new"]] == [owpml_check.kind_text(foreign)] and foreign not in server._sess(to).owpml_ok


def test_heal_does_not_take_kinds_the_edit_itself_brings(client):
    """넣은 기록이 있어도 받아들이는 것은 **편집 전 문서**에 이미 있던 종류뿐(server._heal — 2026-11-22 결과 검토): 넣은 기록이 있는 작업에서 다른 문서의 그림 표를 처음 들이는 편집
    (서식 보관함 적용 · 표지 적용처럼 — 기본 검사)은 전처럼 422 이고 받아들인 종류 · 실행 취소 묶음을 늘리지 않는다."""
    import json

    from app import owpml_check
    src_id, to_id = _upload(client, M.PLAN_FORM), _upload(client, M.REPORT_FORM)
    s, src = server._sess(to_id), server._sess(src_id)
    merge_api._store(to_id, {"filled": {"at": 0, "planId": "시험", "src": {"id": src_id, "rev": 0}, "rev": s.rev, "nothing": False, "ids": []}})   # 글만 넣은 반영의 기록
    assert PIC_KINDS <= set(merge_api.owpml_from(s))   # 넣은 기록은 살아 있다 — 받아들임이 원본 기준선까지 가서 편집 전 문서로 거른다
    undo, rev, got = len(s.undo), s.rev, {}

    def run():
        got["new"] = s.doc.insert_after("p975", [{"kind": "copy", "srcId": PIC_TABLE}], src=src.doc)
        return {"hosts": [s.doc._ids[got["new"][0]]], "struct": set(), "origin": {}, "anchor": None}
    with s.lock, src.lock:
        out, after = server._transact(s, run, "styleApply")
    assert after is None and out.status_code == 422
    assert {owpml_check.kind_text(k) for k in PIC_KINDS} <= {x["kind"] for x in json.loads(out.body)["owpml"]["new"]}
    assert s.owpml_ok == set() and len(s.undo) == undo and s.rev == rev and not s.doc._attached(s.doc._ids.get(got["new"][0]))


def test_legacy_heal_counts_a_nothing_fill_record(client):
    """다시 넣기의 「넣을 것 0」 이 앞 반영의 기록(merge.json `filled`)을 덮었고 `applied` 가 비어도(표 칸 · 표 대응 · 빈 자리 · 통째 복사로만 넣은 반영) 그 원본으로 받아들인다 —
    편집 전 문서에 그림의 꼴이 있으니(2026-11-22 결과 검토)."""
    to, src_id, tid = _bring_picture(client)
    s = server._sess(to)
    s.owpml_ok.clear()
    for u in s.undo:
        u["owpml_ok"] = set()
    merge_api._store(to, {"filled": {"at": 0, "planId": "시험", "src": {"id": src_id, "rev": 0}, "rev": s.rev, "nothing": True, "ids": []}})
    r = client.post(f"/api/docs/{to}/format/para", json={"ids": [_cell_para(client, to, tid)], "changes": {"align": "right"}})
    assert r.status_code == 200, r.text[:400]
    assert PIC_KINDS <= server._sess(to).owpml_ok


def test_decisions_follow_the_source_they_were_made_with(monkeypatch):
    """판정은 그것을 받은 원본 작업(`src`)에 묶인다 — 사람이 고르지 않아도 지금 쓰는 원본이 달라지면(앞 원본을 지움 · 더 새 원본이 잡힘) 앞 원본의 짝이 새 원본에 안 보이고,
    앞 원본이 다시 잡히면 돌아온다(열쇠가 우연히 맞는 다른 원본의 내용을 가져오지 않게). `src` 가 없는 옛 저장본은 지금 원본의 것으로 본다."""
    box = {"to": {"fixed": {"g1": {"from": "k1", "source": "user"}}, "applied": {"a": 1}}}
    monkeypatch.setattr(merge_api, "_store", lambda wid, data=None: box.__setitem__(wid, data) if data is not None else box.get(wid, {}))
    got = merge_api._bound("to", box["to"], "A")   # 옛 저장본 — 지금 원본 A 의 것으로 적는다
    assert got["src"] == "A" and got["fixed"]["g1"]["from"] == "k1" and box["to"]["src"] == "A"
    got = merge_api._bound("to", box["to"], "B")   # 저절로 B 가 잡힘 — A 의 짝은 넣어 두고 B 에서는 안 보인다
    assert got["src"] == "B" and "fixed" not in got and got["bySource"]["A"]["fixed"]["g1"]["from"] == "k1" and got["applied"] == {"a": 1} and "from" not in got
    assert merge_api._bound("to", box["to"], "B") is box["to"]   # 같은 원본이면 그대로(다시 쓰지 않는다)
    got = merge_api._bound("to", box["to"], "A")   # A 가 다시 잡히면 사람이 정한 짝까지 돌아온다
    assert got["src"] == "A" and got["fixed"]["g1"] == {"from": "k1", "source": "user"} and "bySource" not in got
    assert merge_api._bound("to", {}, "A") == {} and merge_api._bound("to", {"fixed": {"g": {"from": "k"}}}, None) == {"fixed": {"g": {"from": "k"}}}   # 판정이 없거나 원본이 없으면 그대로
