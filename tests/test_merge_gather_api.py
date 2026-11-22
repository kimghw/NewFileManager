"""취합 API(spec_취합 ② §2·§3·§4·§6 — app/merge_gather_api.py): 저장 · 배포 기준본 · 기관 문서 · 자리 연결 → 판정 → 계획 → 반영 · LLM 검토 · 끌어 넣기를 **실제 모듈**로(LLM 호출만 가짜).
첫 시험만 처음부터 진짜 길(양식 → 구분 기준 계획·반영 → 스크립트 분석 → 기준본), 나머지는 저장소 안 자료(gather_data — 값을 반영한 양식 = 기준본, 그 추출 결과는 캐시)를 올리고
구분 기준 반영 상태·분석 결과만 세션에 끼운다(그 과정은 구분 기준·헤딩 시험 몫). 기관 문서 = 기준본 사본을 고쳐 저장해 다시 연 것(블록 id 가 달라진다)."""
import json

import pytest
from fastapi.testclient import TestClient

import gather_data as D
import merge_data as M
from app import heading_runs as HR
from app import llm, server
from app import merge_gather_api as GA

J1, J2 = D.J1, D.J2
_PARTS = {}


@pytest.fixture
def client():
    server.DOCS.clear()
    for box in (GA._MEM, GA._BLOB, GA._FRAMES, GA._LINKS, GA._JUDGE, GA._PLANS, GA._DROPS):
        box.clear()
    return TestClient(server.app)


