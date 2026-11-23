"""같은 양식 취합 API(spec_취합 ② §10 — app/merge_collect_api.py + app/merge_api.py 의 collect 가지)를 **실제 모듈**로: 등록부 · 자동 지정 · 기관 문서마다 못 박기 → 자리 연결 → 넣기 계획 → 반영 ·
출처 + 원장 · 다른 기관 문서의 자리는 겹침 · 수정본 3방향(고칠 곳 · 겹침 · 수정본에 없음) · 실행 취소. 자료 = gather_data(값을 반영한 양식 = 목적 문서 · 그 사본을 고쳐 다시 연 것 = 기관 문서 —
기관 문서의 헤딩 · 표 분석은 진짜로 돈다: 블록 id 가 목적 문서와 달라 캐시를 못 쓴다). 틀 판정(is_collect)은 끼운다 — 조립 틀은 tests/test_custom_tasks.py · 실행기 시험의 몫."""
import time

import pytest
from fastapi.testclient import TestClient

import gather_data as D
from app import heading_runs as HR
from app import merge_api, server
from app import merge_collect_api as CA

J1, J2 = D.J1, D.J2
_PARTS = {}
GOAL, GOAL2, CELL, CELL2 = f" o {J1} 1차년도 개발 목표", f" o {J1} 1차년도 개발 목표(개정)", "기술이전 30건", "기술이전 45건"


@pytest.fixture
def client(monkeypatch):
    server.DOCS.clear()
    for box in (CA._MEM, CA._RPLANS, merge_api._MEM, merge_api._PLANS, merge_api._CACHE, merge_api._FIXED):
        box.clear()
    monkeypatch.setattr(CA, "is_collect", lambda job: True)
    return TestClient(server.app)


def _edit(goal, cell, common=True):
    def edit(d):
        d.set_text(D.nxt(d, D.para(d, f"[공동연구개발기관1({J1})]", 0)), goal)                      # 제 자리(1차년도 ① 개발 목표)
        if common:
            d.set_text(D.nxt(d, D.para(d, "□ 필요성")), f" o {J1}가 쓴 필요성")                       # 공통 자리 — 기본은 안 넣는다
        tid = D.table_after(d, f"[공동연구개발기관 : {J1}]")                                          # 제 표의 빈 값 칸(머리 행 아래 첫 빈 칸)
        d.set_text(next(x for x in d.table_block(tid)["cells"] if x["row"] >= 1 and x["col"] >= 1 and not (x.get("text") or "").strip())["id"], cell)
    edit.__name__ = f"edit_{abs(hash((goal, cell, common)))}"
    return edit


def _bytes(edit):
    if edit.__name__ not in _PARTS:
        _PARTS[edit.__name__] = D.part(edit, edit.__name__)["bytes"]
    return _PARTS[edit.__name__]


