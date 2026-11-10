"""구분 기준(spec_구분_기준 ② §2~§7) — 설정·파생 뷰·FMM 값 가져오기(모델), 후보·계획(사본 모의 실행), 반영 트랜잭션(문서 전체 검사·undo·rev·기록),
오래된 계획 409, 같은 값 재계획 = 할 일 없음, 지원하지 않는 양식 400, 저장한 기준. 계획 한 번이 10초 안팎이라 양식 반영은 모듈 픽스처 하나로 돌린다."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import division_model as model
from app import division_presets, server
from app.division_profiles import rnd

FORM = Path(__file__).parents[1] / "samples" / "연구개발계획서_양식.hwpx"
SMALL = Path(__file__).parents[1] / "samples" / "기술수요조사서.hwpx"
VALUES = {"stages": [2, 3], "orgs": {"lead": "인텍", "joint": ["", "한국선급"], "nonprofit": [False, False, True]}}


# ---------------------------------------------------------------- 모델 · 프로파일(빠름)

def test_settings_and_dimensions():
    st = model.norm_settings({"values": VALUES}, rnd)
    assert st["profileId"] == "rnd" and st["schemaVersion"] == model.SCHEMA_VERSION and st["profileVersion"] == rnd.VERSION
    v = st["values"]
    assert v["orgs"]["nonprofit"] == [False, False, True] and v["orgs"]["outside"] == [] and v["current"] == 1
    d = rnd.dimensions(v)
    assert [s["id"] for s in d["stages"]] == ["s1", "s2"]
    assert [y["id"] for y in d["stages"][1]["years"]] == ["s2y1", "s2y2", "s2y3"] and d["stages"][1]["years"][0]["no"] == 3  # 차년도는 단계가 부모, 전체 차례도
    orgs = {o["id"]: o for o in d["orgs"]}
    assert orgs["lead"]["role"] == "lead" and orgs["joint1"]["label"] == "참여기관1" and orgs["joint2"]["attrs"]["nonprofit"] is True
    assert d["current"] == {"no": 1, "id": "s1y1"}
    # FMM v1 값 그대로(프리셋 값 꼴)도 설정이 된다 — 뜻 보존(subs = 세부과제 주관기관 이름, current = 전체 차례)
    st2 = model.import_fmm_v1({**VALUES, "subs": ["한국선급"], "current": 3}, rnd)
    assert st2["values"]["subs"] == ["한국선급"] and rnd.dimensions(st2["values"])["current"] == {"no": 3, "id": "s2y1"}
    assert model.settings_hash(st) == model.settings_hash(model.norm_settings(VALUES, rnd)) != model.settings_hash(st2)


@pytest.mark.parametrize("bad", [None, {"values": {"stages": []}}, {"values": {"stages": [11]}}, {"profileId": "x", "values": VALUES},
                                 {"values": {"stages": [1], "orgs": {"nonprofit": [1]}}}])
def test_settings_rejects(bad):
    with pytest.raises((ValueError, TypeError)):
        model.norm_settings(bad, rnd)


def test_status_of():
    before = {"key": "a", "done": False, "reason": None}
    assert model.status_of(before, {"a": {"done": True}}, {"a"}, {}, set()) == ("applied", "맞춤")
    assert model.status_of({**before, "done": True}, {}, {"a"}, {}, set()) == ("already", "이미 맞음")
    assert model.status_of(before, {}, {"a"}, {}, {"a"})[0] == "excluded"
    assert model.status_of(before, {}, set(), {}, set()) == ("applied", "바깥 묶음이 지움")
    assert model.status_of(before, {"a": {"done": False, "reason": "blocked", "message": "병합 칸"}}, {"a"}, {}, set()) == ("unsupported", "병합 칸")
    assert model.status_of(before, {"a": {"done": False, "reason": None}}, {"a"}, {}, set())[0] == "unresolved"
    assert model.status_of(before, {}, {"a"}, {"a": "실패"}, set()) == ("unresolved", "실패")


def test_presets_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("NFM_DIVISION_PRESETS", str(tmp_path / "p.json"))
    a = division_presets.put("new", " 기본  값 ", VALUES)
    assert a["id"] == "p1" and a["name"] == "기본 값" and a["values"]["orgs"]["nonprofit"] == [False, False, True]
    with pytest.raises(division_presets.Conflict):
        division_presets.put("new", "기본 값", VALUES)
    b = division_presets.put("new", "둘", {"stages": [1], "orgs": {"lead": "", "joint": []}})
    assert [x["name"] for x in division_presets.listing()] == ["기본 값", "둘"]
    assert division_presets.put("p1", "하나", VALUES)["name"] == "하나" and division_presets.delete(b["id"]) == "p2"
    with pytest.raises(KeyError):
        division_presets.delete("p9")
    (tmp_path / "p.json").write_text("{broken", encoding="utf-8")
    assert division_presets.listing() == [] and (tmp_path / "p.json.broken").exists()


# ---------------------------------------------------------------- 서버 — 양식 한 번 올려 계획·반영·되돌리기(모듈 픽스처)

@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    """양식 올리기 → 설정 → 계획 → 반영 → 같은 값 재계획 → 되돌리기 — 한 번 돌리고 결과를 시험들이 나눠 본다."""
    import os
    tmp = tmp_path_factory.mktemp("div")
    old = {k: os.environ.get(k) for k in ("NFM_PDF", "NFM_RENDER", "NFM_WORKS", "NFM_DIVISION_PRESETS")}
    os.environ.update(NFM_PDF="off", NFM_RENDER=str(tmp / "render"), NFM_WORKS=str(tmp / "works"), NFM_DIVISION_PRESETS=str(tmp / "presets.json"))
    server.DOCS.clear()
    c = TestClient(server.app)
    out = {"c": c, "works": tmp / "works"}  # conftest 의 자동 픽스처가 시험마다 NFM_WORKS 를 바꾸므로 폴더는 여기 것으로 본다
    d = out["d"] = c.post("/api/docs", files={"file": (FORM.name, FORM.read_bytes())}).json()["docId"]
    out["get0"] = c.get(f"/api/docs/{d}/divisions").json()
    out["put"] = c.put(f"/api/docs/{d}/divisions/settings", json={"values": VALUES})
    out["plan1"] = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    # 계획 뒤 글을 고치면 반영은 409, 되돌리면 rev 가 또 올라 그 계획은 그대로 오래됨
    blocks = c.get(f"/api/docs/{d}").json()["blocks"]
    pid = next(b["id"] for b in blocks if b["type"] == "paragraph" and b["text"].strip())
    c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": "★시험"})
    out["stale"] = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": out["plan1"]["planId"]})
    c.post(f"/api/docs/{d}/blocks/{pid}/revert")
    out["before_bytes"] = c.get(f"/api/docs/{d}/download").content
    out["plan"] = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    out["apply"] = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": out["plan"]["planId"], "expectRev": out["plan"]["baseRev"]})
    out["doc"] = c.get(f"/api/docs/{d}").json()
    out["get1"] = c.get(f"/api/docs/{d}/divisions").json()
    out["after_bytes"] = c.get(f"/api/docs/{d}/download").content
    out["plan_same"] = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    out["apply_same"] = c.post(f"/api/docs/{d}/divisions/apply", json={"planId": out["plan_same"]["planId"]})
    out["undo"] = c.post(f"/api/docs/{d}/undo").json()
    out["get2"] = c.get(f"/api/docs/{d}/divisions").json()
    out["undo_bytes"] = c.get(f"/api/docs/{d}/download").content
    out["log"] = c.get(f"/api/works/{d}/log").json()
    yield out
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    server.DOCS.clear()


def test_profile_and_settings(flow):
    g = flow["get0"]
    assert g["profile"] == {"id": "rnd", "name": rnd.NAME, "version": rnd.VERSION, "form": "연구개발계획서", "supported": True, "supportedForms": ["연구개발계획서"]}
    assert g["settings"] is None and g["applied"] is None and g["plan"] is None
    assert flow["put"].status_code == 200 and flow["put"].json()["dimensions"]["orgs"][2]["attrs"]["nonprofit"] is True


def test_plan_candidates_and_deleted_preview(flow):
    p = flow["plan"]
    s = p["summary"]
    assert s["applied"] >= 80 and s["unresolved"] == 0 and s["errors"] == 0 and s["added"] > 50 and s["removed"] > 20 and s["deleted"] > 50
    statuses = {c["status"] for c in p["candidates"]}
    assert statuses <= set(model.STATUSES) and "applied" in statuses and "unsupported" in statuses  # 병합 칸·차례 어긴 라벨 2곳은 지원 안 됨
    uns = [c for c in p["candidates"] if c["status"] == "unsupported"]
    assert all(c["statusMessage"] for c in uns)
    c0 = next(c for c in p["candidates"] if c["drop"])  # 지워질 항목의 글이 미리보기에(② §5)
    assert c0["drop"][0]["texts"] and all("label" in d for d in c0["drop"])
    assert p["deleted"] and all(d["text"] for d in p["deleted"]) and p["changes"] and {"id", "old", "new", "key"} <= set(p["changes"][0])
    assert p["baseRev"] == 2 and p["profileVersion"] == rnd.VERSION and len(p["sha256"]) == 64 and "_doc" not in p


def test_stale_plan_rejected(flow):
    assert flow["stale"].status_code == 409 and "다시 계획" in flow["stale"].json()["detail"]


def test_apply_transaction(flow):
    a = flow["apply"]
    assert a.status_code == 200, a.text
    r = a.json()
    assert r["rev"] == 3 and r["undo"] == 1 and r["owpml"]["status"] == "ok" and r["unresolved"] == []  # 문서 전체 검사 통과 · undo 1 · rev +1
    assert r["detail"] and r["detail"].startswith("divisions/") and r["applied"]["rev"] == 3 and r["applied"]["values"]["stages"] == [2, 3]
    assert {c["status"] for c in r["candidates"]} <= set(model.STATUSES)
    doc = flow["doc"]
    kinds = doc["kinds"]
    assert any(v == "new" for v in kinds.values()) and any(v == "removed" for v in kinds.values()) and any(v == "text" for v in kinds.values())
    assert flow["after_bytes"] != flow["before_bytes"]
    g = flow["get1"]
    assert g["applied"]["planId"] == flow["plan"]["planId"] and g["plan"] is None
    texts = " ".join(b["text"] for b in doc["blocks"] if b["type"] == "paragraph")
    assert "인텍" in texts and "한국선급" in texts  # 기관 이름이 라벨에 들어감


def test_placeholder_item_shape_matches_siblings(flow):
    """2-2 기관 문단 묶음(② §5 「항목 꼴 맞춤」): 양식의 「[공동연구개발기관N(기관명 기입)]」 아래에만 7pt 빈 줄이 끼어 있어 이름을 넣은 항목·사본이
    「라벨 → 빈 줄 → o」가 되고 뒤 빈 줄이 빠지던 것(2026-11-10 사용자 "중간 줄이 맞지 않네") — 반영 뒤에는 주관·공동1 처럼 「라벨 → o → 빈 줄」."""
    tops = [b for b in flow["doc"]["blocks"]]
    text = lambda b: b["text"].strip() if b["type"] == "paragraph" else None  # noqa: E731
    labels = [i for i, b in enumerate(tops) if b["type"] == "paragraph" and "[공동연구개발기관2(한국선급)]" in b["text"]]
    assert labels, "2-2 의 공동2 라벨이 있어야 한다"
    checked = same = 0
    for i in labels:
        lead = next((k for k in range(i - 1, max(0, i - 12), -1) if "[주관연구개발기관(" in (tops[k].get("text") or "")), None)
        if lead is None:
            continue
        if text(tops[lead + 1]) == "":  # 「(2) 일자리 창출 계획」 — 셋 다 「라벨 → 빈 줄 → o」인 묶음은 손대지 않는다
            assert text(tops[i + 1]) == "", (i, tops[i + 1]["text"])
            same += 1
            continue
        assert text(tops[i + 1]) == "o", (i, tops[i + 1]["text"])  # 주관처럼 라벨 바로 다음이 「o」(7pt 빈 줄이 끼지 않음)
        assert text(tops[i + 2]) == "", (i, tops[i + 2]["text"])  # 그다음은 빈 줄
        checked += 1
    assert checked >= 5 and same >= 1
    # 원본에서 N 항목의 군더더기 빈 문단이 후보에 잡힌다(라벨 바로 뒤, 항목 길이에는 안 셈)
    from app import hwpx_doc
    d = hwpx_doc.HwpxDoc(FORM.read_bytes())
    blocks = d.blocks()
    gs = [g for g in rnd.find(blocks, rnd.levels_of(blocks), model.norm_settings({"values": VALUES}, rnd)["values"])
          if g["kind"] == "paragraph" and any(it.get("stray") for it in g["items"])]
    assert len(gs) >= 10 and all(len(g["items"][-1]["stray"]) == 1 and not g["items"][0]["stray"] for g in gs)
    assert all(len({it["size"] for it in g["items"]}) == 1 for g in gs)  # 군더더기를 빼면 세 항목의 길이가 같다


def test_same_values_nothing_to_do(flow):
    s = flow["plan_same"]["summary"]
    assert s["applied"] == 0 and s["changes"] == 0 and s["unresolved"] == 0
    r = flow["apply_same"]
    assert r.status_code == 200 and r.json()["nothing"] is True and r.json()["rev"] == 3  # undo·rev 안 올림


def test_undo_restores_document_and_applied_state(flow):
    u = flow["undo"]
    assert u["rev"] == 4 and u["undo"] == 0 and u["pristine"] is True and u["editedCount"] == 0
    assert flow["undo_bytes"] == flow["before_bytes"] and flow["get2"]["applied"] is None


def test_log_lines(flow):
    kinds = [e["kind"] for e in flow["log"]["events"]]
    assert kinds.count("divisionPlan") == 3 and kinds.count("divisions") == 1 and "undo" in kinds
    ev = next(e for e in flow["log"]["events"] if e["kind"] == "divisions")
    assert ev["planId"] == flow["plan"]["planId"] and ev["summary"]["applied"] == flow["plan"]["summary"]["applied"] and ev["rev"] == 3
    rec = json.loads((flow["works"] / flow["d"] / flow["apply"].json()["detail"]).read_text(encoding="utf-8"))
    assert rec["appliedRev"] == 3 and len(rec["candidates"]) == len(flow["plan"]["candidates"])


def test_unsupported_form_400_and_validation(flow):
    c = flow["c"]
    d2 = c.post("/api/docs", files={"file": (SMALL.name, SMALL.read_bytes())}).json()["docId"]
    r = c.post(f"/api/docs/{d2}/divisions/plan", json={"values": VALUES})
    assert r.status_code == 400 and "지원" in r.json()["detail"]
    assert c.get(f"/api/docs/{d2}/divisions").json()["profile"]["supported"] is False
    assert c.post(f"/api/docs/{d2}/divisions/plan", json={}).status_code == 400  # 값 없음
    assert c.put(f"/api/docs/{d2}/divisions/settings", json={"values": {"stages": [0]}}).status_code == 400
    assert c.post(f"/api/docs/{flow['d']}/divisions/apply", json={"planId": "nope"}).status_code == 409


def test_presets_api(flow):
    c = flow["c"]
    r = c.put("/api/divisions/presets/new", json={"name": "시험", "values": VALUES})
    assert r.status_code == 200 and r.json()["id"] == "p1"
    assert c.put("/api/divisions/presets/new", json={"name": "시험", "values": VALUES}).status_code == 409
    assert c.put("/api/divisions/presets/new", json={"name": "", "values": VALUES}).status_code == 400
    assert [p["name"] for p in c.get("/api/divisions/presets").json()["presets"]] == ["시험"]
    assert c.get(f"/api/docs/{flow['d']}/divisions").json()["presets"][0]["name"] == "시험"
    assert c.delete("/api/divisions/presets/p1").json() == {"deleted": "p1"} and c.delete("/api/divisions/presets/p1").status_code == 404


# ---- 문서 표시 · 추가한 자리 · LLM 재검토(spec_구분_기준 ② §11) --------------------------------------------------------

def _open_form(c):
    return c.post("/api/docs", files={"file": (FORM.name, FORM.read_bytes())}).json()["docId"]


def _log_events(c, d):
    r = c.get(f"/api/works/{d}/log").json()
    return r if isinstance(r, list) else r.get("events") or r.get("log") or []


def _three_body_paras(c, d):
    """본문(표 밖) 맨 위 블록 중 글 있는 문단 셋(차례대로, 서로 떨어져도 됨 — 사이에 라벨이 없게 앞쪽 120블록 안에서)."""
    blocks = c.get(f"/api/docs/{d}").json()["blocks"]
    out = []
    for b in blocks[:400]:
        if b["type"] == "paragraph" and b["text"].strip() and not rnd.core._label(b["text"]) and len(b["text"]) < 60:
            out.append(b["id"])
            if len(out) == 3:
                break
    assert len(out) == 3
    return out


def test_members_and_hints():
    """members = 계획 없이 묶음·문단 id · hint 꼴 규칙: 「가. 1차년도 목표」 한 문단만 표시해도 같은 꼴 형제 둘이 라벨이 되어 묶음(3항목) → 계획 후보에 hinted."""
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    m0 = c.get(f"/api/docs/{d}/divisions/members").json()
    assert m0["supported"] and m0["groups"] and m0["hints"] == [] and m0["rev"] >= 0
    g0 = m0["groups"][0]
    assert {"key", "dim", "dimName", "kind", "kindName", "where", "count", "done", "irregular", "hinted", "items"} <= set(g0)
    assert g0["items"][0]["paras"] and g0["items"][0]["label"] in g0["items"][0]["paras"] or g0["kind"] != "paragraph"
    assert all(not g["hinted"] for g in m0["groups"])
    p1, p2, p3 = _three_body_paras(c, d)
    for pid, text in ((p1, "가. 1차년도 목표"), (p2, "가. 2차년도 목표"), (p3, "가. N차년도 목표")):   # PARA_LABEL 에 안 맞아 자동으로는 라벨이 아님
        assert c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": text}).status_code == 200
    m1 = c.get(f"/api/docs/{d}/divisions/members").json()
    assert not any(p1 in it["paras"] and it["label"] == p1 for g in m1["groups"] for it in g["items"])
    # 틀린 입력
    assert c.post(f"/api/docs/{d}/divisions/hints", json={"para": "nope", "dim": "year"}).status_code == 400
    assert c.post(f"/api/docs/{d}/divisions/hints", json={"para": p1, "dim": ""}).status_code == 400
    r = c.post(f"/api/docs/{d}/divisions/hints", json={"para": p1, "dim": "year", "note": "시험"}).json()
    h = r["hint"]
    assert h["para"] == p1 and h["dim"] == "year" and h["value"] == "1차년도" and h["by"] == "user" and h["note"] == "시험" and len(r["hints"]) == 1
    m2 = c.get(f"/api/docs/{d}/divisions/members").json()
    g = next(g for g in m2["groups"] if g["hinted"])
    assert g["dim"] == "year" and g["count"] == 3 and [it["label"] for it in g["items"]] == [p1, p2, p3] and [it["value"] for it in g["items"]] == ["1차년도", "2차년도", "N차년도"]
    assert p1 in g["items"][0]["paras"]
    hr = m2["hints"][0]
    assert hr["engine"] is True and hr["exists"] and hr["text"] == "가. 1차년도 목표" and hr["read"] == {"dim": "year", "dimName": "차년도", "value": "1차년도"} and hr["dimName"] == "차년도"
    view = c.get(f"/api/docs/{d}/divisions").json()
    assert len(view["hints"]) == 1
    # 같은 문단을 다시 넣으면 고치기(id 유지)
    r2 = c.post(f"/api/docs/{d}/divisions/hints", json={"para": p1, "dim": "year", "value": "1차년도", "note": "고침"}).json()
    assert r2["hint"]["id"] == h["id"] and r2["hint"]["note"] == "고침" and len(r2["hints"]) == 1
    # 계획에 hinted 후보
    assert c.put(f"/api/docs/{d}/divisions/settings", json={"values": VALUES}).status_code == 200
    plan = c.post(f"/api/docs/{d}/divisions/plan", json={}).json()
    cand = next(x for x in plan["candidates"] if x["key"] == p1)
    assert cand["hinted"] is True and cand["dim"] == "year" and cand["count"] == 3 and plan["hints"] == [p1]
    assert all(not x.get("hinted") for x in plan["candidates"] if x["key"] != p1)
    # 작업 저장 → 메모리에서 비우고 다시 열어도 hint 가 남음
    server.DOCS.clear()
    m3 = c.get(f"/api/docs/{d}/divisions/members").json()
    assert [x["para"] for x in m3["hints"]] == [p1]
    # 지우기
    assert c.delete(f"/api/docs/{d}/divisions/hints/{h['id']}").json()["hints"] == []
    assert c.delete(f"/api/docs/{d}/divisions/hints/{h['id']}").status_code == 404
    assert not any(g["hinted"] for g in c.get(f"/api/docs/{d}/divisions/members").json()["groups"])
    kinds = [x["kind"] for x in _log_events(c, d)]
    assert kinds.count("divisionHint") == 3
    server.DOCS.clear()


def test_llm_review_applies_revisions(monkeypatch):
    """LLM 재검토 — 응답의 add/change/remove 를 지금 문서의 문단 id 에 대고 검증해 hint 층에만 반영, 호출 기록·로그."""
    from app import division_llm
    server.DOCS.clear()
    c = TestClient(server.app)
    d = _open_form(c)
    assert c.post(f"/api/docs/{d}/divisions/llm_review", json={}).status_code == 400   # 표시한 자리가 없음
    p1, p2, p3 = _three_body_paras(c, d)
    for pid, text in ((p1, "나. 1단계 계획"), (p2, "다. 2단계 추진 계획")):   # 꼴이 달라 꼴 규칙만으로는 안 묶임 — LLM 이 형제로 더하면 「hint:stage」 로 한 묶음
        c.patch(f"/api/docs/{d}/blocks/{pid}", json={"text": text})
    hid = c.post(f"/api/docs/{d}/divisions/hints", json={"para": p1, "dim": "year"}).json()["hint"]["id"]   # 일부러 틀린 구분(글은 단계)
    assert not any(g["hinted"] for g in c.get(f"/api/docs/{d}/divisions/members").json()["groups"])   # 혼자라 묶음 아님
    seen = {}

    def fake_ask(payload, *, call=None, effort="medium", timeout=240.0):
        seen["payload"] = payload
        return {"data": {"revisions": [
            {"action": "change", "hintId": hid, "para": p1, "dim": "stage", "value": "1단계", "reason": "글은 단계"},
            {"action": "add", "hintId": "", "para": p2, "dim": "stage", "value": "", "reason": "형제"},
            {"action": "add", "hintId": "", "para": "p-none", "dim": "stage", "value": "", "reason": "없는 id"},
            {"action": "add", "hintId": "", "para": p3, "dim": "other", "value": "", "reason": "값 낱말 없음"},
            {"action": "remove", "hintId": hid, "para": p1, "dim": "stage", "value": "", "reason": "사용자 것 — 제안만"}],
            "summary": "형제 하나를 더했습니다."}, "prompt": "p", "call": {"backend": "fake", "model": "m", "effort": effort, "ms": 5, "costUsd": 0, "error": None}}
    monkeypatch.setattr(division_llm, "ask", fake_ask)
    r = c.post(f"/api/docs/{d}/divisions/llm_review", json={})
    assert r.status_code == 200, r.text
    out = r.json()
    pl = seen["payload"]
    assert pl["hints"][0]["hintId"] == hid and pl["hints"][0]["read"] == {"dim": "stage", "value": "1단계"} and pl["hints"][0]["inGroup"] is False
    assert any(x["id"] == p1 for x in pl["hints"][0]["around"]) and pl["groups"] and pl["candidates"] and pl["outline"] is not None
    assert any(x["id"] == p2 and x["dim"] == "stage" for x in pl["candidates"])   # 라벨이 아닌데 값 낱말이 있는 문단 = 후보
    assert out["summary"] == "형제 하나를 더했습니다." and out["call"]["backend"] == "fake" and out["detail"].startswith("divisions/llm_")
    assert len(out["applied"]) == 4 and len(out["skipped"]) == 1 and out["skipped"][0]["why"] == "문단 id 가 문서에 없음"
    hs = {h["para"]: h for h in out["hints"]}
    assert hs[p1]["dim"] == "stage" and hs[p1]["value"] == "1단계" and hs[p1]["by"] == "user" and hs[p1]["llmNote"] and hs[p1]["reason"]
    assert hs[p2]["by"] == "llm" and hs[p2]["dim"] == "stage" and hs[p2]["value"] == "2단계" and hs[p2]["reason"] == "형제"
    assert hs[p3]["by"] == "llm" and hs[p3]["dim"] == "other" and hs[p3]["value"] == ""   # 기타 + 값 낱말 없음 → 표시만
    m = c.get(f"/api/docs/{d}/divisions/members").json()
    g = next(g for g in m["groups"] if g["hinted"])   # LLM 이 더한 형제(다른 꼴)와 사용자 표시가 「hint:stage」 로 한 묶음(1단계·2단계)
    eng = {h["para"]: h["engine"] for h in m["hints"]}
    assert g["dim"] == "stage" and g["count"] == 2 and [it["label"] for it in g["items"]] == [p1, p2] and eng == {p1: True, p2: True, p3: False}
    # 답이 없으면 502, 기록은 남김
    monkeypatch.setattr(division_llm, "ask", lambda payload, **k: {"data": None, "prompt": "p", "call": {"backend": None, "model": "m", "effort": "medium", "ms": 1, "costUsd": None, "error": "off"}})
    assert c.post(f"/api/docs/{d}/divisions/llm_review", json={}).status_code == 502
    kinds = [x["kind"] for x in _log_events(c, d)]
    assert kinds.count("divisionLlm") == 2 and kinds.count("divisionHint") == 1
    server.DOCS.clear()