def _upload(c, name, data):
    r = c.post("/api/docs?new=1", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()["docId"]


def _analysed(doc_id, graph=None, tables=None):
    """분석 결과를 세션에 끼운다(지금 문서 차례의 것으로) — 기관 문서는 빈 그래프(엔진은 blocks 만 읽는다)."""
    s = server._sess(doc_id)
    st = HR.state(s)
    st["stage2"] = {**(graph or {"nodes": []}), "meta": {"rev": s.rev, "run": 2, "stage1Run": 1}}
    if tables is not None:
        st["stage3"] = {**tables, "meta": {"rev": s.rev, "run": 3, "stage2Run": 2}}


def _master(c, project="취합 시험", frame=True):
    """취합본(기준본 바이트 — 블록 id 가 캐시한 추출 결과와 같다) + 구분 기준 반영됨 + 분석 → (id, 취합 상태)."""
    b = D.base()["side"]
    to = _upload(c, "취합본.hwpx", b["bytes"])
    if project is not None:
        assert c.put(f"/api/works/{to}/task", json={"kind": "rnd", "file": "plan", "job": "plan_merge", "project": project}).status_code == 200
    server._sess(to).division["applied"] = {"values": b["values"], "planId": "p1", "rev": 0}
    _analysed(to, b["graph"], b["tables"])
    if not frame:
        return to, None
    r = c.post(f"/api/docs/{to}/gather/frame")
    assert r.status_code == 200, r.text
    return to, r.json()


def _edit_a(d):
    """가나대 문서 — 제 자리(1차년도 ① 개발 목표) · 공통 자리(□ 필요성) · 제 표 칸 · 기관-연도 행 표의 제 덩이에 행 하나."""
    d.set_text(D.nxt(d, D.para(d, f"[공동연구개발기관1({J1})]", 0)), f" o {J1} 1차년도 개발 목표")
    d.set_text(D.nxt(d, D.para(d, "□ 필요성")), f" o {J1}가 쓴 필요성")
    d.set_text(D.cell(d, D.table_after(d, f"[공동연구개발기관 : {J1}]"), 1, 1)["id"], "o 사업화 형태 : 기술이전")
    lt = D.table_after(d, "(1) 연구시설·장비 구축(임차)계획")
    m = d.clone_rows(lt, 3, 3, [1, 8], keep_text=False)["map"]
    for cell, text in zip(sorted((x for x in d.table_block(lt)["cells"] if x["id"] in m.values()), key=lambda x: x["col"]), ["2026", "레이저 가공기", "구매", "가공", "1", "50,000", "26년 5월", f"{J1} 실험동"]):
        d.set_text(cell["id"], text)


def _edit_b(d):
    """다라연 문서 — 제 자리 + 같은 공통 자리(□ 필요성)에 다른 글."""
    d.set_text(D.nxt(d, D.para(d, f"[공동연구개발기관2({J2})]", 0)), f" o {J2} 1차년도 개발 목표")
    d.set_text(D.nxt(d, D.para(d, "□ 필요성")), f" o {J2}가 쓴 필요성")


def _bytes(edit):
    """edit 로 고친 기관 문서의 바이트(프로세스에 한 번 — 만드는 데 몇 초)."""
    if edit not in _PARTS:
        _PARTS[edit] = D.part(edit, edit.__name__)["bytes"]
    return _PARTS[edit]


def _part(c, to, name, edit=None, data=None, orgs=None):
    """기관 문서를 올려 취합에 넣는다(분석은 빈 그래프) → id."""
    pid = _upload(c, name, _bytes(edit) if data is None else data)
    _analysed(pid)
    r = c.put(f"/api/docs/{to}/gather/parts/{pid}", json={} if orgs is None else {"orgs": orgs})
    assert r.status_code == 200, r.text
    return pid


def _why(r, status, reason):
    """오류 꼴 = detail {reason, message(한국어 글)}."""
    d = r.json().get("detail")
    assert r.status_code == status and isinstance(d, dict) and d.get("reason") == reason and isinstance(d.get("message"), str) and d["message"], (r.status_code, r.text[:300])
    return d


def _texts(doc_id):
    return D.texts(server._sess(doc_id).doc)


def _row(view, pid):
    return next(p for p in view["parts"] if p["work"] == pid)


def _task(c, wid):
    return next(w for w in c.get("/api/works").json() if w["id"] == wid)["task"]


def test_frame_needs_applied_divisions_and_fresh_analysis_then_fixes_the_bytes(client):
    """진짜 길: 빈 양식 → 까닭(noValues → notApplied → staleHeadings) → 기준본 = 그때의 저장 바이트 + 자리 정보 · 내려받는 파일이 그 바이트 · 구분 기준이 되돌아가면 낡음."""
    c = client
    to = _upload(c, "계획서.hwpx", M.PLAN_FORM.read_bytes())
    v = c.get(f"/api/docs/{to}/gather").json()
    assert v == {"project": "", "reasons": ["noValues"], "frame": None, "version": 0, "orgs": [], "parts": []}
    _why(c.post(f"/api/docs/{to}/gather/frame"), 409, "noValues")
    _why(c.get(f"/api/docs/{to}/gather/frame/file"), 404, "noFrame")
    assert c.put(f"/api/docs/{to}/divisions/settings", json={"values": D.VALUES}).status_code == 200
    _why(c.post(f"/api/docs/{to}/gather/frame"), 409, "notApplied")
    v = c.get(f"/api/docs/{to}/gather").json()
    assert v["reasons"] == ["notApplied"] and [(o["key"], o["role"]) for o in v["orgs"]] == [(D.LEAD, "lead"), (J1, "joint"), (J2, "joint")]   # 기관은 입력 중인 값으로도 보인다
    plan = c.post(f"/api/docs/{to}/divisions/plan", json={}).json()
    assert c.post(f"/api/docs/{to}/divisions/apply", json={"planId": plan["planId"]}).status_code == 200
    _why(c.post(f"/api/docs/{to}/gather/frame"), 409, "staleHeadings")   # 분석이 아예 없을 때도 같은 까닭(화면이 2·3단계를 다시 건다)
    s = server._sess(to)
    HR.run_sync(s, 2, False)
    _why(c.post(f"/api/docs/{to}/gather/frame"), 409, "staleHeadings")   # 2단계만으로는 안 된다
    HR.run_sync(s, 3, False)
    r = c.post(f"/api/docs/{to}/gather/frame")
    assert r.status_code == 200, r.text
    v = r.json()
    fr = v["frame"]
    assert v["reasons"] == [] and v["version"] == 1 and fr["rev"] == s.rev == 1 and fr["stale"] is False and len(fr["frameId"]) == 12 and fr["at"][:2] == "20"
    data = c.get(f"/api/docs/{to}/gather/frame/file")
    assert data.status_code == 200 and "attachment" in data.headers["content-disposition"] and data.content == GA._blob(to, f"frame-{fr['frameId']}.hwpx")
    with s.lock:
        assert data.content == s.doc.save()   # 고정한 바이트 = 그때의 문서(그 뒤 안 고쳤다)
    stored = GA._frame(to, fr["frameId"])
    assert stored["sha256"] == server.works.sha256(data.content) and stored["runs"] == {"stage2": HR.graph(s)["meta"]["run"], "stage3": HR.tables(s)["meta"]["run"]}
    assert stored["division"] == {"planId": plan["planId"], "rev": 1} and [o["key"] for o in stored["orgs"]] == [D.LEAD, J1, J2]
    assert {b["id"] for b in stored["blocks"]} <= {b["id"] for b in s.doc.blocks()} and {"label", "guide", "title", "table"} <= {b["cls"] for b in stored["blocks"]}
    folder = server.works.folder(to)
    assert (folder / "gather.json").is_file() and sorted(p.name for p in (folder / "gather").iterdir()) == [f"frame-{fr['frameId']}.hwpx", f"frame-{fr['frameId']}.json.gz"]
    first = next(b["id"] for b in s.doc.blocks() if b["type"] == "paragraph" and b["text"].strip())
    assert c.patch(f"/api/docs/{to}/blocks/{first}", json={"text": "고친 표지 글"}).status_code == 200   # 글을 고친 것은 기준본을 낡게 하지 않는다(그 자리만 겹침이 된다) — 새 기준본은 분석부터 다시
    v = c.get(f"/api/docs/{to}/gather").json()
    assert v["frame"]["stale"] is False and v["reasons"] == ["staleHeadings"] and c.get(f"/api/docs/{to}/gather/frame/file").content == data.content
    assert c.post(f"/api/docs/{to}/undo").status_code == 200   # 구분 기준 반영을 되돌림 = 기준본을 만든 문서가 아니다
    v = c.get(f"/api/docs/{to}/gather").json()
    assert v["frame"]["stale"] is True and v["frame"]["frameId"] == fr["frameId"] and v["reasons"] == ["notApplied"]


@pytest.mark.parametrize("different", [{"project": "다른 프로젝트"}, {"job": "plan_to_report"}, {"round": 1}])
def test_gather_parts_cannot_cross_task_rounds(client, different):
    """미소속 파일은 현재 라운드에 붙이고, 등록 전후의 다른 그룹 문서는 사용하지 않는다."""
    from types import SimpleNamespace
    from app import works

    data = (M.ROOT / "samples" / "기술수요조사서.hwpx").read_bytes()
    to = _upload(client, "취합.hwpx", data)
    part = _upload(client, "기관.hwpx", data)
    task = {"kind": "rnd", "file": "plan", "job": "plan_merge", "project": "선박", "round": 2}
    works.update(to, task=task)
    outsider = {**task, "file": "part", **different}
    works.update(part, task=outsider)
    url = f"/api/docs/{to}/gather/parts/{part}"
    _why(client.put(url, json={}), 400, "badPart")
    assert GA._store(to)["parts"] == {} and works.work(part)["task"] == outsider

    works.update(part, task={})
    response = client.put(url, json={})
    assert response.status_code == 200, response.text
    assert works.work(part)["task"] == {**task, "file": "part"}
    version = GA._store(to)["version"]
    scope = GA._part_scope(to, part)
    works.update(part, task={})
    GA._PLANS[(to, part)] = {"planId": "detached", "scope": scope}
    _why(client.post(url + "/apply", json={"planId": "detached"}), 409, "stalePlan")
    GA._DROPS[to] = {"planId": "detached-drop", "from": part, "scope": scope}
    _why(client.post(f"/api/docs/{to}/gather/drop/apply", json={"planId": "detached-drop"}), 409, "stalePlan")
    works.update(part, task=outsider)
    _why(client.put(url, json={"common": False}), 400, "badPart")
    assert GA._store(to)["version"] == version
    GA._JUDGE[(to, part)] = (("frame", 0, version, 0, (), ()), {"cached": True})
    with pytest.raises(GA._Why, match="badPart"):
        GA._compute(SimpleNamespace(id=to), {}, {}, part)
    GA._PLANS[(to, part)] = {"planId": "old-scope"}
    _why(client.post(url + "/apply", json={"planId": "old-scope"}), 409, "stalePlan")
    _why(client.post(f"/api/docs/{to}/gather/drop/plan", json={"from": part, "srcId": "p1", "afterId": "p2"}), 400, "notPart")
    assert client.delete(url).status_code == 200
    assert works.work(part)["task"] == outsider  # 옛 취합에서 빼도 옮겨 간 문서의 역할은 그대로.


def test_register_assign_plan_apply_replan_undo_and_decisions(client):
    c = client
    to, v = _master(c)
    assert v["frame"] and v["version"] == 1 and c.get(f"/api/docs/{to}/gather/frame/file").content == D.base()["side"]["bytes"]
    other = _upload(c, "참고문서.hwpx", (M.ROOT / "samples" / "기술수요조사서.hwpx").read_bytes())
    assert c.put(f"/api/works/{other}/task", json={"kind": "rnd", "file": "", "job": "", "project": "다른 과제"}).status_code == 200
    docx = _upload(c, "조사서.docx", (M.ROOT / "samples" / "기술수요조사서.docx").read_bytes())
    for bad, status in ((to, 400), (other, 400), (docx, 400), ("0" * 12, 404), ("x", 400)):   # 취합본 자신 · 다른 과제 · hwpx 아님 · 없는 문서 · id 꼴이 아님
        _why(c.put(f"/api/docs/{to}/gather/parts/{bad}", json={}), status, "badPart")
    _why(c.put(f"/api/docs/{to}/gather/parts/{docx}", json={"orgs": "가나대"}), 400, "badValue")
    A = _upload(c, "기관A_가나대.hwpx", _bytes(_edit_a))
    v = c.put(f"/api/docs/{to}/gather/parts/{A}", json={}).json()
    assert v["version"] == 2 and [p["work"] for p in v["parts"]] == [A]
    assert _row(v, A) == {"work": A, "name": "기관A_가나대.hwpx", "order": 0, "orgs": [], "orgsBy": None, "common": True, "frameId": v["frame"]["frameId"], "state": "blocked", "counts": None, "todo": None,
                          "llm": None, "recommend": None, "reasons": ["noHeadings"]}   # 분석 전 — 그 줄에만 까닭(전체는 나간다)
    _why(c.get(f"/api/docs/{to}/gather/parts/{A}/links"), 409, "noHeadings")
    assert _task(c, A) == {"kind": "rnd", "file": "part", "job": "plan_merge", "project": "취합 시험"} and _task(c, to)["file"] == "plan"
    _analysed(A)
    B = _part(c, to, "기관B_다라연.hwpx", _edit_b)
    v = c.get(f"/api/docs/{to}/gather").json()
    assert [p["work"] for p in v["parts"]] == [A, B] and v["version"] == 3 and _task(c, A)["file"] == "part" and _task(c, B)["file"] == "part"   # 더해도 앞의 기관 문서가 남는다
    _why(c.get(f"/api/docs/{to}/gather/parts/{other}/links"), 404, "notPart")

    # 반영할 기관 미지정 = 아무것도 안 넣음(추천은 보이기만)
    L0 = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()
    assert L0["counts"] == {"unassigned": 4} and L0["todo"] == 0 and L0["part"]["state"] == "unassigned" and L0["part"]["recommend"] == {"org": J1, "n": 3, "tie": False}
    assert L0["coverage"]["ratio"] > 0.95 and L0["share"] == 1.0 and L0["reasons"] == [] and L0["llm"] is None
    assert all(set(it) == {"key", "kind", "status", "detail", "scope", "path", "to", "from", "text", "counts", "unique", "decision"} and set(it["from"]) == {"ids", "table", "at"} and set(it["to"]) == {"prev", "next", "at"} for it in L0["items"])
    spot = {it["kind"]: (it["to"]["at"], it["from"]["at"]) for it in L0["items"] if it["scope"]["kind"] == "org"}   # 화면이 갈 자리 — 표 칸·표 행은 표가 아니라 그 칸
    assert all(a and b for a, b in spot.values()) and spot["cells"][0].startswith("c") and spot["cells"][1].startswith("c") and spot["rows"][1].startswith("c") and spot["filled"][1].startswith("p")
    p0 = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert p0["todo"] == 0 and p0["items"] == [] and p0["skipped"] == {"unassigned": 4}
    before = _texts(to)
    r = c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": p0["planId"]})
    assert r.status_code == 200 and r.json()["nothing"] is True and r.json()["rev"] == 0 and _texts(to) == before

    # 기관을 지정 → 계획 → 반영
    v = c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J1]}).json()
    assert v["version"] == 4 and _row(v, A)["counts"] == {"ready": 4} and _row(v, A)["todo"] == 4 and _row(v, A)["state"] == "todo"
    assert {o["key"]: (o["received"], o["applied"]) for o in v["orgs"]} == {D.LEAD: ([], []), J1: ([A], []), J2: ([], [])}
    _why(c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": p0["planId"]}), 409, "stalePlan")   # 설정을 바꾸면 세워 둔 계획은 못 쓴다
    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert plan["todo"] == 4 and plan["skipped"] == {} and sorted(it["kind"] for it in plan["items"]) == ["cells", "filled", "filled", "rows"] and plan["counts"]["paragraphs"] == 2
    assert all({"key", "kind", "scope", "path", "text", "to", "from", "counts", "decision"} <= set(it) and it["to"]["prev"] for it in plan["items"])
    done = c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]})
    assert done.status_code == 200, done.text[:600]
    out = done.json()
    assert set(out["counts"]) == {"hunks", "blocks", "paragraphs", "tables", "pictures", "placeholders", "cells", "rows", "shaped", "fitted", "converted", "kept", "over", "recalculated", "skipped"}   # converted·kept = 틀 맞춤(§4-4) · over = 넘친 개요 줄(spec_병합 ② §5-5)
    assert out["counts"] == {**out["counts"], "hunks": 4, "paragraphs": 2, "placeholders": 2, "cells": 1, "rows": 1, "skipped": 0} and (out["rev"], out["undo"]) == (1, 1)
    assert out["calc"] == [] and out["dropped"] == [] and out["skipped"] == []
    tx = _texts(to)
    i = tx.index(f"[공동연구개발기관1({J1})]")
    assert tx[i + 1] == f"o {J1} 1차년도 개발 목표" and tx[tx.index("□ 필요성") + 1] == f"o {J1}가 쓴 필요성"
    assert server._sess(A).rev == 0 and server._sess(A).pristine_file()   # 기관 문서는 그대로
    _why(c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]}), 409, "stalePlan")   # 같은 계획을 두 번 못 쓴다
    saved = GA._store(to)
    assert saved["version"] == 4 and len(saved["parts"][A]["applied"]) == 4 and all(set(x) == {"at", "ids", "fp", "kind", "ev"} for x in saved["parts"][A]["applied"].values())   # 넣은 기록은 판을 안 올린다 · ev = 그 편집이 적은 출처 이벤트 id(spec_구역 ② §4)

    # 다시 계획 = 할 일 없음 · 기관 현황의 반영한 기관
    v = c.get(f"/api/docs/{to}/gather").json()
    assert _row(v, A)["counts"] == {"same": 4} and _row(v, A)["todo"] == 0 and _row(v, A)["state"] == "done" and {o["key"]: o["applied"] for o in v["orgs"]}[J1] == [A]
    again = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert again["todo"] == 0 and again["skipped"] == {"same": 4}
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": again["planId"]}).json()["nothing"] is True

    # 뺐다가 다시 넣어도 넣은 기록이 이어진다(이어 넣는 표의 행은 기록으로만 「이미 넣음」 — 두 번 넣지 않는다) · 빼면 종류 꼬리표만 뗀다
    v = c.delete(f"/api/docs/{to}/gather/parts/{A}").json()
    assert [p["work"] for p in v["parts"]] == [B] and _task(c, A) == {"kind": "rnd", "file": "", "job": "plan_merge", "project": "취합 시험"} and f"o {J1}가 쓴 필요성" in _texts(to)
    _why(c.delete(f"/api/docs/{to}/gather/parts/{A}"), 404, "notPart")
    v = c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J1]}).json()
    assert [p["work"] for p in v["parts"]] == [B, A] and _row(v, A)["counts"] == {"same": 4} and _task(c, A)["file"] == "part"

    # 실행 취소 = 다시 할 일(넣은 블록이 없어 기록을 안 믿는다)
    assert c.post(f"/api/docs/{to}/undo").status_code == 200
    L1 = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()
    assert L1["counts"] == {"ready": 4} and L1["todo"] == 4 and [it["key"] for it in L1["items"]] == [it["key"] for it in L0["items"]]   # 열쇠는 그대로

    # 사람이 고름 — 뺌 · 되돌리기 · 막힌 것은 못 넣는다
    key = next(it["key"] for it in L1["items"] if it["kind"] == "cells")
    n = GA._store(to)["version"]
    L2 = c.put(f"/api/docs/{to}/gather/parts/{A}/links/{key}", json={"value": "skip"}).json()
    it = next(x for x in L2["items"] if x["key"] == key)
    assert (it["status"], it["decision"]) == ("ready", {"value": "skip", "source": "user"}) and L2["todo"] == 3 and L2["counts"] == {"ready": 4} and GA._store(to)["version"] == n + 1
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()["skipped"] == {"skip": 1}
    L3 = c.put(f"/api/docs/{to}/gather/parts/{A}/links/{key}", json={"value": None}).json()
    assert next(x for x in L3["items"] if x["key"] == key)["decision"] is None and L3["todo"] == 4
    _why(c.put(f"/api/docs/{to}/gather/parts/{A}/links/없는열쇠", json={"value": "skip"}), 404, "noKey")
    _why(c.put(f"/api/docs/{to}/gather/parts/{A}/links/{key}", json={"value": "insert"}), 400, "badValue")
    LB = c.put(f"/api/docs/{to}/gather/parts/{B}", json={"orgs": [J1]}).json()   # 다라연 문서에 가나대를 지정 — 다라연 자리의 글은 다른 기관 자리
    assert _row(LB, B)["counts"] == {"otherOrg": 1, "ready": 1}
    other_key = next(x["key"] for x in c.get(f"/api/docs/{to}/gather/parts/{B}/links").json()["items"] if x["status"] == "otherOrg")
    kept = c.put(f"/api/docs/{to}/gather/parts/{B}/links/{other_key}", json={"value": "keep"}).json()
    assert next(x for x in kept["items"] if x["key"] == other_key)["status"] == "otherOrg" and kept["todo"] == 1   # 「넣음」 은 막힌 상태를 못 푼다


