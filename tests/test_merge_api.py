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
                         {"fixed": {}, "none": [{"to": "tA", "reason": "다시 보니 다른 표"}], "rejected": [{"to": "x", "why": "y"}]}]

    def fake(to_side, from_side, pairs, to_groups, from_groups, **kw):
        seen.append(kw.get("tables"))
        return {"fixed": {}, "rejected": [], "none": [], "tables": answers[len(seen) - 1], "units": [], "left": 0, "form": [], "guide": {"name": "links", "title": "자리 연결 LLM 검토", "sha1": "s"}}
    monkeypatch.setattr(merge_llm, "review", fake)
    out = client.post(f"/api/docs/{report}/merge-links/llm").json()
    assert seen == [None]   # 문서 없이 요약만 끼운 읽기(시험) — 표 자료는 안 만든다
    assert out["llm"]["tables"] == {"paired": 3, "none": 0, "rejected": 0} and out["llm"]["guide"]["name"] == "links"
    saved = merge_api._store(report)["tables"]
    assert saved["tU"] == {"from": None, "source": "user"} and (saved["tA"]["from"], saved["tB"]["format"]) == ("fA", "행 수가 다름")   # 사람 것은 LLM 이 못 바꾼다
    out = client.post(f"/api/docs/{report}/merge-links/llm").json()
    saved = merge_api._store(report)["tables"]
    assert set(saved) == {"tU", "tB"} and out["llm"]["tables"] == {"paired": 0, "none": 1, "rejected": 1}   # tA = 「같은 표 없음」 으로 지움 · tB = 이번에 답이 없어 그대로
    assert merge_api._forced(merge_api._store(report), "user") == {"tU": {"from": None, "source": "user"}}


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
    again = client.post(f"/api/docs/{to}/merge-links/plan").json()
    assert again["body"]["counts"].get("todo", 0) == 0, again["body"]["counts"]   # 같은 내용을 두 번 넣지 않는다


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