def _upload(c, name, data, project="같은 양식 취합"):
    r = c.post("/api/docs?new=1", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    wid = r.json()["docId"]
    assert c.put(f"/api/works/{wid}/task", json={"kind": "rnd", "file": "plan", "job": "", "project": project}).status_code == 200
    return wid


def _settings():
    return {"schemaVersion": 1, "profileId": "rnd", "profileVersion": 8, "values": D.base()["side"]["values"]}


def _master(c):
    b = D.base()["side"]
    to = _upload(c, "본 계획서.hwpx", b["bytes"])
    s = server._sess(to)
    s.division["applied"] = {"values": b["values"], "planId": "p1", "rev": 0}
    s.division["settings"] = _settings()
    st = HR.state(s)
    st["stage2"] = {**b["graph"], "meta": {"rev": s.rev, "run": 2, "stage1Run": 1}}
    st["stage3"] = {**b["tables"], "meta": {"rev": s.rev, "run": 3, "stage2Run": 2}}
    return to


def _part(c, name, edit):
    pid = _upload(c, name, _bytes(edit))
    c.post(f"/api/docs/{pid}/headings", json={"first": True})
    for _ in range(600):
        if (c.get(f"/api/docs/{pid}/headings").json().get("job") or {}).get("status") != "running":
            break
        time.sleep(0.2)
    server._sess(pid).division["settings"] = _settings()   # 프로젝트 구성 값(프로젝트에서 같이 쓰는 값 — 시험은 세션에 끼운다)
    return pid


def _all(to):
    """목적 문서의 모든 글(본문 블록 · 표 칸)을 한 덩이로."""
    return "\n".join(CA._Texts(server._sess(to).doc).text.values())


def _row(view, pid):
    return next(p for p in view["parts"] if p["work"] == pid)


def _fill(c, to, pid):
    assert c.post(f"/api/docs/{to}/collect/parts/{pid}/bind").status_code == 200
    p = c.post(f"/api/docs/{to}/merge-links/plan", json={"part": pid})
    assert p.status_code == 200, (p.text[:400], {k: v.get("reasons") for k, v in c.get(f"/api/docs/{to}/merge-links").json().items() if k in ("to", "from") and v})
    a = c.post(f"/api/docs/{to}/merge-links/apply", json={"planId": p.json()["planId"]})
    assert a.status_code == 200, a.text[:400]
    return p.json(), a.json()


def test_collect_fill_then_revision_three_way(client):
    c = client
    to = _master(c)
    a1 = _part(c, f"계획서_{J1}_초안.hwpx", _edit(GOAL, CELL))
    v = c.get(f"/api/docs/{to}/collect").json()
    assert v["collect"] and [p["state"] for p in v["parts"]] == ["unassigned"]                      # 같은 묶음의 문서를 저절로 실었다(미지정)
    un = c.post(f"/api/docs/{to}/collect/parts/{a1}/bind")
    got = c.get(f"/api/docs/{to}/merge-links")
    assert un.status_code == 200 and got.status_code == 200 and "unassigned" in got.json()["from"]["reasons"], (un.text[:300], got.text[:300])   # 미지정 문서는 아무것도 안 넣는다
    assert c.post(f"/api/docs/{to}/merge-links/plan", json={"part": a1}).status_code == 409
    auto = c.post(f"/api/docs/{to}/collect/parts/{a1}/auto").json()
    assert auto["auto"]["org"] == J1 and auto["auto"]["by"] == "name" and _row(auto, a1)["state"] == "todo"
    assert c.post(f"/api/docs/{to}/merge-links/plan", json={"part": "다른문서"}).status_code == 409    # 기대한 기관 문서가 아니다
    plan, done = _fill(c, to, a1)
    s = server._sess(to)
    assert GOAL.strip() in _all(to), [(i["value"], i["skip"], i["detail"]) for i in plan["body"]["items"]]
    assert CELL in _all(to), (plan["fixed"]["counts"], [t for t in plan["fixed"]["tables"] if J1 in str(t.get("ctx"))][:3], plan["fixed"]["skipped"][:6])
    assert f"{J1}가 쓴 필요성" not in _all(to)                                                     # 공통 자리 — 「공통 자리 포함」 이 꺼져 있다
    ev = [e for e in s.zones["origins"] if e["part"] == a1]
    assert {e["kind"] for e in ev} >= {"filled", "cells"} and all(e["orgs"] == [J1] and e["src"]["work"] == a1 for e in ev)
    led = [r for e in ev for r in e["led"]]
    assert any(r[2] == GOAL and r[3] is not None for r in led) and any(r[2] == CELL and r[3] == CELL for r in led)   # 원장 = 원본 글 · 넣은 직후 목적 글
    assert c.post(f"/api/docs/{to}/merge-links/plan", json={"part": a1}).json()["todo"] == 0        # 다시 계획하면 할 일 0
    assert _row(c.get(f"/api/docs/{to}/collect").json(), a1)["state"] in ("done", "left")
    z = c.get(f"/api/docs/{to}/zones").json()
    assert [o for o in z["origins"] if o["part"] == a1] and "led" not in z["origins"][0]            # 보기는 원장을 싣지 않는다

    # 다른 기관 문서가 같은 자리를 노려도(반영할 기관을 같게 지정한 둘째 문서) 앞 문서의 내용을 둔다 — 겹침
    b1 = _part(c, "다른 문서.hwpx", _edit(f" o {J1} 다른 글", "o 다른 칸"))
    assert c.put(f"/api/docs/{to}/collect/parts/{b1}", json={"orgs": [J1]}).status_code == 200
    plan_b, _ = _fill(c, to, b1)
    assert plan_b["body"]["counts"]["occupied"] >= 1 and plan_b["body"]["counts"]["changed"] == 0 and f"{J1} 다른 글" not in _all(to)
    assert c.put(f"/api/docs/{to}/collect/parts/{b1}", json={"orgs": []}).status_code == 200         # 미지정으로 되돌림

    # 수정본 — 본문 한 줄과 표 칸이 바뀜 · 그 사이 사람이 표 칸을 고침(겹침)
    a2 = _part(c, f"계획서_{J1}_수정.hwpx", _edit(GOAL2, CELL2, common=False))
    r = c.put(f"/api/docs/{to}/collect/parts/{a2}", json={"orgs": [J1], "revOf": a1})
    assert r.status_code == 200 and _row(r.json(), a2)["state"] == "revision" and _row(r.json(), a1)["state"] == "superseded"
    assert c.put(f"/api/docs/{to}/collect/parts/{b1}", json={"revOf": a1}).status_code == 400       # 이미 수정본이 있는 문서
    c.post(f"/api/docs/{to}/collect/parts/{a2}/bind")
    assert c.post(f"/api/docs/{to}/merge-links/plan", json={"part": a2}).status_code == 409         # 수정본은 다시 넣지 않는다
    c.post(f"/api/docs/{to}/collect/parts/{a1}/bind")
    assert c.post(f"/api/docs/{to}/merge-links/plan", json={"part": a1}).status_code == 409         # 수정본이 생긴 앞 제출본도
    cell = next(r[0] for r in led if r[2] == CELL)
    para = next(i for i, t in server._sess(to).texts.items() if t == CELL and i != cell) if False else None   # (칸 안 문단은 아래에서 칸 글로 고친다)
    with s.lock:
        pid = next(p for p in s.doc._ids if s.texts.get(p) == CELL)
    assert c.patch(f"/api/docs/{to}/blocks/{pid}", json={"text": "o 사람이 고친 칸"}).status_code == 200
    rp = c.post(f"/api/docs/{to}/collect/parts/{a2}/revise/plan")
    assert rp.status_code == 200, rp.text[:500]
    rp = rp.json()
    assert rp["counts"]["ready"] == 1 and rp["counts"]["overlap"] == 1, (rp["counts"], rp["items"], rp["fresh"])                # 본문 줄 = 고칠 곳 · 사람이 고친 칸 = 겹침
    ra = c.post(f"/api/docs/{to}/collect/parts/{a2}/revise/apply", json={"planId": rp["planId"]})
    assert ra.status_code == 200, ra.text[:500]
    now = _all(to)
    assert GOAL2.strip() in now and GOAL.strip() + "\n" not in now + "\n" and "o 사람이 고친 칸" in now and CELL2 not in now
    ev2 = [e for e in s.zones["origins"] if e["part"] == a2]
    assert ev2 and ev2[0].get("mode") == "revise" and any(r[2] == GOAL2 for e in ev2 for r in e["led"])   # 고친 자리만 수정본의 출처로
    assert any(r[0] == cell for e in s.zones["origins"] if e["part"] == a1 for r in e["led"])             # 겹친 칸은 앞 제출본의 원장에 그대로
    again = c.post(f"/api/docs/{to}/collect/parts/{a2}/revise/plan").json()
    assert again["counts"]["ready"] == 0 and again["todo"] == 0 and again["counts"]["overlap"] == 1
    assert _row(c.get(f"/api/docs/{to}/collect").json(), a2)["state"] == "left"                        # 겹침이 남았다(끝남으로 세지 않는다)
    assert c.post(f"/api/docs/{to}/undo").status_code == 200                                           # 실행 취소 — 글 · 출처 · 상태가 함께
    assert GOAL.strip() + "\n" in _all(to) + "\n" and GOAL2.strip() not in _all(to) and not [e for e in s.zones["origins"] if e["part"] == a2]
    assert _row(c.get(f"/api/docs/{to}/collect").json(), a2)["state"] == "revision"