def test_second_part_overlaps_the_common_place_and_stale_plans_are_refused(client):
    c = client
    to, v = _master(c)
    A = _part(c, to, "기관A_가나대.hwpx", _edit_a, orgs=[J1])
    B = _part(c, to, "기관B_다라연.hwpx", _edit_b, orgs=[J2])
    assert [p["todo"] for p in c.get(f"/api/docs/{to}/gather").json()["parts"]] == [4, 2]   # 반영 전에는 둘 다 넣을 수 있다
    pa = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    pb = c.post(f"/api/docs/{to}/gather/parts/{B}/plan").json()
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": pa["planId"]}).status_code == 200
    _why(c.post(f"/api/docs/{to}/gather/parts/{B}/apply", json={"planId": pb["planId"]}), 409, "stalePlan")   # 앞 문서를 반영하기 전에 세운 계획 — 취합본이 바뀌었다
    LB = c.get(f"/api/docs/{to}/gather/parts/{B}/links").json()
    common = next(it for it in LB["items"] if it["scope"]["kind"] == "common")
    assert LB["counts"] == {"overlap": 1, "ready": 1} and common["status"] == "overlap" and f"{J1}가 쓴 필요성" in common["detail"]   # 먼저 들어온 것을 두고 뒤의 것은 겹침
    pb = c.post(f"/api/docs/{to}/gather/parts/{B}/plan").json()
    assert pb["todo"] == 1 and pb["skipped"] == {"overlap": 1}
    v = c.put(f"/api/docs/{to}/gather/parts/{B}", json={"common": False}).json()   # 설정이 바뀜(판 +1) → 계획이 낡는다
    assert _row(v, B)["common"] is False and _row(v, B)["counts"] == {"otherOrg": 1, "ready": 1}
    _why(c.post(f"/api/docs/{to}/gather/parts/{B}/apply", json={"planId": pb["planId"]}), 409, "stalePlan")
    pb = c.post(f"/api/docs/{to}/gather/parts/{B}/plan").json()
    first = next(b["id"] for b in server._sess(to).doc.blocks() if b["type"] == "paragraph" and b["text"].strip())
    assert c.patch(f"/api/docs/{to}/blocks/{first}", json={"text": "계획 뒤에 고친 글"}).status_code == 200   # 계획 뒤 취합본을 고침
    _why(c.post(f"/api/docs/{to}/gather/parts/{B}/apply", json={"planId": pb["planId"]}), 409, "stalePlan")
    pb = c.post(f"/api/docs/{to}/gather/parts/{B}/plan").json()
    server._sess(B).rev += 1   # 계획 뒤 기관 문서가 바뀜
    _why(c.post(f"/api/docs/{to}/gather/parts/{B}/apply", json={"planId": pb["planId"]}), 409, "stalePlan")
    server._sess(B).rev -= 1
    pb = c.post(f"/api/docs/{to}/gather/parts/{B}/plan").json()
    assert c.post(f"/api/docs/{to}/gather/parts/{B}/apply", json={"planId": pb["planId"]}).json()["counts"]["hunks"] == 1
    tx = _texts(to)
    assert f"o {J2} 1차년도 개발 목표" in tx and f"o {J1}가 쓴 필요성" in tx and f"o {J2}가 쓴 필요성" not in tx
    v = c.get(f"/api/docs/{to}/gather").json()
    assert {o["key"]: (o["received"], o["applied"]) for o in v["orgs"]} == {D.LEAD: ([], []), J1: ([A], [A]), J2: ([B], [B])} and [p["todo"] for p in v["parts"]] == [0, 0]

    # 기준본이 낡음 · 다른 판 — 저절로 안 넣는다
    s = server._sess(to)
    s.division["applied"] = {**s.division["applied"], "planId": "p2", "rev": s.rev}   # 구분 기준을 다시 반영한 것
    v = c.get(f"/api/docs/{to}/gather").json()
    assert v["frame"]["stale"] is True and [p["reasons"] for p in v["parts"]] == [["frameStale"]] * 2 and [p["state"] for p in v["parts"]] == ["blocked"] * 2
    for call in (c.get(f"/api/docs/{to}/gather/parts/{A}/links"), c.post(f"/api/docs/{to}/gather/parts/{A}/links"), c.post(f"/api/docs/{to}/gather/parts/{A}/plan"), c.post(f"/api/docs/{to}/gather/parts/{A}/llm")):
        _why(call, 409, "frameStale")
    _analysed(to, D.base()["side"]["graph"], D.base()["side"]["tables"])   # 지금 차례의 분석으로 새 판
    old = v["frame"]["frameId"]
    v = c.post(f"/api/docs/{to}/gather/frame").json()
    assert v["frame"]["frameId"] != old and v["frame"]["stale"] is False and [p["reasons"] for p in v["parts"]] == [["frameDiffers"]] * 2 and _row(v, A)["frameId"] == old
    _why(c.get(f"/api/docs/{to}/gather/parts/{A}/links"), 409, "frameDiffers")
    assert c.get(f"/api/docs/{to}/gather/frame/file").content != D.base()["side"]["bytes"]   # 새 판의 바이트(넣은 내용이 든 문서)


def test_apply_marks_the_last_fill_and_refit_fp_keeps_untouched_records_same(client):
    """마지막 반영 표식 gather.json filled{at, rev, part, kind, ids}(「넣은 뒤 템플릿 · 서식 정리」 가 읽는다 — spec_병합 ② §5-9 · 판은 안 올린다) · 넣을 것 0 이면 안 적는다 ·
    넣은 줄을 바꾼 편집 뒤 refit_fp(편집 전에 잡은 fp_matches)를 하면 다음 판정이 그 기록을 「같음」 으로 본다 — 편집 전에 이미 안 맞던 기록(사람이 넣은 뒤 고친 것)은 그대로 둔다."""
    from app import merge_gather as MG
    c = client
    to, _v = _master(c)
    A = _part(c, to, "기관A_가나대.hwpx", _edit_a, orgs=[J1])
    assert "filled" not in GA._store(to)
    n = GA._store(to)["version"]
    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    done = c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]}).json()
    G = GA._store(to)
    f = G["filled"]
    body = {k: v for k, v in G["parts"][A]["applied"].items() if v["kind"] in MG.BODY}
    assert set(f) == {"at", "rev", "part", "kind", "ids"} and (f["rev"], f["part"], f["kind"]) == (done["rev"], A, "fill") and isinstance(f["at"], float)
    assert f["ids"] and set(f["ids"]) == {i for v in body.values() for i in v["ids"]} and G["version"] == n   # 본문 기록의 넣은 블록만(칸 · 행 기록은 칸 id) · 판은 그대로
    again = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": again["planId"]}).json()["nothing"] is True and GA._store(to)["filled"] == f   # 넣을 것 0 — 표식 그대로

    s = server._sess(to)
    assert GA.fp_matches(to, s.doc.blocks()) == {(A, k) for k in body} and len(body) == 2
    text = lambda i: next(b for b in s.doc.blocks() if b["id"] == i).get("text") or ""  # noqa: E731
    para = {k: next(i for i in v["ids"] if text(i).strip()) for k, v in body.items()}   # 기록마다 글이 든 넣은 문단(본문 기록의 ids = 새 최상위 블록)
    (kx, px), (ky, py) = sorted(para.items())
    assert c.patch(f"/api/docs/{to}/blocks/{px}", json={"text": text(px) + " — 사람이 고침"}).status_code == 200   # 넣은 뒤 사람이 고친 기록
    assert c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["counts"].get("same") == 3
    matched = GA.fp_matches(to, s.doc.blocks())
    assert matched == {(A, k) for k in body if k != kx}
    assert c.patch(f"/api/docs/{to}/blocks/{py}", json={"text": text(py).replace("o ", "ㅇ ", 1)}).status_code == 200   # 정리가 넣은 줄의 레터 글자를 닮은 글자로 바꿈
    assert c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["counts"].get("same") == 2
    assert GA.refit_fp(to, s.doc.blocks(), matched) == 1 and GA._store(to)["version"] == n
    counts = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["counts"]
    assert counts.get("same") == 3 and sum(counts.values()) == 4   # 정리가 바꾼 기록은 다시 「같음」 · 사람이 고친 기록은 그대로 「같음」 이 아니다
    assert GA.refit_fp(to, s.doc.blocks(), set()) == 0

    # 표식을 적기 전 판에 넣은 취합본(넣은 기록은 있고 filled 가 없다) — 넣은 뒤 정리의 재료를 읽을 때 한 번 적는다(안 그러면 「넣은 내용이 없습니다」 · 줄이 「건너뜀」 — 다시 반영해도 넣을 것 0 이라 표식이 안 생긴다)
    from app import merge_retidy_api as RA
    GA._change(to, lambda G: G.pop("filled"), bump=False)
    fa = RA.facts(to)
    f2 = GA._store(to)["filled"]
    assert fa["why"] == "" and fa["fill"] == f2["at"] and fa["inserted"] == len(f["ids"]) and (f2["legacy"], f2["rev"], f2["part"]) == (True, s.rev, None) and set(f2["ids"]) == set(f["ids"])
    assert RA.facts(to)["fill"] == f2["at"] and GA._store(to)["version"] == n   # 한 번만 적는다 · 판은 그대로
    GA._store(to, {**GA._store(to), "parts": {}, "filled": None})
    assert RA.facts(to)["why"] == RA.NO_FILL and not GA._store(to).get("filled")   # 넣은 기록이 없으면 적지 않는다


def test_documents_not_made_from_the_frame_are_never_planned_until_a_person_keeps_a_hunk(client):
    c = client
    to, v = _master(c)
    raw = _part(c, to, "다른과제_같은양식.hwpx", data=M.PLAN_FORM.read_bytes(), orgs=[D.LEAD, J1, J2])     # 같은 양식 · 기준본에서 나오지 않음(값을 반영하지 않은 빈 양식)
    report = _part(c, to, "연차보고서.hwpx", data=M.REPORT_FORM.read_bytes(), orgs=[D.LEAD, J1, J2])     # 다른 양식
    alien = _part(c, to, "조사서.hwpx", data=(M.ROOT / "samples" / "기술수요조사서.hwpx").read_bytes(), orgs=[J1])
    v = c.get(f"/api/docs/{to}/gather").json()
    assert _row(v, alien)["reasons"] == ["noMatch"] and _row(v, alien)["state"] == "blocked" and _row(v, alien)["counts"] is None
    _why(c.get(f"/api/docs/{to}/gather/parts/{alien}/links"), 409, "noMatch")
    _why(c.post(f"/api/docs/{to}/gather/parts/{alien}/plan"), 409, "noMatch")
    L1, L2 = (c.get(f"/api/docs/{to}/gather/parts/{p}/links").json() for p in (raw, report))
    assert L1["coverage"]["ratio"] >= GA.LOW_MATCH and L1["share"] < GA.LABEL_MATCH   # 같은 양식은 맞은 정도가 높다 — 기관 이름이 든 구분 라벨로 가린다
    assert L2["coverage"]["ratio"] < GA.LOW_MATCH
    before = _texts(to)
    for pid, L in ((raw, L1), (report, L2)):
        ready = [it for it in L["items"] if it["status"] == "ready"]
        assert L["reasons"] == ["lowMatch"] and L["part"]["reasons"] == ["lowMatch"] and ready and L["todo"] == 0 and L["counts"]["ready"] == len(ready)
        assert all(it["decision"] == {"value": "check", "source": "auto", "reason": "기준본과 자리를 충분히 확인하지 못한 문서"} for it in ready)
        assert all(it["decision"] is None for it in L["items"] if it["status"] != "ready")
        p = c.post(f"/api/docs/{to}/gather/parts/{pid}/plan").json()
        assert p["todo"] == 0 and p["skipped"]["check"] == len(ready)
        assert c.post(f"/api/docs/{to}/gather/parts/{pid}/apply", json={"planId": p["planId"]}).json()["nothing"] is True
    assert _texts(to) == before and [(_row(v, p)["todo"], _row(v, p)["reasons"]) for p in (raw, report)] == [(0, ["lowMatch"])] * 2
    pick = next(it for it in L1["items"] if it["status"] == "ready")
    L1 = c.put(f"/api/docs/{to}/gather/parts/{raw}/links/{pick['key']}", json={"value": "keep"}).json()   # 사람이 넣음으로 고른 것만
    assert L1["todo"] == 1 and next(it for it in L1["items"] if it["key"] == pick["key"])["decision"] == {"value": "keep", "source": "user"}
    p = c.post(f"/api/docs/{to}/gather/parts/{raw}/plan").json()
    assert p["todo"] == 1 and [it["key"] for it in p["items"]] == [pick["key"]]
    assert c.post(f"/api/docs/{to}/gather/parts/{raw}/apply", json={"planId": p["planId"]}).json()["counts"]["hunks"] == 1 and _texts(to) != before


def _payload(job):
    return json.loads(job["content"].split("## 자료(JSON)\n", 1)[1])


def test_llm_review_narrows_holds_keeps_user_choices_and_shows_its_prompts(client, monkeypatch, tmp_path):
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "plan_merge.md").write_text("# 할 일 프롬프트 — 시험 취합\n\n- 겹치면 덮지 않는다(시험 표식)\n", encoding="utf-8")
    c = client
    to, v = _master(c)
    A = _part(c, to, "기관A_가나대.hwpx", _edit_a, orgs=[J1])
    B = _part(c, to, "기관B_다라연.hwpx", _edit_b, orgs=[J2])
    items = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["items"]
    by = {(it["kind"], it["scope"]["kind"]): it["key"] for it in items}
    cells, rows, own, common = by[("cells", "org")], by[("rows", "org")], by[("filled", "org")], by[("filled", "common")]
    assert c.put(f"/api/docs/{to}/gather/parts/{A}/links/{common}", json={"value": "skip"}).status_code == 200   # 사람이 먼저 뺀 것 — 보내지도 않는다
    n, jobs = GA._store(to)["version"], []

    monkeypatch.setattr(llm, "ask_all", lambda js, **kw: [{"data": None, "backend": None, "error": "off", "model": j["model"]} for j in js])
    _why(c.post(f"/api/docs/{to}/gather/parts/{A}/llm"), 409, "noLlm")   # 꺼진 LLM 을 「전부 보류」 로 적지 않는다
    assert GA._store(to)["version"] == n and GA._store(to)["parts"][A]["llm"] is None

    def ask(js, **kw):   # 표 칸 = 안내 글이라 제외 · 표 행 = 답 없음(보류) · 그 밖 = 유지
        jobs.extend(js)
        out = []
        for j in js:
            said = {"cells": ("안내", "제외"), "rows": None}
            rev = [{"id": h["id"], "inputHash": h["inputHash"], "nature": a[0], "verdict": a[1], "reason": "시험 까닭"} for h in _payload(j)["hunks"] if (a := said.get(h["kind"], ("내용", "유지")))]
            out.append({"data": {"reviews": rev, "summary": ""}, "backend": "fake", "model": j["model"], "error": None})
        return out
    monkeypatch.setattr(llm, "ask_all", ask)
    r = c.post(f"/api/docs/{to}/gather/parts/{A}/llm")
    assert r.status_code == 200, r.text[:400]
    L = r.json()
    sent = [h["id"] for j in jobs for h in _payload(j)["hunks"]]
    assert sorted(sent) == sorted([cells, rows, own]) and all(j["model"] == "claude-opus-5-5" and "겹치면 덮지 않는다(시험 표식)" in j["content"] for j in jobs)
    assert _payload(jobs[0])["doc"]["part"] == "기관A_가나대.hwpx" and _payload(jobs[0])["doc"]["assigned"] == [J1]
    d = {it["key"]: it["decision"] for it in L["items"]}
    assert d[cells] == {"value": "skip", "source": "llm", "nature": "안내", "reason": "시험 까닭"} and d[own] == {"value": "keep", "source": "llm", "nature": "내용", "reason": "시험 까닭"}
    assert (d[rows]["value"], d[rows]["source"], d[rows]["held"]) == ("check", "llm", True) and d[common] == {"value": "skip", "source": "user"}
    assert L["todo"] == 1 and L["counts"] == {"ready": 4} and L["part"]["llm"] == {"at": L["llm"]["at"], "held": 1, "stale": 0}   # 좁히기만 — 상태는 그대로
    assert (L["llm"]["held"], L["llm"]["rejected"], L["llm"]["job"]["job"], L["llm"]["guide"]["name"], L["llm"]["counts"]) == (1, 0, "plan_merge", "gather", {"targets": 3, "opinions": 0, "user": 1})
    assert len([u for u in L["llm"]["units"] if u["call"]]) == len(jobs) and all("prompt" not in u and "answer" not in u for u in L["llm"]["units"])
    assert GA._store(to)["version"] == n + 1 and c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()["skipped"] == {"skip": 2, "check": 1}
    # 화면 「지침」 — 계약 · 판단 지침 · 할 일 프롬프트 + 그 기관 문서에 마지막으로 보낸 프롬프트
    g = c.get(f"/api/docs/{to}/llm-guide/gather?part={A}").json()
    assert (g["step"], g["name"], g["model"]) == ("gather", "취합 LLM 검토", "claude-opus-5-5") and [p["key"] for p in g["parts"]] == ["contract", "guide", "job"]
    assert g["parts"][1]["source"].endswith("gather.md") and g["parts"][2]["source"].endswith("plan_merge.md")
    assert len(g["last"]["units"]) == len(jobs) and all(u["has"] and u["chars"] > 1000 for u in g["last"]["units"]) and g["last"]["at"] == L["llm"]["at"]
    got = c.get(f"/api/docs/{to}/llm-guide/gather/prompt?unit={g['last']['units'][0]['n']}&part={A}").json()
    assert got["prompt"] in [j["content"] for j in jobs] and got["answer"]["reviews"]
    assert c.get(f"/api/docs/{to}/llm-guide/gather?part={B}").json()["last"] is None   # 기관 문서마다 따로
    assert c.get(f"/api/docs/{to}/llm-guide/gather/prompt?unit=0&part={B}").status_code == 404 and c.get(f"/api/docs/{to}/llm-guide/gather").json()["last"] is None
    # 사람이 LLM 판정을 뒤집음 → 되돌리면 LLM 판정으로
    L = c.put(f"/api/docs/{to}/gather/parts/{A}/links/{cells}", json={"value": "keep"}).json()
    assert next(it for it in L["items"] if it["key"] == cells)["decision"] == {"value": "keep", "source": "user", "nature": "안내", "reason": "시험 까닭"} and L["todo"] == 2
    L = c.put(f"/api/docs/{to}/gather/parts/{A}/links/{cells}", json={"value": None}).json()
    assert next(it for it in L["items"] if it["key"] == cells)["decision"]["source"] == "llm" and L["todo"] == 1
    # 다시 검토 — 사람이 고른 것은 그대로 · 이번 답으로 갈아 끼움
    jobs.clear()
    monkeypatch.setattr(llm, "ask_all", lambda js, **kw: jobs.extend(js) or [{"data": {"reviews": [
        {"id": h["id"], "inputHash": h["inputHash"], "nature": "내용", "verdict": "유지", "reason": "다시"} for h in _payload(j)["hunks"]], "summary": ""}, "error": None} for j in js])
    L = c.post(f"/api/docs/{to}/gather/parts/{A}/llm").json()
    d = {it["key"]: it["decision"] for it in L["items"]}
    assert L["todo"] == 3 and L["llm"]["held"] == 0 and d[common] == {"value": "skip", "source": "user"} and d[cells]["value"] == "keep"
    # 낡은 자료의 판정은 안 쓴다(inputHash 가 지금 자료와 다름)
    GA._change(to, lambda G: G["parts"][A]["decisions"][own].update(value="skip", inputHash="0" * 12))
    L = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()
    assert next(it for it in L["items"] if it["key"] == own)["decision"] is None and L["llm"]["stale"] == 1 and L["todo"] == 3
    # 반영 뒤에는 그 자리가 「이미 들어 있음」 — 낡은 판정으로 세지 않는다
    p = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": p["planId"]}).json()["counts"]["hunks"] == 3
    L = c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()
    assert L["counts"] == {"same": 3, "ready": 1} and L["llm"]["stale"] == 0 and L["todo"] == 0


def test_drop_plan_then_apply_and_what_is_refused(client):
    c = client
    b = D.base()["side"]
    to, v = _master(c, frame=False)   # 끌어 넣기는 기준본이 없어도 된다(기준본에서 나오지 않은 문서를 넣는 길)
    P = _upload(c, "기관P.hwpx", b["bytes"])   # 기준본 사본 그대로 — 블록 id·그래프가 캐시한 추출 결과와 같다
    assert c.put(f"/api/docs/{to}/gather/parts/{P}", json={}).status_code == 200
    doc, src = server._sess(to).doc, server._sess(P).doc
    need, after = D.para(src, "□ 필요성"), D.para(doc, "1-2. 연구개발과제의 배경 및 필요성")
    body = {"from": P, "srcId": need, "afterId": after}
    _why(c.post(f"/api/docs/{to}/gather/drop/plan", json=body), 409, "noHeadings")   # 기관 문서의 분석 전 — 절의 범위를 모른다(끈 줄 하나만 말없이 넣지 않는다)
    _analysed(P, b["graph"])
    loose = _upload(c, "취합밖.hwpx", b["bytes"])
    _why(c.post(f"/api/docs/{to}/gather/drop/plan", json={**body, "from": loose}), 400, "notPart")
    _why(c.post(f"/api/docs/{to}/gather/drop/plan", json={"from": P, "srcId": need}), 400, "badValue")
    cell = next(x for t in doc.blocks() if t["type"] == "table" for x in t["cells"] if x["blocks"])
    assert "표 칸 안에는 놓을 수 없습니다" in _why(c.post(f"/api/docs/{to}/gather/drop/plan", json={**body, "afterId": cell["blocks"][0]["id"]}), 400, "badDrop")["message"]
    assert "표 칸 안의 줄은 끌 수 없습니다" in _why(c.post(f"/api/docs/{to}/gather/drop/plan", json={**body, "srcId": cell["blocks"][0]["id"]}), 400, "badDrop")["message"]
    _why(c.post(f"/api/docs/{to}/gather/drop/apply", json={"planId": "없음"}), 409, "stalePlan")
    r = c.post(f"/api/docs/{to}/gather/drop/plan", json=body)
    assert r.status_code == 200, r.text[:400]
    p = r.json()
    assert set(p) == {"planId", "from", "range", "after", "owner", "convert", "dropped"} and p["from"] == P
    assert set(p["range"]) == {"title", "blocks", "paragraphs", "tables", "pictures", "lines", "single"} and p["range"]["title"] == "□ 필요성" and p["range"]["single"] is False and p["range"]["blocks"] >= 4
    assert p["after"] == {"id": after, "text": "1-2. 연구개발과제의 배경 및 필요성", "given": after} and p["owner"]["id"] == after
    assert set(p["convert"]) == {"converted", "kept", "labels", "anchor", "rows", "more"} and set(p["convert"]["kept"]) == set(p["convert"]["labels"])
    assert _texts(to).count("□ 필요성") == 1 and server._sess(to).rev == 0   # 계획은 문서를 안 바꾼다
    first = next(x["id"] for x in doc.blocks() if x["type"] == "paragraph" and x["text"].strip())
    assert c.patch(f"/api/docs/{to}/blocks/{first}", json={"text": "계획 뒤에 고친 글"}).status_code == 200   # 계획 뒤 취합본이 바뀜
    _why(c.post(f"/api/docs/{to}/gather/drop/apply", json={"planId": p["planId"], "convert": True}), 409, "stalePlan")
    p = c.post(f"/api/docs/{to}/gather/drop/plan", json=body).json()
    done = c.post(f"/api/docs/{to}/gather/drop/apply", json={"planId": p["planId"], "convert": False})
    assert done.status_code == 200, done.text[:400]
    out = done.json()
    assert out["blocks"] == p["range"]["blocks"] and out["converted"] == 0 and out["kept"] == {} and out["dropped"] == [] and (out["rev"], out["undo"]) == (2, 1) and len(out["ids"]) == out["blocks"]
    tx = _texts(to)
    i = tx.index("1-2. 연구개발과제의 배경 및 필요성")
    assert tx.count("□ 필요성") == 2 and tx[i + 1] == "□ 필요성" and server._sess(P).rev == 0   # 놓은 블록 바로 뒤에 · 기관 문서는 그대로
    _why(c.post(f"/api/docs/{to}/gather/drop/apply", json={"planId": p["planId"]}), 409, "stalePlan")   # 같은 계획을 두 번 못 쓴다
    assert c.post(f"/api/docs/{to}/undo").status_code == 200 and _texts(to).count("□ 필요성") == 1   # 실행 취소 한 번


def test_everything_stays_in_memory_when_work_storage_is_off(client, monkeypatch):
    monkeypatch.setenv("NFM_WORKS", "off")
    c = client
    to, v = _master(c, project=None)
    fid = v["frame"]["frameId"]
    assert v["project"] == "" and GA._MEM[to]["frameId"] == fid and set(k[1] for k in GA._BLOB) == {f"frame-{fid}.hwpx", f"frame-{fid}.json.gz"}
    assert c.get(f"/api/docs/{to}/gather/frame/file").content == D.base()["side"]["bytes"]
    P = _part(c, to, "기관P.hwpx", data=D.base()["side"]["bytes"], orgs=[J1])
    L = c.get(f"/api/docs/{to}/gather/parts/{P}/links").json()
    assert L["items"] == [] and L["coverage"]["ratio"] == 1.0 and L["part"]["state"] == "done" and GA._MEM[to]["parts"][P]["orgs"] == [J1]


OGOAL, OSUB, ODEEP = "가나대 넘침 목표", "가나대 넘침 세부", "가나대 넘침 더 깊은 줄"


def _edit_over(d):
    """가나대 문서 — 제 자리(취합본 틀 [기관]›o›- 의 L2)에 o · - 까지는 틀 안, 그 아래 「·」 줄은 틀에 없는 레벨(넘친 개요 레벨)."""
    o = next(i for i in (D.nxt(d, D.para(d, f"[공동연구개발기관1({J1})]", 0), k) for k in range(1, 12)) if next(b["text"] for b in D.top(d) if b["id"] == i).strip() == "o")
    d.set_text(o, f"  o {OGOAL}")
    d.insert_after(o, [{"kind": "paragraph", "text": f"    - {OSUB}"}, {"kind": "paragraph", "text": f"      · {ODEEP}"}])


def test_overflow_levels_choose_in_the_plan_then_refit_what_went_in(client):
    """넘친 개요 레벨(spec_병합 ② §5-5 — 취합): 계획에 사례가 보임 → 처리를 고르면 세워 둔 계획을 버림 → 그 처리로 반영 · 기록 → 다시 계획하면 넣은 줄의 사례로 보임 →
    넣은 뒤 다시 맞추기(덮은 그대로로) 뒤에도 판정은 「이미 들어 있음」(넣은 결과의 지문을 다시 적는다)."""
    c = client
    to, _ = _master(c)
    part = D.part(_edit_over, "fit-over")
    graph, tables = M._cached("gather-fit-over", part["bytes"], part["doc"], "fit-over.hwpx")   # 기관 문서의 2단계 그래프(틀 맞춤이 읽는다) — test_merge_gather_fit 과 같은 캐시
    A = _upload(c, f"기관A_{J1}.hwpx", part["bytes"])
    _analysed(A, graph, tables)
    assert c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J1]}).status_code == 200
    status = lambda: next(i for i in c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["items"] if OGOAL in i["text"])["status"]  # noqa: E731

    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    (case,) = plan["over"]["cases"]
    item = next(x for x in plan["items"] if (x.get("convert") or {}).get("over"))
    key = case["key"]
    assert item["convert"]["over"]["key"] == key and item["counts"]["over"] == 1 and plan["counts"]["over"] == 1 and item["convert"]["kept"] == {"tooDeep": 1}
    assert (case["mode"], case["lines"], case["applied"], case["to"]["level"], case["at"]) == ("cover", 1, 0, 3, item["to"]["prev"]) and [(x["n"], x["was"], x["lines"]) for x in case["levels"]][:1] == [(4, "·", 1)]
    assert plan["over"]["records"] == {"lines": 0, "cases": {}} and plan["over"]["templates"]

    r = c.put(f"/api/docs/{to}/merge-over", json={"key": key, "mode": "edit", "levels": [{"letter": "▪"}]})
    assert r.status_code == 200 and r.json()["case"]["mode"] == "edit"
    _why(c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]}), 409, "stalePlan")   # 처리를 바꾸면 세워 둔 계획은 못 쓴다
    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert (plan["over"]["cases"][0]["mode"], plan["over"]["cases"][0]["levels"][0]["letter"]) == ("edit", "▪")
    done = c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]})
    assert done.status_code == 200, done.text[:600]
    assert done.json()["counts"]["over"] == 1 and f"▪ {ODEEP}" in _texts(to) and f"o {OGOAL}" in _texts(to) and f"- {OSUB}" in _texts(to) and status() == "same"
    rec = next(v for v in GA._store(to)["parts"][A]["applied"].values() if (v.get("convert") or {}).get("over"))
    assert [(x["over"], x["was"], x["letter"]) for x in rec["convert"]["over"]["lines"]] == [(1, "·", "▪")] and rec["convert"]["over"]["key"] == key

    again = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()   # 다 넣은 뒤에도 그 사례는 넣은 줄의 기록으로 보인다
    assert again["todo"] == 0 and [(x["key"], x["lines"], x["applied"], x["mode"]) for x in again["over"]["cases"]] == [(key, 0, 1, "edit")] and again["over"]["records"] == {"lines": 1, "cases": {key: 1}}
    assert c.post(f"/api/docs/{to}/merge-over/refit", json={}).json()["nothing"] is True
    assert c.put(f"/api/docs/{to}/merge-over", json={"key": key, "reset": True}).status_code == 200
    rev, fp = server._sess(to).rev, rec["fp"]
    r = c.post(f"/api/docs/{to}/merge-over/refit", json={})
    assert r.status_code == 200 and (r.json()["lines"], r.json()["rev"]) == (1, rev + 1) and f"· {ODEEP}" in _texts(to) and f"▪ {ODEEP}" not in _texts(to)
    now = next(v for v in GA._store(to)["parts"][A]["applied"].values() if (v.get("convert") or {}).get("over"))
    assert now["convert"]["over"]["lines"][0]["letter"] == "·" and now["fp"] != fp and status() == "same"   # 레터가 바뀐 만큼 지문도 다시 — 판정은 그대로 「이미 들어 있음」


def test_retidy_on_a_gather_target_touches_only_inserted_lines_and_holds_the_chosen_overflow(client):
    """넣은 뒤 템플릿 · 서식 정리를 취합본에(spec_병합 ② §5-9 9 — 진짜 끝점 · 진짜 헤딩 다시 분석): 넣은 기록 = gather.json(마지막 반영 표식 · 본문 기록) ·
    취합본에 있던 줄은 한 바이트도 안 바뀐다(그 레벨에 취합본의 줄이 있으면 settle 하지 않음 · 「≈」 줄 없음) · 사람이 처리를 고른 넘친 줄(merge_over.json cases)은 맞추지 않는다 ·
    판정은 그대로 「이미 들어 있음」 · 두 번째는 할 것 없음 · 정리 기록의 fill = 그 반영 표식."""
    from lxml import etree

    from app import merge_gather as MG
    from app import merge_retidy_api as RA
    c = client
    to, _ = _master(c)
    part = D.part(_edit_over, "fit-over")
    graph, tables = M._cached("gather-fit-over", part["bytes"], part["doc"], "fit-over.hwpx")
    A = _upload(c, f"기관A_{J1}.hwpx", part["bytes"])
    _analysed(A, graph, tables)
    assert c.put(f"/api/docs/{to}/gather/parts/{A}", json={"orgs": [J1]}).status_code == 200
    assert c.post(f"/api/docs/{to}/merge-retidy", json={}).status_code == 409   # 넣은 기록이 없다
    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    key = plan["over"]["cases"][0]["key"]
    assert c.put(f"/api/docs/{to}/merge-over", json={"key": key, "mode": "edit", "levels": [{"letter": "▪"}]}).status_code == 200   # 사람이 넘친 레벨의 처리를 고름
    plan = c.post(f"/api/docs/{to}/gather/parts/{A}/plan").json()
    assert c.post(f"/api/docs/{to}/gather/parts/{A}/apply", json={"planId": plan["planId"]}).status_code == 200
    s, G = server._sess(to), GA._store(to)
    body = {i for v in G["parts"][A]["applied"].values() if v["kind"] in MG.BODY for i in v["ids"]}
    held = [x["id"] for v in G["parts"][A]["applied"].values() for x in ((v.get("convert") or {}).get("over") or {}).get("lines") or ()]
    R = RA._records(to)
    assert R["gather"] and R["n"] == len(body) == 3 and R["held"] == set(held) and len(held) == 1 and set(R["mark"]["ids"]) == body
    g = c.get(f"/api/docs/{to}/merge-retidy").json()
    assert (g["gather"], g["stale"], g["inserted"], g["why"]) == (True, True, 3, "")   # 반영 뒤 그래프가 낡았다 — 반영이 먼저 다시 분석한다
    xml = lambda: {b["id"]: etree.tostring(s.doc._ids[b["id"]]) for b in s.doc.blocks()}  # noqa: E731
    before = xml()
    r = c.post(f"/api/docs/{to}/merge-retidy", json={})
    assert r.status_code == 200 and r.json()["reanalyzed"] is True and not r.json().get("nothing"), r.text[:600]
    D_ = r.json()["done"]
    assert D_["counts"]["held"] == 1 and D_["counts"]["near"] == 0 and any(x["kind"] == "form" and x["form"] > 0 for x in D_["rows"]), D_   # 취합본의 줄이 있는 레벨(form)을 거쳤다
    after = xml()
    assert [i for i in before if i not in body and after.get(i) != before[i]] == []   # 취합본에 있던 줄은 그대로(뒤에 올 기관 문서가 그 줄의 글로 자리를 찾는다)
    assert all(after[i] == before[i] for i in held) and [i for i in body if after[i] != before[i]]   # 사람이 고른 넘친 줄은 그대로 · 넣은 줄은 맞춤
    assert next(i for i in c.get(f"/api/docs/{to}/gather/parts/{A}/links").json()["items"] if OGOAL in i["text"])["status"] == "same"
    again = c.post(f"/api/docs/{to}/merge-retidy", json={}).json()
    assert again["nothing"] is True and again["reanalyzed"] is False and xml() == after
    assert RA.load(to)["applied"]["fill"] == GA._store(to)["filled"]["at"] and RA.facts(to)["inserted"] == 3


# ---- 가져온 스키마 위반 종류(spec_병합 ② §5-10 「가져온 스키마 위반 종류」 — 취합 반영도 server.import_check · 옛 작업은 GA.owpml_from 으로 _heal) ------------------------
PIC_TABLE = "t12501"   # 연구개발계획서 양식의 그림이 든 표 — 연차보고서 서식에는 그림이 없다(그림 꼴의 종류가 목적 기준선에 없음)
PIC_KINDS = {("section", "renderingInfo", "transMatrix", "", "SCHEMAV_ELEMENT_CONTENT"), ("section", "imgRect", "pt0", "", "SCHEMAV_ELEMENT_CONTENT"),
             ("section", "pic", "inMargin", "", "SCHEMAV_ELEMENT_CONTENT")}


def test_gather_fill_carries_imported_kinds_and_legacy_heals(client):
    to = _upload(client, "연차보고서.hwpx", M.REPORT_FORM.read_bytes())
    pid = _upload(client, "기관 문서.hwpx", M.PLAN_FORM.read_bytes())
    s, src = server._sess(to), server._sess(pid)
    got = {}

    def run():
        got["new"] = s.doc.insert_after("p975", [{"kind": "copy", "srcId": PIC_TABLE}], src=src.doc)
        return {"hosts": [], "struct": set(), "origin": {}, "anchor": None}
    with s.lock, src.lock:
        out, after = GA._tx(s, src, run, "gatherFill", {"part": pid}, "applyFailed")
    assert after is not None and PIC_KINDS <= s.owpml_ok   # 반영(gatherFill · gatherDrop)이 들여온 종류를 작업에 남긴다
    t = next(b for b in client.get(f"/api/docs/{to}").json()["blocks"] if b["id"] == got["new"][0])
    para = next(x["id"] for c in t["cells"] for x in c["blocks"] if x["type"] == "paragraph")

    def edit():
        return client.post(f"/api/docs/{to}/format/para", json={"ids": [para], "changes": {"align": "right"}})
    assert edit().status_code == 200
    # 고침 전에 넣은 작업 — 받아들인 종류가 없다: 넣은 기록(gather.json 기관 문서의 applied)이 없으면 422, 있으면 처음 걸린 편집에서 받아들인다
    s.owpml_ok.clear()
    for u in s.undo:
        u["owpml_ok"] = set()
    assert GA.owpml_from(s) == [] and edit().status_code == 422
    GA._store(to, {"version": 1, "frameId": None, "order": [pid], "parts": {pid: {"name": "기관 문서", "applied": {"k": {"ids": [got["new"][0]], "at": "시험"}}}}})
    assert PIC_KINDS <= set(GA.owpml_from(s))
    r = edit()
    assert r.status_code == 200, r.text[:400]
    assert PIC_KINDS <= server._sess(to).owpml_ok
    # 끌어 넣은 출처(편집 구역의 출처 이벤트) · 뺀 기관 문서의 넣은 기록도 원본으로 본다
    GA._store(to, {"version": 2, "frameId": None, "order": [], "parts": {}, "gone": {pid: {"applied": {"k": {"ids": []}}}}})
    assert PIC_KINDS <= set(GA.owpml_from(s))
    GA._store(to, {"version": 3, "frameId": None, "order": [], "parts": {}})
    assert GA.owpml_from(s) == []
    s.zones["origins"].append({"id": "e1", "part": pid, "ids": []})
    assert PIC_KINDS <= set(GA.owpml_from(s))
